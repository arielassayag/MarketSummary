"""Testes para o provedor OpenRouter e pacote de dados reais."""

from unittest.mock import patch

import pytest

from fechamento.evidence import organize_evidence
from fechamento.ingestion import load_and_validate_package
from fechamento.metrics import compute_all_metrics
from fechamento.providers import NarrativeRequest, OpenRouterProvider
from fechamento.validation import validate_draft


def test_real_data_package_ingestion() -> None:
    pkg = load_and_validate_package("data/real/2026-02-11")
    assert pkg.is_blocked is False
    assert len(pkg.quotes) == 8
    assert len(pkg.positions) == 6
    assert len(pkg.eligible_news) == 4
    assert pkg.manifest.is_synthetic is False

    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert metrics.reconciled is True
    assert metrics.reconciliation_diff_bps <= 0.05
    assert metrics.ibov_return_pct == pytest.approx(0.0202985, rel=1e-3)
    assert metrics.usd_brl.change_pct == pytest.approx(-0.0035945, rel=1e-3)


def test_openrouter_provider_missing_key() -> None:
    provider = OpenRouterProvider(api_key="")
    pkg = load_and_validate_package("data/real/2026-02-11")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert pkg.manifest is not None
    ev = organize_evidence(metrics, pkg.manifest, pkg.eligible_news, pkg.excluded_news)
    req = NarrativeRequest(factbook=ev.factbook, eligible_news=ev.eligible_news)

    res = provider.generate(req)
    assert res.success is False
    assert "não configurada" in (res.error_message or "")


def test_openrouter_provider_mock_response() -> None:
    provider = OpenRouterProvider(api_key="sk-mock-key", model_name="google/gemini-2.5-flash")
    pkg = load_and_validate_package("data/real/2026-02-11")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert pkg.manifest is not None
    ev = organize_evidence(metrics, pkg.manifest, pkg.eligible_news, pkg.excluded_news)
    req = NarrativeRequest(factbook=ev.factbook, eligible_news=ev.eligible_news)

    mock_json_content = """{
      "paragraphs": [
        {
          "paragraph_id": 1,
          "text": "No pregão desta sessão, o Ibovespa encerrou com variação de {{fact:ibov.return_pct}}, enquanto a carteira de referência registrou retorno de {{fact:portfolio.return_pct}}, resultando em um desempenho relativo de {{fact:portfolio.spread_vs_ibov_bps}} frente ao benchmark. No mercado de câmbio, o dólar comercial apresentou oscilação de {{fact:usd_brl.change_pct}}, cotado a R$ {{fact:usd_brl.level}} por dólar ao término dos negócios regulares. O comportamento agregado refletiu a recomposição de posições entre setores cíclicos e defensivos, com liquidez concentrada nos papéis de maior capitalização da bolsa brasileira.",
          "claim_type": "factual",
          "fact_refs": ["ibov.return_pct", "portfolio.return_pct", "portfolio.spread_vs_ibov_bps", "usd_brl.change_pct", "usd_brl.level"],
          "news_refs": []
        },
        {
          "paragraph_id": 2,
          "text": "Entre os destaques positivos da carteira, o principal impacto favorável adveio de ITUB4, que avançou {{fact:asset.ITUB4.return_pct}} e acrescentou {{fact:asset.ITUB4.contribution_bps}} à rentabilidade total do portfólio. O papel foi influenciado por desdobramentos operacionais noticiados na sessão ({{news:news_real_itub_balanco}}), embora a confirmação plena do efeito estrutural sobre as receitas dependa dos próximos resultados trimestrais. Adicionalmente, BBDC4 registrou alta de {{fact:asset.BBDC4.return_pct}}, contribuindo com {{fact:asset.BBDC4.contribution_bps}} para o resultado. O setor financeiro e as empresas de bens de capital sustentaram o viés positivo, compensando a volatilidade externa observada nas primeiras horas de negociação.",
          "claim_type": "interpretation",
          "fact_refs": ["asset.ITUB4.return_pct", "asset.ITUB4.contribution_bps", "asset.BBDC4.return_pct", "asset.BBDC4.contribution_bps"],
          "news_refs": ["news_real_itub_balanco"]
        },
        {
          "paragraph_id": 3,
          "text": "Em contrapartida, no campo dos detratores de desempenho, nenhum ativo apresentou detração expressiva no período analisado. Ressalta-se que, para os ativos sem comunicados formais ao mercado, os movimentos foram atribuídos a fluxos técnicos de liquidação, sem evidência de alterações em fundamentos corporativos.",
          "claim_type": "factual",
          "fact_refs": [],
          "news_refs": []
        }
      ]
    }"""

    with patch.object(
        provider,
        "_call_openrouter",
        return_value=(
            mock_json_content,
            {"prompt_tokens": 500, "completion_tokens": 120, "total_tokens": 620},
            0.00015,
        ),
    ):
        res = provider.generate(req)
        assert res.success is True
        assert res.draft is not None
        assert res.cost_usd == 0.00015
        assert res.token_usage["total_tokens"] == 620

        # Conferência determinística
        checked_draft, checks = validate_draft(res.draft, ev.factbook, ev.eligible_news)
        critical_checks = [c for c in checks if c.severity == "critical"]
        assert all(c.passed for c in critical_checks)
        assert "+2,03%" in checked_draft.rendered_text
