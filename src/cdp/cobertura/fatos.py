"""Fatos de valuation por emissor para a mente — contrato congelado no W0 (dono: A).

Os números da nota de pesquisa (B) e da ficha do ativo (C) só entram como ``{{fact:id}}``:
``val.<k>.{preco, preco_alvo (unidade "preco"), upside, alvo_otimista, alvo_pessimista,
prob_otimista, prob_pessimista, ke, wacc, g, etr, alpha, alpha_rel, rating_codigo,
confianca_codigo, pl_fwd, ev_ebitda_fwd, pb, cv_metodos, consenso_alvo, diff_consenso, sens.*}``,
``cob.<k>.*`` e ``evento.<k>.*`` (DESIGN §A.7), com ``point_in_time`` honesto.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..contracts import FactBook
    from ..market import MarketData
    from .livro import SnapshotCobertura


def factbook_emissor(snap: SnapshotCobertura, issuer_id: str, md: MarketData) -> FactBook:
    """FactBook do emissor = ``build_factbook`` base + fatos de valuation do snapshot + o
    conjunto de pares definido em código (fatos de outros emissores só para esses pares)."""
    raise NotImplementedError("cobertura.fatos.factbook_emissor: em implementação (workstream A)")


__all__ = ["factbook_emissor"]
