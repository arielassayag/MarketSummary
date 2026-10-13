"""DADOS SIMULADOS: oráculos analíticos sem livro, coleta, solver ou modelo."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, tzinfo

import pytest

from cdp.risk.earnings_diagnostico import (
    CenarioEarnings,
    EntradaEarnings,
    JanelaEarnings,
    ReferenciaEarnings,
    dimensionar_earnings_sombra,
)


def entrada():
    corte = datetime(2026, 10, 10, tzinfo=UTC)
    ref = ReferenciaEarnings("DADOS SIMULADOS", "a" * 64, "SIMULATED_TEST_ONLY")
    return EntradaEarnings(
        issuer_id="SIMULADO",
        ticker="SIM",
        share_class="A",
        currency_basis="USD_TOTAL_RETURN_SAME_LINE",
        weight_current=0.1,
        weight_candidate=0.2,
        event_id="evento_simulado",
        event_version="v1",
        event_windows_utc=(
            JanelaEarnings(corte + timedelta(days=1), corte + timedelta(days=2), "ESTIMATED", ref),
            JanelaEarnings(corte + timedelta(days=2), corte + timedelta(days=3), "CONFIRMED", ref),
        ),
        event_session_timing="UNKNOWN",
        capture_declared_utc=corte,
        physical_received_utc=corte,
        cut_utc=corte,
        cenarios=(CenarioEarnings("cauda", -0.2, ref, "SIMULATED_TEST_ONLY"),),
        scenario_budget_nav=0.02,
        budget_kind="SCENARIO_LOSS_BUDGET",
        proportional_cost_period=0.0,
        borrow_period=0.0,
        financing_period=0.0,
        native_caps_abs_weight=(0.3,),
        config_body_ref=ref,
        novo_short_bloqueado=False,
    )


def test_oraculo_orcamento_cenarios_e_referencias_nao_autenticam():
    x = entrada()
    y = dimensionar_earnings_sombra(x)
    assert y.estado == "CONDICIONAL_CENARIOS"
    assert y.perda_adversa_por_unidade == 0.2
    assert y.limite_cenarios_abs == pytest.approx(0.1)
    assert y.peso_condicional == pytest.approx(0.1)
    assert y.janelas == x.event_windows_utc
    assert y.autenticidade_das_referencias == "NAO_VERIFICADA"
    assert y.autoridade_operacional is False
    with pytest.raises(FrozenInstanceError):
        y.peso_condicional = 0.5
    assert x == entrada()


def test_simetria_long_short_analitica():
    x = entrada()
    long = dimensionar_earnings_sombra(x)
    short = dimensionar_earnings_sombra(
        replace(
            x,
            weight_current=-x.weight_current,
            weight_candidate=-x.weight_candidate,
            cenarios=tuple(
                replace(c, movimento_preco_total_usd=-c.movimento_preco_total_usd)
                for c in x.cenarios
            ),
        )
    )
    assert short.limite_cenarios_abs == long.limite_cenarios_abs
    assert short.peso_condicional == -long.peso_condicional


def test_cauda_e_custo_mais_adversos_nao_aumentam_limite():
    x = entrada()
    original = dimensionar_earnings_sombra(x)
    cauda = dimensionar_earnings_sombra(
        replace(x, cenarios=(replace(x.cenarios[0], movimento_preco_total_usd=-0.4),))
    )
    custo = dimensionar_earnings_sombra(replace(x, proportional_cost_period=0.05))
    assert cauda.limite_cenarios_abs < original.limite_cenarios_abs
    assert custo.limite_cenarios_abs < original.limite_cenarios_abs
    assert custo.limite_cenarios_abs == pytest.approx(0.02 / 0.25)


def test_zero_cenario_nao_apaga_cauda_e_candidato_nao_aumenta():
    x = entrada()
    y = dimensionar_earnings_sombra(
        replace(
            x,
            weight_candidate=0.03,
            cenarios=x.cenarios
            + (replace(x.cenarios[0], id="zero", movimento_preco_total_usd=0.0),),
        )
    )
    assert y.ids_cenarios == ("cauda", "zero")
    assert y.perda_adversa_por_unidade == 0.2
    assert y.peso_condicional == 0.03


@pytest.mark.parametrize(
    "mudanca",
    [
        {"scenario_budget_nav": 0.0},
        {"native_caps_abs_weight": (0.0, 0.1)},
        {"weight_candidate": 0.0},
    ],
)
def test_zeros_legitimos_preservados(mudanca):
    y = dimensionar_earnings_sombra(replace(entrada(), **mudanca))
    assert y.estado == "CONDICIONAL_CENARIOS"
    assert y.peso_condicional == 0.0


@pytest.mark.parametrize(
    "mudanca",
    [
        {"event_windows_utc": ()},
        {"cenarios": ()},
        {"proportional_cost_period": None},
        {"borrow_period": None},
        {"financing_period": None},
        {"native_caps_abs_weight": ()},
        {"native_caps_abs_weight": (None,)},
        {"financing_period": -0.1},
    ],
)
def test_ausencias_e_credito_nao_viram_limite_livre(mudanca):
    y = dimensionar_earnings_sombra(replace(entrada(), **mudanca))
    assert y.estado == "INSUFICIENTE"
    assert y.limite_conjunto_abs is None and y.peso_condicional is None


def test_sem_cenario_adverso_e_posicao_sem_lado():
    x = entrada()
    y = dimensionar_earnings_sombra(
        replace(x, cenarios=(replace(x.cenarios[0], movimento_preco_total_usd=0.1),))
    )
    assert y.limite_cenarios_abs is None
    assert (
        dimensionar_earnings_sombra(replace(x, weight_current=0.0, weight_candidate=0.0)).estado
        == "INSUFICIENTE"
    )


def test_nao_relaxa_veto_ou_orcamento_absoluto_short():
    x = replace(entrada(), weight_current=-0.1, weight_candidate=-0.2)
    absoluto = dimensionar_earnings_sombra(replace(x, budget_kind="ABSOLUTE_LOSS_CAP"))
    bloqueado = dimensionar_earnings_sombra(replace(x, novo_short_bloqueado=True))
    assert absoluto.estado == bloqueado.estado == "FORA_DO_ESCOPO"
    assert absoluto.peso_condicional is bloqueado.peso_condicional is None
    assert bloqueado.veto_short_preservado is True
    reducao = replace(
        x,
        weight_candidate=-0.05,
        novo_short_bloqueado=True,
        cenarios=(replace(x.cenarios[0], movimento_preco_total_usd=0.2),),
    )
    assert dimensionar_earnings_sombra(reducao).peso_condicional == -0.05


@pytest.mark.parametrize("atual,candidato", [(0.1, -0.2), (-0.1, 0.2), (1e-300, -1e-300)])
def test_troca_de_lado_nao_e_escolhida(atual, candidato):
    assert (
        dimensionar_earnings_sombra(
            replace(entrada(), weight_current=atual, weight_candidate=candidato)
        ).estado
        == "FORA_DO_ESCOPO"
    )


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("weight_current", True),
        ("weight_candidate", 1),
        ("scenario_budget_nav", float("nan")),
        ("proportional_cost_period", -0.01),
        ("borrow_period", float("inf")),
        ("novo_short_bloqueado", 1),
        ("currency_basis", "LOCAL"),
        ("event_session_timing", "estimated"),
        ("budget_kind", "LIVRE"),
        ("cenarios", []),
        ("native_caps_abs_weight", (1,)),
        ("physical_received_utc", datetime(2026, 10, 11, tzinfo=UTC)),
        ("capture_declared_utc", datetime(2026, 10, 11, tzinfo=UTC)),
    ],
)
def test_ingressos_invalidos_recusados(campo, valor):
    with pytest.raises(ValueError):
        dimensionar_earnings_sombra(replace(entrada(), **{campo: valor}))


def test_janela_cenario_e_referencia_invalidos():
    x = entrada()
    for y in (
        replace(x, event_windows_utc=(replace(x.event_windows_utc[0], fim_utc=x.cut_utc),)),
        replace(x, cenarios=x.cenarios * 2),
        replace(x, cenarios=(replace(x.cenarios[0], movimento_preco_total_usd=-1.1),)),
        replace(x, config_body_ref=replace(x.config_body_ref, sha256="invalid")),
    ):
        with pytest.raises(ValueError):
            dimensionar_earnings_sombra(y)


def test_objetos_e_fuso_recusados_antes_de_callback():
    class Malicioso:
        def __getattribute__(self, name):
            raise AssertionError("callback de cliente executado")

    class FusoMalicioso(tzinfo):
        def utcoffset(self, dt):
            raise AssertionError("callback de fuso executado")

    with pytest.raises(ValueError):
        dimensionar_earnings_sombra(Malicioso())
    with pytest.raises(ValueError):
        dimensionar_earnings_sombra(
            replace(entrada(), cut_utc=datetime(2026, 10, 10, tzinfo=FusoMalicioso()))
        )
    with pytest.raises(ValueError):
        dimensionar_earnings_sombra(replace(entrada(), cenarios=(Malicioso(),)))


def test_overflow_finito_nao_vira_infinito_publicado():
    with pytest.raises(ValueError, match="Overflow"):
        dimensionar_earnings_sombra(
            replace(entrada(), proportional_cost_period=1e308, borrow_period=1e308)
        )
