"""Viés de risco em sombra: descrição e intervalo IID adaptado do NIST.

Entradas são declarações explícitas, sem recepção física, PIT ou autoridade de
escrita. Não há livro, configuração global, relógio, I/O ou modelo de risco.
O arredondamento floor da média aparada é adaptação CDP, não reprodução integral
do paper de Bonett. IID declarada nunca significa independência comprovada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import NormalDist, fmean, stdev
from typing import Literal

MetodoVies = Literal["descritivo", "nist_bonett_iid_floor_v1"]
HipoteseIID = Literal["DECLARADA_NAO_PROVADA", "DEPENDENCIA_CONHECIDA", "DESCONHECIDA"]


@dataclass(frozen=True, slots=True)
class ReferenciaCorpo:
    """Referência declarada; seu hash não autentica o corpo nem a disponibilidade."""

    body_id: str
    sha256: str
    locator: str
    kind: Literal["ORIGINAL_REF_NOT_REVALIDATED", "SIMULATED_TEST_ONLY"]


@dataclass(frozen=True, slots=True)
class ParRisco:
    """Previsão anterior e retorno de preços da mesma carteira/período em USD."""

    id: str
    inicio_utc: datetime
    fim_utc: datetime
    previsao_selada_utc: datetime
    modelo_as_of_utc: datetime
    carteira_abertura_hash: str
    previsao_carteira_hash: str
    forecast_body_ref: ReferenciaCorpo
    outcome_body_ref: ReferenciaCorpo
    retorno_precos_usd: float | None
    sigma_periodo: float | None
    horizonte_sessoes: int
    unidade: Literal["fracao_USD_mesmo_periodo"]
    nao_reprecificadas: int
    motivo_ausencia: str | None
    origem: Literal["PUBLICA_RECEBIDA", "SIMULADA_TESTE"]


@dataclass(frozen=True, slots=True)
class PoliticaVies:
    """Política explícita somente deste diagnóstico; não muda o mandato."""

    corte_utc: datetime
    minimo_descritivo: int
    metodo_inferencia: MetodoVies
    hipotese_iid: HipoteseIID
    alpha: float


@dataclass(frozen=True, slots=True)
class IntervaloDesvio:
    estado: Literal["CONDICIONAL_IID", "INSUFICIENTE"]
    metodo: Literal["nist_bonett_iid_floor_v1"]
    n: int
    alpha: float
    desvio: float | None
    curtose_ajustada: float | None
    proporcao_corte: float | None
    cortadas_por_cauda: int | None
    media_aparada: float | None
    inferior: float | None
    superior: float | None
    motivo: str | None
    limite: str


@dataclass(frozen=True, slots=True)
class DiagnosticoViesRisco:
    estado: Literal["DESCRITIVO", "CONDICIONAL_IID", "INSUFICIENTE"]
    corte_utc: datetime
    metodo_inferencia: MetodoVies
    hipotese_iid: HipoteseIID
    n_total: int
    n: int
    incluidos: tuple[str, ...]
    excluidos: tuple[tuple[str, str], ...]
    media_z: float | None
    sd_z: float | None
    rms_z: float | None
    excesso_curtose_descritivo: float | None
    sobreposicao: bool
    intervalo: IntervaloDesvio | None
    interpretacao: Literal["SUBPREVISAO_CONDICIONAL", "SOBREPREVISAO_CONDICIONAL",
                           "INCONCLUSIVO", "SEM_INFERENCIA"]
    motivo: str | None
    vinculos_declarados: tuple[tuple[str, ...], ...]
    limites: tuple[str, ...]


_LIMITE_IID = (
    "IID declarada não foi comprovada; intervalo aproximado NIST com floor CDP, "
    "sem identidade integral ao paper Bonett ou garantia de cobertura financeira."
)
_LIMITES = (
    "Referências e hashes declarados não autenticam corpos, carteira, disponibilidade ou PIT.",
    "Sem calibração real, gate, mandato, aprovação, promoção ou escrita operacional.",
    _LIMITE_IID,
)


def _texto(v: object, nome: str) -> None:
    if type(v) is not str or not v.strip():
        raise ValueError(f"{nome}: texto nativo não vazio obrigatório")


def _opcao(v: object, opcoes: tuple[str, ...], nome: str) -> None:
    if type(v) is not str or v not in opcoes:
        raise ValueError(f"{nome}: opção textual nativa inválida")


def _hash(v: object, nome: str) -> None:
    if type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
        raise ValueError(f"{nome}: SHA-256 hexadecimal nativo obrigatório")


def _utc(v: object, nome: str) -> None:
    # Nenhum utcoffset/astimezone de tzinfo livre é chamado.
    if type(v) is not datetime or v.tzinfo is not UTC or v.fold != 0:
        raise ValueError(f"{nome}: datetime nativo em UTC obrigatório")


def _numero(v: object, nome: str) -> None:
    if type(v) is not float or not math.isfinite(v):
        raise ValueError(f"{nome}: float nativo finito obrigatório")


def _natural(v: object, minimo: int, nome: str) -> None:
    if type(v) is not int or v < minimo:
        raise ValueError(f"{nome}: inteiro nativo fora da faixa")


def _alpha(v: object) -> None:
    _numero(v, "alpha")
    if not 0.0 < v < 0.5:
        raise ValueError("alpha deve estar estritamente entre zero e 0.5")


def _referencia(v: object) -> None:
    if type(v) is not ReferenciaCorpo:
        raise ValueError("Referência deve ter o tipo nativo exato")
    _texto(v.body_id, "body_id")
    _hash(v.sha256, "sha256")
    _texto(v.locator, "locator")
    _opcao(v.kind, ("ORIGINAL_REF_NOT_REVALIDATED", "SIMULATED_TEST_ONLY"), "kind")


def _validar_politica(p: object) -> None:
    if type(p) is not PoliticaVies:
        raise ValueError("Política deve ter o tipo nativo exato")
    _utc(p.corte_utc, "corte_utc")
    _natural(p.minimo_descritivo, 2, "minimo_descritivo")
    _opcao(p.metodo_inferencia, ("descritivo", "nist_bonett_iid_floor_v1"), "método")
    _opcao(p.hipotese_iid,
           ("DECLARADA_NAO_PROVADA", "DEPENDENCIA_CONHECIDA", "DESCONHECIDA"), "IID")
    _alpha(p.alpha)


def _validar_par(p: object, politica: PoliticaVies) -> None:
    if type(p) is not ParRisco:
        raise ValueError("Par deve ter o tipo nativo exato")
    _texto(p.id, "id")
    for nome in ("inicio_utc", "fim_utc", "previsao_selada_utc", "modelo_as_of_utc"):
        _utc(getattr(p, nome), nome)
    _hash(p.carteira_abertura_hash, "carteira_abertura_hash")
    _hash(p.previsao_carteira_hash, "previsao_carteira_hash")
    _referencia(p.forecast_body_ref)
    _referencia(p.outcome_body_ref)
    if p.retorno_precos_usd is not None:
        _numero(p.retorno_precos_usd, "retorno_precos_usd")
    if p.sigma_periodo is not None:
        _numero(p.sigma_periodo, "sigma_periodo")
        if p.sigma_periodo <= 0.0:
            raise ValueError("sigma_periodo deve ser positiva")
    _natural(p.horizonte_sessoes, 1, "horizonte_sessoes")
    _natural(p.nao_reprecificadas, 0, "nao_reprecificadas")
    _opcao(p.unidade, ("fracao_USD_mesmo_periodo",), "unidade")
    _opcao(p.origem, ("PUBLICA_RECEBIDA", "SIMULADA_TESTE"), "origem")
    if p.motivo_ausencia is not None:
        _texto(p.motivo_ausencia, "motivo_ausencia")
    incompleto = (p.retorno_precos_usd is None or p.sigma_periodo is None
                  or p.nao_reprecificadas > 0)
    if incompleto != (p.motivo_ausencia is not None):
        raise ValueError("Motivo de ausência deve identificar exatamente um par incompleto")
    if not p.previsao_selada_utc <= p.inicio_utc < p.fim_utc <= politica.corte_utc:
        raise ValueError("Previsão, intervalo e corte têm ordem temporal inválida")
    if p.modelo_as_of_utc > p.previsao_selada_utc:
        raise ValueError("Modelo posterior ao selo da previsão")
    if p.carteira_abertura_hash != p.previsao_carteira_hash:
        raise ValueError("Identidades declaradas da carteira de abertura diferem")
    esperado = ("SIMULATED_TEST_ONLY" if p.origem == "SIMULADA_TESTE"
                else "ORIGINAL_REF_NOT_REVALIDATED")
    if p.forecast_body_ref.kind != esperado or p.outcome_body_ref.kind != esperado:
        raise ValueError("Origem e tipo de referência declarada não conferem")


def _momentos(amostra: tuple[float, ...]) -> tuple[float, float, float, float | None]:
    media = fmean(amostra)
    sd = stdev(amostra)
    escala = max(abs(v) for v in amostra)
    rms = (escala * math.sqrt(math.fsum((v / escala) ** 2 for v in amostra) / len(amostra))
           if escala > 0.0 else 0.0)
    escala_centrada = max(abs(v - media) for v in amostra)
    curtose = None
    if escala_centrada > 0.0:
        d = tuple((v - media) / escala_centrada for v in amostra)
        soma2 = math.fsum(v * v for v in d)
        curtose = len(amostra) * math.fsum(v ** 4 for v in d) / soma2 ** 2 - 3.0
    if not all(math.isfinite(v) for v in (media, sd, rms)) \
            or (curtose is not None and not math.isfinite(curtose)):
        raise OverflowError("Momentos não representáveis")
    return media, sd, rms, curtose


def intervalo_desvio_nist(amostra: tuple[float, ...], *, alpha: float) -> IntervaloDesvio:
    """Intervalo aproximado de σ populacional IID, com floor CDP explícito.

    Todas as observações ficam em s² e nos momentos. Apenas a média usada em g4
    é aparada. Não transforma caudas, não estima independência nem recebe prior.
    Ausência não é aceita nesta amostra; o diagnóstico de pares preserva a máscara.
    """
    if type(amostra) is not tuple:
        raise ValueError("Amostra deve ser uma tupla nativa")
    _alpha(alpha)
    for v in amostra:
        _numero(v, "amostra")
    n = len(amostra)
    sd = g4 = q = m = inferior = superior = None
    k = None
    motivo = None
    if n <= 4:
        motivo = "N_ATE_QUATRO"
    else:
        try:
            media, sd, _, _ = _momentos(amostra)
            if sd == 0.0:
                motivo = "VARIANCIA_NULA"
            else:
                q = 1.0 / (2.0 * math.sqrt(n - 4))
                k = math.floor(n * q)
                ordenada = sorted(amostra)
                miolo = ordenada[k:n - k]
                if not miolo:
                    raise ValueError("Cauda aparada sem observações")
                m = fmean(miolo)
                escala = max(abs(v - media) for v in amostra)
                soma2 = math.fsum(((v - media) / escala) ** 2 for v in amostra)
                g4 = n * math.fsum(((v - m) / escala) ** 4 for v in amostra) / soma2 ** 2
                zcrit = NormalDist().inv_cdf(1.0 - alpha / 2.0)
                if n - zcrit <= 0.0:
                    raise ValueError("Correção finita não positiva")
                c = n / (n - zcrit)
                radicando = (g4 - (n - 3.0) / n) / (n - 1.0)
                if radicando < 0.0:
                    raise ValueError("Erro-padrão não real")
                se = c * math.sqrt(radicando)
                centro_log = math.log(sd) + 0.5 * math.log(c)
                inferior = math.exp(centro_log - 0.5 * zcrit * se)
                superior = math.exp(centro_log + 0.5 * zcrit * se)
                if not all(math.isfinite(v) for v in (m, g4, inferior, superior)) \
                        or not 0.0 < inferior <= superior:
                    raise OverflowError("Intervalo não representável")
        except (OverflowError, ValueError, ZeroDivisionError):
            inferior = superior = None
            sd = sd if sd is None or math.isfinite(sd) else None
            g4 = g4 if g4 is None or math.isfinite(g4) else None
            m = m if m is None or math.isfinite(m) else None
            motivo = "ARITMETICA_NAO_REPRESENTAVEL"
    return IntervaloDesvio(
        estado="CONDICIONAL_IID" if motivo is None else "INSUFICIENTE",
        metodo="nist_bonett_iid_floor_v1", n=n, alpha=alpha, desvio=sd,
        curtose_ajustada=g4, proporcao_corte=q, cortadas_por_cauda=k,
        media_aparada=m, inferior=inferior, superior=superior, motivo=motivo, limite=_LIMITE_IID,
    )


def diagnosticar_vies_risco(pares: tuple[ParRisco, ...], politica: PoliticaVies
                           ) -> DiagnosticoViesRisco:
    """Descreve r/σ e somente infere sob IID declarada e períodos sem sobreposição.

    Custos/financiamento não são subtraídos nem incorporados silenciosamente.
    Referências são conservadas como declarações; nenhum corpo é aberto/revalidado.
    """
    if type(pares) is not tuple:
        raise ValueError("Pares devem ser uma tupla nativa")
    _validar_politica(politica)
    ids: set[str] = set()
    periodos: set[tuple[datetime, datetime]] = set()
    horizonte = None
    for p in pares:
        _validar_par(p, politica)
        if p.id in ids or (p.inicio_utc, p.fim_utc) in periodos:
            raise ValueError("Id ou período duplicado")
        ids.add(p.id)
        periodos.add((p.inicio_utc, p.fim_utc))
        if horizonte is not None and p.horizonte_sessoes != horizonte:
            raise ValueError("Horizontes de sessão incompatíveis")
        horizonte = p.horizonte_sessoes
    incluidos: list[str] = []
    excluidos: list[tuple[str, str]] = []
    amostra: list[float] = []
    intervalos: list[tuple[datetime, datetime]] = []
    vinculos: list[tuple[str, ...]] = []
    for p in pares:
        f, o = p.forecast_body_ref, p.outcome_body_ref
        vinculos.append((p.id, f.body_id, f.sha256, f.locator, f.kind,
                         o.body_id, o.sha256, o.locator, o.kind, p.origem))
        if p.motivo_ausencia is not None:
            excluidos.append((p.id, p.motivo_ausencia))
            continue
        z = p.retorno_precos_usd / p.sigma_periodo
        if not math.isfinite(z):
            raise ValueError("Retorno normalizado não representável")
        amostra.append(z)
        incluidos.append(p.id)
        intervalos.append((p.inicio_utc, p.fim_utc))
    ordenados = sorted(intervalos)
    sobreposicao = any(a[1] > b[0]
                      for a, b in zip(ordenados[:-1], ordenados[1:], strict=True))
    valores = tuple(amostra)
    media = sd = rms = curtose = None
    intervalo = None
    interpretacao = "SEM_INFERENCIA"
    motivo = None
    estado = "DESCRITIVO"
    if len(valores) < politica.minimo_descritivo:
        estado, motivo = "INSUFICIENTE", "AMOSTRA_DESCRITIVA_INSUFICIENTE"
    else:
        try:
            media, sd, rms, curtose = _momentos(valores)
        except (OverflowError, ValueError, ZeroDivisionError):
            estado, motivo = "INSUFICIENTE", "MOMENTOS_NAO_REPRESENTAVEIS"
        if motivo is None and politica.metodo_inferencia != "descritivo":
            if sobreposicao:
                motivo = "SOBREPOSICAO_SEM_INFERENCIA_IID"
            elif politica.hipotese_iid != "DECLARADA_NAO_PROVADA":
                motivo = "IID_NAO_DECLARADA_SEM_INFERENCIA"
            else:
                intervalo = intervalo_desvio_nist(valores, alpha=politica.alpha)
                if intervalo.estado == "CONDICIONAL_IID":
                    estado = "CONDICIONAL_IID"
                    interpretacao = ("SUBPREVISAO_CONDICIONAL" if intervalo.inferior > 1.0
                                     else "SOBREPREVISAO_CONDICIONAL" if intervalo.superior < 1.0
                                     else "INCONCLUSIVO")
                else:
                    motivo = intervalo.motivo
    limites = _LIMITES
    if any(p.origem == "SIMULADA_TESTE" for p in pares):
        limites += ("DADOS SIMULADOS: entradas de teste não são observações financeiras reais.",)
    return DiagnosticoViesRisco(
        estado=estado, corte_utc=politica.corte_utc,
        metodo_inferencia=politica.metodo_inferencia, hipotese_iid=politica.hipotese_iid,
        n_total=len(pares), n=len(valores), incluidos=tuple(incluidos), excluidos=tuple(excluidos),
        media_z=media, sd_z=sd, rms_z=rms, excesso_curtose_descritivo=curtose,
        sobreposicao=sobreposicao, intervalo=intervalo, interpretacao=interpretacao,
        motivo=motivo, vinculos_declarados=tuple(vinculos), limites=limites,
    )
