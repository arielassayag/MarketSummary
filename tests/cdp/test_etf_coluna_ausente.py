"""DADOS SIMULADOS: ausência de preço não pode remover o modelo configurado."""
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.cobertura.etf import avaliar_etfs, calcular_etfs
from cdp.cobertura.parametros import carregar_parametros
from cdp.workflow.painel_cobertura import _modelo_etf

DAY = date(2026, 10, 8)
INDEXES = {
    'ETF_ILF': ('S&P Latin America 40', 'USD'),
    'ETF_EWZ': ('MSCI Brazil 25/50', 'USD'),
    'ETF_EWW': ('MSCI Mexico IMI 25/50', 'USD'),
    'ETF_ECH': ('MSCI Chile IMI 25/50', 'USD'),
    'ETF_EPU': ('MSCI All Peru Capped', 'USD'),
    'ETF_COLO': ('MSCI All Colombia Select 25/50', 'USD'),
    'ETF_ARGT': ('MSCI All Argentina 25/50', 'USD'),
    'ETF_BOVA11': ('Ibovespa', 'BRL'),
}


def market(columns, when=DAY):
    empty = pd.DataFrame(index=pd.DatetimeIndex([]))
    return SimpleNamespace(benchmarks=pd.DataFrame(columns, index=pd.DatetimeIndex([when])),
                           rates=empty, adj_close=empty, is_synthetic=True)


def evaluate(md, params=None):
    params = params or carregar_parametros()
    data = SimpleNamespace(etfs={}, origem='SIMULADO')
    models, inputs = avaliar_etfs(md, data, params, {}, {}, None, DAY)
    return models, inputs, params


@pytest.mark.parametrize('columns,when,present', [
    ({}, DAY, set()),
    ({'ILF':[17.0]}, DAY, {'ETF_ILF'}),
    ({'ILF':[None]}, DAY, set()),
    ({'ILF':[-17.0]}, DAY, set()),
    ({'ILF':[17.0]}, date(2026,10,9), set()),
    ({ticker:[17.0] for ticker in ['ILF','EWZ','EWW','ECH','EPU','COLO','ARGT','BOVA11.SA']}, DAY, set(INDEXES)),
])
def test_todos_os_modelos_permanecem_e_ausencia_nao_vira_preco(columns, when, present):
    models, inputs, params = evaluate(market(columns, when))
    assert set(models) == set(inputs) == set(INDEXES)
    assert models == calcular_etfs(inputs, params, {}, {}, None)
    for iid, model in models.items():
        assert (model['indice'],model['moeda']) == INDEXES[iid]
        assert model['tem_alvo'] is False
        assert model.get('preco_alvo') is None and model.get('retorno_esperado') is None
        if iid in present:
            assert model['preco'] == inputs[iid]['preco'] == 17.0
            assert model['data_preco'] == inputs[iid]['data_preco'] == DAY.isoformat()
        else:
            assert model['preco'] is inputs[iid]['preco'] is None
            assert model['data_preco'] is inputs[iid]['data_preco'] is None
            assert any(x['insumo'] == 'preco' for x in model['lacunas'])
            assert {g['status'] for g in model['portoes']} == {'nao_aplicavel'}


def test_fichas_dos_oito_indices_explicam_preco_ausente():
    models, _, params = evaluate(market({}))
    for cfg in params.etfs['etfs']:
        iid = 'ETF_' + cfg['ticker'].split('.')[0]
        row = dict(iid=iid,citavel=False,preco_texto='n/d',preco_data=None,
                   alvo_texto='Sem preço-alvo',upside_texto='n/d',etr_texto='n/d',
                   rating='Em revisão',nome=cfg['nome'],ticker=cfg['ticker'],
                   pais_nome=cfg['pais'],moeda=cfg['moeda'],rating_tom='sem',
                   rating_desde=None,data_modelo=DAY.isoformat())
        face = _modelo_etf(SimpleNamespace(etfs=models),row,{})
        assert face['indice'] == INDEXES[iid][0]
        assert face['cabecalho'][0] == {'t':'Índice de referência','v':INDEXES[iid][0]}
        assert face['passos'][0]['r'] == INDEXES[iid][0]
        assert face['lacunas'] and face['portoes']


def test_configuracao_vazia_preserva_saida_vazia():
    params = replace(carregar_parametros(),etfs={'etfs':[]})
    models, inputs, _ = evaluate(market({}),params)
    assert models == inputs == {}


def test_ausencia_de_coluna_nao_contorna_autoridade_observada():
    params = carregar_parametros()
    policy = {**params.valuation,'qualidade':{**params.sec('qualidade'),
                                            'ri_disponibilidade_metodo':'captura_observada_identidade'}}
    with pytest.raises(ValueError,match='fornecedor externo ausente'):
        evaluate(market({}),replace(params,valuation=policy))
