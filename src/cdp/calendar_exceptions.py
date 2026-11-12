"""Fechamentos extraordinários documentados, independentes da biblioteca de calendários."""

from datetime import date

# Exceções oficiais ainda ausentes de exchange_calendars 4.13.2. Não são
# permissões para tolerar preço ausente: só corrigem dias sem negociação.
# Fonte e prova visual: docs/cdp/FERIADOS_EXTRAORDINARIOS.md.
_EXTRAORDINARY_CLOSURES = {
    "XBUE": frozenset({date(2026, 11, 9), date(2026, 11, 10)}),
}


def is_extraordinary_closure(d: date, exchange: str) -> bool:
    """Fechamento integral documentado, não mera restrição de liquidação."""
    return d in _EXTRAORDINARY_CLOSURES.get(exchange, ())
