"""Orçamento condicional de cenários; não seleciona ordens nem altera gates."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ReferenciaEarnings:
    """Identificador declarado; nenhum hash autentica arquivos nesta função pura."""

    body_id: str
    sha256: str
    kind: str


@dataclass(frozen=True)
class JanelaEarnings:
    inicio_utc: datetime
    fim_utc: datetime
    status: str
    source_ref: ReferenciaEarnings


@dataclass(frozen=True)
class CenarioEarnings:
    id: str
    movimento_preco_total_usd: float
    source_ref: ReferenciaEarnings
    label: str


@dataclass(frozen=True)
class EntradaEarnings:
    issuer_id: str
    ticker: str
    share_class: str
    currency_basis: str
    weight_current: float
    weight_candidate: float
    event_id: str
    event_version: str
    event_windows_utc: tuple[JanelaEarnings, ...]
    event_session_timing: str
    capture_declared_utc: datetime
    physical_received_utc: datetime
    cut_utc: datetime
    cenarios: tuple[CenarioEarnings, ...]
    scenario_budget_nav: float
    budget_kind: str
    proportional_cost_period: float | None
    borrow_period: float | None
    financing_period: float | None
    native_caps_abs_weight: tuple[float | None, ...]
    config_body_ref: ReferenciaEarnings
    novo_short_bloqueado: bool


@dataclass(frozen=True)
class DiagnosticoEarnings:
    estado: str
    motivo: str
    ids_cenarios: tuple[str, ...]
    janelas: tuple[JanelaEarnings, ...]
    perda_adversa_por_unidade: float | None
    custo_por_unidade: float | None
    limite_cenarios_abs: float | None
    limite_conjunto_abs: float | None
    peso_condicional: float | None
    veto_short_preservado: bool
    autoridade_operacional: bool = field(default=False, init=False)
    autenticidade_das_referencias: str = field(default="NAO_VERIFICADA", init=False)


def _texto(value: object, nome: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{nome}: texto nativo não vazio obrigatório")


def _numero(value: object, nome: str, *, negativo: bool = True) -> None:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{nome}: float nativo finito obrigatório")
    if not negativo and value < 0.0:
        raise ValueError(f"{nome}: valor negativo")


def _utc(value: object, nome: str) -> None:
    # Conferir a identidade do fuso antes de utcoffset evita callbacks do caller.
    if type(value) is not datetime or value.tzinfo is not UTC:
        raise ValueError(f"{nome}: datetime nativo com UTC obrigatório")


def _referencia(value: object) -> None:
    if type(value) is not ReferenciaEarnings:
        raise ValueError("Referência fora do tipo fechado")
    _texto(value.body_id, "body_id")
    if type(value.sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", value.sha256) is None:
        raise ValueError("SHA-256 declarado inválido")
    if type(value.kind) is not str or value.kind not in {
        "ORIGINAL_REF_NOT_REVALIDATED",
        "SIMULATED_TEST_ONLY",
    }:
        raise ValueError("Tipo da referência inválido")


def _validar(entrada: object) -> None:
    if type(entrada) is not EntradaEarnings:
        raise ValueError("Entrada fora do tipo fechado")
    for nome in ("issuer_id", "ticker", "share_class", "event_id", "event_version"):
        _texto(getattr(entrada, nome), nome)
    if (
        type(entrada.currency_basis) is not str
        or entrada.currency_basis != "USD_TOTAL_RETURN_SAME_LINE"
    ):
        raise ValueError("Cenários e posição exigem mesma linha e retorno total USD")
    _numero(entrada.weight_current, "weight_current")
    _numero(entrada.weight_candidate, "weight_candidate")
    _numero(entrada.scenario_budget_nav, "scenario_budget_nav", negativo=False)
    for nome in ("capture_declared_utc", "physical_received_utc", "cut_utc"):
        _utc(getattr(entrada, nome), nome)
    if (
        entrada.capture_declared_utc > entrada.cut_utc
        or entrada.physical_received_utc > entrada.cut_utc
    ):
        raise ValueError("Captura ou recepção declarada posterior ao corte")
    if type(entrada.event_session_timing) is not str or entrada.event_session_timing not in {
        "BEFORE_OPEN",
        "AFTER_CLOSE",
        "UNKNOWN",
    }:
        raise ValueError("Momento do evento inválido")
    if type(entrada.budget_kind) is not str or entrada.budget_kind not in {
        "SCENARIO_LOSS_BUDGET",
        "ABSOLUTE_LOSS_CAP",
    }:
        raise ValueError("Orçamento fora do contrato")
    if type(entrada.novo_short_bloqueado) is not bool:
        raise ValueError("Veto exige bool nativo")
    _referencia(entrada.config_body_ref)
    for nome in ("event_windows_utc", "cenarios", "native_caps_abs_weight"):
        if type(getattr(entrada, nome)) is not tuple:
            raise ValueError(f"{nome}: tuple nativa obrigatória")
    for janela in entrada.event_windows_utc:
        if type(janela) is not JanelaEarnings:
            raise ValueError("Janela fora do tipo fechado")
        _utc(janela.inicio_utc, "inicio_utc")
        _utc(janela.fim_utc, "fim_utc")
        if janela.inicio_utc > janela.fim_utc:
            raise ValueError("Intervalo de evento invertido")
        if type(janela.status) is not str or janela.status not in {"CONFIRMED", "ESTIMATED"}:
            raise ValueError("Status do evento inválido")
        _referencia(janela.source_ref)
    ids = set()
    for cenario in entrada.cenarios:
        if type(cenario) is not CenarioEarnings:
            raise ValueError("Cenário fora do tipo fechado")
        _texto(cenario.id, "id_cenario")
        if cenario.id in ids:
            raise ValueError("Cenário duplicado")
        ids.add(cenario.id)
        _numero(cenario.movimento_preco_total_usd, "movimento_preco_total_usd")
        if cenario.movimento_preco_total_usd < -1.0:
            raise ValueError("Retorno de preço total menor que perda integral")
        _referencia(cenario.source_ref)
        if type(cenario.label) is not str or cenario.label not in {
            "HUMAN_SCENARIO_PREDECLARED",
            "SIMULATED_TEST_ONLY",
        }:
            raise ValueError("Origem do cenário inválida")
    for nome in ("proportional_cost_period", "borrow_period", "financing_period"):
        value = getattr(entrada, nome)
        if value is not None:
            _numero(value, nome, negativo=nome == "financing_period")
    for limite in entrada.native_caps_abs_weight:
        if limite is not None:
            _numero(limite, "native_caps_abs_weight", negativo=False)


def dimensionar_earnings_sombra(entrada: EntradaEarnings) -> DiagnosticoEarnings:
    """Calcula B/(perda adversa+custo) sob cenários explicitamente recebidos.

    Referências e campos de linha/período são declarações, não prova PIT. Todos
    os custos são coeficientes por unidade de nocional no mesmo período.
    """
    _validar(entrada)
    ids = tuple(c.id for c in entrada.cenarios)

    def resultado(estado, motivo, perda=None, custo=None, cap=None, conjunto=None, peso=None):
        return DiagnosticoEarnings(
            estado,
            motivo,
            ids,
            entrada.event_windows_utc,
            perda,
            custo,
            cap,
            conjunto,
            peso,
            entrada.novo_short_bloqueado,
        )

    atual, candidato = entrada.weight_current, entrada.weight_candidate
    if (atual < 0.0 < candidato) or (candidato < 0.0 < atual):
        return resultado("FORA_DO_ESCOPO", "Troca de lado requer contrato próprio")
    referencia = candidato if candidato != 0.0 else atual
    if referencia == 0.0:
        return resultado("INSUFICIENTE", "Sem lado da posição para avaliar cenário")
    if entrada.budget_kind == "ABSOLUTE_LOSS_CAP":
        return resultado("FORA_DO_ESCOPO", "Cenários não certificam perda máxima absoluta")
    if entrada.novo_short_bloqueado and candidato < 0.0 and abs(candidato) > max(0.0, -atual):
        return resultado("FORA_DO_ESCOPO", "Veto nativo de novo short preservado")
    if not entrada.event_windows_utc or not entrada.cenarios:
        return resultado("INSUFICIENTE", "Evento ou cenários ausentes")
    sinal = 1.0 if referencia > 0.0 else -1.0
    perda = max(max(0.0, -sinal * c.movimento_preco_total_usd) for c in entrada.cenarios)
    if perda == 0.0:
        return resultado("INSUFICIENTE", "Sem cenário adverso; limite desconhecido", perda)
    custos = (entrada.proportional_cost_period, entrada.borrow_period, entrada.financing_period)
    if any(c is None for c in custos):
        return resultado("INSUFICIENTE", "Custos do período ausentes", perda)
    custo = sum(custos)
    if not math.isfinite(custo):
        raise ValueError("Overflow no agregado de custos")
    if custo < 0.0:
        return resultado("INSUFICIENTE", "Crédito líquido exige contrato próprio", perda, custo)
    denominador = perda + custo
    if not math.isfinite(denominador):
        raise ValueError("Overflow na perda por unidade")
    cap = entrada.scenario_budget_nav / denominador
    if not math.isfinite(cap):
        raise ValueError("Overflow no limite de cenários")
    if not entrada.native_caps_abs_weight or any(c is None for c in entrada.native_caps_abs_weight):
        return resultado("INSUFICIENTE", "Restrições nativas incompletas", perda, custo, cap)
    conjunto = min((cap, *entrada.native_caps_abs_weight))
    peso = sinal * min(abs(candidato), conjunto)
    return resultado(
        "CONDICIONAL_CENARIOS",
        "Sem escolha ou autoridade operacional",
        perda,
        custo,
        cap,
        conjunto,
        peso,
    )
