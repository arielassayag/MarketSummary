"""Escritor único em qualquer harness: identidade do ambiente, executor designado, trava
distribuída (ramo cdp-trava, compare-and-swap), sincronização e publicação.

Usa um remoto local (repositório nu) e dois clones; nada sai da máquina."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from cdp import executor as ex
from cdp.rotinas import carregar

ROOT = Path(__file__).resolve().parents[2]
ROT = carregar(ROOT / "configs" / "cdp" / "rotinas.yaml")
DIARIO = ROT.tarefa("cdp-diario")
RISCO = ROT.tarefa("cdp-risco-1330")
STATUS = ROT.tarefa("cdp-status")
ENV_PC = {"CDP_EXECUTOR": "local-pc", "CDP_HARNESS": "claude-code"}
T0 = datetime(2026, 10, 12, 22, 30, tzinfo=UTC)


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                       env={**os.environ, "LC_ALL": "C"})
    return r.stdout.strip()


def _clone(remoto: Path, destino: Path) -> Path:
    subprocess.run(["git", "clone", "-q", str(remoto), str(destino)], check=True,
                   capture_output=True)
    _git(destino, "config", "user.name", "Teste")
    _git(destino, "config", "user.email", "teste@example.com")
    _git(destino, "checkout", "-q", "-B", "main", "origin/main")
    return destino


def _executor_yaml(executor: str = "local-pc") -> str:
    return ("# cabeçalho de teste\n# segunda linha\n"
            + yaml.safe_dump({"versao": 1, "executor": executor, "harness": "claude-code",
                              "desde": "2026-10-06T19:00:00-03:00", "por": "Teste",
                              "motivo": "teste", "anterior": None}, sort_keys=False))


@pytest.fixture
def repos(tmp_path) -> tuple[Path, Path, Path]:
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remoto)], check=True)
    semente = tmp_path / "semente"
    semente.mkdir()
    _git(semente, "init", "-q", "-b", "main")
    _git(semente, "config", "user.name", "Teste")
    _git(semente, "config", "user.email", "teste@example.com")
    (semente / "configs/cdp").mkdir(parents=True)
    (semente / "configs/cdp/executor.yaml").write_text(_executor_yaml(), encoding="utf-8")
    (semente / "configs/cdp/rotinas.yaml").write_bytes(
        (ROOT / "configs/cdp/rotinas.yaml").read_bytes())
    (semente / "src").mkdir()
    (semente / "src/codigo.py").write_text("x = 1\n")
    (semente / "book").mkdir()
    (semente / "book/audit_log.jsonl").write_text("{}\n")
    (semente / ".gitignore").write_text(".cdp/\n")
    _git(semente, "add", "-A")
    _git(semente, "commit", "-q", "-m", "inicial")
    _git(semente, "remote", "add", "origin", str(remoto))
    _git(semente, "push", "-q", "origin", "main")
    a = _clone(remoto, tmp_path / "a")
    b = _clone(remoto, tmp_path / "b")
    return remoto, a, b


# ----------------------------------------------------------------------------- identidade


def test_identity_resolution_is_explicit(tmp_path):
    assert ex.identidade(tmp_path, {})["executor"] == "desconhecido"
    auto = ex.identidade(tmp_path, {"GITHUB_ACTIONS": "true", "CLAUDE_CODE_REMOTE": "true"})
    assert auto["executor"] == "desconhecido" and auto["ambiente_detectado"] == "github-actions"
    (tmp_path / ".cdp").mkdir()
    (tmp_path / ".cdp/local.yaml").write_text("executor: local-pc\nharness: codex\n")
    assert ex.identidade(tmp_path, {}) ["executor"] == "local-pc"
    # o harness do arquivo é só informativo: a mente que grava vem de CDP_HARNESS
    assert ex.identidade(tmp_path, {})["harness"] is None
    assert ex.identidade(tmp_path, {})["harness_registrado"] == "codex"
    assert ex.identidade(tmp_path, {"CDP_HARNESS": "gemini"})["harness"] == "gemini"
    env = ex.identidade(tmp_path, {"CDP_EXECUTOR": "claude-cloud", "CDP_HARNESS": "claude-code"})
    assert env["executor"] == "claude-cloud" and env["origem"] == "CDP_EXECUTOR"


@pytest.mark.parametrize(("designado", "env", "codigo"), [
    ("local-pc", ENV_PC, ex.OK),
    ("local-pc", {"CDP_EXECUTOR": "claude-cloud"}, ex.OUTRO_EXECUTOR),
    ("nenhum", ENV_PC, ex.PAUSADO),
    ("local-pc", {}, ex.IDENTIDADE_DESCONHECIDA),
])
def test_verify_codes(tmp_path, designado, env, codigo):
    (tmp_path / "configs/cdp").mkdir(parents=True)
    (tmp_path / "configs/cdp/executor.yaml").write_text(_executor_yaml(designado))
    code, info = ex.verificar(tmp_path, DIARIO, env=env)
    assert code == codigo and info["designado"] == designado
    assert ex.verificar(tmp_path, STATUS, env=env)[0] == ex.OK  # leitura sempre passa


def test_verify_invalid_file_and_remote_change(repos, tmp_path):
    _, a, b = repos
    (tmp_path / "configs/cdp").mkdir(parents=True)
    (tmp_path / "configs/cdp/executor.yaml").write_text("versao: 1\nexecutor: marte\n")
    assert ex.verificar(tmp_path, DIARIO, env=ENV_PC)[0] == ex.CONFIG
    # a designação muda em origin/main: o clone a ainda tem local-pc
    (b / "configs/cdp/executor.yaml").write_text(_executor_yaml("claude-cloud"))
    _git(b, "commit", "-qam", "CDP: executor → claude-cloud")
    _git(b, "push", "-q", "origin", "main")
    code, info = ex.verificar(a, DIARIO, env=ENV_PC, remoto=True)
    assert code == ex.MUDOU_NO_REMOTO and info["remoto"] == "claude-cloud"


def test_trailers_and_session_links():
    ident = {"executor": "claude-cloud", "harness": "claude-code"}
    tr = ex.trailers("cdp-diario", ident, "e1", {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_abc"})
    assert tr == ["CDP-Tarefa: cdp-diario", "CDP-Executor: claude-cloud",
                  "CDP-Harness: claude-code", "CDP-Execucao: e1",
                  "CDP-Sessao: https://claude.ai/code/session_abc"]
    gh = ex.sessao_url({"GITHUB_RUN_ID": "9", "GITHUB_REPOSITORY": "o/r"})
    assert gh == "https://github.com/o/r/actions/runs/9"


# ---------------------------------------------------------------------------------- trava


def test_lease_acquire_renew_release_and_takeover(repos):
    _, a, b = repos
    head_a = _git(a, "rev-parse", "HEAD")
    t1 = ex.trava_adquirir(a, DIARIO, agora=T0, env=ENV_PC)
    assert t1["estado"] == "adquirida"
    t2 = ex.trava_adquirir(b, DIARIO, agora=T0 + timedelta(minutes=5),
                           env={"CDP_EXECUTOR": "claude-cloud"})
    assert t2["estado"] == "ocupada_por_outro" and "cdp-diario em andamento" in t2["motivo"]
    assert ex.trava_renovar(b, "outro-id", agora=T0, env=ENV_PC)["estado"] == "perdida"
    r = ex.trava_renovar(a, t1["id"], ttl_min=90, agora=T0 + timedelta(minutes=30), env=ENV_PC)
    assert r["estado"] == "renovada"
    assert ex.trava_liberar(b, "outro-id", agora=T0, env=ENV_PC)["estado"] == "nao_detentor"
    assert ex.trava_liberar(a, t1["id"], agora=T0, env=ENV_PC)["estado"] == "liberada"
    estado, _, erro = ex.trava_ler(b)
    assert erro is None and estado["estado"] == "livre" and estado["ultima"]["tarefa"] == "cdp-diario"
    # trava abandonada: vence (TTL + folga) e a próxima execução assume
    t3 = ex.trava_adquirir(a, DIARIO, agora=T0, env=ENV_PC)
    tarde = T0 + timedelta(minutes=DIARIO.trava_ttl_min) + ex.FOLGA_RELOGIO + timedelta(seconds=1)
    assert ex.trava_adquirir(b, DIARIO, agora=tarde, env=ENV_PC)["estado"] == "adquirida"
    assert ex.trava_renovar(a, t3["id"], agora=tarde, env=ENV_PC)["estado"] == "perdida"
    # nenhuma mudança na árvore de trabalho nem no ramo atual
    assert _git(a, "status", "--porcelain") == "" and _git(a, "rev-parse", "HEAD") == head_a
    assert _git(a, "branch", "--show-current") == "main"


def test_lease_compare_and_swap_rejects_a_stale_writer(repos):
    _, a, b = repos
    assert ex.trava_adquirir(a, DIARIO, agora=T0, env=ENV_PC)["estado"] == "adquirida"
    estado_a, ponta_a, _ = ex.trava_ler(a)
    estado_b, ponta_b, _ = ex.trava_ler(b)
    assert ponta_a == ponta_b
    assert ex._trava_gravar(b, {**estado_b, "id": "b"}, ponta_b, "b")      # b ganha
    assert not ex._trava_gravar(a, {**estado_a, "id": "a"}, ponta_a, "a")  # a perde (CAS)
    assert ex.trava_ler(a)[0]["id"] == "b"


def test_lease_creation_race_has_one_winner(repos):
    _, a, b = repos
    novo = {"versao": 1, "estado": "ocupada", "id": "x", "expira": "2099-01-01T00:00:00+00:00"}
    assert ex._trava_gravar(a, novo, None, "a")
    assert not ex._trava_gravar(b, {**novo, "id": "y"}, None, "b")  # ramo já existe


def test_lease_unreachable_remote(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "remote", "add", "origin", str(tmp_path / "nao-existe.git"))
    out = ex.trava_adquirir(repo, DIARIO, agora=T0, env=ENV_PC)
    assert out["estado"] == "indisponivel" and out["id"] is None


# ----------------------------------------------------------------------------- sincronizar


def _commit(repo: Path, rel: str, texto: str, msg: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)
    _git(repo, "push", "-q", "origin", "HEAD:main")


def test_sync_classification(repos):
    _, a, b = repos
    assert ex.sincronizar(a, env=ENV_PC)["acao"] == "seguir"
    _commit(b, "src/novo.py", "y = 2\n", "código novo")
    s = ex.sincronizar(a, env=ENV_PC)
    assert s["acao"] == "pull" and s["arquivos"] == ["src/novo.py"]
    s = ex.sincronizar(a, executar=True, env=ENV_PC)
    assert s["executado"] and (a / "src/novo.py").exists()
    _commit(b, "reports/risk/2026-10-12/risco_1330.md", "x", "CDP: risco")
    assert ex.sincronizar(a, env=ENV_PC)["acao"] == "pull"  # arquivo novo de risco: mesclável
    ex.sincronizar(a, executar=True, env=ENV_PC)
    _commit(b, "book/audit_log.jsonl", "{}\n{}\n", "CDP: fechamento")
    s = ex.sincronizar(a, env=ENV_PC)
    assert s["acao"] == "parar" and "outra sessão gravou o livro" in s["motivo"]


def test_sync_stops_on_development_clones_and_reevaluates_executor(repos):
    _, a, b = repos
    (a / "src/codigo.py").write_text("x = 99\n")
    assert ex.sincronizar(a, env=ENV_PC)["acao"] == "parar"
    _git(a, "checkout", "--", "src/codigo.py")
    (a / "src/codigo.py").write_text("x = 3\n")
    _git(a, "commit", "-qam", "dev local")
    s = ex.sincronizar(a, env=ENV_PC)
    assert s["acao"] == "parar" and s["arquivos"] == ["src/codigo.py"]
    _git(a, "reset", "-q", "--hard", "origin/main")
    _commit(b, "configs/cdp/executor.yaml", _executor_yaml("claude-cloud"), "CDP: executor")
    assert ex.sincronizar(a, env=ENV_PC)["acao"] == "reavaliar"
    s = ex.sincronizar(a, executar=True, env=ENV_PC)
    assert s["acao"] == "parar" and "claude-cloud" in s["motivo"]


def test_sync_without_remote_continues_without_push(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "remote", "add", "origin", str(tmp_path / "nao-existe.git"))
    assert ex.sincronizar(repo, env=ENV_PC)["acao"] == "seguir_sem_push"


# ------------------------------------------------------------------------------- publicar


class _RT:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    def verify_all(self):
        return self.ok, ["livro: íntegro" if self.ok else "livro: cadeia quebrada"]


def test_publish_commits_only_task_paths_with_trailers_and_pushes_main(repos, monkeypatch):
    remoto, a, b = repos
    chamadas: list[list[str]] = []
    original = ex.git

    def espiao(args, raiz, **kw):
        chamadas.append(list(args))
        return original(args, raiz, **kw)

    monkeypatch.setattr(ex, "git", espiao)
    trava = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
    (a / "book/2026-10-12").mkdir(parents=True)
    (a / "book/2026-10-12/registro.json").write_text("{}")
    (a / "notas_soltas.txt").write_text("não entra")  # fora dos caminhos: nunca adicionado
    code, out = ex.publicar(a, DIARIO, "CDP: fechamento 2026-10-12", rt=_RT(), env=ENV_PC,
                            trava=trava)
    assert code == ex.OK and out["push"], out
    assert out["arquivos"] == ["book/2026-10-12/registro.json"]
    msg = _git(a, "log", "-1", "--format=%B")
    assert msg.startswith("CDP: fechamento 2026-10-12")
    for tr in ("CDP-Tarefa: cdp-diario", "CDP-Executor: local-pc", "CDP-Harness: claude-code",
               "CDP-Execucao: "):
        assert tr in msg
    assert _git(b, "ls-remote", "origin", "main").split()[0] == _git(a, "rev-parse", "HEAD")
    assert (a / "notas_soltas.txt").exists() and "notas_soltas.txt" in _git(a, "status",
                                                                            "--porcelain")
    pushes = [c for c in chamadas if c and c[0] == "push"]
    assert pushes and all("--force" not in c and "-f" not in c for c in pushes)
    assert any(c[-1] == "HEAD:refs/heads/main" for c in pushes)
    code, out = ex.publicar(a, DIARIO, "CDP: de novo", rt=_RT(), env=ENV_PC, trava=trava)
    assert code == ex.OK and out["motivo"] == "nada a publicar"


def test_publish_guards(repos):
    _, a, _ = repos
    (a / "book/x.json").write_text("{}")
    assert ex.publicar(a, DIARIO, "sem prefixo", rt=_RT(), env=ENV_PC)[0] == ex.CONFIG
    assert ex.publicar(a, STATUS, "CDP: x", rt=_RT(), env=ENV_PC)[0] == ex.CONFIG
    code, out = ex.publicar(a, DIARIO, "CDP: x", rt=_RT(), env={"CDP_ENSAIO": "1", **ENV_PC})
    assert code == ex.OK and out["commit"] is None and "ensaio" in out["motivo"]
    code, out = ex.publicar(a, DIARIO, "CDP: x", rt=_RT(), env={"CDP_EXECUTOR": "claude-cloud"})
    assert code == ex.OUTRO_EXECUTOR and out["commit"] is None
    # arquivo de código já preparado (staged) fora dos caminhos da tarefa: nada é publicado
    (a / "src/codigo.py").write_text("x = 7\n")
    _git(a, "add", "src/codigo.py")
    code, out = ex.publicar(a, DIARIO, "CDP: x", rt=_RT(), env=ENV_PC)
    assert code == ex.FORA_DO_ESCOPO and out["arquivos"] == ["src/codigo.py"]
    assert _git(a, "diff", "--cached", "--name-only") == "src/codigo.py"  # book/ devolvido
    _git(a, "reset", "-q", "HEAD", "src/codigo.py")
    _git(a, "checkout", "--", "src/codigo.py")
    # risco só publica os seus caminhos (book/x.json fica de fora)
    code, out = ex.publicar(a, RISCO, "CDP: risco", rt=_RT(), env=ENV_PC, sem_push=True)
    assert code == ex.OK and out["arquivos"] == [] and out["commit"] is None


def test_publish_with_broken_integrity_commits_locally_without_push(repos):
    _, a, b = repos
    trava = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
    (a / "book/y.json").write_text("{}")
    code, out = ex.publicar(a, DIARIO, "CDP: y", rt=_RT(ok=False), env=ENV_PC, trava=trava)
    assert code == ex.FALHA and out["commit"] and not out["push"]
    assert _git(b, "ls-remote", "origin", "main").split()[0] != out["commit"]


def test_publish_stops_when_the_remote_wrote_the_book(repos):
    _, a, b = repos
    _commit(b, "book/audit_log.jsonl", "{}\n{}\n", "CDP: outro escritor")
    trava = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
    (a / "book/z.json").write_text("{}")
    code, out = ex.publicar(a, DIARIO, "CDP: z", rt=_RT(), env=ENV_PC, trava=trava)
    assert code == ex.SEM_PUSH and not out["push"] and "outra sessão" in out["motivo"]


def test_token_is_never_persisted(repos):
    _, a, _ = repos
    (a / "book/t.json").write_text("{}")
    env = {**ENV_PC, "CDP_GIT_TOKEN": "segredo-de-teste-123"}
    ex.publicar(a, DIARIO, "CDP: t", rt=_RT(), env=env)
    assert "segredo-de-teste-123" not in (a / ".git" / "config").read_text()


# ------------------------------------------------------------------- registrar e transferir


def test_register_only_in_a_dedicated_main_clone(repos):
    _, a, _ = repos
    _git(a, "checkout", "-q", "-b", "dev")
    code, info = ex.registrar_local(a, "local-pc")
    assert code == ex.CONFIG and not (a / ".cdp/local.yaml").exists()
    _git(a, "checkout", "-q", "main")
    wt = a.parent / "wt"
    _git(a, "worktree", "add", "-q", "-b", "wtb", str(wt))
    assert ex.registrar_local(wt, "local-pc")[0] == ex.CONFIG
    code, info = ex.registrar_local(a, "local-pc", "codex")
    assert code == ex.OK
    assert yaml.safe_load((a / ".cdp/local.yaml").read_text())["executor"] == "local-pc"
    assert ex.identidade(a, {})["harness_registrado"] == "codex"


def test_transfer_rewrites_the_designation_with_history(repos):
    _, a, b = repos
    code, info = ex.transferir(a, "claude-cloud", "Pessoa", "rotinas na nuvem após o ensaio",
                               env=ENV_PC)
    assert code == ex.CONFIG and "dentro de uma rotina" in info["motivo"]
    assert ex.transferir(a, "claude-cloud", "Pessoa", "curto", env={})[0] == ex.CONFIG
    # trava ocupada por outra execução: recusa
    t = ex.trava_adquirir(b, DIARIO, agora=datetime.now(UTC), env=ENV_PC)
    assert ex.transferir(a, "claude-cloud", "Pessoa", "rotinas na nuvem após o ensaio",
                         env={})[0] == ex.CONFIG
    ex.trava_liberar(b, t["id"], env=ENV_PC)
    code, info = ex.transferir(a, "claude-cloud", "Pessoa", "rotinas na nuvem após o ensaio",
                               env={})
    assert code == ex.OK and info["de"] == "local-pc" and info["para"] == "claude-cloud"
    texto = (a / "configs/cdp/executor.yaml").read_text(encoding="utf-8")
    assert texto.startswith("# cabeçalho de teste\n# segunda linha\n")
    novo = ex.ler_executor(texto)
    assert novo["executor"] == "claude-cloud" and novo["anterior"]["executor"] == "local-pc"
    assert any("git push origin HEAD:main" in p for p in info["proximos_passos"])


def test_execution_records(tmp_path):
    ex.registrar_execucao(tmp_path, "e1", {"tarefa": "cdp-diario", "inicio": "2026-10-12T19:22"})
    ex.registrar_execucao(tmp_path, "e2", {"tarefa": "cdp-diario", "inicio": "2026-10-12T21:07"})
    ex.registrar_execucao(tmp_path, "e3", {"tarefa": "cdp-semanal", "inicio": "2026-10-12T23:00"})
    assert ex.ultima_execucao(tmp_path, "cdp-diario")[0] == "e2"
    assert ex.ler_execucao(tmp_path, "e3")["tarefa"] == "cdp-semanal"
    assert json.loads((tmp_path / ".cdp/execucoes/e1.json").read_text())["tarefa"] == "cdp-diario"


# ------------------------------------------------- trava na publicação e escopo por execução

SEMANAL = ROT.tarefa("cdp-semanal")


def _gate(repo: Path, tarefa, exec_id: str, trava: str | None = None) -> None:
    """O que `cdp rotinas gate` registra: o retrato dos caminhos no início da execução."""
    ex.registrar_execucao(repo, exec_id, {
        "tarefa": tarefa.id, "inicio": "2026-10-09T13:30:00-03:00", "trava": trava,
        "instantaneo": ex.estado_dos_caminhos(repo, (*tarefa.caminhos,
                                                     *tarefa.caminhos_exclusivos))})


def test_publish_refuses_an_exclusive_writer_without_the_lock(repos):
    _, a, b = repos
    (a / "book/w.json").write_text("{}")
    code, out = ex.publicar(a, DIARIO, "CDP: w", rt=_RT(), env=ENV_PC)
    assert code == ex.TRAVA_AUSENTE and out["commit"] is None and "sem a trava" in out["motivo"]
    outra = ex.trava_adquirir(b, DIARIO, env=ENV_PC)["id"]  # outra execução segura a trava
    code, out = ex.publicar(a, DIARIO, "CDP: w", rt=_RT(), env=ENV_PC, trava="id-antigo")
    assert code == ex.TRAVA_AUSENTE and out["commit"] is None
    assert _git(a, "status", "--porcelain") == "?? book/w.json"  # nada preparado nem gravado
    # a trava da execução também vem do registro do gate (ou de CDP_TRAVA_ID)
    _gate(a, DIARIO, "e-ok", trava=outra)
    (a / "book/w2.json").write_text("{}")
    code, out = ex.publicar(a, DIARIO, "CDP: w", rt=_RT(), env=ENV_PC, execucao="e-ok")
    assert code == ex.OK and out["push"] and out["arquivos"] == ["book/w.json", "book/w2.json"]
    assert out["anteriores"] == ["book/w.json"]  # a gravação recusada antes sai junto, com a trava
    # operador, explicitamente: sem trava
    (a / "book/v.json").write_text("{}")
    code, out = ex.publicar(a, DIARIO, "CDP: v", rt=_RT(), env=ENV_PC, sem_trava=True,
                            sem_push=True)
    assert code == ex.OK and out["commit"]


def test_risk_publishes_only_its_files_while_a_writer_holds_the_lock(repos):
    """Clone compartilhado (PC local): a semanal está no meio (trilha alterada, sem commit) e
    segura a trava; a rotina de risco liga o kill switch. Só o relatório de risco é publicado;
    o kill switch e a trilha ficam no clone (a semanal os publica)."""
    _, a, b = repos
    semanal = ex.trava_adquirir(b, SEMANAL, env=ENV_PC)["id"]
    (a / "book/audit_log.jsonl").write_text("{}\n{\"semanal\": 1}\n")  # semanal em andamento
    _gate(a, RISCO, "e-risco")
    (a / "reports/risk/2026-10-09").mkdir(parents=True)
    (a / "reports/risk/2026-10-09/risco_1330.md").write_text("risco")
    (a / "book/audit_log.jsonl").write_text("{}\n{\"semanal\": 1}\n{\"ks\": 1}\n")
    (a / "book/KILL_SWITCH").write_text("motivo")
    code, out = ex.publicar(a, RISCO, "CDP: risco 2026-10-09 13:30", rt=_RT(), env=ENV_PC,
                            execucao="e-risco", esperar_min=0)
    assert code == ex.PARCIAL and out["push"], out
    assert out["arquivos"] == ["reports/risk/2026-10-09/risco_1330.md"]
    assert out["retidos"] == ["book/KILL_SWITCH", "book/audit_log.jsonl"]
    assert _git(a, "show", "--name-only", "--format=", "HEAD") == \
        "reports/risk/2026-10-09/risco_1330.md"
    assert {tuple(x.split()) for x in _git(a, "status", "--porcelain").splitlines()} == {
        ("M", "book/audit_log.jsonl"), ("??", "book/KILL_SWITCH")}
    # trava livre: a própria publicação a adquire para o kill switch e a libera no fim
    ex.trava_liberar(b, semanal, env=ENV_PC)
    _gate(a, RISCO, "e-risco2")
    (a / "book/KILL_SWITCH").write_text("motivo 2")
    (a / "book/audit_log.jsonl").write_text("{}\n{\"ks\": 2}\n")
    code, out = ex.publicar(a, RISCO, "CDP: risco 16:03", rt=_RT(), env=ENV_PC,
                            execucao="e-risco2", esperar_min=0)
    assert code == ex.OK and out["push"] and out["trava_liberada"] == "liberada", out
    assert out["arquivos"] == ["book/KILL_SWITCH", "book/audit_log.jsonl"]
    assert ex.trava_ler(a)[0]["estado"] == "livre"


def test_shared_task_publishes_only_its_files_and_leftovers_of_its_new_files_folder(repos):
    """Tarefa compartilhada (risco): o que ESTA execução gravou e o que uma execução anterior da
    tarefa deixou na pasta só de arquivos novos (``reports/risk/``); a trilha alterada antes do
    gate (outra execução em andamento neste clone) fica para o escritor exclusivo."""
    _, a, _ = repos
    (a / "reports/risk/2026-10-08").mkdir(parents=True)
    (a / "reports/risk/2026-10-08/risco_1603.md").write_text("caiu antes de publicar")
    (a / "book/audit_log.jsonl").write_text("{}\n{\"semanal\": 1}\n")
    _gate(a, RISCO, "r1")
    (a / "reports/risk/2026-10-09").mkdir(parents=True)
    (a / "reports/risk/2026-10-09/risco_1330.md").write_text("risco")
    code, out = ex.publicar(a, RISCO, "CDP: risco", rt=_RT(), env=ENV_PC, execucao="r1",
                            esperar_min=0)
    assert code == ex.OK and out["push"], out
    assert out["arquivos"] == ["reports/risk/2026-10-08/risco_1603.md",
                               "reports/risk/2026-10-09/risco_1330.md"]
    assert out["anteriores"] == ["reports/risk/2026-10-08/risco_1603.md"]
    assert _git(a, "status", "--porcelain") == "M book/audit_log.jsonl"


def test_exclusive_writer_publishes_what_an_interrupted_run_left_in_the_clone(repos):
    """Clone persistente (PC): o fechamento grava o registro e a trilha e cai antes de publicar;
    o reforço retoma (a agenda lê o livro local) e publica tudo junto — senão a trilha publicada
    citaria um registro que não está no remoto."""
    _, a, _ = repos
    (a / "book/track_record").mkdir(parents=True)
    (a / "book/track_record/2026-10-13.json").write_text("{\"nav\": 1}\n")
    (a / "book/audit_log.jsonl").write_text("{}\n{\"DAILY_RECORD\": 1}\n")
    (a / "book/KILL_SWITCH").write_text("retido pelo risco")
    trava = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
    _gate(a, DIARIO, "reforco", trava=trava)
    (a / "reports/daily/2026-10-13").mkdir(parents=True)
    (a / "reports/daily/2026-10-13/relatorio.md").write_text("relatório")
    (a / "book/audit_log.jsonl").write_text("{}\n{\"DAILY_RECORD\": 1}\n{\"REPORT\": 1}\n")
    code, out = ex.publicar(a, DIARIO, "CDP: fechamento 2026-10-13", rt=_RT(), env=ENV_PC,
                            execucao="reforco")
    assert code == ex.OK and out["push"], out
    assert out["arquivos"] == ["book/KILL_SWITCH", "book/audit_log.jsonl",
                               "book/track_record/2026-10-13.json",
                               "reports/daily/2026-10-13/relatorio.md"]
    assert out["anteriores"] == ["book/KILL_SWITCH", "book/track_record/2026-10-13.json"]
    assert _git(a, "status", "--porcelain") == ""
    assert "Inclui 2 arquivo(s) gravado(s) por execução anterior" in _git(a, "log", "-1",
                                                                          "--format=%B")


def test_publish_reports_git_failures(repos):
    _, a, _ = repos
    trava = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
    (a / "book/q.json").write_text("{}")
    (a / ".git/index.lock").write_text("")  # outro git em andamento
    code, out = ex.publicar(a, DIARIO, "CDP: q", rt=_RT(), env=ENV_PC, trava=trava)
    assert code == ex.FALHA and out["motivo"].startswith("git add falhou") and not out["commit"]


def test_renewal_never_shortens_the_weekly_lock(repos):
    _, a, _ = repos
    t = ex.trava_adquirir(a, SEMANAL, agora=T0, env=ENV_PC)
    assert ex._dt(t["expira"]) == T0 + timedelta(minutes=60)
    r = ex.trava_renovar(a, t["id"], agora=T0 + timedelta(minutes=1), env=ENV_PC)
    assert ex._dt(r["expira"]) == T0 + timedelta(minutes=61)  # TTL da tarefa (60), não 45
    r = ex.trava_renovar(a, t["id"], ttl_min=5, agora=T0 + timedelta(minutes=2), env=ENV_PC)
    assert ex._dt(r["expira"]) == T0 + timedelta(minutes=61)  # nunca encolhe
    assert ex.ttl_da_tarefa(a, "cdp-semanal-b") == 60


def test_sync_merges_note_and_thesis_drafts_from_development(repos):
    _, a, b = repos
    _commit(b, "docs/cdp/notas/BR_VALE/2026-10-12.json", "{}", "rascunho de nota")
    _commit(b, "docs/cdp/teses/2026-10-16.json", "{}", "rascunho de tese")
    s = ex.sincronizar(a, executar=True, env=ENV_PC)
    assert s["acao"] == "pull" and s["executado"], s
    assert (a / "docs/cdp/notas/BR_VALE/2026-10-12.json").exists()


def test_delivery_package_roundtrip_and_refusals(repos, tmp_path):
    import io
    import tarfile

    _, a, b = repos
    (a / "book/2026-10-12").mkdir(parents=True)
    (a / "book/2026-10-12/registro.json").write_text('{"x": 1}')
    (a / "book/audit_log.jsonl").write_text("{}\n{}\n")
    (a / "src/codigo.py").write_text("x = 666\n")  # fora dos caminhos: nunca entra
    pacote = tmp_path / "entrega.tar"
    info = ex.entrega_exportar(a, DIARIO, pacote)
    assert info["arquivos"] == 2
    code, out = ex.entrega_importar(b, DIARIO, pacote)
    assert code == ex.OK and out["arquivos"] == 2, out
    assert (b / "book/2026-10-12/registro.json").read_text() == '{"x": 1}'
    assert (b / "src/codigo.py").read_text() == "x = 1\n"
    assert ex.entrega_importar(b, RISCO, pacote)[0] == ex.CONFIG  # outra tarefa

    def malicioso(nome: str, *, link: bool = False) -> Path:
        destino = tmp_path / f"mal_{abs(hash(nome))}.tar"
        man = json.dumps({"versao": 1, "tarefa": "cdp-diario", "apagados": []}).encode()
        with tarfile.open(destino, "w") as tar:
            ti = tarfile.TarInfo("manifesto.json")
            ti.size = len(man)
            tar.addfile(ti, io.BytesIO(man))
            ti = tarfile.TarInfo(nome)
            if link:
                ti.type, ti.linkname = tarfile.SYMTYPE, "/etc/passwd"
                tar.addfile(ti)
            else:
                ti.size = 2
                tar.addfile(ti, io.BytesIO(b"{}"))
        return destino

    for nome, link in (("arquivos/../src/codigo.py", False), ("arquivos/src/codigo.py", False),
                       ("arquivos/book/../../fora.txt", False), ("/etc/x", False),
                       ("arquivos/book/ln", True), ("arquivos/.git/hooks/pre-push", False)):
        code, out = ex.entrega_importar(b, DIARIO, malicioso(nome, link=link))
        assert code == ex.FORA_DO_ESCOPO, (nome, out)
    assert (b / "src/codigo.py").read_text() == "x = 1\n"
    assert not (b.parent / "fora.txt").exists()
