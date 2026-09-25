"""Testes do cache SQLite e das chaves determinísticas."""

from __future__ import annotations

from market_eval.cache import (
    ResponseCache,
    generation_cache_key,
    judge_cache_key,
)


def test_cache_idempotente(tmp_path) -> None:  # type: ignore[no-untyped-def]
    cache = ResponseCache(tmp_path / "cache.db")
    key = "k1"
    assert cache.get("generation", key) is None
    cache.put("generation", key, {"output": {"headline": "h"}}, meta={"a": 1})
    first = cache.get("generation", key)
    assert first is not None and first["output"]["headline"] == "h"
    # reexecução (put igual) não duplica nem muda payload
    cache.put("generation", key, {"output": {"headline": "h"}}, meta={"a": 1})
    assert cache.get("generation", key) == first
    stats = cache.stats()
    assert stats["generation"] == 1
    cache.close()


def test_generation_key_deterministica_e_sensivel() -> None:
    common = dict(
        case_id="c1",
        split="dev",
        model_id="m",
        prompt_version="v1",
        prompt_hash="ph",
        common_system_hash="ch",
        input_hash="ih",
        repetition=1,
        generation_params={"temperature": 0.0},
        schema_version="v1",
    )
    k1 = generation_cache_key(**common)
    k2 = generation_cache_key(**common)
    assert k1 == k2
    different_repetition = dict(common, repetition=2)
    assert generation_cache_key(**different_repetition) != k1
    different_model = dict(common, model_id="m2")
    assert generation_cache_key(**different_model) != k1
    different_params = dict(common, generation_params={"temperature": 0.7})
    assert generation_cache_key(**different_params) != k1
    different_prompt = dict(common, prompt_hash="other")
    assert generation_cache_key(**different_prompt) != k1


def test_judge_key_inclui_referencia_e_output() -> None:
    base = dict(
        candidate_output_hash="oh",
        judge_model="j",
        judge_prompt_hash="ph",
        reference_hash="rh",
        judge_params={"temperature": 0.0},
    )
    assert judge_cache_key(**base) == judge_cache_key(**base)
    assert judge_cache_key(**dict(base, reference_hash="other")) != judge_cache_key(**base)
    assert judge_cache_key(**dict(base, candidate_output_hash="other")) != judge_cache_key(**base)
