"""DADOS SIMULADOS: representações concorrentes de D&A no mesmo grão CVM."""
from __future__ import annotations

import hashlib
import io
import os
import sys
import zipfile
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.cobertura.fontes import _fatos_suplementares
from cdp.data import publico as P
from cdp.data import publico_cvm as CVM
from cdp.data.publico_arquivo import RegistroArquivo
from cdp.data.publico_fatos import selecionar_pit

CNPJ = '00.000.000/0001-00'
FIM = '2025-12-31'
TOLERANCIA = Decimal('0.000001')


def linha(conta, descricao, valor, **changes):
    row = {'CNPJ_CIA': CNPJ, 'DT_REFER': FIM, 'VERSAO': '1', 'MOEDA': 'REAL',
           'ESCALA_MOEDA': 'UNIDADE', 'ORDEM_EXERC': 'ÚLTIMO',
           'DT_INI_EXERC': '2025-01-01', 'DT_FIM_EXERC': FIM,
           'CD_CONTA': conta, 'DS_CONTA': descricao, 'VL_CONTA': str(valor)}
    return {**row, **changes}


def da(valor=25, **changes):
    return linha('6.01.01.01', 'Depreciação e amortização', valor, **changes)


def corpo(mi=(), md=()):
    rows = [*mi, *md, linha('7.04.01', 'Depreciação, amortização e exaustão', -99)]
    index = pd.DataFrame([{'CNPJ_CIA': CNPJ, 'DT_REFER': r['DT_REFER'],
                           'VERSAO': r['VERSAO'], 'DT_RECEB': '2026-03-01',
                           'LINK_DOC': 'https://example.invalid/DADOS_SIMULADOS/DFP'}
                          for r in rows]).drop_duplicates()
    frames = {'dfp_cia_aberta_2025.csv': index,
              'dfp_cia_aberta_DRE_con_2025.csv': pd.DataFrame([
                  linha('3.05', 'Resultado Antes do Resultado Financeiro e dos Tributos', 200)]),
              'dfp_cia_aberta_DVA_con_2025.csv': pd.DataFrame([rows[-1]])}
    for method, values in [('MI', mi), ('MD', md)]:
        if values:
            frames[f'dfp_cia_aberta_DFC_{method}_con_2025.csv'] = pd.DataFrame([
                *values, linha('6.01', 'Caixa Líquido das Atividades Operacionais', 100)])
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for member, frame in frames.items():
            archive.writestr(zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0)),
                             frame.to_csv(index=False, sep=';').encode('latin-1'))
    return output.getvalue()


@contextmanager
def guarda_api():
    active = [True]
    counts = {'read': 0, 'write': 0, 'network': 0, 'process': 0, 'mutation': 0}

    def guard(event, args):
        if not active[0]:
            return
        if event == 'open':
            _, mode, flags = args
            writer = ((isinstance(mode, str) and any(c in mode for c in 'wax+'))
                      or (isinstance(flags, int) and flags & (
                          os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            counts['write' if writer else 'read'] += 1
            assert not writer, 'Writer vedado na API'
        elif event.startswith('socket.'):
            counts['network'] += 1
            raise AssertionError('Rede vedada na API')
        elif event.startswith(('subprocess.', 'os.system', 'os.exec', 'os.fork', 'os.posix_spawn')):
            counts['process'] += 1
            raise AssertionError('Processo vedado na API')
        elif event in ('os.remove', 'os.rename', 'os.replace', 'os.mkdir', 'os.rmdir',
                       'os.link', 'os.symlink', 'os.utime', 'os.chmod', 'os.truncate'):
            counts['mutation'] += 1
            raise AssertionError('Mutação vedada na API')
    sys.addaudithook(guard)
    try:
        yield counts
    finally:
        active[0] = False


def produzir(body, monkeypatch):
    reg = RegistroArquivo('CVM/DFP/dfp_cia_aberta_2025.zip', 'CVM', CVM.url_zip('DFP', 2025),
                         'DADOS_SIMULADOS.zip', hashlib.sha256(body).hexdigest(), len(body),
                         datetime(2026, 10, 8, tzinfo=UTC), 'microseconds')

    class Transporte:
        offline = True
        falhas = []
        conhecimento_ate = None

        def chaves(self):
            return [reg.chave]

        def obter(self, chave, fonte, url, baixar, **kwargs):
            if chave != reg.chave:
                return None
            assert fonte == reg.fonte and url == reg.url
            if kwargs.get('validar'):
                kwargs['validar'](body)
            return reg, body

    monkeypatch.setattr(P, '_arquivo', lambda *_a, **_k: Transporte())
    monkeypatch.setattr(P, 'mestre_publico', lambda *_a, **_k: pd.DataFrame(
        {'cnpj': [CNPJ], 'cik': [None]}, index=['DADOS_SIMULADOS']))
    universe = SimpleNamespace(issuers=pd.DataFrame(
        {'gics_sector': ['DADOS SIMULADOS']}, index=['DADOS_SIMULADOS']))

    def proibido(*_args, **_kwargs):
        raise AssertionError('Rede/fábrica vedada')

    with guarda_api() as counts:
        tabs = CVM.ler_zip_demonstracoes(body, 'DFP', 2025)
        raw = CVM.fatos_cvm(tabs, 'DFP').assign(fonte='CVM', sha256=reg.sha256)
        supplemental = _fatos_suplementares(tabs, 'DFP')
        selected = selecionar_pit(raw, date(2026, 10, 9))
        P._CACHE_CVM.clear()
        normal = P.demonstrativos(['DADOS_SIMULADOS'], date(2026, 10, 9), offline=True,
                                 universe=universe, complementar_yahoo=False,
                                 http_get=proibido, yf_factory=proibido, anos=1)
    assert all(counts[k] == 0 for k in ('write', 'network', 'process', 'mutation'))
    assert set(normal['sha256']) == {reg.sha256}
    return raw, supplemental, selected, normal, reg, counts


def valores(frame, item):
    return [Decimal(str(v)) for v in frame.loc[frame['item'].eq(item), 'value']]


@pytest.mark.parametrize('case', ['identicos', 'divergentes', 'divergentes_com_disjunto',
                                  'zero_divergente', 'disjuntos', 'ausente', 'invertido'])
def test_representacoes_no_mesmo_grao_em_todas_as_apis(monkeypatch, case):
    mi, md, expected = [da()], [da()], Decimal(25)
    if case == 'divergentes':
        md, expected = [da(26)], None
    elif case == 'divergentes_com_disjunto':
        mi = [da(), linha('6.01.01.02', 'Exaustão dos ativos biológicos', 15)]
        md, expected = [da(26)], None
    elif case == 'zero_divergente':
        mi, md, expected = [da(0)], [da()], None
    elif case == 'disjuntos':
        md, expected = [linha('6.01.01.02', 'Amortização', 26)], Decimal(25) + Decimal(26)
    elif case == 'ausente':
        mi, md, expected = [], [], None
    elif case == 'invertido':
        mi, md, expected = [da(DT_INI_EXERC='2026-01-01')], [], None
    raw, supplement, selected, normal, reg, _ = produzir(corpo(mi, md), monkeypatch)
    targets = [] if expected is None else [expected]
    assert valores(raw, 'd_a') == valores(raw, 'd_a_dfc') == targets
    assert valores(supplement, 'd_a_dfc') == targets
    assert valores(raw, 'retencoes_dva') == [Decimal(-99)]
    for frame in (selected, normal):
        for freq in ('A', 'TTM'):
            view = frame[frame['freq'].eq(freq)]
            assert valores(view, 'd_a') == valores(view, 'd_a_dfc') == targets
            ebitda = valores(view, 'ebitda')
            if expected is None:
                assert ebitda == []
            else:
                assert len(ebitda) == 1
                assert abs(ebitda[0] - (Decimal(200) + expected)) <= TOLERANCIA
            assert valores(view, 'retencoes_dva') == [Decimal(-99)]
    if case in ('divergentes', 'divergentes_com_disjunto', 'zero_divergente', 'invertido'):
        reason = 'montantes concorrentes' if case != 'invertido' else 'intervalo invertido'
        assert any(reason in a['msg'] for a in raw.attrs['qa'])
        assert any(reason in a['msg'] for a in supplement.attrs['qa'])
        assert any(reason in a for a in normal.attrs['qa'])
    else:
        assert not raw.attrs['qa'] and not supplement.attrs.get('qa')
    selected_da = normal[normal['item'].eq('d_a')]
    assert selected_da['data_publicacao'].tolist() == ([] if expected is None else [date(2026, 3, 1)] * 2)
    assert selected_da['sha256'].tolist() == ([] if expected is None else [reg.sha256] * 2)


def test_conflito_nao_recusa_versao_distinta_do_mesmo_emissor():
    body = corpo([da(), da(27, VERSAO='2')], [da(26)])
    raw = CVM.fatos_cvm(CVM.ler_zip_demonstracoes(body, 'DFP', 2025), 'DFP')
    view = raw[raw['item'].eq('d_a')]
    assert view['version'].tolist() == [2] and valores(view, 'd_a') == [Decimal(27)]
    assert any('montantes concorrentes' in a['msg'] for a in raw.attrs['qa'])


def test_limite_de_niveis_pai_misto_filho_puro_permanece_declarado(monkeypatch):
    body = corpo([linha('6.01.01', 'Depreciação e perda por redução ao valor recuperável', 50),
                  da(), linha('6.01.01.02', 'Perda por redução ao valor recuperável', 25)])
    raw, supplement, selected, normal, _, _ = produzir(body, monkeypatch)
    assert valores(raw, 'd_a') == [Decimal(25)]
    assert valores(supplement, 'd_a_dfc') == []
    for frame in (selected, normal):
        assert valores(frame[frame['freq'].eq('A')], 'd_a') == [Decimal(25)]
    assert any('D&A da DFC indeterminada' in a['msg'] for a in supplement.attrs['qa'])
