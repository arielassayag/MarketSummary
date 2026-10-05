"""Testes de liquidez, disponibilidade de aluguel e risco de short squeeze (DADOS SIMULADOS)."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from latam_ls.analytics.liquidity import (
    days_to_liquidate,
    horizon_column,
    liquidity_profile,
    liquidity_summary,
    liquidity_tier,
    max_weight_by_liquidity,
)
from latam_ls.analytics.panel import build_asset_panel
from latam_ls.analytics.shortability import (
    AVAILABILITY_COLUMNS,
    FEE_SOURCE_B3,
    FEE_SOURCE_GC_BR,
    FEE_SOURCE_GC_US,
    FEE_SOURCE_NA,
    REASON_BR_NO_LENDING,
    REASON_LOCAL_OFFSHORE,
    REASON_NO_DATA,
    SIDE_LINE_COLUMNS,
    US_HTB_FEE_ESTIMATE,
    US_SPECIAL_FEE_ESTIMATE,
    issuer_side_lines,
    short_availability,
)
from latam_ls.analytics.squeeze import (
    SQUEEZE_COLUMNS,
    catalyst_score,
    composite_squeeze_score,
    effective_bucket,
    float_score,
    short_cap_multiplier,
    squeeze_bucket,
    squeeze_table,
    threshold_score,
)
from latam_ls.config import FundConfig
from latam_ls.data.synthetic import make_synthetic_market

START = date(2024, 1, 2)
NAV = 100_000_000.0


# ----------------------------------------------------------------------------------------
# Fixtures (mercado SIMULADO pequeno, reaproveitado no módulo)
# ----------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cfg() -> FundConfig:
    return FundConfig()


@pytest.fixture(scope="module")
def md():
    return make_synthetic_market(seed=7, start=START)


@pytest.fixture(scope="module")
def panel(md, cfg):
    return build_asset_panel(md, cfg)


@pytest.fixture(scope="module")
def avail(panel, md, cfg):
    return short_availability(panel, md, cfg)


@pytest.fixture(scope="module")
def sq(panel, md, avail, cfg):
    return squeeze_table(panel, md, avail, cfg)


@pytest.fixture(scope="module")
def hot_ticker(md) -> str:
    si = md.short_interest["short_pct_float"]
    hot = si.index[si >= 0.30]
    assert len(hot) == 1
    return str(hot[0])


def _lines_where(panel, **conds) -> list[str]:
    mask = pd.Series(True, index=panel.lines.index)
    for col, val in conds.items():
        mask &= panel.lines[col] == val
    return list(panel.lines.index[mask])


def _br_issuer_with_adr(panel) -> tuple[str, str, str]:
    lines = panel.lines
    for iid, grp in lines.groupby("issuer_id"):
        types = set(grp["line_type"])
        if grp["market"].eq("BR").any() and "ADR" in types:
            local = grp.index[(grp["market"] == "BR")][0]
            adr = grp.index[grp["line_type"] == "ADR"][0]
            return str(iid), str(local), str(adr)
    raise AssertionError("Universo simulado sem emissor BR com ADR")


# ----------------------------------------------------------------------------------------
# Liquidez
# ----------------------------------------------------------------------------------------

def test_liquidity_tier_breaks_and_nan():
    adtv = pd.Series([60e6, 50e6, 20e6, 15e6, 6e6, 5e6, 1e6, 0.0, np.nan],
                     index=list("abcdefghi"))
    tiers = liquidity_tier(adtv, [50e6, 15e6, 5e6])
    assert tiers.tolist() == ["T1", "T1", "T2", "T2", "T3", "T3", "T4", "T4", "T4"]
    assert list(tiers.index) == list(adtv.index)


@pytest.mark.parametrize("bad", [[15e6, 50e6, 5e6], [50e6, 50e6, 5e6], [], [np.nan, 1.0]])
def test_liquidity_tier_rejects_bad_breaks(bad):
    with pytest.raises(ValueError):
        liquidity_tier(pd.Series([1.0]), bad)


def test_days_to_liquidate_rules():
    notional = pd.Series({"A": 10e6, "B": -10e6, "C": 5e6, "D": 5e6, "E": 0.0, "F": np.nan,
                          "G": 1e6})
    adtv = pd.Series({"A": 50e6, "B": 25e6, "C": np.nan, "D": 0.0, "E": np.nan, "F": 10e6})
    d = days_to_liquidate(notional, adtv, 0.2)
    assert d["A"] == pytest.approx(1.0)
    assert d["B"] == pytest.approx(2.0)  # vendido: usa |nocional|
    assert math.isinf(d["C"]) and math.isinf(d["D"])  # ADTV ausente/zero ⇒ inf
    assert d["E"] == 0.0  # nada a liquidar
    assert math.isnan(d["F"])  # nocional ausente continua ausente
    assert math.isinf(d["G"])  # ticker sem ADTV no índice ⇒ inf
    with pytest.raises(ValueError):
        days_to_liquidate(notional, adtv, 0.0)
    with pytest.raises(ValueError):
        days_to_liquidate(notional, adtv, 1.5)


def test_max_weight_by_liquidity():
    adtv = pd.Series({"A": 50e6, "B": np.nan, "C": -1.0, "D": 1e6})
    cap = max_weight_by_liquidity(adtv, NAV, 0.2, 3.0)
    assert cap["A"] == pytest.approx(0.30)
    assert cap["B"] == 0.0 and cap["C"] == 0.0  # sem ADTV utilizável ⇒ não negociável
    assert cap["D"] == pytest.approx(0.006)
    with pytest.raises(ValueError):
        max_weight_by_liquidity(adtv, 0.0, 0.2, 3.0)
    with pytest.raises(ValueError):
        max_weight_by_liquidity(adtv, NAV, 0.2, -1.0)


def test_liquidity_profile_hand_computed():
    w = pd.Series({"A": 0.04, "B": -0.02, "C": 0.01, "D": -0.03, "Z": 0.0})
    adtv = pd.Series({"A": 10e6, "B": 5e6, "C": 100e6})  # D sem ADTV
    prof = liquidity_profile(w, adtv, NAV, 0.2, horizons=(1, 2, 3, 5, 10))
    assert list(prof.index) == ["A", "B", "C", "D"]  # peso zero fica de fora
    assert prof.loc["A", "days_to_liquidate"] == pytest.approx(2.0)
    assert prof.loc["B", "days_to_liquidate"] == pytest.approx(2.0)
    assert prof.loc["C", "days_to_liquidate"] == pytest.approx(0.05)
    assert math.isinf(prof.loc["D", "days_to_liquidate"])
    assert bool(prof.loc["D", "adtv_missing"]) and not bool(prof.loc["A", "adtv_missing"])
    assert prof["side"].tolist() == ["LONG", "SHORT", "LONG", "SHORT"]
    assert prof.loc["B", "notional_usd"] == pytest.approx(-2e6)

    totals = prof[[horizon_column(h) for h in (1, 2, 3, 5, 10)]].sum()
    # gross = 0.10; 1d: 0.02 + 0.01 + 0.01 + 0 = 0.04; 2d em diante: 0.07 (D nunca liquida)
    assert totals[horizon_column(1)] == pytest.approx(0.4)
    for h in (2, 3, 5, 10):
        assert totals[horizon_column(h)] == pytest.approx(0.7)
    # cada nome limitado ao próprio tamanho
    share = w[w != 0].abs() / 0.10
    for h in (1, 2, 3, 5, 10):
        assert (prof[horizon_column(h)] <= share + 1e-12).all()

    summ = liquidity_summary(prof)
    assert list(summ.index) == [1.0, 2.0, 3.0, 5.0, 10.0]
    assert summ.loc[1.0, "gross"] == pytest.approx(0.4)
    assert summ.loc[1.0, "long"] == pytest.approx(0.03 / 0.05)
    assert summ.loc[1.0, "short"] == pytest.approx(0.01 / 0.05)
    assert summ.loc[10.0, "long"] == pytest.approx(1.0)
    assert summ.loc[10.0, "short"] == pytest.approx(0.02 / 0.05)


def test_liquidity_profile_validation_and_empty():
    adtv = pd.Series({"A": 10e6})
    with pytest.raises(ValueError):
        liquidity_profile(pd.Series({"A": np.nan}), adtv, NAV, 0.2)
    with pytest.raises(ValueError):
        liquidity_profile(pd.Series({"A": 0.01}), adtv, NAV, 0.2, horizons=(0, 1))
    empty = liquidity_profile(pd.Series({"A": 0.0}), adtv, NAV, 0.2)
    assert empty.empty and horizon_column(1) in empty.columns
    summ = liquidity_summary(empty)
    assert summ.isna().all().all()


def test_liquidity_profile_on_synthetic_panel(panel, cfg):
    elig = panel.eligible[:20]
    rng = np.random.default_rng(0)
    w = pd.Series(rng.uniform(0.005, 0.03, len(elig)) * np.where(np.arange(len(elig)) % 2, 1, -1),
                  index=elig)
    prof = liquidity_profile(w, panel.assets["adtv_usd"], NAV, cfg.liquidity.participation_rate)
    cols = [horizon_column(h) for h in (1, 2, 3, 5, 10)]
    totals = prof[cols].sum()
    assert (totals.diff().dropna() >= -1e-12).all()  # monotônico no horizonte
    assert totals.max() <= 1.0 + 1e-12
    # nomes elegíveis têm ADTV >= 2 mi ⇒ posições <= 3% liquidam em <= 7,5 dias
    assert totals[horizon_column(10)] == pytest.approx(1.0)
    expected_days = (w.abs() * NAV) / (cfg.liquidity.participation_rate
                                       * panel.assets.loc[elig, "adtv_usd"])
    pd.testing.assert_series_equal(prof["days_to_liquidate"], expected_days,
                                   check_names=False)


# ----------------------------------------------------------------------------------------
# Disponibilidade de aluguel
# ----------------------------------------------------------------------------------------

def test_availability_schema(avail, panel):
    assert list(avail.columns) == AVAILABILITY_COLUMNS
    assert set(avail.index) == set(panel.lines.index)
    assert avail["shortable"].dtype == bool
    assert set(avail["fee_source"]) <= {FEE_SOURCE_B3, FEE_SOURCE_GC_US, FEE_SOURCE_GC_BR,
                                        FEE_SOURCE_NA}
    # fonte NA ⇔ taxa NaN (nunca zero)
    na_src = avail["fee_source"] == FEE_SOURCE_NA
    assert avail.loc[na_src, "borrow_fee_annual"].isna().all()
    assert avail.loc[~na_src, "borrow_fee_annual"].notna().all()
    assert (avail["borrow_fee_annual"].dropna() > 0).all()
    assert avail["reason"].map(lambda s: isinstance(s, str) and len(s) > 0).all()


def test_hot_adr_not_shortable(avail, hot_ticker, cfg):
    row = avail.loc[hot_ticker]
    assert row["fee_source"] == FEE_SOURCE_GC_US and bool(row["fee_is_estimate"])
    assert row["borrow_fee_annual"] == pytest.approx(US_SPECIAL_FEE_ESTIMATE)
    assert US_SPECIAL_FEE_ESTIMATE > cfg.shorting.max_borrow_fee
    assert not row["shortable"]
    assert "acima do máximo" in row["reason"]


def test_br_locals_use_b3_fees(avail, panel, md, cfg):
    br_local = _lines_where(panel, market="BR", line_type="LOCAL")
    with_rate = [t for t in br_local if t in md.lending.index]
    assert len(with_rate) == len(br_local) > 0
    rates = md.lending.loc[with_rate, "lending_rate_annual"].astype(float)
    sub = avail.loc[with_rate]
    assert (sub["fee_source"] == FEE_SOURCE_B3).all()
    assert not sub["fee_is_estimate"].any()
    np.testing.assert_allclose(sub["borrow_fee_annual"].to_numpy(), rates.to_numpy())
    expected = rates <= cfg.shorting.max_borrow_fee
    assert (sub["shortable"] == expected).all()


@pytest.mark.parametrize("market", ["MX", "CL", "CO", "PE", "AR"])
def test_other_local_markets_not_shortable(avail, panel, market):
    tickers = _lines_where(panel, market=market, line_type="LOCAL")
    assert tickers
    sub = avail.loc[tickers]
    assert not sub["shortable"].any()
    assert (sub["reason"] == REASON_LOCAL_OFFSHORE).all()
    assert sub["borrow_fee_annual"].isna().all()
    assert (sub["fee_source"] == FEE_SOURCE_NA).all()


def test_regular_adrs_shortable_with_gc_estimate(avail, panel, md, cfg):
    usd = avail[avail["line_type"].isin(["ADR", "US_LISTED"])]
    si = md.short_interest["short_pct_float"].reindex(usd.index)
    normal = usd[si < cfg.squeeze.si_pct_float_high]
    assert len(normal) > 10
    assert normal["shortable"].all()
    assert (normal["borrow_fee_annual"] == cfg.shorting.gc_borrow_fee_us).all()
    assert normal["fee_is_estimate"].all()


def test_si_escalation_and_mcap_rules(panel, md, cfg):
    adrs = [t for t in _lines_where(panel, line_type="ADR")
            if md.short_interest.loc[t, "short_pct_float"] < 0.15]
    a_htb, a_special, a_small, a_nan_mcap, a_no_si = adrs[:5]
    si = md.short_interest.copy()
    si.loc[a_htb, "short_pct_float"] = 0.16
    si.loc[a_special, "short_pct_float"] = 0.31
    si = si.drop(index=a_no_si)
    assets = panel.assets.copy()
    small_iid = panel.lines.loc[a_small, "issuer_id"]
    nan_iid = panel.lines.loc[a_nan_mcap, "issuer_id"]
    assets.loc[small_iid, "market_cap_usd"] = 300e6
    assets.loc[nan_iid, "market_cap_usd"] = np.nan
    av = short_availability(replace(panel, assets=assets), replace(md, short_interest=si), cfg)

    assert av.loc[a_htb, "borrow_fee_annual"] == pytest.approx(US_HTB_FEE_ESTIMATE)
    assert bool(av.loc[a_htb, "shortable"])
    assert "short interest alto" in av.loc[a_htb, "reason"]
    assert av.loc[a_special, "borrow_fee_annual"] == pytest.approx(US_SPECIAL_FEE_ESTIMATE)
    assert not av.loc[a_special, "shortable"]
    assert not av.loc[a_small, "shortable"] and "abaixo do mínimo" in av.loc[a_small, "reason"]
    assert not av.loc[a_nan_mcap, "shortable"] and "ausente" in av.loc[a_nan_mcap, "reason"]
    # sem short interest: continua alugável com GC estimada, sinalizado no motivo
    assert bool(av.loc[a_no_si, "shortable"])
    assert av.loc[a_no_si, "borrow_fee_annual"] == pytest.approx(cfg.shorting.gc_borrow_fee_us)
    assert "sem dado de short interest" in av.loc[a_no_si, "reason"]


def test_br_without_lending_data(panel, md, cfg):
    br_local = _lines_where(panel, market="BR", line_type="LOCAL")
    iss = panel.lines.loc[br_local, "issuer_id"]
    big = [t for t in br_local
           if panel.assets.loc[iss[t], "adtv_usd"] >= 10e6
           and panel.assets.loc[iss[t], "market_cap_usd"] >= 1e9]
    small = [t for t in br_local if panel.assets.loc[iss[t], "adtv_usd"] < 10e6]
    assert big and small
    t_big, t_small, t_hi_fee, t_bad = big[0], small[0], big[1], big[2]
    lending = md.lending.drop(index=[t_big, t_small]).copy()
    lending.loc[t_hi_fee, "lending_rate_annual"] = 0.20
    lending.loc[t_bad, "lending_rate_annual"] = -0.01  # inválido ⇒ ausente
    av = short_availability(panel, replace(md, lending=lending), cfg)

    assert av.loc[t_big, "fee_source"] == FEE_SOURCE_GC_BR
    assert av.loc[t_big, "borrow_fee_annual"] == pytest.approx(cfg.shorting.gc_borrow_fee_br)
    assert bool(av.loc[t_big, "shortable"])
    assert av.loc[t_small, "fee_source"] == FEE_SOURCE_NA
    assert math.isnan(av.loc[t_small, "borrow_fee_annual"])
    assert not av.loc[t_small, "shortable"]
    assert av.loc[t_small, "reason"] == REASON_BR_NO_LENDING
    assert av.loc[t_hi_fee, "fee_source"] == FEE_SOURCE_B3
    assert av.loc[t_hi_fee, "borrow_fee_annual"] == pytest.approx(0.20)
    assert not av.loc[t_hi_fee, "shortable"]
    assert av.loc[t_bad, "fee_source"] == FEE_SOURCE_GC_BR  # taxa inválida tratada como ausente


def test_no_price_data_and_config_exclusion(panel, md, cfg):
    _, local, adr = _br_issuer_with_adr(panel)
    lines = panel.lines.copy()
    lines.loc[adr, "has_data"] = False
    av = short_availability(replace(panel, lines=lines), md, cfg)
    assert not av.loc[adr, "shortable"] and av.loc[adr, "reason"] == REASON_NO_DATA

    cfg_no_br = cfg.with_overrides({"shorting": {"shortable_line_types": ["ADR", "US_LISTED"]}})
    av2 = short_availability(panel, md, cfg_no_br)
    br_local = _lines_where(panel, market="BR", line_type="LOCAL")
    assert not av2.loc[br_local, "shortable"].any()
    assert av2.loc[local, "reason"].startswith("tipo de linha LOCAL_BR")
    # a taxa continua informada (alimenta o escore de squeeze)
    assert (av2.loc[br_local, "fee_source"] == FEE_SOURCE_B3).all()
    assert bool(av2.loc[adr, "shortable"])


# ----------------------------------------------------------------------------------------
# Linhas de execução por emissor
# ----------------------------------------------------------------------------------------

def test_side_lines_schema_and_non_shortable(panel, avail, hot_ticker):
    side = issuer_side_lines(panel, avail)
    assert list(side.columns) == SIDE_LINE_COLUMNS
    assert list(side.index) == list(panel.assets.index)
    assert side["long_ticker"].notna().all()
    mx_only = [i for i, g in panel.lines.groupby("issuer_id")
               if set(g["market"]) == {"MX"}]
    assert mx_only
    sub = side.loc[mx_only]
    assert not sub["can_short"].any()
    assert sub["short_ticker"].map(lambda x: x is None).all()
    assert sub["adtv_short_usd"].isna().all() and sub["borrow_fee_annual"].isna().all()
    assert (sub["fee_source"] == FEE_SOURCE_NA).all()
    assert sub["short_reason"].str.contains("usar ADR").all()
    hot_iid = panel.lines.loc[hot_ticker, "issuer_id"]
    assert not side.loc[hot_iid, "can_short"]
    shortable = side[side["can_short"]]
    assert (avail.loc[shortable["short_ticker"], "shortable"]).all()


@pytest.mark.parametrize(("local_adtv", "adr_adtv", "expected"), [
    (100e6, 95e6, "adr"),    # empate (dentro de 10%) ⇒ ADR
    (100e6, 90e6, "adr"),    # exatamente no limite de 10%
    (100e6, 80e6, "local"),  # local claramente mais líquida
    (80e6, 100e6, "adr"),
])
def test_side_lines_prefer_adr_on_ties(panel, avail, local_adtv, adr_adtv, expected):
    iid, local, adr = _br_issuer_with_adr(panel)
    lines = panel.lines.copy()
    lines.loc[local, "adtv_usd"] = local_adtv
    lines.loc[adr, "adtv_usd"] = adr_adtv
    av = avail.copy()
    av.loc[[local, adr], "shortable"] = True
    side = issuer_side_lines(replace(panel, lines=lines), av)
    want = adr if expected == "adr" else local
    assert side.loc[iid, "long_ticker"] == want
    assert side.loc[iid, "short_ticker"] == want
    assert side.loc[iid, "adtv_long_usd"] == pytest.approx(lines.loc[want, "adtv_usd"])
    assert side.loc[iid, "fee_source"] == av.loc[want, "fee_source"]
    assert side.loc[iid, "long_currency"] == lines.loc[want, "currency"]


def test_side_lines_short_only_on_shortable_line(panel, avail):
    iid, local, adr = _br_issuer_with_adr(panel)
    lines = panel.lines.copy()
    lines.loc[local, "adtv_usd"] = 100e6
    lines.loc[adr, "adtv_usd"] = 20e6
    av = avail.copy()
    av.loc[local, "shortable"] = False
    av.loc[adr, "shortable"] = True
    side = issuer_side_lines(replace(panel, lines=lines), av)
    assert side.loc[iid, "long_ticker"] == local
    assert side.loc[iid, "short_ticker"] == adr
    assert side.loc[iid, "adtv_short_usd"] == pytest.approx(20e6)
    # linha ausente da tabela de disponibilidade ⇒ não alugável
    side2 = issuer_side_lines(panel, avail.drop(index=[local, adr]))
    assert not side2.loc[iid, "can_short"]


# ----------------------------------------------------------------------------------------
# Short squeeze: mapeamentos
# ----------------------------------------------------------------------------------------

def test_threshold_score_piecewise():
    x = pd.Series([-0.1, 0.0, 0.025, 0.05, 0.10, 0.15, 0.225, 0.30, 0.5, np.nan, np.inf])
    s = threshold_score(x, 0.05, 0.15)
    expected = [0, 0, 20, 40, 55, 70, 85, 100, 100, np.nan, 100]
    np.testing.assert_allclose(s.to_numpy(), expected, equal_nan=True)
    with pytest.raises(ValueError):
        threshold_score(x, 0.15, 0.05)


def test_float_score_log_interpolation():
    low = 1e9
    x = pd.Series([0.1e9, 0.25e9, 0.5e9, 1e9, math.sqrt(10) * 1e9, 10e9, 50e9, np.nan, 0.0, -1.0])
    s = float_score(x, low)
    expected = [100, 100, 70, 40, 20, 0, 0, np.nan, np.nan, np.nan]
    np.testing.assert_allclose(s.to_numpy(), expected, equal_nan=True, atol=1e-9)


def test_catalyst_score():
    d = pd.Series([0, 7, 8, 14, 15, 90, np.nan])
    np.testing.assert_allclose(catalyst_score(d).to_numpy(), [100, 100, 50, 50, 0, 0, np.nan],
                               equal_nan=True)


def test_composite_renormalization_and_red_flag():
    comp = pd.DataFrame({
        "score_si": [50.0, np.nan, 75.0, np.nan, np.nan],
        "score_dtc": [50.0, 20.0, 0.0, np.nan, np.nan],
        "score_fee": [50.0, np.nan, 0.0, np.nan, np.nan],
        "score_mom": [50.0, 40.0, 0.0, 70.0, np.nan],
        "score_float": [50.0, np.nan, 0.0, 0.0, np.nan],
        "score_catalyst": [50.0, np.nan, 0.0, 0.0, np.nan],
    })
    score = composite_squeeze_score(comp, 70.0)
    assert score[0] == pytest.approx(50.0)
    assert score[1] == pytest.approx((0.25 * 20 + 0.15 * 40) / 0.40)  # renormalizado
    assert score[2] == pytest.approx(70.0)  # regra do máximo: um sinal vermelho basta
    assert score[3] == pytest.approx(70.0)
    assert math.isnan(score[4])


def test_bucket_rules():
    score = pd.Series([10.0, 45.0, 75.0, 10.0, 75.0, np.nan])
    si_na = pd.Series([False, False, False, True, True, False])
    dtc_na = pd.Series([False, False, False, True, True, True])
    b = squeeze_bucket(score, si_na, dtc_na, 40.0, 70.0)
    assert b.tolist() == ["LOW", "MEDIUM", "HIGH", "NA", "HIGH", "NA"]
    assert effective_bucket(b).tolist() == ["LOW", "MEDIUM", "HIGH", "MEDIUM", "HIGH", "MEDIUM"]


# ----------------------------------------------------------------------------------------
# Short squeeze: tabela no mercado simulado
# ----------------------------------------------------------------------------------------

def test_squeeze_table_schema_and_ranges(sq, panel):
    assert list(sq.columns) == SQUEEZE_COLUMNS
    assert list(sq.index) == list(panel.assets.index)
    s = sq["squeeze_score"].dropna()
    assert ((s >= 0) & (s <= 100)).all()
    assert set(sq["bucket"]) <= {"LOW", "MEDIUM", "HIGH", "NA"}
    for c in [c for c in sq.columns if c.startswith("score_")]:
        v = sq[c].dropna()
        assert ((v >= 0) & (v <= 100)).all(), c
    assert sq["point_in_time"].all()  # painel na data do snapshot
    assert sq["data_quality"].str.contains("si=").all()


def test_hot_adr_is_high(sq, panel, hot_ticker):
    iid = panel.lines.loc[hot_ticker, "issuer_id"]
    row = sq.loc[iid]
    assert row["si_pct_float"] == pytest.approx(0.30)
    assert row["days_to_cover"] == pytest.approx(9.0)
    assert row["score_si"] == pytest.approx(100.0)
    assert row["score_dtc"] == pytest.approx(70 + 30 * (9 - 7) / 7)
    assert row["borrow_fee"] == pytest.approx(US_SPECIAL_FEE_ESTIMATE)
    assert row["bucket"] == "HIGH"
    assert row["squeeze_score"] >= 70.0
    assert "GC_ESTIMATE_US(estimada)" in row["data_quality"]


def test_missing_si_is_nan_not_zero(sq, panel):
    no_data = [i for i, g in panel.lines.groupby("issuer_id") if set(g["market"]) == {"MX"}]
    sub = sq.loc[no_data]
    assert sub["si_pct_float"].isna().all()
    assert sub["days_to_cover"].isna().all()
    assert sub["borrow_fee"].isna().all()
    assert sub["score_si"].isna().all() and sub["score_dtc"].isna().all()
    assert sub["bucket"].isin(["NA", "HIGH"]).all()
    na = sub[sub["bucket"] == "NA"]
    assert not na.empty
    assert na["data_quality"].str.contains("faixa_NA_tratar_como_MEDIUM").all()
    assert (na["components_available"] == 3).all()


def test_br_days_to_cover_and_si_proxy(sq, panel, md, cfg):
    iid = next(i for i, g in panel.lines.groupby("issuer_id")
               if list(g["market"]) == ["BR"] and list(g["line_type"]) == ["LOCAL"])
    tkr = panel.lines.index[panel.lines["issuer_id"] == iid][0]
    avg_vol = md.volume[tkr].tail(cfg.liquidity.adv_window_days).mean()
    lent = float(md.lending.loc[tkr, "lent_shares"])
    assert sq.loc[iid, "days_to_cover"] == pytest.approx(lent / avg_vol)
    assert sq.loc[iid, "si_pct_float"] == pytest.approx(md.lending.loc[tkr, "lending_pct_shares"])
    assert sq.loc[iid, "lending_pct_shares"] == pytest.approx(
        md.lending.loc[tkr, "lending_pct_shares"])
    assert sq.loc[iid, "borrow_fee"] == pytest.approx(md.lending.loc[tkr, "lending_rate_annual"])


def test_si_proxy_takes_max_over_lines(sq, panel, md):
    iid, local, adr = _br_issuer_with_adr(panel)
    expected = max(md.short_interest.loc[adr, "short_pct_float"],
                   md.lending.loc[local, "lending_pct_shares"])
    assert sq.loc[iid, "si_pct_float"] == pytest.approx(expected)
    assert "SI_US+BTC_B3" in sq.loc[iid, "data_quality"]


def test_momentum_and_vol_from_usd_returns(sq, panel):
    r = panel.returns
    iid = panel.eligible[0]
    last21 = r[iid].tail(21)
    assert sq.loc[iid, "ret_1m"] == pytest.approx(float((1 + last21).prod() - 1))
    assert sq.loc[iid, "ret_3m"] == pytest.approx(float((1 + r[iid].tail(63)).prod() - 1))
    assert sq.loc[iid, "vol_1m"] == pytest.approx(float(last21.std(ddof=1) * math.sqrt(252)))
    # papel sem negociação nos últimos 10 pregões: janela de 1m insuficiente ⇒ NaN
    stale = panel.assets.index[panel.assets["exclusion_reason"].str.contains("preco_defasado")]
    assert len(stale) == 1
    assert math.isnan(sq.loc[stale[0], "ret_1m"]) and math.isnan(sq.loc[stale[0], "vol_1m"])


def test_days_to_earnings_and_catalyst(panel, md, avail, cfg):
    iid = panel.eligible[0]
    tickers = list(panel.lines.index[panel.lines["issuer_id"] == iid])
    fund = md.fundamentals.copy()
    as_of = pd.Timestamp(panel.as_of)
    fund.loc[tickers, "next_earnings_date"] = (as_of + pd.Timedelta(days=5)).date().isoformat()
    other = panel.eligible[1]
    other_t = list(panel.lines.index[panel.lines["issuer_id"] == other])
    fund.loc[other_t, "next_earnings_date"] = (as_of - pd.Timedelta(days=3)).date().isoformat()
    t = squeeze_table(panel, replace(md, fundamentals=fund), avail, cfg)
    assert t.loc[iid, "days_to_earnings"] == 5
    assert t.loc[iid, "score_catalyst"] == 100
    assert math.isnan(t.loc[other, "days_to_earnings"])
    assert math.isnan(t.loc[other, "score_catalyst"])
    assert "data_resultado_defasada" in t.loc[other, "data_quality"]


def test_no_short_data_at_all(panel, md, cfg):
    empty = pd.DataFrame()
    md2 = replace(md, short_interest=empty, lending=empty)
    av = short_availability(panel, md2, cfg)
    t = squeeze_table(panel, md2, av, cfg)
    assert t["si_pct_float"].isna().all()
    assert t["days_to_cover"].isna().all()
    assert t["bucket"].isin(["NA", "HIGH"]).all()
    # ADRs continuam com taxa GC estimada; BR sem dado só com GC se líquido e grande
    assert set(av["fee_source"]) <= {FEE_SOURCE_GC_US, FEE_SOURCE_GC_BR, FEE_SOURCE_NA}


def test_no_look_ahead(md, cfg):
    as_of = date(2026, 6, 30)
    p_past = build_asset_panel(md, cfg, as_of=as_of)
    av = short_availability(p_past, md, cfg)
    base = squeeze_table(p_past, md, av, cfg)
    # perturba dados posteriores a as_of: resultado não pode mudar
    vol = md.volume.copy()
    vol.loc[vol.index > pd.Timestamp(as_of)] *= 50.0
    shocked = squeeze_table(p_past, replace(md, volume=vol), av, cfg)
    pd.testing.assert_frame_equal(base, shocked)
    iid = p_past.eligible[0]
    r = p_past.returns.loc[:pd.Timestamp(as_of), iid].tail(21)
    assert base.loc[iid, "ret_1m"] == pytest.approx(float((1 + r).prod() - 1))
    # retratos atuais usados num painel passado são sinalizados como não point-in-time
    assert not base["point_in_time"].any()
    assert base["data_quality"].str.contains("nao_pit").all()


def test_deterministic_and_cap_multiplier(panel, md, avail, sq, cfg):
    again = squeeze_table(panel, md, short_availability(panel, md, cfg), cfg)
    pd.testing.assert_frame_equal(sq, again)
    mult = short_cap_multiplier(sq, cfg)
    assert (mult[sq["bucket"] == "HIGH"] == 0.0).all()
    assert (mult[sq["bucket"].isin(["MEDIUM", "NA"])]
            == cfg.squeeze.medium_short_cap_multiplier).all()
    assert (mult[sq["bucket"] == "LOW"] == 1.0).all()


def test_dtc_infinite_when_no_volume(panel, md, avail, cfg):
    iid = next(i for i, g in panel.lines.groupby("issuer_id")
               if list(g["market"]) == ["BR"] and list(g["line_type"]) == ["LOCAL"])
    tkr = panel.lines.index[panel.lines["issuer_id"] == iid][0]
    vol = md.volume.copy()
    vol[tkr] = 0.0
    t = squeeze_table(panel, replace(md, volume=vol), avail, cfg)
    assert math.isinf(t.loc[iid, "days_to_cover"])
    assert t.loc[iid, "score_dtc"] == 100.0
    assert t.loc[iid, "bucket"] == "HIGH"
    assert "dtc_infinito_sem_volume" in t.loc[iid, "data_quality"]
