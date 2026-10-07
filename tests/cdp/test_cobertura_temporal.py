"""DADOS SIMULADOS: fluxo .8 por dois relógios, rede falsa e PDF original próprio."""
from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.alpha.signals import valuation_gap_sombra
from cdp.cobertura import cli
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import preparar_emissor
from cdp.cobertura.livro import (
    CortePosterior,
    LivroErro,
    conferir_corte,
    snapshot,
    ultimo_snapshot,
    verificar,
)
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.resultado import visao
from cdp.cobertura.temporal import construir, validar
from cdp.config import load_config
from cdp.data import publico, publico_arquivo
from cdp.data import publico_resultados as R
from cdp.data.synthetic import make_synthetic_market
from cdp.research.factbook import com_fatos_valuation
from cdp.workflow.agenda import coverage_status
from cdp.workflow.demo import DemoStore
from cdp.workflow.runtime import Runtime

BASE, DIA = date(2026, 10, 8), date(2026, 10, 9)
INICIO = datetime(2026, 10, 9, 14, 7, tzinfo=UTC)
FIXTURE = Path(__file__).parents[1] / "fixtures/cdp/resultado_ri"


def _hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    md = DemoStore(make_synthetic_market(seed=7, as_of=DIA)).load(BASE)
    # Força o adaptador público, mantendo todos os valores/páginas explicitamente simulados.
    md = replace(md, manifest=md.manifest.model_copy(update={"is_synthetic": False}))
    iid = next(i for i in md.universe.issuers.index
               if md.universe.issuers.loc[i, "country"] == "MX"
               and md.universe.issuers.loc[i, "gics_sector"] != "Financials")
    cfgdir = tmp_path / "configuracao"
    shutil.copytree(Path("configs/cdp"), cfgdir)
    estrutura = json.loads((FIXTURE / "catalogo_sintetico.json").read_text())
    for doc in estrutura["documentos"]:
        doc["issuer_id"] = iid
    for evento in estrutura["eventos"]:
        evento["issuer_id"] = iid
        evento["identidade"]["entidade"] = iid
    (cfgdir / "resultado_evidencias.json").write_text(R.texto_json(estrutura))
    params = carregar_parametros(cfgdir / "valuation.yaml")
    assert params.versao == "2026-10.8"
    monkeypatch.setattr(R, "CATALOGO", cfgdir / "resultado_evidencias.json")
    monkeypatch.setattr(cli, "config_paths", lambda: {
        "valuation.yaml": cfgdir / "valuation.yaml",
        "resultado_evidencias.json": cfgdir / "resultado_evidencias.json",
        **{f"cobertura/{n}": cfgdir / "cobertura" / n
           for n in ("arquetipos.csv", "betas_setor.csv", "unidades.csv", "sotp.yaml", "etfs.yaml")}})
    velho = pd.DataFrame([{
        "issuer_id": iid, "demonstrativo": "DRE", "freq": "A", "period_end": "2025-12-31",
        "period_start": "2025-01-01", "item": "ebit", "value": 210000000., "currency": "MXN",
        "escala": 1, "consolidado": True, "fonte": "SIMULADO",
        "url": "https://example.invalid/DADOS_SIMULADOS/baseline", "documento": "DADOS SIMULADOS",
        "data_publicacao": "2026-03-01", "data_coleta": "2026-03-02T12:00:00+00:00",
        "sha256": "a" * 64, "pit_estimado": False, "nota": "DADOS SIMULADOS: baseline conhecido"}])
    monkeypatch.setattr(publico, "demonstrativos", lambda *a, **k: velho.copy())
    for nome in ("consenso_publico", "dividendos", "eventos_corporativos", "taxas_publicas", "free_float", "composicao_etf"):
        monkeypatch.setattr(publico, nome, lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(publico, "capital_fre", lambda *a, **k: pd.DataFrame(), raising=False)
    original = publico_arquivo.Arquivo
    at = {"agora": INICIO, "rede": 0}
    monkeypatch.setattr(publico_arquivo, "Arquivo", lambda root, offline=False: original(
        root, offline=offline, agora=lambda: at["agora"]))
    bs = {(d["url"]): (FIXTURE / n).read_bytes() for d, n in zip(
        estrutura["documentos"], ("anual_simulado.pdf", "semestre_simulado.pdf"), strict=True)}

    def baixar(url, **kwargs):
        at["rede"] += 1
        at["agora"] += timedelta(seconds=30)
        return SimpleNamespace(content=bs[url], raise_for_status=lambda: None)
    import requests
    monkeypatch.setattr(requests, "get", baixar)
    def clock():
        at["agora"] += timedelta(seconds=10)
        return at["agora"]
    return SimpleNamespace(md=md, iid=iid, params=params, at=at, clock=clock,
                           root=tmp_path / "arquivo", book=tmp_path / "book", cfgdir=cfgdir)


def _run(a, *, clock=True):
    return cli.executar_snapshot(a.book, a.md, BASE, offline=False, raiz=a.root, params=a.params,
                                 agora=INICIO, relogio=a.clock if clock else None, codigo={"git": None})


def test_primeira_coleta_cache_vazio_final_corte_e_reserva_idempotente(ambiente):
    a = ambiente
    r = _run(a)
    assert a.at["rede"] == 2 and r["selo"]["as_of"] == DIA.isoformat()
    snap = snapshot(a.book, DIA)
    corte = snap.manifest["corte_temporal"]
    assert corte["base_preco"] == BASE.isoformat() and corte["data_modelo"] == DIA.isoformat()
    assert datetime.fromisoformat(corte["coleta_inicio"]) == INICIO
    assert INICIO < datetime.fromisoformat(corte["coleta_fim"]) <= datetime.fromisoformat(corte["conhecimento_ate"])
    modelo = snap.modelo(a.iid)
    assert modelo["corte_temporal"] == corte
    assert modelo["resumo"]["data_preco"] == BASE.isoformat()
    assert modelo["diagnosticos"]["visao_resultado"]["diagnostico"]["corrente"]["status"] == "apos_ajustes_evidenciados"
    before = _hashes(a.book)
    a.at["agora"] += timedelta(hours=1)
    reserva = cli.executar_snapshot(a.book, a.md, BASE, params=a.params, raiz=a.root,
                                   agora=a.at["agora"], relogio=a.clock, codigo={"git": None})
    assert reserva["ja_concluido"] and reserva["n_eventos"] == 0 and a.at["rede"] == 2
    assert _hashes(a.book) == before
    ok, msgs = verificar(a.book, versao_atual="2026-10.8")
    assert ok, msgs


def test_reserva_com_outro_escopo_nao_declara_conclusao_nem_reescreve_retrato(ambiente):
    a = ambiente
    cli.executar_snapshot(a.book, a.md, BASE, emissores=[a.iid], offline=False,
                           raiz=a.root, params=a.params, agora=INICIO,
                           relogio=a.clock, codigo={"git": None})
    antes = _hashes(a.book)
    with pytest.raises(LivroErro, match="outro escopo"):
        cli.executar_snapshot(a.book, a.md, BASE, params=a.params, raiz=a.root,
                               agora=a.at["agora"], relogio=a.clock, codigo={"git": None})
    assert _hashes(a.book) == antes and a.at["rede"] == 2


def test_corte_fixo_passado_nao_conhece_download_posterior_nem_substitui_baseline(ambiente):
    a = ambiente
    dados = coletar(a.md, BASE, [a.iid], list(a.md.universe.lines_for(a.iid).index), [],
                    raiz=a.root, params=a.params, conhecimento_ate=INICIO)
    assert a.at["rede"] == 2
    cat = json.loads(dados.resultado_evidencias.iloc[0]["catalogo_json"])
    assert not cat["documentos"] and not cat["fatos"] and not cat["eventos"]
    assert len(dados.demonstrativos) == 1 and dados.demonstrativos.iloc[0]["value"] == 210000000.
    pac = preparar_emissor(a.md, dados, a.params, a.iid, BASE)
    assert pac["as_of"] == DIA.isoformat() and pac["data_preco"] == BASE.isoformat()
    assert visao(pac, a.params)["t.ebit"] == 210000000.


def test_snapshot_depois_do_corte_no_mesmo_dia_nao_alimenta_sombra_ou_factbook(ambiente):
    a = ambiente
    _run(a)
    snap = snapshot(a.book, DIA)
    corte = datetime.fromisoformat(snap.manifest["corte_temporal"]["conhecimento_ate"])
    assert ultimo_snapshot(a.book, DIA, conhecimento_ate=corte) is None
    with pytest.raises(CortePosterior, match="Conclusão"):
        conferir_corte(snap, corte)
    with pytest.raises(CortePosterior):
        valuation_gap_sombra(snap, [a.iid], conhecimento_ate=corte)
    cfg = load_config()
    rt = Runtime(cfg, a.book, a.root, a.book / "reports", clock=lambda: a.at["agora"])
    ctx = rt._context(a.md, DIA, conhecimento_ate=a.at["agora"])
    # Nenhuma coluna/sinal ativo nem peso novo: sombra é atributo separado.
    assert "valuation_gap" not in ctx.alpha.signal_z.columns
    with pytest.raises(CortePosterior):
        rt._factbook(ctx, [a.iid], conhecimento_ate=corte)
    base = rt._factbook(ctx, [a.iid], permitir_cobertura=False)
    with pytest.raises(CortePosterior):
        com_fatos_valuation(base, snap, [a.iid], conhecimento_ate=corte)


def test_manifesto_temporal_precisa_corresponder_a_tabela_selada(ambiente):
    a = ambiente
    _run(a)
    snap = snapshot(a.book, DIA)
    m = deepcopy(snap.manifest)
    m["corte_temporal"]["coleta_inicio"] = (INICIO - timedelta(seconds=1)).isoformat()
    # Objeto forjado em memória, mantendo hashes dos bytes: rejeição sem regravar bruto/livro.
    falso = replace(snap, manifest=m)
    with pytest.raises(LivroErro, match="tabela temporal selada"):
        conferir_corte(falso, a.at["agora"])


def test_weekly_prepare_seleciona_modelo_atual_com_preco_anterior_e_reconstroi_cutoff(ambiente):
    a = ambiente
    _run(a)
    cfg = load_config()
    rt = Runtime(cfg, a.book, a.root, a.book / "reports", clock=lambda: a.at["agora"],
                 store_override=DemoStore(a.md))
    rt.weekly_prepare(DIA, mind="demo", live=False)
    md, info, ctx, fb, _ = rt._week_state(DIA)
    assert md.as_of == BASE
    assert info["cobertura"]["as_of"] == DIA.isoformat()
    assert info["cobertura"]["manifest_sha256"] == snapshot(a.book, DIA).manifest_sha256
    assert ctx.cobertura_snapshot.as_of == DIA
    assert f"val.{a.iid}.rating_codigo" in fb.facts
    assert "valuation_gap" not in ctx.alpha.weights_used
    inicial = fb.model_dump_json()
    a.at["agora"] += timedelta(days=1)
    _, info2, _, fb2, _ = rt._week_state(DIA)
    assert info2 == info and fb2.model_dump_json() == inicial


def test_contrato_rejeita_datas_escala_temporal_e_tamper_do_pacote(ambiente):
    a = ambiente
    with pytest.raises(ValueError, match="posterior"):
        construir(DIA, INICIO - timedelta(days=1))
    c = construir(BASE, INICIO)
    c["data_modelo"] = BASE.isoformat()
    with pytest.raises(ValueError, match="incompatíveis"):
        validar(c)
    dados = coletar(a.md, BASE, [a.iid], list(a.md.universe.lines_for(a.iid).index), [],
                    raiz=a.root, params=a.params, conhecimento_ate=INICIO)
    p = preparar_emissor(a.md, dados, a.params, a.iid, BASE)
    q = visao(p, a.params)
    adulterado = deepcopy(q)
    adulterado["corte_temporal"]["conhecimento_ate"] = (INICIO + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="adulterada"):
        visao(adulterado, a.params)


def test_api_ativa_sem_clock_recusa_antes_de_qualquer_rede_ou_gravacao(ambiente):
    a = ambiente
    with pytest.raises(Exception, match="relógio explícito"):
        cli.executar_snapshot(a.book, a.md, BASE, params=a.params, raiz=a.root)
    assert a.at["rede"] == 0 and not a.book.exists()


def test_agenda_reserva_sai_de_cobertura_apos_modelo_concluido_sem_retrodatar(ambiente):
    a = ambiente
    cfg = load_config()
    rt = Runtime(cfg, a.book, a.root, a.book / "reports", clock=lambda: a.at["agora"],
                 store_override=DemoStore(a.md))
    antes = coverage_status(rt, INICIO, fonte_eventos=lambda *a, **k: pd.DataFrame(), eventos_macro={})
    assert antes["atualizar_antes_da_decisao"] and not antes["modelos_em_dia_para_a_decisao"]
    _run(a)
    depois = coverage_status(rt, a.at["agora"], fonte_eventos=lambda *a, **k: pd.DataFrame(), eventos_macro={})
    assert not depois["atualizar_antes_da_decisao"] and depois["modelos_em_dia_para_a_decisao"]
    assert depois["ultima_base_preco_completa"] == BASE
    # Mesmo livro, clock anterior ao fim: ainda não há modelo disponível à rotina.
    futuro = coverage_status(rt, INICIO, fonte_eventos=lambda *a, **k: pd.DataFrame(), eventos_macro={})
    assert futuro["atualizar_antes_da_decisao"] and not futuro["modelos_em_dia_para_a_decisao"]


def test_reconstrucao_de_prepare_legado_nao_anexa_cobertura_existente(ambiente, monkeypatch):
    a = ambiente
    _run(a)
    rt = Runtime(load_config(), a.book, a.root, a.book / "reports", clock=lambda: a.at["agora"],
                 store_override=DemoStore(a.md))
    # Reproduz o caminho anterior: nenhuma política/vínculo de cobertura no prepare.
    with monkeypatch.context() as m:
        m.setattr(Runtime, "_snapshot_cobertura", lambda *args, **kwargs: (None, None))
        rt.weekly_prepare(DIA, mind="demo", live=False)
        _, info, _, original, _ = rt._week_state(DIA)
    assert "cobertura_metodo" not in info and "cobertura" not in info
    before = _hashes(a.book)
    _, _, ctx, refeito, _ = rt._week_state(DIA)
    assert original.model_dump_json() == refeito.model_dump_json()
    assert not hasattr(ctx, "cobertura_snapshot") and not any(k.startswith("val.") for k in refeito.facts)
    assert _hashes(a.book) == before


def test_prepare_8_sem_snapshot_permanece_sem_snapshot_apos_aparecer_retrato(ambiente):
    a = ambiente
    rt = Runtime(load_config(), a.book, a.root, a.book / "reports", clock=lambda: INICIO,
                 store_override=DemoStore(a.md))
    rt.weekly_prepare(DIA, mind="demo", live=False)
    _, info, _, original, _ = rt._week_state(DIA)
    assert info["cobertura_metodo"] == "base_preco_conhecimento_explicitos" and info["cobertura"] is None
    _run(a)
    # O relógio vivo posterior não modifica nem a ausência declarada nem o corte do prepare.
    rt.clock = lambda: a.at["agora"]
    _, _, ctx, refeito, _ = rt._week_state(DIA)
    assert ctx.cobertura_snapshot is None
    assert original.model_dump_json() == refeito.model_dump_json()
