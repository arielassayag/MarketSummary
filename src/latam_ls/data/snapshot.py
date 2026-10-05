"""Snapshots imutáveis de dados de mercado com SHA-256 por arquivo.

Layout (docs/latam_ls/ARQUITETURA.md §4)::

    manifest.json            SnapshotManifest (hash de cada arquivo, fontes, limitações)
    universe.csv             cópia byte a byte do universo usado
    prices.parquet           longo: date, ticker, close, adj_close, volume, volume_flag
    fx.parquet               longo: date, currency, usd_per_unit (USD não é gravado)
    benchmarks.parquet       longo: date, symbol, close, adj_close
    rates.parquet            longo: date, series, value, source
    fundamentals.parquet     índice ticker (FUNDAMENTAL_FIELDS + extras de qualidade)
    short_interest.parquet   índice ticker (SHORT_INTEREST_FIELDS + extras FINRA)
    lending.parquet          índice ticker (LENDING_FIELDS + extras, B3/BTC; último pregão)
    lending_history.parquet  longo: date, ticker, ... (janela D-21 do BDI, que se perde)
    news.jsonl               NewsItem por linha (conteúdo NÃO confiável)
    qa.json                  relatório de qualidade (paridade ADR, volume suspeito, defasagem)

Regras: a pasta de destino precisa ser NOVA (nunca sobrescreve); a gravação é feita numa pasta
temporária ao lado e renomeada atomicamente; Parquet via pyarrow (zstd), colunas em ordem
determinística e linhas ordenadas; :func:`load_snapshot` recalcula todos os hashes e falha em
qualquer divergência. Fontes obrigatórias (preços, câmbio) com falha em mais de 20% dos
tickers/moedas abortam a construção; fontes opcionais (benchmarks, taxas, fundamentos, short
interest, aluguel, notícias) que falham viram limitação registrada no manifesto.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import DEFAULT_CONFIG_PATH, FundConfig, load_config
from ..contracts import NewsItem, SnapshotFile, SnapshotManifest, SourceRecord
from ..hashing import sha256_file
from ..market import FUNDAMENTAL_FIELDS, LENDING_FIELDS, SHORT_INTEREST_FIELDS, MarketData
from ..universe import REQUIRED_COLUMNS, Universe, listing_market, load_universe
from . import b3_lending, macro, news, yahoo

log = logging.getLogger(__name__)

DEFAULT_START = date(2019, 1, 2)
DEFAULT_SNAPSHOT_ROOT = Path("data/snapshots")
REQUIRED_FAILURE_THRESHOLD = 0.20
STALE_BDAYS = 5
EXTREME_MOVE = 0.35
ARS_PARITY_TOLERANCE = 0.05
PARITY_WINDOW = 20
FX_FFILL_LIMIT = 3
# Resolução canônica das datas = padrão do pandas instalado (us no pandas 3, ns no pandas 2).
DATETIME_DTYPE = pd.bdate_range("2020-01-01", periods=1).dtype

# Benchmarks/ETFs de referência (GXG não tem dados no Yahoo desde a troca para COLO).
BENCHMARKS = ["ILF", "EWZ", "EWW", "ECH", "COLO", "EPU", "ARGT", "^BVSP", "^MXX", "^MERV",
              "BOVA11.SA", "SPY", "EEM"]
# Indicadores de mercado para contexto/risco (futuros "front": saltos de rolagem possíveis).
MARKET_INDICATORS = ["^VIX", "DX-Y.NYB", "HG=F", "CL=F", "BZ=F", "GC=F", "SI=F"]

FILE_MANIFEST = "manifest.json"
FILE_UNIVERSE = "universe.csv"
FILE_PRICES = "prices.parquet"
FILE_FX = "fx.parquet"
FILE_BENCHMARKS = "benchmarks.parquet"
FILE_RATES = "rates.parquet"
FILE_FUNDAMENTALS = "fundamentals.parquet"
FILE_SHORT_INTEREST = "short_interest.parquet"
FILE_LENDING = "lending.parquet"
FILE_LENDING_HISTORY = "lending_history.parquet"
FILE_NEWS = "news.jsonl"
FILE_QA = "qa.json"

FILE_DESCRIPTIONS = {
    FILE_UNIVERSE: "Universo (emissores e linhas) usado no snapshot",
    FILE_PRICES: "Preços diários longos: close (ajuste só por desdobramento), adj_close "
                 "(proventos), volume (0 com preço => NaN + flag volume_suspeito)",
    FILE_FX: "Câmbio: USD por 1 unidade da moeda (USD=1 adicionado na leitura)",
    FILE_BENCHMARKS: "Fechamento nativo de ETFs/índices/indicadores de referência",
    FILE_RATES: "Taxas anuais em decimal (USD_3M, SELIC)",
    FILE_FUNDAMENTALS: "Fundamentos por linha (retrato atual, NÃO point-in-time)",
    FILE_SHORT_INTEREST: "Short interest de linhas nos EUA (FINRA/Yahoo; float do ADS)",
    FILE_LENDING: "Aluguel B3/BTC do último pregão disponível <= as_of",
    FILE_LENDING_HISTORY: "Aluguel B3/BTC diário da janela D-21 do BDI",
    FILE_NEWS: "Manchetes (Google News RSS) — conteúdo NÃO confiável",
    FILE_QA: "Relatório de qualidade: paridade ADR, volume suspeito, linhas defasadas",
}

PRICES_COLUMNS = yahoo.PRICE_COLUMNS
FX_COLUMNS = yahoo.FX_COLUMNS
BENCHMARK_COLUMNS = yahoo.BENCHMARK_COLUMNS
RATES_COLUMNS = macro.RATES_COLUMNS

STANDARD_LIMITATIONS = [
    "Viés de sobrevivência: o universo foi definido na data de criação (não é point-in-time); "
    "emissores deslistados antes dessa data não aparecem no histórico.",
    "Fundamentos (Yahoo Ticker.info) são retrato atual, NÃO point-in-time; múltiplos podem "
    "misturar moedas/classes — ver coluna fundamentals_quality.",
    "Adj Close do Yahoo é ajustado retroativamente por proventos/desdobramentos e muda a cada "
    "novo evento; o hash é por snapshot.",
    "Câmbio do Yahoo (=X) usa barras diárias carimbadas em Europe/London, normalizadas para a "
    "data do pregão; não é fixing oficial (PTAX/FIX/TRM).",
    "Short interest de ADRs refere-se ao float do ADS (não ao float total da companhia) e é "
    "publicado pela FINRA com defasagem (liquidação + 7 dias úteis).",
    "Saldo de aluguel B3 (BTC) inclui arbitragem/ETF/hedge (limite superior do short); taxas sem "
    "contratos no dia são a última taxa calculada (rate_stale).",
    "Notícias (Google News RSS) são conteúdo NÃO confiável: usadas apenas como dado citado.",
]


class SnapshotError(RuntimeError):
    """Erro de construção de snapshot."""


class SnapshotIntegrityError(ValueError):
    """Hash ou estrutura do snapshot não confere (adulteração ou corrupção)."""


# ======================================================================
# Injeção de dependências (fetchers)
# ======================================================================

def _default_prices(tickers: Sequence[str], start: date, end: date
                    ) -> tuple[pd.DataFrame, list[str]]:
    return yahoo.fetch_price_history(tickers, start, end)


def _default_fx(currencies: Sequence[str], start: date, end: date) -> pd.DataFrame:
    return yahoo.fetch_fx_history(currencies, start, end)


def _default_benchmarks(symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
    return yahoo.fetch_benchmarks(symbols, start, end)


def _default_fundamentals(tickers: Sequence[str], currency_map: Mapping[str, str],
                          as_of: date) -> pd.DataFrame:
    return yahoo.fetch_fundamentals(tickers, currency_map=currency_map, as_of=as_of)


def _default_short_interest(tickers: Sequence[str], as_of: date,
                            adr_ratios: Mapping[str, float]) -> pd.DataFrame:
    return yahoo.fetch_short_interest(tickers, as_of=as_of, adr_ratios=adr_ratios)


def _default_lending(tickers: Sequence[str], start: date, end: date,
                     shares_outstanding: Mapping[str, float]) -> pd.DataFrame:
    return b3_lending.fetch_b3_lending(tickers, start, end, shares_outstanding=shares_outstanding)


def _default_rates(start: date, end: date) -> pd.DataFrame:
    return macro.fetch_rates(start, end)


def _default_news(queries: Sequence[news.NewsQuery], as_of: date, lookback_days: int
                  ) -> tuple[list[NewsItem], list[str]]:
    return news.fetch_news(queries, as_of, lookback_days)


@dataclass(frozen=True)
class Fetchers:
    """Funções de coleta (padrão = implementações reais); substituíveis em testes.

    Assinaturas:
    - ``prices(tickers, start, end) -> (longo, ausentes)``
    - ``fx(moedas, start, end) -> longo``; ``benchmarks(símbolos, start, end) -> longo``
    - ``fundamentals(tickers, mapa_moeda, as_of) -> índice ticker``
    - ``short_interest(tickers_eua, as_of, razões_adr) -> índice ticker``
    - ``lending(tickers_b3, start, end, ações_em_circulação) -> longo [date, ticker, ...]``
    - ``rates(start, end) -> longo``; ``news(consultas, as_of, lookback) -> (itens, falhas)``
    """

    prices: Callable[..., tuple[pd.DataFrame, list[str]]] = _default_prices
    fx: Callable[..., pd.DataFrame] = _default_fx
    benchmarks: Callable[..., pd.DataFrame] = _default_benchmarks
    fundamentals: Callable[..., pd.DataFrame] = _default_fundamentals
    short_interest: Callable[..., pd.DataFrame] = _default_short_interest
    lending: Callable[..., pd.DataFrame] = _default_lending
    rates: Callable[..., pd.DataFrame] = _default_rates
    news: Callable[..., Any] = _default_news


# ======================================================================
# Normalização de quadros (ordem de colunas e tipos determinísticos)
# ======================================================================

def _ensure_columns(df: pd.DataFrame | None, cols: Sequence[str]) -> pd.DataFrame:
    df = pd.DataFrame(columns=list(cols)) if df is None else df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    extras = sorted(c for c in df.columns if c not in cols)
    return df[list(cols) + extras]


def normalize_prices(df: pd.DataFrame | None) -> pd.DataFrame:
    df = _ensure_columns(df, PRICES_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).astype(DATETIME_DTYPE)
    df["ticker"] = df["ticker"].astype(str)
    for c in ("close", "adj_close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["volume_flag"] = df["volume_flag"].where(df["volume_flag"].notna(), "").astype(str)
    return df.sort_values(["date", "ticker"]).reset_index(drop=True)


def normalize_fx(df: pd.DataFrame | None) -> pd.DataFrame:
    df = _ensure_columns(df, FX_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).astype(DATETIME_DTYPE)
    df["currency"] = df["currency"].astype(str).str.upper()
    df["usd_per_unit"] = pd.to_numeric(df["usd_per_unit"], errors="coerce").astype(float)
    df = df[(df["currency"] != "USD") & df["usd_per_unit"].notna() & (df["usd_per_unit"] > 0)]
    return df.sort_values(["date", "currency"]).reset_index(drop=True)


def normalize_benchmarks(df: pd.DataFrame | None) -> pd.DataFrame:
    df = _ensure_columns(df, BENCHMARK_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).astype(DATETIME_DTYPE)
    df["symbol"] = df["symbol"].astype(str)
    for c in ("close", "adj_close"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df = df[df["close"].notna()]
    return df.sort_values(["date", "symbol"]).reset_index(drop=True)


def normalize_rates(df: pd.DataFrame | None) -> pd.DataFrame:
    df = _ensure_columns(df, RATES_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).astype(DATETIME_DTYPE)
    df["series"] = df["series"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype(float)
    df["source"] = df["source"].where(df["source"].notna(), "").astype(str)
    df = df[df["value"].notna()]
    return df.sort_values(["date", "series"]).reset_index(drop=True)


_TEXT_HINT = re.compile(r"(date|currency|source|sector|industry|quality|ticker|type|flag|_at|stale)$")


def normalize_indexed(df: pd.DataFrame | None, fields: Sequence[str]) -> pd.DataFrame:
    """Quadro indexado por ticker: campos canônicos primeiro, extras em ordem alfabética."""
    df = _ensure_columns(df, fields)
    df.index = pd.Index([str(i) for i in df.index], name="ticker")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s) or pd.api.types.is_numeric_dtype(s):
            continue
        num = pd.to_numeric(s, errors="coerce")
        if s.notna().sum() > 0 and num.notna().sum() == s.notna().sum() and not _TEXT_HINT.search(c):
            df[c] = num.astype(float)
        else:
            df[c] = s.astype(object).where(s.notna(), None)
    return df


def normalize_lending_history(df: pd.DataFrame | None) -> pd.DataFrame:
    df = _ensure_columns(df, b3_lending.LENDING_LONG_COLUMNS)
    df["date"] = pd.to_datetime(df["date"]).astype(DATETIME_DTYPE)
    df["ticker"] = df["ticker"].astype(str)
    for c in df.columns:
        if c in ("date", "ticker"):
            continue
        s = df[c]
        if c in ("lending_date", "source", "b3_ticker", "published_at", "lending_quality",
                 "rate_stale"):
            df[c] = s.astype(object).where(s.notna(), None)
        else:
            df[c] = pd.to_numeric(s, errors="coerce").astype(float)
    return df.sort_values(["date", "ticker"]).reset_index(drop=True)


# ======================================================================
# Gravação/leitura de arquivos
# ======================================================================

def _write_parquet(df: pd.DataFrame, path: Path) -> int:
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.date
    table = pa.Table.from_pandas(out, preserve_index=False)
    pq.write_table(table, path, compression="zstd", compression_level=9)
    return int(len(out))


def _read_parquet(path: Path) -> pd.DataFrame:
    df = pq.read_table(path).to_pandas()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).astype(DATETIME_DTYPE)
    return df


def _indexed_to_long(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index.name = "ticker"
    return out.reset_index()


def _long_to_indexed(df: pd.DataFrame) -> pd.DataFrame:
    if "ticker" not in df.columns:
        raise SnapshotIntegrityError("Quadro indexado sem coluna 'ticker'.")
    out = df.set_index("ticker")
    out.index.name = "ticker"
    for c in out.columns:
        if out[c].dtype == object or pd.api.types.is_string_dtype(out[c]):
            out[c] = out[c].astype(object).where(out[c].notna(), np.nan)
    return out


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    return obj


def write_news_jsonl(items: Sequence[NewsItem], path: Path) -> int:
    ordered = sorted(items, key=lambda n: (n.published_at, n.news_id))
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for it in ordered:
            f.write(json.dumps(it.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
            f.write("\n")
    return len(ordered)


def read_news_jsonl(path: Path) -> tuple[NewsItem, ...]:
    if not path.exists():
        return ()
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(NewsItem.model_validate_json(line))
    return tuple(sorted(out, key=lambda n: (n.published_at, n.news_id)))


def _universe_csv_bytes(universe: Universe) -> bytes:
    cols = REQUIRED_COLUMNS + ["notes"]
    lines = universe.lines.copy()
    if "yahoo_ticker" not in lines.columns:
        lines["yahoo_ticker"] = lines.index
    for c in cols:
        if c not in lines.columns:
            lines[c] = ""
    df = lines[cols].reset_index(drop=True)
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8")


@dataclass
class _Staged:
    files: list[SnapshotFile] = field(default_factory=list)


def _stage_file(staged: _Staged, root: Path, name: str, rows: int | None) -> None:
    staged.files.append(SnapshotFile(path=name, sha256=sha256_file(root / name), rows=rows,
                                     description=FILE_DESCRIPTIONS.get(name, "")))


def _write_dir(out_dir: Path, writer: Callable[[Path, _Staged], SnapshotManifest]
               ) -> SnapshotManifest:
    """Grava numa pasta temporária ao lado e renomeia atomicamente. Nunca sobrescreve."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"Destino já existe (snapshots são imutáveis): {out_dir}")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = out_dir.parent / f".{out_dir.name}.staging-{uuid.uuid4().hex[:10]}"
    staging.mkdir()
    try:
        staged = _Staged()
        manifest = writer(staging, staged)
        (staging / FILE_MANIFEST).write_text(manifest.model_dump_json(indent=2) + "\n",
                                             encoding="utf-8")
        if out_dir.exists():
            raise FileExistsError(f"Destino criado durante a gravação: {out_dir}")
        os.rename(staging, out_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


@dataclass(frozen=True)
class SnapshotTables:
    """Conteúdo bruto (formato longo/indexado) de um snapshot verificado."""

    path: Path
    manifest: SnapshotManifest
    universe: Universe
    prices: pd.DataFrame
    fx: pd.DataFrame
    benchmarks: pd.DataFrame
    rates: pd.DataFrame
    fundamentals: pd.DataFrame
    short_interest: pd.DataFrame
    lending: pd.DataFrame
    lending_history: pd.DataFrame
    news: tuple[NewsItem, ...]
    qa: dict[str, Any]


def write_tables(out_dir: Path, *, manifest_fields: Mapping[str, Any],
                 universe_bytes: bytes, prices: pd.DataFrame, fx: pd.DataFrame,
                 benchmarks: pd.DataFrame, rates: pd.DataFrame, fundamentals: pd.DataFrame,
                 short_interest: pd.DataFrame, lending: pd.DataFrame,
                 lending_history: pd.DataFrame | None, news_items: Sequence[NewsItem],
                 qa: Mapping[str, Any]) -> SnapshotManifest:
    """Grava o layout completo e devolve o manifesto (``files`` com sha256 e linhas)."""

    def writer(root: Path, staged: _Staged) -> SnapshotManifest:
        (root / FILE_UNIVERSE).write_bytes(universe_bytes)
        _stage_file(staged, root, FILE_UNIVERSE, None)
        tables: list[tuple[str, pd.DataFrame]] = [
            (FILE_PRICES, normalize_prices(prices)),
            (FILE_FX, normalize_fx(fx)),
            (FILE_BENCHMARKS, normalize_benchmarks(benchmarks)),
            (FILE_RATES, normalize_rates(rates)),
            (FILE_FUNDAMENTALS, _indexed_to_long(normalize_indexed(fundamentals,
                                                                   FUNDAMENTAL_FIELDS))),
            (FILE_SHORT_INTEREST, _indexed_to_long(normalize_indexed(short_interest,
                                                                     SHORT_INTEREST_FIELDS))),
            (FILE_LENDING, _indexed_to_long(normalize_indexed(lending, LENDING_FIELDS))),
        ]
        if lending_history is not None:
            tables.append((FILE_LENDING_HISTORY, normalize_lending_history(lending_history)))
        for name, df in tables:
            rows = _write_parquet(df, root / name)
            _stage_file(staged, root, name, rows)
        n_news = write_news_jsonl(list(news_items), root / FILE_NEWS)
        _stage_file(staged, root, FILE_NEWS, n_news)
        (root / FILE_QA).write_text(json.dumps(_json_safe(dict(qa)), ensure_ascii=False,
                                               sort_keys=True, indent=2) + "\n", encoding="utf-8")
        _stage_file(staged, root, FILE_QA, None)
        fields = dict(manifest_fields)
        fields["universe_sha256"] = sha256_file(root / FILE_UNIVERSE)
        fields["files"] = sorted(staged.files, key=lambda f: f.path)
        return SnapshotManifest(**fields)

    return _write_dir(out_dir, writer)


def read_manifest(path: Path) -> SnapshotManifest:
    p = Path(path) / FILE_MANIFEST
    if not p.exists():
        raise SnapshotIntegrityError(f"Manifesto ausente: {p}")
    return SnapshotManifest.model_validate_json(p.read_text(encoding="utf-8"))


def verify_files(root: Path, manifest: SnapshotManifest) -> None:
    """Recalcula o SHA-256 de cada arquivo listado; levanta em divergência."""
    root = Path(root)
    names = {f.path for f in manifest.files}
    for required in (FILE_UNIVERSE, FILE_PRICES, FILE_FX):
        if required not in names:
            raise SnapshotIntegrityError(f"Manifesto sem o arquivo obrigatório {required}.")
    for f in manifest.files:
        p = root / f.path
        if not p.exists():
            raise SnapshotIntegrityError(f"Arquivo do manifesto ausente: {p}")
        h = sha256_file(p)
        if h != f.sha256:
            raise SnapshotIntegrityError(
                f"Hash divergente em {p}: esperado {f.sha256[:12]}…, obtido {h[:12]}…")
    uni_hash = sha256_file(root / FILE_UNIVERSE)
    if uni_hash != manifest.universe_sha256:
        raise SnapshotIntegrityError("universe.csv não corresponde ao universe_sha256 do manifesto.")


def read_tables(path: Path, verify: bool = True) -> SnapshotTables:
    """Lê (e, por padrão, verifica) todos os arquivos de um snapshot."""
    root = Path(path)
    manifest = read_manifest(root)
    if verify:
        verify_files(root, manifest)
    names = {f.path for f in manifest.files}

    def opt(name: str) -> pd.DataFrame | None:
        return _read_parquet(root / name) if name in names and (root / name).exists() else None

    universe = load_universe(root / FILE_UNIVERSE)
    fund = opt(FILE_FUNDAMENTALS)
    si = opt(FILE_SHORT_INTEREST)
    lend = opt(FILE_LENDING)
    lh = opt(FILE_LENDING_HISTORY)
    qa: dict[str, Any] = {}
    if FILE_QA in names and (root / FILE_QA).exists():
        qa = json.loads((root / FILE_QA).read_text(encoding="utf-8"))
    return SnapshotTables(
        path=root, manifest=manifest, universe=universe,
        prices=normalize_prices(opt(FILE_PRICES)), fx=normalize_fx(opt(FILE_FX)),
        benchmarks=normalize_benchmarks(opt(FILE_BENCHMARKS)),
        rates=normalize_rates(opt(FILE_RATES)),
        fundamentals=_long_to_indexed(fund) if fund is not None
        else normalize_indexed(None, FUNDAMENTAL_FIELDS),
        short_interest=_long_to_indexed(si) if si is not None
        else normalize_indexed(None, SHORT_INTEREST_FIELDS),
        lending=_long_to_indexed(lend) if lend is not None
        else normalize_indexed(None, LENDING_FIELDS),
        lending_history=normalize_lending_history(lh),
        news=read_news_jsonl(root / FILE_NEWS) if FILE_NEWS in names else (),
        qa=qa,
    )


# ======================================================================
# Pivot longo -> largo e montagem do MarketData
# ======================================================================

def _pivot(df: pd.DataFrame, key: str, value: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(index=pd.DatetimeIndex([], dtype=DATETIME_DTYPE), dtype=float)
    wide = df.pivot(index="date", columns=key, values=value).sort_index()
    wide = wide.reindex(sorted(wide.columns), axis=1).astype(float)
    wide.index = pd.DatetimeIndex(wide.index).astype(DATETIME_DTYPE)
    wide.index.name = None
    wide.columns.name = None
    return wide


def prices_to_wide(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    p = normalize_prices(prices)
    if p.duplicated(["date", "ticker"]).any():
        raise SnapshotIntegrityError("Preços com (date, ticker) duplicados.")
    return _pivot(p, "ticker", "close"), _pivot(p, "ticker", "adj_close"), _pivot(p, "ticker",
                                                                                 "volume")


def fx_to_wide(fx: pd.DataFrame) -> pd.DataFrame:
    f = normalize_fx(fx)
    if f.duplicated(["date", "currency"]).any():
        raise SnapshotIntegrityError("Câmbio com (date, currency) duplicados.")
    wide = _pivot(f, "currency", "usd_per_unit")
    wide["USD"] = 1.0
    return wide


def assemble_market_data(manifest: SnapshotManifest, universe: Universe, prices: pd.DataFrame,
                         fx: pd.DataFrame, benchmarks: pd.DataFrame, rates: pd.DataFrame,
                         fundamentals: pd.DataFrame, short_interest: pd.DataFrame,
                         lending: pd.DataFrame, news_items: Sequence[NewsItem]) -> MarketData:
    close, adj, vol = prices_to_wide(prices)
    b = normalize_benchmarks(benchmarks)
    r = normalize_rates(rates)
    if r.duplicated(["date", "series"]).any():
        raise SnapshotIntegrityError("Taxas com (date, series) duplicados.")
    return MarketData(
        manifest=manifest, universe=universe, close=close, adj_close=adj, volume=vol,
        fx=fx_to_wide(fx), fundamentals=fundamentals, short_interest=short_interest,
        lending=lending, benchmarks=_pivot(b.drop_duplicates(["date", "symbol"], keep="last"),
                                           "symbol", "close"),
        rates=_pivot(r, "series", "value"),
        news=tuple(sorted(news_items, key=lambda n: (n.published_at, n.news_id))),
    )


def load_snapshot(path: Path, verify: bool = True) -> MarketData:
    """Carrega um snapshot (verificando todos os SHA-256 por padrão) como ``MarketData``."""
    t = read_tables(Path(path), verify=verify)
    return assemble_market_data(t.manifest, t.universe, t.prices, t.fx, t.benchmarks, t.rates,
                                t.fundamentals, t.short_interest, t.lending, t.news)


def snapshot_hash(path: Path, verify: bool = True) -> str:
    """Hash de conteúdo do snapshot (``SnapshotManifest.content_hash``), após verificação."""
    root = Path(path)
    manifest = read_manifest(root)
    if verify:
        verify_files(root, manifest)
    return manifest.content_hash()


_DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def latest_snapshot(root: Path = DEFAULT_SNAPSHOT_ROOT) -> Path | None:
    """Pasta ``YYYY-MM-DD`` mais recente que contém ``manifest.json`` (ou ``None``)."""
    root = Path(root)
    if not root.exists():
        return None
    cands = [p for p in root.iterdir()
             if p.is_dir() and _DATE_DIR.match(p.name) and (p / FILE_MANIFEST).exists()]
    return max(cands, key=lambda p: p.name) if cands else None


# ======================================================================
# Quadros largos -> longos (write_snapshot)
# ======================================================================

def wide_prices_to_long(close: pd.DataFrame, adj_close: pd.DataFrame,
                        volume: pd.DataFrame) -> pd.DataFrame:
    idx = close.index.union(adj_close.index).union(volume.index).sort_values()
    cols = sorted(set(close.columns) | set(adj_close.columns) | set(volume.columns))
    n_d, n_t = len(idx), len(cols)
    parts = {}
    for name, w in (("close", close), ("adj_close", adj_close), ("volume", volume)):
        parts[name] = w.reindex(index=idx, columns=cols).to_numpy(dtype=float).ravel()
    df = pd.DataFrame({"date": np.repeat(pd.DatetimeIndex(idx).to_numpy(), n_t),
                       "ticker": np.tile(np.array(cols, dtype=object), n_d), **parts})
    df = df[df[["close", "adj_close", "volume"]].notna().any(axis=1)]
    df["volume_flag"] = ""
    return normalize_prices(df)


def _wide_to_long(w: pd.DataFrame, key: str, value: str, drop: Sequence[str] = ()) -> pd.DataFrame:
    if w is None or w.empty:
        return pd.DataFrame(columns=["date", key, value])
    cols = [c for c in sorted(w.columns) if c not in drop]
    sub = w[cols]
    df = pd.DataFrame({"date": np.repeat(pd.DatetimeIndex(sub.index).to_numpy(), len(cols)),
                       key: np.tile(np.array(cols, dtype=object), len(sub.index)),
                       value: sub.to_numpy(dtype=float).ravel()})
    return df[df[value].notna()]


def write_snapshot(md: MarketData, out_dir: Path) -> SnapshotManifest:
    """Grava um ``MarketData`` (ex.: sintético) no layout de snapshot.

    O manifesto mantém ``snapshot_id``, ``as_of``, ``created_at``, fontes, limitações,
    ``is_synthetic`` e o aviso (``DADOS SIMULADOS`` quando sintético); ``files`` e
    ``universe_sha256`` passam a refletir os arquivos gravados.
    """
    m = md.manifest
    prices = wide_prices_to_long(md.close, md.adj_close, md.volume)
    fx = _wide_to_long(md.fx, "currency", "usd_per_unit", drop=("USD",))
    bench = _wide_to_long(md.benchmarks, "symbol", "close")
    bench["adj_close"] = np.nan
    rates = _wide_to_long(md.rates, "series", "value")
    rates["source"] = "SIMULADO" if m.is_synthetic else ""
    fields = {
        "snapshot_id": m.snapshot_id, "as_of": m.as_of, "created_at": m.created_at,
        "sources": list(m.sources), "limitations": list(m.limitations),
        "missing_tickers": list(m.missing_tickers), "is_synthetic": m.is_synthetic,
        "data_notice": m.data_notice,
    }
    return write_tables(
        Path(out_dir), manifest_fields=fields, universe_bytes=_universe_csv_bytes(md.universe),
        prices=prices, fx=fx, benchmarks=bench, rates=rates, fundamentals=md.fundamentals,
        short_interest=md.short_interest, lending=md.lending, lending_history=None,
        news_items=list(md.news), qa={"is_synthetic": m.is_synthetic,
                                      "data_notice": m.data_notice})


# ======================================================================
# Controle de qualidade (QA)
# ======================================================================

def adr_parity_report(close: pd.DataFrame, fx: pd.DataFrame, universe: Universe,
                      tolerance: float, ars_tolerance: float = ARS_PARITY_TOLERANCE,
                      window: int = PARITY_WINDOW) -> dict[str, Any]:
    """Paridade ADR × local: ``ADR / (local × razão × USD por unidade local)``.

    Para cada ADR com linha local do mesmo emissor, usa a linha local de menor desvio mediano
    (casa a classe correta em emissores multi-classe). Sinaliza quando ``|mediana 20d| > tol`` ou
    ``|último| > 2 × tol``. Para ARS, a referência é o CCL implícito (mediana cross-section dos
    desvios argentinos) e a tolerância é ``max(tol, 5%)``.
    """
    lines = universe.lines
    fxw = fx.copy()
    if "USD" not in fxw.columns:
        fxw["USD"] = 1.0
    fxw = fxw.reindex(close.index.union(fxw.index)).sort_index().ffill(limit=FX_FFILL_LIMIT)
    fxw = fxw.reindex(close.index)
    pairs: list[dict[str, Any]] = []
    for adr, row in lines[lines["line_type"] == "ADR"].iterrows():
        ratio = row.get("adr_ratio")
        if adr not in close.columns or not (isinstance(ratio, (int, float)) and ratio > 0):
            continue
        locals_ = lines[(lines["issuer_id"] == row["issuer_id"]) & (lines["line_type"] == "LOCAL")
                        & (lines["currency"] != "USD")]
        best: dict[str, Any] | None = None
        for loc, lrow in locals_.iterrows():
            ccy = lrow["currency"]
            if loc not in close.columns or ccy not in fxw.columns:
                continue
            parity = close[adr] / (close[loc] * float(ratio) * fxw[ccy])
            parity = parity.replace([np.inf, -np.inf], np.nan).dropna()
            if parity.empty:
                continue
            dev = parity - 1.0
            tail = dev.tail(window)
            cand = {"adr": adr, "local": loc, "currency": ccy, "adr_ratio": float(ratio),
                    "last_date": dev.index[-1].date().isoformat(),
                    "dev_last": float(dev.iloc[-1]), "dev_median": float(tail.median()),
                    "n_common": int(len(tail))}
            if best is None or abs(cand["dev_median"]) < abs(best["dev_median"]):
                best = cand
        if best is not None:
            pairs.append(best)
    ars = [p for p in pairs if p["currency"] == "ARS"]
    ccl_dev = float(np.median([p["dev_median"] for p in ars])) if ars else math.nan
    for p in pairs:
        if p["currency"] == "ARS":
            tol = max(tolerance, ars_tolerance)
            ref = ccl_dev if not math.isnan(ccl_dev) else 0.0
        else:
            tol, ref = tolerance, 0.0
        p["reference_dev"] = ref
        p["tolerance"] = tol
        p["flagged"] = bool(abs(p["dev_median"] - ref) > tol or abs(p["dev_last"] - ref) > 2 * tol)
    pairs.sort(key=lambda p: p["adr"])
    return {"pairs": pairs, "ars_implied_ccl_premium": (1.0 / (1.0 + ccl_dev) - 1.0)
            if not math.isnan(ccl_dev) else None}


def quality_report(prices: pd.DataFrame, fx: pd.DataFrame, universe: Universe, as_of: date,
                   cfg: FundConfig, missing: Sequence[str]) -> tuple[dict[str, Any], list[str]]:
    """QA do histórico de preços; devolve (relatório, limitações em pt-BR)."""
    p = normalize_prices(prices)
    close, adj, _ = prices_to_wide(p)
    fxw = fx_to_wide(fx)
    lim: list[str] = []
    sus = p[p["volume_flag"] == yahoo.VOLUME_SUSPECT_FLAG].groupby("ticker").size()
    sus = {str(k): int(v) for k, v in sus.sort_index().items()}
    if sus:
        top = ", ".join(f"{k} ({v})" for k, v in sorted(sus.items(), key=lambda kv: -kv[1])[:8])
        lim.append(f"Volume zero com preço válido tratado como AUSENTE (NaN + volume_suspeito): "
                   f"{sum(sus.values())} observações em {len(sus)} linhas; maiores: {top}.")
    cutoff = pd.Timestamp(as_of) - pd.offsets.BDay(STALE_BDAYS)
    last = close.apply(lambda s: s.last_valid_index()) if not close.empty else pd.Series(dtype=object)
    stale = sorted(str(t) for t, d in last.items() if d is not None and pd.notna(d) and d < cutoff)
    if stale:
        lim.append(f"Linhas sem preço nos últimos {STALE_BDAYS} pregões (defasadas): "
                   f"{', '.join(stale)}.")
    rets = adj.pct_change(fill_method=None)
    extreme = (rets.abs() > EXTREME_MOVE).sum()
    extreme = {str(k): int(v) for k, v in extreme[extreme > 0].sort_index().items()}
    if extreme:
        lim.append(f"Retornos diários > {EXTREME_MOVE:.0%} em módulo (revisar eventos "
                   f"corporativos): {', '.join(f'{k} ({v})' for k, v in extreme.items())}.")
    parity = adr_parity_report(close, fxw, universe, cfg.squeeze.adr_parity_tolerance)
    flagged = [x for x in parity["pairs"] if x["flagged"]]
    for x in flagged:
        lim.append(f"QA paridade ADR: {x['adr']} vs {x['local']} desvio mediano "
                   f"{x['dev_median']:+.1%} (último {x['dev_last']:+.1%}; referência "
                   f"{x['reference_dev']:+.1%}; tolerância {x['tolerance']:.0%}).")
    if parity.get("ars_implied_ccl_premium") is not None:
        lim.append(f"Argentina: CCL implícito nas paridades ADR ≈ "
                   f"{parity['ars_implied_ccl_premium']:+.1%} vs câmbio oficial (ARS=X); "
                   "preços locais em ARS embutem o CCL.")
    if missing:
        lim.append(f"Tickers sem dados na fonte (ausentes/renomeados): {', '.join(missing)}.")
    report = {
        "as_of": as_of.isoformat(), "n_lines_with_prices": int(close.shape[1]),
        "n_price_rows": int(len(p)), "first_date": p["date"].min().date().isoformat()
        if len(p) else None, "last_date": p["date"].max().date().isoformat() if len(p) else None,
        "missing_tickers": sorted(missing), "volume_suspect_by_ticker": sus,
        "stale_tickers": stale, "extreme_moves_by_ticker": extreme, "adr_parity": parity,
        "lines_by_market": {m: int(n) for m, n in sorted(
            pd.Series([listing_market(t) for t in close.columns]).value_counts().items())},
    }
    return report, lim


# ======================================================================
# Construção do snapshot real
# ======================================================================

def filter_news_as_of(items: Sequence[NewsItem], universe: Universe, as_of: date,
                      lookback_days: int) -> list[NewsItem]:
    """Defesa em profundidade contra look-ahead: mantém só itens dentro da janela local.

    O limite superior é ``as_of 23:59:59`` no fuso do país de cada emissor citado (o mais
    permissivo entre eles); itens sem emissor conhecido usam o fuso de Nova York.
    """
    countries = universe.issuers["country"].to_dict()
    out = []
    for n in items:
        tzs = {news.NewsQuery(i, "", "", str(countries.get(i, "LATAM"))).locale[4]
               for i in n.issuer_ids} or {"America/New_York"}
        bounds = [news.window_bounds(as_of, lookback_days, tz) for tz in sorted(tzs)]
        lo = min(b[0] for b in bounds)
        hi = max(b[1] for b in bounds)
        if lo <= n.published_at <= hi:
            out.append(n)
    return out


def _src(source_id: str, name: str, url: str, fields: Sequence[str], at: datetime, pit: bool,
         notes: str = "") -> SourceRecord:
    return SourceRecord(source_id=source_id, name=name, url=url, fields=list(fields),
                        retrieved_at=at, point_in_time=pit, notes=notes)


def _cfg_or_default(cfg: FundConfig | None) -> FundConfig:
    if cfg is not None:
        return cfg
    return load_config() if DEFAULT_CONFIG_PATH.exists() else FundConfig()


def build_snapshot(universe_path: Path, out_dir: Path, as_of: date, start: date = DEFAULT_START,
                   cfg: FundConfig | None = None, fetchers: Fetchers | None = None,
                   include_news: bool = True, news_issuers: list[str] | None = None, *,
                   benchmarks: Sequence[str] | None = None,
                   now: Callable[[], datetime] | None = None) -> SnapshotManifest:
    """Coleta todas as fontes e grava um snapshot imutável em ``out_dir`` (que não pode existir).

    ``as_of`` = último pregão completo incluído (linhas com data > ``as_of`` são descartadas).
    Levanta :class:`SnapshotError` quando preços ou câmbio falham para mais de 20% dos
    tickers/moedas; falhas de fontes opcionais viram limitação no manifesto.
    """
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"Destino já existe (snapshots são imutáveis): {out_dir}")
    if start > as_of:
        raise ValueError("start precisa ser <= as_of.")
    cfg = _cfg_or_default(cfg)
    f = fetchers or Fetchers()
    clock = now or (lambda: datetime.now(UTC))
    universe_path = Path(universe_path)
    uni = load_universe(universe_path)
    tickers = uni.tickers
    lines = uni.lines
    ts_end = pd.Timestamp(as_of)
    limitations = list(STANDARD_LIMITATIONS)
    sources: list[SourceRecord] = []

    # 1) Preços (obrigatório)
    try:
        prices, missing = f.prices(tickers, start, as_of)
    except Exception as exc:
        raise SnapshotError(f"Fonte obrigatória de preços falhou: {exc!r}") from exc
    prices = normalize_prices(prices)
    prices = prices[prices["ticker"].isin(tickers) & (prices["date"] <= ts_end)
                    & (prices["date"] >= pd.Timestamp(start))]
    missing = sorted(set(missing or []) | (set(tickers) - set(prices["ticker"])))
    if len(missing) > REQUIRED_FAILURE_THRESHOLD * len(tickers):
        raise SnapshotError(f"Preços ausentes para {len(missing)}/{len(tickers)} tickers "
                            f"(> {REQUIRED_FAILURE_THRESHOLD:.0%}): {missing[:20]}")
    sources.append(_src("yahoo_prices", "Yahoo Finance (yfinance) — barras diárias",
                        "https://query1.finance.yahoo.com/v8/finance/chart/",
                        ["close", "adj_close", "volume"], clock(), True,
                        "auto_adjust=False; volume 0 com preço => NaN + flag volume_suspeito; "
                        "barras com data > as_of descartadas."))

    # 2) Câmbio (obrigatório)
    ccys = sorted(c for c in uni.currencies if c != "USD")
    try:
        fx = normalize_fx(f.fx(ccys, start, as_of))
    except Exception as exc:
        raise SnapshotError(f"Fonte obrigatória de câmbio falhou: {exc!r}") from exc
    fx = fx[fx["currency"].isin(ccys) & (fx["date"] <= ts_end) & (fx["date"] >= pd.Timestamp(start))]
    missing_ccy = sorted(set(ccys) - set(fx["currency"]))
    if ccys and len(missing_ccy) > REQUIRED_FAILURE_THRESHOLD * len(ccys):
        raise SnapshotError(f"Câmbio ausente para {missing_ccy} (> {REQUIRED_FAILURE_THRESHOLD:.0%}).")
    if missing_ccy:
        affected = sorted(t for t in tickers if lines.loc[t, "currency"] in missing_ccy)
        limitations.append(f"Câmbio ausente para {', '.join(missing_ccy)}: linhas sem conversão "
                           f"para USD: {', '.join(affected)}.")
    sources.append(_src("yahoo_fx", "Yahoo Finance — câmbio <CCY>=X (invertido: USD por unidade)",
                        "https://query1.finance.yahoo.com/v8/finance/chart/", ["usd_per_unit"],
                        clock(), True, "Barras em Europe/London normalizadas para a data."))

    # 3) Benchmarks (opcional)
    syms = list(benchmarks) if benchmarks is not None else BENCHMARKS + MARKET_INDICATORS
    try:
        bench = normalize_benchmarks(f.benchmarks(syms, start, as_of))
        bench = bench[(bench["date"] <= ts_end) & (bench["date"] >= pd.Timestamp(start))]
        miss_b = sorted(set(syms) - set(bench["symbol"]))
        if miss_b:
            limitations.append(f"Benchmarks sem dados: {', '.join(miss_b)}.")
        sources.append(_src("yahoo_benchmarks", "Yahoo Finance — ETFs, índices e indicadores",
                            "https://query1.finance.yahoo.com/v8/finance/chart/",
                            ["close", "adj_close"], clock(), True,
                            "Futuros 'front' (=F) têm saltos de rolagem."))
    except Exception as exc:
        bench = normalize_benchmarks(None)
        limitations.append(f"Benchmarks indisponíveis (fonte opcional): {exc!r}.")

    # 4) Taxas (opcional)
    try:
        rates = normalize_rates(f.rates(start, as_of))
        rates = rates[(rates["date"] <= ts_end) & (rates["date"] >= pd.Timestamp(start))]
        for s in ("USD_3M", "SELIC"):
            if s not in set(rates["series"]):
                limitations.append(f"Taxa {s} indisponível no snapshot.")
        sources.append(_src("rates", "BCB SGS 432 (Selic meta) + Yahoo ^IRX / FRED DGS3MO",
                            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados",
                            ["USD_3M", "SELIC"], clock(), True,
                            "Datas futuras da série 432 descartadas (sem look-ahead)."))
    except Exception as exc:
        rates = normalize_rates(None)
        limitations.append(f"Taxas indisponíveis (fonte opcional): {exc!r}.")

    # 5) Fundamentos (opcional)
    cmap = {t: str(lines.loc[t, "currency"]) for t in tickers}
    try:
        fund = normalize_indexed(f.fundamentals(tickers, cmap, as_of), FUNDAMENTAL_FIELDS)
        fund = fund[fund.index.isin(tickers)]
        n_bad = int((fund.get("fundamentals_quality") == "sem_dados").sum()) \
            if "fundamentals_quality" in fund.columns else 0
        if n_bad:
            limitations.append(f"Fundamentos sem dados no Yahoo para {n_bad} linhas.")
        sources.append(_src("yahoo_fundamentals", "Yahoo Finance — Ticker.info (retrato atual)",
                            "https://query1.finance.yahoo.com/v10/finance/quoteSummary/",
                            FUNDAMENTAL_FIELDS, clock(), False,
                            "dividend_yield normalizado para decimal; múltiplos sinalizados em "
                            "fundamentals_quality."))
    except Exception as exc:
        fund = normalize_indexed(None, FUNDAMENTAL_FIELDS)
        limitations.append(f"Fundamentos indisponíveis (fonte opcional): {exc!r}.")

    # 6) Short interest (opcional; linhas nos EUA)
    us = [t for t in tickers if listing_market(t) == "US"]
    ratios = {t: float(lines.loc[t, "adr_ratio"]) for t in us
              if pd.notna(lines.loc[t, "adr_ratio"])}
    try:
        si = normalize_indexed(f.short_interest(us, as_of, ratios), SHORT_INTEREST_FIELDS)
        si = si[si.index.isin(us)]
        miss_si = sorted(set(us) - set(si.index))
        if miss_si:
            limitations.append(f"Short interest ausente para {len(miss_si)} linhas nos EUA: "
                               f"{', '.join(miss_si)}.")
        sources.append(_src("finra_yahoo_short_interest",
                            "FINRA consolidatedShortInterest + Yahoo (base de float do ADS)",
                            yahoo.FINRA_SI_URL, SHORT_INTEREST_FIELDS, clock(), False,
                            "Somente liquidações com publicação estimada <= as_of."))
    except Exception as exc:
        si = normalize_indexed(None, SHORT_INTEREST_FIELDS)
        limitations.append(f"Short interest indisponível (fonte opcional): {exc!r}.")

    # 7) Aluguel B3 (opcional; janela D-21)
    br = [t for t in tickers if listing_market(t) == "BR"]
    so_map = {}
    if "shares_outstanding" in fund.columns:
        so_map = {t: float(v) for t, v in fund["shares_outstanding"].items()
                  if t in br and pd.notna(v)}
    try:
        lh = normalize_lending_history(f.lending(br, b3_lending.lending_window_start(as_of),
                                                 as_of, so_map))
        lh = lh[lh["date"] <= ts_end]
        lend = normalize_indexed(b3_lending.latest_lending(lh, as_of), LENDING_FIELDS)
        if lend.empty:
            limitations.append("Aluguel B3 (BTC) sem dados na janela D-21 do BDI.")
        else:
            last_l = str(lh["date"].max().date())
            if last_l != as_of.isoformat():
                limitations.append(f"Aluguel B3 mais recente disponível é de {last_l} "
                                   f"(as_of {as_of.isoformat()}).")
        sources.append(_src("b3_bdi_lending", "B3 Boletim Diário (BDI) — BTBLendingOpenPosition "
                            "+ BTBLoanBalance", b3_lending.BDI_TABLE_URL, LENDING_FIELDS, clock(),
                            False, "Janela móvel D-21; coleta diária necessária."))
    except Exception as exc:
        lh = normalize_lending_history(None)
        lend = normalize_indexed(None, LENDING_FIELDS)
        limitations.append(f"Aluguel B3 (BTC) indisponível (fonte opcional): {exc!r}.")

    # 8) Notícias (opcional)
    items: list[NewsItem] = []
    if include_news:
        lookback = cfg.research.news_lookback_days
        queries = news.queries_from_universe(uni, news_issuers)
        try:
            res = f.news(queries, as_of, lookback)
            items, failed = (res if isinstance(res, tuple) else (res, []))
            items = news.dedupe_news(filter_news_as_of(items, uni, as_of, lookback))
            if failed:
                limitations.append(f"Notícias indisponíveis para {len(failed)} emissores.")
            sources.append(_src("google_news_rss", "Google News RSS (conteúdo NÃO confiável)",
                                news.GOOGLE_NEWS_RSS, ["title", "source", "url", "published_at"],
                                clock(), False, f"Janela de {lookback} dias até as_of 23:59 "
                                "local; itens futuros excluídos."))
        except Exception as exc:
            items = []
            limitations.append(f"Notícias indisponíveis (fonte opcional): {exc!r}.")
    else:
        limitations.append("Notícias não coletadas neste snapshot (include_news=False).")

    qa, qa_lim = quality_report(prices, fx, uni, as_of, cfg, missing)
    limitations.extend(qa_lim)
    fields = {
        "snapshot_id": f"snapshot-{as_of.isoformat()}", "as_of": as_of, "created_at": clock(),
        "sources": sources, "limitations": limitations, "missing_tickers": missing,
        "is_synthetic": False,
        "data_notice": "Dados reais de fontes públicas gratuitas (Yahoo, FINRA, B3/BDI, BCB, "
                       "Google News); uso de pesquisa — não é feed licenciado.",
    }
    return write_tables(out_dir, manifest_fields=fields, universe_bytes=universe_path.read_bytes(),
                        prices=prices, fx=fx, benchmarks=bench, rates=rates, fundamentals=fund,
                        short_interest=si, lending=lend, lending_history=lh, news_items=items,
                        qa=qa)
