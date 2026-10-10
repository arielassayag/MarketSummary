"""DADOS SIMULADOS: protocolo C em raízes privadas, sem autorização financeira.

As fixtures exercem somente selos/persistência/recuperação. O positivo econômico
integrado deve passar pela composição nativa A/B e pelo escritor Book separado.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from cdp.audit import AuditLog
from cdp.config import FundConfig
from cdp.contracts import (
    BookEntry,
    DailyPosition,
    DailyRecord,
    DailyRisk,
    Decision,
    OptimizerDiagnostics,
    Proposal,
    RiskSummary,
)
from cdp.hashing import sha256_obj, sha256_text
from cdp.workflow import net_moc_prova as proof
from cdp.workflow import risco_diario as risk
from cdp.workflow.book import _write_exclusive, dump_json
from cdp.workflow.net_moc import (
    RECORD_MARKER,
    SCHEMA,
    NetCandidate,
    NetUnverifiable,
    PhysicalSources,
    archive_config,
    exact_net,
    stamp,
)
from cdp.workflow.track_record import GENESIS_RECORD_HASH, TrackRecord, record_json

DAY = date(2026, 11, 13)


def native_proposal(cfg):
    from cdp.workflow.net_moc import PROPOSAL_KEY

    rs = RiskSummary(
        ex_ante_vol=0, factor_vol=0, specific_vol=0, factor_risk_share=0, beta=0, gross=0, net=0,
        long_exposure=0, short_exposure=0, n_long=0, n_short=0, var_1d_99=0, es_1d_99=0,
        var_1w_99=0, effective_n=0, max_days_to_liquidate=0, pct_nav_liquidated_1d=0,
        stress_tests={"stress_ausente": math.nan})
    return Proposal(
        proposal_id="fixture-protocolo-c", week=DAY, version=1,
        created_at=datetime(2026, 11, 13, 20, tzinfo=UTC), created_by="sistema", nav_usd=100,
        snapshot_id="DADOS SIMULADOS", snapshot_hash="b" * 64, config_hash=cfg.config_hash(),
        research_hash="c" * 64, overrides={PROPOSAL_KEY: stamp(cfg)}, positions=[],
        risk=rs, compliance=[], optimizer=OptimizerDiagnostics(status="hold", solver="nenhum", solve_seconds=0),
        is_synthetic=True, data_notice="DADOS SIMULADOS")


def inventory(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@pytest.fixture(params=["main", "shadow"])
def candidate(tmp_path, request):
    root = tmp_path / "book"
    root.mkdir()
    market = tmp_path / "market"
    market.mkdir()
    (market / "origem.json").write_text('{"data_notice":"DADOS SIMULADOS"}\n')
    (root / "origem.json").write_text('{"data_notice":"DADOS SIMULADOS"}\n')
    audit = AuditLog(root / "audit_log.jsonl")
    audit.append("FIXTURE_PROTOCOL_C", "teste", {"data_notice": "DADOS SIMULADOS"}, week=DAY)
    side = request.param
    cfg = FundConfig().with_overrides({"execution": {}})
    cfg_path = archive_config(root, cfg)
    proposal = native_proposal(cfg)
    proposal_raw = dump_json(proposal)
    if side == "main":
        _write_exclusive(root / str(DAY) / "proposal_v1.json", proposal_raw)
        audit.append("PROPOSAL_CREATED", "teste", proposal.proposal_hash(), week=DAY)
        decision = Decision(
            week=DAY, proposal_id=proposal.proposal_id, proposal_hash=proposal.proposal_hash(),
            snapshot_hash=proposal.snapshot_hash, config_hash=proposal.config_hash,
            research_hash=proposal.research_hash, decision="APPROVE", approver="Operador Simulado",
            rationale="DADOS SIMULADOS: protocolo C, sem aprovação financeira de escritor",
            decided_at=proposal.created_at, approval_hash="a" * 64)
        _write_exclusive(root / str(DAY) / "decision_v1.json", dump_json(decision))
        audit.append("DECISION_APPROVE", "teste", decision, week=DAY)
        approval = decision.approval_hash
    else:
        _write_exclusive(root / str(DAY) / "shadow_quant.json", proposal_raw)
        _write_exclusive(root / "track_record_shadow" / "proposals" / f"{DAY}.json", proposal_raw)
        audit.append("SHADOW_QUANT", "teste", {"sha256": sha256_text(proposal_raw)}, week=DAY)
        decision, approval = None, proposal.proposal_hash()
    record = DailyRecord(
        date=DAY, fund_name="DADOS SIMULADOS", track_record_type=side,
        nav_start_usd=100, nav_end_usd=100, pnl_usd=0, ret=0,
        pnl_components={n: 0 for n in ("equity", "costs", "borrow", "financing")},
        risk=DailyRisk(gross=0, net=0, long_exposure=0, short_exposure=0, n_long=0, n_short=0),
        live_book_week=DAY, approval_hash=approval,
        prev_record_hash=GENESIS_RECORD_HASH, is_synthetic=True, data_notice="DADOS SIMULADOS")
    diagnostic = {"policy": risk.POLICY, "session": str(DAY), "data_notice": "DADOS SIMULADOS"}
    record = record.model_copy(update={"input_hashes": {risk.MARKER: sha256_text(risk.text(diagnostic))}})
    record = record.model_copy(update={"record_hash": record.compute_hash()})
    entry = BookEntry(week=DAY, proposal_id="fixture-protocolo-c", approval_hash=approval,
                      booked_at=datetime(2026, 11, 13, 20, tzinfo=UTC), nav_usd=100,
                      positions=[], pricing_note="DADOS SIMULADOS")
    tr = TrackRecord(root / ("track_record" if side == "main" else "track_record_shadow"))
    outputs = {proof._booked_path(root, side, DAY), tr.record_path(DAY),
               tr.csv_path, risk.path(tr, DAY)}
    sources = PhysicalSources({"book": root, "market": market}, audit, excluded=outputs)
    base = {"schema": SCHEMA, "side": side, "session": str(DAY),
            "entry": entry.model_dump(mode="json"), "record": record.model_dump(mode="json"),
            "diagnostic": diagnostic.copy(), "sources": sources.manifest(),
            "proposal_json": proposal_raw,
            "decision": decision.model_dump(mode="json") if decision else None,
            "config_raw": cfg_path.read_text(), "config": json.loads(cfg_path.read_text()),
            "config_raw_sha256": sha256_text(cfg_path.read_text()),
            "net": exact_net(record, cfg_path.read_text()),
            "data_notice": "DADOS SIMULADOS: fixture C, não receita A/B"}
    obj = NetCandidate(root, audit, side, entry, record, diagnostic, base, sources)
    yield obj
    sources.close()


def track(candidate):
    return TrackRecord(candidate.root / ("track_record" if candidate.side == "main"
                                         else "track_record_shadow"))


def booked(candidate, *, event=True):
    p = proof._booked_path(candidate.root, candidate.side, DAY)
    _write_exclusive(p, dump_json(candidate.entry))
    if event:
        candidate.audit.append("BOOKED" if candidate.side == "main" else "BOOKED_SHADOW",
                               "teste", candidate.entry, week=DAY)


def prepare(candidate):
    return proof.prepare(candidate)


def finish(candidate):
    prepare(candidate)
    booked(candidate)
    tr = track(candidate)
    risk.append(tr, candidate.record, candidate.diagnostic)
    proof.bind(tr, candidate.record)
    return tr


def test_seal_is_memory_only_and_preserves_all_economics(candidate):
    before = inventory(candidate.root.parent)
    old_record, old_diagnostic = proof._unsealed(candidate.record, candidate.diagnostic)
    result = proof.seal(candidate)
    assert inventory(candidate.root.parent) == before
    assert proof._unsealed(candidate.record, candidate.diagnostic) == (old_record, old_diagnostic)
    assert result.base_sha256 == candidate.record.input_hashes[RECORD_MARKER]
    assert result.base_sha256 == candidate.diagnostic[RECORD_MARKER]
    assert proof.seal(candidate).candidate_raw == result.candidate_raw


def test_preparation_recovery_is_literal_and_idempotent(candidate):
    result = prepare(candidate)
    before = inventory(candidate.root.parent)
    got = proof.recover(candidate.root, DAY, candidate.side)
    assert got.state == "prepared"
    assert got.entry == candidate.entry and got.record == candidate.record
    assert got.diagnostic == candidate.diagnostic
    assert prepare(candidate).candidate_raw == result.candidate_raw
    assert inventory(candidate.root.parent) == before
    assert len([e for e in candidate.audit.events() if e.event_type == proof.PREPARED_EVENT]) == 1
    assert not (proof.proof_dir(candidate.root, candidate.side, DAY, DAY) / "binding.json").exists()


def test_complete_binding_requires_native_booked_and_daily_events(candidate):
    prepare(candidate)
    with pytest.raises(NetUnverifiable, match="prova física ausente"):
        proof.validate_record(track(candidate), candidate.record)
    booked(candidate, event=False)
    assert proof.recover(candidate.root, DAY, candidate.side).state == "booked_pending_event"
    with pytest.raises(NetUnverifiable, match="não autenticada"):
        proof.validate_record(track(candidate), candidate.record)
    candidate.audit.append("BOOKED" if candidate.side == "main" else "BOOKED_SHADOW",
                           "teste", candidate.entry, week=DAY)
    assert proof.recover(candidate.root, DAY, candidate.side).state == "booked"
    tr = track(candidate)
    proof.validate_record(tr, candidate.record)
    risk.append(tr, candidate.record, candidate.diagnostic)
    # risco.recover integrado fecha o vínculo imediatamente após seu próprio selo.
    assert proof.recover(candidate.root, DAY, candidate.side).state == "bound"
    proof.bind(tr, candidate.record)
    assert proof.load(tr, candidate.record) == candidate.base
    assert proof.recover(candidate.root, DAY, candidate.side).state == "bound"
    before = inventory(candidate.root.parent)
    proof.bind(tr, candidate.record)
    assert inventory(candidate.root.parent) == before
    assert len([e for e in candidate.audit.events() if e.event_type == proof.BOUND_EVENT]) == 1


def test_orphan_files_have_no_preparation_authority(candidate):
    sealed = proof.seal(candidate)
    folder = proof.proof_dir(candidate.root, candidate.side, DAY, DAY)
    _write_exclusive(folder / "base.json", sealed.base_raw)
    _write_exclusive(folder / "candidate.json", sealed.candidate_raw)
    before = inventory(candidate.root.parent)
    with pytest.raises(NetUnverifiable, match="órfão"):
        proof.recover(candidate.root, DAY, candidate.side)
    assert inventory(candidate.root.parent) == before


def test_interruption_after_record_json_recovers_native_tail_without_rewrite(candidate, monkeypatch):
    prepare(candidate)
    booked(candidate)
    tr = track(candidate)
    original = TrackRecord.append

    def crash_after_json(self, rec):
        _write_exclusive(self.record_path(rec.date), record_json(rec))
        raise RuntimeError("interrupção simulada")

    with monkeypatch.context() as patch:
        patch.setattr(TrackRecord, "append", crash_after_json)
        with pytest.raises(RuntimeError, match="interrupção simulada"):
            risk.append(tr, candidate.record, candidate.diagnostic)
    assert TrackRecord.append is original
    raw_record, raw_diag = tr.record_path(DAY).read_bytes(), risk.path(tr, DAY).read_bytes()
    assert proof.recover(candidate.root, DAY, candidate.side).state == "recorded_pending_binding"
    risk.recover(tr, candidate.record)
    proof.bind(tr, candidate.record)
    assert proof.recover(candidate.root, DAY, candidate.side).state == "bound"
    assert tr.record_path(DAY).read_bytes() == raw_record
    assert risk.path(tr, DAY).read_bytes() == raw_diag
    assert tr.verify()[0]


def test_interruption_after_binding_file_completes_exactly_one_event(candidate, monkeypatch):
    prepare(candidate)
    booked(candidate)
    tr = track(candidate)
    original = AuditLog.append

    def interrupt(self, kind, *args, **kwargs):
        if kind == proof.BOUND_EVENT:
            raise RuntimeError("interrupção do vínculo")
        return original(self, kind, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(AuditLog, "append", interrupt)
        with pytest.raises(RuntimeError, match="interrupção do vínculo"):
            risk.append(tr, candidate.record, candidate.diagnostic)
    p = proof.proof_dir(candidate.root, candidate.side, DAY, DAY) / "binding.json"
    raw = p.read_bytes()
    assert proof.recover(candidate.root, DAY, candidate.side).state == "recorded_pending_binding"
    proof.bind(tr, candidate.record)
    assert p.read_bytes() == raw
    assert len([e for e in tr.audit.events() if e.event_type == proof.BOUND_EVENT]) == 1


@pytest.mark.parametrize("name", ["base.json", "candidate.json", "binding.json", "booked", "record", "risk"])
def test_any_physical_tamper_is_refused_without_writes(candidate, name):
    tr = finish(candidate)
    folder = proof.proof_dir(candidate.root, candidate.side, DAY, DAY)
    paths = {"booked": proof._booked_path(candidate.root, candidate.side, DAY),
             "record": tr.record_path(DAY), "risk": risk.path(tr, DAY)}
    p = paths.get(name, folder / name)
    p.write_bytes(p.read_bytes() + b" ")
    before = inventory(candidate.root.parent)
    with pytest.raises(NetUnverifiable):
        proof.load(tr, candidate.record)
    assert inventory(candidate.root.parent) == before


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "extra", "unknown_schema", "duplicate_json"])
def test_nonexclusive_unknown_or_ambiguous_proof_refused(candidate, tmp_path, kind):
    prepare(candidate)
    folder = proof.proof_dir(candidate.root, candidate.side, DAY, DAY)
    p = folder / "candidate.json"
    if kind == "symlink":
        target = tmp_path / "saved.json"
        p.rename(target)
        p.symlink_to(target)
    elif kind == "hardlink":
        (tmp_path / "alias.json").hardlink_to(p)
    elif kind == "extra":
        (folder / "pass.json").write_text('{"PASS":true}')
    elif kind == "unknown_schema":
        obj = json.loads(p.read_text())
        obj["schema"] = "cdp.net_moc.candidate/v99"
        p.write_text(proof._text(obj))
    else:
        p.write_text('{"schema":1,"schema":2}\n')
    with pytest.raises(NetUnverifiable):
        proof.recover(candidate.root, DAY, candidate.side)


def test_changed_source_is_refused_before_persisting_preparation(candidate):
    (candidate.root / "origem.json").write_text('{"data_notice":"DADOS SIMULADOS adulterado"}\n')
    with pytest.raises(NetUnverifiable, match="origem física mudou"):
        prepare(candidate)
    assert not (candidate.root / proof.FOLDER).exists()


def test_lapse_preserves_candidate_and_never_returns_booking_state(candidate):
    if candidate.side == "shadow":
        prepare(candidate)
        assert proof.recover(candidate.root, DAY, "shadow").state == "prepared"
        assert not (candidate.root / str(DAY) / "efetivacao_recusada.json").exists()
        return
    prepare(candidate)
    payload = {"semana": str(DAY), "sessao": str(DAY), "proposal_id": candidate.entry.proposal_id,
               "approval_hash": candidate.entry.approval_hash, "motivo": "NET FAIL", "regra": "simulada"}
    _write_exclusive(candidate.root / str(DAY) / "efetivacao_recusada.json", dump_json(payload))
    candidate.audit.append("BOOKING_LAPSED", "teste", payload, week=DAY)
    before = inventory(candidate.root.parent)
    assert proof.recover(candidate.root, DAY).state == "lapsed"
    assert inventory(candidate.root.parent) == before
    assert not proof._booked_path(candidate.root, "main", DAY).exists()


def test_fake_record_marker_or_different_side_does_not_bind(candidate):
    tr = finish(candidate)
    bad = candidate.record.model_copy(deep=True)
    bad = bad.model_copy(update={"input_hashes": dict(bad.input_hashes) | {RECORD_MARKER: "f" * 64}})
    bad = bad.model_copy(update={"record_hash": bad.compute_hash()})
    with pytest.raises(NetUnverifiable):
        proof.load(tr, bad)
    other = TrackRecord(candidate.root / ("track_record_shadow" if candidate.side == "main"
                                         else "track_record"))
    with pytest.raises(NetUnverifiable):
        proof.load(other, candidate.record)


def test_prepared_event_duplicate_is_refused(candidate):
    prepared = prepare(candidate)
    candidate.audit.append(proof.PREPARED_EVENT, "teste", prepared.binding, week=DAY)
    with pytest.raises(NetUnverifiable, match="duplicada"):
        proof.recover(candidate.root, DAY, candidate.side)


def test_hashes_alone_do_not_authorize_an_orphan_candidate(candidate):
    sealed = proof.seal(candidate)
    assert sha256_obj(sealed.binding)
    assert sealed.base_sha256 == sha256_text(sealed.base_raw)
    with pytest.raises(NetUnverifiable):
        proof.validate_booking(candidate)


def test_pending_recovery_rechecks_old_sources_and_refuses_new_names(candidate):
    prepare(candidate)
    (candidate.root.parent / "market" / "extra.json").write_text('{"data_notice":"DADOS SIMULADOS"}')
    before = inventory(candidate.root.parent)
    with pytest.raises(NetUnverifiable, match="readset físico antigo"):
        proof.recover(candidate.root, DAY, candidate.side)
    assert inventory(candidate.root.parent) == before


def test_seal_never_inserts_marker_into_aliased_economic_base(candidate):
    candidate.base["diagnostic"] = candidate.diagnostic
    original = proof._text(candidate.base)
    first = proof.seal(candidate)
    assert proof._text(candidate.base) == original
    assert RECORD_MARKER not in candidate.base["diagnostic"]
    assert proof.seal(candidate).candidate_raw == first.candidate_raw
    assert prepare(candidate).candidate_raw == first.candidate_raw


def test_bound_historical_proof_survives_later_native_records_and_namespace(candidate):
    tr = finish(candidate)
    day = DAY + timedelta(days=3)
    diagnostic = {"policy": risk.POLICY, "session": str(day), "data_notice": "DADOS SIMULADOS"}
    record = candidate.record.model_copy(update={
        "date": day, "prev_record_hash": candidate.record.record_hash,
        "input_hashes": {risk.MARKER: sha256_text(risk.text(diagnostic))}})
    record = record.model_copy(update={"record_hash": record.compute_hash()})
    risk.append(tr, record, diagnostic)
    (candidate.root.parent / "market" / "novo-vintage.json").write_text('{"data_notice":"DADOS SIMULADOS"}')
    before = inventory(candidate.root.parent)
    assert proof.load(tr, candidate.record) == candidate.base
    assert proof.recover(candidate.root, DAY, candidate.side).state == "bound"
    proof.bind(tr, candidate.record)
    assert inventory(candidate.root.parent) == before


def test_removed_marker_on_prospective_booking_day_is_not_historical(candidate):
    prepare(candidate)
    booked(candidate)
    removed = candidate.record.model_copy(update={
        "input_hashes": {k: v for k, v in candidate.record.input_hashes.items()
                         if k != RECORD_MARKER}})
    removed = removed.model_copy(update={"record_hash": removed.compute_hash()})
    before = inventory(candidate.root.parent)
    with pytest.raises(NetUnverifiable, match="sem marcador NET"):
        proof.validate_record(track(candidate), removed)
    assert inventory(candidate.root.parent) == before


@pytest.mark.parametrize("change", ["nav", "position", "passed", "limit"])
def test_resealed_economics_cannot_replace_native_config_or_comparison(candidate, change):
    from cdp.config import config_json
    from cdp.workflow.net_moc import PROPOSAL_KEY

    before = inventory(candidate.root.parent)
    if change == "passed":
        candidate.base["net"] = {"passed": True}
    elif change == "nav":
        candidate.record = candidate.record.model_copy(update={"nav_end_usd": 99, "pnl_usd": -1,
                                                               "ret": -0.01, "pnl_components": {
                                                                   "equity": 0, "costs": -1,
                                                                   "borrow": 0, "financing": 0}})
        candidate.record = candidate.record.model_copy(update={"record_hash": candidate.record.compute_hash()})
        candidate.base["record"] = candidate.record.model_dump(mode="json")
    elif change == "position":
        pos = DailyPosition(issuer_id="SIM", ticker="SIM", currency="USD", side="LONG",
                            shares=1, price_local=1, price_usd=1, market_value_usd=1,
                            weight=0.01, day_pnl_usd=0)
        candidate.record = candidate.record.model_copy(update={"positions": [pos]})
        candidate.record = candidate.record.model_copy(update={"record_hash": candidate.record.compute_hash()})
        candidate.base["record"] = candidate.record.model_dump(mode="json")
    else:
        cfg = FundConfig.model_validate_json(candidate.base["config_raw"]).with_overrides(
            {"risk": {"net_exposure_max_abs": 0.02}})
        raw = config_json(cfg)
        proposal = Proposal.model_validate_json(candidate.base["proposal_json"])
        proposal = proposal.model_copy(update={"config_hash": cfg.config_hash(),
                                               "overrides": {PROPOSAL_KEY: stamp(cfg)}})
        candidate.base["config"] = json.loads(raw)
        candidate.base["config_raw"] = raw
        candidate.base["config_raw_sha256"] = sha256_text(raw)
        candidate.base["proposal_json"] = dump_json(proposal)
        if candidate.side == "main":
            decision = Decision.model_validate(candidate.base["decision"]).model_copy(update={
                "config_hash": cfg.config_hash(), "proposal_hash": proposal.proposal_hash()})
            candidate.base["decision"] = decision.model_dump(mode="json")
        else:
            candidate.entry = candidate.entry.model_copy(update={"approval_hash": proposal.proposal_hash()})
            candidate.record = candidate.record.model_copy(update={"approval_hash": proposal.proposal_hash()})
            candidate.record = candidate.record.model_copy(update={"record_hash": candidate.record.compute_hash()})
            candidate.base["entry"] = candidate.entry.model_dump(mode="json")
            candidate.base["record"] = candidate.record.model_dump(mode="json")
        candidate.base["net"] = exact_net(candidate.record, raw)
    with pytest.raises(NetUnverifiable):
        prepare(candidate)
    assert inventory(candidate.root.parent) == before


def test_received_resealed_nav_is_rejected_before_preparation_event_lookup(candidate):
    prepare(candidate)
    folder = proof.proof_dir(candidate.root, candidate.side, DAY, DAY)
    base = json.loads((folder / "base.json").read_text())
    envelope = json.loads((folder / "candidate.json").read_text())
    record = candidate.record.model_copy(update={"nav_end_usd": 99, "pnl_usd": -1, "ret": -0.01,
                                                "pnl_components": {"equity": 0, "costs": -1,
                                                                   "borrow": 0, "financing": 0}})
    diagnostic = copy.deepcopy(candidate.diagnostic)
    unsealed, _ = proof._unsealed(record, diagnostic)
    base["record"] = unsealed
    base_raw = proof._text(base)
    base_sha = sha256_text(base_raw)
    diagnostic[RECORD_MARKER] = base_sha
    diagnostic_raw = risk.text(diagnostic)
    record = record.model_copy(update={"input_hashes": dict(record.input_hashes) | {
        RECORD_MARKER: base_sha, risk.MARKER: sha256_text(diagnostic_raw)}})
    record = record.model_copy(update={"record_hash": record.compute_hash()})
    envelope.update({"base_sha256": base_sha, "record_json": record_json(record),
                     "record_sha256": sha256_text(record_json(record)),
                     "diagnostic_json": diagnostic_raw, "diagnostic_sha256": sha256_text(diagnostic_raw)})
    (folder / "base.json").write_text(base_raw)
    (folder / "candidate.json").write_text(proof._text(envelope))
    before = inventory(candidate.root.parent)
    with pytest.raises(NetUnverifiable, match="configuração/comparação NET"):
        proof.recover(candidate.root, DAY, candidate.side)
    assert inventory(candidate.root.parent) == before


@pytest.mark.parametrize("name", ["base.json", "candidate.json", "binding.json"])
@pytest.mark.parametrize("change", ["missing", "tamper"])
def test_native_verify_rejects_missing_or_tampered_bound_proof_without_writes(candidate, name, change):
    tr = finish(candidate)
    assert tr.verify() == (True, [])
    path = proof.proof_dir(candidate.root, candidate.side, DAY, DAY) / name
    if change == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" ")
    before = inventory(candidate.root.parent)
    ok, problems = tr.verify()
    assert not ok and any("prova NET inválida" in p for p in problems)
    assert inventory(candidate.root.parent) == before


def test_native_verify_does_not_accept_removed_marker_with_rehashed_json_csv_and_event(candidate):
    from cdp.workflow.track_record import CSV_COLUMNS, _cell, record_summary

    prepare(candidate)
    booked(candidate)
    tr = track(candidate)
    record = candidate.record.model_copy(update={
        "input_hashes": {k: v for k, v in candidate.record.input_hashes.items() if k != RECORD_MARKER}})
    record = record.model_copy(update={"record_hash": record.compute_hash()})
    _write_exclusive(tr.record_path(DAY), record_json(record))
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    row = record_summary(record)
    writer.writerow([_cell(row[c]) for c in CSV_COLUMNS])
    _write_exclusive(tr.csv_path, buf.getvalue())
    tr.audit.append(tr.audit_event, tr.actor, record.record_hash, week=DAY)
    before = inventory(candidate.root.parent)
    ok, problems = tr.verify()
    assert not ok and len(problems) == 1 and "sem marcador NET" in problems[0]
    assert inventory(candidate.root.parent) == before


def test_native_absent_stress_is_retained_as_literal_original_proposal_json(candidate):
    tr = finish(candidate)
    folder = proof.proof_dir(candidate.root, candidate.side, DAY, DAY)
    base = proof._object((folder / "base.json").read_text())
    source = (candidate.root / str(DAY) / "proposal_v1.json" if candidate.side == "main" else
              candidate.root / str(DAY) / "shadow_quant.json")
    assert base["proposal_json"] == source.read_text()
    assert '"stress_ausente": NaN' in base["proposal_json"]
    native = Proposal.model_validate_json(base["proposal_json"])
    assert math.isnan(native.risk.stress_tests["stress_ausente"])
    assert proof.load(tr, candidate.record) == base


def test_unmarked_historical_utility_series_remains_readable(candidate, tmp_path):
    from cdp.workflow.track_record import CSV_COLUMNS, _cell, record_summary

    tr = TrackRecord(tmp_path / "serie_historica_utilitaria")
    record = candidate.record
    _write_exclusive(tr.record_path(DAY), record_json(record))
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    row = record_summary(record)
    writer.writerow([_cell(row[c]) for c in CSV_COLUMNS])
    _write_exclusive(tr.csv_path, buf.getvalue())
    tr.audit.append(tr.audit_event, tr.actor, record.record_hash, week=DAY)
    before = inventory(tmp_path)
    assert proof.load(tr, record) is None
    assert tr.verify() == (True, [])
    assert inventory(tmp_path) == before


def copy_literal_tree(candidate, tmp_path_factory):
    target = tmp_path_factory.mktemp("replica-literal-net") / "tree"
    shutil.copytree(candidate.root.parent, target)
    assert inventory(target) == inventory(candidate.root.parent)
    return target / "book"


def test_bound_literal_replica_reads_without_original_paths_or_rewriting(candidate, tmp_path_factory):
    finish(candidate)
    clone_root = copy_literal_tree(candidate, tmp_path_factory)
    clone_track = TrackRecord(clone_root / ("track_record" if candidate.side == "main"
                                            else "track_record_shadow"))
    before = inventory(clone_root.parent)
    # A configuração original deixa de existir. O clone recebe seus bytes
    # próprios, nunca os caminhos/FDs registrados na origem.
    original_cfg = candidate.root / stamp(FundConfig().with_overrides({"execution": {}}))["config_path"]
    original_cfg.unlink()
    assert proof.load(clone_track, candidate.record) == candidate.base
    assert proof.recover(clone_root, DAY, candidate.side).state == "bound"
    assert clone_track.verify()[0]
    proof.bind(clone_track, candidate.record)  # repetição BOUND continua somente leitura
    assert inventory(clone_root.parent) == before
    with pytest.raises(NetUnverifiable, match="raiz econômica"):
        proof._receive_sources(clone_root, clone_track.audit, candidate.base)
    assert inventory(clone_root.parent) == before


@pytest.mark.parametrize("state", ["prepared", "booked_pending_event", "booked",
                                   "recorded_pending_binding"])
def test_pending_literal_replica_cannot_migrate_custody(candidate, tmp_path_factory, monkeypatch, state):
    prepare(candidate)
    if state != "prepared":
        booked(candidate, event=state != "booked_pending_event")
    if state == "recorded_pending_binding":
        original = AuditLog.append

        def interrupt(self, kind, *args, **kwargs):
            if kind == proof.BOUND_EVENT:
                raise RuntimeError("interrupção antes do evento BOUND")
            return original(self, kind, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(AuditLog, "append", interrupt)
            with pytest.raises(RuntimeError, match="antes do evento BOUND"):
                risk.append(track(candidate), candidate.record, candidate.diagnostic)
    assert proof.recover(candidate.root, DAY, candidate.side).state == state
    clone_root = copy_literal_tree(candidate, tmp_path_factory)
    clone_track = TrackRecord(clone_root / ("track_record" if candidate.side == "main"
                                            else "track_record_shadow"))
    before = inventory(clone_root.parent)
    with pytest.raises(NetUnverifiable, match="raiz da trilha"):
        proof.recover(clone_root, DAY, candidate.side)
    with pytest.raises(NetUnverifiable, match="raiz da trilha"):
        proof.validate_record(clone_track, candidate.record)
    relocated = replace(candidate, root=clone_root, audit=clone_track.audit)
    with pytest.raises(NetUnverifiable, match="raiz da trilha"):
        proof.prepare(relocated)
    assert inventory(clone_root.parent) == before


@pytest.mark.parametrize("change", ["prefix", "binding"])
def test_bound_replica_still_requires_exact_prefix_and_final_binding(candidate, tmp_path_factory, change):
    finish(candidate)
    clone_root = copy_literal_tree(candidate, tmp_path_factory)
    clone_track = TrackRecord(clone_root / ("track_record" if candidate.side == "main"
                                            else "track_record_shadow"))
    if change == "prefix":
        p = clone_root / "audit_log.jsonl"
        raw = p.read_text()
        altered = raw.replace('"actor": "teste"', '"actor": "adulterado"', 1)
        assert altered != raw
        p.write_text(altered)
    else:
        (proof.proof_dir(clone_root, candidate.side, DAY, DAY) / "binding.json").unlink()
    before = inventory(clone_root.parent)
    with pytest.raises(NetUnverifiable):
        proof.load(clone_track, candidate.record)
    with pytest.raises(NetUnverifiable):
        proof.recover(clone_root, DAY, candidate.side)
    assert inventory(clone_root.parent) == before
