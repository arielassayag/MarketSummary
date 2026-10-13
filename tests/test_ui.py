"""Testes da interface gráfica Streamlit usando AppTest."""

import shutil
import urllib.request
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest


def test_streamlit_app_loads_and_has_tabs(tmp_path, monkeypatch) -> None:
    root = Path(__file__).parent.parent
    shutil.copy(root / "app.py", tmp_path / "app.py")
    shutil.copytree(root / "data", tmp_path / "data")
    monkeypatch.chdir(tmp_path)
    st.cache_resource.clear()

    def offline(*args, **kwargs):
        raise OSError("Teste offline: chamada externa recusada")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    app_path = tmp_path / "app.py"
    at = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not at.exception
    # Verifica que existem as abas principais
    assert len(at.tabs) >= 4
    tab_labels = [t.label for t in at.tabs]
    assert "1. Processo" in tab_labels
    assert "2. Executar" in tab_labels
    assert "3. Revisar" in tab_labels
    assert "4. Evidências" in tab_labels
    # Verifica presença do título
    assert len(at.title) >= 1
    assert "Fechamento" in at.title[0].value
