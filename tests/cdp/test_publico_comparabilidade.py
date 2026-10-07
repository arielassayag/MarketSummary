"""Receita reportada e comparabilidade: trechos reais CVM + casos DADOS SIMULADOS.

Os CSVs públicos de HAPVIDA são trechos de fontes primárias com proveniência e hashes;
preços, universo de integração e cenários econômicos auxiliares são DADOS SIMULADOS.
Nenhum teste consulta a rede nem grava o livro.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from cdp.cobertura.fontes import alertas_de_attrs, coletar
from cdp.cobertura.formato import r6
from cdp.cobertura.insumos import Demonstrativos, _prov_linha, preparar
from cdp.cobertura.parametros import carregar_parametros
from cdp.data import publico as P
from cdp.data.publico_arquivo import Arquivo
from cdp.data.publico_cvm import fatos_cvm, ler_zip_demonstracoes
from cdp.data.publico_fatos import selecionar_pit
from cdp.data.synthetic import make_synthetic_market

FIX = Path(__file__).resolve().parents[1] / "fixtures/publico/comparabilidade"
META = json.loads((FIX / "proveniencia.json").read_text())
D = date(2026, 10, 7)


def _zip_trechos(fonte, cnpj=None):
    """Reempacota somente os trechos publicados; mantém campos e valores literais."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for trecho in fonte["trechos"]:
            raw = (FIX / trecho["arquivo"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == trecho["sha256"]
            df = pd.read_csv(io.BytesIO(raw), sep=";", dtype=str)
            if cnpj:
                df["CNPJ_CIA"] = cnpj  # cenário explicitamente SIMULADO de outro emissor
            z.writestr(trecho["membro"], df.to_csv(index=False, sep=";").encode("latin1"))
    return b.getvalue()


def _fatos_reais(cnpj=None):
    partes = []
    for fonte in META["fontes"]:
        raw = _zip_trechos(fonte, cnpj)
        f = fatos_cvm(ler_zip_demonstracoes(raw, fonte["doc"], fonte["ano"]), fonte["doc"])
        partes.append(f.assign(fonte="CVM", sha256=fonte["sha256_zip"]))
    return pd.concat(partes, ignore_index=True)


def _fato(inicio, fim, valor, conceito="receita_dre", recebido=None, **kw):
    return dict(entidade="SIMULADO", item="receita", demonstrativo="DRE",
                period_start=inicio, period_end=fim, value=valor, currency="BRL",
                received_date=recebido or (pd.Timestamp(fim) + pd.Timedelta(days=40)).date(),
                version=1, documento=f"DADOS SIMULADOS {inicio}/{fim}",
                url="https://example.test/simulado", consolidado=True,
                anual=fim.endswith("12-31"), fonte="SIMULADO", sha256="s" * 64,
                semantica_fluxo=conceito, rubrica_reportada="DADOS SIMULADOS 3.01", **kw)


def _canonico(rows, as_of=D):
    return selecionar_pit(pd.DataFrame(rows), as_of)


def test_fonte_real_preserva_rubrica_valor_sinal_e_classifica_por_identidade():
    f = _fatos_reais()
    receita = f[f.item.eq("receita")]
    anual = receita[receita.anual].iloc[0]
    assert anual.value == 31_577_240_000
    assert anual.semantica_fluxo == "receita_dre"
    assert anual.rubrica_reportada == "3.01: Receita de Venda de Bens e/ou Serviços"
    h1 = receita[(receita.period_start == pd.Timestamp("2026-01-01"))
                 & (receita.period_end == pd.Timestamp("2026-06-30"))].iloc[0]
    assert h1.value == 2_610_617_000
    assert h1.semantica_fluxo == "resultado_liquido_seguros"
    assert h1.received_date == pd.Timestamp("2026-08-12")
    # A regra depende de contas/identidade, não do nome, CNPJ ou ano do emissor.
    simulado = _fatos_reais("99.999.999/0001-99")
    assert list(simulado.semantica_fluxo) == list(f.semantica_fluxo)
    assert list(simulado.value) == list(f.value)


def test_real_ttm_misto_recusado_q_reportado_e_anual_original_preservados():
    s = selecionar_pit(_fatos_reais(), D)
    r = s[s.item.eq("receita")]
    t = r[r.freq.eq("TTM")]
    assert list(t.period_end) == [pd.Timestamp("2025-12-31")]
    assert t.iloc[0].value == 31_577_240_000
    assert t.iloc[0].data_publicacao == pd.Timestamp("2026-03-18")
    assert t.iloc[0].sha256 == META["fontes"][0]["sha256_zip"]
    assert "fallback" in t.iloc[0].nota
    q = r[(r.freq == "Q") & (r.period_end == pd.Timestamp("2026-06-30"))].iloc[0]
    assert q.value == 1_218_855_000 and q.data_publicacao == pd.Timestamp("2026-08-12")
    assert "semantica_fluxo=resultado_liquido_seguros" in q.nota
    alerta = s.attrs["incompatibilidades_fluxos"][0]["motivo"]
    assert "2026-06-30" in alerta and "2026-03-31" in alerta
    dem = Demonstrativos(s.rename(columns={"entidade": "issuer_id"}), META["cnpj"])
    valor, row = dem.valor("receita")
    assert valor == 31_577_240_000 and row.period_end == pd.Timestamp("2025-12-31")
    # Sem marcador, o caminho legado recompõe o valor misto: regressão econômica explícita.
    legado = s.rename(columns={"entidade": "issuer_id"}).assign(nota=None)
    errado, _ = Demonstrativos(legado, META["cnpj"]).valor("receita")
    assert errado == 18_422_788_000 and errado != valor


def test_caminho_inteiro_provedor_canonico_preparar_fallback_e_alerta(tmp_path, monkeypatch):
    def sem_rede(*a, **kw):
        raise AssertionError("rede proibida no teste offline")

    md = make_synthetic_market(as_of=D)
    iid = next(i for i in md.universe.issuers.index
               if md.universe.issuers.loc[i, "country"] == "BR"
               and md.universe.issuers.loc[i, "gics_sector"] != "Financials")
    params = carregar_parametros()
    dados = coletar(md, D, [iid], list(md.universe.lines_for(iid).index), [])
    monkeypatch.setattr(P, "mestre_publico", lambda *a, **kw: pd.DataFrame(
        {"cnpj": [META["cnpj"]], "cik": [None]}, index=[iid]))
    arq = Arquivo(tmp_path, agora=lambda: datetime(2026, 10, 7, tzinfo=UTC))
    for fonte in META["fontes"]:
        doc, ano = fonte["doc"], fonte["ano"]
        arq.gravar(f"CVM/{doc}/{doc.lower()}_cia_aberta_{ano}.zip", "CVM", fonte["url"],
                   _zip_trechos(fonte))
    publico = P.demonstrativos([iid], D, root=tmp_path, offline=True, universe=md.universe,
                               http_get=sem_rede, yf_factory=sem_rede, complementar_yahoo=False)
    assert any("comparabilidade: receita" in x for x in publico.attrs["qa"])
    demonstrativos = pd.concat([dados.demonstrativos[dados.demonstrativos.item.ne("receita")],
                               publico], ignore_index=True)
    dados = replace(dados, demonstrativos=demonstrativos, alertas=alertas_de_attrs(publico.attrs))
    pacote = preparar(md, dados, params, [iid], D)[iid]
    assert pacote["t.receita"] == r6(31_577_240_000)
    assert pacote["fontes"]["t.receita"]["data_publicacao"] == "2026-03-18"
    assert any("comparabilidade: receita" in x["texto"] for x in pacote["alertas_fonte"])
    assert not ((publico.freq == "TTM") & (publico.period_end == pd.Timestamp("2026-06-30"))).any()


@pytest.mark.parametrize("conceito", ["resultado_liquido_seguros", None,
                                      "seguros_composicao_nao_conciliada"])
def test_semestre_misto_nao_cruza_conceitos_ou_ausencia(conceito):
    rows = [_fato("2025-01-01", "2025-12-31", 100),
            _fato("2025-01-01", "2025-06-30", 45),
            _fato("2026-01-01", "2026-06-30", 7, conceito)]
    s = _canonico(rows)
    assert not ((s.freq == "TTM") & (s.period_end == pd.Timestamp("2026-06-30"))).any()
    dem = Demonstrativos(s.rename(columns={"entidade": "issuer_id"}), "SIMULADO")
    v, r = dem.valor("receita")
    assert v == 100 and r.period_end == pd.Timestamp("2025-12-31")
    assert s.attrs["incompatibilidades_fluxos"]


def test_trimestre_por_diferenca_de_acumulados_nao_cruza_quebra():
    s = _canonico([_fato("2026-01-01", "2026-03-31", 20),
                   _fato("2026-01-01", "2026-06-30", 5, "resultado_liquido_seguros")])
    assert not ((s.freq == "Q") & (s.period_end == pd.Timestamp("2026-06-30"))).any()
    assert s.attrs["incompatibilidades_fluxos"]


def test_reapresentacao_homogenea_so_e_usada_depois_da_publicacao_maxima():
    rows = [_fato("2025-01-01", "2025-12-31", 100),
            _fato("2025-01-01", "2025-06-30", 45, "resultado_liquido_seguros"),
            _fato("2026-01-01", "2026-06-30", 7, "resultado_liquido_seguros"),
            _fato("2025-01-01", "2025-12-31", 10, "resultado_liquido_seguros",
                  recebido="2026-09-01")]
    antes = _canonico(rows, date(2026, 8, 31))
    assert not ((antes.freq == "TTM") & (antes.period_end == pd.Timestamp("2026-06-30"))).any()
    depois = _canonico(rows)
    t = depois[(depois.freq == "TTM") & (depois.period_end == pd.Timestamp("2026-06-30"))].iloc[0]
    assert t.value == 7 + 10 - 45
    assert t.data_publicacao == pd.Timestamp("2026-09-01")
    assert not depois.attrs["incompatibilidades_fluxos"]


@pytest.mark.parametrize("faltante", ["receita", "despesa", "conciliacao"])
def test_seguros_sem_composicao_publicada_conciliada_nao_sao_rotulados_liquidos(faltante):
    fonte = META["fontes"][2]
    tabs = ler_zip_demonstracoes(_zip_trechos(fonte), "ITR", 2026)
    dre = tabs["DRE_con"].copy()
    if faltante == "receita":
        dre = dre[dre.CD_CONTA.ne("3.01.01")]
    elif faltante == "despesa":
        dre.loc[dre.CD_CONTA.eq("3.01.02"), "CD_CONTA"] = "3.02.01"
    else:
        dre.loc[dre.CD_CONTA.eq("3.01"), "VL_CONTA"] = "999"
    tabs["DRE_con"] = dre
    r = fatos_cvm(tabs, "ITR").query("item == 'receita'")
    assert not r.semantica_fluxo.eq("resultado_liquido_seguros").any()
    if faltante == "conciliacao":
        assert r.semantica_fluxo.eq("seguros_composicao_nao_conciliada").all()
        s = selecionar_pit(r.assign(fonte="CVM", sha256="x" * 64), D)
        assert not s.freq.eq("TTM").any()


def test_conceito_homogeneo_preserva_valores_com_proveniencia_explicita():
    rows = [_fato("2025-01-01", "2025-12-31", 100),
            _fato("2025-01-01", "2025-06-30", 45),
            _fato("2026-01-01", "2026-06-30", 55)]
    com = _canonico(rows)
    sem = selecionar_pit(pd.DataFrame(rows).drop(columns=["semantica_fluxo", "rubrica_reportada"]), D)
    pd.testing.assert_frame_equal(com.drop(columns="nota"), sem.drop(columns="nota"))
    assert com.attrs == sem.attrs
    assert com.nota.fillna("").str.contains("semantica_fluxo=").sum() == 0
    assert com.nota.fillna("").str.contains("componentes_fluxo=", regex=False).any()


@pytest.mark.parametrize("marcadores,esperado", [
    (["receita_dre"] * 4, 100),
    (["resultado_liquido_seguros"] * 4, 100),
    (["receita_dre", "receita_dre", "resultado_liquido_seguros", "resultado_liquido_seguros"], None),
    (["receita_dre", "receita_dre", None, "receita_dre"], None),
    (["nao_informada"] * 4, None),
    (["seguros_composicao_nao_conciliada"] * 4, None),
])
def test_consumidor_quatro_q_exige_conceitos_conhecidos_em_todos_componentes(marcadores, esperado):
    rows = []
    for fim, valor, conceito in zip(["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"],
                                    [10, 20, 30, 40], marcadores, strict=True):
        rows.append(dict(issuer_id="SIMULADO", item="receita", freq="Q", period_end=fim,
                         data_publicacao=pd.Timestamp(fim) + pd.Timedelta(days=40), value=valor,
                         consolidado=True, currency="BRL", escala=1, demonstrativo="DRE",
                         fonte="SIMULADO", documento="DADOS SIMULADOS", sha256="s" * 64,
                         nota=f"semantica_fluxo={conceito}" if conceito else None))
    v, _ = Demonstrativos(pd.DataFrame(rows), "SIMULADO").valor("receita")
    assert v == esperado


def _quatro_q(conceito):
    return [_fato(inicio, fim, valor, conceito)
            for inicio, fim, valor in [("2025-07-01", "2025-09-30", 10),
                                      ("2025-10-01", "2025-12-31", 20),
                                      ("2026-01-01", "2026-03-31", 30),
                                      ("2026-04-01", "2026-06-30", 40)]]


@pytest.fixture(scope="module")
def ambiente_simulado():
    md = make_synthetic_market(as_of=D)
    iid = next(i for i in md.universe.issuers.index
               if md.universe.issuers.loc[i, "country"] == "BR"
               and md.universe.issuers.loc[i, "gics_sector"] != "Financials")
    dados = coletar(md, D, [iid], list(md.universe.lines_for(iid).index), [])
    return md, carregar_parametros(), dados, iid


@pytest.mark.parametrize("conceito", ["nao_informada", "conceito_desconhecido", "?",
                                      "receita_dre-desconhecida"])
def test_uniforme_desconhecido_recusa_ttm_no_provedor_e_na_preparacao(conceito, ambiente_simulado):
    md, params, dados, iid = ambiente_simulado
    rows = _quatro_q(conceito)
    # O ramo anterior fornecia um TTM pronto; o consumidor o aceitaria sem nova composição.
    legado = selecionar_pit(pd.DataFrame(rows).drop(columns="semantica_fluxo"), D)
    assert legado[legado.freq.eq("TTM")].iloc[0].value == sum(r["value"] for r in rows)
    s = _canonico(rows)
    assert list(s.freq) == ["Q"] * 4 and list(s.value) == [10, 20, 30, 40]
    assert s.nota.str.contains("semantica_fluxo=", regex=False).all()
    alertas = s.attrs["incompatibilidades_fluxos"]
    assert len(alertas) == 1 and "indeterminadas" in alertas[0]["motivo"]
    can = s.rename(columns={"entidade": "issuer_id"}).assign(issuer_id=iid)
    dem = Demonstrativos(can, iid)
    assert dem.valor("receita")[0] is None and not dem.df.freq.eq("TTM").any()
    ds = pd.concat([dados.demonstrativos[dados.demonstrativos.item.ne("receita")], can], ignore_index=True)
    al = alertas_de_attrs({"qa": [f"{iid}: {a['motivo']}" for a in alertas]})
    pacote = preparar(md, replace(dados, demonstrativos=ds, alertas=al), params, [iid], D)[iid]
    assert pacote.get("t.receita") is None
    assert any("indeterminadas" in a["texto"] for a in pacote["alertas_fonte"])


@pytest.mark.parametrize("conceito", ["nao_informada", "conceito_desconhecido"])
def test_uniforme_desconhecido_preserva_anual_e_12m_reportados(conceito):
    rows = [_fato("2025-01-01", "2025-12-31", 0, conceito, recebido="2026-03-18")]
    s = _canonico(rows)
    assert set(s.freq) == {"A", "TTM"} and list(s.value) == [0, 0]
    assert s.data_publicacao.eq(pd.Timestamp("2026-03-18")).all()
    assert s.sha256.eq("s" * 64).all()
    assert not s.attrs["incompatibilidades_fluxos"]


@pytest.mark.parametrize("ausencia", ["coluna", None, pd.NA, float("nan"), "", "   "])
def test_ausencia_efetiva_global_preserva_ttm_legado_ate_preparar(ausencia, ambiente_simulado):
    md, params, dados, iid = ambiente_simulado
    rows = _quatro_q(None)
    f = pd.DataFrame(rows)
    if isinstance(ausencia, str) and ausencia == "coluna":
        f = f.drop(columns="semantica_fluxo")
    else:
        f["semantica_fluxo"] = ausencia
    s = selecionar_pit(f, D)
    t = s[s.freq.eq("TTM")].iloc[0]
    assert t.value == sum(r["value"] for r in rows)
    assert not s.attrs["incompatibilidades_fluxos"]
    assert not s.nota.fillna("").str.contains("semantica_fluxo=", regex=False).any()
    can = s.rename(columns={"entidade": "issuer_id"}).assign(issuer_id=iid)
    ds = pd.concat([dados.demonstrativos[dados.demonstrativos.item.ne("receita")], can], ignore_index=True)
    pacote = preparar(md, replace(dados, demonstrativos=ds), params, [iid], D)[iid]
    assert pacote["t.receita"] == t.value


def _reapresentacao_quatro_q():
    rows = _quatro_q("resultado_liquido_seguros")
    rows[0].update(semantica_fluxo="receita_dre", received_date="2025-11-01", sha256="1" * 64)
    for k, pub in enumerate(["2026-02-09", "2026-05-09", "2026-08-09"], start=1):
        rows[k].update(received_date=pub, sha256=str(k + 1) * 64)
    rows.append({**rows[0], "value": 11, "semantica_fluxo": "resultado_liquido_seguros",
                 "received_date": "2026-09-01", "sha256": "5" * 64,
                 "documento": "DADOS SIMULADOS reapresentação Q3/2025"})
    return rows


def test_quatro_q_reapresentado_data_maxima_e_todas_fontes_ate_preparar(ambiente_simulado):
    md, params, dados, iid = ambiente_simulado
    rows = _reapresentacao_quatro_q()
    antes = _canonico(rows, date(2026, 8, 31))
    assert not antes.freq.eq("TTM").any()
    depois = _canonico(rows, date(2026, 9, 1))
    t = depois[depois.freq.eq("TTM")].iloc[0]
    assert t.value == 11 + 20 + 30 + 40
    assert t.data_publicacao == pd.Timestamp("2026-09-01")
    partes = _prov_linha(t, detalhar_fluxos=True)["componentes_fluxo"]
    assert sum(p["valor"] * p["coeficiente"] for p in partes) == t.value
    assert {(p["period_start"], p["period_end"]) for p in partes} == {
        (r["period_start"], r["period_end"]) for r in rows[1:]}
    assert {p["fonte"]["sha256"] for p in partes} == {r["sha256"] for r in rows[1:]}
    assert max(p["fonte"]["data_publicacao"] for p in partes) == "2026-09-01"
    can = depois.rename(columns={"entidade": "issuer_id"}).assign(issuer_id=iid)
    ds = pd.concat([dados.demonstrativos[dados.demonstrativos.item.ne("receita")], can], ignore_index=True)
    pacote = preparar(md, replace(dados, demonstrativos=ds), params, [iid], D)[iid]
    assert pacote["t.receita"] == t.value
    assert pacote["fontes"]["t.receita"]["data_publicacao"] == "2026-09-01"
    assert pacote["fontes"]["t.receita"]["componentes_fluxo"] == partes
    # O caminho sem metadado conserva o corpo histórico, inclusive sua data anterior.
    legado = selecionar_pit(pd.DataFrame(rows).drop(columns="semantica_fluxo"), date(2026, 9, 1))
    lt = legado[legado.freq.eq("TTM")].iloc[0]
    assert lt.value == t.value and lt.data_publicacao == pd.Timestamp("2026-08-09")
    assert "componentes_fluxo=" not in str(lt.nota)


def test_q_por_diferenca_carrega_reapresentacao_do_acumulado_anterior():
    rows = [_fato("2026-01-01", "2026-03-31", 20, recebido="2026-05-01"),
            _fato("2026-01-01", "2026-06-30", 60, "resultado_liquido_seguros",
                  recebido="2026-08-09"),
            _fato("2026-01-01", "2026-03-31", 25, "resultado_liquido_seguros",
                  recebido="2026-09-01")]
    rows[1]["sha256"], rows[2]["sha256"] = "6" * 64, "7" * 64
    antes = _canonico(rows, date(2026, 8, 31))
    assert not ((antes.freq == "Q") & (antes.period_end == pd.Timestamp("2026-06-30"))).any()
    depois = _canonico(rows, date(2026, 9, 1))
    q = depois[(depois.freq == "Q") & (depois.period_end == pd.Timestamp("2026-06-30"))].iloc[0]
    assert q.value == 60 - 25 and q.data_publicacao == pd.Timestamp("2026-09-01")
    partes = _prov_linha(q, detalhar_fluxos=True)["componentes_fluxo"]
    assert [(p["period_start"], p["period_end"], p["coeficiente"]) for p in partes] == [
        ("2026-01-01", "2026-06-30", 1), ("2026-01-01", "2026-03-31", -1)]
    assert {p["fonte"]["sha256"] for p in partes} == {"6" * 64, "7" * 64}
    assert sum(p["valor"] * p["coeficiente"] for p in partes) == q.value
