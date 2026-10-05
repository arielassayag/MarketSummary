"""Backtest walk-forward semanal do núcleo quantitativo e métricas de desempenho.

``metrics`` é leve (só numpy/pandas) e é importado diretamente; os nomes do motor
(``run_backtest`` etc.) são carregados sob demanda para não importar o otimizador (cvxpy)
quando apenas as métricas são necessárias (ex.: track record na interface).
"""

from __future__ import annotations

from typing import Any

from .metrics import (
    deflated_sharpe_ratio,
    drawdown_series,
    ic_summary,
    performance_metrics,
    weekly_returns,
)

_ENGINE_EXPORTS = frozenset({
    "BacktestConfig", "BacktestResult", "PointInTimeInputs", "earliest_start",
    "rebalance_dates", "run_backtest", "run_full_backtest", "run_snapshot_backtest",
    "simulate_weights",
})

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "PointInTimeInputs",
    "deflated_sharpe_ratio",
    "drawdown_series",
    "earliest_start",
    "ic_summary",
    "performance_metrics",
    "rebalance_dates",
    "run_backtest",
    "run_full_backtest",
    "run_snapshot_backtest",
    "simulate_weights",
    "weekly_returns",
]


def __getattr__(name: str) -> Any:
    if name in _ENGINE_EXPORTS:
        from . import engine

        return getattr(engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
