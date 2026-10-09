"""DADOS SIMULADOS: derivação portável autora, API normal e assertivas preservadas.

Origem test_dimensoes.py do candidato privado; retirados somente os 9 controles
documentais de bytes fechados, imports/caminhos privados. Sem seed/coleta/motor.
"""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from dimensoes_contabeis_fixtures import (
    CORTE,
    DIA,
    PAR,
    coletor,
    fato,
    selecionar,
    semestre,
    trimestres,
)

from cdp.cobertura.disponibilidade_demonstrativos import (
    RegistroParticipantes,
    _grupos,
    conferir,
    participante,
)
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.cobertura.temporal import construir
from cdp.data.dimensoes_contabeis import CAMPOS, compativeis, dimensoes
from cdp.data.publico_fatos import derivados


def linha_ttm(df, fim="2026-06-30"):
    return df[df.freq.eq("TTM") & df.period_end.eq(pd.Timestamp(fim))]


def test_api_ordinaria_propaga_par_fatos_meta_componentes_proveniencia_e_identidade():
    df = selecionar(semestre())
    row = linha_ttm(df).iloc[0]
    assert Decimal(str(row.value)) == Decimal("100") + Decimal("60") - Decimal("30")
    assert {k: row[k] for k in CAMPOS} == PAR
    assert row.data_publicacao is None
    partes = _grupos(row)[0][1]
    assert len(partes) == 3 and all({k: c[k] for k in CAMPOS} == PAR for c in partes)
    assert {k: _prov_linha(row)[k] for k in CAMPOS} == PAR
    normal = Demonstrativos(df, "SIMULADO")
    assert {k: normal.valor("lucro_liquido_controladores")[1][k] for k in CAMPOS} == PAR
    pac = pacote(row)
    assert conferir(pac)[0]
    assert all(
        {k: c[k] for k in CAMPOS} == PAR
        for c in pac["disponibilidade_demonstrativos"][0]["componentes"]
    )
    ident = pac["manifesto_disponibilidade"]["participantes_esperados"][0]
    assert {k: ident[k] for k in CAMPOS} == PAR


def pacote(row):
    out = {
        "issuer_id": "SIMULADO",
        "as_of": DIA.isoformat(),
        "corte_temporal": construir(DIA, CORTE),
        "t.lucro_simulado": float(row.value),
    }
    registro = RegistroParticipantes("SIMULADO")
    registro.registrar(row, "t.lucro_simulado")
    registro.finalizar(out)
    return out


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("politica_contabil_id", "IFRS_DADOS_SIMULADOS"),
        ("poder_aquisitivo_data", "2025-12-31"),
        ("par", None),
    ],
)
@pytest.mark.parametrize("index", [0, 1, 2])
def test_semestre_nao_mistura_componentes_tipados_ausentes_ou_divergentes(campo, valor, index):
    rows = semestre()
    if campo == "par":
        for key in CAMPOS:
            rows[index].pop(key)
    else:
        rows[index][campo] = valor
    df = selecionar(rows)
    assert linha_ttm(df).empty
    assert len(df[df.freq.eq("A")]) == 1  # Valor anual reportado não é apagado.


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("politica_contabil_id", None),
        ("poder_aquisitivo_data", None),
        ("politica_contabil_id", " "),
        ("politica_contabil_id", 17),
        ("poder_aquisitivo_data", "2026-02-30"),
        ("poder_aquisitivo_data", "2026-6-30"),
        ("poder_aquisitivo_data", "2026-06-30T00:00:00"),
        ("poder_aquisitivo_data", datetime(2026, 6, 30)),
    ],
)
def test_parcial_e_tipo_invalido_recusados_no_caller(campo, valor):
    rows = semestre()
    rows[0][campo] = valor
    with pytest.raises(ValueError):
        selecionar(rows)


def test_date_real_aceito_sem_inferir_data_do_periodo_ou_corte():
    assert dimensoes({**PAR, "poder_aquisitivo_data": date(2026, 6, 30)}) == PAR
    assert not compativeis([PAR, {**PAR, "poder_aquisitivo_data": DIA.isoformat()}])


def test_ausencia_integral_e_nota_nao_declaram_homogeneidade():
    rows = semestre(tipado=False)
    for row in rows:
        row["nota"] += "; politica_contabil_id=X; poder_aquisitivo_data=2026-06-30"
    df = selecionar(rows)
    assert not set(CAMPOS) & set(df.columns)
    assert not set(CAMPOS) & set(participante(linha_ttm(df).iloc[0], "simulado"))
    assert Decimal(str(linha_ttm(df).iloc[0].value)) == Decimal("130")


@pytest.mark.parametrize("campo", CAMPOS)
def test_quatro_q_e_consumidor_recusam_dimensao_divergente(campo):
    rows = trimestres()
    original = selecionar(rows)
    assert Decimal(str(linha_ttm(original).iloc[0].value)) == Decimal("26")
    rows[1][campo] = "IFRS_SIMULADO" if campo == CAMPOS[0] else "2025-12-31"
    assert linha_ttm(selecionar(rows)).empty
    q = original[original.freq.eq("Q")].copy()
    q.loc[q.index[1], campo] = rows[1][campo]
    assert linha_ttm(Demonstrativos(q, "SIMULADO").df).empty


def test_consumidor_4q_propaga_componentes_native_sem_provider_ttm():
    q = selecionar(trimestres())
    q = q[q.freq.eq("Q")]
    row = linha_ttm(Demonstrativos(q, "SIMULADO").df).iloc[0]
    assert Decimal(str(row.value)) == Decimal("26")
    pac = pacote(row)
    assert conferir(pac)[0]
    assert len(pac["disponibilidade_demonstrativos"][0]["componentes"]) == 4


@pytest.mark.parametrize(
    "campo,valor", [(CAMPOS[0], "IFRS_SIMULADO"), (CAMPOS[1], "2025-12-31"), ("par", None)]
)
def test_diferenca_ytd_quarto_trimestre_recusa_mistura(campo, valor):
    rows = [fato("2025-01-01", "2025-09-30", 60), fato("2025-01-01", "2025-12-31", 100)]
    if campo == "par":
        for k in CAMPOS:
            rows[0].pop(k)
    else:
        rows[0][campo] = valor
    df = selecionar(rows)
    assert df[df.freq.eq("Q") & df.period_end.eq(pd.Timestamp("2025-12-31"))].empty
    assert Decimal(str(df[df.freq.eq("A")].iloc[0].value)) == Decimal("100")


def test_derivados_so_componentes_reais_politica_igual_e_fonte_financeira_default():
    rows = [
        fato("2025-01-01", "2025-12-31", v, item=item)
        for item, v in [
            ("ebit", 20),
            ("d_a", 3),
            ("lucro_antes_ir", 22),
            ("resultado_financeiro", 2),
        ]
    ]
    rows[2][CAMPOS[0]] = "OUTRA_SIMULADA"  # Não participa de EBIT reportado + D&A.
    df = selecionar(rows)
    row = df[df.item.eq("ebitda") & df.freq.eq("TTM")].iloc[0]
    assert Decimal(str(row.value)) == Decimal("23")
    assert [c["item"] for c in _grupos(row)[-1][1]] == ["ebit", "d_a"]
    rows[1][CAMPOS[1]] = "2025-12-31"
    assert not selecionar(rows).item.eq("ebitda").any()


@pytest.mark.parametrize(
    "item1,item2,result",
    [("cfo", "capex", "fcf"), ("lucro_antes_ir", "resultado_financeiro", "ebit")],
)
def test_identidades_aritmeticas_rejeitam_componentes_ausentes_ou_divergentes(item1, item2, result):
    rows = [
        fato("2025-01-01", "2025-12-31", 10, item=item1),
        fato("2025-01-01", "2025-12-31", 2, item=item2, tipado=False),
    ]
    assert not selecionar(rows).item.eq(result).any()
    rows[1].update(PAR)
    assert Decimal(
        str(selecionar(rows).query("item == @result and freq == 'TTM'").iloc[0].value)
    ) == Decimal("8")
    rows[1][CAMPOS[0]] = "IFRS_SIMULADO"
    assert not selecionar(rows).item.eq(result).any()


@pytest.mark.parametrize(
    "campo,valor", [(CAMPOS[0], "OUTRA"), (CAMPOS[1], "2025-12-31"), (CAMPOS[1], None)]
)
def test_manifesto_vincula_dimensoes_sem_reassinar(campo, valor):
    pac = pacote(linha_ttm(selecionar(semestre())).iloc[0])
    pac["disponibilidade_demonstrativos"][0]["componentes"][0][campo] = valor
    assert not conferir(pac)[0]


def test_mutacao_coerente_manifesto_nao_autentica_mistura_de_grupo():
    row = linha_ttm(selecionar(semestre())).iloc[0].copy()
    row["componentes_fluxo"] = deepcopy(_grupos(row)[0][1])
    row.componentes_fluxo[0][CAMPOS[0]] = "OUTRA"
    assert not conferir(pacote(row))[0]


def test_colunas_nulas_ausentes_conservam_default_sem_certificar():
    rows = semestre(tipado=False)
    for row in rows:
        row.update(dict.fromkeys(CAMPOS))
    assert not set(CAMPOS) & set(selecionar(rows).columns)








def test_derivados_caller_sem_tipo_usa_formulas_existentes():
    df = selecionar(semestre(item="cfo", tipado=False) + semestre(item="capex", tipado=False))
    assert not set(CAMPOS) & set(derivados(df).columns)


def test_coletor_api_integral_preserva_dimensoes_componentes_recebimento_e_publicacao():
    df = coletor(semestre())
    row = linha_ttm(df).iloc[0]
    assert Decimal(str(row.value)) == Decimal("130")
    assert {k: row[k] for k in CAMPOS} == PAR
    assert pd.isna(row.data_publicacao)
    assert row.disponivel_desde == "2026-10-08T21:00:00+00:00"
    assert pd.Timestamp(row.data_coleta) == pd.Timestamp("2026-10-08T21:00:00+00:00")
    assert len(_grupos(row)[0][1]) == 3
    assert all({k: c[k] for k in CAMPOS} == PAR for c in _grupos(row)[0][1])
    assert conferir(pacote(row))[0]


@pytest.mark.parametrize(
    "campo,bad", [(CAMPOS[0], None), (CAMPOS[1], "2026-02-30"), (CAMPOS[0], " ")]
)
def test_coletor_normal_recusa_par_invalido_ou_parcial(campo, bad):
    rows = semestre()
    rows[0][campo] = bad
    with pytest.raises(ValueError):
        coletor(rows)


@pytest.mark.parametrize("tipo", ["politica", "poder", "ausente"])
def test_coletor_normal_recusa_composicao_tipada_mista(tipo):
    rows = semestre()
    if tipo == "ausente":
        for k in CAMPOS:
            rows[0].pop(k)
    else:
        rows[0][CAMPOS[0] if tipo == "politica" else CAMPOS[1]] = (
            "OUTRA" if tipo == "politica" else "2025-12-31"
        )
    assert linha_ttm(coletor(rows)).empty


def test_coletor_normal_default_nao_tipado_nao_cria_dimensoes_vazias():
    df = coletor(semestre(tipado=False))
    assert not set((*CAMPOS, "componentes_fluxo")) & set(df.columns)
    assert Decimal(str(linha_ttm(df).iloc[0].value)) == Decimal("130")


@pytest.mark.parametrize("mutado", [None, "anual", "atual", "anterior"])
def test_consumidor_identidade_anual_mais_q_menos_comparativo_exige_mesmo_par(mutado):
    rows = [
        fato("2025-01-01", "2025-12-31", 100),
        fato("2025-01-01", "2025-03-31", 30),
        fato("2026-01-01", "2026-03-31", 60),
    ]
    df = selecionar(rows)
    # Testa o fallback do consumidor com A/Q fornecidos, sem TTM do provider.
    df = df[df.freq.isin(["A", "Q"])].copy()
    if mutado is not None:
        role = {
            "anual": ("A", "2025-12-31"),
            "atual": ("Q", "2026-03-31"),
            "anterior": ("Q", "2025-03-31"),
        }[mutado]
        df.loc[df.freq.eq(role[0]) & df.period_end.eq(pd.Timestamp(role[1])), CAMPOS[0]] = "OUTRA"
    ttm = linha_ttm(Demonstrativos(df, "SIMULADO").df, "2026-03-31")
    if mutado is None:
        assert Decimal(str(ttm.iloc[0].value)) == Decimal("130")
        assert conferir(pacote(ttm.iloc[0]))[0]
    else:
        assert ttm.empty


def test_consumidor_nao_recompoe_q_com_grupo_tipada_incompleto():
    rows = [
        fato("2025-01-01", "2025-09-30", 60),
        fato("2025-01-01", "2025-12-31", 100),
    ] + trimestres()[2:]
    df = selecionar(rows)
    q = df[df.freq.eq("Q")].copy()
    derived = q[q.period_end.eq(pd.Timestamp("2025-12-31"))].index[0]
    grupos = _grupos(q.loc[derived])[0][1]
    for k in CAMPOS:
        grupos[0].pop(k)
    q["componentes_fluxo"] = None
    q.at[derived, "componentes_fluxo"] = grupos
    assert not Demonstrativos._ttm_derivado(q).freq.eq("TTM").any()


def test_schema_opcional_nao_adiciona_campo_ao_layout_legacy():
    from cdp.data import publico_cvm, publico_fatos, publico_ri

    assert (
        publico_cvm.FATO_DIMENSOES
        == publico_ri.COLUNAS_DIMENSOES
        == publico_fatos.SAIDA_DIMENSOES
        == CAMPOS
    )
    assert not set(CAMPOS) & set(publico_cvm.FATO_COLUNAS)
    assert not set(CAMPOS) & set(publico_ri.COLUNAS)
    assert not set(CAMPOS) & set(publico_fatos.SAIDA_COLUNAS)


@pytest.mark.parametrize("campo", CAMPOS)
def test_participante_linha_tipado_vinculado_a_identidade_manifesto(campo):
    pac = pacote(linha_ttm(selecionar(semestre())).iloc[0])
    row = pac["disponibilidade_demonstrativos"][0]
    row[campo] = "OUTRA" if campo == CAMPOS[0] else "2025-12-31"
    assert not conferir(pac)[0]
