"""DADOS SIMULADOS: oráculos temporais, não prova de vintages históricos reais."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from cdp.backtest.proveniencia import (
    DEPENDENCIES,
    EVIDENCE_FILE,
    EVIDENCE_SCHEMA,
    FIELDS,
    FileVintageSource,
    TemporalEvidenceError,
    assess_temporal_inputs,
    prefix_market,
)
from cdp.contracts import SourceRecord
from cdp.data.snapshot import load_snapshot, write_tables
from cdp.hashing import sha256_file
from cdp.universe import universe_from_frame

CAPTURE = datetime(2026, 10, 6, 22, tzinfo=UTC)
CUTOFF = datetime(2026, 10, 7, 1, tzinfo=UTC)
ASOF = date(2026, 10, 6)


@pytest.fixture
def snapshot(tmp_path):
    dates = pd.to_datetime(['2026-10-05', '2026-10-06'])
    uni = pd.DataFrame([dict(issuer_id='SIM_A', issuer_name='DADOS SIMULADOS', country='BR',
        gics_sector='Energy', line_type='LOCAL', yahoo_ticker='SIM.SA', exchange='BVMF',
        currency='BRL', adr_ratio=1., primary_line=True)])
    universe_from_frame(uni)  # valida o fixture com o contrato real
    source = SourceRecord(source_id='fixture', name='DADOS SIMULADOS — fonte arquivada de prova',
        url='https://example.org/fixture', retrieved_at=CAPTURE, point_in_time=False,
        fields=sorted({f for fs in FIELDS.values() for f in fs}))
    prices = pd.DataFrame({'date':dates, 'ticker':'SIM.SA', 'close':[10.,11.],
                          'adj_close':[10.,11.], 'volume':[100.,np.nan]})
    path = tmp_path/'2026-10-06'
    write_tables(path, manifest_fields=dict(snapshot_id='fixture',as_of=ASOF,
        created_at=CAPTURE,sources=[source],limitations=[],missing_tickers=[],
        is_synthetic=False,data_notice='DADOS SIMULADOS — fixture de schema real'),
        universe_bytes=uni.to_csv(index=False).encode(),prices=prices,
        fx=pd.DataFrame({'date':dates,'currency':'BRL','usd_per_unit':[.2,.21]}),
        benchmarks=pd.DataFrame({'date':dates,'symbol':'BZ=F','close':[80.,81.]}),
        rates=pd.DataFrame({'date':dates,'series':'USD_3M','value':[.03,.03]}),
        fundamentals=pd.DataFrame({'market_cap':[1e6],'shares_outstanding':[10000.],
                                   'forward_eps':[np.nan],'currency':['BRL']},index=['SIM.SA']),
        short_interest=pd.DataFrame({'shares_short':[200.]},index=['SIM.SA']),
        lending=pd.DataFrame({'lending_rate_annual':[.02]},index=['SIM.SA']),
        lending_history=None,news_items=[],qa={})
    return path


def evidence(path, *, registered_at=CAPTURE):
    md = load_snapshot(path)
    bindings = {f.path:f.sha256 for f in md.manifest.files}
    raw = {'schema_version':EVIDENCE_SCHEMA,'registered_at':registered_at.isoformat(),
           'manifest_sha256':sha256_file(path/'manifest.json'),
           'dependencies':{k:{'kind':'captured_vintage','scope':k,
                 'fields':sorted(FIELDS[k]),
                 'available_at':registered_at.isoformat(),
                 'files':{v:bindings[v]},'source_ids':['fixture']}
                 for k,v in DEPENDENCIES.items()}}
    (path/EVIDENCE_FILE).write_text(json.dumps(raw))
    return raw


def source(path, *, mode='pit_auditado', cutoff=CUTOFF):
    return FileVintageSource(path.parent,mode=mode,knowledge_cutoff=cutoff)


def test_boolean_period_publication_and_attrs_do_not_certify_pit(snapshot):
    md = load_snapshot(snapshot)
    md.fundamentals['period_end'] = '2025-12-31'
    md.fundamentals['publication_date'] = '2026-03-01'
    md.fundamentals.attrs.update(point_in_time=True, available_at='2026-03-01', authenticated=True)
    s = md.manifest.sources[0].model_copy(update={'point_in_time':True})
    md = replace(md,manifest=md.manifest.model_copy(update={'sources':[s]}))
    assessment = assess_temporal_inputs(md,CUTOFF,'pit_auditado')
    assert set(assessment['non_pit_dependencies']) == set(DEPENDENCIES)
    with pytest.raises(TemporalEvidenceError,match='PIT incompleto'):
        prefix_market(md,ASOF,CUTOFF,'pit_auditado')


def test_shadow_prefix_preserves_slow_current_data_source_and_nan(snapshot):
    md = load_snapshot(snapshot)
    before = md.manifest.model_dump()
    old_funds = md.fundamentals.copy(deep=True)
    out = prefix_market(md,date(2026,10,5),datetime(2026,10,5,23,tzinfo=UTC),'sombra_real')
    assert len(out.close) == 1 and out.as_of == date(2026,10,5)
    pd.testing.assert_frame_equal(out.fundamentals,old_funds)
    assert out.manifest.sources == md.manifest.sources and not out.is_synthetic
    assert out.manifest.created_at == md.manifest.created_at
    assert out.manifest.files == md.manifest.files and md.manifest.model_dump() == before
    assert out.fundamentals['forward_eps'].isna().all()
    assert any('não PIT' in v for v in out.manifest.limitations)
    out.fundamentals.loc['SIM.SA','shares_outstanding'] = 2.
    assert md.fundamentals.loc['SIM.SA','shares_outstanding'] == 10000.


def test_future_changes_change_knowledge_hash_even_when_prices_same(snapshot):
    md = load_snapshot(snapshot)
    original = assess_temporal_inputs(md,CUTOFF,'sombra_real')['knowledge_sha256']
    newer = replace(md,fundamentals=md.fundamentals.copy())
    newer.fundamentals.loc['SIM.SA','market_cap'] = np.nextafter(1e6,np.inf)
    assert assess_temporal_inputs(newer,CUTOFF,'sombra_real')['knowledge_sha256'] != original
    np.testing.assert_array_equal(newer.close,md.close)


def test_prefix_knowledge_sha_and_original_metadata_are_stable(snapshot):
    md = load_snapshot(snapshot)
    out = prefix_market(md,date(2026,10,5),CUTOFF,'sombra_real')
    assessment = assess_temporal_inputs(out,CUTOFF,'sombra_real')
    assert any(assessment['knowledge_sha256'] in line for line in out.manifest.limitations)
    assert assessment['origin_manifest_sha256'] == assess_temporal_inputs(md,CUTOFF,'sombra_real')['origin_manifest_sha256']


def test_simulation_requires_flag_notice_and_tz(snapshot):
    md = load_snapshot(snapshot)
    with pytest.raises(TemporalEvidenceError,match='origem simulada'):
        prefix_market(md,ASOF,CUTOFF,'simulado')
    with pytest.raises(ValueError,match='fuso'):
        assess_temporal_inputs(md,datetime(2026,10,7),'sombra_real')
    with pytest.raises(ValueError,match='desconhecido'):
        assess_temporal_inputs(md,CUTOFF,'auto')
    synthetic = replace(md,manifest=md.manifest.model_copy(update={'is_synthetic':True,
                                              'data_notice':'DADOS SIMULADOS'}))
    out = prefix_market(synthetic,ASOF,CUTOFF,'simulado')
    assert out.is_synthetic and 'DADOS SIMULADOS' in out.manifest.data_notice
    assert assess_temporal_inputs(out,CUTOFF,'simulado')['complete']
    with pytest.raises(TemporalEvidenceError):
        assess_temporal_inputs(synthetic,CUTOFF,'pit_auditado')


def test_verified_archived_capture_with_explicit_scopes_can_be_pit(snapshot):
    evidence(snapshot)
    md = source(snapshot).load(ASOF)
    report = assess_temporal_inputs(md,CUTOFF,'pit_auditado')
    assert report['complete'] and not report['non_pit_dependencies']
    assert all(v['status']=='captura_verificada' for v in report['dependencies'].values())
    assert report['evidence_sha256'] == sha256_file(snapshot/EVIDENCE_FILE)
    # O snapshot não se torna simulado; captura antiga é distinta de eficácia/IC.
    assert not md.is_synthetic and md.volume.iloc[-1].isna().all()


@pytest.mark.parametrize('dependency', ['listing_adr_actions','adjusted_prices',
                                      'style_capitalization','consensus_events'])
def test_generic_table_proof_does_not_certify_special_semantics(snapshot,dependency):
    raw = evidence(snapshot)
    raw['dependencies'][dependency].pop('scope')
    (snapshot/EVIDENCE_FILE).write_text(json.dumps(raw))
    with pytest.raises(TemporalEvidenceError) as exc:
        source(snapshot).load(ASOF)
    assert dependency in exc.value.diagnostics['non_pit_dependencies']


def test_registry_written_later_does_not_retroactively_certify_capture(snapshot):
    evidence(snapshot,registered_at=datetime(2026,10,8,tzinfo=UTC))
    with pytest.raises(TemporalEvidenceError,match='PIT incompleto'):
        source(snapshot).load(ASOF)


def test_dependency_missing_wrong_file_or_future_source_stays_incomplete(snapshot):
    raw = evidence(snapshot)
    raw['dependencies']['lending']['source_ids'] = []
    raw['dependencies']['short_interest']['files'] = {'fundamentals.parquet':'0'*64}
    raw['dependencies']['fundamentals']['available_at'] = '2026-10-08T00:00:00+00:00'
    (snapshot/EVIDENCE_FILE).write_text(json.dumps(raw))
    with pytest.raises(TemporalEvidenceError) as exc:
        source(snapshot).load(ASOF)
    assert {'lending','short_interest','fundamentals'} <= set(exc.value.diagnostics['non_pit_dependencies'])


def test_fields_cannot_be_asserted_when_source_metadata_does_not_contain_them(snapshot):
    raw = evidence(snapshot)
    raw['dependencies']['style_capitalization']['fields'].append('inventado')
    (snapshot/EVIDENCE_FILE).write_text(json.dumps(raw))
    with pytest.raises(TemporalEvidenceError) as exc:
        source(snapshot).load(ASOF)
    assert 'style_capitalization' in exc.value.diagnostics['non_pit_dependencies']


def test_before_first_base_never_selects_future_snapshot(snapshot):
    with pytest.raises(TemporalEvidenceError,match='Sem captura/base elegível'):
        source(snapshot,mode='sombra_real').load(date(2026,10,5))
    with pytest.raises(TemporalEvidenceError,match='Sem captura/base elegível'):
        source(snapshot,mode='sombra_real',cutoff=datetime(2026,10,6,20,tzinfo=UTC)).load(ASOF)


def test_verified_memory_mutation_cannot_be_laundered_by_prefix(snapshot):
    evidence(snapshot)
    md = source(snapshot).load(ASOF)
    md.universe.lines.loc['SIM.SA','adr_ratio'] = 2.
    assert not assess_temporal_inputs(md,CUTOFF,'pit_auditado')['complete']
    with pytest.raises(TemporalEvidenceError):
        prefix_market(md,ASOF,CUTOFF,'pit_auditado')


def test_manifest_source_metadata_mutation_is_not_a_new_authentication(snapshot):
    evidence(snapshot)
    md = source(snapshot).load(ASOF)
    md.manifest.sources[0] = md.manifest.sources[0].model_copy(update={'point_in_time':True})
    assessment = assess_temporal_inputs(md,CUTOFF,'pit_auditado')
    assert not assessment['complete']
    assert any('metadados originais' in r for r in assessment['dependencies']['fundamentals']['reasons'])


@pytest.mark.parametrize('target', ['manifest.json',EVIDENCE_FILE,'fundamentals.parquet'])
def test_disk_mutation_invalidates_authenticated_capture(snapshot,target):
    evidence(snapshot)
    md = source(snapshot).load(ASOF)
    (snapshot/target).write_bytes((snapshot/target).read_bytes()+b' ')
    assert not assess_temporal_inputs(md,CUTOFF,'pit_auditado')['complete']


def test_source_schema_without_registry_and_future_prefix_fail_closed(snapshot):
    with pytest.raises(TemporalEvidenceError,match='PIT incompleto'):
        source(snapshot).load(ASOF)
    md = load_snapshot(snapshot)
    with pytest.raises(TemporalEvidenceError,match='data futura'):
        prefix_market(md,date(2026,10,7),CUTOFF,'sombra_real')
