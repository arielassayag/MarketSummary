"""Fundamentos POINT-IN-TIME: CVM (Brasil) e SEC EDGAR (ADRs e emissores listados nos EUA).

Objetivo: sinais de *value*/*quality* honestos no backtest e robustos ao vivo. Os campos de
múltiplos do Yahoo não são confiáveis para a LatAm (docs/research/06_fontes_dados_ferramentas.md,
§7); aqui tudo sai de demonstrações oficiais com a data em que ficaram PÚBLICAS.

Regras point-in-time
--------------------
- **CVM** (``dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{DFP,ITR}/DADOS/``): cada documento tem
  ``VERSAO`` e ``DT_RECEB`` no índice. ``available_date = DT_RECEB + 1 dia útil``. Os CSVs anuais
  publicados trazem apenas os valores da ÚLTIMA versão de cada documento; por isso o valor
  publicado vale a partir da data de recebimento DESSA versão (política estrita: uma
  reapresentação nunca é antecipada para a data do original). Versões vistas em downloads
  anteriores são preservadas no cache extraído (``data/cache/cvm/extracted``), de modo que ao
  vivo o histórico de versões se acumula.
- **SEC** (``companyfacts``): cada fato traz ``filed``; ``available_date = filed + 1 dia útil``.
  Comparativos reapresentados em arquivos posteriores viram novas versões com a data do novo
  arquivo.
- Seleção em ``as_of``: só linhas com ``available_date <= as_of``; por (emissor, métrica), o maior
  ``period_end`` e, nele, a publicação mais recente (``available_date``, depois ``version``).

Fluxos (DRE) e TTM
------------------
O ITR traz a DRE acumulada no exercício (YTD) e, no 2º/3º trimestres, também o trimestre
isolado. Trimestre discreto = trimestre isolado reportado (3 meses) quando existe; senão
``YTD(t) − YTD(t−3m)`` do mesmo exercício (mesmo ``DT_INI_EXERC``); Q4 = DFP anual − 9M do ITR.
TTM = valor anual (12 meses) quando o período fecha o exercício; senão soma dos 4 últimos
trimestres discretos conhecidos na data. Exercícios fora do ano civil (ex.: abril–março) são
tratados pelas próprias datas de início/fim.

Plano de contas (verificado nos arquivos de 2017–2026)
------------------------------------------------------
- Receita: ``3.01`` (em bancos é a receita de intermediação financeira).
- EBIT: conta de nível 2 "Resultado Antes do Resultado Financeiro e dos Tributos" (``3.05`` no
  layout comercial). Não se aplica a bancos/seguradoras ⇒ ausente.
- Lucro líquido: conta de nível 2 "Lucro/Prejuízo (Líquido) Consolidado do Período"
  (``3.11`` comercial, ``3.09``/``3.11`` bancos, ``3.13`` seguradoras) e, quando existe, sua
  filha "Atribuído a Sócios da Empresa Controladora" (``3.11.01``) — preferida.
- Patrimônio líquido: conta de nível 2 "Patrimônio Líquido Consolidado" (``2.03``; ``2.07``/
  ``2.08`` em financeiras) atribuído ao controlador (total − não controladores ``2.03.09``).
- Ativo total ``1``; caixa ``1.01.01 + 1.01.02``; dívida bruta ``2.01.04 + 2.02.01`` (só no
  layout comercial — em financeiras caixa/dívida não têm o mesmo significado ⇒ ausentes).
- Ações: ``composicao_capital`` (``QT_ACAO_TOTAL_CAP_INTEGR − QT_ACAO_TOTAL_TESOURO``), publicado
  pela CVM apenas a partir de 2020 (antes disso ⇒ ausente).
- Preferência ``con`` (consolidado) com *fallback* ``ind`` (individual) por documento/demonstração.

Moeda e preços
--------------
Os valores ficam na moeda das demonstrações (BRL na CVM; a unidade do fato na SEC). Em
:func:`pit_ratios` o chamador passa preços **por ação local, na moeda das demonstrações**
(linhas locais: preço da ação; units: preço ÷ ações por unit; ADRs: preço USD ÷ razão ADR ×
câmbio). :func:`local_equivalent_prices` faz essa conversão a partir do security master.
Ausências permanecem ``NaN`` — nunca viram zero.
"""

from __future__ import annotations

import calendar
import hashlib
import io
import json
import logging
import math
import re
import time
import zipfile
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..universe import Universe
from .security_master import (
    CVM_DOC_BASE_URL,
    DEFAULT_USER_AGENT,
    HttpError,
    HttpGet,
    RateLimiter,
    _sec_get,
    build_line_master,
    build_security_master,
    default_http_get,
    fetch_cvm_fca,
    fetch_sec_company_tickers,
    format_cik,
    normalize_text,
    read_cvm_csv,
)

logger = logging.getLogger(__name__)

# ==========================================================
# Esquemas e constantes
# ==========================================================

PIT_COLUMNS = [
    "issuer_id", "metric", "period_end", "available_date", "value", "currency", "source",
    "version",
]
PIT_METRICS = (
    "net_income_ttm", "revenue_ttm", "ebit_ttm", "equity", "total_assets", "cash",
    "gross_debt", "shares_outstanding",
)
FLOW_METRICS = ("net_income", "revenue", "ebit")
"""Fluxos brutos (DRE); viram ``<métrica>_ttm`` na tabela PIT."""
STOCK_METRICS = ("equity", "total_assets", "cash", "gross_debt", "shares_outstanding")
"""Saldos (balanço/capital) usados como estão, na data de referência."""
RATIO_COLUMNS = [
    "earnings_yield", "book_to_price", "roe", "ebit_margin", "net_debt_to_equity",
    "asset_turnover",
]
RAW_FACT_COLUMNS = [
    "entity", "metric", "period_start", "period_end", "value", "currency", "received_date",
    "version", "source",
]
"""Fatos brutos antes do TTM: ``entity`` = CNPJ (CVM) ou CIK (SEC); ``received_date`` sem lag."""

DEFAULT_CACHE_ROOT = Path("data/cache")
DEFAULT_PIT_PATH = Path("data/fundamentals/pit_fundamentals.parquet")
PIT_SNAPSHOT_FILENAME = "fundamentals_pit.parquet"
"""Nome do arquivo quando o integrador gravar a tabela PIT dentro de um snapshot."""

DEFAULT_LAG_BDAYS = 1
DEFAULT_MAX_AGE_DAYS = 540
"""Idade máxima (``as_of − period_end``) para um fundamento ainda ser usado (≈ 18 meses)."""
DEFAULT_MAX_PRICE_AGE_DAYS = 7

CVM_PARSER_VERSION = "1"
CVM_DOCS = ("ITR", "DFP")
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ACCEPTED_FORMS = frozenset({
    "10-K", "10-K/A", "10-KT", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A",
    "6-K", "6-K/A",
})

_QUARTER_DAYS = (80, 100)
_ANNUAL_DAYS = (350, 380)
_END_TOLERANCE_DAYS = 10

PIT_NOTICE = (
    "Fundamentos point-in-time de fontes oficiais (CVM dados abertos e SEC EDGAR). "
    "available_date = recebimento/arquivamento + 1 dia útil; reapresentações valem a partir "
    "da própria data de recebimento."
)


# ==========================================================
# Utilidades de datas
# ==========================================================

def add_business_days(d: pd.Series | pd.Timestamp | date, n: int) -> pd.Series | pd.Timestamp:
    """Soma ``n`` dias úteis (seg–sex). ``n = 0`` mantém a data (fins de semana inclusive)."""
    if isinstance(d, pd.Series):
        ts = pd.to_datetime(d)
        if n == 0:
            return ts
        out = ts + pd.offsets.BDay(n)
        return out.where(ts.notna())
    ts = pd.Timestamp(d)
    return ts if n == 0 else ts + pd.offsets.BDay(n)


def _months_back(d: date, months: int) -> date:
    """Mesma posição no mês ``months`` meses antes (fim de mês ⇒ fim de mês)."""
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12
        y -= 1
    last = calendar.monthrange(y, m)[1]
    if d.day == calendar.monthrange(d.year, d.month)[1]:
        return date(y, m, last)
    return date(y, m, min(d.day, last))


def _to_date(x) -> date:
    return pd.Timestamp(x).date()


# ==========================================================
# Motor de trimestres discretos e TTM
# ==========================================================

def _match_end(by_end: Mapping[date, Mapping[date, float]], target: date) -> date | None:
    if target in by_end:
        return target
    best: date | None = None
    best_gap = _END_TOLERANCE_DAYS + 1
    for e in by_end:
        gap = abs((e - target).days)
        if gap < best_gap:
            best, best_gap = e, gap
    return best


def _quarter_value(by_end: Mapping[date, Mapping[date, float]], end: date) -> float:
    flows = by_end.get(end)
    if not flows:
        return math.nan
    direct = [(abs((end - s).days + 1 - 91), v) for s, v in flows.items()
              if _QUARTER_DAYS[0] <= (end - s).days + 1 <= _QUARTER_DAYS[1]]
    if direct:
        return min(direct, key=lambda t: t[0])[1]
    for s in sorted(flows):
        dur = (end - s).days + 1
        if dur <= _QUARTER_DAYS[1] or dur > _ANNUAL_DAYS[1]:
            continue
        prev_end = _match_end(by_end, _months_back(end, 3))
        if prev_end is None:
            continue
        prev = by_end[prev_end].get(s)
        if prev is None or not math.isfinite(prev):
            continue
        return flows[s] - prev
    return math.nan


def _ttm_value(by_end: Mapping[date, Mapping[date, float]], end: date) -> tuple[float, str]:
    flows = by_end.get(end)
    if not flows:
        return math.nan, ""
    annual = [(abs((end - s).days + 1 - 365), v) for s, v in flows.items()
              if _ANNUAL_DAYS[0] <= (end - s).days + 1 <= _ANNUAL_DAYS[1]]
    if annual:
        return min(annual, key=lambda t: t[0])[1], "12m"
    total = 0.0
    for k in range(4):
        e_k = end if k == 0 else _match_end(by_end, _months_back(end, 3 * k))
        if e_k is None:
            return math.nan, ""
        q = _quarter_value(by_end, e_k)
        if not math.isfinite(q):
            return math.nan, ""
        total += q
    return total, "4q"


def _known_state(flows: pd.DataFrame, as_of: date | pd.Timestamp | None,
                 date_col: str) -> dict[date, dict[date, float]]:
    df = flows
    if as_of is not None:
        df = df[pd.to_datetime(df[date_col]) <= pd.Timestamp(as_of)]
    df = df.sort_values([date_col, "version"])
    by_end: dict[date, dict[date, float]] = {}
    for s, e, v in zip(df["period_start"], df["period_end"], df["value"], strict=True):
        if pd.isna(s) or pd.isna(e) or pd.isna(v):
            continue
        by_end.setdefault(_to_date(e), {})[_to_date(s)] = float(v)
    return by_end


def discrete_quarters(flows: pd.DataFrame, as_of: date | None = None,
                      date_col: str = "available_date") -> pd.Series:
    """Trimestres discretos conhecidos em ``as_of`` a partir de fluxos YTD/trimestrais/anuais.

    ``flows``: colunas ``period_start``, ``period_end``, ``value``, ``version`` e ``date_col``
    (uma única entidade/métrica). Retorna série indexada por ``period_end`` (``Timestamp``);
    trimestres não deriváveis ficam ``NaN``.
    """
    by_end = _known_state(flows, as_of, date_col)
    ends = sorted(by_end)
    vals = [_quarter_value(by_end, e) for e in ends]
    return pd.Series(vals, index=pd.DatetimeIndex(ends, name="period_end"), dtype=float,
                     name="quarter")


def ttm_at(flows: pd.DataFrame, as_of: date | None = None,
           date_col: str = "available_date") -> pd.Series:
    """TTM por ``period_end`` conhecido em ``as_of`` (anual direto ou soma de 4 trimestres)."""
    by_end = _known_state(flows, as_of, date_col)
    ends = sorted(by_end)
    vals = [_ttm_value(by_end, e)[0] for e in ends]
    return pd.Series(vals, index=pd.DatetimeIndex(ends, name="period_end"), dtype=float,
                     name="ttm")


def _ttm_history(flows: pd.DataFrame) -> list[dict]:
    """Histórico PIT do TTM de uma entidade/métrica: uma linha por mudança publicada.

    ``flows`` precisa de ``available_date`` (com lag), ``version``, ``source``, ``currency``.
    Em cada data de publicação recalcula apenas os ``period_end`` afetados (até ~13 meses
    após o fim de cada fluxo alterado) e emite quando o TTM é novo ou mudou.
    """
    df = flows.dropna(subset=["period_start", "period_end", "value", "available_date"])
    if df.empty:
        return []
    df = df.sort_values(["available_date", "version"])
    by_end: dict[date, dict[date, float]] = {}
    anchor: dict[date, tuple[int, int, str, str | None]] = {}
    last: dict[date, float] = {}
    out: list[dict] = []
    for d, batch in df.groupby("available_date", sort=True):
        changed: set[date] = set()
        for s, e, v, ver, src, ccy in zip(batch["period_start"], batch["period_end"],
                                          batch["value"], batch["version"], batch["source"],
                                          batch["currency"], strict=True):
            s_d, e_d = _to_date(s), _to_date(e)
            by_end.setdefault(e_d, {})[s_d] = float(v)
            dur = (e_d - s_d).days
            prev = anchor.get(e_d)
            if prev is None or dur >= prev[0]:
                anchor[e_d] = (dur, int(ver), str(src), ccy if isinstance(ccy, str) else None)
            changed.add(e_d)
        horizon = 400
        cands = sorted(E for E in by_end
                       if any(0 <= (E - c).days <= horizon for c in changed))
        for E in cands:
            val, how = _ttm_value(by_end, E)
            if not math.isfinite(val):
                continue
            if E in last and math.isclose(last[E], val, rel_tol=1e-12, abs_tol=1e-9):
                continue
            last[E] = val
            _, ver, src, ccy = anchor[E]
            out.append({"period_end": pd.Timestamp(E), "available_date": pd.Timestamp(d),
                        "value": val, "currency": ccy, "source": f"{src}|ttm:{how}",
                        "version": ver})
    return out


# ==========================================================
# CVM: download, leitura e extração
# ==========================================================

def cvm_zip_name(doc: str, year: int) -> str:
    doc = doc.upper()
    if doc not in CVM_DOCS:
        raise ValueError(f"Documento CVM inválido: {doc!r} (use ITR ou DFP).")
    return f"{doc.lower()}_cia_aberta_{int(year)}.zip"


def cvm_zip_url(doc: str, year: int) -> str:
    return f"{CVM_DOC_BASE_URL}/{doc.upper()}/DADOS/{cvm_zip_name(doc, year)}"


def fetch_cvm_zip(doc: str, year: int, *, cache_dir: str | Path = DEFAULT_CACHE_ROOT / "cvm",
                  http_get: HttpGet | None = None, max_age_days: float = 7.0,
                  refresh: bool = False, today: date | None = None) -> Path | None:
    """Garante o ZIP ``{doc}_cia_aberta_{year}.zip`` no cache e devolve o caminho.

    Anos ``>= hoje.ano − 1`` são rebaixados quando o cache tem mais de ``max_age_days``
    (a CVM republica semanalmente); anos antigos só com ``refresh=True``. 404 ⇒ ``None``
    (ano não publicado). Falha de rede com cache existente ⇒ usa o cache (com aviso).
    """
    path = Path(cache_dir) / cvm_zip_name(doc, year)
    today = today or date.today()
    if path.exists() and not refresh:
        recent = int(year) >= today.year - 1
        age_days = (time.time() - path.stat().st_mtime) / 86400.0
        if not recent or age_days <= max_age_days:
            return path
    getter = http_get or default_http_get
    try:
        data = getter(cvm_zip_url(doc, year), {"User-Agent": DEFAULT_USER_AGENT})
    except HttpError as exc:
        if exc.status == 404:
            return path if path.exists() else None
        if path.exists():
            logger.warning("Falha ao atualizar %s (%s); usando cache.", path.name, exc)
            return path
        raise
    if not zipfile.is_zipfile(io.BytesIO(data)):
        if path.exists():
            logger.warning("Conteúdo inválido para %s; usando cache.", path.name)
            return path
        raise ValueError(f"Resposta da CVM não é um ZIP válido: {cvm_zip_url(doc, year)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


_STMT_USECOLS = {
    "DRE": ["CNPJ_CIA", "DT_REFER", "VERSAO", "MOEDA", "ESCALA_MOEDA", "ORDEM_EXERC",
            "DT_INI_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA"],
    "BPA": ["CNPJ_CIA", "DT_REFER", "VERSAO", "MOEDA", "ESCALA_MOEDA", "ORDEM_EXERC",
            "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA"],
    "BPP": ["CNPJ_CIA", "DT_REFER", "VERSAO", "MOEDA", "ESCALA_MOEDA", "ORDEM_EXERC",
            "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA"],
}
_STMT_ACCOUNTS = {
    "DRE": re.compile(r"^3\.\d{2}(\.\d{2})?$"),
    "BPA": re.compile(r"^1(\.01(\.0[12])?)?$"),
    "BPP": re.compile(r"^2\.\d{2}(\.\d{2})?$"),
}


def _member(names: list[str], suffix: str) -> str | None:
    suffix = suffix.lower()
    return next((n for n in names if n.lower().endswith(suffix)), None)


def read_cvm_zip(source: str | Path | bytes, doc: str, year: int) -> dict[str, pd.DataFrame]:
    """Lê o ZIP da CVM e devolve as tabelas necessárias (texto bruto, sem conversões).

    Chaves: ``index``, ``DRE_con``, ``DRE_ind``, ``BPA_con``, ``BPA_ind``, ``BPP_con``,
    ``BPP_ind``, ``capital``. Arquivos ausentes viram DataFrames vazios. Só linhas
    ``ORDEM_EXERC == ÚLTIMO`` e contas usadas pelo extrator são mantidas.
    """
    data = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    prefix = f"{doc.lower()}_cia_aberta_"
    out: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        idx_name = _member(names, f"{prefix}{year}.csv")
        out["index"] = (read_cvm_csv(zf.read(idx_name)) if idx_name
                        else pd.DataFrame(columns=["CNPJ_CIA", "DT_REFER", "VERSAO", "DT_RECEB"]))
        for stmt, cols in _STMT_USECOLS.items():
            for kind in ("con", "ind"):
                name = _member(names, f"{prefix}{stmt}_{kind}_{year}.csv")
                if name is None:
                    out[f"{stmt}_{kind}"] = pd.DataFrame(columns=cols)
                    continue
                df = read_cvm_csv(zf.read(name), usecols=lambda c, cols=cols: c in cols)
                for c in cols:
                    if c not in df.columns:
                        df[c] = pd.NA
                ordem = df["ORDEM_EXERC"].fillna("").map(normalize_text)
                keep = (ordem == "ultimo") & df["CD_CONTA"].fillna("").str.match(
                    _STMT_ACCOUNTS[stmt])
                out[f"{stmt}_{kind}"] = df.loc[keep, cols].reset_index(drop=True)
        cap_name = _member(names, f"{prefix}composicao_capital_{year}.csv")
        out["capital"] = (read_cvm_csv(zf.read(cap_name)) if cap_name
                          else pd.DataFrame(columns=["CNPJ_CIA", "DT_REFER", "VERSAO"]))
    return out


_SCALE = {"mil": 1_000.0, "unidade": 1.0, "milhao": 1_000_000.0, "milhoes": 1_000_000.0}
_CURRENCY = {"real": "BRL", "reais": "BRL", "dolar": "USD", "dolares": "USD"}


def _norm_map(values: pd.Series) -> pd.Series:
    uniq = values.fillna("").unique()
    lookup = {u: normalize_text(u) for u in uniq}
    return values.fillna("").map(lookup)


def _prepare_statement(tables: Mapping[str, pd.DataFrame], stmt: str) -> pd.DataFrame:
    """Une con/ind de uma demonstração preferindo ``con`` por documento (CNPJ, data, versão)."""
    frames = []
    for kind in ("con", "ind"):
        df = tables.get(f"{stmt}_{kind}")
        if df is None or df.empty:
            continue
        df = df.copy()
        df["kind"] = kind
        frames.append(df)
    cols = ["cnpj", "dt_refer", "versao", "kind", "dt_ini", "dt_fim", "cd", "ds", "value",
            "currency"]
    if not frames:
        return pd.DataFrame(columns=cols)
    df = pd.concat(frames, ignore_index=True)
    scale = _norm_map(df["ESCALA_MOEDA"]).map(_SCALE)
    moeda = _norm_map(df["MOEDA"])
    currency = moeda.map(_CURRENCY).fillna(df["MOEDA"].fillna("").str.upper())
    value = pd.to_numeric(df["VL_CONTA"], errors="coerce") * scale
    out = pd.DataFrame({
        "cnpj": df["CNPJ_CIA"].astype(str).str.strip(),
        "dt_refer": pd.to_datetime(df["DT_REFER"], errors="coerce"),
        "versao": pd.to_numeric(df["VERSAO"], errors="coerce"),
        "kind": df["kind"],
        "dt_ini": pd.to_datetime(df.get("DT_INI_EXERC"), errors="coerce")
        if "DT_INI_EXERC" in df.columns else pd.NaT,
        "dt_fim": pd.to_datetime(df["DT_FIM_EXERC"], errors="coerce"),
        "cd": df["CD_CONTA"].astype(str).str.strip(),
        "ds": _norm_map(df["DS_CONTA"]),
        "value": value,
        "currency": currency.replace("", np.nan),
    })
    out = out.dropna(subset=["dt_refer", "versao", "dt_fim", "value"])
    out["versao"] = out["versao"].astype(int)
    doc_key = ["cnpj", "dt_refer", "versao"]
    has_con = out.loc[out["kind"] == "con", doc_key].drop_duplicates()
    has_con["_con"] = True
    out = out.merge(has_con, on=doc_key, how="left")
    out = out[(out["kind"] == "con") | out["_con"].isna()].drop(columns="_con")
    return out.reset_index(drop=True)


def _first_per_key(df: pd.DataFrame, key: list[str], order: list[str]) -> pd.DataFrame:
    return df.sort_values(key + order).drop_duplicates(key, keep="last")


def _financial_docs(bpa: pd.DataFrame, dre: pd.DataFrame) -> pd.DataFrame:
    """Documentos com layout de instituição financeira (sem ativo circulante / DRE bancária)."""
    key = ["cnpj", "dt_refer", "versao"]
    fin_bpa = bpa[(bpa["cd"] == "1.01") & ~bpa["ds"].str.contains("ativo circulante")][key]
    fin_dre = dre[(dre["cd"] == "3.01") & dre["ds"].str.contains(
        r"intermediacao|segur|resseguro|previdencia|capitalizacao")][key]
    out = pd.concat([fin_bpa, fin_dre]).drop_duplicates()
    out["financial"] = True
    return out


def _flag_financial(df: pd.DataFrame, fin: pd.DataFrame) -> pd.Series:
    key = ["cnpj", "dt_refer", "versao"]
    m = df[key].merge(fin, on=key, how="left")
    return m["financial"].fillna(False).astype(bool).to_numpy()


def _dre_facts(dre: pd.DataFrame, fin: pd.DataFrame) -> pd.DataFrame:
    if dre.empty:
        return pd.DataFrame(columns=["cnpj", "dt_refer", "versao", "kind", "dt_ini", "dt_fim",
                                     "metric", "value", "currency"])
    dre = dre.dropna(subset=["dt_ini"]).copy()
    dre["level"] = dre["cd"].str.count(r"\.")
    dre["financial"] = _flag_financial(dre, fin)
    key = ["cnpj", "dt_refer", "versao", "kind", "dt_ini", "dt_fim"]
    facts = []
    rev = dre[dre["cd"] == "3.01"]
    facts.append(rev.assign(metric="revenue"))
    ebit = dre[(dre["level"] == 1) & ~dre["financial"]
               & dre["ds"].str.contains("antes do resultado financeiro e dos tributos")]
    facts.append(_first_per_key(ebit, key, ["cd"]).assign(metric="ebit"))
    lvl1 = dre[dre["level"] == 1]
    ni_mask = (lvl1["ds"].str.contains(r"lucro|resultado liquido|prejuizo")
               & lvl1["ds"].str.contains(r"periodo|exercicio")
               & ~lvl1["ds"].str.contains(r"antes|continuad|por acao|participac"))
    ni = _first_per_key(lvl1[ni_mask], key, ["cd"])
    child = dre[(dre["level"] == 2)
                & dre["ds"].str.contains("controlador")
                & ~dre["ds"].str.contains(r"nao controlador|nao-controlador")].copy()
    child["parent"] = child["cd"].str.rsplit(".", n=1).str[0]
    attrib = ni[key + ["cd"]].merge(child[key + ["parent", "value", "currency"]],
                                     left_on=key + ["cd"], right_on=key + ["parent"], how="inner")
    attrib = _first_per_key(attrib, key, ["parent"])
    ni = ni.merge(attrib[key + ["value"]].rename(columns={"value": "v_parent"}), on=key,
                  how="left")
    ni["value"] = ni["v_parent"].where(ni["v_parent"].notna(), ni["value"])
    facts.append(ni.assign(metric="net_income"))
    cols = key + ["metric", "value", "currency"]
    return pd.concat([f[cols] for f in facts], ignore_index=True)


def _balance_facts(bpa: pd.DataFrame, bpp: pd.DataFrame, fin: pd.DataFrame) -> pd.DataFrame:
    key = ["cnpj", "dt_refer", "versao", "kind", "dt_fim"]
    cols = key + ["metric", "value", "currency"]
    facts = []
    if not bpa.empty:
        bpa = bpa.copy()
        bpa["financial"] = _flag_financial(bpa, fin)
        facts.append(bpa[bpa["cd"] == "1"].assign(metric="total_assets")[cols])
        nf = bpa[~bpa["financial"]]
        c1 = nf[(nf["cd"] == "1.01.01") & nf["ds"].str.contains("caixa")]
        c2 = nf[(nf["cd"] == "1.01.02") & nf["ds"].str.contains("aplica")]
        c1 = _first_per_key(c1, key, ["cd"])
        c2 = _first_per_key(c2, key, ["cd"])
        cash = c1.merge(c2[key + ["value"]].rename(columns={"value": "v2"}), on=key, how="left")
        # 1.01.02 (aplicações financeiras) é conta fixa do layout comercial; quando o documento
        # não a traz, não há o que somar: caixa = 1.01.01 (sem 1.01.01 ⇒ caixa ausente).
        cash["value"] = cash["value"] + cash["v2"].fillna(0.0)
        facts.append(cash.assign(metric="cash")[cols])
    if not bpp.empty:
        bpp = bpp.copy()
        bpp["financial"] = _flag_financial(bpp, fin)
        bpp["level"] = bpp["cd"].str.count(r"\.")
        eq = bpp[(bpp["level"] == 1) & bpp["ds"].str.contains("patrimonio liquido")].copy()
        eq["_cons"] = eq["ds"].str.contains("consolidado").astype(int)
        eq = _first_per_key(eq, key, ["_cons", "cd"])
        ch = bpp[bpp["level"] == 2].copy()
        ch["parent"] = ch["cd"].str.rsplit(".", n=1).str[0]
        ch = ch.merge(eq[key + ["cd"]].rename(columns={"cd": "parent"}), on=key + ["parent"])
        nci_mask = ch["ds"].str.contains(r"nao controlador|nao-controlador")
        ctrl = ch[ch["ds"].str.contains("controlador") & ~nci_mask]
        nci = ch[nci_mask]
        ctrl = _first_per_key(ctrl, key, ["cd"])[key + ["value"]].rename(
            columns={"value": "v_ctrl"})
        nci = _first_per_key(nci, key, ["cd"])[key + ["value"]].rename(
            columns={"value": "v_nci"})
        eq = eq.merge(ctrl, on=key, how="left").merge(nci, on=key, how="left")
        eq["value"] = np.where(eq["v_ctrl"].notna(), eq["v_ctrl"],
                               np.where(eq["v_nci"].notna(), eq["value"] - eq["v_nci"],
                                        eq["value"]))
        facts.append(eq.assign(metric="equity")[cols])
        nf = bpp[~bpp["financial"]]
        debt = nf[nf["cd"].isin(["2.01.04", "2.02.01"]) & nf["ds"].str.contains("emprestim")]
        debt = (debt.groupby(key, as_index=False)
                .agg(value=("value", "sum"), currency=("currency", "first")))
        facts.append(debt.assign(metric="gross_debt")[cols])
    if not facts:
        return pd.DataFrame(columns=cols)
    return pd.concat(facts, ignore_index=True)


def _capital_facts(capital: pd.DataFrame) -> pd.DataFrame:
    cols = ["cnpj", "dt_refer", "versao", "value"]
    need = {"CNPJ_CIA", "DT_REFER", "VERSAO", "QT_ACAO_TOTAL_CAP_INTEGR", "QT_ACAO_TOTAL_TESOURO"}
    if capital is None or capital.empty or not need <= set(capital.columns):
        return pd.DataFrame(columns=cols)
    total = pd.to_numeric(capital["QT_ACAO_TOTAL_CAP_INTEGR"], errors="coerce")
    treasury = pd.to_numeric(capital["QT_ACAO_TOTAL_TESOURO"], errors="coerce")
    out = pd.DataFrame({
        "cnpj": capital["CNPJ_CIA"].astype(str).str.strip(),
        "dt_refer": pd.to_datetime(capital["DT_REFER"], errors="coerce"),
        "versao": pd.to_numeric(capital["VERSAO"], errors="coerce"),
        "value": total - treasury,
    })
    out = out[(total > 0) & out["value"].gt(0)].dropna()
    out["versao"] = out["versao"].astype(int)
    return out


def extract_cvm_facts(tables: Mapping[str, pd.DataFrame], doc: str) -> pd.DataFrame:
    """Fatos brutos (``RAW_FACT_COLUMNS``, ``entity`` = CNPJ) de um ZIP da CVM já lido.

    ``received_date`` vem de ``DT_RECEB`` do índice para (CNPJ, ``DT_REFER``, ``VERSAO``);
    linhas sem recebimento conhecido são descartadas (sem data pública ⇒ nunca usadas).
    """
    doc_l = doc.lower()
    idx = tables.get("index", pd.DataFrame())
    if idx is None or idx.empty:
        return pd.DataFrame(columns=RAW_FACT_COLUMNS)
    receipts = pd.DataFrame({
        "cnpj": idx["CNPJ_CIA"].astype(str).str.strip(),
        "dt_refer": pd.to_datetime(idx["DT_REFER"], errors="coerce"),
        "versao": pd.to_numeric(idx["VERSAO"], errors="coerce"),
        "received_date": pd.to_datetime(idx["DT_RECEB"], errors="coerce"),
    }).dropna()
    receipts["versao"] = receipts["versao"].astype(int)
    receipts = (receipts.sort_values("received_date")
                .drop_duplicates(["cnpj", "dt_refer", "versao"], keep="first"))
    dre = _prepare_statement(tables, "DRE")
    bpa = _prepare_statement(tables, "BPA")
    bpp = _prepare_statement(tables, "BPP")
    fin = _financial_docs(bpa, dre)
    flows = _dre_facts(dre, fin)
    flows = flows.rename(columns={"dt_ini": "period_start", "dt_fim": "period_end"})
    flows["source"] = f"cvm:{doc_l}:" + flows["kind"].astype(str)
    stocks = _balance_facts(bpa, bpp, fin).rename(columns={"dt_fim": "period_end"})
    stocks["period_start"] = pd.NaT
    stocks["source"] = f"cvm:{doc_l}:" + stocks["kind"].astype(str)
    cap = _capital_facts(tables.get("capital", pd.DataFrame()))
    cap = cap.assign(metric="shares_outstanding", period_start=pd.NaT,
                     period_end=cap["dt_refer"], currency=np.nan,
                     source=f"cvm:{doc_l}:capital")
    parts = []
    for part in (flows, stocks, cap):
        if part.empty:
            continue
        p = part.merge(receipts, on=["cnpj", "dt_refer", "versao"], how="inner")
        parts.append(p.rename(columns={"cnpj": "entity", "versao": "version"}))
    if not parts:
        return pd.DataFrame(columns=RAW_FACT_COLUMNS)
    out = pd.concat([p[RAW_FACT_COLUMNS] for p in parts], ignore_index=True)
    out = out.dropna(subset=["value", "period_end", "received_date"])
    out["version"] = out["version"].astype(int)
    return out.reset_index(drop=True)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def cvm_facts_cached(zip_path: str | Path, doc: str, year: int,
                     extracted_dir: str | Path | None = None) -> pd.DataFrame:
    """Fatos do ZIP com cache por hash (e união com extrações de downloads anteriores).

    Cada versão do ZIP baixado gera ``{stem}__{sha16}__p{parser}.parquet``. A leitura une todas
    as extrações do mesmo ano/documento: versões de documentos que a CVM já substituiu no
    arquivo atual continuam disponíveis com a própria data de recebimento (PIT ao vivo).
    """
    zip_path = Path(zip_path)
    ext_dir = Path(extracted_dir) if extracted_dir else zip_path.parent / "extracted"
    stem = zip_path.stem
    sha16 = _sha256_file(zip_path)[:16]
    target = ext_dir / f"{stem}__{sha16}__p{CVM_PARSER_VERSION}.parquet"
    if not target.exists():
        facts = extract_cvm_facts(read_cvm_zip(zip_path, doc, year), doc)
        ext_dir.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".part")
        facts.to_parquet(tmp, index=False, compression="zstd")
        tmp.replace(target)
    frames = [pd.read_parquet(p) for p in sorted(ext_dir.glob(
        f"{stem}__*__p{CVM_PARSER_VERSION}.parquet"))]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=RAW_FACT_COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    return (out.sort_values(["received_date"])
            .drop_duplicates(["entity", "metric", "period_start", "period_end", "version",
                              "source"], keep="first")
            .reset_index(drop=True))


# ==========================================================
# SEC companyfacts
# ==========================================================

SEC_FLOW_TAGS: dict[str, list[tuple[tuple[str, str], ...]]] = {
    "net_income": [
        (("ifrs-full", "ProfitLossAttributableToOwnersOfParent"),),
        (("us-gaap", "NetIncomeLoss"),),
        (("ifrs-full", "ProfitLoss"),),
        (("us-gaap", "ProfitLoss"),),
    ],
    "revenue": [
        (("ifrs-full", "Revenue"),),
        (("ifrs-full", "RevenueFromContractsWithCustomers"),),
        (("us-gaap", "Revenues"),),
        (("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),),
        (("us-gaap", "SalesRevenueNet"),),
    ],
    "ebit": [
        (("ifrs-full", "ProfitLossFromOperatingActivities"),),
        (("us-gaap", "OperatingIncomeLoss"),),
    ],
}
SEC_STOCK_TAGS: dict[str, list[tuple[tuple[str, str], ...]]] = {
    "equity": [
        (("ifrs-full", "EquityAttributableToOwnersOfParent"),),
        (("us-gaap", "StockholdersEquity"),),
        (("ifrs-full", "Equity"),),
        (("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),),
    ],
    "total_assets": [(("ifrs-full", "Assets"),), (("us-gaap", "Assets"),)],
    "cash": [
        (("ifrs-full", "CashAndCashEquivalents"),),
        (("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),),
    ],
    "gross_debt": [
        (("ifrs-full", "Borrowings"),),
        (("ifrs-full", "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"),
         ("ifrs-full", "NoncurrentPortionOfNoncurrentBorrowings")),
        (("ifrs-full", "ShorttermBorrowings"), ("ifrs-full", "LongtermBorrowings")),
        (("us-gaap", "LongTermDebt"),),
        (("us-gaap", "LongTermDebtCurrent"), ("us-gaap", "LongTermDebtNoncurrent")),
    ],
    "shares_outstanding": [
        (("dei", "EntityCommonStockSharesOutstanding"),),
        (("us-gaap", "CommonStockSharesOutstanding"),),
    ],
}

_CCY_UNIT = re.compile(r"^[A-Z]{3}$")


def fetch_sec_companyfacts(cik: str | int, *, http_get: HttpGet | None = None,
                           cache_dir: str | Path | None = DEFAULT_CACHE_ROOT / "sec",
                           max_age_days: float = 7.0, refresh: bool = False,
                           user_agent: str | None = None,
                           limiter: RateLimiter | None = None) -> dict | None:
    """``companyfacts`` de um CIK (cache JSON; ``User-Agent`` e limite ≤ 8 req/s). 404 ⇒ ``None``."""
    cik10 = format_cik(cik)
    if cik10 is None:
        raise ValueError(f"CIK inválido: {cik!r}")
    path = Path(cache_dir) / f"companyfacts_CIK{cik10}.json" if cache_dir is not None else None
    if path is not None and path.exists() and not refresh:
        age_days = (time.time() - path.stat().st_mtime) / 86400.0
        if age_days <= max_age_days:
            return json.loads(path.read_bytes())
    try:
        data = _sec_get(SEC_COMPANYFACTS_URL.format(cik=cik10), http_get, user_agent, limiter)
    except HttpError as exc:
        if exc.status == 404:
            return None
        if path is not None and path.exists():
            logger.warning("Falha ao atualizar companyfacts %s (%s); usando cache.", cik10, exc)
            return json.loads(path.read_bytes())
        raise
    obj = json.loads(data)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return obj


def _sec_entries(facts: Mapping, taxonomy: str, tag: str, unit_filter: Callable[[str], bool],
                 ) -> pd.DataFrame:
    node = facts.get(taxonomy, {}).get(tag)
    cols = ["unit", "start", "end", "val", "filed", "form", "accn"]
    if not node:
        return pd.DataFrame(columns=cols)
    rows = []
    for unit, entries in node.get("units", {}).items():
        if not unit_filter(unit):
            continue
        for e in entries:
            if e.get("form") not in SEC_ACCEPTED_FORMS or e.get("val") is None:
                continue
            rows.append({"unit": unit, "start": e.get("start"), "end": e.get("end"),
                         "val": e.get("val"), "filed": e.get("filed"), "form": e.get("form"),
                         "accn": e.get("accn")})
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows, columns=cols)
    df["start"] = pd.to_datetime(df["start"], errors="coerce")
    df["end"] = pd.to_datetime(df["end"], errors="coerce")
    df["filed"] = pd.to_datetime(df["filed"], errors="coerce")
    df["val"] = pd.to_numeric(df["val"], errors="coerce")
    return df.dropna(subset=["end", "filed", "val"])


def _sec_reporting_currency(facts: Mapping) -> str | None:
    counts: dict[str, int] = {}
    for metric_tags in (SEC_STOCK_TAGS["total_assets"], SEC_FLOW_TAGS["revenue"],
                        SEC_STOCK_TAGS["equity"]):
        for cand in metric_tags:
            for tax, tag in cand:
                for unit, entries in facts.get(tax, {}).get(tag, {}).get("units", {}).items():
                    if _CCY_UNIT.match(unit):
                        counts[unit] = counts.get(unit, 0) + len(entries)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _sec_candidate_frame(facts: Mapping, cand: tuple[tuple[str, str], ...], flow: bool,
                         unit_filter: Callable[[str], bool]) -> pd.DataFrame:
    parts = [_sec_entries(facts, tax, tag, unit_filter) for tax, tag in cand]
    if any(p.empty for p in parts):
        return pd.DataFrame(columns=["unit", "start", "end", "val", "filed", "accn"])
    if flow:
        parts = [p[p["start"].notna()] for p in parts]
    else:
        parts = [p.assign(start=pd.NaT) for p in parts]
    if len(parts) == 1:
        df = parts[0]
    else:
        key = ["unit", "end", "filed", "accn"] + (["start"] if flow else [])
        df = parts[0][key + ["val"]]
        for p in parts[1:]:
            p2 = p[key + ["val"]].drop_duplicates(key)
            df = df.drop_duplicates(key).merge(p2, on=key, suffixes=("", "_b"))
            df["val"] = df["val"] + df["val_b"]
            df = df.drop(columns="val_b")
        if not flow:
            df["start"] = pd.NaT
    return df


def _version_walk(df: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """Sequência PIT por período: em ordem de ``filed``, só aceita valores da melhor tag vista
    até então; repetições do mesmo valor não geram nova versão."""
    out = []
    # No mesmo dia de arquivamento vale só a melhor tag (sem versões intermediárias espúrias).
    df = (df.sort_values(key + ["filed", "priority", "accn"])
          .drop_duplicates(key + ["filed"], keep="first"))
    for _, g in df.groupby(key, sort=False, dropna=False):
        best = math.inf
        last_val: float | None = None
        ver = 0
        for row in g.itertuples(index=False):
            if row.priority > best:
                continue
            best = row.priority
            if last_val is not None and math.isclose(row.val, last_val, rel_tol=1e-12,
                                                     abs_tol=1e-9):
                continue
            ver += 1
            last_val = row.val
            out.append({**{k: getattr(row, k) for k in key}, "val": row.val,
                        "filed": row.filed, "version": ver, "tag": row.tag, "form": row.form})
    return pd.DataFrame(out)


def extract_sec_facts(companyfacts: Mapping) -> pd.DataFrame:
    """Fatos brutos (``RAW_FACT_COLUMNS``, ``entity`` = CIK) de um JSON ``companyfacts``.

    Moeda única por empresa (a unidade monetária mais frequente nos fatos-chave); fluxos com
    duração de 3, 6, 9 ou 12 meses (formulários 10-K/10-Q/20-F/40-F/6-K); saldos por data.
    Múltiplas tags candidatas por métrica, em ordem de prioridade, resolvidas sem look-ahead.
    """
    facts = companyfacts.get("facts", {}) if companyfacts else {}
    cik = format_cik(companyfacts.get("cik")) if companyfacts else None
    ccy = _sec_reporting_currency(facts)
    rows = []
    specs = [(m, c, True) for m, c in SEC_FLOW_TAGS.items()] + \
            [(m, c, False) for m, c in SEC_STOCK_TAGS.items()]
    for metric, candidates, flow in specs:
        is_shares = metric == "shares_outstanding"
        if not is_shares and ccy is None:
            continue

        def unit_ok(u: str, is_shares: bool = is_shares) -> bool:
            return u == "shares" if is_shares else u == ccy

        frames = []
        for prio, cand in enumerate(candidates):
            df = _sec_candidate_frame(facts, cand, flow, unit_ok)
            if df.empty:
                continue
            if flow:
                dur = (df["end"] - df["start"]).dt.days + 1
                df = df[dur.between(_QUARTER_DAYS[0], _ANNUAL_DAYS[1])]
            if is_shares:
                # Capa (dei) com várias classes no mesmo arquivo/data: soma de valores distintos.
                df = (df.groupby(["end", "filed", "accn"], as_index=False, dropna=False)
                      .agg(val=("val", lambda s: float(pd.Series(s).drop_duplicates().sum())),
                           unit=("unit", "first"), start=("start", "first")))
            if df.empty:
                continue
            tag = "+".join(t for _, t in cand)
            form = (df["form"] if "form" in df.columns else pd.Series("", index=df.index))
            frames.append(df.assign(priority=prio, tag=tag, form=form.fillna("")))
        if not frames:
            continue
        allc = pd.concat(frames, ignore_index=True)
        allc["start_k"] = allc["start"].fillna(pd.Timestamp(0))
        seq = _version_walk(allc, ["start_k", "end"])
        if seq.empty:
            continue
        seq["start"] = seq["start_k"].where(seq["start_k"] != pd.Timestamp(0), pd.NaT)
        for r in seq.itertuples(index=False):
            rows.append({
                "entity": cik, "metric": metric,
                "period_start": r.start if flow else pd.NaT, "period_end": r.end,
                "value": float(r.val), "currency": None if is_shares else ccy,
                "received_date": r.filed, "version": int(r.version),
                "source": f"sec:{r.tag}" + (f":{r.form}" if r.form else ""),
            })
    if not rows:
        return pd.DataFrame(columns=RAW_FACT_COLUMNS)
    out = pd.DataFrame(rows, columns=RAW_FACT_COLUMNS)
    out["period_start"] = pd.to_datetime(out["period_start"])
    out["period_end"] = pd.to_datetime(out["period_end"])
    out["received_date"] = pd.to_datetime(out["received_date"])
    return out


# ==========================================================
# Montagem da tabela PIT
# ==========================================================

def _empty_pit() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="object") for c in PIT_COLUMNS})
    return _coerce_pit(df)


def _coerce_pit(df: pd.DataFrame) -> pd.DataFrame:
    out = df[PIT_COLUMNS].copy()
    out["issuer_id"] = out["issuer_id"].astype(str)
    out["metric"] = out["metric"].astype(str)
    out["period_end"] = pd.to_datetime(out["period_end"]).astype("datetime64[ns]")
    out["available_date"] = pd.to_datetime(out["available_date"]).astype("datetime64[ns]")
    out["value"] = pd.to_numeric(out["value"], errors="coerce").astype(float)
    out["currency"] = out["currency"].astype("string")
    out["source"] = out["source"].astype(str)
    out["version"] = pd.to_numeric(out["version"], errors="coerce").astype("int64")
    return out.reset_index(drop=True)


def pit_from_raw_facts(raw: pd.DataFrame, entity_to_issuer: Mapping[str, str | Iterable[str]],
                       lag_bdays: int = DEFAULT_LAG_BDAYS) -> pd.DataFrame:
    """Converte fatos brutos em tabela PIT longa (``PIT_COLUMNS``).

    ``available_date = received_date + lag_bdays`` dias úteis. Saldos: uma linha por
    publicação que muda o valor do período. Fluxos: histórico PIT do TTM (ver módulo).
    """
    if raw is None or raw.empty:
        return _empty_pit()
    mapping: list[tuple[str, str]] = []
    for ent, iss in entity_to_issuer.items():
        if ent is None or (isinstance(ent, float) and math.isnan(ent)):
            continue
        for i in ([iss] if isinstance(iss, str) else list(iss)):
            mapping.append((str(ent), str(i)))
    if not mapping:
        return _empty_pit()
    mp = pd.DataFrame(mapping, columns=["entity", "issuer_id"]).drop_duplicates()
    df = raw.copy()
    df["entity"] = df["entity"].astype(str)
    df = df.merge(mp, on="entity", how="inner")
    if df.empty:
        return _empty_pit()
    df["available_date"] = add_business_days(pd.to_datetime(df["received_date"]), lag_bdays)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df = df.dropna(subset=["available_date", "period_end", "value"])
    early = df["available_date"] < df["period_end"]
    if early.any():
        logger.warning("%d fatos com publicação anterior ao fim do período descartados.",
                       int(early.sum()))
        df = df[~early]
    out_frames = []
    stocks = df[df["metric"].isin(STOCK_METRICS)].sort_values(
        ["issuer_id", "metric", "period_end", "available_date", "version", "source"])
    stocks = stocks.drop_duplicates(["issuer_id", "metric", "period_end", "available_date",
                                     "version"], keep="first")
    if not stocks.empty:
        grp = stocks.groupby(["issuer_id", "metric", "period_end"], sort=False)["value"]
        prev = grp.shift(1)
        changed = prev.isna() | ~np.isclose(stocks["value"], prev, rtol=1e-12, atol=1e-9)
        out_frames.append(stocks[changed])
    flows = df[df["metric"].isin(FLOW_METRICS)]
    ttm_rows = []
    for (iid, metric), g in flows.groupby(["issuer_id", "metric"], sort=True):
        ccy = g["currency"].dropna()
        if not ccy.empty and ccy.nunique() > 1:
            main = ccy.value_counts().index[0]
            g = g[g["currency"] == main]
        for r in _ttm_history(g):
            ttm_rows.append({"issuer_id": iid, "metric": f"{metric}_ttm", **r})
    if ttm_rows:
        out_frames.append(pd.DataFrame(ttm_rows))
    if not out_frames:
        return _empty_pit()
    out = pd.concat([f.reindex(columns=PIT_COLUMNS) for f in out_frames], ignore_index=True)
    out = _coerce_pit(out)
    return out.sort_values(["issuer_id", "metric", "period_end", "available_date",
                            "version"]).reset_index(drop=True)


def _progress(cb: Callable[[str], None] | None, msg: str) -> None:
    logger.info(msg)
    if cb is not None:
        cb(msg)


def build_pit_fundamentals(
    universe: Universe,
    start: date,
    end: date,
    http_get: HttpGet | None = None,
    *,
    security_master: pd.DataFrame | None = None,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
    lag_bdays: int = DEFAULT_LAG_BDAYS,
    include_cvm: bool = True,
    include_sec: bool = True,
    cvm_max_age_days: float = 7.0,
    sec_max_age_days: float = 7.0,
    user_agent: str | None = None,
    limiter: RateLimiter | None = None,
    today: date | None = None,
    progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Tabela PIT longa para o universo entre ``start`` e ``end``.

    Fonte por emissor: CVM quando há CNPJ (preferida: trimestral e PIT), senão SEC quando
    há CIK. Baixa ITR/DFP de ``start.year − 1`` (necessário para o TTM no início da janela)
    até ``end.year``, com cache em ``cache_root/cvm`` e ``cache_root/sec``. Mantém linhas com
    ``available_date <= end`` e ``period_end >= start − 760 dias``.

    ``df.attrs`` registra janela, fontes, limitações e cobertura (JSON-serializável).
    """
    if start > end:
        raise ValueError("start precisa ser <= end.")
    cache_root = Path(cache_root)
    cvm_dir = cache_root / "cvm"
    sec_dir = cache_root / "sec"
    if security_master is None:
        fca = None
        for year in (end.year, end.year - 1):
            try:
                fca = fetch_cvm_fca(year, http_get=http_get, cache_dir=cvm_dir)
                break
            except HttpError as exc:
                if exc.status != 404:
                    raise
        sec_t = None
        if include_sec:
            us = [t for t, ln in universe.lines.iterrows()
                  if str(ln["line_type"]) in ("ADR", "US_LISTED")]
            try:
                sec_t = fetch_sec_company_tickers(http_get=http_get, user_agent=user_agent,
                                                  limiter=limiter, fallback_tickers=us,
                                                  cache_dir=sec_dir)
            except HttpError as exc:
                logger.warning("Mapa ticker→CIK da SEC indisponível: %s", exc)
        security_master = build_security_master(universe, fca, sec_t)
    sm = security_master
    limitations = [
        "Valores da CVM publicados apenas na última versão de cada documento: "
        "reapresentações valem a partir do próprio DT_RECEB (política estrita).",
        "composicao_capital da CVM só existe a partir de 2020: ações antes disso ausentes.",
        "Financeiras (bancos/seguradoras): EBIT, caixa e dívida bruta não se aplicam (ausentes).",
    ]
    raw_frames: list[pd.DataFrame] = []
    entity_map: dict[str, list[str]] = {}
    sources: list[str] = []
    if include_cvm:
        cvm_iss = sm[sm["cnpj"].notna()]
        for iid, cnpj in cvm_iss["cnpj"].items():
            entity_map.setdefault(str(cnpj), []).append(str(iid))
        if entity_map:
            cnpjs = set(entity_map)
            for year in range(start.year - 1, end.year + 1):
                for doc in CVM_DOCS:
                    path = fetch_cvm_zip(doc, year, cache_dir=cvm_dir, http_get=http_get,
                                         max_age_days=cvm_max_age_days, today=today)
                    if path is None:
                        _progress(progress, f"CVM {doc} {year}: não publicado (404).")
                        continue
                    facts = cvm_facts_cached(path, doc, year)
                    facts = facts[facts["entity"].isin(cnpjs)]
                    _progress(progress, f"CVM {doc} {year}: {len(facts)} fatos do universo.")
                    raw_frames.append(facts)
            sources.append(f"CVM dados abertos ITR/DFP {start.year - 1}–{end.year}")
    cvm_covered: set[str] = set()
    for f in raw_frames:
        for ent in f["entity"].astype(str).unique():
            cvm_covered.update(entity_map.get(ent, []))
    if include_sec:
        sec_iss = sm[sm["cik"].notna() & ~sm.index.astype(str).isin(sorted(cvm_covered))]
        for iid, cik in sec_iss["cik"].items():
            obj = fetch_sec_companyfacts(cik, http_get=http_get, cache_dir=sec_dir,
                                         max_age_days=sec_max_age_days, user_agent=user_agent,
                                         limiter=limiter)
            if obj is None:
                _progress(progress, f"SEC CIK {cik} ({iid}): sem companyfacts (404).")
                continue
            facts = extract_sec_facts(obj)
            entity_map.setdefault(str(format_cik(cik)), []).append(str(iid))
            _progress(progress, f"SEC CIK {cik} ({iid}): {len(facts)} fatos.")
            raw_frames.append(facts)
        if not sec_iss.empty:
            sources.append("SEC EDGAR companyfacts")
    raw = (pd.concat([f for f in raw_frames if not f.empty], ignore_index=True)
           if any(not f.empty for f in raw_frames) else pd.DataFrame(columns=RAW_FACT_COLUMNS))
    pit = pit_from_raw_facts(raw, entity_map, lag_bdays=lag_bdays)
    end_ts = pd.Timestamp(end)
    floor = pd.Timestamp(start) - pd.Timedelta(days=760)
    pit = pit[(pit["available_date"] <= end_ts) & (pit["period_end"] >= floor)]
    pit = pit.reset_index(drop=True)
    cov = pit_coverage(pit)
    pit.attrs = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "start": start.isoformat(), "end": end.isoformat(), "lag_bdays": int(lag_bdays),
        "sources": sources, "limitations": limitations, "notice": PIT_NOTICE,
        "point_in_time": True,
        "issuers_requested": int(len(sm)),
        "issuers_with_data": int(cov.shape[0]),
        "issuers_without_data": sorted(set(sm.index.astype(str)) - set(cov.index.astype(str))),
    }
    return pit


# ==========================================================
# Consulta PIT e índices
# ==========================================================

def pit_snapshot(pit: pd.DataFrame, as_of: date, *, max_age_days: int = DEFAULT_MAX_AGE_DAYS,
                 metrics: Iterable[str] | None = None) -> pd.DataFrame:
    """Linha escolhida por (emissor, métrica) em ``as_of`` — sem look-ahead.

    Só linhas com ``available_date <= as_of``; maior ``period_end``; dentro dele, publicação
    mais recente (``available_date``, depois ``version``). Períodos com mais de
    ``max_age_days`` dias em ``as_of`` são descartados (dado velho ≠ dado atual).
    """
    ts = pd.Timestamp(as_of)
    df = pit[pit["available_date"] <= ts]
    if metrics is not None:
        df = df[df["metric"].isin(list(metrics))]
    if max_age_days is not None:
        df = df[(ts - df["period_end"]).dt.days <= max_age_days]
    if df.empty:
        return df.iloc[0:0].copy()
    df = df.sort_values(["issuer_id", "metric", "period_end", "available_date", "version"])
    return df.drop_duplicates(["issuer_id", "metric"], keep="last").reset_index(drop=True)


def _last_price(price_local: pd.DataFrame, as_of: date, max_age_days: int) -> pd.Series:
    ts = pd.Timestamp(as_of)
    px = price_local.copy()
    px.index = pd.to_datetime(px.index)
    px = px.loc[px.index <= ts].sort_index()
    if px.empty:
        return pd.Series(np.nan, index=price_local.columns, dtype=float)
    out = {}
    for col in px.columns:
        s = pd.to_numeric(px[col], errors="coerce").dropna()
        s = s[s > 0]
        if s.empty or (ts - s.index[-1]).days > max_age_days:
            out[col] = np.nan
        else:
            out[col] = float(s.iloc[-1])
    return pd.Series(out, dtype=float)


def _safe_div(num: pd.Series, den: pd.Series, positive_den: bool = True) -> pd.Series:
    den = den.astype(float)
    ok = den.notna() & num.notna() & ((den > 0) if positive_den else (den != 0))
    out = pd.Series(np.nan, index=num.index, dtype=float)
    out[ok] = num[ok].astype(float) / den[ok]
    return out


def pit_ratios(pit: pd.DataFrame, price_local: pd.DataFrame, as_of: date,
               shares: pd.Series | None = None, *,
               max_age_days: int = DEFAULT_MAX_AGE_DAYS,
               max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS,
               price_currency: Mapping[str, str] | pd.Series | None = None) -> pd.DataFrame:
    """Índices fundamentalistas PIT por emissor em ``as_of``.

    - ``price_local``: data × emissor, preço POR AÇÃO LOCAL na MOEDA DAS DEMONSTRAÇÕES
      (o chamador converte; ver :func:`local_equivalent_prices`). Usa o último preço
      ``<= as_of`` com até ``max_price_age_days`` dias.
    - ``shares``: opcional (emissor → ações); padrão = ``shares_outstanding`` da tabela PIT.
    - ``price_currency``: opcional; se informado e divergente da moeda das demonstrações,
      os índices de preço do emissor ficam ``NaN`` (nunca mistura moedas).

    Colunas: ``earnings_yield`` (LL TTM / valor de mercado), ``book_to_price`` (PL / valor de
    mercado), ``roe`` (LL TTM / PL), ``ebit_margin`` (EBIT TTM / receita TTM),
    ``net_debt_to_equity`` ((dívida bruta − caixa) / PL), ``asset_turnover`` (receita TTM /
    ativo total). Denominadores ``<= 0`` ou ausentes ⇒ ``NaN``.
    """
    snap = pit_snapshot(pit, as_of, max_age_days=max_age_days)
    wide = (snap.pivot(index="issuer_id", columns="metric", values="value")
            if not snap.empty else pd.DataFrame())
    ccy = (snap[snap["currency"].notna()].groupby("issuer_id")["currency"]
           .agg(lambda s: s.iloc[0] if s.nunique() == 1 else pd.NA)
           if not snap.empty else pd.Series(dtype="string"))
    issuers = sorted(set(map(str, price_local.columns)) | set(map(str, wide.index)))
    wide = wide.reindex(index=issuers, columns=list(PIT_METRICS))
    px = _last_price(price_local, as_of, max_price_age_days).reindex(issuers)
    sh = wide["shares_outstanding"] if shares is None else pd.Series(shares, dtype=float).reindex(
        issuers)
    if price_currency is not None:
        pc = pd.Series(price_currency).reindex(issuers)
        stmt = ccy.reindex(issuers)
        bad = pc.notna() & stmt.notna() & (pc.astype(str) != stmt.astype(str))
        px[bad] = np.nan
    mcap = px * sh.astype(float)
    eq = wide["equity"]
    out = pd.DataFrame(index=pd.Index(issuers, name="issuer_id"), columns=RATIO_COLUMNS,
                       dtype=float)
    out["earnings_yield"] = _safe_div(wide["net_income_ttm"], mcap)
    out["book_to_price"] = _safe_div(eq, mcap)
    out["roe"] = _safe_div(wide["net_income_ttm"], eq)
    out["ebit_margin"] = _safe_div(wide["ebit_ttm"], wide["revenue_ttm"])
    out["net_debt_to_equity"] = _safe_div(wide["gross_debt"] - wide["cash"], eq)
    out["asset_turnover"] = _safe_div(wide["revenue_ttm"], wide["total_assets"])
    out.attrs = {"as_of": pd.Timestamp(as_of).date().isoformat(), "point_in_time": True,
                 "max_age_days": int(max_age_days)}
    return out


def local_equivalent_prices(close: pd.DataFrame, fx: pd.DataFrame, line_master: pd.DataFrame,
                            statement_currency: Mapping[str, str] | pd.Series,
                            issuers: Iterable[str] | None = None,
                            fx_max_gap_days: int = 5) -> pd.DataFrame:
    """Preço por AÇÃO LOCAL na moeda das demonstrações (data × emissor) para :func:`pit_ratios`.

    Escolha da linha por emissor (determinística): linhas na moeda das demonstrações primeiro
    (ON/PN antes de unit), depois ADR/US; dentro de cada grupo a linha primária e depois a
    ordem alfabética. Exige ``shares_per_line`` conhecido. Conversão:
    ``preço_linha / ações_por_linha × fx[moeda_linha] / fx[moeda_demonstrações]`` com ``fx`` em
    USD por unidade (``USD`` = 1). Câmbio pode ser propagado até ``fx_max_gap_days`` dias;
    preços NUNCA são propagados.
    """
    stmt = pd.Series(statement_currency, dtype=object)
    want = list(issuers) if issuers is not None else sorted(stmt.index.astype(str))
    fxx = fx.copy()
    fxx.index = pd.to_datetime(fxx.index)
    fxx = fxx.sort_index().reindex(pd.to_datetime(close.index).union(fxx.index))
    fxx = fxx.ffill(limit=fx_max_gap_days)
    if "USD" not in fxx.columns:
        fxx["USD"] = 1.0
    cl = close.copy()
    cl.index = pd.to_datetime(cl.index)
    out = {}
    for iid in want:
        s_ccy = stmt.get(iid)
        lines = line_master[(line_master["issuer_id"] == iid)
                            & line_master["shares_per_line"].notna()
                            & line_master.index.isin(cl.columns)]
        if lines.empty or s_ccy is None or (isinstance(s_ccy, float) and math.isnan(s_ccy)):
            out[iid] = pd.Series(np.nan, index=cl.index)
            continue
        rank = pd.DataFrame({
            "other_ccy": (lines["currency"] != s_ccy).astype(int),
            "unit": (lines["share_class"] == "UNIT").astype(int),
            "secondary": (~lines["primary_line"].astype(bool)).astype(int),
            "ticker": lines.index,
        }, index=lines.index).sort_values(["other_ccy", "unit", "secondary", "ticker"])
        tk = rank.index[0]
        ln = lines.loc[tk]
        px = pd.to_numeric(cl[tk], errors="coerce") / float(ln["shares_per_line"])
        l_ccy = str(ln["currency"])
        if l_ccy != s_ccy:
            if l_ccy not in fxx.columns or s_ccy not in fxx.columns:
                out[iid] = pd.Series(np.nan, index=cl.index)
                continue
            conv = (fxx[l_ccy] / fxx[s_ccy]).reindex(cl.index)
            px = px * conv
        out[iid] = px
    return pd.DataFrame(out, index=cl.index)


# ==========================================================
# Persistência e cobertura
# ==========================================================

def validate_pit(df: pd.DataFrame) -> None:
    """Valida esquema e invariantes da tabela PIT (levanta ``ValueError``)."""
    missing = [c for c in PIT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Tabela PIT sem colunas: {missing}")
    bad = sorted(set(df["metric"]) - set(PIT_METRICS))
    if bad:
        raise ValueError(f"Métricas desconhecidas na tabela PIT: {bad}")
    if df["value"].isna().any():
        raise ValueError("Tabela PIT não armazena valores ausentes (ausência = sem linha).")
    if (pd.to_datetime(df["available_date"]) < pd.to_datetime(df["period_end"])).any():
        raise ValueError("available_date anterior ao fim do período (look-ahead).")
    dup = df.duplicated(["issuer_id", "metric", "period_end", "available_date", "version"])
    if dup.any():
        raise ValueError("Linhas PIT duplicadas para a mesma publicação.")


def save_pit(df: pd.DataFrame, path: str | Path = DEFAULT_PIT_PATH) -> Path:
    """Grava a tabela PIT em parquet (zstd) após validação; não sobrescreve outro arquivo
    silenciosamente — escreve em ``.part`` e renomeia (atômico)."""
    validate_pit(df)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".part")
    out = _coerce_pit(df)
    out.attrs = {k: v for k, v in df.attrs.items() if _json_ok(v)}
    out.to_parquet(tmp, index=False, compression="zstd")
    tmp.replace(p)
    return p


def _json_ok(v) -> bool:
    try:
        json.dumps(v)
        return True
    except TypeError:
        return False


def load_pit(path: str | Path = DEFAULT_PIT_PATH) -> pd.DataFrame:
    """Lê e valida uma tabela PIT gravada por :func:`save_pit`."""
    df = pd.read_parquet(Path(path))
    attrs = dict(df.attrs)
    out = _coerce_pit(df)
    validate_pit(out)
    out.attrs = attrs
    return out


def pit_coverage(pit: pd.DataFrame) -> pd.DataFrame:
    """Cobertura por emissor: métricas presentes, último ``period_end`` e ``available_date``."""
    if pit.empty:
        return pd.DataFrame(columns=["n_metrics", "metrics", "last_period_end",
                                     "last_available_date", "n_rows"])
    g = pit.groupby("issuer_id")
    return pd.DataFrame({
        "n_metrics": g["metric"].nunique(),
        "metrics": g["metric"].agg(lambda s: "|".join(sorted(set(s)))),
        "last_period_end": g["period_end"].max(),
        "last_available_date": g["available_date"].max(),
        "n_rows": g.size(),
    }).sort_index()


__all__ = [
    "PIT_COLUMNS", "PIT_METRICS", "RATIO_COLUMNS", "RAW_FACT_COLUMNS", "FLOW_METRICS",
    "STOCK_METRICS", "PIT_SNAPSHOT_FILENAME", "DEFAULT_PIT_PATH", "add_business_days",
    "discrete_quarters", "ttm_at", "cvm_zip_url", "fetch_cvm_zip", "read_cvm_zip",
    "extract_cvm_facts", "cvm_facts_cached", "fetch_sec_companyfacts", "extract_sec_facts",
    "pit_from_raw_facts", "build_pit_fundamentals", "pit_snapshot", "pit_ratios",
    "local_equivalent_prices", "validate_pit", "save_pit", "load_pit", "pit_coverage",
    "build_line_master",
]
