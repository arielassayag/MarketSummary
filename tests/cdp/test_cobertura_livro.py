"""Livro da cobertura: execução offline completa, verificação, adulteração, retrodatação e
reprodutibilidade (DADOS SIMULADOS; sem rede)."""

from __future__ import annotations

import gzip
import json
import shutil
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cdp.audit import AuditLog
from cdp.cobertura.cli import executar_snapshot
from cdp.cobertura.livro import (
    LivroErro,
    datas_snapshots,
    eventos,
    ler_pacotes,
    ler_tabela,
    snapshot,
    ultimo_snapshot,
    verificar,
)
from cdp.cobertura.parametros import carregar_parametros
from cdp.data.synthetic import make_synthetic_market
from cdp.universe import universe_from_frame
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
    book = tmp_path_factory.mktemp("cob") / "book"
    params = carregar_parametros()
    r1 = executar_snapshot(book, mercado.load(D1), D1, offline=True, params=params, agora=_agora(D1),
                           codigo=CODIGO)
    r2 = executar_snapshot(book, mercado.load(D2), D2, offline=True, params=params, agora=_agora(D2),
                           codigo=CODIGO)
    return book, r1, r2


def _copia(book: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "book"
    shutil.copytree(book, dst)
    return dst


def test_offline_run_models_every_instrument(livro, mercado):
    book, r1, _ = livro
    snap = snapshot(book, D1)
    ids = sorted(mercado.md.universe.issuers.index)
    assert snap.manifest["emissores"] == ids
    assert snap.is_synthetic and "DADOS SIMULADOS" in snap.manifest["data_notice"]
    tab = snap.tabela()
    assert sorted(tab.index) == ids
    for iid in ids:
        m = snap.modelo(iid)
        assert m["schema"] == "cdp.cobertura.modelo/v1"
        assert m["aviso_dados"] == "DADOS SIMULADOS"
        # todo instrumento tem preço-alvo ou lista explícita de lacunas
        assert m["resumo"]["preco_alvo"] is not None or m["lacunas"]
        assert m["passos"], iid
        for p in m["passos"]:
            assert set(p) >= {"id", "titulo", "formula", "substituicao", "resultado", "unidade", "fontes"}
            assert p["substituicao"]
    assert len(ler_tabela(snap.pasta, "demonstrativos")) > 0
    assert set(ler_pacotes(snap.pasta)) == set(ids)
    ets = snap.etfs()
    assert {"ETF_ILF", "ETF_EWZ", "ETF_EWW"} <= set(ets.index)
    assert r1["selo"]["n_com_alvo"] >= 50


def test_open_model_steps_cover_the_chain(livro):
    book, _, _ = livro
    snap = snapshot(book, D1)
    tab = snap.tabela()
    iid = next(i for i in tab.index if isinstance(tab.loc[i, "rating"], str)
               and tab.loc[i, "rating"] in ("Compra", "Neutro", "Venda"))
    m = snap.modelo(iid)
    ids = [p["id"] for p in m["passos"]]
    for prefixo in ("insumos.preco", "ke.rf", "ke.beta", "ke.erp", "ke.crp", "ke.usd", "ke.local", "ke.g",
                    "alvo.v0", "alvo.tp12", "cenarios.mc", "cenarios.pwr", "sensibilidade", "rating.regra",
                    "qualidade"):
        assert any(i.startswith(prefixo) for i in ids), prefixo
    assert ids.index("ke.usd") < ids.index("alvo.v0") < ids.index("alvo.tp12") < ids.index("cenarios.pwr")
    assert any(i.startswith("metodo.") for i in ids)
    # números formatados em pt-BR pelo código (vírgula decimal), nunca ponto decimal cru
    tp = next(p for p in m["passos"] if p["id"] == "alvo.tp12")
    assert "," in tp["resultado_texto"] and "TP12 = " in tp["substituicao"]
    assert m["sensibilidade"]["preco_alvo"] and len(m["sensibilidade"]["preco_alvo"]) == 5


def test_verify_green_and_ledger_events(livro):
    book, _, r2 = livro
    ok, msgs = verificar(book)
    assert ok, msgs
    evs = eventos(book)
    tipos = {e["tipo"] for e in evs}
    assert "INICIACAO" in tipos and tipos & {"REITERACAO", "REVISAO", "MUDANCA_RATING"}
    assert r2["selo"]["livro_head"] == evs[-1]["event_hash"]
    trilha = AuditLog(book / "audit_log.jsonl").events()
    assert [e.event_type for e in trilha] == ["COVERAGE_SNAPSHOT", "COVERAGE_SNAPSHOT"]
    ok, _ = AuditLog(book / "audit_log.jsonl").verify_chain()
    assert ok


def test_null_preserved_for_instrument_without_target(livro):
    book, _, _ = livro
    snap = snapshot(book, D1)
    tab = snap.tabela()
    sem = tab[tab["rating"] == "Sem preço-alvo"]
    assert len(sem) >= 1
    m = snap.modelo(sem.index[0])
    assert m["resumo"]["preco_alvo"] is None and m["resumo"]["upside"] is None
    assert any(lac["insumo"] == "demonstrativos" for lac in m["lacunas"])


def test_tampering_a_model_file_is_detected(livro, tmp_path):
    book = _copia(livro[0], tmp_path)
    p = next((book / "cobertura" / D1.isoformat() / "modelos").glob("*.json"))
    obj = json.loads(p.read_text(encoding="utf-8"))
    obj["resumo"]["preco_alvo"] = 999.0
    p.write_text(json.dumps(obj), encoding="utf-8")
    ok, msgs = verificar(book, recalcular=False)
    assert not ok and any("adulterado" in m for m in msgs)


def test_tampering_a_ledger_line_is_detected(livro, tmp_path):
    book = _copia(livro[0], tmp_path)
    p = book / "cobertura" / "livro.jsonl"
    linhas = p.read_text(encoding="utf-8").splitlines()
    ev = json.loads(linhas[3])
    ev["rating"] = "Compra" if ev.get("rating") != "Compra" else "Venda"
    linhas[3] = json.dumps(ev, ensure_ascii=False, sort_keys=True)
    p.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    ok, msgs = verificar(book, recalcular=False)
    assert not ok and any("adulterado" in m for m in msgs)


def test_tampering_archived_inputs_breaks_the_file_hash(livro, tmp_path):
    # adulteração sem refazer manifesto/selo/trilha: pega pelo hash do arquivo (a versão
    # consistente, que só o recálculo detecta, está em test_cobertura_auditoria)
    book = _copia(livro[0], tmp_path)
    pasta = book / "cobertura" / D2.isoformat()
    pac = ler_pacotes(pasta)
    iid = next(i for i, x in pac.items() if x.get("bvps"))
    pac[iid]["bvps"] = pac[iid]["bvps"] * 2
    (pasta / "insumos" / "emissores.json.gz").write_bytes(
        gzip.compress(json.dumps(pac, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0))
    ok, msgs = verificar(book, recalcular=False)
    assert not ok and any("adulterado insumos/emissores.json.gz" in m for m in msgs)


def test_backdating_and_duplicate_dates_are_refused(livro, mercado, tmp_path):
    book = _copia(livro[0], tmp_path)
    legado = deepcopy(carregar_parametros())
    legado.sec("projecao").pop("resultado_corte_metodo", None)
    with pytest.raises(LivroErro):
        executar_snapshot(book, mercado.load(D1), D1, offline=True, params=legado, agora=_agora(D1), codigo=CODIGO)
    with pytest.raises(LivroErro):
        executar_snapshot(book, mercado.load(D2), D2, offline=True, params=legado, agora=_agora(D2), codigo=CODIGO)
    assert datas_snapshots(book) == [D1, D2]


def test_ultimo_snapshot_never_returns_a_later_one(livro):
    book, _, _ = livro
    assert ultimo_snapshot(book, date(2026, 10, 7)) is None
    assert ultimo_snapshot(book, date(2026, 10, 12)).as_of == D1
    s = ultimo_snapshot(book, date(2026, 12, 31))
    assert s.as_of == D2 and s.manifest_sha256


def test_same_inputs_same_bytes(mercado, tmp_path):
    params = carregar_parametros()
    a, b = tmp_path / "a", tmp_path / "b"
    for book in (a, b):
        executar_snapshot(book, mercado.load(D1), D1, offline=True, params=params, agora=_agora(D1),
                          codigo=CODIGO, audit=False)
    pa, pb = a / "cobertura" / D1.isoformat(), b / "cobertura" / D1.isoformat()
    assert (pa / "manifest.json").read_bytes() == (pb / "manifest.json").read_bytes()
    assert (a / "cobertura" / "livro.jsonl").read_bytes() == (b / "cobertura" / "livro.jsonl").read_bytes()
    man = json.loads((pa / "manifest.json").read_text(encoding="utf-8"))
    assert set(man["ambiente"]) >= {"python", "numpy", "pandas", "scipy"}
    assert "configuracao/valuation.yaml" in man["arquivos"]


def test_partial_run_and_encerramento(livro, mercado, tmp_path):
    book = _copia(livro[0], tmp_path)
    d3 = date(2026, 10, 16)
    md = mercado.load(d3)
    # execução parcial (após resultados) num dia posterior: só os emissores pedidos
    d_parc = date(2026, 10, 17)
    md_parc = replace(md, manifest=md.manifest.model_copy(update={"as_of": d_parc}))
    alvo = sorted(md.universe.issuers.index)[:2]
    executar_snapshot(book, md_parc, d_parc, emissores=alvo, offline=True, agora=_agora(d_parc), codigo=CODIGO)
    s = snapshot(book, d_parc)
    assert s.manifest["parcial"] is True and s.manifest["emissores"] == alvo
    estado = s.estado()
    assert len(estado) == len(md.universe.issuers)
    assert set(estado.loc[alvo, "snapshot"]) == {d_parc.isoformat()}
    # emissor fora do universo ⇒ ENCERRAMENTO
    lines = md.universe.lines
    saiu = sorted(md.universe.issuers.index)[-1]
    uni2 = universe_from_frame(lines[lines["issuer_id"] != saiu].reset_index(drop=True),
                               source_sha256=md.universe.source_sha256)
    d4 = date(2026, 10, 18)
    md4 = replace(md, universe=uni2, manifest=md.manifest.model_copy(update={"as_of": d4}))
    executar_snapshot(book, md4, d4, offline=True, agora=_agora(d4), codigo=CODIGO)
    enc = [e for e in eventos(book) if e["tipo"] == "ENCERRAMENTO"]
    assert [e["issuer_id"] for e in enc] == [saiu]
    assert saiu not in snapshot(book, d4).estado().index   # encerrado sai da tabela consolidada
    ok, msgs = verificar(book)
    assert ok, msgs
