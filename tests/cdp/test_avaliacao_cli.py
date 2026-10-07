"""Leitura CLI de um ciclo real do runtime, offline: DADOS SIMULADOS."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cdp.__main__ import build_parser
from cdp.config import load_config
from cdp.workflow.demo import run_demo
from cdp.workflow.runtime import Runtime


@pytest.fixture(scope="module")
def evaluated_cli(tmp_path_factory):
    root = tmp_path_factory.mktemp("avaliacao-cli")
    cfg = load_config(Path(__file__).parent / "fixtures/fund_legado.yaml")
    run_demo(root, days=6, cfg=cfg)
    return Runtime(cfg, root / "book", root / "market", root / "reports",
                   teses_root=None,
                   clock=lambda: datetime(2024, 3, 12, 23, tzinfo=UTC))


def _invoke(monkeypatch, capsys, rt, *argv):
    monkeypatch.setattr(Runtime, "from_args", staticmethod(lambda args: rt))
    args = build_parser().parse_args(["avaliacao", *argv])
    status = args.func(args)
    captured = capsys.readouterr()
    assert not captured.err
    return status, json.loads(captured.out)


def _hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_cli_reads_real_anchored_cohorts_without_writing(monkeypatch, capsys, evaluated_cli):
    rt = evaluated_cli
    before = _hashes(rt.book_root.parent)
    status, result = _invoke(monkeypatch, capsys, rt, "status")
    assert status == 0
    assert result["coortes"][0]["estado"] == "resolvida"
    status, result = _invoke(monkeypatch, capsys, rt, "ic", "--mind", "demo")
    assert status == 0 and result["historico"] == []
    status, result = _invoke(monkeypatch, capsys, rt, "ic", "--mind", "demo", "--simulados")
    assert status == 0 and result["historico"]
    assert "DADOS SIMULADOS" in result["dados"]
    assert result["fase_vigente"] == result["fase_recomendada"]
    assert result["brier"]["valor"] is None and result["brier"]["n"] == 0
    assert _hashes(rt.book_root.parent) == before


def test_cli_quant_keeps_absent_incremental_as_null(monkeypatch, capsys, evaluated_cli):
    status, result = _invoke(monkeypatch, capsys, evaluated_cli, "ic", "--mind", "demo",
                             "--canal", "quant", "--simulados")
    assert status == 0 and result["historico"]
    for row in result["historico"]:
        assert row["ic_ai"] is None and row["ic_incremental"] is None
        assert row["n_incremental"] == 0 and row["n_quant"] > 0
    status, result = _invoke(monkeypatch, capsys, evaluated_cli, "ic", "--mind", "codex", "--simulados")
    assert status == 0 and result["historico"] == []


def test_cli_refuses_changed_outcome(monkeypatch, capsys, evaluated_cli):
    rt = evaluated_cli
    path = rt.book_root / "2024-03-04/avaliacao/outcome.json"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b" ")
        monkeypatch.setattr(Runtime, "from_args", staticmethod(lambda args: rt))
        args = build_parser().parse_args(["avaliacao", "ic", "--mind", "demo", "--simulados"])
        assert args.func(args) == 1
        captured = capsys.readouterr()
        assert captured.out == "" and "não autenticada" in captured.err
    finally:
        path.write_bytes(original)
