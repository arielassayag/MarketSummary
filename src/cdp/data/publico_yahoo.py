"""Yahoo Finance (yfinance) como fonte pública: consenso, proventos, calendário, demonstrações.

Cada resposta é serializada em JSON canônico (chaves ordenadas, ``NaN`` ⇒ ``null``) e arquivada
como arquivo bruto (``YAHOO/<parte>/<ticker>.json``), de modo que a leitura offline reproduz
exatamente a coleta. Partes:

- ``info``: subconjunto de ``Ticker.info`` (moedas, alvo e recomendação médios, ações, float,
  datas de resultado/provento);
- ``estimativas``: ``earnings_estimate``, ``revenue_estimate``, ``analyst_price_targets``;
- ``demonstracoes``: DRE/BP/DFC anuais e trimestrais (agregação do Yahoo; sem data de
  publicação ⇒ data estimada = fim do período + defasagem regulatória, limitada à coleta);
- ``dividendos``: ``Ticker.dividends`` (data-ex, valor por ação na moeda de cotação);
- ``calendario``: ``Ticker.calendar`` e ``get_earnings_dates`` (datas passadas e futuras).

Rotulado sempre como "consenso público Yahoo Finance". Valores ausentes ⇒ ``null``/``NaN``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from .publico_cvm import FATO_COLUNAS
from .yahoo import call_with_retry, to_float

PARTES = ("info", "estimativas", "demonstracoes", "dividendos", "calendario")
INFO_CAMPOS = (
    "currency", "financialCurrency", "quoteType", "shortName", "longName",
    "recommendationMean", "recommendationKey", "numberOfAnalystOpinions", "targetMeanPrice",
    "targetMedianPrice", "targetHighPrice", "targetLowPrice", "currentPrice",
    "regularMarketPrice", "previousClose", "sharesOutstanding", "floatShares",
    "impliedSharesOutstanding", "earningsTimestamp", "earningsTimestampStart",
    "earningsTimestampEnd", "isEarningsDateEstimate", "exDividendDate", "lastFiscalYearEnd",
    "mostRecentQuarter", "sector", "industry",
)
DEMONSTRACOES = {
    "income_stmt": ("DRE", "A"), "quarterly_income_stmt": ("DRE", "Q"),
    "balance_sheet": ("BP", "A"), "quarterly_balance_sheet": ("BP", "Q"),
    "cashflow": ("DFC", "A"), "quarterly_cashflow": ("DFC", "Q"),
}
DEFASAGEM_DIAS = {"A": 120, "Q": 60}
"""Defasagem máxima de publicação usada como data estimada (prazos regulatórios LatAm)."""

URL_QUOTE = "https://finance.yahoo.com/quote/{t}"


# ======================================================================
# Serialização canônica
# ======================================================================

def _limpo(v: Any) -> Any:
    if v is None or isinstance(v, bool | str):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(v).date().isoformat() if not isinstance(v, datetime) or \
            (v.hour == 0 and v.minute == 0) else pd.Timestamp(v).isoformat()
    if hasattr(v, "item"):
        return _limpo(v.item())
    if isinstance(v, Mapping):
        return {str(k): _limpo(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_limpo(x) for x in v]
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return str(v)


def _quadro(df: Any) -> dict | None:
    """DataFrame (linhas = rótulos, colunas = datas) ⇒ dict canônico."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    cols = [pd.Timestamp(c).date().isoformat() for c in df.columns]
    linhas = {str(idx): [_limpo(to_float(v)) for v in row]
              for idx, row in zip(df.index, df.to_numpy(), strict=True)}
    return {"colunas": cols, "linhas": dict(sorted(linhas.items()))}


def _tabela(df: Any) -> dict | None:
    """DataFrame genérico (índice = período, colunas = campos) ⇒ dict canônico."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    return {str(i): {str(c): _limpo(v) for c, v in row.items()}
            for i, row in df.iterrows()}


def serializar(obj: Mapping) -> bytes:
    return (json.dumps(_limpo(obj), ensure_ascii=False, sort_keys=True, indent=1)
            + "\n").encode("utf-8")


def ler_json(conteudo: bytes) -> dict:
    obj = json.loads(conteudo)
    if not isinstance(obj, dict) or "ticker" not in obj:
        raise ValueError("Pacote Yahoo inválido (sem 'ticker').")
    return obj


# ======================================================================
# Coleta (rede; injetável)
# ======================================================================

def _yf_ticker(symbol: str) -> Any:
    import yfinance as yf

    return yf.Ticker(symbol)


def coletar_parte(ticker: str, parte: str, *, factory: Callable[[str], Any] | None = None,
                  sleep: Callable[[float], None] | None = None) -> bytes:
    """Coleta uma parte para o ``ticker`` e devolve o JSON canônico (bytes)."""
    if parte not in PARTES:
        raise ValueError(f"Parte Yahoo desconhecida: {parte!r}")
    tk = (factory or _yf_ticker)(ticker)
    kw = {"sleep": sleep} if sleep is not None else {}
    doc: dict[str, Any] = {"ticker": ticker, "parte": parte, "fonte": "YAHOO",
                           "url": URL_QUOTE.format(t=ticker)}
    erros: dict[str, str] = {}

    def seguro(campo: str, fn: Callable[[], Any]) -> Any:
        """Consulta parcial: falha (ex.: limite de requisições) fica registrada em ``erros`` —
        "sem cobertura" (tabela vazia válida) nunca se confunde com "consulta falhou"."""
        try:
            return call_with_retry(fn, retries=1, backoff=(1.0,), what=f"yfinance {campo}", **kw)
        except Exception as exc:
            erros[campo] = f"{type(exc).__name__}: {str(exc)[:200]}"
            return None

    def fechar(n_consultas: int) -> None:
        if len(erros) >= n_consultas:  # todas falharam: nada é arquivado (falha registrada)
            raise ValueError(f"Yahoo: todas as consultas de {parte} falharam para {ticker}: "
                             + "; ".join(f"{k}: {v}" for k, v in sorted(erros.items())))
        if erros:
            doc["erros"] = dict(sorted(erros.items()))

    if parte == "info":
        info = call_with_retry(lambda: dict(tk.info or {}), what=f"info {ticker}", **kw)
        doc["info"] = {k: info.get(k) for k in INFO_CAMPOS}
        if not any(v is not None for v in doc["info"].values()):
            raise ValueError(f"Yahoo sem dados para {ticker}.")
    elif parte == "estimativas":
        doc["earnings_estimate"] = _tabela(seguro("earnings_estimate",
                                                  lambda: tk.earnings_estimate))
        doc["revenue_estimate"] = _tabela(seguro("revenue_estimate", lambda: tk.revenue_estimate))
        alvos = seguro("analyst_price_targets", lambda: tk.analyst_price_targets)
        doc["analyst_price_targets"] = _limpo(dict(alvos)) if isinstance(alvos, Mapping) else None
        fechar(3)
    elif parte == "demonstracoes":
        doc["demonstracoes"] = {nome: _quadro(seguro(nome, lambda n=nome: getattr(tk, n)))
                                for nome in DEMONSTRACOES}
        fechar(len(DEMONSTRACOES))
        if not any(doc["demonstracoes"].values()):
            raise ValueError(f"Yahoo sem demonstrações para {ticker}.")
    elif parte == "dividendos":
        s = call_with_retry(lambda: tk.dividends, what=f"dividendos {ticker}", **kw)
        pares = []
        if isinstance(s, pd.Series):
            for d, v in s.items():
                x = to_float(v)
                if math.isfinite(x) and x > 0:
                    pares.append([pd.Timestamp(d).tz_localize(None).date().isoformat()
                                  if pd.Timestamp(d).tzinfo else pd.Timestamp(d).date().isoformat(),
                                  x])
        doc["dividendos"] = sorted(pares)
    elif parte == "calendario":
        cal = seguro("calendar", lambda: tk.calendar)
        doc["calendar"] = _limpo(dict(cal)) if isinstance(cal, Mapping) else None
        ed = seguro("earnings_dates", lambda: tk.get_earnings_dates(limit=16))
        linhas = []
        if isinstance(ed, pd.DataFrame) and not ed.empty:
            for idx, row in ed.iterrows():
                ts = pd.Timestamp(idx)
                if ts.tzinfo is not None:
                    ts = ts.tz_convert(UTC).tz_localize(None)
                linhas.append({"data": ts.date().isoformat(),
                               "eps_estimado": _limpo(to_float(row.get("EPS Estimate"))),
                               "eps_reportado": _limpo(to_float(row.get("Reported EPS")))})
        doc["earnings_dates"] = sorted(linhas, key=lambda r: r["data"])
        fechar(2)
    return serializar(doc)


# ======================================================================
# Leitura (pura; offline)
# ======================================================================

def _ts_data(v: Any) -> date | None:
    x = to_float(v)
    if not math.isfinite(x) or x <= 0:
        return None
    try:
        return datetime.fromtimestamp(x, tz=UTC).date()
    except (OverflowError, OSError, ValueError):
        return None


def consenso_de(info_doc: dict | None, est_doc: dict | None) -> dict:
    """Campos de consenso (``float``/``NaN``) a partir das partes ``info`` e ``estimativas``."""
    info = (info_doc or {}).get("info") or {}
    est = est_doc or {}
    ee = est.get("earnings_estimate") or {}
    re_ = est.get("revenue_estimate") or {}
    alv = est.get("analyst_price_targets") or {}

    def g(tab: dict, per: str, campo: str) -> float:
        return to_float((tab.get(per) or {}).get(campo))

    # cada tabela tem a própria moeda (ADR: LPA em USD e receita na moeda do balanço, ou o
    # inverso); ausente ⇒ None (nunca a moeda de outra tabela)
    moeda_eps = (ee.get("0y") or {}).get("currency") or (ee.get("+1y") or {}).get("currency")
    moeda_rec = (re_.get("0y") or {}).get("currency") or (re_.get("+1y") or {}).get("currency")
    return {
        "eps_fy1": g(ee, "0y", "avg"), "eps_fy2": g(ee, "+1y", "avg"),
        "receita_fy1": g(re_, "0y", "avg"), "receita_fy2": g(re_, "+1y", "avg"),
        "n_analistas_eps": g(ee, "0y", "numberOfAnalysts"),
        "alvo_medio": to_float(alv.get("mean", info.get("targetMeanPrice"))),
        "alvo_mediano": to_float(alv.get("median", info.get("targetMedianPrice"))),
        "alvo_alto": to_float(alv.get("high", info.get("targetHighPrice"))),
        "alvo_baixo": to_float(alv.get("low", info.get("targetLowPrice"))),
        "n_analistas_alvo": to_float(info.get("numberOfAnalystOpinions")),
        "recomendacao_media": to_float(info.get("recommendationMean")),
        "moeda_cotacao": info.get("currency"),
        "moeda_estimativas": moeda_eps or None,
        "preco_referencia_yahoo": to_float(alv.get("current", info.get("currentPrice"))),
        "moeda_receita": moeda_rec or None,
    }


class _Serie(list):
    """Valores de uma linha do Yahoo com o rótulo de origem (definição auditável)."""

    rotulo: str = ""


def _serie(valores: list, rotulo: str) -> _Serie:
    out = _Serie(valores)
    out.rotulo = rotulo
    return out


def _linha(linhas: Mapping[str, list], *rotulos: str) -> list | None:
    for r in rotulos:
        v = linhas.get(r)
        if v is not None and any(x is not None for x in v):
            return _serie(list(v), r)
    return None


def _com_rotulo(v: list | None, base: list | None, rotulo: str | None = None) -> list | None:
    if v is None:
        return None
    return _serie(list(v), rotulo or getattr(base, "rotulo", "") or "")


def _combinar(a: list | None, b: list | None, op: Callable[[float, float], float],
              sinal: str = "+") -> list | None:
    if a is None or b is None:
        return None
    out = []
    for x, y in zip(a, b, strict=True):
        out.append(None if x is None or y is None else op(float(x), float(y)))
    return _serie(out, f"{getattr(a, 'rotulo', '')} {sinal} {getattr(b, 'rotulo', '')}")


def _mapear(nome: str, linhas: Mapping[str, list], financeira: bool) -> dict[str, list]:
    """Rótulos do Yahoo ⇒ itens canônicos (listas alinhadas às colunas)."""
    m: dict[str, list | None] = {}
    if nome.endswith("income_stmt"):
        m["receita"] = _linha(linhas, "Total Revenue", "Operating Revenue")
        m["lucro_bruto"] = _linha(linhas, "Gross Profit")
        # EBIT = resultado operacional (a definição da CVM e da SEC); o "EBIT" do Yahoo
        # (lucro antes do IR + despesa de juros) inclui ganhos de valor justo e equivalência
        # e só entra na falta do resultado operacional. O EBITDA do Yahoo não é usado: vira
        # cópia do EBIT quando falta a depreciação trimestral — o código calcula ebit + d_a.
        m["ebit"] = _linha(linhas, "Operating Income", "EBIT")
        # D&A da DRE: só reserva (``Reconciled Depreciation`` às vezes é só a parcela das
        # despesas gerais); a da DFC (total) prevalece — ver ``fatos_yahoo``
        m["d_a"] = _linha(linhas, "Reconciled Depreciation",
                          "Depreciation And Amortization In Income Statement",
                          "Depreciation Amortization Depletion Income Statement")
        m["resultado_financeiro"] = _linha(linhas, "Net Non Operating Interest Income Expense")
        m["lucro_antes_ir"] = _linha(linhas, "Pretax Income")
        tax = _linha(linhas, "Tax Provision")
        m["ir_csll"] = _com_rotulo(None if tax is None else [None if x is None else -x
                                                             for x in tax], tax)
        m["lucro_liquido"] = _linha(linhas, "Net Income Including Noncontrolling Interests")
        m["lucro_liquido_controladores"] = _linha(linhas, "Net Income Common Stockholders",
                                                  "Net Income")
        if financeira:
            m["margem_financeira"] = _linha(linhas, "Net Interest Income")
            pdd = _linha(linhas, "Credit Losses Provision", "Provision For Doubtful Accounts")
            m["despesa_pdd"] = _com_rotulo(None if pdd is None else [None if x is None else -abs(x)
                                                                     for x in pdd], pdd)
            m["receita_servicos"] = _linha(linhas, "Fees And Commission Income",
                                           "Fees And Commissions")
    elif nome.endswith("balance_sheet"):
        m["ativo_total"] = _linha(linhas, "Total Assets")
        m["patrimonio_controladores"] = _linha(linhas, "Stockholders Equity",
                                               "Common Stock Equity")
        m["patrimonio_liquido"] = _linha(linhas, "Total Equity Gross Minority Interest")
        m["participacao_minoritarios"] = _linha(linhas, "Minority Interest")
        m["acoes_emitidas"] = _linha(linhas, "Share Issued")
        m["acoes_tesouraria"] = _linha(linhas, "Treasury Shares Number")
        m["acoes_em_circulacao"] = _linha(linhas, "Ordinary Shares Number")
        if financeira:
            m["carteira_credito"] = _linha(linhas, "Gross Loan", "Net Loan")
            prov = _linha(linhas, "Allowance For Loans And Lease Losses")
            m["provisao_credito"] = _com_rotulo(None if prov is None else [
                None if x is None else abs(x) for x in prov], prov)
        else:
            m["caixa"] = _linha(linhas, "Cash And Cash Equivalents")
            m["aplicacoes_cp"] = _linha(linhas, "Other Short Term Investments")
            arr = _linha(linhas, "Capital Lease Obligations") or _combinar(
                _linha(linhas, "Current Capital Lease Obligation"),
                _linha(linhas, "Long Term Capital Lease Obligation"), lambda a, b: a + b)
            m["arrendamentos"] = arr
            div = _combinar(_linha(linhas, "Current Debt"), _linha(linhas, "Long Term Debt"),
                            lambda a, b: a + b)
            total = _linha(linhas, "Total Debt")
            if div is None and total is not None:
                if arr is not None:
                    div = _combinar(total, arr, lambda a, b: a - b, "−")
                elif not any(r in linhas for r in ("Capital Lease Obligations",
                                                   "Current Capital Lease Obligation",
                                                   "Long Term Capital Lease Obligation")):
                    div = total
            m["divida_bruta"] = div
    elif nome.endswith("cashflow"):
        m["cfo"] = _linha(linhas, "Operating Cash Flow",
                          "Cash Flowsfromusedin Operating Activities Direct")
        for item, rot in (("capex", ("Capital Expenditure",)),
                          ("dividendos_pagos", ("Cash Dividends Paid",
                                                "Common Stock Dividend Paid",
                                                "Dividends Paid Direct")),
                          ("recompras", ("Repurchase Of Capital Stock", "Common Stock Payments")),
                          ("d_a_dfc", ("Depreciation And Amortization",
                                       "Depreciation Amortization Depletion"))):
            v = _linha(linhas, *rot)
            m[item] = _com_rotulo(None if v is None else [None if x is None else abs(x)
                                                          for x in v], v)
    return {k: v for k, v in m.items() if v is not None}


RAZAO_MIN_DA_CAPEX = 0.10
"""D&A abaixo de 10% do capex do mesmo período ⇒ D&A parcial (ex.: só a parcela das despesas
gerais) — descartada (ausente, nunca um valor parcial)."""


def fatos_yahoo(doc: dict, *, data_coleta: date, financeira: bool,
                moeda: str | None = None, nota: str | None = None) -> pd.DataFrame:
    """Fatos canônicos (``FATO_COLUNAS`` + ``pit_estimado`` + ``nota``) da parte
    ``demonstracoes``. ``data_coleta`` é a data (São Paulo) da coleta: limite da data de
    publicação estimada. ``documento`` registra o rótulo do Yahoo usado em cada item."""
    ticker = str(doc.get("ticker"))
    dem = doc.get("demonstracoes") or {}
    rows: list[dict] = []
    for nome, (demonstrativo, freq) in DEMONSTRACOES.items():
        q = dem.get(nome)
        if not q:
            continue
        cols = [pd.Timestamp(c) for c in q.get("colunas", [])]
        itens = _mapear(nome, q.get("linhas", {}), financeira)
        for item, vals in itens.items():
            it = "d_a" if item == "d_a_dfc" else item
            rotulo = getattr(vals, "rotulo", "") or ""
            for end, v in zip(cols, vals, strict=True):
                if v is None or not math.isfinite(float(v)):
                    continue
                if demonstrativo == "BP":
                    start = pd.NaT
                elif freq == "A":
                    start = end - pd.DateOffset(years=1) + pd.Timedelta(days=1)
                else:
                    start = end - pd.DateOffset(months=3) + pd.Timedelta(days=1)
                est = min(end.date() + timedelta(days=DEFASAGEM_DIAS[freq]), data_coleta)
                rows.append({
                    "entidade": ticker, "demonstrativo": "DFC" if item == "d_a_dfc" else
                    demonstrativo, "item": it, "period_start": start, "period_end": end,
                    "value": float(v), "currency": moeda, "received_date": pd.Timestamp(est),
                    # D&A: a da DFC (total) prevalece; a da DRE (versão 0) só na falta dela
                    "version": 0 if (it == "d_a" and item != "d_a_dfc") else 1,
                    "documento": f"Yahoo Finance {nome}" + (f": {rotulo}" if rotulo else ""),
                    "url": URL_QUOTE.format(t=ticker) + "/financials", "consolidado": True,
                    "anual": freq == "A", "pit_estimado": True, "nota": nota,
                })
    if not rows:
        return pd.DataFrame(columns=[*FATO_COLUNAS, "pit_estimado", "nota"])
    out = pd.DataFrame(rows)
    # D&A implausível frente ao capex do mesmo período (D&A parcial) ⇒ descartada
    capex = out[out["item"] == "capex"].set_index(["period_start", "period_end"])["value"]
    capex = capex[~capex.index.duplicated(keep="last")]
    da = out["item"] == "d_a"
    if da.any() and not capex.empty:
        ref = pd.Series([capex.get((s0, e0), float("nan")) for s0, e0 in
                         zip(out.loc[da, "period_start"], out.loc[da, "period_end"],
                             strict=True)], index=out.index[da])
        ruim = ref.notna() & (out.loc[da, "value"] < RAZAO_MIN_DA_CAPEX * ref)
        out = out.drop(index=ruim[ruim].index)
    # A D&A restituída na DFC tem contrato próprio para o reinvestimento FCFF.
    # Mantém o item d_a consumido pelo EBITDA e acrescenta somente o fluxo
    # explicitamente extraído da DFC, após os mesmos controles de qualidade.
    da_dfc = out[(out["item"] == "d_a") & (out["demonstrativo"] == "DFC")].copy()
    if not da_dfc.empty:
        da_dfc["item"] = "d_a_dfc"
        out = pd.concat([out, da_dfc], ignore_index=True)
    return out.reset_index(drop=True)


def dividendos_de(doc: dict) -> list[tuple[date, float]]:
    return [(date.fromisoformat(d), float(v)) for d, v in (doc.get("dividendos") or [])]


def eventos_de(info_doc: dict | None, cal_doc: dict | None, hoje: date) -> list[dict]:
    """Eventos (resultado/dividendo) do Yahoo: ``[{data, tipo, estimada, rotulo}]``."""
    out: list[dict] = []
    info = (info_doc or {}).get("info") or {}
    estimado = bool(info.get("isEarningsDateEstimate"))
    for r in (cal_doc or {}).get("earnings_dates") or []:
        try:
            d = date.fromisoformat(str(r["data"])[:10])
        except (KeyError, ValueError):
            continue
        out.append({"data": d, "tipo": "resultado",
                    "estimada": d >= hoje and estimado and r.get("eps_reportado") is None,
                    "rotulo": "Yahoo earnings_dates"})
    cal = (cal_doc or {}).get("calendar") or {}
    datas = cal.get("Earnings Date") or []
    if not isinstance(datas, list):
        datas = [datas]
    for v in datas:
        try:
            d = date.fromisoformat(str(v)[:10])
        except ValueError:
            continue
        out.append({"data": d, "tipo": "resultado", "estimada": estimado,
                    "rotulo": "Yahoo calendar"})
    for k in ("earningsTimestampStart", "earningsTimestamp"):
        d = _ts_data(info.get(k))
        if d is not None:
            out.append({"data": d, "tipo": "resultado", "estimada": estimado,
                        "rotulo": f"Yahoo {k}"})
    exd = _ts_data(info.get("exDividendDate"))
    if exd is None and cal.get("Ex-Dividend Date"):
        try:
            exd = date.fromisoformat(str(cal["Ex-Dividend Date"])[:10])
        except ValueError:
            exd = None
    if exd is not None:
        out.append({"data": exd, "tipo": "dividendo", "estimada": False,
                    "rotulo": "Yahoo data-ex"})
    return out


def float_de(info_doc: dict | None) -> tuple[float, str]:
    """``floatShares / sharesOutstanding`` (mesma linha); fora de (0, 1] ⇒ ``NaN`` + motivo."""
    info = (info_doc or {}).get("info") or {}
    fl = to_float(info.get("floatShares"))
    so = to_float(info.get("sharesOutstanding"))
    if not math.isfinite(so) or so <= 0:
        so = to_float(info.get("impliedSharesOutstanding"))
    if not (math.isfinite(fl) and math.isfinite(so)) or so <= 0 or fl <= 0:
        return math.nan, "float_ou_acoes_ausentes"
    r = fl / so
    if r > 1.0:
        return math.nan, "float_maior_que_total"
    return r, "floatShares/sharesOutstanding"


__all__ = [
    "DEFASAGEM_DIAS", "DEMONSTRACOES", "INFO_CAMPOS", "PARTES", "coletar_parte", "consenso_de",
    "dividendos_de", "eventos_de", "fatos_yahoo", "float_de", "ler_json", "serializar",
]
