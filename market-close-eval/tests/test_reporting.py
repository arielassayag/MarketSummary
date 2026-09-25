"""Testes de relatórios: geração de artefatos e proteção do holdout."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from market_eval.cli import cmd_report, cmd_run
from market_eval.dataset import HoldoutAccessError
from market_eval.evaluators.absolute_judge import JudgeGrade, compute_raw_score
from market_eval.evaluators.deterministic import grade_output
from market_eval.reporting import (
    build_manifest,
    write_examples_before_after,
)
from market_eval.schemas import (
    AbsoluteJudgeOutput,
    GenerationRecord,
    GenerationStatus,
    JudgeDimension,
)


def fake_judge(scores: tuple[int, int, int, int, int], hard: bool = False) -> JudgeGrade:
    f, m, c, cov, cl = scores
    jo = AbsoluteJudgeOutput(
        factuality=JudgeDimension(score=f, reason=""),
        materiality=JudgeDimension(score=m, reason=""),
        causal_discipline=JudgeDimension(score=c, reason=""),
        coverage=JudgeDimension(score=cov, reason=""),
        clarity=JudgeDimension(score=cl, reason=""),
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


def _write_run(run_dir: Path, records: list[GenerationRecord]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "raw_generations.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n")


def test_report_gera_artefatos(project_root, mini_case, make_output, scoring, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("market_eval.cli.load_configs", lambda: (project_root, __import__("market_eval.config", fromlist=["ExperimentConfig"]).ExperimentConfig(), scoring))
    monkeypatch.setattr("market_eval.cli.root_dir", lambda: project_root)
    # usa apenas casos dev reais em run temporário dentro de outputs/
    run_id = "test_report_run"
    run_dir = project_root / "outputs" / run_id
    out = make_output()
    records = []
    for case in load_two_dev_cases(project_root):
        for version in ("v1", "v2"):
            rec = GenerationRecord.model_validate(
                {
                    "task_id": f"{case.case_id}|dev|m1|{version}|rep1",
                    "run_id": run_id,
                    "case_id": case.case_id,
                    "split": "dev",
                    "regime": case.regime.value,
                    "model_id": "m1",
                    "prompt_version": version,
                    "repetition": 1,
                    "seed": 1,
                    "status": GenerationStatus.completed.value,
                    "output": out.model_dump(mode="json"),
                    "created_at": "2026-08-27T12:00:00-03:00",
                }
            )
            records.append(rec)
    _write_run(run_dir, records)
    # deterministic + judge grades
    det_rows = [
        grade_output(
            next(c for c in load_two_dev_cases(project_root) if c.case_id == r.case_id),
            r.output,
            scoring,
            task_id=r.task_id,
        ).to_dict()
        for r in records
    ]
    (run_dir / "deterministic_grades.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in det_rows) + "\n", encoding="utf-8"
    )
    judge_rows = []
    for r in records:
        jg = fake_judge((3, 3, 3, 3, 3))
        judge_rows.append(
            {
                "task_id": r.task_id,
                "case_id": r.case_id,
                "sample_id": "s1",
                "raw_score": jg.raw_score,
                "final_score": jg.raw_score,
                "det_hard_fail": False,
                "judge_hard_fail": False,
                "hard_fail": False,
                "hard_fail_reasons": [],
                "judge_output": jg.judge_output.model_dump(mode="json"),
                "error_kind": None,
            }
        )
    (run_dir / "judge_grades.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in judge_rows) + "\n", encoding="utf-8"
    )

    args = SimpleNamespace(run_id=run_id, confirm_holdout=False)
    cmd_report(args)

    for name in (
        "manifest.json",
        "all_results.csv",
        "summary_by_model_prompt.csv",
        "prompt_delta.csv",
        "failure_analysis.csv",
        "cost_latency.csv",
        "methodology.md",
        "caveats.md",
        "article_results.md",
        "examples_before_after.md",
        "report.html",
    ):
        assert (run_dir / name).exists(), f"ausente: {name}"
    charts = sorted((run_dir / "charts").glob("*.png"))
    assert charts, "gráficos não gerados"
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "RASCUNHO" in html  # casos draft -> banner de rascunho
    assert "data:image/png;base64" in html  # gráficos embutidos (abre offline)
    article = (run_dir / "article_results.md").read_text(encoding="utf-8")
    assert "aprovação factual" in article

    # limpeza
    import shutil

    shutil.rmtree(run_dir)


def load_two_dev_cases(project_root: Path):  # type: ignore[no-untyped-def]
    from market_eval.dataset import load_cases

    return load_cases(project_root, "dev")[:2]


def test_report_holdout_exige_flag(project_root, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from market_eval.dataset import load_cases

    holdout = load_cases(project_root, "holdout", allow_holdout=True)[0]
    run_dir = project_root / "outputs" / "test_holdout_run"
    rec = GenerationRecord.model_validate(
        {
            "task_id": f"{holdout.case_id}|holdout|m1|v1|rep1",
            "run_id": "test_holdout_run",
            "case_id": holdout.case_id,
            "split": "holdout",
            "regime": holdout.regime.value,
            "model_id": "m1",
            "prompt_version": "v1",
            "repetition": 1,
            "seed": 1,
            "status": GenerationStatus.completed.value,
            "created_at": "2026-08-27T12:00:00-03:00",
        }
    )
    _write_run(run_dir, [rec])
    args = SimpleNamespace(run_id="test_holdout_run", confirm_holdout=False)
    with pytest.raises(HoldoutAccessError):
        cmd_report(args)
    import shutil

    shutil.rmtree(run_dir)


def test_run_holdout_bloqueado_sem_flag(project_root, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("market_eval.cli.root_dir", lambda: project_root)
    args = SimpleNamespace(
        split="holdout",
        prompt="v1",
        run_id=None,
        models=None,
        cases=None,
        concurrency=None,
        repetitions=None,
        force=False,
        no_cache=False,
        resume=False,
        confirm_holdout=False,
    )
    with pytest.raises(HoldoutAccessError):
        cmd_run(args)  # bloqueia ANTES de exigir chave de API


def test_examples_usam_somente_showcases(project_root) -> None:  # type: ignore[no-untyped-def]
    run_dir = project_root / "outputs" / "test_examples"
    write_examples_before_after(run_dir, project_root, [])
    text = (run_dir / "examples_before_after.md").read_text(encoding="utf-8")
    assert "showcase" in text.lower()
    assert "pendente" in text.lower()  # sem execuções -> marcado como pendente
    shutil.rmtree(run_dir)


def test_manifest_hashes(project_root) -> None:  # type: ignore[no-untyped-def]
    from market_eval.config import ExperimentConfig

    manifest = build_manifest(
        root=project_root,
        run_id="x",
        cfg=ExperimentConfig(),
        splits=["dev"],
        model_ids=["m"],
        prompt_versions=["v1", "v2"],
        repetitions=1,
        synthetic=False,
    )
    assert manifest["hashes"]["prompt_v1"] is not None
    assert manifest["hashes"]["prompt_v1"] != manifest["hashes"]["prompt_v2"]
    assert manifest["hashes"]["models_lock"] is not None
    assert len(manifest["hashes"]["cases"]) == 20
