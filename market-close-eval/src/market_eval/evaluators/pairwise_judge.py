"""Comparação pareada V1 x V2 (análise secundária).

Para cada combinação (modelo, caso, repetição), o judge recebe os dois outputs
anonimizados como A e B, nas duas ordens. Regra de consistência:
- ambas escolhem V2 -> vitória de V2; ambas V1 -> vitória de V1;
- divergência -> resultado instável; empate em ambas -> empate.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..agent import build_package, load_prompt
from ..cache import ResponseCache, pairwise_cache_key
from ..config import JudgeConfig
from ..logging_utils import log_event
from ..openrouter_client import OpenRouterClient
from ..schemas import (
    PAIRWISE_JSON_SCHEMA,
    Case,
    GenerationRecord,
    PairwiseOutput,
    parse_pairwise,
    sha256_text,
)

logger = logging.getLogger(__name__)


@dataclass
class PairwiseOutcome:
    model_id: str
    case_id: str
    split: str
    regime: str
    repetition: int
    outcome: str  # v2_win | v1_win | tie | unstable
    order1_choice: str
    order2_choice: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "case_id": self.case_id,
            "split": self.split,
            "regime": self.regime,
            "repetition": self.repetition,
            "outcome": self.outcome,
            "order1_choice": self.order1_choice,
            "order2_choice": self.order2_choice,
            "error": self.error,
        }


def outcome_from_choices(choice1: str, choice2: str) -> str:
    # choice refere-se ao rótulo A/B; na ordem 1, A=V1; na ordem 2, A=V2.
    v1_votes = (1 if choice1 == "A" else 0) + (1 if choice2 == "B" else 0)
    v2_votes = (1 if choice1 == "B" else 0) + (1 if choice2 == "A" else 0)
    if v1_votes == 2:
        return "v1_win"
    if v2_votes == 2:
        return "v2_win"
    if choice1 == "tie" and choice2 == "tie":
        return "tie"
    return "unstable"


def build_pair_messages(
    package: str,
    output_a_json: str,
    output_b_json: str,
    prompts_dir: Path,
) -> list[dict[str, str]]:
    system = load_prompt(prompts_dir, "judge_pairwise")
    user = "\n\n".join(
        [
            package,
            f"COMENTÁRIO A:\n{output_a_json}",
            f"COMENTÁRIO B:\n{output_b_json}",
            "Avalie e responda apenas com o JSON.",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class PairwiseJudge:
    def __init__(
        self,
        *,
        client: OpenRouterClient,
        cfg: JudgeConfig,
        cache: ResponseCache,
        root: Path,
    ) -> None:
        self.client = client
        self.cfg = cfg
        self.cache = cache
        self.prompts_dir = root / "prompts"

    def _params(self) -> dict[str, object]:
        return {
            "temperature": self.cfg.temperature,
            "top_p": self.cfg.top_p,
            "max_tokens": self.cfg.max_tokens,
            "reasoning_effort": self.cfg.reasoning_effort,
        }

    async def _ask(
        self,
        case: Case,
        output_a_json: str,
        output_b_json: str,
        *,
        use_cache: bool,
    ) -> PairwiseOutput | None:
        package = build_package(case)
        key = pairwise_cache_key(
            output_a_hash=sha256_text(output_a_json),
            output_b_hash=sha256_text(output_b_json),
            judge_model=self.cfg.model,
            judge_prompt_hash=sha256_text(load_prompt(self.prompts_dir, "judge_pairwise")),
            package_hash=sha256_text(package),
            judge_params=self._params(),
        )
        if use_cache:
            cached = self.cache.get("judge_pairwise", key)
            if cached is not None and cached.get("pairwise") is not None:
                return PairwiseOutput.model_validate(cached["pairwise"])
        messages = build_pair_messages(package, output_a_json, output_b_json, self.prompts_dir)
        result = await self.client.generate(
            model_id=self.cfg.model,
            system=messages[0]["content"],
            user=messages[1]["content"],
            response_mode="json_schema",
            schema=PAIRWISE_JSON_SCHEMA,
            schema_name="pairwise_output",
            temperature=self.cfg.temperature,
            top_p=self.cfg.top_p,
            max_tokens=self.cfg.max_tokens,
            reasoning_effort=self.cfg.reasoning_effort,
        )
        if not result.ok or result.content is None:
            log_event(logger, "pairwise_error", case=case.case_id, kind=result.error_kind)
            return None
        try:
            parsed = parse_pairwise(result.content)
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "pairwise_invalid", case=case.case_id, err=str(exc)[:120])
            return None
        self.cache.put("judge_pairwise", key, {"pairwise": parsed.model_dump(mode="json")})
        return parsed

    async def compare_pair(
        self,
        case: Case,
        v1: GenerationRecord,
        v2: GenerationRecord,
        *,
        use_cache: bool = True,
    ) -> PairwiseOutcome | None:
        v1_json = json.dumps(v1.output.model_dump(mode="json"), ensure_ascii=False) if v1.output else (v1.raw_text or "")
        v2_json = json.dumps(v2.output.model_dump(mode="json"), ensure_ascii=False) if v2.output else (v2.raw_text or "")
        first = await self._ask(case, v1_json, v2_json, use_cache=use_cache)  # A=V1
        second = await self._ask(case, v2_json, v1_json, use_cache=use_cache)  # A=V2
        if first is None or second is None:
            return PairwiseOutcome(
                model_id=v1.model_id,
                case_id=case.case_id,
                split=case.split.value,
                regime=case.regime.value,
                repetition=v1.repetition,
                outcome="unstable",
                order1_choice="",
                order2_choice="",
                error="judge_error",
            )
        return PairwiseOutcome(
            model_id=v1.model_id,
            case_id=case.case_id,
            split=case.split.value,
            regime=case.regime.value,
            repetition=v1.repetition,
            outcome=outcome_from_choices(first.choice, second.choice),
            order1_choice=first.choice,
            order2_choice=second.choice,
        )

    async def compare_all(
        self,
        records: list[GenerationRecord],
        cases: dict[str, Case],
        *,
        use_cache: bool = True,
        concurrency: int = 4,
    ) -> list[PairwiseOutcome]:
        # agrupa por (modelo, caso, repetição)
        groups: dict[tuple[str, str, int], dict[str, GenerationRecord]] = {}
        for r in records:
            if r.status.value != "completed" or r.output is None:
                continue
            groups.setdefault((r.model_id, r.case_id, r.repetition), {})[r.prompt_version] = r

        sem = asyncio.Semaphore(concurrency)

        async def one(pair: tuple[str, str, int], versions: dict[str, GenerationRecord]) -> PairwiseOutcome | None:
            if "v1" not in versions or "v2" not in versions:
                return None
            case = cases[pair[1]]
            async with sem:
                return await self.compare_pair(case, versions["v1"], versions["v2"], use_cache=use_cache)

        results = await asyncio.gather(*(one(k, v) for k, v in groups.items()))
        return [r for r in results if r is not None]
