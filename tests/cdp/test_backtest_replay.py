"""Replay usa ordens/ações efetivas e autentica as duas cronologias (DADOS SIMULADOS)."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from cdp.backtest.replay import (
    ReplayIntegrityError,
    ReplaySchedule,
    ReplayStore,
    _execution_config,
    _inventory,
    _report_payload,
    _require_receipt,
    _Steps,
    isolated_output,
    replay_sessions,
    run_replay,
    verify_replay,
)
from cdp.calendar import is_rebalance_day
from cdp.config import load_config
from cdp.data.snapshot import load_snapshot, write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file
from cdp.research.evaluation import AuthenticatedViewTracker
from cdp.workflow.runtime import Runtime

FIRST, END = date(2024, 3, 8), date(2024, 3, 12)


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("replay_inputs")
    source = root / "source"
    cfg = load_config()
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=END)
    rng = np.random.default_rng(730)
    benchmarks = md.benchmarks.copy()
    for factor in cfg.risk_model.macro_factors:
        benchmarks[factor] = 80 * np.cumprod(1 + rng.normal(0, .02, len(benchmarks)))
    md = replace(md, benchmarks=benchmarks)
    write_snapshot(md, source)
    return root, source, cfg


@pytest.fixture(scope="module")
def finished(inputs):
    root, source, cfg = inputs
    out = root / ".cdp" / "ensaios" / "full"
    source_before = _inventory(source)
    config_before = cfg.model_dump(mode="json")
    result = run_replay(source, out, start=FIRST, end=END, mode="simulado", cfg=cfg,
                        workspace=root)
    assert _inventory(source) == source_before
    assert cfg.model_dump(mode="json") == config_before
    return out, result


def test_calendar_partial_week_does_not_invent_tuesday_decision():
    cfg = _execution_config(load_config(), date(2026, 9, 4))
    sessions = replay_sessions(date(2026, 9, 4), date(2026, 10, 6))
    decisions = [d for d in sessions if is_rebalance_day(d, cfg)]
    assert decisions == [date(2026, 9, d) for d in (4, 11, 18, 25)] + [date(2026, 10, 2)]
    cfg_partial = _execution_config(load_config(), date(2026, 10, 5))
    assert cfg_partial.fund.inception_date == date(2026, 10, 9)
    assert not is_rebalance_day(date(2026, 10, 6), cfg_partial)


def test_only_inception_is_a_declared_counterfactual():
    cfg = load_config()
    effective = _execution_config(cfg, FIRST)
    before, after = cfg.model_dump(mode="json"), effective.model_dump(mode="json")
    assert after["fund"].pop("inception_date") == str(FIRST)
    before["fund"].pop("inception_date")
    assert before == after


@pytest.mark.parametrize("values", [{"prepare_at": time(20)}, {"decide_at": time(22)}])
def test_schedule_rejects_time_regression(values):
    with pytest.raises(ValueError, match="prepare_at"):
        ReplaySchedule(**values)


def test_output_official_path_and_symlink_are_rejected(tmp_path):
    with pytest.raises(ReplayIntegrityError, match="dentro"):
        isolated_output(tmp_path / "book", tmp_path)
    (tmp_path / ".cdp").mkdir()
    (tmp_path / ".cdp" / "ensaios").symlink_to(tmp_path / "book")
    with pytest.raises(ReplayIntegrityError, match="redirecionada"):
        isolated_output(tmp_path / ".cdp" / "ensaios" / "evil", tmp_path)


def test_real_operational_paths_book_actions_nav_costs_and_macro(finished):
    out, result = finished
    assert result["integridade"] and result["registros"] == 3
    assert result["prospectiva"] is False
    assert result["merito_economico_validado"] is False
    assert "DADOS SIMULADOS" in result["aviso"]
    assert len(result["decisoes"]) == 1
    assert result["decisoes"][0]["data"] == str(FIRST)
    assert result["decisoes"][0]["efetivada"] is True
    assert result["decisoes"][0]["posicoes_efetivas"] > 0
    assert any("efetivação conferida" in m for m in result["verificacao"])
    assert not any("sem base de mercado para conferir" in m for m in result["verificacao"])
    cfg = _execution_config(load_config(), FIRST)
    rt = Runtime(cfg, out / "book", out / "market", out / "reports",
                 store_override=ReplayStore(out / "market", cfg=cfg), teses_root=None)
    first = rt.track().get(FIRST)
    booked = rt.book.load_booked(FIRST)
    assert first.nav_start_usd == cfg.fund.inception_nav_usd
    assert {(p.issuer_id, p.ticker): p.shares for p in first.positions} == {
        (p.issuer_id, p.ticker): p.shares for p in booked.positions}
    assert first.pnl_components["costs"] < 0
    for day in result["diarios"]:
        assert abs(day["ponte_nav_residuo_usd"]) < 1e-6
        assert abs(day["ponte_caixa_residuo_usd"]) < 1e-6
    from cdp.workflow.risco_diario import load, restore

    diagnostic = load(rt.track(), rt.track().get(END))
    assert all(f"macro:{f}" in restore(diagnostic["models"]["base"]).factor_names
               for f in cfg.risk_model.macro_factors)
    assert verify_replay(out)["integridade"]
    tracker = AuthenticatedViewTracker(out / "book", mind="codex", include_synthetic=True)
    with pytest.raises(ValueError, match="retrospectivo"):
        tracker.ic_history()


def test_resume_is_byte_identical_and_source_metadata_changes_refused(inputs, finished):
    root, source, cfg = inputs
    out, first = finished
    before = _inventory(out)
    resumed = run_replay(source, out, start=FIRST, end=END, mode="simulado", cfg=cfg,
                         workspace=root, resume=True)
    assert resumed == first and _inventory(out) == before
    source_copy = root / "source_changed"
    shutil.copytree(source, source_copy)
    manifest = source_copy / "manifest.json"
    raw = json.loads(manifest.read_text())
    raw["limitations"].append("captura alterada sem mudar os preços")
    manifest.write_text(json.dumps(raw))
    with pytest.raises(ReplayIntegrityError, match="Retomada diverge"):
        run_replay(source_copy, out, start=FIRST, end=END, mode="simulado", cfg=cfg,
                   workspace=root, resume=True)
    assert _inventory(out) == before


def test_store_never_chooses_future_base(finished):
    out, _ = finished
    store = ReplayStore(out / "market", close_cutoff=time(19, 22),
                        now=lambda: datetime(2024, 3, 8, 11, 7, tzinfo=ZoneInfo("America/Sao_Paulo")))
    with pytest.raises(ReplayIntegrityError, match="Sem base"):
        store.load(date(2023, 1, 2))
    assert store.load().as_of == date(2024, 3, 7)
    with pytest.raises(ReplayIntegrityError, match="posterior ao corte"):
        store.load(FIRST)


@pytest.mark.parametrize("name", ["steps.jsonl", "result.json", "inputs/fund_ensaio.json"])
def test_tamper_never_resumes_or_passes_verify(tmp_path, finished, name):
    original, _ = finished
    copied = tmp_path / "copy"
    shutil.copytree(original, copied)
    path = copied / name
    before = sha256_file(path)
    path.write_bytes(path.read_bytes() + b"\n ")
    assert sha256_file(path) != before
    with pytest.raises(ReplayIntegrityError):
        verify_replay(copied)


def test_completed_result_deletion_is_detected_without_writing(tmp_path, finished):
    copied = tmp_path / "copy"
    shutil.copytree(finished[0], copied)
    (copied / "result.json").unlink()
    before = _inventory(copied)
    with pytest.raises(ReplayIntegrityError, match="removido"):
        verify_replay(copied)
    assert _inventory(copied) == before


def test_pending_step_anchor_needs_the_authentic_file(tmp_path, finished):
    copied = tmp_path / "copy"
    shutil.copytree(finished[0], copied)
    audit = copied / "book" / "audit_log.jsonl"
    lines = audit.read_text().splitlines(keepends=True)
    assert json.loads(lines[-1])["event_type"] == "REPLAY_COMPLETE"
    audit.write_text("".join(lines[:-1]))
    (copied / "result.json").unlink()
    steps = copied / "steps.jsonl"
    rows = steps.read_text().splitlines(keepends=True)
    pending = json.loads(rows[-1])
    steps.write_text("".join(rows[:-1]))
    report = verify_replay(copied)
    assert report["integridade"] and not report["concluido"] and report["pendencias"]
    (copied / "steps" / pending["file"]).unlink()
    before = _inventory(copied)
    with pytest.raises(ReplayIntegrityError, match="pendente foi removido"):
        verify_replay(copied)
    assert _inventory(copied) == before


@pytest.mark.parametrize("boundary", ["inventory", "result", "anchor"])
def test_recovery_at_completion_boundaries(inputs, monkeypatch, boundary):
    import cdp.backtest.replay as replay
    from cdp.audit import AuditLog

    root, source, cfg = inputs
    out = root / ".cdp" / "ensaios" / f"crash-{boundary}"
    writer, append = replay._write_exclusive, AuditLog.append

    def interrupted_write(path, text):
        if (boundary == "inventory" and path.name == "result.json") or (
                boundary == "result" and path.name == "result.json"):
            if boundary == "result":
                writer(path, text)
            raise RuntimeError("queda simulada antes do selo final")
        return writer(path, text)

    def interrupted_append(self, event_type, *args, **kwargs):
        if boundary == "anchor" and event_type == "REPLAY_COMPLETE":
            append(self, event_type, *args, **kwargs)
            raise RuntimeError("queda simulada após o selo final")
        return append(self, event_type, *args, **kwargs)

    monkeypatch.setattr(replay, "_write_exclusive", interrupted_write)
    monkeypatch.setattr(AuditLog, "append", interrupted_append)
    with pytest.raises(RuntimeError, match="queda simulada"):
        run_replay(source, out, start=FIRST, end=FIRST, mode="simulado", cfg=cfg, workspace=root)
    before = _inventory(out)
    monkeypatch.setattr(replay, "_write_exclusive", writer)
    monkeypatch.setattr(AuditLog, "append", append)
    result = run_replay(source, out, start=FIRST, end=FIRST, mode="simulado", cfg=cfg,
                        workspace=root, resume=True)
    after = _inventory(out)
    assert result["integridade"] and verify_replay(out)["concluido"]
    for name, sha in before.items():
        if name != "book/audit_log.jsonl":
            assert after[name] == sha
    events = [json.loads(s) for s in (out / "book" / "audit_log.jsonl").read_text().splitlines()]
    assert sum(e["event_type"] == "DECISION_APPROVE" for e in events) == 1
    assert sum(e["event_type"] == "BOOKED" for e in events) == 1
    assert sum(e["event_type"] == "REPLAY_COMPLETE" for e in events) == 1


def test_one_second_after_deadline_produces_no_decision(inputs):
    root, source, cfg = inputs
    out = root / ".cdp" / "ensaios" / "late"
    result = run_replay(source, out, start=FIRST, end=FIRST, mode="simulado", cfg=cfg,
                        workspace=root, schedule=ReplaySchedule(decision_lateness_seconds=1))
    assert result["decisoes"] == [] and result["registros"] == 0
    step = json.loads((out / "steps" / f"{FIRST}-decide.json").read_text())
    assert step["result"]["status"] == "prazo_vencido"
    assert datetime.fromisoformat(step["actual_started_at"]).tzinfo is not None


def test_realized_capacity_fills_fixed_shares_and_next_decision_uses_them(inputs):
    root, _source, cfg = inputs
    last = date(2024, 3, 15)
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=last)
    benchmarks = md.benchmarks.copy()
    rng = np.random.default_rng(730)
    for factor in cfg.risk_model.macro_factors:
        benchmarks[factor] = 80 * np.cumprod(1 + rng.normal(0, .02, len(benchmarks)))
    volume = md.volume.copy()
    volume.loc[str(FIRST)] *= .008  # choque causal só no leilão, fora do ADV do prepare.
    md = replace(md, volume=volume, benchmarks=benchmarks)
    source = root / "partial-source"
    write_snapshot(md, source)
    original = _inventory(source)
    out = root / ".cdp" / "ensaios" / "partial"
    result = run_replay(source, out, start=FIRST, end=last, mode="simulado", cfg=cfg, workspace=root)
    effective = _execution_config(cfg, FIRST)
    rt = Runtime(effective, out / "book", out / "market", out / "reports",
                 store_override=ReplayStore(out / "market", cfg=effective), teses_root=None)
    first, second = rt.book.load_proposal(FIRST), rt.book.load_proposal(last)
    booked = rt.book.load_booked(FIRST)
    assert first is not None and second is not None and booked is not None
    filled = {(p.issuer_id, p.ticker): p.shares for p in booked.positions}
    raw = load_snapshot(source)
    cap = effective.execution.capacity
    partial = 0
    checked = 0
    # Oráculo independente: em USD, preço cancela cap/preço; calendário normal, lote unitário.
    for p in first.positions:
        if p.currency != "USD" or not p.shares or not filled.get((p.issuer_id, p.execution_ticker)):
            continue
        line = raw.universe.lines.loc[p.execution_ticker]
        category = "ADR" if line["line_type"] == "ADR" else "US_STOCK"
        fraction = cap.auction_participation * cap.auction_share[category] + (
            cap.preclose_participation * cap.preclose_volume_share)
        multiplier = cap.short_multiplier if p.shares < 0 else 1.
        limit = math.floor(float(raw.volume.loc[str(FIRST), p.execution_ticker]) * fraction * multiplier + 1e-9)
        expected = (1 if p.shares > 0 else -1) * min(abs(p.shares), limit)
        actual = filled[(p.issuer_id, p.execution_ticker)]
        assert actual == expected
        partial += abs(actual) < abs(p.shares)
        checked += 1
    assert checked > 0 and partial > 0
    before_second = rt.track().get(date(2024, 3, 14))
    actual_before = {(p.issuer_id, p.ticker): int(p.shares) for p in before_second.positions if p.shares}
    assert rt.book.holdings_before(last) == actual_before
    # Contexto da próxima decisão usa NAV/carteira efetivos; ordens residuais não migram.
    assert second.nav_usd == before_second.nav_end_usd
    assert _inventory(source) == original
    assert len(result["decisoes"]) == 2 and verify_replay(out)["concluido"]


@pytest.mark.parametrize("forged", [False, True])
def test_unanchored_step_never_authenticates_or_reexecutes(tmp_path, forged):
    out = tmp_path / "orphan"
    out.mkdir()
    manifest = out / "run_manifest.json"
    manifest.write_text(json.dumps({"sessions": [str(FIRST)]}))
    cfg = _execution_config(load_config(), FIRST)
    rt = Runtime(cfg, out / "book", out / "market", out / "reports", teses_root=None)
    steps = _Steps(out, rt, sha256_file(manifest))
    folder = out / "steps"
    folder.mkdir()
    path = folder / f"{FIRST}-risk_before.json"
    path.write_text(json.dumps({"step_id": f"{FIRST}/risk_before",
                                "manifest_sha256": sha256_file(manifest),
                                "result": {"status": "inventado" if forged else "original"}}))
    before = _inventory(out)
    called = []
    with pytest.raises(ReplayIntegrityError, match="sem âncora"):
        steps.run(FIRST, "risk_before", lambda: called.append(True))
    assert called == [] and _inventory(out) == before


def test_artifact_recovery_requires_exact_event_and_preserves_bytes(tmp_path):
    folder = tmp_path / "reports" / "daily" / str(FIRST)
    folder.mkdir(parents=True)
    (folder / "relatorio.md").write_text("DADOS SIMULADOS; resultado do código")
    (folder / "relatorio.html").write_text("<p>DADOS SIMULADOS</p>")
    rt = Runtime(_execution_config(load_config(), FIRST), tmp_path / "book",
                 tmp_path / "market", tmp_path / "reports", teses_root=None)
    payload = {**_report_payload(folder), "record": "1" * 64, "commentary_issues": []}
    with pytest.raises(ReplayIntegrityError, match="sem recibo"):
        _require_receipt(rt, "DAILY_REPORT", payload)
    rt.book.audit.append("DAILY_REPORT", "CDP", payload)
    before = _inventory(tmp_path)
    _require_receipt(rt, "DAILY_REPORT", payload)
    assert _inventory(tmp_path) == before
    (folder / "relatorio.md").write_text("DADOS SIMULADOS; adulterado após publicação")
    changed = {**payload, **_report_payload(folder)}
    before = _inventory(tmp_path)
    with pytest.raises(ReplayIntegrityError, match="sem recibo"):
        _require_receipt(rt, "DAILY_REPORT", changed)
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("stage", ["prepare", "daily", "weekly", "thesis"])
def test_canonical_artifacts_are_recovered_only_with_receipts(finished, stage):
    from cdp.backtest.replay import _daily_report, _prepare, _thesis, _weekly_report

    out, _ = finished
    cfg = _execution_config(load_config(), FIRST)
    rt = Runtime(cfg, out / "book", out / "market", out / "reports",
                 store_override=ReplayStore(out / "market", cfg=cfg), teses_root=None,
                 expected_mind="outro")
    before = _inventory(out)
    func, day = {"prepare": (_prepare, FIRST), "daily": (_daily_report, END),
                 "weekly": (_weekly_report, FIRST), "thesis": (_thesis, FIRST)}[stage]
    assert "existente" in func(rt, day).get("status", "") or stage == "prepare"
    assert _inventory(out) == before


def test_future_price_volume_fx_and_macro_cannot_change_first_decision(inputs, finished):
    root, source, cfg = inputs
    original, _ = finished
    md = load_snapshot(source)
    arrays = {}
    for name, multiplier in (("close", 37.), ("adj_close", 37.), ("volume", 11.),
                             ("fx", 9.), ("benchmarks", .02)):
        frame = getattr(md, name).copy()
        frame.loc[frame.index > str(FIRST)] *= multiplier
        arrays[name] = frame
    changed_source = root / "future-shock"
    write_snapshot(replace(md, **arrays), changed_source)
    inventory = _inventory(changed_source)
    out = root / ".cdp" / "ensaios" / "anticausal"
    run_replay(changed_source, out, start=FIRST, end=FIRST, mode="simulado", cfg=cfg, workspace=root)
    effective = _execution_config(cfg, FIRST)
    rts = [Runtime(effective, p / "book", p / "market", p / "reports", teses_root=None)
           for p in (original, out)]
    left, right = [rt.book.load_proposal(FIRST) for rt in rts]
    assert left is not None and right is not None and left.positions
    # Hashes da proveniência diferem; comparamos as ações e medidas econômicas.
    assert [p.model_dump() for p in left.positions] == [p.model_dump() for p in right.positions]
    assert left.risk.model_dump() == right.risk.model_dump()
    a, b = [rt.track().get(FIRST) for rt in rts]
    assert a.nav_end_usd == b.nav_end_usd and a.pnl_components == b.pnl_components
    assert a.risk.model_dump() == b.risk.model_dump()
    assert _inventory(changed_source) == inventory
