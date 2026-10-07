"""Rotinas como dados (configs/cdp/rotinas.yaml), gates, prompts neutros, exportação para
agendadores, skills neutras (.agents/skills) e a camada de conhecimento agnóstica ao harness
(AGENTS.md canônico, CLAUDE.md, GEMINI.md, .gemini/settings.json e os guias do agente).

Tudo offline: os gates recebem agendas sintéticas; o gate composto usa uma agenda falsa e uma
raiz temporária (sem remoto, a trava fica "indisponivel" e o escritor exclusivo NÃO executa —
falha fechada) ou um remoto local (repositório nu)."""

from __future__ import annotations

import hashlib
import json
import plistlib
import re
import shlex
import subprocess
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from cdp import rotinas as ro
from cdp.__main__ import build_parser, main

ROOT = Path(__file__).resolve().parents[2]
BRT = ZoneInfo("America/Sao_Paulo")
ROT = ro.carregar(ROOT / "configs" / "cdp" / "rotinas.yaml")
MODEL_RE = re.compile(r"(?i)\b(?:claude-(?:opus|sonnet|haiku)[\w.-]*|opus|sonnet|haiku|gpt-[\w.-]+)\b")
SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}(\s+#.*)?$")
AGENTS_FECHAMENTO_SHA256 = "9c1ec3171c390078b30f0c3cf60f0d8951f2b862b99ee75d2935329854692d28"
MEUS_DOCS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "docs/cdp/AGENTE.md", "docs/cdp/AUTOMACAO.md",
             "docs/cdp/REPLICAR.md", "docs/cdp/SITE.md", "docs/cdp/DECISOES.md",
             "docs/cdp/EM_ANDAMENTO.md", "docs/cdp/playbooks/RETOMAR.md",
             "docs/cdp/playbooks/RISCO.md", "docs/cdp/playbooks/STATUS.md",
             "docs/cdp/playbooks/CALIBRACAO.md")


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=BRT)


# ------------------------------------------------------------------------------ agenda


def test_rotinas_yaml_is_coherent():
    assert ro.verificar(ROT, ROOT) == []
    assert main(["rotinas", "verificar", "--raiz", str(ROOT),
                 "--rotinas", str(ROOT / "configs/cdp/rotinas.yaml")]) == 0


def test_expected_tasks_reserves_and_inheritance():
    ids = set(ROT.tarefas)
    assert {"cdp-status", "cdp-semanal", "cdp-semanal-b", "cdp-semanal-c", "cdp-semanal-d",
            "cdp-risco-1330", "cdp-risco-1603", "cdp-diario", "cdp-diario-reforco",
            "cdp-diario-sabado", "cdp-cobertura", "cdp-calibracao"} == ids
    b = ROT.tarefa("cdp-semanal-b")
    assert b.reserva_de == "cdp-semanal" and b.familia == "cdp-semanal" and b.hora == "12:07"
    assert b.playbook == ROT.tarefa("cdp-semanal").playbook and b.exclusiva
    r2 = ROT.tarefa("cdp-risco-1603")
    assert r2.playbook == "docs/cdp/playbooks/RISCO.md" and r2.reserva_de is None
    assert r2.concorrencia == "compartilhada" and not r2.exclusiva and r2.grava
    sab = ROT.tarefa("cdp-diario-sabado")
    assert sab.dias == ("sab",) and sab.cron_utc == "7 13 * * 6"
    assert not ROT.tarefa("cdp-status").grava
    for t in ROT.tarefas.values():  # escritores só nos caminhos do livro
        assert all(any(c == b or c.startswith(b + "/") for b in ro.CAMINHOS_DO_LIVRO)
                   for c in t.caminhos), t.id


@pytest.mark.parametrize(("brt", "utc"), [
    ("7 21 * * 1-5", "7 0 * * 2-6"),        # reforço vira o dia em UTC
    ("37 22 * * 1-4", "37 1 * * 2-5"),      # cobertura
    ("7 10 * * 6", "7 13 * * 6"),           # repescagem de sábado
    ("15 9 1 * *", "15 12 1 * *"),          # calibração mensal
    ("30 23 * * 0", "30 2 * * 1"),          # domingo → segunda
    ("0 22 15 * *", "0 1 16 * *"),          # dia do mês também vira
])
def test_cron_brt_to_utc(brt: str, utc: str):
    assert ro.Cron.ler(brt).em_utc().texto() == utc


def test_cron_parsing_and_firings():
    c = ro.Cron.ler("22 19 * * 1-5")
    assert c.casa(date(2026, 10, 9)) and not c.casa(date(2026, 10, 10))
    ult = c.ultimo(_dt("2026-10-12T08:00:00"), BRT)
    assert ult == _dt("2026-10-09T19:22:00")  # sexta anterior
    assert c.proximo(_dt("2026-10-09T19:22:00"), BRT) == _dt("2026-10-12T19:22:00")
    assert ro.Cron.ler("0 0 * * 7").dias_semana == frozenset({0})
    both = ro.Cron.ler("0 9 1 * 1")  # regra do cron: dia do mês OU dia da semana
    assert both.casa(date(2026, 10, 1)) and both.casa(date(2026, 10, 5))
    for ruim in ("0 9 * *", "*/5 9 * * *", "0 9 * 10 *", "0 25 * * *", "0 9 * * 1-9"):
        with pytest.raises(ro.ErroRotinas):
            ro.Cron.ler(ruim)
    with pytest.raises(ro.ErroRotinas):
        ro.Cron.ler("0 22 30 * *").em_utc()


def test_proximas_orders_firings():
    prox = ROT.proximas(_dt("2026-10-09T10:00:00"), 6)
    assert [t.id for _, t in prox] == ["cdp-semanal", "cdp-semanal-b", "cdp-semanal-c",
                                       "cdp-risco-1330", "cdp-semanal-d", "cdp-risco-1603"]


def _yaml(tmp_path: Path, tarefas: dict) -> Path:
    p = tmp_path / "rotinas.yaml"
    p.write_text(yaml.safe_dump({"versao": 1, "fuso": "America/Sao_Paulo",
                                 "repositorio": "x/y", "ramo": "main", "tarefas": tarefas},
                                allow_unicode=True), encoding="utf-8")
    return p


BASE = {"descricao": "d", "playbook": "docs/cdp/playbooks/DIARIO.md", "skill": "cdp-x",
        "hora": "19:22", "dias": ["seg"], "cron": "22 19 * * 1", "cron_utc": "22 22 * * 1",
        "gate": "diario", "caminhos": ["book"]}


@pytest.mark.parametrize("mudanca", [
    {"campo_novo": 1}, {"gate": "outro"}, {"cron": "x"}, {"hora": "25:00"},
    {"caminhos": ["../fora"]}, {"modelo": "um-modelo-qualquer"}, {"alvos": ["nuvem-x"]},
    {"pre_comando": "rm -rf /"}, {"dias": ["dom", "xyz"]},
])
def test_invalid_task_is_rejected(tmp_path, mudanca):
    with pytest.raises(ro.ErroRotinas):
        ro.carregar(_yaml(tmp_path, {"cdp-x": {**BASE, **mudanca}}))


def test_verificar_catches_utc_drift_and_crowded_writers(tmp_path):
    rot = ro.carregar(_yaml(tmp_path, {
        "cdp-x": {**BASE, "cron_utc": "22 19 * * 1"},
        "cdp-y": {**BASE, "skill": "cdp-y", "hora": "19:40", "cron": "40 19 * * 1",
                  "cron_utc": "40 22 * * 1"}}))
    probs = " ".join(ro.verificar(rot, ROOT))
    assert "cron_utc" in probs and "escritores exclusivos a 18 min" in probs


# ------------------------------------------------------------------------------- gates

CTX = ro.ContextoGate(hoje=date(2026, 10, 12))


def _ag(**kw) -> dict:
    base = {"fase": "operacao", "reinicio": {"pendente": False}, "semanal": {"acao": "nenhuma",
            "motivo": "a montagem desta semana é sexta-feira", "semana": date(2026, 10, 16)},
            "fechamentos_pendentes": [], "publicacoes_pendentes": [], "teses_pendentes": [],
            "relatorio_semanal": {"pendente": False}, "cobertura": {"snapshot_pendente": False},
            "ultimo_registro_diario": date(2026, 10, 9), "pregao_b3_hoje": True,
            "kill_switch": False}
    base.update(kw)
    return base


@pytest.mark.parametrize(("ag", "executa"), [
    (_ag(), False),
    (_ag(semanal={"acao": "montar", "etapa": "prepare", "motivo": "dia de montagem"}), True),
    (_ag(semanal={"acao": "tese", "motivo": "tese pendente"}), True),
    (_ag(semanal={"acao": "prazo_vencido", "motivo": "prazo vencido"}), False),
    (_ag(semanal={"acao": "aguardar", "motivo": "pesquisa às 11:00"}), False),
    (_ag(reinicio={"pendente": True}), True),
])
def test_gate_semanal(ag, executa):
    assert ro.gate_semanal(ag, CTX).executar is executa


def test_gate_diario_items():
    assert not ro.gate_diario(_ag(), CTX).executar
    d = ro.gate_diario(_ag(fechamentos_pendentes=[date(2026, 10, 9), date(2026, 10, 12)],
                           publicacoes_pendentes=[{"data": date(2026, 10, 8)}],
                           teses_pendentes=[date(2026, 10, 16)],
                           relatorio_semanal={"pendente": True, "data": date(2026, 10, 9)},
                           cobertura={"snapshot_pendente": True, "data": date(2026, 10, 9)}),
                       CTX)
    assert d.executar and len(d.itens) == 5 and "2026-10-12" in d.motivo
    # tese pendente de semana antiga não dispara o diário (só a semana corrente)
    assert not ro.gate_diario(_ag(teses_pendentes=[date(2026, 10, 2)]), CTX).executar
    # pré-início: só quando a base de mercado está defasada
    pre = _ag(fase="pre_inicio", ultimo_registro_diario=None)
    ctx = ro.ContextoGate(hoje=date(2026, 10, 7), base_ultimo_pregao=lambda: date(2026, 10, 6),
                          ultimo_pregao_encerrado=lambda: date(2026, 10, 7))
    assert ro.gate_diario(pre, ctx).executar
    ctx2 = ro.ContextoGate(hoje=date(2026, 10, 7), base_ultimo_pregao=lambda: date(2026, 10, 7),
                           ultimo_pregao_encerrado=lambda: date(2026, 10, 7))
    assert not ro.gate_diario(pre, ctx2).executar


def test_gate_risco():
    assert ro.gate_risco(_ag(), CTX).executar
    assert not ro.gate_risco(_ag(fase="pre_inicio"), CTX).executar
    assert not ro.gate_risco(_ag(reinicio={"pendente": True}), CTX).executar
    assert not ro.gate_risco(_ag(ultimo_registro_diario=None), CTX).executar
    # 2026-10-12: feriado na B3 com a NYSE aberta
    nyse = ro.ContextoGate(hoje=date(2026, 10, 12), pregao_nyse_hoje=lambda: True)
    assert ro.gate_risco(_ag(pregao_b3_hoje=False), nyse).executar
    assert not ro.gate_risco(_ag(pregao_b3_hoje=False), CTX).executar


def test_gate_cobertura_and_calibracao(tmp_path):
    cheio = ro.ContextoGate(hoje=date(2026, 10, 12), fila_notas=lambda: {
        "pendentes": 3, "fila": [{"issuer_id": "BR_VALE"}]})
    assert ro.gate_cobertura(_ag(), cheio).executar
    assert not ro.gate_cobertura(_ag(), CTX).executar

    def falha():
        raise OSError("sem base")

    d = ro.gate_cobertura(_ag(), ro.ContextoGate(hoje=date(2026, 10, 12), fila_notas=falha))
    assert not d.executar and "indisponível" in d.motivo
    assert not ro.gate_cobertura(_ag(reinicio={"pendente": True}), cheio).executar
    dia1 = ro.ContextoGate(hoje=date(2026, 11, 1), reports_root=tmp_path)
    assert ro.gate_calibracao(_ag(), dia1).executar
    feito = tmp_path / "backtest" / "2026-11-01" / "CALIBRACAO_MENSAL.md"
    feito.parent.mkdir(parents=True)
    feito.write_text("x")
    assert not ro.gate_calibracao(_ag(), dia1).executar
    assert not ro.gate_calibracao(_ag(), CTX).executar


# ------------------------------------------------------------------------ gate composto


@pytest.fixture
def raiz(tmp_path) -> Path:
    (tmp_path / "configs" / "cdp").mkdir(parents=True)
    for n in ("executor.yaml", "rotinas.yaml"):
        (tmp_path / "configs" / "cdp" / n).write_bytes((ROOT / "configs/cdp" / n).read_bytes())
    return tmp_path


def _avaliar(raiz: Path, tarefa: str, agora: str, env: dict, ag: dict | None = None, **kw):
    return ro.avaliar(ROT, tarefa, rt=None, agora=_dt(agora), raiz=raiz, env=env,
                      agenda_fn=lambda rt, now: ag or _ag(
                          fechamentos_pendentes=[date(2026, 10, 12)]), ctx=CTX, **kw)


def test_gate_requires_the_designated_executor(raiz):
    code, out = _avaliar(raiz, "cdp-diario", "2026-10-12T19:25:00", {})
    assert code == ro.EXIT_PULAR and "desconhecida" in out["motivo"]
    code, out = _avaliar(raiz, "cdp-diario", "2026-10-12T19:25:00",
                         {"CDP_EXECUTOR": "claude-cloud"})
    assert code == ro.EXIT_PULAR and "local-pc" in out["motivo"]
    # tarefa só de leitura não depende do executor
    code, out = _avaliar(raiz, "cdp-status", "2026-10-12T08:31:00", {})
    assert code == ro.EXIT_EXECUTAR and out["executar"]
    # ensaio ignora o executor e nunca pega a trava
    code, out = _avaliar(raiz, "cdp-diario", "2026-10-12T19:25:00", {"CDP_ENSAIO": "1"},
                         adquirir=True)
    assert code == ro.EXIT_EXECUTAR and out["ensaio"] and out["trava"] is None


def test_gate_stale_guard_and_execution_record(raiz):
    env = {"CDP_EXECUTOR": "local-pc", "CDP_HARNESS": "codex"}
    code, out = _avaliar(raiz, "cdp-semanal", "2026-10-09T15:30:00", env,
                         ag=_ag(semanal={"acao": "montar", "motivo": "x"}))
    assert code == ro.EXIT_PULAR and "atrasada" in out["motivo"]
    code, out = _avaliar(raiz, "cdp-semanal", "2026-10-09T15:30:00", env, manual=True,
                         ag=_ag(semanal={"acao": "montar", "motivo": "x"}))
    assert code == ro.EXIT_EXECUTAR
    # sem remoto, a trava fica indisponível: um escritor exclusivo NÃO executa (falha fechada)
    antes = len(list((raiz / ".cdp/execucoes").iterdir()))
    code, out = _avaliar(raiz, "cdp-diario", "2026-10-12T19:25:00", env, adquirir=True)
    assert code == ro.EXIT_PULAR and out["trava"]["estado"] == "indisponivel"
    assert "sem a trava" in out["motivo"]
    assert len(list((raiz / ".cdp/execucoes").iterdir())) == antes
    # só uma sessão de operador, explicitamente, segue sem a trava
    code, out = _avaliar(raiz, "cdp-diario", "2026-10-12T19:25:00", env, adquirir=True,
                         sem_trava=True)
    assert code == ro.EXIT_EXECUTAR and out["mente"] == "codex" and out["sem_trava"]
    uuid.UUID(out["execucao"])
    assert f"CDP-Execucao: {out['execucao']}" in out["trailers"]
    assert "CDP-Tarefa: cdp-diario" in out["trailers"]
    reg = json.loads((raiz / ".cdp/execucoes" / f"{out['execucao']}.json").read_text())
    assert reg["tarefa"] == "cdp-diario" and reg["itens"] == out["itens"]
    assert reg["sem_trava"] is True and reg["instantaneo"] == {} and reg["mente"] == "codex"
    # prévia (script de rotina): não registra execução
    n = len(list((raiz / ".cdp/execucoes").iterdir()))
    code, out = _avaliar(raiz, "cdp-diario", "2026-10-12T19:25:00", env, registrar=False)
    assert code == ro.EXIT_EXECUTAR and out["execucao"] is None
    assert len(list((raiz / ".cdp/execucoes").iterdir())) == n
    code, out = _avaliar(raiz, "cdp-diario", "2026-10-12T19:25:00", env, ag=_ag())
    assert code == ro.EXIT_PULAR and out["motivo"] == "nada pendente no fechamento diário"


def test_gate_cli_github_format_and_config_error(capsys):
    assert main(["rotinas", "gate", "--tarefa", "cdp-inexistente"]) == ro.EXIT_CONFIG
    capsys.readouterr()


# ------------------------------------------------------------------------------ prompts


def _cmds(texto: str) -> list[str]:
    return re.findall(r"`(uv run python -m cdp [^`]+)`", texto)


def _parse(cmd: str) -> None:
    c = re.sub(r"<[^<>]+>", "X", cmd)
    toks = shlex.split(c)
    assert toks[:5] == ["uv", "run", "python", "-m", "cdp"], cmd
    build_parser().parse_args(toks[5:])


@pytest.mark.parametrize("tid", sorted(ROT.tarefas))
@pytest.mark.parametrize("harness", ["claude", "codex", "gemini"])
def test_prompts_follow_the_envelope(tid: str, harness: str):
    t = ROT.tarefa(tid)
    p = ro.prompt(ROT, tid, harness=harness)
    assert f"--tarefa {tid}" in p and "AGENTS.md" in p and t.playbook in p
    assert "nunca use --force" in p and "não confiáveis" in p
    if harness == "claude":
        assert "nunca publique artifacts" in p and ".claude/skills/" in p
    else:  # Codex, Gemini, Antigravity: nada do Claude (artifact, .claude/) no prompt
        assert "artifact" not in p and ".claude/" not in p and ".agents/skills/" in p
    if t.exclusiva:
        assert "--adquirir" in p and "trava liberar" in p and "trava renovar" in p
    if t.grava:
        assert "cdp sincronizar --executar" in p and f"cdp publicar --tarefa {tid}" in p
        assert p.index("rotinas gate") < p.index("sincronizar") < p.index("cdp publicar")
    else:
        assert "publicar" not in p and "Não grave arquivos" in p
    for c in _cmds(p):
        _parse(c)
    assert not MODEL_RE.findall(p)


def test_prompt_variants():
    ens = ro.prompt(ROT, "cdp-diario", ensaio=True)
    assert "ENSAIO" in ens and "--ensaio" in ens and "commit local" in ens
    assert "trava liberar" not in ens and "--trava" not in ens   # ensaio nunca toca a trava
    exe = ro.prompt(ROT, "cdp-diario", harness="codex", publicacao="executor")
    assert "não rode `cdp rotinas gate`" in exe and "--mind codex" in exe
    assert "cdp publicar --tarefa" not in exe and "uv sync" not in exe
    assert "nem se a skill ou o AGENTS.md mandarem" in exe
    agente = ro.prompt(ROT, "cdp-semanal", harness="claude")
    assert ("cdp publicar --tarefa cdp-semanal --mensagem" in agente
            and "--execucao <execucao> --trava <trava.id> --mente claude-code" in agente)
    risco = ro.prompt(ROT, "cdp-risco-1330", harness="gemini")
    assert "--execucao <execucao> --mente gemini" in risco and "--trava" not in risco
    assert "--manual" in ro.prompt(ROT, "cdp-diario", manual=True)


# ---------------------------------------------------------------------------- exportação


def test_export_claude_routines_bodies():
    corpos = ro.exportar_claude_routines(ROT, ambiente="env_x", modelos={"forte": "m-forte"})
    alvo = [t for t in ROT.tarefas.values() if "claude-routines" in t.alvos]
    assert len(corpos) == len(alvo) == len(ROT.tarefas)
    uuids = set()
    for c, t in zip(corpos, alvo, strict=True):
        assert c["name"] == f"CDP · {t.id} ({t.hora} BRT)"
        assert c["cron_expression"] == t.cron_utc and c["enabled"] is False
        ccr = c["job_config"]["ccr"]
        assert ccr["environment_id"] == "env_x"
        sc = ccr["session_context"]
        assert sc["sources"] == [{"git_repository": {
            "url": "https://github.com/arielassayag/MarketSummary"}}]
        assert set(sc["allowed_tools"]) == set(ro.FERRAMENTAS_NUVEM)
        assert ("model" in sc) == (t.modelo == "forte")
        ev = ccr["events"][0]["data"]
        assert uuid.UUID(ev["uuid"]).version == 4 and ev["uuid"] == ev["uuid"].lower()
        uuids.add(ev["uuid"])
        assert ev["type"] == "user" and ev["parent_tool_use_id"] is None
        assert ev["message"]["role"] == "user" and ev["message"]["content"] == ro.prompt(
            ROT, t.id)
        assert c["mcp_connections"] == [] and c["persist_session"] is False
    assert len(uuids) == len(corpos)
    assert all(c["enabled"] for c in ro.exportar_claude_routines(ROT, ativar=True))


def test_export_cli_prints_name_cron_and_prompt(capsys):
    assert main(["rotinas", "exportar", "--alvo", "claude-routines", "--raiz", str(ROOT),
                 "--rotinas", str(ROOT / "configs/cdp/rotinas.yaml")]) == 0
    out = capsys.readouterr()
    corpos = json.loads(out.out)
    assert {c["name"] for c in corpos} == {ro.nome_rotina(t) for t in ROT.tarefas.values()}
    assert "CDP_EXECUTOR=claude-cloud" in out.err
    assert main(["rotinas", "exportar", "--alvo", "claude-routines", "--formato", "md",
                 "--rotinas", str(ROOT / "configs/cdp/rotinas.yaml")]) == 0
    md = capsys.readouterr().out
    assert "cron (UTC): `7 0 * * 2-6`" in md and "## CDP · cdp-diario-reforco (21:07 BRT)" in md


def _run_blocks(wf: dict) -> list[str]:
    return [s["run"] for job in wf["jobs"].values() for s in job.get("steps", []) if "run" in s]


def _uses(wf: dict) -> list[str]:
    return [s["uses"] for job in wf["jobs"].values() for s in job.get("steps", []) if "uses" in s]


def test_export_github_actions_workflow():
    texto = ro.exportar_github_actions(ROT)
    wf = yaml.safe_load(texto)
    on = wf[True] if True in wf else wf["on"]
    crons = {c["cron"] for c in on["schedule"]}
    assert crons == {t.cron_utc for t in ROT.tarefas.values() if "github-actions" in t.alvos}
    assert wf["permissions"] == {"contents": "read"}
    # fila por tarefa (cada disparo tem horário próprio), nunca um grupo único para todas
    assert "github.event.schedule" in wf["concurrency"]["group"]
    assert wf["concurrency"]["cancel-in-progress"] is False
    gate, mente, pub = wf["jobs"]["gate"], wf["jobs"]["mente"], wf["jobs"]["publicar"]
    assert gate["if"] == "vars.CDP_ROTINAS_ATIVAS == '1'"
    # permissões por job: a IA roda num job só de leitura e sem credencial de escrita
    assert gate["permissions"] == {"contents": "write"}
    assert mente["permissions"] == {"contents": "read"}
    assert pub["permissions"] == {"contents": "write", "actions": "write"}
    assert mente["needs"] == "gate" and pub["needs"] == ["gate", "mente"]
    assert "always()" in pub["if"]
    for run in _run_blocks(wf):
        assert "${{" not in run
    for u in _uses(wf):
        assert SHA_RE.match(u), u
    for job in (gate, mente, pub):
        assert job["steps"][0]["with"]["persist-credentials"] is False
    assert "github.token" not in json.dumps(mente) and "CDP_GIT_TOKEN" not in json.dumps(mente)
    assert mente["steps"][0]["with"]["ref"] == pub["steps"][0]["with"]["ref"] == \
        "${{ needs.gate.outputs.sha }}"
    roteiro = next(s for s in mente["steps"] if s.get("name") == "Roteiro da tarefa")
    assert "--publicacao executor --sem-gate" in roteiro["run"]
    assert mente["env"]["CDP_TRAVA_ID"] == "${{ needs.gate.outputs.trava_id }}"
    assert any("cdp entrega exportar" in s.get("run", "") for s in mente["steps"])
    publica = next(s for s in pub["steps"] if s.get("name") == "Importar e publicar")["run"]
    assert "cdp entrega importar" in publica and '--execucao "$EXECUCAO"' in publica
    assert '--trava "$TRAVA"' in publica
    libera = pub["steps"][-1]
    assert libera["if"] == "always()" and "trava liberar" in libera["run"]
    instalar = next(s for s in mente["steps"] if s.get("name") == "Instalar o harness")["run"]
    assert "claude-code) CDP_HARNESS=claude" in instalar and "antigravity) CDP_HARNESS=agy" in instalar
    assert "antigravity.google/cli/install.sh" in instalar and "exit 1" in instalar
    assert 'CDP_HARNESS: "codex"' in ro.exportar_github_actions(ROT, harness="codex")
    assert 'CDP_HARNESS: "agy"' in ro.exportar_github_actions(ROT, harness="antigravity")


def test_export_other_schedulers(tmp_path, capsys):
    cron = ro.exportar_cron(ROT)
    assert "CRON_TZ=America/Sao_Paulo" in cron and "22 19 * * 1-5 cd" in cron
    assert "7 0 * * 2-6" in ro.exportar_cron(ROT, utc=True)
    plists = ro.exportar_launchd(ROT)
    p = plistlib.loads(plists["com.cdp.cdp-calibracao.plist"].encode())
    assert p["StartCalendarInterval"] == [{"Day": 1, "Hour": 9, "Minute": 15}]
    p = plistlib.loads(plists["com.cdp.cdp-semanal.plist"].encode())
    assert len(p["StartCalendarInterval"]) == 5
    win = ro.exportar_windows(ROT)
    assert "Register-ScheduledTask" in win and "/SC MONTHLY /D 1" in win
    assert "-AllowStartIfOnBatteries" in win
    assert "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=19;BYMINUTE=22" == ro.rrule(
        ROT.tarefa("cdp-diario"))
    assert ro.rrule(ROT.tarefa("cdp-calibracao")).startswith("RRULE:FREQ=MONTHLY;BYMONTHDAY=1")
    assert main(["rotinas", "exportar", "--alvo", "launchd", "--saida", str(tmp_path / "la"),
                 "--rotinas", str(ROOT / "configs/cdp/rotinas.yaml")]) == 0
    assert len(list((tmp_path / "la").glob("com.cdp.*.plist"))) == len(ROT.tarefas)
    capsys.readouterr()
    assert main(["rotinas", "resolver", "--cron-utc", "7  0 * * 2-6",
                 "--rotinas", str(ROOT / "configs/cdp/rotinas.yaml")]) == 0
    assert capsys.readouterr().out.strip() == "tarefa=cdp-diario-reforco"
    assert main(["rotinas", "resolver", "--cron-utc", "1 2 3 * *",
                 "--rotinas", str(ROOT / "configs/cdp/rotinas.yaml")]) == ro.EXIT_CONFIG
    capsys.readouterr()


def test_markdown_table_in_agents_md_is_the_generated_one():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert ro.exportar_markdown(ROT) in agents


def test_pre_command_only_when_missing(tmp_path):
    hoje = date(2026, 11, 1)
    cmd = ro.pre_comando(ROT, "cdp-calibracao", tmp_path, hoje)
    assert cmd == ("uv run python -m cdp backtest --start 2021-01-04 --out "
                   "reports/backtest/2026-11-01/mensal")
    m = tmp_path / "reports/backtest/2026-11-01/mensal/metrics.json"
    m.parent.mkdir(parents=True)
    m.write_text("{}")
    assert ro.pre_comando(ROT, "cdp-calibracao", tmp_path, hoje) is None
    assert ro.pre_comando(ROT, "cdp-diario", tmp_path, hoje) is None


# --------------------------------------------------------------------------- skills neutras

SKILLS = ROOT / ".agents" / "skills"
CHAVES_PADRAO = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def _fm(path: Path) -> tuple[dict, str]:
    texto = path.read_text(encoding="utf-8")
    assert texto.startswith("---\n")
    fim = texto.index("\n---\n", 4)
    return yaml.safe_load(texto[4:fim]), texto[fim + 5:]


def test_neutral_skills_are_generated_and_in_sync():
    gerado = ro.gerar_skills(ROT)
    for rel, txt in gerado.items():
        assert (ROOT / rel).read_text(encoding="utf-8") == txt, (
            f"{rel} desatualizada: rode `uv run python -m cdp skills sincronizar`")
    no_disco = {p.relative_to(ROOT).as_posix() for p in SKILLS.glob("*/SKILL.md")}
    assert no_disco == set(gerado)
    assert ro.sincronizar_skills(ROT, ROOT, verificar_apenas=True)["ok"]


def test_neutral_skills_cover_every_plugin_skill_and_follow_the_spec():
    plugin = {p.name for p in (ROOT / "plugins/cdp/skills").iterdir() if p.is_dir()}
    neutras = {p.name for p in SKILLS.iterdir() if p.is_dir()}
    assert {f"cdp-{n}" for n in plugin} | {"cdp-retomar"} == neutras
    for path in SKILLS.glob("*/SKILL.md"):
        fm, corpo = _fm(path)
        assert set(fm) <= CHAVES_PADRAO, path
        assert fm["name"] == path.parent.name and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*",
                                                                fm["name"])
        assert 50 <= len(fm["description"]) <= 1024
        assert len(fm.get("compatibility", "")) <= 500
        assert all(isinstance(v, str) for v in fm["metadata"].values())
        assert len(corpo.splitlines()) < 500
        for c in _cmds(corpo):
            _parse(c)
        assert not MODEL_RE.findall(path.read_text(encoding="utf-8"))
        if fm["name"] != "cdp-retomar":
            assert fm["metadata"]["playbook"] in corpo and (ROOT / fm["metadata"]["playbook"]
                                                            ).is_file()


def test_gitignore_keeps_neutral_skills_versioned():
    r = subprocess.run(["git", "check-ignore", "-q", ".agents/skills/cdp-diario/SKILL.md"],
                       cwd=ROOT, capture_output=True, check=False)
    assert r.returncode == 1, ".gitignore ignora .agents/skills (use .agents/* + !.agents/skills/)"
    r = subprocess.run(["git", "check-ignore", "-q", ".cdp/local.yaml"], cwd=ROOT,
                       capture_output=True, check=False)
    assert r.returncode == 0


# -------------------------------------------------------------------- camada de conhecimento


def test_agents_md_is_canonical_and_small():
    raw = (ROOT / "AGENTS.md").read_bytes()
    assert len(raw) < 32 * 1024  # limite padrão do Codex
    linhas = raw.split(b"\n")
    fechamento = b"\n".join(linhas[:22]) + b"\n"
    assert hashlib.sha256(fechamento).hexdigest() == AGENTS_FECHAMENTO_SHA256
    texto = raw.decode("utf-8")
    for agulha in ("Pegar o bonde andando", "uv run python -m cdp estado",
                   "docs/cdp/EM_ANDAMENTO.md", "docs/cdp/DECISOES.md", "configs/cdp/executor.yaml",
                   "docs/cdp/teses/<semana>.json", ".agents/skills", "docs/cdp/AUTOMACAO.md"):
        assert agulha in texto, agulha
    from cdp.ui.data import agents_invariants

    sec, origem = agents_invariants(ROOT / "AGENTS.md")
    assert sec and "Números só em código" in sec and "Invariantes do CDP" in origem


def test_harness_adapters_point_to_agents_md():
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in claude and len(claude.splitlines()) <= 40
    gemini = (ROOT / "GEMINI.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in gemini.splitlines()[2] and "--mind gemini" in gemini
    cfg = json.loads((ROOT / ".gemini" / "settings.json").read_text(encoding="utf-8"))
    assert cfg["context"]["fileName"] == ["AGENTS.md", "GEMINI.md"]


@pytest.mark.parametrize("doc", MEUS_DOCS)
def test_agent_docs_commands_parse_and_links_resolve(doc: str):
    texto = (ROOT / doc).read_text(encoding="utf-8")
    for c in _cmds(texto):
        _parse(c)
    for ref in re.findall(r"`((?:docs|configs|scripts|src|plugins)/[\w./-]+\.(?:md|yaml|sh|ps1|py))`",
                          texto):
        assert (ROOT / ref).exists(), (doc, ref)
    assert not MODEL_RE.findall(texto), doc
    assert ("quar" + "tr") not in texto.lower()


@pytest.mark.parametrize("doc", ["docs/cdp/REPLICAR.md", "docs/cdp/SITE.md"])
def test_public_guides_have_no_internal_backstage_terms(doc: str):
    texto = (ROOT / doc).read_text(encoding="utf-8").lower()
    for termo in ("reinicio", "pré-início", "ensaio", "segunda-feira, 05"):
        assert termo not in texto, termo


def test_operation_configs_have_no_model_identifiers():
    for rel in ("configs/cdp/rotinas.yaml", "configs/cdp/executor.yaml", "configs/cdp/site.yaml",
                ".gemini/settings.json", "scripts/cdp_rotina.sh", "scripts/cdp_rotina.ps1"):
        assert not MODEL_RE.findall((ROOT / rel).read_bytes().decode("utf-8-sig")), rel


# ----------------------------------------------------------------------------- runner


def test_runner_scripts_are_valid():
    sh = ROOT / "scripts" / "cdp_rotina.sh"
    texto = sh.read_text(encoding="utf-8")
    assert texto.startswith("#!/usr/bin/env bash") and "\r\n" not in texto
    assert subprocess.run(["bash", "-n", str(sh)], check=False).returncode == 0
    for agulha in ("rotinas gate", "rotinas prompt", "rotinas conferir", "trava liberar",
                   "exit 75", "exit 78", "CDP_HARNESS_CMD", "--seco"):
        assert agulha in texto, agulha
    raw = (ROOT / "scripts" / "cdp_rotina.ps1").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    ps = raw.decode("utf-8-sig")
    for agulha in ("rotinas gate", "rotinas prompt", "rotinas conferir", "exit 75", "exit 78",
                   "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8"):
        assert agulha in ps, agulha


def test_runner_skips_without_a_model_call(tmp_path):
    """Com o gate dizendo "pular" (10), o harness nunca é chamado."""
    fake = tmp_path / "bin"
    fake.mkdir()
    marca = tmp_path / "harness_chamado"
    (fake / "uv").write_text("#!/usr/bin/env bash\n"
                             'if [ "$4 $5 $6" = "cdp rotinas gate" ]; then '
                             'echo \'{"motivo": "nada pendente"}\'; exit 10; fi\nexit 0\n')
    (fake / "claude").write_text(f"#!/usr/bin/env bash\ntouch {marca}\n")
    for f in fake.iterdir():
        f.chmod(0o755)
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "cdp_rotina.sh").write_bytes((ROOT / "scripts/cdp_rotina.sh").read_bytes())
    (repo / "scripts" / "cdp_rotina.sh").chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)}
    r = subprocess.run([str(repo / "scripts/cdp_rotina.sh"), "cdp-diario", "--harness", "claude"],
                       env=env, capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sem execução" in r.stdout and not marca.exists()
    r = subprocess.run([str(repo / "scripts/cdp_rotina.sh"), "x"], env=env, capture_output=True,
                       text=True, timeout=30, check=False)
    assert r.returncode == 2


def test_last_scheduled_slot_covers_utc_midnight():
    t = ROT.tarefa("cdp-diario-reforco")
    agora = _dt("2026-10-09T21:30:00")
    slot = ro.Cron.ler(t.cron).ultimo(agora, BRT)
    assert slot == _dt("2026-10-09T21:07:00") and agora - slot < timedelta(minutes=30)


# ------------------------------------------------------- trava: falha fechada e reentrada


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                          env={**__import__("os").environ, "LC_ALL": "C"}).stdout.strip()


@pytest.fixture
def dois_clones(tmp_path) -> tuple[Path, Path]:
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remoto)], check=True)
    clones = []
    for nome in ("a", "b"):
        c = tmp_path / nome
        if not clones:
            c.mkdir()
            _git(c, "init", "-q", "-b", "main")
            _git(c, "config", "user.name", "Teste")
            _git(c, "config", "user.email", "t@example.com")
            (c / "configs/cdp").mkdir(parents=True)
            for n in ("executor.yaml", "rotinas.yaml"):
                (c / "configs/cdp" / n).write_bytes((ROOT / "configs/cdp" / n).read_bytes())
            (c / ".gitignore").write_text(".cdp/\n")
            _git(c, "add", "-A")
            _git(c, "commit", "-qm", "inicial")
            _git(c, "remote", "add", "origin", str(remoto))
            _git(c, "push", "-q", "origin", "main")
        else:
            subprocess.run(["git", "clone", "-q", str(remoto), str(c)], check=True)
        clones.append(c)
    return clones[0], clones[1]


MONTAR = _ag(semanal={"acao": "montar", "motivo": "dia de montagem"})
PC = {"CDP_EXECUTOR": "local-pc", "CDP_HARNESS": "claude-code"}


def test_gate_lock_is_fail_closed_exclusive_and_reentrant(dois_clones):
    a, b = dois_clones
    # a principal (11:07) adquire a trava às 11:30 (validade de 50 min: até 12:20)
    code, out = _avaliar(a, "cdp-semanal", "2026-10-09T11:30:00", PC, ag=MONTAR, adquirir=True)
    assert code == ro.EXIT_EXECUTAR and out["trava"]["estado"] == "adquirida"
    tid = out["trava"]["id"]
    reg = json.loads((a / ".cdp/execucoes" / f"{out['execucao']}.json").read_text())
    assert reg["trava"] == tid and "instantaneo" in reg
    # a reserva (outro clone) não executa enquanto a principal segura a trava
    code, out = _avaliar(b, "cdp-semanal-b", "2026-10-09T12:08:00", PC, ag=MONTAR,
                         adquirir=True)
    assert code == ro.EXIT_PULAR and out["trava"]["estado"] == "ocupada_por_outro"
    # prévia do script de rotina: só lê a trava e já pula, sem chamar a IA
    code, out = _avaliar(b, "cdp-semanal-b", "2026-10-09T12:08:00", PC, ag=MONTAR,
                         registrar=False)
    assert code == ro.EXIT_PULAR and "em andamento" in out["motivo"]
    # reentrada: a mesma execução (CDP_TRAVA_ID) roda o gate de novo e continua com a trava
    code, out = _avaliar(b, "cdp-semanal", "2026-10-09T11:40:00", {**PC, "CDP_TRAVA_ID": tid},
                         ag=MONTAR, adquirir=True)
    assert code == ro.EXIT_EXECUTAR and out["trava"]["id"] == tid and out["trava"]["reentrada"]
    # tarefas compartilhadas não disputam a trava no gate
    risco = _ag()
    code, out = _avaliar(b, "cdp-risco-1330", "2026-10-12T13:31:00", PC, ag=risco,
                         adquirir=True)
    assert code == ro.EXIT_EXECUTAR and out["trava"] is None


def test_rehearsal_never_pushes_and_never_touches_the_lock(dois_clones):
    from cdp import executor as ex

    a, _ = dois_clones
    code, out = _avaliar(a, "cdp-diario", "2026-10-12T19:25:00", {"CDP_ENSAIO": "1"},
                         adquirir=True)
    assert code == ro.EXIT_EXECUTAR and out["ensaio_protecao"]["instalado"]
    (a / "x.txt").write_text("x")
    _git(a, "add", "x.txt")
    _git(a, "commit", "-qm", "ensaio")
    import os

    r = subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=a, capture_output=True,
                       text=True, check=False, env={**os.environ, "CDP_ENSAIO": "1"})
    assert r.returncode != 0 and "ensaio" in r.stderr
    # fora do ambiente de ensaio o gancho é inerte (um --ensaio local não trava o clone real)
    sem = {k: v for k, v in os.environ.items() if k != "CDP_ENSAIO"}
    r = subprocess.run(["git", "push", "-q", "--dry-run", "origin", "HEAD:main"], cwd=a,
                       capture_output=True, text=True, check=False, env=sem)
    assert r.returncode == 0, r.stderr
    # `rotinas conferir` (avaliação interna "em ensaio") nunca instala nada
    (a / ".git/hooks/pre-push").unlink()
    _avaliar(a, "cdp-diario", "2026-10-12T19:25:00", PC, registrar=False, ensaio=True)
    assert not (a / ".git/hooks/pre-push").exists()
    ens = {"CDP_ENSAIO": "1", **PC}
    assert ex.trava_adquirir(a, ROT.tarefa("cdp-diario"), env=ens)["estado"] == "ensaio"
    assert ex.trava_liberar(a, "x", env=ens)["estado"] == "ensaio"
    assert ex.trava_ler(a)[0] is None  # ramo cdp-trava nunca criado


def test_mind_comes_only_from_cdp_harness(raiz):
    (raiz / ".cdp").mkdir()
    (raiz / ".cdp/local.yaml").write_text("executor: local-pc\nharness: claude-code\n")
    code, out = _avaliar(raiz, "cdp-status", "2026-10-12T08:31:00", {})
    assert code == ro.EXIT_EXECUTAR and out["mente"] is None and out["harness"] is None
    code, out = _avaliar(raiz, "cdp-status", "2026-10-12T08:31:00", {"CDP_HARNESS": "codex"})
    assert out["mente"] == "codex"
    assert ro.mente_do_harness("antigravity") == "gemini" and ro.mente_do_harness("") is None


def test_shared_tasks_only_write_mergeable_paths(tmp_path):
    r = ROT.tarefa("cdp-risco-1330")
    assert r.caminhos == ("reports/risk",) and r.espera_trava_min > 0
    assert r.caminhos_exclusivos == ("book/KILL_SWITCH", "book/audit_log.jsonl")
    assert ROT.tarefa("cdp-risco-1603").caminhos_exclusivos == r.caminhos_exclusivos
    assert "docs/cdp/notas" not in ro.CAMINHOS_DO_LIVRO
    assert not any(c.startswith("docs/") for t in ROT.tarefas.values() for c in t.caminhos)
    rot = ro.carregar(_yaml(tmp_path, {
        "cdp-x": {**BASE, "concorrencia": "compartilhada", "caminhos": ["book"]},
        "cdp-y": {**BASE, "skill": "cdp-y", "hora": "20:22", "cron": "22 20 * * 1",
                  "cron_utc": "22 23 * * 1", "caminhos_exclusivos": ["book/KILL_SWITCH"]}}))
    probs = " ".join(ro.verificar(rot, ROOT))
    assert "cdp-x: tarefa compartilhada com caminho não mesclável: book" in probs
    assert "cdp-y: caminhos_exclusivos só valem para tarefas compartilhadas" in probs


def test_skills_carry_the_executor_exception_and_lock_ids():
    sem = ro.gerar_skills(ROT)[".agents/skills/cdp-semanal/SKILL.md"]
    assert "Exceção: se o prompt da rotina disser que a agenda" in sem
    assert "nunca rode o gate duas vezes" in sem
    assert "--execucao <execucao> --trava <trava.id> --mente <mente>" in sem
    risco = ro.gerar_skills(ROT)[".agents/skills/cdp-risco/SKILL.md"]
    assert "--execucao <execucao> --mente <mente>" in risco and "--trava" not in risco
    assert "nome do seu harness" in risco
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "a agenda, a trava e a publicação são do executor" in agents


# ------------------------------------------------------------------- script de rotina


def _uv_falso(pasta: Path, registro: Path, gate_json: str, gate_rc: int = 0) -> None:
    import sys

    (pasta / "uv").write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{registro}"\n'
        f'if [ "$1 $2" = "run python" ] && [ "$3" != "-m" ]; then shift 2; exec "{sys.executable}" "$@"; fi\n'
        f'if [ "$4 $5 $6" = "cdp rotinas gate" ]; then echo \'{gate_json}\'; exit {gate_rc}; fi\n'
        'if [ "$4 $5" = "cdp sincronizar" ]; then echo \'{"acao": "seguir", "motivo": "em dia"}\'; exit 0; fi\n'
        'if [ "$4 $5" = "cdp publicar" ]; then echo \'{"motivo": "publicado em origin/main"}\'; exit 0; fi\n'
        'if [ "$4 $5 $6" = "cdp rotinas prompt" ]; then echo "prompt da rotina"; exit 0; fi\n'
        "exit 0\n")
    (pasta / "uv").chmod(0o755)


def _repo_runner(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "cdp_rotina.sh").write_bytes((ROOT / "scripts/cdp_rotina.sh").read_bytes())
    (repo / "scripts" / "cdp_rotina.sh").chmod(0o755)
    return repo


def test_runner_accepts_identity_names_and_defaults_codex_to_executor_mode(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    _uv_falso(fake, tmp_path / "uv.log", '{"motivo": "x"}', 10)
    repo = _repo_runner(tmp_path)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)}

    def seco(*args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(repo / "scripts/cdp_rotina.sh"), "cdp-status", *args,
                               "--seco"], env={**env, **extra}, capture_output=True, text=True,
                              timeout=60, check=False)

    for nome, esperado in (("claude-code", "claude"), ("antigravity", "agy"), ("codex", "codex"),
                           ("gemini", "gemini")):
        r = seco("--harness", nome)
        assert r.returncode == 0, r.stdout + r.stderr
        assert f"harness: {esperado}" in r.stdout
        assert ("publicacao: executor" if nome == "codex" else "publicacao: agente") in r.stdout
    r = seco(CDP_HARNESS="claude-code")
    assert r.returncode == 0 and "harness: claude" in r.stdout
    r = seco(CDP_HARNESS="antigravity")
    assert r.returncode == 0 and "harness: agy" in r.stdout
    assert seco("--harness", "marte").returncode == 2
    texto = (ROOT / "scripts/cdp_rotina.sh").read_text(encoding="utf-8")
    assert "--print-timeout" in texto
    assert "--print-timeout" in (ROOT / "scripts/cdp_rotina.ps1").read_text(encoding="utf-8-sig")


def test_runner_executor_mode_keeps_git_outside_the_mind(tmp_path):
    """Codex (sandbox sem escrita em .git): o script pega a trava, sincroniza, chama a mente
    com o prompt sem git, publica com a trava e a execução do gate e libera a trava."""
    fake = tmp_path / "bin"
    fake.mkdir()
    registro = tmp_path / "uv.log"
    gate = json.dumps({"executar": True, "motivo": "fechamento pendente", "grava": True,
                       "timeout_min": 150, "execucao": "E1", "trava": {"id": "T1"}})
    _uv_falso(fake, registro, gate)
    marca = tmp_path / "codex.args"
    (fake / "codex").write_text(f'#!/usr/bin/env bash\necho "$*" > "{marca}"\n')
    (fake / "codex").chmod(0o755)
    repo = _repo_runner(tmp_path)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)}
    r = subprocess.run([str(repo / "scripts/cdp_rotina.sh"), "cdp-diario", "--harness", "codex"],
                       env=env, capture_output=True, text=True, timeout=120, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    chamadas = registro.read_text().splitlines()

    def idx(trecho: str) -> int:
        return next(i for i, c in enumerate(chamadas) if trecho in c)

    assert idx("rotinas gate --tarefa cdp-diario --adquirir") < idx("sincronizar --executar") \
        < idx("rotinas prompt --tarefa cdp-diario --harness codex --modo neutro "
              "--publicacao executor") < idx("cdp publicar") < idx("trava liberar --id T1")
    pub = chamadas[idx("cdp publicar")]
    assert "--trava T1" in pub and "--execucao E1" in pub
    assert marca.exists() and "workspace-write" in marca.read_text()
    assert not any("--previa" in c for c in chamadas)


def test_coverage_cadence_rides_on_the_existing_routines():
    """A cadência dos modelos da cobertura não cria tarefa nova: a montagem atualiza os modelos
    antes da coleta, o fechamento roda os retratos parciais e completos e a revisão mensal, e a
    rotina de notas só escreve notas (nunca roda o motor da cobertura)."""
    assert set(ROT.tarefas) >= {"cdp-semanal", "cdp-diario", "cdp-cobertura"}
    for tid in ("cdp-semanal", "cdp-diario"):
        t = ROT.tarefa(tid)
        assert t.exclusiva and {"book", "data/publico"} <= set(t.caminhos), tid
    cob = ROT.tarefa("cdp-cobertura")
    assert "data/publico" not in cob.caminhos and "book" not in cob.caminhos
    notas = (ROOT / cob.playbook).read_text(encoding="utf-8")
    assert "cdp cobertura run" not in notas.replace("nunca roda `cdp cobertura run`", "")
    assert "cobertura" in ROT.tarefa("cdp-semanal").descricao
    assert "revisão mensal" in ROT.tarefa("cdp-diario").descricao
    assert "pós-resultado" in cob.descricao
    sem = (ROOT / ROT.tarefa("cdp-semanal").playbook).read_text(encoding="utf-8")
    i_cob = sem.index("uv run python -m cdp cobertura run --date AAAA-MM-DD")
    assert i_cob < sem.index("uv run python -m cdp weekly prepare --date AAAA-MM-DD")
    assert "cobertura.atualizar_antes_da_decisao" in sem and "cobertura.data_base_decisao" in sem
    dia = (ROOT / ROT.tarefa("cdp-diario").playbook).read_text(encoding="utf-8")
    ordem = [dia.index("uv run python -m cdp cobertura run --date AAAA-MM-DD --emissores IID_A,IID_B"),
             dia.index("uv run python -m cdp cobertura revisao-mensal preparar --date"),
             dia.index("uv run python -m cdp cobertura revisao-mensal validar --date"),
             dia.index("uv run python -m cdp cobertura revisao-mensal publicar --date"),
             dia.index("## 7. Integridade e painel")]
    assert ordem == sorted(ordem)
    for chave in ("cobertura.tipo", "cobertura.passo", "cobertura.revisao_mensal.pendente",
                  "cobertura.adiado_para_a_decisao", "COVERAGE_MONTHLY_REVIEW"):
        assert chave in dia, chave
    assert "cobertura.notas_pos_resultado" in notas


def test_coverage_cadence_gates():
    """Os gates existentes bastam: a etapa ``cobertura`` da montagem passa pelo gate semanal e o
    retrato pendente (parcial ou completo) pelo gate diário."""
    ctx = ro.ContextoGate(hoje=date(2026, 10, 16))
    sem = ro.avaliar_gate("semanal", {"semanal": {"acao": "montar", "etapa": "cobertura",
                                                  "motivo": "dia de montagem"}}, ctx)
    assert sem.executar and "etapa=cobertura" in sem.itens
    cob = {"snapshot_pendente": True, "data": date(2026, 10, 13), "tipo": "parcial",
           "emissores": ["BR_VALE"]}
    dia = ro.avaliar_gate("diario", {"fase": "operacao", "cobertura": cob}, ctx)
    assert dia.executar and "retrato da cobertura de 2026-10-13 pendente" in dia.itens
    adiado = {"snapshot_pendente": False, "adiado_para_a_decisao": date(2026, 10, 16)}
    assert not ro.avaliar_gate("diario", {"fase": "operacao", "cobertura": adiado}, ctx).executar
