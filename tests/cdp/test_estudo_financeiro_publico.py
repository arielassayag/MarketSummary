"""DADOS SIMULADOS: regressões de grão/entidade do leitor documental público.

Porta os dois contraexemplos materiais V1 para a CI, sem novos casos financeiros.
Não há coleta, modelo CDP, preço, alvo, soma operacional ou certificado PIT.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def leitor():
    path = Path(__file__).parents[2] / "scripts/cdp/cdp_conferir_estudo_financeiro.py"
    spec = importlib.util.spec_from_file_location("leitor_estudo_publico", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def grao_ttm():
    entidade = {"CNPJ_CIA": "00.000.000/0001-00", "DENOM_CIA": "DADOS SIMULADOS A"}
    periods = [("atual", "2026-01-01", "2026-06-30", "ITR"),
               ("anual", "2025-01-01", "2025-12-31", "DFP"),
               ("anterior", "2025-01-01", "2025-06-30", "ITR")]
    rows, locators, sources = {}, {}, {}
    for role, start, end, kind in periods:
        rows[role] = {**entidade, "DT_INI_EXERC": start, "DT_FIM_EXERC": end,
            "DT_REFER": end, "VERSAO": "1", "ORDEM_EXERC": "ÚLTIMO",
            "GRUPO_DFP": "DF Consolidado - Demonstração do Fluxo de Caixa (Método Indireto)",
            "MOEDA": "REAL", "ESCALA_MOEDA": "MIL"}
        locators[role] = {"membro": f"{kind.lower()}_cia_aberta_DFC_MI_con_{end[:4]}.csv",
                          "SourceID": role}
        sources[role] = {"tipo": "ZIP",
            "url": f"https://dados.cvm.gov.br/dados/{kind}/DADOS/itr_simulados/{kind.lower()}_cia_aberta_{end[:4]}.zip"}
    evidence = {"mapeamento_issuer_CVM": {"natureza": "declaracao_curatorial_versionada",
        "versao": "DADOS SIMULADOS 1", "vinculos": {
            "BR_A": entidade,
            "BR_B": {"CNPJ_CIA": "00.000.000/0002-00", "DENOM_CIA": "DADOS SIMULADOS B"}}},
        "CVM_linhas": locators, "fontes": sources}
    account = {"issuer_id": "BR_A", "moeda": "BRL", "usar_modulo_nas_partes": True,
        "inicio": "2025-07-01", "fim": "2026-06-30", "tipo": "TTM", "frequencia": "TTM",
        "termos": [{"linhas": [role], "coeficiente": sign}
                   for role, sign in [("atual", "1"), ("anual", "1"), ("anterior", "-1")]]}
    return evidence, account, rows


def test_intervalo_ttm_derivado_nao_e_rotulo_livre(leitor, grao_ttm):
    evidence, account, rows = grao_ttm
    result = leitor.grao_composicao_cvm(evidence, account, rows)
    assert (result["inicio_derivado"], result["fim_derivado"], result["frequencia_derivada"]) == (
        "2025-07-01", "2026-06-30", "TTM")
    account["inicio"] = "2024-07-01"
    with pytest.raises(ValueError, match="Intervalo/tipo/frequência"):
        leitor.grao_composicao_cvm(evidence, account, rows)


def test_issuer_precisa_do_cnpj_e_nome_fisicos(leitor, grao_ttm):
    evidence, account, rows = grao_ttm
    account["issuer_id"] = "BR_B"
    with pytest.raises(ValueError, match="Issuer declarado diverge"):
        leitor.grao_composicao_cvm(evidence, account, rows)


def test_termo_anterior_nao_pode_repetir_o_exercicio(leitor, grao_ttm):
    evidence, account, rows = grao_ttm
    rows["anterior"].update(DT_FIM_EXERC="2025-12-31", DT_REFER="2025-12-31")
    with pytest.raises(ValueError, match="Períodos/origens/coeficientes"):
        leitor.grao_composicao_cvm(evidence, account, rows)


def test_sinal_do_exercicio_e_acumulado_anterior_nao_e_intercambiavel(leitor, grao_ttm):
    evidence, account, rows = grao_ttm
    account["termos"][1]["coeficiente"] = "-1"
    account["termos"][2]["coeficiente"] = "1"
    with pytest.raises(ValueError, match="Períodos/origens/coeficientes"):
        leitor.grao_composicao_cvm(evidence, account, rows)


def test_alias_coerente_continua_declaracao_curatorial_sem_pit(leitor, grao_ttm):
    evidence, account, rows = grao_ttm
    mapping = evidence["mapeamento_issuer_CVM"]["vinculos"]
    mapping["BR_ALIAS"] = copy.deepcopy(mapping["BR_A"])
    account["issuer_id"] = "BR_ALIAS"
    result = leitor.grao_composicao_cvm(evidence, account, rows)
    assert result["issuer_id_curatorial"] == "BR_ALIAS"
    assert result["CNPJ_documental"] == mapping["BR_A"]["CNPJ_CIA"]
    assert result["mapeamento_e_declaracao_versionada_nao_prova_PIT"] is True


def test_ordem_dos_termos_nao_altera_intervalo_fisico(leitor, grao_ttm):
    evidence, account, rows = grao_ttm
    original = leitor.grao_composicao_cvm(evidence, account, rows)
    account["termos"].reverse()
    reordered = leitor.grao_composicao_cvm(evidence, account, rows)
    for field in ("inicio_derivado", "fim_derivado", "tipo_derivado", "frequencia_derivada", "CNPJ_documental"):
        assert reordered[field] == original[field]
