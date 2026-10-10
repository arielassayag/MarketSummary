"""DADOS SIMULADOS: vazio documental não aborta a API pública multi-arquivo.

Fixtures regulares produzidas antes da custódia, bibliotecas e APIs normais.
Ausente não é zero. Não certifica classificação universal, PIT ou eficácia.
"""
import io
import re
import zipfile
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
import test_capital_semantica_optin as C
import test_publico as T

from cdp.cobertura import fontes as F
from cdp.data import publico as P
from cdp.data import publico_yahoo as YH
from cdp.data.publico_cvm import url_zip

DAY=date(2026,10,9)


def mista(body):
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        files={n:z.read(n) for n in z.namelist()}
    for name in files:
        if '_DFC_MI_con_' not in name:
            continue
        rows=pd.read_csv(io.BytesIO(files[name]),sep=';',encoding='latin1',dtype=str)
        mask=rows.DS_CONTA.str.contains('deprecia|amortiza|exaust',case=False,na=False)
        rows=rows[mask|rows.CD_CONTA.eq('6.01')].copy()
        rows.loc[rows.CD_CONTA.ne('6.01'),'DS_CONTA']='Depreciação e baixa de ativos'
        files[name]=rows.to_csv(index=False,sep=';').encode('latin1')
    return T.fx._zip(files)


def fixture(tmp_path,monkeypatch,*,todos_vazios=False):
    dfp,itr=T.fx._dfp,T.fx._itr
    class ArquivoFixture(T.fx.Arquivo):
        def gravar(self,chave,fonte,url,conteudo,**kwargs):
            match=re.fullmatch(r'CVM/(DFP|ITR)/(?:dfp|itr)_cia_aberta_(\d{4})\.zip',chave)
            if match:
                url=url_zip(match[1],int(match[2]))
            return super().gravar(chave,fonte,url,conteudo,**kwargs)
    # Recibos DADOS SIMULADOS, URI estrutural requerida pela política observada.
    # A classe normal Arquivo da API leitora não é substituída.
    monkeypatch.setattr(T.fx,'Arquivo',ArquivoFixture)
    monkeypatch.setattr(T.fx,'_dfp',lambda year,*a,**k:
                        mista(dfp(year,*a,**k)) if todos_vazios or year==2025 else dfp(year,*a,**k))
    if todos_vazios:
        monkeypatch.setattr(T.fx,'_itr',lambda year:mista(itr(year)))
    out=T.fx.construir_arquivo(tmp_path)
    monkeypatch.setattr(P,'default_http_get',T._sem_rede)
    monkeypatch.setattr(YH,'_yf_ticker',T._sem_rede)
    monkeypatch.setattr(P,'_universo',lambda universe=None:universe or out['universo'])
    out['root']=tmp_path
    out['corte']=datetime.now(UTC)+timedelta(seconds=5)
    return out


def politica():
    return SimpleNamespace(sec=lambda key:{
        'projecao':{'resultado_corte_metodo':'base_preco_conhecimento_explicitos'},
        'qualidade':{'demonstrativos_disponibilidade_metodo':'recepcao_observada'},
    }.get(key,{}))


@pytest.mark.parametrize('owners,capital',[(False,False),(True,False),(False,True),(True,True)])
def test_DFP_suplementar_vazia_com_ITR_presente_na_API_normal(tmp_path,monkeypatch,owners,capital):
    out=fixture(tmp_path,monkeypatch)
    md=SimpleNamespace(is_synthetic=False,universe=out['universo'],as_of=DAY)
    with C.guarda('regressao-vazio-ITR') as counts:
        sup=F.contas_suplementares_cvm(['BR_SIMU'],DAY,tmp_path,universe=out['universo'])
        assert not sup.empty and sup.issuer_id.eq('BR_SIMU').all()
        assert sup.value.notna().all() and not sup.value.eq(0).any()
        annual=sup[sup.freq.eq('A')&sup.period_end.eq(pd.Timestamp('2025-12-31'))]
        assert annual.empty
        # A ausência do exercício impede a identidade TTM recente, não vira zero.
        assert sup[sup.freq.eq('TTM')&sup.period_end.eq(pd.Timestamp('2026-06-30'))].empty
        args=dict(offline=True,raiz=tmp_path,params=politica(),conhecimento_ate=out['corte'],
                  patrimonio_owners_observado=owners,preservar_semantica_capital=capital)
        result=F.coletar(md,DAY,['BR_SIMU'],['SIMU3.SA'],[],**args)
        assert not result.demonstrativos.empty
        a=result.demonstrativos[result.demonstrativos.freq.eq('A')
                              &result.demonstrativos.period_end.eq(pd.Timestamp('2025-12-31'))]
        assert not a.item.isin(['d_a','d_a_dfc','ebitda']).any()
        assert a.item.eq('retencoes_dva').any()
        if capital:
            assert result.capital_semantica is not None and not result.capital_semantica.empty
        else:
            assert result.capital_semantica is None
    assert counts['reads']>0 and all(counts[k]==0 for k in counts if k!='reads')


def test_todas_suplementares_vazias_retornam_vazio_sem_zero(tmp_path,monkeypatch):
    out=fixture(tmp_path,monkeypatch,todos_vazios=True)
    md=SimpleNamespace(is_synthetic=False,universe=out['universo'],as_of=DAY)
    with C.guarda('regressao-todas-vazias') as counts:
        sup=F.contas_suplementares_cvm(['BR_SIMU'],DAY,tmp_path,universe=out['universo'])
        assert sup.empty and list(sup.columns)==F.COLS_DEMONSTRATIVOS
        result=F.coletar(md,DAY,['BR_SIMU'],['SIMU3.SA'],[],offline=True,raiz=tmp_path)
        assert not result.demonstrativos.empty
        assert not result.demonstrativos.item.isin(['d_a','d_a_dfc','ebitda']).any()
        assert result.demonstrativos.item.eq('retencoes_dva').any()
    assert all(counts[k]==0 for k in counts if k!='reads')
