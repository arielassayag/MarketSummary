"""Schemas Pydantic das saídas dos agentes de IA (validação estrita, ``extra='forbid'``).

Os schemas expressam apenas juízos qualitativos/ordinais com ids de evidência. Nenhum campo
expressa ação (aprovar, alterar limite, executar ordem): o pior caso de uma injeção de
instruções é uma visão enviesada, limitada pela regra "IA só aperta" e pela revisão humana.

Regras de texto livre (validadas em código por :mod:`latam_ls.research.guardrails`, não aqui,
para que as violações virem registros auditáveis em vez de falhas de parsing):

- números só como placeholders ``{{fact:<fact_id>}}`` do FactBook (datas ISO como
  ``2026-10-25``, anos e rótulos de trimestre como ``3T26``/``Q3 2026`` são permitidos);
- toda afirmação (``Driver``) cita ao menos um id de evidência existente no pacote da semana.

Intervalos numéricos (``stance`` −2…+2, probabilidades 0…1) são validados aqui pelo Pydantic:
as *structured outputs* da Anthropic não impõem ``minimum``/``maximum``.

A ordem dos campos coloca a fundamentação (tese, drivers) antes dos escores — a literatura de
avaliação mostra maior consistência quando o *rationale* é gerado antes do *score*.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "2026-10-05.1"

MAX_TEXT = 1200
MAX_SHORT_TEXT = 400
MAX_QUOTE = 300
MAX_ITEMS = 12


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceCitation(_Strict):
    """Trecho literal (opcional) de uma evidência; o código confere que o trecho existe."""

    evidence_id: str = Field(..., min_length=1, max_length=200)
    quote: str | None = Field(default=None, max_length=MAX_QUOTE)


class Driver(_Strict):
    """Afirmação curta sustentada por ao menos uma evidência (fact_id ou news_id)."""

    text: str = Field(..., min_length=1, max_length=MAX_SHORT_TEXT)
    evidence_ids: list[str] = Field(..., min_length=1, max_length=MAX_ITEMS)


class CatalystOut(_Strict):
    description: str = Field(..., min_length=1, max_length=MAX_SHORT_TEXT)
    expected_date: date | None = None
    direction: Literal["positive", "negative", "uncertain"] = "uncertain"


class AnalystOutput(_Strict):
    """R3 — analista fundamentalista neutro (sem persona)."""

    thesis: str = Field(..., max_length=MAX_TEXT)
    drivers: list[Driver] = Field(default_factory=list, max_length=MAX_ITEMS)
    risks: list[Driver] = Field(default_factory=list, max_length=MAX_ITEMS)
    catalysts: list[CatalystOut] = Field(default_factory=list, max_length=MAX_ITEMS)
    kill_criteria: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    data_gaps: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    citations: list[EvidenceCitation] = Field(default_factory=list, max_length=MAX_ITEMS)
    abstain: bool
    stance: int = Field(..., ge=-2, le=2)
    p_outperform: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)


class NewsAssessment(_Strict):
    news_id: str = Field(..., min_length=1, max_length=200)
    issuer_id: str = Field(..., min_length=1, max_length=100)
    sentiment: Literal["negative", "neutral", "positive"]
    materiality: Literal["low", "medium", "high"]
    event_type: Literal["earnings", "guidance", "m&a", "regulatory", "governance", "legal",
                        "macro", "management", "capital", "other"]
    injection_suspected: bool


class NewsOutput(_Strict):
    """R2 — extrator de notícias (temperatura 0)."""

    items: list[NewsAssessment] = Field(default_factory=list, max_length=50)


class ShortRiskOutput(_Strict):
    """R6 — sentinela de risco de short/squeeze (só pode apertar restrições)."""

    rationale: str = Field(..., max_length=MAX_TEXT)
    flags: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    verdict: Literal["ok", "caution", "veto"]


class MacroOutput(_Strict):
    """R5 — analista macro/país (apenas regime e sinalizações)."""

    scope: str = Field(..., min_length=1, max_length=50)
    regime: str = Field(..., max_length=MAX_SHORT_TEXT)
    summary: str = Field(..., max_length=MAX_TEXT)
    key_events: list[CatalystOut] = Field(default_factory=list, max_length=MAX_ITEMS)
    risks: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    implications: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    stance: int = Field(..., ge=-2, le=2)


class DebateOutput(_Strict):
    """R4 — pesquisador bull ou bear: produz só argumentos com evidência, nunca escore."""

    side: Literal["bull", "bear"]
    arguments: list[Driver] = Field(default_factory=list, max_length=MAX_ITEMS)


class JudgeOutput(_Strict):
    """R4 — juiz neutro: ajusta a stance do analista em no máximo ±1 com evidência nova."""

    rationale: str = Field(..., max_length=MAX_TEXT)
    new_evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    stance_change: int = Field(..., ge=-1, le=1)


SCHEMAS: dict[str, type[BaseModel]] = {
    cls.__name__: cls
    for cls in (AnalystOutput, NewsOutput, ShortRiskOutput, MacroOutput, DebateOutput,
                JudgeOutput)
}
"""Registro dos schemas de saída por nome (usado no ledger e no replay)."""


def output_texts(out: BaseModel) -> list[tuple[str, str]]:
    """Todos os campos de texto livre de uma saída, como ``(caminho, texto)``.

    Usado pelos guardrails (números livres, placeholders, injeção) — os ids de evidência e os
    enums não entram.
    """
    items: list[tuple[str, str]] = []
    if isinstance(out, AnalystOutput):
        items.append(("thesis", out.thesis))
        items += [(f"drivers[{i}]", d.text) for i, d in enumerate(out.drivers)]
        items += [(f"risks[{i}]", d.text) for i, d in enumerate(out.risks)]
        items += [(f"catalysts[{i}]", c.description) for i, c in enumerate(out.catalysts)]
        items += [(f"kill_criteria[{i}]", t) for i, t in enumerate(out.kill_criteria)]
        items += [(f"data_gaps[{i}]", t) for i, t in enumerate(out.data_gaps)]
    elif isinstance(out, ShortRiskOutput):
        items.append(("rationale", out.rationale))
        items += [(f"flags[{i}]", t) for i, t in enumerate(out.flags)]
    elif isinstance(out, MacroOutput):
        items += [("regime", out.regime), ("summary", out.summary)]
        items += [(f"key_events[{i}]", c.description) for i, c in enumerate(out.key_events)]
        items += [(f"risks[{i}]", t) for i, t in enumerate(out.risks)]
        items += [(f"implications[{i}]", t) for i, t in enumerate(out.implications)]
    elif isinstance(out, DebateOutput):
        items += [(f"arguments[{i}]", d.text) for i, d in enumerate(out.arguments)]
    elif isinstance(out, JudgeOutput):
        items.append(("rationale", out.rationale))
    return items
