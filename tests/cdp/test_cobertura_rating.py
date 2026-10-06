"""Regra de rating da cobertura: limiares por incerteza, guardas, histerese, confiança,
"Em revisão" e "Sem preço-alvo"."""

from __future__ import annotations

import pytest

import cdp.cobertura.rating as R
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.rating import aplicar, classes_incerteza, confianca, grupo_pares


@pytest.fixture(scope="module")
def params():
    return carregar_parametros()


@pytest.fixture
def media(monkeypatch):
    """Fixa a classe de incerteza em "Média" (limiar ±10%) para testar só a regra de rating."""
    monkeypatch.setattr(R, "classes_incerteza", lambda mods: ({i: "Média" for i in mods}, []))


def _pac(pais="BR", setor="Utilities", pit=True, moeda="ok"):
    return {"pais": pais, "setor": setor, "pit_ok": pit, "status_moeda": moeda}


def _mod(alpha, largura=0.5, n=3, cv=0.10, portoes=None, tem=True):
    return {"tem_alvo": tem, "alpha": alpha, "largura_cenarios": largura, "n_metodos": n, "cv": cv,
            "portoes": portoes or [], "motivo_sem_alvo": None if tem else "nenhum método"}


def _universo(alphas, larguras=None, **kw):
    """Universo de teste; larguras padrão 0,1…0,8 + o alvo (último) em 0,4 ⇒ incerteza Média."""
    n = len(alphas)
    if larguras is None:
        base = [0.1, 0.2, 0.3, 0.5, 0.6, 0.7, 0.8]
        larguras = [base[i % len(base)] for i in range(n - 1)] + [0.4]
    pacs = {f"I{i:02d}": _pac(**kw) for i in range(n)}
    mods = {f"I{i:02d}": _mod(a, w) for i, (a, w) in enumerate(zip(alphas, larguras, strict=True))}
    return pacs, mods


def test_compra_and_venda_thresholds(params, media):
    # mediana dos α = 0 ⇒ α_rel = α; limiar ±10% (incerteza média)
    pacs, mods = _universo([0.0, 0.0, 0.0, 0.0, 0.25, -0.25, 0.05, -0.05, 0.0, 0.12, -0.12])
    aplicar(mods, pacs, params)
    assert mods["I04"]["rating"] == "Compra"
    assert mods["I05"]["rating"] == "Venda"
    assert mods["I06"]["rating"] == "Neutro" and mods["I07"]["rating"] == "Neutro"
    assert mods["I09"]["rating"] == "Compra" and mods["I10"]["rating"] == "Venda"


def test_threshold_scales_with_uncertainty(params):
    larguras = [0.1, 0.1, 0.3, 0.1, 0.5, 0.6, 0.7, 0.8, 1.5, 1.5]
    alphas = [0.0, 0.0, 0.0, 0.09, -0.09, 0.0, 0.0, 0.0, 0.16, -0.16]
    pacs = {f"I{i:02d}": _pac() for i in range(10)}
    mods = {f"I{i:02d}": _mod(a, w) for i, (a, w) in enumerate(zip(alphas, larguras, strict=True))}
    aplicar(mods, pacs, params)
    assert mods["I03"]["incerteza"] == "Baixa" and mods["I03"]["rating"] == "Compra"   # 9% ≥ 8%
    assert mods["I08"]["incerteza"] == "Muito alta" and mods["I08"]["rating"] == "Neutro"  # 16% < 20%


def test_absolute_guards(params, media):
    # α_rel alto mas α negativo ⇒ não é Compra; α_rel baixo mas α > −5 p.p. ⇒ não é Venda
    pacs, mods = _universo([-0.30, -0.30, -0.30, -0.30, -0.30, -0.05, 0.0, -0.45])
    aplicar(mods, pacs, params)
    assert mods["I05"]["alpha_rel"] == pytest.approx(0.25) and mods["I05"]["rating"] == "Neutro"
    assert mods["I06"]["rating"] == "Compra"  # α = 0 ≥ 0
    pacs, mods = _universo([0.30, 0.30, 0.30, 0.30, 0.30, 0.02])
    aplicar(mods, pacs, params)
    assert mods["I05"]["alpha_rel"] == pytest.approx(-0.28) and mods["I05"]["rating"] == "Neutro"


def test_hysteresis_keeps_existing_rating(params, media):
    pacs, mods = _universo([0.0, 0.0, 0.0, 0.0, 0.0, 0.09])
    aplicar(mods, pacs, params, anteriores={"I05": "Compra"})
    assert mods["I05"]["rating"] == "Compra"  # 9% ≥ 10% − 2 p.p.
    pacs, mods = _universo([0.0, 0.0, 0.0, 0.0, 0.0, 0.09])
    aplicar(mods, pacs, params)
    assert mods["I05"]["rating"] == "Neutro"  # sem histórico: limiar cheio


def test_confidence_gating_blocks_compra(params, media):
    pacs, mods = _universo([0.0, 0.0, 0.0, 0.0, 0.0, 0.30])
    mods["I05"]["n_metodos"] = 1  # método único ⇒ confiança C
    aplicar(mods, pacs, params)
    assert mods["I05"]["confianca"] == "C"
    assert mods["I05"]["rating"] == "Neutro" and "confiança C" in mods["I05"]["rating_motivo"]


def test_blocking_gate_and_no_target(params, media):
    pacs, mods = _universo([0.0, 0.0, 0.0, 0.0, 0.0, 0.30, 0.0])
    mods["I05"]["portoes"] = [{"codigo": "G9", "status": "bloqueio", "nome": "x", "detalhe": "y"}]
    mods["I06"] = _mod(None, tem=False)
    aplicar(mods, pacs, params)
    assert mods["I05"]["rating"] == "Em revisão"
    assert mods["I06"]["rating"] == "Sem preço-alvo" and mods["I06"]["confianca"] == "Insuficiente"


def test_confidence_levels(params):
    assert confianca(_pac(), _mod(0.0, n=3, cv=0.10), params)[0] == "A"
    assert confianca(_pac(moeda="fx_corrigido"), _mod(0.0, n=3, cv=0.10), params)[0] == "B"
    assert confianca(_pac(), _mod(0.0, n=2, cv=0.40), params)[0] == "B"
    assert confianca(_pac(), _mod(0.0, n=2, cv=0.60), params)[0] == "C"
    assert confianca(_pac(pais="AR"), _mod(0.0, n=3, cv=0.05), params)[0] == "C"
    aviso = [{"codigo": "G1", "status": "aviso", "nome": "x", "detalhe": "y"}]
    assert confianca(_pac(), _mod(0.0, n=3, cv=0.10, portoes=aviso), params)[0] == "C"
    info = [{"codigo": "G4", "status": "informativo", "nome": "x", "detalhe": "y"}]
    assert confianca(_pac(), _mod(0.0, n=3, cv=0.10, portoes=info), params)[0] == "A"
    hold = {**_pac(), "arquetipo": "holding", "soma_partes": {"conferido": False}}
    c, motivo = confianca(hold, _mod(0.0, n=3, cv=0.10), params)
    assert c == "C" and "não conferidas" in motivo


def test_peer_group_fallbacks():
    pacs = {f"BR{i}": {"pais": "BR", "setor": "Utilities"} for i in range(5)}
    pacs.update({f"MX{i}": {"pais": "MX", "setor": "Utilities"} for i in range(2)})
    todos = set(pacs)
    nome, ids = grupo_pares("BR0", pacs, todos, 5)
    assert nome == "BR × Utilities" and len(ids) == 5
    nome, ids = grupo_pares("MX0", pacs, todos, 5)
    assert nome.startswith("Utilities") and len(ids) == 7


def test_uncertainty_quartiles():
    mods = {f"I{i}": {"tem_alvo": True, "largura_cenarios": w} for i, w in enumerate([0.1, 0.2, 0.3, 0.4])}
    cl, q = classes_incerteza(mods)
    assert [cl[f"I{i}"] for i in range(4)] == ["Baixa", "Média", "Alta", "Muito alta"]
    assert len(q) == 3


def test_base_case_guards_block_simulation_only_ratings(params, media):
    # α_rel e α altos, mas o caso-base tem ETR abaixo do ke ⇒ Neutro, com a guarda no motivo
    pacs, mods = _universo([0.0, 0.0, 0.0, 0.0, 0.0, 0.25])
    mods["I05"].update({"etr": 0.05, "upside": 0.02, "custo_capital": {"ke": 0.12}})
    aplicar(mods, pacs, params)
    assert mods["I05"]["rating"] == "Neutro"
    assert "guarda de Compra" in mods["I05"]["rating_motivo"] and "abaixo do ke" in mods["I05"]["rating_motivo"]
    # Venda exige ETR do caso-base ≤ ke − 5 p.p.
    pacs, mods = _universo([0.0, 0.0, 0.0, 0.0, 0.0, -0.25])
    mods["I05"].update({"etr": 0.10, "upside": -0.02, "custo_capital": {"ke": 0.12}})
    aplicar(mods, pacs, params)
    assert mods["I05"]["rating"] == "Neutro" and "guarda de Venda" in mods["I05"]["rating_motivo"]
    pacs, mods = _universo([0.0, 0.0, 0.0, 0.0, 0.0, -0.25])
    mods["I05"].update({"etr": 0.05, "upside": -0.08, "custo_capital": {"ke": 0.12}})
    aplicar(mods, pacs, params)
    assert mods["I05"]["rating"] == "Venda"


def test_neutral_explains_the_absolute_guard(params, media):
    pacs, mods = _universo([-0.30, -0.30, -0.30, -0.30, -0.30, -0.05])
    aplicar(mods, pacs, params)
    assert mods["I05"]["rating"] == "Neutro"
    assert "guarda de Compra não atendida" in mods["I05"]["rating_motivo"] and "< 0%" in mods["I05"]["rating_motivo"]


def test_g4_is_informative_and_quiet_for_a_homogeneous_group(params):
    from cdp.cobertura.qualidade import portoes_transversais

    pacs = {f"I{i}": {"pais": "BR", "setor": "Utilities"} for i in range(7)}
    mods = {f"I{i}": {"custo_capital": {"ke": 0.130 + 0.001 * i}, "portoes": []} for i in range(7)}
    portoes_transversais(mods, pacs, params)
    g4 = [p for m in mods.values() for p in m["portoes"] if p["codigo"] == "G4"]
    assert len(g4) == 7 and all(p["status"] == "ok" for p in g4)   # extremos não falham por construção
    mods["I6"]["custo_capital"]["ke"] = 0.30
    for m in mods.values():
        m["portoes"] = []
    portoes_transversais(mods, pacs, params)
    st = {p["status"] for p in mods["I6"]["portoes"] if p["codigo"] == "G4"}
    assert st == {"informativo"}


def _g13(params, preco, b0, roe1=0.15, iid="X_TESTE", peso=0.75, diverge=False):
    from cdp.cobertura.qualidade import _g13

    return _g13({"issuer_id": iid, "preco": preco}, {"b0": b0, "roe1": roe1, "peso_patrimonial": peso,
                                                      "lpa_diverge": diverge}, params)


def test_g13_blocks_unit_and_currency_traps(params):
    # YPF: patrimônio convertido com fator de câmbio errado (B0 ≈ US$ 0,02 por ADR)
    assert _g13(params, 30.0, 0.0123, roe1=317.6)["status"] == "bloqueio"
    # Hapvida: unidades erradas (P/VPA 0,087)
    assert _g13(params, 8.76, 101.17)["status"] == "bloqueio"
    # exceção curada (patrimônio reduzido por recompras) e caso normal
    assert _g13(params, 40.0, 1.5, iid="MX_KIMBER")["status"] == "ok"
    assert _g13(params, 20.0, 12.0)["status"] == "ok"
    # LPA de consenso incoerente com métodos patrimoniais dominantes
    assert _g13(params, 20.0, 12.0, diverge=True)["status"] == "bloqueio"
    assert _g13(params, 20.0, 12.0, peso=0.3, diverge=True)["status"] == "ok"


def test_g14_compares_year_one_fcff_with_observed_cash_flow(params):
    from cdp.cobertura.qualidade import portoes_emissor

    pac = {"as_of": "2026-10-08", "status_moeda": "ok", "defasagem_preco_dias": 0, "tem_demonstrativos": False}
    base = {"tem_alvo": True, "metodos": [{"valor": 1.0}], "tp": 10.0, "tp_otimista": 12.0, "tp_pessimista": 8.0,
            "upside": 0.1, "pwr": 0.1}
    st = {p["codigo"]: p["status"] for p in portoes_emissor(
        pac, {**base, "fcff_ano1": 300.0, "fcf_observado": 100.0, "fcff_ano1_vs_observado": 3.0}, params)}
    assert st["G14"] == "aviso"
    st = {p["codigo"]: p["status"] for p in portoes_emissor(
        pac, {**base, "fcff_ano1": 105.0, "fcf_observado": 100.0, "fcff_ano1_vs_observado": 1.05}, params)}
    assert st["G14"] == "ok"
    st = {p["codigo"]: p["status"] for p in portoes_emissor(
        pac, {**base, "fcff_ano1": 50.0, "fcf_observado": -20.0, "fcff_ano1_vs_observado": None}, params)}
    assert st["G14"] == "aviso"
