"""Revisão adversarial do backtest: casos que expõem erros de calendário, look-ahead e métricas.

DADOS SIMULADOS, offline. Os backtests aqui são curtos (2–3 semanas, modo ``cap``) para manter o
arquivo rápido.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cdp.analytics.panel import build_asset_panel
from cdp.backtest.engine import (
    BacktestConfig,
    PointInTimeInputs,
    primary_sessions,
    rebalance_dates,
    results_hash,
    rf_daily_series,
    run_backtest,
    simulate_weights,
    summary_metrics,
)
from cdp.backtest.metrics import deflated_sharpe_ratio, performance_metrics
from cdp.config import load_config
from cdp.data.synthetic import make_synthetic_market
from cdp.risk.event_scaling import apply_event_windows
from cdp.risk.model import RiskModelEstimator

CFG_PATH = Path(__file__).resolve().parents[2] / "configs" / "cdp" / "fund.yaml"
CFG = load_config(CFG_PATH)
B3_HOLIDAY_MONDAY = pd.Timestamp("2023-09-11")   # feriado só na B3 no mercado sintético
MX_CLOSED_MONDAY = pd.Timestamp("2024-01-29")    # México fechado; B3 aberta


@pytest.fixture(scope="module")
def md():
    return make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=date(2024, 2, 23),
                                 planted_alpha=0.003)


@pytest.fixture(scope="module")
def panel(md):
    return build_asset_panel(md, CFG)


@pytest.fixture(scope="module")
def theme_members(md):
    iss = md.universe.issuers
    return sorted(iss.index[iss["country"] == "BR"][:8])


@pytest.fixture(scope="module")
def mx_run(md, theme_members):
    """Três semanas com o México fechado na última segunda; tema neutro sintético."""
    bt = BacktestConfig(start=date(2024, 1, 15), end=date(2024, 2, 2), risk_target_mode="cap",
                        themes={"state_owned": theme_members})
    return run_backtest(md, CFG, bt)


# ======================================================================
# Calendário: primeiro pregão da B3 (regra do mandato) e data de informação
# ======================================================================

def test_primary_sessions_follow_b3_trading_days(md):
    sess = primary_sessions(md, CFG)
    cal = md.close.index
    assert B3_HOLIDAY_MONDAY in cal and B3_HOLIDAY_MONDAY not in sess
    assert MX_CLOSED_MONDAY in sess  # outro mercado fechado não muda o calendário da B3
    # A linha defasada (sem preço nos 10 últimos pregões) não transforma pregões em feriados.
    assert sess[-1] == cal[-1]
    reb = rebalance_dates(sess, date(2023, 9, 4), date(2023, 9, 15))
    assert list(reb) == [pd.Timestamp("2023-09-04"), pd.Timestamp("2023-09-12")]


def test_rebalance_moves_to_first_b3_session_when_monday_is_b3_holiday(md):
    res = run_backtest(md, CFG, BacktestConfig(start=date(2023, 9, 4), end=date(2023, 9, 15),
                                               risk_target_mode="cap"))
    wk = res.weekly
    # Segunda 11/09 é feriado na B3: a carteira é montada na terça 12/09 com dados até 08/09.
    assert list(wk.index) == [pd.Timestamp("2023-09-04"), pd.Timestamp("2023-09-12")]
    assert wk.loc["2023-09-12", "info_date"] == pd.Timestamp("2023-09-08")
    assert not bool(res.daily.loc[B3_HOLIDAY_MONDAY, "rebalance"])
    # O P&L do feriado da B3 continua sendo contabilizado (ADRs negociam em NY).
    assert B3_HOLIDAY_MONDAY in res.daily.index


# ======================================================================
# Mercado da linha primária fechado no rebalanceamento: sem negociação nesses nomes
# ======================================================================

def test_names_with_closed_market_are_not_traded_on_rebalance_day(mx_run, panel):
    res = mx_run
    assert MX_CLOSED_MONDAY in res.weekly.index
    prev_t = res.weekly.index[res.weekly.index < MX_CLOSED_MONDAY][-1]
    closed = panel.returns.columns[panel.returns.loc[MX_CLOSED_MONDAY].isna()]
    held = [i for i in closed if i in res.weights.columns and res.weights.loc[prev_t, i] != 0]
    assert held, "o cenário precisa de nomes mexicanos em carteira"
    # Peso derivado independente: w_t = w_{t-1}(1 + r)/(1 + R_pré), R_pré = ret_net + custo.
    d = res.daily
    days = d.index[(d.index > prev_t) & (d.index <= MX_CLOSED_MONDAY)]
    pre = (d["ret_net"] + d["cost"]).loc[days]
    for i in held:
        r = panel.returns.loc[days, i].fillna(0.0)
        drifted = res.weights.loc[prev_t, i] * float(np.prod((1 + r) / (1 + pre)))
        assert res.weights.loc[MX_CLOSED_MONDAY, i] == pytest.approx(drifted, rel=1e-12)
    # Candidatos fechados também não abrem posição no dia.
    not_held = [i for i in closed if i not in held]
    if not_held:
        w = res.weights.reindex(columns=not_held, fill_value=0.0).loc[MX_CLOSED_MONDAY]
        assert (w == 0).all()
    assert res.weekly.loc[MX_CLOSED_MONDAY, "n_frozen"] >= len(held)
    assert any("mercado da linha primária fechado" in n for n in res.notes)


def test_reported_ex_ante_vol_matches_independent_model(mx_run, md, panel):
    """Vol ex-ante e beta recalculados com um estimador independente batem com o relatório."""
    res = mx_run
    n_est = int(res.provenance["n_estimation_issuers"])
    issuers = [i for i in panel.assets.index if panel.returns[i].loc[:"2024-02-02"].notna().any()]
    assert len(issuers) == n_est
    first_info = res.weekly["info_date"].iloc[0]
    pos = int(panel.returns.index.get_loc(first_info))
    est = RiskModelEstimator(panel, CFG, md=md, issuers=issuers,
                             start=panel.returns.index[max(1, pos - CFG.risk_model.history_days
                                                           + 1)],
                             end=pd.Timestamp("2024-02-02"))
    vt = CFG.risk.vol_target_annual / CFG.risk.bias_prior
    for t, row in res.weekly.iterrows():
        model = apply_event_windows(est.model_at(row["info_date"]), panel.assets["country"],
                                    CFG, t.date())
        w = res.weights.loc[t]
        w = w[w != 0]
        vol = model.portfolio_vol(w)
        assert vol == pytest.approx(row["ex_ante_vol"], rel=1e-3, abs=1e-6)
        assert vol <= vt * (1 + 1e-3)
        assert abs(w.sum()) <= CFG.risk.net_exposure_max_abs + 1e-4


def test_theme_neutrality_is_enforced(mx_run, theme_members):
    limit = CFG.risk.theme_net_max_abs["state_owned"]
    w = mx_run.weights.reindex(columns=theme_members, fill_value=0.0)
    assert (w.abs().sum(axis=1) > 0).any()  # o tema tem posições
    assert (w.sum(axis=1).abs() <= limit + 1e-6).all()
    assert any("state_owned" in n for n in mx_run.notes)


def test_borrow_and_financing_accrue_on_previous_close_book(mx_run, md):
    """Aluguel = taxa GC/252 sobre os shorts do fechamento anterior; juros = USD_3M/252 sobre o
    caixa (1 − líquido) do fechamento anterior (verificação independente do livro)."""
    d = mx_run.daily
    sh = CFG.shorting
    short_prev = ((d["gross"] - d["net"]) / 2).shift(1).iloc[1:]
    fee_annual = (d["borrow"].iloc[1:] / short_prev * 252)[short_prev > 0]
    assert len(fee_annual) > 5
    # Sem dado PIT de aluguel: só taxas GC (US 0,3% a.a.; BR 0,8% a.a.) ou a máxima do mandato.
    lo, hi = sh.gc_borrow_fee_us, max(sh.gc_borrow_fee_br, sh.max_borrow_fee)
    assert ((fee_annual >= lo - 1e-12) & (fee_annual <= hi + 1e-12)).all()
    rate = float(md.rates["USD_3M"].iloc[0])
    expected = (1.0 - d["net"].shift(1).iloc[1:]) * rate / 252
    np.testing.assert_allclose(d["financing"].iloc[1:], expected, rtol=1e-12)
    assert d["financing"].iloc[0] == pytest.approx(rate / 252)  # 1º dia: só caixa


# ======================================================================
# Proveniência (hash dos dados, da configuração e dos resultados)
# ======================================================================

def test_provenance_hashes_detect_tampering(mx_run, md):
    prov = mx_run.provenance
    assert prov["data_hash"] == md.manifest.content_hash()
    assert prov["config_hash"] == CFG.config_hash()
    assert prov["data_notice"] == "DADOS SIMULADOS"
    assert prov["backtest_config"]["start"] == "2024-01-15"
    h = results_hash(mx_run.daily, mx_run.weekly, mx_run.weights, mx_run.ic)
    assert h == prov["results_hash"]
    tampered = mx_run.daily.copy()
    tampered.iloc[3, 0] += 1e-6
    assert results_hash(tampered, mx_run.weekly, mx_run.weights, mx_run.ic) != h


# ======================================================================
# Métricas agregadas do motor
# ======================================================================

def test_avg_turnover_excludes_actual_inception_after_hold_weeks(md):
    # Início antes de haver modelo/elegíveis: semanas em caixa e só depois a montagem real.
    res = run_backtest(md, CFG, BacktestConfig(start=date(2023, 6, 26), end=date(2023, 7, 21),
                                               risk_target_mode="cap"))
    wk = res.weekly
    assert wk["status"].iloc[0].startswith("manter:")
    first_invested = wk.index[wk["gross"] > 0][0]
    assert first_invested != wk.index[0]
    assert wk.loc[first_invested, "turnover"] == pytest.approx(wk.loc[first_invested, "gross"])
    after = wk.index > first_invested
    assert after.any()
    # A montagem (turnover = gross) não entra na média de turnover semanal.
    assert res.metrics["avg_turnover_weekly"] == pytest.approx(wk.loc[after, "turnover"].mean())
    assert wk.loc[first_invested, "turnover"] > res.metrics["avg_turnover_weekly"]


def _toy_frames(n_nan_attr: int = 0):
    idx = pd.bdate_range("2024-01-01", periods=10)
    daily = pd.DataFrame({
        "ret_net": 0.001, "ret_gross": 0.0012, "cost": 0.0, "borrow": 0.0001,
        "financing": 0.0, "factor_pnl": 0.0002, "specific_pnl": 0.001, "nav": 1.0,
        "gross": 2.0, "net": 0.0, "rebalance": False,
    }, index=idx)
    daily.iloc[:n_nan_attr, daily.columns.get_loc("factor_pnl")] = np.nan
    daily.iloc[:n_nan_attr, daily.columns.get_loc("specific_pnl")] = np.nan
    weekly = pd.DataFrame({"status": ["ok", "ok"], "turnover": [2.0, 0.2], "gross": [2.0, 2.0],
                           "ex_ante_vol": [0.04, 0.045], "relaxations": ["", ""]},
                          index=idx[[0, 5]])
    ic = pd.DataFrame({"residual_momentum": [0.1, 0.2]}, index=idx[[0, 5]])
    return daily, weekly, ic


def test_attribution_annualized_over_days_with_attribution_only():
    daily, weekly, ic = _toy_frames(n_nan_attr=4)
    bt = BacktestConfig(start=date(2024, 1, 1))
    m = summary_metrics(daily, weekly, ic, None, CFG, bt, 0.045)
    # Dias sem atribuição (NaN) não entram como zero na média anualizada.
    assert m["factor_pnl_annual"] == pytest.approx(0.0002 * 252)
    assert m["specific_pnl_annual"] == pytest.approx(0.001 * 252)
    assert m["n_days_without_attribution"] == 4
    assert m["avg_turnover_weekly"] == pytest.approx(0.2)


# ======================================================================
# Utilitários: juros, réplica de pesos, PIT e métricas
# ======================================================================

def test_rate_in_percent_is_rejected(md):
    pct = dataclasses.replace(md, rates=md.rates.assign(USD_3M=4.0))
    with pytest.raises(ValueError, match="decimal"):
        rf_daily_series(pct, md.close.index)


def test_simulate_weights_rate_series_checked_on_simulated_days_only():
    idx = pd.bdate_range("2024-01-01", periods=6)
    rets = pd.DataFrame({"A": [0.0, 0.01, 0.0, 0.02, -0.01, 0.0]}, index=idx)
    targets = pd.DataFrame({"A": [0.5]}, index=idx[[2]])
    rf = pd.Series([np.nan, 0.04, 0.04, 0.04, 0.04, 0.04], index=idx)
    out = simulate_weights(rets, targets, rf_annual=rf)  # NaN antes do início não importa
    assert out["financing"].iloc[0] == pytest.approx(0.04 / 252)
    # Sem taxa do pregão anterior no primeiro dia simulado: erro, nunca juro zero silencioso.
    early = pd.DataFrame({"A": [0.5]}, index=idx[[0]])
    with pytest.raises(ValueError, match="Taxa de juros ausente"):
        simulate_weights(rets, early, rf_annual=rf)


def test_pit_eligibility_does_not_use_end_of_sample_eligibility(md, panel):
    stale = md.universe.issuers.index[5]
    assert not bool(panel.assets.loc[stale, "eligible"])  # inelegível só no fim da amostra
    pit = PointInTimeInputs(panel, md, CFG)
    pos = int(pit.calendar.get_loc(pd.Timestamp("2023-12-01")))
    assert bool(pit.assets_at(pos).loc[stale, "eligible"])


def test_provisional_bars_are_excluded(md):
    last = md.close.index[-1].date()
    prov = md.manifest.model_copy(update={"provisional_dates": [last]})
    md_prov = dataclasses.replace(md, manifest=prov)
    res = run_backtest(md_prov, CFG, BacktestConfig(start=date(2024, 2, 19),
                                                    risk_target_mode="cap"))
    assert res.daily.index[-1] < pd.Timestamp(last)
    assert any("provisória" in n for n in res.notes)


def test_vol_band_is_validated_even_for_short_series():
    r = pd.Series([0.001, -0.002, 0.003], index=pd.bdate_range("2024-01-01", periods=3))
    with pytest.raises(ValueError):
        performance_metrics(r, vol_band_min=0.07, vol_band_max=0.03)


def test_config_rejects_boolean_weights_and_string_theme_members():
    with pytest.raises(ValueError, match="Peso inválido"):
        BacktestConfig(start=date(2024, 1, 1), signal_weights={"residual_momentum": True})
    with pytest.raises(ValueError, match="tema"):
        BacktestConfig(start=date(2024, 1, 1), themes={"state_owned": "SIM001"})
    ok = BacktestConfig(start=date(2024, 1, 1), signal_weights={"low_risk": np.float64(2.0)},
                        signal_names=("low_risk",))
    assert ok.effective_signal_weights(CFG) == {"low_risk": 1.0}


def test_all_package_exports_resolve():
    import cdp.backtest as bt_pkg

    for name in bt_pkg.__all__:
        assert getattr(bt_pkg, name) is not None, name


def test_deflated_sharpe_matches_bailey_lopez_de_prado_example():
    """Exemplo numérico do artigo (2014): SR anual 2,5; T = 1250; N = 100; V[SR] = 0,5;
    assimetria −3; curtose 10 ⇒ DSR ≈ 0,9004 (anualização com 250 pregões)."""
    dsr = deflated_sharpe_ratio(2.5, 1250, 100, -3.0, 10.0, sharpe_trials_std=math.sqrt(0.5),
                                kurtosis_is_excess=False, periods_per_year=250)
    assert dsr == pytest.approx(0.9004, abs=2e-3)
