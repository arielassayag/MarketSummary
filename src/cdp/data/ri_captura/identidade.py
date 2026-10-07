"""Autoridades privadas fixas por bytes/âncora; nenhum legado mutável persistente.

Roots externos são definidos pelo contexto confiado antes do candidato. Aqui se
protege sua continuidade; não se certifica um relógio externo/primeira publicação.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .custodia import _immutable
from .identidade_legada import IdentityVault as LegacyIdentityVault
from .identidade_legada import MasterAuthority as LegacyMasterAuthority
from .observado import sha


def _validated(raw, anchor, path, domain):
    if sha(raw) != anchor:
        raise ValueError(f"{domain} v4: autoridade interna diferente da âncora fixa")
    if path is not None and path.read_bytes() != raw:
        raise ValueError(f"{domain} v4: backing alterado após autenticação")
    return raw


@dataclass(frozen=True, slots=True, init=False)
class MasterAuthority:
    _raw: bytes
    _anchor: str
    _path: Path | None

    def __init__(self, anchor_bytes: bytes, expected_anchor_sha: str, *, anchor_path: Path | None = None):
        if not isinstance(anchor_bytes, bytes) or sha(anchor_bytes) != expected_anchor_sha:
            raise ValueError("master v4: root diferente da autoridade previamente confiada")
        LegacyMasterAuthority(anchor_bytes, expected_anchor_sha)
        object.__setattr__(self, "_raw", anchor_bytes)
        object.__setattr__(self, "_anchor", expected_anchor_sha)
        object.__setattr__(self, "_path", Path(anchor_path) if anchor_path is not None else None)
        self._bytes()

    def _bytes(self):
        return _validated(self._raw, self._anchor, self._path, "master")

    @property
    def anchor_sha256(self):
        self._bytes()
        return self._anchor

    @property
    def root(self):
        return _immutable(json.loads(self._bytes()))

    @property
    def master_sha256(self):
        self.authenticate()
        return json.loads(self._bytes())["master_sha256"]

    @property
    def observation_sha256(self):
        self.authenticate()
        return json.loads(self._bytes())["observacao_sha256"]

    def authenticate(self):
        # Instância efêmera, nunca guardada nem exposta como autoridade.
        LegacyMasterAuthority(self._bytes(), self._anchor)._read()
        self._bytes()
        return self._anchor

    def read_line(self, ticker, exchange):
        result = LegacyMasterAuthority(self._bytes(), self._anchor).read_line(ticker, exchange)
        self.authenticate()
        return result


@dataclass(frozen=True, slots=True, init=False)
class IdentityVault:
    _raw: bytes
    _anchor: str
    _master: MasterAuthority
    _path: Path | None

    def __init__(self, config_bytes: bytes, expected_config_sha: str, *, master: MasterAuthority,
                 config_path: Path | None = None):
        if type(master) is not MasterAuthority:
            raise ValueError("registro v4: exige master v4 exato previamente confiado")
        if not isinstance(config_bytes, bytes) or sha(config_bytes) != expected_config_sha:
            raise ValueError("registro v4: custódia diferente da âncora externa fixa")
        LegacyIdentityVault(config_bytes, expected_config_sha, master=master)
        object.__setattr__(self, "_raw", config_bytes)
        object.__setattr__(self, "_anchor", expected_config_sha)
        object.__setattr__(self, "_master", master)
        object.__setattr__(self, "_path", Path(config_path) if config_path is not None else None)
        self._bytes()

    def _bytes(self):
        raw = _validated(self._raw, self._anchor, self._path, "registro")
        if type(self._master) is not MasterAuthority:
            raise ValueError("registro v4: instância do master diferente da autoridade fixa")
        if json.loads(raw)["master_anchor_sha256"] != self._master.anchor_sha256:
            raise ValueError("registro v4: master diferente do root previamente confiado")
        return raw

    @property
    def config_sha256(self):
        self._bytes()
        return self._anchor

    @property
    def config(self):
        return _immutable(json.loads(self._bytes()))

    @property
    def master(self):
        self._bytes()
        return self._master

    def registration(self):
        self._master.authenticate()
        result = LegacyIdentityVault(self._bytes(), self._anchor, master=self._master).registration()
        self._master.authenticate()
        self._bytes()
        return result

    def authenticate(self):
        self.registration()
        return self._anchor
