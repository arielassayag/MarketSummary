"""DADOS SIMULADOS: fonte opcional não preenche nem contradiz o contexto nativo."""

from copy import deepcopy

import pytest
from dimensoes_contabeis_fixtures import PAR, fato, selecionar, trimestres

from cdp.cobertura.disponibilidade_demonstrativos import _grupos
from cdp.cobertura.insumos import Demonstrativos
from cdp.data.dimensoes_contabeis import CAMPOS, compativeis, dimensoes


@pytest.mark.parametrize('fonte', [None, 'RI SIMULADO', {}, dict.fromkeys(CAMPOS), PAR])
def test_fonte_opcional_ausente_ou_igual_preserva_par_nativo(fonte):
    assert dimensoes({**PAR, 'fonte': fonte}) == PAR
    assert compativeis([{**PAR, 'fonte': fonte}, PAR])


@pytest.mark.parametrize('fonte', [
    {CAMPOS[0]: PAR[CAMPOS[0]]},
    {CAMPOS[1]: PAR[CAMPOS[1]]},
    {**PAR, CAMPOS[0]: 'OUTRA_SIMULADA'},
    {**PAR, CAMPOS[1]: '2025-12-31'},
    {**PAR, CAMPOS[0]: ' '},
    {**PAR, CAMPOS[1]: '2026-02-30'},
])
def test_fonte_presente_parcial_invalida_ou_contraditoria_recusada(fonte):
    with pytest.raises(ValueError):
        dimensoes({**PAR, 'fonte': fonte})
    assert not compativeis([{**PAR, 'fonte': fonte}, PAR])


def test_fonte_tipada_nao_preenche_topo_ausente():
    with pytest.raises(ValueError):
        dimensoes({'fonte': PAR})
    assert not compativeis([{'fonte': PAR}, PAR])
    assert dimensoes({'fonte': {}}) == {}


@pytest.mark.parametrize('campo,outro', [(CAMPOS[0], 'OUTRA_SIMULADA'), (CAMPOS[1], '2025-12-31')])
def test_consumidor_nao_compoe_grupo_de_q_com_fonte_contraditoria(campo, outro):
    quarters = trimestres()
    rows = [quarters[0], fato('2025-01-01', '2025-09-30', 60),
            fato('2025-01-01', '2025-12-31', 100), *quarters[2:]]
    selected = selecionar(rows)
    qs = selected[selected.freq.eq('Q')].copy()
    assert Demonstrativos(qs, 'SIMULADO').df.freq.eq('TTM').any()
    index = qs.index[qs.period_end.eq('2025-12-31')][0]
    grupos = deepcopy(_grupos(qs.loc[index])[0][1])
    # Declaração opcional explícita SIMULADA, inicialmente coerente; o parser não a inventa.
    for c in grupos:
        c['fonte'].update({k: c[k] for k in CAMPOS})
    qs['componentes_fluxo'] = None
    qs.at[index, 'componentes_fluxo'] = grupos
    assert Demonstrativos(qs, 'SIMULADO').df.freq.eq('TTM').any()
    grupos[0]['fonte'][campo] = outro
    # Só a fonte do componente efetivamente usado foi alterada; nenhuma cifra ou dimensão nativa.
    assert not Demonstrativos(qs, 'SIMULADO').df.freq.eq('TTM').any()
