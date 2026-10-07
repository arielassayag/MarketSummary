"""Identidades econômicas de FCFF; DADOS SIMULADOS, sem rede ou livro oficial."""

from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest

from cdp.cobertura.contexto import reinvestimento_observado
from cdp.cobertura.metodos import fcff_tres_estagios
from cdp.cobertura.reinvestimento import COMPONENTES, reinvestimento_capitalizado


def pacote(*, rou: float = 20, principal: float = 13, ano: str = "2026") -> dict:
    p = {"financeira": False, "t.ebit": 100.0, "t.capex": 30.0, "t.d_a_dfc": 25.0,
         "t.variacao_capital_giro_operacional": 5.0, "t.adicoes_direito_uso": rou,
         "t.cfo": 900.0, "t.arrendamentos_pagos": principal, "t.arrendamentos": 0,
         "historico": {}, "periodos_fluxos": {k: f"TTM|{ano}-06-30" for k in COMPONENTES},
         "moeda_demonstrativos": "BRL", "bases_fluxos": {k: "consolidado" for k in COMPONENTES},
         "moedas_fluxos": {k: "BRL" for k in COMPONENTES}}
    return p


def test_fcff_restitui_depreciacao_e_investe_em_novos_ativos_sem_amortizar_divida():
    p = pacote()
    ri = reinvestimento_capitalizado(p, 0.30)
    assert ri is not None
    assert ri["nopat"] == 70
    assert ri["reinvestimento"] == 30 + 20 - 25 + 5
    assert ri["fcf"] == 70 + 25 - 30 - 20 - 5
    assert ri["rr"] == pytest.approx(30 / 70)
    # CFO arbitrário, principal maior e juros pagos não alteram o capital reinvestido.
    q = {**p, "t.cfo": 1, "t.arrendamentos_pagos": 80, "t.juros_pagos_operacionais": 30}
    assert reinvestimento_capitalizado(q, 0.30) == ri
    assert ri["principal_descontado"] is False


def test_aquisicao_financiada_por_lease_tem_mesmo_fcff_que_aquisicao_por_capex():
    lease = reinvestimento_capitalizado(pacote(rou=20), 0.30)
    proprio = reinvestimento_capitalizado({**pacote(rou=0), "t.capex": 50.0}, 0.30)
    assert lease["fcf"] == proprio["fcf"]
    assert lease["reinvestimento"] == proprio["reinvestimento"]


def test_mais_capex_ou_rou_reduz_valor_sem_observar_preco_ou_rating():
    base = dict(receita0=1000, g1=0.03, g2=0.03, g_term=0.02, phi=0.9, margem=0.10,
                imposto=0.3, roic0=0.15, wacc=0.10, ronic_final=0.12)
    baixo = reinvestimento_capitalizado(pacote(rou=5), 0.3)
    alto = reinvestimento_capitalizado(pacote(rou=25), 0.3)
    a = fcff_tres_estagios(**base, reinvest_obs=baixo["rr"])
    b = fcff_tres_estagios(**base, reinvest_obs=alto["rr"])
    assert float(b.ev) < float(a.ev)
    assert float(b.fcff[0]) < float(a.fcff[0])


def test_modelo_publica_identidade_e_fontes_e_recusa_observacao_parcial():
    from cdp.cobertura.contexto import montar_contexto
    from cdp.cobertura.fontes import coletar
    from cdp.cobertura.insumos import preparar_emissor
    from cdp.cobertura.modelo import Avaliador
    from cdp.cobertura.parametros import carregar_parametros
    from cdp.data.synthetic import make_synthetic_market

    d = date(2026, 10, 8)
    md, params = make_synthetic_market(seed=7, as_of=d), carregar_parametros()
    iid = next(i for i in md.universe.issuers.index if md.universe.issuers.loc[i, "gics_sector"] == "Energy")
    dados = coletar(md, d, [iid], list(md.universe.lines.index), [])
    p = preparar_emissor(md, dados, params, iid, d)
    p.update({k: v for k, v in pacote().items() if k != "historico"})
    for k in COMPONENTES:
        p["fontes"][f"t.{k}"] = {"fonte": "SIMULADO", "documento": k, "sha256": k,
                                 "url": f"https://example.test/{k}", "data_publicacao": "2026-08-07"}
    ctx = montar_contexto({iid: p}, params)
    av = Avaliador(p, ctx, params, 0.045, {})
    assert av.rr_info is not None
    assert av.fcf_obs == pytest.approx(100 * (1 - av.cc.imposto) - 30)
    passos = {r["id"]: r for r in av.reg.passos}
    investimento = passos["dir.investimento_liquido"]
    assert {r["sha256"] for r in investimento["fontes"]} == set(COMPONENTES)
    assert "direitos de uso" in investimento["formula"]
    assert "principal pago não é capex" in investimento["premissas"]
    incompleto = deepcopy(p)
    del incompleto["t.variacao_capital_giro_operacional"]
    outro = Avaliador(incompleto, ctx, params, 0.045, {})
    assert outro.rr_info is None and outro.fcf_obs is None
    assert any("g ÷ RONIC" in lac["motivo"] for lac in outro.lacunas if lac["insumo"] == "reinvestimento")


@pytest.mark.parametrize("item", COMPONENTES)
def test_componente_ausente_nao_vira_zero(item):
    p = pacote()
    del p[f"t.{item}"]
    assert reinvestimento_capitalizado(p, 0.3) is None


def test_passivo_zero_no_fim_nao_comprova_ausencia_de_novos_arrendamentos():
    p = pacote()
    del p["t.adicoes_direito_uso"]
    p["t.arrendamentos"] = 0
    assert reinvestimento_capitalizado(p, 0.3) is None
    p["t.adicoes_direito_uso"] = 0  # zero divulgado no quadro é observado
    assert reinvestimento_capitalizado(p, 0.3) is not None


@pytest.mark.parametrize("periodo", ["TTM|2025-12-31", "A|2026-06-30", None])
def test_componentes_com_datas_ou_duracoes_distintas_nao_fecham_a_identidade(periodo):
    p = pacote()
    if periodo is None:
        del p["periodos_fluxos"]["d_a_dfc"]
    else:
        p["periodos_fluxos"]["d_a_dfc"] = periodo
    assert reinvestimento_capitalizado(p, 0.3) is None


@pytest.mark.parametrize("periodo", [None, "", "None", "TTM|2026-02-31", "Q|2026-06-30", "2026-06-30"])
def test_metadados_todos_presentes_mas_invalidos_nao_certificam_fluxo(periodo):
    p = pacote()
    p["periodos_fluxos"] = {k: periodo for k in COMPONENTES}
    assert reinvestimento_capitalizado(p, 0.3) is None


def test_rotulo_ptbr_do_preparador_e_periodo_canonico_sao_equivalentes():
    p = pacote()
    p["periodos_fluxos"]["d_a_dfc"] = "12 meses até 2026-06-30"
    assert reinvestimento_capitalizado(p, 0.3) is not None


@pytest.mark.parametrize("campo,valor", [("bases_fluxos", "individual"), ("bases_fluxos", None),
                                       ("moedas_fluxos", "USD"), ("moedas_fluxos", None), ("moedas_fluxos", "nan")])
def test_componentes_do_mesmo_periodo_exigem_base_contabil_e_moeda_comuns(campo, valor):
    p = pacote()
    p[campo]["adicoes_direito_uso"] = valor
    assert reinvestimento_capitalizado(p, 0.3) is None


def historico(p):
    p = deepcopy(p)
    p["historico"] = {k: {} for k in COMPONENTES}
    p["historico_periodos"] = {k: {} for k in COMPONENTES}
    p["historico_bases"] = {k: {} for k in COMPONENTES}
    p["historico_moedas"] = {k: {} for k in COMPONENTES}
    for a in ("2023", "2024", "2025"):
        for k in COMPONENTES:
            p["historico"][k][a] = p[f"t.{k}"]
            p["historico_periodos"][k][a] = f"A|{a}-12-31"
            p["historico_bases"][k][a] = "consolidado"
            p["historico_moedas"][k][a] = "BRL"
    p["historico"]["capex"]["2023"] = 5
    p["historico"]["capex"]["2024"] = 15
    p["historico"]["capex"]["2025"] = 50
    return p


def test_regime_recente_nao_projeta_media_antiga_como_fato_atual():
    p = historico(pacote())
    atual = reinvestimento_capitalizado(p, 0.3, regime="recente")
    media = reinvestimento_capitalizado(p, 0.3, regime="suavizado")
    assert atual["rr"] != media["rr"]
    assert atual["rr"] == pytest.approx(30 / 70)
    assert atual["rr_historico"] == media["rr"]
    assert media["anos"] == ["2023", "2024", "2025"]


def test_ttm_incompleto_usa_ultimo_exercicio_completo_e_registra_a_lacuna():
    p = historico(pacote())
    del p["t.adicoes_direito_uso"]
    atual = reinvestimento_capitalizado(p, 0.3)
    assert atual["anos"] == ["2025"]
    assert atual["componentes_12m_incompletos"] is True
    assert atual["rr"] == pytest.approx((50 + 20 - 25 + 5) / 70)
    p["historico_periodos"]["capex"]["2025"] = "A|2025-09-30"
    assert reinvestimento_capitalizado(p, 0.3)["anos"] == ["2024"]


def test_politica_arquivada_anterior_permanece_exatamente_recalculavel():
    p = {"t.cfo": 70, "t.capex": 30, "t.ebit": 100, "t.arrendamentos_pagos": 10}
    antigo = reinvestimento_observado(p, 0.3)
    assert antigo["fcf"] == 30
    assert antigo["rr"] == pytest.approx(1 - 30 / 70)
    assert reinvestimento_observado(p, 0.3, metodo="capitalizacao_arrendamentos") is None


@pytest.mark.parametrize("item", ["t.d_a_dfc", "t.capex", "t.adicoes_direito_uso"])
def test_magnitudes_negativas_nao_sao_normalizadas_sem_fonte(item):
    assert reinvestimento_capitalizado({**pacote(), item: -10}, 0.3) is None
