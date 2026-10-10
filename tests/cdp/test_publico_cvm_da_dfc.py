"""DADOS SIMULADOS: classificação nativa CVM, retenção DVA e grãos separados."""
from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.data import publico as P
from cdp.data import publico_cvm as cvm
from cdp.data.publico_arquivo import RegistroArquivo
from cdp.data.publico_fatos import selecionar_pit

CNPJ = '00.000.000/0001-00'
FIM = '2025-12-31'


def row(cd, descricao, valor, *, fim=FIM, inicio='2025-01-01', moeda='REAL', versao='1', ordem='ÚLTIMO'):
    return {'CNPJ_CIA':CNPJ,'DT_REFER':fim,'VERSAO':versao,'MOEDA':moeda,'ESCALA_MOEDA':'MIL',
            'ORDEM_EXERC':ordem,'DT_INI_EXERC':inicio,'DT_FIM_EXERC':fim,'CD_CONTA':cd,
            'DS_CONTA':descricao,'VL_CONTA':str(valor)}


def corpo(dfc=(), dva=(), *, individual=False, dre=True):
    index = pd.DataFrame([{'CNPJ_CIA':CNPJ,'DT_REFER':r['DT_REFER'],'VERSAO':r['VERSAO'],
                          'DT_RECEB':'2026-03-01','LINK_DOC':'https://cvm.example/DADOS_SIMULADOS'}
                         for r in [*dfc,*dva]])
    streams = {'dfp_cia_aberta_2025.csv':index.drop_duplicates()}
    if dfc:
        streams['dfp_cia_aberta_DFC_MI_'+('ind' if individual else 'con')+'_2025.csv'] = pd.DataFrame(dfc)
    if dva:
        streams['dfp_cia_aberta_DVA_con_2025.csv'] = pd.DataFrame(dva)
    if dre:
        streams['dfp_cia_aberta_DRE_con_2025.csv'] = pd.DataFrame([
            row('3.05','Resultado Antes do Resultado Financeiro e dos Tributos',200),
            row('3.01','Receita de Venda de Bens e/ou Serviços',500)])
    out = io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for n,frame in streams.items():
            z.writestr(n,frame.to_csv(index=False,sep=';').encode('latin-1'))
    return out.getvalue()


def fatos(body):
    f=cvm.fatos_cvm(cvm.ler_zip_demonstracoes(body,'DFP',2025), 'DFP')
    return f.assign(fonte='CVM',sha256='a'*64)


def valor(f,item):
    r=f[f['item'].eq(item)]
    assert len(r)<=1
    return None if r.empty else float(r.iloc[0]['value'])


def da(descricao='Depreciação e amortização',value=100,**kw):
    return row('6.01.01.02',descricao,value,**kw)


def dva(value=-100,**kw):
    return row('7.04.01','Depreciação, Amortização e Exaustão',value,**kw)


def test_dva_mista_retida_nao_vira_da_nem_subtracao():
    f=fatos(corpo([da(value=1126),row('6.01.01.16','Perda por redução ao valor recuperável',683)], [dva(-1809)]))
    assert valor(f,'d_a')==1126000
    assert valor(f,'d_a_dfc')==1126000
    assert valor(f,'retencoes_dva')==-1809000
    for item in ('d_a','d_a_dfc'):
        assert f.loc[f['item'].eq(item),'demonstrativo'].tolist()==['DFC']
    s=selecionar_pit(f,date(2026,10,9))
    a=s[s['freq'].eq('A')]
    assert valor(a,'ebitda')==1326000  # somente EBIT + D&A identificada
    assert valor(a,'retencoes_dva')==-1809000


def test_exaustao_biologica_somada_sem_impairment():
    f=fatos(corpo([da(value=80),row('6.01.01.03','Exaustão dos ativos biológicos',20),
                  row('6.01.01.16','Perda por redução ao valor recuperável',30)], [dva(-130)]))
    assert valor(f,'d_a')==100000
    assert valor(f,'retencoes_dva')==-130000


@pytest.mark.parametrize('descricao',[
    'Depreciação, amortização e perda por redução ao valor recuperável',
    'Depreciação e amortização e impairment',
    'Depreciação e baixa de ativos',
    'Depreciação e outros ajustes',
    'Depreciação e juros',
])
def test_descricao_mista_ou_indeterminada_recusa_grupo_completo(descricao):
    f=fatos(corpo([da(descricao,40),row('6.01.01.03','Exaustão dos ativos biológicos',60)],[dva()]))
    assert valor(f,'d_a') is None
    assert valor(f,'d_a_dfc') is None
    assert valor(f,'retencoes_dva')==-100000
    assert any('D&A da DFC indeterminada' in q['msg'] for q in f.attrs['qa'])
    assert valor(selecionar_pit(f,date(2026,10,9)).query("freq=='A'"),'ebitda') is None


@pytest.mark.parametrize('dfc',[
    [da(value=-100)],
    [da(moeda='')],
    [da(moeda='REAL'),row('6.01.01.03','Exaustão dos ativos biológicos',20,moeda='DOLAR')],
])
def test_sinal_moeda_ausente_divergente_nao_viram_magnitude(dfc):
    f=fatos(corpo(dfc,[dva()]))
    assert valor(f,'d_a') is None
    assert valor(f,'d_a_dfc') is None
    assert valor(f,'retencoes_dva')==-100000


def test_dva_pura_sem_dfc_preservada_com_da_ausente():
    f=fatos(corpo([], [dva()]))
    assert valor(f,'retencoes_dva')==-100000
    assert valor(f,'d_a') is None
    assert valor(f,'d_a_dfc') is None
    assert valor(selecionar_pit(f,date(2026,10,9)).query("freq=='A'"),'ebitda') is None


def test_dfc_sem_dva_permanece_identificada():
    f=fatos(corpo([da()],[]))
    assert valor(f,'d_a')==100000
    assert valor(f,'d_a_dfc')==100000
    assert valor(f,'retencoes_dva') is None


def test_zero_explicito_diferente_de_ausencia():
    f=fatos(corpo([da(value=0),row('6.01','Caixa gerado nas operações',1)],[dva(0),row("7.01","Receitas",1)]))
    assert valor(f,'d_a')==0
    assert valor(f,'retencoes_dva')==0
    vazio=fatos(corpo([row('6.01','Caixa gerado nas operações',1)],[dva(-100)]))
    assert valor(vazio,'d_a') is None


def test_amortizacao_de_divida_nao_altera_da():
    f=fatos(corpo([da(),row('6.01.01.03','Amortização de empréstimos, financiamentos e debêntures',40)],[dva(-140)]))
    assert valor(f,'d_a')==100000


def test_nao_junta_dva_consolidada_com_dfc_individual():
    f=fatos(corpo([da()], [dva(-140)],individual=True))
    for item in ('d_a','d_a_dfc'):
        assert f.loc[f['item'].eq(item),'consolidado'].tolist()==[False]
    assert f.loc[f['item'].eq('retencoes_dva'),'consolidado'].tolist()==[True]


def test_periodo_moeda_versao_do_alias_sao_da_dfc():
    f=fatos(corpo([da(fim='2024-12-31',inicio='2024-01-01',moeda='DOLAR',versao='2')], [dva()]))
    da_row=f[f['item'].eq('d_a')].iloc[0]
    assert da_row['period_end']==pd.Timestamp('2024-12-31')
    assert da_row['currency']=='USD' and da_row['version']==2
    assert da_row['documento']=='DFP 2024-12-31 v2'
    assert da_row['demonstrativo']=='DFC'


def test_penultimo_nao_substitui_original():
    f=fatos(corpo([da()],[dva(-140),dva(-100,ordem='PENÚLTIMO')]))
    assert valor(f,'retencoes_dva')==-140000
    assert valor(f,'d_a')==100000


@pytest.mark.parametrize("mista", [False, True])
def test_coletor_normal_usa_parser_fisico_e_retencao_separada(monkeypatch, mista):
    import hashlib
    body=corpo([da("Depreciação e baixa de ativos" if mista else "Depreciação e amortização"),row('6.01.01.16','Perda por redução ao valor recuperável',40)],[dva(-140)])
    reg=RegistroArquivo('CVM/DFP/dfp_cia_aberta_2025.zip','CVM',cvm.url_zip('DFP',2025),
                        'DADOS_SIMULADOS.zip',hashlib.sha256(body).hexdigest(),len(body),
                        datetime(2026,10,8,tzinfo=UTC),'microseconds')
    class Transporte:
        offline=True
        falhas=[]
        conhecimento_ate=None
        def chaves(self): return [reg.chave]
        def obter(self,chave,fonte,url,baixar,**kw):
            if chave==reg.chave:
                assert fonte==reg.fonte and url==reg.url
                kw['validar'](body)
                return reg,body
            return None
    monkeypatch.setattr(P,'_arquivo',lambda *_a,**_k:Transporte())
    monkeypatch.setattr(P,'mestre_publico',lambda *_a,**_k:pd.DataFrame({'cnpj':[CNPJ],'cik':[None]},index=['BR_SIMULADO']))
    def proibido(*_a,**_k): raise AssertionError('rede proibida')
    uni=SimpleNamespace(issuers=pd.DataFrame({'gics_sector':['Industrials']},index=['BR_SIMULADO']))
    P._CACHE_CVM.clear()
    out=P.demonstrativos(['BR_SIMULADO'],date(2026,10,9),offline=True,universe=uni,
                        complementar_yahoo=False,http_get=proibido,yf_factory=proibido,anos=1)
    a=out[out['freq'].eq('A')]
    assert valor(a,'d_a')==(None if mista else 100000)
    assert valor(a,'d_a_dfc')==(None if mista else 100000)
    assert valor(a,'retencoes_dva')==-140000
    assert valor(a,'ebitda')==(None if mista else 300000)
    assert set(a['fonte'])=={'CVM'} and set(a['sha256'])=={reg.sha256}
    assert a[a['item'].eq('d_a')]['demonstrativo'].tolist()==([] if mista else ['DFC'])
    assert a[a['item'].eq('d_a')]['data_publicacao'].tolist()==([] if mista else [date(2026,3,1)])


@pytest.mark.parametrize("mista", [False, True])
def test_complemento_cvm_tem_paridade_e_nao_reintroduz_baixa(mista):
    from cdp.cobertura.fontes import _fatos_suplementares
    body=corpo([da("Depreciação e baixa de ativos" if mista else "Depreciação e amortização"),
                row("6.01.01.16","Perda por redução ao valor recuperável",40)], [dva(-140)])
    tabs=cvm.ler_zip_demonstracoes(body,"DFP",2025)
    supplement=_fatos_suplementares(tabs,"DFP")
    amount=valor(supplement,"d_a_dfc")
    assert amount==(None if mista else 100000)
    assert amount==valor(fatos(body),"d_a_dfc")
    if not mista:
        r=supplement[supplement["item"].eq("d_a_dfc")].iloc[0]
        assert r["consolidado"] and r["currency"]=="BRL"
        assert r["dt_ini"]==pd.Timestamp("2025-01-01") and r["versao"]==1


@pytest.mark.parametrize("dfc", [[], [da(value=-100)], [da(moeda="")],
    [da(moeda="REAL"),row("6.01.01.03","Exaustão dos ativos biológicos",20,moeda="DOLAR")]])
def test_complemento_preserva_ausencia_sinal_e_moeda_indeterminados(dfc):
    from cdp.cobertura.fontes import _fatos_suplementares
    body=corpo(dfc,[dva()])
    s=_fatos_suplementares(cvm.ler_zip_demonstracoes(body,"DFP",2025),"DFP")
    assert valor(s,"d_a_dfc") is None
    assert valor(fatos(body),"d_a_dfc") is None
