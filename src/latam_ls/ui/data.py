"""Leitura defensiva dos artefatos do CDP para o app (sem Streamlit; testável).

Regras:

- Somente leitura: nada aqui grava arquivos, exceto :func:`set_kill_switch` (única ação de escrita
  do app, delegada a ``workflow.runtime.Runtime`` e auditada na trilha).
- Diretórios ausentes (antes da inception) viram estruturas vazias — nunca exceções nem pastas
  criadas como efeito colateral.
- Números vêm dos registros gravados pelo pipeline; aqui só há agregações simples (somas,
  composição de retornos diários, contagens) sobre esses registros, rotuladas "Calculado" na UI.
- Ausente continua ausente (``None``/``NaN``), nunca zero.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

import pandas as pd

from ..audit import AuditLog
from ..config import FundConfig, load_config
from ..contracts import (
    AuditEvent,
    BookEntry,
    DailyRecord,
    Decision,
    ExposureLine,
    LLMCallRecord,
    PositionTarget,
    Proposal,
    ResearchPack,
)
from . import fmt
from .settings import AppPaths

TRACK_DIR = "track_record"
SHADOW_DIR = "track_record_shadow"
AUDIT_FILE = "audit_log.jsonl"
KILL_SWITCH_FILE = "KILL_SWITCH"
SHADOW_RECORD_EVENT_FALLBACK = "DAILY_RECORD_SHADOW"
LLM_LEDGER_NAME = "llm_calls.jsonl"
REPORT_STEM = "relatorio"
COMMENTARY_SECTION = "Comentário do dia"
GOVERNANCE_SCOPES = {"GOVERNANÇA", "GOVERNANCA"}
KILL_SWITCH_MIN_REASON = 10
RESIZE_THRESHOLD = 0.0025
COMPONENT_ORDER = ("equity", "factor", "specific", "costs", "borrow", "financing")
PERIOD_OPTIONS = ("Dia", "Semana", "MTD", "YTD", "ITD", "Personalizado")
LIQUIDITY_BUCKETS = ((1.0, "≤ 1 dia"), (2.0, "1–2 dias"), (3.0, "2–3 dias"), (5.0, "3–5 dias"),
                     (float("inf"), "> 5 dias"))
_SKIP_DIRS = frozenset({"raw", "__pycache__", ".git", "staging"})
_PLACEHOLDER_RE = re.compile(r"\{\{\s*fact:([^}\s]+)\s*\}\}")
_MIND_RE = re.compile(r"mente\s+([\w.-]+)\s*\[IA\]", re.IGNORECASE)

CDP_INVARIANTS = (
    "Números só em código testado: retornos, riscos, pesos, custos e contribuições vêm de Python "
    "determinístico; a mente (IA) só emite juízos estruturados com placeholders de fatos.",
    "IA só aperta, nunca afrouxa: visões podem inclinar o alpha dentro de um teto pequeno e "
    "restringir risco, nunca ampliar limites do mandato.",
    "Decisão autônoma sob gates determinísticos: falha HARD de compliance nunca é executada; "
    "fallback para restrições, só-quant ou manter a carteira.",
    "Tudo vinculado por hash: decisão, proposta, snapshot, mandato, pesquisa, decisão do PM e "
    "gates de risco; registros diários encadeados e trilha de auditoria append-only.",
    "Sem look-ahead: a carteira da semana usa dados até o momento da análise e é executada no "
    "fechamento (MOC) do primeiro pregão da semana na B3.",
    "Dados ausentes nunca viram zero; dados simulados carregam sempre 'DADOS SIMULADOS'.",
    "Notícias são conteúdo não confiável: instruções embutidas nunca alteram o estado do fundo.",
    "KILL SWITCH de emergência: com o arquivo book/KILL_SWITCH presente, só operações que reduzem "
    "risco são aceitas; ligar/desligar é auditado.",
)

T = TypeVar("T")


# ==========================================================
# Utilidades
# ==========================================================

def fingerprint(*paths: Path | str, skip_dirs: Iterable[str] = _SKIP_DIRS) -> str:
    """Impressão digital (caminho relativo, tamanho, mtime) de arquivos/árvores para o cache.

    Muda sempre que um arquivo é criado, removido ou alterado; ausente ⇒ marcador estável.
    """
    skip = set(skip_dirs)
    h = hashlib.sha256()
    for raw in paths:
        p = Path(raw)
        h.update(f"#{p.as_posix()}\n".encode())
        try:
            if not p.exists():
                h.update(b"ausente\n")
                continue
            if p.is_file():
                st = p.stat()
                h.update(f"{p.name}|{st.st_size}|{st.st_mtime_ns}\n".encode())
                continue
        except OSError:
            h.update(b"erro\n")
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = sorted(d for d in dirnames if d not in skip and not d.startswith("."))
            for name in sorted(filenames):
                if name.startswith(".tmp_"):
                    continue
                fp = Path(dirpath) / name
                try:
                    st = fp.stat()
                except OSError:
                    continue
                rel = fp.relative_to(p).as_posix()
                h.update(f"{rel}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def _attempt(issues: list[str], label: str, fn: Callable[[], T], default: T) -> T:
    """Executa ``fn``; erro vira apontamento legível (o app nunca quebra por um artefato)."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura vira apontamento
        issues.append(f"{label}: {type(exc).__name__}: {str(exc)[:300]}")
        return default


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _finite(x: object) -> float | None:
    return float(x) if fmt.is_num(x) else None  # type: ignore[arg-type]


def compound(returns: Iterable[object]) -> float | None:
    """Retorno composto Π(1 + r) − 1; vazio ou algum dia ausente ⇒ ``None`` (nunca zero)."""
    growth = 1.0
    n = 0
    for r in returns:
        v = _finite(r)
        if v is None:
            return None
        growth *= 1.0 + v
        n += 1
    return growth - 1.0 if n else None


def render_facts(text: str | None, facts: dict[str, str]) -> str:
    """Troca ``{{fact:id}}`` pelo valor formatado pelo código (FactBook do briefing).

    Fato desconhecido ⇒ marcador explícito (nunca um número inventado).
    """
    if not text:
        return ""

    def _sub(m: re.Match[str]) -> str:
        fid = m.group(1)
        return facts.get(fid, f"[fato {fid} indisponível]")

    return _PLACEHOLDER_RE.sub(_sub, str(text))


# ==========================================================
# Mandato
# ==========================================================

@dataclass
class ConfigInfo:
    cfg: FundConfig
    path: Path
    text: str
    config_hash: str
    error: str | None = None

    @property
    def from_file(self) -> bool:
        return self.error is None


def load_config_info(path: Path) -> ConfigInfo:
    """Mandato do arquivo; inválido/ausente ⇒ padrões do código com o erro explícito."""
    p = Path(path)
    try:
        cfg = load_config(p)
        return ConfigInfo(cfg=cfg, path=p, text=p.read_text(encoding="utf-8"),
                          config_hash=cfg.config_hash())
    except Exception as exc:  # noqa: BLE001 - YAML/validação/arquivo ausente
        cfg = FundConfig()
        return ConfigInfo(cfg=cfg, path=p, text="", config_hash=cfg.config_hash(),
                          error=f"{type(exc).__name__}: {str(exc)[:300]}")


# ==========================================================
# Track record
# ==========================================================

def _shadow_event() -> str:
    try:
        from ..workflow.daily import SHADOW_RECORD_EVENT
    except Exception:  # noqa: BLE001 - módulo em evolução: usa o nome documentado
        return SHADOW_RECORD_EVENT_FALLBACK
    return SHADOW_RECORD_EVENT


@dataclass
class TrackData:
    """Track record do CDP e da sombra só-quant (somente o que foi gravado)."""

    exists: bool = False
    records: list[DailyRecord] = field(default_factory=list)
    shadow_records: list[DailyRecord] = field(default_factory=list)
    frame: pd.DataFrame | None = None
    shadow_frame: pd.DataFrame | None = None
    compare: pd.DataFrame | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    monthly: pd.DataFrame | None = None
    csv_bytes: bytes | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.records

    @property
    def latest(self) -> DailyRecord | None:
        return self.records[-1] if self.records else None

    def history_until(self, record: DailyRecord) -> list[DailyRecord]:
        """Registros estritamente anteriores a ``record`` (sem look-ahead)."""
        return [r for r in self.records if r.date < record.date]

    @property
    def dates(self) -> list[date]:
        return [r.date for r in self.records]


def load_track(book_root: Path, cfg: FundConfig) -> TrackData:
    from ..workflow.track_record import TrackRecord, compare_tracks

    root = Path(book_root)
    td = TrackData()
    main_dir = root / TRACK_DIR
    if not root.is_dir() or not main_dir.is_dir():
        return td
    td.exists = True
    issues = td.issues
    main = TrackRecord(main_dir)
    td.records = _attempt(issues, "Track record (registros)", main.records, [])
    td.frame = _attempt(issues, "Track record (CSV)", main.frame, None)
    td.stats = _attempt(issues, "Track record (estatísticas)", lambda: main.stats(cfg), {})
    td.monthly = _attempt(issues, "Track record (grade mensal)", main.monthly_returns_table, None)
    if main.csv_path.is_file():
        td.csv_bytes = _attempt(issues, "Track record (download)", main.csv_path.read_bytes, None)
    shadow_dir = root / SHADOW_DIR
    if shadow_dir.is_dir():
        shadow = TrackRecord(shadow_dir, audit_event=_shadow_event())
        td.shadow_records = _attempt(issues, "Sombra só-quant (registros)", shadow.records, [])
        td.shadow_frame = _attempt(issues, "Sombra só-quant (CSV)", shadow.frame, None)
        td.compare = _attempt(issues, "CDP vs sombra", lambda: compare_tracks(main, shadow), None)
    return td


def track_table(records: Sequence[DailyRecord]) -> pd.DataFrame:
    """Tabela numérica do track record (uma linha por registro; ausente = NaN)."""
    rows = []
    for r in records:
        c = r.pnl_components
        rk = r.risk
        rows.append({
            "Data": r.date, "NAV (USD)": r.nav_end_usd, "Retorno": r.ret, "P&L (USD)": r.pnl_usd,
            "Fatorial": c.get("factor"), "Específico": c.get("specific"), "Custos": c.get("costs"),
            "Aluguel": c.get("borrow"), "Financiamento": c.get("financing"),
            "Gross": rk.gross, "Net": rk.net, "Beta": rk.beta, "Vol ex-ante": rk.ex_ante_vol,
            "Drawdown": rk.drawdown, "Hash": (r.record_hash or "")[:12],
        })
    cols = ["Data", "NAV (USD)", "Retorno", "P&L (USD)", "Fatorial", "Específico", "Custos",
            "Aluguel", "Financiamento", "Gross", "Net", "Beta", "Vol ex-ante", "Drawdown", "Hash"]
    return pd.DataFrame(rows, columns=cols)


def risk_series(records: Sequence[DailyRecord]) -> pd.DataFrame:
    """Vol ex-ante, vol realizada 21d/63d e drawdown por data (dos registros)."""
    rows = [{"date": pd.Timestamp(r.date), "ex_ante_vol": r.risk.ex_ante_vol,
             "realized_vol_21d": r.risk.realized_vol_21d,
             "realized_vol_63d": r.risk.realized_vol_63d, "drawdown": r.risk.drawdown,
             "gross": r.risk.gross, "net": r.risk.net, "beta": r.risk.beta}
            for r in records]
    df = pd.DataFrame(rows, columns=["date", "ex_ante_vol", "realized_vol_21d",
                                     "realized_vol_63d", "drawdown", "gross", "net", "beta"])
    df = df.set_index("date")
    return df.astype(float)


def period_summary(record: DailyRecord, history: Sequence[DailyRecord]) -> dict[str, Any]:
    """MTD/YTD/ITD pelo mesmo código do comentário/relatório diário."""
    from ..research.commentary import period_returns

    return period_returns(record, list(history))


# ==========================================================
# Livro semanal
# ==========================================================

@dataclass
class WeekData:
    week: date
    proposals: list[Proposal] = field(default_factory=list)
    states: dict[int, str] = field(default_factory=dict)
    decisions: dict[int, Decision] = field(default_factory=dict)
    booked: BookEntry | None = None
    research: ResearchPack | None = None
    pm_output: Any | None = None
    attempts: dict[str, Any] | None = None
    shadow: Proposal | None = None
    llm_calls: list[LLMCallRecord] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def proposal(self) -> Proposal | None:
        """Proposta efetivada (se houver) ou a versão mais recente."""
        if self.booked is not None:
            for p in self.proposals:
                if p.proposal_id == self.booked.proposal_id:
                    return p
        return self.proposals[-1] if self.proposals else None

    @property
    def decision(self) -> Decision | None:
        p = self.proposal
        if p is not None and p.version in self.decisions:
            return self.decisions[p.version]
        return self.decisions[max(self.decisions)] if self.decisions else None

    @property
    def state(self) -> str | None:
        p = self.proposal
        return self.states.get(p.version) if p is not None else None

    @property
    def mind(self) -> str | None:
        d = self.decision
        if d is not None and d.mind:
            return d.mind
        if self.research is not None and self.research.mind:
            return self.research.mind
        mind = getattr(self.pm_output, "mind", None)
        return str(mind) if mind else None

    @property
    def path_taken(self) -> str | None:
        if self.attempts and self.attempts.get("path"):
            return str(self.attempts["path"])
        p = self.proposal
        label = p.overrides.get("label") if p is not None else None
        return str(label) if label else None


@dataclass(frozen=True)
class KillSwitchState:
    active: bool
    reason: str = ""
    by: str = ""
    created_at: str = ""
    error: str | None = None


@dataclass
class BookData:
    root: Path
    exists: bool = False
    weeks: list[WeekData] = field(default_factory=list)
    kill_switch: KillSwitchState = field(default_factory=lambda: KillSwitchState(False))
    issues: list[str] = field(default_factory=list)

    def week(self, d: date) -> WeekData | None:
        return next((w for w in self.weeks if w.week == d), None)

    def previous(self, d: date) -> WeekData | None:
        before = [w for w in self.weeks if w.week < d and w.proposal is not None]
        return before[-1] if before else None

    @property
    def latest(self) -> WeekData | None:
        with_prop = [w for w in self.weeks if w.proposal is not None]
        return with_prop[-1] if with_prop else (self.weeks[-1] if self.weeks else None)

    @property
    def decided_weeks(self) -> set[date]:
        return {w.week for w in self.weeks if w.decisions}

    def live_week(self, record: DailyRecord | None) -> WeekData | None:
        """Semana da carteira vigente no registro (ou a mais recente com proposta)."""
        if record is not None and record.live_book_week is not None:
            wd = self.week(record.live_book_week)
            if wd is not None:
                return wd
        return self.latest

    def live_proposal(self, record: DailyRecord | None) -> Proposal | None:
        wd = self.live_week(record)
        return wd.proposal if wd is not None else None


def kill_switch_state(book_root: Path) -> KillSwitchState:
    p = Path(book_root) / KILL_SWITCH_FILE
    if not p.exists():
        return KillSwitchState(False)
    try:
        raw = read_json(p)
    except (OSError, ValueError):
        return KillSwitchState(True, error="Arquivo KILL_SWITCH sem JSON válido (ativo mesmo "
                                           "assim: a presença do arquivo basta).")
    if not isinstance(raw, dict):
        return KillSwitchState(True, error="Arquivo KILL_SWITCH com conteúdo inesperado.")
    return KillSwitchState(True, reason=str(raw.get("reason") or ""), by=str(raw.get("by") or ""),
                           created_at=str(raw.get("created_at") or raw.get("at") or ""))


def _load_llm_calls(week_dir: Path, issues: list[str]) -> list[LLMCallRecord]:
    out: list[LLMCallRecord] = []
    for path in sorted(week_dir.rglob(LLM_LEDGER_NAME)):
        if any(part in _SKIP_DIRS for part in path.relative_to(week_dir).parts[:-1]):
            continue
        text = read_text(path) or ""
        bad = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                out.append(LLMCallRecord.model_validate_json(line))
            except ValueError:
                bad += 1
        if bad:
            issues.append(f"Ledger de IA {path.name}: {bad} linha(s) inválida(s) ignorada(s).")
    return out


def _load_pm_output(path: Path, issues: list[str]) -> Any | None:
    if not path.is_file():
        return None
    from ..research.pm_agent import PMDecisionOutput

    try:
        return PMDecisionOutput.model_validate(read_json(path))
    except Exception as exc:  # noqa: BLE001 - arquivo da mente fora do schema
        issues.append(f"Decisão do PM (inputs/pm_decision.json) fora do schema: "
                      f"{type(exc).__name__}.")
        return None


def _load_shadow(book_root: Path, week: date, week_dir: Path, issues: list[str]
                 ) -> Proposal | None:
    for path in (week_dir / "shadow_quant.json",
                 book_root / SHADOW_DIR / "proposals" / f"{week.isoformat()}.json"):
        if path.is_file():
            return _attempt(issues, f"Sombra só-quant ({path.name})",
                            lambda p=path: Proposal.model_validate(read_json(p)), None)
    return None


def _load_facts(week_dir: Path, issues: list[str]) -> dict[str, str]:
    path = week_dir / "briefing" / "context.json"
    if not path.is_file():
        return {}
    raw = _attempt(issues, "Briefing (context.json)", lambda: read_json(path), None)
    facts = raw.get("facts") if isinstance(raw, dict) else None
    if not isinstance(facts, dict):
        return {}
    return {str(k): str(v.get("formatted", fmt.NA)) for k, v in facts.items()
            if isinstance(v, dict)}


def _load_week(book: Any, root: Path, week: date) -> WeekData:
    wd = WeekData(week=week)
    issues = wd.issues
    week_dir = root / week.isoformat()
    for v in _attempt(issues, "Versões de proposta", lambda: book.proposal_versions(week), []):
        p = _attempt(issues, f"Proposta v{v}", lambda v=v: book.load_proposal(week, v), None)
        if p is not None:
            wd.proposals.append(p)
    states = _attempt(issues, "Estados das propostas", lambda: book.week_states(week), {})
    wd.states = {int(k): getattr(s, "value", str(s)) for k, s in states.items()}
    wd.decisions = _attempt(issues, "Decisões", lambda: book.list_decisions(week), {})
    wd.booked = _attempt(issues, "Efetivação (booked.json)", lambda: book.load_booked(week), None)
    wd.research = _attempt(issues, "Pacote de pesquisa",
                           lambda: book.load_research_pack(week), None)
    wd.pm_output = _load_pm_output(week_dir / "inputs" / "pm_decision.json", issues)
    attempts_path = week_dir / "attempts.json"
    if attempts_path.is_file():
        raw = _attempt(issues, "Tentativas (attempts.json)", lambda: read_json(attempts_path),
                       None)
        wd.attempts = raw if isinstance(raw, dict) else None
    wd.shadow = _load_shadow(root, week, week_dir, issues)
    wd.llm_calls = _load_llm_calls(week_dir, issues) if week_dir.is_dir() else []
    wd.facts = _load_facts(week_dir, issues)
    return wd


def load_book(book_root: Path) -> BookData:
    root = Path(book_root)
    bd = BookData(root=root)
    if not root.is_dir():
        return bd
    bd.exists = True
    bd.kill_switch = kill_switch_state(root)
    from ..workflow.book import Book

    book = _attempt(bd.issues, "Livro", lambda: Book(root), None)
    if book is None:
        return bd
    weeks = _attempt(bd.issues, "Semanas do livro", book.list_weeks, [])
    bd.weeks = [_load_week(book, root, w) for w in weeks]
    return bd


def synthetic_artifacts(track: TrackData, book: BookData) -> list[str]:
    """Artefatos carregados marcados como sintéticos (para o banner DADOS SIMULADOS)."""
    found: list[str] = []
    if any(r.is_synthetic for r in track.records):
        found.append("track record")
    if any(r.is_synthetic for r in track.shadow_records):
        found.append("sombra só-quant")
    for w in book.weeks:
        if any(p.is_synthetic for p in w.proposals) or (w.shadow and w.shadow.is_synthetic):
            found.append(f"propostas {w.week.isoformat()}")
        if w.research is not None and w.research.is_synthetic:
            found.append(f"pesquisa {w.week.isoformat()}")
    return found


# ==========================================================
# Kill switch (única escrita do app)
# ==========================================================

def validate_kill_switch_request(turn_on: bool, reason: str, by: str, confirmed: bool,
                                 active: bool) -> list[str]:
    """Problemas que impedem ligar/desligar o kill switch (lista vazia ⇒ pode executar)."""
    problems: list[str] = []
    if turn_on and active:
        problems.append("O kill switch já está LIGADO.")
    if not turn_on and not active:
        problems.append("O kill switch já está DESLIGADO.")
    if len((reason or "").strip()) < KILL_SWITCH_MIN_REASON:
        problems.append(f"Informe o motivo (mínimo de {KILL_SWITCH_MIN_REASON} caracteres).")
    if len((by or "").strip()) < 2:
        problems.append("Informe o responsável pela ação.")
    if not confirmed:
        problems.append("Marque a confirmação explícita.")
    return problems


def set_kill_switch(paths: AppPaths, cfg: FundConfig, turn_on: bool, reason: str,
                    by: str) -> KillSwitchState:
    """Liga/desliga ``book/KILL_SWITCH`` via ``Runtime`` (evento KILL_SWITCH_ON/OFF auditado)."""
    from ..workflow.runtime import Runtime

    rt = Runtime(cfg=cfg, book_root=Path(paths.book), market_root=Path(paths.market),
                 reports_root=Path(paths.reports))
    rt.set_kill_switch(turn_on, reason.strip(), by.strip())
    return kill_switch_state(Path(paths.book))


# ==========================================================
# Trilha de auditoria e integridade
# ==========================================================

@dataclass
class AuditData:
    exists: bool = False
    events: list[AuditEvent] = field(default_factory=list)
    chain_ok: bool | None = None
    chain_message: str = ""
    error: str | None = None


def load_audit(book_root: Path) -> AuditData:
    path = Path(book_root) / AUDIT_FILE
    if not path.is_file():
        return AuditData(chain_message="Trilha de auditoria ainda não existe (antes da inception).")
    log = AuditLog(path)
    try:
        events = log.events()
    except Exception as exc:  # noqa: BLE001 - linha corrompida
        return AuditData(exists=True, chain_ok=False, chain_message="Trilha ilegível.",
                         error=f"{type(exc).__name__}: {str(exc)[:300]}")
    ok, msg = log.verify_chain()
    return AuditData(exists=True, events=events, chain_ok=ok, chain_message=msg)


def audit_frame(events: Sequence[AuditEvent], tz: str = "America/Sao_Paulo") -> pd.DataFrame:
    rows = [{"Seq": ev.seq, "Horário": fmt.dt_local(ev.ts, tz), "Evento": ev.event_type,
             "Ator": ev.actor, "Semana": ev.week.isoformat() if ev.week else "",
             "Resumo": ev.summary, "Payload": ev.payload_hash[:12],
             "Hash": ev.event_hash[:12], "Anterior": ev.prev_hash[:12]}
            for ev in events]
    cols = ["Seq", "Horário", "Evento", "Ator", "Semana", "Resumo", "Payload", "Hash", "Anterior"]
    return pd.DataFrame(rows, columns=cols)


@dataclass(frozen=True)
class CheckResult:
    label: str
    ok: bool
    messages: tuple[str, ...] = ()


def verify_track_integrity(book_root: Path) -> list[CheckResult]:
    """``TrackRecord.verify()`` do CDP e da sombra + cadeia da trilha de auditoria."""
    from ..workflow.track_record import TrackRecord

    root = Path(book_root)
    out: list[CheckResult] = []
    if not (root / TRACK_DIR).is_dir():
        return [CheckResult("Track record", True, ("Sem registros diários ainda.",))]
    for label, sub, event in (("Track record do CDP", TRACK_DIR, None),
                              ("Sombra só-quant", SHADOW_DIR, _shadow_event())):
        if not (root / sub).is_dir():
            continue
        try:
            tr = (TrackRecord(root / sub) if event is None
                  else TrackRecord(root / sub, audit_event=event))
            ok, msgs = tr.verify()
        except Exception as exc:  # noqa: BLE001
            ok, msgs = False, [f"{type(exc).__name__}: {exc}"]
        n = len(list((root / sub / "records").glob("*.json"))) if (root / sub).is_dir() else 0
        out.append(CheckResult(label, ok, tuple(msgs) or (f"{n} registro(s) íntegro(s).",)))
    audit = load_audit(root)
    if audit.exists:
        out.append(CheckResult("Trilha de auditoria", bool(audit.chain_ok),
                               (audit.error or audit.chain_message,)))
    return out


def verify_book_integrity(book_root: Path) -> list[CheckResult]:
    """Cadeia da trilha + ``Book.verify_integrity`` (artefatos × trilha)."""
    root = Path(book_root)
    if not root.is_dir():
        return [CheckResult("Livro", True, ("Livro ainda não existe (antes da inception).",))]
    out: list[CheckResult] = []
    audit = load_audit(root)
    out.append(CheckResult("Cadeia de auditoria", bool(audit.chain_ok) or not audit.exists,
                           (audit.error or audit.chain_message,)))
    from ..workflow.book import Book

    try:
        ok, msgs = Book(root).verify_integrity()
    except Exception as exc:  # noqa: BLE001
        ok, msgs = False, [f"{type(exc).__name__}: {exc}"]
    out.append(CheckResult("Livro × trilha (propostas, decisões, efetivações, ledger)", ok,
                           tuple(msgs) or ("Todos os artefatos conferem com a trilha.",)))
    return out


def verify_market_integrity(market_root: Path) -> CheckResult:
    root = Path(market_root)
    if not (root / "base").is_dir():
        return CheckResult("Base de mercado", True, ("Base de mercado ausente.",))
    try:
        from ..data.store import MarketStore

        ok, msgs = MarketStore(root).verify_chain()
    except Exception as exc:  # noqa: BLE001
        ok, msgs = False, [f"{type(exc).__name__}: {exc}"]
    return CheckResult("Base de mercado (base + incrementos)", ok,
                       tuple(msgs) or ("Base e incrementos íntegros.",))


# ==========================================================
# Relatórios e comentário do dia
# ==========================================================

@dataclass(frozen=True)
class ReportInfo:
    kind: str  # daily | weekly
    key: date
    folder: Path
    md: Path | None
    html: Path | None

    @property
    def label(self) -> str:
        kind = "Diário" if self.kind == "daily" else "Semanal"
        return f"{kind} — {fmt.date_br(self.key)}"


def list_reports(reports_root: Path, kind: str | None = None) -> list[ReportInfo]:
    """Relatórios publicados (mais recentes primeiro); pastas sem relatório são ignoradas."""
    root = Path(reports_root)
    out: list[ReportInfo] = []
    for k in ("daily", "weekly"):
        if kind is not None and k != kind:
            continue
        base = root / k
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            if not folder.is_dir():
                continue
            try:
                key = date.fromisoformat(folder.name)
            except ValueError:
                continue
            md = folder / f"{REPORT_STEM}.md"
            html = folder / f"{REPORT_STEM}.html"
            if not md.is_file() and not html.is_file():
                continue
            out.append(ReportInfo(k, key, folder, md if md.is_file() else None,
                                  html if html.is_file() else None))
    return sorted(out, key=lambda r: (r.key, r.kind), reverse=True)


def extract_section(markdown: str, title: str) -> str | None:
    """Conteúdo de ``## <title>`` (até o próximo ``## ``) num relatório Markdown."""
    lines = markdown.splitlines()
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f"## {title}" or stripped.startswith(f"## {title} ["):
            start = i + 1
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    text = "\n".join(body).strip()
    return text or None


@dataclass(frozen=True)
class Commentary:
    markdown: str
    source: str
    ai: bool
    mind: str | None = None
    issues: tuple[str, ...] = ()


def _commentary_meta(md: str) -> tuple[bool, str | None]:
    m = _MIND_RE.search(md)
    if m:
        return True, m.group(1)
    if "template determinístico" in md or "modo demo" in md:
        return False, None
    return "[IA]" in md, None


def commentary_for(reports_root: Path, record: DailyRecord, history: Sequence[DailyRecord],
                   cfg: FundConfig) -> Commentary | None:
    """Comentário do dia: seção do relatório publicado; senão ``comentario.json`` validado."""
    folder = Path(reports_root) / "daily" / record.date.isoformat()
    report = read_text(folder / f"{REPORT_STEM}.md")
    if report:
        section = extract_section(report, COMMENTARY_SECTION)
        if section:
            ai, mind = _commentary_meta(section)
            return Commentary(section, "relatório diário publicado", ai, mind)
    path = folder / "comentario.json"
    if not path.is_file():
        return None
    try:
        from ..research.commentary import build_daily_factbook, load_commentary_file

        fb = build_daily_factbook(record, list(history), cfg=cfg)
        md, issues = load_commentary_file(path, fb, record=record)
    except Exception as exc:  # noqa: BLE001
        return Commentary("", "comentario.json", False, None,
                          (f"Comentário não renderizado: {type(exc).__name__}",))
    ai, mind = _commentary_meta(md)
    return Commentary(md, "comentario.json validado (relatório ainda não publicado)", ai, mind,
                      tuple(issues))


# ==========================================================
# Atribuição e períodos
# ==========================================================

def period_bounds(kind: str, dates: Sequence[date],
                  custom: tuple[date, date] | None = None) -> tuple[date, date] | None:
    """Intervalo [início, fim] do período pedido, ancorado no último registro."""
    if not dates:
        return None
    first, last = min(dates), max(dates)
    if kind == "Dia":
        return last, last
    if kind == "Semana":
        return last - timedelta(days=last.weekday()), last
    if kind == "MTD":
        return date(last.year, last.month, 1), last
    if kind == "YTD":
        return date(last.year, 1, 1), last
    if kind == "Personalizado" and custom is not None:
        a, b = sorted(custom)
        return max(a, first), min(b, last)
    return first, last


def records_between(records: Sequence[DailyRecord], start: date, end: date
                    ) -> list[DailyRecord]:
    return [r for r in records if start <= r.date <= end]


def components_table(records: Sequence[DailyRecord]) -> pd.DataFrame:
    """P&L acumulado por componente (soma dos registros) e contribuição (soma das diárias)."""
    acc: dict[str, list[float]] = {}
    for r in records:
        nav0 = float(r.nav_start_usd)
        for k, v in r.pnl_components.items():
            fv = _finite(v)
            if fv is None:
                continue
            slot = acc.setdefault(k, [0.0, 0.0])
            slot[0] += fv
            slot[1] += fv / nav0
    order = [k for k in COMPONENT_ORDER if k in acc] + sorted(set(acc) - set(COMPONENT_ORDER))
    rows = [{"key": k, "name": fmt.COMPONENT_PT.get(k, k), "pnl_usd": acc[k][0],
             "contribution": acc[k][1]} for k in order]
    return pd.DataFrame(rows, columns=["key", "name", "pnl_usd", "contribution"])


def attribution_table(records: Sequence[DailyRecord], group: str) -> pd.DataFrame:
    """Soma do P&L e das contribuições diárias por linha de atribuição de um grupo."""
    acc: dict[str, list[float]] = {}
    for r in records:
        for a in r.attribution:
            if a.group != group:
                continue
            slot = acc.setdefault(a.name, [0.0, 0.0, 0.0])
            slot[0] += float(a.pnl_usd)
            slot[1] += float(a.contribution)
            slot[2] += 1
    rows = [{"name": k, "pnl_usd": v[0], "contribution": v[1], "days": int(v[2])}
            for k, v in acc.items()]
    df = pd.DataFrame(rows, columns=["name", "pnl_usd", "contribution", "days"])
    return df.sort_values(["pnl_usd", "name"], ascending=[False, True]).reset_index(drop=True)


def value_added_series(compare: pd.DataFrame | None, start: date, end: date) -> pd.DataFrame:
    """Crescimento acumulado do CDP e da sombra no período e o valor agregado (razão − 1)."""
    cols = ["cum_cdp", "cum_shadow", "value_added"]
    if compare is None or compare.empty:
        return pd.DataFrame(columns=cols)
    idx = compare.index
    sub = compare[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]
    if sub.empty:
        return pd.DataFrame(columns=cols)
    g_cdp = (1.0 + sub["ret_cdp"].astype(float)).cumprod()
    g_sh = (1.0 + sub["ret_shadow"].astype(float)).cumprod()
    return pd.DataFrame({"cum_cdp": g_cdp - 1.0, "cum_shadow": g_sh - 1.0,
                         "value_added": g_cdp / g_sh - 1.0}, index=sub.index)


# ==========================================================
# Posições
# ==========================================================

def issuer_meta(book: BookData) -> dict[str, dict[str, str]]:
    """Nome, país e setor por emissor a partir das propostas gravadas (a mais recente vence)."""
    meta: dict[str, dict[str, str]] = {}
    for w in book.weeks:
        for p in [*([w.shadow] if w.shadow else []), *w.proposals]:
            for t in p.positions:
                meta[t.issuer_id] = {"name": t.name, "country": t.country, "sector": t.sector}
    return meta


def line_meta(book: BookData) -> dict[str, dict[str, str]]:
    """Tipo de linha (LOCAL/ADR/US_LISTED) e moeda por ticker de execução."""
    meta: dict[str, dict[str, str]] = {}
    for w in book.weeks:
        for p in [*([w.shadow] if w.shadow else []), *w.proposals]:
            for t in p.positions:
                meta[t.execution_ticker] = {"line_type": t.line_type.value,
                                            "currency": t.currency}
    return meta


def positions_frame(record: DailyRecord, book: BookData,
                    proposal: Proposal | None) -> pd.DataFrame:
    """Posições de fim de dia do registro com metadados das propostas (sem recalcular nada)."""
    imeta = issuer_meta(book)
    lmeta = line_meta(book)
    targets = {t.issuer_id: t for t in (proposal.positions if proposal else [])}
    rows = []
    for p in record.positions:
        im = imeta.get(p.issuer_id, {})
        lm = lmeta.get(p.ticker, {})
        t = targets.get(p.issuer_id)
        rows.append({
            "issuer_id": p.issuer_id, "name": im.get("name", p.issuer_id),
            "ticker": p.ticker, "line_type": lm.get("line_type", fmt.NA),
            "currency": p.currency, "side": p.side.value,
            "country": im.get("country", fmt.NA), "sector": im.get("sector", fmt.NA),
            "weight": p.weight, "market_value_usd": p.market_value_usd,
            "day_pnl_usd": p.day_pnl_usd, "day_return_usd": p.day_return_usd,
            "repriced": p.repriced,
            "squeeze_bucket": t.squeeze_bucket if t is not None else "NA",
            "squeeze_score": t.squeeze_score if t is not None else None,
            "borrow_fee_annual": t.borrow_fee_annual if t is not None else None,
            "days_to_liquidate": t.days_to_liquidate if t is not None else None,
        })
    cols = ["issuer_id", "name", "ticker", "line_type", "currency", "side", "country", "sector",
            "weight", "market_value_usd", "day_pnl_usd", "day_return_usd", "repriced",
            "squeeze_bucket", "squeeze_score", "borrow_fee_annual", "days_to_liquidate"]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    df["abs_w"] = df["weight"].abs()
    return df.sort_values(["abs_w", "issuer_id"], ascending=[False, True]).drop(
        columns="abs_w").reset_index(drop=True)


def position_history(records: Sequence[DailyRecord], issuer_id: str) -> pd.DataFrame:
    rows = [{"date": r.date, "ticker": p.ticker, "side": p.side.value, "weight": p.weight,
             "market_value_usd": p.market_value_usd, "day_pnl_usd": p.day_pnl_usd,
             "day_return_usd": p.day_return_usd, "repriced": p.repriced}
            for r in records for p in r.positions if p.issuer_id == issuer_id]
    cols = ["date", "ticker", "side", "weight", "market_value_usd", "day_pnl_usd",
            "day_return_usd", "repriced"]
    return pd.DataFrame(rows, columns=cols)


def held_issuers(records: Sequence[DailyRecord]) -> list[str]:
    return sorted({p.issuer_id for r in records for p in r.positions})


# ==========================================================
# Decisões semanais
# ==========================================================

def _issuer_weights(p: Proposal | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in (p.positions if p is not None else []):
        out[t.issuer_id] = out.get(t.issuer_id, 0.0) + float(t.weight)
    return out


def portfolio_changes(new: Proposal, old: Proposal | None,
                      names: dict[str, dict[str, str]] | None = None,
                      threshold: float = RESIZE_THRESHOLD) -> pd.DataFrame:
    """Entradas, saídas, inversões e redimensionamentos (|Δw| ≥ ``threshold``) vs. a semana
    anterior, a partir dos pesos-alvo gravados."""
    a, b = _issuer_weights(old), _issuer_weights(new)
    names = names or {}
    rows = []
    for iid in sorted(set(a) | set(b)):
        wa, wb = a.get(iid, 0.0), b.get(iid, 0.0)
        delta = wb - wa
        if iid not in a:
            kind = "Entrada"
        elif iid not in b:
            kind = "Saída"
        elif wa * wb < 0:
            kind = "Inversão de lado"
        elif abs(delta) >= threshold:
            kind = "Aumento" if abs(wb) > abs(wa) else "Redução"
        else:
            continue
        rows.append({"issuer_id": iid, "name": names.get(iid, {}).get("name", iid),
                     "change": kind, "w_old": wa if iid in a else None,
                     "w_new": wb if iid in b else None, "delta": delta})
    order = {"Entrada": 0, "Saída": 1, "Inversão de lado": 2, "Aumento": 3, "Redução": 4}
    df = pd.DataFrame(rows, columns=["issuer_id", "name", "change", "w_old", "w_new", "delta"])
    if df.empty:
        return df
    df["_o"] = df["change"].map(order)
    df["_a"] = -df["delta"].abs()
    return df.sort_values(["_o", "_a", "issuer_id"]).drop(columns=["_o", "_a"]).reset_index(
        drop=True)


def compliance_frame(p: Proposal) -> pd.DataFrame:
    rows = [{"Severidade": c.severity.value, "Verificação": c.name, "ID": c.check_id,
             "Status": "OK" if c.passed else "FALHA", "Valor": c.value, "Limite": c.limit,
             "Detalhes": c.details}
            for c in p.compliance]
    df = pd.DataFrame(rows, columns=["Severidade", "Verificação", "ID", "Status", "Valor",
                                     "Limite", "Detalhes"])
    if df.empty:
        return df
    df["_s"] = df["Severidade"].map(fmt.SEVERITY_ORDER).fillna(9)
    df["_p"] = (df["Status"] == "OK").astype(int)
    return df.sort_values(["_p", "_s", "ID"]).drop(columns=["_s", "_p"]).reset_index(drop=True)


def proposal_comparison(cdp: Proposal, shadow: Proposal) -> pd.DataFrame:
    """Indicadores gravados da carteira do CDP vs. sombra só-quant (mesma semana)."""
    def row(label: str, a: str, b: str) -> dict[str, str]:
        return {"Indicador": label, "CDP": a, "Sombra só-quant": b}

    ra, rb = cdp.risk, shadow.risk
    oa, ob = cdp.optimizer, shadow.optimizer
    wa, wb = _issuer_weights(cdp), _issuer_weights(shadow)
    common = set(wa) & set(wb)
    rows = [
        row("Vol ex-ante", fmt.pct(ra.ex_ante_vol), fmt.pct(rb.ex_ante_vol)),
        row("Vol fatorial", fmt.pct(ra.factor_vol), fmt.pct(rb.factor_vol)),
        row("Vol específica", fmt.pct(ra.specific_vol), fmt.pct(rb.specific_vol)),
        row("Beta previsto", fmt.num(ra.beta, 3, True), fmt.num(rb.beta, 3, True)),
        row("Gross", fmt.pct(ra.gross), fmt.pct(rb.gross)),
        row("Net", fmt.pct(ra.net, signed=True), fmt.pct(rb.net, signed=True)),
        row("Nº longs / shorts", f"{ra.n_long} / {ra.n_short}", f"{rb.n_long} / {rb.n_short}"),
        row("VaR 1d (99%)", fmt.pct(ra.var_1d_99), fmt.pct(rb.var_1d_99)),
        row("Alpha esperado (a.a.)", fmt.pct(oa.expected_alpha_annual),
            fmt.pct(ob.expected_alpha_annual)),
        row("Custo esperado (a.a.)", fmt.pct(oa.expected_cost_annual),
            fmt.pct(ob.expected_cost_annual)),
        row("Falhas HARD / SOFT", f"{len(cdp.hard_failures)} / {len(cdp.soft_failures)}",
            f"{len(shadow.hard_failures)} / {len(shadow.soft_failures)}"),
        row("Emissores em comum", str(len(common)), str(len(common))),
        row("Emissores exclusivos", str(len(set(wa) - set(wb))), str(len(set(wb) - set(wa)))),
    ]
    return pd.DataFrame(rows, columns=["Indicador", "CDP", "Sombra só-quant"])


def trades_frame(p: Proposal) -> pd.DataFrame:
    rows = [{"Emissor": t.issuer_id, "Ticker": t.ticker, "Ação": t.action.value,
             "Ações": t.shares, "Nocional": fmt.usd_mm(t.notional_usd, 2, True),
             "Δ peso": fmt.pct(t.weight_change, 2, True), "% ADTV": fmt.pct(t.pct_adtv),
             "Custo est.": fmt.num(t.est_cost_bps, 1) + " bps" if fmt.is_num(t.est_cost_bps)
             else fmt.NA,
             "Dias": fmt.days(t.est_days), "Moeda": t.currency}
            for t in sorted(p.trades, key=lambda t: (-abs(t.notional_usd), t.issuer_id))]
    return pd.DataFrame(rows, columns=["Emissor", "Ticker", "Ação", "Ações", "Nocional",
                                       "Δ peso", "% ADTV", "Custo est.", "Dias", "Moeda"])


def hedges_frame(p: Proposal) -> pd.DataFrame:
    rows = [{"Moeda": h.currency, "Exposição": fmt.usd_mm(h.exposure_usd, 2, True),
             "Hedge": fmt.usd_mm(h.hedge_notional_usd, 2, True), "Instrumento": h.instrument,
             "Racional [Calculado]": h.rationale} for h in p.fx_hedges]
    return pd.DataFrame(rows, columns=["Moeda", "Exposição", "Hedge", "Instrumento",
                                       "Racional [Calculado]"])


# ==========================================================
# Risco
# ==========================================================

def exposures_frame(lines: Sequence[ExposureLine]) -> pd.DataFrame:
    rows = [{"group": e.group, "name": e.name, "long": e.long, "short": e.short, "net": e.net,
             "gross": e.gross, "limit": e.limit} for e in lines]
    return pd.DataFrame(rows, columns=["group", "name", "long", "short", "net", "gross",
                                       "limit"])


def stress_frame(stress: dict[str, float]) -> pd.DataFrame:
    rows = [{"Cenário": k, "value": _finite(v)} for k, v in stress.items()]
    df = pd.DataFrame(rows, columns=["Cenário", "value"])
    if df.empty:
        return df
    df["_na"] = df["value"].isna()
    return df.sort_values(["_na", "value", "Cenário"]).drop(columns="_na").reset_index(drop=True)


def liquidity_buckets(positions: Sequence[PositionTarget]) -> pd.DataFrame:
    """Fatia do gross por faixa de dias para liquidar (dias gravados na proposta)."""
    total = sum(abs(float(p.weight)) for p in positions)
    acc: dict[str, list[float]] = {label: [0.0, 0] for _, label in LIQUIDITY_BUCKETS}
    acc["n/d"] = [0.0, 0]
    for p in positions:
        d = _finite(p.days_to_liquidate)
        label = "n/d" if d is None else next(lb for ub, lb in LIQUIDITY_BUCKETS if d <= ub)
        acc[label][0] += abs(float(p.weight))
        acc[label][1] += 1
    rows = [{"Faixa": k, "gross_share": (v[0] / total) if total > 0 else None, "n": int(v[1])}
            for k, v in acc.items() if v[1] > 0 or k != "n/d"]
    return pd.DataFrame(rows, columns=["Faixa", "gross_share", "n"])


def squeeze_frame(proposal: Proposal | None, record: DailyRecord | None) -> pd.DataFrame:
    """Shorts vigentes com balde/escore de squeeze e aluguel gravados na proposta."""
    targets = {t.issuer_id: t for t in (proposal.positions if proposal else [])}
    shorts: list[tuple[str, str, float | None]] = []
    if record is not None:
        shorts = [(p.issuer_id, p.ticker, p.weight) for p in record.positions
                  if p.side.value == "SHORT"]
    else:
        shorts = [(t.issuer_id, t.execution_ticker, t.weight) for t in targets.values()
                  if t.side.value == "SHORT"]
    rows = []
    for iid, ticker, w in shorts:
        t = targets.get(iid)
        rows.append({"issuer_id": iid, "name": t.name if t else iid, "ticker": ticker,
                     "weight": w, "bucket": t.squeeze_bucket if t else "NA",
                     "score": t.squeeze_score if t else None,
                     "borrow_fee": t.borrow_fee_annual if t else None,
                     "days_to_liquidate": t.days_to_liquidate if t else None})
    df = pd.DataFrame(rows, columns=["issuer_id", "name", "ticker", "weight", "bucket", "score",
                                     "borrow_fee", "days_to_liquidate"])
    if df.empty:
        return df
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NA": 3}
    df["_o"] = df["bucket"].map(order).fillna(4)
    df["_s"] = -df["score"].astype(float).fillna(-1.0)
    return df.sort_values(["_o", "_s", "issuer_id"]).drop(columns=["_o", "_s"]).reset_index(
        drop=True)


# ==========================================================
# Pesquisa
# ==========================================================

def llm_stats(calls: Sequence[LLMCallRecord]) -> dict[str, Any]:
    """Contagens do ledger de chamadas de IA (procedência; nenhum número de carteira)."""
    if not calls:
        return {"n_calls": 0}
    lat = [float(c.latency_ms) for c in calls if fmt.is_num(c.latency_ms)]
    tin = [int(c.input_tokens) for c in calls if c.input_tokens is not None]
    tout = [int(c.output_tokens) for c in calls if c.output_tokens is not None]
    cost = [float(c.cost_usd) for c in calls if fmt.is_num(c.cost_usd)]
    return {
        "n_calls": len(calls),
        "parse_ok": sum(1 for c in calls if c.parse_ok),
        "failed": sum(1 for c in calls if not c.parse_ok),
        "with_issues": sum(1 for c in calls if c.validation_issues),
        "by_task": dict(sorted(Counter(c.task for c in calls).items())),
        "providers": sorted({c.provider for c in calls}),
        "models": sorted({c.model for c in calls if c.model}),
        "prompt_versions": sorted({c.prompt_version for c in calls}),
        "input_tokens": sum(tin) if tin else None,
        "output_tokens": sum(tout) if tout else None,
        "cost_usd": sum(cost) if cost else None,
        "latency_median_ms": statistics.median(lat) if lat else None,
    }


def is_abstention_note(note: Any) -> bool:
    thesis = str(getattr(note, "thesis", "") or "")
    return thesis.startswith("Abstenção") or (
        getattr(note, "stance", None) == 0 and getattr(note, "confidence", None) == 0)


def governance_flags(week: WeekData | None, kill: KillSwitchState) -> list[tuple[str, str]]:
    """(severidade, texto) dos sinais de governança da semana: kill switch, IA desativada,
    abstenções, apontamentos do verificador e caminho de fallback."""
    flags: list[tuple[str, str]] = []
    if kill.active:
        flags.append(("error", f"KILL SWITCH LIGADO: {kill.reason or 'motivo não informado'}"))
    if week is None:
        return flags
    pack = week.research
    if pack is not None:
        for m in pack.macro:
            if m.scope.upper() in GOVERNANCE_SCOPES:
                sev = "error" if "DESATIVADA" in m.regime.upper() else "warning"
                flags.append((sev, f"Governança da IA: {m.regime} — {m.summary}"))
                flags += [("warning", f"Evento: {r}") for r in m.risks]
        n_abst = sum(1 for n in pack.notes if is_abstention_note(n))
        n_macro_abst = sum(1 for m in pack.macro if m.regime.startswith("indeterminado"))
        if n_abst or n_macro_abst:
            flags.append(("warning", f"Abstenções: {n_abst} nota(s) por emissor e {n_macro_abst} "
                                     "nota(s) macro (saída indisponível ou rejeitada)."))
    if week.pm_output is not None and getattr(week.pm_output, "abstain", False):
        flags.append(("warning", "Agente PM em abstenção: a carteira seguiu o quant."))
    issues = (week.attempts or {}).get("input_issues") or []
    for i in issues[:20]:
        flags.append(("warning", f"Verificador: {i}"))
    path = week.path_taken
    if path and path != "cdp":
        flags.append(("warning", f"Caminho de fallback: {fmt.PATH_PT.get(path, path)}."))
    calls_failed = sum(1 for c in week.llm_calls if not c.parse_ok)
    if calls_failed:
        flags.append(("warning", f"{calls_failed} chamada(s) de IA falharam ou foram "
                                 "rejeitadas pelo schema."))
    return flags


def views_table(week: WeekData) -> pd.DataFrame:
    """Visões da IA (pacote de pesquisa) e do PM (decisão da mente) lado a lado por emissor."""
    rows: dict[str, dict[str, Any]] = {}
    pack = week.research
    for v in (pack.views if pack else []):
        r = rows.setdefault(v.issuer_id, {"issuer_id": v.issuer_id})
        flags = [x for x, on in (("sem short", v.no_short), ("sem long", v.no_long)) if on]
        if v.max_abs_weight is not None:
            flags.append(f"teto {fmt.pct(v.max_abs_weight)}")
        r.update({"ai_score": v.score, "ai_conf": v.confidence,
                  "ai_limits": ", ".join(flags) or "—",
                  "ai_rationale": render_facts(v.rationale, week.facts)})
    pm = week.pm_output
    for v in (getattr(pm, "views", None) or []):
        r = rows.setdefault(v.issuer_id, {"issuer_id": v.issuer_id})
        r.update({"pm_stance": v.stance, "pm_conviction": v.conviction,
                  "pm_horizon": v.horizon_weeks,
                  "pm_rationale": render_facts(v.rationale, week.facts)})
    for x in (getattr(pm, "exclusions", None) or []):
        r = rows.setdefault(x.issuer_id, {"issuer_id": x.issuer_id})
        lim = [n for n, on in (("sem long", x.no_long), ("sem short", x.no_short)) if on]
        r["pm_exclusion"] = ", ".join(lim) + ": " + render_facts(x.reason, week.facts)
    cols = ["issuer_id", "ai_score", "ai_conf", "ai_limits", "ai_rationale", "pm_stance",
            "pm_conviction", "pm_horizon", "pm_exclusion", "pm_rationale"]
    df = pd.DataFrame(list(rows.values()), columns=cols)
    return df.sort_values("issuer_id").reset_index(drop=True) if not df.empty else df


def safe_url(url: str | None) -> str | None:
    """URL http(s) sem espaços/aspas (para link); caso contrário ``None`` (texto puro)."""
    if not url:
        return None
    u = str(url).strip()
    if not re.match(r"^https?://[^\s\"'<>()\\]+$", u):
        return None
    return u


# ==========================================================
# Agenda e contexto de mercado
# ==========================================================

@dataclass(frozen=True)
class Event:
    label: str
    when: datetime
    note: str = ""


def _at(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=tz)


def next_events(now: datetime, cfg: FundConfig, decided_weeks: set[date] | None = None
                ) -> list[Event]:
    """Próxima decisão semanal (prazo do mandato) e próximo fechamento diário (horário local)."""
    from ..calendar import first_session_of_week, is_session

    tz = ZoneInfo(cfg.fund.timezone)
    local = now.astimezone(tz)
    today = local.date()
    decided = decided_weeks or set()
    events: list[Event] = []

    monday = today - timedelta(days=today.weekday())
    for k in range(0, 8):
        first = first_session_of_week(monday + timedelta(weeks=k))
        if first is None or first < today or first in decided:
            continue
        deadline = _at(first, cfg.fund.decision_deadline_local, tz)
        if deadline <= local:
            continue
        events.append(Event("Decisão semanal (autônoma)", deadline,
                            f"pesquisa a partir de {cfg.fund.weekly_research_start_local}; "
                            "execução no fechamento (MOC)"))
        break

    for k in range(0, 15):
        d = today + timedelta(days=k)
        if not any(is_session(d, ex) for ex in ("BVMF", "XNYS", "XMEX")):
            continue
        run = _at(d, cfg.fund.daily_close_run_local, tz)
        if run <= local:
            continue
        events.append(Event("Fechamento diário", run,
                            "marcação, risco, atribuição, comentário e relatório"))
        break
    return sorted(events, key=lambda e: e.when)


@dataclass
class MarketContext:
    available: bool = False
    last_date: date | None = None
    n_increments: int = 0
    facts: list[tuple[str, str]] = field(default_factory=list)
    is_synthetic: bool = False
    error: str | None = None


def load_market_context(market_root: Path) -> MarketContext:
    """Último pregão da base e variações do dia de benchmarks/câmbio (código do comentário)."""
    root = Path(market_root)
    if not (root / "base").is_dir():
        return MarketContext()
    try:
        from ..data.store import MarketStore
        from ..research.commentary import build_market_day_facts

        store = MarketStore(root)
        md = store.load(verify=False)
        facts = build_market_day_facts(md.benchmarks, md.fx, md.as_of)
        n_inc = len(store.increments())
    except Exception as exc:  # noqa: BLE001
        return MarketContext(error=f"{type(exc).__name__}: {str(exc)[:300]}")
    rows = [(f.name, f.formatted) for f in facts.values()]
    return MarketContext(available=True, last_date=md.as_of, n_increments=n_inc, facts=rows,
                         is_synthetic=bool(md.is_synthetic))


# ==========================================================
# Invariantes
# ==========================================================

def agents_invariants(path: Path) -> tuple[str | None, str]:
    """Seção do CDP no AGENTS.md (cabeçalho com "CDP") ou ``None`` com a origem consultada."""
    text = read_text(Path(path))
    if not text:
        return None, f"{Path(path).as_posix()} não encontrado"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if not m or "CDP" not in m.group(2):
            continue
        level = len(m.group(1))
        body: list[str] = []
        for nxt in lines[i + 1:]:
            m2 = re.match(r"^(#{1,6})\s+", nxt)
            if m2 and len(m2.group(1)) <= level:
                break
            body.append(nxt)
        section = "\n".join(body).strip()
        if section:
            return section, f"{Path(path).as_posix()} — {m.group(2).strip()}"
    return None, f"{Path(path).as_posix()} (sem seção do CDP)"
