"""Logging estruturado sem conteúdo sensível (chaves de API nunca são logadas)."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")


def redact(message: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", message)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = redact(str(record.exc_info[1])) if record.exc_info[1] else "error"
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler: logging.Handler
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    parts = " ".join(f"{k}={fields[k]}" for k in sorted(fields))
    logger.info("%s %s", event, parts)
