"""Orquestrador multiagente da pesquisa semanal (padrão "centauro").

Papéis (docs/research/01, 02 e 07):

- R5 macro/país — regime e sinalizações por país;
- R2 extrator de notícias (temperatura 0) — notícias SANITIZADAS; itens com suspeita de injeção
  são excluídos do contexto dos analistas e registrados;
- R3 analista fundamentalista neutro (sem persona) — ``samples_per_judgment`` amostras (1 se o
  provedor for determinístico) e portão de concordância de sinal; stance = mediana (truncada
  em direção a zero), confiança = concordância × confiança média;
- R4 debate bull × bear + juiz — só para os ``top N`` por |alpha_z|; o juiz ajusta a stance em
  no máximo ±1 e somente com evidência nova válida; bull/bear só argumentam;
- R6 sentinela de short/squeeze — regras determinísticas + LLM; o LLM só pode APERTAR;
- R7 verificador — guardrails de código em toda saída; falha ⇒ abstenção (ou ``caution``).

Toda chamada gera um :class:`~cdp.contracts.LLMCallRecord` (ledger append-only com resposta
bruta e hashes). As respostas entram no ``input_hash`` das notas, portanto no
``research_hash``. Falhas do provedor nunca derrubam a execução: viram abstenções. Se o kill
switch da IA disparar, a semana segue em modo "somente quant" (visões descartadas, exceto as
restrições das regras determinísticas de short).
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pandas as pd
from pydantic import BaseModel, ValidationError

from ..config import FundConfig
from ..contracts import (
    Catalyst,
    EvidenceKind,
    EvidenceRef,
    FactBook,
    LLMCallRecord,
    MacroNote,
    NewsItem,
    ResearchNote,
    ResearchPack,
    SqueezeAssessment,
    View,
    ViewSource,
)
from ..hashing import combine_hashes, sha256_obj, sha256_text
from .factbook import facts_for_issuer, macro_facts, render_facts_block
from .guardrails import (
    INJECTION_FLAG_PREFIX,
    ai_kill_switch,
    defuse_for_display,
    detect_injection,
    is_injection_flagged,
    sanitize_untrusted,
    verifier_messages,
    verify_analyst_output,
    verify_debate_output,
    verify_judge_output,
    verify_macro_output,
    verify_news_output,
    verify_short_risk_output,
)
from .prompts import (
    PROMPT_VERSION,
    analyst_prompt,
    debate_prompt,
    drivers_block,
    format_news_block,
    judge_prompt,
    macro_prompt,
    news_prompt,
    short_risk_prompt,
)
from .providers.base import (
    LLMProvider,
    LLMResult,
    error_result,
    request_sha256,
    result_payload,
    usage_tokens,
)
from .providers.cache import LLMCallLedger, calls_digest
from .schemas import (
    AnalystOutput,
    DebateOutput,
    Driver,
    JudgeOutput,
    MacroOutput,
    NewsAssessment,
    NewsOutput,
    ShortRiskOutput,
)

COUNTRY_CURRENCY = {"BR": "BRL", "MX": "MXN", "CL": "CLP", "CO": "COP", "PE": "PEN", "AR": "ARS"}
LOCAL_LANGUAGE = {"BR": "pt", "MX": "es", "CL": "es", "CO": "es", "PE": "es", "AR": "es",
                  "PA": "es", "UY": "es"}
DEBATE_TOP_N = 5
ANALYST_SAMPLE_TEMPERATURE = 0.7
"""Temperatura das amostras do analista quando há mais de uma (provedores que a aceitam)."""
PROVIDER_FAILURE_RATE = 0.5
"""Fração de chamadas com erro do provedor acima da qual a semana é tratada como indisponível."""
MAX_NEWS_PER_ISSUER = 15
MAX_NEWS_PER_COUNTRY = 20
NEWS_TITLE_MAX_LEN = 500
VIEW_RATIONALE_MAX_LEN = 300
NEWS_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,119}$")
"""Ids de notícia/emissor aceitos nos prompts (metadados não confiáveis fora do título)."""
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?$")
UNKNOWN_LANGUAGE = "und"
VERDICT_ORDER = {"ok": 0, "caution": 1, "veto": 2}
GOVERNANCE_SCOPE = "GOVERNANÇA"
GOVERNANCE_PROVIDER = "codigo (governança determinística)"
RULES_AUTHOR = "regras determinísticas de short (Calculado)"
AI_LABEL = "IA"
CALCULATED_LABEL = "Calculado"
TASK_ROLE = {
    "macro": "macro", "news": "news_sentiment", "analyst": "fundamental",
    "debate_bull": "bull_bear_debate", "debate_bear": "bull_bear_debate",
    "judge": "bull_bear_judge", "short_risk": "short_risk",
}
_MATERIALITY_PT = {"high": "alta", "medium": "média", "low": "baixa"}
_MATERIALITY_WEIGHT = {"high": 1.0, "medium": 0.5, "low": 0.25}
_SENTIMENT_SCORE = {"positive": 1, "neutral": 0, "negative": -1}
_ROLE_ORDER = {"fundamental": 0, "bull_bear_judge": 1, "news_sentiment": 2, "short_risk": 3,
               "pm": 4}


# ==========================================================
# Tipos públicos
# ==========================================================

@dataclass
class ResearchRequest:
    """Insumos da pesquisa semanal (``issuers``: índice issuer_id; issuer_name, country, sector)."""

    week: date
    as_of: date
    snapshot_id: str
    long_candidates: list[str]
    short_candidates: list[str]
    countries: list[str]
    issuers: pd.DataFrame
    factbook: FactBook
    news: list[NewsItem]
    squeeze: pd.DataFrame | None = None
    alpha_z: pd.Series | None = None


@dataclass(frozen=True)
class GateResult:
    """Resultado do portão de concordância de sinal do analista (R3)."""

    abstain: bool
    stance: int
    confidence: float
    agreement: float
    representative: int | None
    reason: str


@dataclass(frozen=True)
class ResearchRun:
    """Execução completa: pacote, ledger e decisões de governança."""

    pack: ResearchPack
    records: list[LLMCallRecord]
    ledger_hash: str
    calls_hash: str
    kill_switch: bool
    kill_reason: str
    excluded_news: dict[str, list[str]]
    rule_verdicts: dict[str, str]
    notes_issues_rate: float
    provider_error_rate: float
    injection_confirmed: bool
    budget_exhausted: bool
    governance_events: list[str] = field(default_factory=list)


@dataclass
class _Call:
    result: LLMResult
    record: LLMCallRecord
    issues: list[str]
    input_hash: str

    @property
    def accepted(self) -> bool:
        return self.result.ok and not self.issues


# ==========================================================
# Funções puras
# ==========================================================

def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def sign_agreement_gate(samples: Sequence[AnalystOutput | None], min_agreement: float,
                        n_requested: int | None = None) -> GateResult:
    """Portão de concordância de sinal entre amostras do analista.

    Amostras ``None`` (erro/reprovadas no verificador) ou com ``abstain`` contam no
    denominador como discordância. Stance final = mediana das amostras válidas truncada em
    direção a zero; concordância = fração das amostras pedidas com o mesmo sinal da mediana;
    confiança = concordância × média das confianças concordantes. Concordância abaixo de
    ``min_agreement`` ⇒ abstenção.
    """
    n = max(int(n_requested or len(samples)), 1)
    valid = [(i, s) for i, s in enumerate(samples) if s is not None and not s.abstain]
    if not valid:
        return GateResult(True, 0, 0.0, 0.0, None, "nenhuma amostra válida do analista")
    med = statistics.median(s.stance for _, s in valid)
    stance = int(math.trunc(med))
    target = _sign(med)
    agreeing = [(i, s) for i, s in valid if _sign(s.stance) == target]
    agreement = len(agreeing) / n
    if agreement < min_agreement:
        return GateResult(True, 0, 0.0, round(agreement, 4), None,
                          "concordância de sinal entre amostras abaixo do mínimo configurado")
    confidence = round(agreement * statistics.fmean(s.confidence for _, s in agreeing), 4)
    exact = [(i, s) for i, s in agreeing if s.stance == stance] or agreeing
    rep = sorted(exact, key=lambda t: (-t[1].confidence, t[0]))[0][0]
    return GateResult(False, stance, confidence, round(agreement, 4), rep, "")


def most_restrictive(*verdicts: str) -> str:
    return max(verdicts, key=lambda v: VERDICT_ORDER.get(v, 2))


def rule_short_verdict(squeeze: pd.DataFrame | None, issuer_id: str,
                       cfg: FundConfig) -> tuple[str, str]:
    """Veredito determinístico de short (HIGH ou sem taxa ⇒ veto; MEDIUM/NA ⇒ caution)."""
    row = squeeze.loc[issuer_id] if (squeeze is not None and issuer_id in squeeze.index) else None
    bucket = str(row.get("bucket")) if row is not None and pd.notna(row.get("bucket")) else "NA"
    fee_raw = row.get("borrow_fee") if row is not None else None
    fee = float(fee_raw) if fee_raw is not None and pd.notna(fee_raw) else None
    if bucket == "HIGH":
        return "veto", "faixa de squeeze HIGH"
    if fee is None:
        return "veto", "sem taxa de aluguel observada ou estimada"
    if fee > cfg.shorting.max_borrow_fee:
        return "veto", "taxa de aluguel acima do máximo do mandato"
    if bucket in ("MEDIUM", "NA"):
        return "caution", f"faixa de squeeze {bucket} (NA tratado como MEDIUM)"
    return "ok", "faixa de squeeze LOW"


def _caution_cap(cfg: FundConfig) -> float:
    return float(cfg.risk.max_short_weight * cfg.squeeze.medium_short_cap_multiplier)


def _clip_text(text: str, limit: int = VIEW_RATIONALE_MAX_LEN) -> str:
    """Trunca sem cortar um placeholder ``{{fact:…}}`` ao meio (renderização segura)."""
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)]
    opened = cut.rfind("{{")
    if opened > cut.rfind("}}"):
        cut = cut[:opened]
    return cut.rstrip() + "…"


def notes_to_views(notes: Iterable[ResearchNote], cfg: FundConfig, *,
                   long_candidates: Iterable[str] = ()) -> list[View]:
    """Converte notas verificadas em visões (uma por emissor; só restringem risco).

    - inclinação (score = stance): se houver nota ``bull_bear_judge`` aceita (confiança > 0),
      ela prevalece — o juiz viu a tese do analista e o debate, inclusive quando neutraliza a
      stance (stance 0 ⇒ sem inclinação). Sem juiz aceito, vale a nota ``fundamental`` com
      stance ≠ 0 e confiança > 0. Entre notas do mesmo papel, a de evidência mais forte (mais
      evidências, depois maior confiança);
    - ``short_risk`` ``veto`` ⇒ ``no_short``; ``caution`` ⇒ ``max_abs_weight`` =
      ``max_short_weight × medium_short_cap_multiplier``;
    - restrições combinadas pelo mais restritivo.

    ``long_candidates``: emissores que também são candidatos/posições compradas. Para eles o
    ``caution`` NÃO vira ``max_abs_weight``: o contrato ``View`` não tem teto por lado e o teto
    simétrico limitaria a posição comprada (risco de squeeze só existe vendido); o lado vendido
    continua limitado pelo multiplicador MEDIUM/NA que o otimizador aplica a partir da tabela
    de squeeze. ``veto`` (``no_short``) vale sempre.
    """
    protect = {str(i) for i in long_candidates}
    judges: dict[str, list[ResearchNote]] = {}
    analysts: dict[str, list[ResearchNote]] = {}
    restrict: dict[str, dict[str, Any]] = {}
    for n in notes:
        if n.role == "bull_bear_judge" and n.confidence > 0:
            judges.setdefault(n.issuer_id, []).append(n)
        elif n.role == "fundamental" and n.stance != 0 and n.confidence > 0:
            analysts.setdefault(n.issuer_id, []).append(n)
        if n.role == "short_risk" and n.squeeze is not None and n.squeeze.verdict != "ok":
            r = restrict.setdefault(n.issuer_id, {"no_short": False, "cap": None, "notes": [],
                                                  "author": n.provider,
                                                  "rationale": n.squeeze.rationale})
            r["notes"].append(n.note_id)
            if n.squeeze.verdict == "veto":
                r["no_short"] = True
            elif n.issuer_id not in protect:
                cap = _caution_cap(cfg)
                r["cap"] = cap if r["cap"] is None else min(r["cap"], cap)
    views = []
    for iid in sorted(set(judges) | set(analysts) | set(restrict)):
        cands = judges.get(iid) or analysts.get(iid) or []
        best = max(cands, key=lambda n: (len(n.evidence), n.confidence, n.note_id)
                   ) if cands else None
        if best is not None and best.stance == 0:
            best = None  # juiz neutralizou a stance do analista: sem inclinação
        r = restrict.get(iid)
        if r is not None and not r["no_short"] and r["cap"] is None:
            r = None  # caution protegido (candidato comprado): nada a restringir pela visão
        if best is None and r is None:
            continue
        r = r or {"no_short": False, "cap": None, "notes": [], "author": "", "rationale": ""}
        if best is not None:
            score, conf = best.stance, best.confidence
            rationale, author = _clip_text(best.thesis), best.provider
            note_ids = [best.note_id] + r["notes"]
        else:
            score, conf = 0, (1.0 if r["no_short"] else 0.0)
            rationale = _clip_text(r["rationale"] or "Restrição de risco de short")
            author, note_ids = r["author"], list(r["notes"])
        views.append(View(issuer_id=iid, source=ViewSource.AI, score=score,
                          confidence=round(float(conf), 4), rationale=rationale, author=author,
                          no_short=bool(r["no_short"]),
                          max_abs_weight=None if r["no_short"] else r["cap"],
                          note_ids=sorted(set(note_ids))))
    return views


def merge_views(views: Iterable[View]) -> list[View]:
    """Uma visão por emissor: inclinação da primeira visão com score ≠ 0 e restrições somadas.

    ``no_short``/``no_long`` combinam por "ou"; ``max_abs_weight`` pelo mínimo (só aperta).
    """
    by_issuer: dict[str, list[View]] = {}
    for v in views:
        by_issuer.setdefault(v.issuer_id, []).append(v)
    out = []
    for iid in sorted(by_issuer):
        group = by_issuer[iid]
        tilt = next((v for v in group if v.score != 0), group[0])
        caps = [v.max_abs_weight for v in group if v.max_abs_weight is not None]
        no_short = any(v.no_short for v in group)
        no_long = any(v.no_long for v in group)
        confidence = tilt.confidence
        if tilt.score == 0 and (no_short or no_long):
            confidence = max(v.confidence for v in group)
        out.append(View(issuer_id=iid, source=ViewSource.AI, score=tilt.score,
                        confidence=confidence, rationale=tilt.rationale, author=tilt.author,
                        no_short=no_short, no_long=no_long,
                        max_abs_weight=min(caps) if caps else None,
                        note_ids=sorted({n for v in group for n in v.note_ids})))
    return out


def rule_views(rule_verdicts: dict[str, str], cfg: FundConfig, *,
               long_candidates: Iterable[str] = ()) -> list[View]:
    """Restrições das regras determinísticas de short (mantidas mesmo com a IA desligada).

    ``long_candidates``: ver :func:`notes_to_views` (``caution`` não limita o lado comprado).
    """
    protect = {str(i) for i in long_candidates}
    out = []
    for iid, verdict in sorted(rule_verdicts.items()):
        if verdict == "veto":
            out.append(View(issuer_id=iid, source=ViewSource.AI, score=0, confidence=1.0,
                            rationale="Veto de short por regra determinística (squeeze/aluguel).",
                            author=RULES_AUTHOR, no_short=True))
        elif verdict == "caution" and iid not in protect:
            out.append(View(issuer_id=iid, source=ViewSource.AI, score=0, confidence=0.0,
                            rationale="Teto reduzido de short por regra determinística.",
                            author=RULES_AUTHOR, max_abs_weight=_caution_cap(cfg)))
    return out


def provenance_label(provider: str) -> str:
    """``IA`` para textos de provedores de IA; ``Calculado`` para código; ``Gestor`` para PM."""
    p = (provider or "").strip().lower()
    if p in {"pm", "gestor", "manual", "human", "humano"}:
        return "Gestor"
    if p.startswith("codigo") or p.startswith("regras"):
        return CALCULATED_LABEL
    return AI_LABEL


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _safe_id(value: str) -> str:
    """Id não confiável para exibição: ids inválidos nunca são ecoados (podem carregar a
    própria injeção); aparecem como ``id-invalido:<sha256[:12]>``."""
    text = str(value)
    return text if NEWS_ID_RE.match(text) else f"id-invalido:{sha256_text(text)[:12]}"


def _revalidate(parsed: BaseModel | None, schema: type[BaseModel]
                ) -> tuple[BaseModel | None, str | None]:
    """Revalida a saída do provedor pelo schema (objetos montados sem validação, ex.
    ``model_construct``, não podem furar intervalos como stance −2…+2)."""
    try:
        data = parsed.model_dump(mode="json", warnings=False)  # type: ignore[union-attr]
        return schema.model_validate(data), None
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}"
                            for e in exc.errors()[:5])
        return None, f"Saída fora do schema {schema.__name__} na revalidação: {details}"
    except Exception as exc:  # noqa: BLE001 — objeto malformado vira erro, nunca exceção
        return None, f"Saída ilegível na revalidação ({type(exc).__name__})."


def _evidence_refs(ids: Iterable[str], fb: FactBook, news_ids: set[str],
                   quotes: dict[str, str] | None = None) -> list[EvidenceRef]:
    refs = []
    for rid in sorted(set(ids)):
        kind = (EvidenceKind.FACT if rid in fb.facts else
                EvidenceKind.NEWS if rid in news_ids else EvidenceKind.SOURCE)
        note = f"trecho sha256={sha256_text(quotes[rid])}" if quotes and rid in quotes else ""
        refs.append(EvidenceRef(kind=kind, ref_id=rid, note=note))
    return refs


# ==========================================================
# Orquestrador
# ==========================================================

class ResearchOrchestrator:
    """Executa os papéis R2–R7 sobre o provedor dado, com orçamento de chamadas e ledger."""

    def __init__(self, provider: LLMProvider, cfg: FundConfig, max_calls: int = 400, *,
                 ledger: LLMCallLedger | None = None,
                 clock: Callable[[], datetime] | None = None,
                 debate_top_n: int = DEBATE_TOP_N, eval_regressed: bool = False) -> None:
        self.provider = provider
        self.cfg = cfg
        self.max_calls = int(max_calls)
        self.ledger = ledger
        self.clock = clock
        self.debate_top_n = int(debate_top_n)
        self.eval_regressed = bool(eval_regressed)
        self.last_run: ResearchRun | None = None

    # ------------------------------------------------------------------ API
    def run(self, req: ResearchRequest) -> ResearchPack:
        return self.execute(req).pack

    def run_with_ledger(self, req: ResearchRequest) -> tuple[ResearchPack, list[LLMCallRecord]]:
        result = self.execute(req)
        return result.pack, result.records

    def execute(self, req: ResearchRequest) -> ResearchRun:
        _RunState.check_request(req)
        st = _RunState(self, req)
        st.prepare_news()
        st.run_macro()
        st.run_news()
        st.run_analysts()
        st.run_debates()
        st.run_short_risk()
        run = st.finish()
        self.last_run = run
        return run


class _RunState:
    """Estado de uma execução (separado do orquestrador para manter ``execute`` reentrante)."""

    def __init__(self, orch: ResearchOrchestrator, req: ResearchRequest) -> None:
        self.o = orch
        self.p = orch.provider
        self.cfg = orch.cfg
        self.req = req
        self.fb = req.factbook
        self.as_of = req.as_of
        recorded_at = getattr(self.p, "recorded_at", None)
        if orch.clock is not None:
            self.now = orch.clock()
        elif isinstance(recorded_at, datetime):
            # Replay: reutiliza o carimbo da execução original (reprodução bit a bit).
            self.now = recorded_at
        elif self.p.deterministic:
            # Carimbo lógico determinístico (segunda-feira 06:00 UTC) para execuções
            # reprodutíveis do provedor demo; provedores reais usam o relógio.
            self.now = datetime.combine(req.week, time(6, 0), tzinfo=UTC)
        else:
            self.now = datetime.now(UTC)
        self.calls = 0
        self.records: list[LLMCallRecord] = []
        self.notes: list[ResearchNote] = []
        self.macro: list[MacroNote] = []
        self.macro_text: dict[str, str] = {}
        self.eligible: dict[str, NewsItem] = {}
        self.news_flags: dict[str, list[str]] = {}
        self.excluded: dict[str, list[str]] = {}
        self.assessments: dict[str, NewsAssessment] = {}
        self.analyst_notes: dict[str, ResearchNote] = {}
        self.rule_verdicts: dict[str, str] = {}
        self.gate_failed_notes: set[str] = set()
        self.llm_note_ids: set[str] = set()
        self.injection_confirmed = False
        self.budget_exhausted = False
        self.skipped_tasks = 0
        self.events: list[str] = []
        self.candidates = sorted(dict.fromkeys(
            [str(i) for i in req.long_candidates] + [str(i) for i in req.short_candidates]))

    @staticmethod
    def check_request(req: ResearchRequest) -> None:
        if req.factbook.as_of != req.as_of:
            raise ValueError("O FactBook precisa ter o mesmo as_of da pesquisa.")
        if req.as_of > req.week:
            raise ValueError("as_of posterior à semana de decisão (look-ahead).")

    # ------------------------------------------------------------------ utilidades
    def issuer_row(self, iid: str) -> dict[str, Any]:
        row: dict[str, Any] = {"issuer_id": iid}
        df = self.req.issuers
        if df is not None and iid in df.index:
            for col, sources in (("issuer_name", ("issuer_name",)), ("country", ("country",)),
                                 ("sector", ("sector", "gics_sector"))):
                for src in sources:
                    if src in df.columns and pd.notna(df.loc[iid, src]):
                        row[col] = str(df.loc[iid, src])
                        break
        return row

    def alpha(self, iid: str) -> float | None:
        a = self.req.alpha_z
        if a is None or iid not in a.index:
            return None
        return _finite(a.loc[iid])

    def allowed_terms(self, iid: str | None) -> list[str]:
        if iid is None:
            return []
        row = self.issuer_row(iid)
        return [t for t in (iid, row.get("issuer_name", "")) if t]

    def note_id(self, role: str, key: str) -> str:
        return f"{self.req.week.isoformat()}:{role}:{key}"

    def news_ids_for(self, iid: str) -> list[str]:
        items = [n for n in self.eligible.values() if iid in n.issuer_ids]
        items.sort(key=lambda n: (n.published_at, n.news_id), reverse=True)
        return sorted(n.news_id for n in items[:MAX_NEWS_PER_ISSUER])

    def issuer_fact_ids(self, iid: str) -> list[str]:
        country = self.issuer_row(iid).get("country", "")
        ccy = COUNTRY_CURRENCY.get(country)
        macro_ids = [f for f in macro_facts(self.fb)
                     if not f.startswith("fx.") or f == f"fx.{ccy}.ret_1m"]
        return sorted(list(facts_for_issuer(self.fb, iid)) + macro_ids)

    def facts_values(self, fact_ids: Iterable[str]) -> dict[str, float | None]:
        return {f: self.fb.facts[f].value for f in sorted(fact_ids) if f in self.fb.facts}

    def facts_block(self, fact_ids: Iterable[str]) -> str:
        ids = list(fact_ids)
        issuers = {self.fb.facts[f].issuer_id for f in ids if f in self.fb.facts} - {None}
        return render_facts_block(self.fb, issuers, macro=True, fact_ids=ids)  # type: ignore[arg-type]

    def news_dates(self, ids: Iterable[str]) -> dict[str, datetime]:
        return {i: self.eligible[i].published_at for i in ids if i in self.eligible}

    def news_texts(self, ids: Iterable[str]) -> dict[str, str]:
        return {i: self.eligible[i].title for i in ids if i in self.eligible}

    # ------------------------------------------------------------------ chamada + ledger
    def call(self, task: str, schema: type[BaseModel], system: str, user: str,
             context: dict[str, Any], verify: Callable[[BaseModel], list[str]], *,
             issuer_id: str | None = None, sample: int = 0,
             temperature: float = 0.0) -> _Call | None:
        if self.calls >= self.o.max_calls:
            self.budget_exhausted = True
            self.skipped_tasks += 1
            return None
        self.calls += 1
        p = self.p
        req_hash = request_sha256(p.name, p.model, system, user, schema.__name__, temperature,
                                  sample)
        input_pack = sha256_obj(context)
        try:
            result = p.complete_json(system, user, schema, task=task, temperature=temperature,
                                     sample=sample, context=context)
        except Exception as exc:  # noqa: BLE001 — provedor nunca derruba a pesquisa
            result = error_result(p.name, p.model,
                                  f"Falha inesperada do provedor ({type(exc).__name__}): {exc}",
                                  deterministic=p.deterministic)
        if result.error is None and not isinstance(result.parsed, schema):
            result.error = f"Saída sem o schema esperado {schema.__name__}."
            result.parsed = None
        elif result.error is None:
            result.parsed, problem = _revalidate(result.parsed, schema)
            if problem:
                result.error = problem
        issues: list[str] = []
        if result.ok:
            try:
                issues = verify(result.parsed)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                issues = [f"falha no verificador ({type(exc).__name__}): {exc}"]
            if any("padrão de injeção na saída" in i for i in issues):
                self.injection_confirmed = True
        raw_path, resp_hash = None, (sha256_text(result.raw_text)
                                     if isinstance(result.raw_text, str) else None)
        if self.o.ledger is not None:
            raw_path, resp_hash = self.o.ledger.save_raw(
                req_hash, result_payload(result, request_hash=req_hash,
                                         schema_name=schema.__name__, configured_model=p.model))
        tin, tout = usage_tokens(result.usage)
        record = LLMCallRecord(
            call_id=f"{self.req.week.isoformat()}:{self.calls:04d}:{req_hash[:12]}",
            week=self.req.week, task=task, role=TASK_ROLE.get(task, task), issuer_id=issuer_id,
            provider=p.name, model=result.model or p.model, prompt_version=PROMPT_VERSION,
            schema_name=schema.__name__, request_sha256=req_hash, input_pack_sha256=input_pack,
            response_sha256=resp_hash, raw_response_path=raw_path,
            stop_reason=result.stop_reason, parse_ok=result.ok,
            validation_issues=([f"ERRO: {result.error}"] if result.error else []) + issues,
            input_tokens=tin, output_tokens=tout, cost_usd=result.cost_usd,
            latency_ms=round(float(result.latency_ms), 3), created_at=self.now,
        )
        if self.o.ledger is not None:
            self.o.ledger.append(record)
        self.records.append(record)
        base = sha256_obj({"system": system, "user": user, "context": input_pack})
        return _Call(result=result, record=record, issues=issues, input_hash=base)

    def failure_lines(self, call: _Call | None) -> list[str]:
        if call is None:
            return ["Orçamento de chamadas de IA esgotado: tarefa não executada (abstenção)."]
        if call.result.error:
            return [f"Falha do provedor de IA: {defuse_for_display(call.result.error, 300)}"]
        return verifier_messages(call.issues)

    def input_hash(self, calls: Sequence[_Call | None], extra: str = "") -> str:
        done = [c for c in calls if c is not None]
        base = sha256_obj([c.input_hash for c in done] + [extra])
        return combine_hashes(base, calls_digest(c.record for c in done))

    def model_of(self, calls: Sequence[_Call | None]) -> str | None:
        models = [c.record.model for c in calls if c is not None and c.record.model]
        return models[0] if models else self.p.model

    def register_llm_note(self, note_id: str, calls: Sequence[_Call | None]) -> None:
        done = [c for c in calls if c is not None]
        if not done:
            return
        self.llm_note_ids.add(note_id)
        if any(c.issues for c in done):
            self.gate_failed_notes.add(note_id)

    # ------------------------------------------------------------------ notícias
    def prepare_news(self) -> None:
        lookback = self.cfg.research.news_lookback_days
        start = self.as_of - timedelta(days=lookback)
        counts: dict[str, int] = {}
        for n in self.req.news:
            counts[n.news_id] = counts.get(n.news_id, 0) + 1
        for n in sorted(self.req.news, key=lambda x: (x.published_at, x.news_id)):
            reasons = []
            pub = n.published_at.astimezone(UTC).date()
            if pub > self.as_of:
                reasons.append("publicada após o as_of (look-ahead)")
            elif pub < start:
                reasons.append(f"fora da janela de {lookback} dias")
            title, flags = sanitize_untrusted(n.title, NEWS_TITLE_MAX_LEN)
            source, sflags = sanitize_untrusted(n.source, 80)
            flags = sorted(set(flags) | {f for f in sflags if f.startswith(INJECTION_FLAG_PREFIX)})
            # Metadados também são não confiáveis: id, idioma e emissores entram nos prompts.
            meta = [n.news_id, n.language, *n.issuer_ids]
            meta_inj = sorted({h for m in meta for h in detect_injection(str(m))})
            flags = sorted(set(flags) | {f"{INJECTION_FLAG_PREFIX}{h}" for h in meta_inj})
            if is_injection_flagged(flags):
                names = [f[len(INJECTION_FLAG_PREFIX):] for f in flags
                         if f.startswith(INJECTION_FLAG_PREFIX)]
                reasons.append(f"suspeita de injeção de instruções ({', '.join(names)})")
            if not NEWS_ID_RE.match(n.news_id or ""):
                reasons.append("id de notícia inválido (metadado não confiável)")
            if counts.get(n.news_id, 0) > 1:
                reasons.append("id de notícia duplicado no pacote")
            if not title:
                reasons.append("título vazio após sanitização")
            if reasons:
                self.excluded.setdefault(n.news_id, [])
                self.excluded[n.news_id] += [r for r in reasons
                                             if r not in self.excluded[n.news_id]]
                continue
            url = n.url if (n.url or "").lower().startswith(("http://", "https://")) else None
            language = n.language if LANGUAGE_RE.match(n.language or "") else UNKNOWN_LANGUAGE
            issuer_ids = sorted({i for i in n.issuer_ids if NEWS_ID_RE.match(i or "")})
            self.eligible[n.news_id] = n.model_copy(update={
                "title": title, "source": source, "url": url, "language": language,
                "issuer_ids": issuer_ids})
            self.news_flags[n.news_id] = flags
        for nid, reasons in sorted(self.excluded.items()):
            if any("injeção" in r for r in reasons):
                self.events.append(f"Notícia {_safe_id(nid)} excluída do contexto dos "
                                   "analistas: " + "; ".join(reasons) + ".")

    # ------------------------------------------------------------------ R5 macro
    def run_macro(self) -> None:
        for scope in sorted(dict.fromkeys(str(c) for c in self.req.countries)):
            ccy = COUNTRY_CURRENCY.get(scope)
            fact_ids = [f for f in macro_facts(self.fb)
                        if not f.startswith("fx.") or f == f"fx.{ccy}.ret_1m"]
            members = set()
            if self.req.issuers is not None and "country" in self.req.issuers.columns:
                members = set(self.req.issuers.index[self.req.issuers["country"] == scope])
            items = [n for n in self.eligible.values() if members.intersection(n.issuer_ids)]
            items = sorted(items, key=lambda n: (n.published_at, n.news_id),
                           reverse=True)[:MAX_NEWS_PER_COUNTRY]
            news_ids = sorted(n.news_id for n in items)
            context = {"task": "macro", "scope": scope, "currency": ccy,
                       "as_of": self.as_of.isoformat(), "facts": self.facts_values(fact_ids),
                       "news_ids": news_ids}
            system, user = macro_prompt(scope, self.facts_block(fact_ids), format_news_block(items),
                                        as_of=self.as_of, news_ids=news_ids)
            valid = set(fact_ids) | set(news_ids)
            call = self.call("macro", MacroOutput, system, user, context,
                             lambda out, s=scope, v=valid, ids=news_ids: verify_macro_output(
                                 out, self.fb, v, self.as_of, scope=s,
                                 evidence_dates=self.news_dates(ids)))
            nid = self.note_id("macro", scope)
            self.register_llm_note(nid, [call])
            if call is not None and call.accepted:
                out: MacroOutput = call.result.parsed  # type: ignore[assignment]
                note = MacroNote(
                    note_id=nid, week=self.req.week, scope=scope, stance=out.stance,
                    regime=out.regime, summary=out.summary,
                    key_events=[Catalyst(description=e.description, expected_date=e.expected_date,
                                         direction=e.direction) for e in out.key_events],
                    risks=list(out.risks), portfolio_implications=list(out.implications),
                    evidence=_evidence_refs(out.evidence_ids, self.fb, set(news_ids)),
                    provider=self.p.name, model=self.model_of([call]),
                    prompt_version=PROMPT_VERSION, created_at=self.now,
                    is_synthetic=self.fb.is_synthetic)
                self.macro_text[scope] = f"Regime: {out.regime}. {out.summary}"
            else:
                note = MacroNote(
                    note_id=nid, week=self.req.week, scope=scope, stance=0,
                    regime="indeterminado (abstenção)",
                    summary="Abstenção do analista macro: saída indisponível ou rejeitada pelo "
                            "verificador.",
                    risks=self.failure_lines(call), provider=self.p.name,
                    model=self.model_of([call]), prompt_version=PROMPT_VERSION,
                    created_at=self.now, is_synthetic=self.fb.is_synthetic)
            self.macro.append(note)

    # ------------------------------------------------------------------ R2 notícias
    def run_news(self) -> None:
        for iid in self.candidates:
            ids = self.news_ids_for(iid)
            if not ids:
                continue
            items = [self.eligible[i] for i in ids]
            context = {"task": "news", "issuer_id": iid, "as_of": self.as_of.isoformat(),
                       "items": [{"news_id": n.news_id, "title": n.title,
                                  "language": n.language,
                                  "flags": self.news_flags.get(n.news_id, [])} for n in items]}
            system, user = news_prompt(self.issuer_row(iid), format_news_block(items),
                                       as_of=self.as_of, news_ids=ids)
            expected = {i: iid for i in ids}
            call = self.call("news", NewsOutput, system, user, context,
                             lambda out, e=expected: verify_news_output(out, e), issuer_id=iid)
            nid = self.note_id("news_sentiment", iid)
            self.register_llm_note(nid, [call])
            if call is not None and call.accepted:
                out: NewsOutput = call.result.parsed  # type: ignore[assignment]
                bull, bear, total, used = [], [], 0.0, []
                for a in sorted(out.items, key=lambda x: x.news_id):
                    if a.injection_suspected:
                        self.excluded.setdefault(a.news_id, []).append(
                            "suspeita de injeção apontada pelo extrator de notícias")
                        self.events.append(f"Notícia {a.news_id} excluída: extrator de notícias "
                                           "apontou suspeita de injeção.")
                        continue
                    self.assessments[a.news_id] = a
                    used.append(a.news_id)
                    text = (f"Notícia {'positiva' if a.sentiment == 'positive' else 'negativa'} "
                            f"de materialidade {_MATERIALITY_PT[a.materiality]} "
                            f"(evento {a.event_type})")
                    if a.sentiment == "positive":
                        bull.append(text)
                    elif a.sentiment == "negative":
                        bear.append(text)
                    total += _SENTIMENT_SCORE[a.sentiment] * _MATERIALITY_WEIGHT[a.materiality]
                stance = 1 if total >= 0.5 else -1 if total <= -0.5 else 0
                label = "positiva" if stance > 0 else "negativa" if stance < 0 else "neutra"
                conf = round(min(1.0, sum(_MATERIALITY_WEIGHT[self.assessments[i].materiality]
                                          for i in used) / 2.0), 4) if used else 0.0
                note = self._note(nid, iid, "news_sentiment", [call], stance=stance,
                                  confidence=conf,
                                  thesis=f"Avaliação de notícias da semana: predominância {label}.",
                                  bull_points=bull, bear_points=bear,
                                  evidence=_evidence_refs(used, self.fb, set(used)))
            else:
                note = self._note(nid, iid, "news_sentiment", [call], stance=0, confidence=0.0,
                                  thesis="Abstenção do extrator de notícias.",
                                  key_risks=self.failure_lines(call))
            self.notes.append(note)
        for nid in [n for n in self.excluded if n in self.eligible]:
            self.eligible.pop(nid, None)

    def _note(self, nid: str, iid: str, role: str, calls: Sequence[_Call | None], **kw: Any
              ) -> ResearchNote:
        horizon = int(min(52, max(1, round(self.cfg.alpha.horizon_weeks))))
        return ResearchNote(
            note_id=nid, issuer_id=iid, week=self.req.week, role=role, provider=self.p.name,
            model=self.model_of(calls), prompt_version=PROMPT_VERSION,
            horizon_weeks=horizon, input_hash=self.input_hash(calls, extra=role),
            created_at=self.now, is_synthetic=self.fb.is_synthetic, **kw)

    # ------------------------------------------------------------------ R3 analista
    def analyst_context(self, iid: str) -> tuple[dict, list[str], list[str]]:
        row = self.issuer_row(iid)
        fact_ids = self.issuer_fact_ids(iid)
        news_ids = self.news_ids_for(iid)
        news = []
        for i in news_ids:
            n = self.eligible[i]
            a = self.assessments.get(i)
            news.append({"news_id": i, "title": n.title, "language": n.language,
                         "published_at": n.published_at.isoformat(),
                         "sentiment": a.sentiment if a else None,
                         "materiality": a.materiality if a else None,
                         "event_type": a.event_type if a else None})
        local = LOCAL_LANGUAGE.get(row.get("country", ""))
        ctx = {"task": "analyst", **row, "as_of": self.as_of.isoformat(),
               "alpha_z": self.alpha(iid), "facts": self.facts_values(fact_ids), "news": news,
               "local_language": any(n["language"] == local for n in news) if local else False,
               "macro": self.macro_text.get(row.get("country", ""), "")}
        return ctx, fact_ids, news_ids

    def run_analysts(self) -> None:
        n_samples = 1 if self.p.deterministic else int(self.cfg.research.samples_per_judgment)
        temperature = 0.0 if n_samples == 1 else ANALYST_SAMPLE_TEMPERATURE
        horizon = int(min(52, max(1, round(self.cfg.alpha.horizon_weeks))))
        for iid in self.candidates:
            ctx, fact_ids, news_ids = self.analyst_context(iid)
            row = self.issuer_row(iid)
            items = [self.eligible[i] for i in news_ids]
            macro = self.macro_text.get(row.get("country", ""), "") or \
                "Sem leitura macro verificada para o país."
            system, user = analyst_prompt(row, self.facts_block(fact_ids), format_news_block(items),
                                          macro, as_of=self.as_of, horizon_weeks=horizon,
                                          news_ids=news_ids)
            valid = set(fact_ids) | set(news_ids)
            dates, texts = self.news_dates(news_ids), self.news_texts(news_ids)
            terms = self.allowed_terms(iid)

            def verify(out: BaseModel, v=valid, d=dates, t=texts, i=iid, tm=terms) -> list[str]:
                return verify_analyst_output(out, self.fb, v, self.as_of,  # type: ignore[arg-type]
                                             evidence_dates=d, evidence_texts=t, issuer_id=i,
                                             allowed_terms=tm)

            calls = [self.call("analyst", AnalystOutput, system, user, ctx, verify, issuer_id=iid,
                               sample=s, temperature=temperature) for s in range(n_samples)]
            samples = [c.result.parsed if (c is not None and c.accepted) else None for c in calls]
            gate = sign_agreement_gate(samples, self.cfg.research.min_sign_agreement, n_samples)
            nid = self.note_id("fundamental", iid)
            self.register_llm_note(nid, calls)
            problems = [line for c in calls for line in self.failure_lines(c)
                        if c is None or not c.accepted]
            problems = list(dict.fromkeys(problems))
            if gate.abstain or gate.representative is None:
                note = self._note(nid, iid, "fundamental", calls, stance=0, confidence=0.0,
                                  thesis=f"Abstenção do analista: {gate.reason}.",
                                  key_risks=problems or [f"Abstenção: {gate.reason}."])
            else:
                rep: AnalystOutput = samples[gate.representative]  # type: ignore[assignment]
                quotes = {c.evidence_id: c.quote for c in rep.citations if c.quote}
                ev = [e for d in [*rep.drivers, *rep.risks] for e in d.evidence_ids]
                ev += [c.evidence_id for c in rep.citations]
                key_risks = ([f"Critério de saída: {k}" for k in rep.kill_criteria]
                             + [f"Lacuna de dados: {g}" for g in rep.data_gaps] + problems)
                if n_samples > 1:
                    key_risks.append("Portão de concordância de sinal aprovado "
                                     "(amostras independentes do analista).")
                note = self._note(
                    nid, iid, "fundamental", calls, stance=gate.stance,
                    confidence=gate.confidence, thesis=rep.thesis,
                    bull_points=[d.text for d in rep.drivers],
                    bear_points=[d.text for d in rep.risks],
                    catalysts=[Catalyst(description=c.description, expected_date=c.expected_date,
                                        direction=c.direction) for c in rep.catalysts],
                    key_risks=key_risks,
                    evidence=_evidence_refs(ev, self.fb, set(news_ids), quotes))
            self.analyst_notes[iid] = note
            self.notes.append(note)

    # ------------------------------------------------------------------ R4 debate + juiz
    def run_debates(self) -> None:
        ranked = []
        for iid, note in self.analyst_notes.items():
            az = self.alpha(iid)
            if note.stance != 0 and note.confidence > 0 and az is not None:
                ranked.append((-abs(az), iid))
        for _, iid in sorted(ranked)[: self.o.debate_top_n]:
            self._debate_one(iid)

    def _debate_one(self, iid: str) -> None:
        analyst = self.analyst_notes[iid]
        ctx_base, fact_ids, news_ids = self.analyst_context(iid)
        row = self.issuer_row(iid)
        items = [self.eligible[i] for i in news_ids]
        valid = set(fact_ids) | set(news_ids)
        dates, terms = self.news_dates(news_ids), self.allowed_terms(iid)
        facts_block, news_block = self.facts_block(fact_ids), format_news_block(items)
        prior = {e.ref_id for e in analyst.evidence}
        sides: dict[str, list[Driver]] = {}
        calls: list[_Call | None] = []
        problems: list[str] = []
        for side in ("bull", "bear"):
            task = f"debate_{side}"
            system, user = debate_prompt(side, row, facts_block, news_block, analyst.thesis,
                                         as_of=self.as_of, news_ids=news_ids)
            ctx = {**ctx_base, "task": task, "side": side,
                   "analyst_evidence": sorted(prior), "analyst_stance": analyst.stance}
            call = self.call(task, DebateOutput, system, user, ctx,
                             lambda out, s=side: verify_debate_output(
                                 out, self.fb, valid, self.as_of, side=s, issuer_id=iid,
                                 evidence_dates=dates, allowed_terms=terms),
                             issuer_id=iid)
            calls.append(call)
            if call is not None and call.accepted:
                sides[side] = list(call.result.parsed.arguments)  # type: ignore[union-attr]
            else:
                sides[side] = []
                problems += [f"Debate {side}: {line}" for line in self.failure_lines(call)]
        system, user = judge_prompt(
            row, facts_block, analyst.thesis,
            drivers_block(sides["bull"]) or "(argumentos indisponíveis ou rejeitados)",
            drivers_block(sides["bear"]) or "(argumentos indisponíveis ou rejeitados)",
            prior, as_of=self.as_of, analyst_stance=analyst.stance, news_block=news_block,
            news_ids=news_ids)
        ctx = {**ctx_base, "task": "judge", "analyst_stance": analyst.stance,
               "prior_evidence": sorted(prior),
               "bull": [d.model_dump() for d in sides["bull"]],
               "bear": [d.model_dump() for d in sides["bear"]]}
        judge = self.call("judge", JudgeOutput, system, user, ctx,
                          lambda out: verify_judge_output(
                              out, self.fb, valid, self.as_of, prior_evidence_ids=prior,
                              issuer_id=iid, evidence_dates=dates, allowed_terms=terms),
                          issuer_id=iid)
        calls.append(judge)
        nid = self.note_id("bull_bear_judge", iid)
        self.register_llm_note(nid, calls)
        bull_ev = [e for d in sides["bull"] for e in d.evidence_ids]
        bear_ev = [e for d in sides["bear"] for e in d.evidence_ids]
        if judge is not None and judge.accepted:
            out: JudgeOutput = judge.result.parsed  # type: ignore[assignment]
            stance = max(-2, min(2, analyst.stance + int(out.stance_change)))
            note = self._note(
                nid, iid, "bull_bear_judge", calls, stance=stance, confidence=analyst.confidence,
                thesis=f"{analyst.thesis} Juiz bull × bear: {out.rationale}",
                bull_points=[d.text for d in sides["bull"]],
                bear_points=[d.text for d in sides["bear"]],
                key_risks=problems + [f"Ajuste do juiz sobre a stance do analista: "
                                      f"{'sem mudança' if out.stance_change == 0 else 'um nível'}"],
                evidence=_evidence_refs(list(prior) + bull_ev + bear_ev + list(out.new_evidence_ids),
                                        self.fb, set(news_ids)))
        else:
            note = self._note(nid, iid, "bull_bear_judge", calls, stance=0, confidence=0.0,
                              thesis="Abstenção do juiz bull × bear; prevalece a nota do analista.",
                              bull_points=[d.text for d in sides["bull"]],
                              bear_points=[d.text for d in sides["bear"]],
                              key_risks=problems + self.failure_lines(judge))
        self.notes.append(note)

    # ------------------------------------------------------------------ R6 sentinela
    def run_short_risk(self) -> None:
        for iid in sorted(dict.fromkeys(str(i) for i in self.req.short_candidates)):
            rule, rule_reason = rule_short_verdict(self.req.squeeze, iid, self.cfg)
            self.rule_verdicts[iid] = rule
            row = self.issuer_row(iid)
            sq_ids = [f"{iid}.{m}" for m in ("si_pct_float", "days_to_cover", "borrow_fee",
                                             "squeeze_score") if f"{iid}.{m}" in self.fb.facts]
            base_ids = [f"{iid}.{m}" for m in ("ret_1m_usd", "ret_3m_usd", "vol_3m",
                                               "adtv_usd_mm", "mcap_usd_bn")
                        if f"{iid}.{m}" in self.fb.facts]
            fact_ids = sorted(set(sq_ids + base_ids))
            news_ids = self.news_ids_for(iid)
            items = [self.eligible[i] for i in news_ids]
            sq = self.req.squeeze
            sq_row = sq.loc[iid] if (sq is not None and iid in sq.index) else None
            bucket = (str(sq_row.get("bucket")) if sq_row is not None
                      and pd.notna(sq_row.get("bucket")) else "NA")
            fee = _finite(sq_row.get("borrow_fee")) if sq_row is not None else None
            squeeze_block = "\n".join([render_facts_block(self.fb, [iid], macro=False,
                                                          fact_ids=sq_ids),
                                       f"Faixa de squeeze calculada: {bucket}"])
            context = {"task": "short_risk", "issuer_id": iid, "as_of": self.as_of.isoformat(),
                       "bucket": bucket, "borrow_fee": fee,
                       "max_borrow_fee": float(self.cfg.shorting.max_borrow_fee),
                       "rule_verdict": rule, "facts": self.facts_values(fact_ids),
                       "news_ids": news_ids}
            system, user = short_risk_prompt(row, self.facts_block(base_ids), squeeze_block,
                                             format_news_block(items), as_of=self.as_of,
                                             rule_verdict=rule, news_ids=news_ids)
            valid = set(fact_ids) | set(news_ids)
            dates, terms = self.news_dates(news_ids), self.allowed_terms(iid)
            call = self.call("short_risk", ShortRiskOutput, system, user, context,
                             lambda out, v=valid, d=dates, i=iid, t=terms: verify_short_risk_output(
                                 out, self.fb, v, self.as_of, evidence_dates=d, issuer_id=i,
                                 allowed_terms=t), issuer_id=iid)
            nid = self.note_id("short_risk", iid)
            self.register_llm_note(nid, [call])
            if call is not None and call.accepted:
                out: ShortRiskOutput = call.result.parsed  # type: ignore[assignment]
                final = most_restrictive(rule, out.verdict)
                thesis = out.rationale
                rationale = f"Regra: {rule_reason} ({rule}). Sentinela de IA: {out.rationale}"
                key_risks = [f"Sinalização: {f}" for f in out.flags]
                evidence = _evidence_refs(out.evidence_ids, self.fb, set(news_ids))
                confidence = 1.0
            else:
                final = most_restrictive(rule, "caution")
                thesis = ("Sentinela de IA indisponível ou rejeitada; vale a regra determinística "
                          "com piso de cautela.")
                rationale = f"Regra: {rule_reason} ({rule}). {thesis}"
                key_risks = self.failure_lines(call)
                evidence = _evidence_refs(sq_ids, self.fb, set())
                confidence = 0.5
            note = self._note(nid, iid, "short_risk", [call], stance=0, confidence=confidence,
                              thesis=thesis, key_risks=key_risks + [f"Regra determinística: "
                                                                    f"{rule_reason}"],
                              squeeze=SqueezeAssessment(verdict=final, rationale=rationale),
                              evidence=evidence)
            self.notes.append(note)

    # ------------------------------------------------------------------ fechamento
    def finish(self) -> ResearchRun:
        n_calls = len(self.records)
        n_errors = sum(1 for r in self.records if not r.parse_ok)
        error_rate = n_errors / n_calls if n_calls else 0.0
        provider_failed = n_calls > 0 and error_rate > PROVIDER_FAILURE_RATE
        llm_notes = len(self.llm_note_ids)
        issues_rate = len(self.gate_failed_notes) / llm_notes if llm_notes else 0.0
        kill, reason = ai_kill_switch(issues_rate, provider_failed, self.injection_confirmed,
                                      self.o.eval_regressed)
        if self.budget_exhausted:
            self.events.append(f"Orçamento de chamadas de IA esgotado: {self.skipped_tasks} "
                               "tarefa(s) viraram abstenção.")
        lookahead = sorted(_safe_id(n) for n, rs in self.excluded.items()
                           if any("look-ahead" in r for r in rs))
        if lookahead:
            self.events.append("Notícias posteriores ao as_of descartadas (look-ahead): "
                               + ", ".join(lookahead) + ".")
        longs = [str(i) for i in self.req.long_candidates]
        views = (rule_views(self.rule_verdicts, self.cfg, long_candidates=longs) if kill
                 else notes_to_views(self.notes, self.cfg, long_candidates=longs))
        macro = list(self.macro)
        if kill or self.events:
            macro.append(MacroNote(
                note_id=self.note_id("governanca", "ia"), week=self.req.week,
                scope=GOVERNANCE_SCOPE, stance=0,
                regime="IA DESATIVADA (modo somente quant)" if kill else "IA ativa com ressalvas",
                summary=reason, risks=list(self.events),
                portfolio_implications=(["Visões de IA descartadas; mantidas apenas as restrições "
                                         "das regras determinísticas de short."] if kill else []),
                provider=GOVERNANCE_PROVIDER, model=None, prompt_version=PROMPT_VERSION,
                created_at=self.now, is_synthetic=self.fb.is_synthetic))
        notes = sorted(self.notes, key=lambda n: (n.issuer_id, _ROLE_ORDER.get(n.role, 9),
                                                  n.note_id))
        news = sorted(self.eligible.values(), key=lambda n: (n.published_at, n.news_id))
        pack = ResearchPack(week=self.req.week, snapshot_id=self.req.snapshot_id,
                            provider=self.p.name, notes=notes, macro=macro, views=views,
                            news=news, is_synthetic=self.fb.is_synthetic)
        # Hash dos registros DESTA execução (o arquivo do ledger pode acumular execuções;
        # anexar outra execução depois não pode mudar o hash vinculado a esta aprovação).
        ledger_hash = sha256_obj([r.model_dump(mode="json") for r in self.records])
        return ResearchRun(
            pack=pack, records=list(self.records), ledger_hash=ledger_hash,
            calls_hash=calls_digest(self.records), kill_switch=kill, kill_reason=reason,
            excluded_news={k: list(v) for k, v in sorted(self.excluded.items())},
            rule_verdicts=dict(sorted(self.rule_verdicts.items())),
            notes_issues_rate=round(issues_rate, 6), provider_error_rate=round(error_rate, 6),
            injection_confirmed=self.injection_confirmed, budget_exhausted=self.budget_exhausted,
            governance_events=list(self.events))


def run_research(req: ResearchRequest, provider: LLMProvider, cfg: FundConfig, *,
                 ledger_path: str | None = None, max_calls: int = 400,
                 eval_regressed: bool = False,
                 clock: Callable[[], datetime] | None = None) -> ResearchRun:
    """Atalho: executa a pesquisa e (opcionalmente) grava o ledger em ``ledger_path``."""
    ledger = LLMCallLedger(ledger_path) if ledger_path else None
    orch = ResearchOrchestrator(provider, cfg, max_calls=max_calls, ledger=ledger, clock=clock,
                                eval_regressed=eval_regressed)
    return orch.execute(req)


def research_hash_with_ledger(run: ResearchRun) -> str:
    """Hash da pesquisa incluindo o ledger de chamadas (para o hash de aprovação)."""
    return combine_hashes(run.pack.research_hash(), run.ledger_hash)
