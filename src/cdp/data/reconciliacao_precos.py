"""Reconcilia uma lacuna documentada sem regravar o incremento original."""
from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import pandas as pd

from ..contracts import SourceRecord
from ..leitura_arquivos import ler_bytes, raiz_recebida
from .eventos_corporativos import comparable_basis

_PREV = date(2026, 11, 16)
_DAY = date(2026, 11, 17)
_TICKER = "EMBJ"
_EVIDENCE = Path("docs/cdp/evidencias/eventos_corporativos")
_SOURCES = {
    "nasdaq": (
        "https://api.nasdaq.com/api/quote/EMBJ/historical?assetclass=stocks"
        "&fromdate=2026-11-16&todate=2026-11-17",
        "14993020b5db4da57ad4ba2f661855840870dfc182cff18d260676b86927baf9",
        datetime(2026, 11, 20, 23, 16, 7, tzinfo=UTC),
    ),
    "yahoo": (
        "https://query2.finance.yahoo.com/v8/finance/chart/EMBJ?period1=1794528000"
        "&period2=1795219200&interval=1d&events=div%2Csplits%2CcapitalGains",
        "78d443f2b0c7bd111326a0c48c77e21e5bc58d47fa3f4d5f8e03f6bd8d766b5b",
        datetime(2026, 11, 20, 23, 16, 18, tzinfo=UTC),
    ),
}


def reconcile_prices(base, increments, actions, as_of):
    """Devolve a visão de preços com a lacuna resolvida e os hashes da prova, se usada."""
    if as_of < _DAY or not increments:
        return increments, {}

    rows = [frame.loc[frame["ticker"].eq(_TICKER)] for frame in (base, *increments)]
    for i, (frame, ticker_rows) in enumerate(zip(increments, rows[1:], strict=True)):
        target = ticker_rows.loc[ticker_rows["date"].eq(pd.Timestamp(_DAY))]
        if target.empty or comparable_basis(next(target.itertuples()), pd.Timestamp(_PREV)):
            continue
        previous = pd.concat(rows[:i + 1])
        previous = previous.loc[(previous["date"] < pd.Timestamp(_DAY)) & (previous["close"] > 0)]
        if (len(target) != 1 or previous.empty
                or previous["date"].max() != pd.Timestamp(_PREV)
                or pd.Timestamp(target.iloc[0]["prev_date"]) != pd.Timestamp(_PREV)):
            raise ValueError("Predecessor de EMBJ diverge da janela reconciliada")

        latest = previous.loc[previous["date"].eq(pd.Timestamp(_PREV))]
        if len(latest) != 1:
            raise ValueError("Predecessor duplicado na janela reconciliada de EMBJ")
        first, last = latest.iloc[0], target.iloc[0]
        if not any(e.ticker == _TICKER and e.effective_on == _PREV and e.quantity_factor == 4
                   for e in actions) or any(e.ticker == _TICKER and _PREV < e.effective_on <= _DAY
                                            for e in actions):
            raise ValueError("Vigência do evento de EMBJ diverge da janela reconciliada")

        root = raiz_recebida() or Path(__file__).resolve().parents[3]
        proofs, data = {}, {}
        for provider, (_, expected, _) in _SOURCES.items():
            name = _EVIDENCE / f"{_TICKER}-{_DAY}-{provider}.json"
            raw = ler_bytes(root / name)
            if sha256(raw).hexdigest() != expected:
                raise ValueError(f"Evidência de preços {name.name} adulterada")
            proofs[name.as_posix()] = expected
            data[provider] = json.loads(raw)

        nasdaq = data["nasdaq"]["data"]
        yahoo = data["yahoo"]["chart"]["result"][0]
        yahoo_dates = [datetime.fromtimestamp(t, UTC).date() for t in yahoo["timestamp"]]
        days = [datetime.fromtimestamp(e["date"], UTC).date()
                for group in yahoo.get("events", {}).values() for e in group.values()]
        if (nasdaq["symbol"] != _TICKER or yahoo["meta"]["symbol"] != _TICKER
                or yahoo["meta"]["currency"] != "USD" or _PREV not in days
                or any(_PREV < d <= _DAY for d in days)):
            raise ValueError("Evidência de ticker, moeda ou eventos divergente para EMBJ")

        closes = {datetime.strptime(r["date"], "%m/%d/%Y").date(): float(r["close"].removeprefix("$"))
                  for r in nasdaq["tradesTable"]["rows"]}
        adj = yahoo["indicators"]["adjclose"][0]["adjclose"][yahoo_dates.index(_DAY)]
        for day, row in ((_PREV, first), (_DAY, last)):
            if not all(math.isclose(row[c], closes[day], rel_tol=0, abs_tol=1e-5)
                       for c in ("close", "adj_close")):
                raise ValueError("Preço selado de EMBJ diverge da fonte de reconciliação")
        if not math.isclose(last["adj_close"], adj, rel_tol=0, abs_tol=1e-5):
            raise ValueError("Preço ajustado de EMBJ diverge da consulta de reconciliação")

        repaired = list(increments)
        repaired[i] = frame.copy()
        repaired[i].loc[target.index, "prev_close_window"] = first["close"]
        repaired[i].loc[target.index, "prev_adj_close_window"] = first["adj_close"]
        return repaired, proofs

    return increments, {}


def sources():
    return [
        SourceRecord(source_id=f"reconciliacao_embj_{provider}", name=provider, url=url,
                     fields=["close"] if provider == "nasdaq" else ["adj_close", "events"],
                     retrieved_at=when, point_in_time=False)
        for provider, (url, _, when) in _SOURCES.items()
    ]
