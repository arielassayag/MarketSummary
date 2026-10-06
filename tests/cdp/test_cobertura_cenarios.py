"""Cenários centrados no caso-base, FCFF ancorado no fluxo de caixa observado e texto do modelo
aberto (substituições que fecham a conta, pt-BR, sem jargão). DADOS SIMULADOS, sem rede."""

from __future__ import annotations

import re
from datetime import date

import numpy as np
import pytest

from cdp.cobertura import metodos as M
from cdp.cobertura.fontes import coletar
from cdp.cobertura.motor import executar
from cdp.cobertura.parametros import carregar_parametros
from cdp.data.synthetic import make_synthetic_market

D = date(2026, 10, 8)
MENOS = "−"


@pytest.fixture(scope="module")
def run():
    md = make_synthetic_market(seed=7, as_of=D)
    params = carregar_parametros()
    dados = coletar(md, D, list(md.universe.issuers.index), list(md.universe.lines.index), ["ILF", "EWZ", "EWW"])
    return md, params, dados, executar(md, dados, params, D)


BASE = dict(receita0=1000.0, g1=0.06, g2=0.05, g_term=0.04, phi=0.9, margem=0.18, imposto=0.3, roic0=0.08,
            wacc=0.10, anos=10, ronic_final=0.12, reinvest_obs=0.40)


def test_fcff_scenario_is_mean_preserving_for_growth_and_margin_shocks():
    base = M.fcff_tres_estagios(**BASE)
    rng = np.random.default_rng([21, 4])
    z = rng.standard_normal(4000)
    dg = 0.03 * np.concatenate([z, -z])                      # antitéticos: média exatamente zero
    dm = 0.02 * np.concatenate([z[::-1], -z[::-1]])
    cen = M.CenarioFCFF(g1=BASE["g1"] + dg, g2=BASE["g2"] + dg, g_term=np.full(8000, BASE["g_term"]),
                        wacc=np.full(8000, BASE["wacc"]), d_margem=dm)
    res = M.fcff_tres_estagios(**BASE, cenario=cen)
    assert float(np.mean(res.ev)) == pytest.approx(float(base.ev), rel=1e-9)
    # choque nulo reproduz o caso-base
    zero = M.CenarioFCFF(g1=BASE["g1"], g2=BASE["g2"], g_term=BASE["g_term"], wacc=BASE["wacc"])
    assert float(M.fcff_tres_estagios(**BASE, cenario=zero).ev) == pytest.approx(float(base.ev), rel=1e-12)


def test_commodity_shock_is_transitory_and_never_reaches_the_perpetuity():
    base = M.fcff_tres_estagios(**BASE)
    w = M.perfil_transitorio(10, 3, 5)
    assert list(w[:5]) == [1.0, 1.0, 1.0, 0.5, 0.0] and not w[5:].any()
    c = np.array([0.2, -0.2])
    cen = M.CenarioFCFF(g1=BASE["g1"], g2=BASE["g2"], g_term=BASE["g_term"], wacc=BASE["wacc"],
                        d_margem_trans=w[:, None] * c[None, :])
    res = M.fcff_tres_estagios(**BASE, cenario=cen)
    assert np.allclose(res.pv_terminal, float(base.pv_terminal))
    assert float(np.mean(res.ev)) == pytest.approx(float(base.ev), rel=1e-12)


def test_reinvestment_anchored_on_observed_cash_flow_then_converges():
    res = M.fcff_tres_estagios(**BASE)
    assert res.reinvest[0] == pytest.approx(0.40) and res.reinvest[1] == pytest.approx(0.40)
    assert float(res.fcff[0]) == pytest.approx(float(res.nopat[0]) * 0.60)
    # ano T: g_{T+1} ÷ RONIC_final
    assert res.reinvest[-1] == pytest.approx(BASE["g_term"] / BASE["ronic_final"])
    # reinvestimento observado acima do teto é limitado e sinalizado
    alto = M.fcff_tres_estagios(**{**BASE, "reinvest_obs": 1.4})
    assert alto.reinvest[0] == pytest.approx(0.95) and 1 in alto.limite_atingido


def test_simulation_is_centred_on_the_house_case(run):
    _, _, _, ex = run
    p50, gap = [], []
    for m in ex.modelos.values():
        if not m.get("tem_alvo") or not m.get("tp_pessimista"):
            continue  # piso de zero do patrimônio atingido: valor de opção legítimo
        p50.append(m["tp_mediana_mc"] / m["tp"] - 1)
        # PWR sem o piso de zero (base do alpha) contra o caso-base: só convexidade, em proporção do
        # valor (1 + ETR)
        gap.append((m["pwr"] - m["etr"]) / (1 + m["etr"]))
    p50, gap = np.abs(np.array(p50)), np.abs(np.array(gap))
    assert len(p50) >= 30
    assert np.median(p50) <= 0.01 and p50.max() <= 0.05
    assert np.median(gap) <= 0.02 and gap.max() <= 0.05


def test_rating_never_rests_on_the_simulation_alone(run):
    _, _, _, ex = run
    for m in ex.modelos.values():
        if m.get("rating") == "Compra":
            assert m["etr"] >= m["custo_capital"]["ke"] and m["upside"] > 0
        if m.get("rating") == "Venda":
            assert m["etr"] <= m["custo_capital"]["ke"] - 0.05 + 1e-12


NUM = r"[−-]?\(?[−-]?(?:R\$|US\$|[A-Z]{3})?\s?[−-]?\d[\d.]*(?:,\d+)?(?:%|x| p\.p\.| bi| mi| tri)?\)?"


def test_open_model_substitutions_close_the_account(run):
    _, _, _, ex = run
    for iid, reg in ex.registros.items():
        for p in reg.passos:
            sub = p["substituicao"]
            for proibido in ("sha256", "fisher(", f"{MENOS} -", f"+ {MENOS}", f"{MENOS} {MENOS}", "+ -", "- -",
                             "[demonstrativos]", "resultado_financeiro", "income_stmt", "balance_sheet"):
                assert proibido not in sub, (iid, p["id"], sub)
            if p["unidade"] == "texto" or p["resultado"] is None:
                continue
            assert sub.endswith("= " + p["resultado_texto"]), (iid, p["id"], sub)
            for a, b in re.findall(r"= (" + NUM + r") = (" + NUM + r")(?:$|[;\s])", sub):
                assert a.strip() == b.strip(), (iid, p["id"], sub)
    # contagens com separador de milhar e a semente descrita sem jargão
    mc = next(p for p in next(iter(ex.registros.values())).passos if p["id"] == "cenarios.mc")
    assert "2.000" in mc["substituicao"] and "semente fixa por emissor e data" in mc["premissas"]


def test_regression_step_shows_issuer_regressors(run):
    _, _, _, ex = run
    achou = False
    for reg in ex.registros.values():
        for p in reg.passos:
            if p["id"].endswith(".multiplo"):
                achou = True
                assert "×" in p["substituicao"] and "R²" in p["formula"]
    assert achou


def test_synthetic_models_never_name_real_sources(run):
    md, params, _, ex = run
    from cdp.cobertura.motor import modelo_json

    for iid in ex.modelos:
        m = modelo_json(ex, iid, params)
        texto = repr(m["passos"]) + repr(m["insumos"])
        for real in ("Yahoo", "CVM", "SEC ", "iShares", "ISHARES", "Global X", "GLOBALX"):
            assert real not in texto, (iid, real)
    for e in ex.etfs.values():
        assert e["fonte_composicao"]["fonte"] in ("SIMULADO", "CODIGO")
        assert "iShares" not in repr(e["passos"])
