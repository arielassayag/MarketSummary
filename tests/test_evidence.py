"""Testes para o FactBook e organização de evidências."""

from fechamento.evidence import build_factbook, organize_evidence
from fechamento.ingestion import load_and_validate_package
from fechamento.metrics import compute_all_metrics


def test_manchete_nao_produz_taxa_oficial() -> None:
    from datetime import UTC, datetime

    from fechamento.contracts import NewsItem

    pkg = load_and_validate_package("data/demo/normal")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    news = NewsItem(news_id="externa", title="Selic em 99% e CDI em 98%",
                    body="Não é dado da BrasilAPI", source="GDELT",
                    published_at=datetime(2026, 9, 18, tzinfo=UTC))
    fb = build_factbook(metrics, pkg.manifest, [news])
    assert "macro.selic.rate" not in fb.facts
    assert "macro.cdi.rate" not in fb.facts

def test_factbook_generation() -> None:
    pkg = load_and_validate_package("data/demo/normal")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert pkg.manifest is not None
    factbook = build_factbook(metrics, pkg.manifest)

    # Verificar existência dos fatos obrigatórios
    assert factbook.get_fact("ibov.return_pct") is not None
    assert factbook.get_fact("usd_brl.change_pct") is not None
    assert factbook.get_fact("portfolio.return_pct") is not None
    assert factbook.get_fact("portfolio.spread_vs_ibov_bps") is not None

    # Verificar fato de ativo
    petr_fact = factbook.get_fact("asset.PETR4.contribution_bps")
    assert petr_fact is not None
    assert "bps" in petr_fact.formatted_value

    # Verificar evidência organizada
    ev = organize_evidence(metrics, pkg.manifest, pkg.eligible_news, pkg.excluded_news)
    assert len(ev.eligible_news) == 5
    assert "PETR4" in ev.news_by_ticker
