"""Contratos Pydantic v2 do projeto Fechamento — AI Notes #8.

Define os modelos estruturados de dados para processos, entradas financeiras,
evidências, FactBook, rascunhos, revisões e máquina de estados.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ==========================================
# Especificação do Processo (ProcessSpec)
# ==========================================

class StepClassification(StrEnum):
    ELIMINATE = "eliminar"
    CODE = "codigo"
    AI = "ia"
    HUMAN = "humano"


class ProcessStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_id: str = Field(..., description="Identificador único da etapa")
    name: str = Field(..., description="Nome descritivo da etapa")
    objective: str = Field(..., description="Objetivo principal da etapa")
    inputs: list[str] = Field(default_factory=list, description="Entradas requeridas")
    outputs: list[str] = Field(default_factory=list, description="Saídas geradas")
    responsible: str = Field(..., description="Responsável pela execução")
    dependencies: list[str] = Field(default_factory=list, description="IDs das etapas predecessoras")
    completion_rule: str = Field(..., description="Regra de conclusão objetiva")
    exceptions: list[str] = Field(default_factory=list, description="Possíveis exceções")
    exception_destination: str = Field(..., description="Destino do fluxo em caso de exceção")
    classification: StepClassification = Field(..., description="Classificação da etapa no redesenho")
    observed_time_minutes: float | None = Field(default=None, description="Tempo medido empiricamente (minutos)")
    estimated_time_minutes: float | None = Field(default=None, description="Tempo estimado inicial (minutos)")


class ProcessSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    process_id: str = Field(..., description="Identificador do processo")
    title: str = Field(..., description="Título do processo")
    description: str = Field(..., description="Descrição detalhada do processo")
    is_redesign: bool = Field(default=False, description="Indica se é a versão redesenhada")
    steps: list[ProcessStep] = Field(..., description="Lista de etapas do processo")

    @model_validator(mode="after")
    def validate_graph(self) -> ProcessSpec:
        ids = [s.step_id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Identificadores de etapas (step_id) devem ser únicos.")

        id_set = set(ids)
        for s in self.steps:
            for dep in s.dependencies:
                if dep not in id_set:
                    raise ValueError(f"Dependência '{dep}' na etapa '{s.step_id}' não existe no processo.")

        # Detecção de ciclos no caminho principal (Topological Sort / DFS)
        adj: dict[str, list[str]] = {s.step_id: [] for s in self.steps}
        for s in self.steps:
            for dep in s.dependencies:
                adj[dep].append(s.step_id)

        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited

        def dfs(node: str) -> None:
            visited[node] = 1
            for neighbor in adj.get(node, []):
                if visited.get(neighbor) == 1:
                    raise ValueError(f"Ciclo detectado no fluxo do processo envolvendo a etapa '{neighbor}'.")
                if visited.get(neighbor, 0) == 0:
                    dfs(neighbor)
            visited[node] = 2

        for step_id in ids:
            if visited.get(step_id, 0) == 0:
                dfs(step_id)

        return self


# ==========================================
# Contratos de Ingestão e Dados Financeiros
# ==========================================

class InstrumentType(StrEnum):
    EQUITY = "equity"
    INDEX = "index"
    CURRENCY = "currency"


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str = Field(..., description="Código do instrumento (ex: IBOV, USD/BRL, PETR4)")
    instrument_type: InstrumentType = Field(..., description="Tipo do instrumento")
    currency: str = Field(..., description="Moeda ou unidade de cotação (BRL, USD, POINTS, BRL_PER_USD)")
    previous_price: float = Field(..., gt=0, description="Preço de fechamento da sessão anterior")
    current_price: float = Field(..., gt=0, description="Preço de fechamento da sessão atual")
    observed_at: datetime = Field(..., description="Timestamp da observação com fuso horário")
    source: str = Field(..., description="Fonte dos dados")
    adjustment_criteria: str = Field(..., description="Critério de ajuste de proventos/splits")
    is_synthetic: bool = Field(default=True, description="Indicador obrigatório de dado simulado")

    @field_validator("observed_at")
    @classmethod
    def check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp de observação da cotação deve conter fuso horário.")
        return v


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str = Field(..., description="Ticker da ação na carteira")
    sector: str = Field(..., description="Setor econômico da empresa")
    weight_start: float = Field(..., ge=0.0, le=1.0, description="Peso inicial na carteira (0 a 1)")
    reference_date: date = Field(..., description="Data de referência da posição")
    is_synthetic: bool = Field(default=True, description="Indicador obrigatório de dado simulado")


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    news_id: str = Field(..., description="Identificador único da notícia")
    title: str = Field(..., description="Título da notícia")
    body: str = Field(..., description="Corpo do texto da notícia")
    published_at: datetime = Field(..., description="Timestamp de publicação com fuso horário")
    source: str = Field(..., description="Fonte da notícia")
    url: str | None = Field(default=None, description="Link fornecido pela fonte; pode ser redirecionamento")
    related_tickers: list[str] = Field(default_factory=list, description="Tickers diretamente relacionados")
    is_synthetic: bool = Field(default=True, description="Indicador obrigatório de dado simulado")

    @field_validator("published_at")
    @classmethod
    def check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp de publicação da notícia deve conter fuso horário.")
        return v


class ManifestFileEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    path: str
    sha256: str


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_notice: str = Field(default="", description="Limitações e natureza dos dados do pacote")
    scenario_id: str = Field(..., description="Identificador do cenário de dados")
    reference_date: date = Field(..., description="Data do pregão atual")
    previous_session: date = Field(..., description="Data da sessão anterior")
    cutoff_time: datetime = Field(..., description="Horário de corte para evidências")
    timezone: str = Field(default="America/Sao_Paulo", description="Fuso horário de mercado")
    files: list[ManifestFileEntry] = Field(default_factory=list, description="Lista de arquivos e seus hashes")
    is_synthetic: bool = Field(default=True, description="Indicador obrigatório de cenário simulado")

    @field_validator("cutoff_time")
    @classmethod
    def check_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Horário de corte deve conter fuso horário.")
        return v


# ==========================================
# FactBook e Evidências Estruturadas
# ==========================================

class Unit(StrEnum):
    PCT = "pct"
    BPS = "bps"
    POINTS = "points"
    BRL_PER_USD = "brl_per_usd"
    NONE = "none"


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str = Field(..., description="Identificador estável do fato (ex: ibov.return_pct)")
    name: str = Field(..., description="Nome descritivo legível")
    value: float = Field(..., description="Valor numérico exato")
    formatted_value: str = Field(..., description="Valor formatado para exibição (ex: +1,25%, -45 bps)")
    unit: Unit = Field(..., description="Unidade de medida")
    period: str = Field(default="diario", description="Período de referência")
    formula: str = Field(..., description="Fórmula aplicável")
    input_refs: list[str] = Field(default_factory=list, description="Referências aos dados de entrada")


class FactBook(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_notice: str = Field(default="", description="Limitações e natureza dos dados do pacote")
    scenario_id: str = Field(...)
    reference_date: date = Field(...)
    facts: dict[str, Fact] = Field(default_factory=dict)
    is_synthetic: bool = Field(default=True)

    def get_fact(self, fact_id: str) -> Fact | None:
        return self.facts.get(fact_id)


# ==========================================
# Rascunho, Parágrafos e Revisões
# ==========================================

class ClaimType(StrEnum):
    FACTUAL = "factual"
    INTERPRETATION = "interpretation"


class CommentaryParagraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    paragraph_id: int = Field(..., description="Índice ordinal do parágrafo")
    text: str = Field(..., description="Texto com placeholders {{fact:id}} e {{news:id}}")
    rendered_text: str | None = Field(default=None, description="Texto após substituição determinística")
    claim_type: ClaimType = Field(default=ClaimType.FACTUAL, description="Classificação da afirmação")
    fact_refs: list[str] = Field(default_factory=list, description="IDs dos fatos referenciados")
    news_refs: list[str] = Field(default_factory=list, description="IDs das notícias referenciadas")


class CommentaryDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id: str = Field(...)
    paragraphs: list[CommentaryParagraph] = Field(default_factory=list)
    rendered_text: str | None = Field(default=None)
    provider_id: str = Field(...)
    model_id: str | None = Field(default=None)
    created_at: datetime = Field(...)
    is_synthetic: bool = Field(default=True)


# ==========================================
# Máquina de Estados e Auditoria
# ==========================================

class WorkflowState(StrEnum):
    CREATED = "CREATED"
    INPUTS_VALIDATED = "INPUTS_VALIDATED"
    METRICS_READY = "METRICS_READY"
    DRAFT_READY = "DRAFT_READY"
    CHECKED = "CHECKED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    EXPORTED = "EXPORTED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ValidationCheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_id: str
    name: str
    passed: bool
    severity: str = "critical"  # "critical", "warning", "info"
    details: str


class RevisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    revision_number: int
    text: str
    created_at: datetime
    created_by: str
    text_hash: str
    checks_passed: bool
    notes: str = ""


class WorkflowRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    scenario_id: str
    state: WorkflowState
    created_at: datetime
    updated_at: datetime
    inputs_hash: str
    facts_hash: str | None = None
    draft_hash: str | None = None
    approval_hash: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    blocking_reason: str | None = None
    provider_used: str | None = None
    latency_ms: float | None = None
    token_usage: dict[str, int] | None = None
    cost_usd: float | None = None
