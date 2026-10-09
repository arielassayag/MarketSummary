"""Autoria V2: grão composto explícito; recepções/transporte DADOS SIMULADOS.

Nenhuma revisão independente nova: conserva a causal de Genese com atribuição.
Não cria início, Q, número financeiro ou contexto documental novo.
"""

from copy import deepcopy

import galicia_fixture_observada as galicia
import pytest
import supervielle_fixture_observada as supervielle

from cdp.cobertura.disponibilidade_demonstrativos import _grupos, conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.data.dimensoes_contabeis import dimensoes
from cdp.data.publico_contexto_documental import contexto_composicao, contexto_documental


@pytest.fixture(scope="module", params=[galicia, supervielle], ids=["galicia", "supervielle"])
def normal_v2(request):
    modulo = request.param
    with pytest.MonkeyPatch.context() as patch:
        frame, _ = modulo.coletor(patch)
    consumer = Demonstrativos(frame, modulo.universo().issuers.index[0])
    anual = consumer.df[consumer.df.freq.eq("A")].iloc[0]
    comp = {"item": str(anual["item"]), "freq": str(anual.freq),
            "period_end": anual.period_end.date().isoformat(), "valor": float(anual.value),
            "coeficiente": 1.0, "fonte": _prov_linha(anual),
            **dimensoes(anual), **contexto_documental(anual)}
    ag = frame[frame.freq.eq("TTM") & frame.period_end.eq(anual.period_end)].iloc[0].copy()
    ag["componentes_fluxo"] = [comp]
    for key, value in contexto_composicao([comp]).items():
        ag[key] = value
    assert conferir(modulo.pacote(ag))[0]
    return modulo, frame, anual, comp, ag


def test_periodico_A_nativo_e_contexto_composto_conferem(normal_v2):
    modulo, _, _, comp, ag = normal_v2
    before = deepcopy(comp)
    assert comp["freq"] == ag.contexto_documental["componentes"][0]["freq"] == "A"
    assert conferir(modulo.pacote(ag, fonte=_prov_linha(ag)))[0]
    assert "period_start" not in comp
    assert comp == before


def test_causal_Genese_freq_consumida_e_rotulo_TTM_ctx_A_preservado(normal_v2):
    modulo, _, anual, comp, ag = normal_v2
    alterado = deepcopy(comp)
    alterado["freq"] = "TTM"
    row_rotulo = anual.copy()
    row_rotulo["freq"] = "TTM"
    alterado["fonte"] = _prov_linha(row_rotulo)
    # Continua primário documental íntegro; o erro está no uso/grão composto.
    assert contexto_documental(alterado)
    assert alterado["fonte"]["documento"] != comp["fonte"]["documento"]
    changed = ag.copy()
    changed["componentes_fluxo"] = [alterado]
    assert changed.contexto_documental_sha256 == ag.contexto_documental_sha256
    assert changed.value == ag.value
    pack = modulo.pacote(changed, fonte=_prov_linha(changed))
    assert not conferir(pack)[0]


@pytest.mark.parametrize("campo", ["freq", "period_end"])
def test_campo_periodico_explicitamente_documentado_nao_pode_ser_omitido(normal_v2, campo):
    modulo, _, _, comp, ag = normal_v2
    alterado = deepcopy(comp)
    alterado.pop(campo)
    changed = ag.copy()
    changed["componentes_fluxo"] = [alterado]
    try:
        ok, _ = conferir(modulo.pacote(changed))
    except ValueError:
        ok = False
    assert not ok
    assert campo in ag.contexto_documental["componentes"][0]


def test_componentes_intervalares_sem_freq_preservam_ausencia(normal_v2):
    modulo, frame, _, _, _ = normal_v2
    row = modulo.row_ttm(frame)
    componentes = _grupos(row)[0][1]
    assert all("period_start" in c and "period_end" in c for c in componentes)
    assert all("freq" not in c for c in componentes)
    assert conferir(modulo.pacote(row, fonte=_prov_linha(row)))[0]
    assert all("freq" not in c for c in componentes)


@pytest.mark.parametrize("posicao", [1, 2])
def test_fim_divergente_segundo_e_ultimo_componentes_recusado(normal_v2, posicao):
    modulo, frame, _, _, _ = normal_v2
    row = modulo.row_ttm(frame).copy()
    componentes = deepcopy(_grupos(row)[0][1])
    # Usar outro fim já recebido no quadro; nenhum período financeiro inventado.
    ends = sorted({r.period_end.date().isoformat() for _, r in frame.iterrows()})
    fim_original = componentes[posicao]["period_end"]
    componentes[posicao]["period_end"] = next(e for e in ends if e != fim_original)
    row["componentes_fluxo"] = componentes
    try:
        ok, _ = conferir(modulo.pacote(row))
    except ValueError:
        ok = False
    assert not ok
