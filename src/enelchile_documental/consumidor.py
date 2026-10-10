"""Dois saldos documentais Enel separados; staging puro, default inativo.

Não produz DataFrame, A/Q/TTM ou versão SEC. filed civil, acceptance e recepção
UTC permanecem campos diferentes. Não integra o perfil documental nativo/CDP.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from fractions import Fraction

from . import produtor

ISSUER = 'CL_ENELCHILE'
SCHEMA = 'cdp.enelchile.estagio_documental/v3'
METADATA_SHA256 = '25d6197f836943c6fb99c153f8d0ef79ba2a857c0494fea904e69ad6c72f127b'
SUBMISSIONS_SHA256 = 'b3702cf634660baa7d9b0c0e64c4a3c96d77a46dd9b33406b3e4c3eb85747a3f'
INDEX_RECEIPTS_SHA256 = 'c29efd420ec2584e905449b6345569137e6fb4c7ded5f02a7606d137e552d7f9'
SUBMISSIONS_URL = 'https://data.sec.gov/submissions/CIK0001659939.json'
SUBMISSIONS_PATH = 'data/publico/SEC/submissions/2026-10-09/CIK0001659939.json'
XML_RECEIPT_PATH = '.cdp/prototipos/enelchile-emprestimos-v1/inputs/recibo_xml_literal.json'
FLOOR = datetime(2026, 10, 9, 14, 13, 45, 703490, tzinfo=UTC)


class InvalidConsumerInput(ValueError):
    """Contrato finito incompleto/contraditório; nenhuma saída parcial."""


def _require(condition, reason):
    if not condition:
        raise InvalidConsumerInput(reason)


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _pin(body, expected_sha, expected_bytes, label):
    _require(type(body) is bytes, f'{label} exige bytes literais')
    _require(len(body) == expected_bytes and _sha(body) == expected_sha, f'Pin de {label} divergente')


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        _require(key not in out, 'JSON com chave duplicada')
        out[key] = value
    return out


def _json(body, label):
    try:
        out = json.loads(body, object_pairs_hook=_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidConsumerInput(f'{label}: JSON inválido') from exc
    _require(isinstance(out, Mapping), f'{label} deve ser objeto')
    return out


def _instant(value, label):
    try:
        dt = datetime.fromisoformat(value) if isinstance(value, str) else value
        _require(type(dt) is datetime and dt.tzinfo is not None and dt.utcoffset() == timedelta(0),
                 f'{label} exige instante UTC explícito')
        return dt.astimezone(UTC)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidConsumerInput(f'{label} exige instante UTC explícito') from exc


def _metadata(submissions, receipts, metadata, xml_receipt):
    """Confere identidade/período e deriva floor dos recibos dos corpos recebidos."""
    cik = submissions.get('cik')
    _require(type(cik) in (str, int) and str(cik).isdigit()
             and str(cik).zfill(10) == produtor.CIK, 'CIK submissions divergente')
    recent = submissions.get('filings', {}).get('recent', {})
    _require(isinstance(recent, Mapping), 'recent SEC ausente')
    accns = recent.get('accessionNumber')
    _require(type(accns) is list, 'accessions SEC ausentes')
    positions = [i for i, value in enumerate(accns) if value == produtor.ACCESSION]
    _require(positions == [3] and metadata.get('accession_index') == 3, 'Accession/ordinal divergente')
    fields = {}
    for key, expected in metadata['fields_literal'].items():
        values = recent.get(key)
        _require(type(values) is list and len(values) == len(accns), f'Campo SEC {key} incompleto')
        fields[key] = values[3]
        _require(fields[key] == expected, f'Submissions/recibo contradiz {key}')
    _require(fields.get('accessionNumber') == produtor.ACCESSION
             and fields.get('form') == '20-F' and fields.get('reportDate') == produtor.END
             and fields.get('primaryDocument') == 'enic-20251231x20f.htm',
             'Documento/forma/data-base SEC divergente')
    _require(fields.get('filingDate') == '2026-04-28'
             and fields.get('acceptanceDateTime') == '2026-04-28T19:24:13.000Z',
             'Filed/acceptance fora da fonte fechada')
    filed = date.fromisoformat(fields['filingDate'])
    accepted = _instant(fields['acceptanceDateTime'], 'Acceptance SEC')
    _require(accepted.date() == filed, 'Filed/acceptance contraditórios no pacote fechado')
    expected_receipts = [item['receipt'] for item in metadata['archive_receipts']]
    _require(receipts == expected_receipts and len(receipts) == 2, 'Recibos índice divergentes')
    observations = []
    for receipt in receipts:
        _require(receipt.get('fonte') == 'SEC' and receipt.get('url') == SUBMISSIONS_URL
                 and receipt.get('sha256') == SUBMISSIONS_SHA256
                 and type(receipt.get('bytes')) is int and receipt['bytes'] == 42640,
                 'Recibo índice não vincula submissions fechado')
        observations.append(_instant(receipt.get('data_coleta'), 'Recepção submissions'))
    xml_received = _instant(xml_receipt.get('data_coleta'), 'Recepção XML')
    submissions_received = min(observations)
    floor = max(xml_received, submissions_received)
    _require(floor == FLOOR and floor == _instant(metadata['availability_floor_received_bodies_UTC'], 'Floor'),
             'Floor declarado não confere com os corpos recebidos')
    return fields, filed, accepted, xml_received, submissions_received, floor


def adaptar_enel(xml_body: bytes, xml_receipt_body: bytes, submissions_body: bytes,
                 index_receipts_body: bytes, metadata_receipt_body: bytes,
                 knowledge_cutoff: datetime, *, enabled: bool = False,
                 issuer_id: str = ISSUER, accession: str = produtor.ACCESSION,
                 period_end: str = produtor.END) -> dict | None:
    """Recebe literais fechados, nunca envelope/valor/callback do caller.

    Saída é staging de dois agregados exatos com sua proveniência completa. A
    recepção dos corpos estabelece um floor observado, não publicação/PIT/posse OP.
    A fonte e recibos são finitos fixados; não há parâmetro que relaxe seus pins.
    """
    _require(type(enabled) is bool, 'Opt-in exige booleano explícito')
    if not enabled:
        return None
    _require(type(knowledge_cutoff) is datetime, 'Corte exige datetime UTC explícito')
    cut = _instant(knowledge_cutoff, 'Corte de conhecimento')
    _require(type(issuer_id) is str and issuer_id == ISSUER, 'Issuer solicitado diverge de Enel Chile')
    _require(type(accession) is str and accession == produtor.ACCESSION, 'Accession solicitado divergente')
    _require(type(period_end) is str and period_end == produtor.END, 'Data-base solicitada divergente')
    _pin(metadata_receipt_body, METADATA_SHA256, 3758, 'recibo metadados ROOT')
    _pin(submissions_body, SUBMISSIONS_SHA256, 42640, 'submissions')
    _pin(index_receipts_body, INDEX_RECEIPTS_SHA256, 736, 'recibos índice')
    _pin(xml_receipt_body, produtor.RECEIPT_SHA256, 438, 'recibo XML')
    _pin(xml_body, produtor.BODY_SHA256, produtor.BODY_BYTES, 'XML')
    metadata = _json(metadata_receipt_body, 'recibo metadados ROOT')
    submissions = _json(submissions_body, 'submissions')
    receipts = [_json(line, 'recibo índice') for line in index_receipts_body.splitlines()]
    xml_receipt = _json(xml_receipt_body, 'recibo XML')
    pins = metadata['source_before_after_M6']
    _require(pins[SUBMISSIONS_PATH]['sha256'] == SUBMISSIONS_SHA256
             and pins[SUBMISSIONS_PATH]['bytes'] == len(submissions_body)
             and pins[XML_RECEIPT_PATH]['sha256'] == produtor.RECEIPT_SHA256,
             'Recibo metadados não vincula os corpos recebidos')
    fields, filed, accepted, xml_received, submissions_received, floor = _metadata(
        submissions, receipts, metadata, xml_receipt)
    _require(cut >= floor, 'Corte anterior ao floor observado de XML e submissions')
    try:
        reported = produtor.extrair_enel(xml_body, xml_receipt_body, produtor.RECEIPT_SHA256,
                                        cut, enabled=True)
    except produtor.InvalidDocument as exc:
        raise InvalidConsumerInput('Produtor documental recusou os corpos recebidos') from exc
    _require(reported['cik'] == produtor.CIK and reported['issuer_id'] == issuer_id
             and reported['period_end'] == period_end and reported['source']['accn'] == accession,
             'Identidade/período entre produtor e submissions divergente')
    expected_tags = {
        'divida_bruta': [f'{{{produtor.CUSTOM}}}InterestBearingLoansAndBorrowingsCurrent',
                        f'{{{produtor.CUSTOM}}}InterestBearingLoansAndBorrowingsNoncurrent'],
        'arrendamentos': [f'{{{produtor.IFRS}}}CurrentLeaseLiabilities',
                         f'{{{produtor.IFRS}}}NoncurrentLeaseLiabilities'],
    }
    _require(len(reported['facts']) == 4, 'Quatro componentes documentais obrigatórios')
    provenance = {
        'schema': SCHEMA, 'reported_documental_envelope': reported,
        'submissions': {'sha256': SUBMISSIONS_SHA256, 'bytes': len(submissions_body),
                        'url': SUBMISSIONS_URL, 'body_utf8': submissions_body.decode(),
                        'accession_index': 3, 'fields_literal': fields},
        'index_receipts': {'sha256': INDEX_RECEIPTS_SHA256, 'bytes': len(index_receipts_body),
                           'body_utf8': index_receipts_body.decode(), 'records': receipts,
                           'source_index_sha256': pins['data/publico/indice.jsonl']['sha256'],
                           'source_lines_1based': [x['line'] for x in metadata['archive_receipts']]},
        'xml_receipt': {'sha256': produtor.RECEIPT_SHA256, 'bytes': len(xml_receipt_body),
                        'body_utf8': xml_receipt_body.decode(), 'record': xml_receipt},
        'metadata_receipt_ROOT': {'sha256': METADATA_SHA256, 'bytes': len(metadata_receipt_body),
                                  'body_utf8': metadata_receipt_body.decode(), 'record': metadata},
        'temporal': {'filed_date': filed.isoformat(), 'sec_acceptance_at_utc': accepted.isoformat(),
                     'xml_received_at_utc': xml_received.isoformat(),
                     'submissions_received_at_utc': submissions_received.isoformat(),
                     'availability_floor_utc': floor.isoformat(), 'knowledge_cutoff_utc': cut.isoformat(),
                     'first_publication_utc': None, 'PIT_certified': False,
                     'executor_possession_authenticated': False,
                     'metadata_receipt_created_at_utc': metadata['utc']},
    }
    provenance_body = json.dumps(provenance, ensure_ascii=False, sort_keys=True,
                                 separators=(',', ':'), allow_nan=False).encode()
    provenance_sha = _sha(provenance_body)
    facts = []
    for item, group, note in [('divida_bruta', 'emprestimos', '20.1'),
                              ('arrendamentos', 'arrendamentos', '21')]:
        components = [f for f in reported['facts'] if f['group'] == group]
        _require([f['tag'] for f in components] == expected_tags[item], 'Partição de dívida/leases divergente')
        value = sum((Fraction(f['value_USD']) for f in components), Fraction(0))
        total = reported['totals_separate'][group]
        _require(Fraction(total['value_USD']) == value and total['components'] == expected_tags[item]
                 and total['includes_leases'] is (group == 'arrendamentos'), 'Total documental incompatível')
        facts.append({
            'entidade': produtor.CIK, 'issuer_id': issuer_id, 'demonstrativo': 'BP', 'item': item,
            'period_start': None, 'period_end': period_end, 'value_USD': produtor._finite_decimal(value),
            'currency': 'USD', 'escala': '1', 'consolidado': True, 'stock_not_flow': True,
            'freq': None, 'source_version': None, 'native_version': None,
            'form': '20-F', 'accession': accession, 'note': note,
            'evidence_label': 'derived_calculation', 'component_tags': expected_tags[item],
            'reported_components': deepcopy(components), 'includes_leases': item == 'arrendamentos',
            'disponibilidade_tipo': 'recepcao_observada', 'disponivel_desde': floor.isoformat(),
            'filed_date': filed.isoformat(), 'sec_acceptance_at_utc': accepted.isoformat(),
            'xml_received_at_utc': xml_received.isoformat(),
            'submissions_received_at_utc': submissions_received.isoformat(),
            'knowledge_cutoff_utc': cut.isoformat(), 'first_publication_utc': None,
            'source_XML_sha256': produtor.BODY_SHA256, 'provenance_sha256': provenance_sha,
            'PIT_certified': False, 'executor_possession_authenticated': False,
        })
    return {
        'schema': SCHEMA, 'opt_in': True, 'staging_only': True,
        'data_notice': 'DADOS PÚBLICOS REPORTADOS — AGREGADOS DOCUMENTAIS EM STAGING',
        'facts': facts, 'provenance': provenance, 'provenance_sha256': provenance_sha,
        'native_dataframe_emitted': False, 'native_context_profile_registered': False,
        'native_selection_adopted': False, 'source_restatement_order_unknown': True,
        'native_blockers': ['Perfil de estoque Enel não registrado no contexto documental nativo',
                            'Versionamento/reapresentações SEC não estabelecidos',
                            'Datas-base oficiais/fluxos do emissor não integrados; sem A/Q/TTM inventados'],
        'financial_adoption': False, 'G19_closed': False, 'P0_closed': False, 'PIT_certified': False,
    }


__all__ = ['adaptar_enel', 'InvalidConsumerInput']
