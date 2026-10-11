"""Texto da recusa de risco, isolado e sem modelo financeiro (DADOS SIMULADOS)."""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.config import FundConfig
from cdp.contracts import SnapshotManifest
from cdp.hashing import sha256_obj
from cdp.workflow import risco_diario as rd


@pytest.mark.parametrize("basis", ["base", "evento"])
@pytest.mark.parametrize(
    ("field", "value"),
    [("vol", 0.125), ("reasons", ["divergência simulada de teste"])],
    ids=["escalar", "lista"],
)
def test_verify_recusa_divergencia_com_medidas_integrais(tmp_path, monkeypatch, basis, field, value):
    """O load é isolado; este teste prova mensagem/recusa, não autenticação ou B/F/D."""
    session = date(2023, 12, 4)
    cfg = FundConfig().with_overrides({"risk_model": {"macro_factors": []}})
    config = cfg.model_dump(mode="json")
    manifest = SnapshotManifest(
        snapshot_id="diagnostico-simulado",
        as_of=session,
        created_at=datetime(2023, 12, 4, tzinfo=UTC),
        universe_sha256="0" * 64,
        files=[],
        is_synthetic=True,
        data_notice="DADOS SIMULADOS",
    )
    record = SimpleNamespace(
        date=session,
        input_hashes={
            rd.MARKER: "1" * 64,
            "market_data": manifest.content_hash(),
            "config": sha256_obj(config),
        },
        positions=[],
        nav_end_usd=1.0,
        record_hash="2" * 64,
    )
    computed = rd.measures(None, pd.Series(dtype=float), [], 1.0)
    archived = {name: copy.deepcopy(computed) for name in ("base", "evento")}
    archived[basis][field] = value
    diagnostic = {
        "config": config,
        "config_hash": sha256_obj(config),
        "config_bytes_sha256": rd.sha256_text(rd.text(config)),
        "sources": {"current": {"manifest": manifest.model_dump(mode="json")}},
        "weights": {},
        "nav_usd": 1.0,
        "models": {"base": None, "evento": None, "previous": None},
        "required_macro": [],
        "cutoffs": {
            "base_as_of": None,
            "previous_base_as_of": None,
            "event_session": str(session),
            "returns_through": str(session),
        },
        "kappa_f": 1.0,
        "kappa_info": {"mode": "legado"},
        "measures": archived,
    }
    track = SimpleNamespace(
        root=tmp_path,
        records=lambda: [record],
        audit_event="DAILY_RECORD",
        audit=SimpleNamespace(events=lambda: []),
    )
    monkeypatch.setattr(rd, "load", lambda *_args: diagnostic)

    problems = rd.verify(track)

    assert len(problems) == 1
    prefix = f"{session}: medidas base/evento não recalculam: "
    assert problems[0].startswith(prefix)
    detail = json.loads(problems[0][len(prefix):])
    assert detail == {"modelo": basis, "computed": computed, "archived": archived[basis]}
    assert detail["archived"][field] == value
