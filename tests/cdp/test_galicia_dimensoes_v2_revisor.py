"""DADOS SIMULADOS: contexto tipado e redundância explícita de fonte efetiva."""

from copy import deepcopy

import pytest
from test_galicia_dimensoes_revisor import (
    CAMPOS,
    CORTE,
    IID,
    PAR,
    coletor,
    conferir,
    escolher,
    fato,
    pacote,
    semestres,
)

from cdp.cobertura.disponibilidade_demonstrativos import _grupos
from cdp.cobertura.insumos import Demonstrativos
from cdp.data import publico_fatos


@pytest.fixture(autouse=True)
def relogio_v2(monkeypatch):
    monkeypatch.setattr(publico_fatos, "_agora_observado", lambda: CORTE)


def quatro_q_consumidor(monkeypatch):
    rows = [fato(s, e) for s, e in [("2025-07-01", "2025-09-30"),
            ("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
            ("2026-04-01", "2026-06-30")]]
    selected = coletor(rows, monkeypatch)
    qs = selected[selected.freq.eq("Q")].copy()
    ttm = escolher(Demonstrativos(qs, IID).df).iloc[0]
    components = _grupos(ttm)[0][1]
    assert len(components) == 4
    assert all({k: c[k] for k in CAMPOS} == PAR for c in components)
    # Fonte foi produzida por _prov_linha no próprio consumidor; não é declaração externa inventada.
    assert all({k: c["fonte"][k] for k in CAMPOS} == PAR for c in components)
    return ttm


@pytest.mark.parametrize("campo,outro", [
    ("politica_contabil_id", "IFRS_DADOS_SIMULADOS_REV"),
    ("poder_aquisitivo_data", "2025-09-30"),
])
def test_par_presente_na_fonte_efetiva_nao_pode_contradizer_topo(monkeypatch, campo, outro):
    row = quatro_q_consumidor(monkeypatch)
    pac = pacote(row)
    assert conferir(pac)[0]
    original = deepcopy(pac)
    c = pac["disponibilidade_demonstrativos"][0]["componentes"][0]
    assert c[campo] != outro and c["fonte"][campo] == c[campo]
    c["fonte"][campo] = outro
    assert c[campo] == original["disponibilidade_demonstrativos"][0]["componentes"][0][campo]
    assert pac["manifesto_disponibilidade"] == original["manifesto_disponibilidade"]
    # Contradição localizada em dimensão declarada na fonte, sem autoridade universal ou novo requisito.
    ok, motivo = conferir(pac)
    assert not ok, motivo


def test_fonte_sem_par_completo_preserva_formato_legado_sem_inferir(monkeypatch):
    row = quatro_q_consumidor(monkeypatch)
    pac = pacote(row)
    for c in pac["disponibilidade_demonstrativos"][0]["componentes"]:
        for key in CAMPOS:
            c["fonte"].pop(key)
    assert conferir(pac)[0]
    assert not set(CAMPOS) & set(pac["disponibilidade_demonstrativos"][0]["fonte"])


def test_contexto_nao_tipado_nao_aceita_componente_tipado_por_condicionalidade(monkeypatch):
    row = escolher(coletor(semestres(tipado=False), monkeypatch)).iloc[0]
    pac = pacote(row)
    assert conferir(pac)[0]
    pac["disponibilidade_demonstrativos"][0]["componentes"][0].update(PAR)
    assert not conferir(pac)[0]
