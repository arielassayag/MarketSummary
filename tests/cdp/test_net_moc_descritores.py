"""DADOS SIMULADOS: custódia física sob orçamento finito de descritores."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from cdp.audit import AuditLog
from cdp.workflow.net_moc import NetUnverifiable, PhysicalSources


@pytest.mark.parametrize("ordem", [(0, 1, 2), (2, 1, 0), (1, 0, 2)])
def test_validacoes_sobrepostas_cabem_no_limite_sem_perder_custodia(tmp_path, ordem):
    """Duplicar descritores por contexto estoura o limite real deste subprocesso."""
    pytest.importorskip("resource")
    script = r'''
import os
import resource
import sys
from pathlib import Path
from cdp.audit import AuditLog
from cdp.workflow.net_moc import PhysicalSources

root = Path(sys.argv[1])
root.mkdir()
for i in range(50):
    (root / f"origem-{i}.txt").write_text("DADOS SIMULADOS\n")
audit = AuditLog(root / "audit_log.jsonl", somente_leitura=True)
_, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (128, hard))
contexts = []
try:
    for _ in range(3):
        contexts.append(PhysicalSources({"book": root}, audit))
    assert len(contexts[0].manifest()["files"]) == 50
    # Depois de fork, um novo contexto deve ter sua própria posição de leitura.
    if hasattr(os, "fork"):
        fd = contexts[0]._fds["book/origem-0.txt"]
        os.lseek(fd, 0, os.SEEK_SET)
        pid = os.fork()
        if pid == 0:
            child = PhysicalSources({"book": root}, audit)
            child.close()
            os._exit(0)
        _, status = os.waitpid(pid, 0)
        assert status == 0
        assert os.read(fd, 16) == b"DADOS SIMULADOS\n"
    remaining = set(range(3))
    for i in map(int, sys.argv[2:]):
        contexts[i].close()
        contexts[i].close()
        remaining.remove(i)
        for j in remaining:
            contexts[j].recheck()
    # Nenhum descritor do contexto encerrado fica retido no processo.
    held = [open(root / "origem-0.txt", "rb") for _ in range(100)]
    for stream in held:
        stream.close()
finally:
    for context in contexts:
        context.close()
'''
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "book"), *map(str, ordem)],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("alteracao", ["corpo", "substituicao", "link", "namespace"])
def test_contextos_sobrepostos_continuam_recusando_adulteracao(tmp_path, alteracao):
    root = tmp_path / "book"
    root.mkdir()
    path = root / "origem.txt"
    path.write_text("DADOS SIMULADOS\n")
    audit = AuditLog(root / "audit_log.jsonl", somente_leitura=True)
    outer = PhysicalSources({"book": root}, audit)
    inner = PhysicalSources({"book": root}, audit)
    try:
        if alteracao == "corpo":
            path.write_text("DADOS SIMULADOS adulterados\n")
        elif alteracao == "substituicao":
            path.unlink()
            path.write_text("DADOS SIMULADOS\n")
        elif alteracao == "link":
            target = tmp_path / "alvo.txt"
            target.write_text("DADOS SIMULADOS\n")
            path.unlink()
            path.symlink_to(target)
        else:
            (root / "extra.txt").write_text("DADOS SIMULADOS\n")
        for context in (inner, outer):
            with pytest.raises(NetUnverifiable):
                context.recheck()
    finally:
        inner.close()
        outer.close()


def test_falha_na_recebida_interna_nao_libera_custodia_externa(tmp_path):
    root = tmp_path / "book"
    root.mkdir()
    path = root / "origem.txt"
    path.write_text("DADOS SIMULADOS\n")
    audit = AuditLog(root / "audit_log.jsonl", somente_leitura=True)
    outer = PhysicalSources({"book": root}, audit)
    alias = tmp_path / "hardlink.txt"
    try:
        alias.hardlink_to(path)
        with pytest.raises(NetUnverifiable):
            PhysicalSources({"book": root}, audit)
        alias.unlink()
        outer.recheck()
    finally:
        alias.unlink(missing_ok=True)
        outer.close()


def test_contexto_interno_recebe_recibo_proprio_do_corpo_atual(tmp_path):
    root = tmp_path / "book"
    root.mkdir()
    path = root / "origem.txt"
    path.write_text("DADOS SIMULADOS anteriores\n")
    audit = AuditLog(root / "audit_log.jsonl", somente_leitura=True)
    outer = PhysicalSources({"book": root}, audit)
    inner = None
    try:
        path.write_text("DADOS SIMULADOS atuais\n")
        inner = PhysicalSources({"book": root}, audit)
        inner.recheck()
        with pytest.raises(NetUnverifiable):
            outer.recheck()
    finally:
        if inner is not None:
            inner.close()
        outer.close()
