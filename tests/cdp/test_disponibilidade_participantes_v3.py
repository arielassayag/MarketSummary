"""DADOS SIMULADOS: autoria V3, usando fixture normal do revisor sem alterá-la.

construir_entrada e seus seis controles têm autoria p0_bancos_argentinos.
Os causais abaixo são de autoria revisao_bridge e mudam apenas metadados
de componentes na entrada consumida, antes do registro de participantes.
"""
import copy
import json
from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest
from test_g2_v2_fluxo_nativo_revisor import DAY, construir_entrada

from cdp.cobertura.disponibilidade_demonstrativos import conferir
from cdp.cobertura.insumos import preparar_emissor


def grupos(nota):
    out = []
    restante = nota
    while "componentes_fluxo=" in restante:
        restante = restante.split("componentes_fluxo=", 1)[1]
        grupo, fim = json.JSONDecoder().raw_decode(restante)
        out.append(grupo)
        restante = restante[fim:]
    return out


def entrada(itens=("receita",)):
    return construir_entrada("RI", itens=itens)


def pacote(ctx, dados=None):
    md, original, params, _, _ = ctx
    return preparar_emissor(md, dados if dados is not None else original, params, "SIM003", DAY)


def mudar(ctx, item, transformar):
    frame = ctx[1].demonstrativos.copy(deep=True)
    mask = frame.issuer_id.eq("SIM003") & frame.item.eq(item) & frame.freq.eq("TTM")
    mask &= pd.to_datetime(frame.period_end).eq(pd.Timestamp("2026-06-30"))
    assert mask.sum() == 1
    index = frame.index[mask][0]
    composicoes = grupos(frame.loc[index, "nota"])
    transformar(composicoes)
    frame.loc[index, "nota"] = "; ".join("componentes_fluxo=" + json.dumps(g, ensure_ascii=False)
                                         for g in composicoes)
    return replace(ctx[1], demonstrativos=frame)


def financeiros(pac):
    return {k: v for k, v in pac.items() if k.startswith("t.") or k in ("unidades", "historico", "serie_acoes")}


def test_semantica_intervalar_nativa_literal_sem_identidade_ou_frequencia_inventada():
    ctx = entrada()
    pac = pacote(ctx)
    row = ctx[4][ctx[4].item.eq("receita") & ctx[4].freq.eq("TTM")
                 & ctx[4].period_end.eq(pd.Timestamp("2026-06-30"))].iloc[0]
    raw = grupos(row.nota)[0]
    member = next(r for r in pac["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    keys = ("item", "period_start", "period_end", "valor", "coeficiente", "currency", "consolidado", "fonte")
    assert [{k: c[k] for k in keys} for c in member["componentes"]] == raw
    assert all(not {"freq", "issuer_id", "origem"} & set(c) for c in member["componentes"])
    assert all(c["contexto"]["issuer_id"] == "SIM003" for c in member["componentes"])
    esperado = Decimal("60") + Decimal("100") - Decimal("30")
    assert Decimal(str(row.value)) == esperado
    assert pac["max_data_publicacao"] is None and pac["pit_ok"] is False and conferir(pac)[0]


def test_ebitda_nativo_preserva_grupos_ebit_e_depreciacao():
    ctx = entrada(("ebit", "d_a"))
    pac = pacote(ctx)
    row = ctx[4][ctx[4].item.eq("ebitda") & ctx[4].freq.eq("TTM")
                 & ctx[4].period_end.eq(pd.Timestamp("2026-06-30"))].iloc[0]
    raw = grupos(row.nota)
    member = next(r for r in pac["disponibilidade_demonstrativos"] if r["uso"] == "t.ebitda")
    assert len(raw) == len(member["grupos_componentes"]) == 2
    assert {c["item"] for c in member["componentes"]} == {"ebit", "d_a"}
    assert Decimal(str(row.value)) == (Decimal("60") + Decimal("100") - Decimal("30")) * 2
    assert conferir(pac)[0]


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2026-10-08T18:00:00.000001+00:00"])
def test_fcf_capex_grupo_posterior_invalido_nao_some_no_agregado(bad):
    ctx = entrada(("cfo", "capex"))
    baseline = pacote(ctx)
    assert conferir(baseline)[0]

    def alterar(composicoes):
        assert len(composicoes) == 2 and composicoes[1][0]["item"] == "capex"
        composicoes[1][0]["fonte"]["disponivel_desde"] = bad

    changed = pacote(ctx, mudar(ctx, "fcf", alterar))
    assert financeiros(changed) == financeiros(baseline)
    member = next(r for r in changed["disponibilidade_demonstrativos"] if r["uso"] == "t.fcf")
    assert member["disponivel_desde"] == "2026-10-08T12:00:00+00:00"
    assert member["componentes"][3]["fonte"]["disponivel_desde"] == bad
    assert not conferir(changed)[0]


@pytest.mark.parametrize("field,bad", [("issuer_id", "SIM999"), ("origem", "oficial"),
    ("entidade", "outra_entidade"), ("period_start", ""), ("period_start", "2026-07-01"),
    ("period_end", "2026-09-30"), ("coeficiente", float("nan")), ("valor", True),
    ("currency", "brl"), ("consolidado", "True")])
def test_declaracao_incompativel_antes_do_registro_nao_e_sobrescrita(field, bad):
    ctx = entrada()
    baseline = pacote(ctx)
    changed = pacote(ctx, mudar(ctx, "receita", lambda g: g[0][0].update({field: bad})))
    assert financeiros(changed) == financeiros(baseline)
    assert not conferir(changed)[0]


def test_duplicata_da_mesma_operacao_nativa_recusada_antes_do_registro():
    ctx = entrada()
    baseline = pacote(ctx)
    changed = pacote(ctx, mudar(ctx, "receita", lambda g: g[0].append(copy.deepcopy(g[0][0]))))
    assert financeiros(changed) == financeiros(baseline)
    assert not conferir(changed)[0]


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2026-10-08T18:00:00.000001+00:00"])
def test_recibo_explicito_do_componente_nao_e_substituido_pelo_da_fonte(bad):
    ctx = entrada()
    baseline = pacote(ctx)
    changed = pacote(ctx, mudar(ctx, "receita", lambda g: g[0][0].update({"disponivel_desde": bad})))
    assert financeiros(changed) == financeiros(baseline)
    member = next(r for r in changed["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    assert member["componentes"][0]["disponivel_desde"] == bad
    assert member["componentes"][0]["fonte"]["disponivel_desde"] == "2026-10-08T12:00:00+00:00"
    assert not conferir(changed)[0]


@pytest.mark.parametrize("field,bad", [("valor", 999), ("coeficiente", -1), ("currency", "USD"),
    ("consolidado", False), ("period_start", "2026-02-01")])
def test_manifesto_vincula_semantica_intervalar_conservada(field, bad):
    pac = pacote(entrada())
    assert conferir(pac)[0]
    member = next(r for r in pac["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    member["componentes"][0][field] = bad
    assert not conferir(pac)[0]


def test_identidade_explicita_coerente_e_reutilizacao_entre_usos_validas():
    ctx = entrada()
    changed = pacote(ctx, mudar(ctx, "receita", lambda g: g[0][0].update(
        {"issuer_id": "SIM003", "origem": "demonstrativos", "entidade": "SIM003"})))
    assert conferir(changed)[0]
    assert len([r for r in changed["disponibilidade_demonstrativos"] if r.get("componentes")]) > 1


def test_marcador_no_texto_documental_nao_cria_grupo_adicional():
    ctx = entrada()
    changed = pacote(ctx, mudar(ctx, "receita", lambda g: g[0][0]["fonte"].update(
        {"documento": "DADOS SIMULADOS; componentes_fluxo=[] dentro do documento"})))
    member = next(r for r in changed["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    assert len(member["grupos_componentes"]) == 1 and conferir(changed)[0]
