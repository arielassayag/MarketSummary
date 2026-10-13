"""TESTE/DADOS SIMULADOS: kernels matemáticos não autenticarão uma coorte pública."""

import ast
import importlib.util
import math
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

# Corpo integral isolado: o agregador research importaria agentes financeiros não exercitados.
SOURCE = Path(__file__).parents[2] / "src/cdp/research/fase_diagnostico.py"
SPEC = importlib.util.spec_from_file_location("_cdp_fase_diagnostico_puro", SOURCE)
FASE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = FASE
SPEC.loader.exec_module(FASE)

ChaveGrupo = FASE.ChaveGrupo
AmostraIC = FASE.AmostraIC
PoliticaFase = FASE.PoliticaFase
CalendarioFaseDeclarado = FASE.CalendarioFaseDeclarado
EntradaFaseInvalida = FASE.EntradaFaseInvalida
recomendar_fase_grupo = FASE.recomendar_fase_grupo
START = datetime(2026, 1, 2, 20, tzinfo=UTC)
GROUP = ChaveGrupo("codex", "provider_original_TESTE", "snapshot_original_TESTE", "pesquisa_ai")
MACRO = "a" * 64


def calendar(**changes):
    value = CalendarioFaseDeclarado(
        "CALENDARIO_TESTE_DECLARADO_SEM_PIT", START - timedelta(days=1),
        tuple((START + timedelta(weeks=i)).date() for i in range(104)),
    )
    return replace(value, **changes)


def policy(**changes):
    value = PoliticaFase(START + timedelta(days=400), 5, MACRO, FASE.UNIDADE,
                        "GRUPO_REFERENCIA_HUMANA", "REFERENCIA_TESTE_SEM_AUTORIDADE",
                        "UNIVERSO_TESTE_PREDECLARADO", START - timedelta(days=1),
                        "DECLARADA_NAO_PROVADA", calendar())
    return replace(value, **changes)


def sample(i=0, **changes):
    begin = START + timedelta(weeks=i)
    value = AmostraIC(
        f"DADOS_SIMULADOS-{i}", GROUP, begin.date(), begin, begin + timedelta(days=5),
        begin - timedelta(hours=1), begin - timedelta(hours=2), begin - timedelta(minutes=30),
        begin + timedelta(days=5, hours=1), "COORTE_TESTE", "BINDING_TESTE", "OUTCOME_TESTE",
        ("CHAMADA_TESTE",), (GROUP.model_snapshot_original,), "ORIGINAL_UNIQUE_COMPLETE", 1,
        "SIMULADA_TESTE", MACRO, 5, FASE.UNIDADE,
        ("TESTE_A", "TESTE_B", "TESTE_C", "TESTE_D"),
        (3.0, 1.0, 4.0, 2.0), (1.0, 2.0, 3.0, 4.0),
        (0.03, 0.01, 0.04, 0.02), ("confirmed",) * 4,
    )
    return replace(value, **changes)


def diagnose(samples=None, group=GROUP, reference="S0", **policy_changes):
    return recomendar_fase_grupo((sample(),) if samples is None else samples,
                                group, policy(**policy_changes), reference)


def test_matematica_spearman_oraculo_postos_com_empate():
    # Postos (1.5,1.5,3,4) vs (1,2,3,4): cov/sqrt(SSa*SSb) = 4.5/sqrt(4.5*5).
    value = FASE._spearman((1.0, 1.0, 3.0, 4.0), (10.0, 20.0, 30.0, 40.0))
    assert value == pytest.approx(4.5 / math.sqrt(4.5 * 5.0), abs=1e-14)
    assert FASE._spearman((3.0, 2.0, 1.0), (1.0, 2.0, 3.0)) == pytest.approx(-1.0)


def test_incremental_oraculo_mqo_e_quant_constante():
    ai, q = (3.0, 1.0, 4.0, 2.0), (1.0, 2.0, 3.0, 4.0)
    # AI média2.5; cov com q zero. Resíduo=(.5,-1.5,1.5,-.5), rank igual ao outcome.
    assert FASE._incremental(ai, q, ai) == pytest.approx(1.0)
    assert FASE._incremental(ai, (2.0,) * 4, ai) == pytest.approx(1.0)
    assert FASE._incremental(tuple(2.0 * x + 1.0 for x in q), q, ai) is None


def test_quant_pequeno_nao_fabrica_residuo_incremental():
    q = (1e-200, 2e-200, 3e-200, 4e-200)
    assert FASE._incremental((3.0, 5.0, 7.0, 9.0), q, (1.0, 2.0, 3.0, 4.0)) is None


@pytest.mark.parametrize("x,y", [
    ((1.0, 2.0), (2.0, 3.0)), ((1.0,) * 3, (1.0, 2.0, 3.0)),
    ((1.0, 2.0, 3.0), (0.0,) * 3),
])
def test_rank_ic_indefinido_nao_zero(x, y):
    assert FASE._spearman(x, y) is None


def test_media_desvio_t_ddof1_oraculo_independente():
    stats = FASE._statistics((0.0, 1.0, 2.0))
    assert (stats.n_semanas, stats.media, stats.desvio_ddof1, stats.icir) == (3, 1.0, 1.0, 1.0)
    assert stats.t_iid_descritivo == pytest.approx(math.sqrt(3.0))
    assert FASE._statistics((0.5,) * 13).t_iid_descritivo is None
    assert FASE._statistics(()).media is None


def _alternating(n):
    # Receita fixa; testes da política isolada, nenhum objeto recebe origem pública fictícia.
    return tuple(0.2 if i % 2 == 0 else 0.4 for i in range(n))


@pytest.mark.parametrize("current,n,expected", [
    ("S0", 12, "S0"), ("S0", 13, "S1"),
    ("S1", 25, "S1"), ("S1", 26, "S2"),
    ("S2", 51, "S2"), ("S2", 52, "S3"), ("S3", 52, "S3"),
])
def test_fronteiras_semanas_politica_isolada(current, n, expected):
    assert FASE._fase_nativa(_alternating(n), _alternating(n), current)[0] == expected


@pytest.mark.parametrize("phase,n,limit", [("S0", 13, 0.5), ("S1", 26, 1.5), ("S2", 52, 2.0)])
def test_limiar_nativo_igual_e_abaixo(phase, n, limit):
    # Vetor simétrico de média0/desvio1 independente da rotina testada.
    base = tuple((i - (n - 1) / 2) for i in range(n))
    sd = math.sqrt(sum(x * x for x in base) / (n - 1))
    target_mean = limit if phase == "S0" else limit / math.sqrt(n)
    at = tuple(x / sd + target_mean for x in base)
    # Fronteira >= testada com tolerância para arredondamento da própria receita analítica.
    # Construção em torno do limiar: a saída observada nunca escolhe o vetor depois.
    above = tuple(x + 1e-12 for x in at)
    below = tuple(x - 1e-12 for x in at)
    next_phase = {"S0": "S1", "S1": "S2", "S2": "S3"}[phase]
    assert FASE._fase_nativa(above, above, phase)[0] == next_phase
    assert FASE._fase_nativa(below, below, phase)[0] == phase


@pytest.mark.parametrize("phase", ["S0", "S1", "S2", "S3"])
def test_rebaixamento_s0_nativo_sem_promover_dois_niveis(phase):
    negative = tuple(-x for x in _alternating(13))
    assert FASE._fase_nativa(negative, _alternating(52), phase)[0] == "S0"
    assert FASE._fase_nativa(_alternating(52), _alternating(52), "S0")[0] == "S1"


def test_icir_exatamente_meio_inclui_fronteira():
    # Média .5 e soma de desvios²12 em13 observações: ddof1 resulta sd1 exato.
    values = (-0.5, 1.5) * 6 + (0.5,)
    assert FASE._statistics(values).icir == 0.5
    assert FASE._fase_nativa(values, (), "S0")[0] == "S1"


def test_simulado_descreve_sem_recomendacao_ou_autorizacao():
    samples = tuple(sample(i) for i in range(13))
    before = samples, policy()
    result = diagnose(samples)
    assert result.ic_ai_descritivo.n_semanas == 13
    assert result.ic_ai_descritivo.media == pytest.approx(1.0)
    assert result.fase_sugerida is None
    assert result.ids_elegiveis_declarados == ()
    assert "DADOS_SIMULADOS" in result.coortes[0].impedimentos
    assert result.autoriza_promocao is False
    assert result.autoridade == "SEM_RECEPCAO_FISICA_SEM_PIT_SEM_ADOCAO"
    assert (samples, policy()) == before
    with pytest.raises(FrozenInstanceError):
        result.fase_sugerida = "S3"


def test_mascara_comum_remove_um_emissor_em_tres_series():
    s = sample(quant_scores=(None, 2.0, 3.0, 4.0))
    row = diagnose((s,)).coortes[0]
    assert row.emissores_incluidos == ("TESTE_B", "TESTE_C", "TESTE_D")
    assert row.emissores_excluidos == (("TESTE_A", "SCORE_AUSENTE_MASCARA_COMUM"),)
    assert (row.n_ai, row.n_quant, row.n_incremental) == (3, 3, 3)
    assert row.ic_ai == pytest.approx(1.0)
    assert row.ic_quant == pytest.approx(0.5)


@pytest.mark.parametrize("field,values,reason", [
    ("ai_scores", (None, 1.0, 4.0, 2.0), "SCORE_AUSENTE_MASCARA_COMUM"),
    ("realized_residuals_usd", (None, 0.01, 0.04, 0.02), "RETORNO_AUSENTE"),
    ("autoria", ("external", "confirmed", "confirmed", "confirmed"), "AUTORIA_NAO_CONFIRMADA"),
    ("autoria", ("absent", "confirmed", "confirmed", "confirmed"), "AUTORIA_NAO_CONFIRMADA"),
])
def test_ausencia_autoria_preserva_contagem_mascara(field, values, reason):
    row = diagnose((sample(**{field: values}),)).coortes[0]
    assert row.emissores_excluidos == (("TESTE_A", reason),)
    assert row.n_ai == row.n_quant == row.n_incremental == 3


def test_zero_realizado_e_constante_incremental_nao_viram_ausencia_ou_zero():
    row = diagnose((sample(realized_residuals_usd=(0.0, 0.01, 0.04, 0.02)),)).coortes[0]
    assert row.n_ai == 4
    linear = sample(ai_scores=(3.0, 5.0, 7.0, 9.0))
    assert diagnose((linear,)).coortes[0].ic_incremental is None


@pytest.mark.parametrize("field,value", [
    ("mind_original", "chatgpt"), ("provider_original", "outro_provider_TESTE"),
    ("model_snapshot_original", "outro_snapshot_TESTE"), ("channel", "mente_final"),
])
def test_grupo_original_nao_vaza_mente_modelo_provider_canal(field, value):
    other = replace(GROUP, **{field: value})
    altered = sample(1, grupo=other, modelos_observados=(other.model_snapshot_original,))
    result = diagnose((sample(), altered))
    assert tuple(r.id_coorte for r in result.coortes) == ("DADOS_SIMULADOS-0",)
    assert result.coortes_outros_grupos == ("DADOS_SIMULADOS-1",)
    assert result.ic_ai_descritivo.n_semanas == 1


@pytest.mark.parametrize("field", ["mind_original", "provider_original", "model_snapshot_original"])
def test_identidade_ausente_nao_recebe_config_atual(field):
    group = replace(GROUP, **{field: None})
    result = diagnose((sample(grupo=group),), group=group)
    assert result.estado == "NAO_IDENTIFICADO"
    assert result.grupo == group and result.fase_sugerida is None


@pytest.mark.parametrize("changes", [
    {"identity_state": "MISSING"}, {"identity_state": "MIXED"},
    {"identity_state": "ALIAS_UNRESOLVED"}, {"modelos_observados": ()},
    {"modelos_observados": ("snapshot_original_TESTE", "outro_TESTE")},
    {"linhagem_chamadas": ()}, {"modelo_as_of_utc": None},
])
def test_linhagem_identidade_ambigua_bloqueia(changes):
    result = diagnose((sample(**changes),))
    assert "IDENTIDADE_OU_LINHAGEM_NAO_IDENTIFICADA" in result.coortes[0].impedimentos
    assert result.fase_sugerida is None


@pytest.mark.parametrize("changes,reason", [
    ({"tentativas_modelo": 2}, "MULTIPLAS_TENTATIVAS"), ({"origem": "REPLAY"}, "REPLAY"),
    ({"binding_ref": None}, "REFERENCIA_DE_COORTE_BINDING_OUTCOME_AUSENTE"),
    ({"outcome_ref": None}, "REFERENCIA_DE_COORTE_BINDING_OUTCOME_AUSENTE"),
    ({"previsao_selada_utc": START - timedelta(minutes=15)}, "SELO_TARDIO_AO_DEADLINE"),
    ({"outcome_selado_utc": None}, "OUTCOME_NAO_MADURO_NO_CORTE"),
])
def test_amostra_nao_prospectiva_ou_sem_vinculo_insuficiente(changes, reason):
    result = diagnose((sample(**changes),))
    assert reason in result.coortes[0].impedimentos
    assert result.fase_sugerida is None


def test_corte_maturacao_nao_recalcula_outcome():
    result = diagnose(corte_utc=START + timedelta(days=5))
    assert result.coortes[0].n_ai == 0
    assert "OUTCOME_NAO_MADURO_NO_CORTE" in result.coortes[0].impedimentos
    at = diagnose(corte_utc=START + timedelta(days=5, hours=1))
    assert at.coortes[0].n_ai == 4


def test_quant_nao_recebe_fase_ia():
    group = replace(GROUP, channel="quant", model_snapshot_original=None)
    value = sample(grupo=group, ai_scores=(None,) * 4, autoria=("not_applicable",) * 4)
    result = diagnose((value,), group=group, reference="S3")
    assert result.estado == "QUANT_FORA_DA_FASE_IA"
    assert result.fase_sugerida is None
    assert (result.coortes[0].n_ai, result.coortes[0].n_quant) == (0, 4)
    assert result.ic_ai_descritivo.media is None
    assert result.ic_quant_descritivo.media is not None


@pytest.mark.parametrize("changes", [
    {"escopo_fase": "GLOBAL_APENAS_CONTEXTO"}, {"escopo_fase": "DESCONHECIDO"},
    {"referencia_fase": None},
])
def test_fase_global_nao_e_heranca_de_grupo(changes):
    result = diagnose(reference="S3", **changes)
    assert result.estado == "SEM_FASE_DE_GRUPO"
    assert result.fase_referencia == "S3" and result.fase_sugerida is None


def test_sem_fase_propria_retorna_estatistica():
    result = diagnose(reference=None)
    assert result.estado == "SEM_FASE_DE_GRUPO"
    assert result.ic_ai_descritivo.n_semanas == 1


@pytest.mark.parametrize("qual", ["DESCONHECIDA", "SOBREPOSTA_OU_DEPENDENTE"])
def test_iid_desconhecida_ou_dependencia_nao_promove(qual):
    result = diagnose(independencia=qual)
    assert "IID_NAO_DECLARADO_OU_DEPENDENCIA_CONHECIDA" in result.impedimentos
    assert result.fase_sugerida is None


def test_overlap_observado_e_comparacoes_tardias_nao_promovem():
    first = sample(fim_utc=START + timedelta(days=8),
                   outcome_selado_utc=START + timedelta(days=8, hours=1))
    result = diagnose((first, sample(1)))
    assert "OUTCOMES_SOBREPOSTOS" in result.impedimentos
    late = diagnose(comparisons_seladas_utc=START)
    assert "COMPARACOES_NAO_PRE_DECLARADAS" in late.impedimentos


@pytest.mark.parametrize("changes", [
    {"modelo_as_of_utc": START - timedelta(minutes=45)},
    {"previsao_selada_utc": START + timedelta(seconds=1)},
    {"fim_utc": START}, {"deadline_utc": START + timedelta(seconds=1)},
    {"outcome_selado_utc": START + timedelta(days=4)},
])
def test_cronologia_contraditoria_recusa_antes_calculo(changes):
    with pytest.raises(EntradaFaseInvalida):
        diagnose((sample(**changes),))


@pytest.mark.parametrize("changes", [
    {"inicio_utc": START.replace(tzinfo=None)}, {"inicio_utc": START.replace(fold=1)},
    {"inicio_utc": START.replace(tzinfo=timezone(timedelta(hours=1)))},
    {"horizonte_sessoes": 8}, {"macro_base_policy_hash": "b" * 64},
    {"unidade": "retorno_equity_USD"}, {"ai_scores": (3.0, 1.0)},
    {"emissores": ("A", "A", "C", "D")}, {"linhagem_chamadas": ("x", "x")},
    {"origem": "desconhecida"}, {"identity_state": "passed"},
    {"tentativas_modelo": 0}, {"horizonte_sessoes": True},
    {"macro_base_policy_hash": "hash-livre"}, {"autoria": ("codex",) * 4},
])
def test_malformados_e_unidades_diferentes_recusados(changes):
    with pytest.raises(EntradaFaseInvalida):
        diagnose((sample(**changes),))


class MaliciousFloat(float):
    def __float__(self):
        raise AssertionError("callback numérico proibido")


class MaliciousText(str):
    def __eq__(self, other):
        raise AssertionError("callback textual proibido")

    def __hash__(self):
        raise AssertionError("hash textual proibido")


class MaliciousTZ(tzinfo):
    def utcoffset(self, dt):
        raise AssertionError("callback temporal proibido")


@pytest.mark.parametrize("bad", [True, 1, float("nan"), float("inf"), MaliciousFloat(1.0), object()])
def test_numero_exato_recusa_sem_coercao(bad):
    with pytest.raises(EntradaFaseInvalida):
        diagnose((sample(ai_scores=(bad, 1.0, 4.0, 2.0)),))


@pytest.mark.parametrize("changes", [
    {"id_coorte": MaliciousText("x")}, {"unidade": MaliciousText(FASE.UNIDADE)},
    {"ai_scores": [3.0, 1.0, 4.0, 2.0]},
    {"inicio_utc": START.replace(tzinfo=MaliciousTZ())},
])
def test_callbacks_livres_recusados(changes):
    with pytest.raises(EntradaFaseInvalida):
        diagnose((sample(**changes),))


@pytest.mark.parametrize("value", [object(), {"mind_original": "codex"}, MaliciousText("S0")])
def test_dto_ou_fase_subclasse_nao_autorizam(value):
    with pytest.raises(EntradaFaseInvalida):
        if isinstance(value, str):
            diagnose(reference=value)
        else:
            diagnose(group=value)


@pytest.mark.parametrize("changes", [
    {"comparisons_scope_ref": None}, {"comparisons_seladas_utc": None},
    {"corte_utc": START.replace(tzinfo=None)}, {"independencia": "passed"},
    {"escopo_fase": "cfg_atual"}, {"horizonte_sessoes": True},
])
def test_politica_malformada_recusa(changes):
    with pytest.raises(EntradaFaseInvalida):
        diagnose(**changes)


def test_duplicata_e_lista_nao_viram_n_semanas():
    with pytest.raises(EntradaFaseInvalida):
        diagnose((sample(), sample()))
    with pytest.raises(EntradaFaseInvalida):
        diagnose((sample(), sample(id_coorte="outro")))
    with pytest.raises(EntradaFaseInvalida):
        diagnose([sample()])


def test_coorte_vazia_menos_tres_e_constante_preservam_none():
    empty = sample(emissores=(), ai_scores=(), quant_scores=(), realized_residuals_usd=(), autoria=())
    result = diagnose((empty,))
    assert result.coortes[0].ic_ai is None and result.coortes[0].ic_incremental is None
    assert result.coortes[0].n_ai == 0
    constant = diagnose((sample(ai_scores=(1.0,) * 4),)).coortes[0]
    assert constant.ic_ai is None and constant.ic_incremental is None


def test_sem_io_ambiente_financeiro_ou_imports_do_agregador():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert modules == {"__future__", "math", "sys", "dataclasses", "datetime", "statistics"}
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert not any(isinstance(n.func, ast.Name) and n.func.id in {"open", "eval", "exec"}
                   for n in calls)
    assert not any(isinstance(n.func, ast.Attribute) and n.func.attr in {"now", "today"}
                   for n in calls)


def daily_sample(i):
    """Receita diária fixa, disjunta e rotulada TESTE; nunca origem pública fictícia."""
    begin = START + timedelta(days=i)
    return sample(i, week=begin.date(), inicio_utc=begin, fim_utc=begin + timedelta(hours=6),
                  previsao_selada_utc=begin - timedelta(hours=1),
                  modelo_as_of_utc=begin - timedelta(hours=2),
                  deadline_utc=begin - timedelta(minutes=30),
                  outcome_selado_utc=begin + timedelta(hours=7), horizonte_sessoes=1)


def test_treze_diarias_disjuntas_nao_contam_treze_semanas():
    samples = tuple(daily_sample(i) for i in range(13))
    assert all(s.origem == "SIMULADA_TESTE" for s in samples)
    with pytest.raises(EntradaFaseInvalida, match="grupo na mesma semana civil"):
        diagnose(samples, horizonte_sessoes=1, calendario=None)


def test_calendario_diario_nao_fabrica_unidade_semanal():
    keys = tuple((START + timedelta(days=i)).date() for i in range(13))
    with pytest.raises(EntradaFaseInvalida, match="chave por semana civil"):
        diagnose(calendario=calendar(chaves=keys))


def test_chaves_artificiais_semanais_nao_rebatizam_retornos_diarios():
    s = replace(daily_sample(1), week=(START + timedelta(weeks=1)).date())
    with pytest.raises(EntradaFaseInvalida, match="dia civil UTC"):
        diagnose((daily_sample(0), s), horizonte_sessoes=1, calendario=None)


def test_dois_dias_diferentes_da_mesma_semana_recusam_sem_selecionar_coorte():
    thursday = START - timedelta(days=1)
    s = sample(1, week=thursday.date(), inicio_utc=thursday,
               previsao_selada_utc=thursday - timedelta(hours=1),
               modelo_as_of_utc=thursday - timedelta(hours=2),
               deadline_utc=thursday - timedelta(minutes=30))
    with pytest.raises(EntradaFaseInvalida, match="grupo na mesma semana civil"):
        diagnose((s, sample()), calendario=None)


def test_grupos_distintos_podem_reter_mesma_chave_sem_vazar_estatistica():
    other = replace(GROUP, channel="mente_final")
    result = diagnose((sample(), sample(id_coorte="DADOS_SIMULADOS-1", grupo=other)))
    assert result.ic_ai_descritivo.n_semanas == 1
    assert result.coortes_outros_grupos == ("DADOS_SIMULADOS-1",)
    assert result.coortes[0].week == START.date()


@pytest.mark.parametrize("begin", [datetime(2026, 1, 1, 20, tzinfo=UTC),
                                  datetime(2026, 1, 7, 20, tzinfo=UTC)])
def test_quinta_feriado_e_inception_declaradas_sem_impor_sexta(begin):
    s = sample(week=begin.date(), inicio_utc=begin, fim_utc=begin + timedelta(days=5),
               previsao_selada_utc=begin - timedelta(hours=1),
               modelo_as_of_utc=begin - timedelta(hours=2),
               deadline_utc=begin - timedelta(minutes=30),
               outcome_selado_utc=begin + timedelta(days=5, hours=1))
    cal = calendar(chaves=(begin.date(),), selado_utc=begin - timedelta(days=1))
    result = diagnose((s,), calendario=cal)
    assert result.coortes[0].week == begin.date()
    assert result.ic_ai_descritivo.n_semanas == 1
    assert result.fase_sugerida is None and not result.autoriza_promocao
    assert "DADOS_SIMULADOS" in result.coortes[0].impedimentos


@pytest.mark.parametrize("cal", [None, calendar(chaves=())])
def test_calendario_ausente_conserva_estatistica_sem_recomendacao(cal):
    result = diagnose(calendario=cal)
    assert result.ic_ai_descritivo.n_semanas == 1
    assert "CALENDARIO_DECLARADO_AUSENTE" in result.impedimentos
    assert result.fase_sugerida is None


def test_calendario_tardio_nao_recebe_selo_da_propria_previsao():
    result = diagnose(calendario=calendar(selado_utc=START))
    assert "CALENDARIO_NAO_PRE_DECLARADO" in result.impedimentos
    at = diagnose(calendario=calendar(selado_utc=START - timedelta(hours=1)))
    assert "CALENDARIO_NAO_PRE_DECLARADO" not in at.impedimentos


def test_chave_ausente_recusada_sem_fallback_calendario_global():
    with pytest.raises(EntradaFaseInvalida, match="ausente no calendário"):
        diagnose(calendario=calendar(chaves=((START + timedelta(weeks=1)).date(),)))


class MaliciousDate(date):
    def weekday(self):
        raise AssertionError("callback weekday proibido")

    def __eq__(self, other):
        raise AssertionError("callback de igualdade temporal proibido")


@pytest.mark.parametrize("bad", [None, "2026-01-02", START,
                                 MaliciousDate(2026, 1, 2), object()])
def test_week_exata_antes_de_comparacao_ou_callback(bad):
    with pytest.raises(EntradaFaseInvalida, match="week: date"):
        diagnose((sample(week=bad),))


@pytest.mark.parametrize("changes", [
    {"corpo_ref": None}, {"corpo_ref": MaliciousText("x")},
    {"selado_utc": START.replace(tzinfo=None)},
    {"selado_utc": START.replace(fold=1)}, {"chaves": [START.date()]},
    {"chaves": (START,)}, {"chaves": (MaliciousDate(2026, 1, 2),)},
    {"chaves": (START.date(), START.date())},
    {"chaves": ((START + timedelta(weeks=1)).date(), START.date())},
])
def test_calendario_tipos_ordem_e_metadados_exatos(changes):
    with pytest.raises(EntradaFaseInvalida):
        diagnose(calendario=calendar(**changes))


@pytest.mark.parametrize("bad", [object(), {"chaves": ()}])
def test_dto_calendario_nao_confere_autoridade(bad):
    with pytest.raises(EntradaFaseInvalida, match="CalendarioFaseDeclarado exato"):
        diagnose(calendario=bad)


def test_virada_ano_semana_civil_nao_separa_chaves_por_ano():
    with pytest.raises(EntradaFaseInvalida, match="chave por semana civil"):
        diagnose(calendario=calendar(chaves=(date(2025, 12, 31), date(2026, 1, 2))))
    begin = datetime(2026, 1, 5, 20, tzinfo=UTC)
    s = sample(1, inicio_utc=begin, week=begin.date(),
               previsao_selada_utc=begin - timedelta(hours=1),
               modelo_as_of_utc=begin - timedelta(hours=2),
               deadline_utc=begin - timedelta(minutes=30))
    result = diagnose((sample(), s), calendario=calendar(chaves=(START.date(), s.week)))
    assert result.ic_ai_descritivo.n_semanas == 2


def test_semanas_ausentes_nao_viram_zero_ou_exigem_consecutividade():
    result = diagnose((sample(), sample(2)))
    assert result.ic_ai_descritivo.n_semanas == 2
    assert tuple(r.week for r in result.coortes) == (START.date(), (START + timedelta(weeks=2)).date())
    assert result.ic_ai_descritivo.media == pytest.approx(1.0)


def test_calendario_congelado_e_preservado_sem_reescrever_chaves():
    cal = calendar()
    before = cal
    diagnose(calendario=cal)
    assert cal == before
    with pytest.raises(FrozenInstanceError):
        cal.chaves = ()
