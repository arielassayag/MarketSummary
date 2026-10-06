"""Relatório semanal de resultado, na noite do dia de montagem (dono: workstream D).

Depois da efetivação no leilão de fechamento do dia de montagem D e do registro diário de D:

- ``cdp weekly close-report --date D``: o código calcula (:func:`calcular_semana`) e grava
  ``reports/semanal/<D>/{fatos.md, factbook.json, comentario.schema.json}``: resultado da semana
  (fechamento do dia de montagem anterior → fechamento de D) e desde o início (USD e %),
  atribuição por componente, grupo de fatores, país, setor, lado e emissor — semana e acumulada,
  somas exatas das linhas de atribuição dos registros diários —, mudanças da carteira no
  fechamento (entradas, saídas, aumentos e reduções), giro, custos, taxa de execução, emissores
  congelados, *implementation shortfall* (deriva decisão→fechamento e custo modelado, com a
  estatística t móvel de 13 semanas), risco ex-ante da carteira decidida e da efetiva (inclusive a
  fatia idiossincrática), trajetória do período de montagem e liquidez em estresse. A mente
  escreve ``comentario.json`` (:mod:`cdp.research.comentario_semanal`).
- ``cdp validate-weekly-report --date D``: valida ``comentario.json`` sem publicar.
- ``cdp weekly close-report --date D --publish``: renderiza ``relatorio.md/.html`` (comentário da
  mente, ou o modelo determinístico se inválido/ausente; imutável) e grava o evento
  ``WEEKLY_CLOSE_REPORT``.

O relatório existe para TODO dia de montagem da regra semanal com registro diário (a data de início
e o dia da regra de cada semana), com ou sem decisão: sem decisão gravada a carteira foi mantida —
o relatório traz o resultado, a atribuição e o risco da semana, e a execução fica sem objeto. A
semana vai do fechamento do dia de montagem anterior ao fechamento de D. Na semana da carteira
inaugural (sem registro anterior) é o "relatório de montagem". O relatório da decisão
(``reports/weekly/<W>/``, ``WEEKLY_REPORT``) não muda.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE

if TYPE_CHECKING:  # pragma: no cover
    from ..contracts import BookEntry, DailyRecord, FactBook, Proposal
    from ..market import MarketData
    from .runtime import Runtime

EM_IMPLEMENTACAO = 2
SEMANAL_DIR = "semanal"
REPORT_EVENT = "WEEKLY_CLOSE_REPORT"
ACTOR = "CDP"
_GROUPS = ("component", "factor_group", "country", "sector", "side", "issuer")


def report_dir(rt: Runtime, d: date) -> Path:
    """``reports/semanal/<D>/``."""
    return Path(rt.reports_root) / SEMANAL_DIR / d.isoformat()


# ============================================================ cálculo


def _f(x: object) -> float | None:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def somar_atribuicao(records: Sequence[DailyRecord]) -> dict[str, dict[str, float]]:
    """Σ P&L (USD) por grupo e nome das linhas de atribuição dos registros (soma exata)."""
    out: dict[str, dict[str, float]] = {g: {} for g in _GROUPS}
    for r in records:
        for ln in r.attribution:
            if ln.group not in out:
                continue
            out[ln.group][ln.name] = out[ln.group].get(ln.name, 0.0) + float(ln.pnl_usd)
    return out


def _periodo(records: Sequence[DailyRecord]) -> dict[str, Any]:
    if not records:
        return {"n": 0, "ret": None, "pnl_usd": None, "nav_inicio": None, "inicio": None,
                "atribuicao": {g: {} for g in _GROUPS}}
    ret = float(np.prod([1.0 + float(r.ret) for r in records]) - 1.0)
    return {"n": len(records), "ret": ret, "pnl_usd": float(sum(r.pnl_usd for r in records)),
            "nav_inicio": float(records[0].nav_start_usd), "inicio": records[0].date,
            "atribuicao": somar_atribuicao(records)}


def _nav_pre(rec: DailyRecord) -> float:
    return float(rec.nav_end_usd) - float(rec.pnl_components.get("costs", 0.0) or 0.0)


def _proposal_of(rt: Runtime, d: date) -> tuple[Proposal | None, BookEntry | None]:
    b = rt.book
    entry = b.load_booked(d)
    if entry is not None:
        for p in b.list_proposals(d):
            if p.proposal_id == entry.proposal_id:
                return p, entry
    decs = b.list_decisions(d)
    if decs:
        return b.load_proposal(d, max(decs)), None
    return None, None


def _lines(rec: DailyRecord | None) -> dict[tuple[str, str], Any]:
    if rec is None:
        return {}
    return {(p.issuer_id, p.ticker): p for p in rec.positions}


def mudancas_carteira(prev: DailyRecord | None, rec: DailyRecord,
                      proposal: Proposal | None) -> tuple[list[dict[str, Any]], float]:
    """Mudanças por emissor no fechamento e o giro Σ|Δw|.

    Peso antes = valor pré-negociação (posição anterior marcada no dia) / NAV pré-negociação;
    peso depois = valor de fechamento / NAV de fechamento. Só há mudança se as ações de alguma
    linha do emissor mudaram (deriva de preço não é mudança)."""
    before, after = _lines(prev), _lines(rec)
    nav_pre, nav_end = _nav_pre(rec), float(rec.nav_end_usd)
    w0: dict[str, float] = {}
    w1: dict[str, float] = {}
    traded: dict[str, bool] = {}
    for key in set(before) | set(after):
        iid = key[0]
        p0, p1 = before.get(key), after.get(key)
        s0 = float(p0.shares or 0) if p0 is not None and p0.market_value_usd != 0 else 0.0
        s1 = float(p1.shares or 0) if p1 is not None and p1.market_value_usd != 0 else 0.0
        if p0 is not None and p0.market_value_usd != 0:
            pre = float(p0.market_value_usd) + (float(p1.day_pnl_usd) if p1 is not None else 0.0)
            w0[iid] = w0.get(iid, 0.0) + pre / nav_pre
        if p1 is not None and p1.market_value_usd != 0:
            w1[iid] = w1.get(iid, 0.0) + float(p1.market_value_usd) / nav_end
        if round(s1) != round(s0):
            traded[iid] = True
    info = {p.issuer_id: p for p in (proposal.positions if proposal is not None else [])}
    out: list[dict[str, Any]] = []
    giro = 0.0
    for iid in sorted(set(w0) | set(w1)):
        a, b = w0.get(iid, 0.0), w1.get(iid, 0.0)
        if not traded.get(iid):
            continue
        giro += abs(b - a)
        if a == 0 or (b != 0 and a * b < 0):
            tipo = "entrada"
        elif b == 0:
            tipo = "saida"
        elif abs(b) > abs(a):
            tipo = "aumento"
        else:
            tipo = "reducao"
        p = info.get(iid)
        out.append({"emissor": iid, "tipo": tipo, "antes": a, "depois": b, "delta": b - a,
                    "alpha_z": _f(p.alpha_z) if p is not None else None,
                    "visao": _f(p.view_score) if p is not None else None,
                    "risco": _f(p.risk_contribution) if p is not None else None,
                    "pais": p.country if p is not None else None,
                    "setor": p.sector if p is not None else None})
    order = {"entrada": 0, "aumento": 1, "reducao": 2, "saida": 3}
    out.sort(key=lambda m: (order[m["tipo"]], -abs(m["delta"]), m["emissor"]))
    return out, giro


def _int_br(n: object) -> str:
    """Inteiro com separador de milhar pt-BR (``196484`` ⇒ ``196.484``)."""
    return f"{int(n):,}".replace(",", ".")


class _Custos:
    """Contexto de custo do pregão ``d`` (painel do dia), montado uma vez por relatório."""

    def __init__(self, rt: Runtime, d: date, md: MarketData) -> None:
        self.rt, self.d, self.md = rt, d, md
        self._runner: Any = None
        self._ctx: Any = None

    def frame(self, trades: Sequence[tuple]) -> pd.DataFrame:
        if self._ctx is None:
            self._runner = self.rt._runner()
            self._ctx = self._runner.context(self.d, self.md.truncate(self.d), None,
                                             need_models=False)
        return self._runner.custo_frame(self._ctx, trades)


def analise_execucao(rt: Runtime, d: date, md: MarketData, rec: DailyRecord,
                     prev: DailyRecord | None, proposal: Proposal | None,
                     entry: BookEntry | None, custos: _Custos | None = None) -> dict[str, Any]:
    """Ordens × execuções no fechamento de ``d`` (reconstruídas do livro e dos registros) e o
    *implementation shortfall* (:func:`cdp.portfolio.execucao.shortfall`).

    ``congelados``: TODO emissor detido com linha num mercado sem fechamento elegível no pregão
    (ações mantidas), com ou sem ordem. ``parciais``: linhas executadas abaixo da ordem pela
    capacidade (ações executadas/ordenadas); ``avisos``: limitações do cálculo."""
    from ..calendar import previous_data_session
    from ..portfolio.costs import custos_fechamento
    from ..portfolio.execucao import (
        categoria_da_linha,
        janela_execucao,
        mic_da_linha,
        motivo_inelegivel,
        shortfall,
    )

    cfg = rt.cfg
    before, after = _lines(prev), _lines(rec)
    nav_pre = _nav_pre(rec)
    hold = proposal is None or entry is None or proposal.optimizer.status == "hold"
    targets = {} if hold else {(p.issuer_id, p.execution_ticker): p
                               for p in proposal.positions if p.weight != 0}
    uni = md.universe.lines
    exch = uni["exchange"] if "exchange" in uni.columns else pd.Series(dtype=object)
    janela = janela_execucao(d, cfg)
    ts = pd.Timestamp(d)
    prev_ts = pd.Timestamp(previous_data_session(d))
    capcfg = cfg.execution.capacity if cfg.execution is not None else None
    share_cfg = capcfg.auction_share if capcfg is not None else {}
    pre_share = float(capcfg.preclose_volume_share) if capcfg is not None else 0.0
    keys = sorted(set(k for k, p in before.items() if p.market_value_usd != 0)
                  | set(k for k, p in after.items() if p.market_value_usd != 0) | set(targets))
    linhas: list[dict[str, Any]] = []
    congelados: dict[str, str] = {}
    parciais: list[str] = []
    avisos: list[str] = []
    for iid, tk in keys:
        p0, p1 = before.get((iid, tk)), after.get((iid, tk))
        s0 = int(round(float(p0.shares or 0))) if p0 is not None and p0.market_value_usd else 0
        s1 = int(round(float(p1.shares or 0))) if p1 is not None and p1.market_value_usd else 0
        q = s1 - s0
        px = _f(p1.price_local) if p1 is not None else None
        if px is None and tk in md.close.columns and ts in md.close.index:
            px = _f(md.close.at[ts, tk])
        fx = (_f(p1.price_usd) / px if p1 is not None and _f(p1.price_usd) and px else None)
        t = targets.get((iid, tk))
        if hold:
            st = s0
        elif t is None:
            st = 0
        elif t.shares is not None:
            st = int(t.shares)
        elif px and fx:
            st = int(round(t.weight * nav_pre / (px * fx)))
        else:
            st = s0
        order = st - s0
        dec_px = _f(t.price_local) if t is not None else None
        if dec_px is None and tk in md.close.columns and prev_ts in md.close.index:
            dec_px = _f(md.close.at[prev_ts, tk])
        vol = None
        if tk in md.volume.columns and ts in md.volume.index:
            v = _f(md.volume.at[ts, tk])
            vol = v if v is not None and v > 0 else None
        lt = uni.at[tk, "line_type"] if tk in uni.index else None
        cat = categoria_da_linha(tk, lt)
        mic = mic_da_linha(tk, exch.get(tk))
        if not hold and s0 != 0:
            motivo = motivo_inelegivel(mic, janela, cfg)
            if motivo is not None:
                congelados.setdefault(iid, motivo)
        if order != 0 and 0 < abs(q) < abs(order):
            parciais.append(f"{tk} ({_int_br(abs(q))}/{_int_br(abs(order))})")
        linhas.append({"emissor": iid, "ticker": tk, "ordem": order, "executadas": q,
                       "preco_decisao": dec_px, "preco_fechamento": px, "fx": fx,
                       "volume_acoes": vol, "fatia_leilao": float(share_cfg.get(cat, 0.0)),
                       "fatia_pre": pre_share,
                       "moeda": p1.currency if p1 is not None else (
                           t.currency if t is not None else "USD"),
                       "custo_modelo_usd": 0.0})
    traded = [ln for ln in linhas if ln["executadas"] and ln["preco_fechamento"] and ln["fx"]]
    if traded:
        try:
            custos = custos or _Custos(rt, d, md)
            frame = custos.frame([(ln["emissor"], ln["ticker"], ln["moeda"],
                                   abs(ln["executadas"]) * ln["preco_fechamento"] * ln["fx"],
                                   ln["executadas"], ln["preco_fechamento"])
                                  for ln in traded])
            res = custos_fechamento(frame, cfg)
            for ln in traded:
                v = _f(res["cost_usd"].get(ln["ticker"]))
                ln["custo_modelo_usd"] = v if v is not None else 0.0
        except (ValueError, KeyError) as exc:  # custo modelado indisponível: fica n/d
            for ln in traded:
                ln["custo_modelo_usd"] = None
            avisos.append(f"custo modelado indisponível ({type(exc).__name__})")
    sf = shortfall([{**ln, "custo_modelo_usd": ln["custo_modelo_usd"] or 0.0} for ln in linhas])
    custos_usd = -float(rec.pnl_components.get("costs", 0.0) or 0.0)
    exec_usd = sf["nocional_executado_usd"]
    return {**sf, "linhas": linhas, "congelados": congelados, "parciais": parciais,
            "avisos": avisos, "custos_usd": custos_usd,
            "custos_nav": custos_usd / nav_pre if nav_pre > 0 else None,
            "custos_bps": custos_usd / exec_usd * 1e4 if exec_usd > 0 else None,
            "manter": hold, "decisao": proposal is not None}


def _linhas_principais(rec: DailyRecord) -> dict[str, tuple[str, float, str]]:
    """Linha principal (maior valor) de cada emissor detido: ``iid -> (ticker, valor, moeda)``."""
    main: dict[str, tuple[str, float, str]] = {}
    for p in rec.positions:
        if p.market_value_usd == 0:
            continue
        cur = main.get(p.issuer_id)
        if cur is None or abs(p.market_value_usd) > abs(cur[1]):
            main[p.issuer_id] = (p.ticker, float(p.market_value_usd), p.currency)
    return main


def _proximo_dia_util(d: date) -> date:
    x = d + timedelta(days=1)
    while x.weekday() >= 5:
        x += timedelta(days=1)
    return x


def capacidade_carteira(rt: Runtime, d: date, md: MarketData, rec: DailyRecord
                        ) -> dict[str, Any]:
    """Capacidade por fechamento (fração do NAV) da linha principal de cada emissor detido,
    com o volume (ADV P25) dos pregões até ``d``.

    - ``estrutural``: num pregão REGULAR (:func:`cdp.portfolio.execucao.janela_regular`) — base
      do estresse de liquidez; feriados de um dia não tornam nomes ilíquidos.
    - ``por_janela``: nos próximos dias de montagem do calendário, um mapa por fechamento
      (mercado fechado ou fechamento antecipado naquele dia entram ali) — base da trajetória do
      período de montagem.
    - ``proximo``, ``mercados_fechados_proximo``: o próximo dia de montagem e os mercados das
      linhas detidas sem fechamento elegível nele (nota operacional)."""
    from ..calendar import proximas_montagens
    from ..portfolio.execucao import (
        MIC_NOME,
        TRAJETORIA_FECHAMENTOS,
        capacidade_por_janela,
        janela_execucao,
        janela_regular,
        motivo_inelegivel,
        resolver_mic,
        tabela_capacidade,
    )

    cfg = rt.cfg
    nav = float(rec.nav_end_usd)
    main = _linhas_principais(rec)
    out: dict[str, Any] = {"estrutural": {}, "por_janela": [], "proximo": None,
                           "mercados_fechados_proximo": []}
    if not main or nav <= 0:
        return out
    uni = md.universe.lines
    tickers = sorted({t for t, _, _ in main.values()})
    lines = uni.reindex(tickers)
    md_d = md.truncate(d)
    jr = janela_regular(_proximo_dia_util(d), cfg)
    tabs = {lado: tabela_capacidade(lines, md_d, jr, cfg, lado=lado)
            for lado in ("long", "short")}
    datas = list(proximas_montagens(d + timedelta(days=1), cfg,
                                    semanas=TRAJETORIA_FECHAMENTOS + 2))[:TRAJETORIA_FECHAMENTOS]
    janelas = [janela_execucao(x, cfg) for x in datas]
    seqs = {lado: capacidade_por_janela(tabs[lado], janelas, cfg) for lado in tabs}
    out["por_janela"] = [{} for _ in janelas]
    for iid, (tk, mv, _ccy) in main.items():
        lado = "short" if mv < 0 else "long"
        tab = tabs[lado]
        out["estrutural"][iid] = (float(tab.at[tk, "capacidade_usd"]) / nav
                                  if tk in tab.index else 0.0)
        for k, serie in enumerate(seqs[lado]):
            out["por_janela"][k][iid] = float(serie.get(tk, 0.0)) / nav
    if janelas:
        j0 = janelas[0]
        out["proximo"] = j0.sessao
        fechados = set()
        for tk in tickers:
            mic = str(tabs["long"].at[tk, "mic"]) if tk in tabs["long"].index else None
            if mic and motivo_inelegivel(mic, j0, cfg) is not None:
                m = resolver_mic(mic, cfg) or mic
                fechados.add(MIC_NOME.get(m, m))
        out["mercados_fechados_proximo"] = sorted(fechados)
    return out


def custo_liquidacao_estresse(custos: _Custos, rec: DailyRecord,
                              capacidade: Mapping[str, float], cfg: Any, *,
                              fator_volume: float) -> dict[str, Any]:
    """Custo estimado de liquidar a carteira em estresse: cada nome com capacidade é vendido
    (ou recomprado) em fechamentos sucessivos com ``fator_volume`` × capacidade por fechamento;
    custo em bps de :func:`cdp.portfolio.costs.custos_fechamento` com spreads e σ × 2
    (impacto sobre o nocional por fechamento), aplicado ao nocional inteiro do nome. Nomes sem
    capacidade conhecida ficam fora (``cobertura`` = fração do gross coberta)."""
    from ..portfolio.costs import custos_fechamento
    from ..portfolio.execucao import ESTRESSE_SPREAD_MULT, ESTRESSE_VOL_MULT

    nav = float(rec.nav_end_usd)
    main = _linhas_principais(rec)
    gross = sum(abs(mv) for _, mv, _ in main.values())
    out: dict[str, Any] = {"custo_usd": None, "custo_nav": None, "custo_bps_gross": None,
                           "cobertura": None, "spread_mult": ESTRESSE_SPREAD_MULT,
                           "vol_mult": ESTRESSE_VOL_MULT}
    trades = []
    total: dict[str, float] = {}
    for iid, (tk, mv, ccy) in main.items():
        c = float(capacidade.get(iid, 0.0) or 0.0) * nav * fator_volume
        if not c > 0:
            continue
        trades.append((iid, tk, ccy, min(abs(mv), c)))
        total[tk] = abs(mv)
    if not trades or gross <= 0:
        return out
    try:
        res = custos_fechamento(custos.frame(trades), cfg, spread_mult=ESTRESSE_SPREAD_MULT,
                                vol_mult=ESTRESSE_VOL_MULT)
    except (ValueError, KeyError):
        return out
    usd = 0.0
    coberto = 0.0
    for tk, notional in total.items():
        bps = _f(res["total_bps"].get(tk)) if tk in res.index else None
        if bps is None:
            continue
        usd += bps * notional / 1e4
        coberto += notional
    if coberto <= 0:
        return out
    out.update({"custo_usd": usd, "custo_nav": usd / nav if nav > 0 else None,
                "custo_bps_gross": usd / coberto * 1e4, "cobertura": coberto / gross})
    return out


def _causa_capacidade(proposal: Proposal | None, ex: Mapping[str, Any]) -> bool:
    """A capacidade de fechamento limitou a carteira desta montagem: algum teto de negociação
    ou de posição com origem na capacidade do fechamento vinculou na decisão, ou a execução
    ficou abaixo da ordem (taxa < 1, ordens parciais)."""
    if ex.get("parciais"):
        return True
    taxa = _f(ex.get("taxa_execucao"))
    if taxa is not None and taxa < 0.999:
        return True
    if proposal is None or not isinstance(proposal.overrides, dict):
        return False
    form = proposal.overrides.get("formulacao")
    lim = form.get("limites_por_nome") if isinstance(form, dict) else None
    if not isinstance(lim, dict):
        return False
    return any(isinstance(v, dict) and v.get("origem") == "capacidade_fechamento"
               and v.get("vinculante") for v in lim.values())


def dia_de_relatorio(rt: Runtime, d: date) -> bool:
    """``d`` é dia de relatório semanal: dia de montagem da regra (``chave_da_semana``) ou dia
    com decisão gravada (chaves aceitas pelo livro)."""
    from ..calendar import chave_da_semana

    return chave_da_semana(d, rt.cfg) == d or bool(rt.book.list_decisions(d))


def _kappa_da_decisao(proposal: Proposal | None) -> float | None:
    """κ_F gravado na decisão (``None`` sem o bloco ``overrides["risco"]``)."""
    if proposal is None:
        return None
    try:
        from ..risk.idio import decomposicao_decisao

        dec = decomposicao_decisao(proposal)
    except (ImportError, NotImplementedError, AttributeError, TypeError, KeyError):
        return None
    if not dec.get("disponivel"):
        return None
    kap = dec.get("kappa_f")
    return _f(kap.get("valor")) if isinstance(kap, dict) else _f(kap)


def _risco(cfg: Any, proposal: Proposal | None, rec: DailyRecord,
           kappa_vigente: float | None = None) -> dict[str, Any]:
    """Risco da carteira decidida (proposta) e da efetiva (registro do fechamento).

    A fatia idiossincrática PRINCIPAL é a da base do limite do mandato (κ_F no bloco fatorial,
    no modelo que vincula — :func:`cdp.risk.idio.base_vinculante`), a mesma do portal; a
    carteira efetiva recebe o mesmo κ_F sobre o modelo de risco do fechamento (sem decisão no
    dia, o κ_F da decisão vigente, ``kappa_vigente``). A fatia sem κ_F fica como linha
    secundária, rotulada."""
    rk: dict[str, Any] = {"meta": cfg.risk.vol_target_annual,
                          "banda_min": cfg.risk.vol_band_min}
    kappa: float | None = kappa_vigente if proposal is None else None
    if kappa is not None:
        rk["kappa_f"] = kappa
    if proposal is not None and proposal.positions:
        r = proposal.risk
        rk["alvo"] = {"vol": r.ex_ante_vol, "fatorial": r.factor_vol,
                      "especifica": r.specific_vol, "idio": 1.0 - r.factor_risk_share,
                      "beta": r.beta, "gross": r.gross, "net": r.net, "n_long": r.n_long,
                      "n_short": r.n_short}
        try:
            from ..risk.idio import base_vinculante, decomposicao_decisao

            dec = decomposicao_decisao(proposal)
            if dec.get("disponivel"):
                kap = dec.get("kappa_f")
                kappa = _f(kap.get("valor")) if isinstance(kap, dict) else _f(kap)
                rk["kappa_f"] = kappa
                rk["idio_decisao"] = _f(dec.get("idio_decisao"))
                basis = base_vinculante(proposal.overrides.get("risco"))
                if basis is not None:
                    rk["alvo"]["idio_kf"] = basis["idio"]
                    rk["base"] = {"modelo": basis["modelo"], "rotulo": basis["rotulo"]}
                    rk["por_grupo"] = {g: _f(v) for g, v in (basis.get("por_grupo")
                                                             or {}).items()}
        except (ImportError, NotImplementedError, AttributeError, TypeError, KeyError):
            pass
    er = rec.risk
    eff: dict[str, Any] = {"vol": er.ex_ante_vol, "fatorial": er.factor_vol,
                           "especifica": er.specific_vol, "beta": er.beta, "gross": er.gross,
                           "net": er.net, "n_long": er.n_long, "n_short": er.n_short}
    v, f_, s_ = _f(er.ex_ante_vol), _f(er.factor_vol), _f(er.specific_vol)
    if v and s_ is not None and v > 0:
        eff["idio"] = (s_ / v) ** 2
        if kappa is not None and f_ is not None:
            den = max(kappa, 1.0) * f_ ** 2 + s_ ** 2
            eff["idio_kf"] = s_ ** 2 / den if den > 0 else None
    rk["efetiva"] = eff
    return rk


def calcular_semana(rt: Runtime, d: date, md: MarketData | None = None) -> dict[str, Any]:
    """Todos os números do relatório semanal do dia de montagem ``d`` (só código).

    ``d`` precisa ser dia de relatório (:func:`dia_de_relatorio`) com registro diário. A semana
    vai do fechamento do dia de montagem ANTERIOR (da regra, decidido ou não) ao fechamento de
    ``d``; sem decisão em ``d`` a carteira foi mantida (sem mudanças nem execução)."""
    from ..portfolio.execucao import (
        ESTRESSE_REVERSO_VOLUME,
        SHORTFALL_SEMANAS,
        estatistica_t,
        estresse_liquidez,
        trajetoria_montagem,
    )

    cfg = rt.cfg
    b = rt.book
    records = [r for r in rt._records() if r.date <= d]
    rec = next((r for r in records if r.date == d), None)
    if rec is None:
        raise ValueError(f"Sem registro diário em {d}: rode `cdp daily close --date {d}` antes.")
    if not dia_de_relatorio(rt, d):
        raise ValueError(f"{d} não é dia de montagem da regra semanal (o relatório semanal é da "
                         "noite do dia de montagem).")
    prev_rec = next((r for r in reversed(records) if r.date < d), None)
    anteriores = [r.date for r in records if r.date < d and dia_de_relatorio(rt, r.date)]
    prev_key = anteriores[-1] if anteriores else None
    montagem = prev_rec is None
    week = [r for r in records if (prev_key is None or r.date > prev_key)]
    decided = [w for w in b.list_weeks() if w < d and b.list_decisions(w)]
    md = md if md is not None else rt.store.load(as_of=d)
    custos = _Custos(rt, d, md)
    proposal, entry = _proposal_of(rt, d)
    mud, giro = mudancas_carteira(prev_rec, rec, proposal)
    ex = analise_execucao(rt, d, md, rec, prev_rec, proposal, entry, custos)
    ex["giro"] = giro
    for m in mud:
        rows = [ln for ln in ex["linhas"] if ln["emissor"] == m["emissor"]]
        o = sum(abs(ln["ordem"]) for ln in rows)
        m["execucao"] = (sum(abs(ln["executadas"]) for ln in rows) / o) if o else None
    hist: list[float | None] = []
    weeks = [w for w in decided if any(r.date == w for r in records)][-(SHORTFALL_SEMANAS - 1):]
    by_date = {r.date: r for r in records}
    for w in weeks:
        r_w = by_date[w]
        p_w = next((r for r in reversed(records) if r.date < w), None)
        prop_w, ent_w = _proposal_of(rt, w)
        try:
            hist.append(analise_execucao(rt, w, md, r_w, p_w, prop_w, ent_w)["deriva_bps"])
        except (ValueError, KeyError):
            hist.append(None)
    if proposal is not None:
        hist.append(ex["deriva_bps"])
    ex["historico_deriva_bps"] = hist
    ex["t_13s"] = estatistica_t(hist)

    vigente = None
    if proposal is None and decided:
        vigente = _kappa_da_decisao(_proposal_of(rt, decided[-1])[0])
    rk = _risco(cfg, proposal, rec, vigente)
    er = rec.risk
    pesos: dict[str, float] = {}
    for p in rec.positions:
        if p.market_value_usd != 0:
            pesos[p.issuer_id] = pesos.get(p.issuer_id, 0.0) + float(p.weight)
    try:
        cap = capacidade_carteira(rt, d, md, rec)
    except (ValueError, KeyError):
        cap = {"estrutural": {}, "por_janela": [], "proximo": None,
               "mercados_fechados_proximo": []}
    vol_e = _f(er.ex_ante_vol)
    meta = float(cfg.risk.vol_target_annual)
    traj = trajetoria_montagem(pesos, cap["por_janela"] or cap["estrutural"], vol_e, meta)
    banda = float(cfg.risk.vol_band_min)
    fase = not any((_f(r.risk.ex_ante_vol) or 0.0) >= banda for r in records)
    traj["fase_montagem"] = fase
    traj["causa_capacidade"] = _causa_capacidade(proposal, ex)
    traj["publicar"] = bool(fase and vol_e is not None and vol_e < meta - 0.0025
                            and traj.get("fechamentos_ate_meta") != 0 and traj["trajetoria"])
    nav = float(rec.nav_end_usd)
    lst = estresse_liquidez(pesos, cap["estrutural"], nav)
    rev = estresse_liquidez(pesos, cap["estrutural"], nav, fator_volume=ESTRESSE_REVERSO_VOLUME)
    lst["reverso"] = {"fator_volume": rev["fator_volume"],
                      "fracao_liquidavel": rev["fracao_liquidavel"],
                      "fechamentos_p90": rev["fechamentos_p90"]}
    lst["custo"] = custo_liquidacao_estresse(custos, rec, cap["estrutural"], cfg,
                                             fator_volume=float(lst["fator_volume"]))
    lst["proximo_dia_de_montagem"] = cap["proximo"]
    lst["mercados_fechados_proximo"] = cap["mercados_fechados_proximo"]
    names = (md.universe.issuers["issuer_name"].astype(str).to_dict()
             if "issuer_name" in md.universe.issuers.columns else {})
    return {
        "data": d, "fundo": cfg.fund.name, "montagem": montagem, "anterior": prev_key,
        "inicio": records[0].date, "inicio_mandato": cfg.fund.inception_date, "nav": nav,
        "decisao": proposal is not None,
        "semana": _periodo(week), "desde_inicio": _periodo(records),
        "mudancas": mud, "execucao": ex, "risco": rk, "montagem_trajetoria": traj,
        "liquidez": lst, "nomes": names,
        "registro": rec.record_hash, "aprovacao": entry.approval_hash if entry else None,
        "proposta": proposal.proposal_id if proposal is not None else None,
        "is_synthetic": bool(rec.is_synthetic), "aviso": rec.data_notice,
        "snapshot_id": f"registro-{(rec.record_hash or '')[:12]}",
        "alertas": list(rec.alerts),
    }


def factbook_semana(dados: Mapping[str, Any]) -> FactBook:
    """FactBook da semana (:func:`cdp.research.comentario_semanal.build_weekly_factbook`)."""
    from ..research.comentario_semanal import build_weekly_factbook

    return build_weekly_factbook(dados)


# ============================================================ renderização


def _pct(x: object, signed: bool = False, digits: int = 2) -> str:
    from .memo import fmt_pct

    return fmt_pct(_f(x), digits, signed)


def _usd(x: object, signed: bool = False) -> str:
    """Valor em USD no padrão dos relatórios do CDP (``US$ 31.031``, ``-US$ 470.317``,
    ``US$ 99,89 mi``) — o mesmo do relatório diário e dos fatos da semana."""
    from ..research.commentary import format_money

    return format_money(_f(x), signed)


def _bps(frac: object, signed: bool = True) -> str:
    v = _f(frac)
    if v is None:
        return "n/d"
    from .memo import fmt_num

    return f"{fmt_num(v * 1e4, 0, signed)} bps"


def _bps_val(v: object, signed: bool = True) -> str:
    x = _f(v)
    if x is None:
        return "n/d"
    from .memo import fmt_num

    return f"{fmt_num(x, 0, signed)} bps"


def _num(v: object, digits: int = 2, signed: bool = False) -> str:
    from .memo import fmt_num

    return fmt_num(_f(v), digits, signed)


def _plural(n: object, um: str, varios: str) -> str:
    try:
        return um if abs(float(n)) == 1 else varios  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return varios


_COMP_ORDER = ("equity", "factor", "specific", "costs", "borrow", "financing")
_COMP_PT = {"equity": "Ações (total)", "factor": "Fatorial", "specific": "Específico (alpha)",
            "costs": "Custos de transação", "borrow": "Aluguel", "financing": "Financiamento"}
_GROUP_PT = {"factor_group": "Grupo de fatores", "country": "País", "sector": "Setor",
             "side": "Lado"}
#: Rótulos pt-BR dos nomes de cada grupo de atribuição (os mesmos do portal).
_NOME_PT: dict[str, dict[str, str]] = {
    "factor_group": {"market": "Mercado", "style": "Estilos", "country": "País",
                     "sector": "Setor", "commodity": "Commodities", "theme": "Temas",
                     "currency": "Moeda", "macro": "Macro", "event": "Eventos"},
    "side": {"LONG": "Comprado", "SHORT": "Vendido"},
    "country": {"AR": "Argentina", "BR": "Brasil", "CL": "Chile", "CO": "Colômbia",
                "MX": "México", "PE": "Peru", "UY": "Uruguai", "PA": "Panamá",
                "US": "Estados Unidos", "LATAM": "Regional (América Latina)",
                "OTHER": "Outros"},
    "sector": {"Financials": "Financeiro", "Energy": "Energia", "Materials": "Materiais",
               "Utilities": "Utilidades públicas", "Industrials": "Industriais",
               "Consumer Discretionary": "Consumo discricionário",
               "Consumer Staples": "Consumo básico", "Health Care": "Saúde",
               "Real Estate": "Imobiliário", "Communication Services": "Comunicações",
               "Information Technology": "Tecnologia", "OTHER": "Outros"},
}
_GRUPO_IDIO_PT = {"mercado": "Mercado", "pais": "País", "setor": "Setor", "estilo": "Estilos",
                  "macro": "Macro", "especifico": "Específico"}
_TIPO_PT = {"entrada": "Entrada", "saida": "Saída", "aumento": "Aumento", "reducao": "Redução"}


def rotulo(group: str, name: str) -> str:
    """Rótulo pt-BR de um nome de atribuição (código desconhecido fica como está)."""
    if group == "component":
        return _COMP_PT.get(name, name)
    return _NOME_PT.get(group, {}).get(name, name)


def _attr_table(sem: Mapping[str, Any], itd: Mapping[str, Any], group: str,
                limit: int | None = None, nomes: Mapping[str, str] | None = None
                ) -> list[list[str]]:
    a, b = sem["atribuicao"].get(group, {}), itd["atribuicao"].get(group, {})
    n0s, n0i = sem.get("nav_inicio") or 0.0, itd.get("nav_inicio") or 0.0
    names = list(dict.fromkeys(list(a) + list(b)))
    if group == "component":
        names = [c for c in _COMP_ORDER if c in names] + [c for c in names
                                                          if c not in _COMP_ORDER]
    else:
        names.sort(key=lambda n: -abs(b.get(n, 0.0)))
    rows = []
    for n in names[:limit] if limit else names:
        label = (f"{(nomes or {}).get(n, n)} ({n})" if group == "issuer" and nomes
                 and (nomes or {}).get(n, n) != n else rotulo(group, n))
        rows.append([label, _usd(a.get(n), True), _bps(a[n] / n0s if n in a and n0s else None),
                     _usd(b.get(n), True), _bps(b[n] / n0i if n in b and n0i else None)])
    return rows


def _risk_rows(rk: Mapping[str, Any]) -> list[list[str]]:
    a, e = rk.get("alvo") or {}, rk.get("efetiva") or {}
    tem_kf = a.get("idio_kf") is not None or e.get("idio_kf") is not None
    base = rk.get("base") or {}
    specs: list[tuple[str, str, str]] = [
        ("vol", "Vol ex-ante", "pct"), ("fatorial", "Vol fatorial", "pct"),
        ("especifica", "Vol específica", "pct")]
    if tem_kf:
        specs.append(("idio_kf", "Fatia idiossincrática da variância — base do limite do "
                                 f"mandato (κ_F, {base.get('rotulo', 'modelo de decisão')})",
                      "pct"))
        specs.append(("idio", "Fatia idiossincrática da variância — modelo sem κ_F", "pct"))
    else:
        specs.append(("idio", "Fatia idiossincrática da variância (modelo sem κ_F)", "pct"))
    specs += [("beta", "Beta previsto", "x"), ("gross", "Gross", "pct"),
              ("net", "Net", "pct"), ("n_long", "Nomes comprados", "n"),
              ("n_short", "Nomes vendidos", "n")]
    rows = []
    for key, label, fmt in specs:
        def f(v: object, _fmt: str = fmt, _k: str = key) -> str:
            if v is None:
                return "n/d"
            if _fmt == "pct":
                return _pct(v, _k == "net")
            if _fmt == "x":
                return _num(v, 3, True)
            return str(int(v))  # type: ignore[call-overload]
        rows.append([label, f(a.get(key)), f(e.get(key))])
    return rows


def render_relatorio(dados: Mapping[str, Any], fb: FactBook, texto: Mapping[str, Any], *,
                     da_mente: bool, problemas: Sequence[str], cfg: Any) -> tuple[str, str]:
    """Markdown e HTML do relatório semanal (números do código; texto da mente rotulado IA)."""
    from .reports import Document, Section, to_html, to_markdown

    d: date = dados["data"]
    sem, itd, ex, rk = dados["semana"], dados["desde_inicio"], dados["execucao"], dados["risco"]
    montagem = bool(dados["montagem"])
    decisao = bool(dados.get("decisao", True))
    nomes: Mapping[str, str] = dados.get("nomes") or {}
    titulo = ("Relatório de montagem da carteira" if montagem
              else "Relatório semanal de resultado")
    ia = da_mente
    secs: list[Section] = []
    s = Section("Resumo", ai=ia)
    s.p(texto["resumo"], ai=ia)
    secs.append(s)

    s = Section("Resultado" if not montagem else "Resultado do dia da montagem")
    rows = [["Retorno (USD)", _pct(sem["ret"], True), _pct(itd["ret"], True)],
            ["P&L", _usd(sem["pnl_usd"], True), _usd(itd["pnl_usd"], True)],
            ["Pregões", str(sem["n"]), str(itd["n"])]]
    ini = sem.get("inicio")
    inicio = dados.get("inicio") or itd.get("inicio")
    cap = (f"Montagem da carteira no fechamento de {d:%d/%m/%Y}." if montagem else
           f"Semana: do fechamento do dia de montagem anterior ao fechamento de {d:%d/%m/%Y} "
           f"(registros de {ini:%d/%m/%Y} a {d:%d/%m/%Y}); desde o início: a partir de "
           f"{inicio:%d/%m/%Y}.")
    s.table(["", "Semana" if not montagem else "Dia da montagem", "Desde o início"], rows,
            caption=cap)
    for p in texto["desempenho_semana"]:
        s.p(p, ai=ia)
    for p in texto["desempenho_desde_inicio"]:
        s.p(p, ai=ia)
    secs.append(s)

    s = Section("Atribuição de performance")
    per = "Dia da montagem" if montagem else "Semana"
    hdr = ["", f"{per} (USD)", per, "Desde o início (USD)", "Desde o início"]
    s.table(hdr, _attr_table(sem, itd, "component"),
            caption="Componentes (em bps do NAV no início de cada período)")
    for g in ("factor_group", "side", "country", "sector"):
        rows = _attr_table(sem, itd, g, limit=12)
        if rows:
            s.table(hdr, rows, caption=_GROUP_PT[g])
    rows = _attr_table(sem, itd, "issuer", limit=10, nomes=nomes)
    if rows:
        s.table(hdr, rows, caption="Emissores (dez maiores contribuições absolutas desde o "
                                   "início)")
    for p in texto["atribuicao"]:
        s.p(p, ai=ia)
    secs.append(s)

    s = Section("Mudanças da carteira no fechamento")
    mud = dados["mudancas"]
    if mud:
        rac = texto["mudancas_carteira"]
        s.table(["Emissor", "Mudança", "Peso antes", "Peso depois", "Δ peso", "Alpha (z)",
                 "Execução", "Racional"],
                [[m["emissor"], _TIPO_PT[m["tipo"]], _pct(m["antes"], True),
                  _pct(m["depois"], True), _pct(m["delta"], True),
                  _num(m.get("alpha_z"), 2, True),
                  _pct(m.get("execucao"), digits=0), rac.get(m["emissor"], "—")]
                 for m in mud], caption="Racional: texto da gestão (IA) quando validado.")
    elif not decisao:
        s.p("Sem decisão gravada no dia de montagem: a carteira anterior foi mantida, sem "
            "negociação no fechamento.")
    else:
        s.p("Sem mudanças de posição no fechamento.")
    secs.append(s)

    s = Section("Execução no leilão de fechamento")
    if not decisao or ex.get("manter"):
        s.p("Sem negociação no fechamento (carteira mantida): giro, custos e implementation "
            "shortfall sem objeto nesta semana.")
    else:
        s.kv([("Giro (Σ|Δw|)", _pct(ex.get("giro"))),
              ("Custos", f"{_usd(ex.get('custos_usd'))} ({_bps(ex.get('custos_nav'), False)} "
                         f"do NAV; {_bps_val(ex.get('custos_bps'), False)} do valor "
                         "negociado)"),
              ("Taxa de execução (nocional)", _pct(ex.get("taxa_execucao"))),
              ("Deriva decisão→fechamento (positivo = custo)", _bps_val(ex.get("deriva_bps"))),
              ("Custo modelado no leilão", _bps_val(ex.get("custo_modelo_bps"), False)),
              ("Implementation shortfall (deriva + custo modelado)",
               _bps_val(ex.get("shortfall_bps"))),
              ("Custo de oportunidade (parcela não executada)",
               _bps_val(ex.get("oportunidade_bps"))),
              ("Participação mediana na janela de fechamento (leilão + pré-fechamento)",
               _pct(ex.get("participacao_janela_mediana"))),
              ("Estatística t da deriva decisão→fechamento (até 13 semanas)",
               _num(ex.get("t_13s"), 2, True))],
             caption="Paper trading: a execução é registrada ao preço oficial de fechamento "
                     "de cada linha, inclusive a parcela da janela pré-fechamento; o custo "
                     "debitado é o custo modelado, e a deriva decisão→fechamento é a parcela "
                     "mensurável do implementation shortfall. Participação = ações executadas "
                     "/ ((fatia do leilão + fatia pré-fechamento) × volume do pregão), limitada "
                     "a 10% pela regra de capacidade.")
    if ex.get("congelados"):
        s.items([(f"{nomes[k]} ({k}): {v}" if nomes.get(k, k) != k else f"{k}: {v}")
                 for k, v in sorted(ex["congelados"].items())],
                caption="Emissores detidos sem negociação no fechamento (ações mantidas)")
    if ex.get("parciais"):
        s.items(list(ex["parciais"]), caption="Execuções limitadas pela capacidade do leilão "
                                              "(ações executadas/ordenadas)")
    for p in texto["execucao"]:
        s.p(p, ai=ia)
    secs.append(s)

    s = Section("Risco da nova carteira")
    e = rk.get("efetiva") or {}
    kap = rk.get("kappa_f")
    cap_r = (f"Meta de vol ex-ante {_pct(rk.get('meta'))}; piso da banda "
             f"{_pct(rk.get('banda_min'))}.")
    if kap is not None:
        cap_r += (f" Fatia idiossincrática na base do limite: σ²_específica / (κ_F · "
                  f"σ²_fatorial + σ²_específica), κ_F = {_num(kap, 2)}; "
                  + (f"carteira decidida no "
                     f"{(rk.get('base') or {}).get('rotulo', 'modelo de decisão')} gravado na "
                     "decisão, carteira efetiva no modelo de risco do fechamento."
                     if decisao else
                     "carteira efetiva no modelo de risco do fechamento, com o κ_F da decisão "
                     "vigente."))
    s.table(["", "Carteira decidida" if decisao else "Carteira decidida (sem decisão)",
             "Carteira efetiva (após o leilão)"], _risk_rows(rk), caption=cap_r)
    grupos = rk.get("por_grupo") or {}
    if any(v is not None for v in grupos.values()):
        s.table(["Grupo", "Participação na variância"],
                [[_GRUPO_IDIO_PT.get(g, g), _pct(v)] for g, v in grupos.items()],
                caption=("Decomposição da variância ex-ante da carteira decidida por grupo "
                         "(base do limite, κ_F no bloco fatorial)."))
    traj = dados.get("montagem_trajetoria") or {}
    if traj.get("publicar"):
        k_meta = traj.get("fechamentos_ate_meta")
        pts = [row for row in traj["trajetoria"] if row["fechamento"] in (0, 1, 2, 4, 8)]
        causa = ("limitado pela capacidade do leilão de fechamento" if traj.get(
            "causa_capacidade") else "abaixo da meta")
        meta_txt = (f"a meta seria alcançada em {k_meta} "
                    f"{_plural(k_meta, 'fechamento semanal', 'fechamentos semanais')}"
                    if k_meta is not None else
                    "a meta não seria alcançada no horizonte de oito fechamentos semanais")
        fixos = traj.get("nomes_sem_capacidade") or []
        extra = ""
        if fixos:
            extra = (f" {len(fixos)} "
                     + _plural(len(fixos), "nome sem volume conhecido mantém",
                               "nomes sem volume conhecido mantêm")
                     + " o peso atual.")
        s.table(["Fechamentos semanais", "Vol ex-ante esperada"],
                [[str(row["fechamento"]), _pct(row["vol"])] for row in pts],
                caption=(f"Período de montagem: risco efetivo {causa}. Trajetória condicional, "
                         "pela capacidade de fechamento dos nomes em cada um dos próximos dias "
                         f"de montagem: se a composição atual fosse mantida, {meta_txt}."
                         + extra))
    lq = dados.get("liquidez") or {}
    if lq.get("fracao_liquidavel"):
        rev = (lq.get("reverso") or {}).get("fracao_liquidavel") or {}
        s.table(["Fechamentos", "Gross liquidável — estresse (0,7 × ADV)",
                 "Gross liquidável — cenário reverso (0,5 × ADV)"],
                [[str(h), _pct(v), _pct(rev.get(h))]
                 for h, v in sorted(lq["fracao_liquidavel"].items())],
                caption="Estresse de liquidez contado em leilões de fechamento: volume de 0,7 × "
                        "ADV por nome (P10 dos episódios de estresse na região) e cenário "
                        "reverso de 0,5 × ADV, com a capacidade do leilão e da janela "
                        "pré-fechamento num pregão regular.")
        c = lq.get("custo") or {}
        p90, p90r = lq.get("fechamentos_p90"), (lq.get("reverso") or {}).get("fechamentos_p90")
        kv = [("Fechamentos para liquidar 90% do gross (estresse; cenário reverso)",
               f"{p90 if p90 is not None else 'n/d'}; {p90r if p90r is not None else 'n/d'}")]
        if c.get("custo_usd") is not None:
            kv.append(("Custo estimado de liquidação em estresse (spreads e σ × 2)",
                       f"{_usd(c['custo_usd'])} ({_bps(c.get('custo_nav'), False)} do NAV; "
                       f"{_bps_val(c.get('custo_bps_gross'), False)} do gross coberto, "
                       f"{_pct(c.get('cobertura'), digits=0)} do gross)"))
        prox, fech = lq.get("proximo_dia_de_montagem"), lq.get("mercados_fechados_proximo")
        if prox is not None and fech:
            kv.append((f"Sem fechamento elegível no próximo dia de montagem ({prox:%d/%m/%Y})",
                       ", ".join(fech)))
        s.kv(kv)
    for p in texto["risco_nova_carteira"]:
        s.p(p, ai=ia)
    secs.append(s)

    if texto["perspectivas"]:
        s = Section("Perspectivas", ai=ia)
        for p in texto["perspectivas"]:
            s.p(p, ai=ia)
        secs.append(s)

    s = Section("Integridade")
    prov = (f"Autoria do texto: mente {texto.get('mind')} [IA], validado; números calculados "
            "pelo código." if da_mente else
            "Autoria do texto: modelo determinístico do CDP [Calculado].")
    s.kv([("Registro diário do fechamento", str(dados.get("registro") or "n/d")),
          ("Aprovação da carteira", str(dados.get("aprovacao") or "n/d")),
          ("Base de fatos da semana", fb.factbook_hash()), ("Procedência", prov)])
    secs.append(s)

    notice = str(dados.get("aviso") or "")
    synthetic = bool(dados.get("is_synthetic"))
    if synthetic and SIMULATED_DATA_NOTICE not in notice.upper():
        notice = f"{SIMULATED_DATA_NOTICE} — {notice}".rstrip(" —")
    a = rk.get("alvo") or {}
    if a.get("idio_kf") is not None:
        idio_kpi = ("Fatia idiossincrática (κ_F)", _pct(a.get("idio_kf")),
                    f"carteira decidida, {(rk.get('base') or {}).get('rotulo', 'decisão')}")
    elif e.get("idio_kf") is not None:
        idio_kpi = ("Fatia idiossincrática (κ_F)", _pct(e.get("idio_kf")), "carteira efetiva")
    else:
        idio_kpi = ("Fatia idiossincrática", _pct(e.get("idio")), "carteira efetiva, sem κ_F")
    ini_txt = f"de {ini:%d/%m} a {d:%d/%m/%Y}" if ini is not None else f"{d:%d/%m/%Y}"
    kpis = [("Semana" if not montagem else "Dia da montagem", _pct(sem["ret"], True),
             f"P&L {_usd(sem['pnl_usd'], True)} · {ini_txt}"),
            ("Desde o início", _pct(itd["ret"], True),
             f"desde {inicio:%d/%m/%Y}" if inicio is not None else ""),
            ("NAV", _usd(dados["nav"]), f"fechamento de {d:%d/%m/%Y}"),
            ("Vol ex-ante efetiva", _pct(e.get("vol")),
             f"meta {_pct(rk.get('meta'))} · piso {_pct(rk.get('banda_min'))}"),
            idio_kpi]
    doc = Document(title=f"{dados['fundo']} — {titulo}", subtitle=f"Fechamento de {d:%d/%m/%Y}",
                   labels=([SIMULATED_DATA_NOTICE, "paper trading"] if synthetic
                           else ["paper trading com preços reais"]),
                   synthetic=synthetic, data_notice=notice, sections=secs, kpis=kpis)
    return to_markdown(doc), to_html(doc)


# ============================================================ fluxo


def preparar(rt: Runtime, d: date, *, mind: str | None = None) -> dict[str, Any]:
    """Calcula e grava os insumos da mente (regraváveis); devolve o resumo."""
    from ..research.comentario_semanal import write_inputs

    dados = calcular_semana(rt, d)
    fb = factbook_semana(dados)
    folder = report_dir(rt, d)
    paths = write_inputs(folder, fb, dados, mind_hint=mind)
    return {"data": d, "tipo": "montagem" if dados["montagem"] else "semanal",
            "fatos": {k: str(v) for k, v in paths.items()},
            "mudancas": len(dados["mudancas"]), "retorno_semana": dados["semana"]["ret"],
            "retorno_desde_inicio": dados["desde_inicio"]["ret"],
            "proximo_passo": (f"escreva {folder / 'comentario.json'} e rode "
                              f"`cdp validate-weekly-report --date {d}` e "
                              f"`cdp weekly close-report --date {d} --publish`")}


def validar(rt: Runtime, d: date) -> tuple[bool, list[str]]:
    from ..research.comentario_semanal import (
        COMENTARIO_JSON,
        parse_comentario,
        verificar_comentario,
    )

    dados = calcular_semana(rt, d)
    fb = factbook_semana(dados)
    out, issues = parse_comentario(report_dir(rt, d) / COMENTARIO_JSON)
    if out is None:
        return False, issues
    probs = verificar_comentario(out, fb, dados["mudancas"])
    return not probs, probs


def publicar(rt: Runtime, d: date) -> dict[str, Any]:
    """Publica o relatório (imutável) e grava ``WEEKLY_CLOSE_REPORT`` na trilha."""
    from ..research.comentario_semanal import (
        COMENTARIO_JSON,
        carregar_comentario,
        render_comentario,
        write_inputs,
    )
    from .reports import write_report_files

    folder = report_dir(rt, d)
    if (folder / "relatorio.md").exists():
        raise FileExistsError(f"Relatório semanal de {d} já publicado (imutável).")
    dados = calcular_semana(rt, d)
    fb = factbook_semana(dados)
    write_inputs(folder, fb, dados)
    out, da_mente, issues = carregar_comentario(folder / COMENTARIO_JSON, fb, dados["mudancas"],
                                                montagem=dados["montagem"])
    texto = render_comentario(out, fb)
    md_txt, html = render_relatorio(dados, fb, texto, da_mente=da_mente, problemas=issues,
                                    cfg=rt.cfg)
    report = write_report_files(folder, md_txt, html)
    payload = {**report, "registro": dados["registro"], "factbook": fb.factbook_hash(),
               "comentario_da_mente": da_mente, "apontamentos": issues,
               "tipo": "montagem" if dados["montagem"] else "semanal"}
    rt.book.audit.append(REPORT_EVENT, ACTOR, payload,
                         summary=f"Relatório semanal de resultado de {d} publicado.", week=d)
    return {"data": d, "relatorio": report, "comentario_da_mente": da_mente,
            "apontamentos_comentario": issues, "tipo": payload["tipo"]}


# ============================================================ CLI


def _json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_close_report(args: argparse.Namespace) -> int:
    """``cdp weekly close-report`` (``args.date``, ``args.publish``)."""
    from .runtime import Runtime

    rt = Runtime.from_args(args)
    try:
        out = publicar(rt, args.date) if args.publish else preparar(
            rt, args.date, mind=getattr(args, "mind", None))
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        print(f"cdp weekly close-report: {exc}", file=sys.stderr)
        return 1
    _json(out)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """``cdp validate-weekly-report`` (``args.date``; código 0 válido, 1 inválido)."""
    from .runtime import Runtime

    rt = Runtime.from_args(args)
    try:
        ok, issues = validar(rt, args.date)
    except (ValueError, FileNotFoundError) as exc:
        print(f"cdp validate-weekly-report: {exc}", file=sys.stderr)
        return 1
    _json({"data": args.date, "valido": ok, "problemas": issues})
    return 0 if ok else 1


__all__ = ["EM_IMPLEMENTACAO", "REPORT_EVENT", "analise_execucao", "calcular_semana",
           "cmd_close_report", "cmd_validate", "factbook_semana", "mudancas_carteira",
           "preparar", "publicar", "render_relatorio", "report_dir", "somar_atribuicao",
           "validar"]
