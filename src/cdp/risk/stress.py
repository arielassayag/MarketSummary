"""Testes de estresse: reaplicação histórica, choques fatoriais hipotéticos e idiossincráticos.

Todos os resultados são P&L em fração do NAV (negativo = perda), calculados em código.

- Históricos: retorno acumulado de cada emissor do fechamento de ``início`` ao fechamento de
  ``fim`` (retornos em USD com data em ``(início, fim]``), carteira estática. Emissor sem dado
  na janela ⇒ retorno fatorial implícito acumulado (``Π(1 + B_i·f_t) − 1``); se o modelo não
  tiver histórico fatorial na janela, o cenário fica "sem dados" (``NaN``, nunca zero).
- Hipotéticos: choque ``s`` nos fatores escolhidos com propagação condicional
  ``E[f_resto | f_choque = s] = F_rs F_ss⁻¹ s`` (escala-invariante, usa a covariância do
  modelo). O tamanho do choque é calibrado para que a carteira de referência (ex.: Brasil
  ponderado por capitalização) tenha o retorno-alvo do cenário.
- Idiossincráticos: squeeze (+30% nos 5 maiores shorts) e quebra (−30% nos 5 maiores longs).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from ..analytics.panel import AssetPanel
from .analytics import check_weights, model_implied_returns
from .types import MARKET_FACTOR, TRADING_DAYS, RiskModel, country_factor, sector_factor

NO_DATA = "sem dados"

HISTORICAL_SCENARIOS: dict[str, tuple[date, date]] = {
    "Taper tantrum (mai-jun/2013)": (date(2013, 5, 22), date(2013, 6, 24)),
    "Joesley Day (mai/2017)": (date(2017, 5, 17), date(2017, 5, 18)),
    "PASO Argentina 2019": (date(2019, 8, 9), date(2019, 8, 12)),
    "Estallido social Chile (out-nov/2019)": (date(2019, 10, 17), date(2019, 11, 12)),
    "COVID crash (fev-mar/2020)": (date(2020, 2, 19), date(2020, 3, 23)),
    "Taper/estresse jun/2022": (date(2022, 6, 8), date(2022, 7, 14)),
    "Eleição Brasil out/2022 (2º turno)": (date(2022, 10, 28), date(2022, 11, 11)),
    "Eleição México jun/2024": (date(2024, 5, 31), date(2024, 6, 12)),
    "Choque fiscal BRL dez/2024": (date(2024, 11, 26), date(2024, 12, 18)),
    "Tarifas EUA abr/2025 (Liberation Day)": (date(2025, 4, 2), date(2025, 4, 8)),
}

COUNTRY_SHOCK = -0.15
MARKET_SHOCK = -0.20
COMMODITY_SHOCK = -0.15
MOMENTUM_CRASH_SIGMAS = -3.0
MOMENTUM_CRASH_HORIZON_DAYS = 21
IDIO_SHOCK = 0.30
IDIO_TOP_N = 5


@dataclass(frozen=True)
class StressResult:
    name: str
    kind: str        # histórico | hipotético | idiossincrático
    pnl: float       # fração do NAV; NaN quando sem dados
    status: str      # ok | sem dados
    detail: str = ""


# ==========================================================
# Históricos
# ==========================================================

def historical_scenario_pnl(
    w: pd.Series, panel: AssetPanel, model: RiskModel, start: date, end: date,
) -> tuple[float, str]:
    """P&L da carteira estática ``w`` reaplicando os retornos de ``(start, end]``."""
    wa = model.align(check_weights(w))
    held = wa[wa != 0]
    cal = pd.DatetimeIndex(panel.returns.index)
    cal = cal[cal <= pd.Timestamp(model.as_of)]
    ts0, ts1 = pd.Timestamp(start), pd.Timestamp(end)
    if len(cal) == 0 or cal[0] > ts0 or cal[-1] < ts1:
        return np.nan, "painel não cobre a janela"
    dates = cal[(cal > ts0) & (cal <= ts1)]
    if len(dates) == 0:
        return np.nan, "sem pregões na janela"
    if held.empty:
        return 0.0, "carteira sem posições"
    rets = panel.returns.reindex(index=dates, columns=held.index)
    px = panel.price_usd.reindex(columns=held.index)
    traded_before = px.loc[px.index <= ts0].notna().any()
    covered = rets.notna().any() & traded_before
    cum = pd.Series(np.nan, index=held.index)
    for iid in held.index[covered.to_numpy()]:
        r = rets[iid].dropna()
        cum[iid] = float(np.prod(1.0 + r.to_numpy()) - 1.0)
    missing = list(held.index[~covered.to_numpy()])
    detail = ""
    if missing:
        fr = model.factor_returns
        if len(fr) == 0 or fr.index[0] > dates[0] or not dates.isin(fr.index).all():
            return np.nan, f"modelo sem histórico fatorial na janela para {missing}"
        implied = model_implied_returns(model, missing, dates)
        for iid in missing:
            r = implied[iid].dropna()
            if r.empty:
                return np.nan, f"retorno fatorial implícito indefinido para {iid}"
            cum[iid] = float(np.prod(1.0 + r.to_numpy()) - 1.0)
        detail = f"retorno fatorial implícito para {missing}"
    return float((held * cum).sum()), detail


# ==========================================================
# Hipotéticos (choques fatoriais com propagação condicional)
# ==========================================================

def conditional_factor_move(model: RiskModel, shocks: dict[str, float]) -> pd.Series:
    """Vetor completo de movimentos fatoriais dado o choque: ``[s; F_rs F_ss⁻¹ s]``."""
    names = model.factor_names
    unknown = sorted(set(shocks) - set(names))
    if unknown:
        raise KeyError(f"Fatores inexistentes no modelo: {unknown}")
    F = model.factor_cov.loc[names, names].to_numpy()
    s_idx = [names.index(k) for k in shocks]
    s = np.array([shocks[k] for k in shocks], dtype=float)
    F_ss = F[np.ix_(s_idx, s_idx)]
    coef = np.linalg.lstsq(F_ss, s, rcond=None)[0]
    move = F[:, s_idx] @ coef
    move[s_idx] = s
    return pd.Series(move, index=names, name="factor_move")


def factor_shock_pnl(w: pd.Series, model: RiskModel, shocks: dict[str, float]) -> float:
    """P&L fatorial (sem específico) da carteira para o choque condicional."""
    x = model.factor_exposure(check_weights(w))
    return float(x @ conditional_factor_move(model, shocks).reindex(x.index))


def _calibrated_shock(
    model: RiskModel, factors: list[str], ref: pd.Series, target: float,
) -> dict[str, float] | None:
    """Choque igual ``v`` em ``factors`` tal que a carteira ``ref`` renda ``target``."""
    unit = {f: 1.0 for f in factors}
    ref_ret = float(model.factor_exposure(ref) @ conditional_factor_move(model, unit)
                    .reindex(model.factor_names))
    if not abs(ref_ret) > 1e-12:
        return None
    v = target / ref_ret
    return {f: v for f in factors}


def _members(model: RiskModel, factors: list[str]) -> list[str]:
    B = model.exposures[factors]
    return list(B.index[(B != 0).any(axis=1)])


def _ref_portfolio(market_w: pd.Series, model: RiskModel, members: list[str]) -> pd.Series | None:
    m = market_w.reindex(members)
    m = m[m.notna() & (m > 0)]
    if m.empty:
        return None
    return m / m.sum()


def _hypothetical(
    name: str, w: pd.Series, model: RiskModel, market_w: pd.Series, factors: list[str],
    target: float, ref_members: list[str] | None = None,
) -> StressResult:
    present = [f for f in factors if f in model.factor_names]
    if not present:
        return StressResult(name, "hipotético", np.nan, NO_DATA,
                            f"fator(es) ausente(s) no modelo: {factors}")
    members = ref_members if ref_members is not None else _members(model, present)
    ref = _ref_portfolio(market_w, model, members)
    if ref is None:
        return StressResult(name, "hipotético", np.nan, NO_DATA, "carteira de referência vazia")
    shocks = _calibrated_shock(model, present, ref, target)
    if shocks is None:
        return StressResult(name, "hipotético", np.nan, NO_DATA, "choque não calibrável")
    pnl = factor_shock_pnl(w, model, shocks)
    detail = ", ".join(f"{k} {v:+.2%}" for k, v in shocks.items())
    return StressResult(name, "hipotético", pnl, "ok",
                        f"choque {detail}; referência {target:+.0%} (cap-weighted)")


def _momentum_crash(w: pd.Series, model: RiskModel) -> StressResult:
    name = "Momentum crash -3σ"
    if "momentum" not in model.factor_names:
        return StressResult(name, "hipotético", np.nan, NO_DATA, "fator momentum ausente")
    var_a = float(model.factor_cov.loc["momentum", "momentum"])
    s = MOMENTUM_CRASH_SIGMAS * np.sqrt(var_a * MOMENTUM_CRASH_HORIZON_DAYS / TRADING_DAYS)
    pnl = factor_shock_pnl(w, model, {"momentum": s})
    return StressResult(name, "hipotético", pnl, "ok",
                        f"momentum {s:+.2%} (−3σ em {MOMENTUM_CRASH_HORIZON_DAYS} pregões)")


def _idiosyncratic(w: pd.Series, model: RiskModel) -> list[StressResult]:
    wa = model.align(check_weights(w))
    shorts = wa[wa < 0].sort_values().head(IDIO_TOP_N)
    longs = wa[wa > 0].sort_values(ascending=False).head(IDIO_TOP_N)
    return [
        StressResult(f"Squeeze: {IDIO_TOP_N} maiores shorts +30%", "idiossincrático",
                     float((shorts * IDIO_SHOCK).sum()), "ok",
                     f"nomes: {list(shorts.index)}" if len(shorts) else "sem shorts"),
        StressResult(f"Quebra: {IDIO_TOP_N} maiores longs -30%", "idiossincrático",
                     float((longs * -IDIO_SHOCK).sum()), "ok",
                     f"nomes: {list(longs.index)}" if len(longs) else "sem longs"),
    ]


# ==========================================================
# API
# ==========================================================

def stress_report(
    w: pd.Series, panel: AssetPanel, model: RiskModel, market_w: pd.Series,
    scenarios: dict[str, tuple[date, date]] | None = None,
) -> pd.DataFrame:
    """Tabela completa (cenário × tipo, pnl, status, detalhe); "sem dados" ⇒ ``pnl`` NaN."""
    w = check_weights(w)
    results: list[StressResult] = []
    for name, (d0, d1) in (scenarios or HISTORICAL_SCENARIOS).items():
        pnl, detail = historical_scenario_pnl(w, panel, model, d0, d1)
        status = "ok" if np.isfinite(pnl) else NO_DATA
        results.append(StressResult(name, "histórico", pnl, status,
                                    f"{d0.isoformat()}→{d1.isoformat()}"
                                    + (f"; {detail}" if detail else "")))
    br, mx = country_factor("BR"), country_factor("MX")
    results.append(_hypothetical("Brasil -15%", w, model, market_w, [br], COUNTRY_SHOCK))
    results.append(_hypothetical("México -15%", w, model, market_w, [mx], COUNTRY_SHOCK))
    results.append(_hypothetical("Mercado LatAm -20%", w, model, market_w, [MARKET_FACTOR],
                                 MARKET_SHOCK, ref_members=list(model.assets)))
    results.append(_hypothetical(
        "Commodities -15%", w, model, market_w,
        [sector_factor("Energy"), sector_factor("Materials")], COMMODITY_SHOCK))
    results.append(_momentum_crash(w, model))
    results.extend(_idiosyncratic(w, model))
    df = pd.DataFrame([r.__dict__ for r in results]).set_index("name")
    df.attrs["as_of"] = str(model.as_of)
    return df


def stress_tests(
    w: pd.Series, panel: AssetPanel, model: RiskModel, market_w: pd.Series,
) -> dict[str, float]:
    """P&L por cenário em fração do NAV; cenários "sem dados" retornam ``NaN`` (nunca zero).

    Use ``stress_report`` para status e detalhes (janelas, choques calibrados, nomes).
    """
    rep = stress_report(w, panel, model, market_w)
    return {name: float(v) for name, v in rep["pnl"].items()}
