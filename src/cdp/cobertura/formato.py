"""Formatação pt-BR dos números do modelo aberto (vírgula decimal, ponto de milhar).

Todo texto numérico que a página exibe (fórmulas substituídas, resultados, tabelas de insumos)
é produzido aqui, em Python. A página nunca formata nem calcula: só mostra o texto.

Convenções:

- taxas e retornos em decimal → ``5,07%`` (``pct``), com sinal opcional (``+12,30%``);
- múltiplos → ``1,46x``;
- preços por ação → ``R$ 45,20``, ``US$ 12,34``, ``MXN 31,50`` (``preco``);
- valores totais → escala automática (``R$ 12,3 bi``, ``US$ 450,0 mi``);
- números puros → ``0,93``; contagens → ``1.234``;
- ausente → ``n/d`` (nunca zero);
- negativos com o sinal tipográfico de menos (U+2212); como operando de uma conta, entre
  parênteses (``operando``): ``R$ 10,00 − (−R$ 0,63)``.
"""

from __future__ import annotations

import math

NA = "n/d"
MENOS = "\u2212"

SIMBOLO_MOEDA = {"BRL": "R$", "USD": "US$"}


def _ok(x: object) -> bool:
    if x is None:
        return False
    try:
        return math.isfinite(float(x))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _br(v: float, casas: int) -> str:
    texto = f"{abs(v):,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _sinal(v: float, casas: int, sinal: bool) -> str:
    if round(abs(v), casas) == 0:
        return ""
    if v < 0:
        return MENOS
    return "+" if sinal else ""


def num(x: float | None, casas: int = 2, sinal: bool = False) -> str:
    """``0.9312`` → ``0,93``; ``1234.5`` → ``1.234,50``."""
    if not _ok(x):
        return NA
    v = float(x)  # type: ignore[arg-type]
    return f"{_sinal(v, casas, sinal)}{_br(v, casas)}"


def pct(x: float | None, casas: int = 2, sinal: bool = False) -> str:
    """Decimal → percentual: ``0.0507`` → ``5,07%``."""
    if not _ok(x):
        return NA
    v = float(x) * 100.0  # type: ignore[arg-type]
    return f"{_sinal(v, casas, sinal)}{_br(v, casas)}%"


def pp(x: float | None, casas: int = 1, sinal: bool = True) -> str:
    """Diferença de taxas em pontos percentuais: ``0.031`` → ``+3,1 p.p.``."""
    if not _ok(x):
        return NA
    v = float(x) * 100.0  # type: ignore[arg-type]
    return f"{_sinal(v, casas, sinal)}{_br(v, casas)} p.p."


def mult(x: float | None, casas: int = 2) -> str:
    if not _ok(x):
        return NA
    v = float(x)  # type: ignore[arg-type]
    return f"{_sinal(v, casas, False)}{_br(v, casas)}x"


def simbolo(moeda: str | None) -> str:
    m = (moeda or "").upper()
    return SIMBOLO_MOEDA.get(m, m or "?")


def preco(x: float | None, moeda: str | None, casas: int = 2) -> str:
    """Preço por ação/linha na moeda: ``R$ 45,20``."""
    if not _ok(x):
        return NA
    v = float(x)  # type: ignore[arg-type]
    if abs(v) >= 100000:
        casas = 0
    return f"{MENOS if v < 0 and round(abs(v), casas) else ''}{simbolo(moeda)} {_br(v, casas)}"


def total(x: float | None, moeda: str | None) -> str:
    """Valor total com escala: ``R$ 12,3 bi``, ``US$ 450,0 mi``, ``CLP 1,2 tri``."""
    if not _ok(x):
        return NA
    v = float(x)  # type: ignore[arg-type]
    s = MENOS if v < 0 else ""
    a = abs(v)
    sim = simbolo(moeda)
    if a >= 1e12:
        return f"{s}{sim} {_br(a / 1e12, 2)} tri"
    if a >= 1e9:
        return f"{s}{sim} {_br(a / 1e9, 2)} bi"
    if a >= 1e6:
        return f"{s}{sim} {_br(a / 1e6, 1)} mi"
    return f"{s}{sim} {_br(a, 0)}"


def contagem(x: float | None) -> str:
    if not _ok(x):
        return NA
    v = float(x)  # type: ignore[arg-type]
    a = abs(v)
    s = MENOS if v < 0 else ""
    if a >= 1e9:
        return f"{s}{_br(a / 1e9, 3)} bi"
    if a >= 1e6:
        return f"{s}{_br(a / 1e6, 2)} mi"
    return f"{s}{_br(a, 0)}"


def operando(texto: str) -> str:
    """Valor já formatado usado como operando de uma conta: negativo vai entre parênteses
    (``− (−10,70%)``, nunca ``− -10,70%``)."""
    return f"({texto})" if texto.startswith((MENOS, "-")) else texto


def inteiro(x: float | None) -> str:
    """Contagem com separador de milhar: ``2000`` → ``2.000``."""
    return num(x, 0)


def valor(x: float | None, unidade: str) -> str:
    """Formatação canônica pela unidade do passo/insumo.

    Unidades: ``%`` (decimal), ``p.p.``, ``x``, ``preco:<MOEDA>``, ``total:<MOEDA>``,
    ``fx:<DE>/<PARA>``, ``acoes``, ``anos``, ``dias``, ``n`` (número puro), ``prob``.
    """
    if unidade == "%":
        return pct(x)
    if unidade == "p.p.":
        return pp(x)
    if unidade == "x":
        return mult(x)
    if unidade.startswith("preco:"):
        return preco(x, unidade.split(":", 1)[1])
    if unidade.startswith("total:"):
        return total(x, unidade.split(":", 1)[1])
    if unidade.startswith("fx:"):
        return num(x, 6)
    if unidade == "acoes":
        return contagem(x)
    if unidade == "anos":
        return f"{num(x, 1)} anos" if _ok(x) else NA
    if unidade == "dias":
        return f"{num(x, 0)} dias" if _ok(x) else NA
    if unidade == "prob":
        return pct(x, 1)
    return num(x, 4 if _ok(x) and abs(float(x)) < 10 else 2)  # type: ignore[arg-type]


def r6(x: float | None) -> float | None:
    """Arredonda a 6 algarismos significativos (armazenamento determinístico)."""
    if not _ok(x):
        return None
    v = float(x)  # type: ignore[arg-type]
    if v == 0:
        return 0.0
    return float(f"{v:.6g}")


__all__ = ["MENOS", "NA", "contagem", "inteiro", "mult", "num", "operando", "pct", "pp", "preco", "r6",
           "simbolo", "total", "valor"]
