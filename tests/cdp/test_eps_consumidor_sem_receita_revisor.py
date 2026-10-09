"""DADOS SIMULADOS. Controle não autor do contrato EPS-only no consumo real."""

import io

import pandas as pd
import pytest
import test_publico_eps_por_periodo as f

from cdp.cobertura.fontes import csv_canonico
from cdp.data.publico_eps import autenticar_linha


def test_produtor_eps_sem_receita_preserva_consumo(tmp_path):
    row = f.linha(tmp_path)
    assert pd.isna(row.receita_fy1) and pd.isna(row.receita_fy2)
    pk = f.participante(row, tmp_path)
    assert pk.v["eps_fy1"] == 2.25 and pk.v["eps_fy2"] == 2.75
    assert pk.v.get("g_receita_fy1") is None and pk.v.get("g_receita_fy2") is None


@pytest.mark.parametrize("serializar", [False, True])
@pytest.mark.parametrize("r1,r2", [(1000, 1100), (500, 600)])
def test_eps_autenticado_nao_ativa_receita_auxiliar_na_linha(tmp_path, serializar, r1, r2):
    row = f.linha(tmp_path)
    contexto = row.eps_contexto
    original = autenticar_linha(row, tmp_path)
    changed = row.copy()
    changed["receita_fy1"], changed["receita_fy2"], changed["moeda_receita"] = r1, r2, "ARS"
    if serializar:
        changed = pd.read_csv(io.StringIO(csv_canonico(pd.DataFrame([changed])))).iloc[0]
    assert changed.eps_contexto == contexto
    assert changed.eps_fy1 == row.eps_fy1 and changed.eps_fy2 == row.eps_fy2
    try:
        assert autenticar_linha(changed, tmp_path) == original
        pacote = f.participante(changed, tmp_path)
    except ValueError:
        return  # A recusa explícita também cumpre o contrato EPS-only.
    assert pacote.v.get("g_receita_fy1") is None
    assert pacote.v.get("g_receita_fy2") is None, "Receita fora do contrato EPS ativou crescimento financeiro"


def test_metadado_moeda_sem_receita_nao_ativa_formula(tmp_path):
    row = f.linha(tmp_path)
    row["moeda_receita"] = "ARS"
    try:
        pacote = f.participante(row, tmp_path)
    except ValueError:
        return
    assert pacote.v.get("g_receita_fy1") is None and pacote.v.get("g_receita_fy2") is None


def test_eps_adulterado_continua_recusado(tmp_path):
    row = f.linha(tmp_path)
    row["eps_fy2"] = 9
    with pytest.raises(ValueError):
        f.participante(row, tmp_path)
