"""Testes para o módulo de ingestão e validação estrita de dados."""

from fechamento.ingestion import load_and_validate_package


def test_load_normal_package() -> None:
    res = load_and_validate_package("data/demo/normal")
    assert res.is_blocked is False
    assert len(res.blocking_errors) == 0
    assert "IBOV" in res.quotes
    assert "USD/BRL" in res.quotes
    assert len(res.positions) == 7
    assert len(res.eligible_news) == 5
    assert len(res.excluded_news) == 1  # Notícia pós-corte documentada


def test_load_corrupted_package_blocked() -> None:
    res = load_and_validate_package("data/demo/corrupted")
    assert res.is_blocked is True
    assert len(res.blocking_errors) >= 1
    # Verifica que o erro menciona soma de pesos ou cotação ausente
    combined_errors = " ".join(res.blocking_errors)
    assert "soma dos pesos" in combined_errors or "não possui cotação" in combined_errors


def test_post_cutoff_news_exclusion() -> None:
    res = load_and_validate_package("data/demo/normal")
    assert len(res.excluded_news) == 1
    item, reason = res.excluded_news[0]
    assert item.news_id == "news_post_cutoff_01"
    assert "posterior ao horário de corte" in reason
