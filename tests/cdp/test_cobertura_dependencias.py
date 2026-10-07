"""G17 por dependência econômica; DADOS SIMULADOS, sem rede ou livro oficial."""

from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest
import yaml

from cdp.cobertura.contexto import montar_contexto, prever
from cdp.cobertura.dependencias import dependencia_fluxos_financeiros
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import preparar
from cdp.cobertura.modelo import Avaliador, Drivers
from cdp.cobertura.motor import Execucao, modelo_json
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.qualidade import _g17
from cdp.cobertura.rating import confianca
from cdp.cobertura.reinvestimento import COMPONENTES
from cdp.data.synthetic import make_synthetic_market


@pytest.fixture
def params():
    p = deepcopy(carregar_parametros())
    p.sec("projecao").pop("normalizacao_resultado_metodo", None)  # Isola a política .6 sob teste.
    p.sec("qualidade")["alertas_fonte_metodo"] = "dependencias_efetivas"
    return p


def _financeira(params, arquetipo="banco"):
    p = {"issuer_id": "SIM_FIN", "financeira": True, "arquetipo": arquetipo, "pais": "BR",
         "as_of": "2026-10-08", "max_data_publicacao": "2026-08-07", "pit_ok": True,
         "status_moeda": "ok", "historico": {}, "alertas_fonte": [
             {"item": "capex", "tipo": "salto", "data": "2026-06-30", "texto": "capex mudou"}]}
    m = {"metodos": [{"m": k, "peso": w, "valor": 10.0} for k, w in params.pesos(arquetipo).items()],
         "custo_capital": {"ke": 0.12, "beta": 0.9, "imposto": 0.34, "kd": None, "wacc": None,
                           "peso_divida": None, "beta_fonte": "regressão própria (sem pares suficientes)"},
         "tem_alvo": True, "n_metodos": len(params.pesos(arquetipo)), "cv_todos": 0.10,
         "eps1_consenso": True, "n_eps": 2}
    if arquetipo == "holding":
        p["soma_partes"] = {"nav": 100, "conferido": True, "razao_mediana": 0.8, "semanas": 60,
                            "partes": [{"emissor": "SIM_INVESTIDA", "valor_participacao": 100}],
                            "visao_casa": {"fator": 1.1, "partes": [
                                {"emissor": "SIM_INVESTIDA", "razao_v0_p0": 1.1}]}}
    return p, m


@pytest.mark.parametrize("arquetipo", ["banco", "seguradora", "holding"])
@pytest.mark.parametrize("item", ["capex", "d_a"])
def test_alerta_financeiro_irrelevante_permanece_visivel_sem_rebaixar_confianca(params, arquetipo, item):
    p, m = _financeira(params, arquetipo)
    p["alertas_fonte"][0]["item"] = item
    antes = deepcopy(p)
    legado = deepcopy(params)
    legado.sec("qualidade").pop("alertas_fonte_metodo")
    antigo = _g17(p, m, legado)
    atual = _g17(p, m, params)
    assert antigo["status"] == "aviso" and atual["status"] == "informativo"
    assert atual["avaliacao_alertas"][0]["alerta"] == p["alertas_fonte"][0]
    assert atual["avaliacao_alertas"][0]["dependencia"] == "nao_usado"
    assert atual["avaliacao_alertas"][0]["caminhos"]
    assert "não alimentam" in atual["detalhe"]
    assert p == antes
    assert confianca(p, {**m, "portoes": [antigo]}, params)[0] == "C"
    assert confianca(p, {**m, "portoes": [atual]}, params)[0] == "B"
    outro = {"codigo": "G11", "status": "aviso"}
    assert confianca(p, {**m, "portoes": [atual, outro]}, params)[0] == "C"


@pytest.mark.parametrize("nome", ["fcff", "fcff_real", "fcff_normalizado", "fcff_vida_finita",
                                  "regressao_ev_receita", "metodo_futuro"])
def test_metodo_ativo_ou_dissidente_com_dependencia_nao_certificada_conserva_aviso(params, nome):
    p, m = _financeira(params)
    # Valor negativo não entra na média, mas continua na dispersão/confiança.
    m["metodos"].append({"m": nome, "peso": 0.2, "valor": None, "valor_calculado": -3})
    g = _g17(p, m, params)
    assert g["status"] == "aviso"
    assert nome in g["dependencias_fluxos"]["metodos"]
    assert g["avaliacao_alertas"][0]["dependencia"] == "indeterminado"


def test_fcff_configurado_mas_ausente_do_relatorio_nao_certifica_independencia(params):
    p, m = _financeira(params)
    params.valuation["pesos_metodos"]["banco"]["fcff"] = 0.1
    assert _g17(p, m, params)["status"] == "aviso"


@pytest.mark.parametrize("modo", ["custo_ausente", "beta_desconhecido", "kd", "wacc", "peso_divida",
                                  "metodos_ausentes", "peso_desconhecido", "porte_alavancagem"])
def test_custo_metodo_ou_intermediario_transitivo_desconhecido_conserva_severidade(params, modo):
    p, m = _financeira(params)
    if modo == "custo_ausente":
        del m["custo_capital"]
    elif modo == "beta_desconhecido":
        m["custo_capital"]["beta_fonte"] = "estimativa futura"
    elif modo in ("kd", "wacc", "peso_divida"):
        m["custo_capital"][modo] = 0.05
    elif modo == "metodos_ausentes":
        m["metodos"] = []
    elif modo == "peso_desconhecido":
        del m["metodos"][0]["peso"]
    else:
        params.sec("persistencia_roe")["tamanho_variavel"] = "alavancagem"
    assert _g17(p, m, params)["status"] == "aviso"


@pytest.mark.parametrize("modo", ["nav_ausente", "partes_ausentes", "autorreferencia", "visao_desconhecida"])
def test_soma_partes_com_dependencia_transitiva_desconhecida_nao_isenta_fluxos(params, modo):
    p, m = _financeira(params, "holding")
    if modo == "nav_ausente":
        del p["soma_partes"]["nav"]
    elif modo == "partes_ausentes":
        p["soma_partes"]["partes"] = []
    elif modo == "autorreferencia":
        p["soma_partes"]["partes"][0]["emissor"] = p["issuer_id"]
    else:
        p["soma_partes"]["visao_casa"]["partes"][0]["emissor"] = "SIM_NAO_IDENTIFICADA"
    assert _g17(p, m, params)["status"] == "aviso"


def test_conferencia_so_dos_fluxos_certificados_e_todos_alertas_brutos_sao_preservados(params):
    p, m = _financeira(params)
    p["em_conferencia"] = [{"item": "capex", "data": "2026-06-30", "nota": "valor pendente"}]
    p["alertas_fonte"] *= 7
    bruto = deepcopy(p)
    g = _g17(p, m, params)
    assert g["status"] == "informativo" and len(g["avaliacao_alertas"]) == 8
    assert [a["alerta"] for a in g["avaliacao_alertas"]] == p["em_conferencia"] + p["alertas_fonte"]
    assert p == bruto
    p["em_conferencia"].append({"item": "lucro_liquido_controladores", "data": "2026-06-30"})
    assert _g17(p, m, params)["status"] == "aviso"


@pytest.mark.parametrize("item", ["cfo", "receita", "ebit", "patrimonio_controladores", "acoes_em_circulacao"])
def test_demais_itens_conservam_regra_historica(params, item):
    p, m = _financeira(params)
    p["alertas_fonte"][0]["item"] = item
    assert _g17(p, m, params)["status"] == "aviso"


def test_troca_de_moeda_nao_e_isentada_quando_o_fornecedor_associa_evento_a_capex(params):
    p, m = _financeira(params)
    p["alertas_fonte"][0]["tipo"] = "moeda_trocada"
    p["historico"] = {"receita": {"2025": 1}}
    g = _g17(p, m, params)
    assert g["status"] == "aviso" and "moeda" in g["avaliacao_alertas"][0]["motivo"]


@pytest.mark.parametrize("versao", ["2026-10.4", "2026-10.5"])
def test_sem_chave_historica_preserva_json_g17_exato(params, versao):
    params.valuation["versao"] = versao
    params.sec("qualidade").pop("alertas_fonte_metodo")
    p, m = _financeira(params)
    assert _g17(p, m, params) == {
        "codigo": "G17", "nome": "Alertas da fonte pública", "status": "aviso",
        "detalhe": "salto de magnitude a conferir na fonte: capex mudou"}
    p["alertas_fonte"] = []
    assert _g17(p, m, params) == {
        "codigo": "G17", "nome": "Alertas da fonte pública", "status": "ok",
        "detalhe": "sem alertas da fonte sobre os períodos usados"}


@pytest.mark.parametrize("valor", ["dependencias_efetiva", "nucleo", None, False])
def test_politica_desconhecida_e_recusada_na_leitura_da_configuracao(params, tmp_path, valor):
    params.sec("qualidade")["alertas_fonte_metodo"] = valor
    arq = tmp_path / "valuation.yaml"
    arq.write_text(yaml.safe_dump(params.valuation), encoding="utf-8")
    with pytest.raises(ValueError, match="alertas_fonte_metodo desconhecido"):
        carregar_parametros(arq)


@pytest.fixture(scope="module")
def universo_simulado():
    d = date(2026, 10, 8)
    md, params = make_synthetic_market(seed=7, as_of=d), carregar_parametros()
    dados = coletar(md, d, list(md.universe.issuers.index), list(md.universe.lines.index), [], offline=True)
    return preparar(md, dados, params, list(md.universe.issuers.index), d)


def _avaliar(p, ctx, params):
    return Avaliador(p, ctx, params, 0.045, {}).avaliar()


def test_financeiras_independentes_com_contexto_inteiro_reconstruido(params, universo_simulado):
    a, b = deepcopy(universo_simulado), deepcopy(universo_simulado)
    ids = [iid for iid, p in a.items() if p["financeira"] and p["arquetipo"] in ("banco", "seguradora")]
    assert ids
    for iid in ids:
        for k in ("capex", "d_a", "d_a_dfc", "ebitda"):
            b[iid][f"t.{k}"] = None
            b[iid]["historico"].pop(k, None)
    ca, cb = montar_contexto(a, params, 0.045), montar_contexto(b, params, 0.045)
    assert {k: v for k, v in ca.items() if k != "fundamentos"} == {k: v for k, v in cb.items() if k != "fundamentos"}
    for iid in ids:
        ma, mb = _avaliar(a[iid], ca, params), _avaliar(b[iid], cb, params)
        for k in ("metodos", "custo_capital", "tp", "tp_pessimista", "tp_otimista", "pwr", "cv_todos"):
            assert ma.get(k) == mb.get(k), (iid, k)
        prova = dependencia_fluxos_financeiros(a[iid], ma, params)
        assert prova["classificacao"] == "nao_usado", (iid, prova)


def test_modelo_aberto_exporta_todos_alertas_com_razao_e_caminho(params, universo_simulado):
    iid = next(i for i, p in universo_simulado.items() if p["financeira"] and p["arquetipo"] == "banco")
    p = deepcopy(universo_simulado[iid])
    p["alertas_fonte"] = [{"item": "capex", "tipo": "salto", "data": "2026-06-30",
                          "texto": f"DADOS SIMULADOS: alerta {n}"} for n in range(9)]
    ctx = montar_contexto({iid: p}, params, 0.045)
    av = Avaliador(p, ctx, params, 0.045, {})
    m = av.avaliar()
    m.update({"resumo": {}, "portoes": [_g17(p, m, params)]})
    ex = Execucao(as_of=date(2026, 10, 8), pacotes={iid: p}, contexto=ctx, modelos={iid: m}, etfs={},
                  rf={}, distribuicao={}, is_synthetic=True, emissores=[iid], registros={iid: av.reg})
    g = modelo_json(ex, iid, params)["portoes"][0]
    assert g["status"] == "informativo"
    assert [a["alerta"] for a in g["avaliacao_alertas"]] == p["alertas_fonte"]
    assert all(a["motivo"] and a["caminhos"] for a in g["avaliacao_alertas"])


def test_capex_consumido_por_fcff_preserva_aviso_c_e_direcao_economica(params, universo_simulado):
    iid = next(i for i, p in universo_simulado.items() if not p["financeira"] and p["arquetipo"] == "corporativo")
    p = deepcopy(universo_simulado[iid])
    p.update({"t.ebit": 100.0, "t.receita": 1000.0, "t.capex": 30.0, "t.d_a_dfc": 25.0,
              "t.variacao_capital_giro_operacional": 5.0, "t.adicoes_direito_uso": 20.0,
              "moeda_demonstrativos": p["moeda"],
              "periodos_fluxos": {k: "TTM|2026-06-30" for k in (*COMPONENTES, "receita")},
              "bases_fluxos": {k: "consolidado" for k in (*COMPONENTES, "receita")},
              "moedas_fluxos": {k: p["moeda"] for k in (*COMPONENTES, "receita")},
              "alertas_fonte": [{"item": "capex", "tipo": "salto", "data": "2026-06-30", "texto": "capex mudou"}]})
    # Escala coerente da ponte patrimonial; nenhum alvo/preço determina RR.
    p.update({"divida_liquida": 30.0, "divida_bruta": 50.0, "arrendamentos": 20.0,
              "valor_mercado": 500.0, "t.patrimonio_controladores": 300.0, "minoritarios": 0.0,
              "unidades": 10.0})
    ctx = montar_contexto({iid: p}, params, 0.045)
    av = Avaliador(p, ctx, params, 0.045, {})
    av.preparar_metodos()
    outro = Avaliador({**p, "t.capex": 50.0}, ctx, params, 0.045, {})
    outro.preparar_metodos()
    assert av.rr_obs is not None and outro.rr_obs > av.rr_obs
    assert float(outro._valor_metodo("fcff", Drivers())) < float(av._valor_metodo("fcff", Drivers()))
    mod = av.avaliar()
    assert any(m["m"] == "fcff" and m["valor"] is not None for m in mod["metodos"])
    g = _g17(p, mod, params)
    assert g["status"] == "aviso"
    assert confianca(p, {**mod, "portoes": [g]}, params)[0] == "C"


def test_da_transitiva_em_ebitda_move_regressao_ev_receita_e_conserva_aviso(params, universo_simulado):
    iid = next(i for i, p in universo_simulado.items() if not p["financeira"] and p["arquetipo"] == "corporativo")
    p = {**deepcopy(universo_simulado[iid]), "t.ebit": 100.0, "t.ebitda": None, "t.d_a": 20.0,
         "divida_liquida": 60.0, "alertas_fonte": [{"item": "d_a", "tipo": "salto",
                                                    "data": "2026-06-30", "texto": "D&A mudou"}]}
    c1 = montar_contexto({iid: p}, params, 0.045)
    c2 = montar_contexto({iid: {**p, "t.d_a": 40.0}}, params, 0.045)
    f1, f2 = c1["fundamentos"][iid], c2["fundamentos"][iid]
    assert f2["alavancagem"] < f1["alavancagem"]
    reg = {"disponivel": True, "colunas": ["intercepto", "alavancagem"], "coef": [2.0, -1.0],
           "regressores": ["alavancagem"], "efeitos": [], "limites": [0.1, 5.0]}
    assert prever(reg, f2, p["pais"]) > prever(reg, f1, p["pais"])
    _, m = _financeira(params)
    m["metodos"].append({"m": "regressao_ev_receita", "peso": 0.1, "valor": 10})
    assert _g17(p, m, params)["status"] == "aviso"
