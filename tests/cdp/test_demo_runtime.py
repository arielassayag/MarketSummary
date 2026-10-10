"""Demonstração offline ponta a ponta pelo mesmo ``Runtime`` das rotinas (DADOS SIMULADOS)."""

from __future__ import annotations

import json
import warnings
from datetime import date
from pathlib import Path

import pytest

from cdp.config import load_config
from cdp.contracts import DecisionMode
from cdp.workflow.demo import demo_sessions, run_demo
from cdp.workflow.runtime import Runtime

LEGACY = Path(__file__).resolve().parent / "fixtures" / "fund_legado.yaml"
CONFIG = Path(__file__).resolve().parents[2] / "configs/cdp/fund.yaml"
FIRST = date(2026, 11, 13)
SECOND = date(2026, 11, 16)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("cdp_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summary = run_demo(out, days=2, first_week=FIRST, cfg=load_config(CONFIG))
    return out, summary


def test_demo_sessions_follow_b3_calendar():
    s = demo_sessions(3, date(2024, 2, 12))  # carnaval: 12 e 13/02 sem pregão na B3
    assert s[0] == date(2024, 2, 14)
    assert all(d.weekday() < 5 for d in s)


def test_demo_runs_weekly_and_daily_cycle(demo):
    out, summary = demo
    assert summary["integridade"] is True
    assert summary["registros"] == 2
    weekly = [e for e in summary["etapas"] if "semana" in e]
    assert weekly and weekly[0]["entradas_validas"] and weekly[0]["caminho"] == "cdp"
    assert weekly[0]["n_long"] > 0 and weekly[0]["n_short"] > 0
    daily = [e for e in summary["etapas"] if e.get("status") == "registrado"]
    assert len(daily) == 2 and all(e["comentario_da_mente"] for e in daily)
    assert "DADOS SIMULADOS" in summary["aviso"]
    saved = json.loads((out / "demo_summary.json").read_text(encoding="utf-8"))
    assert saved["registros"] == 2


def test_demo_decision_is_autonomous_and_verifiable(demo):
    out, _ = demo
    rt = Runtime(load_config(CONFIG), out / "book", out / "market", out / "reports")
    week = FIRST
    assert rt.book.list_decisions(week)
    d = rt.book.load_decision(week)
    assert d is not None and d.mode == DecisionMode.AUTONOMOUS and d.mind == "demo"
    ok, msgs = rt.book.verify_integrity()
    assert ok, msgs


def test_demo_reports_carry_simulated_notice(demo):
    out, _ = demo
    weekly = (out / "reports" / "weekly" / str(FIRST) / "relatorio.md").read_text(encoding="utf-8")
    daily = (out / "reports" / "daily" / str(SECOND) / "relatorio.md").read_text(encoding="utf-8")
    assert "DADOS SIMULADOS" in weekly
    assert "DADOS SIMULADOS" in daily


def test_demo_refuses_existing_book(demo):
    out, _ = demo
    with pytest.raises(FileExistsError):
        run_demo(out, days=1)


def test_demo_refuses_configuration_without_execution_before_writing(tmp_path):
    from cdp.workflow.net_moc import NetUnverifiable

    with pytest.raises(NetUnverifiable, match="execution explícita"):
        run_demo(tmp_path, days=1, cfg=load_config(LEGACY))
    assert list(tmp_path.iterdir()) == []


def test_demo_refuses_week_before_own_genesis_before_writing(tmp_path):
    from cdp.workflow.net_moc import NetUnverifiable

    with pytest.raises(NetUnverifiable, match="antecede a gênese"):
        run_demo(tmp_path, days=1, first_week=date(2024, 3, 4), cfg=load_config(CONFIG))
    assert list(tmp_path.iterdir()) == []


def test_cli_demo_receives_explicit_legacy_config_and_refuses_without_io(tmp_path, capsys):
    from cdp.__main__ import main

    cfg_path = tmp_path / "fund_legado_proprio.yaml"
    cfg_path.write_bytes(LEGACY.read_bytes())
    out = tmp_path / "demo_recusada"
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert main(["--config", str(cfg_path), "demo", "--out", str(out), "--days", "1"]) == 2
    captured = capsys.readouterr()
    assert "NET UNVERIFIABLE" in captured.err and "execution explícita" in captured.err
    assert "DADOS SIMULADOS" in captured.out and "Traceback" not in captured.err
    assert not out.exists()
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*")
                      if p.is_file()}


def test_cli_demo_forwards_complete_config_from_own_file(tmp_path, monkeypatch, capsys):
    from cdp.__main__ import main
    from cdp.config import config_json
    from cdp.workflow import demo as native

    cfg_path = tmp_path / "fund_integral_proprio.yaml"
    cfg_path.write_bytes(CONFIG.read_bytes())
    received = []

    def receive(out, *, days, cfg):
        received.append((out, days, cfg))
        return {"aviso": "DADOS SIMULADOS", "encaminhamento_unitario": True}

    monkeypatch.setattr(native, "run_demo", receive)
    out = tmp_path / "demo"
    assert main(["--config", str(cfg_path), "demo", "--out", str(out), "--days", "1"]) == 0
    assert len(received) == 1
    assert received[0][:2] == (out, 1)
    assert received[0][2].execution is not None
    assert config_json(received[0][2]) == config_json(load_config(cfg_path))
    assert cfg_path.read_bytes() == CONFIG.read_bytes()
    assert not out.exists()
    assert "DADOS SIMULADOS" in capsys.readouterr().out


def test_demo_sessions_follow_the_nyse_rule_when_active():
    from test_calendar import ativado

    s = demo_sessions(3, date(2024, 3, 4), ativado())
    assert s == [date(2024, 3, 8), date(2024, 3, 11), date(2024, 3, 12)]
    assert demo_sessions(2, date(2024, 3, 25), ativado())[0] == date(2024, 3, 28)  # Sexta Santa
