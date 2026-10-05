"""Barra intradiária provisória: só cotações do dia, ausentes nunca viram zero, hash reprodutível."""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from cdp.data.intraday import fresh_quotes, load_quotes, overlay_intraday, save_quotes
from cdp.data.synthetic import make_synthetic_market

SESSION = date(2024, 3, 4)


@pytest.fixture(scope="module")
def md():
    full = make_synthetic_market(seed=7, start=date(2023, 6, 1), as_of=date(2024, 3, 1))
    return full


def _quotes(md, fresh_time: str, stale_time: str) -> pd.DataFrame:
    lines = list(md.close.columns[:3])
    last = md.close.ffill().iloc[-1]
    rows = [
        {"symbol": lines[0], "kind": "line", "price": float(last[lines[0]]) * 1.10,
         "time": fresh_time},
        {"symbol": lines[1], "kind": "line", "price": float(last[lines[1]]), "time": stale_time},
        {"symbol": lines[2], "kind": "line", "price": np.nan, "time": None},
    ]
    for ccy in md.fx.columns:
        if ccy != "USD":
            rows.append({"symbol": ccy, "kind": "fx", "price": float(md.fx[ccy].iloc[-1]),
                         "time": fresh_time})
    return pd.DataFrame(rows)


def test_fresh_quotes_keeps_only_session_day(md):
    q = _quotes(md, "2024-03-04T14:10:00+00:00", "2024-03-01T20:00:00+00:00")
    kept, stale = fresh_quotes(q, SESSION)
    assert md.close.columns[1] in stale
    assert md.close.columns[1] not in set(kept["symbol"])
    assert md.close.columns[0] in set(kept["symbol"])
    # 01h UTC de 05/03 ainda é 04/03 em Brasília
    late, _ = fresh_quotes(q.assign(time="2024-03-05T01:00:00+00:00"), SESSION)
    assert len(late) == len(q)  # todas com horário no dia (preço ausente segue NaN)


def test_overlay_adds_provisional_bar_without_fake_zero(md):
    q = _quotes(md, "2024-03-04T14:10:00+00:00", "2024-03-01T20:00:00+00:00")
    out = overlay_intraday(md, SESSION, q, datetime(2024, 3, 4, 14, 10, tzinfo=UTC))
    ts = pd.Timestamp(SESSION)
    a, b, c = md.close.columns[:3]
    assert out.as_of == SESSION and SESSION in out.manifest.provisional_dates
    assert out.close.loc[ts, a] == pytest.approx(float(md.close.ffill().iloc[-1][a]) * 1.10)
    ratio = out.adj_close.loc[ts, a] / float(md.adj_close.ffill().iloc[-1][a])
    assert ratio == pytest.approx(1.10)
    assert np.isnan(out.close.loc[ts, b])  # cotação de sexta não vira preço de hoje
    assert np.isnan(out.close.loc[ts, c])
    assert out.volume.loc[ts].isna().all()
    assert any("descartadas" in x for x in out.manifest.limitations)
    with pytest.raises(ValueError):
        overlay_intraday(out, SESSION, q, datetime(2024, 3, 4, 15, 0, tzinfo=UTC))


def test_quotes_roundtrip_is_hash_checked(md, tmp_path):
    q = _quotes(md, "2024-03-04T14:10:00+00:00", "2024-03-01T20:00:00+00:00")
    path = tmp_path / "q.parquet"
    sha = save_quotes(q, path, datetime(2024, 3, 4, 14, 10, tzinfo=UTC))
    back, captured = load_quotes(path, sha)
    assert captured == datetime(2024, 3, 4, 14, 10, tzinfo=UTC)
    assert sorted(back["symbol"]) == sorted(q["symbol"])
    with pytest.raises(ValueError):
        load_quotes(path, "0" * 64)
