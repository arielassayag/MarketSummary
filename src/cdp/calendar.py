"""Calendários de pregão (exchange_calendars) e regra de rebalanceamento do CDP.

Regra: a carteira é montada no PRIMEIRO pregão da semana da bolsa primária (B3/BVMF). Se a
segunda-feira for feriado na B3 (ex.: 12/10), a montagem ocorre na terça, e assim por diante.

Data de início do mandato (``fund.inception_date``): é sempre dia de montagem — a carteira
inaugural —, mesmo fora da regra semanal (ex.: numa sexta). Na semana do início, só ela é dia de
montagem e é a chave do livro dessa semana; nas demais semanas vale a regra semanal
(:func:`dia_de_montagem`, :func:`chave_da_semana`). As funções sem ``cfg`` seguem só a regra
semanal (comportamento legado).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING

import exchange_calendars as xc
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from .config import FundConfig

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


def week_id(d: date, cfg: FundConfig | None = None) -> date:
    """Identificador da semana de decisão: o dia de montagem da semana de ``d`` (o primeiro
    pregão da B3; com ``cfg``, a data de início na semana do início); sem pregão, a segunda."""
    first = chave_da_semana(d, cfg)
    return first if first is not None else _monday(d)


# ----------------------------------------------------------------------------- data de início


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def semana_do_inicio(d: date, cfg: FundConfig) -> bool:
    """``d`` está na semana (seg–dom) da data de início do mandato."""
    return _monday(d) == _monday(cfg.fund.inception_date)


def dia_de_montagem(d: date, cfg: FundConfig | None = None) -> bool:
    """Dia de montagem da carteira: a data de início do mandato (sempre, mesmo fora da regra
    semanal) e, nas demais semanas, o dia da regra semanal. Na semana do início, nenhum outro
    dia monta carteira. Sem ``cfg``: só a regra semanal (legado)."""
    if cfg is None:
        return is_rebalance_day(d)
    if semana_do_inicio(d, cfg):
        return d == cfg.fund.inception_date
    return is_rebalance_day(d)


def chave_da_semana(d: date, cfg: FundConfig | None = None) -> date | None:
    """Chave do livro (dia de montagem) da semana de ``d``: a data de início na semana do
    início; nas demais, o primeiro pregão da B3 (``None`` se a semana não tiver pregão). Sem
    ``cfg``: só a regra semanal (legado)."""
    if cfg is not None and semana_do_inicio(d, cfg):
        return cfg.fund.inception_date
    return first_session_of_week(d)


def chave_valida(week: date, cfg: FundConfig | None = None) -> bool:
    """``week`` pode ser chave do livro: o dia da regra semanal ou a data de início."""
    if cfg is not None and week == cfg.fund.inception_date:
        return True
    return first_session_of_week(week) == week


def proximas_montagens(desde: date, cfg: FundConfig | None = None,
                       semanas: int = 8) -> Iterator[date]:
    """Dias de montagem a partir de ``desde`` (inclusive), em ordem, por até ``semanas``
    semanas."""
    for k in range(semanas + 1):
        dia = chave_da_semana(_monday(desde) + timedelta(weeks=k), cfg)
        if dia is not None and dia >= desde and dia_de_montagem(dia, cfg):
            yield dia
