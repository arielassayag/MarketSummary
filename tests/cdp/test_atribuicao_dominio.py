"""DADOS SIMULADOS: domínio homogêneo sem transformação presumida."""

import json
from copy import deepcopy

import pytest
from fixture_atribuicao import endpoint

from cdp.cobertura.atribuicao_endpoints import Etapa, SessaoAtribuicao
from cdp.data.ri_captura.observado import instant


def _dominio_economico(*args):
    # A importação local permite a mesma regressão de sessão em controle v1;
    # os checks puros de domínio são exclusivos do contrato novo v2.
    from cdp.cobertura.atribuicao_endpoints import _dominio_economico as check

    return check(*args)


def pacote_simulado():
    """Metadata canônica de saída; unidade da fonte não é autorização primária."""
    p = {
        "moeda": "BRL",
        "fontes": {},
        "tabela_insumos": [],
        "historico": {},
        "bases_fluxos": {},
        "moedas_fluxos": {},
        "periodos_fluxos": {},
        "historico_bases": {},
        "historico_moedas": {},
        "historico_periodos": {},
        "historico_fontes": {},
    }
    flows = ("receita", "ebit", "lucro_liquido_controladores")
    for item in (*flows, "caixa", "divida_bruta", "patrimonio_controladores"):
        key = "t." + item
        p[key] = 10.0
        p["fontes"][key] = {
            "base_contabil": "consolidado",
            "moeda_fonte": "BRL",
            "freq_fonte": "TTM" if item in flows else "Q",
            "fim_fonte": "2026-06-30",
        }
        p["tabela_insumos"].append({"id": key, "unidade": "total:BRL"})
        if item in flows:
            p["bases_fluxos"][item] = "consolidado"
            p["moedas_fluxos"][item] = "BRL"
            p["periodos_fluxos"][item] = "TTM|2026-06-30"
        p["historico"][item] = {"2025": 9.0}
        p["historico_bases"][item] = {"2025": "consolidado"}
        p["historico_moedas"][item] = {"2025": "BRL"}
        p["historico_periodos"][item] = {"2025": "A|2025-12-31"}
        p["historico_fontes"][item] = {
            "2025": {
                "base_contabil": "consolidado",
                "moeda_fonte": "BRL",
                "freq_fonte": "A",
                "fim_fonte": "2025-12-31",
                "item_fonte": item,
                "valor_modelo": 9.0,
            }
        }
    return p


def metadata(p, item, layer, dimension, value):
    if layer == "corrente":
        source = p["fontes"]["t." + item]
        if dimension == "base":
            source["base_contabil"] = value
            if item in p["bases_fluxos"]:
                p["bases_fluxos"][item] = value
        elif dimension == "moeda_fonte":
            source["moeda_fonte"] = value
            if item in p["moedas_fluxos"]:
                p["moedas_fluxos"][item] = value
        elif dimension == "periodo":
            source["fim_fonte"] = value
            if item in p["periodos_fluxos"]:
                p["periodos_fluxos"][item] = (
                    None if value is None else source["freq_fonte"] + "|" + value
                )
        elif dimension == "unidade_modelo":
            next(row for row in p["tabela_insumos"] if row["id"] == "t." + item)["unidade"] = value
    else:
        source = p["historico_fontes"][item]["2025"]
        if dimension == "base":
            p["historico_bases"][item]["2025"] = source["base_contabil"] = value
        elif dimension == "moeda_fonte":
            p["historico_moedas"][item]["2025"] = source["moeda_fonte"] = value
        elif dimension == "periodo":
            source["fim_fonte"] = value
            p["historico_periodos"][item]["2025"] = None if value is None else "A|" + value
        elif dimension == "conceito":
            source["item_fonte"] = value


@pytest.mark.parametrize(
    "layer,item",
    [
        ("corrente", "lucro_liquido_controladores"),
        ("historico", "lucro_liquido_controladores"),
        ("corrente", "ebit"),
        ("historico", "receita"),
        ("corrente", "caixa"),
        ("historico", "patrimonio_controladores"),
    ],
)
def test_base_um_componente_fluxo_estoque_historico(layer, item):
    old = pacote_simulado()
    new = deepcopy(old)
    metadata(new, item, layer, "base", "individual")
    before = deepcopy((old, new))
    reasons, records = _dominio_economico(old, new)
    assert any(item in r and "base muda" in r for r in reasons)
    assert (old, new) == before
    assert records


@pytest.mark.parametrize(
    "layer,dimension,value",
    [
        ("corrente", "moeda_fonte", "USD"),
        ("historico", "moeda_fonte", "USD"),
        ("corrente", "unidade_modelo", "total:USD"),
        ("corrente", "periodo", "2026-03-31"),
        ("historico", "periodo", "2025-06-30"),
        ("historico", "conceito", "lucro_liquido"),
    ],
)
def test_moeda_unidade_janela_conceito_sem_transformacao(layer, dimension, value):
    old = pacote_simulado()
    new = deepcopy(old)
    metadata(new, "lucro_liquido_controladores", layer, dimension, value)
    reasons, _ = _dominio_economico(old, new)
    assert any(dimension + " muda" in r for r in reasons)


@pytest.mark.parametrize(
    "item,layer,dimension",
    [
        ("caixa", "corrente", "base"),
        ("lucro_liquido_controladores", "corrente", "base"),
        ("patrimonio_controladores", "historico", "base"),
        ("receita", "historico", "moeda_fonte"),
        ("ebit", "corrente", "periodo"),
    ],
)
def test_metadado_necessario_ausente_nao_se_inventa(item, layer, dimension):
    p = pacote_simulado()
    metadata(p, item, layer, dimension, None)
    reasons, _ = _dominio_economico(p, deepcopy(p))
    assert any(dimension + " desconhecido" in r for r in reasons)


def test_mapa_base_ou_historico_nao_substitui_fonte_estoques_incluidos():
    old = pacote_simulado()
    new = deepcopy(old)
    new["bases_fluxos"]["receita"] = "individual"
    new["historico_bases"]["patrimonio_controladores"]["2025"] = "individual"
    reasons, _ = _dominio_economico(old, new)
    assert any("mapa e fonte" in r for r in reasons)
    assert any("mapa histórico e fonte" in r for r in reasons)


def test_par_igualmente_misto_nao_e_homogeneo():
    p = pacote_simulado()
    metadata(p, "caixa", "corrente", "base", "individual")
    reasons, _ = _dominio_economico(p, deepcopy(p))
    assert any("base heterogêneo" in r for r in reasons)


def test_homogeneo_individual_e_periodos_representados_igualmente():
    p = pacote_simulado()
    for item in p["historico"]:
        metadata(p, item, "corrente", "base", "individual")
        metadata(p, item, "historico", "base", "individual")
    other = deepcopy(p)
    for item in other["periodos_fluxos"]:
        other["periodos_fluxos"][item] = "12 meses até 2026-06-30"
    assert _dominio_economico(p, other)[0] == []


def test_ausencia_numerica_nao_zero_valores_iguais_dominios_iguais():
    old = pacote_simulado()
    new = deepcopy(old)
    old["t.caixa"] = new["t.caixa"] = None
    assert _dominio_economico(old, new)[0] == []
    new["t.divida_bruta"] = None
    reasons, _ = _dominio_economico(old, new)
    assert any("t.divida_bruta: componente ausente" in r for r in reasons)
    assert new["t.divida_bruta"] is None


@pytest.mark.parametrize("selector", ["item_patrimonio", "item_lucro"])
def test_conceito_escolhido_pelo_valorador_muda_sem_transformacao(selector):
    old = pacote_simulado()
    new = deepcopy(old)
    old[selector] = "controladores"
    new[selector] = "total"
    assert any(selector in r for r in _dominio_economico(old, new)[0])


@pytest.fixture(scope="module")
def anterior(tmp_path_factory):
    return endpoint(tmp_path_factory.mktemp("dominio-anterior-DADOS-SIMULADOS")).reextrair()


@pytest.mark.parametrize(
    "changes,scope",
    [
        (
            [{"item": "lucro_liquido_controladores", "freq": "TTM", "consolidado": False}],
            "t.lucro_liquido_controladores",
        ),
        (
            [{"item": "lucro_liquido_controladores", "freq": "A", "consolidado": False}],
            "historico.lucro_liquido_controladores",
        ),
        (
            [
                {"item": "lucro_liquido_controladores", "freq": "TTM", "consolidado": False},
                {"item": "lucro_liquido_controladores", "freq": "A", "consolidado": False},
            ],
            "lucro_liquido_controladores",
        ),
        ([{"item": "divida_bruta", "consolidado": False}], "t.divida_bruta"),
        (
            [{"item": "lucro_liquido_controladores", "freq": "TTM", "consolidado": None}],
            "t.lucro_liquido_controladores",
        ),
        ([{"item": "lucro_liquido_controladores", "freq": "TTM", "currency": "USD"}], "moeda"),
    ],
)
def test_endpoints_externos_novos_reabertos_base_moeda_ausencia(anterior, tmp_path, changes, scope):
    source = endpoint(tmp_path / "novo-DADOS-SIMULADOS", novo=True, alteracoes=changes)
    new = source.reextrair()
    session = SessaoAtribuicao(anterior, new, instant(new.conhecimento_ate))
    assert session.avaliar(session.cenario(Etapa.BASE)).valor == anterior.tp_recalculado
    assert session.avaliar(session.cenario(Etapa.METODOS)).valor == new.tp_recalculado
    assert source.reextrair() == new
    result = session.avaliar(session.cenario(Etapa.ESTIMATIVAS))
    assert result.valor is None and any(scope in r for r in result.razoes)
    bridge = session.ponte()
    assert all(bridge["componentes"][step.value] is None for step in list(Etapa)[1:-1])
    assert bridge["notas"] and bridge["g7_observado"] is False
    assert json.loads(result.pacote_numerico_json)["pit_ok"] is False
