"""Staging V4 em bytes canônicos, rederivado integralmente antes do consumo.

Não registra perfil nativo nem emite DataFrame/frequência/versão financeira.
SHA do caller é checksum, não assinatura; os pins fixos e a rederivação fecham
o vínculo entre valores consumidos e componentes dos cinco corpos recebidos.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from . import consumidor, produtor

SCHEMA = 'cdp.enelchile.estagio_reautenticado/v4'
CONTEXT_SCHEMA = 'cdp.enelchile.contexto_estoque_proposto/v1'
MAX_STAGING_BYTES = 8_000_000


class InvalidStaging(ValueError):
    """Envelope/consumo não corresponde integralmente às fontes fechadas."""


@dataclass(frozen=True, slots=True)
class ConsumedStock:
    """Valor rederivado; apenas primitivos imutáveis, sem versão/frequência atribuída."""

    item: str
    entity: str
    period_end: str
    currency: str
    value_USD: str
    component_tags: tuple[str, ...]
    includes_leases: bool
    note: str


@dataclass(frozen=True, slots=True)
class ValidatedStaging:
    """Saída imutável. Esta classe não é uma entrada aceita pelo leitor."""

    body: bytes
    sha256: str
    stocks: tuple[ConsumedStock, ...]
    proposed_context_bodies: tuple[bytes, ...]


def _require(condition, message):
    if not condition:
        raise InvalidStaging(message)


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise InvalidStaging('JSON não serializável no contrato canônico') from exc


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        _require(key not in out, 'Chave JSON duplicada')
        out[key] = value
    return out


def _constant(value):
    raise InvalidStaging(f'Constante JSON não finita: {value}')


def _decode(body):
    try:
        value = json.loads(body, object_pairs_hook=_pairs, parse_constant=_constant)
    except InvalidStaging:
        raise
    except (ValueError, RecursionError) as exc:
        raise InvalidStaging('JSON inválido') from exc
    _require(type(value) is dict, 'Envelope JSON deve ser objeto fechado')
    _require(_canonical(value) == body, 'Corpo JSON não canônico')
    return value


def _derive(xml_body, xml_receipt_body, submissions_body, index_receipts_body,
            metadata_receipt_body, knowledge_cutoff):
    try:
        documentary = consumidor.adaptar_enel(
            xml_body, xml_receipt_body, submissions_body, index_receipts_body,
            metadata_receipt_body, knowledge_cutoff, enabled=True)
    except consumidor.InvalidConsumerInput as exc:
        raise InvalidStaging('Fontes/corte recusados pelo staging documental fechado') from exc
    envelope = documentary['provenance']['reported_documental_envelope']
    documentary_sha = _sha(_canonical(documentary))
    temporal = documentary['provenance']['temporal']
    pins = [{
        'role': role, 'sha256': _sha(body), 'bytes': len(body),
    } for role, body in [('XML', xml_body), ('XML_receipt', xml_receipt_body),
                         ('submissions', submissions_body), ('index_receipts', index_receipts_body),
                         ('metadata_receipt_ROOT', metadata_receipt_body)]]
    contexts = []
    for fact in documentary['facts']:
        components = fact['reported_components']
        value = sum((Fraction(c['value_USD']) for c in components), Fraction())
        _require(Fraction(fact['value_USD']) == value, 'Valor consumido contradiz componentes')
        ties = [envelope['tieouts'][c['tieout_index']] for c in components]
        contexts.append({
            'schema': CONTEXT_SCHEMA, 'type': 'estoque_calculado_proposto',
            'native_profile_registered': False, 'reportado_no_documento': False,
            'entity': fact['entidade'], 'issuer_id': fact['issuer_id'], 'item': fact['item'],
            'period_start': None, 'period_end': fact['period_end'], 'currency': fact['currency'],
            'scale': '1', 'consolidated': fact['consolidado'], 'value_USD': produtor._finite_decimal(value),
            'component_tags': fact['component_tags'], 'components': components,
            'includes_leases': fact['includes_leases'], 'note': fact['note'],
            'source_XML_sha256': produtor.BODY_SHA256, 'source_URL': produtor.URL,
            'accession': produtor.ACCESSION, 'dependencies': pins,
            'documentary_full_sha256': documentary_sha, 'tieouts': ties,
            'localizer_refs': [{k: loc[k] for k in ('tag', 'ordinal_xml_0base', 'note', 'textblock_sha256_utf8')}
                               for loc in envelope['localizers']],
            'temporal': temporal, 'freq': None, 'source_version': None, 'native_version': None,
            'first_publication_utc': None, 'PIT_certified': False,
            'executor_possession_authenticated': False,
        })
    return {
        'schema': SCHEMA, 'staging_only': True, 'source_pins': pins,
        'documentary': documentary, 'documentary_full_sha256': documentary_sha,
        'proposed_contexts': contexts,
        'version_contract': {
            'identity_kind': 'instancia_por_accession_e_sha_sem_ranking', 'cik': produtor.CIK,
            'accession': produtor.ACCESSION, 'source_XML_sha256': produtor.BODY_SHA256,
            'period_end': produtor.END, 'source_version': None, 'native_version': None,
            'restatement_order': 'nao_estabelecida', 'freq': None,
            'schema_version_is_not_financial_version': True,
        },
        'native_adoption': False, 'P0_closed': False, 'G19_closed': False, 'PIT_certified': False,
    }


def preparar_enel_v4(xml_body: bytes, xml_receipt_body: bytes, submissions_body: bytes,
                     index_receipts_body: bytes, metadata_receipt_body: bytes,
                     knowledge_cutoff: datetime, *, enabled: bool = False) -> bytes | None:
    """Prepara somente bytes imutáveis, rederivados dos cinco corpos pinned; sem I/O."""
    _require(type(enabled) is bool, 'Opt-in exige booleano explícito')
    if not enabled:
        return None
    body = _canonical(_derive(xml_body, xml_receipt_body, submissions_body,
                              index_receipts_body, metadata_receipt_body, knowledge_cutoff))
    _require(len(body) <= MAX_STAGING_BYTES, 'Envelope acima do teto fechado')
    return body


def receber_enel_v4(staging_body: bytes, expected_sha256: str,
                    xml_body: bytes, xml_receipt_body: bytes, submissions_body: bytes,
                    index_receipts_body: bytes, metadata_receipt_body: bytes,
                    knowledge_cutoff: datetime, *, enabled: bool = False) -> ValidatedStaging | None:
    """Não aceita objeto/envelope/valor/callback confiável do caller.

    Mesmo com checksum recomputado, todo conteúdo deve coincidir com nova
    derivação das fontes pinned. Quem recebe bytes depois de qualquer transporte
    deve entrar novamente por este leitor; DTO construído manualmente não é input.
    """
    _require(type(enabled) is bool, 'Opt-in exige booleano explícito')
    if not enabled:
        return None
    _require(type(staging_body) is bytes and len(staging_body) <= MAX_STAGING_BYTES,
             'Staging exige bytes imutáveis dentro do teto')
    _require(type(expected_sha256) is str and re.fullmatch(r'[0-9a-f]{64}', expected_sha256),
             'Checksum externo SHA256 ausente/inválido')
    _require(_sha(staging_body) == expected_sha256, 'Checksum externo diverge do corpo')
    _decode(staging_body)
    rederived = _derive(xml_body, xml_receipt_body, submissions_body,
                        index_receipts_body, metadata_receipt_body, knowledge_cutoff)
    expected = _canonical(rederived)
    _require(staging_body == expected, 'Envelope/valores consumidos divergem da rederivação integral')
    stocks = tuple(ConsumedStock(
        item=f['item'], entity=f['entidade'], period_end=f['period_end'], currency=f['currency'],
        value_USD=f['value_USD'], component_tags=tuple(f['component_tags']),
        includes_leases=f['includes_leases'], note=f['note'],
    ) for f in rederived['documentary']['facts'])
    return ValidatedStaging(body=expected, sha256=_sha(expected), stocks=stocks,
                           proposed_context_bodies=tuple(_canonical(c) for c in rederived['proposed_contexts']))


__all__ = ['ConsumedStock', 'InvalidStaging', 'ValidatedStaging', 'preparar_enel_v4', 'receber_enel_v4']
