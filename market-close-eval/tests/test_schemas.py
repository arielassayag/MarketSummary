"""Testes de schemas Pydantic (validações do dataset)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from market_eval.schemas import (
    AgentOutput,
    Case,
    Direction,
    Fact,
    MeasureKind,
    Unit,
    parse_agent_output,
)


def _fact(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "fact_id": "IDX-01",
        "category": "index",
        "subject": "Ibovespa",
        "statement": "Fecho do índice (teste).",
        "measure_kind": "return_pct",
        "value": 1.0,
        "unit": "pct",
        "direction": "up",
        "observed_at": "2026-03-10T18:00:00-03:00",
        "source": {"name": "T", "url": "https://example.com/a", "source_tier": 3, "published_at": None},
    }
    base.update(overrides)
    return base


class TestFact:
    def test_quantitativo_exige_valor(self) -> None:
        with pytest.raises(ValidationError):
            Fact.model_validate(_fact(value=None))

    def test_text_only_sem_valor(self) -> None:
        fact = Fact.model_validate(_fact(measure_kind="text_only", value=None, unit="none", direction="na"))
        assert fact.value is None

    def test_direcao_incoerente(self) -> None:
        with pytest.raises(ValidationError, match="incoerente"):
            Fact.model_validate(_fact(value=1.0, direction="down"))

    def test_contribuicao_nao_pode_ser_pct(self) -> None:
        with pytest.raises(ValidationError, match="unidade"):
            Fact.model_validate(_fact(measure_kind="return_pct", unit="bps"))

    def test_url_invalida(self) -> None:
        with pytest.raises(ValidationError, match="URL"):
            Fact.model_validate(_fact(source={"name": "T", "url": "ftp://x", "source_tier": 1, "published_at": None}))

    def test_tipos_distintos_retorno_vs_contribuicao(self) -> None:
        r = Fact.model_validate(_fact(measure_kind="return_pct", unit="pct"))
        c = Fact.model_validate(
            _fact(fact_id="EQ-01-C", measure_kind="contribution_bps", unit="bps", value=25.0, direction="up")
        )
        assert r.measure_kind == MeasureKind.return_pct
        assert c.measure_kind == MeasureKind.contribution_bps
        assert MeasureKind.return_pct != MeasureKind.contribution_bps
        assert Direction.up == c.direction


class TestCase:
    def test_fact_id_duplicado_rejeitado(self, mini_case: Case) -> None:
        data = mini_case.model_dump(mode="json")
        dup = dict(data["input"]["facts"][0])
        dup["fact_id"] = data["input"]["facts"][1]["fact_id"]
        data["input"]["facts"].append(dup)
        with pytest.raises(ValidationError, match="duplicado"):
            Case.model_validate(data)

    def test_ids_de_referencia_inexistentes(self, mini_case: Case) -> None:
        from market_eval.dataset import validate_reference_ids

        data = mini_case.model_dump(mode="json")
        data["reference"]["critical_fact_ids"].append("FANTASMA-99")
        case = Case.model_validate(data)
        errors = validate_reference_ids(case)
        assert any("FANTASMA-99" in e for e in errors)


class TestAgentOutput:
    def test_parse_json_com_cerca_de_codigo(self) -> None:
        text = '```json\n{"headline": "h", "commentary": "c", "key_moves": [], "drivers": [], "claims": [], "watch_items": []}\n```'
        out = parse_agent_output(text)
        assert out.headline == "h"

    def test_parse_json_invalido(self) -> None:
        from market_eval.schemas import OutputParseError

        with pytest.raises(OutputParseError):
            parse_agent_output("isto não é json")

    def test_parse_schema_invalido(self) -> None:
        from market_eval.schemas import OutputParseError

        with pytest.raises(OutputParseError):
            parse_agent_output('{"headline": 1}')

    def test_agent_output_tipo(self) -> None:
        out = AgentOutput(
            headline="h", commentary="c", key_moves=[], drivers=[], claims=[], watch_items=[]
        )
        assert out.watch_items == []
        assert Unit.pct.value == "pct"
