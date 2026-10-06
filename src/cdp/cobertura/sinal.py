"""Sinal de valuation para o alpha — contrato congelado no W0 (dono: A; consumidor: E).

``valuation_gap`` entra em ``alpha.signal_weights`` com peso 0,0 (sombra) até a promoção por IC
realizado (ICIR ≥ 0,5 em ≥ 13 semanas), com rebaixamento automático (DESIGN §A.7, decisão #13).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from .livro import SnapshotCobertura


def valuation_gap(snap: SnapshotCobertura) -> pd.Series:
    """``alpha_rel`` de cada emissor como z-score dentro de país × setor (winsorizado), indexado
    por ``issuer_id``; emissor sem preço-alvo fica ``NaN`` (nunca zero). A ortogonalização aos
    fatores é a mesma dos demais sinais (feita pelo consumidor)."""
    raise NotImplementedError("cobertura.sinal.valuation_gap: em implementação (workstream A)")


__all__ = ["valuation_gap"]
