"""Schemas Pydantic v2 do projeto + JSON Schemas estritos para structured outputs.

Nota de projeto: os modelos de SAÍDA (AgentOutput) não validam faixas (contagem
de palavras, número de itens etc.) no parse — isso é calculado pelo avaliador
determinístico para que violações apareçam como métricas, não como crashes.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class Category(StrEnum):
    index = "index"  # type: ignore[assignment]
    currency = "currency"
    rates = "rates"
    sector = "sector"
    equity = "equity"
    macro_data = "macro_data"
    news_domestic = "news_domestic"
    news_global = "news_global"
    news_corporate = "news_corporate"
    other = "other"


class MeasureKind(StrEnum):
    level = "level"
    return_pct = "return_pct"
    change_pct = "change_pct"
    change_bps = "change_bps"
    contribution_bps = "contribution_bps"
    absolute_value = "absolute_value"
    text_only = "text_only"


class Unit(StrEnum):
    pct = "pct"
    bps = "bps"
    points = "points"
    brl_per_usd = "brl_per_usd"
    brl = "brl"
    usd = "usd"
    count = "count"  # type: ignore[assignment]
    none = "none"


class Direction(StrEnum):
    up = "up"
    down = "down"
    flat = "flat"
    na = "na"


class Regime(StrEnum):
    calm = "calm"
    domestic_macro = "domestic_macro"
    global_macro = "global_macro"
    corporate = "corporate"
    stress = "stress"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class ReviewStatus(StrEnum):
    draft = "draft"
    in_review = "in_review"
    reviewed = "reviewed"
    rejected = "rejected"


class Split(StrEnum):
    dev = "dev"
    holdout = "holdout"


class Severity(StrEnum):
    critical = "critical"
    warning = "warning"


SIGNED_MEASURE_KINDS = {
    MeasureKind.return_pct,
    MeasureKind.change_pct,
    MeasureKind.change_bps,
    MeasureKind.contribution_bps,
}

QUANTITATIVE_MEASURE_KINDS = SIGNED_MEASURE_KINDS | {
    MeasureKind.level,
    MeasureKind.absolute_value,
}

# unidade esperada por measure_kind
UNIT_FOR_MEASURE: dict[MeasureKind, set[Unit]] = {
    MeasureKind.return_pct: {Unit.pct},
    MeasureKind.change_pct: {Unit.pct},
    MeasureKind.change_bps: {Unit.bps},
    MeasureKind.contribution_bps: {Unit.bps},
}


class Source(BaseModel):
    name: str
    url: str
    source_tier: int = Field(ge=1, le=3)
    published_at: str | None = None

    @field_validator("url")
    @classmethod
    def _url_ok(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"URL inválida: {v}")
        return v


class Fact(BaseModel):
    fact_id: str
    category: Category
    subject: str
    statement: str
    measure_kind: MeasureKind
    value: float | None = None
    unit: Unit
    direction: Direction
    observed_at: str
    source: Source

    @model_validator(mode="after")
    def _check_value_and_direction(self) -> Fact:
        if self.measure_kind in QUANTITATIVE_MEASURE_KINDS and self.value is None:
            raise ValueError(f"{self.fact_id}: medida {self.measure_kind.value} exige valor numérico")
        if self.measure_kind == MeasureKind.text_only and self.value is not None:
            raise ValueError(f"{self.fact_id}: text_only não deve ter valor numérico")
        if self.value is not None and self.measure_kind in SIGNED_MEASURE_KINDS:
            expected = Direction.up if self.value > 0 else (Direction.down if self.value < 0 else Direction.flat)
            if self.direction not in (expected, Direction.na):
                raise ValueError(
                    f"{self.fact_id}: direção {self.direction.value} incoerente com sinal {self.value}"
                )
        expected_units = UNIT_FOR_MEASURE.get(self.measure_kind)
        if expected_units and self.unit not in expected_units:
            raise ValueError(f"{self.fact_id}: unidade {self.unit.value} inválida para {self.measure_kind.value}")
        return self


class CaseInput(BaseModel):
    facts: list[Fact]

    @model_validator(mode="after")
    def _unique_ids(self) -> CaseInput:
        ids = [f.fact_id for f in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("fact_id duplicado dentro do caso")
        return self


class DriverGroup(BaseModel):
    label: str
    evidence_ids: list[str]
    confidence: Confidence


class ForbiddenConclusion(BaseModel):
    description: str
    severity: Severity


class Reference(BaseModel):
    critical_fact_ids: list[str]
    must_mention_fact_ids: list[str]
    useful_fact_ids: list[str]
    fact_importance: dict[str, int]
    accepted_driver_groups: list[DriverGroup]
    forbidden_conclusions: list[ForbiddenConclusion]
    judge_notes: str = ""


class ReviewBlock(BaseModel):
    status: ReviewStatus = ReviewStatus.draft
    reviewer: str | None = None
    reviewed_at: str | None = None
    notes: str | None = None


class Case(BaseModel):
    case_id: str
    date: str
    split: Split
    regime: Regime
    showcase: bool = False
    input: CaseInput
    reference: Reference
    review: ReviewBlock

    @property
    def facts(self) -> list[Fact]:
        return self.input.facts

    def fact_ids(self) -> set[str]:
        return {f.fact_id for f in self.input.facts}


# ---------------------------------------------------------------------------
# Saída do agente candidato
# ---------------------------------------------------------------------------


class KeyMove(BaseModel):
    fact_id: str
    subject: str
    measure_kind: str
    value: float | None = None
    unit: str
    direction: str


class Driver(BaseModel):
    claim: str
    claim_type: str
    evidence_ids: list[str]
    confidence: str


class Claim(BaseModel):
    text: str
    claim_type: str
    evidence_ids: list[str]


class AgentOutput(BaseModel):
    headline: str
    commentary: str
    key_moves: list[KeyMove]
    drivers: list[Driver]
    claims: list[Claim]
    watch_items: list[str]


class OutputParseError(ValueError):
    """JSON inválido ou fora do schema do agente."""


def parse_agent_output(text: str) -> AgentOutput:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise OutputParseError("sem objeto JSON na resposta")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OutputParseError(f"JSON inválido: {exc}") from exc
    try:
        return AgentOutput.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - converte qualquer erro pydantic
        raise OutputParseError(f"schema inválido: {exc}") from exc


# ---------------------------------------------------------------------------
# Saídas dos judges
# ---------------------------------------------------------------------------


class JudgeDimension(BaseModel):
    score: int = Field(ge=0, le=4)
    reason: str = ""
    unsupported_claims: list[str] = Field(default_factory=list)
    missed_key_facts: list[str] = Field(default_factory=list)
    unsupported_causal_claims: list[str] = Field(default_factory=list)


class CriticalError(BaseModel):
    category: str
    description: str = ""
    severity: str = "warning"
    evidence: str | None = None


class AbsoluteJudgeOutput(BaseModel):
    factuality: JudgeDimension
    materiality: JudgeDimension
    causal_discipline: JudgeDimension
    coverage: JudgeDimension
    clarity: JudgeDimension
    critical_errors: list[CriticalError] = Field(default_factory=list)
    overall_notes: str = ""


class PairwiseOutput(BaseModel):
    choice: str
    factuality_winner: str | None = None
    reason: str = ""

    @field_validator("choice")
    @classmethod
    def _choice_ok(cls, v: str) -> str:
        if v not in ("A", "B", "tie"):
            raise ValueError(f"choice inválido: {v}")
        return v


def parse_absolute_judge(text: str) -> AbsoluteJudgeOutput:
    raw = text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise OutputParseError("sem objeto JSON na resposta do judge")
    data = json.loads(raw[start : end + 1])
    return AbsoluteJudgeOutput.model_validate(data)


def parse_pairwise(text: str) -> PairwiseOutput:
    raw = text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise OutputParseError("sem objeto JSON na resposta do judge pareado")
    data = json.loads(raw[start : end + 1])
    return PairwiseOutput.model_validate(data)


# ---------------------------------------------------------------------------
# Registro de geração (checkpoint em raw_generations.jsonl)
# ---------------------------------------------------------------------------


class GenerationStatus(StrEnum):
    completed = "completed"
    invalid_response = "invalid_response"
    failed_terminal = "failed_terminal"
    retry_exhausted = "retry_exhausted"


class GenerationRecord(BaseModel):
    task_id: str
    run_id: str
    case_id: str
    split: str
    regime: str
    model_id: str
    prompt_version: str
    repetition: int
    seed: int | None
    status: GenerationStatus
    from_cache: bool = False
    synthetic: bool = False
    output: AgentOutput | None = None
    raw_text: str | None = None
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
    cache_key: str | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------


def canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_obj(obj: object) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# JSON Schemas estritos (response_format json_schema, strict=true)
# ---------------------------------------------------------------------------


def _strict_object(properties: dict[str, object], required: list[str]) -> dict[str, object]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


AGENT_JSON_SCHEMA: dict[str, object] = _strict_object(
    {
        "headline": {"type": "string"},
        "commentary": {"type": "string"},
        "key_moves": {
            "type": "array",
            "items": _strict_object(
                {
                    "fact_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "measure_kind": {"type": "string"},
                    "value": {"type": ["number", "null"]},
                    "unit": {"type": "string"},
                    "direction": {"type": "string"},
                },
                ["fact_id", "subject", "measure_kind", "value", "unit", "direction"],
            ),
        },
        "drivers": {
            "type": "array",
            "items": _strict_object(
                {
                    "claim": {"type": "string"},
                    "claim_type": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string"},
                },
                ["claim", "claim_type", "evidence_ids", "confidence"],
            ),
        },
        "claims": {
            "type": "array",
            "items": _strict_object(
                {
                    "text": {"type": "string"},
                    "claim_type": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                ["text", "claim_type", "evidence_ids"],
            ),
        },
        "watch_items": {"type": "array", "items": {"type": "string"}},
    },
    ["headline", "commentary", "key_moves", "drivers", "claims", "watch_items"],
)


def _dimension_schema(with_claims: bool, claim_field: str | None = None) -> dict[str, object]:
    props: dict[str, object] = {
        "score": {"type": "integer"},
        "reason": {"type": "string"},
    }
    required = ["score", "reason"]
    if with_claims and claim_field:
        props[claim_field] = {"type": "array", "items": {"type": "string"}}
        required.append(claim_field)
    return _strict_object(props, required)


JUDGE_JSON_SCHEMA: dict[str, object] = _strict_object(
    {
        "factuality": _dimension_schema(True, "unsupported_claims"),
        "materiality": _dimension_schema(True, "missed_key_facts"),
        "causal_discipline": _dimension_schema(True, "unsupported_causal_claims"),
        "coverage": _dimension_schema(False),
        "clarity": _dimension_schema(False),
        "critical_errors": {
            "type": "array",
            "items": _strict_object(
                {
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "string"},
                    "evidence": {"type": ["string", "null"]},
                },
                ["category", "description", "severity", "evidence"],
            ),
        },
        "overall_notes": {"type": "string"},
    },
    ["factuality", "materiality", "causal_discipline", "coverage", "clarity", "critical_errors", "overall_notes"],
)


PAIRWISE_JSON_SCHEMA: dict[str, object] = _strict_object(
    {
        "choice": {"type": "string", "enum": ["A", "B", "tie"]},
        "factuality_winner": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    ["choice", "factuality_winner", "reason"],
)
