"""Dossiês por ativo: cobertura completa, cautela econômica, cortes e conteúdo não confiável."""
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from cdp.workflow import teses_ativos as ta


def _arquivos(iids=("BR_EMPRESA", "ETF_REGIONAL"), *, citavel=False):
    universo, modelos = [], {}
    for iid in iids:
        etf = iid.startswith("ETF_")
        u = {"iid": iid, "nome": "Empresa <script>alert(1)</script>" if not etf else "ETF regional",
             "ticker": "SIM", "tipo": "etf" if etf else "acao", "pais_nome": "Brasil",
             "setor_nome": "ETF" if etf else "Financeiro", "arquetipo_nome": "ETF" if etf else "Bancos",
             "rating": "Neutra" if etf else "Em revisão", "preco_texto": "US$ 7,00",
             "alvo_texto": "Em revisão", "upside_texto": "não disponível",
             "etr_texto": "não disponível", "preco_data": "2026-10-08", "citavel": citavel}
        universo.append(u)
        modelos[iid] = {"iid": iid, "arquetipo": "Bancos", "indice": "Índice regional",
                        "cabecalho": [{"t": "Preço-alvo", "v": "Em revisão"}],
                        "fontes": [{"doc": "Fonte <img src=x onerror=alert(1)>", "fonte": "RI",
                                    "url": "javascript:alert(1)"}], "portoes": [{"t": "Ações",
                                    "s": "Bloqueio", "d": "Denominador não reconciliado"}]}
    return {"cobertura.json": json.dumps({"meta": {"estado": "publicado", "as_of": "2026-10-09",
                                              "is_synthetic": True, "files": {"modelos": [{"file": "cobertura-modelo-1.json"}]}},
                                        "universe": universo}),
            "cobertura-modelo-1.json": json.dumps({"modelos": modelos})}


def test_cada_ativo_tem_documento_sem_inventar_tese_qualitativa():
    docs = ta.documentos(_arquivos(), {})
    assert [d["endereco"] for d in docs] == ["ativos/br_empresa/", "ativos/etf_regional/"]
    assert all(d["estado_pesquisa"] == "analise_quantitativa_preliminar" for d in docs)
    body = ta.corpo(docs[0])
    assert "Análise quantitativa preliminar" in body
    assert "alvo agregado não é citável" in body and "Denominador não reconciliado" in body
    assert "O preço de referência é" not in body
    assert "ainda não estabelece uma tese qualitativa específica" in body
    etf = ta.corpo(docs[1])
    assert "não mede a aderência ao índice contratual" in etf
    assert "Spread, prêmio ou desconto" in etf
    assert "DADOS SIMULADOS" in ta.markdown(docs[0])
    assert "## Valuation e premissas" in ta.markdown(docs[0])


def test_textos_e_urls_externos_sao_dados_nao_executaveis():
    body = ta.corpo(ta.documentos(_arquivos(), {})[0])
    assert "<script>alert" not in body and "<img src=x" not in body
    assert "&lt;script&gt;" in body and "&lt;img" in body
    assert 'href="javascript:' not in body


@pytest.mark.parametrize("iid", ["../livro", "A/B", "A.B", "", "x" * 65])
def test_identificador_nao_pode_criar_rota_arbitraria(iid):
    with pytest.raises(ValueError):
        ta.caminho(iid)


def test_colisao_de_rotas_e_modelo_ausente_recusados():
    with pytest.raises(ValueError, match="duplicado"):
        ta.documentos(_arquivos(("BR_A", "br_a")), {})
    a = _arquivos()
    a["cobertura-modelo-1.json"] = '{"modelos": {}}'
    with pytest.raises(ValueError, match="sem modelo"):
        ta.documentos(a, {})


def test_cobertura_em_verificacao_nao_vira_dossie():
    a = _arquivos()
    d = json.loads(a["cobertura.json"])
    d["meta"]["estado"] = "em_verificacao"
    a["cobertura.json"] = json.dumps(d)
    assert ta.documentos(a, {}) == []


def test_nota_futura_ou_de_outro_emissor_nao_contamina_visao():
    for doc in [{"issuer_id": "BR_OUTRA", "data": "2026-10-08"},
                {"issuer_id": "BR_EMPRESA", "data": "2026-10-10"}]:
        with pytest.raises(ValueError, match="Nota incompatível"):
            ta.documentos(_arquivos(), {"BR_EMPRESA": {"documento": doc}})


def test_geracao_deterministica_e_sem_mutar_insumos():
    a = _arquivos()
    original = dict(a)
    x = ta.documentos(a, {})
    y = ta.documentos(a, {})
    assert x == y and ta.corpo(x[0]) == ta.corpo(y[0])
    assert a == original


def test_paginas_completas_downloads_e_simulacao(tmp_path, monkeypatch):
    from cdp import site

    monkeypatch.setattr(ta, "carregar_notas", lambda rt, ate: {})
    cfg = {"base_url": "https://exemplo.test/cdp", "titulo_curto": "CDP",
           "repositorio": "exemplo/cdp", "autor": "CDP", "idioma": "pt-BR"}
    rotas = site.construir_analises(SimpleNamespace(), _arquivos(), cfg, tmp_path,
                                   indexar=False, demo=True, commit="a" * 40,
                                   agora=datetime(2026, 10, 11, tzinfo=ZoneInfo("America/Sao_Paulo")))
    assert set(rotas) == {"ativos/br_empresa/", "ativos/etf_regional/"}
    paginas = [tmp_path / "ativos/index.html", *(tmp_path / r / "index.html" for r in rotas)]
    for p in paginas:
        h = p.read_text()
        assert h.startswith('<!doctype html>\n<html lang="pt-BR">')
        assert "DADOS SIMULADOS" in h and "noindex" in h
        assert "Content-Security-Policy" in h and 'src="' in h
        assert '<link rel="canonical" href="https://exemplo.test/cdp/ativos/' in h
    for r in rotas:
        d = json.loads((tmp_path / r / "analise.json").read_bytes())
        assert d["dados_simulados"] is True and d["endereco"] == r
        assert "DADOS SIMULADOS" in (tmp_path / r / "analise.md").read_text()
        assert 'href="analise.md" download' in (tmp_path / r / "index.html").read_text()
