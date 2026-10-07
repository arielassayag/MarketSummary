"""Barra intradiária PROVISÓRIA: todo dado disponível até o momento da análise.

Na segunda-feira (ou primeiro pregão da semana) a decisão é tomada ANTES do fechamento usando
também os preços e o câmbio do momento. Este módulo:

- coleta o último preço (atrasado pela fonte) de cada linha e de cada moeda;
- grava as cotações em arquivo com hash (para que a etapa ``decide`` reproduza exatamente o
  mesmo conjunto de dados da etapa ``prepare``);
- sobrepõe uma barra provisória ao ``MarketData`` do pregão anterior, marcada no manifesto
  (``provisional_dates``/``provisional_as_of``). Volume parcial NÃO entra (fica ``NaN``) para não
  subestimar a liquidez; o fechamento oficial substitui a barra na rotina diária.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..contracts import SnapshotFile
from ..hashing import sha256_file
from ..market import MarketData

USER_AGENT = "Mozilla/5.0 (CDP-Cabra-da-Peste; pesquisa)"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=5m"
MAX_WORKERS = 8


def _http_json(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_quote(symbol: str, getter: Callable[[str], dict] = _http_json,
                retries: int = 3) -> dict | None:
    """Último preço regular e horário da fonte; ``None`` se indisponível (nunca inventa)."""
    url = CHART_URL.format(sym=urllib.parse.quote(symbol, safe=""))
    for attempt in range(retries):
        try:
            data = getter(url)
            res = data["chart"]["result"][0]
            meta = res["meta"]
            price = meta.get("regularMarketPrice")
            ts = meta.get("regularMarketTime")
            if price is None or ts is None or not np.isfinite(float(price)) or float(price) <= 0:
                return None
            return {"symbol": symbol, "price": float(price),
                    "time": datetime.fromtimestamp(int(ts), UTC).isoformat(),
                    "currency": meta.get("currency")}
        except Exception:  # noqa: BLE001 - rede/formato: tenta de novo e depois desiste
            time.sleep(0.5 * (2 ** attempt))
    return None


def fetch_intraday_quotes(tickers: list[str], currencies: list[str],
                          benchmarks: list[str] | None = None,
                          getter: Callable[[str], dict] = _http_json) -> pd.DataFrame:
    """Cotações do momento para linhas, benchmarks e moedas (``<CCY>=X`` → USD por unidade)."""
    fx_syms = {f"{c}=X": c for c in currencies if c != "USD"}
    bench = list(benchmarks or [])
    symbols = list(tickers) + bench + list(fx_syms)
    with ThreadPoolExecutor(MAX_WORKERS) as pool:
        rows = list(pool.map(lambda s: fetch_quote(s, getter), symbols))
    out = []
    for sym, row in zip(symbols, rows, strict=True):
        if row is None:
            kind = "fx" if sym in fx_syms else ("bench" if sym in bench else "line")
            out.append({"symbol": fx_syms.get(sym, sym), "kind": kind, "price": np.nan,
                        "time": None})
            continue
        if sym in fx_syms:
            out.append({"symbol": fx_syms[sym], "kind": "fx", "price": 1.0 / row["price"],
                        "time": row["time"]})
        elif sym in bench:
            out.append({"symbol": sym, "kind": "bench", "price": row["price"], "time": row["time"]})
        else:
            out.append({"symbol": sym, "kind": "line", "price": row["price"], "time": row["time"]})
    return pd.DataFrame(out)


def save_quotes(quotes: pd.DataFrame, path: Path, captured_at: datetime) -> str:
    """Grava as cotações (parquet) e devolve o SHA-256; recusa sobrescrever."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Cotações intradiárias já gravadas: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df = quotes.copy()
    df["captured_at"] = captured_at.astimezone(UTC).isoformat()
    df.sort_values(["kind", "symbol"]).reset_index(drop=True).to_parquet(path, index=False)
    return sha256_file(path)


def load_quotes(path: Path, expected_sha256: str | None = None) -> tuple[pd.DataFrame, datetime]:
    path = Path(path)
    if expected_sha256 is not None and sha256_file(path) != expected_sha256:
        raise ValueError(f"Hash divergente nas cotações intradiárias: {path}")
    df = pd.read_parquet(path)
    captured = datetime.fromisoformat(str(df["captured_at"].iloc[0]))
    return df.drop(columns=["captured_at"]), captured


def fresh_quotes(quotes: pd.DataFrame, session: date,
                 tz: str = "America/Sao_Paulo") -> tuple[pd.DataFrame, list[str]]:
    """Mantém só cotações com horário no dia ``session`` (fuso de Brasília).

    Uma linha que ainda não negociou hoje devolve o último fechamento com o horário antigo; usá-lo
    criaria um retorno zero falso na barra provisória. Sem horário ⇒ descartada também.
    """
    if quotes.empty:
        return quotes, []
    t = pd.to_datetime(quotes["time"], utc=True, errors="coerce")
    local = t.dt.tz_convert(tz).dt.date
    ok = local == session
    stale = sorted(quotes.loc[~ok & quotes["price"].notna(), "symbol"].astype(str))
    return quotes.loc[ok].copy(), stale


MIN_FRESH_LINE_SHARE = 0.5
"""Fração mínima de linhas com cotação do dia para a barra provisória valer."""


def intraday_collection_failure(quotes: pd.DataFrame, session: date,
                                currencies: list[str] | None = None) -> str | None:
    """Motivo pelo qual a coleta intradiária NÃO serve para a barra provisória (ou ``None``).

    Rede ou fonte fora devolvem cotações vazias; sobrepor uma barra vazia apagaria o pregão
    do modelo de risco. Exige câmbio do dia para toda moeda e cotação do dia para ao menos
    metade das linhas; senão a análise usa o fechamento do pregão anterior (sem barra
    provisória) e a falha fica registrada como falha de coleta.
    """
    fresh, _stale = fresh_quotes(quotes, session)
    fresh = fresh[fresh["price"].notna()] if not fresh.empty else fresh
    n_lines = int((quotes["kind"] == "line").sum()) if not quotes.empty else 0
    n_fresh = int((fresh["kind"] == "line").sum()) if not fresh.empty else 0
    fx_ok = set(fresh.loc[fresh["kind"] == "fx", "symbol"].astype(str)) if not fresh.empty else set()
    fx_missing = sorted(c for c in (currencies or []) if c != "USD" and c not in fx_ok)
    motivos = []
    if n_lines and n_fresh < MIN_FRESH_LINE_SHARE * n_lines:
        motivos.append(f"{n_fresh} de {n_lines} linhas com cotação do dia")
    if fx_missing:
        motivos.append("câmbio do dia ausente para " + ", ".join(fx_missing))
    if not motivos:
        return None
    return ("Cotações intradiárias: falha de coleta (" + "; ".join(motivos) + "); a análise "
            "usa o fechamento do pregão anterior, sem barra provisória.")


def overlay_intraday(md: MarketData, session: date, quotes: pd.DataFrame,
                     captured_at: datetime, quotes_path: str = "",
                     quotes_sha256: str = "") -> MarketData:
    """Acrescenta a barra provisória de ``session`` ao ``MarketData`` do pregão anterior.

    ``adj_close`` provisório = ``adj_close`` anterior × (preço atual / ``close`` anterior), para
    manter o retorno total coerente. Linhas sem cotação ficam ``NaN`` (não negociaram ainda ou
    fonte indisponível). Volume provisório = ``NaN``.
    """
    if session <= md.as_of:
        raise ValueError(f"A barra provisória ({session}) precisa ser posterior ao snapshot "
                         f"({md.as_of}).")
    ts = pd.Timestamp(session)
    quotes, stale = fresh_quotes(quotes, session)
    lines = quotes[quotes["kind"] == "line"].set_index("symbol")["price"]
    fxq = quotes[quotes["kind"] == "fx"].set_index("symbol")["price"]

    def add_row(df: pd.DataFrame, values: pd.Series) -> pd.DataFrame:
        row = pd.DataFrame([values.reindex(df.columns)], index=pd.DatetimeIndex([ts]))
        return pd.concat([df, row.astype(float)])

    last_close = md.close.ffill().iloc[-1]
    last_adj = md.adj_close.ffill().iloc[-1]
    price = lines.reindex(md.close.columns).astype(float)
    ratio = price / last_close
    adj = last_adj * ratio
    fx_row = md.fx.iloc[-1].copy() * np.nan
    for ccy, v in fxq.items():
        if ccy in fx_row.index:
            fx_row[ccy] = float(v)
    if "USD" in fx_row.index:
        fx_row["USD"] = 1.0
    files = list(md.manifest.files)
    if quotes_sha256:
        files.append(SnapshotFile(path=quotes_path or f"intraday/{session.isoformat()}.parquet",
                                  sha256=quotes_sha256, rows=int(len(quotes)),
                                  description="Cotações intradiárias provisórias"))
    bq = quotes[quotes["kind"] == "bench"].set_index("symbol")["price"]
    manifest = md.manifest.model_copy(update={
        "as_of": session,
        "files": files,
        "provisional_dates": sorted({*md.manifest.provisional_dates, session}),
        "provisional_as_of": captured_at.astimezone(UTC),
        "limitations": list(md.manifest.limitations) + [
            f"Barra intradiária PROVISÓRIA de {session.isoformat()} capturada em "
            f"{captured_at.astimezone(UTC).isoformat()} (preços atrasados da fonte; volume "
            "parcial descartado)."] + ([
            f"Cotações sem negócio em {session.isoformat()} descartadas (ficam ausentes, nunca "
            f"repetidas): {len(stale)} símbolo(s)."] if stale else []),
    })
    return replace(
        md, manifest=manifest, close=add_row(md.close, price), adj_close=add_row(md.adj_close, adj),
        volume=add_row(md.volume, pd.Series(np.nan, index=md.volume.columns)),
        fx=add_row(md.fx, fx_row),
        benchmarks=add_row(md.benchmarks, bq.reindex(md.benchmarks.columns).astype(float)),
        rates=md.rates,
    )
