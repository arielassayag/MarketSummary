"""DADOS SIMULADOS: protocolo HTTP/recibo offline, sem autenticar transporte vivo."""

from __future__ import annotations

import copy
import io
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from cdp.cobertura.fontes import coletar, csv_canonico
from cdp.cobertura.insumos import _consenso, _Pacote
from cdp.cobertura.parametros import ParametrosCobertura
from cdp.data import publico
from cdp.data import publico_eps as eps
from cdp.data.publico_arquivo import Arquivo, ArquivoAdulterado
from cdp.data.publico_yahoo import consenso_de
from cdp.universe import Universe

TICKER = "CDP_SIM"
RECEBIDO = datetime(2026, 10, 7, 15, 1, 2, 345678, UTC)
DATA = date(2026, 10, 7)


def documento():
    def celula(period, end, value, currency="USD"):
        return {
            "period": period,
            "endDate": end,
            "earningsEstimate": {
                "avg": {"raw": value},
                "earningsCurrency": currency,
                "numberOfAnalysts": {"raw": 7},
            },
            "revenueEstimate": {
                "avg": {"raw": 1000 if period == "0y" else 1100},
                "revenueCurrency": "ARS",
            },
        }

    return {
        "rotulo": "DADOS SIMULADOS",
        "quoteSummary": {
            "error": None,
            "result": [
                {
                    "quoteType": {"symbol": TICKER},
                    "earningsTrend": {
                        "trend": [
                            celula("0q", "2026-09-30", 1, "MXN"),
                            celula("0y", "2026-12-31", 2.25),
                            celula("+1y", "2027-12-31", 2.75),
                        ]
                    },
                }
            ],
        },
    }


def trend(d):
    return d["quoteSummary"]["result"][0]["earningsTrend"]["trend"]


def corpo(d=None):
    return json.dumps(d if d is not None else documento(), separators=(",", ":")).encode()


def arquivo(root, body=None, recebido=RECEBIDO):
    a = Arquivo(root, agora=lambda: recebido, conhecimento_ate=recebido)
    key, url = eps.identidade(TICKER)
    b = corpo() if body is None else body
    reg = a.gravar(key, "YAHOO", url, b)
    info = {
        "ticker": TICKER,
        "rotulo": "DADOS SIMULADOS",
        "info": {"currency": "USD", "financialCurrency": "ARS", "targetMeanPrice": 50},
    }
    a.gravar(
        f"YAHOO/info/{TICKER}.json",
        "YAHOO",
        f"https://finance.yahoo.com/quote/{TICKER}",
        json.dumps(info).encode(),
    )
    return a, reg, b


def linha(root):
    arquivo(root)
    return publico.consenso_publico(
        [TICKER], DATA, root=root, offline=True, eps_por_periodo=True, conhecimento_ate=RECEBIDO
    ).iloc[0]


def mercado():
    lines = pd.DataFrame(
        [{"issuer_id": "SIM", "currency": "USD", "line_type": "LOCAL"}], index=[TICKER]
    )
    uni = Universe(lines, pd.DataFrame([{"country": "AR"}], index=["SIM"]))
    # Só recipiente fixo; não constrói mercado, modelo ou seed.
    return SimpleNamespace(universe=uni, is_synthetic=False, as_of=DATA, fx=pd.DataFrame())


def participante(row, raiz=None):
    p = ParametrosCobertura(
        {
            "consenso": {"unidade_metodo": "declaracao_fonte"},
            "qualidade": {"upside_limites": [-0.9, 3]},
        },
        {},
        {},
        {},
        {},
        {},
    )
    pk = _Pacote()
    _consenso(
        mercado(),
        SimpleNamespace(consenso=pd.DataFrame([row]), raiz=raiz),
        p,
        pk,
        "SIM",
        TICKER,
        "USD",
        "ARS",
        50,
        None,
        None,
        {},
        DATA,
    )
    return pk


def test_corpo_individual_decimal_e_origem():
    parsed, c = eps.ler_corpo(corpo(), TICKER)
    assert Decimal(str(parsed["earnings_estimate"]["0y"]["avg"])) == Decimal("2.25")
    assert c["moeda_comum"] == "USD"
    assert c["periodos"]["0y"]["period_end"] == "2026-12-31"
    assert c["periodos"]["0y"]["ancora"].endswith("/1")
    assert "revenue_estimate" not in parsed  # V2 limita este contrato ao EPS.
    assert consenso_de({"info": {"financialCurrency": "MXN"}}, parsed)["moeda_estimativas"] == "USD"


@pytest.mark.parametrize("campo", ["earningsCurrency", "avg"])
def test_ausencia_nao_preenchida_por_trimestre_ou_info(campo):
    d = documento()
    trend(d)[2]["earningsEstimate"].pop(campo)
    parsed, c = eps.ler_corpo(corpo(d), TICKER)
    assert c["periodos"]["+1y"]["currency" if campo == "earningsCurrency" else "avg"] is None
    if campo == "earningsCurrency":
        assert c["moeda_comum"] is None
    else:
        assert parsed["earnings_estimate"]["+1y"]["avg"] is None


def test_exercicio_e_data_ausentes_preservados():
    d = documento()
    trend(d).pop()
    trend(d)[1].pop("endDate")
    _, c = eps.ler_corpo(corpo(d), TICKER)
    assert "+1y" not in c["periodos"] and c["moeda_comum"] is None
    assert c["periodos"]["0y"]["period_end"] is None


@pytest.mark.parametrize(
    "caso",
    [
        "symbol",
        "error",
        "result",
        "duplicate",
        "currency",
        "date",
        "date_order",
        "bool",
        "string_raw",
        "negative_count",
        "fraction_count",
        "block",
        "invalid_currency",
        "infinite",
        "overflow",
    ],
)
def test_recusa_corpo_contraditorio(caso):
    d = documento()
    t = trend(d)
    if caso == "symbol":
        d["quoteSummary"]["result"][0]["quoteType"]["symbol"] = "OUTRO"
    elif caso == "error":
        d["quoteSummary"]["error"] = {"code": "Unauthorized"}
    elif caso == "result":
        d["quoteSummary"]["result"].append(copy.deepcopy(d["quoteSummary"]["result"][0]))
    elif caso == "duplicate":
        t.append(copy.deepcopy(t[1]))
    elif caso == "currency":
        t[2]["earningsEstimate"]["earningsCurrency"] = "ARS"
    elif caso == "date":
        t[1]["endDate"] = "2026-02-30"
    elif caso == "date_order":
        t[2]["endDate"] = "2026-01-01"
    elif caso == "bool":
        t[1]["earningsEstimate"]["avg"]["raw"] = True
    elif caso == "string_raw":
        t[1]["earningsEstimate"]["avg"]["raw"] = "2.25"
    elif caso == "negative_count":
        t[1]["earningsEstimate"]["numberOfAnalysts"]["raw"] = -1
    elif caso == "fraction_count":
        t[1]["earningsEstimate"]["numberOfAnalysts"]["raw"] = 1.5
    elif caso == "block":
        t[1]["earningsEstimate"] = []
    elif caso == "invalid_currency":
        t[1]["earningsEstimate"]["earningsCurrency"] = "US"
    elif caso == "infinite":
        t[1]["earningsEstimate"]["avg"]["raw"] = float("inf")
    elif caso == "overflow":
        t[1]["earningsEstimate"]["avg"]["raw"] = 10**400
    with pytest.raises(ValueError):
        eps.ler_corpo(corpo(d), TICKER)


@pytest.mark.parametrize(
    "body", [b'{"quoteSummary":{},"quoteSummary":{}}', b"{}", b"NaN", b"[]", b"{"]
)
def test_recusa_json_ambiguo(body):
    with pytest.raises(ValueError):
        eps.ler_corpo(body, TICKER)


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("url", "https://exemplo.invalid"),
        ("fonte", "RI"),
        ("chave", "YAHOO/earningsTrend/OUTRO.json"),
        ("sha256", "0" * 64),
        ("bytes", 1),
        ("data_coleta", RECEBIDO.replace(tzinfo=None)),
        ("data_coleta", datetime(2099, 1, 1, tzinfo=UTC)),
    ],
)
def test_recusa_registro_contraditorio(tmp_path, campo, valor):
    _, reg, b = arquivo(tmp_path)
    with pytest.raises(ValueError):
        eps.consenso_do_registro(
            b, TICKER, replace(reg, **{campo: valor}), conhecimento_ate=RECEBIDO
        )


def test_corte_exato_antes_depois_e_precisao(tmp_path):
    _, r, b = arquivo(tmp_path)
    with pytest.raises(ValueError):
        eps.consenso_do_registro(
            b, TICKER, r, conhecimento_ate=RECEBIDO - timedelta(microseconds=1)
        )
    for cut in (RECEBIDO, RECEBIDO + timedelta(microseconds=1)):
        _, extra = eps.consenso_do_registro(b, TICKER, r, conhecimento_ate=cut)
        c = json.loads(extra["eps_contexto"])
        assert c["publicacao_primaria"] is None and c["base_nominal_id"] is None
        assert c["ponte_FY_12m_FX"] is None and c["disponivel_desde"] == RECEBIDO.isoformat()
    with pytest.raises(ValueError):
        eps.consenso_do_registro(b, TICKER, r, conhecimento_ate=RECEBIDO.replace(tzinfo=None))
    seconds = replace(r, precisao="seconds")
    with pytest.raises(ValueError):
        eps.consenso_do_registro(b, TICKER, seconds, conhecimento_ate=RECEBIDO)


def test_arquivo_native_adulteracao(tmp_path):
    a, reg, b = arquivo(tmp_path)
    assert a.ler(reg) == b
    (a.base / reg.caminho).write_bytes(b + b" ")
    with pytest.raises(ArquivoAdulterado):
        a.ler(reg)


def test_api_offline_csv_proveniencia_participante(tmp_path):
    row = linha(tmp_path)
    c = eps.contexto_da_linha(row)
    assert c["provider"] == "Yahoo Finance" and c["ticker"] == TICKER
    table = pd.read_csv(io.StringIO(csv_canonico(pd.DataFrame([row]))))
    assert eps.contexto_da_linha(table.iloc[0]) == c
    pk = participante(table.iloc[0], tmp_path)
    assert pk.v["eps_fy1"] == 2.25 and pk.v["eps_fy2"] == 2.75
    assert pk.fontes["eps_fy1"]["eps_contexto"] == c
    assert pk.fontes["eps_fy1"]["sha256"] != pk.fontes["consenso"]["sha256"]
    assert "eps_contexto" not in pk.fontes["consenso"]


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("eps_fy1", 2.5),
        ("eps_fy2", None),
        ("sha256", "0" * 64),
        ("moeda_estimativas", "ARS"),
        ("eps_origem_moeda", None),
        ("eps_contexto", None),
    ],
)
def test_contradicao_linha_recusada_no_consumidor(tmp_path, campo, valor):
    row = linha(tmp_path).copy()
    row[campo] = valor
    with pytest.raises(ValueError):
        participante(row, tmp_path)


@pytest.mark.parametrize("null", [None, float("nan"), pd.NA, pd.NaT])
def test_ausencia_integral_legada(null):
    assert eps.contexto_da_linha({"eps_contexto": null, "eps_origem_moeda": null}) is None


def test_moeda_parcial_nao_cai_na_cotacao(tmp_path):
    d = documento()
    trend(d)[2]["earningsEstimate"].pop("earningsCurrency")
    arquivo(tmp_path, corpo(d))
    row = publico.consenso_publico(
        [TICKER], DATA, root=tmp_path, offline=True, eps_por_periodo=True, conhecimento_ate=RECEBIDO
    ).iloc[0]
    assert pd.isna(row.moeda_estimativas)
    pk = participante(row, tmp_path)
    assert pk.v["eps_fy1"] is None and pk.v.get("eps_fy2") is None


def test_coletor_normal_preserva_contexto(tmp_path):
    arquivo(tmp_path)
    d = coletar(
        mercado(),
        DATA,
        [],
        [TICKER],
        [],
        offline=True,
        raiz=tmp_path,
        eps_por_periodo=True,
        conhecimento_ate=RECEBIDO,
    )
    assert len(d.consenso) == 1
    assert eps.contexto_da_linha(d.consenso.iloc[0])["corpo_sha256"] == d.consenso.iloc[0].sha256
    assert (
        participante(d.consenso.iloc[0], tmp_path).fontes["eps_fy2"]["eps_contexto"][
            "publicacao_primaria"
        ]
        is None
    )


def test_default_nao_acrescenta_colunas(tmp_path):
    arquivo(tmp_path)
    out = publico.consenso_publico([TICKER], DATA, root=tmp_path, offline=True)
    assert not set(eps.COLUNAS) & set(out.columns)
    assert pd.isna(out.iloc[0].eps_fy1)


def test_validacao_http_nao_retorna_cache_sdk(tmp_path):
    arquivo(tmp_path)
    d = documento()
    trend(d)[2]["earningsEstimate"]["earningsCurrency"] = "ARS"
    a, _, _ = arquivo(tmp_path / "invalido", corpo(d))
    out = publico.consenso_publico(
        [TICKER], DATA, root=a.raiz, offline=True, eps_por_periodo=True, conhecimento_ate=RECEBIDO
    )
    assert pd.isna(out.iloc[0].eps_fy1) and "eps_contexto" not in out
    assert any("divergem" in f for f in out.attrs["falhas"])


def test_transporte_injetado_unico_registro_nativo(tmp_path, monkeypatch):
    a, reg, _ = arquivo(tmp_path)
    # Retirar só o documento EPS; a cotação info já foi recebida no sandbox.
    (a.base / reg.caminho).unlink()
    native = Arquivo(tmp_path, agora=lambda: RECEBIDO, conhecimento_ate=RECEBIDO)
    monkeypatch.setattr(
        publico, "_arquivo", lambda root, offline: native
    )  # somente relógio/Arquivo
    calls = []

    def transporte(url, headers):
        calls.append(url)
        return corpo()

    row = publico.consenso_publico(
        [TICKER],
        DATA,
        root=tmp_path,
        eps_por_periodo=True,
        eps_http_get=transporte,
        conhecimento_ate=RECEBIDO,
    ).iloc[0]
    assert calls == [eps.identidade(TICKER)[1]]
    c = eps.contexto_da_linha(row)
    stored = native.por_sha(c["corpo_sha256"])
    assert native.ler(stored) == corpo() and stored.limite_captura == RECEBIDO


def test_corte_normal_antes_da_recepcao(tmp_path):
    arquivo(tmp_path)
    out = publico.consenso_publico(
        [TICKER],
        DATA,
        root=tmp_path,
        offline=True,
        eps_por_periodo=True,
        conhecimento_ate=RECEBIDO - timedelta(microseconds=1),
    )
    assert pd.isna(out.iloc[0].eps_fy1) and "eps_contexto" not in out


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("dataset", "info"),
        ("provider", "OUTRO"),
        ("ticker", "OUTRO"),
        ("url", "https://exemplo.invalid"),
        ("publicacao_primaria", "2026-10-07"),
        ("moeda_comum", "ARS"),
        ("recebido_em", "2026-10-07"),
    ],
)
def test_contexto_adulterado_recusado(tmp_path, campo, valor):
    row = linha(tmp_path).copy()
    c = json.loads(row.eps_contexto)
    c[campo] = valor
    row["eps_contexto"] = json.dumps(c)
    with pytest.raises(ValueError):
        participante(row, tmp_path)


@pytest.mark.parametrize(
    "campo,valor", [("currency", "ARS"), ("period_end", "2026-01-01"), ("avg", 3)]
)
def test_segundo_periodo_contextual_mutado_recusado(tmp_path, campo, valor):
    row = linha(tmp_path).copy()
    c = json.loads(row.eps_contexto)
    c["periodos"]["+1y"][campo] = valor
    row["eps_contexto"] = json.dumps(c)
    with pytest.raises(ValueError):
        participante(row, tmp_path)


def test_precisao_csv_dez_algarismos_sem_tolerancia_adicional(tmp_path):
    d = documento()
    trend(d)[1]["earningsEstimate"]["avg"]["raw"] = 2.1234567890123
    arquivo(tmp_path, corpo(d))
    raw = publico.consenso_publico(
        [TICKER], DATA, root=tmp_path, offline=True, eps_por_periodo=True, conhecimento_ate=RECEBIDO
    )
    csv = pd.read_csv(io.StringIO(csv_canonico(raw))).iloc[0]
    assert eps.contexto_da_linha(csv)["periodos"]["0y"]["avg"] == 2.1234567890123
    csv["eps_fy1"] = 2.12345679  # outro valor representável, não um epsilon aceito
    with pytest.raises(ValueError):
        eps.contexto_da_linha(csv)


@pytest.mark.parametrize(
    "campo,valor",
    [("period_end", "2027-11-30"), ("valor_raw_literal", "9"), ("numberOfAnalysts", 11)],
)
def test_metadata_sozinha_nao_autentica_corpo(tmp_path, campo, valor):
    row = linha(tmp_path).copy()
    c = json.loads(row.eps_contexto)
    c["periodos"]["+1y"][campo] = valor
    row["eps_contexto"] = json.dumps(c)
    with pytest.raises(ValueError):
        participante(row, tmp_path)


def test_arquivo_ausente_no_consumo_tipado_recusado(tmp_path):
    row = linha(tmp_path)
    with pytest.raises(ValueError):
        participante(row)
    with pytest.raises(ValueError):
        participante(row, tmp_path / "ausente")


def test_numero_analistas_mutado_na_linha_recusado(tmp_path):
    row = linha(tmp_path).copy()
    row["n_analistas_eps"] = 100
    with pytest.raises(ValueError):
        participante(row, tmp_path)
