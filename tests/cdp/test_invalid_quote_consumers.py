"""Oráculos de cotações inválidas e preservação dos brutos (DADOS SIMULADOS)."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cdp.analytics.panel import _line_usd_returns, build_asset_panel
from cdp.config import FundConfig
from cdp.contracts import DailyPosition, DailyRecord, DailyRisk, Side
from cdp.data.synthetic import make_synthetic_market
from cdp.risk.gatilhos import price_jumps
from cdp.workflow.daily import DailyContext, DailyRunner, _last_valid

IDX = pd.to_datetime(["2024-03-14", "2024-03-15", "2024-03-18"])
BAD = [0.0, np.inf, -np.inf, np.nan, -10.0]


@pytest.mark.parametrize("invalid", BAD)
@pytest.mark.parametrize("component", ["price", "fx"])
def test_retorno_ausente_nao_vira_zero_e_catchup_so_no_proximo_preco(invalid, component):
    adj = pd.Series([100.0, invalid if component == "price" else 100.0, 110.0], index=IDX)
    fx = pd.Series([1.0, invalid if component == "fx" else 1.0, 1.0], index=IDX)
    original_adj, original_fx = adj.copy(), fx.copy()
    ret = _line_usd_returns(adj, fx).reindex(IDX)
    assert pd.isna(ret.loc[IDX[1]])
    assert ret.loc[IDX[2]] == pytest.approx(110.0 / 100.0 - 1.0)
    assert _line_usd_returns(adj.loc[:IDX[1]], fx.loc[:IDX[1]]).empty
    pd.testing.assert_series_equal(adj, original_adj)
    pd.testing.assert_series_equal(fx, original_fx)


def test_retorno_negativo_legitimo_e_preco_nao_positivo_sao_dominios_distintos():
    ret = _line_usd_returns(pd.Series([100.0, 90.0], index=IDX[:2]), pd.Series(1.0, index=IDX[:2]))
    assert ret.iloc[0] == pytest.approx(-0.1)
    assert ret.iloc[0] < 0


@pytest.mark.parametrize("invalid", BAD + ["corrompido"])
def test_ultimo_preco_valido_e_finito_positivo_sem_consultar_futuro(invalid):
    values = pd.Series([100.0, invalid, 110.0], index=IDX)
    price, at = _last_valid(values, IDX[1])
    assert price == 100.0 and at == IDX[0]
    missing = pd.Series([invalid], index=IDX[1:2])
    assert _last_valid(missing, IDX[1]) == (None, None)


class Store:
    def __init__(self, md):
        self.md = md

    def load(self, as_of):
        return self.md.truncate(as_of)


def record(day, pos):
    return DailyRecord(date=day, fund_name="CDP teste privado", track_record_type="paper",
        nav_start_usd=1000.0, nav_end_usd=1000.0, pnl_usd=0.0, ret=0.0,
        pnl_components={}, positions=[pos], risk=DailyRisk(gross=.2, net=-.2, long_exposure=0.0,
            short_exposure=-.2, n_long=0, n_short=1), is_synthetic=True,
        data_notice="DADOS SIMULADOS", prev_record_hash="0" * 64)


@pytest.mark.parametrize("invalid", BAD)
def test_marcacao_preserva_acoes_valor_alerta_e_catchup_sem_principal_fabricado(tmp_path, invalid):
    cfg = FundConfig()
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=IDX[-1].date())
    ticker = "SBR04ADR"
    close, adj = md.close.copy(), md.adj_close.copy()
    close.loc[IDX, ticker] = [100.0, invalid, 110.0]
    adj.loc[IDX, ticker] = [100.0, invalid, 110.0]
    md = replace(md, close=close, adj_close=adj)
    raw_close, raw_adj = close.copy(), adj.copy()
    pos = DailyPosition(issuer_id="SIM004", ticker=ticker, currency="USD", side=Side.SHORT,
        shares=-2.0, price_local=100.0, price_usd=100.0, market_value_usd=-200.0,
        weight=-.2, day_pnl_usd=0.0, day_return_usd=0.0, repriced=True)
    prior = record(IDX[0].date(), pos)
    runner = DailyRunner.from_root(cfg, Store(md), tmp_path / "book", with_shadow=False)
    day = md.truncate(IDX[1].date())
    ctx = DailyContext(day.as_of, day, build_asset_panel(day, cfg), None, None, prior)
    held = runner._mark(ctx, prior, None)
    line = held.lines[0]
    assert line.shares == -2 and line.mv_end == -200 and line.pnl == 0
    assert line.ret is None and line.repriced is False
    assert line.price_local == line.price_usd == 100
    assert any("posição não reprecificada" in text for text in held.alerts)
    frozen_pos = pos.model_copy(update={"repriced": False, "day_return_usd": None})
    frozen = record(IDX[1].date(), frozen_pos)
    next_ctx = DailyContext(md.as_of, md, build_asset_panel(md, cfg), None, None, frozen)
    caught_up = runner._mark(next_ctx, frozen, None).lines[0]
    assert caught_up.shares == -2 and caught_up.repriced is True
    assert caught_up.ret == pytest.approx(110.0 / 100.0 - 1.0)
    assert caught_up.pnl == pytest.approx(-200.0 * (110.0 / 100.0 - 1.0))
    assert caught_up.mv_end == pytest.approx(-220.0)
    assert caught_up.price_local == caught_up.price_usd == 110.0
    assert price_jumps(frozen, day) == []
    assert price_jumps(record(IDX[2].date(), pos), md) == []
    pd.testing.assert_frame_equal(md.close, raw_close)
    pd.testing.assert_frame_equal(md.adj_close, raw_adj)


@pytest.mark.parametrize("component", ["close", "adj_close"])
@pytest.mark.parametrize("invalid", BAD)
def test_monitor_recusa_preco_invalido_em_qualquer_lado_da_ponte(component, invalid):
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=IDX[1].date())
    ticker = "SBR04ADR"
    frame = getattr(md, component).copy()
    frame.loc[IDX[1], ticker] = invalid
    changed = replace(md, **{component: frame})
    pos = DailyPosition(issuer_id="SIM004", ticker=ticker, currency="USD", side=Side.SHORT,
        shares=-2.0, price_local=100.0, price_usd=100.0, market_value_usd=-200.0,
        weight=-.2, day_pnl_usd=0.0, day_return_usd=None, repriced=False)
    assert price_jumps(record(IDX[1].date(), pos), changed) == []


@pytest.mark.parametrize("component", ["close", "adj_close"])
@pytest.mark.parametrize("invalid", BAD)
def test_monitor_compara_mesmas_datas_apos_ausencia_sem_evento_fabricado(component, invalid):
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=IDX[2].date())
    ticker = "SBR04ADR"
    close, adj = md.close.copy(), md.adj_close.copy()
    close.loc[IDX, ticker] = [100.0, 105.0, 110.0]
    adj.loc[IDX, ticker] = [100.0, 105.0, 110.0]
    (close if component == "close" else adj).loc[IDX[1], ticker] = invalid
    changed = replace(md, close=close, adj_close=adj)
    raw_close, raw_adj = close.copy(), adj.copy()
    pos = DailyPosition(issuer_id="SIM004", ticker=ticker, currency="USD", side=Side.SHORT,
        shares=-2.0, price_local=110.0, price_usd=110.0, market_value_usd=-220.0,
        weight=-.2, day_pnl_usd=-20.0, day_return_usd=.1, repriced=True)
    assert price_jumps(record(IDX[2].date(), pos), changed) == []
    pd.testing.assert_frame_equal(changed.close, raw_close)
    pd.testing.assert_frame_equal(changed.adj_close, raw_adj)


def test_monitor_sem_duas_datas_comuns_nao_cria_ponte_nem_usa_futuro():
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=IDX[2].date())
    ticker = "SBR04ADR"
    close, adj = md.close.copy(), md.adj_close.copy()
    close[ticker] = np.nan
    adj[ticker] = np.nan
    close.loc[IDX, ticker] = [100.0, 105.0, 110.0]
    adj.loc[IDX, ticker] = [np.nan, 105.0, 110.0]
    changed = replace(md, close=close, adj_close=adj)
    pos = DailyPosition(issuer_id="SIM004", ticker=ticker, currency="USD", side=Side.SHORT,
        shares=-2.0, price_local=105.0, price_usd=105.0, market_value_usd=-210.0,
        weight=-.2, day_pnl_usd=0.0, day_return_usd=None, repriced=False)
    assert price_jumps(record(IDX[1].date(), pos), changed) == []


@pytest.mark.parametrize("component", ["price", "fx"])
@pytest.mark.parametrize("invalid", BAD)
def test_painel_inteiro_cotacao_invalida_equivale_nan_sem_mudar_brutos(component, invalid):
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=IDX[1].date())
    close, adj, fx = md.close.copy(), md.adj_close.copy(), md.fx.copy()
    missing_close, missing_adj, missing_fx = close.copy(), adj.copy(), fx.copy()
    if component == "price":
        close.loc[IDX[1], "SBR04ADR"] = invalid
        adj.loc[IDX[1], "SBR04ADR"] = invalid
        missing_close.loc[IDX[1], "SBR04ADR"] = np.nan
        missing_adj.loc[IDX[1], "SBR04ADR"] = np.nan
    else:
        fx.loc[IDX[1], "BRL"] = invalid
        missing_fx.loc[IDX[1], "BRL"] = np.nan
    changed = replace(md, close=close, adj_close=adj, fx=fx)
    missing = replace(md, close=missing_close, adj_close=missing_adj, fx=missing_fx)
    expected = build_asset_panel(missing, FundConfig())
    observed = build_asset_panel(changed, FundConfig())
    for key in ["assets", "returns", "price_usd", "traded_value_usd", "line_returns", "lines"]:
        pd.testing.assert_frame_equal(getattr(observed, key), getattr(expected, key), check_exact=True)
    pd.testing.assert_frame_equal(changed.close, close)
    pd.testing.assert_frame_equal(changed.adj_close, adj)
    pd.testing.assert_frame_equal(changed.fx, fx)


def test_produto_de_preco_cambio_overflow_fica_ausente_sem_capacidade_fabricada():
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=IDX[1].date())
    close, adj, fx = md.close.copy(), md.adj_close.copy(), md.fx.copy()
    ticker = "SBR04.SA"
    close.loc[IDX[1], ticker] = 1e308
    adj.loc[IDX[1], ticker] = 1e308
    fx.loc[IDX[1], "BRL"] = 1e308
    changed = replace(md, close=close, adj_close=adj, fx=fx)
    panel = build_asset_panel(changed, FundConfig())
    assert pd.isna(panel.price_usd.loc[IDX[1], "SIM004"])
    assert pd.isna(panel.line_returns.loc[IDX[1], ticker])
    assert pd.isna(panel.lines.loc[ticker, "last_price_usd"])
    assert changed.close.loc[IDX[1], ticker] == 1e308
    assert changed.fx.loc[IDX[1], "BRL"] == 1e308
