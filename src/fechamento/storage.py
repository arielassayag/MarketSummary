"""Camada de persistência em SQLite para histórico de execuções, revisões e auditoria.

Gerencia o banco local fechamento.db de forma segura e determinística.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import RevisionRecord, WorkflowRun, WorkflowState

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    inputs_hash TEXT NOT NULL,
    facts_hash TEXT,
    draft_hash TEXT,
    approval_hash TEXT,
    approved_by TEXT,
    approved_at TEXT,
    blocking_reason TEXT,
    provider_used TEXT,
    latency_ms REAL,
    token_usage TEXT,
    cost_usd REAL
);

CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    revision_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    checks_passed INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS manual_time_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observer TEXT NOT NULL,
    task_name TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    time_minutes REAL NOT NULL,
    is_estimated INTEGER NOT NULL,
    logged_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
"""


class Storage:
    def __init__(self, db_path: str | Path = "fechamento.db") -> None:
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._conn = sqlite3.connect(":memory:")
            self._conn.row_factory = sqlite3.Row
        else:
            p = Path(self.db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(DB_SCHEMA)

    def save_run(self, run: WorkflowRun) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, scenario_id, state, created_at, updated_at,
                    inputs_hash, facts_hash, draft_hash, approval_hash,
                    approved_by, approved_at, blocking_reason, provider_used,
                    latency_ms, token_usage, cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.scenario_id,
                    run.state.value if hasattr(run.state, "value") else str(run.state),
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                    run.inputs_hash,
                    run.facts_hash,
                    run.draft_hash,
                    run.approval_hash,
                    run.approved_by,
                    run.approved_at.isoformat() if run.approved_at else None,
                    run.blocking_reason,
                    run.provider_used,
                    run.latency_ms,
                    json.dumps(run.token_usage) if run.token_usage else None,
                    run.cost_usd,
                ),
            )

    def get_run(self, run_id: str) -> WorkflowRun | None:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None

            return WorkflowRun(
                run_id=row["run_id"],
                scenario_id=row["scenario_id"],
                state=WorkflowState(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                inputs_hash=row["inputs_hash"],
                facts_hash=row["facts_hash"],
                draft_hash=row["draft_hash"],
                approval_hash=row["approval_hash"],
                approved_by=row["approved_by"],
                approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
                blocking_reason=row["blocking_reason"],
                provider_used=row["provider_used"],
                latency_ms=row["latency_ms"],
                token_usage=json.loads(row["token_usage"]) if row["token_usage"] else None,
                cost_usd=row["cost_usd"],
            )

    def list_runs(self, limit: int = 50) -> list[WorkflowRun]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            runs: list[WorkflowRun] = []
            for row in rows:
                runs.append(
                    WorkflowRun(
                        run_id=row["run_id"],
                        scenario_id=row["scenario_id"],
                        state=WorkflowState(row["state"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.fromisoformat(row["updated_at"]),
                        inputs_hash=row["inputs_hash"],
                        facts_hash=row["facts_hash"],
                        draft_hash=row["draft_hash"],
                        approval_hash=row["approval_hash"],
                        approved_by=row["approved_by"],
                        approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
                        blocking_reason=row["blocking_reason"],
                        provider_used=row["provider_used"],
                        latency_ms=row["latency_ms"],
                        token_usage=json.loads(row["token_usage"]) if row["token_usage"] else None,
                        cost_usd=row["cost_usd"],
                    )
                )
            return runs

    def add_revision(self, run_id: str, revision: RevisionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO revisions (
                    run_id, revision_number, text, text_hash,
                    checks_passed, created_by, created_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    revision.revision_number,
                    revision.text,
                    revision.text_hash,
                    1 if revision.checks_passed else 0,
                    revision.created_by,
                    revision.created_at.isoformat(),
                    revision.notes,
                ),
            )

    def get_revisions(self, run_id: str) -> list[RevisionRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM revisions WHERE run_id = ? ORDER BY revision_number ASC",
                (run_id,),
            )
            rows = cursor.fetchall()
            return [
                RevisionRecord(
                    revision_number=r["revision_number"],
                    text=r["text"],
                    text_hash=r["text_hash"],
                    checks_passed=bool(r["checks_passed"]),
                    created_by=r["created_by"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    notes=r["notes"] or "",
                )
                for r in rows
            ]

    def log_audit_event(self, run_id: str, event_type: str, details: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (run_id, event_type, details, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, event_type, details, datetime.now(UTC).isoformat()),
            )

    def get_audit_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM audit_events WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def log_manual_time(
        self,
        observer: str,
        task_name: str,
        scenario_id: str,
        time_minutes: float,
        is_estimated: bool,
        notes: str = "",
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO manual_time_logs (
                    observer, task_name, scenario_id, time_minutes,
                    is_estimated, logged_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observer,
                    task_name,
                    scenario_id,
                    time_minutes,
                    1 if is_estimated else 0,
                    datetime.now(UTC).isoformat(),
                    notes,
                ),
            )

    def get_manual_time_logs(self) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM manual_time_logs ORDER BY logged_at DESC")
            return [dict(r) for r in cursor.fetchall()]
