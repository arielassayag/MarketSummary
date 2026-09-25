"""Testes para os provedores de narrativa (DemoProvider e GeminiProvider)."""

from fechamento.evidence import organize_evidence
from fechamento.ingestion import load_and_validate_package
from fechamento.metrics import compute_all_metrics
from fechamento.providers import DemoProvider, GeminiProvider, NarrativeRequest


def test_demo_provider_deterministic() -> None:
    pkg = load_and_validate_package("data/demo/normal")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert pkg.manifest is not None
    ev = organize_evidence(metrics, pkg.manifest, pkg.eligible_news, pkg.excluded_news)

    req = NarrativeRequest(factbook=ev.factbook, eligible_news=ev.eligible_news)
    provider = DemoProvider()

    res1 = provider.generate(req)
    res2 = provider.generate(req)

    assert res1.success is True
    assert res1.draft is not None
    assert res2.draft is not None

    # Determinismo: o texto gerado por regras deve ser idêntico em chamadas sucessivas
    t1 = "\n\n".join(p.text for p in res1.draft.paragraphs)
    t2 = "\n\n".join(p.text for p in res2.draft.paragraphs)
    assert t1 == t2
    assert "{{fact:ibov.return_pct}}" in t1
    assert res1.is_deterministic is True


def test_gemini_provider_disabled_by_default() -> None:
    pkg = load_and_validate_package("data/demo/normal")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert pkg.manifest is not None
    ev = organize_evidence(metrics, pkg.manifest, pkg.eligible_news, pkg.excluded_news)

    req = NarrativeRequest(factbook=ev.factbook, eligible_news=ev.eligible_news)
    provider = GeminiProvider(api_key=None, enabled=False)

    res = provider.generate(req)
    assert res.success is False
    assert "desabilitado" in (res.error_message or "").lower()


def test_gemini_provider_missing_key() -> None:
    pkg = load_and_validate_package("data/demo/normal")
    metrics = compute_all_metrics(pkg.quotes, pkg.positions)
    assert pkg.manifest is not None
    ev = organize_evidence(metrics, pkg.manifest, pkg.eligible_news, pkg.excluded_news)

    req = NarrativeRequest(factbook=ev.factbook, eligible_news=ev.eligible_news)
    provider = GeminiProvider(api_key="", enabled=True)

    res = provider.generate(req)
    assert res.success is False
    assert "não fornecida" in (res.error_message or "").lower()
