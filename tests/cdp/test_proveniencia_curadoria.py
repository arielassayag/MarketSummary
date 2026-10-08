"""Proveniência de transcrição não pode autenticar bytes primários nunca capturados."""
import hashlib
from datetime import UTC, date, datetime

import pytest

from cdp.cobertura.passos import Registro, prov_dict
from cdp.data.publico import Proveniencia
from cdp.data.publico_arquivo import RegistroArquivo


def test_bytes_publicos_arquivados_conservam_hash_e_captura():
    content = b'DADOS SIMULADOS: documento publico do controle'
    sha = hashlib.sha256(content).hexdigest()
    capture = datetime(2026, 10, 7, 11, 0, tzinfo=UTC)
    record = RegistroArquivo('controle', 'RI', 'https://example.org/controle.pdf',
                             'controle.pdf', sha, len(content), capture)
    public = Proveniencia.de_registro(record, documento='DADOS SIMULADOS',
                                      data_publicacao=date(2026, 10, 6))
    output = prov_dict(public)
    assert output == {'fonte': 'RI', 'url': record.url, 'documento': 'DADOS SIMULADOS',
                      'data_publicacao': '2026-10-06', 'data_coleta': capture.isoformat(),
                      'sha256': sha}
    assert prov_dict(output) == output
    assert 'curadoria' not in output


def test_hash_curadoria_permanece_distinto_do_documento_primario():
    source = {'fonte': 'RI', 'url': 'https://example.org/participacoes.pdf',
              'documento': 'DADOS SIMULADOS — participações transcritas',
              'data_publicacao': '2026-10-06', 'data_coleta': None, 'sha256': None,
              'curadoria': {'arquivo': 'cobertura/sotp.yaml', 'sha256': 'a' * 64}}
    output = prov_dict(source)
    assert output == source
    assert output['sha256'] is None and output['data_coleta'] is None
    assert output['curadoria']['sha256'] != output['sha256']
    record = Registro()
    record.add('controle', 'DADOS SIMULADOS', '1', '1', 1, 'n', fontes=[output])
    assert record.passos[0]['fontes'] == [output]


def test_leitor_conserva_proveniencia_historica_sem_reinterpretar_digest():
    archived = {'fonte': 'RI', 'url': 'https://example.org/DADOS_SIMULADOS.pdf',
                'documento': 'DADOS SIMULADOS — proveniência histórica sem tipo de digest',
                'data_publicacao': '2026-10-06', 'data_coleta': None, 'sha256': 'a'*64}
    assert prov_dict(archived) == archived
    assert 'curadoria' not in prov_dict(archived)


def test_digests_distintos_de_curadoria_nao_sao_descartados_na_memoria():
    source = {'fonte': 'DAMODARAN', 'url': 'https://example.org/betas.xls',
              'documento': 'DADOS SIMULADOS', 'sha256': None, 'data_coleta': None,
              'data_publicacao': '2026-01-07'}
    first = {**source, 'curadoria': {'arquivo': 'cobertura/betas_setor.csv', 'sha256': 'a'*64}}
    second = {**source, 'curadoria': {'arquivo': 'cobertura/betas_setor.csv', 'sha256': 'b'*64}}
    record = Registro()
    record.add('controle', 'DADOS SIMULADOS', '1', '1', 1, 'n', fontes=[first, second, first])
    assert record.passos[0]['fontes'] == [prov_dict(first), prov_dict(second)]


def test_curadoria_sem_hash_nao_inventa_bytes_ou_coleta():
    from cdp.cobertura.passos import prov_curadoria

    output = prov_curadoria(fonte='RI', url='https://example.org/controle.pdf',
                            documento='DADOS SIMULADOS', data_publicacao=None,
                            arquivo='cobertura/sotp.yaml', sha256_curadoria=None)
    assert output['sha256'] is None and output['data_coleta'] is None
    assert output['data_publicacao'] is None
    assert output['curadoria'] == {'arquivo': 'cobertura/sotp.yaml', 'sha256': None}


@pytest.mark.parametrize('invalid', ['abc', {'sha256': 'a'*64}, {'arquivo': None}])
def test_curadoria_sem_tipo_e_arquivo_explicitos_e_recusada(invalid):
    with pytest.raises(ValueError, match='curadoria sem arquivo'):
        prov_dict({'fonte': 'RI', 'curadoria': invalid})


@pytest.fixture(scope='module')
def base_simulada():
    from cdp.cobertura.fontes import coletar
    from cdp.cobertura.parametros import carregar_parametros
    from cdp.data.synthetic import make_synthetic_market

    day = date(2026, 10, 8)
    market = make_synthetic_market(seed=7, as_of=day)
    params = carregar_parametros()
    ids = list(market.universe.issuers.index)
    data = coletar(market, day, ids, list(market.universe.lines.index), [])
    return market, params, data, day


def test_preparador_normal_do_beta_nao_atribui_hash_csv_a_planilha(base_simulada):
    from cdp.cobertura.insumos import preparar_emissor

    market, params, data, day = base_simulada
    iid = next(iter(market.universe.issuers.index))
    package = preparar_emissor(market, data, params, iid, day)
    source = package['fontes']['beta_u_setor']
    assert source['fonte'] == 'DAMODARAN' and source['url']
    assert source['sha256'] is None and source['data_coleta'] is None
    assert source['curadoria'] == {'arquivo': 'cobertura/betas_setor.csv',
                                   'sha256': params.arquivos['cobertura/betas_setor.csv']}
    table = next(p for p in package['tabela_insumos'] if p['id'] == 'beta_u_setor')
    assert table['curadoria'] == source['curadoria'] and table['sha256'] is None


def test_preparador_normal_da_holding_nao_atribui_hash_yaml_a_pdf(base_simulada):
    from copy import deepcopy

    from cdp.cobertura.insumos import preparar_soma_partes

    market, original_params, _, day = base_simulada
    params = deepcopy(original_params)
    hold, investee = list(market.universe.issuers.index)[:2]
    line = market.universe.primary_ticker(hold)
    currency = str(market.universe.lines.loc[line, 'currency'])
    params.sotp['holdings'][hold] = {
        'participacoes': [{'emissor': investee, 'fracao': 0.25, 'conferido': True,
                          'url': 'https://example.org/DADOS_SIMULADOS.pdf',
                          'fonte': 'RI', 'documento': 'DADOS SIMULADOS — participação',
                          'data_publicacao': '2026-10-06', 'data_referencia': '2026-10-06'}]}
    package = {'issuer_id': hold, 'linha': line, 'moeda': currency, 'lacunas': []}
    preparar_soma_partes(market, params, package, day)
    part = package['soma_partes']['partes'][0]
    assert part['valor_participacao'] > 0 and part['fracao'] == 0.25
    assert part['fonte']['sha256'] is None and part['fonte']['data_coleta'] is None
    assert part['fonte']['curadoria'] == {'arquivo': 'cobertura/sotp.yaml',
                                         'sha256': params.arquivos['cobertura/sotp.yaml']}
