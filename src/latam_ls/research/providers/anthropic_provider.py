"""Provedor Anthropic (SDK oficial ``anthropic``, dependência opcional do extra ``ai``).

Configuração exclusivamente por ambiente (nenhum identificador de modelo no código):

- ``ANTHROPIC_API_KEY`` — chave da API;
- ``LATAM_LS_ANTHROPIC_MODEL`` — ID COMPLETO do snapshot do modelo (sem aliases); sem ele a
  chamada devolve erro em português e a pesquisa se abstém;
- ``LATAM_LS_ANTHROPIC_MAX_TOKENS`` (padrão 4096), ``LATAM_LS_ANTHROPIC_EFFORT`` (opcional,
  ``low``…``max``), ``LATAM_LS_ANTHROPIC_TEMPERATURE`` (opcional — só é enviada se configurada:
  modelos recentes rejeitam temperatura não padrão com erro 400);
- ``LATAM_LS_ANTHROPIC_PRICE_IN_PER_MTOK`` / ``LATAM_LS_ANTHROPIC_PRICE_OUT_PER_MTOK``
  (opcionais, USD por milhão de tokens) para estimar o custo.

Desenho (docs/research/07 §5.2 e §5.6):

- saída forçada no schema por *structured outputs* (``output_config.format`` com
  ``json_schema``); intervalos (stance −2…+2 etc.) validados em código pelo Pydantic. Não se usa
  ``tool_choice`` forçado (rejeitado por modelos recentes) nem a API de *citations*
  (incompatível com structured outputs) — os ids de evidência vivem em campos do schema e são
  verificados pelos guardrails;
- o prompt de sistema longo e estável por papel recebe ``cache_control`` (cache de prompt);
- ``stop_reason == "refusal"`` ou ``"max_tokens"`` ⇒ erro (sem parsing de saída parcial);
- não há *fallback* automático de modelo: troca de modelo é mudança de versão que exige
  revalidação; se o modelo servido diferir do configurado, o resultado é rejeitado;
- *retries* de 408/409/429/5xx e erros de conexão ficam com o SDK (``max_retries``).
"""

from __future__ import annotations

import os
import time
from typing import Any

from pydantic import BaseModel

from .base import LLMProvider, LLMResult, error_result, parse_json_payload, strict_json_schema

ENV_API_KEY = "ANTHROPIC_API_KEY"
ENV_MODEL = "LATAM_LS_ANTHROPIC_MODEL"
ENV_MAX_TOKENS = "LATAM_LS_ANTHROPIC_MAX_TOKENS"
ENV_EFFORT = "LATAM_LS_ANTHROPIC_EFFORT"
ENV_TEMPERATURE = "LATAM_LS_ANTHROPIC_TEMPERATURE"
ENV_PRICE_IN = "LATAM_LS_ANTHROPIC_PRICE_IN_PER_MTOK"
ENV_PRICE_OUT = "LATAM_LS_ANTHROPIC_PRICE_OUT_PER_MTOK"
DEFAULT_MAX_TOKENS = 4096
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1
VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _describe_error(exc: Exception) -> str:
    """Mensagem em português por tipo de falha do SDK (mais específico primeiro)."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - SDK ausente
        anthropic = None  # type: ignore[assignment]
    if anthropic is not None:
        checks = [
            ("AuthenticationError", "autenticação recusada (verifique ANTHROPIC_API_KEY)"),
            ("PermissionDeniedError", "chave sem permissão para o modelo/recurso"),
            ("NotFoundError", "modelo ou recurso inexistente (verifique o ID do snapshot)"),
            ("RateLimitError", "limite de requisições excedido após as tentativas do SDK"),
            ("BadRequestError", "requisição inválida"),
            ("APITimeoutError", "tempo esgotado"),
            ("APIConnectionError", "falha de conexão com a API"),
            ("APIStatusError", "erro de status da API"),
        ]
        for cls_name, text in checks:
            cls = getattr(anthropic, cls_name, None)
            if isinstance(cls, type) and isinstance(exc, cls):
                status = getattr(exc, "status_code", None)
                suffix = f" (HTTP {status})" if status else ""
                return f"Anthropic: {text}{suffix}: {exc}"
    return f"Anthropic: falha na chamada ({type(exc).__name__}): {exc}"


class AnthropicResearchProvider(LLMProvider):
    """Saídas JSON estruturadas via Messages API com *structured outputs*.

    ``client`` permite injetar um cliente compatível (testes usam um *mock*, sem rede).
    """

    name = "anthropic"
    deterministic = False

    def __init__(self, model: str | None = None, api_key: str | None = None, client: Any = None,
                 max_tokens: int | None = None, temperature: float | None = None,
                 effort: str | None = None, timeout: float = 120.0, max_retries: int = 2,
                 cache_system_prompt: bool = True, price_in_per_mtok: float | None = None,
                 price_out_per_mtok: float | None = None) -> None:
        self.model = (model or os.environ.get(ENV_MODEL, "")).strip() or None
        self._api_key = (api_key or os.environ.get(ENV_API_KEY, "")).strip() or None
        self._client = client
        env_max = _env_float(ENV_MAX_TOKENS)
        self.max_tokens = int(max_tokens or env_max or DEFAULT_MAX_TOKENS)
        self.temperature = temperature if temperature is not None else _env_float(ENV_TEMPERATURE)
        eff = (effort or os.environ.get(ENV_EFFORT, "")).strip().lower() or None
        self.effort = eff if eff in VALID_EFFORTS else None
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_system_prompt = cache_system_prompt
        self.price_in = price_in_per_mtok if price_in_per_mtok is not None else _env_float(ENV_PRICE_IN)
        self.price_out = (price_out_per_mtok if price_out_per_mtok is not None
                          else _env_float(ENV_PRICE_OUT))

    # ------------------------------------------------------------------ cliente
    def _get_client(self) -> tuple[Any, str | None]:
        if self._client is not None:
            return self._client, None
        if not self._api_key:
            return None, (f"Chave {ENV_API_KEY} não configurada; a pesquisa com o provedor "
                          "Anthropic fica indisponível (abstenção).")
        try:
            import anthropic
        except ImportError:
            return None, ("SDK 'anthropic' não instalado; instale o extra opcional "
                          "('uv sync --extra ai').")
        self._client = anthropic.Anthropic(api_key=self._api_key, timeout=self.timeout,
                                           max_retries=self.max_retries)
        return self._client, None

    def build_request(self, system: str, user: str, schema: type[BaseModel]) -> dict[str, Any]:
        """Parâmetros da chamada ``messages.create`` (sem temperatura se não configurada)."""
        system_block: dict[str, Any] = {"type": "text", "text": system}
        if self.cache_system_prompt:
            system_block["cache_control"] = {"type": "ephemeral"}
        output_config: dict[str, Any] = {
            "format": {"type": "json_schema", "schema": strict_json_schema(schema)},
        }
        if self.effort:
            output_config["effort"] = self.effort
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [system_block],
            "messages": [{"role": "user", "content": user}],
            "output_config": output_config,
        }
        if self.temperature is not None:
            params["temperature"] = float(self.temperature)
        return params

    def _usage(self, response: Any) -> dict | None:
        usage = _get(response, "usage")
        if usage is None:
            return None
        out = {}
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                    "cache_read_input_tokens"):
            v = _get(usage, key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[key] = int(v)
        return out or None

    def _cost(self, usage: dict | None) -> float | None:
        if not usage or self.price_in is None or self.price_out is None:
            return None
        tin = usage.get("input_tokens", 0)
        cw = usage.get("cache_creation_input_tokens", 0)
        cr = usage.get("cache_read_input_tokens", 0)
        tout = usage.get("output_tokens", 0)
        cost = (tin * self.price_in + cw * self.price_in * CACHE_WRITE_MULTIPLIER
                + cr * self.price_in * CACHE_READ_MULTIPLIER + tout * self.price_out) / 1e6
        return round(cost, 8)

    # ------------------------------------------------------------------ chamada
    def complete_json(self, system: str, user: str, schema: type[BaseModel], *, task: str,
                      temperature: float = 0.0, sample: int = 0,
                      context: dict | None = None) -> LLMResult:
        if not self.model:
            return error_result(self.name, None,
                                f"Modelo Anthropic não configurado: defina {ENV_MODEL} com o ID "
                                "completo do snapshot (aliases não são aceitos).")
        client, problem = self._get_client()
        if problem:
            return error_result(self.name, self.model, problem)
        params = self.build_request(system, user, schema)
        start = time.perf_counter()
        try:
            response = client.messages.create(**params)
        except Exception as exc:  # noqa: BLE001 — falha do provedor vira abstenção
            return error_result(self.name, self.model, _describe_error(exc),
                                latency_ms=(time.perf_counter() - start) * 1000.0)
        latency = (time.perf_counter() - start) * 1000.0
        usage = self._usage(response)
        cost = self._cost(usage)
        stop = _get(response, "stop_reason")
        served = _get(response, "model")
        texts = [_get(b, "text") for b in (_get(response, "content") or [])
                 if _get(b, "type") == "text"]
        raw_text = "".join(t for t in texts if isinstance(t, str)) or None
        common = {"latency_ms": latency, "raw_text": raw_text, "usage": usage, "cost_usd": cost,
                  "stop_reason": stop}
        if stop == "refusal":
            details = _get(response, "stop_details")
            category = _get(details, "category")
            return error_result(self.name, self.model,
                                f"Recusa do modelo (stop_reason=refusal, categoria={category}).",
                                **common)
        if stop == "max_tokens":
            return error_result(self.name, self.model,
                                "Resposta truncada por max_tokens; saída descartada.", **common)
        if served and served != self.model:
            return error_result(self.name, self.model,
                                f"Modelo servido ({served}) difere do configurado ({self.model}); "
                                "troca automática de modelo não é permitida.", **common)
        parsed, err = parse_json_payload(raw_text, schema)
        return LLMResult(parsed=parsed, raw_text=raw_text, provider=self.name, model=self.model,
                         latency_ms=latency, usage=usage, cost_usd=cost, error=err,
                         deterministic=False, stop_reason=stop)
