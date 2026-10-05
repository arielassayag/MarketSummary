"""Decisão autônoma do CDP — Cabra da Peste sob gates determinísticos.

O CDP decide sozinho (sem aprovação humana), mas a decisão continua:

- assinada por ``contracts.AUTONOMOUS_DECIDER`` em modo ``AUTONOMOUS``;
- vinculada por hash à proposta, ao snapshot, ao mandato, à pesquisa, à decisão estruturada do
  agente PM (``pm_decision_hash``) e ao resultado dos gates de risco (``risk_gate_hash``);
- impossível quando há falha HARD de compliance (o orquestrador cai para alternativas mais
  conservadoras antes de chegar aqui);
- com toda falha SOFT registrada como ciente, com justificativa automática auditável.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..config import FundConfig
from ..contracts import (
    AUTONOMOUS_DECIDER,
    Decision,
    DecisionJournal,
    DecisionMode,
    DecisionType,
    Proposal,
)
from ..hashing import combine_hashes, sha256_obj


def risk_gate_hash(proposal: Proposal) -> str:
    return sha256_obj([c.model_dump(mode="json") for c in proposal.compliance])


def autonomous_approval_hash(proposal_hash: str, snapshot_hash: str, config_hash: str,
                             research_hash: str, decision: DecisionType | str,
                             decided_at: datetime, pm_decision_hash: str, risk_gate: str,
                             journal: DecisionJournal | None,
                             audit_head_hash: str | None) -> str:
    parts = [proposal_hash, snapshot_hash, config_hash, research_hash, AUTONOMOUS_DECIDER,
             DecisionType(decision).value, decided_at.isoformat(), "mode:AUTONOMOUS",
             f"pm:{pm_decision_hash}", f"risk_gate:{risk_gate}"]
    if journal is not None:
        parts.append(f"journal:{sha256_obj(journal)}")
    if audit_head_hash:
        parts.append(f"audit_head:{audit_head_hash}")
    return combine_hashes(*parts)


def make_autonomous_decision(proposal: Proposal, *, research_hash: str, pm_decision_hash: str,
                             rationale: str, journal: DecisionJournal | None = None,
                             conviction: int | None = None, decided_at: datetime | None = None,
                             audit_head_hash: str | None = None) -> Decision:
    """Decisão APPROVE autônoma; recusa propostas com falha HARD (nunca executáveis)."""
    if proposal.hard_failures:
        ids = ", ".join(c.check_id for c in proposal.hard_failures)
        raise ValueError(f"Proposta com falha HARD não pode ser executada: {ids}.")
    if research_hash != proposal.research_hash:
        raise ValueError("Hash da pesquisa difere do usado na proposta.")
    decided_at = (decided_at or datetime.now(UTC)).astimezone(UTC)
    gate = risk_gate_hash(proposal)
    soft = sorted(c.check_id for c in proposal.soft_failures)
    approval = autonomous_approval_hash(
        proposal.proposal_hash(), proposal.snapshot_hash, proposal.config_hash, research_hash,
        DecisionType.APPROVE, decided_at, pm_decision_hash, gate, journal, audit_head_hash)
    reasons = [f"Ciência automática de {cid} (limite SOFT do mandato; registrado no relatório)."
               for cid in soft]
    return Decision(
        week=proposal.week, proposal_id=proposal.proposal_id,
        proposal_hash=proposal.proposal_hash(), snapshot_hash=proposal.snapshot_hash,
        config_hash=proposal.config_hash, research_hash=research_hash,
        decision=DecisionType.APPROVE, approver=AUTONOMOUS_DECIDER,
        rationale=rationale if len(rationale) >= 10 else (rationale + " — decisão autônoma."),
        acknowledged_soft_checks=soft, conviction=conviction, decided_at=decided_at,
        approval_hash=approval, co_sign_reasons=reasons, journal=journal,
        audit_head_hash=audit_head_hash, mode=DecisionMode.AUTONOMOUS,
        pm_decision_hash=pm_decision_hash, risk_gate_hash=gate,
    )


def verify_autonomous_decision(decision: Decision, proposal: Proposal, snapshot_hash_now: str,
                               config_hash_now: str, research_hash_now: str
                               ) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if decision.mode != DecisionMode.AUTONOMOUS:
        return False, ["Decisão não é autônoma."]
    if decision.approver != AUTONOMOUS_DECIDER:
        reasons.append("Assinante inválido para decisão autônoma.")
    if decision.proposal_hash != proposal.proposal_hash():
        reasons.append("Proposta alterada após a decisão.")
    if decision.snapshot_hash != snapshot_hash_now or proposal.snapshot_hash != snapshot_hash_now:
        reasons.append("Dados de mercado diferentes dos usados na decisão.")
    if decision.config_hash != config_hash_now or proposal.config_hash != config_hash_now:
        reasons.append("Mandato (configuração) alterado após a decisão.")
    if decision.research_hash != research_hash_now or proposal.research_hash != research_hash_now:
        reasons.append("Pesquisa alterada após a decisão.")
    gate = risk_gate_hash(proposal)
    if decision.risk_gate_hash != gate:
        reasons.append("Resultado dos gates de risco não confere.")
    if decision.decision == DecisionType.APPROVE and proposal.hard_failures:
        reasons.append("Proposta com falha HARD não pode ter decisão APPROVE.")
    soft = sorted(c.check_id for c in proposal.soft_failures)
    if sorted(decision.acknowledged_soft_checks) != soft:
        reasons.append("Ciência das falhas SOFT não confere com a proposta.")
    expected = autonomous_approval_hash(
        decision.proposal_hash, decision.snapshot_hash, decision.config_hash,
        decision.research_hash, decision.decision, decision.decided_at,
        decision.pm_decision_hash or "", decision.risk_gate_hash or "", decision.journal,
        decision.audit_head_hash)
    if expected != decision.approval_hash:
        reasons.append("approval_hash não confere (decisão adulterada).")
    return (not reasons), reasons


def effective_vol_target(cfg: FundConfig, posture_target: float | None, live_weeks: int) -> float:
    """Meta ex-ante efetiva: alvo da postura dentro da banda, dividido pelo viés a priori.

    Enquanto o track record tiver menos de ``bias_prior_weeks`` semanas, divide pelo viés a priori
    (carteiras otimizadas têm risco subestimado). Nunca sai da banda do mandato.
    """
    rk = cfg.risk
    target = rk.vol_target_annual if posture_target is None else float(posture_target)
    target = min(max(target, rk.vol_band_min), rk.vol_band_max)
    if live_weeks < rk.bias_prior_weeks:
        target = target / rk.bias_prior
    return max(target, rk.vol_band_min)
