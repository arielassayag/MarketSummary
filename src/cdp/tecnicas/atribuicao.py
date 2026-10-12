"""Atribuição dos registros nativos recebidos; sem leitura do livro ou recalcular D0.

P&L em USD; contribuição soma as frações diárias do PL inicial de cada dia, não é
retorno composto. days conserva cobertura parcial dos componentes observados.
"""
from cdp.ui.data import attribution_table as somar_atribuicao
from cdp.ui.data import components_table as somar_componentes

__all__ = ["somar_atribuicao", "somar_componentes"]
