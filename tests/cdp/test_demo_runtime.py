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


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("cdp_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summary = run_demo(out, days=2, cfg=load_config(LEGACY))
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
    rt = Runtime(load_config(LEGACY), out / "book", out / "market", out / "reports")
    week = date(2024, 3, 4)
    assert rt.book.list_decisions(week)
    d = rt.book.load_decision(week)
    assert d is not None and d.mode == DecisionMode.AUTONOMOUS and d.mind == "demo"
    ok, msgs = rt.book.verify_integrity()
    assert ok, msgs


def test_demo_reports_carry_simulated_notice(demo):
    out, _ = demo
    weekly = (out / "reports" / "weekly" / "2024-03-04" / "relatorio.md").read_text(encoding="utf-8")
    daily = (out / "reports" / "daily" / "2024-03-05" / "relatorio.md").read_text(encoding="utf-8")
    assert "DADOS SIMULADOS" in weekly
    assert "DADOS SIMULADOS" in daily


def test_demo_refuses_existing_book(demo):
    out, _ = demo
    with pytest.raises(FileExistsError):
        run_demo(out, days=1)


def test_demo_sessions_follow_the_nyse_rule_when_active():
    from test_calendar import ativado

    s = demo_sessions(3, date(2024, 3, 4), ativado())
    assert s == [date(2024, 3, 8), date(2024, 3, 11), date(2024, 3, 12)]
    assert demo_sessions(2, date(2024, 3, 25), ativado())[0] == date(2024, 3, 28)  # Sexta Santa
