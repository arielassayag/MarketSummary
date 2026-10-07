"""Margem entre fluxos comparáveis; DADOS SIMULADOS, sem rede nem livro oficial."""

from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest
import yaml

from cdp.cobertura.contexto import fundamentos, montar_contexto, prever
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import preparar
from cdp.cobertura.margens import METODO, margens_alinhadas
from cdp.cobertura.modelo import Avaliador, Drivers
from cdp.cobertura.motor import Execucao, modelo_json
from cdp.cobertura.parametros import carregar_parametros
from cdp.data.synthetic import make_synthetic_market


def _pacote():
    p = {"moeda": "BRL", "t.receita": 100.0, "t.ebit": 20.0,
         "periodos_fluxos": {k: "TTM|2026-06-30" for k in ("receita", "ebit")},
         "moedas_fluxos": {k: "BRL" for k in ("receita", "ebit")},
         "bases_fluxos": {k: "consolidado" for k in ("receita", "ebit")},
         "fontes": {f"t.{k}": {"fonte": "DADOS SIMULADOS", "sha256": "a" * 64,
                                  "data_publicacao": "2026-08-07"} for k in ("receita", "ebit")},
         "historico": {"receita": {}, "ebit": {}}, "historico_periodos": {},
         "historico_moedas": {}, "historico_bases": {}, "historico_fontes": {}}
    for item in ("receita", "ebit"):
        for campo in ("historico_periodos", "historico_moedas", "historico_bases", "historico_fontes"):
            p[campo][item] = {}
        for ano, margem in (("2023", 0.1), ("2024", 0.2), ("2025", 0.3)):
            valor = 100.0 if item == "receita" else 100.0 * margem
            p["historico"][item][ano] = valor
            p["historico_periodos"][item][ano] = f"A|{ano}-12-31"
            p["historico_moedas"][item][ano] = "BRL"
            p["historico_bases"][item][ano] = "consolidado"
            p["historico_fontes"][item][ano] = {"fonte": "DADOS SIMULADOS", "valor_modelo": valor,
                                                "sha256": "b" * 64, "data_publicacao": f"{int(ano) + 1}-03-01"}
    return p


def test_razao_comparavel_preserva_bruto_e_fontes_sem_mutar_pacote():
    p = _pacote()
    bruto = deepcopy(p)
    d = margens_alinhadas(p)
    assert d["corrente"]["status"] == "comparavel" and d["corrente"]["margem"] == 0.2
    assert d["corrente"]["insumos"]["receita"]["fonte"] == p["fontes"]["t.receita"]
    assert [v["margem"] for v in d["historico"].values()] == [0.1, 0.2, 0.3]
    assert p == bruto
    d["corrente"]["insumos"]["receita"]["fonte"]["sha256"] = "outro"
    assert p == bruto


@pytest.mark.parametrize("campo,valor,motivo", [
    ("periodos_fluxos", "A|2025-12-31", "janelas de 12 meses diferentes"),
    ("periodos_fluxos", "Q|2026-06-30", "período de 12 meses não demonstrado"),
    ("periodos_fluxos", "TTM|2026-02-30", "período de 12 meses não demonstrado"),
    ("periodos_fluxos", None, "período de 12 meses não demonstrado"),
    ("periodos_fluxos", "", "período de 12 meses não demonstrado"),
    ("moedas_fluxos", "USD", "moedas diferentes"),
    ("moedas_fluxos", "brl", "moeda da fonte não demonstrada"),
    ("moedas_fluxos", None, "moeda da fonte não demonstrada"),
    ("bases_fluxos", "individual", "bases contábeis diferentes"),
    ("bases_fluxos", None, "base contábil não demonstrada"),
    ("bases_fluxos", "base mista", "base contábil não demonstrada"),
])
def test_desconhecimento_ou_desalinhamento_recusa_margem(campo, valor, motivo):
    p = _pacote()
    p[campo]["receita"] = valor
    d = margens_alinhadas(p)["corrente"]
    assert d["margem"] is None and d["status"] == "ausente" and motivo in d["motivo"]
    assert d["insumos"]["receita"]["valor"] == 100 and d["insumos"]["ebit"]["valor"] == 20


def test_ambas_bases_desconhecidas_nao_certificam_identidade():
    p = _pacote()
    p["bases_fluxos"] = {"receita": None, "ebit": None}
    assert margens_alinhadas(p)["corrente"]["margem"] is None


@pytest.mark.parametrize("anual", ["receita", "ebit"])
def test_corrente_anual_e_ttm_mesma_janela_de_12_meses_sao_compativeis(anual):
    p = _pacote()
    p["periodos_fluxos"][anual] = "A|2026-06-30"
    d = margens_alinhadas(p)["corrente"]
    assert d["margem"] == 0.2
    assert d["insumos"][anual]["periodo"] == "A|2026-06-30"
    assert {r["fim_janela_12m"] for r in d["insumos"].values()} == {"2026-06-30"}


@pytest.mark.parametrize("valor,margem", [(0, 0.0), (-20, -0.2), (None, None),
                                           (float("nan"), None), (float("inf"), None), (True, None)])
def test_zero_ebit_e_prejuizo_sao_fatos_ausencia_nao_e_zero(valor, margem):
    p = _pacote()
    p["t.ebit"] = valor
    assert margens_alinhadas(p)["corrente"]["margem"] == margem


@pytest.mark.parametrize("valor", [0, -1, None, float("nan"), float("inf"), True])
def test_receita_invalida_nao_produz_razao(valor):
    p = _pacote()
    p["t.receita"] = valor
    assert margens_alinhadas(p)["corrente"]["margem"] is None


def test_razao_nao_finita_e_recusada_mesmo_com_componentes_finitos():
    p = _pacote()
    p.update({"t.ebit": 1e308, "t.receita": 1e-308})
    d = margens_alinhadas(p)["corrente"]
    assert d["margem"] is None and "razão EBIT/receita não finita" in d["motivo"]


@pytest.mark.parametrize("campo,valor", [("historico_periodos", "A|2024-12-31"),
                                        ("historico_periodos", "TTM|2025-12-31"),
                                        ("historico_bases", "individual"),
                                        ("historico_moedas", "USD"),
                                        ("historico_fontes", None),
                                        ("historico_fontes", {"valor_modelo": 19.0})])
def test_historico_exige_janela_e_proveniencia_do_valor_sem_fallback_parcial(campo, valor):
    p = _pacote()
    p[campo]["ebit"]["2025"] = valor
    f = fundamentos(p, margem_fluxos_metodo=METODO)
    assert f["margem"] == 0.2
    assert f["margem_hist"] is None and f["margem_sd"] is None  # apenas dois anos certificados
    assert f["margem_fluxos"]["historico"]["2025"]["margem"] is None
    assert p["historico"]["ebit"]["2025"] == 30.0


def test_historico_mesmo_ano_com_datas_fiscais_distintas_e_recusado():
    p = _pacote()
    p["historico_periodos"]["receita"]["2025"] = "A|2025-06-30"
    d = margens_alinhadas(p)["historico"]["2025"]
    assert d["margem"] is None and "janelas de 12 meses diferentes" in d["motivo"]


def test_anos_ausentes_em_um_item_permanecem_diagnosticados():
    p = _pacote()
    del p["historico"]["ebit"]["2025"]
    d = margens_alinhadas(p)["historico"]["2025"]
    assert d["margem"] is None and d["insumos"]["ebit"]["valor"] is None


@pytest.fixture(scope="module")
def universo_simulado():
    d = date(2026, 10, 8)
    params = carregar_parametros()
    md = make_synthetic_market(seed=7, as_of=d)
    ids = list(md.universe.issuers.index)
    dados = coletar(md, d, ids, list(md.universe.lines.index), [], offline=True)
    return preparar(md, dados, params, ids, d)


@pytest.fixture
def params():
    p = deepcopy(carregar_parametros())
    p.sec("qualidade")["margem_fluxos_metodo"] = METODO
    return p


def _corporativo(universo):
    return deepcopy(next(p for p in universo.values()
                         if not p["financeira"] and p["arquetipo"] == "corporativo" and p["tem_demonstrativos"]))


def test_contexto_exclui_razao_desalinhada_antes_dos_pares_e_ev_receita(params, universo_simulado):
    p = _corporativo(universo_simulado)
    iid = p["issuer_id"]
    a = montar_contexto({iid: p}, params, 0.045)
    p["periodos_fluxos"]["receita"] = "A|2025-12-31"
    b = montar_contexto({iid: p}, params, 0.045)
    assert a["fundamentos"][iid]["margem"] is not None
    assert b["fundamentos"][iid]["margem"] is None
    assert b["universo"]["margem_mediana"] is None
    assert b["setores"][p["setor"]]["margem_mediana"] is None
    assert a["regressoes"]["ev_receita"]["n"] == 1
    assert b["regressoes"]["ev_receita"]["n"] == 0
    assert a["fundamentos"][iid]["margem_hist"] == b["fundamentos"][iid]["margem_hist"]


def test_contexto_antigo_nao_recupera_margem_invalida_no_avaliador_ou_fcff_normalizado(params, universo_simulado):
    p = _corporativo(universo_simulado)
    iid = p["issuer_id"]
    ctx = montar_contexto({iid: p}, params, 0.045)
    ctx["regressoes"]["ev_receita"] = {
        "disponivel": True, "colunas": ["intercepto", "margem"], "coef": [1.0, 1.0],
        "regressores": ["margem"], "efeitos": [], "limites": [0.1, 5.0]}
    bruto_ctx = deepcopy(ctx)
    assert prever(ctx["regressoes"]["ev_receita"], ctx["fundamentos"][iid], p["pais"]) is not None
    p["bases_fluxos"]["receita"] = None
    av = Avaliador(p, ctx, params, 0.045, {})
    assert av.receita0 == p["t.receita"] and av.margem is None and av.margem_hist is not None
    for metodo in ("fcff", "fcff_real", "fcff_normalizado", "fcff_vida_finita"):
        assert "margem EBIT" in av._requisitos(metodo)
    assert "incompletos" in av._requisitos("regressao_ev_receita")
    assert prever(ctx["regressoes"]["ev_receita"], av.fund, p["pais"]) is None
    assert ctx == bruto_ctx


def test_margem_certificada_move_fcff_na_direcao_economica(params, universo_simulado):
    p = _corporativo(universo_simulado)
    iid = p["issuer_id"]
    ctx = montar_contexto({iid: p}, params, 0.045)
    av = Avaliador(p, ctx, params, 0.045, {})
    q = deepcopy(p)
    q["t.ebit"] *= 1.1
    bv = Avaliador(q, montar_contexto({iid: q}, params, 0.045), params, 0.045, {})
    assert av._requisitos("fcff") is None and bv._requisitos("fcff") is None
    assert bv.margem > av.margem
    assert float(bv._valor_metodo("fcff", Drivers())) > float(av._valor_metodo("fcff", Drivers()))


def test_modelo_aberto_expoe_ausencia_par_e_proveniencia_sem_alterar_insumos(params, universo_simulado):
    p = _corporativo(universo_simulado)
    iid = p["issuer_id"]
    p["periodos_fluxos"]["receita"] = "A|2025-12-31"
    bruto = deepcopy(p)
    ctx = montar_contexto({iid: p}, params, 0.045)
    av = Avaliador(p, ctx, params, 0.045, {})
    m = av.avaliar()
    m.update({"resumo": {}, "portoes": []})
    ex = Execucao(as_of=date(2026, 10, 8), pacotes={iid: p}, contexto=ctx, modelos={iid: m},
                  etfs={}, rf={}, distribuicao={}, is_synthetic=True, emissores=[iid], registros={iid: av.reg})
    out = modelo_json(ex, iid, params)
    d = out["diagnosticos"]["margem_fluxos"]["corrente"]
    assert d["margem"] is None and d["status"] == "ausente"
    assert d["insumos"]["receita"]["periodo"] == "A|2025-12-31"
    assert d["insumos"]["ebit"]["fonte"]["sha256"] == p["fontes"]["t.ebit"]["sha256"]
    assert any(lacuna["insumo"] == "margem" for lacuna in out["lacunas"])
    assert any(s["id"] == "dir.margem_comparabilidade" for s in out["passos"])
    assert out["aviso_dados"] == "DADOS SIMULADOS"
    assert p == bruto


@pytest.mark.parametrize("versao", ["2026-10.4", "2026-10.5"])
def test_sem_chave_preserva_fundamentos_e_modelo_historicos(params, universo_simulado, versao):
    params.valuation["versao"] = versao
    params.sec("qualidade").pop("margem_fluxos_metodo")
    p = _corporativo(universo_simulado)
    iid = p["issuer_id"]
    ctx = montar_contexto({iid: p}, params, 0.045)
    m = Avaliador(p, ctx, params, 0.045, {}).avaliar()
    q = deepcopy(p)
    for k in ("periodos_fluxos", "moedas_fluxos", "bases_fluxos", "historico_periodos",
              "historico_moedas", "historico_bases", "historico_fontes"):
        q.pop(k, None)
    # RR capitalizado possui dependências próprias; isolamos aqui o contrato da margem.
    params.sec("projecao").pop("reinvestimento_metodo", None)
    params.sec("projecao").pop("reinvestimento_regime", None)
    c1, c2 = montar_contexto({iid: p}, params, 0.045), montar_contexto({iid: q}, params, 0.045)
    a1, a2 = Avaliador(p, c1, params, 0.045, {}), Avaliador(q, c2, params, 0.045, {})
    assert fundamentos(p) == fundamentos(q)
    assert c1 == c2
    assert a1.avaliar() == a2.avaliar()
    assert "margem_fluxos" not in m
    assert not any(lacuna["insumo"] in ("margem", "margem_historica") for lacuna in m["lacunas"])


@pytest.mark.parametrize("valor", [None, False, "periodo", "periodo_moeda_base_futura"])
def test_configuracao_explicitamente_desconhecida_e_recusada(params, tmp_path, valor):
    params.sec("qualidade")["margem_fluxos_metodo"] = valor
    arq = tmp_path / "valuation.yaml"
    arq.write_text(yaml.safe_dump(params.valuation), encoding="utf-8")
    with pytest.raises(ValueError, match="margem_fluxos_metodo desconhecido"):
        carregar_parametros(arq)
