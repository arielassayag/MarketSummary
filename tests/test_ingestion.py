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
