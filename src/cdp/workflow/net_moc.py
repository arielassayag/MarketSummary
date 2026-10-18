"""Contrato NET prospectivo e recomposição econômica a partir de origens físicas.

A leitura histórica não ganha estampa. Toda nova efetivação, inclusive HOLD e sombra,
exige o contrato reservado, configuração completa e MarketStore nativo verificável.
O monitor passivo permanece independente desta barreira de escrita.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from threading import local
from zoneinfo import ZoneInfo

from cdp.leitura_arquivos import ler_bytes, ler_texto

from ..audit import AuditLog
from ..config import FundConfig, config_json, load_archived_config
from ..contracts import BookEntry, DailyRecord
from ..hashing import sha256_obj, sha256_text

PROPOSAL_KEY = "net_moc_contract"
RECORD_MARKER = "net_moc_v1"
SCHEMA = "cdp.net_moc/v1"
CONFIG_FOLDER = "net_config"
_SHA = re.compile(r"[0-9a-f]{64}")
_PHYSICAL_FDS = local()


class NetUnverifiable(ValueError):
    """Ausência/adulteração impede uma nova escrita; não equivale a NET igual a zero."""


class NetLimitExceeded(ValueError):
    """O estado econômico recomposto ultrapassa o limite exato do mandato."""


def stamp(cfg: FundConfig) -> dict:
    raw = config_json(cfg)
    digest = sha256_text(raw)
    return {"schema": SCHEMA, "config_path": f"{CONFIG_FOLDER}/{digest}.json",
            "config_sha256": digest, "comparison": "abs_signed_usd/nav_after_costs_exact"}


def descriptor(proposal, *, required: bool = False) -> dict | None:
    if proposal is None or PROPOSAL_KEY not in proposal.overrides:
        if required:
            raise NetUnverifiable("NET UNVERIFIABLE: contrato prospectivo ausente")
        return None
    value = proposal.overrides[PROPOSAL_KEY]
    return _descriptor_value(value)


def _descriptor_value(value) -> dict:
    keys = {"schema", "config_path", "config_sha256", "comparison"}
    if (not isinstance(value, dict) or set(value) != keys or value["schema"] != SCHEMA
            or not isinstance(value["config_sha256"], str)
            or not _SHA.fullmatch(value["config_sha256"])
            or value["config_path"] != f"{CONFIG_FOLDER}/{value['config_sha256']}.json"
            or value["comparison"] != "abs_signed_usd/nav_after_costs_exact"):
        raise NetUnverifiable("NET UNVERIFIABLE: contrato desconhecido/malformado")
    return dict(value)


def archive_config(root: Path, cfg: FundConfig) -> Path:
    """Arquiva a configuração efetiva integral antes de gerar/aprovar a proposta."""
    from .book import _write_exclusive

    raw = config_json(cfg)
    p = Path(root) / stamp(cfg)["config_path"]
    _own_path(p)
    if p.exists():
        if ler_texto(p, encoding='utf-8') != raw:
            raise NetUnverifiable("NET UNVERIFIABLE: configuração arquivada divergente")
    else:
        _write_exclusive(p, raw)
    return p


def economic_genesis(cfg: FundConfig) -> dict:
    """Descritor monetário somente para a abertura nativa de um livro realmente vazio."""
    return {"schema": "cdp.economic_genesis/v1", "currency": "USD",
            "initial_nav_usd": cfg.fund.inception_nav_usd, "config": stamp(cfg)}


def _own_path(path: Path) -> None:
    for p in (path, *path.absolute().parents):
        if p.is_symlink():
            raise NetUnverifiable(f"NET UNVERIFIABLE: link simbólico em {p}")


def _number(value, label: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise NetUnverifiable(f"NET UNVERIFIABLE: número ausente/inválido em {label}")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
        if not dec.is_finite():
            raise ValueError("não finito")
        return Fraction(dec)
    except (ValueError, ArithmeticError) as exc:
        raise NetUnverifiable(f"NET UNVERIFIABLE: número inválido em {label}") from exc


def exact_net(record: DailyRecord, config_raw: str) -> dict:
    """Compara lexemas decimais sem epsilon e sem arredondamento de contexto Decimal."""
    obj = json.loads(config_raw, parse_float=Decimal, parse_int=Decimal)
    risk = obj.get("risk")
    if not isinstance(risk, dict) or "net_exposure_max_abs" not in risk:
        raise NetUnverifiable("NET UNVERIFIABLE: limite explícito ausente na configuração")
    limit = _number(risk["net_exposure_max_abs"], "risk.net_exposure_max_abs")
    if limit < 0:
        raise NetUnverifiable("NET UNVERIFIABLE: limite negativo")
    body = json.loads(record.model_dump_json(), parse_float=Decimal, parse_int=Decimal)
    nav = _number(body["nav_end_usd"], "NAV após custos")
    if nav <= 0:
        raise NetUnverifiable("NET UNVERIFIABLE: NAV após custos não positivo")
    net = sum((_number(p["market_value_usd"], "posição USD") for p in body["positions"]),
              Fraction(0))
    bound = nav * limit
    result = {"schema": SCHEMA, "net_usd": [net.numerator, net.denominator],
              "nav_after_costs_usd": [nav.numerator, nav.denominator],
              "limit": [limit.numerator, limit.denominator],
              "bound_usd": [bound.numerator, bound.denominator],
              "passed": abs(net) <= bound}
    if not result["passed"]:
        raise NetLimitExceeded("NET FAIL: exposição resultante excede o limite após custos")
    return result


def receive_config(root: Path, proposal) -> tuple[FundConfig, str]:
    desc = descriptor(proposal, required=True)
    return _receive_archived(root, desc, proposal.config_hash)


def _receive_archived(root: Path, desc: dict, config_hash: str) -> tuple[FundConfig, str]:
    desc = _descriptor_value(desc)
    p = root / desc["config_path"]
    _own_path(p)
    try:
        raw = ler_texto(p, encoding='utf-8')
        if sha256_text(raw) != desc["config_sha256"]:
            raise ValueError("SHA bruto divergente")
        obj = json.loads(raw)
        if sha256_obj(obj) != config_hash:
            raise ValueError("config_hash da proposta divergente")
        cfg = FundConfig.model_validate(obj)
        if cfg.execution is None or "net_exposure_max_abs" not in obj.get("risk", {}):
            raise ValueError("execução/limite explícitos ausentes")
        if stamp(cfg) != desc:
            raise ValueError("configuração integral não recompõe a estampa")
        return cfg, raw
    except (OSError, ValueError, TypeError) as exc:
        raise NetUnverifiable(f"NET UNVERIFIABLE: configuração física inválida ({exc})") from exc


class PhysicalSources:
    """Custódia dos FDs e namespace fechado, sob o escritor único cooperativo.

    A trilha conserva o prefixo integral recebido; a autoridade dos eventos acrescidos
    pertence às validações nativas de Book e da prova preparatória, nunca a este hash.
    Contextos sobrepostos da mesma thread e processo compartilham cada FD até
    o último close; cada contexto conserva seus próprios recibos e rechecagens.
    """

    def __init__(self, roots: dict[str, Path], audit: AuditLog, *,
                 excluded: set[Path] | None = None, audit_rows: int | None = None) -> None:
        self.roots = {k: Path(v).absolute() for k, v in roots.items()}
        self.audit = audit
        self.excluded = {p.absolute() for p in (excluded or set())}
        self._fds: dict[str, int] = {}
        pid = os.getpid()
        if getattr(_PHYSICAL_FDS, "pid", None) != pid:
            _PHYSICAL_FDS.pool = {}
            _PHYSICAL_FDS.pid = pid
        self._pool: dict[Path, tuple[int, int]] = _PHYSICAL_FDS.pool
        self.receipts: dict[str, dict] = {}
        self.namespace: dict[str, list[str]] = {}
        self.directories: dict[str, dict] = {}
        raw = ler_bytes(audit.path) if audit.path.exists() else b""
        self.audit_raw = (b"".join(raw.splitlines(keepends=True)[:audit_rows])
                          if audit_rows is not None else raw)
        events = audit.events()
        if audit_rows is not None:
            events = events[:audit_rows]
        self.audit_prefix = {"path": str(audit.path.absolute()),
                             "bytes_len": len(self.audit_raw),
                             "sha256": hashlib.sha256(self.audit_raw).hexdigest(),
                             "head": events[-1].event_hash if events else "0" * 64,
                             "rows": [e.model_dump(mode="json") for e in events]}
        try:
            for name, root in self.roots.items():
                _own_path(root)
                paths = self._paths(root)
                self.namespace[name] = [str(p.relative_to(root)) for p in paths]
                for p in [root, *sorted(root.rglob("*"))]:
                    if p.is_dir() and not self._effect_directory(p, root):
                        s = p.lstat()
                        self.directories[f"{name}/{p.relative_to(root)}"] = {
                            "dev": s.st_dev, "ino": s.st_ino, "mode": s.st_mode}
                for p in paths:
                    if p.absolute() == audit.path.absolute():
                        continue
                    key = f"{name}/{p.relative_to(root)}"
                    shared = self._pool.get(p)
                    if shared is None:
                        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
                        self._pool[p] = (fd, 1)
                    else:
                        fd, references = shared
                        self._pool[p] = (fd, references + 1)
                    self._fds[key] = fd
                    self.receipts[key] = self._receipt(fd, p)
        except BaseException:
            self.close()
            raise

    def _paths(self, root: Path) -> list[Path]:
        if not root.is_dir():
            raise NetUnverifiable(f"NET UNVERIFIABLE: origem física ausente {root}")
        paths = sorted(root.rglob("*"))
        for p in paths:
            _own_path(p)
            if not p.is_dir() and not p.is_file():
                raise NetUnverifiable(f"NET UNVERIFIABLE: nó não regular {p}")
        out = []
        for p in paths:
            if not p.is_file() or p.absolute() in self.excluded:
                continue
            rel = p.relative_to(root).parts
            if root == self.roots.get("book") and rel and rel[0] == "net_moc":
                if (len(rel) != 6 or rel[1] != "v1" or rel[2] not in {"main", "shadow"}
                        or rel[5] not in {"base.json", "candidate.json", "binding.json"}):
                    raise NetUnverifiable("NET UNVERIFIABLE: nome extra na área de prova")
                continue  # Corpos recebidos pelo protocolo nativo, nunca insumos livres.
            out.append(p)
        return out

    def _effect_directory(self, path: Path, root: Path) -> bool:
        if root != self.roots.get("book"):
            return False
        rel = path.relative_to(root).parts
        return bool(rel) and (rel[0] == "net_moc" or any(
            path.absolute() in p.parents for p in self.excluded))

    @staticmethod
    def _receipt(fd: int, p: Path) -> dict:
        before = os.fstat(fd)
        named = p.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino)):
            raise NetUnverifiable(f"NET UNVERIFIABLE: origem sem custódia exclusiva {p}")
        os.lseek(fd, 0, os.SEEK_SET)
        h = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            h.update(chunk)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns")
        if any(getattr(before, f) != getattr(after, f) for f in fields):
            raise NetUnverifiable(f"NET UNVERIFIABLE: origem mudou durante leitura {p}")
        return {f.removeprefix("st_"): getattr(after, f) for f in fields} | {"sha256": h.hexdigest()}

    def manifest(self) -> dict:
        return {"roots": {k: str(v) for k, v in self.roots.items()},
                "files": dict(self.receipts), "namespace": dict(self.namespace),
                "directories": dict(self.directories),
                "native_outputs": sorted(str(p) for p in self.excluded),
                "audit_prefix": self.audit_prefix}

    def recheck(self) -> None:
        for name, root in self.roots.items():
            now = [str(p.relative_to(root)) for p in self._paths(root)]
            if now != self.namespace[name]:
                raise NetUnverifiable("NET UNVERIFIABLE: namespace físico mudou antes da escrita")
            directories = {}
            for p in [root, *sorted(root.rglob("*"))]:
                if p.is_dir() and not self._effect_directory(p, root):
                    s = p.lstat()
                    directories[f"{name}/{p.relative_to(root)}"] = {
                        "dev": s.st_dev, "ino": s.st_ino, "mode": s.st_mode}
            expected = {k: v for k, v in self.directories.items() if k.startswith(name + "/")}
            if directories != expected:
                raise NetUnverifiable("NET UNVERIFIABLE: namespace/diretório físico mudou")
        for key, fd in self._fds.items():
            name, rel = key.split("/", 1)
            if self._receipt(fd, self.roots[name] / rel) != self.receipts[key]:
                raise NetUnverifiable("NET UNVERIFIABLE: origem física mudou antes da escrita")
        raw = ler_bytes(self.audit.path) if self.audit.path.exists() else b""
        if not raw.startswith(self.audit_raw) or not self.audit.verify_chain()[0]:
            raise NetUnverifiable("NET UNVERIFIABLE: prefixo/trilha mudou antes da escrita")

    def close(self) -> None:
        for key, fd in self._fds.items():
            name, rel = key.split("/", 1)
            p = self.roots[name] / rel
            _, references = self._pool[p]
            if references == 1:
                os.close(fd)
                del self._pool[p]
            else:
                self._pool[p] = (fd, references - 1)
        self._fds.clear()


@dataclass
class NetCandidate:
    root: Path
    audit: AuditLog
    side: str
    entry: BookEntry
    record: DailyRecord
    diagnostic: dict
    base: dict
    sources: PhysicalSources


def _configuration_of_prior(book, proposal) -> dict:
    """Recebe o mandato próprio do fato anterior, inclusive o arquivo legado autenticado.

    A leitura de um prior não autoriza nova escrita: o candidato prospectivo
    continua obrigado à estampa e ao contrato de execução atuais de sua origem.
    """
    if descriptor(proposal) is not None:
        _, raw = receive_config(book.root, proposal)
        return {"proposal_config_hash": proposal.config_hash, "raw_sha256": sha256_text(raw),
                "raw": raw, "body": json.loads(raw)}
    p = book.week_dir(proposal.week) / "config_decisao.json"
    archived = load_archived_config(p, proposal.config_hash)
    if archived is None:
        raise NetUnverifiable("NET UNVERIFIABLE: configuração própria da carteira anterior ausente")
    return {"proposal_config_hash": proposal.config_hash,
            "raw_sha256": sha256_text(ler_texto(p)), "raw": ler_texto(p),
            "body": json.loads(ler_texto(p))}


def _prior_config(book, entry) -> dict | None:
    if entry is None:
        return None
    proposal = book._find_proposal(entry.week, entry.proposal_id)
    return _configuration_of_prior(book, proposal)


def compose(book, entry: BookEntry, *, shadow: bool = False) -> NetCandidate:
    """Recompõe pelo livro, trilha e armazenamento nativos; entrada é só o candidato comparado."""
    from ..data.store import MarketStore
    from .daily import (
        BOOK_SHADOW_FILE,
        DailyRunner,
        ShadowBook,
        _Plan,
        book_shadow_proposal,
        executable_in,
    )
    from .risco_diario import load as load_risk
    from .track_record import TrackRecord

    cfg_now = book.config
    if cfg_now is None or cfg_now.execution is None:
        raise NetUnverifiable("NET UNVERIFIABLE: configuração/execução nativa ausente")
    from ..backtest.replay import ReplayStore

    if type(book.market_store) not in (MarketStore, ReplayStore):
        raise NetUnverifiable("NET UNVERIFIABLE: MarketStore físico nativo ausente")
    root = book.root.absolute()
    track = TrackRecord(root / ("track_record_shadow" if shadow else "track_record"))
    shadow_book = ShadowBook(track)
    if shadow:
        proposal = book_shadow_proposal(book, entry.week)
        duplicate = shadow_book.load_proposal(entry.week)
        if (proposal is None or duplicate is not None
                and ler_bytes(root / str(entry.week) / BOOK_SHADOW_FILE)
                != ler_bytes(shadow_book.proposal_path(entry.week))):
            raise NetUnverifiable("NET UNVERIFIABLE: origem/duplicata da proposta-sombra divergente")
    else:
        proposal = book._find_proposal(entry.week, entry.proposal_id)
    if proposal is None or proposal.proposal_id != entry.proposal_id:
        raise NetUnverifiable("NET UNVERIFIABLE: proposta física própria ausente")
    cfg, raw = receive_config(root, proposal)
    from .contrato_custos import CURRENT, contract

    if contract(proposal) != CURRENT:
        raise NetUnverifiable("NET UNVERIFIABLE: contrato prospectivo de custos ausente")
    if cfg_now.config_hash() != cfg.config_hash():
        raise NetUnverifiable("NET UNVERIFIABLE: mandato atual difere da nova proposta")
    session = entry.booked_at.astimezone(ZoneInfo(cfg.fund.timezone)).date()
    if not executable_in(entry.week, session, cfg):
        raise NetUnverifiable("NET UNVERIFIABLE: candidato fora da janela MOC")
    # O conjunto de entradas não inclui os efeitos próprios da sessão. Seus corpos só
    # podem existir/autenticar pelo protocolo de preparação, BOOKED e append diário.
    outputs = {root / entry.week.isoformat() / "booked.json",
               root / entry.week.isoformat() / "efetivacao_recusada.json"}
    for tr_name in ("track_record", "track_record_shadow"):
        tr_root = root / tr_name
        outputs.update({tr_root / "records" / f"{session}.json",
                        tr_root / "risco_diario" / f"{session}.json",
                        tr_root / "track_record.csv"})
    outputs.update({root / "track_record_shadow" / "booked" / f"{entry.week}.json",
                    root / "track_record_shadow" / "proposals" / f"{entry.week}.json"})
    events = book.audit.events()
    authority = [e for e in events if e.week == entry.week and (
        e.event_type == "SHADOW_QUANT" if shadow else
        e.event_type == "DECISION_APPROVE" and e.payload_hash == sha256_obj(
            book.load_decision(entry.week, proposal.version)))]
    if not authority:
        raise NetUnverifiable("NET UNVERIFIABLE: evento de origem próprio ausente")
    sources = PhysicalSources({"book": root, "market": book.market_store.root}, book.audit,
                              excluded=outputs, audit_rows=authority[-1].seq + 1)
    try:
        prev = track.last()
        if prev is not None:
            ok, issues = track.verify()
            if not ok:
                raise NetUnverifiable("NET UNVERIFIABLE: prior diário incompleto: " + "; ".join(issues))
            for r in track.records():
                if r.input_hashes.get("risco_diario_v1"):
                    load_risk(track, r)
            if prev.date >= session:
                raise NetUnverifiable("NET UNVERIFIABLE: prior não anterior à execução")
        else:
            other = TrackRecord(root / ("track_record" if shadow else "track_record_shadow"))
            if not shadow and (other.records() or book._previous_booked(entry.week) is not None):
                raise NetUnverifiable("NET UNVERIFIABLE: gênese econômica contradiz história existente")
            gen = book.genesis()
            events = book.audit.events()
            if gen is None and events and events[0].event_type == "REPLAY_ORIGIN":
                from .origem import ECONOMIC_FILE, read_replay_origin

                read_replay_origin(book)
                monetary = root / ECONOMIC_FILE
                if monetary.is_file():
                    money = json.loads(ler_texto(monetary))
                    if set(money) != {"schema", "currency", "initial_nav_usd", "config",
                                      "config_hash", "inception_date"}:
                        raise NetUnverifiable("NET UNVERIFIABLE: gênese monetária incompleta")
                    gen = {"economic": {k: money[k] for k in (
                        "schema", "currency", "initial_nav_usd", "config")},
                        "config_hash": money["config_hash"],
                        "inception_date": money["inception_date"]}
            if (gen is None or not events or events[0].event_type != "FUND_GENESIS"
                    and events[0].event_type != "REPLAY_ORIGIN"
                    or events[0].event_type == "FUND_GENESIS"
                    and events[0].payload_hash != sha256_obj(gen)):
                raise NetUnverifiable("NET UNVERIFIABLE: gênese econômica autenticada ausente")
            economic = gen.get("economic")
            if not isinstance(economic, dict) or not isinstance(economic.get("config"), dict):
                raise NetUnverifiable("NET UNVERIFIABLE: descritor monetário da gênese ausente")
            if "config_hash" not in gen or "inception_date" not in gen:
                raise NetUnverifiable("NET UNVERIFIABLE: origem monetária incompleta")
            initial_cfg, _ = _receive_archived(root, economic["config"], gen["config_hash"])
            if (economic != economic_genesis(initial_cfg)
                    or gen["inception_date"] != str(initial_cfg.fund.inception_date)
                    or initial_cfg.fund.inception_date != cfg.fund.inception_date
                    or _number(economic["initial_nav_usd"], "NAV da gênese")
                    != _number(cfg.fund.inception_nav_usd, "NAV inicial do mandato")):
                raise NetUnverifiable("NET UNVERIFIABLE: gênese monetária/configuração inicial divergente")
        # ReplayStore aplica seu relógio/vintage próprio antes da recepção física fresca.
        book.market_store.load(as_of=session, verify=True)
        store = MarketStore(book.market_store.root, cfg=cfg)
        fresh = DailyRunner.from_root(cfg, store, root, with_shadow=True)
        md = store.load(as_of=session, verify=True).truncate(session)
        ctx = fresh.context(session, md, prev)
        decision = None if shadow else book.load_decision(entry.week, proposal.version)
        if shadow:
            if entry.approval_hash != proposal.proposal_hash():
                raise NetUnverifiable("NET UNVERIFIABLE: vínculo próprio da sombra divergente")
        else:
            fresh._verify_decision(session, proposal, decision, None)
        plan = _Plan(week=entry.week, proposal=proposal, decision=decision, entry=None,
                     hold=proposal.optimizer.status == "hold", approval_hash=entry.approval_hash,
                     proposal_id=entry.proposal_id, source="sombra" if shadow else "decisão")
        side = fresh.shadow if shadow else fresh.main
        result = fresh._prepare_side(side, ctx, prev, plan)
        if result.entry != entry:
            raise NetUnverifiable("NET UNVERIFIABLE: candidato difere da receita MOC integral")
        check = exact_net(result.record, raw)
        if not shadow:
            try:
                shadow_proposal = book_shadow_proposal(book, entry.week)
                if shadow_proposal is None:
                    shadow_plan = None
                else:
                    shadow_prev = fresh.shadow.track.last()
                    shadow_plan = fresh._shadow_plan(fresh.shadow, ctx, shadow_prev, None)
                from .net_moc_prova import seal
                if shadow_plan is not None:
                    shadow_result = fresh._prepare_side(fresh.shadow, ctx, shadow_prev, shadow_plan)
                    shadow_candidate = compose(book, shadow_result.entry, shadow=True)
                    try:
                        seal(shadow_candidate)
                        hashes = dict(result.record.input_hashes)
                        hashes["shadow_record"] = shadow_candidate.record.record_hash
                        result.record = result.record.model_copy(update={"input_hashes": hashes})
                        result.record = result.record.model_copy(
                            update={"record_hash": result.record.compute_hash()})
                    finally:
                        shadow_candidate.sources.close()
            except ValueError as exc:
                from .daily import clean_text

                alerts = [*result.record.alerts,
                          "Carteira-sombra só-quant não processada: " + clean_text(exc, 600)]
                result.record = result.record.model_copy(update={"alerts": alerts})
                result.record = result.record.model_copy(
                    update={"record_hash": result.record.compute_hash()})
        prior_entry = side.load_entry(prev.live_book_week) if prev and prev.live_book_week else None
        if shadow and prior_entry:
            prior_proposal = book_shadow_proposal(book, prior_entry.week)
            if prior_proposal is None or prior_proposal.proposal_id != prior_entry.proposal_id:
                raise NetUnverifiable("NET UNVERIFIABLE: proposta originária do prior sombra ausente")
            prior_cfg = _configuration_of_prior(book, prior_proposal)
        else:
            prior_cfg = _prior_config(book, prior_entry)
        proposal_path = (root / str(entry.week) / BOOK_SHADOW_FILE if shadow else
                         root / str(entry.week) / f"proposal_v{proposal.version}.json")
        # O JSON nativo pode registrar NaN em stress tests ausentes. Seus bytes
        # integrais ficam como texto: ausência não vira zero, null ou novo dado.
        base = {"schema": SCHEMA, "side": "shadow" if shadow else "main",
                "session": str(session), "proposal_json": ler_texto(proposal_path, encoding='utf-8'),
                "decision": decision.model_dump(mode="json") if decision else None,
                "config_raw_sha256": sha256_text(raw), "config_raw": raw,
                "config": json.loads(raw),
                "prior_configuration": prior_cfg,
                "prior_records": [r.model_dump(mode="json") for r in track.records()],
                "prior_entry": prior_entry.model_dump(mode="json") if prior_entry else None,
                "entry": entry.model_dump(mode="json"),
                "record": result.record.model_dump(mode="json"),
                "diagnostic": result.diagnostic, "net": check,
                "market_manifest": md.manifest.model_dump(mode="json"),
                "sources": sources.manifest()}
        sources.recheck()
        return NetCandidate(root, book.audit, "shadow" if shadow else "main", entry,
                            result.record, result.diagnostic, base, sources)
    except BaseException:
        sources.close()
        raise
