"""Carteiras de ETFs a partir dos arquivos públicos dos emissores e da B3.

- iShares (ILF, EWZ, EWW, ECH, EPU, EWZS): ``.../products/<id>/<slug>/1467271812596.ajax?
  fileType=csv&fileName=<ETF>_holdings&dataType=fund`` respondia HTML em 2026-10; o caminho
  verificado é ``.../products/<id>/<slug>/latest-holdings.csv`` (só a carteira mais recente:
  a rotina arquiva cada coleta e o histórico point-in-time é o próprio arquivo).
- Global X (ARGT, COLO): ``assets.globalxetfs.com/funds/holdings/<etf>_full-holdings_<AAAAMMDD>.csv``
  (arquivos datados; tenta a data pedida e até 7 dias corridos para trás).
- B3 (BOVA11 → IBOV, SMAL11 → SMLL): ``GetPortfolioDay`` (carteira teórica do dia).

Mapeamento ``ticker_bruto → issuer_id``: arquivo curado ``configs/cdp/cobertura/etf_mapa.csv``
quando existir (``fonte, etf, ticker_bruto, issuer_id``…); senão regra pela bolsa (sufixo do
Yahoo) contra as linhas do universo. Sem correspondência ⇒ ``issuer_id`` ausente ("fora do
universo"), nunca descartado. Pesos em fração do patrimônio (``0,0782`` = 7,82%); futuros
têm peso 0 e ``valor_nocional`` preenchido.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from collections.abc import Mapping
from datetime import date, datetime

import numpy as np
import pandas as pd

ISHARES = {
    "ILF": (239761, "ishares-latin-america-40-etf"),
    "EWZ": (239612, "ishares-msci-brazil-etf"),
    "EWW": (239670, "ishares-msci-mexico-etf"),
    "ECH": (239618, "ishares-msci-chile-etf"),
    "EPU": (239606, "ishares-msci-peru-and-global-exposure-etf"),
    "EWZS": (239613, "ishares-msci-brazil-small-cap-etf"),
}
GLOBALX = ("ARGT", "COLO")
B3_INDICE = {"BOVA11": "IBOV", "BOVA11.SA": "IBOV", "SMAL11": "SMLL", "SMAL11.SA": "SMLL"}
ETFS = tuple(ISHARES) + GLOBALX + ("BOVA11.SA", "SMAL11.SA")

COLUNAS = ["ticker_bruto", "nome", "peso", "setor", "pais", "issuer_id", "fonte", "url",
           "data_ref", "sha256", "classe_ativo", "yahoo_ticker", "valor_mercado",
           "valor_nocional", "sedol", "mapeamento"]

_ISHARES_BOLSA = {
    "XBSP": ".SA", "Bolsa Mexicana De Valores": ".MX", "Santiago Stock Exchange": ".SN",
    "Bolsa De Valores De Colombia": ".CL", "Bolsa De Valores De Lima": ".LM",
    "Buenos Aires Stock Exchange": ".BA",
}
_BBG_BOLSA = {"BZ": ".SA", "MM": ".MX", "CI": ".SN", "CB": ".CL", "PE": ".LM", "AR": ".BA"}


def url_ishares(etf: str) -> str:
    pid, slug = ISHARES[etf]
    return f"https://www.ishares.com/us/products/{pid}/{slug}/latest-holdings.csv"


def url_globalx(etf: str, d: date) -> str:
    return (f"https://assets.globalxetfs.com/funds/holdings/{etf.lower()}_full-holdings_"
            f"{d.strftime('%Y%m%d')}.csv")


def url_b3(indice: str) -> str:
    q = json.dumps({"language": "pt-br", "pageNumber": 1, "pageSize": 200, "index": indice,
                    "segment": "1"}, separators=(",", ":"))
    return ("https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/"
            + base64.b64encode(q.encode()).decode())


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", "", regex=False)
                         .str.replace("%", "", regex=False).str.strip()
                         .replace({"-": None, "": None}), errors="coerce")


def validar_csv_ishares(conteudo: bytes) -> None:
    txt = conteudo.decode("utf-8-sig", errors="replace")
    if "<html" in txt[:500].lower() or "\nTicker," not in txt:
        raise ValueError("Arquivo iShares sem tabela de carteira (resposta HTML?).")


def ler_ishares(conteudo: bytes) -> tuple[pd.DataFrame, date | None]:
    txt = conteudo.decode("utf-8-sig", errors="replace")
    linhas = txt.splitlines()
    data_ref = None
    for ln in linhas[:12]:
        m = re.search(r'Fund Holdings as of,"?([A-Za-z]{3} \d{1,2}, \d{4})', ln)
        if m:
            data_ref = datetime.strptime(m.group(1), "%b %d, %Y").date()
    i = next(k for k, ln in enumerate(linhas) if ln.startswith("Ticker,"))
    corpo = []
    for ln in linhas[i:]:
        if not ln.strip() or ln.startswith("\xa0") or ln.lower().startswith('"the content'):
            break
        corpo.append(ln)
    df = pd.read_csv(io.StringIO("\n".join(corpo)), dtype=str, keep_default_na=False)
    out = pd.DataFrame({
        "ticker_bruto": df["Ticker"].str.strip(),
        "nome": df["Name"].str.strip(),
        "peso": _num(df["Weight (%)"]) / 100.0,
        "setor": df.get("Sector", pd.Series("", index=df.index)).str.strip(),
        "pais": df.get("Location", pd.Series("", index=df.index)).str.strip(),
        "classe_ativo": df.get("Asset Class", pd.Series("", index=df.index)).str.strip(),
        "bolsa": df.get("Exchange", pd.Series("", index=df.index)).str.strip(),
        "valor_mercado": _num(df.get("Market Value", pd.Series("", index=df.index))),
        "valor_nocional": _num(df.get("Notional Value", pd.Series("", index=df.index))),
        "sedol": None,
    })
    return out, data_ref


def ler_globalx(conteudo: bytes) -> tuple[pd.DataFrame, date | None]:
    txt = conteudo.decode("utf-8-sig", errors="replace")
    linhas = txt.splitlines()
    data_ref = None
    for ln in linhas[:4]:
        m = re.search(r"as of (\d{2})/(\d{2})/(\d{4})", ln)
        if m:
            data_ref = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    i = next(k for k, ln in enumerate(linhas) if ln.startswith("% of Net Assets"))
    df = pd.read_csv(io.StringIO("\n".join(linhas[i:])), dtype=str, keep_default_na=False)
    df = df[df["Ticker"].str.strip() != ""]
    out = pd.DataFrame({
        "ticker_bruto": df["Ticker"].str.strip(),
        "nome": df["Name"].str.strip(),
        "peso": _num(df["% of Net Assets"]) / 100.0,
        "setor": None, "pais": None,
        "classe_ativo": "Equity",
        "bolsa": df["Ticker"].str.strip().str.split(" ").str[-1].where(
            df["Ticker"].str.strip().str.contains(" "), "US"),
        "valor_mercado": _num(df.get("Market Value ($)", pd.Series("", index=df.index))),
        "valor_nocional": None,
        "sedol": df.get("SEDOL", pd.Series(None, index=df.index)),
    })
    return out, data_ref


def validar_b3(conteudo: bytes) -> None:
    obj = json.loads(conteudo)
    if not isinstance(obj, dict) or not obj.get("results"):
        raise ValueError("Resposta da B3 sem carteira.")


def ler_b3(conteudo: bytes) -> tuple[pd.DataFrame, date | None]:
    obj = json.loads(conteudo)
    data_ref = None
    hd = (obj.get("header") or {}).get("date")
    if hd:
        try:
            data_ref = datetime.strptime(hd, "%d/%m/%y").date()
        except ValueError:
            data_ref = None
    res = obj.get("results") or []
    df = pd.DataFrame(res)
    if df.empty:
        return pd.DataFrame(columns=["ticker_bruto"]), data_ref
    out = pd.DataFrame({
        "ticker_bruto": df["cod"].astype(str).str.strip(),
        "nome": df.get("asset", pd.Series("", index=df.index)).astype(str).str.strip(),
        "peso": pd.to_numeric(df["part"].astype(str).str.replace(".", "", regex=False)
                              .str.replace(",", ".", regex=False), errors="coerce") / 100.0,
        "setor": None, "pais": "Brazil", "classe_ativo": "Equity", "bolsa": "XBSP",
        "valor_mercado": None, "valor_nocional": None, "sedol": None,
    })
    return out, data_ref


def yahoo_de(ticker: str, bolsa: str | None) -> str:
    """Ticker Yahoo provável a partir do ticker bruto e da bolsa do arquivo."""
    t = str(ticker).strip().replace("*", "")
    b = str(bolsa or "").strip()
    if b in _ISHARES_BOLSA:
        suf = _ISHARES_BOLSA[b]
        if suf == ".SN":
            t = t.replace(".", "-")
        return f"{t}{suf}"
    partes = t.split(" ")
    if len(partes) == 2 and partes[1] in _BBG_BOLSA:
        base, suf = partes[0], _BBG_BOLSA[partes[1]]
        if suf == ".SN" and len(base) > 1 and base[-1] in "AB" and "-" not in base and \
                base.upper() in {"SQMB", "ANDINAB", "ANDINAA", "CCU", "EMBONORB"}:
            base = base[:-1] + "-" + base[-1]
        return f"{base}{suf}"
    if b == "XBSP" or re.fullmatch(r"[A-Z]{4}\d{1,2}", t):
        return f"{t}.SA"
    return t.replace(" ", "-").replace(".", "-")


def mapear(df: pd.DataFrame, etf: str, fonte: str, linhas_universo: pd.DataFrame | None,
           mapa: pd.DataFrame | None) -> pd.DataFrame:
    """Preenche ``yahoo_ticker`` e ``issuer_id`` (mapa curado > regra pela bolsa)."""
    out = df.copy()
    out["yahoo_ticker"] = [yahoo_de(t, b) for t, b in zip(out["ticker_bruto"],
                                                           out.get("bolsa", ""), strict=False)]
    iid: dict[str, str] = {}
    if linhas_universo is not None and not linhas_universo.empty:
        iid = {str(k).upper(): str(v) for k, v in linhas_universo["issuer_id"].items()}
    out["issuer_id"] = out["yahoo_ticker"].str.upper().map(iid)
    if mapa is not None and not mapa.empty:
        m = mapa.copy()
        m.columns = [c.strip() for c in m.columns]
        m = m[(m.get("etf", etf).astype(str).str.upper() == etf.upper())
              | (m.get("etf", "").astype(str) == "")]
        if "fonte" in m.columns:
            m = m[(m["fonte"].astype(str).str.upper() == fonte) | (m["fonte"].astype(str) == "")]
        por_ticker = {str(r["ticker_bruto"]).strip().upper(): r for _, r in m.iterrows()
                      if str(r.get("ticker_bruto", "")).strip()}
        for i, t in out["ticker_bruto"].items():
            r = por_ticker.get(str(t).strip().upper())
            if r is None:
                continue
            if str(r.get("yahoo_ticker", "")).strip():
                out.at[i, "yahoo_ticker"] = str(r["yahoo_ticker"]).strip()
            v = str(r.get("issuer_id", "")).strip()
            out.at[i, "issuer_id"] = v or None
    out["mapeamento"] = np.where(out["issuer_id"].notna(), "ticker", None)
    if mapa is not None and not mapa.empty:
        out.loc[out["ticker_bruto"].str.strip().str.upper().isin(
            {str(t).strip().upper() for t in mapa.get("ticker_bruto", [])}), "mapeamento"] = "curado"
    if linhas_universo is not None and not linhas_universo.empty and \
            "issuer_name" in linhas_universo.columns:
        _por_nome(out, linhas_universo)
    out["issuer_id"] = out["issuer_id"].where(out["issuer_id"].notna(), None)
    return out


_STOP = frozenset({"sa", "s", "a", "de", "cv", "sab", "sa.b", "the", "inc", "corp", "co",
                   "ltd", "plc", "nv", "adr", "ads", "sponsored", "spon", "rep", "repr",
                   "representing", "one", "ord", "pref", "pfd", "class", "cl", "series",
                   "serie", "on", "pn", "unit", "units", "cpo", "ubd", "ubl", "holding",
                   "holdings", "group", "grupo", "cia", "companhia", "compania", "empresas",
                   "y", "e", "and", "&", "del", "do", "da", "dos", "das", "brasil", "brazil",
                   "mexico", "chile", "peru", "colombia", "argentina", "financiero",
                   "financial", "participacoes", "part", "ns", "nm", "n1", "n2"})


def _tokens(nome: str) -> frozenset[str]:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(nome))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return frozenset(w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 2 and w not in _STOP)


def _contem(tu: frozenset[str], tk: frozenset[str]) -> bool:
    """Todo termo do nome do emissor aparece no nome da posição (igual, ou como prefixo de
    um termo da posição quando tem 4+ letras: "sura" ⊂ "suramericana")."""
    return all(any(w == t or (len(t) >= 4 and w.startswith(t)) for w in tk) for t in tu)


def _raiz_ticker(t: object) -> str:
    """Raiz do ticker bruto sem a bolsa e sem o prefixo de preferenciais colombianas (PF)."""
    base = str(t).strip().upper().split(" ")[0]
    return re.sub(r"^PF(?=[A-Z]{4})", "", base)


def _mesmo_emissor(tickers: list[object], nomes: list[str]) -> bool:
    """Posições que apontam para o mesmo emissor são classes dele (ordinária e preferencial):
    mesmo conjunto de termos no nome ou tickers com a mesma raiz (4+ letras em comum)."""
    toks = {_tokens(n) for n in nomes}
    if len(toks) == 1:
        return True
    raizes = [_raiz_ticker(t) for t in tickers]
    return all(len(os.path.commonprefix([raizes[0], r])) >= 4 for r in raizes[1:])


def _por_nome(out: pd.DataFrame, linhas: pd.DataFrame) -> None:
    """Fallback conservador por nome (correspondência ÚNICA nos dois sentidos) para ações
    sem ``issuer_id``; marcado ``mapeamento = 'nome'`` para conferência no mapa curado.
    Várias posições no mesmo emissor só quando são classes dele (ver :func:`_mesmo_emissor`)."""
    nomes = (linhas.drop_duplicates("issuer_id").set_index("issuer_id")["issuer_name"]
             .map(_tokens))
    nomes = nomes[nomes.map(len) > 0]
    alvo = out["issuer_id"].isna() & out["classe_ativo"].fillna("Equity").str.lower().eq(
        "equity")
    escolhas: dict[int, str] = {}
    for i in out.index[alvo]:
        tk = _tokens(out.at[i, "nome"])
        if not tk:
            continue
        hits = [iid for iid, tu in nomes.items() if tu <= tk or (tk <= tu and len(tk) >= 2)]
        if len(hits) == 1:
            escolhas[i] = hits[0]
    ja = set(out["issuer_id"].dropna())
    por_emissor: dict[str, list[int]] = {}
    for i, iid in escolhas.items():
        por_emissor.setdefault(iid, []).append(i)
    for iid, idx in por_emissor.items():
        if len(idx) == 1 or iid in ja or _mesmo_emissor(
                [out.at[i, "ticker_bruto"] for i in idx], [out.at[i, "nome"] for i in idx]):
            for i in idx:
                out.at[i, "issuer_id"] = iid
                out.at[i, "mapeamento"] = "nome"
    # classe irmã de uma posição já mapeada no MESMO ETF (ticker com a mesma raiz) cujo nome
    # abrevia o do emissor (ex.: "GRUPO DE INV SURAMERICANA" ↔ "Grupo Sura")
    mapeadas = out[out["issuer_id"].notna()]
    for i in out.index[out["issuer_id"].isna() & alvo]:
        tk = _tokens(out.at[i, "nome"])
        raiz = _raiz_ticker(out.at[i, "ticker_bruto"])
        cands = {str(r.issuer_id) for r in mapeadas.itertuples()
                 if len(os.path.commonprefix([raiz, _raiz_ticker(r.ticker_bruto)])) >= 4
                 and str(r.issuer_id) in nomes.index and _contem(nomes[str(r.issuer_id)], tk)}
        if len(cands) == 1:
            out.at[i, "issuer_id"] = cands.pop()
            out.at[i, "mapeamento"] = "nome"


def carteira(etf: str) -> tuple[str, str]:
    """``(fonte, tipo)`` do arquivo de carteira do ETF."""
    e = etf.upper()
    if e in ISHARES:
        return "ISHARES", "ishares"
    if e in GLOBALX:
        return "GLOBALX", "globalx"
    if e in B3_INDICE:
        return "B3", "b3"
    raise KeyError(f"ETF sem fonte pública de carteira configurada: {etf}")


def ler_mapa(caminho) -> pd.DataFrame | None:
    try:
        return pd.read_csv(caminho, dtype=str, keep_default_na=False)
    except (FileNotFoundError, OSError, ValueError):
        return None


def resumo_mapeamento(df: pd.DataFrame) -> Mapping[str, float]:
    eq = df[df["classe_ativo"].fillna("Equity").str.lower().eq("equity")]
    total = float(eq["peso"].sum())
    mapeado = float(eq.loc[eq["issuer_id"].notna(), "peso"].sum())
    return {"peso_acoes": total, "peso_mapeado": mapeado,
            "cobertura": mapeado / total if total > 0 else float("nan")}


__all__ = [
    "B3_INDICE", "COLUNAS", "ETFS", "GLOBALX", "ISHARES", "carteira", "ler_b3", "ler_globalx",
    "ler_ishares", "ler_mapa", "mapear", "resumo_mapeamento", "url_b3", "url_globalx",
    "url_ishares", "validar_b3", "validar_csv_ishares", "yahoo_de",
]
