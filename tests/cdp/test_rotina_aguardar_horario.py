"""DADOS SIMULADOS: clocks e gates locais; nenhuma rede/trava/execução oficial."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from cdp import executor as ex
from cdp import rotinas as ro
from cdp.__main__ import build_parser
from cdp.workflow.runtime import Runtime

ROOT = Path(__file__).resolve().parents[2]
ROT = ro.carregar(ROOT / "configs/cdp/rotinas.yaml")
BRT = ZoneInfo("America/Sao_Paulo")


class FakeClock:
    def __init__(self, now, mode="normal"):
        self.now, self.elapsed, self.mode, self.calls = now, 0.0, mode, []
        self.on_sleep = lambda: None

    def clock(self):
        return self.now

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        assert 0 < seconds <= 1
        self.calls.append(seconds)
        if self.mode == "interrupt":
            raise KeyboardInterrupt
        if self.mode == "error":
            raise OSError("falha simulada")
        self.elapsed += seconds
        if self.mode == "normal":
            self.now += timedelta(seconds=seconds)
        elif self.mode == "rollback":
            self.now -= timedelta(seconds=seconds)
        elif self.mode == "mono_back":
            self.elapsed = -1
        elif self.mode == "oversleep":
            self.elapsed += 301
            self.now += timedelta(minutes=10)
        self.on_sleep()


def nominal(tid):
    return ro.Cron.ler(ROT.tarefa(tid).cron).proximo(datetime(2026, 10, 5, tzinfo=BRT), BRT)


def wait(tid, clock):
    return ro.aguardar_horario(ROT, tid, clock=clock.clock, monotonic=clock.monotonic, sleep=clock.sleep)


@pytest.mark.parametrize("tid", sorted(ROT.tarefas))
def test_all_12_tasks_early_exact_and_late(tid):
    target = nominal(tid)
    fake = FakeClock(target - timedelta(minutes=3))
    result = wait(tid, fake)
    assert fake.now == target and result["tarefa"] == tid
    assert datetime.fromisoformat(result["agendada_para"]) == target
    assert result["segundos_monotonicos"] == 180
    for instant in (target, target + timedelta(seconds=1)):
        fake = FakeClock(instant)
        assert wait(tid, fake) is None and fake.calls == []


@pytest.mark.parametrize("zone", ["UTC", "America/New_York", "Asia/Tokyo"])
def test_cut_uses_configured_brasilia_day_and_aware_instant(zone):
    target = nominal("cdp-cobertura")
    fake = FakeClock((target - timedelta(minutes=2)).astimezone(ZoneInfo(zone)))
    result = wait("cdp-cobertura", fake)
    assert fake.now == target
    assert datetime.fromisoformat(result["agendada_para"]) == target


def test_five_minute_boundary_is_inclusive_but_earlier_is_not():
    target = nominal("cdp-semanal")
    exact = FakeClock(target - timedelta(minutes=5))
    assert wait("cdp-semanal", exact)["segundos_monotonicos"] == 300
    outside = FakeClock(target - timedelta(minutes=5, microseconds=1))
    assert wait("cdp-semanal", outside) is None and not outside.calls


def test_task_reserve_does_not_wait_for_family_primary():
    fake = FakeClock(datetime(2026, 10, 7, 11, 4, tzinfo=BRT))
    assert wait("cdp-semanal-b", fake) is None and not fake.calls
    assert wait("cdp-semanal", fake)["tarefa"] == "cdp-semanal"


@pytest.mark.parametrize(("tid", "instant", "should_wait"), [
    ("cdp-semanal", "2026-10-10T11:04:00-03:00", False),
    ("cdp-diario-sabado", "2026-10-10T10:04:00-03:00", True),
    ("cdp-calibracao", "2026-11-01T09:12:00-03:00", True),
    ("cdp-calibracao", "2026-11-02T09:12:00-03:00", False),
    ("cdp-calibracao", "2026-10-31T23:59:00-03:00", False),
])
def test_weekend_and_monthday_match_own_cron(tid, instant, should_wait):
    fake = FakeClock(datetime.fromisoformat(instant))
    assert (wait(tid, fake) is not None) is should_wait
    assert bool(fake.calls) is should_wait


@pytest.mark.parametrize("mode", ["rollback", "mono_back", "frozen", "oversleep"])
def test_clock_fault_cannot_reach_gate(mode):
    fake = FakeClock(nominal("cdp-semanal") - timedelta(minutes=3), mode)
    with pytest.raises(ro.ErroEsperaHorario):
        wait("cdp-semanal", fake)
    assert sum(fake.calls) <= 300


def test_clock_requires_timezone_and_finite_monotonic():
    with pytest.raises(ro.ErroEsperaHorario, match="fuso"):
        wait("cdp-semanal", FakeClock(datetime(2026, 10, 7, 11, 4)))
    fake = FakeClock(nominal("cdp-semanal") - timedelta(minutes=1))
    with pytest.raises(ro.ErroEsperaHorario, match="monotônico"):
        ro.aguardar_horario(ROT, "cdp-semanal", clock=fake.clock,
                           monotonic=lambda: float("nan"), sleep=fake.sleep)
    assert not fake.calls


def args(tmp_path, *extra):
    return build_parser().parse_args(["rotinas", "gate", "--tarefa", "cdp-semanal",
                                     "--raiz", str(tmp_path), "--adquirir", *extra])


def setup_cli(monkeypatch, fake):
    monkeypatch.setattr(ro, "_carregar", lambda args: ROT)
    monkeypatch.setattr(ro, "_agora", lambda args: fake.clock())
    monkeypatch.setattr(ro, "clock_time", SimpleNamespace(monotonic=fake.monotonic, sleep=fake.sleep))


def test_command_builds_fresh_runtime_after_wait_and_evaluates_once(monkeypatch, tmp_path, capsys):
    target = nominal("cdp-semanal")
    fake = FakeClock(target - timedelta(minutes=3))
    setup_cli(monkeypatch, fake)
    state = tmp_path / "state.json"
    state.write_text('{"marker":"before"}')
    seen = []
    fake.on_sleep = lambda: state.write_text('{"marker":"after"}')

    def fresh_runtime(cls, cli):
        assert fake.now >= target
        seen.append(("runtime", fake.now))
        return SimpleNamespace(marker=json.loads(state.read_text())["marker"])

    monkeypatch.setattr(Runtime, "from_args", classmethod(fresh_runtime))
    monkeypatch.setattr(ex, "identidade", lambda *a, **k: {"harness": "codex"})
    monkeypatch.setattr(ex, "verificar", lambda *a, **k: (0, {"sou_o_executor": True}))
    monkeypatch.setattr(ex, "git_head", lambda *a: "DADOS SIMULADOS")
    monkeypatch.setattr(ex, "trailers", lambda *a: [])
    monkeypatch.setattr(ex, "estado_dos_caminhos", lambda *a: {})
    monkeypatch.setattr(ex, "ler_execucao", lambda *a: None)

    def acquire(*a, **k):
        assert fake.now >= target
        seen.append(("acquire", fake.now))
        return {"estado": "adquirida", "id": "DADOS SIMULADOS"}

    def register(*a, **k):
        assert fake.now >= target
        seen.append(("register", fake.now))

    monkeypatch.setattr(ex, "trava_adquirir", acquire)
    monkeypatch.setattr(ex, "registrar_execucao", register)
    monkeypatch.setattr(ro, "contexto_do_runtime", lambda rt, now: ro.ContextoGate(hoje=now.date()))
    import cdp.workflow.agenda as ag

    def agenda(rt, now):
        assert now >= target and rt.marker == "after"
        seen.append(("agenda", now))
        return {"fase": "operacao", "semanal": {"acao": "montar", "motivo": "DADOS SIMULADOS"}}

    monkeypatch.setattr(ag, "agenda", agenda)
    original = ro.avaliar

    def evaluate(*a, **k):
        assert k["agora"] >= target and k["manual"] is False
        seen.append(("evaluate", k["agora"]))
        return original(*a, **k)

    monkeypatch.setattr(ro, "avaliar", evaluate)
    assert ro.cmd_gate(args(tmp_path, "--aguardar-horario")) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["executar"] and out["espera_horario"]["tarefa"] == "cdp-semanal"
    assert [x[0] for x in seen] == ["runtime", "evaluate", "agenda", "acquire", "register"]
    assert not (tmp_path / ".cdp").exists()  # callbacks são simulados, não escritor oficial


@pytest.mark.parametrize("mode", ["rollback", "frozen", "interrupt", "error"])
def test_aborted_wait_constructs_no_runtime_and_calls_no_gate(monkeypatch, tmp_path, capsys, mode):
    fake = FakeClock(nominal("cdp-semanal") - timedelta(minutes=1), mode)
    setup_cli(monkeypatch, fake)
    calls = []
    monkeypatch.setattr(Runtime, "from_args", classmethod(lambda *a: calls.append("runtime")))
    monkeypatch.setattr(ro, "avaliar", lambda *a, **k: calls.append("evaluate"))
    monkeypatch.setattr(ex, "trava_adquirir", lambda *a, **k: calls.append("acquire"))
    monkeypatch.setattr(ex, "registrar_execucao", lambda *a, **k: calls.append("register"))
    assert ro.cmd_gate(args(tmp_path, "--aguardar-horario")) == 10
    out = json.loads(capsys.readouterr().out)
    assert not out["executar"] and out["trava"] is out["execucao"] is None
    assert calls == [] and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("extra", [("--manual",), ("--agora", "2026-10-07T11:04:00-03:00")])
def test_wait_does_not_enable_manual_or_historical_clock(monkeypatch, tmp_path, extra):
    monkeypatch.setattr(ro, "_carregar", lambda a: ROT)
    monkeypatch.setattr(Runtime, "from_args", classmethod(lambda *a: pytest.fail("Runtime antecipado")))
    assert ro.cmd_gate(args(tmp_path, "--aguardar-horario", *extra)) == 2


def test_interrupt_in_evaluator_keeps_existing_propagation(monkeypatch, tmp_path):
    fake = FakeClock(nominal("cdp-semanal"))
    setup_cli(monkeypatch, fake)
    monkeypatch.setattr(Runtime, "from_args", classmethod(lambda *a: SimpleNamespace()))

    def interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(ro, "avaliar", interrupt)
    with pytest.raises(KeyboardInterrupt):
        ro.cmd_gate(args(tmp_path, "--aguardar-horario"))


@pytest.mark.parametrize("instant", ["2026-10-07T11:01:00-03:00", "2026-10-07T11:07:00-03:00", "2026-10-07T11:08:00-03:00", "2026-10-10T11:04:00-03:00"])
def test_outside_window_and_no_flag_preserve_protocol(monkeypatch, tmp_path, capsys, instant):
    fixed = datetime.fromisoformat(instant)
    commands = [(ro, False), (ro, True)]
    outputs = []
    for module, flag in commands:
        monkeypatch.setattr(module, "_carregar", lambda a: ROT)
        monkeypatch.setattr(module, "_agora", lambda a: fixed)
        monkeypatch.setattr(Runtime, "from_args", classmethod(lambda *a: SimpleNamespace()))

        def evaluate(rot, tid, **kw):
            assert kw["agora"] == fixed and not kw["manual"]
            return 10, {"tarefa": tid, "executar": False, "motivo": "original", "trava": None}

        monkeypatch.setattr(module, "avaliar", evaluate)
        code = module.cmd_gate(args(tmp_path, *(('--aguardar-horario',) if flag else ())))
        outputs.append((code, capsys.readouterr().out))
    assert outputs[0] == outputs[1]


def test_12_prompts_have_exact_own_id_single_gate_and_opt_in():
    for tid in ROT.tarefas:
        text = ro.prompt(ROT, tid, harness="codex", publicacao="agente")
        assert text.count("uv run python -m cdp rotinas gate --tarefa " + tid + " ") == 1
        assert text.count("--aguardar-horario") == 1
        assert "--manual" not in text
        if ROT.tarefa(tid).grava:
            assert text.index("rotinas gate") < text.index("sincronizar")
    generated = ro.gerar_skills(ROT)
    for rel, text in generated.items():
        assert (ROOT / rel).read_text() == text
        assert (ROOT / rel.replace(".agents/", ".claude/", 1)).read_text() == text
        if "cdp-retomar/" not in rel:
            assert text.count("uv run python -m cdp rotinas gate") == 1
            assert "--aguardar-horario" in text


@pytest.mark.parametrize("opt_in", [False, True])
def test_runtime_interrupt_outside_wait_keeps_original_propagation(monkeypatch, tmp_path, opt_in):
    fake = FakeClock(nominal("cdp-semanal"))
    setup_cli(monkeypatch, fake)

    def interrupt(*a):
        raise KeyboardInterrupt

    monkeypatch.setattr(Runtime, "from_args", classmethod(interrupt))
    monkeypatch.setattr(ro, "avaliar", lambda *a, **k: pytest.fail("não avalia após interrupção"))
    with pytest.raises(KeyboardInterrupt):
        ro.cmd_gate(args(tmp_path, *(('--aguardar-horario',) if opt_in else ())))
