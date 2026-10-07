"""DADOS SIMULADOS: custódia por instante antes da extração, sem rede."""
from __future__ import annotations

import importlib.util
import io
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from cdp.cobertura.fontes import (
    DadosPublicos,
    capital_oficial,
    contas_suplementares_cvm,
    csv_canonico,
)
from cdp.cobertura.temporal import construir
from cdp.data import publico as P
from cdp.data import publico_arquivo as A
from cdp.data import publico_resultados as R
from cdp.data import publico_yahoo as Y

DIA = date(2026, 10, 9)
ANTERIOR = datetime(2026, 10, 8, 22, tzinfo=UTC)
CEDO = datetime(2026, 10, 9, 10, tzinfo=UTC)
CORTE = datetime(2026, 10, 9, 14, 7, tzinfo=UTC)
TARDE = datetime(2026, 10, 9, 18, tzinfo=UTC)


def _sem_rede(*a, **kw):
    raise AssertionError("rede proibida em DADOS SIMULADOS")


def _gravar(arq, parte, ticker, conteudo, quando):
    return arq.gravar(f"YAHOO/{parte}/{ticker}.json", "YAHOO", "https://example.invalid/DADOS_SIMULADOS",
                      Y.serializar({"ticker": ticker, "parte": parte, **conteudo}), data_coleta=quando)


def test_arquivo_seleciona_vintage_anterior_e_recusa_sha_e_leitura_futura(tmp_path):
    arq = A.Arquivo(tmp_path)
    cedo = _gravar(arq, "info", "TEST", {"info": {"targetMeanPrice": 50}}, CEDO)
    tarde = _gravar(arq, "info", "TEST", {"info": {"targetMeanPrice": 100}}, TARDE)
    with A.corte_de_conhecimento(CORTE):
        sel = A.Arquivo(tmp_path, offline=True)
        assert sel.buscar(cedo.chave, DIA) == cedo
        assert sel.por_sha(cedo.sha256) == cedo and sel.por_sha(tarde.sha256) is None
        with pytest.raises(A.FonteIndisponivel, match="posterior"):
            sel.ler(tarde)
        reg, raw = sel.obter(cedo.chave, "YAHOO", None, _sem_rede, ate=DIA, instantaneo=True)
        assert reg == cedo and Y.ler_json(raw)["info"]["targetMeanPrice"] == 50
    # A ausência da política conserva integralmente a escolha por data civil.
    assert A.Arquivo(tmp_path, offline=True).buscar(cedo.chave, DIA) == tarde


def test_captura_posterior_no_mesmo_segundo_recusada_e_indice_preserva_micros(tmp_path):
    corte = CORTE.replace(microsecond=100000)
    captura = CORTE.replace(microsecond=900000)
    chave = "RI/nota/subsegundo.pdf"
    arq = A.Arquivo(tmp_path, conhecimento_ate=corte, agora=lambda: captura)
    assert arq.obter(chave, "RI", None, lambda: b"DADOS SIMULADOS", ate=DIA) is None
    reg = arq.registros(chave)[0]
    assert reg.data_coleta == captura and arq.buscar(chave) is None
    indice = json.loads(arq.caminho_indice.read_text().strip())
    assert indice["data_coleta"] == captura.isoformat(timespec="microseconds")
    assert indice["precisao_temporal"] == "microseconds"
    assert reg.como_dict()["data_coleta"] == captura.isoformat(timespec="microseconds")
    assert A.Arquivo(tmp_path, offline=True, conhecimento_ate=corte).buscar(chave) is None
    assert A.Arquivo(tmp_path, offline=True, conhecimento_ate=captura).buscar(chave).data_coleta == captura
    # Sem chave/contexto temporal, mantém o índice histórico com precisão de segundos.
    antigo = A.Arquivo(tmp_path / "legado", agora=lambda: captura)
    r = antigo.gravar(chave, "RI", None, b"DADOS SIMULADOS")
    assert r.data_coleta == captura.replace(microsecond=0)
    assert json.loads(antigo.caminho_indice.read_text().strip())["data_coleta"] == CORTE.isoformat()


@pytest.mark.parametrize("microseconds", [100000, 900000])
def test_registro_legado_truncado_so_prova_custodia_apos_limite_superior(tmp_path, microseconds):
    legado = A.Arquivo(tmp_path, agora=lambda: CORTE.replace(microsecond=900000))
    chave = "RI/nota/legado.pdf"
    r = legado.gravar(chave, "RI", None, b"DADOS SIMULADOS")
    assert r.precisao == "seconds" and r.limite_captura == CORTE + pd.Timedelta(seconds=1)
    estrito = A.Arquivo(tmp_path, offline=True, conhecimento_ate=CORTE.replace(microsecond=microseconds))
    assert estrito.buscar(chave) is None and estrito.por_sha(r.sha256) is None
    with pytest.raises(A.FonteIndisponivel):
        estrito.ler(r)
    final = A.Arquivo(tmp_path, offline=True, conhecimento_ate=CORTE + pd.Timedelta(seconds=1))
    assert final.buscar(chave).precisao == "seconds" and final.ler(final.buscar(chave)) == b"DADOS SIMULADOS"
    assert "precisao_temporal" not in r.como_dict()


def test_relogio_default_preserva_precisao_ativa_sem_alterar_padrao_legado(tmp_path, monkeypatch):
    captura = CORTE.replace(microsecond=900000)
    monkeypatch.setattr(A, "_agora_preciso", lambda: captura)
    estrito = A.Arquivo(tmp_path, conhecimento_ate=CORTE.replace(microsecond=100000))
    assert estrito._agora() == captura
    assert estrito.obter("RI/nota/default.pdf", "RI", None, lambda: b"DADOS SIMULADOS", ate=DIA) is None
    assert A.Arquivo(tmp_path / "legado")._agora is A.agora_utc


def test_catalogo_ri_exige_limite_conservador_da_captura_legada(tmp_path):
    fixture = Path(__file__).parents[1] / "fixtures/cdp/resultado_ri"
    estrutura = json.loads((fixture / "catalogo_sintetico.json").read_text())
    antigo = A.Arquivo(tmp_path, agora=lambda: CORTE.replace(microsecond=900000))
    ids = sorted({d["issuer_id"] for d in estrutura["documentos"]})
    for d, nome in zip(estrutura["documentos"], ("anual_simulado.pdf", "semestre_simulado.pdf"), strict=True):
        antigo.gravar(f"RI/resultados/{d['issuer_id']}/{d['sha256']}.pdf", "RI", d["url"],
                       (fixture / nome).read_bytes())
    cedo = CORTE.replace(microsecond=100000)
    f, c = R.coletar_resultados(ids, arquivo=A.Arquivo(tmp_path, offline=True, conhecimento_ate=cedo),
                                conhecimento_ate=cedo, estrutura=estrutura, exigir_captura=True,
                                http_get=_sem_rede)
    assert f.empty and not c["documentos"] and not c["bindings"]
    final = CORTE + pd.Timedelta(seconds=1)
    f, c = R.coletar_resultados(ids, arquivo=A.Arquivo(tmp_path, offline=True, conhecimento_ate=final),
                                conhecimento_ate=final, estrutura=estrutura, exigir_captura=True,
                                http_get=_sem_rede)
    assert not f.empty and len(c["documentos"]) == 2 and c["bindings"]
    assert all(d["first_capture"] == final.isoformat() for d in c["documentos"])
    assert all(d["arquivo"]["data_coleta"] == CORTE.isoformat() for d in c["documentos"])
    assert all("precisao_temporal" not in d["arquivo"] for d in c["documentos"])


def test_envelope_ri_sem_politica_preserva_schema_antigo_mesmo_lendo_indice_preciso(tmp_path):
    fixture = Path(__file__).parents[1] / "fixtures/cdp/resultado_ri"
    estrutura = json.loads((fixture / "catalogo_sintetico.json").read_text())
    captura = CORTE.replace(microsecond=900000)
    arq = A.Arquivo(tmp_path, conhecimento_ate=captura, agora=lambda: captura)
    ids = sorted({d["issuer_id"] for d in estrutura["documentos"]})
    for d, nome in zip(estrutura["documentos"], ("anual_simulado.pdf", "semestre_simulado.pdf"), strict=True):
        arq.gravar(f"RI/resultados/{d['issuer_id']}/{d['sha256']}.pdf", "RI", d["url"], (fixture / nome).read_bytes())
    _, velho = R.coletar_resultados(ids, arquivo=A.Arquivo(tmp_path, offline=True),
                                    conhecimento_ate=captura, estrutura=estrutura, http_get=_sem_rede)
    assert all("precisao_temporal" not in d["arquivo"] for d in velho["documentos"])
    assert all(d["arquivo"]["data_coleta"] == CORTE.isoformat() for d in velho["documentos"])
    _, novo = R.coletar_resultados(ids, arquivo=A.Arquivo(tmp_path, offline=True, conhecimento_ate=captura),
                                   conhecimento_ate=captura, estrutura=estrutura, exigir_captura=True,
                                   http_get=_sem_rede)
    assert all(d["arquivo"]["precisao_temporal"] == "microseconds" for d in novo["documentos"])
    assert all(d["arquivo"]["data_coleta"] == captura.isoformat() for d in novo["documentos"])


@pytest.mark.parametrize("instantaneo", [True, False])
def test_primeira_download_arquivado_depois_do_corte_so_entra_na_releitura_final(tmp_path, instantaneo):
    arq = A.Arquivo(tmp_path, agora=lambda: TARDE, conhecimento_ate=CORTE)
    chave = "YAHOO/info/TEST.json"
    assert arq.obter(chave, "YAHOO", None, lambda: b"DADOS SIMULADOS", ate=DIA,
                     instantaneo=instantaneo) is None
    assert len(arq.registros(chave)) == 1 and arq.buscar(chave) is None
    final = A.Arquivo(tmp_path, offline=True, conhecimento_ate=TARDE)
    assert final.obter(chave, "YAHOO", None, _sem_rede, ate=DIA,
                       instantaneo=instantaneo)[1] == b"DADOS SIMULADOS"


def test_fonte_com_publicacao_antiga_nao_autoriza_captura_futura_e_fallback_usa_anterior(tmp_path):
    arq = A.Arquivo(tmp_path)
    antigo = arq.gravar("RI/nota/antiga.pdf", "RI", "https://example.invalid/DADOS_SIMULADOS",
                        b"DADOS SIMULADOS: publicado 2025", data_coleta=ANTERIOR)
    arq.gravar(antigo.chave, "RI", antigo.url, b"DADOS SIMULADOS: reapresentado 2025", data_coleta=TARDE)
    sel = A.Arquivo(tmp_path, offline=True, conhecimento_ate=CORTE)
    reg, raw = sel.obter(antigo.chave, "RI", antigo.url, _sem_rede, ate=date(2025, 12, 31))
    assert reg == antigo and raw == b"DADOS SIMULADOS: publicado 2025"


@pytest.mark.parametrize("futuro", ["nenhum", "info", "estimativas"])
def test_consenso_multithread_seleciona_duas_dependencias_antes_da_normalizacao(tmp_path, futuro):
    arq = A.Arquivo(tmp_path)
    ticks = ["TESTA", "TESTB", "TESTC"]
    for t in ticks:
        if futuro != "info":
            _gravar(arq, "info", t, {"info": {"currency": "USD", "targetMeanPrice": 50}}, CEDO)
        if futuro != "estimativas":
            _gravar(arq, "estimativas", t, {"analyst_price_targets": {"mean": 55},
                    "earnings_estimate": {"0y": {"avg": 5, "currency": "USD"}}}, CEDO)
        _gravar(arq, "info", t, {"info": {"currency": "MXN", "targetMeanPrice": 100}}, TARDE)
        _gravar(arq, "estimativas", t, {"analyst_price_targets": {"mean": 105},
                "earnings_estimate": {"0y": {"avg": 10, "currency": "MXN"}}}, TARDE)
    with A.corte_de_conhecimento(CORTE):
        out = P.consenso_publico(ticks, DIA, offline=True, root=tmp_path, yf_factory=_sem_rede)
    assert len(out) == 3
    if futuro == "estimativas":
        assert out["eps_fy1"].isna().all() and set(out["alvo_medio"]) == {50}
        assert set(out["moeda_estimativas"]) == {None}
    else:
        assert set(out["eps_fy1"]) == {5} and set(out["alvo_medio"]) == {55}
        assert set(out["moeda_estimativas"]) == {"USD"}
    if futuro == "info":
        assert out["data_coleta_info"].isna().all() and out["sha256_info"].isna().all()
        assert set(out["moeda_cotacao"]) == {None}
    else:
        assert set(out["data_coleta_info"]) == {pd.Timestamp(CEDO)}
        assert set(out["moeda_cotacao"]) == {"USD"}
    assert all(pd.Timestamp(d) <= CORTE for d in out["data_coleta"] if pd.notna(d))
    tarde = P.consenso_publico(ticks, DIA, offline=True, root=tmp_path, yf_factory=_sem_rede)
    assert set(tarde["alvo_medio"]) == {105}


def test_serializacao_ativa_preserva_instantes_e_ausencia_sem_mudar_corpo_legado():
    vazio = pd.DataFrame()
    consenso = pd.DataFrame({"ticker": ["TEST", "AUSENTE"],
                             "data_coleta": pd.to_datetime([CEDO, None], utc=True),
                             "data_coleta_info": pd.to_datetime([CORTE, None], utc=True)})
    dados = DadosPublicos(vazio, consenso, vazio, vazio, vazio, vazio)
    velho = csv_canonico(dados.tabelas()["consenso"])
    assert "T10:00" not in velho and "2026-10-09" in velho
    ativo = replace(dados, corte_temporal=construir(date(2026, 10, 8), CORTE))
    texto = csv_canonico(ativo.tabelas()["consenso"])
    roundtrip = pd.read_csv(io.StringIO(texto))
    linha = roundtrip.set_index("ticker").loc["TEST"]
    assert linha["data_coleta"] == CEDO.isoformat()
    assert linha["data_coleta_info"] == CORTE.isoformat()
    assert pd.isna(roundtrip.set_index("ticker").loc["AUSENTE", "data_coleta"])
    assert csv_canonico(dados.tabelas()["consenso"]) == velho


def test_fundamentos_demais_blocos_e_helpers_cvm_usam_mesma_selecao_estrita(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("fixture_corte_publico", Path(__file__).parents[1]
                                                / "fixtures/publico/construir.py")
    fx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fx)
    base = fx.construir_arquivo(tmp_path)
    uni = base["universo"]
    # Construtores diretos dos helpers usam o mestre real da fixture.
    original_uni = P._universo
    monkeypatch.setattr(P, "_universo", lambda u: uni if u is None else original_uni(u))
    arq = base["arquivo"]
    registros = arq.registros()
    for r in registros:
        arq.gravar(r.chave, r.fonte, r.url, b"DADOS SIMULADOS: versao futura deliberadamente ilegivel",
                    data_coleta=TARDE)
    leitura = A.Arquivo.ler
    lidos = []
    def conferir(self, reg):
        assert self.conhecimento_ate == CORTE and reg.data_coleta <= CORTE
        lidos.append(reg.chave)
        return leitura(self, reg)
    monkeypatch.setattr(A.Arquivo, "ler", conferir)
    with A.corte_de_conhecimento(CORTE):
        dem = P.demonstrativos(list(uni.issuers.index), DIA, offline=True, root=tmp_path,
                              universe=uni, http_get=_sem_rede, yf_factory=_sem_rede)
        ff = P.free_float(list(uni.issuers.index), DIA, offline=True, root=tmp_path,
                          universe=uni, http_get=_sem_rede, yf_factory=_sem_rede)
        div = P.dividendos(list(uni.lines.index), DIA, offline=True, root=tmp_path,
                           universe=uni, yf_factory=_sem_rede)
        taxas = P.taxas_publicas(DIA, offline=True, root=tmp_path, http_get=_sem_rede)
        etf = P.composicao_etf("ILF", DIA, offline=True, root=tmp_path,
                              universe=uni, http_get=_sem_rede)
        eventos = P.eventos_corporativos(list(uni.issuers.index), date(2026, 10, 1), date(2026, 11, 1),
                                          as_of=DIA, offline=True, root=tmp_path, universe=uni,
                                          http_get=_sem_rede, yf_factory=_sem_rede)
        cap = capital_oficial(list(uni.issuers.index), DIA, tmp_path)
        contas_suplementares_cvm(list(uni.issuers.index), DIA, tmp_path)
    assert all(not df.empty for df in (dem, ff, div, taxas, etf, eventos))
    # O FRE da fixture contém float, sem a tabela de capital social: ausência preservada.
    assert cap.empty
    assert any(k.startswith("CVM/FRE/") for k in lidos)
    assert any(k.startswith("CVM/DFP/") for k in lidos)
    assert any(k.startswith("CVM/ITR/") for k in lidos)
    assert any(k.startswith("SEC/") for k in lidos) and any(k.startswith("YAHOO/") for k in lidos)
