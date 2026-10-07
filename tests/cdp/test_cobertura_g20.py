"""G20: revisão analítica sem ancorar a visão no consenso. DADOS SIMULADOS, sem rede."""

from copy import deepcopy
from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from cdp.cobertura.fontes import coletar
from cdp.cobertura.modelo import Avaliador, Drivers
from cdp.cobertura.motor import executar, modelo_json
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.qualidade import _g20
from cdp.data.synthetic import make_synthetic_market


@pytest.fixture(scope="module")
def params():
    return carregar_parametros()


def pacote():
    return {"preco": 10.0, "consenso": {"plausivel": True, "n_alvo": 8,
                                         "alvo_alto": 12.0, "alvo_baixo": 8.0}}


def modelo(tp=16.0, valores=(15.0, 17.0)):
    return {"tp": tp, "tp_pessimista": 8.0, "tp_otimista": 18.0, "etr": 0.60,
            "metodos": [{"m": str(i), "valor": v} for i, v in enumerate(valores)]}


@pytest.mark.parametrize("tp,valores", [(16.0, (15.0, 17.0)), (5.0, (4.5, 5.5))])
def test_divergencia_corroborada_do_consenso_e_informativa(params, tp, valores):
    g = _g20(pacote(), modelo(tp, valores), params)
    assert g["status"] == "informativo"
    assert "revisão analítica" in g["detalhe"] and "2 métodos brutos" in g["detalhe"]


@pytest.mark.parametrize("valores", [(15.0,), (15.0, 9.0), (11.0, 40.0), (15.0, -3.0)])
def test_sem_corroboração_ha_aviso_mesmo_com_cv_declarado_baixo(params, valores):
    m = {**modelo(valores=valores), "cv": 0.01, "cv_todos": 0.01}
    assert _g20(pacote(), m, params)["status"] == "aviso"


def test_metodo_limitado_nao_esconde_dissidencia(params):
    m = modelo()
    m["metodos"][1].update(valor=16.0, valor_bruto=5.0)
    assert _g20(pacote(), m, params)["status"] == "aviso"
    m["metodos"][1].update(valor=None, valor_bruto=None, valor_calculado=-2.0)
    assert _g20(pacote(), m, params)["status"] == "aviso"


def test_dois_metodos_alinhados_bastam_com_cv_sobre_todos(params):
    p = {"preco": 100.0, "consenso": {"plausivel": True, "n_alvo": 8, "alvo_alto": 90.0}}
    m = {**modelo(tp=130.0, valores=(120.0, 125.0, 95.0)), "etr": 0.30}
    assert _g20(p, m, params)["status"] == "informativo"
    # A terceira opinião não pode ser descartada na dispersão.
    m["metodos"][2]["valor"] = -200.0
    assert _g20(p, m, params)["status"] == "aviso"


def test_copias_do_mesmo_metodo_nao_sao_corroboração(params):
    m = modelo()
    m["metodos"] = [{"m": "rim", "valor": 15.0}, {"m": "rim", "valor": 15.0}]
    assert _g20(pacote(), m, params)["status"] == "aviso"


def test_faixa_unilateral_sozinha_nao_invalida_cenario(params):
    m = {**modelo(tp=12.0, valores=(11.0, 13.0)), "tp_pessimista": 10.5}
    g = _g20({"preco": 10.0}, m, params)
    assert g["status"] == "informativo" and "não invalida" in g["detalhe"]
    assert m["tp_pessimista"] == 10.5  # jamais limitar o pessimista ao preço para atingir uma meta


def test_faixa_unilateral_com_insumo_invalido_ou_falha_da_simulacao_avisa(params):
    m = {**modelo(tp=12.0), "tp_pessimista": 10.5}
    g = _g20({"preco": 10.0}, m, params, portoes=[{"codigo": "G13c", "status": "bloqueio"}])
    assert g["status"] == "aviso" and "G13c" in g["detalhe"]
    m["diagnostico_cenarios"] = {"falhas": ["método do caso-base ausente na simulação"]}
    g = _g20({"preco": 10.0}, m, params)
    assert g["status"] == "aviso" and "ausente na simulação" in g["detalhe"]


@pytest.mark.parametrize("codigo", ["G17", "G13c"])
def test_aviso_de_conferencia_nao_comprova_erro_de_cenario(params, codigo):
    m = {**modelo(tp=12.0), "tp_pessimista": 10.5}
    g = _g20({"preco": 10.0}, m, params, portoes=[{"codigo": codigo, "status": "aviso"}])
    assert g["status"] == "informativo"
    assert "sem falha comprovada" in g["detalhe"]


def test_g11_proximo_do_limite_exige_corroboração_sem_mudar_seu_limite(params):
    m = {**modelo(tp=19.8, valores=(18.0, 19.0)), "etr": 0.98, "tp_otimista": 23.0}
    g = _g20({"preco": 10.0}, m, params)
    assert g["status"] == "informativo" and "G11" in g["detalhe"]
    m["metodos"] = [{"valor": 18.0}]
    assert _g20({"preco": 10.0}, m, params)["status"] == "aviso"


def test_recalculo_historico_mantem_regra_arquivada(params):
    val = deepcopy(params.valuation)
    val["versao"] = "2026-10.3"
    del val["qualidade"]["g20_corroboracao_metodos_min"]
    legado = replace(params, valuation=val)
    assert _g20(pacote(), modelo(), legado)["status"] == "aviso"
    assert _g20(pacote(), modelo(), params)["status"] == "informativo"


@pytest.fixture(scope="module")
def execucao(params):
    d = date(2026, 10, 8)
    md = make_synthetic_market(seed=7, as_of=d)
    dados = coletar(md, d, list(md.universe.issuers.index), list(md.universe.lines.index), ["ILF"])
    return executar(md, dados, params, d)


def test_integridade_da_simulacao_e_auditavel_e_independente_do_preco(execucao, params):
    for iid, m in execucao.modelos.items():
        if not m.get("tem_alvo"):
            continue
        diag = m["diagnostico_cenarios"]
        assert diag["falhas"] == []
        assert diag["erro_reproducao_base"] <= 1e-12
        assert diag["sorteios_finitos"] == diag["sorteios_total"]
        assert modelo_json(execucao, iid, params)["cenarios"]["diagnostico_cenarios"] == diag


def test_simulacao_detecta_metodo_do_caso_base_omitido(execucao, params, monkeypatch):
    iid = next(i for i, m in execucao.modelos.items() if m.get("n_metodos", 0) >= 2)
    av = Avaliador(execucao.pacotes[iid], execucao.contexto, params, execucao.rf["valor"], {})
    av.preparar_metodos()
    validos = av.metodos_validos()
    original = av._valor_metodo

    def omitir(m, dr):
        if m == validos[0] and np.ndim(dr.d_ke) > 0:
            raise ValueError("falha simulada")
        return original(m, dr)

    monkeypatch.setattr(av, "_valor_metodo", omitir)
    vals = {m: np.asarray(original(m, Drivers())) for m in validos}
    tp = float(av.combinar(vals) * (1 + av.cc.ke) - av.dps12)
    m = av._cenarios(float(av.pac["preco"]), tp, 0.0, validos)
    assert validos[0] not in m["diagnostico_cenarios"]["metodos_usados"]
    assert "ausentes na simulação" in m["diagnostico_cenarios"]["falhas"][0]
