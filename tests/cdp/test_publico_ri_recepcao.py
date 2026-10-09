"""DADOS SIMULADOS: parser e fluxo público RI, sem PDF real, rede ou origem privada.

As datas de recepção vêm do Arquivo temporário. Não representam publicação,
PIT/vintage histórico, conta de ações ou confiança financeira certificada.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from cdp.cobertura import fontes
from cdp.cobertura.insumos import Demonstrativos, preparar_emissor
from cdp.cobertura.parametros import carregar_parametros
from cdp.data import publico, publico_fatos, publico_ri
from cdp.data.publico_arquivo import Arquivo
from cdp.data.synthetic import make_synthetic_market
from cdp.universe import load_universe
from cdp.workflow.demo import DemoStore

BASE = date(2026, 10, 7)
DIA = date(2026, 10, 8)
RECEBIDO = datetime(2026, 10, 8, 0, 8, 7, 123456, tzinfo=UTC)
AGORA = datetime(2026, 10, 9, 12, tzinfo=UTC)
ENTIDADE = "DADOS SIMULADOS SOCIEDAD ANONIMA"
UNIDADE = "Amounts expressed in millions of United States dollars"


def _pdf(paginas):
    """PDF vetorial pequeno; o leitor real extrai todos os títulos e células."""
    writer = PdfWriter()
    for texto in paginas:
        pagina = writer.add_blank_page(width=612, height=792)
        fonte = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                  NameObject("/Subtype"): NameObject("/Type1"),
                                  NameObject("/BaseFont"): NameObject("/Helvetica"),
                                  NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
        pagina[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
            DictionaryObject({NameObject("/F1"): writer._add_object(fonte)})})
        comandos = ["BT /F1 9 Tf 30 760 Td 12 TL"]
        for linha in texto.splitlines():
            escaped = linha.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            comandos.append(f"({escaped}) Tj T*")
        comandos.append("ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(comandos).encode("cp1252"))
        pagina[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _documento(iid="DADOS_SIMULADOS", *, anual=False):
    if anual:
        bp_periodos = [(None, f"{y}-12-31") for y in (2025, 2024, 2023)]
        dre_periodos = [(f"{y}-01-01", f"{y}-12-31") for y in (2025, 2024, 2023)]
        bp_decl = "AS OF DECEMBER 31, 2025, 2024 AND 2023"
        dre_decl = "FOR THE YEARS ENDED DECEMBER 31, 2025, 2024 AND 2023"
        bp_cols = dre_cols = "Notes 2025 2024 2023"
        bp_values, revenues, ni, parent, da = "70 60 50", "100 90 80", "15 14 13", "10 9 8", "0 - 2"
    else:
        bp_periodos = [(None, "2026-06-30"), (None, "2025-12-31")]
        dre_periodos = [("2026-01-01", "2026-06-30"), ("2025-01-01", "2025-06-30"),
                        ("2026-04-01", "2026-06-30"), ("2025-04-01", "2025-06-30")]
        bp_decl = "AS OF JUNE 30, 2026 AND DECEMBER 31, 2025"
        dre_decl = "FOR THE SIX AND THREE-MONTH PERIODS ENDED JUNE 30, 2026 AND 2025"
        bp_cols, dre_cols = "Notes 2026 2025", "Notes 2026 2025 2026 2025"
        bp_values, revenues, ni, parent, da = "80 70", "60 50 35 30", "12 10 7 6", "7 5 4 (3)", "0 - 0 -"
    bp_text = f"""{ENTIDADE}
CONSOLIDATED STATEMENT OF FINANCIAL POSITION
{bp_decl}
{UNIDADE}
{bp_cols}
Parent equity {bp_values}
TOTAL ASSETS {bp_values}
LIABILITIES
Parent equity 999 888"""
    dre_text = f"""{ENTIDADE}
CONSOLIDATED STATEMENT OF COMPREHENSIVE INCOME
{dre_decl}
{UNIDADE}
{dre_cols}
Revenues {revenues}
Net profit {ni}
Depreciation {da}
Net profit for the period attributable to:
Shareholders of the parent company {parent}
Other comprehensive income:
Shareholders of the parent company 999 888"""
    paginas = [bp_text, dre_text]
    raw = _pdf(paginas)

    def tabela(pagina, tipo, header, periodos, itens):
        return {"pagina": pagina, "demonstrativo": tipo,
                "ancoras": ["CONSOLIDATED STATEMENT OF FINANCIAL POSITION" if tipo == "BP"
                            else "CONSOLIDATED STATEMENT OF COMPREHENSIVE INCOME", UNIDADE],
                "cabecalho_colunas": header,
                "colunas": [{"rotulo": fim[:4], **({"inicio": ini} if ini else {}), "fim": fim}
                            for ini, fim in periodos],
                "moeda": "USD", "escala": 1_000_000,
                "itens": {item: {"rotulos": [label]} for item, label in itens.items()}}

    bp = tabela(1, "BP", bp_cols, bp_periodos,
                {"patrimonio_controladores": "Parent equity", "ativo_total": "TOTAL ASSETS"})
    bp["fim_tabela"] = "LIABILITIES"
    dre = tabela(2, "DRE", dre_cols, dre_periodos,
                 {"receita": "Revenues", "lucro_liquido": "Net profit", "d_a_dfc": "Depreciation"})
    dre["fim_tabela"] = "Other comprehensive income:"
    atribuicao = tabela(2, "DRE", dre_cols, dre_periodos,
                       {"lucro_liquido_controladores": "Shareholders of the parent company"})
    atribuicao.update(inicio_tabela="Net profit for the period attributable to:",
                      fim_tabela="Other comprehensive income:")
    nome = "DADOS_SIMULADOS_ANUAL.pdf" if anual else "DADOS_SIMULADOS_SEMESTRAL.pdf"
    doc = {"issuer_id": iid, "sha256": hashlib.sha256(raw).hexdigest(),
           "data_publicacao": None, "entidade_documento": ENTIDADE,
           "disponibilidade_tipo": "recepcao_observada", "documento": nome,
           "url": "https://example.invalid/DADOS_SIMULADOS/" + nome,
           "tabelas": [bp, dre, atribuicao]}
    return raw, doc, paginas


@pytest.fixture(autouse=True)
def relogio_simulado(monkeypatch):
    monkeypatch.setattr(publico_fatos, "_agora_observado", lambda: AGORA)


@pytest.fixture(scope="module")
def mercado():
    md = DemoStore(make_synthetic_market(seed=7, as_of=DIA)).load(BASE)
    # Exercita o adaptador público, com todas as linhas ainda rotuladas DADOS SIMULADOS.
    md = replace(md, manifest=md.manifest.model_copy(update={"is_synthetic": False}))
    iid = next(i for i, r in md.universe.issuers.iterrows()
               if r["country"] == "AR" and r["gics_sector"] != "Financials")
    assert iid not in load_universe().issuers.index
    return SimpleNamespace(md=md, iid=iid, tickers=list(md.universe.lines_for(iid).index))


def _params(*, observado=True, temporal=True):
    params = carregar_parametros()
    val = copy.deepcopy(params.valuation)
    val["qualidade"].pop("ri_disponibilidade_metodo", None)
    if observado:
        val["qualidade"]["demonstrativos_disponibilidade_metodo"] = "recepcao_observada"
    else:
        val["qualidade"].pop("demonstrativos_disponibilidade_metodo", None)
    if temporal:
        val["projecao"]["resultado_corte_metodo"] = "base_preco_conhecimento_explicitos"
    else:
        val["projecao"].pop("resultado_corte_metodo", None)
    # Os outros opt-ins têm contratos e testes próprios; esta prova é da fonte PDF normal.
    val["projecao"].pop("normalizacao_resultado_metodo", None)
    return replace(params, valuation=val)


@pytest.fixture
def ambiente(tmp_path, monkeypatch, mercado):
    catalogo = tmp_path / "catalogo.json"
    docs, raws, regs = [], {}, []
    root = tmp_path / "arquivo"
    for anual, clock in [(False, RECEBIDO), (True, RECEBIDO + timedelta(minutes=1))]:
        raw, doc, _ = _documento(mercado.iid, anual=anual)
        docs.append(doc)
        raws[doc["documento"]] = raw
        arq = Arquivo(root, agora=lambda clock=clock: clock, conhecimento_ate=clock)
        regs.append(arq.gravar(f"RI/demonstrativos/{mercado.iid}/{doc['documento']}",
                               "RI", doc["url"], raw))
    catalogo.write_text(json.dumps({"schema": "cdp.ri_demonstrativos/v1", "documentos": docs}))
    monkeypatch.setattr(publico_ri, "CATALOGO_RI", catalogo)
    mestre = pd.DataFrame([{"issuer_id": mercado.iid, "cnpj": None, "cik": None}]).set_index("issuer_id")
    monkeypatch.setattr(publico, "mestre_publico", lambda *a, **kw: mestre)
    # Sem complementação externa: a API permanece real até selecionar_pit e normalizar.
    monkeypatch.setattr(publico, "_parte_yahoo", lambda *a, **kw: None)
    for name in ("consenso_publico", "dividendos", "eventos_corporativos", "taxas_publicas", "free_float", "composicao_etf"):
        monkeypatch.setattr(publico, name, lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(fontes, "contas_suplementares_cvm", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(fontes, "capital_oficial", lambda *a, **kw: pd.DataFrame())
    return SimpleNamespace(**vars(mercado), root=root, docs=docs, raws=raws, regs=regs,
                           params=_params(), tmp=tmp_path)


def _normal(a, corte, *, civil=DIA, observado=True):
    return publico.demonstrativos([a.iid], civil, root=a.root, universe=a.md.universe,
                                  offline=True, complementar_yahoo=False,
                                  conhecimento_ate=corte if observado else None,
                                  selecionar_ri_observado=observado)


def test_pdf_ingles_parent_total_sinal_escala_zero_e_ausencia():
    raw, doc, _ = _documento()
    assert len(raw) < 10_000
    f = publico_ri.fatos_pdf_ri(raw, doc, as_of=DIA, recebido_em=RECEBIDO)
    sem = f[(f["period_start"] == pd.Timestamp("2026-01-01")) & (f["period_end"] == pd.Timestamp("2026-06-30"))]
    v = sem.set_index("item")["value"].to_dict()
    assert Decimal(str(v["receita"])) == Decimal(60) * Decimal(1_000_000)
    assert v["lucro_liquido_controladores"] == 7_000_000 and v["lucro_liquido"] == 12_000_000
    assert v["d_a_dfc"] == 0
    assert not f[(f["item"] == "d_a_dfc") & (f["period_end"] == pd.Timestamp("2025-06-30"))].shape[0]
    assert f[(f["item"] == "lucro_liquido_controladores") & (f["period_start"] == pd.Timestamp("2025-04-01"))].iloc[0]["value"] == -3_000_000
    assert f["currency"].eq("USD").all() and f["received_date"].eq(pd.Timestamp(RECEBIDO)).all()
    assert f["data_publicacao_primaria"].isna().all() and f["data_recebimento_documento"].isna().all()


@pytest.mark.parametrize("erro", ["hash", "moeda", "escala", "periodo", "grao", "colunas", "entidade", "individual", "publicacao", "delimitador"])
def test_pdf_recusa_contrato_literal_inconsistente(erro):
    raw, doc, paginas = _documento()
    if erro == "hash":
        raw += b"DADOS SIMULADOS alterados"
    elif erro == "moeda":
        doc["tabelas"][0]["moeda"] = "ARS"
    elif erro == "escala":
        doc["tabelas"][0]["escala"] = 1000
    elif erro == "periodo":
        doc["tabelas"][0]["colunas"][0]["fim"] = "2026-09-30"
    elif erro == "grao":
        doc["tabelas"][1]["colunas"][0]["inicio"] = "2026-04-01"
    elif erro == "colunas":
        doc["tabelas"][1]["colunas"].reverse()
    elif erro == "entidade":
        doc["entidade_documento"] = "OUTRA ENTIDADE DADOS SIMULADOS"
    elif erro == "individual":
        paginas[0] = paginas[0].replace("CONSOLIDATED", "INDIVIDUAL")
        raw = _pdf(paginas)
        doc["sha256"] = hashlib.sha256(raw).hexdigest()
        doc["tabelas"][0]["ancoras"][0] = "INDIVIDUAL STATEMENT OF FINANCIAL POSITION"
    elif erro == "publicacao":
        doc["data_publicacao"] = "2026-10-08"
    elif erro == "delimitador":
        doc["tabelas"][2]["inicio_tabela"] = "BLOCO INEXISTENTE DADOS SIMULADOS"
    with pytest.raises(ValueError):
        publico_ri.fatos_pdf_ri(raw, doc, as_of=DIA, recebido_em=RECEBIDO)


def test_pdf_ars_literal_preserva_moeda_sem_override_global():
    _, doc, paginas = _documento()
    paginas = [p.replace("United States dollars", "Argentine pesos") for p in paginas]
    raw = _pdf(paginas)
    doc["sha256"] = hashlib.sha256(raw).hexdigest()
    for tabela in doc["tabelas"]:
        tabela["moeda"] = "ARS"
        tabela["ancoras"][1] = tabela["ancoras"][1].replace("United States dollars", "Argentine pesos")
    f = publico_ri.fatos_pdf_ri(raw, doc, as_of=DIA, recebido_em=RECEBIDO)
    assert f["currency"].eq("ARS").all()
    usd, d, _ = _documento()
    assert publico_ri.fatos_pdf_ri(usd, d, as_of=DIA, recebido_em=RECEBIDO)["currency"].eq("USD").all()


def test_duplicata_divergente_nao_vira_fato():
    _, doc, paginas = _documento()
    paginas[1] = paginas[1].replace("Revenues 60 50 35 30", "Revenues 60 50 35 30\nRevenues 61 50 35 30")
    raw = _pdf(paginas)
    doc["sha256"] = hashlib.sha256(raw).hexdigest()
    f = publico_ri.fatos_pdf_ri(raw, doc, as_of=DIA, recebido_em=RECEBIDO)
    assert "receita" not in set(f["item"])
    assert "lucro_liquido_controladores" in set(f["item"])


def test_descoberta_sem_publicacao_e_competencia_futura(ambiente):
    a = ambiente
    assert publico_ri.documentos_ri(a.iid, DIA) == a.docs
    assert publico_ri.documentos_ri(a.iid, date(2026, 6, 29)) == [a.docs[1]]
    assert publico_ri.documentos_ri("OUTRO_DADOS_SIMULADOS", DIA) == []


@pytest.mark.parametrize("delta,admitido", [(-1, False), (0, True), (1, True)])
def test_api_corte_utc_antes_exato_depois_do_recibo(ambiente, delta, admitido):
    a = ambiente
    out = _normal(a, RECEBIDO + timedelta(microseconds=delta))
    assert (not out.empty) is admitido
    if admitido:
        pl = out[(out["item"] == "patrimonio_controladores") & (out["period_end"] == pd.Timestamp("2026-06-30"))].iloc[0]
        assert pl["value"] == 80_000_000 and pl["currency"] == "USD"
        assert pd.Timestamp(pl["disponivel_desde"]) == pd.Timestamp(RECEBIDO)
        assert pd.isna(pl["data_publicacao"]) and pd.isna(pl["data_recebimento_documento"])


def test_date_civil_07_08_09_respeita_cruzamento_utc(ambiente):
    a = ambiente
    # 00:08 UTC de 08 ainda é 07 em São Paulo; recibo permanece um instante.
    before = _normal(a, AGORA, civil=date(2026, 10, 7))
    today = _normal(a, AGORA, civil=DIA)
    tomorrow = _normal(a, AGORA, civil=date(2026, 10, 9))
    pd.testing.assert_frame_equal(before, today)
    pd.testing.assert_frame_equal(today, tomorrow)
    civil, corte = publico_fatos._corte_observado(DIA, None)
    assert civil == DIA and corte == datetime(2026, 10, 9, 2, 59, 59, 999999, tzinfo=UTC)


@pytest.mark.parametrize("recibo", [None, datetime(2026, 10, 8), "2026-10-08T18:00:00", AGORA + timedelta(seconds=1)])
def test_recibo_ausente_naive_futuro_nao_e_publicacao(recibo):
    raw, doc, _ = _documento()
    f = publico_ri.fatos_pdf_ri(raw, doc, as_of=DIA, recebido_em=RECEBIDO)
    f["disponivel_desde"] = recibo
    assert publico_fatos.selecionar_pit(f, AGORA + timedelta(days=1)).empty
    assert f["data_publicacao_primaria"].isna().all()


def test_parser_naive_e_api_sem_corte_recusam_antes_de_acesso(tmp_path, monkeypatch):
    raw, doc, _ = _documento()
    with pytest.raises(ValueError, match="fuso"):
        publico_ri.fatos_pdf_ri(raw, doc, as_of=DIA, recebido_em=datetime(2026, 10, 8))
    monkeypatch.setattr(publico, "_arquivo", lambda *a: pytest.fail("acesso antes de validar o corte"))
    with pytest.raises(ValueError, match="corte UTC explícito"):
        publico.demonstrativos(["DADOS_SIMULADOS"], DIA, root=tmp_path,
                               selecionar_ri_observado=True)


def test_ttm_condicional_multidocumento_so_participantes_efetivos(ambiente):
    a = ambiente
    out = _normal(a, AGORA)
    ni = out[(out["item"] == "lucro_liquido_controladores") & (out["freq"] == "TTM")
             & (out["period_end"] == pd.Timestamp("2026-06-30"))].iloc[0]
    assert Decimal(str(ni["value"])) == (Decimal(10) + Decimal(7) - Decimal(5)) * Decimal(1_000_000)
    raw = ni["nota"].split("componentes_fluxo=", 1)[1]
    components, _ = json.JSONDecoder().raw_decode(raw)
    assert len(components) == 3
    assert {c["fonte"]["documento"] for c in components} == set(a.raws)
    assert all(c["fonte"]["data_publicacao"] is None for c in components)
    assert pd.Timestamp(ni["disponivel_desde"]) == pd.Timestamp(a.regs[1].limite_captura)
    assert pd.isna(ni["data_publicacao"])
    val, row = Demonstrativos(out, a.iid).valor("lucro_liquido_controladores")
    assert val == 12_000_000 and pd.isna(row["data_publicacao"])
    assert not out["item"].isin(["acoes_em_circulacao", "cfo", "capex"]).any()


def test_complemento_yahoo_ars_nao_reaparece_usd(ambiente):
    a = ambiente
    base = _normal(a, AGORA)
    row = base[(base["item"] == "receita") & (base["freq"] == "Q")].iloc[0].to_dict()
    ars = pd.DataFrame([row | {"currency": "ARS", "fonte": "YAHOO", "item": "ebit", "value": 123.0}])
    qa = []
    result = publico._complemento(base, ars, a.iid, qa)
    assert result is None or result.empty
    assert ars.iloc[0]["currency"] == "ARS" and ars.iloc[0]["value"] == 123.0
    assert base["currency"].eq("USD").all()


def test_default_api_nao_ativa_catalogo_observado(ambiente):
    a = ambiente
    out = _normal(a, AGORA, observado=False)
    assert out.empty and list(out.columns) == publico.DEMONSTRATIVOS_COLUNAS
    assert "disponivel_desde" not in out.columns
    assert out.attrs == {"as_of": DIA.isoformat(), "falhas": [], "desconhecidos": [], "qa": [], "moeda_trocada": {}}


def test_coletar_preparar_serializar_normal_sem_sdk(ambiente):
    a = ambiente
    assert a.params.sec("qualidade").get("ri_disponibilidade_metodo") is None
    dados = fontes.coletar(a.md, DIA, [a.iid], a.tickers, [], offline=True, raiz=a.root,
                           params=a.params, conhecimento_ate=AGORA)
    assert not dados.demonstrativos.empty and dados.demonstrativos["issuer_id"].eq(a.iid).all()
    pacote = preparar_emissor(a.md, dados, a.params, a.iid, DIA)
    assert pacote["max_data_publicacao"] is None and pacote["pit_ok"] is False
    assert pacote["moeda_demonstrativos"] == "USD" and pacote["fator_moeda"] == 1.0
    assert pacote["t.patrimonio_controladores"] == 80_000_000
    assert pacote["data_preco"] == BASE.isoformat() and pacote["as_of"] == date(2026, 10, 9).isoformat()
    csv = fontes.csv_canonico(dados.tabelas()["demonstrativos"])
    assert RECEBIDO.isoformat() in csv
    assert a.regs[1].limite_captura.isoformat() in csv
    assert not dados.demonstrativos["data_publicacao"].notna().any()


@pytest.mark.parametrize("observado", [False, True])
def test_universo_do_mercado_so_e_repassado_no_optin(mercado, monkeypatch, tmp_path, observado):
    calls = []

    def collect(*args, **kwargs):
        calls.append(kwargs)
        return pd.DataFrame()

    for name in ("demonstrativos", "consenso_publico", "dividendos", "eventos_corporativos", "taxas_publicas", "free_float", "composicao_etf"):
        monkeypatch.setattr(publico, name, collect)
    monkeypatch.setattr(fontes, "contas_suplementares_cvm", collect)
    monkeypatch.setattr(fontes, "capital_oficial", collect)
    fontes.coletar(mercado.md, DIA, [mercado.iid], mercado.tickers, ["DADOS_SIMULADOS_ETF"],
                   offline=True, raiz=tmp_path, params=_params(observado=observado), conhecimento_ate=AGORA)
    dem = calls[0]
    assert (dem.get("universe") is mercado.md.universe) is observado
    assert ("selecionar_ri_observado" in dem) is observado
    assert ("confirmar_magnitude_cvm" in dem) is observado
    if observado:
        assert dem["conhecimento_ate"] == AGORA
    for kw in calls[1:]:
        assert "conhecimento_ate" not in kw and "selecionar_ri_observado" not in kw
        assert "confirmar_magnitude_cvm" not in kw
    # ETFs também recebem o universo explícito quando solicitado.
    assert (calls[-1].get("universe") is mercado.md.universe) is observado


def test_config_metodo_invalido_ou_sem_politica_recusa(mercado, tmp_path):
    p = _params(temporal=False)
    with pytest.raises(ValueError, match="política temporal"):
        fontes.coletar(mercado.md, DIA, [mercado.iid], mercado.tickers, [], params=p, raiz=tmp_path)
    p.valuation["qualidade"]["demonstrativos_disponibilidade_metodo"] = "METODO DESCONHECIDO DADOS SIMULADOS"
    with pytest.raises(ValueError, match="desconhecido"):
        fontes.disponibilidade_observada(p)
    with pytest.raises(ValueError, match="instante explícito"):
        fontes.coletar(mercado.md, DIA, [mercado.iid], mercado.tickers, [], params=_params(), raiz=tmp_path)


@pytest.mark.parametrize("ypf,observado,injetado", [
    (True, True, False), (True, True, True), (False, True, False), (True, False, False),
])
def test_conexao_transporte_preserva_arquivo_url_sha_e_default(ambiente, monkeypatch,
                                                              ypf, observado, injetado):
    """Autoria ROOT: fronteira real coletor→closure→Arquivo, com bytes DADOS SIMULADOS."""
    a = ambiente
    docs = copy.deepcopy(a.docs)
    rotas = [
        "https://inversores.ypf.com/r/documents.html?p=Informacion-financiera/YPF%20CONSOLIDATED%20FS%20USD%20-%2030-06-2026.pdf",
        "https://inversores.ypf.com/r/documents.html?p=InformeAnualForm20/YPF%20-%2020-F%202025.pdf",
    ]
    if ypf:
        for doc, rota in zip(docs, rotas, strict=True):
            doc["url"] = rota
    catalogo = a.tmp / "catalogo-transporte-DADOS-SIMULADOS.json"
    catalogo.write_text(json.dumps({"schema": "cdp.ri_demonstrativos/v1", "documentos": docs}))
    monkeypatch.setattr(publico_ri, "CATALOGO_RI", catalogo)
    por_url = {doc["url"]: a.raws[doc["documento"]] for doc in docs}
    chamadas_ypf, chamadas_http = [], []

    def transporte(rota):
        chamadas_ypf.append(rota)
        return por_url[rota]

    def http(rota, headers):
        chamadas_http.append(rota)
        assert "Authorization" not in headers
        return por_url[rota]

    monkeypatch.setattr(publico, "baixar_pdf_ypf", transporte)
    monkeypatch.setattr(publico, "default_http_get", http)
    raiz = a.tmp / "coleta-nova-DADOS-SIMULADOS"
    # DADOS SIMULADOS: a captura online participa do corte civil e usa relógio fixo.
    monkeypatch.setattr(publico, "_arquivo",
                        lambda root, offline: Arquivo(root, offline=offline, agora=lambda: RECEBIDO))
    out = publico.demonstrativos([a.iid], DIA, root=raiz, universe=a.md.universe,
                                offline=False, complementar_yahoo=False,
                                http_get=http if injetado else None,
                                conhecimento_ate=AGORA if observado else None,
                                selecionar_ri_observado=observado)
    esperadas = list(por_url) if observado else []
    assert chamadas_ypf == (esperadas if ypf and observado and not injetado else [])
    assert chamadas_http == ([] if ypf and not injetado else esperadas)
    registros = Arquivo(raiz, offline=True).registros()
    assert sorted(r.url for r in registros) == sorted(esperadas)
    if observado:
        assert not out.empty and out["data_publicacao"].isna().all()
        for reg in registros:
            assert reg.sha256 == hashlib.sha256(por_url[reg.url]).hexdigest()
            assert reg.data_coleta.tzinfo is not None
            assert reg.data_coleta == RECEBIDO.replace(microsecond=0)
            assert Arquivo(raiz, offline=True).ler(reg) == por_url[reg.url]
    else:
        assert out.empty and not registros
