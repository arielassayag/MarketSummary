"""Regressões F05–F08 com DADOS SIMULADOS, sem rede ou livro operacional."""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cdp.alpha.views import final_view_sign, view_constraints, view_tilt_table
from cdp.config import FundConfig
from cdp.contracts import View, ViewSource
from cdp.research import evaluate_golden_set
from cdp.research.providers import DemoResearchProvider
from cdp.risk.analytics import parametric_var_es, risk_decomposition
from cdp.risk.idio import MIN_GL_SEM_MODELO, _regressao_sem_modelo, banda_sem_modelo
from cdp.risk.types import RiskModel


@pytest.fixture
def small_model():
    return RiskModel(
        as_of=date(2026, 10, 2),
        exposures=pd.DataFrame({"market": [1.0, 1.0]}, index=["A", "B"]),
        factor_cov=pd.DataFrame([[0.04]], index=["market"], columns=["market"]),
        specific_var=pd.Series({"A": 0.01, "B": 0.01}),
        factor_returns=pd.DataFrame(columns=["market"], dtype=float),
        specific_returns=pd.DataFrame(columns=["A", "B"], dtype=float),
        factor_groups={"market": "market"},
    )


def _risk_call(api, model, weights):
    if api == "variance":
        return model.portfolio_variance(weights)
    if api == "vol":
        return model.portfolio_vol(weights)
    if api == "decomposition":
        return risk_decomposition(weights, model)
    return parametric_var_es(weights, model)


def test_f05_held_missing_specific_is_refused(small_model):
    broken = replace(small_model, specific_var=pd.Series({"B": 0.01}))
    with pytest.raises(ValueError, match="específica"):
        broken.portfolio_vol(pd.Series({"A": 1.0, "B": 0.0}))


@pytest.mark.parametrize("api", ["variance", "vol", "decomposition", "var_es"])
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, -0.01])
def test_f05_invalid_specific_refused_on_every_risk_api(small_model, api, bad):
    specific = small_model.specific_var.copy()
    specific["A"] = bad
    broken = replace(small_model, specific_var=specific)
    with pytest.raises(ValueError, match="específica"):
        _risk_call(api, broken, pd.Series({"A": 1.0, "B": 0.0}))


@pytest.mark.parametrize("api", ["variance", "vol", "decomposition", "var_es"])
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, -0.01, None])
def test_f05_zero_weight_specific_does_not_change_held_risk(small_model, api, bad):
    weights = pd.Series({"A": 1.0, "B": 0.0})
    specific = (
        small_model.specific_var.drop("B") if bad is None else pd.Series({"A": 0.01, "B": bad})
    )
    broken = replace(small_model, specific_var=specific)
    got = _risk_call(api, broken, weights)
    reference = _risk_call(api, small_model, weights)
    if api == "decomposition":
        assert got.total_vol == reference.total_vol
        assert got.factor_vol == reference.factor_vol
        assert got.specific_vol == reference.specific_vol
        pd.testing.assert_series_equal(got.asset_contrib, reference.asset_contrib)
    else:
        assert got == reference


@pytest.mark.parametrize("part", ["B", "F"])
@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_f05_held_nonfinite_exposure_or_covariance_refused(small_model, part, bad):
    if part == "B":
        B = small_model.exposures.copy()
        B.loc["A", "market"] = bad
        broken = replace(small_model, exposures=B)
    else:
        F = small_model.factor_cov.copy()
        F.loc["market", "market"] = bad
        broken = replace(small_model, factor_cov=F)
    with pytest.raises(ValueError):
        risk_decomposition(pd.Series({"A": 1.0}), broken)


@pytest.mark.parametrize(
    "part", ["weights", "B_index", "B_columns", "D_index", "F_index", "F_columns", "F_missing"]
)
def test_f05_ambiguous_or_unaligned_labels_refused(small_model, part):
    weights = pd.Series({"A": 1.0})
    broken = small_model
    if part == "weights":
        weights = pd.Series([0.5, 0.5], index=["A", "A"])
    elif part == "B_index":
        broken = replace(small_model, exposures=small_model.exposures.set_axis(["A", "A"]))
    elif part == "B_columns":
        broken = replace(small_model, exposures=pd.concat([small_model.exposures] * 2, axis=1))
    elif part == "D_index":
        broken = replace(small_model, specific_var=pd.Series([0.01, 0.01], index=["A", "A"]))
    elif part == "F_index":
        broken = replace(small_model, factor_cov=pd.concat([small_model.factor_cov] * 2))
    elif part == "F_columns":
        broken = replace(small_model, factor_cov=pd.concat([small_model.factor_cov] * 2, axis=1))
    else:
        broken = replace(
            small_model, factor_cov=small_model.factor_cov.rename(index={"market": "other"})
        )
    with pytest.raises(ValueError):
        broken.portfolio_vol(weights)


def test_f05_unheld_unknown_exposure_and_specific_remain_unknown(small_model):
    B = small_model.exposures.copy()
    D = small_model.specific_var.copy()
    B.loc["B", "market"] = np.nan
    D["B"] = np.nan
    broken = replace(small_model, exposures=B, specific_var=D)
    weights = pd.Series({"A": 1.0, "B": 0.0})
    reference = risk_decomposition(weights, small_model)
    result = risk_decomposition(weights, broken)
    assert result.total_vol == reference.total_vol
    assert broken.portfolio_vol(weights) == small_model.portfolio_vol(weights)
    assert np.isnan(result.mctr["B"])
    assert np.isnan(broken.exposures.loc["B", "market"]) and np.isnan(broken.specific_var["B"])


def _regression_inputs(n=63):
    t = np.arange(n, dtype=float)
    return pd.Series(np.sin(t) + t / n), pd.DataFrame({"x": np.cos(t)})


def test_f06_duplicate_regressor_uses_effective_rank():
    y, X = _regression_inputs()
    baseline, n, k = _regressao_sem_modelo(y, X)
    got, n_dup, k_dup = _regressao_sem_modelo(y, X.assign(copy=X["x"]))
    assert (n_dup, k_dup) == (n, k)
    assert got == pytest.approx(baseline, rel=1e-12)
    assert banda_sem_modelo(n_dup, k_dup) == banda_sem_modelo(n, k)


@pytest.mark.parametrize("variant", ["constant", "permuted"])
def test_f06_same_information_preserves_measure_and_band(variant):
    y, X = _regression_inputs()
    base, n, k = _regressao_sem_modelo(y, X)
    redundant = X.assign(copy=X["x"], constant=1.0)
    if variant == "permuted":
        redundant = redundant[["constant", "copy", "x"]]
    got, n_actual, k_actual = _regressao_sem_modelo(y, redundant)
    assert (n_actual, k_actual) == (n, k)
    assert got == pytest.approx(base, rel=1e-12)
    assert banda_sem_modelo(n_actual, k_actual) == banda_sem_modelo(n, k)


def test_f06_effective_rank_controls_sample_availability():
    y, X = _regression_inputs(n=MIN_GL_SEM_MODELO + 2)
    base, n, k = _regressao_sem_modelo(y, X)
    got, n_actual, k_actual = _regressao_sem_modelo(y, X.assign(copy=X["x"]))
    assert np.isfinite(base) and np.isfinite(got)
    assert (n_actual, k_actual) == (n, k)
    assert banda_sem_modelo(n_actual, k_actual) is not None
    short, n_short, k_short = _regressao_sem_modelo(y.iloc[:-1], X.iloc[:-1])
    assert np.isnan(short) and banda_sem_modelo(n_short, k_short) is None


def test_f06_near_collinearity_is_not_exact_redundancy():
    y, X = _regression_inputs()
    X["near"] = X["x"] + np.sin(np.arange(len(y))) * 1e-8
    value, n, k = _regressao_sem_modelo(y, X)
    assert k == 2 and n == len(y) and np.isfinite(value)


@pytest.mark.parametrize("empty", [False, True])
def test_f06_no_independent_regressor_is_unavailable(empty):
    y, X = _regression_inputs()
    X["x"] = 1.0
    if empty:
        y, X = y.iloc[:0], X.iloc[:0]
    value, n, k = _regressao_sem_modelo(y, X)
    assert np.isnan(value) and k == 0
    assert banda_sem_modelo(n, k) is None


def _pm_views(confidence=1.0):
    return [
        View(
            issuer_id="A",
            source=ViewSource.PM,
            score=score,
            confidence=confidence,
            rationale="DADOS SIMULADOS",
            author="pm",
        )
        for score in (2, -1)
    ]


def test_f07_duplicate_pm_refused_before_sign():
    with pytest.raises(ValueError, match="PM"):
        final_view_sign(_pm_views())


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("confidence", [0.0, 1.0])
@pytest.mark.parametrize("api", ["sign", "tilt", "constraints"])
def test_f07_duplicate_pm_refused_at_shared_boundary(reverse, confidence, api):
    views = _pm_views(confidence)
    if reverse:
        views.reverse()
    before = [v.model_dump() for v in views]
    with pytest.raises(ValueError, match="PM"):
        if api == "sign":
            final_view_sign(views)
        elif api == "tilt":
            view_tilt_table(pd.Series({"A": 0.01}), views, pd.Series({"A": 0.3}), FundConfig())
        else:
            view_constraints(pd.Index(["A"]), views, FundConfig())
    assert [v.model_dump() for v in views] == before


def test_f08_empty_golden_set_is_not_an_evaluation():
    with pytest.raises(ValueError, match="vazio"):
        evaluate_golden_set(DemoResearchProvider(), cases=[])
