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
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ...contracts import LLMCallRecord
from ...hashing import sha256_obj, sha256_text
from .base import (
    LLMProvider,
    LLMResult,
    error_result,
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
        path = self.dir / rel if rel else self.raw_dir / f"{request_hash}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def ledger_hash(self) -> str:
        """SHA-256 de todos os registros (ordem de gravação preservada)."""
        return sha256_obj([r.model_dump(mode="json") for r in self.records()])

    def verify_raw(self) -> list[str]:
        """Confere que cada resposta bruta gravada ainda corresponde ao ``response_sha256``."""
        problems = []
        for r in self.records():
            if not r.raw_response_path:
                continue
            path = self.dir / r.raw_response_path
            if not path.exists():
                problems.append(f"{r.call_id}: resposta bruta ausente ({r.raw_response_path}).")
                continue
            raw_text = json.loads(path.read_text(encoding="utf-8")).get("raw_text")
            got = sha256_text(raw_text) if isinstance(raw_text, str) else None
            if got != r.response_sha256:
                problems.append(f"{r.call_id}: resposta bruta adulterada ({r.raw_response_path}).")
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
    iguais aos da execução original para que os ``request_sha256`` coincidam).
    """

    def __init__(self, ledger_dir: str | Path, name: str | None = None, model: str | None = None,
                 deterministic: bool | None = None) -> None:
        self.ledger = LLMCallLedger(ledger_dir)
        self._index = self.ledger.raw_index()
        first = self._first_payload()
        self.name = name or (str(first.get("provider")) if first else "replay")
        self.model = model if model is not None else (first.get("configured_model")
                                                      if first else None)
        self.deterministic = (deterministic if deterministic is not None
                              else bool(first.get("deterministic", True)) if first else True)

    def _first_payload(self) -> dict[str, Any] | None:
        if not self.ledger.raw_dir.exists():
            return None
        for path in sorted(self.ledger.raw_dir.glob("*.json")):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return None

    def complete_json(self, system: str, user: str, schema: type[BaseModel], *, task: str,
                      temperature: float = 0.0, sample: int = 0,
                      context: dict | None = None) -> LLMResult:
        key = request_sha256(self.name, self.model, system, user, schema.__name__, temperature,
                             sample)
        payload = self.ledger.load_raw(key, self._index)
        if payload is None:
            return error_result(self.name, self.model,
                                f"Replay sem resposta gravada para request_sha256={key} "
                                f"(tarefa {task}); reexecução não é permitida.",
                                deterministic=self.deterministic)
        if payload.get("schema_name") not in (None, schema.__name__):
            return error_result(self.name, self.model,
                                f"Replay: schema gravado {payload.get('schema_name')} difere de "
                                f"{schema.__name__}.", deterministic=self.deterministic)
        result = result_from_payload(payload, schema)
        result.provider = self.name
        result.deterministic = self.deterministic
        return result
