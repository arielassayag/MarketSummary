"""Origem retrospectiva autenticada, sem alterar os hashes dos livros legados.

O relógio lógico de um ensaio não comprova pré-registro no mundo real. A marca
é selada antes de qualquer operação e impede usar o replay no IC prospectivo.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..hashing import sha256_file, sha256_obj

if TYPE_CHECKING:
    from .book import Book

ORIGIN_FILE = "replay_origin.json"
ORIGIN_EVENT = "REPLAY_ORIGIN"
SCHEMA = "cdp.replay.origin/v1"


class ReplayOrigin(BaseModel):
    """Origem imutável ligada ao manifesto completo da execução isolada."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["cdp.replay.origin/v1"] = SCHEMA
    mode: Literal["simulado", "sombra_real", "pit_auditado"]
    clock_kind: Literal["historico"] = "historico"
    actual_started_at: datetime
    run_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prospective: Literal[False] = False

    @field_validator("actual_started_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A captura real da origem exige fuso horário.")
        return value


def read_replay_origin(book: Book) -> ReplayOrigin | None:
    """Confere marca/âncora nas duas direções; ausência em livro legado é válida."""
    path = book.root / ORIGIN_FILE
    events = book.audit.events()
    seals = [e for e in events if e.event_type == ORIGIN_EVENT]
    if not path.exists() and not path.is_symlink() and not seals:
        return None
    valid, reason = book.audit.verify_chain()
    if not valid:
        raise ValueError(f"Origem do replay tem cadeia adulterada: {reason}")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Origem do replay ausente ou redirecionada.")
    if len(seals) != 1 or seals[0].seq != 0:
        raise ValueError("Origem do replay exige uma única âncora antes das operações.")
    origin = ReplayOrigin.model_validate_json(path.read_text(encoding="utf-8"))
    payload = {"arquivo": ORIGIN_FILE, "sha256": sha256_file(path)}
    if seals[0].payload_hash != sha256_obj(payload):
        raise ValueError("Origem do replay diverge da âncora de auditoria.")
    if seals[0].ts != origin.actual_started_at:
        raise ValueError("Instante real da origem diverge da âncora de auditoria.")
    return origin


def install_replay_origin(book: Book, origin: ReplayOrigin) -> ReplayOrigin:
    """Sela a origem em livro novo; recupera apenas a escrita sem evento inicial."""
    from .book import _write_exclusive, dump_json

    path = book.root / ORIGIN_FILE
    if book.audit.events():
        current = read_replay_origin(book)
        if current != origin:
            raise ValueError("Livro iniciado com outra origem; não pode ser convertido em replay.")
        return current
    # A janela arquivo→evento pode ser retomada somente com bytes idênticos.
    text = dump_json(origin)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or path.read_text(encoding="utf-8") != text:
            raise ValueError("Marca de origem preexistente diverge da execução.")
    else:
        _write_exclusive(path, text)
    book.audit.append(ORIGIN_EVENT, "sistema", {"arquivo": ORIGIN_FILE,
                      "sha256": sha256_file(path)},
                      summary="Ensaio retrospectivo; fora do IC prospectivo.",
                      ts=origin.actual_started_at)
    return read_replay_origin(book)
