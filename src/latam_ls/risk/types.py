"""Contêiner do modelo de risco fatorial: Σ = B F Bᵀ + D (anualizado)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

MARKET_FACTOR = "market"
STYLE_FACTORS = ["beta", "size", "momentum", "resvol", "value", "liquidity", "fx_sens"]
COUNTRY_PREFIX = "country:"
SECTOR_PREFIX = "sector:"
TRADING_DAYS = 252


def country_factor(code: str) -> str:
    return f"{COUNTRY_PREFIX}{code}"


def sector_factor(name: str) -> str:
    return f"{SECTOR_PREFIX}{name}"


@dataclass(frozen=True)
class RiskModel:
    as_of: date
    exposures: pd.DataFrame        # emissor x fator (B), índice = issuer_id
    factor_cov: pd.DataFrame       # fator x fator (F), anualizada
    specific_var: pd.Series        # emissor (D), variância anual
    factor_returns: pd.DataFrame   # data x fator, retornos diários estimados
    specific_returns: pd.DataFrame  # data x emissor, resíduos diários
    factor_groups: dict[str, str] = field(default_factory=dict)  # fator -> market|country|sector|style
    r_squared: pd.Series | None = None
    meta: dict = field(default_factory=dict)

    @property
    def assets(self) -> list[str]:
        return list(self.exposures.index)

    @property
    def factor_names(self) -> list[str]:
        return list(self.exposures.columns)

    @property
    def specific_vol(self) -> pd.Series:
        return np.sqrt(self.specific_var)

    def factors_in_group(self, group: str) -> list[str]:
        return [f for f in self.factor_names if self.factor_groups.get(f) == group]

    def align(self, w: pd.Series) -> pd.Series:
        """Reindexa pesos ao universo do modelo; nomes fora do modelo são erro (não zero silencioso)."""
        if not np.isfinite(w.to_numpy(dtype=float)).all():
            bad = sorted(map(str, w.index[~np.isfinite(w.to_numpy(dtype=float))]))
            raise ValueError(f"Pesos não finitos (NaN/inf) não são zero: {bad}")
        w = w[w != 0]
        extra = sorted(set(w.index) - set(self.assets))
        if extra:
            raise KeyError(f"Pesos para emissores fora do modelo de risco: {extra}")
        return w.reindex(self.assets).fillna(0.0)

    def cov_matrix(self, assets: list[str] | None = None) -> pd.DataFrame:
        ids = assets or self.assets
        B = self.exposures.loc[ids].to_numpy()
        F = self.factor_cov.loc[self.factor_names, self.factor_names].to_numpy()
        cov = B @ F @ B.T + np.diag(self.specific_var.loc[ids].to_numpy())
        return pd.DataFrame(cov, index=ids, columns=ids)

    def factor_exposure(self, w: pd.Series) -> pd.Series:
        wa = self.align(w)
        return self.exposures.T @ wa

    def portfolio_variance(self, w: pd.Series) -> float:
        wa = self.align(w)
        x = self.exposures.T @ wa
        F = self.factor_cov.loc[x.index, x.index]
        return float(x @ F @ x + (wa ** 2 * self.specific_var).sum())

    def portfolio_vol(self, w: pd.Series) -> float:
        return float(np.sqrt(max(self.portfolio_variance(w), 0.0)))
