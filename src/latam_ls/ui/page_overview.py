"""Página 1 — Visão geral: KPIs do dia, NAV vs. sombra, comentário, alertas, decisão e agenda."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import charts, data, fmt
from . import components as ui
from .state import AppState


def _kpis(state: AppState) -> None:
    cfg = state.cfg
    track = state.track
    rec = track.latest
    assert rec is not None
    rk = rec.risk
    per = data.period_summary(rec, track.history_until(rec))
    c = st.columns(5)
    ui.kpi(c[0], "NAV", fmt.usd_mm(rec.nav_end_usd),
           f"abertura {fmt.usd_mm(rec.nav_start_usd)}")
    ui.kpi(c[1], "Retorno do dia", fmt.pct(rec.ret, signed=True),
           fmt.Status(f"P&L {fmt.usd_mm(rec.pnl_usd, 2, True)}",
                      "green" if rec.ret > 0 else "red" if rec.ret < 0 else "gray"))
    ui.kpi(c[2], "Retorno no mês (MTD)", fmt.pct(per.get("mtd"), signed=True), "composto")
    ui.kpi(c[3], "Retorno no ano (YTD)", fmt.pct(per.get("ytd"), signed=True), "composto")
    ui.kpi(c[4], "Desde o início (ITD)", fmt.pct(per.get("itd"), signed=True),
           f"{per.get('n_days')} pregão(ões)",
           help=f"Composto desde o primeiro registro ({fmt.date_br(per.get('first_date'))}).")

    c = st.columns(5)
    ui.kpi(c[0], "Vol ex-ante", fmt.pct(rk.ex_ante_vol), fmt.vol_status(rk.ex_ante_vol, cfg),
           help="Volatilidade anualizada prevista pelo modelo de risco para a carteira do dia.")
    ui.kpi(c[1], "Vol realizada 21d / 63d",
           f"{fmt.pct(rk.realized_vol_21d)} / {fmt.pct(rk.realized_vol_63d)}",
           fmt.vol_status(rk.realized_vol_21d, cfg) if fmt.is_num(rk.realized_vol_21d)
           else "histórico insuficiente")
    ui.kpi(c[2], "Beta previsto", fmt.num(rk.beta, 3, signed=True),
           fmt.limit_status(rk.beta, cfg.risk.beta_max_abs))
    ui.kpi(c[3], "Gross / net", f"{fmt.pct(rk.gross)} / {fmt.pct(rk.net, signed=True)}",
           fmt.limit_status(rk.net, cfg.risk.net_exposure_max_abs))
    ui.kpi(c[4], "VaR 1d (99%)", fmt.pct(rk.var_1d_99), fmt.max_status(rk.var_1d_99,
                                                                       cfg.risk.var_1d_max))

    c = st.columns(5)
    ui.kpi(c[0], "Drawdown", fmt.pct(rk.drawdown), fmt.ladder_status(rk.drawdown, cfg),
           help=f"Escada: stop suave {fmt.pct(cfg.drawdown.soft_stop, 1)}, stop duro "
                f"{fmt.pct(cfg.drawdown.hard_stop, 1)}, stop-out "
                f"{fmt.pct(cfg.drawdown.stop_out, 1)}.")
    ui.kpi(c[1], "Longs / shorts", f"{rk.n_long} / {rk.n_short}",
           f"L {fmt.pct(rk.long_exposure, 1)} · S {fmt.pct(rk.short_exposure, 1)}",
           help="Exposição comprada (L) e vendida (S) em % do NAV.")
    ui.kpi(c[2], "ES 1d (99%)", fmt.pct(rk.es_1d_99), fmt.max_status(rk.es_1d_99,
                                                                     cfg.risk.es_1d_max))
    ui.kpi(c[3], "Shorts com squeeze HIGH", str(rk.squeeze_high_shorts),
           fmt.Status("monitorar", "red") if rk.squeeze_high_shorts else
           fmt.Status("nenhum", "green"))
    va = None
    if track.compare is not None and not track.compare.empty:
        va = track.compare["cum_value_added"].iloc[-1]
    ui.kpi(c[4], "Valor agregado vs. sombra", fmt.pct(va, signed=True),
           "desde o início" if va is not None else "sem sombra",
           help="CDP ÷ sombra só-quant − 1: o que o PM de IA agregou sobre a carteira só-quant.")
    st.caption(f"Registro diário de {fmt.date_br(rec.date)} · hash "
               f"`{fmt.short_hash(rec.record_hash, 16)}` · números do registro gravado "
               f"{ui.CALC_BADGE}")


def _commentary(state: AppState) -> None:
    rec = state.track.latest
    assert rec is not None
    com = state.commentary(rec)
    if com is None or not com.markdown:
        ui.section("Comentário do dia")
        st.caption("Comentário do dia ainda não publicado para este fechamento.")
        if com is not None:
            ui.bullet_list(list(com.issues))
        return
    badge = ui.IA_BADGE if com.ai else ui.CALC_BADGE
    ui.section("Comentário do dia", badge)
    with st.container(border=True):
        st.markdown(fmt.report_md(com.markdown, demote=2))
    origin = f"Fonte: {com.source}"
    if com.mind:
        origin += f" · mente {fmt.escape_md(com.mind)}"
    st.caption(origin + " · números renderizados pelo código a partir do FactBook do dia.")
    ui.issues(list(com.issues), "Apontamentos do verificador do comentário")


def _execution(wd: data.WeekData, rec: object) -> str:
    """Situação de execução da decisão mais recente vs. o último registro diário."""
    live = getattr(rec, "live_book_week", None)
    if live == wd.week:
        return f"em carteira (registro de {fmt.date_br(getattr(rec, 'date', None))})"
    if wd.booked is not None:
        return "efetivada (aguardando o primeiro registro diário)"
    if wd.decision is not None:
        return ("aguardando a execução no fechamento (MOC) de "
                f"{fmt.date_br(wd.week)} — carteira anterior segue em vigor")
    return "sem decisão gravada"


def _decision(state: AppState) -> None:
    rec = state.track.latest
    wd = state.book.latest  # decisão mais recente (pode ainda não estar executada)
    ui.section("Decisão mais recente", ui.CALC_BADGE)
    if wd is None or wd.proposal is None:
        st.caption("Nenhuma decisão semanal gravada ainda.")
        return
    p, d = wd.proposal, wd.decision
    tz = state.cfg.fund.timezone
    rows = [
        ("Semana", fmt.date_br(wd.week)),
        ("Mente que conduziu", wd.mind or fmt.NA),
        ("Caminho", fmt.PATH_PT.get(wd.path_taken or "", wd.path_taken or fmt.NA)),
        ("Estado", wd.state or fmt.NA),
        ("Execução", _execution(wd, rec)),
        ("Decisão", f"{d.decision.value} ({d.mode.value})" if d else "sem decisão"),
        ("Decidida em", fmt.dt_local(d.decided_at, tz) if d else fmt.NA),
        ("Prazo do mandato", data.decision_timing(d, state.cfg).label if d else fmt.NA),
        ("Vol ex-ante na decisão", fmt.pct(p.risk.ex_ante_vol)),
        ("Longs / shorts", f"{p.risk.n_long} / {p.risk.n_short}"),
        ("approval_hash", fmt.short_hash(d.approval_hash, 16) if d else fmt.NA),
    ]
    ui.table(pd.DataFrame(rows, columns=["Item", "Valor"]))


def _alerts(state: AppState) -> None:
    rec = state.track.latest
    assert rec is not None
    ui.section("Alertas ativos", ui.CALC_BADGE)
    if not rec.alerts:
        st.success("Nenhum alerta no último fechamento.", icon=":material/check_circle:")
        return
    for a in rec.alerts:
        st.warning(fmt.escape_md(a), icon=":material/warning:")


def _events(state: AppState) -> None:
    ui.section("Próximos eventos")
    events = data.next_events(state.now(), state.cfg, state.book.decided_weeks)
    tz = state.cfg.fund.timezone
    if not events:
        st.caption("Sem eventos no calendário dos próximos dias.")
    for e in events:
        text = (f"**{fmt.escape_md(e.label)}** — {fmt.dt_local(e.when, tz)}  \n"
                f"{fmt.escape_md(e.note)}")
        if e.overdue:
            st.error(text, icon=":material/alarm:")
        else:
            st.markdown(text)


def _market(state: AppState) -> None:
    mk = state.market
    if not mk.available:
        if mk.error:
            st.caption(f"Base de mercado indisponível: {fmt.escape_md(mk.error)}")
        return
    with st.expander(f"Contexto de mercado — último pregão da base "
                     f"{fmt.date_br(mk.last_date)} ({mk.n_increments} incremento(s) diários)",
                     icon=":material/public:"):
        st.markdown(ui.CALC_BADGE + " variações do dia calculadas pelo código do comentário "
                    "diário (sem negociação ⇒ n/d).")
        df = pd.DataFrame(mk.facts, columns=["Indicador", "Variação no dia"])
        ui.table(df, height=min(420, 36 * (len(df) + 1)))


def render(state: AppState) -> None:
    st.markdown("### Visão geral")
    track = state.track
    ui.issues(track.issues + state.book.issues)
    if track.empty:
        ui.empty_state(
            "Track record ainda não iniciado",
            f"O primeiro registro diário é gravado no fechamento do pregão de execução da "
            f"primeira carteira decidida (inception prevista: "
            f"{fmt.date_br(state.cfg.fund.inception_date)}, NAV "
            f"{fmt.usd_mm(state.cfg.fund.inception_nav_usd, 0)}). Os indicadores aparecem "
            "aqui assim que o pipeline diário gravar o primeiro `DailyRecord`.")
        left, right = st.columns([3, 2])
        with left:
            _decision(state)
        with right:
            _events(state)
        _market(state)
        return
    _kpis(state)
    st.plotly_chart(charts.nav_chart(track.frame, track.shadow_frame,
                                     track.stats.get("nav_start")),
                    width="stretch", key="overview_nav")
    left, right = st.columns([3, 2])
    with left:
        _commentary(state)
    with right:
        _alerts(state)
        _decision(state)
        _events(state)
    _market(state)
