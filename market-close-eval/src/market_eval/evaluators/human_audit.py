"""Auditoria humana: amostra estratificada, exportação, importação e concordância."""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

from ..schemas import GenerationRecord

HUMAN_COLUMNS = [
    "sample_id",
    "human_hard_fail",
    "human_factuality",
    "human_materiality",
    "human_causal_discipline",
    "human_coverage",
    "human_clarity",
    "human_error_category",
    "human_comment",
]

AUDIT_INSTRUCTIONS = """# Instruções da auditoria humana

Você está avaliando comentários de fechamento de mercado **anonimizados**.
Não é possível saber qual modelo ou versão de prompt gerou cada texto — e não
tente adivinhar. Avalie apenas o conteúdo frente ao pacote de fatos indicado.

Para cada linha do CSV:

1. `human_hard_fail`: `true` se houver erro grave (fato inventado, sinal/valor
   errado em fato crítico, causalidade sem suporte apresentada como fato,
   retorno tratado como contribuição, contradição central com o pacote);
   `false` caso contrário.
2. Notas de 0 a 4 (inteiros) para: `human_factuality`, `human_materiality`,
   `human_causal_discipline`, `human_coverage`, `human_clarity` — use a mesma
   rubrica do judge automático (ver metodologia).
3. `human_error_category`: categoria do erro principal (ou vazio).
4. `human_comment`: observações livres.

Preencha as colunas `human_*` no próprio CSV e salve. Em seguida importe com:

    python -m market_eval import-human-audit CAMINHO_DO_CSV
"""


@dataclass
class AuditItem:
    sample_id: str
    record: GenerationRecord
    package: str
    judge_final_score: float | None
    judge_hard_fail: bool
    deterministic_hard_fail: bool
    divergence_flag: bool


def build_audit_sample(
    *,
    records: list[GenerationRecord],
    final_scores: dict[str, float | None],
    hard_fails: dict[str, bool],
    det_hard_fails: dict[str, bool],
    target: int = 40,
    seed: int = 42,
) -> list[AuditItem]:
    """Amostra estratificada: >= max(10%, 40) outputs; todos os modelos, V1/V2,
    regimes; aprovados e reprovados; prioriza divergências entre verificações."""
    completed = [r for r in records if r.status.value == "completed" and r.output is not None]
    target = max(target, int(len(completed) * 0.10))

    def divergent(r: GenerationRecord) -> bool:
        jf = hard_fails.get(r.task_id, False)
        df = det_hard_fails.get(r.task_id, False)
        score = final_scores.get(r.task_id)
        return (jf != df) or (score is not None and score < 49 and df)

    by_group: dict[tuple[str, str], list[GenerationRecord]] = {}
    for r in completed:
        by_group.setdefault((r.model_id, r.prompt_version), []).append(r)

    rng = random.Random(seed)
    divergent_pool = [r for r in completed if divergent(r)]
    rest_pool = [r for r in completed if not divergent(r)]
    rng.shuffle(divergent_pool)
    # ordena restante para cobrir regimes distintos primeiro
    seen_regimes: set[str] = set()
    prioritized: list[GenerationRecord] = []
    for r in rest_pool:
        if r.regime not in seen_regimes:
            prioritized.append(r)
            seen_regimes.add(r.regime)
    prioritized += [r for r in rest_pool if r not in prioritized]

    # quota proporcional por (modelo, prompt) sobre o total
    quota = {g: max(1, round(target * len(rows) / max(1, len(completed)))) for g, rows in by_group.items()}

    selected: list[GenerationRecord] = []
    used: set[str] = set()

    def take(pool: list[GenerationRecord], group: tuple[str, str], n: int) -> None:
        count = 0
        for r in pool:
            if count >= n:
                break
            if r.task_id in used:
                continue
            if (r.model_id, r.prompt_version) != group:
                continue
            selected.append(r)
            used.add(r.task_id)
            count += 1

    for group in sorted(quota):
        take(divergent_pool, group, max(1, quota[group] // 2))
    for group in sorted(quota):
        remaining = quota[group] - sum(1 for s in selected if (s.model_id, s.prompt_version) == group)
        take(prioritized, group, remaining)

    # completa até o alvo
    for r in prioritized + divergent_pool:
        if len(selected) >= target:
            break
        if r.task_id not in used:
            selected.append(r)
            used.add(r.task_id)

    items: list[AuditItem] = []
    for i, r in enumerate(sorted(selected, key=lambda x: x.task_id), start=1):
        items.append(
            AuditItem(
                sample_id=f"AUDIT-{i:03d}",
                record=r,
                package="",
                judge_final_score=final_scores.get(r.task_id),
                judge_hard_fail=hard_fails.get(r.task_id, False),
                deterministic_hard_fail=det_hard_fails.get(r.task_id, False),
                divergence_flag=divergent(r),
            )
        )
    return items


def export_human_audit(
    run_dir: Path,
    items: list[AuditItem],
    commentary_by_task: dict[str, str],
) -> list[Path]:
    csv_path = run_dir / "human_audit_sample.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["sample_id", "task_id", "case_id", "split", "regime", "commentary_word_limit_applied"]
            + HUMAN_COLUMNS[1:]
        )
        for item in items:
            r = item.record
            writer.writerow(
                [
                    item.sample_id,
                    r.task_id,
                    r.case_id,
                    r.split,
                    r.regime,
                    "180-220",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    (run_dir / "human_audit_instructions.md").write_text(AUDIT_INSTRUCTIONS, encoding="utf-8")
    html_path = run_dir / "human_audit_form.html"
    html_path.write_text(_audit_form_html(items), encoding="utf-8")
    return [csv_path, run_dir / "human_audit_instructions.md", html_path]


def _audit_form_html(items: list[AuditItem]) -> str:
    rows = []
    for item in items:
        rows.append(
            f"<tr><td>{item.sample_id}</td><td>{item.record.case_id}</td>"
            f"<td>{item.record.regime}</td><td>{item.record.split}</td>"
            f"<td>{'sim' if item.divergence_flag else '—'}</td></tr>"
        )
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<title>Auditoria humana — amostra anonimizada</title>"
        "<style>body{font-family:sans-serif;margin:2rem}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:6px 10px}</style></head><body>"
        "<h1>Auditoria humana — amostra anonimizada</h1>"
        "<p>Modelo, prompt, provedor e custo NÃO são revelados. Preencha as notas "
        "no CSV exportado (human_audit_sample.csv) seguindo human_audit_instructions.md.</p>"
        "<table><tr><th>sample_id</th><th>caso</th><th>regime</th><th>split</th><th>divergente</th></tr>"
        + "".join(rows)
        + "</table></body></html>"
    )


def import_human_audit(csv_path: Path, run_dir: Path) -> dict[str, object]:
    """Importa revisão preenchida e calcula concordância com o judge."""
    from ..statistics import cohens_kappa, mae, spearman

    with csv_path.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    def _bool(v: str) -> bool | None:
        return {"true": True, "false": False, "1": True, "0": False}.get(v.strip().lower())

    dims = ["factuality", "materiality", "causal_discipline", "coverage", "clarity"]
    judge_by_sample = _judge_scores_by_sample(run_dir)
    human_hard: list[bool] = []
    judge_hard: list[bool] = []
    human_scores: dict[str, list[float]] = {d: [] for d in dims}
    judge_scores: dict[str, list[float]] = {d: [] for d in dims}
    n_parsed = 0
    for row in rows:
        sid = (row.get("sample_id") or "").strip()
        if not sid:
            continue
        n_parsed += 1
        hh = _bool(row.get("human_hard_fail") or "")
        jh = judge_by_sample.get(sid, {}).get("hard_fail")
        if hh is not None and isinstance(jh, bool):
            human_hard.append(hh)
            judge_hard.append(jh)
        for d in dims:
            raw = (row.get(f"human_{d}") or "").strip()
            js = judge_by_sample.get(sid, {}).get(d)
            if raw and js is not None:
                try:
                    human_scores[d].append(float(raw))
                    judge_scores[d].append(float(str(js)))
                except ValueError:
                    continue

    per_dimension: dict[str, object] = {}
    maes: list[float] = []
    for d in dims:
        h, j = human_scores[d], judge_scores[d]
        dim_mae = mae(h, j) if h else None
        if dim_mae is not None:
            maes.append(dim_mae)
        per_dimension[d] = {
            "n": len(h),
            "mae": dim_mae,
            "spearman": spearman(h, j) if len(h) >= 3 else None,
        }

    result: dict[str, object] = {
        "n_rows": n_parsed,
        "n_hard_fail_compared": len(human_hard),
        "hard_fail_agreement": (
            sum(1 for a, b in zip(human_hard, judge_hard, strict=False) if a == b) / len(human_hard) if human_hard else None
        ),
        "cohens_kappa_hard_fail": cohens_kappa(human_hard, judge_hard) if len(human_hard) >= 2 else None,
        "score_mae_overall": sum(maes) / len(maes) if maes else None,
        "per_dimension": per_dimension,
    }
    out = run_dir / "human_audit_agreement.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _judge_scores_by_sample(run_dir: Path) -> dict[str, dict[str, object]]:
    path = run_dir / "judge_grades.jsonl"
    mapping: dict[str, dict[str, object]] = {}
    if not path.exists():
        return mapping
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        sid = str(data.get("sample_id", ""))
        if not sid:
            continue
        entry: dict[str, object] = {
            "hard_fail": bool(data.get("hard_fail", False)),
            "final_score": data.get("final_score"),
        }
        jo = data.get("judge_output") or {}
        for d in ("factuality", "materiality", "causal_discipline", "coverage", "clarity"):
            dim = jo.get(d) if isinstance(jo, dict) else None
            entry[d] = dim.get("score") if isinstance(dim, dict) else None
        mapping[sid] = entry
    return mapping
