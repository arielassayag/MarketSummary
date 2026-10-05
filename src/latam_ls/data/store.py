"""Repositório de mercado para o track record DIÁRIO auditável (base imutável + incrementos).

Layout::

    root/base/<as_of>/            snapshot completo (build_snapshot) com o histórico até as_of
    root/daily/<YYYY-MM-DD>/      incremento de UM pregão:
        prices.parquet            linhas com date == pregão (+ prev_date/prev_close_window/
                                  prev_adj_close_window: barra anterior vista na MESMA coleta,
                                  usada para encadear o retorno total sem perder proventos)
        fx.parquet, benchmarks.parquet, rates.parquet   linhas com date == pregão
        lending.parquet           aluguel B3 (longo) de todos os pregões ainda não gravados
                                  (o BDI publica D+1 e guarda só ~21 pregões)
        fundamentals.parquet, short_interest.parquet, news.jsonl   OPCIONAIS (refresh_slow)
        qa.json                   revisões detectadas, paridade ADR, mercados fechados
        manifest.json             IncrementManifest com sha256 de cada arquivo e
                                  prev_manifest_hash (encadeia ao incremento anterior ou ao
                                  content_hash da base)

Garantias:

- Arquivos da base nunca são alterados; incrementos são imutáveis (pasta nova, gravação
  atômica). Recusa: incremento já existente, data <= última gravada, pregão ainda não fechado,
  pregões intermediários não gravados (use :meth:`MarketStore.catch_up`) e dia sem nenhuma
  negociação. Feriado local com câmbio/EUA abertos vira incremento com zero linhas de preço e
  nota ``holiday``; mercados fechados ficam NaN (nunca preenchidos).
- Revisões do Yahoo em datas anteriores NÃO são aplicadas: são reportadas como limitação.
- Retorno total diário = ``adj_close[t] / adj_close_janela[t-1]`` da mesma coleta (o Yahoo
  reajusta todo o histórico a cada provento); o ``adj_close`` montado na leitura é encadeado e
  reescalado para que o último valor coincida com o ajuste mais recente do Yahoo.
- :meth:`MarketStore.load` verifica todos os hashes e a cadeia; o manifesto resultante lista
  os arquivos da base e dos incrementos (o ``content_hash`` muda se qualquer insumo mudar).
"""

from __future__ import annotations

import json
import logging
import math
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import FundConfig
from ..contracts import NewsItem, SnapshotFile, SnapshotManifest, SourceRecord
from ..hashing import sha256_file, sha256_obj
from ..market import FUNDAMENTAL_FIELDS, SHORT_INTEREST_FIELDS, MarketData
from ..universe import listing_market
from . import b3_lending, news
from .snapshot import (
    BENCHMARKS,
    DATETIME_DTYPE,
    FILE_BENCHMARKS,
    FILE_FUNDAMENTALS,
    FILE_FX,
    FILE_LENDING,
    FILE_MANIFEST,
    FILE_NEWS,
    FILE_PRICES,
    FILE_QA,
    FILE_RATES,
    FILE_SHORT_INTEREST,
    MARKET_INDICATORS,
    Fetchers,
    SnapshotIntegrityError,
    SnapshotTables,
    _cfg_or_default,
    _indexed_to_long,
    _json_safe,
    _long_to_indexed,
    _read_parquet,
    _write_parquet,
    adr_parity_report,
    assemble_market_data,
    build_snapshot,
    filter_news_as_of,
    fx_to_wide,
    normalize_benchmarks,
    normalize_fx,
    normalize_indexed,
    normalize_lending_history,
    normalize_prices,
    normalize_rates,
    prices_to_wide,
    read_manifest,
    read_news_jsonl,
    read_tables,
    verify_files,
    write_news_jsonl,
)

log = logging.getLogger(__name__)

DEFAULT_MARKET_ROOT = Path("data/market")
DEFAULT_WINDOW_DAYS = 10
DEFAULT_CLOSE_CUTOFF = time(19, 0)
DEFAULT_CLOSE_TZ = "America/Sao_Paulo"
REVISION_REL_TOL = 1e-6
PREV_COLUMNS = ["prev_date", "prev_close_window", "prev_adj_close_window"]
INCREMENT_DESCRIPTIONS = {
    FILE_PRICES: "Preços do pregão (+ barra anterior da mesma coleta para encadear retorno total)",
    FILE_FX: "Câmbio do pregão (USD por unidade)",
    FILE_BENCHMARKS: "Benchmarks do pregão",
    FILE_RATES: "Taxas do pregão (decimal anual)",
    FILE_LENDING: "Aluguel B3/BTC (longo) dos pregões ainda não gravados",
    FILE_FUNDAMENTALS: "Fundamentos atualizados (retrato atual, não PIT)",
    FILE_SHORT_INTEREST: "Short interest atualizado (FINRA/Yahoo)",
    FILE_NEWS: "Manchetes atualizadas — conteúdo NÃO confiável",
    FILE_QA: "QA do incremento: revisões, paridade ADR, mercados fechados",
}


class IncrementManifest(BaseModel):
    """Manifesto de um incremento diário, encadeado por hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["daily_increment"] = "daily_increment"
    session_date: date
    created_at: datetime
    base_as_of: date
    base_content_hash: str
    prev_manifest_hash: str
    universe_sha256: str
    files: list[SnapshotFile]
    sources: list[SourceRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    markets_traded: list[str] = Field(default_factory=list)
    markets_closed: list[str] = Field(default_factory=list)
    slow_refreshed: list[str] = Field(default_factory=list)
    lending_dates: list[date] = Field(default_factory=list)
    is_synthetic: bool
    data_notice: str = ""
    manifest_hash: str = ""

    @field_validator("created_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamps precisam de fuso horário.")
        return v

    def compute_hash(self) -> str:
        return sha256_obj(self.model_dump(mode="json", exclude={"manifest_hash"}))

    @property
    def is_holiday(self) -> bool:
        return "holiday" in self.notes


@dataclass(frozen=True)
class Increment:
    path: Path
    manifest: IncrementManifest

    @property
    def session_date(self) -> date:
        return self.manifest.session_date


@dataclass(frozen=True)
class IncrementTables:
    increment: Increment
    prices: pd.DataFrame
    fx: pd.DataFrame
    benchmarks: pd.DataFrame
    rates: pd.DataFrame
    lending: pd.DataFrame
    fundamentals: pd.DataFrame | None
    short_interest: pd.DataFrame | None
    news: tuple[NewsItem, ...] | None


def _read_increment_manifest(path: Path) -> IncrementManifest:
    p = Path(path) / FILE_MANIFEST
    if not p.exists():
        raise SnapshotIntegrityError(f"Manifesto do incremento ausente: {p}")
    return IncrementManifest.model_validate_json(p.read_text(encoding="utf-8"))


def _verify_increment_files(path: Path, m: IncrementManifest) -> list[str]:
    problems = []
    for f in m.files:
        p = Path(path) / f.path
        if not p.exists():
            problems.append(f"{path.name}: arquivo ausente {f.path}")
        elif sha256_file(p) != f.sha256:
            problems.append(f"{path.name}: hash divergente em {f.path}")
    return problems


def _combine_prices(base: pd.DataFrame, incs: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Concatena preços da base e dos incrementos encadeando o retorno total.

    Para cada linha do incremento, ``bruto = adj_close / prev_adj_close_window`` (mesma coleta)
    quando a barra anterior coincide com a última gravada; senão, fallback por preço
    (``close / close anterior``). O ``adj_close`` montado é então reescalado por ticker para que
    o último valor coincida com o ``adj_close`` bruto mais recente do Yahoo.
    """
    base = normalize_prices(base)
    if not incs:
        return base
    cols = list(base.columns)
    last_adj: dict[str, tuple[pd.Timestamp, float]] = {}
    last_close: dict[str, float] = {}
    for t, g in base.sort_values("date").groupby("ticker"):
        ga = g[g["adj_close"].notna()]
        if not ga.empty:
            last_adj[str(t)] = (ga["date"].iloc[-1], float(ga["adj_close"].iloc[-1]))
        gc = g[g["close"].notna()]
        if not gc.empty:
            last_close[str(t)] = float(gc["close"].iloc[-1])
    out_parts = [base]
    raw_last: dict[str, tuple[pd.Timestamp, float, float]] = {}
    for inc in incs:
        df = normalize_prices(inc)
        for c in PREV_COLUMNS:
            if c not in df.columns:
                df[c] = np.nan
        assembled = []
        for r in df.itertuples(index=False):
            t = str(r.ticker)
            raw = float(r.adj_close) if pd.notna(r.adj_close) else math.nan
            prev = last_adj.get(t)
            gross = math.nan
            prev_date = pd.Timestamp(r.prev_date) if pd.notna(r.prev_date) else None
            pa_w = float(r.prev_adj_close_window) if pd.notna(r.prev_adj_close_window) else math.nan
            if prev is not None and prev_date is not None and prev_date == prev[0] \
                    and pa_w > 0 and raw > 0:
                gross = raw / pa_w
            elif prev is not None and last_close.get(t, math.nan) > 0 and pd.notna(r.close) \
                    and r.close > 0:
                gross = float(r.close) / last_close[t]
            if prev is None or math.isnan(gross):
                val = raw
            else:
                val = prev[1] * gross
            assembled.append(val)
            if not math.isnan(val):
                last_adj[t] = (pd.Timestamp(r.date), val)
                if raw > 0:
                    raw_last[t] = (pd.Timestamp(r.date), raw, val)
            if pd.notna(r.close) and r.close > 0:
                last_close[t] = float(r.close)
        df = df.copy()
        df["adj_close"] = np.asarray(assembled, dtype=float) if assembled else df["adj_close"]
        out_parts.append(df[cols])
    out = pd.concat(out_parts, ignore_index=True)
    if out.duplicated(["date", "ticker"]).any():
        raise SnapshotIntegrityError("Preços duplicados entre base e incrementos.")
    for t, (_d, raw, val) in raw_last.items():
        if val > 0:
            m = out["ticker"] == t
            out.loc[m, "adj_close"] = out.loc[m, "adj_close"] * (raw / val)
    return normalize_prices(out)


class MarketStore:
    """Base imutável + incrementos diários encadeados por hash."""

    def __init__(self, root: Path = DEFAULT_MARKET_ROOT, *, fetchers: Fetchers | None = None,
                 cfg: FundConfig | None = None, now: Callable[[], datetime] | None = None,
                 close_cutoff: time = DEFAULT_CLOSE_CUTOFF, close_tz: str = DEFAULT_CLOSE_TZ,
                 window_days: int = DEFAULT_WINDOW_DAYS,
                 benchmarks: Sequence[str] | None = None) -> None:
        self.root = Path(root)
        self.fetchers = fetchers or Fetchers()
        self.cfg = cfg
        self._now = now or (lambda: datetime.now(UTC))
        self.close_cutoff = close_cutoff
        self.close_tz = close_tz
        self.window_days = int(window_days)
        self.benchmark_symbols = list(benchmarks) if benchmarks is not None else (
            BENCHMARKS + MARKET_INDICATORS)

    # ------------------------------------------------------------------ base
    @property
    def base_root(self) -> Path:
        return self.root / "base"

    @property
    def daily_root(self) -> Path:
        return self.root / "daily"

    def bases(self) -> list[Path]:
        if not self.base_root.exists():
            return []
        return sorted(p for p in self.base_root.iterdir()
                      if p.is_dir() and not p.name.startswith(".")
                      and (p / FILE_MANIFEST).exists())

    @property
    def base_dir(self) -> Path:
        bases = self.bases()
        if not bases:
            raise FileNotFoundError(f"Nenhuma base em {self.base_root}; use init_base().")
        return bases[-1]

    def init_base(self, snapshot_dir: Path) -> Path:
        """Copia um snapshot VERIFICADO para ``root/base/<as_of>`` (nunca sobrescreve)."""
        src = Path(snapshot_dir)
        m = read_manifest(src)
        verify_files(src, m)
        dest = self.base_root / m.as_of.isoformat()
        if dest.exists():
            raise FileExistsError(f"Base já existe: {dest}")
        if self.bases() and self.bases()[-1].name >= dest.name:
            raise ValueError("Nova base precisa ser posterior à base mais recente.")
        self.base_root.mkdir(parents=True, exist_ok=True)
        staging = self.base_root / f".{dest.name}.staging"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(src, staging)
        verify_files(staging, read_manifest(staging))
        staging.rename(dest)
        return dest

    def build_base(self, universe_path: Path, as_of: date, **kwargs: Any) -> SnapshotManifest:
        """Coleta e grava uma base diretamente em ``root/base/<as_of>``."""
        kwargs.setdefault("fetchers", self.fetchers)
        kwargs.setdefault("cfg", self.cfg)
        kwargs.setdefault("benchmarks", self.benchmark_symbols)
        return build_snapshot(Path(universe_path), self.base_root / as_of.isoformat(), as_of,
                              **kwargs)

    # ----------------------------------------------------------- incrementos
    def _all_increments(self) -> list[Increment]:
        if not self.daily_root.exists():
            return []
        out = []
        for p in sorted(self.daily_root.iterdir()):
            if p.is_dir() and not p.name.startswith(".") and (p / FILE_MANIFEST).exists():
                out.append(Increment(p, _read_increment_manifest(p)))
        return sorted(out, key=lambda i: i.session_date)

    def increments(self, base: Path | None = None) -> list[Increment]:
        """Incrementos encadeados à base (padrão: base mais recente), em ordem de data."""
        b = Path(base) if base is not None else self.base_dir
        h = read_manifest(b).content_hash()
        return [i for i in self._all_increments() if i.manifest.base_content_hash == h]

    def dates(self) -> list[date]:
        """Datas de fechamento disponíveis: ``as_of`` da base seguido de cada incremento."""
        if not self.bases():
            return []
        return [read_manifest(self.base_dir).as_of] + [i.session_date for i in self.increments()]

    def last_date(self) -> date:
        return self.dates()[-1]

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verifica hashes da(s) base(s), de cada incremento e o encadeamento."""
        problems: list[str] = []
        base_hashes: dict[str, tuple[Path, SnapshotManifest]] = {}
        for b in self.bases():
            try:
                m = read_manifest(b)
                verify_files(b, m)
                base_hashes[m.content_hash()] = (b, m)
            except Exception as exc:
                problems.append(f"base {b.name}: {exc}")
        by_base: dict[str, list[Increment]] = {}
        for inc in self._all_increments():
            by_base.setdefault(inc.manifest.base_content_hash, []).append(inc)
        for h, incs in by_base.items():
            if h not in base_hashes:
                problems.extend(f"incremento órfão {i.path.name} (base desconhecida)" for i in incs)
                continue
            prev_hash = h
            prev_date = base_hashes[h][1].as_of
            for inc in sorted(incs, key=lambda i: i.session_date):
                m = inc.manifest
                if inc.path.name != m.session_date.isoformat():
                    problems.append(f"{inc.path.name}: pasta não corresponde a {m.session_date}")
                if m.compute_hash() != m.manifest_hash:
                    problems.append(f"{inc.path.name}: manifesto adulterado (hash divergente)")
                if m.prev_manifest_hash != prev_hash:
                    problems.append(f"{inc.path.name}: cadeia quebrada (prev_manifest_hash)")
                if m.session_date <= prev_date:
                    problems.append(f"{inc.path.name}: data fora de ordem")
                if m.universe_sha256 != base_hashes[h][1].universe_sha256:
                    problems.append(f"{inc.path.name}: universo difere da base")
                problems.extend(_verify_increment_files(inc.path, m))
                prev_hash, prev_date = m.manifest_hash, m.session_date
        return (not problems), problems

    def _require_chain(self) -> None:
        ok, problems = self.verify_chain()
        if not ok:
            raise SnapshotIntegrityError("Cadeia do repositório inválida: " + "; ".join(problems))

    # --------------------------------------------------------------- leitura
    def _read_increment(self, inc: Increment) -> IncrementTables:
        names = {f.path for f in inc.manifest.files}

        def opt(name: str) -> pd.DataFrame | None:
            return _read_parquet(inc.path / name) if name in names else None

        fund = opt(FILE_FUNDAMENTALS)
        si = opt(FILE_SHORT_INTEREST)
        return IncrementTables(
            increment=inc, prices=normalize_prices(opt(FILE_PRICES)),
            fx=normalize_fx(opt(FILE_FX)), benchmarks=normalize_benchmarks(opt(FILE_BENCHMARKS)),
            rates=normalize_rates(opt(FILE_RATES)),
            lending=normalize_lending_history(opt(FILE_LENDING)),
            fundamentals=_long_to_indexed(fund) if fund is not None else None,
            short_interest=_long_to_indexed(si) if si is not None else None,
            news=read_news_jsonl(inc.path / FILE_NEWS) if FILE_NEWS in names else None,
        )

    @staticmethod
    def _base_lending_long(bt: SnapshotTables) -> pd.DataFrame:
        lh = bt.lending_history
        snap = bt.lending
        if snap is not None and not snap.empty and "lending_date" in snap.columns:
            extra = snap.reset_index()
            extra["date"] = pd.to_datetime(extra["lending_date"], errors="coerce")
            extra = extra[extra["date"].notna()]
            if not lh.empty:
                keys = set(zip(lh["date"], lh["ticker"], strict=True))
                extra = extra[[(d, t) not in keys for d, t in
                               zip(extra["date"], extra["ticker"], strict=True)]]
            lh = pd.concat([lh, extra], ignore_index=True) if not extra.empty else lh
        return normalize_lending_history(lh)

    def load(self, as_of: date | None = None, verify: bool = True) -> MarketData:
        """Base + incrementos com data <= ``as_of`` como ``MarketData`` verificado."""
        bases = self.bases()
        if not bases:
            raise FileNotFoundError(f"Nenhuma base em {self.base_root}.")
        if verify:
            self._require_chain()
        base = bases[-1]
        if as_of is not None:
            eligible = [b for b in bases if read_manifest(b).as_of <= as_of]
            base = eligible[-1] if eligible else bases[0]
        bt = read_tables(base, verify=verify)
        incs = [i for i in self.increments(base) if as_of is None or i.session_date <= as_of]
        tabs = [self._read_increment(i) for i in incs]
        base_as_of = bt.manifest.as_of
        if as_of is None:
            eff = incs[-1].session_date if incs else base_as_of
        else:
            eff = max([base_as_of] + [i.session_date for i in incs]) if as_of >= base_as_of \
                else as_of
        ts = pd.Timestamp(eff)

        prices = _combine_prices(bt.prices, [t.prices for t in tabs])
        fx = pd.concat([bt.fx] + [t.fx for t in tabs], ignore_index=True)
        bench = pd.concat([bt.benchmarks] + [t.benchmarks for t in tabs], ignore_index=True)
        rates = pd.concat([bt.rates] + [t.rates for t in tabs], ignore_index=True)
        prices, fx, bench, rates = (d[d["date"] <= ts] for d in (prices, fx, bench, rates))

        fundamentals, short_interest = bt.fundamentals, bt.short_interest
        for t in tabs:
            if t.fundamentals is not None:
                fundamentals = t.fundamentals
            if t.short_interest is not None:
                short_interest = t.short_interest
        lend_long = pd.concat([self._base_lending_long(bt)] + [t.lending for t in tabs],
                              ignore_index=True)
        lend_long = normalize_lending_history(lend_long).drop_duplicates(["date", "ticker"],
                                                                          keep="last")
        lending = b3_lending.latest_lending(lend_long, eff)

        items: list[NewsItem] = list(bt.news)
        for t in tabs:
            if t.news:
                items.extend(t.news)
        items = [n for n in news.dedupe_news(items) if n.published_at.date() <= eff]

        files = [SnapshotFile(path=f"base/{base.name}/{f.path}", sha256=f.sha256, rows=f.rows,
                              description=f.description) for f in bt.manifest.files]
        sources = list(bt.manifest.sources)
        limitations = list(bt.manifest.limitations)
        created = bt.manifest.created_at
        for t in tabs:
            m = t.increment.manifest
            d = m.session_date.isoformat()
            files.extend(SnapshotFile(path=f"daily/{d}/{f.path}", sha256=f.sha256, rows=f.rows,
                                      description=f.description) for f in m.files)
            files.append(SnapshotFile(path=f"daily/{d}/{FILE_MANIFEST}",
                                      sha256=sha256_file(t.increment.path / FILE_MANIFEST),
                                      description="Manifesto do incremento (encadeado)"))
            sources.extend(m.sources)
            limitations.extend(f"[{d}] {x}" for x in m.limitations)
            created = max(created, m.created_at)
        limitations.append(f"Composição: base {base.name} (content_hash "
                           f"{bt.manifest.content_hash()[:12]}…) + {len(tabs)} incremento(s) "
                           f"até {eff.isoformat()}.")
        manifest = SnapshotManifest(
            snapshot_id=f"store-{base.name}+{len(tabs)}-{eff.isoformat()}", as_of=eff,
            created_at=created, universe_sha256=bt.manifest.universe_sha256, files=files,
            sources=sources, limitations=limitations,
            missing_tickers=list(bt.manifest.missing_tickers),
            is_synthetic=bt.manifest.is_synthetic, data_notice=bt.manifest.data_notice)
        return assemble_market_data(manifest, bt.universe, prices, fx, bench, rates, fundamentals,
                                    short_interest, lending, items)

    # --------------------------------------------------------------- escrita
    def session_closed(self, session_date: date) -> bool:
        """True quando ``agora`` >= ``session_date`` no horário de corte (fuso do fechamento)."""
        cutoff = datetime.combine(session_date, self.close_cutoff,
                                  tzinfo=ZoneInfo(self.close_tz))
        return self._now() >= cutoff

    def catch_up(self, until: date, fetchers: Fetchers | None = None,
                 refresh_slow_on_monday: bool = True) -> list[IncrementManifest]:
        """Grava, em ordem, todos os pregões fechados após o último gravado até ``until``.

        Dias sem nenhuma negociação (fins de semana, feriados globais) são pulados.
        """
        out: list[IncrementManifest] = []
        last = self.last_date()
        for ts in pd.bdate_range(last + timedelta(days=1), until):
            d = ts.date()
            if not self.session_closed(d):
                break
            try:
                out.append(self.append_daily(d, fetchers=fetchers,
                                             refresh_slow=refresh_slow_on_monday
                                             and d.weekday() == 0))
            except NoSessionError as exc:
                log.info("Sem pregão em %s: %s", d, exc)
        return out

    def append_daily(self, session_date: date, fetchers: Fetchers | None = None,
                     refresh_slow: bool = False, *, include_news: bool = False,
                     allow_gap: bool = False) -> IncrementManifest:
        """Coleta uma janela curta e grava SOMENTE as linhas com ``date == session_date``.

        ``refresh_slow=True`` também atualiza fundamentos, short interest e notícias (segundas
        ou sob demanda). O aluguel B3 é coletado em todo incremento (janela D-21 do BDI).
        """
        f = fetchers or self.fetchers
        cfg = _cfg_or_default(self.cfg)
        base = self.base_dir
        self._require_chain()
        bt = read_tables(base, verify=False)  # já verificado em _require_chain
        incs = self.increments(base)
        last = incs[-1].session_date if incs else bt.manifest.as_of
        if session_date <= last:
            raise ValueError(f"Pregão {session_date} <= último gravado ({last}); "
                             "incrementos são append-only.")
        inc_dir = self.daily_root / session_date.isoformat()
        if inc_dir.exists():
            raise FileExistsError(f"Incremento já existe: {inc_dir}")
        if session_date > self._now().date() or not self.session_closed(session_date):
            raise ValueError(f"Pregão {session_date} ainda não fechou (corte "
                             f"{self.close_cutoff.isoformat()} {self.close_tz}).")
        tabs = [self._read_increment(i) for i in incs]
        uni = bt.universe
        tickers = uni.tickers
        ts = pd.Timestamp(session_date)
        start_w = min(session_date - timedelta(days=self.window_days), last - timedelta(days=5))
        limitations: list[str] = []
        notes: list[str] = []
        sources: list[SourceRecord] = []

        def src(sid: str, name: str, pit: bool, notes_: str = "") -> SourceRecord:
            return SourceRecord(source_id=sid, name=name, url="", fields=[],
                                retrieved_at=self._now(), point_in_time=pit, notes=notes_)

        # Preços (obrigatório): janela curta, gravando só a data do pregão.
        win, _missing = f.prices(tickers, start_w, session_date)
        win = normalize_prices(win)
        win = win[win["ticker"].isin(tickers) & (win["date"] <= ts)]
        win = win.drop_duplicates(["date", "ticker"], keep="last").reset_index(drop=True)
        day = win[win["date"] == ts].copy()
        sources.append(src("yahoo_prices", "Yahoo Finance — barras diárias (janela)", True))
        stored = pd.concat([bt.prices] + [t.prices for t in tabs], ignore_index=True)
        stored = normalize_prices(stored)
        last_ts = pd.Timestamp(last)
        missed = sorted({d.date() for d in win.loc[(win["date"] > last_ts) & (win["date"] < ts),
                                                    "date"]})
        if missed and not allow_gap:
            raise ValueError(f"Pregões não gravados entre {last} e {session_date}: "
                             f"{[d.isoformat() for d in missed]}; use catch_up().")
        if missed:
            limitations.append("Pregões intermediários NÃO gravados (allow_gap): "
                               + ", ".join(d.isoformat() for d in missed) + ".")

        # Barra anterior (mesma coleta) para encadear o retorno total.
        last_stored = stored[stored["date"] < ts].sort_values("date").groupby("ticker").tail(1)
        prev_map = {str(r.ticker): pd.Timestamp(r.date) for r in last_stored.itertuples()}
        win_idx = win.set_index(["ticker", "date"])
        prev_rows = []
        price_only: list[str] = []
        for r in day.itertuples(index=False):
            pdt = prev_map.get(str(r.ticker))
            pc = pa = math.nan
            if pdt is not None and (r.ticker, pdt) in win_idx.index:
                w = win_idx.loc[(r.ticker, pdt)]
                pc, pa = float(w["close"]), float(w["adj_close"])
            if pdt is not None and not (pa > 0):
                price_only.append(str(r.ticker))
            prev_rows.append((pdt if pdt is not None else pd.NaT, pc, pa))
        day["prev_date"] = pd.to_datetime([x[0] for x in prev_rows]) if prev_rows else \
            pd.Series(dtype=DATETIME_DTYPE)
        day["prev_close_window"] = [x[1] for x in prev_rows]
        day["prev_adj_close_window"] = [x[2] for x in prev_rows]
        if price_only:
            limitations.append("Retorno total por preço (sem barra anterior na janela) para: "
                               + ", ".join(sorted(price_only)) + ".")

        # Revisões do Yahoo em datas anteriores (NÃO aplicadas).
        revisions = self._detect_revisions(win[(win["date"] < ts) & (win["date"] >= pd.Timestamp(
            start_w))], stored)
        n_close = sum(1 for x in revisions if x["kind"] == "close")
        n_vol = sum(1 for x in revisions if x["kind"] == "volume")
        n_late = sum(1 for x in revisions if x["kind"] == "dado_tardio")
        if n_close:
            ex = ", ".join(f"{x['ticker']}@{x['date']} ({x['ratio']:.4f})"
                           for x in revisions if x["kind"] == "close")
            limitations.append(f"Revisões de fechamento do Yahoo em datas anteriores NÃO "
                               f"aplicadas ({n_close}): {ex[:600]}.")
        if n_vol:
            limitations.append(f"Revisões de volume em datas anteriores NÃO aplicadas: {n_vol}.")
        if n_late:
            limitations.append(f"Barras tardias (datas anteriores não gravadas) NÃO aplicadas: "
                               f"{n_late}.")

        # Câmbio, benchmarks e taxas do pregão.
        ccys = sorted(c for c in uni.currencies if c != "USD")
        try:
            fx_day = normalize_fx(f.fx(ccys, start_w, session_date))
            fx_day = fx_day[(fx_day["date"] == ts) & fx_day["currency"].isin(ccys)]
            sources.append(src("yahoo_fx", "Yahoo Finance — câmbio", True))
        except Exception as exc:
            fx_day = normalize_fx(None)
            limitations.append(f"Câmbio indisponível no pregão: {exc!r}.")
        if not fx_day.empty and set(fx_day["currency"]) != set(ccys):
            limitations.append("Câmbio ausente no pregão para: "
                               + ", ".join(sorted(set(ccys) - set(fx_day["currency"]))) + ".")
        try:
            bench_day = normalize_benchmarks(f.benchmarks(self.benchmark_symbols, start_w,
                                                          session_date))
            bench_day = bench_day[bench_day["date"] == ts]
            sources.append(src("yahoo_benchmarks", "Yahoo Finance — benchmarks", True))
        except Exception as exc:
            bench_day = normalize_benchmarks(None)
            limitations.append(f"Benchmarks indisponíveis no pregão: {exc!r}.")
        try:
            rates_day = normalize_rates(f.rates(start_w, session_date))
            rates_day = rates_day[rates_day["date"] == ts]
            sources.append(src("rates", "BCB SGS 432 + Yahoo ^IRX", True))
        except Exception as exc:
            rates_day = normalize_rates(None)
            limitations.append(f"Taxas indisponíveis no pregão: {exc!r}.")

        markets_all = sorted({listing_market(t) for t in tickers})
        traded = sorted({listing_market(t) for t in day["ticker"]})
        closed = sorted(set(markets_all) - set(traded))
        if day.empty:
            if fx_day.empty and bench_day.empty:
                raise NoSessionError(f"Nenhuma linha, câmbio ou benchmark negociou em "
                                     f"{session_date}; nada a gravar.")
            notes.append("holiday")
            limitations.append("Feriado: nenhuma linha do universo negociou; câmbio/EUA abertos.")
        elif closed:
            notes.append("mercados_fechados: " + ",".join(closed))

        # Aluguel B3: todos os pregões publicados após o último gravado.
        br = [t for t in tickers if listing_market(t) == "BR"]
        lend_known = pd.concat([self._base_lending_long(bt)] + [t.lending for t in tabs],
                               ignore_index=True)
        last_lend = lend_known["date"].max() if not lend_known.empty else pd.NaT
        start_l = (last_lend + pd.Timedelta(days=1)).date() if pd.notna(last_lend) else \
            b3_lending.lending_window_start(session_date)
        fund_now = bt.fundamentals
        for t in tabs:
            if t.fundamentals is not None:
                fund_now = t.fundamentals
        so_map = {}
        if fund_now is not None and "shares_outstanding" in fund_now.columns:
            so_map = {t: float(v) for t, v in fund_now["shares_outstanding"].items()
                      if t in br and pd.notna(v)}
        lend_new = normalize_lending_history(None)
        if br and start_l <= session_date:
            try:
                lend_new = normalize_lending_history(f.lending(br, start_l, session_date, so_map))
                lend_new = lend_new[(lend_new["date"] >= pd.Timestamp(start_l))
                                    & (lend_new["date"] <= ts)]
                sources.append(src("b3_bdi_lending", "B3 BDI — aluguel (BTC)", False))
                if lend_new.empty:
                    limitations.append(f"Aluguel B3 sem publicação nova entre {start_l} e "
                                       f"{session_date} (BDI publica em D+1).")
            except Exception as exc:
                limitations.append(f"Aluguel B3 indisponível: {exc!r}.")

        # Dados lentos (segundas ou sob demanda).
        slow: list[str] = []
        fund_new = si_new = None
        news_new: list[NewsItem] | None = None
        if refresh_slow:
            cmap = {t: str(uni.lines.loc[t, "currency"]) for t in tickers}
            try:
                fund_new = normalize_indexed(f.fundamentals(tickers, cmap, session_date),
                                             FUNDAMENTAL_FIELDS)
                slow.append("fundamentals")
                sources.append(src("yahoo_fundamentals", "Yahoo — Ticker.info", False))
            except Exception as exc:
                limitations.append(f"Fundamentos não atualizados: {exc!r}.")
            us = [t for t in tickers if listing_market(t) == "US"]
            ratios = {t: float(uni.lines.loc[t, "adr_ratio"]) for t in us
                      if pd.notna(uni.lines.loc[t, "adr_ratio"])}
            try:
                si_new = normalize_indexed(f.short_interest(us, session_date, ratios),
                                           SHORT_INTEREST_FIELDS)
                slow.append("short_interest")
                sources.append(src("finra_yahoo_short_interest", "FINRA + Yahoo", False))
            except Exception as exc:
                limitations.append(f"Short interest não atualizado: {exc!r}.")
        if refresh_slow or include_news:
            lookback = cfg.research.news_lookback_days if refresh_slow else 2
            try:
                res = f.news(news.queries_from_universe(uni), session_date, lookback)
                items, failed = (res if isinstance(res, tuple) else (res, []))
                news_new = news.dedupe_news(filter_news_as_of(items, uni, session_date, lookback))
                slow.append("news")
                sources.append(src("google_news_rss", "Google News RSS (NÃO confiável)", False))
                if failed:
                    limitations.append(f"Notícias indisponíveis para {len(failed)} emissores.")
            except Exception as exc:
                limitations.append(f"Notícias não atualizadas: {exc!r}.")

        # QA: paridade ADR no pregão (com 30 dias de histórico gravado para a mediana).
        qa: dict[str, Any] = {"session_date": session_date.isoformat(), "revisions": revisions,
                              "markets_traded": traded, "markets_closed": closed,
                              "n_price_rows": int(len(day)), "price_only_returns": price_only}
        if not day.empty:
            recent = stored[stored["date"] >= ts - pd.Timedelta(days=45)]
            close_w, _, _ = prices_to_wide(pd.concat([recent, day[recent.columns]],
                                                     ignore_index=True))
            fx_all = pd.concat([bt.fx] + [t.fx for t in tabs] + [fx_day], ignore_index=True)
            fx_w = fx_to_wide(fx_all[fx_all["date"] >= ts - pd.Timedelta(days=60)]
                              .drop_duplicates(["date", "currency"], keep="last"))
            parity = adr_parity_report(close_w, fx_w, uni, cfg.squeeze.adr_parity_tolerance)
            today = [p for p in parity["pairs"] if p["last_date"] == session_date.isoformat()]
            qa["adr_parity"] = {"pairs": today,
                                "ars_implied_ccl_premium": parity["ars_implied_ccl_premium"]}
            for p in today:
                if p["flagged"]:
                    limitations.append(f"QA paridade ADR: {p['adr']} vs {p['local']} "
                                       f"desvio {p['dev_last']:+.1%} no pregão (mediana "
                                       f"{p['dev_median']:+.1%}; tolerância {p['tolerance']:.0%}).")

        base_m = bt.manifest
        prev_hash = incs[-1].manifest.manifest_hash if incs else base_m.content_hash()
        lend_dates = sorted({d.date() for d in lend_new["date"]}) if not lend_new.empty else []

        def writer(root: Path) -> IncrementManifest:
            files: list[SnapshotFile] = []

            def add(name: str, rows: int | None) -> None:
                files.append(SnapshotFile(path=name, sha256=sha256_file(root / name), rows=rows,
                                          description=INCREMENT_DESCRIPTIONS.get(name, "")))

            add(FILE_PRICES, _write_parquet(normalize_prices(day), root / FILE_PRICES))
            add(FILE_FX, _write_parquet(fx_day, root / FILE_FX))
            add(FILE_BENCHMARKS, _write_parquet(bench_day, root / FILE_BENCHMARKS))
            add(FILE_RATES, _write_parquet(rates_day, root / FILE_RATES))
            add(FILE_LENDING, _write_parquet(normalize_lending_history(lend_new),
                                             root / FILE_LENDING))
            if fund_new is not None:
                add(FILE_FUNDAMENTALS, _write_parquet(_indexed_to_long(fund_new),
                                                      root / FILE_FUNDAMENTALS))
            if si_new is not None:
                add(FILE_SHORT_INTEREST, _write_parquet(_indexed_to_long(si_new),
                                                        root / FILE_SHORT_INTEREST))
            if news_new is not None:
                add(FILE_NEWS, write_news_jsonl(news_new, root / FILE_NEWS))
            (root / FILE_QA).write_text(json.dumps(_json_safe(qa), ensure_ascii=False,
                                                   sort_keys=True, indent=2) + "\n",
                                        encoding="utf-8")
            add(FILE_QA, None)
            m = IncrementManifest(
                session_date=session_date, created_at=self._now(), base_as_of=base_m.as_of,
                base_content_hash=base_m.content_hash(), prev_manifest_hash=prev_hash,
                universe_sha256=base_m.universe_sha256, files=sorted(files, key=lambda x: x.path),
                sources=sources, limitations=limitations, notes=notes, markets_traded=traded,
                markets_closed=closed, slow_refreshed=slow, lending_dates=lend_dates,
                is_synthetic=base_m.is_synthetic, data_notice=base_m.data_notice)
            m = m.model_copy(update={"manifest_hash": m.compute_hash()})
            (root / FILE_MANIFEST).write_text(m.model_dump_json(indent=2) + "\n",
                                              encoding="utf-8")
            return m

        self.daily_root.mkdir(parents=True, exist_ok=True)
        staging = self.daily_root / f".{inc_dir.name}.staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        try:
            manifest = writer(staging)
            if inc_dir.exists():
                raise FileExistsError(f"Incremento criado durante a gravação: {inc_dir}")
            staging.rename(inc_dir)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return manifest

    @staticmethod
    def _detect_revisions(window: pd.DataFrame, stored: pd.DataFrame) -> list[dict[str, Any]]:
        """Compara a janela recém-coletada com o que já está gravado (datas anteriores)."""
        if window.empty:
            return []
        st = stored[stored["date"].isin(set(window["date"]))].set_index(["ticker", "date"])
        out: list[dict[str, Any]] = []
        for r in window.itertuples(index=False):
            key = (r.ticker, r.date)
            if key not in st.index:
                out.append({"kind": "dado_tardio", "ticker": r.ticker,
                            "date": r.date.date().isoformat(), "ratio": math.nan})
                continue
            s = st.loc[key]
            sc, nc = float(s["close"]), float(r.close)
            if sc > 0 and nc > 0 and abs(nc / sc - 1.0) > REVISION_REL_TOL:
                out.append({"kind": "close", "ticker": r.ticker,
                            "date": r.date.date().isoformat(), "ratio": nc / sc,
                            "stored": sc, "new": nc})
            sv, nv = float(s["volume"]), float(r.volume)
            if not (math.isnan(sv) and math.isnan(nv)) and (
                    math.isnan(sv) != math.isnan(nv) or abs(nv - sv) > max(1.0, 1e-6 * abs(sv))):
                out.append({"kind": "volume", "ticker": r.ticker,
                            "date": r.date.date().isoformat(),
                            "ratio": nv / sv if sv and not math.isnan(sv) else math.nan})
        return sorted(out, key=lambda x: (x["date"], x["ticker"], x["kind"]))


class NoSessionError(ValueError):
    """Nenhum mercado negociou na data (fim de semana ou feriado global)."""
