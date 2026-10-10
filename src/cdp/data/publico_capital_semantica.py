"""Metadados de capital reportado; nenhum cálculo ou escolha de denominador."""
from __future__ import annotations

import copy
import json
import math

SCHEMA = 'cdp-capital-semantica-v1'
COLUNA = 'semantica_capital'
COMPOSICAO = (
    ('QT_ACAO_TOTAL_CAP_INTEGR', 'TOTAL'),
    ('QT_ACAO_ORDIN_CAP_INTEGR', 'ORDIN'),
    ('QT_ACAO_PREF_CAP_INTEGR', 'PREF'),
    ('QT_ACAO_TOTAL_TESOURO', 'TOTAL'),
    ('QT_ACAO_ORDIN_TESOURO', 'ORDIN'),
    ('QT_ACAO_PREF_TESOURO', 'PREF'),
)
FRE = (('Quantidade_Total_Acoes', 'TOTAL'), ('Quantidade_Acoes_Ordinarias', 'Ordinarias'),
       ('Quantidade_Acoes_Preferenciais', 'Preferenciais'))


def opcao(value):
    if not isinstance(value, bool):
        raise ValueError('preservar_semantica_capital exige bool explícito')
    return value


def texto(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if type(value).__name__ in ('NAType', 'NaTType'):
        return None
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def lexema(value):
    """Somente texto recebido é lexema bruto; número normalizado não ganha esse rótulo."""
    return value if isinstance(value, str) else None


def serializar(contexto):
    return json.dumps(contexto, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def ler(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if type(value).__name__ in ('NAType', 'NaTType'):
        return None
    try:
        context = json.loads(value) if isinstance(value, str) else copy.deepcopy(value)
    except (ValueError, TypeError) as exc:
        raise ValueError('Metadados de capital inválidos') from exc
    if not isinstance(context, dict) or context.get('schema') != SCHEMA:
        raise ValueError('Schema de semântica de capital desconhecido')
    for key in ('conceito_validado', 'classe_economica', 'direitos', 'ponte_liquida_validada'):
        if context.get(key) is not None:
            raise ValueError('Transporte de capital não valida conceito, classe, direitos ou ponte líquida')
    return context


def contexto(row, *, tipo, fonte=None, recebido=None, registro=None):
    """Projeção física da linha; datas e lexemas não são inferidos de outro valor."""
    fre = tipo == 'FRE'
    identity = 'CNPJ_Companhia' if fre else 'CNPJ_CIA'
    ref = 'Data_Referencia' if fre else 'DT_REFER'
    version = 'Versao' if fre else 'VERSAO'
    campos = FRE if fre else COMPOSICAO
    attributes = {str(key): lexema(value) for key, value in row.items()}
    units = next(({'campo': key, 'lexema': lexema(row[key])} for key in
                  ('UNIDADE_QT_ACAO', 'Unidade_Quantidade_Acoes') if key in row), None)
    scale = next(({'campo': key, 'lexema': lexema(row[key])} for key in
                  ('ESCALA_QT_ACAO', 'Escala_Quantidade_Acoes') if key in row), None)
    out = {'schema': SCHEMA, 'origem': 'CVM/FRE' if fre else 'CVM/composicao_capital',
        'cnpj': texto(row.get(identity)), 'cik': None, 'issuer_id_cadastro': None,
        'data_estoque': None if fre else lexema(row.get(ref)),
        'documento_data_referencia': lexema(row.get(ref)),
        'data_aprovacao': lexema(row.get('Data_Autorizacao_Aprovacao')) if fre else None,
        'versao_reportada_lexema': lexema(row.get(version)),
        'tipo_capital_reportado': lexema(row.get('Tipo_Capital')) if fre else None,
        'conceito_validado': None, 'classe_economica': None, 'direitos': None,
        'ponte_liquida_validada': None, 'unidade_reportada': units, 'escala_reportada': scale,
        'componentes': [{'campo': key, 'classe_designacao_fisica': cls,
                        'valor_reportado_lexema': lexema(row.get(key)),
                        'valor_entrada_normalizada_texto': texto(row.get(key)) if not isinstance(row.get(key), str) else None}
                       for key, cls in campos],
        'campos_fisicos': attributes, 'data_recebimento_documento': texto(recebido),
        'recepcao_observada_UTC': None, 'limite_recepcao_UTC': None,
        'precisao_recepcao_registro': None, 'data_coleta_registro_texto': None,
        'data_publicacao_primaria': None,
        'fonte': copy.deepcopy(fonte) if fonte is not None else None,
        'registro_csv_1based': registro, 'linha_fisica_csv': None,
        'conceitos_reportados': [key for key, _ in campos if key in row],
        'conflitos_documentais': None,
        'estatuto': 'Metadado da linha recebida; não certifica fato financeiro, fonte efetiva G2 ou PIT nominal.',
        'limite': 'Nomes físicos e proximidade numérica não validam bruto/líquido, classes econômicas ou estoque contemporâneo.'}
    out['ausencias'] = [{'campo': key, 'motivo': 'Este transporte não recebeu declaração documental suficiente.'}
        for key in ('data_estoque', 'data_aprovacao', 'unidade_reportada', 'escala_reportada',
                    'classe_economica', 'direitos', 'ponte_liquida_validada', 'data_publicacao_primaria')
        if out[key] is None]
    return serializar(out)


def contextos_composicao(capital, indice):
    """Registros lógicos do CSV e índice; número de linha física não é inferido."""
    if capital is None:
        return []
    rows = capital.attrs.get('capital_semantica_linhas')
    if rows is None:
        rows = [{'raw': row, 'registro_csv_1based': None} for row in capital.to_dict('records')]
    index = [] if indice is None else indice.to_dict('records')
    result = []
    for record in rows:
        row = record['raw']
        matches = [r for r in index if all(texto(r.get(key)) == texto(row.get(key))
                   for key in ('CNPJ_CIA', 'DT_REFER', 'VERSAO'))]
        match = matches[0] if len(matches) == 1 else {}
        source = copy.deepcopy(capital.attrs.get('capital_semantica_fonte')) or {}
        source['url_documento'] = texto(match.get('LINK_DOC'))
        result.append(contexto(row, tipo='COMPOSICAO', fonte=source,
            recebido=match.get('DT_RECEB'), registro=record['registro_csv_1based']))
    return result


def para_item(value, item, unidade_legada=None):
    out = ler(value)
    out['item_legado'] = item
    out['politica_unidade_legada'] = texto(unidade_legada)
    out['formula_legada'] = ('QT_ACAO_TOTAL_CAP_INTEGR - QT_ACAO_TOTAL_TESOURO'
        if item == 'acoes_em_circulacao' else 'QT_ACAO_TOTAL_CAP_INTEGR' if item == 'acoes_emitidas'
        else 'QT_ACAO_TOTAL_TESOURO' if item == 'acoes_tesouraria' else None)
    return serializar(out)


def vincular_registro(value, registro):
    out = ler(value)
    source = out.get('fonte') or {}
    if source.get('arquivo_sha256') not in (None, registro.sha256):
        raise ValueError('Semântica de capital contradiz SHA do arquivo')
    source.update(arquivo_sha256=registro.sha256, url_arquivo=registro.url)
    out['fonte'] = source
    out['data_coleta_registro_texto'] = texto(registro.data_coleta)
    out['precisao_recepcao_registro'] = registro.precisao
    if registro.data_coleta.tzinfo is not None:
        from datetime import UTC

        out['recepcao_observada_UTC'] = registro.data_coleta.astimezone(UTC).isoformat()
        out['limite_recepcao_UTC'] = registro.limite_captura.astimezone(UTC).isoformat()
    return serializar(out)


def discriminacao_contagem(*, contagem, rows_acoes, oficial, observacoes, linha, apl,
                          data_preco, data_mercado, mercado, ratio_curado):
    """Anota o resultado já calculado; não altera a decisão ou participantes do G2."""
    def bloco(origem, componentes):
        return {'origem': origem, 'contagem_legada_texto': texto(contagem['candidatos'].get(origem)),
                'componentes': componentes, 'conceito_validado': None,
                'classe_economica': None, 'data_estoque': None, 'conflitos_documentais': None}

    dem = []
    for row in rows_acoes:
        raw = ler(row.get(COLUNA))
        dem.append({'item_legado': row.get('item'), 'metadata_reportado': raw,
            'period_end_legado': texto(row.get('period_end')),
            'valor_legado_texto': texto(row.get('value')),
            'fonte_legada': {key: texto(row.get(key)) for key in ('fonte', 'url', 'sha256', 'documento')}})
    fre = None if oficial is None else oficial.get(COLUNA)
    participants = [bloco('demonstracoes', dem), bloco('oficial', [] if fre is None else [fre]),
                    bloco('valor_de_mercado', [])]
    participants[2]['mercado'] = {'valor_mercado_legado_texto': texto(mercado.get('market_cap')),
        'data_snapshot_mercado': texto(data_mercado), 'data_preco_consumido': texto(data_preco),
        'data_estoque': None, 'valor_reportado_lexema': None,
        'disponibilidade_mercado_reportada': texto(mercado.get('market_cap_disponivel_desde'))}
    missing = []
    for participant in participants:
        if participant['contagem_legada_texto'] is None:
            missing.append({'participante': participant['origem'], 'campo': 'contagem_legada',
                            'motivo': 'Contagem ausente no resultado legado; não preenchida.'})
        if not participant['componentes']:
            missing.append({'participante': participant['origem'], 'campo': 'metadata_fisico_capital',
                            'motivo': 'Este caminho não forneceu metadado físico de capital para o participante.'})
    missing.extend({'campo': key, 'motivo': 'Este transporte não confirma uma declaração contemporânea.'}
                   for key in ('ratio_documental_contemporaneo', 'classe_subjacente', 'ponte_liquida_validada'))
    return {'schema': SCHEMA, 'participantes': participants, 'ausencias': missing,
        'fontes_efetivas_G2_legadas': copy.deepcopy(contagem.get('fontes_participantes')),
        'observacoes_documentais_recebidas': [ler(value) for value in observacoes],
        'linha': linha, 'acoes_por_linha_legadas_texto': texto(apl),
        'ratio_curadoria_legada': copy.deepcopy(ratio_curado),
        'ratio_documental_contemporaneo': None, 'classe_subjacente': None,
        'ponte_liquida_validada': None, 'conflitos_documentais': None,
        'limites': ['Resultado financeiro e fontes efetivas G2 preservados.',
            'FRE referência/aprovação não estabelece estoque de junho.',
            'Proximidade numérica não valida bruto/líquido, classe, escala ou paridade contemporânea.',
            'Conflitos de canais não recebidos por este transporte permanecem desconhecidos.']}
