"""DADOS SIMULADOS: contrato da D&A DFC exercitado pelas APIs do checkout atual."""
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from cdp.cobertura.insumos import Demonstrativos
from cdp.data.publico_fatos import selecionar_pit
from cdp.data.publico_yahoo import fatos_yahoo


def quadro(ends, rows):
    return {"colunas": ends, "linhas": rows}


def fatos(doc):
    return fatos_yahoo(doc, data_coleta=date(2026, 10, 7), financeira=False,
                       moeda="BRL", nota="DADOS SIMULADOS; publicação estimada")


@pytest.mark.parametrize("nome", ["cashflow", "quarterly_cashflow"])
@pytest.mark.parametrize("rotulo", ["Depreciation And Amortization", "Depreciation Amortization Depletion"])
def test_da_restituida_na_dfc_preserva_contrato_e_proveniencia(nome, rotulo):
    end = "2025-12-31" if nome == "cashflow" else "2026-06-30"
    doc = {"ticker": "SIMULADO.SA", "demonstracoes": {nome: quadro([end], {rotulo: [12.5]})}}
    out = fatos(doc)
    generic = out[out.item == "d_a"].reset_index(drop=True)
    dfc = out[out.item == "d_a_dfc"].reset_index(drop=True)
    assert len(generic) == len(dfc) == 1
    assert_frame_equal(generic.drop(columns="item"), dfc.drop(columns="item"))
    assert dfc.iloc[0].value == 12.5
    assert dfc.iloc[0].demonstrativo == "DFC"
    assert rotulo in dfc.iloc[0].documento
    assert dfc.iloc[0].pit_estimado


@pytest.mark.parametrize("valor", [None, float("nan"), float("inf")])
def test_ausencia_de_da_dfc_nao_e_preenchida(valor):
    doc = {"ticker": "SIMULADO.SA", "demonstracoes": {
        "cashflow": quadro(["2025-12-31"], {"Depreciation And Amortization": [valor]})}}
    assert fatos(doc).empty


def test_da_dre_nao_e_restituicao_dfc_e_filtro_existente_e_preservado():
    dre = {"ticker": "SIMULADO.SA", "demonstracoes": {
        "income_stmt": quadro(["2025-12-31"], {"Reconciled Depreciation": [25.0], "Operating Income": [100.0]})}}
    assert "d_a" in set(fatos(dre).item)
    assert "d_a_dfc" not in set(fatos(dre).item)
    parcial = {"ticker": "SIMULADO.SA", "demonstracoes": {
        "cashflow": quadro(["2025-12-31"], {"Depreciation And Amortization": [5.0], "Capital Expenditure": [-100.0]})}}
    assert not set(fatos(parcial).item) & {"d_a", "d_a_dfc"}
    zero = {"ticker": "SIMULADO.SA", "demonstracoes": {
        "cashflow": quadro(["2025-12-31"], {"Depreciation And Amortization": [0.0]})}}
    assert fatos(zero).set_index("item").loc["d_a_dfc", "value"] == 0.0


def test_ttm_dfc_atravessa_consumidor_e_nao_usa_da_dre_para_completar():
    ends = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]
    values = [12.5, 11.0, 10.0, 9.5]
    doc = {"ticker": "SIMULADO.SA", "demonstracoes": {
        "quarterly_income_stmt": quadro(ends, {"Total Revenue": [1000.0, 900.0, 800.0, 700.0],
                                                  "Operating Income": [100.0, 90.0, 80.0, 70.0],
                                                  "Reconciled Depreciation": values.copy()}),
        "quarterly_cashflow": quadro(ends, {"Depreciation And Amortization": values.copy()})}}
    complete = selecionar_pit(fatos(doc).assign(fonte="YAHOO", sha256="simulado"), date(2026, 10, 7))
    dem = Demonstrativos(complete.assign(issuer_id="BR_SIMULADO"), "BR_SIMULADO")
    value, source = dem.valor("d_a_dfc")
    expected = sum((Decimal(str(v)) for v in values), Decimal(0))
    assert Decimal(str(value)) == expected
    assert source["freq"] == "TTM" and source["escala"] == 1
    assert source["currency"] == "BRL" and source["pit_estimado"]
    doc["demonstracoes"]["quarterly_cashflow"]["linhas"]["Depreciation And Amortization"][2] = None
    partial = selecionar_pit(fatos(doc).assign(fonte="YAHOO", sha256="simulado"), date(2026, 10, 7))
    missing = partial[(partial.item == "d_a_dfc") & (partial.freq == "TTM")
                      & (partial.period_end == pd.Timestamp(ends[0]))]
    assert missing.empty
    assert not partial[(partial.item == "d_a") & (partial.freq == "TTM")].empty
