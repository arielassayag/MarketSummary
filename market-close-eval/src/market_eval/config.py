"""Carregamento das configurações YAML com tipagem Pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    concurrency: int = 4
    timeout_s: int = 120
    max_attempts: int = 5
    retry_backoff_base_s: float = 1.5
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 2000
    repetitions_dev: int = 2
    repetitions_holdout: int = 2
    seeds: list[int] = Field(default_factory=lambda: [20260827, 20260828])
    shuffle_seed: int = 42
    # esforço de raciocínio (parâmetro unificado OpenRouter); None = padrão do provedor
    reasoning_effort: str | None = "low"
    response_mode: Literal["json_schema", "json_object"] = "json_schema"


class CacheConfig(BaseModel):
    sqlite_path: str = "outputs/cache.db"


class JudgeConfig(BaseModel):
    model: str
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 4000
    max_attempts: int = 5
    reasoning_effort: str | None = "low"


class CandidatesConfig(BaseModel):
    preferences: dict[str, list[str]] = Field(default_factory=dict)
    judge_preferences: list[str] = Field(default_factory=list)


class PathsConfig(BaseModel):
    prompts_dir: str = "prompts"
    outputs_dir: str = "outputs"
    data_dir: str = "data"


class ExperimentConfig(BaseModel):
    run: RunConfig = RunConfig()
    cache: CacheConfig = CacheConfig()
    judge: JudgeConfig = JudgeConfig(model="anthropic/claude-opus-5")
    candidates: CandidatesConfig = CandidatesConfig()
    paths: PathsConfig = PathsConfig()


class ScoringConfig(BaseModel):
    weights: dict[str, int]
    hard_fail_cap: int = 49
    word_range: list[int] = Field(default_factory=lambda: [180, 220])
    headline_max_chars: int = 90
    limits: dict[str, list[int]] = Field(
        default_factory=lambda: {
            "key_moves": [3, 6],
            "drivers": [1, 3],
            "watch_items": [0, 3],
        }
    )
    tolerances: dict[str, float] = Field(default_factory=dict)
    sign_flip_is_failure: bool = True
    judge_hard_fail_categories: list[str] = Field(default_factory=list)


class ModelLockEntry(BaseModel):
    friendly_name: str
    exact_model_id: str
    provider: str
    role: Literal["candidate", "judge"]
    slot: str = ""
    input_price_usd_per_m: float
    output_price_usd_per_m: float
    context_length: int
    supported_parameters: list[str] = Field(default_factory=list)
    rationale: str = ""


class ModelLock(BaseModel):
    catalog_snapshot: dict[str, object] = Field(default_factory=dict)
    models: list[ModelLockEntry] = Field(default_factory=list)

    def candidates(self) -> list[ModelLockEntry]:
        return [m for m in self.models if m.role == "candidate"]

    def judge(self) -> ModelLockEntry | None:
        for m in self.models:
            if m.role == "judge":
                return m
        return None


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"config não encontrada: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML inválido (raiz não é um mapa): {path}")
    return data


def load_experiment(root: Path | None = None) -> ExperimentConfig:
    base = root or PROJECT_ROOT
    data = _load_yaml(base / "configs" / "experiment.yaml")
    return ExperimentConfig.model_validate(data)


def load_scoring(root: Path | None = None) -> ScoringConfig:
    base = root or PROJECT_ROOT
    data = _load_yaml(base / "configs" / "scoring.yaml")
    return ScoringConfig.model_validate(data)


def load_model_lock(root: Path | None = None) -> ModelLock:
    base = root or PROJECT_ROOT
    data = _load_yaml(base / "configs" / "models.lock.yaml")
    return ModelLock.model_validate(data)
