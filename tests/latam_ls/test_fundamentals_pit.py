"""Testes dos fundamentos point-in-time (CVM/SEC) e do security master — 100% offline.

As fixtures em ``tests/latam_ls/fixtures/cvm`` imitam o layout real dos arquivos de dados
abertos da CVM (``;``, latin-1, colunas e plano de contas reais) com empresas fictícias
(DADOS SIMULADOS). A fixture SEC imita ``companyfacts`` (IFRS, MXN).

A ALFA traz duas versões do ITR 1T25 (original em 2025-05-08 e reapresentação em 2025-09-15),
como se o cache tivesse acumulado dois downloads — o caso usado para testar que uma
reapresentação publicada depois NÃO altera datas anteriores.
"""

from __future__ import annotations

import io
import json
import math
import os
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from latam_ls.data import fundamentals_pit as fp
from latam_ls.data import security_master as smod
from latam_ls.data.fundamentals_pit import (
    PIT_COLUMNS,
    RATIO_COLUMNS,
    add_business_days,
    build_pit_fundamentals,
    cvm_facts_cached,
    cvm_zip_url,
    discrete_quarters,
    extract_cvm_facts,
    extract_sec_facts,
    fetch_cvm_zip,
    fetch_sec_companyfacts,
    load_pit,
    local_equivalent_prices,
    pit_coverage,
    pit_from_raw_facts,
    pit_ratios,
    pit_snapshot,
    read_cvm_zip,
    save_pit,
    ttm_at,
    validate_pit,
)
from latam_ls.data.security_master import (
    SEC_TICKERS_URL,
    HttpError,
    RateLimiter,
    b3_class_from_code,
    build_line_master,
    build_security_master,
    default_http_get,
    fca_url,
    fetch_cvm_fca,
    fetch_sec_company_tickers,
    parse_fca_zip,
    parse_sec_company_tickers,
    parse_unit_composition,
    search_sec_ciks,
    sec_user_agent,
)
from latam_ls.universe import universe_from_frame

FIX = Path(__file__).parent / "fixtures"
CVM_FIX = FIX / "cvm"
SEC_FIX = FIX / "sec"

ALFA = "11.111.111/0001-11"
BETA = "22.222.222/0001-22"
GAMA = "33.333.333/0001-33"
DELTA_CIK = "0009999999"
K = 1_000.0  # ESCALA_MOEDA = MIL


# ----------------------------------------------------------------------------
# Infra: sem rede, zips a partir das fixtures, HTTP falso
# ----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("Acesso à rede proibido nos testes.")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)


def zip_bytes(prefix: str) -> bytes:
    """Zipa os CSVs de fixture cujo nome começa com ``prefix`` (ex.: ``itr_cia_aberta_``)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(CVM_FIX.glob(f"{prefix}*.csv")):
            zf.writestr(p.name, p.read_bytes())
    return buf.getvalue()


def cvm_zip(doc: str, year: int) -> bytes:
    buf = io.BytesIO()
    pat = f"{doc.lower()}_cia_aberta_"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(CVM_FIX.glob(f"{pat}*{year}.csv")):
            zf.writestr(p.name, p.read_bytes())
    return buf.getvalue()


def fca_zip() -> bytes:
    return zip_bytes("fca_cia_aberta_")


def companyfacts() -> dict:
    return json.loads((SEC_FIX / "companyfacts_CIK0009999999.json").read_text(encoding="utf-8"))


SEC_TICKERS_JSON = json.dumps({
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [[9999999, "SIMULADA DELTA (DADOS SIMULADOS)", "SDLT", "NYSE"],
             [1119639, "PETROLEO BRASILEIRO SA PETROBRAS", "PBR", "NYSE"]],
}).encode()


class FakeHttp:
    """Servidor HTTP falso: URL → bytes; o resto devolve 404. Registra chamadas e headers."""

    def __init__(self, routes: dict[str, bytes | Exception]):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, headers) -> bytes:
        self.calls.append((url, dict(headers)))
        r = self.routes.get(url)
        if r is None:
            raise HttpError(404, url)
        if isinstance(r, Exception):
            raise r
        return r


def all_routes() -> dict[str, bytes]:
    return {
        cvm_zip_url("ITR", 2024): cvm_zip("ITR", 2024),
        cvm_zip_url("DFP", 2024): cvm_zip("DFP", 2024),
        cvm_zip_url("ITR", 2025): cvm_zip("ITR", 2025),
        cvm_zip_url("DFP", 2025): cvm_zip("DFP", 2025),
        fca_url(2025): fca_zip(),
        SEC_TICKERS_URL: SEC_TICKERS_JSON,
        fp.SEC_COMPANYFACTS_URL.format(cik=DELTA_CIK): json.dumps(companyfacts()).encode(),
    }


def fake_limiter() -> tuple[RateLimiter, list[float]]:
    clock = [0.0]
    sleeps: list[float] = []

    def sleep(dt: float) -> None:
        sleeps.append(dt)
        clock[0] += dt

    return RateLimiter(8.0, clock=lambda: clock[0], sleep=sleep), sleeps


def make_universe():
    rows = [
        dict(issuer_id="SIM_ALFA", issuer_name="Simulada Alfa", country="BR",
             gics_sector="Industrials", line_type="LOCAL", yahoo_ticker="ALFA3.SA",
             exchange="B3", currency="BRL", adr_ratio="", primary_line=True),
        dict(issuer_id="SIM_ALFA", issuer_name="Simulada Alfa", country="BR",
             gics_sector="Industrials", line_type="LOCAL", yahoo_ticker="ALFA11.SA",
             exchange="B3", currency="BRL", adr_ratio="", primary_line=False),
        dict(issuer_id="SIM_ALFA", issuer_name="Simulada Alfa", country="BR",
             gics_sector="Industrials", line_type="ADR", yahoo_ticker="SALFA",
             exchange="NYSE", currency="USD", adr_ratio="2", primary_line=False),
        dict(issuer_id="SIM_BETA", issuer_name="Banco Simulado Beta", country="BR",
             gics_sector="Financials", line_type="LOCAL", yahoo_ticker="BETA6.SA",
             exchange="B3", currency="BRL", adr_ratio="", primary_line=True),
        dict(issuer_id="SIM_GAMA", issuer_name="Simulada Gama", country="BR",
             gics_sector="Consumer Staples", line_type="LOCAL", yahoo_ticker="GAMA3.SA",
             exchange="B3", currency="BRL", adr_ratio="", primary_line=True),
        dict(issuer_id="SIM_DELTA", issuer_name="Simulada Delta", country="MX",
             gics_sector="Materials", line_type="LOCAL", yahoo_ticker="SDLTB.MX",
             exchange="BMV", currency="MXN", adr_ratio="", primary_line=True),
        dict(issuer_id="SIM_DELTA", issuer_name="Simulada Delta", country="MX",
             gics_sector="Materials", line_type="ADR", yahoo_ticker="SDLT",
             exchange="NYSE", currency="USD", adr_ratio="5", primary_line=False),
        dict(issuer_id="SIM_EPS", issuer_name="Simulada Epsilon", country="BR",
             gics_sector="Utilities", line_type="LOCAL", yahoo_ticker="SEPS3.SA",
             exchange="B3", currency="BRL", adr_ratio="", primary_line=True),
    ]
    return universe_from_frame(pd.DataFrame(rows), source_sha256="fixture")


@pytest.fixture(scope="module")
def cvm_raw() -> pd.DataFrame:
    frames = [extract_cvm_facts(read_cvm_zip(cvm_zip(doc, y), doc, y), doc)
              for doc, y in (("ITR", 2024), ("DFP", 2024), ("ITR", 2025), ("DFP", 2025))]
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def cvm_pit(cvm_raw) -> pd.DataFrame:
    return pit_from_raw_facts(cvm_raw, {ALFA: "SIM_ALFA", BETA: "SIM_BETA", GAMA: "SIM_GAMA"})


def rows(pit: pd.DataFrame, issuer: str, metric: str) -> pd.DataFrame:
    return pit[(pit["issuer_id"] == issuer) & (pit["metric"] == metric)].reset_index(drop=True)


def snap_value(pit, issuer, metric, as_of):
    s = pit_snapshot(pit, as_of)
    s = s[(s["issuer_id"] == issuer) & (s["metric"] == metric)]
    return (float(s["value"].iloc[0]), s["period_end"].iloc[0].date()) if len(s) else (None, None)


# ----------------------------------------------------------------------------
# Leitura e extração CVM
# ----------------------------------------------------------------------------

def test_read_cvm_zip_keeps_only_last_period_and_used_accounts():
    t = read_cvm_zip(cvm_zip("ITR", 2025), "ITR", 2025)
    assert set(t) >= {"index", "DRE_con", "DRE_ind", "BPA_con", "BPP_con", "capital"}
    assert (t["DRE_con"]["ORDEM_EXERC"] == "ÚLTIMO").all()  # latin-1 decodificado
    assert not t["BPA_con"]["CD_CONTA"].isin(["1.01.03"]).any()  # conta não usada filtrada
    assert t["BPA_ind"].empty  # arquivo ausente no zip ⇒ tabela vazia


def test_extract_cvm_layout_resolution(cvm_raw):
    a = cvm_raw[cvm_raw["entity"] == ALFA]
    dfp = a[(a["period_end"] == "2024-12-31") & (a["source"].str.startswith("cvm:dfp"))]
    # con tem preferência sobre ind (ind divergente 999/888 ignorado)
    rev = dfp[dfp["metric"] == "revenue"]
    assert rev["value"].tolist() == [1000 * K]
    assert (rev["source"] == "cvm:dfp:con").all()
    ni = dfp[dfp["metric"] == "net_income"]
    assert ni["value"].tolist() == [100 * K]  # 3.11.01 atribuído ao controlador
    eq = dfp[dfp["metric"] == "equity"]["value"].tolist()
    assert eq == [1000 * K]  # 1050 − 50 não controladores
    assert dfp[dfp["metric"] == "cash"]["value"].tolist() == [200 * K]
    assert dfp[dfp["metric"] == "gross_debt"]["value"].tolist() == [800 * K]
    assert dfp[dfp["metric"] == "total_assets"]["value"].tolist() == [2000 * K]
    sh = a[(a["metric"] == "shares_outstanding") & (a["period_end"] == "2024-12-31")]
    assert sh["value"].tolist() == [990_000.0]
    assert sh["currency"].isna().all()
    # PENÚLTIMO (comparativos com valores absurdos) nunca entra
    assert not (a["value"].isin([99999 * K, 77777 * K])).any()
    # Banco: sem EBIT/caixa/dívida; LL e PL atribuídos ao controlador
    b = cvm_raw[cvm_raw["entity"] == BETA]
    assert set(b["metric"]) == {"revenue", "net_income", "equity", "total_assets",
                                "shares_outstanding"}
    b24 = b[b["period_end"] == "2024-12-31"].set_index("metric")["value"]
    assert b24["net_income"] == 1150 * K and b24["equity"] == 6000 * K
    # Só individual (GAMA): lucro do período sem filhas
    g = cvm_raw[(cvm_raw["entity"] == GAMA) & (cvm_raw["metric"] == "net_income")]
    assert sorted(g["value"]) == sorted(v * K for v in (10, 21, 33, 45, 12))
    assert (g["source"].str.endswith(":ind")).all()


def test_received_date_and_versions_come_from_index(cvm_raw):
    q1 = cvm_raw[(cvm_raw["entity"] == ALFA) & (cvm_raw["metric"] == "revenue")
                 & (cvm_raw["period_end"] == "2025-03-31")].sort_values("version")
    assert q1["version"].tolist() == [1, 2]
    assert q1["value"].tolist() == [270 * K, 275 * K]
    assert [d.date() for d in q1["received_date"]] == [date(2025, 5, 8), date(2025, 9, 15)]


def test_rows_without_receipt_are_dropped():
    t = read_cvm_zip(cvm_zip("ITR", 2025), "ITR", 2025)
    t["index"] = t["index"][t["index"]["VERSAO"] != "2"]
    f = extract_cvm_facts(t, "ITR")
    assert not ((f["entity"] == ALFA) & (f["version"] == 2)).any()


# ----------------------------------------------------------------------------
# YTD → trimestre discreto e TTM
# ----------------------------------------------------------------------------

def _flows(raw, entity, metric, lag=1):
    f = raw[(raw["entity"] == entity) & (raw["metric"] == metric)].copy()
    f["available_date"] = add_business_days(f["received_date"], lag)
    return f


def test_ytd_to_discrete_quarters(cvm_raw):
    f = _flows(cvm_raw, ALFA, "revenue")
    q = discrete_quarters(f, as_of=date(2025, 9, 1)) / K
    expected = {"2024-03-31": 230, "2024-06-30": 250,  # Q1 = YTD 3M; Q2 = trimestre reportado
                "2024-09-30": 260,  # só YTD: 740 − 480
                "2024-12-31": 260,  # DFP anual − 9M: 1000 − 740
                "2025-03-31": 270, "2025-06-30": 290}
    assert {k.strftime("%Y-%m-%d"): v for k, v in q.items()} == expected
    q_later = discrete_quarters(f, as_of=date(2025, 9, 20)) / K
    assert q_later[pd.Timestamp("2025-03-31")] == 275  # versão 2 já pública


def test_discrete_quarters_non_calendar_fiscal_year(cvm_raw):
    f = _flows(cvm_raw, GAMA, "revenue")
    q = discrete_quarters(f) / K  # exercício abril–março
    assert q[pd.Timestamp("2024-06-30")] == 100
    assert q[pd.Timestamp("2024-09-30")] == 110
    assert q[pd.Timestamp("2024-12-31")] == 120
    assert q[pd.Timestamp("2025-03-31")] == 120  # DFP (12m abr–mar) − 9M
    assert q[pd.Timestamp("2025-06-30")] == 120


def test_ttm_sum_of_four_quarters_and_annual(cvm_raw):
    f = _flows(cvm_raw, ALFA, "revenue")
    t = ttm_at(f, as_of=date(2025, 9, 1)) / K
    assert t[pd.Timestamp("2024-12-31")] == 1000  # anual direto
    assert t[pd.Timestamp("2025-03-31")] == 270 + 260 + 260 + 250
    assert t[pd.Timestamp("2025-06-30")] == 290 + 270 + 260 + 260
    assert math.isnan(t[pd.Timestamp("2024-09-30")])  # falta 4T23 ⇒ ausente, não zero
    g = ttm_at(_flows(cvm_raw, GAMA, "revenue")) / K
    assert g[pd.Timestamp("2025-03-31")] == 450
    assert g[pd.Timestamp("2025-06-30")] == 120 + 120 + 120 + 110


def test_ttm_history_is_point_in_time(cvm_pit):
    r = rows(cvm_pit, "SIM_ALFA", "revenue_ttm")
    got = {(p.date().isoformat(), a.date().isoformat()): v / K
           for p, a, v in zip(r["period_end"], r["available_date"], r["value"], strict=True)}
    assert got == {
        ("2024-12-31", "2025-03-11"): 1000,  # DFP recebido seg 10/03 + 1 dia útil
        ("2025-03-31", "2025-05-09"): 1040,  # ITR recebido qui 08/05 + 1 dia útil
        ("2025-03-31", "2025-09-16"): 1045,  # reapresentação (v2) só a partir de 16/09
        ("2025-06-30", "2025-08-08"): 1080,
        ("2025-06-30", "2025-09-16"): 1085,  # 2T25 recalculado com o 1T25 reapresentado
    }
    assert set(r["currency"]) == {"BRL"}
    assert r["source"].str.contains(r"\|ttm:(?:12m|4q)$").all()


# ----------------------------------------------------------------------------
# Seleção por data de disponibilidade (sem look-ahead)
# ----------------------------------------------------------------------------

def test_version_selection_by_available_date(cvm_pit):
    # antes da lag: só o anual
    assert snap_value(cvm_pit, "SIM_ALFA", "revenue_ttm", date(2025, 5, 8)) == (
        1000 * K, date(2024, 12, 31))
    assert snap_value(cvm_pit, "SIM_ALFA", "revenue_ttm", date(2025, 5, 9)) == (
        1040 * K, date(2025, 3, 31))
    assert snap_value(cvm_pit, "SIM_ALFA", "revenue_ttm", date(2025, 9, 1)) == (
        1080 * K, date(2025, 6, 30))
    # reapresentação publicada depois NÃO afeta datas anteriores
    assert snap_value(cvm_pit, "SIM_ALFA", "equity", date(2025, 6, 1)) == (
        1028 * K, date(2025, 3, 31))
    assert snap_value(cvm_pit, "SIM_ALFA", "revenue_ttm", date(2025, 9, 16)) == (
        1085 * K, date(2025, 6, 30))
    eq = rows(cvm_pit, "SIM_ALFA", "equity")
    q1 = eq[eq["period_end"] == "2025-03-31"].sort_values("available_date")
    assert q1["value"].tolist() == [1028 * K, 1033 * K]
    assert q1["version"].tolist() == [1, 2]


def test_strict_policy_when_only_latest_version_is_published():
    """Arquivo real traz só a última versão: o valor vale a partir do DT_RECEB dela."""
    t = read_cvm_zip(cvm_zip("ITR", 2025), "ITR", 2025)
    for k in ("DRE_con", "BPA_con", "BPP_con"):
        t[k] = t[k][t[k]["VERSAO"] != "1"]  # versão 1 substituída no arquivo publicado
    t["DRE_con"] = pd.concat([t["DRE_con"], read_cvm_zip(cvm_zip("ITR", 2025), "ITR", 2025)[
        "DRE_con"].query("DT_REFER == '2025-06-30'")]).drop_duplicates()
    raw = pd.concat([extract_cvm_facts(t, "ITR"),
                     extract_cvm_facts(read_cvm_zip(cvm_zip("ITR", 2024), "ITR", 2024), "ITR"),
                     extract_cvm_facts(read_cvm_zip(cvm_zip("DFP", 2024), "DFP", 2024), "DFP")])
    pit = pit_from_raw_facts(raw, {ALFA: "SIM_ALFA"})
    # Em 01/06/2025 o 1T25 só existe na v2 (recebida em 15/09) ⇒ ainda não é conhecido.
    assert snap_value(pit, "SIM_ALFA", "revenue_ttm", date(2025, 6, 1)) == (
        1000 * K, date(2024, 12, 31))
    assert snap_value(pit, "SIM_ALFA", "equity", date(2025, 6, 1)) == (
        1000 * K, date(2024, 12, 31))
    assert snap_value(pit, "SIM_ALFA", "revenue_ttm", date(2025, 9, 16))[0] == 1085 * K


def test_snapshot_staleness_drops_old_periods(cvm_pit):
    s = pit_snapshot(cvm_pit, date(2027, 12, 31))
    assert s.empty
    s2 = pit_snapshot(cvm_pit, date(2027, 12, 31), max_age_days=2000)
    assert not s2.empty


# ----------------------------------------------------------------------------
# Índices
# ----------------------------------------------------------------------------

def test_pit_ratios_values(cvm_pit):
    px = pd.DataFrame({"SIM_ALFA": [9.0, 10.0], "SIM_BETA": [20.0, 20.0],
                       "SIM_GAMA": [np.nan, 5.0]},
                      index=pd.to_datetime(["2025-08-29", "2025-09-01"]))
    r = pit_ratios(cvm_pit, px, date(2025, 9, 1))
    assert list(r.columns) == RATIO_COLUMNS
    a = r.loc["SIM_ALFA"]
    mcap = 10.0 * 990_000
    ni, rev, ebit, eq = 111 * K, 1080 * K, 216 * K, 1060 * K
    assert a["earnings_yield"] == pytest.approx(ni / mcap)
    assert a["book_to_price"] == pytest.approx(eq / mcap)
    assert a["roe"] == pytest.approx(ni / eq)
    assert a["ebit_margin"] == pytest.approx(ebit / rev) == pytest.approx(0.2)
    assert a["net_debt_to_equity"] == pytest.approx((800 * K - 200 * K) / eq)
    assert a["asset_turnover"] == pytest.approx(rev / (2100 * K))
    # Banco: sem EBIT/dívida ⇒ NaN (nunca zero); TTM 1T25 indisponível ⇒ usa anual 2024
    b = r.loc["SIM_BETA"]
    assert math.isnan(b["ebit_margin"]) and math.isnan(b["net_debt_to_equity"])
    assert b["roe"] == pytest.approx(1150 / 6200)
    assert b["earnings_yield"] == pytest.approx(1150 * K / (20.0 * 2_000_000))
    # GAMA: sem ações nem balanço ⇒ índices de preço/balanço ausentes
    g = r.loc["SIM_GAMA"]
    assert math.isnan(g["earnings_yield"]) and math.isnan(g["book_to_price"])
    assert math.isnan(g["roe"])


def test_pit_ratios_missing_data_stays_nan(cvm_pit):
    px = pd.DataFrame({"SIM_ALFA": [10.0], "SIM_ZETA": [3.0]},
                      index=pd.to_datetime(["2025-09-01"]))
    r = pit_ratios(cvm_pit, px, date(2025, 3, 1))  # antes de qualquer TTM publicado
    assert r.loc["SIM_ALFA", ["earnings_yield", "roe", "ebit_margin"]].isna().all()
    assert r.loc["SIM_ZETA"].isna().all()  # emissor sem fundamentos
    # preço velho demais ⇒ NaN
    old = pd.DataFrame({"SIM_ALFA": [10.0]}, index=pd.to_datetime(["2025-07-01"]))
    r2 = pit_ratios(cvm_pit, old, date(2025, 9, 1))
    assert math.isnan(r2.loc["SIM_ALFA", "earnings_yield"])
    assert not math.isnan(r2.loc["SIM_ALFA", "roe"])  # índices sem preço continuam válidos
    # moeda do preço divergente da moeda das demonstrações ⇒ NaN
    px3 = pd.DataFrame({"SIM_ALFA": [10.0]}, index=pd.to_datetime(["2025-09-01"]))
    r3 = pit_ratios(cvm_pit, px3, date(2025, 9, 1), price_currency={"SIM_ALFA": "USD"})
    assert math.isnan(r3.loc["SIM_ALFA", "book_to_price"])
    # ações informadas pelo chamador substituem as da tabela
    r4 = pit_ratios(cvm_pit, px3, date(2025, 9, 1), shares=pd.Series({"SIM_ALFA": 495_000}))
    assert r4.loc["SIM_ALFA", "earnings_yield"] == pytest.approx(111 * K / (10 * 495_000))


def test_pit_ratios_negative_equity_guards():
    pit = pd.DataFrame([
        ("X", "net_income_ttm", "2025-06-30", "2025-08-01", 50.0, "BRL", "t", 1),
        ("X", "equity", "2025-06-30", "2025-08-01", -100.0, "BRL", "t", 1),
        ("X", "gross_debt", "2025-06-30", "2025-08-01", 300.0, "BRL", "t", 1),
        ("X", "cash", "2025-06-30", "2025-08-01", 50.0, "BRL", "t", 1),
        ("X", "shares_outstanding", "2025-06-30", "2025-08-01", 10.0, None, "t", 1),
        ("X", "revenue_ttm", "2025-06-30", "2025-08-01", 0.0, "BRL", "t", 1),
    ], columns=PIT_COLUMNS)
    pit = fp._coerce_pit(pit)
    px = pd.DataFrame({"X": [10.0]}, index=pd.to_datetime(["2025-08-01"]))
    r = pit_ratios(pit, px, date(2025, 8, 1)).loc["X"]
    assert math.isnan(r["roe"]) and math.isnan(r["net_debt_to_equity"])
    assert r["book_to_price"] == pytest.approx(-1.0)  # PL negativo é informação válida
    assert math.isnan(r["ebit_margin"])  # receita zero ⇒ NaN


# ----------------------------------------------------------------------------
# SEC companyfacts
# ----------------------------------------------------------------------------

def test_sec_companyfacts_parsing():
    raw = extract_sec_facts(companyfacts())
    assert set(raw["entity"]) == {DELTA_CIK}
    money = raw[raw["metric"] != "shares_outstanding"]
    assert set(money["currency"]) == {"MXN"}  # moeda do unit key (USD de conveniência fora)
    assert raw[raw["metric"] == "shares_outstanding"]["currency"].isna().all()
    rev = raw[raw["metric"] == "revenue"]
    assert 9_999_999 not in rev["value"].tolist()  # formulário S-8 ignorado
    assert 300 not in rev["value"].tolist()  # USD ignorado
    # mesmo valor refiled não cria versão nova
    assert len(rev[rev["period_end"] == "2023-12-31"]) == 1
    ni = raw[raw["metric"] == "net_income"].sort_values(["period_end", "version"])
    fy22 = ni[ni["period_end"] == "2022-12-31"]
    assert fy22["value"].tolist() == [450.0, 440.0]  # ProfitLoss antes, tag melhor depois
    assert [d.date() for d in fy22["received_date"]] == [date(2023, 4, 20), date(2024, 4, 19)]
    fy23 = ni[ni["period_end"] == "2023-12-31"]
    assert fy23["value"].tolist() == [500.0, 520.0]  # mesmo dia: só a melhor tag
    assert fy23["version"].tolist() == [1, 2]


def test_sec_pit_ttm_and_ratios():
    raw = extract_sec_facts(companyfacts())
    pit = pit_from_raw_facts(raw, {DELTA_CIK: "SIM_DELTA"})
    validate_pit(pit)
    assert snap_value(pit, "SIM_DELTA", "net_income_ttm", date(2023, 12, 29)) == (
        450.0, date(2022, 12, 31))
    assert snap_value(pit, "SIM_DELTA", "net_income_ttm", date(2024, 4, 22)) == (
        500.0, date(2023, 12, 31))
    assert snap_value(pit, "SIM_DELTA", "net_income_ttm", date(2025, 4, 22)) == (
        500.0, date(2023, 12, 31))  # 20-F de 2025 arquivado em 22/04 ⇒ disponível 23/04
    assert snap_value(pit, "SIM_DELTA", "net_income_ttm", date(2025, 4, 23)) == (
        600.0, date(2024, 12, 31))
    px = pd.DataFrame({"SIM_DELTA": [50.0]}, index=pd.to_datetime(["2025-05-02"]))
    r = pit_ratios(pit, px, date(2025, 5, 2)).loc["SIM_DELTA"]
    assert r["earnings_yield"] == pytest.approx(600 / (50 * 1_010_000))
    assert r["roe"] == pytest.approx(600 / 4300)
    assert r["ebit_margin"] == pytest.approx(1000 / 5500)
    assert r["net_debt_to_equity"] == pytest.approx((2100 - 900) / 4300)


def test_fetch_sec_companyfacts_cache_ua_and_throttle(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Equipe CDP pesquisa@example.org")
    http = FakeHttp(all_routes())
    lim, sleeps = fake_limiter()
    obj = fetch_sec_companyfacts(9999999, http_get=http, cache_dir=tmp_path, limiter=lim)
    assert obj["cik"] == 9999999
    assert http.calls[0][1]["User-Agent"] == "Equipe CDP pesquisa@example.org"
    again = fetch_sec_companyfacts("9999999", http_get=http, cache_dir=tmp_path, limiter=lim)
    assert again == obj and len(http.calls) == 1  # cache JSON
    assert fetch_sec_companyfacts(123, http_get=http, cache_dir=tmp_path, limiter=lim) is None
    assert sleeps and all(s == pytest.approx(0.125) for s in sleeps)  # ≤ 8 req/s


def test_rate_limiter_spacing():
    lim, sleeps = fake_limiter()
    for _ in range(4):
        lim.wait()
    assert sleeps == [pytest.approx(0.125)] * 3
    with pytest.raises(ValueError):
        RateLimiter(0)


# ----------------------------------------------------------------------------
# HTTP padrão e cache CVM
# ----------------------------------------------------------------------------

class _Resp:
    def __init__(self, data: bytes):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_default_http_get_retries_only_transient(monkeypatch):
    attempts = []

    def fake_urlopen(req, timeout):
        attempts.append(req.full_url)
        if len(attempts) <= 2:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, None)
        return _Resp(b"ok")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    sleeps: list[float] = []
    assert default_http_get("https://x.test/a", {}, sleep=sleeps.append) == b"ok"
    assert sleeps == [1.0, 2.0]

    def not_found(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", not_found)
    sleeps.clear()
    with pytest.raises(HttpError) as ei:
        default_http_get("https://x.test/b", {}, sleep=sleeps.append)
    assert ei.value.status == 404 and sleeps == []


def test_fetch_cvm_zip_cache_refresh_and_fallback(tmp_path):
    http = FakeHttp(all_routes())
    today = date(2025, 10, 3)
    p = fetch_cvm_zip("ITR", 2025, cache_dir=tmp_path, http_get=http, today=today)
    assert p is not None and p.exists() and len(http.calls) == 1
    fetch_cvm_zip("ITR", 2025, cache_dir=tmp_path, http_get=http, today=today)
    assert len(http.calls) == 1  # cache recente
    old = time.time() - 30 * 86400
    os.utime(p, (old, old))
    fetch_cvm_zip("ITR", 2025, cache_dir=tmp_path, http_get=http, today=today)
    assert len(http.calls) == 2  # ano recente + cache velho ⇒ rebaixa
    os.utime(p, (old, old))
    down = FakeHttp({cvm_zip_url("ITR", 2025): HttpError(503, "x")})
    assert fetch_cvm_zip("ITR", 2025, cache_dir=tmp_path, http_get=down, today=today) == p
    assert fetch_cvm_zip("DFP", 2031, cache_dir=tmp_path, http_get=http, today=today) is None
    # anos antigos não são rebaixados automaticamente
    p24 = fetch_cvm_zip("DFP", 2024, cache_dir=tmp_path, http_get=http, today=today)
    os.utime(p24, (old, old))
    n = len(http.calls)
    fetch_cvm_zip("DFP", 2024, cache_dir=tmp_path, http_get=http, today=date(2026, 10, 3))
    assert len(http.calls) == n
    bad = FakeHttp({cvm_zip_url("DFP", 2023): b"<html>erro</html>"})
    with pytest.raises(ValueError):
        fetch_cvm_zip("DFP", 2023, cache_dir=tmp_path, http_get=bad, today=today)


def test_cvm_extracted_cache_accumulates_versions(tmp_path):
    """Downloads sucessivos (v1, depois só v2) preservam as duas versões no cache extraído."""
    full = read_cvm_zip(cvm_zip("ITR", 2025), "ITR", 2025)

    def zip_with(version: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for p in sorted(CVM_FIX.glob("itr_cia_aberta_*2025.csv")):
                df = pd.read_csv(p, sep=";", encoding="latin-1", dtype=str)
                if "VERSAO" in df.columns and "DT_RECEB" not in df.columns:
                    keep = ~((df["CNPJ_CIA"] == ALFA) & (df["DT_REFER"] == "2025-03-31")
                             & (df["VERSAO"] != version))
                    df = df[keep]
                zf.writestr(p.name, df.to_csv(sep=";", index=False).encode("latin-1"))
        return buf.getvalue()

    zpath = tmp_path / "itr_cia_aberta_2025.zip"
    zpath.write_bytes(zip_with("1"))
    f1 = cvm_facts_cached(zpath, "ITR", 2025)
    q = f1[(f1["entity"] == ALFA) & (f1["metric"] == "revenue")
           & (f1["period_end"] == "2025-03-31")]
    assert q["version"].tolist() == [1]
    zpath.write_bytes(zip_with("2"))
    f2 = cvm_facts_cached(zpath, "ITR", 2025)
    q2 = f2[(f2["entity"] == ALFA) & (f2["metric"] == "revenue")
            & (f2["period_end"] == "2025-03-31")].sort_values("version")
    assert q2["version"].tolist() == [1, 2]
    assert len(list((tmp_path / "extracted").glob("*.parquet"))) == 2
    assert full["DRE_con"]["VERSAO"].isin(["1", "2"]).all()


# ----------------------------------------------------------------------------
# Security master
# ----------------------------------------------------------------------------

def test_parse_unit_composition_and_classes():
    assert parse_unit_composition("1 ON / 2 PN") == 3
    assert parse_unit_composition("1 KLBN3 + 4 KLBN4") == 5
    assert parse_unit_composition("1 ON + 1 PN") == 2
    assert parse_unit_composition("01 ação ordinária e 04 ações preferenciais") == 5
    assert math.isnan(parse_unit_composition(None))
    assert math.isnan(parse_unit_composition("composição variável"))
    assert b3_class_from_code("PETR4") == "PN" and b3_class_from_code("KLBN11") == "UNIT"
    assert b3_class_from_code("JBSS32") == "BDR" and b3_class_from_code("XYZ") is None


def test_build_security_master_from_official_sources():
    uni = make_universe()
    fca = parse_fca_zip(fca_zip())
    sec = parse_sec_company_tickers(SEC_TICKERS_JSON)
    lm = build_line_master(uni, fca, sec)
    assert lm.loc["ALFA11.SA", "share_class"] == "UNIT"
    assert lm.loc["ALFA11.SA", "shares_per_line"] == 3  # "1 ALFA3 + 2 ALFA4"
    assert lm.loc["ALFA3.SA", "shares_per_line"] == 1
    assert lm.loc["SALFA", "shares_per_line"] == 2  # razão ADR oficial do universo
    assert lm.loc["BETA6.SA", "share_class"] == "PNB"
    assert not lm.loc["SEPS3.SA", "validated"]
    sm = build_security_master(uni, fca, sec)
    assert sm.loc["SIM_ALFA", "cnpj"] == ALFA
    assert sm.loc["SIM_ALFA", "cvm_code"] == "99991"
    assert sm.loc["SIM_ALFA", "share_classes"] == "ON|UNIT"
    assert sm.loc["SIM_ALFA", "adr_ticker"] == "SALFA" and sm.loc["SIM_ALFA", "adr_ratio"] == 2
    assert sm.loc["SIM_ALFA", "valid_tickers"] == "ALFA11.SA|ALFA3.SA"
    assert sm.loc["SIM_ALFA", "unvalidated_tickers"] == "SALFA"
    assert sm.loc["SIM_DELTA", "cik"] == DELTA_CIK
    assert sm.loc["SIM_DELTA", "fundamentals_source"] == "SEC"
    assert sm.loc["SIM_DELTA", "local_currency"] == "MXN"
    assert sm.loc["SIM_BETA", "fundamentals_source"] == "CVM"
    assert pd.isna(sm.loc["SIM_EPS", "cnpj"]) and pd.isna(sm.loc["SIM_EPS", "cik"])
    assert pd.isna(sm.loc["SIM_EPS", "fundamentals_source"])


def test_fetch_fca_and_sec_tickers_with_cache(tmp_path):
    http = FakeHttp(all_routes())
    fca = fetch_cvm_fca(2025, http_get=http, cache_dir=tmp_path)
    assert "ALFA11" in set(fca["Codigo_Negociacao"])
    fetch_cvm_fca(2025, http_get=http, cache_dir=tmp_path)
    assert len(http.calls) == 1
    lim, _ = fake_limiter()
    t = fetch_sec_company_tickers(http_get=http, cache_dir=tmp_path, limiter=lim)
    assert t.set_index("ticker").loc["SDLT", "cik"] == DELTA_CIK
    assert "CDP-Cabra-da-Peste" in http.calls[-1][1]["User-Agent"]
    assert sec_user_agent() == smod.DEFAULT_USER_AGENT


def test_sec_tickers_fallback_search_when_blocked(tmp_path):
    search = json.dumps({"hits": {"hits": [
        {"_id": "9999999", "_source": {"entity": "SIMULADA DELTA (SDLT)", "tickers": "SDLT"}},
    ]}}).encode()
    decoy = json.dumps({"hits": {"hits": [
        {"_id": "1", "_source": {"entity": "OUTRA (OUTRO)", "tickers": "OUTRO"}},
    ]}}).encode()
    http = FakeHttp({
        SEC_TICKERS_URL: HttpError(403, SEC_TICKERS_URL),
        smod.SEC_SEARCH_URL.format(query="SDLT"): search,
        smod.SEC_SEARCH_URL.format(query="SALFA"): decoy,
    })
    lim, _ = fake_limiter()
    t = fetch_sec_company_tickers(http_get=http, cache_dir=tmp_path, limiter=lim,
                                  fallback_tickers=["SDLT", "SALFA"])
    assert t["ticker"].tolist() == ["SDLT"]  # só correspondência exata
    assert t["cik"].tolist() == [DELTA_CIK]
    with pytest.raises(HttpError):
        fetch_sec_company_tickers(http_get=http, cache_dir=tmp_path / "x", limiter=lim)
    assert search_sec_ciks([], http_get=http, limiter=lim).empty


# ----------------------------------------------------------------------------
# Pipeline completo (offline) + persistência
# ----------------------------------------------------------------------------

def test_build_pit_fundamentals_end_to_end(tmp_path):
    uni = make_universe()
    http = FakeHttp(all_routes())
    lim, sleeps = fake_limiter()
    pit = build_pit_fundamentals(uni, date(2025, 1, 1), date(2025, 10, 3), http_get=http,
                                 cache_root=tmp_path, limiter=lim, today=date(2025, 10, 3))
    validate_pit(pit)
    assert list(pit.columns) == PIT_COLUMNS
    cov = pit_coverage(pit)
    assert set(cov.index) == {"SIM_ALFA", "SIM_BETA", "SIM_GAMA", "SIM_DELTA"}
    assert pit.attrs["issuers_without_data"] == ["SIM_EPS"]
    assert (pit["available_date"] <= pd.Timestamp("2025-10-03")).all()
    assert set(pit.loc[pit["issuer_id"] == "SIM_DELTA", "source"].str[:4]) == {"sec:"}
    assert set(pit.loc[pit["issuer_id"] == "SIM_ALFA", "source"].str[:4]) == {"cvm:"}
    sec_calls = [c for c in http.calls if "sec.gov" in c[0]]
    assert sec_calls and all("User-Agent" in h for _, h in sec_calls)
    assert len(sleeps) == len(sec_calls) - 1  # throttle entre chamadas da SEC
    assert (tmp_path / "cvm" / "itr_cia_aberta_2025.zip").exists()
    assert (tmp_path / "sec" / f"companyfacts_CIK{DELTA_CIK}.json").exists()
    # segunda execução: tudo do cache (zero chamadas)
    http2 = FakeHttp({})
    pit2 = build_pit_fundamentals(uni, date(2025, 1, 1), date(2025, 10, 3), http_get=http2,
                                  cache_root=tmp_path, limiter=lim, today=date(2025, 10, 3))
    assert http2.calls == []
    pd.testing.assert_frame_equal(pit, pit2)
    # janela que termina antes da reapresentação não a contém (sem look-ahead)
    pit_early = build_pit_fundamentals(uni, date(2025, 1, 1), date(2025, 9, 1), http_get=http2,
                                       cache_root=tmp_path, limiter=lim,
                                       today=date(2025, 10, 3))
    assert pit_early["available_date"].max() <= pd.Timestamp("2025-09-01")
    assert snap_value(pit_early, "SIM_ALFA", "revenue_ttm", date(2025, 9, 1))[0] == 1080 * K


def test_local_equivalent_prices_and_ratio_integration():
    uni = make_universe()
    lm = build_line_master(uni, parse_fca_zip(fca_zip()),
                           parse_sec_company_tickers(SEC_TICKERS_JSON))
    idx = pd.to_datetime(["2025-09-01", "2025-09-02"])
    close = pd.DataFrame({"ALFA3.SA": [10.0, np.nan], "ALFA11.SA": [30.0, 31.5],
                          "SALFA": [3.8, 3.9], "SDLT": [10.0, 11.0]}, index=idx)
    fx = pd.DataFrame({"BRL": [0.19, 0.20], "MXN": [0.05, 0.05], "USD": [1.0, 1.0]}, index=idx)
    px = local_equivalent_prices(close, fx, lm, {"SIM_ALFA": "BRL", "SIM_DELTA": "MXN",
                                                 "SIM_EPS": "BRL"})
    # ALFA: linha ON local (mesma moeda, não unit) — sem preenchimento entre linhas
    assert px.loc["2025-09-01", "SIM_ALFA"] == 10.0
    assert math.isnan(px.loc["2025-09-02", "SIM_ALFA"])
    # DELTA: só ADR com preço ⇒ USD / razão 5 × (USD/MXN)
    assert px.loc["2025-09-01", "SIM_DELTA"] == pytest.approx(10.0 / 5 * 1.0 / 0.05)
    assert px["SIM_EPS"].isna().all()
    # unit: preço ÷ ações por unit quando é a única linha
    lm2 = lm.drop(index=["ALFA3.SA"])
    px2 = local_equivalent_prices(close, fx, lm2, {"SIM_ALFA": "BRL"})
    assert px2.loc["2025-09-02", "SIM_ALFA"] == pytest.approx(31.5 / 3)


def test_save_load_roundtrip_and_validation(tmp_path, cvm_pit):
    path = save_pit(cvm_pit, tmp_path / "pit.parquet")
    back = load_pit(path)
    pd.testing.assert_frame_equal(back.reset_index(drop=True), cvm_pit.reset_index(drop=True))
    bad = cvm_pit.copy()
    bad.loc[0, "value"] = np.nan
    with pytest.raises(ValueError, match="ausentes"):
        save_pit(bad, tmp_path / "bad.parquet")
    bad2 = cvm_pit.copy()
    bad2.loc[0, "available_date"] = pd.Timestamp("2000-01-01")
    with pytest.raises(ValueError, match="look-ahead"):
        validate_pit(bad2)
    bad3 = cvm_pit.copy()
    bad3.loc[0, "metric"] = "ev_ebitda"
    with pytest.raises(ValueError, match="desconhecidas"):
        validate_pit(bad3)


def test_add_business_days():
    assert add_business_days(date(2025, 3, 7), 1) == pd.Timestamp("2025-03-10")  # sex → seg
    s = add_business_days(pd.Series(pd.to_datetime(["2025-05-08", None])), 1)
    assert s.iloc[0] == pd.Timestamp("2025-05-09") and pd.isna(s.iloc[1])
    assert add_business_days(date(2025, 3, 8), 0) == pd.Timestamp("2025-03-08")
