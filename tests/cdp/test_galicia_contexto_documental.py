"""DADOS SIMULADOS: coerência de envelopes, não autenticação/extração de PDFs.

Sem arquivo/bytes/snapshot privado. Identidades de documentos são claims de
fixtures de contrato; estes testes não provam células reais nem novo recebimento.
"""

from copy import deepcopy
from datetime import UTC, datetime

import pandas as pd
import pytest

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes, conferir
from cdp.cobertura.temporal import construir
from cdp.data.publico_fatos import selecionar_pit
from cdp.data.publico_galicia import (
    _ANCORAS,
    _CELULAS,
    CAMPOS_CONTEXTO,
    CONTEXTO_SCHEMA,
    PINS,
    PODER,
    POLITICA,
    _envelope,
    contexto_documental,
)

DIA = datetime(2026, 10, 8).date()
RECEBIDO = datetime(2026, 10, 8, 22, 0, 0, 123456, tzinfo=UTC)
CORTE = datetime(2026, 10, 8, 22, 1, tzinfo=UTC)


def claim(role):
    start, end, dem, page, col, index, rubric = _CELULAS[role]
    deps = []
    for kind in ("junho", "anual") if role == "anual2025_reexpresso" else ("junho",):
        pin = PINS[kind]
        deps.append(
            dict(
                papel=kind,
                documento=pin["documento"],
                limite_captura=RECEBIDO.isoformat(),
                registro=dict(
                    chave=f"RI/demonstrativos/AR_GALICIA/{pin['documento']}",
                    fonte="RI",
                    url=pin["url"],
                    sha256=pin["sha256"],
                    bytes=pin["bytes"],
                    caminho="DADOS_SIMULADOS",
                    precisao_temporal="microseconds",
                    data_coleta=RECEBIDO.isoformat(),
                ),
            )
        )
    bridge = None
    if role == "anual2025_reexpresso":
        bridge = dict(
            regra_universal_saldo_fluxo=False,
            sha256_original=PINS["anual"]["sha256"],
            bs_pagina_pdf=4,
            dre_pagina_pdf=5,
            bs_rubrica="Resultado del ejercicio",
            dre_rubrica="Resultado neto atribuible a los propietarios de la controladora",
            bs_lexema="1.000",
            dre_lexema="1.000",
            poder_aquisitivo_original="2025-12-31",
        )
    cell = dict(
        papel=role,
        period_start=start,
        period_end=end,
        demonstrativo=dem,
        pagina_pdf=page,
        coluna=col,
        indice_coluna_zero=index,
        rubrica=rubric,
        escala_ars="1000",
        quantum_ars="1000",
        lexema="1,000",
        valor_decimal_ars="1000000",
        sha256=PINS["junho"]["sha256"],
        owners=True,
        consolidado=True,
        currency="ARS",
        politica_contabil_id=POLITICA,
        poder_aquisitivo_data=PODER,
    )
    ctx = dict(
        schema=CONTEXTO_SCHEMA,
        tipo="celula_primaria",
        celula=cell,
        ponte_especifica=bridge,
        dependencias=deps,
        ancoras_politica_unidade=deepcopy(_ANCORAS),
        publicacao_primaria=None,
        pit_certificado=False,
        disponivel_desde=RECEBIDO.isoformat(),
    )
    return dict(
        entidade="RI:AR_GALICIA",
        issuer_id="AR_GALICIA",
        item="lucro_liquido_controladores",
        period_start=start,
        period_end=end,
        demonstrativo=dem,
        value=1000000.0,
        currency="ARS",
        anual=role == "anual2025_reexpresso",
        consolidado=True,
        version=1,
        fonte="RI",
        url=PINS["junho"]["url"],
        documento=PINS["junho"]["documento"],
        sha256=PINS["junho"]["sha256"],
        received_date=RECEBIDO.isoformat(),
        nota="DADOS SIMULADOS claims, nenhum PDF autenticado",
        disponibilidade_tipo="recepcao_observada",
        disponivel_desde=RECEBIDO.isoformat(),
        data_recebimento_documento=None,
        data_publicacao_primaria=None,
        pit_estimado=False,
        politica_contabil_id=POLITICA,
        poder_aquisitivo_data=PODER,
        **_envelope(ctx),
    )


def package():
    facts = [claim(role) for role in _CELULAS]
    out = selecionar_pit(pd.DataFrame(facts), DIA, conhecimento_ate=CORTE)
    row = out[out.freq.eq("TTM") & out.period_end.eq(pd.Timestamp("2026-06-30"))].iloc[0]
    pac = dict(
        issuer_id="AR_GALICIA",
        as_of=DIA.isoformat(),
        corte_temporal=construir(DIA, CORTE),
        **{"t.lucro_liquido_controladores": float(row.value)},
    )
    reg = RegistroParticipantes("AR_GALICIA")
    reg.registrar(row, "t.lucro_liquido_controladores")
    reg.finalizar(pac)
    return pac


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, pd.NaT])
def test_ausencia_integral_pandas_preserva_legacy(value):
    assert contexto_documental(dict(zip(CAMPOS_CONTEXTO, [value, value], strict=True))) == {}


@pytest.mark.parametrize("campo", CAMPOS_CONTEXTO)
@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, pd.NaT])
def test_parcial_pandas_recusado(campo, value):
    row = claim("H1_2026_owners")
    row[campo] = value
    with pytest.raises(ValueError):
        contexto_documental(row)


def test_serializacao_canonica_recusa_objeto_sem_ocultar_tipo():
    row = claim("H1_2026_owners")
    row["contexto_documental"]["extra"] = object()
    with pytest.raises(ValueError, match="serialização"):
        contexto_documental(row)


@pytest.mark.parametrize(
    "campo,value",
    [
        ("period_end", "2026-03-31"),
        ("value", 1),
        ("politica_contabil_id", "IFRS_INTEGRAL"),
        ("poder_aquisitivo_data", "2025-12-31"),
        ("currency", "USD"),
        ("consolidado", False),
        ("item", "caixa"),
        ("demonstrativo", "BP"),
        ("data_publicacao_primaria", "2026-07-01"),
        ("disponibilidade_tipo", "publicacao_confirmada"),
        ("disponibilidade_tipo", pd.NA),
        ("currency", pd.NA),
        ("value", pd.NA),
    ],
)
def test_claim_nativo_contraditorio_recusado(campo, value):
    row = claim("H1_2026_owners")
    row[campo] = value
    with pytest.raises(ValueError):
        contexto_documental(row)


def test_fluxo_normal_seletor_registro_conferir_coerencia_sem_autoridade_documental():
    pac = package()
    assert conferir(pac)[0]
    member = pac["disponibilidade_demonstrativos"][0]
    assert member["contexto_documental"]["tipo"] == "composicao"
    assert member["contexto_documental"]["reportado_no_documento"] is False
    assert len(member["componentes"]) == 3


@pytest.mark.parametrize("posicao", [1, 2])
@pytest.mark.parametrize("fonte", [False, True])
def test_segundo_ultimo_validado_sem_curto_circuito_com_fonte_nested(posicao, fonte):
    pac = package()
    manifesto = deepcopy(pac["manifesto_disponibilidade"])
    component = pac["disponibilidade_demonstrativos"][0]["componentes"][posicao]
    target = component["fonte"] if fonte else component
    target["contexto_documental"]["dependencias"][0]["registro"]["sha256"] = "0" * 64
    assert pac["manifesto_disponibilidade"] == manifesto
    assert conferir(pac)[0] is False


def test_hash_reassinado_nao_reassina_manifesto():
    pac = package()
    top = pac["disponibilidade_demonstrativos"][0]
    top["contexto_documental"]["observacao"] = "DADOS SIMULADOS alteração exclusiva"
    top.update(_envelope(top["contexto_documental"]))
    assert conferir(pac)[0] is False
