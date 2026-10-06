"""Tabelas públicas SIMULADAS para a demonstração e os testes (mesmo esquema da camada A1).

Determinístico (fluxo RNG próprio ``default_rng([seed, 4101])``, que não altera nenhum número
sintético existente) e coerente com o mercado sintético (``make_synthetic_market``): o valor de
mercado, P/L, P/VPA, margens e alavancagem do retrato sintético geram demonstrativos anuais e
TTM, consenso, dividendos, composição de ETFs, eventos, taxas e free float. Toda linha leva
``fonte="SIMULADO"`` e o documento "DADOS SIMULADOS".

Defeitos deliberados (exercitam os portões de qualidade): um emissor sem demonstrativos, um com
patrimônio negativo, um ADR com consenso de LPA na moeda local (descasamento de moeda) e um
preço-alvo de consenso por unidade errada (armadilha tipo KLBN4). Capital social "oficial"
simulado para os emissores brasileiros (contagem conciliada em três fontes, portão G13c).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..market import MarketData
from .fontes import (
    COLS_CAPITAL,
    COLS_CONSENSO,
    COLS_DEMONSTRATIVOS,
    COLS_DIVIDENDOS,
    COLS_ETF,
    COLS_EVENTOS,
    COLS_FLOAT,
    COLS_TAXAS,
    DadosPublicos,
)

DOC = "DADOS SIMULADOS"
FONTE = "SIMULADO"
_STREAM = 4101


def _num(x: object, default: float = np.nan) -> float:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return v if np.isfinite(v) else default


def _last(md: MarketData, tkr: str, as_of: date) -> float:
    if tkr not in md.close.columns:
        return np.nan
    s = md.close[tkr].loc[:pd.Timestamp(as_of)].dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def _fx(md: MarketData, ccy: str, as_of: date) -> float:
    if ccy == "USD":
        return 1.0
    if ccy not in md.fx.columns:
        return np.nan
    s = md.fx[ccy].loc[:pd.Timestamp(as_of)].dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def _quarter_ends(as_of: date, n: int, lag_days: int = 45) -> list[date]:
    """Últimos ``n`` fins de trimestre publicados até ``as_of`` (defasagem ``lag_days``)."""
    out: list[date] = []
    y, q = as_of.year, (as_of.month - 1) // 3 + 1
    while len(out) < n:
        q -= 1
        if q == 0:
            q, y = 4, y - 1
        end = date(y, 3 * q, {3: 31, 6: 30, 9: 30, 12: 31}[3 * q])
        if end + timedelta(days=lag_days) <= as_of:
            out.append(end)
    return sorted(out)


def dados_sinteticos(md: MarketData, as_of: date, issuer_ids: Sequence[str],
                     tickers: Sequence[str], etfs: Sequence[str], *, seed: int = 7) -> DadosPublicos:
    rng = np.random.default_rng([seed, _STREAM])
    uni = md.universe
    fund = md.fundamentals
    ids = [i for i in uni.issuers.index if i in set(issuer_ids)]
    all_ids = list(uni.issuers.index)
    sem_dem = all_ids[3] if len(all_ids) > 3 else None
    pl_neg = all_ids[8] if len(all_ids) > 8 else None
    adr_ids = [i for i in all_ids if uni.issuers.loc[i, "primary_line_type"] == "ADR"]
    adr_ruim = adr_ids[0] if adr_ids else None
    unidade_ruim = all_ids[10] if len(all_ids) > 10 else None

    qends = _quarter_ends(as_of, 8)
    anos = [y for y in range(as_of.year - 7, as_of.year) if date(y + 1, 3, 25) <= as_of][-5:]
    dem_rows: list[dict] = []
    con_rows: list[dict] = []
    div_rows: list[dict] = []
    eve_rows: list[dict] = []
    ff_rows: list[dict] = []
    cap_rows: list[dict] = []
    stmt: dict[str, dict[str, float]] = {}

    for iid in all_ids:
        lines = uni.lines_for(iid)
        prim = str(uni.issuers.loc[iid, "primary_ticker"])
        sector = str(uni.issuers.loc[iid, "gics_sector"])
        # linha na moeda das demonstrações (a local, quando há)
        fin_ccy = str(fund.loc[prim, "financial_currency"]) if prim in fund.index else "USD"
        cand = [t for t in lines.index if lines.loc[t, "currency"] == fin_ccy]
        ref = cand[0] if cand else prim
        f = fund.loc[ref] if ref in fund.index else fund.loc[prim]
        px = _last(md, ref, as_of)
        mcap_line = _num(f.get("market_cap"))
        line_ccy = str(lines.loc[ref, "currency"])
        mcap = mcap_line * _fx(md, line_ccy, as_of) / _fx(md, fin_ccy, as_of)
        shares = mcap_line / px if px and np.isfinite(px) else np.nan
        pe = max(_num(f.get("trailing_pe"), 12.0), 3.0)
        pb = max(_num(f.get("price_to_book"), 1.5), 0.3)
        pm = max(_num(f.get("profit_margins"), 0.08), 0.03)
        om = max(_num(f.get("operating_margins"), 0.12), 0.03)
        de = max(_num(f.get("debt_to_equity"), 60.0), 0.0) / 100.0
        dy = max(_num(f.get("dividend_yield"), 0.03), 0.0)
        g = float(np.clip(_num(f.get("revenue_growth"), 0.06), -0.1, 0.25))
        lucro = mcap / pe
        pl = mcap / pb
        if iid == pl_neg:
            pl = -0.15 * mcap
        banco = sector == "Financials"
        receita = lucro / pm
        base = {
            "lucro_liquido_controladores": lucro, "lucro_liquido": lucro * 1.03,
            "patrimonio_controladores": pl, "participacao_minoritarios": abs(pl) * 0.03,
            "patrimonio_liquido": pl + abs(pl) * 0.03, "lucro_antes_ir": lucro / 0.7,
            "ir_csll": -(lucro / 0.7 - lucro * 1.03), "dividendos_pagos": dy * mcap,
            "acoes_em_circulacao": shares, "acoes_emitidas": shares * 1.01,
            "acoes_tesouraria": shares * 0.01,
        }
        if banco:
            cart = abs(pl) * 6.0
            mf = cart * 0.08
            base.update({"carteira_credito": cart, "margem_financeira": mf,
                         "despesa_pdd": -cart * 0.02, "receita_servicos": mf * 0.3,
                         "provisao_credito": cart * 0.05, "ativo_total": abs(pl) * 10.0,
                         "receita": mf * 1.3})
        else:
            d_a = receita * 0.05
            divida = abs(pl) * de
            base.update({"receita": receita, "ebit": receita * om, "d_a": d_a,
                         "ebitda": receita * om + d_a, "capex": d_a * 1.2,
                         "cfo": lucro + d_a, "fcf": lucro + d_a - d_a * 1.2,
                         "divida_bruta": divida, "caixa": divida * 0.3,
                         "aplicacoes_cp": divida * 0.1, "arrendamentos": receita * 0.02,
                         "divida_liquida": divida * 0.6 + receita * 0.02,
                         "ativo_total": abs(pl) * 2.5 + divida, "resultado_financeiro": -divida * 0.08})
        stmt[iid] = base
        if str(uni.issuers.loc[iid, "country"]) == "BR" and np.isfinite(shares):
            cap_rows.append(dict(issuer_id=iid, cnpj=None, data_ref=f"{as_of.year}-12-31", versao=1,
                                 data_publicacao=(as_of - timedelta(days=60)).isoformat(),
                                 tipo_capital="Capital Integralizado", data_aprovacao=None, qtd_ordinarias=shares * 1.01,
                                 qtd_preferenciais=0.0, qtd_total=shares * 1.01, url=None, sha256=None))
        if iid == sem_dem or iid not in ids:
            pass
        else:
            stocks = {"patrimonio_controladores", "participacao_minoritarios", "patrimonio_liquido",
                      "acoes_em_circulacao", "acoes_emitidas", "acoes_tesouraria", "carteira_credito",
                      "provisao_credito", "ativo_total", "divida_bruta", "caixa", "aplicacoes_cp",
                      "arrendamentos", "divida_liquida"}
            dem_name = {"cfo": "DFC", "capex": "DFC", "fcf": "DFC", "dividendos_pagos": "DFC",
                        "d_a": "DFC"}
            # trimestres: TTM (fluxos) e BP (estoques); 8 trimestres para o crescimento TTM
            for k, qe in enumerate(qends):
                fator = (1 + g) ** ((k - (len(qends) - 1)) / 4.0)
                pub = qe + timedelta(days=45)
                for item, v in base.items():
                    if item in stocks:
                        dem, freq, val = "BP", "Q", v * (fator if item != "acoes_em_circulacao" else 1.0)
                    else:
                        dem, freq, val = dem_name.get(item, "DRE"), "TTM", v * fator
                    dem_rows.append(dict(issuer_id=iid, demonstrativo=dem, freq=freq, period_end=qe,
                                         item=item, value=float(val), currency=fin_ccy, escala=1,
                                         consolidado=True, fonte=FONTE, url=None, documento=DOC,
                                         data_publicacao=pub, sha256=None))
            # exercícios anuais (histórico de margens e ROE)
            for ano in anos:
                fator = (1 + g) ** (ano - (anos[-1] + 0.5)) * float(rng.normal(1.0, 0.08))
                pub = date(ano + 1, 3, 25)
                if pub > as_of:
                    continue
                for item in ("receita", "ebit", "lucro_liquido_controladores", "patrimonio_controladores",
                             "d_a", "capex", "acoes_em_circulacao"):
                    if item not in base:
                        continue
                    val = base[item] * (fator if item != "acoes_em_circulacao" else 1.0)
                    if item == "ebit":
                        val = base["receita"] * fator * float(np.clip(om + rng.normal(0, 0.03), 0.01, 0.6))
                    dem_rows.append(dict(issuer_id=iid, demonstrativo="BP" if item.startswith(("patrim", "acoes")) else "DRE",
                                         freq="A", period_end=date(ano, 12, 31), item=item,
                                         value=float(val), currency=fin_ccy, escala=1, consolidado=True,
                                         fonte=FONTE, url=None, documento=DOC, data_publicacao=pub,
                                         sha256=None))
        # consenso por linha
        eg = float(np.clip(_num(f.get("earnings_growth"), 0.08), -0.3, 0.4))
        for tkr, ln in lines.iterrows():
            ft = fund.loc[tkr] if tkr in fund.index else f
            ptk = _last(md, tkr, as_of)
            fpe = max(_num(ft.get("forward_pe"), pe), 3.0)
            eps1 = ptk / fpe if np.isfinite(ptk) else np.nan
            m_est = str(ln["currency"])
            if iid == adr_ruim and ln["line_type"] == "ADR":
                eps1 = eps1 / _fx(md, fin_ccy, as_of)  # LPA na moeda do balanço num ADR (como no Yahoo)
                m_est = fin_ccy
            alvo = _num(ft.get("target_mean_price"))
            if iid == unidade_ruim and ln["line_type"] == "LOCAL":
                alvo = alvo * 6.7  # preço-alvo por unidade errada (defeito)
            con_rows.append(dict(
                ticker=tkr, eps_fy1=eps1, eps_fy2=eps1 * (1 + eg), receita_fy1=receita * (1 + g),
                receita_fy2=receita * (1 + g) ** 2, n_analistas_eps=int(_num(ft.get("number_of_analyst_opinions"), 5)),
                alvo_medio=alvo, alvo_mediano=alvo, alvo_alto=alvo * 1.25, alvo_baixo=alvo * 0.75,
                n_analistas_alvo=int(_num(ft.get("number_of_analyst_opinions"), 5)),
                recomendacao_media=_num(ft.get("recommendation_mean")), fonte=FONTE,
                data_coleta=pd.Timestamp(as_of).tz_localize("UTC"), moeda_cotacao=str(ln["currency"]),
                moeda_estimativas=m_est))
            # dividendos trimestrais dos últimos 2 anos
            if np.isfinite(ptk) and dy > 0:
                for k in range(8):
                    dex = as_of - timedelta(days=45 + 91 * k)
                    p_ex = _last(md, tkr, dex)
                    if np.isfinite(p_ex):
                        div_rows.append(dict(ticker=tkr, data_ex=dex, valor_por_acao=dy * p_ex / 4.0,
                                             moeda=ln["currency"], fonte=FONTE))
        ned = f.get("next_earnings_date")
        if isinstance(ned, str) and ned:
            eve_rows.append(dict(issuer_id=iid, data=date.fromisoformat(ned[:10]), tipo="resultado",
                                 estimada=bool(iid == all_ids[0]), fonte=FONTE, url=None))
        fs, so = _num(f.get("float_shares")), _num(f.get("shares_outstanding"))
        if np.isfinite(fs) and np.isfinite(so) and so > 0:
            ff_rows.append(dict(issuer_id=iid, free_float_pct=min(fs / so, 1.0), fonte=FONTE,
                                data_ref=as_of))

    # ETFs: pesos por valor de mercado (mesma lógica do benchmark sintético)
    mcap_usd = {}
    for iid in all_ids:
        prim = str(uni.issuers.loc[iid, "primary_ticker"])
        if prim in fund.index:
            ccy = str(uni.lines.loc[prim, "currency"])
            mcap_usd[iid] = _num(fund.loc[prim, "market_cap"]) * _fx(md, ccy, as_of)
    comp: dict[str, pd.DataFrame | None] = {}
    filtros = {"ILF": None, "EWZ": "BR", "EWW": "MX", "ECH": "CL"}
    for etf in etfs:
        pais = filtros.get(etf, "?")
        if etf not in filtros:
            comp[etf] = None
            continue
        cands = [i for i in all_ids if (pais is None or uni.issuers.loc[i, "country"] == pais)
                 and np.isfinite(mcap_usd.get(i, np.nan))]
        cands = sorted(cands, key=lambda i: -mcap_usd[i])[:40]
        if not cands:
            comp[etf] = None
            continue
        tot = sum(mcap_usd[i] for i in cands)
        rows = []
        for i in cands:
            rows.append(dict(ticker_bruto=str(uni.issuers.loc[i, "primary_ticker"]).split(".")[0],
                             nome=str(uni.issuers.loc[i, "issuer_name"]),
                             peso=0.975 * mcap_usd[i] / tot, setor=str(uni.issuers.loc[i, "gics_sector"]),
                             pais=str(uni.issuers.loc[i, "country"]), issuer_id=i, fonte=FONTE,
                             url=None, data_ref=as_of, sha256=None))
        rows.append(dict(ticker_bruto="XSIM", nome="Ativo simulado sem mapeamento", peso=0.015,
                         setor="Industrials", pais=pais or "BR", issuer_id=None, fonte=FONTE, url=None,
                         data_ref=as_of, sha256=None))
        rows.append(dict(ticker_bruto="USD", nome="Caixa em dólar", peso=0.010, setor="Caixa",
                         pais="US", issuer_id=None, fonte=FONTE, url=None, data_ref=as_of, sha256=None))
        comp[etf] = pd.DataFrame(rows, columns=COLS_ETF)

    tax_rows = []
    for k in range(10):
        d = as_of - timedelta(days=k)
        tax_rows.append(dict(serie="USD_10Y", data=d, valor=0.045, fonte=FONTE))
    sel = md.rates["SELIC"].loc[:pd.Timestamp(as_of)].dropna() if "SELIC" in md.rates else pd.Series(dtype=float)
    if len(sel):
        tax_rows.append(dict(serie="SELIC", data=sel.index[-1].date(), valor=float(sel.iloc[-1]), fonte=FONTE))

    tick = set(tickers)
    con = pd.DataFrame(con_rows, columns=COLS_CONSENSO)
    con = con[con["ticker"].isin(tick)].reset_index(drop=True)
    div = pd.DataFrame(div_rows, columns=COLS_DIVIDENDOS)
    div = div[div["ticker"].isin(tick)].reset_index(drop=True)
    return DadosPublicos(
        demonstrativos=pd.DataFrame(dem_rows, columns=COLS_DEMONSTRATIVOS),
        consenso=con, dividendos=div,
        eventos=pd.DataFrame(eve_rows, columns=COLS_EVENTOS),
        taxas=pd.DataFrame(tax_rows, columns=COLS_TAXAS),
        free_float=pd.DataFrame(ff_rows, columns=COLS_FLOAT),
        etfs=comp, origem=FONTE, raiz=None,
        capital_oficial=pd.DataFrame(cap_rows, columns=COLS_CAPITAL))


__all__ = ["dados_sinteticos"]
