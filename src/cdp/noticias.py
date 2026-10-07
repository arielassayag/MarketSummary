"""Apresentação de notícias públicas; os arquivos brutos e seus hashes ficam intactos."""

from __future__ import annotations

import re

# Nomes de bases proprietárias não são apresentados como fontes dos modelos da casa.
VEDADOS_NO_PORTAL = ("quar" + "tr", "dalo" + "opa", "fact" + "set", "capital" + " iq",
                     "refini" + "tiv", "bloomberg" + " terminal", "econo" + "matica")
_NOMES = re.compile("|".join(re.escape(n) for n in VEDADOS_NO_PORTAL), re.IGNORECASE)


def neutralizar_citacao(texto: str) -> str:
    """Neutraliza só o nome da fonte paga na apresentação, mantendo o restante da manchete."""
    return _NOMES.sub("fonte externa", texto)
