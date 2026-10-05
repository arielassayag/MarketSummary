"""Contêiner imutável dos dados de mercado de um snapshot (reais ou simulados)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .contracts import NewsItem, SnapshotManifest
from .universe import Universe

# Campos de fundamentos por linha (retrato atual da fonte, NÃO point-in-time).
FUNDAMENTAL_FIELDS = [
    "currency",               # moeda de cotação da linha
    "financial_currency",     # moeda das demonstrações
    "market_cap",             # na moeda de cotação da linha
    "shares_outstanding",
    "float_shares",
    "trailing_pe",
    "forward_pe",
    "price_to_book",
    "book_value",             # por ação, na moeda das demonstrações
    "trailing_eps",
    "forward_eps",
    "return_on_equity",
    "return_on_assets",
    "profit_margins",
    "operating_margins",
    "gross_margins",
    "debt_to_equity",
    "dividend_yield",
    "enterprise_to_ebitda",
    "revenue_growth",
    "earnings_growth",
    "beta",
    "target_mean_price",
    "recommendation_mean",
    "number_of_analyst_opinions",
    "average_daily_volume_3m",
    "next_earnings_date",     # ISO date ou NaN
    "sector",
    "industry",
]

SHORT_INTEREST_FIELDS = [
    "shares_short", "short_pct_float", "short_ratio_days", "short_interest_date", "source",
]

LENDING_FIELDS = [
    "lent_shares", "lending_pct_shares", "lending_rate_annual", "lending_date", "source",
]


@dataclass(frozen=True)
class MarketData:
    """Dados brutos alinhados por data (índice ``DatetimeIndex`` diário, colunas = tickers).

    - ``close``/``adj_close``: moeda local da linha; ``adj_close`` ajustado por proventos e
      desdobramentos (retorno total). Ausências permanecem ``NaN``.
    - ``volume``: quantidade de ações (ou ADRs) negociadas.
    - ``fx``: USD por 1 unidade da moeda (coluna ``USD`` = 1.0).
    - ``benchmarks``: fechamento nativo de ETFs/índices de referência (colunas = símbolos Yahoo).
    - ``rates``: taxas anuais em decimal (ex.: ``USD_3M``, ``SELIC``).
    """

    manifest: SnapshotManifest
    universe: Universe
    close: pd.DataFrame
    adj_close: pd.DataFrame
    volume: pd.DataFrame
    fx: pd.DataFrame
    fundamentals: pd.DataFrame
    short_interest: pd.DataFrame
    lending: pd.DataFrame
    benchmarks: pd.DataFrame
    rates: pd.DataFrame
    news: tuple[NewsItem, ...] = field(default_factory=tuple)

    @property
    def as_of(self) -> date:
        return self.manifest.as_of

    @property
    def is_synthetic(self) -> bool:
        return self.manifest.is_synthetic

    def truncate(self, end: date) -> MarketData:
        """Visão sem look-ahead: somente datas <= ``end`` (usada no backtest).

        Fundamentos, short interest e aluguel são retratos atuais e são mantidos; quem os usa
        em backtest deve tratá-los como não point-in-time.
        """
        ts = pd.Timestamp(end)

        def cut(df: pd.DataFrame) -> pd.DataFrame:
            return df.loc[df.index <= ts]

        return MarketData(
            manifest=self.manifest, universe=self.universe,
            close=cut(self.close), adj_close=cut(self.adj_close), volume=cut(self.volume),
            fx=cut(self.fx), fundamentals=self.fundamentals, short_interest=self.short_interest,
            lending=self.lending, benchmarks=cut(self.benchmarks), rates=cut(self.rates),
            news=tuple(n for n in self.news if n.published_at.date() <= end),
        )
