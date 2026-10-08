"""DADOS SIMULADOS: participante causal, independente de publicação histórica."""
import copy
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes, conferir
from cdp.cobertura.fontes import coletar
from cdp.cobertura.insumos import preparar_emissor
from cdp.cobertura.parametros import carregar_parametros
from cdp.cobertura.temporal import construir
from cdp.data.synthetic import make_synthetic_market


@lru_cache(maxsize=1)
def contexto():
    day = date(2026, 10, 8)
    md = make_synthetic_market(seed=7, as_of=day)
    params = carregar_parametros(Path(__file__).parents[2] / 'configs/cdp/valuation.yaml')
    ids = list(md.universe.issuers.index)
    dados = coletar(md, day, ids, list(md.universe.lines.index), [])
    val = copy.deepcopy(params.valuation)
    val['qualidade']['demonstrativos_disponibilidade_metodo'] = 'recepcao_observada'
    val['projecao']['resultado_corte_metodo'] = 'base_preco_conhecimento_explicitos'
    params = replace(params, valuation=val)
    frame = dados.demonstrativos.copy()
    select = pd.Series(True, index=frame.index)
    md.fundamentals['market_cap_disponivel_desde'] = '2026-10-08T12:00:00+00:00'
    md.fundamentals['preco_disponivel_desde'] = '2026-10-08T12:00:00+00:00'
    frame.loc[select, 'data_publicacao'] = None
    frame.loc[select, 'disponibilidade_tipo'] = 'recepcao_observada'
    frame.loc[select, 'disponivel_desde'] = '2026-10-08T12:00:00+00:00'
    dados = replace(dados, demonstrativos=frame, corte_temporal=construir(day, datetime(2026, 10, 8, 18, tzinfo=UTC)))
    return md, dados, params, day


def pacote():
    md, dados, params, day = contexto()
    return preparar_emissor(md, dados, params, 'SIM003', day)


def minimo(row):
    pac = {'issuer_id': 'SIM003', 'as_of': '2026-10-08',
           'corte_temporal': construir(date(2026, 10, 8), datetime(2026, 10, 8, 18, tzinfo=UTC)),
           't.receita': 100}
    registro = RegistroParticipantes('SIM003')
    registro.registrar(row, 't.receita')
    registro.finalizar(pac)
    return pac


def test_rececao_valida_nao_inventa_publicacao_nem_pit():
    pac = pacote()
    assert conferir(pac)[0]
    assert pac['pit_ok'] is False
    assert pac['max_data_publicacao'] is None


@pytest.mark.parametrize('available', [None, '2026-10-08T12:00:00', '2026-10-08', '2026-10-08T18:00:00.000001+00:00'])
def test_um_participante_invalido_nao_some_em_max(available):
    pac = copy.deepcopy(pacote())
    pac['disponibilidade_demonstrativos'][0]['disponivel_desde'] = available
    assert not conferir(pac)[0]


@pytest.mark.parametrize('available', [None, '2026-10-08T12:00:00', '2026-10-08T18:00:01+00:00'])
def test_ttm_agregado_valido_nao_oculta_componente_invalido(available):
    row = pd.Series({'item': 'receita', 'freq': 'TTM', 'period_end': pd.Timestamp('2026-06-30'),
                     'disponivel_desde': '2026-10-08T12:00:00+00:00',
                     'componentes_fluxo': json.dumps([{'item': 'receita', 'freq': 'A', 'period_end': '2025-12-31',
                         'fonte': {'disponivel_desde': available}}])})
    pac = minimo(row)
    assert not conferir(pac)[0]


def test_utc_offsets_comparados_como_instantes_no_corte_exato():
    pac = copy.deepcopy(pacote())
    for row in pac['disponibilidade_demonstrativos']:
        row['disponivel_desde'] = '2026-10-08T19:00:00+01:00'
        if 'disponivel_desde' in row['fonte']:
            row['fonte']['disponivel_desde'] = row['disponivel_desde']
    assert conferir(pac)[0]


def test_fluxo_reportado_no_mesmo_pdf_nao_exige_trimestres_inventados():
    row = pd.Series({'item': 'receita', 'freq': 'TTM', 'period_end': pd.Timestamp('2026-06-30'),
                     'disponivel_desde': '2026-10-08T12:00:00+00:00'})
    pac = minimo(row)
    assert conferir(pac)[0]


@pytest.mark.parametrize('components', ['[', '[]', '[{"item":"receita"}]'])
def test_componentes_marcados_malformados_recusados(components):
    row = pd.Series({'item': 'receita', 'freq': 'TTM', 'period_end': pd.Timestamp('2026-06-30'),
                     'disponivel_desde': '2026-10-08T12:00:00+00:00', 'componentes_fluxo': components})
    pac = minimo(row)
    assert not conferir(pac)[0]


@pytest.mark.parametrize('cut', [None, {'metodo': 'base_preco_conhecimento_explicitos'}])
def test_corte_incompleto_recusado(cut):
    pac = pacote()
    pac['corte_temporal'] = cut
    assert not conferir(pac)[0]


def test_linha_financeira_nao_selecionada_nao_contamina_guard():
    md, dados, params, day = contexto()
    unused = dados.demonstrativos[dados.demonstrativos.issuer_id.eq('SIM003')].iloc[0].copy()
    unused['item'] = 'item_desconhecido_nao_usado'
    unused['disponivel_desde'] = '2099-01-01T00:00:00+00:00'
    changed = replace(dados, demonstrativos=pd.concat([dados.demonstrativos, unused.to_frame().T], ignore_index=True))
    pac = preparar_emissor(md, changed, params, 'SIM003', day)
    assert conferir(pac)[0]
    assert not any(r['item'] == unused['item'] for r in pac['disponibilidade_demonstrativos'])


def test_componentes_da_linha_prevalecem_sobre_nota_antiga():
    valid = [{'item': 'receita', 'freq': 'A', 'period_end': '2025-12-31',
              'fonte': {'disponivel_desde': '2026-10-08T12:00:00+00:00'}}]
    row = pd.Series({'item': 'receita', 'freq': 'TTM', 'period_end': pd.Timestamp('2026-06-30'),
                     'disponivel_desde': '2026-10-08T12:00:00+00:00',
                     'componentes_fluxo': json.dumps(valid), 'nota': 'componentes_fluxo=[]'})
    pac = minimo(row)
    assert conferir(pac)[0]


def test_sem_data_modelo_nao_ignora_validacao_do_corte():
    pac = pacote()
    pac.pop('as_of')
    assert not conferir(pac)[0]
