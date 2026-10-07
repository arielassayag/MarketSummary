"""Feriado B3 e early-close NY por fontes físicas E1 (DADOS SIMULADOS).

Escopo: roteamento/congelamento, capacidade e prazo pelos consumidores públicos.
Não é replay integral de semanas nem validação de mérito/PIT real. O mandato
atual só recebe a data inaugural contrafactual; séries/ordens são fixtures.
"""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from cdp.backtest.proveniencia import prefix_market
from cdp.backtest.replay import ReplayIntegrityError, ReplayStore
from cdp.config import load_config
from cdp.contracts import BookedPosition, BookEntry
from cdp.data.snapshot import write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file
from cdp.portfolio.execucao import (
    OrdemLinha,
    emissores_congelados,
    janela_execucao,
    preenchimentos_esperados,
    rotear_linhas,
    tabela_capacidade,
)
from cdp.workflow.runtime import RecusaEstruturada, Runtime

BRT, NY = ZoneInfo("America/Sao_Paulo"), ZoneInfo("America/New_York")
HOLIDAY, EARLY = date(2026, 11, 20), date(2026, 11, 27)


class Clock:
    def __init__(self, day, at=time(19, 22)):
        self.at = datetime.combine(day, at, tzinfo=BRT)

    def __call__(self):
        return self.at


def inventory(root):
    return {str(p.relative_to(root)): sha256_file(p) for p in root.rglob("*") if p.is_file()}


def br_pairs(md):
    lines, pairs = md.universe.lines, []
    for loc in lines.index:
        if not loc.endswith(".SA"):
            continue
        iid = lines.at[loc, "issuer_id"]
        adrs = lines[(lines["issuer_id"] == iid) & (lines["line_type"] == "ADR")]
        if not adrs.empty:
            pairs.append((str(iid), str(loc), str(adrs.index[0])))
    assert len(pairs) >= 2
    return pairs[:2]


@pytest.fixture(scope="module")
def episode(tmp_path_factory):
    root = tmp_path_factory.mktemp("calendar-physical-simulated")
    original = load_config()
    cfg = original.model_copy(update={"fund": original.fund.model_copy(
        update={"inception_date": date(2026, 11, 13)})})
    before, after = original.model_dump(mode="json"), cfg.model_dump(mode="json")
    before["fund"].pop("inception_date")
    after["fund"].pop("inception_date")
    assert before == after
    md = make_synthetic_market(seed=79, start=date(2026, 1, 2), as_of=EARLY)
    pairs = br_pairs(md)
    frames = {k: getattr(md, k).copy() for k in ("close", "adj_close", "volume", "fx")}
    # Bolsa local sem pregão: ausência permanece NaN em todos os três campos.
    locals_br = [t for t in md.universe.lines.index if t.endswith(".SA")]
    for name in ("close", "adj_close", "volume"):
        frames[name].loc[pd.Timestamp(HOLIDAY), locals_br] = np.nan
    for d in (HOLIDAY, EARLY):
        for _, loc, adr in pairs:
            frames["close"].at[pd.Timestamp(d), adr] = 20.0
            frames["adj_close"].at[pd.Timestamp(d), adr] = 20.0
            frames["volume"].at[pd.Timestamp(d), adr] = 10_000.0
            if d == EARLY:
                frames["close"].at[pd.Timestamp(d), loc] = 100.0
                frames["adj_close"].at[pd.Timestamp(d), loc] = 100.0
                frames["volume"].at[pd.Timestamp(d), loc] = 10_000.0
        frames["fx"].at[pd.Timestamp(d), "BRL"] = 0.20
    md = replace(md, **frames)
    market = root / "market"
    for d in (date(2026, 11, 19), HOLIDAY, date(2026, 11, 26), EARLY):
        view = prefix_market(md, d, datetime.combine(d, time(19, 22), tzinfo=BRT), "simulado")
        write_snapshot(view, market / "base" / str(d))
    return root, cfg, pairs


def physical(episode, day, at=time(19, 22)):
    root, cfg, pairs = episode
    store = ReplayStore(root / "market", cfg=cfg, now=Clock(day, at))
    return store, cfg, pairs


def test_holiday_keeps_held_local_and_routes_new_issuer_adr_with_realized_fill(episode):
    root, cfg, pairs = episode
    store, _, _ = physical(episode, HOLIDAY)
    before = inventory(root)
    md = store.load(as_of=HOLIDAY)
    held_iid, held_loc, held_adr = pairs[0]
    new_iid, new_loc, new_adr = pairs[1]
    j = janela_execucao(HOLIDAY, cfg)
    assert not j.abertos["BVMF"] and j.abertos["XNYS"]
    initial = pd.Timestamp(date(2026, 11, 13))
    held_notional = 1000 * float(md.close.at[initial, held_loc]) * float(md.fx.at[initial, "BRL"])
    held = BookEntry(week=date(2026, 11, 13), proposal_id="DADOS SIMULADOS-local",
        approval_hash="a" * 64, booked_at=datetime(2026, 11, 13, 19, tzinfo=BRT),
        nav_usd=cfg.fund.inception_nav_usd,
        positions=[BookedPosition(issuer_id=held_iid, ticker=held_loc,
            weight=held_notional / cfg.fund.inception_nav_usd,
            notional_usd=held_notional, shares=1000, currency="BRL")],
        pricing_note="DADOS SIMULADOS: fixture de posição anterior, sem decisão de investimento")
    sides = pd.DataFrame({"long_ticker": [held_loc, new_loc],
        "long_line_type": ["LOCAL", "LOCAL"], "long_currency": ["BRL", "BRL"],
        "short_ticker": [held_adr, new_adr]}, index=[held_iid, new_iid])
    routed = rotear_linhas(sides, md.universe.lines, j, cfg, held)
    assert routed.at[held_iid, "long_ticker"] == held_loc
    assert routed.at[new_iid, "long_ticker"] == new_adr
    frozen = emissores_congelados(routed, held, j, cfg)
    assert set(frozen) == {held_iid}
    for name in ("close", "adj_close", "volume"):
        assert math.isnan(getattr(md, name).at[pd.Timestamp(HOLIDAY), held_loc])
    fills = preenchimentos_esperados([
        OrdemLinha(held_iid, held_loc, 1000, 0, None, None),
        OrdemLinha(held_iid, held_adr, 0, 1000, 20.0, 1.0),
        OrdemLinha(new_iid, new_adr, 0, 2000, 20.0, 1.0)], md, j, cfg,
        nav_pre=cfg.fund.inception_nav_usd,
        decidido_em=datetime.combine(HOLIDAY, time(14), tzinfo=BRT))
    assert fills[0].situacao == fills[1].situacao == "congelado"
    assert fills[0].executadas == fills[1].executadas == 0
    assert fills[0].detidas + fills[0].executadas == held.positions[0].shares
    cap = cfg.execution.capacity
    fraction = cap.auction_participation * cap.auction_share["ADR"] + \
        cap.preclose_participation * cap.preclose_volume_share
    expected = math.floor(10_000 * fraction)
    assert 0 < expected < 2000
    assert fills[2].situacao == "parcial" and fills[2].executadas == expected
    assert fills[2].capacidade_usd == pytest.approx(expected * 20.0)
    assert inventory(root) == before


@pytest.mark.parametrize("side,side_multiplier", [("long", 1.0), ("short", 0.75)])
def test_early_close_capacity_and_integer_fills_reduce_ny_only(episode, side, side_multiplier):
    root, cfg, pairs = episode
    store, _, _ = physical(episode, EARLY)
    before = inventory(root)
    md = store.load(as_of=EARLY)
    iid, loc, adr = pairs[1]
    j = janela_execucao(EARLY, cfg)
    assert j.abertos["BVMF"] and j.abertos["XNYS"]
    # Oráculo temporal independente: 13h ET no inverno = 15h BRT; buffer45 →14h15.
    closing = datetime.combine(EARLY, time(13), tzinfo=NY).astimezone(BRT)
    deadline = closing - timedelta(minutes=cfg.execution.decision_buffer_minutes)
    assert deadline.time() == time(14, 15) and j.prazo_decisao == deadline
    assert j.fechamentos["XNYS"].astimezone(BRT) == closing
    table = tabela_capacidade(md.universe.lines.reindex([loc, adr]), md, j, cfg,
                              lado=side, volume="realizado")
    cap = cfg.execution.capacity
    if side == "short":
        assert cap.short_multiplier == side_multiplier
    expected = {}
    for ticker, category, early_mult, fx, price in (
        (loc, "BR", 1.0, 0.20, 100.0),
        (adr, "ADR", cap.early_close_multiplier, 1.0, 20.0)):
        fraction = cap.auction_participation * cap.auction_share[category] + \
            cap.preclose_participation * cap.preclose_volume_share
        expected[ticker] = 10_000 * price * fx * fraction * early_mult * side_multiplier
        assert table.at[ticker, "volume_ref_usd"] == pytest.approx(10_000 * price * fx)
        assert table.at[ticker, "capacidade_usd"] == pytest.approx(expected[ticker])
        assert table.at[ticker, "multiplicador"] == early_mult * side_multiplier
    sign = 1 if side == "long" else -1
    fills = preenchimentos_esperados([
        OrdemLinha(iid, loc, 0, sign * 2000, 100.0, 0.20),
        OrdemLinha(iid, adr, 0, sign * 2000, 20.0, 1.0)], md, j, cfg,
        nav_pre=cfg.fund.inception_nav_usd, decidido_em=deadline)
    for fill in fills:
        expected_shares = sign * math.floor(expected[fill.ticker] / 20.0 + 1e-9)
        assert fill.situacao == "parcial" and fill.executadas == expected_shares
        assert abs(fill.executadas) * 20.0 <= expected[fill.ticker]
    assert inventory(root) == before


def test_early_close_late_decision_is_refused_before_reading_or_writing_inputs(episode, tmp_path):
    _, cfg, _ = episode
    late = Clock(EARLY, time(14, 16))
    store = ReplayStore(tmp_path / "unavailable-market", cfg=cfg, now=late)
    rt = Runtime(cfg, tmp_path / "book", tmp_path / "unavailable-market",
                 tmp_path / "reports", clock=late, store_override=store,
                 teses_root=None, expected_mind="codex")
    book = rt.book  # criação de diretório antecede o inventário; nenhum dado/decisão é criado
    before = inventory(tmp_path)
    with pytest.raises(RecusaEstruturada) as exc:
        rt.weekly_decide(EARLY, mind="codex")
    assert exc.value.status == "prazo_vencido"
    assert "14:15" in str(exc.value)
    assert book.load_decision(EARLY) is None and book.load_booked(EARLY) is None
    assert inventory(tmp_path) == before


def test_physical_future_base_never_supplies_holiday_before_its_close(episode):
    root, _, pairs = episode
    store, _, _ = physical(episode, HOLIDAY, time(14))
    before = inventory(root)
    md = store.load()
    assert md.as_of == date(2026, 11, 19)
    assert md.close.index.max().date() == date(2026, 11, 19)
    # Os arquivos20/27 existem; existência física não torna o fechamento conhecido.
    assert len(store.bases()) == 4
    for d in (HOLIDAY, EARLY):
        with pytest.raises(ReplayIntegrityError, match="posterior ao corte"):
            store.load(as_of=d)
    assert md.close.at[pd.Timestamp(md.as_of), pairs[0][1]] > 0
    assert inventory(root) == before
