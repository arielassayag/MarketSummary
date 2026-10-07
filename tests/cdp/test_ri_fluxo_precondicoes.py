"""DADOS SIMULADOS: escritores ordinários, sem mocks ou estado operacional."""
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from ri_fixture_portatil import BOUND
from test_ri_fluxo_operacional import CHECKOUT, preparar

from cdp.cobertura.cli import config_paths, executar_snapshot
from cdp.cobertura.fontes import coletar
from cdp.cobertura.livro import gravar_snapshot, reparar_pendencias, verificar
from cdp.cobertura.motor import executar
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.ri_consumo import FornecedorConsumoRI
from cdp.cobertura.ri_fluxo import preparar_anterior
from cdp.hashing import sha256_file


def mapa(root):
    return {str(p.relative_to(root)): sha256_file(p) for p in sorted(root.rglob('*')) if p.is_file()}


@pytest.fixture(scope='module')
def entradas(tmp_path_factory):
    root = tmp_path_factory.mktemp('DADOS-SIMULADOS-precondicoes')
    md, params, autoridade, market, cfg = preparar(root, etfs=False)
    arquivos = config_paths(cfg / 'valuation.yaml', cfg / 'cobertura')
    book = root / 'aceito'
    kw = dict(offline=True, params=params, agora=BOUND, ri_autoridade=autoridade,
              ri_mercado=market, arquivos_config=arquivos, codigo={'git': None, 'aviso': 'DADOS SIMULADOS'})
    executar_snapshot(book, md, md.as_of, **kw)
    cuts = {md.as_of.isoformat(): BOUND}
    cut = BOUND + timedelta(days=1)
    dia = cut.date()
    dados = coletar(md, dia, list(md.universe.issuers.index), list(md.universe.lines.index), [],
                   offline=True, params=params, conhecimento_ate=cut, ri_contexto=autoridade.reabrir(md))
    anterior, historicos = preparar_anterior(book, dia, params, autoridade=autoridade, cortes=cuts)
    provider = FornecedorConsumoRI(md, dados, anteriores=historicos)
    ex = executar(md, dados, params, dia, anterior=anterior,
                  ri_fornecedor=provider, conhecimento_ate=cut)
    return dict(md=md, p=params, a=autoridade, market=market, arquivos=arquivos,
                book=book, cuts=cuts, cut=cut, dados=dados, provider=provider, ex=ex, kw=kw)


def interrompido(tmp_path, e, cauda='audit'):
    book = tmp_path / 'book'
    shutil.copytree(e['book'], book)
    arquivo = book / ('audit_log.jsonl' if cauda == 'audit' else 'cobertura/livro.jsonl')
    arquivo.write_bytes(b'')  # Queda ordinária na cauda da fixture, sem adulterar snapshots.
    return book


def writer(e, book, **kw):
    args = dict(md_manifest=e['md'].manifest, config_paths=e['arquivos'], agora=e['cut'],
                codigo={'git': None, 'aviso': 'DADOS SIMULADOS'}, ri_fornecedor=e['provider'],
                conhecimento_ate=e['cut'], ri_autoridade=e['a'], ri_mercado=e['market'])
    args.update(kw)
    return gravar_snapshot(book, e['ex'], e['dados'], e['p'], **args)


@pytest.mark.parametrize('ramo', ['api_default', 'cli_default', 'writer_sem_corte', 'reparo_direto'])
def test_p1_antes_de_qualquer_reparo(tmp_path, entradas, ramo):
    e = entradas
    book = interrompido(tmp_path, e)
    before = mapa(book)
    if ramo == 'cli_default':
        cmd = [sys.executable, '-B', '-m', 'cdp', '--config', str(CHECKOUT / 'configs/cdp/fund.yaml'),
               '--book', str(book), '--market', str(e['market']), 'cobertura', 'run',
               '--date', e['md'].as_of.isoformat(), '--offline']
        proc = subprocess.run(cmd, cwd=CHECKOUT, env=dict(os.environ, PYTHONPATH=str(CHECKOUT / 'src'),
                              PYTHONDONTWRITEBYTECODE='1'), text=True, capture_output=True, check=False)
        assert proc.returncode == 1 and 'opt-in' in proc.stderr, proc.stderr
    else:
        with pytest.raises(ValueError, match='opt-in|cortes externos'):
            if ramo == 'api_default':
                executar_snapshot(book, e['md'], e['md'].as_of, offline=True,
                                  params=carregar_parametros(), agora=e['cut'])
            elif ramo == 'writer_sem_corte':
                writer(e, book)
            else:
                reparar_pendencias(book, agora=e['cut'])
    assert mapa(book) == before


@pytest.mark.parametrize('mapa_invalido', ['omitido', 'vazio', 'incompleto', 'politica_padrao', 'arquivo_alterado'])
def test_p2_configuracao_explicita_antes_do_reparo(tmp_path, entradas, mapa_invalido):
    e = entradas
    book = interrompido(tmp_path, e)
    before = mapa(book)
    arquivos = dict(e['arquivos'])
    if mapa_invalido == 'omitido':
        arquivos = None
    elif mapa_invalido == 'vazio':
        arquivos = {}
    elif mapa_invalido == 'incompleto':
        arquivos.pop('cobertura/unidades.csv')
    elif mapa_invalido == 'politica_padrao':
        arquivos = config_paths()
    else:
        alterado = tmp_path / 'unidades.csv'
        alterado.write_bytes(Path(arquivos['cobertura/unidades.csv']).read_bytes() + b'\nDADOS SIMULADOS')
        arquivos['cobertura/unidades.csv'] = alterado
    with pytest.raises(ValueError, match='config|mapa'):
        executar_snapshot(book, e['md'], e['md'].as_of, **dict(e['kw'], agora=e['cut'],
                          ri_cortes=e['cuts'], arquivos_config=arquivos))
    assert mapa(book) == before


def test_p2_primeiro_snapshot_sem_map_nao_cria_book(tmp_path, entradas):
    e = entradas
    book = tmp_path / 'novo'
    kw = dict(e['kw'])
    kw.pop('arquivos_config')
    with pytest.raises(ValueError, match='arquivos_config explícitos'):
        executar_snapshot(book, e['md'], e['md'].as_of, **kw)
    assert not book.exists()


@pytest.mark.parametrize('falha', ['corte_ausente', 'corte_errado', 'corte_futuro', 'autoridade_ausente',
                                 'digest_errado', 'tabela_ausente', 'eventos_adulterados'])
def test_historico_requer_dependencias_externas_antes_do_writer(tmp_path, entradas, falha):
    from cdp.cobertura.ri_fluxo import AutoridadeFluxoRI
    e = entradas
    book = interrompido(tmp_path, e)
    args = {'ri_cortes': e['cuts']}
    if falha == 'corte_ausente':
        args['ri_cortes'] = {}
    elif falha == 'corte_errado':
        args['ri_cortes'] = {e['md'].as_of.isoformat(): BOUND + timedelta(microseconds=1)}
    elif falha == 'corte_futuro':
        args['ri_cortes'] = {e['md'].as_of.isoformat(): e['cut'] + timedelta(microseconds=1)}
    elif falha == 'autoridade_ausente':
        args['ri_autoridade'] = None
    elif falha == 'digest_errado':
        args['ri_autoridade'] = AutoridadeFluxoRI(e['a'].configuracao, '0' * 64)
    elif falha == 'tabela_ausente':
        (book / 'cobertura' / e['md'].as_of.isoformat() / 'ri/insumos/insumos.json').unlink()
    else:
        f = book / 'cobertura/livro.jsonl'
        event = json.loads(f.read_text().splitlines()[0])
        event['issuer_id'] = 'DADOS SIMULADOS: evento alterado'
        f.write_text(json.dumps(event) + '\n')
    before = mapa(book)
    with pytest.raises((ValueError, RuntimeError, OSError)):
        writer(e, book, **args)
    assert mapa(book) == before


@pytest.mark.parametrize('cauda', ['audit', 'livro'])
def test_retomada_autorizada_da_cauda_exata(tmp_path, entradas, cauda):
    e = entradas
    book = interrompido(tmp_path, e, cauda)
    snaproot = book / 'cobertura' / e['md'].as_of.isoformat()
    before_snap = mapa(snaproot)
    ret = executar_snapshot(book, e['md'], e['md'].as_of,
                           **dict(e['kw'], agora=BOUND + timedelta(minutes=1), ri_cortes=e['cuts']))
    assert ret['ja_concluido'] and ret['n_eventos'] == 0
    assert mapa(snaproot) == before_snap
    ok, msgs = verificar(book, ri_autoridade=e['a'], ri_cortes=e['cuts'])
    assert ok, msgs
    before = mapa(book)
    ret = executar_snapshot(book, e['md'], e['md'].as_of,
                           **dict(e['kw'], agora=BOUND + timedelta(minutes=1), ri_cortes=e['cuts']))
    assert ret['ja_concluido'] and mapa(book) == before


def test_writer_autorizado_repara_anterior_e_grava_nova_data(tmp_path, entradas):
    e = entradas
    book = interrompido(tmp_path, e)
    oldroot = book / 'cobertura' / e['md'].as_of.isoformat()
    before = mapa(oldroot)
    ret = writer(e, book, ri_cortes=e['cuts'])
    assert ret['reparos'] and ret['n_eventos'] == len(e['ex'].emissores)
    assert mapa(oldroot) == before
    cuts = dict(e['cuts'], **{e['ex'].as_of.isoformat(): e['cut']})
    ok, msgs = verificar(book, ri_autoridade=e['a'], ri_cortes=cuts)
    assert ok, msgs


def test_writer_corte_corrente_invalido_nao_repara_anterior(tmp_path, entradas):
    e = entradas
    book = interrompido(tmp_path, e)
    before = mapa(book)
    dados = replace(e['dados'], corte_temporal=dict(e['dados'].corte_temporal, base_preco='2099-01-01'))
    provider = replace(e['provider'], dados=dados)
    with pytest.raises((ValueError, RuntimeError)):
        gravar_snapshot(book, e['ex'], dados, e['p'], md_manifest=e['md'].manifest,
                        config_paths=e['arquivos'], agora=e['cut'], ri_fornecedor=provider,
                        conhecimento_ate=e['cut'], ri_autoridade=e['a'], ri_mercado=e['market'],
                        ri_cortes=e['cuts'])
    assert mapa(book) == before


@pytest.mark.parametrize('caso', ['escopo', 'base', 'data_regressiva'])
def test_reserva_incompativel_com_autoridade_correta_nao_repara(tmp_path, entradas, caso):
    from cdp.data.snapshot import read_tables, write_snapshot, write_tables
    from cdp.data.store import MarketStore
    e = entradas
    book = interrompido(tmp_path, e)
    before = mapa(book)
    md, market = e['md'], e['market']
    extra = {}
    if caso == 'escopo':
        extra['emissores'] = [list(md.universe.issuers.index)[0]]
    elif caso == 'base':
        close = md.close.copy()
        close.iloc[-1, 0] *= 1.01  # DADOS SIMULADOS: outra cotação, sem inventar modelo ou alvo.
        bruto = tmp_path / 'base-bruta'
        write_snapshot(replace(md, close=close), bruto)
        t = read_tables(bruto)
        base = tmp_path / 'base-master-preservado'
        write_tables(base, manifest_fields=t.manifest.model_dump(mode='json', exclude={'files', 'universe_sha256'}),
                     universe_bytes=(e['a'].configuracao.parent / 'master.csv').read_bytes(),
                     prices=t.prices, fx=t.fx, benchmarks=t.benchmarks, rates=t.rates,
                     fundamentals=t.fundamentals, short_interest=t.short_interest, lending=t.lending,
                     lending_history=t.lending_history, news_items=list(t.news), qa=t.qa)
        market = tmp_path / 'mercado-diferente'
        MarketStore(market).init_base(base)
        md = MarketStore(market).load(BOUND.date())
        assert md.manifest.content_hash() != e['md'].manifest.content_hash()
    now = BOUND - timedelta(days=1) if caso == 'data_regressiva' else BOUND + timedelta(minutes=1)
    with pytest.raises((ValueError, RuntimeError)) as exc:
        executar_snapshot(book, md, md.as_of, **dict(e['kw'], agora=now, ri_mercado=market,
                          ri_cortes=e['cuts'], **extra))
    if caso in ('escopo', 'base'):
        assert 'outro escopo' in str(exc.value) or 'outra base/configuração' in str(exc.value)
    else:
        assert 'base de preços posterior ao conhecimento' in str(exc.value)
    assert mapa(book) == before
