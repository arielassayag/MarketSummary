"""DADOS SIMULADOS: controles não autores V3 sobre entradas efetivamente consumidas.

Autoria p0_bancos_argentinos. A fixture construir_entrada e os seis controles
nativos recebidos permanecem literais; este arquivo acrescenta controles próprios.
Não altera manifesto/participantes de saída para simular autoridade externa.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import timedelta

import pandas as pd
import pytest
from test_g2_v2_fluxo_nativo_revisor import CUT, DAY, VALID, construir_entrada

from cdp.cobertura.disponibilidade_demonstrativos import conferir
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import Demonstrativos, preparar_emissor
from cdp.cobertura.parametros import arquetipo_padrao
from cdp.cobertura.qualidade import portoes_emissor


def grupos(nota):
    restantes, lista = str(nota), []
    while "componentes_fluxo=" in restantes:
        restantes = restantes.partition("componentes_fluxo=")[2]
        parte, tamanho = json.JSONDecoder().raw_decode(restantes)
        lista.append(parte)
        restantes = restantes[tamanho:]
    return lista


def financeiros(pac):
    return {k: v for k, v in pac.items() if k.startswith("t.") or k in (
        "unidades", "historico", "serie_acoes", "receita_ano_anterior", "moeda_demonstrativos",
        "linha", "moeda", "fator_moeda")}


def preparar(ctx, *, dados=None, md=None, params=None):
    return preparar_emissor(md if md is not None else ctx[0], dados if dados is not None else ctx[1],
                           params if params is not None else ctx[2], "SIM003", DAY)


def estado(ctx, pac):
    return next(g["status"] for g in portoes_emissor(pac, {"tem_alvo": False, "metodos": []}, ctx[2])
                if g["codigo"] == "G2")


def editar_nativo(ctx, item, alterar, *, campo_explicito=False):
    frame = ctx[1].demonstrativos.copy(deep=True)
    mask = frame.issuer_id.eq("SIM003") & frame.item.eq(item) & frame.freq.eq("TTM")
    mask &= pd.to_datetime(frame.period_end).eq(pd.Timestamp("2026-06-30"))
    mask &= frame.nota.astype(str).str.contains("componentes_fluxo=", regex=False)
    assert mask.sum() == 1
    index = frame.index[mask][0]
    raw = grupos(frame.loc[index, "nota"])
    alterar(raw)
    if campo_explicito:
        if "componentes_fluxo" not in frame:
            frame["componentes_fluxo"] = None
        frame.at[index, "componentes_fluxo"] = json.dumps(raw[0], ensure_ascii=False)
    else:
        frame.at[index, "nota"] = "; ".join("componentes_fluxo=" + json.dumps(g, ensure_ascii=False) for g in raw)
    return replace(ctx[1], demonstrativos=frame)


@pytest.mark.parametrize("item,itens,segundo", [
    ("fcf", ("cfo", "capex"), "capex"), ("ebitda", ("ebit", "d_a"), "d_a")])
@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2026-10-08T18:00:00.000001Z"])
def test_segundo_grupo_nativo_participa_no_g2(item, itens, segundo, bad):
    ctx = construir_entrada("RI", itens=itens)
    before = preparar(ctx)
    assert estado(ctx, before) == "ok"

    def mudar(raw):
        assert len(raw) == 2 and raw[1][-1]["item"] == segundo
        raw[1][-1]["fonte"]["disponivel_desde"] = bad

    after = preparar(ctx, dados=editar_nativo(ctx, item, mudar))
    member = next(r for r in after["disponibilidade_demonstrativos"] if r["uso"] == f"t.{item}")
    assert member["disponivel_desde"] == VALID
    assert len(member["grupos_componentes"]) == 2
    assert member["componentes"][-1]["fonte"]["disponivel_desde"] == bad
    assert financeiros(before) == financeiros(after)
    assert estado(ctx, after) == "bloqueio" and not conferir(after)[0]
    assert after["pit_ok"] is False and after["max_data_publicacao"] is None


def test_terceiro_grupo_repetido_em_outro_grupo_e_valido_mas_recebimento_ainda_participa():
    ctx = construir_entrada("RI", itens=("cfo", "capex"))
    baseline = preparar(ctx)
    changed = editar_nativo(ctx, "fcf", lambda raw: raw.append(copy.deepcopy(raw[1])))
    positive = preparar(ctx, dados=changed)
    assert financeiros(positive) == financeiros(baseline) and conferir(positive)[0]
    row = next(r for r in positive["disponibilidade_demonstrativos"] if r["uso"] == "t.fcf")
    assert len(row["grupos_componentes"]) == 3 and len(row["componentes"]) == 9
    ctx_changed = (ctx[0], changed, *ctx[2:])

    def mudar(raw):
        raw[2][-1]["fonte"]["disponivel_desde"] = None

    negative = preparar(ctx, dados=editar_nativo(ctx_changed, "fcf", mudar))
    assert financeiros(negative) == financeiros(baseline) and estado(ctx, negative) == "bloqueio"


def test_campo_explicito_tem_precedencia_total_sobre_nota_antiga_invalida():
    ctx = construir_entrada("RI")
    baseline = preparar(ctx)
    explicit = editar_nativo(ctx, "receita", lambda raw: None, campo_explicito=True)
    frame = explicit.demonstrativos.copy(deep=True)
    mask = frame.componentes_fluxo.notna()
    assert mask.sum() == 1
    frame.loc[mask, "nota"] = "DADOS SIMULADOS; componentes_fluxo=JSON INVALIDO"
    after = preparar(ctx, dados=replace(explicit, demonstrativos=frame))
    chosen = next(r for r in after["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    assert financeiros(after) == financeiros(baseline) and conferir(after)[0]
    assert chosen["grupos_componentes"][0]["origem"] == "campo"


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2026-10-08T18:00:00.000001Z"])
def test_campo_explicito_invalido_nao_e_substituido_por_nota_valida(bad):
    ctx = construir_entrada("RI")
    baseline = preparar(ctx)

    def alterar(raw):
        raw[0][0]["fonte"]["disponivel_desde"] = bad

    after = preparar(ctx, dados=editar_nativo(ctx, "receita", alterar, campo_explicito=True))
    assert financeiros(after) == financeiros(baseline)
    assert estado(ctx, after) == "bloqueio"


@pytest.mark.parametrize("declaracao", [
    {"issuer_id": "SIM999"}, {"origem": "mercado"},
    {"disponivel_desde": None}, {"disponivel_desde": "2026-10-08T13:00:00Z"},
    {"period_end": "2026-09-30"}, {"period_start": "2026-07-01"}])
def test_declaracao_explicita_na_entrada_preservada_e_recusada(declaracao):
    ctx = construir_entrada("SEC")
    baseline = preparar(ctx)
    after = preparar(ctx, dados=editar_nativo(ctx, "receita", lambda raw: raw[0][0].update(declaracao)))
    chosen = next(r for r in after["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    assert all(chosen["componentes"][0][k] == v for k, v in declaracao.items())
    assert financeiros(after) == financeiros(baseline) and estado(ctx, after) == "bloqueio"


def test_sem_identidade_declarada_nao_se_inventa_frequencia_e_cancelamento_conserva_seus_sinais():
    periods = [("2025-01-01", "2025-03-31", 30), ("2025-01-01", "2025-06-30", 65),
               ("2025-01-01", "2025-09-30", 95), ("2025-01-01", "2025-12-31", 140),
               ("2026-01-01", "2026-03-31", 40), ("2026-01-01", "2026-06-30", 80)]
    ctx = construir_entrada("CVM", periodos=periods)
    pac = preparar(ctx)
    row = next(r for r in pac["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    signs = {}
    for c in row["componentes"]:
        assert not {"freq", "issuer_id", "origem"} & c.keys()
        assert c["contexto"]["issuer_id"] == "SIM003"
        signs.setdefault((c["period_start"], c["period_end"]), set()).add(c["coeficiente"])
    assert {-1.0, 1.0} in signs.values() and estado(ctx, pac) == "ok"


def test_duplicata_no_mesmo_grupo_rejeitada_sem_inventar_veto_a_reutilizacao():
    ctx = construir_entrada("CVM")
    baseline = preparar(ctx)
    after = preparar(ctx, dados=editar_nativo(ctx, "receita", lambda raw: raw[0].append(copy.deepcopy(raw[0][0]))))
    assert financeiros(after) == financeiros(baseline) and estado(ctx, after) == "bloqueio"


@pytest.fixture(scope="module")
def base_contagem():
    return construir_entrada("RI")


def escolher_mask(frame, item, row):
    mask = frame.issuer_id.eq("SIM003") & frame.item.eq(item) & frame.freq.eq(row["freq"])
    mask &= pd.to_datetime(frame.period_end).eq(pd.Timestamp(row["period_end"]))
    assert mask.sum() == 1
    return mask


@pytest.mark.parametrize("modo", ["circulacao", "emitidas_tesouraria", "so_emitidas", "mercado"])
def test_denominador_real_e_confirmadores_registrados(base_contagem, modo):
    ctx = base_contagem
    frame = ctx[1].demonstrativos.copy(deep=True)
    if modo != "circulacao":
        remover = ["acoes_em_circulacao"]
        if modo in ("so_emitidas", "mercado"):
            remover.append("acoes_tesouraria")
        if modo == "mercado":
            remover.append("acoes_emitidas")
        frame = frame[~(frame.issuer_id.eq("SIM003") & frame.item.isin(remover))].copy()
    data = replace(ctx[1], demonstrativos=frame, capital_oficial=ctx[1].capital_oficial.iloc[0:0])
    baseline = preparar(ctx, dados=data)
    assert conferir(baseline)[0]
    usages = {r["uso"] for r in baseline["disponibilidade_demonstrativos"] if r["uso"].startswith("contagem.")}
    expected = {"circulacao": {"acoes_em_circulacao"}, "emitidas_tesouraria": {"acoes_emitidas", "acoes_tesouraria"},
                "so_emitidas": {"acoes_emitidas"}, "mercado": set()}[modo]
    assert {u.removeprefix("contagem.demonstrativos.") for u in usages if u.startswith("contagem.demonstrativos.")} == expected
    assert {"contagem.mercado.market_cap", "contagem.mercado.preco"} <= usages
    for item in expected:
        changed_frame = frame.copy(deep=True)
        _, selected = Demonstrativos(frame, "SIM003").valor(item)
        changed_frame.loc[escolher_mask(frame, item, selected), "disponivel_desde"] = None
        after = preparar(ctx, dados=replace(data, demonstrativos=changed_frame))
        assert financeiros(after) == financeiros(baseline) and estado(ctx, after) == "bloqueio"
    for col in ("market_cap_disponivel_desde", "preco_disponivel_desde"):
        changed_market = copy.deepcopy(ctx[0])
        changed_market.fundamentals.loc[baseline["linha"], col] = None
        after = preparar(ctx, dados=data, md=changed_market)
        assert financeiros(after) == financeiros(baseline) and estado(ctx, after) == "bloqueio"


@pytest.mark.parametrize("oficial_escolhida", [False, True])
def test_fre_com_recibo_proprio_escolhida_ou_confirmadora(base_contagem, oficial_escolhida):
    ctx = base_contagem
    frame = ctx[1].demonstrativos.copy(deep=True)
    md = copy.deepcopy(ctx[0])
    old = preparar(ctx)
    unit = old["unidades"]
    capital = pd.DataFrame([{"issuer_id": "SIM003", "qtd_total": unit * old["acoes_por_linha"],
        "data_ref": "2026-06-30", "versao": 1, "tipo_capital": "capital total",
        "data_publicacao": None, "disponivel_desde": VALID, "url": None, "sha256": None}])
    if oficial_escolhida:
        frame = frame[~(frame.issuer_id.eq("SIM003") & frame.item.str.startswith("acoes_"))].copy()
    else:
        md.fundamentals.loc[old["linha"], "market_cap"] *= 2
    data = replace(ctx[1], demonstrativos=frame, capital_oficial=capital)
    baseline = preparar(ctx, dados=data, md=md)
    assert conferir(baseline)[0]
    assert baseline["contagem"]["fontes_participantes"] == (["oficial", "mercado"] if oficial_escolhida else ["demonstrativos", "oficial"])
    changed_capital = capital.copy(deep=True)
    changed_capital["disponivel_desde"] = None
    after = preparar(ctx, dados=replace(data, capital_oficial=changed_capital), md=md)
    assert financeiros(after) == financeiros(baseline) and estado(ctx, after) == "bloqueio"


@pytest.mark.parametrize("usage", ["receita_ano_anterior", "historico.ebit", "historico.acoes_em_circulacao", "moeda_demonstrativos", "serie_acoes"])
def test_historico_receita_anterior_moeda_e_serie_holding_efetivos(base_contagem, usage):
    ctx = base_contagem
    params = ctx[2]
    if usage == "receita_ano_anterior":
        # A fixture semestral substitui todas as receitas e só tem um TTM.
        # Acrescenta o TTM comparativo do MESMO universo/seed7 recebido.
        original = coletar(ctx[0], DAY, ["SIM003"], list(ctx[0].universe.lines.index), [])
        previous = original.demonstrativos[
            original.demonstrativos.issuer_id.eq("SIM003") & original.demonstrativos.item.eq("receita")
            & original.demonstrativos.freq.eq("TTM")
            & pd.to_datetime(original.demonstrativos.period_end).eq(pd.Timestamp("2025-06-30"))].copy()
        assert len(previous) == 1
        previous["data_publicacao"] = None
        previous["disponibilidade_tipo"] = "recepcao_observada"
        previous["disponivel_desde"] = VALID
        data = replace(ctx[1], demonstrativos=pd.concat([ctx[1].demonstrativos, previous], ignore_index=True))
        ctx = (ctx[0], data, *ctx[2:])
    if usage == "serie_acoes":
        sector = str(ctx[0].universe.issuers.loc["SIM003", "gics_sector"])
        arq = arquetipo_padrao("SIM003", sector)
        params = replace(params, arquetipos={**params.arquetipos, "SIM003": replace(arq, arquetipo="holding")})
    baseline = preparar(ctx, params=params)
    assert conferir(baseline)[0]
    selected = next(r for r in baseline["disponibilidade_demonstrativos"] if r["uso"].startswith(usage))
    frame = ctx[1].demonstrativos.copy(deep=True)
    frame.loc[escolher_mask(frame, selected["item"], selected), "disponivel_desde"] = None
    after = preparar(ctx, dados=replace(ctx[1], demonstrativos=frame), params=params)
    assert financeiros(after) == financeiros(baseline) and estado(ctx, after) == "bloqueio"


@pytest.mark.parametrize("delta,aceito", [(-1, True), (0, True), (1, False)])
def test_recibo_componente_corte_exato_e_offset_equivalente(delta, aceito):
    ctx = construir_entrada("RI")
    target = CUT + timedelta(microseconds=delta)

    def mudar(raw):
        raw[0][0]["disponivel_desde"] = target.isoformat()
        raw[0][0]["fonte"]["disponivel_desde"] = target.isoformat()

    after = preparar(ctx, dados=editar_nativo(ctx, "receita", mudar))
    assert conferir(after)[0] is aceito
    assert estado(ctx, after) == ("ok" if aceito else "bloqueio")


def test_restaurar_recibo_valido_reverte_bloqueio_sem_mutar_entrada_original():
    ctx = construir_entrada("RI", itens=("ebit", "d_a"))
    baseline = preparar(ctx)
    changed = editar_nativo(ctx, "ebitda", lambda raw: raw[1][-1]["fonte"].update({"disponivel_desde": None}))
    negative = preparar(ctx, dados=changed)
    assert estado(ctx, negative) == "bloqueio" and financeiros(negative) == financeiros(baseline)
    restored = preparar(ctx)
    assert restored == baseline and estado(ctx, restored) == "ok"


def test_periodo_futuro_da_linha_realmente_consumida_bloqueia(base_contagem):
    ctx = base_contagem
    baseline = preparar(ctx)
    frame = ctx[1].demonstrativos.copy(deep=True)
    _, chosen = Demonstrativos(frame, "SIM003").valor("caixa")
    frame.loc[escolher_mask(frame, "caixa", chosen), "period_end"] = "2026-10-09"
    changed = preparar(ctx, dados=replace(ctx[1], demonstrativos=frame))
    member = next(r for r in changed["disponibilidade_demonstrativos"] if r["uso"] == "t.caixa")
    assert pd.Timestamp(member["period_end"]).date() > DAY
    assert changed["t.caixa"] == baseline["t.caixa"] and estado(ctx, changed) == "bloqueio"
