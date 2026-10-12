"""Cases DADOS SIMULADOS: grupos econômicos, cortes e apresentação determinística."""
import copy
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from cdp.workflow import dashboard_cases as dc
from cdp.workflow import teses_ativos as ta


def documento(iid="BR_A", *, nome="Banco A", pais="BR", setor="FIN",
              arquetipo="Bancos", etr=0.15, tipo="acao", citavel=True):
    ativo = {"iid": iid, "nome": nome, "ticker": iid, "tipo": tipo,
             "pais": pais, "pais_nome": {"BR": "Brasil", "CL": "Chile"}.get(pais, pais),
             "setor": setor, "setor_nome": "Financeiro" if setor == "FIN" else setor,
             "arquetipo_nome": arquetipo, "moeda": "BRL", "preco": 10.0,
             "preco_texto": "R$ 10,00", "preco_data": "2026-10-08",
             "etr": etr, "etr_texto": "+15,0%", "data_modelo": "2026-10-09",
             "rating": "Compra" if citavel else "Em revisão", "citavel": citavel,
             "confianca": "A"}
    modelo = {"iid": iid, "arquetipo": arquetipo, "as_of": "2026-10-09",
              "metodos": [{"t": "Lucro residual", "peso": "70%"},
                          {"t": "P/VP justificado", "peso": "30%"}],
              "portoes_resumo": "7 conferidos · 0 bloqueios", "indice": "Índice " + iid,
              "rating_motivo": "Modelo público recebido"}
    # Passa pelo compositor público nativo; não cria writer, coleta ou modelo novo.
    arquivos = {"cobertura.json": json.dumps({"meta": {"estado": "publicado",
                    "as_of": "2026-10-09", "is_synthetic": True,
                    "files": {"modelos": [{"file": "cobertura-modelo-1.json"}]}},
                    "universe": [ativo]}),
                "cobertura-modelo-1.json": json.dumps({"modelos": {iid: modelo}})}
    return ta.documentos(arquivos, {})[0]


def caso(dashboard, iid):
    return next(c for c in dashboard["casos"] if c["iid"] == iid)


def test_peergrupo_local_regional_por_setor_pais_e_metodo_sem_alargamento():
    docs = [documento(), documento("BR_B", nome="Banco B"),
            documento("CL_C", nome="Banco C", pais="CL"),
            documento("BR_D", arquetipo="Seguradoras"), documento("BR_E", setor="IND")]
    d = dc.construir_dashboard_cases(docs)
    g = caso(d, "BR_A")["comparaveis"]
    assert g["local"] == ["BR_B"] and g["regional"] == ["BR_B", "CL_C"]
    assert caso(d, "BR_D")["comparaveis"]["local"] == []
    assert "Mesmo setor e enquadramento" in g["criterio"]


@pytest.mark.parametrize("campo", ["setor", "arquetipo_nome", "pais"])
def test_classificacao_ausente_nao_forma_grupo_de_equivalencia(campo):
    a, b = documento(), documento("BR_B")
    for doc in (a, b):
        doc["ativo"][campo] = "Não disponível"
    g = caso(dc.construir_dashboard_cases([a, b]), "BR_A")["comparaveis"]
    assert g["local"] == []
    if campo != "pais":
        assert g["regional"] == []


def test_etfs_separados_indices_diferentes_comparacao_produtos():
    d = dc.construir_dashboard_cases([documento(), documento("ETF_A", tipo="etf"),
        documento("ETF_B", tipo="etf"), documento("ETF_C", tipo="etf", pais="CL")])
    assert caso(d, "BR_A")["comparaveis"]["regional"] == []
    etf = caso(d, "ETF_A")
    assert etf["comparaveis"]["local"] == ["ETF_B"]
    assert etf["comparaveis"]["regional"] == ["ETF_B", "ETF_C"]
    assert "Comparação de produtos" in etf["comparaveis"]["criterio"]
    assert "não implica equivalência" in etf["comparaveis"]["limite"]
    assert d["indicadores"]["companhias"] == 1 and d["indicadores"]["etfs"] == 3


def test_grupo_estatistico_literal_nao_usa_quantidade_de_peers_economicos():
    a, b = documento(), documento("BR_B")
    a["modelo"]["pares"] = {"grupo": "Financeiro (América Latina)",
                             "n": 32, "mediana": "+14,6%", "itens": []}
    d = dc.construir_dashboard_cases([a, b])
    c = caso(d, "BR_A")
    assert c["comparacao_modelo"] == {"grupo": "Financeiro (América Latina)",
                                      "n": 32, "mediana": "+14,6%"}
    assert c["comparaveis"]["local"] == ["BR_B"]
    body = dc.renderizar_dashboard_cases(d)
    assert "Grupo do modelo: Financeiro (América Latina) · n=32 · mediana do α: +14,6%" in body
    assert "a seleção não recalcula o grupo estatístico" in body


@pytest.mark.parametrize("n", [None, True, -1, 32.0])
def test_amostra_ausente_ou_invalida_nao_empresta_tamanho_do_grupo(n):
    doc = documento()
    doc["modelo"]["pares"] = {"n": n}
    c = caso(dc.construir_dashboard_cases([doc]), "BR_A")
    assert c["comparacao_modelo"] == {"grupo": "n/d", "n": None, "mediana": "n/d"}
    assert "n=n/d" in dc.renderizar_dashboard_cases(dc.construir_dashboard_cases([doc]))


def test_grupo_e_mediana_nao_sao_calculados_e_texto_recebido_e_escapado():
    doc = documento()
    doc["modelo"]["pares"] = {"grupo": '<script>grupo</script>', "n": 0,
                               "mediana": '<img src=x>', "itens": [{"v": "+100%"}]}
    d = dc.construir_dashboard_cases([doc])
    assert caso(d, "BR_A")["comparacao_modelo"]["n"] == 0
    assert caso(d, "BR_A")["comparacao_modelo"]["mediana"] == '<img src=x>'
    body = dc.renderizar_dashboard_cases(d)
    assert "&lt;script&gt;grupo&lt;/script&gt;" in body
    assert "&lt;img src=x&gt;" in body and '<img src=x>' not in body


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True])
def test_retorno_ausente_ou_nao_finito_nunca_vira_zero(value):
    c = caso(dc.construir_dashboard_cases([documento(etr=value)]), "BR_A")
    assert c["etr"] is None and c["etr_texto"] == "n/d"
    assert c["ratios"] == "n/d" and "denominador" in c["limite_ratios"]


def test_preco_corte_qualidade_confianca_metodos_e_gate_citavel_preservados():
    doc = documento(citavel=False)
    c = caso(dc.construir_dashboard_cases([doc]), "BR_A")
    assert c["preco_texto"] == "R$ 10,00" and c["moeda"] == "BRL"
    assert c["preco_data"] == "2026-10-08" and c["corte_modelo"] == "2026-10-09"
    assert c["etr"] is None and c["etr_texto"] == "n/d"
    assert c["confianca"] == "A" and c["qualidade"] == "7 conferidos · 0 bloqueios"
    assert c["metodos"] == "Lucro residual (70%) · P/VP justificado (30%)"
    doc["origem_modelo"]["sha256"] = "hash ausente"
    doc["ativo"]["citavel"] = True
    assert not caso(dc.construir_dashboard_cases([doc]), "BR_A")["citavel"]


def nota(doc, data="2026-10-08", *, autoria="mente", sha="a" * 64):
    doc["estado_pesquisa"] = "nota_publicada"
    doc["nota"] = {"documento": {"issuer_id": doc["ativo"]["iid"], "data": data,
                                 "autoria": autoria}, "sha256": sha}
    return doc


def test_corte_pesquisa_posterior_conserva_nota_e_modelo_em_datas_distintas():
    doc = nota(documento(), "2026-10-11")
    doc["corte_pesquisa"] = "2026-10-11"
    c = caso(dc.construir_dashboard_cases([doc]), "BR_A")
    assert c["nota"]["href"] == "../ativos/br_a/#tese"
    assert c["nota"]["data"] == "2026-10-11"
    assert c["corte_cobertura"] == c["corte_modelo"] == "2026-10-09"
    assert c["preco_data"] == "2026-10-08"
    del doc["corte_pesquisa"]
    assert caso(dc.construir_dashboard_cases([doc]), "BR_A")["nota"]["href"] is None


@pytest.mark.parametrize("change", ["futura", "draft", "hash", "emissor", "estado"])
def test_draft_nota_futura_ou_sem_identidade_nao_promovidos(change):
    doc = nota(documento())
    if change == "futura":
        doc["nota"]["documento"]["data"] = "2026-10-12"
    elif change == "draft":
        doc["nota"]["documento"]["autoria"] = "rascunho"
    elif change == "hash":
        doc["nota"]["sha256"] = ""
    elif change == "emissor":
        doc["nota"]["documento"]["issuer_id"] = "BR_OUTRO"
    else:
        doc["estado_pesquisa"] = "analise_quantitativa_preliminar"
    d = dc.construir_dashboard_cases([doc])
    assert caso(d, "BR_A")["nota"]["href"] is None
    assert d["indicadores"]["narrativas_publicadas"] == 0


def test_ordenacao_python_finite_missing_last_nao_ordena_preco_nominal():
    a, b, c = documento("BR_A", nome="Zeta", etr=0.3), documento("BR_B", nome="Álfa", etr=0.1), documento("BR_C", nome="Gama", etr=None)
    a["ativo"]["preco"] = 1.0
    b["ativo"]["preco"] = 9000.0
    c["ativo"]["data_modelo"] = "2026-10-10"
    d = dc.construir_dashboard_cases([a, b, c])
    assert d["ordens"]["nome"] == ["BR_B", "BR_C", "BR_A"]
    assert d["ordens"]["etr"] == ["BR_A", "BR_B", "BR_C"]
    assert d["ordens"]["corte"][0] == "BR_C"
    assert "preco" not in d["ordens"]
    assert caso(d, "BR_A")["ordinais"]["etr"] == "000000"


def test_determinismo_nonmutation_e_folha_sem_io(monkeypatch):
    import builtins

    docs = [documento(), documento("BR_B")]
    before = copy.deepcopy(docs)
    monkeypatch.setattr(builtins, "open", lambda *a, **k: pytest.fail("Dashboard tentou I/O"))
    first = dc.construir_dashboard_cases(docs)
    assert first == dc.construir_dashboard_cases(list(reversed(docs)))
    assert dc.renderizar_dashboard_cases(first) == dc.renderizar_dashboard_cases(first)
    assert docs == before


def test_escaping_rotas_seguras_fragmento_acessivel_e_recursos_locais():
    doc = documento(nome='Empresa <img src=x onerror="alert(1)">')
    doc["modelo"]["metodos"][0]["t"] = "</option><script>alert(1)</script>"
    d = dc.construir_dashboard_cases([doc])
    body = dc.renderizar_dashboard_cases(d)
    assert '<img src=x' not in body and '<script>alert' not in body
    assert '&lt;img' in body and '&lt;/option&gt;' in body
    assert 'href="../ativos/br_a/"' in body and 'href="../dashboard-cases.css"' in body
    assert 'src="../dashboard-cases.js"' in body and 'scope="col"' in body
    assert 'aria-live="polite"' in body and "DADOS SIMULADOS" in body
    assert '<html' not in body and '<body' not in body and 'https://' not in body

    class Estrutura(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if "id" in a:
                self.ids.append(a["id"])

    parser = Estrutura()
    parser.feed(body)
    assert len(parser.ids) == len(set(parser.ids))
    d["casos"][0]["href"] = "javascript:alert(1)"
    with pytest.raises(ValueError, match="rotas públicas"):
        dc.renderizar_dashboard_cases(d)


def test_javascript_nao_recalcula_estatisticas_e_usa_ordinais_recebidos():
    js = Path(dc.__file__).with_suffix(".js").read_text()
    assert "data-ord-" in js and "new URLSearchParams" in js
    assert "innerHTML" not in js and "fetch(" not in js and "eval(" not in js
    assert "parseFloat" not in js and ".reduce(" not in js


def test_latam_pais_ou_regiao_preserva_membros_locais_brasileiros_e_ordinais():
    docs = [documento("LA_PAAS", nome="Pan American", pais="LATAM"),
            documento("LA_FORTUNA", nome="Fortuna", pais="LATAM"),
            documento("BR_A"), documento("BR_B", nome="Banco B")]
    for doc in docs[:2]:
        doc["ativo"]["pais_nome"] = "Regional (América Latina)"
    d = dc.construir_dashboard_cases(docs)
    before = copy.deepcopy(d)
    assert caso(d, "LA_PAAS")["comparaveis"]["local"] == ["LA_FORTUNA"]
    assert caso(d, "BR_A")["comparaveis"]["local"] == ["BR_B"]
    assert caso(d, "LA_PAAS")["comparaveis"]["regional"] == ["BR_A", "BR_B", "LA_FORTUNA"]
    assert caso(d, "LA_PAAS")["pais"] == "LATAM"
    assert caso(d, "BR_A")["pais"] == "BR"
    body = dc.renderizar_dashboard_cases(d)
    assert '<option value="local">Mesmo país ou região</option>' in body
    assert 'aria-label="País ou região"' in body
    assert '<th scope="col">País ou região / setor</th>' in body
    assert "país ou região restringe o grupo local" in caso(d, "LA_PAAS")["comparaveis"]["criterio"]
    assert 'data-local="LA_FORTUNA"' in body and 'data-local="BR_B"' in body
    assert d == before


@pytest.mark.parametrize("tipo", ["acao", "etf"])
def test_retorno_total_12_meses_preserva_valores_cortes_e_ordinais(tipo):
    doc = documento("ETF_A" if tipo == "etf" else "BR_A", tipo=tipo)
    d = dc.construir_dashboard_cases([doc])
    before = copy.deepcopy(d)
    c = d["casos"][0]
    assert c["etr"] == 0.15 and c["etr_texto"] == "+15,0%"
    assert c["preco_data"] == "2026-10-08" and c["corte_modelo"] == "2026-10-09"
    body = dc.renderizar_dashboard_cases(d)
    assert '<dt>Retorno total esperado · 12 meses</dt>' in body
    assert '<th scope="col">Retorno total esperado · 12 meses</th>' in body
    assert '<dd>+15,0%</dd>' in body
    assert "Retorno total esperado · 12 meses · citável" in body
    assert "Retorno esperado não é retorno realizado" in body
    assert d == before


@pytest.mark.parametrize("iid", ["../A", "A/B", "A.B", "", "x" * 65])
def test_rota_arbitraria_recusada(iid):
    d = documento()
    d["ativo"]["iid"] = iid
    with pytest.raises(ValueError, match="Identificador"):
        dc.construir_dashboard_cases([d])


def test_duplicacao_e_recorte_vazio_explicitos():
    with pytest.raises(ValueError, match="duplicados"):
        dc.construir_dashboard_cases([documento(), documento("br_a")])
    d = dc.construir_dashboard_cases([])
    assert d["indicadores"]["total"] == 0 and d["casos"] == []
    assert "Não há dossiês públicos" in dc.renderizar_dashboard_cases(d)
