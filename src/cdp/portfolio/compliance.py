"""Checagens de compliance pré-aprovação da carteira proposta.

Severidades (``contracts.Severity``):
- ``HARD``: bloqueia a aprovação (proposta ``BLOCKED``).
- ``SOFT``: exige ciência explícita do gestor na decisão.
- ``INFO``: apenas informativo.

Todas as checagens têm ``value`` (medido), ``limit`` e ``details`` em português. A tolerância
``TOL`` = 1e-6 absorve ruído numérico do solver. Dados ausentes nunca viram zero: um nome com
ADTV da linha ausente reprova a checagem de liquidez (o ADTV agregado do emissor só é usado
quando a tabela de restrições não traz a coluna da linha, e isso é dito no detalhe); aluguel
ausente reprova a checagem de aluguel.

Liquidez: longs a ``participation_rate``; shorts a ``short_participation_rate`` (mandato).
Drawdown: no stop duro o gross precisa cair a ``degross_multiplier`` × gross atual — ou o risco
já estar cortado (vol ex-ante ≤ ``degross_multiplier`` × meta), para não exigir um novo corte a
cada semana enquanto o drawdown persistir; no ``stop_out`` o gross não pode exceder
``stop_out_gross``. Com ``drawdown.risk_reference = "normal_book_vol"`` (``drawdown_ref_vol``
informado) a escada vale sobre a vol ex-ante: ``vol ≤ m(estágio)·σ_ref``.

Construção com limites operacionais (``risk.operational``): os limites do mandato são HARD
(inclusive estilos); os operacionais, mais apertados, são SOFT (``*_OP``). Sensibilidade a
commodities fica SOFT enquanto os betas vierem de regressões por nome sem encolhimento.
Fatia idiossincrática (κ_F na parte fatorial): meta SOFT (``IDIO_SHARE``) e piso HARD
(``IDIO_FLOOR``) em cada modelo de ``risk.idio_gate_models``. Vetos de short novo
(``SHORT_ENTRY_BLOCK``, HARD), capacidade de fechamento (``TRADE_CLOSE_CAPACITY``, SOFT),
emissores congelados (INFO) e grupos de controle (``LINKED_GROUP``, SOFT).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..config import FundConfig
from ..contracts import ComplianceCheck, Severity
from ..risk.types import STYLE_FACTORS, RiskModel
from .optimizer import (
    UNKNOWN_GROUP,
    model_implied_betas,
    normalize_squeeze_bucket,
    portfolio_risk_parts,
)

TOL = 1e-6
MAX_STALENESS_DAYS = 4
#: Tolerância relativa (variância) do "sem risco fatorial novo" numa decisão só de redução
#: (absorve a tolerância de viabilidade do solver).
REDUCE_ONLY_FACTOR_TOL = 2.5e-3   # ≈ (1 + folga de 0,1% na norma do otimizador)² − 1
VOL_TARGET_INFO_BAND = 0.01  # |vol − meta| ≤ 1 p.p. é considerado "na meta" (informativo)
MAX_LISTED = 8


def _fmt_pct(x: float) -> str:
    return f"{x:.2%}"


def _offenders(values: pd.Series, fmt=_fmt_pct) -> str:
    vals = values.sort_values(key=lambda s: -s.abs())
    items = [f"{i} ({fmt(v)})" if np.isfinite(v) else f"{i} (sem dado)"
             for i, v in vals.head(MAX_LISTED).items()]
    more = len(vals) - MAX_LISTED
    return ", ".join(items) + (f" e mais {more}" if more > 0 else "")


def _check(check_id: str, name: str, passed: bool, severity: Severity,
           value: float | None, limit: float | None, details: str) -> ComplianceCheck:
    v = None if value is None or not np.isfinite(value) else float(value)
    lim = None if limit is None or not np.isfinite(limit) else float(limit)
    return ComplianceCheck(check_id=check_id, name=name, passed=bool(passed), severity=severity,
                           value=v, limit=lim, details=details)


def _lookup(col: str, ids: pd.Index, *frames: pd.DataFrame | None) -> pd.Series:
    """Primeiro valor não ausente de ``col`` entre as tabelas, na ordem dada."""
    out = pd.Series(np.nan, index=ids, dtype=object)
    for df in frames:
        if df is None or col not in df.columns:
            continue
        out = out.where(out.notna(), df[col].reindex(ids))
    return out


def _bool_col(df: pd.DataFrame | None, col: str, ids: pd.Index) -> pd.Series:
    """Coluna booleana; ``None`` quando a tabela não tem a coluna (ausência explícita)."""
    if df is None or col not in df.columns:
        return pd.Series([None] * len(ids), index=ids, dtype=object)
    raw = df[col].reindex(ids)
    return raw.map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v))
                   else bool(v))


def _resolve_betas(ids: pd.Index, constraints: pd.DataFrame, model: RiskModel,
                   market_w: pd.Series | None) -> tuple[pd.Series, str]:
    beta = pd.to_numeric(_lookup("beta", ids, constraints), errors="coerce")
    note = ""
    if beta.isna().any() and market_w is not None:
        try:
            implied = model_implied_betas(model, market_w).reindex(ids)
            n_fill = int((beta.isna() & implied.notna()).sum())
            beta = beta.fillna(implied)
            if n_fill:
                note += f" Beta implícito do modelo usado para {n_fill} nomes."
        except ValueError as exc:
            note += f" Beta implícito indisponível ({exc})."
    if beta.isna().any():
        note += f" Beta ausente imputado em 1,0 para {int(beta.isna().sum())} nomes."
        beta = beta.fillna(1.0)
    return beta, note


def _op_country_groups(country: pd.Series, op, mandate: float
                       ) -> list[tuple[str, list[str], float]]:
    """Grupos de país do painel (os mesmos do limite do mandato) com o limite operacional do
    país ou o de ``"*"`` para os não listados — inclusive países sem fator próprio no modelo
    de risco — nunca acima do mandato."""
    out: list[tuple[str, list[str], float]] = []
    for code in sorted(set(country.dropna())):
        members = [str(i) for i in country.index[country == code]]
        lim = op.country_net_limit(str(code))
        if members and lim is not None:
            out.append((str(code), members, min(float(lim), mandate)))
    return out


def _idio_share(w: pd.Series, model: RiskModel | None, kappa: float) -> float | None:
    """Fatia idiossincrática com κ_F no bloco fatorial; ``None`` sem posições ou sem modelo."""
    if model is None or w.empty:
        return None
    try:
        parts = portfolio_risk_parts(w, model)
    except (ValueError, KeyError):
        return float("nan")
    tot = kappa * parts.factor_var + parts.specific_var
    return parts.specific_var / tot if tot > 0 else None


def _factor_var(w: pd.Series, model: RiskModel | None) -> float | None:
    """Variância fatorial ex-ante (sem κ_F) da carteira; ``None`` se não calculável."""
    if model is None:
        return None
    w = w[w != 0]
    w.index = w.index.map(str)
    try:
        return float(portfolio_risk_parts(w, model).factor_var)
    except (ValueError, KeyError):
        return None


def passive_checks(checks: list[ComplianceCheck]) -> list[ComplianceCheck]:
    """Checagens reprovadas de uma carteira MANTIDA (sem negociação) como INFO ``PASSIVO:``:
    ficam visíveis sem bloquear a decisão de manter (que não cria a violação)."""
    out = []
    for c in checks:
        if c.passed or c.severity == Severity.INFO:
            continue
        out.append(c.model_copy(update={
            "check_id": f"PASSIVO:{c.check_id}", "severity": Severity.INFO,
            "name": f"{c.name} (carteira mantida)",
            "details": f"Violação passiva ({c.severity.value}) na carteira mantida: {c.details}"}))
    return out


def run_compliance(
    weights: pd.Series, model: RiskModel, constraints: pd.DataFrame,
    squeeze: pd.DataFrame | None, panel_assets: pd.DataFrame, cfg: FundConfig, nav: float,
    current: pd.Series | None, inception: bool, snapshot_as_of: date, week: date,
    market_w: pd.Series | None, is_synthetic: bool, drawdown: float | None = None,
    vol_target: float | None = None, *, model_base: RiskModel | None = None,
    kappa_f: float | None = None, drawdown_ref_vol: float | None = None,
    reduce_only: bool = False,
) -> list[ComplianceCheck]:
    """Executa todas as checagens e devolve a lista em ordem estável.

    ``vol_target``: meta efetiva da semana (override do gestor dentro da banda); padrão = config.
    ``drawdown``: drawdown corrente do fundo (aceita 0,04 ou −0,04 para 4%).
    ``model_base``: modelo sem janelas de evento (gate ``base``); ``kappa_f``: inflação de 2ª
    ordem do bloco fatorial (padrão: configuração); ``drawdown_ref_vol``: σ_ref da escada de
    drawdown por volatilidade; ``reduce_only``: decisão só de redução (kill switch) — o piso
    idiossincrático bloqueia risco fatorial NOVO: abaixo do piso, passa se a variância fatorial
    não aumenta em relação à carteira atual (cortar posições nunca é bloqueado por um piso que
    a carteira atual já não cumpre).
    """
    rk, liq, sh, sq = cfg.risk, cfg.liquidity, cfg.shorting, cfg.squeeze
    checks: list[ComplianceCheck] = []
    HARD, SOFT, INFO = Severity.HARD, Severity.SOFT, Severity.INFO
    from .optimizer import metodologia_ativa

    extended = metodologia_ativa(cfg)
    op = rk.operational
    kappa = max(float(kappa_f if kappa_f is not None else rk.second_order_inflation), 1.0)

    # ---------- validade dos pesos ----------
    raw = pd.to_numeric(weights, errors="coerce").copy()
    raw.index = raw.index.map(str)
    bad = raw[~np.isfinite(raw.to_numpy(dtype=float))]
    checks.append(_check(
        "WEIGHTS_VALID", "Pesos numéricos válidos", bad.empty, HARD, float(len(bad)), 0.0,
        "Todos os pesos são finitos." if bad.empty else
        f"Pesos ausentes/não finitos (excluídos das demais métricas): {', '.join(bad.index)}."))
    w = raw[np.isfinite(raw.to_numpy(dtype=float))]
    w = w[w != 0]
    cons = constraints.copy()
    cons.index = cons.index.map(str)
    ids = w.index
    longs = w[w > 0]
    shorts = w[w < 0]

    # ---------- exposições agregadas ----------
    net = float(w.sum())
    gross = float(w.abs().sum())
    checks.append(_check(
        "NET_EXPOSURE", "Exposição líquida (net neutral)",
        abs(net) <= rk.net_exposure_max_abs + TOL, HARD, net, rk.net_exposure_max_abs,
        f"Net {_fmt_pct(net)} do NAV (limite ±{_fmt_pct(rk.net_exposure_max_abs)}); "
        f"long {_fmt_pct(float(longs.sum()))}, short {_fmt_pct(float(shorts.sum()))}."))
    checks.append(_check(
        "GROSS_MAX", "Exposição bruta máxima", gross <= rk.gross_max + TOL, HARD, gross,
        rk.gross_max, f"Gross {gross:.2f}x do NAV (máximo {rk.gross_max:.2f}x)."))
    checks.append(_check(
        "GROSS_MIN", "Exposição bruta mínima", gross >= rk.gross_min - TOL, SOFT, gross,
        rk.gross_min, f"Gross {gross:.2f}x do NAV (mínimo recomendado {rk.gross_min:.2f}x)."
        + ("" if gross >= rk.gross_min - TOL else " Carteira subutiliza o orçamento de risco.")))

    beta, beta_note = _resolve_betas(ids, cons, model, market_w)
    port_beta = float((beta * w).sum())
    checks.append(_check(
        "BETA", "Beta previsto da carteira", abs(port_beta) <= rk.beta_max_abs + TOL, HARD,
        port_beta, rk.beta_max_abs,
        f"Beta previsto {port_beta:+.3f} (limite ±{rk.beta_max_abs:.3f}).{beta_note}"))
    if op is not None:
        b_op = min(op.beta, rk.beta_max_abs)
        checks.append(_check(
            "BETA_OP", "Beta previsto (limite operacional)", abs(port_beta) <= b_op + TOL, SOFT,
            port_beta, b_op, f"Beta previsto {port_beta:+.3f} (limite operacional ±{b_op:.3f})."))

    # ---------- risco ex-ante ----------
    outside = sorted(set(ids) - set(model.exposures.index))
    checks.append(_check(
        "RISK_MODEL_COVERAGE", "Cobertura do modelo de risco", not outside, HARD,
        float(len(outside)), 0.0,
        "Todos os nomes com peso têm risco modelado." if not outside else
        f"Nomes sem modelo de risco (risco subestimado): {', '.join(outside)}."))
    w_model = w[~w.index.isin(outside)]
    parts = None
    risk_err = ""
    try:
        parts = portfolio_risk_parts(w_model, model)
    except (ValueError, KeyError) as exc:
        risk_err = str(exc)
    vol = parts.vol if parts is not None else float("nan")
    partial = " (parcial: nomes fora do modelo ignorados)" if outside else ""
    vol_ok = parts is not None and vol <= rk.vol_band_max + TOL
    checks.append(_check(
        "VOL_MAX", "Volatilidade ex-ante máxima", vol_ok, HARD, vol, rk.vol_band_max,
        (f"Vol ex-ante {_fmt_pct(vol)} a.a. (teto da banda {_fmt_pct(rk.vol_band_max)}){partial}."
         if parts is not None else f"Risco não calculável: {risk_err}")))
    if parts is not None:
        vmin_ok = vol >= rk.vol_band_min - TOL
        vmin_det = (f"Vol ex-ante {_fmt_pct(vol)} a.a. (piso da banda "
                    f"{_fmt_pct(rk.vol_band_min)})" + ("." if vmin_ok else ": risco subutilizado."))
    else:
        vmin_ok, vmin_det = False, f"Risco não calculável: {risk_err}"
    checks.append(_check("VOL_MIN", "Volatilidade ex-ante mínima", vmin_ok, SOFT, vol,
                         rk.vol_band_min, vmin_det))
    target = rk.vol_target_annual if vol_target is None else float(vol_target)
    dist = vol - target if parts is not None else float("nan")
    checks.append(_check(
        "VOL_TARGET", "Distância à meta de volatilidade",
        parts is not None and abs(dist) <= VOL_TARGET_INFO_BAND, INFO, vol, target,
        (f"Vol ex-ante {_fmt_pct(vol)} vs. meta {_fmt_pct(target)} "
         f"(diferença {dist * 100:+.2f} p.p.)." if parts is not None
         else f"Risco não calculável: {risk_err}")))

    # ---------- país / setor / estilos ----------
    universe_ids = cons.index.union(ids)
    country = _lookup("country", universe_ids, cons, panel_assets).map(
        lambda v: v if isinstance(v, str) and v else UNKNOWN_GROUP)
    sector = _lookup("sector", universe_ids, cons, panel_assets).map(
        lambda v: v if isinstance(v, str) and v else UNKNOWN_GROUP)
    for prefix, labels, limit, label in (
        ("COUNTRY_NET", country, rk.country_net_max_abs, "país"),
        ("SECTOR_NET", sector, rk.sector_net_max_abs, "setor"),
    ):
        nets = w.groupby(labels.reindex(ids)).sum() if len(w) else pd.Series(dtype=float)
        for g in sorted(set(labels)):
            v = float(nets.get(g, 0.0))  # grupo sem posição tem exposição nula
            checks.append(_check(
                f"{prefix}:{g}", f"Exposição líquida por {label}: {g}", abs(v) <= limit + TOL, HARD,
                v, limit, f"Net {label} {g}: {_fmt_pct(v)} do NAV (limite ±{_fmt_pct(limit)})."))
    if op is not None:
        sec_op = min(op.sector_net, rk.sector_net_max_abs)
        nets = w.groupby(sector.reindex(ids)).sum() if len(w) else pd.Series(dtype=float)
        for g in sorted(set(sector)):
            v = float(nets.get(g, 0.0))
            checks.append(_check(
                f"SECTOR_OP:{g}", f"Exposição líquida por setor (operacional): {g}",
                abs(v) <= sec_op + TOL, SOFT, v, sec_op,
                f"Net setor {g}: {_fmt_pct(v)} do NAV (limite operacional ±{_fmt_pct(sec_op)})."))
        for g, members, lim_g in _op_country_groups(country, op, rk.country_net_max_abs):
            v = float(w.reindex(members).fillna(0.0).sum())
            checks.append(_check(
                f"COUNTRY_OP:{g}", f"Exposição líquida por país (operacional): {g}",
                abs(v) <= lim_g + TOL, SOFT, v, lim_g,
                f"Net {g}: {_fmt_pct(v)} do NAV (limite operacional ±{_fmt_pct(lim_g)})."))
    styles = model.factors_in_group("style") or [f for f in STYLE_FACTORS
                                                 if f in model.exposures.columns]
    x = parts.factor_exposures if parts is not None else pd.Series(dtype=float)
    for k in styles:
        v = float(x.get(k, np.nan)) if parts is not None else float("nan")
        ok = np.isfinite(v) and abs(v) <= rk.style_exposure_max_abs + TOL
        # Com limites operacionais o limite de estilo do mandato é HARD (a escada nunca o passa).
        checks.append(_check(
            f"STYLE:{k}", f"Exposição ao estilo {k}", ok, HARD if op is not None else SOFT, v,
            rk.style_exposure_max_abs,
            f"Exposição líquida {v:+.3f} desvios-padrão × NAV (limite ±"
            f"{rk.style_exposure_max_abs:.2f})." if np.isfinite(v) else "Exposição indisponível."))
        if op is not None:
            st_op = min(op.style, rk.style_exposure_max_abs)
            checks.append(_check(
                f"STYLE_OP:{k}", f"Exposição ao estilo {k} (operacional)",
                np.isfinite(v) and abs(v) <= st_op + TOL, SOFT, v, st_op,
                f"Exposição líquida {v:+.3f} (limite operacional ±{st_op:.2f})."
                if np.isfinite(v) else "Exposição indisponível."))

    # ---------- limites por nome ----------
    view_max = pd.to_numeric(_lookup("view_max_abs", ids, cons), errors="coerce")
    long_lim = view_max.reindex(longs.index).fillna(np.inf).clip(upper=rk.max_long_weight)
    long_bad = longs[longs > long_lim + TOL]
    checks.append(_check(
        "NAME_LONG_MAX", "Peso máximo por nome (long)", long_bad.empty, HARD,
        float(longs.max()) if len(longs) else 0.0, rk.max_long_weight,
        "Nenhum long acima do teto por nome." if long_bad.empty else
        f"Longs acima do teto ({_fmt_pct(rk.max_long_weight)} ou visão): {_offenders(long_bad)}."))
    short_lim = view_max.reindex(shorts.index).fillna(np.inf).clip(upper=rk.max_short_weight)
    short_bad = shorts[-shorts > short_lim + TOL]
    checks.append(_check(
        "NAME_SHORT_MAX", "Peso máximo por nome (short)", short_bad.empty, HARD,
        float(-shorts.min()) if len(shorts) else 0.0, rk.max_short_weight,
        "Nenhum short acima do teto por nome." if short_bad.empty else
        f"Shorts acima do teto ({_fmt_pct(rk.max_short_weight)} ou visão): "
        f"{_offenders(short_bad)}."))

    # ---------- liquidez ----------
    for side, sel, col, lim, part in (
        ("LONG", longs, "adtv_long_usd", liq.max_days_to_liquidate_long,
         liq.participation_rate),
        ("SHORT", shorts, "adtv_short_usd", liq.max_days_to_liquidate_short,
         liq.short_participation_rate),
    ):
        label = "comprada" if side == "LONG" else "vendida"
        cap_col = f"cap_liquidez_{side.lower()}"
        if cap_col in cons.columns:
            # Execução só no leilão de fechamento: o limite do mandato conta FECHAMENTOS — a
            # posição sobre a capacidade estrutural de redução por fechamento da linha (pregão
            # regular). Capacidade desconhecida (0) ⇒ NaN ⇒ reprova (nunca liquidez imediata).
            cap = pd.to_numeric(cons[cap_col].reindex(sel.index), errors="coerce")
            closes = sel.abs() / cap.where(cap > 0)
            bad = closes[~(closes <= lim * (1 + TOL) + TOL)]
            worst = (float(closes.max()) if closes.notna().any()
                     else (0.0 if sel.empty else float("nan")))
            checks.append(_check(
                f"LIQ_DAYS_{side}", f"Fechamentos para liquidar (ponta {label})", bad.empty,
                HARD, worst, lim,
                (f"Máximo de {worst:.2f} fechamentos à capacidade estrutural do leilão "
                 f"(limite {lim:.1f})." if bad.empty else
                 f"Nomes acima de {lim:.1f} fechamentos à capacidade do leilão (ou sem volume "
                 f"conhecido): "
                 f"{_offenders(closes.reindex(bad.index), fmt=lambda v: f'{v:.2f}')}.")))
            continue
        if col in cons.columns:
            # ADTV da linha de execução; ausente ⇒ NaN ⇒ reprova (nunca o agregado do emissor,
            # que soma todas as linhas e superestimaria a liquidez da linha).
            adtv = pd.to_numeric(cons[col].reindex(sel.index), errors="coerce")
            src = ""
        else:
            adtv = pd.to_numeric(_lookup("adtv_usd", sel.index, panel_assets), errors="coerce")
            src = " ADTV agregado do emissor (tabela sem ADTV por linha)."
        adtv = adtv.where(adtv > 0)
        days = sel.abs() * nav / (part * adtv)
        bad_days = days[~(days <= lim * (1 + TOL) + TOL)]  # NaN (sem ADTV) reprova
        worst = float(days.max()) if days.notna().any() else (0.0 if sel.empty else float("nan"))
        checks.append(_check(
            f"LIQ_DAYS_{side}", f"Dias para liquidar (ponta {label})", bad_days.empty, HARD, worst,
            lim, (f"Máximo {worst:.2f} dias a {part:.0%} do ADTV (limite {lim:.1f}).{src}"
                  if bad_days.empty else
                  f"Nomes acima de {lim:.1f} dias a {part:.0%} do ADTV (ou sem ADTV): "
                  f"{_offenders(days.reindex(bad_days.index), fmt=lambda v: f'{v:.2f}d')}."
                  f"{src}")))

    # ---------- short: permissões, squeeze e aluguel ----------
    shortable = _bool_col(cons, "shortable", shorts.index)
    can_short = _bool_col(cons, "can_short", shorts.index)
    allowed = shortable.where(shortable.notna(), can_short)
    no_short_view = _bool_col(cons, "view_no_short", shorts.index).map(lambda v: v is True)
    not_allowed = shorts[(allowed.map(lambda v: v is not True)) | no_short_view]
    checks.append(_check(
        "SHORT_NOT_ALLOWED", "Short somente em linhas alugáveis e sem veto", not_allowed.empty,
        HARD,
        float(len(not_allowed)), 0.0,
        "Todos os shorts são alugáveis e sem veto." if not_allowed.empty else
        f"Shorts sem aluguel disponível, fora da tabela ou com veto (no_short): "
        f"{_offenders(not_allowed)}."))
    if sq.enforce_entry_blocks and "entry_block" in cons.columns:
        blocked = _bool_col(cons, "entry_block", shorts.index).map(lambda v: v is True)
        w0s = (pd.to_numeric(current, errors="coerce").reindex(shorts.index).fillna(0.0)
               if current is not None else pd.Series(0.0, index=shorts.index))
        w0s.index = w0s.index.map(str)
        grown = shorts[blocked & (-shorts > (-w0s).clip(lower=0.0) + TOL)]
        checks.append(_check(
            "SHORT_ENTRY_BLOCK", "Sem short novo ou aumentado em nome vetado", grown.empty, HARD,
            float(len(grown)), 0.0,
            "Nenhum short novo ou aumentado em nome com resultado próximo ou free float baixo."
            if grown.empty else
            f"Shorts novos/aumentados em nomes vetados (resultado próximo ou free float): "
            f"{_offenders(grown)}."))
        miss = _lookup("entry_block_dado_ausente", cons.index, cons)
        n_miss = int(miss.map(lambda v: isinstance(v, str) and v != "").sum())
        checks.append(_check(
            "SHORT_ENTRY_DATA", "Dados dos vetos de short", True, INFO, float(n_miss), None,
            f"{n_miss} emissores sem data de resultado ou free float conhecidos (sem data: "
            "sinalizado, sem veto; sem free float em nome pequeno: vetado). Participação máxima "
            "do controlador sem fonte pública estruturada: não avaliada."))

    sq_bucket = (squeeze["bucket"] if squeeze is not None and "bucket" in squeeze.columns
                 else _lookup("squeeze_bucket", universe_ids, cons))
    sq_bucket = sq_bucket.copy()
    sq_bucket.index = sq_bucket.index.map(str)
    bucket = normalize_squeeze_bucket(sq_bucket.reindex(shorts.index))
    high = shorts[bucket == "HIGH"]
    checks.append(_check(
        "SQUEEZE_HIGH", "Sem short em risco de squeeze ALTO", high.empty, HARD, float(len(high)),
        0.0, "Nenhum short em nome com risco de squeeze alto." if high.empty else
        f"Shorts em nomes com squeeze HIGH: {_offenders(high)}."))
    med_cap = rk.max_short_weight * sq.medium_short_cap_multiplier
    med = shorts[bucket.isin(["MEDIUM", "NA"])]
    med_bad = med[-med > med_cap + TOL]
    checks.append(_check(
        "SQUEEZE_MEDIUM_CAP", "Teto reduzido para short com squeeze MÉDIO/sem dado",
        med_bad.empty, HARD, float(-med.min()) if len(med) else 0.0, med_cap,
        f"Shorts MEDIUM/NA dentro do teto de {_fmt_pct(med_cap)}." if med_bad.empty else
        f"Shorts MEDIUM/NA acima de {_fmt_pct(med_cap)}: {_offenders(med_bad)}."))

    fee = pd.to_numeric(_lookup("borrow_fee", shorts.index, cons), errors="coerce")
    fee_bad = fee[~(fee <= sh.max_borrow_fee + TOL)]  # NaN reprova
    checks.append(_check(
        "BORROW_FEE", "Taxa de aluguel dos shorts", fee_bad.empty, HARD,
        float(fee.max()) if fee.notna().any() else (0.0 if shorts.empty else float("nan")),
        sh.max_borrow_fee,
        f"Taxas de aluguel dentro do limite de {_fmt_pct(sh.max_borrow_fee)} a.a." if
        fee_bad.empty else f"Aluguel acima do limite ou sem dado: {_offenders(fee_bad)}."))

    can_long = _bool_col(cons, "can_long", longs.index)
    no_long_view = _bool_col(cons, "view_no_long", longs.index).map(lambda v: v is True)
    long_na = longs[(can_long.map(lambda v: v is not True)) | no_long_view]
    checks.append(_check(
        "LONG_NOT_ALLOWED", "Long somente em nomes elegíveis e sem veto", long_na.empty, HARD,
        float(len(long_na)), 0.0,
        "Todos os longs são permitidos." if long_na.empty else
        f"Longs em nomes inelegíveis, fora da tabela ou com veto (no_long): "
        f"{_offenders(long_na)}."))

    # ---------- giro ----------
    cur = (pd.Series(dtype=float) if current is None
           else pd.to_numeric(current, errors="coerce").copy())
    cur.index = cur.index.map(str)
    all_ids = w.index.union(cur.index)
    cur_nan = cur[cur.isna()]
    turnover = float((w.reindex(all_ids).fillna(0.0) - cur.reindex(all_ids).fillna(0.0)).abs()
                     .sum())  # ausência de posição = peso zero
    if inception:
        checks.append(_check(
            "TURNOVER", "Giro semanal", True, SOFT, turnover, None,
            f"Inception: montagem inicial de {_fmt_pct(turnover)} do NAV (sem limite de giro)."))
    else:
        lim = liq.max_weekly_turnover
        ok = turnover <= lim + TOL and cur_nan.empty
        checks.append(_check(
            "TURNOVER", "Giro semanal", ok, SOFT, turnover, lim,
            f"Giro Σ|Δw| = {_fmt_pct(turnover)} do NAV (limite {_fmt_pct(lim)})."
            + ("" if cur_nan.empty else
               f" Pesos atuais ausentes para: {', '.join(cur_nan.index)}.")))

    # ---------- concentração de risco ----------
    if parts is not None and parts.total_var > 0:
        contrib = parts.contributions
        top = contrib.idxmax()
        top_v = float(contrib.max())
        checks.append(_check(
            "SINGLE_NAME_RISK", "Contribuição máxima de um nome para o risco",
            top_v <= rk.max_single_name_risk_share + TOL, SOFT, top_v,
            rk.max_single_name_risk_share,
            f"Maior contribuição: {top} com {_fmt_pct(top_v)} da variância "
            f"(limite {_fmt_pct(rk.max_single_name_risk_share)})."))
        fshare = parts.factor_share
        basis = ""
        if extended:
            ktot = kappa * parts.factor_var + parts.specific_var
            fshare = kappa * parts.factor_var / ktot if ktot > 0 else float("nan")
            basis = f" com inflação de 2ª ordem κ_F = {kappa:.2f} no bloco fatorial"
        checks.append(_check(
            "FACTOR_RISK_SHARE", "Fração do risco vinda de fatores",
            fshare <= rk.max_factor_risk_share + TOL, SOFT, fshare, rk.max_factor_risk_share,
            f"Risco fatorial = {_fmt_pct(fshare)} da variância{basis} (limite "
            f"{_fmt_pct(rk.max_factor_risk_share)}); o restante é específico (alpha puro)."))
    else:
        msg = "Carteira sem risco calculável." if parts is None else "Carteira sem posições."
        checks.append(_check("SINGLE_NAME_RISK", "Contribuição máxima de um nome para o risco",
                             parts is not None, SOFT, None, rk.max_single_name_risk_share, msg))
        checks.append(_check("FACTOR_RISK_SHARE", "Fração do risco vinda de fatores",
                             parts is not None, SOFT, None, rk.max_factor_risk_share, msg))

    # ---------- fatia idiossincrática (meta SOFT, piso HARD) por modelo ----------
    if rk.idio_share_goal is not None or rk.idio_share_floor is not None:
        gates = [("decisao", model, "", "modelo de decisão (com janelas de evento)")]
        if "base" in rk.idio_gate_models:
            gates.append(("base", model_base, "_BASE", "modelo base (sem janelas de evento)"))
        for _nome, mdl, suf, label in gates:
            s = _idio_share(w_model, mdl, kappa)
            if mdl is None:
                checks.append(_check(
                    f"IDIO_FLOOR{suf}", f"Piso da fatia idiossincrática — {label}", False, HARD,
                    None, rk.idio_share_floor, f"Modelo indisponível: {label} não calculado."))
                continue
            det_floor: str | None = None
            if s is None:
                det = "Carteira sem posições: fatia idiossincrática indefinida (sem risco)."
                ok_goal = ok_floor = True
            elif not np.isfinite(s):
                det = "Fatia idiossincrática não calculável (nome fora do modelo)."
                ok_goal = ok_floor = False
            else:
                det = (f"Fatia idiossincrática {_fmt_pct(s)} da variância ex-ante no {label}, "
                       f"κ_F = {kappa:.2f}")
                ok_goal = rk.idio_share_goal is None or s >= rk.idio_share_goal - TOL
                ok_floor = rk.idio_share_floor is None or s >= rk.idio_share_floor - TOL
                if not ok_floor and reduce_only and current is not None:
                    fv_new, fv_cur = _factor_var(w_model, mdl), _factor_var(
                        pd.to_numeric(current, errors="coerce").fillna(0.0), mdl)
                    if fv_new is not None and fv_cur is not None \
                            and fv_new <= fv_cur * (1 + REDUCE_ONLY_FACTOR_TOL) + 1e-14:
                        ok_floor = True
                        det_floor = (f"{det}; decisão só de redução, sem risco fatorial novo: "
                                     f"vol fatorial {_fmt_pct(fv_new ** 0.5)} contra "
                                     f"{_fmt_pct(fv_cur ** 0.5)} da carteira atual")
            if rk.idio_share_goal is not None:
                checks.append(_check(
                    f"IDIO_SHARE{suf}", f"Meta da fatia idiossincrática — {label}", ok_goal,
                    SOFT, s, rk.idio_share_goal,
                    det + (f" (meta {_fmt_pct(rk.idio_share_goal)})." if s is not None
                           and np.isfinite(s) else "")))
            if rk.idio_share_floor is not None:
                checks.append(_check(
                    f"IDIO_FLOOR{suf}", f"Piso da fatia idiossincrática — {label}", ok_floor,
                    HARD, s, rk.idio_share_floor,
                    (det_floor or det) + (f" (piso {_fmt_pct(rk.idio_share_floor)}, nunca "
                                          "relaxado)." if s is not None and np.isfinite(s)
                                          else "")))

    # ---------- execução no fechamento ----------
    if "cap_fechamento_long" in cons.columns or "cap_fechamento_short" in cons.columns:
        # Por perna: aumento da perna comprada contra a capacidade do fechamento da linha
        # comprada, e o da vendida contra a da linha vendida (inversão usa as duas; zerar é
        # sempre permitido). Volume desconhecido ⇒ capacidade 0.
        w_all = w.reindex(cons.index).fillna(0.0)
        c0 = (pd.to_numeric(current, errors="coerce").reindex(cons.index).fillna(0.0)
              if current is not None else pd.Series(0.0, index=cons.index))
        c0.index = c0.index.map(str)
        over: dict[str, float] = {}
        for leg, sign in (("long", 1.0), ("short", -1.0)):
            col = f"cap_fechamento_{leg}"
            capf = (pd.to_numeric(cons[col], errors="coerce").fillna(0.0)
                    if col in cons.columns else pd.Series(0.0, index=cons.index))
            inc = ((sign * w_all).clip(lower=0.0) - (sign * c0).clip(lower=0.0)).clip(lower=0.0)
            bad = inc[(inc > TOL) & ~(inc <= capf * (1 + 1e-6) + TOL)]
            for iid, v in bad.items():
                over[str(iid)] = over.get(str(iid), 0.0) + float(v)
        over_s = pd.Series(over, dtype=float)
        checks.append(_check(
            "TRADE_CLOSE_CAPACITY", "Ordens dentro da capacidade do fechamento", over_s.empty,
            SOFT, float(len(over_s)), 0.0,
            "Toda abertura ou aumento cabe na capacidade do leilão e da janela pré-fechamento."
            if over_s.empty else
            f"Aumentos acima da capacidade do fechamento (ou sem volume conhecido): "
            f"{_offenders(over_s)}."))
    if "congelado" in cons.columns:
        frozen = cons["congelado"].map(lambda v: isinstance(v, str) and v != "")
        names = sorted(map(str, cons.index[frozen.to_numpy(dtype=bool)]))
        checks.append(_check(
            "CLOSED_MARKETS_FROZEN", "Emissores sem fechamento negociável", True, INFO,
            float(len(names)), None,
            "Nenhum emissor congelado." if not names else
            f"Posição mantida sem negociação (mercado fechado ou sem linha elegível): "
            f"{', '.join(names[:MAX_LISTED])}" + (f" e mais {len(names) - MAX_LISTED}"
                                                   if len(names) > MAX_LISTED else "") + "."))
    if "stop_pendente" in cons.columns:
        pend = cons["stop_pendente"].map(lambda v: isinstance(v, str) and v != "")
        names = sorted(map(str, cons.index[pend.to_numpy(dtype=bool)]))
        if names:
            checks.append(_check(
                "SQUEEZE_STOP_PENDING", "Stop de squeeze pendente (sem fechamento negociável)",
                True, INFO, float(len(names)), None,
                "Stop de squeeze em nome sem fechamento negociável nesta decisão: corte à metade "
                f"no próximo rebalanceamento com o mercado aberto: {', '.join(names)}."))
    if op is not None and cfg.risk_model.linked_groups:
        for g, members in sorted(cfg.risk_model.linked_groups.items()):
            ww = w.reindex(members).dropna()
            lg, sg = float(ww[ww > 0].sum()), float(-ww[ww < 0].sum())
            ok = lg <= rk.max_long_weight + TOL and sg <= rk.max_short_weight + TOL
            checks.append(_check(
                f"LINKED_GROUP:{g}", f"Grupo de controle {g}", ok, SOFT, max(lg, sg),
                rk.max_long_weight,
                f"Comprado {_fmt_pct(lg)} (teto {_fmt_pct(rk.max_long_weight)}), vendido "
                f"{_fmt_pct(sg)} (teto {_fmt_pct(rk.max_short_weight)}) somando "
                f"{', '.join(members)}: holding e controlada contam como um só nome."))

    # ---------- dados ----------
    age = (week - snapshot_as_of).days
    stale_ok = 0 <= age <= MAX_STALENESS_DAYS
    checks.append(_check(
        "DATA_STALENESS", "Defasagem do snapshot de dados", stale_ok, HARD, float(age),
        float(MAX_STALENESS_DAYS),
        f"Snapshot de {snapshot_as_of.isoformat()} para a semana de {week.isoformat()}: "
        f"{age} dias corridos (máximo {MAX_STALENESS_DAYS})."
        + ("" if age >= 0 else " Snapshot POSTERIOR à semana da decisão (look-ahead).")))

    # ---------- drawdown ----------
    if drawdown is not None and not np.isfinite(float(drawdown)):
        # Drawdown informado mas ausente/não finito: stops não verificáveis (nunca "sem perda").
        msg = f"Drawdown não finito ({drawdown}): stops de drawdown não verificáveis."
        checks.append(_check("DRAWDOWN_SOFT", "Stop de drawdown (revisão)", False, SOFT, None,
                             cfg.drawdown.soft_stop, msg))
        checks.append(_check("DRAWDOWN_HARD", "Stop de drawdown (corte de gross)", False, HARD,
                             None, cfg.drawdown.hard_stop, msg))
    elif drawdown is not None and drawdown_ref_vol is not None \
            and dds_vol_mode(cfg) and np.isfinite(float(drawdown_ref_vol)):
        # Escada sobre o risco tomado: vol ≤ m(estágio)·σ_ref (σ_ref = mesma tentativa no
        # estágio normal).
        from ..research.pm_agent import ladder_stage
        from ..risk.drawdown import stage_multiplier

        dd = -abs(float(drawdown))
        dds = cfg.drawdown
        ref = float(drawdown_ref_vol)
        stg = ladder_stage(dd, cfg)
        soft_hit = dd <= dds.soft_stop + TOL
        m_soft = stage_multiplier("soft_stop", cfg)
        ok_soft = (not soft_hit) or (parts is not None and vol <= m_soft * ref * (1 + 1e-3))
        checks.append(_check(
            "DRAWDOWN_SOFT", "Stop de drawdown (revisão)", ok_soft, SOFT, dd, dds.soft_stop,
            f"Drawdown {_fmt_pct(dd)} (gatilho de revisão {_fmt_pct(dds.soft_stop)})."
            + ("" if not soft_hit else
               f" Vol ex-ante {_fmt_pct(vol)} vs. teto {_fmt_pct(m_soft * ref)} "
               f"({m_soft:.0%} da vol de referência {_fmt_pct(ref)}).")))
        hard_hit = dd <= dds.hard_stop + TOL
        m = stage_multiplier(stg, cfg)
        # Corte medido no risco tomado: a alternativa de gross vale só contra a carteira ATUAL
        # (nunca contra o gross do mandato, que não limita uma carteira pequena).
        cur_gross = float(cur.dropna().abs().sum()) if len(cur.dropna()) else 0.0
        degrossed = cur_gross > 0 and gross <= m * cur_gross + TOL
        ok_hard = (not hard_hit) or (parts is not None and vol <= m * ref * (1 + 1e-3)) \
            or degrossed
        det = (f"Drawdown {_fmt_pct(dd)} (stop {_fmt_pct(dds.hard_stop)}, stop-out "
               f"{_fmt_pct(dds.stop_out)}).")
        if hard_hit:
            det += (f" Estágio {stg}: vol ex-ante {_fmt_pct(vol)} precisa ser ≤ "
                    f"{_fmt_pct(m * ref)} ({m:.0%} da vol de referência {_fmt_pct(ref)})"
                    + (f" ou gross ≤ {m * cur_gross:.2f}x ({m:.0%} do atual)."
                       if cur_gross > 0 else "."))
        checks.append(_check(
            "DRAWDOWN_HARD", "Stop de drawdown (corte de risco)", ok_hard, HARD, dd,
            dds.hard_stop, det))
    elif drawdown is not None:
        dd = -abs(float(drawdown))  # aceita 0,04 ou −0,04 como drawdown de 4%
        dds = cfg.drawdown
        # Gatilhos inclusivos (drawdown igual ao stop aciona), com a mesma tolerância.
        soft_hit = dd <= dds.soft_stop + TOL
        checks.append(_check(
            "DRAWDOWN_SOFT", "Stop de drawdown (revisão)", not soft_hit, SOFT, dd,
            dds.soft_stop,
            f"Drawdown {_fmt_pct(dd)} (gatilho de revisão {_fmt_pct(dds.soft_stop)})."
            + ("" if not soft_hit else
               f" Revisão obrigatória da carteira; corte recomendado do gross para "
               f"{dds.soft_degross_multiplier:.0%}.")))
        cur_gross = float(cur.dropna().abs().sum()) if len(cur.dropna()) else 0.0
        ref_gross = cur_gross if cur_gross > 0 else rk.gross_max
        gross_cap = dds.degross_multiplier * ref_gross
        risk_cap = dds.degross_multiplier * target
        hard_hit = dd <= dds.hard_stop + TOL
        stop_out = dd <= dds.stop_out + TOL
        degrossed = gross <= gross_cap + TOL
        # Risco já cortado (semanas seguintes ao stop): não exige novo corte a cada semana.
        risk_cut = parts is not None and vol <= risk_cap + TOL
        ok_hard = (not hard_hit) or degrossed or risk_cut
        ok_out = (not stop_out) or gross <= dds.stop_out_gross + TOL
        det = f"Drawdown {_fmt_pct(dd)} (stop {_fmt_pct(dds.hard_stop)}, stop-out " \
              f"{_fmt_pct(dds.stop_out)})."
        if hard_hit:
            det += (f" Stop acionado: gross proposto {gross:.2f}x precisa ser ≤ {gross_cap:.2f}x "
                    f"({dds.degross_multiplier:.0%} do gross de referência {ref_gross:.2f}x) "
                    f"ou vol ex-ante ≤ {_fmt_pct(risk_cap)} (risco já cortado).")
        if stop_out:
            det += (f" Stop-out acionado: gross proposto {gross:.2f}x precisa ser ≤ "
                    f"{dds.stop_out_gross:.2f}x e revisão completa do processo.")
        checks.append(_check(
            "DRAWDOWN_HARD", "Stop de drawdown (corte de gross)", ok_hard and ok_out, HARD, dd,
            dds.hard_stop, det))

    checks.append(_check(
        "SYNTHETIC_DATA", "Origem dos dados", True, INFO, 1.0 if is_synthetic else 0.0, None,
        f"{SIMULATED_DATA_NOTICE}: carteira calculada sobre mercado sintético; não usar para "
        "decisões reais." if is_synthetic
        else "Dados reais de snapshot imutável (hash verificado)."))
    return checks


def dds_vol_mode(cfg: FundConfig) -> bool:
    """Escada de drawdown sobre a vol ex-ante (``drawdown.risk_reference``)."""
    return cfg.drawdown.risk_reference == "normal_book_vol"


def hard_failures(checks: list[ComplianceCheck]) -> list[ComplianceCheck]:
    """Checagens HARD reprovadas (bloqueiam a aprovação)."""
    return [c for c in checks if not c.passed and c.severity == Severity.HARD]


def soft_failures(checks: list[ComplianceCheck]) -> list[ComplianceCheck]:
    """Checagens SOFT reprovadas (exigem ciência explícita do gestor)."""
    return [c for c in checks if not c.passed and c.severity == Severity.SOFT]
