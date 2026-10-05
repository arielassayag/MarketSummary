"""Rotina diária do CDP — Cabra da Peste: execução MOC, marcação a mercado, risco, atribuição e
alertas, gravando um ``DailyRecord`` imutável e encadeado por hash no track record.

Convenção de execução (``fund.execution_convention``)
-----------------------------------------------------
A carteira da semana é decidida no primeiro pregão da semana na B3 (segunda, ou o próximo dia
útil se for feriado) ANTES do fechamento, com dados até o pregão anterior, e executada no
FECHAMENTO desse mesmo pregão (MOC). No pregão de decisão D a rotina diária:

1. apura o P&L do dia da carteira ANTIGA, do fechamento anterior ao fechamento de D — a carteira
   nova não participa do P&L de D;
2. executa a carteira decidida no fechamento de D: nocional-alvo = peso × NAV(D) antes dos custos,
   na linha de execução; ações = nocional / preço de fechamento local / câmbio (arredondadas à
   unidade, meio para longe de zero); custos de transação do modelo de custos são debitados em D;
3. grava o ``BookEntry`` (``booked_at`` = fechamento de D) e as posições de fim de dia do registro
   passam a ser as da carteira NOVA (linhas encerradas aparecem com valor zero e o P&L do dia).

No primeiro registro (inception) não há carteira antiga: o NAV parte de
``fund.inception_nav_usd`` na abertura de D e o P&L do dia são apenas os custos.

A decisão precisa ter sido gravada até o fechamento do pregão de execução (``decided_at``); uma
decisão posterior ao fechamento só é executada no pregão seguinte, e nunca fora da própria
semana (:func:`executable_in`). Decisões autônomas são conferidas com
:func:`~latam_ls.workflow.autonomy.verify_autonomous_decision`; humanas, com
:func:`~latam_ls.workflow.approval.verify_decision` — sempre contra o mandato ATUAL. A efetivação
é gravada pelo próprio livro (``Book.save_proposal``/``save_decision``/``save_booked``, que
revalida a aprovação, a carteira aprovada, a cronologia e o KILL_SWITCH).

Contas do dia (USD)
-------------------
- As posições derivam com os preços entre rebalanceamentos: o valor de mercado inicial vem das
  posições de fim de dia do registro anterior.
- P&L da linha = valor inicial × retorno total em USD da linha no período
  (``AssetPanel.line_returns`` composto nas sessões após o registro anterior). Retorno ausente ⇒
  a linha não negociou: P&L 0, ``repriced=False``, valor mantido e alerta (nunca um retorno
  inventado); o movimento entra integralmente quando a linha voltar a negociar.
- Financiamento = NAV inicial × USD_3M (taxa conhecida no pregão anterior) / 360 × dias corridos
  desde o registro anterior (ACT/360; juros do caixa/colateral).
- Aluguel = − Σ |valor inicial dos shorts| × taxa anual / 360 × dias (taxa da proposta efetivada;
  senão a tabela de aluguel do dia; senão a taxa padrão conservadora, com alerta).
- Custos = custos de transação estimados das negociações do dia (negativos).
- NAV final = NAV inicial + ações + financiamento + aluguel + custos.

Atribuição
----------
Exposições do modelo de risco estimado na sessão ANTERIOR × retornos fatoriais do período (da
regressão cross-section de cada sessão no modelo estimado hoje; se a sessão não tiver retornos
fatoriais, regressão do dia com as mesmas exposições). Linha que voltou a negociar recebe os
retornos fatoriais de todas as sessões desde o seu último preço válido. ``específico = ações −
fatores`` por construção (soma exata). Linhas por componente, grupo de fatores, fator, emissor,
país, setor e lado (long × short); ``contribution`` = P&L / NAV inicial.

Carteira-sombra só-quant
------------------------
A proposta ``WeeklyOutcome.shadow_quant`` é "executada" do mesmo modo numa segunda série
(``book/track_record_shadow``), sem decisão: mede, dia a dia, o valor agregado pelo PM do CDP
em relação ao quant puro (:func:`~latam_ls.workflow.track_record.compare_tracks`).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..analytics.liquidity import liquidity_profile, liquidity_summary
from ..analytics.panel import STALE_DAYS_MAX, AssetPanel, build_asset_panel, fx_for_lines
from ..analytics.shortability import issuer_side_lines, short_availability
from ..analytics.squeeze import squeeze_table
from ..config import FundConfig
from ..contracts import (
    AttributionLine,
    BookedPosition,
    BookEntry,
    DailyPosition,
    DailyRecord,
    DailyRisk,
    Decision,
    DecisionMode,
    DecisionType,
    ExposureLine,
    Proposal,
    Side,
)
from ..hashing import sha256_file, sha256_obj, sha256_text
from ..market import MarketData
from ..portfolio.costs import CostModel, build_cost_model, estimate_rebalance_costs
from ..risk.analytics import (
    historical_var_es,
    parametric_var_es,
    predicted_betas,
    risk_decomposition,
)
from ..risk.event_scaling import apply_event_windows
from ..risk.exposures import market_weights
from ..risk.model import estimate_risk_model
from ..risk.types import STYLE_FACTORS, RiskModel
from .approval import verify_decision
from .autonomy import verify_autonomous_decision
from .book import Book, dump_json
from .ledger import DEFAULT_BORROW_FEE_ANNUAL, cross_sectional_factor_returns
from .memo import fmt_days, fmt_num, fmt_pct, fmt_usd, fmt_usd_mm
from .track_record import (
    GENESIS_RECORD_HASH,
    REALIZED_VOL_WINDOWS,
    SHADOW_RECORD_EVENT,
    TrackRecord,
    realized_vol,
    write_exclusive,
)

MARKET_CLOSE_LOCAL = time(17, 0)
"""Fechamento usado na execução MOC (17h de Brasília = fechamento da B3 e da NYSE em out/2026)."""
DAY_COUNT_BASIS = 360.0
FINANCING_RATE_SERIES = "USD_3M"
RATE_STALE_DAYS = 10
RATE_PLAUSIBLE_RANGE = (-0.02, 0.25)
"""Faixa plausível da taxa anual em decimal; fora dela (ex.: 4.5 = taxa em %) a taxa é recusada."""
MAX_ALERT_TEXT = 300
ENTRY_LOOKBACK_RECORDS = 260
"""Registros consultados (do mais recente para trás) para o preço médio de entrada dos shorts."""
HOLD_STATUS = "hold"
DAILY_ACTOR = "CDP — rotina diária"
SHADOW_LABEL = "sombra só-quant"
SHADOW_BOOKED_EVENT = "BOOKED_SHADOW"
SHADOW_PROPOSAL_EVENT = "SHADOW_PROPOSAL_SAVED"
BOOK_SHADOW_FILE = "shadow_quant.json"
"""Proposta-sombra gravada pelo pipeline semanal em ``<livro>/<semana>/`` (evento SHADOW_QUANT)."""
BOOK_SHADOW_EVENT = "SHADOW_QUANT"
COMPONENTS = ("equity", "factor", "specific", "financing", "borrow", "costs")
FACTOR_GROUPS = ("market", "country", "sector", "style")
_MAX_LISTED = 8


class NoSessionError(ValueError):
    """Não houve pregão na data (sem preços de fechamento no armazenamento de mercado)."""


class NoBookError(ValueError):
    """Não há carteira efetivada para iniciar (ou continuar) o track record."""


class ExecutionRefused(ValueError):
    """A execução MOC da decisão foi recusada (livro, KILL_SWITCH, preço/câmbio ausente).

    Na rotina diária com carteira vigente, a recusa NÃO interrompe o track record: o dia é
    registrado com a carteira anterior e um alerta com o motivo (nenhuma negociação ocorreu).
    """


class MarketSource(Protocol):
    """Fonte de dados de mercado sem look-ahead (ex.: ``latam_ls.data.store.MarketStore``)."""

    def load(self, as_of: date) -> MarketData: ...


# ==========================================================
# Contêineres públicos
# ==========================================================

@dataclass(frozen=True)
class PendingExecution:
    """Decisão da semana a executar no fechamento (proposta final, decisão e sombra só-quant)."""

    proposal: Proposal
    decision: Decision
    shadow: Proposal | None = None
    snapshot_hash_now: str | None = None

    @property
    def week(self) -> date:
        return self.proposal.week

    @classmethod
    def from_outcome(cls, outcome: Any, snapshot_hash_now: str | None = None) -> PendingExecution:
        """A partir de ``weekly.WeeklyOutcome`` (``final``, ``decision``, ``shadow_quant``)."""
        return cls(proposal=outcome.final, decision=outcome.decision,
                   shadow=outcome.shadow_quant, snapshot_hash_now=snapshot_hash_now)


@dataclass
class DailyContext:
    """Insumos da sessão, todos com dados até ``date`` (sem look-ahead).

    ``model`` é o modelo de risco estimado na própria sessão (retornos fatoriais do dia);
    ``risk_model`` é o mesmo modelo com as janelas de evento do mandato (risco ex-ante);
    ``model_prev`` é o modelo da sessão anterior (exposições usadas na atribuição).
    """

    date: date
    md: MarketData
    panel: AssetPanel
    model: RiskModel | None
    book_entry: BookEntry | None
    prev: DailyRecord | None
    model_prev: RiskModel | None = None
    risk_model: RiskModel | None = None
    notes: list[str] = field(default_factory=list)
    cache: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def ts(self) -> pd.Timestamp:
        return pd.Timestamp(self.date)


@dataclass(frozen=True)
class DailyRunResult:
    record: DailyRecord
    shadow: DailyRecord | None = None
    booked: BookEntry | None = None
    shadow_booked: BookEntry | None = None

    @property
    def value_added(self) -> float | None:
        """Retorno do dia do CDP menos o da sombra só-quant (``None`` sem sombra)."""
        return None if self.shadow is None else self.record.ret - self.shadow.ret


# ==========================================================
# Utilidades puras
# ==========================================================

def close_datetime(session: date, cfg: FundConfig) -> datetime:
    """Horário (com fuso) do fechamento usado como ``booked_at`` da execução MOC."""
    return datetime.combine(session, MARKET_CLOSE_LOCAL, tzinfo=ZoneInfo(cfg.fund.timezone))


def executable_in(week: date, session: date) -> bool:
    """A decisão da semana ``week`` (primeiro pregão da B3 na semana) é executável no fechamento
    de ``session``: mesmo calendário semanal e ``session`` ≥ ``week``."""
    monday = week - timedelta(days=week.weekday())
    return week <= session and monday == session - timedelta(days=session.weekday())


def session_has_prices(md: MarketData, session: date) -> bool:
    ts = pd.Timestamp(session)
    return ts in md.close.index and bool(md.close.loc[ts].notna().any())


def session_dates(md: MarketData, start: date, end: date) -> list[date]:
    """Pregões (datas com algum preço de fechamento) em ``[start, end]``."""
    idx = md.close.index
    has = md.close.notna().any(axis=1)
    mask = (idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end)) & has.to_numpy()
    return [ts.date() for ts in idx[mask]]


def store_input_hashes(store: object, session: date) -> dict[str, str]:
    """Hashes dos manifestos do armazenamento (base e incremento do dia), quando existirem.

    Segue o layout de ``MarketStore`` (``root/base/<as_of>/manifest.json`` e
    ``root/daily/<AAAA-MM-DD>/manifest.json``); fontes sem ``root`` não contribuem.
    """
    root = getattr(store, "root", None)
    if root is None:
        return {}
    root = Path(root)
    out: dict[str, str] = {}
    base_root = root / "base"
    if base_root.is_dir():
        bases = []
        for p in base_root.iterdir():
            try:
                d = date.fromisoformat(p.name)
            except ValueError:
                continue
            if p.is_dir() and (p / "manifest.json").exists():
                bases.append((d, p))
        if bases:
            # Mesma escolha de ``MarketStore.load``: a base mais recente <= pregão; sem nenhuma,
            # a mais antiga (cortada no pregão).
            eligible = [b for b in bases if b[0] <= session]
            chosen = max(eligible) if eligible else min(bases)
            out["base_snapshot_manifest"] = sha256_file(chosen[1] / "manifest.json")
    inc = root / "daily" / session.isoformat() / "manifest.json"
    if inc.exists():
        out["daily_increment_manifest"] = sha256_file(inc)
    return out


def clean_text(text: object, max_len: int = MAX_ALERT_TEXT) -> str:
    """Texto de origem externa (manifestos, mensagens de erro de coleta) numa linha só, sem
    caracteres de controle e com tamanho limitado — os alertas viram insumo do comentário do dia
    e nunca podem carregar blocos arbitrários (injeção de instruções)."""
    raw = "".join(ch if ch.isprintable() else " " for ch in str(text))
    one = " ".join(raw.split())
    return one if len(one) <= max_len else one[:max_len - 1].rstrip() + "…"


def session_limitations(md: MarketData, session: date) -> list[str]:
    """Limitações de dados relevantes para o pregão: as da base (sem data) e as do incremento do
    próprio dia (``"[AAAA-MM-DD] ..."`` no ``MarketStore``); as de outros dias e a linha de
    composição ficam fora (já constam dos registros dos respectivos dias/manifestos). Cada texto
    é saneado por :func:`clean_text`."""
    tag = f"[{session.isoformat()}]"
    out: list[str] = []
    for lim in md.manifest.limitations:
        text = str(lim).strip()
        if text.startswith("Composição:"):
            continue
        if text.startswith("[") and "]" in text[:13]:
            if text.startswith(tag):
                out.append(clean_text(text[len(tag):].strip()))
            continue
        out.append(clean_text(text))
    return out


def financing_rate(md: MarketData, as_of: date) -> tuple[float | None, date | None, list[str]]:
    """Taxa ``USD_3M`` (decimal anual) conhecida em ``as_of`` e alertas.

    Ausente ⇒ ``None`` com alerta. Fora de :data:`RATE_PLAUSIBLE_RANGE` (ex.: série gravada em %)
    ⇒ ``None`` com alerta: uma taxa 100× maior num registro imutável é pior que não apurar o
    financiamento. Defasada há mais de :data:`RATE_STALE_DAYS` dias ⇒ usada com alerta.
    """
    rates = md.rates
    if FINANCING_RATE_SERIES not in rates.columns:
        return None, None, [f"Taxa {FINANCING_RATE_SERIES} indisponível: financiamento do caixa "
                            "não apurado (zero) no período."]
    s = pd.to_numeric(rates[FINANCING_RATE_SERIES], errors="coerce").dropna()
    s = s[s.index <= pd.Timestamp(as_of)]
    if s.empty:
        return None, None, [f"Taxa {FINANCING_RATE_SERIES} indisponível: financiamento do caixa "
                            "não apurado (zero) no período."]
    rate, rate_date = float(s.iloc[-1]), s.index[-1].date()
    lo, hi = RATE_PLAUSIBLE_RANGE
    if not (lo <= rate <= hi):
        return None, rate_date, [
            f"Taxa {FINANCING_RATE_SERIES} de {rate_date} fora da faixa plausível "
            f"({fmt_num(rate, 4)}; esperado decimal anual entre {fmt_pct(lo)} e {fmt_pct(hi)}): "
            "financiamento do caixa não apurado (zero) — conferir a unidade da série."]
    alerts = []
    if (as_of - rate_date).days > RATE_STALE_DAYS:
        alerts.append(f"Taxa {FINANCING_RATE_SERIES} defasada (de {rate_date}).")
    return rate, rate_date, alerts


def factor_returns_source(session_model: RiskModel | None, model_prev: RiskModel,
                          session_ts: pd.Timestamp, session_returns: pd.Series | None
                          ) -> tuple[Callable[[pd.Timestamp], pd.Series | None], dict[str, Any]]:
    """Retornos fatoriais por sessão para a atribuição com as exposições de ``model_prev``.

    Ordem: linha COMPLETA (todos os fatores de ``model_prev``) do modelo da sessão, depois do
    modelo anterior; para a própria sessão, regressão cross-section dos retornos do dia com as
    exposições de ``model_prev`` (``session_returns``). Uma linha incompleta (fator que o modelo
    do dia descartou) só é usada como último recurso e é registrada em ``state['partial']`` —
    os fatores sem retorno contribuem zero com alerta, nunca em silêncio.
    """
    names = model_prev.factor_names
    frames = [m.factor_returns for m in (session_model, model_prev) if m is not None]
    cache: dict[pd.Timestamp, pd.Series | None] = {}
    state: dict[str, Any] = {"fallback": False, "partial": {}}

    def get(s: pd.Timestamp) -> pd.Series | None:
        if s in cache:
            return cache[s]
        row: pd.Series | None = None
        partial: pd.Series | None = None
        for fr in frames:
            if s in fr.index:
                cand = fr.loc[s].reindex(names).astype(float)
                if cand.notna().all():
                    row = cand
                    break
                if partial is None and cand.notna().any():
                    partial = cand
        if row is None and s == session_ts and session_returns is not None:
            est = cross_sectional_factor_returns(model_prev.exposures, session_returns,
                                                 model_prev.specific_var)
            if est is not None:
                row = est.reindex(names).astype(float)
                state["fallback"] = True
        if row is None and partial is not None:
            state["partial"][str(s.date())] = sorted(partial.index[partial.isna()])
            row = partial
        cache[s] = row
        return row

    return get, state


def _list(items: Iterable[str]) -> str:
    items = list(items)
    head = ", ".join(items[:_MAX_LISTED])
    return head + (f" (+{len(items) - _MAX_LISTED})" if len(items) > _MAX_LISTED else "")


def _round_shares(x: float) -> int:
    """Arredonda à ação inteira (meio para longe de zero)."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def _finite(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _last_valid(series: pd.Series, ts: pd.Timestamp) -> tuple[float | None, pd.Timestamp | None]:
    s = pd.to_numeric(series.loc[:ts], errors="coerce").dropna()
    s = s[s > 0]
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1]


def _meta_hash(model: RiskModel) -> str:
    try:
        return sha256_obj({"as_of": model.as_of, "meta": model.meta})
    except TypeError:
        return sha256_text(repr(sorted((str(k), repr(v)) for k, v in model.meta.items())))


def risk_alerts(cfg: FundConfig, risk: DailyRisk, has_positions: bool = True) -> list[str]:
    """Alertas de mandato sobre o risco do dia: banda de vol ex-ante, net, beta e escada de
    drawdown (com a ação exigida)."""
    rk, dd_cfg = cfg.risk, cfg.drawdown
    out: list[str] = []
    if has_positions and risk.ex_ante_vol is not None:
        v = risk.ex_ante_vol
        if v < rk.vol_band_min:
            out.append(f"Vol ex-ante {fmt_pct(v)} abaixo da banda ({fmt_pct(rk.vol_band_min)}–"
                       f"{fmt_pct(rk.vol_band_max)}): subutilização do orçamento de risco.")
        elif v > rk.vol_band_max:
            out.append(f"Vol ex-ante {fmt_pct(v)} acima da banda ({fmt_pct(rk.vol_band_min)}–"
                       f"{fmt_pct(rk.vol_band_max)}): reduzir risco no próximo rebalanceamento.")
    elif has_positions:
        out.append("Vol ex-ante indisponível (modelo de risco ausente): banda não verificada.")
    if abs(risk.net) > rk.net_exposure_max_abs:
        out.append(f"Exposição líquida {fmt_pct(risk.net, signed=True)} fora do limite "
                   f"±{fmt_pct(rk.net_exposure_max_abs)} (net neutral).")
    if risk.beta is not None and abs(risk.beta) > rk.beta_max_abs:
        out.append(f"Beta previsto {fmt_num(risk.beta, 3, signed=True)} fora do limite "
                   f"±{fmt_num(rk.beta_max_abs, 3)}.")
    dd = risk.drawdown
    if dd <= dd_cfg.stop_out:
        out.append(f"STOP-OUT: drawdown {fmt_pct(dd)} atingiu {fmt_pct(dd_cfg.stop_out)} — "
                   f"reduzir o gross a {fmt_pct(dd_cfg.stop_out_gross)} do NAV e revisão completa "
                   "do processo.")
    elif dd <= dd_cfg.hard_stop:
        out.append(f"HARD STOP: drawdown {fmt_pct(dd)} atingiu {fmt_pct(dd_cfg.hard_stop)} — "
                   f"cortar o gross para {fmt_pct(dd_cfg.degross_multiplier)} do atual.")
    elif dd <= dd_cfg.soft_stop:
        out.append(f"SOFT STOP: drawdown {fmt_pct(dd)} atingiu {fmt_pct(dd_cfg.soft_stop)} — "
                   "revisão de risco obrigatória e corte do gross para "
                   f"{fmt_pct(dd_cfg.soft_degross_multiplier)} do atual.")
    return out


def short_entry_prices(history: Iterable[DailyRecord],
                       current: Mapping[str, tuple[float, float]],
                       max_records: int = ENTRY_LOOKBACK_RECORDS) -> dict[str, float]:
    """Preço médio de entrada (moeda local) de cada short atual.

    ``history`` vem do registro mais recente para o mais antigo (sem o dia corrente);
    ``current`` mapeia ticker → (ações assinadas, preço local de hoje). O episódio de short é a
    sequência contínua de registros com o ticker vendido; aumentos de posição recompõem o preço
    médio pelo fechamento do dia do aumento; reduções o mantêm.
    """
    open_ = {t for t, (sh, px) in current.items() if sh < 0 and px > 0}
    spells: dict[str, list[tuple[float, float]]] = {t: [] for t in open_}
    for k, rec in enumerate(history):
        if not open_ or k >= max_records:
            break
        pos = {p.ticker: p for p in rec.positions if p.market_value_usd < 0}
        for t in list(open_):
            p = pos.get(t)
            if p is None or p.shares is None or p.price_local is None or not p.price_local > 0:
                open_.discard(t)
                continue
            spells[t].append((float(p.shares), float(p.price_local)))
    out: dict[str, float] = {}
    for t, seq_rev in spells.items():
        seq = list(reversed(seq_rev)) + [current[t]]
        avg = seq[0][1]
        held = abs(seq[0][0])
        for sh, px in seq[1:]:
            a = abs(sh)
            if a > held + 1e-9 and a > 0:
                avg = (held * avg + (a - held) * px) / a
            held = a
        out[t] = float(avg)
    return out


# ==========================================================
# Persistência compatível com o livro (decisões autônomas e sombra)
# ==========================================================

def _verify_autonomous(proposal: Proposal, decision: Decision, cfg: FundConfig,
                       snapshot_hash_now: str | None, config_hash: str | None = None) -> None:
    """``verify_autonomous_decision`` contra o mandato atual (ou ``config_hash`` informado)."""
    if decision.mode != DecisionMode.AUTONOMOUS:
        raise ValueError("Decisão não é autônoma.")
    if decision.decision != DecisionType.APPROVE:
        raise ValueError("Somente decisões APPROVE são executadas.")
    ok, reasons = verify_autonomous_decision(
        decision, proposal, snapshot_hash_now or proposal.snapshot_hash,
        config_hash or cfg.config_hash(), proposal.research_hash)
    if not ok:
        raise ValueError("Decisão autônoma inválida: " + " ".join(reasons))


def save_decided_proposal(book: Book, proposal: Proposal, decision: Decision, cfg: FundConfig,
                          *, snapshot_hash_now: str | None = None, dry_run: bool = False) -> None:
    """Garante a proposta e a decisão gravadas no livro (``Book.save_proposal`` /
    ``Book.save_decision``), de forma idempotente.

    Decisões autônomas são conferidas antes com ``verify_autonomous_decision`` contra o mandato
    atual. Conteúdo divergente do já gravado é recusado. ``dry_run`` só faz as checagens.
    """
    if decision.mode == DecisionMode.AUTONOMOUS:
        _verify_autonomous(proposal, decision, cfg, snapshot_hash_now)
    week = proposal.week
    same = [p for p in book.list_proposals(week) if p.proposal_id == proposal.proposal_id]
    if same:
        if same[0].proposal_hash() != proposal.proposal_hash():
            raise ValueError(f"Proposta {proposal.proposal_id} já gravada com conteúdo diferente.")
        version = same[0].version
    else:
        if book.week_dir(week).joinpath("booked.json").exists():
            raise ValueError(f"A semana {week} já foi efetivada; não aceita nova proposta.")
        if proposal.version != book.next_version(week):
            raise ValueError(f"Versão {proposal.version} fora de sequência na semana {week} "
                             f"(próxima: {book.next_version(week)}).")
        version = proposal.version
    existing = book.load_decision(week, version) if same else None
    if existing is not None and existing.approval_hash != decision.approval_hash:
        raise FileExistsError(f"A proposta v{version} da semana {week} já tem outra decisão.")
    if dry_run:
        return
    if not same:
        book.save_proposal(proposal)
    if existing is None:
        book.save_decision(decision)


def book_execution(book: Book, entry: BookEntry, proposal: Proposal, decision: Decision,
                   cfg: FundConfig, *, snapshot_hash_now: str | None = None,
                   actor: str = DAILY_ACTOR, dry_run: bool = False) -> Path:
    """Efetiva no livro a carteira executada no fechamento (``<semana>/booked.json``).

    Grava proposta e decisão se ausentes (:func:`save_decided_proposal`) e chama
    ``Book.save_booked`` (que revalida a aprovação contra os hashes atuais, a carteira contra a
    aprovada, a cronologia e o KILL_SWITCH, e registra ``BOOKED``). Decisões autônomas passam
    antes por ``verify_autonomous_decision``.
    """
    if entry.week != proposal.week or entry.proposal_id != proposal.proposal_id:
        raise ValueError("BookEntry não corresponde à proposta decidida.")
    if entry.approval_hash != decision.approval_hash:
        raise ValueError("approval_hash do booking difere do da decisão.")
    path = book.week_dir(entry.week) / "booked.json"
    if path.exists():
        raise FileExistsError(f"A semana {entry.week} já foi efetivada (imutável).")
    save_decided_proposal(book, proposal, decision, cfg, snapshot_hash_now=snapshot_hash_now,
                          dry_run=dry_run)
    if dry_run:
        return path
    return book.save_booked(entry, snapshot_hash_now or proposal.snapshot_hash, cfg.config_hash(),
                            decision.research_hash, actor=actor)


class ShadowBook:
    """Propostas e efetivações da carteira-sombra só-quant (dentro da pasta da série sombra).

    ``proposals/<semana>.json`` e ``booked/<semana>.json``, imutáveis, com eventos
    ``SHADOW_PROPOSAL_SAVED`` e ``BOOKED_SHADOW`` na trilha da série.
    """

    def __init__(self, track: TrackRecord) -> None:
        self.track = track
        self.root = track.root
        self.audit = track.audit

    def proposal_path(self, week: date) -> Path:
        return self.root / "proposals" / f"{week.isoformat()}.json"

    def booked_path(self, week: date) -> Path:
        return self.root / "booked" / f"{week.isoformat()}.json"

    def weeks(self) -> list[date]:
        d = self.root / "proposals"
        if not d.is_dir():
            return []
        out = []
        for p in d.glob("*.json"):
            try:
                out.append(date.fromisoformat(p.stem))
            except ValueError:
                continue
        return sorted(out)

    def _audited(self, event_type: str) -> set[str]:
        return {ev.payload_hash for ev in self.audit.events() if ev.event_type == event_type}

    def _audited_in_week(self, event_type: str, week: date) -> set[str]:
        return {ev.payload_hash for ev in self.audit.events()
                if ev.event_type == event_type and ev.week == week}

    def load_proposal(self, week: date) -> Proposal | None:
        """Proposta-sombra da semana, conferida contra a trilha (``ValueError`` se alterada ou
        copiada de outra semana)."""
        path = self.proposal_path(week)
        if not path.exists():
            return None
        proposal = Proposal.model_validate_json(path.read_text(encoding="utf-8"))
        if proposal.week != week:
            raise ValueError(f"Proposta-sombra em {path.name} é da semana {proposal.week} "
                             "(arquivo copiado/renomeado).")
        if (sha256_obj(proposal.proposal_hash())
                not in self._audited_in_week(SHADOW_PROPOSAL_EVENT, week)):
            raise ValueError(f"Proposta-sombra de {week} não confere com a trilha de auditoria.")
        return proposal

    def load_booked(self, week: date) -> BookEntry | None:
        """Efetivação-sombra da semana, conferida contra a trilha (``ValueError`` se alterada ou
        copiada de outra semana)."""
        path = self.booked_path(week)
        if not path.exists():
            return None
        entry = BookEntry.model_validate_json(path.read_text(encoding="utf-8"))
        if entry.week != week:
            raise ValueError(f"Efetivação-sombra em {path.name} é da semana {entry.week} "
                             "(arquivo copiado/renomeado).")
        if sha256_obj(entry) not in self._audited_in_week(SHADOW_BOOKED_EVENT, week):
            raise ValueError(f"Efetivação-sombra de {week} não confere com a trilha de auditoria.")
        return entry

    def save_proposal(self, proposal: Proposal) -> Path:
        """Grava a proposta-sombra da semana (idempotente para o mesmo conteúdo)."""
        path = self.proposal_path(proposal.week)
        existing = (Proposal.model_validate_json(path.read_text(encoding="utf-8"))
                    if path.exists() else None)
        if existing is not None:
            if existing.proposal_hash() != proposal.proposal_hash():
                raise FileExistsError(f"Proposta-sombra da semana {proposal.week} já existe com "
                                      "conteúdo diferente (imutável).")
            return path
        write_exclusive(path, dump_json(proposal))
        self.audit.append(SHADOW_PROPOSAL_EVENT, DAILY_ACTOR, proposal.proposal_hash(),
                          summary=f"Proposta-sombra só-quant {proposal.proposal_id}.",
                          week=proposal.week)
        return path

    def save_booked(self, entry: BookEntry) -> Path:
        path = self.booked_path(entry.week)
        write_exclusive(path, dump_json(entry))
        self.audit.append(SHADOW_BOOKED_EVENT, DAILY_ACTOR, entry,
                          summary=(f"Carteira-sombra efetivada (MOC): {entry.proposal_id}, "
                                   f"{len(entry.positions)} posições."),
                          week=entry.week)
        return path


def book_shadow_proposal(book: Book, week: date) -> Proposal | None:
    """Proposta-sombra só-quant gravada pelo pipeline semanal em ``<livro>/<semana>/`` (arquivo
    :data:`BOOK_SHADOW_FILE`, evento ``SHADOW_QUANT`` com ``{"sha256": <sha256 do arquivo>}``).

    ``None`` se não houver arquivo; ``ValueError`` se o arquivo não conferir com a trilha ou for
    de outra semana (nunca executa uma sombra alterada fora do pipeline).
    """
    path = book.week_dir(week) / BOOK_SHADOW_FILE
    if not path.exists():
        return None
    payload = sha256_obj({"sha256": sha256_file(path)})
    if not any(ev.event_type == BOOK_SHADOW_EVENT and ev.week == week
               and ev.payload_hash == payload for ev in book.audit.events()):
        raise ValueError(f"{BOOK_SHADOW_FILE} da semana {week} não confere com a trilha de "
                         "auditoria.")
    proposal = Proposal.model_validate_json(path.read_text(encoding="utf-8"))
    if proposal.week != week:
        raise ValueError(f"{BOOK_SHADOW_FILE} da semana {week} contém a proposta de "
                         f"{proposal.week}.")
    return proposal


# ==========================================================
# Estruturas internas
# ==========================================================

@dataclass
class _Line:
    issuer_id: str
    ticker: str
    currency: str
    shares: float | None
    mv_start: float
    pnl: float
    ret: float | None
    repriced: bool
    mv_end: float
    price_local: float | None
    price_usd: float | None


@dataclass
class _Marked:
    nav_start: float
    days: int
    lines: list[_Line]
    equity: float
    financing: float
    borrow: float
    alerts: list[str]

    @property
    def nav_pre(self) -> float:
        return self.nav_start + self.equity + self.financing + self.borrow


@dataclass
class _Exec:
    issuer_id: str
    ticker: str
    currency: str
    shares: int
    price_local: float
    fx: float

    @property
    def mv(self) -> float:
        return self.shares * self.price_local * self.fx


@dataclass
class _Plan:
    """Execução no fechamento: proposta decidida (a efetivar) ou efetivação já gravada."""

    week: date
    proposal: Proposal | None
    decision: Decision | None
    entry: BookEntry | None
    hold: bool
    approval_hash: str
    proposal_id: str
    source: str
    persist: Callable[[BookEntry], object] | None = None
    preflight: Callable[[BookEntry], object] | None = None
    notes: list[str] = field(default_factory=list)

    def targets(self) -> list[tuple[str, str, float, str]]:
        if self.entry is not None:
            return [(p.issuer_id, p.ticker, p.weight, p.currency)
                    for p in self.entry.positions if p.weight != 0]
        assert self.proposal is not None
        return [(p.issuer_id, p.execution_ticker, p.weight, p.currency)
                for p in self.proposal.positions if p.weight != 0]


@dataclass
class _SideResult:
    record: DailyRecord
    entry: BookEntry | None
    commit: Callable[[], None] | None


class _MainSide:
    label = "CDP"
    is_shadow = False

    def __init__(self, cfg: FundConfig, book: Book, track: TrackRecord) -> None:
        self.cfg, self.book, self.track = cfg, book, track
        self.fund_name = cfg.fund.name
        self.track_type = cfg.fund.track_record_type

    def load_entry(self, week: date) -> BookEntry | None:
        return self.book.load_booked(week)

    def weeks_before(self, week: date) -> list[date]:
        return [w for w in self.book.list_weeks() if w < week]

    def proposal_for(self, entry: BookEntry) -> Proposal | None:
        for p in self.book.list_proposals(entry.week):
            if p.proposal_id == entry.proposal_id:
                return p
        return None


class _ShadowSide:
    label = "sombra"
    is_shadow = True

    def __init__(self, cfg: FundConfig, track: TrackRecord) -> None:
        self.cfg, self.track = cfg, track
        self.store = ShadowBook(track)
        self.fund_name = f"{cfg.fund.name} — {SHADOW_LABEL}"
        self.track_type = (f"{cfg.fund.track_record_type} — carteira-sombra só-quant "
                           "(contrafactual, sem decisão)")

    def load_entry(self, week: date) -> BookEntry | None:
        return self.store.load_booked(week)

    def weeks_before(self, week: date) -> list[date]:
        return [w for w in self.store.weeks() if w < week]

    def proposal_for(self, entry: BookEntry) -> Proposal | None:
        p = self.store.load_proposal(entry.week)
        return p if p is not None and p.proposal_id == entry.proposal_id else None


# ==========================================================
# Rotina diária
# ==========================================================

class DailyRunner:
    """Executa o fechamento diário: MOC da decisão da semana, MTM, risco, atribuição e alertas.

    ``store`` é qualquer objeto com ``load(as_of) -> MarketData`` sem look-ahead (ex.:
    ``MarketStore``); ``book`` é o livro semanal; ``track`` a série do CDP e ``shadow_track``
    (opcional) a série da carteira-sombra só-quant.
    """

    def __init__(self, cfg: FundConfig, store: MarketSource, book: Book, track: TrackRecord,
                 *, shadow_track: TrackRecord | None = None, actor: str = DAILY_ACTOR) -> None:
        self.cfg = cfg
        self.store = store
        self.book = book
        self.track = track
        self.actor = actor
        self.main = _MainSide(cfg, book, track)
        self.shadow = _ShadowSide(cfg, shadow_track) if shadow_track is not None else None
        self._models: dict[date, RiskModel | None] = {}
        self._model_notes: dict[date, str] = {}

    @classmethod
    def from_root(cls, cfg: FundConfig, store: MarketSource, root: Path | str = "book",
                  *, with_shadow: bool = True) -> DailyRunner:
        """Layout padrão: ``<root>/`` (livro), ``<root>/track_record`` e
        ``<root>/track_record_shadow``."""
        root = Path(root)
        book = Book(root, cfg)
        track = TrackRecord(root / "track_record")
        shadow = (TrackRecord(root / "track_record_shadow", audit_event=SHADOW_RECORD_EVENT)
                  if with_shadow else None)
        return cls(cfg, store, book, track, shadow_track=shadow)

    @property
    def shadow_book(self) -> ShadowBook | None:
        return self.shadow.store if self.shadow is not None else None

    def save_shadow_proposal(self, proposal: Proposal) -> Path:
        """Registra a proposta-sombra só-quant da semana para execução no fechamento."""
        if self.shadow is None:
            raise ValueError("Rotina sem série-sombra configurada.")
        return self.shadow.store.save_proposal(proposal)

    # ------------------------------------------------------------------ API
    def run(self, session_date: date, pending: PendingExecution | None = None) -> DailyRecord:
        """Registro diário do CDP em ``session_date`` (grava também a sombra, se houver)."""
        return self.run_session(session_date, pending).record

    def run_session(self, session_date: date,
                    pending: PendingExecution | None = None) -> DailyRunResult:
        prev = self.track.last()
        if prev is not None and session_date <= prev.date:
            kind = "já registrado" if session_date == prev.date else "anterior ao último registro"
            raise ValueError(f"Pregão {session_date} {kind} ({prev.date}).")
        _check_track_tail(self.track, prev)
        md = self.store.load(as_of=session_date)
        if not session_has_prices(md, session_date):
            raise NoSessionError(f"{session_date}: sem pregão (sem preços de fechamento no "
                                 "armazenamento de mercado).")
        plan = self._main_plan(session_date, prev, pending)
        if prev is None and plan is None:
            raise NoBookError(
                f"Sem carteira efetivada executável em {session_date}: o track record começa no "
                "fechamento do pregão de efetivação da primeira carteira aprovada.")
        ctx = self.context(session_date, md, prev)

        shadow_res: _SideResult | None = None
        shadow_existing: DailyRecord | None = None
        shadow_alert: str | None = None
        if self.shadow is not None:
            try:
                shadow_res, shadow_existing = self._run_shadow(ctx, pending)
            except (ValueError, KeyError, FileExistsError) as exc:
                shadow_alert = f"Carteira-sombra só-quant não processada: {exc}"
        shadow_hash = (shadow_res.record.record_hash if shadow_res is not None
                       else shadow_existing.record_hash if shadow_existing is not None else None)

        extra = [shadow_alert] if shadow_alert else []
        main_res = self._compute_side(self.main, ctx, prev, plan, extra_alerts=extra,
                                      extra_hashes={"shadow_record": shadow_hash}
                                      if shadow_hash else None)

        # Gravação: primeiro a efetivação do CDP no livro (o passo que o livro pode recusar, ex.:
        # KILL_SWITCH); depois a sombra (efetivação + registro) e por fim o registro do CDP, que
        # já carrega o hash do registro-sombra. Uma nova execução retoma de onde parou.
        if main_res.commit is not None:
            main_res.commit()
        if shadow_res is not None and self.shadow is not None:
            if shadow_res.commit is not None:
                shadow_res.commit()
            self.shadow.track.append(shadow_res.record)
        self.track.append(main_res.record)
        return DailyRunResult(
            record=main_res.record,
            shadow=shadow_res.record if shadow_res is not None else shadow_existing,
            booked=main_res.entry if plan is not None else None,
            shadow_booked=shadow_res.entry if shadow_res is not None and shadow_res.commit
            else None)

    def backfill(self, start: date, end: date,
                 pending: Mapping[date, PendingExecution] | Iterable[PendingExecution] | None
                 = None) -> list[DailyRecord]:
        """Roda cada pregão de ``[start, end]`` em ordem; pula não-pregões, dias já registrados e
        pregões anteriores à primeira efetivação. ``pending``: decisões a executar (por semana)."""
        if end < start:
            raise ValueError("Fim do período anterior ao início.")
        if pending is None:
            pend: list[PendingExecution] = []
        elif isinstance(pending, Mapping):
            pend = list(pending.values())
        else:
            pend = list(pending)
        md_end = self.store.load(as_of=end)
        out: list[DailyRecord] = []
        last = self.track.last()
        for s in session_dates(md_end, start, end):
            if last is not None and s <= last.date:
                continue
            live = last.live_book_week if last is not None else None
            close = close_datetime(s, self.cfg)
            cands = [p for p in pend if executable_in(p.week, s)
                     and (live is None or p.week > live) and p.decision.decided_at <= close]
            p = max(cands, key=lambda x: x.week) if cands else None
            try:
                rec = self.run(s, pending=p)
            except NoSessionError:
                continue
            except NoBookError:
                if last is None:
                    continue
                raise
            out.append(rec)
            last = rec
        return out

    def execute_decision(self, session_date: date, proposal: Proposal, decision: Decision,
                         md: MarketData | None = None, *,
                         snapshot_hash_now: str | None = None) -> BookEntry:
        """Executa (efetiva) a proposta decidida no fechamento de ``session_date``.

        Nocional-alvo = peso × NAV antes dos custos (P&L do dia da carteira antiga incluído);
        ações pelo fechamento local e câmbio do dia. Persiste no livro (decisão autônoma: helper
        compatível; humana: ``Book.save_booked``) e devolve o ``BookEntry``. Idempotente quando a
        mesma decisão já foi efetivada. O registro diário do pregão é gravado por :meth:`run`.
        """
        existing = self.book.load_booked(proposal.week)
        if existing is not None:
            if (existing.proposal_id == proposal.proposal_id
                    and existing.approval_hash == decision.approval_hash):
                return existing
            raise FileExistsError(f"A semana {proposal.week} já foi efetivada com outra decisão.")
        md = md if md is not None else self.store.load(as_of=session_date)
        prev = self.track.last()
        if prev is not None and session_date <= prev.date:
            raise ValueError(f"Pregão {session_date} já registrado ({prev.date}).")
        pending = PendingExecution(proposal, decision, snapshot_hash_now=snapshot_hash_now)
        plan = self._plan_from_pending(session_date, prev, pending)
        ctx = self.context(session_date, md, prev, need_models=False)
        if plan.entry is not None:
            return plan.entry
        _, _, ref_prop = self._live(self.main, prev, [])
        marked = self._mark(ctx, prev, ref_prop)
        nav_pre = marked.nav_pre
        if plan.hold:
            entry = self._build_hold_entry(ctx, plan, nav_pre)
        else:
            execs, _ = self._size(ctx, plan, marked, nav_pre)
            cost, _ = self._costs(ctx, marked.lines, execs, nav_pre, plan)
            entry = self._build_entry(ctx, plan, execs, nav_pre, cost)
        if plan.preflight is not None:
            plan.preflight(entry)
        assert plan.persist is not None
        plan.persist(entry)
        return entry

    def verify_all(self) -> tuple[bool, list[str]]:
        """Integridade do track record (e da sombra) e do livro (``Book.verify_integrity``)."""
        problems: list[str] = []
        _, msgs = self.track.verify()
        problems += [f"[track record] {m}" for m in msgs]
        if self.shadow is not None:
            _, msgs_s = self.shadow.track.verify()
            problems += [f"[sombra] {m}" for m in msgs_s]
        _, msgs_b = self.book.verify_integrity()
        problems += [f"[livro] {m}" for m in msgs_b]
        return (not problems, problems)

    # ------------------------------------------------------------------ contexto
    def context(self, session_date: date, md: MarketData | None = None,
                prev: DailyRecord | None = None, *, need_models: bool = True) -> DailyContext:
        """Monta os insumos da sessão; ``NoSessionError`` se não houve pregão."""
        md = md if md is not None else self.store.load(as_of=session_date)
        if not session_has_prices(md, session_date):
            raise NoSessionError(f"{session_date}: sem pregão (sem preços de fechamento no "
                                 "armazenamento de mercado).")
        panel = build_asset_panel(md, self.cfg, as_of=session_date)
        ctx = DailyContext(date=session_date, md=md, panel=panel, model=None,
                           book_entry=None, prev=prev)
        if prev is not None and prev.live_book_week is not None:
            try:
                ctx.book_entry = self.main.load_entry(prev.live_book_week)
            except ValueError as exc:
                ctx.notes.append(f"Efetivação vigente inválida no livro: {exc}")
        if need_models:
            ctx.model = self._model_for(md, session_date, panel)
            if ctx.model is not None:
                ctx.risk_model = apply_event_windows(ctx.model, panel.assets["country"], self.cfg,
                                                     session_date)
                for w in ctx.risk_model.meta.get("event_windows", []):
                    ctx.notes.append(f"Janela de evento ativa: {w['name']} (vol × "
                                     f"{fmt_num(float(w['multiplier']), 2)} em {w['country']}).")
            elif session_date in self._model_notes:
                ctx.notes.append(self._model_notes[session_date])
            if prev is not None:
                ctx.model_prev = self._model_for(md, prev.date)
        return ctx

    def _model_for(self, md: MarketData, d: date, panel: AssetPanel | None = None
                   ) -> RiskModel | None:
        """Modelo de risco com dados ≤ ``d`` (cacheado por data; falha ⇒ ``None`` anotado)."""
        if d in self._models:
            return self._models[d]
        model: RiskModel | None = None
        try:
            p = panel if panel is not None else build_asset_panel(md.truncate(d), self.cfg, as_of=d)
            model = estimate_risk_model(p, self.cfg, md.truncate(d), as_of=d, issuers=p.eligible)
        except (ValueError, KeyError, IndexError, np.linalg.LinAlgError) as exc:
            self._model_notes[d] = f"Modelo de risco indisponível em {d}: {exc}"
        self._models[d] = model
        for old in sorted(self._models)[:-4]:
            self._models.pop(old, None)
        return model

    # ------------------------------------------------------------------ planos de execução
    def _verify_decision(self, session: date, proposal: Proposal, decision: Decision | None,
                         snapshot_hash_now: str | None) -> None:
        if decision is None:
            raise ValueError(f"Proposta {proposal.proposal_id} sem decisão gravada.")
        if decision.decision != DecisionType.APPROVE:
            raise ValueError(f"Proposta {proposal.proposal_id} não aprovada ({decision.decision}).")
        if decision.proposal_id != proposal.proposal_id or decision.week != proposal.week:
            raise ValueError("A decisão não pertence à proposta informada.")
        close = close_datetime(session, self.cfg)
        if decision.decided_at > close:
            raise ValueError(f"Decisão gravada após o fechamento de {session} "
                             f"({decision.decided_at.isoformat()}): executa no pregão seguinte.")
        snap = snapshot_hash_now or proposal.snapshot_hash
        if decision.mode == DecisionMode.AUTONOMOUS:
            _verify_autonomous(proposal, decision, self.cfg, snap)
            return
        ok, reasons = verify_decision(decision, proposal, snap, self.cfg.config_hash(),
                                      decision.research_hash)
        if not ok:
            raise ValueError("Aprovação inválida para execução: " + " ".join(reasons))

    def _check_week_window(self, session: date, week: date, prev: DailyRecord | None) -> None:
        if not executable_in(week, session):
            raise ValueError(f"Decisão da semana {week} não é executável em {session} "
                             "(somente em pregões da própria semana).")
        if prev is not None and prev.live_book_week is not None and week <= prev.live_book_week:
            raise ValueError(f"A semana {week} não é posterior à carteira vigente "
                             f"({prev.live_book_week}).")

    def _plan_from_pending(self, session: date, prev: DailyRecord | None,
                           pending: PendingExecution) -> _Plan:
        proposal, decision = pending.proposal, pending.decision
        self._check_week_window(session, proposal.week, prev)
        existing = self.book.load_booked(proposal.week)
        if existing is not None:
            if (existing.proposal_id != proposal.proposal_id
                    or existing.approval_hash != decision.approval_hash):
                raise FileExistsError(f"A semana {proposal.week} já foi efetivada com outra "
                                      "decisão.")
            self._verify_decision(session, proposal, decision, pending.snapshot_hash_now)
            return self._adopt_plan(existing, proposal, decision, "livro")
        self._verify_decision(session, proposal, decision, pending.snapshot_hash_now)
        return self._execute_plan(proposal, decision, pending.snapshot_hash_now, "decisão")

    def _execute_plan(self, proposal: Proposal, decision: Decision,
                      snapshot_hash_now: str | None, source: str) -> _Plan:
        cfg, book, actor = self.cfg, self.book, self.actor

        def preflight(entry: BookEntry) -> None:
            book_execution(book, entry, proposal, decision, cfg,
                           snapshot_hash_now=snapshot_hash_now, dry_run=True)

        def persist(entry: BookEntry) -> None:
            book_execution(book, entry, proposal, decision, cfg,
                           snapshot_hash_now=snapshot_hash_now, actor=actor)

        return _Plan(week=proposal.week, proposal=proposal, decision=decision, entry=None,
                     hold=proposal.optimizer.status == HOLD_STATUS,
                     approval_hash=decision.approval_hash, proposal_id=proposal.proposal_id,
                     source=source, persist=persist, preflight=preflight)

    @staticmethod
    def _adopt_plan(entry: BookEntry, proposal: Proposal | None, decision: Decision | None,
                    source: str) -> _Plan:
        hold = proposal is not None and proposal.optimizer.status == HOLD_STATUS
        return _Plan(week=entry.week, proposal=proposal, decision=decision, entry=entry,
                     hold=hold, approval_hash=entry.approval_hash, proposal_id=entry.proposal_id,
                     source=source)

    def _main_plan(self, session: date, prev: DailyRecord | None,
                   pending: PendingExecution | None) -> _Plan | None:
        if pending is not None:
            return self._plan_from_pending(session, prev, pending)
        live = prev.live_book_week if prev is not None else None
        close = close_datetime(session, self.cfg)
        weeks = [w for w in self.book.list_weeks()
                 if executable_in(w, session) and (live is None or w > live)]
        for w in sorted(weeks, reverse=True):
            entry = self.book.load_booked(w)
            if entry is not None:
                if entry.booked_at > close:
                    continue
                proposal = self.main.proposal_for(entry)
                if proposal is None:
                    raise ValueError(f"Efetivação da semana {w} sem a proposta correspondente.")
                decision = self.book.load_decision(w, proposal.version)
                if decision is None or decision.approval_hash != entry.approval_hash:
                    raise ValueError(f"Efetivação da semana {w} sem decisão correspondente "
                                     "(approval_hash).")
                self._verify_decision(session, proposal, decision, None)
                return self._adopt_plan(entry, proposal, decision, "livro")
            proposal = self.book.load_proposal(w)
            decision = self.book.load_decision(w)
            if (proposal is None or decision is None or decision.decision != DecisionType.APPROVE
                    or decision.proposal_id != proposal.proposal_id):
                continue
            if decision.decided_at > close:
                continue
            self._verify_decision(session, proposal, decision, None)
            return self._execute_plan(proposal, decision, None, "decisão")
        return None

    def _run_shadow(self, ctx: DailyContext, pending: PendingExecution | None
                    ) -> tuple[_SideResult | None, DailyRecord | None]:
        side = self.shadow
        assert side is not None
        prev = side.track.last()
        if prev is not None and prev.date >= ctx.date:
            return None, (prev if prev.date == ctx.date else None)
        _check_track_tail(side.track, prev)
        live = prev.live_book_week if prev is not None else None
        proposal: Proposal | None = None
        if pending is not None and pending.shadow is not None:
            proposal = pending.shadow
            if proposal.week != pending.proposal.week:
                raise ValueError("Proposta-sombra de outra semana.")
            if (proposal.snapshot_hash != pending.proposal.snapshot_hash
                    or proposal.config_hash != pending.proposal.config_hash):
                raise ValueError("Proposta-sombra com insumos (snapshot/mandato) diferentes da "
                                 "proposta do CDP.")
        else:
            for w in sorted(side.store.weeks(), reverse=True):
                if executable_in(w, ctx.date) and (live is None or w > live):
                    proposal = side.store.load_proposal(w)
                    break
        plan: _Plan | None = None
        if proposal is not None and (live is None or proposal.week > live):
            if not executable_in(proposal.week, ctx.date):
                raise ValueError(f"Proposta-sombra da semana {proposal.week} fora da janela.")
            if proposal.config_hash != self.cfg.config_hash():
                raise ValueError("Proposta-sombra com mandato diferente do atual.")
            existing = side.store.load_booked(proposal.week)
            if existing is not None:
                plan = self._adopt_plan(existing, proposal, None, "sombra")
            else:
                store = side.store

                def persist(entry: BookEntry, _p: Proposal = proposal) -> None:
                    store.save_proposal(_p)
                    store.save_booked(entry)

                plan = _Plan(week=proposal.week, proposal=proposal, decision=None, entry=None,
                             hold=proposal.optimizer.status == HOLD_STATUS,
                             approval_hash=proposal.proposal_hash(),
                             proposal_id=proposal.proposal_id, source="sombra", persist=persist)
        if prev is None and plan is None:
            return None, None
        return self._compute_side(side, ctx, prev, plan), None

    # ------------------------------------------------------------------ cálculo do dia
    def _live(self, side: _MainSide | _ShadowSide, prev: DailyRecord | None,
              alerts: list[str]) -> tuple[BookEntry | None, Proposal | None, Proposal | None]:
        """Efetivação vigente, sua proposta e a proposta de referência das posições (taxas de
        aluguel e faixas de squeeze da decisão), pulando semanas de "manter"."""
        if prev is None or prev.live_book_week is None:
            return None, None, None
        try:
            entry = side.load_entry(prev.live_book_week)
            proposal = side.proposal_for(entry) if entry is not None else None
        except ValueError as exc:
            alerts.append(f"Efetivação vigente ({prev.live_book_week}) inválida no livro ({exc}); "
                          "marcação pelas posições do registro anterior.")
            return None, None, None
        if entry is None:
            alerts.append(f"Efetivação vigente ({prev.live_book_week}) não encontrada no livro: "
                          "taxas de aluguel pela tabela do dia.")
            return None, None, None
        return entry, proposal, self._reference_proposal(side, entry, proposal)

    @staticmethod
    def _reference_proposal(side: _MainSide | _ShadowSide, entry: BookEntry,
                            proposal: Proposal | None) -> Proposal | None:
        if proposal is None or proposal.optimizer.status != HOLD_STATUS:
            return proposal
        try:
            for w in reversed(side.weeks_before(entry.week)):
                e = side.load_entry(w)
                p = side.proposal_for(e) if e is not None else None
                if p is not None and p.optimizer.status != HOLD_STATUS:
                    return p
        except ValueError:
            return None
        return None

    def _compute_side(self, side: _MainSide | _ShadowSide, ctx: DailyContext,
                      prev: DailyRecord | None, plan: _Plan | None,
                      extra_alerts: list[str] | None = None,
                      extra_hashes: dict[str, str] | None = None) -> _SideResult:
        cfg = self.cfg
        alerts: list[str] = list(extra_alerts or [])
        live_entry, live_prop, ref_prop = self._live(side, prev, alerts)
        marked = self._mark(ctx, prev, ref_prop)
        alerts += marked.alerts
        model_prev = (self._model_for(ctx.md, prev.date)
                      if prev is not None and marked.lines else None)
        attribution, factor_pnl, attr_alerts = self._attribution(ctx, prev, marked, model_prev)
        alerts += attr_alerts

        nav_pre = marked.nav_pre
        end_lines = list(marked.lines)
        cost = 0.0
        entry_after = live_entry
        commit: Callable[[], None] | None = None
        proposal_after = live_prop
        if plan is not None:
            alerts += plan.notes
            if plan.week != ctx.date:
                alerts.append(f"Execução da decisão da semana {plan.week} no fechamento de "
                              f"{ctx.date} (primeiro pregão disponível).")
            if plan.hold:
                alerts.append(f"Decisão da semana {plan.week}: manter a carteira anterior "
                              "(sem negociação).")
                entry = plan.entry or self._build_hold_entry(ctx, plan, nav_pre)
            else:
                execs, size_alerts = self._size(ctx, plan, marked, nav_pre)
                alerts += size_alerts
                cost_usd, cost_alerts = self._costs(ctx, marked.lines, execs, nav_pre, plan)
                alerts += cost_alerts
                cost = -cost_usd
                end_lines = _merge_execution(marked.lines, execs)
                entry = plan.entry or self._build_entry(ctx, plan, execs, nav_pre, cost_usd)
            if plan.entry is None:
                if plan.preflight is not None:
                    plan.preflight(entry)
                persist = plan.persist
                assert persist is not None

                def commit(_e: BookEntry = entry) -> None:
                    persist(_e)
            entry_after = entry
            proposal_after = plan.proposal
            if not plan.hold:
                ref_prop = plan.proposal
        pnl = marked.equity + marked.financing + marked.borrow + cost
        nav_end = marked.nav_start + pnl
        if not (math.isfinite(nav_end) and nav_end > 0):
            raise ValueError(f"NAV não positivo em {ctx.date}: registro interrompido.")

        components = {"equity": marked.equity, "financing": marked.financing,
                      "borrow": marked.borrow, "costs": cost}
        if factor_pnl is not None:
            components["factor"] = factor_pnl
            components["specific"] = marked.equity - factor_pnl
        comp_lines = [AttributionLine(group="component", name=k, pnl_usd=components[k],
                                      contribution=components[k] / marked.nav_start)
                      for k in COMPONENTS if k in components]

        positions = self._positions(end_lines, nav_end)
        risk, risk_alerts_ = self._risk(ctx, side, positions, nav_end, pnl / marked.nav_start,
                                        marked.nav_start, prev)
        alerts += risk_alerts_
        alerts += self._position_alerts(ctx, side, positions, nav_end, ref_prop)
        alerts += [f"Limitação de dados: {lim}"
                   for lim in session_limitations(ctx.md, ctx.date)]
        alerts += ctx.notes
        if prev is None and ctx.date != cfg.fund.inception_date:
            alerts.append(f"Inception em {ctx.date} difere da data do mandato "
                          f"({cfg.fund.inception_date}).")

        hashes = self._input_hashes(ctx, entry_after, proposal_after, model_prev
                                    if marked.lines else None)
        if extra_hashes:
            hashes.update({k: v for k, v in extra_hashes.items() if v})
        if ctx.md.is_synthetic:
            notice = (f"{SIMULATED_DATA_NOTICE} — mercado sintético gerado por código; "
                      "paper trading com execução hipotética no fechamento.")
        else:
            notice = ("Dados reais de mercado; paper trading com execução hipotética no "
                      "fechamento (MOC) e custos do modelo.")
        record = DailyRecord(
            date=ctx.date, fund_name=side.fund_name, track_record_type=side.track_type,
            nav_start_usd=marked.nav_start, nav_end_usd=nav_end, pnl_usd=pnl,
            ret=pnl / marked.nav_start, pnl_components=components,
            attribution=comp_lines + attribution, positions=positions, risk=risk,
            alerts=list(dict.fromkeys(alerts)),
            live_book_week=entry_after.week if entry_after is not None else (
                prev.live_book_week if prev is not None else None),
            approval_hash=entry_after.approval_hash if entry_after is not None else (
                prev.approval_hash if prev is not None else None),
            input_hashes=hashes, is_synthetic=ctx.md.is_synthetic, data_notice=notice,
            prev_record_hash=prev.record_hash if prev is not None else GENESIS_RECORD_HASH,
        )
        record = record.model_copy(update={"record_hash": record.compute_hash()})
        return _SideResult(record=record, entry=entry_after if plan is not None else None,
                           commit=commit)

    # ------------------------------------------------------------------ marcação
    def _fx(self, ctx: DailyContext) -> pd.Series:
        if "fx" not in ctx.cache:
            fx = fx_for_lines(ctx.md)
            ctx.cache["fx_frame"] = fx
            ctx.cache["fx"] = fx.loc[ctx.ts] if ctx.ts in fx.index else pd.Series(dtype=float)
        return ctx.cache["fx"]

    def _fx_rate(self, ctx: DailyContext, currency: str) -> float | None:
        if currency == "USD":
            return 1.0
        v = self._fx(ctx).get(currency, np.nan)
        return float(v) if _finite(v) and v > 0 else None

    def _line_currency(self, ctx: DailyContext, ticker: str, fallback: str) -> str:
        lines = ctx.md.universe.lines
        if ticker in lines.index:
            return str(lines.loc[ticker, "currency"])
        return fallback

    def _rate_asof(self, ctx: DailyContext, d: date) -> tuple[float | None, date | None]:
        rates = ctx.md.rates
        if FINANCING_RATE_SERIES not in rates.columns:
            return None, None
        s = pd.to_numeric(rates[FINANCING_RATE_SERIES], errors="coerce").dropna()
        s = s[s.index <= pd.Timestamp(d)]
        if s.empty:
            return None, None
        return float(s.iloc[-1]), s.index[-1].date()

    def _availability(self, ctx: DailyContext) -> pd.DataFrame:
        if "availability" not in ctx.cache:
            ctx.cache["availability"] = short_availability(ctx.panel, ctx.md, self.cfg)
        return ctx.cache["availability"]

    def _borrow_fee(self, ctx: DailyContext, ln: _Line, proposal: Proposal | None
                    ) -> tuple[float, str]:
        if proposal is not None:
            for p in proposal.positions:
                if (p.issuer_id == ln.issuer_id and p.side == Side.SHORT
                        and _finite(p.borrow_fee_annual) and p.borrow_fee_annual >= 0):
                    return float(p.borrow_fee_annual), "proposta"
        try:
            av = self._availability(ctx)
        except (ValueError, KeyError):
            av = None
        if av is not None and ln.ticker in av.index:
            fee = pd.to_numeric(av.loc[ln.ticker, "borrow_fee_annual"], errors="coerce")
            if _finite(fee) and fee >= 0:
                return float(fee), "tabela"
        return DEFAULT_BORROW_FEE_ANNUAL, "padrão"

    def _mark(self, ctx: DailyContext, prev: DailyRecord | None,
              live_proposal: Proposal | None) -> _Marked:
        cfg = self.cfg
        if prev is None:
            return _Marked(nav_start=float(cfg.fund.inception_nav_usd), days=0, lines=[],
                           equity=0.0, financing=0.0, borrow=0.0, alerts=[])
        alerts: list[str] = []
        ts, prev_ts = ctx.ts, pd.Timestamp(prev.date)
        days = (ctx.date - prev.date).days
        lr = ctx.panel.line_returns
        period = lr.loc[(lr.index > prev_ts) & (lr.index <= ts)]
        lines: list[_Line] = []
        stale: list[str] = []
        partial: list[str] = []
        for p in sorted(prev.positions, key=lambda x: (x.issuer_id, x.ticker)):
            if p.market_value_usd == 0:
                continue
            r: float | None = None
            if p.ticker in period.columns:
                s = period[p.ticker].dropna()
                if not s.empty:
                    r = float((1.0 + s).prod() - 1.0)
            price_local, price_usd = p.price_local, p.price_usd
            if r is None:
                stale.append(p.ticker)
            else:
                px, pdate = (_last_valid(ctx.md.close[p.ticker], ts)
                             if p.ticker in ctx.md.close.columns else (None, None))
                fx = self._fx_rate(ctx, p.currency)
                if px is not None:
                    price_local = px
                    price_usd = px * fx if fx is not None else None
                    if pdate is not None and pdate < ts:
                        partial.append(p.ticker)
            pnl = p.market_value_usd * r if r is not None else 0.0
            lines.append(_Line(
                issuer_id=p.issuer_id, ticker=p.ticker, currency=p.currency, shares=p.shares,
                mv_start=p.market_value_usd, pnl=pnl, ret=r, repriced=r is not None,
                mv_end=p.market_value_usd + pnl, price_local=price_local, price_usd=price_usd))
        if stale:
            alerts.append("Preço ausente no pregão (linha não negociou; posição não reprecificada, "
                          f"valor mantido): {_list(stale)}.")
        if partial:
            alerts.append("Preço defasado (último fechamento anterior ao pregão): "
                          f"{_list(partial)}.")
        equity = float(sum(ln.pnl for ln in lines))

        financing = 0.0
        rate, rate_date = self._rate_asof(ctx, prev.date)
        if days > 0:
            if rate is None:
                alerts.append(f"Taxa {FINANCING_RATE_SERIES} indisponível: financiamento do caixa "
                              "não apurado (zero) no período.")
            else:
                financing = marked_financing(prev.nav_end_usd, rate, days)
                if rate_date is not None and (prev.date - rate_date).days > RATE_STALE_DAYS:
                    alerts.append(f"Taxa {FINANCING_RATE_SERIES} defasada (de {rate_date}).")
        borrow = 0.0
        defaulted: list[str] = []
        for ln in lines:
            if ln.mv_start < 0 and days > 0:
                fee, src = self._borrow_fee(ctx, ln, live_proposal)
                if src == "padrão":
                    defaulted.append(ln.ticker)
                borrow -= abs(ln.mv_start) * fee / DAY_COUNT_BASIS * days
        if defaulted:
            alerts.append(f"Aluguel pela taxa padrão conservadora de "
                          f"{fmt_pct(DEFAULT_BORROW_FEE_ANNUAL)} a.a. (sem taxa na proposta nem "
                          f"na tabela): {_list(defaulted)}.")
        return _Marked(nav_start=float(prev.nav_end_usd), days=days, lines=lines, equity=equity,
                       financing=financing, borrow=borrow, alerts=alerts)

    # ------------------------------------------------------------------ atribuição
    def _attribution(self, ctx: DailyContext, prev: DailyRecord | None, marked: _Marked,
                     model_prev: RiskModel | None
                     ) -> tuple[list[AttributionLine], float | None, list[str]]:
        nav0 = marked.nav_start
        alerts: list[str] = []
        lines = marked.lines
        out: list[AttributionLine] = []
        assets = ctx.panel.assets
        issuers = ctx.md.universe.issuers

        def meta(iid: str, col_panel: str, col_uni: str) -> str:
            if iid in assets.index and isinstance(assets.loc[iid, col_panel], str):
                return str(assets.loc[iid, col_panel])
            if iid in issuers.index:
                return str(issuers.loc[iid, col_uni])
            return "NA"

        def agg(group: str, keys: list[str]) -> list[AttributionLine]:
            acc: dict[str, float] = {}
            for k, ln in zip(keys, lines, strict=True):
                acc[k] = acc.get(k, 0.0) + ln.pnl
            return [AttributionLine(group=group, name=k, pnl_usd=v, contribution=v / nav0)
                    for k, v in sorted(acc.items())]

        factor_pnl: float | None = 0.0 if not lines else None
        if lines:
            factor_pnl, factor_lines, f_alerts = self._factor_attribution(ctx, prev, marked,
                                                                          model_prev)
            alerts += f_alerts
            out += factor_lines
            out += agg("issuer", [ln.issuer_id for ln in lines])
            out += agg("country", [meta(ln.issuer_id, "country", "country") for ln in lines])
            out += agg("sector", [meta(ln.issuer_id, "sector", "gics_sector") for ln in lines])
            sides = [Side.LONG.value if ln.mv_start > 0 else Side.SHORT.value for ln in lines]
            side_lines = agg("side", sides)
            order = {Side.LONG.value: 0, Side.SHORT.value: 1}
            out += sorted(side_lines, key=lambda a: order[a.name])
        return out, factor_pnl, alerts

    def _factor_returns_source(self, ctx: DailyContext, model_prev: RiskModel
                               ) -> Callable[[pd.Timestamp], pd.Series | None]:
        names = model_prev.factor_names
        frames = [m.factor_returns for m in (ctx.model, model_prev) if m is not None]
        cache: dict[pd.Timestamp, pd.Series | None] = {}

        def get(s: pd.Timestamp) -> pd.Series | None:
            if s in cache:
                return cache[s]
            row: pd.Series | None = None
            for fr in frames:
                if s in fr.index:
                    row = fr.loc[s].reindex(names)
                    break
            if row is None and s == ctx.ts and s in ctx.panel.returns.index:
                est = cross_sectional_factor_returns(model_prev.exposures,
                                                     ctx.panel.returns.loc[s],
                                                     model_prev.specific_var)
                if est is not None:
                    row = est.reindex(names)
                    ctx.cache["factor_fallback"] = True
            cache[s] = row
            return row

        return get

    def _factor_attribution(self, ctx: DailyContext, prev: DailyRecord | None, marked: _Marked,
                            model_prev: RiskModel | None
                            ) -> tuple[float | None, list[AttributionLine], list[str]]:
        nav0 = marked.nav_start
        if prev is None:
            return 0.0, [], []
        if model_prev is None:
            note = self._model_notes.get(prev.date, "")
            return None, [], [("Atribuição fatorial indisponível (modelo de risco da sessão "
                               "anterior ausente): fatores × específico não calculados. "
                               + note).strip()]
        get = self._factor_returns_source(ctx, model_prev)
        names = model_prev.factor_names
        calendar = ctx.panel.returns.index
        prev_ts, ts = pd.Timestamp(prev.date), ctx.ts
        fx_frame = ctx.cache.get("fx_frame")
        if fx_frame is None:
            self._fx(ctx)
            fx_frame = ctx.cache["fx_frame"]
        contrib = pd.Series(0.0, index=names)
        missing_days: set[str] = set()
        outside: list[str] = []
        session_missing = False
        for ln in marked.lines:
            if not ln.repriced:
                continue
            if ln.issuer_id not in model_prev.exposures.index:
                outside.append(ln.ticker)
                continue
            # Janela do retorno da linha: (último preço válido ≤ registro anterior, último ≤ hoje].
            if ln.ticker in ctx.md.adj_close.columns and ln.currency in fx_frame.columns:
                adj = pd.to_numeric(ctx.md.adj_close[ln.ticker], errors="coerce")
                lvl = adj.where(adj > 0) * fx_frame[ln.currency].reindex(adj.index)
                valid = lvl.dropna().index
                d0 = valid[valid <= prev_ts]
                d1 = valid[valid <= ts]
                start = d0[-1] if len(d0) else prev_ts
                end = d1[-1] if len(d1) else ts
            else:
                start, end = prev_ts, ts
            window = calendar[(calendar > start) & (calendar <= end)]
            f_sum = pd.Series(0.0, index=names)
            for s in window:
                row = get(s)
                if row is None:
                    if s == ts:
                        session_missing = True
                    else:
                        missing_days.add(str(s.date()))
                    continue
                f_sum = f_sum + row.fillna(0.0)
            b = model_prev.exposures.loc[ln.issuer_id].reindex(names).fillna(0.0)
            contrib = contrib + ln.mv_start * b * f_sum
        if session_missing:
            return None, [], [f"Retornos fatoriais de {ctx.date} indisponíveis (modelo e regressão "
                              "do dia): atribuição fatorial não calculada."]
        alerts: list[str] = []
        if ctx.cache.get("factor_fallback"):
            alerts.append("Retornos fatoriais do dia estimados por regressão cross-section com as "
                          "exposições da sessão anterior.")
        if missing_days:
            alerts.append("Sessões sem retornos fatoriais na janela de linhas que voltaram a "
                          "negociar (contribuição fatorial zero nelas): "
                          f"{_list(sorted(missing_days))}.")
        if outside:
            alerts.append("Linhas fora do modelo de risco (P&L classificado como específico): "
                          f"{_list(outside)}.")
        factor_pnl = float(contrib.sum())
        groups = model_prev.factor_groups
        lines: list[AttributionLine] = []
        for g in FACTOR_GROUPS:
            v = float(contrib[[f for f in names if groups.get(f) == g]].sum())
            lines.append(AttributionLine(group="factor_group", name=g, pnl_usd=v,
                                         contribution=v / nav0))
        for f in sorted(names):
            v = float(contrib[f])
            lines.append(AttributionLine(group="factor", name=f, pnl_usd=v, contribution=v / nav0))
        return factor_pnl, lines, alerts

    # ------------------------------------------------------------------ execução
    def _size(self, ctx: DailyContext, plan: _Plan, marked: _Marked, nav_pre: float
              ) -> tuple[list[_Exec], list[str]]:
        alerts: list[str] = []
        execs: list[_Exec] = []
        stale: list[str] = []
        min_lot: list[str] = []
        seen: set[tuple[str, str]] = set()
        for issuer, ticker, weight, ccy in plan.targets():
            if (issuer, ticker) in seen:
                raise ValueError(f"Linha {issuer}/{ticker} duplicada na carteira a executar.")
            seen.add((issuer, ticker))
            if not _finite(weight):
                raise ValueError(f"Peso não finito para {issuer}/{ticker}.")
            currency = self._line_currency(ctx, ticker, ccy)
            if currency != ccy:
                alerts.append(f"{ticker}: moeda da proposta ({ccy}) difere da linha ({currency}); "
                              "usada a moeda da linha.")
            if ticker not in ctx.md.close.columns:
                raise ValueError(f"Linha {ticker} ({issuer}) sem série de preços: execução "
                                 "impossível.")
            px, pdate = _last_valid(ctx.md.close[ticker], ctx.ts)
            if px is None:
                raise ValueError(f"Linha {ticker} ({issuer}) sem preço válido até {ctx.date}.")
            if pdate is not None and pdate < ctx.ts:
                stale.append(f"{ticker} ({pdate.date()})")
                if (ctx.ts - pdate).days > STALE_DAYS_MAX:
                    alerts.append(f"{ticker}: execução a preço com mais de {STALE_DAYS_MAX} dias.")
            fx = self._fx_rate(ctx, currency)
            if fx is None:
                raise ValueError(f"Câmbio {currency} indisponível em {ctx.date}: execução de "
                                 f"{ticker} impossível.")
            shares = _round_shares(weight * nav_pre / (px * fx))
            if shares == 0:
                shares = 1 if weight > 0 else -1
                min_lot.append(ticker)
            execs.append(_Exec(issuer, ticker, currency, shares, px, fx))
        if stale:
            alerts.append("Execução ao último fechamento disponível (sem negociação no pregão): "
                          f"{_list(stale)}.")
        if min_lot:
            alerts.append(f"Posição menor que uma ação; executada 1 ação: {_list(min_lot)}.")
        return execs, alerts

    def _cost_model(self, ctx: DailyContext, nav: float) -> CostModel:
        key = ("cost_model", round(nav, 2))
        if key not in ctx.cache:
            sides = issuer_side_lines(ctx.panel, self._availability(ctx))
            daily_vol = ctx.panel.returns.loc[:ctx.ts].tail(63).std()
            ctx.cache[key] = build_cost_model(sides, ctx.panel.assets, daily_vol, self.cfg, nav)
        return ctx.cache[key]

    def _fallback_bps(self, plan: _Plan) -> tuple[dict[str, float], float]:
        c = self.cfg.costs
        default = (max(c.half_spread_bps_by_tier.values()) + max(c.commission_bps.values())
                   + c.fx_cost_bps)
        bps: dict[str, float] = {}
        if plan.proposal is not None:
            for t in plan.proposal.trades:
                if _finite(t.est_cost_bps) and t.issuer_id not in bps:
                    bps[t.issuer_id] = float(t.est_cost_bps)
        return bps, default

    def _costs(self, ctx: DailyContext, old: list[_Line], execs: list[_Exec], nav_pre: float,
               plan: _Plan) -> tuple[float, list[str]]:
        """Custo (USD, positivo) de passar da carteira antiga (derivada) à executada."""
        w_old: dict[tuple[str, str], float] = {(ln.issuer_id, ln.ticker): ln.mv_end / nav_pre
                                               for ln in old if ln.mv_end != 0}
        w_new: dict[tuple[str, str], float] = {(e.issuer_id, e.ticker): e.mv / nav_pre
                                               for e in execs}
        passes: list[tuple[dict[str, float], dict[str, float]]] = [({}, {}), ({}, {}), ({}, {})]
        for key in sorted(set(w_old) | set(w_new)):
            iid = key[0]
            k = 0 if key in w_old and key in w_new else (1 if key in w_old else 2)
            tgt, cur = passes[k]
            tgt[iid] = tgt.get(iid, 0.0) + w_new.get(key, 0.0)
            cur[iid] = cur.get(iid, 0.0) + w_old.get(key, 0.0)
        alerts: list[str] = []
        try:
            cm = self._cost_model(ctx, nav_pre)
        except (ValueError, KeyError) as exc:
            cm = None
            alerts.append(f"Modelo de custos indisponível ({exc}): custos por bps de fallback.")
        bps, default_bps = self._fallback_bps(plan)
        total = 0.0
        fallback_used: list[str] = []
        for tgt, cur in passes:
            if not tgt:
                continue
            ids = sorted(tgt)
            known = [i for i in ids if cm is not None and i in cm.index]
            unknown = [i for i in ids if i not in known]
            if known:
                t = pd.Series({i: tgt[i] for i in known}, dtype=float)
                c = pd.Series({i: cur[i] for i in known}, dtype=float)
                est = estimate_rebalance_costs(t, c, cm)
                bad = est.index[~np.isfinite(est.to_numpy(dtype=float))]
                total += float(est.drop(bad).sum()) * nav_pre
                unknown += list(bad)
            for i in unknown:
                rate = bps.get(i, default_bps)
                total += abs(tgt[i] - cur[i]) * nav_pre * rate / 1e4
                fallback_used.append(i)
        if fallback_used:
            alerts.append("Custos por bps de fallback (proposta ou conservador de "
                          f"{default_bps:.0f} bps): {_list(sorted(set(fallback_used)))}.")
        return total, alerts

    def _build_entry(self, ctx: DailyContext, plan: _Plan, execs: list[_Exec], nav_pre: float,
                     cost_usd: float) -> BookEntry:
        nav_end = nav_pre - cost_usd
        note = (f"Execução hipotética MOC no fechamento de {ctx.date} (paper trading): "
                f"nocional-alvo = peso × NAV antes dos custos ({fmt_usd_mm(nav_pre)}), ações pelo "
                f"fechamento local e câmbio do dia; custos estimados {fmt_usd(cost_usd)}; NAV após "
                f"custos {fmt_usd_mm(nav_end)}.")
        if self.shadow is not None and plan.source == "sombra":
            note = "Carteira-sombra só-quant (contrafactual, sem decisão). " + note
        positions = [
            BookedPosition(issuer_id=e.issuer_id, ticker=e.ticker, weight=e.mv / nav_pre,
                           notional_usd=e.mv, shares=e.shares, entry_price_local=e.price_local,
                           currency=e.currency)
            for e in execs]
        return BookEntry(week=plan.week, proposal_id=plan.proposal_id,
                         approval_hash=plan.approval_hash,
                         booked_at=close_datetime(ctx.date, self.cfg), nav_usd=nav_pre,
                         positions=positions, pricing_note=note)

    def _build_hold_entry(self, ctx: DailyContext, plan: _Plan, nav_pre: float) -> BookEntry:
        """Efetivação de "manter": sem posições-alvo (como no livro); a carteira segue derivando."""
        return BookEntry(week=plan.week, proposal_id=plan.proposal_id,
                         approval_hash=plan.approval_hash,
                         booked_at=close_datetime(ctx.date, self.cfg), nav_usd=nav_pre,
                         positions=[],
                         pricing_note=(f"Manter a carteira anterior no fechamento de {ctx.date} "
                                       "(sem negociação, sem custos)."))

    # ------------------------------------------------------------------ posições e risco
    @staticmethod
    def _positions(lines: list[_Line], nav_end: float) -> list[DailyPosition]:
        out = []
        for ln in lines:
            side = (Side.LONG if ln.mv_end > 0 else Side.SHORT if ln.mv_end < 0
                    else Side.LONG if ln.mv_start >= 0 else Side.SHORT)
            out.append(DailyPosition(
                issuer_id=ln.issuer_id, ticker=ln.ticker, currency=ln.currency, side=side,
                shares=ln.shares, price_local=ln.price_local, price_usd=ln.price_usd,
                market_value_usd=ln.mv_end, weight=ln.mv_end / nav_end, day_pnl_usd=ln.pnl,
                day_return_usd=ln.ret, repriced=ln.repriced))
        out.sort(key=lambda p: (p.market_value_usd == 0, -abs(p.market_value_usd), p.issuer_id,
                                p.ticker))
        return out

    def _risk(self, ctx: DailyContext, side: _MainSide | _ShadowSide,
              positions: list[DailyPosition], nav_end: float, ret_today: float,
              nav_start: float, prev: DailyRecord | None) -> tuple[DailyRisk, list[str]]:
        cfg = self.cfg
        alerts: list[str] = []
        w = pd.Series(dtype=float)
        for p in positions:
            if p.market_value_usd != 0:
                w.loc[p.issuer_id] = w.get(p.issuer_id, 0.0) + p.market_value_usd / nav_end
        w = w[w != 0].sort_index()
        gross = float(w.abs().sum())
        net = float(w.sum())
        ex_ante = factor_vol = specific_vol = beta = var = es = None
        exposures: list[ExposureLine] = []
        model = ctx.risk_model
        if w.empty:
            ex_ante = factor_vol = specific_vol = beta = var = es = 0.0
        elif model is not None:
            outside = sorted(set(w.index) - set(model.assets))
            if outside:
                alerts.append("Emissores fora do modelo de risco (risco ex-ante parcial): "
                              f"{_list(outside)}.")
            wm = w[w.index.isin(model.assets)]
            if not wm.empty:
                dec = risk_decomposition(wm, model)
                ex_ante, factor_vol, specific_vol = dec.total_vol, dec.factor_vol, dec.specific_vol
                pv, pe = parametric_var_es(wm, model, cfg.risk.var_confidence, 1)
                try:
                    hv, he = historical_var_es(wm, ctx.panel, model, cfg.risk.var_confidence, 1)
                except ValueError:
                    hv, he = math.nan, math.nan
                var = float(np.nanmax([pv, hv]))
                es = float(np.nanmax([pe, he]))
                try:
                    betas = predicted_betas(model, market_weights(ctx.panel, model.assets))
                    beta = float(betas.reindex(wm.index).fillna(0.0) @ wm)
                except ValueError as exc:
                    alerts.append(f"Beta previsto indisponível: {exc}")
                x = dec.exposures
                for s in STYLE_FACTORS:
                    if s in x.index:
                        exposures.append(ExposureLine(
                            group="style", name=s, long=0.0, short=0.0, net=float(x[s]),
                            gross=abs(float(x[s])), limit=cfg.risk.style_exposure_max_abs))
        exposures = self._group_exposures(ctx, w) + exposures

        hist = side.track.frame()
        rets = list(hist["ret"].astype(float)) + [ret_today]
        rv21 = realized_vol(rets, REALIZED_VOL_WINDOWS[0])
        rv63 = realized_vol(rets, REALIZED_VOL_WINDOWS[1])
        if hist.empty:
            peak = nav_start
        else:
            nav0 = float(hist["nav"].iloc[0] - hist["pnl"].iloc[0])
            peak = max(nav0, float(hist["nav"].max()))
        nav_peak = max(peak, nav_end)
        drawdown = nav_end / nav_peak - 1.0

        max_days = pct_1d = None
        if not w.empty:
            prof = liquidity_profile(w, ctx.panel.assets["adtv_usd"], nav_end,
                                     cfg.liquidity.participation_rate)
            days = prof["days_to_liquidate"].astype(float)
            max_days = float(days.max()) if np.isfinite(days.max()) else None
            if max_days is None:
                alerts.append("ADTV indisponível para alguma posição: dias para liquidar "
                              "indeterminados.")
            summ = liquidity_summary(prof)
            if 1.0 in summ.index and _finite(summ.loc[1.0, "gross"]):
                pct_1d = float(summ.loc[1.0, "gross"])
        squeeze_high = 0
        shorts = w[w < 0]
        if not shorts.empty:
            sq = self._squeeze(ctx)
            if sq is not None:
                buckets = sq["bucket"].reindex(shorts.index)
                squeeze_high = int((buckets == "HIGH").sum())
        risk = DailyRisk(
            ex_ante_vol=ex_ante, factor_vol=factor_vol, specific_vol=specific_vol, beta=beta,
            gross=gross, net=net, long_exposure=float(w[w > 0].sum()),
            short_exposure=float(w[w < 0].sum()), n_long=int((w > 0).sum()),
            n_short=int((w < 0).sum()), var_1d_99=var, es_1d_99=es, realized_vol_21d=rv21,
            realized_vol_63d=rv63, drawdown=float(drawdown), max_days_to_liquidate=max_days,
            pct_gross_liquid_1d=pct_1d, squeeze_high_shorts=squeeze_high, exposures=exposures)
        alerts = risk_alerts(cfg, risk, has_positions=not w.empty) + alerts
        if w.empty:
            alerts.append("Carteira sem posições (100% caixa).")
        for e in exposures:
            if e.group in ("country", "sector", "style") and e.limit is not None \
                    and abs(e.net) > e.limit + 1e-9:
                label = {"country": "país", "sector": "setor", "style": "estilo"}[e.group]
                val = (fmt_pct(e.net, signed=True) if e.group != "style"
                       else fmt_num(e.net, 3, signed=True))
                lim = fmt_pct(e.limit) if e.group != "style" else fmt_num(e.limit, 3)
                alerts.append(f"Exposição líquida de {label} {e.name} {val} acima do limite "
                              f"±{lim}.")
        return risk, alerts

    def _group_exposures(self, ctx: DailyContext, w: pd.Series) -> list[ExposureLine]:
        if w.empty:
            return []
        assets = ctx.panel.assets
        out: list[ExposureLine] = []
        for group, col, limit in (("country", "country", self.cfg.risk.country_net_max_abs),
                                  ("sector", "sector", self.cfg.risk.sector_net_max_abs)):
            keys = assets[col].reindex(w.index).fillna("NA").astype(str)
            for k in sorted(keys.unique()):
                ww = w[keys == k]
                out.append(ExposureLine(group=group, name=k, long=float(ww[ww > 0].sum()),
                                        short=float(ww[ww < 0].sum()), net=float(ww.sum()),
                                        gross=float(ww.abs().sum()), limit=limit))
        return out

    def _squeeze(self, ctx: DailyContext) -> pd.DataFrame | None:
        if "squeeze" not in ctx.cache:
            try:
                ctx.cache["squeeze"] = squeeze_table(ctx.panel, ctx.md, self._availability(ctx),
                                                     self.cfg)
            except (ValueError, KeyError) as exc:
                ctx.cache["squeeze"] = None
                ctx.notes.append(f"Tabela de squeeze indisponível: {exc}")
        return ctx.cache["squeeze"]

    def _position_alerts(self, ctx: DailyContext, side: _MainSide | _ShadowSide,
                         positions: list[DailyPosition], nav_end: float,
                         proposal: Proposal | None) -> list[str]:
        cfg = self.cfg
        alerts: list[str] = []
        held = [p for p in positions if p.market_value_usd != 0]
        # Liquidez por posição (participação e limite por lado).
        adtv = ctx.panel.assets["adtv_usd"]
        by_issuer: dict[str, float] = {}
        for p in held:
            by_issuer[p.issuer_id] = by_issuer.get(p.issuer_id, 0.0) + p.market_value_usd
        illiquid: list[str] = []
        for iid, mv in sorted(by_issuer.items()):
            a = adtv.get(iid, np.nan)
            if mv > 0:
                rate = cfg.liquidity.participation_rate
                limit = cfg.liquidity.max_days_to_liquidate_long
            else:
                rate, limit = (cfg.liquidity.short_participation_rate,
                               cfg.liquidity.max_days_to_liquidate_short)
            if not (_finite(a) and a > 0):
                illiquid.append(f"{iid} (ADTV indisponível)")
                continue
            days = abs(mv) / (rate * float(a))
            if days > limit + 1e-9:
                illiquid.append(f"{iid} ({fmt_days(days)} > {fmt_days(limit)})")
        if illiquid:
            alerts.append(f"Posições acima do limite de liquidez: {_list(illiquid)}.")
        # Squeeze: shorts em HIGH (e mudança desde a decisão) e stops de perda.
        shorts = [p for p in held if p.market_value_usd < 0]
        if shorts:
            sq = self._squeeze(ctx)
            decided = {}
            if proposal is not None:
                decided = {p.issuer_id: p.squeeze_bucket for p in proposal.positions
                           if p.side == Side.SHORT}
            if sq is not None:
                for p in shorts:
                    b = sq["bucket"].get(p.issuer_id) if p.issuer_id in sq.index else None
                    if b == "HIGH":
                        was = decided.get(p.issuer_id)
                        change = (f" (era {was} na decisão)" if was and was != "HIGH" else "")
                        alerts.append(f"Short {p.ticker} ({p.issuer_id}) com risco de squeeze "
                                      f"HIGH{change}: reavaliar/reduzir.")
            current = {p.ticker: (float(p.shares), float(p.price_local)) for p in shorts
                       if p.shares is not None and p.price_local is not None}
            entries = short_entry_prices(side.track.iter_records(reverse=True), current)
            for p in shorts:
                avg = entries.get(p.ticker)
                if avg is None or p.price_local is None or p.shares is None:
                    continue
                loss = p.price_local / avg - 1.0
                fx = self._fx_rate(ctx, p.currency)
                loss_usd = abs(p.shares) * (p.price_local - avg) * (fx or 0.0)
                if loss >= cfg.squeeze.stop_short_position_loss:
                    limit = fmt_pct(cfg.squeeze.stop_short_position_loss)
                    alerts.append(f"STOP DE SQUEEZE: short {p.ticker} perde {fmt_pct(loss)} desde "
                                  f"a entrada (limite {limit}): cortar 50% da posição.")
                if fx is not None and loss_usd / nav_end >= cfg.squeeze.stop_short_nav_loss:
                    alerts.append(f"STOP DE SQUEEZE: short {p.ticker} perde "
                                  f"{fmt_pct(loss_usd / nav_end)} do NAV desde a entrada (limite "
                                  f"{fmt_pct(cfg.squeeze.stop_short_nav_loss)}): cortar 50%.")
        missing = sorted(set(ctx.md.manifest.missing_tickers) & {p.ticker for p in held})
        if missing:
            alerts.append(f"Linhas da carteira ausentes na coleta de dados: {_list(missing)}.")
        return alerts

    def _input_hashes(self, ctx: DailyContext, entry: BookEntry | None,
                      proposal: Proposal | None, model_prev: RiskModel | None) -> dict[str, str]:
        h: dict[str, str] = {
            "market_data": ctx.md.manifest.content_hash(),
            "config": self.cfg.config_hash(),
        }
        if ctx.md.universe.source_sha256:
            h["universe"] = ctx.md.universe.source_sha256
        h.update(store_input_hashes(self.store, ctx.date))
        if entry is not None:
            h["book_entry"] = sha256_obj(entry)
            h["approval"] = entry.approval_hash
        if proposal is not None:
            h["proposal"] = proposal.proposal_hash()
        if ctx.model is not None:
            h["risk_model"] = _meta_hash(ctx.model)
        if model_prev is not None:
            h["risk_model_prev"] = _meta_hash(model_prev)
        return h


# ==========================================================
# Funções auxiliares de módulo
# ==========================================================

def marked_financing(nav_start: float, rate_annual: float, days: int) -> float:
    """Juros do caixa/colateral: NAV inicial × taxa / 360 × dias corridos (ACT/360)."""
    return float(nav_start) * float(rate_annual) / DAY_COUNT_BASIS * int(days)


def _merge_execution(old: list[_Line], execs: list[_Exec]) -> list[_Line]:
    """Posições de fim de dia após a execução: continuadas, encerradas (valor 0) e novas."""
    new = {(e.issuer_id, e.ticker): e for e in execs}
    out: list[_Line] = []
    for ln in old:
        e = new.pop((ln.issuer_id, ln.ticker), None)
        if e is None:
            out.append(_Line(ln.issuer_id, ln.ticker, ln.currency, 0.0, ln.mv_start, ln.pnl,
                             ln.ret, ln.repriced, 0.0, ln.price_local, ln.price_usd))
        else:
            out.append(_Line(ln.issuer_id, ln.ticker, e.currency, float(e.shares), ln.mv_start,
                             ln.pnl, ln.ret, ln.repriced, e.mv, e.price_local,
                             e.price_local * e.fx))
    for e in execs:
        if (e.issuer_id, e.ticker) in new:
            out.append(_Line(e.issuer_id, e.ticker, e.currency, float(e.shares), 0.0, 0.0, 0.0,
                             True, e.mv, e.price_local, e.price_local * e.fx))
    return out


def _check_track_tail(track: TrackRecord, prev: DailyRecord | None) -> None:
    """O CSV-resumo precisa terminar no último registro JSON (senão: rode ``verify()``)."""
    frame = track.frame()
    if prev is None:
        if not frame.empty:
            raise ValueError(f"Track record inconsistente em {track.root}: CSV sem registros JSON.")
        return
    if frame.empty or frame["record_hash"].iloc[-1] != prev.record_hash:
        raise ValueError(f"Track record inconsistente em {track.root}: o CSV não termina no último "
                         "registro JSON (rode verify()).")
