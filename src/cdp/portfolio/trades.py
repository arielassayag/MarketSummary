"""Posições-alvo por linha de execução, lista de ordens e sugestões de hedge cambial.

- A carteira é otimizada por EMISSOR; aqui cada peso vira uma posição numa linha negociável:
  long ⇒ ``long_ticker`` (linha de maior liquidez); short ⇒ ``short_ticker`` (linha alugável).
- Quantidades em ações são arredondadas ao menor incremento negociável da linha
  (:func:`share_increment`: 1 ação em todos os mercados da carteira) e são **assinadas**
  (negativas para short). Regras de lote das bolsas (:func:`order_legs_detail`):

  * **B3**: lote padrão de 100 ações no código da linha e o resto (1–99) no mercado
    fracionário, código com sufixo ``F`` (``PETR4`` → ``PETR4F``);
  * **BMV**: o lote é 1 título, mas só ordens de 100 títulos (5, com preço acima de MXN 200)
    formam preço; quantidades menores são "picos", executados ao último preço registrado —
    numa ordem ao fechamento, o próprio fechamento (Reglamento Interior da BMV e glossário);
  * **Santiago, BVC, BVL, BYMA e EUA**: 1 ação, sem lote padrão.

  Com PL pequeno, um lote de 100 ações vale da ordem da posição mínima do mandato
  (``risk.min_position_weight`` × NAV): arredondar ao lote distorceria o peso em até meio lote.
  A posição é uma só (fracionário e pico são a mesma ação); booking e marcação seguem por
  ``execution_ticker``, ao fechamento oficial da linha. Ação muito cara (ex.: MELI, cerca de
  0,19% do NAV por ação com PL de US$ 1 mi) é arredondada à ação inteira mais próxima; o erro de
  arredondamento e as posições que não chegam a uma ação ficam registrados
  (:func:`rounding_report`). Preço/câmbio ausentes ⇒ quantidade ``None`` (nunca 0).
- Ordens comparam alvo × posição atual por TICKER: troca de linha de execução fecha a linha
  antiga e abre a nova.
- Hedge cambial: exposição econômica por moeda "de origem" do emissor (ADRs também carregam
  o câmbio local no preço em USD). Regra anterior: NDF quando |exposição| > limiar × NAV. Com a
  execução no fechamento (PL pequeno), :func:`fx_hedges` com ``futuros=True`` dimensiona o hedge
  em contratos inteiros de minicontratos de bolsa — BRL no mini dólar da B3 (WDO, US$ 10 mil),
  MXN no mini futuro do dólar da MexDer (US$ 1 mil), COP no mini futuro TRM da BVC (US$ 5 mil) —
  e deixa CLP, PEN e ARS sem hedge, com a exposição divulgada (sem futuro listado acessível de
  tamanho compatível; NDF exige nocional mínimo muito acima do PL).
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
from .execucao import fechamentos_necessarios

LOT_SIZE: dict[str, int] = {"BR": 100, "MX": 1, "CL": 1, "CO": 1, "PE": 1, "AR": 1, "US": 1}
"""Lote padrão do mercado de listagem (B3: 100 ações no mercado à vista de lote padrão)."""
#: BMV: ordens que formam preço têm no mínimo 100 títulos (5 com preço acima de MXN 200);
#: abaixo disso são "picos", executados ao último preço registrado (Reglamento Interior da BMV).
BMV_PRICE_LOT = 100
BMV_PRICE_LOT_HIGH = 5
BMV_HIGH_PRICE_MXN = 200.0
DEFAULT_LOT = 1
ODD_LOT_SUFFIX: dict[str, str] = {"BR": "F"}
"""Mercados com livro de lote fracionário e o sufixo do código de negociação (B3: 1 a 99 ações,
``PETR4F``; mesma ação da linha). Nesses mercados a quantidade-alvo é arredondada a 1 ação e a
ordem é dividida em lote padrão + fracionário (:func:`order_legs`)."""
DEFAULT_PARTICIPATION = LiquiditySection().participation_rate
WEIGHT_EPS = 1e-9

COUNTRY_CURRENCY: dict[str, str] = {
    "BR": "BRL", "MX": "MXN", "CL": "CLP", "CO": "COP", "PE": "PEN", "AR": "ARS",
}
HEDGE_INSTRUMENT: dict[str, str] = {"MXN": "Forward 1M (entregável)"}
DEFAULT_HEDGE_INSTRUMENT = "NDF 1M"
NO_HEDGE_INSTRUMENT = "sem hedge (abaixo do limiar)"
#: Minicontratos de bolsa por moeda (PL pequeno): ``(instrumento, tamanho em USD)``. Fontes
#: públicas: B3, especificação do Futuro Míni de Taxa de Câmbio de Reais por Dólar Comercial
#: (WDO, US$ 10.000); MexDer, Futuro "mini" del dólar (US$ 1.000; o padrão DA é de US$ 10.000);
#: BVC, Futuro mini TRM (TRS, US$ 5.000; o padrão é de US$ 50.000).
HEDGE_FUTURES: dict[str, tuple[str, float]] = {
    "BRL": ("Futuro míni de dólar B3 (WDO, US$ 10 mil por contrato)", 10_000.0),
    "MXN": ("Futuro mini do dólar MexDer (US$ 1 mil por contrato)", 1_000.0),
    "COP": ("Futuro mini TRM BVC (US$ 5 mil por contrato)", 5_000.0),
}
#: Moedas sem minicontrato listado acessível: exposição mantida e divulgada.
UNHEDGED_REASON: dict[str, str] = {
    "CLP": "sem futuro de bolsa de tamanho compatível; NDF exige nocional mínimo muito acima do "
           "PL: exposição mantida e divulgada",
    "PEN": "sem futuro de bolsa acessível; exposição mantida e divulgada",
    "ARS": "acesso offshore restrito ao mercado de câmbio argentino; exposição mantida e "
           "divulgada",
}

_ACTION_ORDER = {TradeAction.SELL: 0, TradeAction.COVER: 1, TradeAction.BUY: 2,
                 TradeAction.SHORT: 3}


# ==========================================================
# Utilidades
# ==========================================================

def lot_size(ticker: str) -> int:
    """Lote padrão do mercado de listagem do ticker (B3 = 100; demais = 1)."""
    return LOT_SIZE.get(listing_market(ticker), DEFAULT_LOT)


def share_increment(ticker: str) -> int:
    """Menor quantidade negociável da linha: 1 ação onde há mercado fracionário (B3) ou o lote
    padrão é 1; nos demais casos, o lote padrão."""
    market = listing_market(ticker)
    return 1 if market in ODD_LOT_SUFFIX else LOT_SIZE.get(market, DEFAULT_LOT)


def odd_lot_ticker(ticker: str) -> str | None:
    """Código do mercado fracionário da linha (``PETR4.SA`` → ``PETR4F.SA``); ``None`` se o
    mercado não tem livro fracionário."""
    suffix = ODD_LOT_SUFFIX.get(listing_market(ticker))
    if suffix is None:
        return None
    base, dot, exchange = ticker.partition(".")
    return f"{base}{suffix}{dot}{exchange}"


def order_legs(ticker: str, shares: int) -> list[tuple[str, int]]:
    """Pernas de execução de uma ordem de ``shares`` ações (o sinal é preservado): múltiplos do
    lote padrão no código da linha e o resto no mercado fracionário (B3: ``1.234`` ações de
    ``PETR4.SA`` ⇒ ``[("PETR4.SA", 1200), ("PETR4F.SA", 34)]``). Sem livro fracionário (ou lote
    1), uma única perna; ordem zero, nenhuma."""
    q = int(shares)
    if q == 0:
        return []
    lot = lot_size(ticker)
    odd_ticker = odd_lot_ticker(ticker)
    if odd_ticker is None or lot <= 1:
        return [(ticker, q)]
    sign = 1 if q > 0 else -1
    round_part = (abs(q) // lot) * lot
    odd_part = abs(q) - round_part
    legs = [(ticker, sign * round_part)] if round_part else []
    if odd_part:
        legs.append((odd_ticker, sign * odd_part))
    return legs


def price_setting_lot(ticker: str, price_local: float | None = None) -> int:
    """Quantidade mínima que forma preço no livro principal da linha: B3 100; BMV 100 (5 com
    preço acima de MXN 200; sem preço, 100 — conservador); demais mercados 1."""
    market = listing_market(ticker)
    if market == "MX":
        if price_local is not None and math.isfinite(float(price_local)) \
                and float(price_local) > BMV_HIGH_PRICE_MXN:
            return BMV_PRICE_LOT_HIGH
        return BMV_PRICE_LOT
    return lot_size(ticker)


def order_legs_detail(ticker: str, shares: int, price_local: float | None = None
                      ) -> list[tuple[str, int, str]]:
    """Pernas de execução ``(código, ações assinadas, livro)`` de uma ordem: ``livro`` é
    ``lote_padrao`` (múltiplos do lote que forma preço), ``fracionario`` (B3, código com sufixo
    ``F``), ``pico`` (BMV, mesma série, ao último preço registrado) ou ``unica`` (mercados sem
    lote). Ordem zero ⇒ nenhuma perna."""
    q = int(shares)
    if q == 0:
        return []
    market = listing_market(ticker)
    lot = price_setting_lot(ticker, price_local)
    if lot <= 1:
        return [(ticker, q, "unica")]
    sign = 1 if q > 0 else -1
    round_part = (abs(q) // lot) * lot
    rest = abs(q) - round_part
    legs: list[tuple[str, int, str]] = []
    if round_part:
        legs.append((ticker, sign * round_part, "lote_padrao"))
    if rest:
        odd = odd_lot_ticker(ticker)
        if market in ODD_LOT_SUFFIX and odd is not None:
            legs.append((odd, sign * rest, "fracionario"))
        else:
            legs.append((ticker, sign * rest, "pico"))
    return legs


def max_order_legs(ticker: str) -> int:
    """Número máximo de ordens de uma linha para qualquer quantidade: 2 onde há lote que forma
    preço maior que 1 (B3: lote padrão + fracionário; BMV: lote padrão + pico, conservador sem
    preço), 1 nos demais mercados. A posição mínima da construção usa a banda com esse número
    de ordens, para nunca ficar abaixo da banda da execução (:func:`n_orders`)."""
    return 2 if price_setting_lot(ticker) > 1 else 1


def n_orders(ticker: str, shares: int | None, price_local: float | None = None) -> int:
    """Ordens enviadas para executar ``shares`` (cada perna paga o mínimo por ordem); 1 sem
    quantidade conhecida."""
    if shares is None:
        return 1
    return max(len(order_legs_detail(ticker, int(shares), price_local)), 1)


def rounding_report(targets: list[PositionTarget], nav: float, fx_last: pd.Series
                    ) -> dict[str, object]:
    """Erro do arredondamento a ações inteiras nas posições-alvo (fração do NAV): maior erro
    absoluto (com a linha), soma dos erros absolutos e posições que não chegam a uma ação
    (ficam sem ordem). Ação cara com PL pequeno (ex.: MELI) aparece aqui, nunca escondida."""
    fx = pd.to_numeric(fx_last, errors="coerce")
    worst, worst_tk, total = 0.0, None, 0.0
    zero: list[str] = []
    for t in targets:
        if t.shares is None or t.price_local is None or not nav > 0:
            continue
        rate = 1.0 if t.currency == "USD" else _opt(fx, t.currency)
        if rate is None or not rate > 0:
            continue
        err = (abs(int(t.shares)) * float(t.price_local) * rate - abs(t.notional_usd)) / nav
        total += abs(err)
        if abs(err) > abs(worst):
            worst, worst_tk = err, t.execution_ticker
        if int(t.shares) == 0 and t.weight != 0:
            zero.append(t.execution_ticker)
    return {"maior_erro_pct_nav": worst, "linha_maior_erro": worst_tk,
            "soma_erros_pct_nav": total, "sem_uma_acao": sorted(zero)}


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
    short_participation: float | None = None,
    capacidade_fechamento: pd.Series | None = None,
) -> list[PositionTarget]:
    """Converte pesos por emissor em posições-alvo por linha de execução.

    ``days_to_liquidate`` usa ``participation`` nos longs e ``short_participation`` nos shorts
    (padrão: a mesma participação; o mandato usa ``short_participation_rate`` para shorts).
    Com a execução no fechamento (seção ``execution``), o chamador passa
    ``capacidade_fechamento`` (USD por fechamento por ticker, a capacidade de REDUÇÃO — lado
    comprado da tabela de capacidade) e ``days_to_liquidate`` passa a ser o número de
    FECHAMENTOS para zerar a posição (:func:`cdp.portfolio.execucao.fechamentos_necessarios`;
    ``None`` sem capacidade conhecida ou com o mercado sem fechamento elegível).
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
            shares = round_to_lot(notional / (price * rate), share_increment(ticker))

        adtv = _opt(srow, f"adtv_{leg}_usd") if not srow.empty else None
        if adtv is None and not lrow.empty:
            adtv = _opt(lrow, "adtv_usd")
        adtv = adtv if adtv is not None and adtv > 0 else None
        pct_adtv = abs(notional) / adtv if adtv else None
        part = participation if side == Side.LONG or short_participation is None \
            else short_participation
        if capacidade_fechamento is not None:
            days = fechamentos_necessarios(notional, _opt(capacidade_fechamento, ticker) or 0.0)
        else:
            days = abs(notional) / (part * adtv) if adtv else None

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


def _usd_per_share(t: PositionTarget | None, b: BookedPosition | None) -> float | None:
    """Preço em USD por ação: do alvo (preço atual) ou, na falta, da posição registrada."""
    for notional, shares in ((t.notional_usd, t.shares) if t is not None else (None, None),
                             (b.notional_usd, b.shares) if b is not None else (None, None)):
        if notional is None or not shares:
            continue
        px = abs(float(notional)) / abs(int(shares))
        if math.isfinite(px) and px > 0:
            return px
    return None


def build_trades(
    targets: list[PositionTarget], current: list[BookedPosition] | None, nav: float,
    cost_bps: pd.Series | None = None, participation: float = DEFAULT_PARTICIPATION,
    line_adtv: pd.Series | None = None, *,
    capacidade_long: pd.Series | None = None, capacidade_short: pd.Series | None = None,
    congelados: frozenset[str] | set[str] | None = None,
) -> list[Trade]:
    """Ordens para levar a carteira atual às posições-alvo, linha a linha.

    - Ponta comprada: ``BUY``/``SELL``; ponta vendida: ``SHORT``/``COVER``.
    - Cruzar o zero na mesma linha gera duas ordens (zerar e abrir).
    - Troca de linha de execução: fecha a linha antiga e abre a nova.
    - ``shares`` e ``notional_usd`` são magnitudes; ``weight_change`` tem sinal (positivo
      para BUY/COVER, negativo para SELL/SHORT).
    - ``cost_bps``: custo estimado em bps do valor negociado, indexado por ticker ou emissor.
    - ``line_adtv``: ADTV por ticker para linhas que só existem na carteira atual.
    - Execução no fechamento (seção ``execution``): ``capacidade_long``/``capacidade_short``
      (USD por fechamento por ticker; a de short vale só para ``SHORT``, que abre ou aumenta
      vendido) tornam ``est_days`` o número de FECHAMENTOS para executar a ordem
      (``None`` sem capacidade); ``congelados`` (emissores sem linha negociável no fechamento)
      não geram ordem — as ações ficam como estão.

    Com quantidades conhecidas dos dois lados, a ordem segue a diferença de ações (deriva de
    preço sem mudança de quantidade não gera ordem) e o notional é ações × preço USD por ação
    (do alvo ou da posição registrada), coerente com a ação; sem quantidades, segue a
    diferença de peso.
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
        if congelados and issuer in congelados:
            continue
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
        px = _usd_per_share(t, b) if shares_known else None

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
            if sh is not None and px is not None:
                # Ordem guiada por ações: notional e variação de peso seguem a quantidade, com
                # sinal coerente com a ação (evita VENDA com variação de peso positiva).
                notional = sh * px
                sign = 1.0 if action in (TradeAction.BUY, TradeAction.COVER) else -1.0
                dw = sign * notional / nav
            else:
                notional = abs(dw) * nav
            trades.append(Trade(
                issuer_id=issuer, ticker=ticker, action=action, shares=sh,
                notional_usd=notional, weight_change=float(dw),
                pct_adtv=notional / adtv if adtv else None, est_cost_bps=cost,
                est_days=_est_days(action, ticker, notional, adtv, participation,
                                   capacidade_long, capacidade_short),
                currency=currency,
            ))
    trades.sort(key=lambda x: (x.issuer_id, _ACTION_ORDER[x.action], x.ticker))
    return trades


def _est_days(action: TradeAction, ticker: str, notional: float, adtv: float | None,
              participation: float, cap_long: pd.Series | None,
              cap_short: pd.Series | None) -> float | None:
    """Dias (ADTV × participação) ou, com a capacidade do fechamento, fechamentos."""
    if cap_long is None and cap_short is None:
        return notional / (participation * adtv) if adtv else None
    caps = cap_short if action == TradeAction.SHORT else cap_long
    return fechamentos_necessarios(notional, (_opt(caps, ticker) if caps is not None else None)
                                   or 0.0)


# ==========================================================
# Hedge cambial
# ==========================================================

def home_currency(country: str) -> str:
    """Moeda econômica do emissor pelo país (regionais/US ⇒ USD)."""
    return COUNTRY_CURRENCY.get(country, "USD")


def fx_hedges(targets: list[PositionTarget], nav: float,
              threshold: float = 0.01, *, futuros: bool = False) -> list[FxHedge]:
    """Exposição cambial econômica líquida por moeda e sugestão de hedge.

    A exposição soma os pesos de TODAS as linhas do emissor (local e ADR), pois o preço em USD
    do ADR acompanha o câmbio local. Moedas com |exposição| ≤ ``threshold`` × NAV são
    reportadas com hedge zero. A justificativa informa o caixa necessário na moeda de
    liquidação das linhas locais (compras consomem moeda local; vendas a descoberto geram).

    ``futuros=False`` (regra anterior): NDF/termo de −exposição. ``futuros=True`` (PL pequeno,
    execução no fechamento): contratos INTEIROS do minicontrato de bolsa da moeda
    (:data:`HEDGE_FUTURES`; ``round(|exposição| / tamanho)``, o resíduo fica divulgado) ou sem
    hedge onde não há minicontrato acessível (:data:`UNHEDGED_REASON`).
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
        if futuros:
            out.append(_futures_hedge(ccy, exp, nav, threshold, local_buy.get(ccy, 0.0),
                                      local_short.get(ccy, 0.0)))
            continue
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


def _futures_hedge(ccy: str, exp: float, nav: float, threshold: float, buy: float,
                   short: float) -> FxHedge:
    """Hedge em contratos inteiros do minicontrato de bolsa (ou exposição mantida); valores
    em formato pt-BR."""

    def usd(x: float, signed: bool = False) -> str:
        txt = f"{x:+,.0f}" if signed else f"{x:,.0f}"
        return "USD " + txt.replace(",", ".")

    def pct(x: float, signed: bool = False) -> str:
        return (f"{x:+.2%}" if signed else f"{x:.2%}").replace(".", ",")

    above = abs(exp) > threshold * nav
    spec = HEDGE_FUTURES.get(ccy)
    hedge = 0.0
    if not above:
        instrument = NO_HEDGE_INSTRUMENT
        what = f"Dentro do limiar de {pct(threshold)}: sem hedge."
    elif spec is None:
        instrument = "sem hedge (exposição mantida e divulgada)"
        what = (f"Acima do limiar de {pct(threshold)}, "
                + UNHEDGED_REASON.get(ccy, "sem minicontrato de bolsa acessível; exposição "
                                           "mantida e divulgada") + ".")
    else:
        name, size = spec
        n = int(round(abs(exp) / size))
        hedge = -math.copysign(n * size, exp) if n else 0.0
        instrument = name if n else f"{name}: exposição menor que meio contrato, sem hedge"
        side = "vender" if exp > 0 else "comprar"
        what = (f"Acima do limiar de {pct(threshold)}: {side} {n} "
                f"{'contrato' if n == 1 else 'contratos'} de {usd(size)} ({usd(abs(hedge))}); "
                f"resíduo sem hedge {usd(exp + hedge, True)} "
                f"({pct((exp + hedge) / nav, True)} do NAV).")
    cash = buy - short
    rationale = (
        f"Exposição econômica líquida em {ccy}: {pct(exp / nav, True)} do NAV ({usd(exp)}), "
        "somando linhas locais e ADRs. " + what + " "
        + f"Liquidação local: compras {usd(buy)}, shorts {usd(short)}; "
        + (f"necessidade líquida de comprar {ccy} à vista ≈ {usd(cash)}." if cash > 0 else
           f"excedente líquido em {ccy} ≈ {usd(-cash)} (garantias/conversão)." if cash < 0
           else "sem necessidade líquida de caixa local."))
    return FxHedge(currency=ccy, exposure_usd=float(exp), hedge_notional_usd=float(hedge),
                   instrument=instrument, rationale=rationale)


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
