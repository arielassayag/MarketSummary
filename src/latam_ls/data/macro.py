"""Taxas de juros de referência (decimal anual) para financiamento e contexto macro.

Séries gravadas em formato longo ``[date, series, value, source]``:

- ``USD_3M``: T-bill de 13 semanas (Yahoo ``^IRX``, cotado em % → /100). Fallback: FRED
  ``DGS3MO`` via ``fredgraph.csv`` (uma série por requisição; vários ``id`` devolvem ZIP).
- ``SELIC``: meta Selic (BCB SGS 432, % a.a. → /100). A série 432 é preenchida em dias corridos
  ATÉ A PRÓXIMA REUNIÃO (devolve datas futuras): linhas com data > ``end`` são descartadas — sem
  look-ahead. O SGS limita consultas diárias a 10 anos: a coleta é fatiada.

Valores ausentes (``.``, ``n.d.``, vazio) são descartados, nunca convertidos em zero.
"""

from __future__ import annotations

import io
import logging
import math
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pandas as pd

from .yahoo import Downloader, FetchError, Sleeper, download_bars, http_request, to_float

log = logging.getLogger(__name__)

SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SELIC_TARGET_SGS = 432
USD_3M_YAHOO = "^IRX"
USD_3M_FRED = "DGS3MO"
SGS_MAX_WINDOW_DAYS = 3650
RATES_COLUMNS = ["date", "series", "value", "source"]


def empty_rates() -> pd.DataFrame:
    """Quadro de taxas vazio com o esquema canônico."""
    df = pd.DataFrame({c: pd.Series(dtype=object) for c in RATES_COLUMNS})
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = df["value"].astype(float)
    return df


def fetch_sgs_series(code: int, start: date, end: date, *, session: Any | None = None,
                     sleep: Sleeper = time.sleep) -> pd.Series:
    """Série do BCB SGS como publicada (índice = data, valor numérico), datas <= ``end``."""
    parts: list[pd.Series] = []
    cur = start
    while cur <= end:
        stop = min(end, cur + timedelta(days=SGS_MAX_WINDOW_DAYS - 1))
        resp = http_request("GET", SGS_URL.format(code=code), session=session, sleep=sleep,
                            params={"formato": "json", "dataInicial": cur.strftime("%d/%m/%Y"),
                                    "dataFinal": stop.strftime("%d/%m/%Y")})
        if resp.status_code == 404:  # janela sem observações
            cur = stop + timedelta(days=1)
            continue
        if resp.status_code != 200:
            raise FetchError(f"SGS {code}: HTTP {resp.status_code}")
        data = resp.json()
        if not isinstance(data, list):
            raise FetchError(f"SGS {code}: resposta inesperada ({str(data)[:120]})")
        idx, vals = [], []
        for item in data:
            try:
                d = pd.to_datetime(str(item.get("data")), format="%d/%m/%Y")
            except (TypeError, ValueError):
                continue
            v = to_float(str(item.get("valor", "")).replace(",", "."))
            if math.isnan(v):
                continue
            idx.append(d)
            vals.append(v)
        if idx:
            parts.append(pd.Series(vals, index=pd.DatetimeIndex(idx), dtype=float))
        cur = stop + timedelta(days=1)
    if not parts:
        return pd.Series(dtype=float)
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s[s.index <= pd.Timestamp(end)]


def fetch_fred_series(series_id: str, start: date, end: date, *, session: Any | None = None,
                      sleep: Sleeper = time.sleep, timeout: float = 20.0) -> pd.Series:
    """Série do FRED via ``fredgraph.csv`` (sem chave). ``.``/vazio => descartado."""
    resp = http_request("GET", FRED_CSV_URL, session=session, sleep=sleep, timeout=timeout,
                        params={"id": series_id, "cosd": start.isoformat(),
                                "coed": end.isoformat()})
    if resp.status_code != 200:
        raise FetchError(f"FRED {series_id}: HTTP {resp.status_code}")
    df = pd.read_csv(io.StringIO(resp.text), na_values=[".", ""], keep_default_na=True)
    if df.shape[1] < 2:
        raise FetchError(f"FRED {series_id}: CSV inesperado")
    dcol, vcol = df.columns[0], df.columns[1]
    s = pd.Series(pd.to_numeric(df[vcol], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df[dcol], errors="coerce"), dtype=float).dropna()
    s = s[s.index.notna()]
    return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))].sort_index()


def _long(series: pd.Series, name: str, source: str, scale: float) -> pd.DataFrame:
    s = series.dropna()
    return pd.DataFrame({"date": s.index, "series": name, "value": s.to_numpy(dtype=float) * scale,
                         "source": source})


def fetch_rates(start: date, end: date, *, downloader: Downloader | None = None,
                session: Any | None = None, use_fred_fallback: bool = True,
                sgs_fetcher: Callable[[int, date, date], pd.Series] | None = None,
                fred_fetcher: Callable[[str, date, date], pd.Series] | None = None,
                sleep: Sleeper = time.sleep) -> pd.DataFrame:
    """Taxas anuais em decimal, formato longo ``[date, series, value, source]``.

    Falhas parciais são toleradas (a série ausente simplesmente não aparece); se nenhuma série
    puder ser obtida, levanta :class:`FetchError`.
    """
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    try:
        bars, _ = download_bars([USD_3M_YAHOO], start, end, downloader=downloader, sleep=sleep)
        fr = bars.get(USD_3M_YAHOO)
        if fr is not None and fr["close"].notna().any():
            px = fr["close"][~fr.index.duplicated(keep="last")]
            frames.append(_long(px[px.index <= pd.Timestamp(end)], "USD_3M", "YAHOO:^IRX", 0.01))
        else:
            raise FetchError("^IRX sem dados")
    except Exception as exc:
        errors.append(f"USD_3M (^IRX): {exc}")
        if use_fred_fallback:
            try:
                fred = fred_fetcher or (lambda sid, a, b: fetch_fred_series(sid, a, b,
                                                                            session=session,
                                                                            sleep=sleep))
                s = fred(USD_3M_FRED, start, end)
                if not s.empty:
                    frames.append(_long(s, "USD_3M", f"FRED:{USD_3M_FRED}", 0.01))
            except Exception as exc2:
                errors.append(f"USD_3M (FRED): {exc2}")
    try:
        sgs = sgs_fetcher or (lambda code, a, b: fetch_sgs_series(code, a, b, session=session,
                                                                  sleep=sleep))
        s = sgs(SELIC_TARGET_SGS, start, end)
        s = s[s.index <= pd.Timestamp(end)]
        if s.empty:
            raise FetchError("SGS 432 sem dados")
        frames.append(_long(s, "SELIC", f"BCB:SGS{SELIC_TARGET_SGS}", 0.01))
    except Exception as exc:
        errors.append(f"SELIC (SGS 432): {exc}")
    if not frames:
        raise FetchError("Nenhuma taxa disponível: " + "; ".join(errors))
    for e in errors:
        log.warning("Taxa parcial: %s", e)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] <= pd.Timestamp(end)]
    return df.sort_values(["date", "series"]).reset_index(drop=True)[RATES_COLUMNS]
