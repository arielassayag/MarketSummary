"""Testes do módulo de alpha: sinais, combinação/ortogonalização e visões (DADOS SIMULADOS)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from latam_ls.alpha.combine import (
    CORR_EIGEN_FLOOR,
    MAX_WLS_WEIGHT_RATIO,
    AlphaResult,
    build_alpha,
    coverage_scale,
    information_coefficient,
    neutralize,
    robust_zscore,
    signal_correlation,
    wls_weights,
)
from latam_ls.alpha.signals import (
    MIN_OBS_MOMENTUM,
    MOMENTUM_SKIP,
    RESIDUAL_WINDOW,
    SIGNALS,
    VALUE_FIELDS,
    _cap_weighted_market,
    _market_over_gaps,
    analyst_inputs,
    cap_weights_usd,
    compute_signals,
    earnings_yield,
    residual_returns,
    select_fundamental_lines,
    value_components,
)
from latam_ls.alpha.views import (
    ai_view_ic,
    apply_views,
    mandate_max_abs_weight,
    view_tilt_table,
)
from latam_ls.analytics.panel import build_asset_panel
from latam_ls.config import FundConfig
from latam_ls.contracts import View, ViewSource
from latam_ls.data.synthetic import make_synthetic_market
from latam_ls.market import MarketData
from latam_ls.risk.types import TRADING_DAYS, RiskModel

START = date(2024, 1, 2)
PIT_SIGNALS = [n for n, s in SIGNALS.items() if s.point_in_time]


# ==========================================================
# Fixtures (mercado SIMULADO e modelo de risco mínimo para teste)
# ==========================================================

def _make_model(panel, var_floor: float = 0.05 ** 2) -> RiskModel:
    """Modelo fatorial mínimo (mercado, país, setor, tamanho) por regressão cross-section diária.

    Serve apenas para testar o alpha sem depender do módulo de risco; piso de variância
    específica como no modelo de produção.
    """
    a = panel.assets
    ids = list(a.index)
    B = pd.DataFrame(index=pd.Index(ids, name="issuer_id"))
    B["market"] = 1.0
    for c in sorted(a["country"].unique()):
        B[f"country:{c}"] = (a["country"] == c).astype(float)
    for s in sorted(a["sector"].unique()):
        B[f"sector:{s}"] = (a["sector"] == s).astype(float)
    lm = np.log(a["market_cap_usd"].astype(float))
    B["size"] = ((lm - lm.mean()) / lm.std()).to_numpy()
    X = B.to_numpy()
    R = panel.returns
    F = np.full((len(R), X.shape[1]), np.nan)
    E = np.full(R.shape, np.nan)
    for t, row in enumerate(R.to_numpy()):
        m = np.isfinite(row)
        if m.sum() < 10:
            continue
        coef, *_ = np.linalg.lstsq(X[m], row[m], rcond=None)
        F[t] = coef
        E[t, m] = row[m] - X[m] @ coef
    fr = pd.DataFrame(F, index=R.index, columns=B.columns)
    sr = pd.DataFrame(E, index=R.index, columns=ids)
    spec = (sr.var() * TRADING_DAYS).clip(lower=var_floor)
    groups = {f: ("market" if f == "market" else f.split(":")[0] if ":" in f else "style")
              for f in B.columns}
    return RiskModel(as_of=panel.as_of, exposures=B, factor_cov=fr.cov() * TRADING_DAYS,
                     specific_var=spec, factor_returns=fr, specific_returns=sr,
                     factor_groups=groups)


def _planted_quality(md: MarketData) -> pd.Series:
    """Reconstrói o quality_z plantado no gerador: margem operacional = 0,15 + 0,05·q."""
    prim = md.universe.issuers["primary_ticker"]
    opm = pd.to_numeric(md.fundamentals["operating_margins"]).reindex(prim.to_numpy())
    return pd.Series((opm.to_numpy() - 0.15) / 0.05, index=prim.index)


@pytest.fixture(scope="module")
def cfg() -> FundConfig:
    return FundConfig()


@pytest.fixture(scope="module")
def md() -> MarketData:
    return make_synthetic_market(seed=7, start=START)


@pytest.fixture(scope="module")
def panel(md, cfg):
    return build_asset_panel(md, cfg)


@pytest.fixture(scope="module")
def model(panel) -> RiskModel:
    return _make_model(panel)


@pytest.fixture(scope="module")
def ids(panel) -> list[str]:
    return list(panel.assets.index)


@pytest.fixture(scope="module")
def as_of(panel) -> pd.Timestamp:
    return pd.Timestamp(panel.as_of)


@pytest.fixture(scope="module")
def signals(panel, md, model, as_of, ids) -> pd.DataFrame:
    return compute_signals(panel, md, model, as_of, ids)


@pytest.fixture(scope="module")
def alpha_res(signals, model, cfg) -> AlphaResult:
    return build_alpha(signals, model, cfg)


def _with_fundamentals(md: MarketData, edits: dict[tuple[str, str], object]) -> MarketData:
    f = md.fundamentals.copy()
    for (ticker, col), val in edits.items():
        f.loc[ticker, col] = val
    return replace(md, fundamentals=f)


def _local_primary_with_adr(md: MarketData) -> tuple[str, str, str]:
    """(emissor, linha local primária, linha ADR) de um emissor com as duas linhas."""
    lines = md.universe.lines
    for iid, row in md.universe.issuers.iterrows():
        lf = lines[lines["issuer_id"] == iid]
        if row["primary_line_type"] == "LOCAL" and (lf["line_type"] == "ADR").any():
            adr = lf.index[lf["line_type"] == "ADR"][0]
            return str(iid), str(row["primary_ticker"]), str(adr)
    raise AssertionError("Universo simulado sem emissor local + ADR.")


# ==========================================================
# Sinais
# ==========================================================

def test_registry_matches_config_and_pit_flags(cfg):
    assert set(SIGNALS) == set(cfg.alpha.signal_weights)
    assert PIT_SIGNALS == ["residual_momentum", "short_term_reversal", "low_risk"]
    for name, spec in SIGNALS.items():
        assert spec.name == name
        assert callable(spec.fn)
        assert len(spec.description_pt) > 20
    assert not SIGNALS["value"].point_in_time
    assert not SIGNALS["quality"].point_in_time
    assert not SIGNALS["analyst_revision"].point_in_time


def test_compute_signals_shape_and_metadata(signals, panel, md, model, as_of, ids):
    assert list(signals.index) == ids
    assert list(signals.columns) == list(SIGNALS)
    assert signals.attrs["as_of"] == as_of.date().isoformat()
    assert signals.attrs["point_in_time"]["value"] is False
    assert any("não point-in-time" in n for n in signals.attrs["notes"])
    # Cobertura alta no universo simulado; ausências permanecem NaN (nunca zero).
    assert signals.notna().mean().min() > 0.9
    assert np.isfinite(signals.to_numpy()[signals.notna().to_numpy()]).all()

    sub = compute_signals(panel, md, model, as_of, ids + [ids[0], "NAO_EXISTE"],
                          names=["quality", "residual_momentum", "value"], pit_only=True)
    assert list(sub.columns) == ["residual_momentum"]
    assert list(sub.index) == ids + ["NAO_EXISTE"]
    assert sub.loc["NAO_EXISTE"].isna().all()
    with pytest.raises(KeyError):
        compute_signals(panel, md, model, as_of, ids, names=["inexistente"])


def test_pit_signals_ignore_future_data(md, cfg, as_of):
    """Alterar preços/volumes posteriores a as_of não muda NENHUM sinal (inclusive não-PIT)."""
    cut = pd.Timestamp(md.close.index[-40])
    rng = np.random.default_rng(0)
    future = md.close.index > cut
    shock = rng.uniform(0.5, 1.8, size=(int(future.sum()), md.close.shape[1]))
    close2, adj2, vol2 = md.close.copy(), md.adj_close.copy(), md.volume.copy()
    close2.loc[future] = close2.loc[future] * shock
    adj2.loc[future] = adj2.loc[future] * shock
    vol2.loc[future] = vol2.loc[future] * 3.0
    close2.iloc[-5:, :10] = np.nan
    adj2.iloc[-5:, :10] = np.nan
    md2 = replace(md, close=close2, adj_close=adj2, volume=vol2)

    panel_a = build_asset_panel(md, cfg)
    panel_b = build_asset_panel(md2, cfg)
    panel_c = build_asset_panel(md, cfg, as_of=cut.date())  # painel truncado em as_of
    ids = list(panel_a.assets.index)
    sa = compute_signals(panel_a, md, None, cut, ids)
    sb = compute_signals(panel_b, md2, None, cut, ids)
    sc = compute_signals(panel_c, md.truncate(cut.date()), None, cut, ids)
    pd.testing.assert_frame_equal(sa, sb)
    pd.testing.assert_frame_equal(sa[PIT_SIGNALS], sc[PIT_SIGNALS])
    # Sanidade: no as_of final os sinais de preço mudam (o choque é real).
    end = pd.Timestamp(md.close.index[-1])
    ra = compute_signals(panel_a, md, None, end, ids, pit_only=True)
    rb = compute_signals(panel_b, md2, None, end, ids, pit_only=True)
    assert not ra.equals(rb)


def test_pit_signals_with_model_ignore_future_specific_returns(panel, md, model, ids):
    cut = pd.Timestamp(model.specific_returns.index[-30])
    sr = model.specific_returns.copy()
    sr.loc[sr.index > cut] = 0.5  # futuro absurdo
    model2 = replace(model, specific_returns=sr)
    a = compute_signals(panel, md, model, cut, ids, pit_only=True)
    b = compute_signals(panel, md, model2, cut, ids, pit_only=True)
    pd.testing.assert_frame_equal(a, b)
    assert any("após as_of" in n for n in a.attrs["notes"])


def test_residual_signals_match_manual_formulas(signals, model, as_of):
    S = model.specific_returns.loc[model.specific_returns.index <= as_of].tail(RESIDUAL_WINDOW)
    for iid in ["SIM001", "SIM020", "SIM045"]:
        s = S[iid]
        mom = s.iloc[:-MOMENTUM_SKIP].dropna()
        assert signals.loc[iid, "residual_momentum"] == pytest.approx(mom.sum() / mom.std(ddof=1))
        assert signals.loc[iid, "short_term_reversal"] == pytest.approx(-s.tail(21).sum())
        expected_lr = -s.tail(126).std(ddof=1) * np.sqrt(TRADING_DAYS)
        assert signals.loc[iid, "low_risk"] == pytest.approx(expected_lr)


def test_residual_momentum_requires_min_observations(panel, md, model, as_of, ids):
    sr = model.specific_returns.copy()
    window = sr.index[(sr.index <= as_of)][-RESIDUAL_WINDOW:-MOMENTUM_SKIP]
    holes = window[: len(window) - (MIN_OBS_MOMENTUM - 1)]
    sr.loc[holes, "SIM010"] = np.nan  # sobram 149 observações
    out = compute_signals(panel, md, replace(model, specific_returns=sr), as_of, ids,
                          names=["residual_momentum"])
    assert np.isnan(out.loc["SIM010", "residual_momentum"])
    assert out["residual_momentum"].drop("SIM010").notna().sum() >= len(ids) - 2
    assert any("SIM010" in n for n in out.attrs["notes"])


def test_market_residuals_without_model(panel, md, as_of):
    resid, notes = residual_returns(panel, md, None, as_of)
    assert len(resid) == RESIDUAL_WINDOW
    assert resid.index.max() <= as_of
    # Resíduos de mercado têm vol menor que os retornos totais e ~zero beta com o mercado.
    tot = panel.returns.loc[resid.index]
    assert (resid.std() < tot.std()).mean() > 0.9


def test_quality_signal_tracks_planted_quality(signals, md):
    q = _planted_quality(md)
    rho = signals["quality"].corr(q.reindex(signals.index), method="spearman")
    assert rho > 0.5


def test_price_signal_directions_with_strong_planted_alpha(cfg):
    md_s = make_synthetic_market(seed=11, start=START, planted_alpha=0.003)
    panel_s = build_asset_panel(md_s, cfg)
    ids = list(panel_s.assets.index)
    sig = compute_signals(panel_s, md_s, None, pd.Timestamp(panel_s.as_of), ids, pit_only=True)
    q = _planted_quality(md_s).reindex(ids)
    assert sig["residual_momentum"].corr(q, method="spearman") > 0.6
    assert sig["short_term_reversal"].corr(q, method="spearman") < -0.2


def test_earnings_yield_rules():
    pe = pd.Series([10.0, -5.0, np.nan, np.nan, 0.0, 8.0])
    eps = pd.Series([1.0, -2.0, -3.0, np.nan, 1.0, np.nan])
    px = pd.Series([100.0, 100.0, 50.0, 10.0, 20.0, np.nan])
    out = earnings_yield(pe, eps, px)
    expected = [0.1, -0.02, -0.06, np.nan, 0.05, 0.125]
    np.testing.assert_allclose(out.to_numpy(), expected, equal_nan=True)


def test_value_prefers_financial_currency_line(md, panel, as_of, ids):
    iid, local, adr = _local_primary_with_adr(md)
    sel = select_fundamental_lines(md, ids, VALUE_FIELDS)
    assert sel.loc[iid, "ticker"] == local
    assert bool(sel.loc[iid, "currency_match"])
    base = compute_signals(panel, md, None, as_of, ids, names=["value"])["value"]
    # Múltiplos absurdos na linha ADR (descasamento de moeda típico) não afetam o sinal.
    md_adr = _with_fundamentals(md, {(adr, "trailing_pe"): 0.3, (adr, "price_to_book"): 0.01,
                                     (adr, "enterprise_to_ebitda"): 0.1})
    after_adr = compute_signals(panel, md_adr, None, as_of, ids, names=["value"])["value"]
    pd.testing.assert_series_equal(base, after_adr)
    md_loc = _with_fundamentals(md, {(local, "trailing_pe"): 2.0})
    after_loc = compute_signals(panel, md_loc, None, as_of, ids, names=["value"])["value"]
    assert after_loc[iid] > base[iid]


def test_value_uses_primary_line_without_currency_match(md, ids, signals):
    sel = select_fundamental_lines(md, ids, VALUE_FIELDS)
    nomatch = sel.index[~sel["currency_match"].astype(bool)]
    assert len(nomatch) >= 1  # ex.: empresa regional listada em USD com balanço em BRL
    comp = value_components(md, ids, pd.Timestamp(md.close.index[-1]))
    for iid in nomatch:
        assert sel.loc[iid, "ticker"] == md.universe.issuers.loc[iid, "primary_ticker"]
        assert np.isfinite(signals.loc[iid, "value"])
        # Linha não ADR com balanço em outra moeda: P/VPA e EV/EBITDA corrigidos pelo câmbio.
        assert comp.loc[iid, "currency_status"] == "fx_corrigido"


def test_value_negative_earnings_and_missing_data(md, panel, as_of, ids):
    iid, local, _ = _local_primary_with_adr(md)
    base = compute_signals(panel, md, None, as_of, ids, names=["value"])["value"]
    neg = _with_fundamentals(md, {(local, "trailing_pe"): np.nan, (local, "trailing_eps"): -5.0,
                                  (local, "price_to_book"): np.nan,
                                  (local, "enterprise_to_ebitda"): np.nan})
    v_neg = compute_signals(panel, neg, None, as_of, ids, names=["value"])["value"]
    assert np.isfinite(v_neg[iid])
    assert v_neg[iid] <= v_neg.quantile(0.05)  # lucro negativo ⇒ entre os mais caros
    # Sem nenhum múltiplo válido em nenhuma linha ⇒ NaN (nunca zero).
    lines = md.universe.lines
    edits = {(t, c): np.nan for t in lines.index[lines["issuer_id"] == iid] for c in VALUE_FIELDS}
    v_nan = compute_signals(panel, _with_fundamentals(md, edits), None, as_of, ids,
                            names=["value"])
    assert np.isnan(v_nan.loc[iid, "value"])
    assert v_nan["value"].drop(iid).notna().all()
    assert np.isfinite(base[iid])


def test_quality_negative_equity_is_missing_component(md, panel, as_of, ids):
    iid, local, _ = _local_primary_with_adr(md)
    md2 = _with_fundamentals(md, {(local, "debt_to_equity"): -40.0})
    out = compute_signals(panel, md2, None, as_of, ids, names=["quality"])
    assert np.isfinite(out.loc[iid, "quality"])
    assert any("PL negativo" in n for n in out.attrs["notes"])


def test_analyst_inputs_same_line_and_min_opinions(md, panel, as_of, ids):
    inp = analyst_inputs(md, ids, as_of)
    iid, local, adr = _local_primary_with_adr(md)
    row = inp.loc[iid]
    px = md.close.loc[md.close.index <= as_of, row["ticker"]].dropna().iloc[-1]
    target = float(md.fundamentals.loc[row["ticker"], "target_mean_price"])
    assert row["upside"] == pytest.approx(target / px - 1.0)
    assert row["n_opinions"] >= 3
    assert row["rec_score"] == pytest.approx(
        3.0 - float(md.fundamentals.loc[row["ticker"], "recommendation_mean"]))

    lines = md.universe.lines
    thin = {(t, "number_of_analyst_opinions"): 2 for t in lines.index[lines["issuer_id"] == iid]}
    md_thin = _with_fundamentals(md, thin)
    assert analyst_inputs(md_thin, ids, as_of).loc[iid, "flag"] == "sem_cobertura_minima"
    sig = compute_signals(panel, md_thin, None, as_of, ids, names=["analyst_revision"])
    assert np.isnan(sig.loc[iid, "analyst_revision"])

    # Preço-alvo incoerente (ex.: moeda trocada) ⇒ upside descartado, recomendação mantida.
    md_bad = _with_fundamentals(md, {(row["ticker"], "target_mean_price"): px * 50})
    bad = analyst_inputs(md_bad, ids, as_of).loc[iid]
    assert bad["flag"] == "upside_implausivel" and np.isnan(bad["upside"])
    sig_bad = compute_signals(panel, md_bad, None, as_of, ids, names=["analyst_revision"])
    assert np.isfinite(sig_bad.loc[iid, "analyst_revision"])


def test_stale_price_flagged_in_analyst_inputs(md, as_of, ids):
    inp = analyst_inputs(md, ids, as_of)
    stale_issuer = md.universe.issuers.index[5]  # papel sem negócios nos últimos 10 pregões
    assert inp.loc[stale_issuer, "flag"] == "preco_defasado"
    assert np.isnan(inp.loc[stale_issuer, "upside"])


# ==========================================================
# Combinação
# ==========================================================

def test_robust_zscore_basic_properties():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0, 1, 200), index=[f"A{i}" for i in range(200)])
    x.iloc[:5] = np.nan
    x.iloc[10] = 1e6  # outlier extremo
    z = robust_zscore(x, 3.0)
    assert z.iloc[:5].isna().all() and z.iloc[5:].notna().all()
    assert z.abs().max() <= 3.0 + 1e-12
    assert z.iloc[10] == z.max() and z.iloc[10] > 2.5  # limitado, mas ainda o maior
    assert abs(z.mean()) < 0.05 and abs(z.std(ddof=0) - 1.0) < 0.05
    # O outlier não comprime os demais: ordem preservada e escala próxima da original.
    rest = x.drop(x.index[10]).dropna()
    assert z[rest.index].corr(rest, method="spearman") == pytest.approx(1.0)
    assert z[rest.index].std() == pytest.approx(1.0, abs=0.1)


def test_robust_zscore_groups_with_small_group_fallback():
    idx = [f"I{i}" for i in range(14)]
    x = pd.Series(np.r_[np.linspace(10, 20, 8), np.linspace(-5, 5, 4), [np.nan, 1.0]], index=idx)
    g = pd.Series(["A"] * 8 + ["B"] * 4 + ["A", None], index=idx)
    z = robust_zscore(x, 3.0, groups=g)
    pooled = robust_zscore(x, 3.0)
    a = [i for i in idx[:8]]
    assert abs(z[a].mean()) < 1e-9 and z[a].std(ddof=0) == pytest.approx(1.0)
    # Grupo B (4 nomes < mínimo) e emissor sem grupo usam o z da cross-section inteira.
    b_or_none = idx[8:12] + [idx[13]]
    pd.testing.assert_series_equal(z[b_or_none], pooled[b_or_none])
    assert np.isnan(z[idx[12]])


def test_robust_zscore_degenerate_cases():
    few = pd.Series([1.0, 2.0, np.nan], index=list("abc"))
    assert robust_zscore(few, 3.0).isna().all()
    const = pd.Series([2.0, 2.0, 2.0, np.nan], index=list("abcd"))
    z = robust_zscore(const, 3.0)
    assert (z[:3] == 0.0).all() and np.isnan(z["d"])
    inf = pd.Series([1.0, 2.0, 3.0, np.inf, 4.0], index=list("abcde"))
    assert np.isnan(robust_zscore(inf, 3.0)["d"])
    with pytest.raises(ValueError):
        robust_zscore(inf, 0.0)


def test_neutralize_is_wls_orthogonal_and_preserves_nan():
    rng = np.random.default_rng(3)
    n = 40
    idx = [f"N{i}" for i in range(n)]
    X = pd.DataFrame({"mkt": 1.0, "f1": rng.normal(size=n), "f2": rng.normal(size=n)},
                     index=idx)
    X["dup"] = X["f1"] * 2.0  # colinear
    y = pd.Series(rng.normal(size=n), index=idx)
    w = pd.Series(rng.uniform(0.5, 2.0, n), index=idx)
    y.iloc[0] = np.nan
    X.iloc[1, 1] = np.nan
    w.iloc[2] = 0.0
    r = neutralize(y, X, w)
    assert r.iloc[:3].isna().all() and r.iloc[3:].notna().all()
    used = r.dropna().index
    np.testing.assert_allclose(X.loc[used].T @ (w[used] * r[used]), 0.0, atol=1e-10)
    r_ols = neutralize(y, X)
    np.testing.assert_allclose(X.dropna().loc[r_ols.dropna().index].T
                               @ r_ols.dropna(), 0.0, atol=1e-10)


def test_build_alpha_pure_alpha_orthogonal_to_exposures(alpha_res, model):
    a = alpha_res.alpha.dropna()
    assert len(a) >= 55
    W = 1.0 / model.specific_var[a.index]
    assert (W <= W.median() * MAX_WLS_WEIGHT_RATIO).all()  # sem teto ativo neste modelo
    B = model.exposures.loc[a.index]
    resid = B.T @ (W * a)
    scale = np.abs(B).T @ (W * alpha_res.alpha_raw[a.index].abs())
    assert (resid.abs() <= 1e-9 * scale + 1e-14).all()
    # A ortogonalização remove algo, mas preserva boa parte do alpha bruto.
    assert 0.3 < a.corr(alpha_res.alpha_raw[a.index]) < 1.0


def test_build_alpha_grinold_scaling_and_contributions(alpha_res, model, cfg):
    cz = alpha_res.composite_z.dropna()
    assert cz.abs().max() <= cfg.alpha.winsor_z + 1e-12
    assert abs(cz.mean()) < 0.05 and abs(cz.std(ddof=0) - 1.0) < 0.05
    horizon = np.sqrt(52.0 / cfg.alpha.horizon_weeks)  # IC no horizonte H, anualizado
    expected = cfg.alpha.information_coefficient * horizon * model.specific_vol[cz.index] * cz
    pd.testing.assert_series_equal(alpha_res.alpha_raw[cz.index], expected, check_names=False)
    total = alpha_res.contributions.sum(axis=1, min_count=1)
    np.testing.assert_allclose(total, alpha_res.alpha_raw, atol=1e-15, equal_nan=True)
    total_pure = alpha_res.contributions_pure.sum(axis=1, min_count=1)
    np.testing.assert_allclose(total_pure, alpha_res.alpha, atol=1e-12, equal_nan=True)
    assert sum(alpha_res.weights_used.values()) == pytest.approx(1.0)
    assert list(alpha_res.signal_z.columns) == list(alpha_res.weights_used)
    frame = alpha_res.to_frame()
    assert {"alpha", "alpha_raw", "composite_z", "coverage", "z_value"} <= set(frame.columns)
    assert any("Ortogonalização" in n for n in alpha_res.notes)


def test_build_alpha_nan_handling_and_exclusions(signals, model, cfg):
    raw = signals.copy()
    raw.loc["SIM003"] = np.nan                       # sem nenhum sinal
    raw.loc["SIM004", raw.columns != "quality"] = np.nan  # só um sinal
    raw.loc["FORA01"] = 1.0                          # fora do modelo de risco
    res = build_alpha(raw, model, cfg)
    assert np.isnan(res.alpha["SIM003"]) and res.coverage["SIM003"] == 0
    assert res.exclusion_reason["SIM003"] == "sem_sinais"
    assert np.isnan(res.alpha["FORA01"]) and res.coverage["FORA01"] == 0
    assert res.exclusion_reason["FORA01"] == "fora_do_modelo_de_risco"
    assert res.coverage["SIM004"] == 1 and np.isfinite(res.alpha["SIM004"])
    c4 = res.contributions.loc["SIM004"]
    assert c4.notna().sum() == 1
    assert c4["quality"] == pytest.approx(res.alpha_raw["SIM004"])
    assert res.exclusion_reason["SIM005"] == ""
    assert any("cobertura parcial" in n for n in res.notes)
    assert "SIM003" not in res.included and "SIM005" in res.included

    spec = model.specific_var.copy()
    spec["SIM007"] = np.nan
    res2 = build_alpha(signals, replace(model, specific_var=spec), cfg)
    assert np.isnan(res2.alpha["SIM007"])
    assert res2.exclusion_reason["SIM007"] == "sem_risco_especifico"


def test_build_alpha_weights_validation(signals, model, cfg):
    res = build_alpha(signals, model, cfg, weights={"quality": 2.0, "value": 2.0, "nao_ha": 1.0})
    assert res.weights_used == {"quality": 0.5, "value": 0.5}
    assert any("ausentes" in n for n in res.notes)
    res_np = build_alpha(signals, model, cfg,
                         weights={"quality": np.int64(1), "value": np.float64(3.0)})
    assert res_np.weights_used == {"quality": 0.25, "value": 0.75}
    with pytest.raises(ValueError):
        build_alpha(signals, model, cfg, weights={"quality": -1.0})
    with pytest.raises(ValueError):
        build_alpha(signals, model, cfg, weights={"quality": 0.0})
    with pytest.raises(ValueError):
        build_alpha(pd.concat([signals, signals.iloc[:1]]), model, cfg)


def test_build_alpha_without_orthogonalization(signals, model, cfg):
    cfg2 = cfg.with_overrides({"alpha": {"orthogonalize_to_factors": False}})
    res = build_alpha(signals, model, cfg2)
    pd.testing.assert_series_equal(res.alpha, res.alpha_raw)
    assert any("desligada" in n for n in res.notes)


def test_build_alpha_sector_grouping(signals, model, cfg, panel):
    sector = panel.assets["sector"]
    res = build_alpha(signals, model, cfg, sector=sector)
    z = res.signal_z["quality"]
    big = sector.value_counts()
    big = big[big >= 5].index
    for s in big:
        members = sector.index[sector == s]
        if z[members].notna().sum() >= 5:
            assert abs(z[members].mean()) < 0.2


def test_build_alpha_deterministic_and_inputs_untouched(signals, model, cfg):
    sig_before = signals.copy()
    spec_before = model.specific_var.copy()
    a = build_alpha(signals, model, cfg)
    b = build_alpha(signals, model, cfg)
    pd.testing.assert_series_equal(a.alpha, b.alpha)
    pd.testing.assert_frame_equal(signals, sig_before)
    pd.testing.assert_series_equal(model.specific_var, spec_before)


def test_wls_weights_cap_for_near_zero_specific_variance(signals, model, cfg):
    spec = model.specific_var.copy()
    spec["SIM012"] = 1e-30
    notes: list[str] = []
    w = wls_weights(spec, notes)
    assert w["SIM012"] == pytest.approx((1.0 / spec).median() * MAX_WLS_WEIGHT_RATIO)
    pd.testing.assert_series_equal(w.drop("SIM012"), 1.0 / spec.drop("SIM012"))
    assert notes
    res = build_alpha(signals, replace(model, specific_var=spec), cfg)
    a = res.alpha.dropna()
    B = model.exposures.loc[a.index]
    resid = B.T @ (w[a.index] * a)
    scale = np.abs(B).T @ (w[a.index] * res.alpha_raw[a.index].abs())
    assert (resid.abs() <= 1e-8 * scale + 1e-14).all()
    assert any("Peso WLS limitado" in n for n in res.notes)


def test_information_coefficient():
    idx = list("abcdefgh")
    s = pd.Series(np.arange(8.0), index=idx)
    assert information_coefficient(s, s ** 3) == pytest.approx(1.0)
    assert information_coefficient(s, -s) == pytest.approx(-1.0)
    assert information_coefficient(s, 2 * s + 1, method="pearson") == pytest.approx(1.0)
    r = s.copy()
    r.iloc[:6] = np.nan
    assert np.isnan(information_coefficient(s, r))
    assert np.isnan(information_coefficient(s, pd.Series(1.0, index=idx)))
    part = pd.Series([3.0, 1.0, 2.0, np.nan], index=["a", "b", "c", "zz"])
    assert information_coefficient(s, part) == pytest.approx(-0.5)
    with pytest.raises(ValueError):
        information_coefficient(s, s, method="kendall")


# ==========================================================
# Visões
# ==========================================================

def _view(issuer: str, source: ViewSource, score: int, conf: float = 1.0, **kw) -> View:
    return View(issuer_id=issuer, source=source, score=score, confidence=conf,
                rationale="teste", author="analista" if source == ViewSource.PM else "ia", **kw)


@pytest.fixture()
def base_alpha() -> tuple[pd.Series, pd.Series]:
    idx = pd.Index(["A", "B", "C", "D", "E"], name="issuer_id")
    alpha = pd.Series([0.01, -0.02, 0.0, np.nan, 0.005], index=idx, name="alpha")
    vol = pd.Series([0.25, 0.30, 0.20, 0.35, np.nan], index=idx)
    return alpha, vol


def test_view_tilt_is_bounded(base_alpha, cfg):
    alpha, vol = base_alpha
    rng = np.random.default_rng(5)
    for _ in range(50):
        score = int(rng.integers(-2, 3))
        conf = float(rng.uniform(0, 1))
        src = ViewSource.AI if rng.uniform() < 0.5 else ViewSource.PM
        adj, _, _ = apply_views(alpha, [_view("A", src, score, conf)], vol, cfg)
        ic = ai_view_ic(cfg) if src == ViewSource.AI else cfg.alpha.information_coefficient
        bound = ic * vol["A"] * cfg.alpha.max_view_tilt_z
        assert abs(adj["A"] - alpha["A"]) <= bound + 1e-15
    adj, _, log = apply_views(alpha, [_view("A", ViewSource.AI, 2, 1.0)], vol, cfg)
    expected = ai_view_ic(cfg) * 0.25 * cfg.alpha.max_view_tilt_z
    assert adj["A"] - alpha["A"] == pytest.approx(expected)
    assert adj.drop("A").equals(alpha.drop("A"))
    assert any("A:" in m for m in log)


def test_pm_view_replaces_ai_tilt(base_alpha, cfg):
    alpha, vol = base_alpha
    views = [_view("B", ViewSource.AI, 2, 1.0), _view("B", ViewSource.PM, -1, 0.5)]
    adj, _, log = apply_views(alpha, views, vol, cfg)
    z = -1 / 2 * cfg.alpha.max_view_tilt_z * 0.5
    assert adj["B"] - alpha["B"] == pytest.approx(cfg.alpha.information_coefficient * 0.30 * z)
    assert any("substitui" in m for m in log)
    table, _ = view_tilt_table(alpha, views, vol, cfg)
    assert table.loc["B", "source"] == "pm" and table.loc["B", "n_views"] == 2


def test_multiple_ai_views_are_averaged(base_alpha, cfg):
    alpha, vol = base_alpha
    views = [_view("C", ViewSource.AI, 2, 1.0), _view("C", ViewSource.AI, -2, 0.5)]
    adj, _, log = apply_views(alpha, views, vol, cfg)
    z = (1.0 * cfg.alpha.max_view_tilt_z + (-1.0) * cfg.alpha.max_view_tilt_z * 0.5) / 2
    expected = ai_view_ic(cfg) * 0.20 * z
    assert adj["C"] - alpha["C"] == pytest.approx(expected)
    assert any("média" in m for m in log)


def test_ai_views_only_tighten_constraints(base_alpha, cfg):
    alpha, vol = base_alpha
    mandate = mandate_max_abs_weight(cfg)
    views = [
        _view("A", ViewSource.AI, 0, 0.5, max_abs_weight=0.50),          # tenta afrouxar
        _view("B", ViewSource.PM, 1, 0.5, no_short=True),
        _view("B", ViewSource.AI, 1, 0.5, no_short=False),                # não desfaz o PM
        _view("C", ViewSource.AI, 0, 0.5, max_abs_weight=0.01),
        _view("C", ViewSource.PM, 0, 0.5, max_abs_weight=0.03),
        _view("E", ViewSource.AI, 0, 0.5, no_short=True),
        _view("E", ViewSource.AI, 0, 0.5, no_long=True),
    ]
    _, cons, log = apply_views(alpha, views, vol, cfg)
    assert list(cons.columns) == ["no_short", "no_long", "max_abs_weight"]
    assert list(cons.index) == list(alpha.index)
    assert cons.loc["A", "max_abs_weight"] == pytest.approx(mandate)
    assert bool(cons.loc["B", "no_short"]) and not bool(cons.loc["B", "no_long"])
    assert cons.loc["C", "max_abs_weight"] == pytest.approx(0.01)
    assert bool(cons.loc["E", "no_short"]) and bool(cons.loc["E", "no_long"])
    assert cons.loc["E", "max_abs_weight"] == 0.0
    assert np.isnan(cons.loc["D", "max_abs_weight"]) and not bool(cons.loc["D", "no_short"])
    assert any("limitado ao mandato" in m for m in log)
    assert (cons["max_abs_weight"].dropna() <= mandate).all()


def test_views_outside_universe_or_without_alpha(base_alpha, cfg):
    alpha, vol = base_alpha
    views = [_view("ZZZ", ViewSource.PM, 2, 1.0, no_short=True),
             _view("D", ViewSource.AI, 2, 1.0, no_short=True),   # alpha NaN
             _view("E", ViewSource.PM, 2, 1.0)]                   # vol NaN
    adj, cons, log = apply_views(alpha, views, vol, cfg)
    assert "ZZZ" not in adj.index and "ZZZ" not in cons.index
    assert np.isnan(adj["D"]) and bool(cons.loc["D", "no_short"])
    assert adj["E"] == alpha["E"]
    assert any("ZZZ" in m and "fora do universo" in m for m in log)
    assert any("D:" in m and "sem alpha base" in m for m in log)
    assert any("E:" in m and "sem volatilidade" in m for m in log)


def test_apply_views_does_not_mutate_inputs(base_alpha, cfg):
    alpha, vol = base_alpha
    a0, v0 = alpha.copy(), vol.copy()
    views = [_view("A", ViewSource.AI, -2, 0.8, max_abs_weight=0.02),
             {"issuer_id": "B", "source": "pm", "score": 1, "confidence": 0.7,
              "rationale": "tese", "author": "gestor"}]
    snapshot = [v.model_dump() if isinstance(v, View) else dict(v) for v in views]
    adj, _, _ = apply_views(alpha, views, vol, cfg)
    pd.testing.assert_series_equal(alpha, a0)
    pd.testing.assert_series_equal(vol, v0)
    assert [v.model_dump() if isinstance(v, View) else dict(v) for v in views] == snapshot
    assert adj is not alpha and adj.name == alpha.name
    assert adj["A"] < alpha["A"] and adj["B"] > alpha["B"]


def test_views_accept_non_float_alpha_dtype(cfg):
    alpha = pd.Series([1, -1, 0], index=["A", "B", "C"])  # dtype inteiro
    vol = pd.Series([0.2, 0.2, 0.2], index=["A", "B", "C"])
    adj, _, _ = apply_views(alpha, [_view("A", ViewSource.PM, 2, 1.0)], vol, cfg)
    assert adj["A"] > 1.0 and adj.dtype == float
    pd.testing.assert_series_equal(alpha, pd.Series([1, -1, 0], index=["A", "B", "C"]))


def test_views_end_to_end_with_alpha(alpha_res, model, cfg):
    a = alpha_res.alpha
    top = a.dropna().idxmax()
    views = [_view(top, ViewSource.AI, -2, 1.0, no_long=True)]
    adj, cons, _ = apply_views(a, views, model.specific_vol, cfg)
    assert adj[top] < a[top]
    assert bool(cons.loc[top, "no_long"])
    assert adj.drop(top).equals(a.drop(top))


# ==========================================================
# Revisão adversarial: testes que expõem bugs corrigidos
# ==========================================================

def _single_line_issuer(md: MarketData, country: str) -> tuple[str, str]:
    """(emissor, ticker) de um emissor com uma única linha (local) no país."""
    iss = md.universe.issuers
    sub = iss[(iss["country"] == country) & (iss["n_lines"] == 1)]
    iid = str(sub.index[0])
    return iid, str(sub.loc[iid, "primary_ticker"])


def test_market_residuals_have_zero_covariance_with_market(panel, md, as_of):
    """Beta MQO correto: o resíduo (com intercepto) não covaria com o mercado na janela."""
    resid, _ = residual_returns(panel, md, None, as_of)
    R_all = panel.returns.loc[panel.returns.index <= as_of]
    rm, _ = _cap_weighted_market(R_all, cap_weights_usd(md, as_of))
    M = _market_over_gaps(R_all, rm).loc[resid.index]
    for iid in resid.columns[resid.notna().sum() >= 60]:
        e, m = resid[iid], M[iid]
        ok = e.notna() & m.notna()
        cov = float(((e[ok] - e[ok].mean()) * (m[ok] - m[ok].mean())).mean())
        assert abs(cov) < 1e-12, iid


def test_value_fx_corrects_mixed_currency_multiples_on_local_line(md, panel, as_of, ids):
    """Caso real SQM-B.SN: linha local em CLP, balanço em USD, P/B = 2.889, EV/EBITDA = 6.071."""
    iid, tkr = _single_line_issuer(md, "CL")
    md2 = _with_fundamentals(md, {(tkr, "financial_currency"): "USD",
                                  (tkr, "price_to_book"): 2889.0,
                                  (tkr, "enterprise_to_ebitda"): 6071.0})
    comp = value_components(md2, ids, as_of)
    fx_clp = float(md.fx["CLP"].loc[md.fx.index <= as_of].iloc[-1])
    assert comp.loc[iid, "currency_status"] == "fx_corrigido"
    assert comp.loc[iid, "book_to_price"] == pytest.approx(1.0 / 2889.0 / fx_clp)
    assert comp.loc[iid, "ebitda_to_ev"] == pytest.approx(1.0 / 6071.0 / fx_clp)
    assert 0.2 < comp.loc[iid, "book_to_price"] < 0.5  # P/VPA real ≈ 3,1
    v = compute_signals(panel, md2, None, as_of, ids, names=["value"])
    assert v["value"].rank(pct=True)[iid] > 0.2  # antes: entre os 7% mais "caros"
    assert any("corrigidos pelo câmbio" in n for n in v.attrs["notes"])


def test_value_discards_multiples_of_adr_with_foreign_financials(md, panel, as_of, ids):
    """ADR com balanço em moeda local (CIB, GGAL): múltiplos da fonte misturam moeda e razão."""
    iid, local, adr = _local_primary_with_adr(md)
    md2 = replace(md, fundamentals=md.fundamentals.drop(index=local))
    comp = value_components(md2, ids, as_of)
    assert comp.loc[iid, "ticker"] == adr
    assert comp.loc[iid, "currency_status"] == "adr_moeda_divergente"
    assert comp.loc[iid, ["earnings_yield", "book_to_price", "ebitda_to_ev"]].isna().all()
    v = compute_signals(panel, md2, None, as_of, ids, names=["value"])
    assert np.isnan(v.loc[iid, "value"])  # ausente ⇒ NaN, nunca zero
    assert any("ADR com moeda do balanço" in n for n in v.attrs["notes"])


def test_value_implausible_multiple_is_discarded(md, panel, as_of, ids):
    """CIB P/B = 0,00207 (preço USD / PL COP): fora da faixa plausível ⇒ componente NaN."""
    iid, local, _ = _local_primary_with_adr(md)
    md2 = _with_fundamentals(md, {(local, "price_to_book"): 0.00207})
    comp = value_components(md2, ids, as_of)
    assert np.isnan(comp.loc[iid, "book_to_price"])
    assert comp.loc[iid, "flag"] == "book_to_price_implausivel"
    assert np.isfinite(comp.loc[iid, "earnings_yield"])
    v = compute_signals(panel, md2, None, as_of, ids, names=["value"])
    assert np.isfinite(v.loc[iid, "value"])
    assert any("fora da faixa plausível" in n for n in v.attrs["notes"])


def test_line_selection_requires_line_currency_to_match(md, ids):
    """Fonte rotulando um ADR (USD) com moeda local não torna a linha 'coerente'."""
    iss = md.universe.issuers
    ar = str(iss.index[(iss["country"] == "AR")][0])
    adr = str(iss.loc[ar, "primary_ticker"])  # na Argentina a linha primária é o ADR
    assert md.universe.lines.loc[adr, "line_type"] == "ADR"
    md2 = _with_fundamentals(md, {(adr, "currency"): "ARS"})
    sel = select_fundamental_lines(md2, ids, VALUE_FIELDS)
    assert sel.loc[ar, "ticker"] != adr and sel.loc[ar, "line_currency"] == "ARS"
    assert bool(sel.loc[ar, "currency_match"])
    # Sem a linha local, o ADR rotulado errado é classificado como inconsistente.
    lines = md.universe.lines
    local = [t for t in lines.index[lines["issuer_id"] == ar] if t != adr][0]
    md3 = replace(md2, fundamentals=md2.fundamentals.drop(index=local))
    comp = value_components(md3, ids, pd.Timestamp(md.close.index[-1]))
    assert comp.loc[ar, "currency_status"] == "cotacao_inconsistente"
    assert comp.loc[ar, ["earnings_yield", "book_to_price", "ebitda_to_ev"]].isna().all()


def test_quality_ignores_roe_when_equity_is_negative(md, panel, as_of, ids):
    """PL negativo: prejuízo ÷ PL negativo dá ROE positivo enorme — não pode virar qualidade."""
    iid, local, _ = _local_primary_with_adr(md)
    bad = _with_fundamentals(md, {(local, "debt_to_equity"): -40.0,
                                  (local, "return_on_equity"): 3.0})
    ref = _with_fundamentals(md, {(local, "debt_to_equity"): np.nan,
                                  (local, "return_on_equity"): np.nan})
    q_bad = compute_signals(panel, bad, None, as_of, ids, names=["quality"])
    q_ref = compute_signals(panel, ref, None, as_of, ids, names=["quality"])
    pd.testing.assert_series_equal(q_bad["quality"], q_ref["quality"])
    assert any("ROE tratados como ausentes" in n for n in q_bad.attrs["notes"])


def test_analyst_flags_missing_price_and_adr_ratio_errors(md, as_of, ids):
    inp = analyst_inputs(md, ids, as_of)
    iid, _, _ = _local_primary_with_adr(md)
    tkr = inp.loc[iid, "ticker"]
    close = md.close.copy()
    close[tkr] = np.nan
    no_px = analyst_inputs(replace(md, close=close), ids, as_of).loc[iid]
    assert no_px["flag"] == "sem_preco" and np.isnan(no_px["upside"])
    assert np.isfinite(no_px["rec_score"])  # recomendação continua válida
    # Preço-alvo por ação local contra preço por ADR de 5 ações: upside ≈ −78% ⇒ descartado.
    px = float(inp.loc[iid, "price"])
    md_ratio = _with_fundamentals(md, {(tkr, "target_mean_price"): px * 1.1 / 5.0})
    row = analyst_inputs(md_ratio, ids, as_of).loc[iid]
    assert row["flag"] == "upside_implausivel" and np.isnan(row["upside"])


def _toy_model(ids: list[str], spec_var: float = 0.09) -> RiskModel:
    idx = pd.Index(ids, name="issuer_id")
    B = pd.DataFrame({"market": 1.0}, index=idx)
    F = pd.DataFrame([[0.04]], index=["market"], columns=["market"])
    return RiskModel(as_of=date(2026, 10, 2), exposures=B, factor_cov=F,
                     specific_var=pd.Series(spec_var, index=idx),
                     factor_returns=pd.DataFrame(columns=["market"], dtype=float),
                     specific_returns=pd.DataFrame(columns=ids, dtype=float),
                     factor_groups={"market": "market"})


def test_partial_coverage_does_not_inflate_composite(cfg):
    """Emissor com um único sinal não pode ter |z| sistematicamente maior que o coberto."""
    rng = np.random.default_rng(42)
    n = 4000
    ids = [f"X{i:04d}" for i in range(n)]
    common = rng.normal(size=n)
    raw = pd.DataFrame({
        "residual_momentum": np.sqrt(0.5) * common + np.sqrt(0.5) * rng.normal(size=n),
        "value": np.sqrt(0.5) * common + np.sqrt(0.5) * rng.normal(size=n),  # ρ ≈ 0,5
        "quality": rng.normal(size=n),
        "low_risk": rng.normal(size=n),
    }, index=ids)
    single = ids[: n // 2]
    for k, iid in enumerate(single):
        keep = raw.columns[k % 4]
        raw.loc[iid, raw.columns != keep] = np.nan
    w = {c: 0.25 for c in raw.columns}
    res = build_alpha(raw, _toy_model(ids), cfg, weights=w)
    full = ids[n // 2:]
    ratio = res.composite_z[single].std() / res.composite_z[full].std()
    assert 0.9 < ratio < 1.1  # sem a normalização: ≈ 1,8
    total = res.contributions.sum(axis=1, min_count=1)
    np.testing.assert_allclose(total, res.alpha_raw, atol=1e-15, equal_nan=True)
    assert any("normalizado pelo desvio esperado" in m for m in res.notes)


def test_signal_correlation_is_positive_definite_and_handles_missing_pairs():
    """Correlações por pares podem ser inconsistentes (não PSD); a matriz usada é PD."""
    rng = np.random.default_rng(9)
    base = rng.normal(size=60)
    z = pd.DataFrame(np.nan, index=range(60), columns=["s1", "s2", "s3", "s4"])
    z.loc[0:19, "s1"] = base[0:20]
    z.loc[0:19, "s2"] = base[0:20] + 0.05 * rng.normal(size=20)    # ρ(s1,s2) ≈ +1
    z.loc[20:39, "s2"] = base[20:40]
    z.loc[20:39, "s3"] = base[20:40] + 0.05 * rng.normal(size=20)   # ρ(s2,s3) ≈ +1
    z.loc[40:59, "s1"] = base[40:60]
    z.loc[40:59, "s3"] = -base[40:60] + 0.05 * rng.normal(size=20)  # ρ(s1,s3) ≈ −1
    z.loc[0:5, "s4"] = rng.normal(size=6)                           # sem pares suficientes
    raw_c = z.corr(min_periods=10).to_numpy()[:3, :3]
    assert np.linalg.eigvalsh(raw_c).min() < -0.5  # inconsistente de fato
    notes: list[str] = []
    c = signal_correlation(z, notes)
    vals = np.linalg.eigvalsh(c.to_numpy())
    assert vals.min() > 0.5 * CORR_EIGEN_FLOOR
    np.testing.assert_allclose(np.diag(c.to_numpy()), 1.0)
    assert c.loc["s4", "s1"] == 0.0 and any("assumida 0" in m for m in notes)
    a = pd.DataFrame([[0.5, 0.0, 0.5, 0.0], [np.nan] * 4], columns=c.columns, index=["a", "b"])
    s = coverage_scale(a, c)
    assert s["a"] > 0 and np.isnan(s["b"])


def test_ai_view_ic_follows_adoption_phase(base_alpha, cfg):
    """Fase S0 (shadow): IA não move o alpha, mas as restrições valem; IC nunca passa a fase."""
    alpha, vol = base_alpha
    views = [_view("A", ViewSource.AI, 2, 1.0, no_short=True)]
    s0 = cfg.with_overrides({"research": {"llm_phase": "S0"}})
    adj, cons, log = apply_views(alpha, views, vol, s0)
    assert adj["A"] == alpha["A"] and bool(cons.loc["A", "no_short"])
    assert any("shadow" in m for m in log)
    assert ai_view_ic(cfg) == pytest.approx(cfg.research.llm_view_ic)  # S1 padrão = 0,01
    adj1, _, _ = apply_views(alpha, views, vol, cfg)
    assert adj1["A"] - alpha["A"] == pytest.approx(0.01 * 0.25 * cfg.alpha.max_view_tilt_z)
    capped = cfg.with_overrides({"research": {"llm_phase": "S3"},
                                 "alpha": {"view_information_coefficient": 0.005}})
    assert ai_view_ic(capped) == pytest.approx(0.005)
    # Gestor (PM) usa o IC do alpha quantitativo, independentemente da fase da IA.
    pm = apply_views(alpha, [_view("A", ViewSource.PM, 2, 1.0)], vol, s0)[0]
    expected = cfg.alpha.information_coefficient * 0.25 * cfg.alpha.max_view_tilt_z
    assert pm["A"] - alpha["A"] == pytest.approx(expected)


def test_line_selection_prefers_usable_local_line_without_currency_info(md, as_of, ids):
    """Sem moeda do balanço na fonte: emissor argentino (ADR primário) usa a linha local .BA,
    cujos múltiplos são aproveitáveis, em vez do ADR (múltiplos descartados)."""
    f = md.fundamentals.drop(columns=["financial_currency"])
    comp = value_components(replace(md, fundamentals=f), ids, as_of)
    iss = md.universe.issuers
    for ar in iss.index[iss["country"] == "AR"]:
        assert comp.loc[ar, "line_type"] == "LOCAL"
        assert comp.loc[ar, "currency_status"] == "moeda_fin_desconhecida"
        assert np.isfinite(comp.loc[ar, "earnings_yield"])
    # Sem câmbio (as_of anterior ao histórico): P/L mantido, P/VPA e EV/EBITDA descartados.
    early = value_components(md, ids, pd.Timestamp("2023-06-01"))
    nofx = early.index[early["currency_status"] == "sem_cambio"]
    assert len(nofx) >= 1
    assert early.loc[nofx, "earnings_yield"].notna().all()
    assert early.loc[nofx, ["book_to_price", "ebitda_to_ev"]].isna().all().all()
