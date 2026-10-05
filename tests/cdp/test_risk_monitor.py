"""Monitor de risco (``cdp risk``) e agenda das rotinas locais (``cdp agenda``), offline.

Livro sintético da demonstração (DADOS SIMULADOS) em pasta temporária; cotações intradiárias por
um coletor falso (sem rede). Ausente nunca vira zero; ``kill-switch:`` só para gatilhos HARD.
"""

from __future__ import annotations

import json
import shutil
import warnings
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from cdp.config import load_config
from cdp.workflow.agenda import agenda, pending_closes, validate_daily_commentary
from cdp.workflow.demo import DEMO_HISTORY_START, DEMO_SEED, DemoStore, run_demo
from cdp.workflow.risk_monitor import (
    KILL_SWITCH_PREFIX,
    drawdown_stage,
    render_risk_markdown,
    run_risk_monitor,
    write_risk_report,
)
from cdp.workflow.runtime import Runtime

BRT = ZoneInfo("America/Sao_Paulo")
LAST = date(2024, 3, 5)      # último pregão da demonstração (2 pregões a partir de 04/03)
SESSION = date(2024, 3, 6)   # pregão "de hoje" no monitor intradiário


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("cdp_risk_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_demo(out, days=2)
    return out


def _rt(root, cfg=None, **kw) -> Runtime:
    return Runtime(cfg or load_config(), root / "book", root / "market", root / "reports", **kw)


def _at(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=BRT)


def _quotes(rt: Runtime, *, mult=None, fx_mult=None, drop=(), stale=(), when=None):
    """Coletor falso: preço = fechamento × mult(posição); câmbio = câmbio do fechamento × fx_mult."""
    rec = rt.track().last()
    when = when or _at(SESSION, 14).isoformat()
    yesterday = _at(LAST, 16).isoformat()
    by_ticker = {p.ticker: p for p in rec.positions}

    def fetch(tickers, ccys, bench):
        rows = []
        for t in tickers:
            p = by_ticker[t]
            m = mult(p) if mult else 1.0
            price = np.nan if t in drop else p.price_local * m
            rows.append({"symbol": t, "kind": "line", "price": price,
                         "time": yesterday if t in stale else when})
        for c in ccys:
            p = next(x for x in rec.positions if x.currency == c)
            f = (fx_mult or {}).get(c, 1.0)
            rows.append({"symbol": c, "kind": "fx", "price": p.price_usd / p.price_local * f,
                         "time": when})
        return pd.DataFrame(rows)

    return fetch


def _kill_actions(res):
    return [a for a in res["acoes_recomendadas"] if a.startswith(KILL_SWITCH_PREFIX)]


# ----------------------------------------------------------------------------- monitor


def test_close_mode_reports_mandate_state(demo):
    rt = _rt(demo)
    res = run_risk_monitor(rt, as_of=SESSION, now=_at(SESSION, 13, 30))
    assert res["status"] == "ok" and res["base"]["registro"] == LAST
    assert res["base"]["semana_vigente"] == date(2024, 3, 4)
    assert "DADOS SIMULADOS" in res["aviso"]
    assert res["drawdown"]["estagio"] == drawdown_stage(res["drawdown"]["fechamento"], rt.cfg)
    assert res["risco"]["banda_vol"] == [rt.cfg.risk.vol_band_min, rt.cfg.risk.vol_band_max]
    assert all(t["nivel"] in {"HARD", "SOFT", "INFO"} for t in res["gatilhos"])
    hard = [t for t in res["gatilhos"] if t["nivel"] == "HARD"]
    assert bool(_kill_actions(res)) == bool(hard)
    assert "intradiario" not in res
    rec = rt.track().last()
    shorts = {p.ticker for p in rec.positions if p.market_value_usd < 0}
    assert {s["ticker"] for s in res["squeeze"]["stops_fechamento"]} == shorts


def test_live_mtm_uses_live_prices_and_fx(demo):
    rt = _rt(demo)
    rec = rt.track().last()
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 14, 5),
                           fetch_quotes=_quotes(rt, mult=lambda p: 1.01, fx_mult={"BRL": 1.02}))
    lv = res["intradiario"]
    assert lv["cobertura_gross"] == pytest.approx(1.0) and not lv["parcial"]
    expected = 0.0
    for p in rec.positions:
        if p.market_value_usd == 0:
            continue
        fx = 1.02 if p.currency == "BRL" else 1.0
        expected += p.market_value_usd * (1.01 * fx - 1.0)
    assert lv["pnl_usd"] == pytest.approx(expected, rel=1e-9)
    assert lv["nav_estimado_usd"] == pytest.approx(rec.nav_end_usd + expected)
    brl = [r for r in lv["posicoes"] if r["moeda"] == "BRL"]
    assert brl and all(r["ret_usd"] == pytest.approx(1.01 * 1.02 - 1) for r in brl)
    assert all(r["ret_local"] == pytest.approx(0.01) for r in lv["posicoes"])


def test_missing_and_stale_quotes_stay_missing(demo):
    rt = _rt(demo)
    rec = rt.track().last()
    held = [p for p in rec.positions if p.market_value_usd != 0]
    gone, old = held[0].ticker, held[1].ticker
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 14, 5),
                           fetch_quotes=_quotes(rt, mult=lambda p: 1.05, drop={gone},
                                                stale={old}))
    lv = res["intradiario"]
    motivos = {m["ticker"]: m["motivo"] for m in lv["sem_cotacao"]}
    assert motivos[gone] == "cotação indisponível"
    assert motivos[old] == "sem negócio hoje"
    assert lv["parcial"] and lv["cobertura_gross"] < 1.0
    assert {r["ticker"] for r in lv["posicoes"]}.isdisjoint({gone, old})
    covered = sum(p.market_value_usd for p in held if p.ticker not in {gone, old})
    assert lv["pnl_usd"] == pytest.approx(covered * 0.05, rel=1e-9)  # ausentes fora (não zero)
    assert any("nunca viram retorno zero" in x for x in res["limitacoes"])


def test_hard_intraday_drawdown_recommends_kill_switch(demo, tmp_path):
    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    rt = _rt(root)
    crash = _quotes(rt, mult=lambda p: 0.82 if p.market_value_usd > 0 else 1.18)
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15), fetch_quotes=crash)
    lv = res["intradiario"]
    assert lv["estagio_estimado"] in {"hard_stop", "stop_out"}
    codes = {t["codigo"]: t["nivel"] for t in res["gatilhos"]}
    assert codes.get(f"drawdown_{lv['estagio_estimado']}_intradiario") == "HARD"
    kill = _kill_actions(res)
    assert len(kill) == 1 and res["motivo_kill_switch"]
    assert kill[0] == KILL_SWITCH_PREFIX + res["motivo_kill_switch"]
    assert not any(ch in res["motivo_kill_switch"] for ch in "\"'`$\\")
    # Com o kill switch já ligado: nada de ligar de novo, só "manter".
    rt.set_kill_switch(True, res["motivo_kill_switch"], "teste")
    again = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15, 5),
                             fetch_quotes=crash)
    assert again["kill_switch"]["ativo"] is True
    assert not _kill_actions(again) and again["motivo_kill_switch"] is None
    assert again["acoes_recomendadas"][0].startswith("manter kill switch")


def test_partial_coverage_downgrades_drawdown_to_soft(demo):
    rt = _rt(demo)
    rec = rt.track().last()
    shorts = {p.ticker for p in rec.positions if p.market_value_usd < 0}
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15),
                           fetch_quotes=_quotes(rt, mult=lambda p: 0.55, drop=shorts))
    lv = res["intradiario"]
    assert lv["cobertura_gross"] < 0.95
    assert lv["estagio_estimado"] in {"hard_stop", "stop_out"}
    dd = [t for t in res["gatilhos"] if t["codigo"].endswith("_intradiario")]
    assert dd and all(t["nivel"] == "SOFT" for t in dd)
    assert "cobertura insuficiente" in dd[0]["motivo"]
    assert not _kill_actions(res)


def test_squeeze_stop_is_hard(demo):
    rt = _rt(demo)
    rec = rt.track().last()
    short = min((p for p in rec.positions if p.market_value_usd < 0),
                key=lambda p: p.market_value_usd)
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15),
                           fetch_quotes=_quotes(rt, mult=lambda p: 1.6 if p.ticker == short.ticker
                                                else 1.0))
    hits = [s for s in res["squeeze"]["stops_intradiario"] if s["ticker"] == short.ticker]
    assert hits and hits[0]["stop_posicao"]
    codes = {t["codigo"]: t["nivel"] for t in res["gatilhos"]}
    assert codes[f"stop_squeeze_posicao_{short.ticker}"] == "HARD"
    assert _kill_actions(res) and short.ticker in res["motivo_kill_switch"]


def test_fetch_failure_is_reported_not_fatal(demo):
    rt = _rt(demo)

    def broken(*_a, **_k):
        raise OSError("sem rede")

    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15),
                           fetch_quotes=broken)
    assert res["status"] == "ok" and "intradiario" not in res
    assert any("indisponíveis" in x for x in res["limitacoes"])


def test_stale_record_is_flagged(demo):
    rt = _rt(demo)
    res = run_risk_monitor(rt, as_of=date(2024, 3, 8), now=_at(date(2024, 3, 8), 13))
    codes = {t["codigo"]: t["nivel"] for t in res["gatilhos"]}
    assert codes.get("registro_defasado") == "SOFT"


def test_no_record_yet(tmp_path):
    rt = _rt(tmp_path)
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15),
                           fetch_quotes=lambda *a: pytest.fail("sem carteira: não busca cotações"))
    assert res["status"] == "sem registro"
    assert res["acoes_recomendadas"] == [] and res["motivo_kill_switch"] is None
    assert "Sem registro diário" in render_risk_markdown(res, rt.cfg)


def test_report_files_are_unique_and_flag_simulated_data(demo, tmp_path):
    rt = _rt(demo)
    res = run_risk_monitor(rt, as_of=SESSION, now=_at(SESSION, 13, 30))
    a = write_risk_report(res, tmp_path, rt.cfg)
    b = write_risk_report(res, tmp_path, rt.cfg)
    assert a["md"].endswith("risco_1330.md") and b["md"].endswith("risco_1330_2.md")
    md = (tmp_path / "2024-03-06" / "risco_1330.md").read_text(encoding="utf-8")
    assert "DADOS SIMULADOS" in md and "## Ações recomendadas" in md
    saved = json.loads((tmp_path / "2024-03-06" / "risco_1330.json").read_text(encoding="utf-8"))
    assert saved["base"]["registro"] == "2024-03-05"


def test_drawdown_stage_ladder():
    cfg = load_config()
    d = cfg.drawdown
    assert drawdown_stage(None, cfg) is None
    assert drawdown_stage(0.0, cfg) == "normal"
    assert drawdown_stage(d.soft_stop, cfg) == "soft_stop"
    assert drawdown_stage(d.hard_stop, cfg) == "hard_stop"
    assert drawdown_stage(d.stop_out - 0.01, cfg) == "stop_out"


# ----------------------------------------------------------------------------- agenda


def test_agenda_weekly_actions(demo):
    rt = _rt(demo)
    monday = date(2024, 3, 11)
    assert agenda(rt, _at(monday, 10))["semanal"]["acao"] == "aguardar"
    mid = agenda(rt, _at(monday, 11, 30))["semanal"]
    assert mid["acao"] == "montar" and mid["etapa"] == "prepare"
    assert mid["minutos_ate_o_prazo"] == 300
    late = agenda(rt, _at(monday, 17))["semanal"]
    assert late["acao"] == "prazo_vencido" and late["decisao_perdida"]
    done = agenda(rt, _at(date(2024, 3, 4), 12))["semanal"]
    assert done["acao"] == "nenhuma" and done["decisao_gravada"]
    tue = agenda(rt, _at(date(2024, 3, 12), 12))["semanal"]
    assert tue["acao"] == "nenhuma" and tue.get("decisao_perdida") is True
    carnival = agenda(rt, _at(date(2024, 2, 12), 12))["semanal"]  # B3 fechada seg/ter
    assert carnival["semana"] == date(2024, 2, 14) and carnival["acao"] == "nenhuma"


def test_agenda_pending_closes_respect_close_time(demo):
    rt = _rt(demo)
    assert pending_closes(rt, _at(SESSION, 18)) == []
    assert pending_closes(rt, _at(SESSION, 19, 30)) == [SESSION]
    friday = agenda(rt, _at(date(2024, 3, 8), 20))
    assert friday["fechamentos_pendentes"] == [date(2024, 3, 6), date(2024, 3, 7),
                                               date(2024, 3, 8)]
    assert friday["ultimo_registro_diario"] == LAST
    assert friday["publicacoes_pendentes"] == []
    assert [e["evento"] for e in friday["proximos_eventos"]] == [
        "decisão semanal (autônoma)", "fechamento diário"]


def test_agenda_pending_publications_and_empty_book(demo, tmp_path):
    rt = Runtime(load_config(), demo / "book", demo / "market", tmp_path / "reports")
    pubs = agenda(rt, _at(SESSION, 12))["publicacoes_pendentes"]
    assert [p["data"] for p in pubs] == [date(2024, 3, 4), LAST]
    assert not any(p["comentario_escrito"] for p in pubs)
    empty = agenda(_rt(tmp_path / "vazio"), _at(SESSION, 20))
    assert empty["fechamentos_pendentes"] == [] and empty["ultimo_registro_diario"] is None


def test_validate_daily_commentary_without_publishing(demo):
    from cdp.data.synthetic import make_synthetic_market

    md = make_synthetic_market(seed=DEMO_SEED, start=DEMO_HISTORY_START, as_of=LAST)
    rt = _rt(demo, store_override=DemoStore(md))
    ok, issues = validate_daily_commentary(rt, LAST)
    assert ok and issues == []
    missing, why = validate_daily_commentary(rt, date(2024, 3, 7))
    assert not missing and "sem registro diário" in why[0]


# ----------------------------------------------------------------------------- CLI


def test_cli_risk_and_agenda(demo, tmp_path, capsys):
    from cdp.__main__ import main

    base = ["--book", str(demo / "book"), "--market", str(demo / "market"),
            "--reports", str(demo / "reports")]
    assert main(base + ["risk", "--date", "2024-03-06", "--out", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok" and out["relatorio"]["md"].startswith(str(tmp_path))
    assert "exposicoes" not in out and "stops_acionados" in out["squeeze"]
    assert main(base + ["agenda", "--agora", "2024-03-08T20:00"]) == 0
    ag = json.loads(capsys.readouterr().out)
    assert ag["fechamentos_pendentes"] == ["2024-03-06", "2024-03-07", "2024-03-08"]


def test_cli_painel_on_demo_book(demo, tmp_path, capsys):
    """``cdp painel`` ponta a ponta no livro sintético: só lê o livro e grava o HTML pedido."""
    import hashlib

    from cdp.__main__ import main

    base = ["--book", str(demo / "book"), "--market", str(demo / "market"),
            "--reports", str(demo / "reports")]
    before = sorted(p.relative_to(demo).as_posix() for p in demo.rglob("*") if p.is_file())
    out = tmp_path / "artifacts" / "painel" / "cdp_painel.html"
    local = tmp_path / "local.html"
    assert main(base + ["painel", "--out", str(out), "--standalone", str(local)]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["path"] == out.as_posix() and out.is_file() and local.is_file()
    assert res["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert res["is_synthetic"] is True
    check = res["artifact"]
    assert check["bytes"] == out.stat().st_size and isinstance(check["publicavel"], bool)
    assert check["motivo"] == "ok" or not check["publicavel"]
    assert "DADOS SIMULADOS" in out.read_text(encoding="utf-8")
    after = sorted(p.relative_to(demo).as_posix() for p in demo.rglob("*") if p.is_file())
    assert after == before  # nada gravado no livro, na trilha ou nos relatórios


# ----------------------------------------------------------------------------- revisão humana


def _low_squeeze_cfg():
    """Mandato com stop de squeeze minúsculo: todo short que perde desde a entrada aciona o stop."""
    cfg = load_config()
    return cfg.model_copy(update={"squeeze": cfg.squeeze.model_copy(
        update={"stop_short_position_loss": 1e-9})})


def test_human_off_is_not_overridden_by_a_persisting_condition(demo, tmp_path):
    """Kill switch desligado por humano: a mesma condição de fechamento não o religa."""
    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    cfg = _low_squeeze_cfg()
    rt = _rt(root, cfg)
    first = run_risk_monitor(rt, as_of=SESSION, now=_at(SESSION, 13, 30))
    hard = [t["codigo"] for t in first["gatilhos"] if t["nivel"] == "HARD"]
    squeeze = [c for c in hard if c.startswith("stop_squeeze_")]
    if not squeeze:
        pytest.skip("livro sintético sem short com perda desde a entrada")
    assert _kill_actions(first) and "revisao_humana" not in first
    write_risk_report(first, root / "reports" / "risk", cfg)
    rt.set_kill_switch(True, first["motivo_kill_switch"], "CDP — rotina de risco (teste)")
    rt.set_kill_switch(False, "revisado: stop aceito até o rebalanceamento", "humano (teste)")

    again = run_risk_monitor(rt, as_of=SESSION, now=_at(SESSION, 16))
    assert again["kill_switch"]["ativo"] is False
    assert not _kill_actions(again) and again["motivo_kill_switch"] is None
    levels = {t["codigo"]: t["nivel"] for t in again["gatilhos"]}
    assert all(levels[c] == "SOFT" for c in squeeze)
    rev = again["revisao_humana"]
    assert rev["registro_base"] == LAST and rev["por"] == "humano (teste)"
    assert set(squeeze) <= set(rev["codigos_rebaixados"]) <= set(rev["codigos_revisados"])
    assert any(a.startswith("revisar: ") and "já revisado por humano" in a
               for a in again["acoes_recomendadas"])
    assert "Revisão humana" in render_risk_markdown(again, cfg)

    # Piora depois da revisão (escada de drawdown intradiária em hard stop): religa.
    crash = _quotes(rt, mult=lambda p: 0.82 if p.market_value_usd > 0 else 1.18)
    worse = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 16, 5),
                             fetch_quotes=crash)
    stage = worse["intradiario"]["estagio_estimado"]
    assert stage in {"hard_stop", "stop_out"}
    levels = {t["codigo"]: t["nivel"] for t in worse["gatilhos"]}
    assert levels[f"drawdown_{stage}_intradiario"] == "HARD"
    assert all(levels[c] == "SOFT" for c in squeeze)
    assert len(_kill_actions(worse)) == 1


def test_intraday_hard_seen_before_the_off_stays_reviewed(demo, tmp_path):
    """Relatório das 13:30 com HARD intradiário, humano desliga às 14:00: 16:00 não religa."""
    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    rt = _rt(root)
    crash = _quotes(rt, mult=lambda p: 0.82 if p.market_value_usd > 0 else 1.18)
    first = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 13, 30),
                             fetch_quotes=crash)
    assert _kill_actions(first)
    write_risk_report(first, root / "reports" / "risk", rt.cfg)
    rt.set_kill_switch(True, first["motivo_kill_switch"], "CDP — rotina de risco (teste)")
    rt.set_kill_switch(False, "revisado", "humano (teste)")
    later = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 16),
                             fetch_quotes=crash)
    assert not _kill_actions(later)
    assert later["revisao_humana"]["estagio_revisado"] in {"hard_stop", "stop_out"}


def test_squeeze_stop_text_says_what_the_code_does(demo):
    from cdp.workflow.risk_monitor import SQUEEZE_STOP_ACTION

    rt = _rt(demo)
    rec = rt.track().last()
    short = min((p for p in rec.positions if p.market_value_usd < 0),
                key=lambda p: p.market_value_usd)
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15),
                           fetch_quotes=_quotes(rt, mult=lambda p: 1.6 if p.ticker == short.ticker
                                                else 1.0))
    trig = next(t for t in res["gatilhos"] if t["codigo"] == f"stop_squeeze_posicao_{short.ticker}")
    assert trig["acao"] == SQUEEZE_STOP_ACTION
    assert "gross × 0,5" in trig["acao"] and "não é automático" in trig["acao"]
    assert "livro inteiro" in trig["motivo"]
