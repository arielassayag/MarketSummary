"""CLI do market_eval (python -m market_eval ...)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from .cache import ResponseCache, file_sha256
from .charts import generate_all_charts
from .config import (
    ExperimentConfig,
    ModelLock,
    ScoringConfig,
    load_experiment,
    load_model_lock,
    load_scoring,
)
from .dataset import (
    HoldoutAccessError,
    load_cases,
    validate_dataset,
)
from .evaluators.absolute_judge import AbsoluteJudge, AbsoluteJudgeOutput, JudgeGrade
from .evaluators.deterministic import DeterministicGrade, grade_from_dict, grade_output
from .evaluators.human_audit import build_audit_sample, export_human_audit, import_human_audit
from .evaluators.pairwise_judge import PairwiseJudge
from .logging_utils import setup_logging
from .metrics import flatten_records, save_tables
from .model_catalog import fetch_catalog, load_catalog, select_models, validate_model_ids
from .openrouter_client import OpenRouterClient
from .reporting import (
    build_manifest,
    write_article_results,
    write_caveats,
    write_examples_before_after,
    write_methodology,
    write_report_html,
)
from .runner import Runner, SyntheticBackend, build_tasks, load_records, resume_pending
from .schemas import Case, GenerationStatus

BRT = timezone(timedelta(hours=-3))
logger = logging.getLogger("market_eval")


def _as_float(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def brt_stamp() -> str:
    return datetime.now(BRT).strftime("%Y-%m-%d_%H%M")


def require_api_key() -> str:
    load_dotenv(root_dir() / ".env")
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        print(
            "ERRO: OPENROUTER_API_KEY ausente. Configure o arquivo .env "
            "(copie .env.example) antes de executar comandos com custo.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return key


def load_configs() -> tuple[Path, ExperimentConfig, ScoringConfig]:
    root = root_dir()
    return root, load_experiment(root), load_scoring(root)


def split_arg(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def candidate_model_ids(lock: ModelLock, override: str | None) -> list[str]:
    if override:
        return split_arg(override)
    return [m.exact_model_id for m in lock.candidates()]


def catalog_for_validation(root: Path) -> tuple[dict, str]:
    """Catálogo vivo (público, sem custo); cai para o snapshot se offline."""
    snap_dir = root / "data" / "raw"
    live_path = snap_dir / f"openrouter_models_snapshot_live_{brt_stamp()}.json"
    try:
        n = fetch_catalog(live_path)
        return load_catalog(live_path), f"catalogo vivo ({n} modelos)"
    except Exception as exc:  # noqa: BLE001
        snapshots = sorted(snap_dir.glob("openrouter_models_snapshot_*.json"))
        if not snapshots:
            raise
        source = snapshots[-1]
        print(
            f"AVISO: sem acesso ao catálogo vivo ({exc}); validando contra snapshot {source.name}",
            file=sys.stderr,
        )
        return load_catalog(source), f"snapshot {source.name}"


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def cmd_list_models(args: argparse.Namespace) -> None:
    root, _, _ = load_configs()
    n = fetch_catalog(root / "data" / "raw" / f"openrouter_models_snapshot_{datetime.now(BRT).date()}.json")
    print(f"Catálogo consultado: {n} modelos (snapshot salvo em data/raw/).")
    _, exp, _ = load_configs()
    catalog = load_catalog(sorted((root / "data" / "raw").glob("openrouter_models_snapshot_*.json"))[-1])
    for slot, prefs in exp.candidates.preferences.items():
        for mid in prefs:
            entry = catalog.get(mid)
            status = "DISPONÍVEL" if entry else "indisponível"
            price = f"in=US${entry.input_price_usd_per_m:.2f}/M out=US${entry.output_price_usd_per_m:.2f}/M" if entry else ""
            so = "structured_outputs" if entry and entry.supports("structured_outputs") else "sem-structured-outputs"
            print(f"  [{slot}] {mid}: {status}; {price}; {so}")


def cmd_lock_models(args: argparse.Namespace) -> None:
    root, exp, _ = load_configs()
    snap_path = root / "data" / "raw" / f"openrouter_models_snapshot_{datetime.now(BRT).date()}.json"
    n = fetch_catalog(snap_path)
    catalog = load_catalog(snap_path)
    selected, judge_id, warnings = select_models(
        catalog, exp.candidates.preferences, exp.candidates.judge_preferences
    )
    for w in warnings:
        print(f"AVISO: {w}")
    from .model_catalog import write_lock

    lock_path = root / "configs" / "models.lock.yaml"
    write_lock(
        lock_path=lock_path,
        snapshot_path=snap_path.relative_to(root),
        selected=selected,
        judge_id=judge_id,
        catalog=catalog,
        n_models=n,
    )
    print(f"models.lock.yaml atualizado: {len(selected)} candidatos + judge {judge_id}")
    for slot, mid in selected.items():
        print(f"  {slot}: {mid}")


def cmd_validate_data(args: argparse.Namespace) -> None:
    root, _, _ = load_configs()
    cases, total_errors = validate_dataset(root)
    n_ok = sum(1 for c in cases if c.ok)
    print(f"Casos válidos: {n_ok}/{len(cases)}")
    for c in cases:
        flag = "OK " if c.ok else "ERRO"
        print(f"  [{flag}] {c.case} ({c.split}/{c.regime}, {c.n_facts} fatos, review={c.review_status})")
        for e in c.errors:
            print(f"        - {e}")
    if total_errors:
        raise SystemExit(1)
    print("Dataset válido (erros=0). Lembre: review.status=draft exige auditoria humana antes de publicar.")


def cmd_build_manifest(args: argparse.Namespace) -> None:
    root, _, _ = load_configs()
    dm_path = root / "data" / "dataset_manifest.json"
    if not dm_path.exists():
        print("dataset_manifest.json ausente — gere o dataset com scripts/build_dataset.py")
        raise SystemExit(1)
    manifest: dict[str, object] = json.loads(dm_path.read_text(encoding="utf-8"))
    # atualiza hashes e review status a partir dos arquivos atuais
    entries = manifest.get("cases", [])
    if not isinstance(entries, list):
        raise SystemExit(1)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = root / str(entry["path"])
        if path.exists():
            data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
            entry["sha256"] = file_sha256(path)
            review = data.get("review", {})
            entry["review_status"] = review.get("status", "draft") if isinstance(review, dict) else "draft"
    dm_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    n_cases = len(entries)
    reviewed = sum(
        1
        for e in entries
        if isinstance(e, dict) and e.get("review_status") == "reviewed"
    )
    print(f"Manifest atualizado: {reviewed}/{n_cases} casos revisados.")


def cmd_dry_run(args: argparse.Namespace) -> None:
    root, exp, _ = load_configs()
    print("== DRY RUN (nenhuma chamada paga) ==")
    print("1) Dataset (split dev):")
    all_reports, _ = validate_dataset(root)
    dev_cases = [c for c in all_reports if c.split == "dev"]
    ok = sum(1 for c in dev_cases if c.ok)
    print(f"   {ok}/{len(dev_cases)} casos dev válidos")
    cases = load_cases(root, "dev")
    print(f"   fatos por caso: min={min(len(c.facts) for c in cases)}, max={max(len(c.facts) for c in cases)}")
    print("2) Modelos:")
    catalog, source = catalog_for_validation(root)
    lock = load_model_lock(root)
    model_ids = candidate_model_ids(lock, args.models)
    errors = validate_model_ids(catalog, model_ids + [exp.judge.model])
    print(f"   fonte: {source}; candidatos: {model_ids}; judge: {exp.judge.model}")
    if errors:
        for e in errors:
            print(f"   ERRO: {e}")
        raise SystemExit(1)
    print("   todos os IDs validados (structured_outputs ok)")
    print("3) Mensagens (caso mais recente do dev):")
    from .agent import compose_messages

    sample = cases[-1]
    messages = compose_messages(sample, "v2", root / "prompts")
    print(f"   system: {len(messages[0]['content'])} chars; user(package): {len(messages[1]['content'])} chars")
    print("4) Plano de execução (dev):")
    n_tasks = len(cases) * len(model_ids) * 2 * exp.run.repetitions_dev
    print(f"   tarefas = {len(cases)} casos x {len(model_ids)} modelos x 2 prompts x {exp.run.repetitions_dev} reps = {n_tasks}")
    print("   judge absoluto previsto:", n_tasks)
    print("   pairwise previsto:", n_tasks // 2, "pares x 2 ordens")
    print("DRY RUN OK — execute `run --split dev --prompt all` para iniciar (haverá custo).")


def cmd_run(args: argparse.Namespace) -> None:
    root, exp, _ = load_configs()
    if args.no_cache or args.force:
        print(
            "AVISO: --no-cache/--force ignoram o cache e PODEM GERAR CUSTO ADICIONAL "
            "para combinações já executadas.",
            file=sys.stderr,
        )
    if args.split == "holdout" and not args.confirm_holdout:
        raise HoldoutAccessError("executar o holdout exige --confirm-holdout (congela o prompt antes!)")
    key = require_api_key()
    lock = load_model_lock(root)
    model_ids = candidate_model_ids(lock, args.models)
    cases = load_cases(root, args.split, allow_holdout=args.confirm_holdout)
    if args.cases:
        wanted = set(split_arg(args.cases))
        cases = [c for c in cases if c.case_id in wanted]
        if not cases:
            print("Nenhum caso corresponde a --cases", file=sys.stderr)
            raise SystemExit(1)
    prompts = ["v1", "v2"] if args.prompt == "all" else [args.prompt]
    repetitions = args.repetitions or (
        exp.run.repetitions_dev if args.split == "dev" else exp.run.repetitions_holdout
    )
    if args.concurrency:
        exp.run.concurrency = args.concurrency

    catalog, _ = catalog_for_validation(root)
    errors = validate_model_ids(catalog, model_ids)
    if errors:
        for e in errors:
            print(f"ERRO: {e}", file=sys.stderr)
        print("A execução foi abortada (nenhuma substituição silenciosa de modelo).", file=sys.stderr)
        raise SystemExit(1)

    run_id = args.run_id or f"run_{brt_stamp()}"
    cache = ResponseCache(root / exp.cache.sqlite_path)
    client = OpenRouterClient(
        api_key=key,
        site_url=os.environ.get("OPENROUTER_SITE_URL", ""),
        app_name=os.environ.get("OPENROUTER_APP_NAME", "AI Notes Market Close Eval"),
        timeout_s=float(exp.run.timeout_s),
        max_attempts=exp.run.max_attempts,
        backoff_base_s=exp.run.retry_backoff_base_s,
    )
    runner = Runner(
        cfg=exp,
        root=root,
        run_id=run_id,
        cases={c.case_id: c for c in cases},
        client=client,
        cache=cache,
        model_ids=model_ids,
        prompt_versions=prompts,
        synthetic=False,
    )
    tasks = build_tasks(
        cases, model_ids, prompts, repetitions, exp.run.seeds, exp.run.shuffle_seed
    )
    existing = load_records(runner.out_dir)
    if args.resume:
        pending = resume_pending(tasks, existing)
        print(f"Resume: {len(tasks) - len(pending)} tarefas já concluídas; {len(pending)} pendentes")
        tasks = pending
    print(
        f"Executando {len(tasks)} tarefas (concurrency={exp.run.concurrency}, "
        f"cache={'off' if args.no_cache else 'on'}) -> outputs/{run_id}/"
    )

    async def _run() -> list:
        return await runner.run_tasks(tasks, use_cache=not (args.no_cache or args.force))

    records = asyncio.run(_run())
    ok = sum(1 for r in records if r.status == GenerationStatus.completed)
    print(f"Concluído: {ok}/{len(records)} gerações OK. Registre o run_id: {run_id}")


def _cases_for_records(root: Path, records: list, allow_holdout: bool) -> dict[str, Case]:
    cases: dict[str, Case] = {}
    for split in sorted({r.split for r in records}):
        for case in load_cases(root, split, allow_holdout=allow_holdout):
            cases[case.case_id] = case
    return cases


def cmd_grade(args: argparse.Namespace) -> None:
    root, exp, scoring = load_configs()
    run_dir = root / exp.paths.outputs_dir / args.run_id
    records = load_records(run_dir)
    if not records:
        print(f"Nenhum registro em {run_dir}", file=sys.stderr)
        raise SystemExit(1)
    if any(r.split == "holdout" for r in records) and not args.confirm_holdout:
        raise HoldoutAccessError("o run contém holdout; use --confirm-holdout para avaliar")
    cases = _cases_for_records(root, records, allow_holdout=args.confirm_holdout)

    det_rows = []
    det_by_task: dict[str, DeterministicGrade] = {}
    for r in records:
        if r.status != GenerationStatus.completed or r.output is None:
            continue
        grade = grade_output(cases[r.case_id], r.output, scoring, task_id=r.task_id)
        det_by_task[r.task_id] = grade
        det_rows.append(grade.to_dict())
    (run_dir / "deterministic_grades.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in det_rows) + "\n", encoding="utf-8"
    )
    print(f"Avaliação determinística: {len(det_rows)} outputs -> deterministic_grades.jsonl")

    key = require_api_key()
    if args.judge_model:
        exp.judge.model = args.judge_model
    cache = ResponseCache(root / exp.cache.sqlite_path)
    client = OpenRouterClient(
        api_key=key,
        site_url=os.environ.get("OPENROUTER_SITE_URL", ""),
        app_name=os.environ.get("OPENROUTER_APP_NAME", "AI Notes Market Close Eval"),
        timeout_s=float(exp.run.timeout_s),
        max_attempts=exp.judge.max_attempts,
    )
    judge = AbsoluteJudge(client=client, cfg=exp.judge, scoring=scoring, cache=cache, root=root)

    async def _grade() -> list:
        return await judge.grade_all(
            [r for r in records if r.task_id in det_by_task],
            cases,
            use_cache=not args.no_cache,
        )

    judge_grades = asyncio.run(_grade())
    cap = float(scoring.hard_fail_cap)
    merged_rows = []
    for jg in judge_grades:
        det = det_by_task.get(jg.task_id)
        det_hard = bool(det.hard_fail) if det is not None else False
        combined = det_hard or jg.hard_fail
        raw = jg.raw_score
        final = min(raw, cap) if (raw is not None and combined) else raw
        reasons = sorted(
            set((det.failure_categories if det is not None and det_hard else []) + jg.hard_fail_reasons)
        )
        merged_rows.append(
            {
                "task_id": jg.task_id,
                "case_id": jg.case_id,
                "sample_id": jg.sample_id,
                "raw_score": raw,
                "final_score": final,
                "det_hard_fail": det_hard,
                "judge_hard_fail": jg.hard_fail,
                "hard_fail": combined,
                "hard_fail_reasons": reasons,
                "judge_output": jg.judge_output.model_dump(mode="json") if jg.judge_output else None,
                "error_kind": jg.error_kind,
            }
        )
    (run_dir / "judge_grades.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in merged_rows) + "\n", encoding="utf-8"
    )
    n_judged = sum(1 for m in merged_rows if m["judge_output"] is not None)
    print(f"Judge absoluto: {n_judged}/{len(merged_rows)} julgados -> judge_grades.jsonl")


def cmd_pairwise(args: argparse.Namespace) -> None:
    root, exp, _ = load_configs()
    run_dir = root / exp.paths.outputs_dir / args.run_id
    records = load_records(run_dir)
    if any(r.split == "holdout" for r in records) and not args.confirm_holdout:
        raise HoldoutAccessError("o run contém holdout; use --confirm-holdout")
    cases = _cases_for_records(root, records, allow_holdout=args.confirm_holdout)
    key = require_api_key()
    if args.judge_model:
        exp.judge.model = args.judge_model
    cache = ResponseCache(root / exp.cache.sqlite_path)
    client = OpenRouterClient(
        api_key=key,
        site_url=os.environ.get("OPENROUTER_SITE_URL", ""),
        app_name=os.environ.get("OPENROUTER_APP_NAME", "AI Notes Market Close Eval"),
        timeout_s=float(exp.run.timeout_s),
        max_attempts=exp.judge.max_attempts,
    )
    judge = PairwiseJudge(client=client, cfg=exp.judge, cache=cache, root=root)

    async def _compare() -> list:
        return await judge.compare_all(records, cases, use_cache=not args.no_cache)  # type: ignore[arg-type]

    outcomes = asyncio.run(_compare())
    (run_dir / "pairwise_grades.jsonl").write_text(
        "\n".join(json.dumps(o.to_dict(), ensure_ascii=False) for o in outcomes) + "\n", encoding="utf-8"
    )
    from collections import Counter

    dist = Counter(o.outcome for o in outcomes)
    print(f"Pares avaliados: {len(outcomes)}; distribuição: {dict(dist)} -> pairwise_grades.jsonl")


def cmd_export_human_audit(args: argparse.Namespace) -> None:
    root, exp, _ = load_configs()
    run_dir = root / exp.paths.outputs_dir / args.run_id
    records = load_records(run_dir)
    if any(r.split == "holdout" for r in records) and not args.confirm_holdout:
        raise HoldoutAccessError("o run contém holdout; use --confirm-holdout")
    judge_rows = {str(row["task_id"]): row for row in _load_jsonl(run_dir / "judge_grades.jsonl")}
    det_rows = {str(row["task_id"]): row for row in _load_jsonl(run_dir / "deterministic_grades.jsonl")}
    final_scores: dict[str, float | None] = {
        tid: (_as_float(row.get("final_score"))) for tid, row in judge_rows.items()
    }
    hard_fails = {tid: bool(row.get("hard_fail")) for tid, row in judge_rows.items()}
    det_hard = {tid: bool(row.get("hard_fail")) for tid, row in det_rows.items()}
    target = args.sample or max(40, int(0.10 * len(records)))
    items = build_audit_sample(
        records=records,
        final_scores=final_scores,
        hard_fails=hard_fails,
        det_hard_fails=det_hard,
        target=target,
    )
    commentary_by_task = {
        r.task_id: (r.output.commentary if r.output else (r.raw_text or "")) for r in records
    }
    paths = export_human_audit(run_dir, items, commentary_by_task)
    for p in paths:
        print(f"gerado: {p.relative_to(root)}")
    print(f"amostra: {len(items)} outputs (anonimizada)")


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_import_human_audit(args: argparse.Namespace) -> None:
    root, exp, _ = load_configs()
    csv_path = Path(args.file).resolve()
    if not csv_path.exists():
        print(f"arquivo não encontrado: {csv_path}", file=sys.stderr)
        raise SystemExit(1)
    # localiza o run pelo sample_id presente no CSV
    import csv as _csv

    with csv_path.open("r", encoding="utf-8") as fh:
        first = next(_csv.DictReader(fh), {})
    sid = str(first.get("sample_id", ""))
    if not sid.startswith("AUDIT-"):
        print("CSV sem coluna sample_id válida", file=sys.stderr)
        raise SystemExit(1)
    candidates = sorted((root / exp.paths.outputs_dir).glob("*/human_audit_sample.csv"))
    run_dir = None
    for candidate in candidates:
        if sid in candidate.read_text(encoding="utf-8"):
            run_dir = candidate.parent
            break
    if run_dir is None:
        print("Não encontrei o run que contém essa amostra", file=sys.stderr)
        raise SystemExit(1)
    result = import_human_audit(csv_path, run_dir)
    print(f"Concordância importada em {run_dir / 'human_audit_agreement.json'}")
    print(json.dumps(result, ensure_ascii=False, indent=1)[:1500])


def cmd_report(args: argparse.Namespace) -> None:
    root, exp, _ = load_configs()
    run_dir = root / exp.paths.outputs_dir / args.run_id
    records = load_records(run_dir)
    if not records:
        print(f"Nenhum registro em {run_dir}", file=sys.stderr)
        raise SystemExit(1)
    has_holdout = any(r.split == "holdout" for r in records)
    if has_holdout and not args.confirm_holdout:
        raise HoldoutAccessError("o relatório inclui holdout; use --confirm-holdout")
    synthetic = bool(records and records[0].synthetic)
    manifest = build_manifest(
        root=root,
        run_id=args.run_id,
        cfg=exp,
        splits=sorted({r.split for r in records}),
        model_ids=sorted({r.model_id for r in records}),
        prompt_versions=sorted({r.prompt_version for r in records}),
        repetitions=max(r.repetition for r in records),
        synthetic=synthetic,
    )
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    det_grades: dict[str, DeterministicGrade] = {}
    for row in _load_jsonl(run_dir / "deterministic_grades.jsonl"):
        det_grades[str(row["task_id"])] = grade_from_dict(row)
    judge_grades = _judge_grades_from_jsonl(run_dir)
    df = flatten_records(records, det_grades, judge_grades)
    paths = save_tables(df, run_dir)
    summary = pd.read_csv(paths["summary_by_model_prompt.csv"])
    delta = pd.read_csv(paths["prompt_delta.csv"])
    failures = pd.read_csv(paths["failure_analysis.csv"])
    pairwise_rows = _load_jsonl(run_dir / "pairwise_grades.jsonl")

    write_methodology(run_dir, exp, sorted({r.split for r in records}))
    write_caveats(run_dir)
    write_article_results(run_dir, root, summary, delta, failures, pd.DataFrame(pairwise_rows))
    write_examples_before_after(run_dir, root, records)
    charts = generate_all_charts(
        summary, delta, failures, pd.DataFrame(pairwise_rows) if pairwise_rows else None,
        run_dir / "charts", datetime.now(BRT).strftime("%d/%m/%Y"),
    )
    write_report_html(run_dir, root, manifest, summary, delta, failures, pairwise_rows)
    print(f"Relatório gerado em {run_dir}:")
    for name in ["article_results.md", "report.html", "summary_by_model_prompt.csv", "prompt_delta.csv"]:
        print(f"  - {name}")
    print(f"  - charts/: {len(charts)} PNGs")
    if not synthetic and not all_reviewed(root):
        print(
            "AVISO: dataset ainda em revisão humana — artefatos marcados como RASCUNHO "
            "(não publicar antes de review.status=reviewed e auditoria humana)."
        )


def _judge_grades_from_jsonl(run_dir: Path) -> dict[str, JudgeGrade]:
    grades: dict[str, JudgeGrade] = {}
    for row in _load_jsonl(run_dir / "judge_grades.jsonl"):
        jo = row.get("judge_output")
        raw = row.get("raw_score")
        final = row.get("final_score")
        reasons = row.get("hard_fail_reasons")
        grades[str(row["task_id"])] = JudgeGrade(
            task_id=str(row["task_id"]),
            case_id=str(row["case_id"]),
            sample_id=str(row.get("sample_id", "")),
            from_cache=False,
            judge_output=AbsoluteJudgeOutput.model_validate(jo) if jo else None,
            raw_score=_as_float(raw),
            final_score=_as_float(final),
            hard_fail=bool(row.get("hard_fail", False)),
            hard_fail_reasons=[str(x) for x in reasons] if isinstance(reasons, list) else [],
            error_kind=str(row["error_kind"]) if row.get("error_kind") is not None else None,
        )
    return grades


def all_reviewed(root: Path) -> bool:
    dm = root / "data" / "dataset_manifest.json"
    if not dm.exists():
        return False
    manifest = json.loads(dm.read_text(encoding="utf-8"))
    return all(
        c.get("review_status") == "reviewed" for c in manifest.get("cases", [])
    )


def cmd_status(args: argparse.Namespace) -> None:
    root, exp, _ = load_configs()
    run_dir = root / exp.paths.outputs_dir / args.run_id
    records = load_records(run_dir)
    if not records:
        print(f"Nenhum registro em {run_dir}")
        return
    from collections import Counter

    by_status = Counter(r.status.value for r in records)
    by_model_prompt = Counter(f"{r.model_id} {r.prompt_version}" for r in records)
    cache = ResponseCache(root / exp.cache.sqlite_path)
    print(f"Run: {args.run_id} ({len(records)} registros)")
    print("Por status:", dict(by_status))
    for k, v in sorted(by_model_prompt.items()):
        print(f"  {k}: {v}")
    print("Cache:", cache.stats())
    for name in [
        "deterministic_grades.jsonl",
        "judge_grades.jsonl",
        "pairwise_grades.jsonl",
        "report.html",
        "article_results.md",
    ]:
        if (run_dir / name).exists():
            print(f"  artefato: {name}")


def cmd_smoke(args: argparse.Namespace) -> None:
    """Smoke test SINTÉTICO (sem rede, sem custo). Nunca usar como resultado real."""
    root, exp, scoring = load_configs()
    run_id = args.run_id or f"smoke_synthetic_{brt_stamp()}"
    cases = load_cases(root, "dev")
    selected = cases[:2]
    model_ids = ["synthetic-a", "synthetic-b"]
    cache = ResponseCache(root / exp.cache.sqlite_path)
    runner = Runner(
        cfg=exp,
        root=root,
        run_id=run_id,
        cases={c.case_id: c for c in selected},
        client=SyntheticBackend(),
        cache=cache,
        model_ids=model_ids,
        prompt_versions=["v1", "v2"],
        synthetic=True,
    )
    tasks = build_tasks(selected, model_ids, ["v1", "v2"], 1, exp.run.seeds, exp.run.shuffle_seed)
    records = asyncio.run(runner.run_tasks(tasks))

    det_rows = []
    for r in records:
        if r.output is None:
            continue
        grade = grade_output(cases_by_id(selected, r.case_id), r.output, scoring, task_id=r.task_id)
        det_rows.append(grade.to_dict())
    (runner.out_dir / "deterministic_grades.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in det_rows) + "\n", encoding="utf-8"
    )
    manifest = build_manifest(
        root=root,
        run_id=run_id,
        cfg=exp,
        splits=["dev"],
        model_ids=model_ids,
        prompt_versions=["v1", "v2"],
        repetitions=1,
        synthetic=True,
    )
    (runner.out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # relatório mínimo sintético
    det_grades: dict[str, DeterministicGrade] = {}
    for row in det_rows:
        det_grades[str(row["task_id"])] = grade_from_dict(row)
    df = flatten_records(records, det_grades, {})
    save_tables(df, runner.out_dir)
    print(
        f"SMOKE SINTÉTICO concluído: outputs/{run_id}/ ({len(records)} gerações simuladas, "
        "0 chamadas reais). Resultados 100% sintéticos — não usar em publicação."
    )


def cases_by_id(cases: list[Case], case_id: str) -> Case:
    for c in cases:
        if c.case_id == case_id:
            return c
    raise KeyError(case_id)


def main(argv: list[str] | None = None) -> None:
    setup_logging("INFO")
    parser = argparse.ArgumentParser(prog="market_eval", description="Eval de prompts para comentário de fechamento")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-models", help="consulta o catálogo público do OpenRouter")
    p.set_defaults(func=cmd_list_models)

    p = sub.add_parser("lock-models", help="congela a seleção de modelos em configs/models.lock.yaml")
    p.set_defaults(func=cmd_lock_models)

    p = sub.add_parser("validate-data", help="valida o dataset congelado")
    p.set_defaults(func=cmd_validate_data)

    p = sub.add_parser("build-manifest", help="atualiza hashes/review status do dataset_manifest")
    p.set_defaults(func=cmd_build_manifest)

    p = sub.add_parser("dry-run", help="valida dataset, modelos e plano sem chamadas pagas")
    p.add_argument("--models", default=None)
    p.set_defaults(func=cmd_dry_run)

    p = sub.add_parser("run", help="executa gerações (com custo)")
    p.add_argument("--split", choices=["dev", "holdout"], required=True)
    p.add_argument("--prompt", choices=["v1", "v2", "all"], default="all")
    p.add_argument("--run-id", default=None)
    p.add_argument("--models", default=None, help="IDs separados por vírgula")
    p.add_argument("--cases", default=None, help="case_ids separados por vírgula")
    p.add_argument("--concurrency", type=int, default=None)
    p.add_argument("--repetitions", type=int, default=None)
    p.add_argument("--force", action="store_true", help="ignora cache (custo adicional possível)")
    p.add_argument("--no-cache", action="store_true", help="não lê cache (custo adicional possível)")
    p.add_argument("--resume", action="store_true", help="executa apenas tarefas pendentes")
    p.add_argument("--confirm-holdout", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("grade", help="avalia outputs (determinístico + judge)")
    p.add_argument("--run-id", required=True)
    p.add_argument("--judge-model", default=None)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--confirm-holdout", action="store_true")
    p.set_defaults(func=cmd_grade)

    p = sub.add_parser("pairwise", help="comparação pareada V1 x V2")
    p.add_argument("--run-id", required=True)
    p.add_argument("--judge-model", default=None)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--confirm-holdout", action="store_true")
    p.set_defaults(func=cmd_pairwise)

    p = sub.add_parser("export-human-audit", help="gera amostra estratificada para auditoria humana")
    p.add_argument("--run-id", required=True)
    p.add_argument("--sample", type=int, default=None)
    p.add_argument("--confirm-holdout", action="store_true")
    p.set_defaults(func=cmd_export_human_audit)

    p = sub.add_parser("import-human-audit", help="importa CSV revisado e calcula concordância")
    p.add_argument("file")
    p.set_defaults(func=cmd_import_human_audit)

    p = sub.add_parser("report", help="gera tabelas, gráficos, article_results e report.html")
    p.add_argument("--run-id", required=True)
    p.add_argument("--confirm-holdout", action="store_true")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("status", help="mostra o estado de um run")
    p.add_argument("--run-id", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("smoke", help="smoke test SINTÉTICO offline (não usar como resultado)")
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_smoke)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except HoldoutAccessError as exc:
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc


if __name__ == "__main__":
    main()
