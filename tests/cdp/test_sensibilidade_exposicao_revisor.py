"""Revisor não autor: contratos finitos de apresentação, DADOS SIMULADOS nos metadados.

Os preços/grades permanecem nas cinco fixtures históricas literais do teste autoral.
Não executa valuation, Monte Carlo, novo cenário econômico ou coleta.
"""

import copy
import json

import pytest
from test_sensibilidade_exposicao import FIXTURES, _renderer

from cdp.cobertura.modelo import exposicao_sensibilidade
from cdp.workflow.painel_cobertura import _sensibilidade


@pytest.mark.parametrize(
    "arquetipo,canal,consumidores",
    [
        ("commodity", "d_comm", {"fcff_normalizado"}),
        ("banco", "d_roe", {"rim", "rim_real", "pb_justificado", "multiplo_justificado",
                              "ddm", "ddm_real", "regressao_pb_roe"}),
        ("corporativo", "d_g", {"pb_justificado", "multiplo_justificado", "ddm", "ddm_real",
                                "fcff", "fcff_real", "fcff_vida_finita", "fcff_normalizado"}),
    ],
)
def test_lista_completa_consumidores_confrontada_com_rotas_literais(arquetipo, canal, consumidores):
    # Esperado por leitura independente das rotas _valor_metodo/_fcff/_regressao,
    # sem chamar essas funções ou usar a saída candidata para compor o esperado.
    todos = ["rim", "rim_real", "pb_justificado", "multiplo_justificado", "ddm", "ddm_real",
             "fcff", "fcff_real", "fcff_vida_finita", "fcff_normalizado", "regressao_pb_roe",
             "regressao_pl", "regressao_ev_receita", "soma_partes"]
    for metodo in todos:
        out = exposicao_sensibilidade(arquetipo, [metodo])
        assert out["canal_colunas"] == canal
        assert out["colunas_aplicavel"] is (metodo in consumidores)
        assert out["metodos_colunas"] == ([metodo] if metodo in consumidores else [])
        assert out["metodos_desconhecidos"] == []


@pytest.mark.parametrize("estado,esperado", [("ativo", True), ("zero", False), ("ausente", False)])
def test_somente_consumidor_efetivamente_participante_conserva_grade(estado, esperado):
    m = copy.deepcopy(next(m for m in FIXTURES if m["issuer_id"] == "BR_VALE"))
    d = copy.deepcopy(next(d for d in m["metodos"] if d["m"] == "fcff_normalizado"))
    d["peso"] = 0 if estado == "zero" else 1
    if estado == "ausente":
        d["valor"] = None
    m["metodos"] = [d]
    before = copy.deepcopy(m)
    out = _sensibilidade(m, False)
    assert m == before
    assert out["aplicabilidade"]["colunas_aplicavel"] is esperado
    assert out["aplicabilidade"]["metodos_colunas"] == (["fcff_normalizado"] if esperado else [])
    assert [[c["t"] for c in r["c"]] for r in out["celulas"]] == m["sensibilidade"]["preco_alvo_texto"]
    assert out["citavel"] is False


@pytest.mark.parametrize("peso,esperado", [(0, True), (1, None)])
def test_metodo_desconhecido_so_participante_torna_inventario_incerto(peso, esperado):
    m = copy.deepcopy(next(m for m in FIXTURES if m["issuer_id"] == "BR_VALE"))
    d = copy.deepcopy(next(d for d in m["metodos"] if d["m"] == "fcff_normalizado"))
    d["m"], d["peso"] = "metodo_nao_catalogado_SIMULADO", peso
    m["metodos"].append(d)
    out = _sensibilidade(m, True)
    assert out["aplicabilidade"]["colunas_aplicavel"] is esperado
    assert out["aplicabilidade"]["metodos_colunas"] == ["fcff_normalizado"]
    if peso:
        assert out["aplicabilidade"]["ke_so_rolagem"] is None


@pytest.mark.parametrize("ausencia", ["metodos", "arquetipo", "ambos"])
def test_ausencia_legada_nao_prova_ausencia_de_consumidor(tmp_path, ausencia):
    m = copy.deepcopy(next(m for m in FIXTURES if m["issuer_id"] == "BR_VALE"))
    if ausencia in ("metodos", "ambos"):
        del m["metodos"]
    if ausencia in ("arquetipo", "ambos"):
        del m["arquetipo"]
    out = _sensibilidade(m, False)
    assert out["aplicabilidade"]["colunas_aplicavel"] is None
    assert out["aplicabilidade"]["ke_so_rolagem"] is None
    rendered = json.dumps(_renderer(tmp_path, out), ensure_ascii=False)
    assert "cv-hm" in rendered
    assert "não conferida" in rendered
    assert "só para auditoria" in rendered


def test_duplicata_de_metodo_nao_duplica_lista_e_parametro_so_altera_descricao():
    e = exposicao_sensibilidade("commodity", ["fcff_normalizado", "fcff_normalizado"],
                               anos_plenos=2, zero_em=7)
    assert e["metodos_colunas"] == ["fcff_normalizado"]
    assert "ano 2" in e["perfil"] and "ano 7" in e["perfil"]
    assert "+0,20 equivale a +20 p.p." in e["formula_delta_margem"]
    assert "w_t é adimensional" in e["formula_delta_margem"]


@pytest.mark.parametrize("metodos,esperado", [(["regressao_pl", "soma_partes"], True),
                                            (["soma_partes", "rim_real"], False),
                                            (["regressao_ev_receita", "ddm_real"], False),
                                            ([], False)])
def test_ke_rolagem_exige_todos_metodos_participantes_fixos(metodos, esperado):
    e = exposicao_sensibilidade("commodity", metodos)
    assert e["ke_so_rolagem"] is esperado
    assert bool(e["descricao_ke"]) is esperado
    if esperado:
        assert "V0 permanece fixo" in e["descricao_ke"]
        assert "TP12 = V0 × (1 + ke) − DPS12" in e["descricao_ke"]


def test_renderer_canal_inaplicavel_ke_rolagem_preserva_coluna_base(tmp_path):
    m = next(m for m in FIXTURES if m["issuer_id"] == "BR_BRADESPAR")
    before = copy.deepcopy(m)
    out = _sensibilidade(m, False)
    assert out["aplicabilidade"]["colunas_aplicavel"] is False
    assert out["aplicabilidade"]["ke_so_rolagem"] is True
    rendered = _renderer(tmp_path, out)
    table = next(x for x in rendered["children"] if x["tag"] == "tabela")
    assert [r["alvo"] for r in table["attrs"]["rows"]] == [r[2] for r in m["sensibilidade"]["preco_alvo_texto"]]
    text = json.dumps(rendered, ensure_ascii=False)
    assert "V0 permanece fixo" in text
    assert "cv-hm" not in text
    assert "só para auditoria" in text
    assert m == before
