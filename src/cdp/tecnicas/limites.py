"""Checagem de limites nativa sobre pesos/modelos/datas explicitamente recebidos.

Retorna HARD/SOFT/INFO; não adapta mandato ou risco, aprova, decide ou grava.
Convenções legadas de beta/fallback permanecem nas checagens e seus detalhes;
não constituem evidência primária ou autenticação das entradas.
"""
from cdp.portfolio.compliance import run_compliance as conferir_limites

__all__ = ["conferir_limites"]
