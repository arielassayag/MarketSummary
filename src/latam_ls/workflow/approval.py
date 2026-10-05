"""Aprovação humana vinculada a hashes (sem autoaprovação).

A decisão do gestor fica presa às versões exatas de tudo o que ele viu:

``approval_hash = sha256(proposal_hash | snapshot_hash | config_hash | research_hash |
approver | decision | decided_at)``

Qualquer alteração posterior em proposta, dados, mandato ou pesquisa muda algum desses
componentes e faz :func:`verify_decision` falhar, o que bloqueia o booking.

Regras de aprovação (``APPROVE``):

- falhas HARD de compliance tornam a proposta não aprovável (estado ``BLOCKED``);
- cada falha SOFT precisa constar em ``acknowledged_soft_checks`` (ciência explícita);
- o ``research_hash`` informado pelo gestor precisa ser o mesmo usado na proposta;
- o aprovador precisa ser humano e diferente do criador da proposta.

Rejeições (``REJECT``) são sempre permitidas, desde que justificadas.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from ..contracts import FORBIDDEN_APPROVERS, Decision, DecisionType, Proposal
from ..hashing import combine_hashes

MIN_RATIONALE_CHARS = 10

# Palavras que, em qualquer posição do nome, denunciam um aprovador automatizado. Complementa
# o conjunto exato ``FORBIDDEN_APPROVERS`` do contrato (que só compara o nome inteiro).
AUTOMATED_NAME_TOKENS = frozenset({
    "system", "sistema", "llm", "bot", "robo", "robô", "claude", "gpt", "chatgpt", "openai",
    "anthropic", "gemini", "copilot", "openrouter", "pipeline", "demo", "autoaprovacao",
    "autoaprovação", "agent", "agente",
})


def _decision_value(decision: DecisionType | str) -> str:
    return DecisionType(decision).value


def compute_approval_hash(proposal_hash: str, snapshot_hash: str, config_hash: str,
                          research_hash: str, approver: str, decision: DecisionType | str,
                          decided_at: datetime) -> str:
    """Hash composto da decisão, na ordem documentada (a ordem dos componentes importa)."""
    return combine_hashes(proposal_hash, snapshot_hash, config_hash, research_hash, approver,
                          _decision_value(decision), decided_at.isoformat())


def automated_approver_reason(approver: str, created_by: str | None = None) -> str | None:
    """Motivo (pt-BR) pelo qual ``approver`` não pode aprovar, ou ``None`` se aceitável."""
    name = approver.strip()
    if name.lower() in FORBIDDEN_APPROVERS:
        return f"Aprovador '{name}' não é um responsável humano identificado (sem autoaprovação)."
    tokens = {t for t in re.split(r"[\W_]+", name.lower()) if t}
    hits = sorted(tokens & AUTOMATED_NAME_TOKENS)
    if hits:
        return (f"Aprovador '{name}' parece automatizado (termos: {', '.join(hits)}); "
                "a aprovação exige um humano identificado.")
    if created_by is not None and name.lower() == created_by.strip().lower():
        return "O criador da proposta não pode aprová-la (sem autoaprovação)."
    return None


def _normalize_acks(acks: list[str] | None) -> list[str]:
    return sorted({a.strip() for a in (acks or []) if a and a.strip()})


def _approval_rule_violations(proposal: Proposal, acknowledged: list[str]) -> list[str]:
    """Violações das regras de aprovação que dependem só da proposta (HARD/SOFT)."""
    reasons: list[str] = []
    hard = proposal.hard_failures
    if hard:
        ids = ", ".join(c.check_id for c in hard)
        reasons.append(f"Proposta BLOQUEADA por falhas HARD de compliance: {ids}.")
    missing = sorted({c.check_id for c in proposal.soft_failures} - set(acknowledged))
    if missing:
        reasons.append("Falhas SOFT sem ciência explícita do gestor: " + ", ".join(missing) + ".")
    return reasons


def make_decision(proposal: Proposal, approver: str, decision: DecisionType | str,
                  rationale: str, research_hash: str,
                  acknowledged_soft_checks: list[str] | None = None,
                  conviction: int | None = None, now: datetime | None = None) -> Decision:
    """Cria a decisão humana sobre ``proposal`` com o ``approval_hash`` correspondente.

    Levanta ``ValueError`` (mensagens em pt-BR) quando a decisão viola as regras: aprovador
    não humano ou igual ao criador, justificativa curta, ciência de checagem inexistente,
    aprovação de proposta bloqueada, falha SOFT sem ciência ou pesquisa divergente.
    ``now`` precisa ter fuso horário; é normalizado para UTC antes de entrar no hash.
    """
    kind = DecisionType(decision)
    approver = approver.strip()
    reason = automated_approver_reason(approver, proposal.created_by)
    if reason:
        raise ValueError(reason)
    if len(rationale.strip()) < MIN_RATIONALE_CHARS:
        raise ValueError(
            f"A justificativa da decisão precisa ter ao menos {MIN_RATIONALE_CHARS} caracteres.")
    acks = _normalize_acks(acknowledged_soft_checks)
    known = {c.check_id for c in proposal.compliance}
    unknown = sorted(set(acks) - known)
    if unknown:
        raise ValueError("Ciência registrada para checagens inexistentes na proposta: "
                         + ", ".join(unknown) + ".")
    if kind == DecisionType.APPROVE:
        violations = _approval_rule_violations(proposal, acks)
        if research_hash != proposal.research_hash:
            violations.append("A pesquisa revisada pelo gestor (research_hash) difere da usada "
                              "na proposta; gere nova versão da proposta.")
        if violations:
            raise ValueError("Aprovação recusada: " + " ".join(violations))

    if now is None:
        decided_at = datetime.now(UTC)
    elif now.tzinfo is None:
        raise ValueError("O horário da decisão precisa de fuso horário.")
    else:
        decided_at = now.astimezone(UTC)

    proposal_hash = proposal.proposal_hash()
    approval_hash = compute_approval_hash(proposal_hash, proposal.snapshot_hash,
                                          proposal.config_hash, research_hash, approver,
                                          kind, decided_at)
    return Decision(
        week=proposal.week, proposal_id=proposal.proposal_id, proposal_hash=proposal_hash,
        snapshot_hash=proposal.snapshot_hash, config_hash=proposal.config_hash,
        research_hash=research_hash, decision=kind, approver=approver,
        rationale=rationale.strip(), acknowledged_soft_checks=acks, conviction=conviction,
        decided_at=decided_at, approval_hash=approval_hash,
    )


def verify_decision(decision: Decision, proposal: Proposal, snapshot_hash_now: str,
                    config_hash_now: str, research_hash_now: str) -> tuple[bool, list[str]]:
    """Confere se a decisão continua válida para a proposta e os insumos ATUAIS.

    Recalcula ``proposal.proposal_hash()`` e o ``approval_hash``; compara os hashes de
    snapshot, configuração e pesquisa gravados na decisão com os da proposta e com os
    valores atuais informados. Para ``APPROVE`` também reaplica as regras HARD/SOFT (defesa
    contra arquivos de decisão montados à mão). Retorna ``(ok, motivos_em_pt_BR)``.
    """
    reasons: list[str] = []
    if decision.week != proposal.week:
        reasons.append(f"Semana da decisão ({decision.week}) difere da proposta ({proposal.week}).")
    if decision.proposal_id != proposal.proposal_id:
        reasons.append(f"Decisão refere-se a outra proposta ({decision.proposal_id}).")
    proposal_hash_now = proposal.proposal_hash()
    if decision.proposal_hash != proposal_hash_now:
        reasons.append("A proposta foi alterada após a decisão (proposal_hash diverge).")

    pairs = [
        ("snapshot", decision.snapshot_hash, proposal.snapshot_hash, snapshot_hash_now),
        ("configuração", decision.config_hash, proposal.config_hash, config_hash_now),
    ]
    for label, in_decision, in_proposal, now_value in pairs:
        if in_decision != in_proposal:
            reasons.append(f"Hash de {label} da decisão difere do registrado na proposta.")
        if in_decision != now_value:
            reasons.append(f"Hash de {label} mudou desde a decisão (dados/mandato alterados).")
    if decision.research_hash != research_hash_now:
        reasons.append("Hash da pesquisa mudou desde a decisão (pesquisa alterada).")

    reason = automated_approver_reason(decision.approver, proposal.created_by)
    if reason:
        reasons.append(reason)

    if decision.decision == DecisionType.APPROVE:
        if decision.research_hash != proposal.research_hash:
            reasons.append("Aprovação registrada com pesquisa diferente da usada na proposta.")
        reasons.extend(_approval_rule_violations(
            proposal, _normalize_acks(decision.acknowledged_soft_checks)))

    expected = compute_approval_hash(decision.proposal_hash, decision.snapshot_hash,
                                     decision.config_hash, decision.research_hash,
                                     decision.approver, decision.decision, decision.decided_at)
    if expected != decision.approval_hash:
        reasons.append("approval_hash inválido: a decisão foi adulterada.")
    return (not reasons, reasons)
