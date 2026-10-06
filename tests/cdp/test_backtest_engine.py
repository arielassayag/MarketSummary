"""Testes do backtest walk-forward e das métricas (DADOS SIMULADOS, offline).

O mercado sintético é curto (jan/2023 a fev/2024) e os backtests usam poucas semanas para
manter o arquivo rápido; o modo ``cap`` do otimizador é usado onde a meta de vol não é o
objeto do teste (o modo ``match``, padrão do motor, tem um teste próprio).
"""

from __future__ import annotations

import dataclasses
import math
import sys
import types
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cdp.analytics.panel import build_asset_panel
from cdp.backtest import engine as eng
from cdp.backtest.engine import (
    DAILY_COLUMNS,
    WEEKLY_COLUMNS,
    BacktestConfig,
    PointInTimeInputs,
    earliest_start,
    primary_sessions,
    rebalance_dates,
    rf_daily_series,
    run_backtest,
    simulate_weights,
)
from cdp.backtest.metrics import (
    deflated_sharpe_ratio,
    drawdown_series,
    expected_max_sharpe,
    ic_summary,
    performance_metrics,
    weekly_returns,
)
from cdp.config import load_config
from cdp.data.synthetic import make_synthetic_market
from cdp.portfolio.optimizer import OptimizationError

CFG_PATH = Path(__file__).resolve().parent / "fixtures" / "fund_legado.yaml"
CFG = load_config(CFG_PATH)
START = date(2023, 12, 4)
AS_OF = date(2024, 2, 23)
CUTOFF = pd.Timestamp("2023-12-19")  # dados posteriores alterados no teste de look-ahead
NAV0 = 100e6


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture(scope="module")
def md():
    # Alpha plantado forte e persistente: o momentum residual (PIT) deve capturá-lo.
    return make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=AS_OF,
                                 planted_alpha=0.003)


@pytest.fixture(scope="module")
def panel(md):
    return build_asset_panel(md, CFG)


@pytest.fixture(scope="module")
def main_run(md):
    return run_backtest(md, CFG, BacktestConfig(start=START, risk_target_mode="cap"))


def _alter_after(md, cutoff: pd.Timestamp, seed: int = 123):
    """Mercado com preços e volumes posteriores a ``cutoff`` alterados (futuro diferente).

    O último preço válido de cada linha é preservado: capitalização histórica e B/P usam o
    último preço como âncora (aproximação não-PIT documentada), e o teste isola o look-ahead
    de retornos/volumes.
    """
    rng = np.random.default_rng(seed)
    close, adj, vol = md.close.copy(), md.adj_close.copy(), md.volume.copy()
    shock = 1.0 + rng.normal(0.0, 0.05, close.shape)
    for k, col in enumerate(close.columns):
        last = close[col].last_valid_index()
        mask = (close.index > cutoff) & (close.index < last)
        close.loc[mask, col] = close.loc[mask, col] * shock[mask, k]
        adj.loc[mask, col] = adj.loc[mask, col] * shock[mask, k]
        vol.loc[mask, col] = vol.loc[mask, col] * 3.0
    return dataclasses.replace(md, close=close, adj_close=adj, volume=vol)


@pytest.fixture(scope="module")
def altered_run(md):
    alt = _alter_after(md, CUTOFF)
    return run_backtest(alt, CFG, BacktestConfig(start=START, end=date(2023, 12, 27),
                                                 risk_target_mode="cap"))


# ======================================================================
# Métricas
# ======================================================================

def test_performance_metrics_known_values():
    idx = pd.bdate_range("2024-01-01", periods=252)
    r = pd.Series(0.0004, index=idx)
    m = performance_metrics(r)
    assert m["n_obs"] == 252
    assert m["ann_return"] == pytest.approx(1.0004 ** 252 - 1.0, rel=1e-12)
    assert m["total_return"] == pytest.approx(1.0004 ** 252 - 1.0, rel=1e-12)
    assert m["ann_vol"] == pytest.approx(0.0, abs=1e-12)
    assert math.isnan(m["sharpe"])  # desvio zero: Sharpe indefinido, nunca infinito
    assert m["max_drawdown"] == 0.0
    assert math.isnan(m["calmar"])
    assert m["hit_rate_weekly"] == 1.0


def test_performance_metrics_sharpe_excess_and_drawdown():
    idx = pd.bdate_range("2024-01-01", periods=10)
    r = pd.Series([0.01, -0.02, 0.005, 0.0, 0.01, -0.01, 0.02, -0.005, 0.0, 0.01], index=idx)
    rf = pd.Series(0.0001, index=idx)
    m = performance_metrics(r, rf, periods=252)
    ex = r - rf
    assert m["sharpe"] == pytest.approx(ex.mean() / ex.std(ddof=1) * math.sqrt(252))
    downside = math.sqrt(float(np.mean(np.minimum(ex, 0.0) ** 2)))
    assert m["sortino"] == pytest.approx(ex.mean() / downside * math.sqrt(252))
    wealth = (1 + r).cumprod()
    peak = np.maximum(wealth.cummax(), 1.0)
    assert m["max_drawdown"] == pytest.approx(float((wealth / peak - 1).min()))
    assert m["max_drawdown"] < 0
    assert m["calmar"] == pytest.approx(m["ann_return"] / abs(m["max_drawdown"]))
    assert m["skew"] == pytest.approx(float(r.skew()))
    assert m["excess_kurtosis"] == pytest.approx(float(r.kurt()))


def test_drawdown_starts_from_initial_wealth_and_skips_missing():
    r = pd.Series([-0.01, np.nan, 0.02, -0.03], index=pd.bdate_range("2024-01-01", periods=4))
    dd = drawdown_series(r)
    assert len(dd) == 3  # dia ausente não vira retorno zero
    assert dd.iloc[0] == pytest.approx(-0.01)
    w = np.cumprod([0.99, 1.02, 0.97])
    assert dd.iloc[-1] == pytest.approx(w[-1] / max(w.max(), 1.0) - 1.0)
    m = performance_metrics(r)
    assert m["n_missing"] == 1 and m["n_obs"] == 3


def test_weekly_returns_compound_by_friday_week():
    idx = pd.bdate_range("2024-01-01", periods=10)  # duas semanas completas
    r = pd.Series([0.01] * 5 + [-0.01] * 5, index=idx)
    wk = weekly_returns(r)
    assert len(wk) == 2
    assert wk.iloc[0] == pytest.approx(1.01 ** 5 - 1)
    assert wk.iloc[1] == pytest.approx(0.99 ** 5 - 1)
    assert list(wk.index.dayofweek) == [4, 4]
    m = performance_metrics(r)
    assert m["hit_rate_weekly"] == 0.5
    assert m["best_week"] == pytest.approx(wk.max())
    assert m["worst_week"] == pytest.approx(wk.min())


def test_vol_band_fraction_and_rolling_vol():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2023-01-02", periods=300)
    r = pd.Series(rng.normal(0, 0.05 / math.sqrt(252), 300), index=idx)
    m = performance_metrics(r, vol_band_min=0.03, vol_band_max=0.07)
    assert 0.9 <= m["pct_time_vol_in_band"] <= 1.0
    assert m["avg_realized_vol_63d"] == pytest.approx(0.05, abs=0.01)
    narrow = performance_metrics(r, vol_band_min=0.10, vol_band_max=0.20)
    assert narrow["pct_time_vol_in_band"] == 0.0
    assert math.isnan(performance_metrics(r)["pct_time_vol_in_band"])  # sem banda
    with pytest.raises(ValueError):
        performance_metrics(r, vol_band_min=0.07, vol_band_max=0.03)


def test_performance_metrics_empty_and_invalid():
    m = performance_metrics(pd.Series([np.nan, np.nan]))
    assert m["n_obs"] == 0 and m["n_missing"] == 2
    assert math.isnan(m["ann_return"]) and math.isnan(m["sharpe"])
    with pytest.raises(ValueError):
        performance_metrics(pd.Series([0.01, -1.0]))


def test_deflated_sharpe_decreases_with_trials_and_is_probability():
    args = dict(sharpe=1.5, n_obs=756, skew=-0.2, kurtosis=1.0, periods_per_year=252)
    dsr = [deflated_sharpe_ratio(n_trials=n, **args) for n in (1, 2, 10, 100, 1000)]
    assert all(0.0 <= v <= 1.0 for v in dsr)
    assert all(a > b for a, b in zip(dsr, dsr[1:], strict=False))
    # Sharpe maior ⇒ DSR maior; amostra maior ⇒ DSR maior (mesmo Sharpe positivo).
    assert deflated_sharpe_ratio(2.0, 756, 10, -0.2, 1.0, periods_per_year=252) > dsr[2]
    assert deflated_sharpe_ratio(1.5, 1500, 10, -0.2, 1.0, periods_per_year=252) > dsr[2]


def test_deflated_sharpe_single_trial_equals_psr_formula():
    sr, n, skew, exk = 0.08, 500, -0.5, 2.0  # Sharpe diário
    z = sr * math.sqrt(n - 1) / math.sqrt(1 - skew * sr + (exk + 3 - 1) / 4 * sr ** 2)
    expected = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    assert deflated_sharpe_ratio(sr, n, 1, skew, exk) == pytest.approx(expected, rel=1e-12)
    # Curtose bruta equivalente dá o mesmo resultado.
    raw = deflated_sharpe_ratio(sr, n, 1, skew, exk + 3, kurtosis_is_excess=False)
    assert raw == pytest.approx(expected, rel=1e-12)
    # Desvio entre tentativas informado aumenta a barra com mais tentativas.
    low = deflated_sharpe_ratio(sr, n, 50, skew, exk, sharpe_trials_std=0.01)
    high = deflated_sharpe_ratio(sr, n, 50, skew, exk, sharpe_trials_std=0.05)
    assert high < low


def test_deflated_sharpe_invalid_inputs():
    assert math.isnan(deflated_sharpe_ratio(float("nan"), 100, 5, 0.0, 0.0))
    assert math.isnan(deflated_sharpe_ratio(0.1, 1, 5, 0.0, 0.0))
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(0.1, 100, 0, 0.0, 0.0)
    assert expected_max_sharpe(1, 0.1) == 0.0
    assert expected_max_sharpe(100, 0.1) > expected_max_sharpe(10, 0.1) > 0


def test_ic_summary_values():
    ic = pd.DataFrame({"a": [0.1, 0.2, np.nan, 0.3], "b": [-0.1, 0.1, -0.1, 0.1]})
    s = ic_summary(ic)
    a = pd.Series([0.1, 0.2, 0.3])
    assert s.loc["a", "n"] == 3
    assert s.loc["a", "mean"] == pytest.approx(0.2)
    assert s.loc["a", "std"] == pytest.approx(a.std(ddof=1))
    assert s.loc["a", "icir"] == pytest.approx(0.2 / a.std(ddof=1))
    assert s.loc["a", "t_stat"] == pytest.approx(0.2 / a.std(ddof=1) * math.sqrt(3))
    assert s.loc["a", "hit_rate"] == 1.0
    assert s.loc["b", "mean"] == pytest.approx(0.0)
    assert s.loc["b", "hit_rate"] == 0.5


# ======================================================================
# Configuração, calendário e insumos PIT
# ======================================================================

def test_backtest_config_validation_and_effective_values():
    bt = BacktestConfig(start=START)
    assert bt.effective_vol_target(CFG) == pytest.approx(
        CFG.risk.vol_target_annual / CFG.risk.bias_prior)
    w = bt.effective_signal_weights(CFG)
    cfg_w = CFG.alpha.signal_weights
    # Sinais com peso zero na configuração (ex.: reversão de curto prazo, calibração 2026-10-05)
    # saem do backtest; os demais entram com o peso normalizado.
    assert set(w) == {n for n in bt.signal_names if cfg_w.get(n, 0.0) > 0}
    assert all(cfg_w.get(n, 0.0) == 0 for n in set(bt.signal_names) - set(w))
    assert sum(w.values()) == pytest.approx(1.0)
    total = sum(cfg_w[n] for n in bt.signal_names)
    assert w["residual_momentum"] == pytest.approx(cfg_w["residual_momentum"] / total)
    with pytest.raises(ValueError, match="point-in-time"):
        BacktestConfig(start=START, signal_names=("residual_momentum", "value"))
    with pytest.raises(ValueError, match="desconhecidos"):
        BacktestConfig(start=START, signal_names=("nao_existe",))
    with pytest.raises(ValueError):
        BacktestConfig(start=START, end=START)
    with pytest.raises(ValueError):
        BacktestConfig(start=START, risk_target_mode="max")
    with pytest.raises(ValueError, match="banda"):
        BacktestConfig(start=START, vol_target=0.20).effective_vol_target(CFG)
    with pytest.raises(ValueError):
        BacktestConfig(start=START, signal_weights={"residual_momentum": 0.0}
                       ).effective_signal_weights(CFG)
    with pytest.raises(ValueError, match="fora de signal_names"):
        BacktestConfig(start=START, signal_names=("low_risk",),
                       signal_weights={"residual_momentum": 1.0})
    custom = BacktestConfig(start=START, signal_names=("low_risk", "residual_momentum"),
                            signal_weights={"low_risk": 1.0, "residual_momentum": 3.0})
    assert custom.effective_signal_weights(CFG) == {"low_risk": 0.25, "residual_momentum": 0.75}


def test_rebalance_dates_first_trading_day_of_week():
    cal = pd.bdate_range("2024-01-01", "2024-01-31")
    cal = cal.drop(pd.Timestamp("2024-01-15"))  # segunda-feira feriado
    reb = rebalance_dates(cal, date(2024, 1, 3), date(2024, 1, 31))
    assert pd.Timestamp("2024-01-01") not in reb  # início no meio da semana: próxima semana
    assert list(reb) == [pd.Timestamp(x) for x in
                         ("2024-01-08", "2024-01-16", "2024-01-22", "2024-01-29")]


def test_rebalance_dates_last_trading_day_of_week_for_the_nyse_rule():
    from test_calendar import ativado

    cal = pd.bdate_range("2024-03-18", "2024-04-05").drop(pd.Timestamp("2024-03-29"))
    reb = rebalance_dates(cal, date(2024, 3, 18), date(2024, 4, 5), rule="last")
    assert list(reb) == [pd.Timestamp(x) for x in ("2024-03-22", "2024-03-28", "2024-04-05")]
    assert eng.rebalance_rule(ativado()) == ("last", "XNYS")
    assert eng.rebalance_rule(CFG) == ("first", "BVMF")
    with pytest.raises(ValueError):
        rebalance_dates(cal, date(2024, 3, 18), rule="meio")


def test_rf_daily_uses_previous_day_rate(md):
    cal = md.close.index
    rf = rf_daily_series(md, cal)
    assert math.isnan(rf.iloc[0])
    assert rf.iloc[5] == pytest.approx(float(md.rates["USD_3M"].iloc[4]) / 252)
    no_rates = dataclasses.replace(md, rates=pd.DataFrame(index=cal))
    assert rf_daily_series(no_rates, cal) is None


def test_point_in_time_inputs_eligibility_and_no_lookahead(md, panel):
    pit = PointInTimeInputs(panel, md, CFG)
    cal = pit.calendar
    early = pit.assets_at(int(cal.get_loc(pd.Timestamp("2023-03-01"))))
    assert not early["eligible"].any()
    assert early["exclusion_reason"].str.contains("historico_curto").all()
    end = pit.assets_at(len(cal) - 1)
    stale = md.universe.issuers.index[5]
    assert "preco_defasado" in end.loc[stale, "exclusion_reason"]
    pos = int(cal.get_loc(pd.Timestamp("2023-11-30")))
    a = pit.assets_at(pos)
    iid = a.index[0]
    tv = panel.traded_value_usd[iid].iloc[pos - CFG.liquidity.adv_window_days + 1: pos + 1]
    assert a.loc[iid, "adtv_usd"] == pytest.approx(tv.mean())
    assert a.loc[iid, "n_obs"] == panel.returns[iid].iloc[: pos + 1].notna().sum()
    # Alterar o futuro não muda a fotografia PIT de uma data anterior.
    alt = _alter_after(md, pd.Timestamp("2023-12-01"))
    pit2 = PointInTimeInputs(build_asset_panel(alt, CFG), alt, CFG)
    pd.testing.assert_frame_equal(pit2.assets_at(pos), a)
    pd.testing.assert_frame_equal(pit2.lines_at(pos), pit.lines_at(pos))
    lines = pit.lines_at(pos)
    assert {"adtv_usd", "has_data", "market", "line_type", "issuer_id"} <= set(lines.columns)


def test_earliest_start_is_monday_after_minimum_history(md):
    d = earliest_start(md, CFG)
    assert pd.Timestamp(d).dayofweek == 0
    assert (md.close.index < pd.Timestamp(d)).sum() > CFG.risk_model.min_obs_days


# ======================================================================
# Contabilidade (réplica de pesos)
# ======================================================================

def _toy():
    idx = pd.bdate_range("2024-01-01", periods=5)
    rets = pd.DataFrame({"A": [0.0, 0.01, np.nan, 0.02, -0.01],
                         "B": [0.0, -0.02, 0.01, 0.0, 0.03]}, index=idx)
    targets = pd.DataFrame({"A": [0.5, 0.3], "B": [-0.5, -0.3]}, index=idx[[0, 2]])
    return rets, targets


def _dollar_ledger(rets, targets, cost_rate=0.0, fee=0.0, rf=0.0):
    """Livro em dólares (posições + caixa), independente da implementação do motor."""
    nav, pos, out = 1.0, dict.fromkeys(rets.columns, 0.0), []
    days = rets.index[rets.index >= targets.index[0]]
    for t in days:
        cash = nav - sum(pos.values())
        r = {c: 0.0 if np.isnan(rets.loc[t, c]) else float(rets.loc[t, c]) for c in pos}
        pnl = sum(pos[c] * r[c] for c in pos)
        borrow = sum(-v for v in pos.values() if v < 0) * fee / 252
        interest = cash * rf / 252
        pos = {c: pos[c] * (1.0 + r[c]) for c in pos}
        nav_pre = nav + pnl + interest - borrow
        cost = 0.0
        if t in targets.index:
            cost = cost_rate * sum(abs(float(targets.loc[t, c]) * nav_pre - pos[c]) for c in pos)
            pos = {c: float(targets.loc[t, c]) * (nav_pre - cost) for c in pos}
        new_nav = nav_pre - cost
        out.append({"ret_gross": pnl / nav, "ret_net": new_nav / nav - 1.0, "nav": new_nav})
        nav = new_nav
    return pd.DataFrame(out, index=days)


def test_simulate_weights_pnl_equals_sum_w_r_with_drift():
    rets, targets = _toy()
    d = simulate_weights(rets, targets)
    assert list(d.columns) == ["ret_net", "ret_gross", "cost", "borrow", "financing", "nav",
                               "gross", "net", "rebalance"]
    # Dia do rebalanceamento: retorno acumula nos pesos anteriores (caixa).
    assert d["ret_gross"].iloc[0] == 0.0
    assert d["ret_gross"].iloc[1] == pytest.approx(0.5 * 0.01 + (-0.5) * (-0.02))
    w_a = 0.5 * 1.01 / 1.015  # deriva: w_{t} = w_{t-1}(1 + r) / (1 + R)
    w_b = -0.5 * 0.98 / 1.015
    assert d["gross"].iloc[1] == pytest.approx(abs(w_a) + abs(w_b))
    assert d["net"].iloc[1] == pytest.approx(w_a + w_b)
    # A sem retorno: contribui 0 e a posição é carregada; só B rende.
    assert d["ret_gross"].iloc[2] == pytest.approx(w_b * 0.01)
    assert d["ret_gross"].iloc[3] == pytest.approx(0.3 * 0.02)
    led = _dollar_ledger(rets, targets)
    np.testing.assert_allclose(d["ret_gross"], led["ret_gross"], atol=1e-14)
    np.testing.assert_allclose(d["nav"], led["nav"], atol=1e-14)
    assert d["nav"].iloc[-1] == pytest.approx(float(np.prod(1 + d["ret_net"])))
    assert d["gross"].iloc[2] == pytest.approx(0.6)  # rebalanceado para (0,3; −0,3)


def test_costs_borrow_and_financing_reduce_or_add_as_expected():
    rets, targets = _toy()
    base = simulate_weights(rets, targets)
    costly = simulate_weights(rets, targets, cost_rate=0.001)
    assert (costly["cost"] > 0).sum() == 2  # só nos dois rebalanceamentos
    assert costly["cost"].iloc[0] == pytest.approx(0.001 * 1.0)  # Σ|Δw| = 1 na inception
    assert costly["nav"].iloc[-1] < base["nav"].iloc[-1]
    led = _dollar_ledger(rets, targets, cost_rate=0.001)
    np.testing.assert_allclose(costly["nav"], led["nav"], atol=1e-14)
    borrowed = simulate_weights(rets, targets, borrow_fee=0.05)
    assert (borrowed["borrow"].iloc[1:] > 0).all()
    assert borrowed["borrow"].iloc[1] == pytest.approx(0.5 * 0.05 / 252)
    assert borrowed["nav"].iloc[-1] < base["nav"].iloc[-1]
    fin = simulate_weights(rets, targets, rf_annual=0.04)
    assert fin["financing"].iloc[0] == pytest.approx(0.04 / 252)  # caixa = NAV inteiro
    assert fin["nav"].iloc[-1] > base["nav"].iloc[-1]
    ident = fin["ret_gross"] - fin["cost"] - fin["borrow"] + fin["financing"]
    np.testing.assert_allclose(fin["ret_net"], ident, atol=1e-15)


def test_simulate_weights_rejects_unknown_inputs():
    rets, targets = _toy()
    with pytest.raises(KeyError):
        simulate_weights(rets, targets.assign(C=0.1))
    with pytest.raises(ValueError):
        simulate_weights(rets, targets.astype(float).where(targets > 0))


# ======================================================================
# Motor completo (mercado sintético)
# ======================================================================

def test_main_run_shapes_and_accounting(main_run, md):
    res = main_run
    assert list(res.daily.columns) == DAILY_COLUMNS
    assert list(res.weekly.columns[: len(WEEKLY_COLUMNS)]) == WEEKLY_COLUMNS
    assert (res.weekly["status"] == "ok").all(), res.weekly["status"].tolist()
    assert res.weights.index.equals(res.weekly.index)
    assert res.daily.index[0] == res.weekly.index[0] == pd.Timestamp(START)
    assert res.daily.index[-1] == pd.Timestamp(AS_OF)
    assert all(pd.Timestamp(i).dayofweek == 0 for i in res.weekly.index)
    # Data de informação = pregão anterior da B3 ao rebalanceamento (1º pregão da semana).
    sess = primary_sessions(md, CFG)
    assert list(res.weekly.index) == list(rebalance_dates(sess, START, AS_OF))
    for t, d in res.weekly["info_date"].items():
        assert d == sess[sess < t][-1]
    d = res.daily
    ident = d["ret_gross"] - d["cost"] - d["borrow"] + d["financing"]
    np.testing.assert_allclose(d["ret_net"], ident, atol=1e-15)
    np.testing.assert_allclose(d["nav"], NAV0 * np.cumprod(1 + d["ret_net"]), rtol=1e-12)
    attr = d.dropna(subset=["factor_pnl"])
    assert len(attr) > 0.9 * len(d)
    np.testing.assert_allclose(attr["factor_pnl"] + attr["specific_pnl"], attr["ret_gross"],
                               atol=1e-15)
    assert (d.loc[~d["rebalance"], "cost"] == 0).all()
    assert res.is_synthetic and res.data_notice == "DADOS SIMULADOS"


def test_realized_pnl_is_previous_weights_times_returns(main_run, panel):
    res = main_run
    t0, t1 = res.daily.index[0], res.daily.index[1]
    w0 = res.weights.loc[t0]
    r1 = panel.returns.loc[t1, w0.index].fillna(0.0)
    assert res.daily.loc[t1, "ret_gross"] == pytest.approx(float(w0 @ r1), abs=1e-15)
    assert res.daily.loc[t0, "ret_gross"] == 0.0  # caixa antes da primeira carteira
    assert res.daily.loc[t0, "gross"] == pytest.approx(float(w0.abs().sum()))


def test_net_neutral_and_vol_within_target_every_rebalance(main_run, panel):
    wk = main_run.weekly
    net_max = CFG.risk.net_exposure_max_abs
    # Nomes com mercado fechado no dia não negociam: ficam no peso derivado w0/(1 + R_t), e o
    # líquido realizado difere do otimizado por −R_t·Σ w_congelados (exato, sem folga extra).
    d = main_run.daily
    for t in wk.index:
        w = main_run.weights.loc[t]
        frozen = panel.returns.loc[t, w.index].isna() & (w != 0)
        pre = float(d.loc[t, "ret_net"] + d.loc[t, "cost"])
        slack = abs(pre) * abs(float(w[frozen].sum()))
        assert abs(wk.loc[t, "net"]) <= net_max + 1e-6 + slack, t
        assert abs(float(w.sum())) <= net_max + 1e-6 + slack, t
    assert (wk["n_frozen"] > 0).any()  # o cenário inclui o México fechado (29/01/2024)
    vt = wk["vol_target"].iloc[0]
    assert vt == pytest.approx(CFG.risk.vol_target_annual / CFG.risk.bias_prior)
    assert (wk["ex_ante_vol"] <= vt * (1 + 1e-4)).all()
    assert (wk["ex_ante_vol"] > 0).all()
    assert (wk["gross"] <= CFG.risk.gross_max + 1e-9).all()
    assert (wk["n_long"] > 0).all() and (wk["n_short"] > 0).all()
    w = main_run.weights
    assert (w.max(axis=1) <= CFG.risk.max_long_weight + 1e-6).all()
    assert (w.min(axis=1) >= -CFG.risk.max_short_weight - 1e-6).all()


def test_costs_reduce_returns_in_engine(main_run):
    d, wk = main_run.daily, main_run.weekly
    traded = wk["turnover"] > 0
    assert (wk.loc[traded, "cost"] > 0).all()
    assert d.loc[wk.index, "cost"].to_numpy() == pytest.approx(wk["cost"].to_numpy())
    without_costs = float(np.prod(1 + d["ret_net"] + d["cost"]))
    assert float(np.prod(1 + d["ret_net"])) < without_costs
    assert main_run.metrics["cost_drag_annual"] > 0
    assert main_run.metrics["borrow_drag_annual"] > 0
    assert main_run.metrics["financing_annual"] > 0


def test_metrics_are_finite_and_consistent(main_run):
    m = main_run.metrics
    for k in ("ann_return", "ann_vol", "sharpe", "sortino", "max_drawdown", "hit_rate_weekly",
              "skew", "excess_kurtosis", "best_week", "worst_week", "psr",
              "deflated_sharpe", "avg_turnover_weekly", "avg_gross", "avg_ex_ante_vol",
              "final_nav", "factor_pnl_annual", "specific_pnl_annual"):
        assert math.isfinite(m[k]), k
    assert m["max_drawdown"] <= 0
    assert 0 <= m["hit_rate_weekly"] <= 1 and 0 <= m["psr"] <= 1
    assert m["n_rebalances"] == len(main_run.weekly)
    assert m["n_rebalance_failures"] == 0
    assert m["final_nav"] == pytest.approx(main_run.daily["nav"].iloc[-1])
    assert m["deflated_sharpe"] == pytest.approx(m["psr"])  # n_trials = 1


def test_notes_flag_biases_and_simulated_data(main_run):
    text = "\n".join(main_run.notes)
    assert "DADOS SIMULADOS" in text
    assert "Viés de sobrevivência" in text
    assert "viés otimista" in text
    assert "Sem camada de IA" in text


def test_planted_alpha_gives_positive_ic_for_pit_signal(main_run):
    ic = main_run.ic
    assert list(ic.columns) == ["residual_momentum", "short_term_reversal", "low_risk",
                                "composite"]
    assert ic.index.equals(main_run.weekly.index)
    stats = main_run.ic_stats
    assert stats.loc["residual_momentum", "n"] >= len(ic) - 1
    assert stats.loc["residual_momentum", "mean"] > 0
    assert stats.loc["residual_momentum", "t_stat"] > 1.5
    assert main_run.metrics["ic_mean:residual_momentum"] == pytest.approx(
        stats.loc["residual_momentum", "mean"])


def test_no_lookahead_altering_future_does_not_change_past(main_run, altered_run):
    base, alt = main_run, altered_run
    past = base.weekly.index[base.weekly.index <= CUTOFF]
    assert len(past) >= 3
    cols = base.weights.columns.union(alt.weights.columns)
    wb = base.weights.reindex(columns=cols, fill_value=0.0)
    wa = alt.weights.reindex(columns=cols, fill_value=0.0)
    pd.testing.assert_frame_equal(wa.loc[past], wb.loc[past], check_exact=True)
    num = ["ex_ante_vol", "gross", "net", "beta", "turnover", "cost", "expected_alpha"]
    pd.testing.assert_frame_equal(alt.weekly.loc[past, num], base.weekly.loc[past, num],
                                  check_exact=True)
    dpast = base.daily.index[base.daily.index <= CUTOFF]
    pd.testing.assert_frame_equal(alt.daily.loc[dpast], base.daily.loc[dpast],
                                  check_exact=True)
    # O futuro alterado de fato muda a primeira decisão posterior ao corte.
    after = alt.weekly.index[alt.weekly.index > CUTOFF][0]
    assert not np.allclose(wa.loc[after], wb.loc[after])


def test_match_mode_uses_the_risk_budget(md):
    # Modo padrão do motor; uma única semana (inception) porque o modo "match" resolve o
    # problema várias vezes por rebalanceamento.
    res = run_backtest(md, CFG, BacktestConfig(start=START, end=date(2023, 12, 8)))
    wk = res.weekly
    vt = CFG.risk.vol_target_annual / CFG.risk.bias_prior
    assert (wk["status"] == "ok").all()
    assert (wk["ex_ante_vol"] <= vt * (1 + 1e-4)).all()
    # A meta só é perseguida enquanto o alpha paga os custos; nunca abaixo do piso da banda.
    assert (wk["ex_ante_vol"] >= 0.97 * CFG.risk.vol_band_min).all()
    assert (wk["alpha_scale"] >= 1.0).all()
    assert (wk["net"].abs() <= CFG.risk.net_exposure_max_abs + 1e-6).all()
    assert "modo 'match'" in "\n".join(res.notes)


def test_engine_pnl_matches_independent_replay_without_frictions(md, panel):
    calls: list[tuple[int, int, str]] = []
    bt = BacktestConfig(start=START, end=date(2023, 12, 15), risk_target_mode="cap",
                        include_costs=False, include_borrow=False, include_financing=False)
    res = run_backtest(md, CFG, bt, progress=lambda a, b, m: calls.append((a, b, m)))
    assert [c[0] for c in calls] == [1, 2] and all(c[1] == 2 for c in calls)
    d = res.daily
    assert (d[["cost", "borrow", "financing"]] == 0).all().all()
    rets = panel.returns.loc[d.index]
    rep = simulate_weights(rets, res.weights, nav=NAV0)
    np.testing.assert_allclose(rep["ret_gross"], d["ret_gross"], atol=1e-14)
    np.testing.assert_allclose(rep["nav"], d["nav"], rtol=1e-12)
    np.testing.assert_allclose(rep["gross"], d["gross"], atol=1e-12)
    text = "\n".join(res.notes)
    assert "include_costs=False" in text and "include_financing=False" in text


def test_insufficient_history_holds_cash_with_status(md):
    res = run_backtest(md, CFG, BacktestConfig(start=date(2023, 3, 20), end=date(2023, 4, 7),
                                               risk_target_mode="cap"))
    st = res.weekly["status"].tolist()
    assert st and all(s == "manter:sem_modelo" for s in st)
    assert res.weights.shape[1] == 0  # nunca investiu
    assert (res.daily["ret_gross"] == 0).all()
    np.testing.assert_allclose(res.daily["ret_net"], res.daily["financing"], atol=1e-15)
    assert (res.daily["financing"] > 0).all()
    assert res.metrics["n_rebalance_failures"] == len(st)
    assert any("modelo de risco indisponível" in n for n in res.notes)


def test_too_few_eligible_issuers_holds(md):
    cfg = CFG.with_overrides({"liquidity": {"min_adtv_usd": 1e15}})
    # Fim num sábado: o backtest vai até o último pregão anterior.
    res = run_backtest(md, cfg, BacktestConfig(start=START, end=date(2023, 12, 9),
                                               risk_target_mode="cap"))
    assert res.daily.index[-1] == pd.Timestamp("2023-12-08")
    assert res.weekly["status"].tolist() == ["manter:poucos_elegiveis"]
    assert res.weekly["n_eligible"].iloc[0] == 0
    assert res.weekly["ex_ante_vol"].iloc[0] == 0.0  # carteira vazia mantida
    assert res.weights.shape[1] == 0


def test_optimizer_failure_holds_previous_weights(md, monkeypatch):
    real = eng.optimize
    n_calls = {"n": 0}

    def flaky(*args, **kwargs):
        n_calls["n"] += 1
        if n_calls["n"] >= 2:
            raise OptimizationError("falha simulada", relaxations=["turnover"])
        return real(*args, **kwargs)

    monkeypatch.setattr(eng, "optimize", flaky)
    res = run_backtest(md, CFG, BacktestConfig(start=START, end=date(2023, 12, 15),
                                               risk_target_mode="cap"))
    wk = res.weekly
    assert wk["status"].tolist() == ["ok", "manter:falha_otimizador"]
    t1 = wk.index[1]
    assert wk.loc[t1, "turnover"] == 0.0 and wk.loc[t1, "cost"] == 0.0
    assert wk.loc[t1, "relaxations"] == "turnover"
    assert math.isfinite(wk.loc[t1, "ex_ante_vol"])
    # Carteira mantida = pesos derivados (mesmos sinais e nomes, valores ligeiramente diferentes).
    w0, w1 = res.weights.iloc[0], res.weights.iloc[1]
    assert ((w0 != 0) == (w1 != 0)).all()
    assert np.sign(w0).equals(np.sign(w1))
    assert any("otimização falhou" in n for n in res.notes)


def test_snapshot_entry_point_wires_loader_and_config(md, monkeypatch, tmp_path):
    """O atalho de dados reais carrega o snapshot (verificado) e roda o mesmo motor."""
    seen: dict = {}

    def load_snapshot(path, verify=True):
        seen["path"], seen["verify"] = Path(path), verify
        return md

    fake = types.ModuleType("cdp.data.snapshot")
    fake.load_snapshot = load_snapshot
    fake.latest_snapshot = lambda root=None: tmp_path
    monkeypatch.setitem(sys.modules, "cdp.data.snapshot", fake)
    res = eng.run_snapshot_backtest(None, config_path=str(CFG_PATH), start=START,
                                    end=date(2023, 12, 8), risk_target_mode="cap",
                                    include_costs=False)
    assert seen == {"path": tmp_path, "verify": True}
    assert len(res.weekly) == 1 and res.weekly["status"].iloc[0] == "ok"
    assert res.config.include_costs is False
    fake.latest_snapshot = lambda root=None: None
    with pytest.raises(FileNotFoundError):
        eng.run_snapshot_backtest(None, config_path=str(CFG_PATH))


def test_package_exports_are_lazy_and_complete():
    import cdp.backtest as bt_pkg

    assert bt_pkg.run_backtest is run_backtest
    assert bt_pkg.performance_metrics is performance_metrics
    with pytest.raises(AttributeError):
        _ = bt_pkg.nao_existe
