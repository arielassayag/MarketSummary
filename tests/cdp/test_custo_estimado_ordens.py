"""DADOS SIMULADOS: pisos planejados e débito distintos; oráculos Decimal independentes."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.config import load_config
from cdp.contracts import Trade, TradeAction
from cdp.portfolio.costs import custos_fechamento
from cdp.workflow.weekly import apply_min_order_costs

ROOT = Path(__file__).resolve().parents[2]


def cfg():
    return load_config(ROOT / "configs/cdp/fund.yaml")


def trade(ticker, quantity, notional, action=TradeAction.BUY, base=12.0):
    return Trade(issuer_id="DADOS_SIMULADOS", ticker=ticker, shares=quantity,
                 notional_usd=notional, action=action, weight_change=.01,
                 currency="MXN" if ticker.endswith(".MX") else "USD", est_cost_bps=base)


def planned(trades, config, prices):
    # Mesmo teste financeiro contra v0/v1/v2; versões anteriores usam seu estimador público.
    try:
        from cdp.workflow.estimativa_custos import estimate
    except ImportError:
        positions = [SimpleNamespace(execution_ticker=t, price_local=p) for t, p in prices.items()]
        return apply_min_order_costs(trades, positions, config), None
    return estimate(trades, config, prices=prices, as_of="2026-11-12",
                    snapshot_hash="DADOS SIMULADOS fonte atual",
                    base_commissions={t.issuer_id: {"bps": config.costs.commission_bps[
                        "BR" if t.ticker.endswith(".SA") else "MX" if t.ticker.endswith(".MX")
                        else "CL" if t.ticker.endswith(".SN") else "US"],
                        "source": "DADOS SIMULADOS: comissão explicitamente incluída na base desta fixture"}
                                      for t in trades})


def decimal_floor(config, market, amounts):
    rate = Decimal(str(config.costs.commission_bps[market])) / Decimal("10000")
    table = config.costs.min_order_cost_usd
    floor = Decimal(str(table.get(market, max(table.values())))) if table else Decimal("0")
    return sum(max(amount * rate, floor) for amount in amounts)


def test_regressao_natural_mesmos_inputs_mixed_floor_planejado():
    source = json.loads((Path(__file__).parent / "fixtures/custo_minimo_reserva.json").read_text())
    row = source["row"]
    config = cfg()
    base = 12.0
    current = trade(row["ticker"], 24812, float(row["notional_usd"]), base=base)
    out, _ = planned([current], config, {current.ticker: float(row["price_local"])})
    expected = Decimal(source["row"]["commission_sum_individual_order_floors_usd"])
    rate = Decimal(str(config.costs.commission_bps["MX"]))
    notional = Decimal(source["row"]["notional_usd"])
    # Comissão variável já inclusa nos 12bps é retirada antes de comparar a nova comissão.
    got = notional * Decimal(str(out[0].est_cost_bps - base + float(rate))) / Decimal("10000")
    assert float(got) == pytest.approx(float(expected), abs=1e-10)


@pytest.mark.parametrize("ticker,quantity,price,market,parts", [
    ("SIM.SA", 235, 25, "BR", [200, 35]),
    ("SIM.SA", 35, 25, "BR", [35]),
    ("SIM.MX", 201, 200, "MX", [200, 1]),
    ("SIM.MX", 201, 201, "MX", [200, 1]),
    ("SIM.MX", 203, 201, "MX", [200, 3]),
    ("SIM.MX", 3, 201, "MX", [3]),
    ("SIM.SN", 1733, 25, "CL", [1733]),
    ("SIMUS", 235, 25, "US", [235]),
])
@pytest.mark.parametrize("action", list(TradeAction))
def test_planejadas_sinais_lotes_e_comissao_independente(ticker, quantity, price, market, parts, action):
    config = cfg()
    notional = Decimal("28000")
    original = trade(ticker, quantity, float(notional), action)
    out, diagnostic = planned([original], config, {ticker: price})
    row = diagnostic["trades"][0]
    sign = 1 if action in (TradeAction.BUY, TradeAction.COVER) else -1
    assert [p["shares"] for p in row["orders"]] == [sign * part for part in parts]
    amounts = [Decimal(part) * notional / Decimal(quantity) for part in parts]
    expected = decimal_floor(config, market, amounts)
    assert row["commission_usd"] == pytest.approx(float(expected), abs=1e-10)
    expected_bps = float(expected / notional * Decimal("10000"))
    rate = config.costs.commission_bps[market]
    assert out[0].est_cost_bps == pytest.approx(original.est_cost_bps + max(0, expected_bps - rate))
    assert original.model_dump(exclude={"est_cost_bps"}) == out[0].model_dump(exclude={"est_cost_bps"})


@pytest.mark.parametrize("missing", ["quantity", "price", "base", "notional_zero", "price_nan"])
def test_ausencia_planejada_nao_presume_ordem_lote_custo(missing):
    config = cfg()
    t = trade("SIM.MX", None if missing == "quantity" else 203,
              0.0 if missing == "notional_zero" else 28000,
              base=None if missing == "base" else 12)
    prices = {t.ticker: float("nan") if missing == "price_nan" else 201} if missing != "price" else {}
    out, diagnostic = planned([t], config, prices)
    row = diagnostic["trades"][0]
    assert out[0].est_cost_bps is None
    assert row["state"] == "indisponivel" and row["reasons"]
    assert row["orders"] is row["commission_usd"] is row["commission_bps"] is None


def test_zero_observado_e_ausencia_distintos_sem_uma_ordem_presumida():
    t = trade("SIM.MX", 0, 0)
    out, diagnostic = planned([t], cfg(), {t.ticker: 201})
    assert out[0].est_cost_bps is None  # bps em 0/0 não definido.
    row = diagnostic["trades"][0]
    assert row["state"] == "sem_ordem" and row["orders"] == []
    assert row["commission_usd"] == 0.0


def test_liquidacao_sem_alvo_usa_preco_atual_e_zero_crossing_tem_duas_trades():
    from cdp.portfolio.trades import build_trades

    config = cfg()
    current = SimpleNamespace(issuer_id="DADOS_SIMULADOS", ticker="SIM.MX", currency="MXN",
                              shares=203, weight=.028, notional_usd=28000)
    target = SimpleNamespace(issuer_id="DADOS_SIMULADOS", execution_ticker="SIM.MX", currency="MXN",
                             shares=-3, weight=-.00041, notional_usd=-410, adtv_usd=1e8)
    # Quantidades geradas pelas interfaces canônicas; sem alteração de alvo/ordens no replay.
    trades = build_trades([target], [current], 1e6, cost_bps=pd.Series({"SIM.MX": 12.0}))
    assert [t.action for t in trades] == [TradeAction.SELL, TradeAction.SHORT]
    assert [t.shares for t in trades] == [203, 3]
    out, diagnostic = planned(trades, config, {"SIM.MX": 201})
    assert [p["book"] for p in diagnostic["trades"][0]["orders"]] == ["lote_padrao", "pico"]
    assert [p["book"] for p in diagnostic["trades"][1]["orders"]] == ["pico"]
    assert [r["trade_index"] for r in diagnostic["trades"]] == [0, 1]
    assert all(t.est_cost_bps is not None for t in out)
    liquidation = build_trades([], [current], 1e6, cost_bps=pd.Series({"SIM.MX": 12.0}))
    assert len(liquidation) == 1 and liquidation[0].action == TradeAction.SELL
    known, detail = planned(liquidation, config, {"SIM.MX": 201})
    assert known[0].est_cost_bps is not None
    assert detail["trades"][0]["price_local_current"] == 201
    unknown, reasons = planned(liquidation, config, {})
    assert unknown[0].est_cost_bps is None
    assert reasons["trades"][0]["reasons"] == ["preco_local_atual_ausente_ou_invalido"]


def test_partial_fill_nao_reusa_comissao_planejada():
    config = cfg()
    # Preço/FX/quantidade reais hipotéticos do MOC diferem da ordem planejada.
    _, diagnostic = planned([trade("SIM.MX", 203, 28000)], config, {"SIM.MX": 201})
    planned_commission = diagnostic["trades"][0]["commission_usd"]
    filled = pd.DataFrame([{"notional_usd": 1000., "adtv_usd": 1e8, "sigma_d": .02,
                            "market": "MX", "currency": "MXN", "categoria": "MX",
                            "local_fechado": False, "n_ordens": 1,
                            "contrato_comissao": "individual_orders/v1",
                            "nocionais_ordens_usd": [1000.]}], index=["SIM.MX"])
    result = custos_fechamento(filled, config)
    paid = result.at["SIM.MX", "commission_bps"] * 1000 / 1e4
    expected = decimal_floor(config, "MX", [Decimal("1000")])
    assert paid == pytest.approx(float(expected))
    assert paid != pytest.approx(planned_commission)


@pytest.mark.parametrize("ticker,quantity,notional", [("SIMUS", 235, 28000), ("SIM.MX", 200, 28000)])
def test_estimativa_sem_minimo_ou_unica_sem_double_add_preserva_base(ticker, quantity, notional):
    config = cfg().with_overrides({"costs": {"min_order_cost_usd": {}}})
    original = trade(ticker, quantity, notional)
    out, _ = planned([original], config, {ticker: 201})
    assert out[0].model_dump() == original.model_dump()


def test_payload_suporta_descritor_v1_aprovado_literal_e_v2_distinto():
    from cdp.workflow.contrato_custos import (
        CURRENT,
        LEGACY,
        PROPOSAL_KEY,
        STAMP_V1,
        contract,
        descriptor,
        payload,
        stamp,
    )

    class Approved(SimpleNamespace):
        def proposal_hash(self):
            return "hash aprovado da proposta propria"

    config = cfg()
    old = Approved(overrides={}, proposal_id="legado")
    first = Approved(overrides={PROPOSAL_KEY: dict(STAMP_V1)}, proposal_id="aprovada-v1")
    second = Approved(overrides={PROPOSAL_KEY: stamp()}, proposal_id="aprovada-v2")
    assert contract(old) == LEGACY and descriptor(old) is None
    assert PROPOSAL_KEY not in old.overrides
    assert contract(first) == contract(second) == CURRENT
    empty = pd.DataFrame()
    from datetime import date

    assert payload(empty, empty, first, config, date(2026, 11, 13), 0)["contract"] == STAMP_V1
    assert descriptor(second)["weekly_estimate"] == "planned_individual_orders/v1"
    assert descriptor(first)["weekly_estimate"] == "aggregate_line_approximation/v0"
    assert payload(empty, empty, second, config, date(2026, 11, 13), 0)["contract"] != STAMP_V1


@pytest.mark.parametrize("short_line", ["SIMADR", None])
def test_comissao_base_reextrai_curvas_reais_zero_cross_e_fallback_conhecido(short_line):
    from cdp.workflow.estimativa_custos import estimate, included_commissions

    component = pd.DataFrame({("long", "ticker"): ["SIM.MX"],
                              ("long", "commission_bps"): [3.0],
                              ("short", "ticker"): [short_line],
                              ("short", "commission_bps"): [1.0]}, index=["DADOS_SIMULADOS"])
    model = SimpleNamespace(components=component, linear_rate_long=object(), impact_k_long=object(),
                            linear_rate_short=object(), impact_k_short=object())
    target, current = pd.Series({"DADOS_SIMULADOS": -.03}), pd.Series({"DADOS_SIMULADOS": .02})
    meta = included_commissions(target, current, model)
    expected = ((Decimal(".02") * Decimal("3") + Decimal(".03") * Decimal("1"))
                / Decimal(".05")) if short_line else Decimal("3")
    assert meta["DADOS_SIMULADOS"]["bps"] == pytest.approx(float(expected))
    original = trade("SIMUS", 100, 20000, base=12)
    out, detail = estimate([original], cfg(), prices={"SIMUS": 100}, as_of="2026-11-12",
                           snapshot_hash="DADOS SIMULADOS", base_commissions=meta)
    rate = cfg().costs.commission_bps["US"]
    assert out[0].est_cost_bps == pytest.approx(12 - float(expected) + rate)
    assert detail["trades"][0]["included_commission_bps"] == pytest.approx(float(expected))


def test_sem_metadado_comissao_base_permanece_indisponivel():
    from cdp.workflow.estimativa_custos import estimate

    out, detail = estimate([trade("SIM.MX", 203, 28000)], cfg(), prices={"SIM.MX": 201},
                           as_of="2026-11-12", snapshot_hash="DADOS SIMULADOS")
    assert out[0].est_cost_bps is None
    assert detail["trades"][0]["reasons"] == ["comissao_incluida_na_base_ausente"]
