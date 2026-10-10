"""DADOS SIMULADOS: sistemas identificáveis; nenhum preço ou calibração pública."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, tzinfo

import pytest

from cdp.risk.beta_distribuido_sombra import (
    EntradaBetaDistribuido,
    ObservacaoBeta,
    ReferenciaBeta,
    estimar_beta_distribuido_sombra,
)


def entrada(coef=(2.0, -1.0, 0.5), escala=1.0):
    # Impulsos separados tornam as três colunas independentes.
    mercado = tuple(v * escala for v in (0.0, 1.0, 0.0, 0.0, 0.0, -2.0, 0.0, 0.0, 0.0))
    inicio = datetime(2026, 1, 1, tzinfo=UTC)
    corte = inicio + timedelta(days=30)
    ref = ReferenciaBeta("DADOS SIMULADOS", "b" * 64, "SIMULATED_TEST_ONLY")
    obs = []
    for i, valor in enumerate(mercado):
        carteira = 0.0 if i in (0, len(mercado) - 1) else (
            coef[0] * mercado[i - 1] + coef[1] * mercado[i] + coef[2] * mercado[i + 1]
        )
        dia = inicio + timedelta(days=i)
        obs.append(ObservacaoBeta(i, dia, carteira, valor, dia, dia, "", ""))
    return EntradaBetaDistribuido(
        "CARTEIRA SIMULADA", "MERCADO SIMULADO", "USD_EXCESS_RETURN_SAME_SESSIONS",
        "SESSAO", corte, ref, ref, ref, ref, tuple(obs)
    )


def alterar_obs(x, i, **campos):
    return replace(x, observacoes=tuple(replace(o, **campos) if k == i else o
                                       for k, o in enumerate(x.observacoes)))


def test_oraculo_colunas_ortogonais_e_soma():
    x = entrada()
    y = estimar_beta_distribuido_sombra(x)
    assert y.coeficientes_lag_atual_lead == pytest.approx((2.0, -1.0, 0.5))
    assert y.beta_agregado == pytest.approx(1.5)
    assert y.beta_contemporaneo_mesma_mascara == pytest.approx(-1.0)
    assert y.centros_utilizados == tuple(range(1, 8))
    assert tuple(e.ordinal_sessao for e in y.exclusoes) == (0, 8)
    assert y.entrada is x
    assert y.posto == 3 and y.intercepto is False
    assert y.estado == "CONDICIONAL_SEM_CALIBRACAO"
    assert y.autoridade_operacional is False
    assert y.autenticidade_referencias == "NAO_VERIFICADA"
    assert y.qualificacao_pit == "NAO_DEMONSTRADA"
    with pytest.raises(FrozenInstanceError):
        y.beta_agregado = 0.0
    assert x == entrada()


@pytest.mark.parametrize("coef", [(1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)])
def test_lag_lead_e_zero_observado(coef):
    y = estimar_beta_distribuido_sombra(entrada(coef))
    assert y.coeficientes_lag_atual_lead == pytest.approx(coef)
    assert y.beta_agregado == pytest.approx(sum(coef))
    assert y.beta_contemporaneo_mesma_mascara == pytest.approx(0.0)


@pytest.mark.parametrize("escala", [1e-200, 1e200, -1.0])
def test_escala_comum_preserva_beta(escala):
    y = estimar_beta_distribuido_sombra(entrada(escala=escala))
    assert y.coeficientes_lag_atual_lead == pytest.approx((2.0, -1.0, 0.5))
    assert y.beta_agregado == pytest.approx(1.5)


def test_mesma_mascara_para_comparacao_contemporanea():
    x = alterar_obs(entrada(), 1, retorno_excedente_carteira=None,
                    carteira_disponivel_declarada_utc=None, ausencia_carteira="não recebido")
    y = estimar_beta_distribuido_sombra(x)
    assert 1 not in y.centros_utilizados and len(y.centros_utilizados) == 6
    assert y.beta_contemporaneo_mesma_mascara == pytest.approx(-1.0)
    assert next(e for e in y.exclusoes if e.ordinal_sessao == 1).motivos == ("CARTEIRA_AUSENTE",)


def test_ausencia_mercado_exclui_tres_centros_sem_preencher():
    x = alterar_obs(entrada(), 3, retorno_excedente_mercado=None,
                    mercado_disponivel_declarada_utc=None, ausencia_mercado="lacuna explícita")
    y = estimar_beta_distribuido_sombra(x)
    assert y.centros_utilizados == (1, 5, 6, 7)
    assert {e.ordinal_sessao for e in y.exclusoes} == {0, 2, 3, 4, 8}
    assert x.observacoes[3].retorno_excedente_mercado is None


def test_lead_posterior_ao_corte_nao_entra():
    x = alterar_obs(entrada(), 8, mercado_disponivel_declarada_utc=entrada().corte_utc + timedelta(1))
    y = estimar_beta_distribuido_sombra(x)
    assert 7 not in y.centros_utilizados
    assert next(e for e in y.exclusoes if e.ordinal_sessao == 7).motivos == (
        "MERCADO_LEAD_POSTERIOR_AO_CORTE",
    )


def test_carteira_posterior_ao_corte_nao_entra():
    x = alterar_obs(entrada(), 2, carteira_disponivel_declarada_utc=entrada().corte_utc + timedelta(1))
    assert 2 not in estimar_beta_distribuido_sombra(x).centros_utilizados


@pytest.mark.parametrize("n", [0, 1, 2, 3, 4, 5])
def test_amostra_curta_nao_gera_coeficientes(n):
    x = replace(entrada(), observacoes=entrada().observacoes[:n])
    y = estimar_beta_distribuido_sombra(x)
    assert y.estado == "INSUFICIENTE_AMOSTRA" and y.beta_agregado is None


@pytest.mark.parametrize("valor", [0.0, 1.0])
def test_posto_insuficiente_nao_recebe_ridge(valor):
    x = replace(entrada(), observacoes=tuple(replace(o, retorno_excedente_mercado=valor)
                                            for o in entrada().observacoes))
    y = estimar_beta_distribuido_sombra(x)
    assert y.estado == "INSUFICIENTE_POSTO"
    assert y.coeficientes_lag_atual_lead is None


@pytest.mark.parametrize("valor", [True, 0, float("nan"), float("inf"), -float("inf")])
def test_valor_ausente_nao_vira_zero(valor):
    with pytest.raises(ValueError):
        estimar_beta_distribuido_sombra(alterar_obs(entrada(), 2, retorno_excedente_mercado=valor))


@pytest.mark.parametrize("campos", [
    {"retorno_excedente_mercado": None},
    {"retorno_excedente_mercado": None, "mercado_disponivel_declarada_utc": None},
    {"ausencia_mercado": "contradição"},
    {"ordinal_sessao": True},
    {"ordinal_sessao": 4},
    {"fim_sessao_utc": datetime(2026, 1, 1)},
    {"fim_sessao_utc": datetime(2026, 1, 1, tzinfo=UTC, fold=1)},
    {"mercado_disponivel_declarada_utc": datetime(2025, 1, 1, tzinfo=UTC)},
])
def test_entrada_contraditoria_recusada(campos):
    with pytest.raises(ValueError):
        estimar_beta_distribuido_sombra(alterar_obs(entrada(), 2, **campos))


def test_buraco_ordinal_nao_comprime_calendario():
    x = entrada()
    with pytest.raises(ValueError, match="consecutivas"):
        estimar_beta_distribuido_sombra(replace(x, observacoes=x.observacoes[:3] + x.observacoes[4:]))


def test_fuso_callback_nao_executado():
    class Fuso(tzinfo):
        def utcoffset(self, dt):
            raise AssertionError("callback não autorizado")

    x = alterar_obs(entrada(), 2, mercado_disponivel_declarada_utc=datetime(2026, 1, 3, tzinfo=Fuso()))
    with pytest.raises(ValueError, match="UTC"):
        estimar_beta_distribuido_sombra(x)


def test_objeto_callback_nao_executado():
    class Numero:
        def __float__(self):
            raise AssertionError("callback não autorizado")

    with pytest.raises(ValueError, match="float"):
        estimar_beta_distribuido_sombra(alterar_obs(entrada(), 2, retorno_excedente_carteira=Numero()))


def test_subclasse_nominal_recusada():
    class OutraEntrada(EntradaBetaDistribuido):
        pass

    x = entrada()
    with pytest.raises(ValueError, match="nominal"):
        estimar_beta_distribuido_sombra(OutraEntrada(**x.__dict__))


@pytest.mark.parametrize("campos", [
    {"base": "USD_TOTAL_RETURN"}, {"horizonte": "MES"}, {"linha_carteira": ""},
    {"observacoes": []}, {"historia_ref": ReferenciaBeta("x", "x" * 64, "SIMULATED_TEST_ONLY")},
])
def test_bases_e_referencias_invalidas(campos):
    with pytest.raises(ValueError):
        estimar_beta_distribuido_sombra(replace(entrada(), **campos))


def test_overflow_nao_produz_beta_infinito():
    x = entrada(escala=1e-200)
    x = replace(x, observacoes=tuple(replace(o, retorno_excedente_carteira=1e200)
                                    for o in x.observacoes))
    y = estimar_beta_distribuido_sombra(x)
    assert y.estado == "INSUFICIENTE_NUMERICO" and y.beta_agregado is None


def test_funcao_sem_io_python(monkeypatch):
    def proibido(*args, **kwargs):
        raise AssertionError("I/O não autorizado")

    monkeypatch.setattr("builtins.open", proibido)
    assert estimar_beta_distribuido_sombra(entrada()).estado == "CONDICIONAL_SEM_CALIBRACAO"
