"""FactBook determinístico: todos os números que a camada de IA pode citar.

O LLM nunca calcula nada. Ele recebe uma lista de fatos (``fact_id: valor formatado (nome)``)
e só pode mencionar números por meio de placeholders ``{{fact:<fact_id>}}``, que o código
resolve com o valor formatado deste módulo.

Regras de dados:

- Retornos em USD vêm de ``panel.returns`` (retorno total diário da linha primária) e são
  compostos sobre os pregões disponíveis da janela (``Π(1+r) − 1``). Pregões sem dado não são
  preenchidos; a cobertura (pregões válidos / tamanho da janela) é registrada na fórmula e nos
  insumos. Cobertura abaixo de ``MIN_COVERAGE`` (80%) ⇒ ``value=None``.
- Dado ausente ⇒ ``value=None`` e ``formatted='n/d'`` (nunca zero).
- Fundamentos, consenso e short interest são retratos atuais do snapshot ⇒
  ``point_in_time=False``.
- Função pura e determinística: mesma entrada ⇒ mesmo FactBook (e mesmo hash).

Formatação pt-BR: variações percentuais com sinal e duas casas (``+1,25%``), níveis
percentuais sem sinal (``13,75%``), múltiplos com uma casa (``7,3x``), valores em USD com
escala (``US$ 12,3 mi``, ``US$ 4,5 bi``), escores z com sinal (``+1,23``).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import date

import numpy as np
import pandas as pd

from ..analytics.panel import AssetPanel
from ..contracts import Fact, FactBook
from ..market import MarketData
from ..risk.types import TRADING_DAYS

NA_TEXT = "n/d"
MIN_COVERAGE = 0.8
"""Fração mínima de pregões válidos na janela para publicar um retorno/volatilidade."""

RETURN_WINDOWS: dict[str, int] = {"1w": 5, "1m": 21, "3m": 63, "12m": 252}
VOL_WINDOW = 63
STALE_PRICE_DAYS = 5
"""Preço mais antigo que isso (vs. ``as_of``) não é usado para o upside ao preço-alvo."""
UPSIDE_BOUNDS = (-0.9, 3.0)
"""Upside fora desta faixa é tratado como implausível (provável erro de moeda) ⇒ ``None``."""

NON_PIT_SIGNALS = frozenset({"value", "quality", "analyst_revision"})
"""Sinais derivados de retratos atuais (usados quando ``signal_z.attrs`` não informa)."""

ISSUER_METRICS: tuple[str, ...] = (
    "ret_1w_usd", "ret_1m_usd", "ret_3m_usd", "ret_ytd_usd", "ret_12m_usd", "vol_3m", "beta",
    "adtv_usd_mm", "mcap_usd_bn", "pe_trailing", "pb", "roe", "div_yield", "ev_ebitda",
    "target_upside", "analyst_count", "si_pct_float", "days_to_cover", "borrow_fee",
    "squeeze_score", "alpha_z", "spec_vol",
)


# ==========================================================
# Formatação pt-BR
# ==========================================================

def _is_missing(value: float | None) -> bool:
    return value is None or not math.isfinite(float(value))


def _br_number(value: float, decimals: int) -> str:
    """Número com separador de milhar ``.`` e decimal ``,`` (sem sinal)."""
    text = f"{abs(value):,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _sign(value: float, decimals: int) -> str:
    """Sinal explícito (``+``/``-``); vazio quando o valor arredondado é zero."""
    if round(abs(value), decimals) == 0:
        return ""
    return "+" if value > 0 else "-"


def _neg(value: float, decimals: int) -> str:
    """Somente o sinal negativo (níveis não levam ``+``)."""
    return "-" if value < 0 and round(abs(value), decimals) != 0 else ""


def format_pct(value: float | None, signed: bool = True, decimals: int = 2) -> str:
    """Decimal → percentual pt-BR (``0.0125`` → ``+1,25%``); ausente → ``n/d``."""
    if _is_missing(value):
        return NA_TEXT
    pct = float(value) * 100.0
    sign = _sign(pct, decimals) if signed else _neg(pct, decimals)
    return f"{sign}{_br_number(pct, decimals)}%"


def format_multiple(value: float | None, decimals: int = 1) -> str:
    if _is_missing(value):
        return NA_TEXT
    return f"{_neg(float(value), decimals)}{_br_number(float(value), decimals)}x"


def format_usd(value: float | None) -> str:
    """Valor em USD com escala automática (``bi``/``mi``)."""
    if _is_missing(value):
        return NA_TEXT
    v = float(value)
    sign = "-" if v < 0 else ""
    if abs(v) >= 1e9:
        return f"{sign}US$ {_br_number(v / 1e9, 1)} bi"
    if abs(v) >= 1e6:
        return f"{sign}US$ {_br_number(v / 1e6, 1)} mi"
    return f"{sign}US$ {_br_number(v, 0)}"


def format_usd_mm(value: float | None) -> str:
    """Valor já expresso em milhões de USD."""
    if _is_missing(value):
        return NA_TEXT
    v = float(value)
    sign = "-" if v < 0 else ""
    return f"{sign}US$ {_br_number(v, 1)} mi"


def format_z(value: float | None) -> str:
    if _is_missing(value):
        return NA_TEXT
    v = float(value)
    return f"{_sign(v, 2)}{_br_number(v, 2)}"


def format_value(value: float | None, unit: str, signed: bool = False) -> str:
    """Formatação canônica por unidade (``Fact.unit``)."""
    if _is_missing(value):
        return NA_TEXT
    v = float(value)
    if unit == "pct":
        return format_pct(v, signed=signed)
    if unit == "x":
        return format_multiple(v)
    if unit == "usd":
        return format_usd(v)
    if unit == "usd_mm":
        return format_usd_mm(v)
    if unit == "days":
        return f"{_br_number(v, 1)} dias"
    if unit == "score":
        return f"{_br_number(v, 1)}"
    if unit == "bps":
        return f"{_sign(v, 0) if signed else _neg(v, 0)}{_br_number(v, 0)} bps"
    if unit == "z":
        return format_z(v)
    if unit == "count":
        return f"{_br_number(v, 0)}"
    # ratio
    sign = _sign(v, 2) if signed else _neg(v, 2)
    return f"{sign}{_br_number(v, 2)}"


# ==========================================================
# Cálculos (puros)
# ==========================================================

def _upto(df: pd.DataFrame, as_of: date) -> pd.DataFrame:
    return df.loc[df.index <= pd.Timestamp(as_of)]


def compound_window(daily: pd.Series, window: int) -> tuple[float | None, int, int, str, str]:
    """Retorno composto das últimas ``window`` linhas de ``daily`` (já cortado em ``as_of``).

    Retorna ``(valor, n_validos, tamanho_janela, inicio, fim)``. Pregões ``NaN`` não são
    preenchidos: compõe-se o que existe; cobertura ``n_validos / window`` abaixo de
    ``MIN_COVERAGE`` ⇒ ``None``. Histórico mais curto que a janela conta como ausência.
    """
    if window <= 0:
        return None, 0, 0, "", ""
    tail = daily.tail(window)
    valid = tail.dropna()
    valid = valid[np.isfinite(valid.to_numpy(dtype=float))]
    n_valid = int(len(valid))
    start = tail.index[0].date().isoformat() if len(tail) else ""
    end = tail.index[-1].date().isoformat() if len(tail) else ""
    if n_valid / window < MIN_COVERAGE or n_valid == 0:
        return None, n_valid, window, start, end
    value = float(np.prod(1.0 + valid.to_numpy(dtype=float)) - 1.0)
    return value, n_valid, window, start, end


def level_returns(level: pd.Series) -> pd.Series:
    """Retornos diários de uma série de NÍVEL (câmbio, ETF) sem perder movimentos em lacunas.

    O retorno é calculado entre observações válidas consecutivas (o movimento através de um
    dia sem dado entra no próximo pregão válido) e reindexado ao calendário original: o dia
    sem dado fica ``NaN`` (conta contra a cobertura), nunca zero. ``pct_change`` direto sobre
    o nível com ``NaN`` descartaria o movimento através da lacuna.
    """
    valid = level.where(level > 0).dropna()
    return valid.pct_change(fill_method=None).reindex(level.index)


def annualized_vol(daily: pd.Series, window: int) -> tuple[float | None, int, int]:
    """Desvio-padrão amostral × √252 das últimas ``window`` linhas (cobertura >= 80%)."""
    tail = daily.tail(window)
    valid = tail.dropna()
    valid = valid[np.isfinite(valid.to_numpy(dtype=float))]
    n_valid = int(len(valid))
    if window <= 0 or n_valid / window < MIN_COVERAGE or n_valid < 2:
        return None, n_valid, window
    return float(valid.std(ddof=1) * math.sqrt(TRADING_DAYS)), n_valid, window


def _coverage_text(n_valid: int, window: int) -> str:
    pct = (n_valid / window * 100.0) if window else 0.0
    return f"cobertura {n_valid}/{window} pregões ({pct:.0f}%)"


def _num(x: object) -> float | None:
    """Converte para float finito; qualquer outra coisa ⇒ ``None`` (nunca zero)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _series_value(s: pd.Series | None, key: str) -> float | None:
    if s is None or key not in s.index:
        return None
    return _num(s.loc[key])


# ==========================================================
# Construção dos fatos
# ==========================================================

class _Builder:
    def __init__(self) -> None:
        self.facts: dict[str, Fact] = {}

    def add(self, fact_id: str, issuer_id: str | None, name: str, value: float | None,
            unit: str, formula: str, inputs: Iterable[str] = (), point_in_time: bool = True,
            signed: bool = False, formatted: str | None = None) -> None:
        v = _num(value)
        text = formatted if formatted is not None else format_value(v, unit, signed)
        self.facts[fact_id] = Fact(
            fact_id=fact_id, issuer_id=issuer_id, name=name, value=v, unit=unit,  # type: ignore[arg-type]
            formatted=text, formula=formula, inputs=list(inputs), point_in_time=point_in_time,
        )


def _fundamental_line(md: MarketData, issuer_id: str) -> str | None:
    """Linha cujos fundamentos representam o emissor.

    Preferência: moeda de cotação = moeda das demonstrações (evita descasamento de ADRs),
    depois linha primária, depois ordem alfabética do ticker.
    """
    fund = md.fundamentals
    if fund is None or fund.empty:
        return None
    lines = md.universe.lines
    cand = lines[(lines["issuer_id"] == issuer_id) & lines.index.isin(fund.index)]
    if cand.empty:
        return None
    rows = []
    for tkr, row in cand.iterrows():
        f = fund.loc[tkr]
        quote = str(f.get("currency") or row["currency"]).upper()
        fin = f.get("financial_currency")
        match = isinstance(fin, str) and fin.upper() == quote
        rows.append((not match, not bool(row["primary_line"]), str(tkr)))
    return sorted(rows)[0][2]


def _last_close(md: MarketData, ticker: str, as_of: date) -> tuple[float | None, date | None]:
    if ticker not in md.close.columns:
        return None, None
    s = _upto(md.close[[ticker]], as_of)[ticker].dropna()
    s = s[s > 0]
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1].date()


def _fund_value(md: MarketData, ticker: str | None, field: str) -> float | None:
    if ticker is None or field not in md.fundamentals.columns:
        return None
    return _num(md.fundamentals.loc[ticker, field])


def _return_facts(b: _Builder, iid: str, daily: pd.Series, as_of: date) -> None:
    labels = {"1w": "1 semana", "1m": "1 mês", "3m": "3 meses", "12m": "12 meses"}
    for key, window in RETURN_WINDOWS.items():
        value, n, w, start, end = compound_window(daily, window)
        b.add(
            f"{iid}.ret_{key}_usd", iid, f"Retorno total em USD — {labels[key]}", value, "pct",
            f"Π(1+r_d)−1 dos retornos diários em USD (linha primária) nos últimos {window} "
            f"pregões até {as_of.isoformat()}; {_coverage_text(n, w)}; mínimo "
            f"{MIN_COVERAGE:.0%} de cobertura, dias sem dado não são preenchidos",
            [f"panel.returns[{iid}]", f"janela={start}..{end}", f"cobertura={n}/{w}"],
            signed=True,
        )
    ytd = daily[daily.index.year == as_of.year]
    window = len(ytd)
    value, n, w, start, end = compound_window(ytd, window) if window else (None, 0, 0, "", "")
    b.add(
        f"{iid}.ret_ytd_usd", iid, "Retorno total em USD — no ano", value, "pct",
        f"Π(1+r_d)−1 dos retornos diários em USD de {as_of.year} até {as_of.isoformat()}; "
        f"{_coverage_text(n, w) if w else 'sem pregões no ano'}",
        [f"panel.returns[{iid}]", f"janela={start}..{end}", f"cobertura={n}/{w}"], signed=True,
    )
    vol, n, w = annualized_vol(daily, VOL_WINDOW)
    b.add(
        f"{iid}.vol_3m", iid, "Volatilidade anualizada em USD — 3 meses", vol, "pct",
        f"desvio-padrão amostral dos retornos diários em USD dos últimos {VOL_WINDOW} pregões "
        f"× √{TRADING_DAYS}; {_coverage_text(n, w)}",
        [f"panel.returns[{iid}]", f"cobertura={n}/{w}"],
    )


def _fundamental_facts(b: _Builder, iid: str, md: MarketData, as_of: date) -> None:
    tkr = _fundamental_line(md, iid)
    src = f"fundamentals[{tkr}]" if tkr else "fundamentals[sem linha]"
    note = "retrato atual do snapshot (não point-in-time)"

    pe = _fund_value(md, tkr, "trailing_pe")
    b.add(f"{iid}.pe_trailing", iid, "P/L (lucro dos últimos 12 meses)",
          pe if (pe is not None and pe > 0) else None, "x",
          f"trailing_pe da fonte; valores não positivos ⇒ n/d; {note}",
          [f"{src}.trailing_pe"], point_in_time=False)
    pb = _fund_value(md, tkr, "price_to_book")
    b.add(f"{iid}.pb", iid, "Preço / valor patrimonial", pb if (pb is not None and pb > 0) else None,
          "x", f"price_to_book da fonte; valores não positivos ⇒ n/d; {note}",
          [f"{src}.price_to_book"], point_in_time=False)
    b.add(f"{iid}.roe", iid, "Retorno sobre o patrimônio (ROE)",
          _fund_value(md, tkr, "return_on_equity"), "pct",
          f"return_on_equity da fonte (decimal); {note}", [f"{src}.return_on_equity"],
          point_in_time=False)
    dy = _fund_value(md, tkr, "dividend_yield")
    b.add(f"{iid}.div_yield", iid, "Dividend yield",
          dy if (dy is not None and 0.0 <= dy <= 1.0) else None, "pct",
          f"dividend_yield da fonte (decimal); fora de [0, 1] ⇒ n/d (unidade ambígua); {note}",
          [f"{src}.dividend_yield"], point_in_time=False)
    ev = _fund_value(md, tkr, "enterprise_to_ebitda")
    b.add(f"{iid}.ev_ebitda", iid, "EV / EBITDA", ev if (ev is not None and ev > 0) else None, "x",
          f"enterprise_to_ebitda da fonte; valores não positivos ⇒ n/d; {note}",
          [f"{src}.enterprise_to_ebitda"], point_in_time=False)
    n_an = _fund_value(md, tkr, "number_of_analyst_opinions")
    b.add(f"{iid}.analyst_count", iid, "Número de analistas cobrindo",
          n_an if (n_an is not None and n_an >= 0) else None, "count",
          f"number_of_analyst_opinions da fonte; {note}",
          [f"{src}.number_of_analyst_opinions"], point_in_time=False)

    upside, why = None, "sem linha de fundamentos"
    if tkr is not None:
        target = _fund_value(md, tkr, "target_mean_price")
        quote = md.fundamentals.loc[tkr].get("currency")
        line_ccy = str(md.universe.lines.loc[tkr, "currency"]).upper()
        px, px_date = _last_close(md, tkr, as_of)
        if target is None or target <= 0:
            why = "preço-alvo ausente"
        elif not (isinstance(quote, str) and quote.upper() == line_ccy):
            why = "moeda do preço-alvo difere da moeda de cotação"
        elif px is None or px_date is None:
            why = "sem preço de fechamento"
        elif (as_of - px_date).days > STALE_PRICE_DAYS:
            why = f"preço defasado ({px_date.isoformat()})"
        else:
            u = target / px - 1.0
            if UPSIDE_BOUNDS[0] <= u <= UPSIDE_BOUNDS[1]:
                upside, why = u, f"preço de {px_date.isoformat()}"
            else:
                why = "upside implausível (provável erro de moeda)"
    b.add(f"{iid}.target_upside", iid, "Upside ao preço-alvo médio do consenso", upside, "pct",
          f"target_mean_price / último fechamento da mesma linha − 1; {why}; {note}",
          [f"{src}.target_mean_price", f"close[{tkr}]"], point_in_time=False, signed=True)


def _squeeze_facts(b: _Builder, iid: str, squeeze: pd.DataFrame | None) -> None:
    row = squeeze.loc[iid] if (squeeze is not None and iid in squeeze.index) else None
    pit = False  # short interest e aluguel são sempre retratos atuais do snapshot
    src = "squeeze_table" if row is not None else "squeeze_table[ausente]"

    def get(col: str) -> float | None:
        return None if row is None else _num(row.get(col))

    b.add(f"{iid}.si_pct_float", iid, "Short interest (% do free float, proxy)",
          get("si_pct_float"), "pct",
          "máximo entre short_pct_float (linhas US) e lending_pct_shares (BTC B3); retrato atual",
          [f"{src}.si_pct_float"], point_in_time=pit)
    dtc_raw = None if row is None else row.get("days_to_cover")
    dtc_inf = dtc_raw is not None and isinstance(dtc_raw, (int, float)) and math.isinf(dtc_raw)
    b.add(f"{iid}.days_to_cover", iid, "Dias para cobrir (short / volume médio)",
          None if dtc_inf else get("days_to_cover"), "days",
          "ações vendidas ou doadas / volume médio diário de ações; volume zero com posição "
          "vendida ⇒ infinito (sem volume); retrato atual",
          [f"{src}.days_to_cover"], point_in_time=pit,
          formatted="infinito (sem volume)" if dtc_inf else None)
    b.add(f"{iid}.borrow_fee", iid, "Taxa de aluguel anual (observada ou estimada)",
          get("borrow_fee"), "pct", "maior taxa de aluguel entre as linhas do emissor; retrato atual",
          [f"{src}.borrow_fee"], point_in_time=pit)
    b.add(f"{iid}.squeeze_score", iid, "Escore de risco de short squeeze (0–100)",
          get("squeeze_score"), "score",
          "média ponderada dos componentes si/dtc/fee/mom/float/catalyst com regra do máximo "
          "(analytics.squeeze)", [f"{src}.squeeze_score"], point_in_time=pit)


def _macro_facts(b: _Builder, md: MarketData, as_of: date, currencies: list[str]) -> None:
    fx = _upto(md.fx, as_of)
    for ccy in currencies:
        if ccy == "USD":
            continue
        if ccy in fx.columns:
            daily = level_returns(fx[ccy])
            value, n, w, start, end = compound_window(daily, RETURN_WINDOWS["1m"])
        else:
            value, n, w, start, end = None, 0, RETURN_WINDOWS["1m"], "", ""
        b.add(f"fx.{ccy}.ret_1m", None, f"Variação de 1 mês do {ccy} (USD por unidade)", value, "pct",
              f"variação composta de USD por 1 {ccy} nos últimos {RETURN_WINDOWS['1m']} pregões "
              f"até {as_of.isoformat()}; positivo = moeda local se valorizou; {_coverage_text(n, w)}",
              [f"fx[{ccy}]", f"janela={start}..{end}"], signed=True)
    bench = _upto(md.benchmarks, as_of)
    for sym in sorted(str(c) for c in bench.columns):
        daily = level_returns(bench[sym])
        value, n, w, start, end = compound_window(daily, RETURN_WINDOWS["1m"])
        b.add(f"bench.{sym}.ret_1m", None, f"Retorno de 1 mês de {sym} (USD)", value, "pct",
              f"variação composta do fechamento de {sym} nos últimos {RETURN_WINDOWS['1m']} "
              f"pregões até {as_of.isoformat()}; {_coverage_text(n, w)}",
              [f"benchmarks[{sym}]", f"janela={start}..{end}"], signed=True)
        ytd = daily[daily.index.year == as_of.year]
        value, n, w, start, end = compound_window(ytd, len(ytd)) if len(ytd) else (
            None, 0, 0, "", "")
        b.add(f"bench.{sym}.ret_ytd", None, f"Retorno de {sym} no ano (USD)", value, "pct",
              f"variação composta do fechamento de {sym} de {as_of.year} até {as_of.isoformat()}; "
              f"{_coverage_text(n, w) if w else 'sem pregões no ano'}",
              [f"benchmarks[{sym}]", f"janela={start}..{end}"], signed=True)
    rates = _upto(md.rates, as_of)
    for col in sorted(str(c) for c in rates.columns):
        s = rates[col].dropna()
        value = _num(s.iloc[-1]) if len(s) else None
        when = s.index[-1].date().isoformat() if len(s) else "sem observação"
        b.add(f"rate.{col}", None, f"Taxa {col} (anual)", value, "pct",
              f"último valor disponível até {as_of.isoformat()} ({when}); decimal anual",
              [f"rates[{col}]"], signed=False)


def _signal_pit(signal_z: pd.DataFrame, name: str) -> bool:
    attrs = signal_z.attrs.get("point_in_time") if isinstance(signal_z.attrs, dict) else None
    if isinstance(attrs, Mapping) and name in attrs:
        return bool(attrs[name])
    return name not in NON_PIT_SIGNALS


def build_factbook(panel: AssetPanel, md: MarketData, issuers: list[str],
                   alpha_z: pd.Series | None = None, signal_z: pd.DataFrame | None = None,
                   squeeze: pd.DataFrame | None = None, betas: pd.Series | None = None,
                   specific_vol: pd.Series | None = None,
                   snapshot_id: str | None = None) -> FactBook:
    """Monta o FactBook da semana para ``issuers`` + fatos macro (câmbio, ETFs, juros).

    Ids: ``<issuer_id>.<métrica>`` (ver ``ISSUER_METRICS`` e ``sig_<sinal>_z``),
    ``fx.<MOEDA>.ret_1m``, ``bench.<SÍMBOLO>.ret_1m|ret_ytd`` e ``rate.<SÉRIE>``.
    Nenhum insumo é alterado; ausências viram ``None``/``n/d``.
    """
    as_of = panel.as_of
    b = _Builder()
    ids = sorted(dict.fromkeys(str(i) for i in issuers))
    returns = _upto(panel.returns, as_of)
    assets = panel.assets
    signal_cols = [] if signal_z is None else sorted(str(c) for c in signal_z.columns)
    alpha_pit = bool(alpha_z.attrs.get("point_in_time", False)) if alpha_z is not None else False

    for iid in ids:
        in_panel = iid in assets.index and iid in returns.columns
        daily = returns[iid] if in_panel else pd.Series(np.nan, index=returns.index, dtype=float)
        _return_facts(b, iid, daily, as_of)

        if betas is not None:
            b.add(f"{iid}.beta", iid, "Beta previsto vs. mercado LatAm", _series_value(betas, iid),
                  "ratio", "beta previsto do modelo de risco (exposição ao fator de mercado)",
                  ["risk_model.beta"])
        else:
            tkr = _fundamental_line(md, iid)
            b.add(f"{iid}.beta", iid, "Beta da fonte de dados", _fund_value(md, tkr, "beta"),
                  "ratio", "beta reportado pela fonte de fundamentos; retrato atual (não PIT)",
                  [f"fundamentals[{tkr}].beta"], point_in_time=False)

        adtv = _num(assets.loc[iid, "adtv_usd"]) if iid in assets.index else None
        b.add(f"{iid}.adtv_usd_mm", iid, "Volume médio diário negociado (todas as linhas)",
              None if adtv is None else adtv / 1e6, "usd_mm",
              "média do valor negociado diário em USD somando todas as linhas (janela "
              "liquidity.adv_window_days), em milhões", [f"panel.assets[{iid}].adtv_usd"])
        mcap = _num(assets.loc[iid, "market_cap_usd"]) if iid in assets.index else None
        b.add(f"{iid}.mcap_usd_bn", iid, "Valor de mercado em USD", mcap, "usd",
              "market_cap da fonte × câmbio do último pregão; valor em USD (exibido em bilhões); "
              "retrato atual (não PIT)", [f"panel.assets[{iid}].market_cap_usd"],
              point_in_time=False)

        _fundamental_facts(b, iid, md, as_of)
        _squeeze_facts(b, iid, squeeze)

        if alpha_z is not None:
            b.add(f"{iid}.alpha_z", iid, "Escore z do alpha composto", _series_value(alpha_z, iid),
                  "z", "z-score do alpha combinado (alpha.combine), winsorizado; calculado em código",
                  ["alpha.combine"], point_in_time=alpha_pit, signed=True)
        for name in signal_cols:
            col = signal_z[name] if signal_z is not None else None
            b.add(f"{iid}.sig_{name}_z", iid, f"Escore z do sinal {name}",
                  _series_value(col, iid), "z",
                  f"z-score robusto do sinal {name} (alpha.signals/alpha.combine)",
                  [f"signals[{name}]"], point_in_time=_signal_pit(signal_z, name), signed=True)
        if specific_vol is not None:
            b.add(f"{iid}.spec_vol", iid, "Volatilidade específica anualizada (modelo de risco)",
                  _series_value(specific_vol, iid), "pct",
                  "√(variância específica anual) do modelo de risco", ["risk_model.specific_var"])

    currencies = sorted({str(c) for c in md.universe.lines["currency"].unique()})
    _macro_facts(b, md, as_of, currencies)
    facts = {k: b.facts[k] for k in sorted(b.facts)}
    return FactBook(as_of=as_of, snapshot_id=snapshot_id or md.manifest.snapshot_id,
                    facts=facts, is_synthetic=md.is_synthetic)


# ==========================================================
# Consultas
# ==========================================================

def facts_for_issuer(fb: FactBook, issuer_id: str) -> dict[str, Fact]:
    """Fatos de um emissor (chave = ``fact_id``), em ordem alfabética."""
    return {k: f for k, f in sorted(fb.facts.items()) if f.issuer_id == issuer_id}


def macro_facts(fb: FactBook) -> dict[str, Fact]:
    """Fatos sem emissor (câmbio, ETFs de referência, juros)."""
    return {k: f for k, f in sorted(fb.facts.items()) if f.issuer_id is None}


def fact_line(fact: Fact) -> str:
    return f"{fact.fact_id}: {fact.formatted} ({fact.name})"


def render_facts_block(fb: FactBook, issuer_ids: Iterable[str], macro: bool = True,
                       fact_ids: Iterable[str] | None = None) -> str:
    """Linhas ``fact_id: valor formatado (nome)`` para os prompts (ordem determinística).

    ``fact_ids`` (opcional) restringe a lista a ids específicos (ex.: só fatos de squeeze).
    """
    wanted = set(issuer_ids)
    allow = set(fact_ids) if fact_ids is not None else None
    lines = []
    for fid in sorted(fb.facts):
        fact = fb.facts[fid]
        if allow is not None and fid not in allow:
            continue
        if fact.issuer_id is None and not macro:
            continue
        if fact.issuer_id is not None and fact.issuer_id not in wanted:
            continue
        lines.append(fact_line(fact))
    return "\n".join(lines)
