"""Testes de métricas e estatística (agregação, cap de score, bootstrap)."""

from __future__ import annotations

import pytest

from market_eval.evaluators.absolute_judge import JudgeGrade, compute_raw_score
from market_eval.metrics import flatten_records, summary_by_model_prompt
from market_eval.schemas import (
    AbsoluteJudgeOutput,
    GenerationRecord,
    GenerationStatus,
    JudgeDimension,
)
from market_eval.statistics import (
    bootstrap_paired_delta_by_case,
    cohens_kappa,
    mae,
    spearman,
    wilson_ci,
)


def fake_record(task_id: str, **kw: object) -> GenerationRecord:
    base = dict(
        task_id=task_id,
        run_id="r",
        case_id="c1",
        split="dev",
        regime="calm",
        model_id="m1",
        prompt_version="v1",
        repetition=1,
        seed=1,
        status=GenerationStatus.completed,
        created_at="2026-08-27T12:00:00-03:00",
    )
    base.update(kw)
    return GenerationRecord.model_validate(base)


def fake_judge(scores: tuple[int, int, int, int, int], hard: bool = False) -> JudgeGrade:
    f, m, c, cov, cl = scores
    jo = AbsoluteJudgeOutput(
        factuality=JudgeDimension(score=f, reason=""),
        materiality=JudgeDimension(score=m, reason=""),
        causal_discipline=JudgeDimension(score=c, reason=""),
        coverage=JudgeDimension(score=cov, reason=""),
        clarity=JudgeDimension(score=cl, reason=""),
        critical_errors=[],
        overall_notes="",
    )
    raw = compute_raw_score(jo, {"factuality": 30, "materiality": 25, "causal_discipline": 20, "coverage": 15, "clarity": 10})
    return JudgeGrade(
        task_id="t",
        case_id="c1",
        sample_id="s",
        from_cache=False,
        judge_output=jo,
        raw_score=raw,
        final_score=min(raw, 49.0) if hard else raw,
        hard_fail=hard,
        hard_fail_reasons=["fabricated_fact"] if hard else [],
    )


def test_raw_score_pesos() -> None:
    jo = AbsoluteJudgeOutput(
        factuality=JudgeDimension(score=4, reason=""),
        materiality=JudgeDimension(score=4, reason=""),
        causal_discipline=JudgeDimension(score=4, reason=""),
        coverage=JudgeDimension(score=4, reason=""),
        clarity=JudgeDimension(score=4, reason=""),
    )
    assert compute_raw_score(jo, {"factuality": 30, "materiality": 25, "causal_discipline": 20, "coverage": 15, "clarity": 10}) == 100.0


def test_cap_em_49() -> None:
    grade = fake_judge((4, 4, 4, 4, 4), hard=True)
    records = [fake_record("t")]
    df = flatten_records(records, {}, {"t": grade})
    assert bool(df.iloc[0]["hard_fail"]) is True
    assert float(df.iloc[0]["final_score"]) == 49.0


def test_sem_cap_quando_sem_hard_fail() -> None:
    grade = fake_judge((4, 4, 4, 4, 4), hard=False)
    df = flatten_records([fake_record("t")], {}, {"t": grade})
    assert float(df.iloc[0]["final_score"]) == 100.0


def test_wilson_ci() -> None:
    lo, hi = wilson_ci(8, 10)
    assert 0.4 <= lo <= 0.99 and lo < hi <= 1.0
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_bootstrap_reproduzivel() -> None:
    a = {f"c{i}": 50.0 + i for i in range(10)}
    b = {f"c{i}": 55.0 + i for i in range(10)}
    r1 = bootstrap_paired_delta_by_case(a, b, seed=7)
    r2 = bootstrap_paired_delta_by_case(a, b, seed=7)
    assert r1 == r2
    delta, lo, hi = r1
    assert abs(delta - 5.0) < 1e-9
    assert lo <= delta <= hi


def test_kappa_mae_spearman() -> None:
    assert cohens_kappa([True, False, True, True], [True, False, True, True]) == 1.0
    assert cohens_kappa([True, False], [False, True]) is not None
    assert mae([1.0, 2.0], [1.5, 2.5]) == 0.5
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_summary_agregado(mini_case, make_output, scoring, project_root) -> None:  # type: ignore[no-untyped-def]
    from market_eval.evaluators.deterministic import grade_output

    out = make_output()
    records = [
        fake_record("t1", model_id="m1", prompt_version="v1"),
        fake_record("t2", model_id="m1", prompt_version="v2"),
    ]
    det = {
        "t1": grade_output(mini_case, out, scoring, task_id="t1"),
        "t2": grade_output(mini_case, out, scoring, task_id="t2"),
    }
    judge = {
        "t1": fake_judge((3, 3, 3, 3, 3)),
        "t2": fake_judge((4, 4, 4, 4, 4)),
    }
    df = flatten_records(records, det, judge)
    summary = summary_by_model_prompt(df)
    assert len(summary) == 2
    v1 = summary[summary["prompt_version"] == "v1"].iloc[0]
    v2 = summary[summary["prompt_version"] == "v2"].iloc[0]
    assert float(v1["final_score_mean"]) < float(v2["final_score_mean"])
    assert float(v1["hard_pass_rate"]) == 1.0
    assert int(v1["n_outputs"]) == 1
