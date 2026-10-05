"""Testes do track record diário do CDP: execução MOC, NAV, atribuição, alertas e cadeia de hash.

Mercado sintético (offline, DADOS SIMULADOS) servido por uma fonte falsa sem look-ahead e um livro
montado à mão com carteiras aprovadas (humanas e autônomas).
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from latam_ls.analytics.panel import build_asset_panel
from latam_ls.analytics.shortability import short_availability
from latam_ls.config import FundConfig
from latam_ls.contracts import (
    DailyPosition,
    DailyRecord,
    DailyRisk,
    DecisionType,
    LineType,
    OptimizerDiagnostics,
    PositionTarget,
    Proposal,
    RiskSummary,
    Side,
)
from latam_ls.data.synthetic import make_synthetic_market
from latam_ls.hashing import sha256_file
from latam_ls.market import MarketData
from latam_ls.workflow.approval import make_decision
from latam_ls.workflow.autonomy import make_autonomous_decision
from latam_ls.workflow.book import Book, book_entry_from_proposal
from latam_ls.workflow.daily import (
    SHADOW_RECORD_EVENT,
    DailyRunner,
    NoBookError,
    NoSessionError,
    PendingExecution,
    close_datetime,
    executable_in,
    risk_alerts,
    session_limitations,
    short_entry_prices,
    store_input_hashes,
)
from latam_ls.workflow.track_record import (
    CSV_COLUMNS,
    GENESIS_RECORD_HASH,
    MONTH_LABELS,
    TrackRecord,
    compare_tracks,
    write_exclusive,
)

CFG = FundConfig().with_overrides({"risk_model": {"history_days": 250}})
START, END = date(2025, 1, 2), date(2026, 10, 16)
W1, W2 = date(2026, 10, 5), date(2026, 10, 13)  # 12/10 é feriado na B3: semana 2 começa na terça
BLANK_DAY = date(2026, 10, 7)
BLANK_TICKER = "SBR02.SA"
NAV0 = 100_000_000.0
TOL = 1e-6


# ==========================================================
# Mercado, fonte de dados e carteiras montadas à mão
# ==========================================================

class FakeStore:
    """Fonte sem look-ahead: ``load(as_of)`` corta o mercado sintético em ``as_of``."""

    def __init__(self, md: MarketData) -> None:
        self.md = md
        self.loads: list[date] = []

    def load(self, as_of: date) -> MarketData:
        self.loads.append(as_of)
        return self.md.truncate(as_of)


@pytest.fixture(scope="module")
def market() -> MarketData:
    md = make_synthetic_market(seed=7, start=START, as_of=END)
    ts = pd.Timestamp(BLANK_DAY)
    frames = {}
    for name in ("close", "adj_close", "volume"):
        df = getattr(md, name).copy()
        df.loc[ts, BLANK_TICKER] = np.nan  # a linha não negocia no dia (dado ausente, não zero)
        frames[name] = df
    return replace(md, **frames)


def _target(md: MarketData, iid: str, ticker: str, weight: float,
            fee: float | None = None) -> PositionTarget:
    line = md.universe.lines.loc[ticker]
    issuer = md.universe.issuers.loc[iid]
    side = Side.LONG if weight > 0 else Side.SHORT
    return PositionTarget(
        issuer_id=iid, name=str(issuer["issuer_name"]), country=str(issuer["country"]),
        sector=str(issuer["gics_sector"]), side=side, weight=weight, notional_usd=weight * NAV0,
        execution_ticker=ticker, line_type=LineType(line["line_type"]),
        currency=str(line["currency"]), squeeze_bucket="LOW" if side == Side.SHORT else "NA",
        borrow_fee_annual=fee)


def _risk_summary() -> RiskSummary:
    return RiskSummary(
        ex_ante_vol=0.05, factor_vol=0.01, specific_vol=0.049, factor_risk_share=0.05, beta=0.0,
        gross=0.3, net=0.0, long_exposure=0.15, short_exposure=-0.15, n_long=5, n_short=5,
        var_1d_99=0.007, es_1d_99=0.008, var_1w_99=0.016, effective_n=10.0,
        max_days_to_liquidate=0.5, pct_nav_liquidated_1d=0.9)


def make_proposal(week: date, positions: list[PositionTarget], label: str = "cdp",
                  version: int = 1, cfg: FundConfig = CFG) -> Proposal:
    return Proposal(
        proposal_id=f"CDP-{week.isoformat()}-{label}", week=week, version=version,
        created_at=datetime(week.year, week.month, week.day, 12, 0, tzinfo=UTC),
        created_by="CDP — motor quantitativo", nav_usd=NAV0, snapshot_id="synthetic-7",
        snapshot_hash="a" * 64, config_hash=cfg.config_hash(), research_hash="e" * 64,
        positions=positions, risk=_risk_summary(), compliance=[],
        optimizer=OptimizerDiagnostics(status="optimal", solver="teste", solve_seconds=0.0),
        is_synthetic=True, data_notice="DADOS SIMULADOS — carteira de teste montada à mão")


def week1(md: MarketData) -> list[PositionTarget]:
    return [
        _target(md, "SIM001", "SBR01.SA", 0.03), _target(md, "SIM002", "SBR02.SA", 0.03),
        _target(md, "SIM003", "SBR03.SA", 0.03), _target(md, "SIM027", "SMX01.MX", 0.03),
        _target(md, "SIM040", "SCL02.SN", 0.03),
        _target(md, "SIM052", "SAR01ADR", -0.03, 0.01),  # ADR com SI alto (squeeze)
        _target(md, "SIM004", "SBR04ADR", -0.03, 0.004),
        _target(md, "SIM007", "SBR07ADR", -0.03),  # sem taxa na proposta: tabela do dia
        _target(md, "SIM010", "SBR10ADR", -0.03, 0.003),
        _target(md, "SIM013", "SBR13ADR", -0.03, 0.003),
    ]


def week2(md: MarketData) -> list[PositionTarget]:
    return [
        _target(md, "SIM001", "SBR01ADR", 0.03),  # troca de linha: local -> ADR
        _target(md, "SIM002", "SBR02.SA", 0.025),
        _target(md, "SIM027", "SMX01.MX", 0.03), _target(md, "SIM040", "SCL02.SN", 0.03),
        _target(md, "SIM016", "SBR16.SA", 0.03),  # nova posição (SIM003 sai)
        _target(md, "SIM052", "SAR01ADR", -0.02, 0.01),
        _target(md, "SIM004", "SBR04ADR", -0.03, 0.004),
        _target(md, "SIM007", "SBR07ADR", -0.03),
        _target(md, "SIM010", "SBR10ADR", -0.03, 0.003),
        _target(md, "SIM013", "SBR13ADR", -0.03, 0.003),
    ]


def approve_and_book(book: Book, proposal: Proposal, when: datetime) -> None:
    """Fluxo humano do livro: proposta → decisão com quatro olhos → booking."""
    book.save_proposal(proposal)
    decision = make_decision(proposal, "Ana Gestora", DecisionType.APPROVE,
                             "Aprovação da carteira de teste da semana.", proposal.research_hash,
                             co_signer="Bruno Risco", now=when)
    book.save_decision(decision)
    entry = book_entry_from_proposal(proposal, decision, booked_at=when)
    book.save_booked(entry, proposal.snapshot_hash, CFG.config_hash(), proposal.research_hash)


@pytest.fixture(scope="module")
def human(tmp_path_factory, market) -> SimpleNamespace:
    """Livro com duas semanas aprovadas e efetivadas por humanos; backfill de 01 a 16/out."""
    root = tmp_path_factory.mktemp("daily_human") / "book"
    book = Book(root, CFG)
    approve_and_book(book, make_proposal(W1, week1(market)),
                     datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    approve_and_book(book, make_proposal(W2, week2(market)),
                     datetime(2026, 10, 13, 18, 0, tzinfo=UTC))
    store = FakeStore(market)
    track = TrackRecord(root / "track_record")
    runner = DailyRunner(CFG, store, book, track)
    records = runner.backfill(date(2026, 10, 1), END)
    return SimpleNamespace(root=root, book=book, track=track, runner=runner, records=records,
                           by_date={r.date: r for r in records}, store=store)


def _pos(record: DailyRecord, ticker: str) -> DailyPosition:
    return next(p for p in record.positions if p.ticker == ticker)


def _lines(record: DailyRecord, group: str) -> dict[str, float]:
    return {a.name: a.pnl_usd for a in record.attribution if a.group == group}


# ==========================================================
# Inception, NAV e deriva
# ==========================================================

def test_backfill_starts_at_first_booking_and_skips_non_sessions(human):
    dates = [r.date for r in human.records]
    assert dates[0] == W1  # 01–02/out: sem carteira efetivada (pulados)
    assert all(d.weekday() < 5 for d in dates)
    assert dates == sorted(dates) and len(set(dates)) == len(dates)
    assert dates[-1] == END
    # Sem look-ahead: cada pregão carrega dados só até a própria data.
    assert all(d in human.store.loads for d in dates)


def test_inception_record_is_moc_execution_with_costs_only(human):
    r = human.by_date[W1]
    entry = human.book.load_booked(W1)
    assert r.prev_record_hash == GENESIS_RECORD_HASH
    assert r.nav_start_usd == pytest.approx(CFG.fund.inception_nav_usd)
    comp = r.pnl_components
    assert comp["equity"] == 0.0 and comp["financing"] == 0.0 and comp["borrow"] == 0.0
    assert comp["costs"] < 0
    assert r.pnl_usd == pytest.approx(comp["costs"], abs=TOL)
    assert r.nav_end_usd == pytest.approx(r.nav_start_usd + comp["costs"], abs=TOL)
    assert r.live_book_week == W1 and r.approval_hash == entry.approval_hash
    held = {p.ticker: p for p in r.positions}
    assert set(held) == {p.ticker for p in entry.positions}
    md = human.store.md.truncate(W1)
    for b in entry.positions:
        p = held[b.ticker]
        assert p.day_pnl_usd == 0.0
        assert p.shares == pytest.approx(round(p.shares))  # ações inteiras
        # Nocional-alvo = peso × NAV antes dos custos, ao fechamento local × câmbio do dia.
        assert p.market_value_usd == pytest.approx(b.weight * r.nav_start_usd,
                                                   abs=p.price_usd + 1.0)
        close = float(md.close[b.ticker].dropna().iloc[-1])
        assert p.price_local == pytest.approx(close)
        assert p.market_value_usd == pytest.approx(p.shares * p.price_usd, rel=1e-9)
        assert p.weight == pytest.approx(p.market_value_usd / r.nav_end_usd)


def test_nav_chain_financing_and_borrow(human):
    recs = human.records
    proposals = {W1: human.book.load_proposal(W1), W2: human.book.load_proposal(W2)}
    for prev, r in zip(recs, recs[1:], strict=False):
        days = (r.date - prev.date).days
        comp = r.pnl_components
        assert r.prev_record_hash == prev.record_hash
        assert r.nav_start_usd == prev.nav_end_usd
        assert r.nav_end_usd == pytest.approx(r.nav_start_usd + r.pnl_usd, abs=TOL)
        total = comp["equity"] + comp["financing"] + comp["borrow"] + comp["costs"]
        assert r.pnl_usd == pytest.approx(total, abs=TOL)
        assert r.ret == pytest.approx(r.pnl_usd / r.nav_start_usd)
        # Financiamento ACT/360 sobre o NAV inicial (USD_3M = 4% no sintético).
        assert comp["financing"] == pytest.approx(prev.nav_end_usd * 0.04 / 360 * days)
        # Aluguel: taxa da proposta efetivada; sem taxa, a da tabela de aluguel do dia.
        prop = proposals[prev.live_book_week]
        fees = {p.issuer_id: p.borrow_fee_annual for p in prop.positions
                if p.side == Side.SHORT and p.borrow_fee_annual is not None}
        md = human.store.md.truncate(r.date)
        table = short_availability(build_asset_panel(md, CFG, as_of=r.date), md, CFG)
        expected = 0.0
        for p in prev.positions:
            if p.market_value_usd < 0:
                fee = fees.get(p.issuer_id, table.loc[p.ticker, "borrow_fee_annual"])
                expected -= abs(p.market_value_usd) * fee / 360 * days
        assert comp["borrow"] == pytest.approx(expected, rel=1e-9)
    weekend = human.by_date[date(2026, 10, 12)]
    assert weekend.pnl_components["financing"] == pytest.approx(
        human.by_date[date(2026, 10, 9)].nav_end_usd * 0.04 / 360 * 3)


def test_positions_drift_with_line_usd_returns(human):
    d = date(2026, 10, 9)
    r, prev = human.by_date[d], human.by_date[date(2026, 10, 8)]
    md = human.store.md.truncate(d)
    lr = build_asset_panel(md, CFG, as_of=d).line_returns
    for p0 in prev.positions:
        p = _pos(r, p0.ticker)
        ret = lr.loc[pd.Timestamp(d), p0.ticker]
        if pd.isna(ret):
            assert not p.repriced and p.market_value_usd == p0.market_value_usd
            continue
        assert p.day_return_usd == pytest.approx(ret)
        assert p.day_pnl_usd == pytest.approx(p0.market_value_usd * ret)
        assert p.market_value_usd == pytest.approx(p0.market_value_usd * (1 + ret))
        assert p.shares == p0.shares  # sem negociação entre rebalanceamentos
    assert r.pnl_components["costs"] == 0.0
    assert sum(p.day_pnl_usd for p in r.positions) == pytest.approx(r.pnl_components["equity"])


def test_non_repriced_line_is_carried_alerted_and_caught_up(human):
    prev, r, nxt = (human.by_date[date(2026, 10, 6)], human.by_date[BLANK_DAY],
                    human.by_date[date(2026, 10, 8)])
    p = _pos(r, BLANK_TICKER)
    assert p.repriced is False and p.day_return_usd is None and p.day_pnl_usd == 0.0
    assert p.market_value_usd == _pos(prev, BLANK_TICKER).market_value_usd
    assert p.price_local == _pos(prev, BLANK_TICKER).price_local
    assert any(BLANK_TICKER in a and "não reprecificada" in a for a in r.alerts)
    # No pregão seguinte o movimento acumulado (06→08/out) entra integralmente.
    q = _pos(nxt, BLANK_TICKER)
    md = human.store.md.truncate(date(2026, 10, 8))
    adj = md.adj_close[BLANK_TICKER]
    fx = md.fx["BRL"]
    lvl = adj * fx
    expected = lvl.loc[pd.Timestamp("2026-10-08")] / lvl.loc[pd.Timestamp("2026-10-06")] - 1
    assert q.repriced and q.day_return_usd == pytest.approx(expected, rel=1e-9)
    assert q.day_pnl_usd == pytest.approx(p.market_value_usd * expected)


def test_rebalance_day_pnl_from_old_book_then_new_positions(human):
    r = human.by_date[W2]
    prev = human.by_date[date(2026, 10, 12)]
    entry = human.book.load_booked(W2)
    comp = r.pnl_components
    assert comp["costs"] < 0
    issuers = _lines(r, "issuer")
    assert set(issuers) == {p.issuer_id for p in prev.positions}  # só a carteira antiga
    assert "SIM016" not in issuers
    by_ticker = {p.ticker: p for p in r.positions}
    for closed in ("SBR01.SA", "SBR03.SA"):  # troca de linha e saída
        assert by_ticker[closed].market_value_usd == 0.0 and by_ticker[closed].weight == 0.0
        assert by_ticker[closed].day_pnl_usd != 0.0
    for opened in ("SBR01ADR", "SBR16.SA"):
        assert by_ticker[opened].day_pnl_usd == 0.0 and by_ticker[opened].market_value_usd > 0
    nav_pre = r.nav_start_usd + comp["equity"] + comp["financing"] + comp["borrow"]
    for b in entry.positions:
        p = by_ticker[b.ticker]
        assert p.market_value_usd == pytest.approx(b.weight * nav_pre, abs=p.price_usd + 1.0)
    assert r.live_book_week == W2 and r.approval_hash == entry.approval_hash
    assert sum(p.day_pnl_usd for p in r.positions) == pytest.approx(comp["equity"])
    assert {"market_data", "config", "book_entry", "approval", "proposal", "risk_model",
            "risk_model_prev"} <= set(r.input_hashes)
    assert r.risk.n_long == 5 and r.risk.n_short == 5


# ==========================================================
# Atribuição, risco e alertas
# ==========================================================

def test_attribution_sums_are_exact(human):
    for r in human.records:
        comp = r.pnl_components
        assert comp["factor"] + comp["specific"] == pytest.approx(comp["equity"], abs=TOL)
        for group in ("issuer", "country", "sector", "side"):
            assert sum(_lines(r, group).values()) == pytest.approx(comp["equity"], abs=TOL)
        assert sum(_lines(r, "factor_group").values()) == pytest.approx(comp["factor"], abs=TOL)
        assert sum(_lines(r, "factor").values()) == pytest.approx(comp["factor"], abs=TOL)
        assert _lines(r, "component") == pytest.approx(comp)
        for a in r.attribution:
            assert a.contribution == pytest.approx(a.pnl_usd / r.nav_start_usd)
    later = human.records[1:]
    assert all(set(_lines(r, "factor_group")) == {"market", "country", "sector", "style"}
               for r in later)
    assert all(set(_lines(r, "side")) == {"LONG", "SHORT"} for r in later)
    assert any(abs(r.pnl_components["factor"]) > 0 for r in later)


def test_daily_risk_block(human):
    for r in human.records:
        risk = r.risk
        assert 0.0 < risk.ex_ante_vol < 0.2 and risk.factor_vol <= risk.ex_ante_vol + TOL
        assert risk.var_1d_99 > 0 and risk.es_1d_99 >= risk.var_1d_99 - TOL
        assert risk.gross == pytest.approx(risk.long_exposure - risk.short_exposure)
        assert risk.drawdown <= 0.0
        assert risk.realized_vol_21d is None and risk.realized_vol_63d is None  # < 21 pregões
        assert risk.max_days_to_liquidate is not None and risk.pct_gross_liquid_1d is not None
        assert {e.group for e in risk.exposures} == {"country", "sector", "style"}
        # Os alertas de mandato do registro são exatamente os do risco gravado.
        assert set(risk_alerts(CFG, risk)) <= set(r.alerts)
    navs = [human.records[0].nav_start_usd] + [r.nav_end_usd for r in human.records]
    peak = np.maximum.accumulate(navs)[1:]
    for r, pk in zip(human.records, peak, strict=True):
        assert r.risk.drawdown == pytest.approx(r.nav_end_usd / pk - 1)


def test_squeeze_alerts_for_short_turned_high(human):
    r = human.records[-1]
    assert r.risk.squeeze_high_shorts >= 1
    assert any("SAR01ADR" in a and "squeeze HIGH" in a and "era LOW" in a for a in r.alerts)


def test_synthetic_notice_and_paper_trading_label(human):
    for r in human.records:
        assert r.is_synthetic and "DADOS SIMULADOS" in r.data_notice
        assert "paper trading" in r.track_record_type
        assert r.track_record_type == CFG.fund.track_record_type
        assert r.fund_name == CFG.fund.name


def test_risk_alerts_vol_band_net_beta_and_drawdown_ladder():
    def risk(**kw) -> DailyRisk:
        base = dict(ex_ante_vol=0.05, beta=0.0, gross=1.0, net=0.0, long_exposure=0.5,
                    short_exposure=-0.5, n_long=10, n_short=10, drawdown=0.0)
        base.update(kw)
        return DailyRisk(**base)

    assert risk_alerts(CFG, risk()) == []
    assert any("abaixo da banda" in a for a in risk_alerts(CFG, risk(ex_ante_vol=0.02)))
    assert any("acima da banda" in a for a in risk_alerts(CFG, risk(ex_ante_vol=0.08)))
    assert any("Exposição líquida" in a for a in risk_alerts(CFG, risk(net=0.02)))
    assert any("Beta previsto" in a for a in risk_alerts(CFG, risk(beta=0.10)))
    soft = risk_alerts(CFG, risk(drawdown=-0.03))
    hard = risk_alerts(CFG, risk(drawdown=-0.06))
    out = risk_alerts(CFG, risk(drawdown=-0.08))
    assert len(soft) == 1 and soft[0].startswith("SOFT STOP") and "75,00%" in soft[0]
    assert len(hard) == 1 and hard[0].startswith("HARD STOP") and "50,00%" in hard[0]
    assert len(out) == 1 and out[0].startswith("STOP-OUT") and "revisão completa" in out[0]
    assert risk_alerts(CFG, risk(ex_ante_vol=0.0), has_positions=False) == []


def test_short_entry_prices_average_cost_within_spell():
    def rec(shares: float | None, px: float) -> DailyRecord:
        positions = [] if shares is None else [DailyPosition(
            issuer_id="X", ticker="XADR", currency="USD", side=Side.SHORT, shares=shares,
            price_local=px, price_usd=px, market_value_usd=shares * px, weight=-0.01,
            day_pnl_usd=0.0)]
        return DailyRecord(
            date=date(2026, 10, 5), fund_name="f", track_record_type="t", nav_start_usd=1.0,
            nav_end_usd=1.0, pnl_usd=0.0, ret=0.0, positions=positions,
            risk=DailyRisk(gross=0, net=0, long_exposure=0, short_exposure=0, n_long=0,
                           n_short=0),
            is_synthetic=False, prev_record_hash=GENESIS_RECORD_HASH)

    # Mais recente → mais antigo: aumento de 100 para 200 ações a 12; antes disso, sem posição.
    history = [rec(-200, 12.5), rec(-200, 12.0), rec(-100, 10.0), rec(None, 9.0), rec(-50, 5.0)]
    entries = short_entry_prices(history, {"XADR": (-200.0, 13.0), "NEW": (-10.0, 7.0)})
    assert entries["XADR"] == pytest.approx((100 * 10.0 + 100 * 12.0) / 200)
    assert entries["NEW"] == pytest.approx(7.0)
    # Stop de squeeze: alta de 25% sobre o preço médio de entrada.
    assert 13.75 / entries["XADR"] - 1 >= CFG.squeeze.stop_short_position_loss


# ==========================================================
# Cadeia de hash, imutabilidade e verificação
# ==========================================================

def _copy_track(src_root: Path, dst: Path) -> TrackRecord:
    shutil.copytree(src_root, dst / "book")
    return TrackRecord(dst / "book" / "track_record")


def test_track_verify_passes_and_csv_matches_json(human):
    ok, problems = human.track.verify()
    assert ok, problems
    frame = human.track.frame()
    assert list(frame.columns) == CSV_COLUMNS[1:]
    assert len(frame) == len(human.records)
    assert frame["record_hash"].tolist() == [r.record_hash for r in human.records]
    assert frame["nav"].iloc[-1] == human.records[-1].nav_end_usd
    events = [e for e in human.book.audit.events() if e.event_type == "DAILY_RECORD"]
    assert len(events) == len(human.records)
    ok_all, problems_all = human.runner.verify_all()
    assert ok_all, problems_all


@pytest.mark.parametrize("tamper", ["edit", "delete_middle", "reorder", "csv", "delete_last"])
def test_track_verify_detects_tampering(human, tmp_path, tamper):
    track = _copy_track(human.root, tmp_path)
    files = sorted(track.records_dir.glob("*.json"))
    if tamper == "edit":
        data = json.loads(files[3].read_text(encoding="utf-8"))
        data["nav_end_usd"] += 1_000.0
        files[3].write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        expected = "adulterado"
    elif tamper == "delete_middle":
        files[4].unlink()
        expected = "encadeamento"
    elif tamper == "reorder":
        a, b = files[2].read_text(encoding="utf-8"), files[3].read_text(encoding="utf-8")
        files[2].write_text(b, encoding="utf-8")
        files[3].write_text(a, encoding="utf-8")
        expected = "reordenado"
    elif tamper == "csv":
        lines = track.csv_path.read_text(encoding="utf-8").splitlines()
        cells = lines[3].split(",")
        cells[1] = repr(float(cells[1]) * 1.01)
        lines[3] = ",".join(cells)
        track.csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        expected = "CSV divergente"
    else:
        files[-1].unlink()
        lines = track.csv_path.read_text(encoding="utf-8").splitlines()
        track.csv_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        expected = "sem registro correspondente"
    ok, problems = track.verify()
    assert not ok
    assert any(expected in p for p in problems), problems


def test_refuses_duplicate_out_of_order_and_overwrite(human, tmp_path):
    track = _copy_track(human.root, tmp_path)
    last = track.last()
    with pytest.raises(ValueError, match="Elo da cadeia|duplicado"):
        track.append(last)
    older = human.records[2]
    with pytest.raises(ValueError):
        track.append(older)
    forged = older.model_copy(update={"date": date(2026, 10, 19),
                                      "prev_record_hash": last.record_hash})
    with pytest.raises(ValueError, match="record_hash"):
        track.append(forged)  # hash não recalculado
    resealed = forged.model_copy(update={"record_hash": forged.compute_hash()})
    path = track.append(resealed)  # elo e hash corretos: aceito
    original = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="duplicado|Elo da cadeia"):
        track.append(resealed)
    with pytest.raises(FileExistsError):
        write_exclusive(path, "{}")  # arquivos do track record nunca são sobrescritos
    assert path.read_text(encoding="utf-8") == original
    assert track.verify()[0]
    with pytest.raises(ValueError, match="já registrado"):
        human.runner.run(END)
    with pytest.raises(ValueError, match="anterior ao último registro"):
        human.runner.run(date(2026, 10, 8))


def test_no_session_and_no_book(tmp_path, market):
    runner = DailyRunner(CFG, FakeStore(market), Book(tmp_path / "book", CFG),
                         TrackRecord(tmp_path / "book" / "track_record"))
    with pytest.raises(NoSessionError, match="sem pregão"):
        runner.run(date(2026, 10, 10))  # sábado
    with pytest.raises(NoBookError):
        runner.run(W1)
    assert runner.backfill(date(2026, 10, 1), date(2026, 10, 9)) == []
    assert runner.track.last() is None and not runner.track.csv_path.exists()


# ==========================================================
# Estatísticas e grade mensal
# ==========================================================

def _chain(track: TrackRecord, days: list[tuple[date, float, float]]) -> None:
    nav, prev = NAV0, GENESIS_RECORD_HASH
    peak = nav
    for d, ret, fin_rate in days:
        pnl = nav * ret
        fin = nav * fin_rate
        peak = max(peak, nav + pnl)
        rec = DailyRecord(
            date=d, fund_name="CDP", track_record_type="paper trading", nav_start_usd=nav,
            nav_end_usd=nav + pnl, pnl_usd=pnl, ret=ret,
            pnl_components={"equity": pnl - fin, "financing": fin, "borrow": 0.0, "costs": 0.0},
            risk=DailyRisk(gross=1.0, net=0.0, long_exposure=0.5, short_exposure=-0.5, n_long=1,
                           n_short=1, drawdown=(nav + pnl) / peak - 1),
            is_synthetic=True, data_notice="DADOS SIMULADOS", prev_record_hash=prev)
        rec = rec.model_copy(update={"record_hash": rec.compute_hash()})
        track.append(rec)
        nav, prev = nav + pnl, rec.record_hash


def test_monthly_returns_table_and_stats(tmp_path):
    track = TrackRecord(tmp_path / "book" / "track_record")
    days = [(date(2026, 9, 29), 0.01, 0.0001), (date(2026, 9, 30), -0.02, 0.0001),
            (date(2026, 10, 1), 0.03, 0.0001), (date(2026, 10, 30), 0.01, 0.0003),
            (date(2026, 12, 1), -0.005, 0.0001), (date(2027, 1, 4), 0.02, 0.0003)]
    _chain(track, days)
    assert track.verify()[0]
    table = track.monthly_returns_table()
    assert list(table.columns) == MONTH_LABELS + ["YTD"]
    assert list(table.index) == [2026, 2027]
    assert table.loc[2026, "Set"] == pytest.approx(1.01 * 0.98 - 1)
    assert table.loc[2026, "Out"] == pytest.approx(1.03 * 1.01 - 1)
    assert math.isnan(table.loc[2026, "Nov"])  # mês sem registro fica ausente, não zero
    assert table.loc[2026, "Dez"] == pytest.approx(-0.005)
    assert table.loc[2026, "YTD"] == pytest.approx(1.01 * 0.98 * 1.03 * 1.01 * 0.995 - 1)
    assert table.loc[2027, "Jan"] == pytest.approx(0.02) == pytest.approx(table.loc[2027, "YTD"])

    st = track.stats(CFG)
    rets = np.array([d[1] for d in days])
    assert st["n_days"] == 6
    assert st["since_inception_return"] == pytest.approx(np.prod(1 + rets) - 1)
    assert st["pct_positive_days"] == pytest.approx(4 / 6)
    assert st["best_day"] == (date(2026, 10, 1), pytest.approx(0.03))
    assert st["worst_day"] == (date(2026, 9, 30), pytest.approx(-0.02))
    assert st["max_drawdown"] == pytest.approx(-0.02)
    assert st["annualized_vol"] == pytest.approx(rets.std(ddof=1) * math.sqrt(252))
    excess = rets - np.array([d[2] for d in days])
    assert st["sharpe"] == pytest.approx(excess.mean() / excess.std(ddof=1) * math.sqrt(252))
    assert st["realized_vol_21d"] is None and st["realized_vol_status"] == "histórico insuficiente"
    assert st["annualization_note"]
    assert track.nav_series().iloc[-1] == pytest.approx(NAV0 * np.prod(1 + rets))
    assert track.drawdown_series().min() == pytest.approx(-0.02)
    empty = TrackRecord(tmp_path / "vazio" / "track_record")
    assert empty.stats()["n_days"] == 0 and empty.monthly_returns_table().empty


# ==========================================================
# Execução autônoma (MOC) e carteira-sombra só-quant
# ==========================================================

def _autonomous(md: MarketData, decided: datetime, cfg: FundConfig = CFG):
    final = make_proposal(W1, week1(md), "cdp", cfg=cfg)
    shadow = make_proposal(W1, [_target(md, "SIM001", "SBR01ADR", 0.03),
                                _target(md, "SIM010", "SBR10ADR", -0.03, 0.003)],
                           "sombra-quant", cfg=cfg)
    decision = make_autonomous_decision(final, research_hash=final.research_hash,
                                        pm_decision_hash="b" * 64,
                                        rationale="Decisão autônoma de teste do CDP.",
                                        decided_at=decided)
    return final, shadow, decision


def test_autonomous_moc_execution_with_shadow(tmp_path, market):
    root = tmp_path / "book"
    runner = DailyRunner.from_root(CFG, FakeStore(market), root)
    final, shadow, decision = _autonomous(market, datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    res = runner.run_session(W1, pending=PendingExecution(final, decision, shadow))
    book = runner.book
    entry = book.load_booked(W1)  # conferido contra a trilha de auditoria
    assert entry is not None and res.booked == entry
    assert entry.approval_hash == decision.approval_hash
    assert entry.booked_at == close_datetime(W1, CFG) >= decision.decided_at
    assert book.load_decision(W1).mode.value == "AUTONOMOUS"
    rec = res.record
    shares = {p.ticker: p.shares for p in rec.positions}
    assert {b.ticker: float(b.shares) for b in entry.positions} == shares
    assert {b.ticker: b.notional_usd for b in entry.positions} == pytest.approx(
        {p.ticker: p.market_value_usd for p in rec.positions})
    # Sombra só-quant executada na própria série, ligada ao registro do CDP por hash.
    assert res.shadow is not None and res.shadow_booked is not None
    assert {p.ticker for p in res.shadow.positions} == {"SBR01ADR", "SBR10ADR"}
    assert rec.input_hashes["shadow_record"] == res.shadow.record_hash
    assert "sombra" in res.shadow.fund_name
    assert runner.shadow_book.load_booked(W1) == res.shadow_booked
    assert res.value_added == pytest.approx(rec.ret - res.shadow.ret)

    nxt = runner.run_session(date(2026, 10, 6))  # sem decisão: as duas carteiras derivam
    assert nxt.booked is None and nxt.shadow is not None and nxt.shadow_booked is None
    assert nxt.record.live_book_week == W1 and nxt.shadow.live_book_week == W1
    cmp = compare_tracks(runner.track, runner.shadow.track)
    assert len(cmp) == 2
    assert cmp["value_added"].iloc[-1] == pytest.approx(nxt.record.ret - nxt.shadow.ret)
    events = {e.event_type for e in book.audit.events()}
    assert {"PROPOSAL_CREATED", "DECISION_APPROVE", "BOOKED", "DAILY_RECORD",
            SHADOW_RECORD_EVENT, "BOOKED_SHADOW", "SHADOW_PROPOSAL_SAVED"} <= events

    # Semana 2: o CDP decide "manter" (sem negociação); a sombra só-quant rebalanceia.
    hold = make_proposal(W2, [], "manter").model_copy(update={
        "optimizer": OptimizerDiagnostics(status="hold", solver="none", solve_seconds=0.0)})
    hold_dec = make_autonomous_decision(hold, research_hash=hold.research_hash,
                                        pm_decision_hash="d" * 64,
                                        rationale="Manter a carteira anterior nesta semana.",
                                        decided_at=datetime(2026, 10, 13, 18, 0, tzinfo=UTC))
    shadow2 = make_proposal(W2, [_target(market, "SIM002", "SBR02.SA", 0.02),
                                 _target(market, "SIM010", "SBR10ADR", -0.02, 0.003)],
                            "sombra-quant")
    recs = runner.backfill(date(2026, 10, 7), W2,
                           pending=[PendingExecution(hold, hold_dec, shadow2)])
    assert [r.date for r in recs][-1] == W2
    before, held = recs[-2], recs[-1]
    assert held.pnl_components["costs"] == 0.0 and held.live_book_week == W2
    assert {p.ticker for p in held.positions} == {p.ticker for p in before.positions}
    assert all(p.shares == _pos(before, p.ticker).shares for p in held.positions)
    assert any("manter a carteira anterior" in a for a in held.alerts)
    assert book.load_booked(W2).positions == []
    sh = runner.shadow.track.last()
    assert sh.date == W2 and sh.live_book_week == W2 and sh.pnl_components["costs"] < 0
    assert {p.ticker for p in sh.positions if p.market_value_usd != 0} == {"SBR02.SA",
                                                                          "SBR10ADR"}
    # Depois de uma semana de "manter", o aluguel segue as taxas da decisão que abriu os shorts.
    after = runner.run(date(2026, 10, 14))
    md = market.truncate(date(2026, 10, 14))
    table = short_availability(build_asset_panel(md, CFG, as_of=date(2026, 10, 14)), md, CFG)
    fees = {p.issuer_id: p.borrow_fee_annual for p in final.positions if p.side == Side.SHORT}
    expected = -sum(abs(p.market_value_usd) * (fees[p.issuer_id] if fees[p.issuer_id] is not None
                                                else table.loc[p.ticker, "borrow_fee_annual"])
                    / 360 for p in held.positions if p.market_value_usd < 0)
    assert after.pnl_components["borrow"] == pytest.approx(expected, rel=1e-9)
    ok, problems = runner.verify_all()
    assert ok, problems


def test_store_input_hashes_follow_market_store_layout(tmp_path):
    root = tmp_path / "market"
    (root / "base" / "2026-10-02").mkdir(parents=True)
    (root / "base" / "2026-10-02" / "manifest.json").write_text('{"a": 1}', encoding="utf-8")
    (root / "base" / "2026-11-30").mkdir(parents=True)  # base posterior: ignorada
    (root / "base" / "2026-11-30" / "manifest.json").write_text('{"b": 2}', encoding="utf-8")
    (root / "daily" / "2026-10-05").mkdir(parents=True)
    (root / "daily" / "2026-10-05" / "manifest.json").write_text('{"c": 3}', encoding="utf-8")
    store = SimpleNamespace(root=root)
    h = store_input_hashes(store, W1)
    assert h["base_snapshot_manifest"] == sha256_file(root / "base" / "2026-10-02" /
                                                      "manifest.json")
    assert h["daily_increment_manifest"] == sha256_file(root / "daily" / "2026-10-05" /
                                                        "manifest.json")
    assert "daily_increment_manifest" not in store_input_hashes(store, date(2026, 10, 6))
    assert store_input_hashes(store, date(2026, 9, 1))["base_snapshot_manifest"] == h[
        "base_snapshot_manifest"]  # sem base anterior: a mais antiga (como MarketStore.load)
    assert store_input_hashes(SimpleNamespace(), W1) == {}


def test_tampered_or_late_or_stale_mandate_decisions_are_refused(tmp_path, market):
    root = tmp_path / "book"
    runner = DailyRunner.from_root(CFG, FakeStore(market), root)
    final, shadow, decision = _autonomous(market, datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    tampered = decision.model_copy(update={"pm_decision_hash": "c" * 64})
    with pytest.raises(ValueError, match="approval_hash"):
        runner.run(W1, pending=PendingExecution(final, tampered, shadow))
    assert runner.track.last() is None and runner.shadow.track.last() is None
    assert not (root / W1.isoformat() / "booked.json").exists()

    other_cfg = CFG.with_overrides({"risk": {"var_1d_max": 0.011}})
    other = DailyRunner.from_root(other_cfg, FakeStore(market), tmp_path / "outro")
    with pytest.raises(ValueError, match="Mandato|configuração"):
        other.run(W1, pending=PendingExecution(final, decision, shadow))

    # Decisão gravada depois do fechamento de segunda: só executa no pregão seguinte.
    f2, s2, late = _autonomous(market, datetime(2026, 10, 5, 21, 0, tzinfo=UTC))
    assert late.decided_at > close_datetime(W1, CFG)
    with pytest.raises(ValueError, match="após o fechamento"):
        runner.run(W1, pending=PendingExecution(f2, late, s2))
    recs = runner.backfill(W1, date(2026, 10, 6), pending=[PendingExecution(f2, late, s2)])
    assert [r.date for r in recs] == [date(2026, 10, 6)]
    assert recs[0].nav_start_usd == pytest.approx(CFG.fund.inception_nav_usd)
    assert any("primeiro pregão disponível" in a for a in recs[0].alerts)
    assert executable_in(W1, date(2026, 10, 9)) and not executable_in(W1, date(2026, 10, 12))


def test_execute_decision_then_run_adopts_the_booking(tmp_path, market):
    runner = DailyRunner.from_root(CFG, FakeStore(market), tmp_path / "book", with_shadow=False)
    final, _, decision = _autonomous(market, datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    entry = runner.execute_decision(W1, final, decision)
    assert runner.book.load_booked(W1) == entry
    assert runner.execute_decision(W1, final, decision) == entry  # idempotente
    rec = runner.run(W1)  # descobre a efetivação no livro
    assert rec.approval_hash == decision.approval_hash
    assert {p.ticker: p.shares for p in rec.positions} == {
        b.ticker: float(b.shares) for b in entry.positions}
    assert rec.pnl_components["costs"] < 0
    # Determinismo: executar via pendência num livro novo gera o mesmo registro, byte a byte.
    other = DailyRunner.from_root(CFG, FakeStore(market), tmp_path / "outro", with_shadow=False)
    same = other.run(W1, pending=PendingExecution(final, decision))
    assert same.record_hash == rec.record_hash
    assert (other.track.record_path(W1).read_bytes()
            == runner.track.record_path(W1).read_bytes())


def test_session_limitations_keep_base_and_same_day_only(market):
    manifest = market.manifest.model_copy(update={"limitations": [
        "Sobrevivência: universo definido hoje.", "[2026-10-05] Revisão do Yahoo em X.",
        "[2026-10-06] Feriado na B3.", "Composição: base 2026-10-02 + 2 incremento(s)."]})
    md = replace(market, manifest=manifest)
    assert session_limitations(md, date(2026, 10, 6)) == [
        "Sobrevivência: universo definido hoje.", "Feriado na B3."]
