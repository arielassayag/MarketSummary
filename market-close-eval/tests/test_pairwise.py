"""Testes do judge pareado (inversão A/B) e da proteção contra vazamento no judge."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from market_eval.cache import ResponseCache
from market_eval.config import ExperimentConfig
from market_eval.evaluators.absolute_judge import build_judge_messages
from market_eval.evaluators.pairwise_judge import PairwiseJudge, outcome_from_choices
from market_eval.schemas import AgentOutput, GenerationRecord, GenerationStatus


def test_outcome_from_choices() -> None:
    # ordem1: A=V1, B=V2; ordem2: A=V2, B=V1
    assert outcome_from_choices("A", "B") == "v1_win"  # ambos apontam V1
    assert outcome_from_choices("B", "A") == "v2_win"  # ambos apontam V2
    assert outcome_from_choices("tie", "tie") == "tie"
    assert outcome_from_choices("A", "A") == "unstable"
    assert outcome_from_choices("B", "B") == "unstable"
    assert outcome_from_choices("A", "tie") == "unstable"
    assert outcome_from_choices("B", "tie") == "unstable"


def _record(version: str, headline: str) -> GenerationRecord:
    out = AgentOutput(
        headline=headline,
        commentary="texto " * 120,
        key_moves=[],
        drivers=[],
        claims=[],
        watch_items=[],
    )
    return GenerationRecord.model_validate(
        {
            "task_id": f"c|dev|m|{version}|rep1",
            "run_id": "r",
            "case_id": "c",
            "split": "dev",
            "regime": "calm",
            "model_id": "m",
            "prompt_version": version,
            "repetition": 1,
            "seed": 1,
            "status": GenerationStatus.completed.value,
            "output": out.model_dump(mode="json"),
            "created_at": "2026-08-27T12:00:00-03:00",
        }
    )


class OrderDetectingBackend:
    """Judge fake: escolhe SEMPRE o texto com headline 'PREFIRO' na posição A."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, **kwargs: object) -> SimpleNamespace:
        user = str(kwargs["user"])
        self.prompts.append(user)
        idx_a = user.index("COMENTÁRIO A:")
        chunk_a = user[idx_a : idx_a + 400]
        choice = "A" if "PREFIRO" in chunk_a else "B"
        return SimpleNamespace(
            ok=True,
            content=json.dumps({"choice": choice, "factuality_winner": choice, "reason": "r"}),
            latency_ms=1,
            attempt=1,
        )


def test_pairwise_inversao_ab(project_root, mini_case, tmp_path) -> None:  # type: ignore[no-untyped-def]
    cfg = ExperimentConfig()
    backend = OrderDetectingBackend()

    class Client:
        async def generate(self, **kwargs: object) -> object:
            return await backend.generate(**kwargs)

    judge = PairwiseJudge(
        client=Client(),
        cfg=cfg.judge,
        cache=ResponseCache(tmp_path / "cache.db"),
        root=project_root,
    )
    v1 = _record("v1", "texto comum")
    v2 = _record("v2", "texto PREFIRO")
    outcome = asyncio.run(judge.compare_pair(mini_case, v1, v2, use_cache=False))
    assert outcome is not None
    # ordem1: A=V1 -> escolhe B (V2); ordem2: A=V2 (PREFIRO) -> escolhe A (V2) => v2_win
    assert outcome.outcome == "v2_win"
    assert outcome.order1_choice == "B" and outcome.order2_choice == "A"

    v1b = _record("v1", "texto PREFIRO")
    v2b = _record("v2", "texto comum")
    outcome2 = asyncio.run(judge.compare_pair(mini_case, v1b, v2b, use_cache=False))
    assert outcome2 is not None and outcome2.outcome == "v1_win"

    # divergência -> instável
    class FlipFlopBackend(OrderDetectingBackend):
        async def generate(self, **kwargs: object) -> SimpleNamespace:
            result = await super().generate(**kwargs)
            if len(self.prompts) % 2 == 0:  # segunda ordem responde "B" (=V1)
                result.content = json.dumps({"choice": "B", "factuality_winner": "B", "reason": "r"})
            return result

    backend3 = FlipFlopBackend()

    class Client3:
        async def generate(self, **kwargs: object) -> object:
            return await backend3.generate(**kwargs)

    judge3 = PairwiseJudge(
        client=Client3(),
        cfg=cfg.judge,
        cache=ResponseCache(tmp_path / "cache3.db"),
        root=project_root,
    )
    outcome3 = asyncio.run(judge3.compare_pair(mini_case, v1, v2, use_cache=False))
    assert outcome3 is not None and outcome3.outcome == "unstable"


def test_judge_nao_ve_modelo_nem_prompt(project_root, mini_case) -> None:  # type: ignore[no-untyped-def]
    candidate = json.dumps({"headline": "h", "commentary": "c", "key_moves": []}, ensure_ascii=False)
    messages = build_judge_messages(mini_case, candidate, "sample123", project_root / "prompts")
    everything = "\n".join(m["content"] for m in messages)
    forbidden = [
        "gpt",
        "claude",
        "gemini",
        "deepseek",
        "openai",
        "anthropic",
        "google",
        "Prompt V1",
        "Prompt V2",
        "candidate_v1",
        "candidate_v2",
        "openrouter",
    ]
    for token in forbidden:
        assert token.lower() not in everything.lower(), f"vazamento: {token}"


def test_judge_absolute_usa_cache(project_root, mini_case, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from market_eval.config import ScoringConfig
    from market_eval.evaluators.absolute_judge import AbsoluteJudge

    cfg = ExperimentConfig()
    calls = {"n": 0}
    judge_json = json.dumps(
        {
            "factuality": {"score": 3, "reason": "r", "unsupported_claims": []},
            "materiality": {"score": 3, "reason": "r", "missed_key_facts": []},
            "causal_discipline": {"score": 3, "reason": "r", "unsupported_causal_claims": []},
            "coverage": {"score": 3, "reason": "r"},
            "clarity": {"score": 3, "reason": "r"},
            "critical_errors": [],
            "overall_notes": "",
        }
    )

    class Client:
        async def generate(self, **kwargs: object) -> SimpleNamespace:
            calls["n"] += 1
            return SimpleNamespace(ok=True, content=judge_json, latency_ms=1, attempt=1)

    scoring = ScoringConfig(
        weights={"factuality": 30, "materiality": 25, "causal_discipline": 20, "coverage": 15, "clarity": 10},
        judge_hard_fail_categories=["fabricated_fact"],
    )
    judge = AbsoluteJudge(
        client=Client(),
        cfg=cfg.judge,
        scoring=scoring,
        cache=ResponseCache(tmp_path / "cache.db"),
        root=project_root,
    )
    record = _record("v1", "h")
    g1 = asyncio.run(judge.grade_record(record, mini_case, use_cache=True))
    g2 = asyncio.run(judge.grade_record(record, mini_case, use_cache=True))
    assert calls["n"] == 1  # segunda passou no cache
    assert g1.raw_score == g2.raw_score == 75.0
    assert g1.from_cache is False and g2.from_cache is True
