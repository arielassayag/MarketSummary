"""DADOS SIMULADOS: transporte de capital, sem nova escolha financeira ou fonte live."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import os
import zipfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from cdp_audit_guardas import registrar, remover

from cdp.cobertura.fontes import capital_fre, capital_oficial, coletar, csv_canonico
from cdp.cobertura.insumos import conciliar_contagem, preparar_emissor
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.qualidade import _g13c
from cdp.data import publico as P
from cdp.data import publico_cvm as cvm
from cdp.data import publico_yahoo as yh
from cdp.data.publico_arquivo import RegistroArquivo
from cdp.data.publico_capital_semantica import contexto, ler, serializar, vincular_registro
from cdp.data.synthetic import make_synthetic_market

_SPEC = importlib.util.spec_from_file_location('fixture_capital_simulado',
    Path(__file__).resolve().parents[1] / 'fixtures/publico/construir.py')
fx = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fx)
AVISO = 'DADOS SIMULADOS'
COL = 'semantica_capital'
DAY = date(2026, 10, 9)
GUARDAS_REALIZADAS = []


def sem_rede(*_args, **_kwargs):
    raise AssertionError('GET proibida em prova offline')


@contextmanager
def guarda(uso='API'):
    """Ativa só durante a API; escrita de fixture e recibos é anterior/posterior."""
    counts = {'reads': 0, 'writes': 0, 'network': 0, 'process': 0, 'mutations': 0}
    mutations = {'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.chmod', 'os.utime', 'os.link', 'os.symlink'}

    def audit(event, args):
        if event == 'open':
            _, mode, flags = args
            write = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            counts['writes' if write else 'reads'] += 1
            if write:
                raise RuntimeError('Writer proibido')
        elif event in mutations:
            counts['mutations'] += 1
            raise RuntimeError('Mutação proibida')
        elif event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo'}:
            counts['network'] += 1
            raise RuntimeError('Rede proibida')
        elif event in {'subprocess.Popen', 'os.system', 'os.posix_spawn'}:
            counts['process'] += 1
            raise RuntimeError('Processo proibido')
    token = registrar(audit)
    try:
        yield counts
    finally:
        remover(token)
        GUARDAS_REALIZADAS.append({'uso': uso, **counts})


def limpo(frame):
    result = frame.drop(columns=[COL], errors='ignore').copy()
    result.attrs = {k: v for k, v in frame.attrs.items() if k != 'capital_semantica'}
    return result


def igual(a, b):
    pd.testing.assert_frame_equal(limpo(a), limpo(b), check_exact=True)
    assert limpo(a).attrs == limpo(b).attrs
    assert csv_canonico(limpo(a)) == csv_canonico(limpo(b))


def conteudo(doc='ITR', ano=2026):
    return fx._itr(ano) if doc == 'ITR' else fx._dfp(ano, '2026-03-12')


def trocar_capital(body, **changes):
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    name = next(n for n in files if 'composicao_capital' in n)
    raw = pd.read_csv(io.BytesIO(files[name]), sep=';', encoding='latin1', dtype=str, keep_default_na=False)
    for key, value in changes.items():
        raw.loc[raw.CNPJ_CIA.eq(fx.CNPJ_IND), key] = value
    files[name] = raw.to_csv(sep=';', index=False).encode('latin1')
    return fx._zip(files)


def fre_zip(total='001163046411', *, missing=False):
    if missing:
        return fx._fre()
    header = ['ID_Documento', 'CNPJ_Companhia', 'Data_Referencia', 'Versao', 'Tipo_Capital',
              'Data_Autorizacao_Aprovacao', 'Quantidade_Acoes_Ordinarias',
              'Quantidade_Acoes_Preferenciais', 'Quantidade_Total_Acoes']
    rows = [ ['1', fx.CNPJ_IND, '2026-12-31', '02', tipo, '2025-05-20', total, '0000', total]
             for tipo in ('Capital Integralizado', 'Capital Emitido', 'Capital Subscrito')]
    return fx._zip({'fre_cia_aberta_capital_social_2026.csv': fx._csv(header, rows),
                   'fre_cia_aberta_2026.csv': fx._csv(['ID_DOC', 'DT_RECEB', 'LINK_DOC'],
                       [['1', '2026-08-11', 'https://example.org/DADOS-SIMULADOS/fre']])})


@pytest.fixture()
def arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(P, 'default_http_get', sem_rede)
    monkeypatch.setattr(yh, '_yf_ticker', sem_rede)
    result = fx.construir_arquivo(tmp_path)
    result['root'] = tmp_path
    return result


@pytest.mark.parametrize('doc,ano', [('ITR', 2026), ('ITR', 2025), ('DFP', 2025), ('DFP', 2024)])
def test_api_cvm_preserva_financeiro_e_lexemas(doc, ano):
    body = conteudo(doc, ano)
    before = cvm.fatos_cvm(cvm.ler_zip_demonstracoes(body, doc, ano), doc)
    tables = cvm.ler_zip_demonstracoes(body, doc, ano, preservar_semantica_capital=True)
    after = cvm.fatos_cvm(tables, doc, preservar_semantica_capital=True)
    igual(before, after)
    contexts = [ler(v) for v in after.attrs['capital_semantica']]
    assert contexts and COL not in before
    raw = next(c for c in contexts if c['cnpj'] == fx.CNPJ_IND)
    assert raw['data_estoque'] == raw['documento_data_referencia']
    assert raw['recepcao_observada_UTC'] is None and raw['data_publicacao_primaria'] is None
    assert raw['fonte']['arquivo_sha256'] == hashlib.sha256(body).hexdigest()
    assert raw['unidade_reportada'] is raw['escala_reportada'] is None
    assert raw['classe_economica'] is raw['conflitos_documentais'] is None
    assert raw['registro_csv_1based'] >= 2 and raw['linha_fisica_csv'] is None
    selected = after.loc[after.entidade.eq(fx.CNPJ_IND) & after.item.eq('acoes_em_circulacao')].iloc[-1]
    semantic = ler(selected[COL])
    assert semantic['formula_legada'] == 'QT_ACAO_TOTAL_CAP_INTEGR - QT_ACAO_TOTAL_TESOURO'
    assert semantic['politica_unidade_legada'] is not None and semantic['escala_reportada'] is None


@pytest.mark.parametrize('lex', ['000100000', ' 100000 ', '100000.00'])
def test_lexema_nao_perde_zeros_espacos_ou_decimal(lex):
    body = trocar_capital(conteudo(), QT_ACAO_TOTAL_CAP_INTEGR=lex)
    tables = cvm.ler_zip_demonstracoes(body, 'ITR', 2026, {fx.CNPJ_IND}, preservar_semantica_capital=True)
    frame = cvm.fatos_cvm(tables, 'ITR', preservar_semantica_capital=True)
    assert frame.attrs['capital_semantica']
    for value in frame.attrs['capital_semantica']:
        ctx = ler(value)
        assert ctx['cnpj'] == fx.CNPJ_IND
        raw = next(c for c in ctx['componentes'] if c['campo'] == 'QT_ACAO_TOTAL_CAP_INTEGR')
        assert raw['valor_reportado_lexema'] == lex
        assert raw['valor_entrada_normalizada_texto'] is None


@pytest.mark.parametrize('field,value', [('UNIDADE_QT_ACAO', 'acoes'), ('ESCALA_QT_ACAO', 'MILHARES')])
def test_unidade_escala_apenas_campos_explicitos_simulados(field, value):
    body = trocar_capital(conteudo(), **{field: value})
    tables = cvm.ler_zip_demonstracoes(body, 'ITR', 2026, preservar_semantica_capital=True)
    frame = cvm.fatos_cvm(tables, 'ITR', preservar_semantica_capital=True)
    ctx = next(ler(v) for v in frame.attrs['capital_semantica'] if ler(v)['cnpj'] == fx.CNPJ_IND)
    key = 'unidade_reportada' if field.startswith('UNIDADE') else 'escala_reportada'
    assert ctx[key] == {'campo': field, 'lexema': value}
    assert ctx['conceito_validado'] is None


@pytest.mark.parametrize('field', ['QT_ACAO_TOTAL_TESOURO', 'QT_ACAO_TOTAL_CAP_INTEGR'])
def test_raw_sem_quantidade_nao_cria_fato_financeiro(field):
    body = trocar_capital(conteudo(), **{field: ''})
    tables = cvm.ler_zip_demonstracoes(body, 'ITR', 2026, preservar_semantica_capital=True)
    before = cvm.fatos_cvm(tables, 'ITR')
    after = cvm.fatos_cvm(tables, 'ITR', preservar_semantica_capital=True)
    igual(before, after)
    ctx = next(ler(v) for v in after.attrs['capital_semantica'] if ler(v)['cnpj'] == fx.CNPJ_IND)
    assert ctx['campos_fisicos'][field] == ''
    assert not after.loc[after.entidade.eq(fx.CNPJ_IND), 'item'].isin(['acoes_em_circulacao']).any()


@pytest.mark.parametrize('index_mode', ['ausente', 'ambiguo'])
def test_indice_sem_vinculo_unico_nao_inventa_url_ou_recepcao(index_mode):
    tables = cvm.ler_zip_demonstracoes(conteudo(), 'ITR', 2026, preservar_semantica_capital=True)
    idx = tables['index']
    tables['index'] = idx.iloc[:0] if index_mode == 'ausente' else pd.concat([idx, idx], ignore_index=True)
    frame = cvm.fatos_cvm(tables, 'ITR', preservar_semantica_capital=True)
    for value in frame.attrs['capital_semantica']:
        ctx = ler(value)
        assert ctx['fonte']['url_documento'] is None and ctx['data_recebimento_documento'] is None


@pytest.mark.parametrize('numeric', [False, True])
def test_dataframe_manual_nao_recebe_localizador_ou_lexema_fabricado(numeric):
    row = {'CNPJ_CIA': fx.CNPJ_IND, 'DT_REFER': '2026-06-30', 'VERSAO': '1',
           'QT_ACAO_TOTAL_CAP_INTEGR': 1000 if numeric else '01000', 'QT_ACAO_TOTAL_TESOURO': '00100'}
    ctx = ler(contexto(row, tipo='COMPOSICAO'))
    raw = next(c for c in ctx['componentes'] if c['campo'] == 'QT_ACAO_TOTAL_CAP_INTEGR')
    assert raw['valor_reportado_lexema'] == (None if numeric else '01000')
    assert ctx['fonte'] is None and ctx['registro_csv_1based'] is None
    assert ctx['unidade_reportada'] is None and ctx['escala_reportada'] is None


@pytest.mark.parametrize('total', ['001163046411', '', '0'])
def test_fre_stock_aprovacao_referencia_e_ausencia_distintas(total):
    body = fre_zip(total)
    before = capital_fre(body, 2026)
    after = capital_fre(body, 2026, preservar_semantica_capital=True)
    igual(before, after)
    contexts = [ler(v) for v in after.attrs['capital_semantica']]
    assert len(contexts) == 3
    for ctx in contexts:
        assert ctx['data_estoque'] is None
        assert ctx['data_aprovacao'] == '2025-05-20'
        assert ctx['documento_data_referencia'] == '2026-12-31'
        assert ctx['versao_reportada_lexema'] == '02'
        assert ctx['classe_economica'] is None and ctx['direitos'] is None
        assert ctx['componentes'][0]['valor_reportado_lexema'] == total
        assert ctx['componentes'][2]['valor_reportado_lexema'] == '0000'
        assert ctx['unidade_reportada'] is None and ctx['escala_reportada'] is None
    assert len(after) == (3 if total not in ('', '0') else 0)


def test_fre_layout_ausente_preserva_default_e_ausencia():
    before = capital_fre(fre_zip(missing=True), 2026)
    after = capital_fre(fre_zip(missing=True), 2026, preservar_semantica_capital=True)
    igual(before, after)
    assert after.empty and COL in after and 'capital_semantica' not in before.attrs


def test_capital_oficial_recibo_real_tmp_e_membros(arquivo):
    body = fre_zip()
    reg = arquivo['arquivo'].gravar('CVM/FRE/fre_cia_aberta_2026.zip', 'CVM',
          'https://example.org/DADOS-SIMULADOS/FRE.zip', body, data_coleta=fx.COLETA + timedelta(seconds=1))
    before = capital_oficial(['BR_SIMU'], DAY, arquivo['root'], universe=arquivo['universo'])
    with guarda() as counts:
        after = capital_oficial(['BR_SIMU'], DAY, arquivo['root'], universe=arquivo['universo'], preservar_semantica_capital=True)
    igual(before, after)
    assert counts['reads'] > 0 and all(counts[k] == 0 for k in counts if k != 'reads')
    ctx = ler(after.iloc[0][COL])
    assert ctx['issuer_id_cadastro'] == 'BR_SIMU'
    assert ctx['recepcao_observada_UTC'] == reg.data_coleta.isoformat()
    assert ctx['data_publicacao_primaria'] is None and ctx['data_estoque'] is None
    assert ctx['fonte']['arquivo_sha256'] == reg.sha256
    assert ctx['fonte']['url_arquivo'] == reg.url
    assert ctx['fonte']['membro_sha256'] != ctx['fonte']['indice_membro_sha256']


@pytest.mark.parametrize('ids', [['BR_SIMU'], ['BR_SIMU', 'BR_BSIM'], ['PE_SAND'], ['MX_SIMU'], ['desconhecido']])
def test_demonstrativos_default_warm_optin_cache_e_financeiro_literal(arquivo, ids):
    kw = dict(offline=True, root=arquivo['root'], universe=arquivo['universo'], http_get=sem_rede, yf_factory=sem_rede)
    before = P.demonstrativos(ids, DAY, **kw)
    cache = copy.deepcopy(P._CACHE_CVM)
    with guarda() as counts:
        after = P.demonstrativos(ids, DAY, preservar_semantica_capital=True, **kw)
    again = P.demonstrativos(ids, DAY, **kw)
    igual(before, after)
    igual(before, again)
    assert set(P._CACHE_CVM) == set(cache)
    for key in cache:
        pd.testing.assert_frame_equal(cache[key], P._CACHE_CVM[key], check_exact=True)
        assert cache[key].attrs == P._CACHE_CVM[key].attrs
    assert all(counts[k] == 0 for k in counts if k != 'reads')
    for value in after.attrs.get('capital_semantica', []):
        ctx = ler(value)
        assert ctx['issuer_id_cadastro'] in ids and ctx['recepcao_observada_UTC'] == fx.COLETA.isoformat()
    if ids == ['BR_SIMU']:
        assert after.attrs['capital_semantica']
        assert after.loc[after.item.eq('acoes_em_circulacao'), COL].notna().any()


@pytest.mark.parametrize('schema', ['desconhecido', None])
def test_schema_nao_e_aceito(schema):
    ctx = ler(contexto({}, tipo='COMPOSICAO'))
    ctx['schema'] = schema
    with pytest.raises(ValueError):
        ler(serializar(ctx))


@pytest.mark.parametrize('field', ['conceito_validado', 'classe_economica', 'direitos', 'ponte_liquida_validada'])
def test_nao_aceita_confirmacao_documental_que_o_contrato_nao_tem(field):
    ctx = ler(contexto({}, tipo='COMPOSICAO'))
    ctx[field] = 'DADOS SIMULADOS: alegação sem fonte'
    with pytest.raises(ValueError):
        ler(serializar(ctx))


def test_vinculo_sha_contraditorio_recusa():
    ctx = contexto({}, tipo='COMPOSICAO', fonte={'arquivo_sha256': '0' * 64})
    reg = RegistroArquivo(chave='simulado', fonte='CVM', url='https://example.org', caminho='simulado',
         sha256='1' * 64, bytes=1, data_coleta=fx.COLETA)
    with pytest.raises(ValueError, match='SHA'):
        vincular_registro(ctx, reg)


@pytest.mark.parametrize('value', ['True', 1, None])
def test_opcao_exige_bool(value):
    with pytest.raises(ValueError):
        cvm.ler_zip_demonstracoes(conteudo(), 'ITR', 2026, preservar_semantica_capital=value)
    with pytest.raises(ValueError):
        capital_fre(fre_zip(), 2026, preservar_semantica_capital=value)
    with pytest.raises(ValueError):
        P.demonstrativos([], DAY, preservar_semantica_capital=value)


@pytest.mark.parametrize('mode', ['com_metadado', 'ausente', 'CSV'])
def test_preparar_emissor_preserva_financeiro_g13c_e_fontes_g2(mode):
    md = make_synthetic_market(seed=7, as_of=DAY)
    ids, lines = list(md.universe.issuers.index), list(md.universe.lines.index)
    before = coletar(md, DAY, ids, lines, [])
    opt = coletar(md, DAY, ids, lines, [], preservar_semantica_capital=True)
    assert opt.capital_semantica.empty
    iid = 'SIM003'
    dem, cap = opt.demonstrativos.copy(deep=True), opt.capital_oficial.copy(deep=True)
    observation = None
    if mode != 'ausente':
        observation = contexto({'CNPJ_CIA': fx.CNPJ_IND, 'DT_REFER': '2026-06-30', 'VERSAO': '01',
            'QT_ACAO_TOTAL_CAP_INTEGR': '0100000', 'QT_ACAO_TOTAL_TESOURO': '0001'}, tipo='COMPOSICAO')
        observation = serializar({**ler(observation), 'issuer_id_cadastro': iid})
        dem.loc[dem.issuer_id.eq(iid) & dem.item.isin(['acoes_em_circulacao', 'acoes_emitidas', 'acoes_tesouraria']), COL] = observation
        cap.loc[cap.issuer_id.eq(iid), COL] = observation
    ledger = pd.DataFrame({COL: [] if observation is None else [observation]})
    if mode == 'CSV':
        ledger = pd.read_csv(io.StringIO(csv_canonico(ledger)), dtype=str, keep_default_na=False)
        dem = pd.read_csv(io.StringIO(csv_canonico(dem)), keep_default_na=False)
        # O round-trip testado é do sidecar: quadro financeiro conserva os tipos originais.
        dem = opt.demonstrativos.copy(deep=True)
        dem.loc[dem.issuer_id.eq(iid) & dem.item.eq('acoes_em_circulacao'), COL] = observation
    opt = replace(opt, demonstrativos=dem, capital_oficial=cap, capital_semantica=ledger)
    params = carregar_parametros()
    original = preparar_emissor(md, before, params, iid, DAY)
    result = preparar_emissor(md, opt, params, iid, DAY)
    semantic = result['contagem'].pop('semantica')
    assert result == original
    assert _g13c(result) == _g13c(original)
    assert semantic['fontes_efetivas_G2_legadas'] == original['contagem'].get('fontes_participantes')
    assert len(semantic['participantes']) == 3
    assert semantic['conflitos_documentais'] is None and semantic['ratio_documental_contemporaneo'] is None
    assert semantic['classe_subjacente'] is None and semantic['ponte_liquida_validada'] is None
    assert semantic['observacoes_documentais_recebidas'] == ([] if observation is None else [ler(observation)])
    assert 'capital_semantica' not in before.tabelas() and 'capital_semantica' in opt.tabelas()


@pytest.mark.parametrize('values', [(978.8e6, 3290e6, 1163e6), (100e6, 100e6, 100e6), (None, None, None)])
def test_conciliar_e_g13c_nao_validam_conceito_por_proximidade(values):
    dem, market, fre = values
    official = None if fre is None else {'qtd_total': fre, 'data_ref': '2026-12-31', 'versao': 1,
        'data_publicacao': '2026-08-11', 'tipo_capital': 'Capital Integralizado', 'fonte': {'fonte': 'CVM'}}
    params = carregar_parametros()
    n, _, _, count = conciliar_contagem(dem, 1.0, market, official, params, {'fonte': 'CVM'}, {'fonte': 'YAHOO'}, False)
    if dem == 978.8e6:
        assert count['status'] == 'bloqueio' and _g13c({'contagem': count, 'unidades': n})['status'] == 'bloqueio'
    elif dem is None:
        assert n is None and all(v is None for v in count['candidatos'].values())
    else:
        assert count['status'] == 'ok'
    assert 'semantica' not in count


def test_coletar_publico_normal_ledger_sem_alterar_tabelas(arquivo, monkeypatch):
    from types import SimpleNamespace
    md = SimpleNamespace(is_synthetic=False, universe=arquivo['universo'], as_of=DAY)
    monkeypatch.setattr(P, '_universo', lambda universe=None: universe or arquivo['universo'])
    ids = ['BR_SIMU', 'BR_BSIM']
    tickers = ['SIMU3.SA', 'BSIM4.SA']
    before = coletar(md, DAY, ids, tickers, [], offline=True, raiz=arquivo['root'])
    with guarda() as counts:
        after = coletar(md, DAY, ids, tickers, [], offline=True, raiz=arquivo['root'], preservar_semantica_capital=True)
    assert all(counts[k] == 0 for k in counts if k != 'reads')
    assert counts['reads'] > 0 and not after.capital_semantica.empty
    assert set(after.tabelas()) == set(before.tabelas()) | {'capital_semantica'}
    for name, frame in before.tabelas().items():
        igual(frame, after.tabelas()[name])
    for value in after.capital_semantica[COL]:
        assert ler(value)['issuer_id_cadastro'] in ids


@pytest.mark.parametrize('effect', ['writer', 'socket', 'process', 'remove'])
def test_guarda_recusa_efeitos_reais_sem_efetivar(effect, tmp_path):
    import socket
    import subprocess
    path = tmp_path / 'DADOS_SIMULADOS.txt'
    path.write_text(AVISO)
    with guarda('controle negativo: ' + effect) as counts:
        with pytest.raises(RuntimeError):
            if effect == 'writer':
                path.write_text('adulterado')
            elif effect == 'socket':
                with socket.socket() as sock:
                    sock.connect(('127.0.0.1', 9))
            elif effect == 'process':
                subprocess.run(['processo-proibido'], check=False)
            else:
                path.unlink()
    assert path.read_text() == AVISO
    key = {'writer': 'writes', 'socket': 'network', 'process': 'process', 'remove': 'mutations'}[effect]
    assert counts[key] == 1


def test_guarda_permite_leitura_e_retira_politica_ao_sair(tmp_path):
    path = tmp_path / 'DADOS_SIMULADOS.txt'
    path.write_text(AVISO)
    with guarda('leitura e pós-contexto') as counts:
        assert path.read_text() == AVISO
    assert counts['reads'] > 0 and counts['writes'] == 0
    path.write_text('DADOS SIMULADOS: pós-contexto')
    assert path.read_text().endswith('pós-contexto')


@pytest.mark.parametrize('precision', ['seconds', 'microseconds'])
def test_receipt_conserva_precisao_e_limite_sem_publicacao(precision):
    reg = RegistroArquivo(chave='CVM/SIMULADO/x', fonte='CVM', url=None, caminho='simulado',
        sha256='1' * 64, bytes=1, data_coleta=fx.COLETA, precisao=precision)
    ctx = ler(vincular_registro(contexto({}, tipo='COMPOSICAO'), reg))
    assert ctx['precisao_recepcao_registro'] == precision
    assert ctx['recepcao_observada_UTC'] == reg.data_coleta.isoformat()
    assert ctx['limite_recepcao_UTC'] == reg.limite_captura.isoformat()
    assert ctx['data_publicacao_primaria'] is None


def test_registro_manual_sem_fuso_nao_ganha_utc():
    reg = RegistroArquivo(chave='CVM/SIMULADO/x', fonte='CVM', url=None, caminho='simulado',
        sha256='1' * 64, bytes=1, data_coleta=fx.COLETA.replace(tzinfo=None))
    ctx = ler(vincular_registro(contexto({}, tipo='COMPOSICAO'), reg))
    assert ctx['recepcao_observada_UTC'] is None and ctx['limite_recepcao_UTC'] is None


def test_contradicao_fisica_classe_e_total_preservada_sem_rotular_resolvida():
    body = trocar_capital(conteudo(), QT_ACAO_ORDIN_CAP_INTEGR='2', QT_ACAO_PREF_CAP_INTEGR='3', QT_ACAO_TOTAL_CAP_INTEGR='0100000')
    tables = cvm.ler_zip_demonstracoes(body, 'ITR', 2026, preservar_semantica_capital=True)
    before = cvm.fatos_cvm(tables, 'ITR')
    after = cvm.fatos_cvm(tables, 'ITR', preservar_semantica_capital=True)
    igual(before, after)
    ctx = next(ler(v) for v in after.attrs['capital_semantica'] if ler(v)['cnpj'] == fx.CNPJ_IND)
    physical = {c['campo']: c['valor_reportado_lexema'] for c in ctx['componentes']}
    assert physical['QT_ACAO_ORDIN_CAP_INTEGR'] == '2' and physical['QT_ACAO_PREF_CAP_INTEGR'] == '3'
    assert physical['QT_ACAO_TOTAL_CAP_INTEGR'] == '0100000'
    assert ctx['conflitos_documentais'] is None and ctx['classe_economica'] is None


@pytest.mark.parametrize('fonte', ['CVM', 'SEC', 'RI'])
def test_metadata_separado_preserva_participantes_e_conferencia_g2(fonte):
    from test_g2_v2_fluxo_nativo_revisor import construir_entrada

    from cdp.cobertura.disponibilidade_demonstrativos import conferir
    md, dados, params, _, _ = construir_entrada(fonte)
    original = preparar_emissor(md, dados, params, 'SIM003', date(2026, 10, 8))
    # Opção explicitamente representada por sidecar vazio: não acrescenta fonte G2.
    opted = replace(dados, capital_semantica=pd.DataFrame(columns=[COL]))
    result = preparar_emissor(md, opted, params, 'SIM003', date(2026, 10, 8))
    result['contagem'].pop('semantica')
    assert result == original and conferir(result) == conferir(original)
    assert result['contagem']['fontes_participantes'] == original['contagem']['fontes_participantes']
    assert result['disponibilidade_demonstrativos'] == original['disponibilidade_demonstrativos']
