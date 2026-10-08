"""DADOS SIMULADOS: revisão não autora do consumidor de componentes nativos.

Autoria p0_bancos_argentinos. Fluxo selecionar_pit -> preparar_emissor, sem alterar
manifesto ou participantes produzidos. Vermelho no V2; contrato esperado para revisão.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from cdp.cobertura.disponibilidade_demonstrativos import conferir
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import preparar_emissor
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.temporal import construir
from cdp.data.publico_fatos import selecionar_pit
from cdp.data.synthetic import make_synthetic_market

DAY = date(2026, 10, 8)
CUT = datetime(2026, 10, 8, 18, tzinfo=UTC)
VALID = "2026-10-08T12:00:00+00:00"


def construir_entrada(fonte, *, periodos=None, itens=("receita",)):
    md = make_synthetic_market(seed=7, as_of=DAY)
    md.fundamentals["market_cap_disponivel_desde"] = VALID
    md.fundamentals["preco_disponivel_desde"] = VALID
    params = carregar_parametros()
    val = copy.deepcopy(params.valuation)
    val["qualidade"]["demonstrativos_disponibilidade_metodo"] = "recepcao_observada"
    val["projecao"]["resultado_corte_metodo"] = "base_preco_conhecimento_explicitos"
    observado = replace(params, valuation=val)
    dados = coletar(md, DAY, list(md.universe.issuers.index), list(md.universe.lines.index), [])
    frame = dados.demonstrativos.copy(deep=True)
    frame["data_publicacao"] = None
    frame["disponibilidade_tipo"] = "recepcao_observada"
    frame["disponivel_desde"] = VALID
    currency = frame.loc[frame.issuer_id.eq("SIM003") & frame.item.eq("receita"), "currency"].iloc[-1]
    rows = []
    periodos = periodos or [("2025-01-01", "2025-06-30", 30),
                            ("2025-01-01", "2025-12-31", 100),
                            ("2026-01-01", "2026-06-30", 60)]
    for item in itens:
      for start, end, value in periodos:
        rows.append({"entidade": "SIM003", "item": item, "period_start": start,
            "period_end": end, "value": value, "currency": currency, "consolidado": True,
            "demonstrativo": "DRE" if item == "receita" else "DFC", "fonte": fonte, "url": "https://example.org/simulados",
            "documento": "DADOS SIMULADOS", "sha256": "0" * 64, "received_date": VALID,
            "version": 1, "semantica_fluxo": "receita_dre" if item == "receita" else None, "data_publicacao_primaria": None,
            "disponibilidade_tipo": "recepcao_observada", "disponivel_desde": VALID,
            "data_recebimento_documento": None, "nota": None})
    canonical = selecionar_pit(pd.DataFrame(rows), DAY, conhecimento_ate=CUT)
    canonical["issuer_id"] = "SIM003"
    frame = frame[~(frame.issuer_id.eq("SIM003") & frame.item.isin((*itens, "fcf") if "cfo" in itens else itens))].copy()
    frame = pd.concat([frame, canonical], ignore_index=True)
    capital = dados.capital_oficial.copy(deep=True)
    capital["disponivel_desde"] = VALID
    dados = replace(dados, demonstrativos=frame, capital_oficial=capital,
                    corte_temporal=construir(DAY, CUT))
    legacy_val = copy.deepcopy(val)
    legacy_val["qualidade"].pop("demonstrativos_disponibilidade_metodo")
    legacy_params = replace(params, valuation=legacy_val)
    return md, dados, observado, legacy_params, canonical


@pytest.mark.parametrize("fonte", ["CVM", "SEC", "RI"])
def test_fluxo_normal_com_intervalos_nativos_completos_deve_passar(fonte):
    md, dados, params, legacy_params, canonical = construir_entrada(fonte)
    pac = preparar_emissor(md, dados, params, "SIM003", DAY)
    legacy = preparar_emissor(md, dados, legacy_params, "SIM003", DAY)
    row = canonical[canonical.freq.eq("TTM") & canonical.period_end.eq(pd.Timestamp("2026-06-30"))].iloc[0]
    raw = json.JSONDecoder().raw_decode(row["nota"].split("componentes_fluxo=", 1)[1])[0]
    assert len(raw) == 3 and all("period_start" in c and "freq" not in c for c in raw)
    assert all(c["fonte"]["disponivel_desde"] == VALID for c in raw)
    assert pac["unidades"] == legacy["unidades"]
    assert {k: v for k, v in pac.items() if k.startswith("t.")} == {
        k: v for k, v in legacy.items() if k.startswith("t.")}
    assert pac["max_data_publicacao"] is None and pac["pit_ok"] is False
    assert conferir(pac)[0]


def test_intervalos_originais_dos_componentes_sao_preservados():
    md, dados, params, _, canonical = construir_entrada("RI")
    pac = preparar_emissor(md, dados, params, "SIM003", DAY)
    row = canonical[canonical.freq.eq("TTM") & canonical.period_end.eq(pd.Timestamp("2026-06-30"))].iloc[0]
    raw = json.JSONDecoder().raw_decode(row["nota"].split("componentes_fluxo=", 1)[1])[0]
    member = next(r for r in pac["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    assert [(c.get("period_start"), c["period_end"]) for c in member["componentes"]] == [
        (c["period_start"], c["period_end"]) for c in raw]


def _grupos_nativos(nota):
    grupos = []
    restante = nota
    while "componentes_fluxo=" in restante:
        restante = restante.split("componentes_fluxo=", 1)[1]
        grupo, tamanho = json.JSONDecoder().raw_decode(restante)
        grupos.append(grupo)
        restante = restante[tamanho:]
    return grupos


def test_ytd_para_quatro_qs_admite_cancelamento_legitimo():
    periodos = [("2025-01-01", "2025-03-31", 30), ("2025-01-01", "2025-06-30", 65),
                ("2025-01-01", "2025-09-30", 95), ("2025-01-01", "2025-12-31", 140),
                ("2026-01-01", "2026-03-31", 40), ("2026-01-01", "2026-06-30", 80)]
    md, dados, params, legacy_params, canonical = construir_entrada("CVM", periodos=periodos)
    pac = preparar_emissor(md, dados, params, "SIM003", DAY)
    legacy = preparar_emissor(md, dados, legacy_params, "SIM003", DAY)
    row = canonical[canonical.freq.eq("TTM") & canonical.period_end.eq(pd.Timestamp("2026-06-30"))].iloc[0]
    grupos = _grupos_nativos(row["nota"])
    por_intervalo = {}
    for c in grupos[0]:
        por_intervalo.setdefault((c["period_start"], c["period_end"]), set()).add(c["coeficiente"])
    assert any(sinais == {-1.0, 1.0} for sinais in por_intervalo.values())
    assert pac["t.receita"] == legacy["t.receita"] and pac["unidades"] == legacy["unidades"]
    assert conferir(pac)[0]


def test_derivado_nativo_preserva_ambos_grupos_cfo_capex():
    md, dados, params, _, canonical = construir_entrada("RI", itens=("cfo", "capex"))
    pac = preparar_emissor(md, dados, params, "SIM003", DAY)
    row = canonical[canonical.item.eq("fcf") & canonical.freq.eq("TTM")
                    & canonical.period_end.eq(pd.Timestamp("2026-06-30"))].iloc[0]
    grupos = _grupos_nativos(row["nota"])
    assert len(grupos) == 2 and {c["item"] for g in grupos for c in g} == {"cfo", "capex"}
    member = next(r for r in pac["disponibilidade_demonstrativos"] if r["uso"] == "t.fcf")
    assert {c["item"] for c in member["componentes"]} == {"cfo", "capex"}
