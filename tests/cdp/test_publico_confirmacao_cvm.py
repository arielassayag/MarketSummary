"""Causas da confirmação pública opt-in; fixtures DADOS SIMULADOS, sem rede."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.data.publico import _qa_magnitude, _refazer_derivados
from cdp.data.publico_arquivo import Arquivo
from cdp.data.publico_confirmacao_cvm import ConfirmacaoCVM
from cdp.data.publico_cvm import url_zip
from cdp.data.publico_fatos import _derivados, selecionar_pit

CNPJ = '12.345.678/0001-90'
URL = ('http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?'
       'CodigoInstituicao=1&NumeroSequencialDocumento=900001')


def zip_publico(*, escala='MIL', lexema='10', duplicar=False, indice_duplicado=False):
    index = f'{CNPJ};2026-06-30;1;DADOS SIMULADOS;012345;ITR;900001;2026-07-29;{URL}\n'
    saldo = f'{CNPJ};2026-06-30;1;DADOS SIMULADOS;012345;Real;{escala};ÚLTIMO;2026-06-30;1.01.02;Aplicações;{lexema}\n'
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('itr_cia_aberta_2026.csv',
                   ('CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC\n'
                   + index * (2 if indice_duplicado else 1)).encode('latin-1'))
        z.writestr('itr_cia_aberta_BPA_con_2026.csv',
                   ('CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;'
                   'DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA\n' + saldo * (2 if duplicar else 1)).encode('latin-1'))
    return out.getvalue()


def publico(tmp_path, **kwargs):
    arq = Arquivo(tmp_path, conhecimento_ate=datetime.max.replace(tzinfo=UTC))
    reg = arq.gravar('CVM/ITR/itr_cia_aberta_2026.zip', 'CVM', url_zip('ITR', 2026), zip_publico(**kwargs))
    provider = ConfirmacaoCVM(arq, [reg], {'BR_SIMULADO': CNPJ}, corte=datetime.now(UTC))
    row = pd.Series({'issuer_id': 'BR_SIMULADO', 'entidade': CNPJ, 'item': 'aplicacoes_cp',
                     'freq': 'Q', 'period_end': pd.Timestamp('2026-06-30'), 'value': 10_000.0,
                     'currency': 'BRL', 'escala': 1, 'consolidado': True, 'fonte': 'CVM',
                     'url': URL, 'documento': 'ITR 2026-06-30 v1', 'sha256': reg.sha256,
                     'demonstrativo': 'BP', 'nota': None, 'data_publicacao': None,
                     'pit_estimado': False})
    return arq, reg, provider, row


@pytest.fixture
def relogio_selector(monkeypatch):
    monkeypatch.setattr('cdp.data.publico_fatos._agora_observado',
                        lambda: datetime(2026, 10, 9, 5, tzinfo=UTC))


def test_recibo_real_e_granulo_decimal_nao_certificam_publicacao_ou_caixa(tmp_path):
    arq, reg, provider, row = publico(tmp_path)
    before = {p: p.read_bytes() for p in arq.base.rglob('*') if p.is_file()}
    result = provider.resolver(row)
    ev = json.loads(result.evidencia)
    assert result.estado == 'saldo_unidade_confirmados'
    assert Decimal(ev['literal']) * Decimal(ev['factor_once']) == Decimal(result.valor_brl) == 10_000
    assert ev['account'] == '1.01.02' and ev['filing_id'] == '900001'
    assert ev['record'] == reg.como_dict() and result.data_recebimento_documento == '2026-07-29'
    assert result.data_publicacao is None and ev['utc_accuracy'] is None
    assert ev['classification_or_cash_flow_confirmed'] is False
    assert ev['human_authority_or_private_pins'] is False
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize('field,value', [
    ('issuer_id', 'OUTRO'), ('entidade', '99.999.999/0001-99'), ('period_end', '2026-03-31'),
    ('currency', 'USD'), ('escala', 1000), ('consolidado', False), ('documento', 'ITR 2026-06-30 v2'),
    ('url', URL + '&outra=1'), ('sha256', '0' * 64), ('value', 10000000), ('value', None),
    ('item', 'cfo'), ('freq', 'TTM'),
    ('fonte', 'RI'), ('demonstrativo', 'DFC'), ('consolidado', 'false'),
])
def test_granulo_incompativel_ou_ausente_nao_restaura(tmp_path, field, value):
    _, _, provider, row = publico(tmp_path)
    row[field] = value
    assert provider.resolver(row).estado != 'saldo_unidade_confirmados'


@pytest.mark.parametrize('kwargs', [{'escala': 'BIL'}, {'lexema': '11'}, {'duplicar': True},
                                    {'indice_duplicado': True}])
def test_unidade_lexema_e_unicidade_documentais_sao_causais(tmp_path, kwargs):
    _, _, provider, row = publico(tmp_path, **kwargs)
    assert provider.resolver(row).estado != 'saldo_unidade_confirmados'


@pytest.mark.parametrize('delta,known', [(-1, False), (0, True), (1, True)])
def test_corte_utc_antes_exato_depois_da_captura_completa(tmp_path, delta, known):
    _, reg, provider, row = publico(tmp_path)
    _, available = provider.autenticar()
    result = provider.resolver(row, corte=available[reg.sha256] + timedelta(microseconds=delta))
    assert (result.estado == 'saldo_unidade_confirmados') is known


@pytest.mark.parametrize('resource', ['bytes', 'metadados', 'indice'])
def test_recurso_reaberto_em_toda_consulta_sem_writer_de_confirmacao(tmp_path, resource):
    arq, reg, provider, row = publico(tmp_path)
    assert provider.resolver(row).estado == 'saldo_unidade_confirmados'
    path = arq.base / reg.caminho
    if resource == 'bytes':
        path.write_bytes(path.read_bytes() + b'alterado')
    elif resource == 'metadados':
        import os
        st = path.stat()
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
    else:
        arq.caminho_indice.write_bytes(arq.caminho_indice.read_bytes() + b'\n')
    with pytest.raises((ValueError, RuntimeError)):
        provider.resolver(row)


def test_qa_somente_restaura_ausencia_criada_nesta_heuristica(tmp_path):
    _, _, provider, row = publico(tmp_path)
    rows = [row.to_dict() | {'period_end': pd.Timestamp(d), 'value': v}
            for d, v in [('2025-12-31', 4_000_000), ('2026-03-31', 4_100_000), ('2026-06-30', 10_000)]]
    before = pd.DataFrame(rows)
    qa = []
    default = _qa_magnitude(before, qa)
    assert pd.isna(default.iloc[-1]['value'])
    out = _qa_magnitude(before, qa, confirmacao_cvm=provider)
    assert out.iloc[-1]['value'] == 10_000
    assert out.attrs['confirmacoes_cvm'][0]['qa_descarte'].startswith('conferência:')
    before.loc[2, 'value'] = None
    other_gate = _qa_magnitude(before, [], confirmacao_cvm=provider)
    assert pd.isna(other_gate.iloc[-1]['value']) and other_gate.attrs['confirmacoes_cvm'] == []
    dropped = _qa_magnitude(before.iloc[:2], [], confirmacao_cvm=provider)
    assert len(dropped) == 2 and dropped.attrs['confirmacoes_cvm'] == []
    with pytest.raises(ValueError):
        _qa_magnitude(before, [], confirmacao_cvm=lambda x: True)


def fato(*, end='2026-06-30', start='2026-04-01', item='receita', value=5,
         disponibilidade='2026-10-08T19:16:35.863120+00:00', publication=None):
    return {'entidade': 'BR_SIMULADO', 'demonstrativo': 'DRE', 'freq': 'Q',
            'period_start': start, 'period_end': end, 'item': item, 'value': value,
            'currency': 'BRL', 'escala': 1, 'consolidado': True, 'fonte': 'RI',
            'url': 'https://example.test/DADOS_SIMULADOS', 'documento': 'DADOS SIMULADOS',
            'data_publicacao': publication, 'data_publicacao_primaria': publication,
            'sha256': 's', 'pit_estimado': False, 'nota': None, 'received_date': disponibilidade,
            'version': 1, 'anual': False, 'disponibilidade_tipo': 'recepcao_observada',
            'disponivel_desde': disponibilidade, 'data_recebimento_documento': None}


@pytest.mark.parametrize('cut,known', [
    ('2026-10-08T19:16:35.863119+00:00', False), ('2026-10-08T19:16:35.863120+00:00', True),
    ('2026-10-08T19:16:35.863121+00:00', True), (date(2026, 10, 7), False),
    (date(2026, 10, 8), True), (date(2026, 10, 9), True),
])
def test_selector_corte_exato_e_fim_de_dia_civil_nao_arredondam_recibo(cut, known, relogio_selector):
    cut = datetime.fromisoformat(cut) if isinstance(cut, str) else cut
    out = selecionar_pit(pd.DataFrame([fato()]), cut)
    assert (not out.empty) is known
    if known:
        assert pd.isna(out.iloc[0]['data_publicacao'])
        assert out.iloc[0]['disponivel_desde'].endswith('.863120+00:00')


def test_selector_preserva_dt_receb_civil_recusa_hora_naive_e_posse_futura(relogio_selector):
    f = fato() | {'received_date': '2026-07-29', 'data_recebimento_documento': '2026-07-29'}
    out = selecionar_pit(pd.DataFrame([f]), date(2026, 10, 8))
    assert out.iloc[0]['data_recebimento_documento'] == '2026-07-29'
    assert out.iloc[0]['received_date'] == '2026-07-29'
    assert pd.isna(out.iloc[0]['data_publicacao'])
    with pytest.raises(ValueError):
        selecionar_pit(pd.DataFrame([f]), datetime(2026, 10, 8))
    future = fato(disponibilidade='2099-10-08T19:16:35.863120+00:00')
    assert selecionar_pit(pd.DataFrame([future]), date(2099, 10, 9)).empty
    f.pop('disponivel_desde')
    assert selecionar_pit(pd.DataFrame([f]), date(2026, 10, 8)).empty


@pytest.mark.parametrize('reportado', [True, False])
def test_ebitda_metadados_so_de_participantes_da_formula(reportado):
    rows = [fato(item='ebit', value=7 if reportado else None, publication=None if not reportado else '2026-08-01'),
            fato(item='d_a', value=3, publication='2026-08-02'),
            fato(item='lucro_antes_ir', value=11, publication='2026-08-03'),
            fato(item='resultado_financeiro', value=4, publication='2026-08-04'),
            fato(item='ativo_total', value=99, publication=None)]
    out = _derivados(pd.DataFrame(rows))
    r = out[out['item'].eq('ebitda')].iloc[0]
    assert r['value'] == 10
    assert r['data_publicacao'] == ('2026-08-02' if reportado else '2026-08-04')


def test_ausencia_publicacao_em_participante_nao_e_max_skipnull():
    rows = [fato(item='cfo', value=13, publication=None), fato(item='capex', value=2, publication='2026-08-04')]
    r = _derivados(pd.DataFrame(rows)).iloc[0]
    assert r['value'] == 11 and r['data_publicacao'] is None


def test_refazer_divida_usa_so_formula_atual_e_preserva_publicacao_ausente():
    rows = [fato(item='divida_bruta', value=100), fato(item='caixa', value=20),
            fato(item='aplicacoes_cp', value=10), fato(item='ativo_total', value=900)]
    out = _refazer_derivados(pd.DataFrame(rows).rename(columns={'entidade': 'issuer_id'}))
    r = out[out['item'].eq('divida_liquida')].iloc[0]
    assert r['value'] == 70 and pd.isna(r['data_publicacao'])


def test_consumidor_ttm_preserva_ausencia_e_componentes_quatro_trimestres():
    rows = [fato(end=end, value=i + 1, publication=None if i == 0 else '2026-08-04')
            for i, end in enumerate(('2025-09-30', '2025-12-31', '2026-03-31', '2026-06-30'))]
    df = pd.DataFrame(rows).rename(columns={'entidade': 'issuer_id'})
    dem = Demonstrativos(df, 'BR_SIMULADO')
    value, row = dem.valor('receita')
    assert value == 10 and pd.isna(row['data_publicacao'])
    prov = _prov_linha(row, detalhar_fluxos=True)
    assert prov['data_publicacao'] is None and len(prov['componentes_fluxo']) == 4
    assert prov['componentes_fluxo'][0]['fonte']['data_publicacao'] is None
    assert prov['disponibilidade_tipo'] == 'recepcao_observada'


def test_componentes_json_csv_conservam_instante_integral_e_ausencia(relogio_selector):
    f = pd.DataFrame([fato(start='2026-01-01', end='2026-03-31', value=4),
                      fato(start='2026-01-01', end='2026-06-30', value=9)])
    out = selecionar_pit(f, date(2026, 10, 8))
    q = out[out['freq'].eq('Q') & out['period_end'].eq('2026-06-30')].iloc[0]
    assert q['value'] == 5 and pd.isna(q['data_publicacao'])
    prov = _prov_linha(q, detalhar_fluxos=True)
    assert len(prov['componentes_fluxo']) == 2
    assert all(c['fonte']['data_publicacao'] is None for c in prov['componentes_fluxo'])
    loaded = json.loads(out.to_json(orient='records', date_format='iso'))
    assert all(r['data_publicacao'] is None for r in loaded)
    assert '.863120+00:00' in out.to_csv(index=False)


def test_consumidor_ttm_identidade_anual_acumulados_preserva_ausencia():
    rows = [fato(end=end, value=value, publication=pub) | {'freq': freq}
            for end, value, pub, freq in [('2025-03-31', 20, None, 'Q'),
                                          ('2025-06-30', 25, '2025-08-01', 'Q'),
                                          ('2025-12-31', 100, '2026-03-01', 'A'),
                                          ('2026-03-31', 30, '2026-05-01', 'Q'),
                                          ('2026-06-30', 40, '2026-08-01', 'Q')]]
    dem = Demonstrativos(pd.DataFrame(rows).rename(columns={'entidade': 'issuer_id'}), 'BR_SIMULADO')
    value, row = dem.valor('receita')
    assert value == 125 and pd.isna(row['data_publicacao'])
    prov = _prov_linha(row, detalhar_fluxos=True)
    assert len(prov['componentes_fluxo']) == 5
    assert [c['coeficiente'] for c in prov['componentes_fluxo']] == [1.0, 1.0, 1.0, -1.0, -1.0]
    assert prov['componentes_fluxo'][3]['fonte']['data_publicacao'] is None


def test_max_data_publicacao_nao_promove_acoes_yahoo_a_publicacao_financeira():
    from cdp.cobertura.fontes import coletar
    from cdp.cobertura.insumos import preparar_emissor
    from cdp.cobertura.parametros import carregar_parametros
    from cdp.cobertura.qualidade import portoes_emissor
    from cdp.data.synthetic import make_synthetic_market

    day = date(2026, 10, 8)
    md = make_synthetic_market(seed=7, as_of=day)
    params = carregar_parametros()
    ids = list(md.universe.issuers.index)
    dados = coletar(md, day, ids, list(md.universe.lines.index), ['ILF', 'EWZ', 'EWW'])
    iid = next(i for i in ids if md.universe.issuers.loc[i, 'gics_sector'] != 'Financials'
               and i in set(dados.demonstrativos['issuer_id']))
    default = preparar_emissor(md, dados, params, iid, day)
    assert default['max_data_publicacao'] is not None
    df = dados.demonstrativos.copy()
    financial = df['issuer_id'].eq(iid) & ~df['item'].str.startswith('acoes_')
    df.loc[financial, 'data_publicacao'] = None
    df.loc[financial, 'disponibilidade_tipo'] = 'recepcao_observada'
    df.loc[financial, 'disponivel_desde'] = '2026-10-08T19:16:35.863120+00:00'
    observed = type(dados)(**{**dados.__dict__, 'demonstrativos': df})
    pac = preparar_emissor(md, observed, params, iid, day)
    assert pac['max_data_publicacao'] is None and pac['pit_ok'] is False
    gate = next(g for g in portoes_emissor(pac, {'metodos': [], 'tem_alvo': False}, params) if g['codigo'] == 'G2')
    assert gate['status'] == 'nao_aplicavel'


def test_cache_parser_nao_transporta_recibo_antigo_ao_optin(tmp_path, monkeypatch):
    from cdp.data import publico as p

    arq1, reg1, _, _ = publico(tmp_path / 'um')
    arq2 = Arquivo(tmp_path / 'dois', conhecimento_ate=datetime.max.replace(tzinfo=UTC))
    reg2 = arq2.gravar(reg1.chave, reg1.fonte, reg1.url, arq1.ler(reg1))
    assert reg1.sha256 == reg2.sha256 and reg1.data_coleta < reg2.data_coleta
    f = p._fatos_cvm_zip(reg1, arq1.ler(reg1), 'ITR', 2026, frozenset([CNPJ]))
    cached = p._fatos_cvm_zip(reg2, arq2.ler(reg2), 'ITR', 2026, frozenset([CNPJ]))
    assert cached is f and cached['data_coleta'].iloc[0] == pd.Timestamp(reg1.data_coleta)
    original = f.copy(deep=True)
    captured = []
    monkeypatch.setattr(p, 'mestre_publico', lambda *a, **k: pd.DataFrame({'cnpj': [CNPJ], 'cik': [None]}, index=['BR_SIMULADO']))
    monkeypatch.setattr(p, '_obter_cvm', lambda arq, doc, ano, *a: (reg2, arq2.ler(reg2)) if (doc, ano) == ('ITR', 2026) else None)
    real_selector = p.selecionar_pit

    def selector(facts, *a, **kw):
        captured.append(facts.copy(deep=True))
        return real_selector(facts, *a, **kw)

    monkeypatch.setattr(p, 'selecionar_pit', selector)
    # O saldo isolado não cria data-base Q: prova a entrada ordinária sem inventar fluxo.
    from cdp.data.synthetic import make_synthetic_market
    uni = make_synthetic_market(seed=7, as_of=date(2026, 10, 8)).universe
    iid = next(iter(uni.issuers.index))
    monkeypatch.setattr(p, 'mestre_publico', lambda *a, **k: pd.DataFrame({'cnpj': [CNPJ], 'cik': [None]}, index=[iid]))
    out = p.demonstrativos([iid], date(2026, 10, 8), root=arq2.raiz, universe=uni,
                          offline=True, complementar_yahoo=False, confirmar_magnitude_cvm=True)
    assert out.empty and len(captured) == 1
    assert captured[0]['disponibilidade_tipo'].eq('recepcao_observada').all()
    # data_coleta removida pelo coletor após construir o mapa; recibo correto fica na disponibilidade.
    assert pd.Timestamp(captured[0]['disponivel_desde'].iloc[0]) >= pd.Timestamp(reg2.data_coleta)
    pd.testing.assert_frame_equal(f, original)


@pytest.mark.parametrize('resource', ['indice', 'raw'])
@pytest.mark.parametrize('before_constructor', [True, False])
def test_links_preexistentes_e_posteriores_recusados_sem_seguir_alvo(tmp_path, resource, before_constructor):
    arq, reg, provider, row = publico(tmp_path / 'arquivo')
    path = arq.caminho_indice if resource == 'indice' else arq.base / reg.caminho
    real = tmp_path / ('real_' + resource)
    path.rename(real)
    path.symlink_to(real)
    with pytest.raises(ValueError):
        if before_constructor:
            ConfirmacaoCVM(Arquivo(arq.raiz, offline=True), [reg], {'BR_SIMULADO': CNPJ}, corte=datetime.now(UTC))
        else:
            provider.resolver(row)


@pytest.mark.parametrize('day,known', [(date(2026, 10, 8), True), (date(2026, 10, 7), False),
                                      (date(2026, 10, 9), True)])
def test_corte_civil_brasilia_usa_dia_local_sem_remover_hora_utc(day, known, relogio_selector):
    f = fato(disponibilidade='2026-10-09T02:55:00.123456+00:00')
    assert (not selecionar_pit(pd.DataFrame([f]), day).empty) is known


def test_misto_legacy_utc_conhecido_tem_corte_exato_date_civil_nao_vira_utc(relogio_selector):
    rows = [fato(item='receita'),
            fato(item='cfo') | {'disponibilidade_tipo': None, 'received_date': '2026-10-08T23:00:00+00:00'},
            fato(item='capex') | {'disponibilidade_tipo': None, 'received_date': date(2026, 10, 8)}]
    cut = datetime(2026, 10, 8, 20, tzinfo=UTC)
    out = selecionar_pit(pd.DataFrame(rows), date(2026, 10, 8), conhecimento_ate=cut)
    assert set(out['item']) == {'receita', 'capex'}
    out = selecionar_pit(pd.DataFrame(rows), cut)
    assert set(out['item']) == {'receita', 'capex'}
