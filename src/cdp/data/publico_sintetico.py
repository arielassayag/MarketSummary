"""Arquivo público SIMULADO (DADOS SIMULADOS) para a demonstração e os testes offline.

:func:`gerar_arquivo_sintetico` grava, num ``root`` de demonstração, pacotes ``SIMULADO/*.json``
coerentes com um :class:`~cdp.market.MarketData` sintético (valor de mercado, P/L, P/VPA,
margens e crescimento do próprio gerador): demonstrações anuais/trimestrais/TTM, consenso,
proventos, eventos, free float, taxas e carteiras de ETFs (ILF/EWZ/EWW). As funções de
:mod:`.publico` com ``offline=True`` leem esses pacotes quando presentes (fonte ``SIMULADO``);
nunca em modo online. Sorteios em fluxo próprio (``default_rng([seed, 41])``): nenhum número do
mercado sintético existente muda.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..market import MarketData
from .publico_arquivo import Arquivo

AVISO = "DADOS SIMULADOS — arquivo público sintético gerado por código; não representa dados reais."
PACOTES = ("demonstrativos", "consenso", "dividendos", "eventos", "free_float", "taxas",
           "etf_ILF", "etf_EWZ", "etf_EWW")


def _iso(v):
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(v).date().isoformat()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (np.floating, np.integer)):
        return _iso(v.item())
    return v


def _bytes(linhas: list[dict]) -> bytes:
    obj = {"aviso": AVISO, "linhas": [{k: _iso(v) for k, v in r.items()} for r in linhas]}
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode()


def _clip(x: float, lo: float, hi: float, default: float) -> float:
    return float(np.clip(x, lo, hi)) if x is not None and math.isfinite(float(x)) else default


def _fim_trimestre(d: date) -> date:
    m = ((d.month - 1) // 3) * 3 + 3
    nxt = date(d.year + (m == 12), 1 if m == 12 else m + 1, 1)
    return nxt - timedelta(days=1)


def _dem_fluxo(item: str) -> str:
    return "DFC" if item in ("cfo", "capex", "fcf", "dividendos_pagos", "recompras") else "DRE"


def _linha(dem: list, base: dict, as_of: date, item: str, freq: str, fim: date, valor: float,
           demonstrativo: str) -> None:
    pub = fim + timedelta(days=75 if freq == "A" else 45)
    if pub > as_of:
        return
    dem.append({**base, "demonstrativo": demonstrativo, "freq": freq, "period_end": fim,
                "item": item, "value": float(valor), "data_publicacao": pub})


def _fluxos(p: dict, escala: float) -> dict[str, float]:
    r = p["rec_ttm"] * escala
    ll = r * p["pm"]
    if p["fin"]:
        cart = p["pl"] * 6.0 * escala
        return {"receita": r, "lucro_liquido": ll, "lucro_liquido_controladores": ll * 0.97,
                "margem_financeira": cart * 0.08, "despesa_pdd": -cart * 0.02,
                "receita_servicos": cart * 0.024, "lucro_antes_ir": ll / 0.7,
                "ir_csll": -(ll / 0.7) * 0.3, "dividendos_pagos": ll * 0.45, "cfo": ll * 1.3}
    ebit = r * p["om"]
    da = r * 0.05
    return {"receita": r, "lucro_bruto": r * min(0.9, p["om"] + 0.2), "ebit": ebit, "d_a": da,
            "ebitda": ebit + da, "resultado_financeiro": -(p["pl"] * p["de"]) * 0.08 * escala,
            "lucro_antes_ir": ll / 0.72, "ir_csll": -(ll / 0.72) * 0.28, "lucro_liquido": ll,
            "lucro_liquido_controladores": ll * 0.97, "cfo": (ll + da) * 1.05,
            "capex": r * 0.06, "fcf": (ll + da) * 1.05 - r * 0.06,
            "dividendos_pagos": ll * 0.45, "recompras": ll * 0.05}


def _saldos(p: dict, escala: float) -> dict[str, float]:
    e = p["pl"] * escala
    a = p["acoes"]
    s = {"patrimonio_liquido": e * 1.03, "patrimonio_controladores": e,
         "participacao_minoritarios": e * 0.03, "acoes_em_circulacao": a,
         "acoes_emitidas": a * 1.01, "acoes_tesouraria": a * 0.01}
    if p["fin"]:
        s.update({"ativo_total": e * 10.0, "carteira_credito": e * 6.0,
                  "provisao_credito": e * 0.3})
    else:
        div = e * p["de"]
        s.update({"ativo_total": e * (1 + p["de"]) * 1.4, "divida_bruta": div,
                  "caixa": div * 0.3, "aplicacoes_cp": div * 0.05, "divida_liquida": div * 0.65,
                  "arrendamentos": div * 0.1})
    return s


def gerar_arquivo_sintetico(root: str | Path, md: MarketData, *, seed: int = 41,
                            as_of: date | None = None) -> dict[str, str]:
    """Grava os pacotes ``SIMULADO`` em ``<root>/publico`` e devolve ``{pacote: sha256}``."""
    if not md.is_synthetic:
        raise ValueError("gerar_arquivo_sintetico exige um MarketData sintético (DADOS SIMULADOS).")
    as_of = as_of or md.as_of
    rng = np.random.default_rng([int(seed), 41])
    uni = md.universe
    f = md.fundamentals
    coleta = datetime(as_of.year, as_of.month, as_of.day, 23, 0, tzinfo=UTC)
    arq = Arquivo(root)
    reais = [k for k in arq.chaves() if not k.startswith("SIMULADO/")]
    if reais:
        # nunca misturar DADOS SIMULADOS num arquivo de fontes reais (ex.: ``data/``)
        raise ValueError("gerar_arquivo_sintetico recusado: o arquivo em "
                         f"{arq.base} contém fontes reais ({reais[0]}, …).")
    dem, cons, divs, evs, ffs = [], [], [], [], []
    ult_tri = _fim_trimestre(as_of - timedelta(days=60))
    for iid, iss in uni.issuers.iterrows():
        prim = str(iss["primary_ticker"])
        locais = uni.lines_for(iid)
        loc = locais[locais["line_type"] == "LOCAL"]
        ref = str(loc.index[0]) if not loc.empty else prim
        fr = f.loc[ref] if ref in f.index else None
        if fr is None:
            continue
        moeda = str(fr.get("financial_currency") or uni.lines.loc[ref, "currency"])
        mcap = float(fr["market_cap"])
        if uni.lines.loc[ref, "currency"] != moeda:
            continue
        pe = _clip(fr.get("trailing_pe"), 3, 40, 11.0)
        pb = _clip(fr.get("price_to_book"), 0.3, 8, 1.5)
        pm = _clip(fr.get("profit_margins"), 0.03, 0.30, 0.10)
        om = max(pm * 1.5, _clip(fr.get("operating_margins"), 0.05, 0.45, 0.15))
        g = _clip(fr.get("revenue_growth"), -0.05, 0.25, 0.08)
        de = _clip(fr.get("debt_to_equity"), 0, 300, 80.0) / 100.0
        acoes = float(fr["shares_outstanding"])
        fin = iss["gics_sector"] == "Financials"
        ll_ttm = mcap / pe
        pl = mcap / pb
        rec_ttm = ll_ttm / pm
        anos = [as_of.year - k for k in range(4, 0, -1)]
        base = {"issuer_id": iid, "currency": moeda, "escala": 1, "consolidado": True,
                "fonte": "SIMULADO", "url": None, "documento": "DADOS SIMULADOS",
                "pit_estimado": False, "nota": AVISO}

        prm = {"rec_ttm": rec_ttm, "pm": pm, "om": om, "pl": pl, "de": de, "acoes": acoes,
               "fin": bool(fin)}
        for k, ano in enumerate(anos):
            fator = (1 + g) ** (k - len(anos) + 1)
            fim = date(ano, 12, 31)
            for item, v in _fluxos(prm, fator).items():
                _linha(dem, base, as_of, item, "A", fim, v, _dem_fluxo(item))
            for item, v in _saldos(prm, fator).items():
                _linha(dem, base, as_of, item, "A", fim, v, "BP")
        tri = ult_tri
        for _ in range(6):
            fator = (1 + g) ** (-(ult_tri - tri).days / 365.0) * (1 + rng.normal(0, 0.03))
            for item, v in _fluxos(prm, fator).items():
                _linha(dem, base, as_of, item, "Q", tri, v / 4.0, _dem_fluxo(item))
                _linha(dem, base, as_of, item, "TTM", tri, v, _dem_fluxo(item))
            for item, v in _saldos(prm, fator).items():
                _linha(dem, base, as_of, item, "Q", tri, v, "BP")
            tri = _fim_trimestre(tri - timedelta(days=95))
        ff = float(fr.get("float_shares", math.nan)) / acoes if acoes > 0 else math.nan
        ffs.append({"issuer_id": iid, "free_float_pct": ff if 0 < ff <= 1 else math.nan,
                    "fonte": "SIMULADO", "data_ref": as_of, "url": None, "sha256": None,
                    "detalhe": AVISO})
        prox = fr.get("next_earnings_date")
        try:
            d_res = date.fromisoformat(str(prox)[:10])
            estimada = False
        except ValueError:
            d_res = as_of + timedelta(days=30)
            estimada = True
        evs.append({"issuer_id": iid, "data": d_res, "tipo": "resultado", "estimada": estimada,
                    "fonte": "SIMULADO", "url": None, "documento": AVISO,
                    "janela_inicio": d_res - timedelta(days=7 if estimada else 0),
                    "janela_fim": d_res + timedelta(days=7 if estimada else 0)})
    # consenso e proventos por linha
    for t, ln in uni.lines.iterrows():
        if t not in f.index:
            continue
        fr = f.loc[t]
        px = float(md.close[t].dropna().iloc[-1]) if t in md.close and md.close[t].notna().any() \
            else math.nan
        eps0 = float(fr.get("trailing_eps", math.nan))
        g = _clip(fr.get("earnings_growth"), -0.2, 0.4, 0.08)
        alvo = float(fr.get("target_mean_price", math.nan))
        n = float(fr.get("number_of_analyst_opinions", math.nan))
        cons.append({"ticker": t, "eps_fy1": eps0 * (1 + g), "eps_fy2": eps0 * (1 + g) ** 2,
                     "receita_fy1": math.nan, "receita_fy2": math.nan, "n_analistas_eps": n,
                     "alvo_medio": alvo, "alvo_mediano": alvo,
                     "alvo_alto": alvo * 1.25 if math.isfinite(alvo) else math.nan,
                     "alvo_baixo": alvo * 0.8 if math.isfinite(alvo) else math.nan,
                     "n_analistas_alvo": n,
                     "recomendacao_media": float(fr.get("recommendation_mean", math.nan)),
                     "fonte": "SIMULADO", "data_coleta": coleta.isoformat(),
                     "moeda_cotacao": ln["currency"], "moeda_estimativas": ln["currency"],
                     "preco_referencia_yahoo": px, "url": None, "sha256": None})
        dy = _clip(fr.get("dividend_yield"), 0, 0.15, 0.04)
        if math.isfinite(px):
            for ano in (as_of.year - 1, as_of.year):
                for mes in (5, 11):
                    d = date(ano, mes, 15)
                    if d <= as_of:
                        divs.append({"ticker": t, "data_ex": d, "valor_por_acao": px * dy / 2,
                                     "moeda": ln["currency"], "fonte": "SIMULADO", "url": None,
                                     "sha256": None})
    # taxas
    taxas = []
    for k in range(0, 3 * 365, 7):
        d = as_of - timedelta(days=k)
        for serie, v in (("USD_10Y", 0.045), ("SELIC_META", 0.1375), ("IPCA_12M", 0.045)):
            taxas.append({"serie": serie, "data": d, "valor": v, "fonte": "SIMULADO",
                          "url": None, "sha256": None})
    for ano in range(as_of.year, as_of.year + 5):
        for nome, v in (("IPCA", 0.04), ("SELIC", 0.12), ("CAMBIO", 5.3), ("PIB", 0.02)):
            taxas.append({"serie": f"FOCUS_{nome}_{ano}", "data": as_of, "valor": v,
                          "fonte": "SIMULADO", "url": None, "sha256": None})
    # ETFs (pesos por valor de mercado em USD)
    etfs: dict[str, list[dict]] = {}
    mcap_usd = {}
    for iid in uni.issuers.index:
        t = str(uni.issuers.loc[iid, "primary_ticker"])
        if t in f.index:
            ccy = str(uni.lines.loc[t, "currency"])
            fxv = float(md.fx[ccy].dropna().iloc[-1]) if ccy in md.fx else 1.0
            mcap_usd[iid] = float(f.loc[t, "market_cap"]) * fxv
    for etf, paises in (("ILF", None), ("EWZ", {"BR"}), ("EWW", {"MX"})):
        sel = {i: v for i, v in mcap_usd.items()
               if paises is None or uni.issuers.loc[i, "country"] in paises}
        tot = sum(sel.values())
        etfs[etf] = [{"ticker_bruto": str(uni.issuers.loc[i, "primary_ticker"]),
                      "nome": str(uni.issuers.loc[i, "issuer_name"]), "peso": v / tot,
                      "setor": str(uni.issuers.loc[i, "gics_sector"]),
                      "pais": str(uni.issuers.loc[i, "country"]), "issuer_id": i,
                      "fonte": "SIMULADO", "url": None, "data_ref": as_of, "sha256": None,
                      "classe_ativo": "Equity",
                      "yahoo_ticker": str(uni.issuers.loc[i, "primary_ticker"]),
                      "valor_mercado": v, "valor_nocional": None, "sedol": None}
                     for i, v in sorted(sel.items())]
    pacotes = {"demonstrativos": dem, "consenso": cons, "dividendos": divs, "eventos": evs,
               "free_float": ffs, "taxas": taxas, **{f"etf_{k}": v for k, v in etfs.items()}}
    out = {}
    for nome, linhas in pacotes.items():
        reg = arq.gravar(f"SIMULADO/pacotes/{nome}.json", "SIMULADO", None, _bytes(linhas),
                         data_coleta=coleta)
        out[nome] = reg.sha256
    return out


def ler_pacote(arq: Arquivo, nome: str, ate: date) -> tuple[str, list[dict]] | None:
    """``(sha256, linhas)`` do pacote SIMULADO arquivado até ``ate`` (ou ``None``)."""
    reg = arq.buscar(f"SIMULADO/pacotes/{nome}.json", ate)
    if reg is None:
        return None
    obj = json.loads(arq.ler(reg))
    if obj.get("aviso") != AVISO:
        raise ValueError("Pacote SIMULADO sem o aviso de dados simulados.")
    return reg.sha256, list(obj.get("linhas") or [])


__all__ = ["AVISO", "PACOTES", "gerar_arquivo_sintetico", "ler_pacote"]
