"""Página 2 — Track record diário: registros, grade mensal, vol × banda, drawdown, integridade."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from . import charts, data, fmt
from . import components as ui
from .state import AppState


def _stats(state: AppState) -> None:
    s = state.track.stats
    if not s or not s.get("n_days"):
        return
    c = st.columns(5)
    ui.kpi(c[0], "Retorno desde o início", fmt.pct(s.get("since_inception_return"), signed=True),
           f"{s.get('n_days')} pregão(ões)")
    ui.kpi(c[1], "Retorno anualizado", fmt.pct(s.get("annualized_return"), signed=True),
           fmt.Status("pouco informativo", "orange") if s.get("annualization_note")
           else "composto")
    ui.kpi(c[2], "Vol anualizada", fmt.pct(s.get("annualized_vol")),
           s.get("realized_vol_status") or "")
    ui.kpi(c[3], "Sharpe", fmt.num(s.get("sharpe"), 2), "sobre caixa USD 3M",
           help="Excesso de retorno sobre o financiamento registrado (taxa USD 3M, ACT/360).")
    ui.kpi(c[4], "Drawdown máximo", fmt.pct(s.get("max_drawdown")),
           fmt.ladder_status(s.get("max_drawdown"), state.cfg))
    best, worst = s.get("best_day"), s.get("worst_day")
    st.caption(
        f"Dias positivos: {fmt.pct(s.get('pct_positive_days'), 1)} · melhor dia: "
        + (f"{fmt.date_br(best[0])} ({fmt.pct(best[1], signed=True)})" if best else fmt.NA)
        + " · pior dia: "
        + (f"{fmt.date_br(worst[0])} ({fmt.pct(worst[1], signed=True)})" if worst else fmt.NA)
        + f" · estatísticas de `TrackRecord.stats()` {ui.CALC_BADGE}")
    if s.get("annualization_note"):
        st.caption(fmt.escape_md(s["annualization_note"]))


def _records_table(state: AppState) -> None:
    ui.section("Registros diários", ui.CALC_BADGE,
               help="Um DailyRecord imutável por pregão, encadeado por hash ao anterior.")
    df = data.track_table(state.track.records).iloc[::-1]
    usd = lambda v: fmt.usd_mm(v, 3, signed=True)  # noqa: E731
    show = ui.formatted(df, {
        "Data": fmt.date_br, "NAV (USD)": lambda v: fmt.usd_mm(v, 2),
        "Retorno": lambda v: fmt.pct(v, 3, signed=True), "P&L (USD)": usd, "Fatorial": usd,
        "Específico": usd, "Custos": usd, "Aluguel": usd, "Financiamento": usd,
        "Gross": fmt.pct, "Net": lambda v: fmt.pct(v, signed=True),
        "Beta": lambda v: fmt.num(v, 3, signed=True), "Vol ex-ante": fmt.pct,
        "Drawdown": fmt.pct,
    })
    ui.table(show, height=min(560, 36 * (len(show) + 1)))


def _month_css(v: object) -> str:
    if not fmt.is_num(v):
        return "color: #9AA3AF"
    x = float(v)  # type: ignore[arg-type]
    if x > 0:
        return "color: #0E7C7B; font-weight: 600"
    if x < 0:
        return "color: #D1495B; font-weight: 600"
    return ""


def _monthly(state: AppState) -> None:
    ui.section("Retornos mensais", ui.CALC_BADGE,
               help="Retornos diários compostos por mês; mês sem registro fica vazio (não zero).")
    table = state.track.monthly
    if table is None or table.empty:
        st.caption("Sem meses com registros ainda.")
        return
    t = table.copy()
    t.index = [str(i) for i in t.index]
    t.index.name = "Ano"
    css = t.map(_month_css)
    text = t.map(lambda v: fmt.pct(v, 2, signed=True) if fmt.is_num(v) else "—")
    st.dataframe(text.style.apply(lambda _: css, axis=None), width="stretch")


def _charts(state: AppState) -> None:
    series = data.risk_series(state.track.records)
    left, right = st.columns(2)
    with left:
        st.plotly_chart(charts.vol_chart(series, state.cfg), width="stretch", key="tr_vol")
    with right:
        dd = series["drawdown"] if "drawdown" in series else pd.Series(dtype=float)
        st.plotly_chart(charts.drawdown_chart(dd.replace([np.inf, -np.inf], np.nan).dropna(),
                                              state.cfg), width="stretch", key="tr_dd")


def _integrity(state: AppState) -> None:
    ui.section("Integridade", help="Recalcula todos os hashes dos registros, confere os elos, o "
                                   "CSV × JSON e a presença de cada registro na trilha.")
    if st.button("Verificar integridade", icon=":material/verified:", key="verify_track",
                 type="primary"):
        st.session_state["cdp_track_checks"] = data.verify_track_integrity(state.paths.book)
    results = st.session_state.get("cdp_track_checks")
    if results:
        ui.checks(results)


def render(state: AppState) -> None:
    st.markdown("### Track record diário")
    track = state.track
    ui.issues(track.issues)
    st.caption(f"{fmt.escape_md(state.cfg.fund.track_record_type)} · NAV em USD · retornos "
               "diários do NAV de abertura ao de fechamento.")
    if track.empty:
        ui.empty_state("Sem registros diários",
                       "O track record começa no fechamento do pregão de execução da primeira "
                       "carteira (MOC). Volte após o primeiro fechamento diário.")
        _integrity(state)
        return
    _stats(state)
    _charts(state)
    _monthly(state)
    _records_table(state)
    if track.csv_bytes:
        st.download_button("Baixar track_record.csv", data=track.csv_bytes,
                           file_name="track_record.csv", mime="text/csv",
                           icon=":material/download:", key="dl_track_csv")
    _integrity(state)
