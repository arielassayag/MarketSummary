"""Configuração do fundo (mandato, limites de risco, liquidez, short squeeze, custos e alpha).

A configuração é carregada de ``configs/latam_ls/fund.yaml``, validada por Pydantic e
tem um hash canônico que faz parte do hash de aprovação: qualquer mudança de limite
depois da aprovação invalida a decisão.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .hashing import sha256_obj

DEFAULT_CONFIG_PATH = Path("configs/latam_ls/fund.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FundSection(_Frozen):
    name: str = "CDP — Cabra da Peste"
    base_currency: Literal["USD"] = "USD"
    inception_date: date = date(2026, 10, 5)
    inception_nav_usd: float = Field(100_000_000.0, gt=0)
    rebalance_weekday: Literal["MON"] = "MON"
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


class RiskSection(_Frozen):
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

    @model_validator(mode="after")
    def _band(self) -> RiskSection:
        if not (self.vol_band_min <= self.vol_target_annual <= self.vol_band_max):
            raise ValueError("A meta de volatilidade precisa estar dentro da banda permitida.")
        if self.gross_min > self.gross_max:
            raise ValueError("gross_min não pode exceder gross_max.")
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


class CostsSection(_Frozen):
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


class AlphaSection(_Frozen):
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


class DrawdownSection(_Frozen):
    """Escada de drawdown (a partir do pico), escalada para vol-alvo de 5%."""

    soft_stop: float = Field(-0.025, lt=0, description="Revisão de risco obrigatória e corte de 25% do gross")
    soft_degross_multiplier: float = Field(0.75, gt=0, le=1)
    hard_stop: float = Field(-0.05, lt=0, description="Corte de 50% do gross")
    degross_multiplier: float = Field(0.5, gt=0, le=1)
    stop_out: float = Field(-0.075, lt=0, description="Gross mínimo e revisão completa do processo")
    stop_out_gross: float = Field(0.5, gt=0)


class RiskModelSection(_Frozen):
    history_days: int = Field(756, ge=120)
    min_obs_days: int = Field(126, ge=20)
    halflife_factor_vol: int = Field(84, ge=5)
    halflife_factor_corr: int = Field(252, ge=5)
    halflife_specific: int = Field(84, ge=5)
    newey_west_lags: int = Field(2, ge=0)
    specific_shrinkage: float = Field(0.3, ge=0, le=1)
    min_names_per_sector: int = Field(3, ge=1)
    market_proxy: str = "ILF"


class ResearchSection(_Frozen):
    provider: Literal["demo", "anthropic", "openrouter", "imported"] = "demo"
    top_n_candidates: int = Field(40, ge=1)
    news_lookback_days: int = Field(14, ge=1)
    llm_can_only_tighten: bool = True
    # Adoção gradual das visões de IA no alpha (shadow → produção). O IC efetivo das visões de
    # IA depende da fase; promoção/rebaixamento por IC realizado (ver docs/latam_ls).
    llm_phase: Literal["S0", "S1", "S2", "S3"] = "S1"
    llm_view_ic_by_phase: dict[str, float] = Field(default_factory=lambda: {
        "S0": 0.0, "S1": 0.01, "S2": 0.02, "S3": 0.03,
    })
    samples_per_judgment: int = Field(5, ge=1)
    min_sign_agreement: float = Field(0.8, ge=0.5, le=1)

    @property
    def llm_view_ic(self) -> float:
        return float(self.llm_view_ic_by_phase.get(self.llm_phase, 0.0))


class FundConfig(_Frozen):
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

    def config_hash(self) -> str:
        return sha256_obj(self)

    def with_overrides(self, overrides: dict) -> FundConfig:
        """Retorna nova configuração aplicando um dicionário aninhado de substituições."""
        base = self.model_dump(mode="python")
        for section, values in overrides.items():
            if section not in base or not isinstance(values, dict):
                raise KeyError(f"Seção de configuração desconhecida: {section}")
            base[section].update(values)
        return FundConfig.model_validate(base)


def load_config(path: str | Path | None = None) -> FundConfig:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return FundConfig.model_validate(raw)
