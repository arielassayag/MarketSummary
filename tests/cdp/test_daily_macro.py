"""Macro diário, atribuição observada e diagnóstico autenticado (DADOS SIMULADOS)."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from test_daily_track_record import FakeStore, make_proposal, week1

from cdp.analytics.panel import build_asset_panel
from cdp.config import FundConfig
from cdp.contracts import DecisionType
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file
from cdp.risk.macro import augment_with_macro
from cdp.risk.model import estimate_risk_model
from cdp.risk.types import RiskModel
from cdp.workflow import risco_diario as rd
from cdp.workflow.approval import make_decision
from cdp.workflow.daily import DailyRunner, PendingExecution, factor_returns_source
from cdp.workflow.runtime import Runtime
from cdp.workflow.track_record import TrackRecord
from cdp.workflow.weekly import prepare_week

FIRST = date(2023, 12, 4)
NEXT = date(2023, 12, 5)


@pytest.fixture(scope="module")
def market():
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=date(2023, 12, 22))
    rng = np.random.default_rng(30)
    oil = rng.normal(0, 0.025, len(md.close))
    betas = dict(
        zip(
            md.universe.issuers.index, rng.uniform(-0.8, 0.8, len(md.universe.issuers)), strict=True
        )
    )
    close, adj = md.close.copy(), md.adj_close.copy()
    for ticker, line in md.universe.lines.iterrows():
        multiplier = np.cumprod(1 + betas[line["issuer_id"]] * oil)
        close[ticker] *= multiplier
        adj[ticker] *= multiplier
    return replace(
        md,
        close=close,
        adj_close=adj,
        benchmarks=md.benchmarks.assign(**{"BZ=F": 80 * np.cumprod(1 + oil)}),
    )


@pytest.fixture(scope="module")
def cfg():
    return FundConfig().with_overrides(
        {
            "fund": {"inception_date": str(FIRST), "inception_nav_usd": 100_000_000.0},
            "risk_model": {"macro_factors": ["BZ=F"]},
            "risk": {
                "event_windows": [
                    {
                        "name": "Evento BR simulado",
                        "country": "BR",
                        "start": "2023-12-01",
                        "end": "2023-12-31",
                        "vol_multiplier": 1.5,
                    }
                ]
            },
        }
    )


def inception(root, market, cfg, *, with_shadow=False):
    runner = DailyRunner.from_root(cfg, FakeStore(market), root, with_shadow=with_shadow)
    prop = make_proposal(FIRST, week1(market), cfg=cfg)
    decision = make_decision(
        prop,
        "Ana",
        DecisionType.APPROVE,
        "Teste causal simulado",
        prop.research_hash,
        co_signer="Bruno",
        now=datetime(2023, 12, 4, 18, tzinfo=UTC),
    )
    result = runner.run_session(
        FIRST, PendingExecution(prop, decision, shadow=prop if with_shadow else None)
    )
    return runner, prop, result


@pytest.fixture(scope="module")
def closed(tmp_path_factory, market, cfg):
    runner, prop, first = inception(tmp_path_factory.mktemp("macro-daily") / "book", market, cfg)
    nxt = runner.run(NEXT)
    return SimpleNamespace(runner=runner, proposal=prop, first=first.record, next=nxt)


def copied(tmp_path, closed, market, cfg):
    root = tmp_path / "book"
    shutil.copytree(closed.runner.book.root, root)
    return DailyRunner.from_root(cfg, FakeStore(market), root, with_shadow=False)


def test_daily_weekly_same_cutoff_bfd_and_event_once(closed, market, cfg):
    d = NEXT
    md = replace(market.truncate(d), manifest=market.manifest.model_copy(update={"as_of": d}))
    panel = build_asset_panel(md, cfg, as_of=d)
    structural = estimate_risk_model(panel, cfg, md, as_of=d, issuers=panel.eligible)
    expected = augment_with_macro(structural, md, cfg, panel)
    base = closed.runner._model_at(d)
    weekly = prepare_week(md, cfg, date(2023, 12, 8))
    for other in (expected, weekly.model_base):
        pd.testing.assert_frame_equal(base.exposures, other.exposures)
        pd.testing.assert_frame_equal(base.factor_cov, other.factor_cov)
        pd.testing.assert_series_equal(base.specific_var, other.specific_var)
    assert base.factor_names.count("macro:BZ=F") == 1
    assert "event_windows" not in base.meta
    assert base.specific_var.mean() < structural.specific_var.mean()
    assert (base.specific_var >= 0.5 * structural.specific_var - 1e-12).all()
    diagnostic = rd.load(closed.runner.track, closed.next)
    event = rd.restore(diagnostic["models"]["evento"])
    br = panel.assets["country"].reindex(base.assets) == "BR"
    np.testing.assert_allclose(event.specific_var[br], base.specific_var[br] * 1.5**2)
    pd.testing.assert_frame_equal(event.exposures, base.exposures)
    scales = np.array([1.5 if f == "country:BR" else 1.0 for f in base.factor_names])
    np.testing.assert_allclose(event.factor_cov, base.factor_cov * np.outer(scales, scales))
    assert base.factor_returns.index.max().date() <= d


def test_effective_weights_and_independent_risk_identities(closed):
    rec = closed.next
    diagnostic = rd.load(closed.runner.track, rec)
    weights = pd.Series(
        {
            p.issuer_id: p.market_value_usd / rec.nav_end_usd
            for p in rec.positions
            if p.market_value_usd
        }
    )
    assert diagnostic["weights"] == weights.to_dict()
    target = {p.issuer_id: p.weight for p in closed.proposal.positions}
    assert any(abs(weights[i] - target[i]) > 1e-8 for i in weights.index)
    for name in ("base", "evento"):
        model = rd.restore(diagnostic["models"][name])
        w = weights.reindex(model.assets, fill_value=0.0)
        x = model.exposures.T @ w
        fv = float(x @ model.factor_cov @ x)
        sv = float((w**2 * model.specific_var).sum())
        observed = diagnostic["measures"][name]
        assert observed["factor_vol"] ** 2 == pytest.approx(fv)
        assert observed["specific_vol"] ** 2 == pytest.approx(sv)
        assert observed["vol"] ** 2 == pytest.approx(fv + sv)
        assert observed["idio_kf"] == pytest.approx(sv / (diagnostic["kappa_f"] * fv + sv))
    assert diagnostic["idio_binding"] == min(v["idio_kf"] for v in diagnostic["measures"].values())
    assert rd.verify(closed.runner.track, market_loader=closed.runner.store.load) == []


def toy():
    ids = [f"i{k}" for k in range(40)]
    size = np.linspace(-1, 1, 40)
    B = pd.DataFrame({"market": 1.0, "size": size, "macro:BZ=F": 0.4 + 2 * size}, index=ids)
    return RiskModel(
        FIRST,
        B,
        pd.DataFrame(np.eye(3), index=B.columns, columns=B.columns),
        pd.Series(0.04, index=ids),
        pd.DataFrame(columns=B.columns),
        pd.DataFrame(),
    )


def test_macro_observed_before_structural_wls_not_joint_regression():
    model = toy()
    ts = pd.Timestamp(NEXT)
    observed = pd.DataFrame({"macro:BZ=F": [0.025]}, index=[ts])
    y = (
        model.exposures["market"] * 0.011
        + model.exposures["size"] * -0.006
        + model.exposures["macro:BZ=F"] * 0.025
    )
    get, state = factor_returns_source(None, model, ts, y, observed_macro=observed)
    result = get(ts)
    assert state["fallback"]
    assert result["macro:BZ=F"] == 0.025
    np.testing.assert_allclose(result[["market", "size"]], [0.011, -0.006], atol=1e-12)
    np.testing.assert_allclose(model.exposures @ result, y, atol=1e-12)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_missing_or_nonfinite_macro_is_unavailable(value):
    model = toy()
    ts = pd.Timestamp(NEXT)
    get, state = factor_returns_source(
        None,
        model,
        ts,
        pd.Series(0.02, index=model.assets),
        observed_macro=pd.DataFrame({"macro:BZ=F": [value]}, index=[ts]),
    )
    assert get(ts) is None and state["missing_macro"]


def test_required_macro_missing_from_b_is_not_ignored():
    model = toy()
    ts = pd.Timestamp(NEXT)
    get, state = factor_returns_source(
        None,
        model,
        ts,
        pd.Series(0.02, index=model.assets),
        required_macro=["macro:XX=F"],
        observed_macro=pd.DataFrame({"macro:BZ=F": [0.025]}, index=[ts]),
    )
    assert get(ts) is None and state["missing_macro"][str(NEXT)] == ["macro:XX=F"]


def test_previous_model_frozen_across_restart_future_prices_fundamentals_and_config(
    tmp_path, closed, market, cfg
):
    prices = market.close.copy()
    prices.loc[prices.index > pd.Timestamp(NEXT)] *= 1.9
    fundamentals = market.fundamentals.copy()
    if "market_cap" in fundamentals:
        fundamentals["market_cap"] *= 2.0
    future = replace(market, close=prices, fundamentals=fundamentals)
    changed = cfg.with_overrides(
        {"risk": {"second_order_inflation": 2.0}, "risk_model": {"macro_factors": []}}
    )
    reader = copied(tmp_path, closed, future, changed)
    frozen = reader._model_at(NEXT)
    original = closed.runner._model_at(NEXT)
    pd.testing.assert_frame_equal(frozen.exposures, original.exposures)
    pd.testing.assert_frame_equal(frozen.factor_cov, original.factor_cov)
    pd.testing.assert_series_equal(frozen.specific_var, original.specific_var, check_names=False)


@pytest.mark.parametrize("tamper", ["remove", "value", "metadata", "binding"])
def test_diagnostic_tamper_or_removal_fails_verify(tmp_path, closed, market, cfg, tamper):
    runner = copied(tmp_path, closed, market, cfg)
    p = rd.path(runner.track, NEXT)
    if tamper == "remove":
        p.unlink()
    elif tamper == "binding":
        audit = runner.track.audit.path
        audit.write_text("\n".join(audit.read_text().splitlines()[:-1]) + "\n")
    else:
        obj = json.loads(p.read_text())
        if tamper == "value":
            obj["weights"][next(iter(obj["weights"]))] += 0.01
        else:
            obj["sources"]["current"]["manifest"]["sources"].append({"point_in_time": True})
        p.write_text(json.dumps(obj))
    assert rd.verify(runner.track, market_loader=runner.store.load)
    rt = Runtime(
        cfg,
        runner.book.root,
        tmp_path / "market",
        tmp_path / "reports",
        store_override=runner.store,
    )
    assert not rt.verify_all()[0]


def test_recovery_after_record_before_binding_is_idempotent(tmp_path, market, cfg, monkeypatch):
    real = rd.recover
    with monkeypatch.context() as mp:
        mp.setattr(
            rd,
            "recover",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("queda após registro")),
        )
        with pytest.raises(RuntimeError, match="queda"):
            inception(tmp_path / "book", market, cfg)
    track = TrackRecord(tmp_path / "book/track_record")
    rec = track.get(FIRST)
    before = {str(p): sha256_file(p) for p in track.root.rglob("*") if p.is_file()}
    real(track, rec)
    real(track, rec)
    assert before == {str(p): sha256_file(p) for p in track.root.rglob("*") if p.is_file()}
    assert rd.verify(track) == []
    assert len([e for e in track.audit.events() if e.event_type == rd.EVENT]) == 1


def test_costs_use_total_price_vol_exactly_independent_of_macro(tmp_path, market, cfg):
    _, _, macro = inception(tmp_path / "with-macro", market, cfg)
    _, _, legacy = inception(
        tmp_path / "without-macro",
        market,
        cfg.with_overrides({"risk_model": {"macro_factors": []}}),
    )
    assert macro.record.pnl_components["costs"] == legacy.record.pnl_components["costs"]
    assert macro.record.nav_end_usd == legacy.record.nav_end_usd


def test_readers_use_archived_kappa_binding_or_null_not_current_cfg(closed, market, cfg):
    from cdp.risk.idio import serie_idio
    from cdp.workflow.relatorio_semanal import _risco

    diagnostics = rd.read_measures(closed.runner.track)
    changed = cfg.with_overrides({"risk": {"second_order_inflation": 5.0}})
    series = serie_idio([closed.next], market, changed, diagnostics=diagnostics)
    assert series["ex_ante"][0] == pytest.approx(diagnostics[NEXT]["idio_binding"], rel=1e-5)
    assert serie_idio([closed.next], market, changed)["ex_ante"] == [None]
    report = _risco(changed, None, closed.next, 5.0, diagnostic=diagnostics[NEXT])
    assert report["efetiva"]["kappa_f"] == diagnostics[NEXT]["kappa_f"]
    assert report["efetiva"]["idio_kf"] == diagnostics[NEXT]["idio_binding"]
    assert _risco(changed, None, closed.next, 5.0)["efetiva"]["idio_kf"] is None


def test_moc_partial_execution_uses_effective_quantities_not_ideal_targets(tmp_path, market, cfg):
    from test_calendar import ativado

    fri = date(2023, 12, 8)
    cfg = ativado(cfg, inception_date=str(fri))
    targets = []
    volumes = market.volume.copy()
    for p in week1(market):
        px = float(market.close.at[pd.Timestamp("2023-12-07"), p.execution_ticker])
        fx = float(market.fx.at[pd.Timestamp("2023-12-07"), p.currency])
        shares = int(p.notional_usd / (px * fx))
        targets.append(p.model_copy(update={"shares": shares, "price_local": px}))
        volumes.loc[pd.Timestamp(fri), p.execution_ticker] = abs(shares) * 3
    md = replace(market, volume=volumes)
    runner = DailyRunner.from_root(cfg, FakeStore(md), tmp_path / "book", with_shadow=False)
    proposal = make_proposal(fri, targets, cfg=cfg)
    decision = make_decision(
        proposal,
        "Ana",
        DecisionType.APPROVE,
        "MOC parcial simulado",
        proposal.research_hash,
        co_signer="Bruno",
        now=datetime(2023, 12, 8, 14, tzinfo=UTC),
    )
    result = runner.run_session(fri, PendingExecution(proposal, decision))
    assert result.booked.positions
    quantities = {p.ticker: p.shares for p in result.booked.positions}
    assert any(0 < abs(quantities.get(p.execution_ticker, 0)) < abs(p.shares) for p in targets)
    diag = rd.load(runner.track, result.record)
    assert diag["weights"] == {
        p.issuer_id: p.market_value_usd / result.record.nav_end_usd
        for p in result.record.positions
        if p.market_value_usd
    }
    assert diag["weights"] != {p.issuer_id: p.weight for p in targets}
    assert rd.verify(runner.track, market_loader=runner.store.load) == []


def test_orphan_before_record_recovery_preserves_bytes(tmp_path, market, cfg, monkeypatch):
    real = TrackRecord.append
    with monkeypatch.context() as mp:
        mp.setattr(
            TrackRecord,
            "append",
            lambda *_a: (_ for _ in ()).throw(RuntimeError("queda antes registro")),
        )
        with pytest.raises(RuntimeError, match="queda"):
            inception(tmp_path / "book", market, cfg)
    runner = DailyRunner.from_root(cfg, FakeStore(market), tmp_path / "book", with_shadow=False)
    p = rd.path(runner.track, FIRST)
    before = p.read_bytes()
    assert rd.verify(runner.track)  # órfão explícito, não falso íntegro
    result = runner.run_session(FIRST)
    assert p.read_bytes() == before
    assert real is not None and result.record.input_hashes[rd.MARKER] == sha256_file(p)
    assert rd.verify(runner.track) == []


def test_missing_configured_block_keeps_nav_but_no_compliance_claim(tmp_path, market, cfg):
    missing = cfg.with_overrides({"risk_model": {"macro_factors": ["BZ=F", "XX=F"]}})
    runner, _, first = inception(tmp_path / "book", market, missing)
    rec = runner.run(NEXT)
    diagnostic = rd.load(runner.track, rec)
    assert diagnostic["measures"]["base"]["missing_macro"] == ["macro:XX=F"]
    assert diagnostic["binding"] is None and diagnostic["idio_binding"] is None
    assert rec.risk.ex_ante_vol is None and rec.risk.factor_vol is None
    assert rec.risk.specific_vol is None
    assert "factor" not in rec.pnl_components and "specific" not in rec.pnl_components
    assert rec.nav_end_usd == pytest.approx(first.record.nav_end_usd + rec.pnl_usd)
    assert rd.verify(runner.track, market_loader=runner.store.load) == []


def test_reopened_line_missing_macro_inside_window_is_not_zero(tmp_path, market, cfg):
    ts = pd.Timestamp(NEXT)
    adj, close = market.adj_close.copy(), market.close.copy()
    adj.loc[ts, "SBR01.SA"] = np.nan
    close.loc[ts, "SBR01.SA"] = np.nan
    bench = market.benchmarks.copy()
    bench.loc[ts, "BZ=F"] = np.nan
    runner, _, _ = inception(
        tmp_path / "book", replace(market, close=close, adj_close=adj, benchmarks=bench), cfg
    )
    runner.run(NEXT)
    rec = runner.run(date(2023, 12, 6))
    assert "factor" not in rec.pnl_components and "specific" not in rec.pnl_components
    assert any("Atribuição macro indisponível" in a for a in rec.alerts)
    assert rec.nav_end_usd == pytest.approx(rec.nav_start_usd + rec.pnl_usd)


@pytest.mark.parametrize("stage", ["json", "csv"])
def test_prepared_seal_recovers_partial_append_without_rewriting(
    tmp_path, market, cfg, monkeypatch, stage
):
    from cdp.audit import AuditLog
    from cdp.workflow import track_record as tr

    root = tmp_path / "book"
    with monkeypatch.context() as mp:
        if stage == "json":
            original = tr.write_exclusive

            def fail_after_json(p, raw):
                original(p, raw)
                if p.parent.name == "records":
                    raise RuntimeError("queda após JSON")

            mp.setattr(tr, "write_exclusive", fail_after_json)
        else:
            original = AuditLog.append

            def fail_after_csv(self, kind, *args, **kwargs):
                if kind == "DAILY_RECORD":
                    raise RuntimeError("queda após CSV")
                return original(self, kind, *args, **kwargs)

            mp.setattr(AuditLog, "append", fail_after_csv)
        with pytest.raises(RuntimeError, match="queda"):
            inception(root, market, cfg)
    track = TrackRecord(root / "track_record")
    rec = track.get(FIRST)
    record_bytes = track.record_path(FIRST).read_bytes()
    risk_bytes = rd.path(track, FIRST).read_bytes()
    csv_prefix = track.csv_path.read_bytes() if track.csv_path.exists() else b""
    assert not track.verify()[0] and rd.verify(track)
    rt = Runtime(
        cfg, root, tmp_path / "market", tmp_path / "reports", store_override=FakeStore(market)
    )
    assert rt.daily_close(FIRST, live=False)["status"] == "já registrado"
    assert track.verify()[0] and rd.verify(track, market_loader=rt.store.load) == []
    assert track.record_path(FIRST).read_bytes() == record_bytes
    assert rd.path(track, FIRST).read_bytes() == risk_bytes
    assert track.csv_path.read_bytes().startswith(csv_prefix)
    before = {str(p): sha256_file(p) for p in root.rglob("*") if p.is_file()}
    assert rt.daily_close(FIRST, live=False)["status"] == "já registrado"
    assert before == {str(p): sha256_file(p) for p in root.rglob("*") if p.is_file()}
    assert len([e for e in track.audit.events() if e.event_type == rd.PREPARED_EVENT]) == 1
    assert len([e for e in track.audit.events() if e.event_type == rd.EVENT]) == 1
    assert rec.input_hashes[rd.MARKER] == sha256_file(rd.path(track, FIRST))


def test_recovery_refuses_missing_prepared_seal_without_mutation(
    tmp_path, market, cfg, monkeypatch
):
    from cdp.audit import AuditLog

    original = AuditLog.append

    def omit_prepared(self, kind, *args, **kwargs):
        if kind == rd.PREPARED_EVENT:
            return None
        return original(self, kind, *args, **kwargs)

    root = tmp_path / "book"
    with monkeypatch.context() as mp:
        mp.setattr(AuditLog, "append", omit_prepared)
        with pytest.raises(ValueError, match="selo preparatório"):
            inception(root, market, cfg)
    track = TrackRecord(root / "track_record")
    before = {str(p): sha256_file(p) for p in root.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="selo preparatório"):
        rd.recover(track, track.get(FIRST))
    assert before == {str(p): sha256_file(p) for p in root.rglob("*") if p.is_file()}


def test_active_kappa_is_archived_for_both_effective_risk_models(tmp_path, market, cfg):
    from cdp.risk.idio import serie_idio

    active = cfg.with_overrides(
        {"risk": {"factor_risk_basis": "achieved", "second_order_inflation": 1.45}}
    )
    runner, _, _ = inception(tmp_path / "book", market, active)
    rec = runner.run(NEXT)
    diag = rd.load(runner.track, rec)
    assert diag["kappa_f"] == 1.45
    assert diag["kappa_info"] == {"valor": 1.45, "fonte": "config"}
    for ms in diag["measures"].values():
        fv, sv = ms["factor_vol"] ** 2, ms["specific_vol"] ** 2
        assert ms["idio_kf"] == pytest.approx(sv / (1.45 * fv + sv), abs=1e-14)
        assert ms["vol_kf"] == pytest.approx(np.sqrt(1.45 * fv + sv), abs=1e-14)
    assert diag["idio_binding"] == min(m["idio_kf"] for m in diag["measures"].values())
    future = active.with_overrides({"risk": {"second_order_inflation": 5.0}})
    got = serie_idio([rec], market, future, diagnostics=rd.read_measures(runner.track))
    assert got["ex_ante"][0] == pytest.approx(diag["idio_binding"], rel=1e-5)
    assert rd.verify(runner.track, market_loader=runner.store.load) == []


def test_held_nonfinite_exposure_is_missing_not_zero():
    model = toy()
    model.exposures.loc[model.assets[0], "macro:BZ=F"] = np.nan
    result = rd.measures(model, pd.Series({model.assets[0]: 0.1}), ["macro:BZ=F"], 1.45)
    assert not result["complete"] and result["idio_kf"] is None
    assert result["reasons"] == ["B/F/D inválidos para a posição"]


def test_complete_structural_candidate_on_gross_does_not_absorb_observed_macro():
    model = toy()
    ts = pd.Timestamp(NEXT)
    earlier = pd.Timestamp(FIRST)
    observed = pd.DataFrame({"macro:BZ=F": [0.025, -0.017]}, index=[earlier, ts])
    planted = pd.Series({"market": 0.011, "size": -0.006})
    equity = pd.DataFrame(
        [
            model.exposures[["market", "size"]] @ planted + model.exposures["macro:BZ=F"] * m
            for m in observed["macro:BZ=F"]
        ],
        index=observed.index,
    )
    # Candidato completo, mas calculado sobre o bruto: exatamente o caminho antes errado.
    complete = replace(
        model,
        factor_returns=pd.DataFrame(
            {"market": [0.035, 0.035], "size": [0.031, 0.031], "macro:BZ=F": [0.025, -0.017]},
            index=observed.index,
        ),
    )
    get, _ = factor_returns_source(
        complete, model, ts, equity.loc[ts], observed_macro=observed, observed_equity=equity
    )
    for s in (earlier, ts):
        result = get(s)
        np.testing.assert_allclose(result[["market", "size"]], planted, atol=1e-12)
        assert result["macro:BZ=F"] == observed.loc[s, "macro:BZ=F"]
        np.testing.assert_allclose(model.exposures @ result, equity.loc[s], atol=1e-12)


def test_actual_daily_attribution_uses_previous_exposure_and_observed_macro(closed, market, cfg):
    from cdp.workflow.daily import cross_sectional_factor_returns

    previous = rd.restore(rd.load(closed.runner.track, closed.first)["models"]["base"])
    panel = build_asset_panel(market.truncate(NEXT), cfg, as_of=NEXT)
    y = panel.returns.loc[pd.Timestamp(NEXT)]
    macro = [n for n in previous.factor_names if n.startswith("macro:")]
    structural = [n for n in previous.factor_names if n not in macro]
    observed = market.benchmarks["BZ=F"].pct_change(fill_method=None).loc[str(NEXT)]
    residual = y - previous.exposures[macro].iloc[:, 0] * observed
    estimated = cross_sectional_factor_returns(
        previous.exposures[structural], residual, previous.specific_var
    )
    dollar_weights = pd.Series({p.issuer_id: p.market_value_usd for p in closed.first.positions})
    x = previous.exposures.T @ dollar_weights.reindex(previous.assets, fill_value=0.0)
    expected = float(x[structural] @ estimated + x[macro].iloc[0] * observed)
    assert closed.next.pnl_components["factor"] == pytest.approx(expected, abs=1e-7)
    macro_line = next(
        a for a in closed.next.attribution if a.group == "factor" and a.name == "macro:BZ=F"
    )
    assert macro_line.pnl_usd == pytest.approx(x[macro].iloc[0] * observed, abs=1e-7)
    assert closed.next.pnl_components["factor"] + closed.next.pnl_components[
        "specific"
    ] == pytest.approx(closed.next.pnl_components["equity"], abs=1e-7)


def test_interrupted_shadow_append_recovers_before_adopting_main_booking(
    tmp_path, market, cfg, monkeypatch
):
    from cdp.audit import AuditLog

    original = AuditLog.append
    root = tmp_path / "book"

    def stop_shadow(self, kind, *args, **kwargs):
        if kind == "DAILY_RECORD_SHADOW":
            raise RuntimeError("queda na sombra")
        return original(self, kind, *args, **kwargs)

    with monkeypatch.context() as mp:
        mp.setattr(AuditLog, "append", stop_shadow)
        with pytest.raises(RuntimeError, match="queda"):
            inception(root, market, cfg, with_shadow=True)
    runner = DailyRunner.from_root(cfg, FakeStore(market), root, with_shadow=True)
    booked_before = (runner.book.week_dir(FIRST) / "booked.json").read_bytes()
    shadow_before = runner.shadow.track.record_path(FIRST).read_bytes()
    assert not runner.shadow.track.verify()[0]
    result = runner.run_session(FIRST)
    assert runner.shadow.track.verify()[0] and runner.track.verify()[0]
    assert rd.verify(runner.track, market_loader=runner.store.load) == []
    assert rd.verify(runner.shadow.track, market_loader=runner.store.load) == []
    assert (runner.book.week_dir(FIRST) / "booked.json").read_bytes() == booked_before
    assert runner.shadow.track.record_path(FIRST).read_bytes() == shadow_before
    assert result.record.input_hashes["shadow_record"] == runner.shadow.track.get(FIRST).record_hash
    assert (
        len(
            [e for e in runner.book.audit.events() if e.event_type == rd.PREPARED_EVENT + "_SHADOW"]
        )
        == 1
    )


def test_previous_model_and_source_are_paired_to_the_original_session(tmp_path, market, cfg):
    runner, _, first = inception(tmp_path / "book", market, cfg)
    original = rd.load(runner.track, first.record)
    fundamentals = market.fundamentals.copy()
    fundamentals["market_cap"] *= 2.0
    revised = replace(market, fundamentals=fundamentals)
    runner = DailyRunner.from_root(cfg, FakeStore(revised), runner.book.root, with_shadow=False)
    rec = runner.run(NEXT)
    diagnostic = rd.load(runner.track, rec)
    assert diagnostic["models"]["previous"] == original["models"]["base"]
    assert diagnostic["sources"]["previous"] == original["sources"]["current"]
    assert (
        diagnostic["sources"]["current"]["tables_sha256"]["fundamentals"]
        != diagnostic["sources"]["previous"]["tables_sha256"]["fundamentals"]
    )
    assert rd.verify(runner.track) == []
    # Um store que substitui o retrato antigo não autentica a fonte originalmente usada.
    assert rd.verify(runner.track, market_loader=runner.store.load)
