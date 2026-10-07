"""Demo reaberta pelos leitores reais: fontes físicas, imutáveis e DADOS SIMULADOS."""

from __future__ import annotations

import shutil
import warnings
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cdp.config import load_config
from cdp.data.store import MarketStore
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file
from cdp.workflow.demo import DemoStore, run_demo
from cdp.workflow.painel import painel_data
from cdp.workflow.risco_diario import market_data, read_measures
from cdp.workflow.runtime import Runtime

LEGACY = Path(__file__).parent / "fixtures" / "fund_legado.yaml"
NOW = datetime(2024, 3, 5, 22, 30, tzinfo=UTC)


def _hashes(root):
    return {str(p.relative_to(root)): sha256_file(p) for p in root.rglob("*") if p.is_file()}


def _runtime(root):
    return Runtime(load_config(LEGACY), root / "book", root / "market", root / "reports")


@pytest.fixture(scope="module")
def archived_demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo_arquivada")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = run_demo(root, days=2, cfg=load_config(LEGACY))
    assert result["integridade"], result["verificacao"]
    return root


def test_prefixes_use_canonical_bytes_and_keep_past_vintage(tmp_path):
    md = make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=date(2024, 3, 5))
    cfg = load_config(LEGACY)
    writer = DemoStore(md, root=tmp_path / "market", cfg=cfg)
    canonical = MarketStore(tmp_path / "market", cfg=cfg)
    first = writer.load(date(2024, 3, 4))
    proof = market_data(first)
    assert first.as_of == date(2024, 3, 4)
    assert first.close.index.max().date() == first.as_of
    assert proof["manifest"]["files"]
    assert proof == market_data(canonical.load(date(2024, 3, 4)))
    assert first.manifest.is_synthetic and "DADOS SIMULADOS" in first.manifest.data_notice
    initial_hashes = _hashes(tmp_path / "market" / "base" / "2024-03-04")
    writer.load(date(2024, 3, 5))
    assert proof == market_data(writer.load(date(2024, 3, 4)))
    assert proof == market_data(canonical.load(date(2024, 3, 4)))
    assert initial_hashes == _hashes(tmp_path / "market" / "base" / "2024-03-04")
    # A mesma semente e corte produzem o mesmo arquivo em outra raiz, sem caminhos locais.
    replica = DemoStore(md, root=tmp_path / "replica", cfg=cfg)
    assert proof == market_data(replica.load(date(2024, 3, 4)))
    # O loader que gravou o prefixo também recusa sua remoção; nunca o reconstitui.
    source = tmp_path / "market" / proof["manifest"]["files"][1]["path"]
    source.unlink()
    with pytest.raises(ValueError):
        writer.load(date(2024, 3, 4))
    assert not source.exists()


def test_demo_reopens_without_override_and_reads_authenticated_risk(archived_demo):
    root = archived_demo
    before = _hashes(root)
    rt = _runtime(root)
    valid, problems = rt.verify_all()
    assert valid, problems
    diagnosed = read_measures(rt.track(), market_loader=rt.store.load, market_root=rt.store.root)
    assert set(diagnosed) == {date(2024, 3, 4), date(2024, 3, 5)}
    assert any(obj["weights"] for obj in diagnosed.values())  # carteira efetiva não trivial
    for d, obj in diagnosed.items():
        assert obj["sources"]["current"] == market_data(rt.store.load(d).truncate(d))
        for source in obj["sources"]["current"]["manifest"]["files"]:
            assert sha256_file(root / "market" / source["path"]) == source["sha256"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        panel = painel_data(rt, now=NOW)
    assert panel["issues"] == []
    assert panel["status"]["integrity"]["ok"] is True
    assert panel["meta"]["is_synthetic"] is True
    assert "DADOS SIMULADOS" in panel["meta"]["data_notice"]
    assert before == _hashes(root)  # painel/verificação não repararam nem escreveram o livro


@pytest.mark.parametrize("damage", ["remocao", "adulteracao"])
def test_missing_or_changed_demo_source_fails_closed(archived_demo, tmp_path, damage):
    root = tmp_path / damage
    shutil.copytree(archived_demo, root)
    rt = _runtime(root)
    record = rt.track().records()[-1]
    obj = read_measures(rt.track(), market_loader=rt.store.load, market_root=rt.store.root)[
        record.date
    ]
    source = next(f for f in obj["sources"]["current"]["manifest"]["files"]
                  if f["path"].endswith("prices.parquet"))
    path = root / "market" / source["path"]
    if damage == "remocao":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"arquivo adulterado no teste")
    book_before = _hashes(root / "book")
    valid, problems = rt.verify_all()
    assert valid is False and problems
    with pytest.raises(ValueError, match="risco diário não autenticado"):
        read_measures(rt.track(), market_loader=rt.store.load, market_root=rt.store.root)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        panel = painel_data(rt, now=NOW)
    assert any(issue["scope"] == "Risco diário base/evento"
               and "risco diário não autenticado" in issue["message"]
               for issue in panel["issues"])
    assert panel["status"]["integrity"]["ok"] is False
    assert book_before == _hashes(root / "book")


def test_demo_refuses_orphan_market_before_writing_book(tmp_path):
    (tmp_path / "market").mkdir()
    with pytest.raises(FileExistsError):
        run_demo(tmp_path, days=1)
    assert not (tmp_path / "book").exists()
