"""Controles não autores portáteis, DADOS SIMULADOS; sem modelo/seed/rede.

O parser/provider da fixture entrega somente fatos em memória. As etapas
publico.demonstrativos, selecionar_pit, derivação, consumidor, proveniência e
identidade são as funções normais. Nenhum dado documental de lucro é emitido.
"""

import hashlib
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes, _grupos, conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.cobertura.temporal import construir
from cdp.data import publico, publico_fatos

IID = "DADOS_SIMULADOS_REV"
CAMPOS = ("politica_contabil_id", "poder_aquisitivo_data")
PAR = dict(zip(CAMPOS, ("BCRA_DADOS_SIMULADOS_REV", "2026-06-30"), strict=True))
DIA = date(2026, 10, 8)
CORTE = datetime(2026, 10, 8, 22, 0, tzinfo=UTC)
RECEBIDO = datetime(2026, 10, 8, 21, 0, 0, 123456, tzinfo=UTC)
URL = "https://example.invalid/DADOS_SIMULADOS_REV"


def fato(inicio, fim, value=1.0, *, item="lucro_liquido_controladores", tipado=True):
    out = dict(entidade=f"RI:{IID}", issuer_id=IID, demonstrativo="DRE",
               period_start=inicio, period_end=fim, item=item, value=value, currency="ARS",
               consolidado=True, anual=False, received_date=RECEBIDO.isoformat(),
               version=1, fonte="RI", url=URL, documento="DADOS SIMULADOS REV",
               sha256="0" * 64, pit_estimado=False, nota="DADOS SIMULADOS REV",
               disponibilidade_tipo="recepcao_observada", disponivel_desde=RECEBIDO.isoformat(),
               data_recebimento_documento=None, data_publicacao_primaria=None)
    if tipado:
        out.update(PAR)
    return out


def semestres(*, item="lucro_liquido_controladores", value=1.0, tipado=True):
    return [fato("2025-01-01", "2025-06-30", value, item=item, tipado=tipado),
            fato("2025-01-01", "2025-12-31", value, item=item, tipado=tipado),
            fato("2026-01-01", "2026-06-30", value, item=item, tipado=tipado)]


@pytest.fixture(autouse=True)
def relogio(monkeypatch):
    monkeypatch.setattr(publico_fatos, "_agora_observado", lambda: CORTE)


def coletor(rows, monkeypatch):
    raw = b"DADOS SIMULADOS REV - parser injetado; nao e um PDF primario"
    reg = SimpleNamespace(sha256=hashlib.sha256(raw).hexdigest(),
                          data_coleta=RECEBIDO, limite_captura=RECEBIDO)
    doc = dict(documento="DADOS SIMULADOS REV", url=URL,
               disponibilidade_tipo="recepcao_observada")

    class ArquivoMemoria:
        offline = True
        conhecimento_ate = CORTE

        def __init__(self):
            self.falhas = []

        def chaves(self):
            return []

        def obter(self, chave, fonte, url, baixar, **kwargs):
            assert chave.startswith("RI/demonstrativos/") and fonte == "RI" and url == URL
            kwargs["validar"](raw)
            return reg, raw

    def parser(_raw, _doc, **_kwargs):
        return pd.DataFrame(deepcopy(rows))

    uni = SimpleNamespace(issuers=pd.DataFrame(index=[IID]))
    mestre = pd.DataFrame(index=[IID], columns=["cnpj", "cik"])
    monkeypatch.setattr(publico, "_arquivo", lambda *_args: ArquivoMemoria())
    monkeypatch.setattr(publico, "mestre_publico", lambda *_args, **_kw: mestre)
    monkeypatch.setattr(publico.ri_pdf, "documentos_ri", lambda *_args: [doc])
    monkeypatch.setattr(publico.ri_pdf, "fatos_pdf_ri", parser)

    def rede_proibida(*_args, **_kwargs):
        raise AssertionError("rede proibida; fixture DADOS SIMULADOS")

    return publico.demonstrativos([IID], DIA, offline=True, universe=uni,
                                  complementar_yahoo=False, selecionar_ri_observado=True,
                                  conhecimento_ate=CORTE, http_get=rede_proibida)


def escolher(df, item="lucro_liquido_controladores", freq="TTM", fim="2026-06-30"):
    return df[df.item.eq(item) & df.freq.eq(freq) & df.period_end.eq(pd.Timestamp(fim))]


def par(row):
    return {k: row[k] for k in CAMPOS}


def tempo(row):
    assert pd.Timestamp(row["disponivel_desde"]) == pd.Timestamp(RECEBIDO)
    assert pd.Timestamp(row["received_date"]) == pd.Timestamp(RECEBIDO)
    assert pd.isna(row["data_publicacao"])
    assert pd.isna(row["data_recebimento_documento"])


def pacote(row, destino="t.lucro_liquido_controladores"):
    pac = dict(issuer_id=IID, as_of=DIA.isoformat(), corte_temporal=construir(DIA, CORTE))
    pac[destino] = float(row.value)
    registro = RegistroParticipantes(IID)
    registro.registrar(row, destino)
    registro.finalizar(pac)
    return pac


def test_api_integral_corrige_colapso_e_preserva_temporal_proveniencia_identidade(monkeypatch):
    out = coletor(semestres(), monkeypatch)
    row = escolher(out).iloc[0]
    assert par(row) == PAR
    tempo(row)
    assert Decimal(str(row.value)) == Decimal("1")
    grupos = _grupos(row)
    assert len(grupos) == 1 and len(grupos[0][1]) == 3
    for c in grupos[0][1]:
        assert par(c) == PAR
        tempo(c["fonte"])
    prov = _prov_linha(row, detalhar_resultados=True)
    assert par(prov) == PAR
    tempo(prov)
    dem = Demonstrativos(out, IID)
    assert par(dem.valor("lucro_liquido_controladores")[1]) == PAR
    pac = pacote(row)
    assert conferir(pac)[0]
    assert par(pac["disponibilidade_demonstrativos"][0]) == PAR
    assert all(par(c) == PAR for c in pac["disponibilidade_demonstrativos"][0]["componentes"])
    assert par(pac["manifesto_disponibilidade"]["participantes_esperados"][0]) == PAR


@pytest.mark.parametrize("campo,valor", [
    ("politica_contabil_id", None), ("politica_contabil_id", " \t"),
    ("poder_aquisitivo_data", "2026-02-30"),
])
def test_coletor_recusa_parcial_blank_e_data_impossivel(monkeypatch, campo, valor):
    rows = semestres()
    rows[0][campo] = valor
    with pytest.raises(ValueError):
        coletor(rows, monkeypatch)


@pytest.mark.parametrize("campo,valor", [
    ("politica_contabil_id", "IFRS_INTEGRAL_DADOS_SIMULADOS_REV"),
    ("poder_aquisitivo_data", "2025-06-30"),
    ("par", None),
])
def test_coletor_recusa_composicao_tipada_divergente_sem_apagar_anual(monkeypatch, campo, valor):
    rows = semestres()
    if campo == "par":
        for k in CAMPOS:
            rows[0].pop(k)
    else:
        rows[0][campo] = valor
    out = coletor(rows, monkeypatch)
    assert escolher(out).empty
    annual = escolher(out, freq="A", fim="2025-12-31").iloc[0]
    assert Decimal(str(annual.value)) == Decimal("1") and par(annual) == PAR
    tempo(annual)


def fcf(monkeypatch):
    out = coletor(semestres(item="cfo", value=2.0) + semestres(item="capex"), monkeypatch)
    return out, escolher(out, item="fcf").iloc[0]


def test_fcf_multiplos_grupos_conservam_par_recebimento_e_participantes(monkeypatch):
    _, row = fcf(monkeypatch)
    assert Decimal(str(row.value)) == Decimal("1")
    grupos = _grupos(row)
    assert len(grupos) == 3
    assert [len(cs) for _, cs in grupos] == [3, 3, 2]
    for _, cs in grupos:
        for c in cs:
            assert par(c) == PAR
            tempo(c["fonte"])
    pac = pacote(row, "t.fcf")
    assert conferir(pac)[0]
    registered = pac["disponibilidade_demonstrativos"][0]
    assert len(registered["grupos_componentes"]) == 3
    assert len(registered["componentes"]) == 8
    assert all(par(c) == PAR for c in registered["componentes"])


def test_grupo_posterior_divergente_recusado_sem_reassinar_manifesto(monkeypatch):
    _, row = fcf(monkeypatch)
    pac = pacote(row, "t.fcf")
    assert conferir(pac)[0]
    grupos = pac["disponibilidade_demonstrativos"][0]["grupos_componentes"]
    later = grupos[1]["indices"][0]
    pac["disponibilidade_demonstrativos"][0]["componentes"][later]["poder_aquisitivo_data"] = "2025-06-30"
    assert not conferir(pac)[0]


def test_campo_explicito_tem_precedencia_total_sobre_nota_incompativel(monkeypatch):
    _, row = fcf(monkeypatch)
    row = row.copy()
    explicit = [deepcopy(c) for _, cs in _grupos(row) for c in cs]
    row["componentes_fluxo"] = explicit
    # Nota anterior divergente não é mesclada à declaração explícita.
    row["nota"] = str(row["nota"]).replace(PAR["politica_contabil_id"], "OUTRA_DADOS_SIMULADOS_REV")
    grupos = _grupos(row)
    assert len(grupos) == 1 and grupos[0][0] == "campo"
    assert all(par(c) == PAR for c in grupos[0][1])
    assert conferir(pacote(row, "t.fcf"))[0]


def test_consumidor_quatro_q_preserva_par_e_recusa_grupo_divergente(monkeypatch):
    rows = [fato(s, e) for s, e in [("2025-07-01", "2025-09-30"),
            ("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
            ("2026-04-01", "2026-06-30")]]
    out = coletor(rows, monkeypatch)
    q = out[out.freq.eq("Q")].copy()
    row = escolher(Demonstrativos(q, IID).df).iloc[0]
    assert par(row) == PAR and Decimal(str(row.value)) == Decimal("4")
    assert len(_grupos(row)[0][1]) == 4
    assert all(par(c) == PAR for c in _grupos(row)[0][1])
    q.loc[q.index[0], "poder_aquisitivo_data"] = "2025-09-30"
    assert escolher(Demonstrativos(q, IID).df).empty


def test_alternativa_nao_consumida_nao_bloqueia_ebitda_reportado(monkeypatch):
    rows = [fato("2025-01-01", "2025-12-31", v, item=item)
            for item, v in [("ebit", 2.0), ("d_a", 1.0),
                            ("lucro_antes_ir", 8.0), ("resultado_financeiro", 5.0)]]
    for r in rows[2:]:
        r["politica_contabil_id"] = "IFRS_NAO_USADO_DADOS_SIMULADOS_REV"
        r["poder_aquisitivo_data"] = "2025-12-31"
    out = coletor(rows, monkeypatch)
    row = escolher(out, item="ebitda", fim="2025-12-31").iloc[0]
    assert Decimal(str(row.value)) == Decimal("3") and par(row) == PAR
    assert [c["item"] for c in _grupos(row)[-1][1]] == ["ebit", "d_a"]


def test_ausencia_integral_mantem_colunas_default_sem_certificar_por_nota(monkeypatch):
    rows = semestres(tipado=False)
    for r in rows:
        r["nota"] += "; politica_contabil_id=curadoria; poder_aquisitivo_data=2026-06-30"
    out = coletor(rows, monkeypatch)
    assert not set(CAMPOS) & set(out.columns)
    row = escolher(out).iloc[0]
    assert Decimal(str(row.value)) == Decimal("1")
    tempo(row)
    assert not set(CAMPOS) & set(_prov_linha(row, detalhar_resultados=True))


def test_ausencia_integral_preserva_aceite_existente_dos_componentes_intervalares(monkeypatch):
    out = coletor(semestres(tipado=False), monkeypatch)
    row = escolher(out).iloc[0]
    assert not set(CAMPOS) & set(out.columns)
    assert all(not set(CAMPOS) & set(c) for _, cs in _grupos(row) for c in cs)
    ok, motivo = conferir(pacote(row))
    assert ok, motivo
