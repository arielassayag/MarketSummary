"""Controles próprios V2; original e rodada 100P/2F preservados separadamente.

Bytes primários herdados, transporte/recepções/causais DADOS SIMULADOS.
Fixture P0 e seus17 testes são herdados literalmente, com atribuição separada.
Nenhuma função matemática/documental/financeira alvo é substituída.
"""

import hashlib
import json
from copy import deepcopy

import pandas as pd
import pytest
from galicia_fixture_observada import CORTE, DIA, coletor, pacote, row_ttm

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes, conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.cobertura.temporal import construir
from cdp.data.dimensoes_contabeis import dimensoes
from cdp.data.publico_galicia import contexto_documental


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def observado(monkeypatch):
    out, _ = coletor(monkeypatch)
    selected = deepcopy(row_ttm(out).to_dict())
    assert contexto_documental(selected)
    assert conferir(pacote(pd.Series(selected)))[0]
    return out, selected


@pytest.mark.parametrize("end", ["2026-03-31", "2026-09-30", None, pd.NaT])
def test_fim_agregado_recusa_api_consumidor_registro_conferir(monkeypatch, end):
    out, row = observado(monkeypatch)
    before = deepcopy(row["contexto_documental"])
    row["period_end"] = end
    assert row["contexto_documental"] == before
    with pytest.raises(ValueError):
        contexto_documental(row)
    # A linha alterada deve ser recusada; outra linha só vale com origem íntegra comprovada.
    changed = out.copy(deep=True)
    mask = changed.freq.eq("TTM") & changed.period_end.eq(pd.Timestamp("2026-06-30"))
    changed.loc[mask, "period_end"] = end
    try:
        _, consumed = Demonstrativos(changed, "AR_GALICIA").valor("lucro_liquido_controladores")
        if consumed is None:
            return
        _prov_linha(consumed, detalhar_fluxos=True)
        target = "t.lucro_liquido_controladores"
        pack = {"issuer_id": "AR_GALICIA", "as_of": DIA.isoformat(),
                "corte_temporal": construir(DIA, CORTE), target: float(consumed.value)}
        registry = RegistroParticipantes("AR_GALICIA")
        registry.registrar(consumed, target)
        registry.finalizar(pack)
        ok, _ = conferir(pack)
    except ValueError:
        return
    if not ok:
        return
    # Conferir True exige identidade do fallback literal; nunca autoriza o TTM mutado.
    assert consumed.period_end == pd.Timestamp("2025-12-31")
    assert consumed.freq == "TTM"
    ctx = consumed.contexto_documental
    assert ctx != before and ctx["tipo"] == "composicao"
    assert len(ctx["componentes"]) == 1
    assert ctx["componentes"][0]["contexto_documental"]["celula"]["papel"] == "anual2025_reexpresso"
    untouched = out[(out["item"] == consumed["item"]) & (out.freq == consumed.freq)
                    & (out.period_end == consumed.period_end)]
    assert len(untouched) == 1
    counterpart = untouched.iloc[0]
    # A API TTM pode omitir start integralmente; preservar a mesma ausência, sem fabricá-lo.
    assert ("period_start" in consumed.index) == ("period_start" in counterpart.index)
    keys = ["item", "freq", "period_start", "period_end", "value", "currency", "consolidado",
            "contexto_documental_sha256", "fonte", "sha256", "received_date", "disponivel_desde"]
    def serialize(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)

    for key in [*keys, "componentes_fluxo", "nota", "contexto_documental"]:
        assert serialize(consumed.get(key)) == serialize(counterpart.get(key))


@pytest.mark.parametrize("key,value", [("currency", "USD"), ("item", "receita"),
                                        ("consolidado", False), ("period_end", "2026-09-30")])
def test_fonte_opcional_explicita_divergente_recusa_sem_inferir_topo(monkeypatch, key, value):
    _, row = observado(monkeypatch)
    source = _prov_linha(pd.Series(row), detalhar_fluxos=True)
    row["fonte"] = deepcopy(source)
    assert contexto_documental(row)
    original_top = {k: deepcopy(row.get(k)) for k in ("currency", "item", "consolidado", "period_end")}
    row["fonte"][key] = value
    with pytest.raises(ValueError):
        contexto_documental(row)
    assert original_top == {k: row.get(k) for k in original_top}


@pytest.mark.parametrize("position", [1, 2])
@pytest.mark.parametrize("key,value", [("currency", "USD"), ("item", "receita"), ("consolidado", False)])
def test_segundo_ultimo_primario_recusa_sem_depender_de_hash_desatualizado(monkeypatch, position, key, value):
    _, row = observado(monkeypatch)
    primary_contexts = [deepcopy(x["contexto_documental"]) for x in row["contexto_documental"]["componentes"]]
    row["contexto_documental"]["componentes"][position][key] = value
    # Reassinar só envelope externo expõe a semântica; células/hashes/dependências seguem literais.
    row["contexto_documental_sha256"] = digest(row["contexto_documental"])
    assert primary_contexts == [x["contexto_documental"] for x in row["contexto_documental"]["componentes"]]
    with pytest.raises(ValueError):
        contexto_documental(row)


def test_ausencia_integral_fonte_dimensoes_sem_inferencia_e_parcial_recusada(monkeypatch):
    _, row = observado(monkeypatch)
    native = dimensoes(row)
    source = _prov_linha(pd.Series(row), detalhar_fluxos=True)
    # Par contábil ausente da fonte é permitido, nunca fabricado de nota/contexto.
    for key in ("politica_contabil_id", "poder_aquisitivo_data"):
        source.pop(key, None)
    row["fonte"] = deepcopy(source)
    assert dimensoes(row) == native
    assert contexto_documental(row)
    partial = deepcopy(row)
    partial["fonte"]["politica_contabil_id"] = native["politica_contabil_id"]
    with pytest.raises(ValueError):
        dimensoes(partial)
    only_source = deepcopy(row)
    only_source["fonte"].update(native)
    only_source.pop("politica_contabil_id")
    only_source.pop("poder_aquisitivo_data")
    with pytest.raises(ValueError):
        dimensoes(only_source)


def test_ausencia_integral_contexto_preserva_legacy_sem_injetar_fatos():
    source = {"nota": "DADOS SIMULADOS ausência legítima"}
    assert contexto_documental(source) == {}
    assert source == {"nota": "DADOS SIMULADOS ausência legítima"}
