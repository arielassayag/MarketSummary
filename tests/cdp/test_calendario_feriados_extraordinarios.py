"""Feriados extraordinários BYMA: calendário oficial de outubro/2026."""
from datetime import date

import pandas as pd
import pytest

from cdp.calendar import is_early_close, is_session, session_close_utc
from cdp.data.snapshot import drop_holiday_bars
from cdp.data.store import market_is_open


@pytest.mark.parametrize("dia", [9, 10])
def test_byma_sem_negociacao_nos_feriados_extraordinarios(dia):
    data = date(2026, 11, dia)
    assert is_session(data, "XBUE") is False
    assert market_is_open(data, "AR") is False
    assert is_early_close(data, "XBUE") is False
    assert session_close_utc(data, "XBUE") is None


@pytest.mark.parametrize("dia", [6, 11, 12, 13])
def test_restricao_de_liquidacao_nao_fecha_negociacao_byma(dia):
    data = date(2026, 11, dia)
    assert is_session(data, "XBUE") is True
    assert market_is_open(data, "AR") is True


@pytest.mark.parametrize("dia", [9, 10, 11])
def test_feriado_byma_nao_fecha_b3_nem_nyse(dia):
    data = date(2026, 11, dia)
    for bolsa, mercado in [("BVMF", "BR"), ("XNYS", "US")]:
        assert is_session(data, bolsa) is True
        assert market_is_open(data, mercado) is True


def test_barra_sintetica_byma_feriado_descartada_sem_perder_barras_reais():
    precos = pd.DataFrame([
        {"date": pd.Timestamp("2026-11-10"), "ticker": "GGAL.BA", "close": 10.,
         "adj_close": 10., "volume": float("nan"), "volume_flag": "volume_suspeito"},
        {"date": pd.Timestamp("2026-11-11"), "ticker": "GGAL.BA", "close": 11.,
         "adj_close": 11., "volume": 100., "volume_flag": ""},
        {"date": pd.Timestamp("2026-11-09"), "ticker": "BMA.BA", "close": 12.,
         "adj_close": 12., "volume": 100., "volume_flag": ""},
    ])
    limpos, descartados = drop_holiday_bars(precos, market_is_open)
    assert list(zip(limpos["ticker"], limpos["date"], strict=True)) == [
        ("GGAL.BA", pd.Timestamp("2026-11-11")),
        ("BMA.BA", pd.Timestamp("2026-11-09")),
    ]
    assert descartados == {"AR": 1}
