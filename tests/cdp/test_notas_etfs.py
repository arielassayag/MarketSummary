"""Pesquisa de ETF: produto, ausência, datas, fila e publicação isolada (DADOS SIMULADOS)."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from cdp.config import load_config
from cdp.research.notas import (
    FonteNota,
    PilarTese,
    render_markdown,
    render_nota,
    template_nota,
    verify_nota,
)
from cdp.workflow import notas as N
from cdp.workflow import notas_etfs as E
from cdp.workflow.runtime import Runtime

D = date(2026, 10, 11)


class Retrato:
    as_of = date(2026, 10, 9)
    manifest_sha256 = "a" * 64
    is_synthetic = True

    def __init__(self):
        self.modelos = {"ETF_TESTE": {"iid": "ETF_TESTE", "ticker": "TESTE", "nome": "Fundo teste",
                                    "pais": "BR", "indice": "Índice teste", "as_of": "2026-10-09",
                                    "moeda": "BRL", "preco": 10.0, "preco_alvo": 11.0,
                                    "tem_alvo": True, "retorno_esperado": .12, "r_bu": .10,
                                    "r_td": .14, "cobertura": .6, "ter": .005,
                                    "visao_ilf": "Neutra", "ir": 0.0, "is_synthetic": True,
                                    "fonte_composicao": {"url": "https://www.ishares.com/"}}}

    def etfs(self):
        return pd.DataFrame(index=self.modelos)

    def etf(self, iid):
        return copy.deepcopy(self.modelos.get(iid))

    def estado(self):
        return pd.DataFrame()


def ambiente(tmp_path):
    snap = Retrato()
    md = SimpleNamespace(as_of=date(2026, 10, 9), manifest=SimpleNamespace(snapshot_id="mercado-simulado"), is_synthetic=True,
                         universe=SimpleNamespace(issuers=pd.DataFrame(
                             {"issuer_name": ["Empresa teste"], "country": ["BR"],
                              "gics_sector": ["Financials"]}, index=["BR_TESTE"])))
    rt = Runtime(load_config(), tmp_path / "book", tmp_path / "market", tmp_path / "reports",
                 clock=lambda: datetime(2026, 10, 11, 20, tzinfo=ZoneInfo("America/Sao_Paulo")),
                 store_override=SimpleNamespace(load=lambda d: md), teses_root=tmp_path / "docs/teses",
                 expected_mind="codex")
    return rt, md, snap


def test_fatos_do_produto_sem_contabilidade_de_empresa(tmp_path):
    rt, md, snap = ambiente(tmp_path)
    original = copy.deepcopy(snap.modelos)
    fb, ctx = E.entradas(rt, md, snap, "ETF_TESTE", D)
    assert ctx.setor == "ETF" and ctx.proximo_resultado is None and ctx.pares == ()
    assert all(fid.startswith("etf.TESTE.") for fid in fb.facts)
    assert all(not f.point_in_time for f in fb.facts.values())
    assert fb.facts["etf.TESTE.ter"].formatted == "0,50%"
    assert snap.modelos == original and not (tmp_path / "book").exists()
    nota = template_nota(fb, ctx, "codex")
    assert verify_nota(nota, fb, ctx) == []
    assert "DADOS SIMULADOS" in render_markdown(render_nota(nota, fb, ctx, autoria="codigo", published_at="2026-10-11T20:00:00-03:00"))


def test_alvo_bloqueado_e_taxa_ausente_nao_viram_conclusao(tmp_path):
    rt, md, snap = ambiente(tmp_path)
    snap.modelos["ETF_TESTE"].update(visao_ilf="Em revisão", ter=None)
    fb, ctx = E.entradas(rt, md, snap, "ETF_TESTE", D)
    assert fb.facts["etf.TESTE.preco_alvo"].value is None
    assert fb.facts["etf.TESTE.preco_alvo"].formatted == "Em revisão"
    assert fb.facts["etf.TESTE.ter"].value is None
    assert fb.facts["etf.TESTE.ter"].formatted != "0,0%"
    assert verify_nota(template_nota(fb, ctx), fb, ctx) == []


def test_retrato_pode_ser_posterior_ao_preco_mas_nao_a_nota(tmp_path):
    rt, md, snap = ambiente(tmp_path)
    md.as_of = date(2026, 10, 8)
    fb, ctx = E.entradas(rt, md, snap, "ETF_TESTE", D)
    assert fb.as_of == md.as_of and ctx.snapshot["as_of"] == "2026-10-09"
    snap.as_of = date(2026, 10, 12)
    with pytest.raises(ValueError, match="posteriores ao corte"):
        E.entradas(rt, md, snap, "ETF_TESTE", D)


@pytest.mark.parametrize("alteracao", ["data", "ticker", "identidade"])
def test_modelo_futuro_ou_identidade_incompativel_recusados(tmp_path, alteracao):
    rt, md, snap = ambiente(tmp_path)
    m = snap.modelos["ETF_TESTE"]
    m[{"data": "as_of", "ticker": "ticker", "identidade": "iid"}[alteracao]] = {
        "data": "2026-10-12", "ticker": "OUTRO", "identidade": "ETF_OUTRO"}[alteracao]
    with pytest.raises(ValueError):
        E.entradas(rt, md, snap, "ETF_TESTE", D)
    with pytest.raises(ValueError):
        E.entradas(rt, md, None, "ETF_TESTE", D)


def test_fila_inclui_etf_e_adota_rascunho_sem_nova_rotina(tmp_path, monkeypatch):
    rt, md, snap = ambiente(tmp_path)
    monkeypatch.setattr(N, "_snapshot", lambda rt, d: (snap, None))
    monkeypatch.setattr(N, "_liquidity", lambda md, cfg: {})
    a = N.note_agenda(rt, D)
    assert a["limite_por_execucao"] == 12
    assert {r["issuer_id"] for r in a["fila"]} == {"BR_TESTE", "ETF_TESTE"}
    p = N.handoff_root(rt) / "ETF_TESTE" / f"{D}.json"
    p.parent.mkdir(parents=True)
    fb, ctx = N.build_note_inputs(rt, "ETF_TESTE", D)
    p.write_text(template_nota(fb, ctx, "codex").model_dump_json())
    a = N.note_agenda(rt, D)
    assert a["fila"][0]["grupo"] == "rascunho" and a["fila"][0]["issuer_id"] == "ETF_TESTE"
    assert not a["rascunhos_obsoletos"]
    prep = N.prepare_note(rt, "ETF_TESTE", D)
    assert prep["rascunho_adotado"] is True
    assert N.validate_note(rt, "ETF_TESTE", D)["ok"] is True
    pub = N.publish_note(rt, "ETF_TESTE", D)
    assert pub["autoria"] == "mente" and N.verify_notes(rt) == []
    d = json.loads((N.nota_dir(rt.book_root, "ETF_TESTE", D) / N.PUBLISHED_JSON).read_text())
    assert d["rendered"]["ficha"] and "DADOS SIMULADOS" in d["rendered"]["aviso"]


def test_complementos_do_etf_guardam_fatos_e_so_entram_em_produtos(tmp_path):
    rt, md, snap = ambiente(tmp_path)
    fb, ctx = E.entradas(rt, md, snap, "ETF_TESTE", D)
    nota = template_nota(fb, ctx, "codex")
    nota = nota.model_copy(update={"custos_liquidez_etf": PilarTese(
        titulo="Custo declarado", texto="Taxa {{fact:etf.TESTE.ter}}.", evidencias=["etf.TESTE.ter"])})
    assert verify_nota(nota, fb, ctx) == []
    assert render_nota(nota, fb, ctx, autoria="mente", published_at="2026-10-11T20:00:00-03:00")["custos_liquidez_etf"][0]["texto"] == "Taxa 0,50%."
    issues = verify_nota(nota, fb, replace(ctx, setor="Financials"))
    assert "custos_liquidez_etf: complemento exclusivo de ETF" in issues
    nota = nota.model_copy(update={"custos_liquidez_etf": PilarTese(
        titulo="Custo declarado", texto="Taxa 5%.", evidencias=["F99"])})
    issues = verify_nota(nota, fb, ctx)
    assert any("F99" in s for s in issues) and any("custos_liquidez_etf" in s for s in issues)


def test_publicacao_desconhecida_nao_vira_data_da_consulta(tmp_path):
    rt, md, snap = ambiente(tmp_path)
    fb, ctx = E.entradas(rt, md, snap, "ETF_TESTE", D)
    nota = template_nota(fb, ctx, "codex")
    f = FonteNota(id="F1", tipo="relacoes_com_investidores", instituicao="Administrador",
                  titulo="Página do produto", url="https://www.ishares.com/", publicado_em=None,
                  consultado_em=D)
    nota = nota.model_copy(update={"fontes": [f]})
    assert verify_nota(nota, fb, ctx) == []
    r = render_nota(nota, fb, ctx, autoria="mente", published_at="2026-10-11T20:00:00-03:00")
    assert r["fontes"][0]["publicado_em"] is None and r["fontes"][0]["consultado_em"] == str(D)
    assert "publicação não informada; consulta 2026-10-11" in render_markdown(r)
    nota = nota.model_copy(update={"fontes": [f.model_copy(update={"consultado_em": date(2026, 10, 12)})]})
    assert any("look-ahead" in i for i in verify_nota(nota, fb, ctx))
    nota = nota.model_copy(update={"fontes": [f.model_copy(update={"consultado_em": None})]})
    assert any("exige data real" in i for i in verify_nota(nota, fb, ctx))


def test_etf_recusa_guidance_empresarial_e_pagina_mostra_o_produto(tmp_path):
    from cdp.workflow.teses_ativos import _nota_secoes

    rt, md, snap = ambiente(tmp_path)
    fb, ctx = E.entradas(rt, md, snap, "ETF_TESTE", D)
    nota = template_nota(fb, ctx, "codex")
    assert any("guidance empresarial" in p for p in verify_nota(
        nota.model_copy(update={"guidance": "elevado"}), fb, ctx))
    r = render_nota(nota, fb, ctx, autoria="mente", published_at="2026-10-11T20:00:00-03:00")
    s = _nota_secoes(r, etf=True)
    assert s[0][1] == "Produto e exposição econômica"
    resultado = next(b for k, _, b in s if k == "resultado")
    assert "fundo não analisada" in resultado and "Guidance:" not in resultado
