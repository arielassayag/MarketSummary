"""Transporte anônimo dos três PDFs públicos observados no RI da YPF.

Retorna somente bytes. ``Arquivo.obter`` registra a rota pública, SHA e recepção;
seu validador confere o PDF integral, documento/grão e hash esperado. Este módulo
não interpreta moeda, publicação financeira, disponibilidade histórica ou PIT.

API/site observados no appsettings institucional em 08/10/2026; SHA do JSON
integral observado: f8685f0c10947ac8942ac894980b99e7edb738765a3b2aa18d9f352557015f94.
As respostas loginSite e URLs SharePoint temporárias ficam apenas em memória.
"""
from __future__ import annotations

import json
from http.cookiejar import CookieJar
from urllib.parse import parse_qsl, urlsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)

SETTINGS_URL = "https://inversores.ypf.com/js/appsettings.json"
API_URL = "https://magui.ypf.com/shp/yforms-lists/graphql/"
API_SITE = "comunicaciones/inversores"
DOWNLOAD_HOST = "ypf.sharepoint.com"
DOWNLOAD_PATH = "/sites/comunicaciones/inversores/_layouts/15/download.aspx"
SLUGS = frozenset({
    "Informacion-financiera/YPF CONSOLIDATED FS USD - 30-06-2026.pdf",
    "Informacion-financiera/YPF CONSOLIDATED FS USD - 31-03-2026.pdf",
    "InformeAnualForm20/YPF - 20-F 2025.pdf",
})
_LOGIN = "mutation loginSite($site: String) { loginSite(site:$site) { expiration access_token } }"
_RESOLVE = ("query getItemByListIdAndDriveSharedLink($share: String!) { "
            "getItemByListIdAndDriveSharedLink(sharedLink: $share) { publicWebUrl } }")
_MAX_JSON = 1_048_576
_MAX_PDF = 33_554_432


class TransporteYPFIndisponivel(RuntimeError):
    """Falha classificada sem URL temporária, resposta remota ou credencial."""


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _rota_admitida(rota: str) -> bool:
    if not isinstance(rota, str) or any(ord(c) < 32 or ord(c) == 127 for c in rota):
        return False
    try:
        u = urlsplit(rota)
        params = parse_qsl(u.query, keep_blank_values=True, strict_parsing=True)
        return (u.scheme == "https" and u.netloc == "inversores.ypf.com"
                and u.path == "/r/documents.html" and not u.fragment
                and len(params) == 1 and params[0][0] == "p" and params[0][1] in SLUGS)
    except (TypeError, ValueError):
        return False


def _destino_admitido(url: str) -> bool:
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        return False
    try:
        u = urlsplit(url)
        return (u.scheme == "https" and u.netloc == DOWNLOAD_HOST
                and u.path == DOWNLOAD_PATH and not u.fragment and bool(u.query))
    except (TypeError, ValueError):
        return False


def _pedir(abrir, etapa: str, url: str, *, payload=None, token=None, pdf=False) -> bytes:
    headers = {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = token
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    limit = _MAX_PDF if pdf else _MAX_JSON
    failed = False
    body = b""
    try:
        with abrir(request, timeout=60 if pdf else 30) as response:
            if response.status != 200 or response.geturl() != url:
                failed = True
            else:
                body = response.read(limit + 1)
    except Exception:
        # Fora do bloco except, a exceção pública não conserva a causa remota.
        failed = True
    if failed or not isinstance(body, bytes) or not body or len(body) > limit:
        raise TransporteYPFIndisponivel(f"RI YPF indisponível: {etapa}.") from None
    return body


def _json(body: bytes, etapa: str) -> dict:
    failed = False
    value = None
    try:
        value = json.loads(body)
    except Exception:
        failed = True
    if failed or not isinstance(value, dict) or value.get("errors"):
        raise TransporteYPFIndisponivel(f"RI YPF indisponível: {etapa}.") from None
    return value


def baixar_pdf_ypf(rota: str, *, abrir=None) -> bytes:
    """Resolve uma rota pública admitida, sem retry ou persistência de credencial.

    ``abrir`` injeta o protocolo urllib nos testes offline; por padrão, cada chamada
    usa uma sessão de cookies própria e recusa redirecionamentos. Não envia login
    de usuário, e-mail, contato SEC ou chave de API. A indisponibilidade permanece
    falha de transporte, sem gerar fatos financeiros.
    """
    if not _rota_admitida(rota):
        raise TransporteYPFIndisponivel("RI YPF indisponível: rota não admitida.")
    if abrir is None:
        abrir = build_opener(_SemRedirecionamento(), HTTPCookieProcessor(CookieJar())).open
    settings = _json(_pedir(abrir, "configuração", SETTINGS_URL), "configuração")
    if settings.get("LIST_API_URL") != API_URL or settings.get("LIST_API_SITE") != API_SITE:
        raise TransporteYPFIndisponivel("RI YPF indisponível: configuração alterada.")
    login = _json(_pedir(abrir, "login anônimo", API_URL,
                         payload={"query": _LOGIN, "variables": {"site": API_SITE}}), "login anônimo")
    data = login.get("data")
    auth = data.get("loginSite") if isinstance(data, dict) else None
    token = auth.get("access_token") if isinstance(auth, dict) else None
    if (not isinstance(token, str) or not token or len(token) > 16_384
            or any(c in token for c in "\r\n\0")):
        raise TransporteYPFIndisponivel("RI YPF indisponível: resposta de login anônimo.")
    resolved = _json(_pedir(abrir, "resolução", API_URL,
                            payload={"query": _RESOLVE, "variables": {"share": rota}}, token=token),
                     "resolução")
    data = resolved.get("data")
    item = data.get("getItemByListIdAndDriveSharedLink") if isinstance(data, dict) else None
    destino = item.get("publicWebUrl") if isinstance(item, dict) else None
    if not isinstance(destino, str) or not _destino_admitido(destino):
        raise TransporteYPFIndisponivel("RI YPF indisponível: destino não admitido.")
    body = _pedir(abrir, "download", destino, pdf=True)
    if not body.startswith(b"%PDF-"):
        raise TransporteYPFIndisponivel("RI YPF indisponível: resposta não é PDF.")
    return body
