"""A pasta sem Git próprio nunca usa a trava do projeto pai; todos remotos são locais."""
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cdp import executor as ex
from cdp.rotinas import carregar

SOURCE = Path(__file__).resolve().parents[2]
TASK = carregar(SOURCE / 'configs/cdp/rotinas.yaml').tarefa('cdp-diario')
ENV = {'CDP_EXECUTOR': 'local-pc', 'CDP_HARNESS': 'codex'}


def cli(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def repos(tmp_path):
    remote = tmp_path / 'remote.git'
    cli(tmp_path, 'init', '--bare', '--quiet', str(remote))
    parent = tmp_path / 'parent'
    cli(tmp_path, 'init', '--quiet', str(parent))
    cli(parent, 'remote', 'add', 'origin', str(remote))
    return parent, remote


def test_non_repo_child_cannot_inherit_parent_remote_or_write_its_lock(tmp_path):
    parent, remote = repos(tmp_path)
    child = parent / 'temporary'
    child.mkdir()
    environment_before = dict(os.environ)
    # O Git sem a guarda realmente descobre o pai: regressão demonstrada somente em remoto local.
    assert cli(child, 'rev-parse', '--show-toplevel') == str(parent)
    before = cli(tmp_path, 'ls-remote', '--heads', str(remote))
    result = ex.trava_adquirir(child, TASK, agora=datetime.now(UTC), env=ENV)
    assert result['estado'] == 'indisponivel' and result['id'] is None
    assert cli(tmp_path, 'ls-remote', '--heads', str(remote)) == before == ''
    assert ex.git(['remote', 'get-url', 'origin'], child).returncode != 0
    assert dict(os.environ) == environment_before


def test_repo_root_still_acquires_and_releases_its_local_lock(tmp_path):
    parent, remote = repos(tmp_path)
    acquired = ex.trava_adquirir(parent, TASK, agora=datetime.now(UTC), env=ENV)
    assert acquired['estado'] == 'adquirida' and acquired['id']
    state, _, error = ex.trava_ler(parent, ENV)
    assert not error and state['id'] == acquired['id']
    released = ex.trava_liberar(parent, acquired['id'], env=ENV)
    assert released['estado'] == 'liberada'
    state, _, error = ex.trava_ler(parent, ENV)
    assert not error and state['estado'] == 'livre'
    assert 'refs/heads/cdp-trava' in cli(tmp_path, 'ls-remote', '--heads', str(remote))


def test_linked_worktree_root_is_valid_but_its_non_repo_child_is_rejected(tmp_path):
    parent, _ = repos(tmp_path)
    cli(parent, '-c', 'user.name=Teste CDP', '-c', 'user.email=teste@example.invalid',
        'commit', '--quiet', '--allow-empty', '-m', 'DADOS SIMULADOS')
    worktree = tmp_path / 'worktree'
    cli(parent, 'worktree', 'add', '--quiet', '--detach', str(worktree))
    assert ex.git_head(worktree) == cli(parent, 'rev-parse', 'HEAD')
    child = worktree / 'temporary'
    child.mkdir()
    assert ex.git_head(child) is None
