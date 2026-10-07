"""API de autoridades externas: caminhos e digests vêm do chamador, fora do candidato."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .adapter import ContextoRI
from .custodia import ReceiptVault
from .identidade import IdentityVault, MasterAuthority
from .observado import Column, Document, Item, sha


def carregar_contexto_ri(manifesto, *, sha256_esperado):
    """Carrega configuração previamente confiada; o hash não nasce do pacote financeiro.

    Os roots internos mantêm seus próprios recibos e paths autenticados. Mover
    fontes exige novos recibos externos; esta API nunca reescreve sua custódia.
    """
    path = Path(manifesto).resolve()
    raw = path.read_bytes()
    if sha(raw) != sha256_esperado:
        raise ValueError("RI: configuração externa não corresponde ao digest fornecido")
    cfg = json.loads(raw)
    if cfg.get("schema") != "cdp.ri.configuracao_externa/v1":
        raise ValueError("RI: schema de configuração externa desconhecido")
    def resource(name):
        entry = cfg[name]
        file = Path(entry["path"])
        if not file.is_absolute():
            file = path.parent / file
        return file, entry["sha256"]
    master_path, master_sha = resource("master")
    identity_path, identity_sha = resource("identidade")
    custody_path, custody_sha = resource("custodia")
    master = MasterAuthority(master_path.read_bytes(), master_sha, anchor_path=master_path)
    identity = IdentityVault(identity_path.read_bytes(), identity_sha, master=master, config_path=identity_path)
    vault = ReceiptVault(custody_path.read_bytes(), custody_sha, manifest_path=custody_path)
    spec = cfg["documento"]
    doc = Document(spec["issuer_id"], spec["entity"], spec["currency"],
                   date.fromisoformat(spec["period_start"]), date.fromisoformat(spec["period_end"]),
                   tuple(spec["pages_context"]), spec["page_metadata"], spec["page_table"], spec["page_count"],
                   tuple(Column(c["label"], date.fromisoformat(c["end"])) for c in spec["columns"]),
                   tuple(Item(i["name"], i["label"]) for i in spec["items"]),
                   (spec["identity"][0], tuple(spec["identity"][1])), spec["listing_title"],
                   Decimal(spec["expected_scale"]))
    doc.validate()
    return ContextoRI(vault, identity, doc, cfg["ticker"], cfg["exchange"])


__all__ = ["carregar_contexto_ri"]
