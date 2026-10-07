"""Comissão estimada das ordens planejadas, após arredondar; não é débito futuro.

O nocional vem de Trade, e o preço local da fonte atual apenas determina o livro/lote.
Spread, impacto e FX já integram a estimativa base, que inclui comissão variável uma vez.
Ausência de quantidade/preço/nocional/base é registrada e não recebe ordem ou custo fictício.
"""
from __future__ import annotations

import math

import pandas as pd

from ..contracts import TradeAction
from ..portfolio.costs import minimo_por_ordem_usd
from ..portfolio.trades import order_legs_detail
from ..universe import listing_market

PLANNED_KEY = "planned_order_costs"


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def included_commissions(target, current, model):
    """Comissão incluída na mesma estimativa por emissor, sem mudar suas curvas/pesos.

O custo-base soma as curvas long/short e divide por |alvo−atual|. Não presumir que sua
comissão seja a tabela do ticker negociado: liquidações/trocas podem usar outra curva.
Sem componentes explícitos ou curvas por perna, o componente permanece desconhecido.
"""
    if (model.components is None or model.linear_rate_long is None or model.linear_rate_short is None
            or model.impact_k_long is None or model.impact_k_short is None):
        return {}
    result = {}
    for issuer, value in target.items():
        old = float(current.get(issuer, 0.0)) if current is not None else 0.0
        new = float(value)
        amount = abs(new - old)
        if amount == 0 or issuer not in model.components.index:
            continue
        changes = {"long": abs(max(new, 0.0) - max(old, 0.0)),
                   "short": abs(max(-new, 0.0) - max(-old, 0.0))}
        parts = []
        for leg, weight in changes.items():
            if not weight:
                continue
            try:
                column = leg
                if leg == "short" and pd.isna(model.components.at[issuer, ("short", "ticker")]):
                    column = "long"  # Mesma cópia explícita de curva do build_cost_model.
                rate = _number(model.components.at[issuer, (column, "commission_bps")])
            except KeyError:
                rate = None
            if rate is None or rate < 0:
                parts = []
                break
            parts.append({"leg": leg, "component_curve": column,
                          "weight_change_abs": weight, "commission_bps": rate})
        if parts:
            rates = {p["commission_bps"] for p in parts}
            rate = next(iter(rates)) if len(rates) == 1 else sum(
                p["weight_change_abs"] * p["commission_bps"] for p in parts) / amount
            result[issuer] = {"bps": rate, "components": parts}
    return result


def estimate(trades, cfg, *, prices, as_of, snapshot_hash, base_commissions=None):
    """Ajusta só a comissão; detalhamento completo é incorporado antes do hash da proposta.

Também liquidações recebem preço atual explícito por ticker; preços da posição detida ou
da posição-alvo não substituem essa fonte. Não altera Trade.shares/notional nem solver.
"""
    worst = max(cfg.costs.commission_bps.values())
    rows, out = [], []
    for index, trade in enumerate(trades):
        market = listing_market(trade.ticker)
        quantity = _number(trade.shares)
        notional = _number(trade.notional_usd)
        price = _number(prices.get(trade.ticker))
        base = _number(trade.est_cost_bps)
        variable_bps = float(cfg.costs.commission_bps.get(market, worst))
        minimum = minimo_por_ordem_usd(market, cfg)
        component = (base_commissions or {}).get(trade.issuer_id)
        included = _number(component.get("bps")) if isinstance(component, dict) else None
        reason = []
        if quantity is None or int(quantity) != quantity or quantity < 0:
            reason.append("quantidade_planejada_ausente_ou_invalida")
        if notional is None or notional < 0:
            reason.append("nocional_planejado_ausente_ou_invalido")
        if price is None or price <= 0:
            reason.append("preco_local_atual_ausente_ou_invalido")
        if base is None:
            reason.append("estimativa_base_ausente")
        if included is None or included < 0:
            reason.append("comissao_incluida_na_base_ausente")
        elif base is not None and base < included:
            reason.append("comissao_incluida_excede_estimativa_base")
        row = {"trade_index": index, "issuer_id": trade.issuer_id, "ticker": trade.ticker,
               "action": str(trade.action), "shares": quantity, "notional_usd": notional,
               "price_local_current": price, "market": market, "base_est_cost_bps": base,
               "variable_commission_bps": variable_bps, "minimum_per_order_usd": minimum,
               "included_commission_bps": included, "base_commission_source": component,
               "orders": None, "commission_usd": None, "commission_bps": None,
               "added_commission_bps": None, "est_cost_bps": None}
        if quantity == 0 and notional is not None and notional > 0:
            reason.append("quantidade_zero_com_nocional_positivo")
        if quantity is not None and quantity > 0 and notional == 0:
            reason.append("quantidade_positiva_sem_nocional")
        if reason:
            row.update(state="indisponivel", reasons=reason)
            out.append(trade.model_copy(update={"est_cost_bps": None}))
        elif quantity == 0:
            # Zero observado: nenhuma ordem; bps não definido para nocional zero.
            row.update(state="sem_ordem", reasons=[], orders=[], commission_usd=0.0)
            out.append(trade.model_copy(update={"est_cost_bps": None}))
        else:
            sign = 1 if trade.action in (TradeAction.BUY, TradeAction.COVER) else -1
            legs = order_legs_detail(trade.ticker, sign * int(quantity), price)
            orders = []
            for ticker, shares, book in legs:
                amount = abs(shares) * notional / quantity
                variable = amount * variable_bps / 1e4
                orders.append({"ticker": ticker, "shares": shares, "book": book,
                               "notional_usd": amount, "variable_commission_usd": variable,
                               "commission_usd": max(variable, minimum)})
            commission = sum(order["commission_usd"] for order in orders)
            commission_bps = commission / notional * 1e4
            if all(order["variable_commission_usd"] >= minimum for order in orders):
                # Sem mínimo vinculante, a comissão base já incluída permanece literal.
                commission = notional * variable_bps / 1e4
                commission_bps = variable_bps
            elif all(order["variable_commission_usd"] <= minimum for order in orders):
                commission = len(orders) * minimum
                commission_bps = max(variable_bps, commission / notional * 1e4)
            additional = commission_bps - included
            row.update(state="estimado", reasons=[], orders=orders,
                       commission_usd=commission, commission_bps=commission_bps,
                       added_commission_bps=additional, est_cost_bps=base + additional)
            out.append(trade.model_copy(update={"est_cost_bps": base + additional})
                       if additional != 0 else trade)
        rows.append(row)
    return out, {"schema": "cdp.planned_order_cost_estimate/v1",
                 "basis": "Trade.shares/notional_usd; preco_local_da_fonte_atual",
                 "source": {"market_as_of": str(as_of), "snapshot_hash": snapshot_hash},
                 "commission_base_already_included": True,
                 "actual_fills_or_future_debit_certified": False, "trades": rows}
