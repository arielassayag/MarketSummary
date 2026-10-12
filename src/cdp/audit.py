"""Trilha de auditoria append-only encadeada por hash (tamper-evident).

Cada evento grava o hash do evento anterior; qualquer edição, remoção ou reordenação de
linhas quebra a cadeia e é detectada por :func:`verify_chain`.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TextIO

from cdp.leitura_arquivos import em_leitura, ler_texto, recusar_escrita, validar_modo

from .contracts import AuditEvent
from .hashing import sha256_obj

GENESIS_HASH = "0" * 64


@contextmanager
def _trava_append(stream: TextIO):
    """Seção crítica entre processos: leitura da cauda até o flush do novo evento."""
    if os.name == "nt":  # pragma: no cover — qualificação local em POSIX
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _event_hash(seq: int, ts: datetime, event_type: str, actor: str, week: date | None,
                payload_hash: str, summary: str, prev_hash: str) -> str:
    return sha256_obj({
        "seq": seq, "ts": ts, "event_type": event_type, "actor": actor, "week": week,
        "payload_hash": payload_hash, "summary": summary, "prev_hash": prev_hash,
    })


class AuditLog:
    def __init__(self, path: str | Path, *, somente_leitura: bool = False) -> None:
        self.somente_leitura = validar_modo(somente_leitura)
        self.path = Path(path)
        if not em_leitura(self.somente_leitura):
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def events(self) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        out: list[AuditEvent] = []
        for line in ler_texto(self.path, encoding='utf-8').splitlines():
            if line.strip():
                out.append(AuditEvent.model_validate_json(line))
        return out

    def append(self, event_type: str, actor: str, payload: Any, summary: str = "",
               week: date | None = None, ts: datetime | None = None) -> AuditEvent:
        recusar_escrita(self.somente_leitura)
        with self.path.open("a+", encoding="utf-8") as f, _trava_append(f):
            existing = self.events()
            prev_hash = existing[-1].event_hash if existing else GENESIS_HASH
            seq = existing[-1].seq + 1 if existing else 0
            ts = ts or datetime.now(UTC)
            payload_hash = sha256_obj(payload)
            event = AuditEvent(
                seq=seq, ts=ts, event_type=event_type, actor=actor, week=week,
                payload_hash=payload_hash, summary=summary, prev_hash=prev_hash,
                event_hash=_event_hash(seq, ts, event_type, actor, week,
                                       payload_hash, summary, prev_hash),
            )
            f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
            f.flush()
        return event

    def verify_chain(self) -> tuple[bool, str]:
        prev = GENESIS_HASH
        for i, ev in enumerate(self.events()):
            if ev.seq != i:
                return False, f"Sequência quebrada no evento {i} (seq={ev.seq})."
            if ev.prev_hash != prev:
                return False, f"Encadeamento quebrado no evento {i}."
            expected = _event_hash(ev.seq, ev.ts, ev.event_type, ev.actor, ev.week,
                                   ev.payload_hash, ev.summary, ev.prev_hash)
            if expected != ev.event_hash:
                return False, f"Conteúdo adulterado no evento {i}."
            prev = ev.event_hash
        return True, "Cadeia íntegra."
