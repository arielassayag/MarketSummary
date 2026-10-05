"""Aprovação vinculada a hashes (sem autoaprovação disfarçada, com quatro olhos).

A decisão fica presa às versões exatas de tudo o que o decisor viu:

``approval_hash = sha256(proposal_hash | snapshot_hash | config_hash | research_hash |
approver | decision | decided_at [| mode:<modo> | pm:<h> | risk_gate:<h>] [| journal:<h>]
[| co_signer:<nome> | co_signed_at:<iso>] [| audit_head:<h>])``

Os componentes entre colchetes (docs/research/07, §6.2–6.4; AGENTS.md, invariantes do CDP)
só entram quando presentes; sem eles o hash é exatamente o de sete componentes da
arquitetura. O bloco ``mode/pm/risk_gate`` segue o mesmo layout de
``workflow.autonomy.autonomous_approval_hash``, para que o livro verifique decisões autônomas. Qualquer alteração posterior em proposta, dados, mandato, pesquisa, diário,
co-assinatura, modo de decisão ou hashes dos gates muda o hash e faz :func:`verify_decision`
falhar, o que bloqueia o booking. O hash não tem segredo: a garantia contra a troca completa
do arquivo de decisão vem da trilha de auditoria (ver ``Book``).

Modos de decisão:

- ``HUMAN``: o aprovador precisa ser humano identificado, diferente do criador da proposta e
  do agente autônomo; quatro olhos obrigatórios nos gatilhos de :func:`co_sign_reasons`.
- ``AUTONOMOUS``: assinada por ``AUTONOMOUS_DECIDER`` sob gates determinísticos; exige os
  hashes da decisão do agente PM e dos gates de risco (vinculados ao ``approval_hash``). Os
  gates substituem a co-assinatura humana; se houver co-assinante, ele precisa ser humano.

Regras de aprovação (``APPROVE``), em qualquer modo:

- falhas HARD de compliance tornam a proposta não aprovável (estado ``BLOCKED``);
- cada falha SOFT precisa constar em ``acknowledged_soft_checks`` (ciência explícita);
- o ``research_hash`` informado precisa ser o mesmo usado na proposta;
- a decisão não pode ser anterior à criação da proposta (sem decisão retroativa).

Rejeições (``REJECT``) são sempre permitidas, desde que justificadas.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import UTC, datetime

from ..contracts import (
    AUTONOMOUS_DECIDER,
    FORBIDDEN_APPROVERS,
    Decision,
    DecisionJournal,
    DecisionMode,
    DecisionType,
    Proposal,
    Side,
    TradeAction,
)
from ..hashing import combine_hashes, sha256_obj

MIN_RATIONALE_CHARS = 10

CO_SIGN_VOL_LOW = 0.04
"""Abaixo desta vol ex-ante (dentro da banda, mas longe do alvo de 5%) exige-se co-assinatura."""
CO_SIGN_VOL_HIGH = 0.06
"""Acima desta vol ex-ante exige-se co-assinatura (docs/research/07, §6.4 d)."""

# Palavras que, em qualquer posição do nome, denunciam um assinante automatizado. Complementa
# o conjunto exato ``FORBIDDEN_APPROVERS`` do contrato (que só compara o nome inteiro). Os nomes
# são comparados sem acentos e com camelCase/dígitos separados ("ClaudeBot", "GPT4o").
AUTOMATED_NAME_TOKENS = frozenset({
    "system", "sistema", "llm", "bot", "robo", "claude", "gpt", "chatgpt", "openai",
    "anthropic", "gemini", "copilot", "openrouter", "pipeline", "demo", "autoaprovacao",
    "agent", "agente", "ai", "ia", "auto", "autonomo", "autonomous", "autopilot",
})
# Prefixos inequívocos de modelos/fornecedores para nomes colados ("claudebot", "gpt4o"):
# só denunciam quando o restante é vazio, outro termo automatizado ou uma versão (dígito).
# "Claudete" e "Talbot" continuam aceitos.
AUTOMATED_NAME_PREFIXES = ("claude", "chatgpt", "gpt", "openai", "anthropic", "gemini",
                           "copilot", "openrouter", "llm")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[A-Za-z])(?=\d)"
                       r"|(?<=\d)(?=[A-Za-z])")
_SPLIT_RE = re.compile(r"[\W_]+")
_BAD_NAME_CHARS_RE = re.compile(r"[|\x00-\x1f\x7f]")


def _decision_value(decision: DecisionType | str) -> str:
    return DecisionType(decision).value


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%".replace(".", ",")


def compute_approval_hash(proposal_hash: str, snapshot_hash: str, config_hash: str,
                          research_hash: str, approver: str, decision: DecisionType | str,
                          decided_at: datetime, *, journal_hash: str | None = None,
                          co_signer: str | None = None, co_signed_at: datetime | None = None,
                          audit_head_hash: str | None = None,
                          mode: DecisionMode | str = DecisionMode.HUMAN,
                          pm_decision_hash: str | None = None,
                          risk_gate_hash: str | None = None) -> str:
    """Hash composto da decisão, na ordem documentada (a ordem dos componentes importa).

    Os componentes opcionais (diário, co-assinatura, topo da trilha, modo não humano e hashes
    da decisão do agente PM e dos gates de risco) são anexados rotulados apenas quando
    informados; uma decisão humana sem eles tem exatamente o hash de sete componentes.
    """
    parts = [proposal_hash, snapshot_hash, config_hash, research_hash, approver,
             _decision_value(decision), decided_at.isoformat()]
    autonomous = DecisionMode(mode) != DecisionMode.HUMAN
    if autonomous:
        parts.append(f"mode:{DecisionMode(mode).value}")
    if autonomous or pm_decision_hash:
        parts.append(f"pm:{pm_decision_hash or ''}")
    if autonomous or risk_gate_hash:
        parts.append(f"risk_gate:{risk_gate_hash or ''}")
    if journal_hash:
        parts.append(f"journal:{journal_hash}")
    if co_signer:
        parts.append(f"co_signer:{co_signer}")
        parts.append(f"co_signed_at:{co_signed_at.isoformat() if co_signed_at else ''}")
    if audit_head_hash:
        parts.append(f"audit_head:{audit_head_hash}")
    return combine_hashes(*parts)


def journal_hash(journal: DecisionJournal | None) -> str | None:
    return sha256_obj(journal) if journal is not None else None


def decision_approval_hash(decision: Decision) -> str:
    """Recalcula o ``approval_hash`` esperado a partir dos campos gravados na decisão."""
    return compute_approval_hash(
        decision.proposal_hash, decision.snapshot_hash, decision.config_hash,
        decision.research_hash, decision.approver, decision.decision, decision.decided_at,
        journal_hash=journal_hash(decision.journal), co_signer=decision.co_signer,
        co_signed_at=decision.co_signed_at, audit_head_hash=decision.audit_head_hash,
        mode=decision.mode, pm_decision_hash=decision.pm_decision_hash,
        risk_gate_hash=decision.risk_gate_hash)


def _fold_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _name_tokens(name: str) -> list[str]:
    """Tokens do nome sem acentos, separando camelCase e letras/dígitos, em minúsculas."""
    spaced = _CAMEL_RE.sub(" ", _fold_accents(name))
    return [t for t in _SPLIT_RE.split(spaced.lower()) if t]


def _automated_hits(name: str) -> list[str]:
    hits: set[str] = set()
    for tok in _name_tokens(name):
        if tok in AUTOMATED_NAME_TOKENS:
            hits.add(tok)
            continue
        for prefix in AUTOMATED_NAME_PREFIXES:
            rest = tok[len(prefix):]
            if tok.startswith(prefix) and (rest in AUTOMATED_NAME_TOKENS or rest[:1].isdigit()):
                hits.add(tok)
    return sorted(hits)


def signer_name_problem(name: str) -> str | None:
    """Caracteres que tornariam o hash composto ambíguo ou o registro ilegível (``|``, controle)."""
    if _BAD_NAME_CHARS_RE.search(name):
        return (f"Nome de assinante '{name.strip()}' contém caractere inválido ('|' ou de "
                "controle).")
    return None


def automated_approver_reason(approver: str, created_by: str | None = None) -> str | None:
    """Motivo (pt-BR) pelo qual ``approver`` não pode assinar como HUMANO, ou ``None``.

    Recusa: caracteres inválidos; nomes vetados pelo contrato; a assinatura do agente
    autônomo (``AUTONOMOUS_DECIDER``) em decisão humana; termos de automação em qualquer
    posição do nome (sem acentos, com camelCase separado); e o criador da proposta.
    """
    name = approver.strip()
    bad = signer_name_problem(approver)
    if bad:
        return bad
    if name.lower() in FORBIDDEN_APPROVERS:
        return f"Assinante '{name}' não é um responsável humano identificado (sem autoaprovação)."
    if _fold_accents(name).lower() == _fold_accents(AUTONOMOUS_DECIDER).lower():
        return ("A assinatura do PM autônomo não vale como decisão humana (sem autoaprovação "
                "disfarçada); use o modo AUTONOMOUS com os hashes dos gates.")
    hits = _automated_hits(name)
    if hits:
        return (f"Assinante '{name}' parece automatizado (termos: {', '.join(hits)}); "
                "a decisão exige um humano identificado.")
    if created_by is not None and name.lower() == created_by.strip().lower():
        return "O criador da proposta não pode assiná-la (sem autoaprovação)."
    return None


def _decider_reason(approver: str, mode: DecisionMode, decision: DecisionType,
                    created_by: str | None, pm_decision_hash: str | None,
                    risk_gate_hash: str | None) -> str | None:
    """Valida o signatário conforme o modo (humano ou agente autônomo sob gates).

    No modo ``AUTONOMOUS`` os gates determinísticos substituem a co-assinatura humana, mas a
    aprovação exige os hashes da decisão do agente PM e dos gates (AGENTS.md, CDP §2).
    """
    if mode == DecisionMode.HUMAN:
        return automated_approver_reason(approver, created_by)
    if approver.strip() != AUTONOMOUS_DECIDER:
        return f"Decisões autônomas são assinadas exclusivamente por '{AUTONOMOUS_DECIDER}'."
    if decision == DecisionType.APPROVE and not (pm_decision_hash and risk_gate_hash):
        return ("Aprovação autônoma exige os hashes da decisão do agente PM e do resultado dos "
                "gates determinísticos de risco.")
    return None


def co_sign_reasons(proposal: Proposal) -> list[str]:
    """Motivos, derivados só da proposta, que exigem co-assinatura independente na aprovação."""
    reasons: list[str] = []
    soft = sorted(c.check_id for c in proposal.soft_failures)
    if soft:
        reasons.append("Falha(s) SOFT reconhecida(s): " + ", ".join(soft) + ".")
    new_shorts = {t.issuer_id for t in proposal.trades if t.action == TradeAction.SHORT}
    risky = sorted(
        f"{p.issuer_id} ({p.squeeze_bucket})" for p in proposal.positions
        if p.side == Side.SHORT and p.squeeze_bucket in ("MEDIUM", "HIGH")
        and (p.issuer_id in new_shorts or not proposal.trades))
    if risky:
        reasons.append("Novo(s) short(s) com risco de squeeze: " + ", ".join(risky) + ".")
    vol = proposal.risk.ex_ante_vol
    if not math.isfinite(vol) or not (CO_SIGN_VOL_LOW <= vol <= CO_SIGN_VOL_HIGH):
        shown = _pct(vol) if math.isfinite(vol) else "indisponível"
        reasons.append(f"Vol ex-ante {shown} fora de [{_pct(CO_SIGN_VOL_LOW)}, "
                       f"{_pct(CO_SIGN_VOL_HIGH)}].")
    return reasons


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


def _to_utc(ts: datetime | None, label: str) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        raise ValueError(f"O horário {label} precisa de fuso horário.")
    return ts.astimezone(UTC)


def _temporal_violations(proposal: Proposal, decided_at: datetime,
                         co_signed_at: datetime | None) -> list[str]:
    """Decisão/co-assinatura anteriores à criação da proposta são retroativas (inválidas)."""
    reasons: list[str] = []
    if decided_at < proposal.created_at:
        reasons.append(f"Decisão datada de {decided_at.isoformat()}, anterior à criação da "
                       f"proposta ({proposal.created_at.isoformat()}).")
    if co_signed_at is not None:
        if co_signed_at.tzinfo is None:
            reasons.append("Co-assinatura sem fuso horário (horário ambíguo).")
        elif co_signed_at < proposal.created_at:
            reasons.append("Co-assinatura anterior à criação da proposta.")
    return reasons


def make_decision(proposal: Proposal, approver: str, decision: DecisionType | str,
                  rationale: str, research_hash: str,
                  acknowledged_soft_checks: list[str] | None = None,
                  conviction: int | None = None, now: datetime | None = None, *,
                  co_signer: str | None = None, co_signed_at: datetime | None = None,
                  journal: DecisionJournal | None = None, audit_head_hash: str | None = None,
                  extra_co_sign_reasons: list[str] | None = None) -> Decision:
    """Cria a decisão HUMANA sobre ``proposal`` com o ``approval_hash`` correspondente.

    Levanta ``ValueError`` (mensagens em pt-BR) quando a decisão viola as regras: assinante
    não humano (automatizado, agente autônomo ou criador da proposta), justificativa curta,
    ciência de checagem inexistente, decisão anterior à proposta, aprovação de proposta
    bloqueada, falha SOFT sem ciência, pesquisa divergente ou co-assinatura obrigatória
    ausente. ``now``/``co_signed_at`` precisam ter fuso horário e são normalizados para UTC
    antes de entrar no hash. ``extra_co_sign_reasons`` permite ao livro exigir quatro olhos
    por motivos externos à proposta (ex.: mudança de mandato). Decisões autônomas são criadas
    por ``workflow.autonomy`` e verificadas aqui por :func:`verify_decision`.
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
    if co_signer is not None:
        co_reason = automated_approver_reason(co_signer, proposal.created_by)
        co_signer = co_signer.strip()
        if co_reason:
            raise ValueError("Co-assinatura inválida: " + co_reason)
        if co_signer.lower() == approver.lower():
            raise ValueError("Co-assinante precisa ser pessoa diferente do aprovador "
                             "(quatro olhos).")

    required: list[str] = []
    if kind == DecisionType.APPROVE:
        violations = _approval_rule_violations(proposal, acks)
        if research_hash != proposal.research_hash:
            violations.append("A pesquisa revisada pelo gestor (research_hash) difere da usada "
                              "na proposta; gere nova versão da proposta.")
        if violations:
            raise ValueError("Aprovação recusada: " + " ".join(violations))
        required = co_sign_reasons(proposal) + [r for r in (extra_co_sign_reasons or []) if r]
        if required and co_signer is None:
            raise ValueError("Co-assinatura independente (Risco/Compliance) obrigatória — "
                             "quatro olhos: " + " ".join(required))

    decided_at = _to_utc(now, "da decisão") or datetime.now(UTC)
    co_at = (_to_utc(co_signed_at, "da co-assinatura") or decided_at) if co_signer else None
    late = _temporal_violations(proposal, decided_at, co_at)
    if late:
        raise ValueError("Decisão retroativa recusada: " + " ".join(late))
    proposal_hash = proposal.proposal_hash()
    approval_hash = compute_approval_hash(
        proposal_hash, proposal.snapshot_hash, proposal.config_hash, research_hash, approver,
        kind, decided_at, journal_hash=journal_hash(journal), co_signer=co_signer,
        co_signed_at=co_at, audit_head_hash=audit_head_hash)
    return Decision(
        week=proposal.week, proposal_id=proposal.proposal_id, proposal_hash=proposal_hash,
        snapshot_hash=proposal.snapshot_hash, config_hash=proposal.config_hash,
        research_hash=research_hash, decision=kind, approver=approver,
        rationale=rationale.strip(), acknowledged_soft_checks=acks, conviction=conviction,
        decided_at=decided_at, approval_hash=approval_hash, co_signer=co_signer,
        co_signed_at=co_at, co_sign_reasons=required, journal=journal,
        audit_head_hash=audit_head_hash,
    )


def verify_decision(decision: Decision, proposal: Proposal, snapshot_hash_now: str,
                    config_hash_now: str, research_hash_now: str) -> tuple[bool, list[str]]:
    """Confere se a decisão continua válida para a proposta e os insumos ATUAIS.

    Recalcula ``proposal.proposal_hash()`` e o ``approval_hash``; compara os hashes de
    snapshot, configuração e pesquisa gravados na decisão com os da proposta e com os
    valores atuais informados; revalida o signatário conforme o modo e a cronologia. Para
    ``APPROVE`` também reaplica as regras HARD/SOFT e de quatro olhos (modo humano), como
    defesa contra arquivos de decisão montados à mão. Retorna ``(ok, motivos_em_pt_BR)``.
    """
    reasons: list[str] = []
    if decision.week != proposal.week:
        reasons.append(f"Semana da decisão ({decision.week}) difere da proposta ({proposal.week}).")
    if decision.proposal_id != proposal.proposal_id:
        reasons.append(f"Decisão refere-se a outra proposta ({decision.proposal_id}).")
    if decision.proposal_hash != proposal.proposal_hash():
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

    reason = _decider_reason(decision.approver, decision.mode, decision.decision,
                             proposal.created_by, decision.pm_decision_hash,
                             decision.risk_gate_hash)
    if reason:
        reasons.append(reason)
    if decision.co_signer:
        co_reason = automated_approver_reason(decision.co_signer, proposal.created_by)
        if co_reason:
            reasons.append("Co-assinatura inválida: " + co_reason)
    reasons.extend(_temporal_violations(proposal, decision.decided_at, decision.co_signed_at))

    if decision.decision == DecisionType.APPROVE:
        if decision.research_hash != proposal.research_hash:
            reasons.append("Aprovação registrada com pesquisa diferente da usada na proposta.")
        reasons.extend(_approval_rule_violations(
            proposal, _normalize_acks(decision.acknowledged_soft_checks)))
        if decision.mode == DecisionMode.HUMAN:
            required = co_sign_reasons(proposal) + list(decision.co_sign_reasons)
            if required and decision.co_signer is None:
                reasons.append("Co-assinatura obrigatória (quatro olhos) ausente.")

    if decision_approval_hash(decision) != decision.approval_hash:
        reasons.append("approval_hash inválido: a decisão foi adulterada.")
    return (not reasons, reasons)
