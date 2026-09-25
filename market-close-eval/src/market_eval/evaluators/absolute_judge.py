"""Judge absoluto (LLM-as-a-judge) com anonimização e score final.

O judge recebe: pacote do candidato + referência escondida (judge_notes,
vetores aceitos e conclusões proibidas) + output anonimizado por sample_id.
NUNCA recebe modelo, provedor ou versão do prompt.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..agent import build_package, load_prompt
from ..cache import ResponseCache, judge_cache_key
from ..config import JudgeConfig, ScoringConfig
from ..dataset import case_reference_hash
from ..logging_utils import log_event
from ..openrouter_client import OpenRouterClient
from ..schemas import (
    JUDGE_JSON_SCHEMA,
    AbsoluteJudgeOutput,
    Case,
    GenerationRecord,
    OutputParseError,
    parse_absolute_judge,
    sha256_text,
)

logger = logging.getLogger(__name__)


@dataclass
class JudgeGrade:
    task_id: str
    case_id: str
    sample_id: str
    from_cache: bool
    judge_output: AbsoluteJudgeOutput | None
    raw_score: float | None
    final_score: float | None
    hard_fail: bool
    hard_fail_reasons: list[str]
    error_kind: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "case_id": self.case_id,
            "sample_id": self.sample_id,
            "from_cache": self.from_cache,
            "judge_output": self.judge_output.model_dump(mode="json") if self.judge_output else None,
            "raw_score": self.raw_score,
            "final_score": self.final_score,
            "hard_fail": self.hard_fail,
            "hard_fail_reasons": self.hard_fail_reasons,
            "error_kind": self.error_kind,
        }


def compute_raw_score(judge: AbsoluteJudgeOutput, weights: dict[str, int]) -> float:
    return (
        weights["factuality"] * judge.factuality.score / 4
        + weights["materiality"] * judge.materiality.score / 4
        + weights["causal_discipline"] * judge.causal_discipline.score / 4
        + weights["coverage"] * judge.coverage.score / 4
        + weights["clarity"] * judge.clarity.score / 4
    )


def judge_hard_fail_categories(
    judge: AbsoluteJudgeOutput, scoring: ScoringConfig
) -> list[str]:
    hard = set(scoring.judge_hard_fail_categories)
    return sorted({e.category for e in judge.critical_errors if e.category in hard})


def sample_id_for(record: GenerationRecord, salt: str) -> str:
    content = sha256_text(record.raw_text or (record.output.model_dump_json() if record.output else record.task_id))
    return hashlib.sha256(f"{salt}:{content}".encode()).hexdigest()[:12]


def build_judge_messages(case: Case, candidate_json: str, sample_id: str, prompts_dir: Path) -> list[dict[str, str]]:
    system = load_prompt(prompts_dir, "judge_absolute")
    reference_lines = [
        "NOTAS DA REFERÊNCIA (uso interno do avaliador; não fazer parte da nota de estilo):",
        f"- judge_notes: {case.reference.judge_notes}",
        "- vetores aceitos: "
        + "; ".join(f"{g.label} [{', '.join(g.evidence_ids)}] ({g.confidence.value})" for g in case.reference.accepted_driver_groups),
        "- conclusões proibidas: "
        + "; ".join(f"{c.description} ({c.severity.value})" for c in case.reference.forbidden_conclusions),
        "- fatos críticos: " + ", ".join(case.reference.critical_fact_ids),
        "- must mention: " + ", ".join(case.reference.must_mention_fact_ids),
    ]
    user = "\n\n".join(
        [
            build_package(case),
            "\n".join(reference_lines),
            f"COMENTÁRIO CANDIDATO (sample_id={sample_id}):\n{candidate_json}",
            "Avalie conforme o system prompt e responda apenas com o JSON.",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class AbsoluteJudge:
    def __init__(
        self,
        *,
        client: OpenRouterClient,
        cfg: JudgeConfig,
        scoring: ScoringConfig,
        cache: ResponseCache,
        root: Path,
    ) -> None:
        self.client = client
        self.cfg = cfg
        self.scoring = scoring
        self.cache = cache
        self.root = root
        self.prompts_dir = root / "prompts"

    def _params(self) -> dict[str, object]:
        return {
            "temperature": self.cfg.temperature,
            "top_p": self.cfg.top_p,
            "max_tokens": self.cfg.max_tokens,
            "reasoning_effort": self.cfg.reasoning_effort,
        }

    async def grade_record(
        self, record: GenerationRecord, case: Case, *, use_cache: bool = True
    ) -> JudgeGrade:
        salt = f"{self.cfg.model}:{self.scoring.hard_fail_cap}"
        sample_id = sample_id_for(record, salt)
        candidate_json = (
            json.dumps(record.output.model_dump(mode="json"), ensure_ascii=False)
            if record.output
            else (record.raw_text or "")
        )
        key = judge_cache_key(
            candidate_output_hash=sha256_text(candidate_json),
            judge_model=self.cfg.model,
            judge_prompt_hash=sha256_text(load_prompt(self.prompts_dir, "judge_absolute")),
            reference_hash=case_reference_hash(case),
            judge_params=self._params(),
        )
        if use_cache:
            cached = self.cache.get("judge_absolute", key)
            if cached is not None and cached.get("judge_output") is not None:
                judge = AbsoluteJudgeOutput.model_validate(cached["judge_output"])
                return self._finalize(record, case, sample_id, judge, from_cache=True)
        messages = build_judge_messages(case, candidate_json, sample_id, self.prompts_dir)
        result = await self.client.generate(
            model_id=self.cfg.model,
            system=messages[0]["content"],
            user=messages[1]["content"],
            response_mode="json_schema",
            schema=JUDGE_JSON_SCHEMA,
            schema_name="judge_output",
            temperature=self.cfg.temperature,
            top_p=self.cfg.top_p,
            max_tokens=self.cfg.max_tokens,
            reasoning_effort=self.cfg.reasoning_effort,
        )
        if not result.ok or result.content is None:
            log_event(logger, "judge_error", task=record.task_id, kind=result.error_kind)
            return JudgeGrade(
                task_id=record.task_id,
                case_id=case.case_id,
                sample_id=sample_id,
                from_cache=False,
                judge_output=None,
                raw_score=None,
                final_score=None,
                hard_fail=False,
                hard_fail_reasons=[],
                error_kind=result.error_kind or "no_content",
            )
        try:
            judge = parse_absolute_judge(result.content)
        except (OutputParseError, Exception) as exc:  # noqa: BLE001
            log_event(logger, "judge_invalid", task=record.task_id, err=str(exc)[:120])
            return JudgeGrade(
                task_id=record.task_id,
                case_id=case.case_id,
                sample_id=sample_id,
                from_cache=False,
                judge_output=None,
                raw_score=None,
                final_score=None,
                hard_fail=False,
                hard_fail_reasons=[],
                error_kind="invalid_judge_response",
            )
        self.cache.put(
            "judge_absolute",
            key,
            {"judge_output": judge.model_dump(mode="json")},
            meta={"sample_id": sample_id},
        )
        return self._finalize(record, case, sample_id, judge, from_cache=False)

    def _finalize(
        self,
        record: GenerationRecord,
        case: Case,
        sample_id: str,
        judge: AbsoluteJudgeOutput,
        *,
        from_cache: bool,
    ) -> JudgeGrade:
        raw = compute_raw_score(judge, self.scoring.weights)
        judge_cats = judge_hard_fail_categories(judge, self.scoring)
        hard = bool(judge_cats)
        final = min(raw, float(self.scoring.hard_fail_cap)) if hard else raw
        return JudgeGrade(
            task_id=record.task_id,
            case_id=case.case_id,
            sample_id=sample_id,
            from_cache=from_cache,
            judge_output=judge,
            raw_score=raw,
            final_score=final,
            hard_fail=hard,
            hard_fail_reasons=judge_cats,
        )

    async def grade_all(
        self,
        records: list[GenerationRecord],
        cases: dict[str, Case],
        *,
        use_cache: bool = True,
        concurrency: int = 4,
    ) -> list[JudgeGrade]:
        sem = asyncio.Semaphore(concurrency)

        async def one(record: GenerationRecord) -> JudgeGrade:
            async with sem:
                return await self.grade_record(record, cases[record.case_id], use_cache=use_cache)

        return list(await asyncio.gather(*(one(r) for r in records)))
