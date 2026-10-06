"""Página 5 — Posições do último fechamento, com filtros e histórico por emissor."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import charts, data, fmt
from . import components as ui
from .state import AppState


def _targets(state: AppState) -> None:
    prop = state.book.live_proposal(None)
    if prop is None or not prop.positions:
        return
    st.markdown(f"**Carteira-alvo da proposta {fmt.escape_md(prop.proposal_id)}** (ainda não "
                f"marcada a mercado) {ui.CALC_BADGE}")
    df = pd.DataFrame([{"Emissor": t.issuer_id, "Nome": t.name, "Linha": t.execution_ticker,
                        "Tipo": t.line_type.value, "Moeda": t.currency,
                        "Lado": fmt.SIDE_PT.get(t.side.value, t.side.value),
                        "País": t.country, "Setor": t.sector,
                        "Peso": fmt.pct(t.weight, signed=True),
                        "Nocional": fmt.usd_mm(t.notional_usd, 2, True),
                        "Squeeze": t.squeeze_bucket}
                       for t in sorted(prop.positions, key=lambda t: -abs(t.weight))])
    ui.table(df)


def render(state: AppState) -> None:
    st.markdown("### Posições")
    track = state.track
    rec = track.latest
    if rec is None:
        ui.empty_state("Sem posições marcadas",
                       "As posições aparecem após o primeiro fechamento diário (execução MOC da "
                       "carteira decidida).")
        _targets(state)
        return
    prop = state.book.live_proposal(rec)
    df = data.positions_frame(rec, state.book, prop)
    st.caption(f"Posições de fim de dia do registro de {fmt.date_br(rec.date)} (carteira da "
               f"semana {fmt.date_br(rec.live_book_week)}); valores do registro gravado "
               f"{ui.CALC_BADGE}")
    if df.empty:
        st.info("O último registro não tem posições (carteira em caixa).")
        return

    f1, f2, f3 = st.columns(3)
    sides = f1.multiselect("Lado", ["LONG", "SHORT"], format_func=lambda s: fmt.SIDE_PT.get(s, s),
                           key="pos_side", placeholder="Todos")
    sel_c = f2.multiselect("País", sorted(df["country"].dropna().unique()), key="pos_country",
                           placeholder="Todos")
    sel_s = f3.multiselect("Setor", sorted(df["sector"].dropna().unique()), key="pos_sector",
                           placeholder="Todos")
    view = df[df["side"].isin(sides or ["LONG", "SHORT"])
              & (df["country"].isin(sel_c) if sel_c else True)
              & (df["sector"].isin(sel_s) if sel_s else True)]

    c = st.columns(4)
    longs = view[view["side"] == "LONG"]
    shorts = view[view["side"] == "SHORT"]
    ui.kpi(c[0], "Linhas", str(len(view)), f"{len(longs)} long · {len(shorts)} short")
    ui.kpi(c[1], "Valor comprado", fmt.usd_mm(longs["market_value_usd"].sum()),
           f"{fmt.pct(longs['weight'].sum())} do NAV")
    ui.kpi(c[2], "Valor vendido", fmt.usd_mm(shorts["market_value_usd"].sum()),
           f"{fmt.pct(shorts['weight'].sum())} do NAV")
    pnl = view["day_pnl_usd"].sum()
    ui.kpi(c[3], "P&L do dia (filtro)", fmt.usd_mm(pnl, 3, True),
           fmt.Status("soma das linhas", "green" if pnl > 0 else "red" if pnl < 0 else "gray"))

    show = view.assign(side=[fmt.SIDE_PT.get(s, s) for s in view["side"]],
                       repriced=["sim" if r else "não (sem negociação)" for r in view["repriced"]])
    ui.table(ui.formatted(show, {
        "weight": lambda v: fmt.pct(v, signed=True),
        "market_value_usd": lambda v: fmt.usd_mm(v, 3, True),
        "day_pnl_usd": lambda v: fmt.usd(v, 0, True),
        "day_return_usd": lambda v: fmt.pct(v, signed=True),
        "squeeze_score": lambda v: fmt.num(v, 1), "borrow_fee_annual": fmt.pct,
        "days_to_liquidate": fmt.liq(state.cfg),
    }).rename(columns={
        "issuer_id": "Emissor", "name": "Nome", "ticker": "Linha", "line_type": "Tipo",
        "currency": "Moeda", "side": "Lado", "country": "País", "sector": "Setor",
        "weight": "Peso", "market_value_usd": "Valor de mercado", "day_pnl_usd": "P&L do dia",
        "day_return_usd": "Retorno do dia", "repriced": "Reprecificada",
        "squeeze_bucket": "Squeeze", "squeeze_score": "Escore", "borrow_fee_annual": "Aluguel",
        "days_to_liquidate": fmt.liq_label(state.cfg)}),
        height=min(640, 36 * (len(show) + 1)))

    ui.section("Histórico por emissor", ui.CALC_BADGE)
    current = list(dict.fromkeys(df["issuer_id"]))
    issuers = current + [i for i in data.held_issuers(track.records) if i not in current]
    names = data.issuer_meta(state.book)
    iid = st.selectbox("Emissor", issuers, key="pos_issuer",
                       format_func=lambda i: f"{i} · {names.get(i, {}).get('name', '')}"
                       .strip(" ·"))
    if iid:
        hist = data.position_history(track.records, iid)
        st.plotly_chart(charts.position_history_chart(hist, f"{iid}: peso e P&L diário"),
                        width="stretch", key="pos_hist")
        ui.table(ui.formatted(hist.iloc[::-1], {
            "date": fmt.date_br, "side": lambda s: fmt.SIDE_PT.get(s, s),
            "weight": lambda v: fmt.pct(v, signed=True),
            "market_value_usd": lambda v: fmt.usd_mm(v, 3, True),
            "day_pnl_usd": lambda v: fmt.usd(v, 0, True),
            "day_return_usd": lambda v: fmt.pct(v, signed=True),
            "repriced": lambda r: "sim" if r else "não",
        }).rename(columns={"date": "Data", "ticker": "Linha", "side": "Lado", "weight": "Peso",
                           "market_value_usd": "Valor de mercado", "day_pnl_usd": "P&L do dia",
                           "day_return_usd": "Retorno do dia", "repriced": "Reprecificada"}))
