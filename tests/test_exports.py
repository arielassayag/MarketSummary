"""Testes para exportação e verificação estrita de aprovação."""

import tempfile

import pytest

from fechamento.contracts import WorkflowState
from fechamento.exports import export_artifacts
from fechamento.providers import DemoProvider
from fechamento.storage import Storage
from fechamento.workflow import WorkflowController


def test_export_blocked_without_approval() -> None:
    storage = Storage(":memory:")
    controller = WorkflowController(storage)
    ctx = controller.execute_flow("data/demo/normal", DemoProvider())

    assert ctx.run.state == WorkflowState.IN_REVIEW

    # Tentativa de exportar antes da aprovação deve lançar PermissionError
    with pytest.raises(PermissionError, match="Exportação estritamente bloqueada"):
        export_artifacts(ctx)


def test_export_success_after_approval() -> None:
    storage = Storage(":memory:")
    controller = WorkflowController(storage)
    ctx = controller.execute_flow("data/demo/normal", DemoProvider())

    ctx = controller.approve(ctx, approver="Estrategista")

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = export_artifacts(ctx, output_base_dir=tmpdir)
        assert paths["markdown"].exists()
        assert paths["html"].exists()
        assert paths["bundle"].exists()

        # Verificar aviso de dados simulados no Markdown
        with open(paths["markdown"], encoding="utf-8") as f:
            content = f.read()
            assert "DADOS SIMULADOS" in content
            assert ctx.run.approval_hash in content
