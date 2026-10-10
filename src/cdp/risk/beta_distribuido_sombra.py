"""Regressão histórica BIS164 com três colunas; diagnóstico sem autoridade."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np


@dataclass(frozen=True)
class ReferenciaBeta:
    """Hash declarado: esta função pura não recebe nem autentica arquivos."""

    body_id: str
    sha256: str
    tipo: str


@dataclass(frozen=True)
class ObservacaoBeta:
    ordinal_sessao: int
    fim_sessao_utc: datetime
    retorno_excedente_carteira: float | None
    retorno_excedente_mercado: float | None
    carteira_disponivel_declarada_utc: datetime | None
    mercado_disponivel_declarada_utc: datetime | None
    ausencia_carteira: str
    ausencia_mercado: str


@dataclass(frozen=True)
class EntradaBetaDistribuido:
    linha_carteira: str
    mercado: str
    base: str
    horizonte: str
    corte_utc: datetime
    historia_ref: ReferenciaBeta
    mercado_ref: ReferenciaBeta
    taxa_livre_ref: ReferenciaBeta
    calendario_ref: ReferenciaBeta
    observacoes: tuple[ObservacaoBeta, ...]


@dataclass(frozen=True)
class ExclusaoBeta:
    ordinal_sessao: int
    motivos: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosticoBetaDistribuido:
    entrada: EntradaBetaDistribuido
    estado: str
    motivos: tuple[str, ...]
    centros_utilizados: tuple[int, ...]
    exclusoes: tuple[ExclusaoBeta, ...]
    posto: int | None
    valores_singulares_normalizados: tuple[float, ...]
    coeficientes_lag_atual_lead: tuple[float, float, float] | None
    beta_agregado: float | None
    beta_contemporaneo_mesma_mascara: float | None
    rcond_tecnico: float = field(default=1e-12, init=False)
    intercepto: bool = field(default=False, init=False)
    autoridade_operacional: bool = field(default=False, init=False)
    autenticidade_referencias: str = field(default="NAO_VERIFICADA", init=False)
    qualificacao_pit: str = field(default="NAO_DEMONSTRADA", init=False)


def _texto(x: object, nome: str) -> None:
    if type(x) is not str or not x:
        raise ValueError(f"{nome}: texto nativo não vazio obrigatório")


def _utc(x: object, nome: str) -> None:
    if type(x) is not datetime or x.tzinfo is not UTC or x.fold != 0:
        raise ValueError(f"{nome}: datetime nativo UTC sem fold obrigatório")


def _ref(x: object) -> None:
    if type(x) is not ReferenciaBeta:
        raise ValueError("Referência fora do tipo nominal fechado")
    _texto(x.body_id, "body_id")
    if type(x.sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", x.sha256) is None:
        raise ValueError("SHA-256 declarado inválido")
    if type(x.tipo) is not str or x.tipo not in {
        "ORIGINAL_REF_NOT_REVALIDATED",
        "SIMULATED_TEST_ONLY",
    }:
        raise ValueError("Tipo de referência inválido")


def _validar(x: object) -> None:
    if type(x) is not EntradaBetaDistribuido:
        raise ValueError("Entrada fora do tipo nominal fechado")
    _texto(x.linha_carteira, "linha_carteira")
    _texto(x.mercado, "mercado")
    if type(x.base) is not str or x.base != "USD_EXCESS_RETURN_SAME_SESSIONS":
        raise ValueError("Carteira, mercado e taxa livre exigem mesma base excedente USD")
    if type(x.horizonte) is not str or x.horizonte not in {"SESSAO", "SEMANA"}:
        raise ValueError("Horizonte declarado inválido")
    _utc(x.corte_utc, "corte_utc")
    for ref in (x.historia_ref, x.mercado_ref, x.taxa_livre_ref, x.calendario_ref):
        _ref(ref)
    if type(x.observacoes) is not tuple or len(x.observacoes) > 100_000:
        raise ValueError("Sequência nativa ou limite técnico inválido")
    anterior = None
    for obs in x.observacoes:
        if type(obs) is not ObservacaoBeta:
            raise ValueError("Observação fora do tipo nominal fechado")
        if type(obs.ordinal_sessao) is not int or obs.ordinal_sessao < 0:
            raise ValueError("Ordinal inteiro nativo não negativo obrigatório")
        _utc(obs.fim_sessao_utc, "fim_sessao_utc")
        if anterior is not None and (
            obs.ordinal_sessao != anterior.ordinal_sessao + 1
            or obs.fim_sessao_utc <= anterior.fim_sessao_utc
        ):
            raise ValueError("Sessões devem ser consecutivas, ordenadas e sem duplicidade")
        for valor, disponivel, motivo in (
            (
                obs.retorno_excedente_carteira,
                obs.carteira_disponivel_declarada_utc,
                obs.ausencia_carteira,
            ),
            (
                obs.retorno_excedente_mercado,
                obs.mercado_disponivel_declarada_utc,
                obs.ausencia_mercado,
            ),
        ):
            if type(motivo) is not str:
                raise ValueError("Razão de ausência exige texto nativo")
            if valor is None:
                if not motivo or disponivel is not None:
                    raise ValueError("Ausência exige razão e disponibilidade None")
            else:
                if type(valor) is not float or not math.isfinite(valor) or motivo:
                    raise ValueError("Retorno observado exige float finito e razão vazia")
                _utc(disponivel, "disponibilidade_declarada_utc")
                if disponivel < obs.fim_sessao_utc:
                    raise ValueError("Retorno completo não pode estar disponível antes da sessão")
        anterior = obs


def estimar_beta_distribuido_sombra(x: EntradaBetaDistribuido) -> DiagnosticoBetaDistribuido:
    """OLS conjunta sem intercepto; o lead histórico nunca autoriza previsão."""
    _validar(x)
    centros: list[int] = []
    exclusoes: list[ExclusaoBeta] = []
    linhas: list[list[float]] = []
    respostas: list[float] = []
    for i, obs in enumerate(x.observacoes):
        motivos = []
        if i == 0 or i == len(x.observacoes) - 1:
            motivos.append("PONTA_SEM_TRES_SESSOES")
        else:
            if obs.retorno_excedente_carteira is None:
                motivos.append("CARTEIRA_AUSENTE")
            elif obs.carteira_disponivel_declarada_utc > x.corte_utc:
                motivos.append("CARTEIRA_POSTERIOR_AO_CORTE")
            for papel, k in (("LAG", i - 1), ("ATUAL", i), ("LEAD", i + 1)):
                outro = x.observacoes[k]
                if outro.retorno_excedente_mercado is None:
                    motivos.append(f"MERCADO_{papel}_AUSENTE")
                elif outro.mercado_disponivel_declarada_utc > x.corte_utc:
                    motivos.append(f"MERCADO_{papel}_POSTERIOR_AO_CORTE")
        if motivos:
            exclusoes.append(ExclusaoBeta(obs.ordinal_sessao, tuple(motivos)))
        else:
            centros.append(obs.ordinal_sessao)
            linhas.append(
                [x.observacoes[k].retorno_excedente_mercado for k in (i - 1, i, i + 1)]
            )
            respostas.append(obs.retorno_excedente_carteira)

    def saida(
        estado: str,
        motivo: str,
        posto: int | None = None,
        singular: tuple[float, ...] = (),
        coef: tuple[float, float, float] | None = None,
        beta: float | None = None,
        atual: float | None = None,
    ) -> DiagnosticoBetaDistribuido:
        return DiagnosticoBetaDistribuido(
            x, estado, (motivo,), tuple(centros), tuple(exclusoes), posto, singular, coef, beta, atual
        )

    if len(centros) < 4:
        return saida("INSUFICIENTE_AMOSTRA", "Menos de quatro centros válidos")
    a = np.array(linhas, dtype=np.float64)
    y = np.array(respostas, dtype=np.float64)
    escala_x = float(np.max(np.abs(a)))
    escala_y = float(np.max(np.abs(y)))
    if escala_x == 0.0:
        return saida("INSUFICIENTE_POSTO", "Mercado observado inteiramente zero", 0)
    x_nao_zero, y_nao_zero = a != 0.0, y != 0.0
    y_inteiramente_zero = escala_y == 0.0
    a /= escala_x
    # y=0 continua observado zero; unidade é apenas normalização técnica.
    if escala_y == 0.0:
        escala_y = 1.0
    y /= escala_y
    if np.any(x_nao_zero & (a == 0.0)) or np.any(y_nao_zero & (y == 0.0)):
        return saida("INSUFICIENTE_NUMERICO", "Normalização perdeu observação não zero")
    try:
        coef, _, posto, singular = np.linalg.lstsq(a, y, rcond=1e-12)
    except np.linalg.LinAlgError:
        return saida("INSUFICIENTE_NUMERICO", "SVD sem convergência")
    sv = tuple(float(v) for v in singular)
    if not all(math.isfinite(v) for v in sv):
        return saida("INSUFICIENTE_NUMERICO", "Valores singulares não finitos")
    if posto != 3:
        return saida("INSUFICIENTE_POSTO", "Três colunas não identificáveis no rcond fixo", int(posto), sv)
    if y_inteiramente_zero:
        return saida(
            "CONDICIONAL_SEM_CALIBRACAO",
            "Resposta observada zero com posto3; autenticidade/PIT não demonstrados",
            3, sv, (0.0, 0.0, 0.0), 0.0, 0.0,
        )
    # Multiplicar depois de dividir pode transbordar: saída insuficiente, nunca clamp.
    try:
        escala_beta = escala_y / escala_x
        if escala_beta == 0.0 or not math.isfinite(escala_beta):
            return saida("INSUFICIENTE_NUMERICO", "Escala de coeficientes não representável", 3, sv)
        cs = tuple(float(v) * escala_beta for v in coef)
        agregado = math.fsum(cs)
        atual_normalizado = float(np.dot(a[:, 1], y) / np.dot(a[:, 1], a[:, 1]))
        contemporaneo = atual_normalizado * escala_beta
        if any(float(v) != 0.0 and c == 0.0 for v, c in zip(coef, cs, strict=True)) or (
            atual_normalizado != 0.0 and contemporaneo == 0.0
        ):
            return saida("INSUFICIENTE_NUMERICO", "Produto perdeu coeficiente não zero", 3, sv)
    except (OverflowError, ZeroDivisionError):
        return saida("INSUFICIENTE_NUMERICO", "Escala de coeficientes não representável", 3, sv)
    if not all(math.isfinite(v) for v in (*cs, agregado, contemporaneo)):
        return saida("INSUFICIENTE_NUMERICO", "Coeficientes não finitos", 3, sv)
    return saida(
        "CONDICIONAL_SEM_CALIBRACAO",
        "Regressão explicativa histórica; autenticidade, PIT e correção de viés não demonstrados",
        3,
        sv,
        cs,
        agregado,
        contemporaneo,
    )
