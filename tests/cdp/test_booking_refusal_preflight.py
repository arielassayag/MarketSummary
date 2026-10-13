"""DADOS SIMULADOS: trilha de recusa, sem certificar corrida/atomicidade/MOC positivo."""
from __future__ import annotations

import hashlib
from datetime import time as dtime

import pytest
from test_daily_track_record import NAV0, make_proposal, week1
from test_robustez_rotinas import WEEK, _rt
from test_robustez_rotinas import (
    market as market,
)

import cdp.workflow.book as book_module
from cdp.contracts import OptimizerDiagnostics
from cdp.hashing import sha256_obj
from cdp.workflow.autonomy import make_autonomous_decision
from cdp.workflow.book import LAPSE_EVENT, Book
from cdp.workflow.daily import (
    ExecutionRefused,
    PendingExecution,
    _BookingPreflightRefused,
    _guarded,
    book_execution,
)
from cdp.workflow.leitura_contratos import TentativaDeEfeitoLeitura


def _tree(root):
    return {str(p.relative_to(root)): (
        hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "diretório")
        for p in root.rglob("*")}


def _native_case(root, market):
    rt, clock = _rt(root, market)
    assert rt.cfg.execution is None and rt.cfg.fund.inception_nav_usd == NAV0
    runner = rt._runner()
    md = runner.store.load(as_of=WEEK).truncate(WEEK)
    # Proposta unitária recebida do corpus simulado: não é resultado de um solver.
    proposal = make_proposal(WEEK, week1(md), cfg=rt.cfg).model_copy(update={
        "snapshot_id": md.manifest.snapshot_id,
        "snapshot_hash": md.manifest.content_hash(),
        "optimizer": OptimizerDiagnostics(
            status="fixture_sem_solver", solver="nenhum", solve_seconds=0.0),
    })
    clock.set(WEEK, dtime(15, 0))
    decision = make_autonomous_decision(
        proposal, research_hash=proposal.research_hash, pm_decision_hash="f" * 64,
        rationale="DADOS SIMULADOS: controle unitário de recusa e auditoria.",
        decided_at=clock())
    rt.book.save_proposal(proposal)
    rt.book.save_decision(decision)
    rt.set_kill_switch(True, "gatilho HARD (teste)", "CDP — rotina de risco")
    proposal = rt.book.load_proposal(WEEK)
    decision = rt.book.load_decision(WEEK)
    plan = runner._plan_from_pending(WEEK, None, PendingExecution(proposal, decision))
    context = runner.context(WEEK, runner.store.load(WEEK), None)
    result = runner._prepare_side(runner.main, context, None, plan)
    assert result.entry is not None
    return rt, runner, proposal, decision, plan, result.entry


def _causes(exc):
    causes = []
    while exc is not None:
        causes.append(exc)
        exc = exc.__cause__
    return causes


def _assert_refusal(event, plan, reason, actor):
    assert event.event_type == "BOOKING_REFUSED"
    assert event.week == plan.week and event.actor == actor
    assert event.payload_hash == sha256_obj({
        "proposal_id": plan.proposal_id, "approval_hash": plan.approval_hash,
        "reason": reason,
    })
    assert event.summary == f"Booking recusado ({plan.proposal_id}): {reason[:300]}"


def test_preflight_native_refusal_is_typed_and_never_writes(market, tmp_path):
    rt, runner, proposal, decision, plan, entry = _native_case(tmp_path, market)
    before = _tree(rt.book.root)
    with pytest.raises(_BookingPreflightRefused) as info:
        book_execution(rt.book, entry, proposal, decision, rt.cfg, dry_run=True)
    assert type(info.value) is _BookingPreflightRefused
    assert type(info.value.__cause__) is ValueError
    assert str(info.value) == str(info.value.__cause__)
    assert "KILL_SWITCH" in str(info.value)
    assert _tree(rt.book.root) == before
    assert not any(e.event_type == "BOOKING_REFUSED" for e in rt.book.audit.events())


def test_execute_decision_audits_refusal_and_does_not_lapse(market, tmp_path):
    rt, runner, proposal, decision, plan, entry = _native_case(tmp_path, market)
    with pytest.raises(ExecutionRefused) as info:
        runner.execute_decision(WEEK, proposal, decision)
    assert any(type(c) is _BookingPreflightRefused for c in _causes(info.value))
    assert "KILL_SWITCH" in str(info.value)
    events = rt.book.audit.events()
    refusals = [e for e in events if e.event_type == "BOOKING_REFUSED"]
    assert len(refusals) == 1
    _assert_refusal(refusals[0], plan, str(info.value), runner.actor)
    assert not any(e.event_type == LAPSE_EVENT for e in events)
    assert rt.book.efetivacao_recusada(WEEK) is None
    assert rt.book.load_booked(WEEK) is None and runner.track.last() is None
    assert rt.book.audit.verify_chain()[0]


def test_persist_native_refusal_already_audited_is_not_duplicated(market, tmp_path):
    rt, runner, proposal, decision, plan, entry = _native_case(tmp_path, market)

    def persist(value):
        return book_execution(rt.book, value, proposal, decision, rt.cfg, actor=runner.actor)

    with pytest.raises(ExecutionRefused) as info:
        _guarded(persist, entry)
    assert not any(type(c) is _BookingPreflightRefused for c in _causes(info.value))
    assert "KILL_SWITCH" in str(info.value)
    events = [e for e in rt.book.audit.events() if e.event_type == "BOOKING_REFUSED"]
    assert len(events) == 1
    _assert_refusal(events[0], plan, str(info.value), runner.actor)
    before = _tree(rt.book.root)
    runner._audit_preflight_refusal(plan, info.value)
    assert _tree(rt.book.root) == before
    assert rt.book.load_booked(WEEK) is None and runner.track.last() is None
    assert rt.book.audit.verify_chain()[0]


def test_refusal_event_writer_respects_readonly(market, tmp_path):
    rt, runner, proposal, decision, plan, entry = _native_case(tmp_path, market)
    before = _tree(rt.book.root)
    readonly = Book(rt.book.root, config=rt.cfg, somente_leitura=True)
    with pytest.raises(TentativaDeEfeitoLeitura):
        readonly._registrar_booking_recusado(
            plan.week, plan.proposal_id, plan.approval_hash, "DADOS SIMULADOS", runner.actor)
    assert _tree(rt.book.root) == before


def test_legacy_lapse_rule_keeps_its_received_hash_and_bytes(tmp_path, monkeypatch):
    """Corpo simulado criado hoje em formato legado; não é autoridade/PIT histórico."""
    book = Book(tmp_path / "book")
    old_rule = 'A decisão vale só para o leilão de fechamento do seu dia de montagem. Efetivação recusada nesse leilão pelo kill switch é registrada no próprio dia e a decisão caduca: nunca é efetivada depois (sem efetivação retroativa); o fundo segue com a carteira vigente (em caixa, se for a carteira inaugural) e a próxima data de montagem decide de novo.'
    assert old_rule != book_module.REGRA_CADUCIDADE
    with monkeypatch.context() as old_producer:
        old_producer.setattr(book_module, "REGRA_CADUCIDADE", old_rule)
        payload = book.registrar_efetivacao_recusada(
            WEEK, WEEK, "DADOS SIMULADOS: recusa legada", "DADOS-SIMULADOS-LEGADO",
            "d" * 64, actor="DADOS SIMULADOS")
    assert payload["regra"] == old_rule
    before = _tree(book.root)
    received = book.efetivacao_recusada(WEEK)
    assert received == payload and received["regra"] != book_module.REGRA_CADUCIDADE
    event = next(e for e in book.audit.events() if e.event_type == LAPSE_EVENT)
    assert event.payload_hash == sha256_obj(received)
    assert _tree(book.root) == before
