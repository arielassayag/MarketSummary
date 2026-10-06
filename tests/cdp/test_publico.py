"""Camada de dados públicos (A1) — 100% offline, com arquivo de teste em formatos reais.

O arquivo de teste (``tests/fixtures/publico/construir.py``) imita os arquivos públicos (ZIPs da
CVM, ``companyfacts`` da SEC, respostas serializadas do Yahoo, CSVs de ETFs, FRED/BCB e o PDF
do calendário de eventos) com empresas fictícias (DADOS SIMULADOS). Nenhum teste acessa a rede:
o ``http_get`` e a fábrica do yfinance explodem se chamados.
"""

from __future__ import annotations

import importlib.util
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from cdp.data import publico as P
from cdp.data import publico_arquivo as pa
from cdp.data import publico_cvm as cvm
from cdp.data import publico_etf as etfm
from cdp.data import publico_pdf as pdf
from cdp.data import publico_sec as sec
from cdp.data import publico_yahoo as yh
from cdp.data.publico_fatos import selecionar_pit

_SPEC = importlib.util.spec_from_file_location(
    "construir_publico", Path(__file__).resolve().parents[1] / "fixtures" / "publico" /
    "construir.py")
fx = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fx)


def _sem_rede(*_a, **_k):
    raise AssertionError("acesso à rede em teste offline")


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setattr("cdp.data.publico.default_http_get", _sem_rede)
    monkeypatch.setattr("cdp.data.publico_yahoo._yf_ticker", _sem_rede)
    out = fx.construir_arquivo(tmp_path)
    out["root"] = tmp_path
    return out


def _dem(base, ids=None, as_of=None, **kw):
    return P.demonstrativos(ids or list(base["universo"].issuers.index), as_of or base["as_of"],
                            offline=True, root=base["root"], universe=base["universo"],
                            http_get=_sem_rede, yf_factory=_sem_rede, **kw)


def _v(df, iid, item, freq, fim):
    r = df[(df["issuer_id"] == iid) & (df["item"] == item) & (df["freq"] == freq)
           & (df["period_end"] == pd.Timestamp(fim))]
    assert len(r) <= 1, r
    return float(r["value"].iloc[0]) if len(r) else math.nan


# ======================================================================
# Arquivo
# ======================================================================

def test_arquivo_grava_le_e_detecta_adulteracao(tmp_path):
    t0 = datetime(2026, 10, 1, 12, tzinfo=UTC)
    arq = pa.Arquivo(tmp_path, agora=lambda: t0)
    r1 = arq.gravar("CVM/DFP/x.zip", "CVM", "https://u", b"abc", data_coleta=t0)
    r2 = arq.gravar("CVM/DFP/x.zip", "CVM", "https://u", b"abc",
                    data_coleta=t0 + timedelta(days=1))
    assert r1.caminho == r2.caminho  # conteúdo idêntico não é regravado
    r3 = arq.gravar("CVM/DFP/x.zip", "CVM", "https://u", b"abcd",
                    data_coleta=t0 + timedelta(days=2))
    assert r3.caminho != r1.caminho
    novo = pa.Arquivo(tmp_path, offline=True)
    assert novo.buscar("CVM/DFP/x.zip", date(2026, 10, 1)).sha256 == r1.sha256
    assert novo.buscar("CVM/DFP/x.zip", date(2026, 9, 30)) is None  # coletado depois
    assert novo.ler(novo.buscar("CVM/DFP/x.zip")) == b"abcd"
    (tmp_path / "publico" / r3.caminho).write_bytes(b"zzzz")
    with pytest.raises(pa.ArquivoAdulterado):
        novo.ler(novo.buscar("CVM/DFP/x.zip"))
    with pytest.raises(pa.FonteIndisponivel):
        novo.gravar("CVM/DFP/y.zip", "CVM", None, b"1")
    with pytest.raises(ValueError):
        arq.gravar("../fora", "CVM", None, b"1")


def test_arquivo_obter_offline_instantaneo_e_falha_de_rede(tmp_path):
    t0 = datetime(2026, 10, 9, 22, tzinfo=UTC)
    arq = pa.Arquivo(tmp_path, agora=lambda: t0)
    chamadas = []

    def baixar():
        chamadas.append(1)
        return b"v1"

    reg, c = arq.obter("YAHOO/info/X.json", "YAHOO", None, baixar, ate=date(2026, 10, 9),
                       max_idade_dias=1.0)
    assert c == b"v1" and len(chamadas) == 1
    # reaproveita coleta recente
    arq.obter("YAHOO/info/X.json", "YAHOO", None, baixar, ate=date(2026, 10, 9),
              max_idade_dias=1.0)
    assert len(chamadas) == 1
    # retrato com data passada: nunca baixa (seria look-ahead)
    assert arq.obter("YAHOO/info/Y.json", "YAHOO", None, baixar, ate=date(2026, 10, 1),
                     instantaneo=True) is None
    assert len(chamadas) == 1

    def falha():
        raise OSError("sem rede")

    reg2, c2 = arq.obter("YAHOO/info/X.json", "YAHOO", None, falha, ate=date(2026, 10, 9))
    assert c2 == b"v1" and arq.falhas
    off = pa.Arquivo(tmp_path, offline=True)
    assert off.obter("YAHOO/info/X.json", "YAHOO", None, _sem_rede, ate=date(2026, 10, 9))
    # resposta inválida nunca é arquivada
    assert arq.obter("CVM/DFP/z.zip", "CVM", None, lambda: b"<html>", ate=date(2026, 10, 9),
                     validar=cvm.validar_zip) is None
    assert arq.buscar("CVM/DFP/z.zip") is None


# ======================================================================
# CVM
# ======================================================================

def test_cvm_itens_canonicos_do_dfp(base):
    arq = base["arquivo"]
    conteudo = arq.ler(arq.buscar("CVM/DFP/dfp_cia_aberta_2025.zip"))
    f = cvm.fatos_cvm(cvm.ler_zip_demonstracoes(conteudo, "DFP", 2025), "DFP")
    ind = f[f["entidade"] == fx.CNPJ_IND].set_index("item")["value"]
    v = fx._ind_fluxos(fx.REC_ANUAL[2025])
    assert ind["receita"] == pytest.approx(v["rec"] * 1000)
    assert ind["ebit"] == pytest.approx(v["ebit"] * 1000)
    assert ind["d_a"] == pytest.approx(v["da"] * 1000)  # DVA, em módulo
    assert ind["capex"] == pytest.approx(-(v["imob"] + v["intang"]) * 1000)  # venda excluída
    assert ind["dividendos_pagos"] == pytest.approx(-v["div"] * 1000)
    assert ind["recompras"] == pytest.approx(10_000 * 1000)
    assert ind["ir_csll"] < 0 and ind["resultado_financeiro"] < 0
    assert ind["divida_bruta"] == pytest.approx((120_000 + 500_000) * 1000)  # sem arrendamento
    assert ind["arrendamentos"] == pytest.approx((30_000 + 100_000) * 1000)
    assert ind["patrimonio_controladores"] == pytest.approx((800_000 - 40_000) * 1000)
    # ações reportadas em milhares: unidade conferida pelo LPA (x1000)
    assert ind["acoes_em_circulacao"] == pytest.approx(99_000_000)
    assert ind["acoes_tesouraria"] == pytest.approx(1_000_000)
    banco = f[f["entidade"] == fx.CNPJ_BANCO].set_index("item")["value"]
    assert banco["margem_financeira"] == pytest.approx(250_000 * 1000)  # antes da PDD em 3.02
    assert banco["despesa_pdd"] == pytest.approx(-50_000 * 1000)
    assert banco["receita_servicos"] == pytest.approx(60_000 * 1000)
    assert banco["carteira_credito"] == pytest.approx(3_000_000 * 1000)
    assert banco["provisao_credito"] == pytest.approx(150_000 * 1000)
    assert "ebit" not in banco.index and "caixa" not in banco.index
    assert f["url"].str.startswith("https://www.rad.cvm.gov.br/").all()


def test_pit_trimestres_ttm_e_sem_look_ahead(base):
    d = _dem(base, ["BR_SIMU"])
    k = 1000.0
    assert _v(d, "BR_SIMU", "receita", "A", "2025-12-31") == pytest.approx(1_210_000 * k)
    assert _v(d, "BR_SIMU", "receita", "Q", "2025-06-30") == pytest.approx(300_000 * k)
    # Q4 = anual − 9M
    assert _v(d, "BR_SIMU", "receita", "Q", "2025-12-31") == pytest.approx(
        (1_210_000 - 890_000) * k)
    # DFC só acumulado no ITR: trimestre = diferença de acumulados
    cfo_h1 = fx._ind_fluxos(600_000)["cfo"] - fx._ind_fluxos(280_000)["cfo"]
    assert _v(d, "BR_SIMU", "cfo", "Q", "2026-06-30") == pytest.approx(
        (fx._ind_fluxos(650_000)["cfo"] - fx._ind_fluxos(320_000)["cfo"]) * k)
    assert cfo_h1 > 0
    ttm = 320_000 + 330_000 + (1_210_000 - 890_000) + 310_000
    assert _v(d, "BR_SIMU", "receita", "TTM", "2026-06-30") == pytest.approx(ttm * k)
    assert _v(d, "BR_SIMU", "ebitda", "TTM", "2026-06-30") == pytest.approx(
        0.30 * ttm * k)  # ebit 20% + d_a 10%
    linha = d[(d["item"] == "receita") & (d["freq"] == "Q")
              & (d["period_end"] == pd.Timestamp("2026-06-30"))].iloc[0]
    assert linha["data_publicacao"] == date(2026, 8, 7) and linha["fonte"] == "CVM"
    assert len(linha["sha256"]) == 64 and not linha["pit_estimado"]
    # antes do ITR 2T26: o trimestre não existe; nada publicado depois de as_of entra
    d2 = _dem(base, ["BR_SIMU"], as_of=date(2026, 8, 6))
    assert math.isnan(_v(d2, "BR_SIMU", "receita", "Q", "2026-06-30"))
    assert (pd.to_datetime(d2["data_publicacao"]) <= pd.Timestamp("2026-08-06")).all()
    # sem chaves duplicadas
    assert not d.duplicated(["issuer_id", "freq", "period_end", "item"]).any()
    assert set(d["item"]) <= set(P.CANONICAL_ITEMS)
    assert list(d.columns) == P.DEMONSTRATIVOS_COLUNAS


def test_demonstrativos_sec_yahoo_e_ausencias(base):
    d = _dem(base)
    fontes = d.groupby("issuer_id")["fonte"].agg(lambda s: set(s)).to_dict()
    # data de publicação oficial (CVM/SEC) nunca é marcada como estimada, mesmo misturada
    assert not d.loc[d["fonte"].isin(["CVM", "SEC"]), "pit_estimado"].any()
    assert d.loc[d["fonte"] == "YAHOO", "pit_estimado"].all()
    assert fontes["BR_SIMU"] == {"CVM"} and fontes["BR_BSIM"] == {"CVM"}
    assert "SEC" in fontes["PE_SAND"] and fontes["MX_SIMU"] == {"YAHOO"}
    # SEC: sinal da CVM (despesa negativa), capex em módulo, reapresentação PIT
    assert _v(d, "PE_SAND", "ir_csll", "A", "2025-12-31") == -50.0
    assert _v(d, "PE_SAND", "capex", "A", "2025-12-31") == 80.0
    assert _v(d, "PE_SAND", "receita", "A", "2024-12-31") == 1080.0
    antes = _dem(base, ["PE_SAND"], as_of=date(2026, 1, 1))
    assert _v(antes, "PE_SAND", "receita", "A", "2024-12-31") == 1100.0
    assert math.isnan(_v(antes, "PE_SAND", "receita", "A", "2025-12-31"))
    # complemento Yahoo: trimestres que o 20-F não traz (mesma moeda), sem duplicar
    comp = d[(d["issuer_id"] == "PE_SAND") & (d["fonte"] == "YAHOO")]
    assert not comp.empty and comp["nota"].str.contains("complemento").all()
    assert (comp["currency"] == "USD").all()
    # Yahoo: data de publicação estimada, nunca depois da coleta
    mx = d[d["issuer_id"] == "MX_SIMU"]
    assert mx["pit_estimado"].all()
    assert (pd.to_datetime(mx["data_publicacao"]) <= pd.Timestamp("2026-10-08")).all()
    assert _v(d, "MX_SIMU", "ir_csll", "A", "2025-12-31") == -1.8e9
    assert _v(d, "MX_SIMU", "capex", "A", "2025-12-31") == 5.0e9
    assert _v(d, "MX_SIMU", "divida_bruta", "A", "2025-12-31") == 1.2e10
    assert _v(d, "MX_SIMU", "arrendamentos", "A", "2025-12-31") == 3.0e9
    # ausente nunca vira zero: EBIT 2022 e dividendos 2022 nulos no Yahoo ⇒ sem linha
    assert math.isnan(_v(d, "MX_SIMU", "ebit", "A", "2022-12-31"))
    assert math.isnan(_v(d, "MX_SIMU", "dividendos_pagos", "A", "2022-12-31"))
    assert (d["value"].notna()).all()
    # financeiras: sem FCF/EBITDA calculados
    banco = d[d["issuer_id"] == "BR_BSIM"]
    assert not banco["item"].isin(["fcf", "ebitda"]).any()
    assert banco["item"].isin(["margem_financeira", "despesa_pdd"]).any()


def test_selecionar_pit_reapresentacao_e_versao():
    base = {"entidade": "X", "demonstrativo": "DRE", "item": "receita", "currency": "BRL",
            "documento": "d", "url": None, "consolidado": True, "anual": True,
            "fonte": "CVM", "sha256": "s", "period_start": pd.Timestamp("2025-01-01"),
            "period_end": pd.Timestamp("2025-12-31")}
    f = pd.DataFrame([{**base, "value": 100.0, "received_date": pd.Timestamp("2026-03-01"),
                       "version": 1},
                      {**base, "value": 90.0, "received_date": pd.Timestamp("2026-06-01"),
                       "version": 2}])
    a = selecionar_pit(f, date(2026, 4, 1))
    b = selecionar_pit(f, date(2026, 7, 1))
    assert a.loc[a["freq"] == "A", "value"].item() == 100.0
    assert b.loc[b["freq"] == "A", "value"].item() == 90.0
    assert selecionar_pit(f, date(2026, 2, 1)).empty


# ======================================================================
# Consenso, proventos, free float
# ======================================================================

def test_consenso_publico_offline(base):
    c = P.consenso_publico(["SIMU.MX", "SAND", "NAO.EXISTE"], base["as_of"], offline=True,
                           root=base["root"], yf_factory=_sem_rede)
    assert list(c.columns) == P.CONSENSO_COLUNAS
    r = c.set_index("ticker")
    assert r.loc["SIMU.MX", "eps_fy1"] == 3.1 and r.loc["SIMU.MX", "eps_fy2"] == 3.5
    assert r.loc["SIMU.MX", "alvo_mediano"] == 49.0 and r.loc["SIMU.MX", "n_analistas_alvo"] == 9
    assert r.loc["SIMU.MX", "moeda_estimativas"] == "MXN"
    assert r.loc["SIMU.MX", "fonte"] == "YAHOO"
    assert math.isnan(r.loc["SAND", "eps_fy1"])  # sem estimativas ⇒ NaN, nunca zero
    assert math.isnan(r.loc["NAO.EXISTE", "alvo_medio"]) and pd.isna(r.loc["NAO.EXISTE", "fonte"])
    assert c.attrs["nota"] == "consenso público Yahoo Finance"
    # coletado depois da data de referência ⇒ não existe naquela data
    antes = P.consenso_publico(["SIMU.MX"], date(2026, 10, 1), offline=True, root=base["root"])
    assert math.isnan(antes["eps_fy1"].iloc[0])


def test_dividendos_ate_as_of(base):
    d = P.dividendos(["SIMU.MX"], base["as_of"], offline=True, root=base["root"],
                     universe=base["universo"], yf_factory=_sem_rede)
    assert list(d["data_ex"]) == [date(2025, 5, 10), date(2026, 5, 8)]
    assert (d["moeda"] == "MXN").all() and list(d.columns) == P.DIVIDENDOS_COLUNAS


def test_free_float_cvm_e_yahoo(base):
    ff = P.free_float(["BR_SIMU", "MX_SIMU", "PE_SAND", "BR_BSIM"], base["as_of"], offline=True,
                      root=base["root"], universe=base["universo"], http_get=_sem_rede,
                      yf_factory=_sem_rede).set_index("issuer_id")
    # versão 2 do FRE foi recebida depois de as_of ⇒ vale a versão 1
    assert ff.loc["BR_SIMU", "free_float_pct"] == pytest.approx(0.455)
    assert ff.loc["BR_SIMU", "fonte"] == "CVM"
    assert ff.loc["MX_SIMU", "free_float_pct"] == pytest.approx(0.8)
    assert math.isnan(ff.loc["PE_SAND", "free_float_pct"])  # float > total ⇒ NaN com motivo
    assert "float_maior_que_total" in ff.loc["PE_SAND", "detalhe"]
    assert math.isnan(ff.loc["BR_BSIM", "free_float_pct"])  # sem FRE nem Yahoo
    depois = P.free_float(["BR_SIMU"], date(2026, 12, 20), offline=True, root=base["root"],
                          universe=base["universo"])
    assert depois["free_float_pct"].iloc[0] == pytest.approx(0.46)


# ======================================================================
# ETFs
# ======================================================================

def test_composicao_etf_ishares_globalx_b3(base):
    ilf = P.composicao_etf("ILF", base["as_of"], offline=True, root=base["root"],
                           universe=base["universo"], http_get=_sem_rede,
                           mapa=base["root"] / "inexistente.csv")
    assert list(ilf.columns) == etfm.COLUNAS
    r = ilf.set_index("ticker_bruto")
    assert r.loc["SIMU3", "issuer_id"] == "BR_SIMU" and r.loc["SAND", "issuer_id"] == "PE_SAND"
    assert pd.isna(r.loc["ZZZZ11", "issuer_id"])  # fora do universo: mantido, não descartado
    assert r.loc["IBOVZ6", "peso"] == 0.0 and r.loc["IBOVZ6", "valor_nocional"] == 55_000.0
    assert r.loc["SIMU3", "peso"] == pytest.approx(0.35)
    assert ilf["data_ref"].iloc[0] == date(2026, 10, 8)
    assert ilf.attrs["cobertura"] == pytest.approx(0.75 / 0.99)
    argt = P.composicao_etf("ARGT", base["as_of"], offline=True, root=base["root"],
                            universe=base["universo"], http_get=_sem_rede)
    assert argt.set_index("ticker_bruto").loc["SAND", "issuer_id"] == "PE_SAND"
    assert argt["sedol"].iloc[0] == "B000001"
    bova = P.composicao_etf("BOVA11.SA", base["as_of"], offline=True, root=base["root"],
                            universe=base["universo"], http_get=_sem_rede)
    assert bova["peso"].sum() == pytest.approx(1.0)
    assert set(bova["issuer_id"]) == {"BR_SIMU", "BR_BSIM"}
    assert P.composicao_etf("XYZ", base["as_of"], offline=True, root=base["root"]) is None
    assert P.composicao_etf("EWZ", base["as_of"], offline=True, root=base["root"]) is None
    # carteira com data posterior à referência não é usada
    assert P.composicao_etf("ILF", date(2026, 10, 7), offline=True, root=base["root"]) is None


def test_mapa_curado_tem_precedencia(base, tmp_path):
    mapa = tmp_path / "mapa.csv"
    mapa.write_text("fonte,etf,ticker_bruto,yahoo_ticker,issuer_id\n"
                    "ISHARES,ILF,ZZZZ11,ZZZZ11.SA,BR_SIMU\n", encoding="utf-8")
    ilf = P.composicao_etf("ILF", base["as_of"], offline=True, root=base["root"],
                           universe=base["universo"], mapa=mapa).set_index("ticker_bruto")
    assert ilf.loc["ZZZZ11", "issuer_id"] == "BR_SIMU"
    assert ilf.loc["ZZZZ11", "mapeamento"] == "curado"


def test_yahoo_de_bolsas():
    assert etfm.yahoo_de("VALE3", "XBSP") == "VALE3.SA"
    assert etfm.yahoo_de("SQM.B", "Santiago Stock Exchange") == "SQM-B.SN"
    assert etfm.yahoo_de("ECOPETL CB", None) == "ECOPETL.CL"
    assert etfm.yahoo_de("PBR A", "New York Stock Exchange Inc.") == "PBR-A"


# ======================================================================
# Taxas
# ======================================================================

def test_taxas_publicas(base):
    t = P.taxas_publicas(base["as_of"], offline=True, root=base["root"], http_get=_sem_rede)
    assert list(t.columns) == P.TAXAS_COLUNAS
    s = {k: g for k, g in t.groupby("serie")}
    assert s["USD_10Y"]["valor"].iloc[-1] == pytest.approx(0.0531)
    assert len(s["USD_10Y"]) == 2  # "." do FRED é ausente, não zero
    assert s["SELIC_META"]["data"].max() <= base["as_of"]  # data futura do SGS descartada
    # IPCA datado pela disponibilidade (fim do mês de referência + 12 dias): o de setembro
    # (divulgado em outubro) ainda não existe em 09/10; o de agosto vale desde 12/09
    ipca = s["IPCA_12M"].set_index("data")["valor"]
    assert list(ipca.index) == [date(2026, 9, 12)]
    assert ipca.iloc[-1] == pytest.approx(0.051)
    depois = P.taxas_publicas(date(2026, 10, 12), offline=True, root=base["root"])
    assert depois.loc[depois["serie"] == "IPCA_12M", "valor"].iloc[-1] == pytest.approx(0.0499)
    assert s["FOCUS_IPCA_2026"]["valor"].item() == pytest.approx(0.0499)  # só baseCalculo 0
    assert s["FOCUS_CAMBIO_2026"]["valor"].item() == pytest.approx(5.20)
    assert set(t["fonte"]) == {"FRED", "BCB"}


# ======================================================================
# Eventos e PDF do calendário
# ======================================================================

def test_pdf_calendario_type1_e_identity_h():
    linhas = pdf.linhas_texto(fx.pdf_calendario())
    assert any("Informações Trimestrais" in ln for ln in linhas)
    assert any("06/11/2026" in ln for ln in linhas)
    evs = cvm.eventos_do_calendario(pdf.celulas(fx.pdf_calendario()))
    assert {"data": date(2026, 11, 6), "tipo": "resultado", "rotulo": "ITR 3T"} in evs
    assert {"data": date(2026, 3, 12), "tipo": "resultado", "rotulo": "DFP"} in evs
    assert {"data": date(2026, 4, 29), "tipo": "assembleia", "rotulo": "AGO"} in evs
    assert not any(e["data"] == date(2025, 12, 31) for e in evs)  # data dentro do rótulo
    with pytest.raises(pdf.PdfIlegivel):
        pdf.linhas_texto(b"<html>erro</html>")


def test_eventos_corporativos(base):
    ev = P.eventos_corporativos(list(base["universo"].issuers.index), date(2026, 7, 1),
                                date(2026, 12, 31), offline=True, root=base["root"],
                                universe=base["universo"], http_get=_sem_rede,
                                yf_factory=_sem_rede, as_of=base["as_of"])
    assert list(ev.columns) == P.EVENTOS_COLUNAS
    br = ev[ev["issuer_id"] == "BR_SIMU"]
    res = br[br["tipo"] == "resultado"].set_index("data")
    assert res.loc[date(2026, 8, 7), "fonte"] == "CVM"  # DT_RECEB do ITR 2T26
    assert not res.loc[date(2026, 11, 6), "estimada"]  # calendário publicado na CVM
    assert "calendário" in res.loc[date(2026, 11, 6), "documento"]
    assert (br["tipo"] == "fato_relevante").any()
    mx = ev[(ev["issuer_id"] == "MX_SIMU") & (ev["tipo"] == "resultado")].set_index("data")
    assert not mx.loc[date(2026, 10, 22), "estimada"]
    # PE_SAND: sem data futura conhecida ⇒ estimada pelo mesmo trimestre do ano anterior
    pe = ev[(ev["issuer_id"] == "PE_SAND") & (ev["tipo"] == "resultado")]
    est = pe[pe["estimada"]]
    assert len(est) == 1
    d = est["data"].iloc[0]
    assert d == date(2025, 10, 30) + timedelta(days=364)
    assert est["janela_inicio"].iloc[0] == d - timedelta(days=7)
    assert est["janela_fim"].iloc[0] == d + timedelta(days=7)
    assert "estimada" in est["documento"].iloc[0]


# ======================================================================
# SEC e Yahoo (unidades puras)
# ======================================================================

def test_fatos_sec_tags_e_unidades():
    f = sec.fatos_sec(fx.companyfacts())
    assert set(f["currency"].dropna()) == {"USD"}
    sh = f[f["item"] == "acoes_em_circulacao"]
    assert sh["value"].iloc[0] == 500_000_000 and sh["currency"].isna().all()
    assert f["anual"].all()
    assert f["url"].str.startswith("https://www.sec.gov/Archives/edgar/data/777/").all()


def test_parse_efts_correspondencia_exata():
    payload = json.dumps({"hits": {"hits": [
        {"_id": "1", "_source": {"entity": "X", "tickers": "ABCD, ABC"}},
        {"_id": "2", "_source": {"entity": "Y", "tickers": "AB"}}]}}).encode()
    assert sec.parse_efts(payload, "AB")["cik"] == "0000000002"
    assert sec.parse_efts(payload, "ZZ") is None


def test_yahoo_serializacao_canonica_e_float():
    a = yh.serializar({"b": 1.0, "a": float("nan"), "ticker": "X"})
    assert a == yh.serializar({"a": None, "ticker": "X", "b": 1.0})
    assert json.loads(a)["a"] is None
    assert yh.float_de({"info": {"floatShares": 6, "sharesOutstanding": 5}})[1] == \
        "float_maior_que_total"
    assert math.isnan(yh.float_de(None)[0])


# ======================================================================
# Arquivo SIMULADO (demo)
# ======================================================================

def test_arquivo_sintetico_offline(tmp_path):
    from cdp.data.publico_sintetico import AVISO, gerar_arquivo_sintetico
    from cdp.data.synthetic import make_synthetic_market

    md = make_synthetic_market(seed=7, as_of=date(2026, 10, 9))
    shas = gerar_arquivo_sintetico(tmp_path, md)
    assert set(shas) >= {"demonstrativos", "consenso", "eventos", "taxas", "etf_ILF"}
    ids = list(md.universe.issuers.index)
    d = P.demonstrativos(ids, md.as_of, offline=True, root=tmp_path, universe=md.universe)
    assert set(d["fonte"]) == {"SIMULADO"} and d["issuer_id"].nunique() >= 50
    assert (pd.to_datetime(d["data_publicacao"]) <= pd.Timestamp(md.as_of)).all()
    assert d["nota"].eq(AVISO).all()
    a = d[d["freq"] == "A"].groupby("issuer_id")["period_end"].nunique()
    assert (a >= 3).all()
    c = P.consenso_publico(list(md.universe.lines.index), md.as_of, offline=True, root=tmp_path)
    assert (c["fonte"] == "SIMULADO").all()
    e = P.composicao_etf("ILF", md.as_of, offline=True, root=tmp_path)
    assert e["peso"].sum() == pytest.approx(1.0)
    t = P.taxas_publicas(md.as_of, offline=True, root=tmp_path)
    assert "USD_10Y" in set(t["serie"])
    ev = P.eventos_corporativos(ids, md.as_of, md.as_of + timedelta(days=90), offline=True,
                                root=tmp_path, universe=md.universe)
    assert not ev.empty and (ev["fonte"] == "SIMULADO").all()
    # determinístico: mesmo mercado ⇒ mesmos pacotes
    assert gerar_arquivo_sintetico(tmp_path / "b", md) == shas
    # mercado real é recusado
    with pytest.raises(ValueError):
        gerar_arquivo_sintetico(tmp_path / "c", md.__class__(**{
            **md.__dict__, "manifest": md.manifest.model_copy(update={"is_synthetic": False})}))


def test_unidade_das_acoes_herdada_do_documento_anterior():
    def linha(fim, rec, val, unidade, item="acoes_em_circulacao"):
        return {"entidade": "C", "demonstrativo": "BP", "item": item, "period_start": pd.NaT,
                "period_end": pd.Timestamp(fim), "value": val, "currency": None,
                "received_date": pd.Timestamp(rec), "version": 1,
                "documento": f"ITR {fim} v1 (ações: unidade {unidade})", "url": None,
                "consolidado": True, "anual": False}

    f = pd.DataFrame([linha("2026-03-31", "2026-05-10", 99_000_000.0, "ok"),
                      linha("2026-06-30", "2026-08-10", 99_500.0, "na"),
                      linha("2026-06-30", "2026-08-10", 100_000.0, "na", "acoes_emitidas")])
    out = P._resolver_unidade_acoes(f)
    out = out[out["period_end"] == pd.Timestamp("2026-06-30")].set_index("item")
    assert out.loc["acoes_em_circulacao", "value"] == pytest.approx(99_500_000.0)
    assert out.loc["acoes_emitidas", "value"] == pytest.approx(100_000_000.0)
    assert out.loc["acoes_emitidas", "documento"].endswith("unidade x1000(herdada))")


def test_evento_sem_historico_estimado_pelo_fim_do_trimestre(base):
    ev = P.eventos_corporativos(["BR_BSIM"], date(2026, 10, 9), date(2026, 12, 31),
                                offline=True, root=base["root"], universe=base["universo"],
                                as_of=base["as_of"])
    r = ev[(ev["tipo"] == "resultado")]
    assert len(r) == 1 and r["estimada"].item()
    assert r["data"].item() == date(2026, 9, 30) + timedelta(days=50)
    assert (r["janela_fim"].item() - r["janela_inicio"].item()).days == 28


# ======================================================================
# Revisão: moeda de apresentação, contas, conferência (QA)
# ======================================================================

def _fatos_sec_pit(cf, as_of):
    f = sec.fatos_sec(cf)
    f["fonte"] = "SEC"
    f["sha256"] = "s"
    return f, selecionar_pit(f, as_of)


def _cf_troca(antiga: str, nova: str) -> dict:
    """XBRL de quem mudou a moeda de apresentação (ex.: YPF ARS→USD, Volaris MXN→USD, Sigma
    Lithium CAD→USD): 20-F antigos em ``antiga``; o 20-F de 2023 em ``nova`` com comparativos."""
    k = 1000.0
    a = {2020: "0000000999-21-000001", 2021: "0000000999-22-000001",
         2022: "0000000999-23-000001", 2023: "0000000999-24-000001"}
    filed = {2020: "2021-04-20", 2021: "2022-04-20", 2022: "2023-04-11", 2023: "2024-04-25"}
    rev, ll, at, pl = {}, {}, {}, {}

    def fl(dct, tag, ano_doc, ano, val, unit):
        dct.setdefault(tag, {}).setdefault(unit, []).append(fx._fato(
            val, f"{ano}-12-31", filed[ano_doc], "20-F", a[ano_doc], start=f"{ano}-01-01"))

    def st(dct, tag, ano_doc, ano, val, unit):
        dct.setdefault(tag, {}).setdefault(unit, []).append(fx._fato(
            val, f"{ano}-12-31", filed[ano_doc], "20-F", a[ano_doc]))

    for doc in (2020, 2021, 2022):  # moeda antiga: exercício e anterior
        for ano in (doc - 1, doc):
            fl(rev, "Revenue", doc, ano, 100.0 * ano * k, antiga)
            fl(ll, "ProfitLoss", doc, ano, 10.0 * ano * k, antiga)
            st(at, "Assets", doc, ano, 300.0 * ano * k, antiga)
            st(pl, "Equity", doc, ano, 150.0 * ano * k, antiga)
    if antiga != "USD":  # tradução de conveniência minoritária no 20-F de 2022
        fl(rev, "Revenue", 2022, 2022, 7.0, "USD")
    for ano in (2021, 2022, 2023):  # 20-F 2023 em moeda nova, com comparativos reexpressos
        fl(rev, "Revenue", 2023, ano, 100.0 * ano, nova)
        fl(ll, "ProfitLoss", 2023, ano, 10.0 * ano, nova)
    for ano in (2022, 2023):
        st(at, "Assets", 2023, ano, 300.0 * ano, nova)
        st(pl, "Equity", 2023, ano, 150.0 * ano, nova)
    ifrs = {tag: {"units": units} for d in (rev, ll, at, pl) for tag, units in d.items()}
    return {"cik": 999, "facts": {"ifrs-full": ifrs}}


@pytest.mark.parametrize("antiga,nova", [("ARS", "USD"), ("MXN", "USD"), ("CAD", "USD")])
def test_sec_moeda_por_arquivo_e_troca_de_moeda(antiga, nova):
    cf = _cf_troca(antiga, nova)
    f = sec.fatos_sec(cf)
    por_doc = f.assign(accn=f["documento"].str.split().str[2]).groupby("accn")["currency"].agg(
        lambda c: set(c.dropna()))
    assert por_doc["0000000999-24-000001"] == {nova}
    assert por_doc["0000000999-23-000001"] == {antiga}  # conveniência em USD fica de fora
    _, antes = _fatos_sec_pit(cf, date(2023, 6, 30))
    assert set(antes["currency"].dropna()) == {antiga}
    rec_a = antes[(antes["item"] == "receita") & (antes["freq"] == "A")]
    assert rec_a.set_index("period_end")["value"][pd.Timestamp("2022-12-31")] == 202_200_000.0
    _, depois = _fatos_sec_pit(cf, date(2024, 6, 30))
    assert set(depois["currency"].dropna()) == {nova}  # nunca uma série com moedas misturadas
    rec = depois[(depois["item"] == "receita") & (depois["freq"] == "A")].set_index("period_end")
    assert sorted(rec.index.year) == [2021, 2022, 2023]  # 2020 só existe na moeda antiga
    assert rec["value"][pd.Timestamp("2023-12-31")] == 202_300.0
    assert depois.attrs["moeda_trocada"]["0000000999"]["moeda"] == nova
    if antiga == "ARS":
        assert antes["nota"].fillna("").str.startswith("IAS 29").any()


def test_sec_maior_total_receita_parcial_aplicacoes_ifrs_e_datas_base():
    acc = "0000000888-26-000001"
    fato = fx._fato

    def un(*f):
        return {"units": {"USD": list(f)}}

    ifrs = {
        "Revenue": un(fato(86_184.0, "2025-12-31", "2026-03-25", "20-F", acc, start="2025-01-01"),
                      fato(80_000.0, "2024-12-31", "2026-03-25", "20-F", acc, start="2024-01-01")),
        "RevenueFromContractsWithCustomers": un(fato(0.103, "2023-12-31", "2026-03-25", "20-F",
                                                     acc, start="2023-01-01")),
        "ProfitLoss": un(fato(2_000.0, "2025-12-31", "2026-03-25", "20-F", acc,
                              start="2025-01-01"),
                         fato(1_500.0, "2024-12-31", "2026-03-25", "20-F", acc,
                              start="2024-01-01")),
        "Assets": un(fato(45_156.0, "2025-12-31", "2026-03-25", "20-F", acc),
                     fato(40_685.0, "2024-12-31", "2026-03-25", "20-F", acc),
                     fato(55_718.0, "2023-12-31", "2026-03-25", "20-F", acc),
                     fato(39_000.0, "2019-01-01", "2026-03-25", "20-F", acc)),  # abertura IFRS 16
        "Borrowings": un(fato(191.0, "2025-12-31", "2026-03-25", "20-F", acc)),
        "ShorttermBorrowings": un(fato(833.0, "2025-12-31", "2026-03-25", "20-F", acc)),
        "LongtermBorrowings": un(fato(20_257.0, "2025-12-31", "2026-03-25", "20-F", acc)),
        "CurrentInvestments": un(fato(455.0, "2025-12-31", "2026-03-25", "20-F", acc)),
    }
    dei = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        fato(1_110_000_000, "2026-03-20", "2026-03-25", "20-F", acc)]}}}
    _, d = _fatos_sec_pit({"cik": 888, "facts": {"ifrs-full": ifrs, "dei": dei}},
                          date(2026, 6, 30))

    def v(item, freq, fim):
        r = d[(d["item"] == item) & (d["freq"] == freq) & (d["period_end"] == pd.Timestamp(fim))]
        return float(r["value"].iloc[0]) if len(r) else math.nan

    assert v("divida_bruta", "A", "2025-12-31") == 21_090.0  # curto + longo, não Borrowings
    assert v("aplicacoes_cp", "A", "2025-12-31") == 455.0     # ifrs-full CurrentInvestments
    assert v("divida_liquida", "A", "2025-12-31") == 21_090.0 - 455.0 if not math.isnan(
        v("caixa", "A", "2025-12-31")) else True
    assert math.isnan(v("receita", "A", "2023-12-31"))  # fato parcial (≪ 0,1% do ativo)
    # saldo em data avulsa (abertura IFRS 16; exercício sem fluxo) não vira período
    assert not (d["period_end"] == pd.Timestamp("2019-01-01")).any()
    assert not (d["period_end"] == pd.Timestamp("2023-12-31")).any()
    # contagem da capa vai para a data-base do 20-F (alinha com o exercício)
    sh = d[(d["item"] == "acoes_em_circulacao") & (d["freq"] == "A")]
    assert list(sh["period_end"]) == [pd.Timestamp("2025-12-31")]
    assert "capa (2026-03-20)" in sh["nota"].iloc[0]


def _doc_cvm(cnpj, dt_refer, ini, linhas_dre=(), linhas_dfc=()):
    base = [cnpj, dt_refer, 1, "SIMULADA", "099991", "DF Consolidado", "REAL", "MIL", "ÚLTIMO",
            ini, dt_refer]
    return {"cnpj": cnpj, "dt_refer": dt_refer, "ver": 1, "receb": "2026-03-10",
            "dre": [base + [cd, ds, f"{v:.4f}", "S"] for cd, ds, v in linhas_dre],
            "dfc": [base + [cd, ds, f"{v:.4f}", "S"] for cd, ds, v in linhas_dfc]}


def _fatos_zip(docs):
    conteudo = fx._zip_cvm("DFP", 2025, docs)
    return cvm.fatos_cvm(cvm.ler_zip_demonstracoes(conteudo, "DFP", 2025), "DFP")


def test_cvm_capex_ativo_de_contrato_biologico_e_alerta():
    util = _doc_cvm("33.333.333/0001-33", "2025-12-31", "2025-01-01", linhas_dfc=[
        ("6.01", "Caixa Líquido Atividades Operacionais", 7_163_000),
        ("6.02", "Caixa Líquido Atividades de Investimento", -5_300_000),
        ("6.02.01", "Aquisição de imobilizado", -370_000),
        ("6.02.03", "Adições de ativo contratual", -4_960_000),
        ("6.02.04", "Infraestrutura da transmissão - ativo contratual", -100_000),
        ("6.02.05", "Aplicações financeiras", -900_000),
        ("6.02.06", "Venda de imobilizado", 30_000)])
    papel = _doc_cvm("44.444.444/0001-44", "2025-12-31", "2025-01-01", linhas_dfc=[
        ("6.01", "Caixa Líquido Atividades Operacionais", 18_000_000),
        ("6.02.01", "Aquisições de imobilizado", -4_660_000),
        ("6.02.02", "Adições de ativos biológicos", -7_910_000),
        ("6.02.03", "Adições ao ativo (plantio e tratos)", -1_560_000)])
    alerta = _doc_cvm("55.555.555/0001-55", "2025-12-31", "2025-01-01", linhas_dfc=[
        ("6.01", "Caixa Líquido Atividades Operacionais", 100_000),
        ("6.02.01", "Aquisição de imobilizado", -1_000),
        ("6.02.02", "Aquisição de ativo operacional", -90_000)])
    f = _fatos_zip([util, papel, alerta]).set_index(["entidade", "item"])["value"]
    assert f[("33.333.333/0001-33", "capex")] == pytest.approx(5_430_000_000)
    assert f[("44.444.444/0001-44", "capex")] == pytest.approx(14_130_000_000)
    qa = _fatos_zip([util, papel, alerta]).attrs["qa"]
    assert [q["cnpj"] for q in qa] == ["55.555.555/0001-55"]
    assert "aquisicao de ativo operacional" in qa[0]["msg"]


def test_cvm_recompras_e_dividendos_mutuamente_exclusivos():
    doc = _doc_cvm("66.666.666/0001-66", "2025-12-31", "2025-01-01", linhas_dfc=[
        ("6.01", "Caixa Líquido Atividades Operacionais", 24_000_000),
        ("6.03.01", "Dividendos e juros sobre o capital próprio pagos", -20_464_000),
        ("6.03.02", "Empréstimos, financiamentos e títulos de dívida - amortizações / recompra",
         -13_160_000),
        ("6.03.03", "Proventos/(recompra) de ações", -1_861_000),
        ("6.03.04", "Recompra de cessão de recebíveis", -244_000),
        ("6.03.05", "Recompra de ações", -33_000)])
    f = _fatos_zip([doc]).set_index("item")["value"]
    assert f["dividendos_pagos"] == pytest.approx(20_464_000_000)
    assert f["recompras"] == pytest.approx((1_861_000 + 33_000) * 1000)


def test_cvm_controladores_com_zero_reservado():
    def dre(nci):
        linhas = [("3.01", "Receita de Venda de Bens e/ou Serviços", 10_000_000),
                  ("3.11", "Lucro/Prejuízo Consolidado do Período", 846_573),
                  ("3.11.01", "Atribuído a Sócios da Empresa Controladora", 0)]
        if nci is not None:
            linhas.append(("3.11.02", "Atribuído a Sócios Não Controladores", nci))
        return linhas

    com = _fatos_zip([_doc_cvm("77.777.777/0001-77", "2025-12-31", "2025-01-01", dre(-3_973))])
    sem = _fatos_zip([_doc_cvm("77.777.777/0001-77", "2025-12-31", "2025-01-01", dre(None))])
    v = com.set_index("item")["value"]
    assert v["lucro_liquido_controladores"] == pytest.approx(850_546_000)
    assert "lucro_liquido_controladores" not in set(sem["item"])  # nunca o consolidado


def test_yahoo_ebit_operacional_ebitda_por_codigo_e_da_da_dfc():
    q = fx._quadro
    doc = {"ticker": "X.SN", "demonstracoes": {
        "income_stmt": q(["2025-12-31", "2024-12-31"], {
            "Operating Income": [520.0, 500.0], "EBIT": [1940.0, 600.0],
            "EBITDA": [1940.0, 600.0], "Reconciled Depreciation": [6.0, 300.0]}),
        "cashflow": q(["2025-12-31", "2024-12-31"], {
            "Depreciation And Amortization": [None, 310.0],
            "Capital Expenditure": [-1000.0, -900.0]})}}
    f = yh.fatos_yahoo(doc, data_coleta=date(2026, 10, 1), financeira=False, moeda="CLP",
                       nota="moeda CLP")
    d = selecionar_pit(f.assign(fonte="YAHOO", sha256="s"), date(2026, 10, 1))
    a = d[d["freq"] == "A"].set_index(["item", "period_end"])
    assert a.loc[("ebit", pd.Timestamp("2025-12-31")), "value"] == 520.0
    assert "Operating Income" in a.loc[("ebit", pd.Timestamp("2025-12-31")), "documento"]
    assert a.loc[("d_a", pd.Timestamp("2024-12-31")), "value"] == 310.0  # DFC prevalece
    # D&A da DRE de 6 frente a capex de 1.000 (< 10%): parcial ⇒ ausente; EBITDA idem
    assert ("d_a", pd.Timestamp("2025-12-31")) not in a.index
    assert ("ebitda", pd.Timestamp("2025-12-31")) not in a.index
    assert a.loc[("ebitda", pd.Timestamp("2024-12-31")), "value"] == 500.0 + 310.0
    assert a.loc[("ebitda", pd.Timestamp("2024-12-31")), "nota"].startswith("calculado")


def test_consenso_moedas_por_tabela_e_proveniencia_do_info(base):
    c = yh.consenso_de({"info": {"currency": "USD", "financialCurrency": "MXN"}},
                       {"earnings_estimate": {"0y": {"avg": 1.0, "currency": "USD"}},
                        "revenue_estimate": {"0y": {"avg": 9.0e11, "currency": "MXN"}}})
    assert c["moeda_estimativas"] == "USD" and c["moeda_receita"] == "MXN"
    sem = yh.consenso_de({"info": {"financialCurrency": "MXN"}},
                         {"revenue_estimate": {"0y": {"avg": 1.0}}})
    assert sem["moeda_estimativas"] is None and sem["moeda_receita"] is None
    out = P.consenso_publico(["SIMU.MX"], base["as_of"], offline=True, root=base["root"])
    arq = pa.Arquivo(base["root"], offline=True)
    r = out.iloc[0]
    assert r["sha256_info"] == arq.buscar("YAHOO/info/SIMU.MX.json").sha256
    assert r["sha256"] == arq.buscar("YAHOO/estimativas/SIMU.MX.json").sha256
    assert pd.notna(r["data_coleta_info"])


def _linhas(iid, item, serie, freq="Q", documento="SEC 20-F x (t)"):
    return [{"issuer_id": iid, "item": item, "freq": freq, "period_end": pd.Timestamp(d),
             "value": v, "documento": documento, "nota": None} for d, v in serie]


def test_qa_acoes_outlier_desdobramento_bases_e_unidade():
    ok = [("2024-12-31", 5.43e9), ("2025-03-31", 5.43e9), ("2025-06-30", 5.43e9),
          ("2025-09-30", 5.43e9), ("2025-12-31", 54.3e9), ("2026-03-31", 5.43e9)]
    split = [("2024-12-31", 1.0e9), ("2025-03-31", 1.0e9), ("2025-06-30", 10.0e9),
             ("2025-09-30", 10.0e9), ("2025-12-31", 10.1e9)]
    ultimo = [("2025-06-30", 409e6), ("2025-09-30", 409e6), ("2025-12-31", 2.244e9)]
    out = pd.DataFrame(
        _linhas("A", "acoes_em_circulacao", ok) + _linhas("B", "acoes_em_circulacao", split)
        + _linhas("C", "acoes_em_circulacao", ultimo)
        + _linhas("D", "acoes_em_circulacao", [("2025-12-31", 17.89e9)])
        + _linhas("D", "acoes_emitidas", [("2025-12-31", 3.58e9)])
        + _linhas("E", "acoes_em_circulacao", [("2025-12-31", 99e6)],
                  documento="DFP 2025-12-31 v1 (ações: unidade na)")
        + _linhas("E", "patrimonio_liquido", [("2025-12-31", 400e9)])  # PL/ação R$ 4.040
        + _linhas("F", "acoes_em_circulacao", [("2025-12-31", 11.4e9)],
                  documento="ITR 2025-12-31 v1 (ações: unidade na)")
        + _linhas("F", "patrimonio_liquido", [("2025-12-31", 60e9)])  # PL/ação R$ 5,26
        + _linhas("G", "acoes_em_circulacao", [("2025-12-31", 1.0e9)])
        + _linhas("G", "acoes_emitidas", [("2025-12-31", 0.997e9)]))  # só data: mantém
    qa: list[str] = []
    r = P._qa_acoes(out, qa).set_index(["issuer_id", "item", "period_end"])

    def v(i, d, item="acoes_em_circulacao"):
        return r.loc[(i, item, pd.Timestamp(d)), "value"]

    assert math.isnan(v("A", "2025-12-31")) and v("A", "2026-03-31") == 5.43e9
    assert r.loc[("A", "acoes_em_circulacao", pd.Timestamp("2025-12-31")),
                 "nota"].startswith("conferência:")
    assert v("B", "2025-06-30") == 10.0e9 and v("B", "2025-12-31") == 10.1e9  # novo patamar
    assert math.isnan(v("C", "2025-12-31"))  # última contagem sem confirmação: ausente
    assert math.isnan(v("D", "2025-12-31")) and math.isnan(v("D", "2025-12-31", "acoes_emitidas"))
    assert math.isnan(v("E", "2025-12-31"))  # unidade sem LPA e PL/ação implausível
    assert v("F", "2025-12-31") == 11.4e9  # unidade conferida pelo PL por ação
    assert "conferida pelo PL" in r.loc[("F", "acoes_em_circulacao", pd.Timestamp("2025-12-31")),
                                         "nota"]
    assert v("G", "2025-12-31", "acoes_emitidas") == 0.997e9
    assert len(qa) >= 4


def test_qa_magnitude_e_escala_de_documento():
    serie = [("2022-12-31", 5e9), ("2023-12-31", 9_259.0), ("2024-12-31", 6e9),
             ("2025-12-31", 70e9)]
    out = pd.DataFrame(_linhas("AR_X", "d_a", serie, freq="A"))
    qa: list[str] = []
    r = P._qa_magnitude(out, qa).set_index("period_end")["value"]
    assert math.isnan(r[pd.Timestamp("2023-12-31")])
    assert r[pd.Timestamp("2025-12-31")] == 70e9  # salto de 11,7×: só alerta
    assert any("salto" in q for q in qa)
    # documento da CVM com escala errada (ativo total 1.000× menor) ⇒ valores descartados
    linhas = []
    for doc, at in (("ITR 2024-03-31 v1", 9e9), ("ITR 2024-06-30 v1", 9e6),
                    ("ITR 2024-09-30 v1", 9.1e6), ("DFP 2024-12-31 v1", 9.2e9),
                    ("ITR 2025-03-31 v1", 9.3e9), ("ITR 2025-06-30 v1", 9.4e9)):
        for item, val in (("ativo_total", at), ("receita", at / 10)):
            linhas.append({"entidade": "C", "item": item, "documento": doc, "value": val,
                           "currency": "BRL", "received_date": pd.Timestamp("2025-08-01")})
    linhas.append({"entidade": "C", "item": "acoes_em_circulacao", "documento":
                   "ITR 2024-06-30 v1 (ações: unidade ok)", "value": 1e8, "currency": None,
                   "received_date": pd.Timestamp("2025-08-01")})
    qa2: list[str] = []
    f = P._qa_escala_documentos(pd.DataFrame(linhas), {"C": ["BR_PINE"]}, qa2)
    docs = set(f.loc[f["currency"].notna(), "documento"])
    assert "ITR 2024-06-30 v1" not in docs and "ITR 2024-09-30 v1" not in docs
    assert "DFP 2024-12-31 v1" in docs and (f["item"] == "acoes_em_circulacao").any()
    assert len(qa2) == 2 and all(q.startswith("BR_PINE:") for q in qa2)


def _base(rows):
    cols = ["issuer_id", "item", "freq", "period_end", "value", "currency", "nota"]
    return pd.DataFrame([dict(zip(cols, r, strict=True)) for r in rows])


def test_complemento_magnitude_moeda_saldos_e_acoes():
    t = pd.Timestamp
    base = _base([
        ("X", "receita", "A", t("2024-12-31"), 1000.0, "USD", None),
        ("X", "ativo_total", "A", t("2024-12-31"), 5000.0, "USD", None),
        ("X", "ativo_total", "Q", t("2025-06-30"), 5100.0, "USD", None),
        ("X", "d_a", "A", t("2024-12-31"), 342.0, "USD", None),
        ("X", "acoes_em_circulacao", "A", t("2024-12-31"), 17.89e9, None, None)])
    yahoo = _base([
        ("X", "receita", "A", t("2024-12-31"), 1010.0, "USD", "m"),
        ("X", "receita", "Q", t("2025-06-30"), 260.0, "USD", "m"),
        ("X", "ativo_total", "A", t("2025-06-30"), 5300.0, "USD", "m"),  # saldo já existe (Q)
        ("X", "d_a", "A", t("2025-12-31"), 5.955, "USD", "m"),             # D&A parcial
        ("X", "acoes_em_circulacao", "Q", t("2025-06-30"), 3.46e9, None, "m"),
        ("X", "fcf", "Q", t("2025-06-30"), 50.0, "USD", "calculado: cfo − capex")])
    qa: list[str] = []
    c = P._complemento(base, yahoo, "X", qa)
    assert set(zip(c["item"], c["freq"], strict=True)) == {("receita", "Q")}
    assert c["nota"].iloc[0].startswith("complemento Yahoo") and c["nota"].iloc[0].endswith("m")
    # magnitude incompatível (Yahoo em outra unidade): nada entra
    mil = yahoo.assign(value=yahoo["value"] * 1000)
    assert P._complemento(base, mil, "X", qa) is None
    assert any("magnitude incompatível" in q for q in qa)
    # IAS 29: emissor em ARS não recebe valores monetários do Yahoo; contagens de ações (sem
    # moeda) só quando a fonte oficial não tem a contagem em circulação
    ars = base.assign(currency=base["currency"].map(lambda c: "ARS" if c else c))
    assert P._complemento(ars, yahoo.assign(currency="ARS"), "X", qa) is None
    so_tes = ars[ars["item"] != "acoes_em_circulacao"]
    c2 = P._complemento(so_tes, yahoo.assign(currency=yahoo["currency"].map(
        lambda c: "ARS" if c else c)), "X", qa)
    assert list(c2["item"]) == ["acoes_em_circulacao"]


def test_derivados_refeitos_depois_do_complemento():
    t = pd.Timestamp("2024-12-31")
    meta = {"issuer_id": "X", "entidade": "1", "freq": "A", "period_end": t, "currency": "MXN",
            "consolidado": True, "fonte": "SEC", "url": None, "documento": "d",
            "data_publicacao": date(2025, 4, 1), "sha256": "s", "pit_estimado": False,
            "escala": 1}
    out = pd.DataFrame([
        {**meta, "item": "divida_bruta", "value": 144.4, "demonstrativo": "BP", "nota": None},
        {**meta, "item": "caixa", "value": 139.8, "demonstrativo": "BP", "nota": None},
        {**meta, "item": "divida_liquida", "value": 4.6, "demonstrativo": "BP",
         "nota": "calculado: divida_bruta − caixa (aplicações de curto prazo não informadas)"},
        {**meta, "item": "aplicacoes_cp", "value": 43.2, "demonstrativo": "BP",
         "fonte": "YAHOO", "nota": "complemento Yahoo Finance"}])
    r = P._refazer_derivados(out)
    dl = r[r["item"] == "divida_liquida"]
    assert len(dl) == 1 and dl["value"].iloc[0] == pytest.approx(144.4 - 139.8 - 43.2)


def test_ttm_com_base_mista_nao_e_consolidado():
    linhas = []
    for fim, ini, cons in (("2024-06-30", "2024-04-01", False), ("2024-09-30", "2024-07-01", False),
                           ("2024-12-31", "2024-10-01", True), ("2025-03-31", "2025-01-01", True)):
        linhas.append({"entidade": "P", "demonstrativo": "DRE", "item": "receita",
                       "period_start": pd.Timestamp(ini), "period_end": pd.Timestamp(fim),
                       "value": 100.0, "currency": "BRL", "received_date": pd.Timestamp("2025-05-10"),
                       "version": 1, "documento": "d", "url": None, "consolidado": cons,
                       "anual": False, "fonte": "CVM", "sha256": "s"})
    d = selecionar_pit(pd.DataFrame(linhas), date(2025, 6, 1))
    ttm = d[(d["freq"] == "TTM") & (d["period_end"] == pd.Timestamp("2025-03-31"))].iloc[0]
    assert ttm["value"] == 400.0 and not ttm["consolidado"]
    assert "base mista" in ttm["nota"]


# ----------------------------------------------------------------- arquivo, coleta, segredos

def test_arquivo_registro_incompleto_no_fim_e_pasta_pela_data_local(tmp_path):
    t0 = datetime(2026, 10, 10, 1, 30, tzinfo=UTC)  # 22h30 de 09/10 em São Paulo
    arq = pa.Arquivo(tmp_path, agora=lambda: t0)
    r = arq.gravar("FRED/DGS10/a.csv", "FRED", None, b"x")
    assert r.caminho == "FRED/DGS10/2026-10-09/a.csv"
    with open(tmp_path / "publico" / "indice.jsonl", "a", encoding="utf-8") as fh:
        fh.write('{"chave": "FRED/DGS10/b.csv", "fon')  # gravação interrompida
    novo = pa.Arquivo(tmp_path, agora=lambda: t0)
    assert novo.buscar("FRED/DGS10/a.csv") is not None and novo.falhas
    novo.gravar("FRED/DGS10/c.csv", "FRED", None, b"y")
    linhas = (tmp_path / "publico" / "indice.jsonl").read_text().splitlines()
    assert len(linhas) == 2 and all(json.loads(x) for x in linhas)
    assert pa.Arquivo(tmp_path, offline=True).buscar("FRED/DGS10/c.csv") is not None
    # linha ilegível no meio continua sendo adulteração
    (tmp_path / "publico" / "indice.jsonl").write_text("lixo\n" + "\n".join(linhas) + "\n")
    with pytest.raises(pa.ArquivoAdulterado):
        pa.Arquivo(tmp_path, offline=True).registros()


def test_retrato_nao_e_baixado_para_data_passada(tmp_path):
    # rotina de sexta (09/10) reexecutada no sábado: o retrato baixado hoje seria invisível
    # na releitura de 09/10 — não baixa, registra
    agora = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    arq = pa.Arquivo(tmp_path, agora=lambda: agora)
    got = arq.obter("YAHOO/estimativas/X.json", "YAHOO", None, _sem_rede, ate=date(2026, 10, 9),
                    max_idade_dias=1.0, instantaneo=True)
    assert got is None and any("retrato não coletado" in f for f in arq.falhas)
    # no próprio dia (São Paulo), mesmo depois da meia-noite UTC, baixa e a releitura vê
    noite = datetime(2026, 10, 10, 1, 30, tzinfo=UTC)
    arq2 = pa.Arquivo(tmp_path, agora=lambda: noite)
    assert arq2.obter("YAHOO/estimativas/X.json", "YAHOO", None, lambda: b'{"ticker": "X"}',
                      ate=date(2026, 10, 9), instantaneo=True) is not None
    assert pa.Arquivo(tmp_path, offline=True).obter(
        "YAHOO/estimativas/X.json", "YAHOO", None, _sem_rede, ate=date(2026, 10, 9),
        instantaneo=True) is not None


class _TickerLimitado:
    def __getattr__(self, nome):
        raise RuntimeError("Too Many Requests. Rate limited.")

    def get_earnings_dates(self, limit=16):
        raise RuntimeError("Too Many Requests. Rate limited.")


class _TickerParcial:
    earnings_estimate = pd.DataFrame({"avg": [1.0]}, index=["0y"])
    analyst_price_targets = {"mean": 10.0}

    @property
    def revenue_estimate(self):
        raise RuntimeError("Too Many Requests. Rate limited.")


def test_yahoo_falha_de_consulta_nunca_vira_ausencia_de_cobertura(tmp_path):
    def nada(_s):
        return None

    for parte in ("estimativas", "calendario", "demonstracoes"):
        with pytest.raises(ValueError, match="falharam"):
            yh.coletar_parte("X.MX", parte, factory=lambda t: _TickerLimitado(), sleep=nada)
    arq = pa.Arquivo(tmp_path, agora=lambda: datetime(2026, 10, 9, 23, tzinfo=UTC))
    assert arq.obter("YAHOO/estimativas/X.MX.json", "YAHOO", None,
                     lambda: yh.coletar_parte("X.MX", "estimativas",
                                              factory=lambda t: _TickerLimitado(), sleep=nada),
                     ate=date(2026, 10, 9), instantaneo=True, validar=yh.ler_json) is None
    assert arq.falhas and arq.buscar("YAHOO/estimativas/X.MX.json") is None
    doc = json.loads(yh.coletar_parte("X.MX", "estimativas",
                                      factory=lambda t: _TickerParcial(), sleep=nada))
    assert doc["earnings_estimate"]["0y"]["avg"] == 1.0
    assert "revenue_estimate" in doc["erros"] and doc["revenue_estimate"] is None


def test_efts_e_banxico_invalidos_nao_sao_arquivados_e_token_fora_do_endereco(base, tmp_path,
                                                                                monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    arq = pa.Arquivo(tmp_path / "efts")
    html = b"<html><body>Your request has been rate limited</body></html>"
    m = P._cik_map(arq, base["universo"], date(2026, 10, 9), lambda u, h: html)
    assert m.empty and arq.chaves("SEC/efts") == [] and arq.falhas
    token = "a" * 48
    monkeypatch.setenv("BANXICO_TOKEN", token)
    vistos: list[tuple[str, dict]] = []

    def http(url, headers):
        vistos.append((url, dict(headers)))
        if "banxico" in url:
            return b"<html>Servicio no disponible</html>"
        if "fred" in url:
            return fx.FRED.encode()
        if "bcdata.sgs.432" in url:
            return json.dumps(fx.SGS432).encode()
        if "bcdata.sgs" in url:
            return json.dumps(fx.SGS13522).encode()
        return json.dumps(fx.FOCUS_IPCA, ensure_ascii=False).encode()

    raiz = tmp_path / "taxas"
    t = P.taxas_publicas(date(2026, 10, 9), root=raiz, http_get=http)  # não levanta
    assert "USD_10Y" in set(t["serie"])
    assert pa.Arquivo(raiz, offline=True).chaves("BANXICO") == []
    bx = [(u, h) for u, h in vistos if "banxico" in u]
    assert bx and all(token not in u and h.get("Bmx-Token") == token for u, h in bx)
    assert not any(token in f for f in t.attrs["falhas"])
    assert token not in (raiz / "publico" / "indice.jsonl").read_text()
    from cdp.data.security_master import HttpError

    def falha(url, headers):
        raise HttpError(503, url + "?token=" + token, "indisponível")

    arq2 = pa.Arquivo(tmp_path / "t2")
    arq2.obter("BANXICO/x/x.json", "BANXICO", None, lambda: falha("https://banxico/x", {}),
               ate=date(2026, 10, 9))
    assert arq2.falhas and not any(token in f for f in arq2.falhas)


def test_pacote_simulado_nunca_e_lido_num_arquivo_real(tmp_path):
    from cdp.data.publico_sintetico import gerar_arquivo_sintetico
    from cdp.data.synthetic import make_synthetic_market

    md = make_synthetic_market(seed=7, as_of=date(2026, 10, 9))
    fx.construir_arquivo(tmp_path)  # arquivo com fontes reais (formatos reais)
    with pytest.raises(ValueError, match="fontes reais"):
        gerar_arquivo_sintetico(tmp_path, md)
    # mesmo um pacote gravado à mão num arquivo real é ignorado (com registro)
    arq = pa.Arquivo(tmp_path)
    arq.gravar("SIMULADO/pacotes/free_float.json", "SIMULADO", None,
               json.dumps({"aviso": "DADOS SIMULADOS", "linhas": [
                   {"issuer_id": "BR_SIMU", "free_float_pct": 0.99}]}).encode())
    ff = P.free_float(["BR_SIMU"], date(2026, 10, 9), offline=True, root=tmp_path,
                      universe=fx.universo())
    assert ff["fonte"].iloc[0] == "CVM"
    assert any("SIMULADO ignorados" in f for f in ff.attrs["falhas"])


def test_etf_falhas_e_motivo_quando_indisponivel(base):
    assert P.composicao_etf("EWZ", base["as_of"], offline=True, root=base["root"]) is None
    assert any("não disponível" in m for m in P.FALHAS_ETF["EWZ"])
    assert P.composicao_etf("XYZ", base["as_of"], offline=True, root=base["root"]) is None
    assert P.FALHAS_ETF["XYZ"]
    ilf = P.composicao_etf("ILF", base["as_of"], offline=True, root=base["root"])
    assert ilf.attrs["falhas"] == [] and P.FALHAS_ETF["ILF"] == []


def test_etf_classes_do_mesmo_emissor_por_nome():
    linhas = pd.DataFrame({"issuer_id": ["CO_GRUPOARGOS", "CO_SURA", "AR_TEO"],
                           "issuer_name": ["Grupo Argos", "Grupo Sura", "Telecom Argentina"]},
                          index=["GRUPOARGOS.CL", "GRUPOSURA.CL", "TEO"])
    df = pd.DataFrame({"ticker_bruto": ["GRUPOARG CB", "PFGRUPOA CB", "PFGRUPSU CB",
                                        "GRUPOSUR CB", "ENTEL CI"],
                       "nome": ["GRUPO ARGOS SA", "GRUPO ARGOS SA/COLOMBIA",
                                "GRUPO DE INVERSIONES SURA", "GRUPO DE INV SURAMERICANA",
                                "EMPRESA NACIONAL DE TELECOMUNICACIONES"],
                       "classe_ativo": "Equity", "bolsa": None, "peso": 0.1})
    m = etfm.mapear(df, "COLO", "ISHARES", linhas, None).set_index("ticker_bruto")
    assert m.loc["GRUPOARG CB", "issuer_id"] == "CO_GRUPOARGOS"
    assert m.loc["PFGRUPOA CB", "issuer_id"] == "CO_GRUPOARGOS"
    assert m.loc["GRUPOSUR CB", "issuer_id"] == "CO_SURA"
    assert pd.isna(m.loc["ENTEL CI", "issuer_id"])  # "telecom" ⊄ outra empresa
    assert (m.loc[["GRUPOARG CB", "GRUPOSUR CB"], "mapeamento"] == "nome").all()


# ----------------------------------------------------------------- mestre, datas, eventos

def _fca_zip(cnpjs_codigos, ano):
    vm = fx._csv(["CNPJ_Companhia", "Data_Referencia", "Versao", "Nome_Empresarial",
                  "Valor_Mobiliario", "Sigla_Classe_Acao_Preferencial", "Codigo_Negociacao",
                  "Composicao_BDR_Unit", "Mercado", "Data_Inicio_Negociacao",
                  "Data_Fim_Negociacao", "Segmento"],
                 [[c, f"{ano}-01-01", 1, "X", "Ações Ordinárias" if cod.endswith("3") else
                   "Ações Preferenciais", "" if cod.endswith("3") else "PN", cod, "", "Bolsa",
                   "2010-01-01", "", "Novo Mercado"] for c, cod in cnpjs_codigos])
    return fx._zip({f"fca_cia_aberta_valor_mobiliario_{ano}.csv": vm})


def test_mestre_une_fca_do_ano_anterior_e_identificadores_curados(tmp_path, monkeypatch):
    arq = pa.Arquivo(tmp_path)
    quando = datetime(2026, 2, 1, 12, tzinfo=UTC)
    arq.gravar("CVM/FCA/fca_cia_aberta_2025.zip", "CVM", None,
               _fca_zip([(fx.CNPJ_IND, "SIMU3"), (fx.CNPJ_BANCO, "BSIM4")], 2025),
               data_coleta=quando)
    arq.gravar("CVM/FCA/fca_cia_aberta_2026.zip", "CVM", None,
               _fca_zip([(fx.CNPJ_BANCO, "BSIM4")], 2026), data_coleta=quando)
    sm = P.mestre_publico(date(2026, 2, 1), offline=True, root=tmp_path, universe=fx.universo())
    assert sm.loc["BR_SIMU", "cnpj"] == fx.CNPJ_IND  # só no FCA de 2025
    assert sm.loc["BR_BSIM", "cnpj"] == fx.CNPJ_BANCO
    monkeypatch.setitem(P.IDENTIFICADORES_CURADOS, "MX_SIMU", {"cnpj": "99.999.999/0001-99"})
    sm2 = P.mestre_publico(date(2026, 2, 1), offline=True, root=tmp_path, universe=fx.universo())
    assert sm2.loc["MX_SIMU", "cnpj"] == "99.999.999/0001-99"
    assert P.IDENTIFICADORES_CURADOS["BR_MBRF"]["cnpj"] == "03.853.896/0001-40"


def test_hoje_e_data_de_coleta_no_fuso_de_sao_paulo(base, monkeypatch):
    monkeypatch.setattr("cdp.data.publico.agora_utc",
                        lambda: datetime(2026, 10, 10, 1, 30, tzinfo=UTC))
    assert P._hoje() == date(2026, 10, 9)
    # rotina das 22h30 BRT de 30/10 (01h30 UTC de 31/10): o trimestre de 30/09 divulgado em
    # 22/10 entra em as_of = 30/10 (data estimada limitada à data local da coleta)
    doc = fx.yahoo_partes()["SIMU.MX"]["demonstracoes"]
    q = doc["demonstracoes"]["quarterly_income_stmt"]
    q["colunas"] = ["2026-09-30"] + q["colunas"]
    q["linhas"] = {k: [v[0]] + v for k, v in q["linhas"].items()}
    pa.Arquivo(base["root"]).gravar("YAHOO/demonstracoes/SIMU.MX.json", "YAHOO", None,
                                    (json.dumps(doc, sort_keys=True) + "\n").encode(),
                                    data_coleta=datetime(2026, 10, 31, 1, 30, tzinfo=UTC))
    d = _dem(base, ["MX_SIMU"], as_of=date(2026, 10, 30))
    r = d[(d["item"] == "receita") & (d["freq"] == "Q")]
    assert r["period_end"].max() == pd.Timestamp("2026-09-30")
    assert r.sort_values("period_end")["data_publicacao"].iloc[-1] == date(2026, 10, 30)


def _ev(base, ids, desde, ate, as_of):
    return P.eventos_corporativos(ids, desde, ate, offline=True, root=base["root"],
                                  universe=base["universo"], http_get=_sem_rede,
                                  yf_factory=_sem_rede, as_of=as_of)


def test_eventos_quem_ja_divulgou_nao_ganha_data_estimada(base):
    # chamada do veto de risco: [semana, semana + 45]; BR_SIMU divulgou o 3T em 06/11
    # (calendário da CVM) e MX_SIMU em 22/10 — nenhum ganha um "resultado estimado" falso
    for semana in (date(2026, 11, 13), date(2026, 10, 30)):
        ev = _ev(base, ["BR_SIMU", "MX_SIMU"], semana, semana + timedelta(days=45), semana)
        res = ev[ev["tipo"] == "resultado"]
        assert not res["estimada"].any(), res
    # trimestre sem nenhuma data conhecida continua estimado (fim do trimestre + 50 dias)
    ev = _ev(base, ["BR_BSIM"], date(2026, 11, 13), date(2026, 12, 28), date(2026, 11, 13))
    r = ev[ev["tipo"] == "resultado"]
    assert len(r) == 1 and r["estimada"].item()
    assert r["data"].item() == date(2026, 9, 30) + timedelta(days=50)
    assert "sem data conhecida para o trimestre" in r["documento"].item()


def test_eventos_janela_de_tres_anos_e_calendario_entregue_no_ano_anterior(base):
    # janela do motor de cobertura (ano anterior ao seguinte): o calendário do ano corrente
    # continua lido
    as_of = base["as_of"]
    ev = _ev(base, ["BR_SIMU"], date(2025, 10, 1), date(2027, 10, 28), as_of)
    r = ev[(ev["tipo"] == "resultado") & (ev["data"] == date(2026, 11, 6))]
    assert len(r) == 1 and not r["estimada"].item() and "calendário" in r["documento"].item()
    # semana de janeiro: o calendário de 2026 (v1) foi entregue em dez/2025 (IPE de 2025)
    jan = date(2026, 1, 5)
    ev = _ev(base, ["BR_SIMU"], jan, date(2026, 3, 31), jan)
    dfp = ev[ev["tipo"] == "resultado"]
    assert list(dfp["data"]) == [date(2026, 3, 12)] and not dfp["estimada"].any()
