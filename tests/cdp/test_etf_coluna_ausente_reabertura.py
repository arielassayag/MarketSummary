"""DADOS SIMULADOS: o snapshot deve conservar os cinco ETFs sem preço da fixture herdada."""
from test_cobertura_livro import D1
from test_cobertura_livro import livro as livro  # reexportação da fixture herdada
from test_cobertura_livro import mercado as mercado  # dependência da fixture livro

from cdp.cobertura.livro import ler_pacotes, snapshot


def test_reabrir_oito_etfs_com_precos_ausentes(livro):
    book, _, _ = livro
    snap = snapshot(book, D1)
    ids = {'ETF_ILF','ETF_EWZ','ETF_EWW','ETF_ECH','ETF_EPU','ETF_COLO','ETF_ARGT','ETF_BOVA11'}
    assert set(snap.etfs().index) == ids
    inputs = ler_pacotes(snap.pasta,snap.manifest,'etfs')
    assert set(inputs) == ids
    for iid in ids - {'ETF_ILF','ETF_EWZ','ETF_EWW'}:
        model = snap.etf(iid)
        assert model['tem_alvo'] is False
        assert model['preco'] is model['data_preco'] is None
        assert inputs[iid]['preco'] is inputs[iid]['data_preco'] is None
        assert model.get('preco_alvo') is None and model.get('retorno_esperado') is None
        assert any(row['insumo'] == 'preco' for row in model['lacunas'])
