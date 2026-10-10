"""Técnicas determinísticas portáteis, sem identidade ou permissão operacional.

Os operandos e configurações são declarados pelo chamador. Integridade de um
recurso de exemplo não constitui recepção financeira, PIT ou aprovação.
"""

from .avaliacao import avaliar_pb_justificado
from .capital import calcular_ke
from .execucao import estimar_preenchimento

__all__ = ["avaliar_pb_justificado", "calcular_ke", "estimar_preenchimento"]
