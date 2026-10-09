"""Revisão Genese: subconjunto portátil de 16 casos já cobertos pelo harness.

APIs normais e fixtures públicas recebidas; transporte/recepções DADOS SIMULADOS.
Não usa path privado, arquivo de oráculo privado nem substitui a função auditada.
A bruto/Timestamp permanece limite herdado; a mesma data ISO é explícita aqui.
"""

from copy import deepcopy

import galicia_fixture_observada as galicia
import pytest
import supervielle_fixture_observada as supervielle

from cdp.cobertura.disponibilidade_demonstrativos import _grupos, conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha, documento_proveniencia
from cdp.data.dimensoes_contabeis import dimensoes
from cdp.data.publico_contexto_documental import contexto_composicao, contexto_documental


@pytest.fixture(scope="module", params=[galicia, supervielle], ids=["galicia", "supervielle"])
def caminho_suportado_revisor(request):
    modulo = request.param
    with pytest.MonkeyPatch.context() as patch:
        frame, _ = modulo.coletor(patch)
    iid = modulo.universo().issuers.index[0]
    anual = Demonstrativos(frame, iid).df.loc[lambda df: df.freq.eq("A")].iloc[0]
    comp = {"item": str(anual["item"]), "freq": str(anual.freq),
            "period_end": anual.period_end.date().isoformat(), "valor": float(anual.value),
            "coeficiente": 1.0, "fonte": _prov_linha(anual),
            **dimensoes(anual), **contexto_documental(anual)}
    ag = frame[frame.freq.eq("TTM") & frame.period_end.eq(anual.period_end)].iloc[0].copy()
    ag["componentes_fluxo"] = [comp]
    for key, value in contexto_composicao([comp]).items():
        ag[key] = value
    assert conferir(modulo.pacote(ag, fonte=_prov_linha(ag)))[0]
    assert not {"period_start", "currency", "consolidado"} & set(comp)
    return modulo, frame, anual, comp, ag


def passa_normal(modulo, row):
    try:
        contexto_documental(row)
        return conferir(modulo.pacote(row, fonte=_prov_linha(row)))[0]
    except ValueError:
        return False


def test_revisor_intervalos_reais_sem_freq(caminho_suportado_revisor):
    modulo, frame, _, _, _ = caminho_suportado_revisor
    row = modulo.row_ttm(frame)
    before = deepcopy(_grupos(row)[0][1])
    assert all("freq" not in c for c in before)
    assert passa_normal(modulo, row)
    assert _grupos(row)[0][1] == before


@pytest.mark.parametrize("forma", ["rotulo", "filename"])
def test_revisor_freq_consumida_ctx_A_preservado(caminho_suportado_revisor, forma):
    modulo, frame, anual, comp, ag = caminho_suportado_revisor
    assert "TTM" in set(frame.freq)
    child = deepcopy(comp)
    child["freq"] = "TTM"
    if forma == "rotulo":
        row_rotulo = anual.copy()
        row_rotulo["freq"] = "TTM"
        child["fonte"]["documento"] = documento_proveniencia(row_rotulo)
    else:
        child["fonte"]["documento"] = anual.documento
    assert contexto_documental(child)
    row = ag.copy()
    row["componentes_fluxo"] = [child]
    assert row.contexto_documental_sha256 == ag.contexto_documental_sha256
    assert row.contexto_documental["componentes"][0]["freq"] == "A"
    assert row.value == ag.value
    pacote = modulo.pacote(row, fonte=_prov_linha(row))
    assert not conferir(pacote)[0]


@pytest.mark.parametrize("posicao", [0, 2])
def test_revisor_primeiro_ultimo_fim_consumido(caminho_suportado_revisor, posicao):
    modulo, frame, _, _, _ = caminho_suportado_revisor
    row = modulo.row_ttm(frame).copy()
    sha_original = row.contexto_documental_sha256
    parts = deepcopy(_grupos(row)[0][1])
    ends = sorted({r.period_end.date().isoformat() for _, r in frame.iterrows()})
    parts[posicao]["period_end"] = next(e for e in ends if e != parts[posicao]["period_end"])
    row["componentes_fluxo"] = parts
    assert row.contexto_documental_sha256 == sha_original
    assert not passa_normal(modulo, row)


def test_revisor_primaria_ISO_dois_aliases_corretos(caminho_suportado_revisor):
    modulo, _, anual, comp, _ = caminho_suportado_revisor
    row = anual.copy()
    row["period_end"] = comp["period_end"]
    row["valor"] = float(anual.value)
    assert row["value"] == row["valor"]
    assert passa_normal(modulo, row)


@pytest.mark.parametrize("alias", ["value", "valor"])
def test_revisor_primaria_ISO_segundo_alias_contraditorio(caminho_suportado_revisor, alias):
    modulo, _, anual, comp, _ = caminho_suportado_revisor
    row = anual.copy()
    row["period_end"] = comp["period_end"]
    row["valor"] = float(anual.value)
    row[alias] = float(anual.value) + 1.0
    assert not passa_normal(modulo, row)
