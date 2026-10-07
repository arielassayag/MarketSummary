"""Risco macro/base no backtest: petróleo plantado, PIT e atribuição (DADOS SIMULADOS)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cdp.analytics.panel import build_asset_panel
from cdp.backtest import engine as eng
from cdp.config import load_config
from cdp.data.synthetic import make_synthetic_market
from cdp.risk.model import RiskModelEstimator


@pytest.fixture(scope="module")
def env():
    cfg = load_config(Path(__file__).parent / "fixtures/fund_legado.yaml").with_overrides({
        "risk_model": {"macro_factors": ["BZ=F", "XX=F"]},
        "risk": {
            "max_factor_risk_share": 0.10, "idio_share_goal": 0.90,
            "idio_share_floor": 0.85, "factor_risk_basis": "achieved",
            "factor_risk_aversion_multiplier": 5.0, "second_order_inflation": 1.45,
            "idio_gate_models": ["decisao", "base"], "vol_floor_alpha_scaling": False,
            "event_windows": [{"name": "Evento simulado BR", "country": "BR",
                               "start": "2023-12-01", "end": "2023-12-31",
                               "vol_multiplier": 1.5}],
        },
    })
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=date(2023, 12, 22),
                               planted_alpha=0.003)
    rng = np.random.default_rng(30)
    oil = rng.normal(0, 0.025, len(md.close))
    # Exposições diferentes dentro de país/setor: o petróleo continua no resíduo da WLS.
    beta = dict(zip(md.universe.issuers.index,
                    rng.uniform(-0.8, 0.8, len(md.universe.issuers)), strict=True))
    close, adj = md.close.copy(), md.adj_close.copy()
    for ticker, line in md.universe.lines.iterrows():
        multiplier = np.cumprod(1 + beta[line["issuer_id"]] * oil)
        close[ticker] *= multiplier
        adj[ticker] *= multiplier
    md = replace(md, close=close, adj_close=adj,
                 benchmarks=md.benchmarks.assign(**{"BZ=F": 80 * np.cumprod(1 + oil)}))
    bt = eng.BacktestConfig(start=date(2023, 12, 4), end=date(2023, 12, 15),
                            risk_target_mode="cap", include_costs=False,
                            include_borrow=False, include_financing=False)
    panel = build_asset_panel(md, cfg)
    res, decisions, models = _run(md, cfg, bt)
    return md, cfg, bt, panel, res, decisions, models


def _run(md, cfg, bt):
    """Observa modelos/decisões reais; não substitui o solver nem a contabilidade."""
    decisions, models = {}, {}
    real_decide, real_optimize = eng._decide, eng.optimize

    def optimize(alpha, model, *args, **kwargs):
        models[pd.Timestamp(model.as_of)] = (model, kwargs["model_base"], kwargs["kappa_f"])
        return real_optimize(alpha, model, *args, **kwargs)

    def decide(ctx, t, *args, **kwargs):
        dec = real_decide(ctx, t, *args, **kwargs)
        decisions[t] = dec
        return dec

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(eng, "optimize", optimize)
        mp.setattr(eng, "_decide", decide)
        res = eng.run_backtest(md, cfg, bt)
    return res, decisions, models


def _estimator(md, cfg, bt, panel, res):
    cal = panel.returns.index
    pos = int(cal.get_loc(res.weekly["info_date"].iloc[0]))
    ids = [i for i in panel.assets.index if panel.returns[i].loc[:str(bt.end)].notna().any()]
    return RiskModelEstimator(panel, cfg, md=md, issuers=ids,
                              start=cal[max(1, pos - cfg.risk_model.history_days + 1)],
                              end=pd.Timestamp(bt.end),
                              exposure_refresh_days=bt.exposure_refresh_days)


def _joint_returns(md, estimator):
    # Os fatores transversais inativos são zero por convenção da regressão identificada;
    # o petróleo é uma série independente observada, sem preenchimento de dados ausentes.
    fr = estimator.factor_returns_all.fillna(0.0).copy()
    fr["macro:BZ=F"] = md.benchmarks["BZ=F"].pct_change(fill_method=None).reindex(fr.index)
    return fr


def _share(w, model, kappa):
    x = model.exposures.T @ w.reindex(model.assets, fill_value=0.0)
    fvar = kappa * float(x @ model.factor_cov @ x)
    svar = float((w.reindex(model.assets, fill_value=0.0) ** 2 * model.specific_var).sum())
    return svar / (fvar + svar)


def test_macro_moves_risk_out_of_specific_and_both_gate_models_are_measured(env):
    md, cfg, bt, panel, res, _decisions, models = env
    estimator = _estimator(md, cfg, bt, panel, res)
    assert (res.weekly["status"] == "ok").all() and (res.weekly["gross"] > 0).all()
    for t, row in res.weekly.iterrows():
        decision, base, kappa = models[row["info_date"]]
        original = estimator.model_at(row["info_date"])
        assert base.factor_returns.index.max() <= row["info_date"]
        assert base.meta["macro"]["ativo"] and base.meta["macro"]["ausentes"] == ["XX=F"]
        assert "event_windows" not in base.meta and decision.meta["event_windows"]
        # Macro não duplica o bloco original nem mantém a parte explicada em D.
        pd.testing.assert_frame_equal(base.factor_cov.loc[original.factor_names,
                                                         original.factor_names],
                                      original.factor_cov)
        assert base.exposures["macro:BZ=F"].abs().mean() > 0.05
        assert base.specific_var.mean() < original.specific_var.mean()
        assert (base.specific_var >= 0.5 * original.specific_var - 1e-12).all()
        br = panel.assets["country"].reindex(base.assets) == "BR"
        np.testing.assert_allclose(decision.specific_var[br], base.specific_var[br] * 1.5 ** 2)
        w = res.weights.loc[t]
        assert row["ex_ante_vol"] == pytest.approx(decision.portfolio_vol(w), abs=1e-8)
        assert row["ex_ante_vol_base"] == pytest.approx(base.portfolio_vol(w), abs=1e-8)
        assert row["ex_ante_vol"] > row["ex_ante_vol_base"]
        assert kappa == row["kappa_f"] == 1.45 and row["kappa_source"] == "config"
        for name, model in (("decisao", decision), ("base", base)):
            share = _share(w, model, kappa)
            # O loop zera resíduos numéricos de pesos em linhas sem negócio no dia.
            assert row[f"idio_{name}"] == pytest.approx(share, abs=1e-6)
            assert share >= cfg.risk.idio_share_floor - 1e-6
        assert row["idio_share_goal"] == cfg.risk.idio_share_goal
        assert row["idio_share_floor"] == cfg.risk.idio_share_floor
        assert abs(w.sum()) <= cfg.risk.net_exposure_max_abs + 1e-6
        assert row["ex_ante_vol"] <= bt.effective_vol_target(cfg) + 1e-6


def test_daily_attribution_and_forward_ic_include_the_observed_macro_return(env):
    md, cfg, bt, panel, res, decisions, models = env
    joint = _joint_returns(md, _estimator(md, cfg, bt, panel, res))
    w = pd.Series(0.0, index=panel.assets.index)
    active = None
    macro_pnl = []
    for t, row in res.daily.iterrows():
        if active is None:
            expected = 0.0
        else:
            exposures = active.exposures.T @ w.reindex(active.assets, fill_value=0.0)
            f = joint.loc[t, active.factor_names]
            expected = float(exposures @ f)
            macro_pnl.append(float(exposures["macro:BZ=F"] * f["macro:BZ=F"]))
        assert row["factor_pnl"] == pytest.approx(expected, abs=1e-12)
        assert row["specific_pnl"] + row["factor_pnl"] == pytest.approx(row["ret_gross"])
        r = panel.returns.loc[t].fillna(0.0)  # apenas marcação de posição em mercado fechado
        w = w * (1 + r) / (1 + row["ret_gross"])
        if t in res.weekly.index:
            w = res.weights.loc[t].reindex(w.index, fill_value=0.0)
            active = models[res.weekly.loc[t, "info_date"]][0]
    assert max(abs(x) for x in macro_pnl) > 1e-6  # omitir macro mudaria a atribuição

    dates = list(res.weekly.index)
    for k, t in enumerate(dates):
        dec = decisions[t]
        end = dates[k + 1] if k + 1 < len(dates) else res.daily.index[-1]
        f = joint.loc[(joint.index > t) & (joint.index <= end), dec.model.factor_names]
        # IC de rank calculado diretamente, sem chamar o helper de IC do motor.
        predicted = f @ dec.model.exposures.T
        forward = (panel.returns.reindex(predicted.index)[predicted.columns] - predicted).sum(
            min_count=1)
        expected = dec.alpha.corr(forward.reindex(dec.alpha.index), method="spearman")
        assert res.ic.loc[t, "composite"] == pytest.approx(expected, abs=1e-12)


def test_future_macro_prices_or_a_late_factor_do_not_change_past_decisions(env):
    md, cfg, bt, _panel, res, _decisions, models = env
    benchmarks = md.benchmarks.copy()
    future = benchmarks.index > pd.Timestamp("2023-12-08")
    benchmarks.loc[future, "BZ=F"] *= np.linspace(2.0, 4.0, int(future.sum()))
    benchmarks["XX=F"] = np.nan
    benchmarks.loc[future, "XX=F"] = np.linspace(20, 40, int(future.sum()))
    altered, _decs, alternate_models = _run(replace(md, benchmarks=benchmarks), cfg, bt)
    pd.testing.assert_frame_equal(res.weekly, altered.weekly)
    pd.testing.assert_frame_equal(res.weights, altered.weights)
    for d in models:
        for idx in (0, 1):
            old, new = models[d][idx], alternate_models[d][idx]
            pd.testing.assert_frame_equal(old.exposures, new.exposures)
            pd.testing.assert_frame_equal(old.factor_cov, new.factor_cov)
            pd.testing.assert_series_equal(old.specific_var, new.specific_var)
    assert not res.daily["factor_pnl"].equals(altered.daily["factor_pnl"])


def test_missing_macro_return_is_not_zero_in_attribution_or_forward_ic(env):
    md, cfg, bt, panel, _res, _decisions, _models = env
    benchmarks = md.benchmarks.copy()
    benchmarks.loc["2023-12-06", "BZ=F"] = np.nan
    missing = replace(md, benchmarks=benchmarks)
    res, decisions, _models = _run(missing, cfg, bt)
    absent = pd.to_datetime(["2023-12-06", "2023-12-07"])
    assert res.daily.loc[absent, ["factor_pnl", "specific_pnl"]].isna().all().all()
    assert res.metrics["n_days_without_attribution"] >= len(absent)
    assert any("retorno macro do dia ausente" in note for note in res.notes)
    joint = _joint_returns(missing, _estimator(missing, cfg, bt, panel, res))
    t, end = res.weekly.index[:2]
    dec = decisions[t]
    f = joint.loc[(joint.index > t) & (joint.index <= end), dec.model.factor_names].dropna()
    assert set(absent).isdisjoint(f.index)
    predicted = f @ dec.model.exposures.T
    forward = (panel.returns.reindex(predicted.index)[predicted.columns] - predicted).sum(
        min_count=1)
    expected = dec.alpha.corr(forward.reindex(dec.alpha.index), method="spearman")
    assert res.ic.loc[t, "composite"] == pytest.approx(expected, abs=1e-12)
