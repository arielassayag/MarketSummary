"""DADOS SIMULADOS: identidades independentes mesmo com espaços nos corpos recebidos."""

import json

import pytest
from test_book import NOW, PM, RISK, make_proposal

from cdp.contracts import Decision, DecisionType
from cdp.workflow.approval import (
    co_sign_reasons,
    decision_approval_hash,
    make_decision,
    verify_decision,
)
from cdp.workflow.book import Book

PARES_IGUAIS = [
    (f" {PM} ", PM),
    (PM, f" {PM} "),
    (f" {PM} ", f" {PM} "),
    (f" {PM.lower()} ", PM.upper()),
    (PM.upper(), f" {PM.lower()} "),
    (f"\u00a0{PM}\u00a0", f" {PM} "),
]


def _proposta_quatro_olhos():
    """Proposta sintética com gates aprovados e gatilho nativo de coassinatura."""
    proposal = make_proposal()
    proposal = proposal.model_copy(update={
        "risk": proposal.risk.model_copy(update={"ex_ante_vol": 0.035}),
    })
    assert not proposal.hard_failures and not proposal.soft_failures
    assert co_sign_reasons(proposal)
    return proposal


def _decisao_valida(proposal, *, audit_head_hash=None):
    decision = make_decision(
        proposal, PM, DecisionType.APPROVE,
        "DADOS SIMULADOS — aprovação humana independente para o controle.",
        proposal.research_hash, now=NOW, co_signer=RISK,
        audit_head_hash=audit_head_hash,
    )
    ok, reasons = _verificar(decision, proposal)
    assert ok, reasons
    return decision


def _verificar(decision, proposal):
    return verify_decision(decision, proposal, proposal.snapshot_hash,
                           proposal.config_hash, proposal.research_hash)


def _corpo_manual(decision, approver, co_signer):
    """Simula corpo independente da fábrica e da validação, com hash recalculado válido."""
    forged = decision.model_copy(update={"approver": approver, "co_signer": co_signer})
    forged = forged.model_copy(update={"approval_hash": decision_approval_hash(forged)})
    assert decision_approval_hash(forged) == forged.approval_hash
    return forged


@pytest.mark.parametrize("approver,co_signer", PARES_IGUAIS)
def test_contrato_recusa_mesma_pessoa_normalizando_as_duas_identidades(approver, co_signer):
    proposal = _proposta_quatro_olhos()
    forged = _corpo_manual(_decisao_valida(proposal), approver, co_signer)
    with pytest.raises(ValueError, match="diferente do aprovador"):
        Decision.model_validate_json(forged.model_dump_json())


@pytest.mark.parametrize("approver,co_signer", PARES_IGUAIS)
def test_verificador_recusa_corpo_manual_mesmo_com_hash_valido(approver, co_signer):
    proposal = _proposta_quatro_olhos()
    forged = _corpo_manual(_decisao_valida(proposal), approver, co_signer)
    ok, reasons = _verificar(forged, proposal)
    assert not ok
    assert any("diferente do aprovador" in reason for reason in reasons), reasons
    assert not any("approval_hash" in reason for reason in reasons), reasons


@pytest.mark.parametrize("field", ["approver", "co_signer"])
@pytest.mark.parametrize("empty", ["", "   ", "\u00a0"])
def test_verificador_recusa_identidade_vazia_em_corpo_com_hash_valido(field, empty):
    proposal = _proposta_quatro_olhos()
    values = {"approver": PM, "co_signer": RISK, field: empty}
    forged = _corpo_manual(_decisao_valida(proposal), **values)
    ok, reasons = _verificar(forged, proposal)
    assert not ok
    assert any("humano identificado" in reason for reason in reasons), reasons
    assert not any("approval_hash" in reason for reason in reasons), reasons


@pytest.mark.parametrize("field", ["approver", "co_signer"])
@pytest.mark.parametrize("empty", ["", "   "])
def test_contrato_recusa_identidade_vazia(field, empty):
    proposal = _proposta_quatro_olhos()
    values = {"approver": PM, "co_signer": RISK, field: empty}
    forged = _corpo_manual(_decisao_valida(proposal), **values)
    with pytest.raises(ValueError, match="responsável"):
        Decision.model_validate_json(forged.model_dump_json())


@pytest.mark.parametrize("approver,co_signer", PARES_IGUAIS[:3])
def test_leitor_nativo_recusa_json_gravado_manualmente(tmp_path, approver, co_signer):
    proposal = _proposta_quatro_olhos()
    book = Book(tmp_path / "livro_simulado")
    book.save_proposal(proposal)
    forged = _corpo_manual(_decisao_valida(proposal, audit_head_hash=book.audit_head()),
                          approver, co_signer)
    path = book._decision_path(proposal.week, proposal.version)
    path.write_text(forged.model_dump_json(), encoding="utf-8")
    # O corpo armazenado conserva os hashes/gates da proposta e um approval_hash correto.
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["approval_hash"] == decision_approval_hash(forged)
    assert data["proposal_hash"] == proposal.proposal_hash()
    with pytest.raises(ValueError, match="diferente do aprovador"):
        book.load_decision(proposal.week, version=proposal.version)


@pytest.mark.parametrize("approver,co_signer", [PARES_IGUAIS[0], (PM, "")])
def test_escritor_nativo_recusa_corpo_construido_com_hash_valido(tmp_path, approver, co_signer):
    proposal = _proposta_quatro_olhos()
    book = Book(tmp_path / "livro_simulado")
    book.save_proposal(proposal)
    forged = _corpo_manual(_decisao_valida(proposal, audit_head_hash=book.audit_head()),
                          approver, co_signer)
    with pytest.raises(ValueError, match="diferente do aprovador|humano identificado"):
        book.save_decision(forged)
    assert not book._decision_path(proposal.week, proposal.version).exists()


def test_pessoas_distintas_preservam_aprovador_bruto_e_hash_no_json(tmp_path):
    proposal = _proposta_quatro_olhos()
    approver = f" {PM} "
    decision = _corpo_manual(_decisao_valida(proposal), approver, RISK)
    body = decision.model_dump_json()
    loaded = Decision.model_validate_json(body)
    assert loaded.approver == approver
    assert loaded.approval_hash == decision.approval_hash == decision_approval_hash(loaded)
    assert _verificar(loaded, proposal) == (True, [])
    book = Book(tmp_path / "livro_simulado")
    book.save_proposal(proposal)
    path = book._decision_path(proposal.week, proposal.version)
    path.write_text(body, encoding="utf-8")
    received = book.load_decision(proposal.week, version=proposal.version)
    assert received.approver == approver and received.approval_hash == decision.approval_hash
    assert _verificar(received, proposal) == (True, [])


def test_fabrica_normaliza_espacos_e_conserva_pessoas_distintas():
    proposal = _proposta_quatro_olhos()
    decision = make_decision(
        proposal, f" {PM} ", DecisionType.APPROVE,
        "DADOS SIMULADOS — aprovação por duas pessoas diferentes.",
        proposal.research_hash, now=NOW, co_signer=f" {RISK} ",
    )
    assert decision.approver == PM and decision.co_signer == RISK
    assert _verificar(decision, proposal) == (True, [])


def test_none_permanece_ausencia_valida_quando_coassinatura_nao_e_exigida():
    proposal = make_proposal()
    assert not co_sign_reasons(proposal)
    decision = make_decision(
        proposal, PM, DecisionType.APPROVE,
        "DADOS SIMULADOS — aprovação sem gatilho de coassinatura.",
        proposal.research_hash, now=NOW,
    )
    assert decision.co_signer is None
    assert _verificar(decision, proposal) == (True, [])


def test_equivalencia_lower_existente_nao_e_ampliada_para_casefold():
    proposal = _proposta_quatro_olhos()
    decision = make_decision(
        proposal, "Straße Silva", DecisionType.APPROVE,
        "DADOS SIMULADOS — política de identidade existente preservada.",
        proposal.research_hash, now=NOW, co_signer="STRASSE Silva",
    )
    assert decision.approver.lower() != decision.co_signer.lower()
    loaded = Decision.model_validate_json(decision.model_dump_json())
    assert _verificar(loaded, proposal) == (True, [])
