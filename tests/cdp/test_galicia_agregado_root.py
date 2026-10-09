"""Adulterações de grão após coleta normal; transporte DADOS SIMULADOS."""
import pandas as pd
import pytest
from galicia_fixture_observada import CORTE, DIA, coletor, pacote, row_ttm

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes, conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.cobertura.temporal import construir


@pytest.mark.parametrize('campo,valor', [
    ('currency', 'USD'), ('item', 'receita'), ('consolidado', False),
    ('period_end', pd.Timestamp('2026-05-31')),
    ('period_end', pd.Timestamp('2026-07-31')),
])
def test_agregado_adulterado_recusado_no_fluxo_normal(monkeypatch, campo, valor):
    original, _ = coletor(monkeypatch)
    row = row_ttm(original)
    original_pack = pacote(row)
    assert conferir(original_pack)[0]
    altered = original.copy(deep=True)
    target = altered.freq.eq('TTM') & altered.period_end.eq(pd.Timestamp('2026-06-30'))
    altered.loc[target, campo] = valor
    try:
        consumer = Demonstrativos(altered, 'AR_GALICIA')
        item = 'receita' if campo == 'item' else 'lucro_liquido_controladores'
        amount, consumed = consumer.valor(item)
        assert consumed is not None
        assert consumed.contexto_documental == row.contexto_documental
        _prov_linha(consumed, detalhar_fluxos=True)
        destination = 't.' + item
        changed_pack = dict(issuer_id='AR_GALICIA', as_of=DIA.isoformat(),
                            corte_temporal=construir(DIA, CORTE),
                            **{destination: amount})
        registry = RegistroParticipantes('AR_GALICIA')
        registry.registrar(consumed, destination)
        registry.finalizar(changed_pack)
        accepted, _ = conferir(changed_pack)
    except ValueError:
        return
    assert accepted is False
