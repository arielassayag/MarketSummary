"""Aluguel de ações na B3 (BTC) via API do Boletim Diário (BDI).

Endpoint verificado em 2026-10-05 (docs/research/06_fontes_dados_ferramentas.md §4.2)::

    POST https://arquivos.b3.com.br/bdi/table/{Tabela}/{YYYY-MM-DD}/{YYYY-MM-DD}/{página}/{take}
    corpo JSON {} ; take <= 1000 (acima disso: HTTP 400); paginação por ``table.pageCount``

Tabelas usadas:

- ``BTBLendingOpenPosition`` (posições em aberto): ``StockBalance`` da linha ``Market == 'Total'``
  = saldo emprestado (ações).
- ``BTBLoanBalance`` (empréstimos registrados): ``QtyCtrctsDay`` (contratos no dia),
  ``ValCtrctsDay`` (rotulado "quantidade de ativos"), ``TkrMin/Avrg/MaxRate`` (fração ao ano;
  0,0516 = 5,16% a.a.). Sem contratos no dia, a B3 republica a última taxa calculada: a taxa é
  marcada como DEFASADA (``rate_stale``).

Semântica e limitações:

- Janela histórica móvel de ~21 pregões (D-21): a coleta precisa ser DIÁRIA, senão o histórico
  se perde. Publicação em D+1 até ~08:00 (BRT).
- O saldo BTC inclui arbitragem, ETF e hedge: é LIMITE SUPERIOR do short, não short interest.
- ``lending_pct_shares`` = saldo / ações da MESMA classe (``sharesOutstanding`` do Yahoo da linha
  ``.SA``) quando disponível; units (sufixo 11) têm base incerta e são sinalizadas.
- Nada é inventado: tabela vazia => sem linha; taxa ausente => NaN.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import pandas as pd

from ..market import LENDING_FIELDS
from .yahoo import FetchError, Sleeper, http_request, to_float

log = logging.getLogger(__name__)

BDI_TABLE_URL = "https://arquivos.b3.com.br/bdi/table/{table}/{d}/{d}/{page}/{take}"
OPEN_POSITION_TABLE = "BTBLendingOpenPosition"
LOAN_BALANCE_TABLE = "BTBLoanBalance"
MAX_TAKE = 1000
MAX_PAGES = 60
B3_SOURCE = "B3/BDI"
LENDING_EXTRA_FIELDS = [
    "b3_ticker", "lending_rate_min", "lending_rate_max", "contracts_day", "shares_lent_day",
    "rate_stale", "lent_value_brl", "published_at", "lending_quality",
]
LENDING_LONG_COLUMNS = ["date", "ticker"] + LENDING_FIELDS + LENDING_EXTRA_FIELDS


def yahoo_to_b3(ticker: str) -> str | None:
    t = ticker.strip().upper()
    return t[:-3] if t.endswith(".SA") else None


def b3_to_yahoo(b3_ticker: str) -> str:
    return f"{b3_ticker.strip().upper()}.SA"


def fetch_bdi_table(table: str, session_date: date, *, session: Any | None = None,
                    take: int = MAX_TAKE, max_pages: int = MAX_PAGES,
                    sleep: Sleeper = time.sleep) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Pagina uma tabela do BDI para um pregão. Tabela vazia (fora da janela D-21, feriado ou
    ainda não publicada) devolve DataFrame vazio. Erro HTTP levanta :class:`FetchError`."""
    if not 1 <= take <= MAX_TAKE:
        raise ValueError(f"take precisa estar entre 1 e {MAX_TAKE} (a API devolve 400 acima disso).")
    frames: list[pd.DataFrame] = []
    meta: dict[str, Any] = {}
    page = 1
    columns: list[str] = []
    while page <= max_pages:
        url = BDI_TABLE_URL.format(table=table, d=session_date.isoformat(), page=page, take=take)
        resp = http_request("POST", url, session=session, json={},
                            headers={"Content-Type": "application/json"}, sleep=sleep, timeout=60)
        if resp.status_code != 200:
            raise FetchError(f"BDI {table} {session_date}: HTTP {resp.status_code}")
        payload = resp.json() or {}
        tbl = payload.get("table") or {}
        if page == 1:
            columns = [str(c.get("name")) for c in (tbl.get("columns") or [])]
            meta = {"lastUpdateDate": payload.get("lastUpdateDate"),
                    "pageCount": tbl.get("pageCount"), "limitDate": tbl.get("limitDate"),
                    "columns": columns}
        values = tbl.get("values") or []
        if not values:
            break
        frames.append(pd.DataFrame(values, columns=columns))
        if page >= int(tbl.get("pageCount") or 1):
            break
        page += 1
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    return df, meta


def _rows_for_date(df: pd.DataFrame, session_date: date) -> pd.DataFrame:
    if df.empty or "RptDt" not in df.columns:
        return df
    d = pd.to_datetime(df["RptDt"], errors="coerce").dt.date
    return df[d == session_date]


def parse_lending(open_pos: pd.DataFrame, loans: pd.DataFrame, session_date: date, *,
                  tickers: Sequence[str] | None = None,
                  shares_outstanding: Mapping[str, float] | None = None,
                  published_at: str | None = None) -> pd.DataFrame:
    """Combina posição em aberto e empréstimos do dia em um quadro por ticker Yahoo.

    Índice = ticker Yahoo (``XXXX4.SA``); colunas = ``LENDING_FIELDS`` + extras.
    """
    wanted = None if tickers is None else {b for b in (yahoo_to_b3(t) for t in tickers) if b}
    so_map = {str(k): to_float(v) for k, v in (shares_outstanding or {}).items()}
    open_pos = _rows_for_date(open_pos, session_date)
    loans = _rows_for_date(loans, session_date)

    balances: dict[str, dict[str, float]] = {}
    if not open_pos.empty:
        tot = open_pos[open_pos["Market"].astype(str).str.strip().str.lower() == "total"]
        for _, r in tot.iterrows():
            b3 = str(r["TckrSymb"]).strip().upper()
            if wanted is not None and b3 not in wanted:
                continue
            balances[b3] = {"lent_shares": to_float(r.get("StockBalance")),
                            "lent_value_brl": to_float(r.get("Balance"))}

    rates: dict[str, dict[str, Any]] = {}
    if not loans.empty:
        for b3, g in loans.groupby(loans["TckrSymb"].astype(str).str.strip().str.upper()):
            if wanted is not None and b3 not in wanted:
                continue
            qty = pd.to_numeric(g["QtyCtrctsDay"], errors="coerce")
            shares = pd.to_numeric(g["ValCtrctsDay"], errors="coerce")
            avg = pd.to_numeric(g["TkrAvrgRate"], errors="coerce")
            contracts = float(qty.sum(min_count=1)) if qty.notna().any() else math.nan
            traded = (qty > 0) & avg.notna()
            if traded.any():
                w = shares.where(traded & (shares > 0))
                rate = float((avg[w.notna()] * w.dropna()).sum() / w.sum()) if w.notna().any() \
                    else float(avg[traded].mean())
                stale = False
                lo = pd.to_numeric(g.loc[traded, "TkrMinRate"], errors="coerce").min()
                hi = pd.to_numeric(g.loc[traded, "TkrMaxRate"], errors="coerce").max()
            else:
                rate = float(avg.dropna().iloc[0]) if avg.notna().any() else math.nan
                stale = True
                lo = pd.to_numeric(g["TkrMinRate"], errors="coerce").min()
                hi = pd.to_numeric(g["TkrMaxRate"], errors="coerce").max()
            rates[b3] = {"lending_rate_annual": rate, "lending_rate_min": to_float(lo),
                         "lending_rate_max": to_float(hi), "contracts_day": contracts,
                         "shares_lent_day": float(shares.sum(min_count=1))
                         if shares.notna().any() else math.nan,
                         "rate_stale": stale}

    rows: dict[str, dict[str, Any]] = {}
    for b3 in sorted(set(balances) | set(rates)):
        yt = b3_to_yahoo(b3)
        bal = balances.get(b3, {})
        rt = rates.get(b3, {})
        lent = bal.get("lent_shares", math.nan)
        so = so_map.get(yt, math.nan)
        flags: list[str] = []
        pct = lent / so if (so > 0 and not math.isnan(lent)) else math.nan
        if math.isnan(pct):
            flags.append("sem_base_acoes")
        if b3.endswith("11"):
            flags.append("unit_base_incerta")
        if not bal:
            flags.append("sem_posicao_em_aberto")
        if not rt:
            flags.append("sem_taxa")
        elif rt.get("rate_stale"):
            flags.append("taxa_defasada")
        rows[yt] = {
            "lent_shares": lent, "lending_pct_shares": pct,
            "lending_rate_annual": rt.get("lending_rate_annual", math.nan),
            "lending_date": session_date.isoformat(), "source": B3_SOURCE, "b3_ticker": b3,
            "lending_rate_min": rt.get("lending_rate_min", math.nan),
            "lending_rate_max": rt.get("lending_rate_max", math.nan),
            "contracts_day": rt.get("contracts_day", math.nan),
            "shares_lent_day": rt.get("shares_lent_day", math.nan),
            "rate_stale": rt.get("rate_stale"),
            "lent_value_brl": bal.get("lent_value_brl", math.nan),
            "published_at": published_at, "lending_quality": ";".join(flags) if flags else "OK",
        }
    return lending_frame(rows)


def lending_frame(rows: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    cols = LENDING_FIELDS + LENDING_EXTRA_FIELDS
    df = pd.DataFrame.from_dict({k: dict(v) for k, v in rows.items()}, orient="index")
    for c in cols:
        if c not in df.columns:
            df[c] = math.nan
    df = df[cols + sorted(c for c in df.columns if c not in cols)].sort_index()
    df.index.name = "ticker"
    return _coerce_lending_types(df)


def _coerce_lending_types(df: pd.DataFrame) -> pd.DataFrame:
    text = {"lending_date", "source", "b3_ticker", "published_at", "lending_quality", "ticker"}
    for c in df.columns:
        if c in text:
            df[c] = df[c].astype(object).where(df[c].notna(), None)
        elif c == "rate_stale":
            df[c] = df[c].astype(object).where(df[c].notna(), None)
        elif c != "date":
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def empty_lending_long() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype=object) for c in LENDING_LONG_COLUMNS})
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_b3_lending_day(session_date: date, *, tickers: Sequence[str] | None = None,
                         shares_outstanding: Mapping[str, float] | None = None,
                         session: Any | None = None, sleep: Sleeper = time.sleep) -> pd.DataFrame:
    """Aluguel de um pregão (índice ticker). Vazio se o BDI não tiver dados para a data."""
    open_pos, m1 = fetch_bdi_table(OPEN_POSITION_TABLE, session_date, session=session, sleep=sleep)
    loans, m2 = fetch_bdi_table(LOAN_BALANCE_TABLE, session_date, session=session, sleep=sleep)
    published = m1.get("lastUpdateDate") or m2.get("lastUpdateDate")
    return parse_lending(open_pos, loans, session_date, tickers=tickers,
                         shares_outstanding=shares_outstanding,
                         published_at=str(published) if published else None)


def fetch_b3_lending(tickers: Sequence[str], start: date, end: date, *,
                     shares_outstanding: Mapping[str, float] | None = None,
                     session: Any | None = None, sleep: Sleeper = time.sleep) -> pd.DataFrame:
    """Histórico longo ``[date, ticker, LENDING_FIELDS..., extras]`` entre ``start`` e ``end``.

    Percorre os dias úteis (seg–sex); datas sem dados (feriado, fora da janela D-21 ou ainda não
    publicadas) são puladas. Se TODAS as requisições falharem por erro HTTP/rede, levanta
    ``RuntimeError`` (fonte indisponível) — nunca devolve valores inventados.
    """
    br = [t for t in tickers if yahoo_to_b3(t)]
    if not br or start > end:
        return empty_lending_long()
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    days = pd.bdate_range(start, end)
    for ts in days:
        d = ts.date()
        try:
            day = fetch_b3_lending_day(d, tickers=br, shares_outstanding=shares_outstanding,
                                       session=session, sleep=sleep)
        except (FetchError, ValueError, KeyError) as exc:
            errors.append(f"{d}: {exc}")
            log.warning("BDI indisponível em %s: %r", d, exc)
            continue
        if day.empty:
            continue
        day = day.reset_index()
        day.insert(0, "date", pd.Timestamp(d))
        frames.append(day)
    if errors and len(errors) == len(days):
        raise RuntimeError("Fonte de aluguel B3 (BDI) indisponível: " + "; ".join(errors[:3]))
    if not frames:
        return empty_lending_long()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df[LENDING_LONG_COLUMNS + sorted(c for c in df.columns if c not in LENDING_LONG_COLUMNS)]
    return _coerce_lending_types(df.sort_values(["date", "ticker"]).reset_index(drop=True))


def latest_lending(long_df: pd.DataFrame, as_of: date | None = None) -> pd.DataFrame:
    """Retrato por ticker: linha mais recente com ``date <= as_of`` (índice ticker)."""
    if long_df is None or long_df.empty:
        return lending_frame({})
    df = long_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    if as_of is not None:
        df = df[df["date"] <= pd.Timestamp(as_of)]
    if df.empty:
        return lending_frame({})
    df = df.sort_values(["ticker", "date"]).groupby("ticker", as_index=False).tail(1)
    out = df.drop(columns=["date"]).set_index("ticker")
    cols = LENDING_FIELDS + LENDING_EXTRA_FIELDS
    out = out[cols + sorted(c for c in out.columns if c not in cols)].sort_index()
    out.index.name = "ticker"
    return _coerce_lending_types(out)


def lending_window_start(as_of: date, sessions: int = 21) -> date:
    """Primeiro dia útil da janela D-21 do BDI (aproximação por dias úteis seg–sex)."""
    return (pd.Timestamp(as_of) - pd.offsets.BDay(sessions + 2)).date()


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


__all__ = [
    "B3_SOURCE", "LENDING_EXTRA_FIELDS", "LENDING_LONG_COLUMNS", "fetch_b3_lending",
    "fetch_b3_lending_day", "fetch_bdi_table", "latest_lending", "lending_frame",
    "lending_window_start", "parse_lending", "parse_published_at",
]
