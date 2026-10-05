"""Página 3 — Atribuição de performance por período (soma dos registros diários gravados)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from . import charts, data, fmt
from . import components as ui
from .state import AppState

TOP_FACTORS = 12
TOP_ISSUERS = 8


def _period(state: AppState) -> tuple[date, date] | None:
    dates = state.track.dates
    kind = st.segmented_control("Período", list(data.PERIOD_OPTIONS), default="ITD",
                                key="attr_period") or "ITD"
    custom = None
    if kind == "Personalizado":
        picked = st.date_input("Intervalo personalizado", value=(dates[0], dates[-1]),
                               min_value=dates[0], max_value=dates[-1], format="DD/MM/YYYY",
                               key="attr_custom")
        if isinstance(picked, tuple | list) and len(picked) == 2:
            custom = (picked[0], picked[1])
        elif isinstance(picked, tuple | list) and len(picked) == 1:
            custom = (picked[0], picked[0])
    return data.period_bounds(kind, dates, custom)


def _table(df: pd.DataFrame, label: str) -> pd.DataFrame:
    return ui.formatted(df.rename(columns={"name": label}), {
        "pnl_usd": lambda v: fmt.usd(v, 0, signed=True),
        "contribution": lambda v: fmt.bps(v),
    }).rename(columns={"pnl_usd": "P&L (USD)", "contribution": "Contribuição", "days": "Dias"})


def _bars(df: pd.DataFrame, title: str, key: str, labels: list[str] | None = None) -> None:
    if df.empty:
        st.caption("Sem linhas de atribuição no período.")
        return
    st.plotly_chart(charts.signed_bars(labels or df["name"].tolist(),
                                       df["contribution"].tolist(), title, unit="bps"),
                    width="stretch", key=key)


def render(state: AppState) -> None:
    st.markdown("### Atribuição de performance")
    track = state.track
    if track.empty:
        ui.empty_state("Sem atribuição ainda",
                       "A atribuição (fatores × específico, custos, aluguel, financiamento, país, "
                       "setor, lado e emissor) aparece a partir do primeiro registro diário.")
        return
    bounds = _period(state)
    if bounds is None:
        return
    start, end = bounds
    recs = data.records_between(track.records, start, end)
    st.caption(f"Período: {fmt.date_br(start)} a {fmt.date_br(end)} · {len(recs)} pregão(ões) · "
               f"somas dos registros diários gravados {ui.CALC_BADGE}")
    if not recs:
        st.info("Nenhum registro no período escolhido.")
        return
    gaps = track.unreadable_between(start, end)
    if gaps:
        st.error(f"{len(gaps)} pregão(ões) com registro ilegível no período ("
                 + ", ".join(fmt.date_br(g) for g in gaps) + "): retorno e P&L do período ficam "
                 "n/d e as somas abaixo estão incompletas.", icon=":material/gpp_bad:")
    va = data.value_added_series(track.compare, start, end)
    c = st.columns(4)
    period_ret = None if gaps else data.compound(r.ret for r in recs)
    period_pnl = None if gaps else sum(r.pnl_usd for r in recs)
    ui.kpi(c[0], "Retorno no período", fmt.pct(period_ret, signed=True),
           "composto dos retornos diários")
    ui.kpi(c[1], "P&L no período", fmt.usd_mm(period_pnl, 3, True),
           "soma dos P&L diários")
    ui.kpi(c[2], "Sombra só-quant", fmt.pct(va["cum_shadow"].iloc[-1] if not va.empty else None,
                                            signed=True), "composto no período")
    ui.kpi(c[3], "Valor agregado pelo PM de IA",
           fmt.pct(va["value_added"].iloc[-1] if not va.empty else None, signed=True),
           fmt.Status("CDP ÷ sombra − 1", "green" if not va.empty
                      and va["value_added"].iloc[-1] > 0 else "gray"))

    comp = data.components_table(recs)
    left, right = st.columns([3, 2])
    with left:
        ui.section("Por componente", ui.CALC_BADGE,
                   help="Ações = fatorial + específico; NAV = ações + custos + aluguel + "
                        "financiamento. Contribuição = soma das contribuições diárias (P&L / NAV "
                        "de abertura).")
        _bars(comp[comp["key"] != "equity"], "Contribuição por componente (bps do NAV)",
              "attr_comp")
    with right:
        st.write("")
        ui.table(_table(comp.drop(columns="key"), "Componente"))
        st.caption("Ações (total) = fatorial + específico; fora do gráfico para não contar duas "
                   "vezes.")

    left, right = st.columns(2)
    with left:
        ui.section("Por grupo de fatores", ui.CALC_BADGE)
        fg = data.attribution_table(recs, "factor_group")
        _bars(fg, "Grupos de fatores (bps)", "attr_fg",
              [fmt.GROUP_PT.get(n, n) for n in fg["name"]])
    with right:
        ui.section("Principais fatores", ui.CALC_BADGE)
        fac = data.attribution_table(recs, "factor")
        if not fac.empty:
            fac = fac.reindex(fac["pnl_usd"].abs().sort_values(ascending=False).index)
            fac = fac.head(TOP_FACTORS).sort_values("pnl_usd", ascending=False)
        _bars(fac, f"Top {TOP_FACTORS} fatores por |P&L| (bps)", "attr_fac")

    tabs = st.tabs(["País", "Setor", "Long × short", "Emissores"])
    with tabs[0]:
        df = data.attribution_table(recs, "country")
        _bars(df, "Contribuição por país (bps)", "attr_country")
        ui.table(_table(df, "País"))
    with tabs[1]:
        df = data.attribution_table(recs, "sector")
        _bars(df, "Contribuição por setor (bps)", "attr_sector")
        ui.table(_table(df, "Setor"))
    with tabs[2]:
        df = data.attribution_table(recs, "side")
        _bars(df, "Perna comprada × vendida (bps)", "attr_side",
              [fmt.SIDE_PT.get(n, n) for n in df["name"]])
        ui.table(_table(df.assign(name=[fmt.SIDE_PT.get(n, n) for n in df["name"]]), "Lado"))
    with tabs[3]:
        names = data.issuer_meta(state.book)
        df = data.attribution_table(recs, "issuer")
        df = df.assign(name=[f"{n} · {names.get(n, {}).get('name', '')}".strip(" ·")
                             for n in df["name"]])
        l2, r2 = st.columns(2)
        with l2:
            st.markdown(f"**Maiores contribuidores** {ui.CALC_BADGE}")
            ui.table(_table(df[df["pnl_usd"] > 0].head(TOP_ISSUERS), "Emissor"))
        with r2:
            st.markdown(f"**Maiores detratores** {ui.CALC_BADGE}")
            worst = df[df["pnl_usd"] < 0].sort_values("pnl_usd").head(TOP_ISSUERS)
            ui.table(_table(worst, "Emissor"))

    ui.section("CDP vs. sombra só-quant", ui.CALC_BADGE,
               help="A sombra executa a carteira só-quant da mesma semana, sem a pesquisa de IA "
                    "nem a decisão do PM: a diferença é o valor agregado pela mente.")
    if va.empty:
        st.caption("Sem série-sombra no período.")
    else:
        st.plotly_chart(charts.value_added_chart(va), width="stretch", key="attr_va")
