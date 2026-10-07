"""Ponte EBIT: PDFs mínimos originais DADOS SIMULADOS e leitor real; recusa segura."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from cdp.cobertura.contexto import montar_contexto
from cdp.cobertura.fontes import DadosPublicos, coletar
from cdp.cobertura.formato import r6
from cdp.cobertura.insumos import preparar, preparar_emissor
from cdp.cobertura.margens import margens_alinhadas
from cdp.cobertura.modelo import Avaliador
from cdp.cobertura.motor import arredondar, modelar, tp_deterministico
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.resultado import ponte_fato, visao
from cdp.data import publico_resultados as R
from cdp.data.publico_arquivo import Arquivo
from cdp.data.synthetic import make_synthetic_market

D = date(2026, 10, 7)
CORTE = datetime(2026, 10, 7, 6, tzinfo=UTC)
CAPTURA = datetime(2026, 10, 7, 4, 9, 1, tzinfo=UTC)
FIXTURE = Path(__file__).parents[1] / "fixtures/cdp/resultado_ri"


@pytest.fixture
def primario():
    estrutura = json.loads((FIXTURE / "catalogo_sintetico.json").read_text())
    dados = [
        (FIXTURE / name).read_bytes() for name in ("anual_simulado.pdf", "semestre_simulado.pdf")
    ]
    bs = {hashlib.sha256(b).hexdigest(): b for b in dados}
    partes = [R.extrair(bs[d["sha256"]], d, CAPTURA, CORTE) for d in estrutura["documentos"]]
    return estrutura, R.construir(partes, estrutura, CORTE), bs


def _f(cat, item="ebit", freq="TTM", fim="2026-06-30"):
    fs = [f for f in cat["fatos"] if (f["item"], f["freq"], f["fim"]) == (item, freq, fim)]
    return next((f for f in fs if f.get("componentes")), fs[0])


def _rehash(c):
    c.pop("catalogo_sha256", None)
    c["catalogo_sha256"] = R.hash_obj(c)
    return c


def _pac(cat):
    fs = R.tabela_fatos(cat)
    fontes = {
        "t." + str(r["item"]): {"fato_resultado_id": r["fato_resultado_id"]}
        for r in fs[fs["period_end"] == "2026-06-30"].to_dict("records")
        if r["freq"] == "TTM"
    }
    p = {
        "issuer_id": "DADOS_SIMULADOS_ENTIDADE",
        "as_of": D.isoformat(),
        "corte_temporal": {"metodo": "base_preco_conhecimento_explicitos", "base_preco": D.isoformat(),
                           "data_modelo": D.isoformat(), "conhecimento_ate": cat["conhecimento_ate"]},
        "moeda": "MXN",
        "fator_moeda": 1.0,
        "resultado_evidencias": R.texto_json(cat),
        "t.ebit": r6(float(_f(cat)["valor"])),
        "t.ebitda": 260000000.0,
        "t.d_a": r6(float(_f(cat, "d_a")["valor"])),
        "t.cfo": 120000000.0,
        "eps_fy1": 23.0,
        "eps_ttm": 30.0,
        "t.lucro_liquido": 160000000.0,
        "fontes": fontes,
        "tabela_insumos": [],
        "lacunas": [],
        "historico": {"ebit": {}, "receita": {}},
        "periodos_fluxos": {k: "TTM|2026-06-30" for k in ("ebit", "receita", "d_a")},
        "bases_fluxos": {k: "consolidado" for k in ("ebit", "receita", "d_a")},
        "moedas_fluxos": {k: "MXN" for k in ("ebit", "receita", "d_a")},
        "t.receita": r6(float(_f(cat, "receita")["valor"])),
        "historico_fontes": {"ebit": {}, "receita": {}},
        "historico_periodos": {"ebit": {}, "receita": {}},
        "historico_bases": {"ebit": {}, "receita": {}},
        "historico_moedas": {"ebit": {}, "receita": {}},
    }
    for it in ("ebit", "receita"):
        for ano in ("2023", "2024", "2025"):
            f = _f(cat, it, "A", ano + "-12-31")
            v = r6(float(f["valor"]))
            p["historico"][it][ano] = v
            p["historico_fontes"][it][ano] = {"fato_resultado_id": f["fato_id"], "valor_modelo": v}
            p["historico_periodos"][it][ano] = "A|" + ano + "-12-31"
            p["historico_bases"][it][ano] = "consolidado"
            p["historico_moedas"][it][ano] = "MXN"
    return p


def test_identidade_anual_ttm_e_camadas_sem_dupla_subtracao(primario):
    _, c, _ = primario
    a = ponte_fato(
        _f(c, freq="A", fim="2025-12-31")["fato_id"], c, issuer_id="DADOS_SIMULADOS_ENTIDADE"
    )
    d = ponte_fato(_f(c)["fato_id"], c, issuer_id="DADOS_SIMULADOS_ENTIDADE")
    assert a["reportado"] == "230000000" and a["apos_ajustes"] == "200000000"
    assert d["reportado"] == "250000000" and d["apos_ajustes"] == "220000000"
    assert [x["coeficiente_evento"] for x in d["ajustes"]] == ["1", "0", "0"]
    assert [x["trilha"][0]["coeficiente"] for x in d["ajustes"]] == ["1", "1", "-1"]
    assert d["disponivel_desde"] == CAPTURA.isoformat()
    assert _f(c)["ttm_reportado_fato_ids"]
    p = _pac(c)
    q = visao(p, carregar_parametros())
    assert p["t.ebit"] != q["t.ebit"] and p == q["resultado_reportado"] | {
        k: v for k, v in p.items() if k not in q["resultado_reportado"]
    }
    assert q["t.ebit"] == r6(220000000.0) and q["t.ebitda"] == r6(220000000.0 + 28000000.0)
    for k in ("t.cfo", "eps_fy1", "eps_ttm", "t.lucro_liquido"):
        assert q[k] == p[k]
    assert visao(q, carregar_parametros()) == q
    assert visao(arredondar(q), carregar_parametros()) == arredondar(q)
    margem = margens_alinhadas(q)
    assert margem["corrente"]["margem"] == q["t.ebit"] / q["t.receita"]
    assert margem["historico"]["2025"]["status"] == "comparavel"
    assert q["historico_fontes"]["ebit"]["2025"]["valor_modelo"] == q["historico"]["ebit"]["2025"]
    assert q["historico"]["ebit"]["2024"] == p["historico"]["ebit"]["2024"]
    assert c["eventos"][0]["imposto_evento"] is None and c["eventos"][0]["eps_ajustado"] is None


@pytest.mark.parametrize(
    "defeito",
    ["bind_ausente", "bind_duplicado", "moeda", "base", "valor_fornecedor", "competencia_parcial"],
)
def test_falta_conflito_parcial_nao_vira_zero_nem_bind_por_valor_proximo(primario, defeito):
    _, c, _ = primario
    c = deepcopy(c)
    p = _pac(c)
    if defeito == "bind_ausente":
        c["bindings"] = []
    elif defeito == "bind_duplicado":
        c["bindings"] += deepcopy(c["bindings"])
    elif defeito in ("moeda", "base"):
        c["eventos"][0][defeito] = "USD" if defeito == "moeda" else "individual"
    elif defeito == "competencia_parcial":
        c["eventos"][0]["reconhecimento_fim"] = "2026-09-30"
    else:
        p["fontes"]["t.ebit"] = {"fonte": "YAHOO", "valor_aproximado": p["t.ebit"]}
    p["resultado_evidencias"] = R.texto_json(_rehash(c))
    q = visao(p, carregar_parametros())
    assert q["t.ebit"] is None and q["t.ebitda"] is None and q["t.cfo"] == p["t.cfo"]
    assert q["eps_fy1"] == p["eps_fy1"] and q["lacunas"]


def test_evento_fora_da_janela_tem_zero_temporal_sem_lacuna(primario):
    _, c, _ = primario
    f = _f(c, freq="A", fim="2024-12-31")
    d = ponte_fato(f["fato_id"], c, issuer_id="DADOS_SIMULADOS_ENTIDADE")
    assert (
        d["contribuicao_excluida"] == "0" and d["apos_ajustes"] == f["valor"] and not d["recusas"]
    )
    assert d["ajustes"][0]["estado"] == "fora_janela"


def test_ganho_perda_simetrico_sem_selecao_por_nome(primario):
    _, c, _ = primario
    c = deepcopy(c)
    ev = c["eventos"][0]
    ev["contribuicao_pre_imposto"] = "-30000000"
    for f in c["fatos"]:
        if f["fato_id"] == ev["medida_fato_id"]:
            f["valor"] = "-30000000"
        f["issuer_id"] = "QUALQUER_ENTIDADE"
    ev["issuer_id"] = "QUALQUER_ENTIDADE"
    d = ponte_fato(_f(c)["fato_id"], c, issuer_id="QUALQUER_ENTIDADE")
    assert d["apos_ajustes"] == "280000000"


def test_tamper_catalogo_pacote_contexto_e_idempotencia(primario):
    _, c, _ = primario
    p = _pac(c)
    params = carregar_parametros()
    q = visao(p, params)
    for campo in ("t.ebit", "t.d_a"):
        adulterado = deepcopy(q)
        adulterado[campo] += 1e6
        with pytest.raises(ValueError, match="adulterada|recálculo"):
            visao(adulterado, params)
    adulterado = deepcopy(q)
    adulterado["resultado_reportado"]["t.ebit"] += 100
    with pytest.raises(ValueError, match="reportado adulterado|diverge numericamente"):
        visao(adulterado, params)
    c["eventos"][0]["contribuicao_pre_imposto"] = "999"
    p["resultado_evidencias"] = R.texto_json(c)
    with pytest.raises(ValueError, match="catálogo adulterado"):
        visao(p, params)


def test_publicacao_first_capture_intradia_e_ids_estaveis(primario):
    estrutura, c, bs = primario
    d = estrutura["documentos"][0]
    antes = R.extrair(bs[d["sha256"]], d, CAPTURA, datetime(2026, 10, 7, 4, tzinfo=UTC))
    assert not antes["fatos"] and not antes["provas"]
    outra = R.extrair(bs[d["sha256"]], d, datetime(2026, 10, 7, 5, tzinfo=UTC), CORTE)
    assert {f["fato_id"] for f in outra["fatos"]} <= {f["fato_id"] for f in c["fatos"]}
    with pytest.raises(ValueError, match="fuso"):
        R.extrair(bs[d["sha256"]], d, CAPTURA, datetime(2026, 10, 7, 6))
    with pytest.raises(ValueError, match="SHA"):
        R.extrair(b"PDF adulterado", d, CAPTURA, CORTE)


def test_coleta_online_offline_feed_canonico_e_bruto_imutavel(primario, tmp_path):
    estrutura, c, bs = primario
    por_url = {d["url"]: bs[d["sha256"]] for d in estrutura["documentos"]}
    arq = Arquivo(tmp_path, agora=lambda: CAPTURA)
    f, cat = R.coletar_resultados(
        ["DADOS_SIMULADOS_ENTIDADE"],
        arquivo=arq,
        conhecimento_ate=CORTE,
        http_get=por_url.get,
        estrutura=estrutura,
    )
    offline = Arquivo(tmp_path, offline=True)
    f2, c2 = R.coletar_resultados(
        ["DADOS_SIMULADOS_ENTIDADE"],
        arquivo=offline,
        conhecimento_ate=CORTE,
        http_get=lambda _: pytest.fail("rede offline"),
        estrutura=estrutura,
    )
    assert f.equals(f2) and cat == c2 and f["fato_resultado_id"].notna().all()
    assert len(arq.registros()) == 2 and len(cat["documentos"]) == 2
    assert all(arq.ler(r) == bs[r.sha256] for r in arq.registros())
    before, catbefore = R.coletar_resultados(
        ["DADOS_SIMULADOS_ENTIDADE"],
        arquivo=offline,
        conhecimento_ate=datetime(2026, 10, 7, 4, tzinfo=UTC),
        estrutura=estrutura,
    )
    assert not catbefore["eventos"] and not catbefore["bindings"]
    assert not before.empty  # H126 com data de anúncio própria; ganho auditado ainda desconhecido.


def test_da_indeterminada_nao_recria_ebitda_no_contexto(primario):
    _, c, _ = primario
    p = _pac(c)
    p["fontes"]["t.d_a"] = {"fonte": "YAHOO"}
    q = visao(p, carregar_parametros())
    assert q["t.ebit"] is not None and q["t.ebitda"] is None
    assert not q["resultado_ebitda_base"]["disponivel"]


@pytest.fixture
def universo(primario):
    _, c, _ = primario
    md = make_synthetic_market(seed=7, as_of=D)
    params = carregar_parametros()
    ids = list(md.universe.issuers.index)
    dados = coletar(md, D, ids, list(md.universe.lines.index), [], params=params, conhecimento_ate=CORTE)
    iid = next(i for i in ids if md.universe.issuers.loc[i, "gics_sector"] != "Financials")
    # Fatos documentais em universo sintético para verificar todos os consumidores sem rede.
    c = deepcopy(c)
    for f in c["fatos"]:
        f["issuer_id"] = iid
    for e in c["eventos"]:
        e["issuer_id"] = iid
    for f in c["fatos"]:
        f["moeda"] = "BRL"
    for e in c["eventos"]:
        e["moeda"] = "BRL"
    _rehash(c)
    dem = R.tabela_fatos(c)
    old = dados.demonstrativos
    keys = {(r.item, r.freq, str(r.period_end)) for r in dem.itertuples()}
    keep = [
        not (
            r.issuer_id == iid
            and (r.item, r.freq, pd.Timestamp(r.period_end).date().isoformat()) in keys
        )
        for r in old.itertuples()
    ]
    novo = DadosPublicos(
        **{
            **dados.__dict__,
            "demonstrativos": pd.concat([old.loc[keep], dem], ignore_index=True),
            "resultado_evidencias": pd.DataFrame([{"catalogo_json": R.texto_json(c)}]),
        }
    )
    pacs = preparar(md, novo, params, ids, D)
    return md, params, novo, pacs, iid


def test_preparador_contexto_consumidores_diretos_e_ausencia_nao_bypass(universo):
    _, params, _, pacs, iid = universo
    orig = deepcopy(pacs)
    ctx = montar_contexto(pacs, params, 0.045)
    v = visao(pacs[iid], params)
    assert pacs == orig and v["t.ebit"] != pacs[iid]["t.ebit"]
    assert ctx["fundamentos"][iid]["margem"] == r6(v["t.ebit"] / v["t.receita"])
    assert (
        ctx["fundamentos"][iid]["roic_pre"]
        < montar_contexto(pacs, _legado(params), 0.045)["fundamentos"][iid]["roic_pre"]
    )
    av = Avaliador(pacs[iid], ctx, params, 0.045, {})
    assert av.pac["t.ebit"] == v["t.ebit"] and arredondar(av.fund) == arredondar(
        ctx["fundamentos"][iid]
    )
    assert tp_deterministico(v, ctx, params, 0.045) == tp_deterministico(
        pacs[iid], ctx, params, 0.045
    )
    antigo = montar_contexto(pacs, _legado(params), 0.045)
    with pytest.raises(ValueError, match="contexto"):
        Avaliador(pacs[iid], antigo, params, 0.045, {})
    with pytest.raises(ValueError, match="contexto"):
        modelar(pacs, antigo, params, 0.045, {})
    errado = deepcopy(ctx)
    errado["fundamentos"][iid]["margem"] = 999
    with pytest.raises(ValueError, match="contexto adulterado"):
        tp_deterministico(pacs[iid], errado, params, 0.045)
    recalc = montar_contexto({i: visao(p, params) for i, p in pacs.items()}, params, 0.045)
    assert arredondar(ctx) == arredondar(recalc)


def _legado(p):
    p = deepcopy(p)
    p.sec("projecao").pop("normalizacao_resultado_metodo", None)
    p.sec("projecao").pop("resultado_corte_metodo", None)
    return p


@pytest.mark.parametrize("versao", ["2026-10.4", "2026-10.5", "2026-10.6"])
def test_sem_chave_nao_muda_schema_hash_ou_numeros_anteriores(universo, versao):
    md, p, dados, pacs, iid = universo
    p = _legado(p)
    p.valuation["versao"] = versao
    raw = deepcopy(pacs[iid])
    raw.pop("resultado_evidencias", None)
    assert visao(raw, p) == raw and "visao_resultado" not in visao(raw, p)
    p2 = deepcopy(p)
    p2.valuation["versao"] = "identica_sem_chave"
    c1 = montar_contexto({iid: raw}, p, 0.045)
    c2 = montar_contexto({iid: raw}, p2, 0.045)
    assert c1 == c2 and "visoes_resultado" not in c1
    a1 = Avaliador(raw, c1, p, 0.045, {}).avaliar()
    a2 = Avaliador(raw, c2, p2, 0.045, {}).avaliar()
    assert a1 == a2 and "visao_resultado" not in a1
    normal = preparar_emissor(
        md, DadosPublicos(**{**dados.__dict__, "resultado_evidencias": pd.DataFrame()}), p, iid, D
    )
    assert "resultado_evidencias" not in normal


def test_alias_identico_dedupe_conserva_primeira_captura(primario):
    estrutura, c, bs = primario
    d = estrutura["documentos"][0]
    a = R.extrair(bs[d["sha256"]], d, CAPTURA, CORTE)
    alias = deepcopy(d)
    alias["url"] = "https://fonte-primaria.example/alias-mesmos-bytes.pdf"
    b = R.extrair(bs[d["sha256"]], alias, datetime(2026, 10, 7, 5, tzinfo=UTC), CORTE)
    cat = R.construir([a, b], estrutura, CORTE)
    assert len(cat["documentos"]) == 1 and len(cat["eventos"]) == 1 and len(cat["bindings"]) == 1
    assert cat["documentos"][0]["first_capture"] == CAPTURA.isoformat()
    assert len(cat["documentos"][0]["urls"]) == 2
    anual = _f(cat, freq="A", fim="2025-12-31")
    assert (
        ponte_fato(anual["fato_id"], cat, issuer_id="DADOS_SIMULADOS_ENTIDADE")["apos_ajustes"]
        == "200000000"
    )


def test_traco_e_ausencia_nao_sao_zero_de_evento_ou_rou(primario):
    _, c, _ = primario
    antes = [
        f
        for f in c["fatos"]
        if f["item"] == "ganho_alienacao_controle" and f["fim"] == "2024-12-31"
    ]
    assert len(antes) == 1 and antes[0]["valor"] is None and antes[0]["valor_bruto"] is None
    assert not any(f["item"] == "adicoes_direito_uso" for f in c["fatos"])
    p = visao(_pac(c), carregar_parametros())
    assert (
        p.get("t.adicoes_direito_uso") is None
        and p.get("t.variacao_capital_giro_operacional") is None
    )


def test_contexto_calibracao_sem_evento_mantem_numeros_legados(universo):
    _, params, _, pacs, _ = universo
    sem = deepcopy(pacs)
    for p in sem.values():
        p.pop("resultado_evidencias", None)
    c7 = montar_contexto(sem, params, 0.045)
    c6 = montar_contexto(sem, _legado(params), 0.045)
    assert c7["calibracao_pais"] == c6["calibracao_pais"] and c6["calibracao_pais"]
    for k in ("regressoes", "normas_roe", "porte", "premio_implicito", "setores", "universo"):
        assert c7[k] == c6[k], k


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("periodos_fluxos", "TTM|2026-12-31"),
        ("bases_fluxos", "individual"),
        ("moedas_fluxos", "USD"),
    ],
)
def test_fato_id_nao_autoriza_metadado_incompativel(primario, campo, valor):
    _, c, _ = primario
    p = _pac(c)
    p[campo]["ebit"] = valor
    q = visao(p, carregar_parametros())
    assert q["t.ebit"] is None
    assert q["visao_resultado"]["diagnostico"]["corrente"]["status"] == "vinculo_conflitante"


def test_hora_corte_posterior_ao_pacote_recusada(primario):
    _, c, _ = primario
    p = _pac(c)
    p["as_of"] = "2026-10-06"
    params = deepcopy(carregar_parametros())
    params.sec("projecao").pop("resultado_corte_metodo", None)
    p.pop("corte_temporal", None)
    with pytest.raises(ValueError, match="conhecimento posterior"):
        visao(p, params)


def test_g1_confere_reportado_enquanto_g13_recebe_visao(universo):
    from cdp.cobertura.qualidade import portoes_emissor

    _, params, _, pacs, iid = universo
    pacs[iid]["t.ebitda"] = 1.0
    ctx = montar_contexto(pacs, params, 0.045)
    q = visao(pacs[iid], params)
    mod = Avaliador(q, ctx, params, 0.045, {}).avaliar()
    assert q["t.ebitda"] == r6(q["t.ebit"] + q["t.d_a"])
    gates = portoes_emissor(q, mod, params)
    g1 = next(g for g in gates if g["codigo"] == "G1")
    assert g1["status"] == "informativo"
    assert "EBITDA ≠ EBIT + D&A" in g1["detalhe"]
    g13b = next(g for g in gates if g["codigo"] == "G13b")
    assert g13b["status"] == "ok"


def test_republicacao_seleciona_fato_por_versao_e_disponibilidade_sem_repetir_evento(primario):
    estrutura, c, bs = primario
    partes = [R.extrair(bs[d["sha256"]], d, CAPTURA, CORTE) for d in estrutura["documentos"]]
    nova = deepcopy(partes[0])
    sha = hashlib.sha256(b"DADOS SIMULADOS: republicacao primaria").hexdigest()
    tarde = datetime(2026, 10, 7, 5, tzinfo=UTC).isoformat()
    for d in nova["documentos"]:
        d.update(documento_id=sha, sha256=sha, disponivel_desde=tarde, first_capture=tarde)
    for f in nova["fatos"]:
        f.update(documento_id=sha, versao=2, disponivel_desde=tarde)
        f["fato_id"] = R.hash_obj({"republicacao": sha, "anterior": f["fato_id"]})
    for p in nova["provas"]:
        p.update(documento_id=sha, disponivel_desde=tarde)
        p["prova_id"] = R.hash_obj({"republicacao": sha, "anterior": p["prova_id"]})
    estrutura = deepcopy(estrutura)
    for e in estrutura["eventos"]:
        e["medida_documentos"].append(sha)
        e["documentos_prova"].append(sha)
    cat = R.construir([*partes, nova], estrutura, CORTE)
    assert (
        len(cat["eventos"]) == 1 and cat["eventos"][0]["evento_id"] == c["eventos"][0]["evento_id"]
    )
    assert len(cat["bindings"]) == 1
    assert cat["eventos"][0]["disponivel_desde"] == tarde
    atual = _f(cat)
    assert atual["disponivel_desde"] == tarde
    assert (
        next(f for f in cat["fatos"] if f["fato_id"] == atual["componentes"][0]["fato_id"])[
            "versao"
        ]
        == 2
    )
    ponte = ponte_fato(atual["fato_id"], cat, issuer_id="DADOS_SIMULADOS_ENTIDADE")
    assert ponte["apos_ajustes"] == "220000000" and ponte["disponivel_desde"] == tarde
    sem_versao = deepcopy(nova)
    for f in sem_versao["fatos"]:
        f["versao"] = 1
    with pytest.raises(ValueError, match="versões da medida conflitantes"):
        R.construir([*partes, sem_versao], estrutura, CORTE)


def test_selecao_medida_evento_e_contexto_primario_nao_todo_item_do_emissor(primario):
    estrutura, _, bs = primario
    partes = [R.extrair(bs[d["sha256"]], d, CAPTURA, CORTE) for d in estrutura["documentos"]]
    # Outra medida do mesmo item, ano e emissor não identifica a operação catalogada.
    outra = deepcopy(
        next(
            f
            for f in partes[0]["fatos"]
            if f["item"] == "ganho_alienacao_controle" and f["valor"] is not None
        )
    )
    outra.update(documento_id="outro-documento", fato_id="outra-medida", valor="123", versao=9)
    partes[0]["fatos"].append(outra)
    cat = R.construir(partes, estrutura, CORTE)
    assert cat["eventos"][0]["medida_fato_id"] != "outra-medida"
    assert cat["eventos"][0]["contribuicao_pre_imposto"] == "30000000"


@pytest.mark.parametrize("defeito", ["valor", "base", "periodo", "moeda"])
def test_d_a_operacional_exige_bind_numerico_e_metadados_compatíveis(primario, defeito):
    _, cat, _ = primario
    p = _pac(cat)
    if defeito == "valor":
        p["t.d_a"] += 1000000
    elif defeito == "periodo":
        p["periodos_fluxos"]["d_a"] = "TTM|2025-12-31"
    elif defeito == "base":
        p["bases_fluxos"]["d_a"] = "individual"
    else:
        p["moedas_fluxos"]["d_a"] = "USD"
    q = visao(p, carregar_parametros())
    assert q["t.ebit"] == r6(220000000.0)
    assert q["t.ebitda"] is None and not q["resultado_ebitda_base"]["disponivel"]
    assert not q["visao_resultado"]["diagnostico"]["ebitda"]["compativel"]
