"""Métricas de liquidez: faixas de ADTV, dias para liquidar, tetos de peso e perfil da carteira.

Convenções:

- ``adtv_usd``: valor médio diário negociado em USD (no painel, soma de todas as linhas do
  emissor na janela ``liquidity.adv_window_days``).
- ``participation``: fração máxima do volume diário que o fundo pode consumir (0 < p <= 1).
- ``nav``: patrimônio do fundo em USD; pesos são frações do NAV (positivo = comprado).

Tratamento de dado ausente (nunca vira zero silencioso no dado de origem):

- ADTV ``NaN``, zero, negativo ou não finito significa *liquidez desconhecida ou inexistente* e
  é tratado de forma conservadora: dias para liquidar = ``inf``, teto de peso por liquidez = 0
  (não negociável) e nenhuma fração da posição é considerada liquidável no perfil. A coluna
  ``adtv_missing`` do perfil sinaliza esses casos explicitamente.
- Nocional ``NaN`` produz dias ``NaN`` (não há como medir); nocional zero exige 0 dias.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

DEFAULT_HORIZONS: tuple[float, ...] = (1, 2, 3, 5, 10)
SIDE_LONG = "LONG"
SIDE_SHORT = "SHORT"


# ----------------------------------------------------------------------------------------
# Validações e utilitários
# ----------------------------------------------------------------------------------------

def _check_participation(participation: float) -> float:
    p = float(participation)
    if not (np.isfinite(p) and 0.0 < p <= 1.0):
        raise ValueError(f"Taxa de participação inválida: {participation!r} (esperado 0 < p <= 1).")
    return p


def _check_positive(value: float, name: str) -> float:
    v = float(value)
    if not (np.isfinite(v) and v > 0.0):
        raise ValueError(f"{name} precisa ser finito e positivo: {value!r}.")
    return v


def _check_horizons(horizons: Sequence[float]) -> list[float]:
    hs = [float(h) for h in horizons]
    if not hs:
        raise ValueError("É preciso informar ao menos um horizonte de liquidação.")
    if any(not (np.isfinite(h) and h > 0) for h in hs):
        raise ValueError(f"Horizontes precisam ser finitos e positivos: {list(horizons)!r}.")
    if len(set(hs)) != len(hs):
        raise ValueError(f"Horizontes duplicados: {list(horizons)!r}.")
    return sorted(hs)


def horizon_column(h: float) -> str:
    """Nome da coluna do perfil para o horizonte ``h`` (ex.: ``pct_gross_3d``)."""
    return f"pct_gross_{float(h):g}d"


def usable_adtv(adtv_usd: pd.Series) -> pd.Series:
    """ADTV utilizável (finito e > 0); valores ausentes ou inválidos ficam ``NaN``."""
    a = adtv_usd.astype(float)
    return a.where(np.isfinite(a) & (a > 0.0))


# ----------------------------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------------------------

def liquidity_tier(adtv_usd: pd.Series, breaks: Sequence[float]) -> pd.Series:
    """Classifica o ADTV em faixas ``T1`` (mais líquida) … ``T{k+1}``.

    Com ``breaks = [b0, b1, b2]`` (estritamente decrescentes): ``T1`` se ADTV >= b0, ``T2`` se
    >= b1, ``T3`` se >= b2 e ``T4`` caso contrário. ADTV ``NaN`` cai na faixa menos líquida
    (conservador: maior spread estimado).
    """
    b = [float(x) for x in breaks]
    if not b or any(not np.isfinite(x) for x in b):
        raise ValueError(f"Cortes de faixa de liquidez inválidos: {list(breaks)!r}.")
    if any(b[i] <= b[i + 1] for i in range(len(b) - 1)):
        raise ValueError(f"Cortes de faixa precisam ser estritamente decrescentes: {b!r}.")
    labels = [f"T{k + 1}" for k in range(len(b) + 1)]
    a = adtv_usd.astype(float).to_numpy()
    with np.errstate(invalid="ignore"):
        conds = [a >= x for x in b]  # NaN >= x é False -> faixa menos líquida
    out = np.select(conds, labels[:-1], default=labels[-1])
    return pd.Series(out, index=adtv_usd.index, name="liquidity_tier", dtype=object)


def days_to_liquidate(notional_usd: pd.Series, adtv_usd: pd.Series,
                      participation: float) -> pd.Series:
    """Dias para liquidar: ``|nocional| / (participação × ADTV)``.

    ``adtv_usd`` é alinhado ao índice de ``notional_usd``. ADTV ausente/zero/negativo ⇒ ``inf``
    (posição não liquidável com a informação disponível); nocional zero ⇒ 0 dias; nocional
    ``NaN`` ⇒ ``NaN``.
    """
    p = _check_participation(participation)
    notional = notional_usd.astype(float).abs()
    adtv = usable_adtv(adtv_usd.reindex(notional.index))
    days = notional / (p * adtv)
    days = days.where(adtv.notna(), np.inf)
    days = days.where(notional != 0.0, 0.0)
    days = days.where(notional.notna(), np.nan)
    return days.rename("days_to_liquidate")


def max_weight_by_liquidity(adtv_usd: pd.Series, nav: float, participation: float,
                            days: float) -> pd.Series:
    """Peso absoluto máximo (fração do NAV) liquidável em ``days`` dias.

    ``participação × ADTV × dias / NAV``. ADTV ausente ou inválido ⇒ teto 0, que significa
    **não negociável** (restrição conservadora, não um dado preenchido com zero).
    """
    p = _check_participation(participation)
    nav_v = _check_positive(nav, "NAV")
    d = _check_positive(days, "Dias de liquidação")
    cap = p * usable_adtv(adtv_usd) * d / nav_v
    return cap.fillna(0.0).rename("max_weight_liquidity")


def liquidity_profile(weights: pd.Series, adtv_usd: pd.Series, nav: float, participation: float,
                      horizons: Sequence[float] = DEFAULT_HORIZONS) -> pd.DataFrame:
    """Perfil de liquidez da carteira por nome e por horizonte.

    Retorna um DataFrame indexado pelos nomes com peso não nulo (ordem de ``weights``) e colunas:

    - ``weight``, ``side`` (``LONG``/``SHORT``), ``notional_usd`` (com sinal), ``adtv_usd``,
      ``adtv_missing`` (bool), ``days_to_liquidate``;
    - ``pct_gross_<h>d`` para cada horizonte ``h``: contribuição do nome para a fração do
      **gross** liquidável em até ``h`` dias, ``min(|w|, h × p × ADTV / NAV) / Σ|w|`` (cada nome
      limitado ao próprio tamanho).

    A soma de cada coluna ``pct_gross_<h>d`` é a fração do gross liquidável em ``h`` dias
    (ver :func:`liquidity_summary`). Nomes sem ADTV utilizável contribuem 0 (nada liquidável)
    e têm ``days_to_liquidate = inf``. Pesos ``NaN`` são erro (não são tratados como zero).
    """
    p = _check_participation(participation)
    nav_v = _check_positive(nav, "NAV")
    hs = _check_horizons(horizons)
    w = weights.astype(float)
    if w.isna().any():
        bad = list(w.index[w.isna()])
        raise ValueError(f"Pesos ausentes (NaN) no perfil de liquidez: {bad}")
    if not np.isfinite(w).all():
        raise ValueError("Pesos não finitos no perfil de liquidez.")
    w = w[w != 0.0]
    cols = ["weight", "side", "notional_usd", "adtv_usd", "adtv_missing", "days_to_liquidate",
            *[horizon_column(h) for h in hs]]
    if w.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name=weights.index.name))

    gross = float(w.abs().sum())
    adtv = usable_adtv(adtv_usd.reindex(w.index))
    notional = w * nav_v
    daily_capacity_w = p * adtv / nav_v  # fração do NAV liquidável por dia (NaN se desconhecido)

    out = pd.DataFrame({
        "weight": w,
        "side": np.where(w > 0, SIDE_LONG, SIDE_SHORT),
        "notional_usd": notional,
        "adtv_usd": adtv,
        "adtv_missing": adtv.isna(),
        "days_to_liquidate": days_to_liquidate(notional, adtv, p),
    }, index=w.index)
    abs_w = w.abs()
    for h in hs:
        liquidable = np.minimum(abs_w, daily_capacity_w * h).where(adtv.notna(), 0.0)
        out[horizon_column(h)] = liquidable / gross
    return out[cols]


def liquidity_summary(profile: pd.DataFrame) -> pd.DataFrame:
    """Resumo do perfil: fração do book liquidável por horizonte.

    Índice ``horizon_days`` (float) e colunas ``gross``, ``long`` e ``short`` (fração de cada
    book liquidável em até ``h`` dias). Um lado sem posições fica ``NaN`` (não há book).
    """
    hcols = [c for c in profile.columns if c.startswith("pct_gross_") and c.endswith("d")]
    horizons = [float(c[len("pct_gross_"):-1]) for c in hcols]
    index = pd.Index(horizons, name="horizon_days", dtype=float)
    if profile.empty:
        return pd.DataFrame(np.nan, index=index, columns=["gross", "long", "short"])
    abs_w = profile["weight"].astype(float).abs()
    gross = float(abs_w.sum())
    is_long = profile["weight"] > 0
    rows = {}
    for h, c in zip(horizons, hcols, strict=True):
        liq_w = profile[c].astype(float) * gross  # volta para fração do NAV
        long_book = float(abs_w[is_long].sum())
        short_book = float(abs_w[~is_long].sum())
        rows[h] = {
            "gross": float(profile[c].sum()),
            "long": float(liq_w[is_long].sum()) / long_book if long_book > 0 else np.nan,
            "short": float(liq_w[~is_long].sum()) / short_book if short_book > 0 else np.nan,
        }
    return pd.DataFrame.from_dict(rows, orient="index").reindex(index)[["gross", "long", "short"]]
