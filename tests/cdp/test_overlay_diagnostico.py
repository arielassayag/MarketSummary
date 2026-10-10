"""DADOS SIMULADOS: oráculos analíticos de uma quadrática, sem mercado/solver."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, tzinfo

import pytest

from cdp.risk.overlay_diagnostico import (
    EntradaOverlay,
    ReferenciaOverlay,
    diagnosticar_overlay_sombra,
)


def entrada():
    ref = ReferenciaOverlay("DADOS SIMULADOS", "b" * 64, "SIMULATED_TEST_ONLY")
    corte = datetime(2026, 10, 10, tzinfo=UTC)
    return EntradaOverlay(
        legal_instrument_id="ETF_SIMULADO",
        ticker="SIM",
        currency="USD",
        mic="SIMULADO",
        price_usd=10.0,
        fx_basis_ref=ref,
        price_source_ref=ref,
        cut_utc=corte,
        inputs_available_utc=corte,
        portfolio_base_excludes_etf_hash="a" * 64,
        weight_current_etf=0.0,
        portfolio_var_annual=0.05,
        cross_cov_annual=0.04,
        etf_var_annual=0.04,
        covariance_basis="ANNUAL_USD_FRACTION_JOINT",
        covariance_source_ref=ref,
        tracking_basis_ref=ref,
        hmin=-2.0,
        hmax=2.0,
        oneway_cost_coef=0.01,
        borrow_annual_coef=0.03,
        financing_annual_coef=0.02,
        carry_days=30,
        carry_day_count="ACT360",
        native_constraint_refs=(ref,),
        retained_exposure="exposição declarada DADOS SIMULADOS",
        hedge_failure_scenario="falha declarada DADOS SIMULADOS",
        candidate_set_ref=ref,
        config_body_ref=ref,
    )


def test_clone_analitico_com_residual_nao_zero_e_custos_separados():
    x = entrada()
    y = diagnosticar_overlay_sombra(x)
    assert y.h_livre == y.h_condicional == -1.0
    assert y.delta_h == -1.0
    assert y.variancia_atual == 0.05
    assert y.variancia_condicional == pytest.approx(0.01)
    assert y.custo_alteracao_nav == 0.01
    assert y.borrow_periodo_nav == pytest.approx(0.03 * 30 / 360)
    assert y.financiamento_periodo_nav == pytest.approx(0.02 * 30 / 360)
    assert y.estado == "CONDICIONAL_SEM_ESCOLHA"
    assert y.autoridade_operacional is False
    assert y.autenticidade_das_referencias == "NAO_VERIFICADA"
    assert x == entrada()
    with pytest.raises(FrozenInstanceError):
        y.h_condicional = 0.0


def test_independencia_nao_exige_hedge():
    y = diagnosticar_overlay_sombra(replace(entrada(), cross_cov_annual=0.0))
    assert y.h_livre == y.h_condicional == y.delta_h == 0.0
    assert y.variancia_condicional == y.variancia_atual


def test_sinal_covariancia_troca_sinal_sem_apagar_residual():
    x = entrada()
    a = diagnosticar_overlay_sombra(x)
    b = diagnosticar_overlay_sombra(replace(x, cross_cov_annual=-x.cross_cov_annual))
    assert b.h_condicional == -a.h_condicional
    assert b.variancia_condicional == a.variancia_condicional


@pytest.mark.parametrize(
    "hmin,hmax,cov,esperado,limite",
    [
        (-0.5, 0.5, 0.04, -0.5, "inferior"),
        (-0.5, 0.5, -0.04, 0.5, "superior"),
        (-1.0, 1.0, 0.04, -1.0, "interior"),
    ],
)
def test_limites_explicitos(hmin, hmax, cov, esperado, limite):
    y = diagnosticar_overlay_sombra(replace(entrada(), hmin=hmin, hmax=hmax, cross_cov_annual=cov))
    assert y.h_condicional == esperado and y.limite_ativo == limite


def test_delta_zero_nao_apaga_carry_e_credito_financeiro():
    y = diagnosticar_overlay_sombra(
        replace(entrada(), weight_current_etf=-1.0, financing_annual_coef=-0.02)
    )
    assert y.delta_h == y.custo_alteracao_nav == 0.0
    assert y.borrow_periodo_nav > 0.0
    assert y.financiamento_periodo_nav < 0.0


@pytest.mark.parametrize("convencao,base", [("ACT360", 360), ("ACT365", 365), ("TRADING252", 252)])
def test_convenção_de_dias_recebida(convencao, base):
    y = diagnosticar_overlay_sombra(replace(entrada(), carry_day_count=convencao))
    assert y.borrow_periodo_nav == pytest.approx(0.03 * 30 / base)


@pytest.mark.parametrize(
    "campo",
    [
        "price_usd",
        "fx_basis_ref",
        "tracking_basis_ref",
        "oneway_cost_coef",
        "borrow_annual_coef",
        "financing_annual_coef",
    ],
)
def test_ausencias_preservam_quadratica_sem_prontidao(campo):
    y = diagnosticar_overlay_sombra(replace(entrada(), **{campo: None}))
    assert y.estado == "CONDICIONAL_INCOMPLETO"
    assert campo in y.ausencias
    assert y.h_condicional == -1.0
    assert y.autoridade_operacional is False


def test_restricoes_ausentes_nao_aprovam_candidato():
    y = diagnosticar_overlay_sombra(replace(entrada(), native_constraint_refs=()))
    assert y.estado == "CONDICIONAL_INCOMPLETO"
    assert y.ausencias == ("native_constraint_refs",)


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("portfolio_var_annual", -0.1),
        ("etf_var_annual", 0.0),
        ("cross_cov_annual", 0.1),
        ("etf_var_annual", float("nan")),
        ("cross_cov_annual", float("inf")),
        ("weight_current_etf", True),
        ("carry_days", True),
        ("carry_days", 365001),
        ("currency", "BRL"),
        ("covariance_basis", "DAILY"),
        ("carry_day_count", "DEFAULT"),
        ("hmin", 3.0),
        ("price_usd", 0.0),
        ("oneway_cost_coef", -0.01),
        ("borrow_annual_coef", -0.01),
        ("portfolio_base_excludes_etf_hash", "invalid"),
        ("native_constraint_refs", []),
    ],
)
def test_ingressos_invalidos(campo, valor):
    with pytest.raises(ValueError):
        diagnosticar_overlay_sombra(replace(entrada(), **{campo: valor}))


def test_zero_variancia_portfolio_com_covariancia_nao_zero_recusado():
    with pytest.raises(ValueError, match="PSD"):
        diagnosticar_overlay_sombra(
            replace(entrada(), portfolio_var_annual=0.0, cross_cov_annual=1e-100)
        )
    y = diagnosticar_overlay_sombra(
        replace(entrada(), portfolio_var_annual=0.0, cross_cov_annual=0.0)
    )
    assert y.variancia_condicional == 0.0


def test_corte_e_refs_invalidos():
    x = entrada()
    with pytest.raises(ValueError, match="corte"):
        diagnosticar_overlay_sombra(
            replace(x, inputs_available_utc=x.cut_utc + timedelta(seconds=1))
        )
    with pytest.raises(ValueError):
        diagnosticar_overlay_sombra(
            replace(x, candidate_set_ref=replace(x.candidate_set_ref, sha256="invalid"))
        )


def test_tipo_e_fuso_recusados_antes_callbacks():
    class Malicioso:
        def __getattribute__(self, name):
            raise AssertionError("callback executado")

    class Fuso(tzinfo):
        def utcoffset(self, dt):
            raise AssertionError("callback de fuso executado")

    for x in (
        Malicioso(),
        replace(entrada(), cross_cov_annual=Malicioso()),
        replace(entrada(), cut_utc=datetime(2026, 10, 10, tzinfo=Fuso())),
        replace(entrada(), native_constraint_refs=(Malicioso(),)),
    ):
        with pytest.raises(ValueError):
            diagnosticar_overlay_sombra(x)


def test_overflow_finito_recusado_sem_variancia_ou_custo_infinito():
    with pytest.raises(ValueError, match="Overflow"):
        diagnosticar_overlay_sombra(replace(entrada(), weight_current_etf=1e308))
