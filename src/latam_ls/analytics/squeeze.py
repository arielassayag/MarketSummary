"""Escore de risco de short squeeze por emissor (0–100) e faixa LOW / MEDIUM / HIGH / NA.

Insumos (por emissor, agregando todas as suas linhas):

- ``si_pct_float``: proxy de short interest = máximo entre ``short_interest.short_pct_float``
  (linhas US) e ``lending.lending_pct_shares`` (linhas B3; posição doada no BTC em % das ações).
- ``days_to_cover``: ``short_ratio_days`` (linhas US; se ausente, ``shares_short`` / volume médio)
  e, nas linhas B3, ``lent_shares`` / volume médio de ações da linha na janela
  ``liquidity.adv_window_days`` (somente datas <= ``panel.as_of``). Máximo entre as linhas.
  Ações vendidas > 0 com volume médio zero ⇒ ``inf`` (risco máximo, sinalizado).
- ``borrow_fee``: maior taxa de aluguel (observada ou estimada) entre as linhas do emissor,
  vinda de :func:`latam_ls.analytics.shortability.short_availability`.
- ``ret_1m``/``ret_3m``/``vol_1m``: retornos totais em USD do emissor (``panel.returns``) nas
  últimas 21/63 sessões até ``panel.as_of``; exige ao menos 60% de observações na janela.
- ``free_float_mcap_usd`` (painel) e ``days_to_earnings`` (próximo resultado em qualquer linha;
  datas passadas são descartadas como defasadas).

Componentes (0–100, ``NaN`` se o insumo falta — nunca zero):

- si, dtc, fee, mom (``ret_1m``): linear por partes — 0 em 0, 40 no limiar ``medium`` da
  configuração, 70 no ``high``, 100 em 2× ``high`` (limitado a 100; valores negativos ⇒ 0).
- float: 100 se free float <= 25% de ``free_float_mcap_low_usd``, 40 no limiar e 0 a partir de
  10× o limiar (interpolação em log).
- catalyst: 100 com resultado em até 7 dias, 50 em até 14, senão 0.

Composto = média ponderada dos componentes disponíveis (si 0,30; dtc 0,25; fee 0,15; mom 0,15;
float 0,10; catalyst 0,05; pesos renormalizados) **e** regra do máximo: se qualquer componente
si/dtc/fee/mom for >= 70, o composto é no mínimo ``squeeze.score_high`` (um sinal vermelho basta).

Faixa: ``HIGH`` se composto >= ``score_high``; ``MEDIUM`` se >= ``score_medium``; senão ``LOW``.
Se **si e dtc** faltam ao mesmo tempo e o composto não é ``HIGH``, a faixa é ``NA`` — dado
insuficiente para afirmar risco baixo. Consumidores devem tratar ``NA`` como ``MEDIUM``
(ver :func:`effective_bucket` e :func:`short_cap_multiplier`).

Short interest, aluguel, fundamentos e datas de resultado são retratos atuais do snapshot (não
point-in-time). Quando ``panel.as_of`` é anterior ao snapshot, ou a data do dado é posterior a
``panel.as_of``, a linha recebe o alerta ``nao_pit`` e ``point_in_time = False``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd

from ..config import FundConfig
from ..market import MarketData
from ..risk.types import TRADING_DAYS
from .panel import AssetPanel
from .shortability import ESTIMATED_FEE_SOURCES, numeric_field

COMPONENT_WEIGHTS: Mapping[str, float] = {
    "si": 0.30, "dtc": 0.25, "fee": 0.15, "mom": 0.15, "float": 0.10, "catalyst": 0.05,
}
RED_FLAG_COMPONENTS = ("si", "dtc", "fee", "mom")
RED_FLAG_COMPONENT_SCORE = 70.0
"""Componente >= 70 (nível ``high`` do insumo) eleva o composto a pelo menos ``score_high``."""

WINDOW_1M = 21
WINDOW_3M = 63
MIN_OBS_FRACTION = 0.6
CATALYST_NEAR_DAYS = 7
CATALYST_MID_DAYS = 14
FLOAT_FULL_RISK_FRACTION = 0.25
FLOAT_NO_RISK_MULTIPLE = 10.0
SI_STALE_DAYS = 45
"""Short interest mais antigo que isso (vs. ``as_of``) recebe o alerta ``si_defasado``."""

BUCKET_LOW, BUCKET_MEDIUM, BUCKET_HIGH, BUCKET_NA = "LOW", "MEDIUM", "HIGH", "NA"

SQUEEZE_COLUMNS = [
    "si_pct_float", "days_to_cover", "borrow_fee", "lending_pct_shares", "ret_1m", "ret_3m",
    "vol_1m", "free_float_mcap_usd", "days_to_earnings",
    "score_si", "score_dtc", "score_fee", "score_mom", "score_float", "score_catalyst",
    "squeeze_score", "bucket", "components_available", "point_in_time", "data_quality",
]


# ----------------------------------------------------------------------------------------
# Mapeamentos de componentes (funções puras)
# ----------------------------------------------------------------------------------------

def threshold_score(values: pd.Series, medium: float, high: float) -> pd.Series:
    """Linear por partes: 0 em 0, 40 em ``medium``, 70 em ``high``, 100 em ``2·high``.

    Valores <= 0 ⇒ 0; acima de ``2·high`` ⇒ 100; ``inf`` ⇒ 100; ``NaN`` ⇒ ``NaN``.
    """
    if not (0.0 < medium < high):
        raise ValueError(f"Limiares inválidos: medium={medium!r}, high={high!r}.")
    x = values.astype(float)
    scored = np.interp(x.to_numpy(), [0.0, medium, high, 2.0 * high], [0.0, 40.0, 70.0, 100.0])
    return pd.Series(scored, index=values.index, dtype=float).where(x.notna())


def float_score(free_float_mcap_usd: pd.Series, low_threshold_usd: float) -> pd.Series:
    """Escore de free float pequeno (interpolação em log do valor em USD).

    100 se <= 25% do limiar, 40 no limiar, 0 a partir de 10× o limiar. Valor ausente ou não
    positivo ⇒ ``NaN``.
    """
    if not (np.isfinite(low_threshold_usd) and low_threshold_usd > 0):
        raise ValueError(f"Limiar de free float inválido: {low_threshold_usd!r}.")
    x = free_float_mcap_usd.astype(float)
    valid = x.notna() & (x > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        logx = np.log(x.where(valid).to_numpy())
    xp = np.log([FLOAT_FULL_RISK_FRACTION * low_threshold_usd, low_threshold_usd,
                 FLOAT_NO_RISK_MULTIPLE * low_threshold_usd])
    scored = np.interp(logx, xp, [100.0, 40.0, 0.0])
    return pd.Series(scored, index=x.index, dtype=float).where(valid)


def catalyst_score(days_to_earnings: pd.Series) -> pd.Series:
    """100 se resultado em até 7 dias, 50 em até 14, 0 depois; ``NaN`` sem data."""
    d = days_to_earnings.astype(float)
    with np.errstate(invalid="ignore"):
        scored = np.select([d <= CATALYST_NEAR_DAYS, d <= CATALYST_MID_DAYS], [100.0, 50.0],
                           default=0.0)
    return pd.Series(scored, index=d.index, dtype=float).where(d.notna())


def composite_squeeze_score(components: pd.DataFrame, score_high: float) -> pd.Series:
    """Composto 0–100 a partir das colunas ``score_<componente>``.

    Média ponderada renormalizada sobre os componentes disponíveis e regra do máximo
    (componente si/dtc/fee/mom >= 70 ⇒ composto >= ``score_high``). Sem componentes ⇒ ``NaN``.
    """
    cols = [f"score_{k}" for k in COMPONENT_WEIGHTS]
    comp = components.reindex(columns=cols).astype(float)
    w = pd.Series([COMPONENT_WEIGHTS[k] for k in COMPONENT_WEIGHTS], index=cols)
    num = comp.mul(w, axis=1).sum(axis=1, min_count=1)
    den = comp.notna().mul(w, axis=1).sum(axis=1)
    score = (num / den.where(den > 0)).clip(0.0, 100.0)
    red_cols = [f"score_{k}" for k in RED_FLAG_COMPONENTS]
    red_flag = comp[red_cols].ge(RED_FLAG_COMPONENT_SCORE).any(axis=1)
    return score.where(~red_flag, score.clip(lower=score_high))


def squeeze_bucket(score: pd.Series, si_missing: pd.Series, dtc_missing: pd.Series,
                   score_medium: float, score_high: float) -> pd.Series:
    """Faixa ``LOW``/``MEDIUM``/``HIGH``/``NA`` a partir do composto.

    ``NA`` quando o composto é ``NaN`` ou quando si e dtc faltam ao mesmo tempo (exceto se o
    composto já é ``HIGH`` por outro sinal vermelho).
    """
    s = score.astype(float)
    with np.errstate(invalid="ignore"):
        bucket = np.select([s >= score_high, s >= score_medium, s.notna()],
                           [BUCKET_HIGH, BUCKET_MEDIUM, BUCKET_LOW], default=BUCKET_NA)
    out = pd.Series(bucket, index=s.index, dtype=object)
    si_na = si_missing.reindex(s.index).astype(bool)
    insufficient = si_na & dtc_missing.reindex(s.index).astype(bool)
    return out.where(~(insufficient & (out != BUCKET_HIGH)), BUCKET_NA)


def effective_bucket(bucket: pd.Series) -> pd.Series:
    """Faixa usada nas restrições: ``NA`` (dado insuficiente) é tratado como ``MEDIUM``."""
    return bucket.where(bucket != BUCKET_NA, BUCKET_MEDIUM).astype(object)


def short_cap_multiplier(squeeze: pd.DataFrame, cfg: FundConfig) -> pd.Series:
    """Multiplicador do teto de short por emissor.

    HIGH ⇒ 0 (short proibido); MEDIUM ou NA ⇒ ``squeeze.medium_short_cap_multiplier``; LOW ⇒ 1.
    """
    eff = effective_bucket(squeeze["bucket"])
    mult = np.select([eff == BUCKET_HIGH, eff == BUCKET_MEDIUM],
                     [0.0, cfg.squeeze.medium_short_cap_multiplier], default=1.0)
    return pd.Series(mult, index=squeeze.index, dtype=float, name="short_cap_multiplier")


# ----------------------------------------------------------------------------------------
# Insumos
# ----------------------------------------------------------------------------------------

def _upto(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    return df.loc[df.index <= as_of]


def _min_obs(window: int) -> int:
    return int(math.ceil(MIN_OBS_FRACTION * window))


def window_return(returns: pd.DataFrame, as_of: pd.Timestamp, window: int) -> pd.Series:
    """Retorno composto das últimas ``window`` sessões até ``as_of`` (``NaN`` se poucas obs.)."""
    r = _upto(returns, as_of).tail(window)
    enough = r.notna().sum() >= _min_obs(window)
    return ((1.0 + r).prod(min_count=1) - 1.0).where(enough)


def window_vol(returns: pd.DataFrame, as_of: pd.Timestamp, window: int) -> pd.Series:
    """Vol anualizada (desvio-padrão amostral × √252) das últimas ``window`` sessões."""
    r = _upto(returns, as_of).tail(window)
    enough = r.notna().sum() >= _min_obs(window)
    return (r.std(ddof=1) * math.sqrt(TRADING_DAYS)).where(enough)


def average_share_volume(volume: pd.DataFrame, tickers: pd.Index, as_of: pd.Timestamp,
                         window: int) -> pd.Series:
    """Volume médio de ações por linha nas últimas ``window`` sessões até ``as_of``."""
    v = _upto(volume, as_of).tail(window).reindex(columns=tickers)
    enough = v.notna().sum() >= _min_obs(window)
    return v.mean(skipna=True).where(enough).astype(float)


def days_to_cover_from_shares(shares: pd.Series, avg_volume: pd.Series) -> pd.Series:
    """Dias para cobrir = ações vendidas / volume médio diário de ações.

    Zero vendido ⇒ 0; volume médio zero com vendido > 0 ⇒ ``inf``; insumo ausente ⇒ ``NaN``.
    """
    sh = shares.astype(float)
    vol = avg_volume.reindex(sh.index).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        dtc = pd.Series(sh.to_numpy() / vol.to_numpy(), index=sh.index, dtype=float)
    dtc = dtc.where(~((vol == 0) & (sh > 0)), np.inf)
    return dtc.where(sh != 0, 0.0).where(sh.notna())


def _parse_dates(table: pd.DataFrame, column: str, index: pd.Index) -> pd.Series:
    if table is None or table.empty or column not in table.columns:
        return pd.Series(pd.NaT, index=index, dtype="datetime64[ns]")
    s = table[column]
    s = s[~s.index.duplicated(keep="first")].reindex(index)
    parsed = pd.to_datetime(s, errors="coerce", utc=True)
    return parsed.dt.tz_convert(None).dt.normalize()


def _first_by_issuer(values: pd.Series, issuer: pd.Series, ascending: bool) -> pd.DataFrame:
    """Linha com o maior (ou menor) valor por emissor, ignorando ``NaN``."""
    df = pd.DataFrame({"issuer_id": issuer, "value": values.astype(float)}).rename_axis(None)
    df = df[df["value"].notna()]
    df["ticker"] = df.index.astype(str)
    df = df.sort_values(["issuer_id", "value", "ticker"], ascending=[True, ascending, True])
    return df.groupby("issuer_id", sort=False).head(1).set_index("issuer_id")


def _line_inputs(panel: AssetPanel, md: MarketData, availability: pd.DataFrame,
                 cfg: FundConfig) -> pd.DataFrame:
    """Insumos de squeeze por linha (índice = ticker)."""
    lines = panel.lines
    idx = lines.index
    as_of = pd.Timestamp(panel.as_of)
    si_us = numeric_field(md.short_interest, "short_pct_float", idx)
    ratio_days = numeric_field(md.short_interest, "short_ratio_days", idx)
    shares_short = numeric_field(md.short_interest, "shares_short", idx)
    lend_pct = numeric_field(md.lending, "lending_pct_shares", idx)
    lent_shares = numeric_field(md.lending, "lent_shares", idx)
    avg_vol = average_share_volume(md.volume, idx, as_of, cfg.liquidity.adv_window_days)
    dtc_us_implied = days_to_cover_from_shares(shares_short, avg_vol)
    dtc_us = ratio_days.where(ratio_days.notna(), dtc_us_implied)
    dtc_br = days_to_cover_from_shares(lent_shares, avg_vol)
    avail = availability.reindex(idx)
    return pd.DataFrame({
        "issuer_id": lines["issuer_id"].astype(str),
        "si_us": si_us,
        "lend_pct": lend_pct,
        "si_line": pd.concat([si_us, lend_pct], axis=1).max(axis=1, skipna=True),
        "dtc_us": dtc_us,
        "dtc_us_implied": ratio_days.isna() & dtc_us_implied.notna(),
        "dtc_br": dtc_br,
        "dtc_line": pd.concat([dtc_us, dtc_br], axis=1).max(axis=1, skipna=True),
        "dtc_infinite": np.isinf(dtc_us) | np.isinf(dtc_br),
        "fee": avail["borrow_fee_annual"].astype(float),
        "fee_source": avail["fee_source"].astype(object),
        "si_date": _parse_dates(md.short_interest, "short_interest_date", idx),
        "lend_date": _parse_dates(md.lending, "lending_date", idx),
        "earnings_date": _parse_dates(md.fundamentals, "next_earnings_date", idx),
    }, index=idx)


def _issuer_days_to_earnings(lf: pd.DataFrame, as_of: pd.Timestamp,
                             ids: pd.Index) -> tuple[pd.Series, pd.Series]:
    """Dias até o próximo resultado (mínimo entre linhas, só datas >= as_of) e flag de defasagem."""
    days = (lf["earnings_date"] - as_of).dt.days.astype(float)
    future = days.where(days >= 0)
    nxt = future.groupby(lf["issuer_id"]).min().reindex(ids)
    had_past = days.lt(0).groupby(lf["issuer_id"]).any().reindex(ids).fillna(False).astype(bool)
    return nxt.astype(float), had_past & nxt.isna()


def _data_quality(ids: pd.Index, lf: pd.DataFrame, table: pd.DataFrame, fee_pick: pd.DataFrame,
                  stale_earnings: pd.Series, as_of: pd.Timestamp, snapshot_as_of: pd.Timestamp,
                  ) -> tuple[pd.Series, pd.Series]:
    """Texto de qualidade de dados por emissor e flag ``point_in_time``."""
    g = lf.groupby("issuer_id")

    def any_by(col: pd.Series) -> pd.Series:
        return col.groupby(lf["issuer_id"]).any().reindex(ids).fillna(False).astype(bool)

    has_si_us = any_by(lf["si_us"].notna())
    has_lend = any_by(lf["lend_pct"].notna())
    has_dtc_us = any_by(lf["dtc_us"].notna() & ~lf["dtc_us_implied"])
    has_dtc_impl = any_by(lf["dtc_us"].notna() & lf["dtc_us_implied"])
    has_dtc_br = any_by(lf["dtc_br"].notna())
    dtc_inf = any_by(lf["dtc_infinite"])
    si_age = (as_of - g["si_date"].max().reindex(ids)).dt.days
    si_stale = si_age.gt(SI_STALE_DAYS).fillna(False)
    future_dated = any_by(lf["si_date"].gt(as_of) | lf["lend_date"].gt(as_of))
    snapshot_later = bool(snapshot_as_of > as_of)
    pit = ~(future_dated | snapshot_later)

    texts = []
    for i in ids:
        si_src = "+".join(s for s, ok in (("SI_US", has_si_us[i]), ("BTC_B3", has_lend[i])) if ok)
        dtc_src = "+".join(s for s, ok in (("SI_US", has_dtc_us[i]),
                                           ("SI_US_implicito", has_dtc_impl[i]),
                                           ("BTC_B3", has_dtc_br[i])) if ok)
        if i in fee_pick.index:
            src = str(fee_pick.loc[i, "fee_source"])
            fee_src = f"{src}(estimada)" if src in ESTIMATED_FEE_SOURCES else src
        else:
            fee_src = "ausente"
        row = table.loc[i]
        missing = [k for k in COMPONENT_WEIGHTS if pd.isna(row[f"score_{k}"])]
        alerts = []
        if not pit[i]:
            alerts.append("nao_pit")
        if si_stale[i]:
            alerts.append("si_defasado")
        if dtc_inf[i]:
            alerts.append("dtc_infinito_sem_volume")
        if stale_earnings[i]:
            alerts.append("data_resultado_defasada")
        if row["bucket"] == BUCKET_NA:
            alerts.append("faixa_NA_tratar_como_MEDIUM")
        parts = [f"si={si_src or 'ausente'}", f"dtc={dtc_src or 'ausente'}", f"fee={fee_src}",
                 f"ausentes={','.join(missing) if missing else 'nenhum'}"]
        if alerts:
            parts.append(f"alertas={','.join(alerts)}")
        texts.append("; ".join(parts))
    return pd.Series(texts, index=ids, dtype=object), pit.astype(bool)


# ----------------------------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------------------------

def squeeze_table(panel: AssetPanel, md: MarketData, availability: pd.DataFrame,
                  cfg: FundConfig) -> pd.DataFrame:
    """Tabela de risco de short squeeze por emissor (índice ``issuer_id``, todos do painel).

    Colunas: ``si_pct_float``, ``days_to_cover``, ``borrow_fee``, ``lending_pct_shares``,
    ``ret_1m``, ``ret_3m``, ``vol_1m`` (anualizada), ``free_float_mcap_usd``,
    ``days_to_earnings``, ``score_si``, ``score_dtc``, ``score_fee``, ``score_mom``,
    ``score_float``, ``score_catalyst``, ``squeeze_score`` (0–100), ``bucket``
    (``LOW``/``MEDIUM``/``HIGH``/``NA``; ``NA`` deve ser tratado como ``MEDIUM``),
    ``components_available`` (int), ``point_in_time`` (bool) e ``data_quality`` (fontes,
    componentes ausentes e alertas).
    """
    sq = cfg.squeeze
    ids = panel.assets.index
    as_of = pd.Timestamp(panel.as_of)
    lf = _line_inputs(panel, md, availability, cfg)
    by_issuer = lf.groupby("issuer_id")

    fee_pick = _first_by_issuer(lf["fee"], lf["issuer_id"], ascending=False)
    fee_pick = fee_pick.join(lf[["fee_source"]], on="ticker")
    days_to_earn, stale_earn = _issuer_days_to_earnings(lf, as_of, ids)

    t = pd.DataFrame(index=ids)
    t["si_pct_float"] = by_issuer["si_line"].max().reindex(ids).astype(float)
    t["days_to_cover"] = by_issuer["dtc_line"].max().reindex(ids).astype(float)
    t["borrow_fee"] = fee_pick["value"].reindex(ids).astype(float)
    t["lending_pct_shares"] = by_issuer["lend_pct"].max().reindex(ids).astype(float)
    t["ret_1m"] = window_return(panel.returns, as_of, WINDOW_1M).reindex(ids).astype(float)
    t["ret_3m"] = window_return(panel.returns, as_of, WINDOW_3M).reindex(ids).astype(float)
    t["vol_1m"] = window_vol(panel.returns, as_of, WINDOW_1M).reindex(ids).astype(float)
    t["free_float_mcap_usd"] = panel.assets["free_float_mcap_usd"].reindex(ids).astype(float)
    t["days_to_earnings"] = days_to_earn

    t["score_si"] = threshold_score(t["si_pct_float"], sq.si_pct_float_medium,
                                    sq.si_pct_float_high)
    t["score_dtc"] = threshold_score(t["days_to_cover"], sq.days_to_cover_medium,
                                     sq.days_to_cover_high)
    t["score_fee"] = threshold_score(t["borrow_fee"], sq.borrow_fee_medium, sq.borrow_fee_high)
    t["score_mom"] = threshold_score(t["ret_1m"], sq.ret_1m_medium, sq.ret_1m_high)
    t["score_float"] = float_score(t["free_float_mcap_usd"], sq.free_float_mcap_low_usd)
    t["score_catalyst"] = catalyst_score(t["days_to_earnings"])

    t["squeeze_score"] = composite_squeeze_score(t, sq.score_high)
    t["bucket"] = squeeze_bucket(t["squeeze_score"], t["si_pct_float"].isna(),
                                 t["days_to_cover"].isna(), sq.score_medium, sq.score_high)
    score_cols = [f"score_{k}" for k in COMPONENT_WEIGHTS]
    t["components_available"] = t[score_cols].notna().sum(axis=1).astype(int)
    snapshot_as_of = pd.Timestamp(md.as_of)
    t["data_quality"], t["point_in_time"] = _data_quality(
        ids, lf, t, fee_pick, stale_earn, as_of, snapshot_as_of)
    t.index.name = "issuer_id"
    return t[SQUEEZE_COLUMNS]
