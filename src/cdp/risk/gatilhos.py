r"""Gatilhos de velocidade de perda e de evento societário (monitor diário de risco).

Base do desvio diário, no risco efetivamente tomado (nunca no mandato):
``σ_d = clip(max(σ_ex-ante,κ, σ_realizada,21d), 2%, 5%)/√252``, com
``σ_ex-ante,κ = √(κ_F·σ_fatorial² + σ_específica²)`` do registro diário.

| Gatilho | Nível | Regra |
|---|---|---|
| ``perda_diaria`` | SOFT | retorno do dia ≤ −3σ_d·√n |
| ``perda_diaria_extrema`` | HARD (kill switch) | retorno do dia ≤ −5σ_d·√n ou ≤ −1,0% (absoluto) |
| ``perda_5_pregoes`` | SOFT | retorno composto de 5 registros ≤ −3σ_d·√(Σn) ou ≤ −2,0% |
| ``janela_incompleta`` | INFO | registros faltando na janela (nunca preenchidos com zero) |
| ``possivel_evento_societario:<ticker>`` | SOFT | \|Δln fechamento − Δln fechamento ajustado\| > 1% numa linha detida |
| ``movimento_extremo:<ticker>`` | INFO | \|Δp local\| > 40% numa linha detida (P&L inalterado) |

``n`` = sessões de informação contidas no retorno do registro, por linha detida: dias úteis
desde o último registro em que a linha foi reprecificada (feriado no mercado local ⇒ a linha
carrega dois pregões no dia seguinte, mesmo que haja registro no feriado porque outro mercado
abriu), média ponderada pelo gross das linhas reprecificadas no dia (aditividade da variância),
nunca abaixo de 1; o limite cresce com √n. Sem posições, ``n`` = dias úteis desde o registro
anterior. O nível HARD usa o prefixo de ação do kill switch do monitor, que só reduz risco; o
acionamento por um único short em stop é tratado por nome (:mod:`cdp.risk.limites`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from ..config import FundConfig
    from ..contracts import DailyRecord
    from ..market import MarketData

SIGMA_FLOOR = 0.02
SIGMA_CAP = 0.05
SOFT_1D_SIGMAS = 3.0
HARD_1D_SIGMAS = 5.0
SOFT_5D_SIGMAS = 3.0
ABS_HARD_1D = -0.010
ABS_SOFT_5D = -0.020
WINDOW_5D = 5
CORP_ACTION_LOG_GAP = 0.01
RAW_JUMP = 0.40
KILL_SWITCH_PREFIX = "kill-switch: "


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def sigma_diaria(rec: DailyRecord, cfg: FundConfig) -> float:
    """``σ_d`` do registro (anual limitado a [2%, 5%] dividido por √252)."""
    k = max(float(cfg.risk.second_order_inflation), 1.0)
    fv, sv = _f(rec.risk.factor_vol), _f(rec.risk.specific_vol)
    ex = math.sqrt(k * fv ** 2 + sv ** 2) if fv is not None and sv is not None \
        else _f(rec.risk.ex_ante_vol)
    rv = _f(rec.risk.realized_vol_21d)
    cands = [x for x in (ex, rv) if x is not None and x > 0]
    base = max(cands) if cands else float(cfg.risk.vol_target_annual)
    return min(max(base, SIGMA_FLOOR), SIGMA_CAP) / math.sqrt(252.0)


def _sessions_spanned(prev: DailyRecord | None, rec: DailyRecord) -> int:
    if prev is None:
        return 1
    n = int(np.busday_count(prev.date, rec.date))
    return max(n, 1)


def sessoes_de_informacao(records_desc: Sequence[DailyRecord]) -> float:
    """``n`` efetivo do retorno do registro mais recente (ver módulo): para cada linha
    reprecificada no dia, dias úteis desde o último registro em que ELA foi reprecificada;
    média ponderada pelo gross; mínimo 1."""
    if not records_desc:
        return 1.0
    rec = records_desc[0]
    prev = records_desc[1] if len(records_desc) > 1 else None
    fallback = float(_sessions_spanned(prev, rec))
    num = den = 0.0
    for pos in rec.positions:
        g = abs(float(pos.weight))
        if g <= 0 or not pos.repriced:
            continue
        last = None
        for older in records_desc[1:]:
            hit = next((q for q in older.positions if q.ticker == pos.ticker), None)
            if hit is None:
                break  # linha não detida antes: o retorno do dia é de um pregão
            if hit.repriced:
                last = older.date
                break
        n = max(int(np.busday_count(last, rec.date)), 1) if last is not None else fallback
        num += g * n
        den += g
    return max(num / den, 1.0) if den > 0 else fallback


def loss_velocity(records_desc: Sequence[DailyRecord], cfg: FundConfig) -> list[dict]:
    """Gatilhos de perda diária e de 5 registros (do mais recente para o mais antigo)."""
    out: list[dict] = []
    if not records_desc:
        return out
    rec = records_desc[0]
    prev = records_desc[1] if len(records_desc) > 1 else None
    sd = sigma_diaria(rec, cfg)
    n = sessoes_de_informacao(records_desc) if prev is not None else 1.0
    r = float(rec.ret)
    soft = -SOFT_1D_SIGMAS * sd * math.sqrt(n)
    hard = min(-HARD_1D_SIGMAS * sd * math.sqrt(n), 0.0)
    if r <= hard or r <= ABS_HARD_1D:
        why = (f"retorno do dia {r:+.2%} ≤ {hard:+.2%} (−5σ diário do livro)" if r <= hard
               else f"retorno do dia {r:+.2%} ≤ {ABS_HARD_1D:+.2%} (limite absoluto)")
        out.append({"nivel": "HARD", "codigo": "perda_diaria_extrema",
                    "mensagem": f"Perda diária extrema: {why}.",
                    "acao": KILL_SWITCH_PREFIX + f"perda diária extrema em {rec.date} ({r:+.2%})"})
    elif r <= soft:
        out.append({"nivel": "SOFT", "codigo": "perda_diaria",
                    "mensagem": f"Perda diária {r:+.2%} ≤ {soft:+.2%} (−3σ diário do livro).",
                    "acao": "revisar exposições e contribuições de risco do dia"})
    window = list(records_desc[:WINDOW_5D])
    if len(window) < WINDOW_5D:
        out.append({"nivel": "INFO", "codigo": "janela_incompleta",
                    "mensagem": f"Janela de {WINDOW_5D} registros incompleta ({len(window)}): "
                                "gatilho de 5 pregões não avaliado.", "acao": ""})
        return out
    start = records_desc[WINDOW_5D] if len(records_desc) > WINDOW_5D else None
    span = (int(np.busday_count(start.date, window[0].date)) if start is not None
            else int(np.busday_count(window[-1].date, window[0].date)) + 1)
    gaps = int(np.busday_count(window[-1].date, window[0].date)) + 1 - len(window)
    if gaps > 2:
        out.append({"nivel": "INFO", "codigo": "janela_incompleta",
                    "mensagem": f"{gaps} dias úteis sem registro na janela de {WINDOW_5D} "
                                "registros (retornos ausentes não viram zero).", "acao": ""})
    comp = float(np.prod([1.0 + float(x.ret) for x in window]) - 1.0)
    lim5 = -SOFT_5D_SIGMAS * sd * math.sqrt(max(span, WINDOW_5D))
    if comp <= lim5 or comp <= ABS_SOFT_5D:
        out.append({"nivel": "SOFT", "codigo": "perda_5_pregoes",
                    "mensagem": f"Perda acumulada em {WINDOW_5D} registros {comp:+.2%} "
                                f"(limites {lim5:+.2%} pelo σ do livro e {ABS_SOFT_5D:+.2%}).",
                    "acao": "revisão de risco antes do próximo rebalanceamento"})
    return out


def price_jumps(rec: DailyRecord, md: MarketData | None) -> list[dict]:
    """Detector de evento societário nas linhas detidas: divergência entre a variação do
    fechamento e a do fechamento ajustado (> 1% em log) no dia do registro; movimento bruto
    > 40% fica só informativo. P&L e NAV não são alterados."""
    out: list[dict] = []
    if md is None:
        return out
    ts = pd.Timestamp(rec.date)
    held = sorted({p.ticker for p in rec.positions if p.shares})
    close, adj = md.close, md.adj_close
    for t in held:
        if t not in close.columns or t not in adj.columns:
            continue
        c = close[t].loc[:ts].dropna()
        a = adj[t].loc[:ts].dropna()
        if len(c) < 2 or len(a) < 2 or c.index[-1] != ts or a.index[-1] != ts:
            continue
        dc = math.log(float(c.iloc[-1]) / float(c.iloc[-2])) if c.iloc[-2] > 0 else None
        da = math.log(float(a.iloc[-1]) / float(a.iloc[-2])) if a.iloc[-2] > 0 else None
        if dc is None or da is None:
            continue
        if abs(dc - da) > CORP_ACTION_LOG_GAP:
            out.append({"nivel": "SOFT", "codigo": f"possivel_evento_societario:{t}",
                        "mensagem": f"{t}: variação do fechamento {math.expm1(dc):+.1%} difere "
                                    f"da do fechamento ajustado {math.expm1(da):+.1%} — possível "
                                    "grupamento, desdobramento ou provento.",
                        "acao": "conferir o evento societário antes do próximo rebalanceamento"})
        if abs(math.expm1(dc)) > RAW_JUMP:
            out.append({"nivel": "INFO", "codigo": f"movimento_extremo:{t}",
                        "mensagem": f"{t}: fechamento variou {math.expm1(dc):+.1%} no dia.",
                        "acao": ""})
    return out


__all__ = ["KILL_SWITCH_PREFIX", "loss_velocity", "price_jumps", "sessoes_de_informacao",
           "sigma_diaria"]
