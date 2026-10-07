"""Episódio completo E1 de feriado/early-close: DADOS SIMULADOS.

O driver produz decisões e efetivações; nenhuma carteira/ordem é fabricada.
O oráculo de ações/capacidade usa volume bruto e aritmética independente. O
oráculo de custos compartilha somente os insumos do frame público do diário,
não a fórmula de custos nem a composição do replay. Não certifica PIT real.
"""
from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from cdp.backtest.replay import ReplayStore, run_replay, verify_replay
from cdp.config import FundConfig, load_config
from cdp.contracts import Proposal
from cdp.data.snapshot import load_snapshot, write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file, sha256_obj
from cdp.portfolio.execucao import janela_execucao, tabela_capacidade
from cdp.workflow.daily import DailyRunner
from cdp.workflow.runtime import Runtime

BRT, NY = ZoneInfo("America/Sao_Paulo"), ZoneInfo("America/New_York")
FIRST, HOLIDAY, EARLY = date(2026, 11, 13), date(2026, 11, 20), date(2026, 11, 27)
SESSIONS = [date(2026, 11, d) for d in (13, 16, 17, 18, 19, 20, 23, 24, 25, 26, 27)]


def inventory(root):
    return {str(p.relative_to(root)): sha256_file(p) for p in root.rglob("*") if p.is_file()}


def shares(positions):
    return {(p.issuer_id, p.ticker): int(p.shares) for p in positions if p.shares}


@pytest.fixture(scope="module")
def calendar_driver(tmp_path_factory):
    root = tmp_path_factory.mktemp("calendar-driver-simulated")
    cfg = load_config()
    original = cfg.model_dump(mode="json")
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=EARLY)
    benchmarks, volume = md.benchmarks.copy(), md.volume.copy()
    close, adjusted = md.close.copy(), md.adj_close.copy()
    rng = np.random.default_rng(730)
    for factor in cfg.risk_model.macro_factors:
        benchmarks[factor] = 80 * np.cumprod(1 + rng.normal(0, .02, len(benchmarks)))
    local = [tk for tk in md.universe.lines.index if tk.endswith(".SA")]
    # Ausências correspondem ao feriado observado no calendário; nunca viram zero.
    for frame in (close, adjusted, volume):
        frame.loc[pd.Timestamp(HOLIDAY), local] = np.nan
    # Choque causal de liquidez só no leilão27, fora do ADV usado no prepare27.
    volume.loc[pd.Timestamp(EARLY)] *= .01
    source = root / "source"
    write_snapshot(replace(md, benchmarks=benchmarks, volume=volume,
                           close=close, adj_close=adjusted), source)
    preserved = inventory(source)
    out = root / ".cdp" / "ensaios" / "calendar-driver"
    result = run_replay(source, out, start=FIRST, end=EARLY, mode="simulado",
                        cfg=cfg, workspace=root)
    effective = FundConfig.model_validate_json((out / "inputs/fund_ensaio.json").read_text())
    def now():
        return datetime.combine(EARLY, time(19, 22), tzinfo=BRT)
    store = ReplayStore(out / "market", cfg=effective, now=now, close_cutoff=time(19, 22))
    rt = Runtime(effective, out / "book", out / "market", out / "reports",
                 clock=now, store_override=store, teses_root=None)
    assert inventory(source) == preserved and cfg.model_dump(mode="json") == original
    return rt, result, out, load_snapshot(source), original


def test_full_driver_prepares_decides_books_and_publishes_on_three_fridays(calendar_driver):
    rt, result, out, _, original = calendar_driver
    verified = verify_replay(out)
    assert verified["integridade"] and verified["concluido"]
    assert "DADOS SIMULADOS" in result["aviso"] and result["prospectiva"] is False
    assert result["registros"] == len(SESSIONS)
    assert [r.date for r in rt.track().records()] == SESSIONS
    assert [d["data"] for d in result["decisoes"]] == list(map(str, (FIRST, HOLIDAY, EARLY)))
    steps = [json.loads(line)["step_id"] for line in (out / "steps.jsonl").read_text().splitlines()]
    for day in (FIRST, HOLIDAY, EARLY):
        assert all(f"{day}/{stage}" in steps for stage in
                   ("prepare", "decide", "thesis", "close", "daily_report", "weekly_report"))
        decision, booked = rt.book.load_decision(day), rt.book.load_booked(day)
        assert decision is not None and booked is not None and booked.positions
        assert decision.decided_at <= rt.decision_deadline(day)
        assert shares(booked.positions) == shares(rt.track().get(day).positions)
    before, after = original, rt.cfg.model_dump(mode="json")
    assert after["fund"].pop("inception_date") == str(FIRST)
    before["fund"].pop("inception_date")
    assert before == after
    assert all(abs(d["ponte_nav_residuo_usd"]) < 1e-6 for d in result["diarios"])
    assert all(abs(d["ponte_caixa_residuo_usd"]) < 1e-6 for d in result["diarios"])


def test_full_driver_holiday_freezes_real_held_local_without_adding_adr(calendar_driver):
    rt, _, _, raw, _ = calendar_driver
    prev = rt.track().get(date(2026, 11, 19))
    old, actual = shares(prev.positions), shares(rt.track().get(HOLIDAY).positions)
    held_local = {(iid, tk): qty for (iid, tk), qty in old.items() if tk.endswith(".SA")}
    assert held_local, "O episódio precisa de posição local efetiva antes do feriado."
    frozen = {iid for iid, _ in held_local}
    for iid in frozen:
        assert {k:v for k,v in actual.items() if k[0] == iid} == {
            k:v for k,v in old.items() if k[0] == iid}
    for _, tk in held_local:
        assert all(math.isnan(getattr(raw, name).at[pd.Timestamp(HOLIDAY), tk])
                   for name in ("close", "adj_close", "volume"))
    j = janela_execucao(HOLIDAY, rt.cfg)
    assert not j.abertos["BVMF"] and j.abertos["XNYS"]
    proposal = rt.book.load_proposal(HOLIDAY)
    old_issuers = {iid for iid, _ in old}
    new_br = [p for p in proposal.positions if p.issuer_id not in old_issuers
              and str(raw.universe.issuers.at[p.issuer_id, "country"]) == "BR"]
    # A ocorrência econômica depende do alvo espontâneo do otimizador. A ausência
    # de nova linha é registrada pelo episódio e não fabricada para este teste.
    for p in new_br:
        line = raw.universe.lines.loc[p.execution_ticker]
        assert line["line_type"] == "ADR" and p.currency == "USD"
    # O congelamento pode ocorrer na construção, antes de existir ordem MOC.
    # Conferir a candidata quantitativa autenticada, em vez de exigir texto no
    # alerta diário da decisão final (que pode legitimamente manter a carteira).
    path = rt.week_dir(HOLIDAY) / "shadow_quant.json"
    candidate = Proposal.model_validate_json(path.read_text())
    capacity = candidate.overrides["construcao"]["capacidade_fechamento"]
    reasons = capacity["congelados"]
    assert frozen <= set(reasons)
    assert capacity["sessao"] == str(HOLIDAY)
    assert all("B3" in reasons[iid] for iid in frozen)
    ok, reason = rt.book.audit.verify_chain()
    assert ok, reason
    assert any(e.event_type == "SHADOW_QUANT" and e.week == HOLIDAY and
               e.payload_hash == sha256_obj({"sha256": sha256_file(path)})
               for e in rt.book.audit.events())


def test_full_driver_early_close_fills_and_costs_use_actual_shares(calendar_driver):
    rt, _, _, raw, _ = calendar_driver
    cfg, cap = rt.cfg, rt.cfg.execution.capacity
    j = janela_execucao(EARLY, cfg)
    closing = datetime.combine(EARLY, time(13), tzinfo=NY).astimezone(BRT)
    assert closing.time() == time(15)
    assert j.fechamentos["XNYS"].astimezone(BRT) == closing
    assert j.prazo_decisao == closing - timedelta(minutes=cfg.execution.decision_buffer_minutes)
    assert j.prazo_decisao.time() == time(14, 15)
    md = rt.store.load(as_of=EARLY)
    # Conferir capacidade de toda a seção transversal, incluindo linhas BR/NYSE
    # que o otimizador pode não escolher, para não depender só do alvo espontâneo.
    table = tabela_capacidade(raw.universe.lines, md, j, cfg, lado="long", volume="realizado")
    categories = set()
    for tk, line in raw.universe.lines.iterrows():
        if tk.endswith(".SA"):
            category, early = "BR", 1.
        elif line["line_type"] in ("ADR", "US_LISTED"):
            category = "ADR" if line["line_type"] == "ADR" else "US_STOCK"
            early = cap.early_close_multiplier
        else:
            continue
        currency = str(line["currency"])
        fx = 1. if currency == "USD" else float(raw.fx.at[pd.Timestamp(EARLY), currency])
        v = float(raw.volume.at[pd.Timestamp(EARLY), tk])
        price = float(raw.close.at[pd.Timestamp(EARLY), tk])
        if not all(math.isfinite(x) and x > 0 for x in (v, price, fx)):
            # A ausência nos bytes é conservada; zero é apenas a capacidade
            # permissível, nunca substituição de preço/volume/câmbio ausente.
            assert table.at[tk, "capacidade_usd"] == 0.
            assert table.at[tk, "motivo"]
            continue
        fraction = cap.auction_participation * cap.auction_share[category] + (
            cap.preclose_participation * cap.preclose_volume_share)
        expected = v * price * fx * fraction * early
        assert table.at[tk, "capacidade_usd"] == pytest.approx(expected)
        assert table.at[tk, "multiplicador"] == early
        categories.add(category)
    assert "BR" in categories and "ADR" in categories
    prev, record = rt.track().get(date(2026, 11, 26)), rt.track().get(EARLY)
    old, filled = shares(prev.positions), shares(record.positions)
    proposal = rt.book.load_proposal(EARLY)
    targets = {(p.issuer_id, p.execution_ticker): int(p.shares) for p in proposal.positions if p.shares}
    checked = partial = 0
    trades = []
    for key in sorted(set(old) | set(filled)):
        iid, tk = key
        delta = filled.get(key, 0) - old.get(key, 0)
        if not delta:
            continue
        line = raw.universe.lines.loc[tk]
        currency = str(line["currency"])
        price = float(raw.close.at[pd.Timestamp(EARLY), tk])
        fx = 1. if currency == "USD" else float(raw.fx.at[pd.Timestamp(EARLY), currency])
        assert math.isfinite(price) and price > 0 and math.isfinite(fx) and fx > 0
        trades.append((iid, tk, currency, abs(delta) * price * fx, delta, price))
        if currency != "USD":
            continue
        category = "ADR" if line["line_type"] == "ADR" else "US_STOCK"
        desired = targets.get(key, 0) - old.get(key, 0)
        multiplier = cap.short_multiplier if targets.get(key, 0) < 0 and desired < 0 else 1.
        fraction = cap.auction_participation * cap.auction_share[category] + (
            cap.preclose_participation * cap.preclose_volume_share)
        limit = math.floor(float(raw.volume.at[pd.Timestamp(EARLY), tk]) * fraction *
                           cap.early_close_multiplier * multiplier + 1e-9)
        expected = (1 if desired > 0 else -1) * min(abs(desired), limit)
        assert delta == expected, (key, old.get(key, 0), targets.get(key, 0), delta, expected)
        partial += abs(delta) < abs(desired)
        checked += 1
    assert checked > 0 and partial > 0 and trades
    runner = DailyRunner(cfg, rt.store, rt.book, rt.track())
    ctx = runner.context(EARLY, md, prev, need_models=False)
    frame = runner.custo_frame(ctx, trades)
    # Fórmula independente, usando insumos públicos compartilhados e alocações
    # reais. Nunca calcula custo sobre o delta desejado não preenchido.
    total = 0.
    for _, row in frame.iterrows():
        q, adtv = float(row["notional_usd"]), float(row["adtv_usd"])
        tier = 1 + sum(adtv < b for b in cfg.costs.tier_adtv_breaks_usd)
        half = cfg.costs.half_spread_bps_by_tier[f"T{tier}"]
        if row["local_fechado"]:
            half *= cfg.execution.closed_home_market_spread_mult
        market = row["market"]
        minimum = cfg.costs.min_order_cost_usd.get(market, max(cfg.costs.min_order_cost_usd.values()))
        commission = max(cfg.costs.commission_bps[market], float(row["n_ordens"]) * minimum / q * 1e4)
        fx_bps = 0. if row["currency"] == "USD" else cfg.costs.fx_cost_bps
        impact = cfg.costs.impact_coefficient * float(row["sigma_d"]) * math.sqrt(q / adtv)
        impact *= cfg.execution.close_impact_discount[row["categoria"]] * 1e4
        total += q * (half + commission + fx_bps + impact) / 1e4
    assert total > 0 and record.pnl_components["costs"] == pytest.approx(-total, abs=1e-8)
