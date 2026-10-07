"""Coleta no Yahoo Finance (yfinance 1.x) e na FINRA com política explícita de qualidade.

Regras aplicadas (ver docs/research/06_fontes_dados_ferramentas.md):

- Sempre com ``User-Agent`` (sem ele o Yahoo devolve 429 já na primeira chamada); no máximo
  ``MAX_WORKERS`` = 8 requisições simultâneas; até ``RETRIES`` = 3 novas tentativas com backoff
  de 1/2/4 s em 429/5xx/timeouts. 404 ("delisted"/"not found") nunca é repetido: o ticker é
  registrado como ausente.
- Nunca inventa valores: ausência = ``NaN``; preço <= 0 é inválido (``NaN``); **volume 0 com
  preço válido é dado AUSENTE** (``NaN`` + flag ``volume_suspeito``), nunca liquidez zero
  (Santiago ``.SN`` tem muitos dias com volume 0 no Yahoo).
- ``auto_adjust=False``: ``Close`` (ajustado só por desdobramentos) e ``Adj Close`` (desdobramentos
  e proventos) são guardados separadamente.
- Barras diárias são normalizadas para a data do pregão removendo o fuso sem conversão (as barras
  de câmbio ``=X`` vêm carimbadas em Europe/London; converter para UTC mudaria o dia).
- Linhas com data posterior a ``end`` são descartadas (uma coleta na segunda de manhã pode trazer
  uma barra intradiária parcial).
- Moeda e bolsa vêm do NOSSO arquivo de universo, nunca dos metadados do Yahoo (Lima tem metadados
  quebrados; BAP.LM é cotado em USD).

Todas as funções de rede aceitam um ``downloader``/``ticker_factory``/``session`` injetável para
testes offline.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

from ..market import FUNDAMENTAL_FIELDS, SHORT_INTEREST_FIELDS
from ..universe import listing_market

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; cdp-cabra-da-peste-research/1.0)"
MAX_WORKERS = 8
RETRIES = 3
BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)
CHUNK_SIZE = 50
HTTP_TIMEOUT = 30.0
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

VOLUME_SUSPECT_FLAG = "volume_suspeito"
PRICE_COLUMNS = ["date", "ticker", "close", "adj_close", "volume", "volume_flag"]
FX_COLUMNS = ["date", "currency", "usd_per_unit"]
BENCHMARK_COLUMNS = ["date", "symbol", "close", "adj_close"]

# Colunas extras (além de market.FUNDAMENTAL_FIELDS) gravadas em fundamentals.parquet.
FUNDAMENTAL_EXTRA_FIELDS = [
    "currency_yahoo", "quote_type", "price_yahoo", "dividend_rate", "dividend_yield_raw",
    "implied_shares_outstanding", "fundamentals_quality",
]
SHORT_INTEREST_EXTRA_FIELDS = [
    "settlement_date", "publication_date", "shares_short_prior", "avg_daily_volume",
    "adr_ratio", "float_base_yahoo", "short_pct_float_yahoo", "implied_shares_outstanding",
    "short_pct_shares_equiv", "si_quality",
]

# Faixas de plausibilidade (fora delas o valor é mantido, mas sinalizado).
PB_RANGE = (0.05, 50.0)
PE_RANGE = (-300.0, 300.0)
EV_EBITDA_RANGE = (-100.0, 200.0)
DIVIDEND_YIELD_MAX = 0.40

FINRA_SI_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
FINRA_PUBLICATION_LAG_BDAYS = 7
FINRA_LOOKBACK_DAYS = 75

Downloader = Callable[..., pd.DataFrame | None]
TickerFactory = Callable[[str], Any]
Sleeper = Callable[[float], None]

_PERMANENT_ERROR_RE = re.compile(r"404|not found|delisted|no data found|no price data|invalid",
                                 re.IGNORECASE)


class FetchError(RuntimeError):
    """Falha de coleta após esgotar as novas tentativas."""


class FundamentosVaziosError(FetchError):
    """Nenhuma linha com fundamentos: falha de coleta (rede ou endpoint do Yahoo fora), nunca um
    retrato "vazio" que substitua os fundamentos gravados."""


# ======================================================================
# Política HTTP compartilhada (User-Agent, retry com backoff)
# ======================================================================

def _default_session() -> Any:
    import requests  # dependência transitiva do yfinance

    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"})
    return s


def http_request(method: str, url: str, *, session: Any | None = None, retries: int = RETRIES,
                 backoff: Sequence[float] = BACKOFF_SECONDS, sleep: Sleeper = time.sleep,
                 timeout: float = HTTP_TIMEOUT, **kwargs: Any) -> Any:
    """Requisição HTTP com ``User-Agent`` e novas tentativas em 429/5xx/erros de rede.

    Devolve o objeto de resposta (``status_code`` final pode ser 4xx não repetível, como 404:
    quem chama decide). Erros de rede após a última tentativa levantam :class:`FetchError`.
    """
    sess = session if session is not None else _default_session()
    headers = {"User-Agent": USER_AGENT}
    headers.update(kwargs.pop("headers", {}) or {})
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = sess.request(method, url, headers=headers, timeout=timeout, **kwargs)
        except Exception as exc:  # erros de rede/timeout: repetíveis
            last_exc = exc
            resp = None
        if resp is not None and int(getattr(resp, "status_code", 0)) not in RETRYABLE_STATUS:
            return resp
        if attempt < retries:
            sleep(backoff[min(attempt, len(backoff) - 1)])
            continue
        if resp is not None:
            return resp
    raise FetchError(f"Falha de rede em {method} {url}: {last_exc!r}")


def call_with_retry(fn: Callable[[], Any], *, retries: int = RETRIES,
                    backoff: Sequence[float] = BACKOFF_SECONDS, sleep: Sleeper = time.sleep,
                    what: str = "chamada") -> Any:
    """Executa ``fn`` com novas tentativas (backoff) para exceções não permanentes."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if _PERMANENT_ERROR_RE.search(str(exc)) or attempt >= retries:
                break
            sleep(backoff[min(attempt, len(backoff) - 1)])
    raise FetchError(f"{what} falhou: {last!r}") from last


# ======================================================================
# Conversões numéricas seguras
# ======================================================================

def to_float(v: Any) -> float:
    """Converte para float; ausente, texto inválido, bool ou não finito => NaN (nunca zero)."""
    if v is None or isinstance(v, bool):
        return math.nan
    try:
        x = float(v)
    except (TypeError, ValueError):
        return math.nan
    return x if math.isfinite(x) else math.nan


def _normalize_index(idx: pd.Index) -> pd.DatetimeIndex:
    """Normaliza para a data do pregão: remove o fuso SEM converter e zera o horário."""
    di = pd.DatetimeIndex(pd.to_datetime(idx))
    if di.tz is not None:
        di = di.tz_localize(None)
    return di.normalize()


def _fmt(d: date) -> str:
    return d.isoformat()


# ======================================================================
# Download em lote (preços, câmbio, benchmarks)
# ======================================================================

def _yf_download(**kwargs: Any) -> pd.DataFrame | None:
    import yfinance as yf

    return yf.download(**kwargs)


def _yf_errors() -> dict[str, str]:
    try:
        import yfinance.shared as shared

        return {str(k): str(v) for k, v in dict(getattr(shared, "_ERRORS", {}) or {}).items()}
    except Exception:  # pragma: no cover - depende da versão do yfinance
        return {}


def _split_download(raw: pd.DataFrame | None, tickers: Sequence[str]) -> dict[str, pd.DataFrame]:
    """Separa a saída do ``yf.download`` por ticker (campos Close/Adj Close/Volume)."""
    out: dict[str, pd.DataFrame] = {}
    if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
        return out
    cols = raw.columns
    for t in tickers:
        if isinstance(cols, pd.MultiIndex):
            lvl0 = set(cols.get_level_values(0))
            lvl1 = set(cols.get_level_values(1))
            if t in lvl1:
                sub = raw.xs(t, axis=1, level=1)
            elif t in lvl0:  # group_by="ticker"
                sub = raw[t]
            else:
                continue
        else:
            if len(tickers) != 1:
                continue
            sub = raw
        frame = pd.DataFrame(index=_normalize_index(sub.index))
        for field_name, col in (("close", "Close"), ("adj_close", "Adj Close"), ("volume", "Volume")):
            if col in sub.columns:
                frame[field_name] = pd.to_numeric(pd.Series(sub[col].to_numpy(), index=frame.index),
                                                  errors="coerce")
            else:
                frame[field_name] = np.nan
        frame = frame.dropna(how="all", subset=["close", "adj_close"])
        if not frame.empty:
            out[t] = frame
    return out


def download_bars(tickers: Sequence[str], start: date, end: date, *,
                  downloader: Downloader | None = None,
                  error_getter: Callable[[], dict[str, str]] | None = None,
                  chunk_size: int = CHUNK_SIZE, retries: int = RETRIES,
                  sleep: Sleeper = time.sleep) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Baixa barras diárias em blocos, com novas tentativas só para falhas transitórias.

    Devolve ``({ticker: frame[close, adj_close, volume]}, ausentes)``. ``end`` é inclusivo e
    linhas com data > ``end`` são descartadas.
    """
    dl = downloader or _yf_download
    errs = error_getter if error_getter is not None else (_yf_errors if downloader is None else None)
    uniq = sorted({str(t).strip() for t in tickers if str(t).strip()})
    got: dict[str, pd.DataFrame] = {}
    permanent: set[str] = set()
    end_ts = pd.Timestamp(end)
    for i in range(0, len(uniq), max(1, chunk_size)):
        pending = uniq[i:i + chunk_size]
        for attempt in range(retries + 1):
            if not pending:
                break
            try:
                raw = dl(tickers=list(pending), start=_fmt(start), end=_fmt(end + timedelta(days=1)),
                         interval="1d", auto_adjust=False, actions=False, group_by="column",
                         threads=min(MAX_WORKERS, len(pending)) if len(pending) > 1 else False,
                         progress=False,
                         multi_level_index=True)
            except Exception as exc:
                log.warning("Download falhou (%s): %r", ",".join(pending[:5]), exc)
                raw = None
            parts = _split_download(raw, pending)
            for t, fr in parts.items():
                fr = fr[fr.index <= end_ts]
                if not fr.empty:
                    got[t] = fr
            missing_now = [t for t in pending if t not in got]
            error_map = errs() if errs else {}
            permanent.update(t for t in missing_now
                             if _PERMANENT_ERROR_RE.search(error_map.get(t, "")))
            pending = [t for t in missing_now if t not in permanent]
            if pending and attempt < retries:
                sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
    missing = sorted(set(uniq) - set(got))
    return got, missing


def _clean_price_frame(t: str, fr: pd.DataFrame) -> pd.DataFrame:
    fr = fr[~fr.index.duplicated(keep="last")].sort_index()
    close = fr["close"].where(fr["close"] > 0)
    adj = fr["adj_close"].where(fr["adj_close"] > 0)
    vol = fr["volume"].where(fr["volume"] >= 0)
    # Volume 0 é AUSENTE sempre que a barra é mantida (close OU adj_close válido): nunca
    # "liquidez zero" — inclusive quando só o adj_close sobreviveu à validação.
    suspect = (vol == 0) & (close.notna() | adj.notna())
    vol = vol.mask(suspect)
    out = pd.DataFrame({
        "date": fr.index, "ticker": t, "close": close.to_numpy(dtype=float),
        "adj_close": adj.to_numpy(dtype=float), "volume": vol.to_numpy(dtype=float),
        "volume_flag": np.where(suspect.to_numpy(), VOLUME_SUSPECT_FLAG, ""),
    })
    return out[out["close"].notna() | out["adj_close"].notna()]


def fetch_price_history(tickers: Sequence[str], start: date, end: date, *,
                        downloader: Downloader | None = None,
                        error_getter: Callable[[], dict[str, str]] | None = None,
                        chunk_size: int = CHUNK_SIZE, retries: int = RETRIES,
                        sleep: Sleeper = time.sleep) -> tuple[pd.DataFrame, list[str]]:
    """Histórico diário em formato longo ``[date, ticker, close, adj_close, volume, volume_flag]``.

    Devolve também a lista ordenada de tickers sem nenhum dado (ausentes/renomeados).
    """
    bars, missing = download_bars(tickers, start, end, downloader=downloader,
                                  error_getter=error_getter, chunk_size=chunk_size,
                                  retries=retries, sleep=sleep)
    frames = [_clean_price_frame(t, fr) for t, fr in sorted(bars.items())]
    frames = [f for f in frames if not f.empty]
    if frames:
        df = pd.concat(frames, ignore_index=True)
    else:
        df = pd.DataFrame({c: pd.Series(dtype=float) for c in PRICE_COLUMNS})
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].astype(str)
    df["volume_flag"] = df["volume_flag"].astype(str)
    df = df.sort_values(["date", "ticker"]).reset_index(drop=True)
    missing = sorted(set(missing) | ({str(t) for t in tickers} - set(df["ticker"])))
    return df[PRICE_COLUMNS], missing


def fx_symbol(currency: str) -> str:
    return f"{currency.upper()}=X"


def fetch_fx_history(currencies: Iterable[str], start: date, end: date, *,
                     downloader: Downloader | None = None,
                     error_getter: Callable[[], dict[str, str]] | None = None,
                     retries: int = RETRIES, sleep: Sleeper = time.sleep) -> pd.DataFrame:
    """Câmbio longo ``[date, currency, usd_per_unit]`` a partir de ``<CCY>=X``.

    O Yahoo cota moeda local por USD; invertemos para USD por 1 unidade. Linhas de USD não
    são gravadas (``USD`` = 1.0 é adicionado na leitura).
    """
    ccys = sorted({c.upper() for c in currencies if c and c.upper() != "USD"})
    sym_to_ccy = {fx_symbol(c): c for c in ccys}
    bars, _ = download_bars(list(sym_to_ccy), start, end, downloader=downloader,
                            error_getter=error_getter, retries=retries, sleep=sleep)
    frames = []
    for sym, fr in sorted(bars.items()):
        fr = fr[~fr.index.duplicated(keep="last")].sort_index()
        px = fr["close"].where(fr["close"] > 0)
        f = pd.DataFrame({"date": fr.index, "currency": sym_to_ccy[sym],
                          "usd_per_unit": (1.0 / px).to_numpy(dtype=float)})
        frames.append(f.dropna(subset=["usd_per_unit"]))
    if frames:
        df = pd.concat(frames, ignore_index=True)
    else:
        df = pd.DataFrame({c: pd.Series(dtype=float) for c in FX_COLUMNS})
    df["date"] = pd.to_datetime(df["date"])
    df["currency"] = df["currency"].astype(str)
    return df.sort_values(["date", "currency"]).reset_index(drop=True)[FX_COLUMNS]


def fetch_benchmarks(symbols: Iterable[str], start: date, end: date, *,
                     downloader: Downloader | None = None,
                     error_getter: Callable[[], dict[str, str]] | None = None,
                     retries: int = RETRIES, sleep: Sleeper = time.sleep) -> pd.DataFrame:
    """Benchmarks longos ``[date, symbol, close, adj_close]`` (fechamento nativo)."""
    bars, _ = download_bars(list(symbols), start, end, downloader=downloader,
                            error_getter=error_getter, retries=retries, sleep=sleep)
    frames = []
    for sym, fr in sorted(bars.items()):
        fr = fr[~fr.index.duplicated(keep="last")].sort_index()
        f = pd.DataFrame({"date": fr.index, "symbol": sym,
                          "close": fr["close"].where(fr["close"] > 0).to_numpy(dtype=float),
                          "adj_close": fr["adj_close"].where(fr["adj_close"] > 0).to_numpy(dtype=float)})
        frames.append(f.dropna(subset=["close"]))
    if frames:
        df = pd.concat(frames, ignore_index=True)
    else:
        df = pd.DataFrame({c: pd.Series(dtype=float) for c in BENCHMARK_COLUMNS})
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = df["symbol"].astype(str)
    return df.sort_values(["date", "symbol"]).reset_index(drop=True)[BENCHMARK_COLUMNS]


# ======================================================================
# Fundamentos (Ticker.info) — retrato atual, NÃO point-in-time
# ======================================================================

_INFO_MAP = {
    "market_cap": "marketCap", "shares_outstanding": "sharesOutstanding",
    "float_shares": "floatShares", "trailing_pe": "trailingPE", "forward_pe": "forwardPE",
    "price_to_book": "priceToBook", "book_value": "bookValue", "trailing_eps": "trailingEps",
    "forward_eps": "forwardEps", "return_on_equity": "returnOnEquity",
    "return_on_assets": "returnOnAssets", "profit_margins": "profitMargins",
    "operating_margins": "operatingMargins", "gross_margins": "grossMargins",
    "debt_to_equity": "debtToEquity", "enterprise_to_ebitda": "enterpriseToEbitda",
    "revenue_growth": "revenueGrowth", "earnings_growth": "earningsGrowth", "beta": "beta",
    "target_mean_price": "targetMeanPrice", "recommendation_mean": "recommendationMean",
    "number_of_analyst_opinions": "numberOfAnalystOpinions",
    "average_daily_volume_3m": "averageDailyVolume3Month",
}
_TEXT_FIELDS = {"currency", "financial_currency", "sector", "industry", "next_earnings_date"}


def _yf_ticker(symbol: str) -> Any:
    import yfinance as yf

    return yf.Ticker(symbol)


def _price_from_info(info: Mapping[str, Any]) -> float:
    for k in ("currentPrice", "regularMarketPrice", "previousClose", "regularMarketPreviousClose"):
        v = to_float(info.get(k))
        if v > 0:
            return v
    return math.nan


def normalize_dividend_yield(info: Mapping[str, Any]) -> tuple[float, str]:
    """Normaliza ``dividendYield`` para decimal (0.05 = 5%).

    O yfinance 1.x devolve ``dividendYield`` em PERCENTUAL (ex.: 4.31 = 4,31%; verificado em
    2026-10-05: GGAL 4.31 com ``dividendRate``/preço = 1.55/35.89 = 4,32%), enquanto versões antigas
    devolviam decimal. Detecção, em ordem:

    1. referência ``dividendRate``/preço (mesma moeda de cotação): escolhe a escala (1 ou 1/100)
       mais próxima da referência;
    2. sem referência: valor > 1 só pode ser percentual (/100); valores <= 1 seguem a convenção do
       yfinance 1.x (percentual, /100).

    Devolve ``(valor_decimal, regra_usada)``.
    """
    dy = to_float(info.get("dividendYield"))
    if math.isnan(dy):
        return math.nan, "ausente"
    if dy == 0:
        return 0.0, "zero"
    rate = to_float(info.get("dividendRate"))
    px = _price_from_info(info)
    if rate > 0 and px > 0:
        ref = rate / px
        as_pct = dy / 100.0
        return (as_pct, "ref_dividend_rate_pct") if abs(as_pct - ref) <= abs(dy - ref) else (
            dy, "ref_dividend_rate_dec")
    return dy / 100.0, "convencao_yfinance_1x_pct"


def _epoch_to_date(v: Any) -> date | None:
    x = to_float(v)
    if math.isnan(x) or x <= 0:
        return None
    try:
        return datetime.fromtimestamp(x, tz=UTC).date()
    except (OverflowError, OSError, ValueError):
        return None


def _calendar_dates(obj: Any) -> list[date]:
    out: list[date] = []
    try:
        cal = obj.calendar
    except Exception:
        return out
    vals: Any = None
    if isinstance(cal, Mapping):
        vals = cal.get("Earnings Date")
    elif isinstance(cal, pd.DataFrame) and not cal.empty:
        if "Earnings Date" in cal.index:
            vals = list(cal.loc["Earnings Date"].to_numpy())
        elif "Earnings Date" in cal.columns:
            vals = list(cal["Earnings Date"].to_numpy())
    if vals is None:
        return out
    if not isinstance(vals, (list, tuple, np.ndarray, pd.Series)):
        vals = [vals]
    for v in vals:
        try:
            ts = pd.Timestamp(v)
        except (TypeError, ValueError):
            continue
        if pd.notna(ts):
            out.append(ts.date())
    return out


def next_earnings_date(obj: Any, info: Mapping[str, Any], ref: date) -> str | float:
    """Próxima data de resultado >= ``ref`` (calendário do Yahoo, depois timestamps do info)."""
    cands = [d for d in _calendar_dates(obj) if d >= ref]
    for k in ("earningsTimestampStart", "earningsTimestamp", "earningsTimestampEnd"):
        d = _epoch_to_date(info.get(k))
        if d is not None and d >= ref:
            cands.append(d)
    return min(cands).isoformat() if cands else math.nan


def fundamentals_quality_flags(row: Mapping[str, Any]) -> str:
    """Flags de plausibilidade (valores NUNCA são alterados; apenas sinalizados)."""
    flags: list[str] = []

    def out_of(v: float, lo: float, hi: float) -> bool:
        return not math.isnan(v) and not (lo <= v <= hi)

    if row.get("_no_info"):
        return "sem_dados"
    if out_of(to_float(row.get("price_to_book")), *PB_RANGE):
        flags.append("pb_implausivel")
    if out_of(to_float(row.get("trailing_pe")), *PE_RANGE) or out_of(
            to_float(row.get("forward_pe")), *PE_RANGE):
        flags.append("pe_implausivel")
    if out_of(to_float(row.get("enterprise_to_ebitda")), *EV_EBITDA_RANGE):
        flags.append("ev_ebitda_implausivel")
    dy = to_float(row.get("dividend_yield"))
    if not math.isnan(dy) and dy > DIVIDEND_YIELD_MAX:
        flags.append("dy_implausivel")
    so, fl = to_float(row.get("shares_outstanding")), to_float(row.get("float_shares"))
    if not math.isnan(so) and not math.isnan(fl) and fl > so:
        flags.append("float_maior_que_total")
    cy, cur = row.get("currency_yahoo"), row.get("currency")
    if isinstance(cy, str) and cy and isinstance(cur, str) and cur and cy.upper() != cur.upper():
        flags.append("moeda_yahoo_divergente")
    fc = row.get("financial_currency")
    if isinstance(fc, str) and fc and isinstance(cur, str) and cur and fc.upper() != cur.upper():
        flags.append("moeda_demonstrativos_diferente")
    return ";".join(flags) if flags else "OK"


def _info_row(symbol: str, obj: Any, info: Mapping[str, Any] | None, currency: str | None,
              ref: date) -> dict[str, Any]:
    row: dict[str, Any] = {f: math.nan for f in FUNDAMENTAL_FIELDS + FUNDAMENTAL_EXTRA_FIELDS}
    info = dict(info or {})
    usable = bool(info) and any(info.get(v) is not None for v in _INFO_MAP.values())
    for f, k in _INFO_MAP.items():
        if f in ("sector", "industry"):
            continue
        row[f] = to_float(info.get(k))
    for f, k in (("sector", "sector"), ("industry", "industry")):
        v = info.get(k)
        row[f] = str(v) if isinstance(v, str) and v.strip() else math.nan
    cy = info.get("currency")
    row["currency_yahoo"] = str(cy).upper() if isinstance(cy, str) and cy.strip() else math.nan
    row["currency"] = (currency.upper() if currency else row["currency_yahoo"])
    fc = info.get("financialCurrency")
    row["financial_currency"] = str(fc).upper() if isinstance(fc, str) and fc.strip() else math.nan
    qt = info.get("quoteType")
    row["quote_type"] = str(qt) if isinstance(qt, str) and qt.strip() else math.nan
    row["price_yahoo"] = _price_from_info(info)
    row["dividend_rate"] = to_float(info.get("dividendRate"))
    row["dividend_yield_raw"] = to_float(info.get("dividendYield"))
    row["dividend_yield"], _rule = normalize_dividend_yield(info)
    row["implied_shares_outstanding"] = to_float(info.get("impliedSharesOutstanding"))
    row["next_earnings_date"] = next_earnings_date(obj, info, ref) if usable else math.nan
    row["_no_info"] = not usable
    row["fundamentals_quality"] = fundamentals_quality_flags(row)
    row.pop("_no_info", None)
    return row


def _fetch_info(symbol: str, factory: TickerFactory, sleep: Sleeper) -> tuple[Any, dict | None]:
    obj = factory(symbol)

    def get() -> dict:
        info = obj.info
        if info is None:
            return {}
        return dict(info)

    try:
        return obj, call_with_retry(get, sleep=sleep, what=f"info {symbol}")
    except FetchError as exc:
        log.warning("Sem fundamentos para %s: %s", symbol, exc)
        return obj, None


def fetch_infos(tickers: Sequence[str], *, ticker_factory: TickerFactory | None = None,
                max_workers: int = MAX_WORKERS,
                sleep: Sleeper = time.sleep) -> dict[str, tuple[Any, dict | None]]:
    """Coleta ``Ticker.info`` em paralelo (<= 8 threads). Falha => ``None`` (registrada)."""
    factory = ticker_factory or _yf_ticker
    uniq = sorted({str(t) for t in tickers})
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, max_workers))) as ex:
        results = list(ex.map(lambda s: _fetch_info(s, factory, sleep), uniq))
    return dict(zip(uniq, results, strict=True))


def fundamentals_frame(rows: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    """Monta o DataFrame de fundamentos com ordem de colunas determinística."""
    cols = FUNDAMENTAL_FIELDS + FUNDAMENTAL_EXTRA_FIELDS
    df = pd.DataFrame.from_dict({k: dict(v) for k, v in rows.items()}, orient="index")
    for c in cols:
        if c not in df.columns:
            df[c] = math.nan
    extras = sorted(c for c in df.columns if c not in cols)
    df = df[cols + extras].sort_index()
    df.index.name = "ticker"
    for c in df.columns:
        if c in _TEXT_FIELDS or c in ("currency_yahoo", "quote_type", "fundamentals_quality"):
            df[c] = df[c].astype(object).where(df[c].notna(), None)
        else:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def fetch_fundamentals(tickers: Sequence[str], *, currency_map: Mapping[str, str] | None = None,
                       as_of: date | None = None, ticker_factory: TickerFactory | None = None,
                       max_workers: int = MAX_WORKERS, sleep: Sleeper = time.sleep) -> pd.DataFrame:
    """Fundamentos por linha (índice ticker) com ``market.FUNDAMENTAL_FIELDS`` + extras.

    ``currency`` vem do universo (``currency_map``); a moeda do Yahoo fica em ``currency_yahoo`` e
    divergências são sinalizadas em ``fundamentals_quality``. Múltiplos do Yahoo (P/L, P/VPA,
    EV/EBITDA, beta) são guardados como vieram, junto com os ingredientes brutos (LPA, VPA,
    moedas, ações), e marcados quando implausíveis. Linhas sem nenhum dado ficam com NaN e
    ``fundamentals_quality = 'sem_dados'``; se NENHUMA linha tiver dado, é falha de coleta
    (:class:`FundamentosVaziosError`), nunca um retrato vazio.
    """
    ref = as_of or datetime.now(UTC).date()
    infos = fetch_infos(tickers, ticker_factory=ticker_factory, max_workers=max_workers, sleep=sleep)
    cmap = {str(k): str(v) for k, v in (currency_map or {}).items()}
    rows = {t: _info_row(t, obj, info, cmap.get(t), ref) for t, (obj, info) in infos.items()}
    df = fundamentals_frame(rows)
    if len(df) and bool(linhas_sem_dados(df).all()):
        # Sem rede (ou com o endpoint fora) o yfinance não lança erro: devolve ``info`` vazio
        # para todo ticker. Isso é falha de coleta — nunca um retrato que apague os fundamentos
        # gravados (o valor de mercado some e o modelo de risco fica sem histórico).
        raise FundamentosVaziosError(
            f"Yahoo sem fundamentos para nenhuma das {len(df)} linhas (falha de coleta: rede ou "
            "endpoint fora); valem os fundamentos gravados")
    return df


def linhas_sem_dados(df: pd.DataFrame) -> pd.Series:
    """Máscara das linhas de fundamentos sem nenhum dado do Yahoo: ``fundamentals_quality ==
    'sem_dados'`` ou todos os campos numéricos ausentes (a moeda vem do universo, não conta)."""
    if df is None or len(df) == 0:
        return pd.Series(dtype=bool)
    flag = (df["fundamentals_quality"].astype(str) == "sem_dados"
            if "fundamentals_quality" in df.columns
            else pd.Series(False, index=df.index))
    num = [c for c in df.columns if c not in _TEXT_FIELDS
           and c not in ("currency_yahoo", "quote_type", "fundamentals_quality")]
    vazio = (df[num].apply(pd.to_numeric, errors="coerce").isna().all(axis=1) if num
             else pd.Series(True, index=df.index))
    return (flag | vazio).astype(bool)


# ======================================================================
# Short interest (FINRA + Yahoo) — somente linhas listadas nos EUA
# ======================================================================

_US_BDAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())


def finra_publication_date(settlement: date) -> date:
    """Data de publicação estimada: 7º dia útil após a liquidação.

    Usa o calendário federal dos EUA (conservador: em feriados federais com bolsa aberta a data
    estimada fica mais tarde, nunca antes — sem look-ahead).
    """
    return (pd.Timestamp(settlement) + FINRA_PUBLICATION_LAG_BDAYS * _US_BDAY).date()


def finra_symbol(yahoo_ticker: str) -> str:
    """Ticker Yahoo -> símbolo FINRA (classes: ``PBR-A`` -> ``PBRA``)."""
    return yahoo_ticker.upper().replace("-", "").replace(".", "")


def fetch_finra_short_interest(symbols: Sequence[str], as_of: date, *, session: Any | None = None,
                               lookback_days: int = FINRA_LOOKBACK_DAYS,
                               sleep: Sleeper = time.sleep) -> pd.DataFrame:
    """Short interest consolidado da FINRA (Query API; acesso anônimo — frágil).

    Devolve, por símbolo FINRA, a liquidação MAIS RECENTE cuja publicação estimada
    (liquidação + 7 dias úteis) é <= ``as_of`` — sem look-ahead. Colunas: ``finra_symbol,
    settlement_date, publication_date, shares_short, shares_short_prior, avg_daily_volume,
    days_to_cover``. Erro HTTP levanta :class:`FetchError`.
    """
    syms = sorted({s.upper() for s in symbols})
    cols = ["finra_symbol", "settlement_date", "publication_date", "shares_short",
            "shares_short_prior", "avg_daily_volume", "days_to_cover"]
    if not syms:
        return pd.DataFrame(columns=cols)
    start = as_of - timedelta(days=lookback_days)
    records: list[dict] = []
    for i in range(0, len(syms), 200):
        body = {
            "limit": 5000,
            "dateRangeFilters": [{"fieldName": "settlementDate", "startDate": start.isoformat(),
                                  "endDate": as_of.isoformat()}],
            "domainFilters": [{"fieldName": "symbolCode", "values": syms[i:i + 200]}],
            "fields": ["settlementDate", "symbolCode", "currentShortPositionQuantity",
                       "previousShortPositionQuantity", "averageDailyVolumeQuantity",
                       "daysToCoverQuantity"],
        }
        resp = http_request("POST", FINRA_SI_URL, session=session, json=body,
                            headers={"Accept": "application/json"}, sleep=sleep)
        if resp.status_code == 204:
            continue
        if resp.status_code != 200:
            raise FetchError(f"FINRA devolveu HTTP {resp.status_code}")
        data = resp.json() or []
        if not isinstance(data, list):
            raise FetchError("Resposta inesperada da FINRA (não é lista).")
        records.extend(data)
    rows = []
    for r in records:
        try:
            sd = date.fromisoformat(str(r.get("settlementDate"))[:10])
        except ValueError:
            continue
        pub = finra_publication_date(sd)
        if pub > as_of:
            continue
        rows.append({
            "finra_symbol": str(r.get("symbolCode", "")).upper(), "settlement_date": sd,
            "publication_date": pub,
            "shares_short": to_float(r.get("currentShortPositionQuantity")),
            "shares_short_prior": to_float(r.get("previousShortPositionQuantity")),
            "avg_daily_volume": to_float(r.get("averageDailyVolumeQuantity")),
            "days_to_cover": to_float(r.get("daysToCoverQuantity")),
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows).sort_values(["finra_symbol", "settlement_date"])
    df = df.groupby("finra_symbol", as_index=False).tail(1)
    return df[cols].reset_index(drop=True)


def _yahoo_si_date(info: Mapping[str, Any]) -> date | None:
    return _epoch_to_date(info.get("dateShortInterest"))


def build_short_interest_row(ticker: str, info: Mapping[str, Any] | None,
                             finra: Mapping[str, Any] | None, adr_ratio: float,
                             as_of: date) -> dict[str, Any] | None:
    """Combina FINRA (quantidade, liquidação, publicação) e Yahoo (base de float do ADS).

    - ``shares_short``: FINRA quando disponível (unidade = ADS para ADRs); senão Yahoo.
    - ``short_pct_float``: ``shares_short / base de float do Yahoo`` onde a base é
      ``sharesShort_yahoo / shortPercentOfFloat_yahoo`` (em ADS). Verificado em 2026-10-05: o
      percentual do Yahoo usa uma base de float do ADS (GGAL 17,98%), NÃO o ``floatShares`` (que
      mistura unidades: GGAL em ações locais, AMX em ADS). Essa medida é conservadora para squeeze.
      Base ausente ou implausível => fração sobre o total de ações em ADS-equivalentes (limite
      inferior, flag ``pct_sobre_total``).
    - ``short_pct_shares_equiv``: SI em ações-equivalentes / total de ações =
      ``SI_ADS × razão / ações locais`` = ``SI_ADS / (market cap USD / preço do ADS)``.
    Sem SI em nenhuma fonte => ``None`` (linha omitida; nunca zero). O SI do Yahoo só é usado
    se a sua liquidação já estiver PUBLICADA em ``as_of`` (liquidação + 7 dias úteis); senão é
    descartado (flag ``yahoo_si_nao_publicado_descartado``), como a FINRA.
    """
    info = dict(info or {})
    flags: list[str] = []
    y_ss = to_float(info.get("sharesShort"))
    y_spf = to_float(info.get("shortPercentOfFloat"))
    y_date = _yahoo_si_date(info)
    if y_date is not None and y_date > as_of:
        y_ss, y_spf, y_date = math.nan, math.nan, None
        flags.append("yahoo_si_futuro_descartado")
    elif y_date is not None and finra_publication_date(y_date) > as_of:
        # Liquidação <= as_of, mas ainda NÃO publicada em as_of (liquidação + 7 dias úteis):
        # usar seria look-ahead (snapshots reconstruídos com as_of passado).
        y_ss, y_spf, y_date = math.nan, math.nan, None
        flags.append("yahoo_si_nao_publicado_descartado")
    float_base = math.nan
    if y_ss > 0 and 0 < y_spf <= 1:
        float_base = y_ss / y_spf
    elif not math.isnan(y_spf) and y_spf > 1:
        flags.append("spf_yahoo_implausivel")
    px = _price_from_info(info)
    mcap = to_float(info.get("marketCap"))
    implied = to_float(info.get("impliedSharesOutstanding"))
    if not implied > 0 and mcap > 0 and px > 0:
        implied = mcap / px
    if finra is not None and to_float(finra.get("shares_short")) >= 0:
        shares_short = to_float(finra.get("shares_short"))
        settle: date | None = finra.get("settlement_date")
        pub: date | None = finra.get("publication_date")
        prior = to_float(finra.get("shares_short_prior"))
        adv = to_float(finra.get("avg_daily_volume"))
        dtc = to_float(finra.get("days_to_cover"))
        source = "YAHOO/FINRA" if not math.isnan(float_base) else "FINRA"
        if y_date is not None and settle is not None and y_date != settle:
            flags.append("datas_finra_yahoo_diferentes")
    elif y_ss >= 0:
        shares_short = y_ss
        settle = y_date
        pub = finra_publication_date(y_date) if y_date else None
        prior = to_float(info.get("sharesShortPriorMonth"))
        adv, dtc = math.nan, to_float(info.get("shortRatio"))
        source = "YAHOO"
    else:
        return None
    pct_equiv = shares_short / implied if implied > 0 else math.nan
    if float_base > 0:
        spf = shares_short / float_base
        if spf > 1:
            flags.append("float_base_implausivel")
            spf = pct_equiv
            flags.append("pct_sobre_total")
    else:
        spf = pct_equiv
        if not math.isnan(spf):
            flags.append("pct_sobre_total")
    return {
        "shares_short": shares_short, "short_pct_float": spf, "short_ratio_days": dtc,
        "short_interest_date": settle.isoformat() if settle else math.nan, "source": source,
        "settlement_date": settle.isoformat() if settle else math.nan,
        "publication_date": pub.isoformat() if pub else math.nan,
        "shares_short_prior": prior, "avg_daily_volume": adv,
        "adr_ratio": adr_ratio, "float_base_yahoo": float_base,
        "short_pct_float_yahoo": y_spf if 0 < y_spf <= 1 else math.nan,
        "implied_shares_outstanding": implied, "short_pct_shares_equiv": pct_equiv,
        "si_quality": ";".join(flags) if flags else "OK",
    }


def short_interest_frame(rows: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    cols = SHORT_INTEREST_FIELDS + SHORT_INTEREST_EXTRA_FIELDS
    df = pd.DataFrame.from_dict({k: dict(v) for k, v in rows.items()}, orient="index")
    for c in cols:
        if c not in df.columns:
            df[c] = math.nan
    df = df[cols + sorted(c for c in df.columns if c not in cols)].sort_index()
    df.index.name = "ticker"
    text = {"short_interest_date", "source", "settlement_date", "publication_date", "si_quality"}
    for c in df.columns:
        if c in text:
            df[c] = df[c].astype(object).where(df[c].notna(), None)
        else:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def fetch_short_interest(tickers: Sequence[str], *, as_of: date | None = None,
                         adr_ratios: Mapping[str, float] | None = None,
                         ticker_factory: TickerFactory | None = None,
                         finra_fetcher: Callable[[Sequence[str], date], pd.DataFrame] | None = None,
                         use_finra: bool = True, max_workers: int = MAX_WORKERS,
                         sleep: Sleeper = time.sleep) -> pd.DataFrame:
    """Short interest por linha listada nos EUA (índice ticker; ``SHORT_INTEREST_FIELDS`` + extras).

    Fonte primária FINRA (liquidação + publicação, sem look-ahead em relação a ``as_of``); Yahoo
    ``info`` como base de float e fallback. Falha total da FINRA é tolerada (Yahoo); falha de
    ambas levanta :class:`FetchError`.
    """
    ref = as_of or datetime.now(UTC).date()
    us = sorted({t for t in tickers if listing_market(t) == "US"})
    if not us:
        return short_interest_frame({})
    ratios = {str(k): to_float(v) for k, v in (adr_ratios or {}).items()}
    finra_map: dict[str, dict] = {}
    finra_error: Exception | None = None
    if use_finra:
        fetch = finra_fetcher or (lambda syms, d: fetch_finra_short_interest(syms, d, sleep=sleep))
        try:
            fdf = fetch([finra_symbol(t) for t in us], ref)
            finra_map = {str(r["finra_symbol"]): dict(r) for _, r in fdf.iterrows()}
        except Exception as exc:
            finra_error = exc
            log.warning("FINRA indisponível: %r", exc)
    infos = fetch_infos(us, ticker_factory=ticker_factory, max_workers=max_workers, sleep=sleep)
    if finra_error is not None and all(info is None for _, info in infos.values()):
        raise FetchError(f"Short interest indisponível (FINRA: {finra_error!r}; Yahoo sem dados).")
    rows = {}
    for t in us:
        _, info = infos[t]
        row = build_short_interest_row(t, info, finra_map.get(finra_symbol(t)),
                                       ratios.get(t, math.nan), ref)
        if row is not None:
            rows[t] = row
    return short_interest_frame(rows)
