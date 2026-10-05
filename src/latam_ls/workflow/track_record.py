"""Track record diário auditável do CDP — Cabra da Peste (paper trading com preços reais).

Layout (``root`` = ``book/track_record`` por padrão)::

    records/<AAAA-MM-DD>.json   ``DailyRecord`` imutável (JSON indentado, chaves ordenadas)
    track_record.csv            resumo derivado, uma linha por registro (somente anexação)
    ../audit_log.jsonl          trilha de auditoria do livro (evento ``DAILY_RECORD``)

Regras:

- **Encadeamento por hash:** cada registro grava ``prev_record_hash`` (o ``record_hash`` do
  registro anterior; o primeiro aponta para ``GENESIS_RECORD_HASH``) e ``record_hash =
  DailyRecord.compute_hash()``. Editar, remover ou reordenar um dia quebra a cadeia.
- **Imutabilidade:** cada arquivo é criado de forma exclusiva e atômica; nunca é sobrescrito.
- **Datas estritamente crescentes** (um registro por pregão).
- **Sem zeros silenciosos:** números não finitos são recusados; ausentes ficam vazios no CSV.
- :meth:`TrackRecord.verify` recalcula todos os hashes, confere os elos, a ordem das datas, a
  consistência do CSV com os JSON e a presença de cada registro na trilha de auditoria.

As estatísticas (:meth:`TrackRecord.stats`, :meth:`TrackRecord.monthly_returns_table`) usam só os
registros gravados; o excesso de retorno sobre o caixa usa o próprio financiamento registrado
(``financing / NAV inicial`` é exatamente o retorno da taxa USD 3M no período, ACT/360).
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..audit import GENESIS_HASH, AuditLog
from ..config import FundConfig
from ..contracts import DailyRecord
from ..hashing import sha256_obj
from ..risk.types import TRADING_DAYS

GENESIS_RECORD_HASH = GENESIS_HASH
DAILY_RECORD_EVENT = "DAILY_RECORD"
DEFAULT_TRACK_ROOT = Path("book/track_record")
RECORDS_DIRNAME = "records"
CSV_NAME = "track_record.csv"
TRACK_ACTOR = "CDP — rotina diária"

CSV_COLUMNS: list[str] = [
    "date", "nav", "ret", "pnl", "gross", "net", "beta", "ex_ante_vol", "realized_vol_21d",
    "drawdown", "factor_pnl", "specific_pnl", "costs", "borrow", "financing", "record_hash",
]
FLOAT_COLUMNS: list[str] = CSV_COLUMNS[1:-1]
REQUIRED_FLOAT_COLUMNS = ("nav", "ret", "pnl", "gross", "net", "drawdown")

MONTH_LABELS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
YTD_LABEL = "YTD"
REALIZED_VOL_WINDOWS = (21, 63)


# ==========================================================
# Utilidades puras
# ==========================================================

def record_json(record: DailyRecord) -> str:
    """JSON canônico do registro: indentado (2), chaves ordenadas, UTF-8, com quebra final."""
    return json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True,
                      ensure_ascii=False) + "\n"


def non_finite_fields(obj: Any, path: str = "") -> list[str]:
    """Caminhos de campos numéricos não finitos (NaN/inf) numa estrutura serializada."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += non_finite_fields(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out += non_finite_fields(v, f"{path}[{i}]")
    elif isinstance(obj, float) and not math.isfinite(obj):
        out.append(path or "<raiz>")
    return out


def record_summary(record: DailyRecord) -> dict[str, object]:
    """Linha do CSV-resumo derivada do registro (ausente ⇒ ``None``, nunca zero)."""
    comp = record.pnl_components
    risk = record.risk
    return {
        "date": record.date.isoformat(),
        "nav": record.nav_end_usd,
        "ret": record.ret,
        "pnl": record.pnl_usd,
        "gross": risk.gross,
        "net": risk.net,
        "beta": risk.beta,
        "ex_ante_vol": risk.ex_ante_vol,
        "realized_vol_21d": risk.realized_vol_21d,
        "drawdown": risk.drawdown,
        "factor_pnl": comp.get("factor"),
        "specific_pnl": comp.get("specific"),
        "costs": comp.get("costs"),
        "borrow": comp.get("borrow"),
        "financing": comp.get("financing"),
        "record_hash": record.record_hash,
    }


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _parse_float(raw: str) -> float | None:
    return None if raw in ("", None) else float(raw)


def realized_vol(returns: Sequence[float] | pd.Series, window: int) -> float | None:
    """Vol realizada anualizada dos últimos ``window`` retornos (``None`` sem histórico suficiente)."""
    r = pd.Series(list(returns) if not isinstance(returns, pd.Series) else returns, dtype=float)
    r = r.dropna()
    if len(r) < window or window < 2:
        return None
    return float(r.iloc[-window:].std(ddof=1) * math.sqrt(TRADING_DAYS))


def drawdown_series(nav_start: float, navs: Sequence[float] | pd.Series) -> pd.Series:
    """Drawdown a partir do pico (inclui o NAV inicial como primeiro pico)."""
    path = pd.Series([float(nav_start)] + [float(x) for x in navs], dtype=float)
    return (path / path.cummax() - 1.0).iloc[1:].reset_index(drop=True)


def _parse_record_name(path: Path) -> date | None:
    if path.suffix != ".json":
        return None
    try:
        return date.fromisoformat(path.stem)
    except ValueError:
        return None


def _write_exclusive(path: Path, text: str) -> None:
    """Cria ``path`` atomicamente; ``FileExistsError`` se já existir (nunca sobrescreve)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Arquivo imutável já existe: {path}")
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise FileExistsError(f"Arquivo imutável já existe: {path}") from None
        except OSError:
            with path.open("x", encoding="utf-8", newline="\n") as f:
                f.write(text)
    finally:
        tmp.unlink(missing_ok=True)


# ==========================================================
# Track record
# ==========================================================

class TrackRecord:
    """Série diária imutável de ``DailyRecord`` encadeados por hash, com resumo em CSV.

    ``audit_path`` (padrão: ``<root>/../audit_log.jsonl``, a trilha do livro) recebe um evento
    ``audit_event`` por registro com ``payload = record_hash``. Duas séries que compartilham a
    trilha (ex.: CDP e sombra só-quant) devem usar tipos de evento distintos.
    """

    def __init__(self, root: Path | str = DEFAULT_TRACK_ROOT, *,
                 audit_path: Path | str | None = None,
                 audit_event: str = DAILY_RECORD_EVENT, actor: str = TRACK_ACTOR) -> None:
        self.root = Path(root)
        self.records_dir = self.root / RECORDS_DIRNAME
        self.csv_path = self.root / CSV_NAME
        self.audit_event = audit_event
        self.actor = actor
        self.audit = AuditLog(Path(audit_path) if audit_path is not None
                              else self.root.parent / "audit_log.jsonl")

    # ---------------------------------------------- leitura
    def record_path(self, d: date) -> Path:
        return self.records_dir / f"{d.isoformat()}.json"

    def _record_files(self) -> list[tuple[date, Path]]:
        if not self.records_dir.is_dir():
            return []
        files = [(d, p) for p in self.records_dir.iterdir()
                 if p.is_file() and (d := _parse_record_name(p)) is not None]
        return sorted(files)

    def dates(self) -> list[date]:
        return [d for d, _ in self._record_files()]

    def _load(self, path: Path) -> DailyRecord:
        return DailyRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def get(self, d: date) -> DailyRecord | None:
        path = self.record_path(d)
        return self._load(path) if path.exists() else None

    def iter_records(self, reverse: bool = False) -> Iterator[DailyRecord]:
        files = self._record_files()
        for _, path in (reversed(files) if reverse else files):
            yield self._load(path)

    def records(self) -> list[DailyRecord]:
        return list(self.iter_records())

    def last(self) -> DailyRecord | None:
        files = self._record_files()
        return self._load(files[-1][1]) if files else None

    def __len__(self) -> int:
        return len(self._record_files())

    # ---------------------------------------------- gravação
    def append(self, record: DailyRecord) -> Path:
        """Anexa o registro do dia (imutável), o resumo no CSV e o evento de auditoria.

        Recusa: hash divergente de ``compute_hash()``, elo ``prev_record_hash`` diferente do
        último registro (ou de GENESIS no primeiro), data não posterior à última, números não
        finitos, serialização instável e arquivo já existente.
        """
        if record.record_hash != record.compute_hash():
            raise ValueError("record_hash não confere com o conteúdo do registro.")
        bad = non_finite_fields(record.model_dump(mode="json"))
        if bad:
            raise ValueError("Registro com números não finitos (use None para ausente): "
                             + ", ".join(bad[:10]))
        last = self.last()
        expected_prev = last.record_hash if last is not None else GENESIS_RECORD_HASH
        if record.prev_record_hash != expected_prev:
            raise ValueError(
                f"Elo da cadeia inválido em {record.date}: prev_record_hash não é o hash do "
                "último registro gravado" + (f" ({last.date})." if last else " (GENESIS)."))
        if last is not None and record.date <= last.date:
            kind = "duplicado" if record.date == last.date else "fora de ordem"
            raise ValueError(f"Registro de {record.date} {kind} (último: {last.date}).")
        if self.csv_path.exists() and last is None:
            raise ValueError(f"CSV {self.csv_path} existe sem registros JSON: rode verify().")
        text = record_json(record)
        if DailyRecord.model_validate_json(text).compute_hash() != record.record_hash:
            raise ValueError("Registro não é serializável de forma estável (hash muda ao regravar).")
        path = self.record_path(record.date)
        row = record_summary(record)
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            writer.writerow(CSV_COLUMNS)
        writer.writerow([_cell(row[c]) for c in CSV_COLUMNS])

        _write_exclusive(path, text)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.csv_path.open("a", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
        self.audit.append(
            self.audit_event, self.actor, record.record_hash,
            summary=(f"Registro diário {record.date} ({self.root.name}): NAV "
                     f"USD {record.nav_end_usd / 1e6:,.2f} mm, retorno {record.ret:+.4%}, "
                     f"hash {record.record_hash[:12]}."),
            week=record.live_book_week)
        return path

    # ---------------------------------------------- séries
    def _csv_rows(self) -> list[dict[str, str]]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is not None and list(reader.fieldnames) != CSV_COLUMNS:
                raise ValueError(f"Cabeçalho inesperado em {self.csv_path}: {reader.fieldnames}")
            return list(reader)

    def frame(self) -> pd.DataFrame:
        """Resumo diário (índice ``date``); ausentes como ``NaN``, nunca zero."""
        rows = self._csv_rows()
        cols = CSV_COLUMNS[1:]
        if not rows:
            return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="date"))
        df = pd.DataFrame(rows, columns=CSV_COLUMNS)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        for c in FLOAT_COLUMNS:
            df[c] = pd.to_numeric(df[c].replace("", np.nan), errors="raise").astype(float)
        return df[cols]

    def returns(self) -> pd.Series:
        return self.frame()["ret"].rename("ret")

    def nav_series(self) -> pd.Series:
        """NAV de fechamento por pregão (USD)."""
        return self.frame()["nav"].rename("nav")

    def inception_nav(self) -> float | None:
        """NAV na abertura do primeiro registro (NAV final − P&L do primeiro dia)."""
        f = self.frame()
        if f.empty:
            return None
        return float(f["nav"].iloc[0] - f["pnl"].iloc[0])

    def drawdown_series(self) -> pd.Series:
        f = self.frame()
        if f.empty:
            return pd.Series(dtype=float, name="drawdown")
        start = float(f["nav"].iloc[0] - f["pnl"].iloc[0])
        dd = drawdown_series(start, f["nav"])
        dd.index = f.index
        return dd.rename("drawdown")

    def monthly_returns_table(self) -> pd.DataFrame:
        """Grade clássica anos × meses (Jan…Dez) + YTD, com retornos diários compostos.

        Mês sem registro fica ``NaN`` (não zero); YTD compõe todos os dias do ano.
        """
        r = self.returns().dropna()
        cols = MONTH_LABELS + [YTD_LABEL]
        if r.empty:
            return pd.DataFrame(columns=cols, index=pd.Index([], name="ano", dtype=int))
        growth = 1.0 + r
        monthly = growth.groupby([r.index.year, r.index.month]).prod() - 1.0
        yearly = growth.groupby(r.index.year).prod() - 1.0
        years = sorted({int(y) for y in r.index.year})
        table = pd.DataFrame(np.nan, index=pd.Index(years, name="ano"), columns=cols)
        for (y, m), v in monthly.items():
            table.loc[int(y), MONTH_LABELS[int(m) - 1]] = float(v)
        for y, v in yearly.items():
            table.loc[int(y), YTD_LABEL] = float(v)
        return table

    def stats(self, cfg: FundConfig | None = None) -> dict[str, Any]:
        """Estatísticas desde o início: retorno, retorno e vol anualizados, Sharpe sobre o caixa
        (USD 3M via financiamento registrado), drawdown máximo e atual, % de dias positivos,
        melhor/pior dia e vol realizada vs. banda do mandato.

        Itens sem histórico suficiente ficam ``None``. A anualização com menos de um ano de
        histórico é indicada em ``annualization_note``.
        """
        cfg = cfg or FundConfig()
        band = (cfg.risk.vol_band_min, cfg.risk.vol_band_max)
        f = self.frame()
        out: dict[str, Any] = {
            "n_days": int(len(f)), "first_date": None, "last_date": None,
            "nav_start": None, "nav_end": None, "since_inception_return": None,
            "annualized_return": None, "annualized_vol": None, "sharpe": None,
            "max_drawdown": None, "current_drawdown": None, "pct_positive_days": None,
            "best_day": None, "worst_day": None, "realized_vol_21d": None,
            "realized_vol_63d": None, "vol_band": band, "realized_vol_status": "histórico insuficiente",
            "annualization_note": "",
        }
        if f.empty:
            return out
        r = f["ret"].astype(float)
        n = len(r)
        nav0 = float(f["nav"].iloc[0] - f["pnl"].iloc[0])
        total = float((1.0 + r).prod() - 1.0)
        out.update({
            "first_date": f.index[0].date(), "last_date": f.index[-1].date(),
            "nav_start": nav0, "nav_end": float(f["nav"].iloc[-1]),
            "since_inception_return": total,
            "annualized_return": float((1.0 + total) ** (TRADING_DAYS / n) - 1.0)
            if total > -1.0 else None,
            "pct_positive_days": float((r > 0).mean()),
            "best_day": (f.index[int(np.argmax(r.to_numpy()))].date(), float(r.max())),
            "worst_day": (f.index[int(np.argmin(r.to_numpy()))].date(), float(r.min())),
        })
        if n < TRADING_DAYS:
            out["annualization_note"] = (f"Anualização com {n} pregão(ões) (< {TRADING_DAYS}): "
                                         "valores anualizados são pouco informativos.")
        if n >= 2:
            vol = float(r.std(ddof=1) * math.sqrt(TRADING_DAYS))
            out["annualized_vol"] = vol
            nav_open = (f["nav"] - f["pnl"]).astype(float)
            cash = f["financing"].astype(float) / nav_open
            excess = r - cash
            if excess.notna().all():
                sd = float(excess.std(ddof=1))
                out["sharpe"] = (float(excess.mean() / sd * math.sqrt(TRADING_DAYS))
                                 if sd > 0 else None)
        dd = drawdown_series(nav0, f["nav"])
        out["max_drawdown"] = float(dd.min())
        out["current_drawdown"] = float(dd.iloc[-1])
        out["realized_vol_21d"] = realized_vol(r, REALIZED_VOL_WINDOWS[0])
        out["realized_vol_63d"] = realized_vol(r, REALIZED_VOL_WINDOWS[1])
        rv = out["realized_vol_21d"]
        if rv is not None:
            out["realized_vol_status"] = ("abaixo da banda" if rv < band[0]
                                          else "acima da banda" if rv > band[1]
                                          else "dentro da banda")
        return out

    # ---------------------------------------------- integridade
    def verify(self) -> tuple[bool, list[str]]:
        """Recalcula hashes, confere elos, datas, CSV × JSON e a trilha de auditoria."""
        problems: list[str] = []
        records: list[DailyRecord] = []
        prev_hash: str | None = GENESIS_RECORD_HASH
        prev_date: date | None = None
        for d, path in self._record_files():
            try:
                rec = self._load(path)
            except ValueError as exc:
                problems.append(f"{path.name}: registro ilegível ({str(exc)[:200]}).")
                prev_hash = None
                continue
            records.append(rec)
            if rec.date != d:
                problems.append(f"{path.name}: contém o registro de {rec.date} (arquivo renomeado "
                                "ou reordenado).")
            if rec.compute_hash() != rec.record_hash:
                problems.append(f"{rec.date}: conteúdo adulterado (record_hash não confere).")
            if prev_hash is not None and rec.prev_record_hash != prev_hash:
                problems.append(f"{rec.date}: encadeamento quebrado (registro anterior removido, "
                                "alterado ou fora de ordem).")
            if prev_date is not None and rec.date <= prev_date:
                problems.append(f"{rec.date}: data não posterior ao registro anterior ({prev_date}).")
            prev_hash = rec.record_hash
            prev_date = rec.date

        try:
            rows = self._csv_rows()
        except ValueError as exc:
            problems.append(str(exc))
            rows = []
        if len(rows) != len(records):
            problems.append(f"CSV com {len(rows)} linha(s) para {len(records)} registro(s) JSON.")
        for row, rec in zip(rows, records, strict=False):
            expected = record_summary(rec)
            if row.get("date") != expected["date"] or row.get("record_hash") != rec.record_hash:
                problems.append(f"CSV divergente do JSON em {rec.date} (data/hash).")
                continue
            for col in FLOAT_COLUMNS:
                try:
                    got = _parse_float(row.get(col, ""))
                except ValueError:
                    got = math.nan
                want = expected[col]
                if (got is None) != (want is None) or (
                        got is not None and want is not None and got != float(want)):
                    problems.append(f"CSV divergente do JSON em {rec.date} (coluna {col}).")
                    break

        ok_chain, msg = self.audit.verify_chain()
        if not ok_chain:
            problems.append(f"Trilha de auditoria: {msg}")
        audited = {ev.payload_hash for ev in self.audit.events()
                   if ev.event_type == self.audit_event}
        expected_hashes = {sha256_obj(rec.record_hash) for rec in records}
        for rec in records:
            if sha256_obj(rec.record_hash) not in audited:
                problems.append(f"{rec.date}: registro sem evento {self.audit_event} na trilha.")
        orphan = audited - expected_hashes
        if orphan:
            problems.append(f"{len(orphan)} evento(s) {self.audit_event} na trilha sem registro "
                            "correspondente (registro removido ou substituído).")
        return (not problems, problems)


def compare_tracks(main: TrackRecord, shadow: TrackRecord) -> pd.DataFrame:
    """NAV e retornos do CDP vs. carteira-sombra só-quant nas datas comuns, com valor agregado.

    ``value_added`` = retorno diário do CDP − retorno da sombra; ``cum_value_added`` é a razão
    dos crescimentos acumulados menos 1 (desde a primeira data comum).
    """
    a = main.frame()
    b = shadow.frame()
    cols = ["nav_cdp", "nav_shadow", "ret_cdp", "ret_shadow", "value_added", "cum_value_added"]
    if a.empty or b.empty:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="date"))
    common = a.index.intersection(b.index)
    out = pd.DataFrame({
        "nav_cdp": a.loc[common, "nav"], "nav_shadow": b.loc[common, "nav"],
        "ret_cdp": a.loc[common, "ret"], "ret_shadow": b.loc[common, "ret"],
    }, index=common)
    out["value_added"] = out["ret_cdp"] - out["ret_shadow"]
    out["cum_value_added"] = ((1.0 + out["ret_cdp"]).cumprod()
                              / (1.0 + out["ret_shadow"]).cumprod() - 1.0)
    out.index.name = "date"
    return out[cols]
