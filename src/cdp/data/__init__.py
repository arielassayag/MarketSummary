"""Camada de dados: coleta real (Yahoo, FINRA, B3/BDI, BCB, Google News), snapshots imutáveis
com SHA-256, repositório diário encadeado por hash (``MarketStore``) e mercado sintético.

Invariantes: dado ausente nunca vira zero; nada com data posterior a ``as_of`` entra num
snapshot; arquivos gravados nunca são sobrescritos; notícias são conteúdo NÃO confiável.
"""

from .snapshot import (
    BENCHMARKS,
    MARKET_INDICATORS,
    Fetchers,
    SnapshotError,
    SnapshotIntegrityError,
    build_snapshot,
    latest_snapshot,
    load_snapshot,
    snapshot_hash,
    write_snapshot,
)
from .store import (
    DataNotReadyError,
    IncrementManifest,
    MarketStore,
    NoSessionError,
    StoreLockedError,
)
from .synthetic import SYNTHETIC_NOTICE, make_synthetic_market

__all__ = [
    "BENCHMARKS",
    "DataNotReadyError",
    "MARKET_INDICATORS",
    "SYNTHETIC_NOTICE",
    "Fetchers",
    "IncrementManifest",
    "MarketStore",
    "NoSessionError",
    "SnapshotError",
    "SnapshotIntegrityError",
    "StoreLockedError",
    "build_snapshot",
    "latest_snapshot",
    "load_snapshot",
    "make_synthetic_market",
    "snapshot_hash",
    "write_snapshot",
]
