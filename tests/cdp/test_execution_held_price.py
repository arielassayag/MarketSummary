"""Preço próprio inválido da linha detida impede troca local↔ADR (DADOS SIMULADOS)."""

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from test_daily_track_record import make_proposal

from cdp.config import load_config
from cdp.contracts import BookedPosition, BookEntry, LineType, PositionTarget, Side
from cdp.data.synthetic import make_synthetic_market
from cdp.portfolio.execucao import (
    OrdemLinha,
    conferir_efetivacao,
    janela_execucao,
    preenchimentos_esperados,
)

DAY = date(2024, 3, 15)
BRT = ZoneInfo("America/Sao_Paulo")


@pytest.fixture(scope="module")
def pair():
    cfg = load_config()
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=DAY)
    lines = md.universe.lines
    local = next(
        t for t in lines.index
        if t.endswith(".SA") and (lines.issuer_id == lines.at[t, "issuer_id"]).sum() > 1
    )
    iid = str(lines.at[local, "issuer_id"])
    adr = next(t for t in lines.index if lines.at[t, "issuer_id"] == iid and t != local)
    return cfg, md, iid, local, adr


@pytest.mark.parametrize("invalid", [np.nan, 0.0, np.inf], ids=["ausente", "zero", "infinito"])
@pytest.mark.parametrize("sign", [1, -1], ids=["long", "short"])
def test_held_price_freezes_whole_issuer_and_rejects_new_adr_delta(pair, invalid, sign):
    cfg, md, iid, local, adr = pair
    ts = pd.Timestamp(DAY)
    close = md.close.copy()
    close.at[ts, local] = invalid
    unavailable = replace(md, close=close)
    nav = cfg.fund.inception_nav_usd
    px_adr = float(md.close.at[ts, adr])
    fx = float(md.fx.at[ts, "BRL"])
    decided = datetime(2024, 3, 15, 13, 7, tzinfo=BRT)
    # A troca de linha foi fixada antes de observar a ausência no MOC; não recalibrar a meta.
    target = PositionTarget(
        issuer_id=iid, name=iid, country="BR", sector="X",
        side=Side.LONG if sign > 0 else Side.SHORT,
        weight=sign * 0.01, notional_usd=0.01 * nav,
        execution_ticker=adr, line_type=LineType.ADR, currency="USD",
        price_local=px_adr, shares=sign * 100,
    )
    proposal = make_proposal(DAY, [target], cfg=cfg).model_copy(update={"nav_usd": nav})
    fixed_hash = proposal.proposal_hash()
    # O preço carregado não autoriza fechar a local nem abrir outra linha do mesmo emissor.
    old_px = float(md.close[local].loc[md.close.index < ts].iloc[-1])
    orders = [
        OrdemLinha(iid, local, sign * 100, 0, old_px, fx),
        OrdemLinha(iid, adr, 0, sign * 100, px_adr, 1.0),
    ]
    fills = preenchimentos_esperados(
        orders, unavailable, janela_execucao(DAY, cfg), cfg,
        nav_pre=nav, decidido_em=decided,
    )
    assert all(f.situacao == "congelado" and f.executadas == 0 for f in fills)
    assert all(local in f.motivo and "15/03/2024" in f.motivo for f in fills)
    held = BookedPosition(
        issuer_id=iid, ticker=local, weight=sign * 0.01, notional_usd=0.01 * nav,
        shares=sign * 100, currency="BRL",
    )
    correct = BookEntry(
        week=DAY, proposal_id=proposal.proposal_id, approval_hash="a" * 64,
        booked_at=datetime(2024, 3, 15, 18, tzinfo=BRT), nav_usd=nav, positions=[held],
    )
    assert conferir_efetivacao(
        correct, proposal, decided, {(iid, local): sign * 100}, unavailable, cfg
    ) == []
    # Livro construído pela hipótese econômica indevida, independentemente do fill calculado.
    invalid_book = correct.model_copy(update={"positions": [held, BookedPosition(
        issuer_id=iid, ticker=adr, weight=sign * 0.01, notional_usd=0.01 * nav,
        shares=sign * 100, currency="USD",
    )]})
    errors = conferir_efetivacao(
        invalid_book, proposal, decided, {(iid, local): sign * 100}, unavailable, cfg
    )
    assert len(errors) == 1 and f"{iid}/{adr}" in errors[0]
    assert "sem execução permitida" in errors[0] and local in errors[0]
    assert proposal.proposal_hash() == fixed_hash
    assert (pd.isna(unavailable.close.at[ts, local]) if pd.isna(invalid)
            else unavailable.close.at[ts, local] == invalid)
