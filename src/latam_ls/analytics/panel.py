"""Painel por emissor em USD: retornos totais, preços, valor negociado e elegibilidade.

Regras de dados:
- Retornos são calculados nas datas válidas de cada linha (sem preencher preços ausentes);
  em datas sem negociação o retorno fica ``NaN`` — nunca zero.
- O câmbio (USD por unidade local) pode ser propagado por no máximo ``FX_FFILL_LIMIT`` dias
  úteis para cobrir feriados cambiais; a política é registrada em ``data_policy``.
- O retorno de um emissor vem da sua linha primária; a liquidez agrega todas as linhas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from ..config import FundConfig
from ..market import MarketData

FX_FFILL_LIMIT = 3
STALE_DAYS_MAX = 5
EXTREME_DAILY_MOVE = 0.5


@dataclass(frozen=True)
class AssetPanel:
    as_of: date
    assets: pd.DataFrame            # índice issuer_id
    returns: pd.DataFrame           # data x issuer_id, retorno total diário em USD (linha primária)
    price_usd: pd.DataFrame         # data x issuer_id, fechamento (sem ajuste) em USD
    traded_value_usd: pd.DataFrame  # data x issuer_id, soma de todas as linhas
    line_returns: pd.DataFrame      # data x ticker, retorno total diário em USD
    lines: pd.DataFrame             # índice ticker
    data_policy: dict = field(default_factory=dict)

    @property
    def eligible(self) -> list[str]:
        return list(self.assets.index[self.assets["eligible"]])


def fx_for_lines(md: MarketData) -> pd.DataFrame:
    """USD por unidade local, alinhado ao calendário de preços (ffill limitado)."""
    idx = md.close.index.union(md.fx.index)
    fx = md.fx.reindex(idx).sort_index().ffill(limit=FX_FFILL_LIMIT)
    if "USD" not in fx.columns:
        fx["USD"] = 1.0
    fx["USD"] = 1.0
    return fx.reindex(md.close.index)


def _line_usd_returns(adj: pd.Series, fx: pd.Series) -> pd.Series:
    s = adj.dropna()
    s = s[s > 0]
    if s.empty:
        return pd.Series(dtype=float)
    usd = s * fx.reindex(s.index)
    usd = usd.dropna()
    return usd.pct_change(fill_method=None).iloc[1:]


def build_asset_panel(md: MarketData, cfg: FundConfig, as_of: date | None = None) -> AssetPanel:
    as_of = as_of or md.as_of
    if as_of != md.as_of:
        md = md.truncate(as_of)
    uni = md.universe
    lines = uni.lines.copy()
    fx = fx_for_lines(md)
    calendar = md.close.index

    line_ret = {}
    line_px_usd = {}
    line_tv_usd = {}
    for tkr, row in lines.iterrows():
        if tkr not in md.adj_close.columns:
            continue
        ccy = row["currency"]
        if ccy not in fx.columns:
            continue
        f = fx[ccy]
        line_ret[tkr] = _line_usd_returns(md.adj_close[tkr], f)
        line_px_usd[tkr] = md.close[tkr] * f
        vol = md.volume[tkr] if tkr in md.volume.columns else pd.Series(np.nan, index=calendar)
        line_tv_usd[tkr] = md.close[tkr] * vol * f

    line_returns = pd.DataFrame(line_ret).reindex(calendar)
    px_usd = pd.DataFrame(line_px_usd).reindex(calendar)
    tv_usd = pd.DataFrame(line_tv_usd).reindex(calendar)

    win = cfg.liquidity.adv_window_days
    tail_tv = tv_usd.tail(win)
    lines["adtv_usd"] = tail_tv.mean(skipna=True).reindex(lines.index)
    lines["adtv_median_usd"] = tail_tv.median(skipna=True).reindex(lines.index)
    last_valid = md.close.apply(lambda s: s.last_valid_index()).reindex(lines.index)
    lines["last_date"] = last_valid
    lines["last_price_local"] = [
        md.close[t].loc[d] if (t in md.close.columns and pd.notna(d)) else np.nan
        for t, d in zip(lines.index, last_valid, strict=False)
    ]
    last_fx = fx.ffill().iloc[-1] if len(fx) else pd.Series(dtype=float)
    lines["last_price_usd"] = lines["last_price_local"] * lines["currency"].map(last_fx)
    lines["has_data"] = lines.index.isin(line_returns.columns) & lines["last_date"].notna()

    issuers = uni.issuers
    asset_ids = list(issuers.index)
    prim = issuers["primary_ticker"]
    returns = pd.DataFrame({i: line_returns[prim[i]] if prim[i] in line_returns else np.nan
                            for i in asset_ids}, index=calendar)
    price_usd = pd.DataFrame({i: px_usd[prim[i]] if prim[i] in px_usd else np.nan
                              for i in asset_ids}, index=calendar)
    tv_issuer = pd.DataFrame({
        i: tv_usd[[t for t in uni.lines_for(i).index if t in tv_usd.columns]].sum(axis=1, min_count=1)
        for i in asset_ids
    }, index=calendar)

    # Market cap em USD: linha primária, senão qualquer linha com dado.
    fund = md.fundamentals
    mcap_usd = {}
    float_mcap_usd = {}
    for i in asset_ids:
        val = np.nan
        fval = np.nan
        for t in [prim[i]] + [x for x in uni.lines_for(i).index if x != prim[i]]:
            if t in fund.index and pd.notna(fund.loc[t].get("market_cap", np.nan)):
                ccy = fund.loc[t].get("currency") or lines.loc[t, "currency"]
                rate = last_fx.get(ccy, np.nan)
                val = float(fund.loc[t, "market_cap"]) * rate
                so = fund.loc[t].get("shares_outstanding", np.nan)
                fl = fund.loc[t].get("float_shares", np.nan)
                if pd.notna(so) and pd.notna(fl) and so > 0:
                    fval = val * min(1.0, float(fl) / float(so))
                break
        mcap_usd[i] = val
        float_mcap_usd[i] = fval

    hist = returns.tail(cfg.risk_model.history_days)
    n_obs = hist.notna().sum()
    assets = pd.DataFrame({
        "issuer_name": issuers["issuer_name"],
        "country": issuers["country"],
        "sector": issuers["gics_sector"],
        "primary_ticker": prim,
        "primary_currency": issuers["primary_currency"],
        "market_cap_usd": pd.Series(mcap_usd),
        "free_float_mcap_usd": pd.Series(float_mcap_usd),
        "adtv_usd": tv_issuer.tail(win).mean(skipna=True),
        "adtv_primary_usd": prim.map(lines["adtv_usd"]),
        "price_usd_last": prim.map(lines["last_price_usd"]),
        "last_date": prim.map(lines["last_date"]),
        "n_obs": n_obs,
    })
    extreme = (returns.abs() > EXTREME_DAILY_MOVE).sum()
    assets["n_extreme_moves"] = extreme

    ts_asof = pd.Timestamp(as_of)
    reasons = []
    for i, row in assets.iterrows():
        r = []
        if pd.isna(row["last_date"]):
            r.append("sem_dados")
        elif (ts_asof - pd.Timestamp(row["last_date"])).days > STALE_DAYS_MAX:
            r.append("preco_defasado")
        if not (row["adtv_usd"] >= cfg.liquidity.min_adtv_usd):
            r.append("adtv_baixo")
        if row["n_obs"] < cfg.risk_model.min_obs_days:
            r.append("historico_curto")
        reasons.append(";".join(r))
    assets["exclusion_reason"] = reasons
    assets["eligible"] = assets["exclusion_reason"] == ""

    return AssetPanel(
        as_of=as_of, assets=assets, returns=returns, price_usd=price_usd,
        traded_value_usd=tv_issuer, line_returns=line_returns, lines=lines,
        data_policy={
            "fx_ffill_limit_days": FX_FFILL_LIMIT,
            "stale_days_max": STALE_DAYS_MAX,
            "missing_prices": "NaN (sem preenchimento)",
            "issuer_returns": "linha primária, retorno total em USD",
            "liquidity": f"média de {win} pregões do valor negociado em USD somando todas as linhas",
        },
    )
