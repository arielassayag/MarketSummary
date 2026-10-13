"""Overlay analítico condicional de um ETF, sem seleção ou consumidor."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

TOLERANCIA_PSD_RELATIVA = 1e-12


@dataclass(frozen=True)
class ReferenciaOverlay:
    body_id: str
    sha256: str
    kind: str


@dataclass(frozen=True)
class EntradaOverlay:
    legal_instrument_id: str
    ticker: str
    currency: str
    mic: str
    price_usd: float | None
    fx_basis_ref: ReferenciaOverlay | None
    price_source_ref: ReferenciaOverlay
    cut_utc: datetime
    inputs_available_utc: datetime
    portfolio_base_excludes_etf_hash: str
    weight_current_etf: float
    portfolio_var_annual: float
    cross_cov_annual: float
    etf_var_annual: float
    covariance_basis: str
    covariance_source_ref: ReferenciaOverlay
    tracking_basis_ref: ReferenciaOverlay | None
    hmin: float
    hmax: float
    oneway_cost_coef: float | None
    borrow_annual_coef: float | None
    financing_annual_coef: float | None
    carry_days: int
    carry_day_count: str
    native_constraint_refs: tuple[ReferenciaOverlay, ...]
    retained_exposure: str
    hedge_failure_scenario: str
    candidate_set_ref: ReferenciaOverlay
    config_body_ref: ReferenciaOverlay


@dataclass(frozen=True)
class DiagnosticoOverlay:
    estado: str
    h_livre: float
    h_condicional: float
    delta_h: float
    variancia_atual: float
    variancia_condicional: float
    limite_ativo: str
    custo_alteracao_nav: float | None
    borrow_periodo_nav: float | None
    financiamento_periodo_nav: float | None
    ausencias: tuple[str, ...]
    exposicao_retida_declarada: str
    cenario_falha_declarado: str
    autoridade_operacional: bool = field(default=False, init=False)
    autenticidade_das_referencias: str = field(default="NAO_VERIFICADA", init=False)


def _texto(value: object, nome: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{nome}: texto nativo não vazio obrigatório")


def _numero(value: object, nome: str, *, minimo: float | None = None) -> None:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{nome}: float nativo finito obrigatório")
    if minimo is not None and value < minimo:
        raise ValueError(f"{nome}: abaixo do mínimo")


def _sha(value: object) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("SHA-256 declarado inválido")


def _referencia(value: object) -> None:
    if type(value) is not ReferenciaOverlay:
        raise ValueError("Referência fora do tipo fechado")
    _texto(value.body_id, "body_id")
    _sha(value.sha256)
    if type(value.kind) is not str or value.kind not in {
        "ORIGINAL_REF_NOT_REVALIDATED",
        "SIMULATED_TEST_ONLY",
    }:
        raise ValueError("Tipo da referência inválido")


def _validar(x: object) -> None:
    if type(x) is not EntradaOverlay:
        raise ValueError("Entrada fora do tipo fechado")
    for nome in (
        "legal_instrument_id",
        "ticker",
        "mic",
        "retained_exposure",
        "hedge_failure_scenario",
    ):
        _texto(getattr(x, nome), nome)
    if type(x.currency) is not str or x.currency != "USD":
        raise ValueError("Moeda deve ser USD")
    if type(x.covariance_basis) is not str or x.covariance_basis != "ANNUAL_USD_FRACTION_JOINT":
        raise ValueError("Covariância anual conjunta de mesma base USD obrigatória")
    for nome in ("cut_utc", "inputs_available_utc"):
        dt = getattr(x, nome)
        if type(dt) is not datetime or dt.tzinfo is not UTC:
            raise ValueError("Instantes exigem datetime nativo com UTC")
    if x.inputs_available_utc > x.cut_utc:
        raise ValueError("Disponibilidade declarada posterior ao corte")
    _sha(x.portfolio_base_excludes_etf_hash)
    for nome in ("weight_current_etf", "cross_cov_annual", "hmin", "hmax"):
        _numero(getattr(x, nome), nome)
    _numero(x.portfolio_var_annual, "portfolio_var_annual", minimo=0.0)
    _numero(x.etf_var_annual, "etf_var_annual", minimo=0.0)
    if x.etf_var_annual == 0.0:
        raise ValueError("Variância do ETF deve ser estritamente positiva")
    if x.hmin > x.hmax:
        raise ValueError("Intervalo de cenário invertido")
    for nome in ("price_usd", "oneway_cost_coef", "borrow_annual_coef", "financing_annual_coef"):
        value = getattr(x, nome)
        if value is not None:
            _numero(value, nome, minimo=None if nome == "financing_annual_coef" else 0.0)
    if x.price_usd == 0.0:
        raise ValueError("Preço zero não é preço disponível")
    for nome in (
        "price_source_ref",
        "covariance_source_ref",
        "candidate_set_ref",
        "config_body_ref",
    ):
        _referencia(getattr(x, nome))
    for nome in ("fx_basis_ref", "tracking_basis_ref"):
        value = getattr(x, nome)
        if value is not None:
            _referencia(value)
    if type(x.native_constraint_refs) is not tuple:
        raise ValueError("Restrições exigem tuple nativa")
    for ref in x.native_constraint_refs:
        _referencia(ref)
    if type(x.carry_days) is not int or not 0 <= x.carry_days <= 365000:
        raise ValueError("Dias inteiros de carry fora do orçamento finito")
    if type(x.carry_day_count) is not str or x.carry_day_count not in {
        "ACT360",
        "ACT365",
        "TRADING252",
    }:
        raise ValueError("Convenção de carry inválida")
    limite = math.sqrt(x.portfolio_var_annual) * math.sqrt(x.etf_var_annual)
    tolerancia = TOLERANCIA_PSD_RELATIVA * max(limite, abs(x.cross_cov_annual))
    if abs(x.cross_cov_annual) > limite + tolerancia:
        raise ValueError("Covariância conjunta não PSD")


def diagnosticar_overlay_sombra(x: EntradaOverlay) -> DiagnosticoOverlay:
    """Minimiza somente a quadrática recebida dentro do intervalo declarado.

    Dados/restrições não são autenticados por este kernel. Não recebe alvo de
    alpha nem decide a preferência econômica entre overlay e redução de posição.
    """
    _validar(x)
    livre = -x.cross_cov_annual / x.etf_var_annual
    if not math.isfinite(livre):
        raise ValueError("Overflow no hedge livre")
    candidato = min(max(livre, x.hmin), x.hmax)
    delta = candidato - x.weight_current_etf

    def variancia(h):
        v = x.portfolio_var_annual + 2.0 * h * x.cross_cov_annual + h * h * x.etf_var_annual
        if not math.isfinite(v):
            raise ValueError("Overflow na variância do overlay")
        return v

    atual, nova = variancia(x.weight_current_etf), variancia(candidato)
    ausencias = tuple(
        nome
        for nome in (
            "price_usd",
            "fx_basis_ref",
            "tracking_basis_ref",
            "oneway_cost_coef",
            "borrow_annual_coef",
            "financing_annual_coef",
        )
        if getattr(x, nome) is None
    )
    if not x.native_constraint_refs:
        ausencias += ("native_constraint_refs",)
    denominador = {"ACT360": 360.0, "ACT365": 365.0, "TRADING252": 252.0}[x.carry_day_count]
    fracao = x.carry_days / denominador
    custo = None if x.oneway_cost_coef is None else x.oneway_cost_coef * abs(delta)
    borrow = (
        None if x.borrow_annual_coef is None else x.borrow_annual_coef * abs(candidato) * fracao
    )
    financiamento = (
        None
        if x.financing_annual_coef is None
        else x.financing_annual_coef * abs(candidato) * fracao
    )
    if not math.isfinite(delta) or any(
        v is not None and not math.isfinite(v) for v in (custo, borrow, financiamento)
    ):
        raise ValueError("Overflow no delta ou custo/carry")
    estado = "CONDICIONAL_SEM_ESCOLHA"
    if atual < 0.0 or nova < 0.0:
        estado = "INSUFICIENTE_VARIANCIA_NEGATIVA"
    elif ausencias:
        estado = "CONDICIONAL_INCOMPLETO"
    limite_ativo = "inferior" if livre < x.hmin else "superior" if livre > x.hmax else "interior"
    return DiagnosticoOverlay(
        estado,
        livre,
        candidato,
        delta,
        atual,
        nova,
        limite_ativo,
        custo,
        borrow,
        financiamento,
        ausencias,
        x.retained_exposure,
        x.hedge_failure_scenario,
    )
