"""Testes do modelo de risco fatorial (exposições, estimação, analytics e estresse).

Usa dois tipos de dado SIMULADO (offline):
- painel "plantado" construído aqui com estrutura fatorial conhecida (testes de recuperação);
- mercado sintético completo (``make_synthetic_market``) para integração, sem look-ahead,
  VaR histórico e estresse.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import numpy as np
import pandas as pd
import pytest

from latam_ls.analytics.panel import AssetPanel, build_asset_panel
from latam_ls.config import FundConfig
from latam_ls.data.synthetic import make_synthetic_market
from latam_ls.risk.analytics import (
    effective_n,
    historical_pnl,
    historical_var_es,
    model_implied_returns,
    parametric_var_es,
    portfolio_beta,
    predicted_betas,
    risk_decomposition,
)
from latam_ls.risk.exposures import (
    OTHER_COUNTRY,
    OTHER_SECTOR,
    exposure_matrix,
    factor_structure,
    historical_mcap,
    market_weights,
    standardize_style,
    style_exposures,
)
from latam_ls.risk.model import (
    SPECIFIC_VOL_FLOOR,
    RiskModelEstimator,
    _restriction_matrix,
    estimate_risk_model,
    ewma_weights,
    nearest_psd,
    newey_west_ewma_cov,
)
from latam_ls.risk.stress import (
    HISTORICAL_SCENARIOS,
    NO_DATA,
    conditional_factor_move,
    stress_report,
    stress_tests,
)
from latam_ls.risk.types import STYLE_FACTORS, RiskModel

CFG = FundConfig()
STYLES_WITH_DATA = ["beta", "size", "momentum", "resvol", "value", "liquidity"]


# ======================================================================
# Painel plantado (estrutura conhecida)
# ======================================================================

PLANT_COUNTRIES = [("BR", 34), ("MX", 20), ("CL", 12), ("CO", 2), ("PE", 1)]
PLANT_BIG_SECTORS = ["Energy", "Materials", "Financials", "Industrials", "Utilities",
                     "Consumer Staples"]
# Setores pequenos (agrupados em sector:Other) espalhados por BR, MX e CL.
PLANT_SMALL_SECTORS = {5: "Health Care", 25: "Health Care", 45: "Real Estate"}


@dataclasses.dataclass
class Planted:
    panel: AssetPanel
    idio_vol: pd.Series
    beta: pd.Series
    market: np.ndarray
    country_f: dict[str, np.ndarray]
    mcap: pd.Series


def make_planted_panel(seed: int = 5, T: int = 620,
                       small_sectors: dict[int, str] | None = None) -> Planted:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=T)
    countries = [c for c, n in PLANT_COUNTRIES for _ in range(n)]
    N = len(countries)
    sectors = [PLANT_BIG_SECTORS[k % len(PLANT_BIG_SECTORS)] for k in range(N)]
    for k, s in (PLANT_SMALL_SECTORS if small_sectors is None else small_sectors).items():
        sectors[k] = s
    ids = [f"P{k:03d}" for k in range(N)]
    mkt = rng.normal(0.0003, 0.011, T)
    cf = {c: rng.normal(0, 0.006, T) for c, _ in PLANT_COUNTRIES}
    sf = {s: rng.normal(0, 0.005, T) for s in set(sectors)}
    beta = rng.uniform(0.6, 1.4, N)
    idio = rng.uniform(0.008, 0.02, N)
    eps = rng.normal(0.0, 1.0, (T, N)) * idio
    C = np.column_stack([cf[c] for c in countries])
    S = np.column_stack([sf[s] for s in sectors])
    r = beta * mkt[:, None] + C + S + eps
    px = 10.0 * np.cumprod(1.0 + r, axis=0)
    mcap = np.exp(rng.normal(np.log(5e9), 0.8, N))
    adtv = np.exp(rng.normal(np.log(20e6), 0.7, N))
    tv = adtv * rng.lognormal(0.0, 0.3, (T, N))
    returns = pd.DataFrame(r, index=dates, columns=ids)
    returns.iloc[0] = np.nan  # primeiro dia sem retorno (como no painel real)
    price = pd.DataFrame(px, index=dates, columns=ids)
    assets = pd.DataFrame({
        "issuer_name": [f"Plantada {i}" for i in ids], "country": countries, "sector": sectors,
        "primary_ticker": [f"{i}.T" for i in ids], "primary_currency": "USD",
        "market_cap_usd": mcap, "adtv_usd": adtv, "eligible": True, "exclusion_reason": "",
    }, index=pd.Index(ids, name="issuer_id"))
    lines = pd.DataFrame({"issuer_id": ids, "currency": "USD", "line_type": "US_LISTED"},
                         index=[f"{i}.T" for i in ids])
    panel = AssetPanel(
        as_of=dates[-1].date(), assets=assets, returns=returns, price_usd=price,
        traded_value_usd=pd.DataFrame(tv, index=dates, columns=ids),
        line_returns=returns.set_axis([f"{i}.T" for i in ids], axis=1), lines=lines,
        data_policy={"origem": "DADOS SIMULADOS (painel plantado de teste)"},
    )
    return Planted(panel, pd.Series(idio, index=ids), pd.Series(beta, index=ids), mkt, cf,
                   pd.Series(mcap, index=ids))


@pytest.fixture(scope="module")
def planted() -> Planted:
    return make_planted_panel()


@pytest.fixture(scope="module")
def planted_est(planted: Planted) -> RiskModelEstimator:
    return RiskModelEstimator(planted.panel, CFG, md=None, exposure_refresh_days=5)


# ======================================================================
# Mercado sintético completo
# ======================================================================

@pytest.fixture(scope="module")
def md():
    return make_synthetic_market(seed=11, start=date(2024, 1, 2))


@pytest.fixture(scope="module")
def panel(md) -> AssetPanel:
    return build_asset_panel(md, CFG)


@pytest.fixture(scope="module")
def est(panel, md) -> RiskModelEstimator:
    return RiskModelEstimator(panel, CFG, md=md, issuers=panel.eligible)


@pytest.fixture(scope="module")
def model(est, panel) -> RiskModel:
    return est.model_at(panel.as_of)


@pytest.fixture(scope="module")
def mkt_w(panel, model) -> pd.Series:
    return market_weights(panel, model.assets)


def _ls_weights(model: RiskModel, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    w = pd.Series(rng.normal(0.0, 0.02, len(model.assets)), index=model.assets)
    return w - w.mean()


def _replace_after(panel: AssetPanel, d: pd.Timestamp, seed: int = 99) -> AssetPanel:
    """Painel com retornos e valor negociado posteriores a ``d`` alterados (futuro diferente)."""
    rng = np.random.default_rng(seed)
    rets = panel.returns.copy()
    fut = rets.index > d
    rets.loc[fut] = rets.loc[fut] * 3.0 + rng.normal(0, 0.02, rets.loc[fut].shape)
    tv = panel.traded_value_usd.copy()
    tv.loc[tv.index > d] = tv.loc[tv.index > d] * 7.0
    return dataclasses.replace(panel, returns=rets, traded_value_usd=tv)


# ======================================================================
# Exposições
# ======================================================================

def test_market_weights_sum_to_one_and_scale_with_price(panel):
    ids = panel.eligible
    w_now = market_weights(panel, ids)
    assert w_now.sum() == pytest.approx(1.0)
    d = pd.Timestamp("2025-03-14")
    w_then = market_weights(panel, ids, d)
    assert w_then.sum() == pytest.approx(1.0)
    px = panel.price_usd[ids].ffill()
    mc = panel.assets.loc[ids, "market_cap_usd"] * px.loc[:d].iloc[-1] / px.iloc[-1]
    assert np.allclose(w_then.to_numpy(), (mc / mc.sum()).loc[w_then.index].to_numpy())
    assert not np.allclose(w_then.to_numpy(), w_now.loc[w_then.index].to_numpy())


def test_market_weights_exclude_missing_mcap(panel):
    assets = panel.assets.copy()
    victim = panel.eligible[3]
    assets.loc[victim, "market_cap_usd"] = np.nan
    p2 = dataclasses.replace(panel, assets=assets)
    w = market_weights(p2, panel.eligible)
    assert victim not in w.index
    assert w.sum() == pytest.approx(1.0)
    assert np.isnan(historical_mcap(p2, [victim])[victim]).all()


def test_standardize_style_properties():
    rng = np.random.default_rng(1)
    raw = rng.standard_t(3, 200)
    raw[[3, 50]] = np.nan
    raw[7] = 80.0  # outlier
    cap = rng.uniform(1, 10, 200)
    z = standardize_style(raw, cap, 3.0)
    ok = np.isfinite(z)
    assert np.isnan(z[[3, 50]]).all()
    assert np.sum(z[ok] * cap[ok]) / cap[ok].sum() == pytest.approx(0.0, abs=1e-12)
    assert np.std(z[ok]) == pytest.approx(1.0)
    assert z[7] == pytest.approx(z[ok].max())  # outlier winsorizado vira o máximo, não explode
    assert np.all(np.isnan(standardize_style(np.ones(10), np.ones(10), 3.0)))


def test_style_exposures_standardized_and_imputed(panel, md):
    ids = panel.eligible
    st = style_exposures(panel, md, CFG, panel.as_of, ids)
    assert list(st.columns) == STYLE_FACTORS
    assert st.notna().all().all()
    cw = market_weights(panel, ids).reindex(ids)
    for s in STYLE_FACTORS:
        assert float((st[s] * cw).sum()) == pytest.approx(0.0, abs=1e-10)
    for s in STYLE_FACTORS:
        if st.attrs["meta"]["style_imputations"][s] == 0:
            assert st[s].std(ddof=0) == pytest.approx(1.0, rel=1e-9)
    meta = st.attrs["meta"]
    # emissores regionais/dolarizados não têm moeda de origem: imputação registrada
    assert meta["style_imputations"]["fx_sens"] >= 1
    assert meta["non_point_in_time"]


def test_beta_style_tracks_planted_beta(panel, md):
    ids = panel.eligible
    st = style_exposures(panel, md, CFG, panel.as_of, ids)
    true_beta = md.fundamentals["beta"].reindex(panel.assets.loc[ids, "primary_ticker"])
    assert np.corrcoef(st["beta"], true_beta.to_numpy())[0, 1] > 0.5


def test_style_exposures_use_only_past_data(panel, md):
    ids = panel.eligible
    d = pd.Timestamp("2025-05-30")
    base = style_exposures(panel, md, CFG, d, ids)
    altered = style_exposures(_replace_after(panel, d), md, CFG, d, ids)
    pd.testing.assert_frame_equal(base, altered)
    # Preços futuros diferentes com o mesmo número de ações implícito: nada muda.
    px = panel.price_usd.copy()
    px.loc[px.index > d] *= 1.5
    assets = panel.assets.copy()
    assets["market_cap_usd"] *= 1.5
    p3 = dataclasses.replace(panel, price_usd=px, assets=assets)
    st3 = style_exposures(p3, md, CFG, d, ids)
    np.testing.assert_allclose(base.to_numpy(), st3.to_numpy(), atol=1e-9)


def test_short_history_styles_are_imputed_not_invented(panel, md):
    ids = panel.eligible
    early = panel.returns.index[60]
    st = style_exposures(panel, md, CFG, early, ids)
    imp = st.attrs["meta"]["style_imputations"]
    # 60 pregões < mínimo de 126 para beta/momentum: tudo imputado (0), não estimado.
    assert imp["beta"] == len(ids) and imp["momentum"] == len(ids)
    assert (st["beta"] == 0).all() and (st["momentum"] == 0).all()


def test_exposure_matrix_structure(panel, md):
    ids = panel.eligible
    X, groups = exposure_matrix(panel, md, CFG, panel.as_of, ids)
    assert (X["market"] == 1.0).all()
    assert groups["market"] == "market"
    countries = [f for f, g in groups.items() if g == "country"]
    sectors = [f for f, g in groups.items() if g == "sector"]
    styles = [f for f, g in groups.items() if g == "style"]
    assert styles == STYLE_FACTORS
    assert list(X.columns) == ["market"] + countries + sectors + styles
    assert (X[countries].sum(axis=1) <= 1).all() and (X[sectors].sum(axis=1) == 1).all()
    min_n = CFG.risk_model.min_names_per_sector
    for f in countries + sectors:
        assert int((X[f] != 0).sum()) >= min_n, f
    # Regionais (LATAM, PA, UY) e CO com poucos nomes vão para country:OTHER.
    assert f"country:{OTHER_COUNTRY}" in countries
    small = panel.assets.loc[ids, "country"].value_counts()
    for c in small.index[small < min_n]:
        assert f"country:{c}" not in countries


def test_factor_structure_never_leaves_single_member_factor(planted):
    p = planted.panel
    ids = list(p.assets.index)
    st = factor_structure(p, ids, 3)
    assert f"country:{OTHER_COUNTRY}" in st.country_factors  # CO(2) + PE(1)
    assert f"sector:{OTHER_SECTOR}" in st.sector_factors     # Health Care(2) + Real Estate(1)
    dm = st.dummies(ids)
    assert (dm.sum() >= 3).all()
    # Com o grupo agrupado ainda pequeno, os nomes ficam sem fator (nunca fator de 1 nome).
    ids2 = [i for i in ids if p.assets.loc[i, "country"] != "CO"]
    st2 = factor_structure(p, ids2, 3)
    assert f"country:{OTHER_COUNTRY}" not in st2.country_factors
    assert st2.unassigned_country == [i for i in ids2 if p.assets.loc[i, "country"] == "PE"]
    assert (st2.dummies(ids2).sum() >= 3).all()


def test_sector_duplicating_country_membership_is_removed():
    # Setores pequenos exatamente nos nomes CO/PE: sector:Other ≡ country:OTHER (colinear).
    n = sum(k for _, k in PLANT_COUNTRIES)
    pl = make_planted_panel(T=320, small_sectors={n - 3: "Health Care", n - 2: "Health Care",
                                                  n - 1: "Real Estate"})
    ids = list(pl.panel.assets.index)
    st = factor_structure(pl.panel, ids, 3)
    assert f"sector:{OTHER_SECTOR}" not in st.sector_factors
    assert st.unassigned_sector == ids[-3:]
    est_ = RiskModelEstimator(pl.panel, CFG, exposure_refresh_days=10)
    diag = est_.regression_diagnostics()
    assert (diag["status"] == "ok").mean() > 0.95


# ======================================================================
# Utilitários numéricos
# ======================================================================

def test_ewma_weights_halflife():
    w = ewma_weights(200, 20)
    assert w[-1] == 1.0
    assert w[-21] == pytest.approx(0.5)


def test_nearest_psd_clips_negative_eigenvalues():
    a = np.array([[1.0, 0.99, -0.9], [0.99, 1.0, 0.9], [-0.9, 0.9, 1.0]])
    assert np.linalg.eigvalsh(a).min() < 0
    b, n = nearest_psd(a)
    assert n >= 1
    assert np.linalg.eigvalsh(b).min() >= -1e-12
    np.testing.assert_allclose(b, b.T)


def test_newey_west_increases_variance_for_autocorrelated_series():
    rng = np.random.default_rng(3)
    e = rng.normal(0, 1, 3000)
    ar = np.empty_like(e)
    ar[0] = e[0]
    for t in range(1, len(e)):
        ar[t] = 0.4 * ar[t - 1] + e[t]
    f = ar[:, None]
    c0, _ = newey_west_ewma_cov(f, 10_000, 0)
    c2, _ = newey_west_ewma_cov(f, 10_000, 2)
    assert c2[0, 0] > 1.3 * c0[0, 0]
    f_nan = f.copy()
    f_nan[::7] = np.nan
    c_nan, cnt = newey_west_ewma_cov(f_nan, 10_000, 2)
    assert np.isfinite(c_nan).all() and cnt[0, 0] == np.isfinite(f_nan).sum()


def test_restriction_matrix_enforces_weighted_sum_zero():
    active = np.ones(7, dtype=bool)
    blocks = [np.array([1, 2, 3]), np.array([4, 5, 6])]
    weights = [np.array([0.5, 0.3, 0.2]), np.array([0.1, 0.6, 0.3])]
    R = _restriction_matrix(active, blocks, weights)
    assert R.shape == (7, 5)
    g = np.random.default_rng(0).normal(size=5)
    f = R @ g
    assert weights[0] @ f[1:4] == pytest.approx(0.0, abs=1e-14)
    assert weights[1] @ f[4:7] == pytest.approx(0.0, abs=1e-14)


# ======================================================================
# Recuperação da estrutura plantada
# ======================================================================

def test_planted_recovery_r2_and_specific_vol(planted, planted_est):
    m = planted_est.model_at(planted.panel.as_of)
    assert m.meta["mean_r_squared"] > 0.3
    spec = m.specific_vol.reindex(planted.idio_vol.index)
    true_annual = planted.idio_vol * np.sqrt(252)
    rho = spec.rank().corr(true_annual.rank())
    assert rho > 0.85
    assert float((spec / true_annual).median()) == pytest.approx(1.0, abs=0.25)
    # Sem MarketData não há value nem fx_sens: estilos fora do modelo, com flag.
    assert "value" not in m.factor_names and "fx_sens" not in m.factor_names
    assert "value" in m.meta["style_flags"] and "fx_sens" in m.meta["style_flags"]


def test_planted_market_and_country_factors_recovered(planted, planted_est):
    fr = planted_est.factor_returns_all
    p = planted.panel
    rets = p.returns.loc[fr.index]
    w_prev = historical_mcap(p, list(p.assets.index)).shift(1).loc[fr.index]
    cw_ret = (rets * w_prev).sum(axis=1) / w_prev.sum(axis=1)
    assert np.corrcoef(fr["market"], cw_ret)[0, 1] > 0.95
    # País relativo ao mercado: c_MX − Σ w_c c_c (pesos de capitalização das restrições).
    cw = planted_est.constraint_weights
    true = {c: pd.Series(v, index=p.returns.index).loc[fr.index]
            for c, v in planted.country_f.items()}
    true["OTHER"] = (true["CO"] * 2 + true["PE"]) / 3  # aproximação do grupo agrupado
    cols = [c for c in cw.columns if c.startswith("country:")]
    avg = sum(cw[c] * true[c.split(":")[1]] for c in cols)
    rel_mx = true["MX"] - avg
    assert np.corrcoef(fr["country:MX"], rel_mx)[0, 1] > 0.8


def test_constraints_hold_every_day(planted_est, est):
    for e in (planted_est, est):
        cw = e.constraint_weights
        fr = e.factor_returns_all
        for prefix in ("country:", "sector:"):
            cols = [c for c in cw.columns if c.startswith(prefix)]
            s = np.nansum(cw[cols].to_numpy() * fr[cols].to_numpy(), axis=1)
            assert np.abs(s).max() < 1e-12
        assert len(fr) > 0
    # No painel plantado (sem feriados) todo nome tem país e setor: pesos somam 1 por bloco.
    cw = planted_est.constraint_weights
    for prefix in ("country:", "sector:"):
        cols = [c for c in cw.columns if c.startswith(prefix)]
        np.testing.assert_allclose(cw[cols].sum(axis=1), 1.0, rtol=1e-12)


# ======================================================================
# Modelo no mercado sintético
# ======================================================================

def test_model_shapes_meta_and_flags(model, panel):
    assert set(model.factor_groups.values()) == {"market", "country", "sector", "style"}
    assert model.factor_names[0] == "market"
    assert list(model.factor_cov.index) == model.factor_names
    assert set(model.specific_var.index) == set(model.assets)
    assert (model.specific_var >= SPECIFIC_VOL_FLOOR ** 2 - 1e-15).all()
    assert model.meta["data_notice"] == "DADOS SIMULADOS"
    assert model.meta["non_point_in_time"]
    assert model.meta["n_dates_regression"] > 400
    assert model.r_squared is not None and model.r_squared.between(-1, 1).all()
    assert model.meta["mean_r_squared"] > 0.2
    assert model.factor_returns.index.max() <= pd.Timestamp(model.as_of)
    # Nenhum fator de país/setor com um único membro.
    for f in model.factors_in_group("country") + model.factors_in_group("sector"):
        assert int((model.exposures[f] != 0).sum()) >= CFG.risk_model.min_names_per_sector


def test_factor_cov_is_psd_and_symmetric(model):
    F = model.factor_cov.to_numpy()
    np.testing.assert_allclose(F, F.T, atol=1e-15)
    assert np.linalg.eigvalsh(F).min() >= -1e-12
    vols = np.sqrt(np.diag(F))
    assert (vols > 0.01).all() and (vols < 1.0).all()


def test_estimate_risk_model_equals_estimator(est, panel, md):
    d = pd.Timestamp("2026-06-30")
    a = est.model_at(d)
    b = estimate_risk_model(panel, CFG, md=md, as_of=d, issuers=panel.eligible)
    assert a.as_of == b.as_of
    pd.testing.assert_frame_equal(a.factor_cov, b.factor_cov)
    pd.testing.assert_frame_equal(a.exposures, b.exposures)
    pd.testing.assert_series_equal(a.specific_var, b.specific_var)


def test_model_at_has_no_lookahead(est, panel, md):
    d = pd.Timestamp("2025-07-31")
    m1 = est.model_at(d)
    p2 = _replace_after(panel, d)
    est2 = RiskModelEstimator(p2, CFG, md=md, issuers=panel.eligible)
    m2 = est2.model_at(d)
    pd.testing.assert_frame_equal(m1.exposures, m2.exposures)
    pd.testing.assert_frame_equal(m1.factor_cov, m2.factor_cov)
    pd.testing.assert_series_equal(m1.specific_var, m2.specific_var)
    pd.testing.assert_frame_equal(m1.factor_returns, m2.factor_returns)
    # E o futuro alterado de fato muda o modelo de uma data posterior.
    later = pd.Timestamp(panel.as_of)
    assert not np.allclose(est.model_at(later).specific_var, est2.model_at(later).specific_var)


def test_short_history_issuer_gets_group_mean(panel, md):
    victim = panel.eligible[10]
    rets = panel.returns.copy()
    rets.iloc[:-40, rets.columns.get_loc(victim)] = np.nan
    px = panel.price_usd.copy()
    px.iloc[:-41, px.columns.get_loc(victim)] = np.nan
    p2 = dataclasses.replace(panel, returns=rets, price_usd=px)
    m = estimate_risk_model(p2, CFG, md=md, issuers=panel.eligible)
    assert victim in m.meta["specific_imputed_group_mean"]
    assert np.isfinite(m.specific_var[victim]) and m.specific_var[victim] > 0
    # Antes de existir, o emissor não entra no modelo (sem exposição inventada).
    early = estimate_risk_model(p2, CFG, md=md, as_of=pd.Timestamp("2025-09-30"),
                                issuers=panel.eligible)
    assert victim not in early.assets


# ======================================================================
# Analytics
# ======================================================================

def test_portfolio_vol_matches_full_covariance(model):
    w = _ls_weights(model)
    S = model.cov_matrix()
    direct = float(np.sqrt(w.reindex(S.index) @ S @ w.reindex(S.index)))
    assert model.portfolio_vol(w) == pytest.approx(direct, rel=1e-10)
    dec = risk_decomposition(w, model)
    assert dec.total_vol == pytest.approx(direct, rel=1e-10)
    assert dec.total_vol ** 2 == pytest.approx(dec.factor_vol ** 2 + dec.specific_vol ** 2)


def test_euler_contributions_sum_to_one(model):
    w = _ls_weights(model, seed=4)
    dec = risk_decomposition(w, model)
    assert dec.asset_contrib.sum() == pytest.approx(1.0)
    assert sum(dec.by_group.values()) == pytest.approx(1.0)
    assert dec.by_factor.sum() == pytest.approx(dec.factor_share)
    assert set(dec.by_group) == {"market", "country", "sector", "style", "specific"}
    assert float(dec.mctr.reindex(w.index) @ w) == pytest.approx(dec.total_vol)
    pd.testing.assert_series_equal(dec.exposures, model.factor_exposure(w),
                                   check_names=False)
    empty = risk_decomposition(pd.Series(dtype=float), model)
    assert empty.total_vol == 0.0 and np.isnan(empty.factor_share)


def test_market_portfolio_beta_is_one(model, mkt_w):
    b = predicted_betas(model, mkt_w)
    assert portfolio_beta(mkt_w, model, mkt_w) == pytest.approx(1.0)
    assert float(b @ mkt_w.reindex(b.index).fillna(0.0)) == pytest.approx(1.0)
    assert b.between(0.0, 3.0).all()


def test_parametric_var_es_normal(model):
    w = _ls_weights(model)
    var, es = parametric_var_es(w, model, confidence=0.99, horizon_days=1)
    sigma_d = model.portfolio_vol(w) / np.sqrt(252)
    assert var == pytest.approx(2.326347874 * sigma_d, rel=1e-8)
    assert es == pytest.approx(2.665214220 * sigma_d, rel=1e-8)
    var5, _ = parametric_var_es(w, model, horizon_days=5)
    assert var5 == pytest.approx(var * np.sqrt(5))


def test_historical_var_never_fills_missing_with_zero(model, panel):
    w = _ls_weights(model, seed=7)
    victim = w.abs().idxmax()
    fr = model.factor_returns
    cal = panel.returns.index[panel.returns.index <= pd.Timestamp(model.as_of)][-504:]
    implied = model_implied_returns(model, [victim], cal)[victim]
    good = [d for d in cal if np.isfinite(implied.get(d, np.nan))
            and panel.returns.loc[d, w.index].notna().all()][-30:-20]
    bad_dates = [d for d in cal if d not in fr.index][-2:]
    assert good and bad_dates
    rets = panel.returns.copy()
    rets.loc[good, victim] = np.nan
    p2 = dataclasses.replace(panel, returns=rets)
    pnl, meta = historical_pnl(w, p2, model)
    others = w.drop(victim)
    for d in good:
        expected = float(rets.loc[d, others.index] @ others) + w[victim] * implied[d]
        zero_fill = float(rets.loc[d, others.index] @ others)
        assert pnl[d] == pytest.approx(expected, rel=1e-12, abs=1e-15)
        assert abs(pnl[d] - zero_fill) > 1e-9
    assert meta["n_model_filled"] >= len(good)
    # Data sem regressão (fator indefinido) + retorno ausente ⇒ fora da amostra, nunca zero.
    rets.loc[bad_dates, victim] = np.nan
    pnl2, meta2 = historical_pnl(w, dataclasses.replace(panel, returns=rets), model)
    assert pnl2[bad_dates].isna().all()
    assert all(str(d.date()) in meta2["dropped_dates"] for d in bad_dates)
    var, es = historical_var_es(w, dataclasses.replace(panel, returns=rets), model)
    assert np.isfinite(var) and es >= var > 0


def test_historical_var_horizon_and_ordering(model, panel):
    w = _ls_weights(model, seed=2)
    v1, e1 = historical_var_es(w, panel, model, confidence=0.99, horizon_days=1)
    v5, e5 = historical_var_es(w, panel, model, confidence=0.99, horizon_days=5)
    v95, _ = historical_var_es(w, panel, model, confidence=0.95, horizon_days=1)
    assert e1 >= v1 > v95 > 0
    assert v5 > v1 and e5 >= v5
    pnl, _ = historical_pnl(w, panel, model, lookback=504)
    assert len(pnl) == 504
    assert -np.quantile(pnl.dropna(), 0.01) == pytest.approx(v1)


def test_effective_n():
    assert effective_n(pd.Series([0.01] * 10 + [-0.01] * 10)) == pytest.approx(20.0)
    p = pd.Series([0.05, -0.01])
    assert effective_n(p) == pytest.approx(1.0 / ((5 / 6) ** 2 + (1 / 6) ** 2))
    assert effective_n(pd.Series(dtype=float)) == 0.0


# ======================================================================
# Estresse
# ======================================================================

def test_idiosyncratic_scenarios_exact(model, panel, mkt_w):
    w = _ls_weights(model, seed=5)
    res = stress_tests(w, panel, model, mkt_w)
    shorts = w[w < 0].sort_values().head(5)
    longs = w[w > 0].sort_values(ascending=False).head(5)
    assert res["Squeeze: 5 maiores shorts +30%"] == pytest.approx(0.30 * shorts.sum())
    assert res["Quebra: 5 maiores longs -30%"] == pytest.approx(-0.30 * longs.sum())
    assert res["Squeeze: 5 maiores shorts +30%"] < 0


def test_hypothetical_shocks_are_calibrated(model, panel, mkt_w):
    res = stress_tests(mkt_w, panel, model, mkt_w)
    assert res["Mercado LatAm -20%"] == pytest.approx(-0.20)
    br = [i for i in model.assets if model.exposures.loc[i, "country:BR"] != 0]
    w_br = mkt_w.reindex(br) / mkt_w.reindex(br).sum()
    assert stress_tests(w_br, panel, model, mkt_w)["Brasil -15%"] == pytest.approx(-0.15)
    mx = [i for i in model.assets if model.exposures.loc[i, "country:MX"] != 0]
    w_mx = mkt_w.reindex(mx) / mkt_w.reindex(mx).sum()
    assert stress_tests(w_mx, panel, model, mkt_w)["México -15%"] == pytest.approx(-0.15)
    mom = conditional_factor_move(model, {"momentum": -0.05})
    assert mom["momentum"] == -0.05 and np.isfinite(mom).all()
    w = _ls_weights(model)
    rep = stress_report(w, panel, model, mkt_w)
    hyp = rep[rep["kind"] == "hipotético"]
    assert (hyp["status"] == "ok").all() and hyp["pnl"].notna().all()


def test_historical_scenarios_replay_and_no_data(model, panel, mkt_w):
    w = _ls_weights(model, seed=8)
    rep = stress_report(w, panel, model, mkt_w)
    covid = rep.loc["COVID crash (fev-mar/2020)"]
    assert covid["status"] == NO_DATA and np.isnan(covid["pnl"])
    name = "Eleição México jun/2024"
    d0, d1 = HISTORICAL_SCENARIOS[name]
    r = panel.returns.loc[(panel.returns.index > pd.Timestamp(d0))
                          & (panel.returns.index <= pd.Timestamp(d1)), w.index]
    cum = (1.0 + r.fillna(0.0)).prod() - 1.0  # NaN = feriado: retorno do dia seguinte cobre
    assert rep.loc[name, "status"] == "ok"
    assert rep.loc[name, "pnl"] == pytest.approx(float(cum @ w))


def test_historical_scenario_missing_issuer_uses_factor_implied(model, panel, mkt_w):
    w = _ls_weights(model, seed=9)
    victim = w.abs().idxmax()
    name = "Choque fiscal BRL dez/2024"
    d0, d1 = HISTORICAL_SCENARIOS[name]
    win = (panel.returns.index > pd.Timestamp(d0)) & (panel.returns.index <= pd.Timestamp(d1))
    rets = panel.returns.copy()
    rets.loc[win, victim] = np.nan
    p2 = dataclasses.replace(panel, returns=rets)
    rep = stress_report(w, p2, model, mkt_w, scenarios={name: (d0, d1)})
    dates = panel.returns.index[win]
    if not dates.isin(model.factor_returns.index).all():
        assert rep.loc[name, "status"] == NO_DATA
        assert np.isnan(rep.loc[name, "pnl"])
        return
    implied = model_implied_returns(model, [victim], dates)[victim].dropna()
    cum_v = float(np.prod(1.0 + implied.to_numpy()) - 1.0)
    others = w.drop(victim)
    cum_o = (1.0 + rets.loc[win, others.index].fillna(0.0)).prod() - 1.0
    assert rep.loc[name, "status"] == "ok"
    assert rep.loc[name, "pnl"] == pytest.approx(float(cum_o @ others) + w[victim] * cum_v)
    assert "implícito" in rep.loc[name, "detail"]
