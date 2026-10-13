"""Introspecção do contrato público sem executar os cálculos."""
from typing import get_type_hints

import numpy as np

from cdp.cobertura.metodos import Arr
from cdp.tecnicas import avaliar_pb_justificado


def test_contrato_pb_disponivel_para_introspeccao_runtime():
    hints = get_type_hints(avaliar_pb_justificado)
    assert hints == {"roe": Arr, "ke": Arr, "g": Arr,
                     "estrito": bool, "return": np.ndarray}
