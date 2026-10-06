"""Auditoria do livro da cobertura: eventos sem selo, snapshot apagado, trilha ausente, leitura
conferida pelo manifesto, recuperação de gravação interrompida, adulteração consistente só
detectável pelo recálculo, alvos bloqueados não citáveis e execução parcial com pares publicados.
DADOS SIMULADOS, sem rede."""

from __future__ import annotations

import gzip
import json
import shutil
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from cdp.audit import AuditLog
from cdp.cobertura.cli import executar_snapshot
from cdp.cobertura.livro import (
    LivroErro,
    _hash_evento,
    eventos,
    ler_pacotes,
    reparar_pendencias,
    snapshot,
    ultimo_snapshot,
    verificar,
)
from cdp.cobertura.parametros import carregar_parametros
from cdp.data.synthetic import make_synthetic_market
from cdp.hashing import sha256_file, sha256_obj
from cdp.research.factbook import fatos_valuation
from cdp.workflow.demo import DemoStore

D1, D2 = date(2026, 10, 8), date(2026, 10, 16)
CODIGO = {"git": None}


def _agora(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def mercado():
    return DemoStore(make_synthetic_market(seed=7, as_of=D2))


@pytest.fixture(scope="module")
def livro(mercado, tmp_path_factory):
    book = tmp_path_factory.mktemp("aud") / "book"
    params = carregar_parametros()
    for d in (D1, D2):
        executar_snapshot(book, mercado.load(d), d, offline=True, params=params, agora=_agora(d), codigo=CODIGO)
    return book


def _copia(book: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "book"
    shutil.copytree(book, dst)
    return dst


def _reescrever_trilha(book: Path, selos: list[dict], datas: list[date]) -> None:
    p = book / "audit_log.jsonl"
    p.unlink()
    log = AuditLog(p)
    for selo, d in zip(selos, datas, strict=True):
        log.append("COVERAGE_SNAPSHOT", "CDP", selo, summary=f"Cobertura {d.isoformat()}", ts=_agora(d))


def test_forged_event_after_last_seal_fails_verify_and_blocks_next_run(livro, mercado, tmp_path):
    book = _copia(livro, tmp_path)
    evs = eventos(book)
    falso = {**evs[-1], "seq": len(evs), "prev_hash": evs[-1]["event_hash"], "rating": "Compra",
             "alvo": {"base": 999.0}, "as_of": D2.isoformat()}
    falso["event_hash"] = _hash_evento(falso)
    with open(book / "cobertura" / "livro.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(falso, ensure_ascii=False, sort_keys=True) + "\n")
    ok, msgs = verificar(book, recalcular=False)
    assert not ok and any("além do último selo" in m for m in msgs)
    with pytest.raises(LivroErro):
        ultimo_snapshot(book, D2)
    d3 = date(2026, 10, 23)
    md = mercado.load(D2)
    md3 = replace(md, manifest=md.manifest.model_copy(update={"as_of": d3}))
    with pytest.raises(LivroErro, match="selo"):
        executar_snapshot(book, md3, d3, offline=True, agora=_agora(d3), codigo=CODIGO)


def test_deleted_snapshot_and_truncated_ledger_are_detected(livro, tmp_path):
    book = _copia(livro, tmp_path)
    selo1 = json.loads((book / "cobertura" / D1.isoformat() / "selo.json").read_text(encoding="utf-8"))
    shutil.rmtree(book / "cobertura" / D2.isoformat())
    linhas = (book / "cobertura" / "livro.jsonl").read_text(encoding="utf-8").splitlines()[: selo1["n_eventos"]]
    (book / "cobertura" / "livro.jsonl").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    ok, msgs = verificar(book, recalcular=False)
    assert not ok and any("sem snapshot correspondente" in m for m in msgs)


@pytest.mark.parametrize("modo", ["ausente", "vazia"])
def test_missing_or_empty_fund_trail_fails(livro, tmp_path, modo):
    book = _copia(livro, tmp_path)
    p = book / "audit_log.jsonl"
    if modo == "ausente":
        p.unlink()
    else:
        p.write_text("", encoding="utf-8")
    ok, msgs = verificar(book, recalcular=False)
    assert not ok and any("trilha do fundo sem eventos" in m for m in msgs)


def test_readers_check_files_against_the_manifest(livro, tmp_path):
    book = _copia(livro, tmp_path)
    p = book / "cobertura" / D2.isoformat() / "modelos.csv"
    t = pd.read_csv(p)
    t["rating"] = "Compra"
    t.to_csv(p, index=False)
    s = snapshot(book, D2)
    with pytest.raises(LivroErro, match="não confere com o manifesto"):
        s.tabela()
    with pytest.raises(LivroErro):
        s.estado()


def test_consistent_rewrite_of_inputs_is_caught_only_by_recompute(livro, tmp_path):
    book = _copia(livro, tmp_path)
    pasta = book / "cobertura" / D2.isoformat()
    pac = ler_pacotes(pasta)
    iid = next(i for i, x in pac.items() if x.get("bvps") and x.get("arquetipo") in ("banco", "imobiliario"))
    pac[iid]["bvps"] = pac[iid]["bvps"] * 2
    (pasta / "insumos" / "emissores.json.gz").unlink()
    (pasta / "insumos" / "emissores.json.gz").write_bytes(
        gzip.compress((json.dumps(pac, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8"),
                      compresslevel=9, mtime=0))
    man = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
    man["arquivos"]["insumos/emissores.json.gz"] = sha256_file(pasta / "insumos" / "emissores.json.gz")
    (pasta / "manifest.json").write_bytes(
        (json.dumps(man, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    selo = json.loads((pasta / "selo.json").read_text(encoding="utf-8"))
    selo["manifest_sha256"] = sha256_file(pasta / "manifest.json")
    (pasta / "selo.json").write_bytes((json.dumps(selo, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
                                      .encode("utf-8"))
    selo1 = json.loads((book / "cobertura" / D1.isoformat() / "selo.json").read_text(encoding="utf-8"))
    _reescrever_trilha(book, [selo1, selo], [D1, D2])
    ok, msgs = verificar(book, recalcular=False)
    assert ok, msgs  # cadeia, selos, trilha e hashes consistentes
    ok, msgs = verificar(book)
    assert not ok and any(iid in m for m in msgs)


def _reescrever_modelo(book: Path, d: date, iid: str, mudar) -> None:
    """Reescreve de forma consistente o modelo publicado e a linha do modelos.csv de ``iid`` (hashes do
    manifesto, selo e trilha refeitos): só o recálculo pode detectar."""
    pasta = book / "cobertura" / d.isoformat()
    rel = f"modelos/{iid}.json"
    mod = json.loads((pasta / rel).read_text(encoding="utf-8"))
    mudar(mod["resumo"])
    (pasta / rel).write_bytes(json.dumps(mod, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    tab = pd.read_csv(pasta / "modelos.csv")
    linha = tab["issuer_id"] == iid
    for c in ("alpha_rel_estilo", "pwr_com_piso", "p_patrimonio_zero", "preco_alvo_ke_estatico", "ke_estatico"):
        if c in tab.columns:
            tab.loc[linha, c] = mod["resumo"][c]
    tab.to_csv(pasta / "modelos.csv", index=False)
    man = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
    for r in (rel, "modelos.csv"):
        man["arquivos"][r] = sha256_file(pasta / r)
    (pasta / "manifest.json").write_bytes(
        (json.dumps(man, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    selo = json.loads((pasta / "selo.json").read_text(encoding="utf-8"))
    selo["manifest_sha256"] = sha256_file(pasta / "manifest.json")
    (pasta / "selo.json").write_bytes((json.dumps(selo, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
                                      .encode("utf-8"))
    selo1 = json.loads((book / "cobertura" / D1.isoformat() / "selo.json").read_text(encoding="utf-8"))
    _reescrever_trilha(book, [selo1, selo], [D1, D2])


def test_consistent_rewrite_of_published_style_fields_is_caught_by_recompute(livro, tmp_path):
    book = _copia(livro, tmp_path)
    pasta = book / "cobertura" / D2.isoformat()
    tab = pd.read_csv(pasta / "modelos.csv")
    iid = str(tab.loc[tab["alpha_rel_estilo"].notna()].iloc[0]["issuer_id"])

    def mudar(r: dict) -> None:
        r["alpha_rel_estilo"] = (r["alpha_rel_estilo"] or 0) + 0.18
        r["pwr_com_piso"] = 9.99
        r["p_patrimonio_zero"] = 0.0
        r["preco_alvo_ke_estatico"] = 1e6
        r["ke_estatico"] = 0.01

    _reescrever_modelo(book, D2, iid, mudar)
    ok, msgs = verificar(book, recalcular=False)
    assert ok, msgs
    ok, msgs = verificar(book)
    assert not ok
    texto = " ".join(msgs)
    for c in ("alpha_rel_estilo", "pwr_com_piso", "preco_alvo_ke_estatico", "ke_estatico"):
        assert f"{iid} {c}" in texto or f"{iid} modelos.csv {c}" in texto, c


def test_verify_is_methodology_version_aware(livro):
    # snapshots gravados com outra versão da metodologia: hashes, livro, selos, trilha e placar conferidos e o
    # recálculo indicado como nota (exige o código daquela versão), sem falhar
    ok, msgs = verificar(livro, versao_atual="2026-09.9")
    assert ok, msgs
    assert any("recálculo exige o código da versão" in m for m in msgs)
    ok, msgs = verificar(livro)
    assert ok and not any("recálculo exige" in m for m in msgs)


def test_interrupted_write_is_completed_from_the_sealed_snapshot(livro, tmp_path):
    book = _copia(livro, tmp_path)
    selo1 = json.loads((book / "cobertura" / D1.isoformat() / "selo.json").read_text(encoding="utf-8"))
    selo2 = json.loads((book / "cobertura" / D2.isoformat() / "selo.json").read_text(encoding="utf-8"))
    linhas = (book / "cobertura" / "livro.jsonl").read_text(encoding="utf-8").splitlines()
    (book / "cobertura" / "livro.jsonl").write_text("\n".join(linhas[: selo1["n_eventos"]]) + "\n", encoding="utf-8")
    _reescrever_trilha(book, [selo1], [D1])   # interrupção depois de renomear a pasta de D2
    ok, _ = verificar(book, recalcular=False)
    assert not ok
    feitos = reparar_pendencias(book, agora=_agora(D2))
    assert len(feitos) == 2
    assert len(eventos(book)) == selo2["n_eventos"]
    ok, msgs = verificar(book, recalcular=False)
    assert ok, msgs
    assert reparar_pendencias(book) == []   # idempotente


def test_blocked_targets_are_not_citable(livro):
    s = snapshot(livro, D2)
    bruto, tab = s.tabela(mascarar=False), s.tabela()
    bloq = tab.index[tab["rating"] == "Em revisão"]
    assert len(bloq)
    assert tab.loc[bloq, "preco_alvo"].isna().all() and bruto.loc[bloq, "preco_alvo"].notna().all()
    assert not tab.loc[bloq, "alvo_citavel"].any()
    iid = bloq[0]
    fatos = fatos_valuation(s.modelo(iid), [e for e in eventos(livro) if e["issuer_id"] == iid], D2)
    for suf in ("preco_alvo", "upside", "alpha_rel", "etr", "alvo_otimista"):
        f = fatos[f"val.{iid}.{suf}"]
        assert f.value is None and f.formatted == "Em revisão"
    citavel = tab.index[tab["rating"].isin(["Compra", "Neutro", "Venda"])][0]
    f = fatos_valuation(s.modelo(citavel))[f"val.{citavel}.preco_alvo"]
    assert f.value is not None


def test_fact_point_in_time_follows_the_package(livro):
    s = snapshot(livro, D2)
    for iid in list(s.tabela().index)[:10]:
        m = s.modelo(iid)
        f = fatos_valuation(m)[f"val.{iid}.ke"]
        assert f.point_in_time == bool(m["resumo"]["pit_ok"])


def test_partial_run_uses_published_peer_alphas(livro, mercado, tmp_path):
    book = _copia(livro, tmp_path)
    d = date(2026, 10, 19)
    md = mercado.load(D2)
    md_p = replace(md, manifest=md.manifest.model_copy(update={"as_of": d}))
    tab2 = snapshot(book, D2).tabela(mascarar=False)
    alvo = [i for i in tab2.index if tab2.loc[i, "rating"] in ("Compra", "Neutro", "Venda")][:2]
    executar_snapshot(book, md_p, d, emissores=alvo, offline=True, agora=_agora(d), codigo=CODIGO)
    s = snapshot(book, d)
    ev2 = {e["issuer_id"]: e for e in eventos(book) if e["as_of"] == D2.isoformat()}
    m = s.modelo(alvo[0])
    for j, a in m["pares"]["alphas"]:
        if j not in alvo:
            esperado = ev2[j]["alpha"] if ev2[j]["rating"] in ("Compra", "Neutro", "Venda") else None
            assert a == pytest.approx(esperado) if esperado is not None else a is None
    ok, msgs = verificar(book)
    assert ok, msgs


def test_snapshot_events_file_matches_ledger(livro):
    pasta = livro / "cobertura" / D2.isoformat()
    proprios = [json.loads(x) for x in (pasta / "eventos.jsonl").read_text(encoding="utf-8").splitlines()]
    man = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
    n0 = man["livro_anterior"]["n_eventos"]
    assert proprios == eventos(livro)[n0:n0 + len(proprios)]
    assert sha256_obj(json.loads((pasta / "selo.json").read_text(encoding="utf-8"))) in {
        e.payload_hash for e in AuditLog(livro / "audit_log.jsonl").events()}


def test_etf_facts_masked_under_review():
    from cdp.research.factbook import fatos_etf

    e = {"ticker": "ILF", "iid": "ETF_ILF", "as_of": "2026-10-16", "moeda": "USD", "tem_alvo": True,
         "preco_alvo": 30.0, "retorno_esperado": 0.9, "r_bu": 0.9, "r_td": 0.1, "cobertura": 0.8,
         "visao_ilf": "Em revisão"}
    f = fatos_etf(e)
    assert f["etf.ILF.preco_alvo"].value is None and f["etf.ILF.preco_alvo"].formatted == "Em revisão"
    assert f["etf.ILF.retorno_esperado"].value is None
    ok = fatos_etf({**e, "visao_ilf": "Referência", "retorno_esperado": 0.08})
    assert ok["etf.ILF.preco_alvo"].value == 30.0


def test_statements_are_stored_once_per_content(livro):
    from cdp.cobertura.livro import ler_tabela

    blobs = list((livro / "cobertura" / "publico" / "demonstrativos").rglob("*.csv.gz"))
    m1 = json.loads((livro / "cobertura" / D1.isoformat() / "manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((livro / "cobertura" / D2.isoformat() / "manifest.json").read_text(encoding="utf-8"))
    p1 = {k for k in m1["arquivos"] if k.startswith("../publico/demonstrativos/")}
    p2 = {k for k in m2["arquivos"] if k.startswith("../publico/demonstrativos/")}
    assert p1 and p2 and len(blobs) == len(p1 | p2)
    t = ler_tabela(livro / "cobertura" / D2.isoformat(), "demonstrativos")
    assert len(t) > 0 and t["issuer_id"].nunique() == len(p2)
