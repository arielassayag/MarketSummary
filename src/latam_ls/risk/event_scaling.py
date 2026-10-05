"""Ajuste de risco para janelas de evento (ex.: eleição), quando a vol implícita supera a realizada.

A covariância histórica subestima o risco de gap em eventos binários conhecidos (no 1º turno de
2026 a vol implícita de 1 mês do EWZ estava perto do dobro da realizada). Durante uma janela
ativa, o fator do país e o risco específico dos emissores daquele país são escalados pelo
multiplicador configurado; covariâncias com outros fatores escalam linearmente, preservando
as correlações e a positividade da matriz.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd

from ..config import FundConfig
from .types import RiskModel, country_factor


def active_event_windows(cfg: FundConfig, on: date) -> list[dict]:
    out = []
    for w in cfg.risk.event_windows:
        start = date.fromisoformat(str(w["start"]))
        end = date.fromisoformat(str(w["end"]))
        if start <= on <= end and float(w.get("vol_multiplier", 1.0)) > 0:
            out.append(w)
    return out


def apply_event_windows(model: RiskModel, issuer_country: pd.Series, cfg: FundConfig,
                        on: date) -> RiskModel:
    """Devolve um novo ``RiskModel`` com o risco dos países em janela de evento escalado.

    ``issuer_country``: país de cada emissor (índice ``issuer_id``). Sem janela ativa, devolve
    o próprio modelo. O ajuste é registrado em ``meta['event_windows']``.
    """
    windows = active_event_windows(cfg, on)
    if not windows:
        return model
    factors = model.factor_names
    scale_f = pd.Series(1.0, index=factors)
    spec = model.specific_var.copy()
    applied = []
    for w in windows:
        m = float(w["vol_multiplier"])
        code = str(w["country"])
        fname = country_factor(code)
        if fname in scale_f.index:
            scale_f[fname] *= m
        members = issuer_country.reindex(spec.index) == code
        spec[members] = spec[members] * m ** 2
        applied.append({"name": w.get("name", code), "country": code, "multiplier": m,
                        "factor_scaled": fname in scale_f.index, "n_issuers": int(members.sum())})
    s = scale_f.to_numpy()
    F = model.factor_cov.loc[factors, factors].to_numpy() * np.outer(s, s)
    meta = dict(model.meta)
    meta["event_windows"] = applied
    return replace(model, factor_cov=pd.DataFrame(F, index=factors, columns=factors),
                   specific_var=spec, meta=meta)
