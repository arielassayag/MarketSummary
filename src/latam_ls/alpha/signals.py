"""Sinais de alpha brutos por emissor (maior = mais atrativo).

Cada sinal é uma função pura ``fn(panel, md, model, as_of, issuers) -> pd.Series`` que usa
apenas dados com data ``<= as_of``. Ausências ficam ``NaN`` (nunca zero) e os motivos são
registrados em ``serie.attrs["notes"]``.

| Sinal | Definição | PIT |
|---|---|---|
| ``residual_momentum`` | Σ resíduos t−252…t−21 / desvio dos resíduos (Blitz-Huij-Martens) | Sim |
| ``short_term_reversal`` | −Σ resíduos dos últimos 21 pregões | Sim |
| ``low_risk`` | −vol residual de 126 pregões (anualizada) | Sim |
| ``value`` | E/P, B/P e EBITDA/EV relativos ao setor | Não |
| ``quality`` | ROE, margens operacional e bruta, −dívida/PL relativos ao setor | Não |
| ``analyst_revision`` | upside ao preço-alvo médio e −(recomendação média − 3) | Não |

Resíduos ("retornos específicos"): ``model.specific_returns`` quando há modelo de risco; sem
modelo, resíduos de uma regressão de beta de mercado de 252 pregões contra o retorno da
carteira do universo ponderada por capitalização (o intercepto/alpha permanece no resíduo).

Sinais fundamentalistas usam o retrato atual da fonte (``point_in_time=False``) e não devem
ser usados em backtest histórico sem essa ressalva.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..analytics.panel import STALE_DAYS_MAX, AssetPanel
from ..market import MarketData
from ..risk.types import TRADING_DAYS, RiskModel
from .combine import robust_zscore

SignalFn = Callable[[AssetPanel, MarketData, RiskModel | None, pd.Timestamp, list[str]], pd.Series]

RESIDUAL_WINDOW = 252
"""Pregões da janela de resíduos (estimação do beta e momentum 12m)."""
MOMENTUM_SKIP = 21
"""Pregões mais recentes excluídos do momentum (evita a reversão de curto prazo)."""
REVERSAL_WINDOW = 21
LOW_RISK_WINDOW = 126
MIN_OBS_MOMENTUM = 150
MIN_OBS_REVERSAL = 15
MIN_OBS_LOW_RISK = 90
MIN_OBS_BETA = 60
MIN_ANALYST_OPINIONS = 3
MIN_SECTOR_NAMES = 3
"""Mínimo de nomes com dado no setor para usar a mediana setorial (senão: mediana global)."""
SUBSIGNAL_WINSOR_Z = 3.0
"""Winsorização dos componentes dentro dos compostos fundamentalistas."""
MIN_VALUE_COMPONENTS = 1
MIN_QUALITY_COMPONENTS = 2
MIN_ANALYST_COMPONENTS = 1
UPSIDE_BOUNDS = (-0.9, 3.0)
"""Upside fora desta faixa indica provável descasamento de moeda/unidade (preço-alvo vs. preço)."""
RECOMMENDATION_RANGE = (1.0, 5.0)

VALUE_FIELDS = ["trailing_pe", "trailing_eps", "price_to_book", "enterprise_to_ebitda"]
QUALITY_FIELDS = ["return_on_equity", "operating_margins", "gross_margins", "debt_to_equity"]
ANALYST_FIELDS = ["target_mean_price", "recommendation_mean", "number_of_analyst_opinions"]


@dataclass(frozen=True)
class SignalSpec:
    """Especificação de um sinal: função, marcação point-in-time e descrição para o gestor."""

    name: str
    fn: SignalFn
    point_in_time: bool
    description_pt: str


# ==========================================================
# Utilitários
# ==========================================================

def _with_notes(s: pd.Series, notes: list[str], name: str) -> pd.Series:
    out = s.astype(float).rename(name)
    out.attrs = {"notes": list(notes)}
    return out


def _empty(issuers: list[str], name: str, notes: list[str]) -> pd.Series:
    return _with_notes(pd.Series(np.nan, index=pd.Index(issuers), dtype=float), notes, name)


def _fmt_ids(ids: list[str], limit: int = 8) -> str:
    head = ", ".join(str(i) for i in ids[:limit])
    return head + (f" … (+{len(ids) - limit})" if len(ids) > limit else "")


def _numeric_field(df: pd.DataFrame, col: str, index: pd.Index) -> pd.Series:
    """Coluna numérica reindexada; ausente/não numérico ⇒ ``NaN``; ±inf ⇒ ``NaN``."""
    if col not in df.columns:
        return pd.Series(np.nan, index=index, dtype=float)
    s = pd.to_numeric(df[col].reindex(index), errors="coerce").astype(float)
    return s.where(np.isfinite(s))


def _text_field(df: pd.DataFrame, col: str, index: pd.Index) -> pd.Series:
    if col not in df.columns:
        return pd.Series(pd.NA, index=index, dtype="string")
    s = df[col].reindex(index).astype("string").str.strip().str.upper()
    return s.where(s.notna() & (s != ""))


def _rows_upto(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    return df.loc[df.index <= as_of]


def last_close(md: MarketData, tickers: pd.Series, as_of: pd.Timestamp) -> pd.DataFrame:
    """Último fechamento (moeda da linha) com data ``<= as_of`` para cada ticker.

    ``tickers``: Series (chave → ticker). Retorna DataFrame com ``price`` e ``price_date``
    na mesma chave; ticker ausente ou sem preço ⇒ ``NaN``.
    """
    close = _rows_upto(md.close, as_of)
    valid = tickers.dropna()
    cols = [t for t in pd.unique(valid.to_numpy()) if t in close.columns]
    sub = close[cols]
    last_date = sub.apply(lambda s: s.last_valid_index())
    last_px = sub.ffill().iloc[-1] if len(sub) else pd.Series(np.nan, index=cols, dtype=float)
    price = tickers.map(last_px).astype(float)
    price_date = pd.to_datetime(tickers.map(last_date))
    return pd.DataFrame({"price": price.where(price > 0), "price_date": price_date})


# ==========================================================
# Resíduos (retornos específicos) sem look-ahead
# ==========================================================

def cap_weights_usd(md: MarketData, as_of: pd.Timestamp) -> pd.Series:
    """Capitalização em USD por emissor: ``market_cap`` do retrato × câmbio em ``as_of``.

    Usa a linha primária e, na falta, outra linha do emissor com dado. O câmbio é o último
    disponível ``<= as_of``. A capitalização vem do retrato atual (não PIT): só pondera o
    proxy de mercado, efeito de segunda ordem. Sem dado ⇒ ``NaN`` (emissor fora do proxy).
    """
    lines = md.universe.lines
    fund = md.fundamentals
    mcap = _numeric_field(fund, "market_cap", lines.index)
    ccy = _text_field(fund, "currency", lines.index)
    ccy = ccy.fillna(lines["currency"].astype("string"))
    fx = _rows_upto(md.fx, as_of)
    fx_last = fx.ffill().iloc[-1] if len(fx) else pd.Series(dtype=float)
    fx_last = pd.to_numeric(fx_last, errors="coerce").astype(float)
    fx_last.loc["USD"] = 1.0
    usd = mcap * ccy.map(fx_last).astype(float)
    frame = pd.DataFrame({
        "issuer_id": lines["issuer_id"].astype(str),
        "not_primary": ~lines["primary_line"].astype(bool),
        "ticker": lines.index.astype(str),
        "usd": usd.where(usd > 0),
    }).dropna(subset=["usd"])
    frame = frame.sort_values(["issuer_id", "not_primary", "ticker"])
    return frame.groupby("issuer_id")["usd"].first()


def _cap_weighted_market(returns: pd.DataFrame, weights: pd.Series) -> tuple[pd.Series, list]:
    """Retorno diário da carteira do universo ponderada por cap (sobre os nomes negociados)."""
    notes: list[str] = []
    w = weights.reindex(returns.columns)
    w = w.where(w > 0)
    if w.notna().sum() == 0:
        notes.append("Sem capitalização para nenhum emissor: proxy de mercado equiponderado.")
        w = pd.Series(1.0, index=returns.columns)
    cols = w.dropna().index
    R = returns[cols]
    wc = w[cols]
    num = R.mul(wc, axis=1).sum(axis=1, min_count=1)
    den = R.notna().astype(float).mul(wc, axis=1).sum(axis=1)
    return num / den.where(den > 0), notes


def _market_over_gaps(returns: pd.DataFrame, market: pd.Series) -> pd.DataFrame:
    """Retorno de mercado acumulado entre pregões válidos consecutivos de cada emissor.

    O retorno de um emissor após um feriado local cobre vários dias; o mercado correspondente
    é composto sobre o mesmo intervalo. Dias sem nenhum nome negociado não têm variação
    observada (o movimento entra no retorno do pregão seguinte), por isso não somam ao índice
    acumulado — não é imputação de dado, é a convenção do índice de nível.
    """
    level = np.log1p(market.fillna(0.0)).cumsum().to_numpy()
    lmat = np.where(returns.notna().to_numpy(), level[:, None], np.nan)
    L = pd.DataFrame(lmat, index=returns.index, columns=returns.columns)
    prev = L.ffill().shift(1)
    return np.expm1(L - prev)


def residual_returns(
    panel: AssetPanel,
    md: MarketData,
    model: RiskModel | None,
    as_of: pd.Timestamp,
    window: int = RESIDUAL_WINDOW,
) -> tuple[pd.DataFrame, list[str]]:
    """Retornos específicos diários (data × emissor) nos últimos ``window`` pregões ``<= as_of``.

    Com ``model``: ``model.specific_returns`` cortado em ``as_of``. Sem modelo: resíduo
    ``r_i − β_i r_m`` com ``β_i`` estimado por MQO (com intercepto) em ``window`` pregões
    contra o retorno do universo ponderado por cap; o intercepto permanece no resíduo
    (é o alpha que o momentum residual quer capturar). Mínimo de ``MIN_OBS_BETA`` pares.
    """
    as_of = pd.Timestamp(as_of)
    notes: list[str] = []
    if model is not None:
        S = _rows_upto(model.specific_returns, as_of).astype(float)
        if pd.Timestamp(model.as_of) > as_of:
            notes.append("Modelo de risco estimado após as_of: as exposições podem conter "
                         "informação futura (use um modelo estimado em as_of no backtest).")
        if len(S) and (as_of - S.index[-1]).days > STALE_DAYS_MAX:
            notes.append(f"Resíduos do modelo terminam em {S.index[-1].date()}, defasados "
                         f"em relação a {as_of.date()}.")
        if len(S) < window:
            notes.append(f"Histórico de resíduos do modelo com {len(S)} pregões (< {window}).")
        return S.tail(window), notes

    R_all = _rows_upto(panel.returns, as_of).astype(float)
    if R_all.empty:
        notes.append("Sem retornos até as_of.")
        return R_all, notes
    rm, mnotes = _cap_weighted_market(R_all, cap_weights_usd(md, as_of))
    notes.extend(mnotes)
    M_all = _market_over_gaps(R_all, rm)
    R = R_all.tail(window)
    M = M_all.tail(window)
    if len(R) < window:
        notes.append(f"Histórico de retornos com {len(R)} pregões (< {window}).")
    mask = R.notna() & M.notna()
    X = M.where(mask)
    Y = R.where(mask)
    n = mask.sum()
    xd = X - X.mean()
    yd = Y - Y.mean()
    cov = (xd * yd).sum() / (n - 1)
    var = (xd ** 2).sum() / (n - 1)
    beta = (cov / var).where((n >= MIN_OBS_BETA) & (var > 0))
    short = beta.index[beta.isna()].tolist()
    if short:
        notes.append(f"{len(short)} emissor(es) sem beta estimável (< {MIN_OBS_BETA} pares): "
                     f"{_fmt_ids(short)}.")
    resid = Y - X.mul(beta, axis=1)
    return resid, notes


# ==========================================================
# Sinais de preço (point-in-time)
# ==========================================================

def residual_momentum(panel: AssetPanel, md: MarketData, model: RiskModel | None,
                      as_of: pd.Timestamp, issuers: list[str]) -> pd.Series:
    """Momentum residual 12m−1m padronizado pela própria volatilidade residual."""
    S, notes = residual_returns(panel, md, model, as_of)
    S = S.reindex(columns=issuers)
    mom = S.iloc[:-MOMENTUM_SKIP] if len(S) > MOMENTUM_SKIP else S.iloc[0:0]
    n = mom.notna().sum()
    total = mom.sum(min_count=1)
    sd = mom.std(ddof=1)
    score = (total / sd).where((n >= MIN_OBS_MOMENTUM) & (sd > 0))
    short = score.index[score.isna()].tolist()
    if short:
        notes.append(f"{len(short)} emissor(es) com menos de {MIN_OBS_MOMENTUM} resíduos na "
                     f"janela de momentum: {_fmt_ids(short)}.")
    return _with_notes(score.reindex(issuers), notes, "residual_momentum")


def short_term_reversal(panel: AssetPanel, md: MarketData, model: RiskModel | None,
                        as_of: pd.Timestamp, issuers: list[str]) -> pd.Series:
    """Reversão de curto prazo: −Σ resíduos dos últimos 21 pregões."""
    S, notes = residual_returns(panel, md, model, as_of)
    last = S.reindex(columns=issuers).tail(REVERSAL_WINDOW)
    n = last.notna().sum()
    score = (-last.sum(min_count=1)).where(n >= MIN_OBS_REVERSAL)
    short = score.index[score.isna()].tolist()
    if short:
        notes.append(f"{len(short)} emissor(es) com menos de {MIN_OBS_REVERSAL} resíduos no "
                     f"último mês: {_fmt_ids(short)}.")
    return _with_notes(score.reindex(issuers), notes, "short_term_reversal")


def low_risk(panel: AssetPanel, md: MarketData, model: RiskModel | None,
             as_of: pd.Timestamp, issuers: list[str]) -> pd.Series:
    """Baixo risco: −volatilidade residual anualizada de 126 pregões."""
    S, notes = residual_returns(panel, md, model, as_of)
    last = S.reindex(columns=issuers).tail(LOW_RISK_WINDOW)
    n = last.notna().sum()
    vol = last.std(ddof=1) * np.sqrt(TRADING_DAYS)
    score = (-vol).where(n >= MIN_OBS_LOW_RISK)
    short = score.index[score.isna()].tolist()
    if short:
        notes.append(f"{len(short)} emissor(es) com menos de {MIN_OBS_LOW_RISK} resíduos em "
                     f"{LOW_RISK_WINDOW} pregões: {_fmt_ids(short)}.")
    return _with_notes(score.reindex(issuers), notes, "low_risk")


# ==========================================================
# Fundamentos (retrato atual, não PIT)
# ==========================================================

def _candidate_lines(md: MarketData, issuers: list[str]) -> pd.DataFrame:
    """Linhas com fundamentos, com chaves de preferência (moeda = moeda do balanço, primária)."""
    lines = md.universe.lines
    fund = md.fundamentals
    cand = lines[lines["issuer_id"].isin(issuers) & lines.index.isin(fund.index)]
    idx = cand.index
    quote = _text_field(fund, "currency", idx)
    quote = quote.fillna(cand["currency"].astype("string").str.upper())
    fin = _text_field(fund, "financial_currency", idx)
    issuer_fin = fin.groupby(cand["issuer_id"]).first()  # primeira moeda de balanço não nula
    fin = fin.fillna(cand["issuer_id"].map(issuer_fin).astype("string"))
    match = (quote == fin).fillna(False).astype(bool)
    line_ccy = cand["currency"].astype("string").str.upper()
    return pd.DataFrame({
        "issuer_id": cand["issuer_id"].astype(str),
        "ticker": idx.astype(str),
        "quote_currency": quote,
        "line_currency": line_ccy,
        "financial_currency": fin,
        "currency_match": match,
        "primary": cand["primary_line"].astype(bool),
    }, index=idx)


def select_fundamental_lines(
    md: MarketData, issuers: list[str], fields: list[str], usable: pd.Series | None = None
) -> pd.DataFrame:
    """Escolhe, por emissor, a linha cujos fundamentos serão usados.

    Preferência: (1) moeda de cotação = moeda das demonstrações (evita o descasamento de
    moeda típico de ADRs, ex.: preço em USD e lucro em BRL); (2) linha primária; (3) ticker.
    Só concorrem linhas com ao menos um dos ``fields`` preenchido (e ``usable`` verdadeiro,
    se informado). Retorna DataFrame indexado por ``issuers`` com ``ticker``,
    ``quote_currency``, ``financial_currency`` e ``currency_match`` (``NaN`` sem linha).
    """
    cand = _candidate_lines(md, issuers)
    fund = md.fundamentals
    has = pd.Series(False, index=cand.index)
    for f in fields:
        has |= _numeric_field(fund, f, cand.index).notna()
    if usable is not None:
        has &= usable.reindex(cand.index).fillna(False).astype(bool)
    cand = cand[has]
    cand = cand.assign(no_match=~cand["currency_match"], not_primary=~cand["primary"])
    cand = cand.sort_values(["issuer_id", "no_match", "not_primary", "ticker"])
    best = cand.groupby("issuer_id").head(1).set_index("issuer_id")
    cols = ["ticker", "quote_currency", "line_currency", "financial_currency", "currency_match"]
    return best[cols].reindex(pd.Index(issuers, name="issuer_id"))


def _fields_for(md: MarketData, sel: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    """Valores numéricos dos ``fields`` da linha escolhida de cada emissor."""
    tick = sel["ticker"]
    out = {}
    for f in fields:
        col = _numeric_field(md.fundamentals, f, pd.Index(tick.dropna().unique()))
        out[f] = tick.map(col).astype(float)
    return pd.DataFrame(out, index=sel.index)


def earnings_yield(trailing_pe: pd.Series, trailing_eps: pd.Series, price: pd.Series) -> pd.Series:
    """Lucro/preço: ``1/P/L`` se P/L > 0; senão ``LPA/preço`` (lucro negativo); senão ``NaN``.

    O fallback ``LPA/preço`` só deve receber LPA na mesma moeda do preço (quem chama passa
    ``NaN`` quando as moedas diferem).
    """
    pe = pd.to_numeric(trailing_pe, errors="coerce").astype(float)
    eps = pd.to_numeric(trailing_eps, errors="coerce").astype(float)
    px = pd.to_numeric(price, errors="coerce").astype(float)
    direct = 1.0 / pe.where(pe > 0)
    fallback = (eps / px.where(px > 0)).where(np.isfinite(eps))
    out = direct.where(pe > 0, fallback)
    return out.where(np.isfinite(out))


def _inverse_positive(x: pd.Series) -> pd.Series:
    """``1/x`` para ``x > 0``; múltiplos não positivos (PL ou EBITDA negativos) ⇒ ``NaN``."""
    return 1.0 / x.where(x > 0)


def _sector_relative(x: pd.Series, sector: pd.Series) -> pd.Series:
    """Desvio em relação à mediana do setor (``MIN_SECTOR_NAMES``+ nomes) ou à mediana global."""
    sec = sector.reindex(x.index)
    grp = x.groupby(sec, dropna=True)
    cnt = grp.transform("count")
    med = grp.transform("median")
    center = med.where(cnt >= MIN_SECTOR_NAMES, float(x.median()))
    return x - center


def _composite(
    components: dict[str, pd.Series], sector: pd.Series | None, min_components: int
) -> tuple[pd.Series, pd.DataFrame]:
    """Média dos z-scores robustos dos componentes (relativos ao setor, se ``sector``)."""
    zs = {}
    for name, x in components.items():
        x = x.where(np.isfinite(x))
        rel = _sector_relative(x, sector) if sector is not None else x
        zs[name] = robust_zscore(rel, SUBSIGNAL_WINSOR_Z)
    Z = pd.DataFrame(zs)
    n = Z.notna().sum(axis=1)
    return Z.mean(axis=1).where(n >= min_components), Z


def _sector_of(panel: AssetPanel, md: MarketData, issuers: list[str]) -> pd.Series:
    sec = panel.assets["sector"] if "sector" in panel.assets.columns else pd.Series(dtype=object)
    sec = sec.reindex(issuers)
    if sec.isna().any() and "gics_sector" in md.universe.issuers.columns:
        sec = sec.fillna(md.universe.issuers["gics_sector"].reindex(issuers))
    return sec


def value(panel: AssetPanel, md: MarketData, model: RiskModel | None,
          as_of: pd.Timestamp, issuers: list[str]) -> pd.Series:
    """Valor relativo ao setor: E/P, B/P e EBITDA/EV (mínimo 1 componente)."""
    notes: list[str] = []
    sel = select_fundamental_lines(md, issuers, VALUE_FIELDS)
    if sel["ticker"].isna().all():
        return _empty(issuers, "value", ["Sem fundamentos de valor para nenhum emissor."])
    f = _fields_for(md, sel, VALUE_FIELDS)
    px = last_close(md, sel["ticker"], as_of)["price"]
    same_ccy = sel["currency_match"].fillna(False).astype(bool)
    eps = f["trailing_eps"].where(same_ccy)
    blocked = ~(f["trailing_pe"] > 0) & f["trailing_eps"].notna() & ~same_ccy
    if blocked.any():
        blocked_ids = blocked.index[blocked].tolist()
        notes.append(f"LPA não usado por moeda de cotação ≠ moeda do balanço em "
                     f"{len(blocked_ids)} emissor(es): {_fmt_ids(blocked_ids)}.")
    comps = {
        "earnings_yield": earnings_yield(f["trailing_pe"], eps, px),
        "book_to_price": _inverse_positive(f["price_to_book"]),
        "ebitda_to_ev": _inverse_positive(f["enterprise_to_ebitda"]),
    }
    nonmatch = sel.index[sel["ticker"].notna() & ~same_ccy].tolist()
    if nonmatch:
        notes.append(f"{len(nonmatch)} emissor(es) sem linha na moeda do balanço; usada a linha "
                     f"primária/disponível: {_fmt_ids(nonmatch)}.")
    score, _ = _composite(comps, _sector_of(panel, md, issuers), MIN_VALUE_COMPONENTS)
    missing = score.index[score.isna()].tolist()
    if missing:
        notes.append(f"{len(missing)} emissor(es) sem múltiplos válidos: {_fmt_ids(missing)}.")
    notes.append("Retrato atual de fundamentos (não point-in-time).")
    return _with_notes(score.reindex(issuers), notes, "value")


def quality(panel: AssetPanel, md: MarketData, model: RiskModel | None,
            as_of: pd.Timestamp, issuers: list[str]) -> pd.Series:
    """Qualidade relativa ao setor: ROE, margens operacional e bruta e −dívida/PL."""
    notes: list[str] = []
    sel = select_fundamental_lines(md, issuers, QUALITY_FIELDS)
    if sel["ticker"].isna().all():
        return _empty(issuers, "quality", ["Sem fundamentos de qualidade para nenhum emissor."])
    f = _fields_for(md, sel, QUALITY_FIELDS)
    de = f["debt_to_equity"]
    neg_equity = de < 0
    if neg_equity.any():
        notes.append(f"Dívida/PL negativa (PL negativo) tratada como ausente em "
                     f"{int(neg_equity.sum())} emissor(es): "
                     f"{_fmt_ids(neg_equity.index[neg_equity].tolist())}.")
    comps = {
        "roe": f["return_on_equity"],
        "operating_margin": f["operating_margins"],
        "gross_margin": f["gross_margins"],
        "neg_leverage": -de.where(de >= 0),
    }
    score, _ = _composite(comps, _sector_of(panel, md, issuers), MIN_QUALITY_COMPONENTS)
    missing = score.index[score.isna()].tolist()
    if missing:
        notes.append(f"{len(missing)} emissor(es) com menos de {MIN_QUALITY_COMPONENTS} "
                     f"métricas de qualidade: {_fmt_ids(missing)}.")
    notes.append("Retrato atual de fundamentos (não point-in-time).")
    return _with_notes(score.reindex(issuers), notes, "quality")


def analyst_inputs(md: MarketData, issuers: list[str], as_of: pd.Timestamp) -> pd.DataFrame:
    """Insumos de consenso por emissor, todos da MESMA linha (preço-alvo e preço na mesma moeda).

    Considera apenas linhas com ``number_of_analyst_opinions >= MIN_ANALYST_OPINIONS``.
    Preferência de linha como em :func:`select_fundamental_lines`. ``upside`` é ``NaN``
    quando a moeda dos fundamentos difere da moeda de cotação do preço, quando o preço está
    defasado (> ``STALE_DAYS_MAX`` dias) ou quando cai fora de ``UPSIDE_BOUNDS``.
    Colunas: ``ticker``, ``currency``, ``price``, ``price_date``, ``target_mean_price``,
    ``upside``, ``recommendation_mean``, ``rec_score`` (= 3 − recomendação), ``n_opinions``,
    ``flag``.
    """
    as_of = pd.Timestamp(as_of)
    fund = md.fundamentals
    n_op = _numeric_field(fund, "number_of_analyst_opinions", fund.index)
    usable = (n_op >= MIN_ANALYST_OPINIONS).fillna(False)
    sel = select_fundamental_lines(md, issuers, ["target_mean_price", "recommendation_mean"],
                                   usable=usable)
    f = _fields_for(md, sel, ANALYST_FIELDS)
    px = last_close(md, sel["ticker"], as_of)
    flag = pd.Series("", index=sel.index, dtype=object)
    flag[sel["ticker"].isna()] = "sem_cobertura_minima"
    target = f["target_mean_price"].where(f["target_mean_price"] > 0)
    ccy_ok = (sel["quote_currency"] == sel["line_currency"]).fillna(False).astype(bool)
    flag[sel["ticker"].notna() & ~ccy_ok] = "moeda_inconsistente"
    stale = (as_of - px["price_date"]).dt.days > STALE_DAYS_MAX
    stale = stale.fillna(False).astype(bool) & sel["ticker"].notna()
    flag[stale & (flag == "")] = "preco_defasado"
    upside = (target / px["price"] - 1.0).where(ccy_ok & ~stale)
    lo, hi = UPSIDE_BOUNDS
    out_of_bounds = upside.notna() & ((upside < lo) | (upside > hi))
    flag[out_of_bounds] = "upside_implausivel"
    upside = upside.where(~out_of_bounds)
    rec = f["recommendation_mean"]
    rec = rec.where((rec >= RECOMMENDATION_RANGE[0]) & (rec <= RECOMMENDATION_RANGE[1]))
    return pd.DataFrame({
        "ticker": sel["ticker"],
        "currency": sel["line_currency"],
        "price": px["price"],
        "price_date": px["price_date"],
        "target_mean_price": target,
        "upside": upside,
        "recommendation_mean": rec,
        "rec_score": 3.0 - rec,
        "n_opinions": f["number_of_analyst_opinions"],
        "flag": flag,
    }, index=sel.index)


def analyst_revision(panel: AssetPanel, md: MarketData, model: RiskModel | None,
                     as_of: pd.Timestamp, issuers: list[str]) -> pd.Series:
    """Consenso: upside ao preço-alvo médio e −(recomendação média − 3), ≥ 3 analistas."""
    notes: list[str] = []
    inp = analyst_inputs(md, issuers, as_of)
    for flag, label in [
        ("sem_cobertura_minima", f"menos de {MIN_ANALYST_OPINIONS} analistas"),
        ("moeda_inconsistente", "moeda do preço-alvo ≠ moeda do preço"),
        ("preco_defasado", "preço defasado"),
        ("upside_implausivel", "upside fora da faixa plausível (provável erro de moeda)"),
    ]:
        ids = inp.index[inp["flag"] == flag].tolist()
        if ids:
            notes.append(f"{len(ids)} emissor(es) com {label}: {_fmt_ids(ids)}.")
    comps = {"upside": inp["upside"], "recommendation": inp["rec_score"]}
    score, _ = _composite(comps, None, MIN_ANALYST_COMPONENTS)
    notes.append("Retrato atual do consenso (não point-in-time).")
    return _with_notes(score.reindex(issuers), notes, "analyst_revision")


# ==========================================================
# Registro e cálculo em lote
# ==========================================================

SIGNALS: dict[str, SignalSpec] = {
    "residual_momentum": SignalSpec(
        "residual_momentum", residual_momentum, True,
        "Momentum residual 12m−1m: soma dos retornos específicos de t−252 a t−21 dividida "
        "pela volatilidade residual (Blitz, Huij e Martens).",
    ),
    "short_term_reversal": SignalSpec(
        "short_term_reversal", short_term_reversal, True,
        "Reversão de curto prazo: negativo do retorno específico acumulado no último mês.",
    ),
    "value": SignalSpec(
        "value", value, False,
        "Valor relativo ao setor: lucro/preço, patrimônio/preço e EBITDA/EV, usando a linha "
        "cotada na moeda do balanço.",
    ),
    "quality": SignalSpec(
        "quality", quality, False,
        "Qualidade relativa ao setor: ROE, margem operacional, margem bruta e menor alavancagem.",
    ),
    "low_risk": SignalSpec(
        "low_risk", low_risk, True,
        "Baixo risco: negativo da volatilidade residual dos últimos 6 meses.",
    ),
    "analyst_revision": SignalSpec(
        "analyst_revision", analyst_revision, False,
        "Consenso de analistas: upside ao preço-alvo médio e recomendação média (≥ 3 analistas).",
    ),
}


def compute_signals(
    panel: AssetPanel,
    md: MarketData,
    model: RiskModel | None,
    as_of: pd.Timestamp,
    issuers: list[str],
    names: list[str] | None = None,
    pit_only: bool = False,
) -> pd.DataFrame:
    """Calcula os sinais brutos (emissor × sinal) em ``as_of`` sem look-ahead.

    ``names`` restringe/ordena os sinais (nome desconhecido ⇒ ``KeyError``); ``pit_only``
    mantém apenas sinais point-in-time (uso em backtest). ``attrs`` do resultado traz
    ``as_of``, ``notes`` (motivos de ausência) e ``point_in_time`` por sinal.
    """
    ts = pd.Timestamp(as_of)
    selected = list(names) if names is not None else list(SIGNALS)
    unknown = [n for n in selected if n not in SIGNALS]
    if unknown:
        raise KeyError(f"Sinais desconhecidos: {unknown}. Disponíveis: {list(SIGNALS)}")
    if pit_only:
        selected = [n for n in selected if SIGNALS[n].point_in_time]
    ids = list(dict.fromkeys(str(i) for i in issuers))
    notes: list[str] = []
    if ts.date() > panel.as_of:
        notes.append(f"as_of {ts.date()} posterior ao fim do painel ({panel.as_of}).")
    cols: dict[str, pd.Series] = {}
    for name in selected:
        s = SIGNALS[name].fn(panel, md, model, ts, ids)
        cols[name] = s.reindex(ids).astype(float)
        notes.extend(f"{name}: {m}" for m in s.attrs.get("notes", []))
    out = pd.DataFrame(cols, index=pd.Index(ids, name="issuer_id"), columns=selected)
    out.attrs = {
        "as_of": ts.date().isoformat(),
        "notes": notes,
        "point_in_time": {n: SIGNALS[n].point_in_time for n in selected},
    }
    return out
