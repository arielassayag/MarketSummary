"""Analytics de risco ex-ante sobre um ``RiskModel``: decomposição de Euler, betas, VaR/ES.

Convenções:
- Pesos são frações do NAV (positivo = comprado, negativo = vendido). Peso ``NaN``/infinito é
  erro (nunca zero silencioso).
- Volatilidades e variâncias são anuais; VaR/ES são perdas POSITIVAS em fração do NAV.
- Retorno histórico ausente de um emissor nunca vira zero: usa-se o retorno implícito pelo
  modelo (``B_i · f_t``); se nem isso existir, a data sai da amostra (registrado).
- No ``AssetPanel`` o retorno observado logo após uma lacuna (feriado, suspensão) cobre toda
  a lacuna. Ao preencher a lacuna com ``B_i · f_t`` esse retorno é reescalado para
  ``(1 + r) / Π(1 + B_i · f) − 1`` — o retorno acumulado do emissor é preservado e o
  movimento dos fatores não é contado duas vezes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

from ..analytics.panel import AssetPanel
from .types import TRADING_DAYS, RiskModel

GROUPS = ("market", "country", "sector", "style")


@dataclass(frozen=True)
class RiskDecomposition:
    """Decomposição de risco ex-ante (variâncias anuais; participações por Euler)."""

    total_vol: float
    factor_vol: float
    specific_vol: float
    factor_share: float               # variância fatorial / variância total
    by_group: dict[str, float]        # market|country|sector|style|specific (soma 1)
    by_factor: pd.Series              # participação de Euler por fator (soma = factor_share)
    asset_contrib: pd.Series          # participação de Euler por emissor com peso (soma 1)
    mctr: pd.Series                   # ∂σ/∂w_i para todos os emissores do modelo
    exposures: pd.Series              # Bᵀw
    meta: dict = field(default_factory=dict)


def check_weights(w: pd.Series) -> pd.Series:
    """Valida pesos: ``NaN``/infinito é erro explícito (``RiskModel.align`` os zeraria)."""
    w = pd.Series(w, dtype=float)
    bad = w.index[~np.isfinite(w.to_numpy())]
    if len(bad):
        raise ValueError(f"Pesos não finitos (ausência não vira zero): {sorted(map(str, bad))}")
    if w.index.has_duplicates:
        dup = sorted(map(str, w.index[w.index.duplicated()]))
        raise ValueError(f"Pesos com emissores duplicados: {dup}")
    return w


def _factor_cov(model: RiskModel) -> pd.DataFrame:
    f = model.factor_names
    return model.factor_cov.loc[f, f]


def _cov_times(model: RiskModel, w: pd.Series) -> pd.Series:
    """Σw sem montar a matriz N×N: B (F (Bᵀw)) + D w."""
    B = model.exposures
    F = _factor_cov(model)
    x = B.T @ w
    return B @ (F @ x) + model.specific_var.reindex(B.index) * w


def risk_decomposition(w: pd.Series, model: RiskModel) -> RiskDecomposition:
    """Decomposição de Euler da variância: fatores, grupos, emissores e MCTR.

    Participações podem ser negativas (termos cruzados que reduzem risco); somam 1. Para a
    carteira vazia (variância zero) as participações são indefinidas (``NaN``).
    """
    wa = model.align(check_weights(w))
    B = model.exposures
    F = _factor_cov(model)
    x = B.T @ wa
    fx = F @ x
    factor_var = float(x @ fx)
    spec_var_i = wa ** 2 * model.specific_var.reindex(B.index)
    specific_var = float(spec_var_i.sum())
    total_var = factor_var + specific_var
    sigma = float(np.sqrt(max(total_var, 0.0)))
    sigma_w = B @ fx + model.specific_var.reindex(B.index) * wa
    held = wa[wa != 0].index
    if total_var > 0:
        by_factor = (x * fx) / total_var
        asset_contrib = (wa * sigma_w).loc[held] / total_var
        mctr = sigma_w / sigma
        factor_share = factor_var / total_var
        by_group = {g: float(by_factor[[f for f in by_factor.index
                                         if model.factor_groups.get(f) == g]].sum())
                    for g in GROUPS}
        by_group["specific"] = specific_var / total_var
    else:
        by_factor = pd.Series(np.nan, index=x.index)
        asset_contrib = pd.Series(np.nan, index=held, dtype=float)
        mctr = pd.Series(np.nan, index=B.index)
        factor_share = np.nan
        by_group = {g: np.nan for g in (*GROUPS, "specific")}
    return RiskDecomposition(
        total_vol=sigma,
        factor_vol=float(np.sqrt(max(factor_var, 0.0))),
        specific_vol=float(np.sqrt(max(specific_var, 0.0))),
        factor_share=float(factor_share),
        by_group=by_group,
        by_factor=by_factor.rename("variance_share"),
        asset_contrib=asset_contrib.rename("variance_share"),
        mctr=mctr.rename("mctr"),
        exposures=x.rename("exposure"),
        meta={"total_var": total_var, "factor_var": factor_var, "specific_var": specific_var,
              "n_positions": len(held), "as_of": str(model.as_of)},
    )


def _market_portfolio(model: RiskModel, market_w: pd.Series) -> pd.Series:
    """Carteira de mercado restrita ao universo do modelo e renormalizada (soma 1)."""
    m = market_w.reindex(model.assets)
    m = m[m.notna()]
    if m.empty or not m.sum() > 0:
        raise ValueError("Pesos de mercado sem interseção positiva com o modelo de risco.")
    m = m / m.sum()
    return m.reindex(model.assets).fillna(0.0)  # emissor fora do índice: peso nulo (não dado)


def predicted_betas(model: RiskModel, market_w: pd.Series) -> pd.Series:
    """β_i = (Σm)_i / (mᵀΣm), com ``m`` a carteira de mercado (pesos por capitalização)."""
    m = _market_portfolio(model, market_w)
    sm = _cov_times(model, m)
    var_m = float(m @ sm)
    if not var_m > 0:
        raise ValueError("Variância da carteira de mercado não positiva.")
    return (sm / var_m).rename("predicted_beta")


def portfolio_beta(w: pd.Series, model: RiskModel, market_w: pd.Series) -> float:
    """β previsto da carteira contra a carteira de mercado ponderada por capitalização."""
    wa = model.align(check_weights(w))
    return float(predicted_betas(model, market_w) @ wa)


def parametric_var_es(
    w: pd.Series, model: RiskModel, confidence: float = 0.99, horizon_days: int = 1,
) -> tuple[float, float]:
    """VaR e ES normais (média zero) no horizonte em pregões; perdas positivas em fração do NAV."""
    if not 0.5 < confidence < 1:
        raise ValueError("confidence deve estar em (0.5, 1).")
    if horizon_days < 1:
        raise ValueError("horizon_days deve ser >= 1.")
    sigma_h = model.portfolio_vol(check_weights(w)) * np.sqrt(horizon_days / TRADING_DAYS)
    nd = NormalDist()
    z = nd.inv_cdf(confidence)
    var = z * sigma_h
    es = sigma_h * nd.pdf(z) / (1.0 - confidence)
    return float(var), float(es)


def model_implied_returns(model: RiskModel, issuers: list[str],
                          dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Retornos ``B_i · f_t`` (data × emissor); ``NaN`` se faltar algum fator necessário.

    Fatores com exposição zero não são necessários; um fator necessário sem retorno na data
    (mercado fechado ou dia sem regressão) torna o retorno implícito indefinido.
    """
    B = model.exposures.loc[issuers]
    f = model.factor_returns.reindex(index=dates, columns=B.columns)
    fv = f.to_numpy()
    bv = B.to_numpy()
    out = np.empty((len(dates), len(issuers)))
    for j in range(len(issuers)):
        need = bv[j] != 0
        contrib = fv[:, need] * bv[j, need]
        out[:, j] = contrib.sum(axis=1) if need.any() else 0.0
        out[~np.isfinite(contrib).all(axis=1), j] = np.nan
    return pd.DataFrame(out, index=dates, columns=issuers)


def fill_with_model_returns(
    rets: pd.DataFrame, implied: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Preenche retornos ausentes com ``implied`` sem contar o movimento duas vezes.

    - Lacuna inicial (antes do 1º retorno) ou final (após o último): ``implied`` direto.
    - Lacuna interna: o retorno observado seguinte cobre a lacuna inteira (convenção do
      ``AssetPanel``). Os dias com ``implied`` definido são preenchidos e o retorno seguinte é
      reescalado para ``(1 + r) / Π(1 + implied) − 1``; o acumulado do emissor é preservado.
      Dias sem ``implied`` continuam ``NaN`` (a data sai da amostra; nunca zero).
    """
    r = rets.to_numpy(dtype=float, copy=True)
    m = implied.reindex(index=rets.index, columns=rets.columns).to_numpy(dtype=float)
    n_filled = n_adjusted = 0
    T = r.shape[0]
    for j in range(r.shape[1]):
        obs = np.flatnonzero(np.isfinite(r[:, j]))
        edges = [slice(0, T)] if len(obs) == 0 else [slice(0, obs[0]), slice(obs[-1] + 1, T)]
        for sl in edges:
            r[sl, j] = m[sl, j]
            n_filled += int(np.isfinite(m[sl, j]).sum())
        for g in np.flatnonzero(np.diff(obs) > 1):
            a, c = obs[g] + 1, obs[g + 1]          # lacuna a..c-1; retorno em c cobre a lacuna
            seg = m[a:c, j]
            ok = np.isfinite(seg)
            growth = float(np.prod(1.0 + seg[ok])) if ok.any() else 1.0
            if not ok.any() or not growth > 0:
                continue
            r[a:c, j] = np.where(ok, seg, np.nan)
            r[c, j] = (1.0 + r[c, j]) / growth - 1.0
            n_filled += int(ok.sum())
            n_adjusted += 1
    out = pd.DataFrame(r, index=rets.index, columns=rets.columns)
    return out, {"n_model_filled": n_filled, "n_spanning_returns_rescaled": n_adjusted}


def historical_pnl(
    w: pd.Series, panel: AssetPanel, model: RiskModel, lookback: int = 504,
) -> tuple[pd.Series, dict]:
    """P&L diário (fração do NAV) dos pesos atuais reaplicados aos últimos ``lookback`` pregões.

    Retorno ausente ⇒ retorno implícito pelo modelo (ver ``fill_with_model_returns``); se
    indefinido, a data fica ``NaN`` (fora da amostra). Retorna (série, meta com contagens).
    """
    wa = model.align(check_weights(w))
    held = wa[wa != 0]
    cal_all = pd.DatetimeIndex(panel.returns.index)
    cal_all = cal_all[cal_all <= pd.Timestamp(model.as_of)]
    cal = cal_all[-lookback:]
    if held.empty:
        return pd.Series(0.0, index=cal, name="pnl"), {"n_model_filled": 0, "n_dropped": 0}
    # Preenche no calendário completo (<= as_of) para que lacunas que cruzam o início da
    # janela reescalem corretamente o retorno que as cobre.
    rets_all = panel.returns.reindex(index=cal_all, columns=held.index)
    implied = model_implied_returns(model, list(held.index), cal_all)
    filled_all, fill_meta = fill_with_model_returns(rets_all, implied)
    filled = filled_all.loc[cal]
    pnl = (filled * held).sum(axis=1, min_count=len(held))
    pnl[filled.isna().any(axis=1)] = np.nan
    in_win = rets_all.loc[cal].isna() & filled.notna()
    meta = {
        "n_dates": int(len(cal)),
        "n_model_filled": int(in_win.to_numpy().sum()),
        "n_spanning_returns_rescaled": fill_meta["n_spanning_returns_rescaled"],
        "n_dropped": int(pnl.isna().sum()),
        "dropped_dates": [str(d.date()) for d in pnl.index[pnl.isna()]],
    }
    return pnl.rename("pnl"), meta


def historical_var_es(
    w: pd.Series,
    panel: AssetPanel,
    model: RiskModel,
    confidence: float = 0.99,
    horizon_days: int = 1,
    lookback: int = 504,
) -> tuple[float, float]:
    """VaR/ES históricos (perdas positivas) por reaplicação dos retornos em USD dos emissores.

    Para ``horizon_days > 1`` usa somas sobrepostas de ``horizon_days`` pregões consecutivos
    (janelas com data fora da amostra são descartadas, nunca completadas com zero).
    """
    if not 0.5 < confidence < 1:
        raise ValueError("confidence deve estar em (0.5, 1).")
    if horizon_days < 1:
        raise ValueError("horizon_days deve ser >= 1.")
    pnl, _ = historical_pnl(w, panel, model, lookback)
    if horizon_days > 1:
        pnl = pnl.rolling(horizon_days, min_periods=horizon_days).sum()
    sample = pnl.dropna().to_numpy()
    if len(sample) == 0:
        raise ValueError("Sem amostra histórica para VaR.")
    q = float(np.quantile(sample, 1.0 - confidence))
    tail = sample[sample <= q]
    return float(-q), float(-tail.mean())


def effective_n(w: pd.Series) -> float:
    """Número efetivo de posições: 1 / Σ (w_i / Σ|w|)² (carteira vazia ⇒ 0)."""
    w = check_weights(w)
    gross = float(w.abs().sum())
    if gross == 0:
        return 0.0
    p = w / gross
    return float(1.0 / (p ** 2).sum())
