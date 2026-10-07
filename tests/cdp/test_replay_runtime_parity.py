"""Composição independente do Runtime versus driver; DADOS SIMULADOS.

O caminho manual não usa helpers de composição, resumo, relógio ou configuração
do replay. Ele não fornece um oráculo financeiro independente do Runtime: testa
que o driver compõe as APIs públicas sem mudar a economia das operações.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from cdp.backtest.proveniencia import prefix_market
from cdp.backtest.replay import ReplayStore, run_replay
from cdp.config import FundConfig, load_config
from cdp.contracts import FactBook
from cdp.data.snapshot import load_snapshot, write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file, sha256_obj
from cdp.research.comentario_semanal import COMENTARIO_JSON, modelo_valido
from cdp.research.commentary import COMMENTARY_JSON, example_commentary
from cdp.workflow.book import dump_json
from cdp.workflow.origem import ReplayOrigin, install_replay_origin, read_replay_origin
from cdp.workflow.relatorio_semanal import calcular_semana, factbook_semana, preparar, publicar
from cdp.workflow.risco_diario import load as load_daily_risk
from cdp.workflow.risk_monitor import KILL_SWITCH_PREFIX, run_risk_monitor
from cdp.workflow.runtime import Runtime
from cdp.workflow.tese import TESE_JSON, load_prepared, template_thesis, thesis_dir

BRT = ZoneInfo("America/Sao_Paulo")
SESSIONS = (date(2024, 3, 8), date(2024, 3, 11), date(2024, 3, 12))
PREVIOUS = date(2024, 3, 7)
MIND = "outro"


def _files(root):
    return {str(p.relative_to(root)): sha256_file(p) for p in root.rglob("*") if p.is_file()}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(dump_json(value))


def _monitor_public(rt, day):
    result = run_risk_monitor(rt, as_of=day, live=False, now=rt.now())
    for action in result.get("acoes_recomendadas", []):
        if action.startswith(KILL_SWITCH_PREFIX):
            reason = action[len(KILL_SWITCH_PREFIX):]
            if not any(p["pedido"]["reason"] == reason for p in rt.kill_switch_requests()):
                rt.request_kill_switch(reason, by="sistema")


def _manual(source, out, cfg):
    # Datas conhecidas deste caso; nenhuma seleção de montagem pelo driver.
    raw_cfg = cfg.model_dump(mode="json")
    raw_cfg["fund"]["inception_date"] = SESSIONS[0].isoformat()
    effective = FundConfig.model_validate(raw_cfg)
    md = load_snapshot(source, verify=True)
    for day in (PREVIOUS, *SESSIONS):
        cutoff = datetime.combine(day, time(19, 22), tzinfo=BRT)
        view = prefix_market(md, day, cutoff, "simulado")
        write_snapshot(view, out / "market" / "base" / day.isoformat())
    manifest = out / "manual_manifest.json"
    _write(manifest, {"tipo": "DADOS SIMULADOS; composição retrospectiva independente",
                      "sessions": [d.isoformat() for d in SESSIONS],
                      "contrafactual": "somente fund.inception_date",
                      "cfg": effective.model_dump(mode="json")})
    now = [datetime.combine(SESSIONS[0], time(11, 7), tzinfo=BRT)]
    def clock():
        return now[0]
    store = ReplayStore(out / "market", cfg=effective, now=clock,
                        close_cutoff=time(19, 22), close_tz="America/Sao_Paulo")
    rt = Runtime(effective, out / "book", out / "market", out / "reports", clock=clock,
                 store_override=store, teses_root=None, expected_mind=MIND)
    install_replay_origin(rt.book, ReplayOrigin(
        mode="simulado", actual_started_at=datetime.now(UTC),
        run_manifest_sha256=sha256_file(manifest), source_manifest_sha256=sha256_obj(_files(source))))

    _monitor_public(rt, SESSIONS[0])
    rt.weekly_prepare(SESSIONS[0], mind=MIND, live=False)
    now[0] = datetime.combine(SESSIONS[0], time(13, 7), tzinfo=BRT)
    rt.weekly_decide(SESSIONS[0], mind=MIND)
    rt.thesis_prepare(SESSIONS[0])
    folder = thesis_dir(rt.book_root, SESSIONS[0])
    fb, analysis = load_prepared(folder)
    _write(folder / TESE_JSON, template_thesis(analysis, fb, MIND))
    rt.thesis_publish(SESSIONS[0])

    for day in SESSIONS:
        now[0] = datetime.combine(day, time(19, 22), tzinfo=BRT)
        rt.daily_close(day, live=False, mind=MIND)
        folder = rt.daily_dir(day)
        fb = FactBook.model_validate_json((folder / "factbook.json").read_text())
        _write(folder / COMMENTARY_JSON, example_commentary(fb, MIND))
        rt.daily_publish(day)
        if day == SESSIONS[0]:
            preparar(rt, day, mind=MIND)
            data = calcular_semana(rt, day)
            fb = factbook_semana(data)
            _write(out / "reports" / "semanal" / day.isoformat() / COMENTARIO_JSON,
                   modelo_valido(fb, data["mudancas"], montagem=bool(data["montagem"]), mind=MIND))
            publicar(rt, day)
        _monitor_public(rt, day)
    return rt


@pytest.fixture(scope="module")
def paired(tmp_path_factory):
    root = tmp_path_factory.mktemp("runtime_parity")
    source = root / "source"
    cfg = load_config()
    original_cfg = cfg.model_dump(mode="json")
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=SESSIONS[-1])
    rng = np.random.default_rng(730)
    benchmarks = md.benchmarks.copy()
    for factor in cfg.risk_model.macro_factors:
        benchmarks[factor] = 80 * np.cumprod(1 + rng.normal(0, .02, len(benchmarks)))
    write_snapshot(replace(md, benchmarks=benchmarks), source)
    source_before = _files(source)
    driver = root / ".cdp" / "ensaios" / "driver"
    manual = root / ".cdp" / "ensaios" / "manual"
    result = run_replay(source, driver, start=SESSIONS[0], end=SESSIONS[-1],
                        mode="simulado", cfg=cfg, workspace=root)
    rt_manual = _manual(source, manual, cfg)
    def now():
        return datetime.combine(SESSIONS[-1], time(19, 22), tzinfo=BRT)
    rt_driver = Runtime(rt_manual.cfg, driver / "book", driver / "market", driver / "reports",
                        clock=now, store_override=ReplayStore(driver / "market", cfg=rt_manual.cfg,
                        now=now, close_cutoff=time(19, 22)), teses_root=None)
    assert _files(source) == source_before and cfg.model_dump(mode="json") == original_cfg
    assert result["integridade"] and result["registros"] == len(SESSIONS)
    assert len(result["decisoes"]) == 1 and result["decisoes"][0]["efetivada"]
    return rt_driver, rt_manual, result, original_cfg


def test_driver_composes_same_economy_as_public_runtime_in_another_root(paired):
    driver, manual, result, _ = paired
    for rt in (driver, manual):
        ok, issues = rt.verify_all()
        assert ok, issues
        assert read_replay_origin(rt.book).prospective is False
        assert len(rt.book.list_decisions(SESSIONS[0])) == 1
    a, b = (rt.book.load_proposal(SESSIONS[0]) for rt in (driver, manual))
    assert a.positions and a.trades
    # Alvos, ordens e custo estimado são comparados integralmente.
    for field in ("nav_usd", "positions", "trades", "fx_hedges", "risk", "compliance"):
        assert a.model_dump(mode="json")[field] == b.model_dump(mode="json")[field], field
    a, b = (rt.book.load_booked(SESSIONS[0]) for rt in (driver, manual))
    assert a.positions and all(p.shares is not None for p in a.positions)
    assert a.nav_usd == b.nav_usd
    assert a.positions == b.positions
    for day in SESSIONS:
        a, b = (rt.track().get(day) for rt in (driver, manual))
        for field in ("date", "nav_start_usd", "nav_end_usd", "pnl_usd", "ret", "pnl_components",
                      "positions", "attribution", "risk", "alerts", "live_book_week"):
            assert a.model_dump(mode="json")[field] == b.model_dump(mode="json")[field], (day, field)
        da, db = load_daily_risk(driver.track(), a), load_daily_risk(manual.track(), b)
        for field in ("cutoffs", "nav_usd", "weights", "required_macro", "kappa_f", "measures",
                      "binding", "idio_binding"):
            assert da[field] == db[field], (day, field)
    assert driver.track().get(SESSIONS[0]).pnl_components["costs"] < 0
    assert result["nav_final_usd"] == manual.track().get(SESSIONS[-1]).nav_end_usd
    assert driver.book.proposal_state(SESSIONS[0], 1) == manual.book.proposal_state(SESSIONS[0], 1)
    assert driver.kill_switch_active() == manual.kill_switch_active()


def test_only_inception_changes_and_audit_bytes_are_not_economic_oracle(paired):
    driver, manual, _, original = paired
    effective = manual.cfg.model_dump(mode="json")
    assert effective["fund"].pop("inception_date") == SESSIONS[0].isoformat()
    original = {**original, "fund": dict(original["fund"])}
    original["fund"].pop("inception_date")
    assert effective == original
    # Raízes, instantes reais e eventos REPLAY_STEP exclusivos do driver mudam a trilha.
    assert driver.book.audit_head() != manual.book.audit_head()
    assert driver.book.audit.path.read_bytes() != manual.book.audit.path.read_bytes()
    assert read_replay_origin(driver.book).actual_started_at != read_replay_origin(manual.book).actual_started_at
    assert driver.track().get(SESSIONS[-1]).record_hash != manual.track().get(SESSIONS[-1]).record_hash
