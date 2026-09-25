"""Cliente OpenRouter via SDK oficial OpenAI (sem framework).

- base_url https://openrouter.ai/api/v1
- timeout configurável; retry exponencial com jitter para 429/5xx/conexão;
- erros de autenticação e 4xx são terminais (sem retry);
- registra usage, custo (usage.cost do OpenRouter), latência e finish reasons;
- nunca registra a chave da API.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

from .logging_utils import log_event

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class GenerationResult:
    ok: bool
    content: str | None = None
    error_kind: str | None = None
    error_detail: str | None = None
    response_id: str | None = None
    model_returned: str | None = None
    system_fingerprint: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    finish_reason: str | None = None
    native_finish_reason: str | None = None
    attempt: int | None = None
    warnings: list[str] = field(default_factory=list)


def _extract_usage(resp: object) -> dict[str, object]:
    usage = getattr(resp, "usage", None)
    out: dict[str, object] = {}
    if usage is None:
        return out
    for target, attr in [
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ]:
        val = getattr(usage, attr, None)
        if val is not None:
            out[target] = int(val)
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None) if details is not None else None
    if reasoning is not None:
        out["reasoning_tokens"] = int(reasoning)
    extra = getattr(usage, "model_extra", None) or {}
    cost = extra.get("cost") if isinstance(extra, dict) else None
    if cost is None:
        cost = getattr(usage, "cost", None)
    if cost is not None:
        out["cost_usd"] = float(cost)
    return out


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        site_url: str = "",
        app_name: str = "AI Notes Market Close Eval",
        timeout_s: float = 120.0,
        max_attempts: int = 5,
        backoff_base_s: float = 1.5,
    ) -> None:
        headers = {}
        if site_url:
            headers["HTTP-Referer"] = site_url
        if app_name:
            headers["X-OpenRouter-Title"] = app_name
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers=headers,
            timeout=timeout_s,
            max_retries=0,  # retry é controlado aqui (backoff próprio)
        )
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base_s

    def _response_format(self, response_mode: str, schema: dict[str, object] | None, name: str) -> dict[str, object] | None:
        if response_mode == "json_schema":
            if schema is None:
                raise ValueError("response_mode=json_schema exige schema")
            return {
                "type": "json_schema",
                "json_schema": {"name": name, "strict": True, "schema": schema},
            }
        if response_mode == "json_object":
            return {"type": "json_object"}
        return None

    async def generate(
        self,
        *,
        model_id: str,
        system: str,
        user: str,
        response_mode: str = "json_schema",
        schema: dict[str, object] | None = None,
        schema_name: str = "response",
        temperature: float = 0.0,
        top_p: float = 1.0,
        max_tokens: int = 2000,
        seed: int | None = None,
        reasoning_effort: str | None = None,
    ) -> GenerationResult:
        rf = self._response_format(response_mode, schema, schema_name)
        params: dict[str, object] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if rf is not None:
            params["response_format"] = rf
        if seed is not None:
            params["seed"] = seed
        extra: dict[str, object] = {"usage": {"include": True}}
        if reasoning_effort == "none":
            # desliga o modo de raciocínio em modelos híbridos (ex.: DeepSeek)
            extra["reasoning"] = {"enabled": False}
        elif reasoning_effort:
            extra["reasoning"] = {"effort": reasoning_effort}
        params["extra_body"] = extra

        last_error: str | None = None
        last_kind: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            started = time.monotonic()
            try:
                resp = await self._client.chat.completions.create(**params)  # type: ignore[call-overload]
            except (AuthenticationError, PermissionDeniedError) as exc:
                return GenerationResult(ok=False, error_kind="auth_error", error_detail=str(exc), attempt=attempt)
            except BadRequestError as exc:
                # alguns provedores rejeitam o parâmetro unificado `reasoning`;
                # remove e tenta de novo (sem substituir modelo nem mudar schema)
                extra_now = params.get("extra_body")
                if isinstance(extra_now, dict) and "reasoning" in extra_now:
                    stripped: dict[str, object] = dict(extra_now)
                    stripped.pop("reasoning")
                    params["extra_body"] = stripped
                    log_event(logger, "reasoning_param_rejected", model=model_id, attempt=attempt)
                    if attempt < self.max_attempts:
                        continue
                return GenerationResult(ok=False, error_kind="bad_request", error_detail=str(exc), attempt=attempt)
            except (RateLimitError, APIConnectionError, APITimeoutError, APIStatusError) as exc:
                retryable = isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)) or (
                    isinstance(exc, APIStatusError) and exc.status_code is not None and exc.status_code >= 500
                )
                if not retryable:
                    return GenerationResult(ok=False, error_kind="api_error", error_detail=str(exc), attempt=attempt)
                last_error, last_kind = str(exc), "retryable"
                if attempt < self.max_attempts:
                    delay = self.backoff_base * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    log_event(logger, "retry", model=model_id, attempt=attempt, delay_s=round(delay, 2))
                    await asyncio.sleep(delay)
                continue
            except Exception as exc:  # noqa: BLE001
                last_error, last_kind = str(exc), "unexpected"
                if attempt < self.max_attempts:
                    await asyncio.sleep(self.backoff_base)
                continue

            latency_ms = int((time.monotonic() - started) * 1000)
            choice = resp.choices[0] if resp.choices else None
            message_content = getattr(choice.message, "content", None) if choice is not None else None
            usage = _extract_usage(resp)
            finish = str(getattr(choice, "finish_reason", None) or "") if choice is not None else None
            choice_extra = getattr(choice, "model_extra", None) or {}
            native_finish = choice_extra.get("native_finish_reason") if isinstance(choice_extra, dict) else None
            warnings: list[str] = []
            if finish and finish not in ("stop", "end_turn"):
                warnings.append(f"finish_reason={finish}")
            return GenerationResult(
                ok=True,
                content=message_content if isinstance(message_content, str) else None,
                response_id=getattr(resp, "id", None),
                model_returned=getattr(resp, "model", None),
                system_fingerprint=getattr(resp, "system_fingerprint", None),
                latency_ms=latency_ms,
                finish_reason=finish,
                native_finish_reason=str(native_finish) if native_finish else None,
                attempt=attempt,
                warnings=warnings,
                prompt_tokens=usage.get("prompt_tokens"),  # type: ignore[arg-type]
                completion_tokens=usage.get("completion_tokens"),  # type: ignore[arg-type]
                reasoning_tokens=usage.get("reasoning_tokens"),  # type: ignore[arg-type]
                total_tokens=usage.get("total_tokens"),  # type: ignore[arg-type]
                cost_usd=usage.get("cost_usd"),  # type: ignore[arg-type]
            )

        return GenerationResult(
            ok=False,
            error_kind="retry_exhausted" if last_kind == "retryable" else (last_kind or "unknown"),
            error_detail=last_error,
            attempt=self.max_attempts,
        )
