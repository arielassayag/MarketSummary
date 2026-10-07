"""Ausência no próprio MOC impede fill/resíduo (DADOS SIMULADOS; Runtime público)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from test_replay_risk_boundaries import (
    AFTER,
    SECOND,
    close_remaining,
    seal_market,
)
from test_replay_risk_boundaries import (
    operational as _setup_fixture,  # noqa: F401 - fixture registrado pelo pytest
)

from cdp.hashing import sha256_file


@pytest.fixture(name="operational")
def operational_case(request):
    return request.getfixturevalue("_setup_fixture")


def files(folder):
    return {str(p.relative_to(folder)): sha256_file(p) for p in folder.rglob("*") if p.is_file()}


@pytest.mark.parametrize("missing", ["volume_nan", "volume_zero", "price", "fx", "all_volume_nan"])
def test_missing_moc_input_restricts_fixed_decision_and_never_fills_residual(operational, missing):
    rt, clock, md = operational
    close_remaining(rt, clock, md)
    old = rt.track().last()
    held = {(p.issuer_id, p.ticker): p.shares for p in old.positions if p.shares != 0}
    clock.set(SECOND, 11, 7)
    rt.weekly_prepare(SECOND, mind="codex", live=False)
    clock.set(SECOND, 13, 7)
    rt.weekly_decide(SECOND, mind="codex")
    proposal = rt.book.load_proposal(SECOND)
    # O target foi decidido usando a véspera íntegra, antes de arquivar o próprio MOC.
    candidates = [
        p
        for p in proposal.positions
        if p.shares
        and (
            p.shares != held.get((p.issuer_id, p.execution_ticker), 0)
            if missing == "fx"
            else held.get((p.issuer_id, p.execution_ticker), 0) == 0
        )
        and (p.currency != "USD" if missing == "fx" else p.currency == "USD")
    ]
    assert candidates, "Cenário seed7 deve conter ordem não nula na moeda requerida"
    target = sorted(candidates, key=lambda p: (p.issuer_id, p.execution_ticker))[0]
    fixed_shares, fixed_hash = target.shares, proposal.proposal_hash()
    held_target = held.get((target.issuer_id, target.execution_ticker), 0)
    assert fixed_shares != 0 and rt.book.load_booked(SECOND) is None
    immutable = files(rt.week_dir(SECOND))
    prior_market = files(rt.market_root)
    volume, close, adjusted, fx = (
        md.volume.copy(),
        md.close.copy(),
        md.adj_close.copy(),
        md.fx.copy(),
    )
    ts, tk = pd.Timestamp(SECOND), target.execution_ticker
    if missing in ("volume_nan", "volume_zero"):
        volume.loc[ts, tk] = np.nan if missing == "volume_nan" else 0.0
    elif missing == "all_volume_nan":
        volume.loc[ts, :] = np.nan
    elif missing == "price":
        close.loc[ts, tk] = np.nan
        adjusted.loc[ts, tk] = np.nan
    else:
        fx.loc[ts, target.currency] = np.nan
    unavailable = replace(md, volume=volume, close=close, adj_close=adjusted, fx=fx)
    seal_market(unavailable, rt.market_root, SECOND)
    # Prefixos anteriores não são sobrescritos; bruto ausente permanece ausente.
    assert all(sha256_file(rt.market_root / p) == h for p, h in prior_market.items())
    clock.set(SECOND, 19, 22)
    raw = rt.store.load(as_of=SECOND)
    if missing == "volume_zero":
        assert raw.volume.loc[ts, tk] == 0.0
    elif missing == "volume_nan":
        assert pd.isna(raw.volume.loc[ts, tk])
    elif missing == "all_volume_nan":
        assert raw.volume.loc[ts].isna().all()
    elif missing == "price":
        assert pd.isna(raw.close.loc[ts, tk]) and pd.isna(raw.adj_close.loc[ts, tk])
    else:
        assert pd.isna(raw.fx.loc[ts, target.currency])
    closed = rt.daily_close(SECOND, live=False, mind="codex")
    assert closed["status"] == "registrado"
    record = rt.track().get(SECOND)
    assert record.positions, "Carteira efetiva anterior torna o caso não trivial"
    actual = {(p.issuer_id, p.ticker): p.shares for p in record.positions if p.shares != 0}
    assert actual.get((target.issuer_id, tk), 0) == held_target
    if missing == "all_volume_nan":
        # Abstenção integral da negociação por falta de volume, não retorno/volume imputado.
        assert actual == held and record.pnl_components["costs"] == 0.0
    assert rt.book.load_proposal(SECOND).proposal_hash() == fixed_hash
    unchanged_target = next(
        p
        for p in rt.book.load_proposal(SECOND).positions
        if (p.issuer_id, p.execution_ticker) == (target.issuer_id, tk)
    )
    assert unchanged_target.shares == fixed_shares
    assert all(sha256_file(rt.week_dir(SECOND) / p) == h for p, h in immutable.items())
    # Dados bons no pregão seguinte não executam o pedaço não preenchido da ordem anterior.
    seal_market(md, rt.market_root, AFTER)
    clock.set(AFTER, 19, 22)
    next_close = rt.daily_close(AFTER, live=False, mind="codex")
    assert next_close["status"] == "registrado" and next_close["efetivacao"] is None
    next_record = rt.track().get(AFTER)
    next_actual = {
        (p.issuer_id, p.ticker): p.shares for p in next_record.positions if p.shares != 0
    }
    # O diário pode manter a linha do fill explicitamente zero no MOC e omiti-la depois.
    # Ambas representam o mesmo conjunto de ações detidas; o target continua sem fill.
    assert next_actual == actual and next_actual.get((target.issuer_id, tk), 0) == held_target
    assert next_record.pnl_components["costs"] == 0.0
    assert rt.book.load_proposal(SECOND).proposal_hash() == fixed_hash
    ok, errors = rt.verify_all()
    assert ok, errors
