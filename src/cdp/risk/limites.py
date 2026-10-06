"""Limites de entrada de short e controles por nome (camada de gestão de risco).

- **Vetos de short novo** (``squeeze.enforce_entry_blocks``): nenhum short novo ou aumentado
  (i) com divulgação de resultado em até ``catalyst_block_sessions`` pregões (janela em dias
  corridos ``⌈sessões·7/5⌉`` a partir da data da decisão; data ESTIMADA bloqueia se a janela de
  ±7 dias da estimativa tocar a janela de veto; estimativa com incerteza maior que ±7 dias —
  sem histórico de datas do emissor — é só sinalizada); (ii) com free float abaixo de
  ``free_float_min_pct``. Free float desconhecido: veto (falha fechada) se o valor de mercado
  for menor que ``free_float_mcap_low_usd`` ou desconhecido; acima disso, só sinalizado. Data de
  resultado desconhecida: sem veto e sinalizada (nunca "sem evento" em silêncio). Todas as datas
  candidatas do emissor são avaliadas (uma estimativa larga nunca desloca uma data confirmada).
  ``controller_max_pct`` não tem fonte pública estruturada: registrado como ``sem_fonte``.
  Cobrir (reduzir) um short é sempre permitido.
- **Stop de squeeze por nome** (``squeeze.stop_scope = "name"``): o short em stop é cortado à
  metade (``max_short = 0,5·|w⁰|``) e o nome não pode ficar comprado até a revisão humana.
- **Grupos de controle** (``risk_model.linked_groups``): holding e controlada são a mesma aposta
  econômica; o peso de mesmo sinal do grupo não passa do teto por nome (limite operacional).

Fontes públicas: datas de resultado e free float vêm de :mod:`cdp.data.publico` quando os
arquivos arquivados existem (CVM IPE/FRE, SEC, Yahoo), senão do snapshot (Yahoo); a leitura é
sempre offline (só arquivos já arquivados), para a decisão ser reproduzível.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from ..config import FundConfig
    from ..contracts import DailyRecord
    from ..market import MarketData

ESTIMATE_HALF_WINDOW_DAYS = 7
#: Resultado divulgado há até tantos dias: o trimestre está coberto (a próxima data não é
#: "desconhecida") e a estimativa do mesmo trimestre é descartada pela fonte pública.
RECENT_RESULT_DAYS = 30
BLOCK_COLUMNS = ["catalyst_block", "float_block", "data_resultado", "resultado_estimado",
                 "free_float", "fonte_free_float", "motivo", "dado_ausente"]


def catalyst_window_days(cfg: FundConfig) -> int:
    """Janela de veto em dias corridos: ``⌈catalyst_block_sessions · 7/5⌉``."""
    return int(math.ceil(cfg.squeeze.catalyst_block_sessions * 7 / 5))


# ----------------------------------------------------------------------------- insumos


def _optional_kwargs(fn, **kw) -> dict:
    """Só os argumentos nomeados que a função pública aceita (interface estável e tolerante)."""
    import inspect

    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    return {k: v for k, v in kw.items() if k in params}


def _publico():
    try:
        from ..data import publico  # type: ignore[attr-defined]
    except ImportError:
        return None
    return publico


def _too_wide(est: bool, width: Any) -> bool:
    """Estimativa com incerteza maior que ±7 dias (sem histórico de datas do emissor)."""
    try:
        wv = float(width)
    except (TypeError, ValueError):
        return False
    return bool(est) and math.isfinite(wv) and wv > 2 * ESTIMATE_HALF_WINDOW_DAYS


def _half_window(est: bool, width: Any) -> int:
    """Meia-janela de incerteza da data (0 se confirmada)."""
    if not est:
        return 0
    try:
        wv = float(width)
    except (TypeError, ValueError):
        return ESTIMATE_HALF_WINDOW_DAYS
    return int(math.ceil(wv / 2)) if math.isfinite(wv) else ESTIMATE_HALF_WINDOW_DAYS


def _rank(est: bool, width: Any) -> int:
    """Preferência de exibição: confirmada < estimada (±7) < estimada larga."""
    return 0 if not est else (2 if _too_wide(est, width) else 1)


def earnings_calendar(issuers: Sequence[str], week: date, as_of: date,
                      squeeze: pd.DataFrame | None, md: MarketData | None = None,
                      *, horizon_days: int = 45) -> pd.DataFrame:
    """Datas de resultado relevantes para a decisão de ``week``, por emissor.

    Colunas: ``data``/``estimada``/``fonte``/``janela_dias`` (a data de referência, para
    exibição: confirmada antes de estimada, estimada larga por último), ``candidatos`` (TODAS as
    datas relevantes, ``(data, estimada, fonte, janela_dias)``, avaliadas uma a uma pelos vetos)
    e ``resultado_recente`` (resultado confirmado nos últimos ``RECENT_RESULT_DAYS`` dias).

    Relevante: data confirmada ≥ ``week``; data estimada cuja janela de incerteza ainda alcança
    ``week`` (uma estimativa alguns dias ANTES da decisão, de empresa que ainda não divulgou,
    continua relevante). Fontes: calendário público arquivado
    (:func:`cdp.data.publico.eventos_corporativos`, CVM no Brasil; data imputada pelo ano
    anterior marcada ``estimada``), consultado desde ``week − 7 − RECENT_RESULT_DAYS`` dias
    (a fonte descarta a estimativa de um trimestre já divulgado), e a data do snapshot
    (``days_to_earnings`` da tabela de squeeze, a partir de ``as_of``)."""
    idx = pd.Index(sorted(map(str, issuers)), name="issuer_id")
    cands: dict[str, list[tuple[date, bool, str, int | None]]] = {i: [] for i in idx}
    recent: set[str] = set()

    def offer(iid: str, d: date, est: bool, src: str, width: int | None = None) -> None:
        if iid not in cands:
            return
        if not est and d < week:
            if d >= week - timedelta(days=RECENT_RESULT_DAYS):
                recent.add(iid)
            return
        if d + timedelta(days=_half_window(est, width)) < week:
            return
        item = (d, bool(est), src, width)
        if item not in cands[iid]:
            cands[iid].append(item)

    pub = _publico()
    if pub is not None and md is not None and not md.is_synthetic \
            and hasattr(pub, "eventos_corporativos"):
        desde = week - timedelta(days=ESTIMATE_HALF_WINDOW_DAYS + RECENT_RESULT_DAYS)
        try:
            ev = pub.eventos_corporativos(list(idx), desde, week + timedelta(days=horizon_days),
                                          offline=True, **_optional_kwargs(
                                              pub.eventos_corporativos,
                                              as_of=as_of, universe=md.universe))
        except Exception:  # noqa: BLE001 - calendário público é complementar; nunca derruba
            ev = None
        if isinstance(ev, pd.DataFrame) and not ev.empty and "issuer_id" in ev.columns:
            ev = ev[ev.get("tipo", pd.Series("resultado", index=ev.index)) == "resultado"]
            for _, r in ev.iterrows():
                try:
                    d = pd.Timestamp(r["data"]).date()
                except (TypeError, ValueError):
                    continue
                width = None
                try:
                    ini, fim = r.get("janela_inicio"), r.get("janela_fim")
                    if ini is not None and fim is not None and not pd.isna(ini) \
                            and not pd.isna(fim):
                        width = (pd.Timestamp(fim).date() - pd.Timestamp(ini).date()).days
                except (TypeError, ValueError):
                    width = None
                offer(str(r["issuer_id"]), d, bool(r.get("estimada", False)),
                      str(r.get("fonte") or "publico"), width)
    if squeeze is not None and "days_to_earnings" in squeeze.columns:
        dte = pd.to_numeric(squeeze["days_to_earnings"], errors="coerce")
        for iid, v in dte.items():
            if np.isfinite(v):
                offer(str(iid), as_of + timedelta(days=int(v)), False, "YAHOO")
    rows: dict[str, dict[str, Any]] = {}
    for i in idx:
        lst = sorted(cands[i], key=lambda c: (_rank(c[1], c[3]), c[0], c[2]))
        top = lst[0] if lst else None
        rows[i] = {"data": top[0] if top else None, "estimada": top[1] if top else False,
                   "fonte": top[2] if top else None, "janela_dias": top[3] if top else None,
                   "candidatos": tuple(sorted(lst, key=lambda c: (c[0], c[1], c[2]))),
                   "resultado_recente": i in recent}
    return pd.DataFrame.from_dict(rows, orient="index").reindex(idx)


def free_float_table(issuers: Sequence[str], md: MarketData, as_of: date) -> pd.DataFrame:
    """Free float (fração em (0, 1]) por emissor e fonte: público arquivado (CVM FRE / Yahoo
    floatShares) quando disponível, senão a razão ``float_shares/shares_outstanding`` do
    snapshot (mediana entre linhas válidas; inválida ⇒ ``NaN``)."""
    from ..analytics.squeeze import float_fraction

    idx = pd.Index(sorted(map(str, issuers)), name="issuer_id")
    out = pd.DataFrame({"free_float": np.nan, "fonte": None}, index=idx, dtype=object)
    lines = md.universe.lines
    if "issuer_id" in lines.columns and md.fundamentals is not None \
            and not md.fundamentals.empty:
        issuer = lines["issuer_id"].astype(str)
        frac = float_fraction(md.fundamentals, issuer)
        by = frac.groupby(issuer).median()
        for i in idx:
            v = by.get(i)
            if v is not None and np.isfinite(v):
                out.at[i, "free_float"] = float(v)
                out.at[i, "fonte"] = "SIMULADO" if md.is_synthetic else "YAHOO"
    pub = _publico()
    if pub is not None and not md.is_synthetic and hasattr(pub, "free_float"):
        try:
            ff = pub.free_float(list(idx), as_of, offline=True,
                                **_optional_kwargs(pub.free_float, universe=md.universe))
        except Exception:  # noqa: BLE001 - fonte pública complementar; nunca derruba
            ff = None
        if isinstance(ff, pd.DataFrame) and not ff.empty and "issuer_id" in ff.columns:
            for _, r in ff.iterrows():
                v = pd.to_numeric(pd.Series([r.get("free_float_pct")]), errors="coerce").iloc[0]
                iid = str(r["issuer_id"])
                if iid in out.index and np.isfinite(v):
                    v = float(v) / 100.0 if v > 1.0 else float(v)
                    if 0 < v <= 1:
                        out.at[iid, "free_float"] = v
                        out.at[iid, "fonte"] = str(r.get("fonte") or "publico")
    out["free_float"] = pd.to_numeric(out["free_float"], errors="coerce")
    return out


# ----------------------------------------------------------------------------- vetos


def _as_date(v: Any) -> date | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        return pd.Timestamp(v).date()
    except (TypeError, ValueError):
        return None


def _earnings_row(earnings: pd.DataFrame, i: str
                  ) -> tuple[date | None, bool, list[tuple[date, bool, Any]], bool]:
    """``(data de referência, estimada, candidatos (data, estimada, janela), resultado
    recente)`` do emissor; sem a coluna ``candidatos`` (tabela simples), a data de referência é
    a única candidata."""
    if i not in earnings.index:
        return None, False, [], False

    def get(col: str, default: Any = None) -> Any:
        return earnings.at[i, col] if col in earnings.columns else default

    def flag(col: str) -> bool:
        v = get(col, False)
        return bool(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) \
            else False

    d = _as_date(get("data"))
    est = flag("estimada")
    recent = flag("resultado_recente")
    raw = get("candidatos")
    cands: list[tuple[date, bool, Any]] = []
    if isinstance(raw, (list, tuple)):
        for c in raw:
            cd = _as_date(c[0]) if len(c) else None
            if cd is not None:
                cands.append((cd, bool(c[1]), c[3] if len(c) > 3 else None))
    elif d is not None:
        cands.append((d, est, get("janela_dias")))
    cands.sort(key=lambda c: (c[0], c[1]))
    return d, est, cands, recent


def short_entry_blocks(issuers: Sequence[str], *, week: date, earnings: pd.DataFrame,
                       free_float: pd.DataFrame, market_cap_usd: pd.Series,
                       cfg: FundConfig) -> pd.DataFrame:
    """Vetos de short novo por emissor (colunas :data:`BLOCK_COLUMNS`)."""
    sq = cfg.squeeze
    idx = pd.Index(sorted(map(str, issuers)), name="issuer_id")
    win = catalyst_window_days(cfg)
    rows: dict[str, dict[str, Any]] = {}
    mcap = pd.to_numeric(market_cap_usd.reindex(idx), errors="coerce")
    for i in idx:
        motivo: list[str] = []
        ausente: list[str] = []
        d, est, cands, recent = _earnings_row(earnings, i)
        cat = False
        # Toda data candidata é avaliada: confirmada dentro da janela ou estimada (±7 dias)
        # cuja janela toca a de veto bloqueia; estimativa larga (sem histórico do emissor) só é
        # sinalizada e nunca desloca uma data confirmada ou estimada com precisão.
        precise = [c for c in cands if not _too_wide(c[1], c[2])]
        hits = [c for c in precise
                if ((c[0] - week).days - (ESTIMATE_HALF_WINDOW_DAYS if c[1] else 0)) <= win
                and ((c[0] - week).days + (ESTIMATE_HALF_WINDOW_DAYS if c[1] else 0)) >= 0]
        if hits:
            cat = True
            confirmed = [c for c in hits if not c[1]]
            d, est = (confirmed or hits)[0][0], not confirmed
            motivo.append("bloqueio_resultado" + ("" if confirmed else "_estimado"))
        elif not precise and cands:
            ausente.append("data_resultado_incerta")
        elif not cands and not recent:
            ausente.append("data_resultado")
        ff = free_float["free_float"].get(i) if i in free_float.index else np.nan
        src = free_float["fonte"].get(i) if i in free_float.index else None
        flt = False
        if ff is None or not np.isfinite(ff):
            ausente.append("free_float")
            m = mcap.get(i)
            if m is None or not np.isfinite(m) or m < sq.free_float_mcap_low_usd:
                flt = True  # falha fechada: free float desconhecido em nome pequeno
                motivo.append("bloqueio_free_float_desconhecido")
            ff = None
        elif ff < sq.free_float_min_pct:
            flt = True
            motivo.append("bloqueio_free_float")
        rows[i] = {"catalyst_block": cat, "float_block": flt,
                   "data_resultado": d.isoformat() if d is not None else None,
                   "resultado_estimado": est, "free_float": ff, "fonte_free_float": src,
                   "motivo": ";".join(motivo), "dado_ausente": ";".join(ausente)}
    return pd.DataFrame.from_dict(rows, orient="index", columns=BLOCK_COLUMNS).reindex(idx)


def apply_short_entry_blocks(constraints: pd.DataFrame, blocks: pd.DataFrame
                             ) -> tuple[pd.DataFrame, dict[str, str]]:
    """Nenhum short novo ou aumentado nos emissores vetados (cobrir é sempre permitido).
    Devolve as restrições apertadas e ``{emissor: motivo}`` dos vetos aplicados."""
    c = constraints.copy()
    cur = pd.to_numeric(c.get("current", pd.Series(0.0, index=c.index)),
                        errors="coerce").fillna(0.0)
    applied: dict[str, str] = {}
    blk = blocks.reindex(c.index)
    mask = (blk["catalyst_block"].fillna(False).astype(bool)
            | blk["float_block"].fillna(False).astype(bool))
    for iid in c.index[mask.to_numpy(dtype=bool)]:
        cap = max(-float(cur.get(iid, 0.0)), 0.0)
        before = float(c.at[iid, "max_short"])
        c.at[iid, "max_short"] = min(before, cap)
        if before > cap + 1e-12:
            applied[str(iid)] = str(blk.at[iid, "motivo"])
            if "reasons" in c.columns:
                tok = str(blk.at[iid, "motivo"])
                c.at[iid, "reasons"] = ";".join(x for x in (str(c.at[iid, "reasons"]), tok) if x)
    if "can_short" in c.columns:
        c["can_short"] = c["max_short"] > 0
    return c, applied


def apply_squeeze_name_stops(constraints: pd.DataFrame, stops: Mapping[str, str]
                             ) -> tuple[pd.DataFrame, dict[str, str]]:
    """Stop de squeeze por nome: short cortado à metade e sem posição comprada no emissor."""
    c = constraints.copy()
    cur = pd.to_numeric(c.get("current", pd.Series(0.0, index=c.index)),
                        errors="coerce").fillna(0.0)
    applied: dict[str, str] = {}
    for iid, motivo in sorted(stops.items()):
        if iid not in c.index:
            continue
        w0 = float(cur.get(iid, 0.0))
        if w0 >= 0:
            continue
        c.at[iid, "max_short"] = min(float(c.at[iid, "max_short"]), 0.5 * abs(w0))
        c.at[iid, "max_long"] = 0.0
        if "reasons" in c.columns:
            c.at[iid, "reasons"] = ";".join(x for x in (str(c.at[iid, "reasons"]),
                                                        "stop_squeeze_nome") if x)
        applied[str(iid)] = str(motivo)
    if "can_long" in c.columns:
        c["can_long"] = c["max_long"] > 0
    return c, applied


def stops_de_squeeze(records_desc: Sequence[DailyRecord], cfg: FundConfig,
                     nav_usd: float) -> dict[str, str]:
    """Shorts em stop de squeeze no registro diário mais recente (mesma regra do monitor:
    perda desde a entrada ≥ ``stop_short_position_loss`` ou ≥ ``stop_short_nav_loss`` do NAV).
    ``records_desc``: do mais recente para o mais antigo. Devolve ``{emissor: motivo}``."""
    from ..workflow.risk_monitor import squeeze_stop_checks

    if not records_desc:
        return {}
    last, history = records_desc[0], list(records_desc[1:])
    shorts = []
    for p in last.positions:
        if p.shares is None or p.price_local is None or p.shares >= 0:
            continue
        fx = (p.price_usd / p.price_local
              if p.price_usd is not None and p.price_local else None)
        shorts.append({"ticker": p.ticker, "emissor": p.issuer_id, "acoes": p.shares,
                       "preco_local": p.price_local, "fx": fx})
    out: dict[str, str] = {}
    for s in squeeze_stop_checks(cfg, shorts, history, nav_usd):
        if s.get("stop_posicao") or s.get("stop_nav"):
            why = "perda desde a entrada" if s.get("stop_posicao") else "perda em % do NAV"
            out[str(s["emissor"])] = f"stop de squeeze ({why}) em {s['ticker']}"
    return out


def escalar_para_kill_switch(stop_dates: Mapping[str, Iterable[date]], sessions: Sequence[date],
                             cfg: FundConfig) -> bool:
    """Escala para o kill switch do livro só com ``stop_escalation_count`` shorts distintos em
    stop dentro das últimas ``stop_escalation_sessions`` sessões (assinatura de desmonte
    coletivo). ``stop_dates``: emissor → datas em que o stop foi acionado; ``sessions``: pregões
    em ordem crescente até hoje."""
    sq = cfg.squeeze
    if not sessions:
        return False
    window = set(sorted(sessions)[-sq.stop_escalation_sessions:])
    hits = {iid for iid, ds in stop_dates.items() if any(d in window for d in ds)}
    return len(hits) >= sq.stop_escalation_count


# ----------------------------------------------------------------------------- grupos de controle


def linked_group_exposures(w: pd.Series, cfg: FundConfig) -> dict[str, dict[str, float]]:
    """Peso comprado e vendido de cada grupo de controle (``risk_model.linked_groups``)."""
    out: dict[str, dict[str, float]] = {}
    for g, members in sorted(cfg.risk_model.linked_groups.items()):
        ww = w.reindex(members).dropna()
        out[g] = {"long": float(ww[ww > 0].sum()), "short": float(-ww[ww < 0].sum()),
                  "n": int(len(ww))}
    return out


__all__ = ["BLOCK_COLUMNS", "apply_short_entry_blocks", "apply_squeeze_name_stops",
           "catalyst_window_days", "earnings_calendar", "escalar_para_kill_switch",
           "free_float_table", "linked_group_exposures", "short_entry_blocks",
           "stops_de_squeeze"]
