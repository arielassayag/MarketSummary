"""Confirmação de saldo/unidade por fonte CVM pública arquivada, opt-in.

Não usa o contrato persistente privado nem pins de autoridade. Recebimento
civil do documento, posse local observada e publicação primária são distintos.
Só suporta o saldo BPA 1.01.02; não confirma classificação, DFC ou FCFF.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from types import MappingProxyType
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from .publico_arquivo import Arquivo, RegistroArquivo
from .publico_cvm import url_zip

METODO = 'confirmacao_documental_cvm_publica/v1'
COLUNAS_TEMPORAIS = ('disponivel_desde', 'disponibilidade_tipo',
                     'data_recebimento_documento', 'received_date')


def instante(value) -> datetime:
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('confirmação pública exige corte UTC com fuso explícito')
    return value.astimezone(UTC)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _normal(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value))
                   if not unicodedata.combining(c)).strip().casefold()


def _cnpj(value):
    digits = re.sub(r'\D', '', str(value))
    if len(digits) != 14:
        raise ValueError('CNPJ documental inválido')
    return digits


def _tempo_arquivo(path: Path) -> datetime:
    st = path.stat()
    micros, remainder = divmod(st.st_mtime_ns, 1000)
    mtime = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=micros + bool(remainder))
    birth = getattr(st, 'st_birthtime', None)
    if birth is None:
        return mtime
    micros = int((Decimal(str(birth)) * Decimal(1000000)).to_integral_value(rounding=ROUND_CEILING))
    return max(mtime, datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=micros))


def _csv(raw):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')
    return list(csv.DictReader(io.StringIO(text), delimiter=';'))


@dataclass(frozen=True)
class SaldoDocumental:
    estado: str
    motivo: str
    valor_brl: str | None = None
    disponivel_desde: str | None = None
    data_recebimento_documento: str | None = None
    data_publicacao: None = None
    evidencia: str | None = None
    metodo: str = METODO


class ConfirmacaoCVM:
    """Bytes/registro recebidos pelo coletor normal; reabertos a cada consulta.

    A âncora é a captura pública local do Arquivo. Não declara segregação,
    assinatura, primeiro post, UTC certificado ou uma raiz humana de autoridade.
    """

    def __init__(self, arquivo: Arquivo, registros: list[RegistroArquivo],
                 identidades: dict[str, str], *, corte: datetime):
        if type(arquivo) is not Arquivo or any(type(r) is not RegistroArquivo for r in registros):
            raise ValueError('Arquivo e registros públicos explícitos obrigatórios')
        self.raiz = arquivo.raiz.resolve()
        self.corte = min(instante(corte), datetime.now(UTC))
        self.registros = tuple(registros)
        self.identidades = MappingProxyType({str(k): _cnpj(v) for k, v in identidades.items()})
        base = arquivo.base.absolute()
        self.indice = arquivo.caminho_indice.absolute()
        self._confinado(self.indice, base)
        self.indice_sha256 = _sha(self.indice.read_bytes())
        self._meta = {self.indice: self._stat(self.indice)}
        for reg in self.registros:
            path = (arquivo.base / reg.caminho).absolute()
            relative = Path(reg.caminho)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('recurso CVM fora da raiz pública recebida')
            self._confinado(path, base)
            self._meta[path] = self._stat(path)
        self.autenticar()

    @staticmethod
    def _confinado(path, base):
        if not path.resolve().is_relative_to(base.resolve()):
            raise ValueError('recurso CVM fora da raiz pública recebida')
        if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(base)):
            raise ValueError('recurso CVM atravessa link')

    @staticmethod
    def _stat(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('arquivo público ausente ou link')
        s = path.stat()
        return s.st_size, s.st_mtime_ns, str(getattr(s, 'st_birthtime', None)), s.st_ino, s.st_dev

    def autenticar(self):
        if _sha(self.indice.read_bytes()) != self.indice_sha256:
            raise ValueError('índice público mudou após recebimento do coletor')
        fresh = Arquivo(self.raiz, offline=True)
        available = {}
        for path, expected in self._meta.items():
            self._confinado(path, fresh.base)
            if self._stat(path) != expected:
                raise ValueError('metadados do arquivo público mudaram')
        for reg in self.registros:
            match = re.fullmatch(r'CVM/(DFP|ITR)/(dfp|itr)_cia_aberta_(\d{4})\.zip', reg.chave)
            if not match or match[1].casefold() != match[2] or reg.fonte != 'CVM':
                raise ValueError('registro não é demonstração pública CVM')
            if reg.url != url_zip(match[1], int(match[3])):
                raise ValueError('URL pública não corresponde ao registro CVM')
            if reg not in fresh.registros(reg.chave):
                raise ValueError('registro explícito ausente do índice público atual')
            raw = fresh.ler(reg)
            if len(raw) != reg.bytes:
                raise ValueError('tamanho público diverge do recibo')
            path = fresh.base / reg.caminho
            available[reg.sha256] = max(reg.limite_captura, _tempo_arquivo(path), _tempo_arquivo(self.indice))
        return fresh, available

    def _tabelas(self, reg, arquivo):
        doc, year = reg.chave.split('/')[1], int(reg.chave[-8:-4])
        raw = arquivo.ler(reg)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = z.namelist()
            if len(names) != len(set(names)):
                raise ValueError('ZIP público tem membros duplicados')
            index_name = f'{doc.lower()}_cia_aberta_{year}.csv'
            index_raw = z.read(index_name)
            tables = {'index': _csv(index_raw), 'index_member': index_name,
                      'index_sha256': _sha(index_raw), 'doc': doc, 'year': year}
            for base in ('con', 'ind'):
                member = f'{doc.lower()}_cia_aberta_BPA_{base}_{year}.csv'
                if member in names:
                    body = z.read(member)
                    tables[base] = {'rows': _csv(body), 'member': member, 'sha256': _sha(body)}
        return tables

    def resolver(self, row, *, corte: datetime | None = None) -> SaldoDocumental:
        cut = min(self.corte, instante(corte) if corte is not None else self.corte, datetime.now(UTC))
        archive, available = self.autenticar()
        if row.get('item') != 'aplicacoes_cp' or row.get('freq') not in ('A', 'Q'):
            return SaldoDocumental('inconclusivo', 'item/frequência fora do saldo BPA suportado')
        if row.get('fonte') != 'CVM' or row.get('demonstrativo') != 'BP':
            return SaldoDocumental('conflito', 'origem/demonstrativo normalizados não são BPA da CVM')
        if pd.isna(row.get('value')):
            return SaldoDocumental('inconclusivo', 'ausência anterior ao QA não é restaurável')
        iid = str(row.get('issuer_id'))
        if iid not in self.identidades or _cnpj(row.get('entidade')) != self.identidades[iid]:
            return SaldoDocumental('conflito', 'emissor/CNPJ não correspondem ao coletor público')
        entries = [r for r in self.registros if r.sha256 == row.get('sha256')]
        if len(entries) != 1:
            return SaldoDocumental('inconclusivo', 'recibo público de origem ausente ou ambíguo')
        reg = entries[0]
        if available[reg.sha256] > cut:
            return SaldoDocumental('posterior_ao_corte', 'captura pública completa posterior ao corte',
                                  disponivel_desde=available[reg.sha256].isoformat())
        tables = self._tabelas(reg, archive)
        document = re.fullmatch(r'(DFP|ITR) (\d{4}-\d{2}-\d{2}) v(\d+)', str(row.get('documento')))
        if not document or document[1] != tables['doc']:
            return SaldoDocumental('conflito', 'documento normalizado não pertence ao arquivo público')
        end = pd.Timestamp(row.get('period_end')).date().isoformat()
        if document[2] != end or row.get('currency') != 'BRL' or Decimal(str(row.get('escala'))) != 1:
            return SaldoDocumental('conflito', 'competência/moeda/unidade normalizada divergentes')
        cnpj = self.identidades[iid]
        indices = [r for r in tables['index'] if _cnpj(r['CNPJ_CIA']) == cnpj
                   and r['DT_REFER'] == document[2] and int(r['VERSAO']) == int(document[3])]
        if len(indices) != 1:
            return SaldoDocumental('inconclusivo', 'índice do filing não é único')
        index = indices[0]
        link = urlparse(index['LINK_DOC'])
        query = parse_qs(link.query)
        if link.scheme not in ('http', 'https') or link.hostname != 'www.rad.cvm.gov.br' \
                or query.get('NumeroSequencialDocumento') != [index['ID_DOC']] \
                or row.get('url') != index['LINK_DOC']:
            return SaldoDocumental('conflito', 'locator público não corresponde ao filing normalizado')
        if not isinstance(row.get('consolidado'), (bool, np.bool_)):
            return SaldoDocumental('conflito', 'base normalizada não é booleana explícita')
        base = 'con' if bool(row.get('consolidado')) else 'ind'
        table = tables.get(base)
        if table is None:
            return SaldoDocumental('inconclusivo', 'BPA da base requerida ausente')
        selected = [(n, r) for n, r in enumerate(table['rows'], start=2)
                    if _cnpj(r['CNPJ_CIA']) == cnpj and r['DT_REFER'] == document[2]
                    and int(r['VERSAO']) == int(document[3]) and r['DT_FIM_EXERC'] == end
                    and _normal(r['ORDEM_EXERC']) == 'ultimo' and r['CD_CONTA'] == '1.01.02']
        if len(selected) != 1:
            return SaldoDocumental('inconclusivo', 'grão/conta BPA não é único')
        line, raw = selected[0]
        if raw.get('CD_CVM') != index['CD_CVM'] or _normal(raw['MOEDA']) != 'real':
            return SaldoDocumental('conflito', 'registro CVM/moeda do grão divergentes')
        factor = {'mil': Decimal(1000), 'unidade': Decimal(1)}.get(_normal(raw['ESCALA_MOEDA']))
        if factor is None:
            return SaldoDocumental('inconclusivo', 'escala documental não suportada')
        value = Decimal(raw['VL_CONTA'])
        if not value.is_finite() or value * factor != Decimal(str(row['value'])):
            return SaldoDocumental('conflito', 'valor normalizado não confere com lexema/unidade públicos')
        evidence = {'source': 'CVM pública recebida pelo Arquivo', 'record': reg.como_dict(),
                    'archive_root': str(self.raiz), 'source_path': str(archive.base / reg.caminho),
                    'receipt_index_path': str(self.indice), 'receipt_index_sha256': self.indice_sha256,
                    'availability_utc': available[reg.sha256].isoformat(),
                    'index_member': tables['index_member'], 'index_member_sha256': tables['index_sha256'],
                    'statement_member': table['member'], 'statement_member_sha256': table['sha256'],
                    'row_number': line, 'cnpj': cnpj, 'codigo_cvm': index['CD_CVM'],
                    'filing_id': index['ID_DOC'], 'version': int(index['VERSAO']),
                    'period_end': end, 'base': base, 'account': raw['CD_CONTA'],
                    'label': raw['DS_CONTA'], 'currency': 'BRL', 'literal': raw['VL_CONTA'],
                    'scale_literal': raw['ESCALA_MOEDA'], 'factor_once': str(factor),
                    'normalized_brl': str(value * factor), 'locator': index['LINK_DOC'],
                    'financial_received_date_civil': index['DT_RECEB'], 'publication': None,
                    'classification_or_cash_flow_confirmed': False, 'utc_accuracy': None,
                    'human_authority_or_private_pins': False}
        self.autenticar()
        return SaldoDocumental('saldo_unidade_confirmados', 'lexema/grão/unidade públicos conferidos',
                              str(value * factor), available[reg.sha256].isoformat(), index['DT_RECEB'],
                              evidencia=json.dumps(evidence, ensure_ascii=False, sort_keys=True))
