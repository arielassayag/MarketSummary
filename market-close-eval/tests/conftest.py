"""Fixtures compartilhadas dos testes (sem rede, sem custo)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_eval.config import ExperimentConfig, ScoringConfig  # noqa: E402
from market_eval.schemas import AgentOutput, Case, Claim, Driver, KeyMove  # noqa: E402


@pytest.fixture()
def project_root() -> Path:
    return ROOT


@pytest.fixture()
def mini_case() -> Case:
    data = json.loads((ROOT / "tests" / "fixtures" / "mini_case.json").read_text(encoding="utf-8"))
    return Case.model_validate(data)


@pytest.fixture()
def scoring() -> ScoringConfig:
    return ScoringConfig(
        weights={"factuality": 30, "materiality": 25, "causal_discipline": 20, "coverage": 15, "clarity": 10},
        hard_fail_cap=49,
        word_range=[180, 220],
        headline_max_chars=90,
        limits={"key_moves": [3, 6], "drivers": [1, 3], "watch_items": [0, 3]},
        tolerances={"return_pct": 0.05, "change_pct": 0.05, "change_bps": 1.0, "contribution_bps": 0.5, "level": 0.05, "absolute_value": 0.05},
        sign_flip_is_failure=True,
        judge_hard_fail_categories=[
            "fabricated_fact", "fabricated_event", "unsupported_causal_as_fact",
            "return_as_contribution", "sign_error_critical", "value_error_critical",
            "unit_error_critical", "nonexistent_evidence_id", "schema_invalid",
            "central_contradiction",
        ],
    )


@pytest.fixture()
def exp_cfg() -> ExperimentConfig:
    return ExperimentConfig()


def _make_output(
    *,
    commentary_words: int = 200,
    headline: str = "Ibovespa sobe 1,5% com PTAX em queda",
    idx02_value: float = 1.5,
    fx02_value: float = -0.5,
    idx02_unit: str = "pct",
    idx02_mk: str = "return_pct",
    mention_news: bool = True,
    evidence: list[str] | None = None,
    claim_evidence: list[str] | None = None,
    driver_evidence: list[str] | None = None,
    key_moves_extra: list[KeyMove] | None = None,
) -> AgentOutput:
    filler = "mercado financeiro brasileiro fechamento pregão dados fontes oficiais juros câmbio fluxo estrangeiro"
    base = "O Ibovespa subiu 1,5% e o dólar caiu 0,5% no dia. " + " ".join([filler] * 40)
    words = base.split()
    while len(words) < commentary_words:
        base += " informação adicional do pacote sintético para teste."
        words = base.split()
    commentary = " ".join(words[:commentary_words])
    key_moves = [
        KeyMove(fact_id="IDX-02", subject="Ibovespa", measure_kind=idx02_mk, value=idx02_value, unit=idx02_unit, direction="up"),
        KeyMove(fact_id="FX-01", subject="USD/BRL (PTAX fechamento)", measure_kind="level", value=5.0, unit="brl_per_usd", direction="na"),
        KeyMove(fact_id="FX-02", subject="USD/BRL (PTAX fechamento)", measure_kind="change_pct", value=fx02_value, unit="pct", direction="down"),
    ] + (key_moves_extra or [])
    ev = evidence if evidence is not None else ["NEWS-01"]
    return AgentOutput(
        headline=headline,
        commentary=commentary,
        key_moves=key_moves,
        drivers=[Driver(claim="Copom no radar sustenta leitura.", claim_type="source_supported", evidence_ids=driver_evidence or ev, confidence="medium")],
        claims=[Claim(text="O Ibovespa subiu 1,5%.", claim_type="fact", evidence_ids=claim_evidence or ["IDX-02"])],
        watch_items=["Próxima decisão do Copom"],
    )


@pytest.fixture()
def make_output():  # type: ignore[no-untyped-def]
    """Fábrica de AgentOutput para os testes."""
    return _make_output
