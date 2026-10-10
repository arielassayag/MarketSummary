"""Técnicas determinísticas portáteis, sem identidade ou permissão operacional.

Os operandos e configurações são declarados pelo chamador. Integridade de um
recurso de exemplo não constitui recepção financeira, PIT ou aprovação.
"""

from importlib import import_module
from typing import TYPE_CHECKING

from .avaliacao import avaliar_pb_justificado
from .capital import calcular_ke
from .execucao import estimar_preenchimento

_NATIVAS = {
    "decompor_risco": ".risco", "estimar_modelo_risco": ".risco",
    "construir_candidata": ".otimizacao", "conferir_limites": ".limites",
    "somar_atribuicao": ".atribuicao", "somar_componentes": ".atribuicao",
}
if TYPE_CHECKING:
    from .atribuicao import somar_atribuicao, somar_componentes
    from .limites import conferir_limites
    from .otimizacao import construir_candidata
    from .risco import decompor_risco, estimar_modelo_risco

__all__ = [
    "avaliar_pb_justificado", "calcular_ke", "estimar_preenchimento",
    "decompor_risco", "estimar_modelo_risco", "construir_candidata",
    "conferir_limites", "somar_atribuicao", "somar_componentes",
]


def __getattr__(nome: str):
    """Carrega somente a fachada nomeada, sem iniciar runtime ou buscar clone."""
    if nome not in _NATIVAS:
        raise AttributeError(nome)
    return getattr(import_module(_NATIVAS[nome], __name__), nome)
