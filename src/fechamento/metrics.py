"""Funções matemáticas puras para cálculos de métricas financeiras e atribuições de carteira.

Implementa estritamente as fórmulas especificadas:
- retorno_ativo = preco_atual / preco_anterior - 1
- retorno_carteira = soma(peso_inicial_i * retorno_i)
- contribuicao_ativo_bps = peso_inicial_i * retorno_i * 10_000
- contribuicao_setor_bps = soma(contribuicoes_dos_ativos_do_setor)
- retorno_ativo_vs_ibov_bps = (retorno_carteira - retorno_ibov) * 10_000

Sem arredondamentos intermediários; tolerâncias de reconciliação explícitas.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import Position, Quote


@dataclass(frozen=True)
class AssetMetric:
    ticker: str
    sector: str
    weight_start: float
    previous_price: float
    current_price: float
    return_pct: float
    contribution_bps: float


@dataclass(frozen=True)
class SectorMetric:
    sector: str
    weight_total: float
    contribution_bps: float
    tickers: list[str]


@dataclass(frozen=True)
class CurrencyMetric:
    ticker: str
    previous_price: float
    current_price: float
    change_pct: float
    direction_description: str  # ex: "alta do dólar / desvalorização do real"


@dataclass(frozen=True)
class CalculatedMetrics:
    ibov_return_pct: float
    usd_brl: CurrencyMetric
    portfolio_return_pct: float
    portfolio_vs_ibov_bps: float
    asset_metrics: dict[str, AssetMetric]
    sector_metrics: dict[str, SectorMetric]
    top_positive_contributors: list[AssetMetric]
    top_negative_contributors: list[AssetMetric]
    reconciled: bool
    reconciliation_diff_bps: float


def calculate_asset_return(previous_price: float, current_price: float) -> float:
    """Calcula o retorno simples do ativo: P_atual / P_anterior - 1."""
    if previous_price <= 0:
        raise ValueError(f"Preço anterior deve ser estritamente positivo: {previous_price}")
    if current_price <= 0:
        raise ValueError(f"Preço atual deve ser estritamente positivo: {current_price}")
    return (current_price / previous_price) - 1.0


def calculate_portfolio_return(weights: dict[str, float], returns: dict[str, float]) -> float:
    """Calcula o retorno da carteira: soma(peso_i * retorno_i)."""
    return sum(weights[t] * returns[t] for t in weights)


def calculate_asset_contribution_bps(weight_start: float, asset_return: float) -> float:
    """Calcula a contribuição do ativo para a carteira em pontos-base: peso_i * retorno_i * 10.000."""
    return weight_start * asset_return * 10_000.0


def calculate_portfolio_vs_ibov_bps(portfolio_return: float, ibov_return: float) -> float:
    """Calcula a diferença em pontos-base entre o retorno da carteira e o IBOV:

    (retorno_carteira - retorno_ibov) * 10.000.
    Nota: Representa o spread simples da carteira sobre o benchmark, não alfa fatorial.
    """
    return (portfolio_return - ibov_return) * 10_000.0


def calculate_currency_metric(quote: Quote) -> CurrencyMetric:
    """Calcula a variação do par cambial USD/BRL (reais por dólar).

    Variação positiva = dólar valorizou / real depreciou.
    Variação negativa = dólar depreciou / real valorizou.
    """
    change = calculate_asset_return(quote.previous_price, quote.current_price)
    if change > 0:
        direction = "alta do dólar frente ao real (valorização do dólar e desvalorização do real)"
    elif change < 0:
        direction = "queda do dólar frente ao real (depreciação do dólar e valorização do real)"
    else:
        direction = "estabilidade do dólar frente ao real"

    return CurrencyMetric(
        ticker=quote.ticker,
        previous_price=quote.previous_price,
        current_price=quote.current_price,
        change_pct=change,
        direction_description=direction,
    )


def compute_all_metrics(
    quotes: dict[str, Quote],
    positions: dict[str, Position],
    tolerance_bps: float = 0.05,
) -> CalculatedMetrics:
    """Calcula todas as métricas financeiras, agregando por ativo e por setor.

    Aplica reconciliação estrita entre o retorno da carteira e a soma das contribuições.
    """
    if "IBOV" not in quotes:
        raise KeyError("Cotação 'IBOV' obrigatória não encontrada.")
    if "USD/BRL" not in quotes:
        raise KeyError("Cotação 'USD/BRL' obrigatória não encontrada.")

    ibov_quote = quotes["IBOV"]
    ibov_return = calculate_asset_return(ibov_quote.previous_price, ibov_quote.current_price)

    usd_quote = quotes["USD/BRL"]
    usd_metric = calculate_currency_metric(usd_quote)

    asset_metrics: dict[str, AssetMetric] = {}
    weights: dict[str, float] = {}
    returns: dict[str, float] = {}

    for ticker, pos in positions.items():
        if ticker not in quotes:
            raise KeyError(f"Cotação do ativo '{ticker}' da carteira não encontrada.")
        q = quotes[ticker]
        ret = calculate_asset_return(q.previous_price, q.current_price)
        contrib = calculate_asset_contribution_bps(pos.weight_start, ret)

        weights[ticker] = pos.weight_start
        returns[ticker] = ret

        asset_metrics[ticker] = AssetMetric(
            ticker=ticker,
            sector=pos.sector,
            weight_start=pos.weight_start,
            previous_price=q.previous_price,
            current_price=q.current_price,
            return_pct=ret,
            contribution_bps=contrib,
        )

    portfolio_return = calculate_portfolio_return(weights, returns)
    portfolio_vs_ibov = calculate_portfolio_vs_ibov_bps(portfolio_return, ibov_return)

    # Agregação por setor
    sectors: dict[str, list[AssetMetric]] = {}
    for am in asset_metrics.values():
        sectors.setdefault(am.sector, []).append(am)

    sector_metrics: dict[str, SectorMetric] = {}
    for sector_name, items in sectors.items():
        w_total = sum(i.weight_start for i in items)
        c_total = sum(i.contribution_bps for i in items)
        sector_metrics[sector_name] = SectorMetric(
            sector=sector_name,
            weight_total=w_total,
            contribution_bps=c_total,
            tickers=[i.ticker for i in items],
        )

    # Reconciliação matemática: soma das contribuições vs (retorno_carteira * 10_000)
    sum_contributions = sum(am.contribution_bps for am in asset_metrics.values())
    expected_contrib = portfolio_return * 10_000.0
    diff_bps = abs(sum_contributions - expected_contrib)
    reconciled = diff_bps <= tolerance_bps

    # Rankings de contribuição
    sorted_by_contrib = sorted(asset_metrics.values(), key=lambda x: x.contribution_bps, reverse=True)
    top_pos = [a for a in sorted_by_contrib if a.contribution_bps > 0]
    top_neg = sorted([a for a in sorted_by_contrib if a.contribution_bps < 0], key=lambda x: x.contribution_bps)

    return CalculatedMetrics(
        ibov_return_pct=ibov_return,
        usd_brl=usd_metric,
        portfolio_return_pct=portfolio_return,
        portfolio_vs_ibov_bps=portfolio_vs_ibov,
        asset_metrics=asset_metrics,
        sector_metrics=sector_metrics,
        top_positive_contributors=top_pos,
        top_negative_contributors=top_neg,
        reconciled=reconciled,
        reconciliation_diff_bps=diff_bps,
    )
