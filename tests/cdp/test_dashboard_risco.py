"""Apresentação pura: fixtures DADOS SIMULADOS, sem book, modelo ou getter."""
import copy
import json
import re
from html.parser import HTMLParser

import pytest

from cdp.workflow.dashboard_risco import construir_dashboard_risco, renderizar_dashboard_risco


@pytest.mark.parametrize("encoded", [
    {"_colunas": {"factor": ["market"], "share": [-.02]}, "_n": 1},
    {"_n": 15},
    {"_rep": {"v": ["market"], "n": [1]}},
    {"_partes": ["Dados", " recebidos"]},
    {"_igual": "ex_ante"},
])
def test_codificacao_compactada_recusada_recursivamente_antes_de_numero(payload, encoded, monkeypatch):
    from cdp.workflow import dashboard_risco as dr

    def forbidden(value):
        pytest.fail("A conversão numérica não pode preceder a recusa do transporte compactado.")

    payload["risk"]["ex_ante"]["metadata_aninhada"] = [{"origem": encoded}]
    before = copy.deepcopy(payload)
    monkeypatch.setattr(dr, "_num", forbidden)
    with pytest.raises(ValueError, match="Payload compactado"):
        construir_dashboard_risco(payload)
    assert payload == before


@pytest.fixture
def payload():
    """Declaração de teste de apresentação; nenhuma qualificação financeira ou PIT."""
    proposal_risk = {"ex_ante_vol": .07, "gross": .6, "net": -.2, "beta": -.1,
        "var_1d_99": .009, "es_1d_99": .012, "factor_risk_share": .08,
        "specific_vol": .065, "factor_contributions": [{"factor": "market", "share": -.02},
                                                     {"factor": "country:BR", "share": .10}],
        "top_risk_contributors": [{"issuer_id": "A", "share": .6}, {"issuer_id": "B", "share": .4}],
        "stress_tests": [{"scenario": "Choque de teste", "pnl": -.03}],
        "exposures": [{"group": "country", "name": "BR", "net": .2, "gross": .2, "long": .2,
                       "short": 0, "limit": .3, "status": "ok"},
                      {"group": "country", "name": "MX", "net": -.4, "gross": .4, "long": 0,
                       "short": -.4, "limit": .3, "status": "excesso"},
                      {"group": "sector", "name": "Finance", "net": -.2, "gross": .6},
                      {"group": "style", "name": "value", "net": -1.1, "measure": "z × NAV"}]}
    proposal_positions = [
        {"issuer_id": "A", "name": "Companhia A", "execution_ticker": "A3", "side": "LONG",
         "weight": .2, "country": "BR", "sector": "Finance", "notional_usd": 200000,
         "risk_contribution": .6, "days_to_liquidate": 1, "borrow_fee_annual": None},
        {"issuer_id": "B", "name": "Companhia B", "execution_ticker": "B1", "side": "SHORT",
         "weight": -.4, "country": "MX", "sector": "Finance", "notional_usd": -400000,
         "risk_contribution": .4, "days_to_liquidate": 2, "borrow_fee_annual": .05}]
    return {"meta": {"is_synthetic": True, "data_notice": "DADOS SIMULADOS — apresentação",
             "generated_at": "2026-10-10T20:00:00Z", "data_hash": "retrato-teste", "config_hash": "cfg-atual",
             "rotulos": {"fatores": {"market": "Mercado", "country:BR": "Brasil", "style:value": "Valor"}}},
        "risk": {"executed": True, "live_week": "2026-10-09", "as_of_date": "2026-10-09",
                 "basis_note": "Diário de 09/10; stress ex-ante da decisão.", "ex_ante": proposal_risk,
                 "daily": {"ex_ante_vol": .045, "gross": .5, "net": -.1, "beta": -.03,
                           "exposures": [{"group": "country", "name": "MX", "net": -.3, "gross": .3}]},
                 "limit_checks": [{"id": "net", "label": "Exposição líquida", "basis": "diário",
                     "value": -.1, "limit": .01, "unit": "pct", "status": "alerta", "severity": "HARD",
                     "utilization": 10}, {"id": "gross_min", "label": "Bruta mínima", "basis": "diário",
                     "value": .5, "limit": .8, "unit": "pct", "status": "info", "floor": True,
                     "headroom": -.3, "shortfall": .3, "utilization": None}],
                 "liquidity_by_side": {"LONG": {"max_days": 1, "limit": 3, "n": 1, "n_missing": 0,
                                               "participation": .2},
                                       "SHORT": {"max_days": 2, "limit": 2, "n": 1, "n_missing": 0,
                                                 "participation": .15},
                                       "liquid_3d": .95, "liquid_5d": 1, "n_missing_adtv": 0,
                                       "buckets": [{"bucket": "1d", "gross": .2}]}},
        "latest_day": {"date": "2026-10-09", "live_book_week": "2026-10-09", "record_hash": "registro-teste",
                       "nav_end": 1000000, "positions": [
                           {"issuer_id": "A", "name": "Companhia A", "ticker": "A3", "weight": .2,
                            "side": "LONG", "country": "BR", "market_value_usd": 200000},
                           {"issuer_id": "B", "name": "Companhia B", "ticker": "B1", "weight": -.3,
                            "side": "SHORT", "country": "MX", "market_value_usd": -300000}]},
        "weeks": [{"week": "2026-10-09", "executed": True, "stage_label": "Efetivada", "proposal": {
            "week": "2026-10-09", "created_at": "2026-10-09T13:00:00Z", "nav_usd": 1000000,
            "proposal_id": "proposta-teste", "snapshot_hash": "snapshot-original", "config_hash": "cfg-proposta",
            "positions": proposal_positions, "risk": proposal_risk}}],
        "modelo": {"semana": "2026-10-09", "risco": {"grupos": [
            {"grupo": "mercado", "rotulo": "Mercado", "decisao": -.02, "base": -.01},
            {"grupo": "especifico", "rotulo": "Específico", "decisao": .92, "base": .90}],
            "parametros": [{"rotulo": "Data do modelo", "texto": "08/10/2026"}],
            "fatores": [{"grupo": "Mercado", "n": 1, "texto": "Mercado"}]}}}


def test_quadros_separados_reconciliacao_e_fontes_proprias(payload):
    before = copy.deepcopy(payload)
    d = construir_dashboard_risco(payload)
    daily, proposal = d["views"]
    assert daily["executed"] and proposal["executed"]
    assert daily["reconciliation"]["agrees"] is True
    assert proposal["reconciliation"]["agrees"] is True
    assert daily["kpis"][0]["value"] == .045
    assert proposal["kpis"][0]["value"] == .07
    assert {p["issuer_id"]: p["weight"] for p in daily["positions"]} == {"A": .2, "B": -.3}
    assert {p["issuer_id"]: p["weight"] for p in proposal["positions"]} == {"A": .2, "B": -.4}
    assert daily["cut"] == "2026-10-09"
    assert proposal["cut"] == "2026-10-09T13:00:00Z"
    assert d["config_hash_panel"] == "cfg-atual" and proposal["config_hash"] == "cfg-proposta"
    assert payload == before
    json.dumps(d, allow_nan=False)


@pytest.mark.parametrize("origin", ["own", "same_week_fallback"])
def test_origem_real_do_risco_e_posicoes_separada_sem_mudar_valores(payload, origin):
    baseline = construir_dashboard_risco(payload)["views"][1]
    if origin == "same_week_fallback":
        del payload["weeks"][0]["proposal"]["risk"]
    before = copy.deepcopy(payload)
    d = construir_dashboard_risco(payload)
    view = d["views"][1]
    risk_source = "risk.ex_ante" if origin == "same_week_fallback" else "weeks[].proposal.risk"
    assert view["position_source"] == view["source"] == "weeks[].proposal"
    assert view["position_field_source"] == "weeks[].proposal.positions"
    assert view["risk_source"] == risk_source
    for field in ("positions", "kpis", "exposures", "factor_contributions", "stress",
                  "top_position_risk", "risk_groups", "reconciliation", "nav_usd", "cut", "week"):
        assert view[field] == baseline[field]
    fields = {"exposures": "exposures", "factor_contributions": "factor_contributions",
              "stress": "stress_tests", "top_position_risk": "top_risk_contributors"}
    html = renderizar_dashboard_risco(d)
    for key, path in fields.items():
        expected = risk_source + "." + path
        assert view["risk_field_sources"][key] == expected
        assert f"<code>{expected}</code>" in html
        assert f"<code>weeks[].proposal.{path}</code>" not in html
    assert "<code>weeks[].proposal.positions</code>" in html
    assert payload == before


@pytest.mark.parametrize("origin", ["risk_daily", "latest_day_risk", "absent"])
def test_origem_diaria_real_e_ausencia_sem_caminhos_inventados(payload, origin):
    baseline = construir_dashboard_risco(payload)["views"][0]
    if origin != "risk_daily":
        daily = payload["risk"].pop("daily")
        if origin == "latest_day_risk":
            payload["latest_day"]["risk"] = daily
    d = construir_dashboard_risco(payload)
    view = d["views"][0]
    expected = {"risk_daily": "risk.daily", "latest_day_risk": "latest_day.risk", "absent": None}[origin]
    assert view["position_source"] == "latest_day" and view["position_field_source"] == "latest_day.positions"
    assert view["risk_source"] == expected
    assert view["risk_field_sources"]["stress"] is None
    assert view["risk_field_sources"]["factor_contributions"] is None
    assert view["risk_field_sources"]["top_position_risk"] is None
    html = renderizar_dashboard_risco(d)
    assert "<code>latest_day.positions</code>" in html
    if expected:
        assert view["kpis"] == baseline["kpis"] and view["exposures"] == baseline["exposures"]
        assert view["risk_field_sources"]["exposures"] == expected + ".exposures"
        assert f"<code>{expected}.exposures</code>" in html
    else:
        assert all(k["value"] is None for k in view["kpis"])
        assert all(path is None for path in view["risk_field_sources"].values())
    assert "<code>risk.daily.stress_tests</code>" not in html
    assert "<code>risk.daily.factor_contributions</code>" not in html


def test_ausencias_nao_sao_completadas_por_proposta(payload):
    d = construir_dashboard_risco(payload)
    daily, proposal = d["views"]
    assert daily["kpis"][4]["value"] is None and daily["kpis"][4]["display"] == "n/d"
    assert proposal["kpis"][4]["value"] == .009
    assert daily["factor_contributions"] == daily["top_position_risk"] == daily["stress"] == []
    assert daily["positions"][0]["risk_share"] is None


def test_payload_vazio_preserva_indisponibilidade():
    d = construir_dashboard_risco({})
    for v in d["views"]:
        assert not v["available"] and not v["executed"]
        assert not v["positions_known"] and v["reconciliation"]["net_from_positions"] is None
        assert all(k["value"] is None and k["display"] == "n/d" for k in v["kpis"])
    html = renderizar_dashboard_risco(d)
    assert "Registro diário indisponível" in html and "n/d" in html
    assert "0,00%" not in html


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf"), True, False, "0.5"])
def test_numeros_ausentes_nao_finitos_ou_booleans_nao_viram_zero(payload, value):
    payload["risk"]["daily"]["beta"] = value
    payload["risk"]["limit_checks"][0]["value"] = value
    d = construir_dashboard_risco(payload)
    assert d["views"][0]["kpis"][3]["display"] == "n/d"
    assert d["limits"][0]["value_display"] == "n/d"
    json.dumps(d, allow_nan=False)


def test_zero_observado_e_carteira_vazia_legitima(payload):
    payload["latest_day"]["positions"] = []
    payload["risk"]["daily"].update(net=0, gross=0, beta=0)
    d = construir_dashboard_risco(payload)
    assert d["views"][0]["reconciliation"]["agrees"] is True
    assert d["views"][0]["kpis"][2]["display"] == "0,00%"
    assert "Nenhuma posição no retrato recebido" in renderizar_dashboard_risco(d)


def test_sinais_e_dominios_css_comuns_sem_abs_no_valor(payload):
    d = construir_dashboard_risco(payload)
    country = d["views"][1]["exposures"]["country"]
    positive, negative = country
    assert positive["value"] == .2 and negative["value"] == -.4
    assert positive["bar_left"] == "50.000%" and positive["bar_width"] == "23.000%"
    assert negative["bar_left"] == "4.000%" and negative["bar_width"] == "46.000%"
    assert negative["sign"] == "negativo" and negative["display"] == "-40,00%"
    factors = d["views"][1]["factor_contributions"]
    assert next(r for r in factors if r["key"] == "market")["display"] == "-2,00%"
    assert d["views"][1]["exposures"]["style"][0]["display"] == "-1,10"


def test_risco_por_grupo_usa_modelo_mesma_semana(payload):
    d = construir_dashboard_risco(payload)
    assert d["views"][1]["risk_groups"]["decisao"][0]["value"] == -.02
    assert d["views"][1]["model_parameters"][0]["text"] == "08/10/2026"
    assert d["views"][1]["model_week"] == "2026-10-09"
    payload["modelo"]["semana"] = "2026-10-02"
    d = construir_dashboard_risco(payload)
    assert d["views"][1]["risk_groups"] == {"decisao": [], "base": []}
    assert d["views"][1]["model_parameters"] == []
    assert d["views"][1]["model_week"] is None


def test_proposta_mais_recente_nao_troca_diario_nem_modelo(payload):
    new = copy.deepcopy(payload["weeks"][0])
    new.update(week="2026-10-16", executed=False)
    new["proposal"].update(week="2026-10-16", created_at="2026-10-16T13:00:00Z")
    new["proposal"]["risk"]["ex_ante_vol"] = .09
    payload["weeks"].append(new)
    d = construir_dashboard_risco(payload)
    assert d["views"][0]["week"] == "2026-10-09" and d["views"][0]["kpis"][0]["value"] == .045
    assert d["views"][1]["week"] == "2026-10-16" and not d["views"][1]["executed"]
    assert d["views"][1]["kpis"][0]["value"] == .09
    assert d["views"][1]["risk_source"] == "weeks[].proposal.risk"
    assert d["views"][1]["risk_groups"] == {"decisao": [], "base": []}
    assert d["limit_week"] == "2026-10-09"
    del new["proposal"]["risk"]
    d = construir_dashboard_risco(payload)
    assert d["views"][1]["risk_source"] is None
    assert all(k["value"] is None for k in d["views"][1]["kpis"])


@pytest.mark.parametrize("change", ["executed", "week", "no_record"])
def test_efetivacao_nao_inferida_de_aprovacao_ou_posicoes(payload, change):
    if change == "executed":
        payload["risk"]["executed"] = False
    elif change == "week":
        payload["latest_day"]["live_book_week"] = "2026-10-02"
    else:
        payload["latest_day"] = None
    payload["weeks"][0]["decision"] = {"decision": "APPROVE"}
    assert construir_dashboard_risco(payload)["views"][0]["executed"] is False


def test_divergencias_sao_visiveis_sem_reparar_risco_ou_ponta(payload):
    payload["risk"]["daily"]["net"] = .3
    payload["latest_day"]["positions"][1]["side"] = "LONG"
    d = construir_dashboard_risco(payload)
    assert d["views"][0]["kpis"][2]["value"] == .3
    assert next(p for p in d["views"][0]["positions"] if p["issuer_id"] == "B")["weight"] == -.3
    assert len(d["warnings"]) == 2
    html = renderizar_dashboard_risco(d)
    assert "soma dos pesos difere" in html and "ponta declarada diverge" in html


def test_pisos_nao_exibem_utilizacao_falsa_e_liquidez_usa_chaves_nativas(payload):
    d = construir_dashboard_risco(payload)
    assert d["limits"][1]["floor"] and d["limits"][1]["utilization"] is None
    assert set(d["liquidity"]) == {"LONG", "SHORT"}
    html = renderizar_dashboard_risco(d)
    assert "Piso · distância -30,00%" in html
    assert "3 dias 95,00%; 5 dias 100,00%" in html
    assert "Posições sem ADTV: 0" in html
    assert '<th scope="col">Severidade</th>' in html
    assert '<th scope="col">Gate</th>' not in html


def test_extras_ja_recebidos_decomposicao_e_cargas_sem_chamar_modelo(payload):
    r = payload["risk"]["daily"]
    r["risk_decomposition"] = {"by_group": {"market": -.1, "specific": 1.1},
                               "by_factor": {"market": -.1}}
    r["factor_exposures"] = {"market": -.03}
    d = construir_dashboard_risco(payload)
    daily = d["views"][0]
    assert daily["factor_source"] == "risk_decomposition.by_factor"
    assert daily["direct_risk_groups"][0]["value"] == 1.1
    assert daily["factor_exposures"][0]["display"] == "-0,03"
    assert daily["factor_exposures"][0]["measure"] == "unidade n/d"
    assert 'risk_decomposition.by_group' in renderizar_dashboard_risco(d)


def test_cargas_fatoriais_conservam_unidades_rotulos_e_dominios_separados(payload):
    payload["risk"]["daily"]["factor_exposures"] = [
        {"factor": "market", "value": -.03, "measure": "Σ w·β"},
        {"factor": "style:value", "value": 2, "unit": "z × NAV"}]
    d = construir_dashboard_risco(payload)
    rows = {row["key"]: row for row in d["views"][0]["factor_exposures"]}
    assert rows["market"]["label"] == "Mercado"
    assert rows["market"]["measure"] == "Σ w·β" and rows["market"]["display"] == "-0,03"
    assert rows["style:value"]["measure"] == "z × NAV" and rows["style:value"]["display"] == "+2,00"
    assert rows["market"]["domain_abs"] == .03 and rows["style:value"]["domain_abs"] == 2
    html = renderizar_dashboard_risco(d)
    assert 'Exposições por fator · Σ w·β' in html and 'Exposições por fator · z × NAV' in html


@pytest.mark.parametrize("key", ["name", "sector", "ticker"])
def test_escaping_no_texto_das_posicoes(payload, key):
    payload["latest_day"]["positions"][0][key] = '<img src=x onerror="alert(1)"><script>x</script>'
    html = renderizar_dashboard_risco(construir_dashboard_risco(payload))
    assert '<img src=x' not in html and '<script>x' not in html
    assert '&lt;img' in html and '&lt;script&gt;' in html


def test_escaping_cortes_fontes_nomes_fatores_e_hashes(payload):
    evil = '"><svg onload=alert(1)>'
    payload["meta"]["data_notice"] = payload["meta"]["data_hash"] = evil
    payload["meta"]["rotulos"]["fatores"]["market"] = evil
    payload["latest_day"]["date"] = evil
    html = renderizar_dashboard_risco(construir_dashboard_risco(payload))
    assert '<svg' not in html and '&lt;svg' in html


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = []
        self.hrefs = []
        self.tables = 0
        self.captions = 0
        self.headings = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(attributes["id"])
        if tag == "a":
            self.hrefs.append(attributes.get("href"))
        if tag == "table":
            self.tables += 1
        if tag == "caption":
            self.captions += 1
        if tag == "th":
            assert attributes.get("scope") == "col"
        if tag in {"h1", "h2", "h3", "h4"}:
            self.headings.append(tag)


def test_fragmento_consultavel_acessivel_responsivo_sem_script_ou_shell(payload):
    html = renderizar_dashboard_risco(construir_dashboard_risco(payload))
    parsed = Document()
    parsed.feed(html)
    assert not {"html", "body", "head", "script", "iframe"} & set(parsed.tags)
    assert len(parsed.ids) == len(set(parsed.ids))
    assert all(h[1:] in parsed.ids for h in parsed.hrefs if h.startswith("#"))
    assert parsed.tables == parsed.captions and "details" in parsed.tags
    assert 'aria-hidden="true"' in html and 'focus-visible' in html
    assert '@media(max-width:440px)' in html and 'DADOS SIMULADOS' in html
    assert all(h.startswith(("../data.json", "../dados/", "#dr-")) for h in parsed.hrefs)
    assert "https://" not in html and "fetch(" not in html
    assert parsed.headings[0] == "h1" and parsed.headings.count("h1") == 1
    assert "h4" not in parsed.headings
    assert "Cenários de estresse" in html and "Estresse · resultado / PL" in html
    assert "stress não é" not in html


@pytest.mark.parametrize("target", ["css", "url", "view"])
def test_renderer_recusa_ingresso_adulterado_de_estilo_rota_e_quadro(payload, target):
    d = construir_dashboard_risco(payload)
    if target == "css":
        d["views"][1]["exposures"]["country"][0]["bar_width"] = '10%;background:url(https://bad)'
    elif target == "url":
        d["sources"][0]["url"] = 'javascript:alert(1)'
    else:
        d["views"][0]["id"] = '\"><script>bad</script>'
    with pytest.raises(ValueError):
        renderizar_dashboard_risco(d)


def test_ingressos_invalidos_e_dominios_css_sem_nao_finitos(payload):
    with pytest.raises(TypeError):
        construir_dashboard_risco([])
    with pytest.raises(ValueError):
        renderizar_dashboard_risco({"schema": "desconhecido"})
    html = renderizar_dashboard_risco(construir_dashboard_risco(payload))
    assert "width:None" not in html and "width:nan" not in html and "width:inf" not in html
    widths = re.findall(r'width:(\d+(?:\.\d+)?)%', html)
    assert widths and all(0 <= float(w) <= 100 for w in widths)
