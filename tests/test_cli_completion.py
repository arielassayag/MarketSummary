"""Contrato de conclusão: geração, aprovação explícita de teste e exportação persistida."""
import argparse
import json
import shutil
from pathlib import Path

import pytest

from fechamento.__main__ import cmd_approve, cmd_export, cmd_run
from fechamento.contracts import WorkflowState
from fechamento.providers import DemoProvider
from fechamento.storage import Storage
from fechamento.workflow import WorkflowController


def prepared_run(tmp_path, monkeypatch):
    source = Path('data/demo/normal').resolve()
    target = tmp_path / 'data/demo/normal'
    shutil.copytree(source, target)
    monkeypatch.chdir(tmp_path)
    storage = Storage()
    ctx = WorkflowController(storage).execute_flow(target, DemoProvider())
    return storage, ctx, target


def test_cli_export_finishes_and_persists_state(tmp_path, monkeypatch):
    storage, ctx, _ = prepared_run(tmp_path, monkeypatch)
    args = argparse.Namespace(run_id=ctx.run.run_id, approver='TESTE AUTOMATIZADO', output_dir='outputs', scenario_dir=None)
    cmd_approve(args)
    cmd_export(args)
    assert storage.get_run(ctx.run.run_id).state == WorkflowState.EXPORTED
    output = Path('outputs') / ctx.run.run_id
    bundle = json.loads((output/'bundle.json').read_text())
    assert bundle['state'] == 'EXPORTED'
    assert (output/'comentario.html').stat().st_size > 0
    assert (output/'comentario.md').stat().st_size > 0


def test_cli_refuses_changed_data_at_approval(tmp_path, monkeypatch):
    _, ctx, target = prepared_run(tmp_path, monkeypatch)
    with (target/'quotes.csv').open('a') as f:
        f.write('\n')
    with pytest.raises(SystemExit):
        cmd_approve(argparse.Namespace(run_id=ctx.run.run_id, approver='TESTE', scenario_dir=None))


def test_cli_refuses_changed_data_at_export(tmp_path, monkeypatch):
    _, ctx, target = prepared_run(tmp_path, monkeypatch)
    args = argparse.Namespace(run_id=ctx.run.run_id, approver='TESTE', output_dir='outputs', scenario_dir=None)
    cmd_approve(args)
    with (target/'quotes.csv').open('a') as f:
        f.write('\n')
    with pytest.raises(SystemExit):
        cmd_export(args)
    assert not Path('outputs').exists()


def test_cli_tells_reader_that_generation_completed(tmp_path, monkeypatch, capsys):
    _, _, target = prepared_run(tmp_path, monkeypatch)
    cmd_run(argparse.Namespace(scenario_dir=str(target), provider='demo', model=None, allow_paid=False))
    assert 'Geração concluída' in capsys.readouterr().out
