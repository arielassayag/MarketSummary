"""Métricas agregadas por (modelo, prompt, split) e deltas pareados V2-V1.

O DataFrame mesclado é "achatado": nenhuma coluna carrega objetos, o que torna
o CSV/parquet estável e o groupby previsível.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from .statistics import bootstrap_paired_delta_by_case, summarize, wilson_ci

if TYPE_CHECKING:
    from .evaluators.absolute_judge import JudgeGrade
    from .evaluators.deterministic import DeterministicGrade
    from .schemas import GenerationRecord

DIMENSIONS = ["factuality", "materiality", "causal_discipline", "coverage", "clarity"]


def flatten_records(
    records: list[GenerationRecord],
    det_grades: dict[str, DeterministicGrade],
    judge_grades: dict[str, JudgeGrade],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for r in records:
        det = det_grades.get(r.task_id)
        judge = judge_grades.get(r.task_id)
        det_hard = bool(det.hard_fail) if det is not None else False
        judge_hard = bool(judge.hard_fail) if judge is not None else False
        raw_score = float(judge.raw_score) if judge is not None and judge.raw_score is not None else None
        row: dict[str, object] = {
            "task_id": r.task_id,
            "case_id": r.case_id,
            "split": r.split,
            "regime": r.regime,
            "model_id": r.model_id,
            "prompt_version": r.prompt_version,
            "repetition": r.repetition,
            "status": r.status.value,
            "synthetic": r.synthetic,
            "cost_usd": r.cost_usd,
            "latency_ms": r.latency_ms,
            "total_tokens": r.total_tokens,
            "graded": det is not None or judge is not None,
            "det_hard_fail": det_hard,
            "judge_hard_fail": judge_hard,
            "hard_fail": bool(det_hard or judge_hard) if (det is not None or judge is not None) else None,
            "raw_score": raw_score,
            "final_score": (min(raw_score, 49.0) if (det_hard or judge_hard) else raw_score)
            if raw_score is not None
            else None,
            "deterministic_hard_fail_flag": det_hard if det is not None else None,
            "word_count": det.word_count if det is not None else None,
            "evidence_id_validity": det.evidence_id_validity if det is not None else None,
            "critical_fact_recall": det.critical_fact_recall if det is not None else None,
            "must_mention_recall": det.must_mention_recall if det is not None else None,
            "numeric_accuracy": det.numeric_accuracy if det is not None else None,
            "direction_accuracy": det.direction_accuracy if det is not None else None,
            "unit_accuracy": det.unit_accuracy if det is not None else None,
            "measure_kind_accuracy": det.measure_kind_accuracy if det is not None else None,
            "claim_evidence_coverage": det.claim_evidence_coverage if det is not None else None,
            "return_as_contribution": bool(det.return_as_contribution_violation) if det is not None else None,
            "failure_categories": "|".join(det.failure_categories) if det is not None else None,
            "judge_factuality": None,
            "judge_materiality": None,
            "judge_causal_discipline": None,
            "judge_coverage": None,
            "judge_clarity": None,
            "judge_critical_categories": None,
        }
        if judge is not None and judge.judge_output is not None:
            jo = judge.judge_output
            row["judge_factuality"] = jo.factuality.score
            row["judge_materiality"] = jo.materiality.score
            row["judge_causal_discipline"] = jo.causal_discipline.score
            row["judge_coverage"] = jo.coverage.score
            row["judge_clarity"] = jo.clarity.score
            row["judge_critical_categories"] = "|".join(e.category for e in jo.critical_errors)
        rows.append(row)
    return pd.DataFrame(rows)


def summary_by_model_prompt(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (model, prompt, split), group in df.groupby(["model_id", "prompt_version", "split"]):
        completed = group[group["status"] == "completed"]
        graded = completed[completed["graded"].astype(bool)]
        n = len(completed)
        graded_n = len(graded)
        hard_flags = graded["hard_fail"].astype(bool).tolist() if graded_n else []
        hard_pass = [not f for f in hard_flags]
        lo, hi = wilson_ci(sum(hard_pass), len(hard_pass)) if hard_pass else (0.0, 0.0)
        finals = [float(x) for x in completed["final_score"].dropna().tolist()]
        raws = [float(x) for x in completed["raw_score"].dropna().tolist()]
        s_final = summarize(finals)
        costs = [float(c) for c in completed["cost_usd"].dropna().tolist()]
        lat = sorted(float(v) for v in completed["latency_ms"].dropna().tolist())
        toks = [float(t) for t in completed["total_tokens"].dropna().tolist()]

        group_completed = completed

        def dim_mean(name: str, _g: pd.DataFrame = group_completed) -> float:
            series = _g[f"judge_{name}"].dropna()
            return float(series.mean()) if len(series) else 0.0

        def col_mean(name: str, _g: pd.DataFrame = group_completed) -> float:
            series = _g[name].dropna()
            return float(series.mean()) if len(series) else 0.0

        def cat_rate(column: str, cats: set[str], _g: pd.DataFrame = group_completed) -> float:
            series = _g[column].dropna()
            if not len(series):
                return 0.0
            hits = sum(1 for v in series if set(str(v).split("|")) & cats)
            return hits / len(series)

        rows.append(
            {
                "model_id": model,
                "prompt_version": prompt,
                "split": split,
                "n_cases": int(completed["case_id"].nunique()),
                "n_outputs": n,
                "hard_pass_rate": (sum(hard_pass) / len(hard_pass)) if hard_pass else 0.0,
                "hard_pass_ci95_low": lo,
                "hard_pass_ci95_high": hi,
                "raw_score_mean": (sum(raws) / len(raws)) if raws else None,
                "final_score_mean": s_final["mean"] if finals else None,
                "final_score_median": s_final["median"] if finals else None,
                "final_score_p10": s_final["p10"] if finals else None,
                "final_score_std": s_final["std"] if finals else None,
                "factuality_mean": dim_mean("factuality"),
                "materiality_mean": dim_mean("materiality"),
                "causal_discipline_mean": dim_mean("causal_discipline"),
                "coverage_mean": dim_mean("coverage"),
                "clarity_mean": dim_mean("clarity"),
                "critical_fact_recall": col_mean("critical_fact_recall"),
                "must_mention_recall": col_mean("must_mention_recall"),
                "numeric_accuracy": col_mean("numeric_accuracy"),
                "invalid_schema_rate": (n - graded_n) / n if n else 0.0,
                "fabrication_rate": cat_rate("judge_critical_categories", {"fabricated_fact", "fabricated_event"}),
                "unsupported_causal_rate": cat_rate("judge_critical_categories", {"unsupported_causal_as_fact"}),
                "return_contribution_confusion_rate": (
                    max(
                        cat_rate("judge_critical_categories", {"return_as_contribution"}),
                        float(graded["return_as_contribution"].fillna(False).astype(bool).mean())
                        if graded_n and len(graded)
                        else 0.0,
                    )
                ),
                "cost_total_usd": sum(costs),
                "cost_mean_usd": (sum(costs) / len(costs)) if costs else None,
                "tokens_mean": (sum(toks) / len(toks)) if toks else None,
                "latency_p50_ms": _percentile(lat, 0.5),
                "latency_p95_ms": _percentile(lat, 0.95),
            }
        )
    return pd.DataFrame(rows)


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1))))
    return sorted_values[idx]


def paired_prompt_delta(df: pd.DataFrame, *, seed: int = 42) -> pd.DataFrame:
    """Delta V2 - V1 pareado por caso (média por caso antes do delta, bootstrap por caso)."""
    rows: list[dict[str, object]] = []
    completed = df[df["status"] == "completed"]
    for (model, split), group in completed.groupby(["model_id", "split"]):
        per_case: dict[str, dict[str, list[float]]] = {}
        per_case_hard: dict[str, dict[str, list[float]]] = {}
        regime_of: dict[str, str] = {}
        for _, row in group.iterrows():
            if row["final_score"] is None or pd.isna(row["final_score"]):
                continue
            pv = str(row["prompt_version"])
            bucket = per_case.setdefault(str(row["case_id"]), {"v1": [], "v2": []})
            bucket[pv].append(float(row["final_score"]))
            hf = 1.0 if bool(row["hard_fail"]) else 0.0
            per_case_hard.setdefault(str(row["case_id"]), {"v1": [], "v2": []})[pv].append(hf)
            regime_of[str(row["case_id"])] = str(row["regime"])
        cases = sorted(c for c, d in per_case.items() if d["v1"] and d["v2"])
        if not cases:
            continue
        a = {c: sum(per_case[c]["v1"]) / len(per_case[c]["v1"]) for c in cases}
        b = {c: sum(per_case[c]["v2"]) / len(per_case[c]["v2"]) for c in cases}
        delta, lo, hi = bootstrap_paired_delta_by_case(a, b, seed=seed)
        ah = {c: sum(per_case_hard[c]["v1"]) / len(per_case_hard[c]["v1"]) for c in cases}
        bh = {c: sum(per_case_hard[c]["v2"]) / len(per_case_hard[c]["v2"]) for c in cases}
        delta_hard, lo_h, hi_h = bootstrap_paired_delta_by_case(ah, bh, seed=seed + 1)
        rows.append(
            {
                "model_id": model,
                "split": split,
                "n_cases": len(cases),
                "delta_final_score": delta,
                "delta_ci95_low": lo,
                "delta_ci95_high": hi,
                "delta_hard_pass_rate": bh_mean(bh) - ah_mean(ah),
                "delta_hard_pass_ci_low": -(hi_h),
                "delta_hard_pass_ci_high": -(lo_h),
            }
        )
        for regime in sorted({regime_of[c] for c in cases}):
            sub = [c for c in cases if regime_of[c] == regime]
            dr, lr, hr = bootstrap_paired_delta_by_case(
                {c: a[c] for c in sub}, {c: b[c] for c in sub}, seed=seed + 2
            )
            rows.append(
                {
                    "model_id": model,
                    "split": f"{split}|{regime}",
                    "n_cases": len(sub),
                    "delta_final_score": dr,
                    "delta_ci95_low": lr,
                    "delta_ci95_high": hr,
                    "delta_hard_pass_rate": None,
                    "delta_hard_pass_ci_low": None,
                    "delta_hard_pass_ci_high": None,
                }
            )
    return pd.DataFrame(rows)


def ah_mean(ah: dict[str, float]) -> float:
    return sum(ah.values()) / len(ah) if ah else 0.0


def bh_mean(bh: dict[str, float]) -> float:
    return sum(bh.values()) / len(bh) if bh else 0.0


def failure_analysis(df: pd.DataFrame) -> pd.DataFrame:
    counts: dict[tuple[str, str, str, str], int] = {}
    for _, row in df.iterrows():
        cats = row["failure_categories"]
        if cats is None or (isinstance(cats, float) and pd.isna(cats)) or not str(cats):
            continue
        for cat in str(cats).split("|"):
            key = (str(row["model_id"]), str(row["prompt_version"]), str(row["split"]), cat)
            counts[key] = counts.get(key, 0) + 1
    rows = [
        {"model_id": k[0], "prompt_version": k[1], "split": k[2], "failure_category": k[3], "count": v}
        for k, v in sorted(counts.items())
    ]
    return pd.DataFrame(rows)


def cost_latency(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (model, prompt), group in df.groupby(["model_id", "prompt_version"]):
        costs = [float(c) for c in group["cost_usd"].dropna().tolist()]
        lat = sorted(float(v) for v in group["latency_ms"].dropna().tolist())
        rows.append(
            {
                "model_id": model,
                "prompt_version": prompt,
                "n_calls": len(group),
                "cost_total_usd": sum(costs),
                "cost_mean_usd": (sum(costs) / len(costs)) if costs else None,
                "latency_p50_ms": _percentile(lat, 0.5),
                "latency_p95_ms": _percentile(lat, 0.95),
            }
        )
    return pd.DataFrame(rows)


def save_tables(df: pd.DataFrame, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    summary = summary_by_model_prompt(df)
    delta = paired_prompt_delta(df)
    failures = failure_analysis(df)
    cost = cost_latency(df)
    paths["all_results.csv"] = _write(df, out_dir / "all_results.csv")
    try:
        df.to_parquet(out_dir / "all_results.parquet", index=False)
        paths["all_results.parquet"] = out_dir / "all_results.parquet"
    except (ImportError, OSError):
        # pyarrow/fastparquet ausente: CSV continua disponível (limitação registrada)
        pass
    paths["summary_by_model_prompt.csv"] = _write(summary, out_dir / "summary_by_model_prompt.csv")
    paths["prompt_delta.csv"] = _write(delta, out_dir / "prompt_delta.csv")
    paths["failure_analysis.csv"] = _write(failures, out_dir / "failure_analysis.csv")
    paths["cost_latency.csv"] = _write(cost, out_dir / "cost_latency.csv")
    return paths


def _write(df: pd.DataFrame, path: Path) -> Path:
    df.to_csv(path, index=False, encoding="utf-8")
    return path
