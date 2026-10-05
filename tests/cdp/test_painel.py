"""Exportador do painel (artifact) do CDP: retrato completo, determinístico e seguro (offline);
publicação em ``index.html`` + ``data.json`` (perfil ``publicacao``) e cópia local completa."""

from __future__ import annotations

import copy
import hashlib
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
    EMPTY_DATA_ELEMENT,
    MARKER_NAME,
    PAGE_LAYOUT,
    PAGE_SHA_PLACEHOLDER,
    PLACEHOLDER,
    asset_names,
    clean,
    embed_json,
    mark_published,
    page_assets,
    page_sha256,
    page_version,
    painel_data,
    published_page_sha,
    render_page,
    render_painel,
    scrub_text,
    to_json,
    write_painel,
)
from cdp.workflow.painel_publicacao import (
    COMENTARIOS_MINIMOS,
    DATA_MAX_BYTES,
    DATA_MAX_LINE,
    NIVEIS,
    PAGE_MAX_BYTES,
    PAGE_MAX_LINE,
    PREGOES_MINIMOS,
    cabe,
    chosen_backtest,
    compactar,
    dump_publicacao,
    expandir,
    max_line,
    partes,
    publicacao,
    report_path,
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
    assert meta["schema_version"] == "cdp-painel/2" and meta["profile"] == "completo"
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
    """index.html (dados vazios) + data.json (publicação) + cópia local com o retrato completo."""
    out = tmp_path / "painel"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = write_painel(_rt(demo), out, now=NOW)
    index, data_file, local = out / "index.html", out / "data.json", out / "cdp_painel_local.html"
    page, text, full = (f.read_text(encoding="utf-8") for f in (index, data_file, local))
    assert not page.lower().startswith("<!doctype") and page == render_page()
    assert page.count(EMPTY_DATA_ELEMENT) == 1 and PLACEHOLDER not in page
    # versão da página (SHA-256 do template) carimbada na página, na cópia local e nos dados
    version = page_sha256()
    assert PAGE_SHA_PLACEHOLDER not in page and page_version(page) == version
    assert page_version(full) == version and res["page_sha256"] == version
    assert full.startswith("<!doctype html><html lang=\"pt-BR\">")
    assert _embedded(full)["meta"]["data_hash"] == data["meta"]["data_hash"]  # completo embutido
    assert _embedded(full)["meta"]["profile"] == "completo"
    pub = json.loads(text)
    assert text == dump_publicacao(pub)  # indentado, chaves ordenadas, UTF-8
    assert pub["meta"]["profile"] == "publicacao" and res["data_hash"] == pub["meta"]["data_hash"]
    assert pub["meta"]["page_sha256"] == version
    assert res["data_hash_completo"] == data["meta"]["data_hash"]
    # nada publicado ainda (sem PAGINA_PUBLICADA.sha256): a página precisa ir junto
    assert res["page_changed"] is True and res["index_written"] is True
    assert res["published_page_sha256"] is None and not (out / MARKER_NAME).exists()
    for key, f, body in (("index", index, page), ("data", data_file, text)):
        raw = f.read_bytes()
        assert res[f"{key}_path"] == f.as_posix() and res[f"{key}_bytes"] == len(raw)
        assert res[f"{key}_sha256"] == hashlib.sha256(raw).hexdigest()
        assert res[f"{key}_max_line"] == max_line(body)
    assert res["local_sha256"] == hashlib.sha256(local.read_bytes()).hexdigest()
    assert res["data_bytes"] <= DATA_MAX_BYTES and res["data_max_line"] <= DATA_MAX_LINE
    assert res["index_bytes"] <= PAGE_MAX_BYTES and res["index_max_line"] <= PAGE_MAX_LINE
    # estilo e script versionados ao lado da casca
    css, js = asset_names(version)
    assert [a["path"] for a in res["assets"]] == [(out / css).as_posix(), (out / js).as_posix()]
    for a in res["assets"]:
        raw = Path(a["path"]).read_bytes()
        assert a["bytes"] == len(raw) <= PAGE_MAX_BYTES and a["max_line"] <= PAGE_MAX_LINE
        assert a["sha256"] == hashlib.sha256(raw).hexdigest()
    assert res["assets_removed"] == []


def test_page_is_a_small_shell_with_versioned_assets():
    """A casca publicada referencia o estilo e o script versionados; juntos, reproduzem o
    template (com a versão carimbada) — a cópia local continua com tudo embutido."""
    page, assets, version = render_page(), page_assets(), page_sha256()
    css, js = asset_names(version)
    assert list(assets) == [css, js] and css == f"painel-{version[:16]}.css"
    assert f'<link rel="stylesheet" href="{css}">' in page and f'<script src="{js}"></script>' in page
    assert f'<meta name="cdp-page-sha256" content="{version}">' in page
    assert "<style>" not in page and "<script>" not in page  # sem estilo/script embutidos
    assert len(page.encode("utf-8")) < 8_000
    assert f'var PAGE_SHA = "{version}";' in assets[js] and PAGE_SHA_PLACEHOLDER not in assets[js]
    template = (Path(__file__).resolve().parents[2] / "src" / "cdp" / "workflow"
                / "painel_template.html").read_text(encoding="utf-8")
    assert assets[css].strip() in template and "var DATA_URL" in assets[js]
    assert assets[js].strip() in template.replace(PAGE_SHA_PLACEHOLDER, version)
    # a versão cobre o formato de publicação: mudar o formato obriga a republicar a página
    assert version == hashlib.sha256(f"{PAGE_LAYOUT}\n{template}".encode()).hexdigest()
    assert version != hashlib.sha256(template.encode()).hexdigest()


def test_second_write_keeps_the_page(demo, tmp_path):
    """``index.html`` só é regravado quando o template muda; ``page_changed`` compara com a
    página PUBLICADA (marcador gravado por ``mark_published``), não com o arquivo local."""
    out = tmp_path / "painel"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        first = write_painel(_rt(demo), out, now=NOW, standalone=False)
        stamp = (out / "index.html").stat().st_mtime_ns
        second = write_painel(_rt(demo), out, now=NOW, standalone=False)
        assert first["index_written"] is True and second["index_written"] is False
        assert (out / "index.html").stat().st_mtime_ns == stamp  # não regravada
        # regravado localmente (e talvez commitado), mas ainda não publicado: continua mudado
        assert first["page_changed"] is True and second["page_changed"] is True
        assert second["data_sha256"] == first["data_sha256"]  # determinístico
        assert second["local_path"] is None and not (out / "cdp_painel_local.html").exists()
        marked = mark_published(out)  # a rotina publicou a página com sucesso
        assert marked["mudou"] is True and marked["anterior"] is None
        assert marked["page_sha256"] == page_sha256() == published_page_sha(out)
        assert mark_published(out)["mudou"] is False  # idempotente
        third = write_painel(_rt(demo), out, now=NOW, standalone=False)
    assert third["page_changed"] is False and third["index_written"] is False


def test_page_change_stays_pending_until_published(demo, tmp_path):
    """Template novo gerado fora de uma sessão que publica (Codex, execução sem a ferramenta,
    publicação recusada): ``page_changed`` fica verdadeiro em TODAS as execuções seguintes até
    ``mark_published`` — o ``index.html`` local já atualizado não esconde a mudança."""
    out = tmp_path / "painel"
    template = Path(__file__).resolve().parents[2] / "src" / "cdp" / "workflow" / "painel_template.html"
    new_template = tmp_path / "template.html"
    new_template.write_text(template.read_text(encoding="utf-8").replace(
        "<title>", "<title>Nova versão — "), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_painel(_rt(demo), out, now=NOW, standalone=False)
        mark_published(out)
        old = published_page_sha(out)
        runs = [write_painel(_rt(demo), out, now=NOW, standalone=False, template_path=new_template)
                for _ in range(3)]
        assert [r["index_written"] for r in runs] == [True, False, False]
        # estilo e script da versão anterior saem da pasta; ficam só os da versão nova
        assert sorted(runs[0]["assets_removed"]) == sorted(asset_names(old))
        assert sorted(p.name for p in out.glob("painel-*")) == sorted(
            asset_names(page_sha256(new_template)))
        assert all(r["page_changed"] is True for r in runs)
        assert all(r["published_page_sha256"] == old != r["page_sha256"] for r in runs)
        assert runs[0]["page_sha256"] == page_sha256(new_template)
        data = json.loads((out / "data.json").read_text(encoding="utf-8"))
        assert data["meta"]["page_sha256"] == page_sha256(new_template)  # a página velha avisa
        mark_published(out)
        again = write_painel(_rt(demo), out, now=NOW, standalone=False, template_path=new_template)
    assert again["page_changed"] is False
    bad = tmp_path / "vazio"
    bad.mkdir()
    with pytest.raises(ValueError):
        mark_published(bad)  # sem index.html: nada a registrar


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


# ---------------------------------------------------------------- política dos limites

def _line(group, name, net, limit, long=0.0, short=0.0):
    from cdp.contracts import ExposureLine

    return ExposureLine(group=group, name=name, long=long, short=short, net=net,
                        gross=abs(net), limit=limit)


def test_exposure_status_follows_limit_policy():
    """Drift diário acima do limite é alerta (como nos limites e no monitor); excesso só para
    limite HARD no ex-ante; SOFT (estilo/commodity) nunca é excesso; sem long/short fictícios."""
    from cdp.workflow.painel import _exposure_rows

    lines = [_line("country", "BR", 0.020004, 0.02, 0.1, -0.08),
             _line("style", "value", -0.105, 0.1),
             _line("market", "commodity:gold", 0.0315, 0.03),
             _line("market", "tema:state_owned", 0.0102, 0.01, 0.02, -0.0098),
             _line("currency", "BRL", 0.3, None)]
    daily = {r["name"]: r for r in _exposure_rows(lines, daily=True)}
    ex_ante = {r["name"]: r for r in _exposure_rows(lines, daily=False)}
    assert daily["BR"]["status"] == "alerta" and daily["BR"]["breach"] is True
    assert ex_ante["BR"]["status"] == "excesso" and ex_ante["BR"]["severity"] == "HARD"
    assert ex_ante["tema:state_owned"]["status"] == "excesso"
    assert ex_ante["value"]["status"] == "alerta" and ex_ante["value"]["severity"] == "SOFT"
    assert ex_ante["commodity:gold"]["status"] == "alerta"
    assert ex_ante["BRL"]["status"] is None and ex_ante["BRL"]["severity"] is None
    for name in ("value", "commodity:gold"):
        row = ex_ante[name]
        assert row["long"] is None and row["short"] is None and row["gross"] is None
        assert row["measure"]
    assert ex_ante["BR"]["long"] == 0.1  # linhas com pontas reais ficam intactas


def test_gross_floor_is_not_a_ceiling():
    from cdp.workflow.painel import _check

    comfortable = _check("gross_min", "Gross mínimo", "b", 1.0, 0.5, "pct", "ok")
    assert comfortable["floor"] is True and comfortable["utilization"] is None
    assert comfortable["shortfall"] == 0.0 and comfortable["headroom"] == pytest.approx(0.5)
    below = _check("gross_min", "Gross mínimo", "b", 0.4735, 0.5, "pct", "alerta")
    assert below["shortfall"] == pytest.approx(0.0265) and below["utilization"] is None
    assert below["severity"] == "SOFT" and below["gate"] == "GROSS_MIN"
    ceiling = _check("net", "Net", "b", -0.009, 0.01, "pct", "ok")
    assert ceiling["floor"] is False and ceiling["utilization"] == pytest.approx(0.9)


def test_theme_and_commodity_are_separate_checks(demo):
    """Tema (HARD) e commodity (SOFT) não se misturam num "pior" só; a fatia do gross por país
    não tem gate e nunca vira excesso; ganho no pior gap não consome o limite de perda."""
    from cdp.workflow.painel import _limit_checks

    rt = _rt(demo)
    prop = rt.book.load_proposal(date(2024, 3, 4))
    lines = [x for x in prop.risk.exposures if x.group != "market"]
    lines += [_line("market", "tema:state_owned", 0.0102, 0.01, 0.02, -0.0098),
              _line("market", "commodity:gold", 0.0315, 0.03)]
    stress = {k: (abs(v) if k.startswith("Gap ") else v) for k, v in prop.risk.stress_tests.items()}
    risk = prop.risk.model_copy(update={"exposures": lines, "stress_tests": stress})
    checks = {c["id"]: c for c in _limit_checks(rt.cfg, None, prop.model_copy(
        update={"risk": risk}))}
    assert checks["theme_net"]["status"] == "excesso"
    assert checks["theme_net"]["subject"] == {"group": "market", "name": "tema:state_owned"}
    assert checks["commodity_beta"]["status"] == "alerta"
    assert "ouro" in checks["commodity_beta"]["detail"]
    if "country_gross_share" in checks:
        assert checks["country_gross_share"]["status"] != "excesso"
        assert checks["country_gross_share"]["severity"] is None
    if "country_gap_stress" in checks:
        assert checks["country_gap_stress"]["utilization"] == 0.0


def test_short_liquidity_uses_short_participation(demo, data):
    """Dias para liquidar os shorts a 15% do ADTV (como o gate LIQ_DAYS_SHORT), não a 20%."""
    rt = _rt(demo)
    week = data["risk"]["live_week"]
    prop = rt.book.load_proposal(date.fromisoformat(week))
    gate = {c.check_id: c for c in prop.compliance}
    checks = {c["id"]: c for c in data["risk"]["limit_checks"]}
    assert checks["liq_days_short"]["value"] == pytest.approx(gate["LIQ_DAYS_SHORT"].value)
    assert checks["liq_days_long"]["value"] == pytest.approx(gate["LIQ_DAYS_LONG"].value)
    liq = data["risk"]["liquidity_by_side"]
    assert liq["SHORT"]["max_days"] == pytest.approx(gate["LIQ_DAYS_SHORT"].value)
    assert liq["SHORT"]["participation"] == rt.cfg.liquidity.short_participation_rate
    lq = rt.cfg.liquidity
    for p in prop.positions:
        if p.side.value == "SHORT" and p.adtv_usd:
            exported = next(x for x in data["weeks"][-1]["proposal"]["positions"]
                            if x["issuer_id"] == p.issuer_id)
            assert exported["days_to_liquidate"] == pytest.approx(
                abs(p.notional_usd) / (lq.short_participation_rate * p.adtv_usd))
    for key in ("liquid_3d", "liquid_5d"):
        assert liq[key] is None or 0.0 <= liq[key] <= 1.0
    assert {"liquidez_3d", "liquidez_5d"} <= set(checks)


def test_latest_day_alerts_and_anchor(demo, data):
    rt = _rt(demo)
    records = rt.track().records()
    last = records[-1]
    texts = [a["text"] for a in data["status"]["alerts"] if a.get("source") == "fechamento"]
    assert len(texts) == len(last.alerts)
    assert all(any(a in t for t in texts) for a in last.alerts)
    anchor = data["track_record"]["anchor"]
    assert anchor["nav_cdp"] == records[0].nav_start_usd
    assert anchor["date"] == records[0].date.isoformat()


def test_integrity_is_not_ok_without_checks(tmp_path):
    d = painel_data(_rt(tmp_path / "nada"), now=datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    assert d["status"]["integrity"]["ok"] is None
    assert not any("integridade" in a["text"].lower() for a in d["status"]["alerts"])


def test_aux_artifacts_are_verified_against_audit_trail(demo, data, tmp_path):
    """sombra, entradas da mente e relatórios exibidos conferem com a trilha; adulterados ⇒
    integridade falha e a seção fica marcada como não verificada."""
    aux = next(c for c in data["status"]["integrity"]["checks"] if c["id"] == "auxiliares")
    assert aux["ok"] is True
    week = data["weeks"][-1]
    assert week["shadow_verified"] is True and week["inputs_verified"] is True
    assert week["report"]["verified"] is True and week["pm_decision"]["verified"] is True
    assert all(r["verified"] is True for r in data["daily_reports"] if r["published"])

    root = tmp_path / "adulterado"
    shutil.copytree(demo, root)
    wdir = root / "book" / week["week"]
    shadow = json.loads((wdir / "shadow_quant.json").read_text(encoding="utf-8"))
    shadow["optimizer"]["expected_alpha_annual"] = 0.5
    (wdir / "shadow_quant.json").write_text(json.dumps(shadow), encoding="utf-8")
    pm = json.loads((wdir / "inputs" / "pm_decision.json").read_text(encoding="utf-8"))
    pm["market_view"] = "texto trocado depois da decisão"
    (wdir / "inputs" / "pm_decision.json").write_text(json.dumps(pm), encoding="utf-8")
    md = root / "reports" / "weekly" / week["week"] / "relatorio.md"
    md.write_text(md.read_text(encoding="utf-8") + "\nadulterado\n", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = painel_data(_rt(root), now=NOW)
    aux = next(c for c in d["status"]["integrity"]["checks"] if c["id"] == "auxiliares")
    assert aux["ok"] is False and d["status"]["integrity"]["ok"] is False
    w = next(x for x in d["weeks"] if x["week"] == week["week"])
    assert w["shadow_verified"] is False and w["shadow"]["verified"] is False
    assert w["inputs_verified"] is False and w["pm_decision"]["verified"] is False
    assert w["report"]["verified"] is False
    assert any("integridade" in a["text"].lower() for a in d["status"]["alerts"])


def test_backtest_costs_have_pnl_sign_and_bad_files_become_issues(demo, tmp_path):
    reports = tmp_path / "reports"
    good = reports / "backtest" / "bt_ok"
    good.mkdir(parents=True)
    (good / "metrics.json").write_text(json.dumps({"metrics": {"sharpe": 1.0}}), encoding="utf-8")
    (good / "daily.csv").write_text("date,ret_net,nav,cost,borrow,financing\n"
                                    "2024-01-01,-0.001,99.9,0.001,0.0002,0.0001\n"
                                    "2024-01-02,0.0,99.9,0.0,0.0002,0.0001\n", encoding="utf-8")
    bad = reports / "backtest" / "bt_ruim"
    bad.mkdir(parents=True)
    (bad / "metrics.json").write_text(json.dumps({"metrics": {}}), encoding="utf-8")
    (bad / "daily.csv").write_text("date,ret_net,nav\n2024-01-01,0.0,100.0\n2024-0\n"
                                   "2024-01-03,0.0,abc\n", encoding="utf-8")
    (bad / "ic.csv").write_text("date,composite\nxx,0.1\n2024-01-08,-0.05\n", encoding="utf-8")
    lst = reports / "backtest" / "bt_lista"
    lst.mkdir(parents=True)
    (lst / "metrics.json").write_text("[1]", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = painel_data(_rt(demo, reports), now=NOW)
    runs = {r["id"]: r for r in d["backtests"]["runs"]}
    nw = runs["bt_ok"]["nav_weekly"]
    assert nw["cum_cost_pnl"][-1] == pytest.approx(-0.001)
    assert nw["cum_borrow_pnl"][-1] == pytest.approx(-0.0004)
    assert nw["cum_financing"][-1] == pytest.approx(0.0002)
    assert "cum_cost" not in nw and all(v <= 0 for v in nw["cum_cost_pnl"])
    assert runs["bt_ruim"]["nav_weekly"] is None  # valor não numérico: apontamento, não exceção
    assert runs["bt_ruim"]["ic"]["summary"]["composite"]["n"] == 1
    assert "bt_lista" not in runs
    scopes = " ".join(i["scope"] + " " + i["message"] for i in d["issues"])
    assert "bt_ruim" in scopes and "bt_lista" in scopes and "data inválida" in scopes


# ---------------------------------------------------------------- publicação (artifact)

NOW6 = datetime(2024, 3, 12, 22, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def demo6(tmp_path_factory):
    """Livro sintético com duas semanas e seis pregões (o orçamento vale num livro "real")."""
    from cdp.workflow.demo import run_demo

    out = tmp_path_factory.mktemp("painel_demo6")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_demo(out, days=6)
    return out


@pytest.fixture(scope="module")
def full6(demo6):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return painel_data(_rt(demo6), now=NOW6)


def _floats_outside(obj, skip: tuple[str, ...] = (), path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if not any(p.startswith(s) for s in skip):
                yield from _floats_outside(v, skip, p)
    elif isinstance(obj, list):
        for v in obj:
            yield from _floats_outside(v, skip, path + "[]")
    elif isinstance(obj, float):
        yield obj


def _assert_budget(pub):
    text = dump_publicacao(pub)
    assert len(text.encode("utf-8")) <= DATA_MAX_BYTES, len(text.encode("utf-8"))
    assert max_line(text) <= DATA_MAX_LINE, max_line(text)
    assert cabe(text)
    return text


def test_publication_budget_on_demo_book(demo6, full6, tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = write_painel(_rt(demo6), tmp_path / "painel", now=NOW6)
    text = (tmp_path / "painel" / "data.json").read_text(encoding="utf-8")
    pub = json.loads(text)
    _assert_budget(pub)
    assert res["data_bytes"] <= DATA_MAX_BYTES and res["data_max_line"] <= DATA_MAX_LINE
    meta = expandir(pub["meta"])
    assert meta["profile"] == "publicacao" and meta["is_synthetic"] is True
    assert "DADOS SIMULADOS" in meta["data_notice"]
    assert meta["publication"]["nivel"] == res["nivel_publicacao"]
    assert meta["truncations"] and all({"campo", "regra", "n"} <= set(c) for c in meta["truncations"])
    full = expandir(pub)
    assert set(full) == SECTIONS
    assert len(full["weeks"]) == 2 and full["latest_day"]["date"] == "2024-03-11"
    assert full["status"]["phase"] == full6["status"]["phase"]


def test_publication_numbers_equal_the_full_export(full6):
    """Números nunca alterados: todo float publicado existe no retrato completo (exceto os meses
    consolidados, agregados novos calculados em código) e os itens mantidos são idênticos."""
    pub = expandir(publicacao(full6))
    allowed = set(_floats_outside(full6))
    published = list(_floats_outside(pub, skip=(".track_record.rollup",)))
    assert published and not [x for x in published if x not in allowed]
    ld, ld0 = pub["latest_day"], full6["latest_day"]
    assert {p["issuer_id"]: p["weight"] for p in ld["positions"]} == {
        p["issuer_id"]: p["weight"] for p in ld0["positions"]}
    assert ld["nav_end"] == ld0["nav_end"] and ld["risk"]["ex_ante_vol"] == ld0["risk"]["ex_ante_vol"]
    assert pub["risk"]["limit_checks"] == full6["risk"]["limit_checks"]
    assert pub["risk"]["ex_ante"]["exposures"] == full6["risk"]["ex_ante"]["exposures"]
    recs0 = {r["date"]: r for r in full6["track_record"]["records"]}
    for r in pub["track_record"]["records"]:
        r0 = recs0[r["date"]]
        assert (r["nav_end"], r["ret"], r["pnl"]) == (r0["nav_end"], r0["ret"], r0["pnl"])
        assert r["pnl_components"] == r0["pnl_components"]
        assert r["risk"]["drawdown"] == r0["risk"]["drawdown"]
    assert pub["track_record"]["compare"] == full6["track_record"]["compare"]
    assert pub["track_record"]["stats"] == full6["track_record"]["stats"]
    w, w0 = pub["weeks"][-1], full6["weeks"][-1]
    assert w["decision"] == w0["decision"] and w["pm_decision"] == w0["pm_decision"]
    assert [c["value"] for c in w["proposal"]["compliance"]["checks"]] == [
        c["value"] for c in w0["proposal"]["compliance"]["checks"]]
    assert w["proposal"]["summary"] == w0["proposal"]["summary"]
    pos0 = {p["issuer_id"]: p for p in w0["proposal"]["positions"]}
    for p in w["proposal"]["positions"]:
        assert all(p[k] == pos0[p["issuer_id"]][k] for k in p), p["issuer_id"]
    assert w["shadow"]["comparison"]["metrics"] == w0["shadow"]["comparison"]["metrics"]


def test_publication_index_page_has_empty_data_and_fetch_fallback(tmp_path):
    page = render_page()
    assert page.count(EMPTY_DATA_ELEMENT) == 1 and PLACEHOLDER not in page
    assert page_version(page) == page_sha256() and PAGE_SHA_PLACEHOLDER not in page
    assert len(page.encode("utf-8")) <= PAGE_MAX_BYTES and max_line(page) <= PAGE_MAX_LINE
    template = (Path(__file__).resolve().parents[2] / "src" / "cdp" / "workflow"
                / "painel_template.html").read_text(encoding="utf-8")
    for needle in ('var DATA_URL = "data.json"', 'window.fetch(DATA_URL, { cache: "no-store" })',
                   "Carregando o painel", "Não foi possível carregar data.json", "Tentar de novo",
                   "_colunas", "_partes", "_faltam", "_rep", "_igual", "function unrep",
                   'var PAGE_SCHEMA = "cdp-painel/2"', 'var PAGE_SHA = "__CDP_PAGE_SHA256__"',
                   "META.page_sha256 !== PAGE_SHA", "Página desatualizada",
                   # eixo x proporcional às datas quando meses consolidados precedem os pregões
                   "function timeScale", "timeX: ROLLUP.length > 0", "timeX: !!ns.zone",
                   "meses consolidados (fim de mês)", "function reportPath"):
        assert needle in template, needle
    from cdp.workflow.painel import SCHEMA_VERSION

    assert f'var PAGE_SCHEMA = "{SCHEMA_VERSION}"' in template  # página e dados da mesma versão


def test_publication_compact_forms_roundtrip():
    """Colunas e partes são formas sem perda: expandir(compactado) == original."""
    from cdp.workflow.painel_publicacao import _columnar, _pack, _split

    long = ('linha com "aspas", \\barra e acentuação — ' * 40 + "\n") * 6 + "x" * 3_500
    rows = [{"a": 1.5, "b": {"c": None, "d": [1, 2]}, "t": "curto"},
            {"a": None, "b": None, "t": long, "_truncado": True},
            {"a": 2.0, "b": {"c": 3.25, "d": []}, "e": {}},
            {"a": -0.0, "b": {"c": 1e-12, "d": [{"x": 1}]}, "t": None}]
    col = _columnar(rows)  # linhas heterogêneas: colunas ausentes em _faltam
    assert col["_n"] == 4 and col["_faltam"] and expandir(col) == rows
    assert _columnar([{"a.b": 1}, {"a.b": 2}, {"a.b": 3}]) is None  # ponto na chave: ambíguo
    table = [{"issuer_id": f"ID{i:02d}", "weight": i / 100, "side": "LONG",
              "risk": {"vol": 0.1 * i, "beta": None}} for i in range(30)]
    obj = {"tabela": table, "linhas": rows, "texto": long, "num": [0.1, 0.2, 0.3], "vazio": [],
           "ponto": [{"a.b": 1}, {"a.b": 2}, {"a.b": 3}]}
    packed = _split(_pack(copy.deepcopy(obj)))
    assert "_colunas" in packed["tabela"] and "_partes" in packed["texto"]
    assert expandir(packed) == obj
    text = dump_publicacao(packed)
    assert max_line(text) <= DATA_MAX_LINE and len(text) < len(dump_publicacao(obj))
    assert "".join(partes(long)) == long
    assert all(len(json.dumps(p, ensure_ascii=False)) - 2 <= 1_000 for p in partes(long))
    # colunas em corridas: só quando encurta; 1, 1.0, True e -0.0 nunca se misturam
    runs = [{"k": "daily", "v": v, "n": 1.5} for v in (1, 1, 1.0, True, -0.0, 0.0, None, None)] * 4
    packed = _pack(copy.deepcopy(runs))
    assert "_rep" in packed["_colunas"]["k"] and "_rep" in packed["_colunas"]["n"]
    back = expandir(json.loads(dump_publicacao(packed)))
    assert back == runs and [type(r["v"]) for r in back] == [type(r["v"]) for r in runs]
    assert [str(r["v"]) for r in back] == [str(r["v"]) for r in runs]  # -0.0 continua -0.0
    # período idêntico a um irmão: {"_igual": ...} com os próprios campos
    alias = {"itd": {"label": "Desde o início", "ret": 0.01, "x": [1, 2]},
             "mtd": {"_igual": "itd", "label": "Mês"}}
    assert expandir(alias) == {"itd": alias["itd"], "mtd": {"label": "Mês", "ret": 0.01, "x": [1, 2]}}


def _big_full(full):
    """Pesquisa artificialmente grande (notas longas) e track record longo sobre o retrato real."""
    big = copy.deepcopy(full)
    w = big["weeks"][-1]
    book = [p["issuer_id"] for p in w["proposal"]["positions"]]
    text = ("Tese longa com fatos, contexto e riscos detalhados do emissor. " * 80).strip()
    notes = []
    for i in range(400):
        iid = book[i % len(book)] if i < 2 * len(book) else f"FORA{i:03d}"
        notes.append({
            "note_id": f"n{i}", "issuer_id": iid, "role": "short_risk" if i % 2 else "fundamental",
            "stance": (i % 5) - 2, "confidence": 0.25 + (i % 4) / 10, "horizon_weeks": 4 + i % 9,
            "thesis": text, "bull_points": [text[:600]] * 6, "bear_points": [text[:600]] * 6,
            "key_risks": [f"Risco {k}: {text[:450]}" for k in range(7)],
            "catalysts": [{"description": f"Evento {k}: {text[:450]}", "direction": "positive",
                           "expected_date": "2024-04-01"} for k in range(6)],
            "squeeze": ({"verdict": "caution", "rationale": text[:900], "si_pct_float": 0.125}
                        if i % 2 else None),
            "evidence": [{"kind": "source", "ref_id": f"https://exemplo.org/{i}/{k}",
                          "url": f"https://exemplo.org/{i}/{k}", "note": text[:160]}
                         for k in range(8)],
            "n_evidence": 11, "provider": "imported:demo", "created_at": "2024-03-11T14:00:00+00:00"})
    w["research"]["notes"] = notes
    w["research"]["notes_detail"] = True
    w["research"]["views"] = [{"issuer_id": n["issuer_id"], "source": "ai", "score": 1,
                               "confidence": 0.5, "no_short": False, "no_long": False,
                               "max_abs_weight": None, "rationale": text, "author": "claude-code",
                               "note_ids": ["n1", "n2"]} for n in notes[:150]]
    w["research"]["macro"] = [{
        "note_id": f"m{k}", "scope": c, "stance": 0, "regime": "neutro", "summary": text * 2,
        "key_events": [{"description": text[:500], "direction": "uncertain", "expected_date": None}
                       for _ in range(9)],
        "risks": [text[:500]] * 9, "portfolio_implications": [text[:500]] * 9,
        "evidence": notes[0]["evidence"], "n_evidence": 20, "provider": "imported:demo",
        "created_at": "2024-03-11T14:00:00+00:00"} for k, c in enumerate(
            ("BR", "MX", "CL", "CO", "PE", "AR", "LATAM"))]
    w["pm_decision"]["views"] = [{"issuer_id": iid, "stance": 1, "conviction": 3,
                                  "horizon_weeks": 8, "rationale": text[:1_500], "evidence": []}
                                 for iid in book]
    tr = big["track_record"]
    base_recs, base_cmp = tr["records"], tr["compare"]
    day, dates = date(2023, 1, 2), []
    while len(dates) < 320:
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day = day.fromordinal(day.toordinal() + 1)
    tr["records"] = [{**copy.deepcopy(base_recs[i % len(base_recs)]), "date": d, "ret": 0.001 * (i % 7 - 3)}
                     for i, d in enumerate(dates)]
    tr["compare"] = [{**copy.deepcopy(base_cmp[i % len(base_cmp)]), "date": d}
                     for i, d in enumerate(dates)] if base_cmp else []
    tr["n_days"] = len(dates)
    rep = big["daily_reports"][0]
    big["daily_reports"] = [{**copy.deepcopy(rep), "date": d,
                             "commentary": {**rep["commentary"], "markdown": text * 3}}
                            for d in reversed(dates[-60:])]
    big["reports_index"] = [{"kind": "daily", "date": d, "has_md": True, "has_html": True,
                             "md_sha256": hashlib.sha256(d.encode()).hexdigest()}
                            for d in reversed(dates)]
    big["meta"]["data_hash"] = "0" * 64
    return big


def test_publication_budget_with_large_research_and_long_track(full6):
    big = _big_full(full6)
    pub = publicacao(big)
    _assert_budget(pub)
    meta = expandir(pub["meta"])
    # pesquisa artificialmente enorme: os cortes caem nos textos da pesquisa, não no histórico
    assert meta["publication"]["nivel"] <= 3
    out = expandir(pub)
    tr = out["track_record"]
    kept = meta["publication"]["limites"]["pregoes"]
    assert len(tr["records"]) == kept >= PREGOES_MINIMOS and tr["rollup"]
    assert len(out["daily_reports"]) >= COMENTARIOS_MINIMOS
    assert sum(r["n_days"] for r in tr["rollup"]) + kept == 320
    tail = big["track_record"]["records"][-kept:]
    assert [(r["date"], r["nav_end"], r["ret"]) for r in tr["records"]] == [
        (r["date"], r["nav_end"], r["ret"]) for r in tail]
    # meses consolidados em código: retorno composto e NAV do último pregão do mês
    first = tr["rollup"][0]
    month = [r for r in big["track_record"]["records"] if r["date"].startswith(first["month"])]
    g = 1.0
    for r in month:
        g *= 1.0 + r["ret"]
    assert first["ret"] == pytest.approx(g - 1.0) and first["nav_end"] == month[-1]["nav_end"]
    assert first["n_days"] == len(month)
    cuts = {c["campo"] for c in meta["truncations"]}
    assert "track_record.records" in cuts and "weeks[].research.notes[]" in cuts


def test_publication_level0_rules(full6):
    """Nível 0 (regras do artifact), mesmo quando não cabe: limites por campo e marcações."""
    big = _big_full(full6)
    out = expandir(compactar(big, 0))
    lim = NIVEIS[0]
    r = out["weeks"][-1]["research"]
    assert r["notes"] and r["notes_table"]
    book = {p["issuer_id"] for p in big["weeks"][-1]["proposal"]["positions"]}
    assert {n["issuer_id"] for n in r["notes"]} <= book
    assert all(not n["issuer_id"].startswith("FORA") for n in r["notes"])
    for n in r["notes"]:
        assert n["_truncado"] is True and len(n["thesis"]) <= lim.tese_chars
        assert n["thesis"].endswith("…")
        assert len(n["catalysts"]) <= 3 and len(n["key_risks"]) <= 3 and len(n["evidence"]) <= 3
        assert n["n_evidence"] == 11 and "bull_points" not in n
        assert all(e["url"].startswith("https://") for e in n["evidence"])
    assert {"issuer_id", "role", "stance", "confidence", "horizon_weeks", "squeeze_verdict"} == set(
        r["notes_table"][0])
    for m in r["macro"]:
        assert len(m["summary"]) <= 1_200 and m["_truncado"] is True
        assert max(len(m["key_events"]), len(m["risks"]), len(m["portfolio_implications"])) <= 5
    assert all(len(c["commentary"]["markdown"]) <= 4_000 for c in out["daily_reports"])
    assert len(out["daily_reports"]) == 10 and all("report_markdown" not in x
                                                   for x in out["daily_reports"])
    assert len(out["reports_index"]) == 320 and all(x["has_md"] and x["md_sha256"]
                                                    for x in out["reports_index"])
    # o caminho não se repete em cada linha: a página o monta (reports_dir/kind/date/relatorio.md)
    assert all("path" not in x for x in out["reports_index"])
    assert out["meta"]["publication"]["reports_dir"] == "reports"
    assert report_path("reports", "daily", "2024-03-11") == "reports/daily/2024-03-11/relatorio.md"
    assert len(out["track_record"]["records"]) == 90 and len(out["audit"]["events"]) <= 20
    w = out["weeks"][-1]
    assert "markdown" not in w["report"] and w["report"]["sha256"]
    assert len(w["shadow"]["positions"]) <= 20


def test_publication_previous_week_is_slim_at_level_1(full6):
    """Nível 1: a semana anterior fica enxuta (decisão, leitura do PM e hashes íntegros; sem
    gates aprovados, risco ex-ante nem notas da pesquisa); a semana vigente não muda."""
    lvl0, lvl1 = expandir(compactar(full6, 0)), expandir(compactar(full6, 1))
    old, new = lvl1["weeks"]
    assert old["detail"] == "completo" and old["detail_publicacao"] == "enxuta"
    assert "detail_publicacao" not in new
    w0 = full6["weeks"][0]
    assert old["decision"] == w0["decision"] and old["pm_decision"] == w0["pm_decision"]
    assert "risk" not in old["proposal"] and all(
        c["passed"] is False for c in old["proposal"]["compliance"]["checks"])
    assert old["proposal"]["compliance"]["n"] == w0["proposal"]["compliance"]["n"]
    assert old["research"]["resumo"] is True and old["research"]["notes"] == []
    assert new["proposal"]["compliance"]["n"] == len(new["proposal"]["compliance"]["checks"])
    assert all("details" not in c for c in new["proposal"]["compliance"]["checks"]
               if c["passed"] is True)  # nível 1: sem o texto dos gates aprovados
    assert any("details" in c for c in lvl0["weeks"][-1]["proposal"]["compliance"]["checks"]
               if c["passed"] is True)
    # a semana vigente nunca repete o risco ex-ante (idêntico a risk.ex_ante)
    assert "risk" not in lvl0["weeks"][-1]["proposal"] and lvl0["risk"]["ex_ante"]


def test_publication_older_weeks_are_one_line_summaries(full6):
    pub = expandir(compactar(full6, 2))  # nível 2: só a semana mais recente em detalhe
    old, new = pub["weeks"]
    assert old["detail"] == "resumo" and new["detail"] == "completo"
    assert set(old) <= {"week", "detail", "stage", "state", "executed", "path_taken",
                        "shadow_verified", "inputs_verified", "decision", "pm_decision",
                        "proposal", "performance", "report"}
    w0 = full6["weeks"][0]
    assert old["decision"]["approval_hash"] == w0["decision"]["approval_hash"]
    assert old["proposal"]["summary"]["ex_ante_vol"] == w0["proposal"]["summary"]["ex_ante_vol"]
    assert old["pm_decision"]["posture_label"] == w0["pm_decision"]["posture_label"]


def _txt(tag: str, n: int) -> str:
    return (f"{tag}: fatos, contexto, riscos e catalisadores com números citados por fato. " * 60)[:n]


def _bdays(start: date, n: int) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d = d.fromordinal(d.toordinal() + 1)
    return out


def _year_full(full, *, n_days=250, n_weeks=52, n_comm=60, n_runs=5, n_pos=46):
    """Livro sintético de ~1 ano no tamanho do livro real: pesquisa com 156 notas e 7 notas
    macro, 46 posições, 35 visões e 28 exclusões do PM, 250 pregões, 60 comentários de 3.500
    caracteres e ``n_runs`` execuções de backtest com a curva semanal."""
    y = copy.deepcopy(full)
    dates = _bdays(date(2023, 3, 6), n_days)
    mondays = [d for d in dates if date.fromisoformat(d).weekday() == 0][-n_weeks:]
    base = y["weeks"][-1]
    pos0 = base["proposal"]["positions"]
    positions = [{**copy.deepcopy(pos0[i % len(pos0)]), "issuer_id": f"P{i:03d}",
                  "name": f"Emissor {i:03d}"} for i in range(n_pos)]
    book = [p["issuer_id"] for p in positions]
    notes = [{
        "note_id": f"n{i}", "issuer_id": book[i] if i < n_pos else f"FORA{i:03d}",
        "role": ("fundamental", "short_risk", "catalyst")[i % 3], "stance": i % 5 - 2,
        "confidence": 0.3 + (i % 5) / 10, "horizon_weeks": 4 + i % 9, "thesis": _txt(f"Tese {i}", 900),
        "bull_points": [_txt("a favor", 300)] * 3, "bear_points": [_txt("contra", 300)] * 3,
        "key_risks": [_txt(f"risco {k}", 220) for k in range(4)],
        "catalysts": [{"description": _txt(f"evento {k}", 220), "direction": "positive",
                       "expected_date": "2024-01-15"} for k in range(4)],
        "squeeze": ({"verdict": "caution", "rationale": _txt("squeeze", 400), "si_pct_float": 0.1}
                    if i % 3 == 1 else None),
        "evidence": [{"kind": "source", "ref_id": f"https://exemplo.org/{i}/{k}",
                      "url": f"https://exemplo.org/{i}/{k}", "note": _txt("fonte", 120)}
                     for k in range(8)],
        "n_evidence": 8, "provider": "imported:demo", "created_at": "2024-01-08T14:00:00+00:00"}
        for i in range(156)]
    macro = [{"note_id": f"m{k}", "scope": c, "stance": k % 3 - 1, "regime": "neutro",
              "summary": _txt(f"Macro {c}", 1_500),
              "key_events": [{"description": _txt("evento", 250), "direction": "uncertain",
                              "expected_date": None} for _ in range(6)],
              "risks": [_txt("risco macro", 250)] * 6,
              "portfolio_implications": [_txt("implicação", 250)] * 6,
              "evidence": notes[0]["evidence"][:5], "n_evidence": 12, "provider": "imported:demo",
              "created_at": "2024-01-08T14:00:00+00:00"}
             for k, c in enumerate(("BR", "MX", "CL", "CO", "PE", "AR", "LATAM"))]
    views = [{"issuer_id": n["issuer_id"], "source": "ai", "score": n["stance"], "confidence": 0.5,
              "no_short": False, "no_long": False, "max_abs_weight": None,
              "rationale": _txt("visão", 300), "author": "demo", "note_ids": [n["note_id"]]}
             for n in notes[:82]]
    pm = {**copy.deepcopy(base["pm_decision"]),
          "market_view": _txt("Visão de mercado", 1_500), "what_changed": _txt("Mudanças", 1_500),
          "evaluation_last_week": _txt("Avaliação", 1_500),
          "views": [{"issuer_id": iid, "stance": 1, "conviction": 3, "horizon_weeks": 8,
                     "rationale": _txt("racional", 600),
                     "evidence": [{"id": f"e{k}", "url": f"https://exemplo.org/pm/{k}"}
                                  for k in range(3)]} for iid in book[:35]],
          "exclusions": [{"issuer_id": f"FORA{k:03d}", "no_long": True, "no_short": False,
                          "reason": _txt("exclusão", 300)} for k in range(28)],
          "position_journal": [{"issuer_id": iid, "thesis": _txt("tese", 400),
                                "invalidation_criteria": _txt("invalida", 400),
                                "premortem": _txt("premortem", 400)} for iid in book[:6]]}
    trade0 = (base["proposal"].get("trades") or [{}])[0]
    weeks = []
    for i, wk in enumerate(mondays):
        w = copy.deepcopy(base)
        w.update({"week": wk, "detail": "completo" if i >= len(mondays) - 8 else "resumo",
                  "pm_decision": copy.deepcopy(pm)})
        w["proposal"]["positions"] = copy.deepcopy(positions)
        w["proposal"]["trades"] = [{**copy.deepcopy(trade0), "issuer_id": iid} for iid in book]
        recent = i >= len(mondays) - 2  # o completo só traz as notas das 2 semanas mais recentes
        w["research"].update({"macro": copy.deepcopy(macro), "views": copy.deepcopy(views),
                              "notes": copy.deepcopy(notes) if recent else [],
                              "notes_detail": recent})
        weeks.append(w)
    y["weeks"] = weeks
    y["risk"]["live_week"] = mondays[-1]
    for key in ("live_book_week", "current_week", "latest_decision_week"):
        if key in y["status"]:
            y["status"][key] = mondays[-1]
    tr = y["track_record"]
    recs, cmp = tr["records"], tr["compare"]
    tr["records"] = [{**copy.deepcopy(recs[i % len(recs)]), "date": d, "ret": 0.0004 * (i % 9 - 4),
                      "live_book_week": max((m for m in mondays if m <= d), default=None)}
                     for i, d in enumerate(dates)]
    tr["compare"] = [{**copy.deepcopy(cmp[i % len(cmp)]), "date": d} for i, d in enumerate(dates)]
    tr["n_days"] = n_days
    ld = y["latest_day"]
    lp = ld["positions"]
    ld["positions"] = [{**copy.deepcopy(lp[i % len(lp)]), "issuer_id": p["issuer_id"],
                        "name": p["name"]} for i, p in enumerate(positions)]
    ld["date"] = dates[-1]
    rep = y["daily_reports"][0]
    y["daily_reports"] = [{**copy.deepcopy(rep), "date": d,
                           "commentary": {**rep["commentary"], "markdown": _txt("Comentário", 3_500)}}
                          for d in reversed(dates[-n_comm:])]
    y["reports_index"] = (
        [{"kind": "daily", "date": d, "has_md": True, "has_html": True,
          "md_sha256": hashlib.sha256(d.encode()).hexdigest()} for d in reversed(dates)]
        + [{"kind": "weekly", "date": w, "has_md": True, "has_html": True,
            "md_sha256": hashlib.sha256(w.encode()).hexdigest()} for w in mondays])
    nav_dates = _bdays(date(2019, 1, 4), 1_500)[::5]
    y["backtests"] = {"available": True, "documents": [], "runs": [{
        "id": f"2023-{1 + k // 28:02d}-{1 + k % 28:02d}/V{k}", "label": f"Variante {k}",
        "variant": f"V{k}", "description": _txt("descrição", 200), "overrides": {},
        "signal_weights": {"value": 0.3}, "metrics": {f"m{j}": 0.01 * (j + k) for j in range(25)},
        "is_synthetic": True,
        "notes": [_txt("limitação", 280)] * 4 + [f"2023-01-0{j}: relaxada" for j in range(1, 8)],
        "provenance": {"config_hash": f"c{k}", "data_notice": "DADOS SIMULADOS"},
        "nav_weekly": {"date": nav_dates, "nav": [1e8 + j * 1e4 for j in range(len(nav_dates))],
                       "drawdown": [-0.001 * (j % 7) for j in range(len(nav_dates))]},
        "ic": {"summary": {"value": {"n": 50, "mean": 0.02, "std": 0.1, "t_stat": 1.4,
                                     "pct_positive": 0.55}},
               "cumulative": {"date": nav_dates, "value": [0.01 * j for j in range(len(nav_dates))]}},
        "files": {}, "n_daily_obs": 1_500} for k in range(n_runs)]}
    y["meta"]["data_hash"] = "0" * 64
    return y


def test_publication_levels_are_pinned(full6):
    """Regressão do orçamento: o livro de demonstração (2 semanas, 6 pregões) cabe no nível 0
    (regras do artifact, 2 semanas completas) e um livro de ~1 ano no tamanho do real cabe até o
    nível 3 com ao menos 75 pregões em linhas diárias e 7 comentários do dia."""
    demo_pub = publicacao(full6)
    _assert_budget(demo_pub)
    assert demo_pub["meta"]["publication"]["nivel"] == 0
    assert [w["detail"] for w in expandir(demo_pub["weeks"])] == ["completo", "completo"]
    year = _year_full(full6)
    pub = publicacao(year)
    _assert_budget(pub)
    nivel = pub["meta"]["publication"]["nivel"]
    assert nivel <= 3, nivel
    out = expandir(pub)
    assert len(out["track_record"]["records"]) >= 75 and len(out["daily_reports"]) >= 7
    assert sum(r["n_days"] for r in out["track_record"]["rollup"]) + len(
        out["track_record"]["records"]) == 250
    # o que sai antes do histórico: textos da pesquisa, detalhe das semanas anteriores, etc.
    w = out["weeks"][-1]
    assert w["detail"] == "completo" and w["pm_decision"]["views"]
    assert w["proposal"]["positions"] and w["decision"]["approval_hash"]
    cuts = {c["campo"] for c in out["meta"]["truncations"]}
    assert {"weeks[].proposal.compliance.checks[].details", "weeks[].research.views"} <= cuts


def test_ladder_cuts_low_value_content_before_daily_history():
    """Os primeiros níveis cortam o que a página quase não mostra; o histórico diário (pregões
    em linhas e comentários do dia) só cai abaixo do mínimo nos dois últimos níveis."""
    for i, lim in enumerate(NIVEIS[:7]):
        assert lim.pregoes >= PREGOES_MINIMOS and lim.comentarios >= COMENTARIOS_MINIMOS, i
    assert NIVEIS[-1].pregoes < PREGOES_MINIMOS and NIVEIS[-1].comentarios < COMENTARIOS_MINIMOS
    n0, n1, n2 = NIVEIS[:3]
    assert (n0.detalhes_aprovadas, n0.visao_chars, n0.semana_anterior_detalhe) == (True, 200, True)
    assert (n1.detalhes_aprovadas, n1.visao_chars, n1.visoes_fora_carteira,
            n1.semana_anterior_detalhe) == (False, 0, False, False)
    assert (n1.pregoes, n1.comentarios, n1.notas_completas) == (n0.pregoes, n0.comentarios, True)
    assert not n2.mandato_tabela and n2.backtests_execucoes < n0.backtests_execucoes
    assert (n2.pregoes, n2.comentarios) == (n0.pregoes, n0.comentarios)
    keys = ("pregoes", "comentarios", "comentario_chars", "semanas_resumo", "auditoria",
            "tese_chars", "resumo_macro_chars", "backtests_execucoes", "posicoes_sombra")
    for a, b in zip(NIVEIS, NIVEIS[1:], strict=False):  # cada nível só aperta
        assert all(getattr(b, k) <= getattr(a, k) for k in keys)


def test_backtest_runs_are_bounded(full6):
    """A calibração mensal acrescenta execuções: só a escolhida e as mais recentes são
    publicadas (as demais entram na contagem), e o bloco não cresce com o número de execuções."""
    few, many = _year_full(full6, n_runs=5), _year_full(full6, n_runs=125)
    lim = NIVEIS[0]
    a = expandir(compactar(few, 0))["backtests"]
    b = expandir(compactar(many, 0))["backtests"]
    assert a["n_runs"] == 5 and b["n_runs"] == 125
    assert len(a["runs"]) == 5 and len(b["runs"]) == 1 + lim.backtests_execucoes
    sel = b["selected"]["id"]
    assert sel == many["backtests"]["runs"][-1]["id"]  # sem config_hash nem nota: a mais recente
    ids = [r["id"] for r in many["backtests"]["runs"]]
    assert [r["id"] for r in b["runs"]] == ids[-(1 + lim.backtests_execucoes):]
    full_runs = {r["id"]: r for r in many["backtests"]["runs"]}
    assert all(r["metrics"] == full_runs[r["id"]]["metrics"] for r in b["runs"])
    cut = [c for c in expandir(compactar(many, 0))["meta"]["truncations"]
           if c["campo"] == "backtests.runs"]
    assert cut and cut[0]["n"] == 125 - len(b["runs"])
    size = lambda x: len(dump_publicacao(x))  # noqa: E731
    assert size(compactar(many, 0)["backtests"]) <= size(compactar(few, 0)["backtests"]) * 1.4
    pub = publicacao(many)
    _assert_budget(pub)
    assert pub["meta"]["publication"]["nivel"] <= 3


def test_chosen_backtest_rule():
    runs = [{"id": "a/A", "variant": "A", "provenance": {"config_hash": "x"}},
            {"id": "a/B", "variant": "B", "provenance": {"config_hash": "y"}},
            {"id": "a/C", "variant": "C", "provenance": {"config_hash": "z"}}]
    doc = [{"path": "a/CALIBRACAO.md", "markdown": "| **B** | ... \nA variante B foi escolhida."}]
    assert chosen_backtest(runs, doc, "z") == ("a/C", "configuração vigente (config_hash)")
    assert chosen_backtest(runs, doc, "nenhum")[0] == "a/B"
    assert chosen_backtest(runs, [], None) == ("a/C", "execução mais recente")
    assert chosen_backtest([], doc, "z") == (None, None)


def test_publication_backtests_keep_metrics_and_the_chosen_curve(demo, tmp_path):
    reports = tmp_path / "reports"
    shutil.copytree(demo / "reports", reports)
    for name, variant in (("bt_a", "A"), ("bt_b", "B")):
        run = reports / "backtest" / name
        run.mkdir(parents=True)
        (run / "metrics.json").write_text(json.dumps(
            {"variant": variant, "metrics": {"sharpe": 0.5 if variant == "A" else 0.7},
             "notes": [f"2024-01-0{k}: relaxamentos" for k in range(1, 9)] + ["limitação"] * 3,
             "provenance": {"data_notice": "DADOS SIMULADOS — teste", "config_hash": "q"}}),
            encoding="utf-8")
        lines = ["date,ret_net,nav"] + [f"2024-0{m}-{d:02d},0.0,{100 + m + d / 100}"
                                         for m in (1, 2, 3) for d in (5, 12, 19, 26)]
        (run / "daily.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (run / "ic.csv").write_text("date,composite\n2024-01-05,0.1\n2024-01-12,-0.05\n",
                                    encoding="utf-8")
    (reports / "backtest" / "CALIBRACAO.md").write_text("A variante B foi escolhida.\n",
                                                        encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        full = painel_data(_rt(demo, reports), now=NOW)
    bt = expandir(publicacao(full))["backtests"]
    assert bt["selected"]["id"] == "bt_b" and "CALIBRACAO.md" in bt["selected"]["criterio"]
    runs = {r["id"]: r for r in bt["runs"]}
    full_runs = {r["id"]: r for r in full["backtests"]["runs"]}
    for rid, r in runs.items():
        assert r["metrics"] == full_runs[rid]["metrics"]
    b, a = runs["bt_b"], runs["bt_a"]
    assert b["selected"] is True and "nav_weekly" not in b and "weekly" not in b
    nw = full_runs["bt_b"]["nav_weekly"]
    assert b["nav_monthly"]["date"] == ["2024-01-26", "2024-02-23", "2024-03-29"]
    for k in ("nav", "drawdown"):
        assert b["nav_monthly"][k] == [nw[k][nw["date"].index(d)] for d in b["nav_monthly"]["date"]]
    assert b["ic"] == {"summary": full_runs["bt_b"]["ic"]["summary"]}
    assert b["notes"][:3] == ["limitação"] * 3 and len(b["notes"]) == 8 and b["n_notes"] == 11
    assert set(a) <= {"id", "label", "variant", "description", "overrides", "signal_weights",
                      "metrics", "is_synthetic", "n_notes"}
    assert bt["documents"] == [{"path": "CALIBRACAO.md", "sha256": full["backtests"]["documents"][0]["sha256"]}]


def test_cli_painel_is_publishable_on_demo(demo, tmp_path, capsys):
    from cdp.__main__ import main

    base = ["--book", str(demo / "book"), "--market", str(demo / "market"),
            "--reports", str(demo / "reports")]
    out_dir = tmp_path / "artifacts" / "painel"
    assert main(base + ["painel", "--out-dir", str(out_dir)]) == 0
    res = json.loads(capsys.readouterr().out)
    art = res["artifact"]
    assert art["publicavel"] is True and art["motivo"] == "ok" and art["pagina_mudou"] is True
    css, js = (out_dir / n for n in asset_names(page_sha256()))
    index, data_file = out_dir / "index.html", out_dir / "data.json"
    assert art["arquivos_para_ler"] == [index.as_posix(), css.as_posix(), js.as_posix(),
                                        data_file.as_posix()]
    # a ferramenta exige a página (a casca) em toda publicação; com a página nova, vão também o
    # estilo e o script versionados
    assert art["publicar"] == {"file_path": index.as_posix(),
                               "files": {css.name: css.as_posix(), js.name: js.as_posix(),
                                         "data.json": data_file.as_posix()}}
    assert art["tamanho_dados"] == data_file.stat().st_size <= DATA_MAX_BYTES
    assert art["linhas_max"] <= PAGE_MAX_LINE and art["url"] is None
    (out_dir / "ARTIFACT_URL").write_text("https://claude.ai/artifact/exemplo\n", encoding="utf-8")
    assert main(base + ["painel", "--out-dir", str(out_dir), "--sem-local"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["index_written"] is False  # index.html local já atualizado...
    again = again["artifact"]
    assert again["pagina_mudou"] is True  # ... mas ainda não publicado: a página vai junto
    assert again["arquivos_para_ler"][0] == (out_dir / "index.html").as_posix()
    assert again["url"] == "https://claude.ai/artifact/exemplo" and again["pagina_publicada"] is None
    # depois de publicar com sucesso, a rotina registra a página publicada
    assert main(["painel", "--out-dir", str(out_dir), "--publicado"]) == 0
    marked = json.loads(capsys.readouterr().out)["pagina_publicada"]
    assert marked["mudou"] is True and marked["marcador"] == (out_dir / MARKER_NAME).as_posix()
    assert main(base + ["painel", "--out-dir", str(out_dir), "--sem-local"]) == 0
    third = json.loads(capsys.readouterr().out)["artifact"]
    assert third["pagina_mudou"] is False and third["publicavel"] is True
    # página já publicada: só a casca (pequena) e os dados são lidos e publicados
    assert third["arquivos_para_ler"] == [index.as_posix(), data_file.as_posix()]
    assert third["publicar"] == {"file_path": index.as_posix(),
                                 "files": {"data.json": data_file.as_posix()}}
    assert index.stat().st_size < 8_000
    assert third["pagina_publicada"] == marked["page_sha256"]
    assert third["linhas_max"] <= DATA_MAX_LINE
    assert main(["painel", "--out-dir", str(tmp_path / "nada"), "--publicado"]) == 2
