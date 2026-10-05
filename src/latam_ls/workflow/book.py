"""Livro de decisões semanais: armazenamento em arquivos, git-friendly e somente anexação.

Layout (``root`` = ``book/`` por padrão)::

    audit_log.jsonl                         trilha encadeada por hash (AuditLog)
    ledger.csv                              NAV diário (Ledger)
    <semana>/research_pack_<hash12>.json    pacotes de pesquisa imutáveis (por hash)
    <semana>/research_pack.json             ponteiro {hash, file} para o pacote vigente
    <semana>/proposal_v<k>.json             propostas versionadas (imutáveis)
    <semana>/positions_v<k>.csv, trades_v<k>.csv, memo_v<k>.md   derivados da proposta
    <semana>/decision_v<k>.json             decisão humana sobre a versão k (imutável)
    <semana>/booked.json                    carteira efetivada (uma por semana)

Regras:

- Arquivos de proposta, decisão, pesquisa e booking nunca são sobrescritos (criação
  exclusiva e atômica); só o ponteiro de pesquisa e os derivados podem ser regravados.
- O estado de cada proposta é derivado exclusivamente dos arquivos (:meth:`Book.proposal_state`).
- O booking exige decisão ``APPROVE`` válida contra os hashes ATUAIS de snapshot,
  configuração e pesquisa (:func:`verify_decision`).
- Toda gravação relevante gera evento na trilha de auditoria encadeada.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from ..audit import GENESIS_HASH, AuditLog
from ..config import FundConfig
from ..contracts import (
    BookedPosition,
    BookEntry,
    Decision,
    DecisionType,
    LedgerRow,
    PositionTarget,
    Proposal,
    ProposalState,
    ResearchPack,
    Trade,
)
from ..hashing import sha256_obj
from .approval import co_sign_reasons, verify_decision
from .ledger import Ledger
from .memo import fmt_usd_mm, render_memo

HASH_PREFIX = 12
BOOKING_WEIGHT_TOLERANCE = 0.005
"""Desvio máximo |peso efetivado − peso aprovado| por nome (arredondamento de lotes/preços)."""

SYSTEM_ACTOR = "sistema"

_PROPOSAL_RE = re.compile(r"^proposal_v(\d+)\.json$")
_DECISION_RE = re.compile(r"^decision_v(\d+)\.json$")
_RESEARCH_POINTER = "research_pack.json"
_BOOKED = "booked.json"


# ==========================================================
# E/S auxiliar
# ==========================================================

def dump_json(obj: BaseModel | dict) -> str:
    """JSON canônico do livro: indentado, chaves ordenadas, UTF-8, ``model_dump(mode='json')``."""
    data = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _tmp_in(directory: Path, text: str) -> Path:
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=directory)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return Path(tmp)


def _write_exclusive(path: Path, text: str) -> None:
    """Cria ``path`` atomicamente; ``FileExistsError`` se já existir (nunca sobrescreve)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Arquivo imutável já existe: {path}")
    tmp = _tmp_in(path.parent, text)
    try:
        os.link(tmp, path)
    except FileExistsError:
        raise FileExistsError(f"Arquivo imutável já existe: {path}") from None
    except OSError:
        # Sistemas de arquivos sem hard link: criação exclusiva direta.
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    finally:
        tmp.unlink(missing_ok=True)


def _write_replace(path: Path, text: str) -> None:
    """Grava (ou regrava) ``path`` atomicamente — apenas para ponteiros e derivados."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_in(path.parent, text)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _models_csv(models: list[BaseModel], model_cls: type[BaseModel]) -> str:
    cols = list(model_cls.model_fields)
    df = pd.DataFrame([m.model_dump(mode="json") for m in models], columns=cols)
    return df.to_csv(index=False, lineterminator="\n")


def _parse_week(name: str) -> date | None:
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


def _check_week(week: date) -> None:
    if week.weekday() != 0:
        raise ValueError(f"A semana do livro precisa ser uma segunda-feira (recebido {week}).")


def book_entry_from_proposal(proposal: Proposal, decision: Decision,
                             booked_at: datetime | None = None,
                             pricing_note: str = "") -> BookEntry:
    """Monta o ``BookEntry`` com as posições exatamente como aprovadas na proposta."""
    if decision.decision != DecisionType.APPROVE:
        raise ValueError("Somente propostas com decisão APPROVE podem ser efetivadas.")
    if decision.proposal_id != proposal.proposal_id:
        raise ValueError("A decisão informada não pertence a esta proposta.")
    positions = [
        BookedPosition(issuer_id=p.issuer_id, ticker=p.execution_ticker, weight=p.weight,
                       notional_usd=p.notional_usd, shares=p.shares,
                       entry_price_local=p.price_local, currency=p.currency)
        for p in proposal.positions if p.weight != 0
    ]
    return BookEntry(week=proposal.week, proposal_id=proposal.proposal_id,
                     approval_hash=decision.approval_hash,
                     booked_at=booked_at or datetime.now(UTC), nav_usd=proposal.nav_usd,
                     positions=positions, pricing_note=pricing_note)


def _booking_mismatches(entry: BookEntry, proposal: Proposal) -> list[str]:
    """Diferenças entre a carteira efetivada e a aprovada (nomes, linhas, sinais, pesos)."""
    approved = {p.issuer_id: p for p in proposal.positions if p.weight != 0}
    booked: dict[str, BookedPosition] = {}
    reasons: list[str] = []
    for b in entry.positions:
        if b.issuer_id in booked:
            reasons.append(f"Emissor {b.issuer_id} efetivado em duplicidade.")
        booked[b.issuer_id] = b
    extra = sorted(set(booked) - set(approved))
    missing = sorted(set(approved) - set(booked))
    if extra:
        reasons.append(f"Posições não aprovadas: {extra}.")
    if missing:
        reasons.append(f"Posições aprovadas ausentes do booking: {missing}.")
    for iid in sorted(set(booked) & set(approved)):
        b, a = booked[iid], approved[iid]
        if b.ticker != a.execution_ticker:
            reasons.append(f"{iid}: linha {b.ticker} difere da aprovada ({a.execution_ticker}).")
        if (b.weight > 0) != (a.weight > 0):
            reasons.append(f"{iid}: sinal efetivado difere do aprovado.")
        if abs(b.weight - a.weight) > BOOKING_WEIGHT_TOLERANCE:
            reasons.append(f"{iid}: peso efetivado {b.weight:.4f} difere do aprovado "
                           f"{a.weight:.4f} além da tolerância.")
    return reasons


# ==========================================================
# Livro
# ==========================================================

class Book:
    """Armazenamento em arquivos das semanas: pesquisa, propostas, decisões e booking.

    ``config`` (opcional) é usado apenas para rotular o memo (nome do fundo, meta e limites).
    """

    def __init__(self, root: Path | str = "book", config: FundConfig | None = None) -> None:
        self.root = Path(root)
        self.config = config
        self.root.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(self.root / "audit_log.jsonl")
        self.ledger = Ledger(self.root / "ledger.csv")

    # ---------------------------------------------- semanas
    def week_dir(self, week: date) -> Path:
        return self.root / week.isoformat()

    def list_weeks(self) -> list[date]:
        weeks = [_parse_week(p.name) for p in self.root.iterdir() if p.is_dir()]
        return sorted(w for w in weeks if w is not None)

    # ---------------------------------------------- pesquisa
    def _research_file(self, week: date, research_hash: str) -> Path:
        return self.week_dir(week) / f"research_pack_{research_hash[:HASH_PREFIX]}.json"

    def save_research_pack(self, pack: ResearchPack, actor: str | None = None) -> Path:
        """Grava o pacote (imutável por hash) e aponta ``research_pack.json`` para ele."""
        _check_week(pack.week)
        h = pack.research_hash()
        path = self._research_file(pack.week, h)
        created = False
        if path.exists():
            existing = ResearchPack.model_validate(_read_json(path))
            if existing.research_hash() != h:
                raise FileExistsError(f"Colisão de prefixo de hash em {path.name}; arquivo "
                                      "existente tem conteúdo diferente.")
        else:
            _write_exclusive(path, dump_json(pack))
            created = True
        pointer = self.week_dir(pack.week) / _RESEARCH_POINTER
        previous = _read_json(pointer).get("hash") if pointer.exists() else None
        if previous != h:
            _write_replace(pointer, dump_json({"file": path.name, "hash": h,
                                               "week": pack.week.isoformat()}))
        if created or previous != h:
            self.audit.append(
                "RESEARCH_SAVED" if created else "RESEARCH_SELECTED", actor or pack.provider, h,
                summary=f"Pesquisa {h[:HASH_PREFIX]} ({pack.provider}): {len(pack.notes)} notas, "
                        f"{len(pack.macro)} macro, {len(pack.views)} visões.",
                week=pack.week)
        return path

    def load_research_pack_by_hash(self, week: date, research_hash: str) -> ResearchPack | None:
        path = self._research_file(week, research_hash)
        if not path.exists():
            return None
        pack = ResearchPack.model_validate(_read_json(path))
        if pack.research_hash() != research_hash:
            raise ValueError(f"Pacote de pesquisa {path.name} não corresponde ao hash esperado "
                             "(arquivo alterado).")
        return pack

    def load_research_pack(self, week: date) -> ResearchPack | None:
        """Pacote vigente da semana (via ponteiro), com verificação de integridade."""
        pointer = self.week_dir(week) / _RESEARCH_POINTER
        if not pointer.exists():
            return None
        h = _read_json(pointer)["hash"]
        pack = self.load_research_pack_by_hash(week, h)
        if pack is None:
            raise FileNotFoundError(f"Ponteiro de pesquisa aponta para arquivo ausente ({h}).")
        return pack

    # ---------------------------------------------- propostas
    def _versions(self, week: date, pattern: re.Pattern[str]) -> list[int]:
        d = self.week_dir(week)
        if not d.exists():
            return []
        return sorted(int(m.group(1)) for p in d.iterdir() if (m := pattern.match(p.name)))

    def proposal_versions(self, week: date) -> list[int]:
        return self._versions(week, _PROPOSAL_RE)

    def next_version(self, week: date) -> int:
        versions = self.proposal_versions(week)
        return (versions[-1] + 1) if versions else 1

    def _proposal_path(self, week: date, version: int) -> Path:
        return self.week_dir(week) / f"proposal_v{version}.json"

    def save_proposal(self, proposal: Proposal) -> Path:
        """Grava a proposta versionada (imutável) e seus derivados; audita ``PROPOSAL_CREATED``."""
        week, k = proposal.week, proposal.version
        _check_week(week)
        path = self._proposal_path(week, k)
        if path.exists():
            raise FileExistsError(f"Proposta v{k} da semana {week} já existe (imutável).")
        if self.load_booked(week) is not None:
            raise ValueError(f"A semana {week} já foi efetivada; não aceita novas propostas.")
        expected = self.next_version(week)
        if k != expected:
            raise ValueError(f"Versão {k} fora de sequência; a próxima versão é {expected}.")
        if any(p.proposal_id == proposal.proposal_id for p in self.list_proposals(week)):
            raise ValueError(f"proposal_id {proposal.proposal_id} já usado nesta semana.")
        text = dump_json(proposal)
        h = proposal.proposal_hash()
        if Proposal.model_validate(json.loads(text)).proposal_hash() != h:
            raise ValueError("A proposta não é serializável de forma estável (hash muda ao "
                             "regravar); verifique valores não finitos.")
        _write_exclusive(path, text)

        d = self.week_dir(week)
        _write_replace(d / f"positions_v{k}.csv",
                       _models_csv(list(proposal.positions), PositionTarget))
        _write_replace(d / f"trades_v{k}.csv", _models_csv(list(proposal.trades), Trade))
        state = ProposalState.BLOCKED if proposal.hard_failures else ProposalState.IN_REVIEW
        memo = proposal.memo_markdown or render_memo(
            proposal, self.load_research_pack_by_hash(week, proposal.research_hash),
            config=self.config, state=state, audit_head_hash=self.audit_head())
        footer = f"\n---\n\n_Hash da proposta (SHA-256): `{h}`_\n"
        _write_replace(d / f"memo_v{k}.md", memo.rstrip() + "\n" + footer)

        self.audit.append(
            "PROPOSAL_CREATED", proposal.created_by, h,
            summary=f"Proposta {proposal.proposal_id} v{k}: {len(proposal.positions)} posições, "
                    f"{len(proposal.hard_failures)} falha(s) HARD, "
                    f"{len(proposal.soft_failures)} SOFT ({state.value}).",
            week=week)
        return path

    def load_proposal(self, week: date, version: int | None = None) -> Proposal | None:
        """Proposta da versão pedida (ou a mais recente); ``None`` se não existir."""
        if version is None:
            versions = self.proposal_versions(week)
            if not versions:
                return None
            version = versions[-1]
        path = self._proposal_path(week, version)
        if not path.exists():
            return None
        proposal = Proposal.model_validate(_read_json(path))
        if proposal.version != version or proposal.week != week:
            raise ValueError(f"{path.name} inconsistente com o local (versão/semana divergentes).")
        return proposal

    def list_proposals(self, week: date) -> list[Proposal]:
        out = []
        for v in self.proposal_versions(week):
            p = self.load_proposal(week, v)
            if p is not None:
                out.append(p)
        return out

    def _find_proposal(self, week: date, proposal_id: str) -> Proposal:
        for p in self.list_proposals(week):
            if p.proposal_id == proposal_id:
                return p
        raise ValueError(f"Proposta {proposal_id} não encontrada na semana {week}.")

    # ---------------------------------------------- decisões
    def _decision_path(self, week: date, version: int) -> Path:
        return self.week_dir(week) / f"decision_v{version}.json"

    def audit_head(self) -> str:
        """Hash do último evento da trilha (topo), para ancorar decisões e memos."""
        events = self.audit.events()
        return events[-1].event_hash if events else GENESIS_HASH

    def last_approval_before(self, proposal: Proposal) -> Decision | None:
        """Última decisão APPROVE do livro (até a semana da proposta), exceto a própria."""
        found: list[Decision] = []
        for week in self.list_weeks():
            if week > proposal.week:
                continue
            found += [d for d in self.list_decisions(week).values()
                      if d.decision == DecisionType.APPROVE
                      and d.proposal_id != proposal.proposal_id]
        return max(found, key=lambda d: d.decided_at) if found else None

    def co_sign_reasons(self, proposal: Proposal) -> list[str]:
        """Motivos de quatro olhos: os da proposta mais mudança de mandato desde a última
        aprovação (passe-os em ``make_decision(..., extra_co_sign_reasons=...)``)."""
        reasons = co_sign_reasons(proposal)
        last = self.last_approval_before(proposal)
        if last is not None and last.config_hash != proposal.config_hash:
            reasons.append("Configuração do mandato mudou desde a última aprovação "
                           f"({last.week}).")
        return reasons

    def save_decision(self, decision: Decision) -> Path:
        """Grava a decisão humana da versão correspondente (uma por versão, imutável)."""
        week = decision.week
        proposal = self._find_proposal(week, decision.proposal_id)
        k = proposal.version
        path = self._decision_path(week, k)
        if path.exists():
            raise FileExistsError(f"A proposta v{k} da semana {week} já tem decisão (imutável).")
        if self.load_booked(week) is not None:
            raise ValueError(f"A semana {week} já foi efetivada.")
        latest = self.proposal_versions(week)[-1]
        if k != latest:
            raise ValueError(f"A proposta v{k} foi substituída pela v{latest}; decida sobre a "
                             "versão mais recente.")
        research_now = (proposal.research_hash if decision.decision == DecisionType.APPROVE
                        else decision.research_hash)
        ok, reasons = verify_decision(decision, proposal, proposal.snapshot_hash,
                                      proposal.config_hash, research_now)
        if not ok:
            raise ValueError("Decisão inconsistente com a proposta: " + " ".join(reasons))
        if decision.audit_head_hash is not None:
            known = {GENESIS_HASH} | {e.event_hash for e in self.audit.events()}
            if decision.audit_head_hash not in known:
                raise ValueError("audit_head_hash da decisão não existe na trilha de auditoria.")
        if (decision.decision == DecisionType.APPROVE and decision.co_signer is None
                and self.co_sign_reasons(proposal)):
            raise ValueError("Co-assinatura independente obrigatória (quatro olhos): "
                             + " ".join(self.co_sign_reasons(proposal)))
        _write_exclusive(path, dump_json(decision))
        self.audit.append(
            f"DECISION_{decision.decision.value}", decision.approver, decision.approval_hash,
            summary=f"{decision.decision.value} da proposta {decision.proposal_id} v{k} por "
                    f"{decision.approver}"
                    + (f", co-assinada por {decision.co_signer}" if decision.co_signer else "")
                    + f" (aprovação {decision.approval_hash[:HASH_PREFIX]}).",
            week=week)
        return path

    def _load_decision_file(self, week: date, version: int) -> Decision | None:
        path = self._decision_path(week, version)
        if not path.exists():
            return None
        return Decision.model_validate(_read_json(path))

    def load_decision(self, week: date, version: int | None = None) -> Decision | None:
        """Decisão da versão pedida (padrão: a versão mais recente da proposta)."""
        if version is None:
            versions = self.proposal_versions(week)
            if not versions:
                return None
            version = versions[-1]
        return self._load_decision_file(week, version)

    def list_decisions(self, week: date) -> dict[int, Decision]:
        out: dict[int, Decision] = {}
        for v in self._versions(week, _DECISION_RE):
            dec = self._load_decision_file(week, v)
            if dec is not None:
                out[v] = dec
        return out

    # ---------------------------------------------- booking
    def save_booked(self, entry: BookEntry, snapshot_hash_now: str, config_hash_now: str,
                    research_hash_now: str, actor: str = SYSTEM_ACTOR) -> Path:
        """Efetiva a carteira da semana; exige aprovação válida contra os hashes atuais."""
        week = entry.week
        path = self.week_dir(week) / _BOOKED
        if path.exists():
            raise FileExistsError(f"A semana {week} já foi efetivada (imutável).")
        proposal = self._find_proposal(week, entry.proposal_id)
        k = proposal.version
        decision = self._load_decision_file(week, k)
        if decision is None or decision.decision != DecisionType.APPROVE:
            raise ValueError(f"A proposta v{k} não tem decisão APPROVE; booking recusado.")
        if entry.approval_hash != decision.approval_hash:
            raise ValueError("approval_hash do booking difere do registrado na decisão.")
        ok, reasons = verify_decision(decision, proposal, snapshot_hash_now, config_hash_now,
                                      research_hash_now)
        if not ok:
            raise ValueError("Aprovação inválida para booking: " + " ".join(reasons))
        decisions = self.list_decisions(week)
        pending = [v for v in self.proposal_versions(week) if v > k
                   and (v not in decisions or decisions[v].decision != DecisionType.REJECT)]
        if pending:
            raise ValueError(f"Há versões mais recentes não rejeitadas ({pending}); efetive a "
                             "versão vigente.")
        mismatches = _booking_mismatches(entry, proposal)
        if mismatches:
            raise ValueError("Carteira efetivada difere da aprovada: " + " ".join(mismatches))
        _write_exclusive(path, dump_json(entry))
        self.audit.append(
            "BOOKED", actor, sha256_obj(entry),
            summary=f"Carteira efetivada: {entry.proposal_id} v{k}, {len(entry.positions)} "
                    f"posições, aprovação {entry.approval_hash[:HASH_PREFIX]}.",
            week=week)
        return path

    def load_booked(self, week: date) -> BookEntry | None:
        path = self.week_dir(week) / _BOOKED
        if not path.exists():
            return None
        return BookEntry.model_validate(_read_json(path))

    def latest_booked(self) -> BookEntry | None:
        for week in reversed(self.list_weeks()):
            entry = self.load_booked(week)
            if entry is not None:
                return entry
        return None

    # ---------------------------------------------- ledger
    def record_ledger(self, rows: list[LedgerRow], actor: str = SYSTEM_ACTOR,
                      week: date | None = None) -> int:
        """Anexa linhas de MTM ao ledger e registra o evento ``LEDGER_APPENDED``."""
        n = self.ledger.append(rows)
        if n:
            self.audit.append(
                "LEDGER_APPENDED", actor, [r.model_dump(mode="json") for r in rows],
                summary=f"{n} dia(s) de marcação a mercado ({rows[0].date} a {rows[-1].date}); "
                        f"NAV final {fmt_usd_mm(rows[-1].nav_usd)}.",
                week=week)
        return n

    # ---------------------------------------------- estado e integridade
    def _decision_is_intact(self, decision: Decision, proposal: Proposal) -> bool:
        """Consistência interna da decisão com a proposta gravada (sem hashes externos)."""
        ok, _ = verify_decision(decision, proposal, proposal.snapshot_hash, proposal.config_hash,
                                decision.research_hash)
        return ok

    def proposal_state(self, week: date, version: int) -> ProposalState:
        """Estado derivado só dos arquivos.

        Precedência: ``BOOKED`` > decisão íntegra (``APPROVED``/``REJECTED``) >
        ``SUPERSEDED`` (há versão mais nova e esta não tem decisão) > ``BLOCKED`` (falha
        HARD) > ``IN_REVIEW``. Uma decisão cuja integridade falhe (proposta ou decisão
        alterada) é ignorada: a aprovação fica invalidada.
        """
        proposal = self.load_proposal(week, version)
        if proposal is None:
            raise FileNotFoundError(f"Proposta v{version} da semana {week} não existe.")
        booked = self.load_booked(week)
        if booked is not None and booked.proposal_id == proposal.proposal_id:
            return ProposalState.BOOKED
        decision = self._load_decision_file(week, version)
        if decision is not None and self._decision_is_intact(decision, proposal):
            return (ProposalState.APPROVED if decision.decision == DecisionType.APPROVE
                    else ProposalState.REJECTED)
        if version < self.proposal_versions(week)[-1]:
            return ProposalState.SUPERSEDED
        if proposal.hard_failures:
            return ProposalState.BLOCKED
        return ProposalState.IN_REVIEW

    def week_states(self, week: date) -> dict[int, ProposalState]:
        return {v: self.proposal_state(week, v) for v in self.proposal_versions(week)}

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Confere a cadeia de auditoria e se cada artefato gravado corresponde ao auditado."""
        problems: list[str] = []
        ok_chain, msg = self.audit.verify_chain()
        if not ok_chain:
            problems.append(msg)
        events = self.audit.events()
        by_type: dict[tuple[str, date | None], set[str]] = {}
        for ev in events:
            by_type.setdefault((ev.event_type, ev.week), set()).add(ev.payload_hash)
        for week in self.list_weeks():
            created = by_type.get(("PROPOSAL_CREATED", week), set())
            for v in self.proposal_versions(week):
                try:
                    p = self.load_proposal(week, v)
                except ValueError as exc:
                    problems.append(f"{week} v{v}: proposta ilegível ({exc}).")
                    continue
                if p is not None and sha256_obj(p.proposal_hash()) not in created:
                    problems.append(f"{week} v{v}: proposta não confere com a trilha de auditoria.")
            for v, dec in self.list_decisions(week).items():
                audited = by_type.get((f"DECISION_{dec.decision.value}", week), set())
                if sha256_obj(dec.approval_hash) not in audited:
                    problems.append(f"{week} v{v}: decisão não confere com a trilha de auditoria.")
                p = self.load_proposal(week, v)
                if p is not None and not self._decision_is_intact(dec, p):
                    problems.append(f"{week} v{v}: decisão inválida para a proposta gravada.")
            entry = self.load_booked(week)
            booked_events = by_type.get(("BOOKED", week), set())
            if entry is not None and sha256_obj(sha256_obj(entry)) not in booked_events:
                problems.append(f"{week}: booking não confere com a trilha de auditoria.")
        return (not problems, problems)
