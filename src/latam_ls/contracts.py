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
    provisional_dates: list[date] = Field(
        default_factory=list,
        description="Datas cuja barra é intradiária provisória (preço disponível no momento da análise)")
    provisional_as_of: datetime | None = Field(default=None, description="Horário da barra provisória")

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


HARNESS_MINDS = ("claude-code", "codex", "api", "demo")


class ResearchPack(_Model):
    week: date
    snapshot_id: str
    provider: str
    mind: str | None = Field(default=None, description="Mente que conduziu a pesquisa: claude-code | codex | api | demo")
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


class DecisionMode(StrEnum):
    """AUTONOMOUS: decisão do PM autônomo CDP sob gates determinísticos. HUMAN: decisão humana."""

    AUTONOMOUS = "AUTONOMOUS"
    HUMAN = "HUMAN"


AUTONOMOUS_DECIDER = "CDP — Cabra da Peste (PM autônomo)"


FORBIDDEN_APPROVERS = {"", "system", "sistema", "ai", "ia", "llm", "bot", "auto", "claude", "demo"}


class JournalPosition(_Model):
    """Registro de tese por posição relevante (premortem e critérios de saída pré-comprometidos)."""

    issuer_id: str
    thesis: str
    variant_perception: str = ""
    probability_correct: float | None = Field(default=None, ge=0, le=1)
    invalidation_criteria: str = ""
    premortem: str = ""
    ai_vs_pm_divergence: str = ""


class DecisionJournal(_Model):
    """Diário de decisão do gestor, gravado ANTES do resultado e incluído no hash de aprovação."""

    situation: str = Field(..., min_length=10, description="Contexto de mercado e da carteira")
    key_variables: list[str] = Field(default_factory=list)
    alternatives_considered: str = ""
    horizon_weeks: int = Field(8, ge=1, le=52)
    catalysts: list[Catalyst] = Field(default_factory=list)
    sizing_rationale: str = ""
    ai_vs_quant_vs_pm: str = Field("", description="Onde o gestor divergiu da IA/quant e por quê")
    premortem: str = ""
    bias_checklist: dict[str, bool] = Field(default_factory=dict)
    positions: list[JournalPosition] = Field(default_factory=list)
    mental_state: str = ""


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
    # Quatro olhos: co-assinatura independente (risco/compliance) quando exigida.
    co_signer: str | None = None
    co_signed_at: datetime | None = None
    co_sign_reasons: list[str] = Field(default_factory=list)
    journal: DecisionJournal | None = None
    audit_head_hash: str | None = Field(default=None, description="Topo da trilha de auditoria no momento da decisão")
    mode: DecisionMode = DecisionMode.HUMAN
    mind: str | None = Field(default=None, description="Mente (harness) que conduziu a decisão do PM")
    pm_decision_hash: str | None = Field(default=None, description="Hash da decisão estruturada do agente PM (modo autônomo)")
    risk_gate_hash: str | None = Field(default=None, description="Hash do resultado dos gates determinísticos de risco")

    _tz = field_validator("decided_at")(classmethod(lambda cls, v: _require_tz(v)))

    @model_validator(mode="after")
    def _decider(self) -> Decision:
        name = self.approver.strip()
        if self.mode == DecisionMode.HUMAN and name.lower() in FORBIDDEN_APPROVERS:
            raise ValueError("Decisão humana exige um responsável identificado (sem autoaprovação disfarçada).")
        if self.mode == DecisionMode.AUTONOMOUS:
            if name != AUTONOMOUS_DECIDER:
                raise ValueError(f"Decisões autônomas são assinadas por '{AUTONOMOUS_DECIDER}'.")
            if self.decision == DecisionType.APPROVE and not (self.pm_decision_hash and self.risk_gate_hash):
                raise ValueError("Decisão autônoma exige hashes da decisão do agente PM e dos gates de risco.")
        return self

    @field_validator("co_signer")
    @classmethod
    def _human_cosigner(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v.strip().lower() in FORBIDDEN_APPROVERS:
            raise ValueError("A co-assinatura exige um responsável humano identificado.")
        return v.strip()

    @model_validator(mode="after")
    def _four_eyes(self) -> Decision:
        if self.co_signer is not None and self.co_signer.lower() == self.approver.lower():
            raise ValueError("Co-assinante precisa ser pessoa diferente do aprovador (quatro olhos).")
        if self.co_signer is not None and self.co_signed_at is None:
            raise ValueError("Co-assinatura sem data.")
        return self


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


# ==========================================================
# Track record diário auditável (marcação a mercado, risco e atribuição)
# ==========================================================

class AttributionLine(_Model):
    group: Literal["component", "factor_group", "factor", "country", "sector", "issuer", "side"]
    name: str
    pnl_usd: float
    contribution: float = Field(..., description="P&L / NAV de abertura do dia")


class DailyPosition(_Model):
    issuer_id: str
    ticker: str
    currency: str
    side: Side
    shares: float | None = None
    price_local: float | None = None
    price_usd: float | None = None
    market_value_usd: float
    weight: float
    day_pnl_usd: float
    day_return_usd: float | None = Field(default=None, description="None quando a linha não negociou (sem reprecificação)")
    repriced: bool = True


class DailyRisk(_Model):
    ex_ante_vol: float | None = None
    factor_vol: float | None = None
    specific_vol: float | None = None
    beta: float | None = None
    gross: float
    net: float
    long_exposure: float
    short_exposure: float
    n_long: int
    n_short: int
    var_1d_99: float | None = None
    es_1d_99: float | None = None
    realized_vol_21d: float | None = None
    realized_vol_63d: float | None = None
    drawdown: float = 0.0
    max_days_to_liquidate: float | None = None
    pct_gross_liquid_1d: float | None = None
    squeeze_high_shorts: int = 0
    exposures: list[ExposureLine] = Field(default_factory=list)


class DailyRecord(_Model):
    """Registro diário imutável do track record, encadeado por hash ao registro anterior."""

    date: date
    fund_name: str
    track_record_type: str
    nav_start_usd: float = Field(..., gt=0)
    nav_end_usd: float = Field(..., gt=0)
    pnl_usd: float
    ret: float
    pnl_components: dict[str, float] = Field(default_factory=dict, description="equity, factor, specific, costs, borrow, financing")
    attribution: list[AttributionLine] = Field(default_factory=list)
    positions: list[DailyPosition] = Field(default_factory=list)
    risk: DailyRisk
    alerts: list[str] = Field(default_factory=list)
    live_book_week: date | None = None
    approval_hash: str | None = None
    input_hashes: dict[str, str] = Field(default_factory=dict)
    is_synthetic: bool
    data_notice: str = ""
    prev_record_hash: str
    record_hash: str = ""

    @model_validator(mode="after")
    def _notice(self) -> DailyRecord:
        if self.is_synthetic and "DADOS SIMULADOS" not in self.data_notice.upper():
            raise ValueError("Registros com dados sintéticos precisam do aviso 'DADOS SIMULADOS'.")
        return self

    def compute_hash(self) -> str:
        return sha256_obj(self.model_dump(mode="json", exclude={"record_hash"}))


# ==========================================================
# Ledger de chamadas a LLM (reprodutibilidade = replay, nunca regeneração)
# ==========================================================

class LLMCallRecord(_Model):
    call_id: str
    week: date | None = None
    task: str
    role: str
    issuer_id: str | None = None
    provider: str
    model: str | None = Field(default=None, description="ID completo do snapshot do modelo (sem aliases)")
    prompt_version: str
    schema_name: str
    request_sha256: str
    input_pack_sha256: str = ""
    response_sha256: str | None = None
    raw_response_path: str | None = None
    stop_reason: str | None = None
    parse_ok: bool
    validation_issues: list[str] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    created_at: datetime

    _tz = field_validator("created_at")(classmethod(lambda cls, v: _require_tz(v)))
