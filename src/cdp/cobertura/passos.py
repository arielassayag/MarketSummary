"""Modelo aberto: registro ordenado dos passos de cálculo, com fórmula e substituição.

Cada passo é ``{id, titulo, formula, substituicao, resultado, resultado_texto, unidade, fontes,
premissas}``: a fórmula em notação simbólica pt-BR, a mesma fórmula com os números efetivamente
usados (formatados em Python, vírgula decimal) e terminada por `` = <resultado>``, as premissas
do passo (valores de contexto que não entram na conta exibida) e as proveniências públicas dos
insumos. Regra do texto: a substituição é sempre uma expressão cujo valor é o resultado — nunca
uma lista descritiva seguida de "= resultado". A página do portal só exibe esse texto; ela nunca
calcula.

``Proveniencia`` é o contrato compartilhado com a camada de dados públicos
(:mod:`cdp.data.publico`); enquanto ela não está disponível, a definição local abaixo tem os
mesmos campos.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .formato import r6, valor

try:  # contrato da camada de dados públicos (workstream A1)
    from ..data.publico import Proveniencia  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - usado só até a camada pública existir

    @dataclass(frozen=True)
    class Proveniencia:  # type: ignore[no-redef]
        """Origem pública de um insumo (mesmos campos do contrato de :mod:`cdp.data.publico`)."""

        fonte: str
        url: str | None = None
        documento: str | None = None
        data_publicacao: date | None = None
        data_coleta: datetime | None = None
        sha256: str | None = None


FONTES_VALIDAS = ("CVM", "SEC", "YAHOO", "BCB", "FRED", "B3", "ISHARES", "GLOBALX", "DAMODARAN",
                  "RI", "SIMULADO", "CODIGO", "CONFIG")
"""``CODIGO``: valor derivado em código de outros insumos; ``CONFIG``: parâmetro datado e
versionado em ``configs/cdp/valuation.yaml`` (cada um com sua fonte pública citada); ``RI``:
documento publicado pela própria companhia no site de relações com investidores (demonstrações,
relatório trimestral), com endereço e data."""


def _iso(x: object) -> str | None:
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if hasattr(x, "isoformat"):
        try:
            return x.isoformat()  # pandas Timestamp
        except Exception:  # pragma: no cover
            return str(x)
    texto = str(x)
    return texto or None


def prov_dict(p: Any) -> dict[str, Any]:
    """Proveniência (dataclass do A1, local ou ``dict``) → ``dict`` JSON estável."""
    if p is None:
        return {"fonte": "CODIGO", "url": None, "documento": None, "data_publicacao": None,
                "data_coleta": None, "sha256": None}
    if isinstance(p, Mapping):
        get = p.get
    else:
        def get(k: str, d: Any = None) -> Any:
            return getattr(p, k, d)
    url = get("url")
    doc = get("documento")
    sha = get("sha256")
    return {
        "fonte": str(get("fonte") or "CODIGO"),
        "url": None if url is None or (isinstance(url, float) and math.isnan(url)) else str(url),
        "documento": None if doc is None or (isinstance(doc, float) and math.isnan(doc))
        else str(doc),
        "data_publicacao": _iso(get("data_publicacao")),
        "data_coleta": _iso(get("data_coleta")),
        "sha256": None if sha is None or (isinstance(sha, float) and math.isnan(sha)) else str(sha),
    }


def prov_codigo(descricao: str) -> dict[str, Any]:
    """Proveniência de um valor derivado em código (o documento descreve a derivação)."""
    return {"fonte": "CODIGO", "url": None, "documento": descricao, "data_publicacao": None,
            "data_coleta": None, "sha256": None}


@dataclass
class Registro:
    """Acumula os passos do modelo aberto em ordem (determinística)."""

    passos: list[dict[str, Any]] = field(default_factory=list)

    def add(self, id: str, titulo: str, formula: str, substituicao: str,
            resultado: float | str | None, unidade: str,
            fontes: Iterable[Mapping[str, Any]] = (), texto: str | None = None,
            premissas: str | None = None) -> float | None:
        """Registra um passo; ``substituicao`` é a expressão com os números formatados (o
        resultado é acrescentado aqui como `` = <resultado>``); ``premissas``: valores de
        contexto exibidos à parte. Retorna o resultado numérico."""
        if isinstance(resultado, str):
            num = None
            txt = texto or resultado
        else:
            num = r6(resultado)
            txt = texto if texto is not None else valor(resultado, unidade)
        fs: list[dict[str, Any]] = []
        vistos: set[str] = set()
        for f in fontes:
            d = prov_dict(f)
            chave = "|".join(str(d.get(k)) for k in ("fonte", "url", "documento", "sha256"))
            if chave not in vistos:
                vistos.add(chave)
                fs.append(d)
        sub = substituicao if substituicao.rstrip().endswith(f"= {txt}") else f"{substituicao} = {txt}"
        self.passos.append({
            "id": id, "titulo": titulo, "formula": formula, "substituicao": sub,
            "resultado": num if num is not None else (None if not isinstance(resultado, str)
                                                      else resultado),
            "resultado_texto": txt, "unidade": unidade, "fontes": fs, "premissas": premissas,
        })
        return None if isinstance(resultado, str) else (
            None if resultado is None else float(resultado))

    def nota(self, id: str, titulo: str, texto: str,
             fontes: Iterable[Mapping[str, Any]] = ()) -> None:
        """Passo qualitativo (regra aplicada, decisão de método) sem resultado numérico."""
        self.passos.append({
            "id": id, "titulo": titulo, "formula": "", "substituicao": texto,
            "resultado": None, "resultado_texto": texto, "unidade": "texto",
            "fontes": [prov_dict(f) for f in fontes], "premissas": None,
        })


__all__ = ["FONTES_VALIDAS", "Proveniencia", "Registro", "prov_codigo", "prov_dict"]
