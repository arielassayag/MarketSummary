"""DADOS SIMULADOS: corpus de formato legado criado hoje em tmp, sem autoridade.

O helper cria somente uma fixture sintética de formato legado em tmp. Não prova
recepção histórica nem PIT. Não chama
save_booked, compose, preflight, execute_decision ou callback de persistência.
O kernel prepara os valores; os serializers/eventos nativos preservam os corpos
da fixture, que os leitores históricos recebem sem selo prospectivo NET.
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from cdp.contracts import BookEntry, Proposal
from cdp.workflow.book import dump_json
from cdp.workflow.daily import BOOK_SHADOW_FILE, book_shadow_proposal, save_decided_proposal
from cdp.workflow.net_moc import PROPOSAL_KEY, RECORD_MARKER, descriptor


def _tmp(root):
    path = Path(root).resolve()
    assert path.is_relative_to(Path(tempfile.gettempdir()).resolve()), path


def _legacy(proposal, config):
    assert config is None or config.execution is None, "fixture histórica exige execução legada"
    assert proposal.is_synthetic and "DADOS SIMULADOS" in proposal.data_notice.upper()
    assert PROPOSAL_KEY not in proposal.overrides and descriptor(proposal) is None
    assert RECORD_MARKER not in proposal.overrides


def _body(path, entry):
    """Fecha e relê bytes literais da fixture antes de entregar ao leitor."""
    raw = dump_json(entry).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    actual = path.read_bytes()
    assert actual == raw and BookEntry.model_validate_json(actual) == entry
    return hashlib.sha256(actual).hexdigest()


def instalar_booking_historico(book, entry):
    """Instala corpo/evento legado declarado; não passa pela API de nova efetivação."""
    _tmp(book.root)
    proposal = book._find_proposal(entry.week, entry.proposal_id)
    _legacy(proposal, book.config)
    decision = book.load_decision(entry.week, proposal.version)
    assert decision is not None and entry.approval_hash == decision.approval_hash
    sha = _body(book.week_dir(entry.week) / "booked.json", entry)
    book.audit.append("BOOKED", "fixture sintética em formato legado — DADOS SIMULADOS", entry,
                      summary="DADOS SIMULADOS: corpus de formato legado criado hoje em tmp; sem recepção histórica, PIT ou autoridade NET.",
                      week=entry.week)
    assert book.load_booked(entry.week) == entry
    return sha


def instalar_booking_sombra_historico(store, entry, *, config=None):
    """Sombra histórica explícita; nunca omite o gate da nova escrita."""
    _tmp(store.root)
    proposal = store.load_proposal(entry.week)
    assert proposal is not None and entry.proposal_id == proposal.proposal_id
    _legacy(proposal, config)
    assert entry.approval_hash == proposal.proposal_hash()
    sha = _body(store.booked_path(entry.week), entry)
    store.audit.append("BOOKED_SHADOW", "fixture sintética em formato legado — DADOS SIMULADOS", entry,
                       summary="DADOS SIMULADOS: sombra de formato legado criada hoje em tmp; sem recepção histórica, PIT ou autoridade NET.",
                       week=entry.week)
    assert store.load_booked(entry.week) == entry
    return sha


def instalar_proposta_sombra_historica(store, proposal, *, config=None):
    """Corpo sintético de formato legado; não inventa origem SHADOW_QUANT."""
    _tmp(store.root)
    _legacy(proposal, config)
    raw = dump_json(proposal).encode()
    if store.book is not None:
        origin = book_shadow_proposal(store.book, proposal.week)
        if origin is not None:
            assert dump_json(origin) == dump_json(proposal)
            # O leitor confere SHA/evento; a projeção conserva os bytes da origem.
            raw = (store.book.week_dir(proposal.week) / BOOK_SHADOW_FILE).read_bytes()
            assert dump_json(Proposal.model_validate_json(raw)) == dump_json(proposal)
    path = store.proposal_path(proposal.week)
    if path.exists():
        assert path.read_bytes() == raw
        assert dump_json(store.load_proposal(proposal.week)) == dump_json(proposal)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    actual = path.read_bytes()
    assert actual == raw
    assert dump_json(Proposal.model_validate_json(actual)) == dump_json(proposal)
    store.audit.append("SHADOW_PROPOSAL_SAVED",
                       "fixture sintética em formato legado — DADOS SIMULADOS",
                       proposal.proposal_hash(),
                       summary="DADOS SIMULADOS: proposta de formato legado criada hoje em tmp; sem recepção histórica, PIT ou autoridade NET.",
                       week=proposal.week)
    assert dump_json(store.load_proposal(proposal.week)) == dump_json(proposal)


def historical_session(runner, session, pending):
    """Cria corpus sintético de formato legado hoje em tmp e exerce a adoção.

    Não recebe resultado PASS, preço, NAV, peso ou custo de callback. A fixture
    declara os insumos simulados antes do cálculo e conserva o kernel original.
    Uma execução ativa/selo NET é recusada, mesmo com FakeStore disponível.
    """
    _tmp(runner.book.root)
    _legacy(pending.proposal, runner.cfg)
    assert runner.book.load_booked(pending.proposal.week) is None
    prev = runner.track.last()
    plan = runner._plan_from_pending(session, prev, pending)
    ctx = runner.context(session, prev=prev)
    main = runner._prepare_side(runner.main, ctx, prev, plan)
    assert main.entry is not None and main.commit is None
    assert RECORD_MARKER not in main.record.input_hashes
    shadow = None
    if runner.shadow is not None:
        shadow_prev = runner.shadow.track.last()
        shadow_plan = runner._shadow_plan(runner.shadow, ctx, shadow_prev, pending)
        if shadow_plan is not None:
            assert shadow_plan.proposal is not None
            _legacy(shadow_plan.proposal, runner.cfg)
            shadow = runner._prepare_side(runner.shadow, ctx, shadow_prev, shadow_plan)
            assert shadow.entry is not None and shadow.commit is None
            assert RECORD_MARKER not in shadow.record.input_hashes
    save_decided_proposal(runner.book, pending.proposal, pending.decision, runner.cfg)
    instalar_booking_historico(runner.book, main.entry)
    if shadow is not None:
        instalar_proposta_sombra_historica(runner.shadow.store, shadow_plan.proposal,
                                           config=runner.cfg)
        instalar_booking_sombra_historico(runner.shadow.store, shadow.entry, config=runner.cfg)
    # A produção recebe os corpos já encerrados. Nenhuma closure persist é usada.
    return runner.run_session(session)
