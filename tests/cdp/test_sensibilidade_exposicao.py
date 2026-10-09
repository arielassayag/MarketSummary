"""Exposição do canal, com células históricas literais; nenhum motor/MC é executado."""

import ast
import copy
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cdp.cobertura.formato import num, pp
from cdp.cobertura.modelo import Avaliador, exposicao_sensibilidade
from cdp.workflow.painel_cobertura import _sensibilidade

FIXTURES = json.loads((Path(__file__).parent / "fixtures/sensibilidade_exposicao/retratos.json").read_text())


@pytest.mark.parametrize("metodo", ["fcff_normalizado", "rim", "regressao_ev_receita", "soma_partes"])
def test_canal_commodity_identifica_consumidor(metodo):
    e = exposicao_sensibilidade("commodity", [metodo], anos_plenos=3, zero_em=5)
    assert e["colunas_aplicavel"] is (metodo == "fcff_normalizado")
    assert e["metodos_colunas"] == ([metodo] if metodo == "fcff_normalizado" else [])
    assert e["unidade_colunas"] == "p.p."
    assert "+0,20 equivale a +20 p.p." in e["formula_delta_margem"]
    assert "receita do caso-base" in e["descricao"]
    assert "ano 3" in e["perfil"] and "ano 5" in e["perfil"]


@pytest.mark.parametrize("arquetipo,metodos,esperado", [
    ("banco", ["rim", "regressao_pb_roe"], True),
    ("corporativo", ["rim"], False),
    ("corporativo", ["fcff"], True),
    ("holding", ["soma_partes"], False),
    ("imobiliario", ["rim_real"], False),
])
def test_demais_canais_identificam_consumidor(arquetipo, metodos, esperado):
    assert exposicao_sensibilidade(arquetipo, metodos)["colunas_aplicavel"] is esperado


@pytest.mark.parametrize("arquetipo,metodos,conferido", [
    ("commodity", ["futuro_desconhecido"], True),
    ("commodity", [], False),
    ("arquetipo_desconhecido", ["rim"], True),
])
def test_ausente_nao_vira_ausencia_comprovada(arquetipo, metodos, conferido):
    e = exposicao_sensibilidade(arquetipo, metodos, inventario_conferido=conferido)
    assert e["colunas_aplicavel"] is None
    assert e["ke_so_rolagem"] is None
    assert "não conferida" in e["motivo"]


def test_consumidor_conhecido_com_metodo_desconhecido_nao_apaga_canal():
    e = exposicao_sensibilidade("commodity", ["fcff_normalizado", "futuro_desconhecido"])
    assert e["colunas_aplicavel"] is None
    assert e["metodos_colunas"] == ["fcff_normalizado"]
    assert e["metodos_desconhecidos"] == ["futuro_desconhecido"]
    assert e["ke_so_rolagem"] is None


def test_nome_novo_nao_equivale_a_contrato_conhecido(monkeypatch):
    from cdp.cobertura.modelo import NOME_METODO
    monkeypatch.setitem(NOME_METODO, "metodo_novo", "Método novo")
    e = exposicao_sensibilidade("commodity", ["metodo_novo"])
    assert e["colunas_aplicavel"] is None
    assert e["metodos_desconhecidos"] == ["metodo_novo"]


@pytest.mark.parametrize("participa", [False, True])
def test_texto_real_mc_sem_executar_monte_carlo(participa):
    """Avalia somente a expressão de texto da API; não executa _cenarios ou sorteios."""
    from cdp.cobertura import modelo
    tree = ast.parse(Path(modelo.__file__).read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "add" and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "cenarios.mc"]
    assert len(calls) == 1
    expr = ast.Expression(body=calls[0].args[2])
    contexto = {"pp": pp, "num": num, "int": int, "mc": {"sigma_ke": .005, "sigma_g": .0025,
                "sigma_roe": .03, "sigma_commodity": .20, "commodity_anos_plenos": 3, "commodity_zero_em": 5},
                "s_cres": .03, "s_marg": .03, "rho": .3, "commodity": True,
                "validos": ["fcff_normalizado"] if participa else ["rim"]}
    texto = eval(compile(expr, "texto_mc", "eval"), {"__builtins__": {}}, contexto)
    assert "preço da commodity" not in texto
    if participa:
        assert "aditiva da margem EBIT 20 p.p." in texto
        assert "ano 3" in texto and "ano 5" in texto
    else:
        assert "indisponível nos métodos participantes" in texto


@pytest.mark.parametrize("metodo,esperado", [("soma_partes", True), ("regressao_ev_receita", True),
                                          ("regressao_pb_roe", True), ("rim", False), ("fcff_normalizado", False)])
def test_ke_so_rolagem_tem_contrato_do_metodo(metodo, esperado):
    e = exposicao_sensibilidade("commodity", [metodo])
    assert e["ke_so_rolagem"] is esperado
    if esperado:
        assert "V0 permanece fixo" in e["descricao_ke"]


@pytest.mark.parametrize("m", FIXTURES, ids=lambda m: m["issuer_id"])
def test_apresentacao_preserva_retrato_e_celulas(m):
    original = copy.deepcopy(m)
    out = _sensibilidade(m, True)
    s = m["sensibilidade"]
    assert m == original
    assert out["rot_linhas"] == s["ke_texto"]
    assert [[c["t"] for c in r["c"]] for r in out["celulas"]] == s["preco_alvo_texto"]
    assert [[c["u"] for c in r["c"]] for r in out["celulas"]] == s["upside_texto"]
    assert out["base"] == [2, 2]
    if m["arquetipo"] == "commodity":
        assert "Margem EBIT" in out["colunas"]
        assert out["rot_colunas"] == ["−20 p.p.", "−10 p.p.", "0 p.p.", "+10 p.p.", "+20 p.p."]
        assert "denominação de preço" in out["nota_rotulo_legado"]
        assert "configuração arquivadas" in out["aplicabilidade"]["perfil"]
    esperado = m["issuer_id"] in ("BR_VALE", "BR_ITAU")
    assert out["aplicabilidade"]["colunas_aplicavel"] is esperado


def test_apresentacao_sem_inventario_preserva_rotulo_e_nao_afirma_ausencia():
    m = copy.deepcopy(FIXTURES[0])
    del m["metodos"]
    del m["arquetipo"]
    out = _sensibilidade(m, False)
    assert out["aplicabilidade"]["colunas_aplicavel"] is None
    assert out["colunas"] == m["sensibilidade"]["colunas"]
    assert out["citavel"] is False


@pytest.mark.parametrize("m", FIXTURES, ids=lambda m: m["issuer_id"])
def test_api_grade_somente_devolve_celulas_historicas(m):
    """Instrumenta _grade: verifica contrato de chamadas; não reavalia valuation."""
    a = Avaliador.__new__(Avaliador)
    a.pac = {"arquetipo": m["arquetipo"]}
    a.moeda = m["moeda"]
    a.cc = SimpleNamespace(ke=m["custo_capital"]["ke"])
    a.metodos = {d["m"]: copy.deepcopy(d) for d in m["metodos"]}
    a.reg = SimpleNamespace(nota=lambda *args: None)
    secs = {"sensibilidade": {"ke_passos": [-.01, -.005, 0, .005, .01],
            "g_passos": [-.005, -.0025, 0, .0025, .005], "roe_passos": [-.03, -.015, 0, .015, .03],
            "commodity_passos": [-.2, -.1, 0, .1, .2]},
            "cenarios": {"monte_carlo": {"commodity_anos_plenos": 3, "commodity_zero_em": 5}}}
    a.params = SimpleNamespace(sec=lambda k: secs[k])
    chamadas = []

    def grade(linhas, colunas, fl, fc):
        chamadas.append({"linhas": linhas, "colunas": colunas,
                         "fl": [fl(x) for x in linhas], "fc": [fc(x) for x in colunas]})
        return copy.deepcopy(m["sensibilidade"]["preco_alvo"])

    a._grade = grade
    out = a._sensibilidade(m["preco_recebido"])
    assert out["preco_alvo"] == m["sensibilidade"]["preco_alvo"]
    assert chamadas[0]["linhas"] == secs["sensibilidade"]["ke_passos"]
    assert chamadas[0]["fl"] == [{"d_ke": x} for x in chamadas[0]["linhas"]]
    canal = out["aplicabilidade"]["canal_colunas"]
    assert chamadas[0]["fc"] == [{canal: x} for x in chamadas[0]["colunas"]]
    if m["arquetipo"] == "commodity":
        assert "ano 3" in out["aplicabilidade"]["perfil"]


def _renderer(tmp_path, dados):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node não disponível para a regressão do renderer")
    from cdp.workflow import painel_cobertura
    origem = Path(painel_cobertura.__file__).with_suffix(".js").read_text()
    trecho = origem.split("function sensibilidade(G) {", 1)[1].split("/* V4:", 1)[0]
    script = """
const fs = require('fs');
const G = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
function arr(x) { return Array.isArray(x) ? x : []; }
function obj(x) { return x && typeof x === 'object' ? x : {}; }
function txt(x) { return x == null ? '' : String(x); }
function each(a, f) { arr(a).forEach(f); }
function h(tag, attrs, ...children) {
  const n = {tag, attrs, children: children.flat(Infinity).filter(x => x != null)};
  n.appendChild = x => n.children.push(x); return n;
}
function block(t, s) { return h('block', {t, s}); }
function note(t) { return h('note', null, t); }
function add(n, children) { children.filter(x => x != null).forEach(x => n.appendChild(x)); }
function tabela(c, rows) { return h('tabela', {c, rows}); }
function leitura(t) { return h('leitura', null, t); }
""" + "function sensibilidade(G) {" + trecho + "\nprocess.stdout.write(JSON.stringify(sensibilidade(G)));\n"
    (tmp_path / "renderer.js").write_text(script)
    (tmp_path / "dados.json").write_text(json.dumps(dados, ensure_ascii=False))
    p = subprocess.run([node, str(tmp_path / "renderer.js"), str(tmp_path / "dados.json")],
                       check=True, capture_output=True, text=True)
    return json.loads(p.stdout)


@pytest.mark.parametrize("iid", ["AR_ADECOAGRO", "BR_BRADESPAR", "BR_VALE", "BR_ITAU"])
def test_renderer_aplicabilidade_offline(tmp_path, iid):
    m = next(m for m in FIXTURES if m["issuer_id"] == iid)
    dados = _sensibilidade(m, True)
    r = _renderer(tmp_path, dados)
    txt = json.dumps(r, ensure_ascii=False)
    if dados["aplicabilidade"]["colunas_aplicavel"] is False:
        tabelas = [x for x in r["children"] if x["tag"] == "tabela"]
        assert len(tabelas) == 1
        assert [x["alvo"] for x in tabelas[0]["attrs"]["rows"]] == [row[2] for row in m["sensibilidade"]["preco_alvo_texto"]]
        assert "cv-hm" not in txt
        assert "indisponível" in txt
    else:
        assert "cv-hm" in txt
        assert "Métodos que recebem" in txt
        if iid == "BR_VALE":
            assert "+20 p.p." in txt and "w_t é adimensional" in txt


def test_renderer_compatibilidade_sem_metadados(tmp_path):
    dados = _sensibilidade(FIXTURES[1], True)
    del dados["aplicabilidade"]
    r = _renderer(tmp_path, dados)
    assert "cv-hm" in json.dumps(r)


def test_renderer_nao_conferido_conserva_grade(tmp_path):
    m = copy.deepcopy(FIXTURES[1])
    del m["metodos"]
    dados = _sensibilidade(m, False)
    r = _renderer(tmp_path, dados)
    txt = json.dumps(r, ensure_ascii=False)
    assert "não conferida" in txt and "cv-hm" in txt
    assert "só para auditoria" in txt
