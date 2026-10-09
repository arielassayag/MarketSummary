"""DADOS SIMULADOS: controles não autores finitos, sem seed/mercado/solver."""

from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pandas as pd

from cdp.cobertura.etf import avaliar_etfs
from cdp.cobertura.parametros import carregar_parametros

DIA = date(2026, 10, 8)
IDS = {"ETF_ILF", "ETF_EWZ", "ETF_EWW", "ETF_ECH", "ETF_EPU", "ETF_COLO", "ETF_ARGT", "ETF_BOVA11"}


def avaliar(columns, params=None):
    empty = pd.DataFrame(index=pd.DatetimeIndex([]))
    md = SimpleNamespace(
        benchmarks=pd.DataFrame(columns, index=pd.DatetimeIndex([DIA])),
        rates=empty, adj_close=empty, is_synthetic=True,
    )
    return avaliar_etfs(
        md, SimpleNamespace(etfs={}, origem="SIMULADO"),
        params or carregar_parametros(), {}, {}, None, DIA,
    )


def test_zero_e_coluna_estranha_nao_preenchem_preco_ou_criam_modelo():
    modelos, insumos = avaliar({"ILF": [0.0], "FORA_DO_UNIVERSO": [999.0]})
    assert set(modelos) == set(insumos) == IDS
    for iid in IDS:
        assert modelos[iid]["preco"] is insumos[iid]["preco"] is None
        assert modelos[iid]["data_preco"] is insumos[iid]["data_preco"] is None
        assert modelos[iid]["tem_alvo"] is False
        assert modelos[iid].get("retorno_esperado") is None
        assert any(x["insumo"] == "preco" for x in modelos[iid]["lacunas"])


def test_moeda_do_configurado_ausente_preservada_sem_herdar_preco_brl():
    modelos, insumos = avaliar({"BOVA11.SA": [17.0]})
    assert set(modelos) == set(insumos) == IDS
    assert modelos["ETF_BOVA11"]["moeda"] == "BRL"
    assert modelos["ETF_BOVA11"]["preco"] == 17.0
    assert modelos["ETF_ILF"]["moeda"] == "USD"
    assert modelos["ETF_ILF"]["preco"] is None
    assert modelos["ETF_ILF"]["tem_alvo"] is False


def test_apenas_configuracao_explicita_define_existencia_do_modelo():
    params = carregar_parametros()
    cfg = next(c for c in params.etfs["etfs"] if c["ticker"] == "ARGT")
    params = replace(params, etfs={"etfs": [cfg]})
    modelos, insumos = avaliar({"ILF": [17.0]}, params)
    assert set(modelos) == set(insumos) == {"ETF_ARGT"}
    assert modelos["ETF_ARGT"]["preco"] is None
    assert modelos["ETF_ARGT"]["tem_alvo"] is False
