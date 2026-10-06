"""Bloco macro híbrido do modelo de risco (``risk_model.macro_factors``).

Commodities e dólar (Brent ``BZ=F``, cobre ``HG=F``, ouro ``GC=F``, dólar ``DX-Y.NYB``) não são
fatores transversais do modelo, mas movem grupos de emissores que um livro neutro em país e
setor ainda pode concentrar (petróleo × consumidores de combustível, cobre × minério). O bloco:

- **exposições**: betas de série temporal dos resíduos específicos diários de cada emissor nos
  retornos macro (regressão conjunta, pesos EWMA de meia-vida ``macro_beta_halflife``),
  encolhidos (Vasicek) para a média do setor: ``b̃ = b·τ²/(τ² + se²) + b̄_setor·se²/(τ² + se²)``;
  emissor sem histórico suficiente recebe a média do setor (prior), nunca zero;
- **retornos fatoriais** = retornos diários dos próprios ativos macro;
- **covariância conjunta** com a mesma receita do modelo (vol e correlação EWMA, Newey–West);
  o bloco fatorial original é preservado exatamente e a covariância cruzada é encolhida, se
  preciso, até a matriz ficar positiva semidefinida;
- **risco específico** reduzido pela parte agora explicada pelo bloco:
  ``D̃_i = max(D_i − b̃_iᵀ M b̃_i, ½·D_i)`` — a variância total de cada nome não é contada duas vezes.

Série macro ausente no snapshot ⇒ o fator correspondente fica de fora (registrado em
``model.meta["macro"]``); lista vazia ⇒ o modelo volta inalterado (legado).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from .model import factor_covariance
from .types import RiskModel

if TYPE_CHECKING:  # pragma: no cover
    from ..analytics.panel import AssetPanel
    from ..config import FundConfig
    from ..market import MarketData

MACRO_PREFIX = "macro:"
MACRO_GROUP = "macro"
SPEC_FLOOR_FRACTION = 0.5
CROSS_SHRINK_STEPS = 20


def macro_factor(symbol: str) -> str:
    return f"{MACRO_PREFIX}{symbol}"


def _ewma(n: int, halflife: float) -> np.ndarray:
    w = 0.5 ** ((n - 1 - np.arange(n)) / float(halflife))
    return w / w.sum()


def macro_returns(md: MarketData, symbols: list[str], index: pd.Index) -> pd.DataFrame:
    """Retornos diários dos ativos macro alinhados às datas do modelo (ausente = ``NaN``)."""
    cols = [s for s in symbols if s in md.benchmarks.columns]
    if not cols:
        return pd.DataFrame(index=index)
    px = md.benchmarks[cols].sort_index()
    px = px.loc[: index.max()] if len(index) else px
    r = px.pct_change(fill_method=None)
    return r.reindex(index)


def macro_betas(resid: pd.DataFrame, mret: pd.DataFrame, halflife: float, min_obs: int,
                sector: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Betas encolhidos (emissor × fator macro) e diagnóstico (``imputados``, ``n_obs``)."""
    cols = list(mret.columns)
    ids = list(resid.columns)
    raw = pd.DataFrame(np.nan, index=ids, columns=cols)
    se2 = pd.DataFrame(np.nan, index=ids, columns=cols)
    X_all = mret.to_numpy(dtype=float)
    for i in ids:
        y = resid[i].to_numpy(dtype=float)
        ok = np.isfinite(y) & np.all(np.isfinite(X_all), axis=1)
        if ok.sum() < min_obs:
            continue
        X = X_all[ok]
        yy = y[ok]
        w = _ewma(len(yy), halflife)
        Xc = X - w @ X
        yc = yy - w @ yy
        XtWX = Xc.T @ (w[:, None] * Xc)
        try:
            inv = np.linalg.inv(XtWX)
        except np.linalg.LinAlgError:
            continue
        b = inv @ (Xc.T @ (w * yc))
        res = yc - Xc @ b
        n_eff = 1.0 / float(np.sum(w ** 2))
        s2 = float(w @ res ** 2) * n_eff / max(n_eff - len(cols) - 1, 1.0)
        raw.loc[i] = b
        se2.loc[i] = np.diag(inv) * s2 / n_eff  # var(b) com pesos normalizados (Σw = 1)
    sec = sector.reindex(ids).fillna("NA")
    out = raw.copy()
    imputed: list[str] = []
    for c in cols:
        col = raw[c]
        overall_mean = float(col.mean()) if col.notna().any() else 0.0
        means = col.groupby(sec).mean()
        tau2_by = col.groupby(sec).var()
        tau2_all = float(col.var()) if col.notna().sum() > 1 else 0.0
        for i in ids:
            prior = means.get(sec[i])
            prior = overall_mean if prior is None or not np.isfinite(prior) else float(prior)
            b = col.get(i)
            if b is None or not np.isfinite(b):
                out.loc[i, c] = prior
                imputed.append(i)
                continue
            tau2 = tau2_by.get(sec[i])
            tau2 = tau2_all if tau2 is None or not np.isfinite(tau2) else float(tau2)
            v = float(se2.loc[i, c])
            k = tau2 / (tau2 + v) if tau2 + v > 0 and np.isfinite(v) else 0.0
            out.loc[i, c] = k * float(b) + (1.0 - k) * prior
    return out, {"imputados": sorted(set(imputed)), "n_com_historico": int(raw.notna().all(
        axis=1).sum())}


def augment_with_macro(model: RiskModel, md: MarketData, cfg: FundConfig,
                       panel: AssetPanel | None = None) -> RiskModel:
    """Modelo com o bloco macro (ver docstring do módulo); sem fatores configurados ⇒ inalterado."""
    rm = cfg.risk_model
    symbols = list(rm.macro_factors)
    if not symbols:
        return model
    fr = model.factor_returns
    resid = model.specific_returns
    meta = dict(model.meta)
    if fr is None or fr.empty or resid is None or resid.empty:
        meta["macro"] = {"ativo": False, "motivo": "modelo sem séries de retornos"}
        return replace(model, meta=meta)
    mret = macro_returns(md, symbols, fr.index)
    mret = mret.loc[:, mret.notna().sum() >= rm.min_obs_days]
    missing = [s for s in symbols if s not in mret.columns]
    if mret.empty:
        meta["macro"] = {"ativo": False, "ausentes": missing}
        return replace(model, meta=meta)
    sector = (panel.assets["sector"] if panel is not None and "sector" in panel.assets.columns
              else pd.Series("NA", index=model.exposures.index))
    betas, info = macro_betas(resid.reindex(columns=model.exposures.index), mret,
                              rm.macro_beta_halflife, rm.min_obs_days, sector)
    names = [macro_factor(s) for s in mret.columns]
    betas.columns = names
    # Covariância conjunta com a receita do modelo; bloco fatorial original preservado.
    joint = pd.concat([fr, mret.set_axis(names, axis=1)], axis=1)
    cov, _diag = factor_covariance(joint.to_numpy(dtype=float), rm.halflife_factor_vol,
                                   rm.halflife_factor_corr, rm.newey_west_lags)
    k = len(model.factor_names)
    F = model.factor_cov.loc[model.factor_names, model.factor_names].to_numpy(dtype=float)
    C = cov[:k, k:]
    M = cov[k:, k:]
    t = 1.0
    full = None
    for _ in range(CROSS_SHRINK_STEPS + 1):
        top = np.hstack([F, t * C])
        bottom = np.hstack([t * C.T, M])
        full = np.vstack([top, bottom])
        full = 0.5 * (full + full.T)
        lam = np.linalg.eigvalsh(full)
        if lam.min() >= -1e-12 * max(lam.max(), 1e-300):
            break
        t *= 0.8
    assert full is not None
    cols = model.factor_names + names
    fcov = pd.DataFrame(full, index=cols, columns=cols)
    expo = pd.concat([model.exposures, betas.reindex(model.exposures.index)], axis=1)
    bm = betas.reindex(model.exposures.index).to_numpy(dtype=float)
    explained = np.einsum("ij,jk,ik->i", bm, M, bm)
    D = model.specific_var.reindex(model.exposures.index).to_numpy(dtype=float)
    D_new = np.maximum(D - explained, SPEC_FLOOR_FRACTION * D)
    groups = dict(model.factor_groups)
    groups.update({n: MACRO_GROUP for n in names})
    meta["macro"] = {"ativo": True, "fatores": names, "ausentes": missing,
                     "encolhimento_cruzado": t, "imputados": info["imputados"],
                     "n_com_historico": info["n_com_historico"],
                     "vol_anual": {n: float(np.sqrt(M[j, j])) for j, n in enumerate(names)},
                     "dias": int(mret.notna().all(axis=1).sum())}
    fret = pd.concat([fr, mret.set_axis(names, axis=1)], axis=1)
    return replace(model, exposures=expo, factor_cov=fcov,
                   specific_var=pd.Series(D_new, index=model.exposures.index),
                   factor_returns=fret, factor_groups=groups, meta=meta)


__all__ = ["MACRO_GROUP", "MACRO_PREFIX", "augment_with_macro", "macro_betas", "macro_factor",
           "macro_returns"]
