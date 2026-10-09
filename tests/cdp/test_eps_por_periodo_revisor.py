"""Contrastes independentes offline; corpo/recepções DADOS SIMULADOS.

Reutiliza somente preparo de Arquivo e recipientes da fixture portátil recebida.
As funções de produção/consumo são reais, sem path privado ou oráculo privado.
"""

import io
import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pandas as pd
import pytest
import test_publico_eps_por_periodo as f

from cdp.cobertura.fontes import csv_canonico
from cdp.data import publico
from cdp.data.publico_arquivo import ArquivoAdulterado


def produzir(root, *, cut=None):
    return publico.consenso_publico([f.TICKER], f.DATA, root=root, offline=True,
                                    eps_por_periodo=True, conhecimento_ate=cut or f.RECEBIDO)


def consumir(row, root):
    return f.participante(row, root)


def test_revisor_fisico_decimal_csv_e_fontes_separadas(tmp_path):
    _, _, body = f.arquivo(tmp_path)
    # Esperado do corpo antes do parser CDP; não usa a saída auditada como oráculo.
    raw = json.loads(body, parse_float=Decimal)
    cells = {c["period"]: c for c in f.trend(raw)}
    row = produzir(tmp_path).iloc[0]
    pk = consumir(row, tmp_path)
    for period, field in (("0y", "eps_fy1"), ("+1y", "eps_fy2")):
        assert Decimal(str(pk.v[field])) == cells[period]["earningsEstimate"]["avg"]["raw"]
    ctx = pk.fontes["eps_fy1"]["eps_contexto"]
    assert ctx["base_nominal_id"] is ctx["poder_aquisitivo_data"] is ctx["ponte_FY_12m_FX"] is None
    assert pk.fontes["consenso"]["sha256"] != pk.fontes["eps_fy1"]["sha256"]
    assert "eps_contexto" not in pk.fontes["consenso"]
    table = pd.read_csv(io.StringIO(csv_canonico(pd.DataFrame([row]))))
    assert consumir(table.iloc[0], tmp_path).v == pk.v


@pytest.mark.parametrize("posicao", [1, 2])
def test_revisor_currency_alias_nao_preenche_campo_ausente(tmp_path, posicao):
    doc = f.documento()
    cell = f.trend(doc)[posicao]["earningsEstimate"]
    cell.pop("earningsCurrency")
    cell["currency"] = "USD"  # campo não contratado; não empresta moeda
    f.arquivo(tmp_path, f.corpo(doc))
    row = produzir(tmp_path).iloc[0]
    context = f.eps.contexto_da_linha(row)
    period = f.trend(doc)[posicao]["period"]
    assert context["periodos"][period]["currency"] is None
    assert context["moeda_comum"] is None and pd.isna(row.moeda_estimativas)
    assert consumir(row, tmp_path).v.get("eps_fy1") is None
    assert consumir(row, tmp_path).v.get("eps_fy2") is None


@pytest.mark.parametrize("posicao", [1, 2])
def test_revisor_endDate_ausente_nao_ganha_exercicio(tmp_path, posicao):
    doc = f.documento()
    cell = f.trend(doc)[posicao]
    period = cell["period"]
    cell.pop("endDate")
    cell["end_date"] = "2030-12-31"  # alias não contratado não vira endDate
    f.arquivo(tmp_path, f.corpo(doc))
    row = produzir(tmp_path).iloc[0]
    assert f.eps.contexto_da_linha(row)["periodos"][period]["period_end"] is None
    assert consumir(row, tmp_path).fontes["eps_fy1"]["eps_contexto"]["ponte_FY_12m_FX"] is None


def test_revisor_ordem_dos_blocos_nao_troca_periodos(tmp_path):
    doc = f.documento()
    trend = f.trend(doc)
    trend[:] = [trend[2], trend[0], trend[1]]
    f.arquivo(tmp_path, f.corpo(doc))
    row = produzir(tmp_path).iloc[0]
    pk = consumir(row, tmp_path)
    assert Decimal(str(pk.v["eps_fy1"])) == Decimal("2.25")
    assert Decimal(str(pk.v["eps_fy2"])) == Decimal("2.75")
    c = pk.fontes["eps_fy1"]["eps_contexto"]
    assert c["periodos"]["+1y"]["ancora"].endswith("/0")
    assert c["periodos"]["0y"]["ancora"].endswith("/2")


@pytest.mark.parametrize("posicao", [1, 2])
def test_revisor_avg_fmt_nao_preenche_raw_ausente(tmp_path, posicao):
    doc = f.documento()
    avg = f.trend(doc)[posicao]["earningsEstimate"]["avg"]
    avg.pop("raw")
    avg["fmt"] = "999"
    f.arquivo(tmp_path, f.corpo(doc))
    row = produzir(tmp_path).iloc[0]
    field = "eps_fy1" if posicao == 1 else "eps_fy2"
    assert pd.isna(row[field]) and consumir(row, tmp_path).v.get(field) is None


@pytest.mark.parametrize("posicao", [1, 2])
def test_revisor_moeda_individual_explicitamente_divergente(tmp_path, posicao):
    doc = f.documento()
    f.trend(doc)[posicao]["earningsEstimate"]["earningsCurrency"] = "ARS"
    f.arquivo(tmp_path, f.corpo(doc))
    out = produzir(tmp_path)
    assert pd.isna(out.iloc[0].eps_fy1) and pd.isna(out.iloc[0].eps_fy2)
    assert any("divergem" in e for e in out.attrs["falhas"])


@pytest.mark.parametrize("fim", ["2026-12-31", "2025-12-31"])
def test_revisor_endDate_igual_ou_invertido_recusa(tmp_path, fim):
    doc = f.documento()
    f.trend(doc)[2]["endDate"] = fim
    f.arquivo(tmp_path, f.corpo(doc))
    out = produzir(tmp_path)
    assert pd.isna(out.iloc[0].eps_fy1)
    assert any("Encerramentos" in e for e in out.attrs["falhas"])


@pytest.mark.parametrize("periodo,campo,valor", [
    ("0y", "currency", "ARS"), ("+1y", "currency", "ARS"),
    ("0y", "period_end", "2026-11-30"), ("+1y", "period_end", "2027-11-30"),
    ("0y", "valor_raw_literal", "9"), ("+1y", "valor_raw_literal", "9"),
])
def test_revisor_metadados_nao_substituem_corpo(tmp_path, periodo, campo, valor):
    f.arquivo(tmp_path)
    row = produzir(tmp_path).iloc[0].copy()
    ctx = json.loads(row.eps_contexto)
    ctx["periodos"][periodo][campo] = valor
    row["eps_contexto"] = json.dumps(ctx)
    with pytest.raises(ValueError):
        consumir(row, tmp_path)


@pytest.mark.parametrize("campo,valor", [("ticker", "OUTRO"), ("sha256", "0" * 64),
                                         ("data_coleta", f.RECEBIDO.replace(tzinfo=None)),
                                         ("moeda_estimativas", "ARS")])
def test_revisor_linha_nativa_contraditoria(tmp_path, campo, valor):
    f.arquivo(tmp_path)
    row = produzir(tmp_path).iloc[0].copy()
    row[campo] = valor
    if campo == "ticker":
        # Fora do emissor, o consumidor não escolhe a linha: preserva ausência.
        # Não declarar defeito num campo que essa representação não consome.
        with pytest.raises(ValueError):
            f.eps.contexto_da_linha(row)
        pk = consumir(row, tmp_path)
        assert pk.v.get("eps_fy1") is None and pk.v.get("eps_fy2") is None
        return
    with pytest.raises(ValueError):
        consumir(row, tmp_path)


def test_revisor_corpo_fisico_alterado_recusa_mesmo_json(tmp_path):
    arq, reg, body = f.arquivo(tmp_path)
    row = produzir(tmp_path).iloc[0]
    (arq.base / reg.caminho).write_bytes(body + b" ")
    with pytest.raises((ValueError, ArquivoAdulterado)):
        consumir(row, tmp_path)


def test_revisor_recebimento_naive_e_cutoff_anterior_recusados(tmp_path):
    arq, reg, _ = f.arquivo(tmp_path)
    body = arq.ler(reg)
    with pytest.raises(ValueError):
        f.eps.consenso_do_registro(body, f.TICKER,
            replace(reg, data_coleta=f.RECEBIDO.replace(tzinfo=None)), conhecimento_ate=f.RECEBIDO)
    out = produzir(tmp_path, cut=f.RECEBIDO - timedelta(microseconds=1))
    assert pd.isna(out.iloc[0].eps_fy1) and "eps_contexto" not in out
    assert consumir(produzir(tmp_path).iloc[0], tmp_path).fontes["eps_fy1"]["eps_contexto"]["recebido_em"] == f.RECEBIDO.isoformat()


def test_revisor_ausencia_fisica_nao_aceita_metadados(tmp_path):
    f.arquivo(tmp_path)
    row = produzir(tmp_path).iloc[0]
    with pytest.raises(ValueError):
        consumir(row, tmp_path / "sem_arquivo")


def test_revisor_ticker_no_corpo_tem_de_ser_o_da_chave(tmp_path):
    doc = deepcopy(f.documento())
    doc["quoteSummary"]["result"][0]["quoteType"]["symbol"] = "OUTRO"
    f.arquivo(tmp_path, f.corpo(doc))
    out = produzir(tmp_path)
    assert pd.isna(out.iloc[0].eps_fy1)
    assert any("symbol" in e for e in out.attrs["falhas"])


def test_revisor_receitas_de_moedas_distintas_nao_ativam_crescimento(tmp_path):
    """V2 mantém EPS válido, mas não oferece receita, mesmo com moedas iguais."""
    for nome, moeda in (("positivo_ARS_ARS", "ARS"), ("negativo_ARS_USD", "USD")):
        doc = f.documento()
        f.trend(doc)[2]["revenueEstimate"]["revenueCurrency"] = moeda
        root = tmp_path / nome
        arq, reg, body = f.arquivo(root, f.corpo(doc))
        raw = json.loads(body, parse_float=Decimal)
        expected = {c["period"]: c["earningsEstimate"]["avg"]["raw"] for c in f.trend(raw)}
        row = produzir(root).iloc[0]
        pk = consumir(row, root)
        assert arq.ler(reg) == body
        assert pd.isna(row.receita_fy1) and pd.isna(row.receita_fy2) and pd.isna(row.moeda_receita)
        assert pk.v.get("g_receita_fy1") is None and pk.v.get("g_receita_fy2") is None
        for period, field in (("0y", "eps_fy1"), ("+1y", "eps_fy2")):
            assert Decimal(str(pk.v[field])) == expected[period]
