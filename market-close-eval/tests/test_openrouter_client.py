"""Testes do cliente OpenRouter com mocks (sem rede) e do runner (estados)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import market_eval.openrouter_client as orc
from market_eval.cache import ResponseCache
from market_eval.config import ExperimentConfig
from market_eval.runner import Runner, Task, build_tasks, resume_pending
from market_eval.schemas import GenerationStatus


class FakeRetry(Exception):
    pass


class FakeAuth(Exception):
    pass


def fake_response(content: str = '{"ok": true}') -> SimpleNamespace:
    return SimpleNamespace(
        id="resp-1",
        model="fake/model",
        system_fingerprint="fp",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
                model_extra={"native_finish_reason": "stop"},
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
            model_extra={"cost": 0.0012},
            cost=0.0012,
        ),
    )


def make_client(monkeypatch, outcomes: list) -> orc.OpenRouterClient:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(orc, "RateLimitError", FakeRetry)
    monkeypatch.setattr(orc, "APITimeoutError", FakeRetry)
    monkeypatch.setattr(orc, "APIConnectionError", FakeRetry)
    monkeypatch.setattr(orc, "APIStatusError", FakeRetry)
    monkeypatch.setattr(orc, "AuthenticationError", FakeAuth)
    monkeypatch.setattr(orc, "PermissionDeniedError", FakeAuth)
    monkeypatch.setattr(orc.asyncio, "sleep", asyncio.sleep)
    client = orc.OpenRouterClient(api_key="test", max_attempts=4, backoff_base_s=0.001)
    calls = {"n": 0}

    class FakeCompletions:
        async def create(self, **kwargs: object) -> SimpleNamespace:
            calls["n"] += 1
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client.calls = calls  # type: ignore[attr-defined]
    return client


def test_retry_429_e_5xx_ate_sucesso(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = make_client(
        monkeypatch,
        outcomes=[FakeRetry("429"), FakeRetry("500"), fake_response('{"ok": 1}')],
    )
    result = asyncio.run(client.generate(model_id="m", system="s", user="u", response_mode="none"))
    assert result.ok and result.content == '{"ok": 1}'
    assert result.attempt == 3
    assert client.calls["n"] == 3
    assert result.cost_usd == 0.0012
    assert result.prompt_tokens == 100


def test_retry_exhausted(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = make_client(monkeypatch, outcomes=[FakeRetry("429")] * 4)
    result = asyncio.run(client.generate(model_id="m", system="s", user="u", response_mode="none"))
    assert not result.ok
    assert result.error_kind == "retry_exhausted"
    assert client.calls["n"] == 4


def test_erro_terminal_de_autenticacao(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = make_client(monkeypatch, outcomes=[FakeAuth("401")])
    result = asyncio.run(client.generate(model_id="m", system="s", user="u", response_mode="none"))
    assert not result.ok
    assert result.error_kind == "auth_error"
    assert client.calls["n"] == 1  # sem retry


def _runner_with_client(project_root, mini_case, tmp_cache, client) -> Runner:  # type: ignore[no-untyped-def]
    cfg = ExperimentConfig()
    cfg.cache.sqlite_path = str(tmp_cache)
    return Runner(
        cfg=cfg,
        root=project_root,
        run_id="test_run",
        cases={mini_case.case_id: mini_case},
        client=client,
        cache=ResponseCache(tmp_cache),
        model_ids=["fake/model"],
        prompt_versions=["v1"],
        synthetic=False,
    )


class StaticBackend:
    def __init__(self, content: str, calls: list[int] | None = None) -> None:
        self.content = content
        self.calls = calls if calls is not None else []

    async def generate(self, **kwargs: object) -> orc.GenerationResult:
        self.calls.append(1)
        return orc.GenerationResult(ok=True, content=self.content, latency_ms=1, attempt=1, finish_reason="stop")


def test_runner_resposta_truncada_invalida(project_root, mini_case, tmp_path) -> None:  # type: ignore[no-untyped-def]
    backend = StaticBackend('{"headline": "cortei o json')
    runner = _runner_with_client(project_root, mini_case, tmp_path / "c.db", backend)
    tasks = [Task(case_id=mini_case.case_id, split="dev", model_id="fake/model", prompt_version="v1", repetition=1, seed=1)]
    records = asyncio.run(runner.run_tasks(tasks))
    assert records[0].status == GenerationStatus.invalid_response


def test_runner_cache_e_retomada(project_root, mini_case, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from market_eval.schemas import AgentOutput

    good = json.dumps(
        AgentOutput(
            headline="h", commentary="c", key_moves=[], drivers=[], claims=[], watch_items=[]
        ).model_dump(mode="json"),
        ensure_ascii=False,
    )
    calls: list[int] = []
    backend = StaticBackend(good, calls)
    cache_path = tmp_path / "cache.db"
    runner = _runner_with_client(project_root, mini_case, cache_path, backend)
    tasks = [Task(case_id=mini_case.case_id, split="dev", model_id="fake/model", prompt_version="v1", repetition=1, seed=1)]
    records = asyncio.run(runner.run_tasks(tasks))
    assert records[0].status == GenerationStatus.completed
    assert records[0].from_cache is False
    assert len(calls) == 1

    # reexecução idêntica: 100% cache, nenhuma nova chamada (sem custo novo)
    runner2 = _runner_with_client(project_root, mini_case, cache_path, backend)
    records2 = asyncio.run(runner2.run_tasks(tasks))
    assert records2[0].from_cache is True
    assert len(calls) == 1

    # resume_pending não considera a tarefa pendente
    pending = resume_pending(tasks, records2)
    assert pending == []


def test_build_tasks_ordem_embaralhada_deterministica(mini_case) -> None:  # type: ignore[no-untyped-def]
    tasks_a = build_tasks([mini_case], ["m1", "m2"], ["v1", "v2"], 2, [1, 2], shuffle_seed=42)
    tasks_b = build_tasks([mini_case], ["m1", "m2"], ["v1", "v2"], 2, [1, 2], shuffle_seed=42)
    assert tasks_a == tasks_b
    assert len(tasks_a) == 8
    assert all(t.seed in (1, 2) for t in tasks_a)
