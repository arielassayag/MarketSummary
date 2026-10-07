"""DADOS SIMULADOS: unidade declarada não é reinterpretada para caber numa faixa de LPA."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.cobertura.fontes import DadosPublicos
from cdp.cobertura.insumos import _consenso, _Pacote
from cdp.cobertura.parametros import _validar, carregar_parametros
from cdp.universe import Universe

D = date(2026, 10, 6)


def _pacote(*, moeda="USD", historico=False, fx=True, eps1=0.00954):
    # Recuperação de prejuízo: o LPA previsto pode ser pequeno diante do realizado.
    # A dupla conversão USD→MXN era aceita apenas porque aumentava essa razão.
    lines = pd.DataFrame([{"ticker": "X.MX", "issuer_id": "X", "currency": "MXN",
                           "line_type": "LOCAL", "adr_ratio": 1.0}]).set_index("ticker")
    md = SimpleNamespace(universe=Universe(lines, pd.DataFrame()), is_synthetic=True,
                         fx=pd.DataFrame({"MXN": [1 / 18]} if fx else {}, index=[pd.Timestamp(D)]))
    con = pd.DataFrame([{"ticker": "X.MX", "eps_fy1": eps1, "eps_fy2": 0.07232,
                         "moeda_estimativas": moeda, "n_analistas_eps": 10}])
    dados = DadosPublicos(pd.DataFrame(), con, pd.DataFrame(), pd.DataFrame(),
                          pd.DataFrame(), pd.DataFrame())
    params = carregar_parametros()
    if historico:
        val = deepcopy(params.valuation)
        val.pop("consenso", None)
        val["versao"] = "2026-10.4"
        params = replace(params, valuation=val)
    pk = _Pacote()
    _consenso(md, dados, params, pk, "X", "X.MX", "MXN", "USD", 21.09, 100, -2.0, {}, D)
    return pk


def test_moeda_declarada_convertida_uma_vez_em_ambos_exercicios():
    pk = _pacote()
    assert pk.v["eps_fy1"] == pytest.approx(0.00954 * 18)
    assert pk.v["eps_fy2"] == pytest.approx(0.07232 * 18)
    assert pk.v["consenso"]["status_lpa"] == "fx_corrigido"
    assert pk.v["consenso"]["fator_lpa"] == 18
    assert pk.v["consenso"]["moeda_lpa"] == "USD"
    assert any("declaradas preservadas" in a for a in pk.avisos)


def test_lpa_distante_do_realizado_na_mesma_moeda_nao_muda_unidade():
    pk = _pacote(moeda="MXN")
    assert pk.v["eps_fy1"] == 0.00954
    assert pk.v["eps_fy2"] == 0.07232
    assert pk.v["consenso"]["fator_lpa"] == 1
    assert pk.v["consenso"]["status_lpa"] == "ok"


def test_apenas_ano_dois_tambem_exige_moeda_e_converte_uma_vez():
    pk = _pacote(eps1=None)
    assert pk.v["eps_fy1"] is None
    assert pk.v["eps_fy2"] == pytest.approx(0.07232 * 18)
    assert pk.v["consenso"]["fator_lpa"] == 18
    sem_moeda = _pacote(eps1=None, moeda=None)
    assert "eps_fy2" not in sem_moeda.v
    assert sem_moeda.v["consenso"]["status_lpa"] == "moeda_indeterminada"


def test_moeda_ausente_nao_inferida_da_cotacao_ou_balanco():
    pk = _pacote(moeda=None)
    assert pk.v["eps_fy1"] is None
    assert "eps_fy2" not in pk.v
    assert pk.v["consenso"]["status_lpa"] == "moeda_indeterminada"
    assert any(lacuna["insumo"] == "eps_fy1" for lacuna in pk.lacunas)


def test_sem_cambio_nao_usa_estimativa_como_se_fosse_na_moeda_da_linha():
    pk = _pacote(fx=False)
    assert pk.v["eps_fy1"] is None
    assert pk.v["consenso"]["status_lpa"] == "cambio_indisponivel"


def test_recalculo_historico_preserva_regra_anterior_sem_chave_nova():
    pk = _pacote(historico=True)
    assert pk.v["eps_fy1"] == pytest.approx(0.00954 * 18 * 18)
    assert pk.v["eps_fy2"] == pytest.approx(0.07232 * 18 * 18)
    assert pk.v["consenso"]["status_lpa"] == "unidade_corrigida"
    assert "unidade_metodo" not in pk.v["consenso"]


@pytest.mark.parametrize("secao,chave", [("consenso", "unidade_metodo"),
                                        ("projecao", "reinvestimento_metodo"),
                                        ("projecao", "reinvestimento_regime")])
def test_politica_desconhecida_nao_reverte_silenciosamente_a_formula_anterior(secao, chave):
    params = carregar_parametros()
    val = deepcopy(params.valuation)
    val[secao][chave] = "desconhecido"
    with pytest.raises(ValueError, match="desconhecido"):
        _validar(val, params.arquetipos, params.betas)
