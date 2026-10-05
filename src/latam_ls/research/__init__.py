"""Camada de pesquisa com IA generativa (padrão "centauro").

Agentes de LLM transformam informação não estruturada em juízos qualitativos validados por
schema e com citações; código determinístico calcula todos os números (FactBook), o otimizador
constrói o livro e o gestor humano aprova. Ver docs/latam_ls/ARQUITETURA.md §9.
"""

from __future__ import annotations

from .agents import (
    AI_LABEL,
    CALCULATED_LABEL,
    GateResult,
    ResearchOrchestrator,
    ResearchRequest,
    ResearchRun,
    merge_views,
    notes_to_views,
    provenance_label,
    research_hash_with_ledger,
    rule_short_verdict,
    rule_views,
    run_research,
    sign_agreement_gate,
)
from .evaluation import ViewTracker, evaluate_golden_set, load_golden_cases
from .factbook import build_factbook, facts_for_issuer, render_facts_block
from .guardrails import (
    INJECTION_PATTERNS,
    ai_kill_switch,
    check_placeholders,
    detect_injection,
    find_free_numbers,
    render_placeholders,
    sanitize_untrusted,
    verify_analyst_output,
    verify_macro_output,
    verify_news_output,
    verify_short_risk_output,
)
from .prompts import PROMPT_VERSION
from .providers import (
    AnthropicResearchProvider,
    CachedProvider,
    DemoResearchProvider,
    LLMCallLedger,
    LLMProvider,
    LLMResult,
    OpenRouterResearchProvider,
    ReplayProvider,
    get_provider,
    load_imported_pack,
)

__all__ = [
    "AI_LABEL",
    "CALCULATED_LABEL",
    "INJECTION_PATTERNS",
    "PROMPT_VERSION",
    "AnthropicResearchProvider",
    "CachedProvider",
    "DemoResearchProvider",
    "GateResult",
    "LLMCallLedger",
    "LLMProvider",
    "LLMResult",
    "OpenRouterResearchProvider",
    "ReplayProvider",
    "ResearchOrchestrator",
    "ResearchRequest",
    "ResearchRun",
    "ViewTracker",
    "ai_kill_switch",
    "build_factbook",
    "check_placeholders",
    "detect_injection",
    "evaluate_golden_set",
    "facts_for_issuer",
    "find_free_numbers",
    "get_provider",
    "load_golden_cases",
    "load_imported_pack",
    "merge_views",
    "notes_to_views",
    "provenance_label",
    "render_facts_block",
    "render_placeholders",
    "research_hash_with_ledger",
    "rule_short_verdict",
    "rule_views",
    "run_research",
    "sanitize_untrusted",
    "sign_agreement_gate",
    "verify_analyst_output",
    "verify_macro_output",
    "verify_news_output",
    "verify_short_risk_output",
]
