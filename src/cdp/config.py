"""Configuração do fundo (mandato, limites de risco, liquidez, short squeeze, custos e alpha).

A configuração é carregada de ``configs/cdp/fund.yaml``, validada por Pydantic e
tem um hash canônico que faz parte do hash de aprovação: qualquer mudança de limite
depois da aprovação invalida a decisão.

Regra de evolução do esquema (o ``config_hash`` é o hash do ``model_dump`` inteiro):

1. Todo campo novo tem um valor **legado** — o que reproduz exatamente o comportamento do
   mandato anterior — declarado em ``LEGACY_DEFAULTS`` da seção. No valor legado o campo é
   OMITIDO do dump (e, portanto, do hash e do ``config_decisao.json``): uma configuração antiga,
   relida pelo código novo, tem o mesmo dump e o mesmo ``config_hash`` byte a byte. Só um valor
   diferente do legado (mudança real de mandato) entra no hash.
2. Um campo existente nunca é removido nem renomeado; um ``Literal`` só ganha membros.
3. Configurações arquivadas (``book/<semana>/config_decisao.json`` ou
   ``configs/cdp/historico/<config_hash>.json``) são autenticadas pelo hash do JSON BRUTO antes
   da validação (:func:`load_archived_config`), então continuam verificáveis mesmo que uma
   mudança futura de esquema altere o dump revalidado.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from .hashing import sha256_obj

DEFAULT_CONFIG_PATH = Path("configs/cdp/fund.yaml")
#: Mandatos arquivados por hash (``<config_hash>.json``), para semanas decididas antes de o
#: ``decide`` gravar ``config_decisao.json`` (livros abertos com uma versão anterior do código).
#: Relativo à raiz do repositório, que contém ``book/`` e ``configs/`` lado a lado.
HISTORICO_DIR = DEFAULT_CONFIG_PATH.parent / "historico"
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_HHMM_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")


def _hhmm(value: str | None) -> str | None:
    if value is not None and not _HHMM_RE.fullmatch(value):
        raise ValueError(f"Horário inválido (use HH:MM): {value!r}")
    return value


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Campo novo -> valor legado (ver docstring do módulo). Nesse valor o campo sai do dump.
    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {}

    @model_serializer(mode="wrap")
    def _omit_legacy(self, handler: SerializerFunctionWrapHandler) -> Any:
        data = handler(self)
        if isinstance(data, dict):
            for name, legacy in self.LEGACY_DEFAULTS.items():
                if name in data and getattr(self, name) == legacy:
                    del data[name]
        return data


class FundSection(_Frozen):
    name: str = "CDP — Cabra da Peste"
    base_currency: Literal["USD"] = "USD"
    inception_date: date = date(2026, 10, 5)
    inception_nav_usd: float = Field(1_000_000.0, gt=0, description="PL inicial (USD)")
    # MON: primeiro pregão da semana na B3 (legado). LAST_US_SESSION: último pregão da semana na
    # NYSE (exige a seção ``execution``). Campo existente: só ganha membros, nunca sai do dump.
    rebalance_weekday: Literal["MON", "LAST_US_SESSION"] = "MON"
    manager_role: str = "Gestor (PM)"
    manager_name: str = "CDP — Cabra da Peste"
    track_record_type: str = "paper trading com preços reais (execução hipotética no fechamento)"
    timezone: str = "America/Sao_Paulo"
    weekly_research_start_local: str = "11:00"
    decision_deadline_local: str = Field("16:30", description="Decisão gravada antes do call de fechamento da B3")
    execution_convention: str = (
        "MOC: carteira decidida antes do fechamento de segunda com dados até sexta; executada pelo "
        "valor-alvo (peso × NAV) ao preço de fechamento de segunda de cada linha, com custos do modelo"
    )
    daily_close_run_local: str = "19:20"
    primary_calendar: str = "BVMF"
    rebalance_rule: str = "primeiro pregão da semana na B3 (segunda ou o próximo dia útil)"
    minds: list[str] = Field(default_factory=lambda: ["claude-code", "codex"])
    use_all_available_data: bool = Field(
        True, description="Usa todo dado disponível até o momento da análise, inclusive intradiário")


class OperationalLimits(_Frozen):
    """Limites operacionais de neutralidade, mais apertados que o mandato (restrição do otimizador
    e checagem SOFT da compliance). O limite efetivo é ``min(mandato, operacional)``.

    ``country_net`` aceita a chave ``"*"`` para os demais países (ver
    :meth:`country_net_limit`)."""

    beta: float = Field(0.02, ge=0, description="|β previsto| operacional vs. mercado LatAm")
    style: float = Field(0.05, ge=0, description="|exposição| operacional por fator de estilo")
    sector_net: float = Field(0.015, ge=0, description="|net| operacional por setor")
    country_net: dict[str, float] = Field(
        default_factory=lambda: {"BR": 0.01, "MX": 0.01, "*": 0.005},
        description="|net| operacional por país; '*' = demais países")
    commodity_beta: float = Field(0.01, ge=0, description="|Σ w·β| operacional por commodity")

    @field_validator("country_net")
    @classmethod
    def _country_net_ok(cls, v: dict[str, float]) -> dict[str, float]:
        bad = {k: x for k, x in v.items() if not x >= 0}
        if bad:
            raise ValueError(f"Limites de país negativos ou inválidos: {bad}")
        return v

    def country_net_limit(self, country: str) -> float | None:
        """Limite operacional do país (``"*"`` para os não listados); ``None`` sem limite."""
        if country in self.country_net:
            return float(self.country_net[country])
        star = self.country_net.get("*")
        return None if star is None else float(star)


class RiskSection(_Frozen):
    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {
        "idio_share_goal": None, "idio_share_floor": None, "factor_risk_basis": "target",
        "factor_risk_aversion_multiplier": 0.0, "second_order_inflation": 1.0,
        "idio_gate_models": ("decisao",), "operational": None,
        "second_order_inflation_mode": "config", "second_order_inflation_bounds": (1.2, 1.6),
        "vol_floor_alpha_scaling": True,
    }

    vol_target_annual: float = Field(0.05, gt=0)
    vol_band_min: float = Field(0.03, gt=0)
    vol_band_max: float = Field(0.07, gt=0)
    net_exposure_max_abs: float = Field(0.01, ge=0, description="|Σw| máximo em fração do NAV")
    beta_max_abs: float = Field(0.05, ge=0, description="|β previsto| máximo vs. mercado LatAm")
    gross_max: float = Field(2.5, gt=0)
    gross_min: float = Field(0.5, ge=0)
    country_net_max_abs: float = Field(0.05, ge=0)
    sector_net_max_abs: float = Field(0.05, ge=0)
    style_exposure_max_abs: float = Field(0.15, ge=0, description="Exposição líquida por fator de estilo (desvios-padrão × NAV)")
    max_long_weight: float = Field(0.04, gt=0)
    max_short_weight: float = Field(0.025, gt=0)
    min_position_weight: float = Field(0.002, ge=0)
    max_single_name_risk_share: float = Field(0.08, gt=0, description="Contribuição máxima de um nome para a variância total")
    max_factor_risk_share: float = Field(0.30, gt=0, description="Fração máxima da variância vinda de fatores (alerta)")
    risk_aversion: float = Field(1.0, ge=0, description="λ do termo de variância (regularização sob o teto de vol)")
    risk_target_mode: Literal["cap", "match"] = Field(
        "cap", description="cap: vol-alvo é teto; match: escala o alpha até usar o orçamento de vol")
    var_confidence: float = Field(0.99, gt=0.5, lt=1)
    # Temas com neutralidade própria (ex.: estatais brasileiras durante a eleição).
    theme_net_max_abs: dict[str, float] = Field(default_factory=lambda: {"state_owned": 0.01})
    country_gross_share_max: dict[str, float] = Field(default_factory=dict,
                                                      description="Teto da fatia do gross por país")
    # Sensibilidades a commodities neutralizadas à parte (livro neutro em setor pode esconder
    # aposta em cobre x minério ou petróleo x consumidores de combustível).
    commodity_proxies: dict[str, str] = Field(default_factory=dict)
    commodity_beta_max_abs: float = Field(0.03, ge=0, description="|Σ w·β_commodity| máximo")
    # Janelas de evento: multiplicador de vol para fatores país e risco específico (vol implícita >> realizada).
    event_windows: list[dict] = Field(default_factory=lambda: [
        {"name": "Eleição Brasil 2026 (2º turno 25/out)", "country": "BR", "start": "2026-10-05",
         "end": "2026-10-26", "vol_multiplier": 1.5, "reaction_date": "2026-10-05",
         "reaction_exposure_max_abs": 0.0015},
    ])
    bias_prior: float = Field(1.10, ge=1.0, description="Viés a priori do risco ex-ante de carteiras otimizadas")
    bias_prior_weeks: int = Field(26, ge=0, description="Semanas de histórico antes de estimar o viés realizado")
    var_1d_max: float = Field(0.010, gt=0)
    es_1d_max: float = Field(0.0125, gt=0)
    country_stress_max_loss: float = Field(0.015, gt=0, description="Perda máxima por cenário de gap de país")
    country_gap_scenarios: dict[str, list[float]] = Field(default_factory=lambda: {
        "BR": [-0.10, 0.10], "MX": [-0.13], "CL": [-0.15], "PE": [-0.10], "CO": [-0.11], "AR": [-0.56, 0.41],
    })
    # --- Construção com risco idiossincrático (campos novos; valores legados em LEGACY_DEFAULTS).
    idio_share_goal: float | None = Field(
        None, gt=0, le=1, description="Meta da fatia idiossincrática da variância ex-ante (SOFT)")
    idio_share_floor: float | None = Field(
        None, gt=0, le=1, description="Piso da fatia idiossincrática (HARD; nunca relaxado)")
    factor_risk_basis: Literal["target", "achieved"] = Field(
        "target", description="Base do teto de risco fatorial: vol-alvo (legado) ou vol atingida")
    factor_risk_aversion_multiplier: float = Field(
        0.0, ge=0, description="λ_F = multiplicador × λ (penalidade de risco fatorial; 0 = sem)")
    second_order_inflation: float = Field(
        1.0, ge=1.0, description="κ_F de fallback: inflação de 2ª ordem da covariância fatorial")
    idio_gate_models: tuple[Literal["decisao", "base"], ...] = Field(
        ("decisao",), min_length=1, description="Modelos em que a fatia idiossincrática é exigida")
    operational: OperationalLimits | None = Field(
        None, description="Limites operacionais (None = só os limites do mandato)")
    second_order_inflation_mode: Literal["config", "analytic"] = Field(
        "config", description="κ_F: valor de configuração ou fórmula (1 − K/T_ef)⁻² limitada")
    second_order_inflation_bounds: tuple[float, float] = Field(
        (1.2, 1.6), description="Limites de κ_F no modo analítico")
    vol_floor_alpha_scaling: bool = Field(
        True, description="Modo match: escalar o alpha até o piso da banda de vol (legado)")

    @field_validator("second_order_inflation_bounds")
    @classmethod
    def _kappa_bounds(cls, v: tuple[float, float]) -> tuple[float, float]:
        lo, hi = float(v[0]), float(v[1])
        if not (1.0 <= lo <= hi):
            raise ValueError("second_order_inflation_bounds precisa de 1 ≤ mínimo ≤ máximo.")
        return (lo, hi)

    @model_validator(mode="after")
    def _band(self) -> RiskSection:
        if not (self.vol_band_min <= self.vol_target_annual <= self.vol_band_max):
            raise ValueError("A meta de volatilidade precisa estar dentro da banda permitida.")
        if self.gross_min > self.gross_max:
            raise ValueError("gross_min não pode exceder gross_max.")
        if (self.idio_share_goal is not None and self.idio_share_floor is not None
                and self.idio_share_floor > self.idio_share_goal):
            raise ValueError("idio_share_floor não pode exceder idio_share_goal.")
        if len(set(self.idio_gate_models)) != len(self.idio_gate_models):
            raise ValueError("idio_gate_models com modelo repetido.")
        return self


class LiquiditySection(_Frozen):
    min_adtv_usd: float = Field(2_000_000.0, ge=0)
    adv_window_days: int = Field(63, ge=5)
    participation_rate: float = Field(0.20, gt=0, le=1)
    max_days_to_liquidate_long: float = Field(3.0, gt=0)
    max_days_to_liquidate_short: float = Field(2.0, gt=0)
    max_trade_days_inception: float = Field(5.0, gt=0)
    max_trade_days_weekly: float = Field(2.0, gt=0)
    max_weekly_turnover: float = Field(0.60, gt=0, description="Σ|Δw| máximo por semana fora da inception")
    min_adtv_long_usd: float = Field(5_000_000.0, ge=0)
    min_adtv_short_usd: float = Field(10_000_000.0, ge=0)
    short_participation_rate: float = Field(0.15, gt=0, le=1)
    min_gross_liquid_3d: float = Field(0.80, ge=0, le=1)
    min_gross_liquid_5d: float = Field(0.95, ge=0, le=1)


class ShortingSection(_Frozen):
    # Mercados com empréstimo de ações utilizável por um fundo offshore em USD.
    shortable_line_types: list[str] = Field(default_factory=lambda: ["ADR", "US_LISTED", "LOCAL_BR"])
    gc_borrow_fee_us: float = Field(0.003, ge=0, description="Taxa anual GC estimada para ADRs (sem dado público)")
    gc_borrow_fee_br: float = Field(0.008, ge=0, description="Taxa anual GC estimada no BTC da B3 quando sem dado")
    max_borrow_fee: float = Field(0.08, ge=0, description="Acima disso o nome não é vendido")
    min_market_cap_short_usd: float = Field(500_000_000.0, ge=0)


class SqueezeSection(_Frozen):
    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {
        "enforce_entry_blocks": False, "stop_scope": "book", "stop_escalation_count": 2,
        "stop_escalation_sessions": 5,
    }

    si_pct_float_medium: float = 0.05
    si_pct_float_high: float = 0.15
    days_to_cover_medium: float = 3.0
    days_to_cover_high: float = 7.0
    borrow_fee_medium: float = 0.03
    borrow_fee_high: float = 0.08
    ret_1m_medium: float = 0.15
    ret_1m_high: float = 0.30
    free_float_mcap_low_usd: float = 1_000_000_000.0
    # Calibração específica da B3 (BTC inclui arbitragem/ETF; taxa de aluguel é o sinal primário).
    br_borrow_fee_medium: float = 0.05
    br_borrow_fee_high: float = 0.15
    br_btc_pct_float_medium: float = 0.15
    br_btc_pct_float_high: float = 0.25
    br_btc_dtc_medium: float = 10.0
    br_btc_dtc_high: float = 20.0
    adr_parity_tolerance: float = 0.03
    free_float_min_pct: float = Field(0.20, ge=0, le=1, description="Free float abaixo disso: sem short")
    controller_max_pct: float = Field(0.70, ge=0, le=1, description="Controlador acima disso: sem short")
    catalyst_block_sessions: int = Field(5, ge=0, description="Sem short novo com catalisador próximo")
    stop_short_position_loss: float = Field(0.25, gt=0, description="Perda no short que força corte de 50%")
    stop_short_nav_loss: float = Field(0.01, gt=0, description="Perda em % do NAV que força corte de 50%")
    score_medium: float = Field(40.0, ge=0, le=100)
    score_high: float = Field(70.0, ge=0, le=100)
    medium_short_cap_multiplier: float = Field(0.5, ge=0, le=1)
    # --- Vetos de entrada e stop por nome (campos novos; valores legados em LEGACY_DEFAULTS).
    enforce_entry_blocks: bool = Field(
        False, description="Aplica no otimizador os vetos de short novo (resultado, free float)")
    stop_scope: Literal["book", "name"] = Field(
        "book", description="Stop de squeeze: livro inteiro (kill switch) ou corte de 50% do nome")
    stop_escalation_count: int = Field(
        2, ge=1, description="Stops de squeeze em shorts distintos que escalam para o kill switch")
    stop_escalation_sessions: int = Field(
        5, ge=1, description="Janela (pregões) da contagem de stops para escalar")


class CostsSection(_Frozen):
    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {"min_order_cost_usd": {}}

    commission_bps: dict[str, float] = Field(default_factory=lambda: {
        "US": 1.0, "BR": 3.0, "MX": 8.0, "CL": 10.0, "CO": 15.0, "PE": 15.0, "AR": 15.0,
    })
    half_spread_bps_by_tier: dict[str, float] = Field(default_factory=lambda: {
        "T1": 4.0, "T2": 8.0, "T3": 15.0, "T4": 25.0,
    })
    tier_adtv_breaks_usd: list[float] = Field(default_factory=lambda: [50e6, 15e6, 5e6])
    impact_coefficient: float = Field(0.6, ge=0, description="Coeficiente do impacto raiz quadrada (× σ diária)")
    fx_cost_bps: float = Field(3.0, ge=0)
    amortization_weeks: float = Field(8.0, gt=0, description="Horizonte de amortização do custo no objetivo")
    # --- Custo mínimo por ordem (campo novo; legado {} = sem mínimo; docs/cdp/EXECUCAO.md §7).
    min_order_cost_usd: dict[str, float] = Field(
        default_factory=dict,
        description="Custo mínimo por ordem (USD) por mercado de listagem: piso da comissão + "
                    "tarifa da bolsa em tabelas públicas; ausente = sem mínimo")

    @field_validator("min_order_cost_usd")
    @classmethod
    def _min_cost_ok(cls, v: dict[str, float]) -> dict[str, float]:
        bad = {k: x for k, x in v.items() if not (x >= 0)}
        if bad:
            raise ValueError(f"Custo mínimo por ordem negativo ou inválido: {bad}")
        return v


class AlphaSection(_Frozen):
    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {"reresidualize_after_views": False}

    signal_weights: dict[str, float] = Field(default_factory=lambda: {
        "residual_momentum": 0.25,
        "short_term_reversal": 0.15,
        "value": 0.20,
        "quality": 0.15,
        "low_risk": 0.10,
        "analyst_revision": 0.15,
    })
    information_coefficient: float = Field(0.04, ge=0, le=0.5)
    winsor_z: float = Field(3.0, gt=0)
    horizon_weeks: float = Field(8.0, gt=0)
    orthogonalize_to_factors: bool = True
    view_information_coefficient: float = Field(0.03, ge=0, le=0.5)
    max_view_tilt_z: float = Field(1.5, ge=0)
    view_sign_coherence: bool = Field(
        False, description="Visão final positiva ⇒ sem short; negativa ⇒ sem long (só aperta)")
    reresidualize_after_views: bool = Field(
        False, description="Reortogonaliza o alpha aos fatores depois das inclinações das visões")


class DrawdownSection(_Frozen):
    """Escada de drawdown (a partir do pico), escalada para vol-alvo de 5%."""

    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {"risk_reference": "mandate_gross"}

    soft_stop: float = Field(-0.025, lt=0, description="Revisão de risco obrigatória e corte de 25% do gross")
    soft_degross_multiplier: float = Field(0.75, gt=0, le=1)
    hard_stop: float = Field(-0.05, lt=0, description="Corte de 50% do gross")
    degross_multiplier: float = Field(0.5, gt=0, le=1)
    stop_out: float = Field(-0.075, lt=0, description="Gross mínimo e revisão completa do processo")
    stop_out_gross: float = Field(0.5, gt=0)
    risk_reference: Literal["mandate_gross", "normal_book_vol"] = Field(
        "mandate_gross", description="Base da escada: gross do mandato (legado) ou vol ex-ante "
                                     "da mesma carteira resolvida no estágio normal")


class RiskModelSection(_Frozen):
    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {
        "macro_factors": (), "macro_beta_halflife": 126, "min_names_per_country": None,
        "linked_groups": {},
    }

    history_days: int = Field(756, ge=120)
    min_obs_days: int = Field(126, ge=20)
    halflife_factor_vol: int = Field(84, ge=5)
    halflife_factor_corr: int = Field(252, ge=5)
    halflife_specific: int = Field(84, ge=5)
    newey_west_lags: int = Field(2, ge=0)
    specific_shrinkage: float = Field(0.3, ge=0, le=1)
    min_names_per_sector: int = Field(3, ge=1)
    market_proxy: str = "ILF"
    # --- Bloco macro e países finos (campos novos; valores legados em LEGACY_DEFAULTS).
    macro_factors: tuple[str, ...] = Field(
        (), description="Séries macro do bloco híbrido (ex.: BZ=F, HG=F, GC=F, DX-Y.NYB)")
    macro_beta_halflife: int = Field(126, ge=5, description="Meia-vida (pregões) dos betas macro")
    min_names_per_country: int | None = Field(
        None, ge=1, description="Países com menos emissores são agregados em country:OTHER "
                                "(None = o mesmo mínimo de min_names_per_sector)")
    linked_groups: dict[str, list[str]] = Field(
        default_factory=dict, description="Grupos de controle (holding/controlada): mesma aposta "
                                          "econômica; peso de mesmo sinal ≤ teto por nome")

    @field_validator("linked_groups")
    @classmethod
    def _linked_ok(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        seen: set[str] = set()
        for name, members in v.items():
            if len(members) < 2 or len(set(members)) != len(members):
                raise ValueError(f"Grupo vinculado {name!r} precisa de ≥ 2 emissores distintos.")
            dup = seen & set(members)
            if dup:
                raise ValueError(f"Emissor em mais de um grupo vinculado: {sorted(dup)}")
            seen |= set(members)
        return v

    @field_validator("macro_factors")
    @classmethod
    def _macro_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(v)) != len(v) or any(not s.strip() for s in v):
            raise ValueError("macro_factors com série vazia ou repetida.")
        return v


class ResearchSection(_Frozen):
    provider: Literal["demo", "anthropic", "openrouter", "imported"] = "demo"
    top_n_candidates: int = Field(40, ge=1)
    news_lookback_days: int = Field(14, ge=1)
    llm_can_only_tighten: bool = True
    # Adoção gradual das visões de IA no alpha (shadow → produção). O IC efetivo das visões de
    # IA depende da fase; promoção/rebaixamento por IC realizado (ver docs/cdp).
    llm_phase: Literal["S0", "S1", "S2", "S3"] = "S1"
    llm_view_ic_by_phase: dict[str, float] = Field(default_factory=lambda: {
        "S0": 0.0, "S1": 0.01, "S2": 0.02, "S3": 0.03,
    })
    samples_per_judgment: int = Field(5, ge=1)
    min_sign_agreement: float = Field(0.8, ge=0.5, le=1)

    @property
    def llm_view_ic(self) -> float:
        return float(self.llm_view_ic_by_phase.get(self.llm_phase, 0.0))


#: Marca de horário ainda não verificado em fonte oficial (``close: "verificar"`` no
#: ``fund.yaml``); normalizada para ``None`` na validação.
HORARIO_A_VERIFICAR = "verificar"


class CloseTime(_Frozen):
    """Horário oficial de fechamento de um mercado (``exchange_calendars`` só define os dias).

    ``close``/``moc_cutoff`` ``None`` (omitido ou ``"verificar"`` no ``fund.yaml``) = horário
    ainda não verificado em fonte oficial: as linhas desse mercado não são elegíveis à execução
    no fechamento. A marca vira ``None`` já na validação, então o dump (hash e arquivo) só tem
    ``HH:MM`` ou ``null``."""

    tz: str = Field(..., min_length=1, description="Fuso IANA do horário (ex.: America/New_York)")
    close: str | None = Field(None, description="Fechamento oficial HH:MM no fuso tz")
    moc_cutoff: str | None = Field(None, description="Corte de ordens MOC HH:MM no fuso tz")

    @field_validator("close", "moc_cutoff")
    @classmethod
    def _hhmm_ok(cls, v: str | None) -> str | None:
        if v == HORARIO_A_VERIFICAR:
            return None
        return _hhmm(v)

    @field_validator("tz")
    @classmethod
    def _tz_ok(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Fuso horário desconhecido: {v!r}") from exc
        return v


def _default_close_times() -> dict[str, CloseTime]:
    ny = "America/New_York"
    return {
        "XNYS": CloseTime(tz=ny, close="16:00", moc_cutoff="15:50"),
        "XNAS": CloseTime(tz=ny, close="16:00", moc_cutoff="15:55"),
        "ARCX": CloseTime(tz=ny, close="16:00", moc_cutoff="15:50"),
        "BVMF": CloseTime(tz=ny, close="16:00", moc_cutoff="15:55"),  # B3 alinhada a NY
        "XMEX": CloseTime(tz=ny, close="16:00", moc_cutoff="15:40"),
        "XSGO": CloseTime(tz="America/Santiago", close="16:00", moc_cutoff="15:55"),
        "XBOG": CloseTime(tz="America/Bogota"),                     # a verificar
        "XLIM": CloseTime(tz="America/Lima"),                       # a verificar
        "XBUE": CloseTime(tz="America/Argentina/Buenos_Aires", close="17:00", moc_cutoff="16:50"),
    }


class CapacitySection(_Frozen):
    """Capacidade de execução no fechamento (leilão + janela pré-fechamento), por linha.

    ``cap = mult · [p_leilão · fatia_leilão(mercado) + p_pré · fatia_pré] · ADV`` (ADV pela
    estatística ``adv_statistic`` em ``adv_window_days`` pregões); shorts × ``short_multiplier``;
    dias de fechamento antecipado × ``early_close_multiplier``. Volume desconhecido ⇒ capacidade 0
    (restrição conservadora, nunca dado preenchido)."""

    adv_statistic: Literal["p25", "p50", "mean"] = "p25"
    adv_window_days: int = Field(20, ge=5)
    auction_participation: float = Field(0.10, gt=0, le=0.15, description="teto absoluto 15%")
    preclose_participation: float = Field(0.10, ge=0, le=0.25)
    preclose_volume_share: float = Field(0.25, ge=0, le=1)
    auction_share: dict[str, float] = Field(default_factory=lambda: {
        "US_STOCK": 0.10, "ADR": 0.06, "ETF_US": 0.01, "BR": 0.08, "MX": 0.10, "CL": 0.10,
        "CO": 0.05, "PE": 0.05, "AR": 0.05,
    }, description="Fatia esperada do volume diário no leilão de fechamento, por tipo/mercado")
    short_multiplier: float = Field(0.75, gt=0, le=1)
    early_close_multiplier: float = Field(0.5, gt=0, le=1)

    @field_validator("auction_share")
    @classmethod
    def _shares_ok(cls, v: dict[str, float]) -> dict[str, float]:
        bad = {k: x for k, x in v.items() if not 0 <= x <= 1}
        if bad:
            raise ValueError(f"Fatias de leilão fora de [0, 1]: {bad}")
        return v


class ExecutionSection(_Frozen):
    """Cronograma de rebalanceamento e execução no fechamento (MOC) com capacidade de liquidez.

    A seção inteira é opcional: ``FundConfig.execution = None`` reproduz o comportamento legado
    (primeiro pregão da B3, execução sem teto de leilão). Os padrões abaixo são os da proposta de
    metodologia; quem ativa a regra nova escreve a seção em ``fund.yaml``."""

    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {"max_fixed_cost_bps": None}

    rebalance_calendar: Literal["XNYS", "BVMF"] = "XNYS"
    decision_deadline_cap_local: str = Field("15:00", description="Teto do prazo (HH:MM, Brasília)")
    decision_buffer_minutes: int = Field(45, ge=0, le=240,
                                         description="Prazo = fechamento mais cedo − buffer")
    close_times: dict[str, CloseTime] = Field(default_factory=_default_close_times)
    capacity: CapacitySection = CapacitySection()
    min_trade_weight: float = Field(0.0005, ge=0, description="Banda de não-negociação (% NAV)")
    local_closed_policy: Literal["adr_if_eligible_else_freeze", "freeze"] = (
        "adr_if_eligible_else_freeze")
    early_close_mode: Literal["capacity_half", "risk_reducing_only", "previous_full_session"] = (
        "capacity_half")
    max_closes: int = Field(1, ge=1, le=5, description="Fechamentos por rebalanceamento")
    fill_volume_source: Literal["realized_daily", "expected_adv"] = "realized_daily"
    close_impact_discount: dict[str, float] = Field(default_factory=lambda: {
        "US_STOCK": 0.6, "ADR": 0.6, "BR": 0.6, "MX": 0.6, "CL": 0.6, "ETF_US": 1.0, "CO": 1.0,
        "PE": 1.0, "AR": 1.0,
    }, description="Multiplicador do impacto raiz quadrada executando no leilão")
    closed_home_market_spread_mult: float = Field(1.5, ge=1.0)
    # --- Banda de custo fixo (campo novo; legado None = só ``min_trade_weight``).
    max_fixed_cost_bps: float | None = Field(
        None, gt=0, description="Custo fixo mínimo da ordem ≤ este valor (bps do nocional): "
                                "banda por mercado = mínimo por ordem / limite")

    @field_validator("decision_deadline_cap_local")
    @classmethod
    def _deadline_ok(cls, v: str) -> str:
        return str(_hhmm(v))

    @field_validator("close_impact_discount")
    @classmethod
    def _impact_ok(cls, v: dict[str, float]) -> dict[str, float]:
        bad = {k: x for k, x in v.items() if not 0 <= x <= 1}
        if bad:
            raise ValueError(f"Descontos de impacto fora de [0, 1]: {bad}")
        return v

    @model_validator(mode="after")
    def _calendar_known(self) -> ExecutionSection:
        if self.rebalance_calendar not in self.close_times:
            raise ValueError(f"close_times sem o calendário de rebalanceamento "
                             f"{self.rebalance_calendar}.")
        return self


class FundConfig(_Frozen):
    LEGACY_DEFAULTS: ClassVar[Mapping[str, Any]] = {"execution": None}

    fund: FundSection = FundSection()
    risk: RiskSection = RiskSection()
    liquidity: LiquiditySection = LiquiditySection()
    shorting: ShortingSection = ShortingSection()
    squeeze: SqueezeSection = SqueezeSection()
    costs: CostsSection = CostsSection()
    alpha: AlphaSection = AlphaSection()
    drawdown: DrawdownSection = DrawdownSection()
    risk_model: RiskModelSection = RiskModelSection()
    research: ResearchSection = ResearchSection()
    # Seção nova (None = cronograma e execução legados; ver ExecutionSection).
    execution: ExecutionSection | None = None

    @model_validator(mode="after")
    def _schedule_coherent(self) -> FundConfig:
        if self.fund.rebalance_weekday == "LAST_US_SESSION" and self.execution is None:
            raise ValueError("rebalance_weekday LAST_US_SESSION exige a seção execution.")
        return self

    def config_hash(self) -> str:
        return sha256_obj(self)

    def with_overrides(self, overrides: dict) -> FundConfig:
        """Retorna nova configuração aplicando um dicionário aninhado de substituições."""
        base = self.model_dump(mode="python")
        for section, values in overrides.items():
            if section not in type(self).model_fields or not isinstance(values, dict):
                raise KeyError(f"Seção de configuração desconhecida: {section}")
            if base.get(section) is None:  # seção opcional ausente (valor legado)
                base[section] = dict(values)
            else:
                base[section].update(values)
        return FundConfig.model_validate(base)


def load_config(path: str | Path | None = None) -> FundConfig:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return FundConfig.model_validate(raw)


# ----------------------------------------------------------------------------- arquivo


def config_json(cfg: FundConfig) -> str:
    """Texto canônico de arquivamento (``config_decisao.json`` e ``historico/<hash>.json``):
    ``model_dump(mode="json")`` SEM ``sort_keys`` (a ordem dos dicionários define a ordem das
    somas, e reconstruções precisam ser idênticas bit a bit), indentado, com quebra final."""
    return json.dumps(cfg.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


@dataclass(frozen=True)
class ConfigDecisao:
    """Configuração arquivada e autenticada: ``hash`` é o hash do JSON bruto (o ``config_hash``
    gravado na proposta). Quem compara com um hash gravado usa ``hash``, nunca
    ``cfg.config_hash()`` (que reflete o esquema atual)."""

    cfg: FundConfig
    hash: str
    origem: Path


def load_archived_config(path: str | Path, config_hash: str) -> ConfigDecisao | None:
    """Lê uma configuração arquivada SE o hash do JSON bruto conferir com ``config_hash``.

    A autenticação acontece antes da validação: campos novos do esquema (com valor legado) não
    tornam um arquivo antigo "divergente". ``None`` se o arquivo falta, é ilegível, não confere
    ou não valida com o esquema atual."""
    p = Path(path)
    if not _HASH_RE.fullmatch(config_hash or ""):
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or sha256_obj(raw) != config_hash:
        return None
    try:
        cfg = FundConfig.model_validate(raw)
    except ValueError:
        return None
    return ConfigDecisao(cfg=cfg, hash=config_hash, origem=p)


def archived_config(config_hash: str, base: str | Path = HISTORICO_DIR) -> ConfigDecisao | None:
    """Mandato arquivado em ``<base>/<config_hash>.json`` (autenticado pelo hash bruto). ``base``
    padrão: ``configs/cdp/historico`` relativo ao diretório atual (mesma convenção de
    ``DEFAULT_CONFIG_PATH``)."""
    if not _HASH_RE.fullmatch(config_hash or ""):
        return None
    return load_archived_config(Path(base) / f"{config_hash}.json", config_hash)


def book_historico_dir(book_root: str | Path) -> Path:
    """Histórico de mandatos do repositório que contém o livro: ``<book>/../configs/cdp/historico``
    (``book/`` e ``configs/`` são irmãos no clone; um livro fora do repositório — demonstração,
    cópia de rascunho — não herda o histórico do código)."""
    return Path(book_root).parent / HISTORICO_DIR
