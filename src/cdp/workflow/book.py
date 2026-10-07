"""Livro de decisões semanais: armazenamento em arquivos, git-friendly e somente anexação.

Layout (``root`` = ``book/`` por padrão)::

    audit_log.jsonl                         trilha encadeada por hash (AuditLog)
    genese.json                             gênese do livro (evento FUND_GENESIS; cdp reinicio)
    ledger.csv                              NAV diário (Ledger)
    KILL_SWITCH                             presente ⇒ só bookings que reduzem risco
    <semana>/research_pack_<hash12>.json    pacotes de pesquisa imutáveis (por hash)
    <semana>/research_pack.json             ponteiro {hash, file} para o pacote vigente
    <semana>/proposal_v<k>.json             propostas versionadas (imutáveis)
    <semana>/positions_v<k>.csv, trades_v<k>.csv, memo_v<k>.md   derivados da proposta
    <semana>/decision_v<k>.json             decisão sobre a versão k (imutável)
    <semana>/booked.json                    carteira efetivada (uma por semana)
    <semana>/efetivacao_recusada.json       efetivação recusada no leilão do dia de montagem:
                                            a decisão caducou (``BOOKING_LAPSED``)

Regras:

- Arquivos de proposta, decisão, pesquisa e booking nunca são sobrescritos (criação
  exclusiva e atômica); só o ponteiro de pesquisa e os derivados podem ser regravados.
- Toda gravação relevante gera evento na trilha de auditoria encadeada. Convenção de payload:
  ``PROPOSAL_CREATED`` → ``proposal_hash``; ``RESEARCH_*`` → ``research_hash``;
  ``DECISION_*`` → a decisão completa; ``BOOKED`` → o ``BookEntry`` completo;
  ``LEDGER_APPENDED`` → as linhas anexadas; ``BOOKING_REFUSED`` → motivo da recusa;
  ``BOOKING_LAPSED`` → a decisão caducou (efetivação recusada no leilão do dia de montagem; nunca
  efetivada depois — ``REGRA_CADUCIDADE``).
- Como o ``approval_hash`` não tem segredo, qualquer um pode recalculá-lo: a defesa contra a
  troca ou edição de arquivos é o cruzamento de cada artefato com a trilha de auditoria
  (:meth:`Book.verify_integrity`). Divergência ⇒ estado ``BLOCKED`` e booking recusado
  (docs/research/07, §6.2).
- O estado de cada proposta é derivado exclusivamente dos arquivos (:meth:`Book.proposal_state`).
- O booking exige decisão ``APPROVE`` válida contra os hashes ATUAIS de snapshot,
  configuração e pesquisa (:func:`verify_decision`), carteira idêntica à aprovada (pesos,
  nocionais e NAV) e, com ``KILL_SWITCH`` ativo, apenas redução de risco (AGENTS.md, CDP §4).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import BaseModel

from .. import SIMULATED_DATA_NOTICE
from ..audit import GENESIS_HASH, AuditLog
from ..config import FundConfig
from ..contracts import (
    AuditEvent,
    BookedPosition,
    BookEntry,
    Decision,
    DecisionMode,
    DecisionType,
    LedgerRow,
    PositionTarget,
    Proposal,
    ProposalState,
    ResearchPack,
    Trade,
)
from ..hashing import canonical_json, sha256_obj
from .approval import co_sign_reasons, verify_decision
from .ledger import Ledger
from .memo import fmt_pct, fmt_usd_mm, render_memo

HASH_PREFIX = 12
BOOKING_WEIGHT_TOLERANCE = 0.005
"""Desvio máximo |peso efetivado − peso aprovado| por nome (arredondamento de lotes/preços);
também é a tolerância, em fração do NAV, entre o nocional e ``|peso| × NAV`` do booking."""
BOOKING_NAV_TOLERANCE = 0.05
"""Desvio relativo máximo entre o NAV do booking e o NAV de referência da proposta (5% em um
fim de semana é um evento de muitos desvios para um fundo de vol 5%: indica erro de unidade)."""
KILL_SWITCH_FILE = "KILL_SWITCH"
_REDUCTION_EPS = 1e-9

SYSTEM_ACTOR = "sistema"

_PROPOSAL_RE = re.compile(r"^proposal_v(\d+)\.json$")
_DECISION_RE = re.compile(r"^decision_v(\d+)\.json$")
_RESEARCH_POINTER = "research_pack.json"
_BOOKED = "booked.json"
_CADUCADA = "efetivacao_recusada.json"
LAPSE_EVENT = "BOOKING_LAPSED"
"""Evento da trilha: a efetivação foi recusada no leilão do dia de montagem e a decisão caducou."""
REGRA_CADUCIDADE = (
    "A decisão vale só para o leilão de fechamento do seu dia de montagem. Efetivação recusada "
    "nesse leilão pelo kill switch é registrada no próprio dia e a decisão caduca: nunca é "
    "efetivada depois (sem efetivação retroativa); o fundo segue com a carteira vigente (em "
    "caixa, se for a carteira inaugural) e a próxima data de montagem decide de novo.")
_RESEARCH_EVENTS = ("RESEARCH_SAVED", "RESEARCH_SELECTED")
_DECISION_EVENTS = ("DECISION_APPROVE", "DECISION_REJECT")
_ARTIFACT_EVENTS = ("PROPOSAL_CREATED", "BOOKED", *_DECISION_EVENTS, *_RESEARCH_EVENTS)

_Index = dict[tuple[str, date | None], set[str]]

GENESIS_EVENT = "FUND_GENESIS"
"""Primeiro evento da trilha de um livro aberto na data de início do mandato (``cdp reinicio``);
o payload completo fica em :data:`GENESIS_FILE` (conferido contra o ``payload_hash``):
``inception_date``, ``config_hash``, ``codigo`` (commit do código) e ``ancora_sha256`` (sha256 de
``book/audit_log.jsonl`` nesse commit). Com a gênese, o livro não aceita semana anterior à data
de início do mandato."""
GENESIS_FILE = "genese.json"


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


def _models_csv(models: list[BaseModel], model_cls: type[BaseModel], notice: str) -> str:
    """CSV dos modelos com a coluna ``data_notice`` (aviso de dados, ex.: DADOS SIMULADOS)."""
    cols = list(model_cls.model_fields)
    df = pd.DataFrame([m.model_dump(mode="json") for m in models], columns=cols)
    df["data_notice"] = notice
    return df.to_csv(index=False, lineterminator="\n")


def _parse_week(name: str) -> date | None:
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


def _check_week(week: date, config: FundConfig | None = None) -> None:
    """Chave do livro: o dia de montagem da regra semanal (com ``config`` em
    ``LAST_US_SESSION``, o último pregão da semana na NYSE; sem ela, o primeiro pregão da semana
    na B3) ou, com ``config``, a data de início do mandato (sempre dia de montagem)."""
    from ..calendar import chave_valida, regra

    if not chave_valida(week, config):
        rule = ("o último pregão da semana na NYSE" if regra(config) == "LAST_US_SESSION"
                else "o primeiro pregão da semana na B3 (segunda ou o próximo dia útil)")
        raise ValueError(f"A semana do livro precisa ser {rule} ou a data de início do "
                         f"mandato; recebido {week}.")


def _index_events(events: list[AuditEvent]) -> _Index:
    out: _Index = {}
    for ev in events:
        out.setdefault((ev.event_type, ev.week), set()).add(ev.payload_hash)
    return out


def _proposal_payload_hash(proposal: Proposal) -> str:
    return sha256_obj(proposal.proposal_hash())


def _data_notice(proposal: Proposal) -> str:
    notice = proposal.data_notice or ""
    if proposal.is_synthetic and SIMULATED_DATA_NOTICE not in notice.upper():
        notice = f"{SIMULATED_DATA_NOTICE} — {notice}".rstrip(" —")
    return notice


def book_entry_from_proposal(proposal: Proposal, decision: Decision,
                             booked_at: datetime | None = None,
                             pricing_note: str = "") -> BookEntry:
    """Monta o ``BookEntry`` com as posições exatamente como aprovadas na proposta."""
    if decision.decision != DecisionType.APPROVE:
        raise ValueError("Somente propostas com decisão APPROVE podem ser efetivadas.")
    if decision.proposal_id != proposal.proposal_id:
        raise ValueError("A decisão informada não pertence a esta proposta.")
    if decision.proposal_hash != proposal.proposal_hash():
        raise ValueError("Decisão inválida para esta proposta: proposal_hash diverge (proposta "
                         "alterada após a decisão).")
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
    """Diferenças entre a carteira efetivada e a aprovada (nomes, linhas, sinais, pesos,
    nocionais e NAV). O MTM usa os nocionais: peso certo com nocional errado (unidade, moeda
    local) distorceria o P&L sem ser percebido."""
    approved = {p.issuer_id: p for p in proposal.positions if p.weight != 0}
    booked: dict[str, BookedPosition] = {}
    reasons: list[str] = []
    nav = entry.nav_usd
    nav_ok = math.isfinite(nav) and nav > 0
    if not nav_ok:
        reasons.append("NAV do booking inválido (não positivo ou não finito).")
    elif abs(nav / proposal.nav_usd - 1.0) > BOOKING_NAV_TOLERANCE:
        reasons.append(f"NAV do booking ({fmt_usd_mm(nav)}) difere do NAV de referência da "
                       f"proposta ({fmt_usd_mm(proposal.nav_usd)}) além de "
                       f"{fmt_pct(BOOKING_NAV_TOLERANCE, 0)}; conferir unidade.")
    for b in entry.positions:
        if b.issuer_id in booked:
            reasons.append(f"Emissor {b.issuer_id} efetivado em duplicidade.")
        booked[b.issuer_id] = b
        if nav_ok:
            expected = abs(b.weight) * nav
            if (not math.isfinite(b.notional_usd)
                    or abs(abs(b.notional_usd) - expected) > BOOKING_WEIGHT_TOLERANCE * nav):
                reasons.append(f"{b.issuer_id}: nocional {fmt_usd_mm(b.notional_usd)} "
                               f"incompatível com |peso| × NAV ({fmt_usd_mm(expected)}).")
            elif b.notional_usd < 0 < b.weight:
                reasons.append(f"{b.issuer_id}: nocional negativo em posição comprada.")
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


def _booking_mismatches_fechamento(entry: BookEntry, proposal: Proposal,
                                   held: dict[tuple[str, str], int]) -> list[str]:
    """Carteira efetivada com execução limitada pela capacidade do leilão (seção ``execution``).

    Por linha ``(emissor, ticker)``: as ações efetivadas ficam ENTRE as ações detidas antes do
    fechamento e as ações da ordem aprovada (``PositionTarget.shares``; linha fora da proposta ⇒
    zero) — execução parcial, saldo de saída parcial e emissor congelado são válidos; qualquer
    ação fora desse intervalo (linha não aprovada, sinal invertido, excesso sobre a ordem) não
    é. NAV e nocional × peso conferidos como no booking integral."""
    reasons: list[str] = []
    nav = entry.nav_usd
    nav_ok = math.isfinite(nav) and nav > 0
    if not nav_ok:
        reasons.append("NAV do booking inválido (não positivo ou não finito).")
    elif abs(nav / proposal.nav_usd - 1.0) > BOOKING_NAV_TOLERANCE:
        reasons.append(f"NAV do booking ({fmt_usd_mm(nav)}) difere do NAV de referência da "
                       f"proposta ({fmt_usd_mm(proposal.nav_usd)}) além de "
                       f"{fmt_pct(BOOKING_NAV_TOLERANCE, 0)}; conferir unidade.")
    booked: dict[tuple[str, str], BookedPosition] = {}
    for b in entry.positions:
        key = (b.issuer_id, b.ticker)
        if key in booked:
            reasons.append(f"Linha {b.issuer_id}/{b.ticker} efetivada em duplicidade.")
        booked[key] = b
        if b.shares is None:
            reasons.append(f"{b.issuer_id}/{b.ticker}: efetivação sem quantidade de ações.")
        if nav_ok:
            expected = abs(b.weight) * nav
            if (not math.isfinite(b.notional_usd)
                    or abs(abs(b.notional_usd) - expected) > BOOKING_WEIGHT_TOLERANCE * nav):
                reasons.append(f"{b.issuer_id}: nocional {fmt_usd_mm(b.notional_usd)} "
                               f"incompatível com |peso| × NAV ({fmt_usd_mm(expected)}).")
    approved = {(p.issuer_id, p.execution_ticker): p for p in proposal.positions
                if p.weight != 0}
    for key in sorted(set(booked) | set(approved) | set(held)):
        b = booked.get(key)
        sb = int(b.shares) if b is not None and b.shares is not None else 0
        s0 = int(held.get(key, 0))
        a = approved.get(key)
        tol = 0
        if a is None:
            st: int | None = 0
        elif a.shares is not None:
            st = int(a.shares)
        elif b is not None and b.shares:
            unit = abs(b.notional_usd) / abs(b.shares)
            st = int(round(a.weight * nav / unit)) if unit > 0 and nav_ok else None
            tol = max(1, int(abs(st or 0) * 0.01))
        else:
            st = None
        if st is None:
            continue
        lo, hi = min(s0, st) - tol, max(s0, st) + tol
        if not lo <= sb <= hi:
            what = "linha não aprovada" if a is None and s0 == 0 else "ações efetivadas"
            reasons.append(f"{key[0]}/{key[1]}: {what} ({sb}) fora do intervalo entre a posição "
                           f"anterior ({s0}) e a ordem aprovada ({st}).")
    return reasons


# ==========================================================
# Livro
# ==========================================================

class Book:
    """Armazenamento em arquivos das semanas: pesquisa, propostas, decisões e booking.

    ``config`` (opcional) rotula o memo (nome do fundo, meta e limites) e, com a seção
    ``execution``, define a conferência da efetivação no fechamento. ``mercado`` (opcional):
    ``pregão -> MarketData`` para conferir cada efetivação contra a execução esperada no pregão
    (:func:`cdp.portfolio.execucao.conferir_efetivacao`: capacidade pelo volume realizado,
    mercado elegível, corte MOC, banda); sem ele, só o intervalo entre a posição anterior e a
    ordem aprovada é conferido.
    """

    def __init__(self, root: Path | str = "book", config: FundConfig | None = None,
                 mercado: Callable[[date], Any] | None = None) -> None:
        self.root = Path(root)
        self.config = config
        self.mercado = mercado
        self.root.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(self.root / "audit_log.jsonl")
        self.ledger = Ledger(self.root / "ledger.csv")

    # ---------------------------------------------- semanas
    def week_dir(self, week: date) -> Path:
        return self.root / week.isoformat()

    def list_weeks(self) -> list[date]:
        weeks = [_parse_week(p.name) for p in self.root.iterdir() if p.is_dir()]
        return sorted(w for w in weeks if w is not None)

    def kill_switch_active(self) -> bool:
        """``True`` se ``<root>/KILL_SWITCH`` existe (nenhuma nova operação; só redução)."""
        return (self.root / KILL_SWITCH_FILE).exists()

    # ---------------------------------------------- trilha
    def _audit_state(self) -> tuple[list[AuditEvent], _Index]:
        events = self.audit.events()
        return events, _index_events(events)

    def audit_head(self) -> str:
        """Hash do último evento da trilha (topo), para ancorar decisões e memos."""
        events = self.audit.events()
        return events[-1].event_hash if events else GENESIS_HASH

    @staticmethod
    def _proposal_event_seq(events: list[AuditEvent], proposal: Proposal) -> int | None:
        target = _proposal_payload_hash(proposal)
        for ev in events:
            if (ev.event_type == "PROPOSAL_CREATED" and ev.week == proposal.week
                    and ev.payload_hash == target):
                return ev.seq
        return None

    # ---------------------------------------------- pesquisa
    def _research_file(self, week: date, research_hash: str) -> Path:
        return self.week_dir(week) / f"research_pack_{research_hash[:HASH_PREFIX]}.json"

    def save_research_pack(self, pack: ResearchPack, actor: str | None = None) -> Path:
        """Grava o pacote (imutável por hash) e aponta ``research_pack.json`` para ele."""
        self.check_key(pack.week)
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
        """Grava a proposta versionada (imutável) e seus derivados; audita ``PROPOSAL_CREATED``.

        Os derivados (memo e CSVs) de propostas com dados sintéticos sempre carregam o aviso
        "DADOS SIMULADOS", inclusive quando o memo vem pronto em ``memo_markdown``.
        """
        week, k = proposal.week, proposal.version
        self.check_key(week)
        path = self._proposal_path(week, k)
        if path.exists():
            raise FileExistsError(f"Proposta v{k} da semana {week} já existe (imutável).")
        if self._read_booked(week) is not None:
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
        # Derivados são preparados antes da gravação: uma falha aqui não deixa proposta órfã.
        state = ProposalState.BLOCKED if proposal.hard_failures else ProposalState.IN_REVIEW
        memo = proposal.memo_markdown or render_memo(
            proposal, self.load_research_pack_by_hash(week, proposal.research_hash),
            config=self.config, state=state, audit_head_hash=self.audit_head())
        notice = _data_notice(proposal)
        if proposal.is_synthetic and SIMULATED_DATA_NOTICE not in memo.upper():
            memo = f"> **{SIMULATED_DATA_NOTICE}** — {notice}\n\n{memo}"
        memo_text = memo.rstrip() + f"\n\n---\n\n_Hash da proposta (SHA-256): `{h}`_\n"
        positions_csv = _models_csv(list(proposal.positions), PositionTarget, notice)
        trades_csv = _models_csv(list(proposal.trades), Trade, notice)

        _write_exclusive(path, text)
        self.audit.append(
            "PROPOSAL_CREATED", proposal.created_by, h,
            summary=f"Proposta {proposal.proposal_id} v{k}: {len(proposal.positions)} posições, "
                    f"{len(proposal.hard_failures)} falha(s) HARD, "
                    f"{len(proposal.soft_failures)} SOFT ({state.value}).",
            week=week)
        d = self.week_dir(week)
        _write_replace(d / f"positions_v{k}.csv", positions_csv)
        _write_replace(d / f"trades_v{k}.csv", trades_csv)
        _write_replace(d / f"memo_v{k}.md", memo_text)
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
        """Grava a decisão da versão correspondente (uma por versão, imutável).

        Recusa: decisão já existente, semana efetivada, versão substituída, proposta que não
        confere com a trilha, decisão inconsistente (:func:`verify_decision`),
        ``audit_head_hash`` inexistente ou anterior à criação da proposta, e aprovação humana
        sem co-assinatura quando :meth:`co_sign_reasons` exige. No modo ``AUTONOMOUS`` os gates
        determinísticos substituem a co-assinatura. Audita ``DECISION_<tipo>`` com a decisão
        completa como payload.
        """
        week = decision.week
        proposal = self._find_proposal(week, decision.proposal_id)
        k = proposal.version
        path = self._decision_path(week, k)
        if path.exists():
            raise FileExistsError(f"A proposta v{k} da semana {week} já tem decisão (imutável).")
        if self._read_booked(week) is not None:
            raise ValueError(f"A semana {week} já foi efetivada.")
        latest = self.proposal_versions(week)[-1]
        if k != latest:
            raise ValueError(f"A proposta v{k} foi substituída pela v{latest}; decida sobre a "
                             "versão mais recente.")
        events, _ = self._audit_state()
        created_seq = self._proposal_event_seq(events, proposal)
        if created_seq is None:
            raise ValueError(f"A proposta v{k} gravada não confere com a trilha de auditoria "
                             "(arquivo alterado); decisão recusada.")
        research_now = (proposal.research_hash if decision.decision == DecisionType.APPROVE
                        else decision.research_hash)
        ok, reasons = verify_decision(decision, proposal, proposal.snapshot_hash,
                                      proposal.config_hash, research_now)
        if not ok:
            raise ValueError("Decisão inconsistente com a proposta: " + " ".join(reasons))
        if decision.audit_head_hash is not None:
            head_seq = next((ev.seq for ev in events
                             if ev.event_hash == decision.audit_head_hash), None)
            if head_seq is None:
                raise ValueError("audit_head_hash da decisão não existe na trilha de auditoria.")
            if head_seq < created_seq:
                raise ValueError("audit_head_hash da decisão é anterior à criação da proposta "
                                 "na trilha (âncora retroativa).")
        if (decision.decision == DecisionType.APPROVE and decision.mode == DecisionMode.HUMAN
                and decision.co_signer is None):
            book_reasons = self.co_sign_reasons(proposal)
            if book_reasons:
                raise ValueError("Co-assinatura independente obrigatória (quatro olhos): "
                                 + " ".join(book_reasons))
        _write_exclusive(path, dump_json(decision))
        self.audit.append(
            f"DECISION_{decision.decision.value}", decision.approver, decision,
            summary=f"{decision.decision.value} da proposta {decision.proposal_id} v{k} por "
                    f"{decision.approver} ({decision.mode.value})"
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
    def _previous_booked(self, week: date) -> BookEntry | None:
        for w in reversed(self.list_weeks()):
            if w < week:
                entry = self.load_booked(w)
                if entry is not None:
                    return entry
        return None

    def holdings_before(self, week: date) -> dict[tuple[str, str], int]:
        """Ações detidas antes do fechamento de ``week``: a efetivação anterior mais recente
        (efetivações de "manter", sem posições, são puladas — a carteira segue a anterior)."""
        for w in reversed(self.list_weeks()):
            if w >= week:
                continue
            entry = self.load_booked(w)
            if entry is None:
                continue
            if not entry.positions:
                try:
                    prop = self._find_proposal(w, entry.proposal_id)
                except (ValueError, FileNotFoundError):
                    prop = None
                if prop is not None and prop.optimizer.status == "hold":
                    continue
            return {(p.issuer_id, p.ticker): int(p.shares or 0) for p in entry.positions}
        return {}

    def _kill_switch_violations(self, entry: BookEntry) -> list[str]:
        """Nomes que não são redução de uma posição do booking anterior (mesmo sinal, |w| ≤).
        Com a seção ``execution`` a comparação é em AÇÕES por linha (a efetivação lista a
        carteira resultante inteira, cujos pesos derivam com os preços)."""
        if self.config is not None and self.config.execution is not None:
            held = self.holdings_before(entry.week)
            bad_l: set[str] = set()
            for b in entry.positions:
                s0 = held.get((b.issuer_id, b.ticker), 0)
                sb = int(b.shares or 0)
                if s0 == 0 or sb * s0 < 0 or abs(sb) > abs(s0):
                    bad_l.add(b.issuer_id)
            return sorted(bad_l)
        prev = self._previous_booked(entry.week)
        prev_w: dict[str, float] = {}
        for p in prev.positions if prev is not None else []:
            prev_w[p.issuer_id] = prev_w.get(p.issuer_id, 0.0) + p.weight
        bad = []
        for b in entry.positions:
            w0 = prev_w.get(b.issuer_id, 0.0)
            if w0 == 0 or b.weight * w0 < 0 or abs(b.weight) > abs(w0) + _REDUCTION_EPS:
                bad.append(b.issuer_id)
        return sorted(bad)

    def _validate_booking(self, entry: BookEntry, snapshot_hash_now: str,
                          config_hash_now: str, research_hash_now: str) -> int:
        week = entry.week
        proposal = self._find_proposal(week, entry.proposal_id)
        k = proposal.version
        ok_chain, msg = self.audit.verify_chain()
        if not ok_chain:
            raise ValueError(f"Trilha de auditoria comprometida ({msg}); booking recusado.")
        events, index = self._audit_state()
        problems = self._week_problems(week, events, index)
        if problems:
            raise ValueError("Integridade da semana comprometida; booking recusado: "
                             + " ".join(problems))
        decision = self._load_decision_file(week, k)
        if decision is None or decision.decision != DecisionType.APPROVE:
            raise ValueError(f"A proposta v{k} não tem decisão APPROVE; booking recusado.")
        if entry.approval_hash != decision.approval_hash:
            raise ValueError("approval_hash do booking difere do registrado na decisão.")
        ok, reasons = verify_decision(decision, proposal, snapshot_hash_now, config_hash_now,
                                      research_hash_now)
        if not ok:
            raise ValueError("Aprovação inválida para booking: " + " ".join(reasons))
        if entry.booked_at < decision.decided_at:
            raise ValueError(f"Booking em {entry.booked_at.isoformat()} anterior à decisão "
                             f"({decision.decided_at.isoformat()}).")
        decisions = self.list_decisions(week)
        pending = [v for v in self.proposal_versions(week) if v > k
                   and (v not in decisions or decisions[v].decision != DecisionType.REJECT)]
        if pending:
            raise ValueError(f"Há versões mais recentes não rejeitadas ({pending}); efetive a "
                             "versão vigente.")
        if self.config is not None and self.config.execution is not None:
            held = self.holdings_before(week)
            mismatches = _booking_mismatches_fechamento(entry, proposal, held)
            if not mismatches and self.mercado is not None:
                from ..portfolio.execucao import conferir_efetivacao

                sessao = entry.booked_at.astimezone(
                    ZoneInfo(self.config.fund.timezone)).date()
                mismatches = conferir_efetivacao(entry, proposal, decision.decided_at, held,
                                                 self.mercado(sessao), self.config)
        else:
            mismatches = _booking_mismatches(entry, proposal)
        if mismatches:
            raise ValueError("Carteira efetivada difere da aprovada: " + " ".join(mismatches))
        if self.kill_switch_active():
            bad = self._kill_switch_violations(entry)
            if bad:
                raise ValueError(f"{KILL_SWITCH_FILE} ativo: apenas reduções de posições já "
                                 f"efetivadas são permitidas; novas/aumentadas: {bad}.")
        return k

    def save_booked(self, entry: BookEntry, snapshot_hash_now: str, config_hash_now: str,
                    research_hash_now: str, actor: str = SYSTEM_ACTOR) -> Path:
        """Efetiva a carteira da semana; exige aprovação válida contra os hashes atuais.

        Toda recusa por validação gera o evento ``BOOKING_REFUSED`` na trilha (§6.2).
        """
        week = entry.week
        path = self.week_dir(week) / _BOOKED
        if path.exists():
            raise FileExistsError(f"A semana {week} já foi efetivada (imutável).")
        try:
            k = self._validate_booking(entry, snapshot_hash_now, config_hash_now,
                                       research_hash_now)
        except ValueError as exc:
            self.audit.append(
                "BOOKING_REFUSED", actor,
                {"proposal_id": entry.proposal_id, "approval_hash": entry.approval_hash,
                 "reason": str(exc)},
                summary=f"Booking recusado ({entry.proposal_id}): {str(exc)[:300]}", week=week)
            raise
        _write_exclusive(path, dump_json(entry))
        self.audit.append(
            "BOOKED", actor, entry,
            summary=f"Carteira efetivada: {entry.proposal_id} v{k}, {len(entry.positions)} "
                    f"posições, aprovação {entry.approval_hash[:HASH_PREFIX]}.",
            week=week)
        return path

    def registrar_efetivacao_recusada(self, week: date, sessao: date, motivo: str,
                                      proposal_id: str, approval_hash: str,
                                      actor: str = SYSTEM_ACTOR) -> dict[str, Any]:
        """Registra que a decisão da semana CADUCOU: a efetivação foi recusada no leilão de
        fechamento do dia de montagem (ex.: kill switch ligado). Regra (``REGRA_CADUCIDADE``): a
        ordem vale só para aquele leilão; não há efetivação retroativa e a próxima data de
        montagem decide de novo. Arquivo imutável ``<semana>/efetivacao_recusada.json`` e evento
        ``BOOKING_LAPSED`` na trilha; idempotente (a primeira recusa vale)."""
        atual = self.efetivacao_recusada(week)
        if atual is not None:
            return atual
        if (self.week_dir(week) / _BOOKED).exists():
            raise FileExistsError(f"A semana {week} já foi efetivada: não há o que caducar.")
        payload = {"semana": week.isoformat(), "sessao": sessao.isoformat(),
                   "motivo": " ".join(str(motivo).split())[:600], "proposal_id": proposal_id,
                   "approval_hash": approval_hash, "regra": REGRA_CADUCIDADE}
        _write_exclusive(self.week_dir(week) / _CADUCADA, dump_json(payload))
        self.audit.append(
            LAPSE_EVENT, actor, payload,
            summary=(f"Efetivação recusada no fechamento de {sessao:%d/%m/%Y}: a decisão da "
                     f"semana {week:%d/%m/%Y} caducou (sem efetivação retroativa; a próxima "
                     "data de montagem decide de novo)."), week=week)
        return payload

    def efetivacao_recusada(self, week: date) -> dict[str, Any] | None:
        """Registro de caducidade da decisão da semana (conferido contra a trilha) ou ``None``.

        Arquivo que não confere com o evento ``BOOKING_LAPSED`` ⇒ ``ValueError`` (nunca se
        "descaduca" uma decisão editando o livro)."""
        path = self.week_dir(week) / _CADUCADA
        if not path.exists():
            return None
        data = _read_json(path)
        _, index = self._audit_state()
        if sha256_obj(data) not in index.get((LAPSE_EVENT, week), set()):
            raise ValueError(f"{_CADUCADA} da semana {week} não confere com a trilha de "
                             "auditoria (arquivo alterado fora do livro).")
        return data

    def _read_booked(self, week: date) -> BookEntry | None:
        """Leitura crua de ``booked.json`` (sem conferir a trilha) para integridade/estado."""
        path = self.week_dir(week) / _BOOKED
        if not path.exists():
            return None
        return BookEntry.model_validate(_read_json(path))

    def load_booked(self, week: date) -> BookEntry | None:
        """Carteira efetivada da semana, conferida contra o evento ``BOOKED`` da trilha.

        Levanta ``ValueError`` se o arquivo não confere (a marcação a mercado nunca usa uma
        carteira alterada fora do livro).
        """
        entry = self._read_booked(week)
        if entry is None:
            return None
        _, index = self._audit_state()
        if sha256_obj(entry) not in index.get(("BOOKED", week), set()):
            raise ValueError(f"booked.json da semana {week} não confere com a trilha de "
                             "auditoria (arquivo alterado fora do livro).")
        return entry

    def latest_booked(self) -> BookEntry | None:
        """Booking da semana mais recente, conferido contra a trilha (ver :meth:`load_booked`)."""
        for week in reversed(self.list_weeks()):
            entry = self.load_booked(week)
            if entry is not None:
                return entry
        return None

    # ---------------------------------------------- ledger
    def record_ledger(self, rows: list[LedgerRow], actor: str = SYSTEM_ACTOR,
                      week: date | None = None) -> int:
        """Anexa linhas de MTM ao ledger e registra o evento ``LEDGER_APPENDED``."""
        rows = list(rows)
        n = self.ledger.append(rows)
        if n:
            self.audit.append(
                "LEDGER_APPENDED", actor, [r.model_dump(mode="json") for r in rows],
                summary=f"{n} dia(s) de marcação a mercado ({rows[0].date} a {rows[-1].date}); "
                        f"NAV final {fmt_usd_mm(rows[-1].nav_usd)}.",
                week=week)
        return n

    # ---------------------------------------------- gênese
    def genesis(self) -> dict | None:
        """Payload da gênese do livro (``genese.json``), ou ``None`` se o livro não tem gênese."""
        path = self.root / GENESIS_FILE
        if not path.exists():
            return None
        return _read_json(path)

    def check_key(self, week: date) -> None:
        """Chave válida para gravar no livro: :func:`_check_week` e, num livro aberto na data de
        início (com gênese), nunca anterior a ela (a data de início do mandato configurada; sem
        configuração, a da gênese)."""
        _check_week(week, self.config)
        gen = self.genesis()
        if gen is None:
            return
        if self.config is not None:
            inicio = self.config.fund.inception_date
        else:
            inicio = date.fromisoformat(str(gen.get("inception_date")))
        if week < inicio:
            raise ValueError(f"Livro aberto na data de início do mandato ({inicio}): a semana "
                             f"{week} é anterior a ela.")


    def _genesis_problems(self, events: list[AuditEvent]) -> list[str]:
        """Gênese: no máximo um evento ``FUND_GENESIS``, sempre o primeiro da trilha, e o arquivo
        ``genese.json`` com o payload exato desse evento (e vice-versa)."""
        gen = [ev for ev in events if ev.event_type == GENESIS_EVENT]
        path = self.root / GENESIS_FILE
        if not gen:
            return [f"{GENESIS_FILE} sem evento {GENESIS_EVENT} na trilha."] if path.exists() else []
        problems: list[str] = []
        if len(gen) > 1 or gen[0].seq != 0:
            problems.append(f"Evento {GENESIS_EVENT} precisa ser único e o primeiro da trilha.")
        if not path.exists():
            return problems + [f"Evento {GENESIS_EVENT} sem o arquivo {GENESIS_FILE}."]
        try:
            payload = _read_json(path)
        except ValueError as exc:
            return problems + [f"{GENESIS_FILE} ilegível ({exc})."]
        if sha256_obj(payload) != gen[0].payload_hash:
            problems.append(f"{GENESIS_FILE} não confere com o evento {GENESIS_EVENT} da trilha.")
        return problems

    # ---------------------------------------------- estado e integridade
    def _decision_is_intact(self, decision: Decision, proposal: Proposal) -> bool:
        """Consistência interna da decisão com a proposta gravada (sem hashes externos)."""
        ok, _ = verify_decision(decision, proposal, proposal.snapshot_hash, proposal.config_hash,
                                decision.research_hash)
        return ok

    def _decision_valid(self, decision: Decision, proposal: Proposal, index: _Index) -> bool:
        """Íntegra em relação à proposta E idêntica à decisão auditada na trilha."""
        audited = index.get((f"DECISION_{decision.decision.value}", decision.week), set())
        return sha256_obj(decision) in audited and self._decision_is_intact(decision, proposal)

    def proposal_state(self, week: date, version: int) -> ProposalState:
        """Estado derivado só dos arquivos (incluindo a trilha de auditoria).

        Precedência: ``BOOKED`` > decisão válida (``APPROVED``/``REJECTED``) > ``SUPERSEDED``
        (há versão mais nova e esta não tem decisão) > ``BLOCKED`` (falha HARD) >
        ``IN_REVIEW``. Qualquer divergência de integridade — proposta, decisão ou booking que
        não conferem entre si ou com a trilha — resulta em ``BLOCKED`` (docs/research/07,
        §6.2): a aprovação fica invalidada e não há como "voltar" à revisão.
        """
        try:
            proposal = self.load_proposal(week, version)
        except ValueError:
            return ProposalState.BLOCKED
        if proposal is None:
            raise FileNotFoundError(f"Proposta v{version} da semana {week} não existe.")
        _, index = self._audit_state()
        if _proposal_payload_hash(proposal) not in index.get(("PROPOSAL_CREATED", week), set()):
            return ProposalState.BLOCKED
        try:
            decision = self._load_decision_file(week, version)
            booked = self._read_booked(week)
        except ValueError:
            return ProposalState.BLOCKED
        decision_ok = decision is not None and self._decision_valid(decision, proposal, index)
        if booked is not None and booked.proposal_id == proposal.proposal_id:
            if (decision_ok and decision is not None
                    and decision.decision == DecisionType.APPROVE
                    and booked.approval_hash == decision.approval_hash
                    and sha256_obj(booked) in index.get(("BOOKED", week), set())):
                return ProposalState.BOOKED
            return ProposalState.BLOCKED
        if decision is not None:
            if not decision_ok:
                return ProposalState.BLOCKED
            return (ProposalState.APPROVED if decision.decision == DecisionType.APPROVE
                    else ProposalState.REJECTED)
        if version < self.proposal_versions(week)[-1]:
            return ProposalState.SUPERSEDED
        if proposal.hard_failures:
            return ProposalState.BLOCKED
        return ProposalState.IN_REVIEW

    def week_states(self, week: date) -> dict[int, ProposalState]:
        return {v: self.proposal_state(week, v) for v in self.proposal_versions(week)}

    def _research_problems(self, week: date, events: list[AuditEvent],
                           index: _Index) -> list[str]:
        problems: list[str] = []
        audited = index.get(("RESEARCH_SAVED", week), set())
        d = self.week_dir(week)
        for path in sorted(d.glob("research_pack_*.json")):
            try:
                h = ResearchPack.model_validate(_read_json(path)).research_hash()
            except ValueError as exc:
                problems.append(f"{week}: {path.name} ilegível ({exc}).")
                continue
            if path.name != f"research_pack_{h[:HASH_PREFIX]}.json" or sha256_obj(h) not in audited:
                problems.append(f"{week}: {path.name} não confere com o hash/trilha de auditoria.")
        selections = [ev for ev in events if ev.week == week and ev.event_type in _RESEARCH_EVENTS]
        pointer = d / _RESEARCH_POINTER
        if not pointer.exists():
            if selections:
                problems.append(f"{week}: ponteiro de pesquisa ausente apesar de seleção auditada.")
            return problems
        try:
            ptr = _read_json(pointer)
            h, name = str(ptr["hash"]), str(ptr["file"])
        except (ValueError, KeyError, TypeError) as exc:
            return problems + [f"{week}: ponteiro de pesquisa ilegível ({exc})."]
        if not selections or selections[-1].payload_hash != sha256_obj(h):
            problems.append(f"{week}: ponteiro de pesquisa não confere com a última seleção "
                            "auditada (redirecionado fora do livro).")
        if name != f"research_pack_{h[:HASH_PREFIX]}.json" or not (d / name).exists():
            problems.append(f"{week}: ponteiro de pesquisa aponta para arquivo inconsistente.")
        return problems

    def _week_problems(self, week: date, events: list[AuditEvent], index: _Index) -> list[str]:
        """Artefatos da semana × trilha: cada arquivo auditado e cada evento com seu arquivo."""
        problems = self._research_problems(week, events, index)
        proposals: dict[int, Proposal] = {}
        created = index.get(("PROPOSAL_CREATED", week), set())
        for v in self.proposal_versions(week):
            try:
                p = self.load_proposal(week, v)
            except ValueError as exc:
                problems.append(f"{week} v{v}: proposta ilegível ({exc}).")
                continue
            if p is None:
                continue
            proposals[v] = p
            if _proposal_payload_hash(p) not in created:
                problems.append(f"{week} v{v}: proposta não confere com a trilha de auditoria.")
        if created - {_proposal_payload_hash(p) for p in proposals.values()}:
            problems.append(f"{week}: evento PROPOSAL_CREATED sem arquivo de proposta "
                            "correspondente (proposta removida ou substituída).")

        decisions: dict[int, Decision] = {}
        for v in self._versions(week, _DECISION_RE):
            try:
                dec = self._load_decision_file(week, v)
            except ValueError as exc:
                problems.append(f"{week} v{v}: decisão ilegível ({exc}).")
                continue
            if dec is None:
                continue
            decisions[v] = dec
            audited = index.get((f"DECISION_{dec.decision.value}", week), set())
            if sha256_obj(dec) not in audited:
                problems.append(f"{week} v{v}: decisão não confere com a trilha de auditoria.")
            p = proposals.get(v)
            if p is None or p.proposal_id != dec.proposal_id:
                problems.append(f"{week} v{v}: decisão sem proposta correspondente.")
            elif not self._decision_is_intact(dec, p):
                problems.append(f"{week} v{v}: decisão inválida para a proposta gravada.")
        decision_events = set().union(*(index.get((t, week), set()) for t in _DECISION_EVENTS))
        if decision_events - {sha256_obj(dec) for dec in decisions.values()}:
            problems.append(f"{week}: evento de decisão sem arquivo correspondente (decisão "
                            "removida ou substituída).")

        booked_events = index.get(("BOOKED", week), set())
        try:
            entry = self._read_booked(week)
        except ValueError as exc:
            return problems + [f"{week}: booking ilegível ({exc})."]
        booked_payloads: set[str] = set()
        if entry is not None:
            booked_payloads.add(sha256_obj(entry))
            if sha256_obj(entry) not in booked_events:
                problems.append(f"{week}: booking não confere com a trilha de auditoria.")
            if not any(dec.decision == DecisionType.APPROVE
                       and dec.approval_hash == entry.approval_hash
                       and dec.proposal_id == entry.proposal_id for dec in decisions.values()):
                problems.append(f"{week}: booking sem decisão APPROVE correspondente.")
        if booked_events - booked_payloads:
            problems.append(f"{week}: evento BOOKED sem booked.json correspondente.")
        lapse_events = index.get((LAPSE_EVENT, week), set())
        lapse_path = self.week_dir(week) / _CADUCADA
        if lapse_path.exists():
            try:
                lapse_ok = sha256_obj(_read_json(lapse_path)) in lapse_events
            except ValueError:
                lapse_ok = False
            if not lapse_ok:
                problems.append(f"{week}: registro de efetivação recusada não confere com a "
                                "trilha de auditoria.")
            if entry is not None:
                problems.append(f"{week}: semana com efetivação e com decisão caducada.")
        elif lapse_events:
            problems.append(f"{week}: evento {LAPSE_EVENT} sem {_CADUCADA} correspondente.")
        return problems

    def _ledger_problems(self, events: list[AuditEvent]) -> list[str]:
        """Confere ``ledger.csv`` contra a sequência de eventos ``LEDGER_APPENDED``.

        O payload de cada evento é a lista das linhas anexadas; como o JSON canônico de uma
        lista é a junção dos itens, o hash de cada lote é recalculado incrementalmente.
        """
        try:
            rows = self.ledger.rows()
        except ValueError as exc:
            return [f"ledger.csv ilegível ({exc})."]
        parts = [canonical_json(r.model_dump(mode="json")).encode("utf-8") for r in rows]
        i = 0
        for ev in (e for e in events if e.event_type == "LEDGER_APPENDED"):
            h = hashlib.sha256(b"[")
            matched = False
            for j in range(i, len(parts)):
                if j > i:
                    h.update(b",")
                h.update(parts[j])
                probe = h.copy()
                probe.update(b"]")
                if probe.hexdigest() == ev.payload_hash:
                    i, matched = j + 1, True
                    break
            if not matched:
                return [f"ledger.csv não confere com o evento de auditoria seq {ev.seq} (linhas "
                        "alteradas, removidas ou reordenadas)."]
        if i < len(parts):
            return [f"ledger.csv tem {len(parts) - i} linha(s) sem evento LEDGER_APPENDED "
                    "(anexadas fora do livro)."]
        return []

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Confere a cadeia de auditoria e cada artefato contra a trilha (e vice-versa).

        Detecta: edição ou remoção de eventos; pesquisa, proposta, decisão ou booking
        alterados, substituídos ou removidos; ponteiro de pesquisa redirecionado; decisões
        inconsistentes com a proposta; linhas do ledger alteradas ou anexadas fora do livro; e
        gênese (``genese.json``) ausente, alterada ou fora do início da trilha.
        """
        problems: list[str] = []
        ok_chain, msg = self.audit.verify_chain()
        if not ok_chain:
            problems.append(msg)
        events, index = self._audit_state()
        weeks = set(self.list_weeks()) | {
            ev.week for ev in events if ev.week is not None and ev.event_type in _ARTIFACT_EVENTS}
        for week in sorted(weeks):
            problems += self._week_problems(week, events, index)
        problems += self._ledger_problems(events)
        problems += self._genesis_problems(events)
        from .origem import read_replay_origin

        try:
            read_replay_origin(self)
        except (OSError, ValueError) as exc:
            problems.append(f"origem: {exc}")
        from .avaliacao import verify

        problems += [f"avaliação: {m}" for m in verify(self)]
        return (not problems, problems)
