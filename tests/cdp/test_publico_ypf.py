"""Protocolo offline com respostas e tokens DADOS SIMULADOS, sem rede."""
from __future__ import annotations

import hashlib
import json
import traceback
from datetime import UTC, date, datetime
from urllib.parse import quote

import pytest

from cdp.data import publico_ypf as ypf
from cdp.data.publico_arquivo import Arquivo, ArquivoAdulterado

TOKEN = "DADOS_SIMULADOS_TOKEN_PRIVADO"
TEMP_TOKEN = "DADOS_SIMULADOS_TOKEN_SHAREPOINT"
PDF = b"%PDF-1.4\n%DADOS SIMULADOS: transporte, sem fatos financeiros\n%%EOF\n"
DESTINO = (f"https://{ypf.DOWNLOAD_HOST}{ypf.DOWNLOAD_PATH}"
           f"?UniqueId=DADOS_SIMULADOS&tempauth={TEMP_TOKEN}")
ROTA = "https://inversores.ypf.com/r/documents.html?p=" + quote(sorted(ypf.SLUGS)[0])


class Resposta:
    def __init__(self, body, url, status=200):
        self.body = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        self.url = url
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def geturl(self):
        return self.url

    def read(self, size):
        return self.body[:size]


class Protocolo:
    def __init__(self, *, settings=None, login=None, resolved=None, pdf=PDF, falha=None):
        self.settings = settings if settings is not None else {"LIST_API_URL": ypf.API_URL,
                                                              "LIST_API_SITE": ypf.API_SITE}
        self.login = login if login is not None else {"data": {"loginSite": {"access_token": TOKEN}}}
        self.resolved = resolved if resolved is not None else {
            "data": {"getItemByListIdAndDriveSharedLink": {"publicWebUrl": DESTINO}}}
        self.pdf = pdf
        self.calls = []
        self.falha = falha

    def abrir(self, request, timeout):
        self.calls.append((request, timeout))
        step = len(self.calls)
        if self.falha == step:
            raise RuntimeError(f"{TOKEN} {DESTINO}")
        body = [self.settings, self.login, self.resolved, self.pdf][step - 1]
        return Resposta(body, request.full_url)


def afirmar_falha_segura(call, capsys):
    with pytest.raises(ypf.TransporteYPFIndisponivel) as info:
        call()
    rendered = "".join(traceback.format_exception(info.value))
    assert TOKEN not in rendered and TEMP_TOKEN not in rendered
    assert "tempauth=" not in rendered and "sharepoint.com" not in rendered
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("slug", sorted(ypf.SLUGS))
def test_tres_documentos_protocolo_bytes_sem_token_em_get(slug):
    rota = "https://inversores.ypf.com/r/documents.html?p=" + quote(slug)
    transport = Protocolo()
    body = ypf.baixar_pdf_ypf(rota, abrir=transport.abrir)
    assert body == PDF and hashlib.sha256(body).digest() == hashlib.sha256(PDF).digest()
    calls = transport.calls
    assert [r.get_method() for r, _ in calls] == ["GET", "POST", "POST", "GET"]
    assert [r.full_url for r, _ in calls] == [ypf.SETTINGS_URL, ypf.API_URL, ypf.API_URL, DESTINO]
    assert json.loads(calls[1][0].data)["variables"] == {"site": ypf.API_SITE}
    assert json.loads(calls[2][0].data)["variables"] == {"share": rota}
    assert calls[2][0].get_header("Authorization") == TOKEN
    assert all(r.get_header("Authorization") is None for r, _ in [calls[0], calls[1], calls[3]])
    assert [timeout for _, timeout in calls] == [30, 30, 30, 60]


@pytest.mark.parametrize("rota", [
    None, 1, "", ROTA.replace("https:", "http:"),
    ROTA.replace("inversores.ypf.com", "inversores.ypf.com.evil.test"),
    ROTA.replace("inversores.ypf.com", "u:p@inversores.ypf.com"),
    ROTA.replace("inversores.ypf.com", "inversores.ypf.com:443"),
    ROTA.replace("documents.html", "outro.html"), ROTA + "#fragmento",
    ROTA + "&p=outro.pdf", ROTA + f"&token={TOKEN}", ROTA.replace("?p=", "?q="),
    "https://inversores.ypf.com/r/documents.html?p=../fora.pdf", ROTA + "\n",
])
def test_rota_recusada_antes_de_rede(rota, capsys):
    transport = Protocolo()
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(rota, abrir=transport.abrir), capsys)
    assert transport.calls == []


@pytest.mark.parametrize("settings", [
    {"LIST_API_URL": "https://evil.test/graphql", "LIST_API_SITE": ypf.API_SITE},
    {"LIST_API_URL": ypf.API_URL, "LIST_API_SITE": "outro/site"},
    {"LIST_API_URL": ypf.API_URL + f"?token={TOKEN}", "LIST_API_SITE": ypf.API_SITE},
    {"LIST_API_URL": ypf.API_URL.replace("https:", "http:"), "LIST_API_SITE": ypf.API_SITE},
    {}, b"nao-json", [], {"errors": [{"message": TOKEN}]},
])
def test_configuracao_nao_pode_redirecionar_login(settings, capsys):
    transport = Protocolo(settings=settings)
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir), capsys)
    assert len(transport.calls) == 1


@pytest.mark.parametrize("login", [
    {}, {"data": None}, {"data": {"loginSite": None}},
    {"data": {"loginSite": {"access_token": ""}}},
    {"data": {"loginSite": {"access_token": [TOKEN]}}},
    {"data": {"loginSite": {"access_token": TOKEN + "\r\nHeader: valor"}}},
    {"errors": [{"message": TOKEN}], "data": {"loginSite": {"access_token": TOKEN}}},
    b"json-invalido " + TOKEN.encode(),
])
def test_login_sem_credencial_utilizavel(login, capsys):
    transport = Protocolo(login=login)
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir), capsys)
    assert len(transport.calls) == 2


@pytest.mark.parametrize("destino", [
    "http://ypf.sharepoint.com" + ypf.DOWNLOAD_PATH + "?a=1",
    DESTINO.replace("ypf.sharepoint.com", "ypf.sharepoint.com.evil.test"),
    DESTINO.replace("ypf.sharepoint.com", "u:p@ypf.sharepoint.com"),
    DESTINO.replace("ypf.sharepoint.com", "ypf.sharepoint.com:443"),
    DESTINO.replace("download.aspx", "outro.aspx"), DESTINO + "#fora", DESTINO + "\n",
    "https://ypf.sharepoint.com" + ypf.DOWNLOAD_PATH,
    None, [DESTINO],
])
def test_destino_fechado_antes_de_download(destino, capsys):
    transport = Protocolo(resolved={"data": {"getItemByListIdAndDriveSharedLink": {
        "publicWebUrl": destino}}})
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir), capsys)
    assert len(transport.calls) == 3


@pytest.mark.parametrize("resolved", [
    {}, {"data": None}, {"data": {"getItemByListIdAndDriveSharedLink": None}},
    {"errors": [{"message": TOKEN}], "data": {"getItemByListIdAndDriveSharedLink": {
        "publicWebUrl": DESTINO}}}, b"json-invalido " + TOKEN.encode(),
])
def test_resolucao_graphql_incompleta_ou_com_erros(resolved, capsys):
    transport = Protocolo(resolved=resolved)
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir), capsys)
    assert len(transport.calls) == 3


@pytest.mark.parametrize("falha", [1, 2, 3, 4])
def test_excecao_remota_sem_mensagem_contexto_ou_retry(falha, capsys):
    transport = Protocolo(falha=falha)
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir), capsys)
    assert len(transport.calls) == falha


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 429, 500])
def test_http_nao_200_sem_retry(status, capsys):
    transport = Protocolo()

    def abrir(request, timeout):
        return Resposta(TOKEN.encode(), request.full_url, status=status)

    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=abrir), capsys)
    assert transport.calls == []


def test_handler_padrao_recusa_redirect_e_final_divergente(capsys):
    assert ypf._SemRedirecionamento().redirect_request(None, None, 302, "", {}, DESTINO) is None
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=lambda req, **kw:
                        Resposta({}, "https://evil.test/?token=" + TOKEN)), capsys)


@pytest.mark.parametrize("pdf", [b"<html>401</html>", b"", b"%PDX-invalido"])
def test_html_e_resposta_vazia_nao_viram_pdf(pdf, capsys):
    transport = Protocolo(pdf=pdf)
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir), capsys)


def test_limite_de_bytes_falha_segura(monkeypatch, capsys):
    monkeypatch.setattr(ypf, "_MAX_PDF", 8)
    transport = Protocolo()
    afirmar_falha_segura(lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir), capsys)


def test_arquivo_normal_registra_so_rota_publica_sha_e_recepcao(tmp_path):
    instante = datetime(2026, 10, 8, 20, 0, 1, 123456, tzinfo=UTC)
    transport = Protocolo()
    arq = Arquivo(tmp_path, agora=lambda: instante, conhecimento_ate=instante)
    expected = hashlib.sha256(PDF).hexdigest()

    def validar(body):
        if hashlib.sha256(body).hexdigest() != expected:
            raise ValueError("SHA esperado do documento não confere; DADOS SIMULADOS")

    got = arq.obter("RI/demonstrativos/AR_YPF/teste.pdf", "RI", ROTA,
                    lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir),
                    ate=date(2026, 10, 8), validar=validar)
    assert got is not None
    reg, body = got
    assert body == PDF and reg.sha256 == expected and reg.url == ROTA
    assert reg.data_coleta == instante and reg.limite_captura == instante
    text = arq.caminho_indice.read_text()
    assert TOKEN not in text and TEMP_TOKEN not in text and "sharepoint.com" not in text
    assert "data_publicacao" not in text
    (arq.base / reg.caminho).write_bytes(PDF + b"alterado")
    with pytest.raises(ArquivoAdulterado):
        arq.ler(reg)


def test_arquivo_nao_grava_pdf_de_hash_diverso_ou_erro(tmp_path):
    instante = datetime(2026, 10, 8, 20, 0, 1, tzinfo=UTC)
    arq = Arquivo(tmp_path, agora=lambda: instante)

    def validar(_):
        raise ValueError("SHA esperado diverso; DADOS SIMULADOS")

    transport = Protocolo(pdf=PDF + b"alterado")
    got = arq.obter("RI/demonstrativos/AR_YPF/teste.pdf", "RI", ROTA,
                    lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir),
                    ate=date(2026, 10, 8), validar=validar)
    assert got is None and arq.registros() == []
    assert not arq.caminho_indice.exists()
    transport = Protocolo(falha=4)
    got = arq.obter("RI/demonstrativos/AR_YPF/teste.pdf", "RI", ROTA,
                    lambda: ypf.baixar_pdf_ypf(ROTA, abrir=transport.abrir), ate=date(2026, 10, 8))
    assert got is None and arq.registros() == []
    assert all(TOKEN not in text and TEMP_TOKEN not in text for text in arq.falhas)
