"""DADOS SIMULADOS: fontes macro opcionais sem alterar os dados originais."""
from dataclasses import fields
from datetime import date

import pandas as pd
import pytest

from cdp.data.snapshot import write_snapshot
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file

SYMBOLS = ("BZ=F", "HG=F", "GC=F", "DX-Y.NYB")
ARGS = {"seed": 7, "start": date(2023, 1, 2), "as_of": date(2026, 11, 20)}


def _same_fields(first, second, *, excluding=()):
    for field in fields(first):
        if field.name in excluding:
            continue
        left, right = getattr(first, field.name), getattr(second, field.name)
        if isinstance(left, pd.DataFrame):
            pd.testing.assert_frame_equal(left, right, check_exact=True)
        elif field.name == "universe":
            assert left.source_sha256 == right.source_sha256
            pd.testing.assert_frame_equal(left.issuers, right.issuers, check_exact=True)
            pd.testing.assert_frame_equal(left.lines, right.lines, check_exact=True)
        else:
            assert left == right, field.name


def test_optional_macros_preserve_every_original_field_and_default():
    base = make_synthetic_market(**ARGS)
    disabled = make_synthetic_market(**ARGS, macro_symbols=())
    _same_fields(base, disabled)
    expanded = make_synthetic_market(**ARGS, macro_symbols=SYMBOLS)
    _same_fields(base, expanded, excluding={"benchmarks", "manifest"})
    pd.testing.assert_frame_equal(base.benchmarks, expanded.benchmarks[list(base.benchmarks)],
                                  check_exact=True)
    assert list(base.benchmarks) == ["ILF", "EWZ", "EWW"]
    assert expanded.manifest.model_copy(update={"limitations": base.manifest.limitations}) == base.manifest
    assert expanded.manifest.is_synthetic and "DADOS SIMULADOS" in expanded.manifest.data_notice
    assert "cdp.synthetic.macro/v1" in expanded.manifest.limitations[-1]
    assert all(expanded.benchmarks[s].notna().all() for s in SYMBOLS)
    assert all((expanded.benchmarks[s] > 0).all() for s in SYMBOLS)
    assert all(expanded.benchmarks[s].nunique() > 1 for s in SYMBOLS)


def test_macro_order_and_repeat_have_identical_native_archived_bytes(tmp_path):
    first = make_synthetic_market(**ARGS, macro_symbols=SYMBOLS)
    second = make_synthetic_market(**ARGS, macro_symbols=tuple(reversed(SYMBOLS)))
    repeated = make_synthetic_market(**ARGS, macro_symbols=SYMBOLS)
    _same_fields(first, second)
    _same_fields(first, repeated)
    for name, market in [("one", first), ("two", second), ("three", repeated)]:
        write_snapshot(market, tmp_path / name)
    bodies = [{p.relative_to(tmp_path / name).as_posix(): sha256_file(p)
               for p in (tmp_path / name).rglob("*") if p.is_file()}
              for name in ["one", "two", "three"]]
    assert bodies[0] == bodies[1] == bodies[2]


@pytest.mark.parametrize("symbols", [("BZ=F", "BZ=F"), ("ILF",), ("",), (" BZ=F",), "BZ=F"])
def test_invalid_macros_cannot_replace_an_original_column(symbols):
    with pytest.raises(ValueError, match="únicos, válidos e próprios"):
        make_synthetic_market(**ARGS, macro_symbols=symbols)
