"""Camada de dados PÚBLICOS para o motor de cobertura e os vetos de risco (workstream A1).

Somente fontes públicas e reproduzíveis por qualquer pessoa:

- **CVM dados abertos** — DFP/ITR completos (DRE, BPA, BPP, DFC, DVA, composição do capital),
  FCA (CNPJ ↔ ticker), FRE (ações em circulação) e IPE (assembleias, fatos relevantes e o
  "Calendário de Eventos Corporativos");
- **SEC EDGAR** — ``companyfacts`` (XBRL us-gaap/ifrs-full) dos emissores com CIK;
- **Yahoo Finance** (yfinance) — demonstrações agregadas para quem não arquiva na CVM/SEC,
  consenso público (estimativas, preços-alvo, recomendação), proventos, calendário, float;
- **iShares / Global X / B3** — carteiras de ETFs;
- **FRED / BCB (SGS e Focus) / Banxico (com token)** — taxas e expectativas.

Todo arquivo bruto baixado é arquivado com SHA-256 em ``<root>/publico/`` (ver
:mod:`.publico_arquivo`; ``root`` padrão ``data/`` na rotina); ``offline=True`` lê só o arquivo
(nunca a rede). Point-in-time: só entra o que foi publicado (e coletado, no caso de retratos
sem data própria) até ``as_of``. Dado ausente nunca vira zero.

Contrato compartilhado com A2 (``cobertura run``) e E2 (vetos de risco): :class:`Proveniencia`,
:data:`CANONICAL_ITEMS`, :func:`demonstrativos`, :func:`consenso_publico`, :func:`dividendos`,
:func:`composicao_etf`, :func:`eventos_corporativos`, :func:`taxas_publicas`,
:func:`free_float`.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..universe import Universe, load_universe
from . import publico_cvm as cvm
from . import publico_etf as etfm
from . import publico_ri as ri_pdf
from . import publico_sec as sec
from . import publico_taxas as tx
from . import publico_yahoo as yh
from .fundamentals_pit import resolve_share_scale
from .publico_arquivo import Arquivo, RegistroArquivo, agora_utc, data_local
from .publico_fatos import FLUXOS as FLUXOS_PIT
from .publico_fatos import derivados, selecionar_pit
from .publico_pdf import PdfIlegivel, celulas
from .security_master import (
    DEFAULT_USER_AGENT,
    HttpError,
    RateLimiter,
    _sec_get,
    build_security_master,
    default_http_get,
    format_cik,
    parse_fca_zip,
)

logger = logging.getLogger(__name__)

HttpGet = Callable[[str, dict], bytes]

FONTES_PUBLICAS = ("CVM", "SEC", "RI", "YAHOO", "BCB", "FRED", "B3", "ISHARES", "GLOBALX",
                   "DAMODARAN", "SIMULADO")

CANONICAL_ITEMS: tuple[str, ...] = (
    "receita", "lucro_bruto", "ebit", "ebitda", "d_a", "resultado_financeiro", "lucro_antes_ir",
    "ir_csll", "lucro_liquido", "lucro_liquido_controladores", "cfo", "capex", "fcf",
    "d_a_dfc", "adicoes_direito_uso", "depreciacao_direito_uso",
    "variacao_capital_giro_operacional", "juros_pagos_operacionais",
    "dividendos_pagos", "recompras", "caixa", "aplicacoes_cp", "divida_bruta", "divida_liquida",
    "arrendamentos", "arrendamentos_pagos", "patrimonio_liquido", "patrimonio_controladores",
    "participacao_minoritarios", "ativo_total", "acoes_emitidas", "acoes_tesouraria",
    "acoes_em_circulacao", "provisao_credito", "carteira_credito", "margem_financeira",
    "receita_servicos", "despesa_pdd",
)
"""Itens canônicos (coluna ``item``). Convenção de sinais (a da CVM): receitas e lucros positivos;
despesas negativas (``ir_csll``, ``resultado_financeiro`` líquido negativo, ``despesa_pdd``);
``d_a``, ``capex``, ``dividendos_pagos``, ``recompras`` e ``provisao_credito`` em módulo; ``cfo``
e ``fcf`` com sinal. Valores em unidades da moeda (``escala = 1``); ações em quantidade."""

DEMONSTRATIVOS_COLUNAS = [
    "issuer_id", "demonstrativo", "freq", "period_end", "item", "value", "currency", "escala",
    "consolidado", "fonte", "url", "documento", "data_publicacao", "sha256", "pit_estimado",
    "nota", "data_coleta",
]
CONSENSO_COLUNAS = [
    "ticker", "eps_fy1", "eps_fy2", "receita_fy1", "receita_fy2", "n_analistas_eps",
    "alvo_medio", "alvo_mediano", "alvo_alto", "alvo_baixo", "n_analistas_alvo",
    "recomendacao_media", "fonte", "data_coleta", "moeda_cotacao", "moeda_estimativas",
    "preco_referencia_yahoo", "url", "sha256", "moeda_receita", "sha256_info",
    "data_coleta_info",
]
"""``moeda_estimativas`` = moeda do LPA de consenso; ``moeda_receita`` = moeda da receita de
consenso (cada uma da própria tabela do Yahoo; ausente ⇒ ``None``). ``sha256``/``data_coleta``
= arquivo de estimativas (LPA, receita, preços-alvo); ``sha256_info``/``data_coleta_info`` =
arquivo ``info`` (recomendação média, nº de analistas do alvo, moeda de cotação e o alvo
quando a tabela de preços-alvo não veio)."""
DIVIDENDOS_COLUNAS = ["ticker", "data_ex", "valor_por_acao", "moeda", "fonte", "url", "sha256"]
EVENTOS_COLUNAS = ["issuer_id", "data", "tipo", "estimada", "fonte", "url", "documento",
                   "janela_inicio", "janela_fim"]
TAXAS_COLUNAS = ["serie", "data", "valor", "fonte", "url", "sha256"]
FLOAT_COLUNAS = ["issuer_id", "free_float_pct", "fonte", "data_ref", "url", "sha256",
                 "detalhe"]

MAX_WORKERS = 8
SEC_LIMITER = RateLimiter(8.0)
NOTA_CONSENSO = "consenso público Yahoo Finance"
_MOEDA_SUFIXO = {".SA": "BRL", ".MX": "MXN", ".SN": "CLP", ".CL": "COP", ".LM": "PEN",
                 ".BA": "ARS"}


@dataclass(frozen=True)
class Proveniencia:
    """Origem pública de um insumo: fonte, endereço, documento, publicação, coleta e hash."""

    fonte: str
    url: str | None
    documento: str | None
    data_publicacao: date | None
    data_coleta: datetime | None
    sha256: str | None

    @staticmethod
    def de_registro(reg: RegistroArquivo, *, documento: str | None = None,
                    data_publicacao: date | None = None) -> Proveniencia:
        return Proveniencia(fonte=reg.fonte, url=reg.url, documento=documento,
                            data_publicacao=data_publicacao, data_coleta=reg.data_coleta,
                            sha256=reg.sha256)


# ======================================================================
# Infraestrutura comum
# ======================================================================

def _arquivo(root: Path | str | None, offline: bool) -> Arquivo:
    return Arquivo(root, offline=offline)


def _http(http_get: HttpGet | None) -> HttpGet:
    return http_get or default_http_get


def _baixar(http_get: HttpGet | None, url: str, headers: dict | None = None,
            ) -> Callable[[], bytes | None]:
    def f() -> bytes | None:
        try:
            return _http(http_get)(url, {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})})
        except HttpError as exc:
            if exc.status == 404:
                return None
            raise
    return f


def _simulado(arq: Arquivo, nome: str, ate: date, colunas: list[str]) -> pd.DataFrame | None:
    """Pacote SIMULADO (DADOS SIMULADOS) do arquivo — só em modo offline (demo/testes) e só
    num arquivo exclusivamente sintético: um arquivo com fontes reais (ex.: ``data/``) nunca
    devolve dados simulados, mesmo que um pacote SIMULADO tenha sido gravado ali por engano."""
    if not arq.offline:
        return None
    from .publico_sintetico import AVISO, ler_pacote

    chaves = arq.chaves()
    if not any(k.startswith("SIMULADO/") for k in chaves):
        return None
    if any(not k.startswith("SIMULADO/") for k in chaves):
        msg = "pacotes SIMULADO ignorados: o arquivo também contém fontes reais"
        if msg not in arq.falhas:
            arq.falhas.append(msg)
        return None
    got = ler_pacote(arq, nome, ate)
    if got is None:
        return None
    sha, linhas = got
    df = pd.DataFrame(linhas).reindex(columns=colunas)
    if "sha256" in df.columns:
        df["sha256"] = df["sha256"].fillna(sha)
    df.attrs = {"as_of": ate.isoformat(), "falhas": [], "aviso": AVISO}
    return df


def _baixar_pdf(http_get: HttpGet | None, url: str, esperas: tuple[float, ...] = (2.0, 5.0),
                sleep: Callable[[float], None] | None = None) -> Callable[[], bytes | None]:
    """Download de documento do sistema da CVM: o servidor responde HTML sob carga; repete."""
    import time

    def f() -> bytes | None:
        conteudo = _baixar(http_get, url)()
        for espera in esperas:
            if conteudo is None or conteudo.startswith(b"%PDF"):
                return conteudo
            (sleep or time.sleep)(espera)
            conteudo = _baixar(http_get, url)()
        return conteudo
    return f


def _universo(universe: Universe | None) -> Universe:
    return universe if universe is not None else load_universe()


def _hoje() -> date:
    """Hoje em São Paulo (às 22h BRT a data UTC já é a do dia seguinte)."""
    return data_local(agora_utc())


def _data_coleta(reg: RegistroArquivo | None) -> pd.Timestamp | None:
    return pd.Timestamp(reg.data_coleta) if reg is not None else None


def _validar_zip(c: bytes) -> None:
    cvm.validar_zip(c)


def _validar_pdf(c: bytes) -> None:
    if not c.startswith(b"%PDF"):
        raise ValueError("Resposta não é PDF.")


def _validar_globalx(c: bytes) -> None:
    if b"% of Net Assets" not in c:
        raise ValueError("CSV Global X sem carteira.")


def _validar_yahoo(c: bytes) -> None:
    yh.ler_json(c)


def _validar_tickers_sec(c: bytes) -> None:
    sec.parse_company_tickers(c)


def _arquivamentos_sec(arq: Arquivo, cik10: str, ref: date, desde: date,
                       http_get: HttpGet | None) -> pd.DataFrame:
    """Histórico oficial arquivado, inclusive páginas antigas que intersectam a janela."""
    url = sec.URL_SUBMISSIONS.format(cik=cik10)
    got = arq.obter(f"SEC/submissions/CIK{cik10}.json", "SEC", url,
                    lambda: _sec_get(url, http_get, None, SEC_LIMITER), ate=ref,
                    max_idade_dias=1.0, validar=lambda c: sec.validar_submissions(c, cik10) and None)
    if got is None:
        return pd.DataFrame(columns=sec.ARQUIVAMENTOS_COLUNAS)
    obj = sec.validar_submissions(got[1], cik10)
    frames = [sec.arquivamentos_sec(obj, cik10, ref)]
    for page in (obj.get("filings") or {}).get("files") or []:
        nome = str(page.get("name", ""))
        if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", nome):
            continue
        inicio = pd.to_datetime(page.get("filingFrom"), errors="coerce")
        fim = pd.to_datetime(page.get("filingTo"), errors="coerce")
        if pd.isna(inicio) or pd.isna(fim) or fim.date() < desde or inicio.date() > ref:
            continue
        page_url = f"https://data.sec.gov/submissions/{nome}"
        older = arq.obter(f"SEC/submissions/{nome}", "SEC", page_url,
                         lambda u=page_url: _sec_get(u, http_get, None, SEC_LIMITER), ate=ref,
                         max_idade_dias=30.0, validar=lambda c: sec.validar_submissions(c) and None)
        if older:
            frames.append(sec.arquivamentos_sec(sec.validar_submissions(older[1]), cik10, ref))
    out = pd.concat(frames, ignore_index=True).drop_duplicates("accn")
    return out[out["filed"] >= pd.Timestamp(desde)].sort_values("filed", ascending=False)


def _validar_banxico(c: bytes) -> None:
    import json

    obj = json.loads(c)
    bmx = obj.get("bmx") if isinstance(obj, dict) else None
    if not isinstance(bmx, dict) or not isinstance(bmx.get("series"), list):
        raise ValueError("Resposta do Banxico (SIE) sem 'bmx.series'.")


def _idade_cvm(ano: int, as_of: date) -> float:
    """Idade máxima (dias) para reaproveitar um ZIP da CVM sem nova coleta."""
    return 1.0 if ano >= as_of.year - 1 else 30.0


def _obter_cvm(arq: Arquivo, doc: str, ano: int, as_of: date, http_get: HttpGet | None,
               ) -> tuple[RegistroArquivo, bytes] | None:
    nome = f"{doc.lower()}_cia_aberta_{ano}.zip"
    url = cvm.url_zip(doc, ano)
    return arq.obter(f"CVM/{doc.upper()}/{nome}", "CVM", url, _baixar(http_get, url),
                     ate=as_of, max_idade_dias=_idade_cvm(ano, as_of), validar=_validar_zip)


# ----------------------------------------------------------------- mestre de identificadores

def _cik_map(arq: Arquivo, uni: Universe, as_of: date, http_get: HttpGet | None,
             ) -> pd.DataFrame:
    """``ticker → CIK`` (SEC) para as linhas listadas nos EUA (arquivado)."""
    us = sorted({str(t).upper() for t, ln in uni.lines.iterrows()
                 if str(ln["line_type"]) in ("ADR", "US_LISTED")})
    rows: list[dict] = []
    chave = "SEC/mapa/company_tickers_exchange.json"
    if os.environ.get("SEC_USER_AGENT", "").strip() or arq.offline:
        # www.sec.gov exige contato no User-Agent; sem ele, só o índice de entidades (efts)
        got = arq.obter(chave, "SEC", sec.URL_TICKERS,
                        lambda: _sec_get(sec.URL_TICKERS, http_get, None, SEC_LIMITER),
                        ate=as_of, max_idade_dias=7.0, validar=_validar_tickers_sec)
    else:
        reg = arq.buscar(chave, as_of)
        got = (reg, arq.ler(reg)) if reg is not None else None
    if got is not None:
        mapa = sec.parse_company_tickers(got[1])
        rows = [{"cik": mapa[t], "name": "", "ticker": t, "exchange": None}
                for t in us if t in mapa]
        return pd.DataFrame(rows, columns=["cik", "name", "ticker", "exchange"])

    def um(t: str) -> dict | None:
        url = sec.URL_EFTS.format(q=t)
        r = arq.obter(f"SEC/efts/{t}.json", "SEC", url,
                      lambda: _sec_get(url, http_get, None, SEC_LIMITER), ate=as_of,
                      max_idade_dias=30.0, validar=sec.validar_efts)
        if r is None:
            return None
        try:
            hit = sec.parse_efts(r[1], t)
        except ValueError:
            return None
        return None if hit is None else {"cik": hit["cik"], "name": hit["nome"], "ticker": t,
                                         "exchange": None}

    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = [r for r in ex.map(um, us) if r is not None]
    return pd.DataFrame(rows, columns=["cik", "name", "ticker", "exchange"])


IDENTIFICADORES_CURADOS: dict[str, dict[str, str]] = {
    # O FCA lista o código de negociação da MBRF (ex-Marfrig, CNPJ 03.853.896/0001-40) como
    # "ADR": sem o CNPJ, um emissor que arquiva na CVM cairia no Yahoo.
    "BR_MBRF": {"cnpj": "03.853.896/0001-40"},
}
"""Identificadores públicos conferidos manualmente (``issuer_id`` → ``cnpj``/``cik``); têm
precedência sobre a correspondência pelo FCA/SEC. Fonte: cadastro público da CVM/SEC."""


def mestre_publico(as_of: date, *, offline: bool = False, root: Path | None = None,
                   universe: Universe | None = None, http_get: HttpGet | None = None,
                   arquivo: Arquivo | None = None) -> pd.DataFrame:
    """Security master (CNPJ via CVM FCA, CIK via SEC) por ``issuer_id`` — fontes arquivadas.

    O FCA do ano corrente só traz quem já entregou o formulário no ano (a maioria entrega até
    maio): o do ano anterior entra junto, com o do ano corrente prevalecendo por companhia e
    código (identidade cadastral não cria look-ahead). ``IDENTIFICADORES_CURADOS`` prevalece."""
    arq = arquivo or _arquivo(root, offline)
    uni = _universo(universe)
    partes = []
    for ano in (as_of.year - 1, as_of.year):
        url = f"{cvm.CVM_DOC_BASE_URL}/FCA/DADOS/fca_cia_aberta_{ano}.zip"
        got = arq.obter(f"CVM/FCA/fca_cia_aberta_{ano}.zip", "CVM", url, _baixar(http_get, url),
                        ate=as_of, max_idade_dias=7.0, validar=_validar_zip)
        if got is None:
            continue
        try:
            partes.append(parse_fca_zip(got[1]))
        except ValueError as exc:
            arq.falhas.append(f"FCA {ano}: {exc}")
    # ordem cronológica (ano anterior, depois o corrente): a leitura do FCA fica com a versão
    # mais recente por companhia e código
    fca = pd.concat(partes, ignore_index=True) if partes else None
    sec_t = _cik_map(arq, uni, as_of, http_get)
    cur = {i: v for i, v in IDENTIFICADORES_CURADOS.items() if i in uni.issuers.index}
    return build_security_master(
        uni, fca, sec_t,
        cnpj_overrides={i: v["cnpj"] for i, v in cur.items() if v.get("cnpj")} or None,
        cik_overrides={i: v["cik"] for i, v in cur.items() if v.get("cik")} or None)


# ======================================================================
# demonstrativos
# ======================================================================

_CACHE_CVM: dict[tuple[str, int], pd.DataFrame] = {}


def _fatos_cvm_zip(reg: RegistroArquivo, conteudo: bytes, doc: str, ano: int,
                   cnpjs: frozenset[str]) -> pd.DataFrame:
    chave = (reg.sha256, hash(cnpjs))
    if chave in _CACHE_CVM:
        return _CACHE_CVM[chave]
    tabs = cvm.ler_zip_demonstracoes(conteudo, doc, ano, cnpjs)
    f = cvm.fatos_cvm(tabs, doc)
    f["fonte"] = "CVM"
    f["sha256"] = reg.sha256
    f["data_coleta"] = pd.Timestamp(reg.data_coleta)
    if len(_CACHE_CVM) > 32:
        _CACHE_CVM.clear()
    _CACHE_CVM[chave] = f
    return f


def _resolver_unidade_acoes(f: pd.DataFrame) -> pd.DataFrame:
    """Unidade das ações da CVM não conferida no próprio documento (``na``/``divergente``):
    resolvida por continuidade com o documento anterior já conferido (sem look-ahead), como em
    :func:`.fundamentals_pit.resolve_share_scale`; o fator vale para emitidas e tesouraria."""
    sh = f[f["item"] == "acoes_em_circulacao"]
    if sh.empty:
        return f
    tag = sh["documento"].str.extract(r"unidade (\S+)\)$")[0].fillna("ok")
    raw = pd.DataFrame({"entity": sh["entidade"].to_numpy(), "metric": "shares_outstanding",
                        "period_start": pd.NaT, "period_end": sh["period_end"].to_numpy(),
                        "value": sh["value"].to_numpy(), "currency": None,
                        "received_date": sh["received_date"].to_numpy(),
                        "version": sh["version"].to_numpy(),
                        "source": ("cvm:x:capital|unidade:" + tag).to_numpy(),
                        "idx0": sh.index.to_numpy()})
    res = resolve_share_scale(raw)
    mudou = res[res["source"] != raw["source"]]
    if mudou.empty:
        return f
    f = f.copy()
    for r in mudou.itertuples(index=False):
        i0 = r.idx0
        fator = float(r.value) / float(f.at[i0, "value"])
        novo = r.source.rsplit("unidade:", 1)[1]
        alvo = f.index[(f["entidade"] == f.at[i0, "entidade"])
                       & (f["period_end"] == f.at[i0, "period_end"])
                       & (f["version"] == f.at[i0, "version"])
                       & (f["received_date"] == f.at[i0, "received_date"])
                       & f["item"].isin(["acoes_em_circulacao", "acoes_emitidas",
                                         "acoes_tesouraria"])]
        f.loc[alvo, "value"] = f.loc[alvo, "value"] * fator
        f.loc[alvo, "documento"] = f.loc[alvo, "documento"].str.replace(
            r"unidade \S+\)$", f"unidade {novo})", regex=True)
    return f


def _linha_yahoo(uni: Universe, iid: str) -> str:
    """Linha preferida para dados do Yahoo: local primária, senão a primária."""
    ln = uni.lines_for(iid)
    loc = ln[ln["line_type"] == "LOCAL"]
    if not loc.empty:
        prim = loc[loc["primary_line"].astype(bool)]
        return str((prim if not prim.empty else loc).index[0])
    return uni.primary_ticker(iid)


def _parte_yahoo(arq: Arquivo, ticker: str, parte: str, as_of: date,
                 yf_factory: Callable[[str], Any] | None, *, instantaneo: bool,
                 ) -> tuple[RegistroArquivo, dict] | None:
    safe = re.sub(r"[^A-Za-z0-9_.=\-]", "_", ticker)
    got = arq.obter(f"YAHOO/{parte}/{safe}.json", "YAHOO", yh.URL_QUOTE.format(t=ticker),
                    lambda: yh.coletar_parte(ticker, parte, factory=yf_factory), ate=as_of,
                    max_idade_dias=1.0, instantaneo=instantaneo, validar=_validar_yahoo)
    if got is None:
        return None
    return got[0], yh.ler_json(got[1])


def demonstrativos(issuer_ids: Sequence[str], as_of: date, *, offline: bool = False,
                   root: Path | None = None, universe: Universe | None = None,
                   http_get: HttpGet | None = None,
                   yf_factory: Callable[[str], Any] | None = None, anos: int = 5,
                   complementar_yahoo: bool = True) -> pd.DataFrame:
    """Demonstrações em formato longo (``DEMONSTRATIVOS_COLUNAS``), point-in-time em ``as_of``.

    Fonte por emissor: CVM (CNPJ; trimestral e anual) > SEC (CIK; ``companyfacts``) > Yahoo
    (agregado; data de publicação estimada, ``pit_estimado = True``). Com
    ``complementar_yahoo``, o que a SEC não cobre (ex.: 20-F só anual) entra do Yahoo — fluxos
    por (``freq, period_end, item``) e saldos por (``period_end, item``) ausentes na fonte
    oficial, na mesma moeda, sem contagens de ações quando a fonte oficial as tem — só se a
    magnitude do Yahoo confere com a da fonte oficial nos períodos comuns; emissores em ARS
    (IAS 29) não são complementados (unidade de medida diferente). XBRL com menos de 2
    exercícios de lucro ⇒ Yahoo assume.

    Conferência (``nota`` começando com "conferência:", ``value`` ausente — nunca um palpite):
    contagens de ações sem unidade conferida, com emitidas < em circulação ou fora de
    0,5–2× a contagem anterior sem confirmação pela seguinte; valores ≥ 200× fora dos períodos
    vizinhos. Documento da CVM com escala incompatível com os demais da companhia é descartado.
    Itens calculados (``ebit`` na falta, ``ebitda``, ``fcf``, ``divida_liquida``) são refeitos
    por código depois do complemento e da conferência.

    Uma linha por chave: a publicação mais recente conhecida em ``as_of``. ``attrs``:
    ``falhas`` (coletas que falharam — o emissor fica sem os itens), ``qa`` (alertas de
    conferência), ``moeda_trocada`` (emissores que mudaram a moeda de apresentação).
    """
    arq = _arquivo(root, offline)
    uni = _universo(universe)
    pedidos = [str(i) for i in dict.fromkeys(issuer_ids)]
    desconhecidos = [i for i in pedidos if i not in uni.issuers.index]
    pedidos = [i for i in pedidos if i in uni.issuers.index]
    sim = _simulado(arq, "demonstrativos", as_of, DEMONSTRATIVOS_COLUNAS)
    if sim is not None:
        sim["data_publicacao"] = pd.to_datetime(sim["data_publicacao"]).dt.date
        sim["period_end"] = pd.to_datetime(sim["period_end"])
        sim["data_coleta"] = pd.Timestamp(arq.buscar("SIMULADO/pacotes/demonstrativos.json",
                                                     as_of).data_coleta)
        sim = sim[sim["issuer_id"].isin(pedidos) & (sim["data_publicacao"] <= as_of)]
        return sim.reset_index(drop=True)
    sm = mestre_publico(as_of, universe=uni, http_get=http_get, arquivo=arq)
    frames: list[pd.DataFrame] = []
    ent_iss: dict[str, list[str]] = {}
    cobertos: set[str] = set()
    qa: list[str] = []

    # ---- CVM
    cnpj_de = {i: str(sm.loc[i, "cnpj"]) for i in pedidos
               if i in sm.index and isinstance(sm.loc[i, "cnpj"], str) and sm.loc[i, "cnpj"]}
    if cnpj_de:
        todos = frozenset(str(c) for c in sm["cnpj"].dropna().astype(str) if c)
        for iid, c in cnpj_de.items():
            ent_iss.setdefault(c, []).append(iid)
        zips = ([("DFP", a) for a in range(as_of.year - anos, as_of.year + 1)]
                + [("ITR", a) for a in range(as_of.year - 2, as_of.year + 1)])
        for doc, ano in zips:
            got = _obter_cvm(arq, doc, ano, as_of, http_get)
            if got is None:
                continue
            try:
                f = _fatos_cvm_zip(got[0], got[1], doc, ano, todos)
            except Exception as exc:  # ZIP corrompido/layout inesperado: registrado
                arq.falhas.append(f"CVM {doc} {ano}: leitura falhou ({exc})")
                continue
            for q in f.attrs.get("qa") or []:
                for iid in ent_iss.get(q["cnpj"], []):
                    qa.append(f"{iid}: {q['documento']}: {q['msg']}")
            f = f[f["entidade"].isin(set(cnpj_de.values()))]
            if not f.empty:
                frames.append(f)
        if frames:
            cvm_f = _resolver_unidade_acoes(pd.concat(frames, ignore_index=True))
            frames = [_qa_escala_documentos(cvm_f, ent_iss, qa)]
        com_cvm = set().union(*[set(f["entidade"]) for f in frames]) if frames else set()
        cobertos |= {i for i, c in cnpj_de.items() if c in com_cvm}

    # ---- Notas SEC complementares: períodos e documento primário conferidos no
    # histórico oficial, inclusive 6-K sem XBRL. Mesma entidade do balanço principal.
    for iid in pedidos:
        cik_notas = format_cik(sm.loc[iid, "cik"]) if iid in sm.index else None
        catalogados = sec.documentos_fluxos_sec(cik_notas, as_of) if cik_notas else []
        if not catalogados:
            continue
        historico = _arquivamentos_sec(arq, cik_notas, as_of, date(as_of.year - anos, 1, 1), http_get)
        entidade = cnpj_de[iid] if iid in cobertos and iid in cnpj_de else cik_notas
        for doc_notas in catalogados:
            oficial = historico[historico["accn"] == doc_notas["accn"]]
            if len(oficial) != 1:
                arq.falhas.append(f"SEC ({iid}): nota catalogada sem arquivamento oficial conferido")
                continue
            r_notas = oficial.iloc[0].to_dict()
            try:
                got_notas = arq.obter(f"SEC/notas/{cik_notas}/{doc_notas['accn']}/{doc_notas['documento']}",
                                     "SEC", doc_notas["url"],
                                     lambda u=doc_notas["url"]: _sec_get(u, http_get, None, SEC_LIMITER),
                                     ate=as_of, max_idade_dias=3650.0,
                                     validar=lambda c, d=doc_notas, r=r_notas, e=entidade:
                                     sec.fatos_fluxos_documento(c, e, d, r))
                if got_notas:
                    f_notas = sec.fatos_fluxos_documento(got_notas[1], entidade, doc_notas, r_notas)
                    if not f_notas.empty:
                        f_notas["fonte"] = "SEC"
                        f_notas["sha256"] = got_notas[0].sha256
                        f_notas["data_coleta"] = pd.Timestamp(got_notas[0].data_coleta)
                        frames.append(f_notas)
                        if iid not in ent_iss.get(entidade, []):
                            ent_iss.setdefault(entidade, []).append(iid)
            except ValueError as exc:
                arq.falhas.append(f"SEC ({iid}): nota complementar recusada ({exc})")

    # ---- Classes SEC também para emissor coberto pela CVM. Só complementa contagens
    # da data efetivamente observada, na entidade cadastral do balanço CVM; não troca
    # moeda/demonstrações nem transporta a contagem anual para um trimestre posterior.
    ciks_classes = sec.ciks_classes_sec()
    for iid in sorted(cobertos):
        cik_capital = format_cik(sm.loc[iid, "cik"])
        if iid not in cnpj_de or cik_capital not in ciks_classes:
            continue
        historico = _arquivamentos_sec(arq, cik_capital, as_of, date(as_of.year - anos, 1, 1), http_get)
        for r_capital in sec.documentos_classes_sec(historico, cik_capital).to_dict("records"):
            prefixo = f"SEC/filings/{cik_capital}/{r_capital['accn']}/"
            indice_url = sec.url_filing(cik_capital, r_capital["accn"]) + "index.json"
            indice = arq.obter(prefixo + "index.json", "SEC", indice_url,
                               lambda u=indice_url: _sec_get(u, http_get, None, SEC_LIMITER),
                               ate=as_of, max_idade_dias=3650.0,
                               validar=lambda c, r=r_capital, k=cik_capital: sec.instancia_sec(c, k, r))
            xml_url = sec.instancia_sec(indice[1], cik_capital, r_capital) if indice else None
            if not xml_url:
                continue
            try:
                documento = arq.obter(prefixo + xml_url.rsplit("/", 1)[-1], "SEC", xml_url,
                                      lambda u=xml_url: _sec_get(u, http_get, None, SEC_LIMITER),
                                      ate=as_of, max_idade_dias=3650.0,
                                      validar=lambda c, r=r_capital, k=cik_capital:
                                      sec.companyfacts_documento(c, k, r))
                if documento:
                    f_capital = sec.fatos_sec(sec.companyfacts_documento(documento[1], cik_capital, r_capital))
                    f_capital = f_capital[f_capital["item"].isin(sec.ACOES)
                                            & f_capital["nota"].fillna("").str.contains("classes completas da capa")].copy()
                    if not f_capital.empty:
                        f_capital["entidade"] = cnpj_de[iid]
                        f_capital["fonte"] = "SEC"
                        f_capital["sha256"] = documento[0].sha256
                        f_capital["data_coleta"] = pd.Timestamp(documento[0].data_coleta)
                        f_capital["url"] = xml_url
                        frames.append(f_capital)
            except ValueError as exc:
                arq.falhas.append(f"SEC ({iid}): classes complementares recusadas ({exc})")

    # ---- SEC
    cik_de = {i: format_cik(sm.loc[i, "cik"]) for i in pedidos
              if i not in cobertos and i in sm.index and isinstance(sm.loc[i, "cik"], str)}
    cik_de = {i: c for i, c in cik_de.items() if c}

    def um_sec(item: tuple[str, str]) -> pd.DataFrame | None:
        iid, cik10 = item
        url = sec.URL_COMPANYFACTS.format(cik=cik10)
        got = arq.obter(f"SEC/companyfacts/CIK{cik10}.json", "SEC", url,
                        lambda: _sec_get(url, http_get, None, SEC_LIMITER), ate=as_of,
                        max_idade_dias=1.0,
                        validar=lambda c: sec.validar_companyfacts(c, cik10) and None)
        partes = []

        def add_sec(fatos: pd.DataFrame, reg: RegistroArquivo, fonte_url: str) -> None:
            if fatos.empty:
                return
            fatos = fatos.copy()
            fatos["fonte"] = "SEC"
            fatos["sha256"] = reg.sha256
            fatos["data_coleta"] = pd.Timestamp(reg.data_coleta)
            if fonte_url != url:
                fatos["url"] = fonte_url
            partes.append(fatos)

        if got:
            add_sec(sec.fatos_sec(sec.validar_companyfacts(got[1], cik10)), got[0], url)
        f = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(
            columns=sec.FATO_SEC_COLUNAS)
        arquivos = _arquivamentos_sec(arq, cik10, as_of, date(as_of.year - anos, 1, 1), http_get)
        # O Companyfacts pode omitir o arquivo mais recente. Só o XBRL do próprio documento
        # fornece os números; a data do arquivamento não é tratada como balanço novo.
        alvo = sec.documentos_pendentes(arquivos, f, as_of)
        classes_capa = sec.documentos_classes_sec(arquivos, cik10)
        if not classes_capa.empty:
            alvo = pd.concat([alvo, classes_capa], ignore_index=True).drop_duplicates("accn")
        for r in alvo.to_dict("records"):
            prefixo = f"SEC/filings/{cik10}/{r['accn']}/"
            indice_url = sec.url_filing(cik10, r["accn"]) + "index.json"
            indice = arq.obter(prefixo + "index.json", "SEC", indice_url,
                               lambda u=indice_url: _sec_get(u, http_get, None, SEC_LIMITER),
                               ate=as_of, max_idade_dias=3650.0,
                               validar=lambda c, r=r: sec.instancia_sec(c, cik10, r) and None)
            instancia_url = sec.instancia_sec(indice[1], cik10, r) if indice else None
            # XML extraído antes do HTML inline: recursos oficiais distintos, não espelhos
            # inventados. Em ambos o parser confere entidade, período, unidade e contexto.
            urls = ([instancia_url] if instancia_url else []) + [r["url"]]
            completo = False
            for documento_url in urls:
                nome = documento_url.rsplit("/", 1)[-1]
                documento = arq.obter(prefixo + nome, "SEC", documento_url,
                                      lambda u=documento_url: _sec_get(u, http_get, None, SEC_LIMITER),
                                      ate=as_of, max_idade_dias=3650.0,
                                      validar=lambda c, r=r: sec.companyfacts_documento(c, cik10, r) and None)
                if documento:
                    cf = sec.companyfacts_documento(documento[1], cik10, r)
                    direto = sec.fatos_sec(cf)
                    add_sec(direto, documento[0], documento_url)
                    # HTTP 200 e fatos da capa não provam que o documento contém o balanço.
                    nucleo = direto[direto["period_end"] <= r["period_end"]]
                    if sec.documentos_pendentes(pd.DataFrame([r]), nucleo, as_of).empty:
                        completo = True
                        break
            if completo:
                continue
            try:
                ri = sec.documento_ri(cik10, r)
                if ri:
                    extensao = "zip" if ri.get("membro_zip") else "xml"
                    espelho = arq.obter(f"SEC/RI/{cik10}/{r['accn']}/documento.{extensao}",
                                        "SEC", ri["url"], _baixar(http_get, ri["url"]),
                                        ate=as_of, max_idade_dias=3650.0,
                                        validar=lambda c, r=r, ri=ri: sec.companyfacts_ri(c, cik10, r, ri) and None)
                    if espelho:
                        cf = sec.companyfacts_ri(espelho[1], cik10, r, ri)
                        fonte_url = ri["url"] + ("#" + ri["membro_zip"] if ri.get("membro_zip") else "")
                        espelhado = sec.fatos_sec(cf)
                        add_sec(espelhado, espelho[0], fonte_url)
                        nucleo = espelhado[espelhado["period_end"] <= r["period_end"]]
                        if sec.documentos_pendentes(pd.DataFrame([r]), nucleo, as_of).empty:
                            continue
            except ValueError as exc:
                arq.falhas.append(f"SEC CIK {cik10} ({iid}): espelho RI recusado ({exc})")
            arq.falhas.append(f"SEC CIK {cik10} ({iid}): {r['form']} {r['accn']} "
                              "não forneceu núcleo financeiro na data-base; dado anterior preservado")
        if not partes:
            return None
        f = pd.concat(partes, ignore_index=True)
        lucro = f[f["item"].isin(["lucro_liquido", "lucro_liquido_controladores"])
                  & f["anual"].astype(bool) & (f["received_date"] <= pd.Timestamp(as_of))]
        if lucro["period_end"].nunique() < 2:
            # XBRL insuficiente (registro recente ou taxonomia própria): Yahoo assume
            arq.falhas.append(f"SEC CIK {cik10} ({iid}): menos de 2 exercícios de lucro no "
                              "XBRL; demonstrações do Yahoo Finance usadas")
            return None
        return f

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        res = list(ex.map(um_sec, sorted(cik_de.items())))
    for (iid, cik10), f in zip(sorted(cik_de.items()), res, strict=True):
        if f is None:
            continue
        ent_iss.setdefault(cik10, []).append(iid)
        frames.append(f)
        cobertos.add(iid)

    # ---- RI: documentos oficiais sem cobertura CVM/SEC suficiente. O catálogo não
    # contém valores; a estrutura e os bytes são conferidos antes da leitura do PDF.
    for iid in pedidos:
        if iid in cobertos:
            continue
        partes_ri = []
        for doc_ri in ri_pdf.documentos_ri(iid, as_of):
            url_ri = doc_ri["url"]
            got_ri = arq.obter(f"RI/demonstrativos/{iid}/{doc_ri['documento']}", "RI", url_ri,
                               _baixar(http_get, url_ri), ate=as_of, max_idade_dias=3650.0,
                               validar=lambda c, d=doc_ri: ri_pdf.fatos_pdf_ri(c, d, as_of=as_of))
            if got_ri:
                f_ri = ri_pdf.fatos_pdf_ri(got_ri[1], doc_ri, as_of=as_of)
                if not f_ri.empty:
                    f_ri["fonte"] = "RI"
                    f_ri["sha256"] = got_ri[0].sha256
                    f_ri["data_coleta"] = pd.Timestamp(got_ri[0].data_coleta)
                    partes_ri.append(f_ri)
        if partes_ri:
            f_ri = pd.concat(partes_ri, ignore_index=True)
            ent_iss.setdefault("RI:" + iid, []).append(iid)
            frames.append(f_ri)
            cobertos.add(iid)

    # ---- Yahoo (sem CVM/SEC; e complemento trimestral)
    alvo_yh = [i for i in pedidos if i not in cobertos]
    compl = [i for i in pedidos if i in cobertos and i not in cnpj_de] if complementar_yahoo \
        else []

    def um_yh(iid: str) -> pd.DataFrame | None:
        t = _linha_yahoo(uni, iid)
        got = _parte_yahoo(arq, t, "demonstracoes", as_of, yf_factory, instantaneo=False)
        if got is None:
            return None
        info = _parte_yahoo(arq, t, "info", as_of, yf_factory, instantaneo=False)
        inf = (info[1].get("info") or {}) if info else {}
        moeda = inf.get("financialCurrency")
        if moeda:
            nota = f"moeda {moeda}: Yahoo Finance info (sha256 {info[0].sha256})"
        elif str(uni.lines.loc[t, "line_type"]) == "LOCAL":
            # sem moeda das demonstrações no Yahoo: a da cotação local (emissor doméstico)
            moeda = str(uni.lines.loc[t, "currency"])
            nota = f"moeda {moeda}: moeda de cotação da linha local (Yahoo sem moeda do balanço)"
        else:
            nota = "moeda das demonstrações não informada pelo Yahoo Finance"
        fin = str(uni.issuers.loc[iid, "gics_sector"]) == "Financials"
        f = yh.fatos_yahoo(got[1], data_coleta=data_local(got[0].data_coleta), financeira=fin,
                           moeda=moeda, nota=nota)
        if f.empty:
            return None
        f["entidade"] = f"YAHOO:{t}"
        f["fonte"] = "YAHOO"
        f["sha256"] = got[0].sha256
        f["data_coleta"] = pd.Timestamp(got[0].data_coleta)
        return f

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        res_y = list(ex.map(um_yh, alvo_yh + compl))
    compl_frames: dict[str, pd.DataFrame] = {}
    for iid, f in zip(alvo_yh + compl, res_y, strict=True):
        if f is None:
            continue
        ent = str(f["entidade"].iloc[0])
        if iid in alvo_yh:
            ent_iss.setdefault(ent, []).append(iid)
            frames.append(f)
        else:
            compl_frames[iid] = f

    def vazio() -> pd.DataFrame:
        out = pd.DataFrame(columns=DEMONSTRATIVOS_COLUNAS)
        out.attrs = {"as_of": as_of.isoformat(), "falhas": list(arq.falhas),
                     "desconhecidos": desconhecidos, "qa": qa, "moeda_trocada": {}}
        return out

    if not frames and not compl_frames:
        return vazio()
    fatos = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    coleta = (fatos.groupby("sha256")["data_coleta"].first().to_dict()
              if not fatos.empty else {})
    sel = selecionar_pit(fatos.drop(columns=["data_coleta"], errors="ignore"), as_of) \
        if not fatos.empty else pd.DataFrame()
    trocas: dict[str, dict] = {}
    partes = []
    if not sel.empty:
        for alerta in sel.attrs.get("incompatibilidades_fluxos", []):
            for iid in ent_iss.get(alerta["entidade"], []):
                qa.append(f"{iid}: {alerta['motivo']}")
        for ent, t in (sel.attrs.get("moeda_trocada") or {}).items():
            for iid in ent_iss.get(ent, []):
                trocas[iid] = t
                qa.append(f"{iid}: moeda de apresentação {', '.join(t['anteriores'])} → "
                          f"{t['moeda']} (documentos desde {t['desde']}); períodos só "
                          "publicados na moeda anterior ficam fora")
        sel = sel[sel["entidade"].isin(ent_iss)].copy()
        sel["issuer_id"] = sel["entidade"].map(ent_iss)
        sel = sel.explode("issuer_id")
        partes.append(sel)
    for iid, f in compl_frames.items():
        s2 = selecionar_pit(f.drop(columns=["data_coleta"]), as_of)
        for alerta in s2.attrs.get("incompatibilidades_fluxos", []):
            qa.append(f"{iid}: {alerta['motivo']}")
        coleta.update(f.groupby("sha256")["data_coleta"].first().to_dict())
        if s2.empty or not partes:
            continue
        base = partes[0][partes[0]["issuer_id"] == iid]
        if base.empty:
            continue
        s2 = _complemento(base, s2.assign(issuer_id=iid), iid, qa)
        if s2 is not None and not s2.empty:
            partes.append(s2)
    if not partes:
        return vazio()
    out = pd.concat(partes, ignore_index=True)
    out = _qa_magnitude(out, qa)
    out = _qa_acoes(out, qa)
    out = _refazer_derivados(out)
    # Bancos (intermediação financeira): o fluxo de caixa operacional inclui captações e
    # aplicações ⇒ FCF, EBITDA e EBIT calculados não têm significado econômico e não são
    # publicados (ausentes, nunca zero).
    bancos = set(out.loc[out["item"].isin(["margem_financeira", "carteira_credito",
                                           "despesa_pdd"]), "issuer_id"])
    calc = out["nota"].fillna("").str.startswith("calculado")
    out = out[~(out["issuer_id"].isin(bancos) & (out["item"].isin(["fcf", "ebitda"])
                                                 | (calc & (out["item"] == "ebit"))))].copy()
    out["data_coleta"] = out["sha256"].map(coleta)
    out["data_publicacao"] = pd.to_datetime(out["data_publicacao"]).dt.date
    out["period_end"] = pd.to_datetime(out["period_end"])
    out = out[DEMONSTRATIVOS_COLUNAS].sort_values(
        ["issuer_id", "item", "freq", "period_end"], kind="stable").reset_index(drop=True)
    out.attrs = {"as_of": as_of.isoformat(), "falhas": list(arq.falhas),
                 "desconhecidos": desconhecidos, "qa": qa, "moeda_trocada": trocas}
    return out


# ----------------------------------------------------------------- conferência (QA)

NOTA_CONFERENCIA = "conferência:"
ITENS_POSITIVOS = ("receita", "ativo_total", "d_a", "capex", "caixa", "aplicacoes_cp",
                   "divida_bruta", "arrendamentos", "carteira_credito")
FATOR_ESCALA = 200.0
"""Razão a partir da qual um valor é tratado como erro de escala (≈ 1.000×: milhares × unidades)."""
FATOR_SALTO = 10.0
"""Saltos de 10× entre períodos consecutivos são registrados para conferência (sem descarte)."""
FAIXA_ACOES = (0.5, 2.0)
"""Contagem de ações fora de 0,5–2× da anterior sem confirmação pela seguinte ⇒ ausente."""
RAZAO_MIN_EMITIDAS = 0.9
"""Emitidas < 90% das em circulação no mesmo período ⇒ bases distintas (ações × units/CPOs);
diferenças menores são de data (contagem da capa × fim do exercício)."""
FAIXA_PL_POR_ACAO = (0.01, 1000.0)
"""PL por ação (R$) plausível para conferir a unidade das ações da CVM sem LPA utilizável: uma
contagem em milhares tratada como unidades daria PL por ação 1.000× maior (nenhuma ação da B3
tem PL por ação acima de R$ 1.000)."""
FAIXA_COMPLEMENTO = (0.8, 1.25)
"""Magnitude Yahoo ÷ fonte oficial nos períodos comuns (receita, ativo, PL)."""


def _doc_id(doc: pd.Series) -> pd.Series:
    return doc.fillna("").str.replace(r" \(ações: unidade .*\)$", "", regex=True)


def _qa_escala_documentos(f: pd.DataFrame, ent_iss: dict[str, list[str]],
                          qa: list[str]) -> pd.DataFrame:
    """CVM: documento cujo ativo total destoa ≥ 200× da mediana dos documentos da companhia
    (ex.: ``ESCALA_MOEDA`` "UNIDADE" com valores em milhares) ⇒ valores monetários do
    documento descartados (ausentes; trimestres e TTM que dependem dele também)."""
    at = f[f["item"] == "ativo_total"]
    if at.empty:
        return f
    at = at.assign(_doc=_doc_id(at["documento"]))
    at = at.sort_values("received_date").drop_duplicates(["entidade", "_doc"], keep="last")
    ruins: set[tuple[str, str]] = set()
    for ent, g in at.groupby("entidade"):
        v = g["value"].abs()
        v = v[v > 0]
        if len(v) < 3:
            continue
        med = float(v.median())
        r = v / med
        for i in r.index[(r >= FATOR_ESCALA) | (r <= 1.0 / FATOR_ESCALA)]:
            doc = str(g.at[i, "_doc"])
            ruins.add((str(ent), doc))
            for iid in ent_iss.get(str(ent), []):
                qa.append(f"{iid}: {doc}: ativo total {float(g.at[i, 'value']):.6g} vs mediana "
                          f"{med:.6g} dos demais documentos — escala incompatível; valores do "
                          "documento descartados")
    if not ruins:
        return f
    chave = list(zip(f["entidade"].astype(str), _doc_id(f["documento"]), strict=True))
    fora = pd.Series([k in ruins for k in chave], index=f.index) & f["currency"].notna()
    return f[~fora].reset_index(drop=True)


def _marcar(out: pd.DataFrame, idx, motivo: str) -> None:
    out.loc[idx, "value"] = np.nan
    atual = out.loc[idx, "nota"].fillna("")
    out.loc[idx, "nota"] = [f"{NOTA_CONFERENCIA} {motivo}" + (f"; {a}" if a else "")
                            for a in atual]


def _qa_magnitude(out: pd.DataFrame, qa: list[str]) -> pd.DataFrame:
    """Valores ≥ 200× fora dos períodos vizinhos (vizinhos coerentes entre si) ⇒ ausentes com
    motivo; saltos ≥ 10× entre períodos consecutivos ⇒ alerta em ``qa``."""
    out = out.copy()
    alvo = out[out["item"].isin(ITENS_POSITIVOS) & out["freq"].isin(["A", "Q", "TTM"])
               & out["value"].notna() & (out["value"] > 0)]
    for (iid, item, freq), g in alvo.groupby(["issuer_id", "item", "freq"], sort=False):
        g = g.sort_values("period_end")
        if len(g) < 2:
            continue
        v = g["value"].to_numpy(dtype=float)
        idx = list(g.index)
        datas = [pd.Timestamp(d).date() for d in g["period_end"]]

        def longe(a: float, b: float) -> bool:
            r = a / b
            return r >= FATOR_ESCALA or r <= 1.0 / FATOR_ESCALA

        for k in range(len(v)):
            viz = [j for j in (k - 1, k + 1) if 0 <= j < len(v)]
            if len(v) >= 3 and all(longe(v[k], v[j]) for j in viz):
                if len(viz) == 2:
                    coerentes = not longe(v[viz[0]], v[viz[1]])
                else:  # ponta da série: o vizinho precisa ser coerente com o seguinte dele
                    j = viz[0]
                    j2 = j + (j - k)
                    coerentes = 0 <= j2 < len(v) and not longe(v[j], v[j2])
                if coerentes:
                    _marcar(out, [idx[k]], f"{item} {freq} {datas[k]} ≥ {FATOR_ESCALA:g}× fora "
                            "dos períodos vizinhos (erro de escala na fonte)")
                    qa.append(f"{iid}: {item} {freq} {datas[k]} {v[k]:.6g} descartado: escala "
                              "incompatível com os períodos vizinhos")
                    continue
            if k > 0:
                r = v[k] / v[k - 1]
                if r >= FATOR_SALTO or r <= 1.0 / FATOR_SALTO:
                    qa.append(f"{iid}: {item} {freq} salto de {r:.3g}× entre {datas[k - 1]} e "
                              f"{datas[k]} — conferir")
    return out


_ACOES = ("acoes_em_circulacao", "acoes_emitidas", "acoes_tesouraria")


def _qa_acoes(out: pd.DataFrame, qa: list[str]) -> pd.DataFrame:
    """Contagens de ações: unidade não conferida, emitidas < em circulação e quebras de
    continuidade (fora de 0,5–2× da anterior sem confirmação pela maioria das seguintes) ⇒
    ausentes com motivo (nunca um palpite de unidade)."""
    out = out.copy()
    sh = out[out["item"].isin(_ACOES) & out["value"].notna()]
    if sh.empty:
        return out
    # 1) unidade não conferida na CVM pelo LPA nem por continuidade: conferida pelo PL por ação
    #    do mesmo documento; sem PL ou fora da faixa ⇒ ausente
    sem_unid = sh["documento"].fillna("").str.contains(r"unidade (?:na|divergente)\)$")
    if sem_unid.any():
        pl = out[(out["item"] == "patrimonio_liquido") & out["value"].notna()]
        pl = pl.drop_duplicates(["issuer_id", "freq", "period_end"]).set_index(
            ["issuer_id", "freq", "period_end"])["value"]
        circ = sh[sh["item"] == "acoes_em_circulacao"].set_index(
            ["issuer_id", "freq", "period_end"])["value"]
        circ = circ[~circ.index.duplicated()]
        lo_pl, hi_pl = FAIXA_PL_POR_ACAO
        ok_pl: list[bool] = []
        for r in sh[sem_unid].itertuples():
            k = (r.issuer_id, r.freq, r.period_end)
            n_acoes = circ.get(k)
            v_pl = pl.get(k)
            ok_pl.append(n_acoes is not None and v_pl is not None and n_acoes > 0
                         and lo_pl <= abs(float(v_pl)) / float(n_acoes) <= hi_pl)
        ok_pl_s = pd.Series(ok_pl, index=sh.index[sem_unid])
        conferidas = ok_pl_s.index[ok_pl_s]
        if len(conferidas):
            atual = out.loc[conferidas, "nota"].fillna("")
            out.loc[conferidas, "nota"] = [
                "unidade das ações conferida pelo PL por ação" + (f"; {a}" if a else "")
                for a in atual]
        sem = ok_pl_s.index[~ok_pl_s]
        if len(sem):
            _marcar(out, sem, "unidade das ações não conferida (LPA, PL por ação e documento "
                    "anterior)")
            for iid, g in sh.loc[sem].groupby("issuer_id"):
                qa.append(f"{iid}: contagem de ações sem unidade conferida em "
                          f"{sorted({str(pd.Timestamp(d).date()) for d in g['period_end']})}")
    sh = out[out["item"].isin(_ACOES) & out["value"].notna()]
    lo, hi = FAIXA_ACOES
    for iid, g in sh.groupby("issuer_id", sort=False):
        # 2) emitidas < em circulação no mesmo período: bases distintas (ações × units)
        w = g.pivot_table(index=["freq", "period_end"], columns="item", values="value",
                          aggfunc="first")
        if {"acoes_emitidas", "acoes_em_circulacao"} <= set(w.columns):
            inc = w[w["acoes_emitidas"] < RAZAO_MIN_EMITIDAS * w["acoes_em_circulacao"]]
            for fq, pe in inc.index:
                m = g.index[(g["freq"] == fq) & (g["period_end"] == pe)]
                _marcar(out, m, "ações emitidas < em circulação (bases distintas)")
                qa.append(f"{iid}: ações emitidas < em circulação em "
                          f"{pd.Timestamp(pe).date()} ({fq})")
        # 3) continuidade da contagem em circulação (uma por data-base)
        c = out.loc[g.index]
        c = c[(c["item"] == "acoes_em_circulacao") & c["value"].notna()]
        if c.empty:
            continue
        serie = (c.assign(_q=(c["freq"] == "Q").astype(int)).sort_values(["period_end", "_q"])
                 .drop_duplicates("period_end", keep="last"))
        datas = list(serie["period_end"])
        v = serie["value"].to_numpy(dtype=float)
        ref: float | None = None
        for k in range(len(v)):
            ok_ref = ref is not None and lo <= v[k] / ref <= hi
            if ref is None or ok_ref:
                if ref is None and k + 2 < len(v) and not (lo <= v[k] / v[k + 1] <= hi) \
                        and lo <= v[k + 1] / v[k + 2] <= hi:
                    pass  # primeira contagem destoa das duas seguintes (coerentes): fora
                else:
                    ref = v[k]
                    continue
            else:
                seguintes = v[k + 1:]
                if len(seguintes) and sum(lo <= x / v[k] <= hi for x in seguintes) * 2 > \
                        len(seguintes):
                    ref = v[k]  # novo patamar confirmado (desdobramento/grupamento)
                    continue
            m = out.index[(out["issuer_id"] == iid) & out["item"].isin(_ACOES)
                          & (out["period_end"] == datas[k])]
            _marcar(out, m, f"contagem fora de {lo:g}–{hi:g}× da anterior sem confirmação "
                    "pela seguinte")
            qa.append(f"{iid}: ações em circulação {v[k]:.6g} em {pd.Timestamp(datas[k]).date()} "
                      f"fora de {lo:g}–{hi:g}× de {ref if ref is not None else float('nan'):.6g}"
                      " — ausente")
    return out


def _refazer_derivados(out: pd.DataFrame) -> pd.DataFrame:
    """Itens calculados refeitos por emissor sobre o conjunto final (fonte oficial +
    complemento, depois da conferência): nunca um derivado de componentes que mudaram."""
    calc = out["nota"].fillna("").str.startswith("calculado")
    base = out[~calc]
    if base.empty:
        return base.reset_index(drop=True)
    novos = derivados(base.drop(columns=["entidade"], errors="ignore")
                      .rename(columns={"issuer_id": "entidade"}))
    if novos.empty:
        return base.reset_index(drop=True)
    novos = novos.rename(columns={"entidade": "issuer_id"})
    novos["escala"] = 1
    return pd.concat([base, novos], ignore_index=True)


def _coerente(base: pd.DataFrame, s2: pd.DataFrame) -> tuple[bool, str]:
    """Magnitude do Yahoo frente à fonte oficial (receita, ativo total, PL)."""
    itens = ["receita", "ativo_total", "patrimonio_liquido"]
    b = base[base["item"].isin(itens) & base["value"].notna()]
    y = s2[s2["item"].isin(itens) & s2["value"].notna()]
    m = b.merge(y, on=["freq", "period_end", "item"], suffixes=("_b", "_y"))
    m = m[m["value_b"] != 0]
    lo, hi = FAIXA_COMPLEMENTO
    if not m.empty:
        r = float((m["value_y"] / m["value_b"]).median())
        return lo <= r <= hi, f"razão mediana Yahoo/oficial {r:.4g} em {len(m)} período(s) comum(ns)"
    ba = b[b["freq"] == "A"]
    ya = y[y["freq"] == "A"]
    rs = []
    for it in ("ativo_total", "receita"):
        bi, yi = ba[ba["item"] == it], ya[ya["item"] == it]
        if bi.empty or yi.empty:
            continue
        ub = bi.sort_values("period_end").iloc[-1]
        d = (yi["period_end"] - ub["period_end"]).abs()
        if d.min() > pd.Timedelta(days=400) or ub["value"] == 0:
            continue
        rs.append(float(yi.loc[d.idxmin(), "value"]) / float(ub["value"]))
    if not rs:
        return True, "sem período comparável"
    r = float(np.median(rs))
    return 1 / 3 <= r <= 3, f"razão Yahoo/oficial {r:.4g} em períodos próximos"


def _complemento(base: pd.DataFrame, s2: pd.DataFrame, iid: str,
                 qa: list[str]) -> pd.DataFrame | None:
    """Linhas do Yahoo que completam a fonte oficial de ``iid`` (ver :func:`demonstrativos`)."""
    moedas = set(base["currency"].dropna())
    # só itens reportados: os calculados são refeitos sobre o conjunto final
    s2 = s2[~s2["nota"].fillna("").str.startswith("calculado")]
    if (base["item"] == "acoes_em_circulacao").any():
        # contagens oficiais (ações) × Yahoo (units, CPOs, ADS): bases diferentes
        s2 = s2[~s2["item"].isin(_ACOES)]
    acoes = s2["item"].isin(_ACOES)
    if "ARS" in moedas:
        # IAS 29: valores monetários do Yahoo em outra unidade de medida; contagens de ações
        # (sem moeda) continuam válidas
        qa.append(f"{iid}: complemento Yahoo só com contagens de ações — ARS (IAS 29): unidade "
                  "de medida da fonte oficial difere da do Yahoo")
        s2 = s2[acoes]
    else:
        ok, motivo = _coerente(base, s2)
        if not ok:
            qa.append(f"{iid}: complemento Yahoo rejeitado — magnitude incompatível com a fonte "
                      f"oficial ({motivo})")
            return None
        s2 = s2[s2["currency"].isin(moedas) | (s2["currency"].isna() & acoes)]
    fluxo = s2["item"].isin(FLUXOS_PIT)
    k_fluxo = set(zip(base["freq"], base["period_end"], base["item"], strict=True))
    k_saldo = set(zip(base["period_end"], base["item"], strict=True))
    novos = [((f_, p_, i_) not in k_fluxo) if fl else ((p_, i_) not in k_saldo)
             for f_, p_, i_, fl in zip(s2["freq"], s2["period_end"], s2["item"], fluxo,
                                       strict=True)]
    s2 = s2[novos]
    if s2.empty:
        return None
    s2 = _plausivel_frente_base(base, s2, iid, qa)
    if s2.empty:
        return None
    nota = "complemento Yahoo Finance (item ou período ausente na fonte oficial)"
    return s2.assign(nota=[nota + (f"; {n}" if isinstance(n, str) and n else "")
                           for n in s2["nota"]])


def _plausivel_frente_base(base: pd.DataFrame, s2: pd.DataFrame, iid: str,
                           qa: list[str]) -> pd.DataFrame:
    """Linha do complemento fora de 0,1–10× do mesmo item na fonte oficial (período mais
    próximo; trimestre comparado a 1/4 do anual) ⇒ descartada (ex.: D&A parcial)."""
    fora = []
    for i, r in s2[s2["item"].isin(ITENS_POSITIVOS) & (s2["value"] > 0)].iterrows():
        b = base[(base["item"] == r["item"]) & base["value"].notna() & (base["value"] > 0)]
        if b.empty:
            continue
        mesma = b[b["freq"] == r["freq"]]
        fator = 1.0
        if mesma.empty:
            mesma = b[b["freq"] == "A"]
            fator = 0.25 if r["freq"] == "Q" else 1.0
        if mesma.empty:
            continue
        d = (mesma["period_end"] - r["period_end"]).abs()
        if d.min() > pd.Timedelta(days=730):
            continue
        ref = float(mesma.loc[d.idxmin(), "value"]) * fator
        razao = float(r["value"]) / ref
        if razao < 0.1 or razao > 10.0:
            fora.append(i)
            qa.append(f"{iid}: complemento Yahoo {r['item']} {r['freq']} "
                      f"{pd.Timestamp(r['period_end']).date()} descartado ({razao:.3g}× a fonte "
                      "oficial)")
    return s2.drop(index=fora)


# ======================================================================
# consenso, dividendos, free float (Yahoo / CVM FRE)
# ======================================================================

def consenso_publico(tickers: Sequence[str], as_of: date, *, offline: bool = False,
                     root: Path | None = None,
                     yf_factory: Callable[[str], Any] | None = None) -> pd.DataFrame:
    """Consenso público (Yahoo Finance) por ticker, como coletado até ``as_of``.

    Retrato sem data própria: com ``as_of`` no passado só vale o que foi arquivado até lá
    (coletar hoje seria look-ahead). Campos ausentes ⇒ ``NaN``; o rótulo de exibição é
    "consenso público Yahoo Finance" (``NOTA_CONSENSO``).
    """
    arq = _arquivo(root, offline)
    lista = [str(t) for t in dict.fromkeys(tickers)]
    sim = _simulado(arq, "consenso", as_of, CONSENSO_COLUNAS)
    if sim is not None:
        sim["data_coleta"] = pd.to_datetime(sim["data_coleta"])
        return sim[sim["ticker"].isin(lista)].reset_index(drop=True)

    def um(t: str) -> dict:
        info = _parte_yahoo(arq, t, "info", as_of, yf_factory, instantaneo=True)
        est = _parte_yahoo(arq, t, "estimativas", as_of, yf_factory, instantaneo=True)
        c = yh.consenso_de(info[1] if info else None, est[1] if est else None)
        reg = est[0] if est else (info[0] if info else None)
        reg_info = info[0] if info else None
        return {"ticker": t, **c, "fonte": "YAHOO" if reg else None,
                "data_coleta": _data_coleta(reg), "url": yh.URL_QUOTE.format(t=t) + "/analysis",
                "sha256": reg.sha256 if reg else None,
                "sha256_info": reg_info.sha256 if reg_info else None,
                "data_coleta_info": _data_coleta(reg_info)}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        rows = list(ex.map(um, lista))
    out = pd.DataFrame(rows, columns=CONSENSO_COLUNAS) if rows else pd.DataFrame(
        columns=CONSENSO_COLUNAS)
    out.attrs = {"as_of": as_of.isoformat(), "falhas": list(arq.falhas), "nota": NOTA_CONSENSO}
    return out


def _moeda_ticker(t: str, uni: Universe | None) -> str:
    if uni is not None and t in uni.lines.index:
        return str(uni.lines.loc[t, "currency"])
    for suf, m in _MOEDA_SUFIXO.items():
        if t.upper().endswith(suf):
            return m
    return "USD"


def dividendos(tickers: Sequence[str], as_of: date, *, offline: bool = False,
               root: Path | None = None, universe: Universe | None = None,
               yf_factory: Callable[[str], Any] | None = None) -> pd.DataFrame:
    """Proventos por data-ex ``<= as_of`` (valor por ação na moeda de cotação da linha)."""
    arq = _arquivo(root, offline)
    try:
        uni = _universo(universe)
    except (FileNotFoundError, ValueError):
        uni = None
    lista = [str(t) for t in dict.fromkeys(tickers)]
    sim = _simulado(arq, "dividendos", as_of, DIVIDENDOS_COLUNAS)
    if sim is not None:
        sim["data_ex"] = pd.to_datetime(sim["data_ex"]).dt.date
        return sim[sim["ticker"].isin(lista) & (sim["data_ex"] <= as_of)].reset_index(drop=True)

    def um(t: str) -> list[dict]:
        got = _parte_yahoo(arq, t, "dividendos", as_of, yf_factory, instantaneo=False)
        if got is None:
            return []
        reg, doc = got
        moeda = _moeda_ticker(t, uni)
        return [{"ticker": t, "data_ex": d, "valor_por_acao": v, "moeda": moeda,
                 "fonte": "YAHOO", "url": yh.URL_QUOTE.format(t=t) + "/history",
                 "sha256": reg.sha256}
                for d, v in yh.dividendos_de(doc) if d <= as_of]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        rows = [r for lst in ex.map(um, lista) for r in lst]
    out = pd.DataFrame(rows, columns=DIVIDENDOS_COLUNAS)
    out = out.sort_values(["ticker", "data_ex"], kind="stable").reset_index(drop=True)
    out.attrs = {"as_of": as_of.isoformat(), "falhas": list(arq.falhas)}
    return out


def free_float(issuer_ids: Sequence[str], as_of: date, *, offline: bool = False,
               root: Path | None = None, universe: Universe | None = None,
               http_get: HttpGet | None = None,
               yf_factory: Callable[[str], Any] | None = None) -> pd.DataFrame:
    """Free float (fração 0–1) por emissor: CVM FRE (ações em circulação, item 15.3) para o
    Brasil; Yahoo ``floatShares/sharesOutstanding`` (mesma linha) nos demais casos.

    Sem dado confiável ⇒ ``NaN`` com ``detalhe`` (quem veta decide: fail-closed abaixo do corte
    de capitalização, conforme a regra de risco)."""
    arq = _arquivo(root, offline)
    uni = _universo(universe)
    pedidos = [str(i) for i in dict.fromkeys(issuer_ids) if str(i) in uni.issuers.index]
    sim = _simulado(arq, "free_float", as_of, FLOAT_COLUNAS)
    if sim is not None:
        sim["data_ref"] = pd.to_datetime(sim["data_ref"]).dt.date
        return sim[sim["issuer_id"].isin(pedidos)].reset_index(drop=True)
    sm = mestre_publico(as_of, universe=uni, http_get=http_get, arquivo=arq)
    rows: dict[str, dict] = {}
    cnpj_de = {i: str(sm.loc[i, "cnpj"]) for i in pedidos
               if i in sm.index and isinstance(sm.loc[i, "cnpj"], str) and sm.loc[i, "cnpj"]}
    if cnpj_de:
        frames = []
        for ano in (as_of.year, as_of.year - 1):
            url = f"{cvm.CVM_DOC_BASE_URL}/FRE/DADOS/fre_cia_aberta_{ano}.zip"
            got = arq.obter(f"CVM/FRE/fre_cia_aberta_{ano}.zip", "CVM", url,
                            _baixar(http_get, url), ate=as_of, max_idade_dias=7.0,
                            validar=_validar_zip)
            if got is None:
                continue
            f = cvm.free_float_fre(got[1], ano, set(cnpj_de.values()))
            f["sha256"] = got[0].sha256
            frames.append(f)
        if frames:
            fre = pd.concat(frames, ignore_index=True)
            fre = fre[fre["data_publicacao"] <= pd.Timestamp(as_of)]
            fre = fre.sort_values(["cnpj", "data_ref", "versao", "data_publicacao"])
            fre = fre.drop_duplicates("cnpj", keep="last").set_index("cnpj")
            for iid, c in cnpj_de.items():
                if c in fre.index:
                    r = fre.loc[c]
                    rows[iid] = {"issuer_id": iid, "free_float_pct": float(r["free_float_pct"]),
                                 "fonte": "CVM", "data_ref": pd.Timestamp(r["data_ref"]).date(),
                                 "url": r["url"], "sha256": r["sha256"],
                                 "detalhe": (f"FRE {pd.Timestamp(r['data_ref']).year} v"
                                             f"{int(r['versao'])}: ações em circulação ÷ total")}
    resto = [i for i in pedidos if i not in rows]

    def um(iid: str) -> dict:
        t = _linha_yahoo(uni, iid)
        got = _parte_yahoo(arq, t, "info", as_of, yf_factory, instantaneo=True)
        if got is None:
            return {"issuer_id": iid, "free_float_pct": math.nan, "fonte": None,
                    "data_ref": None, "url": None, "sha256": None, "detalhe": "sem_dados"}
        v, det = yh.float_de(got[1])
        return {"issuer_id": iid, "free_float_pct": v, "fonte": "YAHOO",
                "data_ref": data_local(got[0].data_coleta), "url": yh.URL_QUOTE.format(t=t),
                "sha256": got[0].sha256, "detalhe": f"{t}: {det}"}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for r in ex.map(um, resto):
            rows[r["issuer_id"]] = r
    out = pd.DataFrame([rows[i] for i in pedidos if i in rows], columns=FLOAT_COLUNAS)
    out.attrs = {"as_of": as_of.isoformat(), "falhas": list(arq.falhas)}
    return out


# ======================================================================
# ETFs
# ======================================================================

MAPA_ETF_PADRAO = Path("configs/cdp/cobertura/etf_mapa.csv")
FALHAS_ETF: dict[str, list[str]] = {}
"""Motivo da última chamada de :func:`composicao_etf` por ETF (sobretudo quando devolve
``None``): sem fonte configurada, carteira não coletada até a data, resposta inválida, falha de
rede com versão arquivada, carteira com data posterior à referência."""


def _falha_etf(e: str, arq: Arquivo | None, motivo: str | None = None) -> None:
    FALHAS_ETF[e] = [*(arq.falhas if arq is not None else []), *([motivo] if motivo else [])]


def composicao_etf(etf: str, as_of: date, *, offline: bool = False, root: Path | None = None,
                   universe: Universe | None = None, http_get: HttpGet | None = None,
                   mapa: Path | None = None) -> pd.DataFrame | None:
    """Carteira pública do ETF (``etfm.COLUNAS``) com data de referência ``<= as_of``.

    ``None`` quando o ETF não tem fonte pública configurada ou o arquivo não está disponível —
    o motivo fica em ``FALHAS_ETF[etf]``. ``attrs['falhas']`` registra coletas que falharam
    (ex.: versão arquivada usada por falha de rede).
    """
    e = etf.upper()
    try:
        fonte, tipo = etfm.carteira(etf)
    except KeyError:
        _falha_etf(e, None, "ETF sem fonte pública de carteira configurada")
        return None
    arq = _arquivo(root, offline)
    sim = _simulado(arq, f"etf_{e}", as_of, etfm.COLUNAS)
    if sim is not None:
        sim["data_ref"] = pd.to_datetime(sim["data_ref"]).dt.date
        sim.attrs.update({"etf": e, **etfm.resumo_mapeamento(sim)})
        _falha_etf(e, arq)
        return sim
    got = None
    if tipo == "ishares":
        url = etfm.url_ishares(e)
        got = arq.obter(f"ISHARES/{e}/{e}_holdings.csv", "ISHARES", url,
                        _baixar(http_get, url), ate=as_of, max_idade_dias=1.0, instantaneo=True,
                        validar=etfm.validar_csv_ishares)
        leitor = etfm.ler_ishares
    elif tipo == "globalx":
        leitor = etfm.ler_globalx
        for k in range(0, 8):
            d = as_of - timedelta(days=k)
            if d.weekday() >= 5:
                continue
            url = etfm.url_globalx(e, d)
            got = arq.obter(f"GLOBALX/{e}/{e.lower()}_full-holdings_{d:%Y%m%d}.csv", "GLOBALX",
                            url, _baixar(http_get, url), ate=as_of, max_idade_dias=3650.0,
                            validar=_validar_globalx)
            if got is not None:
                break
    else:
        indice = etfm.B3_INDICE[e]
        url = etfm.url_b3(indice)
        got = arq.obter(f"B3/carteira_teorica/{indice}.json", "B3", url, _baixar(http_get, url),
                        ate=as_of, max_idade_dias=1.0, instantaneo=True,
                        validar=etfm.validar_b3)
        leitor = etfm.ler_b3
    if got is None:
        _falha_etf(e, arq, f"carteira de {e} não disponível no arquivo até {as_of.isoformat()}")
        return None
    reg, conteudo = got
    try:
        df, data_ref = leitor(conteudo)
    except (ValueError, StopIteration, KeyError) as exc:
        logger.warning("Carteira %s ilegível: %s", e, exc)
        _falha_etf(e, arq, f"carteira de {e} ilegível ({exc})")
        return None
    if data_ref is not None and data_ref > as_of:
        _falha_etf(e, arq, f"carteira de {e} com data {data_ref.isoformat()} posterior a "
                   f"{as_of.isoformat()}")
        return None
    try:
        uni = _universo(universe)
        linhas = uni.lines
    except (FileNotFoundError, ValueError):
        linhas = None
    m = etfm.ler_mapa(mapa or MAPA_ETF_PADRAO)
    df = etfm.mapear(df, e, fonte, linhas, m)
    df["fonte"] = fonte
    df["url"] = reg.url
    df["data_ref"] = data_ref or data_local(reg.data_coleta)
    df["sha256"] = reg.sha256
    out = df.reindex(columns=etfm.COLUNAS).reset_index(drop=True)
    out.attrs = {"etf": e, "as_of": as_of.isoformat(), "data_coleta":
                 reg.data_coleta.isoformat(), "falhas": list(arq.falhas),
                 **etfm.resumo_mapeamento(out)}
    _falha_etf(e, arq)
    return out


# ======================================================================
# Taxas
# ======================================================================

def taxas_publicas(as_of: date, *, offline: bool = False, root: Path | None = None,
                   http_get: HttpGet | None = None, anos: int = 3) -> pd.DataFrame:
    """Séries públicas de taxas e expectativas com ``data <= as_of`` (``TAXAS_COLUNAS``)."""
    arq = _arquivo(root, offline)
    ini, fim = as_of - timedelta(days=365 * anos), as_of
    sim = _simulado(arq, "taxas", as_of, TAXAS_COLUNAS)
    if sim is not None:
        sim["data"] = pd.to_datetime(sim["data"]).dt.date
        return sim[sim["data"] <= as_of].sort_values(["serie", "data"]).reset_index(drop=True)
    frames: list[pd.DataFrame] = []

    def add(got, df: pd.DataFrame, fonte: str) -> None:
        if got is None or df is None or df.empty:
            return
        df = df[df["data"] <= pd.Timestamp(as_of)].copy()
        df["fonte"] = fonte
        df["url"] = got[0].url
        df["sha256"] = got[0].sha256
        frames.append(df)

    url = tx.url_fred("DGS10", ini, fim)
    got = arq.obter("FRED/DGS10/DGS10.csv", "FRED", url, _baixar(http_get, url),
                    ate=as_of, max_idade_dias=1.0, validar=tx.validar_fred)
    add(got, tx.ler_fred(got[1], "USD_10Y") if got else None, "FRED")
    for serie, code in tx.SGS.items():
        url = tx.url_sgs(code, ini, fim)
        got = arq.obter(f"BCB/SGS/sgs{code}.json", "BCB", url,
                        _baixar(http_get, url), ate=as_of, max_idade_dias=1.0,
                        validar=tx.validar_json_lista)
        add(got, tx.ler_sgs(got[1], serie, as_of) if got else None, "BCB")
    desde = as_of - timedelta(days=400)
    for ind, nome in tx.FOCUS.items():
        url = tx.url_focus(ind, desde)
        got = arq.obter(f"BCB/focus/focus_{nome}.json", "BCB", url,
                        _baixar(http_get, url), ate=as_of, max_idade_dias=1.0,
                        validar=tx.validar_focus)
        add(got, tx.ler_focus(got[1], as_of) if got else None, "BCB")
    token = os.environ.get("BANXICO_TOKEN", "").strip()

    def banxico(serie: str, got) -> None:
        if got is None:
            return
        try:
            df = tx.ler_banxico(got[1], serie, as_of)
        except (ValueError, TypeError, AttributeError) as exc:
            arq.falhas.append(f"Banxico {serie}: resposta ilegível ({type(exc).__name__})")
            return
        add(got, df, "BANXICO")

    if token and not offline:
        for serie, sid in tx.BANXICO.items():
            # o token pessoal vai no cabeçalho ``Bmx-Token``: nunca no endereço (que fica no
            # índice do arquivo e nas mensagens de falha)
            url = tx.URL_BANXICO.format(sid=sid, ini=ini.isoformat(), fim=fim.isoformat())
            got = arq.obter(f"BANXICO/{sid}/{sid}.json", "BANXICO", url,
                            _baixar(http_get, url, {"Bmx-Token": token}), ate=as_of,
                            max_idade_dias=1.0, validar=_validar_banxico)
            banxico(serie, got)
    elif offline:
        for serie, sid in tx.BANXICO.items():
            reg = arq.buscar(f"BANXICO/{sid}/{sid}.json", as_of)
            if reg is not None:
                banxico(serie, (reg, arq.ler(reg)))
    if not frames:
        out = pd.DataFrame(columns=TAXAS_COLUNAS)
    else:
        out = pd.concat(frames, ignore_index=True)
        out["data"] = pd.to_datetime(out["data"]).dt.date
        out = out[TAXAS_COLUNAS].sort_values(["serie", "data"], kind="stable")
        out = out.drop_duplicates(["serie", "data"], keep="last").reset_index(drop=True)
    out.attrs = {"as_of": as_of.isoformat(), "falhas": list(arq.falhas),
                 "limitacoes": ([] if token else
                                ["Banxico (SIE) exige token pessoal: séries do México fora."])}
    return out


# ======================================================================
# Eventos corporativos
# ======================================================================

_PRIO_EVENTO = {"CVM_CAL": 0, "CVM": 1, "SEC": 1, "YAHOO": 2, "IMPUTADA": 3}


def _indice_zip(conteudo: bytes, doc: str, ano: int) -> pd.DataFrame:
    import io
    import zipfile

    from .security_master import read_cvm_csv
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        nome = next((n for n in zf.namelist()
                     if n.lower().endswith(f"{doc.lower()}_cia_aberta_{ano}.csv")), None)
        if nome is None:
            return pd.DataFrame(columns=["CNPJ_CIA", "DT_REFER", "VERSAO", "DT_RECEB"])
        return read_cvm_csv(zf.read(nome))


def _fim_trimestre(d: date) -> date:
    """Último dia do trimestre civil que contém ``d``."""
    m = ((d.month - 1) // 3) * 3 + 3
    prox = date(d.year + (m == 12), 1 if m == 12 else m + 1, 1)
    return prox - timedelta(days=1)


def eventos_corporativos(issuer_ids: Sequence[str], desde: date, ate: date, *,
                         offline: bool = False, root: Path | None = None,
                         universe: Universe | None = None, http_get: HttpGet | None = None,
                         yf_factory: Callable[[str], Any] | None = None,
                         as_of: date | None = None, ler_calendarios: bool = True,
                         ) -> pd.DataFrame:
    """Eventos (``resultado``, ``teleconferencia``, ``assembleia``, ``fato_relevante``,
    ``dividendo``) entre ``desde`` e ``ate``.

    Brasil: datas efetivas de resultado (``DT_RECEB`` da 1ª versão do ITR/DFP), o
    "Calendário de Eventos Corporativos" (IPE, PDF padronizado), editais de assembleia e fatos
    relevantes. Demais: Yahoo (calendário, ``earnings_dates`` e data-ex). Resultado trimestral
    sem data conhecida ⇒ **estimada** (``estimada = True``): mesma data do trimestre do ano
    anterior + 52 semanas, janela ± 7 dias — nunca "sem evento" — salvo se já há data
    conhecida (efetiva, calendário ou Yahoo, em qualquer janela) a até 30 dias; trimestre sem
    nenhuma data conhecida (efetiva ou anunciada) ⇒ fim do trimestre + 50 dias, ± 14 dias.
    ``as_of`` (padrão: hoje em São Paulo) limita o que se sabia (arquivo). Os calendários da CVM
    são lidos para todos os anos de ``desde`` a ``ate`` (entregues no próprio ano ou no
    anterior).
    """
    ref = as_of or (_hoje() if not offline else ate)
    arq = _arquivo(root, offline)
    uni = _universo(universe)
    pedidos = [str(i) for i in dict.fromkeys(issuer_ids) if str(i) in uni.issuers.index]
    sim = _simulado(arq, "eventos", ref, EVENTOS_COLUNAS)
    if sim is not None:
        for c in ("data", "janela_inicio", "janela_fim"):
            sim[c] = pd.to_datetime(sim[c]).dt.date
        return sim[sim["issuer_id"].isin(pedidos) & (sim["data"] >= desde)
                   & (sim["data"] <= ate)].reset_index(drop=True)
    sm = mestre_publico(ref, universe=uni, http_get=http_get, arquivo=arq)
    ev: list[dict] = []
    cnpj_de = {i: str(sm.loc[i, "cnpj"]) for i in pedidos
               if i in sm.index and isinstance(sm.loc[i, "cnpj"], str) and sm.loc[i, "cnpj"]}
    iss_de: dict[str, list[str]] = {}
    for i, c in cnpj_de.items():
        iss_de.setdefault(c, []).append(i)
    historico: dict[str, list[date]] = {}
    # todas as datas de resultado conhecidas (efetivas, calendário da CVM, Yahoo), em qualquer
    # janela: base da deduplicação das estimadas
    conhecidas: dict[str, set[date]] = {}

    def conhece(iid: str, d: date) -> None:
        conhecidas.setdefault(iid, set()).add(d)

    def add(iid: str, d: date, tipo: str, estimada: bool, fonte: str, url: str | None,
            documento: str, prio: str, janela: int = 0) -> None:
        ev.append({"issuer_id": iid, "data": d, "tipo": tipo, "estimada": bool(estimada),
                   "fonte": fonte, "url": url, "documento": documento,
                   "janela_inicio": d - timedelta(days=janela) if janela else d,
                   "janela_fim": d + timedelta(days=janela) if janela else d, "_prio": prio})

    if cnpj_de:
        # datas efetivas de resultado (índices ITR/DFP) — inclui o ano anterior para imputar
        idx, docs = [], []
        for doc in ("ITR", "DFP"):
            for ano in range(desde.year - 2, min(ate.year, ref.year) + 1):
                got = _obter_cvm(arq, doc, ano, ref, http_get)
                if got is None:
                    continue
                idx.append(_indice_zip(got[1], doc, ano))
                docs.append(doc)
        datas = cvm.datas_resultado_cvm(idx, docs)
        datas = datas[datas["cnpj"].isin(iss_de) & (datas["data"] <= pd.Timestamp(ref))]
        for r in datas.itertuples(index=False):
            d = pd.Timestamp(r.data).date()
            for iid in iss_de[r.cnpj]:
                historico.setdefault(iid, []).append(d)
                conhece(iid, d)
                if desde <= d <= ate:
                    add(iid, d, "resultado", False, "CVM", r.url, f"CVM {r.documento}", "CVM")
        # IPE: assembleias, fatos relevantes, calendários
        ipes = []
        # o IPE é particionado pelo ano de ENTREGA: o calendário do ano Y costuma ser entregue
        # em dezembro de Y−1 ⇒ inclui o ano anterior ao início da janela
        for ano in range(min(desde.year, ref.year) - 1, min(ate.year, ref.year) + 1):
            url = f"{cvm.CVM_DOC_BASE_URL}/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
            got = arq.obter(f"CVM/IPE/ipe_cia_aberta_{ano}.zip", "CVM", url,
                            _baixar(http_get, url), ate=ref, max_idade_dias=1.0,
                            validar=_validar_zip)
            if got is not None:
                ipes.append(cvm.ler_ipe(got[1], ano, set(iss_de)))
        ipe = pd.concat(ipes, ignore_index=True) if ipes else pd.DataFrame(
            columns=cvm.IPE_COLUNAS)
        ipe = ipe[ipe["data_entrega"] <= pd.Timestamp(ref)]
        for r in cvm.eventos_ipe(ipe).itertuples(index=False):
            d = pd.Timestamp(r.data).date()
            if desde <= d <= ate:
                for iid in iss_de.get(r.cnpj, []):
                    add(iid, d, r.tipo, False, "CVM", r.url, r.documento, "CVM")
        if ler_calendarios:
            cal = cvm.calendarios_ipe(ipe)
            cal = cal[cal["ano"].between(desde.year, ate.year)]

            def um_cal(r) -> list[tuple[str, dict, str]]:
                dig = re.sub(r"\D", "", r.cnpj)
                chave = f"CVM/IPE_calendario/{dig}_{int(r.ano)}_v{int(r.versao)}.pdf"
                got = arq.obter(chave, "CVM", r.url, _baixar_pdf(http_get, r.url), ate=ref,
                                max_idade_dias=3650.0, validar=_validar_pdf)
                if got is None:
                    return []
                try:
                    evs = cvm.eventos_do_calendario(celulas(got[1]))
                except (PdfIlegivel, ValueError, KeyError) as exc:
                    arq.falhas.append(f"calendário {r.cnpj} {r.ano}: ilegível ({exc})")
                    return []
                return [(r.cnpj, e, r.url) for e in evs]

            with ThreadPoolExecutor(max_workers=2) as ex:
                for lst in ex.map(um_cal, list(cal.itertuples(index=False))):
                    for c, e, url in lst:
                        for iid in iss_de.get(c, []):
                            if e["tipo"] == "resultado":
                                conhece(iid, e["data"])
                            if desde <= e["data"] <= ate:
                                add(iid, e["data"], e["tipo"], False, "CVM", url,
                                    f"CVM calendário de eventos corporativos ({e['rotulo']})",
                                    "CVM_CAL")

    # SEC: datas oficiais de arquivamento de demonstrações. Um 6-K sem XBRL pode tratar
    # de tráfego, dividendos ou governança: nunca o rotula automaticamente como resultado.
    for iid in pedidos:
        cik = format_cik(sm.loc[iid, "cik"]) if iid in sm.index else None
        if not cik or iid in cnpj_de:
            continue
        arquivos = _arquivamentos_sec(arq, cik, ref, date(desde.year - 2, 1, 1), http_get)
        financeiros = arquivos[arquivos["period_end"].notna()
                               & (arquivos["period_end"] <= pd.Timestamp(ref))
                               & (arquivos["form"].isin(sec.ANUAIS) | arquivos["xbrl"])]
        for r in financeiros.itertuples(index=False):
            d = r.filed.date()
            historico.setdefault(iid, []).append(d)
            conhece(iid, d)
            if desde <= d <= ate:
                add(iid, d, "resultado", False, "SEC", r.url,
                    f"SEC arquivamento {r.form} {r.accn} (referência {r.period_end.date()})", "SEC")

    # Yahoo (todos; complementa o Brasil)
    def um_yh(iid: str) -> list[dict]:
        t = _linha_yahoo(uni, iid)
        info = _parte_yahoo(arq, t, "info", ref, yf_factory, instantaneo=True)
        cal = _parte_yahoo(arq, t, "calendario", ref, yf_factory, instantaneo=True)
        if info is None and cal is None:
            return []
        url = yh.URL_QUOTE.format(t=t)
        return [{**e, "iid": iid, "url": url}
                for e in yh.eventos_de(info[1] if info else None, cal[1] if cal else None, ref)]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for lst in ex.map(um_yh, pedidos):
            for e in lst:
                d = e["data"]
                if e["tipo"] == "resultado":
                    conhece(e["iid"], d)
                    if d <= ref and not e["estimada"]:
                        historico.setdefault(e["iid"], []).append(d)
                if desde <= d <= ate:
                    add(e["iid"], d, e["tipo"], e["estimada"], "YAHOO", e["url"],
                        e["rotulo"], "YAHOO", 7 if e["estimada"] else 0)

    # imputação: resultado do mesmo trimestre do ano anterior + 52 semanas (± 7 dias), salvo
    # se já há data conhecida (efetiva, calendário ou Yahoo — em qualquer janela) a até 30 dias
    for iid in pedidos:
        for d0 in sorted(set(historico.get(iid, []))):
            cand = d0 + timedelta(days=364)
            if not (desde <= cand <= ate) or cand < ref - timedelta(days=7):
                continue
            if any(abs((k - cand).days) <= 30 for k in conhecidas.get(iid, set())):
                continue
            add(iid, cand, "resultado", True, "CVM" if iid in cnpj_de else "YAHOO", None,
                f"estimada: mesmo trimestre de {d0.year} (resultado em {d0.isoformat()}) "
                f"+ 52 semanas", "IMPUTADA", 7)
            conhece(iid, cand)
    # trimestre sem nenhuma data conhecida (efetiva ou anunciada): fim do trimestre + 50 dias
    # (prazo típico), ± 14 dias — nunca para quem já divulgou o trimestre
    if ate >= ref:
        for iid in pedidos:
            fim_tri = _fim_trimestre(ref - timedelta(days=50))
            cand = fim_tri + timedelta(days=50)
            while cand < ref:
                fim_tri = _fim_trimestre(fim_tri + timedelta(days=1))
                cand = fim_tri + timedelta(days=50)
            if any(fim_tri < d <= fim_tri + timedelta(days=100)
                   for d in conhecidas.get(iid, set())):
                continue
            if desde <= cand <= ate:
                motivo = ("sem data conhecida para o trimestre" if historico.get(iid)
                          else "sem histórico de datas")
                add(iid, cand, "resultado", True, "CVM" if iid in cnpj_de else "YAHOO", None,
                    f"estimada: trimestre encerrado em {fim_tri.isoformat()} + 50 dias "
                    f"({motivo})", "IMPUTADA", 14)
    if not ev:
        out = pd.DataFrame(columns=EVENTOS_COLUNAS)
    else:
        out = pd.DataFrame(ev)
        out["_p"] = out["_prio"].map(_PRIO_EVENTO)
        out = out.sort_values(["issuer_id", "data", "tipo", "_p"], kind="stable")
        out = out.drop_duplicates(["issuer_id", "data", "tipo"], keep="first")
        out = out[EVENTOS_COLUNAS].reset_index(drop=True)
    out.attrs = {"desde": desde.isoformat(), "ate": ate.isoformat(), "as_of": ref.isoformat(),
                 "falhas": list(arq.falhas)}
    return out


# ======================================================================
# Cobertura (relatório de suficiência dos dados)
# ======================================================================

ITENS_NUCLEO = ("receita", "ebit", "lucro_liquido", "patrimonio_liquido")


def resumo_cobertura(dem: pd.DataFrame, uni: Universe, *, consenso: pd.DataFrame | None = None,
                     divs: pd.DataFrame | None = None, eventos: pd.DataFrame | None = None,
                     ) -> pd.DataFrame:
    """Contagem por país: emissores com ≥ 3 exercícios anuais de cada item núcleo, com
    ``cfo``/``capex``, com ``d_a``, e (se dados) consenso, proventos e eventos."""
    paises = uni.issuers["country"]
    if not dem.empty:  # linhas de conferência (valor ausente) não contam como cobertura
        dem = dem[dem["value"].notna()]
    a = dem[dem["freq"] == "A"] if not dem.empty else dem

    def n_anos(item: str) -> pd.Series:
        if a.empty:
            return pd.Series(dtype=float)
        return a[a["item"] == item].groupby("issuer_id")["period_end"].nunique()

    nucleo = pd.concat({i: n_anos(i) for i in ITENS_NUCLEO}, axis=1).reindex(
        index=paises.index, columns=list(ITENS_NUCLEO)).fillna(0)
    bancos = uni.issuers["gics_sector"].reindex(paises.index) == "Financials"
    ok_geral = (nucleo >= 3).all(axis=1)
    ok_banco = (nucleo[["lucro_liquido", "patrimonio_liquido"]] >= 3).all(axis=1)
    ok_nucleo = ok_geral | (bancos & ok_banco)

    def tem(it: str) -> pd.Series:
        if dem.empty:
            return pd.Series(False, index=paises.index)
        return dem[dem["item"] == it].groupby("issuer_id").size().reindex(
            paises.index).fillna(0) > 0

    linhas = {
        "emissores": paises.groupby(paises).size(),
        "nucleo_3a": ok_nucleo.groupby(paises).sum(),
        "cfo_capex": (tem("cfo") & tem("capex")).groupby(paises).sum(),
        "d_a": tem("d_a").groupby(paises).sum(),
        "fonte_cvm": _por_fonte(dem, "CVM", paises), "fonte_sec": _por_fonte(dem, "SEC", paises),
        "fonte_yahoo": _por_fonte(dem, "YAHOO", paises),
    }
    if consenso is not None and not consenso.empty:
        c = consenso.copy()
        c["issuer_id"] = c["ticker"].map(uni.lines["issuer_id"])
        ok = c[c["eps_fy1"].notna() | c["alvo_medio"].notna()].groupby("issuer_id").size()
        linhas["consenso"] = (ok.reindex(paises.index).fillna(0) > 0).groupby(paises).sum()
    if divs is not None and not divs.empty:
        d = divs.copy()
        d["issuer_id"] = d["ticker"].map(uni.lines["issuer_id"])
        ok = d.groupby("issuer_id").size()
        linhas["dividendos"] = (ok.reindex(paises.index).fillna(0) > 0).groupby(paises).sum()
    if eventos is not None and not eventos.empty:
        r = eventos[eventos["tipo"] == "resultado"]
        ok = r.groupby("issuer_id").size()
        linhas["evento_resultado"] = (ok.reindex(paises.index).fillna(0) > 0).groupby(
            paises).sum()
        okr = r[~r["estimada"].astype(bool)].groupby("issuer_id").size()
        linhas["evento_confirmado"] = (okr.reindex(paises.index).fillna(0) > 0).groupby(
            paises).sum()
    out = pd.DataFrame(linhas).fillna(0).astype(int)
    out.loc["TOTAL"] = out.sum()
    return out


def _por_fonte(dem: pd.DataFrame, fonte: str, paises: pd.Series) -> pd.Series:
    if dem.empty:
        return pd.Series(0, index=paises.unique())
    ids = set(dem.loc[dem["fonte"] == fonte, "issuer_id"])
    return paises.index.to_series().isin(ids).groupby(paises).sum()


def proveniencias(df: pd.DataFrame) -> list[Proveniencia]:
    """Proveniências distintas de um quadro com ``fonte, url, documento, data_publicacao,
    data_coleta, sha256`` (colunas ausentes ⇒ ``None``)."""
    cols = ["fonte", "url", "documento", "data_publicacao", "data_coleta", "sha256"]
    if df is None or df.empty:
        return []
    sub = df.reindex(columns=cols).drop_duplicates()
    out = []
    for r in sub.itertuples(index=False):
        dp = r.data_publicacao
        dc = r.data_coleta
        out.append(Proveniencia(
            fonte=str(r.fonte), url=None if pd.isna(r.url) else str(r.url),
            documento=None if pd.isna(r.documento) else str(r.documento),
            data_publicacao=None if dp is None or pd.isna(dp) else pd.Timestamp(dp).date(),
            data_coleta=None if dc is None or pd.isna(dc) else pd.Timestamp(dc).to_pydatetime(),
            sha256=None if pd.isna(r.sha256) else str(r.sha256)))
    return out


__all__ = [
    "CANONICAL_ITEMS", "CONSENSO_COLUNAS", "DEMONSTRATIVOS_COLUNAS", "DIVIDENDOS_COLUNAS",
    "EVENTOS_COLUNAS", "FLOAT_COLUNAS", "FONTES_PUBLICAS", "NOTA_CONSENSO", "Proveniencia",
    "TAXAS_COLUNAS", "composicao_etf", "consenso_publico", "demonstrativos", "dividendos",
    "eventos_corporativos", "free_float", "mestre_publico", "proveniencias", "resumo_cobertura",
    "taxas_publicas",
]
