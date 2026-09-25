"""Testes do avaliador determinístico."""

from __future__ import annotations

from market_eval.evaluators.deterministic import DeterministicGrade, grade_output, word_count
from market_eval.schemas import KeyMove


def test_word_count() -> None:
    assert word_count("um dois três") == 3
    assert word_count("") == 0
    assert word_count("a\nb\tc  d") == 4


def test_output_valido_passa(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    grade = grade_output(mini_case, make_output(), scoring, task_id="t")
    assert isinstance(grade, DeterministicGrade)
    assert grade.schema_valid
    assert grade.length_valid
    assert grade.headline_ok
    assert grade.key_moves_count_ok and grade.drivers_count_ok
    assert grade.critical_fact_recall == 1.0
    assert grade.must_mention_recall == 1.0
    assert not grade.hard_fail
    assert grade.failure_categories == []


def test_contagem_palavras_fora(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    grade = grade_output(mini_case, make_output(commentary_words=50), scoring)
    assert not grade.length_valid
    assert "word_count" in grade.failure_categories


def test_valor_errado_em_fato_critico_hards_fail(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    grade = grade_output(mini_case, make_output(idx02_value=2.9), scoring)
    assert "numeric_mismatch" in grade.failure_categories
    assert grade.hard_fail


def test_troca_de_sinal_em_fato_critico(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    grade = grade_output(mini_case, make_output(fx02_value=0.5), scoring)
    assert "sign_flip" in grade.failure_categories
    assert grade.hard_fail


def test_valor_errado_em_fato_nao_critico_nao_e_hard_fail(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    # FX-01 (level) não é crítico: valor trocado não derruba hard_fail
    grade = grade_output(mini_case, make_output(), scoring)
    assert not grade.hard_fail


def test_unidade_errada_em_fato_critico(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    out = make_output()
    out.key_moves[0] = KeyMove(
        fact_id="IDX-02", subject="Ibovespa", measure_kind="return_pct", value=1.5, unit="bps", direction="up"
    )
    grade = grade_output(mini_case, out, scoring)
    assert "unit_mismatch" in grade.failure_categories
    assert grade.hard_fail


def test_measure_kind_trocado_retorno_como_contribuicao(mini_case, scoring, make_output) -> None:
    out = make_output()
    out.key_moves[0] = KeyMove(
        fact_id="IDX-02", subject="Ibovespa", measure_kind="contribution_bps", value=1.5, unit="pct", direction="up"
    )
    grade = grade_output(mini_case, out, scoring)
    assert "measure_kind_mismatch" in grade.failure_categories
    assert grade.return_as_contribution_violation
    assert grade.hard_fail


def test_texto_menciona_contribuicao_sem_fato_de_contribuicao(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    out = make_output()
    out.commentary = (
        "A Petrobras contribuiu com 10 pontos-base para o índice. " + " ".join(["palavra"] * 60)
    )
    grade = grade_output(mini_case, out, scoring)
    assert "return_as_contribution" in grade.failure_categories
    assert grade.hard_fail


def test_mencao_qualitativa_de_contribuicao_nao_e_hard_fail(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    out = make_output()
    out.commentary = "Fatores externos contribuíram para o clima de cautela. " + " ".join(["palavra"] * 60)
    grade = grade_output(mini_case, out, scoring)
    assert "return_as_contribution" not in grade.failure_categories
    assert not grade.hard_fail


def test_id_inexistente_e_hard_fail(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    grade = grade_output(mini_case, make_output(claim_evidence=["FANTASMA-01"]), scoring)
    assert "unknown_fact_id" in grade.failure_categories
    assert grade.hard_fail


def test_key_moves_fora_da_faixa(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    out = make_output()
    out.key_moves = out.key_moves[:2]
    grade = grade_output(mini_case, out, scoring)
    assert "key_moves_count" in grade.failure_categories


def test_output_none_hard_fail(mini_case, scoring) -> None:  # type: ignore[no-untyped-def]
    grade = grade_output(mini_case, None, scoring, json_parse_ok=False)
    assert grade.hard_fail
    assert "json_invalid" in grade.failure_categories


def test_tolerancias_aceitam_pequena_diferenca(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    grade = grade_output(mini_case, make_output(idx02_value=1.52), scoring)
    assert "numeric_mismatch" not in grade.failure_categories


def test_duplicates(mini_case, scoring, make_output) -> None:  # type: ignore[no-untyped-def]
    out = make_output()
    out.key_moves.append(KeyMove(fact_id="IDX-02", subject="Ibovespa", measure_kind="return_pct", value=1.5, unit="pct", direction="up"))
    grade = grade_output(mini_case, out, scoring)
    assert "duplicate_id" in grade.failure_categories
