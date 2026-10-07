"""MOC histórico usa o próprio vintage, nunca metadados futuros (DADOS SIMULADOS)."""

from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from test_calendar import ativado
from test_daily_track_record import FakeStore, make_proposal, week1, week2

from cdp.config import config_json
from cdp.contracts import DecisionType
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file
from cdp.workflow.approval import make_decision
from cdp.workflow.daily import DailyRunner, PendingExecution
from cdp.workflow.runtime import DECISION_CONFIG, Runtime

FIRST, SECOND = date(2023, 12, 8), date(2023, 12, 15)


@pytest.fixture(scope="module")
def booked(tmp_path_factory):
    root = tmp_path_factory.mktemp("booking-vintages")
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=date(2023, 12, 22))
    cfg = ativado(inception_date=str(FIRST), inception_nav_usd=100_000_000.0)
    runner = DailyRunner.from_root(cfg, FakeStore(md), root / "book", with_shadow=False)
    for d, positions in ((FIRST, week1(md)), (SECOND, week2(md))):
        prop = make_proposal(d, positions, cfg=cfg)
        dec = make_decision(
            prop,
            "Ana",
            DecisionType.APPROVE,
            "MOC simulado",
            prop.research_hash,
            co_signer="Bruno",
            now=datetime(d.year, d.month, d.day, 14, tzinfo=UTC),
        )
        runner.run_session(d, PendingExecution(prop, dec))
    return root / "book", cfg, md


class Vintages:
    def __init__(self, md, *, future_currency=False, unavailable=None, old_volume=False):
        self.md, self.calls = md, []
        self.future_currency = future_currency
        self.unavailable, self.old_volume = unavailable, old_volume

    def load(self, as_of=None, verify=True):
        self.calls.append(as_of)
        if as_of == self.unavailable and as_of is not None:
            raise FileNotFoundError("vintage ausente")
        view = self.md.truncate(as_of) if as_of else self.md
        if as_of is None and self.future_currency:
            lines = view.universe.lines.copy()
            lines["currency"] = "EUR"
            view = replace(view, universe=replace(view.universe, lines=lines))
        if as_of == FIRST and self.old_volume:
            volume = view.volume.copy()
            volume.loc[pd.Timestamp(FIRST)] = 1.0
            view = replace(view, volume=volume)
        return view


def runtime(tmp_path, booked, store):
    book, cfg, _ = booked
    target = tmp_path / "book"
    shutil.copytree(book, target)
    return Runtime(
        cfg,
        target,
        tmp_path / "market",
        tmp_path / "reports",
        store_override=store,
        teses_root=None,
    )


def test_each_booking_uses_own_day_future_metadata_cannot_reinterpret_it(tmp_path, booked):
    _, _, md = booked
    latest_changed = Vintages(md, future_currency=True)
    rt = runtime(tmp_path, booked, latest_changed)
    before = {str(p): sha256_file(p) for p in rt.book_root.rglob("*") if p.is_file()}
    assert rt.verify_execucao() == (
        True,
        ["2 efetivações conferidas contra a execução esperada no fechamento"],
    )
    assert latest_changed.calls == [FIRST, SECOND]
    # O vintage futuro só é incoerente neste cenário causal; nenhum valor é zero imputado.
    assert set(latest_changed.load().universe.lines["currency"]) == {"EUR"}
    assert before == {str(p): sha256_file(p) for p in rt.book_root.rglob("*") if p.is_file()}


def test_missing_own_vintage_is_failed_closed_without_latest_fallback(tmp_path, booked):
    _, _, md = booked
    store = Vintages(md, unavailable=FIRST)
    rt = runtime(tmp_path, booked, store)
    ok, errors = rt.verify_execucao()
    assert not ok and any("próprio pregão 2023-12-08" in e for e in errors)
    assert store.calls == [FIRST, SECOND] and None not in store.calls


def test_past_realized_volume_violation_still_fails_verification(tmp_path, booked):
    _, _, md = booked
    store = Vintages(md, old_volume=True)
    rt = runtime(tmp_path, booked, store)
    ok, errors = rt.verify_execucao()
    assert not ok and any("ações negociadas" in e for e in errors)
    assert any("2023-12-08" in e for e in errors)
    assert store.calls == [FIRST, SECOND]


def test_booking_day_uses_archived_mandate_timezone(tmp_path, booked):
    _, cfg, md = booked
    store = Vintages(md)
    rt = runtime(tmp_path, booked, store)
    for d in (FIRST, SECOND):
        (rt.week_dir(d) / DECISION_CONFIG).write_text(config_json(cfg), encoding="utf-8")
    # Uma configuração posterior converteria o carimbo UTC para o dia seguinte.
    rt.cfg = cfg.model_copy(
        update={"fund": cfg.fund.model_copy(update={"timezone": "Pacific/Kiritimati"})}
    )
    for d in (FIRST, SECOND):
        entry = rt.book.load_booked(d)
        assert entry.booked_at.tzinfo is not None
        assert entry.booked_at.astimezone(ZoneInfo(rt.cfg.fund.timezone)).date() != d
        assert rt._config_da_decisao(d, rt.book.load_proposal(d)).config_hash() == cfg.config_hash()
    assert rt.verify_execucao()[0]
    assert store.calls == [FIRST, SECOND]


def test_unknown_archived_mandate_is_failed_closed_even_if_book_is_integral(tmp_path, booked):
    _, cfg, md = booked
    store = Vintages(md)
    rt = runtime(tmp_path, booked, store)
    rt.cfg = cfg.model_copy(
        update={"fund": cfg.fund.model_copy(update={"timezone": "Pacific/Kiritimati"})}
    )
    assert rt.book.verify_integrity() == (True, [])
    for d in (FIRST, SECOND):
        assert rt._config_da_decisao(d, rt.book.load_proposal(d)) is None
    ok, errors = rt.verify_execucao()
    assert not ok and len(errors) == 2
    assert all("mandato autenticado da decisão indisponível" in e for e in errors)
    assert store.calls == []
