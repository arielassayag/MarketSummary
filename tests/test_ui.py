"""Testes da interface gráfica Streamlit usando AppTest."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_loads_and_has_tabs() -> None:
    app_path = Path(__file__).parent.parent / "app.py"
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
