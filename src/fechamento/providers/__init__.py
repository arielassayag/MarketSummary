"""Módulo de provedores de narrativa para o AI Notes #8."""

from .base import NarrativeProvider, NarrativeRequest, NarrativeResult
from .demo_provider import DemoProvider
from .gemini_provider import GeminiProvider
from .openrouter_provider import OpenRouterProvider, get_recommended_free_models

__all__ = [
    "NarrativeProvider",
    "NarrativeRequest",
    "NarrativeResult",
    "DemoProvider",
    "GeminiProvider",
    "OpenRouterProvider",
    "get_recommended_free_models",
]
