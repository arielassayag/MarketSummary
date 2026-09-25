"""Interface base para provedores de narrativa de fechamento de mercado."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..contracts import CommentaryDraft, FactBook, NewsItem


@dataclass(frozen=True)
class NarrativeRequest:
    factbook: FactBook
    eligible_news: list[NewsItem]
    style_instructions: str = (
        "Comentário profissional para investidores institucionais, tom sóbrio e factual, "
        "sem adjetivos vazios ou recomendações de compra/venda. Aproximadamente 180-300 palavras."
    )
    target_words_min: int = 180
    target_words_max: int = 300


@dataclass(frozen=True)
class NarrativeResult:
    draft: CommentaryDraft | None = None
    raw_response: str | None = None
    latency_ms: float = 0.0
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None
    provider_name: str = ""
    model_name: str | None = None
    is_deterministic: bool = True
    error_message: str | None = None

    @property
    def success(self) -> bool:
        return self.draft is not None and self.error_message is None


class NarrativeProvider(ABC):
    @abstractmethod
    def generate(self, request: NarrativeRequest) -> NarrativeResult:
        """Gera o rascunho estruturado do comentário a partir do FactBook e das notícias elegíveis."""
        pass
