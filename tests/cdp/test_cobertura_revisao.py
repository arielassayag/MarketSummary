"""Revisão da cobertura (2026-10.3): testes das correções da revisão do A2b (DADOS SIMULADOS, sem rede).

Retorno extremo com corroboração em toda a faixa de aviso (G11); bottom-up dos ETFs só com alvos
citáveis e portão de concentração (E5); custo da dívida pela cobertura de juros estimada em base
dólar, ``kd ≤ ke``; ajuste de porte pelo patrimônio contábil e só quando significativo; combinação
robusta monótona (G18 limita, não retira) e dissidência na dispersão; payout dos acionistas pela
mediana dos payouts anuais; lucro residual e dividendos em termos reais; visão da casa nas holdings;
ajuste de nível do país (ponto fixo, grupo regional, norma do ROE independente) e o indicador de
viés; receita de construção das concessões; consenso de poucos analistas; perpetuidade do lucro
residual como impressa; principal de arrendamentos no fluxo observado; proveniência; consolidado ×
individual por período e demonstrações defasadas (G19); calendário do consenso; prêmio implícito
sem recompras ausentes; conferência cruzada das participações; contas suplementares da CVM."""

from __future__ import annotations

import copy
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from cdp.cobertura import metodos as M
from cdp.cobertura.contexto import (
    custos_capital,
    fundamentos,
    inclinacao_porte,
    premio_implicito,
    reinvestimento_observado,
)
from cdp.cobertura.etf import _elegivel_bu
from cdp.cobertura.fontes import _fatos_suplementares, coletar
from cdp.cobertura.insumos import (
    Demonstrativos,
    _Pacote,
    _participacao_conferida,
    _receita_construcao,
    fim_exercicio_consenso,
)
from cdp.cobertura.modelo import Avaliador
from cdp.cobertura.motor import executar, tp_deterministico, vies_modelo, visao_casa
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.qualidade import _g19, portoes_etf
from cdp.data.synthetic import make_synthetic_market

D = date(2026, 10, 8)


@pytest.fixture(scope="module")
def params():
    return carregar_parametros()


@pytest.fixture(scope="module")
def run(params):
    md = make_synthetic_market(seed=11, as_of=D)
    dados = coletar(md, D, list(md.universe.issuers.index), list(md.universe.lines.index), ["ILF", "EWZ", "EWW"])
    return md, executar(md, dados, params, D)


# ============================================================ G11 e ETFs

def test_etf_bottom_up_uses_only_citable_ab_targets(params, run):
    ec = params.sec("etf")
    ok = {"tem_alvo": True, "rating": "Compra", "confianca": "B", "portoes": []}
    assert _elegivel_bu(ok, ec)[0]
    assert not _elegivel_bu({**ok, "confianca": "C"}, ec)[0]
    assert not _elegivel_bu({**ok, "portoes": [{"codigo": "G11", "status": "aviso"}]}, ec)[0]
    assert not _elegivel_bu({**ok, "portoes": [{"codigo": "G16", "status": "aviso"}]}, ec)[0]
    assert not _elegivel_bu({**ok, "rating": "Em revisão"}, ec)[0]
    _, ex = run
    for e in ex.etfs.values():
        for x in e.get("posicoes", []):
            if x.get("imputado") or not x.get("issuer_id"):
                continue
            m = ex.modelos[x["issuer_id"]]
            assert m["confianca"] in ("A", "B") and m["rating"] in ("Compra", "Neutro", "Venda")
        assert any(p["codigo"] == "E5" for p in e["portoes"])


def test_etf_concentration_gate():
    e = {"preco_alvo": 10.0, "preco": 9.0, "retorno_esperado": 0.1,
         "concentracao_bu": {"emissor": "X", "contribuicao": 0.08, "limite": 0.05}}
    g = {p["codigo"]: p for p in portoes_etf(e, carregar_parametros())}
    assert g["E5"]["status"] == "aviso" and "X" in g["E5"]["detalhe"]
    e["concentracao_bu"]["contribuicao"] = 0.02
    assert {p["codigo"]: p for p in portoes_etf(e, carregar_parametros())}["E5"]["status"] == "ok"


# ============================================================ custo de capital

def test_cost_of_debt_never_above_cost_of_equity(run):
    _, ex = run
    n = 0
    for m in ex.modelos.values():
        cc = m["custo_capital"]
        if cc.get("kd") is not None:
            n += 1
            assert cc["kd"] <= cc["ke"] + 1e-12
    assert n > 10


def test_size_slope_uses_book_equity_and_only_when_significant(params):
    rng = np.random.default_rng(3)
    x = rng.normal(0.0, 1.0, 80)
    forte = [{"pais": "BR", "setor": "S", "roe_hist": 0.12 + 0.02 * a + rng.normal(0, 0.005), "ln_pl_usd": a,
              "ln_mcap_usd": 0.0} for a in x]
    p = inclinacao_porte(forte, params)
    assert p["variavel"] == "ln_pl_usd" and p["significativa"] and 0.015 < p["b"] < 0.025
    ruido = [{"pais": "BR", "setor": "S", "roe_hist": 0.12 + rng.normal(0, 0.05), "ln_pl_usd": a,
              "ln_mcap_usd": 3 * a} for a in x]
    p = inclinacao_porte(ruido, params)
    assert p["b"] == 0.0 and not p["significativa"] and p["ic95"][0] < 0 < p["ic95"][1]


def test_size_term_and_norm_ignore_the_country_level_adjustment(run):
    _, ex = run
    n = 0
    for m in ex.modelos.values():
        pr, cc = m.get("persistencia_roe"), m["custo_capital"]
        if not pr or pr.get("norma") is None:
            continue
        n += 1
        porte = (pr.get("porte") or {}).get("ajuste") or 0.0
        assert pr["norma"] == pytest.approx(cc["ke_sem_calibracao"] + pr["spread"] + porte, abs=2e-6)
    assert n >= 20


def test_raising_the_cost_of_debt_never_raises_the_target(run, params):
    _, ex = run
    alvos = []
    for iid, m in ex.modelos.items():
        cc = m["custo_capital"]
        if m.get("tem_alvo") and cc.get("kd") is not None and (cc.get("peso_divida") or 0) > 0.2 \
                and any(d["m"].startswith("fcff") and d.get("valor") for d in m["metodos"]):
            alvos.append(iid)
    assert alvos
    for iid in alvos[:6]:
        tps = []
        for k in (1.0, 2.0, 4.0, 8.0):
            p2 = copy.deepcopy(params)
            p2.cc["spread_sintetico"] = [[a, r, s * k] for a, r, s in p2.cc["spread_sintetico"]]
            p2.cc["spread_credito_corporativo"] = params.cc["spread_credito_corporativo"] * k
            tps.append(tp_deterministico(ex.pacotes[iid], ex.contexto, p2, ex.rf["valor"]))
        assert all(b <= a + 1e-9 for a, b in zip(tps, tps[1:], strict=False)), (iid, tps)


# ============================================================ G18: limita, não retira

def _stub(params, valores: dict[str, float], preco: float) -> Avaliador:
    from cdp.cobertura.passos import Registro

    av = Avaliador.__new__(Avaliador)
    av.params, av.pac, av.moeda, av.reg = params, {"preco": preco, "arquetipo": "corporativo"}, "BRL", Registro()
    av.metodos = {m: {"m": m, "peso": w, "valor": v} for m, (v, w) in valores.items()}
    return av


def test_discrepant_method_is_limited_monotonically_not_dropped(params):
    av = _stub(params, {"fcff": (40.0, 0.5), "rim": (10.0, 0.25), "multiplo_justificado": (10.5, 0.25)}, 9.0)
    av._excluir_discrepante()
    d = av.discrepante
    assert d["metodo"] == "fcff" and d["limitado"] and d["valor_limitado"] == pytest.approx(3 * 10.25)
    assert av.metodos["fcff"]["valor_bruto"] == 40.0 and av.metodos["fcff"]["limitado"]
    v0s = []
    for v in (20.0, 30.0, 40.0, 60.0, 90.0):
        vals = {"fcff": np.asarray(v), "rim": np.asarray(10.0), "multiplo_justificado": np.asarray(10.5)}
        v0s.append(float(av.combinar(vals)))
    assert all(b >= a - 1e-12 for a, b in zip(v0s, v0s[1:], strict=False))   # monótono no valor do método
    cv, dis = av.dispersao_todos()
    assert cv > 0.5 and dis[0]["tipo"] == "limitado"   # a dissidência entra na dispersão pelo valor bruto


def test_discrepant_method_on_the_price_side_or_without_consensus_is_kept(params):
    av = _stub(params, {"fcff": (2.0, 0.5), "rim": (10.0, 0.25), "multiplo_justificado": (10.5, 0.25)}, 3.0)
    av._excluir_discrepante()
    assert av.discrepante["lado_preco"] and not av.discrepante["limitado"]
    assert av.metodos["fcff"]["valor"] == 2.0
    av = _stub(params, {"fcff": (70.0, 0.5), "rim": (10.0, 0.25), "multiplo_justificado": (20.0, 0.25)}, 9.0)
    av._excluir_discrepante()
    assert not av.discrepante["limitado"] and av.discrepante["cv_demais"] > 0.10


# ============================================================ payout dos acionistas

def _stub_payout(pac: dict) -> Avaliador:
    av = Avaliador.__new__(Avaliador)
    av.pac, av.k_luc, av.moeda, av.fontes, av.fund = pac, "t.lucro_liquido_controladores", "BRL", {}, {}
    av.eps1 = av.eps_ttm = None
    av.avisos = []
    return av


def test_payout_uses_shareholder_dividends_and_ignores_one_off_years():
    # DFC consolidada com dividendos a minoritários de controladas (4,95 bi) e um ano extraordinário
    pac = {"unidades": 1.0e9, "t.lucro_liquido_controladores": 1.0e9, "t.dividendos_pagos": -4.95e9,
           "dps_12m": 1.58, "dps_fonte": "proventos",
           "dps_anual": {"2023": 0.40, "2024": 0.50, "2025": 2.40},
           "historico": {"lucro_liquido_controladores": {"2023": 1.0e9, "2024": 1.0e9, "2025": 1.0e9}}}
    k, sub, form, prem, _ = _stub_payout(pac)._payout()
    assert k == pytest.approx(0.50) and "mediana" in form and "DFC consolidada" in prem
    # ano sem proventos por ação mas com dividendos na DFC: lacuna da série ⇒ DFC do exercício
    pac2 = {**pac, "dps_anual": {"2023": 0.40, "2024": 0.0, "2025": 0.45},
            "historico": {**pac["historico"], "dividendos_pagos": {"2024": -0.42e9}}}
    k2 = _stub_payout(pac2)._payout()[0]
    assert k2 == pytest.approx(0.42)


# ============================================================ termos reais e perpetuidade do lucro residual

def test_real_terms_rim_and_ddm_match_nominal_with_matched_assumptions():
    pi, ke, b0, k, kf = 0.04, 0.12, 10.0, 0.5, 0.6
    r1, r2, ra = 0.18, 0.16, 0.13
    nom = M.rim_gls(b0, r1, r2, ra, ke, k, 12, kf, omega=0.7)
    real = lambda x: (1 + x) / (1 + pi) - 1  # noqa: E731
    rea = M.rim_gls(b0, real(r1), real(r2), real(ra), real(ke), k, 12, kf, omega=0.7, inflacao=pi)
    # anos explícitos idênticos (o patrimônio real é o nominal deflacionado)
    assert float(rea.pv_explicito) == pytest.approx(float(nom.pv_explicito), rel=1e-10)
    for t in range(13):
        assert float(rea.b[t]) * (1 + pi) ** t == pytest.approx(float(nom.b[t]), rel=1e-10)
    # perpetuidade real constante = nominal crescendo à inflação
    b_t = float(nom.b[-1])
    term_nom = (float(nom.roe[-1]) - ke) * b_t / ((ke - pi) * (1 + ke) ** 12)
    term_rea = (real(float(nom.roe[-1])) - real(ke)) * float(rea.b[-1]) / (real(ke) * (1 + real(ke)) ** 12)
    assert term_rea == pytest.approx(term_nom, rel=1e-10)
    # dividendos: DPS_1 em moeda de hoje, g e ke reais ⇒ o mesmo valor do nominal
    d1, g1, g = 1.0, 0.08, 0.05
    vn = float(M.ddm_dois_estagios(d1, g1, g, ke, 5))
    vr = float(M.ddm_dois_estagios(d1 / (1 + pi), real(g1), real(g), real(ke), 5))
    assert vr == pytest.approx(vn, rel=1e-12)


def test_rim_terminal_is_the_printed_formula():
    ke, om = 0.12, 0.85
    res = M.rim_gls(10.0, 0.30, 0.28, 0.18, ke, 0.4, 12, 0.6, omega=om)
    b, rt = float(res.b[-1]), float(res.roe[-1])
    alvo = (0.18 - ke) * b / (ke * (1 + ke) ** 12)
    cauda = (rt - 0.18) * b * om / ((1 + ke - om) * (1 + ke) ** 12)
    assert float(res.pv_terminal) == pytest.approx(alvo + cauda, rel=1e-12)
    assert float(res.valor) == pytest.approx(10.0 + float(res.pv_explicito) + alvo + cauda, rel=1e-12)


def test_open_model_rim_steps_reproduce_v0(run):
    _, ex = run
    n = 0
    for reg in ex.registros.values():
        ps = {p["id"]: p for p in reg.passos}
        for m in ("rim", "rim_real"):
            if f"metodo.{m}" in ps and f"metodo.{m}.perpetuidade" in ps:
                n += 1
                assert ps[f"metodo.{m}.perpetuidade"]["resultado"] is not None
    assert n >= 10


# ============================================================ holdings, ajuste de nível e viés

def test_holding_inherits_the_house_view_of_citable_stakes(params):
    sp = {"partes": [{"emissor": "A", "fracao": 0.5, "valor_participacao": 100.0},
                     {"emissor": "B", "fracao": 0.5, "valor_participacao": 300.0}]}
    pacs = {"A": {"pais": "BR", "preco": 10.0, "pit_ok": True, "status_moeda": "ok"},
            "B": {"pais": "BR", "preco": 10.0, "pit_ok": True, "status_moeda": "ok"}}
    mods = {"A": {"tem_alvo": True, "v0": 12.0, "n_metodos": 2, "cv": 0.1, "n_eps": 5, "eps1_consenso": True,
                  "portoes": []},
            "B": {"tem_alvo": True, "v0": 5.0, "n_metodos": 1, "cv": None, "portoes": []}}   # B: método único ⇒ C
    v = visao_casa({"soma_partes": sp}, pacs, mods, params)
    assert v["fator"] == pytest.approx((100 * 1.2 + 300 * 1.0) / 400)
    assert "confiança C" in v["partes"][1]["motivo"]


def test_model_bias_monitor_uses_the_uncalibrated_level(params):
    ctx = {"calibracao_pais": {"BR": {"delta": -0.015, "limitado": True, "mediana_v_p_sem_calibracao": 0.80,
                                      "grupo": "BR", "n": 100},
                               "MX": {"delta": 0.0, "limitado": False, "mediana_v_p_sem_calibracao": 0.99,
                                      "grupo": "MX", "n": 40},
                               "PE": {"delta": -0.002, "limitado": False, "mediana_v_p_sem_calibracao": 0.4,
                                      "grupo": "regional", "n": 3}}}
    v = vies_modelo(ctx, params)
    assert v["paises"]["BR"]["mediana_v_p_sem_ajuste"] == 0.80
    assert any("BR" in a and "limite" in a for a in v["alertas"]) and any("viés" in a and "BR" in a for a in v["alertas"])
    assert not any("MX" in a or "PE" in a for a in v["alertas"])


def test_calibration_step_is_labelled_as_model_bias_not_premium(run):
    _, ex = run
    for reg in ex.registros.values():
        for p in reg.passos:
            if p["id"] == "ke.calibracao_pais":
                assert "não prêmio de risco" in p["titulo"]
                return
    pytest.skip("nenhum país com ajuste de nível no universo sintético")


# ============================================================ insumos

def test_construction_revenue_is_stripped_when_it_reconciles_consensus(params):
    # Equatorial (CVM DVA 2025): receita de construção de R$ 10,71 bi; consenso do ano 1 de R$ 43,2 bi
    pk = _Pacote()
    pk.v.update({"moeda": "BRL", "arquetipo": "utilidade_regulada"})
    itens = {"receita": 53.95e9, "receita_construcao": 10.71e9}
    razao = _receita_construcao(pk, params, itens, 43.2e9, 53.95e9, 1.0, 43.2e9 / 53.95e9)
    assert razao == pytest.approx(43.2 / 43.24, rel=1e-6)
    assert pk.v["t.receita"] == pytest.approx(43.24e9) and pk.v["receita_sem_construcao"]
    assert itens["receita"] == pytest.approx(43.24e9)
    # sem a receita de construção e crescimento de consenso de −35%: não usado (lacuna)
    pk2 = _Pacote()
    pk2.v.update({"moeda": "BRL", "arquetipo": "utilidade_regulada"})
    assert _receita_construcao(pk2, params, {"receita": 4.48e9}, 2.9e9, 4.48e9, 1.0, 2.9 / 4.48) is None
    assert pk2.v["receita_consenso_rejeitada"] and pk2.lacunas[0]["insumo"] == "g_receita_fy1"


def test_thin_consensus_falls_back_to_trailing_earnings(run, params):
    _, ex = run
    iid = next(i for i, p in ex.pacotes.items() if p.get("eps_fy1") and p.get("eps_ttm") and p.get("bvps")
               and not p["financeira"])
    pac = copy.deepcopy(ex.pacotes[iid])
    pac["consenso"] = {**(pac.get("consenso") or {}), "n_eps": 1.0}
    av = Avaliador(pac, ex.contexto, params, ex.rf["valor"], {})
    assert av.consenso_raso and av.eps1 == pytest.approx(pac["eps_ttm"])
    assert any(p["id"] == "dir.consenso_raso" for p in av.reg.passos)


def test_observed_reinvestment_subtracts_lease_principal():
    hist = {"cfo": {"2023": 100.0, "2024": 110.0, "2025": 120.0}, "capex": {"2023": -40.0, "2024": -45.0, "2025": -50.0},
            "ebit": {"2023": 100.0, "2024": 100.0, "2025": 100.0},
            "arrendamentos_pagos": {"2023": 10.0, "2024": 10.0, "2025": 10.0}}
    r = reinvestimento_observado({"historico": hist}, 0.3)
    assert r["arrendamentos"] == pytest.approx(30.0)
    assert r["rr"] == pytest.approx(1 - (330 - 135 - 30) / 210)
    sem = reinvestimento_observado({"historico": {k: v for k, v in hist.items() if k != "arrendamentos_pagos"}}, 0.3)
    assert sem["arrendamentos"] is None and sem["rr"] == pytest.approx(1 - (330 - 135) / 210)


def test_external_sources_do_not_borrow_the_config_hash(params):
    f = params.fonte("damodaran_ctryprem")
    assert f["sha256"] is None and "transcrito" in f["documento"]
    assert params.fonte_config("x")["sha256"] == params.arquivos["valuation.yaml"]
    for a in params.arquetipos.values():
        if a.fim_concessao is not None:
            assert a.fim_concessao_fonte and "http" in a.fim_concessao_fonte, a.issuer_id


def test_individual_statements_newer_than_consolidated_are_used():
    rows = []
    for ano, cons in ((2022, True), (2023, True), (2024, False), (2025, False)):
        for item, v in (("patrimonio_liquido", 100.0 + ano - 2022), ("lucro_liquido", 10.0 + ano - 2022)):
            rows.append({"issuer_id": "X", "demonstrativo": "BP" if "patr" in item else "DRE", "freq": "A",
                         "period_end": f"{ano}-12-31", "item": item, "value": v, "consolidado": cons,
                         "data_publicacao": f"{ano + 1}-03-01", "fonte": "CVM", "documento": f"DFP {ano}"})
    rows.append({"issuer_id": "X", "demonstrativo": "BP", "freq": "Q", "period_end": "2026-06-30",
                 "item": "patrimonio_liquido", "value": 104.0, "consolidado": False,
                 "data_publicacao": "2026-08-10", "fonte": "CVM", "documento": "ITR 2T26"})
    # período com as duas bases: o consolidado prevalece
    rows.append({"issuer_id": "X", "demonstrativo": "BP", "freq": "A", "period_end": "2023-12-31",
                 "item": "patrimonio_liquido", "value": 999.0, "consolidado": False,
                 "data_publicacao": "2024-03-01", "fonte": "CVM", "documento": "DFP 2023 ind"})
    dem = Demonstrativos(pd.DataFrame(rows), "X")
    v, row = dem.valor("patrimonio_liquido")
    assert v == 104.0 and pd.Timestamp(row["period_end"]) == pd.Timestamp("2026-06-30")
    assert dem.anual("patrimonio_liquido")[2023] == 101.0
    assert dem.valor("lucro_liquido")[0] == 13.0


def test_stale_statements_gate():
    p = carregar_parametros()
    assert _g19({"idade_balanco_dias": 98, "idade_fluxos_dias": 98}, p)["status"] == "ok"
    assert _g19({"idade_balanco_dias": 320, "idade_fluxos_dias": 98}, p)["status"] == "aviso"
    assert _g19({"idade_balanco_dias": 644, "idade_fluxos_dias": 644}, p)["status"] == "bloqueio"
    assert _g19({}, p)["status"] == "nao_aplicavel"


def test_consensus_calendar_follows_the_fiscal_year_end():
    fye, nota = fim_exercicio_consenso(pd.Timestamp("2025-12-31"), date(2026, 10, 6))
    assert fye == pd.Timestamp("2025-12-31") and nota is None
    # demonstrações anuais de 2025 ausentes 279 dias depois: o consenso já rolou (sinalizado)
    fye, nota = fim_exercicio_consenso(pd.Timestamp("2024-12-31"), date(2026, 10, 6))
    assert fye == pd.Timestamp("2025-12-31") and "não encontradas" in nota
    # dentro do prazo de entrega: o exercício recém-encerrado ainda é o "ano 1"
    assert fim_exercicio_consenso(pd.Timestamp("2024-12-31"), date(2025, 3, 15))[0] == pd.Timestamp("2024-12-31")
    # exercício encerrado em junho: 98 dias depois do encerramento ainda no prazo; 154 dias depois, já rolou
    assert fim_exercicio_consenso(pd.Timestamp("2025-06-30"), date(2026, 10, 6))[0] == pd.Timestamp("2025-06-30")
    assert fim_exercicio_consenso(pd.Timestamp("2025-06-30"), date(2026, 12, 1))[0] == pd.Timestamp("2026-06-30")


def test_calendarization_flag_reaches_the_context():
    p = {"preco": 10.0, "bvps": 5.0, "eps_fy1": 1.0, "eps_fy2": 2.0, "fim_exercicio": "2025-12-31",
         "as_of": "2026-07-01", "financeira": False}
    assert fundamentos(p, calendarizar=False)["pe"] == pytest.approx(10.0)
    assert fundamentos(p, calendarizar=True)["pe"] < 10.0


def test_implied_premium_skips_missing_buybacks_and_honours_n_min(run, params):
    _, ex = run
    kes = custos_capital(ex.pacotes, ex.contexto, params, ex.rf["valor"], ex.rf["fonte"])
    sem = {i: {**p, "t.recompras": None} for i, p in ex.pacotes.items()}
    assert premio_implicito(sem, [], kes, params, ex.rf["valor"]) == {}
    p2 = copy.deepcopy(params)
    p2.cc["premio_implicito_pais"]["n_min"] = 10_000
    assert premio_implicito(ex.pacotes, [], kes, p2, ex.rf["valor"]) == {}


def test_stake_cross_check_with_the_investee_filing():
    ok = {"conferido": True, "url": "http://x", "data_publicacao": "2026-08-12", "data_referencia": "2026-08-12",
          "documento": "FRE", "fracao": 0.6093, "fracao_investida": 0.53705, "documento_investida": "FRE da Movida"}
    c, txt = _participacao_conferida(ok, date(2026, 10, 6), tolerancia=0.01)
    assert not c and "conferência cruzada falhou" in txt
    assert _participacao_conferida({**ok, "fracao_investida": 0.605}, date(2026, 10, 6), tolerancia=0.01)[0]
    assert _participacao_conferida(ok, date(2026, 10, 6), tolerancia=0.10)[0]


def test_supplementary_cvm_accounts():
    idx = pd.DataFrame({"CNPJ_CIA": ["1"], "DT_REFER": ["2025-12-31"], "VERSAO": ["1"], "DT_RECEB": ["2026-03-01"],
                        "LINK_DOC": ["http://cvm/1"]})

    def lin(cd, ds, v, tab):
        return {"CNPJ_CIA": "1", "DT_REFER": "2025-12-31", "VERSAO": "1", "MOEDA": "REAL", "ESCALA_MOEDA": "MIL",
                "ORDEM_EXERC": "ÚLTIMO", "DT_INI_EXERC": "2025-01-01", "DT_FIM_EXERC": "2025-12-31", "CD_CONTA": cd,
                "DS_CONTA": ds, "VL_CONTA": str(v)}

    dfc = pd.DataFrame([lin("6.03.05", "Pagamento de arrendamentos", -100, "DFC"),
                        lin("6.03.06", "Juros pagos sobre arrendamentos", -30, "DFC"),
                        lin("6.03.07", "Amortização de arrendamento mercantil", -20, "DFC")])
    dva = pd.DataFrame([lin("7.01.02", "Outras Receitas", 500, "DVA"),
                        lin("7.01.02.01", "Receita de construção", 400, "DVA"),
                        lin("7.01.03", "Receitas refs. à Construção de Ativos Próprios", 0, "DVA")])
    vazio = pd.DataFrame(columns=dfc.columns)
    tabs = {"index": idx, "DFC_MI_con": dfc, "DFC_MI_ind": vazio, "DFC_MD_con": vazio, "DFC_MD_ind": vazio,
            "DVA_con": dva, "DVA_ind": vazio}
    f = _fatos_suplementares(tabs, "DFP").set_index("item")
    assert f.loc["arrendamentos_pagos", "value"] == pytest.approx(120_000.0)    # sem os juros, em R$
    assert f.loc["receita_construcao", "value"] == pytest.approx(400_000.0)     # filha sem dupla contagem
    assert bool(f.loc["arrendamentos_pagos", "consolidado"])


def test_vida_finita_text_prints_integer_years(run, params):
    _, ex = run
    iid = next(i for i, p in ex.pacotes.items() if not p["financeira"] and p.get("t.receita") and p.get("divida_liquida")
               is not None and p.get("minoritarios") is not None and ex.modelos[i].get("tem_alvo"))
    pac = {**copy.deepcopy(ex.pacotes[iid]), "arquetipo": "concessao", "fim_concessao": 2058.0}
    av = Avaliador(pac, ex.contexto, params, ex.rf["valor"], {})
    av.avaliar()
    passo = next(p for p in av.reg.passos if p["id"] == "metodo.fcff_vida_finita")
    assert "fluxos até 2058;" in passo["premissas"] and "2058.0" not in passo["premissas"]
    _ = SimpleNamespace
