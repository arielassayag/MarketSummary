"""Aba "Cobertura de ativos" do portal: arquivos de dados (``painel_cobertura.py``) e módulo da
página (``painel_cobertura.js``).

Cobre o esquema e o aviso DADOS SIMULADOS na demonstração, a estabilidade byte a byte, os
orçamentos de publicação (248 instrumentos × 104 semanas), ausente → ``null``, o determinismo dos
fragmentos, a máscara dos modelos em revisão, a compactação que nunca remove o universo, o
vocabulário (sem TI), a cópia local embutida, a gravação com remoção de fragmentos antigos e as
regras do módulo: agulhas, nada de ``</script>`` e nenhuma conta sobre os dados. Também: os
fragmentos param no retrato (um pregão a mais muda só ``cobertura.json`` e
``cobertura-precos.json``), o gráfico dos ETFs com preço-alvo e faixa de 90%, o texto de exibição
em português (sem códigos internos), o livro que não confere, a metodologia montada da
configuração e os endereços fixos na versão publicada."""

from __future__ import annotations

import json
import random
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from cdp.cobertura.cli import executar_snapshot
from cdp.cobertura.parametros import carregar_parametros
from cdp.data.synthetic import make_synthetic_market
from cdp.workflow import painel_cobertura as PC
from cdp.workflow.demo import DemoStore
from cdp.workflow.painel_publicacao import expandir

D1, D2 = date(2026, 10, 8), date(2026, 10, 16)
CODIGO = {"git": None}
SIM = "DADOS SIMULADOS"


# ==========================================================================================
# Livro sintético real (motor da cobertura, sem rede)
# ==========================================================================================


@pytest.fixture(scope="module")
def mercado():
    return DemoStore(make_synthetic_market(seed=7, as_of=D2))


@pytest.fixture(scope="module")
def livro(mercado, tmp_path_factory):
    book = tmp_path_factory.mktemp("cobpainel") / "book"
    params = carregar_parametros()
    for d in (D1, D2):
        executar_snapshot(book, mercado.load(d), d, offline=True, params=params,
                          agora=datetime(d.year, d.month, d.day, 23, tzinfo=UTC), codigo=CODIGO)
    return book


@pytest.fixture(scope="module")
def arquivos_demo(livro, mercado):
    ent = PC.carregar(livro, md=mercado.load(D2), carteira={"SIM001": 0.02, "SIM002": -0.015})
    return ent, PC.exportar(ent)


def _todos(arquivos: dict[str, str]) -> dict[str, Any]:
    return {n: expandir(json.loads(t)) for n, t in arquivos.items()}


def test_esquema_e_dados_simulados_na_demonstracao(arquivos_demo, mercado):
    ent, arqs = arquivos_demo
    assert PC.conferir(arqs) == []
    docs = _todos(arqs)
    assert set(docs) >= {PC.ARQUIVO, PC.ARQUIVO_PRECOS}
    assert any(n.startswith(PC.PREFIXO_MODELO) for n in docs)
    assert any(n.startswith(PC.PREFIXO_HISTORICO) for n in docs)
    for nome, d in docs.items():
        assert d["meta"]["is_synthetic"] is True, nome
        assert d["meta"]["data_notice"] == SIM, nome
    c = docs[PC.ARQUIVO]
    m = c["meta"]
    assert m["schema_version"] == PC.SCHEMA and m["simulated_label"] == SIM
    assert m["as_of"] == D2.isoformat() and m["estado"] == "publicado"
    assert set(c) == {"meta", "kpis", "universe", "aggregates", "etfs", "track_record", "revisions",
                      "methodology"}
    ids = sorted(mercado.md.universe.issuers.index)
    acoes = [u["iid"] for u in c["universe"] if u["tipo"] == "acao"]
    assert acoes == ids  # uma linha por emissor, nunca omitida
    assert [u["iid"] for u in c["universe"] if u["tipo"] == "etf"] == sorted(ent.etfs)
    assert m["counts"]["instruments"] == len(c["universe"])
    assert m["has_book"] is True and sum(1 for u in c["universe"] if u["carteira"]) == 2
    for u in c["universe"]:
        assert u["rating"] in PC.RATINGS + PC.VISOES_ETF
        assert u["mk"] is not None and u["hk"] is not None
    # cada instrumento tem o modelo aberto completo no fragmento indicado
    modelos = {}
    for n, d in docs.items():
        if n.startswith(PC.PREFIXO_MODELO):
            modelos.update(d["modelos"])
    for u in c["universe"]:
        mo = modelos[u["iid"]]
        assert mo["passos"], u["iid"]
        for p in mo["passos"]:
            assert p["t"] and p["s"]
            for i in p.get("fo") or []:
                assert 0 <= i < len(mo["fontes"])
        if u["tipo"] == "acao":
            assert {"insumos", "lacunas", "portoes", "sensibilidade", "cenarios", "football"} <= set(mo)
    assert c["methodology"]["aviso"] == PC.AVISO_CVM
    assert "Resolução CVM 20/2021" in c["meta"]["aviso_cvm"]


def test_estavel_byte_a_byte(livro, mercado, arquivos_demo):
    _, a = arquivos_demo
    ent2 = PC.carregar(livro, md=mercado.load(D2), carteira={"SIM002": -0.015, "SIM001": 0.02})
    assert PC.exportar(ent2) == a
    assert PC.de_book(livro, md=mercado.load(D2), painel={"latest_day": {"positions": [
        {"issuer_id": "SIM001", "weight": 0.02}, {"issuer_id": "SIM002", "weight": -0.015}]}}) == a
    for texto in a.values():
        assert "generated_at" not in texto


def test_formas_compactas_desfeitas_sem_sobra(arquivos_demo):
    _, arqs = arquivos_demo

    def sobras(x: Any) -> int:
        if isinstance(x, dict):
            return sum(k in ("_colunas", "_rep", "_partes", "_igual") for k in x) + sum(sobras(v) for v in x.values())
        if isinstance(x, list):
            return sum(sobras(v) for v in x)
        return 0

    for nome, d in _todos(arqs).items():
        assert sobras(d) == 0, nome


def test_geometria_entre_0_e_100(arquivos_demo):
    _, arqs = arquivos_demo
    chaves = {"x", "y", "w", "h", "x0", "y0", "y1", "ly", "a", "zero", "zero_x", "zero_y", "retrato",
              "preco", "alvo"}

    def andar(x: Any, caminho: str) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k in chaves and isinstance(v, (int, float)) and not isinstance(v, bool) \
                        and caminho.split(".")[0] in ("aggregates", "track_record", "series", "modelos"):
                    if "football" in caminho or "ponte" in caminho or "aggregates" in caminho \
                            or "track_record" in caminho or "series" in caminho:
                        assert 0.0 <= v <= 100.0, f"{caminho}.{k} = {v}"
                andar(v, f"{caminho}.{k}" if caminho else k)
        elif isinstance(x, list):
            for v in x:
                andar(v, caminho)

    for d in _todos(arqs).values():
        andar({k: v for k, v in d.items() if k != "meta"}, "")


# ==========================================================================================
# Entrada sintética em memória (orçamentos e casos de borda, sem o motor)
# ==========================================================================================

PAISES = ("BR", "MX", "CL", "CO", "PE", "AR")
SETORES = ("Financials", "Materials", "Energy", "Utilities", "Industrials", "Consumer Staples",
           "Consumer Discretionary", "Health Care", "Real Estate", "Communication Services")


def _fonte(i: int, k: int) -> dict[str, Any]:
    return {"fonte": "CVM", "url": f"http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?"
                                   f"CodigoInstituicao=1&NumeroSequencialDocumento={100000 + i * 7 + k % 4}",
            "documento": f"ITR 2026-06-30 v3 (DRE, 12 meses até 2026-06-30) documento {k % 4}",
            "data_publicacao": "2026-07-31", "data_coleta": "2026-10-06T09:52:07+00:00", "sha256": "ab" * 32}


def _modelo(iid: str, i: int, pais: str, setor: str, moeda: str, rating: str, as_of: str,
            preco: float | None, alvo: float | None) -> dict[str, Any]:
    citavel = rating in PC.RATINGS_CITAVEIS and alvo is not None
    passos = [{"id": f"metodo.passo_{k}", "titulo": f"Passo {k} do modelo de {iid}",
               "formula": "V = Σ FCFF_t ÷ (1 + WACC)^t + VT ÷ (1 + WACC)^n − dívida líquida",
               "substituicao": f"V = R$ {k},50 bi ÷ 1,1235 + R$ 12,40 bi ÷ 1,1235^10 − R$ 3,20 bi = R$ {k + 10},44 bi",
               "resultado": float(k), "resultado_texto": f"R$ {k + 10},44 bi", "unidade": f"total:{moeda}",
               "premissas": "crescimento convergindo ao g de longo prazo; margem ao longo do ciclo" if k % 3 == 0 else None,
               "fontes": [_fonte(i, k), _fonte(i, k + 1)] if k % 2 == 0 else [_fonte(i, k)]}
              for k in range(58)]
    insumos = [{"id": f"insumo_{k}", "nome": f"Insumo contábil {k}", "valor": 1.5 * k, "valor_texto": f"R$ {k},50 bi",
                "unidade": f"total:{moeda}", "periodo": "12 meses até 2026-06-30", "data_publicacao": "2026-07-31",
                "data_estimada": False, **{kk: v for kk, v in _fonte(i, k).items() if kk != "data_publicacao"}}
               for k in range(36)]
    proj = [{"ano": a, "receita": 1e9 * a, "fcff": 1e8 * a,
             "texto": {"receita": f"R$ {a},00 bi", "crescimento": "4,13%", "fcff": f"R$ {a},10 bi",
                       "nopat": "R$ 1,20 bi", "reinvestimento": "16,71%"}} for a in range(1, 11)]
    grade = [[(alvo or 10.0) * (1 + 0.05 * (c - 2) - 0.04 * (r - 2)) for c in range(5)] for r in range(5)]
    return {
        "schema": "cdp.cobertura.modelo/v1", "issuer_id": iid, "nome": f"Emissor {i:03d}", "pais": pais, "setor": setor,
        "arquetipo": "corporativo", "industria": "Diversified", "as_of": as_of, "linha": f"T{i:03d}3.SA", "moeda": moeda,
        "is_synthetic": True, "aviso_dados": SIM, "versao_metodologia": "2026-10.2", "horizonte_meses": 12,
        "resumo": {"preco": preco, "data_preco": as_of, "preco_alvo": alvo, "upside": None if not (alvo and preco) else alvo / preco - 1,
                   "etr": 0.12, "pwr": 0.11, "ke": 0.13, "rating": rating, "rating_motivo": "α_rel acima do limiar",
                   "confianca": "B", "confianca_motivo": "3 métodos", "incerteza": "Média",
                   "alvo_otimista": None if alvo is None else alvo * 1.3, "alvo_pessimista": None if alvo is None else alvo * 0.7,
                   "vencimento": "2027-10-16", "alvo_citavel": citavel, "motivo_sem_alvo": None,
                   "consenso": {"alvo_medio": None if preco is None else preco * 1.1, "alvo_alto": None if preco is None else preco * 1.4,
                                "alvo_baixo": None if preco is None else preco * 0.8, "n_alvo": 9.0, "plausivel": preco is not None,
                                "upside": 0.1},
                   "texto": {"pwr": "11,00%", "pl_fwd": "8,10x", "pb": "1,40x"}},
        "alvos_linhas": [], "insumos": insumos, "lacunas": [{"insumo": "capex", "nome": "Investimento", "motivo": "não publicado"}],
        "avisos": ["LPA de consenso em USD convertido"],
        "custo_capital": {"rf": 0.05, "erp": 0.042, "crp": 0.031, "beta": 1.1, "ke": 0.13, "wacc": 0.11, "g": 0.05},
        "metodos": [{"m": "fcff", "nome": "Fluxo de caixa livre da firma", "peso": 0.5, "valor": alvo, "fracao_terminal": 0.6,
                     "projecao": proj},
                    {"m": "rim", "nome": "Lucro residual", "peso": 0.25, "valor": None if alvo is None else alvo * 0.9},
                    {"m": "multiplo_justificado", "nome": "P/L justificado", "peso": 0.25, "valor": None, "motivo": "LPA negativo"}],
        "cenarios": {"tp_pessimista": None if alvo is None else alvo * 0.7, "tp_otimista": None if alvo is None else alvo * 1.3,
                     "tp_mediana_mc": alvo, "pwr": 0.11, "ret_p10": -0.3, "ret_p50": 0.1, "ret_p90": 0.5, "udr": 1.4,
                     "prob_modelo_supera_ke": 0.45, "prob_mercado_otimista": 0.08, "prob_mercado_pessimista": 0.02,
                     "n_sorteios": 2000, "perda_esperada_cauda": -0.4} if citavel else None,
        "sensibilidade": {"linhas": "ke", "colunas": "g", "ke_texto": ["12,0%", "12,5%", "13,0%", "13,5%", "14,0%"],
                          "colunas_texto": ["−0,50 p.p.", "−0,25 p.p.", "0,00 p.p.", "+0,25 p.p.", "+0,50 p.p."],
                          "choques_colunas": [-0.005, -0.0025, 0.0, 0.0025, 0.005], "preco_alvo": grade,
                          "upside": [[v / (preco or 1) - 1 for v in row] for row in grade],
                          "preco_alvo_texto": [[f"R$ {v:.2f}".replace(".", ",") for v in row] for row in grade],
                          "upside_texto": [[f"{(v / (preco or 1) - 1) * 100:+.1f}%".replace(".", ",") for v in row] for row in grade]},
        "diagnosticos": {"icc": {"composto": 0.12, "icc_menos_ke": -0.01}, "reverso": {"roe_implicito": 0.15, "roe_sustentavel": 0.14}},
        "pares": {"grupo": f"{pais} × {setor}", "n": 3, "mediana_alpha": 0.01, "alphas": [[iid, 0.02]]},
        "portoes": [{"codigo": f"G{k}", "nome": f"Verificação {k}", "status": "ok" if k % 5 else "aviso",
                     "detalhe": "conferido em 2026-10-06"} for k in range(1, 16)],
        "ponte": {"componentes": {"rolagem": 0.4, "estimativas": -0.9, "parametros": 0.2, "estrutura_capital": None,
                                  "cambio": 0.1, "preco": 0.0, "metodos": 0.0, "residuo": 0.01},
                  "motivo": "RESULTADO", "alvo_anterior": None if alvo is None else alvo - 0.19, "alvo_novo": alvo,
                  "notas": [], "residuo_relativo": 0.001} if citavel else None,
        "passos": passos,
    }


def _etf(k: int, as_of: str) -> dict[str, Any]:
    pos = [{"nome": f"POSICAO {j}", "peso": 0.3 / (j + 1), "issuer_id": f"BR_E{j:03d}" if j % 3 else None,
            "imputado": j % 3 == 0, "u": 0.01 * (j - 5), "texto": {"peso": f"{30 / (j + 1):.2f}%".replace(".", ","),
                                                                   "u": f"{j - 5:+d},0%"}} for j in range(60)]
    return {"iid": f"ETF_X{k}", "ticker": f"X{k}", "nome": f"ETF sintético {k}", "moeda": "USD", "pais": "BR",
            "indice": "Índice sintético", "preco": 40.0, "preco_alvo": 42.0, "upside": 0.05, "retorno_esperado": 0.06,
            "visao_ilf": ("Positiva", "Neutra", "Negativa", "Em revisão")[k % 4], "tem_alvo": True, "metodo": "combinado",
            "data_preco": as_of, "as_of": as_of, "posicoes": pos, "passos": [], "portoes": [], "lacunas": [], "avisos": [],
            "texto": {"preco": "US$ 40,00", "preco_alvo": "US$ 42,00", "upside": "+5,0%", "retorno_esperado": "+6,0%",
                      "r_bu": "+4,0%", "r_td": "+8,0%", "cobertura": "80%", "te_ilf": "12,0%"},
            "agregados": {"pl": 10.0}, "is_synthetic": True}


def entrada_sintetica(n_acoes: int = 240, n_etfs: int = 8, semanas: int = 104, seed: int = 3,
                      ratings: tuple[str, ...] = ("Compra", "Neutro", "Venda", "Em revisão")) -> PC.Entrada:
    """Universo sintético (DADOS SIMULADOS) com ``semanas`` retratos semanais completos."""
    rnd = random.Random(seed)
    fim = date(2026, 10, 16)
    datas = [fim - timedelta(weeks=k) for k in range(semanas)][::-1]
    linhas, modelos, eventos, fech, ult, adtv = [], {}, [], {}, {}, {}
    seq = 0
    for i in range(n_acoes):
        iid = f"BR_E{i:03d}"
        pais, setor = PAISES[i % len(PAISES)], SETORES[i % len(SETORES)]
        moeda = "BRL"
        preco = 10.0 + i % 50
        rating = ratings[i % len(ratings)]
        alvo = None if rating == "Sem preço-alvo" else preco * (1 + 0.3 * rnd.uniform(-1, 1))
        modelos[iid] = _modelo(iid, i, pais, setor, moeda, rating, fim.isoformat(), preco, alvo)
        cit = rating in PC.RATINGS_CITAVEIS
        linhas.append({"issuer_id": iid, "nome": f"Emissor {i:03d}", "pais": pais, "setor": setor, "arquetipo": "corporativo",
                       "linha": f"T{i:03d}3.SA", "moeda": moeda, "preco": preco, "data_preco": fim.isoformat(),
                       "preco_alvo": alvo if cit else None, "upside": (alvo / preco - 1) if cit and alvo else None,
                       "etr": 0.12 if cit else None, "ke": 0.13, "rating": rating, "confianca": "B", "incerteza": "Média",
                       "alvo_otimista": None if not cit else alvo * 1.3, "alvo_pessimista": None if not cit else alvo * 0.7,
                       "diff_consenso": -0.05 if cit else None, "portoes_bloqueio": "" if cit else "G11",
                       "snapshot": fim.isoformat()})
        serie = []
        d, p = fim - timedelta(weeks=semanas + 2), preco
        while d <= fim:
            if d.weekday() < 5:
                p = max(0.5, p * (1 + rnd.gauss(0, 0.015)))
                serie.append((d.isoformat(), round(p, 4)))
            d += timedelta(days=1)
        fech[f"T{i:03d}3.SA"] = serie
        ult[iid] = serie[-1]
        adtv[iid] = 1e6 * (1 + i % 7)
        tp = alvo
        r_ant = None
        for k, dd in enumerate(datas):
            tp_k = None if tp is None else tp * (1 + 0.02 * rnd.uniform(-1, 1))
            r_k = rating if k % 9 else ("Neutro" if rating != "Neutro" else "Compra")
            eventos.append({"seq": seq, "issuer_id": iid, "as_of": dd.isoformat(), "linha": f"T{i:03d}3.SA", "moeda": moeda,
                            "pais": pais, "setor": setor, "parcial": False,
                            "tipo": "INICIACAO" if k == 0 else ("MUDANCA_RATING" if r_k != r_ant else "REVISAO"),
                            "alvo": {"base": tp_k}, "alvo_citavel": tp_k is not None and r_k in PC.RATINGS_CITAVEIS,
                            "alvo_anterior": {"base": tp} if k else None, "rating": r_k, "rating_anterior": r_ant,
                            "alpha_rel": rnd.uniform(-0.2, 0.2), "preco_ref": {"fechamento": preco * (1 + 0.01 * k % 7)},
                            "consenso": {"alvo_alto": preco * 1.4, "alvo_baixo": preco * 0.8, "alvo_medio": preco * 1.1,
                                         "n_alvo": 9}, "motivos": ["RESULTADO"], "vencimento": "2027-10-16"})
            seq += 1
            r_ant = r_k
    etfs = {f"ETF_X{k}": _etf(k, fim.isoformat()) for k in range(n_etfs)}
    for k in etfs:
        fech[etfs[k]["ticker"]] = fech[f"T{0:03d}3.SA"]
        ult[k] = fech[etfs[k]["ticker"]][-1]
    placar = {"n_previsoes": n_acoes * semanas, "n_vencidas": 30, "exibir_taxas": True, "em_maturacao": False,
              "primeiro_vencimento": "2025-10-17", "tpmet12": {"k": 10, "n": 30, "taxa": 1 / 3, "ic90": [0.2, 0.48]},
              "tpmetany": {"k": 16, "n": 30, "taxa": 16 / 30, "ic90": [0.38, 0.68]}, "erro_abs_mediano": 0.31,
              "ic_semanal": [{"data": a.isoformat(), "ate": b.isoformat(), "ic": rnd.uniform(-0.1, 0.12), "n": n_acoes}
                             for a, b in zip(datas, datas[1:], strict=False)],
              "ic_resumo": {"media": 0.02, "dp": 0.05, "t_newey_west": 2.1, "semanas": semanas - 1},
              "referencias_literatura": {"tpmet12": [0.24, 0.38], "tpmetany": [0.45, 0.64], "erro_abs": [0.36, 0.45]},
              "metodo": "amostragem semanal"}
    cfg = {"versao": "2026-10.2", "horizonte_meses": 12,
           "pesos_metodos": {"corporativo": {"fcff": 0.5, "rim": 0.25, "multiplo_justificado": 0.25}},
           "custo_capital": {"erp_contemporaneo": 0.037, "erp_contemporaneo_data": "2026-10-01", "crp": {"BR": 0.031, "MX": 0.0272}},
           "rating": {"limiar_alpha_rel": {"Baixa": 0.08, "Média": 0.10}, "guarda_compra_alpha_min": 0.0,
                      "guarda_venda_alpha_max": -0.05, "guarda_venda_etr_menos_ke_max": -0.05, "histerese": 0.02,
                      "confianca_minima": "B"}}
    return PC.Entrada(as_of=fim, is_synthetic=True, linhas=linhas, modelos=modelos, etfs=etfs, eventos=eventos,
                      placar=placar, snapshots=[d.isoformat() for d in datas], fechamentos=fech, ultimo_preco=ult,
                      adtv_usd=adtv, carteira={f"BR_E{i:03d}": 0.01 * (1 if i % 2 else -1) for i in range(0, 60, 3)},
                      configuracao=cfg)


@pytest.fixture(scope="module")
def grande():
    ent = entrada_sintetica()
    return ent, PC.exportar(ent)


def test_orcamento_248_instrumentos_104_semanas(grande):
    ent, arqs = grande
    assert PC.conferir(arqs) == []
    c = expandir(json.loads(arqs[PC.ARQUIVO]))
    assert len(c["universe"]) == 248
    assert c["meta"]["publication"]["nivel"] == 0  # cabe sem cortes
    assert len(arqs[PC.ARQUIVO_PRECOS].encode()) <= 30_000
    for nome, texto in arqs.items():
        assert len(texto.encode("utf-8")) <= PC.MAX_BYTES, nome
        assert max(len(x) for x in texto.splitlines()) <= PC.MAX_LINHA, nome
    hist = [n for n in arqs if n.startswith(PC.PREFIXO_HISTORICO)]
    serie = expandir(json.loads(arqs[hist[0]]))["series"]
    s0 = next(iter(serie.values()))
    assert 52 <= s0["n"] <= 52 + 13  # 52 semanas + um ponto por mês antes delas
    assert len(s0["tabela"]) == 104  # todos os eventos do instrumento


def test_compactacao_nunca_remove_universo(monkeypatch):
    ent = entrada_sintetica(n_acoes=120, n_etfs=4, semanas=30)
    completo = expandir(json.loads(PC.exportar(ent)[PC.ARQUIVO]))
    monkeypatch.setattr(PC, "MAX_BYTES", 40_000)
    out = expandir(json.loads(PC.exportar(ent)[PC.ARQUIVO]))
    pub = out["meta"]["publication"]
    assert pub["nivel"] == len(PC.NIVEIS) - 1
    assert out["meta"]["truncations"]
    chaves = ("iid", "rating", "alvo", "alvo_texto", "upside", "upside_texto", "pessimista_texto", "otimista_texto",
              "citavel", "mk", "hk")
    assert [{k: u[k] for k in chaves} for u in out["universe"]] == [{k: u[k] for k in chaves} for u in completo["universe"]]
    assert out["track_record"]["tiles"] == completo["track_record"]["tiles"]
    assert out["kpis"] == completo["kpis"]


def test_ausente_vira_null_nunca_zero():
    ent = entrada_sintetica(n_acoes=12, n_etfs=1, semanas=3)
    ent.linhas[0].update({"preco": None, "preco_alvo": None, "upside": None, "etr": None, "ke": None,
                          "diff_consenso": None, "incerteza": None})
    ent.modelos["BR_E000"]["resumo"].update({"consenso": {}, "incerteza": None})
    ent.ultimo_preco.pop("BR_E000")
    c = expandir(json.loads(PC.exportar(ent)[PC.ARQUIVO]))
    u = next(x for x in c["universe"] if x["iid"] == "BR_E000")
    for k in ("preco", "alvo", "upside", "etr", "ke", "vs_consenso", "consenso_n", "incerteza_ordem"):
        assert u[k] is None, k
    assert u["preco_texto"] == "n/d" and u["upside_texto"] == "n/d" and u["vs_consenso_texto"] == "n/d"
    assert u["citavel"] is False
    precos = expandir(json.loads(PC.exportar(ent)[PC.ARQUIVO_PRECOS]))["precos"]
    assert "BR_E000" not in {p["i"] for p in precos}


def test_mascara_dos_modelos_em_revisao(grande):
    _, arqs = grande
    c = expandir(json.loads(arqs[PC.ARQUIVO]))
    rev = [u for u in c["universe"] if u["rating"] == "Em revisão"]
    assert rev
    for u in rev:
        assert u["alvo"] is None and u["upside"] is None and u["etr"] is None and u["vs_consenso"] is None
        assert u["alvo_texto"] == "Em revisão" and u["pessimista_texto"] == "n/d" and not u["citavel"]
    pontos = {p["i"] for p in c["aggregates"]["distribuicao"]["leiautes"]["pais"]["pontos"]}
    assert not pontos & {u["iid"] for u in rev}
    modelos = {}
    for n, t in arqs.items():
        if n.startswith(PC.PREFIXO_MODELO):
            modelos.update(expandir(json.loads(t))["modelos"])
    m = modelos[rev[0]["iid"]]
    assert m["citavel"] is False and m["cenarios"] is None and m["ponte"] is None
    assert m["football"] is None or m["football"]["alvo"] is None


def test_fragmentos_deterministicos_e_etfs_por_ultimo():
    a = entrada_sintetica(n_acoes=40, n_etfs=3, semanas=6)
    b = entrada_sintetica(n_acoes=40, n_etfs=3, semanas=6)
    b.linhas = list(reversed(b.linhas))
    b.modelos = dict(reversed(list(b.modelos.items())))
    b.etfs = dict(reversed(list(b.etfs.items())))
    ra, rb = PC.exportar(a), PC.exportar(b)
    assert ra == rb
    c = expandir(json.loads(ra[PC.ARQUIVO]))
    for prefixo, chave, campo in ((PC.PREFIXO_MODELO, "modelos", "mk"), (PC.PREFIXO_HISTORICO, "series", "hk")):
        vistos: dict[str, int] = {}
        nomes = sorted((n for n in ra if n.startswith(prefixo)), key=lambda n: int(re.findall(r"\d+", n)[0]))
        ordem = []
        for n in nomes:
            d = expandir(json.loads(ra[n]))
            k = d["meta"]["fragmento"]
            assert n == f"{prefixo}{k}.json"
            for iid in d[chave]:
                assert iid not in vistos
                vistos[iid] = k
                ordem.append(iid)
        assert ordem == [u["iid"] for u in c["universe"]]  # ordenado; ETFs por último
        assert ordem[-3:] == sorted(a.etfs)
        for u in c["universe"]:
            assert u[campo] == vistos[u["iid"]]


def test_sem_cobertura_aviso_institucional():
    out = PC.exportar(None)
    assert list(out) == [PC.ARQUIVO]
    d = json.loads(out[PC.ARQUIVO])
    assert d["meta"]["estado"] == "sem_cobertura" and d["universe"] == []


_TI = re.compile(r"\b(hash|sha-?256|json|commit|pipeline|artifact|segunda-feira)\b", re.I)


def _sem_ti(x: Any, onde: str) -> None:
    if isinstance(x, dict):
        for k, v in x.items():
            assert not re.search(r"(?:^|_)(?:sha256|hash)$", k), f"{onde}.{k}"
            _sem_ti(v, f"{onde}.{k}")
    elif isinstance(x, list):
        for v in x:
            _sem_ti(v, onde)
    elif isinstance(x, str) and not re.match(r"^(https?://|livro/|cobertura/\d{4}-\d{2}-\d{2}/)", x):
        assert not _TI.search(x), f"{onde} = {x!r}"


def test_sem_vocabulario_de_ti_nem_de_semana_anterior(arquivos_demo, grande):
    for _, arqs in (arquivos_demo, grande):
        for nome, d in _todos(arqs).items():
            _sem_ti({k: v for k, v in d.items() if k != "meta"}, nome)


def test_embutir_copia_local(arquivos_demo):
    _, arqs = arquivos_demo
    el = PC.embutir(arqs)
    assert el.startswith(f'<script type="application/json" id="{PC.ELEMENTO_LOCAL}">')
    assert el.endswith("</script>") and el.count("</script") == 1 and el.count("<") == 2
    corpo = el[el.index(">") + 1: -len("</script>")]
    dados = json.loads(corpo)
    assert set(dados) == set(arqs)
    assert dados[PC.ARQUIVO] == json.loads(arqs[PC.ARQUIVO])


def test_gravar_remove_fragmentos_antigos_e_marca_publicacao(tmp_path, arquivos_demo):
    _, arqs = arquivos_demo
    (tmp_path / "cobertura-modelo-99.json").write_text("{}\n")
    (tmp_path / "data.json").write_text("{}\n")
    r = PC.gravar(tmp_path, arqs)
    assert r["removidos_do_disco"] == ["cobertura-modelo-99.json"]
    assert (tmp_path / "data.json").exists()
    assert sorted(p.name for p in tmp_path.glob("cobertura*.json")) == sorted(arqs)
    assert r["mudaram"] == sorted(arqs) and r["removidos"] == []
    PC.marcar_publicado(tmp_path, arqs)
    r2 = PC.gravar(tmp_path, arqs)
    assert r2["escritos"] == [] and r2["mudaram"] == [] and r2["removidos"] == []
    menos = {k: v for k, v in arqs.items() if k != sorted(arqs)[-1]}
    r3 = PC.gravar(tmp_path, menos)
    assert r3["removidos"] == [sorted(arqs)[-1]]


def test_resumo_e_carteira_do_painel(livro):
    class RT:
        book_root = livro

    r = PC.resumo(RT())
    assert r["disponivel"] is True and r["as_of"] == D2.isoformat() and r["dados_simulados"] is True
    assert len(json.dumps(r, ensure_ascii=False).encode()) <= 300

    class Vazio:
        book_root = Path("/nao/existe/livro")

    assert PC.resumo(Vazio()) == {"disponivel": False}
    assert PC.carteira_do_painel(None) is None
    assert PC.carteira_do_painel({"latest_day": {"positions": []}, "weeks": []}) is None
    pesos = PC.carteira_do_painel({"latest_day": None, "risk": {"live_week": "2026-10-09"},
                                   "weeks": [{"week": "2026-10-09", "proposal": {"positions": [
                                       {"issuer_id": "BR_VALE", "weight": -0.02}]}}]})
    assert pesos == {"BR_VALE": -0.02}


# ==========================================================================================
# Módulo da página
# ==========================================================================================

JS = PC.MODULO.read_text(encoding="utf-8")


def test_modulo_agulhas_e_limites():
    for agulha in ("window.CDP_COBERTURA", "render: render", "abrir:", '"Cobertura de ações e ETFs"',
                   '"Painel do universo"', '"Tabela de cobertura"', '"Ficha do ativo"', '"Histórico de acertos"',
                   '"ETFs"', '"Metodologia de avaliação"', '"Memória de cálculo"', '"Insumos e fontes"',
                   '"Lacunas e portões de qualidade"', '"Não foi possível carregar a cobertura."',
                   "function football", "function grafPreco", "function sensibilidade", "function ponte",
                   "function distribuicao", "function dispersao", "function grafCalib", "function grafIc",
                   "function grafCestas", "#cobertura:", "cdp-cobertura-dados", "dados/datapackage.json",
                   "forced-colors", "@media print"):
        assert agulha in JS, agulha
    assert "</script" not in JS.lower()
    assert len(JS.encode("utf-8")) <= 120_000
    assert max(len(x) for x in JS.splitlines()) <= 2_000
    assert PC.modulo_js().endswith("\n")
    assert PC.nome_modulo("a" * 64) == "painel-aaaaaaaaaaaaaaaa-cobertura.js"
    # dados por endereço relativo (nunca absoluto) ao lado da página
    for m in re.finditer(r"fetch\(([^,)]*)", JS):
        assert "http" not in m.group(1) and not m.group(1).strip().startswith('"/'), m.group(0)


def _tokens(js: str) -> list[tuple[str, str]]:
    """Tokens de JavaScript sem comentários; textos, expressões regulares e números marcados."""
    out: list[tuple[str, str]] = []
    i, n = 0, len(js)
    puncts = sorted(("===", "!==", "**=", "...", "**", "++", "--", "+=", "-=", "*=", "/=", "%=", "==", "!=",
                     "<=", ">=", "&&", "||", "=>", "??", "?.", "<<", ">>", "+", "-", "*", "/", "%", "=", "<", ">",
                     "!", "?", ":", ",", ";", ".", "(", ")", "[", "]", "{", "}", "&", "|", "^", "~"), key=len, reverse=True)
    kw_antes_de_expr = {"return", "typeof", "case", "in", "of", "new", "delete", "void", "throw", "else", "do"}

    def regex_ok() -> bool:
        if not out:
            return True
        k, t = out[-1]
        if k == "p":
            return t not in (")", "]", "}")
        return k == "id" and t in kw_antes_de_expr

    while i < n:
        c = js[i]
        if js.startswith("//", i):
            i = js.find("\n", i)
            i = n if i < 0 else i
        elif js.startswith("/*", i):
            i = js.index("*/", i) + 2
        elif c in "\"'`":
            j = i + 1
            while js[j] != c:
                j += 2 if js[j] == "\\" else 1
            out.append(("s", js[i:j + 1]))
            i = j + 1
        elif c == "/" and regex_ok():
            j, classe = i + 1, False
            while True:
                ch = js[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "[":
                    classe = True
                elif ch == "]":
                    classe = False
                elif ch == "/" and not classe:
                    break
                j += 1
            j += 1
            while j < n and js[j].isalpha():
                j += 1
            out.append(("re", js[i:j]))
            i = j
        elif c.isspace():
            i += 1
        elif c.isdigit():
            m = re.match(r"\d+(\.\d+)?", js[i:])
            out.append(("n", m.group(0)))
            i += len(m.group(0))
        elif c.isalpha() or c in "_$":
            m = re.match(r"[\w$]+", js[i:])
            out.append(("id", m.group(0)))
            i += len(m.group(0))
        else:
            p = next(p for p in puncts if js.startswith(p, i))
            out.append(("p", p))
            i += len(p)
    return out


_LIMITES_EXPR = {",", ";", "?", ":", "=", "=>", "&&", "||", "??", "==", "===", "!=", "!==", "<", ">", "<=", ">=",
                 "return", "!"}


def _cadeia_tem_texto(tok: list[tuple[str, str]], i: int) -> bool:
    """A expressão de soma em torno do ``+`` na posição ``i`` (mesma profundidade de
    parênteses) contém um texto literal — ou seja, é concatenação, não conta."""
    for passo in (-1, 1):
        j, prof = i + passo, 0
        while 0 <= j < len(tok):
            k, t = tok[j]
            if t in ("(", "[", "{"):
                prof += passo
            elif t in (")", "]", "}"):
                prof -= passo
            if prof < 0:
                break
            if prof == 0:
                if t in _LIMITES_EXPR or (k == "id" and t == "return"):
                    break
                if k == "s":
                    return True
            j += passo
    return False


def problemas_de_conta(js: str) -> list[str]:
    """Contas sobre números no JavaScript (a página nunca calcula): ``* / %``, menos binário,
    ``+`` fora de concatenação de textos, atribuições compostas numéricas e funções numéricas."""
    tok = _tokens(js)
    out = []
    for i, (k, t) in enumerate(tok):
        ant = tok[i - 1] if i else ("p", ";")
        if k == "p" and t in ("*", "/", "%", "**", "*=", "/=", "%=", "**=", "-=", "--"):
            out.append(f"operador {t!r} no token {i}")
        elif k == "p" and t == "-":
            binario = ant[0] in ("id", "n", "s") and ant[1] not in ("return", "case", "typeof") or ant[1] in (")", "]")
            if binario:
                out.append(f"menos binário no token {i} ({ant[1]} - …)")
        elif k == "p" and t == "+":
            unario = ant[0] == "p" and ant[1] not in (")", "]")
            if unario or not _cadeia_tem_texto(tok, i):
                out.append(f"soma numérica no token {i} ({ant[1]} + {tok[i + 1][1]})")
        elif k == "p" and t == "+=":
            if tok[i + 1][0] != "s":
                out.append(f"'+=' sem texto no token {i}")
        elif k == "id" and t in ("Math", "toFixed", "toPrecision", "parseFloat", "parseInt", "Number",
                                 "NumberFormat", "toLocaleString", "Intl"):
            out.append(f"função numérica {t}")
    return out


def test_verificador_de_contas_pega_contas():
    for ruim in ("var a = r.target / r.price;", "var u = x - 1;", "var s = a + b;", "w = v * 100;",
                 "y = Math.round(v);", "t = v.toFixed(2);", "i += 1;", "z = (a) - (b);", "q = n % 2;",
                 'k = "a" + (x + y);'):
        assert problemas_de_conta(ruim), ruim
    for bom in ('var s = "a" + b + (c ? " d" : "");', "for (var i = 0; i < n; i++) {}", "return -1;",
                'el.style.left = x + "%";', "var r = /a\\/b/.test(s) ? -1 : 1;", 'x += "texto";',
                'f(a, -2, "-");'):
        assert not problemas_de_conta(bom), (bom, problemas_de_conta(bom))


def test_modulo_nao_faz_contas_sobre_os_dados():
    assert problemas_de_conta(JS) == []
    # nenhum campo numérico dos dados aparece numa conta (a geometria chega pronta, de 0 a 100)
    codigo = " ".join(t for k, t in _tokens(JS) if k not in ("s", "re"))
    assert not re.search(r"(?:price|preco|target|alvo|upside)\s*[-*/]", codigo)
    assert "- 1 )" not in codigo and "/ r . price" not in codigo


def test_modulo_em_portugues():
    textos = [t for k, t in _tokens(JS) if k == "s"]
    ingles = re.compile(r"\b(Loading|Error|Download|Click|Show|Hide|Filter|Search|Price|Target|Upside"
                        r"|Coverage|Sector|Country|Weight|Model|Sources?|Inputs?|Steps?)\b")
    for t in textos:
        assert not ingles.search(t), t


# ==========================================================================================
# Correções da revisão: fragmentos estáveis, ETFs, texto, livro em conferência, metodologia
# ==========================================================================================


def test_um_pregao_a_mais_muda_so_o_resumo_e_os_precos(livro, mercado):
    """Mesmo retrato (D1), base de mercado um pregão e uma semana à frente: os fragmentos de
    histórico e de modelo não mudam; os fechamentos posteriores ao retrato chegam em
    ``cobertura-precos.json``, já na escala do gráfico."""
    antes = PC.exportar(PC.carregar(livro, ate=D1, md=mercado.load(D1)))
    for depois_de in (date(2026, 10, 9), date(2026, 10, 15)):
        depois = PC.exportar(PC.carregar(livro, ate=D1, md=mercado.load(depois_de)))
        assert set(depois) == set(antes)
        mudaram = {n for n in depois if depois[n] != antes[n]}
        assert mudaram <= {PC.ARQUIVO, PC.ARQUIVO_PRECOS}, sorted(mudaram)
        assert PC.ARQUIVO_PRECOS in mudaram
    precos = expandir(json.loads(depois[PC.ARQUIVO_PRECOS]))
    assert precos["meta"]["modelos_em"] == D1.isoformat()
    com_trecho = [p for p in precos["precos"] if p.get("g")]
    assert com_trecho
    for p in com_trecho:
        assert p["d"] > D1.isoformat()
        assert 0 <= p["g"]["x"] <= 100 and 0 <= p["g"]["y"] <= 100
        assert re.fullmatch(r"M[\d. ]+(L[\d. ]+)+", p["g"]["c"]), p["g"]["c"]
    # o histórico do fragmento termina na data dos preços do retrato
    docs = _todos(antes)
    for n, d in docs.items():
        if n.startswith(PC.PREFIXO_HISTORICO):
            for h in d["series"].values():
                if h.get("vazio"):
                    continue
                assert "hoje" not in h and 0 <= h["retrato"] <= 100
                assert h["ultimo"] is None or h["ultimo"]["d"] <= D1.strftime("%d/%m/%Y")


def test_etf_com_preco_alvo_faixa_de_90_e_legenda_propria(arquivos_demo):
    ent, arqs = arquivos_demo
    docs = _todos(arqs)
    series = {}
    for n, d in docs.items():
        if n.startswith(PC.PREFIXO_HISTORICO):
            series.update(d["series"])
    c = docs[PC.ARQUIVO]
    citaveis = [u for u in c["universe"] if u["tipo"] == "etf" and u["citavel"]]
    assert citaveis
    for u in citaveis:
        h = series[u["iid"]]
        assert h["etf"] is True and h["leque"]
        rot = [r["t"] for r in h["leque"]["rotulos"]]
        assert rot[0].startswith("limite superior (90%)") and rot[1].startswith("preço-alvo")
        assert all(t[1] in PC.VISOES_ETF for t in h["tons"])
        assert h["tabela"][0]["alvo"] == u["alvo_texto"]


def test_texto_de_exibicao_sem_codigos_internos(arquivos_demo):
    nomes = {"BR_ABC": "Banco ABC Brasil", "BR_B3": "B3"}
    casos = {
        "VALE3.SA (LOCAL, BRL): linha cotada": "VALE3 (ação local, BRL): linha cotada",
        "AUGO (US_LISTED)": "AUGO (listada nos EUA)",
        "TP × câmbio BRL→USD esperado": "preço-alvo × câmbio BRL→USD esperado",
        "pares: Brasil × Materials, 8 nomes (BR_ABC, BR_B3)": "pares: Brasil × Materiais, 8 nomes (Banco ABC Brasil, B3)",
        "mediana de 24 emissores de Financials × banco": "mediana de 24 emissores de Financeiro × bancos",
        "BR × Financials": "Brasil × Financeiro",
        "G4 ke no envelope dos pares: nao_aplicavel (menos de 4)": "G4 ke no envelope dos pares: não se aplica (menos de 4)",
        "ex.: carteira_credito A salto de 2.67e+03× entre": "ex.: carteira de crédito (anual) salto de 2.670× entre",
        "ETR do caso-base ≥ ke com upside positivo": "retorno esperado do caso-base ≥ ke com potencial positivo",
        "α_rel 43,54% vs limiar": "α relativo 43,54% contra limiar",
        "3 métodos, CV 2%, insumos point-in-time": "3 métodos, CV 2%, insumos disponíveis na data",
        "ações: unidade ok(herdada)": "ações: unidade conferida, herdada do período anterior",
        "status: fx_corrigido": "câmbio corrigido na conversão",
        "Real Estate (Development)": "Real Estate (Development)",  # nome de categoria da fonte
        "Vista Energy": "Vista Energy",
    }
    for bruto, esperado in casos.items():
        assert PC._pt(bruto, nomes) == esperado, bruto
    assert PC._nome_posicao("YPF S.A.-SPONSORED ADR") == "YPF S.A."
    assert PC._nome_posicao("PAMPA ENERGIA SA-SPON ADR") == "Pampa Energia S.A."
    assert PC._nome_posicao("VISTA ENERGY SAB DE CV") == "Vista Energy S.A.B. de C.V."
    # portões: situação em português e contada no resumo
    ps = [{"codigo": "G1", "status": "ok"}, {"codigo": "G4", "status": "nao_aplicavel"},
          {"codigo": "G9", "status": "sem_alvo"}]
    assert [p["s"] for p in PC._portoes(ps)] == ["Conferido", "Não se aplica", "Sem preço-alvo"]
    assert PC._resumo_portoes(ps) == "1 conferido · 0 avisos · 0 bloqueios · 1 não se aplica · 1 outro"
    # nos arquivos publicados: nenhum símbolo do provedor nem tipo de linha fora dos endereços
    proibido = re.compile(r"\.(SA|MX|SN)\b|US_LISTED|\(LOCAL\b|nao_aplicavel|point-in-time|\bETR\b|\bupside\b|α_rel\b")

    def andar(x: Any, onde: str) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k not in ("url", "id", "i", "iid", "dados", "rel", "ticker", "linha"):
                    andar(v, f"{onde}.{k}")
        elif isinstance(x, list):
            for v in x:
                andar(v, onde)
        elif isinstance(x, str) and not x.startswith("http"):
            assert not proibido.search(x), f"{onde} = {x!r}"

    for n, d in _todos(arquivos_demo[1]).items():
        andar({k: v for k, v in d.items() if k != "meta"}, n)


def test_colunas_da_projecao_na_ordem_da_conta(grande):
    _, arqs = grande
    modelos = {}
    for n, t in arqs.items():
        if n.startswith(PC.PREFIXO_MODELO):
            modelos.update(expandir(json.loads(t))["modelos"])
    m = modelos["BR_E000"]
    cols = [c["k"] for c in m["metodos"][0]["colunas"]]
    assert cols == ["receita", "crescimento", "nopat", "reinvestimento", "fcff"]
    assert m["metodos"][0]["colunas"][2]["t"] == "Lucro operacional após impostos"
    assert all("Perda esperada" not in a for a, _ in m["cenarios"]["resumo"])
    assert any(a == "Retorno médio nos 10% piores sorteios" for a, _ in m["cenarios"]["resumo"])


def test_livro_que_nao_confere_fica_em_verificacao(livro, tmp_path):
    import shutil

    from cdp.cobertura.livro import LivroErro

    out = expandir(json.loads(PC.exportar(None, estado="em_verificacao")[PC.ARQUIVO]))
    assert out["meta"]["estado"] == "em_verificacao" and out["universe"] == []
    with pytest.raises(ValueError):
        PC.exportar(None, estado="outro")
    copia = tmp_path / "book"
    shutil.copytree(livro, copia)
    p = copia / "cobertura" / "livro.jsonl"
    linhas = p.read_text(encoding="utf-8").splitlines(keepends=True)
    p.write_text("".join(linhas[:-1]), encoding="utf-8")  # execução interrompida

    class RT:
        book_root = copia

    assert PC.resumo(RT()) == {"disponivel": False, "estado": "em_verificacao"}
    with pytest.raises(LivroErro):
        PC.carregar(copia)
    assert "em_verificacao" in JS and "Os modelos da cobertura estão em conferência" in JS


def test_metodologia_da_configuracao_e_enderecos_fixos(livro, mercado):
    ent = PC.carregar(livro, md=mercado.load(D2), versao="0123abcd" * 5)
    arqs = PC.exportar(ent)
    c = expandir(json.loads(arqs[PC.ARQUIVO]))
    met = c["methodology"]
    ke = " | ".join(met["ke"])
    assert "δ do país" in ke and "limitado a [0,50; 1,80]" in ke and "±1,5 p.p." in ke
    assert "0,67 × β + 0,33" in ke and "não é prêmio de risco" in ke
    assert "não dimensiona posições" in met["carteira"] and "peso no alpha é zero" in met["carteira"]
    assert "26 semanas" in met["carteira"]
    for ln in met["links"]:
        assert "/main/" not in ln["u"] and not re.search(r"\.md|src/", ln["t"]), ln
    assert met["repo_livro"].endswith("/blob/" + "0123abcd" * 5 + "/book/")
    # os fragmentos não levam a versão do repositório (não mudam a cada publicação)
    for n, t in arqs.items():
        if n != PC.ARQUIVO:
            assert "0123abcd" not in t and "github.com" not in t, n
    assert PC.exportar(PC.carregar(livro, md=mercado.load(D2), versao="fedcba98" * 5)).keys() == arqs.keys()
    # placar: texto do mínimo sem confundir com o número de previsões; referência só com estudo citado
    t0 = c["track_record"]["tiles"][0]
    assert t0["maturacao"] and "a taxa é publicada a partir de 20 vencidas" in t0["sub"]
    assert t0["ref"] is None
    lit = {"tpmet12": {"faixa": [0.24, 0.38], "fonte": "Estudo citado, 2013"}}
    assert PC._referencia(lit, "tpmet12") == "referência: 24%–38% (Estudo citado, 2013)"
    assert PC._referencia({"tpmet12": [0.24, 0.38]}, "tpmet12") is None


def test_modulo_abre_a_ficha_pedida_de_qualquer_aba_e_imprime_so_a_ficha():
    for agulha in ('window.addEventListener("hashchange"', "iid !== ATUAL", "cv-com-ficha", "marcarImpressao",
                   ".cv-imp-aviso", "repo_livro", "cv-thp", "cv-alvo-b", "posicaoEtf", "x.colunas",
                   "na carteira", "clip-path"):
        assert agulha in JS, agulha
    assert "cv-pid" not in JS and "Bottom-up" not in JS and "top-down" not in JS
