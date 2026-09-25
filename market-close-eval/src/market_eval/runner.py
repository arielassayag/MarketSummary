"""Runner do experimento: tarefas, cache, checkpoint, retomada e concorrência.

Todas as tarefas são criadas ANTES da execução e embaralhadas com seed fixa,
reduzindo correlação entre ordem de execução e modelo/prompt. Cada resposta é
gravada (append + flush) em outputs/<run_id>/raw_generations.jsonl — o cache
SQLite garante que reexecutar o mesmo comando não gera nova cobrança.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .agent import compose_messages
from .cache import ResponseCache, generation_cache_key
from .config import ExperimentConfig
from .dataset import case_input_hash
from .logging_utils import log_event
from .openrouter_client import GenerationResult, OpenRouterClient
from .schemas import (
    AGENT_JSON_SCHEMA,
    Case,
    GenerationRecord,
    GenerationStatus,
    OutputParseError,
    parse_agent_output,
    sha256_text,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "agent-output-v2"  # v2: pacote passou a expor tokens de unidade


def brt_now() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).isoformat()


@dataclass(frozen=True)
class Task:
    case_id: str
    split: str
    model_id: str
    prompt_version: str
    repetition: int
    seed: int | None

    @property
    def task_id(self) -> str:
        return f"{self.case_id}|{self.split}|{self.model_id}|{self.prompt_version}|rep{self.repetition}"


def build_tasks(
    cases: list[Case],
    model_ids: list[str],
    prompt_versions: list[str],
    repetitions: int,
    seeds: list[int],
    shuffle_seed: int,
) -> list[Task]:
    tasks: list[Task] = []
    for case in cases:
        for model_id in model_ids:
            for prompt_version in prompt_versions:
                for rep in range(1, repetitions + 1):
                    seed = seeds[(rep - 1) % len(seeds)] if seeds else None
                    tasks.append(
                        Task(
                            case_id=case.case_id,
                            split=case.split.value,
                            model_id=model_id,
                            prompt_version=prompt_version,
                            repetition=rep,
                            seed=seed,
                        )
                    )
    rng = random.Random(shuffle_seed)
    rng.shuffle(tasks)
    return tasks


class SyntheticBackend:
    """Backend determinístico OFFLINE (smoke test). Nunca usa rede nem cobrança.

    Produz saídas válidas com diferenças pequenas entre V1 e V2, para exercitar
    o pipeline. Tudo é marcado como synthetic=True e nunca entra em relatório
    de publicação.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        *,
        model_id: str,
        system: str,
        user: str,
        response_mode: str = "json_schema",
        schema: dict[str, object] | None = None,
        schema_name: str = "response",
        temperature: float = 0.0,
        top_p: float = 1.0,
        max_tokens: int = 2000,
        seed: int | None = None,
        reasoning_effort: str | None = None,
    ) -> GenerationResult:
        self.calls += 1
        date = user.splitlines()[0].replace("PACOTE DE FECHAMENTO — ", "").strip()
        facts: list[tuple[str, str, str, float | None, str, str]] = []
        for line in user.splitlines():
            if line.startswith("[") and "|" in line:
                fid = line[1 : line.index("]")]
                parts = [p.strip() for p in line.split("|")]
                subject = parts[0].split("] ", 1)[1] if "] " in parts[0] else fid
                facts.append((fid, subject, "", None, "", ""))
        # recupera dados estruturados direto do system (fallback simples p/ smoke)
        is_v2 = "síntese factual, material e direta" in system
        picked = facts[:4] if len(facts) >= 4 else facts
        key_moves = []
        for fid, subject, _mk, _val, _unit, _dir in picked:
            key_moves.append(
                {"fact_id": fid, "subject": subject, "measure_kind": "text_only", "value": None, "unit": "none", "direction": "na"}
            )
        if len(key_moves) < 3:
            for fid, subject, _mk, _val, _unit, _dir in facts:
                if all(km["fact_id"] != fid for km in key_moves):
                    key_moves.append({"fact_id": fid, "subject": subject, "measure_kind": "text_only", "value": None, "unit": "none", "direction": "na"})
                if len(key_moves) == 3:
                    break
        driver_ids = [km["fact_id"] for km in key_moves[:2]]
        claim_ids = [km["fact_id"] for km in key_moves[:1]]
        commentary = (
            f"Pregão de {date}: o Ibovespa e o câmbio definiram o tom da sessão, "
            "com movimentos registrados no pacote. Os dados de referência mostram a direção "
            "dos principais ativos e as fontes oficiais sustentam as leituras abaixo. "
            "Entre os destaques, os fatos listados em key_moves concentram as variações "
            "mais relevantes do dia, enquanto os eventos reportados ajudam a explicar o "
            "contexto. O câmbio acompanhou o humor externo e os fluxos do dia. "
            "Vale acompanhar a confirmação dos vetores nas próximas sessões e a "
            "divulgação de novos dados que possam confirmar ou refutar as leituras de hoje. "
            "Esta é uma saída sintética do smoke test, com estrutura completa mas sem "
            "análise real de mercado, apenas para validação do pipeline de avaliação. "
            "Recomenda-se não usar este texto para qualquer fim editorial. "
            "Os vetores do dia devem ser confirmados com os dados consolidados."
        )
        word_count = len(commentary.split())
        while word_count < 185:
            commentary += " Conteúdo sintético adicional para atender ao intervalo de palavras do schema."
            word_count = len(commentary.split())
        payload = {
            "headline": f"[SMOKE SINTÉTICO] Fechamento de {date}",
            "commentary": commentary,
            "key_moves": key_moves[:4] if is_v2 else key_moves[:3],
            "drivers": [
                {
                    "claim": "Vetores do dia conforme pacote sintético.",
                    "claim_type": "inference",
                    "evidence_ids": driver_ids,
                    "confidence": "medium" if is_v2 else "high",
                }
            ],
            "claims": [
                {
                    "text": "Os principais movimentos do dia estão no pacote.",
                    "claim_type": "fact",
                    "evidence_ids": claim_ids,
                }
            ],
            "watch_items": ["Confirmação dos vetores nas próximas sessões"],
        }
        import time as _time

        await asyncio.sleep(0.01)
        return GenerationResult(
            ok=True,
            content=json.dumps(payload, ensure_ascii=False),
            response_id=f"synthetic-{self.calls}",
            model_returned=model_id,
            latency_ms=int(_time.monotonic() * 1000) % 1000,
            finish_reason="stop",
            attempt=1,
            prompt_tokens=len(system.split()) + len(user.split()),
            completion_tokens=len(json.dumps(payload).split()),
            total_tokens=len(system.split()) + len(user.split()) + len(json.dumps(payload).split()),
            cost_usd=0.0,
        )


class Runner:
    def __init__(
        self,
        *,
        cfg: ExperimentConfig,
        root: Path,
        run_id: str,
        cases: dict[str, Case],
        client: OpenRouterClient | SyntheticBackend,
        cache: ResponseCache,
        model_ids: list[str],
        prompt_versions: list[str] | None = None,
        synthetic: bool = False,
    ) -> None:
        self.cfg = cfg
        self.root = root
        self.run_id = run_id
        self.cases = cases
        self.client = client
        self.cache = cache
        self.model_ids = model_ids
        self.prompt_versions = prompt_versions or ["v1", "v2"]
        self.synthetic = synthetic
        self.out_dir = root / cfg.paths.outputs_dir / run_id
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.out_dir / "raw_generations.jsonl"
        self._write_lock = asyncio.Lock()
        self.prompts_dir = root / cfg.paths.prompts_dir

    def generation_params(self) -> dict[str, object]:
        return {
            "temperature": self.cfg.run.temperature,
            "top_p": self.cfg.run.top_p,
            "max_tokens": self.cfg.run.max_tokens,
            "response_mode": self.cfg.run.response_mode,
            "reasoning_effort": self.cfg.run.reasoning_effort,
            "schema_version": SCHEMA_VERSION,
        }

    def cache_key_for(self, task: Task, case: Case) -> str:
        return generation_cache_key(
            case_id=case.case_id,
            split=case.split.value,
            model_id=task.model_id,
            prompt_version=task.prompt_version,
            prompt_hash=sha256_text(self._prompt_text(task.prompt_version)),
            common_system_hash=sha256_text(self._prompt_text("common")),
            input_hash=case_input_hash(case),
            repetition=task.repetition,
            generation_params=self.generation_params(),
            schema_version=SCHEMA_VERSION,
        )

    def _prompt_text(self, key: str) -> str:
        from .agent import load_prompt

        return load_prompt(self.prompts_dir, key)

    async def _append(self, record: GenerationRecord) -> None:
        async with self._write_lock:
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
                fh.flush()

    async def run_tasks(self, tasks: list[Task], *, use_cache: bool = True) -> list[GenerationRecord]:
        sem = asyncio.Semaphore(self.cfg.run.concurrency)
        done_cache: dict[str, GenerationRecord] = {}

        async def one(task: Task) -> GenerationRecord:
            async with sem:
                if task.task_id in done_cache:
                    return done_cache[task.task_id]
                record = await self._execute(task, use_cache=use_cache)
                done_cache[task.task_id] = record
                await self._append(record)
                log_event(
                    logger,
                    "generation",
                    task=task.task_id,
                    status=record.status.value,
                    cached=record.from_cache,
                    synthetic=record.synthetic,
                )
                return record

        return list(await asyncio.gather(*(one(t) for t in tasks)))

    async def _execute(self, task: Task, *, use_cache: bool) -> GenerationRecord:
        case = self.cases[task.case_id]
        key = self.cache_key_for(task, case)
        base = {
            "task_id": task.task_id,
            "run_id": self.run_id,
            "case_id": case.case_id,
            "split": case.split.value,
            "regime": case.regime.value,
            "model_id": task.model_id,
            "prompt_version": task.prompt_version,
            "repetition": task.repetition,
            "seed": task.seed,
            "cache_key": key,
        }

        if use_cache:
            cached = self.cache.get("generation", key)
            if cached is not None:
                record = GenerationRecord.model_validate(
                    {
                        **base,
                        "status": GenerationStatus.completed.value,
                        "created_at": brt_now(),
                        **cached,
                    }
                )
                record.from_cache = True
                record.status = GenerationStatus.completed
                return record

        messages = compose_messages(case, task.prompt_version, self.prompts_dir)
        result = await self.client.generate(
            model_id=task.model_id,
            system=messages[0]["content"],
            user=messages[1]["content"],
            response_mode=self.cfg.run.response_mode,
            schema=AGENT_JSON_SCHEMA,
            schema_name="agent_output",
            temperature=self.cfg.run.temperature,
            top_p=self.cfg.run.top_p,
            max_tokens=self.cfg.run.max_tokens,
            seed=task.seed,
            reasoning_effort=self.cfg.run.reasoning_effort,
        )
        common = {
            "response_id": result.response_id,
            "model_returned": result.model_returned,
            "system_fingerprint": result.system_fingerprint,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "reasoning_tokens": result.reasoning_tokens,
            "total_tokens": result.total_tokens,
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
            "finish_reason": result.finish_reason,
            "native_finish_reason": result.native_finish_reason,
            "attempt": result.attempt,
        }
        if not result.ok:
            status = (
                GenerationStatus.failed_terminal
                if result.error_kind in ("auth_error", "bad_request", "api_error")
                else GenerationStatus.retry_exhausted
            )
            return GenerationRecord.model_validate(
                {
                    **base,
                    "status": status.value,
                    "synthetic": self.synthetic,
                    "error_kind": result.error_kind,
                    "error_detail": (result.error_detail or "")[:500],
                    "created_at": brt_now(),
                    **common,
                }
            )
        if not result.content or not result.content.strip():
            # ok=True com conteúdo vazio: típico de truncamento por max_tokens em
            # modelos de raciocínio (todo o orçamento foi para reasoning)
            return GenerationRecord.model_validate(
                {
                    **base,
                    "status": GenerationStatus.invalid_response.value,
                    "synthetic": self.synthetic,
                    "error_kind": "empty_content",
                    "error_detail": (
                        f"resposta vazia (finish_reason={result.finish_reason}); "
                        "considere aumentar max_tokens"
                    ),
                    "created_at": brt_now(),
                    **common,
                }
            )
        try:
            output = parse_agent_output(result.content)
        except OutputParseError as exc:
            return GenerationRecord.model_validate(
                {
                    **base,
                    "status": GenerationStatus.invalid_response.value,
                    "synthetic": self.synthetic,
                    "raw_text": result.content[:2000],
                    "error_kind": "invalid_response",
                    "error_detail": str(exc)[:500],
                    "created_at": brt_now(),
                    **common,
                }
            )
        payload = {"output": output.model_dump(mode="json"), "raw_text": result.content[:2000], **common}
        self.cache.put("generation", key, payload, meta={"synthetic": self.synthetic})
        return GenerationRecord.model_validate(
            {
                **base,
                "status": GenerationStatus.completed.value,
                "from_cache": False,
                "synthetic": self.synthetic,
                "output": output.model_dump(mode="json"),
                "raw_text": result.content[:2000],
                "created_at": brt_now(),
                **common,
            }
        )


def load_records(run_dir: Path) -> list[GenerationRecord]:
    path = run_dir / "raw_generations.jsonl"
    if not path.exists():
        return []
    # última ocorrência de cada task_id vence (checkpoint em append; retomada sobrescreve)
    by_task: dict[str, GenerationRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = GenerationRecord.model_validate(json.loads(line))
            by_task[record.task_id] = record
    return list(by_task.values())


def resume_pending(tasks: list[Task], records: list[GenerationRecord]) -> list[Task]:
    """Retorna tarefas sem registro concluído (para retomada com --resume)."""
    completed = {r.task_id for r in records if r.status == GenerationStatus.completed}
    return [t for t in tasks if t.task_id not in completed]
