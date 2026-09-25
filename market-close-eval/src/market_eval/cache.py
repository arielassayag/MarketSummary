"""Cache SQLite (biblioteca padrão) para chamadas pagas de LLM.

Reexecutar o mesmo comando NÃO gera nova cobrança: toda geração/julgamento é
chaveado por um hash canônico dos parâmetros que definem a resposta.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import canonical_json, sha256_obj


def cache_key(parts: dict[str, object]) -> str:
    """Chave estável: sha256 do JSON canônico das partes."""
    return sha256_obj(parts)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ResponseCache:
    def __init__(self, sqlite_path: str | Path) -> None:
        path = Path(sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS responses (
                cache_key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                meta TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, kind: str, key: str) -> dict[str, object] | None:
        cur = self._conn.execute(
            "SELECT payload FROM responses WHERE cache_key = ? AND kind = ?", (key, kind)
        )
        row = cur.fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        assert isinstance(payload, dict)
        return payload

    def put(self, kind: str, key: str, payload: dict[str, Any], meta: dict[str, object] | None = None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO responses (cache_key, kind, payload, meta, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                key,
                kind,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(meta or {}, ensure_ascii=False),
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        cur = self._conn.execute("SELECT kind, COUNT(*) FROM responses GROUP BY kind")
        return {kind: int(n) for kind, n in cur.fetchall()}

    def close(self) -> None:
        self._conn.close()


def generation_cache_key(
    *,
    case_id: str,
    split: str,
    model_id: str,
    prompt_version: str,
    prompt_hash: str,
    common_system_hash: str,
    input_hash: str,
    repetition: int,
    generation_params: dict[str, object],
    schema_version: str,
) -> str:
    return cache_key(
        {
            "v": 1,
            "kind": "generation",
            "case_id": case_id,
            "split": split,
            "model_id": model_id,
            "prompt_version": prompt_version,
            "prompt_hash": prompt_hash,
            "common_system_hash": common_system_hash,
            "input_hash": input_hash,
            "repetition": repetition,
            "generation_params": generation_params,
            "schema_version": schema_version,
        }
    )


def judge_cache_key(
    *,
    candidate_output_hash: str,
    judge_model: str,
    judge_prompt_hash: str,
    reference_hash: str,
    judge_params: dict[str, object],
) -> str:
    return cache_key(
        {
            "v": 1,
            "kind": "judge_absolute",
            "candidate_output_hash": candidate_output_hash,
            "judge_model": judge_model,
            "judge_prompt_hash": judge_prompt_hash,
            "reference_hash": reference_hash,
            "judge_params": judge_params,
        }
    )


def pairwise_cache_key(
    *,
    output_a_hash: str,
    output_b_hash: str,
    judge_model: str,
    judge_prompt_hash: str,
    package_hash: str,
    judge_params: dict[str, object],
) -> str:
    return cache_key(
        {
            "v": 1,
            "kind": "judge_pairwise",
            "output_a_hash": output_a_hash,
            "output_b_hash": output_b_hash,
            "judge_model": judge_model,
            "judge_prompt_hash": judge_prompt_hash,
            "package_hash": package_hash,
            "judge_params": judge_params,
        }
    )


__all__ = [
    "ResponseCache",
    "cache_key",
    "canonical_json",
    "file_sha256",
    "generation_cache_key",
    "judge_cache_key",
    "pairwise_cache_key",
]
