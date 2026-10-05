"""Security master: identificadores oficiais por emissor (CNPJ, CIK), classes de ações e linhas.

Fontes oficiais (ver docs/research/06_fontes_dados_ferramentas.md, §7):

- **CVM FCA** (``dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip``):
  mapa CNPJ ↔ código de negociação na B3 (``Codigo_Negociacao``), espécie do valor mobiliário
  (ON/PN/Units/BDR), composição das units (``Composicao_BDR_Unit``) e datas de negociação.
- **SEC** ``company_tickers_exchange.json``: ticker → CIK → bolsa. O host ``www.sec.gov`` exige
  ``User-Agent`` com contato (``Nome contato@dominio``); sem isso devolve 403. Nesse caso há
  *fallback* pelo índice de busca de entidades do EDGAR (``efts.sec.gov``), consultado só para
  os tickers do universo.

O módulo também concentra a infraestrutura HTTP compartilhada com
:mod:`.fundamentals_pit`: ``http_get`` injetável (testes 100% offline), *retry* com *backoff*
apenas em 429/5xx/timeout, ``User-Agent`` descritivo e limitador de taxa (SEC ≤ 8 req/s).

Nada aqui altera arquivos de entrada; ausências permanecem ``NaN`` (nunca viram zero).
"""

from __future__ import annotations

import io
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from ..universe import Universe

# ==========================================================
# Infraestrutura HTTP compartilhada
# ==========================================================

HttpGet = Callable[[str, Mapping[str, str]], bytes]
"""Assinatura do *getter* injetável: ``(url, headers) -> bytes``; erro HTTP ⇒ :class:`HttpError`."""

CVM_DOC_BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index?keysTyped={query}"

SEC_USER_AGENT_ENV = "SEC_USER_AGENT"
DEFAULT_USER_AGENT = (
    "CDP-Cabra-da-Peste/0.1 (pesquisa de fundamentos point-in-time; fundo LatAm L/S; "
    "defina SEC_USER_AGENT='Nome contato@dominio')"
)
SEC_MAX_REQUESTS_PER_SECOND = 8.0
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
RETRY_BACKOFF_S = (1.0, 2.0, 4.0, 8.0)


class HttpError(RuntimeError):
    """Falha HTTP com status explícito (``404`` nunca é repetido: vira dado ausente)."""

    def __init__(self, status: int, url: str, message: str = "") -> None:
        self.status = int(status)
        self.url = url
        super().__init__(f"HTTP {status} em {url}" + (f": {message}" if message else ""))


def sec_user_agent() -> str:
    """``User-Agent`` para a SEC: variável de ambiente ``SEC_USER_AGENT`` ou o padrão descritivo.

    A SEC pede ``Nome contato@dominio``. O padrão não inclui e-mail de ninguém (nenhum dado
    pessoal é enviado sem configuração explícita); ``data.sec.gov`` aceita o padrão, mas
    ``www.sec.gov`` pode recusar (403) — nesse caso use :func:`search_sec_ciks`.
    """
    ua = os.environ.get(SEC_USER_AGENT_ENV, "").strip()
    return ua or DEFAULT_USER_AGENT


class RateLimiter:
    """Limitador de taxa simples (intervalo mínimo entre chamadas), seguro para threads.

    ``clock``/``sleep`` são injetáveis para testes determinísticos.
    """

    def __init__(self, max_per_second: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if max_per_second <= 0:
            raise ValueError("max_per_second precisa ser positivo.")
        self.min_interval = 1.0 / float(max_per_second)
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last is not None:
                delay = self._last + self.min_interval - now
                if delay > 0:
                    self._sleep(delay)
                    now = now + delay
            self._last = now


SEC_RATE_LIMITER = RateLimiter(SEC_MAX_REQUESTS_PER_SECOND)
"""Limitador global para hosts da SEC (margem sob o limite oficial de 10 req/s)."""


def default_http_get(url: str, headers: Mapping[str, str], timeout: float = 120.0,
                     sleep: Callable[[float], None] = time.sleep) -> bytes:
    """GET com ``urllib`` (respeita ``HTTPS_PROXY``/``SSL_CERT_FILE``) e *retry* exponencial.

    Repete somente em 429, 5xx e erros de rede/timeout (1, 2, 4, 8 s). 404 e demais 4xx
    falham imediatamente com :class:`HttpError`.
    """
    hdrs = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Encoding": "identity", **dict(headers)}
    last_exc: Exception | None = None
    for attempt in range(len(RETRY_BACKOFF_S) + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL fixa)
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_STATUS:
                raise HttpError(exc.code, url, str(exc.reason)) from exc
            last_exc = HttpError(exc.code, url, str(exc.reason))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_exc = exc
        if attempt < len(RETRY_BACKOFF_S):
            sleep(RETRY_BACKOFF_S[attempt])
    if isinstance(last_exc, HttpError):
        raise last_exc
    raise HttpError(0, url, f"falha de rede após {len(RETRY_BACKOFF_S) + 1} tentativas: {last_exc}")


def _sec_get(url: str, http_get: HttpGet | None, user_agent: str | None,
             limiter: RateLimiter | None) -> bytes:
    (limiter or SEC_RATE_LIMITER).wait()
    getter = http_get or default_http_get
    return getter(url, {"User-Agent": user_agent or sec_user_agent(), "Accept": "application/json"})


def normalize_text(text: object) -> str:
    """Minúsculas, sem acentos e com espaços simples (comparação robusta de descrições CVM)."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def read_cvm_csv(data: bytes | io.BytesIO, **kwargs) -> pd.DataFrame:
    """Lê um CSV da CVM (``;``, latin-1) mantendo tudo como texto (conversão explícita depois)."""
    buf = io.BytesIO(data) if isinstance(data, bytes) else data
    return pd.read_csv(buf, sep=";", encoding="latin-1", dtype=str, keep_default_na=False,
                       na_values=[""], **kwargs)


# ==========================================================
# CVM FCA (mapa CNPJ ↔ ticker B3)
# ==========================================================

FCA_COLUMNS = [
    "CNPJ_Companhia", "Data_Referencia", "Versao", "Nome_Empresarial", "Valor_Mobiliario",
    "Sigla_Classe_Acao_Preferencial", "Codigo_Negociacao", "Composicao_BDR_Unit", "Mercado",
    "Data_Inicio_Negociacao", "Data_Fim_Negociacao", "Segmento",
]


def fca_url(year: int) -> str:
    return f"{CVM_DOC_BASE_URL}/FCA/DADOS/fca_cia_aberta_{int(year)}.zip"


def parse_fca_zip(data: bytes) -> pd.DataFrame:
    """Extrai ``valor_mobiliario`` do ZIP do FCA (+ ``Codigo_CVM``/setor do arquivo ``geral``)."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        vm_name = next((n for n in names if "valor_mobiliario" in n), None)
        if vm_name is None:
            raise ValueError("ZIP do FCA sem o arquivo valor_mobiliario.")
        vm = read_cvm_csv(zf.read(vm_name))
        geral_name = next((n for n in names if "_geral_" in n), None)
        geral = read_cvm_csv(zf.read(geral_name)) if geral_name else None
    for col in FCA_COLUMNS:
        if col not in vm.columns:
            vm[col] = pd.NA
    if geral is not None and {"CNPJ_Companhia", "Codigo_CVM"} <= set(geral.columns):
        g = geral.sort_values(["CNPJ_Companhia", "Versao"]).drop_duplicates("CNPJ_Companhia",
                                                                             keep="last")
        keep = [c for c in ("CNPJ_Companhia", "Codigo_CVM", "Setor_Atividade") if c in g.columns]
        vm = vm.merge(g[keep], on="CNPJ_Companhia", how="left")
    return vm


def fetch_cvm_fca(year: int, http_get: HttpGet | None = None,
                  cache_dir: str | Path | None = Path("data/cache/cvm")) -> pd.DataFrame:
    """Baixa (com cache em disco) e lê o FCA da CVM do ano ``year`` (tabela valor_mobiliario).

    O ZIP bruto é guardado sem alteração em ``cache_dir`` (gitignored); com cache presente
    não há acesso à rede.
    """
    fname = f"fca_cia_aberta_{int(year)}.zip"
    path = Path(cache_dir) / fname if cache_dir is not None else None
    if path is not None and path.exists():
        return parse_fca_zip(path.read_bytes())
    data = (http_get or default_http_get)(fca_url(year), {"User-Agent": DEFAULT_USER_AGENT})
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return parse_fca_zip(data)


# ==========================================================
# SEC: ticker → CIK
# ==========================================================

SEC_TICKER_COLUMNS = ["cik", "name", "ticker", "exchange"]


def format_cik(cik: object) -> str | None:
    """CIK com 10 dígitos (``0001119639``); ``None`` se inválido/ausente."""
    if cik is None or (isinstance(cik, float) and np.isnan(cik)) or cik is pd.NA:
        return None
    digits = re.sub(r"\D", "", str(cik).split(".")[0])
    return digits.zfill(10) if digits else None


def parse_sec_company_tickers(payload: bytes | str | Mapping) -> pd.DataFrame:
    """Converte ``company_tickers_exchange.json`` (``fields`` + ``data``) em DataFrame."""
    obj = json.loads(payload) if isinstance(payload, (bytes, str)) else payload
    fields = list(obj.get("fields", []))
    rows = obj.get("data", [])
    df = pd.DataFrame(rows, columns=fields) if rows else pd.DataFrame(columns=SEC_TICKER_COLUMNS)
    missing = [c for c in SEC_TICKER_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"JSON de tickers da SEC sem campos: {missing}")
    out = df[SEC_TICKER_COLUMNS].copy()
    out["cik"] = out["cik"].map(format_cik)
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    return out.dropna(subset=["cik"]).reset_index(drop=True)


def search_sec_ciks(tickers: Iterable[str], http_get: HttpGet | None = None,
                    user_agent: str | None = None,
                    limiter: RateLimiter | None = None) -> pd.DataFrame:
    """*Fallback*: resolve tickers → CIK pelo índice de entidades do EDGAR (``efts.sec.gov``).

    Só aceita correspondência EXATA do ticker no campo ``tickers`` da entidade (sem palpites).
    Tickers sem correspondência ficam fora do resultado (dado ausente, não inventado).
    """
    out = []
    for raw in sorted({str(t).upper().strip() for t in tickers if str(t).strip()}):
        url = SEC_SEARCH_URL.format(query=urllib.parse.quote(raw))
        try:
            payload = json.loads(_sec_get(url, http_get, user_agent, limiter))
        except HttpError:
            continue
        for hit in payload.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            listed = [t.strip().upper() for t in str(src.get("tickers", "")).split(",")]
            if raw in listed:
                name = re.sub(r"\s*\([^)]*\)\s*$", "", str(src.get("entity", ""))).strip()
                out.append({"cik": format_cik(hit.get("_id")), "name": name, "ticker": raw,
                            "exchange": pd.NA})
                break
    if not out:
        return pd.DataFrame(columns=SEC_TICKER_COLUMNS)
    return pd.DataFrame(out, columns=SEC_TICKER_COLUMNS)


def fetch_sec_company_tickers(http_get: HttpGet | None = None, user_agent: str | None = None,
                              limiter: RateLimiter | None = None,
                              fallback_tickers: Iterable[str] | None = None,
                              cache_dir: str | Path | None = Path("data/cache/sec"),
                              max_age_days: int = 7) -> pd.DataFrame:
    """Mapa oficial ticker → CIK → bolsa da SEC (com cache JSON e limite ≤ 8 req/s).

    Se ``www.sec.gov`` recusar (403, ``User-Agent`` sem contato) e ``fallback_tickers`` for
    informado, resolve só esses tickers via :func:`search_sec_ciks`.
    """
    path = Path(cache_dir) / "company_tickers_exchange.json" if cache_dir is not None else None
    if path is not None and path.exists():
        age_days = (time.time() - path.stat().st_mtime) / 86400.0
        if age_days <= max_age_days:
            return parse_sec_company_tickers(path.read_bytes())
    try:
        data = _sec_get(SEC_TICKERS_URL, http_get, user_agent, limiter)
    except HttpError:
        if path is not None and path.exists():
            return parse_sec_company_tickers(path.read_bytes())
        if fallback_tickers is None:
            raise
        return search_sec_ciks(fallback_tickers, http_get=http_get, user_agent=user_agent,
                               limiter=limiter)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return parse_sec_company_tickers(data)


# ==========================================================
# Classes de ações, units e linhas
# ==========================================================

_UNIT_PART = re.compile(
    r"(\d+)\s*(?:a[cç](?:[aã]o|[oõ]es)\s*)?(?:ordin[aá]rias?|preferenciais?|"
    r"ON|PN[A-Z]?|[A-Z]{4}\d{1,2})\b",
    re.IGNORECASE,
)


def parse_unit_composition(text: object) -> float:
    """Número de ações por unit a partir do texto livre do FCA (``Composicao_BDR_Unit``).

    Exemplos reais: ``"1 ON / 2 PN"`` → 3; ``"1 KLBN3 + 4 KLBN4"`` → 5; ``"1 ON + 1 PN"`` → 2.
    Texto ausente ou ilegível ⇒ ``NaN`` (nunca um palpite).
    """
    s = "" if text is None or (isinstance(text, float) and np.isnan(text)) else str(text)
    parts = _UNIT_PART.findall(s)
    if not parts:
        return float("nan")
    total = sum(int(p) for p in parts)
    return float(total) if total > 0 else float("nan")


_SUFFIX_CLASS = {"3": "ON", "4": "PN", "5": "PNA", "6": "PNB", "7": "PNC", "8": "PND",
                 "11": "UNIT", "31": "BDR", "32": "BDR", "33": "BDR", "34": "BDR", "35": "BDR"}


def b3_code(yahoo_ticker: str) -> str | None:
    """Código de negociação B3 (``PETR4``) a partir do ticker Yahoo (``PETR4.SA``)."""
    t = str(yahoo_ticker).upper().strip()
    return t[:-3] if t.endswith(".SA") else None


def b3_class_from_code(code: str) -> str | None:
    m = re.match(r"^[A-Z0-9]{4}(\d{1,2})$", str(code).upper())
    return _SUFFIX_CLASS.get(m.group(1)) if m else None


def _fca_class(row: pd.Series) -> str | None:
    vm = normalize_text(row.get("Valor_Mobiliario"))
    if vm.startswith("acoes ordinarias"):
        return "ON"
    if vm.startswith("acoes preferenciais"):
        sig = str(row.get("Sigla_Classe_Acao_Preferencial") or "").upper().strip()
        return sig if sig.startswith("PN") else "PN"
    if vm.startswith("units"):
        return "UNIT"
    if vm.startswith("bdr"):
        return "BDR"
    return None


_VALID_B3_CODE = re.compile(r"^[A-Z][A-Z0-9]{3}\d{1,2}$")  # raiz começa por letra (B3SA3, PETR4)
_NAME_STOPWORDS = frozenset({
    "sa", "s", "a", "cia", "companhia", "bco", "banco", "de", "do", "da", "dos", "das", "e",
    "em", "the", "inc", "ltd", "ltda", "holding", "holdings", "participacoes", "part", "grupo",
    "co", "corp", "nv", "n", "v", "brasil", "brazil", "ex",
})


def _name_tokens(text: object) -> frozenset[str]:
    """Tokens significativos de um nome de empresa (sem acentos, pontuação e termos genéricos)."""
    words = re.sub(r"[^a-z0-9]+", " ", normalize_text(text)).split()
    return frozenset(w for w in words if len(w) > 1 and w not in _NAME_STOPWORDS)


def _fca_rows(cvm_fca: pd.DataFrame | None) -> pd.DataFrame:
    """Ações/units/BDRs negociados em bolsa no FCA (versão mais recente por CNPJ e código)."""
    cols = ["cnpj", "name", "code", "valid_code", "share_class", "unit_composition", "active",
            "cvm_code"]
    if cvm_fca is None or cvm_fca.empty:
        return pd.DataFrame(columns=cols)
    df = cvm_fca.copy()
    if "Mercado" in df.columns:
        df = df[df["Mercado"].fillna("").map(normalize_text).isin(["bolsa", ""])]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["share_class"] = df.apply(_fca_class, axis=1)
    df = df[df["share_class"].notna()]
    if df.empty:
        return pd.DataFrame(columns=cols)
    if "Versao" in df.columns:
        df["Versao"] = pd.to_numeric(df["Versao"], errors="coerce")
    sort_cols = [c for c in ("Data_Referencia", "Versao") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)
    code = df["Codigo_Negociacao"].fillna("").astype(str).str.upper().str.strip()
    out = pd.DataFrame({
        "cnpj": df["CNPJ_Companhia"].astype(str).str.strip(),
        "name": df.get("Nome_Empresarial", pd.Series("", index=df.index)),
        "code": code,
        "valid_code": code.str.match(_VALID_B3_CODE),
        "share_class": df["share_class"],
        "unit_composition": df.get("Composicao_BDR_Unit", pd.Series(pd.NA, index=df.index)),
        "active": df.get("Data_Fim_Negociacao", pd.Series(pd.NA, index=df.index)).isna(),
        "cvm_code": df.get("Codigo_CVM", pd.Series(pd.NA, index=df.index)),
    })
    return out.drop_duplicates(["cnpj", "code", "share_class"], keep="last").reset_index(drop=True)


def _fca_by_code(cvm_fca: pd.DataFrame | None) -> pd.DataFrame:
    """Uma linha por código B3 válido (versão mais recente do FCA), só mercado de bolsa."""
    rows = _fca_rows(cvm_fca)
    rows = rows[rows["valid_code"]].drop_duplicates("code", keep="last")
    return rows.set_index("code")[["cnpj", "share_class", "unit_composition", "active",
                                   "cvm_code"]]


def _explicit_ids(universe: Universe, column: str,
                  overrides: Mapping[str, str] | None) -> dict[str, tuple[str, str]]:
    """Identificadores explícitos por emissor: parâmetro ``overrides`` > coluna do universo."""
    out: dict[str, tuple[str, str]] = {}
    if column in universe.lines.columns:
        for iid, grp in universe.lines.groupby("issuer_id"):
            vals = [str(v).strip() for v in grp[column].tolist() if _is_text(v)]
            if vals:
                out[str(iid)] = (vals[0], "universo")
    for iid, val in (overrides or {}).items():
        if _is_text(val):
            out[str(iid)] = (str(val).strip(), "override")
    return out


def _name_fallback(universe: Universe, fca_rows: pd.DataFrame, matched: set[str],
                   ) -> dict[str, tuple[str, str]]:
    """CNPJ por nome SÓ para companhias do FCA cujos códigos de negociação são inválidos.

    O FCA traz lixo em ``Codigo_Negociacao`` para ~15% das ações (ex.: CSN ``4030``, BTG
    ``000000``, CSN Mineração ``25585``). Casamento conservador: os tokens significativos de um
    nome contidos no outro, com correspondência ÚNICA nos dois sentidos. Sem casamento ⇒ fica
    ausente (use ``cnpj_overrides`` ou a coluna ``cnpj`` do universo).
    """
    if fca_rows.empty:
        return {}
    by_cnpj = fca_rows[fca_rows["active"]].groupby("cnpj")
    invalid = [(cnpj, _name_tokens(g["name"].iloc[-1]), g["code"].iloc[-1])
               for cnpj, g in by_cnpj if not g["valid_code"].any()]
    invalid = [t for t in invalid if t[1]]
    b3_issuers = sorted({str(i) for t, i in universe.lines["issuer_id"].items()
                         if b3_code(str(t)) is not None} - matched)
    cand: dict[str, list[tuple[str, str]]] = {}
    for iid in b3_issuers:
        u_tok = _name_tokens(universe.issuers.loc[iid, "issuer_name"])
        if not u_tok:
            continue
        hits = [(c, code) for c, tok, code in invalid if tok <= u_tok or u_tok <= tok]
        if len(hits) == 1:
            cand[iid] = hits[0]
    counts: dict[str, int] = {}
    for c, _ in cand.values():
        counts[c] = counts.get(c, 0) + 1
    return {iid: (c, code) for iid, (c, code) in cand.items() if counts[c] == 1}


LINE_MASTER_COLUMNS = [
    "issuer_id", "line_type", "market", "currency", "primary_line", "share_class",
    "shares_per_line", "validated", "validation_source", "cnpj", "cik",
]


def _class_spl(share_class: str | None, unit_text: object) -> float:
    if share_class in ("ON", "PN", "PNA", "PNB", "PNC", "PND"):
        return 1.0
    if share_class == "UNIT":
        return parse_unit_composition(unit_text)
    return float("nan")


def _resolve_lines(universe: Universe, cvm_fca: pd.DataFrame | None,
                   sec_tickers: pd.DataFrame | None, cnpj_overrides: Mapping[str, str] | None,
                   cik_overrides: Mapping[str, str] | None, name_fallback: bool,
                   ) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    fca = _fca_by_code(cvm_fca)
    rows_all = _fca_rows(cvm_fca)
    sec = pd.DataFrame(columns=SEC_TICKER_COLUMNS) if sec_tickers is None else sec_tickers
    sec_map = (sec.assign(ticker=sec["ticker"].astype(str).str.upper())
               .drop_duplicates("ticker").set_index("ticker")["cik"].map(format_cik))
    explicit_cnpj = _explicit_ids(universe, "cnpj", cnpj_overrides)
    explicit_cik = {k: (format_cik(v) or "", src)
                    for k, (v, src) in _explicit_ids(universe, "cik", cik_overrides).items()}
    matched = {str(universe.lines.loc[t, "issuer_id"]) for t in universe.lines.index
               if (c := b3_code(str(t))) is not None and c in fca.index}
    fallback = (_name_fallback(universe, rows_all, matched | set(explicit_cnpj))
                if name_fallback else {})
    notes: dict[str, list[str]] = {}
    for iid, (c, src) in explicit_cnpj.items():
        notes.setdefault(iid, []).append(f"CNPJ explícito ({src}): {c}")
    for iid, (c, code) in fallback.items():
        notes.setdefault(iid, []).append(
            f"CNPJ por nome no FCA (código de negociação inválido no FCA: {code!r}): {c}")
    for iid, (c, src) in explicit_cik.items():
        notes.setdefault(iid, []).append(f"CIK explícito ({src}): {c}")
    out = []
    for ticker, ln in universe.lines.iterrows():
        iid = str(ln["issuer_id"])
        lt = str(ln["line_type"])
        code = b3_code(str(ticker))
        share_class: str | None
        spl = float("nan")
        validated = False
        vsource = ""
        cnpj: str | None = None
        cik: str | None = None
        if code is not None:
            hit = fca.loc[code] if code in fca.index else None
            fca_class = hit["share_class"] if hit is not None else None
            share_class = fca_class if isinstance(fca_class, str) else b3_class_from_code(code)
            unit_text = hit["unit_composition"] if hit is not None else None
            if hit is not None:
                cnpj = str(hit["cnpj"])
                validated = bool(hit["active"])
                vsource = "CVM_FCA" if validated else "CVM_FCA(inativo)"
            alt = explicit_cnpj.get(iid)
            alt_src = alt[1] if alt else None
            if alt is None and iid in fallback:
                alt, alt_src = (fallback[iid][0], "nome"), "nome"
            if alt is not None and alt[0] != cnpj:
                cnpj = alt[0]
                validated = False
                vsource = f"CVM_FCA({alt_src})"
                same = rows_all[(rows_all["cnpj"] == cnpj)
                                & (rows_all["share_class"] == share_class)]
                unit_text = same["unit_composition"].iloc[-1] if not same.empty else None
            spl = _class_spl(share_class, unit_text)
        else:
            share_class = "ADR" if lt == "ADR" else ("US" if lt == "US_LISTED" else None)
            sym = str(ticker).upper().strip()
            if sym in sec_map.index and _is_text(sec_map.loc[sym]):
                cik = str(sec_map.loc[sym])
                validated = True
                vsource = "SEC"
            if iid in explicit_cik and lt in ("ADR", "US_LISTED") and explicit_cik[iid][0]:
                if cik != explicit_cik[iid][0]:
                    validated = False
                    vsource = f"SEC({explicit_cik[iid][1]})"
                cik = explicit_cik[iid][0]
            if lt == "ADR":
                ratio = pd.to_numeric(ln.get("adr_ratio"), errors="coerce")
                spl = float(ratio) if pd.notna(ratio) and ratio > 0 else float("nan")
            elif lt == "US_LISTED":
                spl = 1.0
        out.append({
            "yahoo_ticker": ticker, "issuer_id": iid, "line_type": lt,
            "market": ln.get("market", ""), "currency": ln["currency"],
            "primary_line": bool(ln.get("primary_line", False)), "share_class": share_class,
            "shares_per_line": spl, "validated": validated, "validation_source": vsource,
            "cnpj": cnpj, "cik": cik,
        })
    lm = pd.DataFrame(out, columns=["yahoo_ticker", *LINE_MASTER_COLUMNS])
    return lm.set_index("yahoo_ticker").sort_index(), notes


def build_line_master(universe: Universe, cvm_fca: pd.DataFrame | None,
                      sec_tickers: pd.DataFrame | None, *,
                      cnpj_overrides: Mapping[str, str] | None = None,
                      cik_overrides: Mapping[str, str] | None = None,
                      name_fallback: bool = True) -> pd.DataFrame:
    """Uma linha por ticker do universo: classe, ações por linha e validação oficial.

    ``shares_per_line`` converte o preço da linha em preço por ação local:
    ON/PN = 1; unit = soma da composição do FCA; ADR = ``adr_ratio`` oficial do universo;
    US_LISTED = 1 (a própria ação); BDR e composição ilegível ⇒ ``NaN``.
    ``validated`` só é verdadeiro quando o PRÓPRIO ticker consta de fonte oficial (FCA ativo
    ou mapa da SEC); CNPJ/CIK vindos de override, coluna do universo ou nome não validam o
    ticker.
    """
    lm, _ = _resolve_lines(universe, cvm_fca, sec_tickers, cnpj_overrides, cik_overrides,
                           name_fallback)
    return lm


SECURITY_MASTER_COLUMNS = [
    "issuer_name", "country", "gics_sector", "primary_ticker", "primary_line_type", "currency",
    "local_currency", "cnpj", "cvm_code", "cik", "share_classes", "adr_ticker", "adr_ratio",
    "tickers", "valid_tickers", "unvalidated_tickers", "fundamentals_source", "notes",
]


def _is_text(v: object) -> bool:
    """Verdadeiro só para texto não vazio (``None``/``NaN``/``pd.NA`` contam como ausentes)."""
    return isinstance(v, str) and bool(v.strip())


def _most_common(values: Iterable[str]) -> str | None:
    vals = [v for v in values if _is_text(v)]
    if not vals:
        return None
    s = pd.Series(vals).value_counts()
    return str(s.index[0])


def build_security_master(universe: Universe, cvm_fca: pd.DataFrame | None,
                          sec_tickers: pd.DataFrame | None, *,
                          cnpj_overrides: Mapping[str, str] | None = None,
                          cik_overrides: Mapping[str, str] | None = None,
                          name_fallback: bool = True) -> pd.DataFrame:
    """Security master por ``issuer_id``: CNPJ (BR), CIK (SEC), classes, ADR e tickers válidos.

    Precedência do CNPJ: ``cnpj_overrides`` > coluna ``cnpj`` do universo > código de
    negociação no FCA > nome (só para companhias com código inválido no FCA). CIK:
    ``cik_overrides`` > coluna ``cik`` do universo > mapa ticker→CIK da SEC.

    - ``adr_ratio``: razão OFICIAL do universo (ações locais por ADR) da linha ADR primária
      (ou da primeira em ordem alfabética).
    - ``fundamentals_source``: ``CVM`` quando há CNPJ, senão ``SEC`` quando há CIK, senão ``NaN``.
    - ``notes``: origem de identificadores não validados pelo ticker e divergências.
    """
    lm, id_notes = _resolve_lines(universe, cvm_fca, sec_tickers, cnpj_overrides,
                                  cik_overrides, name_fallback)
    rows_all = _fca_rows(cvm_fca)
    cvm_code_by_cnpj = (rows_all.dropna(subset=["cvm_code"]).drop_duplicates("cnpj")
                        .set_index("cnpj")["cvm_code"] if not rows_all.empty
                        else pd.Series(dtype=str))
    explicit_cik = {k: format_cik(v) for k, (v, _) in
                    _explicit_ids(universe, "cik", cik_overrides).items()}
    rows = []
    for iid, iss in universe.issuers.iterrows():
        lines = lm[lm["issuer_id"] == iid]
        notes: list[str] = list(id_notes.get(str(iid), []))
        primary = str(iss["primary_ticker"])
        cnpjs = [c for c in lines["cnpj"].tolist() if _is_text(c)]
        cnpj = None
        if cnpjs:
            if len(set(cnpjs)) > 1:
                prim_cnpj = lines.loc[primary, "cnpj"] if primary in lines.index else None
                cnpj = prim_cnpj if _is_text(prim_cnpj) else _most_common(cnpjs)
                notes.append(f"CNPJs divergentes entre linhas: {sorted(set(cnpjs))}")
            else:
                cnpj = cnpjs[0]
        ciks = [c for c in lines["cik"].tolist() if _is_text(c)]
        cik = explicit_cik.get(str(iid)) or _most_common(ciks)
        if len(set(ciks)) > 1:
            notes.append(f"CIKs divergentes entre linhas: {sorted(set(ciks))}")
        classes = sorted({c for c in lines["share_class"].tolist()
                          if _is_text(c) and c not in ("ADR", "US")})
        adr_lines = lines[lines["line_type"] == "ADR"]
        adr_ticker = None
        adr_ratio = float("nan")
        if not adr_lines.empty:
            prim_adr = adr_lines[adr_lines.index == primary]
            chosen = prim_adr if not prim_adr.empty else adr_lines.sort_index().iloc[:1]
            adr_ticker = str(chosen.index[0])
            adr_ratio = float(chosen["shares_per_line"].iloc[0])
        local = lines[lines["line_type"] == "LOCAL"]
        local_ccy = _most_common(local["currency"].astype(str).tolist()) if not local.empty else None
        valid = sorted(lines.index[lines["validated"]].tolist())
        invalid = sorted(lines.index[~lines["validated"]].tolist())
        source = "CVM" if cnpj else ("SEC" if cik else None)
        rows.append({
            "issuer_id": iid, "issuer_name": iss["issuer_name"], "country": iss["country"],
            "gics_sector": iss["gics_sector"], "primary_ticker": primary,
            "primary_line_type": iss.get("primary_line_type"),
            "currency": iss.get("primary_currency"), "local_currency": local_ccy,
            "cnpj": cnpj,
            "cvm_code": (cvm_code_by_cnpj.get(cnpj) if cnpj and not cvm_code_by_cnpj.empty
                         else None),
            "cik": cik, "share_classes": "|".join(classes) if classes else None,
            "adr_ticker": adr_ticker, "adr_ratio": adr_ratio,
            "tickers": "|".join(sorted(lines.index)), "valid_tickers": "|".join(valid),
            "unvalidated_tickers": "|".join(invalid), "fundamentals_source": source,
            "notes": "; ".join(notes),
        })
    out = pd.DataFrame(rows, columns=["issuer_id", *SECURITY_MASTER_COLUMNS])
    return out.set_index("issuer_id").sort_index()


def security_master_summary(sm: pd.DataFrame) -> dict[str, int]:
    """Contagens de cobertura (para relatório/manifesto)."""
    return {
        "issuers": int(len(sm)),
        "with_cnpj": int(sm["cnpj"].notna().sum()),
        "with_cik": int(sm["cik"].notna().sum()),
        "without_source": int(sm["fundamentals_source"].isna().sum()),
        "br_without_cnpj": int(((sm["country"] == "BR") & sm["cnpj"].isna()).sum()),
    }
