"""F01/F02: DADOS SIMULADOS em clones/remotos locais e pacotes descartáveis."""

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest
from test_executor import _RT, DIARIO, ENV_PC, RISCO, _git
from test_executor import repos as repos  # noqa: F401

from cdp import executor as ex
from cdp.leitura_arquivos import ReceptorArquivos, ativar_receptor
from cdp.workflow.leitura_contratos import TentativaDeEfeitoLeitura


def _pending(a, *, rel="book/pendente.json"):
    lease = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
    path = a / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"aviso":"DADOS SIMULADOS"}')
    code, output = ex.publicar(
        a, DIARIO, "CDP: pendente simulado", rt=_RT(), env=ENV_PC, sem_push=True, trava=lease
    )
    assert code == ex.OK and output["commit"] and not output["push"]
    assert ex.trava_liberar(a, lease, env=ENV_PC)["estado"] == "liberada"
    assert _git(a, "status", "--porcelain") == ""
    return output["commit"]


def test_f01_pending_clean_tree_requires_lock(repos):
    remote, a, _ = repos
    before = _git(remote, "rev-parse", "main")
    _pending(a)
    code, output = ex.publicar(a, DIARIO, "CDP: retomada simulada", rt=_RT(), env=ENV_PC)
    assert code == ex.TRAVA_AUSENTE and not output["push"], output
    assert _git(remote, "rev-parse", "main") == before


def test_f01_shared_retry_cannot_send_exclusive_pending_without_owner(repos):
    remote, a, b = repos
    before = _git(remote, "rev-parse", "main")
    _pending(a)
    held = ex.trava_adquirir(b, DIARIO, env=ENV_PC)["id"]
    try:
        code, output = ex.publicar(
            a, RISCO, "CDP: risco simulado", rt=_RT(), env=ENV_PC, esperar_min=0
        )
        assert code == ex.TRAVA_AUSENTE and not output["push"], output
        assert _git(remote, "rev-parse", "main") == before
    finally:
        ex.trava_liberar(b, held, env=ENV_PC)


def test_f01_pending_is_published_with_confirmed_lock(repos):
    remote, a, _ = repos
    pending = _pending(a)
    lease = ex.trava_adquirir(a, DIARIO, env=ENV_PC)["id"]
    try:
        code, output = ex.publicar(
            a, DIARIO, "CDP: retomada com trava", rt=_RT(), env=ENV_PC, trava=lease
        )
        assert code == ex.OK and output["push"] and output["trava"] == lease, output
        assert _git(remote, "rev-parse", "main") == pending
    finally:
        ex.trava_liberar(a, lease, env=ENV_PC)


def test_f01_all_history_is_scoped_before_new_commit(repos):
    remote, a, _ = repos
    path = a / "src/temporario.py"
    path.write_text("# DADOS SIMULADOS\n")
    _git(a, "add", "src/temporario.py")
    _git(a, "commit", "-qm", "temporário local")
    path.unlink()
    _git(a, "add", "-A", "src/temporario.py")
    _git(a, "commit", "-qm", "remover temporário local")
    head = _git(a, "rev-parse", "HEAD")
    before = _git(remote, "rev-parse", "main")
    (a / "book/novo.json").write_text('{"aviso":"DADOS SIMULADOS"}')
    code, output = ex.publicar(
        a, DIARIO, "CDP: escopo simulado", rt=_RT(), env=ENV_PC, sem_trava=True
    )
    assert code == ex.FORA_DO_ESCOPO and not output["push"], output
    assert _git(a, "rev-parse", "HEAD") == head
    assert _git(remote, "rev-parse", "main") == before


def test_f01_retry_rechecks_new_pending_exclusive_commit(repos, monkeypatch):
    remote, a, _ = repos
    before = _git(remote, "rev-parse", "main")
    path = a / "reports/risk/risco.txt"
    path.parent.mkdir(parents=True)
    path.write_text("DADOS SIMULADOS")
    native = ex.git
    injected = False

    def refuse_then_change(args, root, **kwargs):
        nonlocal injected
        if args and args[0] == "push" and args[-1].endswith(":refs/heads/main") and not injected:
            injected = True
            (a / "book/tardio.json").write_text('{"aviso":"DADOS SIMULADOS"}')
            _git(a, "add", "book/tardio.json")
            _git(a, "commit", "-qm", "CDP: concorrência simulada")
            return subprocess.CompletedProcess(args, 1, "", "[rejected] non-fast-forward")
        return native(args, root, **kwargs)

    monkeypatch.setattr(ex, "git", refuse_then_change)
    code, output = ex.publicar(a, RISCO, "CDP: risco isolado", rt=_RT(), env=ENV_PC, esperar_min=0)
    assert code == ex.SEM_PUSH and not output["push"], output
    assert _git(remote, "rev-parse", "main") == before


def test_f01_push_sends_only_the_immutable_head_that_was_checked(repos, monkeypatch):
    remote, a, _ = repos
    path = a / "reports/risk/risco.txt"
    path.parent.mkdir(parents=True)
    path.write_text("DADOS SIMULADOS")
    native = ex.git
    injected = False

    def change_head_at_push(args, root, **kwargs):
        nonlocal injected
        if args and args[0] == "push" and args[-1].endswith(":refs/heads/main") and not injected:
            injected = True
            (a / "book/tardio.json").write_text('{"aviso":"DADOS SIMULADOS"}')
            _git(a, "add", "book/tardio.json")
            _git(a, "commit", "-qm", "CDP: concorrência simulada")
        return native(args, root, **kwargs)

    monkeypatch.setattr(ex, "git", change_head_at_push)
    code, output = ex.publicar(a, RISCO, "CDP: versão recebida", rt=_RT(), env=ENV_PC)
    assert code == ex.OK and output["push"] and injected, output
    assert _git(remote, "rev-parse", "main") == output["commit"]
    assert _git(remote, "rev-parse", "main") != _git(a, "rev-parse", "HEAD")
    assert _git(remote, "ls-tree", "--name-only", "main", "book/tardio.json") == ""


def _package(tmp_path, *, files=(), deleted=(), manifest_patch=None, extra=()):
    manifest = {
        "versao": 1,
        "tarefa": DIARIO.id,
        "head": None,
        "arquivos": [name for name, _ in files],
        "apagados": list(deleted),
    }
    if manifest_patch:
        manifest.update(manifest_patch)
    output = tmp_path / "entrega-dados-simulados.tar"
    with tarfile.open(output, "w") as archive:
        body = json.dumps(manifest).encode()
        member = tarfile.TarInfo("manifesto.json")
        member.size = len(body)
        archive.addfile(member, io.BytesIO(body))
        for name, data in [*files, *extra]:
            member = tarfile.TarInfo("arquivos/" + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return output


def _target(tmp_path):
    root = tmp_path / "clone-descartavel"
    (root / "book").mkdir(parents=True)
    return root


def test_f02_parent_symlink_deletion_is_refused(tmp_path):
    root = _target(tmp_path)
    outside = tmp_path / "fora"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("DADOS SIMULADOS: preservar")
    (root / "book/linked").symlink_to(outside, target_is_directory=True)
    package = _package(tmp_path, deleted=["book/linked/victim.txt"])
    code, _ = ex.entrega_importar(root, DIARIO, package)
    assert code == ex.FORA_DO_ESCOPO
    assert victim.read_text() == "DADOS SIMULADOS: preservar"


def test_f02_late_invalid_destination_does_not_modify_earlier_file(tmp_path):
    root = _target(tmp_path)
    earlier = root / "book/primeiro.txt"
    earlier.write_bytes(b"DADOS SIMULADOS: original")
    outside = tmp_path / "fora"
    outside.mkdir()
    (root / "book/linked").symlink_to(outside, target_is_directory=True)
    package = _package(
        tmp_path, files=[("book/primeiro.txt", b"novo"), ("book/linked/ultimo.txt", b"novo")]
    )
    code, _ = ex.entrega_importar(root, DIARIO, package)
    assert code == ex.FORA_DO_ESCOPO
    assert earlier.read_bytes() == b"DADOS SIMULADOS: original"
    assert not (outside / "ultimo.txt").exists()


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_write",
        "duplicate_delete",
        "write_delete",
        "undeclared",
        "bad_deleted_type",
        "traversal",
    ],
)
def test_f02_entire_package_validated_before_any_mutation(tmp_path, case):
    root = _target(tmp_path)
    target = root / "book/a.txt"
    target.write_bytes(b"DADOS SIMULADOS: original")
    kwargs = {"files": [("book/a.txt", b"novo")]}
    if case == "duplicate_write":
        kwargs["files"].append(("book/a.txt", b"outro"))
    elif case == "duplicate_delete":
        kwargs["deleted"] = ["book/z.txt", "book/z.txt"]
    elif case == "write_delete":
        kwargs["deleted"] = ["book/a.txt"]
    elif case == "undeclared":
        kwargs["extra"] = [("book/z.txt", b"sem declaracao")]
    elif case == "bad_deleted_type":
        kwargs["manifest_patch"] = {"apagados": "book/a.txt"}
    else:
        kwargs["deleted"] = ["book/../../fora.txt"]
    code, _ = ex.entrega_importar(root, DIARIO, _package(tmp_path, **kwargs))
    assert code in {ex.CONFIG, ex.FORA_DO_ESCOPO}
    assert target.read_bytes() == b"DADOS SIMULADOS: original"
    assert not (root / "book/z.txt").exists()


def test_f02_safe_roundtrip_preserves_literal_bytes_and_deletion(tmp_path):
    root = _target(tmp_path)
    (root / "book/apagar.txt").write_bytes(b"DADOS SIMULADOS")
    data = b"DADOS SIMULADOS\r\nlinha\x00final"
    code, output = ex.entrega_importar(
        root,
        DIARIO,
        _package(tmp_path, files=[("book/nova/arquivo.txt", data)], deleted=["book/apagar.txt"]),
    )
    assert code == ex.OK and output["arquivos"] == 1
    assert (root / "book/nova/arquivo.txt").read_bytes() == data
    assert not (root / "book/apagar.txt").exists()


@pytest.mark.parametrize("link", ["symbolic", "hard"])
def test_f02_write_never_changes_external_link_target(tmp_path, link):
    root = _target(tmp_path)
    outside = tmp_path / "externo.txt"
    outside.write_bytes(b"DADOS SIMULADOS: externo")
    target = root / "book/alvo.txt"
    if link == "symbolic":
        target.symlink_to(outside)
    else:
        os.link(outside, target)
    code, _ = ex.entrega_importar(
        root, DIARIO, _package(tmp_path, files=[("book/alvo.txt", b"novo")])
    )
    assert outside.read_bytes() == b"DADOS SIMULADOS: externo"
    if link == "symbolic":
        assert code == ex.FORA_DO_ESCOPO and target.is_symlink()
    else:
        assert code == ex.OK and target.read_bytes() == b"novo"


def test_f02_conflicting_file_and_child_are_refused_before_creation(tmp_path):
    root = _target(tmp_path)
    package = _package(
        tmp_path, files=[("book/alvo", b"DADOS SIMULADOS"), ("book/alvo/filho", b"novo")]
    )
    assert ex.entrega_importar(root, DIARIO, package)[0] == ex.FORA_DO_ESCOPO
    assert not (root / "book/alvo").exists()


def test_f02_parent_replacement_at_unlink_never_deletes_external_file(tmp_path, monkeypatch):
    root = _target(tmp_path)
    original_parent = root / "book/parent"
    original_parent.mkdir()
    (original_parent / "victim.txt").write_text("DADOS SIMULADOS: interno")
    outside = tmp_path / "fora"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("DADOS SIMULADOS: externo")
    native = os.unlink
    swapped = False

    def swap_before_unlink(path, **kwargs):
        nonlocal swapped
        if Path(path).name == "victim.txt" and not swapped:
            swapped = True
            original_parent.rename(root / "book/parent-original")
            original_parent.symlink_to(outside, target_is_directory=True)
        return native(path, **kwargs)

    monkeypatch.setattr(os, "unlink", swap_before_unlink)
    code, _ = ex.entrega_importar(
        root, DIARIO, _package(tmp_path, deleted=["book/parent/victim.txt"])
    )
    assert code in {ex.OK, ex.FORA_DO_ESCOPO}
    assert victim.read_text() == "DADOS SIMULADOS: externo"


def test_readonly_import_and_publish_refuse_before_effect(tmp_path):
    receiver = ReceptorArquivos({}, {})
    root = tmp_path / "nao_criado"
    with ativar_receptor(receiver):
        with pytest.raises(TentativaDeEfeitoLeitura):
            ex.entrega_importar(root, DIARIO, tmp_path / "inexistente.tar")
        with pytest.raises(TentativaDeEfeitoLeitura):
            ex.publicar(root, DIARIO, "CDP: proibido")
    assert not root.exists()
