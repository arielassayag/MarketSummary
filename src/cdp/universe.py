"""Universo investível: emissores latino-americanos e suas linhas negociáveis (local e ADR).

O modelo de risco e o otimizador trabalham no nível do EMISSOR (``issuer_id``), usando a
linha primária para o histórico de retornos. A linha de execução (local x ADR) é escolhida
depois, por liquidez e possibilidade de aluguel. Isso evita que duas linhas do mesmo papel
apareçam como ativos "independentes" e gerem falsa diversificação ou falsa arbitragem.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .contracts import Country, LineType
from .hashing import sha256_file

DEFAULT_UNIVERSE_PATH = Path("data/universe/latam_universe.csv")

REQUIRED_COLUMNS = [
    "issuer_id", "issuer_name", "country", "gics_sector", "line_type", "yahoo_ticker",
    "exchange", "currency", "adr_ratio", "primary_line",
]

GICS_SECTORS = [
    "Energy", "Materials", "Industrials", "Consumer Discretionary", "Consumer Staples",
    "Health Care", "Financials", "Information Technology", "Communication Services",
    "Utilities", "Real Estate",
]

# Sufixo do Yahoo -> mercado de listagem da linha.
SUFFIX_MARKET = {".SA": "BR", ".MX": "MX", ".SN": "CL", ".CL": "CO", ".LM": "PE", ".BA": "AR"}


def listing_market(ticker: str) -> str:
    for suffix, market in SUFFIX_MARKET.items():
        if ticker.upper().endswith(suffix):
            return market
    return "US"


@dataclass(frozen=True)
class Universe:
    lines: pd.DataFrame    # índice: yahoo_ticker
    issuers: pd.DataFrame  # índice: issuer_id
    source_sha256: str = ""

    def lines_for(self, issuer_id: str) -> pd.DataFrame:
        return self.lines[self.lines["issuer_id"] == issuer_id]

    def primary_ticker(self, issuer_id: str) -> str:
        return str(self.issuers.loc[issuer_id, "primary_ticker"])

    @property
    def tickers(self) -> list[str]:
        return list(self.lines.index)

    @property
    def currencies(self) -> list[str]:
        return sorted(set(self.lines["currency"]))


def _parse_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"true", "1", "yes", "sim", "y"}


NOMES_CANONICOS = Path(__file__).resolve().parents[2] / "configs" / "cdp" / "nomes.yaml"
"""Nomes oficiais com acentos (``configs/cdp/nomes.yaml``) aplicados ao carregar o universo."""


@lru_cache(maxsize=4)
def nomes_canonicos(path: str | None = None) -> dict[str, str]:
    """``{emissor: nome com a grafia oficial}`` (vazio sem o arquivo)."""
    import yaml

    p = Path(path) if path else NOMES_CANONICOS
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    nomes = raw.get("nomes") if isinstance(raw, dict) else None
    return {str(k): str(v) for k, v in (nomes or {}).items() if v}


def universe_from_frame(df: pd.DataFrame, source_sha256: str = "") -> Universe:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Universo sem colunas obrigatórias: {missing}")
    df = df.copy()
    canon = nomes_canonicos()
    if canon:
        iid = df["issuer_id"].astype(str).str.strip()
        df["issuer_name"] = [canon.get(i, n) for i, n in zip(iid, df["issuer_name"], strict=True)]
    df["yahoo_ticker"] = df["yahoo_ticker"].astype(str).str.strip()
    df["issuer_id"] = df["issuer_id"].astype(str).str.strip()
    if df["yahoo_ticker"].duplicated().any():
        dups = df.loc[df["yahoo_ticker"].duplicated(), "yahoo_ticker"].tolist()
        raise ValueError(f"Tickers duplicados no universo: {dups}")
    valid_countries = {c.value for c in Country}
    bad_c = sorted(set(df["country"]) - valid_countries)
    if bad_c:
        raise ValueError(f"Países inválidos: {bad_c}")
    valid_lt = {t.value for t in LineType}
    bad_lt = sorted(set(df["line_type"]) - valid_lt)
    if bad_lt:
        raise ValueError(f"Tipos de linha inválidos: {bad_lt}")
    bad_s = sorted(set(df["gics_sector"]) - set(GICS_SECTORS))
    if bad_s:
        raise ValueError(f"Setores GICS inválidos: {bad_s}")
    df["primary_line"] = df["primary_line"].map(_parse_bool)
    df["adr_ratio"] = pd.to_numeric(df["adr_ratio"], errors="coerce")
    adr_missing = df[(df["line_type"] == "ADR") & df["adr_ratio"].isna()]
    if not adr_missing.empty:
        raise ValueError(f"ADRs sem adr_ratio: {adr_missing['yahoo_ticker'].tolist()}")
    df["market"] = df["yahoo_ticker"].map(listing_market)
    if "notes" not in df.columns:
        df["notes"] = ""
    df["notes"] = df["notes"].fillna("")

    prim = df[df["primary_line"]].groupby("issuer_id")["yahoo_ticker"].agg(list)
    issuers_ids = df["issuer_id"].unique()
    bad_primary = [i for i in issuers_ids if len(prim.get(i, [])) != 1]
    if bad_primary:
        raise ValueError(f"Cada emissor precisa de exatamente uma linha primária: {bad_primary}")
    # País e setor devem ser consistentes entre linhas do mesmo emissor.
    for col in ("country", "gics_sector", "issuer_name"):
        incons = df.groupby("issuer_id")[col].nunique()
        if (incons > 1).any():
            raise ValueError(f"'{col}' inconsistente entre linhas: {incons[incons > 1].index.tolist()}")

    lines = df.set_index("yahoo_ticker", drop=False).sort_index()
    first = df.groupby("issuer_id").first()
    issuers = pd.DataFrame({
        "issuer_name": first["issuer_name"],
        "country": first["country"],
        "gics_sector": first["gics_sector"],
        "primary_ticker": prim.map(lambda x: x[0]),
        "n_lines": df.groupby("issuer_id").size(),
    }).sort_index()
    issuers["primary_currency"] = issuers["primary_ticker"].map(lines["currency"])
    issuers["primary_line_type"] = issuers["primary_ticker"].map(lines["line_type"])
    return Universe(lines=lines, issuers=issuers, source_sha256=source_sha256)


def load_universe(path: str | Path | None = None) -> Universe:
    p = Path(path) if path else DEFAULT_UNIVERSE_PATH
    df = pd.read_csv(p, dtype={"adr_ratio": "string"}, keep_default_na=False, na_values=[""])
    return universe_from_frame(df, source_sha256=sha256_file(p))
