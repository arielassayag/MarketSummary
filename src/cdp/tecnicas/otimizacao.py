"""Otimização nativa sobre objetos declarados; candidato em memória, sem decisão.

Alpha residual anual e pesos em fração, PL em USD e unidades do CostModel nativo.
Configuração e restrições são explícitas; overrides só apertam o contrato nativo.
Status do solver não equivale a aprovação, booking ou efetivação monetária MOC.
"""
from cdp.portfolio.optimizer import optimize as construir_candidata

__all__ = ["construir_candidata"]
