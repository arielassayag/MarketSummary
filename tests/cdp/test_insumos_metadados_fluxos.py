"""Políticas independentes usam as mesmas fontes reais do pacote DADOS SIMULADOS."""

from copy import deepcopy
from datetime import date

import pytest

from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import preparar_emissor
from cdp.cobertura.margens import METODO, margens_alinhadas
from cdp.cobertura.parametros import arquetipo_padrao, carregar_parametros
from cdp.data.synthetic import make_synthetic_market

D = date(2026, 10, 8)
METADADOS = ("historico_fontes", "historico_periodos", "historico_bases", "historico_moedas",
             "bases_fluxos", "moedas_fluxos", "periodos_fluxos")


@pytest.fixture(scope="module")
def fonte():
    md = make_synthetic_market(seed=7, as_of=D)
    params = carregar_parametros()
    ids = list(md.universe.issuers.index)
    dados = coletar(md, D, ids, list(md.universe.lines.index), ["ILF", "EWZ", "EWW"])
    iid = next(i for i in ids if arquetipo_padrao(i, md.universe.issuers.loc[i, "gics_sector"]).arquetipo == "corporativo"
               and i in set(dados.demonstrativos["issuer_id"]))
    return md, params, dados, iid


def test_margem_independe_da_politica_de_reinvestimento_e_recebe_mesmas_fontes(fonte):
    md, params, dados, iid = fonte
    ambas = deepcopy(params)
    ambas.sec("qualidade")["margem_fluxos_metodo"] = METODO
    so_margem = deepcopy(ambas)
    so_margem.sec("projecao").pop("reinvestimento_metodo")
    p = preparar_emissor(md, dados, so_margem, iid, D)
    referencia = preparar_emissor(md, dados, ambas, iid, D)
    assert p == referencia
    d = margens_alinhadas(p)
    assert d["corrente"]["status"] == "comparavel"
    assert d["corrente"]["margem"] == pytest.approx(p["t.ebit"] / p["t.receita"])
    assert d["historico"] and all(v["status"] == "comparavel" for v in d["historico"].values())
    for item in ("receita", "ebit"):
        for ano, valor in p["historico"][item].items():
            assert p["historico_fontes"][item][ano]["valor_modelo"] == valor
            assert p["historico_periodos"][item][ano] == f"A|{ano}-12-31"


def test_ausencia_de_ambas_politicas_conserva_corpo_e_numeros_legados(fonte):
    md, params, dados, iid = fonte
    legado = deepcopy(params)
    legado.sec("projecao").pop("reinvestimento_metodo", None)
    legado.sec("qualidade").pop("margem_fluxos_metodo", None)
    p = preparar_emissor(md, dados, legado, iid, D)
    ativado = deepcopy(legado)
    ativado.sec("qualidade")["margem_fluxos_metodo"] = METODO
    q = preparar_emissor(md, dados, ativado, iid, D)
    assert all(k not in p for k in METADADOS)
    for k in METADADOS:
        q.pop(k)
    assert p == q
