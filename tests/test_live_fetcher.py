"""Testes unitários para o módulo live_fetcher (BrasilAPI, AwesomeAPI, B3)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fechamento.ingestion import load_and_validate_package
from fechamento.live_fetcher import (
    build_live_market_package,
    compute_sha256,
    fetch_awesomeapi_usd_brl,
    fetch_brasilapi_taxas,
    fetch_yahoo_chart,
)


def test_compute_sha256(tmp_path: Path) -> None:
    test_file = tmp_path / "sample.txt"
    test_file.write_text("conteúdo de teste", encoding="utf-8")
    h = compute_sha256(test_file)
    assert isinstance(h, str)
    assert len(h) == 64


def test_fetch_brasilapi_taxas_mocked() -> None:
    mock_payload = b'[{"nome": "Selic", "valor": 13.75}, {"nome": "CDI", "valor": 13.65}]'
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_payload
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        taxas = fetch_brasilapi_taxas()
        assert taxas.get("SELIC") == 13.75
        assert taxas.get("CDI") == 13.65


def test_fetch_brasilapi_taxas_fallback_on_error() -> None:
    with patch("urllib.request.urlopen", side_effect=Exception("Timeout simulado")):
        taxas = fetch_brasilapi_taxas()
        assert "SELIC" in taxas
        assert "CDI" in taxas
        assert "_error" in taxas


def test_fetch_awesomeapi_usd_brl_mocked() -> None:
    mock_payload = b'{"USDBRL": {"bid": "5.4520", "varBid": "0.0210", "pctChange": "0.39", "high": "5.48", "low": "5.43", "create_date": "2026-09-20 10:00:00"}}'
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_payload
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = fetch_awesomeapi_usd_brl()
        assert res["ticker"] == "USD/BRL"
        assert res["current_price"] == 5.4520
        assert res["previous_price"] == 5.4520 - 0.0210
        assert res["pct_change"] == pytest.approx(0.0039)


def test_fetch_yahoo_chart_mocked() -> None:
    mock_payload = b'{"chart": {"result": [{"meta": {"regularMarketPrice": 38.50, "chartPreviousClose": 38.00, "currency": "BRL"}}]}}'
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_payload
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = fetch_yahoo_chart("PETR4.SA")
        assert res["ticker"] == "PETR4"
        assert res["current_price"] == 38.50
        assert res["previous_price"] == 38.00
        assert res["currency"] == "BRL"


def test_build_live_market_package(tmp_path: Path) -> None:
    out_dir = tmp_path / "live_pkg"

    # Mock das 3 chamadas externas para teste hermético
    with (
        patch("fechamento.live_fetcher.fetch_awesomeapi_usd_brl", return_value={
            "ticker": "USD/BRL", "current_price": 5.20, "previous_price": 5.18, "pct_change": 0.0038
        }),
        patch("fechamento.live_fetcher.fetch_yahoo_chart", side_effect=lambda t: {
            "ticker": t.replace(".SA", "").replace("^BVSP", "IBOV"),
            "current_price": 100.0 if "BVSP" in t else 30.0,
            "previous_price": 98.0 if "BVSP" in t else 29.0,
            "currency": "POINTS" if "BVSP" in t else "BRL",
        }),
        patch("fechamento.live_fetcher.fetch_brasilapi_taxas", return_value={"SELIC": 13.75, "CDI": 13.65}),
    ):
        pkg_dir = build_live_market_package(out_dir, timeframe="1d", tickers=["PETR4.SA", "VALE3.SA"])
        assert pkg_dir.exists()
        assert (pkg_dir / "quotes.csv").exists()
        assert (pkg_dir / "positions.csv").exists()
        assert (pkg_dir / "news.jsonl").exists()
        assert (pkg_dir / "manifest.json").exists()

        # Verifica se o pacote é perfeitamente carregável e validável pela pipeline do Fechamento
        ingestion_res = load_and_validate_package(pkg_dir)
        assert ingestion_res.is_blocked is False
        assert ingestion_res.manifest is not None
        assert ingestion_res.manifest.is_synthetic is False
        assert len(ingestion_res.quotes) == 4  # IBOV, USD/BRL, PETR4, VALE3
        assert len(ingestion_res.positions) == 2
