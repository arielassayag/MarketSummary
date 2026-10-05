"""Demonstração offline completa do CDP — Cabra da Peste (DADOS SIMULADOS).

Roda o mesmo caminho operacional das rotinas reais (``Runtime``), sem internet e sem chaves de
API, sobre um mercado sintético determinístico:

1. no primeiro pregão de cada semana: ``weekly prepare`` → a mente ``demo`` escreve
   ``inputs/research_pack.json`` e ``inputs/pm_decision.json`` → ``validate`` → ``weekly decide``
   (decisão autônoma sob gates determinísticos e relatório semanal) → ``tese prepare`` → a
   mente ``demo`` escreve ``tese/tese.json`` (só fatos citados) → ``tese publish``;
2. em cada pregão: ``daily close`` (execução MOC da decisão da semana, marcação, risco,
   atribuição e registro encadeado por hash) → comentário da mente ``demo`` → ``daily publish``;
3. ``verify`` de toda a trilha.

Um relógio lógico (pregão às 11h e decisão às 15h de Brasília) torna a execução reprodutível.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import SIMULATED_DATA_NOTICE
from ..calendar import first_session_of_week, is_rebalance_day, is_session
from ..config import FundConfig, load_config
from ..market import MarketData
from .runtime import Runtime

DEMO_MIND = "demo"
DEMO_SEED = 7
DEMO_HISTORY_START = date(2023, 1, 2)
DEMO_FIRST_WEEK = date(2024, 3, 4)
BRT = ZoneInfo("America/Sao_Paulo")


class DemoStore:
    """Fonte sem look-ahead sobre o mercado sintético: ``load(as_of)`` corta em ``as_of``."""

    def __init__(self, md: MarketData) -> None:
        self.md = md

    def load(self, as_of: date | None = None, verify: bool = True) -> MarketData:
        if as_of is None:
            return self.md
        cut = self.md.truncate(as_of)
        last = cut.close.index.max()
        real_as_of = min(as_of, last.date()) if last is not None else as_of
        return replace(cut, manifest=cut.manifest.model_copy(update={"as_of": real_as_of}))

    def last_date(self) -> date:
        return self.md.as_of

    def verify_chain(self) -> tuple[bool, list[str]]:
        return True, [f"mercado sintético em memória ({SIMULATED_DATA_NOTICE})"]


class _Clock:
    def __init__(self) -> None:
        self.at = datetime(2000, 1, 1, tzinfo=BRT)

    def set(self, d: date, hhmm: time) -> None:
        self.at = datetime.combine(d, hhmm, tzinfo=BRT)

    def __call__(self) -> datetime:
        return self.at


def demo_sessions(days: int, first_week: date = DEMO_FIRST_WEEK) -> list[date]:
    """``days`` pregões da B3 a partir do primeiro pregão da semana ``first_week``."""
    if days < 1:
        raise ValueError("A demonstração precisa de pelo menos um pregão.")
    d = first_session_of_week(first_week)
    out: list[date] = []
    while len(out) < days:
        if is_session(d, "BVMF"):
            out.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    return out


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, default=str),
                    encoding="utf-8")


def write_demo_inputs(rt: Runtime, week: date) -> dict[str, str]:
    """A mente ``demo`` escreve o pacote de pesquisa e a decisão do PM da semana (determinístico)."""
    from ..research.pm_agent import example_research_pack, run_pm_agent
    from ..research.providers.demo import DemoResearchProvider

    _md, _info, _ctx, _fb, pmctx = rt._week_state(week)
    inputs = rt.week_dir(week) / "inputs"
    pack = example_research_pack(pmctx, DEMO_MIND)
    _write_json(inputs / "research_pack.json", pack)
    out, issues = run_pm_agent(DemoResearchProvider(), pmctx, now=rt.now())
    _write_json(inputs / "pm_decision.json", out.model_dump(mode="json"))
    return {"research_pack": str(inputs / "research_pack.json"),
            "pm_decision": str(inputs / "pm_decision.json"), "pm_issues": "; ".join(issues)}


def write_demo_commentary(rt: Runtime, session: date) -> Path | None:
    """A mente ``demo`` escreve ``comentario.json`` (template verificado, só fatos do dia)."""
    from ..research.commentary import COMMENTARY_JSON, example_commentary

    rec = rt.track().get(session)
    if rec is None:
        return None
    fb, _history = rt._daily_factbook(session, rec)
    path = rt.daily_dir(session) / COMMENTARY_JSON
    _write_json(path, example_commentary(fb, DEMO_MIND))
    return path


def write_demo_thesis(rt: Runtime, week: date) -> Path:
    """A mente ``demo`` escreve ``tese.json`` (tese automática do código, só fatos citados)."""
    from .tese import TESE_JSON, load_prepared, template_thesis, thesis_dir

    folder = thesis_dir(rt.book_root, week)
    fb, analysis = load_prepared(folder)
    path = folder / TESE_JSON
    _write_json(path, template_thesis(analysis, fb, DEMO_MIND).model_dump(mode="json"))
    return path


def run_demo(out: Path | str, days: int = 5, *, seed: int = DEMO_SEED,
             first_week: date = DEMO_FIRST_WEEK, cfg: FundConfig | None = None) -> dict:
    """Executa a demonstração completa em ``out`` (recusa reutilizar uma pasta com livro)."""
    from ..data.synthetic import make_synthetic_market

    out = Path(out)
    if (out / "book").exists():
        raise FileExistsError(f"Já existe uma demonstração em {out}: use outra pasta (--out).")
    cfg = cfg or load_config()
    sessions = demo_sessions(days, first_week)
    md = make_synthetic_market(seed=seed, start=DEMO_HISTORY_START, as_of=sessions[-1])
    clock = _Clock()
    # ``teses_root=None``: a demonstração nunca adota rascunhos de tese do repositório.
    rt = Runtime(cfg=cfg, book_root=out / "book", market_root=out / "market",
                 reports_root=out / "reports", store_override=DemoStore(md), clock=clock,
                 teses_root=None)
    log: list[dict] = []
    for s in sessions:
        if is_rebalance_day(s):
            clock.set(s, time(11, 0))
            prep = rt.weekly_prepare(s, mind=DEMO_MIND, live=False)
            clock.set(s, time(12, 0))
            inputs = write_demo_inputs(rt, s)
            ok, issues = rt.validate_inputs(s, mind=DEMO_MIND)
            clock.set(s, time(15, 0))
            dec = rt.weekly_decide(s, mind=DEMO_MIND)
            clock.set(s, time(15, 30))
            prep_tese = rt.thesis_prepare(s)
            write_demo_thesis(rt, s)
            tese = rt.thesis_publish(s)
            log.append({"semana": s, "briefing": prep["briefing"], "entradas_validas": ok,
                        "apontamentos": issues, "pm": inputs.get("pm_issues", ""),
                        "caminho": dec["caminho"], "postura": dec["postura"],
                        "vol_ex_ante": dec["vol_ex_ante"], "n_long": dec["n_long"],
                        "n_short": dec["n_short"], "relatorio": dec["relatorio"]["md"],
                        "tese": tese["autoria"], "tese_apontamentos": tese["problemas"],
                        "tese_rascunho_adotado": prep_tese["rascunho_adotado"]})
        clock.set(s, time(19, 20))
        close = rt.daily_close(s, live=False, mind=DEMO_MIND)
        entry: dict = {"data": s, "status": close.get("status")}
        if close.get("status") == "registrado":
            write_demo_commentary(rt, s)
            pub = rt.daily_publish(s)
            entry.update({"nav_usd": close["nav_usd"], "retorno_dia": close["retorno_dia"],
                          "relatorio": pub["relatorio"]["md"],
                          "comentario_da_mente": pub["comentario_da_mente"]})
        log.append(entry)
    ok, msgs = rt.verify_all()
    last = rt.track().last()
    summary = {
        "aviso": f"{SIMULATED_DATA_NOTICE} — demonstração offline (mercado sintético).",
        "pasta": str(out), "pregoes": [s.isoformat() for s in sessions],
        "nav_final_usd": last.nav_end_usd if last else None,
        "registros": len(rt.track().records()), "integridade": ok, "verificacao": msgs,
        "etapas": log,
    }
    _write_json(out / "demo_summary.json", summary)
    return summary


__all__ = ["DEMO_FIRST_WEEK", "DEMO_MIND", "DemoStore", "demo_sessions", "run_demo",
           "write_demo_commentary", "write_demo_inputs", "write_demo_thesis"]
