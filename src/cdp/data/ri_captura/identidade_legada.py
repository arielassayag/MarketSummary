"""Vínculo privado fechado: PDF → registro SEC → linha do master confiado.

O master é uma autoridade externa previamente selada, não um candidato do fato.
Substituir simultaneamente os roots de confiança é uma decisão externa à API.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from .observado import Document, ReceiptVault, instant, normalize, sha


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def legal_tokens(value: str) -> tuple[str, ...]:
    """Sem aliases, cortes de sufixos, similaridade ou uso de telefone/endereço."""
    if not isinstance(value, str):
        raise ValueError('nome legal não textual')
    value = unicodedata.normalize('NFD', value.upper())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    # Abreviação pontuada continua a mesma palavra: S.A.B.→SAB e C.V./→CV.
    value = value.translate(str.maketrans('', '', '.,/'))
    return tuple(re.findall('[A-Z0-9]+', value))


class MasterAuthority:
    """Inicializada pelo contexto confiado, antes de receber candidato/documento.

    expected_anchor_sha é o root fixado pelo auditor. Um CSV novo, ainda que
    re-selado pelo solicitante, não substitui esse root nem sua linha canônica.
    """
    def __init__(self, anchor_bytes: bytes, expected_anchor_sha: str):
        if sha(anchor_bytes) != expected_anchor_sha:
            raise ValueError('master: root diferente da autoridade previamente confiada')
        root = json.loads(anchor_bytes)
        if root.get('schema') != 'cdp.ri.master_confiado_privado/v2' or not root.get('origem_confianca'):
            raise ValueError('master: autoridade/origem ausente')
        self._root = root
        self._root_fingerprint = sha(canonical(root))
        self.anchor_sha256 = expected_anchor_sha

    def _read(self):
        root = self._root
        if sha(canonical(root)) != self._root_fingerprint:
            raise ValueError('master: root interno adulterado após autenticação')
        raw = Path(root['master_path']).read_bytes()
        if sha(raw) != root['master_sha256']:
            raise ValueError('master: bytes diferentes da autoridade previamente confiada')
        proof_raw = Path(root['observacao_path']).read_bytes()
        if sha(proof_raw) != root['observacao_sha256']:
            raise ValueError('master: observação diferente da autoridade')
        proof = json.loads(proof_raw)
        if (proof.get('schema') != 'cdp.observacao_local_curada/v1'
                or proof.get('master_path') != root['master_path']
                or proof.get('master_sha256') != root['master_sha256']):
            raise ValueError('master: observação não vincula o arquivo curado')
        started, completed = instant(proof['inicio_utc']), instant(proof['fim_utc'])
        if completed < started:
            raise ValueError('master: observação invertida')
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
        if not rows or not {'issuer_id', 'yahoo_ticker', 'exchange'} <= set(rows[0]):
            raise ValueError('master: colunas canônicas ausentes')
        keys = [(r['yahoo_ticker'], r['exchange']) for r in rows]
        if len(keys) != len(set(keys)) or any(not all((r['issuer_id'], *k)) for r, k in zip(rows, keys, strict=True)):
            raise ValueError('master: linhas repetidas/identidade ausente')
        return rows, completed

    def read_line(self, ticker: str, exchange: str):
        rows, completed = self._read()
        candidates = [r for r in rows if (r['yahoo_ticker'], r['exchange']) == (ticker, exchange)]
        if len(candidates) != 1:
            raise ValueError('master: ticker/bolsa não identificam uma linha única')
        row = candidates[0]
        return {'issuer_id': row['issuer_id'], 'ticker': row['yahoo_ticker'], 'exchange': row['exchange']}, completed

    @property
    def master_sha256(self):
        return self._root['master_sha256']

    @property
    def observation_sha256(self):
        return self._root['observacao_sha256']


@dataclass(frozen=True)
class Registration:
    name: str
    cik: str
    pairs: tuple[tuple[str, str], ...]
    available: datetime
    url: str
    raw_sha256: str
    receipt_sha256: str
    namespace: str


class IdentityVault:
    """Custódia do registro primário, separada do catálogo do fato financeiro."""
    def __init__(self, config_bytes: bytes, expected_config_sha: str, *, master: MasterAuthority):
        if sha(config_bytes) != expected_config_sha:
            raise ValueError('registro: custódia diferente da âncora')
        config = json.loads(config_bytes)
        if config.get('schema') != 'cdp.ri.identidade_custodia/v2' or not config.get('origem_confianca'):
            raise ValueError('registro: schema/origem ausente')
        if config.get('master_anchor_sha256') != master.anchor_sha256:
            raise ValueError('registro: master diferente do root previamente confiado')
        self.config = config
        self._config_fingerprint = sha(canonical(config))
        self.config_sha256 = expected_config_sha
        self.master = master

    def registration(self) -> Registration:
        if sha(canonical(self.config)) != self._config_fingerprint:
            raise ValueError('registro: custódia interna adulterada após autenticação')
        if self.config['master_anchor_sha256'] != self.master.anchor_sha256:
            raise ValueError('registro: master diferente do root previamente confiado')
        entry = self.config['registro']
        if entry.get('namespace') != 'sec.submissions':
            raise ValueError('registro: namespace não certifica identidade/listagem')
        raw, receipt_raw = (Path(entry[k]).read_bytes() for k in ('raw_path', 'receipt_path'))
        if sha(raw) != entry['raw_sha256'] or sha(receipt_raw) != entry['receipt_sha256']:
            raise ValueError('registro: bytes/recibo diferentes da custódia')
        batch = json.loads(receipt_raw)
        if batch.get('schema') != 'cdp.captura_publica_http/v1' or batch.get('retrodatada') is not False:
            raise ValueError('registro: recibo não é captura HTTP declarada')
        entries = [r for r in batch['fontes'] if r.get('path') == entry['raw_path']]
        if len(entries) != 1:
            raise ValueError('registro: recibo não vincula bruto de forma única')
        receipt = entries[0]
        if (receipt.get('status_http') != 200 or receipt.get('aceita_como_documento') is not True
                or receipt.get('sha256') != sha(raw)
                or receipt.get('url_solicitada') != entry['url'] or receipt.get('url_final') != entry['url']):
            raise ValueError('registro: status/URL/hash não vinculam os bytes')
        url_cik = re.fullmatch(r'https://data\.sec\.gov/submissions/CIK([0-9]{10})\.json', entry['url'])
        if not url_cik:
            raise ValueError('registro: URL/namespace SEC incompatíveis')
        started, completed = instant(receipt['inicio_utc']), instant(receipt['fim_utc'])
        if completed < started:
            raise ValueError('registro: captura invertida')
        data = json.loads(raw)
        cik = str(data['cik'])
        if not re.fullmatch('[0-9]{1,10}', cik) or cik.zfill(10) != url_cik[1]:
            raise ValueError('registro: CIK difere do identificador no URL')
        tickers, exchanges = data['tickers'], data['exchanges']
        if not isinstance(tickers, list) or not isinstance(exchanges, list) or len(tickers) != len(exchanges) or not tickers:
            raise ValueError('registro: ticker/bolsa não têm correspondência definida')
        pairs = tuple(zip(tickers, exchanges, strict=True))
        if any(not isinstance(t, str) or not isinstance(e, str) or not t or not e for t, e in pairs) or len(pairs) != len(set(pairs)):
            raise ValueError('registro: ticker/bolsa ausentes/repetidos')
        if not legal_tokens(data['name']):
            raise ValueError('registro: entidade legal ausente')
        return Registration(data['name'], cik.zfill(10), pairs, completed, entry['url'], sha(raw), sha(receipt_raw), entry['namespace'])


@dataclass(frozen=True)
class Bind:
    issuer_id: str
    document_entity: str
    document_symbol: str
    registry_name: str
    cik: str
    ticker: str
    exchange: str
    namespace: str
    available_since: datetime
    registry_capture: datetime
    master_observation: datetime
    pdf_capture: datetime
    pdf_sha256: str
    custody_manifest_sha256: str
    registry_sha256: str
    registry_receipt_sha256: str
    identity_custody_sha256: str
    master_sha256: str
    master_observation_sha256: str
    master_anchor_sha256: str
    registry_url: str
    locator: str


def bind(vault: ReceiptVault, doc: Document, identity: IdentityVault, *, ticker: str, exchange: str, cutoff: datetime):
    cut = instant(cutoff)
    doc.validate()
    registration = identity.registration()
    line, master_observed = identity.master.read_line(ticker, exchange)
    captures = [vault.read(n) for n in ('origem', 'lista', 'pdf')]
    available = max(*(c.completed for c in captures), registration.available, master_observed)
    if available > cut:
        return None, available
    pdf = captures[-1]
    if (ticker, exchange) not in registration.pairs:
        raise ValueError('registro: candidato não é uma listagem primária explícita')
    reader = PdfReader(io.BytesIO(pdf.payload), strict=True)
    if reader.is_encrypted or len(reader.pages) != doc.page_count or not 1 <= doc.page_metadata <= len(reader.pages):
        raise ValueError('identidade: estrutura/página física do PDF divergente')
    meta = normalize(reader.pages[doc.page_metadata - 1].extract_text())
    names = re.findall(r'Nombre de la entidad que informa u otras formas de identificación:\s*(.*?)\s+Descripción de la moneda de presentación:', meta)
    if len(names) != 1 or legal_tokens(names[0]) != legal_tokens(doc.entity) or legal_tokens(names[0]) != legal_tokens(registration.name):
        raise ValueError('identidade: entidade literal não concorda com PDF e registro')
    labels = ''.join(c for c in unicodedata.normalize('NFD', meta) if not unicodedata.combining(c))
    symbols = re.findall(r'Clave de cotizacion:\s*([A-Z][A-Z0-9.\-]*)', labels, re.IGNORECASE)
    if not symbols or len(set(symbols)) != 1 or symbols[0] != ticker:
        raise ValueError('identidade: símbolo explícito do PDF não concorda com ticker do registro')
    if line['issuer_id'] != doc.issuer_id:
        raise ValueError('identidade: IID solicitado difere da linha do master confiado')
    return Bind(line['issuer_id'], names[0], symbols[0], registration.name, registration.cik,
                line['ticker'], line['exchange'], registration.namespace, available,
                registration.available, master_observed, pdf.completed, pdf.payload_sha256, vault.manifest_sha256,
                registration.raw_sha256, registration.receipt_sha256, identity.config_sha256,
                identity.master.master_sha256, identity.master.observation_sha256, identity.master.anchor_sha256,
                registration.url, f'PDF página física {doc.page_metadata}; entidade/símbolo; SEC submissions CIK/ticker/bolsa; linha canônica ticker/bolsa'), available
