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

from cdp.audit import AuditLog
from cdp.config import FundConfig, load_config
from cdp.contracts import (
    BookEntry,
    DailyPosition,
    DailyRecord,
    DailyRisk,
    Decision,
    DecisionType,
    LineType,
    OptimizerDiagnostics,
    PositionTarget,
    Proposal,
    RiskSummary,
    Side,
)
from cdp.hashing import sha256_obj
from cdp.ui import data, fmt
from cdp.ui.app import PAGES
from cdp.ui.settings import AppPaths

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
    from cdp.data.snapshot import write_snapshot
    from cdp.data.store import MarketStore
    from cdp.data.synthetic import make_synthetic_market
    from cdp.hashing import sha256_file
    from cdp.research.agents import ResearchRequest, run_research
    from cdp.research.commentary import (
        build_daily_factbook,
        example_commentary,
        load_commentary_file,
    )
    from cdp.research.factbook import build_factbook
    from cdp.research.pm_agent import (
        PMContext,
        example_pm_decision,
        load_pm_decision_file,
        pm_factbook,
        to_bundle,
        write_briefing_bundle,
    )
    from cdp.research.providers.demo import DemoResearchProvider
    from cdp.workflow.autonomy import make_autonomous_decision
    from cdp.workflow.book import Book
    from cdp.workflow.daily import SHADOW_RECORD_EVENT, DailyRunner, PendingExecution
    from cdp.workflow.reports import (
        render_daily_report,
        render_weekly_report,
        write_report_files,
    )
    from cdp.workflow.track_record import TrackRecord
    from cdp.workflow.weekly import prepare_week, run_weekly_decision

    root.mkdir(parents=True, exist_ok=True)
    cfg = load_config(REPO / "configs/cdp/fund.yaml").with_overrides(
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
    at = AppTest.from_string(f"from cdp.ui.app import run_page\nrun_page({key!r})\n",
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
    _env(monkeypatch, base / "book", base / "reports", REPO / "configs/cdp/fund.yaml",
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
    _env(monkeypatch, base / "book", base / "reports", REPO / "configs/cdp/fund.yaml",
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


def test_light_loaders_on_fixture(fixture_book):
    fb = fixture_book
    assert data.market_is_synthetic(fb.market)
    ctx = data.load_market_context(fb.market)
    assert ctx.available and ctx.last_date == SESSIONS[-1] and ctx.facts
    book = data.load_book(fb.book)
    wk = book.week(W1)
    assert wk is not None and wk.mind == MIND and wk.path_taken == "cdp"
    assert wk.state == "BOOKED" and wk.shadow is not None and wk.llm_calls and wk.facts
    assert not wk.issues and not book.issues
    track = data.load_track(fb.book, fb.cfg)
    assert [r.date for r in track.records] == list(SESSIONS) and not track.issues
    assert len(track.shadow_records) == 3 and track.compare is not None
    com = data.commentary_for(fb.reports, track.latest, track.history_until(track.latest),
                              fb.cfg)
    assert com is not None and com.ai and com.mind == MIND
    reports = data.list_reports(fb.reports)
    assert {(r.kind, r.key) for r in reports} == {("weekly", W1)} | {
        ("daily", d) for d in SESSIONS}


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
    assert "FALHA DE INTEGRIDADE" not in text  # livro-fixture íntegro: sem falso alarme
    last = fx_env.records[-1]
    if key == "visao-geral":
        assert any(m.label == "NAV" and m.value == fmt.usd_mm(last.nav_end_usd)
                   for m in at.metric)
        dec = next(df.value for df in at.dataframe if "Item" in df.value.columns)
        rows = dict(zip(dec["Item"], dec["Valor"], strict=False))
        assert rows["Execução"].startswith("em carteira")
        assert rows["Prazo do mandato"].startswith("dentro do prazo")
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
    assert values["Prazo do mandato"] == "dentro do prazo (16:30 de 05/10/2026)"
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


def _fill_kill_switch(at: AppTest, act: str, reason: str, by: str = "Operador de risco",
                      confirm: bool = True) -> AppTest:
    """Preenche e envia o formulário do kill switch da ação ``act`` (on | off)."""
    at.text_area(key=f"ks_reason_{act}").input(reason)
    at.text_input(key=f"ks_by_{act}").input(by)
    if confirm:
        at.checkbox(key=f"ks_confirm_{act}").check()
    return at.button(key=f"ks_submit_{act}").click().run()


def test_kill_switch_on_and_off_writes_file_and_audit_events(fixture_book, tmp_path,
                                                             monkeypatch):
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    n0 = len(AuditLog(c.book / "audit_log.jsonl").events())
    at = page_app("auditoria")
    reason = "Teste de emergência <script>alert(1)</script> [x](javascript:alert(1))"
    _fill_kill_switch(at, "on", reason)
    _no_exceptions(at)
    ks_file = c.book / "KILL_SWITCH"
    assert ks_file.exists()
    payload = json.loads(ks_file.read_text(encoding="utf-8"))
    # Campos do spec ({reason, created_at, by}) + os da CLI (on, at).
    assert payload["reason"] == reason and payload["by"] == "Operador de risco"
    assert payload["created_at"] and payload["on"] is True
    assert datetime.fromisoformat(payload["created_at"]).tzinfo is not None
    events = AuditLog(c.book / "audit_log.jsonl").events()
    assert len(events) == n0 + 1 and events[-1].event_type == "KILL_SWITCH_ON"
    assert events[-1].actor == "Operador de risco"
    assert events[-1].payload_hash == sha256_obj(payload)  # arquivo = payload auditado
    assert AuditLog(c.book / "audit_log.jsonl").verify_chain()[0]
    assert not any("mudou" in str(e.value) for e in at.error)  # sem falso "estado mudou"
    # Banner e status aparecem; o texto digitado é exibido escapado (nunca como HTML).
    errors = [str(e.value) for e in at.error]
    assert any("KILL SWITCH LIGADO" in e for e in errors)
    assert all("<script>" not in e for e in errors)
    assert any("\\<script\\>" in e for e in errors)
    assert any("registrado na trilha" in str(s.value) for s in at.success)

    _fill_kill_switch(at, "off", "Fim do teste de emergência")
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
    _fill_kill_switch(at, "on", "curto", by="Op", confirm=False)
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
    # Cobertura explícita: componente ausente num dia não é somado como zero às escondidas.
    assert comp.loc["factor", "days"] == 2 and comp.loc["specific", "days"] == 1
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


# ==========================================================
# Revisão adversarial: regressões (cada teste expõe um defeito corrigido)
# ==========================================================

def test_kill_switch_intent_is_never_inverted_by_concurrent_change(fixture_book, tmp_path,
                                                                   monkeypatch):
    """Operador preenche LIGAR; outro operador (ou a CLI) liga antes do envio. Antes, o envio
    era reinterpretado pelo estado novo e DESLIGAVA o kill switch."""
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    at = page_app("auditoria")
    data.set_kill_switch(AppPaths.from_env(), FundConfig(), True, "Ligado por outro operador",
                         "Outro operador")
    n0 = len(AuditLog(c.book / "audit_log.jsonl").events())
    _fill_kill_switch(at, "on", "Quero ligar: risco de gap no Brasil")
    _no_exceptions(at)
    assert (c.book / "KILL_SWITCH").exists(), "intenção de LIGAR virou DESLIGAR"
    events = AuditLog(c.book / "audit_log.jsonl").events()
    assert len(events) == n0 and events[-1].event_type == "KILL_SWITCH_ON"
    assert any("estado do kill switch mudou" in str(e.value) for e in at.error)


def test_set_kill_switch_refuses_stale_expectation(tmp_path):
    paths = AppPaths.from_env({"CDP_BOOK_DIR": str(tmp_path / "book")})
    with pytest.raises(RuntimeError, match="mudou"):
        data.set_kill_switch(paths, FundConfig(), False, "desligar agora", "Ana",
                             expect_active=True)
    assert not (tmp_path / "book").exists()  # nada gravado
    ks = data.set_kill_switch(paths, FundConfig(), True, "ligar por teste", "Ana",
                              expect_active=False,
                              now=datetime(2026, 10, 5, 15, 0, tzinfo=UTC))
    assert ks.active and ks.created_at == "2026-10-05T15:00:00+00:00"
    with pytest.raises(RuntimeError, match="já está LIGADO"):
        data.set_kill_switch(paths, FundConfig(), True, "ligar de novo", "Ana")
    assert len(AuditLog(tmp_path / "book" / "audit_log.jsonl").events()) == 1


def test_tampered_record_raises_integrity_banner_on_every_page(fixture_book, tmp_path,
                                                               monkeypatch):
    """Antes, um registro adulterado só aparecia ao clicar em "Verificar integridade"; as
    páginas exibiam os números alterados como se fossem válidos."""
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    path = c.book / "track_record" / "records" / f"{SESSIONS[1].isoformat()}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["pnl_components"]["specific"] = raw["pnl_components"]["specific"] + 50_000.0
    path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    for key in ("visao-geral", "atribuicao"):
        at = page_app(key)
        _no_exceptions(at)
        assert any("FALHA DE INTEGRIDADE" in str(e.value) for e in at.error), key


def test_corrupted_record_is_flagged_not_shown_as_empty_track(fixture_book, tmp_path,
                                                              monkeypatch):
    """Antes, um único JSON ilegível zerava a lista de registros e a visão geral dizia
    "Track record ainda não iniciado"; compor só os dias legíveis trataria o dia ilegível como
    retorno zero."""
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    (c.book / "track_record" / "records" / f"{SESSIONS[1].isoformat()}.json").write_text(
        '{"date": "2026-10-06"', encoding="utf-8")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    track = data.load_track(c.book, fixture_book.cfg)
    assert [r.date for r in track.records] == [SESSIONS[0], SESSIONS[2]]
    assert track.unreadable == [SESSIONS[1]] and track.integrity_failures
    assert any("ilegível" in i for i in track.issues)
    at = page_app("visao-geral")
    _no_exceptions(at)
    text = _texts(at)
    assert "Track record ainda não iniciado" not in text
    assert any("FALHA DE INTEGRIDADE" in str(e.value) for e in at.error)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["NAV"] == fmt.usd_mm(fixture_book.records[2].nav_end_usd)
    assert metrics["Desde o início (ITD)"] == "n/d" and metrics["Retorno no mês (MTD)"] == "n/d"
    at = page_app("atribuicao")
    _no_exceptions(at)
    assert any("registro ilegível no período" in str(e.value) for e in at.error)
    assert {m.label: m.value for m in at.metric}["Retorno no período"] == "n/d"


def test_integrity_result_is_not_reused_after_files_change(fixture_book, tmp_path,
                                                           monkeypatch):
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    at = page_app("track-record")
    at.button(key="verify_track").click().run()
    assert any("íntegro" in str(s.value) for s in at.success)
    path = c.book / "track_record" / "records" / f"{SESSIONS[0].isoformat()}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["ret"] = raw["ret"] + 0.01
    path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    at.run()
    _no_exceptions(at)
    assert not any("Track record do CDP: íntegro" in str(s.value) for s in at.success)
    assert "verifique novamente" in _texts(at)


def test_deleted_track_record_is_detected(fixture_book, tmp_path, monkeypatch):
    """Antes, sem a pasta do track record a verificação dizia "Sem registros diários ainda"
    (íntegro) mesmo com a trilha listando três registros."""
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    shutil.rmtree(c.book / "track_record")
    results = data.verify_track_integrity(c.book)
    main = next(r for r in results if r.label == "Track record do CDP")
    assert not main.ok and any("sem registro correspondente" in m for m in main.messages)
    assert not (c.book / "track_record").exists()  # verificar não recria a pasta
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    at = page_app("risco")
    _no_exceptions(at)
    assert any("FALHA DE INTEGRIDADE" in str(e.value) for e in at.error)
    # Sem registro diário, o monitor de squeeze diz n/d (nunca "0 HIGH").
    assert any(m.label == "HIGH no último fechamento" and m.value == "n/d" for m in at.metric)


def test_html_report_with_active_content_is_not_rendered(fixture_book, tmp_path, monkeypatch):
    for r in data.list_reports(fixture_book.reports):
        assert data.html_active_content(r.html.read_text(encoding="utf-8")) == [], r.label
    for bad in ("<script>alert(1)</script>", '<img src=x onerror="alert(1)">',
                '<a href="javascript:alert(1)">x</a>', '<img src="https://evil.example/p.png">',
                "<iframe srcdoc='x'></iframe>", "<style>@import url(//evil.example/x.css)</style>"):
        assert data.html_active_content(bad), bad
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    html = c.reports / "daily" / SESSIONS[2].isoformat() / "relatorio.html"
    html.write_text(html.read_text(encoding="utf-8").replace(
        "</body>", "<script>parent.document.title='x'</script></body>"), encoding="utf-8")
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    at = page_app("relatorios")
    at.toggle(key="rep_html").set_value(True).run()
    _no_exceptions(at)
    assert any("HTML não exibido" in str(e.value) for e in at.error)


def test_ai_text_in_widget_labels_is_escaped(fixture_book, tmp_path, monkeypatch):
    """Rótulos de expander interpretam Markdown (links e imagens): o escopo macro vem da IA."""
    from cdp.workflow.book import Book

    evil = "BR ![x](https://evil.example/p.png) [clique](https://evil.example)"
    assert "](" not in fmt.label(evil)
    c = _copy_fixture(fixture_book, tmp_path / "copia")
    book = Book(c.book)
    pack = book.load_research_pack(W1)
    macro = [m.model_copy(update={"scope": evil}) if i == 0 else m
             for i, m in enumerate(pack.macro) if m.scope.upper() != "GOVERNANÇA"]
    book.save_research_pack(pack.model_copy(update={"macro": macro}), actor=MIND)
    _env(monkeypatch, c.book, c.reports, c.config, c.market)
    at = page_app("pesquisa")
    _no_exceptions(at)
    labels = _block_labels(at.main)
    assert any("evil" in lb and "BR" in lb for lb in labels)
    assert all("](" not in lb for lb in labels)


def _block_labels(node: object) -> list[str]:
    """Rótulos de blocos expansíveis (expander com ícone aparece como ``Status`` no AppTest)."""
    out: list[str] = []
    for child in getattr(node, "children", {}).values():
        if type(child).__name__ in ("Expander", "Status") and getattr(child, "label", None):
            out.append(str(child.label))
        out += _block_labels(child)
    return out


def test_report_md_defuses_links_and_images():
    md = fmt.report_md("![p](https://evil.example/p.png) e [a](javascript:alert(1)) "
                       "<https://evil.example> e `[c](d)`")
    assert "](" not in md.replace("`[c](d)`", "") and "`[c](d)`" in md
    assert "\\<https:" in md


def _decision_for(p: Proposal, kind: DecisionType) -> Decision:
    return Decision(week=p.week, proposal_id=p.proposal_id, proposal_hash="d" * 64,
                    snapshot_hash=p.snapshot_hash, config_hash=p.config_hash,
                    research_hash=p.research_hash, decision=kind, approver="Ana Gestora",
                    rationale="Racional de teste suficiente.", decided_at=T_DECIDED,
                    approval_hash="e" * 64)


def _versions() -> tuple[Proposal, Proposal]:
    base = _proposal([_pt("A", 0.02), _pt("B", -0.02)])
    return (base.model_copy(update={"proposal_id": "P1", "version": 1}),
            base.model_copy(update={"proposal_id": "P2", "version": 2}))


def test_week_never_pairs_a_proposal_with_another_versions_decision():
    p1, p2 = _versions()
    wk = data.WeekData(week=W1, proposals=[p1, p2],
                       decisions={1: _decision_for(p1, DecisionType.REJECT)})
    # Antes: proposta v2 exibida com a decisão (REJECT) da v1.
    assert wk.proposal is p2 and wk.decision is None
    approved = _decision_for(p1, DecisionType.APPROVE)
    wk = data.WeekData(week=W1, proposals=[p1, p2], decisions={1: approved})
    assert wk.proposal is p1 and wk.decision is approved  # rascunho v2 não substitui a decidida
    wk = data.WeekData(week=W1, proposals=[p1, p2],
                       decisions={2: _decision_for(p2, DecisionType.APPROVE)})
    assert wk.proposal is p2 and wk.decision.proposal_id == "P2"


def _booked(week: date, pid: str) -> BookEntry:
    return BookEntry(week=week, proposal_id=pid, approval_hash="e" * 64, booked_at=T_DECIDED,
                     nav_usd=1e8, positions=[])


def test_live_week_has_no_look_ahead_and_previous_prefers_booked():
    p1, p2 = _versions()
    w0, w1, w2 = date(2026, 9, 28), date(2026, 10, 5), date(2026, 10, 13)
    book = data.BookData(root=Path("x"), weeks=[
        data.WeekData(week=w0, proposals=[p1], booked=_booked(w0, "P1")),
        data.WeekData(week=w1, proposals=[p2]),
        data.WeekData(week=w2, proposals=[p1])])
    rec = _record(date(2026, 10, 7), 0.0, {})
    # Semana citada no registro fora do livro ⇒ None (antes: a decisão mais NOVA, de 13/10).
    assert book.live_week(rec.model_copy(update={"live_book_week": date(2026, 9, 21)})) is None
    assert book.live_week(rec).week == w1  # sem semana no registro: a última até a data
    assert book.live_week(None).week == w2
    # "O que mudou" compara com a carteira efetivada (w0), não com a proposta não executada.
    assert book.previous(w2).week == w0


def test_liquidity_uses_the_short_side_limit_and_missing_first():
    cfg = FundConfig()
    lo = _pt("A", 0.03).model_copy(update={"days_to_liquidate": 2.5})
    sh = _pt("B", -0.02).model_copy(update={"days_to_liquidate": 2.5})
    unknown = _pt("C", -0.01)
    by_side = data.liquidity_by_side([lo, sh], cfg)
    assert by_side["LONG"].status.color == "green"  # 2,5 d ≤ 3 d (long)
    assert by_side["SHORT"].status.color == "red"   # 2,5 d > 2 d (short): antes ficava verde
    worst = data.worst_liquidity_status(by_side)
    assert worst.color == "red" and worst.label.startswith("S:")
    assert data.liquidity_by_side([lo, unknown], cfg)["SHORT"].status.color == "orange"
    assert [p.issuer_id for p in data.least_liquid([lo, sh, unknown])] == ["C", "A", "B"]


def test_value_added_series_does_not_treat_missing_day_as_zero():
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in SESSIONS], name="date")
    cmp_ = pd.DataFrame({"ret_cdp": [0.01, float("nan"), 0.01], "ret_shadow": [0.0, 0.0, 0.0]},
                        index=idx)
    va = data.value_added_series(cmp_, SESSIONS[0], SESSIONS[2])
    assert va["value_added"].iloc[0] == pytest.approx(0.01)
    assert va["value_added"].iloc[1:].isna().all()  # antes: 1,01² − 1 (dia ausente = 0%)


def test_next_events_flags_overdue_weekly_decision():
    from zoneinfo import ZoneInfo

    cfg = FundConfig()
    tz = ZoneInfo("America/Sao_Paulo")
    late = datetime(2026, 10, 19, 17, 0, tzinfo=tz)
    ev = data.next_events(late, cfg, set())
    overdue = [e for e in ev if e.overdue]
    assert len(overdue) == 1 and overdue[0].when.date() == date(2026, 10, 19)
    assert not any(e.overdue for e in data.next_events(late, cfg, {date(2026, 10, 19)}))
    before_inception = datetime(2026, 9, 28, 17, 0, tzinfo=tz)
    assert not any(e.overdue for e in data.next_events(before_inception, cfg, set()))


def test_decision_timing_against_mandate_deadline():
    cfg = FundConfig()
    p1, _ = _versions()
    d = _decision_for(p1, DecisionType.APPROVE)
    assert data.decision_timing(d, cfg).color == "green"  # 14h de Brasília
    late = d.model_copy(update={"decided_at": datetime(2026, 10, 5, 20, 0, tzinfo=UTC)})
    status = data.decision_timing(late, cfg)
    assert status.color == "red" and status.label.startswith("APÓS o prazo")


def test_commentary_mind_comes_from_the_code_provenance_line():
    md = ("Parágrafo que imita: mente impostora [IA] fez isto.\n\n"
          "_Autoria: mente codex [IA]; números calculados por código._")
    assert data._commentary_meta(md) == (True, "codex")


def test_list_reports_ignores_symlinks_outside_root(tmp_path):
    secret = tmp_path / "segredo.md"
    secret.write_text("# segredo", encoding="utf-8")
    folder = tmp_path / "reports" / "daily" / "2026-10-05"
    folder.mkdir(parents=True)
    (folder / "relatorio.md").symlink_to(secret)
    assert data.list_reports(tmp_path / "reports") == []
    (folder / "relatorio.html").write_text("<html></html>", encoding="utf-8")
    [rep] = data.list_reports(tmp_path / "reports")
    assert rep.md is None and rep.html is not None


def test_fingerprint_content_mode_detects_same_size_and_mtime_edit(tmp_path):
    import os

    f = tmp_path / "audit_log.jsonl"
    f.write_text('{"seq": 0}\n', encoding="utf-8")
    st0 = f.stat()
    a, a_content = data.fingerprint(f), data.fingerprint(f, content=True)
    f.write_text('{"seq": 9}\n', encoding="utf-8")
    os.utime(f, ns=(st0.st_atime_ns, st0.st_mtime_ns))
    assert data.fingerprint(f) == a  # tamanho e mtime iguais
    assert data.fingerprint(f, content=True) != a_content
