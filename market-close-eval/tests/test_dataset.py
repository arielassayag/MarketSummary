"""Testes do dataset: carga real, proteção do holdout e validações."""

from __future__ import annotations

import pytest

from market_eval.dataset import (
    HoldoutAccessError,
    case_input_hash,
    case_reference_hash,
    list_case_paths,
    load_case,
    load_cases,
    validate_reference_ids,
)


def test_holdout_bloqueado_sem_flag(project_root) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(HoldoutAccessError):
        list_case_paths(project_root, "holdout")
    with pytest.raises(HoldoutAccessError):
        load_cases(project_root, "holdout")


def test_holdout_abre_com_flag(project_root) -> None:  # type: ignore[no-untyped-def]
    cases = load_cases(project_root, "holdout", allow_holdout=True)
    assert len(cases) == 6


def test_dev_tem_14_casos(project_root) -> None:  # type: ignore[no-untyped-def]
    cases = load_cases(project_root, "dev")
    assert len(cases) == 14
    regimes = {c.regime.value for c in cases}
    assert regimes == {"calm", "domestic_macro", "global_macro", "corporate", "stress"}


def test_showcases_marcados_antes(project_root) -> None:  # type: ignore[no-untyped-def]
    all_cases = load_cases(project_root, "dev") + load_cases(project_root, "holdout", allow_holdout=True)
    showcases = [c for c in all_cases if c.showcase]
    regimes = sorted(c.regime.value for c in showcases)
    assert regimes == ["calm", "domestic_macro"]
    assert len(showcases) == 2


def test_todos_os_casos_tem_direcao_e_fonte(project_root) -> None:  # type: ignore[no-untyped-def]
    for split in ("dev",):
        for case in load_cases(project_root, split):
            assert case.facts
            for f in case.facts:
                assert f.source.url.startswith("https://")
                assert f.direction in ("up", "down", "flat", "na")
            assert not validate_reference_ids(case)
            assert case.review.status.value in ("draft", "in_review", "reviewed")


def test_contribuicao_ausente_do_dataset(project_root) -> None:  # type: ignore[no-untyped-def]
    from market_eval.schemas import MeasureKind

    for split in ("dev",):
        for case in load_cases(project_root, split):
            assert all(f.measure_kind != MeasureKind.contribution_bps for f in case.facts)


def test_case_id_bate_com_arquivo(project_root) -> None:  # type: ignore[no-untyped-def]
    path = list_case_paths(project_root, "dev")[0]
    case = load_case(path)
    assert case.case_id == path.stem


def test_hashes_estaveis(project_root) -> None:  # type: ignore[no-untyped-def]
    case = load_cases(project_root, "dev")[0]
    assert case_input_hash(case) == case_input_hash(case)
    assert case_reference_hash(case) == case_reference_hash(case)
    assert case_input_hash(case) != case_reference_hash(case)
