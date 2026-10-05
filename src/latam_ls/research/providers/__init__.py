"""Provedores de LLM da camada de pesquisa (demo, Anthropic, OpenRouter, importado, replay).

Nenhum identificador de modelo é fixado em código: provedores reais leem o modelo de
variáveis de ambiente. O provedor ``demo`` é determinístico e offline.
"""

from __future__ import annotations

from typing import Any

from .anthropic_provider import AnthropicResearchProvider
from .base import (
    LLMProvider,
    LLMResult,
    error_result,
    parse_json_payload,
    request_sha256,
    strict_json_schema,
)
from .cache import CachedProvider, LLMCallLedger, ReplayProvider, calls_digest
from .demo import DEMO_MODEL_LABEL, DemoResearchProvider
from .imported import IMPORTED_PREFIX, load_imported_pack
from .openrouter_provider import OpenRouterResearchProvider


def get_provider(name: str, **kwargs: Any) -> LLMProvider:
    """Instancia o provedor pelo nome da configuração (``research.provider``).

    ``imported`` não é um provedor de chamadas: use :func:`load_imported_pack`.
    """
    key = (name or "").strip().lower()
    if key == "demo":
        return DemoResearchProvider()
    if key == "anthropic":
        return AnthropicResearchProvider(**kwargs)
    if key == "openrouter":
        return OpenRouterResearchProvider(**kwargs)
    if key == "imported":
        raise ValueError("O provedor 'imported' carrega notas externas: use load_imported_pack().")
    raise ValueError(f"Provedor de pesquisa desconhecido: {name!r}")


__all__ = [
    "DEMO_MODEL_LABEL",
    "IMPORTED_PREFIX",
    "AnthropicResearchProvider",
    "CachedProvider",
    "DemoResearchProvider",
    "LLMCallLedger",
    "LLMProvider",
    "LLMResult",
    "OpenRouterResearchProvider",
    "ReplayProvider",
    "calls_digest",
    "error_result",
    "get_provider",
    "load_imported_pack",
    "parse_json_payload",
    "request_sha256",
    "strict_json_schema",
]
