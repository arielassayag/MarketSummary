"""Testes para o orquestrador do fluxo e máquina de estados."""

import tempfile
from pathlib import Path

from fechamento.contracts import WorkflowState
from fechamento.providers import DemoProvider
from fechamento.storage import Storage
from fechamento.workflow import WorkflowController


def test_workflow_normal_execution() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = Storage(db_path)
        controller = WorkflowController(storage)

        ctx = controller.execute_flow("data/demo/normal", DemoProvider())
        assert ctx.run.state == WorkflowState.IN_REVIEW
        assert len(ctx.revisions) == 1
        assert ctx.latest_revision is not None
        assert ctx.latest_revision.revision_number == 1


def test_workflow_corrupted_blocked() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = Storage(db_path)
        controller = WorkflowController(storage)

        ctx = controller.execute_flow("data/demo/corrupted", DemoProvider())
        assert ctx.run.state == WorkflowState.BLOCKED
        assert ctx.run.blocking_reason is not None


def test_approval_and_invalidation_upon_edit() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = Storage(db_path)
        controller = WorkflowController(storage)

        ctx = controller.execute_flow("data/demo/normal", DemoProvider())
        assert ctx.run.state == WorkflowState.IN_REVIEW

        # Aprovação formal
        ctx = controller.approve(ctx, approver="Estrategista Chefe")
        assert ctx.run.state == WorkflowState.APPROVED
        assert ctx.run.approval_hash is not None

        # Edição posterior pelo revisor
        ctx = controller.edit_text(ctx, "Texto editado manualmente.", author="Revisor")
        # Deve revogar aprovação e retornar para IN_REVIEW
        assert ctx.run.state == WorkflowState.IN_REVIEW
        assert ctx.run.approval_hash is None
        assert ctx.latest_revision.revision_number == 2


def test_rejection_flow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = Storage(db_path)
        controller = WorkflowController(storage)

        ctx = controller.execute_flow("data/demo/normal", DemoProvider())
        ctx = controller.reject(ctx, reason="Falta de dados macroeconômicos", rejector="Gestor")
        assert ctx.run.state == WorkflowState.REJECTED
        assert "Falta de dados" in (ctx.run.blocking_reason or "")
