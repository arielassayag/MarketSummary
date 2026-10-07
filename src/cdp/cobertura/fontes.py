"""Acesso aos dados públicos da cobertura (contrato compartilhado com :mod:`cdp.data.publico`).

O motor nunca busca dados por conta própria: recebe um :class:`DadosPublicos` com as tabelas do
contrato (demonstrativos CVM/SEC, consenso público Yahoo Finance, dividendos, composição de ETFs,
eventos corporativos, taxas públicas e free float), todas point-in-time (``data_publicacao <=
as_of``). Mercado sintético ⇒ tabelas sintéticas (:mod:`cdp.cobertura.sintetico`, fonte
``SIMULADO``); mercado real ⇒ funções da camada pública (A1), em modo ``offline`` lendo só o
arquivo de dados públicos arquivados (``<raiz>/publico/...``).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..market import MarketData

COLS_DEMONSTRATIVOS = ["issuer_id", "demonstrativo", "freq", "period_end", "item", "value",
                       "currency", "escala", "consolidado", "fonte", "url", "documento",
                       "data_publicacao", "sha256"]
COLS_CONSENSO = ["ticker", "eps_fy1", "eps_fy2", "receita_fy1", "receita_fy2", "n_analistas_eps",
                 "alvo_medio", "alvo_mediano", "alvo_alto", "alvo_baixo", "n_analistas_alvo",
                 "recomendacao_media", "fonte", "data_coleta", "moeda_cotacao", "moeda_estimativas"]
COLS_DIVIDENDOS = ["ticker", "data_ex", "valor_por_acao", "moeda", "fonte"]
COLS_ETF = ["ticker_bruto", "nome", "peso", "setor", "pais", "issuer_id", "fonte", "url",
            "data_ref", "sha256"]
COLS_EVENTOS = ["issuer_id", "data", "tipo", "estimada", "fonte", "url"]
COLS_TAXAS = ["serie", "data", "valor", "fonte"]
COLS_FLOAT = ["issuer_id", "free_float_pct", "fonte", "data_ref"]
COLS_ALERTAS = ["issuer_id", "tipo", "texto", "data", "item"]
"""Alertas da camada pública (``attrs['qa']`` e ``attrs['moeda_trocada']`` dos demonstrativos)."""
COLS_CAPITAL = ["issuer_id", "cnpj", "data_ref", "versao", "data_publicacao", "tipo_capital",
                "data_aprovacao", "qtd_ordinarias", "qtd_preferenciais", "qtd_total", "url", "sha256"]
"""Contagem oficial de ações (Formulário de Referência da CVM, capital social)."""


class FontePublicaIndisponivel(RuntimeError):
    """A camada de dados públicos (``cdp.data.publico``) não está disponível nesta instalação."""


@dataclass(frozen=True)
class DadosPublicos:
    """Tabelas públicas de uma execução (já filtradas point-in-time)."""

    demonstrativos: pd.DataFrame
    consenso: pd.DataFrame
    dividendos: pd.DataFrame
    eventos: pd.DataFrame
    taxas: pd.DataFrame
    free_float: pd.DataFrame
    etfs: dict[str, pd.DataFrame | None] = field(default_factory=dict)
    origem: str = "PUBLICO"          # "PUBLICO" | "SIMULADO"
    raiz: str | None = None
    alertas: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=COLS_ALERTAS))
    capital_oficial: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=COLS_CAPITAL))

    resultado_evidencias: pd.DataFrame = field(default_factory=pd.DataFrame)
    corte_temporal: dict[str, str] | None = None

    def tabelas(self) -> dict[str, pd.DataFrame]:
        out = {"demonstrativos": self.demonstrativos, "consenso": self.consenso,
               "dividendos": self.dividendos, "eventos": self.eventos, "taxas": self.taxas,
               "free_float": self.free_float}
        if not self.alertas.empty:
            out["alertas_fonte"] = self.alertas
        if not self.capital_oficial.empty:
            out["capital_oficial"] = self.capital_oficial
        if not self.resultado_evidencias.empty:
            out["resultado_evidencias"] = self.resultado_evidencias
        if self.corte_temporal is not None:
            out["corte_temporal"] = pd.DataFrame([self.corte_temporal])
        for etf, df in sorted(self.etfs.items()):
            if df is not None:
                out[f"etf_{_slug(etf)}"] = df
        if self.corte_temporal is not None:
            # A precisão da custódia é parte do contrato .8. O serializador histórico
            # continua reduzindo datetime64 a data civil; aqui os carimbos viram
            # texto ISO antes dele, sem atribuir hora/fuso a datas indeterminadas.
            out = {nome: _capturas_iso(df) for nome, df in out.items()}
        return out


def _slug(t: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in t.upper())


def _capturas_iso(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in d.columns:
        if str(c).startswith("data_coleta") or c == "first_capture":
            d[c] = d[c].map(lambda x: None if pd.isna(x) else
                           x.isoformat() if hasattr(x, "isoformat") else x)
    return d


def _garantir(df: pd.DataFrame | None, cols: list[str]) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame(columns=cols)
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan
    return df


def csv_canonico(df: pd.DataFrame) -> str:
    """CSV determinístico (colunas e linhas ordenadas; floats com 10 algarismos significativos)."""
    if df is None or df.empty:
        return ",".join(sorted(df.columns) if df is not None else []) + "\n"
    d = df.copy()
    d = d[sorted(d.columns, key=str)]
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.strftime("%Y-%m-%d")
        elif d[c].dtype == object:
            d[c] = d[c].map(lambda x: x.isoformat() if hasattr(x, "isoformat") else x)
    d = d.sort_values(list(d.columns), key=lambda s: s.astype(str), kind="mergesort")
    buf = io.StringIO()
    d.to_csv(buf, index=False, float_format="%.10g", lineterminator="\n")
    return buf.getvalue()


def sha256_tabela(df: pd.DataFrame) -> str:
    return hashlib.sha256(csv_canonico(df).encode("utf-8")).hexdigest()


def _pit(df: pd.DataFrame, col: str, as_of: date) -> pd.DataFrame:
    """Mantém só linhas publicadas até ``as_of`` (datas ausentes são mantidas e sinalizadas
    adiante como não point-in-time)."""
    if df.empty or col not in df.columns:
        return df
    d = pd.to_datetime(df[col], errors="coerce")
    return df.loc[d.isna() | (d <= pd.Timestamp(as_of))].copy()


_DATA_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def alertas_de_attrs(attrs: dict | None) -> pd.DataFrame:
    """``attrs`` dos demonstrativos (camada A1) → tabela de alertas por emissor.

    ``qa``: textos ``"<emissor>: <alerta>"`` (saltos de magnitude, complementos descartados, capex
    com classificação a conferir, contagens ausentes); ``moeda_trocada``: mudança da moeda de
    apresentação (``{moeda, anteriores, desde, fatos_descartados}``). A data do alerta é a mais
    recente citada no texto; o item, o primeiro item canônico citado."""
    rows: list[dict] = []
    attrs = attrs or {}
    for s in attrs.get("qa") or []:
        texto = str(s)
        if ": " not in texto:
            continue
        iid, corpo = texto.split(": ", 1)
        datas = _DATA_RE.findall(corpo)
        item = next((w for w in re.findall(r"[a-z_]+", corpo) if w in ITENS_ALERTA), None)
        if item is None and corpo.startswith(("ações", "acoes")):
            item = "acoes_em_circulacao"
        tipo = ("salto" if "salto de" in corpo else "descartado" if "descartad" in corpo
                else "capex" if "saídas de investimento" in corpo else "moeda" if "moeda de apresenta" in corpo
                else "contagem" if "ações" in corpo else "outro")
        rows.append({"issuer_id": iid.strip(), "tipo": tipo, "texto": corpo.strip(),
                     "data": max(datas) if datas else None, "item": item})
    for iid, tr in sorted((attrs.get("moeda_trocada") or {}).items()):
        rows.append({"issuer_id": str(iid), "tipo": "moeda_trocada",
                     "texto": (f"moeda de apresentação {', '.join(tr.get('anteriores') or [])} → {tr.get('moeda')} "
                               f"desde {tr.get('desde')} ({tr.get('fatos_descartados')} fatos na moeda anterior "
                               "fora do histórico)"),
                     "data": str(tr.get("desde")) if tr.get("desde") else None, "item": None})
    return pd.DataFrame(rows, columns=COLS_ALERTAS).drop_duplicates().reset_index(drop=True)


ITENS_ALERTA = ("receita", "ebit", "ebitda", "d_a", "capex", "cfo", "fcf", "caixa", "aplicacoes_cp",
                "divida_bruta", "arrendamentos", "patrimonio_controladores", "patrimonio_liquido",
                "lucro_liquido_controladores", "lucro_liquido", "participacao_minoritarios", "carteira_credito",
                "acoes_em_circulacao", "acoes_emitidas", "dividendos_pagos", "ativo_total")


TIPOS_CAPITAL = ("Capital Integralizado", "Capital Emitido", "Capital Subscrito")


def capital_fre(conteudo: bytes, ano: int, cnpjs: set[str] | None = None) -> pd.DataFrame:
    """Capital social do FRE (CVM): uma linha por (CNPJ, data de referência, versão, tipo), com a
    quantidade total de ações e a data de recebimento da versão."""
    import zipfile

    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        nomes = zf.namelist()
        n_cap = next((n for n in nomes if n.endswith(f"capital_social_{ano}.csv")), None)
        n_idx = next((n for n in nomes if n.endswith(f"fre_cia_aberta_{ano}.csv")), None)
        if n_cap is None or n_idx is None:
            return pd.DataFrame(columns=COLS_CAPITAL)
        cap = pd.read_csv(io.BytesIO(zf.read(n_cap)), sep=";", encoding="latin1", dtype=str)
        idx = pd.read_csv(io.BytesIO(zf.read(n_idx)), sep=";", encoding="latin1", dtype=str)
    cap = cap[cap["Tipo_Capital"].isin(TIPOS_CAPITAL)].copy()
    cap["cnpj"] = cap["CNPJ_Companhia"].astype(str).str.strip()
    if cnpjs is not None:
        cap = cap[cap["cnpj"].isin(cnpjs)]
    idx = idx.rename(columns={"ID_DOC": "ID_Documento", "DT_RECEB": "data_publicacao", "LINK_DOC": "url"})
    cap = cap.merge(idx[["ID_Documento", "data_publicacao", "url"]], on="ID_Documento", how="left")
    out = pd.DataFrame({
        "cnpj": cap["cnpj"], "data_ref": cap["Data_Referencia"], "versao": pd.to_numeric(cap["Versao"], errors="coerce"),
        "data_publicacao": cap["data_publicacao"], "tipo_capital": cap["Tipo_Capital"],
        "data_aprovacao": cap["Data_Autorizacao_Aprovacao"],
        "qtd_ordinarias": pd.to_numeric(cap["Quantidade_Acoes_Ordinarias"], errors="coerce"),
        "qtd_preferenciais": pd.to_numeric(cap["Quantidade_Acoes_Preferenciais"], errors="coerce"),
        "qtd_total": pd.to_numeric(cap["Quantidade_Total_Acoes"], errors="coerce"), "url": cap["url"]})
    return out[out["qtd_total"] > 0].reset_index(drop=True)


def capital_oficial(issuer_ids: Sequence[str], as_of: date, raiz: Path | None) -> pd.DataFrame:
    """Contagem oficial de ações dos emissores brasileiros pelo FRE arquivado pela camada pública
    (sem rede): a versão mais recente recebida até ``as_of``; entre os tipos de capital, o maior
    total (integralizado, emitido ou subscrito)."""
    try:
        from ..data import publico  # type: ignore[attr-defined]
        from ..data.publico_arquivo import Arquivo  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - depende da camada A1
        return pd.DataFrame(columns=COLS_CAPITAL)
    try:
        mestre = publico.mestre_publico(as_of, offline=True, root=raiz)
    except Exception:  # noqa: BLE001 - sem cadastro arquivado ⇒ sem contagem oficial
        return pd.DataFrame(columns=COLS_CAPITAL)
    cnpj_de = {str(i): str(mestre.loc[i, "cnpj"]) for i in issuer_ids
               if i in mestre.index and isinstance(mestre.loc[i, "cnpj"], str) and mestre.loc[i, "cnpj"]}
    if not cnpj_de:
        return pd.DataFrame(columns=COLS_CAPITAL)
    arq = Arquivo(raiz, offline=True)
    partes = []
    for ano in (as_of.year - 1, as_of.year):
        reg = arq.buscar(f"CVM/FRE/fre_cia_aberta_{ano}.zip", ate=as_of)
        if reg is None:
            continue
        f = capital_fre(arq.ler(reg), ano, set(cnpj_de.values()))
        f["sha256"] = reg.sha256
        partes.append(f)
    if not partes:
        return pd.DataFrame(columns=COLS_CAPITAL)
    fre = pd.concat(partes, ignore_index=True)
    fre = fre[pd.to_datetime(fre["data_publicacao"], errors="coerce") <= pd.Timestamp(as_of)]
    fre = fre.sort_values(["cnpj", "data_ref", "versao", "qtd_total"], kind="mergesort")
    ult = fre.groupby("cnpj").tail(1).set_index("cnpj")
    rows = []
    for iid, c in sorted(cnpj_de.items()):
        if c in ult.index:
            r = ult.loc[c]
            rows.append({"issuer_id": iid, "cnpj": c, **{k: r[k] for k in COLS_CAPITAL if k in r.index
                                                         and k not in ("issuer_id", "cnpj")}})
    return pd.DataFrame(rows, columns=COLS_CAPITAL)


# ============================================================ contas suplementares da CVM

ITENS_SUPLEMENTARES = ("arrendamentos_pagos", "receita_construcao", "d_a_dfc", "variacao_capital_giro_operacional")
"""Contas lidas pela cobertura diretamente dos ZIPs DFP/ITR arquivados (emissores com CNPJ):

- ``arrendamentos_pagos``: −Σ das linhas de financiamento ``6.03.xx`` (em qualquer nível) da DFC com "arrendamento" na
  descrição e valor ≤ 0, exceto juros, captações e recebimentos. A rubrica genérica não certifica
  principal isolado; fica somente na reprodução da política histórica, nunca como investimento
  na política de capitalização de arrendamentos;
- ``receita_construcao``: Σ das linhas ``7.01.xx`` (em qualquer nível) da DVA com "constru" e "receit" (ou "ativos
  próprios") na descrição — a receita de construção da infraestrutura de concessão (ICPC 01), que a
  receita da DRE inclui e o consenso de receita não.
- ``d_a_dfc``: restituição de depreciação, amortização e exaustão explicitamente publicada na DFC;
- ``variacao_capital_giro_operacional``: rubrica explicitamente de capital de giro, com utilização
  de caixa positiva. Variações genéricas de ativos/passivos e diferenças de balanços não a substituem.

Exercícios pela DFP; 12 meses pela identidade ``exercício + acumulado do ano − acumulado do mesmo
período do ano anterior`` (ITR); conta não encontrada ⇒ item ausente (nunca zero)."""

_RE_ARR = re.compile(r"arrendament")
_RE_ARR_FORA = re.compile(r"juros|captac|recebid|recebiment|ingresso|sublocac|emprestimo|financiamento")
_RE_CONSTR = re.compile(r"constru")
_RE_CONSTR_REC = re.compile(r"receit|ativos? propri")
_RE_CONSTR_FORA = re.compile(r"custo|gasto|insumo|materia|pessoal|servicos de terceiros")
_RE_DA_DFC = re.compile(r"depreciac|amortizac|exaust|deplec")
_RE_DA_FORA = re.compile(r"juros|financ|divida|emprest|arrendamento.*pag|principal|impairment|perda.*recuper")
_RE_GIRO = re.compile(r"variac.*capital de giro|capital de giro.*variac")


def _tabelas_cvm(conteudo: bytes, doc: str, ano: int, cnpjs: set[str]) -> dict[str, pd.DataFrame]:
    """Índice e DFC/DVA (consolidado e individual, ``ORDEM_EXERC = ÚLTIMO``) de um ZIP DFP/ITR."""
    import zipfile

    from ..data.publico_cvm import USECOLS  # type: ignore[attr-defined]
    from ..data.security_master import normalize_text, read_cvm_csv  # type: ignore[attr-defined]

    pref = f"{doc.lower()}_cia_aberta_"
    out: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        nomes = {n.lower(): n for n in zf.namelist()}
        n_idx = nomes.get(f"{pref}{ano}.csv")
        idx = read_cvm_csv(zf.read(n_idx)) if n_idx else pd.DataFrame(
            columns=["CNPJ_CIA", "DT_REFER", "VERSAO", "DT_RECEB", "LINK_DOC"])
        out["index"] = idx[idx["CNPJ_CIA"].astype(str).str.strip().isin(cnpjs)].reset_index(drop=True)
        for tab in ("DFC_MI", "DFC_MD", "DVA"):
            cols = USECOLS[tab]
            for kind in ("con", "ind"):
                nome = nomes.get(f"{pref}{tab}_{kind}_{ano}.csv".lower())
                if nome is None:
                    out[f"{tab}_{kind}"] = pd.DataFrame(columns=cols)
                    continue
                df = read_cvm_csv(zf.read(nome), usecols=lambda c, cols=cols: c in cols)
                for c in cols:
                    if c not in df.columns:
                        df[c] = pd.NA
                df = df[df["CNPJ_CIA"].astype(str).str.strip().isin(cnpjs)]
                ordem = df["ORDEM_EXERC"].fillna("").map(normalize_text)
                out[f"{tab}_{kind}"] = df.loc[ordem == "ultimo", cols].reset_index(drop=True)
    return out


def _sem_ancestral(df: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """Remove as linhas cuja conta-mãe também foi selecionada (sem dupla contagem pai/filha; a
    posição da conta muda entre documentos da mesma companhia)."""
    if df.empty:
        return df
    keep = []
    for _, g in df.groupby(key, sort=False, dropna=False):
        cds = set(g["cd"])
        for i, cd in zip(g.index, g["cd"], strict=True):
            partes = cd.split(".")
            if not any(".".join(partes[:k]) in cds for k in range(1, len(partes))):
                keep.append(i)
    return df.loc[sorted(keep)]


def _fatos_suplementares(tabs: dict[str, pd.DataFrame], doc: str) -> pd.DataFrame:
    """Linhas ``(cnpj, versao, dt_refer, dt_ini, dt_fim, item, value, consolidado, recebido, url)``."""
    from ..data.fundamentals_pit import _prepare_statement  # type: ignore[attr-defined]

    idx = tabs.get("index", pd.DataFrame())
    cols = ["cnpj", "dt_refer", "versao", "dt_ini", "dt_fim", "item", "value", "currency", "consolidado",
            "recebido", "url", "doc"]
    if idx is None or idx.empty:
        return pd.DataFrame(columns=cols)
    rec = pd.DataFrame({
        "cnpj": idx["CNPJ_CIA"].astype(str).str.strip(),
        "dt_refer": pd.to_datetime(idx["DT_REFER"], errors="coerce"),
        "versao": pd.to_numeric(idx["VERSAO"], errors="coerce"),
        "recebido": pd.to_datetime(idx["DT_RECEB"], errors="coerce"),
        "url": idx["LINK_DOC"].astype(str) if "LINK_DOC" in idx.columns else None,
    }).dropna(subset=["dt_refer", "versao", "recebido"]).drop_duplicates(["cnpj", "dt_refer", "versao"])
    key = ["cnpj", "dt_refer", "versao", "kind", "dt_ini", "dt_fim"]
    partes = []
    dfc = pd.concat([_prepare_statement(tabs, "DFC_MI"), _prepare_statement(tabs, "DFC_MD")], ignore_index=True)
    if not dfc.empty:
        d = dfc.dropna(subset=["dt_ini"])
        arr = _sem_ancestral(d[d["cd"].str.match(r"^6\.03(\.\d{2})+$") & d["ds"].str.contains(_RE_ARR)
                               & ~d["ds"].str.contains(_RE_ARR_FORA) & (d["value"] <= 0)], key)
        if not arr.empty:
            g = arr.groupby(key, as_index=False, dropna=False).agg(value=("value", "sum"),
                                                                    currency=("currency", "first"))
            g["value"] = -g["value"]
            partes.append(g.assign(item="arrendamentos_pagos"))
        da = _sem_ancestral(d[d["cd"].str.match(r"^6\.01(\.\d{2})+$")
                              & d["ds"].str.contains(_RE_DA_DFC) & ~d["ds"].str.contains(_RE_DA_FORA)
                              & (d["value"] >= 0)], key)
        if not da.empty:
            g = da.groupby(key, as_index=False, dropna=False).agg(value=("value", "sum"),
                                                                   currency=("currency", "first"))
            partes.append(g.assign(item="d_a_dfc"))
        # Só a rubrica explicitamente de capital de giro; uma linha genérica de variações de
        # ativos/passivos pode incluir dívida, pensões e provisões de desmantelamento.
        giro = _sem_ancestral(d[d["cd"].str.match(r"^6\.01(\.\d{2})+$")
                                & d["ds"].str.contains(_RE_GIRO)], key)
        if not giro.empty:
            g = giro.groupby(key, as_index=False, dropna=False).agg(value=("value", "sum"),
                                                                     currency=("currency", "first"))
            g["value"] = -g["value"]  # contrato: utilização de caixa é investimento positivo
            partes.append(g.assign(item="variacao_capital_giro_operacional"))
    dva = _prepare_statement(tabs, "DVA")
    if not dva.empty:
        d = dva.dropna(subset=["dt_ini"])
        con = _sem_ancestral(d[d["cd"].str.match(r"^7\.01(\.\d{2})+$") & d["ds"].str.contains(_RE_CONSTR)
                               & d["ds"].str.contains(_RE_CONSTR_REC) & ~d["ds"].str.contains(_RE_CONSTR_FORA)
                               & (d["value"] >= 0)], key)
        if not con.empty:
            g = con.groupby(key, as_index=False, dropna=False).agg(value=("value", "sum"),
                                                                    currency=("currency", "first"))
            partes.append(g.assign(item="receita_construcao"))
    if not partes:
        return pd.DataFrame(columns=cols)
    f = pd.concat(partes, ignore_index=True)
    f["versao"] = pd.to_numeric(f["versao"], errors="coerce")
    f = f.merge(rec, on=["cnpj", "dt_refer", "versao"], how="inner")
    f["consolidado"] = f["kind"].astype(str).eq("con")
    f["doc"] = doc.upper()
    return f[cols]


def contas_suplementares_cvm(issuer_ids: Sequence[str], as_of: date, raiz: Path | None) -> pd.DataFrame:
    """Itens ``ITENS_SUPLEMENTARES`` (exercícios e 12 meses) dos emissores com CNPJ, no formato dos
    demonstrativos (``COLS_DEMONSTRATIVOS``), lidos dos ZIPs DFP/ITR arquivados pela camada pública
    (sem rede), point-in-time (versão mais recente recebida até ``as_of``), consolidado quando há."""
    vazio = pd.DataFrame(columns=COLS_DEMONSTRATIVOS)
    try:
        from ..data import publico  # type: ignore[attr-defined]
        from ..data.publico_arquivo import Arquivo  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - depende da camada A1
        return vazio
    try:
        mestre = publico.mestre_publico(as_of, offline=True, root=raiz)
    except Exception:  # noqa: BLE001 - sem cadastro arquivado ⇒ sem contas suplementares
        return vazio
    cnpj_de = {str(i): str(mestre.loc[i, "cnpj"]) for i in issuer_ids
               if i in mestre.index and isinstance(mestre.loc[i, "cnpj"], str) and mestre.loc[i, "cnpj"]}
    if not cnpj_de:
        return vazio
    cnpjs = set(cnpj_de.values())
    arq = Arquivo(raiz, offline=True)
    partes = []
    for doc, anos in (("DFP", range(as_of.year - 4, as_of.year + 1)), ("ITR", range(as_of.year - 2, as_of.year + 1))):
        for ano in anos:
            reg = arq.buscar(f"CVM/{doc}/{doc.lower()}_cia_aberta_{ano}.zip", ate=as_of)
            if reg is None:
                continue
            try:
                f = _fatos_suplementares(_tabelas_cvm(arq.ler(reg), doc, ano, cnpjs), doc)
            except Exception:  # noqa: BLE001 - ZIP com layout inesperado: itens ausentes
                continue
            f["sha256"] = reg.sha256
            f["data_coleta"] = pd.Timestamp(reg.data_coleta)
            partes.append(f)
    if not partes:
        return vazio
    f = pd.concat(partes, ignore_index=True)
    f = f[f["recebido"] <= pd.Timestamp(as_of)]
    # versão mais recente por documento; consolidado quando o documento tem as duas bases
    f = f.sort_values(["cnpj", "item", "dt_fim", "dt_ini", "consolidado", "recebido", "versao"], kind="mergesort")
    f = f.drop_duplicates(["cnpj", "item", "doc", "dt_ini", "dt_fim"], keep="last")
    rows: list[dict] = []
    for (cnpj, item), g in f.groupby(["cnpj", "item"], sort=True):
        dur = (g["dt_fim"] - g["dt_ini"]).dt.days
        anual = g[(g["doc"] == "DFP") & dur.between(350, 380)].drop_duplicates("dt_fim", keep="last").set_index("dt_fim")
        ytd = g[(g["doc"] == "ITR") & (g["dt_ini"].dt.month == 1) & (g["dt_ini"].dt.day == 1)].drop_duplicates(
            "dt_fim", keep="last").set_index("dt_fim")
        tab = "DVA" if item == "receita_construcao" else "DFC"
        ultimo_anual = None
        for e, r in anual.iterrows():
            ultimo_anual = {"cnpj": cnpj, "item": item, "freq": "A", "period_end": e, "value": float(r["value"]),
                            "consolidado": bool(r["consolidado"]), "recebido": r["recebido"], "url": r["url"],
                               "sha256": r["sha256"], "currency": r["currency"], "data_coleta": r["data_coleta"],
                            "documento": f"DFP {e.date()} v{int(r['versao'])} (CVM, contas da {tab})"}
            rows.append(ultimo_anual)
        fins = sorted(set(anual.index) | set(ytd.index))
        if not fins:
            continue
        e = fins[-1]
        if e in anual.index:
            rows.append({**ultimo_anual, "freq": "TTM"} if ultimo_anual and ultimo_anual["period_end"] == e else {})
            continue
        fy = pd.Timestamp(year=e.year - 1, month=12, day=31)
        prev = pd.Timestamp(e) - pd.DateOffset(years=1)
        prev = prev + pd.offsets.MonthEnd(0)
        if fy not in anual.index or prev not in ytd.index:
            continue
        a, y, yp = anual.loc[fy], ytd.loc[e], ytd.loc[prev]
        moedas = {str(r["currency"]) for r in (a, y, yp)}
        bases = {bool(r["consolidado"]) for r in (a, y, yp)}
        if len(moedas) != 1 or not re.fullmatch(r"[A-Z]{3}", next(iter(moedas))) or len(bases) != 1:
            continue  # uma soma entre moedas/bases contábeis diferentes não é TTM observado
        componentes = json.dumps([{"item": item, "freq": freq, "period_end": fim.date().isoformat(),
                        "valor": float(r["value"]), "coeficiente": sinal,
                        "fonte": {"fonte": "CVM", "url": r["url"], "sha256": r["sha256"],
                                  "data_publicacao": pd.Timestamp(r["recebido"]).date().isoformat(),
                                  "data_coleta": str(r["data_coleta"]), "documento": f"{doc} {fim.date()} v{int(r['versao'])}"}}
                        for r, fim, freq, sinal, doc in [(a, fy, "A", 1, "DFP"), (y, e, "YTD", 1, "ITR"),
                                                       (yp, prev, "YTD", -1, "ITR")]], ensure_ascii=False)
        rows.append({"cnpj": cnpj, "item": item, "freq": "TTM", "period_end": e,
                     "value": float(a["value"]) + float(y["value"]) - float(yp["value"]),
                     "consolidado": bool(a["consolidado"] and y["consolidado"] and yp["consolidado"]),
                     "recebido": max(a["recebido"], y["recebido"], yp["recebido"]), "url": y["url"], "sha256": y["sha256"],
                     "currency": y["currency"], "data_coleta": y["data_coleta"],
                     "componentes_fluxo": componentes,
                     "documento": (f"ITR {e.date()} v{int(y['versao'])} + DFP {fy.date()} − ITR {prev.date()} (CVM, "
                                   f"12 meses pela identidade exercício + acumulado do ano − acumulado do ano anterior)")})
    rows = [r for r in rows if r]
    if not rows:
        return vazio
    x = pd.DataFrame(rows)
    iss_de: dict[str, list[str]] = {}
    for iid, c in cnpj_de.items():
        iss_de.setdefault(c, []).append(iid)
    x["issuer_id"] = x["cnpj"].map(iss_de)
    x = x.explode("issuer_id")
    out = pd.DataFrame({
        "issuer_id": x["issuer_id"], "demonstrativo": x["item"].map({"arrendamentos_pagos": "DFC",
                                                                     "receita_construcao": "DVA",
                                                                     "d_a_dfc": "DFC",
                                                                     "variacao_capital_giro_operacional": "DFC"}),
        "freq": x["freq"], "period_end": pd.to_datetime(x["period_end"]), "item": x["item"],
        "value": x["value"].astype(float), "currency": x["currency"].fillna("BRL"), "escala": 1,
        "consolidado": x["consolidado"], "fonte": "CVM", "url": x["url"], "documento": x["documento"],
        "data_publicacao": pd.to_datetime(x["recebido"]).dt.date, "sha256": x["sha256"],
        "pit_estimado": False, "nota": None, "data_coleta": x["data_coleta"]})
    if "componentes_fluxo" in x:
        out["componentes_fluxo"] = x["componentes_fluxo"]
    return out.sort_values(["issuer_id", "item", "freq", "period_end"], kind="mergesort").reset_index(drop=True)


def incorporar_resultados(dem: pd.DataFrame, primaria: pd.DataFrame, catalogo: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Seleção primária comum à coleta online e ao recálculo das tabelas seladas.

    Preferência por fato/contexto integral, jamais por valor próximo ou nome do emissor.
    Valores de itens não cobertos permanecem reportados nas respectivas fontes.
    """
    from ..data.publico_resultados import hash_obj, texto_json
    if catalogo["catalogo_sha256"] != hash_obj({k: v for k, v in catalogo.items() if k != "catalogo_sha256"}):
        raise ValueError("catálogo de resultados adulterado")
    if not primaria.empty:
        chaves = ["issuer_id", "item", "freq", "period_end"]
        antiga = dem.assign(period_end=pd.to_datetime(dem["period_end"]).dt.strftime("%Y-%m-%d"))
        preferidos = set(map(tuple, primaria[chaves].astype(str).to_numpy()))
        dem = dem.loc[[tuple(x) not in preferidos for x in antiga[chaves].astype(str).to_numpy()]]
        dem = pd.concat([dem, primaria], ignore_index=True)
    tabela = pd.DataFrame([{"schema": catalogo["schema"], "catalogo_sha256": catalogo["catalogo_sha256"],
                           "conhecimento_ate": catalogo["conhecimento_ate"], "catalogo_json": texto_json(catalogo)}])
    return dem, tabela


def _coletar(md: MarketData, as_of: date, issuer_ids: Sequence[str], tickers: Sequence[str],
            etfs: Sequence[str], *, offline: bool = False, raiz: Path | None = None,
            seed: int = 7, params=None, conhecimento_ate: datetime | None = None) -> DadosPublicos:
    """Coleta as tabelas públicas da execução (sintéticas quando o mercado é sintético)."""
    from .temporal import ativo as temporal_ativo
    from .temporal import construir as corte_temporal

    corte = None
    if params is not None and temporal_ativo(params):
        if conhecimento_ate is None:
            raise ValueError("Política temporal exige corte explícito de conhecimento.")
        corte = corte_temporal(md.as_of, conhecimento_ate)
        conhecimento_ate = datetime.fromisoformat(corte["conhecimento_ate"])
        as_of = date.fromisoformat(corte["data_modelo"])
    if md.is_synthetic:
        from .sintetico import dados_sinteticos

        dados = dados_sinteticos(md, as_of, issuer_ids, tickers, etfs, seed=seed)
        return replace(dados, corte_temporal=corte) if corte is not None else dados
    try:
        from ..data import publico  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - depende da camada A1
        raise FontePublicaIndisponivel(
            "camada de dados públicos (cdp.data.publico) indisponível") from exc
    kw = {"offline": offline, "root": raiz}
    dem_bruto = publico.demonstrativos(list(issuer_ids), as_of, **kw)
    alertas = alertas_de_attrs(getattr(dem_bruto, "attrs", None))
    dem = _garantir(dem_bruto, COLS_DEMONSTRATIVOS)
    br = [i for i in issuer_ids if i in md.universe.issuers.index and str(md.universe.issuers.loc[i, "country"]) == "BR"]
    sup = contas_suplementares_cvm(br, as_of, raiz)
    if not sup.empty:
        dem = pd.concat([dem, sup[[c for c in sup.columns if c in dem.columns]]], ignore_index=True)
    resultado_evidencias = pd.DataFrame()
    if params is not None:
        from .resultado import ativo
        if ativo(params):
            from ..data.publico_arquivo import Arquivo
            from ..data.publico_resultados import coletar_resultados
            opcoes_resultado = {"exigir_captura": True} if corte is not None else {}
            primaria, catalogo = coletar_resultados(list(issuer_ids), arquivo=Arquivo(raiz, offline=offline),
                                                   conhecimento_ate=conhecimento_ate, **opcoes_resultado)
            dem, resultado_evidencias = incorporar_resultados(dem, primaria, catalogo)
    con = _garantir(publico.consenso_publico(list(tickers), as_of, **kw), COLS_CONSENSO)
    div = _garantir(publico.dividendos(list(tickers), as_of, **kw), COLS_DIVIDENDOS)
    ini = date(as_of.year - 1, as_of.month, 1)
    fim = date(as_of.year + 1, as_of.month, 28)
    try:  # ``as_of`` limita o calendário ao que se sabia na data (sem look-ahead)
        eve_df = publico.eventos_corporativos(list(issuer_ids), ini, fim, as_of=as_of, **kw)
    except TypeError:
        eve_df = publico.eventos_corporativos(list(issuer_ids), ini, fim, **kw)
    eve = _garantir(eve_df, COLS_EVENTOS)
    tax = _garantir(publico.taxas_publicas(as_of, **kw), COLS_TAXAS)
    ff = _garantir(publico.free_float(list(issuer_ids), as_of, **kw), COLS_FLOAT)
    cap = capital_oficial([i for i in issuer_ids if i in md.universe.issuers.index
                           and str(md.universe.issuers.loc[i, "country"]) == "BR"], as_of, raiz)
    comp: dict[str, pd.DataFrame | None] = {}
    for e in etfs:
        try:
            df = publico.composicao_etf(e, as_of, **kw)
        except Exception:  # composição indisponível na semana ⇒ só top-down
            df = None
        comp[e] = None if df is None else _garantir(df, COLS_ETF)
    return DadosPublicos(
        demonstrativos=_pit(dem, "data_publicacao", as_of), consenso=con,
        dividendos=_pit(div, "data_ex", as_of), eventos=eve, taxas=_pit(tax, "data", as_of),
        free_float=ff, etfs=comp, origem="PUBLICO", raiz=None if raiz is None else str(raiz),
        alertas=alertas, capital_oficial=cap, resultado_evidencias=resultado_evidencias, corte_temporal=corte)


def coletar(md: MarketData, as_of: date, issuer_ids: Sequence[str], tickers: Sequence[str],
            etfs: Sequence[str], *, offline: bool = False, raiz: Path | None = None,
            seed: int = 7, params=None, conhecimento_ate: datetime | None = None) -> DadosPublicos:
    """Política nova sela corte exato em todos os arquivos; ausência conserva seleção legada."""
    from .temporal import ativo as temporal_ativo
    opcoes = dict(offline=offline, raiz=raiz, seed=seed, params=params, conhecimento_ate=conhecimento_ate)
    if params is not None and temporal_ativo(params):
        if conhecimento_ate is None:
            raise ValueError("Coleta temporal exige instante explícito de conhecimento.")
        from ..data.publico_arquivo import corte_de_conhecimento
        with corte_de_conhecimento(conhecimento_ate):
            return _coletar(md, as_of, issuer_ids, tickers, etfs, **opcoes)
    return _coletar(md, as_of, issuer_ids, tickers, etfs, **opcoes)


__all__ = ["COLS_ALERTAS", "COLS_CAPITAL", "ITENS_SUPLEMENTARES", "contas_suplementares_cvm", "COLS_CONSENSO", "COLS_DEMONSTRATIVOS", "COLS_DIVIDENDOS", "COLS_ETF", "COLS_EVENTOS",
           "COLS_FLOAT", "COLS_TAXAS", "DadosPublicos", "FontePublicaIndisponivel", "alertas_de_attrs",
           "capital_fre", "capital_oficial", "coletar",
           "csv_canonico", "sha256_tabela"]
