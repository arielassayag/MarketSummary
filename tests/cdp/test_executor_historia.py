"""F01: origens de rename e resoluções de merge em remotos locais descartáveis."""

import subprocess

import pytest
from test_executor import _RT, DIARIO, ENV_PC, _git
from test_executor import repos as repos  # noqa: F401

from cdp import executor as ex


def _historia(repos, case):
    remote, a, b = repos
    _git(a, "config", "diff.renames", "true")
    original = (a / "src/codigo.py").read_bytes()
    if case == "rename":
        _git(a, "mv", "src/codigo.py", "book/codigo.py")
        _git(a, "commit", "-qm", "CDP: rename simulado")
        assert not (a / "src/codigo.py").exists()
        assert (a / "book/codigo.py").read_bytes() == original
    else:
        ancestor = _git(a, "rev-parse", "HEAD")
        (b / "src/codigo.py").write_text("# DADOS SIMULADOS\nx = 2\n")
        _git(b, "commit", "-qam", "código remoto simulado")
        _git(b, "push", "-q", "origin", "main")
        remote_parent = _git(remote, "rev-parse", "main")
        _git(a, "fetch", "-q", "origin", "main")
        _git(a, "merge", "--no-ff", "--no-commit", "origin/main")
        # H é igual ao pai ancestral A neste arquivo, mas altera a versão remota R.
        (a / "src/codigo.py").write_bytes(original)
        (a / "book/merge.json").write_text('{"aviso":"DADOS SIMULADOS"}')
        _git(a, "add", "src/codigo.py", "book/merge.json")
        _git(a, "commit", "-qm", "CDP: resolução simulada")
        assert _git(a, "show", "-s", "--format=%P", "HEAD").split() == [ancestor, remote_parent]
        assert _git(a, "show", "HEAD:src/codigo.py") != _git(remote, "show", "main:src/codigo.py")
        assert _git(a, "show", "HEAD:src/codigo.py") == _git(a, "show", ancestor + ":src/codigo.py")
    return remote, a


@pytest.mark.parametrize("case", ["rename", "merge"])
@pytest.mark.parametrize("entry", ["publicar", "sincronizar"])
def test_f01_every_origin_and_merge_resolution_is_scoped(repos, case, entry):
    remote, a = _historia(repos, case)
    before = _git(remote, "rev-parse", "main")
    if entry == "sincronizar":
        output = ex.sincronizar(a, env=ENV_PC, executar=False)
        assert output["acao"] == "parar" and "src/codigo.py" in output["arquivos"], output
    else:
        lease = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
        try:
            code, output = ex.publicar(
                a, DIARIO, "CDP: história simulada", rt=_RT(), env=ENV_PC, trava=lease
            )
            assert code == ex.FORA_DO_ESCOPO and not output["push"], output
            assert "src/codigo.py" in output["arquivos"]
        finally:
            ex.trava_liberar(a, lease, env=ENV_PC)
    assert _git(remote, "rev-parse", "main") == before


def test_f01_remote_code_merge_remains_publishable(repos, monkeypatch):
    remote, a, b = repos
    (a / "book/local.json").write_text('{"aviso":"DADOS SIMULADOS"}')
    _git(a, "add", "book/local.json")
    _git(a, "commit", "-qm", "CDP: livro local simulado")
    (b / "src/codigo.py").write_text("# DADOS SIMULADOS\nx = 2\n")
    (b / "docs").mkdir()
    (b / "docs/atualizacao.md").write_text("DADOS SIMULADOS: documentação remota")
    _git(b, "add", "src/codigo.py", "docs/atualizacao.md")
    _git(b, "commit", "-qm", "código e documentação remotos")
    _git(b, "push", "-q", "origin", "main")
    remote_source = _git(remote, "show", "main:src/codigo.py")
    native = subprocess.run
    sync_requests = []

    def no_environment_sync(args, **kwargs):
        if args[:2] == ["uv", "sync"]:
            sync_requests.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        return native(args, **kwargs)

    # O merge Git é real; a fronteira de instalação é simulada, nunca instala/sincroniza.
    monkeypatch.setattr(ex.subprocess, "run", no_environment_sync)
    synchronized = ex.sincronizar(a, executar=True, env=ENV_PC)
    assert synchronized["acao"] == "pull" and synchronized["executado"], synchronized
    assert len(sync_requests) == 1
    assert _git(a, "show", "HEAD:src/codigo.py") == remote_source
    lease = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
    try:
        code, output = ex.publicar(
            a, DIARIO, "CDP: recuperação simulada", rt=_RT(), env=ENV_PC, trava=lease
        )
        assert code == ex.OK and output["push"], output
        assert _git(remote, "show", "main:src/codigo.py") == remote_source
        assert (
            _git(remote, "show", "main:docs/atualizacao.md")
            == "DADOS SIMULADOS: documentação remota"
        )
        assert _git(remote, "show", "main:book/local.json") == '{"aviso":"DADOS SIMULADOS"}'
    finally:
        ex.trava_liberar(a, lease, env=ENV_PC)


@pytest.mark.parametrize("entry", ["publicar", "sincronizar"])
def test_f01_unreadable_history_never_becomes_empty_inventory(repos, monkeypatch, entry):
    remote, a, _ = repos
    before = _git(remote, "rev-parse", "main")
    (a / "book/local.json").write_text('{"aviso":"DADOS SIMULADOS"}')
    _git(a, "add", "book/local.json")
    _git(a, "commit", "-qm", "CDP: livro local simulado")
    native = ex.git

    def unreadable_diff(args, root, **kwargs):
        if args[0] == "diff-tree":
            return subprocess.CompletedProcess(args, 1, "", "leitura interrompida simulada")
        return native(args, root, **kwargs)

    monkeypatch.setattr(ex, "git", unreadable_diff)
    if entry == "sincronizar":
        output = ex.sincronizar(a, env=ENV_PC, executar=True)
        assert output["acao"] == "seguir_sem_push" and not output["executado"], output
    else:
        lease = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
        try:
            code, output = ex.publicar(
                a, DIARIO, "CDP: falha simulada", rt=_RT(), env=ENV_PC, trava=lease
            )
            assert code == ex.SEM_PUSH and not output["push"] and output["commit"] is None, output
        finally:
            ex.trava_liberar(a, lease, env=ENV_PC)
    assert "leitura interrompida simulada" in output["motivo"]
    assert _git(remote, "rev-parse", "main") == before
