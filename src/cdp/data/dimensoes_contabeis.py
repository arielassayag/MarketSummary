"""Dimensões contábeis opcionais; presença não autentica documento nem publicação.

O par tipado exige política explícita e data real de poder aquisitivo. Fontes totalmente
não tipadas conservam o contrato histórico. Nota/curadoria nunca preenchem este par.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime

import pandas as pd

CAMPOS = ("politica_contabil_id", "poder_aquisitivo_data")


def _ausente(value) -> bool:
    return (
        value is None
        or value is pd.NA
        or value is pd.NaT
        or (pd.api.types.is_scalar(value) and bool(pd.isna(value)))
    )


def _par_nativo(row) -> dict:
    """Valida somente os dois campos explícitos, sem inferir por fonte ou nota."""
    politica, poder = (row.get(k) for k in CAMPOS)
    ausentes = (_ausente(politica), _ausente(poder))
    if all(ausentes):
        return {}
    if any(ausentes):
        raise ValueError("dimensões contábeis parciais")
    if not isinstance(politica, str) or not politica.strip():
        raise ValueError("política contábil deve ser string não vazia")
    if isinstance(poder, datetime):
        raise ValueError("poder aquisitivo exige data civil, não instante")
    if isinstance(poder, date):
        poder = poder.isoformat()
    if not isinstance(poder, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", poder):
        raise ValueError("poder aquisitivo exige data ISO real")
    try:
        date.fromisoformat(poder)
    except ValueError as exc:
        raise ValueError("poder aquisitivo exige data ISO real") from exc
    return dict(zip(CAMPOS, (politica, poder), strict=True))


def dimensoes(row) -> dict:
    """Conserva o par nativo e recusa contradição explícita em fonte estruturada.

    A fonte pode não trazer o par. Se o declara, precisa ser completo e igual ao
    contexto nativo; nunca preenche uma ausência no topo. Não autentica documento.
    """
    par = _par_nativo(row)
    fonte = row.get("fonte")
    if isinstance(fonte, Mapping):
        par_fonte = _par_nativo(fonte)
        if par_fonte and par_fonte != par:
            raise ValueError("dimensões contábeis contraditórias na fonte explícita")
    return par


def compativeis(rows) -> bool:
    """Só o legado integral ou pares completos e iguais podem ser compostos."""
    try:
        pares = [dimensoes(row) for row in rows]
    except (TypeError, ValueError):
        return False
    return not pares or all(par == pares[0] for par in pares)


def composicao(rows) -> dict:
    """Propaga o par sem declarar homogeneidade para ausência ou mistura."""
    rows = list(rows)
    if not compativeis(rows):
        raise ValueError("componentes com dimensões contábeis incompatíveis ou ausentes")
    return dimensoes(rows[0]) if rows else {}
