"""MOC, pedidos HARD e episódios de squeeze via APIs públicas (DADOS SIMULADOS).

O fixture usa o mesmo Runtime/ReplayStore do E1 e relógio causal. Não altera mandato,
parâmetros nem funções de produção. O único contrafactual é a data inaugural declarada.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from cdp.backtest.proveniencia import prefix_market
from cdp.backtest.replay import ReplayStore
from cdp.calendar import previous_data_session
from cdp.config import load_config
from cdp.data.intraday import save_quotes
from cdp.data.snapshot import write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file, sha256_obj
from cdp.risk.limites import episodios_de_squeeze
from cdp.workflow.risk_monitor import KILL_SWITCH_PREFIX, run_risk_monitor, write_risk_report
from cdp.workflow.runtime import KILL_SWITCH_REQUEST_EVENT, Runtime

FIRST, SECOND, AFTER = date(2024, 3, 8), date(2024, 3, 15), date(2024, 3, 18)
BRT = ZoneInfo("America/Sao_Paulo")


def seal_market(md, market_root, day):
    cutoff = datetime.combine(day, time(19, 22), tzinfo=BRT)
    view = prefix_market(md, day, cutoff, "simulado")
    write_snapshot(view, market_root / "base" / str(day))


class Clock:
    def __init__(self):
        self.at = datetime.combine(FIRST, time(11, 7), tzinfo=BRT)

    def __call__(self):
        return self.at

    def set(self, day, hour, minute):
        next_at = datetime.combine(day, time(hour, minute), tzinfo=BRT)
        assert next_at >= self.at, "O teste não retrocede seu relógio"
        self.at = next_at


@pytest.fixture
def operational(tmp_path):
    original = load_config()
    cfg = original.model_copy(
        update={"fund": original.fund.model_copy(update={"inception_date": FIRST})}
    )
    before, effective = original.model_dump(mode="json"), cfg.model_dump(mode="json")
    before["fund"].pop("inception_date")
    effective["fund"].pop("inception_date")
    assert before == effective
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=AFTER)
    rng = np.random.default_rng(730)
    benchmarks = md.benchmarks.copy()
    for factor in cfg.risk_model.macro_factors:
        benchmarks[factor] = 80 * np.cumprod(1 + rng.normal(0, 0.02, len(benchmarks)))
    md = replace(md, benchmarks=benchmarks)
    clock = Clock()
    market = tmp_path / "market"
    for d in (previous_data_session(FIRST), FIRST):
        seal_market(md, market, d)
    rt = Runtime(
        cfg,
        tmp_path / "book",
        market,
        tmp_path / "reports",
        clock=clock,
        store_override=ReplayStore(market, cfg=cfg, now=clock),
        teses_root=None,
        expected_mind="codex",
    )
    rt.weekly_prepare(FIRST, mind="codex", live=False)
    clock.set(FIRST, 13, 7)
    decided = rt.weekly_decide(FIRST, mind="codex")
    assert decided["n_short"] > 0
    clock.set(FIRST, 19, 22)
    assert rt.daily_close(FIRST, live=False, mind="codex")["efetivacao"]
    assert rt.track().last().positions
    return rt, clock, md


def close_remaining(rt, clock, md, *, through=date(2024, 3, 14)):
    for ts in md.close.index:
        d = ts.date()
        if FIRST < d <= through:
            seal_market(md, rt.market_root, d)
            clock.set(d, 19, 22)
            assert rt.daily_close(d, live=False, mind="codex")["status"] == "registrado"


def prepare_second(rt, clock, md):
    seal_market(md, rt.market_root, SECOND)
    clock.set(SECOND, 11, 7)
    rt.weekly_prepare(SECOND, mind="codex", live=False)
    clock.set(SECOND, 13, 7)
    decision = rt.weekly_decide(SECOND, mind="codex")
    assert rt.book.load_decision(SECOND).approval_hash == decision["decisao"]
    return decision


def test_hard_request_after_decision_lapses_moc_and_never_fills_next_session(operational):
    rt, clock, md = operational
    close_remaining(rt, clock, md)
    old = rt.track().last()
    old_shares = {(p.issuer_id, p.ticker): p.shares for p in old.positions}
    prepare_second(rt, clock, md)
    decision_hash = rt.book.load_decision(SECOND).approval_hash
    assert rt.book.load_booked(SECOND) is None and not rt.kill_switch_active()
    # Todas as cotações são do mesmo momento, com cobertura completa de linhas/moedas.
    # Longs caem 90%; shorts dobram: o HARD é derivado de preços, não um retorno fabricado.
    clock.set(SECOND, 16, 3)
    rows = [
        {
            "kind": "line",
            "symbol": p.ticker,
            "price": p.price_local * (0.1 if p.shares > 0 else 2.0),
            "time": clock().isoformat(),
        }
        for p in old.positions
    ]
    currencies = {
        p.currency: p.price_usd / p.price_local for p in old.positions if p.currency != "USD"
    }
    rows += [
        {"kind": "fx", "symbol": c, "price": fx, "time": clock().isoformat()}
        for c, fx in currencies.items()
    ]
    quotes = pd.DataFrame(rows)
    quote_path = rt.book_root.parent / "quotes_adversas.parquet"
    quote_sha = save_quotes(quotes, quote_path, clock())
    report = run_risk_monitor(
        rt, as_of=SECOND, live=True, fetch_quotes=lambda *_: quotes.copy(), now=clock()
    )
    assert report["intradiario"]["cobertura_gross"] == pytest.approx(1.0)
    assert any(g["nivel"] == "HARD" for g in report["gatilhos"])
    reasons = [
        a[len(KILL_SWITCH_PREFIX) :]
        for a in report["acoes_recomendadas"]
        if a.startswith(KILL_SWITCH_PREFIX)
    ]
    assert reasons
    write_risk_report(report, rt.reports_root / "risk", rt.cfg)
    requested = [rt.request_kill_switch(r, by="sistema (teste causal)") for r in reasons]
    assert all(sha256_file(Path(r["arquivo"])) == r["sha256"] for r in requested)
    assert not rt.kill_switch_active()  # o monitor/arquivo mesclável não grava o switch sozinho
    clock.set(SECOND, 19, 22)
    result = rt.daily_close(SECOND, live=False, mind="codex")
    assert rt.kill_switch_active() and rt.kill_switch_requests() == []
    assert result["efetivacao_recusada"]["decisao_caducada"] is True
    assert result["efetivacao"] is None and rt.book.load_booked(SECOND) is None
    rec = rt.track().get(SECOND)
    assert rec.live_book_week == FIRST and rec.approval_hash == old.approval_hash
    assert {(p.issuer_id, p.ticker): p.shares for p in rec.positions} == old_shares
    assert rec.pnl_components["costs"] == 0.0
    assert rt.book.load_decision(SECOND).approval_hash == decision_hash
    handled = {
        e.payload_hash for e in rt.book.audit.events() if e.event_type == KILL_SWITCH_REQUEST_EVENT
    }
    assert all(sha256_obj({"pedido_sha256": r["sha256"]}) in handled for r in requested)
    before = {str(p): sha256_file(p) for p in rt.book_root.rglob("*") if p.is_file()}
    assert rt.daily_close(SECOND, live=False, mind="codex")["status"] == "já registrado"
    assert before == {str(p): sha256_file(p) for p in rt.book_root.rglob("*") if p.is_file()}
    # Operador fictício somente no livro temporário: mesmo após OFF, a decisão caducou.
    clock.set(AFTER, 11, 7)
    rt.set_kill_switch(False, "revisão humana simulada no teste isolado", by="humano simulado")
    seal_market(md, rt.market_root, AFTER)
    clock.set(AFTER, 19, 22)
    next_result = rt.daily_close(AFTER, live=False, mind="codex")
    nxt = rt.track().get(AFTER)
    assert next_result["efetivacao"] is None and rt.book.load_booked(SECOND) is None
    assert nxt.live_book_week == FIRST and nxt.pnl_components["costs"] == 0.0
    assert {(p.issuer_id, p.ticker): p.shares for p in nxt.positions} == old_shares
    assert sha256_file(quote_path) == quote_sha
    ok, errors = rt.verify_all()
    assert ok, errors


def test_actual_closed_squeeze_cuts_once_and_keeps_long_veto(operational):
    rt, clock, md = operational
    entry = rt.track().get(FIRST)
    target = min(
        (p for p in entry.positions if p.shares < -4 and p.currency == "USD"),
        key=lambda p: abs(p.weight),
    )
    assert rt.cfg.squeeze.stop_scope == "name"
    # Um único short cruza o limite vigente; as demais linhas e parâmetros são preservados.
    close, adjusted = md.close.copy(), md.adj_close.copy()
    future = close.index.date > FIRST
    px = target.price_local * (1 + rt.cfg.squeeze.stop_short_position_loss + 0.05)
    close.loc[future, target.ticker] = px
    ratio = float(md.adj_close.loc[str(FIRST), target.ticker]) / target.price_local
    adjusted.loc[future, target.ticker] = px * ratio
    shocked = replace(md, close=close, adj_close=adjusted)
    close_remaining(rt, clock, shocked)
    first_stop = date(2024, 3, 11)
    episodes = [
        e
        for e in episodios_de_squeeze(rt.track().records(), rt.cfg)
        if e.emissor == target.issuer_id
    ]
    assert len(episodes) == 1 and episodes[0].data_stop == first_stop
    assert episodes[0].corte_pendente
    shares_at_stop = episodes[0].acoes_no_stop
    bound = rt.squeeze_stops(SECOND)[target.issuer_id]
    assert bound["veto_compra"] and bound["fracao_maxima_short"] == pytest.approx(0.5)
    prepare_second(rt, clock, shocked)
    proposal = rt.book.load_proposal(SECOND)
    assert not any(p.weight > 0 and p.issuer_id == target.issuer_id for p in proposal.positions)
    clock.set(SECOND, 19, 22)
    assert rt.daily_close(SECOND, live=False, mind="codex")["efetivacao"]
    actual = sum(
        abs(p.shares)
        for p in rt.track().get(SECOND).positions
        if p.issuer_id == target.issuer_id and p.shares < 0
    )
    assert actual <= shares_at_stop / 2 + 1e-9
    episode_after = [
        e
        for e in episodios_de_squeeze(rt.track().records(), rt.cfg)
        if e.emissor == target.issuer_id
    ]
    assert len(episode_after) == 1 and not episode_after[0].corte_pendente
    # No próximo preparo o mesmo episódio não pede outra metade, mesmo ainda em stop.
    next_bound = rt.squeeze_stops(date(2024, 3, 22))[target.issuer_id]
    assert next_bound["veto_compra"] and next_bound["fracao_maxima_short"] is None
    before = {str(p): sha256_file(p) for p in rt.book_root.rglob("*") if p.is_file()}
    assert rt.daily_close(SECOND, live=False, mind="codex")["status"] == "já registrado"
    assert before == {str(p): sha256_file(p) for p in rt.book_root.rglob("*") if p.is_file()}
    ok, errors = rt.verify_all()
    assert ok, errors
