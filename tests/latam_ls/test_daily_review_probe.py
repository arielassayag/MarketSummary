"""Sondas temporárias da revisão (serão incorporadas ao arquivo de testes do módulo)."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import test_daily_track_record as T
from latam_ls.contracts import BookEntry
from latam_ls.workflow.daily import DailyRunner, PendingExecution, ShadowBook, save_decided_proposal
from latam_ls.workflow.track_record import TrackRecord
from latam_ls.workflow.autonomy import make_autonomous_decision

CFG, W1, W2 = T.CFG, T.W1, T.W2
market = T.market


def test_probe_tampered_last_record(tmp_path, market):
    runner = DailyRunner.from_root(CFG, T.FakeStore(market), tmp_path / "book", with_shadow=False)
    final, _, decision = T._autonomous(market, datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    runner.run(W1, pending=PendingExecution(final, decision))
    path = runner.track.record_path(W1)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["positions"][0]["market_value_usd"] *= 2
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="adulterad"):
        runner.run(date(2026, 10, 6))


def test_probe_mandate_change_after_booking(tmp_path, market):
    root = tmp_path / "book"
    runner = DailyRunner.from_root(CFG, T.FakeStore(market), root, with_shadow=False)
    final, _, decision = T._autonomous(market, datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    runner.execute_decision(W1, final, decision)
    other_cfg = CFG.with_overrides({"risk": {"var_1d_max": 0.011}})
    other = DailyRunner.from_root(other_cfg, T.FakeStore(market), root, with_shadow=False)
    rec = other.run(W1)
    assert rec.approval_hash == decision.approval_hash


def test_probe_kill_switch(tmp_path, market):
    root = tmp_path / "book"
    runner = DailyRunner.from_root(CFG, T.FakeStore(market), root, with_shadow=False)
    final, _, decision = T._autonomous(market, datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    runner.run(date(2026, 10, 9), pending=PendingExecution(final, decision))
    p2 = T.make_proposal(W2, T.week2(market))
    d2 = make_autonomous_decision(p2, research_hash=p2.research_hash, pm_decision_hash="f" * 64,
                                  rationale="Semana 2 autônoma de teste.",
                                  decided_at=datetime(2026, 10, 13, 18, 0, tzinfo=UTC))
    save_decided_proposal(runner.book, p2, d2, CFG)
    (root / "KILL_SWITCH").write_text("{}", encoding="utf-8")
    rec = runner.run(W2)
    assert rec.live_book_week == W1


def test_probe_shadow_event_inferred(tmp_path):
    t = TrackRecord(tmp_path / "book" / "track_record_shadow")
    assert t.audit_event == "DAILY_RECORD_SHADOW"


def test_probe_provisional(tmp_path, market):
    runner = DailyRunner.from_root(CFG, T.FakeStore(market), tmp_path / "book", with_shadow=False)
    final, _, decision = T._autonomous(market, datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    md = replace(market, manifest=market.manifest.model_copy(update={"provisional_dates": [W1]}))
    with pytest.raises(ValueError, match="provis"):
        runner.execute_decision(W1, final, decision, md=md)


class RevisingStore(T.FakeStore):
    def load(self, as_of):
        md = super().load(as_of)
        k = (as_of - W1).days
        f = md.fundamentals.copy()
        idx = f.index[::3]
        f.loc[idx, "market_cap"] = f.loc[idx, "market_cap"] * (1 + 0.5 * max(k, 0))
        return replace(md, fundamentals=f)


def test_probe_path_independence(tmp_path, market):
    final, _, decision = T._autonomous(market, datetime(2026, 10, 5, 18, 0, tzinfo=UTC))
    a = DailyRunner.from_root(CFG, RevisingStore(market), tmp_path / "a", with_shadow=False)
    a.backfill(W1, date(2026, 10, 6), pending=[PendingExecution(final, decision)])
    root_b = tmp_path / "b"
    DailyRunner.from_root(CFG, RevisingStore(market), root_b, with_shadow=False).run(
        W1, pending=PendingExecution(final, decision))
    b = DailyRunner.from_root(CFG, RevisingStore(market), root_b, with_shadow=False)
    b.run(date(2026, 10, 6))
    for d in (W1, date(2026, 10, 6)):
        assert a.track.record_path(d).read_bytes() == b.track.record_path(d).read_bytes(), d


def test_probe_shadow_cross_week(tmp_path, market):
    track = TrackRecord(tmp_path / "book" / "track_record_shadow", audit_event="X")
    sb = ShadowBook(track)
    p = T.make_proposal(W1, T.week1(market), "sombra-quant")
    sb.save_proposal(p)
    entry = BookEntry(week=W1, proposal_id=p.proposal_id, approval_hash=p.proposal_hash(),
                      booked_at=datetime(2026, 10, 5, 20, 0, tzinfo=UTC), nav_usd=1e8,
                      positions=[])
    sb.save_booked(entry)
    sb.proposal_path(W2).write_text(sb.proposal_path(W1).read_text("utf-8"), "utf-8")
    sb.booked_path(W2).parent.mkdir(parents=True, exist_ok=True)
    sb.booked_path(W2).write_text(sb.booked_path(W1).read_text("utf-8"), "utf-8")
    with pytest.raises(ValueError):
        sb.load_proposal(W2)
    with pytest.raises(ValueError):
        sb.load_booked(W2)
