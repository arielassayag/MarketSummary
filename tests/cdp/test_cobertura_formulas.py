"""Testes de ouro das fórmulas da cobertura (DESIGN §A.9) — tudo em código, sem rede."""

from __future__ import annotations

import math

import numpy as np
import pytest

from cdp.cobertura import formato
from cdp.cobertura import metodos as M
from cdp.cobertura.custo_capital import beta_realavancado, blume, fisher, ke_usd, real, wacc
from cdp.cobertura.etf import grinold_kroner, pl_gordon


def test_gordon_pb_golden():
    # (15,5% − 6%) / (12,5% − 6%) = 1,4615x
    assert float(M.pb_gordon(0.155, 0.125, 0.06)) == pytest.approx(1.461538, rel=1e-6)


def test_damodaran_roll_forward_and_etr():
    # V0 = 42,30; ke = 7,7%; DPS = 2,32 × 1,021 ≈ 2,37 ⇒ TP12 ≈ 43,19; ETR a partir de 40,76 ≈ 11,77%
    tp = float(M.rolagem(42.30, 0.077, 2.37))
    assert tp == pytest.approx(43.19, abs=0.005)
    etr = float(M.retorno_esperado(tp, 2.37, 40.76))
    assert etr == pytest.approx(0.1177, abs=0.0005)


def test_easton_peg_and_mpeg():
    # Caso PEG: r = √((EPS2 − EPS1)/P0) ≈ 10,1%
    assert M.icc_peg(98.0, 5.0, 6.0) == pytest.approx(0.1010, abs=0.0002)
    r = M.icc_mpeg(100.0, 5.0, 6.0, 2.0)
    # raiz da quadrática r² − r·DPS1/P0 − (EPS2 − EPS1)/P0 = 0
    assert r * r - r * 0.02 - 0.01 == pytest.approx(0.0, abs=1e-12)
    assert M.icc_mpeg(100.0, 6.0, 5.0, 2.0) is None  # crescimento negativo ⇒ indefinido


def test_rim_with_roe_equal_ke_is_book_value():
    res = M.rim_gls(20.0, 0.12, 0.12, 0.12, 0.12, 0.4)
    assert float(res.valor) == pytest.approx(20.0, rel=1e-12)
    assert float(res.pv_terminal) == pytest.approx(0.0, abs=1e-12)


def test_rim_excess_return_adds_value_and_terminal_share():
    res = M.rim_gls(20.0, 0.18, 0.17, 0.15, 0.12, 0.4)
    assert float(res.valor) > 20.0
    ft = float(res.fracao_terminal)
    assert 0.0 < ft < 1.0
    # vetorizado: cada sorteio igual ao cálculo escalar
    vec = M.rim_gls(20.0, np.array([0.18, 0.12]), np.array([0.17, 0.12]), np.array([0.15, 0.12]),
                    np.array([0.12, 0.12]), 0.4).valor
    assert vec[0] == pytest.approx(float(res.valor))
    assert vec[1] == pytest.approx(20.0)


def test_rim_refuses_negative_book():
    with pytest.raises(ValueError):
        M.rim_gls(-1.0, 0.1, 0.1, 0.1, 0.12, 0.3)


@pytest.mark.parametrize("fn", [
    lambda: M.pb_gordon(0.15, 0.10, 0.10),
    lambda: M.pl_justificado(0.15, 0.10, 0.11),
    lambda: M.ddm_dois_estagios(1.0, 0.05, 0.12, 0.10),
    lambda: M.fcff_tres_estagios(100.0, 0.05, 0.05, 0.10, 0.9, 0.2, 0.3, 0.12, 0.10),
    lambda: pl_gordon(0.5, 0.08, 0.09),
])
def test_g_at_or_above_ke_raises(fn):
    with pytest.raises(ValueError):
        fn()


def test_ddm_two_stage_collapses_to_gordon():
    # g1 = g2 ⇒ DPS1/(ke − g)
    v = float(M.ddm_dois_estagios(2.0, 0.04, 0.04, 0.11, 5))
    assert v == pytest.approx(2.0 / (0.11 - 0.04), rel=1e-12)


def test_fcff_constant_growth_value_neutral_equals_gordon_on_fcff():
    # crescimento constante e RONIC = WACC em todo o horizonte ⇒ EV = FCFF_1/(WACC − g)
    w, g = 0.10, 0.04
    res = M.fcff_tres_estagios(1000.0, g, g, g, 0.9, 0.20, 0.25, w, w)
    fcff1 = 1000.0 * (1 + g) * 0.20 * 0.75 * (1 - g / w)
    assert float(res.ev) == pytest.approx(fcff1 / (w - g), rel=1e-9)
    assert 0 < float(res.fracao_terminal) < 1


def test_fcff_finite_life_has_no_terminal_value():
    res = M.fcff_tres_estagios(1000.0, 0.05, 0.05, 0.03, 0.9, 0.3, 0.3, 0.15, 0.10, vida=8)
    assert float(res.pv_terminal) == 0.0
    assert res.fcff.shape[0] == 8
    with pytest.raises(ValueError):
        M.fcff_tres_estagios(1000.0, 0.05, 0.05, 0.03, 0.9, 0.3, 0.3, 0.15, 0.10, vida=0)


def test_pl_justificado():
    # (1 − 5%/15%)/(12% − 5%) = 9,5238x
    assert float(M.pl_justificado(0.15, 0.12, 0.05)) == pytest.approx((1 - 0.05 / 0.15) / 0.07)


def test_safra_ibovespa_golden():
    # Safra (dez/2025): 0,55/(14,3% − 8,4%) = 9,32x × LPA 2027 de 21.283 ≈ 198,4 mil pontos
    pe = pl_gordon(0.55, 0.143, 0.084)
    assert pe == pytest.approx(9.322, abs=0.001)
    assert pe * 21283 == pytest.approx(198_400, abs=150)


def test_grinold_kroner_golden():
    # 1,78% + 0,2% + 2,4% + 1,8% + 0,85% = 7,03% (ΔS = −0,2%: recompras líquidas)
    assert grinold_kroner(0.0178, -0.002, 0.024, 0.018, 0.0085) == pytest.approx(0.0703, abs=1e-12)


def test_cost_of_equity_build_up():
    # β = 1, λ = 1, Brasil: 5,07% + 1 × 4,20% + 1 × 3,10% = 12,37% em dólar
    k = ke_usd(0.0529 - 0.0022, 1.0, 0.042, 1.0, 0.031)
    assert k == pytest.approx(0.1237, abs=1e-12)
    kl = fisher(k, 0.0323, 0.0235)
    assert kl == pytest.approx((1.1237 * 1.0323) / 1.0235 - 1, rel=1e-12)
    assert real(kl, 0.0323) == pytest.approx(1.1237 / 1.0235 - 1, rel=1e-12)
    assert beta_realavancado(0.8, 0.5, 0.34) == pytest.approx(0.8 * (1 + 0.66 * 0.5))
    assert blume(1.5) == pytest.approx(0.67 * 1.5 + 0.33)
    assert wacc(0.12, 0.08, 0.3, 60.0, 40.0) == pytest.approx(0.6 * 0.12 + 0.4 * 0.08 * 0.7)


def test_swanson_fallback_symmetric_equals_mean():
    rng = np.random.default_rng([7, 1])
    x = rng.normal(0.05, 0.10, 200_000)
    p10, p50, p90 = np.percentile(x, [10, 50, 90])
    assert M.swanson(p10, p50, p90) == pytest.approx(float(x.mean()), abs=0.002)


def test_icc_gls_recovers_ke_at_fair_price():
    v = float(M.rim_gls(20.0, 0.18, 0.17, 0.15, 0.11, 0.4).valor)
    assert M.icc_gls(v, 20.0, 0.18, 0.17, 0.15, 0.4) == pytest.approx(0.11, abs=1e-6)


def test_ptbr_formatting():
    assert formato.pct(0.0507) == "5,07%"
    assert formato.pct(-0.1234, sinal=True) == "\u221212,34%"   # sinal tipográfico de menos
    assert formato.operando(formato.pct(-0.107)) == "(\u221210,70%)"
    assert formato.operando(formato.preco(-0.63, "USD")) == "(\u2212US$ 0,63)"
    assert formato.inteiro(2000) == "2.000"
    assert formato.pct(0.1234, sinal=True) == "+12,34%"
    assert formato.preco(45.2, "BRL") == "R$ 45,20"
    assert formato.preco(12.345, "USD") == "US$ 12,35"
    assert formato.preco(1234.5, "MXN") == "MXN 1.234,50"
    assert formato.total(12.3e9, "BRL") == "R$ 12,30 bi"
    assert formato.mult(1.461538) == "1,46x"
    assert formato.pct(None) == "n/d"
    assert formato.r6(math.pi) == 3.14159
    assert formato.r6(float("nan")) is None
