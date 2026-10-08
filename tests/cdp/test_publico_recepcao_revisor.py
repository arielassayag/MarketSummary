"""DADOS SIMULADOS: controles não autores, oráculo financeiro Decimal independente."""

import csv
import io
import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal as D

import pandas as pd
import pytest

from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.data.publico import _qa_magnitude, _refazer_derivados
from cdp.data.publico_arquivo import Arquivo
from cdp.data.publico_confirmacao_cvm import ConfirmacaoCVM
from cdp.data.publico_cvm import url_zip
from cdp.data.publico_fatos import _derivados, _observacao_componentes, selecionar_pit

CN = '82.901.000/0001-27'
LINK = 'http://www.rad.cvm.gov.br/ENET/frmGerenciaPaginaFRE.aspx?NumeroSequencialDocumento=900001&CodigoTipoInstituicao=1'


def csv_bytes(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), delimiter=';')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def publico(tmp_path, duplicate=False):
    index = {'CNPJ_CIA': CN, 'DT_REFER': '2026-06-30', 'VERSAO': '1',
             'CD_CVM': '025453', 'ID_DOC': '900001', 'LINK_DOC': LINK, 'DT_RECEB': '2026-07-29'}
    raw = {'CNPJ_CIA': CN, 'DT_REFER': '2026-06-30', 'VERSAO': '1', 'CD_CVM': '025453',
           'DT_FIM_EXERC': '2026-06-30', 'ORDEM_EXERC': 'ÚLTIMO', 'CD_CONTA': '1.01.02',
           'MOEDA': 'REAL', 'ESCALA_MOEDA': 'MIL', 'VL_CONTA': '10.125',
           'DS_CONTA': 'Aplicações — DADOS SIMULADOS'}
    body = io.BytesIO()
    with zipfile.ZipFile(body, 'w') as z:
        z.writestr('itr_cia_aberta_2026.csv', csv_bytes([index]))
        z.writestr('itr_cia_aberta_BPA_con_2026.csv', csv_bytes([raw, raw] if duplicate else [raw]))
    arq = Arquivo(tmp_path, conhecimento_ate=datetime.max.replace(tzinfo=UTC))
    reg = arq.gravar('CVM/ITR/itr_cia_aberta_2026.zip', 'CVM', url_zip('ITR', 2026), body.getvalue())
    confirm = ConfirmacaoCVM(arq, [reg], {'DADOS_SIMULADOS': CN}, corte=datetime.now(UTC))
    return confirm, reg


def fato(item='receita', value=10, *, available='2026-10-08T19:00:00+00:00',
         received='2026-07-29', end='2026-06-30', publication=None):
    return {'entidade': CN, 'issuer_id': 'DADOS_SIMULADOS', 'item': item, 'value': value,
            'freq': 'Q', 'period_start': '2026-04-01', 'period_end': end, 'anual': False,
            'currency': 'BRL', 'escala': 1, 'consolidado': True, 'fonte': 'CVM',
            'demonstrativo': 'BP', 'url': LINK, 'sha256': 'DADOS_SIMULADOS',
            'documento': 'ITR 2026-06-30 v1', 'nota': None, 'version': 1,
            'data_publicacao': publication, 'data_publicacao_primaria': publication,
            'received_date': received, 'disponibilidade_tipo': 'recepcao_observada',
            'disponivel_desde': available, 'data_recebimento_documento': '2026-07-29',
            'pit_estimado': False}


def target(reg, **changes):
    return pd.Series(fato('aplicacoes_cp', float(D('10.125') * D(1000))) |
                     {'sha256': reg.sha256} | changes)


def test_decimal_restore_exatamente_saldo_e_divida_na_formula_atual(tmp_path):
    verifier, reg = publico(tmp_path)
    row = target(reg)
    frame = pd.DataFrame([row.to_dict() | {'period_end': d, 'value': v} for d, v in
                          [('2025-12-31', 4_000_000), ('2026-03-31', 4_100_000), ('2026-06-30', row.value)]])
    before = _qa_magnitude(frame, [])
    assert pd.isna(before.iloc[-1].value)
    after = _qa_magnitude(frame, [], confirmacao_cvm=verifier)
    raw = json.loads(after.attrs['confirmacoes_cvm'][0]['evidencia'])
    expected = D(raw['literal']) * D(raw['factor_once'])
    assert D(str(after.iloc[-1].value)) == expected
    assert raw['classification_or_cash_flow_confirmed'] is False
    debt_rows = [fato('divida_bruta', 3_000_000), fato('caixa', 200_000), after.iloc[-1].to_dict()]
    result = _refazer_derivados(pd.DataFrame(debt_rows))
    debt = result.loc[result.item.eq('divida_liquida'), 'value'].iloc[0]
    assert D(str(debt)) == D(3_000_000) - D(200_000) - expected
    assert not any(result.item.eq('fcf'))


@pytest.mark.parametrize('changes', [{'value': None}, {'item': 'caixa'}, {'freq': 'TTM'},
                                    {'currency': 'USD'}, {'consolidado': False}, {'value': 10.125}])
def test_scope_ausencia_granulo_unitario_nunca_sao_restaurados(tmp_path, changes):
    verifier, reg = publico(tmp_path)
    assert verifier.resolver(target(reg, **changes)).estado != 'saldo_unidade_confirmados'


def test_bpa_duplicada_no_granulo_nao_confirma(tmp_path):
    verifier, reg = publico(tmp_path, True)
    assert verifier.resolver(target(reg)).estado == 'inconclusivo'


def test_disponibilidade_ausente_nao_e_publicacao_civil():
    row = fato() | {'disponivel_desde': None}
    assert selecionar_pit(pd.DataFrame([row]), date(2026, 10, 8)).empty


def test_disponibilidade_sem_fuso_nao_pode_ser_promovida_a_UTC():
    row = fato(available='2026-10-08T18:00:00')
    assert selecionar_pit(pd.DataFrame([row]), date(2026, 10, 8)).empty


def test_max_entre_offsets_e_max_de_instante_nao_lexicografico():
    first = fato('cfo', 40, available='2026-10-08T20:00:00+01:00')
    last = fato('capex', 11, available='2026-10-08T19:30:00+00:00')
    row = _derivados(pd.DataFrame([first, last])).iloc[0]
    assert D(str(row.value)) == D(40) - D(11)
    assert pd.Timestamp(row.disponivel_desde) == pd.Timestamp(last['disponivel_desde'])


def test_dado_nao_participante_nao_contamina_rececao_divida():
    rows = [fato('divida_bruta', 100), fato('caixa', 20), fato('aplicacoes_cp', 3),
            fato('ativo_total', 777, available='2099-01-01T00:00:00+00:00')]
    row = _derivados(pd.DataFrame(rows)).iloc[0]
    assert D(str(row.value)) == D(100) - D(20) - D(3)
    assert row.disponivel_desde == rows[0]['disponivel_desde']
    assert pd.isna(row.data_publicacao)


def test_civil_e_UTC_em_componentes_preservam_contratos_separados():
    civil = fato(received='2026-07-29')
    aware = fato(received=datetime(2026, 8, 4, tzinfo=UTC))
    out = _observacao_componentes([civil, aware])
    # Contrato explícito ROOT: civil+instante não ganham max com fuso inventado.
    assert out['received_date'] is None
    assert pd.Timestamp(out['disponivel_desde']) == pd.Timestamp(civil['disponivel_desde'])


def test_ttm_civil_e_UTC_preservam_valor_e_publicacao_ausente():
    rows = [fato(value=v, end=end, received=r) for v, end, r in [
        (2, '2025-09-30', '2026-07-29'), (3, '2025-12-31', '2026-07-29'),
        (5, '2026-03-31', datetime(2026, 8, 4, tzinfo=UTC)), (7, '2026-06-30', '2026-07-29')]]
    val, row = Demonstrativos(pd.DataFrame(rows), 'DADOS_SIMULADOS').valor('receita')
    assert D(str(val)) == sum(D(x) for x in [2, 3, 5, 7])
    assert pd.isna(row.data_publicacao)
    assert row.received_date is None
    componentes = _prov_linha(row, detalhar_fluxos=True)['componentes_fluxo']
    assert len(componentes) == 4
    for comp, original in zip(componentes, rows, strict=True):
        assert pd.Timestamp(comp['fonte']['received_date']) == pd.Timestamp(original['received_date'])


@pytest.fixture(autouse=True)
def relogio_portatil_revisor(monkeypatch):
    """DADOS SIMULADOS: independencia da data real; portabilidade por p0_bancos_argentinos."""
    monkeypatch.setattr("cdp.data.publico_fatos._agora_observado",
                        lambda: datetime(2026, 10, 9, 5, tzinfo=UTC))
