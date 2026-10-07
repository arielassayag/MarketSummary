"""DADOS SIMULADOS: PDF vetorial sem rede; confere recusas e integração PIT."""

import copy
import hashlib
import io
import json
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from cdp.data import publico as P
from cdp.data import publico_ri as ri
from cdp.data.publico_arquivo import Arquivo
from cdp.data.publico_fatos import selecionar_pit
from cdp.universe import load_universe


def _pdf(texto):
    """Cria bytes de documento, exercitando o leitor real, sem fixture paga/bruto real."""
    escritor = PdfWriter()
    pagina = escritor.add_blank_page(width=612, height=792)
    fonte = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                              NameObject('/Subtype'): NameObject('/Type1'),
                              NameObject('/BaseFont'): NameObject('/Helvetica'),
                              NameObject('/Encoding'): NameObject('/WinAnsiEncoding')})
    pagina[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
        DictionaryObject({NameObject('/F1'): escritor._add_object(fonte)})})
    fluxo = DecodedStreamObject()
    comandos = ['BT /F1 9 Tf 30 760 Td 12 TL']
    for linha in texto.splitlines():
        literal = linha.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        comandos.append(f'({literal}) Tj T*')
    comandos.append('ET')
    fluxo.set_data('\n'.join(comandos).encode('cp1252'))
    pagina[NameObject('/Contents')] = escritor._add_object(fluxo)
    buf = io.BytesIO()
    escritor.write(buf)
    return buf.getvalue()


TEXTO = '''DADOS SIMULADOS; Fideicomiso F/2157; 18 de febrero de 2026
Estados consolidados de utilidad integral
Cifras expresadas en miles de pesos mexicanos ($)
2025 2024
Ingresos totales $1,200 $900
Utilidad neta consolidada (100) 50
Depreciacion y amortizacion 0 -
Otros componentes de la utilidad integral:
Utilidad neta consolidada 999 888'''


def _doc(conteudo):
    return {'issuer_id': 'MX_FMTY', 'sha256': hashlib.sha256(conteudo).hexdigest(),
            'data_publicacao': '2026-02-18', 'entidade_documento': 'Fideicomiso F/2157',
            'publicacao_no_documento': {'pagina': 1, 'texto': '18 de febrero de 2026'},
            'documento': 'DADOS_SIMULADOS.pdf', 'url': 'https://example.org/simulado.pdf',
            'tabelas': [{'pagina': 1, 'demonstrativo': 'DRE',
                        'ancoras': ['Estados consolidados de utilidad integral',
                                    'Cifras expresadas en miles de pesos mexicanos ($)'],
                        'cabecalho_colunas': '2025 2024',
                        'fim_tabela': 'Otros componentes de la utilidad integral:',
                        'colunas': [{'rotulo': '2025', 'inicio': '2025-01-01', 'fim': '2025-12-31'},
                                    {'rotulo': '2024', 'inicio': '2024-01-01', 'fim': '2024-12-31'}],
                        'moeda': 'MXN', 'escala': 1000,
                        'itens': {'receita': {'rotulos': ['Ingresos totales']},
                                  'lucro_liquido': {'rotulos': ['Utilidad neta consolidada']},
                                  'd_a_dfc': {'rotulos': ['Depreciacion y amortizacion']}}}]}


def test_pdf_tabela_total_sinal_escala_zero_explicito_e_ausencia():
    raw = _pdf(TEXTO)
    f = ri.fatos_pdf_ri(raw, _doc(raw), as_of=date(2026, 3, 1))
    f = f.set_index(['item', 'period_end'])
    assert f.loc[('receita', pd.Timestamp('2025-12-31')), 'value'] == 1_200_000
    assert f.loc[('lucro_liquido', pd.Timestamp('2025-12-31')), 'value'] == -100_000
    assert f.loc[('d_a_dfc', pd.Timestamp('2025-12-31')), 'value'] == 0
    assert ('d_a_dfc', pd.Timestamp('2024-12-31')) not in f.index
    assert f['currency'].eq('MXN').all()
    assert f['received_date'].eq(pd.Timestamp('2026-02-18')).all()
    assert f['consolidado'].all() and not f['pit_estimado'].any()


@pytest.mark.parametrize('erro', ['hash', 'coluna', 'periodo', 'individual', 'publicacao', 'data_catalogo', 'entidade'])
def test_pdf_recusa_documento_ou_metadados_inconsistentes(erro):
    texto = TEXTO.replace('consolidados', 'individuales') if erro == 'individual' else TEXTO
    raw = _pdf(texto)
    d = _doc(raw)
    if erro == 'hash':
        raw += b'\nconteudo alterado'
    elif erro == 'coluna':
        d['tabelas'][0]['colunas'].reverse()
    elif erro == 'periodo':
        d['tabelas'][0]['colunas'][0]['fim'] = '2026-12-31'
    elif erro == 'individual':
        d['tabelas'][0]['ancoras'][0] = 'Estados individuales de utilidad integral'
    elif erro == 'publicacao':
        d['publicacao_no_documento']['texto'] = '20 de febrero de 2026'
    elif erro == 'data_catalogo':
        d['data_publicacao'] = '2026-02-19'
    elif erro == 'entidade':
        d['entidade_documento'] = 'outra entidade'
    with pytest.raises(ValueError):
        ri.fatos_pdf_ri(raw, d, as_of=date(2026, 3, 1))
    with pytest.raises(ValueError, match='publicação posterior'):
        ri.fatos_pdf_ri(_pdf(TEXTO), _doc(_pdf(TEXTO)), as_of=date(2026, 2, 17))


def test_subtotal_e_duplicata_divergente_nao_substituem_total():
    for troca in ['Subtotal Ingresos totales', 'Ingresos totales 1,500 900\nIngresos totales']:
        raw = _pdf(TEXTO.replace('Ingresos totales', troca))
        f = ri.fatos_pdf_ri(raw, _doc(raw), as_of=date(2026, 3, 1))
        assert 'receita' not in set(f['item'])
    raw = _pdf(TEXTO.replace('$1,200 $900', '$1,20 $900'))
    assert 'receita' not in set(ri.fatos_pdf_ri(raw, _doc(raw), as_of=date(2026, 3, 1))['item'])


def test_coleta_ri_publicacao_pit_hash_e_releitura_offline(tmp_path, monkeypatch):
    raw = _pdf(TEXTO)
    catalogo = tmp_path / 'catalogo.json'
    d = _doc(raw)
    futuro = copy.deepcopy(d)
    futuro['data_publicacao'] = '2026-12-01'
    catalogo.write_text(json.dumps({'schema': 'cdp.ri_demonstrativos/v1',
                                  'documentos': [d, futuro]}))
    monkeypatch.setattr(ri, 'CATALOGO_RI', catalogo)
    uni = load_universe()
    mestre = pd.DataFrame([{'issuer_id': 'MX_FMTY', 'cnpj': None, 'cik': None}]).set_index('issuer_id')
    monkeypatch.setattr(P, 'mestre_publico', lambda *a, **kw: mestre)
    monkeypatch.setattr(P, '_arquivo', lambda root, offline: Arquivo(tmp_path / 'cache', offline=offline,
                              agora=lambda: datetime(2026, 3, 1, 12, tzinfo=UTC)))
    chamadas = []

    def baixar(url, headers):
        chamadas.append(url)
        assert url == d['url']
        return raw

    f = P.demonstrativos(['MX_FMTY'], date(2026, 3, 1), universe=uni, root=tmp_path / 'cache',
                         http_get=baixar, complementar_yahoo=False)
    assert chamadas == [d['url']]
    assert not f.empty and f['fonte'].eq('RI').all()
    assert f['sha256'].eq(hashlib.sha256(raw).hexdigest()).all()
    assert f['data_publicacao'].eq(date(2026, 2, 18)).all()
    g = P.demonstrativos(['MX_FMTY'], date(2026, 3, 1), universe=uni, root=tmp_path / 'cache',
                         offline=True, http_get=lambda *a: pytest.fail('rede offline'),
                         complementar_yahoo=False)
    pd.testing.assert_frame_equal(f, g)


def test_ttm_semestral_preserva_componentes_sem_inventar_trimestre():
    raw = _pdf(TEXTO)
    anual = ri.fatos_pdf_ri(raw, _doc(raw), as_of=date(2026, 8, 1))
    anual = anual[anual['item'] == 'receita'].assign(fonte='RI', sha256='a' * 64)
    semestres = []
    for inicio, fim, valor in [('2026-01-01', '2026-06-30', 750_000),
                                ('2025-01-01', '2025-06-30', 500_000)]:
        linha = anual.iloc[0].to_dict()
        linha.update(period_start=pd.Timestamp(inicio), period_end=pd.Timestamp(fim),
                     value=valor, received_date=pd.Timestamp('2026-07-31'), anual=False,
                     documento='semestral.pdf', url='https://example.org/semestral.pdf', sha256='b' * 64)
        semestres.append(linha)
    fatos = pd.concat([anual, pd.DataFrame(semestres)], ignore_index=True)
    out = selecionar_pit(fatos, date(2026, 8, 1))
    atual = out[out['period_end'] == pd.Timestamp('2026-06-30')]
    assert list(atual['freq']) == ['TTM']  # nenhum Q1/Q2 é inferido do semestre
    assert atual.iloc[0]['value'] == 1_450_000
    assert atual.iloc[0]['data_publicacao'] == pd.Timestamp('2026-07-31')
    assert 'a' * 64 in atual.iloc[0]['nota'] and 'b' * 64 in atual.iloc[0]['nota']
    assert 'semestre atual + anual anterior − semestre comparativo' in atual.iloc[0]['nota']
    assert not (selecionar_pit(fatos, date(2026, 7, 30))['period_end'] == pd.Timestamp('2026-06-30')).any()
    revisada = anual[anual['period_end'] == pd.Timestamp('2025-12-31')].copy()
    revisada['value'] = 1_500_000
    revisada['received_date'] = pd.Timestamp('2026-08-15')
    revisada['sha256'] = 'c' * 64
    revisada['documento'] = 'anual-republicada.pdf'
    com_revisao = pd.concat([fatos, revisada], ignore_index=True)
    anterior = selecionar_pit(com_revisao, date(2026, 8, 14))
    anterior = anterior[anterior['period_end'] == pd.Timestamp('2026-06-30')].iloc[0]
    assert anterior['value'] == 1_450_000 and anterior['data_publicacao'] == pd.Timestamp('2026-07-31')
    posterior = selecionar_pit(com_revisao, date(2026, 8, 15))
    posterior = posterior[posterior['period_end'] == pd.Timestamp('2026-06-30')].iloc[0]
    assert posterior['value'] == 1_750_000
    assert posterior['data_publicacao'] == pd.Timestamp('2026-08-15')
    assert 'c' * 64 in posterior['nota'] and 'b' * 64 in posterior['nota']
    individual = anual.copy()
    individual['consolidado'] = False
    mistos = pd.DataFrame(semestres)
    mistos.loc[mistos['period_end'] == pd.Timestamp('2025-06-30'), 'consolidado'] = False
    misturado = selecionar_pit(pd.concat([individual, mistos]), date(2026, 8, 1))
    assert not (misturado['period_end'] == pd.Timestamp('2026-06-30')).any()
    semestres[1]['period_start'] = pd.Timestamp('2025-02-01')
    desalinhado = selecionar_pit(pd.concat([anual, pd.DataFrame(semestres)]), date(2026, 8, 1))
    assert not (desalinhado['period_end'] == pd.Timestamp('2026-06-30')).any()
