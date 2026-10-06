"""Fatos de valuation por emissor para a mente — contrato congelado no W0 (dono: A).

Os números da nota de pesquisa (B) e da ficha do ativo (C) só entram como ``{{fact:id}}``:
``val.<k>.{preco, preco_alvo (unidade "preco"), upside, alvo_otimista, alvo_pessimista,
prob_otimista, prob_pessimista, ke, wacc, g, etr, alpha, alpha_rel, rating_codigo,
confianca_codigo, pl_fwd, pb, cv_metodos, consenso_alvo, diff_consenso, sens.*}``,
``cob.<k>.*`` e ``evento.<k>.*`` (DESIGN §A.7), com ``point_in_time`` honesto.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..contracts import FactBook
    from ..market import MarketData
    from .livro import SnapshotCobertura

MAX_PARES = 8


def factbook_emissor(snap: SnapshotCobertura, issuer_id: str, md: MarketData) -> FactBook:
    """FactBook do emissor = ``build_factbook`` base + fatos de valuation do snapshot + o
    conjunto de pares definido em código (fatos de outros emissores só para esses pares).

    Pares: os do grupo usado no ``α_rel`` do modelo (país × setor, setor ou país), em ordem
    alfabética, até ``MAX_PARES``."""
    from ..analytics.panel import build_asset_panel
    from ..config import load_config
    from ..research.factbook import build_factbook, com_fatos_valuation

    if snap.as_of > md.as_of:
        raise ValueError("Snapshot da cobertura posterior aos dados de mercado (look-ahead).")
    cfg = load_config()
    mod = snap.modelo(issuer_id)
    if mod is None:
        estado = snap.estado()
        if issuer_id in estado.index:
            from .livro import snapshot

            mod = snapshot(snap.pasta.parent.parent,
                           date.fromisoformat(str(estado.loc[issuer_id, "snapshot"]))).modelo(issuer_id)
    pares = []
    if mod and mod.get("pares"):
        pares = [i for i in mod["pares"].get("emissores", []) if i != issuer_id][:MAX_PARES]
    ids = [issuer_id, *pares]
    ids = [i for i in ids if i in md.universe.issuers.index]
    panel = build_asset_panel(md, cfg)
    fb = build_factbook(panel, md, ids)
    return com_fatos_valuation(fb, snap, ids, incluir_etfs=True)


__all__ = ["MAX_PARES", "factbook_emissor"]
