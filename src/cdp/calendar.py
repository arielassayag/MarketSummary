"""Calendários de pregão (exchange_calendars) e regra de rebalanceamento do CDP.

Regra: a carteira é montada no PRIMEIRO pregão da semana da bolsa primária (B3/BVMF). Se a
segunda-feira for feriado na B3 (ex.: 12/10), a montagem ocorre na terça, e assim por diante.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import exchange_calendars as xc
import pandas as pd

PRIMARY_EXCHANGE = "BVMF"
MARKET_EXCHANGES = {
    "BR": "BVMF", "MX": "XMEX", "CL": "XSGO", "CO": "XBOG", "PE": "XLIM", "AR": "XBUE",
    "US": "XNYS",
}


@lru_cache(maxsize=16)
def _cal(code: str):
    return xc.get_calendar(code)


def _in_range(cal, d: date) -> bool:
    ts = pd.Timestamp(d)
    return cal.first_session <= ts <= cal.last_session


def is_session(d: date, exchange: str = PRIMARY_EXCHANGE) -> bool:
    cal = _cal(exchange)
    if not _in_range(cal, d):
        return d.weekday() < 5  # fora do calendário conhecido: dias úteis
    return bool(cal.is_session(pd.Timestamp(d)))


def first_session_of_week(d: date, exchange: str = PRIMARY_EXCHANGE) -> date | None:
    """Primeiro pregão da semana (seg–sex) que contém ``d``; ``None`` se a semana não tiver pregão."""
    monday = d - timedelta(days=d.weekday())
    for i in range(5):
        day = monday + timedelta(days=i)
        if is_session(day, exchange):
            return day
    return None


def is_rebalance_day(d: date, exchange: str = PRIMARY_EXCHANGE) -> bool:
    return first_session_of_week(d, exchange) == d


def previous_session(d: date, exchange: str = PRIMARY_EXCHANGE) -> date:
    day = d - timedelta(days=1)
    while not is_session(day, exchange):
        day -= timedelta(days=1)
    return day


def open_markets(d: date) -> dict[str, bool]:
    """Quais mercados negociam em ``d`` (útil em feriados parciais, ex.: 12/10 só NYSE/BMV/BVL)."""
    return {m: is_session(d, code) for m, code in MARKET_EXCHANGES.items()}


def week_id(d: date) -> date:
    """Identificador da semana de decisão: o primeiro pregão da B3 na semana de ``d``."""
    first = first_session_of_week(d)
    return first if first is not None else d - timedelta(days=d.weekday())
