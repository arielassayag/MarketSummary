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


def test_export_preserves_collector_limitations(tmp_path):
    import json
    import shutil

    package = tmp_path / 'package'
    shutil.copytree('data/demo/normal', package)
    manifest = json.loads((package/'manifest.json').read_text())
    manifest['data_notice'] = 'Cotações públicas com atraso; CARTEIRA SIMULADA de pesos iguais.'
    (package/'manifest.json').write_text(json.dumps(manifest))
    ctx = WorkflowController(Storage(':memory:')).execute_flow(package, DemoProvider())
    ctx = WorkflowController(ctx.storage).approve(ctx, approver='TESTE AUTOMATIZADO')
    paths = export_artifacts(ctx, tmp_path/'output')
    md = paths['markdown'].read_text()
    assert manifest['data_notice'] in md
    assert 'Todos os números, carteira e notícias' not in md
    assert 'CARTEIRA SIMULADA' in paths['html'].read_text()
    assert json.loads(paths['bundle'].read_text())['data_notice'] == manifest['data_notice']
