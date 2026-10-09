"""DADOS SIMULADOS: endpoint primário e cenário derivado permanecem tipos distintos."""
from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone
from pathlib import Path

import pytest
from fixture_atribuicao import FONTE, endpoint
from ri_fixture_atribuicao import BOUND

from cdp.cobertura.atribuicao_endpoints import (
    CenarioDerivado,
    Etapa,
    SessaoAtribuicao,
    _AvaliadorDerivado,
)
from cdp.cobertura.margens import margens_alinhadas
from cdp.cobertura.modelo import Avaliador, Drivers
from cdp.cobertura.motor import tp_deterministico
from cdp.cobertura.ponte import ORDEM, ponte
from cdp.data.ri_captura.configuracao import carregar_contexto_ri
from cdp.data.ri_captura.observado import instant, sha
from cdp.data.ri_captura.transporte import reabrir_insumos_ri
from cdp.data.snapshot import load_snapshot


@pytest.fixture(scope='module')
def pair(tmp_path_factory):
    path = tmp_path_factory.mktemp('endpoints-DADOS-SIMULADOS')
    a, b = endpoint(path / 'anterior'), endpoint(path / 'novo', novo=True)
    ra, rb = a.reextrair(), b.reextrair()
    return SessaoAtribuicao(ra, rb, instant(rb.conhecimento_ate))


def provider(retrato):
    source = json.loads(retrato.fonte.arquivo.read_bytes())
    md = load_snapshot(Path(source['mercado']), verify=True)
    ctxri = carregar_contexto_ri(source['ri_config'], sha256_esperado=source['ri_config_sha256'])
    p = retrato.fonte.parametros()
    f = reabrir_insumos_ri(source['transporte'], sha256_esperado=source['transporte_sha256'],
        md=md, contexto=ctxri, params=p, conhecimento_ate=instant(retrato.conhecimento_ate))
    return f, p


@pytest.mark.parametrize('etapa,retrato', [(Etapa.BASE, 'anterior'), (Etapa.METODOS, 'novo')])
def test_paridade_endpoint_numerica_publico_e_derivado(pair, etapa, retrato):
    r = getattr(pair, retrato)
    f, params = provider(r)
    p, c, rf = json.loads(r.pacote_json), json.loads(r.contexto_json), json.loads(r.rf_json)
    control = tp_deterministico(p, c, params, rf['valor'], rf['fonte'], ri_fornecedor=f,
                               conhecimento_ate=instant(r.conhecimento_ate))
    derived = pair.avaliar(pair.cenario(etapa))
    assert control == r.tp_recalculado == derived.valor
    assert derived.razoes == ()
    assert json.loads(derived.pacote_numerico_json) == p
    assert json.loads(derived.contexto_numerico_json) == c
    assert derived.natureza == 'contrafactual de atribuição; não é medição primária'


def test_hibrido_primario_recusado_derivacao_fechada_calculavel(pair):
    f, params = provider(pair.novo)
    p, c, rf, _, _ = pair._materializar(Etapa.ESTIMATIVAS)
    with pytest.raises(ValueError, match='reextração|incompatíveis|contexto'):
        Avaliador(p, c, params, rf['valor'], rf['fonte'], ri_fornecedor=f,
                  conhecimento_ate=instant(pair.novo.conhecimento_ate))
    value = pair.avaliar(pair.cenario(Etapa.ESTIMATIVAS))
    assert value.valor is not None
    assert value.valor != pair.anterior.tp_recalculado


def test_catalogos_ebit_e_historico_a3_materialmente_distintos(pair):
    a, b = json.loads(pair.anterior.pacote_json), json.loads(pair.novo.pacote_json)
    assert a['t.ebit'] == 220_000_000 and b['t.ebit'] == 290_000_000
    assert a['historico']['ebit']['2025'] == 200_000_000
    assert b['historico']['ebit']['2025'] == 260_000_000
    assert pair.anterior.parametros_sha256 != pair.novo.parametros_sha256
    assert pair.anterior.configuracao_economica_sha256 == pair.novo.configuracao_economica_sha256
    assert a['visao_resultado']['visao_sha256'] != b['visao_resultado']['visao_sha256']
    assert margens_alinhadas(a)['historico']['2025']['margem'] != margens_alinhadas(b)['historico']['2025']['margem']
    p, c, rf, proof, reasons = pair._materializar(Etapa.ESTIMATIVAS)
    assert not reasons
    for key in ('historico', 'periodos_fluxos', 'bases_fluxos', 'moedas_fluxos', 'historico_fontes',
                'historico_periodos', 'historico_moedas', 'historico_bases', 'resultado_ebitda_base',
                'visao_resultado', 'resultado_reportado', 'resultado_evidencias'):
        assert p.get(key) == b.get(key)
        assert proof['campos'][key] == 'novo'
    for key in set(a) | set(b):
        if key.startswith('t.'):
            assert p.get(key) == b.get(key)
            assert proof['campos'][key] == 'novo'
    assert c == json.loads(pair.anterior.contexto_json)
    assert proof['contexto'] == 'anterior' and proof['medicao_primaria'] is False
    assert proof['params_endpoints'] == [pair.anterior.parametros_sha256, pair.novo.parametros_sha256]
    assert proof['campos']['fontes'] == 'derivado_por_campo'
    source_row = next(r for r in b['tabela_insumos'] if r['id']=='t.ebit')
    scenario_row = next(r for r in p['tabela_insumos'] if r['id']=='t.ebit')
    assert source_row == scenario_row and proof['tabela_insumos']['t.ebit'] == 'novo'
    av = _AvaliadorDerivado(pair, Etapa.ESTIMATIVAS, p, c, rf)
    assert av.margem_fluxos == margens_alinhadas(b)
    po, co, ro, _, _ = pair._materializar(Etapa.BASE)
    oldav = _AvaliadorDerivado(pair, Etapa.BASE, po, co, ro)
    assert float(oldav._valor_metodo('fcff', Drivers())) != float(av._valor_metodo('fcff', Drivers()))
    with pytest.raises(ValueError, match='virtual'):
        av.avaliar()


def test_pl_nci_regime_elegibilidade_preservados(pair):
    for e, r in ((Etapa.BASE, pair.anterior), (Etapa.METODOS, pair.novo)):
        f, par = provider(r)
        p, c, rf, _, _ = pair._materializar(e)
        primary = Avaliador(p, c, par, rf['valor'], rf['fonte'], ri_fornecedor=f,
                            conhecimento_ate=instant(r.conhecimento_ate))
        derived = _AvaliadorDerivado(pair, e, p, c, rf)
        assert primary.k_pl == derived.k_pl == 't.patrimonio_controladores'
        assert primary._participacao_controladores() == derived._participacao_controladores()
        assert primary._requisitos('fcff') == derived._requisitos('fcff')
        assert p['ri_observada']['selecao'] and p['pit_ok'] is False


def test_receita_plano_fechado_e_tipos(pair):
    with pytest.raises(ValueError, match='etapa'):
        pair.cenario('estimativas')
    with pytest.raises(ValueError, match='sessão'):
        pair.avaliar(CenarioDerivado(pair, 'estimativas'))
    other = SessaoAtribuicao(pair.anterior, pair.novo, pair.conhecimento_ate)
    with pytest.raises(ValueError, match='sessão'):
        pair.avaliar(other.cenario(Etapa.BASE))
    p, c, rf, _, _ = pair._materializar(Etapa.ESTIMATIVAS)
    p['historico_fontes']['ebit']['2025']['valor_modelo'] = 999
    with pytest.raises(ValueError, match='receita'):
        _AvaliadorDerivado(pair, Etapa.ESTIMATIVAS, p, c, rf)


def test_copia_profunda_ordem_resolucao_e_cache_immutavel(pair):
    before = (pair.anterior, pair.novo)
    ordered = {e: pair.avaliar(pair.cenario(e)) for e in Etapa}
    # Modificar cópias públicas não altera o cache, o segundo endpoint ou o cenário seguinte.
    p, c, _, _, _ = pair._materializar(Etapa.ESTIMATIVAS)
    p['historico']['ebit']['2025'] = None
    c['fundamentos'].clear()
    reversed_ = {e: pair.avaliar(pair.cenario(e)) for e in reversed(list(Etapa))}
    assert ordered == reversed_
    assert (pair.anterior, pair.novo) == before
    assert pair.anterior.fonte.reextrair() == before[0]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        pair.anterior.fonte._retrato = None
    with pytest.raises((FrozenInstanceError, AttributeError)):
        pair.novo.pacote_json = '{}'


@pytest.mark.parametrize('offset,aceita', [(-1,False), (0,True), (1,True)])
def test_corte_sessao_anterior_exato_posterior(pair, offset, aceita):
    cut = pair.conhecimento_ate + timedelta(microseconds=offset)
    if aceita:
        sess = SessaoAtribuicao(pair.anterior, pair.novo, cut)
        assert sess.avaliar(sess.cenario(Etapa.METODOS)).valor == pair.novo.tp_recalculado
    else:
        with pytest.raises(ValueError, match='após o corte'):
            SessaoAtribuicao(pair.anterior, pair.novo, cut)


def test_instante_equivalente_e_ingenuo(pair):
    equivalent = pair.conhecimento_ate.astimezone(timezone(timedelta(hours=-3)))
    s = SessaoAtribuicao(pair.anterior, pair.novo, equivalent)
    assert s.avaliar(s.cenario(Etapa.PARAMETROS)) == pair.avaliar(pair.cenario(Etapa.PARAMETROS))
    with pytest.raises(ValueError):
        SessaoAtribuicao(pair.anterior, pair.novo, pair.conhecimento_ate.replace(tzinfo=None))


def test_identidade_e_corte_endpoints_revalidados(pair):
    with pytest.raises(ValueError, match='reextração'):
        SessaoAtribuicao(replace(pair.anterior, issuer_id='OUTRO'), pair.novo, pair.conhecimento_ate)
    with pytest.raises(ValueError, match='reextração'):
        SessaoAtribuicao(pair.anterior, replace(pair.novo, conhecimento_ate=BOUND.isoformat()), pair.conhecimento_ate)
    with pytest.raises(ValueError, match='reextração'):
        SessaoAtribuicao(pair.anterior, replace(pair.novo, contexto_json='{}'), pair.conhecimento_ate)
    with pytest.raises(ValueError, match='ordem temporal'):
        SessaoAtribuicao(pair.novo, pair.anterior, pair.conhecimento_ate)


def test_config_economica_distinta_ausencia_razao_preserva_endpoints(pair, tmp_path):
    src = endpoint(tmp_path / 'regra-diversa', novo=True, config_diversa=True)
    new = src.reextrair()
    s = SessaoAtribuicao(pair.anterior, new, instant(new.conhecimento_ate))
    r = s.avaliar(s.cenario(Etapa.PARAMETROS))
    assert r.valor is None and any('regra econômica' in x for x in r.razoes)
    assert s.avaliar(s.cenario(Etapa.BASE)).valor == pair.anterior.tp_recalculado
    assert s.avaliar(s.cenario(Etapa.METODOS)).valor == new.tp_recalculado
    out = s.ponte()
    assert all(out['componentes'][e] is None for e in ORDEM[:-1])
    assert out['notas'] and out['g7_observado'] is False


def test_dados_ausentes_nao_zero_eps_e_receita(pair, tmp_path):
    source = endpoint(tmp_path / 'ausencias', novo=True, receita_ausente=True, faltas=True)
    new = source.reextrair()
    s = SessaoAtribuicao(pair.anterior, new, instant(new.conhecimento_ate))
    r = s.avaliar(s.cenario(Etapa.ESTIMATIVAS))
    p = json.loads(r.pacote_numerico_json)
    assert p['eps_fy1'] is None and p['t.receita'] is None
    assert margens_alinhadas(p)['corrente']['margem'] is None
    assert margens_alinhadas(p)['corrente']['motivos']
    av = _AvaliadorDerivado(s, Etapa.ESTIMATIVAS, *s._materializar(Etapa.ESTIMATIVAS)[:3])
    assert av._requisitos('fcff') is not None
    f, params = provider(new)
    q, ctx, rf = json.loads(new.pacote_json), json.loads(new.contexto_json), json.loads(new.rf_json)
    primary = Avaliador(q, ctx, params, rf['valor'], rf['fonte'], ri_fornecedor=f, conhecimento_ate=instant(new.conhecimento_ate))
    # O núcleo pode derivar EPS de TTM por sua regra existente. A ausência do
    # consenso continua intacta; não inventamos um bloqueio metodológico adicional.
    assert av.eps1 == primary.eps1
    assert av._requisitos('multiplo_justificado') == primary._requisitos('multiplo_justificado')


def test_endpoint_sem_preco_nao_inventa_alvo_ou_g7(pair, tmp_path):
    new = endpoint(tmp_path / 'sem-preco', novo=True, sem_preco=True).reextrair()
    assert new.tp_recalculado is None
    s = SessaoAtribuicao(pair.anterior, new, instant(new.conhecimento_ate))
    r = s.avaliar(s.cenario(Etapa.METODOS))
    assert r.valor is None and r.razoes
    out = s.ponte()
    assert out['componentes'] is None and out['g7_observado'] is False


def test_soma_residuo_formula_literal_e_nao_emite_g7(pair):
    out = pair.ponte()
    assert list(out['componentes']) == [*ORDEM, 'residuo']
    stages = [pair.avaliar(pair.cenario(e)).valor for e in Etapa]
    iterator = iter(stages)
    a, b = pair.anterior, pair.novo
    reference = ponte(a.tp_recalculado, json.loads(a.pacote_json), json.loads(b.pacote_json),
        json.loads(a.contexto_json), json.loads(b.contexto_json), json.loads(a.rf_json)['valor'],
        json.loads(b.rf_json)['valor'], b.tp_recalculado, lambda p,c,r:next(iterator))
    for key in reference:
        assert out[key] == reference[key]
    assert sum(v for v in out['componentes'].values() if v is not None) + out['alvo_anterior'] == pytest.approx(out['alvo_novo'], abs=.001)
    assert out['g7_observado'] is False and out['alvo_anterior_publicado'] is False
    assert not any('G7' == k for k in out)
    assert out['componentes']['estimativas'] != 0


def test_cache_revalida_backing_bytes_antes_de_consumir(pair, tmp_path):
    source = endpoint(tmp_path / 'backing')
    r = source.reextrair()
    spec = json.loads(source.arquivo.read_bytes())
    # Negativo material pedido: uma dependência deixa de ser a fonte previamente selada.
    path = Path(spec['resultado_documentos'][next(iter(spec['resultado_documentos']))]['path'])
    before = path.read_bytes()
    path.write_bytes(before + b'\n')
    try:
        with pytest.raises(ValueError, match='dependência externa mudou'):
            source.reextrair()
        with pytest.raises(ValueError, match='dependência externa mudou'):
            SessaoAtribuicao(pair.anterior, r, pair.conhecimento_ate)
    finally:
        path.write_bytes(before)
    assert source.reextrair() == r


def _dump_ast_portatil(node):
    """Preserva o AST de referência, omitindo campos opcionais vazios em 3.12/3.13."""
    if isinstance(node, ast.AST):
        fields = []
        for name, value in ast.iter_fields(node):
            if value is None and getattr(type(node), name, ...) is None:
                continue
            if (value is None or value == []) and not isinstance(node, (ast.Constant, ast.MatchSingleton)):
                continue
            fields.append(f'{name}={_dump_ast_portatil(value)}')
        return f'{type(node).__name__}({", ".join(fields)})'
    if isinstance(node, list):
        return f'[{", ".join(_dump_ast_portatil(value) for value in node)}]'
    return repr(node)


@pytest.mark.parametrize('left,right', [
    ('x = a + b', 'x = a - b'),
    ('if x: raise ValueError()', 'if not x: raise ValueError()'),
    ('f(x=1)', 'f()'),
    ('x = "keywords=[]"', 'x = ""'),
    ('x = None', 'x = 0'),
    ('x = None', 'x = False'),
    ('f(a,b)', 'f(b,a)'),
])
def test_ast_portatil_preserva_diferencas_semanticas(left, right):
    assert _dump_ast_portatil(ast.parse(left)) != _dump_ast_portatil(ast.parse(right))


def test_ast_numerico_guardas_e_ponte_literais():
    expected = json.loads((FONTE / 'tests/fixtures/cdp/atribuicao/AST_ORIGINAL.json').read_text())
    def dump(n):
        return _dump_ast_portatil(n)
    model = ast.parse((FONTE / 'src/cdp/cobertura/modelo.py').read_text())
    cl = next(n for n in model.body if isinstance(n,ast.ClassDef) and n.name=='Avaliador')
    methods = {n.name:n for n in cl.body if isinstance(n,ast.FunctionDef)}
    assert [dump(n) for n in methods['__init__'].body[:4]] == expected['modelo_guardas']
    assert [dump(n) for n in methods['_inicializar_numerico'].body] == expected['modelo_numerico']
    methods['__init__'].body = methods['__init__'].body[:4] + methods['_inicializar_numerico'].body
    cl.body.remove(methods['_inicializar_numerico'])
    # Pin completo da versão de apresentação revista. A referência numérica original
    # continua imutável e é conferida acima; motor e ponte mantêm seus pins originais.
    presentation = json.loads((FONTE / 'tests/fixtures/cdp/atribuicao/AST_APRESENTACAO_SENSIBILIDADE.json').read_text())
    assert sha((FONTE / 'tests/fixtures/cdp/atribuicao/AST_ORIGINAL.json').read_bytes()) == presentation['ast_original_sha256']
    assert sha(dump(model).encode()) == presentation['modelo_completo_sha256']
    motor = ast.parse((FONTE / 'src/cdp/cobertura/motor.py').read_text())
    functions = {n.name:n for n in motor.body if isinstance(n,ast.FunctionDef)}
    assert [dump(n) for n in functions['tp_deterministico'].body[:2]] == expected['motor_guardas']
    assert [dump(n) for n in functions['_tp_do_avaliador'].body] == expected['motor_numerico']
    functions['tp_deterministico'].body = functions['tp_deterministico'].body[:2] + functions['_tp_do_avaliador'].body
    motor.body.remove(functions['_tp_do_avaliador'])
    assert dump(motor) == expected['motor_completo']
    assert sha((FONTE / 'src/cdp/cobertura/ponte.py').read_bytes()) == expected['ponte_sha256']


def test_ebit_negativo_preservado_sem_abs_ou_zero(pair, tmp_path):
    r = endpoint(tmp_path / 'ebit-negativo', ebit_negativo=True).reextrair()
    s = SessaoAtribuicao(r, r, instant(r.conhecimento_ate))
    value = s.avaliar(s.cenario(Etapa.BASE))
    p = json.loads(value.pacote_numerico_json)
    assert p['t.ebit'] == -20_000_000
    assert p['historico']['ebit']['2025'] == -40_000_000
    assert margens_alinhadas(p)['corrente']['margem'] < 0
    assert value.valor == r.tp_recalculado


def test_inventario_de_dependencias_incompleto_nao_autoriza_cache(pair, tmp_path):
    from cdp.cobertura.atribuicao_endpoints import FonteEndpoint
    from cdp.data.ri_captura.adapter import texto
    spec = json.loads(pair.anterior.fonte.arquivo.read_bytes())
    spec['dependencias'].clear()
    path = tmp_path / 'inventario-incompleto.json'
    path.write_text(texto(spec))
    src = FonteEndpoint(path, sha(path.read_bytes()))
    with pytest.raises(ValueError, match='fechamento de dependências'):
        src.reextrair()


def test_campo_documental_desconhecido_recusado(pair, tmp_path):
    from cdp.cobertura.atribuicao_endpoints import reextrair_resultado
    spec = json.loads(pair.novo.fonte.arquivo.read_bytes())
    structure = json.loads(Path(spec['resultado_catalogo']).read_bytes())
    structure['documentos'][0]['parametro_valoracao_desconhecido'] = 999
    path = tmp_path / 'catalogo-desconhecido.json'
    path.write_text(json.dumps(structure))
    spec['resultado_catalogo'] = str(path)
    with pytest.raises(ValueError, match='campo documental desconhecido'):
        reextrair_resultado(spec, pair.conhecimento_ate)


def test_conversao_distinta_fora_do_dominio_sem_inventar_efeito_fx(tmp_path):
    a = endpoint(tmp_path / 'cotacao-usd-antiga', moeda_linha_usd=True).reextrair()
    b = endpoint(tmp_path / 'cotacao-usd-nova', novo=True, moeda_linha_usd=True, fx_distinto=True).reextrair()
    assert json.loads(a.pacote_json)['fator_moeda'] != json.loads(b.pacote_json)['fator_moeda']
    sess = SessaoAtribuicao(a,b,instant(b.conhecimento_ate))
    r = sess.avaliar(sess.cenario(Etapa.CAMBIO))
    assert r.valor is None and any('fator_moeda' in x for x in r.razoes)
    assert sess.avaliar(sess.cenario(Etapa.BASE)).valor == a.tp_recalculado
    assert sess.avaliar(sess.cenario(Etapa.METODOS)).valor == b.tp_recalculado
