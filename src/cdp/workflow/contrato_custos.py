"""Contrato prospectivo de comissão: proposta aprovada e insumos MOC autenticados.

A ausência literal de estampa pertence ao schema histórico e escolhe a fórmula agregada
antiga. Nunca se acrescenta estampa a uma proposta/decisão já selada.
"""
from __future__ import annotations

import json
import math
from datetime import date

import pandas as pd

from ..config import FundConfig
from ..hashing import sha256_text

PROPOSAL_KEY = "execution_cost_contract"
RECORD_MARKER = "execution_costs_v1"
DIAGNOSTIC_KEY = "execution_costs"
LEGACY = "aggregate_line/v0"
CURRENT = "individual_orders/v1"
STAMP_V1 = {
    "schema": "cdp.execution_cost_contract/v1",
    "commission": CURRENT,
    "orders": "actual_filled_standard_fractional_peak/v1",
    "spread_impact_fx": "aggregate_line/v0",
    "weekly_estimate": "aggregate_line_approximation/v0",
}
STAMP = {
    "schema": "cdp.execution_cost_contract/v2",
    "commission": CURRENT,
    "orders": "actual_filled_standard_fractional_peak/v1",
    "spread_impact_fx": "aggregate_line/v0",
    "weekly_estimate": "planned_individual_orders/v1",
    "planned_estimate_basis": "trade_shares_notional_current_local_price/v1",
    "included_commission_source": "cost_model_components_rebalance_same_weights/v1",
}


def stamp() -> dict:
    return dict(STAMP)


def descriptor(proposal) -> dict | None:
    """Descritor autenticado DA proposta: ausência antiga não recebe estampa retroativa."""
    if proposal is None or PROPOSAL_KEY not in proposal.overrides:
        return None
    value = proposal.overrides[PROPOSAL_KEY]
    if not isinstance(value, dict) or value not in (STAMP_V1, STAMP):
        raise ValueError("contrato de custos da proposta desconhecido ou malformado")
    return dict(value)


def contract(proposal) -> str:
    if descriptor(proposal) is None:
        return LEGACY
    return CURRENT


def clean(value):
    """JSON com toda a precisão binária disponível; ausência permanece None."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "item"):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def payload(frame: pd.DataFrame, result: pd.DataFrame, proposal, cfg: FundConfig,
            session: date, cost_usd: float) -> dict:
    assert contract(proposal) == CURRENT
    return {
        "schema": "cdp.execution_cost_calculation/v1", "contract": descriptor(proposal),
        "session": str(session), "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash(), "config_hash": cfg.config_hash(),
        "frame": clean(frame.to_dict(orient="index")),
        "result": clean(result.to_dict(orient="index")), "cost_usd": float(cost_usd),
    }


def digest(value: dict) -> str:
    return sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                                 allow_nan=False) + "\n")


def trades_from_records(previous, record, md) -> list[tuple]:
    """Reextrai ações reais e preço/FX do próprio pregão; não usa alvo nem preço de decisão."""
    from ..portfolio.execucao import cambio_do_pregao

    before = {(p.issuer_id, p.ticker): p for p in previous.positions} if previous else {}
    after = {(p.issuer_id, p.ticker): p for p in record.positions}
    ts = pd.Timestamp(record.date)
    rows = []
    for key in sorted(set(before) | set(after)):
        p0, p1 = before.get(key), after.get(key)
        if any(p is not None and p.shares is None for p in (p0, p1)):
            raise ValueError("quantidade observada ausente nos registros dos custos")
        s0 = float(p0.shares) if p0 is not None else 0.0
        s1 = float(p1.shares) if p1 is not None else 0.0
        if not all(math.isfinite(s) and int(s) == s for s in (s0, s1)):
            raise ValueError("quantidade executada ausente ou não inteira")
        q = int(s1 - s0)
        if q == 0:
            continue
        iid, ticker = key
        if ticker not in md.universe.lines.index or ts not in md.close.index:
            raise ValueError("vintage do pregão sem linha/preço dos custos")
        line = md.universe.lines.loc[ticker]
        if str(line["issuer_id"]) != iid:
            raise ValueError("associação emissor/linha diverge nos custos")
        currency = str(line["currency"])
        px = float(md.close.at[ts, ticker])
        fx = cambio_do_pregao(md, currency, record.date)
        if not math.isfinite(px) or px <= 0 or fx is None:
            raise ValueError("preço/FX do próprio pregão indisponível nos custos")
        rows.append((iid, ticker, currency, abs(q) * px * fx, q, px))
    return rows


def _booked(rt, track, week):
    from .daily import ShadowBook

    if week is None:
        return None
    return (rt.book.load_booked(week) if track.root == rt.track().root
            else ShadowBook(track).load_booked(week))


def _booking_date(entry, cfg):
    from zoneinfo import ZoneInfo

    return entry.booked_at.astimezone(ZoneInfo(cfg.fund.timezone)).date()


def verify_record(rt, track, record, previous, proposal) -> list[str]:
    """Reextrai a decomposição pelo vintage e recompõe custos novos; legado não é reescrito."""
    from .daily import DailyRunner
    from .risco_diario import MARKER, load

    try:
        marked = RECORD_MARKER in record.input_hashes
        chosen = contract(proposal)
        entry = _booked(rt, track, record.live_book_week)
        obj = load(track, record) if MARKER in record.input_hashes else None
        saved = obj.get(DIAGNOSTIC_KEY) if obj is not None else None
        if not marked:
            if saved is not None:
                raise ValueError("cálculo prospectivo sem marcador no registro diário")
            if (chosen == CURRENT and entry is not None
                    and _booking_date(entry, rt.cfg) == record.date):
                raise ValueError("efetivação nova sem cálculo de custo autenticado")
            return []
        if chosen != CURRENT or obj is None or entry is None:
            raise ValueError("marcador de custo sem proposta/efetivação/diagnóstico prospectivo")
        if not isinstance(saved, dict) or digest(saved) != record.input_hashes[RECORD_MARKER]:
            raise ValueError("cálculo de custo ausente ou SHA divergente")
        cfg = FundConfig.model_validate(obj["config"])
        if _booking_date(entry, cfg) != record.date or entry.proposal_id != proposal.proposal_id:
            raise ValueError("custo não pertence ao pregão/proposta da efetivação")
        if cfg.config_hash() != proposal.config_hash:
            raise ValueError("mandato do custo diverge da proposta aprovada")
        if record.input_hashes.get("proposal") != proposal.proposal_hash():
            raise ValueError("proposta do custo diverge do registro diário")
        md = rt.store.load(as_of=record.date).truncate(record.date)
        runner = DailyRunner(cfg, rt.store, rt.book, track)
        ctx = runner.context(record.date, md, previous, need_models=False)
        rows = trades_from_records(previous, record, md)
        frame, result, total = runner._closing_cost_calculation(ctx, rows, proposal)
        recomputed = payload(frame, result, proposal, cfg, record.date, total)
        if recomputed != saved:
            raise ValueError("custos por ordem divergem da reextração do vintage")
        debit = -float(record.pnl_components["costs"])
        if not math.isclose(total, debit, rel_tol=0.0, abs_tol=1e-8):
            raise ValueError("débito diverge do custo rederivado por ordem")
        return []
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        return [str(exc)]


def verify(rt, *, include_shadow: bool = True) -> list[str]:
    from .daily import ShadowBook

    problems = []
    for shadow in ((False, True) if include_shadow else (False,)):
        track = rt.track(shadow)
        records = sorted(track.records(), key=lambda r: r.date)
        previous = None
        weeks = ShadowBook(track).weeks() if shadow else rt.book.list_weeks()
        for week in weeks:
            try:
                entry = _booked(rt, track, week)
                p = (ShadowBook(track).load_proposal(week) if shadow else
                     next((p for p in rt.book.list_proposals(week)
                           if entry is not None and p.proposal_id == entry.proposal_id), None))
                if (entry is not None and contract(p) == CURRENT
                        and not any(r.date == _booking_date(entry, rt.cfg)
                                    and r.live_book_week == week for r in records)):
                    problems.append(f"{week} {'sombra' if shadow else 'efetivo'}: "
                                    "efetivação prospectiva pendente de registro/custo diário")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                problems.append(f"{week}: {exc}")
        for record in records:
            try:
                if record.live_book_week is None:
                    proposal = None
                elif shadow:
                    proposal = ShadowBook(track).load_proposal(record.live_book_week)
                else:
                    entry = rt.book.load_booked(record.live_book_week)
                    proposal = next((p for p in rt.book.list_proposals(record.live_book_week)
                                     if entry is not None and p.proposal_id == entry.proposal_id), None)
                errs = verify_record(rt, track, record, previous, proposal)
            except (ValueError, TypeError, KeyError) as exc:
                errs = [str(exc)]
            problems += [f"{record.date} {'sombra' if shadow else 'efetivo'}: {e}" for e in errs]
            previous = record
    return problems
