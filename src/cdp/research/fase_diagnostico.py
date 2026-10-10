"""IC e fase consultiva por identidade original; sem consumidor ou autenticação física.

Referências e hipóteses são declarações. Dados simulados/replay não promovem fase;
a configuração global e o registro de modelos nunca são lidos ou alterados.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import mean, stdev

MIN_IC_OBS = 3
PHASES = ("S0", "S1", "S2", "S3")
UNIDADE = "fracao_residual_USD_mesmo_horizonte"


class EntradaFaseInvalida(ValueError):
    """Contradição ou tipo malformado, antes de qualquer recomendação."""


@dataclass(frozen=True, slots=True)
class ChaveGrupo:
    mind_original: str | None
    provider_original: str | None
    model_snapshot_original: str | None
    channel: str


@dataclass(frozen=True, slots=True)
class AmostraIC:
    id_coorte: str
    grupo: ChaveGrupo
    inicio_utc: datetime
    fim_utc: datetime
    previsao_selada_utc: datetime
    modelo_as_of_utc: datetime | None
    deadline_utc: datetime
    outcome_selado_utc: datetime | None
    cohort_ref: str | None
    binding_ref: str | None
    outcome_ref: str | None
    linhagem_chamadas: tuple[str, ...]
    modelos_observados: tuple[str, ...]
    identity_state: str
    tentativas_modelo: int
    origem: str
    macro_base_policy_hash: str
    horizonte_sessoes: int
    unidade: str
    emissores: tuple[str, ...]
    ai_scores: tuple[float | None, ...]
    quant_scores: tuple[float | None, ...]
    realized_residuals_usd: tuple[float | None, ...]
    autoria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PoliticaFase:
    corte_utc: datetime
    horizonte_sessoes: int
    macro_base_policy_hash: str
    unidade: str
    escopo_fase: str
    referencia_fase: str | None
    comparisons_scope_ref: str | None
    comparisons_seladas_utc: datetime | None
    independencia: str


@dataclass(frozen=True, slots=True)
class CoorteIC:
    id_coorte: str
    inicio_utc: datetime
    fim_utc: datetime
    emissores_incluidos: tuple[str, ...]
    emissores_excluidos: tuple[tuple[str, str], ...]
    n_ai: int
    n_quant: int
    n_incremental: int
    ic_ai: float | None
    ic_quant: float | None
    ic_incremental: float | None
    impedimentos: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EstatisticasIC:
    n_semanas: int
    media: float | None
    desvio_ddof1: float | None
    icir: float | None
    t_iid_descritivo: float | None


@dataclass(frozen=True, slots=True)
class RecomendacaoFase:
    grupo: ChaveGrupo
    estado: str
    fase_referencia: str | None
    escopo_fase: str
    fase_sugerida: str | None
    motivo: str
    coortes: tuple[CoorteIC, ...]
    coortes_outros_grupos: tuple[str, ...]
    ids_elegiveis_declarados: tuple[str, ...]
    ic_ai_descritivo: EstatisticasIC
    ic_quant_descritivo: EstatisticasIC
    ic_incremental_descritivo: EstatisticasIC
    impedimentos: tuple[str, ...]
    qualificacao_t: str
    autoridade: str
    autoriza_promocao: bool = False


def _text(value: object, name: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if type(value) is not str or not value.strip():
        raise EntradaFaseInvalida(f"{name}: string nativa não vazia obrigatória.")


def _enum(value: object, name: str, values: tuple[str, ...]) -> None:
    _text(value, name)
    if value not in values:
        raise EntradaFaseInvalida(f"{name}: valor fora do contrato.")


def _utc(value: object, name: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if type(value) is not datetime or value.tzinfo is not UTC or value.fold != 0:
        raise EntradaFaseInvalida(f"{name}: datetime nativo com UTC literal obrigatório.")


def _positive_int(value: object, name: str) -> None:
    if type(value) is not int or value < 1:
        raise EntradaFaseInvalida(f"{name}: inteiro nativo positivo obrigatório.")


def _hash(value: object, name: str) -> None:
    _text(value, name)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise EntradaFaseInvalida(f"{name}: SHA-256 literal obrigatório, sem autenticação implícita.")


def _tuple(value: object, name: str) -> None:
    if type(value) is not tuple:
        raise EntradaFaseInvalida(f"{name}: tupla nativa obrigatória.")


def _group(group: object) -> None:
    if type(group) is not ChaveGrupo:
        raise EntradaFaseInvalida("grupo: ChaveGrupo exata obrigatória.")
    for name in ("mind_original", "provider_original", "model_snapshot_original"):
        _text(getattr(group, name), name, optional=True)
    _enum(group.channel, "channel", ("quant", "pesquisa_ai", "mente_final"))


def _policy(policy: object, reference: object) -> None:
    if type(policy) is not PoliticaFase:
        raise EntradaFaseInvalida("politica: PoliticaFase exata obrigatória.")
    _utc(policy.corte_utc, "corte_utc")
    _positive_int(policy.horizonte_sessoes, "horizonte_sessoes")
    _hash(policy.macro_base_policy_hash, "macro_base_policy_hash")
    _enum(policy.unidade, "unidade", (UNIDADE,))
    _enum(policy.escopo_fase, "escopo_fase",
          ("GRUPO_REFERENCIA_HUMANA", "GLOBAL_APENAS_CONTEXTO", "DESCONHECIDO"))
    _enum(policy.independencia, "independencia",
          ("DECLARADA_NAO_PROVADA", "SOBREPOSTA_OU_DEPENDENTE", "DESCONHECIDA"))
    _text(policy.referencia_fase, "referencia_fase", optional=True)
    _text(policy.comparisons_scope_ref, "comparisons_scope_ref", optional=True)
    _utc(policy.comparisons_seladas_utc, "comparisons_seladas_utc", optional=True)
    if (policy.comparisons_scope_ref is None) != (policy.comparisons_seladas_utc is None):
        raise EntradaFaseInvalida("Comparações: referência e selo devem estar ambos presentes/ausentes.")
    if reference is not None:
        _enum(reference, "fase_referencia", PHASES)


def _sample(sample: object, policy: PoliticaFase) -> None:
    if type(sample) is not AmostraIC:
        raise EntradaFaseInvalida("amostra: AmostraIC exata obrigatória.")
    _group(sample.grupo)
    _text(sample.id_coorte, "id_coorte")
    for name in ("inicio_utc", "fim_utc", "previsao_selada_utc", "deadline_utc"):
        _utc(getattr(sample, name), name)
    for name in ("modelo_as_of_utc", "outcome_selado_utc"):
        _utc(getattr(sample, name), name, optional=True)
    if not sample.previsao_selada_utc <= sample.inicio_utc < sample.fim_utc:
        raise EntradaFaseInvalida("Cronologia exige selo <= início < fim.")
    if sample.modelo_as_of_utc is not None and sample.modelo_as_of_utc > sample.previsao_selada_utc:
        raise EntradaFaseInvalida("Modelo as-of posterior ao selo da previsão.")
    if sample.deadline_utc > sample.inicio_utc:
        raise EntradaFaseInvalida("Deadline posterior ao início do retorno.")
    if sample.outcome_selado_utc is not None and sample.outcome_selado_utc < sample.fim_utc:
        raise EntradaFaseInvalida("Outcome declarado antes do fim do retorno.")
    for name in ("cohort_ref", "binding_ref", "outcome_ref"):
        _text(getattr(sample, name), name, optional=True)
    for name in ("linhagem_chamadas", "modelos_observados"):
        vector = getattr(sample, name)
        _tuple(vector, name)
        for item in vector:
            _text(item, name)
        if len(set(vector)) != len(vector):
            raise EntradaFaseInvalida(f"{name}: duplicata.")
    _enum(sample.identity_state, "identity_state",
          ("ORIGINAL_UNIQUE_COMPLETE", "MISSING", "MIXED", "ALIAS_UNRESOLVED"))
    _enum(sample.origem, "origem", ("PUBLICA_RECEBIDA", "SIMULADA_TESTE", "REPLAY"))
    _positive_int(sample.tentativas_modelo, "tentativas_modelo")
    _positive_int(sample.horizonte_sessoes, "horizonte_sessoes")
    _hash(sample.macro_base_policy_hash, "macro_base_policy_hash")
    _enum(sample.unidade, "unidade", (UNIDADE,))
    if (sample.unidade, sample.horizonte_sessoes, sample.macro_base_policy_hash) != (
        policy.unidade, policy.horizonte_sessoes, policy.macro_base_policy_hash
    ):
        raise EntradaFaseInvalida("Horizonte/unidade/base macro diferentes da política explícita.")
    for name in ("emissores", "ai_scores", "quant_scores", "realized_residuals_usd", "autoria"):
        _tuple(getattr(sample, name), name)
    if len({len(getattr(sample, name)) for name in (
        "emissores", "ai_scores", "quant_scores", "realized_residuals_usd", "autoria"
    )}) != 1:
        raise EntradaFaseInvalida("Vetores por emissor têm comprimentos diferentes.")
    for iid in sample.emissores:
        _text(iid, "emissor")
    if len(set(sample.emissores)) != len(sample.emissores):
        raise EntradaFaseInvalida("Emissor duplicado na coorte.")
    for vector in (sample.ai_scores, sample.quant_scores, sample.realized_residuals_usd):
        for value in vector:
            if value is not None and (type(value) is not float or not math.isfinite(value)):
                raise EntradaFaseInvalida("Score/retorno exige float nativo finito ou None explícito.")
    for author in sample.autoria:
        _enum(author, "autoria", ("confirmed", "absent", "external", "not_applicable"))


def _ranks(values: tuple[float, ...]) -> tuple[float, ...]:
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and values[ordered[j]] == values[ordered[i]]:
            j += 1
        rank = (i + 1 + j) / 2.0
        for index in ordered[i:j]:
            ranks[index] = rank
        i = j
    return tuple(ranks)


def _spearman(x: tuple[float, ...], y: tuple[float, ...]) -> float | None:
    if len(x) < MIN_IC_OBS:
        return None
    a, b = _ranks(x), _ranks(y)
    abar, bbar = mean(a), mean(b)
    aa = tuple(v - abar for v in a)
    bb = tuple(v - bbar for v in b)
    denominator = math.hypot(*aa) * math.hypot(*bb)
    if denominator == 0.0:
        return None
    return math.fsum(i * j for i, j in zip(aa, bb, strict=True)) / denominator


def _incremental(ai: tuple[float, ...], quant: tuple[float, ...],
                 outcome: tuple[float, ...]) -> float | None:
    if len(ai) < MIN_IC_OBS:
        return None
    # Escala local positiva: mesma MQO com intercepto, sem alterar arrays de entrada.
    scale_ai = max(1.0, max(abs(v) for v in ai))
    scale_q = max(abs(v) for v in quant) or 1.0
    y, x = tuple(v / scale_ai for v in ai), tuple(v / scale_q for v in quant)
    ybar, xbar = mean(y), mean(x)
    yc, xc = tuple(v - ybar for v in y), tuple(v - xbar for v in x)
    xx = math.fsum(v * v for v in xc)
    slope = math.fsum(a * b for a, b in zip(xc, yc, strict=True)) / xx if xx else 0.0
    residual = tuple(a - slope * b for a, b in zip(yc, xc, strict=True))
    # Piso nativo em unidades normalizadas; resíduo de arredondamento não é informação.
    threshold = 64 * sys.float_info.epsilon * max(1.0 / scale_ai, math.hypot(*y))
    if math.hypot(*residual) <= threshold:
        return None
    return _spearman(residual, outcome)


def _statistics(values: tuple[float, ...]) -> EstatisticasIC:
    if not values:
        return EstatisticasIC(0, None, None, None, None)
    avg = mean(values)
    sd = stdev(values) if len(values) >= 2 else None
    ratio = avg / sd if sd is not None and sd > 0.0 else None
    return EstatisticasIC(len(values), avg, sd, ratio,
                          ratio * math.sqrt(len(values)) if ratio is not None else None)


def _fase_nativa(ai: tuple[float, ...], incremental: tuple[float, ...],
                 reference: str) -> tuple[str, str]:
    """Política matemática isolada; não recebe/prova coorte nem autoriza promoção."""
    if len(ai) >= 13:
        recent = _statistics(ai[-13:])
        if (recent.media < 0.0 and recent.t_iid_descritivo is not None
                and recent.t_iid_descritivo <= -1.5):
            return "S0", "REBAIXAMENTO_NATIVO_13_SEMANAS"
    if reference == "S0":
        stats = _statistics(ai)
        if stats.n_semanas >= 13 and stats.icir is not None and stats.icir >= 0.5:
            return "S1", "LIMIAR_NATIVO_S0_S1"
        return "S0", "LIMIAR_S1_NAO_ATINGIDO_OU_INDEFINIDO"
    if reference in ("S1", "S2"):
        count, limit, next_phase = (26, 1.5, "S2") if reference == "S1" else (52, 2.0, "S3")
        stats = _statistics(incremental)
        if (stats.n_semanas >= count and stats.t_iid_descritivo is not None
                and stats.t_iid_descritivo >= limit):
            return next_phase, f"LIMIAR_NATIVO_{reference}_{next_phase}"
        return reference, "LIMIAR_INCREMENTAL_NAO_ATINGIDO_OU_INDEFINIDO"
    return "S3", "FASE_MAXIMA_SEM_PROMOCAO"


def _cohort(sample: AmostraIC, policy: PoliticaFase) -> CoorteIC:
    blockers = []
    if sample.previsao_selada_utc > sample.deadline_utc:
        blockers.append("SELO_TARDIO_AO_DEADLINE")
    mature = (sample.fim_utc <= policy.corte_utc and sample.outcome_selado_utc is not None
              and sample.outcome_selado_utc <= policy.corte_utc)
    if not mature:
        blockers.append("OUTCOME_NAO_MADURO_NO_CORTE")
    if any(v is None for v in (sample.cohort_ref, sample.binding_ref, sample.outcome_ref)):
        blockers.append("REFERENCIA_DE_COORTE_BINDING_OUTCOME_AUSENTE")
    if (sample.identity_state != "ORIGINAL_UNIQUE_COMPLETE"
            or sample.grupo.model_snapshot_original is None
            or sample.modelos_observados != (sample.grupo.model_snapshot_original,)
            or not sample.linhagem_chamadas or sample.modelo_as_of_utc is None):
        blockers.append("IDENTIDADE_OU_LINHAGEM_NAO_IDENTIFICADA")
    if sample.tentativas_modelo != 1:
        blockers.append("MULTIPLAS_TENTATIVAS")
    if sample.origem != "PUBLICA_RECEBIDA":
        blockers.append("DADOS_SIMULADOS" if sample.origem == "SIMULADA_TESTE" else "REPLAY")
    included, excluded, ai, quant, outcome = [], [], [], [], []
    if mature and sample.previsao_selada_utc <= sample.deadline_utc:
        for iid, a, q, r, author in zip(sample.emissores, sample.ai_scores,
                                      sample.quant_scores, sample.realized_residuals_usd,
                                      sample.autoria, strict=True):
            reason = None
            if sample.grupo.channel != "quant" and author != "confirmed":
                reason = "AUTORIA_NAO_CONFIRMADA"
            elif r is None:
                reason = "RETORNO_AUSENTE"
            elif q is None or (sample.grupo.channel != "quant" and a is None):
                reason = "SCORE_AUSENTE_MASCARA_COMUM"
            if reason is not None:
                excluded.append((iid, reason))
            else:
                included.append(iid)
                if a is not None:
                    ai.append(a)
                quant.append(q)
                outcome.append(r)
    else:
        excluded = [(iid, "COORTE_TARDIA_OU_NAO_MADURA") for iid in sample.emissores]
    n = len(included)
    q_ic = _spearman(tuple(quant), tuple(outcome))
    if sample.grupo.channel == "quant":
        return CoorteIC(sample.id_coorte, sample.inicio_utc, sample.fim_utc,
                        tuple(included), tuple(excluded), 0, n, 0,
                        None, q_ic, None, tuple(blockers))
    a_ic = _spearman(tuple(ai), tuple(outcome))
    incr = _incremental(tuple(ai), tuple(quant), tuple(outcome))
    if n < MIN_IC_OBS:
        blockers.append("MENOS_DE_3_PARES_COMUNS")
    return CoorteIC(sample.id_coorte, sample.inicio_utc, sample.fim_utc,
                    tuple(included), tuple(excluded), n, n, n,
                    a_ic, q_ic, incr, tuple(blockers))


def recomendar_fase_grupo(amostras: tuple[AmostraIC, ...], grupo: ChaveGrupo,
                          politica: PoliticaFase, fase_referencia: str | None) -> RecomendacaoFase:
    """Recomendação condicionada a declarações; nunca muda/adota a fase efetiva."""
    _tuple(amostras, "amostras")
    _group(grupo)
    _policy(politica, fase_referencia)
    for sample in amostras:
        _sample(sample, politica)
    ids = tuple(s.id_coorte for s in amostras)
    if len(set(ids)) != len(ids):
        raise EntradaFaseInvalida("Coorte duplicada.")
    periods = tuple((s.grupo, s.inicio_utc) for s in amostras)
    if len(set(periods)) != len(periods):
        raise EntradaFaseInvalida("Início de coorte duplicado no mesmo grupo.")
    selected = tuple(sorted((s for s in amostras if s.grupo == grupo), key=lambda s: s.inicio_utc))
    rows = tuple(_cohort(s, politica) for s in selected)
    other = tuple(s.id_coorte for s in amostras if s.grupo != grupo)
    blockers = []
    if any(v is None for v in (grupo.mind_original, grupo.provider_original,
                              grupo.model_snapshot_original)):
        blockers.append("GRUPO_NAO_IDENTIFICADO")
    if grupo.channel == "quant":
        blockers.append("QUANT_SEM_FASE_IA")
    if (fase_referencia is None or politica.escopo_fase != "GRUPO_REFERENCIA_HUMANA"
            or politica.referencia_fase is None):
        blockers.append("SEM_FASE_PROPRIA_DE_GRUPO")
    if politica.independencia != "DECLARADA_NAO_PROVADA":
        blockers.append("IID_NAO_DECLARADO_OU_DEPENDENCIA_CONHECIDA")
    if (politica.comparisons_scope_ref is None or not selected
            or politica.comparisons_seladas_utc > min(s.previsao_selada_utc for s in selected)):
        blockers.append("COMPARACOES_NAO_PRE_DECLARADAS")
    if any(a.fim_utc > b.inicio_utc for a, b in zip(selected, selected[1:], strict=False)):
        blockers.append("OUTCOMES_SOBREPOSTOS")
    eligible = tuple(r for r in rows if not r.impedimentos)
    if not eligible:
        blockers.append("SEM_COORTES_ELEGIVEIS_DECLARADAS")
    ai = tuple(r.ic_ai for r in eligible if r.ic_ai is not None)
    incr = tuple(r.ic_incremental for r in eligible if r.ic_incremental is not None)
    suggested, reason = None, "INSUFICIENTE_PARA_RECOMENDACAO"
    if not blockers:
        suggested, reason = _fase_nativa(ai, incr, fase_referencia)
    state = "CONDICIONAL_A_DECLARACOES" if not blockers else "INSUFICIENTE_PARA_RECOMENDACAO"
    if grupo.channel == "quant":
        state = "QUANT_FORA_DA_FASE_IA"
    elif "GRUPO_NAO_IDENTIFICADO" in blockers:
        state = "NAO_IDENTIFICADO"
    elif "SEM_FASE_PROPRIA_DE_GRUPO" in blockers:
        state = "SEM_FASE_DE_GRUPO"
    return RecomendacaoFase(
        grupo, state, fase_referencia, politica.escopo_fase, suggested, reason, rows, other,
        tuple(r.id_coorte for r in eligible),
        _statistics(tuple(r.ic_ai for r in rows if r.ic_ai is not None)),
        _statistics(tuple(r.ic_quant for r in rows if r.ic_quant is not None)),
        _statistics(tuple(r.ic_incremental for r in rows if r.ic_incremental is not None)),
        tuple(blockers), "T_IID_DESCRITIVO_NAO_PROVA_INDEPENDENCIA",
        "SEM_RECEPCAO_FISICA_SEM_PIT_SEM_ADOCAO",
    )
