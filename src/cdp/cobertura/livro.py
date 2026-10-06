"""Livro imutável da cobertura (``book/cobertura/``) — contrato congelado no W0 (dono: A).

Layout (DESIGN §A.5): ``livro.jsonl`` (append-only, encadeado por hash, um evento por
instrumento por execução: INICIACAO, REITERACAO, REVISAO, MUDANCA_RATING, SUSPENSAO, RETOMADA,
ENCERRAMENTO), ``<D>/manifest.json``, ``<D>/modelos.parquet``, ``<D>/modelos/<IID>.json``,
``<D>/etfs.parquet``, ``<D>/insumos/*.parquet`` e ``<D>/placar.json``. O snapshot ``D`` alimenta
a decisão SEGUINTE (sem look-ahead).

Consumidores: B (notas de pesquisa), C (portal) e E (sinal ``valuation_gap`` em sombra).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SnapshotCobertura:
    """Snapshot semanal (ou parcial) da cobertura, lido e conferido do livro.

    ``as_of``: data do snapshot (pregão de referência dos preços); ``pasta``:
    ``book/cobertura/<as_of>``; ``manifest``: conteúdo de ``manifest.json`` (as_of,
    prices_as_of, store_content_hash, hash da configuração de valuation, versão do código,
    insumos ``{arquivo: sha256}``, ``is_synthetic``, ``data_notice``); ``manifest_sha256``: hash
    do arquivo conferido contra o evento ``COVERAGE_SNAPSHOT``. O dono pode acrescentar campos
    (tabelas carregadas sob demanda) sem quebrar os consumidores."""

    as_of: date
    pasta: Path
    manifest: dict[str, Any] = field(default_factory=dict)
    manifest_sha256: str = ""
    is_synthetic: bool = False


def ultimo_snapshot(root: Path, ate: date) -> SnapshotCobertura | None:
    """Último snapshot com ``as_of <= ate`` sob ``root`` (a pasta ``book``), com manifesto e
    cadeia conferidos; ``None`` se não há snapshot até a data (nunca um posterior)."""
    raise NotImplementedError("cobertura.livro.ultimo_snapshot: em implementação (workstream A)")


__all__ = ["SnapshotCobertura", "ultimo_snapshot"]
