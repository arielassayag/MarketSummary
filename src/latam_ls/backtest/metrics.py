"""Métricas de desempenho do backtest e do track record (determinísticas, sem LLM).

Convenções:

- ``daily_returns``: retornos simples diários do NAV (decimal). Dias ``NaN`` são descartados e
  contados em ``n_missing`` — nunca viram zero.
- Retorno anual geométrico: ``(Π(1 + r))^(periods/n) − 1``.
- Sharpe e Sortino usam o excesso sobre ``rf_daily`` quando informado (dias com ``rf`` ausente
  ficam fora da amostra do excesso); sem ``rf_daily``, o retorno é tratado como excesso
  (adequado a um livro net neutral cujo caixa não rende juros no cálculo).
- Drawdown é medido a partir do pico da riqueza, que começa em 1 (perda no primeiro dia já é
  drawdown); ``max_drawdown`` é negativo (ou zero).
- Semanas: retornos compostos por semana de calendário encerrada na sexta (``W-FRI``).
- ``deflated_sharpe_ratio``: Bailey & López de Prado (2014), "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-Normality".
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

TRADING_DAYS = 252
DEFAULT_VOL_WINDOW = 63
EULER_MASCHERONI = 0.5772156649015329
MIN_OBS_MOMENTS = 3
"""Mínimo de observações para assimetria/curtose (abaixo disso: ``NaN``)."""
ZERO_STD = 1e-12
"""Desvio por período abaixo disso é ruído de ponto flutuante (série constante): razões
que dividem pelo desvio (Sharpe, Sortino, ICIR) ficam ``NaN``, nunca "infinitas"."""

_NORMAL = NormalDist()

METRIC_KEYS = (
    "n_obs", "n_missing", "total_return", "ann_return", "ann_vol", "sharpe", "sortino",
    "max_drawdown", "calmar", "hit_rate_weekly", "skew", "excess_kurtosis", "best_week",
    "worst_week", "pct_time_vol_in_band", "avg_realized_vol_63d",
)


# ==========================================================
# Utilitários
# ==========================================================

def _clean(returns: pd.Series) -> tuple[pd.Series, int]:
    """Retornos numéricos finitos e a contagem de ausentes (``NaN``/``±inf``)."""
    r = pd.to_numeric(pd.Series(returns), errors="coerce").astype(float)
    finite = np.isfinite(r.to_numpy())
    return r[finite], int((~finite).sum())


def _safe_div(a: float, b: float) -> float:
    if not (math.isfinite(a) and math.isfinite(b)) or b == 0:
        return float("nan")
    return float(a / b)


def weekly_returns(returns: pd.Series) -> pd.Series:
    """Retornos compostos por semana (sexta a sexta) a partir de retornos diários.

    Com ``DatetimeIndex`` usa semanas de calendário encerradas na sexta (``W-FRI``); com outro
    índice agrupa blocos consecutivos de 5 observações. Semanas sem observação não aparecem.
    """
    r, _ = _clean(returns)
    if r.empty:
        return pd.Series(dtype=float)
    if isinstance(r.index, pd.DatetimeIndex):
        grp = r.groupby(r.index.to_period("W-FRI"))
        out = grp.apply(lambda s: float(np.prod(1.0 + s.to_numpy()) - 1.0))
        out.index = out.index.to_timestamp(how="end").normalize()
        return out.astype(float)
    block = np.arange(len(r)) // 5
    vals = [float(np.prod(1.0 + r.to_numpy()[block == b]) - 1.0) for b in np.unique(block)]
    return pd.Series(vals, dtype=float)


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Drawdown diário (≤ 0) da riqueza ``Π(1 + r)`` em relação ao pico (que começa em 1).

    Dias com retorno ausente não aparecem no resultado (não são tratados como retorno zero).
    """
    r, _ = _clean(returns)
    if r.empty:
        return pd.Series(dtype=float, name="drawdown")
    wealth = np.cumprod(1.0 + r.to_numpy())
    peak = np.maximum.accumulate(np.maximum(wealth, 1.0))
    return pd.Series(wealth / peak - 1.0, index=r.index, name="drawdown")


def rolling_realized_vol(returns: pd.Series, window: int = DEFAULT_VOL_WINDOW,
                         periods: int = TRADING_DAYS) -> pd.Series:
    """Volatilidade realizada anualizada em janela móvel de ``window`` observações completas."""
    if window < 2:
        raise ValueError("A janela de volatilidade precisa ter pelo menos 2 observações.")
    r, _ = _clean(returns)
    return (r.rolling(window, min_periods=window).std(ddof=1) * math.sqrt(periods)).rename(
        "realized_vol")


# ==========================================================
# Métricas
# ==========================================================

def performance_metrics(
    daily_returns: pd.Series,
    rf_daily: pd.Series | None = None,
    periods: int = TRADING_DAYS,
    vol_band_min: float | None = None,
    vol_band_max: float | None = None,
    vol_window: int = DEFAULT_VOL_WINDOW,
) -> dict[str, float]:
    """Métricas de desempenho de uma série de retornos diários.

    Chaves: ``n_obs``, ``n_missing``, ``total_return``, ``ann_return`` (geométrico),
    ``ann_vol``, ``sharpe`` (excesso sobre ``rf_daily``), ``sortino``, ``max_drawdown``
    (negativo), ``calmar``, ``hit_rate_weekly``, ``skew``, ``excess_kurtosis``, ``best_week``,
    ``worst_week``, ``pct_time_vol_in_band`` (fração dos dias com vol realizada de
    ``vol_window`` pregões dentro de ``[vol_band_min, vol_band_max]``; ``NaN`` sem banda) e
    ``avg_realized_vol_63d`` (média da vol realizada móvel). Métricas indefinidas (amostra
    curta, desvio zero) ficam ``NaN`` — nunca zero.
    """
    if periods <= 0:
        raise ValueError("periods precisa ser positivo.")
    nan = float("nan")
    out: dict[str, float] = dict.fromkeys(METRIC_KEYS, nan)
    r, n_missing = _clean(daily_returns)
    n = len(r)
    out["n_obs"] = float(n)
    out["n_missing"] = float(n_missing)
    if n == 0:
        return out
    rv = r.to_numpy()
    if np.any(rv <= -1.0):
        raise ValueError("Retorno diário <= −100%: série inválida para métricas de NAV.")
    log_total = float(np.sum(np.log1p(rv)))
    out["total_return"] = float(math.expm1(log_total))
    out["ann_return"] = float(math.expm1(log_total * periods / n))

    # Excesso sobre a taxa livre de risco (dias sem rf ficam fora do excesso).
    if rf_daily is not None:
        rf = pd.to_numeric(pd.Series(rf_daily), errors="coerce").astype(float).reindex(r.index)
        ex = (r - rf).dropna()
    else:
        ex = r
    exv = ex.to_numpy()
    if n >= 2:
        sd = float(np.std(rv, ddof=1))
        out["ann_vol"] = sd * math.sqrt(periods)
    if len(exv) >= 2:
        sd_ex = float(np.std(exv, ddof=1))
        out["sharpe"] = _safe_div(float(np.mean(exv)), sd_ex) * math.sqrt(periods) \
            if sd_ex > ZERO_STD else nan
        downside = float(np.sqrt(np.mean(np.minimum(exv, 0.0) ** 2)))
        out["sortino"] = (_safe_div(float(np.mean(exv)), downside) * math.sqrt(periods)
                          if downside > ZERO_STD else nan)

    dd = drawdown_series(r)
    mdd = float(dd.min())
    out["max_drawdown"] = mdd
    out["calmar"] = _safe_div(out["ann_return"], abs(mdd)) if mdd < 0 else nan

    if n >= MIN_OBS_MOMENTS:
        out["skew"] = float(r.skew())
    if n >= MIN_OBS_MOMENTS + 1:
        out["excess_kurtosis"] = float(r.kurt())

    wk = weekly_returns(r)
    if len(wk):
        out["hit_rate_weekly"] = float((wk > 0).mean())
        out["best_week"] = float(wk.max())
        out["worst_week"] = float(wk.min())

    if n >= vol_window:
        rvol = rolling_realized_vol(r, vol_window, periods).dropna()
        if len(rvol):
            out["avg_realized_vol_63d"] = float(rvol.mean())
            if vol_band_min is not None and vol_band_max is not None:
                if vol_band_min > vol_band_max:
                    raise ValueError("vol_band_min não pode exceder vol_band_max.")
                inside = (rvol >= vol_band_min) & (rvol <= vol_band_max)
                out["pct_time_vol_in_band"] = float(inside.mean())
    return out


def _sharpe_variance_factor(sr: float, skew: float, kurt_raw: float) -> float:
    """``1 − γ₃·SR + (γ₄ − 1)/4·SR²`` (Mertens/Opdyke; γ₄ = curtose bruta)."""
    return 1.0 - skew * sr + (kurt_raw - 1.0) / 4.0 * sr * sr


def expected_max_sharpe(n_trials: int, sharpe_trials_std: float) -> float:
    """Máximo esperado de ``n_trials`` Sharpe estimados sob H0 (Sharpe verdadeiro zero).

    ``E[max] ≈ σ·[(1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e))]`` (γ = Euler-Mascheroni).
    Com ``N = 1`` o máximo esperado é zero.
    """
    if n_trials < 1:
        raise ValueError("n_trials precisa ser >= 1.")
    if n_trials == 1:
        return 0.0
    g = EULER_MASCHERONI
    z1 = _NORMAL.inv_cdf(1.0 - 1.0 / n_trials)
    z2 = _NORMAL.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return float(sharpe_trials_std * ((1.0 - g) * z1 + g * z2))


def deflated_sharpe_ratio(
    sharpe: float,
    n_obs: int,
    n_trials: int,
    skew: float,
    kurtosis: float,
    sharpe_trials_std: float | None = None,
    *,
    kurtosis_is_excess: bool = True,
    periods_per_year: int | None = None,
) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado, 2014): probabilidade em [0, 1].

    ``DSR = Φ((SR − SR₀)·√(T − 1) / √(1 − γ₃·SR + (γ₄ − 1)/4·SR²))`` em que ``SR₀`` é o
    máximo esperado dos Sharpe de ``n_trials`` tentativas sob H0 (:func:`expected_max_sharpe`).

    - ``sharpe``: Sharpe **por período** (mesma frequência de ``n_obs``), salvo se
      ``periods_per_year`` for informado — então ``sharpe`` e ``sharpe_trials_std`` são
      anualizados e convertidos dividindo por ``√periods_per_year``.
    - ``kurtosis``: curtose em EXCESSO (normal = 0, igual a ``performance_metrics``) por padrão;
      ``kurtosis_is_excess=False`` aceita a curtose bruta (normal = 3).
    - ``sharpe_trials_std``: desvio-padrão dos Sharpe entre as tentativas; ausente ⇒ desvio do
      estimador sob H0, ``1/√(T − 1)``.
    - ``n_trials = 1`` reduz ao Probabilistic Sharpe Ratio contra zero.

    Entradas não finitas, ``n_obs < 2`` ou fator de variância não positivo ⇒ ``NaN``.
    """
    if n_trials < 1:
        raise ValueError("n_trials precisa ser >= 1.")
    vals = (sharpe, skew, kurtosis)
    if any(v is None or not math.isfinite(float(v)) for v in vals) or n_obs < 2:
        return float("nan")
    sr = float(sharpe)
    std_trials = None if sharpe_trials_std is None else float(sharpe_trials_std)
    if periods_per_year is not None:
        if periods_per_year <= 0:
            raise ValueError("periods_per_year precisa ser positivo.")
        scale = math.sqrt(periods_per_year)
        sr /= scale
        std_trials = None if std_trials is None else std_trials / scale
    if std_trials is None:
        std_trials = 1.0 / math.sqrt(n_obs - 1.0)
    if not (math.isfinite(std_trials) and std_trials >= 0):
        return float("nan")
    kurt_raw = float(kurtosis) + 3.0 if kurtosis_is_excess else float(kurtosis)
    var_factor = _sharpe_variance_factor(sr, float(skew), kurt_raw)
    if not var_factor > 0:
        return float("nan")
    sr0 = expected_max_sharpe(int(n_trials), std_trials)
    z = (sr - sr0) * math.sqrt(n_obs - 1.0) / math.sqrt(var_factor)
    return float(_NORMAL.cdf(z))


def ic_summary(ic: pd.DataFrame) -> pd.DataFrame:
    """Resumo do IC por sinal (colunas de ``ic``; linhas = datas de rebalanceamento).

    Colunas: ``n`` (semanas com IC definido), ``mean``, ``std``, ``icir`` (média/desvio),
    ``t_stat`` (média/(desvio/√n)) e ``hit_rate`` (fração de IC > 0). ``NaN`` de uma semana
    (IC indefinido) fica fora da amostra; menos de 2 observações ⇒ desvio/ICIR/t ``NaN``.
    """
    rows: dict[str, dict[str, float]] = {}
    for col in ic.columns:
        s = pd.to_numeric(ic[col], errors="coerce").astype(float)
        s = s[np.isfinite(s.to_numpy())]
        n = len(s)
        mean = float(s.mean()) if n else float("nan")
        std = float(s.std(ddof=1)) if n >= 2 else float("nan")
        icir = _safe_div(mean, std) if n >= 2 and std > ZERO_STD else float("nan")
        t = icir * math.sqrt(n) if math.isfinite(icir) else float("nan")
        rows[str(col)] = {"n": float(n), "mean": mean, "std": std, "icir": icir, "t_stat": t,
                          "hit_rate": float((s > 0).mean()) if n else float("nan")}
    out = pd.DataFrame.from_dict(rows, orient="index",
                                 columns=["n", "mean", "std", "icir", "t_stat", "hit_rate"])
    out.index.name = "signal"
    return out
