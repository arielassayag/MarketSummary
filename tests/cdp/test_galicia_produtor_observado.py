"""Provas portáteis: PDFs primários literais e recibos de transporte DADOS SIMULADOS."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest
from galicia_fixture_observada import (
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
    replace,
    row_ttm,
)

from cdp.cobertura.disponibilidade_demonstrativos import conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.data.publico_fatos import selecionar_pit
from cdp.data.publico_galicia import (
    CAMPOS_CONTEXTO,
    PINS,
    ExtracaoRecusada,
    contexto_documental,
    fatos_pdf_observado,
)


@pytest.fixture(scope="module")
def primarios():
    return fatos()


def test_tres_celulas_owners_exatas_recebimentos_novos_e_origem_bpa(primarios):
    assert len(primarios) == 3
    esperado = ["229072116000", "329308168000", "437224719000"]
    for (_, row), value in zip(primarios.iterrows(), esperado, strict=True):
        assert Decimal(str(row.value)) == Decimal(value)
        assert row.received_date == JUNHO
        assert row.data_publicacao_primaria is None and row.data_recebimento_documento is None
        assert contexto_documental(row)
    annual = primarios.iloc[0]
    assert annual.demonstrativo == "BPA"
    assert annual.contexto_documental["ponte_especifica"]["regra_universal_saldo_fluxo"] is False
    assert annual.disponivel_desde == ANUAL.isoformat()
    assert primarios.iloc[1].disponivel_desde == JUNHO.isoformat()


def test_coletor_normal_consumidor_contextos_e_manifesto(monkeypatch):
    out, arq = coletor(monkeypatch)
    row = row_ttm(out)
    assert Decimal(str(row.value)) == Decimal("121155565000")
    assert row.contexto_documental["tipo"] == "composicao"
    assert row.contexto_documental["reportado_no_documento"] is False
    assert "celula" not in row.contexto_documental
    assert {d["papel"] for d in row.contexto_documental["dependencias"]} == {"junho", "anual"}
    assert pd.isna(row.data_publicacao) and pd.isna(row.data_recebimento_documento)
    assert pd.Timestamp(row.disponivel_desde) == pd.Timestamp(ANUAL)
    assert pd.Timestamp(row.received_date) == pd.Timestamp(JUNHO)
    assert set(out.item) == {"lucro_liquido_controladores"}
    assert any("GALICIA_202512" in k for k, _, _ in arq.pedidos)
    dem = Demonstrativos(out, "AR_GALICIA")
    val, selected = dem.valor("lucro_liquido_controladores")
    assert Decimal(str(val)) == Decimal("121155565000")
    assert (
        _prov_linha(selected, detalhar_fluxos=True)["contexto_documental"]
        == row.contexto_documental
    )
    pac = pacote(selected)
    assert conferir(pac)[0], conferir(pac)
    member = pac["disponibilidade_demonstrativos"][0]
    assert member["fonte"]["contexto_documental"] == row.contexto_documental
    assert len(member["componentes"]) == 3
    assert (
        member["contexto_documental_sha256"]
        == pac["manifesto_disponibilidade"]["participantes_esperados"][0][
            "contexto_documental_sha256"
        ]
    )
    assert all(
        c["fonte"]["contexto_documental_sha256"] == c["contexto_documental_sha256"]
        for c in member["componentes"]
    )


@pytest.mark.parametrize(
    "cut,entra",
    [
        (JUNHO + timedelta(seconds=30), False),
        (ANUAL - timedelta(microseconds=1), False),
        (ANUAL, True),
        (CORTE, True),
    ],
)
def test_corte_seletor_entre_recepcoes_exato_e_depois(primarios, cut, entra):
    out = selecionar_pit(primarios, DIA, conhecimento_ate=cut)
    present = out.freq.eq("TTM") & out.period_end.eq(pd.Timestamp("2026-06-30"))
    assert bool(present.any()) is entra
    if not entra:
        assert out.empty  # H1 não se converte isoladamente em trimestre/TTM.


@pytest.mark.parametrize(
    "cut,entra",
    [
        (JUNHO + timedelta(seconds=30), False),
        (ANUAL - timedelta(microseconds=1), False),
        (ANUAL, True),
        (CORTE, True),
    ],
)
def test_g2_corte_entre_recepcoes_exato_e_depois(primarios, cut, entra):
    row = row_ttm(selecionar_pit(primarios, DIA, conhecimento_ate=CORTE))
    assert conferir(pacote(row, cut))[0] is entra


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "0" * 64),
        ("bytes", 1),
        ("url", "https://example.invalid/DADOS_SIMULADOS"),
        ("chave", "RI/demonstrativos/AR_GALICIA/OUTRO.pdf"),
        ("data_coleta", datetime(2026, 10, 9, 0, 11)),
        ("data_coleta", datetime.now(UTC) + timedelta(days=1)),
        ("precisao", "days"),
    ],
)
def test_registro_anual_divergente_naive_futuro_recusado(field, value):
    data = corpos()
    with pytest.raises(ValueError):
        fatos_pdf_observado(
            data["junho"],
            registro("junho"),
            data["anual"],
            replace(registro("anual"), **{field: value}),
            documento(),
        )


@pytest.mark.parametrize("role", ["junho", "anual"])
def test_bytes_alterados_recusados(role):
    data = corpos()
    data[role] = data[role] + b" "
    with pytest.raises(ExtracaoRecusada):
        fatos_pdf_observado(
            data["junho"], registro("junho"), data["anual"], registro("anual"), documento()
        )


def test_ponte_ausente_no_catalogo_recusada():
    doc = deepcopy(documento())
    doc.pop("dependencia_anual")
    data = corpos()
    with pytest.raises(ExtracaoRecusada):
        fatos_pdf_observado(data["junho"], registro("junho"), data["anual"], registro("anual"), doc)


def test_coletor_ponte_nao_recebida_sem_fatos(monkeypatch):
    out, _ = coletor(monkeypatch, arquivo=ArquivoMemoria(ausente="anual"))
    assert out.empty
    assert any("ponte anual" in m for m in out.attrs["falhas"])


@pytest.mark.parametrize("scope", ["topo", "componente", "fonte"])
def test_mutacao_unica_dependencia_anual_recusada_sem_reassinar(primarios, scope):
    row = row_ttm(selecionar_pit(primarios, DIA, conhecimento_ate=CORTE))
    pac = pacote(row)
    original = deepcopy(pac["manifesto_disponibilidade"])
    member = pac["disponibilidade_demonstrativos"][0]
    if scope == "componente":
        target = next(
            c for c in member["componentes"] if c["contexto_documental"]["ponte_especifica"]
        )
    elif scope == "fonte":
        target = next(
            c["fonte"]
            for c in member["componentes"]
            if c["contexto_documental"]["ponte_especifica"]
        )
    else:
        target = member
    target["contexto_documental"]["dependencias"][-1]["registro"]["sha256"] = "0" * 64
    assert pac["manifesto_disponibilidade"] == original
    assert conferir(pac)[0] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("politica_contabil_id", None),
        ("politica_contabil_id", "IFRS_INTEGRAL"),
        ("poder_aquisitivo_data", "2025-12-31"),
        ("contexto_documental_sha256", None),
    ],
)
def test_par_contexto_divergente_ou_parcial_recusado(primarios, field, value):
    altered = primarios.copy(deep=True)
    altered.loc[0, field] = value
    with pytest.raises(ValueError):
        selecionar_pit(altered, DIA, conhecimento_ate=CORTE)


def test_segundos_antigos_conservam_limite_superior():
    data = corpos()
    rj = registro("junho", JUNHO.replace(microsecond=0), "seconds")
    ra = registro("anual", ANUAL.replace(microsecond=0), "seconds")
    out = fatos_pdf_observado(data["junho"], rj, data["anual"], ra, documento())
    assert out.iloc[0].disponivel_desde == (ra.data_coleta + timedelta(seconds=1)).isoformat()
    assert out.iloc[1].disponivel_desde == (rj.data_coleta + timedelta(seconds=1)).isoformat()


def test_default_nao_habilita_filing_nem_contexto(monkeypatch):
    out, arq = coletor(monkeypatch, ativo=False)
    assert out.empty and not any(
        k.startswith("RI/demonstrativos/AR_GALICIA/") for k, _, _ in arq.pedidos
    )
    assert not any(k in out for k in CAMPOS_CONTEXTO)


def test_outros_recibos_legitimos_posteriores_mesmos_bytes():
    data = corpos()
    out = fatos_pdf_observado(
        data["junho"],
        registro("junho", JUNHO + timedelta(minutes=3)),
        data["anual"],
        registro("anual", ANUAL + timedelta(minutes=3)),
        documento(),
    )
    assert out.iloc[0].disponivel_desde == (ANUAL + timedelta(minutes=3)).isoformat()
    assert out.iloc[0].sha256 == PINS["junho"]["sha256"]


def test_coletor_corte_apos_junho_antes_ponte_sem_ttm(monkeypatch):
    out, _ = coletor(monkeypatch, corte=JUNHO + timedelta(seconds=30))
    assert out.empty
