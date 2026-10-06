"""Demonstração offline da cobertura (DADOS SIMULADOS).

``gerar(rt, datas)`` produz um snapshot de cobertura por data (sem rede, sem chaves) sobre o
mercado sintético do ``Runtime`` da demonstração (``DemoStore``): modelos abertos para todos os
emissores e ETFs sintéticos, livro encadeado com iniciações, reiterações, revisões e mudanças de
rating, e o evento ``COVERAGE_SNAPSHOT`` na trilha. A integração no ``run_demo`` é feita pela
etapa de integração (uma linha), nas sextas-feiras da demonstração.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .cli import executar_snapshot
from .livro import datas_snapshots
from .parametros import carregar_parametros

BRT = ZoneInfo("America/Sao_Paulo")
CODIGO_DEMO = {"git": None, "nota": "demonstração offline"}


def gerar(rt: Any, datas: Sequence[date]) -> list[dict[str, Any]]:
    """Um snapshot por data (ordem crescente; datas já cobertas são ignoradas)."""
    params = carregar_parametros()
    book = Path(rt.book_root)
    feitas = set(datas_snapshots(book))
    out = []
    for d in sorted(set(datas)):
        if d in feitas:
            continue
        md = rt.store.load(d)
        if md.as_of != d:
            continue
        agora = datetime.combine(d, time(21, 30), tzinfo=BRT)
        res = executar_snapshot(book, md, d, params=params, offline=True, agora=agora, codigo=CODIGO_DEMO)
        out.append(res)
    return out


__all__ = ["gerar"]
