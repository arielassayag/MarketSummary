"""Escore de risco de short squeeze por emissor (0–100) e faixa LOW / MEDIUM / HIGH / NA.

Os componentes são pontuados **por linha e por fonte**, com os limiares da fonte, e o emissor
recebe o maior escore entre as suas linhas (conservador). Os valores brutos publicados
(``si_pct_float``, ``days_to_cover``, ``borrow_fee``) são os da linha/fonte que determina o
escore, para que valor e escore sejam sempre coerentes.

Fontes e limiares (``squeeze`` em ``configs/latam_ls/fund.yaml``):

- **SI dos EUA** (``short_interest``, linhas listadas nos EUA): ``short_pct_float`` com
  ``si_pct_float_medium/high``; dias para cobrir = ``short_ratio_days`` (se ausente,
  ``shares_short`` / volume médio de ações, sinalizado ``SI_US_implicito``) com
  ``days_to_cover_medium/high``.
- **BTC da B3** (``lending``, linhas locais BR). O saldo BTC inclui arbitragem, ETF e hedge,
  portanto **não** é short interest; a calibração própria vem de docs/research/06 §4.3:
  - saldo em % do **free float**: ``lending_pct_shares`` (em % das ações) ÷ fração de free float
    da linha (``float_shares / shares_outstanding``, em (0, 1]; razão inválida ⇒ mediana das
    linhas do emissor). Sem free float confiável, usa-se a base em ações, que subestima o
    percentual; o alerta é ``btc_base=acoes``. Limiares ``br_btc_pct_float_medium/high``.
  - "DTC" BTC = ``lent_shares`` / volume médio de ações da linha na janela
    ``liquidity.adv_window_days`` (somente datas <= ``panel.as_of``), com
    ``br_btc_dtc_medium/high``.
  - taxa observada no BTC (sinal primário) com ``br_borrow_fee_medium/high``.
- **Taxa estimada** (GC dos EUA ou da B3, vinda de
  :func:`latam_ls.analytics.shortability.short_availability`): é publicada em ``borrow_fee``
  (``borrow_fee_is_estimate = True``), mas **não entra no escore**. Ela é uma suposição (GC) ou
  uma função do próprio SI, não uma evidência independente. Pontuá-la diluiria o composto com
  um valor otimista ou contaria o SI duas vezes. Taxas observadas de outras fontes usariam
  ``borrow_fee_medium/high``.
- ``ret_1m``/``ret_3m``/``vol_1m``: retornos totais em USD do emissor (``panel.returns``) nas
  últimas 21/63 sessões até ``panel.as_of``, com pelo menos 60% de observações na janela.
- ``free_float_mcap_usd`` (painel) e ``days_to_earnings`` (próximo resultado em qualquer linha;
  datas passadas são descartadas como defasadas).

Componentes (0–100; ``NaN`` se o insumo falta, nunca zero):

- si, dtc, fee, mom (``ret_1m``): linear por partes, com 0 em 0, 40 no limiar ``medium``, 70 no
  ``high`` e 100 em 2× ``high`` (limitado a 100; valores negativos ⇒ 0).
- float: 100 se free float <= 25% de ``free_float_mcap_low_usd``, 40 no limiar e 0 a partir de
  10× o limiar (interpolação em log).
- catalyst: 100 com resultado em até 7 dias, 50 em até 14, senão 0. Data passada ⇒ ``NaN``.

Composto = média ponderada dos componentes disponíveis (si 0,30; dtc 0,25; fee 0,15; mom 0,15;
float 0,10; catalyst 0,05; pesos renormalizados) **e** regra do máximo: se qualquer componente
si/dtc/fee/mom for >= 70, o composto é no mínimo ``squeeze.score_high`` (um sinal vermelho basta).

Faixa: ``HIGH`` se o composto >= ``score_high``; ``MEDIUM`` se >= ``score_medium``; senão ``LOW``.
Se **si e dtc** faltam ao mesmo tempo e o composto não é ``HIGH``, a faixa é ``NA``: não há dado
suficiente para afirmar risco baixo. Consumidores devem tratar ``NA`` (e qualquer valor ausente
ou desconhecido) como ``MEDIUM`` (ver :func:`effective_bucket` e :func:`short_cap_multiplier`).

Short interest, aluguel, fundamentos e datas de resultado são retratos atuais do snapshot, não
point-in-time. Se ``panel.as_of`` é anterior ao snapshot, ou se a data do dado é posterior a
``panel.as_of``, o emissor recebe o alerta ``nao_pit`` e ``point_in_time = False``.
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
from .shortability import (
    ESTIMATED_FEE_SOURCES,
    FEE_SOURCE_B3,
    FEE_SOURCE_NA,
    numeric_field,
)

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
LENDING_STALE_DAYS = 10
"""Dado de BTC mais antigo que isso (dias corridos vs. ``as_of``) ⇒ alerta ``aluguel_defasado``."""

SOURCE_SI_US = "SI_US"
SOURCE_SI_US_IMPLIED = "SI_US_implicito"
SOURCE_BTC = "BTC_B3"

BUCKET_LOW, BUCKET_MEDIUM, BUCKET_HIGH, BUCKET_NA = "LOW", "MEDIUM", "HIGH", "NA"
BUCKETS = (BUCKET_LOW, BUCKET_MEDIUM, BUCKET_HIGH, BUCKET_NA)

SQUEEZE_COLUMNS = [
    "si_pct_float", "days_to_cover", "borrow_fee", "lending_pct_shares", "ret_1m", "ret_3m",
    "vol_1m", "free_float_mcap_usd", "days_to_earnings",
    "score_si", "score_dtc", "score_fee", "score_mom", "score_float", "score_catalyst",
    "squeeze_score", "bucket", "btc_pct_float", "borrow_fee_is_estimate",
    "components_available", "point_in_time", "data_quality",
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
    """100 se o resultado sai em até 7 dias, 50 em até 14 e 0 depois.

    Sem data ⇒ ``NaN``. Data passada (dias < 0) também ⇒ ``NaN``: é dado defasado, não um
    catalisador iminente.
    """
    d = days_to_earnings.astype(float)
    valid = d.notna() & (d >= 0)
    with np.errstate(invalid="ignore"):
        scored = np.select([d <= CATALYST_NEAR_DAYS, d <= CATALYST_MID_DAYS], [100.0, 50.0],
                           default=0.0)
    return pd.Series(scored, index=d.index, dtype=float).where(valid)


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


def normalize_bucket(bucket: pd.Series) -> pd.Series:
    """Faixa normalizada (maiúsculas, sem espaços); ausente ou desconhecida ⇒ ``NA``."""
    b = bucket.map(lambda v: v.strip().upper() if isinstance(v, str) else BUCKET_NA)
    return b.where(b.isin(BUCKETS), BUCKET_NA).astype(object)


def effective_bucket(bucket: pd.Series) -> pd.Series:
    """Faixa usada nas restrições, que falha fechada.

    ``NA``, ausente (``NaN``/``None``) ou desconhecida ⇒ ``MEDIUM``. Nunca ``LOW`` por omissão.
    """
    b = normalize_bucket(bucket)
    return b.where(b != BUCKET_NA, BUCKET_MEDIUM).astype(object)


def short_cap_multiplier(squeeze: pd.DataFrame, cfg: FundConfig) -> pd.Series:
    """Multiplicador do teto de short por emissor.

    HIGH ⇒ 0 (short proibido); LOW ⇒ 1. MEDIUM, NA, ausente ou desconhecido ⇒
    ``squeeze.medium_short_cap_multiplier`` (falha fechada).
    """
    eff = effective_bucket(squeeze["bucket"])
    mult = np.select([eff == BUCKET_HIGH, eff == BUCKET_LOW], [0.0, 1.0],
                     default=cfg.squeeze.medium_short_cap_multiplier)
    return pd.Series(mult, index=squeeze.index, dtype=float, name="short_cap_multiplier")


# ----------------------------------------------------------------------------------------
# Insumos
# ----------------------------------------------------------------------------------------

def _upto(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    return df.loc[df.index <= as_of]


def _min_obs(window: int) -> int:
    return int(math.ceil(MIN_OBS_FRACTION * window))


def window_return(returns: pd.DataFrame, as_of: pd.Timestamp, window: int) -> pd.Series:
    """Retorno composto das últimas ``window`` sessões até ``as_of`` (``NaN`` se poucas obs.).

    Os retornos do painel são calculados entre pregões válidos consecutivos, então um ``NaN``
    (feriado) não é retorno perdido e pode ser ignorado no produto.
    """
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


def float_fraction(fundamentals: pd.DataFrame, issuer: pd.Series) -> pd.Series:
    """Fração de free float por linha (``float_shares / shares_outstanding``), em (0, 1].

    Uma razão é inválida quando está ausente, é <= 0 ou é > 1. O Yahoo, por exemplo, mistura
    ON/PN no PETR4 e dá ``floatShares > sharesOutstanding``. Nesse caso usa-se a mediana das
    razões válidas das outras linhas do mesmo emissor; sem nenhuma, o resultado é ``NaN``.
    ``issuer`` é indexado por ticker.
    """
    idx = issuer.index
    so = numeric_field(fundamentals, "shares_outstanding", idx)
    fl = numeric_field(fundamentals, "float_shares", idx)
    frac = (fl / so.where(so > 0)).astype(float)
    frac = frac.where((frac > 0.0) & (frac <= 1.0))
    by_issuer = frac.groupby(issuer).median()
    return frac.where(frac.notna(), issuer.map(by_issuer)).astype(float)


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


def _candidates(lf: pd.DataFrame, raw: str, score: str, source: pd.Series | str) -> pd.DataFrame:
    """Candidatos (linha, fonte, valor bruto, escore) a determinar um componente do emissor."""
    src = source if isinstance(source, pd.Series) else pd.Series(source, index=lf.index)
    return pd.DataFrame({
        "issuer_id": lf["issuer_id"].astype(str),
        "ticker": lf.index.astype(str),
        "source": src.astype(object),
        "raw": lf[raw].astype(float),
        "score": lf[score].astype(float),
    }).reset_index(drop=True)


def _driver(cands: list[pd.DataFrame], ids: pd.Index) -> pd.DataFrame:
    """Linha/fonte que determina o componente do emissor.

    Critério: maior escore; empate ⇒ maior valor bruto, depois ticker (determinístico).
    Emissor sem candidato ⇒ linha ``NaN``.
    """
    c = pd.concat(cands, ignore_index=True)
    c = c[c["score"].notna()]
    c = c.sort_values(["issuer_id", "score", "raw", "ticker"],
                      ascending=[True, False, False, True])
    return c.groupby("issuer_id", sort=False).head(1).set_index("issuer_id").reindex(ids)


def _line_inputs(panel: AssetPanel, md: MarketData, availability: pd.DataFrame,
                 cfg: FundConfig) -> pd.DataFrame:
    """Insumos e escores de squeeze por linha (índice = ticker), com limiares por fonte."""
    sq = cfg.squeeze
    lines = panel.lines
    idx = lines.index
    issuer = lines["issuer_id"].astype(str)
    as_of = pd.Timestamp(panel.as_of)

    # SI dos EUA
    si_us = numeric_field(md.short_interest, "short_pct_float", idx)
    ratio_days = numeric_field(md.short_interest, "short_ratio_days", idx)
    shares_short = numeric_field(md.short_interest, "shares_short", idx)
    avg_vol = average_share_volume(md.volume, idx, as_of, cfg.liquidity.adv_window_days)
    dtc_us_implied = days_to_cover_from_shares(shares_short, avg_vol)
    dtc_us = ratio_days.where(ratio_days.notna(), dtc_us_implied)

    # BTC da B3 (saldo em % do free float; "DTC" sobre volume da própria linha)
    lend_pct = numeric_field(md.lending, "lending_pct_shares", idx)
    lent_shares = numeric_field(md.lending, "lent_shares", idx)
    frac = float_fraction(md.fundamentals, issuer)
    btc_pct_float = (lend_pct / frac).where(frac.notna())
    btc_proxy = btc_pct_float.where(btc_pct_float.notna(), lend_pct)
    dtc_br = days_to_cover_from_shares(lent_shares, avg_vol)

    # Taxa: só a observada entra no escore (estimativa é suposição, não evidência)
    avail = availability.reindex(idx)
    fee = avail["borrow_fee_annual"].astype(float)
    fee_source = avail["fee_source"].astype(object)
    observed = (fee.notna() & fee_source.notna() & ~fee_source.isin(ESTIMATED_FEE_SOURCES)
                & (fee_source != FEE_SOURCE_NA))
    is_b3 = fee_source == FEE_SOURCE_B3
    fee_obs = fee.where(observed)
    s_fee = threshold_score(fee_obs, sq.br_borrow_fee_medium, sq.br_borrow_fee_high).where(
        is_b3, threshold_score(fee_obs, sq.borrow_fee_medium, sq.borrow_fee_high))

    return pd.DataFrame({
        "issuer_id": issuer,
        "si_us": si_us,
        "lend_pct": lend_pct,
        "btc_pct_float": btc_pct_float,
        "btc_proxy": btc_proxy,
        "btc_shares_base": lend_pct.notna() & btc_pct_float.isna(),
        "dtc_us": dtc_us,
        "dtc_us_implied": ratio_days.isna() & dtc_us_implied.notna(),
        "dtc_br": dtc_br,
        "dtc_infinite": np.isinf(dtc_us) | np.isinf(dtc_br),
        "fee": fee,
        "fee_obs": fee_obs,
        "fee_est": fee.where(~observed),
        "fee_source": fee_source,
        "s_si_us": threshold_score(si_us, sq.si_pct_float_medium, sq.si_pct_float_high),
        "s_si_br": threshold_score(btc_proxy, sq.br_btc_pct_float_medium,
                                   sq.br_btc_pct_float_high),
        "s_dtc_us": threshold_score(dtc_us, sq.days_to_cover_medium, sq.days_to_cover_high),
        "s_dtc_br": threshold_score(dtc_br, sq.br_btc_dtc_medium, sq.br_btc_dtc_high),
        "s_fee": s_fee,
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


def _data_quality(ids: pd.Index, lf: pd.DataFrame, table: pd.DataFrame, fee_label: pd.Series,
                  stale_earnings: pd.Series, as_of: pd.Timestamp, snapshot_as_of: pd.Timestamp,
                  ) -> tuple[pd.Series, pd.Series]:
    """Texto de qualidade de dados por emissor e flag ``point_in_time``."""
    g = lf.groupby("issuer_id")

    def any_by(col: pd.Series) -> pd.Series:
        return col.groupby(lf["issuer_id"]).any().reindex(ids).fillna(False).astype(bool)

    has_si_us = any_by(lf["si_us"].notna())
    has_lend = any_by(lf["lend_pct"].notna())
    btc_shares_base = any_by(lf["btc_shares_base"])
    has_dtc_us = any_by(lf["dtc_us"].notna() & ~lf["dtc_us_implied"])
    has_dtc_impl = any_by(lf["dtc_us"].notna() & lf["dtc_us_implied"])
    has_dtc_br = any_by(lf["dtc_br"].notna())
    dtc_inf = any_by(lf["dtc_infinite"])
    si_age = (as_of - g["si_date"].max().reindex(ids)).dt.days
    si_stale = si_age.gt(SI_STALE_DAYS).fillna(False)
    lend_age = (as_of - g["lend_date"].max().reindex(ids)).dt.days
    lend_stale = lend_age.gt(LENDING_STALE_DAYS).fillna(False)
    future_dated = any_by(lf["si_date"].gt(as_of) | lf["lend_date"].gt(as_of))
    snapshot_later = bool(snapshot_as_of > as_of)
    pit = ~(future_dated | snapshot_later)

    texts = []
    for i in ids:
        si_src = "+".join(s for s, ok in ((SOURCE_SI_US, has_si_us[i]),
                                          (SOURCE_BTC, has_lend[i])) if ok)
        dtc_src = "+".join(s for s, ok in ((SOURCE_SI_US, has_dtc_us[i]),
                                           (SOURCE_SI_US_IMPLIED, has_dtc_impl[i]),
                                           (SOURCE_BTC, has_dtc_br[i])) if ok)
        row = table.loc[i]
        missing = [k for k in COMPONENT_WEIGHTS if pd.isna(row[f"score_{k}"])]
        alerts = []
        if not pit[i]:
            alerts.append("nao_pit")
        if si_stale[i]:
            alerts.append("si_defasado")
        if lend_stale[i]:
            alerts.append("aluguel_defasado")
        if dtc_inf[i]:
            alerts.append("dtc_infinito_sem_volume")
        if stale_earnings[i]:
            alerts.append("data_resultado_defasada")
        if row["bucket"] == BUCKET_NA:
            alerts.append("faixa_NA_tratar_como_MEDIUM")
        parts = [f"si={si_src or 'ausente'}"]
        if has_lend[i]:
            parts.append(f"btc_base={'acoes' if btc_shares_base[i] else 'free_float'}")
        parts += [f"dtc={dtc_src or 'ausente'}", f"fee={fee_label[i]}",
                  f"ausentes={','.join(missing) if missing else 'nenhum'}"]
        if alerts:
            parts.append(f"alertas={','.join(alerts)}")
        texts.append("; ".join(parts))
    return pd.Series(texts, index=ids, dtype=object), pit.astype(bool)


def _fee_label(fee_drv: pd.DataFrame, est_pick: pd.DataFrame, ids: pd.Index) -> pd.Series:
    """Rótulo da fonte da taxa: observada, estimada (fora do escore) ou ausente."""
    labels = {}
    for i in ids:
        if pd.notna(fee_drv.loc[i, "score"]):
            labels[i] = str(fee_drv.loc[i, "source"])
        elif i in est_pick.index:
            labels[i] = f"{est_pick.loc[i, 'fee_source']}(estimada,fora_do_escore)"
        else:
            labels[i] = "ausente"
    return pd.Series(labels, index=ids, dtype=object)


# ----------------------------------------------------------------------------------------
# API pública
# ----------------------------------------------------------------------------------------

def squeeze_table(panel: AssetPanel, md: MarketData, availability: pd.DataFrame,
                  cfg: FundConfig) -> pd.DataFrame:
    """Tabela de risco de short squeeze por emissor (índice ``issuer_id``, todos do painel).

    Colunas: ``si_pct_float`` (proxy de SI em % do float da linha/fonte que determina
    ``score_si``), ``days_to_cover``, ``borrow_fee`` (observada; sem observação, a maior
    estimada), ``lending_pct_shares`` (BTC bruto em % das ações, máximo entre as linhas),
    ``ret_1m``, ``ret_3m``, ``vol_1m`` (anualizada), ``free_float_mcap_usd``,
    ``days_to_earnings``, ``score_si``, ``score_dtc``, ``score_fee``, ``score_mom``,
    ``score_float``, ``score_catalyst``, ``squeeze_score`` (0–100), ``bucket``
    (``LOW``/``MEDIUM``/``HIGH``/``NA``; ``NA`` deve ser tratado como ``MEDIUM``),
    ``btc_pct_float`` (BTC em % do free float, máximo entre as linhas B3; ``NaN`` sem free
    float confiável), ``borrow_fee_is_estimate`` (bool), ``components_available`` (int),
    ``point_in_time`` (bool) e ``data_quality`` (fontes, componentes ausentes e alertas).
    """
    sq = cfg.squeeze
    ids = panel.assets.index
    as_of = pd.Timestamp(panel.as_of)
    lf = _line_inputs(panel, md, availability, cfg)
    by_issuer = lf.groupby("issuer_id")

    si_drv = _driver([_candidates(lf, "si_us", "s_si_us", SOURCE_SI_US),
                      _candidates(lf, "btc_proxy", "s_si_br", SOURCE_BTC)], ids)
    dtc_us_src = pd.Series(np.where(lf["dtc_us_implied"], SOURCE_SI_US_IMPLIED, SOURCE_SI_US),
                           index=lf.index)
    dtc_drv = _driver([_candidates(lf, "dtc_us", "s_dtc_us", dtc_us_src),
                       _candidates(lf, "dtc_br", "s_dtc_br", SOURCE_BTC)], ids)
    fee_drv = _driver([_candidates(lf, "fee_obs", "s_fee", lf["fee_source"])], ids)
    est_pick = _first_by_issuer(lf["fee_est"], lf["issuer_id"], ascending=False)
    est_pick = est_pick.join(lf[["fee_source"]], on="ticker")
    est_fee = est_pick["value"].reindex(ids).astype(float)
    days_to_earn, stale_earn = _issuer_days_to_earnings(lf, as_of, ids)

    t = pd.DataFrame(index=ids)
    t["si_pct_float"] = si_drv["raw"].astype(float)
    t["days_to_cover"] = dtc_drv["raw"].astype(float)
    obs_fee = fee_drv["raw"].astype(float)
    t["borrow_fee"] = obs_fee.where(obs_fee.notna(), est_fee)
    t["lending_pct_shares"] = by_issuer["lend_pct"].max().reindex(ids).astype(float)
    t["ret_1m"] = window_return(panel.returns, as_of, WINDOW_1M).reindex(ids).astype(float)
    t["ret_3m"] = window_return(panel.returns, as_of, WINDOW_3M).reindex(ids).astype(float)
    t["vol_1m"] = window_vol(panel.returns, as_of, WINDOW_1M).reindex(ids).astype(float)
    t["free_float_mcap_usd"] = panel.assets["free_float_mcap_usd"].reindex(ids).astype(float)
    t["days_to_earnings"] = days_to_earn

    t["score_si"] = si_drv["score"].astype(float)
    t["score_dtc"] = dtc_drv["score"].astype(float)
    t["score_fee"] = fee_drv["score"].astype(float)
    t["score_mom"] = threshold_score(t["ret_1m"], sq.ret_1m_medium, sq.ret_1m_high)
    t["score_float"] = float_score(t["free_float_mcap_usd"], sq.free_float_mcap_low_usd)
    t["score_catalyst"] = catalyst_score(t["days_to_earnings"])

    t["squeeze_score"] = composite_squeeze_score(t, sq.score_high)
    t["bucket"] = squeeze_bucket(t["squeeze_score"], t["score_si"].isna(),
                                 t["score_dtc"].isna(), sq.score_medium, sq.score_high)
    t["btc_pct_float"] = by_issuer["btc_pct_float"].max().reindex(ids).astype(float)
    t["borrow_fee_is_estimate"] = (obs_fee.isna() & est_fee.notna()).astype(bool)
    score_cols = [f"score_{k}" for k in COMPONENT_WEIGHTS]
    t["components_available"] = t[score_cols].notna().sum(axis=1).astype(int)
    snapshot_as_of = pd.Timestamp(md.as_of)
    t["data_quality"], t["point_in_time"] = _data_quality(
        ids, lf, t, _fee_label(fee_drv, est_pick, ids), stale_earn, as_of, snapshot_as_of)
    t.index.name = "issuer_id"
    return t[SQUEEZE_COLUMNS]
