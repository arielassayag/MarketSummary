"""Múltiplo P/VPA justificado; não constitui rating de um emissor."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

    from ..cobertura.metodos import Arr


def avaliar_pb_justificado(roe: Arr, ke: Arr, g: Arr, *, estrito: bool = True) -> np.ndarray:
    """Preserva broadcast, forma, NaN e erro estrito do núcleo nativo."""
    from ..cobertura.metodos import pb_gordon

    return pb_gordon(roe, ke, g, estrito=estrito)
