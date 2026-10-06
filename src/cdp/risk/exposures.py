"""Exposições fatoriais por emissor (estilo Barra), calculadas sem look-ahead.

Fatores: ``market`` (1 para todos), dummies de país (``country:<XX>``) e de setor GICS
(``sector:<nome>``) e sete estilos padronizados (``beta``, ``size``, ``momentum``, ``resvol``,
``value``, ``liquidity``, ``fx_sens``).

Regras de dados (ver AGENTS.md e docs/cdp/ARQUITETURA.md):

- Toda exposição numa data usa apenas retornos, preços e volumes com data <= essa data.
- Capitalização histórica = capitalização atual × preço_usd(data) / preço_usd(último), isto é,
  número de ações constante (aproximação registrada como não point-in-time).
- ``value`` usa o P/B do retrato atual de fundamentos (NÃO point-in-time), levado ao passado
  com patrimônio por ação constante na moeda das demonstrações: ``B/P(t) = B/P(último) ×
  preço_usd(último)/preço_usd(t) × fx_fin(t)/fx_fin(último)`` — o câmbio usado em ``t`` é o de
  ``t`` (nunca o futuro) e só datas do painel são consideradas.
- Ausências nunca viram zero antes da padronização. Depois de padronizar (média ponderada por
  capitalização = 0), a exposição ausente recebe 0 — exatamente a média do corte transversal —
  e a quantidade de imputações é registrada em ``meta``.
- Países/setores com menos de ``min_names_per_sector`` emissores são agrupados em
  ``country:OTHER`` / ``sector:Other``: um fator com um único membro absorveria o risco
  específico desse nome e o faria parecer sem risco.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type

import numpy as np
import pandas as pd

from ..analytics.panel import AssetPanel, fx_for_lines
from ..config import FundConfig
from ..market import MarketData
from ..universe import GICS_SECTORS
from .types import (
    MARKET_FACTOR,
    STYLE_FACTORS,
    country_factor,
    sector_factor,
)

# Janelas (em pregões do calendário do painel) e mínimos de observações.
BETA_WINDOW = 252
BETA_MIN_OBS = 126
RESVOL_WINDOW = 126
RESVOL_MIN_OBS = 63
MOMENTUM_WINDOW = 252
MOMENTUM_SKIP = 21
MOMENTUM_MIN_OBS = 126
LIQUIDITY_MIN_OBS = 21
FX_WINDOW = 252
FX_MIN_OBS = 126

OTHER_COUNTRY = "OTHER"
OTHER_SECTOR = "Other"

# Moeda "de origem" por país para o fator ``fx_sens``. Panamá é dolarizado e emissores
# regionais (``LATAM``) não têm moeda dominante: nesses casos a sensibilidade é indefinida
# (NaN, imputada como 0 = média após a padronização, com contagem em ``meta``). Emissores
# listados em USD com país BR/MX usam BRL/MXN pela regra do país.
HOME_CURRENCY: dict[str, str | None] = {
    "BR": "BRL", "MX": "MXN", "CL": "CLP", "CO": "COP", "PE": "PEN", "AR": "ARS",
    "UY": "UYU", "PA": None, "LATAM": None,
}

NON_PIT_NOTES = {
    "value": (
        "value: P/B do retrato atual de fundamentos (não point-in-time); patrimônio por ação "
        "constante na moeda das demonstrações, convertido pelo câmbio de cada data e dividido "
        "pelo preço em USD da data"
    ),
    "size": (
        "size/capitalização histórica: ações em circulação atuais × preço histórico em USD "
        "(não point-in-time)"
    ),
}

_TINY = 1e-12


# ==========================================================
# Capitalização e pesos de mercado
# ==========================================================

def _as_timestamp(d: date_type | pd.Timestamp | str) -> pd.Timestamp:
    return pd.Timestamp(d)


def historical_mcap(panel: AssetPanel, issuers: list[str]) -> pd.DataFrame:
    """Capitalização em USD estimada por data (data × emissor).

    ``mcap(t) = market_cap_usd(atual) × price_usd(t) / price_usd(último)``, com o preço em USD
    propagado apenas para frente (último preço conhecido até ``t``). Emissor sem capitalização
    ou sem preço fica ``NaN`` (nunca zero).
    """
    px = panel.price_usd.reindex(columns=issuers).ffill()
    if px.empty:
        return px
    last = px.iloc[-1]
    mcap_now = pd.to_numeric(panel.assets["market_cap_usd"], errors="coerce").reindex(issuers)
    ratio = px.div(last.where(last > 0))
    return ratio.mul(mcap_now.where(mcap_now > 0), axis=1)


def market_weights(
    panel: AssetPanel,
    issuers: list[str],
    date: date_type | pd.Timestamp | None = None,
) -> pd.Series:
    """Pesos por capitalização (somam 1) sobre os emissores com capitalização e preço.

    Para ``date`` anterior ao ``as_of`` do painel a capitalização atual é escalada pela razão
    de preços em USD (último preço conhecido até ``date``). Emissores sem dado são excluídos
    do resultado (não recebem peso zero implícito).
    """
    issuers = list(dict.fromkeys(issuers))
    hist = historical_mcap(panel, issuers)
    if date is not None:
        hist = hist.loc[hist.index <= _as_timestamp(date)]
    if hist.empty:
        raise ValueError("Sem preços até a data pedida para calcular pesos de mercado.")
    mc = hist.iloc[-1]
    mc = mc[np.isfinite(mc) & (mc > 0)]
    if mc.empty:
        raise ValueError("Nenhum emissor com capitalização e preço para pesos de mercado.")
    return (mc / mc.sum()).rename("market_weight")


def market_return_series(panel: AssetPanel, issuers: list[str]) -> pd.Series:
    """Retorno diário em USD da carteira ponderada por capitalização dos ``issuers``.

    Pesos de ``t`` usam a capitalização estimada em ``t-1``; só entram emissores com retorno
    observado em ``t`` (pesos renormalizados). Dia sem nenhum emissor ⇒ ``NaN``.
    """
    rets = panel.returns.reindex(columns=issuers)
    w_prev = historical_mcap(panel, issuers).shift(1)
    valid = rets.notna() & w_prev.notna() & (w_prev > 0)
    num = (rets.where(valid) * w_prev.where(valid)).sum(axis=1, min_count=1)
    den = w_prev.where(valid).sum(axis=1, min_count=1)
    return (num / den).rename("market_return")


# ==========================================================
# Estrutura de país/setor (agrupamento de grupos pequenos)
# ==========================================================

@dataclass(frozen=True)
class FactorStructure:
    """Mapeamento emissor -> fator de país/setor, já com os agrupamentos de grupos pequenos."""

    country: pd.Series                 # emissor -> nome do fator de país (ou None)
    sector: pd.Series                  # emissor -> nome do fator de setor (ou None)
    country_factors: list[str]
    sector_factors: list[str]
    merged_countries: list[str] = field(default_factory=list)
    merged_sectors: list[str] = field(default_factory=list)
    unassigned_country: list[str] = field(default_factory=list)
    unassigned_sector: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def dummies(self, issuers: list[str]) -> pd.DataFrame:
        cols = self.country_factors + self.sector_factors
        out = pd.DataFrame(0.0, index=pd.Index(issuers, name="issuer_id"), columns=cols)
        for col_map in (self.country, self.sector):
            for iid, fac in col_map.reindex(issuers).items():
                if isinstance(fac, str) and fac in out.columns:
                    out.loc[iid, fac] = 1.0
        return out

    def meta(self) -> dict:
        return {
            "merged_countries": list(self.merged_countries),
            "merged_sectors": list(self.merged_sectors),
            "unassigned_country": list(self.unassigned_country),
            "unassigned_sector": list(self.unassigned_sector),
            "structure_notes": list(self.notes),
        }


def _clean_labels(raw: pd.Series) -> pd.Series:
    """Rótulos de país/setor como ``str``; ausente (NaN/None/vazio) continua ausente.

    Evita que ``astype(str)`` transforme ausências em um grupo ``"nan"`` com fator próprio.
    """
    s = raw.astype(object)
    ok = s.notna() & (s.astype(str).str.strip() != "")
    return s.where(ok).map(lambda v: str(v) if pd.notna(v) else None)


def _group_block(
    labels: pd.Series, min_names: int, other_label: str, make_name, order: list[str] | None,
    kind: str,
) -> tuple[pd.Series, list[str], list[str], list[str], list[str]]:
    labels = _clean_labels(labels)
    counts = labels.value_counts()
    small = sorted(counts.index[counts < min_names].tolist())
    merged = labels.where(~labels.isin(small), other_label).where(labels.notna(), None)
    notes: list[str] = []
    unassigned: list[str] = sorted(labels.index[labels.isna()].tolist())
    if unassigned:
        notes.append(f"{kind}: {len(unassigned)} emissor(es) sem rótulo; sem fator de {kind}")
    n_other = int((merged == other_label).sum())
    if small and n_other < min_names:
        # Mesmo agrupados, os pequenos não formam um fator com membros suficientes:
        # ficam sem fator do bloco (efeito vai para o resíduo), com flag.
        unassigned = sorted(set(unassigned) | set(merged.index[merged == other_label]))
        merged = merged.where(merged != other_label, None)
        notes.append(
            f"{kind}: grupo agrupado com {n_other} emissor(es) < {min_names}; "
            "emissores sem fator de " + kind
        )
    rank = {g: k for k, g in enumerate(order or [])}
    groups = sorted(merged.dropna().unique().tolist(),
                    key=lambda g: (g == other_label, rank.get(g, len(rank)), g))
    if len(groups) == 1:
        # Bloco com um único grupo é colinear com o mercado: descartado.
        notes.append(f"{kind}: apenas um grupo ({groups[0]}); bloco colinear com mercado removido")
        unassigned = sorted(set(unassigned) | set(merged.dropna().index))
        merged = merged.where(merged.isna(), None)
        groups = []
    names = {g: make_name(g) for g in groups}
    mapped = merged.map(lambda g: names.get(g) if isinstance(g, str) else None)
    return mapped, [names[g] for g in groups], small, unassigned, notes


def factor_structure(panel: AssetPanel, issuers: list[str], min_names: int,
                     min_names_country: int | None = None) -> FactorStructure:
    """Define os fatores de país e setor para ``issuers`` agrupando grupos pequenos.

    ``min_names_country`` (``risk_model.min_names_per_country``): mínimo próprio para países;
    ``None`` = o mesmo de setores (``min_names``)."""
    missing = sorted(set(issuers) - set(panel.assets.index))
    if missing:
        raise KeyError(f"Emissores fora do painel: {missing}")
    assets = panel.assets.loc[issuers]
    c_map, c_fac, c_merged, c_un, c_notes = _group_block(
        assets["country"], min_names if min_names_country is None else int(min_names_country),
        OTHER_COUNTRY, country_factor, None, "país")
    s_map, s_fac, s_merged, s_un, s_notes = _group_block(
        assets["sector"], min_names, OTHER_SECTOR, sector_factor, GICS_SECTORS, "setor")
    # Fator de setor com exatamente os mesmos membros de um fator de país é colinear com ele
    # (regressão sem posto completo): o setor é removido e os membros ficam sem fator setorial.
    c_sets = {frozenset(c_map.index[c_map == f]) for f in c_fac}
    for f in list(s_fac):
        members = frozenset(s_map.index[s_map == f])
        if members in c_sets:
            s_fac.remove(f)
            s_map = s_map.where(s_map != f, None)
            s_un = sorted(set(s_un) | set(members))
            s_notes.append(f"setor: {f} tem os mesmos membros de um fator de país; removido")
    return FactorStructure(
        country=c_map, sector=s_map, country_factors=c_fac, sector_factors=s_fac,
        merged_countries=c_merged, merged_sectors=s_merged,
        unassigned_country=c_un, unassigned_sector=s_un, notes=c_notes + s_notes,
    )


# ==========================================================
# Insumos de estilo (pré-computados uma vez, todos causais)
# ==========================================================

def _fx_on_panel_dates(md: MarketData, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Câmbio (USD por unidade) no calendário do painel, propagado só para frente (causal).

    Usa apenas datas do painel: um ``MarketData`` mais longo que o painel não vaza câmbio
    futuro para as exposições.
    """
    fx = fx_for_lines(md)
    return fx.reindex(fx.index.union(dates)).sort_index().ffill().reindex(dates)


def _adr_ratio(own: pd.DataFrame, tkr: str) -> float:
    if "adr_ratio" not in own.columns or tkr not in own.index:
        return np.nan
    return float(pd.to_numeric(pd.Series([own.loc[tkr, "adr_ratio"]]), errors="coerce").iloc[0])


def _book_to_price_last(
    panel: AssetPanel, md: MarketData | None, issuers: list[str],
    fx_last: pd.Series | None = None,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """B/P em USD na última data do painel a partir do P/B do retrato atual de fundamentos.

    Retorna (B/P, fonte, moeda das demonstrações) por emissor. Preferência:
    (1) linha cuja moeda de cotação = moeda das demonstrações (P/B consistente);
    (2) linha não-ADR com moedas diferentes, corrigida pelo câmbio da última data do painel;
    (3) linha local com moeda das demonstrações desconhecida (assume a moeda da linha).
    ADR só é usado com moeda igual à das demonstrações E razão 1: com razão ≠ 1 o P/B do
    fornecedor pode dividir o preço por ADR pelo patrimônio por ação (erro de unidade de até
    ``adr_ratio`` vezes). Sem fonte ⇒ ``NaN``.
    """
    bp = pd.Series(np.nan, index=issuers, dtype=float)
    src = pd.Series("sem_dado", index=issuers, dtype=object)
    fin_ccy = pd.Series(None, index=issuers, dtype=object)
    if md is None:
        return bp, pd.Series("sem_marketdata", index=issuers, dtype=object), fin_ccy
    if md.fundamentals is None or md.fundamentals.empty:
        return bp, pd.Series("sem_fundamentos", index=issuers, dtype=object), fin_ccy
    fund = md.fundamentals
    if "price_to_book" not in fund.columns:
        return bp, pd.Series("sem_price_to_book", index=issuers, dtype=object), fin_ccy
    if fx_last is None:
        fx_all = _fx_on_panel_dates(md, pd.DatetimeIndex(panel.returns.index))
        fx_last = fx_all.iloc[-1] if len(fx_all) else pd.Series(dtype=float)
    lines = panel.lines
    for iid in issuers:
        own = lines[lines["issuer_id"] == iid] if "issuer_id" in lines.columns else lines.iloc[:0]
        prim = panel.assets.loc[iid].get("primary_ticker") if iid in panel.assets.index else None
        order = ([prim] if isinstance(prim, str) else []) + [t for t in own.index if t != prim]
        best: tuple[int, float, str, str] | None = None
        for tkr in order:
            if tkr not in fund.index:
                continue
            row = fund.loc[tkr]
            pb = pd.to_numeric(pd.Series([row.get("price_to_book")]), errors="coerce").iloc[0]
            if not (np.isfinite(pb) and pb > 0):
                continue
            ccy = row.get("currency")
            if not isinstance(ccy, str) and tkr in own.index:
                ccy = own.loc[tkr, "currency"]
            fin = row.get("financial_currency")
            line_type = own.loc[tkr, "line_type"] if tkr in own.index else None
            if line_type == "ADR" and not (isinstance(fin, str) and fin == ccy
                                           and _adr_ratio(own, tkr) == 1.0):
                continue
            if isinstance(fin, str) and fin == ccy:
                cand = (0, 1.0 / pb, "linha_mesma_moeda", fin)
            elif (isinstance(fin, str) and isinstance(ccy, str)
                  and np.isfinite(fx_last.get(fin, np.nan))
                  and np.isfinite(fx_last.get(ccy, np.nan)) and fx_last.get(ccy) > 0):
                cand = (1, (1.0 / pb) * float(fx_last[fin]) / float(fx_last[ccy]),
                        "corrigido_cambio", fin)
            elif not isinstance(fin, str) and line_type == "LOCAL" and isinstance(ccy, str):
                cand = (2, 1.0 / pb, "local_moeda_fin_desconhecida", ccy)
            else:
                continue
            if best is None or cand[0] < best[0]:
                best = cand
            if best[0] == 0:
                break
        if best is not None:
            bp[iid], src[iid], fin_ccy[iid] = best[1], best[2], best[3]
    return bp, src, fin_ccy


def _book_fx_ratio(
    fx: pd.DataFrame | None, fin_ccy: pd.Series, dates: pd.DatetimeIndex,
) -> np.ndarray:
    """``fx_fin(t) / fx_fin(último)`` (T × N): leva o patrimônio em USD de hoje à data ``t``.

    O patrimônio por ação é constante na moeda das demonstrações (aproximação não-PIT); o seu
    valor em USD em ``t`` usa o câmbio de ``t`` (nunca o futuro). Moeda desconhecida ⇒ ``NaN``.
    """
    out = np.full((len(dates), len(fin_ccy)), np.nan)
    if fx is None or fx.empty:
        return out
    for j, ccy in enumerate(fin_ccy.to_numpy()):
        if not isinstance(ccy, str):
            continue
        if ccy == "USD":
            out[:, j] = 1.0
        elif ccy in fx.columns:
            s = fx[ccy].to_numpy(dtype=float)
            last = s[-1]
            if np.isfinite(last) and last > 0:
                out[:, j] = np.where(np.isfinite(s) & (s > 0), s / last, np.nan)
    return out


@dataclass(frozen=True)
class StyleInputs:
    """Matrizes alinhadas ao calendário do painel usadas para calcular estilos em qualquer data.

    Todas as séries são causais (o valor em ``t`` depende só de dados <= ``t``), exceto a
    aproximação de ações em circulação/valor patrimonial atuais (não point-in-time, ver meta).
    """

    dates: pd.DatetimeIndex
    issuers: list[str]
    returns: np.ndarray        # T × N, retorno total diário em USD (NaN = sem negociação)
    market: np.ndarray         # T, retorno da carteira ponderada por capitalização
    mcap: np.ndarray           # T × N, capitalização histórica estimada em USD
    price: np.ndarray          # T × N, preço em USD propagado para frente
    price_last: np.ndarray     # N, último preço em USD do painel
    adtv: np.ndarray           # T × N, média móvel do valor negociado em USD
    fx_returns: np.ndarray     # T × N, retorno em USD da moeda de origem (NaN se indefinida)
    book_to_price_last: np.ndarray  # N, B/P em USD na última data do painel
    book_fx_ratio: np.ndarray  # T × N, fx_moeda_demonstrações(t) / fx(último)
    home_currency: dict[str, str | None]
    value_source: dict[str, str]
    available_styles: list[str]
    flags: dict = field(default_factory=dict)

    def position(self, d: date_type | pd.Timestamp) -> int:
        """Índice do último pregão <= ``d`` (erro se ``d`` é anterior ao início)."""
        pos = int(self.dates.searchsorted(_as_timestamp(d), side="right")) - 1
        if pos < 0:
            raise ValueError(f"Data {d} anterior ao início do painel ({self.dates[0].date()}).")
        return pos

    def cap_weights(self, pos: int) -> np.ndarray:
        mc = self.mcap[pos]
        ok = np.isfinite(mc) & (mc > 0)
        w = np.where(ok, mc, np.nan)
        tot = np.nansum(w)
        return w / tot if tot > 0 else w

    def raw_styles(self, pos: int) -> pd.DataFrame:
        """Estilos brutos (não padronizados) na posição ``pos`` usando dados <= ``pos``."""
        n = len(self.issuers)
        out = {s: np.full(n, np.nan) for s in STYLE_FACTORS}
        beta, alpha = _rolling_beta(self.returns, self.market, pos)
        out["beta"] = beta
        out["resvol"] = _resvol(self.returns, self.market, pos, beta, alpha)
        out["momentum"] = _momentum(self.returns, pos)
        mc = self.mcap[pos]
        with np.errstate(divide="ignore", invalid="ignore"):
            out["size"] = np.where(np.isfinite(mc) & (mc > 0), np.log(mc), np.nan)
            px = self.price[pos]
            ok_px = np.isfinite(px) & (px > 0)
            # B/P(t) = patrimônio_fin × fx_fin(t) / preço_usd(t) (patrimônio constante, não-PIT).
            out["value"] = np.where(
                ok_px, self.book_to_price_last * self.price_last / px * self.book_fx_ratio[pos],
                np.nan)
            liq_ok = np.isfinite(self.adtv[pos]) & (self.adtv[pos] > 0) & np.isfinite(mc) & (mc > 0)
            out["liquidity"] = np.where(liq_ok, np.log(self.adtv[pos] / mc), np.nan)
        out["fx_sens"] = _fx_sensitivity(self.returns, self.market, self.fx_returns, pos)
        for s in STYLE_FACTORS:
            if s not in self.available_styles:
                out[s] = np.full(n, np.nan)
        return pd.DataFrame(out, index=pd.Index(self.issuers, name="issuer_id"))[STYLE_FACTORS]


def _window(pos: int, length: int) -> slice:
    return slice(max(0, pos - length + 1), pos + 1)


def _centered_moments(y: np.ndarray, m: np.ndarray, mask: np.ndarray):
    n = mask.sum(axis=0).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        mm = np.where(mask, m[:, None], 0.0)
        yy = np.where(mask, y, 0.0)
        mean_m = mm.sum(axis=0) / n
        mean_y = yy.sum(axis=0) / n
        dm = np.where(mask, m[:, None] - mean_m, 0.0)
        dy = np.where(mask, y - mean_y, 0.0)
    return n, mean_m, mean_y, dm, dy


def _rolling_beta(rets: np.ndarray, mkt: np.ndarray, pos: int) -> tuple[np.ndarray, np.ndarray]:
    sl = _window(pos, BETA_WINDOW)
    y, m = rets[sl], mkt[sl]
    mask = np.isfinite(y) & np.isfinite(m)[:, None]
    n, mean_m, mean_y, dm, dy = _centered_moments(y, m, mask)
    with np.errstate(invalid="ignore", divide="ignore"):
        smm = (dm * dm).sum(axis=0)
        beta = (dm * dy).sum(axis=0) / smm
        alpha = mean_y - beta * mean_m
    bad = (n < BETA_MIN_OBS) | ~(smm > _TINY)
    beta = np.where(bad, np.nan, beta)
    alpha = np.where(bad, np.nan, alpha)
    return beta, alpha


def _resvol(rets: np.ndarray, mkt: np.ndarray, pos: int, beta: np.ndarray,
            alpha: np.ndarray) -> np.ndarray:
    sl = _window(pos, RESVOL_WINDOW)
    y, m = rets[sl], mkt[sl]
    mask = np.isfinite(y) & np.isfinite(m)[:, None] & np.isfinite(beta)[None, :]
    n = mask.sum(axis=0).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        e = np.where(mask, y - alpha[None, :] - beta[None, :] * m[:, None], 0.0)
        mean_e = e.sum(axis=0) / n
        ss = np.where(mask, (e - mean_e) ** 2, 0.0).sum(axis=0)
        sd = np.sqrt(ss / (n - 1.0))
    return np.where(n >= RESVOL_MIN_OBS, sd, np.nan)


def _momentum(rets: np.ndarray, pos: int) -> np.ndarray:
    end = pos - MOMENTUM_SKIP  # inclusivo: exclui o último mês
    start = pos - MOMENTUM_WINDOW + 1
    n_iss = rets.shape[1]
    if end < 0 or start < 0:
        return np.full(n_iss, np.nan)
    y = rets[start:end + 1]
    mask = np.isfinite(y)
    logs = np.where(mask, np.log1p(np.maximum(np.where(mask, y, 0.0), -0.999999)), 0.0)
    cum = np.expm1(logs.sum(axis=0))
    return np.where(mask.sum(axis=0) >= MOMENTUM_MIN_OBS, cum, np.nan)


def _fx_sensitivity(rets: np.ndarray, mkt: np.ndarray, fx: np.ndarray, pos: int) -> np.ndarray:
    """Coeficiente de ``r_i ~ a + b·mercado + c·câmbio_i`` (252d), retorna ``c``."""
    sl = _window(pos, FX_WINDOW)
    y, m, x = rets[sl], mkt[sl], fx[sl]
    mask = np.isfinite(y) & np.isfinite(m)[:, None] & np.isfinite(x)
    n = mask.sum(axis=0).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        mm = np.where(mask, m[:, None], 0.0)
        xx = np.where(mask, x, 0.0)
        yy = np.where(mask, y, 0.0)
        dm = np.where(mask, mm - mm.sum(axis=0) / n, 0.0)
        dx = np.where(mask, xx - xx.sum(axis=0) / n, 0.0)
        dy = np.where(mask, yy - yy.sum(axis=0) / n, 0.0)
        smm = (dm * dm).sum(axis=0)
        sxx = (dx * dx).sum(axis=0)
        smx = (dm * dx).sum(axis=0)
        smy = (dm * dy).sum(axis=0)
        sxy = (dx * dy).sum(axis=0)
        det = smm * sxx - smx * smx
        coef = (smm * sxy - smx * smy) / det
    ok = (n >= FX_MIN_OBS) & (det > 1e-10 * smm * sxx) & (sxx > _TINY)
    return np.where(ok, coef, np.nan)


def prepare_style_inputs(
    panel: AssetPanel, md: MarketData | None, cfg: FundConfig, issuers: list[str],
) -> StyleInputs:
    """Pré-computa, uma única vez, as séries causais necessárias aos estilos."""
    issuers = list(dict.fromkeys(issuers))
    missing = sorted(set(issuers) - set(panel.assets.index))
    if missing:
        raise KeyError(f"Emissores fora do painel: {missing}")
    dates = pd.DatetimeIndex(panel.returns.index)
    rets = panel.returns.reindex(columns=issuers)
    mcap = historical_mcap(panel, issuers).reindex(dates)
    price = panel.price_usd.reindex(columns=issuers).ffill().reindex(dates)
    price_last = price.iloc[-1].to_numpy(dtype=float) if len(price) else np.full(
        len(issuers), np.nan)
    mkt = market_return_series(panel, issuers).reindex(dates)
    win = cfg.liquidity.adv_window_days
    tv = panel.traded_value_usd.reindex(columns=issuers).reindex(dates)
    adtv = tv.rolling(win, min_periods=LIQUIDITY_MIN_OBS).mean()

    flags: dict = {}
    home: dict[str, str | None] = {}
    fx_ret = pd.DataFrame(np.nan, index=dates, columns=issuers)
    available = ["beta", "size", "momentum", "resvol", "liquidity"]
    fx_ffill: pd.DataFrame | None = None
    if md is not None and md.fx is not None and not md.fx.empty:
        fx = fx_for_lines(md).reindex(dates)
        fx_ffill = _fx_on_panel_dates(md, dates)
        fx_r = fx.pct_change(fill_method=None)
        for iid in issuers:
            ccy = HOME_CURRENCY.get(str(panel.assets.loc[iid, "country"]))
            home[iid] = ccy
            if ccy is not None and ccy in fx_r.columns:
                fx_ret[iid] = fx_r[ccy]
        available.append("fx_sens")
        no_home = sorted(i for i in issuers if home.get(i) is None
                         or home.get(i) not in fx_r.columns)
        if no_home:
            flags["fx_sens_sem_moeda_de_origem"] = no_home
    else:
        home = {i: None for i in issuers}
        flags["fx_sens"] = "sem MarketData/câmbio: estilo indisponível"

    fx_last = (fx_ffill.iloc[-1] if fx_ffill is not None and len(fx_ffill)
               else pd.Series(dtype=float))
    bp, src, fin_ccy = _book_to_price_last(panel, md, issuers, fx_last)
    book_fx = _book_fx_ratio(fx_ffill, fin_ccy, dates)
    last_ratio = book_fx[-1] if len(dates) else np.full(len(issuers), np.nan)
    has_bp = np.isfinite(bp.to_numpy())
    no_fx = [i for i, b, r in zip(issuers, has_bp, np.isfinite(last_ratio), strict=True)
             if b and not r]
    if no_fx:
        flags["value_sem_cambio_moeda_demonstracoes"] = no_fx
    if (has_bp & np.isfinite(last_ratio)).any():
        available.append("value")
    else:
        flags["value"] = "sem P/B utilizável: estilo indisponível"
    available = [s for s in STYLE_FACTORS if s in available]
    return StyleInputs(
        dates=dates, issuers=issuers, returns=rets.to_numpy(dtype=float),
        market=mkt.to_numpy(dtype=float), mcap=mcap.to_numpy(dtype=float),
        price=price.to_numpy(dtype=float), price_last=price_last,
        adtv=adtv.to_numpy(dtype=float), fx_returns=fx_ret.to_numpy(dtype=float),
        book_to_price_last=bp.to_numpy(dtype=float), book_fx_ratio=book_fx,
        home_currency=home,
        value_source={k: str(v) for k, v in src.items()}, available_styles=available,
        flags=flags,
    )


# ==========================================================
# Padronização
# ==========================================================

def standardize_style(raw: np.ndarray, cap_w: np.ndarray, winsor_z: float) -> np.ndarray:
    """z robusto (mediana/MAD) → winsor ±``winsor_z`` → média ponderada por cap 0 → desvio 1.

    Retorna ``NaN`` onde o bruto é ``NaN``; se não houver dispersão no corte transversal,
    devolve tudo ``NaN`` (estilo não informativo nesta data).
    """
    x = np.asarray(raw, dtype=float)
    ok = np.isfinite(x)
    out = np.full_like(x, np.nan)
    if ok.sum() < 2:
        return out
    xo = x[ok]
    med = np.median(xo)
    scale = 1.4826 * np.median(np.abs(xo - med))
    if not scale > _TINY:
        scale = float(np.std(xo))
    if not scale > _TINY:
        return out
    z = np.clip((x - med) / scale, -winsor_z, winsor_z)
    cw = np.where(ok & np.isfinite(cap_w) & (cap_w > 0), cap_w, 0.0)
    if cw.sum() > 0:
        z = z - np.nansum(np.where(ok, z, 0.0) * cw) / cw.sum()
    else:
        z = z - np.nanmean(z[ok])
    sd = float(np.std(z[ok]))
    if sd > _TINY:
        z = z / sd
    out[ok] = z[ok]
    return out


def standardized_styles(
    inputs: StyleInputs, pos: int, winsor_z: float,
) -> tuple[pd.DataFrame, dict]:
    """Estilos padronizados na posição ``pos`` com imputação (ausente ⇒ 0) e contagens."""
    raw = inputs.raw_styles(pos)
    cap_w = inputs.cap_weights(pos)
    active = np.isfinite(inputs.price[pos])
    std = pd.DataFrame(index=raw.index, columns=raw.columns, dtype=float)
    imputations: dict[str, int] = {}
    for s in raw.columns:
        z = standardize_style(np.where(active, raw[s].to_numpy(), np.nan), cap_w, winsor_z)
        miss = ~np.isfinite(z)
        imputations[s] = int((miss & active).sum())
        std[s] = np.where(miss, 0.0, z)
    meta = {
        "date": str(inputs.dates[pos].date()),
        "style_imputations": imputations,
        "n_active": int(active.sum()),
        "available_styles": list(inputs.available_styles),
        "imputation_rule": "exposição ausente = 0 (média ponderada por cap após padronização)",
    }
    return std, meta


def style_exposures(
    panel: AssetPanel,
    md: MarketData | None,
    cfg: FundConfig,
    date: date_type | pd.Timestamp,
    issuers: list[str],
) -> pd.DataFrame:
    """Matriz emissor × 7 estilos padronizados usando somente dados <= ``date``.

    ``attrs['meta']`` traz imputações por estilo, fonte do ``value`` e flags não-PIT.
    """
    inputs = prepare_style_inputs(panel, md, cfg, issuers)
    pos = inputs.position(date)
    std, meta = standardized_styles(inputs, pos, cfg.alpha.winsor_z)
    meta["value_source"] = dict(inputs.value_source)
    meta["flags"] = dict(inputs.flags)
    meta["non_point_in_time"] = [NON_PIT_NOTES["size"]] + (
        [NON_PIT_NOTES["value"]] if "value" in inputs.available_styles else [])
    std.attrs["meta"] = meta
    return std


def build_exposure_matrix(
    structure: FactorStructure, styles: pd.DataFrame, style_names: list[str],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Junta mercado (1), dummies de país/setor e estilos na ordem canônica dos fatores."""
    issuers = list(styles.index)
    dummies = structure.dummies(issuers)
    X = pd.concat(
        [pd.DataFrame({MARKET_FACTOR: 1.0}, index=dummies.index), dummies,
         styles[style_names].set_axis(dummies.index)],
        axis=1,
    )
    groups: dict[str, str] = {MARKET_FACTOR: "market"}
    groups.update({f: "country" for f in structure.country_factors})
    groups.update({f: "sector" for f in structure.sector_factors})
    groups.update({s: "style" for s in style_names})
    return X.astype(float), groups


def exposure_matrix(
    panel: AssetPanel,
    md: MarketData | None,
    cfg: FundConfig,
    date: date_type | pd.Timestamp,
    issuers: list[str],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Matriz B (emissor × fator) e grupos de fatores (market|country|sector|style).

    Estilos sem nenhuma fonte de dados (ex.: ``value``/``fx_sens`` sem ``MarketData``) são
    omitidos e listados em ``attrs['meta']['dropped_styles']``.
    """
    structure = factor_structure(panel, list(issuers), cfg.risk_model.min_names_per_sector,
                                 cfg.risk_model.min_names_per_country)
    styles = style_exposures(panel, md, cfg, date, list(issuers))
    meta = dict(styles.attrs.get("meta", {}))
    names = [s for s in STYLE_FACTORS if s in meta.get("available_styles", STYLE_FACTORS)]
    X, groups = build_exposure_matrix(structure, styles, names)
    meta.update(structure.meta())
    meta["dropped_styles"] = [s for s in STYLE_FACTORS if s not in names]
    X.attrs["meta"] = meta
    return X, groups
