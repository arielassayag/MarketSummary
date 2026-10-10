"""DADOS SIMULADOS: decisão natural, MOC, custo autenticado e recuperação offline."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from cdp.audit import AuditLog
from cdp.backtest.replay import run_replay, verify_replay
from cdp.config import FundConfig, load_config
from cdp.data.snapshot import write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.workflow import risco_diario
from cdp.workflow.book import REGRA_CADUCIDADE
from cdp.workflow.contrato_custos import (
    DIAGNOSTIC_KEY,
    RECORD_MARKER,
    digest,
    verify,
    verify_record,
)
from cdp.workflow.daily import DailyRunner, book_execution
from cdp.workflow.net_moc import RECORD_MARKER as NET_MARKER
from cdp.workflow.net_moc_prova import load as load_net
from cdp.workflow.net_moc_prova import recover as recover_net
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
    native_run = DailyRunner.run_session
    preflight = []

    def with_native_preflight(self, session, *args, **kwargs):
        if session == DAY and self.track.last() is None:
            # Mesmo plano natural. Exercita a API de dry_run sem I/O e a API
            # execute_decision antes de o fechamento adotar os corpos preparados.
            ctx = self.context(session)
            plan = self._discover_plan(session, session)
            assert plan is not None
            candidate = self._prepare_side(self.main, ctx, None, plan)
            before = inventory(self.book.root)
            book_execution(self.book, candidate.entry, plan.proposal, plan.decision, self.cfg,
                           dry_run=True)
            assert inventory(self.book.root) == before
            native_append = AuditLog.append

            def before_booked_event(audit, event_type, *a, **k):
                if event_type == 'BOOKED':
                    raise RuntimeError('DADOS SIMULADOS: interrupção após arquivo BOOKED')
                return native_append(audit, event_type, *a, **k)

            with patch.object(AuditLog, 'append', before_booked_event):
                with pytest.raises(RuntimeError, match='após arquivo BOOKED'):
                    self.execute_decision(session, plan.proposal, plan.decision)
            assert recover_net(self.book.root, session).state == 'booked_pending_event'
            # Recalibração posterior altera o hash e o parâmetro econômico do
            # mandato atual; fechar só o evento recebe a configuração ORIGINAL.
            changed = self.cfg.model_copy(update={
                'costs': self.cfg.costs.model_copy(update={
                    'fx_cost_bps': self.cfg.costs.fx_cost_bps + 1})})
            assert changed.config_hash() != self.cfg.config_hash()
            own_cfg = self.book.config
            self.book.config = changed
            try:
                self.book.recover_booking(session)
            finally:
                self.book.config = own_cfg
            got = self.execute_decision(session, plan.proposal, plan.decision)
            assert got == candidate.entry and got.positions
            assert recover_net(self.book.root, session).state == 'booked'
            preflight.append(session)
            def before_shadow_booked_event(audit, event_type, *a, **k):
                if event_type == 'BOOKED_SHADOW':
                    raise RuntimeError('DADOS SIMULADOS: interrupção após BOOKED_SHADOW')
                return native_append(audit, event_type, *a, **k)

            with patch.object(AuditLog, 'append', before_shadow_booked_event):
                with pytest.raises(RuntimeError, match='após BOOKED_SHADOW'):
                    native_run(self, session, *args, **kwargs)
            assert recover_net(self.book.root, session, 'shadow').state == 'booked_pending_event'
            # A adoção main/sombra também recebe os corpos econômicos selados
            # sob a configuração anterior; não prepara outra receita/custo.
            runner_cfg = self.cfg
            self.cfg = self.book.config = changed
            try:
                self.shadow.store.recover_booking(session)
                result = native_run(self, session, *args, **kwargs)
                assert result.record.nav_end_usd == recover_net(self.book.root, session).record.nav_end_usd
                assert result.shadow == recover_net(self.book.root, session, 'shadow').record
                return result
            finally:
                self.cfg, self.book.config = runner_cfg, own_cfg
        return native_run(self, session, *args, **kwargs)

    with patch.object(DailyRunner, 'run_session', with_native_preflight):
        result = run_replay(raw, out, start=DAY, end=DAY, mode='simulado', cfg=cfg,
                            workspace=workspace)
    assert result['integridade']
    rt = runtime(out)
    record = rt.track().get(DAY)
    assert preflight == [DAY]
    assert record and len(record.positions) == 29 and abs(record.pnl_components['costs']) > 0
    return workspace, raw, out, cfg


def test_net_nativo_d0_d1_bound_historico_e_carry_sem_nova_autorizacao(natural_episode, tmp_path):
    workspace, _, original, _ = natural_episode
    out = tmp_path / 'carry-historico'
    shutil.copytree(original, out)
    rt = runtime(out)
    d0 = rt.track().get(DAY)
    assert d0.risk.n_long > 0 and d0.risk.n_short > 0 and d0.input_hashes[NET_MARKER]
    assert recover_net(rt.book_root, DAY).state == 'bound'
    assert load_net(rt.track(), d0)['net']['passed']
    shadow0 = rt.track(shadow=True).get(DAY)
    assert shadow0 and shadow0.input_hashes[NET_MARKER]
    assert recover_net(rt.book_root, DAY, 'shadow').state == 'bound'
    assert d0.input_hashes['shadow_record'] == shadow0.record_hash
    proof = out / f'book/net_moc/v1/main/{DAY}/{DAY}/base.json'
    base = json.loads(proof.read_text())
    assert 'NaN' in base['proposal_json']  # sete stress ausentes preservados literalmente

    # Hipótese fixa para D1: carry literal das barras D0, em outra base sintética.
    # Nenhum retorno, preço, sinal, seed ou mandato é escolhido pelo resultado.
    d1 = date(2026, 11, 16)
    md = rt.store.load(DAY)

    def carried(frame):
        new = frame.copy(deep=True)
        new.loc[pd.Timestamp(d1)] = frame.loc[pd.Timestamp(DAY)]
        return new

    fields = {name: carried(getattr(md, name)) for name in
              ('close', 'adj_close', 'volume', 'fx', 'benchmarks', 'rates')}
    manifest = md.manifest.model_copy(update={
        'as_of': d1, 'snapshot_id': md.manifest.snapshot_id + '-carry-d1', 'files': [],
        'limitations': [*md.manifest.limitations,
                        'DADOS SIMULADOS: D1 conserva literalmente barras D0 como hipótese fixa.']})
    d1_raw = workspace / 'inputs-d1-carry'
    write_snapshot(replace(md, manifest=manifest, **fields), d1_raw)
    rt.store.init_base(d1_raw)
    runner = DailyRunner.from_root(rt.cfg, rt.store, rt.book_root, with_shadow=True)
    got = runner.run_session(d1)
    assert got.booked is None and got.shadow_booked is None
    assert got.record.prev_record_hash == d0.record_hash
    assert NET_MARKER not in got.record.input_hashes
    assert len(got.record.positions) == len(d0.positions)
    assert got.record.pnl_components['costs'] == 0
    assert got.record.pnl_components['borrow'] < 0
    assert got.record.nav_start_usd == d0.nav_end_usd
    assert load_net(rt.track(), d0)['net']['passed']
    recovered = recover_net(rt.book_root, DAY)
    assert recovered.state == 'bound' and recovered.record == d0
    assert runner.verify_all()[0]


def test_net_fail_nativo_caduca_sem_kill_e_nao_efetiva_depois(natural_episode):
    """Mandato negativo fixo antes do modelo: NET exatamente zero, demais campos iguais.

    Hipótese de teste mais restritiva; não procura seed/resultado nem afrouxa gate.
    Usa o mesmo snapshot público sintético inteiro, em outro livro nativo vazio.
    """
    workspace, raw, _, cfg = natural_episode
    strict = cfg.model_copy(update={
        'risk': cfg.risk.model_copy(update={'net_exposure_max_abs': 0.0})})
    before, after = cfg.model_dump(mode='json'), strict.model_dump(mode='json')
    before['risk'].pop('net_exposure_max_abs')
    after['risk'].pop('net_exposure_max_abs')
    assert before == after
    out = workspace / '.cdp/ensaios/net-zero-negativo'
    result = run_replay(raw, out, start=DAY, end=DAY, mode='simulado', cfg=strict,
                        workspace=workspace)
    assert result['integridade']
    rt = runtime(out)
    lapsed = rt.book.efetivacao_recusada(DAY)
    assert lapsed and lapsed['regra'] == REGRA_CADUCIDADE and 'NET FAIL' in lapsed['motivo']
    assert not rt.kill_switch_active() and rt.book.load_booked(DAY) is None
    rec = rt.track().get(DAY)
    assert rec and not rec.positions and rec.pnl_components['costs'] == 0
    assert all('kill switch ligado' not in text for text in rec.alerts)
    runner = DailyRunner.from_root(rt.cfg, rt.store, rt.book_root, with_shadow=True)
    proposal = rt.book.load_proposal(DAY)
    decision = rt.book.load_decision(DAY)
    with pytest.raises(ValueError, match='caduc|execut|janela|fechamento'):
        runner.execute_decision(date(2026, 11, 16), proposal, decision)
    assert rt.book.load_booked(DAY) is None


def test_hold_nativo_com_origem_propria_preflight_e_bound_sem_ordens(natural_episode, tmp_path):
    """Rota HOLD escolhida antes da chamada, sem solver, insumo financeiro ou PASS do teste.

    O gerador nativo recebe o contexto integral do mercado fixo do ensaio. Este
    caso verifica seu contrato de escrita; não declara que o modelo escolheu HOLD.
    """
    from cdp.data.store import MarketStore
    from cdp.hashing import combine_hashes, sha256_file
    from cdp.research.pm_agent import load_week_inputs, pm_factbook, to_bundle
    from cdp.workflow.autonomy import make_autonomous_decision
    from cdp.workflow.demo import write_demo_inputs
    from cdp.workflow.origem import ReplayOrigin, install_replay_origin
    from cdp.workflow.weekly import hold_proposal

    _, raw, original, _ = natural_episode
    cfg = runtime(original).cfg  # configuração integral do próprio ensaio, não cfg atual
    out = tmp_path / 'hold-nativo'
    store = MarketStore(out / 'market', cfg=cfg)
    store.init_base(raw)
    now = datetime(2026, 11, 13, 17, tzinfo=UTC)
    rt = Runtime(cfg, out / 'book', out / 'market', out / 'reports',
                 store_override=store, teses_root=None, clock=lambda: now)
    # Manifesto específico e explícito deste teste de protocolo, não replay
    # completo nem pré-registro econômico real. Ambas âncoras são bytes físicos.
    origin_path = out / 'hold_test_manifest.json'
    origin_path.write_text(json.dumps({
        'aviso': 'DADOS SIMULADOS: teste da rota nativa HOLD, escolhida antes da chamada.',
        'config_hash': cfg.config_hash(), 'source_manifest_sha256': sha256_file(raw / 'manifest.json'),
        'generator_sha256': sha256_file(Path(__file__).parents[2] / 'src/cdp/workflow/weekly.py'),
        'test_sha256': sha256_file(Path(__file__))}, sort_keys=True))
    install_replay_origin(rt.book, ReplayOrigin(
        mode='simulado', actual_started_at=datetime.now(UTC),
        run_manifest_sha256=sha256_file(origin_path),
        source_manifest_sha256=sha256_file(raw / 'manifest.json')))
    rt.weekly_prepare(DAY, live=False, mind='demo')
    write_demo_inputs(rt, DAY)
    _, _, ctx, _, pmctx = rt._week_state(DAY)
    pack, output, _, pmctx = load_week_inputs(rt.week_dir(DAY), pmctx, now=now)
    bundle = to_bundle(output, cfg, pmctx.drawdown, factbook=pm_factbook(pmctx))
    research_hash = combine_hashes(pack.research_hash(), bundle.pm_output_hash)
    proposal = hold_proposal(ctx, research_hash, 1,
                             'DADOS SIMULADOS: teste declarado da rota manter em caixa.',
                             created_at=now)
    rt.book.save_research_pack(pack, actor='demo')
    rt.book.save_proposal(proposal)
    decision = make_autonomous_decision(
        proposal, research_hash=research_hash, pm_decision_hash=bundle.pm_output_hash,
        rationale='DADOS SIMULADOS: recepção da rota HOLD nativa sem negociação.',
        journal=bundle.journal, decided_at=now, audit_head_hash=rt.book.audit_head()).model_copy(
            update={'mind': 'demo'})
    rt.book.save_decision(decision)
    runner = DailyRunner.from_root(cfg, store, rt.book_root, with_shadow=False)
    context = runner.context(DAY)
    plan = runner._discover_plan(DAY, DAY)
    candidate = runner._prepare_side(runner.main, context, None, plan)
    before = inventory(out)
    book_execution(runner.book, candidate.entry, proposal, decision, cfg, dry_run=True)
    assert inventory(out) == before
    booked = runner.execute_decision(DAY, proposal, decision)
    assert booked.positions == []
    result = runner.run_session(DAY)
    assert result.record.positions == [] and result.record.pnl_components['costs'] == 0
    assert result.record.nav_start_usd == result.record.nav_end_usd == cfg.fund.inception_nav_usd
    assert load_net(runner.track, result.record)['net']['passed']
    assert recover_net(rt.book_root, DAY).state == 'bound'
    assert runner.verify_all()[0]


def test_natural_booking_payload_matches_independent_floor_and_readers_do_not_write(natural_episode):
    _, _, out, _ = natural_episode
    rt = runtime(out)
    before = inventory(out)
    rec = rt.track().get(DAY)
    diag = risco_diario.load(rt.track(), rec)[DIAGNOSTIC_KEY]
    md = rt.store.load(DAY)
    positions = {p.ticker: p for p in rec.positions}
    mixed_floors = []
    # Quantidades vêm do MOC natural. O oráculo Decimal usa preço/FX do vintage,
    # ações efetivas e mandato; não chama o kernel de custos nem o divisor de lotes.
    with localcontext() as context:
        context.prec = 50
        for ticker, row in diag['frame'].items():
            orders = row['ordens']
            assert orders and row['n_ordens'] == len(orders)
            assert all(isinstance(p['acoes'], int) and p['acoes'] != 0 for p in orders)
            assert sum(p['acoes'] for p in orders) == positions[ticker].shares
            assert row['acoes_executadas'] == positions[ticker].shares
            price = Decimal.from_float(float(md.close.loc[str(DAY), ticker]))
            # USD/USD=1 é identidade de unidade; moeda local exige observação no pregão.
            fx = (Decimal(1) if row['currency'] == 'USD' else
                  Decimal.from_float(float(md.fx.loc[str(DAY), row['currency']])))
            assert price > 0 and fx > 0
            amounts = [Decimal(abs(p['acoes'])) * price * fx for p in orders]
            rate = Decimal(str(rt.cfg.costs.commission_bps[row['market']])) / Decimal('10000')
            table = rt.cfg.costs.min_order_cost_usd
            floor = Decimal(str(table.get(row['market'], max(table.values()))))
            expected = sum((max(amount * rate, floor) for amount in amounts), Decimal(0))
            assert row['notional_usd'] == pytest.approx(float(sum(amounts)), rel=0, abs=1e-8)
            assert row['nocionais_ordens_usd'] == pytest.approx([float(a) for a in amounts],
                                                              rel=0, abs=1e-8)
            got = diag['result'][ticker]['commission_bps'] * row['notional_usd'] / 1e4
            assert got == pytest.approx(float(expected), rel=0, abs=1e-10)
            aggregate_floor = max(sum(amounts) * rate, len(orders) * floor)
            if (any(amount * rate < floor for amount in amounts) and
                    any(amount * rate > floor for amount in amounts)):
                assert expected > aggregate_floor
                mixed_floors.append(ticker)
    assert mixed_floors, 'episódio deve exercer mínimo individual que difere do agregado'
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
