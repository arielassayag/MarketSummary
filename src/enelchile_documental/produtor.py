"""Candidato opt-in, puro e fechado: empréstimos Enel Chile Nota 20/20.1 e leases Nota 21.

Não importa CDP, não abre arquivos/rede e não emite fatos canônicos. A API pública
autentica corpo/recibo antes da extração e aceita somente o corpo primário já recebido.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction

from lxml import etree, html

CIK = '0001659939'
ACCESSION = '0001104659-26-050251'
BODY_SHA256 = 'fe0cb64242a503309cf75c5a4ed292569073ea6c0014ec351c5d5c2485566102'
BODY_BYTES = 38598294
RECEIPT_SHA256 = '2d4710181623696931d02c901ab4f44864ead53a5d969de7f45bc3aa456e0a2e'
URL = ('https://www.sec.gov/Archives/edgar/data/1659939/000110465926050251/'
       'enic-20251231x20f_htm.xml')
END = '2025-12-31'
START = '2025-01-01'
XBRL = 'http://www.xbrl.org/2003/instance'
XBRLDI = 'http://xbrl.org/2006/xbrldi'
IFRS = 'https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full'
CUSTOM = 'http://www.enelchile.cl/20251231'
DEI = 'http://xbrl.sec.gov/dei/2025'
ISO = 'http://www.xbrl.org/2003/iso4217'
DIMENSIONS = [(f'{{{IFRS}}}CategoriesOfFinancialLiabilitiesAxis',
               f'{{{IFRS}}}FinancialLiabilitiesAtAmortisedCostCategoryMember')]
NUMERIC = re.compile(r'[0-9]+(?:\.[0-9]+)?\Z')
HTML_NUMBER = re.compile(r'(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\Z')


class InvalidDocument(ValueError):
    """Documento fora do contrato específico; nenhum resultado parcial é devolvido."""


def _require(condition, reason):
    if not condition:
        raise InvalidDocument(reason)


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _json_pairs(pairs):
    obj = {}
    for key, value in pairs:
        _require(key not in obj, 'Recibo com chave duplicada')
        obj[key] = value
    return obj


def _utc(value, label):
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        _require(isinstance(parsed, datetime) and parsed.tzinfo is not None,
                 f'{label} ausente, inválido ou sem fuso')
        _require(parsed.utcoffset() is not None, f'{label} sem fuso')
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidDocument(f'{label} ausente, inválido ou sem fuso') from exc


def extrair_enel(body: bytes, receipt_body: bytes, receipt_sha256: str,
                 knowledge_cutoff: datetime, *, enabled: bool = False) -> dict | None:
    """Retorna envelope documental opcional, sem chamar/modificar o parser default.

    ``receipt_sha256`` deve vir do manifesto confiável do chamador, separado do
    próprio recibo. Conferir bytes não autentica as afirmações do recibo nem prova PIT.
    A fonte é fixada por SHA/bytes além de URL/accession, sem parâmetro para relaxar o pin.
    """
    _require(type(enabled) is bool, 'Opt-in precisa ser booleano explícito')
    if not enabled:
        return None
    _require(type(body) is bytes and type(receipt_body) is bytes, 'Corpo/recibo precisam ser bytes')
    _require(isinstance(receipt_sha256, str) and re.fullmatch(r'[0-9a-f]{64}', receipt_sha256),
             'SHA externo do recibo ausente ou inválido')
    _require(_sha(receipt_body) == receipt_sha256, 'SHA do recibo diverge do manifesto')
    try:
        receipt = json.loads(receipt_body, object_pairs_hook=_json_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidDocument('Recibo JSON inválido') from exc
    _require(isinstance(receipt, Mapping), 'Recibo precisa ser objeto')
    _require(type(receipt.get('bytes')) is int and receipt['bytes'] == len(body),
             'Tamanho do corpo diverge do recibo')
    _require(receipt.get('sha256') == _sha(body), 'SHA do corpo diverge do recibo')
    _require(len(body) == BODY_BYTES and receipt['sha256'] == BODY_SHA256,
             'Corpo fora da fonte primária fechada')
    _require(receipt.get('url') == URL and receipt.get('fonte') == 'SEC', 'URL/fonte fora do contrato')
    for name, expected in [('cik', CIK), ('accn', ACCESSION), ('form', '20-F'), ('period_end', END)]:
        _require(name not in receipt or receipt[name] == expected, f'Recibo contradiz {name}')
    received = _utc(receipt.get('data_coleta'), 'Recepção do recibo')
    _require(receipt_sha256 == RECEIPT_SHA256, 'Recibo fora da recepção literal fechada')
    cutoff = _utc(knowledge_cutoff, 'Corte de conhecimento')
    _require(received <= cutoff, 'Recepção posterior ao corte de conhecimento')
    source = {'sha256': receipt['sha256'], 'bytes': len(body), 'receipt_sha256': receipt_sha256,
              'receipt_literal': dict(receipt), 'url': URL, 'accn': ACCESSION,
              'received_at_utc': received.isoformat(), 'knowledge_cutoff_utc': cutoff.isoformat(),
              'first_publication_utc': None, 'filed_date': None,
              'PIT_certified': False, 'executor_possession_at_cutoff_proven': False}
    return _extract_document(body, source, simulated=False)


def _local(node):
    return etree.QName(node).localname


def _qname(node, lexical):
    _require(isinstance(lexical, str) and lexical.count(':') == 1, 'QName ausente ou inválido')
    prefix, name = lexical.split(':')
    _require(prefix in node.nsmap and bool(name), 'QName sem namespace conhecido')
    return f'{{{node.nsmap[prefix]}}}{name}'


def _text(text):
    return ' '.join(text.replace('\u200b', '').split())


def _raw_context(node):
    return {'id': node.get('id'), 'sha256_serializado': _sha(etree.tostring(node)),
            'entity': [{'attrs': dict(x.attrib), 'lexema': x.text}
                       for x in node.findall(f'.//{{{XBRL}}}identifier')],
            'period': [{'tag': x.tag, 'lexema': x.text}
                       for x in node.findall(f'{{{XBRL}}}period/*')],
            'dimensions': [{'tag': x.tag, 'attrs': dict(x.attrib), 'lexema': x.text}
                           for x in node.iter() if _local(x) in {'explicitMember', 'typedMember'}]}


def _validate_context(ctx, *, annual, expected_dimensions):
    _require(set(x.tag for x in ctx) == {f'{{{XBRL}}}entity', f'{{{XBRL}}}period'},
             'Contexto com escopo adicional ou estrutura desconhecida')
    entities, periods = ctx.findall(f'{{{XBRL}}}entity'), ctx.findall(f'{{{XBRL}}}period')
    _require(len(entities) == len(periods) == 1, 'Entidade/período duplicado')
    ids = entities[0].findall(f'{{{XBRL}}}identifier')
    _require(len(ids) == 1 and ids[0].text == CIK and ids[0].attrib == {'scheme': 'http://www.sec.gov/CIK'},
             'Entidade fora do CIK consolidado Enel')
    _require(all(x.tag in {f'{{{XBRL}}}identifier', f'{{{XBRL}}}segment'} for x in entities[0]),
             'Entidade com estrutura desconhecida')
    expected = [('startDate', START), ('endDate', END)] if annual else [('instant', END)]
    _require([(_local(x), x.text) for x in periods[0]] == expected and
             all(etree.QName(x).namespace == XBRL for x in periods[0]), 'Período fora do contrato')
    dims = [x for x in ctx.iter() if _local(x) in {'explicitMember', 'typedMember'}]
    _require(all(x.tag == f'{{{XBRLDI}}}explicitMember' and set(x.attrib) == {'dimension'}
                 and len(x) == 0 for x in dims), 'Dimensão typed/estrutura desconhecida')
    resolved = [(_qname(x, x.get('dimension')), _qname(x, x.text)) for x in dims]
    _require(resolved == expected_dimensions, 'Dimensões fora do contrato')
    segments = entities[0].findall(f'{{{XBRL}}}segment')
    _require(len(segments) <= 1 and all(len(seg) == len(dims) for seg in segments),
             'Segmento contém informação fora das dimensões aceitas')
    return _raw_context(ctx)


def _grid(table):
    rows = table.xpath('./tr|./tbody/tr|./thead/tr|./tfoot/tr')
    grid = []
    for y, row in enumerate(rows):
        while len(grid) <= y:
            grid.append([])
        col = 0
        for ordinal, cell in enumerate(row.xpath('./td|./th')):
            while col < len(grid[y]) and grid[y][col] is not None:
                col += 1
            try:
                colspan, rowspan = int(cell.get('colspan', 1)), int(cell.get('rowspan', 1))
            except (ValueError, TypeError) as exc:
                raise InvalidDocument('Span HTML inválido') from exc
            _require(1 <= colspan <= 13 and 1 <= rowspan <= 8, 'Span HTML fora do contrato')
            record = {'raw_text': cell.text_content(), 'text': _text(cell.text_content()),
                      'row_0base': y, 'cell_ordinal_0base': ordinal,
                      'expanded_column_0base': col, 'colspan': colspan, 'rowspan': rowspan,
                      'attrs': dict(cell.attrib), 'sha256_serializado': _sha(etree.tostring(cell))}
            for yy in range(y, y + rowspan):
                while len(grid) <= yy:
                    grid.append([])
                while len(grid[yy]) < col + colspan:
                    grid[yy].append(None)
                for xx in range(col, col + colspan):
                    _require(grid[yy][xx] is None, 'Solapamento HTML')
                    grid[yy][xx] = record
            col += colspan
    return grid


def _html_amount(cell):
    _require(cell is not None and HTML_NUMBER.fullmatch(cell['text']),
             'Célula monetária ausente, travessão ou inválida')
    return Fraction(cell['text'].replace(',', '')) * 1000


def _finite_decimal(value: Fraction) -> str:
    """Transmite fração decimal finita sem usar precisão/rounding do chamador."""
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    _require(denominator == 1, 'Valor fora do domínio decimal finito')
    places = max(twos, fives)
    if places == 0:
        return str(value.numerator)
    unscaled = abs(value.numerator) * (10 ** places // value.denominator)
    digits = str(unscaled).rjust(places + 1, '0')
    sign = '-' if value.numerator < 0 else ''
    return sign + digits[:-places] + '.' + digits[-places:]


def _extract_document(body, source, *, simulated):
    """Núcleo sem filesystem; fixtures entram somente aqui, marcadas como simuladas."""
    _require(type(body) is bytes and type(simulated) is bool, 'Entrada interna inválida')
    _require(len(body) <= 50_000_000, 'XML acima do limite')
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, recover=False)
    try:
        root = etree.fromstring(body, parser)
    except etree.XMLSyntaxError as exc:
        raise InvalidDocument('Instância XML inválida') from exc
    _require(root.tag == f'{{{XBRL}}}xbrl' and not root.getroottree().docinfo.doctype,
             'Raiz/DTD fora do contrato')
    indexes, contexts, units = {}, {}, {}
    for ordinal, node in enumerate(root):
        _require(isinstance(node.tag, str), 'Nó XML não elementar fora do contrato')
        indexes.setdefault(node.tag, []).append((ordinal, node))
        if node.tag in {f'{{{XBRL}}}context', f'{{{XBRL}}}unit'}:
            store = contexts if _local(node) == 'context' else units
            _require(node.get('id') and node.get('id') not in store, 'ID contexto/unidade duplicado ou ausente')
            store[node.get('id')] = node

    def single(tag):
        nodes = indexes.get(tag, [])
        _require(len(nodes) == 1, f'Localizador ausente/duplicado: {tag}')
        return nodes[0]

    def context(node):
        _require(node.get('contextRef') in contexts, 'contextRef ausente ou não recebido')
        return contexts[node.get('contextRef')]

    def block(namespace, name, note, *, table=False):
        ordinal, node = single(f'{{{namespace}}}{name}')
        _require(node.text and node.get('id'), 'Textblock sem corpo/id')
        _require(set(node.attrib) == {'contextRef', 'id'} and len(node) == 0,
                 'Textblock com nil/atributo/estrutura fora do contrato')
        ctx = _validate_context(context(node), annual=True, expected_dimensions=[])
        try:
            parsed = html.fromstring(node.text)
        except (etree.ParserError, ValueError) as exc:
            raise InvalidDocument('Textblock HTML inválido') from exc
        tables = parsed.xpath('self::table|.//table')
        if table:
            _require(len(tables) == 1, 'Tabela ausente/duplicada no textblock')
        return {'ordinal_xml_0base': ordinal, 'tag': node.tag, 'attrs': dict(node.attrib),
                'note': note, 'context': ctx, 'textblock_sha256_utf8': _sha(node.text.encode()),
                'text': _text(parsed.text_content()), 'html_body': node.text,
                'table_grid': _grid(tables[0]) if table else None}

    for name, expected in [('EntityRegistrantName', 'ENEL CHILE S.A.'),
                           ('DocumentType', '20-F'), ('DocumentPeriodEndDate', END)]:
        _, node = single(f'{{{DEI}}}{name}')
        _require(set(node.attrib) == {'contextRef', 'id'} and node.get('id') and len(node) == 0,
                 'Identidade com nil/atributo/estrutura fora do contrato')
        _require(node.text == expected, f'Documento contradiz {name}')
        _validate_context(context(node), annual=True, expected_dimensions=[])
    basis = block(IFRS, 'DisclosureOfBasisOfPreparationOfFinancialStatementsExplanatory', '2')
    _require('Enel Chile and its subsidiaries' in basis['text'] and
             'International Financial Reporting Standards (IFRS Accounting Standards)' in basis['text'],
             'Escopo consolidado/IFRS não demonstrado')
    parent = block(IFRS, 'DisclosureOfFinancialLiabilitiesExplanatory', '20/20.1')
    lease_parent = block(CUSTOM, 'DisclosureOfLeaseLiabilitiesTextBlock', '21')
    _require(parent['text'].startswith('20. OTHER FINANCIAL LIABILITIES.') and
             '20.1 Interest-bearing borrowings' in parent['text'], 'Localizador Nota 20/20.1 contraditório')
    _require(lease_parent['text'].startswith('21. LEASE LIABILITIES'), 'Localizador Nota 21 contraditório')
    other = block(CUSTOM, 'DisclosureOfOtherFinancialLiabilitiesExplanatory', '20', table=True)
    loans = block(IFRS, 'DisclosureOfDetailedInformationAboutBorrowingsExplanatory', '20.1', table=True)
    leases = block(CUSTOM, 'ScheduleOfLeaseLiabilitiesTableTextBlock', '21', table=True)
    _require(other['html_body'] in parent['html_body'] and loans['html_body'] in parent['html_body'] and
             leases['html_body'] in lease_parent['html_body'], 'Tabela fora do localizador primário declarado')
    for item, expected_rows in [(other, 8), (loans, 8), (leases, 5)]:
        g = item['table_grid']
        _require(len(g) == expected_rows and all(len(row) == 13 and all(cell is not None for cell in row)
                                               for row in g), 'Grade HTML fora do contrato')
        for col, group in [(2, 'current'), (8, 'non-current')]:
            header = g[1][col]
            _require(header['text'].lower() == group and header['expanded_column_0base'] == col
                     and header['colspan'] == 5 and header['rowspan'] == 1, 'Grupo/span de cabeçalho divergente')
            if item is leases:
                _require(g[2][col]['text'] == '12-31-2025ThUS$', 'Data/unidade de leases divergente')
            else:
                _require(g[2][col]['text'] == '12-31-2025' and g[3][col]['text'] == 'ThUS$',
                         'Data/unidade HTML divergente')
    _require(other['table_grid'][4][0]['text'] == 'Interest-bearing borrowings', 'Subtotal empréstimos ausente')
    _require([loans['table_grid'][i][0]['text'] for i in [4, 5, 6, 7]] ==
             ['Secured bank loans', 'Unsecured bank loans', 'Unsecured obligations with the public', 'Total'],
             'Detalhe de empréstimos mudou a definição')
    _require(leases['table_grid'][3][0]['text'] == 'Lease liability' and
             leases['table_grid'][4][0]['text'] == 'Total', 'Rubricas de leases divergentes')

    terms = [(CUSTOM, 'InterestBearingLoansAndBorrowingsCurrent', 'emprestimos', 'current'),
             (CUSTOM, 'InterestBearingLoansAndBorrowingsNoncurrent', 'emprestimos', 'noncurrent'),
             (IFRS, 'CurrentLeaseLiabilities', 'arrendamentos', 'current'),
             (IFRS, 'NoncurrentLeaseLiabilities', 'arrendamentos', 'noncurrent')]
    facts, excluded = [], []
    for namespace, name, group, maturity in terms:
        chosen, values = [], set()
        for ordinal, node in indexes.get(f'{{{namespace}}}{name}', []):
            ctx = context(node)
            raw_ctx = _raw_context(ctx)
            period = [(x['tag'], x['lexema']) for x in raw_ctx['period']]
            expected_dims = DIMENSIONS if group == 'emprestimos' else []
            dims = [x for x in ctx.iter() if _local(x) in {'explicitMember', 'typedMember'}]
            target_period = period == [(f'{{{XBRL}}}instant', END)]
            target_dims = all(x.tag == f'{{{XBRLDI}}}explicitMember' for x in dims) and [
                (_qname(x, x.get('dimension')), _qname(x, x.text)) for x in dims] == expected_dims
            if not (target_period and target_dims):
                excluded.append({'ordinal_xml_0base': ordinal, 'tag': node.tag,
                                 'attrs': dict(node.attrib), 'lexema': node.text, 'context': raw_ctx,
                                 'fact_sha256_serializado': _sha(etree.tostring(node)),
                                 'unit_xml_serializado': (etree.tostring(units[node.get('unitRef')]).decode()
                                                         if node.get('unitRef') in units else None),
                                 'reason': 'fora_do_periodo_ou_dimensoes_fechados'})
                continue
            selected_ctx = _validate_context(ctx, annual=False, expected_dimensions=expected_dims)
            _require(node.get('unitRef') in units, 'Unidade ausente/não recebida')
            unit = units[node.get('unitRef')]
            _require(len(unit) == 1 and unit[0].tag == f'{{{XBRL}}}measure' and
                     _qname(unit[0], unit[0].text) == f'{{{ISO}}}USD', 'Unidade não é USD monetário simples')
            _require(set(node.attrib) == {'contextRef', 'unitRef', 'decimals', 'id'} and node.get('id'),
                     'Fato com nil/scale/sign/atributo desconhecido ou id ausente')
            _require(node.get('decimals') == '-3' and len(node) == 0 and node.text is not None and
                     NUMERIC.fullmatch(node.text), 'Precisão/lexema numérico fora do contrato')
            value = Decimal(node.text)
            values.add(value)
            chosen.append({'ordinal_xml_0base': ordinal, 'tag': node.tag, 'attrs': dict(node.attrib),
                           'lexema': node.text, 'value_USD': str(value), 'context': selected_ctx,
                           'unit_xml_serializado': etree.tostring(unit).decode(),
                           'fact_sha256_serializado': _sha(etree.tostring(node))})
        _require(chosen, f'Componente obrigatório ausente: {name}')
        _require(len({x['attrs']['id'] for x in chosen}) == len(chosen), 'ID de fato selecionado duplicado')
        _require(len(values) == 1, f'Fatos duplicados conflitantes: {name}')
        facts.append({'tag': f'{{{namespace}}}{name}', 'group': group, 'maturity': maturity,
                      'semantic_key': [CIK, f'{{{namespace}}}{name}', END, 'USD',
                                       [list(pair) for pair in expected_dims]],
                      'value_USD': str(next(iter(values))), 'currency': 'USD', 'xml_scale': '1',
                      'decimals': '-3', 'evidence_label': 'fact_source_reported',
                      'sign_convention': 'lexema_positivo_sem_atributo_sign',
                      'occurrences': chosen, 'dedup': 'um_valor_por_grao_semantico_sem_somar_ocorrencias'})
    ties = []
    for i, col in enumerate([2, 8]):
        for fact, blocks, row_numbers in [(facts[i], [other, loans], [4, 7]),
                                         (facts[i + 2], [leases, leases], [3, 4])]:
            cells = [{'block_tag': b['tag'], 'block_ordinal_xml_0base': b['ordinal_xml_0base'],
                      'block_sha256_utf8': b['textblock_sha256_utf8'], 'note': b['note'],
                      'row_0base': row, 'expanded_column_0base': col,
                      'cell': b['table_grid'][row][col]} for b, row in zip(blocks, row_numbers, strict=True)]
            amounts = [_html_amount(x['cell']) for x in cells]
            _require(all(v == Fraction(fact['value_USD']) for v in amounts), 'Tie-out HTML/tag divergente')
            tie = {'tag': fact['tag'], 'cells': cells, 'html_scale': '1000',
                   'xml_scale': '1', 'currency': 'USD', 'end': END,
                   'residuals_HTML_tag_USD': [_finite_decimal(v - Fraction(fact['value_USD'])) for v in amounts]}
            fact['tieout_index'] = len(ties)
            ties.append(tie)
    totals = {name: {'value_USD': _finite_decimal(sum(
                        (Fraction(f['value_USD']) for f in facts if f['group'] == name), Fraction(0))),
                     'components': [f['tag'] for f in facts if f['group'] == name],
                     'evidence_label': 'derived_calculation', 'includes_leases': name == 'arrendamentos'}
              for name in ['emprestimos', 'arrendamentos']}
    localizers = [basis, parent, lease_parent, other, loans, leases]
    for item in localizers:
        item.pop('html_body')
    return {'schema': 'cdp.enelchile.documental/v1', 'opt_in': True,
            'data_notice': 'DADOS SIMULADOS — fixture do produtor' if simulated else 'DADOS PÚBLICOS REPORTADOS',
            'is_synthetic': simulated, 'source': dict(source), 'cik': CIK, 'issuer_id': 'CL_ENELCHILE',
            'form': '20-F', 'scope': 'Enel Chile e subsidiárias, consolidado IFRS reportado',
            'period_end': END, 'period_start': None, 'stock_not_flow': True,
            'facts': facts, 'excluded_occurrences': excluded, 'totals_separate': totals,
            'localizers': localizers, 'tieouts': ties,
            'canonical_fact_adopted': False, 'consumer_integrated': False,
            'PIT_certified': False, 'G19_closed': False, 'P0_closed': False,
            'consumer_contract_proposal': {'native_columns_known': {'entidade': CIK, 'demonstrativo': 'BP',
                'period_start': None, 'period_end': END, 'currency': 'USD', 'consolidado': True,
                'url': source.get('url'), 'received_date': source.get('received_at_utc')},
                'item_mapping_requires_review': {'emprestimos': 'divida_bruta', 'arrendamentos': 'arrendamentos'},
                'filed_date_unknown': True, 'received_date_basis': 'recepcao_observada_nao_filed',
                'version_owned_by_consumer': True, 'no_companyfacts_alias_injection': True}}


__all__ = ['extrair_enel', 'InvalidDocument']
