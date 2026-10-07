"""Monitor de risco (``cdp risk``) e agenda das rotinas locais (``cdp agenda``), offline.

Livro sintético da demonstração (DADOS SIMULADOS) em pasta temporária; cotações intradiárias por
um coletor falso (sem rede). Ausente nunca vira zero; ``kill-switch:`` só para gatilhos HARD.
"""

from __future__ import annotations

import json
import shutil
import warnings
from datetime import date, datetime
from pathlib import Path
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

LEGACY = Path(__file__).resolve().parent / "fixtures" / "fund_legado.yaml"
BRT = ZoneInfo("America/Sao_Paulo")
LAST = date(2024, 3, 5)      # último pregão da demonstração (2 pregões a partir de 04/03)
SESSION = date(2024, 3, 6)   # pregão "de hoje" no monitor intradiário


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("cdp_risk_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_demo(out, days=2, cfg=load_config(LEGACY))
    return out


def _rt(root, cfg=None, **kw) -> Runtime:
    return Runtime(cfg or load_config(LEGACY), root / "book", root / "market", root / "reports", **kw)


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
    cfg = load_config(LEGACY)  # mandato já iniciado (data de início explícita): livro sem registro
    cfg = cfg.model_copy(update={"fund": cfg.fund.model_copy(
        update={"inception_date": date(2024, 3, 4)})})
    rt = _rt(tmp_path, cfg=cfg)
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
    cfg = load_config(LEGACY)
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
    rt = Runtime(load_config(LEGACY), demo / "book", demo / "market", tmp_path / "reports")
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
    """``cdp painel`` ponta a ponta no livro sintético: só lê o livro e grava a pasta pedida."""
    import hashlib

    from cdp.__main__ import main

    base = ["--book", str(demo / "book"), "--market", str(demo / "market"),
            "--reports", str(demo / "reports")]
    before = sorted(p.relative_to(demo).as_posix() for p in demo.rglob("*") if p.is_file())
    out_dir = tmp_path / "artifacts" / "painel"
    assert main(base + ["painel", "--out-dir", str(out_dir)]) == 0
    res = json.loads(capsys.readouterr().out)
    data, index = out_dir / "data.json", out_dir / "index.html"
    local = out_dir / "cdp_painel_local.html"
    assert res["data_path"] == data.as_posix() and data.is_file() and index.is_file()
    assert local.is_file() and res["local_path"] == local.as_posix()
    assert res["data_sha256"] == hashlib.sha256(data.read_bytes()).hexdigest()
    assert res["is_synthetic"] is True and res["page_changed"] is True
    check = res["artifact"]
    assert check["tamanho_dados"] == data.stat().st_size and isinstance(check["publicavel"], bool)
    assert check["motivo"] == "ok" or not check["publicavel"]
    assert "DADOS SIMULADOS" in data.read_text(encoding="utf-8")
    assert "DADOS SIMULADOS" in local.read_text(encoding="utf-8")
    after = sorted(p.relative_to(demo).as_posix() for p in demo.rglob("*") if p.is_file())
    assert after == before  # nada gravado no livro, na trilha ou nos relatórios


# ----------------------------------------------------------------------------- revisão humana


def _low_squeeze_cfg():
    """Mandato com stop de squeeze minúsculo: todo short que perde desde a entrada aciona o stop."""
    cfg = load_config(LEGACY)
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
    """Regra anterior (``squeeze.stop_scope = "book"``, mandato legado): o stop escala para o
    livro inteiro e o texto diz isso."""
    from cdp.workflow.risk_monitor import SQUEEZE_STOP_ACTION_LIVRO as SQUEEZE_STOP_ACTION

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


def test_loss_velocity_triggers_are_wired_only_with_the_active_construction(demo, tmp_path):
    """Gatilhos de velocidade de perda (``cdp.risk.gatilhos``) só com a metodologia de construção
    ativa (kill switch só-redução); no mandato legado o monitor não muda."""
    legacy = run_risk_monitor(_rt(demo), as_of=SESSION, now=_at(SESSION, 13, 30))
    codes = {t["codigo"] for t in legacy["gatilhos"]}
    assert "janela_incompleta" not in codes and "perda_diaria_extrema" not in codes
    active_cfg = load_config(LEGACY).with_overrides({"risk": {"idio_share_goal": 0.9,
                                                        "idio_share_floor": 0.85}})
    active_rt = Runtime(active_cfg, demo / "book", tmp_path / "mercado_ausente", demo / "reports")
    active = run_risk_monitor(active_rt, as_of=SESSION,
                              now=_at(SESSION, 13, 30))
    by_code = {t["codigo"]: t for t in active["gatilhos"]}
    assert by_code["janela_incompleta"]["nivel"] == "INFO"  # dois registros na demonstração
    assert not _kill_actions(active)
    assert any("evento societário" in x for x in active["limitacoes"])  # sem base de mercado


# ----------------------------------------------------------------------------- stop por nome


def _per_name_cfg():
    return load_config(LEGACY).with_overrides({"squeeze": {"stop_scope": "name"}})


def _shorts(rt):
    rec = rt.track().last()
    return sorted((p for p in rec.positions if p.market_value_usd < 0),
                  key=lambda p: p.market_value_usd)


def test_per_name_squeeze_stop_is_soft_and_cut_by_code(demo):
    """Regra por nome (metodologia vigente): stop isolado é SOFT; no intradiário é aviso
    antecipado (o corte e o veto valem a partir de um fechamento em stop); nenhum kill switch."""
    from cdp.workflow.risk_monitor import SQUEEZE_STOP_ACTION_INTRADIARIO

    rt = _rt(demo, cfg=_per_name_cfg())
    short = _shorts(rt)[0]
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15),
                           fetch_quotes=_quotes(rt, mult=lambda p: 1.6 if p.ticker == short.ticker
                                                else 1.0))
    trig = next(t for t in res["gatilhos"]
                if t["codigo"] == f"stop_squeeze_posicao_{short.ticker}")
    assert trig["nivel"] == "SOFT" and trig["acao"] == SQUEEZE_STOP_ACTION_INTRADIARIO
    assert "fechamento" in trig["acao"] and "dois shorts distintos" in trig["acao"]
    assert res["squeeze"]["regra"] == "por nome"
    assert res["squeeze"]["escalada"]["escalada"] is False
    assert res["squeeze"]["vetos_compra"] == []      # nenhum stop em fechamento
    assert not _kill_actions(res)


def test_per_name_close_stop_promises_the_cut_and_lists_the_long_veto(demo):
    """Stop num fechamento (regra por nome): o gatilho promete o corte do código e o relatório
    lista o emissor com compra vedada até revisão humana (INFO, com o comando de revisão)."""
    from cdp.workflow.risk_monitor import SQUEEZE_STOP_ACTION, SQUEEZE_VETO_CODE

    cfg = _per_name_cfg().with_overrides({"squeeze": {"stop_short_position_loss": 1e-9}})
    rt = _rt(demo, cfg=cfg)
    res = run_risk_monitor(rt, as_of=SESSION, now=_at(SESSION, 13, 30))
    hit = [s for s in res["squeeze"]["stops_fechamento"] if s["stop_posicao"]]
    if not hit:
        pytest.skip("livro sintético sem short com perda desde a entrada")
    by_code = {t["codigo"]: t for t in res["gatilhos"]}
    trig = by_code[f"stop_squeeze_posicao_{hit[0]['ticker']}"]
    assert trig["nivel"] == "SOFT" and trig["acao"] == SQUEEZE_STOP_ACTION
    assert "uma vez por episódio" in trig["acao"]
    vetos = {v["emissor"] for v in res["squeeze"]["vetos_compra"]}
    assert {str(s["emissor"]) for s in hit} <= vetos
    veto = by_code[SQUEEZE_VETO_CODE]
    assert veto["nivel"] == "INFO" and "revisar-squeeze" in veto["acao"]


def test_two_distinct_stops_escalate_to_the_book_kill_switch(demo, tmp_path):
    """Dois shorts distintos em stop dentro de 5 pregões ⇒ HARD (kill switch do livro); depois
    do desligamento humano, a mesma dupla não religa — um terceiro short em stop, sim."""
    from cdp.workflow.risk_monitor import SQUEEZE_ESCALATION_ACTION, SQUEEZE_ESCALATION_CODE

    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    rt = _rt(root, cfg=_per_name_cfg())
    shorts = _shorts(rt)
    if len(shorts) < 3:
        pytest.skip("livro sintético com menos de três shorts")
    two = {shorts[0].ticker, shorts[1].ticker}
    res = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 15),
                           fetch_quotes=_quotes(rt, mult=lambda p: 1.6 if p.ticker in two
                                                else 1.0))
    esc = {t["codigo"]: t for t in res["gatilhos"]}[SQUEEZE_ESCALATION_CODE]
    assert esc["nivel"] == "HARD" and esc["acao"] == SQUEEZE_ESCALATION_ACTION
    assert set(res["squeeze"]["escalada"]["emissores_em_stop"]) == {
        shorts[0].issuer_id, shorts[1].issuer_id}
    assert len(_kill_actions(res)) == 1 and "ESCALADA DE SQUEEZE" in res["motivo_kill_switch"]
    write_risk_report(res, root / "reports" / "risk", rt.cfg)
    rt.set_kill_switch(True, res["motivo_kill_switch"], "CDP — rotina de risco (teste)")
    rt.set_kill_switch(False, "revisado: dois shorts em stop aceitos", "humano (teste)")
    again = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 16),
                             fetch_quotes=_quotes(rt, mult=lambda p: 1.6 if p.ticker in two
                                                  else 1.0))
    assert {t["codigo"]: t["nivel"] for t in again["gatilhos"]}[SQUEEZE_ESCALATION_CODE] == "SOFT"
    assert not _kill_actions(again)
    three = two | {shorts[2].ticker}
    worse = run_risk_monitor(rt, as_of=SESSION, live=True, now=_at(SESSION, 16, 5),
                             fetch_quotes=_quotes(rt, mult=lambda p: 1.6 if p.ticker in three
                                                  else 1.0))
    assert {t["codigo"]: t["nivel"] for t in worse["gatilhos"]}[SQUEEZE_ESCALATION_CODE] == "HARD"
    assert len(_kill_actions(worse)) == 1


def test_runtime_passes_name_stops_to_the_weekly_context(demo):
    """``Runtime.squeeze_stops`` (regra por nome): episódios de stop nos registros anteriores ao
    dia de montagem, com corte pendente e veto de compra; regra do livro inteiro ⇒ nenhum."""
    legacy = _rt(demo)
    assert legacy.squeeze_stops(date(2024, 3, 11)) == {}
    cfg = _per_name_cfg().with_overrides({"squeeze": {"stop_short_position_loss": 1e-9}})
    rt = _rt(demo, cfg=cfg)
    stops = rt.squeeze_stops(date(2024, 3, 11))
    held_short = {p.issuer_id for r in rt.track().records() for p in r.positions
                  if p.market_value_usd < 0}
    assert set(stops) <= held_short
    for spec in stops.values():
        assert spec["veto_compra"] and spec["fracao_maxima_short"] == pytest.approx(0.5)
    assert rt.squeeze_stops(date(2024, 3, 4)) == {}   # sem registro anterior ao dia


def test_cli_squeeze_review_is_human_only_and_lifts_the_long_veto(demo, tmp_path, capsys,
                                                                  monkeypatch):
    """``kill-switch revisar-squeeze``: recusado em rotina, CI ou agente; com operador humano,
    grava ``SQUEEZE_REVISADO`` na trilha e libera o veto de compra (o corte continua). Revisão
    gravada depois da preparação de uma semana não muda a reconstrução dessa semana."""
    import sys as _sys

    import yaml

    from cdp.__main__ import main

    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    raw = yaml.safe_load(LEGACY.read_text(encoding="utf-8"))
    raw.setdefault("squeeze", {}).update({"stop_scope": "name",
                                          "stop_short_position_loss": 1e-9})
    cfg_path = tmp_path / "fund_nome.yaml"
    cfg_path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    rt = Runtime(load_config(cfg_path), root / "book", root / "market", root / "reports")
    week = date(2024, 3, 11)
    stops = rt.squeeze_stops(week)
    if not stops:
        pytest.skip("livro sintético sem short com perda desde a entrada")
    iid = sorted(stops)[0]
    base = ["--config", str(cfg_path), "--book", str(root / "book"), "--market",
            str(root / "market"), "--reports", str(root / "reports")]
    cmd = base + ["kill-switch", "revisar-squeeze", "--emissor", iid, "--reason",
                  "revisado: squeeze técnico, sem fato novo", "--by", "Ana"]
    monkeypatch.setenv("CLAUDECODE", "1")
    assert main(cmd) == 2 and "agente" in capsys.readouterr().err
    _sem_contexto_de_agente(monkeypatch)

    class _Tty:
        def __init__(self, stream):
            self._s = stream

        def isatty(self):
            return True

        def __getattr__(self, name):
            return getattr(self._s, name)

    monkeypatch.setattr(_sys, "stdin", _Tty(_sys.stdin))
    monkeypatch.setattr(_sys, "stdout", _Tty(_sys.stdout))
    monkeypatch.setattr("builtins.input",
                        lambda _p="": "revisado: squeeze técnico, sem fato novo")
    _senha_do_operador(monkeypatch, tmp_path)
    assert main(cmd) == 0
    out = json.loads(capsys.readouterr().out)["revisao_squeeze"]
    assert out["emissor"] == iid and out["registro_base"] == LAST.isoformat()
    after = rt.squeeze_stops(week)
    assert iid not in after or not after[iid]["veto_compra"]
    assert after.get(iid, {}).get("fracao_maxima_short") == stops[iid]["fracao_maxima_short"] \
        or iid not in after
    assert main(cmd) == 2 and "aguardando revisão" in capsys.readouterr().err   # nada pendente
    # Revisão depois da preparação da semana: a reconstrução dessa semana não muda.
    rt.book.audit.append("WEEKLY_PREPARED", "teste", {"x": 1}, summary="teste", week=week)
    other = sorted(set(stops) - {iid})
    if other:
        rt.review_squeeze(other[0], "revisado depois do prepare", "Ana")
        assert rt.squeeze_stops(week)[other[0]]["veto_compra"]
        assert rt.squeeze_reviews()[other[0]] == LAST


def test_loss_velocity_hard_seen_by_a_human_is_not_re_armed_on_the_same_record(
        demo, tmp_path, monkeypatch):
    """Perda diária extrema (HARD) revisada por humano: a próxima rotina de risco sobre o mesmo
    registro-base não religa o kill switch; só um registro de fechamento posterior religa."""
    from cdp.risk import gatilhos
    from cdp.workflow import risk_monitor as rm

    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    cfg = load_config(LEGACY).with_overrides({"risk": {"idio_share_goal": 0.9,
                                                       "idio_share_floor": 0.85}})
    rt = _rt(root, cfg=cfg)

    def extreme(records_desc, _cfg):
        d = records_desc[0].date
        return [{"nivel": "HARD", "codigo": "perda_diaria_extrema",
                 "mensagem": f"Perda diária extrema em {d}: -1,20%",
                 "acao": gatilhos.KILL_SWITCH_PREFIX + f"perda diária extrema em {d}"}]

    monkeypatch.setattr(gatilhos, "loss_velocity", extreme)
    first = run_risk_monitor(rt, as_of=SESSION, now=_at(SESSION, 13, 30))
    assert {t["codigo"]: t["nivel"] for t in first["gatilhos"]}["perda_diaria_extrema"] == "HARD"
    assert _kill_actions(first)
    write_risk_report(first, root / "reports" / "risk", cfg)
    rt.set_kill_switch(True, first["motivo_kill_switch"], "CDP — rotina de risco (teste)")
    rt.set_kill_switch(False, "revisado: perda explicada por evento conhecido", "humano (teste)")
    again = run_risk_monitor(rt, as_of=SESSION, now=_at(SESSION, 16, 3))
    assert {t["codigo"]: t["nivel"] for t in again["gatilhos"]}["perda_diaria_extrema"] == "SOFT"
    assert not _kill_actions(again)
    assert "perda_diaria_extrema" in again["revisao_humana"]["codigos_rebaixados"]
    # Registro de fechamento posterior ao revisado: religa.
    hard = rm.Trigger("HARD", "perda_diaria_extrema", "perda", "kill-switch")
    review = {"desligado_em": "x", "por": "humano", "registro_base": LAST,
              "estagio_revisado": "normal", "codigos_rebaixados": [], "_entradas": {}}
    assert rm._apply_review([hard], review, {}, registro=LAST)[0].nivel == "SOFT"
    assert rm._apply_review([hard], review, {}, registro=SESSION)[0].nivel == "HARD"


def test_reviewed_squeeze_escalation_is_keyed_by_short_and_entry_price():
    """Escalada revisada para X e Y a preço médio 50: um novo episódio dos mesmos emissores com
    outro preço médio de entrada é risco novo e volta a ser HARD."""
    from cdp.workflow import risk_monitor as rm

    esc = rm.Trigger("HARD", rm.SQUEEZE_ESCALATION_CODE, "escalada", "kill-switch")
    review = {"desligado_em": "x", "por": "humano", "registro_base": LAST,
              "estagio_revisado": "normal", "codigos_rebaixados": [], "_entradas": {},
              "_shorts_em_stop": {"X": {50.0}, "Y": {50.0}}}
    same = rm._apply_review([esc], dict(review, codigos_rebaixados=[]), {},
                            {"X": [50.0], "Y": [50.0]})
    assert same[0].nivel == "SOFT"
    new = rm._apply_review([esc], dict(review, codigos_rebaixados=[]), {},
                           {"X": [65.0], "Y": [50.0]})
    assert new[0].nivel == "HARD"
    assert rm._apply_review([esc], dict(review, codigos_rebaixados=[]), {}, {})[0].nivel == "HARD"


def test_idio_three_way_block_with_the_active_construction(demo):
    """Fatia idiossincrática por três medidas no monitor (metodologia vigente): ex-ante do
    registro e medidas de 63 pregões ausentes com amostra curta (nunca zero)."""
    legacy = run_risk_monitor(_rt(demo), as_of=SESSION, now=_at(SESSION, 13, 30))
    assert "idio" not in legacy
    cfg = load_config(LEGACY).with_overrides({"risk": {"idio_share_goal": 0.9,
                                                       "idio_share_floor": 0.85}})
    res = run_risk_monitor(_rt(demo, cfg=cfg), as_of=SESSION, now=_at(SESSION, 13, 30))
    idio = res["idio"]
    assert idio["data"] == LAST.isoformat() and idio["piso"] == 0.85
    assert idio["ex_ante"] is not None and 0.0 < idio["ex_ante"] <= 1.0
    assert idio["realizada_63d"] is None and idio["sem_modelo_63d"] is None
    assert "Fatia idiossincrática (três medidas)" in render_risk_markdown(res, cfg)


# ----------------------------------------------------------------------------- pedidos de kill switch


def test_kill_switch_request_is_applied_by_the_next_exclusive_run(demo, tmp_path):
    """Kill switch ligado num clone sem a trava (livro retido): o pedido mesclável em
    ``reports/risk/<data>/`` liga o kill switch na próxima execução exclusiva, uma vez."""
    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    vm = _rt(root)
    pedido = vm.request_kill_switch("Monitor de risco (código): teste de pedido", "risco (teste)")
    path = Path(pedido["arquivo"])
    assert path.parent.parent == root / "reports" / "risk" and path.name.startswith("kill_switch_")
    pend = vm.kill_switch_requests()
    assert [r["sha256"] for r in pend] == [pedido["sha256"]] and not pend[0]["superado"]
    assert agenda(vm, _at(SESSION, 12))["kill_switch_pedidos"][0]["arquivo"] == pedido["arquivo"]
    assert not vm.kill_switch_active()
    done = vm.apply_kill_switch_requests()
    assert done == [{"arquivo": pedido["arquivo"], "efeito": "aplicado"}]
    assert vm.kill_switch_active() and vm.kill_switch_requests() == []
    assert vm.apply_kill_switch_requests() == []
    ok, _msgs = vm.book.verify_integrity()
    assert ok


def test_kill_switch_request_before_a_human_off_is_superseded(demo, tmp_path):
    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    rt = _rt(root)
    rt.request_kill_switch("Monitor de risco (código): pedido antigo", "risco (teste)")
    rt.set_kill_switch(True, "ligado pelo operador", "humano (teste)")
    rt.set_kill_switch(False, "revisado pelo operador", "humano (teste)")
    pend = rt.kill_switch_requests()
    assert len(pend) == 1 and pend[0]["superado"]
    assert rt.apply_kill_switch_requests()[0]["efeito"].startswith("superado")
    assert not rt.kill_switch_active() and rt.kill_switch_requests() == []


def test_cli_kill_switch_on_marks_its_request_and_off_refuses_without_a_human(
        demo, tmp_path, capsys, monkeypatch):
    from cdp.__main__ import main

    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    base = ["--config", str(LEGACY), "--book", str(root / "book"), "--market",
            str(root / "market"), "--reports", str(root / "reports")]
    assert main(base + ["kill-switch", "on", "--reason", "gatilho HARD do monitor (teste)",
                        "--by", "CDP — rotina de risco"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kill_switch"] == "on" and Path(out["pedido"]).is_file()
    rt = _rt(root)
    assert rt.kill_switch_active() and rt.kill_switch_requests() == []
    # Rotina, CI ou agente de IA: recusado, com o motivo.
    monkeypatch.setenv("CLAUDECODE", "1")
    assert main(base + ["kill-switch", "off", "--reason", "revisado pelo gestor",
                        "--by", "Ana"]) == 2
    assert "agente" in capsys.readouterr().err and rt.kill_switch_active()
    # Sem terminal interativo (pytest): recusado mesmo sem as variáveis.
    _sem_contexto_de_agente(monkeypatch)
    assert main(base + ["kill-switch", "off", "--reason", "revisado pelo gestor",
                        "--by", "Ana"]) == 2
    assert "terminal interativo" in capsys.readouterr().err and rt.kill_switch_active()


def test_cli_kill_switch_off_with_an_interactive_operator(demo, tmp_path, capsys, monkeypatch):
    """Operador humano num terminal: o motivo digitado de novo precisa conferir."""
    import sys as _sys

    from cdp.__main__ import main

    root = tmp_path / "copia"
    shutil.copytree(demo, root)
    rt = _rt(root)
    rt.set_kill_switch(True, "ligado para o teste", "teste")
    _sem_contexto_de_agente(monkeypatch)

    class _Tty:
        def __init__(self, stream):
            self._s = stream

        def isatty(self):
            return True

        def __getattr__(self, name):
            return getattr(self._s, name)

    monkeypatch.setattr(_sys, "stdin", _Tty(_sys.stdin))
    monkeypatch.setattr(_sys, "stdout", _Tty(_sys.stdout))
    base = ["--config", str(LEGACY), "--book", str(root / "book"), "--market",
            str(root / "market"), "--reports", str(root / "reports")]
    off = base + ["kill-switch", "off", "--reason", "revisado pelo gestor", "--by", "Ana"]
    monkeypatch.setattr("builtins.input", lambda _p="": "outro motivo")
    assert main(off) == 2
    assert rt.kill_switch_active()
    assert main(base + ["kill-switch", "off", "--reason", "revisado pelo gestor",
                        "--by", "CDP — rotina"]) == 2      # rotina nunca é o autor
    monkeypatch.setattr("builtins.input", lambda _p="": "revisado  pelo gestor")
    # Sem a senha do operador definida (fora do repositório): recusado.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg_vazio"))
    assert main(off) == 2 and "senha do operador" in capsys.readouterr().err
    assert rt.kill_switch_active()
    # Um agente com pseudoterminal chega ao pedido da senha, mas não a tem.
    _senha_do_operador(monkeypatch, tmp_path, digitada="chute de agente")
    assert main(off) == 2 and "não confere" in capsys.readouterr().err
    assert rt.kill_switch_active()
    _senha_do_operador(monkeypatch, tmp_path)
    assert main(off) == 0
    assert not rt.kill_switch_active()


SENHA_TESTE = "senha do operador de teste"


def _sem_contexto_de_agente(monkeypatch) -> None:
    """Remove as variáveis de rotina/CI/agente (inclusive as de prefixo, ex.: ``CODEX_*``)."""
    import os

    from cdp.__main__ import _contexto_nao_humano

    for var in _contexto_nao_humano(dict(os.environ)):
        monkeypatch.delenv(var, raising=False)


def _senha_do_operador(monkeypatch, tmp_path, digitada: str = SENHA_TESTE) -> None:
    """Senha do operador definida fora do repositório (pasta de teste) e digitada no terminal."""
    from cdp import operador

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg_operador"))
    if not operador.configurado():
        operador.definir(SENHA_TESTE)
    monkeypatch.setattr("getpass.getpass", lambda _p="": digitada)


def test_kill_switch_off_guard_sees_codex_and_harness_contexts(monkeypatch):
    """Codex com acesso total não exporta as variáveis de sandbox: ``CDP_HARNESS`` (ambiente
    de toda rotina) e os prefixos dos apps de IA bastam para recusar."""
    from cdp.__main__ import CONTEXTO_NAO_HUMANO, _contexto_nao_humano

    env = {"PATH": "/usr/bin", "CODEX_HOME": "/Users/x/.codex"}
    assert _contexto_nao_humano(env) == []
    assert _contexto_nao_humano({**env, "CDP_HARNESS": "codex"}) == ["CDP_HARNESS"]
    assert _contexto_nao_humano({**env, "CODEX_QUALQUER": "1"}) == ["CODEX_QUALQUER"]
    assert _contexto_nao_humano({**env, "ANTIGRAVITY_SESSAO": "x"}) == ["ANTIGRAVITY_SESSAO"]
    assert "CDP_HARNESS" in CONTEXTO_NAO_HUMANO


def test_operator_passphrase_is_stored_only_as_a_salted_hash(tmp_path, monkeypatch):
    from cdp import operador

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert not operador.configurado() and not operador.conferir("qualquer coisa")
    with pytest.raises(ValueError):
        operador.definir("curta")
    path = operador.definir(SENHA_TESTE)
    assert path == tmp_path / "cdp" / "operador.json"
    assert SENHA_TESTE not in path.read_text(encoding="utf-8")
    assert operador.conferir(SENHA_TESTE) and not operador.conferir(SENHA_TESTE + "x")


def test_agenda_reports_the_market_store_last_session(demo, tmp_path):
    from cdp.data.synthetic import make_synthetic_market

    md = make_synthetic_market(seed=DEMO_SEED, start=DEMO_HISTORY_START, as_of=LAST)
    rt = _rt(demo, store_override=DemoStore(md))
    assert agenda(rt, _at(SESSION, 12))["base_ultimo_pregao"] == LAST
    assert agenda(_rt(demo), _at(SESSION, 12))["base_ultimo_pregao"] == LAST  # arquivo físico
    missing = Runtime(load_config(LEGACY), demo / "book", tmp_path / "mercado_ausente",
                      demo / "reports")
    assert agenda(missing, _at(SESSION, 12))["base_ultimo_pregao"] is None
