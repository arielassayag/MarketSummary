"""Convenções públicas do pacote em entradas pequenas e explicitamente simuladas."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cdp.contracts import AttributionLine, DailyRecord, DailyRisk
from cdp.risk.types import RiskModel
from cdp.tecnicas import (
    construir_candidata,
    decompor_risco,
    somar_atribuicao,
    somar_componentes,
)


def test_risco_anual_contra_matriz_independente_e_pesos_invalidos():
    ids, fatores = ["A", "B"], ["market", "country:BR"]
    b = np.array([[1.0, 0.5], [0.7, -0.2]])
    f = np.array([[0.04, 0.002], [0.002, 0.01]])
    d = np.array([0.09, 0.16])
    w = np.array([0.1, -0.08])
    model = RiskModel(date(2026, 10, 9), pd.DataFrame(b, index=ids, columns=fatores),
                      pd.DataFrame(f, index=fatores, columns=fatores), pd.Series(d, index=ids),
                      pd.DataFrame(columns=fatores), pd.DataFrame(columns=ids),
                      {"market": "market", "country:BR": "country"})
    inputs = [model.exposures.copy(), model.factor_cov.copy(), model.specific_var.copy()]
    got = decompor_risco(pd.Series(w, index=ids), model)
    sigma = b @ f @ b.T + np.diag(d)
    variance = float(w @ sigma @ w)
    assert got.total_vol == pytest.approx(np.sqrt(variance))
    assert got.asset_contrib.to_numpy() == pytest.approx(w * (sigma @ w) / variance)
    assert sum(got.by_group.values()) == pytest.approx(1.0)
    pd.testing.assert_frame_equal(model.exposures, inputs[0])
    pd.testing.assert_frame_equal(model.factor_cov, inputs[1])
    pd.testing.assert_series_equal(model.specific_var, inputs[2])
    with pytest.raises(ValueError, match="não finitos"):
        decompor_risco(pd.Series([np.nan], index=["A"]), model)
    with pytest.raises(KeyError, match="fora do modelo"):
        decompor_risco(pd.Series([0.1], index=["AUSENTE"]), model)
    vazio = decompor_risco(pd.Series(0.0, index=ids), model)
    assert vazio.total_vol == 0 and np.isnan(vazio.factor_share)


def _registro(day, nav, pnl, componentes, linhas):
    return DailyRecord(date=date(2026, 10, day), fund_name="DADOS SIMULADOS",
                       track_record_type="DADOS SIMULADOS", nav_start_usd=nav,
                       nav_end_usd=nav+pnl, pnl_usd=pnl, ret=pnl/nav,
                       pnl_components=componentes, attribution=linhas,
                       risk=DailyRisk(gross=0, net=0, long_exposure=0, short_exposure=0,
                                      n_long=0, n_short=0),
                       is_synthetic=True, data_notice="DADOS SIMULADOS", prev_record_hash="")


def test_atribuicao_usd_diaria_preserva_cobertura_parcial_e_nao_composta():
    records = [_registro(8, 1000, 10, {"equity": 10, "borrow": -1},
                         [AttributionLine(group="issuer", name="A", pnl_usd=10, contribution=10/1000)]),
               _registro(9, 1010, -5, {"equity": -5},
                         [AttributionLine(group="issuer", name="A", pnl_usd=-5, contribution=-5/1010)])]
    before = [r.model_dump(mode="json") for r in records]
    comp = somar_componentes(records).set_index("key")
    attr = somar_atribuicao(records, "issuer").set_index("name")
    assert comp.loc["equity", "pnl_usd"] == pytest.approx(10-5)
    assert comp.loc["equity", "contribution"] == pytest.approx(10/1000-5/1010)
    assert comp.loc["equity", "days"] == 2
    assert comp.loc["borrow", "days"] == 1
    assert "costs" not in comp.index
    assert attr.loc["A", "pnl_usd"] == pytest.approx(10-5)
    assert attr.loc["A", "contribution"] == pytest.approx(10/1000-5/1010)
    assert attr.loc["A", "days"] == 2
    assert somar_atribuicao(records, "grupo-desconhecido").empty
    assert somar_componentes([]).empty
    assert before == [r.model_dump(mode="json") for r in records]


@pytest.mark.parametrize("nav", [0, -1, float("nan")])
def test_otimizador_recusa_nav_antes_de_acessar_demais_operandos(nav):
    class NaoAcessar:
        def __getattribute__(self, name):
            raise AssertionError(f"Operando acessado antes da recusa de NAV: {name}")
    value = NaoAcessar()
    with pytest.raises(ValueError, match="NAV precisa ser positivo"):
        construir_candidata(value, value, value, value, value, nav)
