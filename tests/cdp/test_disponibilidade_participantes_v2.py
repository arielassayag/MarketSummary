"""DADOS SIMULADOS: controles de autoria V2; não são revisão independente."""
import copy
from dataclasses import replace
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from cdp.cobertura.disponibilidade_demonstrativos import conferir
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import Demonstrativos, preparar_emissor
from cdp.cobertura.parametros import arquetipo_padrao, carregar_parametros
from cdp.cobertura.temporal import construir
from cdp.data.synthetic import make_synthetic_market

DAY = date(2026, 10, 8)
VALID = "2026-10-08T12:00:00+00:00"


@pytest.fixture(scope="module")
def ctx():
    md = make_synthetic_market(seed=7, as_of=DAY)
    md.fundamentals["market_cap_disponivel_desde"] = VALID
    md.fundamentals["preco_disponivel_desde"] = VALID
    original = carregar_parametros()
    val = copy.deepcopy(original.valuation)
    val["qualidade"]["demonstrativos_disponibilidade_metodo"] = "recepcao_observada"
    val["projecao"]["resultado_corte_metodo"] = "base_preco_conhecimento_explicitos"
    params = replace(original, valuation=val)
    dados = coletar(md, DAY, list(md.universe.issuers.index), list(md.universe.lines.index), [])
    frame = dados.demonstrativos.copy(deep=True)
    frame["data_publicacao"] = None
    frame["disponibilidade_tipo"] = "recepcao_observada"
    frame["disponivel_desde"] = VALID
    capital = dados.capital_oficial.copy(deep=True)
    if not capital.empty:
        capital["disponivel_desde"] = VALID
    dados = replace(dados, demonstrativos=frame, capital_oficial=capital,
                    corte_temporal=construir(DAY, datetime(2026, 10, 8, 18, tzinfo=UTC)))
    return md, dados, params


def pac(ctx, *, frame=None, md=None, params=None, capital=None):
    market, dados, par = ctx
    if frame is not None:
        dados = replace(dados, demonstrativos=frame)
    if capital is not None:
        dados = replace(dados, capital_oficial=capital)
    return preparar_emissor(md if md is not None else market, dados,
                           params if params is not None else par, "SIM003", DAY)


def selecionada(frame, item):
    _, row = Demonstrativos(frame, "SIM003").valor(item)
    assert row is not None
    mask = frame.issuer_id.eq("SIM003") & frame.item.eq(item) & frame.freq.eq(row["freq"])
    mask &= frame.period_end.astype(str).eq(pd.Timestamp(row["period_end"]).date().isoformat())
    assert mask.sum() == 1
    return mask


def test_mapa_cobre_denominador_historico_moeda_e_valores(ctx):
    p = pac(ctx)
    assert conferir(p)[0]
    usos = {r["uso"] for r in p["disponibilidade_demonstrativos"]}
    assert "contagem.demonstrativos.acoes_em_circulacao" in usos
    assert any(u.startswith("historico.acoes_em_circulacao.") for u in usos)
    assert "moeda_demonstrativos" in usos
    assert "contagem.mercado.market_cap" in usos and "contagem.mercado.preco" in usos


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2099-01-01T00:00:00+00:00"])
def test_emitidas_menos_tesouraria_conserva_ambos_recibos(ctx, bad):
    frame = ctx[1].demonstrativos.copy(deep=True)
    frame = frame[~(frame.issuer_id.eq("SIM003") & frame.item.eq("acoes_em_circulacao"))].copy()
    mask = selecionada(frame, "acoes_tesouraria")
    baseline = pac(ctx, frame=frame)
    assert conferir(baseline)[0]
    frame.loc[mask, "disponivel_desde"] = bad
    changed = pac(ctx, frame=frame)
    assert changed["unidades"] == baseline["unidades"]
    assert {k: v for k, v in changed.items() if k.startswith("t.")} == {
        k: v for k, v in baseline.items() if k.startswith("t.")}
    assert {r["item"] for r in changed["disponibilidade_demonstrativos"]
            if r["uso"].startswith("contagem.demonstrativos.")} == {"acoes_emitidas", "acoes_tesouraria"}
    assert not conferir(changed)[0]


def test_tesouraria_descartada_nao_contamina_contagem_circulacao(ctx):
    frame = ctx[1].demonstrativos.copy(deep=True)
    frame.loc[frame.issuer_id.eq("SIM003") & frame.item.eq("acoes_tesouraria"), "disponivel_desde"] = None
    p = pac(ctx, frame=frame)
    assert p["contagem"]["origem"] == "demonstrações" and conferir(p)[0]
    assert not any(r["item"] == "acoes_tesouraria" for r in p["disponibilidade_demonstrativos"])


@pytest.mark.parametrize("field", ["market_cap_disponivel_desde", "preco_disponivel_desde"])
def test_confirmador_mercado_nao_herda_recibo_demonstrativo(ctx, field):
    md = copy.deepcopy(ctx[0])
    baseline = pac(ctx)
    md.fundamentals.loc[baseline["linha"], field] = None
    changed = pac(ctx, md=md)
    assert changed["unidades"] == baseline["unidades"] and not conferir(changed)[0]


def test_oficial_confirmador_tem_recibo_proprio_e_nao_inventa_publicacao(ctx):
    original = pac(ctx)
    capital = pd.DataFrame([{"issuer_id": "SIM003", "qtd_total": original["unidades"],
        "data_ref": "2026-06-30", "versao": 1, "tipo_capital": "capital total",
        "data_publicacao": None, "disponivel_desde": VALID, "url": None, "sha256": None}])
    md = copy.deepcopy(ctx[0])
    md.fundamentals.loc[original["linha"], "market_cap"] *= 2
    baseline = pac(ctx, md=md, capital=capital)
    assert baseline["contagem"]["fontes_participantes"] == ["demonstrativos", "oficial"]
    assert conferir(baseline)[0] and baseline["pit_ok"] is False
    capital["disponivel_desde"] = None
    changed = pac(ctx, md=md, capital=capital)
    assert changed["unidades"] == baseline["unidades"] and not conferir(changed)[0]


def test_serie_holding_conserva_linhas_exatas_e_recibos(ctx):
    par = ctx[2]
    setor = str(ctx[0].universe.issuers.loc["SIM003", "gics_sector"])
    arq = arquetipo_padrao("SIM003", setor)
    params = replace(par, arquetipos={**par.arquetipos, "SIM003": replace(arq, arquetipo="holding")})
    baseline = pac(ctx, params=params)
    rows = [r for r in baseline["disponibilidade_demonstrativos"] if r["uso"].startswith("serie_acoes.")]
    assert len(rows) == len(baseline["serie_acoes"]) > 1 and conferir(baseline)[0]
    frame = ctx[1].demonstrativos.copy(deep=True)
    chosen = rows[0]
    mask = frame.issuer_id.eq("SIM003") & frame.item.eq(chosen["item"]) & frame.freq.eq(chosen["freq"])
    mask &= frame.period_end.astype(str).eq(pd.Timestamp(chosen["period_end"]).date().isoformat())
    assert mask.sum() == 1
    frame.loc[mask, "disponivel_desde"] = None
    changed = pac(ctx, frame=frame, params=params)
    assert changed["serie_acoes"] == baseline["serie_acoes"] and not conferir(changed)[0]


@pytest.mark.parametrize("field,bad", [("issuer_id", None), ("origem", "inexistente"),
    ("item", ""), ("freq", "inexistente"), ("period_end", "inexistente"), ("uso", "")])
def test_grao_obrigatorio_e_valido(ctx, field, bad):
    p = pac(ctx)
    p["disponibilidade_demonstrativos"][0][field] = bad
    assert not conferir(p)[0]


def test_manifesto_truncado_tambem_nao_cobre_campos_usados(ctx):
    p = pac(ctx)
    chosen = next(r for r in p["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    p["disponibilidade_demonstrativos"].remove(chosen)
    m = p["manifesto_disponibilidade"]
    m["participantes_esperados"] = [r for r in m["participantes_esperados"] if r["uso"] != "t.receita"]
    m["vinculos"].pop("t.receita")
    assert p["t.receita"] is not None and not conferir(p)[0]


def test_duplicata_nao_e_selo_de_completude(ctx):
    p = pac(ctx)
    p["disponibilidade_demonstrativos"].append(copy.deepcopy(p["disponibilidade_demonstrativos"][0]))
    assert not conferir(p)[0]


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2099-01-01T00:00:00+00:00",
                                 "2026-10-08T13:00:00+00:00"])
def test_recibo_externo_valido_nao_oculta_recibo_da_fonte(ctx, bad):
    p = pac(ctx)
    r = next(r for r in p["disponibilidade_demonstrativos"] if r["uso"] == "t.receita")
    assert r["disponivel_desde"] == VALID and "disponivel_desde" in r["fonte"]
    r["fonte"]["disponivel_desde"] = bad
    assert not conferir(p)[0]


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2099-01-01T00:00:00+00:00",
                                 "2026-10-08T13:00:00+00:00"])
def test_componente_externo_valido_nao_oculta_recibo_da_fonte(ctx, bad):
    from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes

    p = {"issuer_id": "SIM003", "as_of": DAY.isoformat(), "corte_temporal": ctx[1].corte_temporal,
         "t.receita": 100}
    row = {"item": "receita", "freq": "TTM", "period_end": "2026-06-30", "disponivel_desde": VALID,
           "componentes_fluxo": [{"item": "receita", "freq": "Q", "period_end": "2026-03-31",
                                  "fonte": {"disponivel_desde": VALID}}]}
    registro = RegistroParticipantes("SIM003")
    registro.registrar(row, "t.receita")
    registro.finalizar(p)
    assert conferir(p)[0]
    p["disponibilidade_demonstrativos"][0]["componentes"][0]["fonte"]["disponivel_desde"] = bad
    assert not conferir(p)[0]


@pytest.mark.parametrize("periodo", ["invalido", "2099-01-01"])
def test_periodo_financeiro_invalido_ou_futuro_recusado(ctx, periodo):
    p = pac(ctx)
    p["disponibilidade_demonstrativos"][0]["period_end"] = periodo
    # Mesmo que o manifesto declare esse grão, a data em si é inválida.
    p["manifesto_disponibilidade"]["participantes_esperados"][0]["period_end"] = periodo
    assert not conferir(p)[0]


def test_periodo_financeiro_apos_base_precos_e_antes_modelo_e_valido(ctx):
    from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes

    p = {"issuer_id": "SIM003", "as_of": DAY.isoformat(), "t.receita": 100,
         "corte_temporal": {**ctx[1].corte_temporal, "base_preco": "2026-03-31"}}
    registro = RegistroParticipantes("SIM003")
    registro.registrar({"item": "receita", "freq": "TTM", "period_end": "2026-06-30",
                        "disponivel_desde": VALID}, "t.receita")
    registro.finalizar(p)
    assert conferir(p)[0]


def test_participante_extra_nao_certifica_pacote(ctx):
    p = pac(ctx)
    extra = copy.deepcopy(p["disponibilidade_demonstrativos"][0])
    extra["uso"] = "uso_extra_nao_realizado"
    p["disponibilidade_demonstrativos"].append(extra)
    assert not conferir(p)[0]


def test_vinculo_malformado_recusa_sem_excecao(ctx):
    p = pac(ctx)
    p["manifesto_disponibilidade"]["vinculos"]["historico.incompleto"] = {
        "usos": [p["disponibilidade_demonstrativos"][0]["uso"]], "valor": 100}
    assert not conferir(p)[0]
