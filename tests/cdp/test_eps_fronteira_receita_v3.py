"""DADOS SIMULADOS: receita injetada na linha EPS-only é recusada no consumo real."""
import io
import os
from contextlib import contextmanager
from decimal import Decimal

import pandas as pd
import pytest
import test_publico_eps_por_periodo as f

from cdp.cobertura.fontes import coletar, csv_canonico
from cdp.data.publico_eps import autenticar_linha

# isort: split
from cdp_audit_guardas import registrar, remover


@contextmanager
def guarda():
    state={"active":True,"write":0,"network":0,"process":0,"mutation":0,"reads":0}
    def audit(event,args):
        if not state["active"]:
            return
        group=None
        if event=="open":
            _,mode,flags=args
            if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
                group='write'
            else:
                state['reads']+=1
        elif event.startswith('socket.'):
            group='network'
        elif event.startswith(('subprocess.','os.exec','os.spawn')) or event in {'os.system','os.fork'}:
            group='process'
        elif event in {'os.mkdir','os.remove','os.rename','os.rmdir','os.utime','os.chmod','os.link','os.symlink'}:
            group='mutation'
        if group:
            state[group]+=1
            raise RuntimeError(f'Guarda API EPS: {group}')
    token = registrar(audit)
    try:
        yield state
    finally:
        state['active']=False
        remover(token)
        assert all(state[k]==0 for k in ('write','network','process','mutation'))


def preparar(root, *, eps_ausente=False):
    doc=f.documento()
    if eps_ausente:
        for cell in f.trend(doc):
            cell['earningsEstimate']['avg'].pop('raw')
    archive,record,body=f.arquivo(root,f.corpo(doc))
    indice=(archive.base/'indice.jsonl').read_bytes()
    with guarda():
        data=coletar(f.mercado(),f.DATA,[],[f.TICKER],[],offline=True,raiz=root,
            eps_por_periodo=True,conhecimento_ate=f.RECEBIDO)
        row=pd.read_csv(io.StringIO(csv_canonico(data.consenso))).iloc[0]
        context=autenticar_linha(row,root)
        pk=f.participante(row,root)
    assert context is not None and pk.v.get('g_receita_fy1') is None and pk.v.get('g_receita_fy2') is None
    assert archive.ler(record)==body and (archive.base/'indice.jsonl').read_bytes()==indice
    return row,pk,archive,record,body,indice


def conferir_inalterado(original,changed,archive,record,body,indice):
    for field in ('eps_contexto','sha256','data_coleta','eps_fy1','eps_fy2','alvo_medio'):
        a,b=original[field],changed[field]
        assert a==b or (pd.isna(a) and pd.isna(b))
    assert archive.ler(record)==body and (archive.base/'indice.jsonl').read_bytes()==indice


@pytest.mark.parametrize('values',[(1000,1100),(500,600),(0,0),(-500,-600)])
@pytest.mark.parametrize('currency',['ARS','USD'])
def test_csv_injetado_nao_autentica_nem_ativa_crescimento_v3(tmp_path,values,currency):
    row,_,archive,record,body,indice=preparar(tmp_path)
    changed=row.copy()
    changed['receita_fy1'],changed['receita_fy2'],changed['moeda_receita']=*values,currency
    changed=pd.read_csv(io.StringIO(csv_canonico(pd.DataFrame([changed])))).iloc[0]
    with guarda():
        with pytest.raises(ValueError,match='não admite campo de receita'):
            autenticar_linha(changed,tmp_path)
        with pytest.raises(ValueError,match='não admite campo de receita'):
            f.participante(changed,tmp_path)
    conferir_inalterado(row,changed,archive,record,body,indice)


@pytest.mark.parametrize('field',['receita_fy1','receita_fy2','moeda_receita'])
@pytest.mark.parametrize('value',[0,False,'', '0','inválido',[],{},1000])
def test_campo_auxiliar_isolado_nao_ausente_recusado_v3(tmp_path,field,value):
    row,_,archive,record,body,indice=preparar(tmp_path)
    changed=row.copy()
    changed[field]=value
    with guarda():
        with pytest.raises(ValueError,match='não admite campo de receita'):
            autenticar_linha(changed,tmp_path)
        with pytest.raises(ValueError,match='não admite campo de receita'):
            f.participante(changed,tmp_path)
    conferir_inalterado(row,changed,archive,record,body,indice)


@pytest.mark.parametrize('field,value',[('receita_period_end','2027-12-31'),
    ('receita_period_start','2026-01-01'),('poder_aquisitivo_data_receita','2026-12-31'),
    ('receita_poder_aquisitivo_data','2026-12-31'),('moeda_receita_fy2','ARS'),('receita_contexto','declarado')])
def test_metadata_receita_nao_ganha_autoridade_eps_v3(tmp_path,field,value):
    row,_,archive,record,body,indice=preparar(tmp_path)
    changed=row.copy()
    changed[field]=value
    with guarda():
        with pytest.raises(ValueError,match='não admite campo de receita'):
            f.participante(changed,tmp_path)
    conferir_inalterado(row,changed,archive,record,body,indice)


@pytest.mark.parametrize('missing',[None,pd.NA,pd.NaT,float('nan')])
def test_ausencia_auxiliar_preserva_eps_contexto_target_e_growth_none_v3(tmp_path,missing):
    row,expected,_,_,_,_=preparar(tmp_path)
    changed=row.copy()
    for field in ('receita_fy1','receita_fy2','moeda_receita','receita_period_end','poder_aquisitivo_data_receita'):
        changed[field]=missing
    with guarda():
        assert autenticar_linha(changed,tmp_path)==autenticar_linha(row,tmp_path)
        actual=f.participante(changed,tmp_path)
    assert actual.v==expected.v and actual.fontes==expected.fontes
    assert actual.tabela==expected.tabela and actual.lacunas==expected.lacunas and actual.avisos==expected.avisos


def test_sem_eps_tambem_recusa_receita_antes_consumo_v3(tmp_path):
    row,_,archive,record,body,indice=preparar(tmp_path,eps_ausente=True)
    changed=row.copy()
    changed['receita_fy1'],changed['receita_fy2'],changed['moeda_receita']=500,600,'ARS'
    with guarda():
        with pytest.raises(ValueError,match='não admite campo de receita'):
            f.participante(changed,tmp_path)
    conferir_inalterado(row,changed,archive,record,body,indice)


def test_legado_sem_marcador_preserva_formula_literal_v3(tmp_path):
    row,_,_,_,_,_=preparar(tmp_path)
    changed=row.copy()
    changed['eps_origem_moeda']=None
    changed['eps_contexto']=None
    changed['receita_fy1'],changed['receita_fy2'],changed['moeda_receita']=500,600,'ARS'
    with guarda():
        assert autenticar_linha(changed,tmp_path) is None
        actual=f.participante(changed,tmp_path)
    expected=Decimal('600')/Decimal('500')-Decimal('1')
    assert Decimal(str(actual.v['g_receita_fy2']))==expected


def test_marcador_parcial_nao_escape_para_legado_v3(tmp_path):
    row,_,_,_,_,_=preparar(tmp_path)
    changed=row.copy()
    changed['eps_origem_moeda']=None
    changed['receita_fy1'],changed['receita_fy2']=500,600
    with guarda():
        with pytest.raises(ValueError,match='Contexto EPS parcial'):
            f.participante(changed,tmp_path)
