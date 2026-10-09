"""DADOS SIMULADOS: controles independentes sobre a guarda real, sem novo cálculo."""

from copy import deepcopy

import pytest
from test_cobertura_cenarios import run as run
from test_cobertura_cenarios import test_synthetic_models_never_name_real_sources as auditar


def test_todos_oito_e_cinco_ausentes_literal(run):
    ex = run[-1]
    assert len(ex.etfs) == len(ex.insumos_etf) == 8
    assert sum(e["preco"] is not None for e in ex.etfs.values()) == 3
    assert sum(e["preco"] is None for e in ex.etfs.values()) == 5
    for iid, e in ex.etfs.items():
        if e["preco"] is None:
            assert (
                e["data_preco"]
                is ex.insumos_etf[iid]["preco"]
                is ex.insumos_etf[iid]["data_preco"]
                is None
            )
            assert not e["tem_alvo"] and e.get("preco_alvo") is e.get("retorno_esperado") is None
    auditar(run)


def test_marca_no_nome_nao_e_fonte(run):
    args = deepcopy(run)
    args[-1].insumos_etf["ETF_ECH"]["nome"] = "iShares DADOS SIMULADOS"
    auditar(args)


def test_fonte_ausente_saida_legitima(run):
    args = deepcopy(run)
    e = args[-1].etfs["ETF_ECH"]
    for k in list(e):
        if k.startswith("fonte_"):
            del e[k]
    auditar(args)


@pytest.mark.parametrize("local", ["insumo", "saida"])
@pytest.mark.parametrize("fornecedor", ["Yahoo", "CVM", "SEC", "Global X"])
def test_fonte_explicita_real_recusada(run, local, fornecedor):
    args = deepcopy(run)
    ex = args[-1]
    target = ex.insumos_etf["ETF_ECH"] if local == "insumo" else ex.etfs["ETF_ECH"]
    target["fonte_preco"] = {"fonte": fornecedor}
    with pytest.raises(AssertionError):
        auditar(args)


def test_data_fabricada_sem_preco_recusada(run):
    args = deepcopy(run)
    args[-1].etfs["ETF_ECH"]["data_preco"] = "2026-10-08"
    with pytest.raises(AssertionError):
        auditar(args)


def test_preco_zero_nos_dois_nao_substitui_ausencia(run):
    args = deepcopy(run)
    args[-1].etfs["ETF_ECH"]["preco"] = 0.0
    args[-1].insumos_etf["ETF_ECH"]["preco"] = 0.0
    with pytest.raises(AssertionError):
        auditar(args)


def test_conjunto_insumos_incompleto_recusado(run):
    args = deepcopy(run)
    del args[-1].insumos_etf["ETF_ECH"]
    with pytest.raises(AssertionError):
        auditar(args)
