"""Risco idiossincrático: decomposição da decisão e série monitorada — contrato congelado no W0
(dono: workstream E; consumidores: C no portal e D no relatório semanal).

Definição (DESIGN §E.1): ``S_idio = wᵀDw / (κ_F·wᵀBFBᵀw + wᵀDw)`` na carteira ATINGIDA, com a
covariância conservadora (mercado, país, setor, estilo e bloco macro) e inflação de 2ª ordem κ_F.
Meta ``risk.idio_share_goal`` e piso ``risk.idio_share_floor`` (nunca relaxado).

Gravação sem mudar contratos com hash: a decisão guarda ``Proposal.overrides["risco"]`` com
``idio_decisao``, ``idio_base``, ``kappa_f``, ``por_grupo`` (chaves :data:`GRUPOS_IDIO`, frações
da variância que somam 1), ``custo_neutralidade_bp`` e ``vinculantes``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from ..config import FundConfig
    from ..contracts import DailyRecord, Proposal
    from ..market import MarketData

#: Chave de ``Proposal.overrides`` com a decomposição de risco da decisão.
CHAVE_RISCO = "risco"
#: Grupos da decomposição da variância ex-ante (``por_grupo``).
GRUPOS_IDIO = ("mercado", "pais", "setor", "estilo", "macro", "especifico")


def serie_idio(records: Sequence[DailyRecord], md: MarketData, cfg: FundConfig) -> dict[str, Any]:
    """Série diária da fatia idiossincrática por três medidas: ex-ante (``DailyRisk.factor_vol``
    e ``specific_vol`` já gravados), realizada em 63 pregões (x-sigma-rho
    ``σ_S·ρ(r_S, r_p)/σ_p``) e sem modelo (``1 − R²`` dos retornos diários do fundo contra ILF,
    EWZ, EWW, ECH, EPU, COLO, ARGT, BZ=F, HG=F, GC=F e DX-Y.NYB); ausente fica ``None``."""
    raise NotImplementedError("risk.idio.serie_idio: em implementação (workstream E)")


def decomposicao_decisao(proposal: Proposal) -> dict[str, Any]:
    """Decomposição gravada na decisão (``proposal.overrides["risco"]``); propostas anteriores à
    regra (sem a chave) devolvem a decomposição indisponível, nunca recalculada com outro mandato.
    """
    raise NotImplementedError("risk.idio.decomposicao_decisao: em implementação (workstream E)")


__all__ = ["CHAVE_RISCO", "GRUPOS_IDIO", "decomposicao_decisao", "serie_idio"]
