"""O relógio histórico não autentica mérito prospectivo, inclusive com preços reais."""

import json
from datetime import UTC, datetime

import pytest

from cdp.config import load_config
from cdp.research.evaluation import AuthenticatedViewTracker
from cdp.workflow.book import Book, dump_json
from cdp.workflow.origem import (
    ORIGIN_FILE,
    ReplayOrigin,
    install_replay_origin,
    read_replay_origin,
)


def origin(mode="sombra_real"):
    return ReplayOrigin(mode=mode, actual_started_at=datetime(2026, 10, 7, tzinfo=UTC),
                        run_manifest_sha256="a" * 64, source_manifest_sha256="b" * 64)


@pytest.mark.parametrize("mode", ["sombra_real", "simulado", "pit_auditado"])
def test_origins_are_authenticated_but_never_prospective(tmp_path, mode):
    book = Book(tmp_path / "book")
    installed = install_replay_origin(book, origin(mode))
    assert read_replay_origin(book) == installed
    assert book.verify_integrity() == (True, [])
    anchor = book.audit_head()
    assert install_replay_origin(book, origin(mode)) == installed
    assert book.audit_head() == anchor
    tracker = AuthenticatedViewTracker(book.root, mind="codex", include_synthetic=True)
    with pytest.raises(ValueError, match="retrospectivo"):
        tracker.ic_history()
    cfg = load_config()
    assert tracker.phase_gate(cfg)[0] == cfg.research.llm_phase
    assert "retrospectivo" in tracker.phase_gate(cfg)[1]


@pytest.mark.parametrize("damage", ["delete", "edit", "symlink", "event_delete"])
def test_origin_deletion_or_edit_blocks_book(tmp_path, damage):
    book = Book(tmp_path / "book")
    install_replay_origin(book, origin())
    path = book.root / ORIGIN_FILE
    if damage == "delete":
        path.unlink()
    elif damage == "edit":
        path.write_text(dump_json(origin("pit_auditado")))
    elif damage == "symlink":
        target = tmp_path / "external.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    else:
        book.audit.path.unlink()
    ok, errors = book.verify_integrity()
    assert not ok and any("origem" in e for e in errors)
    with pytest.raises(ValueError):
        read_replay_origin(book)


def test_legacy_book_bytes_and_first_event_unchanged(tmp_path):
    book = Book(tmp_path / "book")
    book.audit.append("LEGACY", "sistema", {"dado": 1})
    before = book.audit.path.read_bytes()
    assert read_replay_origin(book) is None
    assert book.verify_integrity() == (True, [])
    assert book.audit.path.read_bytes() == before
    with pytest.raises(ValueError, match="convertido"):
        install_replay_origin(book, origin())
    assert book.audit.path.read_bytes() == before


def test_origin_requires_actual_timezone_and_initial_anchor(tmp_path):
    with pytest.raises(ValueError, match="fuso"):
        ReplayOrigin(mode="simulado", actual_started_at=datetime(2026, 10, 7),
                     run_manifest_sha256="a" * 64, source_manifest_sha256="b" * 64)
    book = Book(tmp_path / "book")
    book.audit.append("EARLIER", "sistema", {})
    (book.root / ORIGIN_FILE).write_text(dump_json(origin()))
    with pytest.raises(ValueError, match="âncora"):
        read_replay_origin(book)


def test_resume_rejects_modified_audit_before_operations(tmp_path):
    book = Book(tmp_path / "book")
    installed = install_replay_origin(book, origin())
    event = json.loads(book.audit.path.read_text())
    event["prev_hash"] = "c" * 64
    book.audit.path.write_text(json.dumps(event) + "\n")
    for action in (lambda: read_replay_origin(book),
                   lambda: install_replay_origin(book, installed)):
        with pytest.raises(ValueError, match="cadeia adulterada"):
            action()
