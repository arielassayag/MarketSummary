"""Cobertura de ETFs: agregação exata, imputação sinalizada, pesos de cobertura, top-down sem
composição e testes de ouro (Safra, Grinold–Kroner). DADOS SIMULADOS, sem rede."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from cdp.cobertura.etf import (
    agregar_bu,
    avaliar_etf,
    calcular_etf,
    calcular_etfs,
    grinold_kroner,
    payout_sustentavel,
    pl_gordon,
    reversao_pl,
)
from cdp.cobertura.fontes import coletar
from cdp.cobertura.motor import executar
from cdp.cobertura.parametros import carregar_parametros
from cdp.data.synthetic import make_synthetic_market

D = date(2026, 10, 8)


@pytest.fixture(scope="module")
def run():
    md = make_synthetic_market(seed=7, as_of=D)
    params = carregar_parametros()
    dados = coletar(md, D, list(md.universe.issuers.index), list(md.universe.lines.index), ["ILF", "EWZ", "EWW"])
    ex = executar(md, dados, params, D)
    return md, params, dados, ex


def test_bottom_up_aggregation_is_exact():
    linhas = [{"peso": 0.5, "retorno": 0.10}, {"peso": 0.3, "retorno": -0.05}, {"peso": 0.15, "retorno": 0.20}]
    r = agregar_bu(linhas, caixa=0.05, r_caixa=0.04, ter=0.0059)
    assert r == pytest.approx(0.5 * 0.10 + 0.3 * -0.05 + 0.15 * 0.20 + 0.05 * 0.04 - 0.0059, abs=1e-15)


def test_golden_safra_and_gks():
    assert pl_gordon(0.55, 0.143, 0.084) * 21283 == pytest.approx(198_400, abs=150)
    assert grinold_kroner(0.0178, -0.002, 0.024, 0.018, 0.0085) == pytest.approx(0.0703)


def test_etfs_have_targets_coverage_and_imputation_flags(run):
    md, params, dados, ex = run
    for k in ("ETF_ILF", "ETF_EWZ", "ETF_EWW"):
        e = ex.etfs[k]
        assert e["tem_alvo"] and e["preco_alvo"] > 0
        assert 0 < e["cobertura"] <= 1
        imp = [p for p in e["posicoes"] if p["imputado"]]
        assert any(p["issuer_id"] is None for p in imp)  # posição sem mapeamento sinalizada
        assert all(p["retorno"] is not None for p in e["posicoes"])
        # cobertura = soma dos pesos com modelo da casa
        cob = sum(p["peso"] for p in e["posicoes"] if not p["imputado"])
        assert e["cobertura"] == pytest.approx(cob, rel=1e-5)
        omega = 0.5 * min(1.0, e["cobertura"] / 0.90)
        assert e["omega_bu"] == pytest.approx(omega, rel=1e-5)
        assert e["retorno_esperado"] == pytest.approx(omega * e["r_bu"] + (1 - omega) * e["r_td"], abs=2e-6)
        assert e["passos"] and all(p["substituicao"] for p in e["passos"])
        cfg = next(c for c in params.etfs["etfs"] if c["ticker"] == e["ticker"])
        assert e["indice"] == cfg["indice"]
        assert next(p for p in e["passos"] if p["id"] == "etf.indice")["substituicao"] == cfg["indice"]
    assert ex.etfs["ETF_ILF"]["visao_ilf"] == "Referência"
    assert ex.etfs["ETF_EWZ"]["visao_ilf"] in ("Positiva", "Neutra", "Negativa")


def test_indice_de_referencia_visivel_nos_oito_modelos_sem_preco():
    from cdp.workflow import painel_cobertura as pc

    params = carregar_parametros()
    assert len(params.etfs["etfs"]) == 8
    for cfg in params.etfs["etfs"]:
        iid = "ETF_" + cfg["ticker"].split(".")[0]
        ins = {**cfg, "iid": iid, "as_of": D.isoformat(), "preco": None,
               "fonte_indice": {"fonte": "CONFIG", "url": cfg["url"],
                                "documento": "índice de referência declarado pelo emissor",
                                "sha256": params.arquivos["cobertura/etfs.yaml"]}}
        e = calcular_etf(ins, params, {}, {}, 0.045)
        assert e["tem_alvo"] is False and e["indice"] == cfg["indice"]
        assert e["passos"][0]["fontes"][0]["url"] == cfg["url"]
        u = {"iid": iid, "citavel": False, "preco_texto": "n/d", "preco_data": None,
             "alvo_texto": "Sem preço-alvo", "upside_texto": "n/d", "etr_texto": "n/d",
             "rating": "Em revisão", "nome": cfg["nome"], "ticker": cfg["ticker"],
             "pais_nome": cfg["pais"], "moeda": cfg["moeda"], "rating_tom": "sem",
             "rating_desde": None, "data_modelo": D.isoformat()}
        ficha = pc._modelo_etf(SimpleNamespace(etfs={iid: e}), u, {})
        assert ficha["indice"] == cfg["indice"]
        assert ficha["cabecalho"][0] == {"t": "Índice de referência", "v": cfg["indice"]}
        assert ficha["passos"] and ficha["lacunas"]  # modelo visível mesmo sem alvo citável


def test_without_public_holdings_bottom_up_is_unavailable(run):
    md, params, dados, ex = run
    cfg = {"ticker": "EWZ", "nome": "x", "moeda": "USD", "pais": "BR", "ter": 0.0059}
    sem = type(dados)(**{**dados.__dict__, "etfs": {"EWZ": None}})
    e = avaliar_etf(cfg, md, sem, params, ex.pacotes, ex.modelos, 0.045, D, None)
    assert e["tem_alvo"] and e["r_bu"] is None and e["metodo"] == "top_down"
    assert e["composicao_aproximada"] is True
    assert any(lac["insumo"] == "composicao" for lac in e["lacunas"])


def test_mapped_weight_on_fixture_holdings(run):
    _, _, dados, _ = run
    for etf in ("ILF", "EWZ", "EWW"):
        comp = dados.etfs[etf]
        nao_caixa = comp[comp["setor"] != "Caixa"]
        mapeado = nao_caixa[nao_caixa["issuer_id"].notna()]["peso"].sum() / nao_caixa["peso"].sum()
        assert mapeado >= 0.95


def test_steady_state_index_has_no_pe_drift():
    # índice estacionário: payout = 1 − g/ROE e P/L corrente = P/L justificado ⇒ ΔPE = 0
    roe, k, g = 0.15, 0.11, 0.044
    b = payout_sustentavel(roe, g)
    pe_star = pl_gordon(b, k, g)
    assert b == pytest.approx(1 - g / roe)
    assert reversao_pl(pe_star, pe_star, 3.0) == pytest.approx(pe_star)
    assert grinold_kroner(0.03, 0.0, 0.03, 0.02, 0.0) == pytest.approx(0.08)
    # fora do estacionário a reversão é parcial (meia-vida de 3 anos)
    pe12 = reversao_pl(10.0, 5.0, 3.0)
    assert 5.0 < pe12 < 10.0 and pe12 == pytest.approx(10.0 * 0.5 ** (1 - 2 ** (-1 / 3)))


def test_etf_payout_is_sustainable_and_justified_pe_bounded(run):
    _, params, _, ex = run
    for e in ex.etfs.values():
        ag = e.get("agregados")
        if not ag:
            continue
        assert ag["payout"] == pytest.approx(min(max(1 - 0.044 / ag["roe_indice"], 0.05), 0.95), abs=0.01)
        assert 0.6 - 1e-6 <= ag["pl_justificado"] / ag["pl"] <= 1.6 + 1e-6
        assert {p["codigo"] for p in e["portoes"]} >= {"E1", "E2", "E3", "E4"}


def test_etfs_recomputed_from_archived_packages_match(run):
    _, params, _, ex = run
    again = calcular_etfs(ex.insumos_etf, params, ex.pacotes, ex.modelos, ex.rf["valor"])
    for k, e in ex.etfs.items():
        assert again[k]["preco_alvo"] == pytest.approx(e["preco_alvo"], rel=1e-12)
        assert again[k]["visao_ilf"] == e["visao_ilf"]


def test_blocking_etf_gate_puts_view_under_review(run):
    _, params, _, ex = run
    ins = {k: dict(v) for k, v in ex.insumos_etf.items()}
    ilf = next(k for k, v in ins.items() if v["ticker"] == "ILF")
    ins[ilf]["taxa_caixa"] = 50.0   # caixa absurdo ⇒ retorno esperado fora da faixa
    ins[ilf]["composicao"] = [{**x, "setor": "Caixa"} for x in ins[ilf]["composicao"]]
    e = calcular_etfs(ins, params, ex.pacotes, ex.modelos, ex.rf["valor"])[ilf]
    assert e["visao_ilf"] == "Em revisão" and "E2" in e["visao_motivo"]
