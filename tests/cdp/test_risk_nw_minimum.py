"""Regressão do mínimo de pares. DADOS SIMULADOS; imports normais CDP.

Derivação ROOT dos 16 microcasos inline do candidato revisado. Os oito
confrontos com 984 retornos permanecem no estudo externo congelado."""
from decimal import Decimal, localcontext

import numpy as np
import pytest

from cdp.risk.model import factor_covariance, newey_west_ewma_cov

D = Decimal
TOL = D("1e-12")


def decimal_lag(rows, half, lag):
    """Oráculo escalar local independente; nenhum cálculo CDP no esperado."""
    k, n = len(rows[0]), len(rows)
    count = [[0] * k for _ in range(k)]
    cov = [[None] * k for _ in range(k)]
    with localcontext() as ctx:
        ctx.prec = 70
        for i in range(k):
            for j in range(k):
                total, den = D(0), D(0)
                for t in range(lag, n):
                    a, b = rows[t][i], rows[t - lag][j]
                    if a is None or b is None:
                        continue
                    weight = D("0.5") ** (D(n - 1 - t) / D(str(half)))
                    total += weight * D(str(a)) * D(str(b))
                    den += weight
                    count[i][j] += 1
                cov[i][j] = total / den if den else None
    return cov, count


def decimal_nw(rows, half, lags):
    base, count = decimal_lag(rows, half, 0)
    out = [r[:] for r in base]
    with localcontext() as ctx:
        ctx.prec = 70
        for lag in range(1, lags + 1):
            cov, cnt = decimal_lag(rows, half, lag)
            bartlett = D(lags + 1 - lag) / D(lags + 1)
            for i in range(len(out)):
                for j in range(len(out)):
                    if out[i][j] is None:
                        continue
                    a = cov[i][j] if cnt[i][j] >= 20 else D(0)
                    b = cov[j][i] if cnt[j][i] >= 20 else D(0)
                    out[i][j] += bartlett * ((a or D(0)) + (b or D(0)))
        for i in range(len(out)):
            for j in range(len(out)):
                if count[i][j] < 20:
                    out[i][j] = None
            if count[i][i] >= 20 and out[i][i] <= 0:
                out[i][i] = base[i][i]
    return out, count


def as_float(rows):
    return np.array([[np.nan if value is None else float(value) for value in row]
                     for row in rows])


def check_decimal(expected, native):
    assert native.shape == (len(expected), len(expected[0]))
    for i, row in enumerate(expected):
        for j, value in enumerate(row):
            if value is None:
                assert np.isnan(native[i, j])
            else:
                assert np.isfinite(native[i, j])
                assert abs(value - D(str(native[i, j]))) <= TOL


@pytest.mark.parametrize("n", [18, 19, 20, 21])
@pytest.mark.parametrize("lags", [0, 3])
def test_minimum_pair_contract_is_preserved_on_diagonal(n, lags):
    rows = [["0.01"]] * n
    expected, count = decimal_nw(rows, 4, lags)
    got, actual_count = newey_west_ewma_cov(as_float(rows), 4, lags)
    assert actual_count.tolist() == count == [[n]]
    check_decimal(expected, got)
    if n < 20:
        assert expected == [[None]]
    else:
        assert expected[0][0] > 0


@pytest.mark.parametrize("n", [19, 20, 24])
def test_observed_zero_variance_never_overrides_insufficient_pairs(n):
    rows = [["0"]] * n
    expected, count = decimal_nw(rows, 4, 3)
    got, cnt = newey_west_ewma_cov(as_float(rows), 4, 3)
    assert cnt.tolist() == count == [[n]]
    check_decimal(expected, got)
    if n >= 20:
        assert got[0, 0] == 0


def test_sufficient_nonpositive_nw_uses_lag_zero_fallback():
    rows = [["0.02"], ["-0.01"]] * 12
    lag0, _ = decimal_lag(rows, "0.2", 0)
    lag1, cnt1 = decimal_lag(rows, "0.2", 1)
    assert cnt1 == [[23]] and lag0[0][0] + lag1[0][0] < 0
    expected, count = decimal_nw(rows, "0.2", 1)
    got, cnt = newey_west_ewma_cov(as_float(rows), 0.2, 1)
    assert expected == lag0 and cnt.tolist() == count == [[24]]
    check_decimal(expected, got)


def test_completely_missing_factor_stays_missing():
    rows = [[None, "0.01"]] * 24
    expected, count = decimal_nw(rows, 4, 3)
    got, cnt = newey_west_ewma_cov(as_float(rows), 4, 3)
    assert cnt.tolist() == count == [[0, 0], [0, 24]]
    check_decimal(expected, got)


def test_asymmetric_missing_pairs_use_their_own_denominators():
    rows = [["0.01", "0.02"], ["-0.006", "0.009"],
            ["0.004", "-0.013"], ["-0.012", "-0.007"]] * 8
    for t in [0, 3, 9, 18, 25]:
        rows[t] = [None, rows[t][1]]
    for t in [1, 3, 11, 20, 28]:
        rows[t] = [rows[t][0], None]
    expected, count = decimal_nw(rows, 4, 3)
    got, cnt = newey_west_ewma_cov(as_float(rows), 4, 3)
    assert cnt.tolist() == count == [[27, 23], [23, 27]]
    check_decimal(expected, got)
    # Dado ausente não vira retorno zero: o contrafactual altera o momento lag0.
    imputed = [["0" if v is None else v for v in row] for row in rows]
    bad, _ = decimal_lag(imputed, 4, 0)
    good, _ = decimal_lag(rows, 4, 0)
    assert abs(good[0][1] - bad[0][1]) > D("1e-8")


def test_sufficient_marginals_do_not_invent_pair_overlap():
    rows = [["0.01", None]] * 60 + [[None, "0.02"]] * 60
    expected, count = decimal_nw(rows, 84, 3)
    got, cnt = newey_west_ewma_cov(as_float(rows), 84, 3)
    assert cnt.tolist() == count == [[60, 0], [0, 60]]
    check_decimal(expected, got)
    assert np.isnan(got[0, 1]) and np.isfinite(np.diag(got)).all()


def test_sufficient_annual_covariance_is_literal_one_scaling():
    rows = [["0.01"]] * 20
    cov, meta = factor_covariance(as_float(rows), 4, 8, 3)
    assert abs(D(str(cov[0, 0])) - D("0.0001") * 252) <= TOL
    assert meta == {"psd_clipped_eigenvalues": 0, "factor_pairs_without_overlap": 0,
                    "min_pair_obs": 20}
