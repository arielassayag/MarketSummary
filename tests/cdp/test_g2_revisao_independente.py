"""DADOS SIMULADOS: controles não autores do delta G2, depois da coleta.

Autoria dos controles: revisor p0_bancos_argentinos. Adaptação V2 pelo autor: apenas
fixture positiva ganhou recibos SIMULADOS de market_cap/preço; offset positivo atualiza
também o recibo explícito na fonte, mantendo o mesmo instante; asserts preservados.
Não é uma alegação de bypass do seletor normal ou de recibo público histórico.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from cdp.cobertura.disponibilidade_demonstrativos import conferir, participante
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import Demonstrativos, preparar_emissor
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.qualidade import portoes_emissor
from cdp.cobertura.temporal import construir
from cdp.data.synthetic import make_synthetic_market

DAY = date(2026, 10, 8)
CUT = datetime(2026, 10, 8, 18, tzinfo=UTC)
VALID = "2026-10-08T12:00:00+00:00"


@pytest.fixture(scope="module")
def contexto():
    md = make_synthetic_market(seed=7, as_of=DAY)
    md.fundamentals["market_cap_disponivel_desde"] = VALID
    md.fundamentals["preco_disponivel_desde"] = VALID
    original = carregar_parametros()
    dados = coletar(md, DAY, list(md.universe.issuers.index), list(md.universe.lines.index), [])
    val = copy.deepcopy(original.valuation)
    val["qualidade"]["demonstrativos_disponibilidade_metodo"] = "recepcao_observada"
    val["projecao"]["resultado_corte_metodo"] = "base_preco_conhecimento_explicitos"
    params = replace(original, valuation=val)
    frame = dados.demonstrativos.copy(deep=True)
    frame["data_publicacao"] = None
    frame["disponibilidade_tipo"] = "recepcao_observada"
    frame["disponivel_desde"] = VALID
    dados = replace(dados, demonstrativos=frame, corte_temporal=construir(DAY, CUT))
    return md, dados, params


def _pac(contexto, frame=None):
    md, dados, params = contexto
    return preparar_emissor(md, dados if frame is None else replace(dados, demonstrativos=frame),
                            params, "SIM003", DAY)


def _g2(contexto, pac):
    return next(g for g in portoes_emissor(pac, {"tem_alvo": False, "metodos": []}, contexto[2]) if g["codigo"] == "G2")


def test_valido_prospectivo_nao_inventa_publicacao_pit(contexto):
    pac = _pac(contexto)
    assert conferir(pac)[0] and _g2(contexto, pac)["status"] == "ok"
    assert pac["max_data_publicacao"] is None and pac["pit_ok"] is False


@pytest.mark.parametrize("value", [None, "2026-10-08", "2026-10-08T12:00:00", CUT + timedelta(microseconds=1)])
def test_um_participante_monetario_invalido_nao_some_em_max(contexto, value):
    pac = _pac(contexto)
    pac["disponibilidade_demonstrativos"][0]["disponivel_desde"] = value
    assert not conferir(pac)[0] and _g2(contexto, pac)["status"] == "bloqueio"


@pytest.mark.parametrize("value", [CUT - timedelta(microseconds=1), CUT, "2026-10-08T19:00:00+01:00"])
def test_corte_exato_e_offsets(contexto, value):
    pac = _pac(contexto)
    for p in pac["disponibilidade_demonstrativos"]:
        p["disponivel_desde"] = value
        if "disponivel_desde" in p["fonte"]:
            p["fonte"]["disponivel_desde"] = value
    assert conferir(pac)[0]


@pytest.mark.parametrize("field,value", [("corte_temporal", None), ("as_of", None),
    ("corte_temporal", {"metodo": "base_preco_conhecimento_explicitos"}),
    ("as_of", "2026-10-07")])
def test_corte_falso_incompleto_recusa(contexto, field, value):
    pac = _pac(contexto)
    pac[field] = value
    assert not conferir(pac)[0]


@pytest.mark.parametrize("usage", ["receita_ano_anterior", "historico.receita", "historico.ebit"])
def test_todos_historicos_e_receita_anterior_efetivos_sao_verificados(contexto, usage):
    pac = _pac(contexto)
    p = next(p for p in pac["disponibilidade_demonstrativos"] if p["uso"].startswith(usage))
    p["disponivel_desde"] = None
    assert not conferir(pac)[0]


def test_receita_ttm_anterior_no_consumidor_nao_depende_de_historico_anual(contexto):
    frame = contexto[1].demonstrativos.copy(deep=True)
    row = Demonstrativos(frame, "SIM003").linha_ano_anterior("receita")
    mask = frame.issuer_id.eq("SIM003") & frame.item.eq("receita") & frame.freq.eq(row["freq"]) & frame.period_end.astype(str).eq(pd.Timestamp(row["period_end"]).date().isoformat())
    assert mask.sum() == 1 and row["freq"] == "TTM"
    frame.loc[mask, "disponivel_desde"] = None
    pac = _pac(contexto, frame)
    assert pac["receita_ano_anterior"] is not None
    assert not conferir(pac)[0]


def test_estoque_antigo_nao_selecionado_nao_contamina(contexto):
    frame = contexto[1].demonstrativos.copy(deep=True)
    rows = frame[frame.issuer_id.eq("SIM003") & frame.item.eq("caixa")].sort_values("period_end")
    oldest = rows.iloc[0]
    frame.loc[oldest.name, "disponivel_desde"] = "2099-01-01T00:00:00+00:00"
    assert conferir(_pac(contexto, frame))[0]


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2099-01-01T00:00:00+00:00"])
def test_ttm_recebido_nao_oculta_um_componente_invalido(contexto, bad):
    row = pd.Series({"item": "receita", "freq": "TTM", "period_end": "2026-06-30", "disponivel_desde": VALID,
                     "componentes_fluxo": json.dumps([
                         {"item": "receita", "freq": "Q", "period_end": "2025-09-30", "fonte": {"disponivel_desde": VALID}},
                         {"item": "receita", "freq": "Q", "period_end": "2025-12-31", "fonte": {"disponivel_desde": bad}}])})
    pac = _pac(contexto)
    pac["disponibilidade_demonstrativos"] = [participante(row, "t.receita")]
    assert not conferir(pac)[0]


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2099-01-01T00:00:00+00:00"])
def test_contagem_demonstrativos_efetiva_deve_ter_disponibilidade(contexto, bad):
    frame = contexto[1].demonstrativos.copy(deep=True)
    mask = frame.issuer_id.eq("SIM003") & frame.item.str.startswith("acoes_")
    frame.loc[mask, "disponivel_desde"] = bad
    pac = _pac(contexto, frame)
    assert pac["contagem"]["origem"] == "demonstrações" and pac["unidades"] is not None
    # Controle vermelho esperado na v1: exclusão explícita também omite denominador usado.
    assert not conferir(pac)[0]


@pytest.mark.parametrize("member", [{"disponivel_desde": VALID},
    {"uso": "t.receita", "disponivel_desde": VALID},
    {"uso": "t.receita", "item": "receita", "freq": "TTM", "disponivel_desde": VALID}])
def test_participante_sem_identidade_ou_periodo_nao_e_contrato_completo(contexto, member):
    pac = _pac(contexto)
    pac["disponibilidade_demonstrativos"] = [member]
    assert not conferir(pac)[0]


def test_componente_sem_grao_e_identidade_nao_e_contrato_completo(contexto):
    row = pd.Series({"item": "receita", "freq": "TTM", "period_end": "2026-06-30", "disponivel_desde": VALID,
                     "componentes_fluxo": json.dumps([{"fonte": {"disponivel_desde": VALID}}])})
    pac = _pac(contexto)
    pac["disponibilidade_demonstrativos"] = [participante(row, "t.receita")]
    assert not conferir(pac)[0]


def test_lista_truncada_com_identidade_valida_nao_cobre_insumos_reais(contexto):
    pac = _pac(contexto)
    assert len(pac["disponibilidade_demonstrativos"]) > 1
    pac["disponibilidade_demonstrativos"] = pac["disponibilidade_demonstrativos"][:1]
    assert not conferir(pac)[0]


@pytest.mark.parametrize("bad", [None, "2026-10-08T12:00:00", "2099-01-01T00:00:00+00:00"])
def test_apenas_contagem_atual_efetivamente_usada_tem_recibo_invalido(contexto, bad):
    frame = contexto[1].demonstrativos.copy(deep=True)
    _, selected = Demonstrativos(frame, "SIM003").valor("acoes_em_circulacao")
    mask = frame.issuer_id.eq("SIM003") & frame.item.eq("acoes_em_circulacao") & frame.freq.eq(selected["freq"]) & frame.period_end.astype(str).eq(pd.Timestamp(selected["period_end"]).date().isoformat())
    assert mask.sum() == 1
    baseline = _pac(contexto)
    frame.loc[mask, "disponivel_desde"] = bad
    pac = _pac(contexto, frame)
    assert pac["contagem"]["origem"] == "demonstrações"
    assert pac["unidades"] == baseline["unidades"]
    assert {k: v for k, v in pac.items() if k.startswith("t.")} == {k: v for k, v in baseline.items() if k.startswith("t.")}
    assert pac["fontes"]["unidades"]["disponivel_desde"] == bad
    assert not conferir(pac)[0]
