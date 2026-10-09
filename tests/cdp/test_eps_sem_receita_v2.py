"""DADOS SIMULADOS: receita auxiliar não participa do contrato EPS V2."""

import io
import json
from decimal import Decimal

import pandas as pd
import pytest
import test_publico_eps_por_periodo as f

from cdp.cobertura.fontes import csv_canonico
from cdp.data import publico


@pytest.mark.parametrize("caso", ["ausente", "so_0y", "so_1y", "alias_moeda",
                                  "alias_bloco", "moeda_invalida", "valor_invalido", "bloco_invalido"])
def test_receita_auxiliar_nao_ativa_nem_invalida_eps_v2(tmp_path, caso):
    doc = f.documento()
    for cell in f.trend(doc):
        if caso == "ausente" or (caso == "so_0y" and cell["period"] != "0y") or (
            caso == "so_1y" and cell["period"] != "+1y"
        ):
            cell.pop("revenueEstimate")
        elif caso == "alias_moeda":
            cell["revenueEstimate"]["currency"] = cell["revenueEstimate"].pop("revenueCurrency")
        elif caso == "alias_bloco":
            cell["revenue_estimate"] = cell.pop("revenueEstimate")
        elif caso == "moeda_invalida":
            cell["revenueEstimate"]["revenueCurrency"] = "moeda_nao_contratada"
        elif caso == "valor_invalido":
            cell["revenueEstimate"]["avg"] = "valor_nao_contratado"
        elif caso == "bloco_invalido":
            cell["revenueEstimate"] = ["bloco_nao_contratado"]
    arq, reg, body = f.arquivo(tmp_path, f.corpo(doc))
    raw = json.loads(body, parse_float=Decimal)
    expected = {c["period"]: c["earningsEstimate"]["avg"]["raw"] for c in f.trend(raw)}
    parsed, _ = f.eps.ler_corpo(body, f.TICKER)
    assert set(parsed) == {"earnings_estimate"}
    frame = publico.consenso_publico([f.TICKER], f.DATA, root=tmp_path, offline=True,
        eps_por_periodo=True, conhecimento_ate=f.RECEBIDO)
    assert not frame.attrs["falhas"] and arq.ler(reg) == body
    row = pd.read_csv(io.StringIO(csv_canonico(frame))).iloc[0]
    pk = f.participante(row, tmp_path)
    assert pd.isna(row.receita_fy1) and pd.isna(row.receita_fy2) and pd.isna(row.moeda_receita)
    assert pk.v.get("g_receita_fy1") is None and pk.v.get("g_receita_fy2") is None
    for period, field in (("0y", "eps_fy1"), ("+1y", "eps_fy2")):
        assert Decimal(str(pk.v[field])) == expected[period]
    assert json.loads(row.eps_contexto)["schema"] == "cdp.yahoo.eps_por_periodo/v1"
