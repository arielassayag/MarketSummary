"""Interface comum dos provedores de LLM da camada de pesquisa.

Todo provedor devolve um :class:`LLMResult` — nunca levanta exceção por falha do modelo ou da
rede (o erro vai em ``error`` e o orquestrador converte em abstenção). A saída precisa ser JSON
validado contra um schema Pydantic (``parsed``); o texto bruto é preservado para o ledger de
chamadas (reprodutibilidade por *replay*, nunca por regeneração).

Nenhum identificador de modelo é fixado em código: modelos vêm de variáveis de ambiente ou da
configuração.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from ...hashing import sha256_obj

SUPPORTED_STRING_FORMATS = frozenset({
    "date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid",
})
_UNSUPPORTED_SCHEMA_KEYS = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength",
    "maxLength", "pattern", "maxItems", "uniqueItems", "minProperties", "maxProperties",
    "default", "examples",
})
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass
class LLMResult:
    """Resultado de uma chamada (bem-sucedida ou não) a um provedor."""

    parsed: BaseModel | None
    raw_text: str | None
    provider: str
    model: str | None
    latency_ms: float
    usage: dict | None
    cost_usd: float | None
    error: str | None
    deterministic: bool
    stop_reason: str | None = None
    cached: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and self.parsed is not None


class LLMProvider(ABC):
    """Provedor de saídas JSON estruturadas.

    ``context`` carrega os insumos estruturados da tarefa (fatos, emissor, notícias já
    sanitizadas). O provedor demo trabalha só com ele (sem interpretar o prompt); provedores
    reais usam ``system``/``user``.
    """

    name: str = "base"
    model: str | None = None
    deterministic: bool = False

    @abstractmethod
    def complete_json(self, system: str, user: str, schema: type[BaseModel], *, task: str,
                      temperature: float = 0.0, sample: int = 0,
                      context: dict | None = None) -> LLMResult:
        """Executa a tarefa e devolve a saída validada contra ``schema``."""


def request_sha256(provider: str, model: str | None, system: str, user: str, schema_name: str,
                   temperature: float, sample: int) -> str:
    """Hash canônico da requisição (chave do cache, do ledger e do replay)."""
    return sha256_obj({
        "provider": provider, "model": model, "system": system, "user": user,
        "schema": schema_name, "temperature": float(temperature), "sample": int(sample),
    })


def error_result(provider: str, model: str | None, message: str, *, deterministic: bool = False,
                 latency_ms: float = 0.0, raw_text: str | None = None,
                 usage: dict | None = None, cost_usd: float | None = None,
                 stop_reason: str | None = None) -> LLMResult:
    return LLMResult(parsed=None, raw_text=raw_text, provider=provider, model=model,
                     latency_ms=latency_ms, usage=usage, cost_usd=cost_usd, error=message,
                     deterministic=deterministic, stop_reason=stop_reason)


def _extract_json_text(raw_text: str) -> str:
    text = _FENCE_RE.sub("", raw_text.strip()).strip()
    if text.startswith("{"):
        return text
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text


def parse_json_payload(raw_text: str | None,
                       schema: type[BaseModel]) -> tuple[BaseModel | None, str | None]:
    """Extrai e valida o objeto JSON da resposta. Retorna ``(objeto, erro)``."""
    if raw_text is None or not str(raw_text).strip():
        return None, "Resposta vazia do modelo."
    try:
        data = json.loads(_extract_json_text(str(raw_text)))
    except json.JSONDecodeError as exc:
        return None, f"JSON inválido na resposta: {exc.msg} (posição {exc.pos})."
    if not isinstance(data, dict):
        return None, "A resposta não é um objeto JSON."
    try:
        return schema.model_validate(data), None
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                            for e in exc.errors()[:8])
        return None, f"Resposta fora do schema {schema.__name__}: {details}"


def _walk_schema(node: Any, all_required: bool) -> Any:
    if isinstance(node, list):
        return [_walk_schema(x, all_required) for x in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
            out[key] = {k: _walk_schema(v, all_required) for k, v in value.items()}
            continue
        if key in _UNSUPPORTED_SCHEMA_KEYS:
            continue
        if key == "minItems" and value not in (0, 1):
            continue
        if key == "format" and value not in SUPPORTED_STRING_FORMATS:
            continue
        out[key] = _walk_schema(value, all_required)
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        if all_required and isinstance(out.get("properties"), dict):
            out["required"] = list(out["properties"])
    return out


def strict_json_schema(schema: type[BaseModel] | dict, all_required: bool = False) -> dict:
    """JSON schema aceito por *structured outputs* (restrições numéricas/tamanho removidas).

    Intervalos (``stance`` −2…+2 etc.) continuam validados em código pelo Pydantic.
    ``all_required`` lista todas as propriedades em ``required`` (modo estrito estilo OpenAI).
    """
    raw = schema.model_json_schema() if isinstance(schema, type) else dict(schema)
    return _walk_schema(raw, all_required)


def result_payload(result: LLMResult, *, request_hash: str, schema_name: str,
                   configured_model: str | None) -> dict[str, Any]:
    """Representação gravável (JSON) de um resultado — usada no ledger, cache e replay."""
    return {
        "request_sha256": request_hash,
        "schema_name": schema_name,
        "provider": result.provider,
        "configured_model": configured_model,
        "model": result.model,
        "deterministic": result.deterministic,
        "raw_text": result.raw_text,
        "parsed": None if result.parsed is None else result.parsed.model_dump(mode="json"),
        "stop_reason": result.stop_reason,
        "usage": result.usage,
        "cost_usd": result.cost_usd,
        "error": result.error,
    }


def result_from_payload(payload: dict[str, Any], schema: type[BaseModel], *,
                        cached: bool = False) -> LLMResult:
    """Reconstrói um :class:`LLMResult` a partir do payload gravado (revalida o schema)."""
    parsed: BaseModel | None = None
    error = payload.get("error")
    if error is None:
        if payload.get("parsed") is not None:
            try:
                parsed = schema.model_validate(payload["parsed"])
            except ValidationError as exc:
                error = f"Resposta gravada fora do schema {schema.__name__}: {exc.error_count()} erro(s)."
        else:
            parsed, error = parse_json_payload(payload.get("raw_text"), schema)
    return LLMResult(
        parsed=parsed, raw_text=payload.get("raw_text"), provider=str(payload.get("provider")),
        model=payload.get("model"), latency_ms=0.0, usage=payload.get("usage"),
        cost_usd=payload.get("cost_usd"), error=error,
        deterministic=bool(payload.get("deterministic", False)),
        stop_reason=payload.get("stop_reason"), cached=cached,
    )


def usage_tokens(usage: dict | None) -> tuple[int | None, int | None]:
    """(tokens de entrada, tokens de saída) a partir de ``usage`` em formatos comuns."""
    if not usage:
        return None, None

    def _int(*keys: str) -> int | None:
        for k in keys:
            v = usage.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(v)
        return None

    tin = _int("input_tokens", "prompt_tokens")
    if tin is not None:
        tin += (_int("cache_creation_input_tokens") or 0) + (_int("cache_read_input_tokens") or 0)
    return tin, _int("output_tokens", "completion_tokens")
