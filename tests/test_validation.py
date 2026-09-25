"""Testes para o validador de rascunhos e conferência determinística."""

from datetime import UTC, datetime

from fechamento.contracts import ClaimType, CommentaryDraft, CommentaryParagraph
from fechamento.evidence import organize_evidence
from fechamento.ingestion import load_and_validate_package
from fechamento.metrics import compute_all_metrics
from fechamento.validation import (
    find_unauthorized_numbers,
    resolve_text_placeholders,
    validate_draft,
)


def test_find_unauthorized_numbers_detection() -> None:
    # Texto com números financeiros explícitos não autorizados
    text_with_hallucination = "O IBOV subiu 2,45% e o dólar fechou a R$ 5,60 com alta de 15 bps."
    violations = find_unauthorized_numbers(text_with_hallucination)
    assert len(violations) >= 2

    # Texto limpo contendo apenas tickers e datas
    text_clean = "No pregão de 18/09/2026, as ações de PETR4 e VALE3 oscilaram conforme {{fact:ibov.return_pct}}."
    clean_violations = find_unauthorized_numbers(text_clean)
    assert len(clean_violations) == 0


def test_resolve_placeholders_missing() -> None:
    pkg = load_and_validate_package("data/demo/normal")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert pkg.manifest is not None
    ev = organize_evidence(metrics, pkg.manifest, pkg.eligible_news, pkg.excluded_news)

    text = "Variação do IBOV: {{fact:ibov.return_pct}} e fato fantasma: {{fact:inexistente.return_pct}}."
    rendered, errors = resolve_text_placeholders(text, ev.factbook, {n.news_id: n for n in ev.eligible_news})

    assert len(errors) == 1
    assert "inexistente.return_pct" in errors[0]
    assert "+1,00%" in rendered


def test_validate_draft_prohibited_terms() -> None:
    pkg = load_and_validate_package("data/demo/normal")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert pkg.manifest is not None
    ev = organize_evidence(metrics, pkg.manifest, pkg.eligible_news, pkg.excluded_news)

    bad_draft = CommentaryDraft(
        draft_id="bad_1",
        paragraphs=[
            CommentaryParagraph(
                paragraph_id=1,
                text="Recomendamos compra de PETR4 com preço-alvo de R$ 50,00.",
                claim_type=ClaimType.FACTUAL,
                fact_refs=[],
                news_refs=[],
            )
        ],
        provider_id="TestProvider",
        created_at=datetime.now(UTC),
        is_synthetic=True,
    )

    _, checks = validate_draft(bad_draft, ev.factbook, ev.eligible_news)
    prohibited_check = next(c for c in checks if c.check_id == "check_prohibited_terms")
    assert prohibited_check.passed is False
