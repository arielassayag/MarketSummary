"""DADOS SIMULADOS: decisão natural, MOC, custo autenticado e recuperação offline."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cdp.backtest.replay import run_replay, verify_replay
from cdp.config import FundConfig, load_config
from cdp.data.snapshot import write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.workflow import risco_diario
from cdp.workflow.contrato_custos import (
    DIAGNOSTIC_KEY,
    RECORD_MARKER,
    digest,
    verify,
    verify_record,
)
from cdp.workflow.runtime import Runtime

ROOT = Path(__file__).resolve().parents[2]
DAY = date(2026, 11, 13)


def inventory(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def runtime(out):
    cfg = FundConfig.model_validate_json((out / 'inputs/fund_ensaio.json').read_text())
    return Runtime(cfg=cfg, book_root=out / 'book', market_root=out / 'market',
                   reports_root=out / 'reports', teses_root=None,
                   clock=lambda: datetime(2026, 11, 13, 23, tzinfo=UTC))


@pytest.fixture(scope='module')
def natural_episode(tmp_path_factory):
    workspace = tmp_path_factory.mktemp('custos-simulados')
    raw = workspace / 'inputs'
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=DAY)
    write_snapshot(md, raw)
    cfg = load_config(ROOT / 'configs/cdp/fund.yaml')
    out = workspace / '.cdp/ensaios/novo'
    result = run_replay(raw, out, start=DAY, end=DAY, mode='simulado', cfg=cfg,
                        workspace=workspace)
    assert result['integridade']
    rt = runtime(out)
    record = rt.track().get(DAY)
    assert record and len(record.positions) == 29 and abs(record.pnl_components['costs']) > 0
    return workspace, raw, out, cfg


def test_natural_booking_payload_matches_independent_floor_and_readers_do_not_write(natural_episode):
    _, _, out, _ = natural_episode
    rt = runtime(out)
    before = inventory(out)
    rec = rt.track().get(DAY)
    diag = risco_diario.load(rt.track(), rec)[DIAGNOSTIC_KEY]
    fixture = json.loads((Path(__file__).parent / 'fixtures/custo_minimo_reserva.json').read_text())
    row = diag['frame']['SMX06.MX']
    got = diag['result']['SMX06.MX']['commission_bps'] * row['notional_usd'] / 1e4
    assert got == pytest.approx(float(fixture['row']['commission_sum_individual_order_floors_usd']),
                               abs=1e-10)
    assert [p['acoes'] for p in row['ordens']] == [24800, 12]
    assert row['acoes_executadas'] == 24812
    assert verify(rt) == []
    assert verify_replay(out)['integridade']
    assert inventory(out) == before


@pytest.mark.parametrize('mutate', ['remove_diagnostic', 'commission', 'shares', 'price',
                                   'proposal_contract', 'market_fx'])
def test_physical_tamper_refused_readonly(natural_episode, tmp_path, mutate):
    _, _, original, _ = natural_episode
    out = tmp_path / 'clone'
    shutil.copytree(original, out)
    diag = out / 'book/track_record/risco_diario/2026-11-13.json'
    if mutate == 'remove_diagnostic':
        diag.unlink()
    elif mutate in ('commission', 'shares', 'price'):
        obj = json.loads(diag.read_text())
        cost = obj[DIAGNOSTIC_KEY]
        if mutate == 'commission':
            cost['result']['SMX06.MX']['commission_bps'] = 8
        elif mutate == 'shares':
            cost['frame']['SMX06.MX']['acoes_executadas'] += 1
        else:
            cost['frame']['SMX06.MX']['preco_local'] += 1
        diag.write_text(json.dumps(obj))
    elif mutate == 'proposal_contract':
        p = out / 'book/2026-11-13/proposal_v1.json'
        obj = json.loads(p.read_text())
        obj['overrides']['execution_cost_contract']['commission'] = 'unknown'
        p.write_text(json.dumps(obj))
    else:
        p = out / 'market/base/2026-11-13/fx.parquet'
        # Adulteração física de bytes, sem inventar um recibo novo.
        p.write_bytes(p.read_bytes() + b'changed')
    before = inventory(out)
    rt = runtime(out)
    ok, _ = rt.verify_all()
    assert not ok
    assert inventory(out) == before


@pytest.mark.parametrize('field', ['commission', 'decomposition', 'cost_total'])
def test_rederivation_refuses_wrong_arithmetic_even_given_matching_payload_sha(
        natural_episode, monkeypatch, field):
    # Unidade da camada de rederivação: simula uma autoridade de custódia que aceitou um
    # envelope. Não substitui o teste físico de adulteração/trilha acima.
    _, _, out, _ = natural_episode
    rt = runtime(out)
    rec = rt.track().get(DAY)
    proposal = rt.book.load_proposal(DAY)
    obj = copy.deepcopy(risco_diario.load(rt.track(), rec))
    cost = obj[DIAGNOSTIC_KEY]
    if field == 'commission':
        cost['result']['SMX06.MX']['commission_bps'] = 8
    elif field == 'decomposition':
        cost['frame']['SMX06.MX']['nocionais_ordens_usd'] = [cost['frame']['SMX06.MX']['notional_usd']]
    else:
        cost['cost_usd'] -= 1
    modified = rec.model_copy(deep=True)
    modified.input_hashes[RECORD_MARKER] = digest(cost)
    monkeypatch.setattr(risco_diario, 'load', lambda *_a, **_k: obj)
    errors = verify_record(rt, rt.track(), modified, None, proposal)
    assert any('reextração' in x for x in errors)


def test_missing_new_obligation_is_explicit(natural_episode, monkeypatch):
    _, _, out, _ = natural_episode
    rt = runtime(out)
    rec = rt.track().get(DAY).model_copy(deep=True)
    proposal = rt.book.load_proposal(DAY)
    obj = copy.deepcopy(risco_diario.load(rt.track(), rec))
    obj.pop(DIAGNOSTIC_KEY)
    rec.input_hashes.pop(RECORD_MARKER)
    monkeypatch.setattr(risco_diario, 'load', lambda *_a, **_k: obj)
    assert verify_record(rt, rt.track(), rec, None, proposal) == [
        'efetivação nova sem cálculo de custo autenticado']


def test_crash_after_booking_before_append_recovers_exactly_once(natural_episode, monkeypatch):
    workspace, raw, _, cfg = natural_episode
    out = workspace / '.cdp/ensaios/interrompido'
    original_append = risco_diario.append

    def fail_before_append(*_args, **_kwargs):
        raise RuntimeError('interrupção simulada entre booking e custo/record')

    with monkeypatch.context() as patch:
        patch.setattr(risco_diario, 'append', fail_before_append)
        with pytest.raises(RuntimeError, match='interrupção simulada'):
            run_replay(raw, out, start=DAY, end=DAY, mode='simulado', cfg=cfg, workspace=workspace)
    rt = runtime(out)
    assert rt.book.load_booked(DAY) is not None
    assert rt.track().get(DAY) is None
    assert any('pendente' in msg for msg in verify(rt))
    assert risco_diario.append is original_append
    result = run_replay(raw, out, start=DAY, end=DAY, mode='simulado', cfg=cfg,
                        workspace=workspace, resume=True)
    assert result['integridade']
    rec = rt.track().get(DAY)
    assert rec and RECORD_MARKER in rec.input_hashes
    before = inventory(out)
    assert run_replay(raw, out, start=DAY, end=DAY, mode='simulado', cfg=cfg,
                      workspace=workspace, resume=True) == result
    assert inventory(out) == before
    assert len([e for e in rt.book.audit.events() if e.event_type == 'BOOKED']) == 1


def test_crash_after_cost_payload_and_prepared_seal_recovers_without_rewriting(
        natural_episode, monkeypatch):
    from cdp.workflow.track_record import TrackRecord

    workspace, raw, _, cfg = natural_episode
    out = workspace / '.cdp/ensaios/preparado-interrompido'
    original_append = TrackRecord.append

    def fail_before_record(self, _record):
        if self.root.name == 'track_record':
            raise RuntimeError('interrupção simulada após selo do custo antes do record')
        return original_append(self, _record)

    with monkeypatch.context() as patch:
        patch.setattr(TrackRecord, 'append', fail_before_record)
        with pytest.raises(RuntimeError, match='após selo do custo'):
            run_replay(raw, out, start=DAY, end=DAY, mode='simulado', cfg=cfg, workspace=workspace)
    rt = runtime(out)
    assert rt.book.load_booked(DAY) is not None and rt.track().get(DAY) is None
    p = risco_diario.path(rt.track(), DAY)
    raw_payload = p.read_bytes()
    assert DIAGNOSTIC_KEY in json.loads(raw_payload)
    assert len([e for e in rt.track().audit.events()
                if e.event_type == risco_diario.PREPARED_EVENT]) == 1
    assert TrackRecord.append is original_append
    result = run_replay(raw, out, start=DAY, end=DAY, mode='simulado', cfg=cfg,
                        workspace=workspace, resume=True)
    assert result['integridade'] and verify(rt) == []
    assert p.read_bytes() == raw_payload
    assert len(rt.track().records()) == 1
    assert len([e for e in rt.track().audit.events()
                if e.event_type == risco_diario.PREPARED_EVENT]) == 1
    assert len([e for e in rt.book.audit.events() if e.event_type == 'BOOKED']) == 1
