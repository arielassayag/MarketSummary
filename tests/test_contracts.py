"""Testes para os contratos Pydantic e invariantes de dados."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from fechamento.contracts import (
    InstrumentType,
    NewsItem,
    Position,
    Quote,
)


def test_quote_contract_valid() -> None:
    now = datetime.now(UTC)
    quote = Quote(
        ticker="PETR4",
        instrument_type=InstrumentType.EQUITY,
        currency="BRL",
        previous_price=30.0,
        current_price=31.5,
        observed_at=now,
        source="B3_SIMULADO",
        adjustment_criteria="EX_DIV",
        is_synthetic=True,
    )
    assert quote.ticker == "PETR4"
    assert quote.current_price == 31.5
    assert quote.is_synthetic is True


def test_quote_contract_invalid_price() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        Quote(
            ticker="PETR4",
            instrument_type=InstrumentType.EQUITY,
            currency="BRL",
            previous_price=0.0,  # Preço inválido <= 0
            current_price=31.5,
            observed_at=now,
            source="B3",
            adjustment_criteria="NONE",
            is_synthetic=True,
        )


def test_quote_contract_missing_timezone() -> None:
    naive_dt = datetime(2026, 9, 18, 17, 0, 0)
    with pytest.raises(ValidationError):
        Quote(
            ticker="PETR4",
            instrument_type=InstrumentType.EQUITY,
            currency="BRL",
            previous_price=30.0,
            current_price=31.5,
            observed_at=naive_dt,
            source="B3",
            adjustment_criteria="NONE",
            is_synthetic=True,
        )


def test_position_contract() -> None:
    pos = Position(
        ticker="VALE3",
        sector="Materiais Básicos",
        weight_start=0.25,
        reference_date=date(2026, 9, 18),
        is_synthetic=True,
    )
    assert pos.weight_start == 0.25

    with pytest.raises(ValidationError):
        Position(
            ticker="VALE3",
            sector="Materiais Básicos",
            weight_start=1.2,  # Peso > 1.0
            reference_date=date(2026, 9, 18),
            is_synthetic=True,
        )


def test_news_item_contract() -> None:
    now = datetime.now(UTC)
    news = NewsItem(
        news_id="news_1",
        title="Título de teste",
        body="Corpo da notícia de teste.",
        published_at=now,
        source="Fonte_Simulada",
        related_tickers=["PETR4"],
        is_synthetic=True,
    )
    assert news.news_id == "news_1"
    assert "PETR4" in news.related_tickers
