"""Posições-alvo por linha de execução, lista de ordens e sugestões de hedge cambial.

- A carteira é otimizada por EMISSOR; aqui cada peso vira uma posição numa linha negociável:
  long ⇒ ``long_ticker`` (linha de maior liquidez); short ⇒ ``short_ticker`` (linha alugável).
- Quantidades em ações são arredondadas ao lote padrão do mercado (B3: 100; demais: 1) e são
  **assinadas** (negativas para short). Preço/câmbio ausentes ⇒ quantidade ``None`` (nunca 0).
- Ordens comparam alvo × posição atual por TICKER: troca de linha de execução fecha a linha
  antiga e abre a nova.
- Hedge cambial: exposição econômica por moeda "de origem" do emissor (ADRs também carregam
  o câmbio local no preço em USD), sugerindo NDF quando |exposição| > limiar × NAV.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd

from ..config import LiquiditySection
from ..contracts import (
    BookedPosition,
    FxHedge,
    LineType,
    PositionTarget,
    Side,
    Trade,
    TradeAction,
)
from ..universe import listing_market

LOT_SIZE: dict[str, int] = {"BR": 100, "MX": 1, "CL": 1, "CO": 1, "PE": 1, "AR": 1, "US": 1}
DEFAULT_LOT = 1
DEFAULT_PARTICIPATION = LiquiditySection().participation_rate
WEIGHT_EPS = 1e-9

COUNTRY_CURRENCY: dict[str, str] = {
    "BR": "BRL", "MX": "MXN", "CL": "CLP", "CO": "COP", "PE": "PEN", "AR": "ARS",
}
HEDGE_INSTRUMENT: dict[str, str] = {"MXN": "Forward 1M (entregável)"}
DEFAULT_HEDGE_INSTRUMENT = "NDF 1M"
NO_HEDGE_INSTRUMENT = "sem hedge (abaixo do limiar)"

_ACTION_ORDER = {TradeAction.SELL: 0, TradeAction.COVER: 1, TradeAction.BUY: 2,
                 TradeAction.SHORT: 3}


# ==========================================================
# Utilidades
# ==========================================================

def lot_size(ticker: str) -> int:
    """Lote padrão do mercado de listagem do ticker (B3 = 100; demais = 1)."""
    return LOT_SIZE.get(listing_market(ticker), DEFAULT_LOT)


def round_to_lot(quantity: float, lot: int) -> int:
    """Arredonda (meio para longe de zero) ao múltiplo de ``lot``, preservando o sinal."""
    if not math.isfinite(quantity):
        raise ValueError("Quantidade não finita não pode ser arredondada.")
    lots = math.floor(abs(quantity) / lot + 0.5)
    return int(math.copysign(lots * lot, quantity)) if lots else 0


def _opt(series: pd.Series | None, key: str) -> float | None:
    if series is None or key not in series.index:
        return None
    v = series.loc[key]
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _text(v: object) -> str | None:
    if isinstance(v, str) and v.strip() and v.strip().lower() not in ("nan", "none"):
        return v.strip()
    return None


def _line_type(raw: object, fallback: object) -> LineType:
    for cand in (raw, fallback):
        t = _text(cand)
        if t is None:
            continue
        t = t.upper()
        if t.startswith("LOCAL"):
            return LineType.LOCAL
        if t in LineType.__members__:
            return LineType(t)
    raise ValueError(f"Tipo de linha desconhecido: {raw!r}/{fallback!r}")


def _row(df: pd.DataFrame | None, key: str) -> pd.Series:
    if df is None or key not in df.index:
        return pd.Series(dtype=object)
    return df.loc[key]


# ==========================================================
# Posições-alvo
# ==========================================================

def build_positions(
    weights: pd.Series, sides: pd.DataFrame, panel_lines: pd.DataFrame,
    panel_assets: pd.DataFrame, squeeze: pd.DataFrame | None, alpha: pd.Series | None,
    alpha_z: pd.Series | None, view_scores: pd.Series | None, risk_contrib: pd.Series | None,
    betas: pd.Series | None, nav: float, fx_last: pd.Series,
    participation: float = DEFAULT_PARTICIPATION,
) -> list[PositionTarget]:
    """Converte pesos por emissor em posições-alvo por linha de execução.

    Erros explícitos: peso ``NaN``; short sem linha de short; long sem linha comprada nem
    linha primária; moeda da linha desconhecida. Ordenação: longs por peso decrescente,
    depois shorts do maior para o menor (empate por ``issuer_id``).
    """
    if not nav > 0:
        raise ValueError("NAV precisa ser positivo.")
    w = pd.to_numeric(weights, errors="coerce")
    if w.isna().any():
        raise ValueError(f"Pesos com NaN: {list(w.index[w.isna()])}")
    w = w[w.abs() > WEIGHT_EPS]
    fx = pd.to_numeric(fx_last, errors="coerce")
    out: list[PositionTarget] = []
    for iid, wt in w.items():
        iid = str(iid)
        side = Side.LONG if wt > 0 else Side.SHORT
        leg = "long" if side == Side.LONG else "short"
        srow = _row(sides, iid)
        arow = _row(panel_assets, iid)
        ticker = _text(srow.get(f"{leg}_ticker"))
        if ticker is None:
            if side == Side.SHORT:
                raise ValueError(f"Short em {iid} sem linha de short (não alugável).")
            ticker = _text(arow.get("primary_ticker"))
            if ticker is None:
                raise ValueError(f"Long em {iid} sem linha de execução.")
        lrow = _row(panel_lines, ticker)
        line_type = _line_type(srow.get(f"{leg}_line_type"), lrow.get("line_type"))
        currency = _text(srow.get(f"{leg}_currency")) or _text(lrow.get("currency"))
        if currency is None:
            raise ValueError(f"Moeda desconhecida para a linha {ticker} ({iid}).")
        notional = float(wt) * nav

        price = _opt(lrow, "last_price_local") if not lrow.empty else None
        rate = 1.0 if currency == "USD" else _opt(fx, currency)
        shares = None
        if price is not None and price > 0 and rate is not None and rate > 0:
            shares = round_to_lot(notional / (price * rate), lot_size(ticker))

        adtv = _opt(srow, f"adtv_{leg}_usd") if not srow.empty else None
        if adtv is None and not lrow.empty:
            adtv = _opt(lrow, "adtv_usd")
        adtv = adtv if adtv is not None and adtv > 0 else None
        pct_adtv = abs(notional) / adtv if adtv else None
        days = abs(notional) / (participation * adtv) if adtv else None

        bucket = "NA"
        score = None
        if squeeze is not None and iid in squeeze.index:
            b = squeeze.loc[iid].get("bucket")
            bucket = str(b).upper() if isinstance(b, str) else "NA"
            bucket = bucket if bucket in ("LOW", "MEDIUM", "HIGH", "NA") else "NA"
            score = _opt(squeeze.loc[iid], "squeeze_score")
        fee = _opt(srow, "borrow_fee_annual") if side == Side.SHORT and not srow.empty else None
        vs = _opt(view_scores, iid)

        out.append(PositionTarget(
            issuer_id=iid,
            name=_text(arow.get("issuer_name")) or iid,
            country=_text(arow.get("country")) or "NA",
            sector=_text(arow.get("sector")) or "NA",
            side=side, weight=float(wt), notional_usd=notional, execution_ticker=ticker,
            line_type=line_type, currency=currency, price_local=price, shares=shares,
            adtv_usd=adtv, pct_adtv=pct_adtv, days_to_liquidate=days, squeeze_score=score,
            squeeze_bucket=bucket, borrow_fee_annual=fee, alpha_annual=_opt(alpha, iid),
            alpha_z=_opt(alpha_z, iid), view_score=None if vs is None else int(round(vs)),
            risk_contribution=_opt(risk_contrib, iid), beta=_opt(betas, iid),
        ))
    out.sort(key=lambda p: (0 if p.side == Side.LONG else 1, -abs(p.weight), p.issuer_id))
    return out


# ==========================================================
# Ordens
# ==========================================================

def _signed_shares(shares: int | None, weight: float) -> int | None:
    """Normaliza o sinal das ações ao sinal do peso (aceita convenção sem sinal)."""
    if shares is None:
        return None
    return int(math.copysign(abs(int(shares)), weight)) if weight != 0 else int(shares)


def build_trades(
    targets: list[PositionTarget], current: list[BookedPosition] | None, nav: float,
    cost_bps: pd.Series | None = None, participation: float = DEFAULT_PARTICIPATION,
    line_adtv: pd.Series | None = None,
) -> list[Trade]:
    """Ordens para levar a carteira atual às posições-alvo, linha a linha.

    - Ponta comprada: ``BUY``/``SELL``; ponta vendida: ``SHORT``/``COVER``.
    - Cruzar o zero na mesma linha gera duas ordens (zerar e abrir).
    - Troca de linha de execução: fecha a linha antiga e abre a nova.
    - ``shares`` e ``notional_usd`` são magnitudes; ``weight_change`` tem sinal.
    - ``cost_bps``: custo estimado em bps do valor negociado, indexado por ticker ou emissor.
    - ``line_adtv``: ADTV por ticker para linhas que só existem na carteira atual.

    Com quantidades conhecidas dos dois lados, a ordem segue a diferença de ações (deriva de
    preço sem mudança de quantidade não gera ordem); sem quantidades, segue a diferença de peso.
    """
    if not nav > 0:
        raise ValueError("NAV precisa ser positivo.")
    tgt: dict[str, PositionTarget] = {}
    for t in targets:
        if t.execution_ticker in tgt:
            raise ValueError("Ticker de execução duplicado nas posições-alvo: "
                             f"{t.execution_ticker}")
        tgt[t.execution_ticker] = t
    cur: dict[str, BookedPosition] = {}
    for b in current or []:
        if b.ticker in cur:
            raise ValueError(f"Ticker duplicado na carteira atual: {b.ticker}")
        cur[b.ticker] = b

    trades: list[Trade] = []
    for ticker in sorted(set(tgt) | set(cur)):
        t = tgt.get(ticker)
        b = cur.get(ticker)
        ref = t if t is not None else b
        assert ref is not None  # ticker vem da união das duas fontes
        issuer, currency = ref.issuer_id, ref.currency
        new_w = t.weight if t is not None else 0.0  # sem alvo: linha deve ser zerada
        old_w = b.weight if b is not None else 0.0  # sem posição atual: nada a desfazer
        new_sh = (_signed_shares(t.shares, t.weight) if t is not None else 0)
        old_sh = (_signed_shares(b.shares, b.weight) if b is not None else 0)
        shares_known = new_sh is not None and old_sh is not None
        if shares_known and new_sh == old_sh:
            continue
        if not shares_known and abs(new_w - old_w) <= WEIGHT_EPS:
            continue

        adtv = t.adtv_usd if t is not None and t.adtv_usd else _opt(line_adtv, ticker)
        cost = _opt(cost_bps, ticker)
        if cost is None:
            cost = _opt(cost_bps, issuer)

        legs: list[tuple[TradeAction, float, int | None]] = []
        if old_w > 0 > new_w or old_w < 0 < new_w:
            close = TradeAction.SELL if old_w > 0 else TradeAction.COVER
            open_ = TradeAction.SHORT if new_w < 0 else TradeAction.BUY
            legs.append((close, -old_w, abs(old_sh) if shares_known else None))
            legs.append((open_, new_w, abs(new_sh) if shares_known else None))
        else:
            dw = new_w - old_w
            dsh = new_sh - old_sh if new_sh is not None and old_sh is not None else None
            long_side = old_w > 0 or new_w > 0 or (old_w == 0 == new_w and (dsh or 0) > 0)
            direction = dsh if dsh is not None else dw
            if long_side:
                action = TradeAction.BUY if direction > 0 else TradeAction.SELL
            else:
                action = TradeAction.SHORT if direction < 0 else TradeAction.COVER
            legs.append((action, dw, abs(dsh) if dsh is not None else None))

        for action, dw, sh in legs:
            notional = abs(dw) * nav
            trades.append(Trade(
                issuer_id=issuer, ticker=ticker, action=action, shares=sh,
                notional_usd=notional, weight_change=float(dw),
                pct_adtv=notional / adtv if adtv else None, est_cost_bps=cost,
                est_days=notional / (participation * adtv) if adtv else None,
                currency=currency,
            ))
    trades.sort(key=lambda x: (x.issuer_id, _ACTION_ORDER[x.action], x.ticker))
    return trades


# ==========================================================
# Hedge cambial
# ==========================================================

def home_currency(country: str) -> str:
    """Moeda econômica do emissor pelo país (regionais/US ⇒ USD)."""
    return COUNTRY_CURRENCY.get(country, "USD")


def fx_hedges(targets: list[PositionTarget], nav: float,
              threshold: float = 0.01) -> list[FxHedge]:
    """Exposição cambial econômica líquida por moeda e sugestão de hedge (NDF = −exposição).

    A exposição soma os pesos de TODAS as linhas do emissor (local e ADR), pois o preço em USD
    do ADR acompanha o câmbio local. Moedas com |exposição| ≤ ``threshold`` × NAV são
    reportadas com hedge zero. A justificativa informa o caixa necessário na moeda de
    liquidação das linhas locais (compras consomem moeda local; vendas a descoberto geram).
    """
    if not nav > 0:
        raise ValueError("NAV precisa ser positivo.")
    exposure: dict[str, float] = defaultdict(float)
    local_buy: dict[str, float] = defaultdict(float)
    local_short: dict[str, float] = defaultdict(float)
    for t in targets:
        ccy = home_currency(t.country)
        exposure[ccy] += t.weight * nav
        if t.currency != "USD":
            if t.notional_usd > 0:
                local_buy[t.currency] += t.notional_usd
            else:
                local_short[t.currency] += -t.notional_usd
    out: list[FxHedge] = []
    for ccy in sorted((set(exposure) | set(local_buy) | set(local_short)) - {"USD"}):
        exp = exposure.get(ccy, 0.0)  # sem posição na moeda: exposição nula
        hedge_on = abs(exp) > threshold * nav
        hedge = -exp if hedge_on else 0.0
        buy = local_buy.get(ccy, 0.0)
        short = local_short.get(ccy, 0.0)
        cash = buy - short
        direction = ("vender" if exp > 0 else "comprar") + f" {ccy} a termo"
        rationale = (
            f"Exposição econômica líquida em {ccy}: {exp / nav:+.2%} do NAV "
            f"(USD {exp:,.0f}), somando linhas locais e ADRs. "
            + (f"Acima do limiar de {threshold:.1%}: sugerido {direction} "
               f"(USD {abs(hedge):,.0f}). " if hedge_on else
               f"Dentro do limiar de {threshold:.1%}: sem hedge. ")
            + f"Liquidação local: compras USD {buy:,.0f}, shorts USD {short:,.0f}; "
            + (f"necessidade líquida de comprar {ccy} à vista ≈ USD {cash:,.0f}."
               if cash > 0 else
               f"excedente líquido em {ccy} ≈ USD {-cash:,.0f} (garantias/conversão)."
               if cash < 0 else "sem necessidade líquida de caixa local.")
            + (" ARS: NDF offshore com liquidez limitada; validar custo." if ccy == "ARS" else "")
        )
        out.append(FxHedge(
            currency=ccy, exposure_usd=float(exp), hedge_notional_usd=float(hedge),
            instrument=HEDGE_INSTRUMENT.get(ccy, DEFAULT_HEDGE_INSTRUMENT) if hedge_on
            else NO_HEDGE_INSTRUMENT,
            rationale=rationale,
        ))
    return out


def positions_frame(targets: list[PositionTarget]) -> pd.DataFrame:
    """Tabela das posições-alvo (para UI/CSV), uma linha por emissor."""
    if not targets:
        return pd.DataFrame(columns=list(PositionTarget.model_fields))
    df = pd.DataFrame([t.model_dump(mode="json") for t in targets])
    return df.set_index("issuer_id", drop=False)


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    """Tabela das ordens (para UI/CSV)."""
    if not trades:
        return pd.DataFrame(columns=list(Trade.model_fields))
    return pd.DataFrame([t.model_dump(mode="json") for t in trades])


def summarize_liquidity(targets: list[PositionTarget]) -> dict[str, float]:
    """Métricas agregadas de liquidez das posições-alvo (NaN quando sem dado)."""
    days = np.array([t.days_to_liquidate for t in targets if t.days_to_liquidate is not None])
    missing = sum(1 for t in targets if t.days_to_liquidate is None)
    return {
        "max_days_to_liquidate": float(days.max()) if days.size else float("nan"),
        "median_days_to_liquidate": float(np.median(days)) if days.size else float("nan"),
        "n_missing_adtv": float(missing),
    }
