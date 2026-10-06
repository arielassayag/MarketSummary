"""Calendários de pregão (exchange_calendars) e regra de rebalanceamento do CDP.

Regra semanal (``fund.rebalance_weekday``):

- ``LAST_US_SESSION``: a carteira é montada no ÚLTIMO pregão da semana (seg–sex) do calendário
  ``execution.rebalance_calendar`` (NYSE): sexta-feira ou, com feriado nos EUA, o pregão
  anterior (ex.: quinta 25/03/2027, véspera da Sexta-Feira Santa). Decisão antes do fechamento,
  execução no leilão de fechamento (MOC) de cada linha.
- ``MON`` (legado): o PRIMEIRO pregão da semana na B3 (segunda ou o próximo dia útil).

Data de início do mandato (``fund.inception_date``): é sempre dia de montagem — a carteira
inaugural —, mesmo fora da regra semanal. Na semana do início, só ela é dia de montagem e é a
chave do livro dessa semana; nas demais semanas vale a regra semanal (:func:`dia_de_montagem`,
:func:`chave_da_semana`). As funções sem ``cfg`` seguem só a regra legada (``MON``).

Os calendários são construídos com limites explícitos (hoje − 20 anos a hoje + 2 anos), para
que feriados além do horizonte padrão da biblioteca (um ano) sejam conhecidos. Os HORÁRIOS de
fechamento não vêm daqui (a biblioteca só é confiável para os dias de pregão e para os
fechamentos antecipados dos EUA): ver ``execution.close_times`` e
:mod:`cdp.portfolio.execucao`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from .config import FundConfig

PRIMARY_EXCHANGE = "BVMF"
REBALANCE_EXCHANGE = "XNYS"
"""Calendário padrão da regra ``LAST_US_SESSION`` (``execution.rebalance_calendar``)."""
DATA_EXCHANGES = ("BVMF", "XNYS", "XMEX")
"""Calendários em que a base de mercado ganha um pregão (união) — o fechamento diário registra
em qualquer um deles e o pregão de dados anterior é o da união."""
MARKET_EXCHANGES = {
    "BR": "BVMF", "MX": "XMEX", "CL": "XSGO", "CO": "XBOG", "PE": "XLIM", "AR": "XBUE",
    "US": "XNYS",
}
CALENDAR_YEARS_BACK = 20
CALENDAR_YEARS_AHEAD = 2
_WEEKDAYS_PT = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
                "sábado", "domingo")


def _bounds(today: date | None = None) -> tuple[date, date]:
    t = today or date.today()
    return (date(t.year - CALENDAR_YEARS_BACK, t.month, min(t.day, 28)),
            date(t.year + CALENDAR_YEARS_AHEAD, t.month, min(t.day, 28)))


@lru_cache(maxsize=32)
def _cal(code: str):
    start, end = _bounds()
    try:
        return xc.get_calendar(code, start=start.isoformat(), end=end.isoformat())
    except Exception:  # noqa: BLE001 - versão da biblioteca sem suporte aos limites pedidos
        return xc.get_calendar(code)


def _in_range(cal, d: date) -> bool:
    ts = pd.Timestamp(d)
    return cal.first_session <= ts <= cal.last_session


def is_session(d: date, exchange: str = PRIMARY_EXCHANGE) -> bool:
    cal = _cal(exchange)
    if not _in_range(cal, d):
        return d.weekday() < 5  # fora do calendário conhecido: dias úteis
    return bool(cal.is_session(pd.Timestamp(d)))


def is_early_close(d: date, exchange: str) -> bool:
    """Pregão com fechamento antecipado no calendário (ex.: NYSE em 27/11 e 24/12)."""
    cal = _cal(exchange)
    if not _in_range(cal, d) or not cal.is_session(pd.Timestamp(d)):
        return False
    return pd.Timestamp(d) in cal.early_closes


def session_close_utc(d: date, exchange: str) -> datetime | None:
    """Fechamento do pregão segundo a biblioteca (UTC). Use só para fechamentos antecipados."""
    cal = _cal(exchange)
    if not _in_range(cal, d) or not cal.is_session(pd.Timestamp(d)):
        return None
    return cal.session_close(pd.Timestamp(d)).to_pydatetime()


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def first_session_of_week(d: date, exchange: str = PRIMARY_EXCHANGE) -> date | None:
    """Primeiro pregão da semana (seg–sex) que contém ``d``; ``None`` se a semana não tiver pregão."""
    monday = _monday(d)
    for i in range(5):
        day = monday + timedelta(days=i)
        if is_session(day, exchange):
            return day
    return None


def last_session_of_week(d: date, exchange: str = REBALANCE_EXCHANGE) -> date | None:
    """Último pregão da semana (seg–sex) que contém ``d``; ``None`` se a semana não tiver pregão."""
    monday = _monday(d)
    for i in range(4, -1, -1):
        day = monday + timedelta(days=i)
        if is_session(day, exchange):
            return day
    return None


def regra(cfg: FundConfig | None) -> str:
    """Código da regra semanal: ``"LAST_US_SESSION"`` ou ``"MON"`` (legado; também sem ``cfg``)."""
    if cfg is None:
        return "MON"
    return str(cfg.fund.rebalance_weekday)


def calendario_de_rebalanceamento(cfg: FundConfig | None) -> str:
    """Calendário que define o dia de montagem: B3 na regra legada; o
    ``execution.rebalance_calendar`` (NYSE por padrão) na regra ``LAST_US_SESSION``."""
    if regra(cfg) != "LAST_US_SESSION":
        return PRIMARY_EXCHANGE
    ex = cfg.execution if cfg is not None else None
    return str(ex.rebalance_calendar) if ex is not None else REBALANCE_EXCHANGE


def rebalance_date_of_week(d: date, cfg: FundConfig | None = None) -> date | None:
    """Dia da regra semanal na semana de ``d`` (sem a exceção da data de início): MON → primeiro
    pregão da B3; LAST_US_SESSION → último pregão do calendário de rebalanceamento."""
    if regra(cfg) == "LAST_US_SESSION":
        return last_session_of_week(d, calendario_de_rebalanceamento(cfg))
    return first_session_of_week(d)


def is_rebalance_day(d: date, cfg: FundConfig | str | None = None, *,
                     chaves: Sequence[date] = ()) -> bool:
    """``d`` é o dia da regra semanal (ou uma das ``chaves`` aceitas explicitamente).

    Compatibilidade: ``is_rebalance_day(d, "BVMF")`` (código de bolsa no segundo argumento)
    mantém o comportamento legado — primeiro pregão da semana nessa bolsa."""
    if d in set(chaves):
        return True
    if isinstance(cfg, str):
        return first_session_of_week(d, cfg) == d
    return rebalance_date_of_week(d, cfg) == d


def previous_session(d: date, exchange: str = PRIMARY_EXCHANGE) -> date:
    day = d - timedelta(days=1)
    while not is_session(day, exchange):
        day -= timedelta(days=1)
    return day


def is_data_session(d: date) -> bool:
    """Pregão em algum calendário da base de mercado (B3, NYSE ou BMV)."""
    return any(is_session(d, ex) for ex in DATA_EXCHANGES)


def previous_data_session(d: date) -> date:
    """Pregão de dados anterior a ``d`` na união B3 | NYSE | BMV (ex.: 12/10/2026, feriado na B3
    com a NYSE aberta, é o pregão de dados anterior a 13/10)."""
    day = d - timedelta(days=1)
    while not is_data_session(day):
        day -= timedelta(days=1)
    return day


def open_markets(d: date) -> dict[str, bool]:
    """Quais mercados negociam em ``d`` (útil em feriados parciais, ex.: 12/10 só NYSE/BMV/BVL)."""
    return {m: is_session(d, code) for m, code in MARKET_EXCHANGES.items()}


def week_id(d: date, cfg: FundConfig | None = None) -> date:
    """Identificador da semana de decisão: o dia de montagem da semana de ``d`` (regra semanal;
    com ``cfg``, a data de início na semana do início); sem pregão, a segunda."""
    first = chave_da_semana(d, cfg)
    return first if first is not None else _monday(d)


# ----------------------------------------------------------------------------- data de início


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
    return is_rebalance_day(d, cfg)


def chave_da_semana(d: date, cfg: FundConfig | None = None) -> date | None:
    """Chave do livro (dia de montagem) da semana de ``d``: a data de início na semana do
    início; nas demais, o dia da regra semanal (``None`` se a semana não tiver pregão). Sem
    ``cfg``: só a regra semanal legada."""
    if cfg is not None and semana_do_inicio(d, cfg):
        return cfg.fund.inception_date
    return rebalance_date_of_week(d, cfg)


def chave_valida(week: date, cfg: FundConfig | None = None) -> bool:
    """``week`` pode ser chave do livro: o dia da regra semanal ou a data de início."""
    if cfg is not None and week == cfg.fund.inception_date:
        return True
    return rebalance_date_of_week(week, cfg) == week


def proximas_montagens(desde: date, cfg: FundConfig | None = None,
                       semanas: int = 8) -> Iterator[date]:
    """Dias de montagem a partir de ``desde`` (inclusive), em ordem, por até ``semanas``
    semanas."""
    for k in range(semanas + 1):
        dia = chave_da_semana(_monday(desde) + timedelta(weeks=k), cfg)
        if dia is not None and dia >= desde and dia_de_montagem(dia, cfg):
            yield dia


def next_rebalance_after(d: date, cfg: FundConfig | None = None) -> date:
    """Primeiro dia de montagem ESTRITAMENTE posterior a ``d`` (05/10/2026 → 09/10/2026)."""
    for dia in proximas_montagens(d + timedelta(days=1), cfg, semanas=8):
        return dia
    raise ValueError(f"Sem dia de montagem nas oito semanas após {d}.")  # pragma: no cover


def rebalance_schedule(start: date, end: date, cfg: FundConfig | None = None) -> list[date]:
    """Dias de montagem em ``[start, end]`` (inclusive), em ordem."""
    if end < start:
        return []
    weeks = (end - start).days // 7 + 2
    return [d for d in proximas_montagens(start, cfg, semanas=weeks) if d <= end]


# ----------------------------------------------------------------------------- resumo


def _weekday_pt(d: date) -> str:
    return _WEEKDAYS_PT[d.weekday()]


def resumo_cronograma(cfg: FundConfig, hoje: date, *, proximas: int = 4) -> dict[str, Any]:
    """Resumo do cronograma para agenda, painel e UI (só calendário; nenhum dado do livro).

    ``proximo_rebalanceamento``: o próximo dia de montagem a partir de ``hoje`` (inclusive);
    ``prazo_decisao``: prazo efetivo da decisão nesse dia (Brasília); ``fechamentos``: horário de
    fechamento oficial de cada mercado aberto (Brasília); ``mercados_fechados``: países sem pregão
    no dia; ``fechamento_antecipado``: NYSE, B3 ou BMV (os mercados que definem o prazo) fecham
    mais cedo; ``mercados_fechamento_antecipado``: todos os mercados que fecham mais cedo no dia
    (capacidade reduzida só neles)."""
    from .portfolio.execucao import (
        MIC_NOME,
        janela_execucao,
        mercados_elegiveis,
        mics_antecipados,
        prazo_efetivo,
    )

    tz = ZoneInfo(cfg.fund.timezone)
    datas = list(proximas_montagens(hoje, cfg, semanas=max(proximas, 1) + 2))[:proximas]
    out: dict[str, Any] = {
        "regra": cfg.fund.rebalance_rule, "regra_codigo": regra(cfg),
        "calendario": calendario_de_rebalanceamento(cfg),
        "inicio_pesquisa": cfg.fund.weekly_research_start_local,
        "execucao": cfg.fund.execution_convention,
        "proximas_datas": datas,
    }
    if not datas:  # pragma: no cover - calendário sem pregão por semanas
        out.update({"proximo_rebalanceamento": None, "prazo_decisao": None})
        return out
    d = datas[0]
    out["proximo_rebalanceamento"] = d
    out["dia_da_semana"] = _weekday_pt(d)
    out["prazo_decisao"] = prazo_efetivo(d, cfg).astimezone(tz)
    out["mercados_fechados"] = sorted(m for m, ok in open_markets(d).items() if not ok)
    if cfg.execution is None:
        out["fechamento_antecipado"] = False
        out["mercados_fechamento_antecipado"] = []
        out["fechamentos"] = {}
        return out
    j = janela_execucao(d, cfg)
    elig = mercados_elegiveis(j, cfg)
    out["fechamento_antecipado"] = j.fechamento_antecipado
    out["mercados_fechamento_antecipado"] = sorted(MIC_NOME.get(m, m)
                                                   for m in mics_antecipados(j, cfg))
    out["fechamentos"] = {m: t.astimezone(tz) for m, t in sorted(j.fechamentos.items())}
    out["mercados_inelegiveis"] = sorted(m for m, ok in elig.items() if not ok)
    return out


__all__ = [
    "DATA_EXCHANGES", "MARKET_EXCHANGES", "PRIMARY_EXCHANGE", "REBALANCE_EXCHANGE",
    "calendario_de_rebalanceamento", "chave_da_semana", "chave_valida", "dia_de_montagem",
    "first_session_of_week", "is_data_session", "is_early_close", "is_rebalance_day",
    "is_session", "last_session_of_week", "next_rebalance_after", "open_markets",
    "previous_data_session", "previous_session", "proximas_montagens", "rebalance_date_of_week",
    "rebalance_schedule", "regra", "resumo_cronograma", "semana_do_inicio",
    "session_close_utc", "week_id",
]
