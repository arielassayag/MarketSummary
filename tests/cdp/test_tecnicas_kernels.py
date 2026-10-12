"""Fronteiras dos kernels portáteis — DADOS SIMULADOS."""
import numpy as np
import pytest

from cdp.tecnicas import avaliar_pb_justificado, calcular_ke, estimar_preenchimento


@pytest.mark.parametrize("valor", [None, float("nan"), float("inf"), True])
@pytest.mark.parametrize("ordem", [0, 7, -7])
def test_capacidade_ausente_recusada_inclusive_ordem_zero(valor, ordem):
    with pytest.raises(ValueError):
        estimar_preenchimento(ordem, valor, 3.0)
    with pytest.raises(ValueError):
        estimar_preenchimento(ordem, 15.0, valor)


def test_capacidade_finita_sinal_e_lote():
    from cdp.portfolio.execucao import preencher

    for ordem, capacidade, preco in [(7, 15.0, 3.0), (-7, 15.0, 3.0), (0, 15.0, 3.0),
                                     (7, 0.0, 3.0), (7, 1.0, 3.0), (7, 21.0, 3.0)]:
        assert estimar_preenchimento(ordem, capacidade, preco) == preencher(ordem, capacidade, preco)


def test_pb_forma_nan_erro_e_entrada_preservados():
    roe = np.array([[0.15], [0.20]])
    ke = np.array([0.1, 0.03])
    g = np.array([0.02, 0.03])
    saved = tuple(a.copy() for a in (roe, ke, g))
    out = avaliar_pb_justificado(roe, ke, g, estrito=False)
    assert out.shape == (2, 2) and np.isnan(out[:, 1]).all()
    with pytest.raises(ValueError):
        avaliar_pb_justificado(roe, ke, g)
    for a, before in zip((roe, ke, g), saved, strict=True):
        np.testing.assert_array_equal(a, before)


def test_kernels_nao_acessam_rede(monkeypatch):
    def negar(*args, **kwargs):
        pytest.fail("Kernel tentou acessar rede")

    monkeypatch.setattr("socket.create_connection", negar)
    assert isinstance(calcular_ke(0.01, 1.0, 0.05, 1.0, 0.02), float)
    assert avaliar_pb_justificado(0.15, 0.1, 0.02).shape == ()
    assert isinstance(estimar_preenchimento(7, 15.0, 3.0), int)
