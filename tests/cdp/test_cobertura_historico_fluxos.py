"""Histórico de fluxos e sua proveniência; DADOS SIMULADOS, sem rede."""

from datetime import date

import pandas as pd
import pytest

from cdp.cobertura.fontes import _fatos_suplementares, contas_suplementares_cvm
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.cobertura.reinvestimento import giro_por_balancos_sombra


def test_linha_anual_exata_compartilhada_por_valor_data_moeda_e_proveniencia():
    def row(fim, publicado, valor, consolidado, documento, moeda="BRL"):
        return dict(issuer_id="BR_SIMULADO", item="capex", freq="A", period_end=fim,
                    data_publicacao=publicado, value=valor, consolidado=consolidado,
                    demonstrativo="DFC", currency=moeda, escala=1, documento=documento,
                    fonte="SIMULADO", url=f"https://example.test/{documento}", sha256=documento)

    df = pd.DataFrame([
        row("2025-06-30", "2025-08-01", 7, True, "junho_consolidado"),
        row("2025-12-31", "2026-02-01", 9, False, "individual_descartado"),
        row("2025-12-31", "2026-01-30", 11, True, "consolidado_original"),
        row("2025-12-31", "2026-03-01", 12, True, "consolidado_revisado", "USD"),
        row("2024-12-31", "2025-02-01", 4, False, "individual_valido"),
    ])
    dem = Demonstrativos(df, "BR_SIMULADO")
    assert dem.anual("capex") == {2024: 4, 2025: 12}
    r = dem.linhas_anuais("capex")[2025]
    assert r["value"] == dem.anual("capex")[2025]
    assert r["period_end"] == pd.Timestamp("2025-12-31")
    assert r["currency"] == "USD" and r["consolidado"]
    assert _prov_linha(r)["sha256"] == "consolidado_revisado"
    assert not dem.linhas_anuais("capex")[2024]["consolidado"]


def test_ttm_registra_cada_componente_e_sinal_sem_mudar_proveniencia_da_politica_antiga():
    rows = []
    for freq, fim, valor, doc in [("A", "2025-12-31", 100, "anual"),
                                  ("Q", "2025-03-31", 5, "q125"), ("Q", "2025-06-30", 7, "q225"),
                                  ("Q", "2026-03-31", 20, "q126"), ("Q", "2026-06-30", 25, "q226")]:
        rows.append(dict(issuer_id="BR_SIMULADO", item="d_a_dfc", freq=freq, period_end=fim,
                         data_publicacao=pd.Timestamp(fim) + pd.Timedelta(days=40), value=valor,
                         consolidado=True, demonstrativo="DFC", currency="BRL", escala=1,
                         documento=doc, fonte="SIMULADO", url=f"https://example.test/{doc}", sha256=doc))
    # O comparativo republicado por último também determina a data de conhecimento do TTM.
    rows[2]["data_publicacao"] = pd.Timestamp("2026-09-01")
    dem = Demonstrativos(pd.DataFrame(rows), "BR_SIMULADO")
    valor, row = dem.valor("d_a_dfc")
    assert valor == 100 + 20 + 25 - 5 - 7
    prov = _prov_linha(row, detalhar_fluxos=True)
    partes = prov["componentes_fluxo"]
    assert sum(x["valor"] * x["coeficiente"] for x in partes) == valor
    assert {x["fonte"]["sha256"] for x in partes} == {"anual", "q125", "q225", "q126", "q226"}
    assert [x["coeficiente"] for x in partes] == [1, 1, 1, -1, -1]
    assert "componentes_fluxo" not in _prov_linha(row)
    assert row["data_publicacao"] == pd.Timestamp("2026-09-01")
    for campo, valor in [("currency", "USD"), ("consolidado", False)]:
        misto = pd.DataFrame(rows)
        misto.loc[2, campo] = valor
        assert not (Demonstrativos(misto, "BR_SIMULADO").df.freq == "TTM").any()


def test_datas_objetos_date_e_ttm_derivado_ordenam_com_tipo_unico_e_proveniencia_iso():
    rows = []
    for fim, valor in [("2025-09-30", 10), ("2025-12-31", 20), ("2026-03-31", 30), ("2026-06-30", 40)]:
        rows.append(dict(issuer_id="BR_SIMULADO", item="d_a_dfc", freq="Q", period_end=fim,
                         data_publicacao=(pd.Timestamp(fim) + pd.Timedelta(days=40)).date(),
                         value=valor, consolidado=True, demonstrativo="DFC", currency="BRL", escala=1,
                         fonte="SIMULADO", documento=fim, sha256=fim, url=f"https://example.test/{fim}"))
    dem = Demonstrativos(pd.DataFrame(rows), "BR_SIMULADO")
    valor, row = dem.valor("d_a_dfc")
    assert valor == 100 and row.freq == "TTM"
    assert pd.api.types.is_datetime64_any_dtype(dem.df.data_publicacao)
    assert _prov_linha(row)["data_publicacao"] == "2026-08-09"


@pytest.mark.parametrize("moeda,base,ttm", [("BRL", True, True), ("USD", True, False), ("BRL", False, False)])
def test_suplemento_cvm_ttm_republicacao_tardia_moeda_e_base(monkeypatch, moeda, base, ttm):
    from types import SimpleNamespace

    from cdp.cobertura import fontes
    from cdp.data import publico, publico_arquivo

    cnpj = "00.000.000/0001-00"
    primarias = {}
    for doc, ano, fim, valor, publicado, moeda_linha, cons in [
        ("DFP", 2025, "2025-12-31", 100, "2026-03-01", "BRL", True),
        ("ITR", 2025, "2025-06-30", 12, "2026-09-01", moeda, base),
        ("ITR", 2026, "2026-06-30", 45, "2026-08-01", "BRL", True),
    ]:
        key = f"CVM/{doc}/{doc.lower()}_cia_aberta_{ano}.zip"
        primarias[key] = pd.DataFrame([dict(cnpj=cnpj, item="d_a_dfc", doc=doc, dt_fim=pd.Timestamp(fim),
            dt_ini=pd.Timestamp(f"{ano}-01-01"), dt_refer=pd.Timestamp(fim), versao=1, value=valor,
            currency=moeda_linha, consolidado=cons, recebido=pd.Timestamp(publicado), url=f"https://example.test/{key}")])

    class ArquivoSimulado:
        def __init__(self, raiz, offline):
            assert offline

        def buscar(self, chave, ate):
            return None if chave not in primarias else SimpleNamespace(chave=chave, sha256=chave,
                                                                       data_coleta="2026-10-08T00:00:00")

        def ler(self, registro):
            return registro.chave

    monkeypatch.setattr(publico_arquivo, "Arquivo", ArquivoSimulado)
    monkeypatch.setattr(publico, "mestre_publico", lambda *args, **kw: pd.DataFrame({"cnpj": [cnpj]}, index=["BR_SIMULADO"]))
    monkeypatch.setattr(fontes, "_tabelas_cvm", lambda chave, *args: {"chave": chave})
    monkeypatch.setattr(fontes, "_fatos_suplementares", lambda tab, doc: primarias[tab["chave"]].copy())
    df = contas_suplementares_cvm(["BR_SIMULADO"], date(2026, 10, 8), None)
    observado = df[df.freq == "TTM"]
    assert (not observado.empty) is ttm
    if ttm:
        row = observado.iloc[0]
        assert row.value == 100 + 45 - 12
        assert row.data_publicacao == date(2026, 9, 1)
        partes = _prov_linha(row, detalhar_fluxos=True)["componentes_fluxo"]
        assert sum(x["valor"] * x["coeficiente"] for x in partes) == row.value
        assert len({x["fonte"]["sha256"] for x in partes}) == 3
        antes = contas_suplementares_cvm(["BR_SIMULADO"], date(2026, 8, 20), None)
        assert not (antes.freq == "TTM").any()


def test_cvm_dfc_depreciacao_e_giro_explicitamente_operacional(monkeypatch):
    from cdp.data import fundamentals_pit

    ini, fim = pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31")
    key = dict(cnpj="00.000.000/0001-00", dt_refer=fim, versao=1, kind="con", dt_ini=ini,
               dt_fim=fim, currency="BRL")
    # Uma linha de juros não é D&A e a variação agregada não é capital de giro operacional.
    dfc = pd.DataFrame([{**key, "cd": cd, "ds": ds, "value": v} for cd, ds, v in [
        ("6.01.01.01", "depreciacao e amortizacao", 20.0),
        ("6.01.01.02", "amortizacao de encargos financeiros", 3.0),
        ("6.01.02", "variacoes em ativos e passivos", -99.0),
        ("6.01.03", "variacao de capital de giro operacional", -5.0),
    ]])
    monkeypatch.setattr(fundamentals_pit, "_prepare_statement",
                        lambda tabs, tabela: dfc if tabela == "DFC_MI" else dfc.iloc[0:0])
    idx = pd.DataFrame([dict(CNPJ_CIA=key["cnpj"], DT_REFER=fim, VERSAO=1,
                             DT_RECEB="2026-03-01", LINK_DOC="https://example.test/dfp")])
    fatos = _fatos_suplementares({"index": idx}, "DFP").set_index("item")
    assert fatos.loc["d_a_dfc", "value"] == 20
    assert fatos.loc["variacao_capital_giro_operacional", "value"] == 5
    assert fatos.loc["variacao_capital_giro_operacional", "recebido"] == pd.Timestamp("2026-03-01")


def test_proxy_de_balancos_separa_divida_e_dividendos_e_permanece_sombra():
    a = dict(data=date(2024, 12, 31).isoformat(), moeda="BRL", ativo_circulante=100,
             caixa=10, aplicacoes_cp=20, passivo_circulante=80, divida_curto_prazo=30,
             dividendos_a_pagar=5, fontes={"ativo_circulante": {"sha256": "SIMULADO"}})
    b = {**a, "data": "2025-12-31", "ativo_circulante": 110}
    s = giro_por_balancos_sombra(a, b)
    assert s["observacoes"][0]["ncwc"] == 25
    assert s["delta_proxy"] == 10
    assert s["estado"] == "sombra" and s["usavel_fcff"] is False
    assert s["observacoes"][0]["fontes"] == a["fontes"]
    assert "variacao_capital_giro_operacional" not in s
    del b["aplicacoes_cp"]
    assert giro_por_balancos_sombra(a, b)["delta_proxy"] is None
    assert "final.aplicacoes_cp" in giro_por_balancos_sombra(a, b)["faltam"]
    b["aplicacoes_cp"], b["moeda"] = 20, "USD"
    assert giro_por_balancos_sombra(a, b)["delta_proxy"] is None
    b["moeda"], b["data"] = "BRL", a["data"]
    assert giro_por_balancos_sombra(a, b)["delta_proxy"] is None
    b["data"] = "data não encontrada"
    assert giro_por_balancos_sombra(a, b)["delta_proxy"] is None


def test_nenhum_giro_sem_rubrica_explicitamente_de_capital_de_giro(monkeypatch):
    from cdp.data import fundamentals_pit

    d = pd.DataFrame([dict(cnpj="SIMULADO", dt_refer=pd.Timestamp("2025-12-31"), versao=1,
                          kind="con", dt_ini=pd.Timestamp("2025-01-01"), dt_fim=pd.Timestamp("2025-12-31"),
                          currency="BRL", cd="6.01.02", ds="variacoes em ativos e passivos", value=-90)])
    monkeypatch.setattr(fundamentals_pit, "_prepare_statement", lambda tabs, tabela: d if tabela == "DFC_MI" else d.iloc[0:0])
    idx = pd.DataFrame([dict(CNPJ_CIA="SIMULADO", DT_REFER="2025-12-31", VERSAO=1, DT_RECEB="2026-03-01")])
    assert _fatos_suplementares({"index": idx}, "DFP").empty


@pytest.mark.parametrize("base_rou,nota,observado", [(True, None, True), (False, None, False),
    (False, "base mista: componentes individuais e consolidados", False)])
def test_preparador_nao_combina_rou_individual_com_resultado_consolidado(base_rou, nota, observado):
    from dataclasses import replace

    from cdp.cobertura.fontes import coletar
    from cdp.cobertura.insumos import preparar_emissor
    from cdp.cobertura.parametros import carregar_parametros
    from cdp.cobertura.reinvestimento import COMPONENTES, reinvestimento_capitalizado
    from cdp.data.synthetic import make_synthetic_market

    d, params = date(2026, 10, 8), carregar_parametros()
    md = make_synthetic_market(seed=7, as_of=d)
    iid = next(i for i in md.universe.issuers.index if md.universe.issuers.loc[i, "gics_sector"] == "Energy")
    dados = coletar(md, d, [iid], list(md.universe.lines.index), [])
    moeda = Demonstrativos(dados.demonstrativos, iid).moeda()
    novos = pd.DataFrame([dict(issuer_id=iid, item=k, value=v, demonstrativo="DFC", freq="TTM",
                  period_end="2026-06-30", data_publicacao="2026-08-07", currency=moeda, escala=1,
                  consolidado=base_rou if k == "adicoes_direito_uso" or nota else True, fonte="SIMULADO",
                  nota=nota,
                  documento=k, sha256=k, url=f"https://example.test/{k}")
                  for k, v in zip(COMPONENTES, (100, 30, 25, 5, 20), strict=True)])
    dem = dados.demonstrativos
    dem = pd.concat([dem[~dem.item.isin(COMPONENTES)], novos], ignore_index=True)
    p = preparar_emissor(md, replace(dados, demonstrativos=dem), params, iid, d)
    assert p["bases_fluxos"]["adicoes_direito_uso"] == (None if nota else "consolidado" if base_rou else "individual")
    assert p["bases_fluxos"]["ebit"] == (None if nota else "consolidado")
    assert (reinvestimento_capitalizado(p, 0.3) is not None) is observado
