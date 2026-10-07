"""Custódia financeira privada imutável; os freezes v1/v2 não são modificados.

Bytes da âncora são fixados pelo contexto confiado antes do documento. Cada
resolução revalida essa mesma âncora e os recibos/brutos por ela referidos.
Hashes não certificam um relógio externo nem primeira publicação.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .observado import ReceiptVault as LegacyReceiptVault
from .observado import sha


def _immutable(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _immutable(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_immutable(v) for v in value)
    return value


@dataclass(frozen=True, slots=True, init=False)
class ReceiptVault:
    """Autoridade fixa, sem dicionário interno exposto ou âncora recalculável.

    ``manifest_path`` monitora também o índice de backing quando fornecido.
    Sem esse caminho, a autoridade é o conjunto de bytes imutáveis recebido;
    não se alega monitoramento de um arquivo de índice não identificado.
    """
    _raw: bytes
    _anchor: str
    _path: Path | None

    def __init__(self, manifest_bytes: bytes, expected_manifest_sha: str, *, manifest_path: Path | None = None):
        if not isinstance(manifest_bytes, bytes) or sha(manifest_bytes) != expected_manifest_sha:
            raise ValueError("custódia v3: bytes diferentes da âncora financeira confiada")
        LegacyReceiptVault(manifest_bytes, expected_manifest_sha)
        object.__setattr__(self, "_raw", manifest_bytes)
        object.__setattr__(self, "_anchor", expected_manifest_sha)
        object.__setattr__(self, "_path", Path(manifest_path) if manifest_path is not None else None)
        self.authenticate()

    @property
    def manifest_sha256(self):
        self._validated_bytes()
        return self._anchor

    @property
    def manifest(self):
        # Uma árvore nova e recursivamente imutável; não é usada na resolução.
        return _immutable(json.loads(self._validated_bytes()))

    def _validated_bytes(self):
        if sha(self._raw) != self._anchor:
            raise ValueError("custódia v3: autoridade financeira interna adulterada")
        if self._path is not None and self._path.read_bytes() != self._raw:
            raise ValueError("custódia v3: índice financeiro alterado após autenticação")
        return self._raw

    def read(self, name):
        # Instância efêmera nunca exposta. Nenhuma âncora é calculada a partir
        # do estado mutável do candidato, recibo ou índice no disco.
        raw = self._validated_bytes()
        return LegacyReceiptVault(raw, self._anchor).read(name)

    def authenticate(self):
        for name in ("origem", "lista", "pdf"):
            self.read(name)
        return self._anchor
