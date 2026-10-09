"""DADOS SIMULADOS: isolamento do relógio entre fixtures, sem rede/seed/motor.

Autoria não autora da interação AMPLA12. Helpers e API CDP importados normalmente.
PDFs Galicia são os bytes primários já usados pela fixture contratual existente.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest
from dimensoes_contabeis_fixtures import coletor as coletor_dimensoes
from dimensoes_contabeis_fixtures import selecionar, semestre
from galicia_fixture_observada import coletor as coletor_galicia

from cdp.data import publico_fatos


def clock_externo():
    return datetime(2026, 10, 9, 1, 0, 0, 654321, tzinfo=UTC)


@pytest.mark.parametrize("caso", ["valido", "parcial", "incomparavel"])
def test_selecionar_restaura_clock_externo_inclusive_na_excecao(monkeypatch, caso):
    monkeypatch.setattr(publico_fatos, "_agora_observado", clock_externo)
    rows = semestre()
    if caso == "parcial":
        rows[0]["politica_contabil_id"] = None
        with pytest.raises(ValueError):
            selecionar(rows)
    else:
        if caso == "incomparavel":
            rows[0]["politica_contabil_id"] = "OUTRA_DADOS_SIMULADOS"
        selecionar(rows)
    assert publico_fatos._agora_observado is clock_externo


def test_coletor_dimensoes_ja_preserva_clock_externo(monkeypatch):
    monkeypatch.setattr(publico_fatos, "_agora_observado", clock_externo)
    coletor_dimensoes(semestre())
    assert publico_fatos._agora_observado is clock_externo


def test_selecionar_precedente_preserva_coletor_galicia_sem_alterar_granularidade(monkeypatch):
    monkeypatch.setattr(publico_fatos, "_agora_observado", clock_externo)
    antes, _ = coletor_galicia(monkeypatch)
    assert not antes.empty
    selecionar(semestre())
    depois, _ = coletor_galicia(monkeypatch)
    pd.testing.assert_frame_equal(depois, antes)
    assert publico_fatos._agora_observado is clock_externo
