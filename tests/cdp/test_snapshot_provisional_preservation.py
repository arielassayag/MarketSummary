"""Serializar uma captura não promove cotação provisória a fechamento (DADOS SIMULADOS)."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from cdp.config import load_config
from cdp.data.snapshot import load_snapshot, write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.workflow.daily import DailyRunner


def test_provisional_roundtrip_keeps_markers_and_daily_refuses_it(tmp_path):
    day = date(2024, 3, 8)
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=day)
    captured = datetime(2024, 3, 8, 14, 7, tzinfo=UTC)
    md = replace(md, manifest=md.manifest.model_copy(
        update={"provisional_dates": [day], "provisional_as_of": captured}))
    path = tmp_path / "snapshot"
    write_snapshot(md, path)
    loaded = load_snapshot(path)
    assert loaded.manifest.provisional_dates == [day]
    assert loaded.manifest.provisional_as_of == captured
    assert md.manifest.provisional_dates == [day]
    runner = DailyRunner.from_root(load_config(), None, tmp_path / "book", with_shadow=False)
    with pytest.raises(ValueError, match="provisória"):
        runner.context(day, md=loaded, need_models=False)
    assert runner.book.load_booked(day) is None


def test_official_snapshot_roundtrip_does_not_add_provisional_marker(tmp_path):
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=date(2024, 3, 8))
    write_snapshot(md, tmp_path / "snapshot")
    loaded = load_snapshot(tmp_path / "snapshot")
    assert loaded.manifest.provisional_dates == []
    assert loaded.manifest.provisional_as_of is None
