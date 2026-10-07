"""DADOS SIMULADOS: fontes privadas seladas antes dos cenários, nunca produção."""
from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yaml
from pypdf import PdfReader
from ri_fixture_atribuicao import BOUND, fixture, pdf_bytes

from cdp.cobertura.atribuicao_endpoints import FonteEndpoint, reextrair_resultado
from cdp.cobertura.fontes import coletar
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.ri_consumo import FornecedorConsumoRI
from cdp.data import publico_resultados as R
from cdp.data.ri_captura.adapter import texto
from cdp.data.ri_captura.configuracao import carregar_contexto_ri
from cdp.data.ri_captura.observado import sha
from cdp.data.ri_captura.transporte import gravar_insumos_ri
from cdp.data.snapshot import load_snapshot, write_snapshot
from cdp.universe import universe_from_frame

FONTE = Path(__file__).resolve().parents[2]
FIXTURE = FONTE / 'tests/fixtures/cdp/atribuicao'


def _gravar(path, value):
    raw = value if isinstance(value, bytes) else texto(value).encode()
    path.write_bytes(raw)
    return sha(raw)


def endpoint(path, *, novo=False, receita_ausente=False, config_diversa=False, faltas=False,
             sem_preco=False, ebit_negativo=False, moeda_linha_usd=False, fx_distinto=False,
             alteracoes=None):
    """A diferença é gerada nos bytes da fixture ANTES de qualquer âncora externa."""
    path = Path(path).resolve()
    md, _, _ = fixture(path / 'origens')
    if moeda_linha_usd:
        frame = md.universe.lines.copy()
        frame.loc['AMX', 'currency'] = 'USD'
        md = replace(md, universe=universe_from_frame(frame, source_sha256=md.universe.source_sha256))
    if fx_distinto:
        fx = md.fx.copy()
        fx['MXN'] *= 1.1
        md = replace(md, fx=fx)
    if sem_preco:
        close, adj = md.close.copy(), md.adj_close.copy()
        close['AMX'] = float('nan')
        adj['AMX'] = float('nan')
        md = replace(md, close=close, adj_close=adj)
    cut = BOUND + timedelta(hours=1 if novo else 0)
    market = path / 'mercado'
    write_snapshot(md, market)
    md = load_snapshot(market, verify=True)
    # Registry/master nasce da linha normalizada realmente gravada. Não relabelamos
    # uma autoridade já confiada; todas as raízes novas antecedem a extração.
    origin = path / 'origens'
    master_path = market / 'universe.csv'
    observation = json.loads((origin / 'master-observacao.json').read_bytes())
    observation.update(master_path=str(master_path), master_sha256=sha(master_path.read_bytes()))
    obs_sha = _gravar(origin / 'master-observacao.json', observation)
    root = json.loads((origin / 'master-root.json').read_bytes())
    root.update(master_path=str(master_path), master_sha256=sha(master_path.read_bytes()),
                observacao_sha256=obs_sha)
    root_sha = _gravar(origin / 'master-root.json', root)
    identity = json.loads((origin / 'identity-root.json').read_bytes())
    identity['master_anchor_sha256'] = root_sha
    identity_sha = _gravar(origin / 'identity-root.json', identity)
    cfg = json.loads((origin / 'contexto.json').read_bytes())
    cfg['master']['sha256'] = root_sha
    cfg['identidade']['sha256'] = identity_sha
    cfgsha = _gravar(origin / 'contexto.json', cfg)
    context = carregar_contexto_ri(origin / 'contexto.json', sha256_esperado=cfgsha)

    conf = path / 'config'
    conf.mkdir()
    shutil.copytree(FONTE / 'configs/cdp/cobertura', conf / 'cobertura')
    v = yaml.safe_load((FONTE / 'configs/cdp/valuation.yaml').read_text())
    v['qualidade']['ri_disponibilidade_metodo'] = 'captura_observada_identidade'
    if config_diversa:
        v['projecao']['anos_explicitos'] += 1
    (conf / 'valuation.yaml').write_text(yaml.safe_dump(v, sort_keys=False, allow_unicode=True))
    structure = json.loads((FIXTURE / 'catalogo_sintetico.json').read_bytes())
    hashes = {}
    document_refs = {}
    for filename, doc in zip(('anual_simulado.pdf', 'semestre_simulado.pdf'), structure['documentos'], strict=True):
        pages = [p.extract_text().splitlines() for p in PdfReader(FIXTURE / filename).pages]
        if novo:
            replacements = {
                'Lucro bruto 240,000 190,000 150,000': 'Lucro bruto 300,000 190,000 150,000',
                'Outro resultado (40,000) 0 0': 'Outro resultado (70,000) 0 0',
                'EBIT 230,000 150,000 120,000': 'EBIT 320,000 150,000 120,000',
                'Reversao de alienacao (30,000) - -': 'Reversao de alienacao (60,000) - -',
                'EBIT 50,000,000 110,000,000 45,000,000 90,000,000':
                    'EBIT 50,000,000 120,000,000 45,000,000 90,000,000',
                'EBIT 250,000,000 165,000,000': 'EBIT 350,000,000 165,000,000',
            }
            pages = [[replacements.get(line, line) for line in page] for page in pages]
        if ebit_negativo:
            replacements = {
                'Lucro bruto 240,000 190,000 150,000': 'Lucro bruto 0 190,000 150,000',
                'EBIT 230,000 150,000 120,000': 'EBIT (10,000) 150,000 120,000',
                'EBIT 250,000,000 165,000,000': 'EBIT 10,000,000 165,000,000',
            }
            pages = [[replacements.get(line, line) for line in page] for page in pages]
        if receita_ausente:
            pages = [['Receita ' + ' '.join('-' for _ in line.split()[1:])
                      if line.startswith('Receita ') else line for line in page] for page in pages]
        raw = pdf_bytes(pages)
        docpath = path / filename
        digest = _gravar(docpath, raw)
        hashes[doc['sha256']] = digest
        doc['sha256'], doc['issuer_id'] = digest, 'MX_AMX'
        document_refs[digest] = {'path': str(docpath), 'captura': (cut - timedelta(microseconds=1)).isoformat()}
    for b in structure['pontes_subtotal']:
        b['documento_id'] = hashes[b['documento_id']]
    for event in structure['eventos']:
        event['issuer_id'] = 'MX_AMX'
        event['identidade']['entidade'] = 'MX_AMX'
        for key in ('documentos_prova', 'medida_documentos'):
            event[key] = [hashes[h] for h in event[key]]
    _gravar(conf / 'resultado_evidencias.json', structure)
    params = carregar_parametros(conf / 'valuation.yaml', conf / 'cobertura')
    dados = coletar(md, md.as_of, list(md.universe.issuers.index), list(md.universe.lines.index),
                    [], params=params, conhecimento_ate=cut, ri_contexto=context)
    spec = {'resultado_catalogo': str(conf / 'resultado_evidencias.json'),
            'resultado_documentos': document_refs}
    cat = reextrair_resultado(spec, cut)
    primary = R.tabela_fatos(cat)
    old = dados.demonstrativos
    keys = {(r.item, r.freq, str(r.period_end)) for r in primary.itertuples()}
    keep = [not (r.issuer_id == 'MX_AMX' and
                 ((r.item, r.freq, pd.Timestamp(r.period_end).date().isoformat()) in keys or
                  receita_ausente and r.item == 'receita' or
                  r.item in ('patrimonio_controladores', 'participacao_minoritarios', 'patrimonio_liquido')))
            for r in old.itertuples()]
    dem = pd.concat([old.loc[keep], primary], ignore_index=True)
    for change in alteracoes or []:
        # Apenas fontes originais sintéticas, antes de transporte/descriptor/digest.
        # Fato extraído dos PDFs exige seus bytes/catálogo próprios, não esta via.
        select = (dem.issuer_id == 'MX_AMX') & (dem.item == change['item'])
        select &= dem.fato_resultado_id.isna()
        if 'freq' in change:
            select &= dem.freq == change['freq']
        if 'ano' in change:
            select &= pd.to_datetime(dem.period_end).dt.year == change['ano']
        if not select.any():
            raise ValueError('fixture: alteração sem fonte sintética original selecionada')
        for field in ('consolidado', 'currency', 'period_end'):
            if field in change:
                if field == 'consolidado' and change[field] is None:
                    dem[field] = dem[field].astype(object)
                dem.loc[select, field] = change[field]
    if novo:
        con = dados.consenso.copy()
        select = con.ticker == context.ticker
        for key in ('eps_fy1', 'eps_fy2'):
            con.loc[select, key] *= 1.1
        dados = replace(dados, consenso=con)
    if faltas:
        # EPS público faltante é dado ausente verdadeiro de fixture, não zero.
        con = dados.consenso.copy()
        con.loc[con.ticker == context.ticker, ['eps_fy1', 'eps_fy2']] = None
        dados = replace(dados, consenso=con)
    dados = replace(dados, demonstrativos=dem,
                    resultado_evidencias=pd.DataFrame([{'catalogo_json': R.texto_json(cat)}]))
    provider = FornecedorConsumoRI(md, dados)
    transport = path / 'transporte'
    mh = gravar_insumos_ri(transport, raiz_saida=path, fornecedor=provider, params=params, conhecimento_ate=cut)
    dependencies = {str(p): sha(p.read_bytes()) for p in path.rglob('*') if p.is_file()}
    dependencies.update({str(p): sha(p.read_bytes()) for p in (FONTE / 'src').rglob('*.py')})
    spec.update(schema='cdp.fonte_endpoint_confiada_privada/v1', aviso='DADOS SIMULADOS',
                dependencias=dependencies, conhecimento_ate=cut.isoformat(), mercado=str(market),
                valuation=str(conf / 'valuation.yaml'), cobertura=str(conf / 'cobertura'),
                parametros_sha256=params.hash(), ri_config=str(origin / 'contexto.json'),
                ri_config_sha256=cfgsha, transporte=str(transport), transporte_sha256=mh, issuer_id='MX_AMX')
    digest = _gravar(path / 'endpoint.json', spec)
    source = FonteEndpoint(path / 'endpoint.json', digest)
    return source
