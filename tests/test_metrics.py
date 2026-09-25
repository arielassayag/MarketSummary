"""Testes para cálculos matemáticos puros e reconciliação em pontos-base."""

from datetime import UTC, datetime

import pytest

from fechamento.contracts import InstrumentType, Quote
from fechamento.metrics import (
    calculate_asset_contribution_bps,
    calculate_asset_return,
    calculate_currency_metric,
    calculate_portfolio_vs_ibov_bps,
    compute_all_metrics,
)


def test_asset_return_calculation() -> None:
    # Alta de 10%: 110 / 100 - 1 = 0.10
    assert calculate_asset_return(100.0, 110.0) == pytest.approx(0.10)
    # Queda de 5%: 95 / 100 - 1 = -0.05
    assert calculate_asset_return(100.0, 95.0) == pytest.approx(-0.05)


def test_asset_contribution_bps() -> None:
    # Peso 20% (0.20), retorno +2.5% (0.025) -> contribuição = 0.20 * 0.025 * 10000 = +50.0 bps
    assert calculate_asset_contribution_bps(0.20, 0.025) == pytest.approx(50.0)
    # Peso 10% (0.10), retorno -3.0% (-0.030) -> contribuição = 0.10 * -0.030 * 10000 = -30.0 bps
    assert calculate_asset_contribution_bps(0.10, -0.030) == pytest.approx(-30.0)


def test_portfolio_vs_ibov_bps() -> None:
    # Carteira +1.20% (0.0120), IBOV +1.00% (0.0100) -> spread = (0.0120 - 0.0100) * 10000 = +20.0 bps
    assert calculate_portfolio_vs_ibov_bps(0.0120, 0.0100) == pytest.approx(20.0)


def test_currency_metric_direction() -> None:
    now = datetime.now(UTC)
    # Dólar subiu de 5.40 para 5.50 (reais por dólar)
    q_up = Quote(
        ticker="USD/BRL",
        instrument_type=InstrumentType.CURRENCY,
        currency="BRL_PER_USD",
        previous_price=5.40,
        current_price=5.50,
        observed_at=now,
        source="BACEN",
        adjustment_criteria="NONE",
    )
    m_up = calculate_currency_metric(q_up)
    assert m_up.change_pct > 0
    assert "alta do dólar" in m_up.direction_description
    assert "desvalorização do real" in m_up.direction_description

    # Dólar caiu de 5.50 para 5.40
    q_down = Quote(
        ticker="USD/BRL",
        instrument_type=InstrumentType.CURRENCY,
        currency="BRL_PER_USD",
        previous_price=5.50,
        current_price=5.40,
        observed_at=now,
        source="BACEN",
        adjustment_criteria="NONE",
    )
    m_down = calculate_currency_metric(q_down)
    assert m_down.change_pct < 0
    assert "queda do dólar" in m_down.direction_description
    assert "valorização do real" in m_down.direction_description


def test_full_metrics_reconciliation() -> None:
    from fechamento.ingestion import load_and_validate_package

    pkg = load_and_validate_package("data/demo/normal")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)

    assert metrics.reconciled is True
    assert metrics.reconciliation_diff_bps <= 0.05
    assert len(metrics.top_positive_contributors) > 0
    assert len(metrics.top_negative_contributors) > 0
