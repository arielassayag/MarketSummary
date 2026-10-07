"""Fonte física provisória, corte e conferência MOC — DADOS SIMULADOS.

Portável: todos os mercados e books vêm de fixtures existentes e de tmp_path.
Nenhum caminho de ensaio arquivado é necessário para executar estes testes em CI.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from test_calendar import ativado
from test_daily_track_record import FakeStore, make_proposal, week1, week2

from cdp.config import load_config
from cdp.contracts import DecisionType
from cdp.data.snapshot import load_snapshot, write_snapshot
from cdp.data.store import MarketStore
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file
from cdp.workflow.approval import make_decision
from cdp.workflow.daily import DailyRunner, PendingExecution
from cdp.workflow.runtime import Runtime

DAY, BEFORE, MIDDLE, FUTURE = (date(2026, 11, 20), date(2026, 11, 19),
                              date(2026, 11, 26), date(2026, 11, 27))
CAPTURE = datetime(2026, 11, 20, 16, 7, tzinfo=UTC)
FUTURE_CAPTURE = datetime(2026, 11, 27, 16, 7, tzinfo=UTC)
FIRST_BOOKING, SECOND_BOOKING, FUTURE_BOOKING = date(2023, 12, 8), date(2023, 12, 15), date(2023, 12, 22)


def files(root):
    return {str(p.relative_to(root)): sha256_file(p) for p in root.rglob('*') if p.is_file()}


@pytest.fixture(scope='module')
def md():
    return make_synthetic_market(seed=7, start=date(2025, 1, 2), as_of=FUTURE)


def physical(root, md, dates, captured):
    marked = replace(md, manifest=md.manifest.model_copy(update={
        'provisional_dates': dates, 'provisional_as_of': captured}))
    write_snapshot(marked, root / 'base' / str(md.as_of))
    return marked


@pytest.mark.parametrize('cut,expected', [(BEFORE, []), (DAY, [DAY]), (FUTURE, [DAY])])
def test_composed_store_preserves_single_marker_at_eligible_cut(md, tmp_path, cut, expected):
    raw = physical(tmp_path, md, [DAY], CAPTURE)
    before = files(tmp_path)
    loaded = MarketStore(tmp_path, cfg=load_config()).load(cut)
    assert loaded.manifest.provisional_dates == expected
    assert loaded.manifest.provisional_as_of == (CAPTURE if expected else None)
    assert raw.manifest.provisional_dates == [DAY]
    assert files(tmp_path) == before
    base_sha = sha256_file(tmp_path / 'base' / str(FUTURE) / 'manifest.json')
    assert any(f.path == f'base/{FUTURE}/manifest.json' and f.sha256 == base_sha
               for f in loaded.manifest.files)


def test_official_physical_reopen_preserves_content_and_has_no_marker(md, tmp_path):
    write_snapshot(md, tmp_path / 'base' / str(FUTURE))
    before = files(tmp_path)
    first = MarketStore(tmp_path, cfg=load_config()).load(DAY)
    second = MarketStore(tmp_path, cfg=load_config()).load(DAY)
    assert first.manifest.model_dump(mode='json') == second.manifest.model_dump(mode='json')
    assert first.manifest.provisional_dates == [] and first.manifest.provisional_as_of is None
    assert first.manifest.content_hash() == second.manifest.content_hash()
    assert files(tmp_path) == before


def test_runtime_physical_reopen_refuses_bar_before_moc_or_nav(md, tmp_path):
    market = tmp_path / 'market'
    physical(market, md, [DAY], CAPTURE)
    before = files(market)
    rt = Runtime(load_config(), tmp_path / 'book', market, tmp_path / 'reports', teses_root=None)
    with pytest.raises(ValueError, match='barra intradiária provisória'):
        rt.daily_close(DAY, live=False)
    assert rt.book.load_booked(DAY) is None and rt.track().get(DAY) is None
    assert not (tmp_path / 'reports/daily' / str(DAY)).exists()
    assert files(market) == before


@pytest.mark.parametrize('captured', [FUTURE_CAPTURE, CAPTURE], ids=['future_stamp', 'earlier_stamp'])
@pytest.mark.parametrize('cut', [DAY, MIDDLE], ids=['first_marker_day', 'between_markers'])
def test_partial_view_does_not_assign_global_timestamp_to_selected_bar(md, tmp_path, captured, cut):
    physical(tmp_path, md, [DAY, FUTURE], captured)
    before = files(tmp_path)
    loaded = MarketStore(tmp_path, cfg=load_config()).load(cut)
    assert loaded.manifest.provisional_dates == [DAY]
    # O contrato não tem carimbo por data. Nem a proximidade/data/fuso do
    # carimbo único demonstra associação à barra que sobreviveu ao corte.
    assert loaded.manifest.provisional_as_of is None
    assert load_snapshot(tmp_path / 'base' / str(FUTURE)).manifest.provisional_as_of == captured
    assert files(tmp_path) == before


@pytest.mark.parametrize('captured', [FUTURE_CAPTURE, CAPTURE], ids=['future_stamp', 'earlier_stamp'])
def test_complete_view_preserves_original_global_timestamp(md, tmp_path, captured):
    physical(tmp_path, md, [DAY, FUTURE], captured)
    loaded = MarketStore(tmp_path, cfg=load_config()).load(FUTURE)
    assert loaded.manifest.provisional_dates == [DAY, FUTURE]
    assert loaded.manifest.provisional_as_of == captured


def test_view_without_any_marker_has_no_timestamp_even_if_source_supplies_one(md, tmp_path):
    physical(tmp_path, md, [], FUTURE_CAPTURE)
    loaded = MarketStore(tmp_path, cfg=load_config()).load(DAY)
    assert loaded.manifest.provisional_dates == [] and loaded.manifest.provisional_as_of is None
    assert load_snapshot(tmp_path / 'base' / str(FUTURE)).manifest.provisional_as_of == FUTURE_CAPTURE


@pytest.fixture(scope='module')
def new_bookings(tmp_path_factory):
    root = tmp_path_factory.mktemp('fresh-portable-bookings')
    market = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=FUTURE_BOOKING)
    cfg = ativado(inception_date=str(FIRST_BOOKING), inception_nav_usd=100_000_000.0)
    runner = DailyRunner.from_root(cfg, FakeStore(market), root / 'book', with_shadow=False)
    for day, positions in ((FIRST_BOOKING, week1(market)), (SECOND_BOOKING, week2(market))):
        prop = make_proposal(day, positions, cfg=cfg)
        decision = make_decision(prop, 'Ana', DecisionType.APPROVE, 'MOC simulado',
                                 prop.research_hash, co_signer='Bruno',
                                 now=datetime(day.year, day.month, day.day, 14, tzinfo=UTC))
        runner.run_session(day, PendingExecution(prop, decision))
        assert runner.book.load_booked(day).positions
    assert runner.book.verify_integrity() == (True, [])
    return root / 'book', cfg, market


class RecordingStore(MarketStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def load(self, as_of=None, verify=True):
        self.calls.append(as_of)
        return super().load(as_of=as_of, verify=verify)


def runtime_for_bookings(tmp_path, new_bookings, markers):
    book, cfg, md = new_bookings
    market = tmp_path / 'market'
    captured = datetime(2023, 12, 22, 16, 7, tzinfo=UTC) if markers else None
    for day in [FIRST_BOOKING, SECOND_BOOKING]:
        view = replace(md.truncate(day), manifest=md.manifest.model_copy(update={'as_of': day}))
        physical(market, view, markers, captured)
    store = RecordingStore(market, cfg=cfg)
    rt = Runtime(cfg, book, market, tmp_path / 'reports', store_override=store, teses_root=None)
    return rt, store


def test_fresh_official_bookings_are_valid_under_physical_store(tmp_path, new_bookings):
    rt, store = runtime_for_bookings(tmp_path, new_bookings, [])
    before = files(rt.book_root)
    assert rt.verify_execucao() == (True, ['2 efetivações conferidas contra a execução esperada no fechamento'])
    assert store.calls == [FIRST_BOOKING, SECOND_BOOKING]
    assert before == files(rt.book_root)


def test_fresh_booking_on_provisional_own_day_is_rejected_previous_day_is_not(tmp_path, new_bookings):
    rt, store = runtime_for_bookings(tmp_path, new_bookings, [SECOND_BOOKING])
    before = {'book': files(rt.book_root), 'market': files(store.root)}
    assert rt.book.verify_integrity() == (True, [])
    ok, issues = rt.verify_execucao()
    assert not ok
    assert len(issues) == 1 and str(SECOND_BOOKING) in issues[0] and 'provisória' in issues[0]
    assert str(FIRST_BOOKING) not in issues[0]
    assert store.calls == [FIRST_BOOKING, SECOND_BOOKING]
    assert before == {'book': files(rt.book_root), 'market': files(store.root)}


def test_provisional_date_future_to_both_bookings_does_not_reinterpret_them(tmp_path, new_bookings):
    rt, store = runtime_for_bookings(tmp_path, new_bookings, [FUTURE_BOOKING])
    before = {'book': files(rt.book_root), 'market': files(store.root)}
    assert rt.verify_execucao() == (True, ['2 efetivações conferidas contra a execução esperada no fechamento'])
    assert store.calls == [FIRST_BOOKING, SECOND_BOOKING]
    assert before == {'book': files(rt.book_root), 'market': files(store.root)}
