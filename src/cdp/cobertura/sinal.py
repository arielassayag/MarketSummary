"""Sinal de valuation para o alpha — sombra (peso 0) até a promoção por IC realizado.

- :func:`valuation_gap`: ``α_rel`` de cada emissor como z-score robusto (mediana/MAD) dentro de
  país × setor (≥ 5 nomes; senão setor, senão universo), winsorizado em ±3; sem preço-alvo ou
  "Em revisão" ⇒ ``NaN`` (nunca zero). A ortogonalização aos fatores é a mesma dos demais sinais
  (feita pelo consumidor).
- :func:`alpha_cobertura`: tradução para retorno esperado de Grinold,
  ``α = IC × m_incerteza × m_confiança × m_frescor × σ_específica × z`` (shadow). O upside bruto
  do preço-alvo nunca entra no otimizador: a inclinação realizado/previsto de retornos implícitos
  em previsões de 12 meses é da ordem de 0,06–0,10 na literatura.
- Promoção (DESIGN decisão #13, com a correção do comitê de risco): IC residual semanal sem
  sobreposição, ≥ 26 semanas, IC médio ≥ 0,01 e t de Newey–West ≥ 1,5; rebaixamento automático.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from .livro import SnapshotCobertura
    from .parametros import ParametrosCobertura

WINSOR_Z = 3.0
MIN_GRUPO = 5
SEM_SINAL = ("Em revisão", "Sem preço-alvo")


def _z_robusto(s: pd.Series) -> pd.Series:
    med = s.median()
    mad = (s - med).abs().median() * 1.4826
    if not np.isfinite(mad) or mad <= 1e-12:
        sd = s.std(ddof=0)
        if not np.isfinite(sd) or sd <= 1e-12:
            return pd.Series(0.0, index=s.index)
        return (s - s.mean()) / sd
    return (s - med) / mad


def z_por_grupo(tab: pd.DataFrame, col: str = "alpha_rel") -> pd.Series:
    t = tab[tab[col].notna() & ~tab["rating"].isin(SEM_SINAL)].copy()
    z = pd.Series(np.nan, index=tab.index, dtype=float)
    if t.empty:
        return z
    t["_g"] = t["pais"].astype(str) + "|" + t["setor"].astype(str)
    feitos: set[str] = set()
    for _, sub in t.groupby("_g"):
        if len(sub) >= MIN_GRUPO:
            z.loc[sub.index] = _z_robusto(sub[col].astype(float))
            feitos |= set(sub.index)
    resto = t.loc[[i for i in t.index if i not in feitos]]
    for _, sub in resto.groupby("setor"):
        base = t[t["setor"] == sub["setor"].iloc[0]]
        if len(base) >= MIN_GRUPO:
            zz = _z_robusto(base[col].astype(float))
            z.loc[sub.index] = zz.loc[sub.index]
            feitos |= set(sub.index)
    resto = [i for i in t.index if i not in feitos]
    if resto:
        zz = _z_robusto(t[col].astype(float))
        z.loc[resto] = zz.loc[resto]
    return z.clip(-WINSOR_Z, WINSOR_Z)


def valuation_gap(snap: SnapshotCobertura) -> pd.Series:
    """``alpha_rel`` como z dentro de país × setor (winsorizado), indexado por ``issuer_id``;
    emissor sem preço-alvo fica ``NaN`` (nunca zero)."""
    tab = snap.estado()
    if tab.empty:
        return pd.Series(dtype=float, name="valuation_gap")
    z = z_por_grupo(tab)
    z.name = "valuation_gap"
    z.index.name = "issuer_id"
    return z


def m_frescor(dias: float, pleno: float = 30, meia_vida: float = 60, zero: float = 105) -> float:
    if dias <= pleno:
        return 1.0
    if dias > zero:
        return 0.0
    return float(2 ** (-(dias - pleno) / meia_vida))


def alpha_cobertura(snap: SnapshotCobertura, sigma_especifica: pd.Series, params: ParametrosCobertura,
                    as_of: date | None = None) -> pd.DataFrame:
    """Alpha de valuation em sombra (peso 0): ``IC × m_inc × m_conf × m_fresco × σ_esp × z``."""
    a = params.sec("alpha")
    tab = snap.estado()
    if tab.empty:
        return pd.DataFrame(columns=["z", "m_incerteza", "m_confianca", "m_frescor", "sigma", "alpha"])
    z = z_por_grupo(tab)
    as_of = as_of or snap.as_of
    fr = a["frescor"]
    out = pd.DataFrame(index=tab.index)
    out["z"] = z
    out["m_incerteza"] = tab["incerteza"].map(lambda c: float(a["m_incerteza"].get(c, np.nan))
                                              if isinstance(c, str) else np.nan)
    out["m_confianca"] = tab["confianca"].map(lambda c: float(a["m_confianca"].get(c, np.nan))
                                              if isinstance(c, str) else np.nan)
    idade = tab["snapshot"].map(lambda d: (as_of - date.fromisoformat(d)).days)
    out["m_frescor"] = idade.map(lambda d: m_frescor(d, fr["pleno_dias"], fr["meia_vida_dias"], fr["zero_apos_dias"]))
    out["sigma"] = sigma_especifica.reindex(out.index).astype(float)
    out["alpha"] = float(a["ic"]) * out["m_incerteza"] * out["m_confianca"] * out["m_frescor"] * out["sigma"] * out["z"]
    return out


__all__ = ["alpha_cobertura", "m_frescor", "valuation_gap", "z_por_grupo"]
