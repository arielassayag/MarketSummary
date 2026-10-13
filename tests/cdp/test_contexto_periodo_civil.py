"""DADOS SIMULADOS: datas civis e envelopes, sem PDF/coletor/modelo financeiro.

Claims de contrato não autenticam células reais, recepção ou disponibilidade
do ensaio privado. O fluxo de registro conserva a representação/hash recebido.
"""

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from test_galicia_contexto_documental import CORTE, DIA, claim, package

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes, conferir
from cdp.cobertura.temporal import construir
from cdp.data import publico_galicia as gal
from cdp.data import publico_supervielle as sup
from cdp.data.publico_contexto_documental import (
    ExtracaoRecusada,
    _envelope,
    contexto_documental,
    periodo_civil_nativo,
)


def claim_bancario(perfil):
    row = claim("anual2025_reexpresso")
    if perfil is gal:
        return row
    ctx = row["contexto_documental"]
    ctx.update(
        schema=perfil.CONTEXTO_SCHEMA,
        ancoras_politica_unidade=deepcopy(perfil._ANCORAS),
        observacao_visual_fechada=deepcopy(perfil.LEITURA_VISUAL),
        reportado_no_documento=True,
        normalizado=False,
        IFRS_integral=False,
        perimetro_constante_certificado=False,
        reclassificacoes_declaradas=True,
        ponte_especifica=perfil._ponte(
            {"bs": ["1,000"], "dre_owners": ["1,000"], "numerador_monetario": ["1,000"]}
        ),
    )
    keys = (
        "period_start", "period_end", "demonstrativo", "pagina_pdf", "coluna",
        "indice_coluna_zero", "rubrica",
    )
    ctx["celula"].update(zip(keys, perfil._CELULAS["anual2025_reexpresso"], strict=True))
    ctx["celula"].update(sha256=perfil.PINS["junho"]["sha256"], politica_contabil_id=perfil.POLITICA)
    for dep in ctx["dependencias"]:
        pin = perfil.PINS[dep["papel"]]
        dep["documento"] = pin["documento"]
        dep["registro"].update(
            chave=f"RI/demonstrativos/{perfil.ISSUER_ID}/{pin['documento']}",
            url=pin["url"], sha256=pin["sha256"], bytes=pin["bytes"],
        )
    row.update(
        entidade=f"RI:{perfil.ISSUER_ID}", issuer_id=perfil.ISSUER_ID,
        demonstrativo=ctx["celula"]["demonstrativo"],
        documento=perfil.PINS["junho"]["documento"],
        url=perfil.PINS["junho"]["url"], sha256=perfil.PINS["junho"]["sha256"],
        politica_contabil_id=perfil.POLITICA, **_envelope(ctx),
    )
    return row


def pacote_anual(row):
    pac = dict(
        issuer_id=row["issuer_id"], as_of=DIA.isoformat(),
        corte_temporal=construir(DIA, CORTE),
        historico={"lucro_liquido_controladores": {"2025": row["value"]}},
    )
    row["freq"] = "A"
    reg = RegistroParticipantes(row["issuer_id"])
    reg.registrar(row, "historico.lucro_liquido_controladores.2025")
    reg.finalizar(pac)
    return pac


@pytest.mark.parametrize(
    "valor",
    [
        "2025-12-31", "2025-12-31T00:00:00", "2025-12-31T00:00:00.000000000",
        date(2025, 12, 31), datetime(2025, 12, 31), pd.Timestamp("2025-12-31"),
    ],
)
def test_data_civil_aceita_representacoes_nativas_sem_alterar_valor(valor):
    original = deepcopy(valor)
    assert periodo_civil_nativo(valor) == "2025-12-31"
    assert valor == original
    assert type(valor) is type(original)


@pytest.mark.parametrize(
    "valor",
    [
        None, float("nan"), pd.NA, pd.NaT, 20251231,
        "2025-02-30", "20251231", "31/12/2025", "2025-12-31 ",
        "2025-12-31T00:00", "2025-12-31T00:00:00.0000000000",
        "2025-12-31T00:00:00Z", "2025-12-31T00:00:00+00:00",
        "2025-12-31T01:00:00", "2025-12-31T00:00:00.000000001",
        datetime(2025, 12, 31, tzinfo=UTC), datetime(2025, 12, 31, microsecond=1),
        pd.Timestamp("2025-12-31", tz="America/Argentina/Buenos_Aires"),
        pd.Timestamp("2025-12-31T00:00:00.000000001"),
    ],
)
def test_data_civil_recusa_ausencia_parser_livre_hora_e_fuso(valor):
    with pytest.raises(ExtracaoRecusada, match="Período nativo"):
        periodo_civil_nativo(valor)


@pytest.mark.parametrize("perfil", [gal, sup], ids=["galicia", "supervielle"])
@pytest.mark.parametrize("campo", ["period_start", "period_end"])
@pytest.mark.parametrize(
    "representar",
    [str, pd.Timestamp, date.fromisoformat, lambda s: f"{s}T00:00:00"],
    ids=["iso-civil", "timestamp", "date", "timestamp-serializado"],
)
def test_contexto_compara_periodo_civil_preservando_celula_hash_e_grain(perfil, campo, representar):
    row = claim_bancario(perfil)
    row[campo] = representar(row[campo])
    original = deepcopy(row)
    assert contexto_documental(row) == _envelope(original["contexto_documental"])
    assert row == original
    assert type(row[campo]) is type(original[campo])


@pytest.mark.parametrize("perfil", [gal, sup], ids=["galicia", "supervielle"])
@pytest.mark.parametrize("campo", ["period_start", "period_end"])
@pytest.mark.parametrize(
    "alterar",
    [
        lambda s: (date.fromisoformat(s) + timedelta(days=1)).isoformat(),
        lambda s: f"{s}T01:00:00", lambda s: f"{s}T00:00:00.000000001",
        lambda s: f"{s}T00:00:00Z", lambda s: pd.Timestamp(s, tz="UTC"),
        lambda s: pd.Timestamp(f"{s}T00:00:00.000000001"), lambda s: f"{s}/inválida",
    ],
    ids=["outra-data", "hora", "fracao", "fuso-string", "fuso-timestamp", "nanosegundo", "malformada"],
)
def test_contexto_recusa_periodo_divergente_sem_truncar(perfil, campo, alterar):
    row = claim_bancario(perfil)
    row[campo] = alterar(row[campo])
    original = deepcopy(row)
    with pytest.raises(ExtracaoRecusada, match="Período nativo"):
        contexto_documental(row)
    assert row == original


@pytest.mark.parametrize("perfil", [gal, sup], ids=["galicia", "supervielle"])
def test_registro_anual_native_isoformat_confere_sem_reassinar_contexto(perfil):
    row = claim_bancario(perfil)
    row.update(period_start=pd.Timestamp(row["period_start"]), period_end=pd.Timestamp(row["period_end"]))
    envelope = _envelope(row["contexto_documental"])
    pac = pacote_anual(row)
    original = deepcopy(pac)
    member = pac["disponibilidade_demonstrativos"][0]
    assert member["period_end"] == "2025-12-31T00:00:00"
    assert member["contexto_documental"]["celula"]["period_end"] == "2025-12-31"
    assert all(member[k] == v for k, v in envelope.items())
    assert conferir(pac)[0] is True
    assert pac == original


@pytest.mark.parametrize(
    "periodo",
    ["2026-07-01", "2026-06-30T01:00:00", "2026-06-30T00:00:00Z", "2026-06-30/inválida"],
)
def test_fim_agregado_nao_descarta_divergencia_hora_fuso_ou_erro(periodo):
    pac = package()
    row = pac["disponibilidade_demonstrativos"][0]
    row["period_end"] = periodo
    with pytest.raises(ExtracaoRecusada, match="Período nativo contradiz composição"):
        contexto_documental(row)


def test_periodo_valido_nao_torna_disponibilidade_nula_comprovada():
    row = claim_bancario(gal)
    row["period_end"] = pd.Timestamp(row["period_end"])
    row["disponivel_desde"] = None
    pac = pacote_anual(row)
    original = deepcopy(pac)
    ok, motivo = conferir(pac)
    assert ok is False
    assert "disponibilidade ausente" in motivo
    assert pac == original
    assert pac["disponibilidade_demonstrativos"][0]["disponivel_desde"] is None
