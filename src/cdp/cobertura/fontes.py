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
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
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

    def tabelas(self) -> dict[str, pd.DataFrame]:
        out = {"demonstrativos": self.demonstrativos, "consenso": self.consenso,
               "dividendos": self.dividendos, "eventos": self.eventos, "taxas": self.taxas,
               "free_float": self.free_float}
        for etf, df in sorted(self.etfs.items()):
            if df is not None:
                out[f"etf_{_slug(etf)}"] = df
        return out


def _slug(t: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in t.upper())


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


def coletar(md: MarketData, as_of: date, issuer_ids: Sequence[str], tickers: Sequence[str],
            etfs: Sequence[str], *, offline: bool = False, raiz: Path | None = None,
            seed: int = 7) -> DadosPublicos:
    """Coleta as tabelas públicas da execução (sintéticas quando o mercado é sintético)."""
    if md.is_synthetic:
        from .sintetico import dados_sinteticos

        return dados_sinteticos(md, as_of, issuer_ids, tickers, etfs, seed=seed)
    try:
        from ..data import publico  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - depende da camada A1
        raise FontePublicaIndisponivel(
            "camada de dados públicos (cdp.data.publico) indisponível") from exc
    kw = {"offline": offline, "root": raiz}
    dem = _garantir(publico.demonstrativos(list(issuer_ids), as_of, **kw), COLS_DEMONSTRATIVOS)
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
        free_float=ff, etfs=comp, origem="PUBLICO", raiz=None if raiz is None else str(raiz))


__all__ = ["COLS_CONSENSO", "COLS_DEMONSTRATIVOS", "COLS_DIVIDENDOS", "COLS_ETF", "COLS_EVENTOS",
           "COLS_FLOAT", "COLS_TAXAS", "DadosPublicos", "FontePublicaIndisponivel", "coletar",
           "csv_canonico", "sha256_tabela"]
