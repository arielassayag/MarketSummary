"""Contratos Pydantic v2 dos artefatos persistidos do gestor LatAm L/S.

Os objetos quantitativos em memória (painéis de preços, modelo de risco) usam pandas e
dataclasses nos respectivos módulos; tudo o que é gravado em disco, exibido ao gestor ou
vinculado à aprovação passa por estes contratos.

Convenções:
- Pesos (``weight``) são frações do NAV em USD; positivo = comprado, negativo = vendido.
- Taxas e retornos são decimais (0.05 = 5%).
- Datas de semana (``week``) são sempre a segunda-feira da decisão.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .hashing import sha256_obj


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("Timestamps precisam de fuso horário.")
    return v


# ==========================================================
# Universo e snapshot de dados
# ==========================================================

class Country(StrEnum):
    BR = "BR"
    MX = "MX"
    CL = "CL"
    CO = "CO"
    PE = "PE"
    AR = "AR"
    PA = "PA"  # Panamá (ex.: Copa)
    UY = "UY"  # Uruguai (ex.: Arcos Dorados)
    LATAM = "LATAM"  # negócio regional sem país dominante


class LineType(StrEnum):
    LOCAL = "LOCAL"
    ADR = "ADR"
    US_LISTED = "US_LISTED"


class SnapshotFile(_Model):
    path: str
    sha256: str
    rows: int | None = None
    description: str = ""


class SourceRecord(_Model):
    source_id: str
    name: str
    url: str
    fields: list[str] = Field(default_factory=list)
    retrieved_at: datetime
    point_in_time: bool = Field(..., description="False quando o dado é um retrato atual (não PIT)")
    notes: str = ""

    _tz = field_validator("retrieved_at")(classmethod(lambda cls, v: _require_tz(v)))


class SnapshotManifest(_Model):
    snapshot_id: str
    as_of: date = Field(..., description="Último pregão completo incluído")
    created_at: datetime
    universe_sha256: str
    files: list[SnapshotFile]
    sources: list[SourceRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_tickers: list[str] = Field(default_factory=list)
    is_synthetic: bool
    data_notice: str = ""

    _tz = field_validator("created_at")(classmethod(lambda cls, v: _require_tz(v)))

    @model_validator(mode="after")
    def _notice(self) -> SnapshotManifest:
        if self.is_synthetic and "DADOS SIMULADOS" not in self.data_notice.upper():
            raise ValueError("Snapshots sintéticos precisam carregar o aviso 'DADOS SIMULADOS'.")
        return self

    def content_hash(self) -> str:
        return sha256_obj({"as_of": self.as_of, "universe": self.universe_sha256,
                           "files": [(f.path, f.sha256) for f in self.files]})


# ==========================================================
# Pesquisa (camada de IA generativa) — somente qualitativa
# ==========================================================

class EvidenceKind(StrEnum):
    FACT = "fact"      # fato determinístico do FactBook (fact_id)
    NEWS = "news"      # manchete/notícia (conteúdo NÃO confiável)
    SOURCE = "source"  # documento externo (URL) consultado por pesquisador


class EvidenceRef(_Model):
    kind: EvidenceKind
    ref_id: str = Field(..., description="fact_id, news_id ou URL")
    note: str = ""


class Fact(_Model):
    fact_id: str = Field(..., description="Ex.: 'PETROBRAS.ret_1m_usd'")
    issuer_id: str | None = None
    name: str
    value: float | None = Field(..., description="None quando o dado está ausente (nunca vira zero)")
    unit: Literal["pct", "x", "usd", "usd_mm", "days", "score", "bps", "ratio", "z", "count"]
    formatted: str
    formula: str
    inputs: list[str] = Field(default_factory=list)
    point_in_time: bool = True


class FactBook(_Model):
    as_of: date
    snapshot_id: str
    facts: dict[str, Fact]
    is_synthetic: bool

    def factbook_hash(self) -> str:
        return sha256_obj(self)


class NewsItem(_Model):
    news_id: str
    issuer_ids: list[str] = Field(default_factory=list)
    title: str
    source: str = ""
    url: str | None = None
    published_at: datetime
    language: str = "pt"
    untrusted: Literal[True] = True
    is_synthetic: bool = False

    _tz = field_validator("published_at")(classmethod(lambda cls, v: _require_tz(v)))


class Catalyst(_Model):
    description: str
    expected_date: date | None = None
    direction: Literal["positive", "negative", "uncertain"] = "uncertain"


class SqueezeAssessment(_Model):
    verdict: Literal["ok", "caution", "veto"]
    rationale: str


class ResearchNote(_Model):
    """Nota de pesquisa por emissor. Sem números calculados pelo modelo: só referências a fatos."""

    note_id: str
    issuer_id: str
    week: date
    role: Literal["fundamental", "news_sentiment", "short_risk", "bull_bear_judge", "pm"]
    provider: str
    model: str | None = None
    prompt_version: str
    stance: int = Field(..., ge=-2, le=2, description="-2 forte venda … +2 forte compra")
    confidence: float = Field(..., ge=0, le=1)
    horizon_weeks: int = Field(8, ge=1, le=52)
    thesis: str
    bull_points: list[str] = Field(default_factory=list)
    bear_points: list[str] = Field(default_factory=list)
    catalysts: list[Catalyst] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    squeeze: SqueezeAssessment | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    input_hash: str = Field(..., description="Hash do FactBook/notícias/prompt usados")
    created_at: datetime
    is_synthetic: bool = False

    _tz = field_validator("created_at")(classmethod(lambda cls, v: _require_tz(v)))


class MacroNote(_Model):
    note_id: str
    week: date
    scope: str = Field(..., description="País (BR, MX, …), 'GLOBAL' ou tema")
    stance: int = Field(..., ge=-2, le=2)
    regime: str
    summary: str
    key_events: list[Catalyst] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    portfolio_implications: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    provider: str
    model: str | None = None
    prompt_version: str
    created_at: datetime
    is_synthetic: bool = False

    _tz = field_validator("created_at")(classmethod(lambda cls, v: _require_tz(v)))


class ViewSource(StrEnum):
    AI = "ai"
    PM = "pm"


class View(_Model):
    """Visão qualitativa convertida em inclinação de alpha limitada pelo código.

    Regra de segurança: visões de IA só podem RESTRINGIR risco (``no_short``/``no_long``/
    ``max_abs_weight`` menores). Visões do gestor podem inclinar alpha, sempre dentro dos
    limites do mandato.
    """

    issuer_id: str
    source: ViewSource
    score: int = Field(..., ge=-2, le=2)
    confidence: float = Field(..., ge=0, le=1)
    rationale: str
    author: str
    no_short: bool = False
    no_long: bool = False
    max_abs_weight: float | None = Field(default=None, ge=0)
    note_ids: list[str] = Field(default_factory=list)


class ResearchPack(_Model):
    week: date
    snapshot_id: str
    provider: str
    notes: list[ResearchNote] = Field(default_factory=list)
    macro: list[MacroNote] = Field(default_factory=list)
    views: list[View] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    is_synthetic: bool = False

    def research_hash(self) -> str:
        return sha256_obj(self)


# ==========================================================
# Proposta semanal, risco e compliance
# ==========================================================

class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"
    COVER = "COVER"


class PositionTarget(_Model):
    issuer_id: str
    name: str
    country: str
    sector: str
    side: Side
    weight: float
    notional_usd: float
    execution_ticker: str
    line_type: LineType
    currency: str
    price_local: float | None = None
    shares: int | None = None
    adtv_usd: float | None = None
    pct_adtv: float | None = Field(default=None, description="|notional| / ADTV")
    days_to_liquidate: float | None = None
    squeeze_score: float | None = None
    squeeze_bucket: Literal["LOW", "MEDIUM", "HIGH", "NA"] = "NA"
    borrow_fee_annual: float | None = None
    alpha_annual: float | None = None
    alpha_z: float | None = None
    view_score: int | None = None
    risk_contribution: float | None = Field(default=None, description="Fração da variância total")
    beta: float | None = None


class Trade(_Model):
    issuer_id: str
    ticker: str
    action: TradeAction
    shares: int | None = None
    notional_usd: float
    weight_change: float
    pct_adtv: float | None = None
    est_cost_bps: float | None = None
    est_days: float | None = None
    currency: str


class FxHedge(_Model):
    currency: str
    exposure_usd: float
    hedge_notional_usd: float
    instrument: str = "NDF 1M"
    rationale: str = ""


class ExposureLine(_Model):
    group: Literal["country", "sector", "style", "currency", "market"]
    name: str
    long: float
    short: float
    net: float
    gross: float
    limit: float | None = None


class RiskSummary(_Model):
    ex_ante_vol: float
    factor_vol: float
    specific_vol: float
    factor_risk_share: float
    beta: float
    gross: float
    net: float
    long_exposure: float
    short_exposure: float
    n_long: int
    n_short: int
    var_1d_99: float
    es_1d_99: float
    var_1w_99: float
    effective_n: float
    max_days_to_liquidate: float
    pct_nav_liquidated_1d: float
    exposures: list[ExposureLine] = Field(default_factory=list)
    factor_contributions: dict[str, float] = Field(default_factory=dict)
    stress_tests: dict[str, float] = Field(default_factory=dict)
    top_risk_contributors: dict[str, float] = Field(default_factory=dict)


class Severity(StrEnum):
    HARD = "HARD"  # bloqueia aprovação
    SOFT = "SOFT"  # exige ciência explícita do gestor
    INFO = "INFO"


class ComplianceCheck(_Model):
    check_id: str
    name: str
    passed: bool
    severity: Severity
    value: float | None = None
    limit: float | None = None
    details: str = ""


class ProposalState(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BOOKED = "BOOKED"
    SUPERSEDED = "SUPERSEDED"
    BLOCKED = "BLOCKED"


class OptimizerDiagnostics(_Model):
    status: str
    solver: str
    solve_seconds: float
    objective: float | None = None
    expected_alpha_annual: float | None = None
    expected_cost_annual: float | None = None
    binding_constraints: list[str] = Field(default_factory=list)
    n_candidates: int = 0
    n_excluded: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class Proposal(_Model):
    proposal_id: str
    week: date
    version: int = Field(..., ge=1)
    created_at: datetime
    created_by: str = Field(..., description="Sempre o sistema; a aprovação é humana")
    nav_usd: float = Field(..., gt=0)
    snapshot_id: str
    snapshot_hash: str
    config_hash: str
    research_hash: str
    overrides: dict = Field(default_factory=dict)
    positions: list[PositionTarget]
    trades: list[Trade] = Field(default_factory=list)
    fx_hedges: list[FxHedge] = Field(default_factory=list)
    risk: RiskSummary
    compliance: list[ComplianceCheck]
    optimizer: OptimizerDiagnostics
    memo_markdown: str = ""
    is_synthetic: bool
    data_notice: str = ""

    _tz = field_validator("created_at")(classmethod(lambda cls, v: _require_tz(v)))

    @model_validator(mode="after")
    def _notice(self) -> Proposal:
        if self.is_synthetic and "DADOS SIMULADOS" not in self.data_notice.upper():
            raise ValueError("Propostas com dados sintéticos precisam do aviso 'DADOS SIMULADOS'.")
        return self

    @property
    def hard_failures(self) -> list[ComplianceCheck]:
        return [c for c in self.compliance if not c.passed and c.severity == Severity.HARD]

    @property
    def soft_failures(self) -> list[ComplianceCheck]:
        return [c for c in self.compliance if not c.passed and c.severity == Severity.SOFT]

    def proposal_hash(self) -> str:
        return sha256_obj(self)


# ==========================================================
# Decisão humana, livro e auditoria
# ==========================================================

class DecisionType(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


FORBIDDEN_APPROVERS = {"", "system", "sistema", "ai", "ia", "llm", "bot", "auto", "claude", "demo"}


class Decision(_Model):
    week: date
    proposal_id: str
    proposal_hash: str
    snapshot_hash: str
    config_hash: str
    research_hash: str
    decision: DecisionType
    approver: str
    rationale: str = Field(..., min_length=10)
    acknowledged_soft_checks: list[str] = Field(default_factory=list)
    conviction: int | None = Field(default=None, ge=1, le=5)
    decided_at: datetime
    approval_hash: str

    _tz = field_validator("decided_at")(classmethod(lambda cls, v: _require_tz(v)))

    @field_validator("approver")
    @classmethod
    def _human(cls, v: str) -> str:
        if v.strip().lower() in FORBIDDEN_APPROVERS:
            raise ValueError("A aprovação exige um responsável humano identificado (sem autoaprovação).")
        return v.strip()


class BookedPosition(_Model):
    issuer_id: str
    ticker: str
    weight: float
    notional_usd: float
    shares: int | None = None
    entry_price_local: float | None = None
    currency: str


class BookEntry(_Model):
    week: date
    proposal_id: str
    approval_hash: str
    booked_at: datetime
    nav_usd: float
    positions: list[BookedPosition]
    pricing_note: str = ""

    _tz = field_validator("booked_at")(classmethod(lambda cls, v: _require_tz(v)))


class LedgerRow(_Model):
    date: date
    nav_usd: float
    pnl_usd: float
    ret: float
    gross: float
    net: float
    factor_pnl_usd: float | None = None
    specific_pnl_usd: float | None = None
    cost_usd: float | None = None
    financing_usd: float | None = None
    note: str = ""


class AuditEvent(_Model):
    seq: int = Field(..., ge=0)
    ts: datetime
    event_type: str
    actor: str
    week: date | None = None
    payload_hash: str
    summary: str = ""
    prev_hash: str
    event_hash: str

    _tz = field_validator("ts")(classmethod(lambda cls, v: _require_tz(v)))
