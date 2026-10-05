"""Ledger de NAV (CSV append-only) e marcação a mercado da carteira efetivada.

Convenções do P&L diário (datas em ``(start, end]``, sem look-ahead):

- **Ações (buy-and-hold):** cada posição efetivada carrega um nocional assinado em USD
  (sinal do ``weight``) na sua linha de execução. ``pnl_eq_t = Σ n_{i,t-1} · r_{i,t}`` e o
  nocional deriva com o retorno: ``n_{i,t} = n_{i,t-1} · (1 + r_{i,t})``.
- **Retorno ausente (``NaN``):** a posição simplesmente não é reprecificada naquele dia — o
  nocional é mantido e o P&L do dia é zero *por falta de preço*, nunca por um retorno
  inventado. Como o painel calcula o retorno seguinte contra o último preço válido, o
  movimento do período sem preço entra integralmente no próximo pregão da linha. A contagem
  de linhas não reprecificadas fica registrada em ``LedgerRow.note``.
- **Financiamento:** o caixa/colateral rende a taxa curta em USD:
  ``nav_{t-1} · taxa / 252``, com a taxa conhecida no pregão anterior (sem look-ahead). Sem
  taxa disponível — ou com a última taxa defasada em mais de ``RATE_STALE_DAYS_MAX`` dias
  corridos — o financiamento não é apurado (``financing_usd = None``) e isso é anotado. Taxas
  acima de 100% a.a. são tratadas como erro de unidade (percentual em vez de decimal).
- **Aluguel (shorts):** ``-Σ |n_{i,t-1}| · fee_i / 252`` registrado em ``cost_usd``. Short sem
  taxa informada recebe a taxa padrão conservadora ``DEFAULT_BORROW_FEE_ANNUAL`` (anotada).
- **Atribuição (opcional, com ``model``):** exposições B fixas na data do booking (o modelo
  precisa ter ``as_of <= start``; um modelo estimado depois do booking seria look-ahead);
  ``factor_pnl_t = Σ_i n_{i,t-1} · (B_i · f_t)`` e ``specific = pnl_eq - factor_pnl``.
  Os retornos fatoriais ``f_t`` vêm de ``model.factor_returns`` quando cobrem a data; senão,
  de uma regressão cross-section dos ``issuer_returns`` do dia sobre B (pesos 1/variância
  específica). Para posições não reprecificadas, o retorno fatorial fica pendente e é
  reconhecido junto com o retorno acumulado no próximo pregão da linha.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ..contracts import BookedPosition, BookEntry, LedgerRow
from ..risk.types import TRADING_DAYS, RiskModel
from .memo import fmt_pct, fmt_usd

LEDGER_COLUMNS: list[str] = list(LedgerRow.model_fields)
_REQUIRED_FLOATS = ("nav_usd", "pnl_usd", "ret", "gross", "net")
_OPTIONAL_FLOATS = ("factor_pnl_usd", "specific_pnl_usd", "cost_usd", "financing_usd")

DEFAULT_BORROW_FEE_ANNUAL = 0.02
"""Taxa de aluguel anual padrão (conservadora, acima do GC dos EUA e da B3) para shorts sem taxa."""

MIN_XS_DOF = 5
"""Graus de liberdade mínimos (observações − posto de B) na regressão cross-section diária."""

RATE_STALE_DAYS_MAX = 10
"""Defasagem máxima (dias corridos) da taxa de financiamento usada; acima disso é ausente."""

MAX_PLAUSIBLE_RATE = 1.0
"""Taxa anual (decimal) acima da qual o valor é tratado como erro de unidade (ex.: 5.04 = %)."""

NAV_START_RATIO_RANGE = (0.5, 2.0)
"""Faixa plausível de ``nav_start / booked.nav_usd``: fora dela, erro de unidade/escala."""

_MAX_TICKERS_IN_NOTE = 5


# ==========================================================
# Ledger CSV
# ==========================================================

def _to_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _from_record(rec: dict[str, str]) -> LedgerRow:
    data: dict[str, object] = {}
    for col in LEDGER_COLUMNS:
        raw = rec.get(col, "")
        if col == "note":
            data[col] = raw or ""
        else:
            data[col] = None if raw in ("", None) else raw
    return LedgerRow.model_validate(data)


def _check_finite(row: LedgerRow) -> None:
    for col in _REQUIRED_FLOATS:
        if not math.isfinite(getattr(row, col)):
            raise ValueError(f"Linha do ledger em {row.date} com '{col}' não finito.")
    for col in _OPTIONAL_FLOATS:
        v = getattr(row, col)
        if v is not None and not math.isfinite(v):
            raise ValueError(f"Linha do ledger em {row.date} com '{col}' não finito "
                             "(use None para ausente).")


class Ledger:
    """Série de NAV diária em CSV, somente anexação, com datas estritamente crescentes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def rows(self) -> list[LedgerRow]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is not None and list(reader.fieldnames) != LEDGER_COLUMNS:
                raise ValueError(f"Cabeçalho do ledger inesperado em {self.path}: "
                                 f"{reader.fieldnames}")
            return [_from_record(rec) for rec in reader]

    def frame(self) -> pd.DataFrame:
        """Ledger como DataFrame indexado por data (ausentes como ``NaN``, nunca zero)."""
        rows = self.rows()
        cols = [c for c in LEDGER_COLUMNS if c != "date"]
        if not rows:
            return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="date"))
        df = pd.DataFrame([r.model_dump() for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        for c in _REQUIRED_FLOATS + _OPTIONAL_FLOATS:
            df[c] = pd.to_numeric(df[c], errors="raise").astype(float)
        return df[cols]

    def last_row(self) -> LedgerRow | None:
        rows = self.rows()
        return rows[-1] if rows else None

    def last_date(self) -> date | None:
        last = self.last_row()
        return last.date if last else None

    def last_nav(self) -> float | None:
        last = self.last_row()
        return last.nav_usd if last else None

    def append(self, rows: Iterable[LedgerRow]) -> int:
        """Anexa linhas; recusa datas repetidas ou fora de ordem e valores não finitos."""
        new = [LedgerRow.model_validate(r) for r in rows]
        if not new:
            return 0
        prev = self.last_date()
        for row in new:
            _check_finite(row)
            if prev is not None and row.date <= prev:
                kind = "duplicada" if row.date == prev else "fora de ordem"
                raise ValueError(f"Data {row.date} {kind} no ledger (última: {prev}).")
            prev = row.date
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        write_header = not self.path.exists() or self.path.stat().st_size == 0
        if write_header:
            writer.writerow(LEDGER_COLUMNS)
        for row in new:
            dump = row.model_dump()
            writer.writerow([_to_cell(dump[c]) for c in LEDGER_COLUMNS])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
        return len(new)


# ==========================================================
# Retornos fatoriais ex-post
# ==========================================================

def cross_sectional_factor_returns(exposures: pd.DataFrame, returns: pd.Series,
                                   specific_var: pd.Series | None = None,
                                   min_dof: int = MIN_XS_DOF) -> pd.Series | None:
    """Retornos fatoriais de um dia por regressão WLS de ``returns`` sobre ``exposures``.

    Pesos = 1/variância específica (quando informada e válida). Usa a solução de norma mínima
    (``lstsq``), de modo que fatores colineares (mercado × países) não impedem o cálculo: os
    valores ajustados ``B·f`` — que são o que importa para a atribuição — são únicos.
    Retorna ``None`` quando ``n_obs − posto(B) < min_dof`` (dados insuficientes).
    """
    r = pd.to_numeric(returns.reindex(exposures.index), errors="coerce")
    finite_b = np.isfinite(exposures.to_numpy(dtype=float)).all(axis=1)
    ok = r.notna().to_numpy() & finite_b
    if specific_var is not None:
        sv = specific_var.reindex(exposures.index).to_numpy(dtype=float)
        valid_w = np.isfinite(sv) & (sv > 0)
        ok &= valid_w
        w = np.where(valid_w, 1.0 / np.where(valid_w, sv, 1.0), np.nan)
    else:
        w = np.ones(len(exposures))
    if not ok.any():
        return None
    X = exposures.to_numpy(dtype=float)[ok]
    y = r.to_numpy(dtype=float)[ok]
    sw = np.sqrt(w[ok])
    Xw = X * sw[:, None]
    yw = y * sw
    rank = int(np.linalg.matrix_rank(Xw)) if Xw.size else 0
    if len(y) - rank < min_dof:
        return None
    f, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
    return pd.Series(f, index=exposures.columns)


def _factor_return_path(model: RiskModel, issuer_returns: pd.DataFrame | None,
                        dates: pd.DatetimeIndex) -> tuple[np.ndarray, list[str]]:
    """Matriz T×K de retornos fatoriais (linhas ``NaN`` quando indisponíveis) e a origem."""
    names = model.factor_names
    frame = model.factor_returns.copy()
    frame.index = pd.DatetimeIndex(frame.index)
    fr = frame.reindex(index=dates, columns=names).to_numpy(dtype=float, copy=True)
    source = ["modelo" if np.isfinite(row).all() else "" for row in fr]
    if issuer_returns is not None:
        ir = issuer_returns.copy()
        ir.index = pd.DatetimeIndex(ir.index)
        ir = ir.sort_index()
        for t, ts in enumerate(dates):
            if source[t] or ts not in ir.index:
                continue
            est = cross_sectional_factor_returns(model.exposures, ir.loc[ts],
                                                 model.specific_var)
            if est is not None:
                fr[t] = est.reindex(names).to_numpy(dtype=float)
                source[t] = "regressão"
    for t, s in enumerate(source):
        if not s:
            fr[t] = np.nan
    return fr, source


# ==========================================================
# Marcação a mercado
# ==========================================================

def _signed_notional(p: BookedPosition) -> float:
    if not math.isfinite(p.notional_usd) or not math.isfinite(p.weight):
        raise ValueError(f"Posição {p.issuer_id}/{p.ticker} com nocional ou peso não finito.")
    if p.notional_usd == 0:
        raise ValueError(f"Posição {p.issuer_id}/{p.ticker} com peso não nulo e nocional zero.")
    return math.copysign(abs(p.notional_usd), p.weight)


def _rate_path(financing_rate: pd.Series | float,
               prev_dates: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Taxa anual vigente no início de cada dia e máscara de taxas defasadas.

    Usa o último valor conhecido em cada data de ``prev_dates`` (sem look-ahead). Valores com
    mais de ``RATE_STALE_DAYS_MAX`` dias corridos viram ``NaN`` (ausente, nunca reaproveitados
    indefinidamente). Taxas acima de ``MAX_PLAUSIBLE_RATE`` levantam ``ValueError``.
    """
    n = len(prev_dates)
    stale = np.zeros(n, dtype=bool)
    if isinstance(financing_rate, pd.Series):
        s = pd.to_numeric(financing_rate, errors="coerce").dropna()
        if s.empty:
            return np.full(n, np.nan), stale
        s.index = pd.DatetimeIndex(s.index)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        pos = s.index.searchsorted(prev_dates, side="right") - 1
        known = pos >= 0
        safe = np.clip(pos, 0, None)
        rates = np.where(known, s.to_numpy(dtype=float)[safe], np.nan)
        age = np.asarray((prev_dates - s.index[safe]).days)
        stale = known & (age > RATE_STALE_DAYS_MAX)
    else:
        value = float(financing_rate)
        rates = np.full(n, value if math.isfinite(value) else np.nan)
    used = rates[np.isfinite(rates)]
    if used.size and float(np.abs(used).max()) > MAX_PLAUSIBLE_RATE:
        raise ValueError("Taxa de financiamento acima de 100% a.a.: parece estar em % — informe "
                         "em decimal (0.05 = 5% a.a.).")
    return np.where(stale, np.nan, rates), stale


def _lookup_fee(borrow_fees: pd.Series, key: str) -> float:
    """Taxa anual válida (finita e >= 0) para ``key``; ``NaN`` se ausente ou inválida."""
    if key not in borrow_fees.index:
        return math.nan
    value = borrow_fees.loc[key]
    if isinstance(value, pd.Series):
        raise ValueError(f"Taxa de aluguel duplicada para '{key}'.")
    num = pd.to_numeric(value, errors="coerce")
    return float(num) if pd.notna(num) and float(num) >= 0 else math.nan


def _borrow_fee_vector(positions: list[BookedPosition], borrow_fees: pd.Series | None,
                       default_fee: float) -> tuple[np.ndarray, list[str], list[str]]:
    """Taxas anuais por posição, shorts com taxa padrão e shorts com taxa implausível (> 100%)."""
    fees = np.empty(len(positions))
    defaulted: list[str] = []
    suspicious: list[str] = []
    for k, p in enumerate(positions):
        fee = math.nan
        if borrow_fees is not None:
            for key in (p.ticker, p.issuer_id):
                fee = _lookup_fee(borrow_fees, key)
                if math.isfinite(fee):
                    break
        if not math.isfinite(fee):
            fee = default_fee
            if p.weight < 0:
                defaulted.append(p.ticker)
        elif p.weight < 0 and fee > MAX_PLAUSIBLE_RATE:
            suspicious.append(p.ticker)
        fees[k] = fee
    return fees, defaulted, suspicious


def _list_tickers(tickers: list[str]) -> str:
    head = ", ".join(tickers[:_MAX_TICKERS_IN_NOTE])
    extra = len(tickers) - _MAX_TICKERS_IN_NOTE
    return head + (f" (+{extra})" if extra > 0 else "")


def mark_to_market(booked: BookEntry, line_returns: pd.DataFrame, start: date, end: date,
                   nav_start: float, financing_rate: pd.Series | float,
                   borrow_fees: pd.Series | None, model: RiskModel | None = None,
                   issuer_returns: pd.DataFrame | None = None, *,
                   execution_cost_usd: float | None = None,
                   default_borrow_fee: float = DEFAULT_BORROW_FEE_ANNUAL) -> list[LedgerRow]:
    """P&L diário buy-and-hold da carteira efetivada nas datas ``(start, end]``.

    ``line_returns`` é ``AssetPanel.line_returns`` (retorno total diário em USD por ticker).
    ``financing_rate`` é a taxa curta anual em USD (escalar ou série por data);
    ``borrow_fees`` é a taxa anual de aluguel indexada por ticker ou ``issuer_id``.
    ``execution_cost_usd`` (positivo = custo), quando informado, é debitado no primeiro dia.
    Ver o docstring do módulo para as convenções de dados ausentes e atribuição.
    """
    if end <= start:
        raise ValueError("O fim do período de marcação precisa ser posterior ao início.")
    if not (math.isfinite(nav_start) and nav_start > 0):
        raise ValueError("NAV inicial precisa ser positivo e finito.")
    if not (math.isfinite(booked.nav_usd) and booked.nav_usd > 0):
        raise ValueError("NAV do booking precisa ser positivo e finito.")
    lo, hi = NAV_START_RATIO_RANGE
    if not (lo <= nav_start / booked.nav_usd <= hi):
        raise ValueError(f"NAV inicial ({fmt_usd(nav_start)}) incompatível com o NAV do booking "
                         f"({fmt_usd(booked.nav_usd)}); conferir unidade/escala.")
    if not (math.isfinite(default_borrow_fee) and 0 <= default_borrow_fee <= MAX_PLAUSIBLE_RATE):
        raise ValueError("Taxa de aluguel padrão precisa ser decimal anual entre 0 e 1.")
    if model is not None and model.as_of > start:
        raise ValueError(f"Modelo de risco de {model.as_of} é posterior ao booking ({start}): "
                         "exposições fora da data do booking seriam look-ahead.")
    if line_returns.index.has_duplicates:
        raise ValueError("Retornos por linha com datas duplicadas.")
    positions = [p for p in booked.positions if p.weight != 0]
    tickers = [p.ticker for p in positions]
    missing = sorted(set(tickers) - set(line_returns.columns))
    if missing:
        raise KeyError(f"Sem série de retornos para as linhas efetivadas: {missing}")

    lr = line_returns.sort_index()
    idx = pd.DatetimeIndex(lr.index)
    mask = (idx > pd.Timestamp(start)) & (idx <= pd.Timestamp(end))
    dates = idx[mask]
    if len(dates) == 0:
        return []
    R = lr.loc[mask, tickers].to_numpy(dtype=float) if tickers else np.empty((len(dates), 0))
    valid = np.isfinite(R)
    n0 = np.array([_signed_notional(p) for p in positions], dtype=float)
    growth = np.where(valid, 1.0 + np.where(valid, R, 0.0), 1.0)
    n_end = n0[None, :] * np.cumprod(growth, axis=0)
    n_prev = np.vstack([n0[None, :], n_end[:-1]])
    eq_pnl = np.where(valid, n_prev * np.where(valid, R, 0.0), 0.0).sum(axis=1)

    fees, defaulted, suspicious = _borrow_fee_vector(positions, borrow_fees,
                                                     default_borrow_fee)
    borrow = -(np.where(n_prev < 0, -n_prev, 0.0) * fees[None, :]).sum(axis=1) / TRADING_DAYS
    prev_dates = pd.DatetimeIndex([pd.Timestamp(start)]).append(dates[:-1])
    rates, stale_rate = _rate_path(financing_rate, prev_dates)

    # Atribuição fatorial (exposições fixas na data do booking).
    H = None
    has_b = np.zeros(len(positions), dtype=bool)
    sources: list[str] = [""] * len(dates)
    if model is not None:
        B_pos = model.exposures.reindex([p.issuer_id for p in positions]).to_numpy(dtype=float)
        has_b = np.isfinite(B_pos).all(axis=1)
        F, sources = _factor_return_path(model, issuer_returns, dates)
        # Linhas sem exposição e dias sem fatores são mascarados: não entram na atribuição.
        B_ok = np.where(has_b[:, None], B_pos, 0.0)
        F_ok = np.where(np.isfinite(F), F, 0.0)
        H = F_ok @ B_ok.T
        H[:, ~has_b] = np.nan
    pending = np.zeros(len(positions))

    rows: list[LedgerRow] = []
    nav_prev = float(nav_start)
    for t, ts in enumerate(dates):
        notes: list[str] = []
        stale = [tickers[k] for k in np.flatnonzero(~valid[t])]
        if stale:
            notes.append(f"{len(stale)} linha(s) sem retorno no dia (posição não reprecificada; "
                         f"nocional mantido): {_list_tickers(stale)}")
        rate = rates[t]
        if np.isfinite(rate):
            financing: float | None = nav_prev * float(rate) / TRADING_DAYS
        else:
            financing = None
            if stale_rate[t]:
                notes.append(f"taxa de financiamento defasada (> {RATE_STALE_DAYS_MAX} dias): "
                             "financiamento não apurado")
            else:
                notes.append("taxa de financiamento indisponível: financiamento não apurado")
        cost = float(borrow[t])
        if defaulted and (n_prev[t] < 0).any():
            notes.append(f"aluguel padrão conservador de {fmt_pct(default_borrow_fee)} a.a. "
                         f"para short(s) sem taxa: {_list_tickers(defaulted)}")
        if suspicious:
            notes.append("taxa de aluguel acima de 100% a.a. (conferir unidade decimal): "
                         f"{_list_tickers(suspicious)}")
        if t == 0 and execution_cost_usd is not None:
            if not math.isfinite(execution_cost_usd):
                raise ValueError("Custo de execução informado não é finito.")
            cost -= abs(float(execution_cost_usd))
            notes.append("custo de execução estimado debitado: "
                         f"{fmt_usd(abs(execution_cost_usd))}")

        factor_pnl: float | None = None
        specific_pnl: float | None = None
        if model is not None and H is not None:
            realized = valid[t] & has_b
            if sources[t]:
                contrib = n_prev[t] * (pending + H[t])
                factor_pnl = float(contrib[realized].sum())
                specific_pnl = float(eq_pnl[t]) - factor_pnl
                waiting = ~valid[t] & has_b
                pending[waiting] += H[t][waiting]
                if sources[t] == "regressão":
                    notes.append("fatores estimados por regressão cross-section (B do booking)")
            else:
                notes.append("retornos fatoriais indisponíveis: atribuição não calculada")
            pending[realized] = 0.0
            outside = int((~has_b).sum())
            if outside:
                notes.append(f"{outside} posição(ões) fora do modelo de risco: P&L no específico")

        pnl = float(eq_pnl[t]) + (financing or 0.0) + cost
        nav = nav_prev + pnl
        if not (math.isfinite(nav) and nav > 0):
            raise ValueError(f"NAV não positivo em {ts.date()}: marcação interrompida.")
        rows.append(LedgerRow(
            date=ts.date(), nav_usd=nav, pnl_usd=pnl, ret=pnl / nav_prev,
            gross=float(np.abs(n_end[t]).sum()) / nav, net=float(n_end[t].sum()) / nav,
            factor_pnl_usd=factor_pnl, specific_pnl_usd=specific_pnl, cost_usd=cost,
            financing_usd=financing, note="; ".join(notes),
        ))
        nav_prev = nav
    return rows
