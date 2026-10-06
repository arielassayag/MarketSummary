"""``cdp estado``: retrato só de leitura para qualquer agente — chaves, execuções lidas dos
trailers dos commits, incidentes determinísticos (SLAs), próximo passo e o texto em Markdown."""

from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cdp import estado as es
from cdp.__main__ import main
from cdp.config import load_config
from cdp.workflow.runtime import Runtime

ROOT = Path(__file__).resolve().parents[2]
BRT = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 10, 12, 23, 0, tzinfo=BRT)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                          env={**os.environ, "LC_ALL": "C"}).stdout.strip()


def _commit(repo: Path, rel: str, msg: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(msg)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


@pytest.fixture
def raiz(tmp_path) -> Path:
    r = tmp_path / "repo"
    (r / "configs/cdp").mkdir(parents=True)
    for n in ("executor.yaml", "rotinas.yaml", "site.yaml"):
        (r / "configs/cdp" / n).write_bytes((ROOT / "configs/cdp" / n).read_bytes())
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.name", "Teste")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "inicial")
    _commit(r, "book/2026-10-09/registro.json",
            "CDP: fechamento 2026-10-09\n\nCDP-Tarefa: cdp-diario\nCDP-Executor: local-pc\n"
            "CDP-Harness: claude-code\nCDP-Execucao: e1")
    _commit(r, "src/x.py", "CDP: melhoria de código (desenvolvimento)")
    _commit(r, "src/y.py", "CDP: risco 2026-10-12 13:30\n\nCDP-Tarefa: cdp-risco-1330\n"
                           "CDP-Executor: claude-cloud")
    return r


@pytest.fixture
def rt(tmp_path) -> Runtime:
    return Runtime(load_config(), tmp_path / "book", tmp_path / "market", tmp_path / "reports")


def _arvore(*pastas: Path) -> str:
    h = hashlib.sha256()
    for pasta in pastas:
        for p in sorted(pasta.rglob("*")):
            if p.is_file() and ".git" not in p.parts:
                h.update(p.as_posix().encode() + p.read_bytes())
    return h.hexdigest()


def test_last_runs_come_from_commit_trailers(raiz):
    from cdp.rotinas import carregar

    execs = es.ultimas_execucoes(raiz, carregar(raiz / "configs/cdp/rotinas.yaml"))
    assert [x["tarefa"] for x in execs] == ["cdp-risco-1330", "cdp-diario"]
    risco, diario = execs
    assert diario["executor"] == "local-pc" and diario["execucao"] == "e1"
    assert diario["fora_do_escopo"] == []
    assert risco["fora_do_escopo"] == ["src/y.py"]  # a rotina de risco não grava código


def test_estado_is_read_only_and_complete(raiz, rt, tmp_path):
    antes = _arvore(raiz, tmp_path)
    e = es.estado(rt, raiz, agora=AGORA, env={"CDP_EXECUTOR": "local-pc"})
    assert _arvore(raiz, tmp_path) == antes
    for chave in ("versao", "agora_brasilia", "fase", "data_de_inicio", "repositorio", "executor",
                  "trava", "integridade", "kill_switch", "ultimos_registros", "ultimas_execucoes",
                  "pendencias", "incidentes", "proximas_tarefas", "playbook_sugerido", "agenda"):
        assert chave in e, chave
    assert e["executor"]["designado"] == "local-pc" and e["executor"]["sou_o_executor"]
    assert e["repositorio"]["ramo"] == "main" and e["repositorio"]["origin_main"] is None
    assert e["integridade"]["ok"] is True
    codigos = {i["codigo"] for i in e["incidentes"]}
    assert "COMMIT_FORA_DO_ESCOPO" in codigos
    assert len(e["proximas_tarefas"]) == 6 and "vai_agir" in e["proximas_tarefas"][0]
    assert e["playbook_sugerido"]["playbook"].startswith("docs/cdp/playbooks/")
    md = es.para_markdown(e)
    for titulo in ("# CDP — estado da operação", "## Incidentes", "## Pendências",
                   "## Últimas execuções das rotinas", "## Próximas rotinas", "## Próximo passo"):
        assert titulo in md, titulo
    assert 15 <= len(md.splitlines()) <= 60
    for jargao in ("commit", "hash", "JSON"):
        assert jargao not in "\n".join(ln for ln in md.splitlines() if ln.startswith("#"))


def _ag(**kw) -> dict:
    base = {"fase": "operacao", "data_de_inicio": date(2026, 10, 9), "kill_switch": False,
            "reinicio": {"pendente": False}, "semanal": {}, "fechamentos_pendentes": [],
            "teses_pendentes": [], "relatorio_semanal": {}, "cobertura": {},
            "ultimo_registro_diario": date(2026, 10, 9), "pregao_b3_hoje": True}
    base.update(kw)
    return base


def _incs(ag: dict, agora: datetime = AGORA, **kw) -> dict[str, str]:
    args = {"integridade": {"ok": True}, "executor": {"designado": "local-pc"},
            "codigo_executor": 0, "trava": None, "execucoes": [], "repo": {},
            "raiz": Path("/nao-existe"), "reports_root": None}
    args.update(kw)
    return {i["codigo"]: i["severidade"] for i in es.incidentes(ag, agora=agora, **args)}


def test_incidents_table():
    assert _incs(_ag()) == {}
    assert _incs(_ag(kill_switch=True)) == {"KILL_SWITCH": "alta"}
    assert _incs(_ag(), integridade={"ok": False}) == {"INTEGRIDADE": "alta"}
    pend = _ag(reinicio={"pendente": True})
    assert _incs(pend, datetime(2026, 10, 7, 9, tzinfo=BRT)) == {"REINICIO_PENDENTE": "media"}
    assert _incs(pend) == {"REINICIO_PENDENTE": "alta"}
    atrasado = _ag(fechamentos_pendentes=[date(2026, 10, 12)])
    assert _incs(atrasado) == {"SLA_FECHAMENTO": "alta"}
    assert _incs(atrasado, datetime(2026, 10, 12, 21, 30, tzinfo=BRT)) == {}
    assert _incs(_ag(semanal={"decisao_perdida": True, "motivo": "x"})) == {
        "DECISAO_PERDIDA": "alta"}
    assert _incs(_ag(teses_pendentes=[date(2026, 10, 9)])) == {"SLA_TESE": "media"}
    assert _incs(_ag(relatorio_semanal={"pendente": True, "data": date(2026, 10, 9)})) == {
        "SLA_RELATORIO_SEMANAL": "media"}
    assert _incs(_ag(cobertura={"snapshot_pendente": True, "data": date(2026, 10, 8)})) == {
        "SLA_COBERTURA": "media"}
    assert _incs(_ag(), codigo_executor=2, executor={"motivo": "x"}) == {
        "EXECUTOR_INVALIDO": "alta"}
    assert _incs(_ag(), executor={"designado": "nenhum", "desde": "2026-10-10T10:00:00-03:00"}
                 ) == {"EXECUTOR_PAUSADO": "media"}
    assert _incs(_ag(), trava={"estado": "ocupada", "tarefa": "cdp-diario",
                               "expira": "2026-10-12T20:00:00-03:00"}) == {
        "TRAVA_EXPIRADA": "baixa"}
    assert _incs(_ag(), execucoes=[{"commit": "abc", "tarefa": "cdp-diario",
                                    "fora_do_escopo": ["src/x.py"]}]) == {
        "COMMIT_FORA_DO_ESCOPO": "alta"}
    assert _incs(_ag(), portal={"defasado": True}) == {"PORTAL_DEFASADO": "media"}


def test_risk_sla_needs_a_report_today(tmp_path):
    ag = _ag()
    tarde = datetime(2026, 10, 13, 17, 0, tzinfo=BRT)
    assert _incs(ag, tarde, reports_root=tmp_path) == {"SLA_RISCO": "baixa"}
    (tmp_path / "risk" / "2026-10-13").mkdir(parents=True)
    assert _incs(ag, tarde, reports_root=tmp_path) == {}


def test_cli_markdown_and_sla_exit_code(raiz, tmp_path, capsys):
    livro = tmp_path / "book"
    argv = ["--book", str(livro), "--market", str(tmp_path / "market"),
            "--reports", str(tmp_path / "reports"), "estado", "--raiz", str(raiz), "--rapido",
            "--formato", "md", "--agora", "2026-10-12T23:00:00"]
    assert main(argv + ["--sla"]) == 1  # commit fora do escopo é severidade alta
    assert "# CDP — estado da operação" in capsys.readouterr().out
    livro.mkdir(exist_ok=True)
    (livro / "KILL_SWITCH").write_text("teste")
    assert main(argv) == 0
    assert "Kill switch:** ligado" in capsys.readouterr().out


# ------------------------------------------------- pré-início, próximo passo, portal e nuvem


def test_pending_opening_hides_the_rehearsal_book():
    pend = _ag(reinicio={"pendente": True}, fechamentos_pendentes=[date(2026, 10, 6)],
               teses_pendentes=[date(2026, 10, 5)], semanal={"decisao_perdida": True},
               relatorio_semanal={"pendente": True, "data": date(2026, 10, 5)},
               cobertura={"snapshot_pendente": True, "data": date(2026, 10, 5)})
    assert _incs(pend, datetime(2026, 10, 7, 10, tzinfo=BRT)) == {"REINICIO_PENDENTE": "media"}
    assert _incs(pend, datetime(2026, 10, 9, 10, tzinfo=BRT)) == {"REINICIO_PENDENTE": "media"}
    assert _incs(pend, datetime(2026, 10, 9, 13, tzinfo=BRT)) == {"REINICIO_PENDENTE": "alta"}
    pendencias = es._pendencias(pend)
    assert [p["tipo"] for p in pendencias] == ["pre_inicio"]
    md = es.para_markdown({
        "agora_brasilia": "2026-10-07T10:00:00-03:00", "fase": "pre_inicio",
        "reinicio_pendente": True, "data_de_inicio": date(2026, 10, 9),
        "executor": {"designado": "local-pc", "este_ambiente": "local-pc"},
        "repositorio": {}, "avisos": [], "incidentes": [], "pendencias": pendencias,
        "ultimos_registros": {"nota": "livro anterior à data de início (ensaio)"},
        "proximas_tarefas": [], "playbook_sugerido": {}})
    assert ("**Fase:** pré-início (abertura do livro pendente; carteira inaugural em "
            "09/10/2026)") in md
    assert "Livro anterior à data de início (ensaio)." in md and "Fechamento" not in md


def test_suggested_playbook_follows_the_time_window():
    from cdp.rotinas import ContextoGate, carregar

    rot = carregar(ROOT / "configs/cdp/rotinas.yaml")
    pend = _ag(reinicio={"pendente": True})
    sou = {"sou_o_executor": True, "designado": "local-pc"}

    def sug(quando: datetime, ag: dict = pend, info: dict = sou) -> dict:
        return es.playbook_sugerido(rot, ag, ContextoGate(hoje=quando.date()), quando, info)

    s = sug(datetime(2026, 10, 9, 10, 0, tzinfo=BRT))  # dia de início, antes das 11:07
    assert s["tarefa"] == "cdp-semanal" and "sessão de operador: só a pedido" in s["condicao"]
    assert sug(datetime(2026, 10, 7, 20, 0, tzinfo=BRT))["tarefa"] == "cdp-diario"  # 21:07
    montar = _ag(semanal={"acao": "montar", "motivo": "dia de montagem"},
                 fechamentos_pendentes=[date(2026, 10, 15)])
    assert sug(datetime(2026, 10, 16, 11, 30, tzinfo=BRT), montar)["tarefa"] == "cdp-semanal"
    outro = sug(datetime(2026, 10, 9, 10, 0, tzinfo=BRT),
                info={"sou_o_executor": False, "designado": "claude-cloud"})
    assert "só no executor designado (claude-cloud)" in outro["condicao"]
    assert es.playbook_sugerido(rot, _ag(), ContextoGate(hoje=date(2026, 10, 13)),
                                datetime(2026, 10, 13, 9, tzinfo=BRT), sou) is None


def test_portal_staleness_only_counts_changes_that_rebuild_it(raiz):
    publicado = _git(raiz, "rev-parse", "HEAD")
    _commit(raiz, "src/cdp/novo.py", "código do CDP (remonta o portal)")
    _commit(raiz, "docs/cdp/QUALQUER.md", "docs: texto")
    _commit(raiz, "tests/test_x.py", "testes")
    ultimo = es.ultimo_commit_do_portal(raiz, "HEAD")
    assert ultimo == _git(raiz, "rev-parse", "HEAD~2")
    assert not es.portal_defasado(raiz, ultimo, ultimo)
    assert not es.portal_defasado(raiz, _git(raiz, "rev-parse", "HEAD"), ultimo)  # docs depois
    assert es.portal_defasado(raiz, publicado, ultimo)  # faltou a mudança de código
    assert es.portal_defasado(raiz, "f" * 40, ultimo)   # versão publicada desconhecida


def test_cloud_session_with_executor_identity_is_warned(raiz, rt):
    e = es.estado(rt, raiz, agora=AGORA, rapido=True,
                  env={"CDP_EXECUTOR": "local-pc", "CLAUDE_CODE_REMOTE": "true"})
    assert e["avisos"] and "ambiente Default" in e["avisos"][0]
    assert "**Atenção:**" in es.para_markdown(e)
    assert es.estado(rt, raiz, agora=AGORA, rapido=True,
                     env={"CDP_EXECUTOR": "local-pc"})["avisos"] == []
    assert e["mente"] is None
