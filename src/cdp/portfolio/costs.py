"""Modelo de custos de transação: meio spread + comissão + câmbio + impacto raiz quadrada.

Custo de negociar ``t`` (fração do NAV) no emissor *i*, também em fração do NAV::

    custo_i(t) = linear_i · |t| + k_i · |t|^1.5

- ``linear_i`` = meio spread (faixa de ADTV da linha) + comissão do mercado de execução +
  custo de câmbio (somente linhas não USD), em decimal por unidade negociada.
- ``k_i`` = ``impact_coefficient`` · σ_diária_i · sqrt(NAV / ADTV_i). Assim o impacto por dólar
  negociado é ``impact_coefficient · σ · sqrt(Q / ADTV)`` (lei da raiz quadrada) e o custo total
  em fração do NAV fica ``k · |t|^1.5``.

As pernas comprada e vendida podem ser executadas em linhas diferentes (ex.: local MX para
comprar, ADR para vender a descoberto). O modelo guarda os parâmetros por perna e uma curva
combinada conservadora (pior entre as linhas utilizáveis do emissor) para quem precisa de uma
única curva por emissor.

Dados ausentes nunca viram zero:
- ADTV da linha ausente ⇒ ADTV agregado do emissor (``panel_assets.adtv_usd``); se também
  ausente ⇒ ``cfg.liquidity.min_adtv_usd`` (piso conservador). Ambos são sinalizados.
- Volatilidade diária ausente ⇒ percentil 90 da seção transversal (conservador), sinalizado.
- Mercado sem comissão configurada ⇒ maior comissão configurada (conservador), sinalizado.
- Moeda da linha ausente ⇒ inferida pelo mercado de listagem (US ⇒ USD; demais ⇒ cobra FX).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cvxpy as cp
import numpy as np
import pandas as pd

from ..config import FundConfig
from ..universe import listing_market

Leg = Literal["combined", "long", "short"]
IMPACT_EXPONENT = 1.5
BPS = 1e4
MISSING_VOL_QUANTILE = 0.90


@dataclass(frozen=True)
class CostModel:
    """Parâmetros de custo por emissor (índice ``issuer_id``).

    ``linear_rate``/``impact_k`` formam a curva combinada (conservadora). As séries por perna
    (``*_long``/``*_short``) são usadas pelo otimizador, que separa a carteira em perna
    comprada ``l ≥ 0`` e vendida ``s ≥ 0`` (``w = l − s``). ``components`` traz o detalhamento
    (faixa, spread, comissão, FX, ADTV de referência e flags de qualidade) para auditoria.
    """

    index: pd.Index
    linear_rate: pd.Series
    impact_k: pd.Series
    linear_rate_long: pd.Series | None = None
    impact_k_long: pd.Series | None = None
    linear_rate_short: pd.Series | None = None
    impact_k_short: pd.Series | None = None
    components: pd.DataFrame | None = None

    def leg_params(self, leg: Leg = "combined") -> tuple[pd.Series, pd.Series]:
        """Retorna ``(linear, k)`` da perna pedida (cai na curva combinada se não houver)."""
        if leg == "long" and self.linear_rate_long is not None and self.impact_k_long is not None:
            return self.linear_rate_long, self.impact_k_long
        if leg == "short" and self.linear_rate_short is not None \
                and self.impact_k_short is not None:
            return self.linear_rate_short, self.impact_k_short
        if leg not in ("combined", "long", "short"):
            raise ValueError(f"Perna de custo desconhecida: {leg!r}")
        return self.linear_rate, self.impact_k

    def reindex(self, ids: list[str] | pd.Index) -> CostModel:
        """Subconjunto ordenado do modelo; emissor sem custo é erro (nunca custo zero)."""
        ids = pd.Index(list(ids))
        missing = sorted(set(ids) - set(self.index))
        if missing:
            raise KeyError(f"Emissores sem parâmetros de custo: {missing}")

        def sub(s: pd.Series | None) -> pd.Series | None:
            return None if s is None else s.reindex(ids)

        comp = None if self.components is None else self.components.reindex(ids)
        return CostModel(
            index=ids, linear_rate=self.linear_rate.reindex(ids),
            impact_k=self.impact_k.reindex(ids),
            linear_rate_long=sub(self.linear_rate_long), impact_k_long=sub(self.impact_k_long),
            linear_rate_short=sub(self.linear_rate_short), impact_k_short=sub(self.impact_k_short),
            components=comp,
        )


# ==========================================================
# Construção
# ==========================================================

def adtv_tier(adtv_usd: pd.Series, breaks_usd: list[float]) -> pd.Series:
    """Faixa de liquidez ``T1`` (mais líquida) … ``T{n+1}`` a partir dos cortes de ADTV.

    ``T1`` se ADTV ≥ maior corte; ``T2`` se ≥ segundo corte; …; última faixa abaixo de todos.
    ADTV ausente cai na última faixa (conservador).
    """
    cuts = sorted((float(b) for b in breaks_usd), reverse=True)
    vals = pd.to_numeric(adtv_usd, errors="coerce").to_numpy(dtype=float)
    # número de cortes em que o ADTV fica abaixo ⇒ posição da faixa
    below = np.zeros(len(vals), dtype=int)
    for c in cuts:
        below += ~(vals >= c)  # NaN conta como abaixo (conservador)
    return pd.Series([f"T{k + 1}" for k in below], index=adtv_usd.index, dtype=object)


def _resolve_daily_vol(daily_vol: pd.Series, ids: pd.Index) -> tuple[pd.Series, pd.Series]:
    vol = pd.to_numeric(daily_vol, errors="coerce").reindex(ids)
    vol = vol.where(vol > 0)
    known = vol.dropna()
    if known.empty:
        raise ValueError("Volatilidade diária ausente para todos os emissores do modelo de custo.")
    fallback = float(known.quantile(MISSING_VOL_QUANTILE))
    flag = vol.isna()
    return vol.fillna(fallback), flag


def _clean_str(s: pd.Series) -> pd.Series:
    """Texto limpo ou ``None`` (ausente); nunca string vazia ou 'nan'."""
    vals = [v.strip() if isinstance(v, str) and v.strip() not in ("", "nan", "None") else None
            for v in s.tolist()]
    return pd.Series(vals, index=s.index, dtype=object)


def _leg_frame(sides: pd.DataFrame, leg: str, ids: pd.Index) -> pd.DataFrame:
    cols = {
        "ticker": f"{leg}_ticker",
        "line_type": f"{leg}_line_type",
        "currency": f"{leg}_currency",
        "adtv_usd": f"adtv_{leg}_usd",
    }
    sd = sides.reindex(ids)
    out = pd.DataFrame(index=ids)
    for name, col in cols.items():
        out[name] = sd[col] if col in sd.columns else pd.Series(np.nan, index=ids, dtype=object)
    out["ticker"] = _clean_str(out["ticker"])
    out["line_type"] = _clean_str(out["line_type"])
    out["currency"] = _clean_str(out["currency"])
    out["adtv_usd"] = pd.to_numeric(out["adtv_usd"], errors="coerce")
    out.loc[~(out["adtv_usd"] > 0), "adtv_usd"] = np.nan
    return out


def _leg_params(leg_df: pd.DataFrame, panel_assets: pd.DataFrame, vol: pd.Series,
                cfg: FundConfig, nav: float) -> pd.DataFrame:
    """Parâmetros de custo de uma perna (linha de execução) por emissor."""
    costs = cfg.costs
    ids = leg_df.index
    flags: dict[str, list[str]] = {i: [] for i in ids}

    def flag(mask: pd.Series, token: str) -> None:
        for i in mask.index[mask.to_numpy(dtype=bool)]:
            flags[i].append(token)

    has_line = leg_df["ticker"].notna()
    flag(~has_line, "sem_linha_execucao")

    # Mercado de execução: sufixo do ticker; sem linha ⇒ país do emissor (pode não ter tabela).
    country = panel_assets["country"].reindex(ids) if "country" in panel_assets.columns \
        else pd.Series(np.nan, index=ids, dtype=object)
    market = pd.Series(
        [listing_market(t) if isinstance(t, str) else (c if isinstance(c, str) else "NA")
         for t, c in zip(leg_df["ticker"], country, strict=True)],
        index=ids, dtype=object,
    )

    # ADTV de referência com fallbacks explícitos.
    adtv = leg_df["adtv_usd"].copy()
    issuer_adtv = pd.to_numeric(panel_assets.get("adtv_usd", pd.Series(dtype=float)),
                                errors="coerce").reindex(ids)
    issuer_adtv = issuer_adtv.where(issuer_adtv > 0)
    use_issuer = adtv.isna() & issuer_adtv.notna()
    flag(use_issuer, "adtv_emissor")
    adtv = adtv.where(~use_issuer, issuer_adtv)
    use_floor = adtv.isna()
    flag(use_floor, "adtv_minimo_config")
    adtv = adtv.fillna(float(max(cfg.liquidity.min_adtv_usd, 1.0)))

    tier = adtv_tier(adtv.where(~use_floor), costs.tier_adtv_breaks_usd)
    worst_spread = max(costs.half_spread_bps_by_tier.values())
    half_spread = tier.map(lambda t: costs.half_spread_bps_by_tier.get(t, worst_spread))
    flag(~tier.isin(list(costs.half_spread_bps_by_tier)), "faixa_sem_spread")

    worst_comm = max(costs.commission_bps.values())
    commission = market.map(lambda m: costs.commission_bps.get(m, worst_comm)).astype(float)
    flag(~market.isin(list(costs.commission_bps)), "comissao_conservadora")

    currency = leg_df["currency"].copy()
    inferred = currency.isna()
    flag(inferred, "moeda_inferida")
    currency = currency.where(~inferred, market.map(lambda m: "USD" if m == "US" else None))
    fx_bps = pd.Series(np.where(currency == "USD", 0.0, costs.fx_cost_bps), index=ids)

    linear_bps = half_spread.astype(float) + commission + fx_bps
    impact_k = costs.impact_coefficient * vol * np.sqrt(nav / adtv)

    out = pd.DataFrame({
        "ticker": leg_df["ticker"],
        "market": market,
        "currency": currency,
        "adtv_ref_usd": adtv,
        "tier": tier,
        "half_spread_bps": half_spread.astype(float),
        "commission_bps": commission,
        "fx_bps": fx_bps,
        "linear_bps": linear_bps,
        "linear_rate": linear_bps / BPS,
        "impact_k": impact_k,
    }, index=ids)
    out["flags"] = [";".join(flags[i]) for i in ids]
    return out


def build_cost_model(sides: pd.DataFrame, panel_assets: pd.DataFrame, daily_vol: pd.Series,
                     cfg: FundConfig, nav: float) -> CostModel:
    """Constrói o :class:`CostModel` por emissor.

    ``sides``: tabela de linhas de execução (índice ``issuer_id``) com ``long_ticker``,
    ``long_currency``, ``adtv_long_usd``, ``short_ticker``, ``short_currency``,
    ``adtv_short_usd`` e ``can_short``. ``panel_assets``: ``AssetPanel.assets`` (``adtv_usd``,
    ``country``). ``daily_vol``: volatilidade diária total do emissor (decimal).

    A curva combinada usa o pior caso entre a linha comprada e a linha vendida (esta só quando
    existe linha de short distinta e o emissor é alugável).
    """
    if not nav > 0:
        raise ValueError("NAV precisa ser positivo para o modelo de custos.")
    ids = pd.Index(sorted(set(sides.index) | set(panel_assets.index)), name="issuer_id")
    vol, vol_flag = _resolve_daily_vol(daily_vol, ids)

    long_df = _leg_params(_leg_frame(sides, "long", ids), panel_assets, vol, cfg, nav)
    short_raw = _leg_frame(sides, "short", ids)
    short_df = _leg_params(short_raw, panel_assets, vol, cfg, nav)

    # Sem linha de short própria ⇒ a perna vendida (ex.: zeragem de short legado) usa a
    # curva da linha comprada, sinalizada; nunca custo zero.
    no_short_line = short_raw["ticker"].isna()
    for col in ("linear_rate", "impact_k", "linear_bps"):
        short_df.loc[no_short_line, col] = long_df.loc[no_short_line, col]
    short_df.loc[no_short_line, "flags"] = "sem_linha_short_usa_curva_long"

    can_short = sides.reindex(ids).get("can_short", pd.Series(False, index=ids))
    can_short = can_short.map(lambda v: bool(v) if isinstance(v, (bool, np.bool_)) else
                              (str(v).strip().lower() in {"true", "1", "yes", "sim"}
                               if pd.notna(v) else False))
    usable_short = can_short & ~no_short_line
    linear = long_df["linear_rate"].where(
        ~usable_short, np.maximum(long_df["linear_rate"], short_df["linear_rate"]))
    impact = long_df["impact_k"].where(
        ~usable_short, np.maximum(long_df["impact_k"], short_df["impact_k"]))

    components = pd.concat(
        {"long": long_df.drop(columns=["linear_rate"]),
         "short": short_df.drop(columns=["linear_rate"])}, axis=1)
    components[("issuer", "daily_vol")] = vol
    components[("issuer", "daily_vol_imputed")] = vol_flag
    components[("issuer", "usable_short_line")] = usable_short

    return CostModel(
        index=ids, linear_rate=linear.astype(float), impact_k=impact.astype(float),
        linear_rate_long=long_df["linear_rate"].astype(float),
        impact_k_long=long_df["impact_k"].astype(float),
        linear_rate_short=short_df["linear_rate"].astype(float),
        impact_k_short=short_df["impact_k"].astype(float),
        components=components,
    )


# ==========================================================
# Avaliação (cvxpy e numérica)
# ==========================================================

def cost_expr(t: cp.Expression, cm: CostModel, leg: Leg = "combined") -> cp.Expression:
    """Expressão convexa do custo total (fração do NAV) para o vetor de negociação ``t``.

    ``t`` precisa estar alinhado a ``cm.index`` (use :meth:`CostModel.reindex`).
    """
    lin, k = cm.leg_params(leg)
    lin_v = _finite_array(lin, "custo linear")
    k_v = _finite_array(k, "coeficiente de impacto")
    if t.shape not in ((len(lin_v),), (len(lin_v), 1)):
        raise ValueError(f"Dimensão de t {t.shape} difere do modelo de custo ({len(lin_v)}).")
    abs_t = cp.abs(t)
    return lin_v @ abs_t + k_v @ cp.power(abs_t, IMPACT_EXPONENT)


def _finite_array(s: pd.Series, what: str) -> np.ndarray:
    arr = s.to_numpy(dtype=float)
    if not np.all(np.isfinite(arr)) or np.any(arr < 0):
        bad = list(s.index[~np.isfinite(arr) | (arr < 0)])
        raise ValueError(f"Parâmetro de {what} inválido (NaN/negativo) para: {bad}")
    return arr


def estimate_costs(t: pd.Series, cm: CostModel, leg: Leg = "combined") -> pd.Series:
    """Custo estimado (fração do NAV) por emissor para negociações ``t`` (fração do NAV)."""
    lin, k = cm.leg_params(leg)
    t = pd.to_numeric(t, errors="coerce")
    missing = sorted(set(t.index) - set(cm.index))
    if missing:
        raise KeyError(f"Emissores sem parâmetros de custo: {missing}")
    a = t.abs()
    return lin.reindex(t.index) * a + k.reindex(t.index) * a ** IMPACT_EXPONENT


def split_legs(w: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Separa pesos em perna comprada ``l = max(w, 0)`` e vendida ``s = max(−w, 0)``."""
    return w.clip(lower=0.0), (-w).clip(lower=0.0)


def estimate_rebalance_costs(w_target: pd.Series, w_current: pd.Series | None,
                             cm: CostModel) -> pd.Series:
    """Custo (fração do NAV) de ir de ``w_current`` para ``w_target`` usando a curva de cada perna.

    Emissores ausentes de ``w_current`` não têm posição (peso zero — ausência de posição, não
    dado faltante). Pesos ``NaN`` são erro.
    """
    ids = w_target.index.union(w_current.index if w_current is not None else pd.Index([]))
    wt = w_target.reindex(ids)
    if w_current is None:
        w0 = pd.Series(0.0, index=ids)
    else:
        if w_current.isna().any():
            raise ValueError("Pesos atuais com NaN: posição desconhecida não vira zero.")
        w0 = w_current.reindex(ids).fillna(0.0)
    if w_target.isna().any():
        raise ValueError("Pesos-alvo com NaN.")
    wt = wt.fillna(0.0)
    l1, s1 = split_legs(wt)
    l0, s0 = split_legs(w0)
    return estimate_costs(l1 - l0, cm, "long") + estimate_costs(s1 - s0, cm, "short")


def cost_bps_of_traded(t: pd.Series, costs: pd.Series) -> pd.Series:
    """Converte custo (fração do NAV) em bps do valor negociado; ``NaN`` onde não há negociação."""
    a = t.abs().reindex(costs.index)
    return (costs / a.where(a > 0)) * BPS


# ==========================================================
# Custo da execução no leilão de fechamento (seção ``execution``)
# ==========================================================

def custos_fechamento(trades: pd.DataFrame, cfg: FundConfig, *, spread_mult: float = 1.0,
                      vol_mult: float = 1.0) -> pd.DataFrame:
    """Custo por linha negociada no fechamento (USD e bps do nocional negociado).

    ``trades`` (índice ``ticker``): ``notional_usd`` (|valor negociado|), ``adtv_usd`` (ADTV da
    linha), ``sigma_d`` (σ diária do emissor), ``market`` (mercado de listagem), ``currency``,
    ``categoria`` (``ADR``, ``US_STOCK``, país…), ``local_fechado`` (ADR negociado sem pregão
    na bolsa local) e, opcional, ``flag``. Custo em bps::

        meio spread (faixa de ADTV) × [closed_home_market_spread_mult se local fechado]
        + comissão do mercado + câmbio (linha não USD)
        + impact_coefficient · σ · √(nocional / ADTV) · close_impact_discount[categoria]

    ``spread_mult``/``vol_mult`` aplicam o cenário de estresse (spreads e σ × 2). ADTV ou σ
    ausentes nunca viram zero (o chamador informa o piso conservador e a ``flag``)."""
    costs = cfg.costs
    ex = cfg.execution
    discount = dict(ex.close_impact_discount) if ex is not None else {}
    home_mult = float(ex.closed_home_market_spread_mult) if ex is not None else 1.0
    if trades.empty:
        return pd.DataFrame(columns=["half_spread_bps", "commission_bps", "fx_bps",
                                     "impact_bps", "total_bps", "cost_usd", "flags"])
    adtv = pd.to_numeric(trades["adtv_usd"], errors="coerce")
    tier = adtv_tier(adtv, costs.tier_adtv_breaks_usd)
    worst_spread = max(costs.half_spread_bps_by_tier.values())
    half = tier.map(lambda t: costs.half_spread_bps_by_tier.get(t, worst_spread)).astype(float)
    closed = trades.get("local_fechado", pd.Series(False, index=trades.index)).fillna(
        False).astype(bool)
    half = half * np.where(closed, home_mult, 1.0) * spread_mult
    worst_comm = max(costs.commission_bps.values())
    comm = trades["market"].map(lambda m: costs.commission_bps.get(m, worst_comm)).astype(float)
    fx = pd.Series(np.where(trades["currency"].astype(str) == "USD", 0.0, costs.fx_cost_bps),
                   index=trades.index)
    q = pd.to_numeric(trades["notional_usd"], errors="coerce").abs()
    sig = pd.to_numeric(trades["sigma_d"], errors="coerce") * vol_mult
    disc = trades["categoria"].map(lambda c: float(discount.get(c, 1.0))).astype(float)
    impact = costs.impact_coefficient * sig * np.sqrt(q / adtv.where(adtv > 0)) * disc * BPS
    total = half + comm + fx + impact
    flags = trades.get("flag", pd.Series("", index=trades.index)).fillna("").astype(str)
    flags = flags.where(total.notna(), flags + ";custo_indisponivel")
    out = pd.DataFrame({"half_spread_bps": half, "commission_bps": comm, "fx_bps": fx,
                        "impact_bps": impact, "total_bps": total,
                        "cost_usd": (q * total / BPS), "flags": flags}, index=trades.index)
    return out
