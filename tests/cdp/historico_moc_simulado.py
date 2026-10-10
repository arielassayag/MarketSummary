"""Corpus MOC criado hoje em formato pre-NET, sem PIT: DADOS SIMULADOS.

Não executa escritor prospectivo nem constitui autoridade de execução. O kernel
nativo fornece o fato histórico hipotético; o leitor recebe seus bytes/evento
retidos para testar vintage/capacidade/P&L. O novo corpus nasce antes da primeira
aprovação persistida; não remove contrato de nenhum fato já aprovado ou gravado.
Novas escritas são testadas no ensaio
físico com contrato NET em test_contrato_custos_integridade.py.
"""
from pathlib import Path
from tempfile import gettempdir

from cdp.workflow.approval import verify_decision
from cdp.workflow.book import _write_exclusive, dump_json
from cdp.workflow.daily import save_decided_proposal
from cdp.workflow.net_moc import RECORD_MARKER, descriptor


def historical_moc_session(runner, session, pending):
    """Inicializa somente corpo pre-NET literal numa pasta tmp e adota pelo leitor."""
    root = Path(runner.book.root).resolve()
    assert root.is_relative_to(Path(gettempdir()).resolve()), 'Fixture histórica exige tmp.'
    assert pending.shadow is None and runner.shadow is None
    assert runner.cfg.execution is not None and pending.proposal.is_synthetic
    assert descriptor(pending.proposal) is None, 'Corpus histórico não retira contrato NET.'
    assert all(RECORD_MARKER not in r.input_hashes for r in runner.track.records())
    prev = runner.track.last()
    save_decided_proposal(runner.book, pending.proposal, pending.decision, runner.cfg)
    ok, reasons = verify_decision(pending.decision, pending.proposal,
                                  pending.proposal.snapshot_hash, pending.proposal.config_hash,
                                  pending.proposal.research_hash)
    assert ok, reasons
    assert runner.book.verify_integrity()[0]
    context = runner.context(session, prev=prev)
    plan = runner._plan_from_pending(session, prev, pending)
    prepared = runner._prepare_side(runner.main, context, prev, plan)
    assert prepared.entry is not None and prepared.record.is_synthetic
    assert prepared.commit is None
    _write_exclusive(runner.book.week_dir(prepared.entry.week) / 'booked.json',
                     dump_json(prepared.entry))
    runner.book.audit.append('BOOKED', 'fixture-historica', prepared.entry,
                             summary='DADOS SIMULADOS: corpus criado hoje, formato pre-NET, sem PIT.',
                             week=prepared.entry.week)
    assert runner.book.verify_integrity()[0]
    return runner.run_session(session)
