"""Regressões do roteiro real do AI Notes #10, em ambiente isolado."""

import shutil
import urllib.request
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from fechamento.contracts import WorkflowState


def isolated_app(tmp_path, monkeypatch):
    st.cache_resource.clear()
    root = Path(__file__).resolve().parents[1]
    shutil.copy(root / "app.py", tmp_path / "app.py")
    shutil.copytree(root / "data", tmp_path / "data")
    (tmp_path / ".env").write_text('OPENROUTER_API_KEY="tutorial-test-key"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def offline(*args, **kwargs):
        raise OSError("Teste sem chamadas externas")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    return AppTest.from_file(str(tmp_path / "app.py")).run(timeout=30)


def test_first_render_reads_key_from_project_dotenv(tmp_path, monkeypatch):
    at = isolated_app(tmp_path, monkeypatch)
    assert not at.exception
    assert at.text_input(key="live_or_key_input").value == "tutorial-test-key"


def test_export_remains_completed_after_rerun(tmp_path, monkeypatch):
    at = isolated_app(tmp_path, monkeypatch)
    scenario = next(s for s in at.selectbox if s.label == "Cenário de Entrada:")
    scenario.select("Cenário Demo Normal (Sintético — Pregão 18/09/2026)")
    generation = next(r for r in at.radio if r.label == "Modo de Geração:")
    generation.set_value("DemoProvider (Determinístico e Offline — Recomendado)")
    at.run()
    at.button(key="btn_preset_exec").click().run()
    next(t for t in at.text_input if t.label == "Nome do Aprovador:").set_value("TESTE")
    next(b for b in at.button if "Aprovar Comentário" in b.label).click().run()
    next(b for b in at.button if "Exportar Artefatos" in b.label).click().run()
    at.run()
    assert not at.exception
    assert at.session_state.workflow_ctx.run.state == WorkflowState.EXPORTED
    assert not any("Aprovar Comentário" in b.label for b in at.button)
    assert any("Exportação concluída" in s.value for s in at.success)
