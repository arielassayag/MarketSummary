"""Leitura defensiva dos artefatos do CDP para o app (sem Streamlit; testável).

Regras:

- Somente leitura: nada aqui grava arquivos, exceto :func:`set_kill_switch` (única ação de escrita
  do app: ``book/KILL_SWITCH`` com ``{reason, created_at, by}`` e o evento KILL_SWITCH_ON/OFF na
  trilha encadeada; recusa se o estado mudou desde que o operador abriu o formulário).
- Integridade verificada já na carga (``TrackRecord.verify`` e ``Book.verify_integrity``): uma
  adulteração aparece em todas as páginas, não só ao clicar em "Verificar".
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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
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
_SKIP_DIRS = frozenset({"raw", "__pycache__", ".git"})
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
    "Sem look-ahead: a carteira da semana é decidida antes do fechamento do dia de montagem, "
    "com dados até o momento da análise, e executada no leilão de fechamento (MOC) desse dia.",
    "Dados ausentes nunca viram zero; dados simulados carregam sempre 'DADOS SIMULADOS'.",
    "Notícias são conteúdo não confiável: instruções embutidas nunca alteram o estado do fundo.",
    "KILL SWITCH de emergência: com o arquivo book/KILL_SWITCH presente, só operações que reduzem "
    "risco são aceitas; ligar/desligar é auditado.",
)


# ==========================================================
# Utilidades
# ==========================================================

def fingerprint(*paths: Path | str, skip_dirs: Iterable[str] = _SKIP_DIRS,
                content: bool = False) -> str:
    """Impressão digital (caminho relativo, tamanho, mtime) de arquivos/árvores para o cache.

    Muda sempre que um arquivo é criado, removido ou alterado; ausente ⇒ marcador estável.
    ``content=True`` inclui o SHA-256 do conteúdo dos arquivos passados diretamente (para
    arquivos pequenos e críticos como a trilha de auditoria: uma edição que preserve tamanho e
    mtime também invalida o cache).
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
                if content:
                    h.update(hashlib.sha256(p.read_bytes()).hexdigest().encode())
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


def _attempt[T](issues: list[str], label: str, fn: Callable[[], T], default: T) -> T:
    """Executa ``fn``; erro vira apontamento legível (o app nunca quebra por um artefato)."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura vira apontamento
        issues.append(f"{label}: {type(exc).__name__}: {str(exc)[:300]}")
        return default


def relative_to(path: Path, root: Path) -> str:
    """Caminho relativo à raiz configurada (para exibição); fora dela ⇒ caminho completo."""
    try:
        return f"{Path(root).name}/{Path(path).relative_to(Path(root)).as_posix()}"
    except ValueError:
        return Path(path).as_posix()


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
    """Tipo de evento de auditoria da série-sombra (``DAILY_RECORD_SHADOW``)."""
    from ..workflow import track_record

    return str(getattr(track_record, "SHADOW_RECORD_EVENT", SHADOW_RECORD_EVENT_FALLBACK))


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
    integrity: list[CheckResult] = field(default_factory=list)
    unreadable: list[date] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.records

    def unreadable_between(self, start: date, end: date) -> list[date]:
        """Pregões com registro ilegível no intervalo (somas/compostos ficariam incompletos)."""
        return [d for d in self.unreadable if start <= d <= end]

    @property
    def integrity_failures(self) -> list[CheckResult]:
        """Verificações reprovadas na carga (registro adulterado, removido ou ilegível)."""
        return [r for r in self.integrity if not r.ok]

    @property
    def latest(self) -> DailyRecord | None:
        return self.records[-1] if self.records else None

    def history_until(self, record: DailyRecord) -> list[DailyRecord]:
        """Registros estritamente anteriores a ``record`` (sem look-ahead)."""
        return [r for r in self.records if r.date < record.date]

    @property
    def dates(self) -> list[date]:
        return [r.date for r in self.records]


def _load_records(tr: Any, issues: list[str], label: str
                  ) -> tuple[list[DailyRecord], list[date]]:
    """Registros um a um: um JSON ilegível vira apontamento (e data ilegível) sem esconder os
    demais."""
    out: list[DailyRecord] = []
    bad: list[date] = []
    for d in _attempt(issues, f"{label} (datas)", tr.dates, []):
        rec = _attempt(issues, f"{label} {d.isoformat()} ilegível", lambda d=d: tr.get(d), None)
        if rec is None:
            bad.append(d)
        else:
            out.append(rec)
    return out, bad


def load_track(book_root: Path, cfg: FundConfig) -> TrackData:
    """Track record do CDP e da sombra, com a verificação de integridade feita já na carga.

    A verificação (``TrackRecord.verify`` + cadeia da trilha) roda sempre que o livro existe —
    inclusive sem a pasta do track record, para acusar registros removidos que a trilha ainda
    lista. Nenhuma pasta é criada.
    """
    from ..workflow.track_record import TrackRecord, compare_tracks

    root = Path(book_root)
    td = TrackData()
    if not root.is_dir():
        return td
    td.integrity = _attempt(td.issues, "Verificação de integridade",
                            lambda: verify_track_integrity(root), [])
    main_dir = root / TRACK_DIR
    if not main_dir.is_dir():
        return td
    td.exists = True
    issues = td.issues
    main = TrackRecord(main_dir)
    td.records, td.unreadable = _load_records(main, issues, "Track record")
    td.frame = _attempt(issues, "Track record (CSV)", main.frame, None)
    td.stats = _attempt(issues, "Track record (estatísticas)", lambda: main.stats(cfg), {})
    td.monthly = _attempt(issues, "Track record (grade mensal)", main.monthly_returns_table, None)
    if main.csv_path.is_file():
        td.csv_bytes = _attempt(issues, "Track record (download)", main.csv_path.read_bytes, None)
    shadow_dir = root / SHADOW_DIR
    if shadow_dir.is_dir():
        shadow = TrackRecord(shadow_dir, audit_event=_shadow_event())
        td.shadow_records, _ = _load_records(shadow, issues, "Sombra só-quant")
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


def period_summary(record: DailyRecord, history: Sequence[DailyRecord],
                   unreadable: Sequence[date] = ()) -> dict[str, Any]:
    """MTD/YTD/ITD pelo mesmo código do comentário/relatório diário.

    Um pregão com registro ilegível dentro da janela torna o período ``None`` (n/d): compor só
    os dias legíveis trataria o dia ausente como retorno zero.
    """
    from ..research.commentary import period_returns

    out = dict(period_returns(record, list(history)))
    d = record.date
    gaps = [g for g in unreadable if g <= d]
    if gaps:
        out["itd"] = None
        if any(g.year == d.year for g in gaps):
            out["ytd"] = None
        if any((g.year, g.month) == (d.year, d.month) for g in gaps):
            out["mtd"] = None
    return out


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
        """Proposta vigente da semana: a efetivada; senão a mais recente com decisão APPROVE;
        senão a versão mais recente."""
        if self.booked is not None:
            for p in self.proposals:
                if p.proposal_id == self.booked.proposal_id:
                    return p
        approved = [p for p in self.proposals
                    if (d := self.decisions.get(p.version)) is not None
                    and d.proposal_id == p.proposal_id
                    and getattr(d.decision, "value", d.decision) == "APPROVE"]
        if approved:
            return approved[-1]
        return self.proposals[-1] if self.proposals else None

    @property
    def decision(self) -> Decision | None:
        """Decisão da proposta exibida (nunca a de outra versão)."""
        p = self.proposal
        if p is None:
            return None
        d = self.decisions.get(p.version)
        return d if d is not None and d.proposal_id == p.proposal_id else None

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
    integrity: list[CheckResult] = field(default_factory=list)

    @property
    def integrity_failures(self) -> list[CheckResult]:
        return [r for r in self.integrity if not r.ok]

    def week(self, d: date) -> WeekData | None:
        return next((w for w in self.weeks if w.week == d), None)

    def previous(self, d: date) -> WeekData | None:
        """Carteira anterior a ``d``: a última semana EFETIVADA (a que estava em carteira);
        sem efetivação anterior, a última semana com proposta."""
        before = [w for w in self.weeks if w.week < d and w.proposal is not None]
        booked = [w for w in before if w.booked is not None]
        if booked:
            return booked[-1]
        return before[-1] if before else None

    @property
    def latest(self) -> WeekData | None:
        with_prop = [w for w in self.weeks if w.proposal is not None]
        return with_prop[-1] if with_prop else (self.weeks[-1] if self.weeks else None)

    @property
    def decided_weeks(self) -> set[date]:
        return {w.week for w in self.weeks if w.decisions}

    def live_week(self, record: DailyRecord | None) -> WeekData | None:
        """Semana da carteira em carteira no registro (sem registro: a mais recente).

        Nunca devolve uma semana posterior ao registro (sem look-ahead): se a semana citada no
        registro não estiver no livro, devolve ``None`` em vez de uma decisão mais nova.
        """
        if record is None:
            return self.latest
        if record.live_book_week is not None:
            return self.week(record.live_book_week)
        before = [w for w in self.weeks if w.week <= record.date and w.proposal is not None]
        return before[-1] if before else None

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
    bd.integrity = _attempt(bd.issues, "Verificação de integridade do livro",
                            lambda: verify_book_integrity(root), [])
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


def kill_switch_payload(turn_on: bool, reason: str, by: str, now: datetime) -> dict[str, Any]:
    """Conteúdo de ``book/KILL_SWITCH`` e do evento de auditoria.

    Campos do app (``reason``, ``created_at``, ``by``) mais ``on`` e ``at``, os mesmos que
    ``workflow.runtime.Runtime.set_kill_switch`` grava (CLI e app ficam legíveis um pelo outro).
    """
    ts = now.astimezone(UTC).isoformat()
    return {"on": bool(turn_on), "reason": reason.strip(), "by": by.strip(), "created_at": ts,
            "at": ts}


def set_kill_switch(paths: AppPaths, cfg: FundConfig, turn_on: bool, reason: str,
                    by: str, *, expect_active: bool | None = None,
                    now: datetime | None = None) -> KillSwitchState:
    """Liga/desliga ``book/KILL_SWITCH`` e anexa ``KILL_SWITCH_ON``/``OFF`` à trilha encadeada.

    ``expect_active`` é o estado que o operador viu ao preencher o formulário: se o arquivo
    mudou nesse meio-tempo (outro operador ou a CLI), nada é gravado e ``RuntimeError`` é
    levantado — a intenção do operador nunca é invertida. Ligar grava o arquivo antes do evento
    (falha segura: o fundo fica protegido mesmo se a trilha falhar); desligar grava o evento
    antes de remover o arquivo (nunca há desligamento sem auditoria).
    """
    del cfg  # o mandato não altera a ação; mantido na assinatura por compatibilidade
    book = Path(paths.book)
    path = book / KILL_SWITCH_FILE
    active = path.exists()
    if expect_active is not None and active != expect_active:
        raise RuntimeError("O estado do kill switch mudou desde que a página foi aberta "
                           f"(agora {'LIGADO' if active else 'DESLIGADO'}); nada foi gravado.")
    if turn_on == active:
        raise RuntimeError(f"O kill switch já está {'LIGADO' if active else 'DESLIGADO'}.")
    payload = kill_switch_payload(turn_on, reason, by, now or datetime.now(UTC))
    book.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(book / AUDIT_FILE)
    summary = (f"Kill switch {'ligado' if turn_on else 'desligado'} pelo app: "
               f"{payload['reason']}")
    event = "KILL_SWITCH_ON" if turn_on else "KILL_SWITCH_OFF"
    if turn_on:
        tmp = book / f".tmp_{KILL_SWITCH_FILE}"
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, path)
        audit.append(event, payload["by"], payload, summary=summary,
                     ts=datetime.fromisoformat(payload["created_at"]))
    else:
        audit.append(event, payload["by"], payload, summary=summary,
                     ts=datetime.fromisoformat(payload["created_at"]))
        path.unlink(missing_ok=True)
    return kill_switch_state(book)


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
    if not root.is_dir():
        # Livro inexistente: nada a verificar (e nada é criado ao apenas ler).
        return [CheckResult("Track record", True, ("Sem registros diários ainda.",))]
    for label, sub, event in (("Track record do CDP", TRACK_DIR, None),
                              ("Sombra só-quant", SHADOW_DIR, _shadow_event())):
        # A pasta ausente também é verificada: eventos na trilha sem registro ⇒ registros
        # removidos (a verificação nunca cria pastas: só lê).
        try:
            tr = (TrackRecord(root / sub) if event is None
                  else TrackRecord(root / sub, audit_event=event))
            ok, msgs = tr.verify()
            n = len(tr.dates())
        except Exception as exc:  # noqa: BLE001
            ok, msgs, n = False, [f"{type(exc).__name__}: {exc}"], 0
        if ok and not (root / sub).is_dir() and sub == SHADOW_DIR:
            continue  # sem série-sombra e sem eventos dela na trilha
        default = f"{n} registro(s) íntegro(s)." if n else "Sem registros diários ainda."
        out.append(CheckResult(label, ok, tuple(msgs) or (default,)))
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
    try:
        real_root = root.resolve()
    except OSError:
        return out

    def inside(p: Path) -> bool:
        """Arquivo regular dentro da raiz (link simbólico para fora ⇒ ignorado)."""
        try:
            return p.is_file() and p.resolve().is_relative_to(real_root)
        except OSError:
            return False

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
            md_ok, html_ok = inside(md), inside(html)
            if not md_ok and not html_ok:
                continue
            out.append(ReportInfo(k, key, folder, md if md_ok else None,
                                  html if html_ok else None))
    return sorted(out, key=lambda r: (r.key, r.kind), reverse=True)


_ACTIVE_HTML = (
    (re.compile(r"<\s*script\b", re.I), "elemento <script>"),
    (re.compile(r"<\s*(iframe|frame|object|embed|applet|form|base|link|portal)\b", re.I),
     "elemento ativo/externo (iframe, object, embed, form, base, link)"),
    (re.compile(r"<\s*meta\b[^>]*http-equiv", re.I), "meta http-equiv"),
    (re.compile(r"\son[a-z]+\s*=", re.I), "atributo de evento (on…=)"),
    (re.compile(r"javascript\s*:", re.I), "URL javascript:"),
    (re.compile(r"(src|href|action|srcset|xlink:href)\s*=\s*[\"']?\s*(https?:)?//", re.I),
     "recurso externo (src/href remoto)"),
    (re.compile(r"url\(\s*[\"']?\s*(https?:)?//", re.I), "CSS url() remoto"),
    (re.compile(r"@import", re.I), "CSS @import"),
)


def html_active_content(text: str) -> list[str]:
    """Conteúdo ativo ou externo num relatório HTML (lista vazia ⇒ seguro para exibir).

    O relatório gerado pelo código é autocontido e sem scripts; um arquivo alterado fora do
    pipeline poderia executar código no navegador do operador (o iframe do Streamlit compartilha
    a origem do app). Nesses casos o app não renderiza o HTML.
    """
    return [label for rx, label in _ACTIVE_HTML if rx.search(text or "")]


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
    """(texto de IA?, mente) pela linha de procedência — a ÚLTIMA ocorrência, escrita pelo
    código após o texto da mente (um parágrafo que imite a procedência não troca a mente)."""
    found = _MIND_RE.findall(md)
    if found:
        return True, found[-1]
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
    """P&L acumulado por componente (soma dos registros) e contribuição (soma das diárias).

    ``days`` conta os pregões em que o componente foi registrado: cobertura parcial
    (``days`` < pregões do período) fica visível em vez de somar ausente como zero.
    """
    acc: dict[str, list[float]] = {}
    for r in records:
        nav0 = float(r.nav_start_usd)
        for k, v in r.pnl_components.items():
            fv = _finite(v)
            if fv is None:
                continue
            slot = acc.setdefault(k, [0.0, 0.0, 0.0])
            slot[0] += fv
            slot[1] += fv / nav0
            slot[2] += 1
    order = [k for k in COMPONENT_ORDER if k in acc] + sorted(set(acc) - set(COMPONENT_ORDER))
    rows = [{"key": k, "name": fmt.COMPONENT_PT.get(k, k), "pnl_usd": acc[k][0],
             "contribution": acc[k][1], "days": int(acc[k][2])} for k in order]
    return pd.DataFrame(rows, columns=["key", "name", "pnl_usd", "contribution", "days"])


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
    # skipna=False: um dia sem retorno interrompe a série (NaN daí em diante), nunca vira 0%.
    g_cdp = (1.0 + sub["ret_cdp"].astype(float)).cumprod(skipna=False)
    g_sh = (1.0 + sub["ret_shadow"].astype(float)).cumprod(skipna=False)
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


@dataclass(frozen=True)
class SideLiquidity:
    """Máximo de dias para liquidar de um lado vs. o teto do mandato para esse lado."""

    side: str
    max_days: float | None
    limit: float
    n: int
    n_missing: int

    @property
    def status(self) -> fmt.Status:
        tag = "L" if self.side == "LONG" else "S"
        if self.n == 0:
            return fmt.Status(f"{tag}: sem posições", "gray")
        if self.n_missing:
            return fmt.Status(f"{tag}: {self.n_missing} sem ADTV (n/d)", "orange")
        st = fmt.max_status(self.max_days, self.limit, fmt.days)
        return fmt.Status(f"{tag}: {st.label}", st.color)


def worst_liquidity_status(by_side: dict[str, SideLiquidity]) -> fmt.Status:
    """Pior estado entre os lados (vermelho > laranja > verde/cinza)."""
    statuses = [x.status for x in by_side.values()]
    for color in ("red", "orange"):
        hit = [s for s in statuses if s.color == color]
        if hit:
            return fmt.Status(" · ".join(s.label for s in hit), color)
    return fmt.Status(" · ".join(s.label for s in statuses), "green")


def liquidity_by_side(positions: Sequence[PositionTarget], cfg: FundConfig
                      ) -> dict[str, SideLiquidity]:
    """Máx. de dias para liquidar por lado com o teto de cada lado (long 3 d; short 2 d).

    Um único teto para a carteira inteira esconderia um short acima do limite dos shorts.
    Ausente continua ausente (contado em ``n_missing``), nunca zero.
    """
    limits = {"LONG": cfg.liquidity.max_days_to_liquidate_long,
              "SHORT": cfg.liquidity.max_days_to_liquidate_short}
    out: dict[str, SideLiquidity] = {}
    for side, lim in limits.items():
        ps = [p for p in positions if p.side.value == side]
        vals = [v for p in ps if (v := _finite(p.days_to_liquidate)) is not None]
        out[side] = SideLiquidity(side, max(vals) if vals else None, float(lim), len(ps),
                                  len(ps) - len(vals))
    return out


def least_liquid(positions: Sequence[PositionTarget], n: int = 10) -> list[PositionTarget]:
    """Posições menos líquidas primeiro; dias ausentes (liquidez desconhecida) vêm antes de
    todas — nunca tratadas como liquidez imediata."""
    def key(p: PositionTarget) -> tuple[int, float, str]:
        d = _finite(p.days_to_liquidate)
        return (0, 0.0, p.issuer_id) if d is None else (1, -d, p.issuer_id)

    return sorted(positions, key=key)[:n]


def decision_timing(decision: Decision, cfg: FundConfig) -> fmt.Status:
    """Horário da decisão vs. prazo do mandato no pregão de decisão (antes do MOC)."""
    dt = decision.decided_at
    if dt.tzinfo is None:
        return fmt.Status("horário sem fuso: prazo não verificável", "orange")
    from ..portfolio.execucao import prazo_efetivo

    tz = ZoneInfo(cfg.fund.timezone)
    deadline = prazo_efetivo(decision.week, cfg).astimezone(tz)
    hhmm = f"{deadline:%H:%M}"
    if dt <= deadline:
        return fmt.Status(f"dentro do prazo ({hhmm} de {fmt.date_br(decision.week)})", "green")
    return fmt.Status(f"APÓS o prazo ({hhmm} de {fmt.date_br(decision.week)})", "red")


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


def squeeze_alerted(record: DailyRecord | None) -> set[str]:
    """Emissores citados em alertas de squeeze do registro (texto gerado pela rotina diária)."""
    if record is None:
        return set()
    ids = {p.issuer_id for p in record.positions} | {p.ticker for p in record.positions}
    by_ticker = {p.ticker: p.issuer_id for p in record.positions}
    out: set[str] = set()
    for alert in record.alerts:
        if "squeeze" not in alert.lower():
            continue
        for token in re.findall(r"[\w.\-]+", alert):
            if token in ids:
                out.add(by_ticker.get(token, token))
    return out


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
    overdue: bool = False


def _at(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=tz)


def next_events(now: datetime, cfg: FundConfig, decided_weeks: set[date] | None = None
                ) -> list[Event]:
    """Próxima decisão semanal (prazo do mandato) e próximo fechamento diário (horário local).

    A data de início do mandato é sempre dia de montagem (carteira inaugural); antes dela, sem
    semana decidida, o próximo fechamento diário é o do início."""
    from ..calendar import chave_da_semana, is_session, proximas_montagens
    from ..portfolio.execucao import prazo_efetivo

    tz = ZoneInfo(cfg.fund.timezone)
    local = now.astimezone(tz)
    today = local.date()
    decided = decided_weeks or set()
    events: list[Event] = []

    current = chave_da_semana(today, cfg)
    if (current is not None and current <= today and current not in decided
            and current >= cfg.fund.inception_date):
        deadline = prazo_efetivo(current, cfg).astimezone(tz)
        if deadline <= local:
            events.append(Event("Decisão semanal ATRASADA", deadline,
                                "prazo do mandato vencido sem decisão gravada no livro",
                                overdue=True))
    # Antes da data de início, sem semana decidida, nada é montado antes dela.
    start = (cfg.fund.inception_date if not decided and today < cfg.fund.inception_date
             else today)
    for first in proximas_montagens(start, cfg):
        if first in decided:
            continue
        deadline = prazo_efetivo(first, cfg).astimezone(tz)
        if deadline <= local:
            continue
        # Sem semana decidida, a próxima montagem é a carteira inaugural.
        inaugural = not decided and first >= cfg.fund.inception_date
        events.append(Event("Decisão semanal (autônoma)", deadline,
                            ("carteira inaugural; " if inaugural else "")
                            + f"pesquisa a partir de {cfg.fund.weekly_research_start_local}; "
                            "execução no fechamento (MOC)"))
        break

    for k in range(0, 15):
        d = start + timedelta(days=k)
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


def market_is_synthetic(market_root: Path) -> bool:
    """Leitura leve dos manifestos das bases (sem carregar preços) para o banner."""
    base = Path(market_root) / "base"
    if not base.is_dir():
        return False
    for manifest in base.glob("*/manifest.json"):
        try:
            if bool(read_json(manifest).get("is_synthetic")):
                return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


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
    """Seção de invariantes do CDP no AGENTS.md (ou ``None``) e a origem consultada.

    Preferência: título com "CDP" e "Invariantes"; senão o primeiro título com "CDP".
    """
    text = read_text(Path(path))
    if not text:
        return None, f"{Path(path).as_posix()} não encontrado"
    lines = text.splitlines()
    heads: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m and "CDP" in m.group(2):
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    heads.sort(key=lambda h: (0 if "invariante" in h[2].lower() else 1, h[0]))
    for i, level, title in heads:
        body: list[str] = []
        for nxt in lines[i + 1:]:
            m2 = re.match(r"^(#{1,6})\s+", nxt)
            if m2 and len(m2.group(1)) <= level:
                break
            body.append(nxt)
        section = "\n".join(body).strip()
        if section:
            return section, f"{Path(path).as_posix()} — {title}"
    return None, f"{Path(path).as_posix()} (sem seção do CDP)"
