"""DADOS SIMULADOS: revisão não autora do mínimo de pares Newey-West.

Autoria p0_bancos_argentinos; fixture/oráculo escalar próprios, imports CDP normais.
Não requer estudo privado, dados externos, configurações ou sorteio/seeds.
"""
from __future__ import annotations

from decimal import Decimal, localcontext

import numpy as np
import pytest

from cdp.risk.model import newey_west_ewma_cov

D = Decimal


def momento(rows, i, j, lag, half):
    terms = []
    for t in range(lag, len(rows)):
        left, right = rows[t][i], rows[t-lag][j]
        if left is None or right is None:
            continue
        left, right = D(str(left)), D(str(right))
        if not left.is_finite() or not right.is_finite():
            continue
        age = D(len(rows)-1-t)
        weight = D("0.5") ** (age / D(str(half)))
        terms.append((weight, left, right))
    if not terms:
        return None, 0
    return (sum((w*a*b for w, a, b in terms), D(0)) / sum((w for w, _, _ in terms), D(0)),
            len(terms))


def esperado(rows, half, lags):
    size = len(rows[0])
    out = [[None]*size for _ in range(size)]
    counts = [[0]*size for _ in range(size)]
    raw_diag = []
    with localcontext() as context:
        context.prec = 80
        for i in range(size):
            for j in range(size):
                base, n = momento(rows, i, j, 0, half)
                counts[i][j] = n
                raw = base
                if base is not None:
                    for lag in range(1, lags+1):
                        forward, nf = momento(rows, i, j, lag, half)
                        backward, nb = momento(rows, j, i, lag, half)
                        raw += (D(1)-D(lag)/D(lags+1)) * (
                            (forward if nf >= 20 else D(0)) + (backward if nb >= 20 else D(0)))
                if i == j:
                    raw_diag.append(raw)
                if n < 20:
                    continue
                out[i][j] = base if i == j and raw <= 0 else raw
    return out, counts, raw_diag


def verificar(rows, half, lags):
    array = np.array([[np.nan if v is None else float(v) for v in row] for row in rows])
    before = array.copy()
    expect, counts, raw = esperado(rows, half, lags)
    got, actual_counts = newey_west_ewma_cov(array, half, lags)
    assert actual_counts.tolist() == counts
    assert np.array_equal(array, before, equal_nan=True)
    for i, row in enumerate(expect):
        for j, value in enumerate(row):
            if value is None:
                assert np.isnan(got[i, j])
            else:
                assert np.isfinite(got[i, j])
                assert abs(D(str(got[i, j]))-value) <= D("1e-12")
    return got, actual_counts, raw


@pytest.mark.parametrize("n", [19, 20])
@pytest.mark.parametrize("half", [4, 84])
@pytest.mark.parametrize("lags", [0, 1, 3])
def test_marginal_curta_contra_60_preserva_diagonal_boa(n, half, lags):
    rows = [["0.008" if t < n else None, str(D("0.01") + D(t%3)*D("0.002"))]
            for t in range(60)]
    cov, counts, _ = verificar(rows, half, lags)
    assert counts.tolist() == [[n, n], [n, 60]]
    assert np.isfinite(cov[1, 1]) and cov[1, 1] > 0
    if n == 19:
        assert np.isnan(cov[0, 0]) and np.isnan(cov[0, 1]) and np.isnan(cov[1, 0])
    else:
        assert np.isfinite(cov).all()


@pytest.mark.parametrize("half", [4, 84])
@pytest.mark.parametrize("lags", [0, 1, 3])
def test_duas_marginais_60_overlap_19_nao_inventa_covariancia(half, lags):
    rows = [["0.01" if t < 60 else None, "0.02" if t >= 41 else None] for t in range(101)]
    cov, counts, _ = verificar(rows, half, lags)
    assert counts.tolist() == [[60, 19], [19, 60]]
    assert np.isfinite(np.diag(cov)).all()
    assert np.isnan(cov[0, 1]) and np.isnan(cov[1, 0])


@pytest.mark.parametrize("lags", [0, 3])
def test_zero_observado_curto_e_ausencia_total_nao_viram_risco_estimado(lags):
    rows = [["0" if t < 19 else None, None, "0.01"] for t in range(60)]
    cov, counts, _ = verificar(rows, 4, lags)
    assert counts.tolist() == [[19, 0, 19], [0, 0, 0], [19, 0, 60]]
    assert np.isnan(cov[0, 0]) and np.isnan(cov[1, :]).all() and np.isfinite(cov[2, 2])


@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf"])
def test_observacao_nao_finita_nao_atinge_minimo_20(invalid):
    rows = [["0.01", "0.02"]]*19 + [[invalid, "0.02"]]
    cov, counts, _ = verificar(rows, 4, 3)
    assert counts.tolist() == [[19, 19], [19, 20]]
    assert np.isnan(cov[0, 0]) and np.isfinite(cov[1, 1])


@pytest.mark.parametrize("n", [20, 60, 80])
def test_nw_minimo_sem_lag_estimavel_e_fallback_negativo_suficiente(n):
    rows = [["0.02" if t%2 == 0 else "-0.01"] for t in range(n)]
    cov, counts, raw = verificar(rows, "0.2", 1)
    with localcontext() as ctx:
        ctx.prec = 80
        base, _ = momento(rows, 0, 0, 0, "0.2")
    assert counts[0, 0] == n
    if n == 20:
        # Lag1 só tem19 pares: nenhum ajuste NW pode provocar fallback.
        assert raw[0] == base
    else:
        assert raw[0] < 0
    assert abs(D(str(cov[0, 0])) - base) <= D("1e-12")


def test_zeros_suficientes_sao_zero_observado_sem_imputar_coluna_ausente():
    rows = [["0", None, "0.01"]]*60
    cov, counts, _ = verificar(rows, 84, 3)
    assert counts.tolist() == [[60, 0, 60], [0, 0, 0], [60, 0, 60]]
    assert cov[0, 0] == 0 and np.isnan(cov[1, 1]) and cov[2, 2] > 0
