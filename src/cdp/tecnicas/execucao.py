"""Estimativa de ações preenchidas, sem decisão, booking ou publicação."""
import math
from numbers import Integral


def estimar_preenchimento(ordem_acoes: int, capacidade_usd: float, preco_usd: float) -> int:
    """Delega capacidade/sinal/arredondamento; operandos ausentes são recusados.

    Preço e capacidade devem ser números finitos declarados, inclusive para ordem
    zero. Capacidade finita não positiva preserva o preenchimento zero nativo.
    """
    if isinstance(ordem_acoes, bool) or not isinstance(ordem_acoes, Integral):
        raise ValueError("Ordem deve ser uma quantidade inteira declarada")
    for nome, value in (("capacidade_usd", capacidade_usd), ("preco_usd", preco_usd)):
        if value is None or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"Operando ausente/não finito: {nome}")
    from ..portfolio.execucao import preencher

    return preencher(ordem_acoes, capacidade_usd, preco_usd)
