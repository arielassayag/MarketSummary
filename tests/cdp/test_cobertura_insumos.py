"""Normalização dos insumos públicos: moeda, unidade, defasagem, ausências (nunca zero) e
determinismo (DADOS SIMULADOS; sem rede)."""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cdp.cobertura.contexto import _regressao, montar_contexto, prever
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import Demonstrativos, acoes_por_linha, preparar_emissor
from cdp.cobertura.motor import executar, modelo_json
from cdp.cobertura.parametros import carregar_parametros
from cdp.data.synthetic import make_synthetic_market

D = date(2026, 10, 8)


@pytest.fixture(scope="module")
def base():
    md = make_synthetic_market(seed=7, as_of=D)
    params = carregar_parametros()
    ids = list(md.universe.issuers.index)
    dados = coletar(md, D, ids, list(md.universe.lines.index), ["ILF", "EWZ", "EWW"])
    ex = executar(md, dados, params, D)
    return md, params, dados, ex


def _numeros(obj, caminho=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _numeros(v, f"{caminho}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _numeros(v, f"{caminho}[{i}]")
    elif isinstance(obj, float):
        yield caminho, obj


def test_no_nan_or_infinite_in_stored_models(base):
    md, params, _, ex = base
    for iid in ex.modelos:
        m = modelo_json(ex, iid, params)
        for cam, v in _numeros(m):
            assert math.isfinite(v), (iid, cam)
        json.dumps(m, allow_nan=False)


def test_missing_statement_item_stays_missing_not_zero(base):
    md, params, dados, _ = base
    iid = next(i for i in md.universe.issuers.index if md.universe.issuers.loc[i, "gics_sector"] != "Financials"
               and i in set(dados.demonstrativos["issuer_id"]))
    dem = dados.demonstrativos
    sem_caixa = dem[~((dem["issuer_id"] == iid) & (dem["item"].isin(["caixa", "divida_liquida"])))]
    pac = preparar_emissor(md, type(dados)(**{**dados.__dict__, "demonstrativos": sem_caixa}), params, iid, D)
    assert pac["divida_liquida"] is None
    assert "t.caixa" not in pac
    assert any(lac["insumo"] == "divida_liquida" for lac in pac["lacunas"])
    # e o método de fluxo de caixa fica indisponível com o motivo, sem valor substituto
    ctx = montar_contexto({iid: pac}, params)
    from cdp.cobertura.modelo import Avaliador

    av = Avaliador(pac, ctx, params, 0.045, {})
    mod = av.avaliar()
    fc = [m for m in mod["metodos"] if m["m"].startswith("fcff")]
    assert fc and all(m["valor"] is None and "dívida líquida" in (m["motivo"] or "") for m in fc)


def test_issuer_without_statements_has_explicit_gaps(base):
    md, params, dados, ex = base
    sem = [i for i in ex.pacotes if not ex.pacotes[i]["tem_demonstrativos"]]
    assert sem
    for iid in sem:
        assert any(lac["insumo"] == "demonstrativos" for lac in ex.pacotes[iid]["lacunas"])
        assert ex.pacotes[iid].get("bvps") is None or ex.pacotes[iid].get("bvps_fonte_yahoo")


def test_adr_ratio_conversion(base):
    md, params, _, _ = base
    lines = md.universe.lines
    adr = lines[lines["line_type"] == "ADR"].iloc[0]
    n, txt = acoes_por_linha(md, params, adr["issuer_id"], adr.name)
    assert n == pytest.approx(float(adr["adr_ratio"]))
    assert "ADR" in txt


def test_unit_lines_use_curated_share_counts():
    params = carregar_parametros()
    assert params.unidades["KLBN11.SA"]["acoes_por_unidade"] == 5
    assert params.unidades["TLEVISACPO.MX"]["acoes_por_unidade"] == 117


def test_consensus_eps_in_statement_currency_is_converted(base):
    md, params, _, ex = base
    uni = md.universe
    adr_ids = [i for i in uni.issuers.index if uni.issuers.loc[i, "primary_line_type"] == "ADR"]
    pac = ex.pacotes[adr_ids[0]]
    if pac["linha_tipo"] == "ADR":
        assert pac["consenso"]["status_lpa"] in ("fx_corrigido", "unidade_corrigida")
        pe = pac["preco"] / pac["eps_fy1"]
        assert 1.0 <= pe <= 200.0


def test_per_unit_consensus_target_flagged(base):
    md, params, _, ex = base
    implausiveis = [i for i, p in ex.pacotes.items() if p.get("consenso") and not p["consenso"]["plausivel"]]
    assert implausiveis  # alvo de consenso por unidade errada (×6,7) não é comparado
    for i in implausiveis:
        assert ex.modelos[i]["resumo"]["diff_consenso"] is None


def test_stale_price_blocks_rating(base):
    md, params, _, ex = base
    stale = md.universe.issuers["primary_ticker"].iloc[5]
    iid = md.universe.lines.loc[stale, "issuer_id"]
    if ex.pacotes[iid]["linha"] == stale:
        assert ex.modelos[iid]["rating"] == "Em revisão"
        assert any(p["codigo"] == "G12" and p["status"] == "bloqueio" for p in ex.modelos[iid]["portoes"])


def test_negative_equity_disables_book_methods(base):
    _, _, _, ex = base
    neg = [i for i, p in ex.pacotes.items() if p.get("bvps") is not None and p["bvps"] < 0]
    assert neg
    for iid in neg:
        rim = [m for m in ex.modelos[iid]["metodos"] if m["m"].startswith("rim")]
        assert all(m["valor"] is None for m in rim)


def test_regression_ignores_implausible_multiples():
    # P/VPA de 238x (erro de unidade tipo CMPC) fica fora da regressão e da previsão
    rng = np.random.default_rng([3, 1])
    linhas = []
    for i in range(30):
        roe = float(rng.uniform(0.05, 0.25))
        linhas.append({"pais": "BR" if i % 2 else "MX", "roe": roe, "g": 0.05, "beta_reg": 1.0, "payout": 0.4,
                       "pb": 0.5 + 8 * roe + float(rng.normal(0, 0.05))})
    linhas.append({"pais": "CL", "roe": 0.1, "g": 0.05, "beta_reg": 1.0, "payout": 0.4, "pb": 238.0})
    reg = _regressao("pb", linhas, "pb", ["roe", "g", "beta_reg", "payout"], (0.1, 15.0), 12, 1.345)
    assert reg["disponivel"] and reg["n"] == 30
    coef = dict(zip(reg["colunas"], reg["coef"], strict=False))
    assert coef["roe"] == pytest.approx(8.0, abs=0.6)
    assert prever(reg, {"roe": 0.15, "g": 0.05, "beta_reg": 1.0, "payout": 0.4}, "BR") == pytest.approx(
        0.5 + 8 * 0.15, abs=0.3)
    assert prever(reg, {"roe": 3.0, "g": 0.05, "beta_reg": 1.0, "payout": 0.4}, "BR") is None


def test_demonstrativos_ttm_from_quarters_and_stale_items():
    rows = []
    for k, d in enumerate(["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]):
        rows.append(dict(issuer_id="X", demonstrativo="DRE", freq="Q", period_end=d, item="receita",
                         value=100.0 + k, currency="BRL", escala=1, consolidado=True, fonte="CVM", url=None,
                         documento="ITR", data_publicacao=pd.Timestamp(d) + pd.Timedelta(days=40), sha256=None))
    rows.append(dict(issuer_id="X", demonstrativo="BP", freq="Q", period_end="2026-06-30",
                     item="patrimonio_controladores", value=500.0, currency="BRL", escala=1, consolidado=True,
                     fonte="CVM", url=None, documento="ITR", data_publicacao="2026-08-10", sha256=None))
    rows.append(dict(issuer_id="X", demonstrativo="BP", freq="Q", period_end="2024-12-31", item="caixa",
                     value=50.0, currency="BRL", escala=1, consolidado=True, fonte="SEC", url=None,
                     documento="20-F", data_publicacao="2025-04-25", sha256=None))
    dem = Demonstrativos(pd.DataFrame(rows), "X")
    v, row = dem.valor("receita")
    assert v == pytest.approx(406.0) and row["freq"] == "TTM"
    assert dem.valor("caixa") == (None, None)
    assert any(x.startswith("caixa") for x in dem.defasados)
    assert dem.moeda() == "BRL"


def test_same_inputs_same_model_bytes(base):
    md, params, dados, ex = base
    ex2 = executar(md, dados, params, D)
    for iid in list(ex.modelos)[:12]:
        a = json.dumps(modelo_json(ex, iid, params), sort_keys=True, ensure_ascii=False)
        b = json.dumps(modelo_json(ex2, iid, params), sort_keys=True, ensure_ascii=False)
        assert a == b, iid


def _com_dem(dados, dem):
    return type(dados)(**{**dados.__dict__, "demonstrativos": dem})


def _nao_fin(md, dados):
    return next(i for i in md.universe.issuers.index if md.universe.issuers.loc[i, "gics_sector"] not in
                ("Financials", "Utilities", "Real Estate") and i in set(dados.demonstrativos["issuer_id"]))


def test_estimated_publication_dates_are_not_point_in_time(base):
    md, params, dados, _ = base
    iid = _nao_fin(md, dados)
    dem = dados.demonstrativos.copy()
    dem["pit_estimado"] = dem["issuer_id"] == iid
    dem["data_coleta"] = "2026-10-08T22:00:00+00:00"
    pac = preparar_emissor(md, _com_dem(dados, dem), params, iid, D)
    assert pac["pit_ok"] is False and pac["datas_estimadas"] is True
    linha = next(x for x in pac["tabela_insumos"] if x["id"] == "t.receita")
    assert linha["data_estimada"] is True and linha["data_coleta"].startswith("2026-10-08")
    outro = next(i for i in md.universe.issuers.index if i != iid and i in set(dem["issuer_id"]))
    assert preparar_emissor(md, _com_dem(dados, dem), params, outro, D)["pit_ok"] is True


def test_missing_minorities_never_become_zero(base):
    md, params, dados, _ = base
    iid = _nao_fin(md, dados)
    dem = dados.demonstrativos
    sem = dem[~((dem["issuer_id"] == iid) & dem["item"].isin(["participacao_minoritarios", "patrimonio_liquido"]))]
    pac = preparar_emissor(md, _com_dem(dados, sem), params, iid, D)
    assert pac["minoritarios"] is None
    assert any(lac["insumo"] == "minoritarios" for lac in pac["lacunas"])
    from cdp.cobertura.modelo import Avaliador

    mod = Avaliador(pac, montar_contexto({iid: pac}, params), params, 0.045, {}).avaliar()
    fc = [m for m in mod["metodos"] if m["m"].startswith("fcff")]
    assert fc and all(m["valor"] is None and "não controladores" in m["motivo"] for m in fc)
    # derivada do mesmo balanço quando há patrimônio total e dos controladores
    so_nci = dem[~((dem["issuer_id"] == iid) & (dem["item"] == "participacao_minoritarios"))]
    pac2 = preparar_emissor(md, _com_dem(dados, so_nci), params, iid, D)
    assert pac2["minoritarios"] == pytest.approx(pac2["t.patrimonio_liquido"] - pac2["t.patrimonio_controladores"],
                                                 rel=1e-3)  # valores do pacote a 6 algarismos
    assert pac2["fontes"]["minoritarios"]["fonte"] == "CODIGO"


def test_leases_enter_leverage_and_wacc_like_the_bridge(base):
    md, params, dados, ex = base
    iid = next(i for i, p in ex.pacotes.items() if p.get("arrendamentos") and p.get("divida_bruta")
               and not p["financeira"])
    p = ex.pacotes[iid]
    assert p["d_e_mercado"] == pytest.approx((p["divida_bruta"] + p["arrendamentos"]) / p["valor_mercado"], rel=1e-5)
    cc = ex.modelos[iid]["custo_capital"]
    assert cc["peso_divida"] == pytest.approx((p["divida_bruta"] + p["arrendamentos"])
                                              / (p["valor_mercado"] + p["divida_bruta"] + p["arrendamentos"]), rel=1e-4)


def test_financials_do_not_use_revenue_growth(base):
    md, params, dados, ex = base
    fin = [i for i, p in ex.pacotes.items() if p["financeira"]]
    assert fin
    for i in fin:
        assert ex.pacotes[i]["g_receita_fy1"] is None and ex.pacotes[i]["g_receita_historico"] is None
        f = ex.contexto["fundamentos"][i]
        assert f["g"] is None or f["g"] == pytest.approx(min(max(f["g_eps"], -0.2), 0.3), rel=1e-5)


def test_implausible_historical_growth_is_missing(base):
    md, params, dados, _ = base
    iid = _nao_fin(md, dados)
    dem = dados.demonstrativos.copy()
    rec = (dem["issuer_id"] == iid) & (dem["item"] == "receita") & (dem["freq"] == "TTM")
    ult = dem.loc[rec, "period_end"].max()
    dem.loc[rec & (dem["period_end"] == ult), "value"] *= 4.0     # +300%: efeito contábil
    pac = preparar_emissor(md, _com_dem(dados, dem), params, iid, D)
    assert pac["g_receita_historico"] is None
    assert any(lac["insumo"] == "g_receita_historico" for lac in pac["lacunas"])


def test_flows_lagging_the_balance_sheet_raise_a_gap_and_warning(base):
    md, params, dados, _ = base
    iid = _nao_fin(md, dados)
    dem = dados.demonstrativos
    fluxos = dem["item"].isin(["receita", "ebit", "lucro_liquido", "lucro_liquido_controladores"])
    ult = dem.loc[(dem["issuer_id"] == iid) & fluxos, "period_end"].max()
    tira = (dem["issuer_id"] == iid) & fluxos & (pd.to_datetime(dem["period_end"]) > pd.Timestamp(ult) - pd.Timedelta(days=200))
    pac = preparar_emissor(md, _com_dem(dados, dem[~tira]), params, iid, D)
    assert pac["defasagem_fluxos_dias"] > 100
    assert any(lac["insumo"] == "defasagem_fluxos" for lac in pac["lacunas"])
    from cdp.cobertura.qualidade import portoes_emissor

    g15 = [p for p in portoes_emissor(pac, {"tem_alvo": False}, params) if p["codigo"] == "G15"]
    assert g15 and g15[0]["status"] == "aviso"


def test_other_share_classes_keep_the_current_price_ratio():
    from types import SimpleNamespace

    from cdp.cobertura.motor import _alvos_linhas

    idx = pd.date_range("2026-10-01", "2026-10-08")
    lines = pd.DataFrame({"currency": ["BRL", "BRL", "USD"], "line_type": ["LOCAL", "LOCAL", "ADR"],
                          "issuer_id": ["BR_X"] * 3, "adr_ratio": [None, None, 1.0]},
                         index=["XPTO4.SA", "XPTO3.SA", "XPTO"])
    uni = SimpleNamespace(lines=lines, lines_for=lambda i: lines[lines["issuer_id"] == i])
    close = pd.DataFrame({"XPTO4.SA": 40.0, "XPTO3.SA": 32.0, "XPTO": 8.0}, index=idx)
    md = SimpleNamespace(universe=uni, close=close, fx=pd.DataFrame({"BRL": 0.2}, index=idx))
    params = carregar_parametros()
    pac = {"issuer_id": "BR_X", "linha": "XPTO4.SA", "moeda": "BRL", "preco": 40.0,
           "linhas": ["XPTO3.SA", "XPTO4.SA", "XPTO"]}
    out = {x["ticker"]: x for x in _alvos_linhas(md, params, pac, {"tem_alvo": True, "tp": 50.0}, D)}
    assert out["XPTO4.SA"]["preco_alvo"] == pytest.approx(50.0) and out["XPTO4.SA"]["linha_valuation"]
    assert out["XPTO3.SA"]["preco_alvo"] == pytest.approx(40.0)          # 50 × 32/40
    assert out["XPTO3.SA"]["upside"] == pytest.approx(out["XPTO4.SA"]["upside"])
    assert "razão corrente" in out["XPTO3.SA"]["conversao"] and "câmbio" not in out["XPTO3.SA"]["conversao"]
    assert "câmbio" in out["XPTO"]["conversao"]
