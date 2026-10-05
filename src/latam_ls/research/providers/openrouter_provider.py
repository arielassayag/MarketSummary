"""Provedor OpenRouter (API compatível com OpenAI via ``urllib``; sem dependência extra).

- Endpoint: ``https://openrouter.ai/api/v1/chat/completions``.
- Chave: ``OPENROUTER_API_KEY``; modelo: ``LATAM_LS_OPENROUTER_MODEL`` (padrão
  ``openrouter/free``, o roteador gratuito; nesse caso o pedido exige preço máximo zero e
  ``require_parameters`` para só usar provedores que respeitam o ``json_schema``).
- Saída forçada por ``response_format = {"type": "json_schema", ...}`` em modo estrito; o
  resultado ainda é validado pelo Pydantic e pelos guardrails.
- O modelo efetivamente servido (campo ``model`` da resposta) é registrado no resultado.
- Reenvia em 429/5xx (``max_retries``) com espera exponencial; demais erros viram ``error``.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from .base import LLMProvider, LLMResult, error_result, parse_json_payload, strict_json_schema

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
ENV_API_KEY = "OPENROUTER_API_KEY"
ENV_MODEL = "LATAM_LS_OPENROUTER_MODEL"
DEFAULT_MODEL = "openrouter/free"
RETRY_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})
DEFAULT_MAX_TOKENS = 4096


def _is_free_route(model: str) -> bool:
    return model == DEFAULT_MODEL or model.endswith(":free")


class OpenRouterResearchProvider(LLMProvider):
    """Saídas JSON estruturadas via OpenRouter. ``opener``/``sleep`` injetáveis para testes."""

    name = "openrouter"
    deterministic = False

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 timeout: float = 90.0, max_retries: int = 2, max_tokens: int = DEFAULT_MAX_TOKENS,
                 site_url: str = "https://github.com/arielassayag/MarketSummary",
                 app_name: str = "CDP — Cabra da Peste (pesquisa)",
                 opener: Callable[..., Any] | None = None,
                 sleep: Callable[[float], None] | None = None) -> None:
        self.model = (model or os.environ.get(ENV_MODEL, "")).strip() or DEFAULT_MODEL
        self._api_key = (api_key or os.environ.get(ENV_API_KEY, "")).strip() or None
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.max_tokens = int(max_tokens)
        self.site_url = site_url
        self.app_name = app_name
        self._opener = opener
        self._sleep = sleep or time.sleep

    def build_payload(self, system: str, user: str, schema: type[BaseModel],
                      temperature: float) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "strict": True,
                                "schema": strict_json_schema(schema, all_required=True)},
            },
            "temperature": float(temperature),
            "max_tokens": self.max_tokens,
        }
        if _is_free_route(self.model):
            payload["provider"] = {"max_price": {"prompt": 0, "completion": 0},
                                   "require_parameters": True}
        return payload

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            OPENROUTER_API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self._api_key}",
                     "Content-Type": "application/json", "HTTP-Referer": self.site_url,
                     "X-Title": self.app_name})
        opener = self._opener or urllib.request.urlopen
        with opener(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def complete_json(self, system: str, user: str, schema: type[BaseModel], *, task: str,
                      temperature: float = 0.0, sample: int = 0,
                      context: dict | None = None) -> LLMResult:
        if not self._api_key:
            return error_result(self.name, self.model,
                                f"Chave {ENV_API_KEY} não configurada; a pesquisa com o provedor "
                                "OpenRouter fica indisponível (abstenção).")
        payload = self.build_payload(system, user, schema, temperature)
        start = time.perf_counter()
        body: dict[str, Any] | None = None
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                body = self._post(payload)
                break
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}: {exc.reason}"
                if exc.code not in RETRY_STATUS or attempt == self.max_retries:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = f"falha de conexão: {exc}"
                if attempt == self.max_retries:
                    break
            except json.JSONDecodeError as exc:
                last_error = f"resposta não-JSON do gateway: {exc.msg}"
                break
            self._sleep(min(8.0, 0.5 * (2 ** attempt)))
        latency = (time.perf_counter() - start) * 1000.0
        if body is None:
            return error_result(self.name, self.model, f"OpenRouter: {last_error}",
                                latency_ms=latency)

        usage_raw = body.get("usage") or {}
        usage = {k: int(v) for k, v in usage_raw.items()
                 if k in ("prompt_tokens", "completion_tokens", "total_tokens")
                 and isinstance(v, (int, float)) and not isinstance(v, bool)} or None
        cost = usage_raw.get("cost")
        cost = float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None
        served = body.get("model") or self.model
        choices = body.get("choices") or []
        if not choices:
            message = (body.get("error") or {}).get("message", "sem 'choices' na resposta")
            return error_result(self.name, served, f"OpenRouter: {message}", latency_ms=latency,
                                usage=usage, cost_usd=cost)
        choice = choices[0] or {}
        finish = choice.get("finish_reason")
        msg = choice.get("message") or {}
        raw_text = msg.get("content") if isinstance(msg.get("content"), str) else None
        common = {"latency_ms": latency, "raw_text": raw_text, "usage": usage, "cost_usd": cost,
                  "stop_reason": finish}
        if msg.get("refusal"):
            return error_result(self.name, served, f"Recusa do modelo: {msg['refusal']}", **common)
        if finish == "length":
            return error_result(self.name, served,
                                "Resposta truncada por limite de tokens; saída descartada.",
                                **common)
        parsed, err = parse_json_payload(raw_text, schema)
        return LLMResult(parsed=parsed, raw_text=raw_text, provider=self.name, model=served,
                         latency_ms=latency, usage=usage, cost_usd=cost, error=err,
                         deterministic=False, stop_reason=finish)
