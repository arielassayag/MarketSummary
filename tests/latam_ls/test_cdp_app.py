"""Testes do app Streamlit do CDP — Cabra da Peste (offline, DADOS SIMULADOS).

- Livro vazio: todas as páginas mostram estados vazios, sem exceções e sem criar pastas.
- Livro-fixture montado com os módulos reais: mercado sintético → ``MarketStore`` → semana
  (pesquisa demo, decisão do PM pela rota de arquivo, decisão autônoma) → 3 registros diários com
  sombra só-quant → relatórios diário/semanal. Cada página renderiza; a verificação de integridade
  mostra sucesso; o KILL SWITCH grava o arquivo e o evento de auditoria.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml
from streamlit.testing.v1 import AppTest

from latam_ls.audit import AuditLog
from latam_ls.config import FundConfig, load_config
from latam_ls.contracts import (
    DailyPosition,
    DailyRecord,
    DailyRisk,
    LineType,
    OptimizerDiagnostics,
    PositionTarget,
    Proposal,
    RiskSummary,
    Side,
)
from latam_ls.ui import data, fmt
from latam_ls.ui.app import PAGES
from latam_ls.ui.settings import AppPaths

REPO = Path(__file__).resolve().parents[2]
W1 = date(2026, 10, 5)
SESSIONS = (date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7))
MIND = "claude-code"
T_RESEARCH = datetime(2026, 10, 5, 14, 30, tzinfo=UTC)
T_CREATED = datetime(2026, 10, 5, 16, 0, tzinfo=UTC)
T_DECIDED = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)  # 14h de Brasília (antes das 16h30)
PAGE_KEYS = [p.key for p in PAGES]
TIMEOUT = 90
BANNER = "DADOS SIMULADOS — artefatos sintéticos carregados"


# ==========================================================
# Livro-fixture (módulos reais do pipeline)
# ==========================================================

def build_fixture_book(root: Path) -> SimpleNamespace:
    """Monta book/, reports/, market/ e fund.yaml em ``root`` com o pipeline real (offline)."""
    from latam_ls.data.snapshot import write_snapshot
    from latam_ls.data.store import MarketStore
    from latam_ls.data.synthetic import make_synthetic_market
    from latam_ls.hashing import sha256_file
    from latam_ls.research.agents import ResearchRequest, run_research
    from latam_ls.research.commentary import (
        build_daily_factbook,
        example_commentary,
        load_commentary_file,
    )
    from latam_ls.research.factbook import build_factbook
    from latam_ls.research.pm_agent import (
        PMContext,
        example_pm_decision,
        load_pm_decision_file,
        pm_factbook,
        to_bundle,
        write_briefing_bundle,
    )
    from latam_ls.research.providers.demo import DemoResearchProvider
    from latam_ls.workflow.autonomy import make_autonomous_decision
    from latam_ls.workflow.book import Book
    from latam_ls.workflow.daily import SHADOW_RECORD_EVENT, DailyRunner, PendingExecution
    from latam_ls.workflow.reports import (
        render_daily_report,
        render_weekly_report,
        write_report_files,
    )
    from latam_ls.workflow.track_record import TrackRecord
    from latam_ls.workflow.weekly import prepare_week, run_weekly_decision

    root.mkdir(parents=True, exist_ok=True)
    cfg = load_config(REPO / "configs/latam_ls/fund.yaml").with_overrides(
        {"risk_model": {"history_days": 300}})
    cfg_path = root / "fund.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg.model_dump(mode="json"), allow_unicode=True,
                                       sort_keys=False), encoding="utf-8")
    assert load_config(cfg_path).config_hash() == cfg.config_hash()

    md = make_synthetic_market(seed=7, start=date(2025, 3, 3), as_of=SESSIONS[-1])
    write_snapshot(md, root / "snapshot")
    store = MarketStore(root / "market", cfg=cfg)
    store.init_base(root / "snapshot")

    book_root, reports = root / "book", root / "reports"
    book = Book(book_root, cfg)
    md_w = store.load(as_of=date(2026, 10, 2))
    ctx = prepare_week(md_w, cfg, W1, nav=cfg.fund.inception_nav_usd, drawdown=0.0)
    alpha = ctx.alpha.alpha.dropna()
    can_short = ctx.sides["can_short"].reindex(alpha.index).fillna(False).astype(bool)
    longs = list(alpha.sort_values(ascending=False).head(12).index)
    shorts = list(alpha[can_short].sort_values().head(12).index)
    fb = build_factbook(ctx.panel, ctx.md, sorted(set(longs) | set(shorts)),
                        alpha_z=ctx.alpha.composite_z, signal_z=ctx.alpha.signal_z,
                        squeeze=ctx.squeeze, betas=ctx.betas,
                        specific_vol=ctx.model.specific_vol, snapshot_id=ctx.snapshot_id)
    issuers = ctx.panel.assets[["issuer_name", "country", "sector"]]
    week_dir = book_root / W1.isoformat()
    req = ResearchRequest(week=W1, as_of=md_w.as_of, snapshot_id=ctx.snapshot_id,
                          long_candidates=longs, short_candidates=shorts,
                          countries=sorted(set(issuers["country"])), issuers=issuers,
                          factbook=fb, news=list(md_w.news), squeeze=ctx.squeeze,
                          alpha_z=ctx.alpha.composite_z)
    run = run_research(req, DemoResearchProvider(), cfg, ledger_path=str(week_dir / "research"),
                       clock=lambda: T_RESEARCH)
    pack = run.pack.model_copy(update={"mind": MIND})
    pmctx = PMContext(
        week=W1, as_of=md_w.as_of, fund_name=cfg.fund.name, factbook=fb,
        universe_issuers=issuers, quant_alpha_z=ctx.alpha.composite_z,
        quant_candidates_long=longs, quant_candidates_short=shorts, current_book=None,
        previous_views=[], previous_pm_output=None, research_notes=list(pack.notes),
        macro_notes=list(pack.macro), drawdown=0.0, realized_vol_21d=None,
        track_record_facts={}, kill_switch=False, cfg=cfg, analysis_ts=T_RESEARCH)
    write_briefing_bundle(pmctx, week_dir / "briefing", mind_hint=MIND)
    inputs = week_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "pm_decision.json").write_text(
        json.dumps(example_pm_decision(pmctx, MIND), ensure_ascii=False, indent=2),
        encoding="utf-8")
    out, pm_issues = load_pm_decision_file(inputs / "pm_decision.json", pmctx)
    pfb = pm_factbook(pmctx)
    bundle = to_bundle(out, cfg, 0.0, factbook=pfb)
    outcome = run_weekly_decision(ctx, pack, bundle, version=book.next_version(W1))
    # Carimbos fixos (fixture determinística): proposta antes da decisão, decisão antes do prazo.
    final = outcome.final.model_copy(update={"created_at": T_CREATED})
    shadow = outcome.shadow_quant.model_copy(update={"created_at": T_CREATED})
    book.save_research_pack(pack, actor=MIND)
    book.save_proposal(final)
    shadow_path = week_dir / "shadow_quant.json"
    shadow_path.write_text(json.dumps(shadow.model_dump(mode="json"), ensure_ascii=False,
                                      indent=2, sort_keys=True), encoding="utf-8")
    book.audit.append("SHADOW_QUANT", "CDP", {"sha256": sha256_file(shadow_path)},
                      summary="Carteira-sombra só-quant gravada.", week=W1)
    d0 = outcome.decision
    decision = make_autonomous_decision(
        final, research_hash=outcome.research_hash, pm_decision_hash=bundle.pm_output_hash,
        rationale=d0.rationale, journal=d0.journal, conviction=d0.conviction,
        decided_at=T_DECIDED, audit_head_hash=book.audit_head()).model_copy(
        update={"mind": MIND})
    book.save_decision(decision)
    (week_dir / "attempts.json").write_text(json.dumps(
        {"path": outcome.path_taken, "attempts": outcome.attempts, "input_issues": pm_issues},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_txt, html = render_weekly_report(
        W1, final, decision, out, None, [], list(pack.views), [], shadow, cfg.fund.name,
        factbook=pfb, cfg=cfg, attempts=outcome.attempts, path_taken=outcome.path_taken)
    write_report_files(reports / "weekly" / W1.isoformat(), md_txt, html)

    track = TrackRecord(book_root / "track_record")
    shadow_track = TrackRecord(book_root / "track_record_shadow", audit_event=SHADOW_RECORD_EVENT)
    runner = DailyRunner(cfg, store, book, track, shadow_track=shadow_track)
    history: list[DailyRecord] = []
    for i, d in enumerate(SESSIONS):
        pending = PendingExecution(final, decision, shadow) if i == 0 else None
        rec = runner.run_session(d, pending=pending).record
        fbd = build_daily_factbook(rec, history, cfg=cfg)
        ddir = reports / "daily" / d.isoformat()
        ddir.mkdir(parents=True, exist_ok=True)
        (ddir / "comentario.json").write_text(
            json.dumps(example_commentary(fbd, MIND), ensure_ascii=False), encoding="utf-8")
        commentary, _ = load_commentary_file(ddir / "comentario.json", fbd, record=rec)
        mdr, htmlr = render_daily_report(rec, history, commentary, cfg.fund.name, cfg=cfg)
        write_report_files(ddir, mdr, htmlr)
        history.append(rec)
    return SimpleNamespace(root=root, book=book_root, reports=reports, market=root / "market",
                           config=cfg_path, cfg=cfg, records=history, decision=decision,
                           proposal=final, shadow=shadow)


@pytest.fixture(scope="module")
def fixture_book(tmp_path_factory) -> SimpleNamespace:
    return build_fixture_book(tmp_path_factory.mktemp("cdp_app") / "fx")


def _env(monkeypatch, book: Path, reports: Path, config: Path, market: Path) -> None:
    monkeypatch.setenv("CDP_BOOK_DIR", str(book))
    monkeypatch.setenv("CDP_REPORTS_DIR", str(reports))
    monkeypatch.setenv("CDP_CONFIG", str(config))
    monkeypatch.setenv("CDP_MARKET_DIR", str(market))
    monkeypatch.setenv("CDP_AGENTS_MD", str(REPO / "AGENTS.md"))


@pytest.fixture
def fx_env(monkeypatch, fixture_book) -> SimpleNamespace:
    fb = fixture_book
    _env(monkeypatch, fb.book, fb.reports, fb.config, fb.market)
    return fb


def page_app(key: str) -> AppTest:
    at = AppTest.from_string(f"from latam_ls.ui.app import run_page\nrun_page({key!r})\n",
                             default_timeout=TIMEOUT)
    return at.run()


def _texts(at: AppTest) -> str:
    parts: list[str] = []
    for kind in ("markdown", "caption", "info", "success", "warning", "error", "subheader"):
        parts += [str(e.value) for e in getattr(at, kind)]
    parts += [f"{m.label}={m.value}|{m.delta}" for m in at.metric]
    return re.sub(r"\\(.)", r"\1", "\n".join(parts))  # texto como exibido (sem escapes)


def _no_exceptions(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]


# ==========================================================
# Livro vazio (antes da inception)
# ==========================================================

@pytest.mark.parametrize("key", PAGE_KEYS)
def test_pages_render_empty_states_without_creating_dirs(key, tmp_path, monkeypatch):
    base = tmp_path / "vazio"
    _env(monkeypatch, base / "book", base / "reports", REPO / "configs/latam_ls/fund.yaml",
         base / "market")
    at = page_app(key)
    _no_exceptions(at)
    text = _texts(at)
    assert "CDP — Cabra da Peste" in text
    assert BANNER not in text  # nada sintético foi carregado
    if key != "auditoria":
        assert at.info, "página sem estado vazio explicativo"
    assert not base.exists(), "o app não pode criar pastas ao apenas ler"


def test_main_app_with_navigation_renders_default_page_empty(tmp_path, monkeypatch):
    base = tmp_path / "vazio"
    _env(monkeypatch, base / "book", base / "reports", REPO / "configs/latam_ls/fund.yaml",
         base / "market")
    at = AppTest.from_file(str(REPO / "cdp_app.py"), default_timeout=TIMEOUT).run()
    _no_exceptions(at)
    assert "Track record ainda não iniciado" in _texts(at)


def test_invalid_config_falls_back_to_defaults_with_warning(tmp_path, monkeypatch):
    bad = tmp_path / "fund.yaml"
    bad.write_text("risk: [isto não é um mapa", encoding="utf-8")
    _env(monkeypatch, tmp_path / "book", tmp_path / "reports", bad, tmp_path / "market")
    at = page_app("auditoria")
    _no_exceptions(at)
    assert any("padrões do código" in str(w.value) for w in at.warning)


# ==========================================================
# Livro-fixture
# ==========================================================

def test_fixture_book_is_consistent(fixture_book):
    fb = fixture_book
    assert [r.date for r in fb.records] == list(SESSIONS)
    assert fb.decision.mind == MIND
    for r in data.verify_track_integrity(fb.book) + data.verify_book_integrity(fb.book):
        assert r.ok, (r.label, r.messages)


def test_main_app_navigation_with_fixture(fx_env):
    at = AppTest.from_file(str(REPO / "cdp_app.py"), default_timeout=TIMEOUT).run()
    _no_exceptions(at)
    text = _texts(at)
    assert BANNER in text and "paper trading com preços reais" in text
    last = fx_env.records[-1]
    assert any(m.value == fmt.usd_mm(last.nav_end_usd) for m in at.metric)


@pytest.mark.parametrize("key", PAGE_KEYS)
def test_each_page_renders_with_fixture(key, fx_env):
    at = page_app(key)
    _no_exceptions(at)
    text = _texts(at)
    assert BANNER in text
    last = fx_env.records[-1]
    if key == "visao-geral":
        assert any(m.label == "NAV" and m.value == fmt.usd_mm(last.nav_end_usd)
                   for m in at.metric)
        assert any(m.label == "Retorno do dia" and m.value == fmt.pct(last.ret, signed=True)
                   for m in at.metric)
        assert "Comentário do dia :violet-badge" in text  # comentário da mente com selo IA
        assert "Próximos eventos" in text
    elif key == "track-record":
        assert "Registros diários" in text and len(at.dataframe) >= 2
    elif key == "atribuicao":
        assert "Valor agregado pelo PM de IA" in text
    elif key == "risco":
        assert any(m.label == "Vol ex-ante (total)"
                   and m.value == fmt.pct(last.risk.ex_ante_vol) for m in at.metric)
        assert "Monitor de short squeeze" in text
    elif key == "posicoes":
        assert any(m.label == "Linhas" and m.value == str(len(last.positions))
                   for m in at.metric)
    elif key == "decisoes":
        assert MIND in text and "Caminho percorrido" in text
    elif key == "pesquisa":
        assert ":violet-badge[:material/smart_toy: IA]" in text and MIND in text
    elif key == "relatorios":
        assert at.selectbox(key="rep_choice").value.startswith("Diário — 07/10/2026")
    elif key == "auditoria":
        assert any("Cadeia íntegra" in str(s.value) for s in at.success)


def test_decision_page_shows_autonomous_decision_hashes(fx_env):
    at = page_app("decisoes")
    _no_exceptions(at)
    tables = [df.value for df in at.dataframe]
    decision_tbl = next(t for t in tables if "Item" in t.columns)
    values = dict(zip(decision_tbl["Item"], decision_tbl["Valor"], strict=False))
    assert values["Modo"] == "AUTONOMOUS" and values["Mente"] == MIND
    assert values["Assinada por"] == "CDP — Cabra da Peste (PM autônomo)"
    hashes = next(t for t in tables if "Hash" in t.columns)
    d = fx_env.decision
    assert set(hashes["Valor"]) >= {d.approval_hash, d.proposal_hash, d.pm_decision_hash,
                                    d.risk_gate_hash, d.config_hash}


def test_track_record_integrity_button_shows_success(fx_env):
    at = page_app("track-record")
    at.button(key="verify_track").click().run()
    _no_exceptions(at)
    assert not at.error
    labels = [str(s.value) for s in at.success]
    assert any("Track record do CDP: íntegro" in s for s in labels)
    assert any("Sombra só-quant: íntegro" in s for s in labels)
    assert any("Trilha de auditoria: íntegro" in s for s in labels)


def test_audit_page_full_verification_success(fx_env):
    at = page_app("auditoria")
    at.button(key="verify_book").click().run()
    _no_exceptions(at)
    assert not at.error
    assert any("Livro × trilha" in str(s.value) for s in at.success)


def test_attribution_period_selector_and_custom_range(fx_env):
    at = page_app("atribuicao")
    at.segmented_control(key="attr_period").set_value("Dia").run()
    _no_exceptions(at)
    assert "Período: 07/10/2026 a 07/10/2026" in _texts(at)
    at.segmented_control(key="attr_period").set_value("Personalizado").run()
    at.date_input(key="attr_custom").set_value((SESSIONS[1], SESSIONS[2])).run()
    _no_exceptions(at)
    assert "Período: 06/10/2026 a 07/10/2026 · 2 pregão(ões)" in _texts(at)


def test_positions_filters_and_history(fx_env):
    at = page_app("posicoes")
    at.multiselect(key="pos_side").set_value(["SHORT"]).run()
    _no_exceptions(at)
    n_short = sum(1 for p in fx_env.records[-1].positions if p.side == Side.SHORT)
    assert any(m.label == "Linhas" and m.value == str(n_short) for m in at.metric)
    iid = fx_env.records[-1].positions[0].issuer_id
    at.selectbox(key="pos_issuer").set_value(iid).run()
    _no_exceptions(at)


def test_reports_page_switches_to_weekly(fx_env):
    at = page_app("relatorios")
    at.segmented_control(key="rep_kind").set_value("Semanais").run()
    _no_exceptions(at)
    assert at.selectbox(key="rep_choice").value == "Semanal — 05/10/2026"


def test_research_page_filters_notes(fx_env):
    at = page_app("pesquisa")
    sb = at.selectbox(key="res_issuer")
    sb.set_value(sb.options[1]).run()
    _no_exceptions(at)


# ==========================================================
# KILL SWITCH (única escrita) e integridade adulterada
# ==========================================================

def _copy_fixture(fx: SimpleNamespace, dest: Path) -> SimpleNamespace:
    shutil.copytree(fx.root, dest)
    return SimpleNamespace(book=dest / "book", reports=dest / "reports",
                           config=dest / "fund.yaml", market=dest / "market")


def test_kill_switch_on_and_off_writes_file_and_audit_events(fixture_book, tmp_path,
                                                             monkeypatch):
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    n0 = len(AuditLog(c.book / "audit_log.jsonl").events())
    at = page_app("auditoria")
    reason = "Teste de emergência <script>alert(1)</script> [x](javascript:alert(1))"
    at.text_area(key="ks_reason").input(reason)
    at.text_input(key="ks_by").input("Operador de risco")
    at.checkbox(key="ks_confirm").check()
    at.button(key="ks_submit").click().run()
    _no_exceptions(at)
    ks_file = c.book / "KILL_SWITCH"
    assert ks_file.exists()
    payload = json.loads(ks_file.read_text(encoding="utf-8"))
    assert payload["reason"] == reason and payload["by"] == "Operador de risco"
    assert payload.get("created_at") or payload.get("at")
    events = AuditLog(c.book / "audit_log.jsonl").events()
    assert len(events) == n0 + 1 and events[-1].event_type == "KILL_SWITCH_ON"
    assert events[-1].actor == "Operador de risco"
    assert AuditLog(c.book / "audit_log.jsonl").verify_chain()[0]
    # Banner e status aparecem; o texto digitado é exibido escapado (nunca como HTML).
    errors = [str(e.value) for e in at.error]
    assert any("KILL SWITCH LIGADO" in e for e in errors)
    assert all("<script>" not in e for e in errors)
    assert any("\\<script\\>" in e for e in errors)
    assert any("registrado na trilha" in str(s.value) for s in at.success)

    at.text_area(key="ks_reason").input("Fim do teste de emergência")
    at.text_input(key="ks_by").input("Operador de risco")
    at.checkbox(key="ks_confirm").check()
    at.button(key="ks_submit").click().run()
    _no_exceptions(at)
    assert not ks_file.exists()
    events = AuditLog(c.book / "audit_log.jsonl").events()
    assert events[-1].event_type == "KILL_SWITCH_OFF" and len(events) == n0 + 2
    assert all(r.ok for r in data.verify_book_integrity(c.book))


def test_kill_switch_requires_reason_and_confirmation(fixture_book, tmp_path, monkeypatch):
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    n0 = len(AuditLog(c.book / "audit_log.jsonl").events())
    at = page_app("auditoria")
    at.text_area(key="ks_reason").input("curto")
    at.text_input(key="ks_by").input("Op")
    at.button(key="ks_submit").click().run()
    _no_exceptions(at)
    assert not (c.book / "KILL_SWITCH").exists()
    assert len(AuditLog(c.book / "audit_log.jsonl").events()) == n0
    assert any("Ação não executada" in str(e.value) for e in at.error)


def test_tampered_record_is_reported_not_crashed(fixture_book, tmp_path, monkeypatch):
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    path = c.book / "track_record" / "records" / f"{SESSIONS[1].isoformat()}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["nav_end_usd"] = raw["nav_end_usd"] + 1_000_000.0
    path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    at = page_app("track-record")
    at.button(key="verify_track").click().run()
    _no_exceptions(at)
    assert any("FALHA DE INTEGRIDADE" in str(e.value) for e in at.error)
    results = data.verify_track_integrity(c.book)
    assert not results[0].ok and any("adulterado" in m for m in results[0].messages)


# ==========================================================
# Funções puras (data, fmt)
# ==========================================================

def test_fingerprint_tracks_changes_and_absence(tmp_path):
    missing = data.fingerprint(tmp_path / "nada")
    assert missing == data.fingerprint(tmp_path / "nada")
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.json").write_text("1", encoding="utf-8")
    raw = d / "raw"
    raw.mkdir()
    f1 = data.fingerprint(d)
    (raw / "x.json").write_text("ignorado", encoding="utf-8")
    assert data.fingerprint(d) == f1  # respostas brutas de IA não invalidam o cache
    (d / "b.json").write_text("2", encoding="utf-8")
    assert data.fingerprint(d) != f1


def test_compound_and_missing_never_zero():
    assert data.compound([0.01, -0.02]) == pytest.approx(1.01 * 0.98 - 1)
    assert data.compound([]) is None
    assert data.compound([0.01, None]) is None
    assert data.compound([0.01, float("nan")]) is None


def test_period_bounds():
    ds = [date(2026, 9, 28), date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 7)]
    assert data.period_bounds("Dia", ds) == (date(2026, 10, 7), date(2026, 10, 7))
    assert data.period_bounds("Semana", ds) == (date(2026, 10, 5), date(2026, 10, 7))
    assert data.period_bounds("MTD", ds) == (date(2026, 10, 1), date(2026, 10, 7))
    assert data.period_bounds("YTD", ds) == (date(2026, 1, 1), date(2026, 10, 7))
    assert data.period_bounds("ITD", ds) == (date(2026, 9, 28), date(2026, 10, 7))
    custom = (date(2026, 12, 1), date(2026, 1, 1))
    assert data.period_bounds("Personalizado", ds, custom) == (date(2026, 9, 28),
                                                              date(2026, 10, 7))
    assert data.period_bounds("ITD", []) is None


def test_render_facts_and_escaping():
    facts = {"SIM001.alpha_z": "+1,20"}
    assert data.render_facts("z {{fact:SIM001.alpha_z}} e {{ fact:X }}", facts) == (
        "z +1,20 e [fato X indisponível]")
    esc = fmt.escape_md("<script>alert(1)</script> ![img](http://x) **b** $x$")
    assert "<script>" not in esc and "\\<script\\>" in esc
    assert "\\!\\[img\\]\\(http://x\\)" in esc.replace("\\.", ".")
    assert "\\$x\\$" in esc
    assert fmt.code("a`b\nc") == "`a'b c`"
    md = fmt.report_md("# Título\nUS$ 1,00 e `US$ 2`\n```\nUS$ 3\n```", demote=2)
    assert md.splitlines()[0] == "### Título" and "US\\$ 1,00" in md
    assert "`US$ 2`" in md and "\nUS$ 3\n" in md


def test_formatting_ptbr():
    assert fmt.pct(0.0125, signed=True) == "+1,25%"
    assert fmt.usd_mm(100_383_005.6) == "USD 100,38 mm"
    assert fmt.num(1234.5, 2) == "1.234,50"
    assert fmt.bps(0.00125) == "+12,5 bps"
    assert fmt.pct(None) == fmt.pct(float("nan")) == "n/d"
    assert fmt.days(1.26) == "1,3 d"
    assert fmt.short_hash("abcdef0123456789", 6) == "abcdef…" and fmt.short_hash(None) == "n/d"


def test_status_against_mandate():
    cfg = FundConfig()
    assert fmt.vol_status(0.05, cfg).color == "green"
    assert fmt.vol_status(0.02, cfg).color == "orange"
    assert fmt.vol_status(0.08, cfg).color == "red"
    assert fmt.vol_status(None, cfg).color == "gray"
    assert fmt.ladder_status(-0.01, cfg).label == "normal"
    assert fmt.ladder_status(-0.03, cfg).label == "stop suave"
    assert fmt.ladder_status(-0.06, cfg).label == "stop duro"
    assert fmt.ladder_status(-0.08, cfg).label == "stop-out"
    assert fmt.limit_status(0.02, 0.01).color == "red"
    assert fmt.limit_status(-0.005, 0.01).color == "green"
    assert fmt.max_status(2.0, 3.0, fmt.days).label == "teto 3,0 d"


def test_validate_kill_switch_request():
    assert data.validate_kill_switch_request(True, "motivo suficiente", "Ana", True, False) == []
    probs = data.validate_kill_switch_request(True, "curto", "", False, True)
    assert len(probs) == 4
    assert data.validate_kill_switch_request(False, "desligando agora", "Ana", True, False) == [
        "O kill switch já está DESLIGADO."]


def test_kill_switch_state_reads_runtime_payload(tmp_path):
    assert not data.kill_switch_state(tmp_path).active
    (tmp_path / "KILL_SWITCH").write_text(json.dumps(
        {"on": True, "reason": "teste", "by": "Ana", "at": "2026-10-05T12:00:00+00:00"}),
        encoding="utf-8")
    ks = data.kill_switch_state(tmp_path)
    assert ks.active and ks.reason == "teste" and ks.created_at.startswith("2026-10-05")
    (tmp_path / "KILL_SWITCH").write_text("não é json", encoding="utf-8")
    ks = data.kill_switch_state(tmp_path)
    assert ks.active and ks.error


def _pt(iid: str, w: float) -> PositionTarget:
    return PositionTarget(issuer_id=iid, name=f"Nome {iid}", country="BR", sector="Energy",
                          side=Side.LONG if w > 0 else Side.SHORT, weight=w,
                          notional_usd=w * 1e8, execution_ticker=f"{iid}.SA",
                          line_type=LineType.LOCAL, currency="BRL", days_to_liquidate=None)


def _proposal(positions: list[PositionTarget]) -> Proposal:
    risk = RiskSummary(ex_ante_vol=0.05, factor_vol=0.01, specific_vol=0.049,
                       factor_risk_share=0.05, beta=0.0, gross=0.1, net=0.0, long_exposure=0.05,
                       short_exposure=-0.05, n_long=1, n_short=1, var_1d_99=0.007,
                       es_1d_99=0.008, var_1w_99=0.016, effective_n=2.0,
                       max_days_to_liquidate=0.5, pct_nav_liquidated_1d=0.9)
    return Proposal(proposal_id="P", week=W1, version=1, created_at=T_CREATED,
                    created_by="teste", nav_usd=1e8, snapshot_id="s", snapshot_hash="a" * 64,
                    config_hash="b" * 64, research_hash="c" * 64, positions=positions,
                    risk=risk, compliance=[],
                    optimizer=OptimizerDiagnostics(status="optimal", solver="t",
                                                   solve_seconds=0.0),
                    is_synthetic=True, data_notice="DADOS SIMULADOS — teste")


def test_portfolio_changes_classification():
    old = _proposal([_pt("A", 0.02), _pt("B", 0.02), _pt("C", -0.02), _pt("D", 0.02)])
    new = _proposal([_pt("A", 0.03), _pt("C", 0.01), _pt("D", 0.021), _pt("E", -0.01)])
    df = data.portfolio_changes(new, old)
    kinds = dict(zip(df["issuer_id"], df["change"], strict=False))
    assert kinds == {"E": "Entrada", "B": "Saída", "C": "Inversão de lado", "A": "Aumento"}
    assert "D" not in kinds  # |Δ| abaixo do limiar
    first = data.portfolio_changes(new, None)
    assert set(first["change"]) == {"Entrada"}


def test_liquidity_buckets_keep_missing_days_separate():
    ps = [_pt("A", 0.03), _pt("B", -0.01)]
    ps = [ps[0].model_copy(update={"days_to_liquidate": 0.5}), ps[1]]
    df = data.liquidity_buckets(ps).set_index("Faixa")
    assert df.loc["≤ 1 dia", "gross_share"] == pytest.approx(0.75)
    assert df.loc["n/d", "n"] == 1


def _record(d: date, ret: float, comps: dict[str, float],
            alerts: list[str] | None = None) -> DailyRecord:
    rec = DailyRecord(
        date=d, fund_name="CDP", track_record_type="paper", nav_start_usd=1e8,
        nav_end_usd=1e8 * (1 + ret), pnl_usd=1e8 * ret, ret=ret, pnl_components=comps,
        positions=[DailyPosition(issuer_id="SIM016", ticker="SBR16ADR", currency="USD",
                                 side=Side.SHORT, market_value_usd=-1e6, weight=-0.01,
                                 day_pnl_usd=10.0)],
        risk=DailyRisk(gross=0.1, net=0.0, long_exposure=0.05, short_exposure=-0.05,
                       n_long=1, n_short=1),
        alerts=alerts or [], is_synthetic=True, data_notice="DADOS SIMULADOS", prev_record_hash="0")
    return rec


def test_components_and_attribution_aggregation():
    recs = [_record(date(2026, 10, 5), 0.001, {"factor": 50_000.0, "specific": 50_000.0}),
            _record(date(2026, 10, 6), -0.001, {"factor": -20_000.0, "costs": -80_000.0})]
    comp = data.components_table(recs).set_index("key")
    assert comp.loc["factor", "pnl_usd"] == pytest.approx(30_000.0)
    assert comp.loc["costs", "contribution"] == pytest.approx(-0.0008)
    assert list(comp.index) == ["factor", "specific", "costs"]
    assert data.attribution_table(recs, "country").empty


def test_squeeze_alerted_parses_daily_alerts():
    rec = _record(date(2026, 10, 7), 0.0, {}, alerts=[
        "Short SBR16ADR (SIM016) com risco de squeeze HIGH (era LOW na decisão).",
        "Exposição líquida de país MX +2,19% acima do limite ±2,00%."])
    assert data.squeeze_alerted(rec) == {"SIM016"}
    assert data.squeeze_alerted(None) == set()


def test_extract_section_and_commentary_meta():
    md = "# T\n\n## Comentário do dia\n\nTexto.\n\n_Autoria: mente codex [IA]; x_\n\n## Outra\n"
    sec = data.extract_section(md, "Comentário do dia")
    assert sec.startswith("Texto.") and "Outra" not in sec
    assert data._commentary_meta(sec) == (True, "codex")
    assert data._commentary_meta("Autoria: template determinístico do CDP") == (False, None)
    assert data.extract_section(md, "Inexistente") is None


def test_next_events_respects_deadlines_and_holidays():
    cfg = FundConfig()
    tz = "America/Sao_Paulo"
    from zoneinfo import ZoneInfo

    monday_morning = datetime(2026, 10, 5, 10, 0, tzinfo=ZoneInfo(tz))
    ev = {e.label: e.when for e in data.next_events(monday_morning, cfg, set())}
    assert ev["Decisão semanal (autônoma)"].date() == date(2026, 10, 5)
    assert ev["Fechamento diário"].date() == date(2026, 10, 5)
    # Semana já decidida ⇒ próxima decisão no primeiro pregão da semana seguinte (12/10 é
    # feriado na B3 ⇒ terça 13/10).
    ev = {e.label: e.when for e in data.next_events(monday_morning, cfg, {date(2026, 10, 5)})}
    assert ev["Decisão semanal (autônoma)"].date() == date(2026, 10, 13)
    evening = datetime(2026, 10, 5, 20, 0, tzinfo=ZoneInfo(tz))
    ev = {e.label: e.when for e in data.next_events(evening, cfg, set())}
    assert ev["Fechamento diário"].date() == date(2026, 10, 6)


def test_agents_invariants_prefers_cdp_invariants_section(tmp_path):
    p = tmp_path / "AGENTS.md"
    p.write_text("# Projeto\n## Invariantes\nantigo\n# CDP — fundo\nintro\n"
                 "## Invariantes do CDP\n1. Números só em código.\n# Outro\n", encoding="utf-8")
    sec, src = data.agents_invariants(p)
    assert sec == "1. Números só em código." and "Invariantes do CDP" in src
    sec, src = data.agents_invariants(tmp_path / "nao_existe.md")
    assert sec is None and "não encontrado" in src


def test_safe_url():
    assert data.safe_url("https://exemplo.com/a?b=1") == "https://exemplo.com/a?b=1"
    assert data.safe_url("javascript:alert(1)") is None
    assert data.safe_url("https://x.com/a b") is None
    assert data.safe_url(None) is None


def test_app_paths_from_env(tmp_path):
    env = {"CDP_BOOK_DIR": str(tmp_path / "b"), "CDP_REPORTS_DIR": "",
           "CDP_CONFIG": str(tmp_path / "f.yaml")}
    paths = AppPaths.from_env(env)
    assert paths.book == tmp_path / "b" and paths.reports == Path("reports")
    assert paths.config == tmp_path / "f.yaml" and paths.market == Path("data/market")


def test_track_table_keeps_missing_as_nan():
    rec = _record(date(2026, 10, 5), 0.001, {"factor": 1.0})
    df = data.track_table([rec])
    assert pd.isna(df.loc[0, "Custos"]) and df.loc[0, "Fatorial"] == 1.0
