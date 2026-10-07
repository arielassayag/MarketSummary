"""Replay isolado pelo ciclo operacional, com relógios real e histórico distintos.

Não busca dados, não altera o mandato oficial e não publica o portal. Preços reais
prefixados com fundamentos atuais são sombra; PIT exige capturas autenticadas.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import subprocess
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..calendar import (
    is_data_session,
    is_rebalance_day,
    previous_data_session,
    rebalance_date_of_week,
)
from ..config import FundConfig
from ..data.snapshot import load_snapshot, read_manifest, write_snapshot
from ..data.store import MarketStore
from ..hashing import sha256_file, sha256_obj
from ..workflow.book import _write_exclusive
from ..workflow.origem import ReplayOrigin, install_replay_origin, read_replay_origin
from ..workflow.runtime import RecusaEstruturada, Runtime, briefing_completo
from .proveniencia import FileVintageSource, assess_temporal_inputs, prefix_market

SCHEMA = "cdp.replay.operacional/v1"
STEP_EVENT = "REPLAY_STEP"
MIND = "outro"
BRT = ZoneInfo("America/Sao_Paulo")


class ReplaySchedule(BaseModel):
    """Horários explícitos do ensaio; atraso testa a recusa canônica do prazo."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    prepare_at: time = time(11, 7)
    decide_at: time = time(13, 7)
    close_at: time = time(19, 22)
    decision_lateness_seconds: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def chronological(self):
        if any(t.tzinfo is not None for t in (self.prepare_at, self.decide_at, self.close_at)):
            raise ValueError("Horários do replay são locais de Brasília, sem fuso embutido.")
        if not self.prepare_at <= self.decide_at <= self.close_at:
            raise ValueError("Horários exigem prepare_at <= decide_at <= close_at.")
        return self


class ReplayIntegrityError(ValueError):
    """Arquivo, origem, passo ou configuração divergente: não continua a operação."""


class _Clock:
    def __init__(self, at: datetime):
        self._at = at

    @property
    def at(self):
        return self._at

    @at.setter
    def at(self, value: datetime):
        if value < self._at:
            raise ReplayIntegrityError("Relógio do replay não pode voltar antes da etapa anterior.")
        self._at = value

    def __call__(self) -> datetime:
        return self.at

    def set(self, day: date, at: time) -> None:
        self.at = datetime.combine(day, at, tzinfo=BRT)


class ReplayStore(MarketStore):
    """Só bases físicas disponíveis na data pedida; nunca seleciona base futura."""

    def load(self, as_of: date | None = None, verify: bool = True):
        local = self._now().astimezone(BRT)
        available = (previous_data_session(local.date()) if local.time() < self.close_cutoff
                     else local.date())
        if as_of is None:
            as_of = min(available, self.last_date())
        elif as_of > available:
            raise ReplayIntegrityError("Data pedida posterior ao corte do relógio do replay.")
        eligible = [p for p in self.bases() if read_manifest(p).as_of <= as_of]
        if not eligible:
            raise ReplayIntegrityError(f"Sem base anterior ou igual a {as_of}; replay incompleto.")
        return super().load(as_of=as_of, verify=verify)


def _jsonable(value: Any) -> Any:
    """JSON sem NaN/inf; ausência estatística é null, nunca um zero."""
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return _jsonable(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _dump(value: Any) -> str:
    # A ordem de dicionários de configuração é preservada (somas em ponto flutuante).
    return json.dumps(_jsonable(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ReplayIntegrityError(f"Entrada redirecionada no ensaio: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha256_file(path)
    return result


def _verify_inventory(root: Path, expected: dict[str, str], *, exact: bool = True) -> None:
    current = _inventory(root)
    if (current != expected if exact else any(current.get(k) != v for k, v in expected.items())):
        raise ReplayIntegrityError(f"Arquivos congelados divergem: {root}")


def _code_identity() -> dict:
    repo = Path(__file__).resolve().parents[3]
    files = {}
    for folder in ("src/cdp", "configs/cdp"):
        for path in sorted((repo / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(repo).as_posix()] = sha256_file(path)
    for name in ("data/universe.csv", "pyproject.toml", "uv.lock"):
        path = repo / name
        if path.is_file():
            files[name] = sha256_file(path)
    run = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                         text=True, check=False)
    return {"commit": run.stdout.strip() if run.returncode == 0 else None,
            "files": files, "source_sha256": sha256_obj(files)}


def _workspace() -> Path:
    repo = Path(__file__).resolve().parents[3]
    run = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=repo,
                         capture_output=True, text=True, check=True)
    common = Path(run.stdout.strip())
    if not common.is_absolute():
        common = repo / common
    return common.resolve().parent


def isolated_output(out: Path | str, workspace: Path | str | None = None) -> Path:
    """Restringe qualquer escrita a uma subpasta nova de .cdp/ensaios do projeto."""
    workspace = Path(workspace).resolve() if workspace is not None else _workspace()
    requested = Path(out).absolute()
    allowed = workspace / ".cdp" / "ensaios"
    try:
        requested.relative_to(allowed)
    except ValueError as exc:
        raise ReplayIntegrityError(f"Saída precisa ficar dentro de {allowed}.") from exc
    if requested == allowed:
        raise ReplayIntegrityError("Escolha uma subpasta própria para o ensaio.")
    p = requested
    while p != workspace:
        if p.is_symlink():
            raise ReplayIntegrityError(f"Saída redirecionada: {p}")
        p = p.parent
    if not requested.resolve().is_relative_to(allowed.resolve()):
        raise ReplayIntegrityError("Saída escapa da pasta de ensaios.")
    return requested


@contextmanager
def _lock(out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with (out.parent / f".{out.name}.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReplayIntegrityError("Este replay já tem um escritor ativo.") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def replay_sessions(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("Fim do replay anterior ao início.")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)
            if is_data_session(start + timedelta(days=i))]


def _expected_steps(sessions: list[date], cfg: FundConfig) -> list[str]:
    names = []
    for day in sessions:
        if day >= cfg.fund.inception_date and is_rebalance_day(day, cfg):
            names += [f"{day}/{s}" for s in ("risk_before", "prepare", "decide", "thesis")]
        names += [f"{day}/{s}" for s in ("close", "daily_report")]
        if is_rebalance_day(day, cfg):
            names.append(f"{day}/weekly_report")
        names.append(f"{day}/risk_after")
    return names


def _execution_config(cfg: FundConfig, start: date) -> FundConfig:
    # Apenas a data de início contrafactual muda. A semana parcial não vira montagem.
    first = rebalance_date_of_week(start, cfg)
    while first is None or first < start:
        start += timedelta(days=7)
        first = rebalance_date_of_week(start, cfg)
    data = cfg.model_dump(mode="json")
    data["fund"]["inception_date"] = first.isoformat()
    return FundConfig.model_validate(data)


class _Steps:
    """Passos encadeados e ancorados no livro; retomada não repete passos selados."""

    def __init__(self, out: Path, rt: Runtime, manifest_sha256: str):
        self.out, self.rt, self.manifest_sha256 = out, rt, manifest_sha256
        self.path = out / "steps.jsonl"
        self.verify()

    def rows(self) -> list[dict]:
        try:
            return ([json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
                    if self.path.exists() else [])
        except (OSError, ValueError) as exc:
            raise ReplayIntegrityError(f"Cadeia de passos ilegível: {exc}") from exc

    def verify(self) -> list[str]:
        previous, names = "0" * 64, set()
        seals = [e for e in self.rt.book.audit.events() if e.event_type == STEP_EVENT]
        rows = self.rows()
        manifest = json.loads((self.out / "run_manifest.json").read_text())
        expected = _expected_steps([date.fromisoformat(d) for d in manifest["sessions"]], self.rt.cfg)
        if [r["step_id"] for r in rows] != expected[:len(rows)]:
            raise ReplayIntegrityError("Passos divergem do calendário e da sequência selados.")
        if len(seals) < len(rows) or len(seals) > len(rows) + 1:
            raise ReplayIntegrityError("Quantidade de âncoras e passos diverge.")
        sealed_files = {r["file"] for r in rows}
        if len(seals) > len(rows) and len(rows) < len(expected):
            pending_day, pending_stage = expected[len(rows)].split("/")
            sealed_files.add(f"{pending_day}-{pending_stage}.json")
        folder = self.out / "steps"
        if folder.exists():
            if folder.is_symlink() or not folder.is_dir():
                raise ReplayIntegrityError("Pasta de passos redirecionada ou inválida.")
            if {p.name for p in folder.iterdir()} - sealed_files:
                raise ReplayIntegrityError("Arquivo de passo sem âncora; não autenticar bytes órfãos.")
        for i, row in enumerate(rows):
            if Path(row["file"]).name != row["file"]:
                raise ReplayIntegrityError("Caminho de passo escapa da execução.")
            if row["seq"] != i or row["prev_hash"] != previous or row["step_id"] in names:
                raise ReplayIntegrityError("Cadeia de passos quebrada ou passo duplicado.")
            value = {k: v for k, v in row.items() if k != "step_hash"}
            if sha256_obj(value) != row["step_hash"]:
                raise ReplayIntegrityError("Conteúdo do passo alterado.")
            path = self.out / "steps" / row["file"]
            if path.is_symlink() or sha256_file(path) != row["sha256"]:
                raise ReplayIntegrityError("Arquivo do passo ausente, alterado ou redirecionado.")
            if seals[i].payload_hash != sha256_obj({"step_id": row["step_id"],
                                                    "sha256": row["sha256"]}):
                raise ReplayIntegrityError("Passo diverge da âncora de auditoria.")
            names.add(row["step_id"])
            previous = row["step_hash"]
        if len(seals) > len(rows):
            if len(rows) >= len(expected):
                raise ReplayIntegrityError("Âncora de passo inesperada após a última etapa.")
            pending = expected[len(rows)]
            day, stage = pending.split("/")
            path = self.out / "steps" / f"{day}-{stage}.json"
            if not path.is_file() or path.is_symlink():
                raise ReplayIntegrityError("Arquivo do passo ancorado pendente foi removido/redirecionado.")
            saved = json.loads(path.read_text())
            payload = {"step_id": pending, "sha256": sha256_file(path)}
            if (saved.get("step_id") != pending or
                    saved.get("manifest_sha256") != self.manifest_sha256 or
                    seals[-1].payload_hash != sha256_obj(payload)):
                raise ReplayIntegrityError("Passo pendente diverge da âncora ou do manifesto.")
            return [f"passo ancorado aguarda registro na cadeia: {pending}"]
        return []

    def run(self, day: date, stage: str, action: Callable[[], Any]) -> dict:
        self.verify()
        step_id = f"{day}/{stage}"
        rows = self.rows()
        for row in rows:
            if row["step_id"] == step_id:
                return json.loads((self.out / "steps" / row["file"]).read_text())["result"]
        path = self.out / "steps" / f"{day}-{stage}.json"
        seals = [e for e in self.rt.book.audit.events() if e.event_type == STEP_EVENT]
        if path.exists():
            saved = json.loads(path.read_text())
            # Apenas âncora→ledger é recuperável. Sem âncora, a integridade do livro
            # não autentica os bytes do resultado, mesmo se a ação foi concluída.
            if len(seals) != len(rows) + 1:
                raise ReplayIntegrityError("Passo parcial sem âncora; recuperação recusada.")
            if saved.get("step_id") != step_id or saved.get("manifest_sha256") != self.manifest_sha256:
                raise ReplayIntegrityError("Passo parcial ligado a outra execução.")
            valid, errors = self.rt.book.verify_integrity()
            if not valid:
                raise ReplayIntegrityError("Passo parcial não autenticado: " + "; ".join(errors))
        else:
            if len(seals) != len(rows):
                raise ReplayIntegrityError("Âncora órfã de outro passo; não retomar fora da sequência.")
            started, before = datetime.now(UTC), self.rt.book.audit_head()
            result = action()
            saved = {"step_id": step_id, "logical_at": self.rt.now(),
                     "actual_started_at": started, "actual_finished_at": datetime.now(UTC),
                     "manifest_sha256": self.manifest_sha256,
                     "audit_before": before, "audit_after": self.rt.book.audit_head(),
                     "result": result}
            _write_exclusive(path, _dump(saved))
        file_sha = sha256_file(path)
        payload = {"step_id": step_id, "sha256": file_sha}
        if len(seals) == len(rows):
            self.rt.book.audit.append(STEP_EVENT, "sistema", payload,
                                      summary=f"Replay: {step_id}", ts=datetime.now(UTC))
        elif seals[-1].payload_hash != sha256_obj(payload):
            raise ReplayIntegrityError("Passo parcial diverge da âncora existente.")
        row = {"seq": len(rows), "prev_hash": rows[-1]["step_hash"] if rows else "0" * 64,
               "step_id": step_id, "file": path.name, "sha256": file_sha}
        row["step_hash"] = sha256_obj(row)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            handle.flush()
        self.verify()
        return _jsonable(saved["result"])


def _monitor(rt: Runtime, day: date) -> dict:
    from ..workflow.risk_monitor import KILL_SWITCH_PREFIX, run_risk_monitor

    result = run_risk_monitor(rt, as_of=day, live=False, now=rt.now())
    requests = []
    for action in result.get("acoes_recomendadas", []):
        if action.startswith(KILL_SWITCH_PREFIX):
            reason = action[len(KILL_SWITCH_PREFIX):]
            # Recuperação após arquivo/pedido: não cria outra solicitação idêntica.
            pending = [p for p in rt.kill_switch_requests() if p["pedido"]["reason"] == reason]
            requests += pending or [rt.request_kill_switch(reason, by="sistema")]
    return {"monitor": result, "pedidos": requests}


def _prepare(rt: Runtime, day: date) -> dict:
    path = rt.week_dir(day) / "briefing"
    if briefing_completo(path):
        # Reconstrução confere hashes; não confundir existência com sucesso.
        _, info, _, _, _ = rt._week_state(day)
        receipt = dict(info)
        # O manifesto usa default=str (espaço); a trilha autentica datetime ISO (T).
        for key in ("prepared_at", "captured_at"):
            if isinstance(receipt.get(key), str):
                receipt[key] = datetime.fromisoformat(receipt[key])
        _require_receipt(rt, "WEEKLY_PREPARED", receipt, week=day)
        return {"semana": day, "status": "briefing recuperado", "briefing": path}
    return rt.weekly_prepare(day, mind=MIND, live=False)


def _require_receipt(rt: Runtime, event: str, payload: dict, *, week: date | None = None) -> None:
    valid, errors = rt.book.verify_integrity()
    if not valid:
        raise ReplayIntegrityError("Livro divergente ao retomar artefato: " + "; ".join(errors))
    expected = sha256_obj(payload)
    if not any(e.event_type == event and (week is None or e.week == week) and
               e.payload_hash == expected for e in rt.book.audit.events()):
        raise ReplayIntegrityError(f"Artefato existente sem recibo válido {event}; retomada recusada.")


def _report_payload(folder: Path) -> dict:
    md, html = folder / "relatorio.md", folder / "relatorio.html"
    if any(not p.is_file() or p.is_symlink() for p in (md, html)):
        raise ReplayIntegrityError("Relatório parcial ou redirecionado; retomada recusada.")
    return {"md": md.as_posix(), "html": html.as_posix(),
            "md_sha256": sha256_file(md), "html_sha256": sha256_file(html)}


def _daily_report(rt: Runtime, day: date) -> dict:
    from ..research.commentary import COMMENTARY_JSON, example_commentary, load_commentary_file

    rec = rt.track().get(day)
    if rec is None:
        return {"status": "sem registro diário", "data": day}
    folder = rt.daily_dir(day)
    if any((folder / f"relatorio.{suffix}").exists() for suffix in ("md", "html")):
        fb, _ = rt._daily_factbook(day, rec)
        _, issues = load_commentary_file(folder / COMMENTARY_JSON, fb, record=rec,
                                         expected_mind=rt.mente_esperada())
        _require_receipt(rt, "DAILY_REPORT", {**_report_payload(folder),
                                              "record": rec.record_hash,
                                              "commentary_issues": issues})
        return {"status": "relatório existente", "data": day}
    fb, _ = rt._daily_factbook(day, rec)
    path = rt.daily_dir(day) / COMMENTARY_JSON
    if not path.exists():
        _write_exclusive(path, _dump(example_commentary(fb, MIND)))
    return rt.daily_publish(day)


def _thesis(rt: Runtime, day: date) -> dict:
    from ..workflow.tese import (
        TESE_JSON,
        _payload,
        load_prepared,
        load_published,
        template_thesis,
        thesis_applicable,
        thesis_dir,
    )

    if not thesis_applicable(rt.book, day):
        return {"status": "tese vigente mantida"}
    folder = thesis_dir(rt.book_root, day)
    if (folder / "tese.md").exists():
        doc = load_published(rt.book_root, day)
        decision = rt.book.load_decision(day)
        if doc is None or decision is None:
            raise ReplayIntegrityError("Tese existente incompleta; retomada recusada.")
        _require_receipt(rt, "WEEKLY_THESIS", _payload(folder / "tese_publicada.json",
                                                      folder / "tese.md", decision,
                                                      str(doc.get("autoria"))), week=day)
        return {"status": "tese existente", "semana": day}
    rt.thesis_prepare(day)
    fb, analysis = load_prepared(folder)
    path = folder / TESE_JSON
    if not path.exists():
        _write_exclusive(path, _dump(template_thesis(analysis, fb, MIND)))
    return rt.thesis_publish(day)


def _weekly_report(rt: Runtime, day: date) -> dict:
    from ..research.comentario_semanal import COMENTARIO_JSON, carregar_comentario, modelo_valido
    from ..workflow.relatorio_semanal import (
        calcular_semana,
        factbook_semana,
        preparar,
        publicar,
        report_dir,
    )

    if rt.track().get(day) is None or not rt.book.list_decisions(day):
        return {"status": "sem montagem/registro para relatório semanal"}
    folder = report_dir(rt, day)
    if any((folder / f"relatorio.{suffix}").exists() for suffix in ("md", "html")):
        data = calcular_semana(rt, day)
        fb = factbook_semana(data)
        _, da_mente, issues = carregar_comentario(
            folder / COMENTARIO_JSON, fb, data["mudancas"], montagem=data["montagem"],
            mente_esperada=rt.mente_esperada())
        payload = {**_report_payload(folder), "registro": data["registro"],
                   "factbook": fb.factbook_hash(), "comentario_da_mente": da_mente,
                   "apontamentos": issues, "tipo": "montagem" if data["montagem"] else "semanal"}
        _require_receipt(rt, "WEEKLY_CLOSE_REPORT", payload, week=day)
        return {"status": "relatório existente", "data": day}
    preparar(rt, day, mind=MIND)
    data = calcular_semana(rt, day)
    fb = factbook_semana(data)
    path = folder / COMENTARIO_JSON
    if not path.exists():
        out = modelo_valido(fb, data["mudancas"], montagem=bool(data["montagem"]), mind=MIND)
        _write_exclusive(path, _dump(out))
    return publicar(rt, day)


def _summary(rt: Runtime, manifest: dict, out: Path) -> dict:
    records = rt.track().records()
    days = []
    for rec in records:
        components = rec.pnl_components
        days.append({"data": rec.date, "registro_hash": rec.record_hash,
                     "nav_inicial_usd": rec.nav_start_usd, "nav_final_usd": rec.nav_end_usd,
                     "pnl_usd": rec.pnl_usd, "retorno": rec.ret,
                     "pnl_componentes": components,
                     "ponte_nav_residuo_usd": rec.nav_end_usd - rec.nav_start_usd - rec.pnl_usd,
                     # factor/specific são decomposição de equity, não fluxos adicionais.
                     "ponte_caixa_residuo_usd": rec.pnl_usd - sum(components.get(k, 0.) for k in
                                                                  ("equity", "costs", "borrow", "financing")),
                     "posicoes_efetivas": len(rec.positions), "risco": rec.risk,
                     "alertas": rec.alerts})
    decisions = []
    for day in rt.book.list_weeks():
        decision = rt.book.load_decision(day)
        if decision is None:
            continue
        proposal, booked = rt.book.load_proposal(day), rt.book.load_booked(day)
        decisions.append({"data": day, "approval_hash": decision.approval_hash,
                          "proposta_hash": proposal.proposal_hash(),
                          "risco_proposto": proposal.risk,
                          "posicoes_propostas": len(proposal.positions),
                          "efetivada": booked is not None,
                          "posicoes_efetivas": len(booked.positions) if booked else None})
    return {"schema_version": SCHEMA, "mode": manifest["mode"], "pasta": out,
            "prospectiva": False, "merito_economico_validado": False,
            "aviso": manifest["aviso"], "pregoes": manifest["sessions"],
            "decisoes": decisions, "diarios": days,
            "registros": len(records), "nav_final_usd": records[-1].nav_end_usd if records else None,
            "limites_temporais": manifest["limitations"],
            "kill_switch_ativo": rt.kill_switch_active(),
            "autoria": "só-quant; comentários e tese são modelos do código, sem previsão de IA",
            "manifest_sha256": sha256_file(out / "run_manifest.json"),
            "audit_head": rt.book.audit_head(),
            "steps_sha256": sha256_file(out / "steps.jsonl")}


def _verify_result_files(out: Path, result: dict, *, completed: bool) -> None:
    files_path = out / "result_files.json"
    if sha256_file(files_path) != result["result_files_sha256"]:
        raise ReplayIntegrityError("Inventário final alterado.")
    files = json.loads(files_path.read_text())
    if completed:
        # Preserva também os bytes da trilha anterior à única âncora final.
        prefix = b"".join((out / "book" / "audit_log.jsonl").read_bytes().splitlines(keepends=True)[:-1])
        if hashlib.sha256(prefix).hexdigest() != files.pop("book/audit_log.jsonl"):
            raise ReplayIntegrityError("Bytes da trilha anteriores à conclusão foram alterados.")
    _verify_inventory(out, files, exact=False)
    expected_names = set(files) | {"book/audit_log.jsonl", "result.json", "result_files.json"}
    if set(_inventory(out)) != expected_names:
        raise ReplayIntegrityError("Arquivo inesperado depois do encerramento do replay.")


def _recover_final_anchor(rt: Runtime, manifest: dict, out: Path) -> None:
    """Arquivo→selo final: recálculo exato, sem outra decisão, booking ou registro."""
    steps = _Steps(out, rt, sha256_file(out / "run_manifest.json"))
    expected_names = _expected_steps([date.fromisoformat(d) for d in manifest["sessions"]], rt.cfg)
    if steps.verify() or len(steps.rows()) != len(expected_names):
        raise ReplayIntegrityError("Resultado parcial: ainda faltam etapas seladas.")
    terminal = out / "result.json"
    result = json.loads(terminal.read_text())
    _verify_result_files(out, result, completed=False)
    ok, messages = rt.verify_all()
    if not ok:
        raise ReplayIntegrityError("Conclusão parcial sem integridade: " + "; ".join(messages))
    expected = _summary(rt, manifest, out)
    expected.update({"integridade": True, "verificacao": messages,
                     "result_files_sha256": sha256_file(out / "result_files.json")})
    if _jsonable(expected) != result:
        raise ReplayIntegrityError("Resultado sem selo diverge do recálculo operacional.")
    rt.book.audit.append("REPLAY_COMPLETE", "sistema", {"sha256": sha256_file(terminal)},
                          summary="Replay operacional concluído; sem certificação de mérito econômico.",
                          ts=datetime.now(UTC))


def run_replay(snapshot: Path | str, out: Path | str, *, start: date, end: date,
               mode: str, cfg: FundConfig, workspace: Path | str | None = None,
               schedule: ReplaySchedule | None = None, resume: bool = False) -> dict:
    """Executa o Runtime sobre arquivos locais, sem gravação no livro oficial.

    Uma captura real atual nunca vira PIT pela seleção de um intervalo de preços.
    Em PIT, ``snapshot`` pode ser uma pasta de capturas históricas completas.
    A única premissa contrafactual de mandato é a data inaugural, declarada/selada.
    """
    out = isolated_output(out, workspace)
    snapshot = Path(snapshot).resolve()
    if snapshot.is_relative_to(out) or out.is_relative_to(snapshot):
        raise ReplayIntegrityError("Origem e saída não podem se sobrepor.")
    schedule = schedule or ReplaySchedule()
    sessions = replay_sessions(start, end)
    if not sessions:
        raise ValueError("O intervalo não contém pregões.")
    source_files, code = _inventory(snapshot), _code_identity()
    if not source_files:
        raise ValueError("Captura de mercado ausente.")
    options = {"start": start, "end": end, "mode": mode, "snapshot": snapshot,
               "schedule": schedule, "original_config_hash": cfg.config_hash(),
               "source_files": source_files, "code": code}
    options = _jsonable(options)
    execution_cfg = _execution_config(cfg, start)
    with _lock(out):
        manifest_path = out / "run_manifest.json"
        if out.exists():
            if not resume or not manifest_path.is_file():
                raise FileExistsError("Ensaio já existe; retomada exige --resume e manifesto íntegro.")
            manifest = json.loads(manifest_path.read_text())
            _inventory(out)  # Nenhuma subpasta retomada pode apontar para o livro oficial.
            if manifest["options"] != options:
                raise ReplayIntegrityError("Retomada diverge de fonte, código, janela, horário ou mandato.")
            _verify_inventory(out / "market", manifest["market_files"])
            _verify_inventory(out / "inputs", manifest["input_files"])
        else:
            # Preparação é promovida antes de iniciar qualquer operação do livro.
            out.mkdir()
            original = out / "inputs" / "fund_original.json"
            effective = out / "inputs" / "fund_ensaio.json"
            _write_exclusive(original, _dump(cfg))
            _write_exclusive(effective, _dump(execution_cfg))
            cuts = sorted(set(sessions + [previous_data_session(sessions[0])]))
            limitations, temporal = [], {}
            md = load_snapshot(snapshot, verify=True) if mode != "pit_auditado" else None
            for day in cuts:
                cutoff = datetime.combine(day, schedule.close_at, tzinfo=BRT)
                if mode == "pit_auditado":
                    view = FileVintageSource(snapshot, mode=mode, knowledge_cutoff=cutoff).load(day)
                    if view.as_of != day:
                        raise ReplayIntegrityError(f"Captura histórica não contém o fechamento de {day}.")
                else:
                    view = prefix_market(md, day, cutoff, mode)
                proof = assess_temporal_inputs(view, cutoff, mode)
                temporal[day.isoformat()] = proof
                limitations += proof["non_pit_dependencies"]
                write_snapshot(view, out / "market" / "base" / day.isoformat())
            _write_exclusive(out / "inputs" / "temporal.json", _dump(temporal))
            actual = datetime.now(UTC)
            manifest = {"schema_version": SCHEMA, "mode": mode, "actual_started_at": actual,
                        "options": options, "sessions": sessions,
                        "calendar": "união B3/NYSE/BMV; montagem pela semana inteira do mandato",
                        "contrafactual": {"campo": "fund.inception_date",
                                           "original": cfg.fund.inception_date,
                                           "ensaio": execution_cfg.fund.inception_date},
                        "config_original_hash": cfg.config_hash(),
                        "config_ensaio_hash": execution_cfg.config_hash(),
                        "input_files": _inventory(out / "inputs"),
                        "market_files": _inventory(out / "market"),
                        "no_network": True, "no_official_publish": True,
                        "limitations": sorted(set(limitations)),
                        "aviso": ("DADOS SIMULADOS — ensaio operacional retrospectivo."
                                  if mode == "simulado" else
                                  f"Ensaio retrospectivo {mode}; execução hipotética, fora do IC prospectivo.")}
            _write_exclusive(manifest_path, _dump(manifest))
            manifest = json.loads(manifest_path.read_text())
        clock = _Clock(datetime.combine(start, schedule.prepare_at, tzinfo=BRT))
        store = ReplayStore(out / "market", cfg=execution_cfg, now=clock,
                            close_cutoff=schedule.close_at, close_tz="America/Sao_Paulo")
        rt = Runtime(cfg=execution_cfg, book_root=out / "book", market_root=out / "market",
                     reports_root=out / "reports", clock=clock, store_override=store,
                     teses_root=None, expected_mind=MIND)
        origin = ReplayOrigin(mode=mode,
                              actual_started_at=datetime.fromisoformat(manifest["actual_started_at"]),
                              run_manifest_sha256=sha256_file(manifest_path),
                              source_manifest_sha256=sha256_obj(source_files))
        install_replay_origin(rt.book, origin)
        steps = _Steps(out, rt, origin.run_manifest_sha256)
        terminal = out / "result.json"
        final_seals = [e for e in rt.book.audit.events() if e.event_type == "REPLAY_COMPLETE"]
        if final_seals and not terminal.is_file():
            raise ReplayIntegrityError("Resultado final removido; não executar o replay outra vez.")
        if terminal.exists():
            clock.set(end, schedule.close_at)
            if not final_seals:
                _recover_final_anchor(rt, manifest, out)
            verify_replay(out, cfg=execution_cfg)
            return json.loads(terminal.read_text())
        for day in sessions:
            if day >= execution_cfg.fund.inception_date and is_rebalance_day(day, execution_cfg):
                clock.set(day, schedule.prepare_at)
                steps.run(day, "risk_before", lambda d=day: _monitor(rt, d))
                steps.run(day, "prepare", lambda d=day: _prepare(rt, d))
                deadline = rt.decision_deadline(day)
                clock.set(day, schedule.decide_at)
                if schedule.decision_lateness_seconds:
                    clock.at = deadline + timedelta(seconds=schedule.decision_lateness_seconds)

                def decide(d=day):
                    try:
                        result = rt.weekly_decide(d, mind=MIND)
                        if "avaliacao" in result:
                            result["avaliacao"] = {**result["avaliacao"], "prospectiva": False,
                                                   "origem": "ensaio retrospectivo"}
                        return result
                    except RecusaEstruturada as exc:
                        return exc.as_dict()

                steps.run(day, "decide", decide)
                steps.run(day, "thesis", lambda d=day: _thesis(rt, d))
            clock.set(day, schedule.close_at)
            steps.run(day, "close", lambda d=day: rt.daily_close(d, live=False, mind=MIND))
            steps.run(day, "daily_report", lambda d=day: _daily_report(rt, d))
            if is_rebalance_day(day, execution_cfg):
                steps.run(day, "weekly_report", lambda d=day: _weekly_report(rt, d))
            steps.run(day, "risk_after", lambda d=day: _monitor(rt, d))
        _verify_inventory(snapshot, source_files)
        if _code_identity() != code:
            raise ReplayIntegrityError("Código mudou durante o replay; não selar resultado misto.")
        ok, messages = rt.verify_all()
        steps.verify()
        if not ok:
            raise ReplayIntegrityError("Replay não íntegro: " + "; ".join(messages))
        summary = _summary(rt, manifest, out)
        summary.update({"integridade": True, "verificacao": messages})
        files = _inventory(out)
        files.pop("result_files.json", None)
        final_inventory = out / "result_files.json"
        if final_inventory.exists():
            if json.loads(final_inventory.read_text()) != files:
                raise ReplayIntegrityError("Inventário final parcial diverge dos arquivos atuais.")
        else:
            _write_exclusive(final_inventory, _dump(files))
        summary["result_files_sha256"] = sha256_file(out / "result_files.json")
        _write_exclusive(terminal, _dump(summary))
        rt.book.audit.append("REPLAY_COMPLETE", "sistema", {"sha256": sha256_file(terminal)},
                              summary="Replay operacional concluído; sem certificação de mérito econômico.",
                              ts=datetime.now(UTC))
        return json.loads(terminal.read_text())


def verify_replay(out: Path | str, *, cfg: FundConfig | None = None) -> dict:
    """Confere execução e arquivos finais, inclusive retomada sem uma nova ordem."""
    out = Path(out)
    if not (out / "book" / "audit_log.jsonl").is_file():
        raise ReplayIntegrityError("Livro/trilha do replay ausente; verificação não cria outro livro.")
    _inventory(out)  # Recusa redirecionamentos antes de instanciar leitores do Runtime.
    manifest = json.loads((out / "run_manifest.json").read_text())
    cfg = cfg or FundConfig.model_validate_json((out / "inputs" / "fund_ensaio.json").read_text())
    schedule = ReplaySchedule.model_validate(manifest["options"]["schedule"])
    end = date.fromisoformat(manifest["options"]["end"])
    clock = _Clock(datetime.combine(end, schedule.close_at, tzinfo=BRT))
    rt = Runtime(cfg=cfg, book_root=out / "book", market_root=out / "market",
                 reports_root=out / "reports", clock=clock,
                 store_override=ReplayStore(out / "market", cfg=cfg, now=clock,
                                            close_cutoff=schedule.close_at, close_tz="America/Sao_Paulo"),
                 teses_root=None)
    origin = read_replay_origin(rt.book)
    if origin is None or origin.run_manifest_sha256 != sha256_file(out / "run_manifest.json"):
        raise ReplayIntegrityError("Manifesto diverge da origem do replay.")
    _verify_inventory(out / "inputs", manifest["input_files"])
    _verify_inventory(out / "market", manifest["market_files"])
    steps = _Steps(out, rt, origin.run_manifest_sha256)
    pending = steps.verify()
    ok, messages = rt.verify_all()
    if not ok:
        raise ReplayIntegrityError("Replay não íntegro: " + "; ".join(messages))
    terminal = out / "result.json"
    seal = [e for e in rt.book.audit.events() if e.event_type == "REPLAY_COMPLETE"]
    if seal and not terminal.is_file():
        raise ReplayIntegrityError("Resultado final removido, apesar da âncora de conclusão.")
    if terminal.exists():
        result = json.loads(terminal.read_text())
        if len(seal) != 1 or seal[0].payload_hash != sha256_obj({"sha256": sha256_file(terminal)}):
            raise ReplayIntegrityError("Resultado final diverge da âncora.")
        if rt.book.audit.events()[-1] != seal[0] or seal[0].prev_hash != result["audit_head"]:
            raise ReplayIntegrityError("Trilha mudou depois do resultado final.")
        expected_steps = _expected_steps([date.fromisoformat(d) for d in manifest["sessions"]], cfg)
        if pending or len(steps.rows()) != len(expected_steps):
            raise ReplayIntegrityError("Conclusão com passos ainda pendentes.")
        _verify_result_files(out, result, completed=True)
    elif not pending:
        pending = ["execução ainda sem resultado final selado"]
    return {"integridade": True, "concluido": bool(terminal.exists()),
            "pendencias": pending, "verificacao": messages}
