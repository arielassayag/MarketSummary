"""Testes para ProcessSpec, validação de DAG e detecção de ciclos."""

import pytest

from fechamento.contracts import ProcessSpec, ProcessStep, StepClassification
from fechamento.process import get_default_current_process, get_default_redesigned_process


def test_default_specs_valid() -> None:
    current = get_default_current_process()
    assert len(current.steps) == 10
    assert current.is_redesign is False

    redesigned = get_default_redesigned_process()
    assert len(redesigned.steps) == 8
    assert redesigned.is_redesign is True


def test_process_spec_duplicate_ids() -> None:
    steps = [
        ProcessStep(
            step_id="step_1",
            name="Etapa 1",
            objective="Obj 1",
            responsible="Resp",
            completion_rule="Rule",
            exception_destination="Dest",
            classification=StepClassification.CODE,
        ),
        ProcessStep(
            step_id="step_1",  # Duplicado!
            name="Etapa 1 Duplicada",
            objective="Obj 2",
            responsible="Resp",
            completion_rule="Rule",
            exception_destination="Dest",
            classification=StepClassification.CODE,
        ),
    ]
    with pytest.raises(ValueError, match="Identificadores de etapas .* devem ser únicos"):
        ProcessSpec(
            process_id="proc_test",
            title="Teste",
            description="Desc",
            steps=steps,
        )


def test_process_spec_missing_dependency() -> None:
    steps = [
        ProcessStep(
            step_id="step_1",
            name="Etapa 1",
            objective="Obj 1",
            responsible="Resp",
            dependencies=["step_inexistente"],
            completion_rule="Rule",
            exception_destination="Dest",
            classification=StepClassification.CODE,
        )
    ]
    with pytest.raises(ValueError, match="Dependência 'step_inexistente' .* não existe"):
        ProcessSpec(
            process_id="proc_test",
            title="Teste",
            description="Desc",
            steps=steps,
        )


def test_process_spec_cycle_detection() -> None:
    steps = [
        ProcessStep(
            step_id="step_A",
            name="Etapa A",
            objective="Obj A",
            responsible="Resp",
            dependencies=["step_B"],  # Ciclo A -> B -> A
            completion_rule="Rule",
            exception_destination="Dest",
            classification=StepClassification.CODE,
        ),
        ProcessStep(
            step_id="step_B",
            name="Etapa B",
            objective="Obj B",
            responsible="Resp",
            dependencies=["step_A"],
            completion_rule="Rule",
            exception_destination="Dest",
            classification=StepClassification.CODE,
        ),
    ]
    with pytest.raises(ValueError, match="Ciclo detectado no fluxo do processo"):
        ProcessSpec(
            process_id="proc_test",
            title="Teste",
            description="Desc",
            steps=steps,
        )
