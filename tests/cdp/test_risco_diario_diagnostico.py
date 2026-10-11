"""Texto da recusa de risco, isolado e sem modelo financeiro (DADOS SIMULADOS)."""

from __future__ import annotations

import copy
import json
import math
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
def test_verify_recusa_divergencia_com_medidas_integrais(
    tmp_path, monkeypatch, basis, field, value
):
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
    detail = json.loads(problems[0][len(prefix) :])
    assert detail == {"modelo": basis, "computed": computed, "archived": archived[basis]}
    assert detail["archived"][field] == value


# Pares recebidos do run Linux 38180259231, sem rederivação de modelo:
# DIFERENCAS_LINUX_MEDIDAS.json SHA 899939c6f37e617e2e86d68142c22fa65f3e2e250258571f0f0056094ba4aaba.
_REAL_LINUX_PAIRS = [
    ("factor_vol", 0.00562629747537935, 0.005626297475379351),
    ("factor_vol", 0.0063916506533837495, 0.006391650653383748),
    ("idio_kf", 0.9520905974492331, 0.9520905974492333),
    ("vol_kf", 0.035163059328974386, 0.03516305932897438),
]
_REAL_LINUX_COMPONENTS = [
    {
        "archived": {
            "complete": True,
            "factor_vol": 0.005626297475379351,
            "idio": 0.9586172113534719,
            "idio_kf": 0.9410919570534119,
            "missing_macro": [],
            "outside_model": [],
            "reasons": [],
            "specific_vol": 0.027079174769912073,
            "vol": 0.02765749318902389,
            "vol_kf": 0.02791382775574786,
        },
        "computed": {
            "complete": True,
            "factor_vol": 0.00562629747537935,
            "idio": 0.9586172113534719,
            "idio_kf": 0.9410919570534119,
            "missing_macro": [],
            "outside_model": [],
            "reasons": [],
            "specific_vol": 0.027079174769912073,
            "vol": 0.02765749318902389,
            "vol_kf": 0.02791382775574786,
        },
        "modelo": "base",
    },
    {
        "archived": {
            "complete": True,
            "factor_vol": 0.006391650653383748,
            "idio": 0.9664603506176422,
            "idio_kf": 0.9520905974492333,
            "missing_macro": [],
            "outside_model": [],
            "reasons": [],
            "specific_vol": 0.03431040081614271,
            "vol": 0.034900670512746125,
            "vol_kf": 0.03516305932897438,
        },
        "computed": {
            "complete": True,
            "factor_vol": 0.0063916506533837495,
            "idio": 0.9664603506176422,
            "idio_kf": 0.9520905974492331,
            "missing_macro": [],
            "outside_model": [],
            "reasons": [],
            "specific_vol": 0.03431040081614271,
            "vol": 0.034900670512746125,
            "vol_kf": 0.035163059328974386,
        },
        "modelo": "base",
    },
]
_NUMERIC_FIELDS = ("vol", "vol_kf", "factor_vol", "specific_vol", "idio", "idio_kf")


def _comparison_example():
    """Dicionário simulado para política de comparação; não representa B/F/D autenticados."""
    return {
        "complete": True,
        "reasons": [],
        "missing_macro": [],
        "outside_model": [],
        **{field: 0.125 for field in _NUMERIC_FIELDS},
    }


@pytest.mark.parametrize(
    ("field", "computed", "archived"),
    _REAL_LINUX_PAIRS,
    ids=["efetivo-factor-vol", "sombra-factor-vol", "sombra-idio-kf", "sombra-vol-kf"],
)
def test_comparacao_aceita_quatro_pares_reais_linux(field, computed, archived):
    current, saved = _comparison_example(), _comparison_example()
    current[field], saved[field] = computed, archived
    assert rd._measures_equal(current, saved)


@pytest.mark.parametrize("component", _REAL_LINUX_COMPONENTS, ids=["efetivo", "sombra"])
def test_comparacao_aceita_objetos_integrais_recebidos_linux(component):
    assert rd._measures_equal(component["computed"], component["archived"])


@pytest.mark.parametrize("field", _NUMERIC_FIELDS)
@pytest.mark.parametrize("case", ["ulp", "none", "zero", "none-current", "none-saved"])
def test_comparacao_derivados_ulp_none_zero(field, case):
    current, saved = _comparison_example(), _comparison_example()
    expected = True
    if case == "ulp":
        saved[field] = math.nextafter(current[field], math.inf)
    elif case == "none":
        current[field] = saved[field] = None
    elif case == "zero":
        current[field] = saved[field] = 0.0
    else:
        (current if case == "none-current" else saved)[field] = None
        expected = False
    assert rd._measures_equal(current, saved) is expected


@pytest.mark.parametrize("field", _NUMERIC_FIELDS)
def test_comparacao_rejeita_divergencia_material(field):
    current, saved = _comparison_example(), _comparison_example()
    saved[field] = 0.25
    assert not rd._measures_equal(current, saved)


@pytest.mark.parametrize("field", _NUMERIC_FIELDS)
@pytest.mark.parametrize(
    "invalid",
    [True, "0.125", math.nan, math.inf, -math.inf],
    ids=["bool", "string", "nan", "inf", "negative-inf"],
)
@pytest.mark.parametrize("side", ["computed", "archived"])
def test_comparacao_rejeita_tipo_ou_valor_nao_finito(field, invalid, side):
    current, saved = _comparison_example(), _comparison_example()
    (current if side == "computed" else saved)[field] = invalid
    assert not rd._measures_equal(current, saved)


@pytest.mark.parametrize(
    "change",
    [
        "missing-key",
        "extra-key",
        "status",
        "status-type",
        "reasons",
        "missing-macro",
        "outside-model",
        "list-order",
        "list-type",
        "list-element-type",
        "other-numeric-field",
        "other-numeric-type",
        "other-dict-type",
        "derived-bool-both",
        "derived-string-both",
        "derived-nan-both",
        "derived-inf-both",
    ],
)
def test_comparacao_metadados_chaves_e_outros_campos_exatos(change):
    current, saved = _comparison_example(), _comparison_example()
    if change == "missing-key":
        saved.pop("vol")
    elif change == "extra-key":
        saved["extra"] = "campo novo"
    elif change == "status":
        saved["complete"] = False
    elif change == "status-type":
        saved["complete"] = 1
    elif change in ("reasons", "missing-macro", "outside-model"):
        saved[change.replace("-", "_")] = ["divergência simulada"]
    elif change == "list-order":
        current["reasons"], saved["reasons"] = ["a", "b"], ["b", "a"]
    elif change == "list-type":
        saved["reasons"] = ()
    elif change == "list-element-type":
        current["reasons"], saved["reasons"] = [True], [1]
    elif change == "other-numeric-field":
        current["extra"] = 0.125
        saved["extra"] = math.nextafter(0.125, math.inf)
    elif change == "other-numeric-type":
        current["extra"], saved["extra"] = 1, 1.0
    elif change == "other-dict-type":
        current["extra"], saved["extra"] = {"a": [True]}, {"a": [1]}
    else:
        invalid = {
            "derived-bool-both": True,
            "derived-string-both": "0.125",
            "derived-nan-both": math.nan,
            "derived-inf-both": math.inf,
        }[change]
        current["vol"] = saved["vol"] = invalid
    assert not rd._measures_equal(current, saved)
