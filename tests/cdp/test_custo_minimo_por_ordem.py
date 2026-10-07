"""DADOS SIMULADOS: contrato financeiro e caso natural, sem rede/livro oficial."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from cdp.config import load_config
from cdp.portfolio.costs import custos_fechamento

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "individual_orders/v1"


def natural_case():
    fixture = json.loads((Path(__file__).parent / "fixtures/custo_minimo_reserva.json").read_text())
    row = fixture["row"]
    frame = pd.DataFrame([{
        "notional_usd": float(row["notional_usd"]), "adtv_usd": float(row["adtv_usd"]),
        "sigma_d": float(row["sigma_daily"]), "market": row["market"],
        "currency": row["currency"], "categoria": row["category"],
        "local_fechado": False, "n_ordens": int(row["orders"]),
        "contrato_comissao": CONTRACT,
        "nocionais_ordens_usd": [float(x["notional_usd"]) for x in fixture["legs"]],
    }], index=[row["ticker"]])
    return fixture, frame


def test_natural_mexican_peak_pays_its_own_commission_floor():
    fixture, frame = natural_case()
    cfg = load_config(ROOT / "configs/cdp/fund.yaml")
    out = custos_fechamento(frame, cfg)
    # Número vem do oráculo Decimal50 independente, sem chamar consumidores CDP.
    expected = float(Decimal(fixture["row"]["commission_sum_individual_order_floors_usd"]))
    realized = out.loc[frame.index[0], "commission_bps"] * frame.iloc[0]["notional_usd"] / 1e4
    assert realized == pytest.approx(expected, abs=1e-10)


@pytest.mark.parametrize('ticker,quantity,price,legs', [
    ('SBR01.SA', 235, 25, [200, 35]),
    ('SBR01.SA', -235, 25, [-200, -35]),
    ('SBR01.SA', 35, 25, [35]),
    ('SMX06.MX', 24812, 23, [24800, 12]),
    ('SMX06.MX', -24812, 23, [-24800, -12]),
    ('SMX06.MX', 24812, 201, [24810, 2]),
    ('SMX06.MX', 3, 201, [3]),
    ('SCL02.SN', 1733, 25, [1733]),
    ('SIMUS', 235, 25, [235]),
])
def test_actual_order_books_and_individual_commission_oracle(ticker, quantity, price, legs):
    from cdp.portfolio.trades import order_legs_detail

    cfg = load_config(ROOT / 'configs/cdp/fund.yaml')
    market = ('BR' if ticker.endswith('.SA') else 'MX' if ticker.endswith('.MX')
              else 'CL' if ticker.endswith('.SN') else 'US')
    parts = order_legs_detail(ticker, quantity, price)
    # Oráculo por regra pública dos livros, independente do gerador de custos.
    assert [p[1] for p in parts] == legs
    rate = Decimal(str(cfg.costs.commission_bps[market])) / Decimal('10000')
    floor = Decimal(str(cfg.costs.min_order_cost_usd.get(
        market, max(cfg.costs.min_order_cost_usd.values()))))
    amounts = [Decimal(abs(q)) * Decimal(price) for q in legs]
    expected = sum(max(a * rate, floor) for a in amounts)
    frame = pd.DataFrame([dict(notional_usd=float(sum(amounts)), adtv_usd=1e8,
                               sigma_d=.02, market=market, currency='USD', categoria=market,
                               local_fechado=False, n_ordens=len(legs),
                               contrato_comissao=CONTRACT,
                               nocionais_ordens_usd=[float(a) for a in amounts])], index=[ticker])
    out = custos_fechamento(frame, cfg)
    got = out.loc[ticker, 'commission_bps'] * frame.loc[ticker, 'notional_usd'] / 1e4
    assert got == pytest.approx(float(expected), abs=1e-10)


@pytest.mark.parametrize('parts,minimum', [([350], None), ([20000, 350], 0),
                                         ([20000, 15000], None), ([20, 30], None)])
def test_single_order_no_floor_and_homogeneous_legs_preserve_exact_legacy(parts, minimum):
    cfg = load_config(ROOT / 'configs/cdp/fund.yaml')
    if minimum == 0:
        cfg = cfg.with_overrides({'costs': {'min_order_cost_usd': {}}})
    frame = pd.DataFrame([dict(notional_usd=sum(parts), adtv_usd=1e8, sigma_d=.02,
                               market='MX', currency='MXN', categoria='MX',
                               local_fechado=False, n_ordens=len(parts))], index=['SMX06.MX'])
    old = custos_fechamento(frame, cfg)
    current = frame.assign(contrato_comissao=CONTRACT)
    current['nocionais_ordens_usd'] = [parts]
    pd.testing.assert_frame_equal(custos_fechamento(current, cfg), old, check_exact=True)


@pytest.mark.parametrize('contract,parts,n_orders', [
    ('unknown', [20000, 350], 2), (None, [20000, 350], 2),
    (CONTRACT, None, 2), (CONTRACT, [], 2), (CONTRACT, [20000], 2),
    (CONTRACT, [20000, 0], 2), (CONTRACT, [20000, float('nan')], 2),
    (CONTRACT, [20000, float('inf')], 2), (CONTRACT, [20000, True], 2),
    (CONTRACT, [20000, 350], 1),
])
def test_new_contract_unknown_or_missing_decomposition_fails_closed(contract, parts, n_orders):
    cfg = load_config(ROOT / 'configs/cdp/fund.yaml')
    frame = pd.DataFrame([dict(notional_usd=20350, adtv_usd=1e8, sigma_d=.02,
                               market='MX', currency='MXN', categoria='MX',
                               local_fechado=False, n_ordens=n_orders,
                               contrato_comissao=contract, nocionais_ordens_usd=parts)],
                         index=['SMX06.MX'])
    with pytest.raises(ValueError):
        custos_fechamento(frame, cfg)


@pytest.mark.parametrize('value', [None, 'individual_orders/v1', {},
                                   {'commission': 'aggregate_line/v0'}])
def test_present_but_unknown_proposal_stamp_is_not_legacy(value):
    from types import SimpleNamespace

    from cdp.workflow.contrato_custos import PROPOSAL_KEY, contract

    with pytest.raises(ValueError, match='desconhecido ou malformado'):
        contract(SimpleNamespace(overrides={PROPOSAL_KEY: value}))


def test_literal_legacy_absence_stays_absent_and_new_stamp_changes_approval_hash():
    from types import SimpleNamespace

    from cdp.hashing import sha256_obj
    from cdp.workflow.contrato_custos import CURRENT, LEGACY, PROPOSAL_KEY, contract, stamp

    old = {'label': 'DADOS SIMULADOS'}
    before = json.dumps(old)
    assert contract(SimpleNamespace(overrides=old)) == LEGACY
    assert json.dumps(old) == before and PROPOSAL_KEY not in old
    current = {**old, PROPOSAL_KEY: stamp()}
    assert contract(SimpleNamespace(overrides=current)) == CURRENT
    assert sha256_obj(old) != sha256_obj(current)


def test_missing_sigma_stays_unknown_and_conservative_debit_keeps_known_order_floors():
    from types import SimpleNamespace

    from cdp.workflow.contrato_custos import PROPOSAL_KEY, stamp
    from cdp.workflow.daily import DailyRunner

    cfg = load_config(ROOT / 'configs/cdp/fund.yaml')
    # Fixture sintética: lote100+pico1, nocionalUSD1 por ação; não é dado real coletado.
    frame = pd.DataFrame([dict(notional_usd=101., adtv_usd=1e8, sigma_d=float('nan'),
                               market='MX', currency='MXN', categoria='MX',
                               local_fechado=False, n_ordens=2, contrato_comissao=CONTRACT,
                               nocionais_ordens_usd=[100., 1.])], index=['SMX06.MX'])
    facade = SimpleNamespace(cfg=cfg, custo_frame=lambda *_args, **_kwargs: frame.copy())
    proposal = SimpleNamespace(overrides={PROPOSAL_KEY: stamp()})
    raw, result, total = DailyRunner._closing_cost_calculation(facade, None, [], proposal)
    assert pd.isna(raw.loc['SMX06.MX', 'sigma_d'])
    assert pd.isna(result.loc['SMX06.MX', 'impact_bps'])
    assert total >= 2 * cfg.costs.min_order_cost_usd['MX']
    assert 'bps_conservador' in result.loc['SMX06.MX', 'flags']
