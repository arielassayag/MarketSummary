"""DADOS SIMULADOS: configuração/CLI, dois relógios, nenhum writer financeiro.

Mocks substituem somente fronteiras normais de coleta/gravação desta prova de
orquestração; não trocam origem de módulos ou o código dos seletores/parser.
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.cobertura import cli
from cdp.cobertura.fontes import DadosPublicos
from cdp.cobertura.parametros import carregar_parametros
from cdp.data.synthetic import make_synthetic_market
from cdp.workflow.demo import DemoStore
from cdp.workflow.runtime import Runtime

BASE = date(2026, 10, 7)
INICIO = datetime(2026, 10, 8, 19, 1, 2, 123456, tzinfo=UTC)
FIM = INICIO + timedelta(seconds=1, microseconds=3)


@pytest.fixture(scope="module")
def mercado():
    return DemoStore(make_synthetic_market(seed=7, as_of=date(2026, 10, 8))).load(BASE)


def _params(temporal=True):
    params = carregar_parametros()
    val = copy.deepcopy(params.valuation)
    val["qualidade"].pop("ri_disponibilidade_metodo", None)
    val["qualidade"]["demonstrativos_disponibilidade_metodo"] = "recepcao_observada"
    if temporal:
        val["projecao"]["resultado_corte_metodo"] = "base_preco_conhecimento_explicitos"
    else:
        val["projecao"].pop("resultado_corte_metodo", None)
    return replace(params, valuation=val)


@pytest.mark.parametrize("clock", ["sem_politica", "ausente", "naive"])
def test_cli_recusa_antes_de_reparo_coleta_ou_gravacao(tmp_path, monkeypatch, mercado, clock):
    for name in ("reparar_pendencias", "coletar", "gravar_snapshot"):
        monkeypatch.setattr(cli, name, lambda *a, **kw: pytest.fail("fronteira de escrita acessada"))
    book = tmp_path / "book_DADOS_SIMULADOS"
    kwargs = {"agora": datetime(2026, 10, 8)} if clock == "naive" else {}
    message = "fuso" if clock == "naive" else "política temporal" if clock == "sem_politica" else "instante ou relógio"
    with pytest.raises((RuntimeError, ValueError), match=message):
        cli.executar_snapshot(book, mercado, BASE, params=_params(clock != "sem_politica"), **kwargs)
    assert not book.exists()


def _fronteiras(monkeypatch):
    for name in ("checar_data", "reparar_pendencias"):
        monkeypatch.setattr(cli, name, lambda *a, **kw: None)
    monkeypatch.setattr(cli, "selado", lambda *a: (True, "DADOS SIMULADOS: livro mock"))
    monkeypatch.setattr(cli, "carregar_anterior", lambda *a: None)
    monkeypatch.setattr(cli, "executar", lambda *a, **kw: SimpleNamespace(distribuicao={}))
    monkeypatch.setattr(cli, "config_paths", lambda *a: {})


def test_snapshot_reutiliza_inicio_fim_e_releitura_offline(tmp_path, monkeypatch, mercado):
    _fronteiras(monkeypatch)
    empty = pd.DataFrame()
    dados = DadosPublicos(empty, empty, empty, empty, empty, empty, origem="SIMULADO")
    calls, writes = [], []

    def collect(*args, **kwargs):
        calls.append((args[1], kwargs["offline"], kwargs["conhecimento_ate"]))
        assert kwargs["ri_contexto"] is None
        return dados

    def write(book, ex, tabelas, params, **kwargs):
        writes.append(kwargs)
        assert tabelas.corte_temporal == {
            "metodo": "base_preco_conhecimento_explicitos", "base_preco": BASE.isoformat(),
            "data_modelo": "2026-10-08", "conhecimento_ate": FIM.isoformat(),
            "coleta_inicio": INICIO.isoformat(), "coleta_fim": FIM.isoformat()}
        return {"DADOS SIMULADOS": "mock de writer, nenhum arquivo"}

    monkeypatch.setattr(cli, "coletar", collect)
    monkeypatch.setattr(cli, "gravar_snapshot", write)
    book = tmp_path / "book_DADOS_SIMULADOS"
    cli.executar_snapshot(book, mercado, BASE, params=_params(), agora=INICIO, relogio=lambda: FIM)
    assert calls == [(date(2026, 10, 8), False, INICIO), (date(2026, 10, 8), True, FIM)]
    assert len(writes) == 1 and writes[0]["agora"] == FIM
    assert not book.exists()


def test_clock_retrocede_nao_alcanca_writer(tmp_path, monkeypatch, mercado):
    _fronteiras(monkeypatch)
    empty = pd.DataFrame()
    dados = DadosPublicos(empty, empty, empty, empty, empty, empty, origem="SIMULADO")
    calls = []
    monkeypatch.setattr(cli, "coletar", lambda *a, **kw: calls.append(kw) or dados)
    monkeypatch.setattr(cli, "gravar_snapshot", lambda *a, **kw: pytest.fail("writer após relógio retroceder"))
    with pytest.raises(RuntimeError, match="retrocedeu"):
        cli.executar_snapshot(tmp_path / "book_DADOS_SIMULADOS", mercado, BASE, params=_params(),
                              agora=INICIO, relogio=lambda: INICIO - timedelta(microseconds=1))
    assert len(calls) == 1


@pytest.mark.parametrize("temporal,ok", [(True, True), (False, False)])
def test_cmd_run_configuracao_normal_sem_argumento_sdk(tmp_path, monkeypatch, mercado, capsys, temporal, ok):
    _fronteiras(monkeypatch)
    rt = SimpleNamespace(store=SimpleNamespace(load=lambda d: mercado), now=lambda: INICIO)
    monkeypatch.setattr(Runtime, "from_args", lambda args: rt)
    monkeypatch.setattr(cli, "carregar_parametros", lambda *a, **kw: _params(temporal))
    # A função de execução permanece real; apenas coleta e writer são fronteiras falsas.
    empty = pd.DataFrame()
    dados = DadosPublicos(empty, empty, empty, empty, empty, empty, origem="SIMULADO")
    collects, writes = [], []
    monkeypatch.setattr(cli, "coletar", lambda *a, **kw: collects.append(kw) or dados)
    monkeypatch.setattr(cli, "gravar_snapshot", lambda *a, **kw: writes.append(kw) or {"DADOS SIMULADOS": "mock"})
    book = tmp_path / "book_DADOS_SIMULADOS"
    args = SimpleNamespace(date=BASE, offline=True, book=str(book), emissores=None)
    assert cli.cmd_run(args) == (cli.OK if ok else cli.FALHA)
    out = capsys.readouterr()
    if ok:
        assert len(collects) == 2 and len(writes) == 1
        assert all(k["conhecimento_ate"] == INICIO and k["offline"] for k in collects)
        assert all(k["ri_contexto"] is None for k in collects)
        assert json.loads(out.out)["DADOS SIMULADOS"] == "mock"
    else:
        assert not collects and not writes and "política temporal" in out.err
    assert not book.exists()
