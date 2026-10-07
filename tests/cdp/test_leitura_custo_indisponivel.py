"""DADOS SIMULADOS: ausência de previsão, subtotal e zero nas APIs de apresentação."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from cdp.workflow import contrato_custos
from cdp.workflow.painel import _proposal_summary
from cdp.workflow.reports import _expected_cost


def proposta(contrato, custos):
    overrides = ({contrato_custos.PROPOSAL_KEY: contrato_custos.stamp()} if contrato == "v2" else
                 {contrato_custos.PROPOSAL_KEY: dict(contrato_custos.STAMP_V1)}
                 if contrato == "v1" else {})
    trades = [SimpleNamespace(est_cost_bps=bps, notional_usd=10000.0,
                              weight_change=0.01) for bps in custos]
    return SimpleNamespace(
        overrides=overrides, trades=trades, positions=[], hard_failures=[], soft_failures=[],
        risk=SimpleNamespace(n_long=0, n_short=0, gross=0.0, net=0.0, beta=0.0,
                             ex_ante_vol=0.0, var_1d_99=0.0),
        optimizer=SimpleNamespace(expected_alpha_annual=None, expected_cost_annual=None),
    )


@pytest.mark.parametrize("contrato", ["legado", "v1", "v2"])
@pytest.mark.parametrize("custos", [[], [None, None], [0.0], [None, 2.5]])
def test_ausencia_integral_prospectiva_zero_e_subtotal_com_cobertura(contrato, custos):
    p = proposta(contrato, custos)
    partial = any(bps is None for bps in custos)
    known = [bps for bps in custos if bps is not None]
    expected = (None if contrato == "v2" and custos and not known else
                float(sum((Decimal("10000") * Decimal(str(bps)) / Decimal("10000")
                           for bps in known), Decimal(0))))
    assert _expected_cost(p) == (expected, partial)
    panel = _proposal_summary(p)
    assert panel["trade_cost_usd"] == expected
    assert panel["trade_cost_partial"] is partial


def test_estimativa_indisponivel_nao_altera_payload_proposta():
    p = proposta("v2", [None, None])
    before = dict(p.overrides[contrato_custos.PROPOSAL_KEY])
    assert _expected_cost(p) == (None, True)
    assert _proposal_summary(p)["trade_cost_usd"] is None
    assert p.overrides[contrato_custos.PROPOSAL_KEY] == before
    assert all(t.est_cost_bps is None for t in p.trades)
