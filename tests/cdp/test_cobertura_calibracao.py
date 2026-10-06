"""Calibração da cobertura (revisão 2026-10.3): testes de referência (golden) das peças novas e
propriedades de distribuição no universo sintético (DADOS SIMULADOS, sem rede).

Peças: ERP contemporâneo com o estático como sensibilidade; calibração de nível por país;
persistência do ROE por classe de estabilidade (norma em spread sobre o ke, porte, θ, ω);
calendarização do consenso; P/L justificado com modelo H; rating sintético no custo da dívida;
contagem de ações conciliada (G13c); TTM pela identidade anual + acumulado; marcadores "em
conferência"; alertas da fonte (G17); α pela média sem o piso de zero (G16); retorno extremo
simétrico em log com corroboração (G11); combinação robusta (G18); soma das partes com janela
reiniciada por variação das ações."""

from __future__ import annotations

import math
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from cdp.cobertura import metodos as M
from cdp.cobertura.contexto import (
    alvo_roe,
    fracao_exercicio,
    reinvestimento_observado,
    roe_historico,
)
from cdp.cobertura.custo_capital import erp_oficial, spread_corporativo
from cdp.cobertura.fontes import alertas_de_attrs, coletar
from cdp.cobertura.insumos import (
    Demonstrativos,
    _participacao_conferida,
    conciliar_contagem,
    desde_por_acoes,
)
from cdp.cobertura.motor import executar
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.qualidade import _g11, _g13b, _g13c, _g17, portoes_emissor
from cdp.data.synthetic import make_synthetic_market

D = date(2026, 10, 8)


@pytest.fixture(scope="module")
def params():
    return carregar_parametros()


@pytest.fixture(scope="module")
def run(params):
    md = make_synthetic_market(seed=7, as_of=D)
    dados = coletar(md, D, list(md.universe.issuers.index), list(md.universe.lines.index), ["ILF", "EWZ", "EWW"])
    return md, executar(md, dados, params, D)


# ============================================================ golden: peças puras

def test_exponential_roe_fade_golden():
    r = M.caminho_roe(0.25, 0.22, 0.14, 12, omega=0.70)
    assert r[0] == pytest.approx(0.25) and r[1] == pytest.approx(0.22)
    for t in range(3, 13):
        assert r[t - 1] == pytest.approx(0.14 + 0.08 * 0.70 ** (t - 2), rel=1e-12)
    lin = M.caminho_roe(0.25, 0.22, 0.14, 12)
    assert lin[-1] == pytest.approx(0.14) and lin[6] == pytest.approx(0.22 - 0.08 * 5 / 10)
    # o lucro residual usa o caminho escolhido: decaimento mais lento ⇒ mais valor com ROE acima do ke
    lento = float(M.rim_gls(10.0, 0.25, 0.22, 0.14, 0.12, 0.4, 12, omega=0.85).valor)
    rapido = float(M.rim_gls(10.0, 0.25, 0.22, 0.14, 0.12, 0.4, 12, omega=0.55).valor)
    assert lento > rapido


def test_h_model_factor_golden():
    # Fuller e Hsia: 1 + H × (g_c − g) ÷ (1 + g) = 1 + 4 × 10% ÷ 1,05
    assert float(M.fator_h(0.15, 0.05, 4.0)) == pytest.approx(1 + 4 * 0.10 / 1.05, rel=1e-12)
    assert float(M.fator_h(0.05, 0.05, 4.0)) == pytest.approx(1.0)


def test_concession_run_off_last_third(params):
    w = M.perfil_runoff(21, 1 / 3)
    assert not w[:14].any() and w[-1] == pytest.approx(1.0) and np.all(np.diff(w[14:]) > 0)
    base = dict(receita0=1000.0, g1=0.06, g2=0.05, g_term=0.04, phi=0.9, margem=0.4, imposto=0.3, roic0=0.10,
                wacc=0.10, vida=21, reinvest_obs=0.5)
    sem = M.fcff_tres_estagios(**base)
    com = M.fcff_tres_estagios(**base, runoff_fracao=1 / 3, g_runoff=0.03)
    assert com.reinvest[-1] == pytest.approx(0.0, abs=1e-12) and com.g[-1] == pytest.approx(0.03)
    assert float(com.pv_terminal) == 0.0 and float(com.ev) > float(sem.ev)


def test_commodity_margin_path_reverts_to_cycle():
    mg = 0.10 + (0.30 - 0.10) * M.perfil_transitorio(10, 3, 5)
    res = M.fcff_tres_estagios(1000.0, 0.0, 0.0, 0.0, 0.9, mg, 0.3, 0.1, 0.1, ronic_final=0.1, reinvest_obs=0.0)
    assert res.nopat[0] == pytest.approx(1000 * 0.30 * 0.7) and res.nopat[-1] == pytest.approx(1000 * 0.10 * 0.7)


def test_synthetic_rating_spread_golden():
    tab = carregar_parametros().cc
    # cobertura = EBIT ÷ (dívida bruta com arrendamentos × (rf + spread soberano + reserva de 1,5%)), base dólar
    pac = {"divida_bruta": 900.0, "arrendamentos": 100.0, "divida_liquida": 600.0}
    k_ref = 0.05 + 0.02 + 0.015
    assert spread_corporativo({**pac, "t.ebit": 3.2 * 1000 * k_ref}, tab, 0.05, 0.02)[:3] == (0.0089, "A−", pytest.approx(3.2))
    assert spread_corporativo({**pac, "t.ebit": 0.9 * 1000 * k_ref}, tab, 0.05, 0.02)[:2] == (0.0885, "CCC")
    # o resultado financeiro líquido (câmbio, derivativos, aplicações) nunca define a cobertura
    assert spread_corporativo({**pac, "t.ebit": 0.9 * 1000 * k_ref, "t.resultado_financeiro": 50.0}, tab, 0.05,
                              0.02)[:2] == (0.0885, "CCC")
    # caixa líquido, EBIT não positivo ou sem os insumos ⇒ spread de reserva (nunca AAA nem D por sinal)
    assert spread_corporativo({**pac, "divida_liquida": -10.0, "t.ebit": 50.0}, tab, 0.05, 0.02)[:3] == (0.015, None, None)
    assert spread_corporativo({**pac, "t.ebit": -50.0}, tab, 0.05, 0.02)[:3] == (0.015, None, None)
    assert spread_corporativo({"t.ebit": 50.0}, tab, 0.05, 0.02)[:3] == (0.015, None, None)


def test_official_erp_is_the_contemporaneous_pair(params):
    erp, chave = erp_oficial(params.cc)
    assert erp == pytest.approx(0.037) and chave == "damodaran_erp_mensal"
    assert erp_oficial({**params.cc, "modo_erp": "estatico"}) == (0.042, "damodaran_ctryprem")


def test_fiscal_year_fraction_and_roe_history():
    assert fracao_exercicio({"fim_exercicio": "2025-12-31", "as_of": "2026-10-06"}) == pytest.approx(279 / 365)
    assert fracao_exercicio({"fim_exercicio": "2024-12-31", "as_of": "2026-10-06"}) == 1.0
    assert fracao_exercicio({"as_of": "2026-10-06"}) is None
    hist = {"lucro_liquido_controladores": {str(a): v for a, v in zip(range(2018, 2026), [5, 6, -1, 9, 10, 11, 12, 13], strict=True)},
            "patrimonio_controladores": {str(a): 100.0 for a in range(2018, 2026)}}
    r = roe_historico({"historico": hist}, 5)
    assert [a for a, _ in r["serie"]] == ["2021", "2022", "2023", "2024", "2025"]
    assert r["mediana"] == pytest.approx(0.11) and r["prejuizo"] == 0
    assert roe_historico({"historico": hist}, 6)["prejuizo"] == 1


def test_observed_reinvestment_three_years_then_ttm():
    p = {"historico": {"cfo": {"2023": 100.0, "2024": 120.0, "2025": 80.0}, "capex": {"2023": 40.0, "2024": 60.0,
                                                                                     "2025": 50.0},
                       "ebit": {"2023": 150.0, "2024": 150.0, "2025": 150.0}}}
    rr = reinvestimento_observado(p, 0.3, 3)
    assert rr["rr"] == pytest.approx(1 - 150.0 / 315.0) and rr["base"] == "3 exercícios"
    rr1 = reinvestimento_observado({"t.cfo": 50.0, "t.capex": 20.0, "t.ebit": 100.0}, 0.3, 3)
    assert rr1["rr"] == pytest.approx(1 - 30.0 / 70.0) and rr1["base"] == "12 meses"


def _ctx_roe(ke=0.12):
    return {"normas_roe": {"setor_arquetipo": {"Industrials|corporativo": {"spread": 0.01, "n": 12}},
                           "setor": {"Industrials": {"spread": 0.02, "n": 20}}, "pais_setor": {},
                           "universo": {"spread": 0.0, "n": 100}},
            "porte": {"b": 0.025, "mediana_ln_mcap_setor": {"Industrials": 21.0}},
            "fundamentos": {"E": {"roe_hist": 0.30, "roe_hist_sigma": 0.02, "roe_hist_prejuizo": 0, "roe_hist_n": 5,
                                  "ln_mcap_usd": 23.0},
                            "I": {"roe_hist": 0.05, "roe_hist_sigma": 0.15, "roe_hist_prejuizo": 1,
                                  "roe_hist_n": 5, "ln_mcap_usd": 19.0},
                            "N": {"roe_hist": None, "roe_hist_n": 1, "ln_mcap_usd": None}}}


def test_roe_target_by_stability_class_golden(params):
    ctx = _ctx_roe()
    e = alvo_roe(ctx, params, "E", "BR", "Industrials", "corporativo", 0.12, 0.26)
    # norma = ke + spread + porte = 12% + 1% + mín(2,5% × 2; 5%) = 18%; R̄ = (30% + 26%) ÷ 2 = 28%
    assert e["norma"] == pytest.approx(0.18) and e["rbar"] == pytest.approx(0.28)
    assert e["classe"] == "estavel" and e["theta"] == 0.60 and e["omega"] == 0.85
    assert e["alvo"] == pytest.approx(0.18 + 0.60 * 0.10)
    i = alvo_roe(ctx, params, "I", "BR", "Industrials", "corporativo", 0.12, -0.20)
    # prejuízo ⇒ instável; R̄ = −7,5% limitado a norma − 5 p.p.; porte −5 p.p. (limite)
    assert i["classe"] == "instavel" and i["norma"] == pytest.approx(0.12 + 0.01 - 0.05)
    assert i["rbar_limitado"] == pytest.approx(i["norma"] - 0.05)
    assert i["alvo"] == pytest.approx(i["norma"] - 0.15 * 0.05)
    n = alvo_roe(ctx, params, "N", "BR", "Industrials", "outro", 0.12, None)
    assert n["referencia"]["tipo"] == "setor" and n["alvo"] == pytest.approx(0.14) and n["classe"] == "instavel"


# ============================================================ golden: insumos e portões

def _p(qtd=None):
    return {"qtd_total": qtd, "data_ref": "2026-12-31", "versao": 7.0, "data_publicacao": "2026-09-01",
            "tipo_capital": "Capital Integralizado", "fonte": {"fonte": "CVM"}}


def test_share_count_reconciliation_resolves_unit_traps(params):
    fd, fm = {"fonte": "CVM"}, {"fonte": "YAHOO"}
    # TAESA: valor de mercado da fonte de dados conta ações como units (3×); demonstrações = FRE
    n, st, _, info = conciliar_contagem(1033.5e6, 3.0, 1033.5e6, _p(1033.5e6), params, fd, fm, False)
    assert n == pytest.approx(344.5e6) and st == "demonstrativos" and info["status"] == "ok"
    # KLABIN: idem com 5 ações por unit
    n, *_ = conciliar_contagem(6152.9e6, 5.0, 6152.9e6, _p(6241.5e6), params, fd, fm, False)
    assert n == pytest.approx(6152.9e6 / 5)
    # demonstrações erradas, FRE e mercado concordam ⇒ FRE
    n, st, _, info = conciliar_contagem(137.3e6, 1.0, 549.3e6, _p(550.0e6), params, fd, fm, False)
    assert st == "oficial" and n == pytest.approx(550.0e6)
    # nenhum par ⇒ bloqueio, com as três contagens no detalhe
    *_, info = conciliar_contagem(978.8e6, 1.0, 3290e6, _p(1163e6), params, fd, fm, False)
    assert info["status"] == "bloqueio" and "Formulário de Referência" in info["detalhe"]
    # sem fonte oficial: divergência ⇒ mercado com aviso; unidade conferida ⇒ demonstrações em unidades
    n, st, _, info = conciliar_contagem(39.3e6, 1.0, 392e6, None, params, fd, fm, False)
    assert st == "valor_de_mercado" and info["status"] == "aviso"
    n, st, _, info = conciliar_contagem(600e6, 3.0, 600e6, None, params, fd, fm, True)
    assert st == "demonstrativos_em_unidades" and info["status"] == "ok"
    assert _g13c({"contagem": info, "unidades": n})["status"] == "ok"


def _demo(rows):
    base = dict(issuer_id="X", currency="BRL", escala=1, consolidado=True, fonte="CVM", url=None,
                documento="ITR", sha256=None)
    return pd.DataFrame([{**base, **r} for r in rows])


def test_ttm_from_annual_plus_year_to_date():
    rows = [dict(demonstrativo="DRE", freq="A", period_end="2025-12-31", item="receita", value=400.0,
                 data_publicacao=pd.Timestamp("2026-03-20"))]
    for d, v in (("2025-03-31", 90.0), ("2025-06-30", 95.0), ("2026-03-31", 110.0), ("2026-06-30", 120.0)):
        rows.append(dict(demonstrativo="DRE", freq="Q", period_end=d, item="receita", value=v,
                         data_publicacao=pd.Timestamp(d) + pd.Timedelta(days=40)))
    dem = Demonstrativos(_demo(rows), "X")
    v, row = dem.valor("receita")
    assert v == pytest.approx(400 + 110 + 120 - 90 - 95) and row["freq"] == "TTM"
    assert pd.Timestamp(row["period_end"]) == pd.Timestamp("2026-06-30") and "acumulado" in row["documento"]


def test_conference_marker_makes_the_period_missing():
    rows = [dict(demonstrativo="BP", freq="Q", period_end="2026-03-31", item="acoes_em_circulacao", value=700e6,
                 data_publicacao=pd.Timestamp("2026-05-10"), nota=None),
            dict(demonstrativo="BP", freq="Q", period_end="2026-06-30", item="acoes_em_circulacao", value=np.nan,
                 data_publicacao=pd.Timestamp("2026-08-10"), nota="conferência: fora de 0,5–2× sem confirmação"),
            dict(demonstrativo="BP", freq="Q", period_end="2026-06-30", item="patrimonio_controladores", value=5e9,
                 data_publicacao=pd.Timestamp("2026-08-10"), nota=None)]
    dem = Demonstrativos(_demo(rows), "X")
    assert dem.valor("acoes_em_circulacao") == (None, None)
    assert dem.em_conferencia and dem.em_conferencia[0][0] == "acoes_em_circulacao"
    assert dem.valor("patrimonio_controladores")[0] == pytest.approx(5e9)


def test_source_alerts_parsing_and_g17(params):
    al = alertas_de_attrs({"qa": ["BR_X: receita Q salto de 12.5× entre 2025-12-31 e 2026-06-30 — conferir",
                                  "BR_X: caixa Q salto de 30× entre 2026-03-31 e 2026-06-30 — conferir",
                                  "BR_Y: ITR 2021-03-31 v1: capex 1,0 é 4% das saídas de investimento"],
                           "moeda_trocada": {"BR_Z": {"moeda": "USD", "anteriores": ["CAD"], "desde": "2026-03-30",
                                                      "fatos_descartados": 68}}})
    x = al[al.issuer_id == "BR_X"].to_dict("records")
    assert {r["item"] for r in x} == {"receita", "caixa"} and {r["tipo"] for r in x} == {"salto"}
    pac = {"max_data_publicacao": "2026-08-10", "as_of": "2026-10-08",
           "alertas_fonte": [{k: r[k] for k in ("tipo", "texto", "data", "item")} for r in x]}
    g = _g17(pac, {}, params)
    assert g["status"] == "aviso" and "receita" in g["detalhe"] and "caixa" not in g["detalhe"]
    z = al[al.issuer_id == "BR_Z"].to_dict("records")
    g = _g17({"max_data_publicacao": "2026-08-10", "historico": {"receita": {"2025": 1.0}},
              "alertas_fonte": [{k: r[k] for k in ("tipo", "texto", "data", "item")} for r in z]}, {}, params)
    assert g["status"] == "aviso" and "insumos históricos indisponíveis" in g["detalhe"]


def test_g11_is_log_symmetric_with_corroboration(params):
    pac = {"preco": 10.0, "consenso": {"plausivel": True, "upside": -0.45}}
    tres = {"metodos": [{"valor": 3.0}, {"valor": 4.0}, {"valor": 5.0}], "cv_todos": 0.2}
    assert _g11(pac, {**tres, "etr": -0.40}, params)["status"] == "ok"
    # toda a faixa de aviso exige corroboração: por ≥ 3 métodos do mesmo lado (CV ≤ 50%) ⇒ aviso
    assert _g11(pac, {**tres, "etr": -0.55}, params)["status"] == "aviso"
    sem = {"preco": 10.0, "consenso": {"plausivel": True, "upside": 0.20}}
    g = _g11(sem, {"metodos": [{"valor": 3.0}, {"valor": 4.0}], "cv_todos": 0.1, "etr": -0.55}, params)
    assert g["status"] == "bloqueio" and "sem corroboração" in g["detalhe"]   # 2 métodos não bastam
    # o método limitado (G18) e o não positivo contam como dissidência
    diss = {"metodos": [{"valor": 3.0, "valor_bruto": 14.0}, {"valor": 4.0}, {"valor": 5.0}], "cv_todos": 0.7}
    assert _g11(sem, {**diss, "etr": -0.55}, params)["status"] == "bloqueio"
    nao_pos = {"metodos": [{"valor": 3.0}, {"valor": 4.0}, {"valor": None, "valor_calculado": -2.0}], "cv_todos": 0.6}
    assert _g11(sem, {**nao_pos, "etr": 1.2}, params)["status"] == "bloqueio"
    # consenso: mesmo lado e magnitude compatível (||ln(1 + ETR)| − |ln(1 + upside)|| ≤ 0,4)
    um = {"metodos": [{"valor": 30.0}], "cv_todos": None}
    assert _g11({"preco": 10.0, "consenso": {"plausivel": True, "upside": 0.80}}, {**um, "etr": 1.45}, params)["status"] == "aviso"
    g = _g11({"preco": 10.0, "consenso": {"plausivel": True, "upside": 0.54}}, {**um, "etr": 1.87}, params)
    assert g["status"] == "bloqueio" and "magnitude incompatível" in g["detalhe"]   # caso Suzano
    assert _g11(sem, {**um, "etr": 1.45}, params)["status"] == "bloqueio"


def test_g13b_consensus_and_margin_traps(params):
    assert _g13b({"preco": 20.0, "eps_fy2": 23.6, "arquetipo": "corporativo"}, {}, params)["status"] == "bloqueio"
    assert _g13b({"preco": 20.0, "arquetipo": "corporativo"}, {"margem": 1.15}, params)["status"] == "bloqueio"
    assert _g13b({"preco": 20.0, "arquetipo": "holding"}, {"margem": 1.15}, params)["status"] == "ok"
    assert _g13b({"preco": 20.0, "arquetipo": "corporativo"}, {"roe2": 1.55}, params)["status"] == "bloqueio"


def test_g16_and_unfloored_alpha_in_gates(params):
    pac = {"as_of": "2026-10-08", "status_moeda": "ok", "defasagem_preco_dias": 0, "tem_demonstrativos": False}
    base = {"tem_alvo": True, "metodos": [{"valor": 1.0}], "tp": 10.0, "tp_otimista": 12.0, "tp_pessimista": 0.0,
            "upside": 0.1, "etr": 0.12, "pwr": -0.30, "pwr_com_piso": 0.05}
    g = {p["codigo"]: p for p in portoes_emissor(pac, {**base, "p_patrimonio_zero": 0.35}, params)}
    assert g["G16"]["status"] == "aviso" and "sem o piso" in g["G16"]["detalhe"]
    g = {p["codigo"]: p for p in portoes_emissor(pac, {**base, "p_patrimonio_zero": 0.02}, params)}
    assert g["G16"]["status"] == "ok"


def test_holding_window_restarts_on_share_issuance_not_on_splits():
    idx = pd.to_datetime(["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"])
    close = pd.DataFrame({"H": [10.0, 10.0, 5.0, 5.0], "K": [10.0, 10.0, 10.0, 10.0]}, index=idx)
    adj = pd.DataFrame({"H": [5.0, 5.0, 5.0, 5.0], "K": [10.0, 10.0, 10.0, 10.0]}, index=idx)
    md = SimpleNamespace(close=close, adj_close=adj)
    # H: ações dobram com o preço caindo à metade e o ajustado contínuo ⇒ desdobramento, sem reinício
    assert desde_por_acoes(md, "H", [["2025-09-30", 100.0], ["2025-12-31", 200.0]], 0.05, date(2026, 10, 6)) == (None, None)
    # K: ações +40% sem ajuste de preço ⇒ emissão (ou mudança de base) ⇒ janela desde a nova contagem
    d, motivo = desde_por_acoes(md, "K", [["2025-09-30", 100.0], ["2025-12-31", 140.0]], 0.05, date(2026, 10, 6))
    assert d == "2025-12-31" and "ações da holding" in motivo


def test_stake_confirmation_requires_document_dates():
    ok = {"conferido": True, "url": "http://x", "data_publicacao": "2026-08-12", "data_referencia": "2026-08-12",
          "documento": "FRE"}
    assert _participacao_conferida(ok, date(2026, 10, 6))[0]
    assert not _participacao_conferida({**ok, "data_publicacao": "2026-10-07"}, date(2026, 10, 6))[0]
    assert not _participacao_conferida({**ok, "data_referencia": "2025-01-31"}, date(2026, 10, 6))[0]
    assert not _participacao_conferida({**ok, "url": None}, date(2026, 10, 6))[0]


def test_curated_stakes_cite_public_filings(params):
    for hold, cfg in params.sotp["holdings"].items():
        for p in cfg["participacoes"]:
            assert p.get("url") and p.get("documento") and p.get("data_publicacao") and p.get("data_referencia"), hold
            assert p.get("fonte") in ("CVM", "SEC", "RI"), hold
            assert 0 < float(p["fracao"]) <= 1


# ============================================================ propriedades no universo sintético

def test_country_level_calibration_centres_median_alpha(run, params):
    _, ex = run
    cal = ex.contexto["calibracao_pais"]
    lim = float(params.cc["calibracao_pais"]["limite"])
    assert cal, "calibração de nível vazia"
    por_pais: dict[str, list[float]] = {}
    for iid, m in ex.modelos.items():
        if m.get("tem_alvo"):
            por_pais.setdefault(ex.pacotes[iid]["pais"], []).append(float(m["alpha"]))
    proprios = {p: c for p, c in cal.items() if c.get("grupo") == p}
    for pais, c in cal.items():
        assert abs(c["delta"]) <= lim + 1e-12
        if c.get("grupo") == pais and not c["limitado"]:
            assert abs(float(np.median(por_pais[pais]))) <= 0.05, (pais, np.median(por_pais[pais]))
            # ponto fixo: a mediana de V0 ÷ P0 com o ajuste aplicado fica na tolerância
            assert abs(c["mediana_v_p"] - 1) <= float(params.cc["calibracao_pais"]["tolerancia"]) + 1e-9
        elif c.get("grupo") == "regional":
            # países sem nível próprio: mediana ponderada dos δ dos países calibrados
            pares = sorted((x["delta"], x["n"]) for x in proprios.values())
            tot, acum, d_reg = sum(n for _, n in pares), 0, None
            for d, n in pares:
                acum += n
                if acum >= tot / 2:
                    d_reg = d
                    break
            assert c["delta"] == pytest.approx(d_reg)
        iid = next(i for i in ex.modelos if ex.pacotes[i]["pais"] == pais)
        ids = [p["id"] for p in ex.registros[iid].passos]
        assert ("ke.calibracao_pais" in ids) == (abs(c["delta"]) > 0)
        assert ex.modelos[iid]["custo_capital"]["delta_calibracao"] == pytest.approx(c["delta"], abs=1e-6)


def test_static_erp_is_a_disclosed_sensitivity(run):
    _, ex = run
    for iid, m in ex.modelos.items():
        cc = m["custo_capital"]
        # sensibilidade de um fator: só o ERP muda (ajuste de nível do país mantido)
        esperado = (1 + cc["ke_usd"] + cc["beta"] * (cc["erp_estatico"] - cc["erp"])) * (1 + cc["pi_local"]) \
            / (1 + cc["pi_us"]) - 1
        assert cc["ke_estatico"] == pytest.approx(esperado, abs=2e-6)
        assert cc["ke_estatico"] > cc["ke"]
        ids = {p["id"] for p in ex.registros[iid].passos}
        assert "ke.estatico" in ids
        if m.get("tem_alvo") and m.get("tp_ke_estatico") is not None:
            assert "sensibilidade.ke_estatico" in ids


def test_alpha_uses_the_unfloored_mean_and_floor_is_displayed(run):
    _, ex = run
    for m in ex.modelos.values():
        if not m.get("tem_alvo"):
            continue
        assert m["alpha"] == pytest.approx(m["pwr"] - m["custo_capital"]["ke"], abs=1e-5)
        assert m["pwr_com_piso"] >= m["pwr"] - 1e-12
        if m["p_patrimonio_zero"] >= 0.10:
            assert any(p["codigo"] == "G16" and p["status"] == "aviso" for p in m["portoes"])


def test_ratings_relative_style_neutral_and_guarded(run, params):
    _, ex = run
    r = params.sec("rating")
    frac = float(r["estilo"]["fracao_limiar"])
    for m in ex.modelos.values():
        if m["rating"] not in ("Compra", "Venda"):
            continue
        tau = float(r["limiar_alpha_rel"][m["incerteza"]])
        assert m["confianca"] in ("A", "B")
        if m["rating"] == "Compra":
            assert m["alpha_rel"] >= tau and m["alpha_rel_estilo"] >= frac * tau and m["etr"] >= m["custo_capital"]["ke"]
        else:
            assert m["alpha_rel"] <= -tau and m["alpha_rel_estilo"] <= -frac * tau
    # pares: quem está bloqueado, em G11 ou G16 não entra na mediana dos demais
    excl = {i for i, m in ex.modelos.items()
            if any(p["status"] == "bloqueio" or (p["status"] == "aviso" and p["codigo"] in ("G11", "G16"))
                   for p in m["portoes"])}
    for iid, m in ex.modelos.items():
        if m.get("pares"):
            outros = [j for j, a in m["pares"]["alphas"] if j != iid and a is not None]
            assert not (set(outros) & excl)


def test_every_blocked_issuer_has_a_precise_reason(run):
    _, ex = run
    for iid, m in ex.modelos.items():
        if m["rating"] != "Em revisão":
            continue
        bl = [p for p in m["portoes"] if p["status"] == "bloqueio"]
        assert bl and all(len(p["detalhe"]) > 15 for p in bl), iid
        assert m["rating_motivo"].startswith("portão de qualidade bloqueante")


def test_roe_persistence_identity_holds_in_every_model(run):
    _, ex = run
    n = 0
    for m in ex.modelos.values():
        pr = m.get("persistencia_roe")
        if not pr or pr.get("rbar_limitado") is None:
            continue
        n += 1
        assert pr["alvo"] == pytest.approx(pr["norma"] + pr["theta"] * (pr["rbar_limitado"] - pr["norma"]), rel=1e-5)
        assert pr["norma"] + pr["faixa"][0] - 1e-5 <= pr["rbar_limitado"] <= pr["norma"] + pr["faixa"][1] + 1e-5
        assert (pr["theta"], pr["omega"]) in ((0.60, 0.85), (0.35, 0.70), (0.15, 0.55))
    assert n >= 20


def test_calendarized_consensus_and_h_model_in_open_model(run):
    _, ex = run
    vistos = {"dir.lpa_12m": 0, "dir.lpa_12m_2": 0, "metodo.multiplo_justificado": 0}
    for reg in ex.registros.values():
        for p in reg.passos:
            if p["id"] in vistos:
                vistos[p["id"]] += 1
                if p["id"] == "metodo.multiplo_justificado":
                    assert "Fuller e Hsia" in (p.get("premissas") or "") or "H ×" not in p["formula"]
    assert all(v > 0 for v in vistos.values()), vistos


def test_context_is_deterministic(run, params):
    from cdp.cobertura.contexto import montar_contexto
    from cdp.cobertura.motor import arredondar
    from cdp.hashing import sha256_obj

    _, ex = run
    rf = ex.rf["valor"]
    a = sha256_obj(arredondar(montar_contexto(ex.pacotes, params, rf, ex.rf["fonte"])))
    assert a == sha256_obj(arredondar(ex.contexto))
    _ = math  # noqa: F841


def test_discrepant_method_limits_confidence_with_dissent_in_the_dispersion(params):
    from cdp.cobertura.rating import confianca

    pac = {"pais": "BR", "pit_ok": True, "status_moeda": "ok"}
    g18 = [{"codigo": "G18", "status": "aviso", "nome": "Métodos coerentes", "detalhe": "x"}]
    base = {"tem_alvo": True, "n_metodos": 3, "cv": 0.05, "n_eps": 8, "eps1_consenso": True, "portoes": g18,
            "dissidencia": [{"metodo": "fcff", "tipo": "limitado", "valor": 40.0}]}
    # a dispersão usada é a de TODOS os métodos calculados (o discrepante pelo valor bruto)
    assert confianca(pac, {**base, "cv_todos": 0.40}, params)[0] == "B"
    assert confianca(pac, {**base, "cv_todos": 0.60}, params)[0] == "C"
    # sem dissidência e com consenso de ≥ 3 analistas: A; método principal dissidente ⇒ no máximo B
    limpo = {"tem_alvo": True, "n_metodos": 3, "cv": 0.05, "cv_todos": 0.05, "n_eps": 8, "eps1_consenso": True,
             "portoes": [], "dissidencia": []}
    assert confianca(pac, limpo, params)[0] == "A"
    assert confianca(pac, {**limpo, "principal_dissidente": True, "metodo_principal": "fcff"}, params)[0] == "B"
    assert confianca(pac, {**limpo, "n_eps": 2}, params)[0] == "B"
