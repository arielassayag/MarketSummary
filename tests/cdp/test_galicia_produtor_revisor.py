"""Revisão não autora: PDFs reais, transporte/recibos DADOS SIMULADOS.

Fixture de fronteira do autor será portada literalmente com atribuição após freeze.
Alvos coletor/parser/seletor/TTM/Registro/conferir são implementações normais.
"""

import hashlib
import json
from copy import deepcopy
from datetime import timedelta
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
    row_ttm,
)

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes, conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.cobertura.temporal import construir
from cdp.data.publico_fatos import selecionar_pit
from cdp.data.publico_galicia import contexto_documental, fatos_pdf_observado


def canonico(contexto):
    return hashlib.sha256(json.dumps(contexto, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def test_oraculo_decimal_fluxo_normal_sem_hifen_de_autoridade(monkeypatch):
    out, _ = coletor(monkeypatch)
    row = row_ttm(out)
    esperado = Decimal("229072116000") + Decimal("329308168000") - Decimal("437224719000")
    assert Decimal(str(row.value)) == esperado
    assert row.currency == "ARS"
    dem = Demonstrativos(out, "AR_GALICIA")
    value, selected = dem.valor("lucro_liquido_controladores")
    assert Decimal(str(value)) == esperado
    assert _prov_linha(selected, detalhar_fluxos=True)["contexto_documental"]["tipo"] == "composicao"
    pac = pacote(selected)
    assert conferir(pac)[0], conferir(pac)
    assert all(c["contexto_documental_sha256"] == canonico(c["contexto_documental"])
               for c in pac["disponibilidade_demonstrativos"][0]["componentes"])


def test_recebimentos_invertidos_maximo_de_dependencias(monkeypatch):
    novos = {"junho": registro("junho", ANUAL + timedelta(minutes=1)),
             "anual": registro("anual", JUNHO - timedelta(minutes=1))}
    out, _ = coletor(monkeypatch, corte=CORTE + timedelta(minutes=2),
                     arquivo=ArquivoMemoria(registros=novos, corte=CORTE + timedelta(minutes=2)))
    row = row_ttm(out)
    assert pd.Timestamp(row.disponivel_desde) == pd.Timestamp(novos["junho"].data_coleta)
    assert conferir(pacote(row, corte=novos["junho"].data_coleta))[0]
    assert conferir(pacote(row, corte=novos["junho"].data_coleta - timedelta(microseconds=1)))[0] is False
    assert pd.isna(row.data_publicacao) and pd.isna(row.data_recebimento_documento)


@pytest.mark.parametrize("field,value", [("currency", "USD"), ("consolidado", False),
                                         ("item", "receita"), ("demonstrativo", "DFC")])
def test_contexto_primario_recusa_semantica_nativa_contraditoria(field, value):
    primary = fatos().iloc[1].to_dict()
    primary[field] = value  # DADOS SIMULADOS: alteração exclusiva, envelope/hash literal.
    with pytest.raises(ValueError):
        contexto_documental(primary)


def test_moeda_nativa_divergente_nao_pode_gerar_ttm_usd():
    primary = fatos()
    altered = primary.copy(deep=True)
    altered["currency"] = "USD"  # DADOS SIMULADOS; contexto primário diz ARS.
    with pytest.raises(ValueError):
        selecionar_pit(altered, DIA, conhecimento_ate=CORTE)


@pytest.mark.parametrize("posicao", [1, 2])
def test_segundo_ultimo_contexto_hash_fonte_recusado(posicao):
    out = selecionar_pit(fatos(), DIA, conhecimento_ate=CORTE)
    pac = pacote(row_ttm(out))
    member = pac["disponibilidade_demonstrativos"][0]["componentes"][posicao]
    original = deepcopy(pac["manifesto_disponibilidade"])
    member["fonte"]["contexto_documental_sha256"] = "0" * 64
    assert pac["manifesto_disponibilidade"] == original
    assert conferir(pac)[0] is False


def test_anual_bpa_preservado_e_composicao_nao_reportada(monkeypatch):
    out, _ = coletor(monkeypatch)
    ctx = row_ttm(out).contexto_documental
    assert ctx["tipo"] == "composicao" and ctx["reportado_no_documento"] is False
    annual = next(c["contexto_documental"] for c in ctx["componentes"]
                  if c["contexto_documental"].get("ponte_especifica"))
    assert annual["celula"]["demonstrativo"] == "BPA"
    assert annual["celula"]["rubrica"] == "Income from the Period/Fiscal Year"
    assert annual["ponte_especifica"]["regra_universal_saldo_fluxo"] is False
    assert annual["ponte_especifica"]["bs_lexema"] == annual["ponte_especifica"]["dre_lexema"]
    assert len(annual["dependencias"]) == 2
    assert canonico(ctx) == row_ttm(out).contexto_documental_sha256


def test_mesmos_bytes_novos_recibos_sem_publicacao_ou_retrodata():
    data = corpos()
    rj = registro("junho", JUNHO + timedelta(minutes=4))
    ra = registro("anual", ANUAL + timedelta(minutes=4))
    primary = fatos_pdf_observado(data["junho"], rj, data["anual"], ra, documento())
    assert all(primary.received_date.eq(rj.data_coleta))
    assert all(primary.data_recebimento_documento.isna())
    assert all(primary.data_publicacao_primaria.isna())
    assert primary.iloc[0].disponivel_desde == ra.data_coleta.isoformat()
    assert primary.iloc[1].disponivel_desde == rj.data_coleta.isoformat()


@pytest.mark.parametrize("posicao", [4, 5])
def test_todos_grupos_nota_segundo_ultimo_contexto_na_fonte(posicao):
    """DADOS SIMULADOS: nota ganha grupo adicional; alvos não substituídos."""
    row = row_ttm(selecionar_pit(fatos(), DIA, conhecimento_ate=CORTE)).copy()
    text = row.nota.split("componentes_fluxo=", 1)[1]
    group, _ = json.JSONDecoder().raw_decode(text)
    assert len(group) == 3
    row["nota"] += "; componentes_fluxo=" + json.dumps(group, ensure_ascii=False)
    pac = pacote(row)
    assert conferir(pac)[0], conferir(pac)
    member = pac["disponibilidade_demonstrativos"][0]
    assert len(member["grupos_componentes"]) == 2
    assert len(member["componentes"]) == 6
    manifesto = deepcopy(pac["manifesto_disponibilidade"])
    member["componentes"][posicao]["fonte"]["contexto_documental_sha256"] = "0" * 64
    assert pac["manifesto_disponibilidade"] == manifesto
    assert conferir(pac)[0] is False


def test_campo_explicito_prevalece_totalmente_sobre_nota_simulada():
    row = row_ttm(selecionar_pit(fatos(), DIA, conhecimento_ate=CORTE)).copy()
    group, _ = json.JSONDecoder().raw_decode(row.nota.split("componentes_fluxo=", 1)[1])
    row["componentes_fluxo"] = group
    row["nota"] += "; componentes_fluxo=INVALIDO_DADOS_SIMULADOS"
    pac = pacote(row)
    assert conferir(pac)[0], conferir(pac)
    member = pac["disponibilidade_demonstrativos"][0]
    assert len(member["componentes"]) == 3
    assert [g["origem"] for g in member["grupos_componentes"]] == ["campo"]


@pytest.mark.parametrize("field,value", [("currency", "USD"), ("item", "receita"),
                                         ("consolidado", False)])
def test_ttm_nativo_contraditorio_nao_pode_preservar_conferencia(monkeypatch, field, value):
    """DADOS SIMULADOS: altera exclusivamente o agregado após coletor normal."""
    out, _ = coletor(monkeypatch)
    selected = row_ttm(out)
    original = pacote(selected)
    assert conferir(original)[0]
    changed = out.copy(deep=True)
    mask = changed.freq.eq("TTM") & changed.period_end.eq(pd.Timestamp("2026-06-30"))
    changed.loc[mask, field] = value
    try:
        dem = Demonstrativos(changed, "AR_GALICIA")
        _, consumed = dem.valor("receita" if field == "item" else "lucro_liquido_controladores")
        assert consumed is not None
        _prov_linha(consumed, detalhar_fluxos=True)
        # Destino financeiro efetivo acompanha o item escolhido pelo consumidor.
        destino = "t." + str(consumed.item)
        pac = {"issuer_id": "AR_GALICIA", "as_of": DIA.isoformat(),
               "corte_temporal": construir(DIA, CORTE), destino: float(consumed.value)}
        reg = RegistroParticipantes("AR_GALICIA")
        reg.registrar(consumed, destino)
        reg.finalizar(pac)
        ok, _ = conferir(pac)
    except ValueError:
        return  # Recusa na fronteira normal também atende o contrato.
    assert ok is False, f"TTM {field}={value!r} aceito com contexto primário ARS/NI/consolidado literal"
