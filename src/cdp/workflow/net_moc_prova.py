"""Persistência exclusiva e recuperação literal da prova NET prospectiva.

A receita econômica pertence a ``net_moc.compose``. Esta camada sela seus corpos
inteiros, preserva o candidato antes de BOOKED e vincula os efeitos nativos depois
do append diário. Recuperar lê estados finitos; nunca negocia nem recalcula NAV.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..audit import AuditLog
from ..contracts import BookEntry, DailyRecord, Decision, Proposal
from ..hashing import sha256_obj, sha256_text
from .net_moc import RECORD_MARKER, SCHEMA, NetCandidate, NetUnverifiable, PhysicalSources

FOLDER = "net_moc"
VERSION = "v1"
CANDIDATE_SCHEMA = "cdp.net_moc.candidate/v1"
BINDING_SCHEMA = "cdp.net_moc.binding/v1"
PREPARED_EVENT = "NET_MOC_PREPARED"
BOUND_EVENT = "NET_MOC_BOUND"
FILENAMES = frozenset({"base.json", "candidate.json", "binding.json"})


@dataclass(frozen=True)
class PreparedNetProof:
    base: dict
    base_raw: str
    base_sha256: str
    candidate: dict
    candidate_raw: str
    binding: dict
    entry: BookEntry
    record: DailyRecord
    diagnostic: dict


@dataclass(frozen=True)
class RecoveredNetProof:
    entry: BookEntry
    record: DailyRecord
    diagnostic: dict
    state: str
    base: dict
    binding: dict


def _text(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False) + "\n"


def _fail(reason: str) -> None:
    raise NetUnverifiable("NET UNVERIFIABLE: " + reason)


def _no_links(path: Path) -> None:
    for node in (path, *path.absolute().parents):
        if node.is_symlink():
            _fail(f"link simbólico na prova: {node}")


def _read(path: Path) -> str:
    """Recebe todos os bytes com FD/nome estáveis, sem seguir links."""
    _no_links(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before, named = os.fstat(fd), path.lstat()
            fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns")
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or any(getattr(before, f) != getattr(named, f) for f in fields)):
                _fail(f"arquivo sem custódia exclusiva: {path}")
            chunks = []
            while chunk := os.read(fd, 1024 * 1024):
                chunks.append(chunk)
            after, named_after = os.fstat(fd), path.lstat()
            if any(getattr(before, f) != getattr(s, f)
                   for s in (after, named_after) for f in fields):
                _fail(f"arquivo mudou durante recepção: {path}")
            return b"".join(chunks).decode("utf-8")
        finally:
            os.close(fd)
    except (OSError, UnicodeError) as exc:
        raise NetUnverifiable(f"NET UNVERIFIABLE: prova física ausente/inválida: {path}") from exc


def _object(raw: str) -> dict:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                _fail("chave JSON duplicada")
            out[key] = value
        return out

    try:
        obj = json.loads(raw, object_pairs_hook=unique,
                         parse_constant=lambda _: _fail("número JSON não finito"))
        if not isinstance(obj, dict) or _text(obj) != raw:
            _fail("corpo da prova não é JSON canônico integral")
        return obj
    except (ValueError, TypeError) as exc:
        raise NetUnverifiable("NET UNVERIFIABLE: JSON da prova inválido") from exc


def proof_dir(root: Path, side: str, week: date, session: date) -> Path:
    if side not in {"main", "shadow"} or type(week) is not date or type(session) is not date:
        _fail("seleção de lado/semana/sessão inválida")
    return Path(root) / FOLDER / VERSION / side / str(week) / str(session)


def _check_area(root: Path) -> None:
    area = Path(root) / FOLDER
    _no_links(area)
    if not area.exists():
        return
    for node in area.rglob("*"):
        _no_links(node)
        parts = node.relative_to(area).parts
        valid = bool(parts) and parts[0] == VERSION
        if len(parts) >= 2:
            valid &= parts[1] in {"main", "shadow"}
        for part in parts[2:4]:
            try:
                valid &= str(date.fromisoformat(part)) == part
            except ValueError:
                valid = False
        valid &= ((node.is_dir() and len(parts) <= 4)
                  or (node.is_file() and len(parts) == 5 and parts[4] in FILENAMES))
        if not valid:
            _fail(f"nome extra/malformado na área de prova: {node}")


def _write_same(path: Path, raw: str) -> None:
    from .book import _write_exclusive

    _no_links(path)
    if path.exists():
        if _read(path) != raw:
            _fail(f"conflito com arquivo imutável: {path}")
    else:
        _write_exclusive(path, raw)


def _track_identity(track) -> tuple[Path, str]:
    from .track_record import TrackRecord

    if type(track) is not TrackRecord:
        _fail("TrackRecord nativo ausente")
    names = {"track_record": ("main", "DAILY_RECORD"),
             "track_record_shadow": ("shadow", "DAILY_RECORD_SHADOW")}
    if track.root.name not in names:
        _fail("raiz diária desconhecida")
    side, event = names[track.root.name]
    root = track.root.parent.absolute()
    if track.audit_event != event or track.audit.path.absolute() != root / "audit_log.jsonl":
        _fail("trilha/lado diário divergente")
    return root, side


def _binding(base_sha: str, envelope: dict, envelope_raw: str, record: DailyRecord) -> dict:
    return {"schema": BINDING_SCHEMA, "side": envelope["side"],
            "week": envelope["week"], "session": envelope["session"],
            "base_sha256": base_sha, "candidate_sha256": sha256_text(envelope_raw),
            "entry_sha256": envelope["entry_sha256"],
            "entry_payload_hash": sha256_obj(json.loads(envelope["entry_json"])),
            "record_hash": record.record_hash,
            "record_sha256": envelope["record_sha256"],
            "diagnostic_sha256": envelope["diagnostic_sha256"]}


def _unsealed(record: DailyRecord, diagnostic: dict) -> tuple[dict, dict]:
    from .risco_diario import MARKER

    diag = copy.deepcopy(diagnostic)
    diag.pop(RECORD_MARKER, None)
    inputs = dict(record.input_hashes)
    inputs.pop(RECORD_MARKER, None)
    inputs[MARKER] = sha256_text(_text(diag))
    rec = record.model_copy(update={"input_hashes": inputs})
    rec = rec.model_copy(update={"record_hash": rec.compute_hash()})
    return rec.model_dump(mode="json"), diag


def _economics(base: dict, record: DailyRecord, entry: BookEntry, side: str) -> Proposal:
    """Recompõe comparação/configuração em memória; passed não é uma autoridade."""
    from ..config import FundConfig
    from .net_moc import descriptor, exact_net, stamp

    try:
        proposal = Proposal.model_validate_json(base["proposal_json"])
        raw = base["config_raw"]
        cfg = FundConfig.model_validate_json(raw)
        desc = descriptor(proposal, required=True)
        config = json.loads(raw)
        if (not isinstance(raw, str) or config != base["config"]
                or sha256_text(raw) != base["config_raw_sha256"]
                or sha256_text(raw) != desc["config_sha256"]
                or sha256_obj(config) != proposal.config_hash or cfg.config_hash() != proposal.config_hash
                or stamp(cfg) != desc or cfg.execution is None
                or proposal.week != entry.week or proposal.proposal_id != entry.proposal_id
                or exact_net(record, raw) != base["net"]):
            _fail("configuração/comparação NET não recompõe a origem integral")
        if side == "main":
            decision = Decision.model_validate(base["decision"])
            if (decision.week != entry.week or decision.proposal_id != entry.proposal_id
                    or decision.proposal_hash != proposal.proposal_hash()
                    or decision.approval_hash != entry.approval_hash
                    or decision.config_hash != proposal.config_hash
                    or decision.snapshot_hash != proposal.snapshot_hash
                    or decision.research_hash != proposal.research_hash
                    or decision.decision.value != "APPROVE"):
                _fail("decisão integral difere do candidato recebido")
        elif base["decision"] is not None or entry.approval_hash != proposal.proposal_hash():
            _fail("origem/vínculo da proposta sombra divergente")
        return proposal
    except (KeyError, ValueError, TypeError) as exc:
        if isinstance(exc, NetUnverifiable):
            raise
        raise NetUnverifiable("NET UNVERIFIABLE: comparação/configuração integral inválida") from exc


def _receive_origin(root: Path, audit: AuditLog, proof: PreparedNetProof, *,
                    historical_bound: bool = False) -> None:
    """Recebe a proposta e seu próprio mandato; não consulta configuração atual."""
    from .daily import BOOK_SHADOW_FILE
    from .net_moc import receive_config

    base, entry, side = proof.base, proof.entry, proof.binding["side"]
    proposal = _economics(base, proof.record, entry, side)
    p = (root / str(entry.week) / f"proposal_v{proposal.version}.json" if side == "main" else
         root / str(entry.week) / BOOK_SHADOW_FILE)
    raw_proposal = _read(p)
    receipt = base["sources"]["files"].get(f"book/{p.relative_to(root)}")
    if receipt is None or receipt["sha256"] != sha256_text(raw_proposal):
        _fail("bytes da proposta física diferem da origem recebida")
    physical = Proposal.model_validate_json(raw_proposal)
    if raw_proposal != base["proposal_json"]:
        _fail("proposta física própria diverge da base recebida")
    _, raw = receive_config(root, physical)
    if raw != base["config_raw"]:
        _fail("bytes do mandato próprio divergem da prova-base")
    rows = base["sources"]["audit_prefix"]["rows"]
    if side == "main":
        kind, digest = "PROPOSAL_CREATED", sha256_obj(proposal.proposal_hash())
        decision_path = root / str(entry.week) / f"decision_v{proposal.version}.json"
        decision_raw = _read(decision_path)
        receipt = base["sources"]["files"].get(f"book/{decision_path.relative_to(root)}")
        if receipt is None or receipt["sha256"] != sha256_text(decision_raw):
            _fail("bytes da decisão física diferem da origem recebida")
        decision = Decision.model_validate_json(decision_raw)
        if decision.model_dump(mode="json") != base["decision"]:
            _fail("decisão física própria diverge da base recebida")
        approved = [e for e in rows if e["event_type"] == "DECISION_APPROVE"
                    and e["week"] == str(entry.week) and e["payload_hash"] == sha256_obj(decision)]
        if len(approved) != 1:
            _fail("decisão própria não autenticada no prefixo original")
    else:
        kind, digest = "SHADOW_QUANT", sha256_obj({"sha256": sha256_text(raw_proposal)})
        copy_path = root / "track_record_shadow" / "proposals" / f"{entry.week}.json"
        if copy_path.exists() and _read(copy_path) != raw_proposal:
            _fail("cópia nativa da proposta sombra divergente")
    authenticated = [e for e in rows if e["event_type"] == kind
                     and e["week"] == str(entry.week) and e["payload_hash"] == digest]
    if len(authenticated) != 1:
        _fail("proposta própria não autenticada no prefixo original")
    _prefix(audit, base, historical_bound=historical_bound)


def seal(candidate: NetCandidate) -> PreparedNetProof:
    """Sela somente em memória; não altera nenhum campo econômico ou arquivo."""
    from .book import dump_json
    from .risco_diario import MARKER
    from .track_record import record_json

    if type(candidate) is not NetCandidate or type(candidate.sources) is not PhysicalSources:
        _fail("candidato/receptor nativo ausente")
    base = copy.deepcopy(candidate.base)
    if (base.get("schema") != SCHEMA or base.get("side") != candidate.side
            or base.get("session") != str(candidate.record.date)
            or base.get("entry") != candidate.entry.model_dump(mode="json")
            or base.get("sources") != candidate.sources.manifest()
            or base.get("net", {}).get("passed") is not True):
        _fail("base não corresponde ao produto nativo inteiro")
    original_record, original_diagnostic = _unsealed(candidate.record, candidate.diagnostic)
    if (base.get("record") != original_record
            or base.get("diagnostic") != original_diagnostic
            or candidate.record.live_book_week != candidate.entry.week
            or candidate.record.approval_hash != candidate.entry.approval_hash):
        _fail("record/diagnóstico divergem da receita nativa")
    _economics(base, candidate.record, candidate.entry, candidate.side)
    base_raw = _text(base)
    base_sha = sha256_text(base_raw)
    # compose pode conservar o mesmo dict em base e candidate; o marcador não
    # deve modificar o corpo original que participa do hash da prova-base.
    candidate.diagnostic = copy.deepcopy(candidate.diagnostic)
    candidate.diagnostic[RECORD_MARKER] = base_sha
    diagnostic_raw = _text(candidate.diagnostic)
    inputs = dict(candidate.record.input_hashes) | {
        RECORD_MARKER: base_sha, MARKER: sha256_text(diagnostic_raw)}
    candidate.record = candidate.record.model_copy(update={"input_hashes": inputs})
    candidate.record = candidate.record.model_copy(update={"record_hash": candidate.record.compute_hash()})
    entry_raw, record_raw = dump_json(candidate.entry), record_json(candidate.record)
    envelope = {"schema": CANDIDATE_SCHEMA, "side": candidate.side,
                "week": str(candidate.entry.week), "session": str(candidate.record.date),
                "base_sha256": base_sha, "entry_json": entry_raw, "record_json": record_raw,
                "diagnostic_json": diagnostic_raw, "entry_sha256": sha256_text(entry_raw),
                "record_sha256": sha256_text(record_raw),
                "diagnostic_sha256": sha256_text(diagnostic_raw)}
    envelope_raw = _text(envelope)
    binding = _binding(base_sha, envelope, envelope_raw, candidate.record)
    return PreparedNetProof(base, base_raw, base_sha, envelope, envelope_raw, binding,
                            candidate.entry, candidate.record, candidate.diagnostic)


def _events(audit: AuditLog, kind: str, binding: dict):
    digest = sha256_obj(binding)
    return [e for e in audit.events() if e.event_type == kind
            and e.week == date.fromisoformat(binding["week"]) and e.payload_hash == digest]


def _prefix(audit: AuditLog, base: dict, *, historical_bound: bool = False) -> None:
    prefix = base["sources"]["audit_prefix"]
    original_root = Path(base["sources"]["roots"]["book"]).absolute()
    original_audit = Path(prefix["path"]).absolute()
    if original_audit != original_root / "audit_log.jsonl":
        _fail("trilha original externa à raiz econômica recebida")
    if not historical_bound and original_audit != audit.path.absolute():
        _fail("raiz da trilha difere da origem recebida")
    raw = _read(audit.path) if audit.path.exists() else ""
    data = raw.encode("utf-8")[:prefix["bytes_len"]]
    if (len(data) != prefix["bytes_len"] or hashlib.sha256(data).hexdigest() != prefix["sha256"]
            or [e.model_dump(mode="json") for e in audit.events()[:len(prefix["rows"])]]
            != prefix["rows"]):
        _fail("prefixo integral da trilha foi alterado")
    expected_head = prefix["rows"][-1]["event_hash"] if prefix["rows"] else "0" * 64
    if prefix["head"] != expected_head or not audit.verify_chain()[0]:
        _fail("cadeia/head de auditoria inválida")


def prepare(candidate: NetCandidate) -> PreparedNetProof:
    """Recebe novamente as fontes e persiste a preparação antes do writer BOOKED."""
    prepared = seal(candidate)
    root = candidate.root.absolute()
    if candidate.audit.path.absolute() != root / "audit_log.jsonl":
        _fail("candidato com trilha externa ao livro")
    candidate.sources.recheck()
    _receive_origin(root, candidate.audit, prepared)
    _check_area(root)
    folder = proof_dir(root, candidate.side, candidate.entry.week, candidate.record.date)
    _write_same(folder / "base.json", prepared.base_raw)
    _write_same(folder / "candidate.json", prepared.candidate_raw)
    _prefix(candidate.audit, prepared.base)
    found = _events(candidate.audit, PREPARED_EVENT, prepared.binding)
    if len(found) > 1:
        _fail("preparação duplicada")
    if not found:
        candidate.audit.append(PREPARED_EVENT, "sistema", prepared.binding,
                               f"Preparação NET {candidate.side} {candidate.record.date}",
                               week=candidate.entry.week)
    candidate.sources.recheck()
    return prepared


def _receive(root: Path, side: str, week: date, session: date, *,
             historical_bound: bool = False) -> PreparedNetProof:
    from .book import dump_json
    from .risco_diario import MARKER
    from .track_record import record_json

    folder = proof_dir(root, side, week, session)
    base_raw, envelope_raw = _read(folder / "base.json"), _read(folder / "candidate.json")
    base, envelope = _object(base_raw), _object(envelope_raw)
    keys = {"schema", "side", "week", "session", "base_sha256", "entry_json", "record_json",
            "diagnostic_json", "entry_sha256", "record_sha256", "diagnostic_sha256"}
    if (set(envelope) != keys or envelope["schema"] != CANDIDATE_SCHEMA
            or envelope["side"] != side or envelope["week"] != str(week)
            or envelope["session"] != str(session)
            or envelope["base_sha256"] != sha256_text(base_raw)):
        _fail("contrato/identidade do candidato retido divergente")
    try:
        entry = BookEntry.model_validate_json(envelope["entry_json"])
        record = DailyRecord.model_validate_json(envelope["record_json"])
        diagnostic = _object(envelope["diagnostic_json"])
    except (ValueError, TypeError) as exc:
        raise NetUnverifiable("NET UNVERIFIABLE: candidato retido inválido") from exc
    for name in ("entry", "record", "diagnostic"):
        if sha256_text(envelope[name + "_json"]) != envelope[name + "_sha256"]:
            _fail(f"hash literal do corpo {name} divergente")
    base_sha = sha256_text(base_raw)
    original_record, original_diagnostic = _unsealed(record, diagnostic)
    if (base.get("schema") != SCHEMA or base.get("side") != side
            or base.get("session") != str(session) or base.get("net", {}).get("passed") is not True
            or base.get("entry") != entry.model_dump(mode="json")
            or base.get("record") != original_record or base.get("diagnostic") != original_diagnostic
            or record.date != session or entry.week != week or record.live_book_week != week
            or record.approval_hash != entry.approval_hash
            or record.input_hashes.get(RECORD_MARKER) != base_sha
            or diagnostic.get(RECORD_MARKER) != base_sha
            or record.input_hashes.get(MARKER) != envelope["diagnostic_sha256"]
            or record.record_hash != record.compute_hash()
            or dump_json(entry) != envelope["entry_json"]
            or record_json(record) != envelope["record_json"]):
        _fail("produto final não recompõe a base selada integral")
    binding = _binding(base_sha, envelope, envelope_raw, record)
    audit = AuditLog(root / "audit_log.jsonl")
    _prefix(audit, base, historical_bound=historical_bound)
    result = PreparedNetProof(base, base_raw, base_sha, envelope, envelope_raw, binding,
                              entry, record, diagnostic)
    _receive_origin(root, audit, result, historical_bound=historical_bound)
    found = _events(audit, PREPARED_EVENT, binding)
    if len(found) != 1 or found[0].seq < len(base["sources"]["audit_prefix"]["rows"]):
        _fail("candidato órfão/preparação ausente ou duplicada")
    return result


def _booked_path(root: Path, side: str, week: date) -> Path:
    return (root / str(week) / "booked.json" if side == "main" else
            root / "track_record_shadow" / "booked" / f"{week}.json")


def _booked_events(audit: AuditLog, proof: PreparedNetProof):
    kind = "BOOKED" if proof.binding["side"] == "main" else "BOOKED_SHADOW"
    events = [e for e in audit.events() if e.event_type == kind and e.week == proof.entry.week]
    prepared = _events(audit, PREPARED_EVENT, proof.binding)[0]
    if any(e.payload_hash != proof.binding["entry_payload_hash"] or e.seq <= prepared.seq
           for e in events):
        _fail("BOOKED divergente/anterior à preparação NET")
    return events


def _receive_sources(root: Path, audit: AuditLog, base: dict) -> None:
    """Só reentradas pendentes recebem o readset antigo integral novamente."""
    manifest = base["sources"]
    roots = {key: Path(value) for key, value in manifest["roots"].items()}
    if roots.get("book", Path()).absolute() != root.absolute():
        _fail("raiz econômica recebida difere do livro")
    received = PhysicalSources(roots, audit,
                               excluded={Path(p) for p in manifest["native_outputs"]},
                               audit_rows=len(manifest["audit_prefix"]["rows"]))
    try:
        if received.manifest() != manifest:
            _fail("readset físico antigo não corresponde à preparação integral")
        received.recheck()
    finally:
        received.close()


def _missing_marker(track, record: DailyRecord) -> None:
    """A data de uma efetivação prospectiva não pode se apresentar como legado."""
    from zoneinfo import ZoneInfo

    from ..contracts import Proposal
    from .net_moc import descriptor, receive_config

    if record.live_book_week is None:
        return
    # Selecionar primeiro o contrato existente permite ler séries utilitárias
    # históricas com outra pasta. Uma obrigação prospectiva exige a raiz nativa.
    root = Path(track.root).parent.absolute()
    side = "shadow" if track.audit_event == "DAILY_RECORD_SHADOW" else "main"
    booked = _booked_path(root, side, record.live_book_week)
    if not booked.exists():
        return
    entry = BookEntry.model_validate_json(_read(booked))
    paths = (list((root / str(entry.week)).glob("proposal_v*.json")) if side == "main" else
             [root / "track_record_shadow" / "proposals" / f"{entry.week}.json"])
    for p in paths:
        if not p.exists():
            continue
        proposal = Proposal.model_validate_json(_read(p))
        if proposal.proposal_id != entry.proposal_id or descriptor(proposal) is None:
            continue
        _track_identity(track)
        cfg, _ = receive_config(root, proposal)
        session = entry.booked_at.astimezone(ZoneInfo(cfg.fund.timezone)).date()
        if record.date == session:
            _fail("efetivação prospectiva sem marcador NET no registro correspondente")


def _daily_effects(track, proof: PreparedNetProof, *, complete: bool) -> bool:
    from .risco_diario import path as risk_path

    rec_path = track.record_path(proof.record.date)
    if not rec_path.exists():
        if complete:
            _fail("registro diário ainda não foi persistido")
        return False
    if _read(rec_path) != proof.candidate["record_json"]:
        _fail("registro diário diverge dos bytes preparados")
    diagnostic_path = risk_path(track, proof.record.date)
    if diagnostic_path.exists() and _read(diagnostic_path) != proof.candidate["diagnostic_json"]:
        _fail("diagnóstico diário diverge dos bytes preparados")
    if complete:
        from .risco_diario import load as load_risk
        from .track_record import (
            CSV_COLUMNS,
            GENESIS_RECORD_HASH,
            _cell,
            record_consistency,
            record_summary,
        )

        load_risk(track, proof.record)
        records, rows = track.records(), track._csv_rows()
        if len(records) != len(rows):
            _fail("CSV/registro diário incompletos")
        previous = None
        for rec, row in zip(records, rows, strict=True):
            expected_prev = previous.record_hash if previous else GENESIS_RECORD_HASH
            expected_row = {c: _cell(record_summary(rec)[c]) for c in CSV_COLUMNS}
            daily = [e for e in track.audit.events() if e.event_type == track.audit_event
                     and e.payload_hash == sha256_obj(rec.record_hash)
                     and e.week == rec.live_book_week]
            if (rec.compute_hash() != rec.record_hash or rec.prev_record_hash != expected_prev
                    or (previous is not None and rec.date <= previous.date)
                    or record_consistency(rec, previous) or row != expected_row or len(daily) != 1):
                _fail("cadeia/CSV/evento diário incompleto ou divergente")
            previous = rec
        daily_events = [e for e in track.audit.events() if e.event_type == track.audit_event
                        and e.payload_hash == sha256_obj(proof.record.record_hash)]
        booked = _booked_events(track.audit, proof)
        if len(daily_events) != 1 or len(booked) != 1 or daily_events[0].seq <= booked[0].seq:
            _fail("append diário incompleto/duplicado")
    return True


def load(track, record: DailyRecord, *, require_event: bool = True) -> dict | None:
    if RECORD_MARKER not in record.input_hashes:
        _missing_marker(track, record)
        return None
    root, side = _track_identity(track)
    _check_area(root)
    if record.live_book_week is None:
        _fail("registro NET sem semana de efetivação")
    # A leitura histórica só retorna após conferir BOOKED, diário e BOUND
    # integrais nesta raiz. Os caminhos originais permanecem nos bytes selados.
    proof = _receive(root, side, record.live_book_week, record.date,
                     historical_bound=require_event)
    if record != proof.record:
        _fail("registro recebido diverge do candidato retido")
    p = _booked_path(root, side, proof.entry.week)
    if (_read(p) != proof.candidate["entry_json"]
            or len(_booked_events(track.audit, proof)) != 1):
        _fail("efetivação ausente/adulterada/não autenticada")
    if require_event:
        _daily_effects(track, proof, complete=True)
        folder = proof_dir(root, side, proof.entry.week, proof.record.date)
        bound = _events(track.audit, BOUND_EVENT, proof.binding)
        daily = [e for e in track.audit.events() if e.event_type == track.audit_event
                 and e.payload_hash == sha256_obj(record.record_hash)]
        if (_object(_read(folder / "binding.json")) != proof.binding or len(bound) != 1
                or bound[0].seq <= daily[0].seq):
            _fail("vínculo final ausente/duplicado/divergente")
    else:
        _receive_sources(root, track.audit, proof.base)
    return proof.base


def validate_record(track, record: DailyRecord) -> None:
    """Confere a preparação antes de append; o vínculo final vem depois do evento diário."""
    load(track, record, require_event=False)


def validate_booking(candidate: NetCandidate) -> None:
    prepared = seal(candidate)
    proof = _receive(candidate.root.absolute(), candidate.side, candidate.entry.week,
                     candidate.record.date)
    if proof.binding != prepared.binding:
        _fail("preparação difere do candidato recomposto")
    candidate.sources.recheck()
    _receive_sources(candidate.root.absolute(), candidate.audit, proof.base)


def bind(track, record: DailyRecord) -> None:
    """Vincula efeitos existentes; repetições literais não escrevem nem duplicam evento."""
    if RECORD_MARKER not in record.input_hashes:
        _missing_marker(track, record)
        return
    root, side = _track_identity(track)
    folder = proof_dir(root, side, record.live_book_week, record.date)
    # Um vínculo já fechado pode ser conferido depois de incrementos legítimos do livro.
    if (folder / "binding.json").exists():
        existing = _object(_read(folder / "binding.json"))
        if _events(track.audit, BOUND_EVENT, existing):
            load(track, record)
            return
    load(track, record, require_event=False)
    proof = _receive(root, side, record.live_book_week, record.date)
    _daily_effects(track, proof, complete=True)
    folder = proof_dir(root, side, proof.entry.week, record.date)
    _write_same(folder / "binding.json", _text(proof.binding))
    found = _events(track.audit, BOUND_EVENT, proof.binding)
    if len(found) > 1:
        _fail("vínculo NET duplicado")
    if not found:
        track.audit.append(BOUND_EVENT, track.actor, proof.binding,
                           f"NET vinculado a BOOKED e registro {side} {record.date}",
                           week=proof.entry.week)


def recover(book_root: Path, week: date, side: str = "main") -> RecoveredNetProof | None:
    """Lê um estado autenticado para os writers nativos completarem sem novas ordens."""
    from .track_record import TrackRecord

    root = Path(book_root).absolute()
    _check_area(root)
    parent = root / FOLDER / VERSION / side / str(week)
    if not parent.exists():
        return None
    sessions = sorted(parent.iterdir())
    if len(sessions) != 1:
        _fail("mais de uma sessão preparatória para a mesma efetivação")
    session = date.fromisoformat(sessions[0].name)
    # Recepção preliminar somente de leitura. Uma raiz diferente só pode sair
    # deste método quando o binding e todos os efeitos BOUND forem íntegros.
    proof = _receive(root, side, week, session, historical_bound=True)
    audit = AuditLog(root / "audit_log.jsonl")
    booked = _booked_path(root, side, week)
    events = _booked_events(audit, proof)
    if len(events) > 1:
        _fail("evento BOOKED duplicado")
    lapse = root / str(week) / "efetivacao_recusada.json"
    state = "prepared"
    if side == "main" and lapse.exists():
        raw = _read(lapse)
        payload = json.loads(raw)
        lapsed = [e for e in audit.events() if e.event_type == "BOOKING_LAPSED"
                  and e.week == week and e.payload_hash == sha256_obj(payload)]
        if (len(lapsed) != 1 or booked.exists() or events
                or payload.get("proposal_id") != proof.entry.proposal_id
                or payload.get("approval_hash") != proof.entry.approval_hash):
            _fail("caducidade conflita com o candidato preparado")
        state = "lapsed"
    elif booked.exists():
        if _read(booked) != proof.candidate["entry_json"]:
            _fail("BOOKED difere do candidato literal preparado")
        state = "booked" if events else "booked_pending_event"
    elif events:
        _fail("evento BOOKED sem arquivo")
    track = TrackRecord(root / ("track_record" if side == "main" else "track_record_shadow"))
    if _daily_effects(track, proof, complete=False):
        if state not in {"booked", "booked_pending_event"}:
            _fail("registro diário sem efetivação preparada")
        state = "recorded_pending_binding"
    final_path = sessions[0] / "binding.json"
    bound = _events(audit, BOUND_EVENT, proof.binding)
    if len(bound) > 1 or (bound and not final_path.exists()):
        _fail("vínculo final órfão/duplicado")
    if final_path.exists():
        if _object(_read(final_path)) != proof.binding or state != "recorded_pending_binding":
            _fail("vínculo final conflita com os efeitos preparados")
        if bound:
            load(track, proof.record)
            state = "bound"
    if state != "bound":
        _prefix(audit, proof.base)
        if state != "lapsed":
            _receive_sources(root, audit, proof.base)
    return RecoveredNetProof(proof.entry, proof.record, proof.diagnostic, state,
                             proof.base, proof.binding)
