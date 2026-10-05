"""Exportador do painel (artifact) do CDP: retrato completo, determinístico e seguro (offline)."""

from __future__ import annotations

import json
import math
import re
import shutil
import warnings
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from cdp.config import load_config
from cdp.workflow.painel import (
    DATA_ELEMENT,
    clean,
    embed_json,
    painel_data,
    render_painel,
    scrub_text,
    to_json,
    write_painel,
)
from cdp.workflow.runtime import Runtime

NOW = datetime(2024, 3, 5, 22, 30, tzinfo=UTC)
SECTIONS = {"meta", "status", "track_record", "latest_day", "risk", "weeks", "daily_reports",
            "reports_index", "risk_monitor", "backtests", "audit", "issues"}
MALICIOUS = "</script><script>alert(1)</script><!-- ]]>"
_DATA_RE = re.compile(r'<script type="application/json" id="cdp-data">(.*?)</script>', re.S)


def _rt(root: Path, reports: Path | None = None) -> Runtime:
    return Runtime(load_config(), root / "book", root / "market", reports or root / "reports")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    from cdp.workflow.demo import run_demo

    out = tmp_path_factory.mktemp("painel_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_demo(out, days=2)
    return out


@pytest.fixture(scope="module")
def data(demo):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return painel_data(_rt(demo), now=NOW)


def _floats(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _floats(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _floats(v)
    elif isinstance(obj, float):
        yield obj


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _embedded(html: str) -> dict:
    found = _DATA_RE.findall(html)
    assert len(found) == 1
    return json.loads(found[0])


# ---------------------------------------------------------------- estrutura e conteúdo

def test_all_sections_present(data):
    assert set(data) == SECTIONS
    meta = data["meta"]
    assert meta["schema_version"] == "cdp-painel/1"
    assert meta["fund_name"] == "CDP — Cabra da Peste"
    assert meta["generated_at"] == NOW.isoformat()
    assert len(meta["data_hash"]) == 64
    for key in ("risk", "liquidity", "squeeze", "drawdown", "ai_adoption", "schedule", "table"):
        assert key in meta["mandate"]
    assert meta["mandate"]["risk"]["vol_band_min"] == 0.03
    assert data["track_record"]["exists"] and data["track_record"]["n_days"] == 2
    assert data["latest_day"]["date"] == "2024-03-05"
    assert data["weeks"] and data["weeks"][0]["week"] == "2024-03-04"
    assert data["weeks"][0]["stage"] == "efetivada"
    assert data["status"]["phase"] == "em_operacao"
    assert data["status"]["integrity"]["ok"] is True
    agenda = data["status"]["agenda"]
    assert agenda["ultimo_registro_diario"] == "2024-03-05"
    assert agenda["fechamentos_pendentes"] == [] and "fuso_do_pc" not in agenda
    assert data["audit"]["chain_ok"] is True and data["audit"]["events"]
    assert {c["id"] for c in data["risk"]["limit_checks"]} >= {"vol_ex_ante", "net", "beta",
                                                              "var_1d", "drawdown"}
    assert len(data["daily_reports"]) == 2 and data["daily_reports"][0]["date"] == "2024-03-05"
    assert data["daily_reports"][0]["commentary"]["markdown"]
    assert data["issues"] == []


def test_json_is_strict_without_nan(data):
    text = to_json(data)  # allow_nan=False: NaN/inf levantariam ValueError

    def _bad(token):
        raise AssertionError(f"constante não JSON: {token}")

    json.loads(text, parse_constant=_bad)
    assert all(math.isfinite(x) for x in _floats(data))


def test_daily_drift_breach_is_alert_not_hard_excess():
    from cdp.workflow.painel import _over

    assert _over(0.0101, 0.01, daily=True, hard=True) == "alerta"
    assert _over(0.0101, 0.01, daily=False, hard=True) == "excesso"
    assert _over(0.0101, 0.01, daily=False, hard=False) == "alerta"
    assert _over(0.0099, 0.01, daily=False, hard=True) == "ok"
    assert _over(None, 0.01, daily=True, hard=True) == "n/d"


def test_nan_becomes_null_never_zero():
    out = clean({"a": float("nan"), "b": [1.0, float("inf")], "c": 0.0})
    assert out == {"a": None, "b": [1.0, None], "c": 0.0}


def test_synthetic_flag_and_notice(data):
    meta = data["meta"]
    assert meta["is_synthetic"] is True
    assert "DADOS SIMULADOS" in meta["data_notice"]
    assert meta["simulated_label"] == "DADOS SIMULADOS"
    assert "track record" in meta["synthetic_sources"]
    page = render_painel(data)
    assert "DADOS SIMULADOS" in page


def test_numbers_equal_source_records(demo, data):
    rt = _rt(demo)
    records = rt.track().records()
    last = records[-1]
    assert data["latest_day"]["nav_end"] == last.nav_end_usd
    assert data["status"]["nav_usd"] == last.nav_end_usd
    assert data["track_record"]["records"][-1]["nav_end"] == last.nav_end_usd
    assert data["track_record"]["records"][-1]["record_hash"] == last.record_hash
    assert data["latest_day"]["ret"] == last.ret
    assert data["latest_day"]["risk"]["ex_ante_vol"] == last.risk.ex_ante_vol
    weights = {p["issuer_id"]: p["weight"] for p in data["latest_day"]["positions"]}
    assert weights == {p.issuer_id: p.weight for p in last.positions}
    week = date(2024, 3, 4)
    proposal = rt.book.load_proposal(week)
    exported = data["weeks"][0]["proposal"]
    assert exported["compliance"]["n"] == len(proposal.compliance)
    assert len(exported["compliance"]["checks"]) == len(proposal.compliance)
    assert {p["issuer_id"]: p["weight"] for p in exported["positions"]} == {
        p.issuer_id: p.weight for p in proposal.positions}
    assert exported["risk"]["ex_ante_vol"] == proposal.risk.ex_ante_vol
    assert exported["risk"]["var_1d_99"] == proposal.risk.var_1d_99
    from cdp.contracts import Proposal

    shadow = Proposal.model_validate_json(
        (demo / "book" / week.isoformat() / "shadow_quant.json").read_text(encoding="utf-8"))
    sh = data["weeks"][0]["shadow"]
    assert sh["risk"]["ex_ante_vol"] == shadow.risk.ex_ante_vol
    # Mesmo formato (listas ordenadas) na proposta do CDP e na sombra; ausente ⇒ null.
    for block, src in ((sh["risk"], shadow.risk), (exported["risk"], proposal.risk)):
        assert {r["factor"]: r["share"] for r in block["factor_contributions"]} == {
            k: (v if math.isfinite(v) else None) for k, v in src.factor_contributions.items()}
        assert {r["scenario"]: r["pnl"] for r in block["stress_tests"]} == {
            k: (v if math.isfinite(v) else None) for k, v in src.stress_tests.items()}
        assert [r["issuer_id"] for r in block["top_risk_contributors"]] == sorted(
            src.top_risk_contributors, key=lambda i: (-abs(src.top_risk_contributors[i]), i))
    decision = rt.book.load_decision(week)
    assert data["weeks"][0]["decision"]["approval_hash"] == decision.approval_hash
    assert data["weeks"][0]["decision"]["mode"] == "AUTONOMOUS"
    assert data["audit"]["n_events"] == len(rt.book.audit.events())


def test_no_model_identifiers(data):
    assert not {"model", "models", "model_id"} & set(_keys(data))
    assert scrub_text("via claude-opus-4-1-20250805 e gpt-4o; mente claude-code") == (
        "via [modelo] e [modelo]; mente claude-code")
    assert clean({"model": "x", "note": {"model": None, "t": "ok"}}) == {"note": {"t": "ok"}}


# ---------------------------------------------------------------- injeção e determinismo

def test_injection_cannot_break_out_of_json(data):
    tampered = json.loads(json.dumps(data))
    tampered["daily_reports"][0]["commentary"]["markdown"] = MALICIOUS
    tampered["weeks"][0]["decision"]["rationale"] = "<!--" + MALICIOUS
    page = render_painel(tampered)
    assert "<script>alert(1)" not in page
    assert "<!--" not in page.split(DATA_ELEMENT.split("__")[0])[1].split("</script>")[0]
    back = _embedded(page)
    assert back["daily_reports"][0]["commentary"]["markdown"] == MALICIOUS
    assert back["weeks"][0]["decision"]["rationale"].endswith(MALICIOUS)
    assert "\\u003c/script\\u003e" in embed_json({"t": "</script>"})


def test_malicious_report_text_end_to_end(demo, tmp_path):
    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    md = root / "reports" / "daily" / "2024-03-05" / "relatorio.md"
    text = md.read_text(encoding="utf-8")
    md.write_text(text.replace("## Comentário do dia [IA]",
                               f"## Comentário do dia [IA]\n\n{MALICIOUS}", 1), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        page = render_painel(painel_data(_rt(root), now=NOW))
    assert "<script>alert(1)" not in page
    back = _embedded(page)
    assert MALICIOUS in back["daily_reports"][0]["commentary"]["markdown"]
    assert MALICIOUS in back["daily_reports"][0]["report_markdown"]


def test_deterministic_with_fixed_now(demo, data):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        again = painel_data(_rt(demo), now=NOW)
        later = painel_data(_rt(demo), now=NOW.replace(hour=23))
    assert again["meta"]["data_hash"] == data["meta"]["data_hash"]
    assert to_json(again) == to_json(data)
    assert later["meta"]["data_hash"] != data["meta"]["data_hash"]


def test_write_painel_files(demo, tmp_path, data):
    out, standalone = tmp_path / "painel" / "cdp.html", tmp_path / "local.html"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = write_painel(_rt(demo), out, standalone_out=standalone, now=NOW)
    page = out.read_text(encoding="utf-8")
    full = standalone.read_text(encoding="utf-8")
    assert not page.lower().startswith("<!doctype")
    assert full.startswith("<!doctype html><html lang=\"pt-BR\">") and page in full
    assert res["data_hash"] == data["meta"]["data_hash"]
    import hashlib

    assert res["sha256"] == hashlib.sha256(page.encode("utf-8")).hexdigest()
    assert res["bytes"] == len(page.encode("utf-8"))
    assert _embedded(page)["meta"]["data_hash"] == data["meta"]["data_hash"]


def test_template_requires_single_placeholder(tmp_path, data):
    bad = tmp_path / "t.html"
    bad.write_text("<div>sem dados</div>", encoding="utf-8")
    with pytest.raises(ValueError):
        render_painel(data, bad)


# ---------------------------------------------------------------- robustez

def test_empty_book_before_inception(tmp_path):
    root = tmp_path / "nada"
    d = painel_data(_rt(root), now=datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    assert set(d) == SECTIONS
    assert d["weeks"] == [] and d["latest_day"] is None
    assert d["track_record"]["exists"] is False
    assert d["status"]["phase"] == "pre_inception"
    assert d["status"]["nav_usd"] == load_config().fund.inception_nav_usd
    assert d["meta"]["is_synthetic"] is False
    assert d["risk"]["limit_checks"] == []
    assert d["status"]["agenda"] is None
    assert any(e["label"].startswith("Decisão semanal") for e in d["status"]["next_events"])
    assert not (root / "book").exists()  # leitura nunca cria pastas
    json.loads(to_json(d))


def test_corrupted_files_are_reported_not_raised(demo, tmp_path):
    root = tmp_path / "corrompido"
    shutil.copytree(demo, root)
    (root / "book" / "2024-03-04" / "proposal_v1.json").write_text("{não é json",
                                                                   encoding="utf-8")
    rec = root / "book" / "track_record" / "records" / "2024-03-05.json"
    raw = json.loads(rec.read_text(encoding="utf-8"))
    raw["nav_end_usd"] = raw["nav_end_usd"] + 1_000_000.0
    rec.write_text(json.dumps(raw), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = painel_data(_rt(root), now=NOW)
    assert d["status"]["integrity"]["ok"] is False
    failed = {c["id"] for c in d["status"]["integrity"]["checks"] if c["ok"] is False}
    assert {"livro", "track_record"} <= failed
    assert d["issues"]
    assert any(a["severity"] == "error" for a in d["status"]["alerts"])
    json.loads(to_json(d))


def test_decided_week_not_yet_executed(tmp_path):
    """Pregão de decisão antes do fechamento: entradas da mente, decisão e nenhum registro."""
    from cdp.data.synthetic import make_synthetic_market
    from cdp.workflow.demo import (
        DEMO_HISTORY_START,
        DEMO_MIND,
        DemoStore,
        _Clock,
        write_demo_inputs,
    )

    week = date(2024, 3, 4)
    md = make_synthetic_market(seed=7, start=DEMO_HISTORY_START, as_of=week)
    clock = _Clock()
    rt = Runtime(load_config(), tmp_path / "book", tmp_path / "market", tmp_path / "reports",
                 store_override=DemoStore(md), clock=clock)
    now = datetime(2024, 3, 4, 18, 0, tzinfo=UTC)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clock.set(week, time(11, 0))
        rt.weekly_prepare(week, mind=DEMO_MIND, live=False)
        clock.set(week, time(12, 0))
        write_demo_inputs(rt, week)
        pending = painel_data(rt, now=now)
        clock.set(week, time(15, 0))
        rt.weekly_decide(week, mind=DEMO_MIND)
        decided = painel_data(rt, now=now)
    w0 = pending["weeks"][0]
    assert pending["status"]["phase"] == "aguardando_decisao"
    assert w0["stage"] == "entradas_gravadas" and w0["decision"] is None
    assert w0["research"]["source"] == "entradas"
    assert w0["pm_decision"]["valid"] is True
    w1 = decided["weeks"][0]
    assert decided["status"]["phase"] == "decidida_aguardando_execucao"
    assert w1["stage"] == "decidida" and w1["executed"] is False
    assert w1["decision"]["mode"] == "AUTONOMOUS" and w1["decision"]["mind"] == DEMO_MIND
    assert w1["research"]["source"] == "livro"
    assert w1["report"]["available"] is True and w1["report"]["markdown"]
    assert decided["latest_day"] is None and decided["track_record"]["exists"] is False
    risk = decided["risk"]
    assert risk["ex_ante"]["ex_ante_vol"] == rt.book.load_proposal(week).risk.ex_ante_vol
    assert risk["daily"] is None and "ainda sem registro diário" in risk["basis_note"]
    assert risk["limit_checks"] and all("ex-ante" in c["basis"] for c in risk["limit_checks"])
    # Coerência com o compliance gravado: sem falha HARD na decisão ⇒ nenhum "excesso" ex-ante.
    assert not w1["proposal"]["compliance"]["failed_hard"]
    assert not [c["id"] for c in risk["limit_checks"] if c["status"] == "excesso"]
    assert decided["meta"]["is_synthetic"] is True


def test_backtests_and_risk_monitor(demo, tmp_path):
    reports = tmp_path / "reports"
    run = reports / "backtest" / "bt_x"
    run.mkdir(parents=True)
    (run / "metrics.json").write_text(json.dumps(
        {"variant": "X", "overrides": {"costs": {"amortization_weeks": 4}},
         "metrics": {"sharpe": float("nan"), "ann_vol": 0.05},
         "notes": ["nota"], "provenance": {"data_notice": "DADOS SIMULADOS — teste"}}),
        encoding="utf-8")
    (run / "weekly.csv").write_text("date,status,ex_ante_vol,turnover\n"
                                    "2024-01-01,ok,0.04,0.3\n2024-01-08,ok,,0.1\n",
                                    encoding="utf-8")
    (run / "daily.csv").write_text("date,ret_net,nav,cost,factor_pnl,rebalance\n"
                                   "2024-01-01,0.0,100.0,0.001,0.0,True\n"
                                   "2024-01-02,0.01,101.0,0.0,0.002,False\n"
                                   "2024-01-03,-0.02,98.98,0.0,-0.001,False\n",
                                   encoding="utf-8")
    (run / "ic.csv").write_text("date,composite\n2024-01-01,0.1\n2024-01-08,-0.05\n",
                                encoding="utf-8")
    (reports / "backtest" / "NOTA.md").write_text("# Calibração\n", encoding="utf-8")
    risk_dir = reports / "risk" / "2024-03-05"
    risk_dir.mkdir(parents=True)
    (risk_dir / "monitor.json").write_text(json.dumps({"var": float("nan"), "model": "x",
                                                       "texto": MALICIOUS}), encoding="utf-8")
    (risk_dir / "monitor.md").write_text("# Monitor\n", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = painel_data(_rt(demo, reports), now=NOW)
    bt = d["backtests"]
    assert bt["available"] and bt["runs"][0]["label"] == "Variante X"
    r = bt["runs"][0]
    assert r["metrics"]["sharpe"] is None and r["metrics"]["ann_vol"] == 0.05
    assert r["is_synthetic"] is True and d["meta"]["is_synthetic"] is True
    assert r["weekly"]["ex_ante_vol"] == [0.04, None]
    assert r["nav_weekly"]["nav"][-1] == 98.98
    assert r["ic"]["summary"]["composite"]["n"] == 2
    assert [(x["path"], x["markdown"]) for x in bt["documents"]] == [("NOTA.md", "# Calibração\n")]
    mon = d["risk_monitor"]
    assert mon["available"] and mon["runs"][0]["date"] == "2024-03-05"
    assert mon["latest"] == {"run_key": "2024-03-05", "file": "monitor.json",
                             "md_file": "monitor.md"}
    assert mon["timeline"][0]["file"] == "monitor.json"
    files = {f["name"]: f for f in mon["runs"][0]["files"]}
    assert files["monitor.json"]["data"] == {"var": None, "texto": MALICIOUS}
    assert files["monitor.md"]["text"] == "# Monitor\n"
    assert "<script>alert(1)" not in render_painel(d)


def test_risk_monitor_runs_timeline_and_limits(demo, tmp_path):
    """Saídas reais do monitor: a mais recente completa, as antigas só no resumo (timeline)."""
    from cdp.workflow.risk_monitor import run_risk_monitor, write_risk_report

    reports = tmp_path / "reports"
    shutil.copytree(demo / "reports", reports)
    rt = _rt(demo, reports)
    session = date(2024, 3, 5)
    written = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for hh in (13, 18):
            res = run_risk_monitor(rt, as_of=session,
                                   now=datetime(2024, 3, 5, hh, 0, tzinfo=UTC))
            written.append(write_risk_report(res, reports / "risk", rt.cfg))
        d = painel_data(rt, now=NOW, max_risk_full_runs=1)
    mon = d["risk_monitor"]
    assert mon["available"] and len(mon["timeline"]) == 2
    newest = json.loads(Path(written[-1]["json"]).read_text(encoding="utf-8"))
    assert mon["latest"]["file"] == Path(written[-1]["json"]).name
    assert mon["latest"]["md_file"] == Path(written[-1]["md"]).name
    top = mon["timeline"][0]
    assert top["file"] == mon["latest"]["file"]
    assert top["nav_fechamento_usd"] == newest["nav"]["fechamento_usd"]
    assert top["nav_fechamento_usd"] == rt.track().get(session).nav_end_usd
    assert top["drawdown_fechamento"] == newest["drawdown"]["fechamento"]
    assert sum(top["n_gatilhos"].values()) == len(newest["gatilhos"])
    files = {f["name"]: f for f in mon["runs"][0]["files"]}
    new_json, old_json = Path(written[-1]["json"]).name, Path(written[0]["json"]).name
    assert files[new_json]["full"] and files[new_json]["data"]["nav"] == newest["nav"]
    assert files[Path(written[-1]["md"]).name]["text"].startswith("#")
    assert not files[old_json]["full"] and "data" not in files[old_json]
    assert files[old_json]["summary"]["status"] == "ok" and "omitted" in files[old_json]
    assert "text" not in files[Path(written[0]["md"]).name]


def test_older_weeks_are_summarized(demo, data):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = painel_data(_rt(demo), now=NOW, full_weeks=0)
    w = d["weeks"][0]
    assert w["detail"] == "resumo"
    assert "trades" not in w["proposal"] and w["proposal"]["positions"]
    full_risk = data["weeks"][0]["proposal"]["risk"]
    for key in ("factor_contributions", "stress_tests", "top_risk_contributors"):
        assert w["proposal"]["risk"][key] == full_risk[key]
    assert "exposures" not in w["proposal"]["risk"]
    assert w["proposal"]["summary"] == data["weeks"][0]["proposal"]["summary"]
    assert w["decision"]["journal"] is None and w["decision"]["journal_omitted"] is True
    assert w["pm_decision"] is None and w["report"]["markdown"] is None
    assert "notes" not in w["research"] and w["research"]["counts"]["notes"] >= 1
    assert "{{fact:" not in to_json(data)
