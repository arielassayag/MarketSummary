"""DADOS SIMULADOS: revisão não autora do transporte e do hook normal ROOT.

Nenhuma chamada HTTP real; os bytes de teste não são um documento financeiro
primário. Os testes importam o pacote normal e não alteram origem de módulos.
"""
from __future__ import annotations

import hashlib
import io
import json
import traceback
from datetime import UTC, date, datetime, timedelta
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor

import pandas as pd
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from cdp.data import publico, publico_fatos, publico_ri
from cdp.data import publico_ypf as ypf
from cdp.data.publico_arquivo import Arquivo
from cdp.universe import universe_from_frame

TOKEN = "DADOS_SIMULADOS_AUTH_MEMORIA"
DESTINO = f"https://{ypf.DOWNLOAD_HOST}{ypf.DOWNLOAD_PATH}?UniqueId=SIMULADO&tempauth=SIMULADO_MEMORIA"
ROTA = "https://inversores.ypf.com/r/documents.html?p=" + quote(sorted(ypf.SLUGS)[0])
CORTE = datetime(2026, 10, 8, 19, 1, 2, 123456, tzinfo=UTC)
PDF = b"%PDF-1.4\n%DADOS SIMULADOS: apenas protocolo\n%%EOF\n"


class Resposta:
    def __init__(self, body, url, reads):
        self.body = body
        self.url = url
        self.status = 200
        self.reads = reads

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, size):
        self.reads.append(size)
        return self.body[:size]


class ProtocoloIndependente:
    def __init__(self, *, pdf=PDF, token=TOKEN, etapa_divergente=None, etapa_tamanho=None,
                 tamanho=None, falha=None):
        self.pdf, self.token = pdf, token
        self.etapa_divergente, self.etapa_tamanho = etapa_divergente, etapa_tamanho
        self.tamanho, self.falha = tamanho, falha
        self.calls, self.reads = [], []

    def abrir(self, request, timeout):
        self.calls.append(request)
        step = len(self.calls)
        if step == self.falha:
            try:
                raise ValueError(TOKEN + " " + DESTINO)
            except ValueError as inner:
                raise RuntimeError("DADOS SIMULADOS " + TOKEN) from inner
        respostas = [{"LIST_API_URL": ypf.API_URL, "LIST_API_SITE": ypf.API_SITE},
                     {"data": {"loginSite": {"access_token": self.token}}},
                     {"data": {"getItemByListIdAndDriveSharedLink": {"publicWebUrl": DESTINO}}}]
        body = self.pdf if step == 4 else json.dumps(respostas[step - 1]).encode()
        if step == self.etapa_tamanho:
            assert self.tamanho >= len(body)
            body += b" " * (self.tamanho - len(body))
        url = request.full_url + "&DADOS_SIMULADOS=divergente" if step == self.etapa_divergente else request.full_url
        return Resposta(body, url, self.reads)


def _falha(call):
    with pytest.raises(ypf.TransporteYPFIndisponivel) as info:
        call()
    rendered = "".join(traceback.format_exception(info.value))
    assert TOKEN not in rendered and "tempauth=" not in rendered and "SIMULADO_MEMORIA" not in rendered
    assert info.value.__cause__ is None and info.value.__context__ is None
    return info.value


@pytest.mark.parametrize("rota", [
    ROTA.replace("inversores.ypf.com", "inversores.ypf.com."),
    ROTA.replace("inversores.ypf.com", "inversores.ypf.com%40evil.invalid"),
    ROTA.replace("inversores.ypf.com", "evil.invalid@inversores.ypf.com"),
    ROTA.replace("inversores.ypf.com", "inversores.ypf.com\\@evil.invalid"),
    ROTA.replace("/r/documents.html", "/r/../r/documents.html"),
    ROTA.replace("/r/documents.html", "/r/%64ocuments.html"),
    ROTA + "&%70=outro", ROTA.replace("?p=", "?p=%00"),
    ROTA.replace("%20", "%2520"),
])
def test_ambiguidades_de_host_path_e_query_nao_alargam_rota(rota):
    protocol = ProtocoloIndependente()
    _falha(lambda: ypf.baixar_pdf_ypf(rota, abrir=protocol.abrir))
    assert not protocol.calls


@pytest.mark.parametrize("etapa", [1, 2, 3, 4])
def test_final_divergente_recusa_em_cada_etapa_mesmo_host_admitido(etapa):
    protocol = ProtocoloIndependente(etapa_divergente=etapa)
    _falha(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir))
    assert len(protocol.calls) == etapa and len(protocol.reads) == etapa - 1


@pytest.mark.parametrize("etapa", [1, 2, 3, 4])
def test_erro_remoto_encadeado_nao_conserva_causa_contexto_ou_retry(etapa, capsys):
    protocol = ProtocoloIndependente(falha=etapa)
    _falha(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir))
    assert len(protocol.calls) == etapa
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("etapa", [1, 2, 3])
@pytest.mark.parametrize("extra,aceito", [(0, True), (1, False)])
def test_json_limite_exato_e_um_byte_alem_com_leitura_limitada(monkeypatch, etapa, extra, aceito):
    monkeypatch.setattr(ypf, "_MAX_JSON", 512)
    protocol = ProtocoloIndependente(etapa_tamanho=etapa, tamanho=512 + extra)
    if aceito:
        assert ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir) == PDF
    else:
        _falha(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir))
        assert len(protocol.calls) == etapa
    assert protocol.reads[etapa - 1] == 513


@pytest.mark.parametrize("extra,aceito", [(0, True), (1, False)])
def test_pdf_limite_exato_e_um_byte_alem_nao_exige_arquivo_gigante(monkeypatch, extra, aceito):
    monkeypatch.setattr(ypf, "_MAX_PDF", 128)
    protocol = ProtocoloIndependente(pdf=PDF + b" " * (128 + extra - len(PDF)))
    if aceito:
        assert len(ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir)) == 128
    else:
        _falha(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir))
    assert protocol.reads[-1] == 129


@pytest.mark.parametrize("tamanho,aceito", [(16384, True), (16385, False)])
def test_limite_token_nao_envia_para_get_ou_outro_host(tamanho, aceito):
    token = "S" * tamanho  # DADOS SIMULADOS: nenhum token de login real.
    protocol = ProtocoloIndependente(token=token)
    if aceito:
        assert ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir) == PDF
        assert protocol.calls[2].get_header("Authorization") == token
        assert protocol.calls[2].full_url == ypf.API_URL
        assert all(protocol.calls[i].get_header("Authorization") is None for i in (0, 1, 3))
    else:
        _falha(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir))
        assert len(protocol.calls) == 2


def test_opener_padrao_cria_cookiejar_distinto_e_handler_sem_redirect(monkeypatch):
    jars, handlers = [], []

    def factory(*options):
        handlers.extend(options)
        cookie = next(h for h in options if isinstance(h, HTTPCookieProcessor))
        jars.append(cookie.cookiejar)
        return type("Opener", (), {"open": ProtocoloIndependente().abrir})()

    monkeypatch.setattr(ypf, "build_opener", factory)
    assert ypf.baixar_pdf_ypf(ROTA) == PDF
    assert ypf.baixar_pdf_ypf(ROTA) == PDF
    assert jars[0] is not jars[1] and len(jars[0]) == len(jars[1]) == 0
    assert sum(isinstance(h, ypf._SemRedirecionamento) for h in handlers) == 2


def _pdf_financeiro(*, observado):
    # PDF mínimo válido, distinto dos reais: o fluxo declara a data-base oficial do BP.
    identidade = "DADOS SIMULADOS"
    titulo = "CONSOLIDATED FINANCIAL POSITION" if observado else "Estados consolidados de situacion financiera"
    titulo_dre = "CONSOLIDATED COMPREHENSIVE INCOME" if observado else "Estados consolidados de resultados"
    unidade = "Amounts expressed in millions of United States dollars" if observado else "Cifras expresadas en miles de pesos mexicanos"
    texto = f"""{identidade}; 1 de octubre de 2026
{titulo}
AS OF JUNE 30, 2026 AND DECEMBER 31, 2025
{unidade}
2026 2025
Parent equity 10 9
LIABILITIES
{titulo_dre}
FOR THE THREE-MONTH PERIODS ENDED JUNE 30, 2026 AND 2025
Quarter 2026 2025
Revenues 30 25
FIM DADOS SIMULADOS"""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
        DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(("BT /F1 9 Tf 30 760 Td 12 TL\n" + "\n".join(f"({line}) Tj T*" for line in texto.splitlines()) + "\nET").encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    buf = io.BytesIO()
    writer.write(buf)
    raw = buf.getvalue()
    doc = {"issuer_id": "DADOS_SIMULADOS", "sha256": hashlib.sha256(raw).hexdigest(),
           "documento": "DADOS_SIMULADOS.pdf", "url": ROTA,
           "entidade_documento": identidade, "data_publicacao": None if observado else "2026-10-01",
           "tabelas": [{"pagina": 1, "demonstrativo": "BP", "ancoras": [titulo, unidade],
                        "cabecalho_colunas": "2026 2025", "fim_tabela": "LIABILITIES",
                        "colunas": [{"rotulo": "2026", "fim": "2026-06-30"},
                                    {"rotulo": "2025", "fim": "2025-12-31"}],
                        "moeda": "USD" if observado else "MXN", "escala": 1_000_000 if observado else 1000,
                        "itens": {"patrimonio_controladores": {"rotulos": ["Parent equity"]}}},
                       {"pagina": 1, "demonstrativo": "DRE", "ancoras": [titulo_dre, unidade],
                        "cabecalho_colunas": "Quarter 2026 2025", "fim_tabela": "FIM DADOS SIMULADOS",
                        "colunas": [{"rotulo": "2026", "inicio": "2026-04-01", "fim": "2026-06-30"},
                                    {"rotulo": "2025", "inicio": "2025-04-01", "fim": "2025-06-30"}],
                        "moeda": "USD" if observado else "MXN", "escala": 1_000_000 if observado else 1000,
                        "itens": {"receita": {"rotulos": ["Revenues"]}}}]}
    if observado:
        doc["disponibilidade_tipo"] = "recepcao_observada"
    else:
        doc["publicacao_no_documento"] = {"pagina": 1, "texto": "1 de octubre de 2026"}
    return raw, doc


@pytest.mark.parametrize("modo", ["observado", "http_injetado", "outro_host", "default", "legacy"])
def test_hook_root_condicoes_normais_arquivo_parser_sem_publicacao_inventada(tmp_path, monkeypatch, modo):
    observado = modo != "legacy"
    raw, doc = _pdf_financeiro(observado=observado)
    if modo == "outro_host":
        doc["url"] = "https://example.invalid/DADOS_SIMULADOS.pdf"
    catalogo = tmp_path / "catalogo.json"
    catalogo.write_text(json.dumps({"schema": "cdp.ri_demonstrativos/v1", "documentos": [doc]}))
    monkeypatch.setattr(publico_ri, "CATALOGO_RI", catalogo)
    monkeypatch.setattr(publico_fatos, "_agora_observado", lambda: CORTE + timedelta(days=1))
    uni = universe_from_frame(pd.DataFrame([{
        "issuer_id": "DADOS_SIMULADOS", "issuer_name": "DADOS SIMULADOS", "country": "AR",
        "gics_sector": "Energy", "line_type": "LOCAL", "yahoo_ticker": "SIMULADO.BA",
        "exchange": "AR", "currency": "ARS", "adr_ratio": "", "primary_line": True,
        "notes": "DADOS SIMULADOS"}]))
    mestre = pd.DataFrame([{"issuer_id": "DADOS_SIMULADOS", "cnpj": None, "cik": None}]).set_index("issuer_id")
    monkeypatch.setattr(publico, "mestre_publico", lambda *a, **kw: mestre)
    monkeypatch.setattr(publico, "_parte_yahoo", lambda *a, **kw: None)
    root = tmp_path / "arquivo_DADOS_SIMULADOS"
    monkeypatch.setattr(publico, "_arquivo", lambda root, offline: Arquivo(root, offline=offline,
                        agora=lambda: CORTE, conhecimento_ate=CORTE))
    protocol, calls = ProtocoloIndependente(pdf=raw), []

    def baixar(route):
        calls.append(("ypf", route))
        return ypf.baixar_pdf_ypf(route, abrir=protocol.abrir)

    def http(url, headers):
        calls.append(("normal", url))
        return raw

    monkeypatch.setattr(publico, "baixar_pdf_ypf", baixar)
    monkeypatch.setattr(publico, "default_http_get", http)
    flag = modo != "default"
    out = publico.demonstrativos(["DADOS_SIMULADOS"], CORTE.date(), root=root, universe=uni,
                                  complementar_yahoo=False, selecionar_ri_observado=flag,
                                  conhecimento_ate=CORTE if flag else None,
                                  http_get=http if modo == "http_injetado" else None)
    if modo == "default":
        assert out.empty and not calls and not (root / "publico/indice.jsonl").exists()
        return
    assert calls == [("ypf" if modo == "observado" else "normal", doc["url"])]
    assert len(protocol.calls) == (4 if modo == "observado" else 0)
    assert not out.empty, out.attrs
    assert out["sha256"].eq(doc["sha256"]).all()
    arquivo = Arquivo(root, offline=True, conhecimento_ate=CORTE)
    reg = arquivo.registros()[0]
    assert reg.url == doc["url"] and reg.limite_captura == CORTE
    assert arquivo.ler(reg) == raw
    index = arquivo.caminho_indice.read_text()
    assert TOKEN not in index and "tempauth=" not in index and "sharepoint.com" not in index
    assert "data_publicacao" not in index
    if observado:
        assert out["data_publicacao"].isna().all() and out["data_recebimento_documento"].isna().all()
        assert out["currency"].eq("USD").all() and out["disponivel_desde"].eq(pd.Timestamp(CORTE)).all()
    else:
        assert out["data_publicacao"].eq(date(2026, 10, 1)).all() and out["currency"].eq("MXN").all()


def test_arquivo_captura_posterior_fica_fora_ate_corte_exato(tmp_path):
    protocol = ProtocoloIndependente()
    chave = "RI/demonstrativos/DADOS_SIMULADOS/teste.pdf"
    antes = CORTE - timedelta(microseconds=1)
    arq = Arquivo(tmp_path, agora=lambda: CORTE, conhecimento_ate=antes)
    assert arq.obter(chave, "RI", ROTA, lambda: ypf.baixar_pdf_ypf(ROTA, abrir=protocol.abrir),
                     ate=CORTE.date()) is None
    assert len(arq.registros()) == 1
    for delta, known in [(-1, False), (0, True), (1, True)]:
        offline = Arquivo(tmp_path, offline=True, conhecimento_ate=CORTE + timedelta(microseconds=delta))
        got = offline.obter(chave, "RI", ROTA, lambda: pytest.fail("rede numa releitura offline"), ate=CORTE.date())
        assert (got is not None) is known
        if got:
            assert got[1] == PDF and got[0].limite_captura == CORTE
    assert "data_publicacao" not in arq.caminho_indice.read_text()
