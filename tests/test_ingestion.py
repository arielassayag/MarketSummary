"""Testes para o módulo de ingestão e validação estrita de dados."""

import hashlib
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fechamento.ingestion import load_and_validate_package


def _pacote_taxas(tmp_path, *, corpo='[{"nome":"Selic","valor":13.75}]', endpoint="https://brasilapi.com.br/api/taxas/v1", atraso=False, declarada=True):
    package = tmp_path / "DADOS_SIMULADOS"
    shutil.copytree(Path("data/demo/normal"), package)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    cutoff = datetime.fromisoformat(manifest["cutoff_time"])
    contexto = {"origem": "BrasilAPI", "endpoint": endpoint, "consultado_em":
                (cutoff + timedelta(seconds=1) if atraso else cutoff).isoformat(), "corpo_json": corpo}
    path = package / "sources.json"
    path.write_text(json.dumps({"taxas_contexto": contexto}))
    if declarada:
        manifest["files"].append({"filename": "sources.json", "path": "sources.json",
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest_path.write_text(json.dumps(manifest))
    return package


def test_taxas_contexto_estruturado_preserva_ausencia_e_proveniencia(tmp_path):
    from fechamento.evidence import build_factbook
    from fechamento.metrics import compute_all_metrics

    package = _pacote_taxas(tmp_path)
    received = load_and_validate_package(package)
    assert not received.is_blocked
    assert received.taxas_contexto is not None
    assert received.taxas_contexto.contexto.taxas() == {"SELIC": 13.75}
    facts = build_factbook(compute_all_metrics(received.quotes, received.positions), received.manifest,
                          received.eligible_news, taxas_contexto=received.taxas_contexto)
    assert "macro.cdi.rate" not in facts.facts
    assert "vigência não informada" in facts.facts["macro.selic.rate"].name
    assert received.taxas_contexto.arquivo_sha256 in facts.facts["macro.selic.rate"].input_refs[0]


@pytest.mark.parametrize("corpo", ['{}', '[{"nome":"Selic","valor":true}]', '[{"nome":"Selic","valor":null}]', '[{"nome":"Selic","valor":"NaN"}]', '[{"nome":"Selic","valor":13},{"nome":"SELIC","valor":14}]'])
def test_taxas_contexto_malformado_bloqueia_sem_zero(tmp_path, corpo):
    received = load_and_validate_package(_pacote_taxas(tmp_path, corpo=corpo))
    assert received.is_blocked
    assert received.taxas_contexto is None


def test_taxas_origem_nao_brasilapi_recusada(tmp_path):
    received = load_and_validate_package(_pacote_taxas(tmp_path, endpoint="https://exemplo.com/taxas"))
    assert received.is_blocked
    assert received.taxas_contexto is None


def test_taxas_apos_corte_sao_ausentes(tmp_path):
    received = load_and_validate_package(_pacote_taxas(tmp_path, atraso=True))
    assert not received.is_blocked
    assert received.taxas_contexto is None
    assert any("consulta posterior" in a for a in received.alerts)


def test_taxas_arquivo_nao_declarado_nao_e_autenticado(tmp_path):
    received = load_and_validate_package(_pacote_taxas(tmp_path, declarada=False))
    assert not received.is_blocked
    assert received.taxas_contexto is None


def test_taxas_alteradas_invalidam_manifesto(tmp_path):
    package = _pacote_taxas(tmp_path)
    (package / "sources.json").write_text('{}')
    received = load_and_validate_package(package)
    assert received.is_blocked
    assert received.taxas_contexto is None


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


def test_noticia_observada_usa_horario_recebido_no_corte(tmp_path) -> None:
    import hashlib
    import json
    import shutil
    from datetime import datetime, timedelta
    from pathlib import Path

    package = tmp_path / "simulado"
    shutil.copytree(Path("data/demo/normal"), package)
    manifest = json.loads((package / "manifest.json").read_text())
    cutoff = datetime.fromisoformat(manifest["cutoff_time"])
    base = {"title": "DADOS SIMULADOS", "body": "Manchete", "source": "Fixture",
            "published_at": None, "is_synthetic": True}
    news = [{**base, "news_id": "antes", "observed_at": (cutoff - timedelta(hours=1)).isoformat()},
            {**base, "news_id": "depois", "observed_at": (cutoff + timedelta(hours=1)).isoformat()},
            {**base, "news_id": "sem-horario"}]
    path = package / "news.jsonl"
    path.write_text("".join(json.dumps(n) + "\n" for n in news))
    for entry in manifest["files"]:
        if entry["filename"] == "news.jsonl":
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (package / "manifest.json").write_text(json.dumps(manifest))
    received = load_and_validate_package(package)
    assert received.is_blocked is False
    assert [n.news_id for n in received.eligible_news] == ["antes"]
    assert received.eligible_news[0].published_at is None
    assert [n.news_id for n, _ in received.excluded_news] == ["depois"]
    assert "Horário retornado pela fonte" in received.excluded_news[0][1]
    assert any("sem horário" in a for a in received.alerts)
