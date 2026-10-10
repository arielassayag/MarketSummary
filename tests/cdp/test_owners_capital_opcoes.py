"""Recusas e precedência das duas flags; nenhum arquivo nativo externo exigido.

Nove controles projetados dos treze privados; não são cenários adicionais.
Universo, transporte e recibos DADOS SIMULADOS; PDFs públicos já existentes.
"""
from types import SimpleNamespace

import pytest
import test_bancos_patrimonio_owners as O
import test_capital_semantica_optin as C

from cdp.cobertura.fontes import coletar
from cdp.data import publico as P


def politica():
    return SimpleNamespace(sec=lambda key: {
        'projecao': {'resultado_corte_metodo': 'base_preco_conhecimento_explicitos'},
        'qualidade': {'demonstrativos_disponibilidade_metodo': 'recepcao_observada'},
    }.get(key, {}))



@pytest.mark.parametrize('owner', [False, True])
def test_flag_capital_invalida_nao_e_legitimada_por_owners(owner):
    with pytest.raises(ValueError, match='bool explícito'):
        P.demonstrativos([], O.DIA, patrimonio_owners_observado=owner,
                         preservar_semantica_capital=1)
    md = SimpleNamespace(is_synthetic=False, as_of=O.DIA)
    with pytest.raises(ValueError, match='bool explícito'):
        coletar(md, O.DIA, [], [], [], patrimonio_owners_observado=owner,
                preservar_semantica_capital=1)



@pytest.mark.parametrize('api', ['publico_ri', 'publico_corte', 'coletor_politica', 'coletor_temporal', 'coletor_corte'])
def test_semantica_nao_afrouxa_precondicoes_owners(api):
    if api.startswith('publico'):
        kw = dict(patrimonio_owners_observado=True, preservar_semantica_capital=True)
        if api == 'publico_corte':
            kw['selecionar_ri_observado'] = True
        mensagem = 'owners observado exige RI observado' if api == 'publico_ri' else 'RI observado exige corte'
        with pytest.raises(ValueError, match=mensagem):
            P.demonstrativos([], O.DIA, **kw)
        return
    md = SimpleNamespace(is_synthetic=False, as_of=O.DIA)
    params = None if api == 'coletor_politica' else politica()
    if api == 'coletor_temporal':
        params = SimpleNamespace(sec=lambda key: {'demonstrativos_disponibilidade_metodo': 'recepcao_observada'}
                                 if key == 'qualidade' else {})
    with pytest.raises(ValueError, match='exige'):
        coletar(md, O.DIA, [], [], [], params=params, patrimonio_owners_observado=True,
                preservar_semantica_capital=True)



@pytest.mark.parametrize('issuer', O.ISSUERS)
def test_semantica_conserva_precedencia_sec_e_lacuna_owners(monkeypatch, issuer):
    original = P.demonstrativos

    def ambos(*args, **kwargs):
        return original(*args, **kwargs, preservar_semantica_capital=True)

    monkeypatch.setattr(P, 'demonstrativos', ambos)
    with C.guarda('composicao-precedencia') as counts:
        O.test_precedencia_SEC_em_chave_presente_e_lacuna_especifica(monkeypatch, issuer)
    assert all(counts[k] == 0 for k in counts if k != 'reads')
