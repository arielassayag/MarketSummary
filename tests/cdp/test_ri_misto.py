"""DADOS SIMULADOS: focais ordinários, sem fonte real/harness histórico/ataques."""

from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta, timezone
from pathlib import Path

import pytest
from ri_fixture_portatil import BOUND, CAPTURE, fixture

from cdp.cobertura.contexto import montar_contexto
from cdp.cobertura.etf import avaliar_etfs, calcular_etfs
from cdp.cobertura.fontes import coletar, csv_canonico
from cdp.cobertura.insumos import preparar_emissor
from cdp.cobertura.modelo import Avaliador
from cdp.cobertura.motor import executar, modelo_json
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.ri_consumo import FornecedorConsumoRI, emissores_autorizados, validar_consumo
from cdp.cobertura.ri_observada import selecionar_demonstrativos
from cdp.data.ri_captura.adapter import coletar_observados
from cdp.data.ri_captura.transporte import gravar_insumos_ri, reabrir_insumos_ri

FONTE = Path(__file__).resolve().parents[2]


def params(ri=True):
    p = carregar_parametros(
        FONTE / "configs/cdp/valuation.yaml", pasta=FONTE / "configs/cdp/cobertura"
    )
    if not ri:
        return p
    v = deepcopy(p.valuation)
    v["qualidade"]["ri_disponibilidade_metodo"] = "captura_observada_identidade"
    return replace(p, valuation=v)


def base(path, cut=BOUND):
    md, context, _ = fixture(path)
    p = params()
    dados = coletar(
        md,
        md.as_of,
        list(md.universe.issuers.index),
        list(md.universe.lines.index),
        ["ILF", "EWZ", "EWW"],
        params=p,
        conhecimento_ate=cut,
        ri_contexto=context,
    )
    # Cenário ordinário de lacuna documental gerado: sem saldos primários posteriores.
    # Apenas a fixture; não muda nenhuma fonte/cifra real.
    lacuna = (dados.demonstrativos.issuer_id == "MX_AMX") & dados.demonstrativos.item.isin(
        ["patrimonio_controladores", "participacao_minoritarios", "patrimonio_liquido"]
    )
    dados = replace(dados, demonstrativos=dados.demonstrativos.loc[~lacuna].copy())
    return md, dados, p, FornecedorConsumoRI(md, dados)


@pytest.mark.parametrize("offset,count", [(-1, 0), (0, 6), (1, 6)])
def test_cortes_exatos_reextraem_seis_sem_publicacao(tmp_path, offset, count):
    md, context, _ = fixture(tmp_path)
    cut = BOUND + timedelta(microseconds=offset)
    table, evidence = coletar_observados(md, context, cut)
    assert len(table) == count
    if count:
        assert table.data_publicacao.isna().all() and table.received_date.isna().all()
        assert set(table.disponivel_desde) == {BOUND.isoformat()}
        assert set(table.data_coleta) == {CAPTURE.isoformat()}
        assert set(table.escala) == {"1"} and set(table.quantum) == {"1000"}
    assert len(evidence) == 1


def test_fuso_mesmo_instante_mesmos_bytes(tmp_path):
    md, context, _ = fixture(tmp_path)
    a, b = coletar_observados(md, context, BOUND)
    c, d = coletar_observados(md, context, BOUND.astimezone(timezone(timedelta(hours=-3))))
    assert csv_canonico(a) == csv_canonico(c) and csv_canonico(b) == csv_canonico(d)


def test_emissores_sem_vinculo_preservam_tabela_objeto_e_sem_traco(tmp_path):
    md, dados, p, provider = base(tmp_path)
    assert emissores_autorizados(provider) == frozenset({"MX_AMX"})
    for iid in set(md.universe.issuers.index) - {"MX_AMX"}:
        table, trace = selecionar_demonstrativos(md, dados, p, iid)
        assert table is dados.demonstrativos and trace is None
        mixed = preparar_emissor(md, dados, p, iid, md.as_of)
        legacy = preparar_emissor(md, dados, params(False), iid, md.as_of)
        assert mixed == legacy and "ri_observada" not in mixed


def test_ausencia_fornecedor_recusa_entrada_ordinaria(tmp_path):
    md, dados, p, _ = base(tmp_path)
    with pytest.raises(ValueError, match="fornecedor externo ausente"):
        executar(md, dados, p, md.as_of, conhecimento_ate=BOUND)


def test_sem_politica_dados_legados_e_ausencias_intactos(tmp_path):
    md, context, _ = fixture(tmp_path)
    p = params(False)
    dados = coletar(
        md,
        md.as_of,
        list(md.universe.issuers.index),
        list(md.universe.lines.index),
        ["ILF"],
        params=p,
        conhecimento_ate=BOUND,
    )
    before = csv_canonico(dados.demonstrativos)
    for iid in md.universe.issuers.index:
        table, trace = selecionar_demonstrativos(md, dados, p, iid)
        assert table is dados.demonstrativos and trace is None
    assert csv_canonico(dados.demonstrativos) == before
    assert dados.ri_observados is None and context.document.issuer_id == "MX_AMX"


@pytest.fixture(scope="module")
def cadeia(tmp_path_factory):
    md, dados, p, provider = base(tmp_path_factory.mktemp("cadeia-DADOS-SIMULADOS"))
    ex = executar(md, dados, p, md.as_of, ri_fornecedor=provider, conhecimento_ate=BOUND)
    return md, dados, p, provider, ex


def test_cadeia_mista_contexto_modelos_json_etf(cadeia):
    md, dados, p, provider, ex = cadeia
    assert len(ex.pacotes) == len(ex.modelos) == 3
    assert set(ex.contexto["ri_observada_consumo"]["tracos"]) == {"MX_AMX"}
    for iid, pac in ex.pacotes.items():
        ri = iid == "MX_AMX"
        assert ("ri_observada" in pac) is ri
        assert ("ri_observada" in ex.modelos[iid]) is ri
        export = modelo_json(ex, iid, p, ri_fornecedor=provider, conhecimento_ate=BOUND)
        assert ("ri_observada" in export["diagnosticos"]) is ri
        if ri:
            assert not pac["pit_ok"]
            selected = [
                f
                for f in pac["fontes"].values()
                if isinstance(f, dict) and f.get("fonte") == "RI_OBSERVADA"
            ]
            assert selected and all(
                f["data_publicacao"] is None and f["received_date"] is None for f in selected
            )
    etfs, inputs = avaliar_etfs(
        md,
        dados,
        p,
        ex.pacotes,
        ex.modelos,
        ex.rf["valor"],
        ex.as_of,
        ri_fornecedor=provider,
        conhecimento_ate=BOUND,
    )
    assert etfs == ex.etfs and inputs == ex.insumos_etf
    assert (
        calcular_etfs(
            inputs,
            p,
            ex.pacotes,
            ex.modelos,
            ex.rf["valor"],
            ri_fornecedor=provider,
            conhecimento_ate=BOUND,
        )
        == ex.etfs
    )


def test_entradas_publicas_exigem_autoridade_de_novo(cadeia):
    _, _, p, _, ex = cadeia
    with pytest.raises(ValueError, match="fornecedor externo ausente"):
        montar_contexto(ex.pacotes, p, ex.rf["valor"], ex.rf["fonte"], conhecimento_ate=BOUND)
    with pytest.raises(ValueError, match="fornecedor externo ausente"):
        Avaliador(
            ex.pacotes["MX_AMX"],
            ex.contexto,
            p,
            ex.rf["valor"],
            ex.rf["fonte"],
            conhecimento_ate=BOUND,
        )
    with pytest.raises(ValueError, match="fornecedor externo ausente"):
        modelo_json(ex, "MX_AMX", p, conhecimento_ate=BOUND)
    with pytest.raises(ValueError, match="fornecedor externo ausente"):
        calcular_etfs(
            ex.insumos_etf, p, ex.pacotes, ex.modelos, ex.rf["valor"], conhecimento_ate=BOUND
        )


def test_transporte_tipos_etfs_reabertura_com_autoridades(cadeia, tmp_path):
    md, dados, p, provider, ex = cadeia
    # Composição ausente permanece None; mapa não é inferido do slug.
    dados = replace(dados, etfs={**dados.etfs, "SEM.DADO": None})
    provider = FornecedorConsumoRI(md, dados)
    path = tmp_path / "transportado"
    digest = gravar_insumos_ri(
        path, raiz_saida=tmp_path, fornecedor=provider, params=p, conhecimento_ate=BOUND
    )
    novo = reabrir_insumos_ri(
        path,
        sha256_esperado=digest,
        md=md,
        contexto=dados.ri_contexto,
        params=p,
        conhecimento_ate=BOUND,
    )
    assert novo.dados.etfs["SEM.DADO"] is None
    assert set(novo.dados.etfs) == set(dados.etfs)
    for name, frame in dados.tabelas().items():
        assert csv_canonico(frame) == csv_canonico(novo.dados.tabelas()[name])
    for _iid, pac in ex.pacotes.items():
        assert validar_consumo(pac, p, fornecedor=novo, conhecimento_ate=BOUND) == pac


@pytest.mark.parametrize("conhecimento", [None])
def test_corte_explicitamente_ausente_nao_certifica(cadeia, conhecimento):
    _, _, p, provider, ex = cadeia
    with pytest.raises(ValueError, match="datetime de conhecimento explícito"):
        modelo_json(ex, "MX_AMX", p, ri_fornecedor=provider, conhecimento_ate=conhecimento)


def test_valores_documentais_e_identidades_sem_dupla_contagem(cadeia):
    _, dados, _, _, _ = cadeia
    from decimal import Decimal

    for _, group in dados.ri_observados.groupby("period_end"):
        amounts = {
            row["item"]: Decimal(row["value"]) * Decimal(row["escala"])
            for _, row in group.iterrows()
        }
        assert (
            amounts["patrimonio_liquido"]
            == amounts["patrimonio_controladores"] + amounts["participacao_minoritarios"]
        )
        assert amounts["patrimonio_liquido"] != amounts["patrimonio_controladores"]
    assert dados.ri_observados.value.notna().all()


def test_subset_legado_nao_recebe_traco_rI(cadeia):
    md, dados, p, provider, _ = cadeia
    ids = sorted(set(md.universe.issuers.index) - {"MX_AMX"})
    ex = executar(
        md, dados, p, md.as_of, emissores=ids, ri_fornecedor=provider, conhecimento_ate=BOUND
    )
    assert ex.emissores == ids
    assert all(
        "ri_observada" not in ex.pacotes[iid] and "ri_observada" not in ex.modelos[iid]
        for iid in ids
    )
    assert "ri_observada" in ex.pacotes["MX_AMX"]


def test_insumos_etf_entrada_direta_exige_fornecedor(cadeia):
    from cdp.cobertura.etf import insumos_etf

    md, dados, p, provider, ex = cadeia
    cfg = next(c for c in p.etfs["etfs"] if c["ticker"] in md.benchmarks.columns)
    with pytest.raises(ValueError, match="fornecedor externo ausente"):
        insumos_etf(cfg, md, dados, p, ex.pacotes, ex.as_of, conhecimento_ate=BOUND)
    ins = insumos_etf(
        cfg, md, dados, p, ex.pacotes, ex.as_of, ri_fornecedor=provider, conhecimento_ate=BOUND
    )
    assert ins == ex.insumos_etf[ins["iid"]]


def test_anterior_referencia_amx_respeita_base_sem_truncar_legados(tmp_path):
    from cdp.cobertura.motor import Anterior, referencias_preco
    from cdp.cobertura.temporal import construir

    md, dados, p, _ = base(tmp_path)
    # DADOS SIMULADOS: barra posterior apenas para separar os dois relógios no teste.
    adjusted = md.adj_close.copy()
    adjusted.loc["2026-10-07", "AMX"] = adjusted.loc["2026-10-06", "AMX"] * 2
    md = replace(md, adj_close=adjusted)
    dados = replace(dados, corte_temporal=construir(date(2026, 10, 6), BOUND))
    provider = FornecedorConsumoRI(md, dados)
    lines = {iid: md.universe.primary_ticker(iid) for iid in md.universe.issuers.index}
    previous = Anterior(data_completa=date(2026, 10, 5), linhas_completa=lines)
    ex = executar(
        md, dados, p, md.as_of, anterior=previous, ri_fornecedor=provider, conhecimento_ate=BOUND
    )
    legacy = referencias_preco(md, ex.pacotes, previous, ex.as_of)
    bound = referencias_preco(
        md.truncate(date(2026, 10, 6)), {"MX_AMX": ex.pacotes["MX_AMX"]}, previous, ex.as_of
    )
    assert ex.referencias["MX_AMX"] == bound["MX_AMX"]
    assert ex.referencias["MX_AMX"] != legacy["MX_AMX"]
    assert all(ex.referencias[iid] == legacy[iid] for iid in ex.pacotes if iid != "MX_AMX")
