"""PDFs públicos completos; transporte/recepções/universo DADOS SIMULADOS.

Expected externo Decimal, nunca extrator/finanças CDP para calcular referência.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

import pandas as pd
import pytest
from supervielle_fixture_observada import (
    ANUAL,
    CORTE,
    DIA,
    JUNHO,
    ArquivoMemoria,
    coletor,
    corpos,
    documento,
    fatos,
    pacote,
    registro,
    row_ttm,
    universo,
)

from cdp.cobertura.disponibilidade_demonstrativos import conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.data import publico, publico_galicia
from cdp.data import publico_supervielle as sup
from cdp.data.publico_contexto_documental import _envelope, contexto_composicao, contexto_documental
from cdp.data.publico_fatos import selecionar_pit


def esperado():
    """Oráculo externo: lexemas recebidos no estudo, escala explícita, Decimal80."""
    with localcontext() as ctx:
        ctx.prec = 80
        values = [Decimal(x) * Decimal("1000") for x in ("-56766551", "-5371246", "29405976")]
        return values, values[1] + values[0] - values[2]


@pytest.fixture(scope="module")
def primarios():
    return fatos()


def test_nativo_three_fatos_reportados_sem_recibo_HTTP_inventado(primarios):
    values, _ = esperado()
    assert len(primarios) == 3
    for (_, row), value in zip(primarios.iterrows(), values, strict=True):
        assert Decimal(str(row.value)) == value
        assert row.politica_contabil_id == sup.POLITICA != publico_galicia.POLITICA
        assert row.poder_aquisitivo_data == "2026-06-30"
        ctx = row.contexto_documental
        assert ctx["schema"] == sup.CONTEXTO_SCHEMA != publico_galicia.CONTEXTO_SCHEMA
        assert ctx["tipo"] == "celula_primaria" and ctx["reportado_no_documento"] is True
        assert ctx["observacao_visual_fechada"] == sup.LEITURA_VISUAL
        assert (
            ctx["IFRS_integral"]
            is ctx["normalizado"]
            is ctx["perimetro_constante_certificado"]
            is False
        )
        assert ctx["publicacao_primaria"] is None and ctx["pit_certificado"] is False
        for dep in ctx["dependencias"]:
            assert "registro" in dep and "recibo_atual" not in dep
            assert not {"status", "content_type", "inicio_observado_utc"} & dep["registro"].keys()
        assert contexto_documental(row)
    assert primarios.iloc[0].demonstrativo == "BPA"
    assert primarios.iloc[0].disponivel_desde == ANUAL.isoformat()
    assert primarios.iloc[1].disponivel_desde == JUNHO.isoformat()
    bridge = primarios.iloc[0].contexto_documental["ponte_especifica"]
    assert [c["pagina_pdf"] for c in bridge["celulas_originais"]] == [6, 7, 8]
    assert {c["lexema"] for c in bridge["celulas_originais"]} == {"(48,582,394)"}
    assert bridge["regra_universal_saldo_fluxo"] is False


def test_collector_seletor_consumidor_prov_participantes_g2(monkeypatch):
    out, arq = coletor(monkeypatch)
    row = row_ttm(out)
    _, expected = esperado()
    assert Decimal(str(row.value)) == expected
    consumer = Demonstrativos(out, "AR_SUPERVIELLE")
    value, selected = consumer.valor("lucro_liquido_controladores")
    assert Decimal(str(value)) == expected
    ctx = selected.contexto_documental
    assert ctx["tipo"] == "composicao" and ctx["reportado_no_documento"] is False
    assert "celula" not in ctx and len(ctx["componentes"]) == 3
    assert {d["papel"] for d in ctx["dependencias"]} == {"junho", "anual"}
    assert pd.Timestamp(row.disponivel_desde) == pd.Timestamp(ANUAL)
    assert pd.isna(row.data_publicacao) and pd.isna(row.data_recebimento_documento)
    assert _prov_linha(selected, detalhar_fluxos=True)["contexto_documental"] == ctx
    pac = pacote(selected)
    assert conferir(pac)[0], conferir(pac)
    assert len(pac["disponibilidade_demonstrativos"][0]["componentes"]) == 3
    assert pac["disponibilidade_demonstrativos"][0]["fonte"]["contexto_documental"] == ctx
    assert any("SUPV_202512" in key for key, _, _ in arq.pedidos)
    assert set(out.item) == {"lucro_liquido_controladores"}


@pytest.mark.parametrize(
    "cut,present",
    [(JUNHO, False), (ANUAL - timedelta(microseconds=1), False), (ANUAL, True), (CORTE, True)],
)
def test_corte_seletor_e_conferencia_normal(primarios, cut, present):
    out = selecionar_pit(primarios, DIA, conhecimento_ate=cut)
    ttm = out.freq.eq("TTM") & out.period_end.eq(pd.Timestamp("2026-06-30"))
    assert bool(ttm.any()) is present
    selected = row_ttm(selecionar_pit(primarios, DIA, conhecimento_ate=CORTE))
    assert conferir(pacote(selected, cut))[0] is present


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "0" * 64),
        ("bytes", 1),
        ("url", "https://invalid.test/DADOS_SIMULADOS"),
        ("chave", "RI/demonstrativos/AR_GALICIA/OUTRO.pdf"),
        ("fonte", "SEC"),
        ("data_coleta", datetime(2026, 10, 9, 0, 11)),
        ("data_coleta", datetime.now(UTC) + timedelta(days=1)),
        ("precisao", "days"),
    ],
)
def test_registro_nativo_divergente_naive_futuro(field, value):
    data = corpos()
    with pytest.raises(ValueError):
        sup.fatos_pdf_observado(
            data["junho"],
            registro("junho"),
            data["anual"],
            replace(registro("anual"), **{field: value}),
            documento(),
        )


@pytest.mark.parametrize("role", ["junho", "anual"])
def test_bytes_alterados(role):
    data = corpos()
    data[role] += b"DADOS SIMULADOS"
    with pytest.raises(ValueError):
        sup.fatos_pdf_observado(
            data["junho"], registro("junho"), data["anual"], registro("anual"), documento()
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer_id", "AR_GALICIA"),
        ("extrator", publico_galicia.EXTRATOR_ID),
        ("sha256", "0" * 64),
        ("data_publicacao", "2026-09-01"),
        ("dependencia_anual", None),
        ("tabelas", []),
    ],
)
def test_catalogo_contexto_nao_declarado(field, value):
    doc = documento()
    doc[field] = value
    with pytest.raises(ValueError):
        sup.validar_catalogo(doc)


def test_recepcao_nova_posterior_e_precisao_seconds():
    data = corpos()
    later = (ANUAL + timedelta(seconds=17)).replace(microsecond=0)
    out = sup.fatos_pdf_observado(
        data["junho"],
        registro("junho"),
        data["anual"],
        registro("anual", later, "seconds"),
        documento(),
    )
    assert pd.Timestamp(out.iloc[0].disponivel_desde) == pd.Timestamp(later + timedelta(seconds=1))
    assert pd.Timestamp(out.iloc[1].disponivel_desde) == pd.Timestamp(JUNHO)
    for delta, present in [(-1, False), (0, True), (1, True)]:
        cutoff = later + timedelta(seconds=1, microseconds=delta)
        out2 = selecionar_pit(out, DIA, conhecimento_ate=cutoff)
        assert bool(out2.freq.eq("TTM").any()) is present


@pytest.mark.parametrize("index", [0, 1, 2])
def test_contexto_invalido_em_todos_participantes(primarios, index):
    frame = primarios.copy(deep=True)
    bad = deepcopy(frame.iloc[index].contexto_documental)
    bad["dependencias"][0]["registro"]["sha256"] = "0" * 64
    frame.at[frame.index[index], "contexto_documental"] = bad
    with pytest.raises(ValueError):
        selecionar_pit(frame, DIA, conhecimento_ate=CORTE)


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "USD"),
        ("item", "receita"),
        ("consolidado", False),
        ("period_end", pd.Timestamp("2026-03-31")),
    ],
)
def test_agregado_contradicao_grain_no_consumidor_e_G2(primarios, field, value):
    row = row_ttm(selecionar_pit(primarios, DIA, conhecimento_ate=CORTE)).copy()
    row[field] = value
    with pytest.raises(ValueError):
        _prov_linha(row, detalhar_fluxos=True)
    with pytest.raises(ValueError):
        pacote(row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("politica_contabil_id", None),
        ("poder_aquisitivo_data", None),
        ("politica_contabil_id", "OUTRA"),
        ("poder_aquisitivo_data", "2025-12-31"),
    ],
)
def test_pares_parciais_divergentes_em_fato(primarios, field, value):
    frame = primarios.copy(deep=True)
    frame.at[0, field] = value
    with pytest.raises(ValueError):
        selecionar_pit(frame, DIA, conhecimento_ate=CORTE)


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, pd.NaT])
def test_ausencia_contexto_nulo_legado(value):
    assert (
        contexto_documental({"contexto_documental": value, "contexto_documental_sha256": value})
        == {}
    )


@pytest.mark.parametrize("index", [0, 1, 2])
def test_composicao_rehash_ponte_visual_ausente_recusa(primarios, index):
    member = primarios.iloc[index].to_dict()
    ctx = deepcopy(member["contexto_documental"])
    ctx["observacao_visual_fechada"] = None
    member.update(_envelope(ctx))
    with pytest.raises(ValueError):
        contexto_composicao([member])


def test_mistura_contextos_galicia_e_super_recusada(primarios):
    member = primarios.iloc[1].to_dict()
    ctx = deepcopy(member["contexto_documental"])
    ctx["schema"] = publico_galicia.CONTEXTO_SCHEMA
    member.update(_envelope(ctx))
    with pytest.raises(ValueError):
        contexto_documental(member)


def test_default_sem_opcao_sem_nova_prioridade(monkeypatch):
    out, arq = coletor(monkeypatch, ativo=False)
    assert out.empty and not any("SUPV_2026" in key for key, _, _ in arq.pedidos)


def test_ponte_ausente_no_transporte_nao_emite_fatos(monkeypatch):
    out, arq = coletor(monkeypatch, arquivo=ArquivoMemoria(ausente="anual"))
    assert out.empty and arq.falhas


def test_arquivo_publico_real_cachecopy_hash_corte(tmp_path, monkeypatch):
    from cdp.data.publico_arquivo import Arquivo, ArquivoAdulterado

    data = corpos()
    # Setup é transporte privado DADOS SIMULADOS; registrador/cache/parser são reais.
    arq = Arquivo(tmp_path, agora=lambda: CORTE, conhecimento_ate=CORTE)
    regs = {}
    for role in ("junho", "anual"):
        pin = sup.PINS[role]
        regs[role] = arq.gravar(
            registro(role).chave,
            "RI",
            pin["url"],
            data[role],
            data_coleta=registro(role).data_coleta,
        )
    arq.offline = True
    monkeypatch.setattr(publico, "_arquivo", lambda *_: arq)

    def no_network(*_args, **_kwargs):
        raise AssertionError("Semrede DADOS SIMULADOS")

    frame = publico.demonstrativos(
        ["AR_SUPERVIELLE"],
        DIA,
        offline=True,
        universe=universo(),
        http_get=no_network,
        complementar_yahoo=False,
        selecionar_ri_observado=True,
        conhecimento_ate=CORTE,
    )
    assert Decimal(str(row_ttm(frame).value)) == esperado()[1]
    assert conferir(pacote(row_ttm(frame)))[0]
    path = arq.base / regs["anual"].caminho
    path.write_bytes(data["anual"] + b"DADOS SIMULADOS")
    with pytest.raises(ArquivoAdulterado):
        publico.demonstrativos(
            ["AR_SUPERVIELLE"],
            DIA,
            offline=True,
            universe=universo(),
            http_get=no_network,
            complementar_yahoo=False,
            selecionar_ri_observado=True,
            conhecimento_ate=CORTE,
        )


@pytest.mark.parametrize("index", [0, 1, 2])
def test_contexto_nested_mutado_com_manifesto_intacto(primarios, index):
    row = row_ttm(selecionar_pit(primarios, DIA, conhecimento_ate=CORTE))
    pac = pacote(row)
    ctx = pac["disponibilidade_demonstrativos"][0]["componentes"][index]["fonte"][
        "contexto_documental"
    ]
    ctx["dependencias"][0]["registro"]["sha256"] = "0" * 64
    assert not conferir(pac)[0]


def test_ponte_contexto_rehash_numerador_original_contraditorio(primarios):
    row = primarios.iloc[0].to_dict()
    ctx = deepcopy(row["contexto_documental"])
    ctx["ponte_especifica"]["celulas_originais"][2]["lexema"] = "48,582,394"
    row.update(_envelope(ctx))
    with pytest.raises(ValueError):
        contexto_documental(row)


def test_seconds_com_subsegundos_nao_vira_recebimento_normalizado():
    data = corpos()
    with pytest.raises(ValueError):
        sup.fatos_pdf_observado(
            data["junho"],
            registro("junho"),
            data["anual"],
            registro("anual", ANUAL, "seconds"),
            documento(),
        )


def _params_simulados(observado=True):
    from types import SimpleNamespace

    q = {
        "identidade_tolerancia": 0.01,
        "tv_aviso": 0.85,
        "upside_limites": [-0.7, 2.0],
        "defasagem_max_dias": 5,
    }
    if observado:
        q["demonstrativos_disponibilidade_metodo"] = "recepcao_observada"
    sections = {
        "qualidade": q,
        "projecao": {"resultado_corte_metodo": "base_preco_conhecimento_explicitos"},
    }
    # Opções/recipiente DADOS SIMULADOS, nenhuma alteração de parâmetro/config oficial.
    return SimpleNamespace(sec=lambda key: sections.get(key, {}))


@pytest.mark.parametrize("cut,status", [(CORTE, "ok"), (JUNHO, "bloqueio")])
def test_G2_normal_recepcao_optin_nao_certifica_publicacao(primarios, cut, status):
    from cdp.cobertura.qualidade import portoes_emissor

    row = row_ttm(selecionar_pit(primarios, DIA, conhecimento_ate=CORTE))
    pac = pacote(row, cut)
    gate = next(g for g in portoes_emissor(pac, {}, _params_simulados()) if g["codigo"] == "G2")
    assert gate["status"] == status
    assert "observada" in gate["nome"]
    legacy = next(
        g for g in portoes_emissor(pac, {}, _params_simulados(False)) if g["codigo"] == "G2"
    )
    assert legacy["status"] == "nao_aplicavel"  # Publicação ausente não recebe uma data.


def test_coletor_cobertura_existente_preserva_contexto(monkeypatch):
    from types import SimpleNamespace

    from cdp.cobertura.fontes import coletar

    arq = ArquivoMemoria()
    monkeypatch.setattr(publico, "_arquivo", lambda *_: arq)
    md = SimpleNamespace(is_synthetic=False, as_of=DIA, universe=universo())
    dados = coletar(
        md,
        DIA,
        ["AR_SUPERVIELLE"],
        [],
        [],
        offline=True,
        params=_params_simulados(),
        conhecimento_ate=CORTE,
    )
    row = row_ttm(dados.demonstrativos)
    assert Decimal(str(row.value)) == esperado()[1]
    assert contexto_documental(row)
    assert conferir(pacote(row))[0]
