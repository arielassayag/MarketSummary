"""DADOS SIMULADOS: fluxo público em checkout normal; fontes geradas, sem rede."""
import json
from pathlib import Path

import pytest
import yaml
from ri_fixture_portatil import BOUND, fixture

from cdp.__main__ import build_parser
from cdp.cobertura.cli import config_paths, executar_snapshot
from cdp.cobertura.livro import recalcular_snapshot, snapshot, verificar
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.ri_fluxo import AutoridadeFluxoRI, carregar_mercado
from cdp.data.ri_captura.observado import sha
from cdp.data.snapshot import read_tables, write_snapshot, write_tables
from cdp.data.store import MarketStore

CHECKOUT = Path(__file__).resolve().parents[2]


def preparar(path, *, etfs=True):
    auth = path / 'autoridade'
    md, _, _ = fixture(auth)
    provisoria = path / 'base-construida'
    write_snapshot(md, provisoria)
    t = read_tables(provisoria)
    fields = t.manifest.model_dump(mode='json', exclude={'files', 'universe_sha256'})
    base = path / 'base-simulada'
    write_tables(base, manifest_fields=fields, universe_bytes=(auth/'master.csv').read_bytes(),
                 prices=t.prices, fx=t.fx, benchmarks=t.benchmarks, rates=t.rates,
                 fundamentals=t.fundamentals, short_interest=t.short_interest,
                 lending=t.lending, lending_history=t.lending_history, news_items=list(t.news), qa=t.qa)
    mercado = path/'mercado'
    MarketStore(mercado).init_base(base)
    md, _ = carregar_mercado(mercado, md.as_of)
    cfg = path/'configuracao'
    cfg.mkdir()
    val = yaml.safe_load((CHECKOUT/'configs/cdp/valuation.yaml').read_text())
    val['qualidade']['ri_disponibilidade_metodo']='captura_observada_identidade'
    (cfg/'valuation.yaml').write_text(yaml.safe_dump(val,allow_unicode=True,sort_keys=False))
    import shutil
    shutil.copytree(CHECKOUT/'configs/cdp/cobertura', cfg/'cobertura')
    shutil.copyfile(CHECKOUT/'configs/cdp/resultado_evidencias.json', cfg/'resultado_evidencias.json')
    if not etfs:
        ef=yaml.safe_load((cfg/'cobertura/etfs.yaml').read_text())
        ef['etfs']=[]
        (cfg/'cobertura/etfs.yaml').write_text(yaml.safe_dump(ef))
    params=carregar_parametros(cfg/'valuation.yaml',cfg/'cobertura')
    autoridade=AutoridadeFluxoRI(auth/'contexto.json',sha((auth/'contexto.json').read_bytes()))
    return md, params, autoridade, mercado, cfg


@pytest.mark.parametrize('ausente',['autoridade','corte','mercado'])
def test_recusa_sem_entrada_externa_antes_de_efeitos(tmp_path,ausente):
    md,p,a,m,cfg=preparar(tmp_path)
    kwargs=dict(params=p,agora=BOUND,ri_autoridade=a,ri_mercado=m,
                arquivos_config=config_paths(cfg/'valuation.yaml',cfg/'cobertura'))
    kwargs[{'autoridade':'ri_autoridade','corte':'agora','mercado':'ri_mercado'}[ausente]]=None
    book=tmp_path/'livro-nao-criado'
    with pytest.raises(ValueError if ausente !='corte' else (ValueError,RuntimeError),match='obrigat|exige'):
        executar_snapshot(book,md,md.as_of,offline=True,**kwargs)
    assert not book.exists()


@pytest.mark.parametrize('etfs',[True,False])
def test_snapshot_reabertura_e_recalculo_publicos(tmp_path,etfs):
    md,p,a,m,cfg=preparar(tmp_path,etfs=etfs)
    book=tmp_path/'livro-simulado'
    result=executar_snapshot(book,md,md.as_of,offline=True,params=p,agora=BOUND,
        ri_autoridade=a,ri_mercado=m,arquivos_config=config_paths(cfg/'valuation.yaml',cfg/'cobertura'),
        codigo={'git':None,'aviso':'DADOS SIMULADOS'})
    snap=snapshot(book,md.as_of)
    assert result['ri_conhecimento_ate']==BOUND.isoformat()
    assert snap.manifest['ri_fluxo']['pit_certificado'] is False
    assert snap.manifest['ri_fluxo']['configuracao_sha256']==a.sha256_esperado
    assert recalcular_snapshot(snap,ri_autoridade=a,conhecimento_ate=BOUND)==[]
    ok,msgs=verificar(book,ri_autoridade=a,ri_cortes={md.as_of.isoformat():BOUND})
    assert ok,msgs
    for cut,authority in [(None,a),(BOUND,None)]:
        ok,msgs=verificar(book,recalcular=False,ri_autoridade=authority,
                         ri_cortes={} if cut is None else {md.as_of.isoformat():cut})
        assert not ok and any('RI' in s for s in msgs)
    raw=(snap.pasta/'ri/insumos/insumos.json').read_text()
    typed=json.loads(raw)
    assert 'ri_contexto' not in typed and 'custodia' not in typed
    obs=typed['quadros']['ri_observados']
    assert obs is not None
    assert all(sha((snap.pasta/name).read_bytes())==digest
               for name,digest in snap.manifest['arquivos'].items() if name.startswith('ri/'))
    if not etfs:
        assert snap.manifest['contagens']['etfs']==0


def test_parser_publico_expoe_config_digest_e_corte():
    parser=build_parser()
    args=parser.parse_args(['cobertura','run','--date','2026-10-07','--offline',
        '--ri-config','externa.json','--ri-config-sha256','a'*64,
        '--ri-conhecimento-ate',BOUND.isoformat(),'--valuation','v.yaml','--parametros-cobertura','cfg'])
    assert args.ri_config=='externa.json' and args.ri_conhecimento_ate==BOUND.isoformat()
    for prefix in (['cobertura','verify'],['verify']):
        args=parser.parse_args(prefix+['--ri-config','externa.json','--ri-config-sha256','a'*64,
                                     '--ri-corte','2026-10-07='+BOUND.isoformat()])
        assert args.ri_corte==['2026-10-07='+BOUND.isoformat()]


def test_composicao_none_preservada_na_reabertura(tmp_path):
    from dataclasses import replace

    from cdp.cobertura.fontes import coletar
    from cdp.cobertura.livro import gravar_snapshot
    from cdp.cobertura.motor import executar
    from cdp.cobertura.ri_consumo import FornecedorConsumoRI
    from cdp.cobertura.ri_fluxo import reabrir
    md,p,a,m,cfg=preparar(tmp_path)
    context=a.reabrir(md)
    dados=coletar(md,md.as_of,list(md.universe.issuers.index),list(md.universe.lines.index),
                  ['ILF'],offline=True,params=p,conhecimento_ate=BOUND,ri_contexto=context)
    dados=replace(dados,etfs={'ILF':None})
    provider=FornecedorConsumoRI(md,dados)
    ex=executar(md,dados,p,md.as_of,ri_fornecedor=provider,conhecimento_ate=BOUND)
    book=tmp_path/'livro-none-simulado'
    gravar_snapshot(book,ex,dados,p,md_manifest=md.manifest,
        config_paths=config_paths(cfg/'valuation.yaml',cfg/'cobertura'),agora=BOUND,
        codigo={'git':None,'aviso':'DADOS SIMULADOS'},ri_fornecedor=provider,
        conhecimento_ate=BOUND,ri_autoridade=a,ri_mercado=m)
    snap=snapshot(book,md.as_of)
    reopened=reabrir(snap,p,autoridade=a,conhecimento_ate=BOUND)
    assert reopened.dados.etfs=={'ILF':None}
    assert recalcular_snapshot(snap,ri_autoridade=a,conhecimento_ate=BOUND)==[]


def test_cli_normal_privada_reabre_autoridade_externa(tmp_path):
    import os
    import subprocess
    import sys
    from datetime import UTC, datetime
    md,p,a,m,cfg=preparar(tmp_path,etfs=False)
    book=tmp_path/'livro-cli-simulado'
    common=[sys.executable,'-B','-m','cdp','--book',str(book),'--market',str(m),
            '--config',str(CHECKOUT/'configs/cdp/fund.yaml'),'--reports',str(tmp_path/'relatorios')]
    env=dict(os.environ,PYTHONPATH=str(CHECKOUT/'src'),PYTHONDONTWRITEBYTECODE='1')
    run=['cobertura','run','--date',str(md.as_of),'--offline',
         '--valuation',str(cfg/'valuation.yaml'),'--parametros-cobertura',str(cfg/'cobertura'),
         '--ri-conhecimento-ate',datetime.now(UTC).isoformat()]
    reject=subprocess.run(common+run,cwd=CHECKOUT,env=env,text=True,capture_output=True)
    assert reject.returncode==1 and 'configuração externa' in reject.stderr
    assert not book.exists()
    external=['--ri-config',str(a.configuracao),'--ri-config-sha256',a.sha256_esperado]
    accepted=subprocess.run(common+run+external,cwd=CHECKOUT,env=env,text=True,capture_output=True)
    assert accepted.returncode==0,accepted.stderr
    receipt=json.loads(accepted.stdout)
    cuts=['--ri-corte',Path(receipt['pasta']).name+'='+receipt['ri_conhecimento_ate']]
    for prefix in (['cobertura','verify'],['verify']):
        check=subprocess.run(common+prefix+external+cuts,cwd=CHECKOUT,env=env,text=True,capture_output=True)
        assert check.returncode==0,check.stdout+check.stderr
    refused=subprocess.run(common+['verify'],cwd=CHECKOUT,env=env,text=True,capture_output=True)
    assert refused.returncode==1 and 'RI' in refused.stdout


@pytest.mark.parametrize('composicao',['None','vazia'])
def test_ausencia_de_composicao_configurada_preservada(tmp_path,composicao):
    from dataclasses import replace

    import pandas as pd

    from cdp.cobertura.fontes import COLS_ETF, coletar
    from cdp.cobertura.livro import gravar_snapshot
    from cdp.cobertura.motor import executar
    from cdp.cobertura.ri_consumo import FornecedorConsumoRI
    from cdp.cobertura.ri_fluxo import reabrir
    md,p,a,m,cfg=preparar(tmp_path)
    comp=None if composicao=='None' else pd.DataFrame(columns=COLS_ETF)
    dados=coletar(md,md.as_of,list(md.universe.issuers.index),list(md.universe.lines.index),
        ['ILF'],offline=True,params=p,conhecimento_ate=BOUND,ri_contexto=a.reabrir(md))
    dados=replace(dados,etfs={'ILF':comp})
    provider=FornecedorConsumoRI(md,dados)
    ex=executar(md,dados,p,md.as_of,ri_fornecedor=provider,conhecimento_ate=BOUND)
    book=tmp_path/'livro-ausencia-simulado'
    gravar_snapshot(book,ex,dados,p,md_manifest=md.manifest,
        config_paths=config_paths(cfg/'valuation.yaml',cfg/'cobertura'),agora=BOUND,
        codigo={'git':None,'aviso':'DADOS SIMULADOS'},ri_fornecedor=provider,
        conhecimento_ate=BOUND,ri_autoridade=a,ri_mercado=m)
    snap=snapshot(book,md.as_of)
    reopened=reabrir(snap,p,autoridade=a,conhecimento_ate=BOUND)
    if comp is None:
        assert reopened.dados.etfs['ILF'] is None
    else:
        pd.testing.assert_frame_equal(reopened.dados.etfs['ILF'],comp)
    assert recalcular_snapshot(snap,ri_autoridade=a,conhecimento_ate=BOUND)==[]


def test_dois_retratos_endpoints_reabertos_e_retomada(tmp_path):
    import math
    from dataclasses import replace
    from datetime import timedelta

    from cdp.cobertura.motor import tp_deterministico
    from cdp.cobertura.ri_fluxo import preparar_anterior, reabrir
    md,p,a,m,cfg=preparar(tmp_path,etfs=False)
    book=tmp_path/'livro-dois-simulado'
    kwargs=dict(offline=True,params=p,ri_autoridade=a,ri_mercado=m,
        arquivos_config=config_paths(cfg/'valuation.yaml',cfg/'cobertura'),
        codigo={'git':None,'aviso':'DADOS SIMULADOS'})
    from cdp.cobertura.fontes import coletar
    from cdp.cobertura.livro import gravar_snapshot
    from cdp.cobertura.motor import executar
    from cdp.cobertura.ri_consumo import FornecedorConsumoRI

    def gravar_retrato(cut,cortes):
        from datetime import date

        from cdp.cobertura.temporal import construir
        dia=date.fromisoformat(construir(md.as_of,cut)['data_modelo'])
        dados=coletar(md,dia,list(md.universe.issuers.index),list(md.universe.lines.index),[],
                      offline=True,params=p,conhecimento_ate=cut,ri_contexto=a.reabrir(md))
        # DADOS SIMULADOS: fixture de ausência dos saldos, anterior à seleção documental.
        # Nenhum modelo/alvo é escrito; os valores são derivados pelo código normal.
        ausente=(dados.demonstrativos.issuer_id=='MX_AMX') & dados.demonstrativos.item.isin(
            ['patrimonio_controladores','participacao_minoritarios','patrimonio_liquido'])
        dados=replace(dados,demonstrativos=dados.demonstrativos.loc[~ausente].copy())
        anterior,historicos=preparar_anterior(book,dia,p,autoridade=a,cortes=cortes)
        provider=FornecedorConsumoRI(md,dados,anteriores=historicos)
        ex=executar(md,dados,p,dia,anterior=anterior,ri_fornecedor=provider,conhecimento_ate=cut)
        return gravar_snapshot(book,ex,dados,p,md_manifest=md.manifest,
            config_paths=kwargs['arquivos_config'],agora=cut,codigo=kwargs['codigo'],
            ri_fornecedor=provider,conhecimento_ate=cut,ri_autoridade=a,ri_mercado=m,ri_cortes=cortes)

    first=gravar_retrato(BOUND,{})
    cuts={md.as_of.isoformat():BOUND}
    repeated=executar_snapshot(book,md,md.as_of,agora=BOUND+timedelta(minutes=1),ri_cortes=cuts,**kwargs)
    assert repeated['ja_concluido'] and repeated['manifest_sha256']==first['manifest_sha256']
    assert repeated['ri_conhecimento_ate']==BOUND.isoformat()
    nextcut=BOUND+timedelta(days=1)
    second=gravar_retrato(nextcut,cuts)
    dia=Path(second['pasta']).name
    snap=snapshot(book,__import__('datetime').date.fromisoformat(dia))
    cuts[dia]=nextcut
    assert recalcular_snapshot(snap,ri_autoridade=a,conhecimento_ate=nextcut,ri_cortes=cuts)==[]
    anterior,history=preparar_anterior(book,snap.as_of,p,autoridade=a,cortes=cuts)
    provider=replace(reabrir(snap,p,autoridade=a,conhecimento_ate=nextcut),anteriores=history)
    oldpac,oldctx,oldrf=anterior.estado['MX_AMX']
    tp=tp_deterministico(oldpac,oldctx,p,oldrf,ri_fornecedor=provider,conhecimento_ate=nextcut)
    assert math.isclose(tp,anterior.alvos['MX_AMX'],rel_tol=1e-5)
    # Fórmula/guarda originais: híbridos não passam a ser fatos primários autorizados.
    ponte=snap.modelo('MX_AMX')['ponte']
    assert ponte['componentes'] is None and 'indisponível' in ponte['nota']
    assert not any(g['codigo']=='G7' for g in snap.modelo('MX_AMX')['portoes'])
    ok,msgs=verificar(book,ri_autoridade=a,ri_cortes=cuts)
    assert ok,msgs


def _fontes_cvm_simuladas(path):
    """DADOS SIMULADOS: bytes FCA/FRE/DFP gerados e lidos pelas APIs ordinárias."""
    import io
    import zipfile
    from datetime import UTC, datetime

    import pandas as pd

    from cdp.data import make_synthetic_market
    from cdp.data.publico_arquivo import Arquivo
    from cdp.universe import universe_from_frame

    md=make_synthetic_market(as_of=BOUND.date())
    frame=md.universe.lines.loc[(md.universe.lines.country=='BR') & md.universe.lines.primary_line].iloc[:1].copy()
    frame['issuer_id']='BR_SIMULADO_CWD'
    frame['issuer_name']='CIA SIMULADA ALFA S.A. (DADOS SIMULADOS)'
    frame['yahoo_ticker']='ALFA3.SA'
    frame['cnpj']='11.111.111/0001-11'
    uni=universe_from_frame(frame)
    arq=Arquivo(path/'arquivo-publico',offline=False)
    capture=datetime(2026,10,6,10,tzinfo=UTC)
    def salvar(doc,year,tabelas):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for nome,rows in tabelas.items():
                content=rows if isinstance(rows,bytes) else pd.DataFrame(rows).to_csv(index=False,sep=';').encode('latin1')
                z.writestr(nome,content)
        raw=out.getvalue()
        arq.gravar(f'CVM/{doc}/{doc.lower()}_cia_aberta_{year}.zip','CVM',
                   f'https://dados.cvm.gov.br/dados/CIA_ABERTA/{doc}/DADOS/{doc.lower()}_cia_aberta_{year}.zip',
                   raw,data_coleta=capture)
    fix=CHECKOUT/'tests/cdp/fixtures/cvm'
    salvar('FCA',2025,{n:(fix/n).read_bytes() for n in (
        'fca_cia_aberta_geral_2025.csv','fca_cia_aberta_valor_mobiliario_2025.csv')})
    cnpj='11.111.111/0001-11'
    salvar('FRE',2026,{
        'fre_cia_aberta_2026.csv':[dict(ID_DOC='9000',DT_RECEB='2026-03-01',LINK_DOC='https://example.test/FRE-DADOS-SIMULADOS')],
        'fre_cia_aberta_capital_social_2026.csv':[dict(ID_Documento='9000',Tipo_Capital='Capital Emitido',
            CNPJ_Companhia=cnpj,Data_Referencia='2025-12-31',Versao='1',Data_Autorizacao_Aprovacao='2025-12-31',
            Quantidade_Acoes_Ordinarias='100',Quantidade_Acoes_Preferenciais='0',Quantidade_Total_Acoes='100')]})
    salvar('DFP',2025,{
        'dfp_cia_aberta_2025.csv':[dict(CNPJ_CIA=cnpj,DT_REFER='2025-12-31',VERSAO='1',
            DT_RECEB='2026-03-01',LINK_DOC='https://example.test/DFP-DADOS-SIMULADOS')],
        'dfp_cia_aberta_DFC_MI_con_2025.csv':[dict(CNPJ_CIA=cnpj,DT_REFER='2025-12-31',VERSAO='1',
            ORDEM_EXERC='ULTIMO',DT_INI_EXERC='2025-01-01',DT_FIM_EXERC='2025-12-31',
            MOEDA='REAL',ESCALA_MOEDA='MIL',CD_CONTA='6.01.01',DS_CONTA='Depreciacao (DADOS SIMULADOS)',VL_CONTA='15')]})
    return uni,path/'arquivo-publico'


@pytest.mark.parametrize('nome',['capital_oficial','contas_suplementares_cvm'])
def test_helpers_cvm_universo_explicito_fora_do_cwd(tmp_path,nome):
    from contextlib import chdir

    from cdp.cobertura import fontes
    uni,archive=_fontes_cvm_simuladas(tmp_path)
    cwd=tmp_path/'cwd-sem-data-universe'
    cwd.mkdir()
    helper=getattr(fontes,nome)
    with chdir(cwd):
        assert not Path('data/universe/latam_universe.csv').exists()
        default=helper(['BR_SIMULADO_CWD'],BOUND.date(),archive)
        explicit=helper(['BR_SIMULADO_CWD'],BOUND.date(),archive,universe=uni)
        assert default.empty
        assert not explicit.empty
        if nome=='capital_oficial':
            assert explicit.iloc[0].qtd_total==100
        else:
            row=explicit.loc[(explicit.item=='d_a_dfc') & (explicit.freq=='A')].iloc[0]
            assert row.value==15*1000 and row.sha256
        # O default continua a usar o universo de cwd, com resultado literal equivalente.
        target=Path('data/universe/latam_universe.csv')
        target.parent.mkdir(parents=True)
        uni.lines.to_csv(target,index=False)
        legacy=helper(['BR_SIMULADO_CWD'],BOUND.date(),archive)
        import pandas as pd
        pd.testing.assert_frame_equal(legacy,explicit)
