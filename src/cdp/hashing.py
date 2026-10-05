"""Hashes SHA-256 canônicos para vincular aprovações a versões exatas de dados e decisões."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

FLOAT_DIGITS = 10


def _normalize(obj: Any) -> Any:
    """Converte objetos para uma forma JSON determinística (ordem de chaves e floats estáveis)."""
    if isinstance(obj, BaseModel):
        return _normalize(obj.model_dump(mode="json"))
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(_normalize(v) for v in obj)
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            # NaN/inf nunca viram zero: são preservados como marcadores explícitos.
            return "NaN" if math.isnan(obj) else ("Infinity" if obj > 0 else "-Infinity")
        return round(obj, FLOAT_DIGITS)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return _normalize(obj.value)
    if isinstance(obj, Path):
        return obj.as_posix()
    # numpy / pandas escalares
    if hasattr(obj, "item"):
        return _normalize(obj.item())
    raise TypeError(f"Tipo não serializável para hash canônico: {type(obj)!r}")


def canonical_json(obj: Any) -> str:
    return json.dumps(_normalize(obj), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(obj: Any) -> str:
    """Hash de qualquer estrutura serializável (pydantic, dict, list, escalares)."""
    return sha256_text(canonical_json(obj))


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 16):
            h.update(chunk)
    return h.hexdigest()


def combine_hashes(*hashes: str) -> str:
    """Hash composto e ordenado por posição (a ordem dos componentes importa)."""
    return sha256_text("|".join(hashes))
