"""Cache por hash de requisição, ledger append-only de chamadas e *replay* de respostas.

- :class:`CachedProvider` evita repetir chamadas idênticas (chave = SHA-256 de provedor, modelo,
  prompts, schema, temperatura e amostra). Erros nunca são gravados no cache.
- :class:`LLMCallLedger` grava um :class:`~latam_ls.contracts.LLMCallRecord` por chamada em
  JSONL append-only e a resposta bruta em ``<ledger_dir>/raw/<request_sha256>.json`` com o
  ``response_sha256``. ``ledger_hash()`` entra no hash da pesquisa.
- :class:`ReplayProvider` reproduz uma semana a partir das respostas gravadas (pelo
  ``request_sha256``) e falha explicitamente quando a resposta não existe: reprodutibilidade é
  *replay* do artefato, nunca regeneração (docs/research/07 §5.6).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ...contracts import LLMCallRecord
from ...hashing import sha256_obj, sha256_text
from ..schemas import SCHEMAS
from .base import (
    LLMProvider,
    LLMResult,
    error_result,
    parse_json_payload,
    request_sha256,
    result_from_payload,
    result_payload,
)

LEDGER_FILENAME = "llm_calls.jsonl"
RAW_DIRNAME = "raw"


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)


def calls_digest(records: Iterable[LLMCallRecord]) -> str:
    """Hash do conteúdo determinístico das chamadas (sem horários nem latência).

    Usado para dobrar as respostas brutas no ``input_hash`` das notas: qualquer mudança de
    resposta, modelo, prompt ou validação altera o hash da pesquisa.
    """
    return sha256_obj([
        {"request": r.request_sha256, "response": r.response_sha256, "model": r.model,
         "prompt_version": r.prompt_version, "schema": r.schema_name, "parse_ok": r.parse_ok,
         "issues": list(r.validation_issues)}
        for r in records
    ])


def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def payload_integrity(payload: dict[str, Any] | None, record: LLMCallRecord) -> str | None:
    """Confere a resposta gravada contra o registro do ledger (``None`` = íntegra).

    O texto bruto é a fonte da verdade: precisa bater com ``response_sha256``; o objeto
    ``parsed`` gravado (se houver) precisa ser exatamente o que o texto bruto produz; e o
    desfecho (erro × sucesso) precisa ser o mesmo registrado em ``parse_ok``.
    """
    if payload is None:
        return "resposta bruta ilegível"
    if payload.get("request_sha256") not in (None, record.request_sha256):
        return "resposta bruta de outra requisição"
    raw_text = payload.get("raw_text")
    got = sha256_text(raw_text) if isinstance(raw_text, str) else None
    if got != record.response_sha256:
        return "resposta bruta adulterada (hash do texto difere do ledger)"
    if bool(record.parse_ok) != (payload.get("error") is None):
        return "desfecho gravado (erro/sucesso) difere do ledger"
    schema = SCHEMAS.get(record.schema_name)
    stored = payload.get("parsed")
    if (record.parse_ok and schema is not None and stored is not None
            and isinstance(raw_text, str)):
        parsed, err = parse_json_payload(raw_text, schema)
        if err is not None or parsed is None or parsed.model_dump(mode="json") != stored:
            return "objeto interpretado gravado difere do texto bruto (adulteração)"
    return None


class LLMCallLedger:
    """Ledger append-only de chamadas a LLM (um ``LLMCallRecord`` por linha).

    ``path`` é o arquivo JSONL; um diretório (ou caminho sem extensão) usa
    ``<dir>/llm_calls.jsonl``. As respostas brutas ficam em ``<dir>/raw/``.
    """

    def __init__(self, path: str | Path) -> None:
        p = Path(path)
        if p.is_dir() or p.suffix == "":
            p = p / LEDGER_FILENAME
        self.path = p
        self.dir = p.parent
        self.raw_dir = self.dir / RAW_DIRNAME

    def records(self) -> list[LLMCallRecord]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(LLMCallRecord.model_validate_json(line))
        return out

    def append(self, record: LLMCallRecord) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False,
                               sort_keys=True) + "\n")

    def extend(self, records: Iterable[LLMCallRecord]) -> None:
        for r in records:
            self.append(r)

    def save_raw(self, request_hash: str, payload: dict[str, Any]) -> tuple[str, str | None]:
        """Grava a resposta bruta (nunca sobrescreve conteúdo diferente).

        Retorna ``(caminho relativo ao diretório do ledger, response_sha256)``; o hash é do
        texto bruto da resposta (``None`` quando não houve resposta, ex.: erro de rede).
        """
        raw_text = payload.get("raw_text")
        response_hash = sha256_text(raw_text) if isinstance(raw_text, str) else None
        content = _dump(payload)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        target = self.raw_dir / f"{request_hash}.json"
        if target.exists() and target.read_text(encoding="utf-8") != content:
            target = self.raw_dir / f"{request_hash}.{sha256_text(content)[:12]}.json"
        if not target.exists():
            target.write_text(content, encoding="utf-8")
        return target.relative_to(self.dir).as_posix(), response_hash

    def _safe_raw_path(self, rel: str | None) -> Path | None:
        """Caminho da resposta bruta confinado a ``<ledger_dir>/raw`` (sem *path traversal*)."""
        if not rel:
            return None
        try:
            path = (self.dir / rel).resolve()
            root = self.raw_dir.resolve()
        except (OSError, ValueError):
            return None
        return path if path.is_relative_to(root) else None

    def missing_records(self, records: Iterable[LLMCallRecord]) -> list[str]:
        """``call_id`` dos registros que NÃO estão gravados (idênticos) neste ledger."""
        stored = {sha256_obj(r.model_dump(mode="json")) for r in self.records()}
        return [r.call_id for r in records
                if sha256_obj(r.model_dump(mode="json")) not in stored]

    def raw_index(self) -> dict[str, str]:
        """``request_sha256`` → caminho relativo da resposta bruta mais recente."""
        index: dict[str, str] = {}
        for r in self.records():
            if r.raw_response_path:
                index[r.request_sha256] = r.raw_response_path
        return index

    def load_raw(self, request_hash: str,
                 index: dict[str, str] | None = None) -> dict[str, Any] | None:
        """Payload bruto mais recente gravado para ``request_hash`` (``None`` se ausente)."""
        rel = (index if index is not None else self.raw_index()).get(request_hash)
        path = self._safe_raw_path(rel or f"{RAW_DIRNAME}/{request_hash}.json")
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def ledger_hash(self) -> str:
        """SHA-256 de todos os registros (ordem de gravação preservada)."""
        return sha256_obj([r.model_dump(mode="json") for r in self.records()])

    def verify_raw(self) -> list[str]:
        """Confere que cada resposta bruta gravada ainda corresponde ao ``response_sha256``."""
        problems = []
        for r in self.records():
            if not r.raw_response_path:
                continue
            path = self._safe_raw_path(r.raw_response_path)
            if path is None:
                problems.append(f"{r.call_id}: caminho de resposta bruta fora do ledger "
                                f"({r.raw_response_path}).")
                continue
            if not path.exists():
                problems.append(f"{r.call_id}: resposta bruta ausente ({r.raw_response_path}).")
                continue
            problem = payload_integrity(_read_payload(path), r)
            if problem:
                problems.append(f"{r.call_id}: {problem} ({r.raw_response_path}).")
        return problems


class CachedProvider(LLMProvider):
    """Envolve um provedor com cache em disco por ``request_sha256`` (erros não são gravados)."""

    def __init__(self, inner: LLMProvider, cache_dir: str | Path) -> None:
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.name = inner.name
        self.model = inner.model
        self.deterministic = inner.deterministic

    def key(self, system: str, user: str, schema: type[BaseModel], temperature: float,
            sample: int) -> str:
        return request_sha256(self.inner.name, self.inner.model, system, user, schema.__name__,
                              temperature, sample)

    def complete_json(self, system: str, user: str, schema: type[BaseModel], *, task: str,
                      temperature: float = 0.0, sample: int = 0,
                      context: dict | None = None) -> LLMResult:
        key = self.key(system, user, schema, temperature, sample)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            try:
                cached = result_from_payload(json.loads(path.read_text(encoding="utf-8")), schema,
                                             cached=True)
            except (OSError, ValueError):
                cached = None
            if cached is not None and cached.ok:
                return cached
        result = self.inner.complete_json(system, user, schema, task=task,
                                          temperature=temperature, sample=sample,
                                          context=context)
        if result.ok:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            payload = result_payload(result, request_hash=key, schema_name=schema.__name__,
                                     configured_model=self.inner.model)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(_dump(payload), encoding="utf-8")
            tmp.replace(path)
        return result


class ReplayProvider(LLMProvider):
    """Reproduz respostas gravadas no ledger; resposta ausente ⇒ erro explícito (sem regenerar).

    Nome, modelo configurado e determinismo são inferidos das respostas gravadas (precisam ser
    iguais aos da execução original para que os ``request_sha256`` coincidam). Cada resposta é
    conferida contra o registro do ledger antes de ser servida (hash do texto bruto, desfecho
    erro/sucesso) e é sempre REINTERPRETADA a partir do texto bruto: um ``parsed`` adulterado
    no arquivo nunca é servido. ``week`` restringe o replay às chamadas daquela semana.
    """

    def __init__(self, ledger_dir: str | Path, name: str | None = None, model: str | None = None,
                 deterministic: bool | None = None, week: date | None = None) -> None:
        self.ledger = LLMCallLedger(ledger_dir)
        records = [r for r in self.ledger.records() if week is None or r.week == week]
        self._records: dict[str, LLMCallRecord] = {}
        self._index: dict[str, str] = {}
        for r in records:  # o mais recente prevalece (mesma regra do raw_index)
            self._records[r.request_sha256] = r
            if r.raw_response_path:
                self._index[r.request_sha256] = r.raw_response_path
        self.recorded_at = records[-1].created_at if records else None
        """Carimbo da execução gravada mais recente (o orquestrador o reutiliza no replay)."""
        first = self._first_payload()
        self.name = name or (str(first.get("provider")) if first else "replay")
        self.model = model if model is not None else (first.get("configured_model")
                                                      if first else None)
        self.deterministic = (deterministic if deterministic is not None
                              else bool(first.get("deterministic", True)) if first else True)

    def _first_payload(self) -> dict[str, Any] | None:
        for key in sorted(self._index):
            payload = self.ledger.load_raw(key, self._index)
            if payload is not None:
                return payload
        return None

    def _fail(self, message: str, payload: dict[str, Any] | None = None) -> LLMResult:
        raw = payload.get("raw_text") if payload else None
        return error_result(self.name, self.model, message, deterministic=self.deterministic,
                            raw_text=raw if isinstance(raw, str) else None,
                            stop_reason=payload.get("stop_reason") if payload else None)

    def complete_json(self, system: str, user: str, schema: type[BaseModel], *, task: str,
                      temperature: float = 0.0, sample: int = 0,
                      context: dict | None = None) -> LLMResult:
        key = request_sha256(self.name, self.model, system, user, schema.__name__, temperature,
                             sample)
        record = self._records.get(key)
        payload = self.ledger.load_raw(key, self._index) if record is not None else None
        if record is None or payload is None:
            return self._fail(f"Replay sem resposta gravada para request_sha256={key} "
                              f"(tarefa {task}); reexecução não é permitida.")
        if payload.get("schema_name") not in (None, schema.__name__):
            return self._fail(f"Replay: schema gravado {payload.get('schema_name')} difere de "
                              f"{schema.__name__}.")
        problem = payload_integrity(payload, record)
        if problem:
            return self._fail(f"Replay recusado: {problem}.")
        if payload.get("error") is not None:
            result = result_from_payload(payload, schema)
        elif isinstance(payload.get("raw_text"), str):
            # Fonte da verdade = texto bruto (o ``parsed`` gravado é só conveniência).
            result = result_from_payload({**payload, "parsed": None}, schema)
            stored = payload.get("parsed")
            if (result.ok and stored is not None
                    and stored != result.parsed.model_dump(mode="json")):  # type: ignore[union-attr]
                return self._fail("Replay recusado: objeto interpretado gravado difere do texto "
                                  "bruto (adulteração).", payload)
        else:
            result = result_from_payload(payload, schema)
        result.provider = self.name
        result.deterministic = self.deterministic
        return result
