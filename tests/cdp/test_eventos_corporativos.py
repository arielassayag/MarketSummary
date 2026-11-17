"""Eventos corporativos: não confundir mudança de unidade com resultado econômico."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cdp.data.store import DataNotReadyError, _combine_prices


def prices(value, day):
    return pd.DataFrame([{'date': pd.Timestamp(day), 'ticker': 'EMBJ', 'close': value,
                          'adj_close': value, 'volume': 1000.0}])


def test_missing_adjusted_basis_cannot_create_gain_on_split():
    base = prices(78.73, '2026-11-13')
    inc = prices(18.77, '2026-11-16').assign(
        prev_date=pd.Timestamp('2026-11-13'), prev_close_window=np.nan,
        prev_adj_close_window=np.nan)
    with pytest.raises(DataNotReadyError, match='evento corporativo'):
        _combine_prices(base, [inc])


@pytest.mark.parametrize('factor,old,new,want', [
    (4.0, 80.0, 19.0, -.05), (.1, 8.0, 76.0, -.05), (2.0, 80.0, 42.0, .05)])
def test_verified_event_adjusts_only_missing_basis(factor, old, new, want):
    from cdp.data.eventos_corporativos import CorporateAction
    event = CorporateAction(ticker='EMBJ', effective_on=date(2026,11,16),
        announced_on=date(2026,10,30), quantity_factor=factor,
        source_url='https://www.sec.gov/example', evidence_sha256='a'*64)
    base = prices(old, '2026-11-13')
    inc = prices(new, '2026-11-16').assign(
        prev_date=pd.Timestamp('2026-11-13'), prev_close_window=np.nan,
        prev_adj_close_window=np.nan)
    got = _combine_prices(base, [inc], actions=(event,))
    assert got.adj_close.pct_change().iloc[-1] == pytest.approx(want)
    # Ajustado na origem: nunca aplicar o fator outra vez.
    inc['prev_adj_close_window'] = old / factor
    inc['prev_close_window'] = old / factor
    got = _combine_prices(base, [inc], actions=(event,))
    assert got.adj_close.pct_change().iloc[-1] == pytest.approx(want)


def test_rectification_preserves_original_and_next_day_uses_corrected_tail(tmp_path):
    from test_daily_track_record import _chain

    from cdp.workflow.retificacao_financeira import seal
    from cdp.workflow.track_record import TrackRecord
    track = TrackRecord(tmp_path / 'book/track_record')
    _chain(track, [(date(2026,10,5), .01, 0.0), (date(2026,10,6), .02, 0.0)])
    original = track.last()
    path = track.record_path(original.date)
    raw, csv = path.read_bytes(), track.csv_path.read_bytes()
    candidate = original.model_copy(update={'nav_end_usd': 101000000.0,
        'pnl_usd': 0.0, 'ret': 0.0, 'pnl_components': {'equity': 0.0, 'financing':0.0,
        'borrow':0.0,'costs':0.0}, 'attribution': [], 'record_hash':''})
    candidate = candidate.model_copy(update={'record_hash':candidate.compute_hash()})
    seal(track, original, candidate, None, ())
    assert path.read_bytes() == raw
    assert track.csv_path.read_bytes() == csv
    assert track.last().nav_end_usd == 101000000.0
    assert track.frame().iloc[-1]['nav'] == 101000000.0
    assert track.verify()[0], track.verify()[1]
    # Repetição literal é idempotente.
    n = len(track.audit.events())
    seal(track, original, candidate, None, ())
    assert len(track.audit.events()) == n
    nxt = candidate.model_copy(update={'date':date(2026,10,7),
        'nav_start_usd':101000000.0, 'nav_end_usd':102010000.0,
        'pnl_usd':1010000.0, 'ret':.01, 'pnl_components':{'equity':1010000.0},
        'prev_record_hash':candidate.record_hash})
    nxt = nxt.model_copy(update={'record_hash':nxt.compute_hash()})
    track.append(nxt)
    assert track.verify()[0], track.verify()[1]
    assert track.last().nav_start_usd == 101000000.0


def test_rectification_tampering_or_removal_blocks_current_view(tmp_path):
    from test_daily_track_record import _chain

    from cdp.workflow.retificacao_financeira import seal
    from cdp.workflow.track_record import TrackRecord
    track = TrackRecord(tmp_path / 'book/track_record')
    _chain(track, [(date(2026,10,5), .01, 0.0)])
    rec = track.last()
    seal(track, rec, rec, None, ())
    correction = track.root / 'retificacoes' / str(rec.date) / 'registro.json'
    correction.write_text('{}')
    with pytest.raises(ValueError):
        track.last()
    correction.unlink()
    with pytest.raises(ValueError):
        track.last()


@pytest.mark.parametrize('side,shares,mv,want_pnl', [
    ('LONG',10.0,800.0,-40.0), ('SHORT',-10.0,-800.0,40.0)])
def test_mark_changes_quantity_without_inventing_trading_profit(side, shares, mv, want_pnl):
    from types import SimpleNamespace

    from cdp.config import FundConfig
    from cdp.contracts import DailyPosition, DailyRecord, DailyRisk
    from cdp.data.eventos_corporativos import CorporateAction
    from cdp.workflow.daily import DailyRunner
    day, before = date(2026,11,16), date(2026,11,13)
    event = CorporateAction(ticker='EMBJ', effective_on=day, announced_on=date(2026,10,30),
        quantity_factor=4,source_url='https://www.sec.gov/example', evidence_sha256='a'*64)
    prev = DailyRecord(date=before,fund_name='CDP',track_record_type='paper trading',
        nav_start_usd=10000,nav_end_usd=10000,pnl_usd=0,ret=0,prev_record_hash='0'*64,
        is_synthetic=True,data_notice='DADOS SIMULADOS',
        positions=[DailyPosition(issuer_id='X',ticker='EMBJ',currency='USD',side=side,
            shares=shares,price_local=80,price_usd=80,market_value_usd=mv,
            weight=mv/10000,day_pnl_usd=0)],
        risk=DailyRisk(gross=.08,net=mv/10000,long_exposure=0,short_exposure=0,n_long=0,n_short=0))
    md = SimpleNamespace(corporate_actions=(event,),unverified_returns=(),
        close=pd.DataFrame({'EMBJ':[19.0]},index=[pd.Timestamp(day)]),
        rates=pd.DataFrame({'USD_3M':[0.0]},index=[pd.Timestamp(before)]))
    ctx=SimpleNamespace(date=day,ts=pd.Timestamp(day),md=md,
        panel=SimpleNamespace(line_returns=pd.DataFrame({'EMBJ':[-.05]},index=[pd.Timestamp(day)])))
    runner=SimpleNamespace(cfg=FundConfig(),_fx_rate=lambda *args:1.0,
        _borrow_fee=lambda *args:(0.0,'proposta'))
    marked=DailyRunner._mark(runner,ctx,prev,None)
    assert marked.lines[0].shares == shares*4
    assert marked.lines[0].pnl == pytest.approx(want_pnl)
    md.corporate_actions=()
    with pytest.raises(ValueError,match='evento corporativo'):
        DailyRunner._mark(runner,ctx,prev,None)
    md.unverified_returns=((day,'EMBJ'),)
    with pytest.raises(ValueError,match='barra ajustada'):
        DailyRunner._mark(runner,ctx,prev,None)


def test_adr_ratio_changes_on_effective_date_only():
    from cdp.data.eventos_corporativos import catalog, ratio_at
    events=catalog()
    assert ratio_at(events,'EMBJ',date(2026,11,13),4)==4
    assert ratio_at(events,'EMBJ',date(2026,11,16),4)==1
    assert ratio_at(events,'EMBJ',date(2026,11,17),4)==1


def test_intraday_does_not_treat_ads_split_as_profit():
    from types import SimpleNamespace

    from cdp.config import FundConfig
    from cdp.workflow.risk_monitor import _live_block
    p=SimpleNamespace(ticker='EMBJ',issuer_id='BR_EMBRAER',currency='USD',
        shares=-10,price_local=80,price_usd=80,market_value_usd=-800)
    rec=SimpleNamespace(date=date(2026,11,13),positions=[p],nav_end_usd=10000)
    quotes=pd.DataFrame([{'kind':'line','symbol':'EMBJ','price':19.0,
        'time':pd.Timestamp('2026-11-16T18:00:00Z')}])
    result=_live_block(rec,quotes,date(2026,11,16),FundConfig(),10000)
    assert result['pnl_usd'] == pytest.approx(40.0)
    assert result['posicoes'][0]['acoes'] == -40


def test_rectification_prefix_cannot_restore_target_risk_model(tmp_path):
    from test_daily_track_record import _chain

    from cdp.workflow.retificacao_financeira import BeforeTrack
    from cdp.workflow.track_record import TrackRecord
    track=TrackRecord(tmp_path/'book/track_record')
    _chain(track,[(date(2026,10,5),.01,0.0),(date(2026,10,6),.02,0.0)])
    prefix=BeforeTrack(track,date(2026,10,6))
    assert prefix.get(date(2026,10,5)) is not None
    assert prefix.get(date(2026,10,6)) is None


def test_unknown_event_without_any_previous_window_is_unsafe():
    from cdp.data.eventos_corporativos import unverified_observations
    base=prices(90.0,'2026-11-13')
    inc=prices(60.0,'2026-11-16').assign(prev_date=pd.NaT,
        prev_close_window=np.nan,prev_adj_close_window=np.nan)
    assert unverified_observations(pd.concat([base,inc]),[inc]) == ((date(2026,11,16),'EMBJ'),)


def test_removed_financial_report_never_reactivates_original(tmp_path):
    from test_daily_track_record import _chain

    from cdp.workflow.retificacao_financeira import report_folder, seal
    from cdp.workflow.track_record import TrackRecord
    track=TrackRecord(tmp_path/'book/track_record')
    _chain(track,[(date(2026,10,5),.01,0.0)])
    rec=track.last()
    seal(track,rec,rec,None,())
    original=tmp_path/'reports/daily/2026-10-05'
    original.mkdir(parents=True)
    (original/'relatorio.md').write_text('original')
    with pytest.raises(ValueError,match='retificado'):
        report_folder(tmp_path/'reports',rec.date)
    import shutil

    shutil.rmtree(track.root/'retificacoes')
    with pytest.raises(ValueError,match='retificação'):
        report_folder(tmp_path/'reports',rec.date)


def test_window_for_wrong_predecessor_is_unsafe():
    from cdp.data.eventos_corporativos import unverified_observations
    base=prices(90.0,'2026-11-13')
    inc=prices(60.0,'2026-11-16').assign(prev_date=pd.Timestamp('2026-11-12'),
        prev_close_window=90.0,prev_adj_close_window=90.0)
    assert unverified_observations(pd.concat([base,inc]),[inc]) == ((date(2026,11,16),'EMBJ'),)


def test_interrupted_financial_seal_can_resume_without_activating_partial(tmp_path,monkeypatch):
    from test_daily_track_record import _chain

    from cdp.workflow.retificacao_financeira import seal
    from cdp.workflow.track_record import TrackRecord
    track=TrackRecord(tmp_path/'book/track_record')
    _chain(track,[(date(2026,10,5),.01,0.0)])
    rec=track.last()
    def crash(*a,**k):
        raise RuntimeError('interrupção simulada antes do evento')
    with monkeypatch.context() as m:
        m.setattr(track.audit,'append',crash)
        with pytest.raises(RuntimeError):
            seal(track,rec,rec,None,())
    with pytest.raises(ValueError):
        track.last()
    seal(track,rec,rec,None,())
    assert track.last() == rec
    assert track.verify()[0]


def test_truncate_restores_historical_adr_ratio():
    from datetime import UTC, datetime

    from cdp.contracts import SnapshotManifest
    from cdp.data.eventos_corporativos import catalog
    from cdp.market import MarketData
    from cdp.universe import Universe
    idx=pd.to_datetime(['2026-11-13','2026-11-16'])
    f=pd.DataFrame({'EMBJ':[80.0,19.0]},index=idx)
    empty=pd.DataFrame(index=idx)
    md=MarketData(manifest=SnapshotManifest(snapshot_id='test',as_of=date(2026,11,16),
        created_at=datetime(2026,11,16,tzinfo=UTC),universe_sha256='0'*64,files=[],
        is_synthetic=True,data_notice='DADOS SIMULADOS'),
        universe=Universe(pd.DataFrame({'adr_ratio':[1.0]},index=['EMBJ']),pd.DataFrame()),
        close=f,adj_close=f,volume=f,fx=empty,fundamentals=empty,short_interest=empty,
        lending=empty,benchmarks=empty,rates=empty,corporate_actions=catalog())
    historical=md.truncate(date(2026,11,13))
    assert historical.universe.lines.loc['EMBJ','adr_ratio']==4
    assert not historical.corporate_actions


def test_catalog_is_received_from_nominal_root_and_requires_evidence_member(tmp_path):
    import hashlib

    import yaml

    from cdp.data.eventos_corporativos import catalog
    from cdp.leitura_arquivos import ReceptorArquivos, ativar_receptor
    from cdp.workflow.leitura_contratos import TentativaDeEfeitoLeitura
    root=tmp_path.resolve()
    relative='docs/cdp/evidencias/eventos_corporativos/SIMADS.html'
    evidence=root/relative
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b'DADOS SIMULADOS - prova de evento de teste')
    digest=hashlib.sha256(evidence.read_bytes()).hexdigest()
    cfg=root/'configs/cdp/eventos_corporativos.yaml'
    cfg.parent.mkdir(parents=True)
    cfg.write_text(yaml.safe_dump({'events':[{'ticker':'SIMADS','effective_on':'2026-11-16',
        'announced_on':'2026-10-30','quantity_factor':4,'source_url':'https://www.sec.gov/example',
        'evidence_path':relative,'evidence_sha256':digest}]}))
    members={'catalog':('repositorio','configs/cdp/eventos_corporativos.yaml',
        hashlib.sha256(cfg.read_bytes()).hexdigest()),'evidence':('repositorio',relative,digest)}
    receiver=ReceptorArquivos({'repositorio':root},members)
    with ativar_receptor(receiver):
        assert [e.ticker for e in catalog()] == ['SIMADS']
    receiver=ReceptorArquivos({'repositorio':root},{'catalog':members['catalog']})
    with ativar_receptor(receiver),pytest.raises(TentativaDeEfeitoLeitura):
        catalog()


def test_prepared_report_completes_audit_once_and_preserves_bytes(tmp_path):
    import json
    from types import SimpleNamespace

    from test_daily_track_record import _chain

    from cdp.hashing import sha256_file
    from cdp.workflow.retificacao_financeira import corrected_report, seal
    from cdp.workflow.track_record import TrackRecord
    track=TrackRecord(tmp_path/'book/track_record')
    _chain(track,[(date(2026,10,5),.01,0.0)])
    rec=track.last()
    seal(track,rec,rec,None,())
    original=tmp_path/'reports/daily/2026-10-05'
    out=original/'retificacoes/financeira'
    out.mkdir(parents=True)
    originals=('relatorio.md','relatorio.html','factbook.json','comentario.json')
    for name in originals:
        (original/name).write_text('original DADOS SIMULADOS')
    for name in (*originals,'facts.md','comentario.schema.json'):
        (out/name).write_text('retificado DADOS SIMULADOS')
    body={'record_hash':rec.record_hash,'original_record_hash':rec.record_hash,
        'date':'2026-10-05','original_report':{n:sha256_file(original/n) for n in originals},
        'current_files':{p.name:sha256_file(p) for p in out.iterdir()},
        'report':{'md_sha256':sha256_file(out/'relatorio.md'),
                  'html_sha256':sha256_file(out/'relatorio.html')}}
    (out/'recibo.json').write_text(json.dumps(body))
    raw=(out/'recibo.json').read_bytes()
    rt=SimpleNamespace(reports_root=tmp_path/'reports',track=lambda:track,
        book=SimpleNamespace(audit=track.audit))
    track.audit.append('DAILY_FINANCIAL_REPORT_PREPARED','CDP',body,week=rec.date)
    n=len(track.audit.events())
    corrected_report(rt,rec.date)
    assert len(track.audit.events())==n+1
    corrected_report(rt,rec.date)
    assert len(track.audit.events())==n+1
    assert (out/'recibo.json').read_bytes()==raw


def test_agenda_recovery_does_not_consume_unfinished_financial_edition(tmp_path):
    from types import SimpleNamespace

    from test_daily_track_record import _chain

    from cdp.workflow.agenda import pending_publications
    from cdp.workflow.retificacao_financeira import pending, seal
    from cdp.workflow.track_record import TrackRecord
    track=TrackRecord(tmp_path/'book/track_record')
    _chain(track,[(date(2026,10,5),.01,0.0)])
    rec=track.last()
    seal(track,rec,rec,None,())
    def unavailable(day):
        raise AssertionError('agenda não deve consumir edição incompleta')
    rt=SimpleNamespace(reports_root=tmp_path/'reports',track=lambda:track,
        book=SimpleNamespace(audit=track.audit),daily_dir=unavailable)
    financial=pending(rt)
    assert financial['pendente']
    assert financial['datas_pendentes']==['2026-10-05']
    assert pending_publications(rt,financial_dates=financial['datas_pendentes'])==[]
    # Recibo preparado ainda sem evento também deve permitir adquirir a trava.
    track.audit.path.write_text('\n'.join(track.audit.path.read_text().splitlines()[:-1])+'\n')
    assert pending(rt)['pendente']


def test_unchanged_units_preserve_native_universe_identity():
    from cdp.data.eventos_corporativos import effective_universe
    from cdp.universe import Universe
    u=Universe(pd.DataFrame({'adr_ratio':[4.0]},index=['EMBJ']),pd.DataFrame())
    assert effective_universe(u,(),date(2026,11,13)) is u


def test_financial_event_cache_rechecks_content_with_same_size_and_mtime(tmp_path):
    import json
    import os

    from test_daily_track_record import _chain

    from cdp.audit import _event_hash
    from cdp.contracts import AuditEvent
    from cdp.workflow.retificacao_financeira import seal
    from cdp.workflow.track_record import TrackRecord
    tr=TrackRecord(tmp_path/'book/track_record')
    _chain(tr,[(date(2026,10,5),.01,0.0)])
    rec=tr.last()
    seal(tr,rec,rec,None,())
    assert tr.last()==rec  # seleção de eventos aquecida
    old=tr.audit.path.stat()
    rows=[]
    prev='0'*64
    for line in tr.audit.path.read_text().splitlines():
        row=json.loads(line)
        if row['event_type']=='DAILY_FINANCIAL_RECTIFICATION':
            row['payload_hash']='f'*64
        row['prev_hash']=prev
        ev=AuditEvent.model_validate(row)
        row['event_hash']=_event_hash(ev.seq,ev.ts,ev.event_type,ev.actor,ev.week,
                                    ev.payload_hash,ev.summary,ev.prev_hash)
        prev=row['event_hash']
        rows.append(json.dumps(row,ensure_ascii=False))
    tr.audit.path.write_text('\n'.join(rows)+'\n')
    assert tr.audit.path.stat().st_size==old.st_size
    os.utime(tr.audit.path,ns=(old.st_atime_ns,old.st_mtime_ns))
    assert tr.audit.verify_chain()[0]  # cadeia coerente, porém não autentica o recibo
    with pytest.raises(ValueError,match='vínculo íntegro'):
        tr.last()
