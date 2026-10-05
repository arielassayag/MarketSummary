"""Página 4 — Risco: vol ex-ante, fatores, exposições vs. limites, VaR/ES, estresse, liquidez,
squeeze, câmbio e alertas (registro diário mais recente + proposta vigente)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import charts, data, fmt
from . import components as ui
from .state import AppState


def _tiles(state: AppState) -> None:
    cfg = state.cfg
    rec = state.track.latest
    prop = state.book.live_proposal(rec)
    rk = rec.risk if rec is not None else None
    pr = prop.risk if prop is not None else None
    vol = rk.ex_ante_vol if rk is not None else (pr.ex_ante_vol if pr else None)
    fvol = rk.factor_vol if rk is not None else (pr.factor_vol if pr else None)
    svol = rk.specific_vol if rk is not None else (pr.specific_vol if pr else None)
    c = st.columns(5)
    ui.kpi(c[0], "Vol ex-ante (total)", fmt.pct(vol), fmt.vol_status(vol, cfg))
    ui.kpi(c[1], "Vol fatorial", fmt.pct(fvol), "componente sistemático")
    ui.kpi(c[2], "Vol específica", fmt.pct(svol), "alpha puro (idiossincrático)")
    share = pr.factor_risk_share if pr is not None else None
    ui.kpi(c[3], "Fatia fatorial da variância", fmt.pct(share),
           fmt.max_status(share, cfg.risk.max_factor_risk_share) if share is not None
           else "sem proposta")
    beta = rk.beta if rk is not None else (pr.beta if pr else None)
    ui.kpi(c[4], "Beta previsto", fmt.num(beta, 3, signed=True),
           fmt.limit_status(beta, cfg.risk.beta_max_abs))
    c = st.columns(5)
    var1 = rk.var_1d_99 if rk is not None else (pr.var_1d_99 if pr else None)
    es1 = rk.es_1d_99 if rk is not None else (pr.es_1d_99 if pr else None)
    ui.kpi(c[0], "VaR 1d (99%)", fmt.pct(var1), fmt.max_status(var1, cfg.risk.var_1d_max))
    ui.kpi(c[1], "ES 1d (99%)", fmt.pct(es1), fmt.max_status(es1, cfg.risk.es_1d_max))
    ui.kpi(c[2], "VaR 1 semana (99%)", fmt.pct(pr.var_1w_99 if pr else None), "na decisão")
    mdl = rk.max_days_to_liquidate if rk is not None else (
        pr.max_days_to_liquidate if pr else None)
    ui.kpi(c[3], "Máx. dias p/ liquidar", fmt.days(mdl),
           fmt.max_status(mdl, cfg.liquidity.max_days_to_liquidate_long, fmt.days)
           if fmt.is_num(mdl) else "n/d")
    liq1 = rk.pct_gross_liquid_1d if rk is not None else (
        pr.pct_nav_liquidated_1d if pr else None)
    ui.kpi(c[4], "Gross liquidável em 1 dia", fmt.pct(liq1),
           f"participação {fmt.pct(cfg.liquidity.participation_rate, 0)} do ADTV")
    src = []
    if rec is not None:
        src.append(f"registro diário de {fmt.date_br(rec.date)} (carteira derivada no dia)")
    if prop is not None:
        src.append(f"proposta {fmt.code(prop.proposal_id)} v{prop.version} "
                   f"(ex-ante na decisão de {fmt.date_br(prop.week)})")
    st.caption("Fontes: " + "; ".join(src) + f" {ui.CALC_BADGE}")


def _factors(state: AppState) -> None:
    prop = state.book.live_proposal(state.track.latest)
    ui.section("Contribuição ao risco por fator", ui.CALC_BADGE,
               help="Decomposição da variância ex-ante da carteira vigente (proposta da semana).")
    if prop is None or not prop.risk.factor_contributions:
        st.caption("Sem decomposição fatorial gravada.")
        return
    fc = prop.risk.factor_contributions
    items = sorted(fc.items(), key=lambda kv: -abs(kv[1]))
    st.plotly_chart(charts.signed_bars([k for k, _ in items], [v for _, v in items],
                                       "Contribuição por fator (% da variância)", unit="pct"),
                    width="stretch", key="risk_factors")
    top = prop.risk.top_risk_contributors
    if top:
        names = data.issuer_meta(state.book)
        df = pd.DataFrame([{"Emissor": k, "Nome": names.get(k, {}).get("name", k),
                            "Contribuição ao risco": fmt.pct(v)}
                           for k, v in sorted(top.items(), key=lambda kv: -abs(kv[1]))])
        with st.expander("Maiores contribuidores de risco por emissor"):
            ui.table(df)


def _exposures(state: AppState) -> None:
    rec = state.track.latest
    prop = state.book.live_proposal(rec)
    lines = list(rec.risk.exposures) if rec is not None and rec.risk.exposures else (
        list(prop.risk.exposures) if prop is not None else [])
    market_lines = [e for e in (prop.risk.exposures if prop is not None else [])
                    if e.group in ("market", "currency")]
    lines = [e for e in lines if e.group not in ("market", "currency")] + market_lines
    df = data.exposures_frame(lines)
    ui.section("Exposições vs. limites do mandato", ui.CALC_BADGE)
    if df.empty:
        st.caption("Sem exposições gravadas.")
        return
    tabs = st.tabs(["País", "Setor", "Estilo", "Temas, commodities e moedas"])
    for tab, group, title in ((tabs[0], "country", "Exposição líquida por país (% NAV)"),
                              (tabs[1], "sector", "Exposição líquida por setor (% NAV)")):
        with tab:
            sub = df[df["group"] == group]
            if sub.empty:
                st.caption("Sem linhas.")
                continue
            left, right = st.columns(2)
            with left:
                st.plotly_chart(charts.exposure_chart(sub, title), width="stretch",
                                key=f"risk_exp_{group}")
            with right:
                st.plotly_chart(charts.long_short_bars(sub.sort_values("gross", ascending=False),
                                                       "Pernas comprada e vendida (% NAV)"),
                                width="stretch", key=f"risk_ls_{group}")
    with tabs[2]:
        sub = df[df["group"] == "style"]
        if sub.empty:
            st.caption("Sem linhas de estilo.")
        else:
            lim = sub["limit"].dropna()
            st.plotly_chart(charts.signed_bars(
                sub["name"].tolist(), sub["net"].tolist(),
                "Exposição a estilos (desvios-padrão × NAV)", unit="x",
                limit=float(lim.iloc[0]) if not lim.empty else None),
                width="stretch", key="risk_exp_style")
    with tabs[3]:
        sub = df[df["group"].isin(["market", "currency"])]
        if sub.empty:
            st.caption("Sem exposições a temas, commodities ou moedas gravadas.")
        else:
            show = sub.assign(status=[fmt.limit_status(n, lim).label
                                      for n, lim in zip(sub["net"], sub["limit"], strict=False)])
            ui.table(ui.formatted(show[["name", "net", "gross", "limit", "status"]], {
                "net": lambda v: fmt.pct(v, signed=True), "gross": fmt.pct,
                "limit": lambda v: f"±{fmt.pct(v)}" if fmt.is_num(v) else "—",
            }).rename(columns={"name": "Linha", "net": "Líquida", "gross": "Bruta",
                               "limit": "Limite", "status": "Status"}))


def _stress(state: AppState) -> None:
    prop = state.book.live_proposal(state.track.latest)
    ui.section("Testes de estresse", ui.CALC_BADGE,
               help="P&L estimado da carteira vigente (% do NAV) em cenários históricos e "
                    "hipotéticos; n/d = cenário sem dados suficientes no histórico.")
    if prop is None or not prop.risk.stress_tests:
        st.caption("Sem testes de estresse gravados.")
        return
    df = data.stress_frame(prop.risk.stress_tests)
    lim = state.cfg.risk.country_stress_max_loss
    df["Status"] = ["n/d" if not fmt.is_num(v) else
                    ("perda acima do teto de gap de país" if str(k).startswith("Gap ")
                     and v < -lim else "ok") for k, v in zip(df["Cenário"], df["value"],
                                                             strict=False)]
    ui.table(ui.formatted(df, {"value": lambda v: fmt.pct(v, 2, signed=True)}).rename(
        columns={"value": "P&L (% NAV)"}), height=min(520, 36 * (len(df) + 1)))


def _liquidity(state: AppState) -> None:
    prop = state.book.live_proposal(state.track.latest)
    ui.section("Perfil de liquidez", ui.CALC_BADGE,
               help="Dias para liquidar cada posição a "
                    f"{fmt.pct(state.cfg.liquidity.participation_rate, 0)} do ADTV (gravado na "
                    "proposta vigente).")
    if prop is None or not prop.positions:
        st.caption("Sem posições na proposta vigente.")
        return
    st.plotly_chart(charts.bucket_bars(data.liquidity_buckets(prop.positions),
                                       "Fatia do gross por dias para liquidar"),
                    width="stretch", key="risk_liq")
    rows = sorted(prop.positions, key=lambda p: -(p.days_to_liquidate or 0.0))[:10]
    df = pd.DataFrame([{"Emissor": p.issuer_id, "Linha": p.execution_ticker,
                        "Lado": fmt.SIDE_PT.get(p.side.value, p.side.value),
                        "Peso": fmt.pct(p.weight, signed=True), "% ADTV": fmt.pct(p.pct_adtv),
                        "Dias p/ liquidar": fmt.days(p.days_to_liquidate)} for p in rows])
    ui.table(df)


def _squeeze(state: AppState) -> None:
    rec = state.track.latest
    prop = state.book.live_proposal(rec)
    ui.section("Monitor de short squeeze", ui.CALC_BADGE,
               help="Balde e escore de squeeze da proposta vigente para cada short; HIGH ⇒ "
                    "short proibido na decisão e alerta diário se o balde piorar.")
    df = data.squeeze_frame(prop, rec)
    if df.empty:
        st.caption("Sem shorts vigentes.")
        return
    counts = df["bucket"].value_counts()
    alerted = data.squeeze_alerted(rec)
    c = st.columns(4)
    n_high = rec.risk.squeeze_high_shorts if rec is not None else 0
    ui.kpi(c[0], "HIGH no último fechamento", str(n_high),
           fmt.Status("reavaliar/reduzir" if n_high else "nenhum", "red" if n_high else "green"),
           help="Balde recalculado na rotina diária (registro do dia).")
    for col, b, color in zip(c[1:], ("HIGH", "MEDIUM", "LOW"), ("red", "orange", "green"),
                             strict=False):
        ui.kpi(col, f"{b} na decisão", str(int(counts.get(b, 0))),
               fmt.Status("balde da proposta", color))
    df = df.assign(alert=["HIGH (alerta diário)" if i in alerted else "—"
                          for i in df["issuer_id"]])
    ui.table(ui.formatted(df, {
        "weight": lambda v: fmt.pct(v, signed=True), "score": lambda v: fmt.num(v, 1),
        "borrow_fee": fmt.pct, "days_to_liquidate": fmt.days,
    }).rename(columns={"issuer_id": "Emissor", "name": "Nome", "ticker": "Linha",
                       "weight": "Peso", "bucket": "Balde na decisão", "score": "Escore",
                       "alert": "Último fechamento",
                       "borrow_fee": "Aluguel a.a.", "days_to_liquidate": "Dias p/ liquidar"}))


def _fx(state: AppState) -> None:
    prop = state.book.live_proposal(state.track.latest)
    ui.section("Câmbio: exposição residual e hedges", ui.CALC_BADGE)
    if prop is None or not prop.fx_hedges:
        st.caption("Sem hedges cambiais sugeridos na proposta vigente.")
        return
    ui.table(data.hedges_frame(prop))


def _alerts(state: AppState) -> None:
    rec = state.track.latest
    ui.section("Alertas do último fechamento", ui.CALC_BADGE)
    if rec is None:
        st.caption("Sem registro diário.")
        return
    if not rec.alerts:
        st.success("Nenhum alerta.", icon=":material/check_circle:")
    for a in rec.alerts:
        st.warning(fmt.escape_md(a), icon=":material/warning:")


def render(state: AppState) -> None:
    st.markdown("### Risco")
    rec = state.track.latest
    prop = state.book.live_proposal(rec)
    if rec is None and prop is None:
        ui.empty_state("Sem carteira para medir risco",
                       "O painel de risco usa o registro diário mais recente e a proposta "
                       "vigente; ambos ainda não existem.")
        return
    _tiles(state)
    _factors(state)
    _exposures(state)
    left, right = st.columns(2)
    with left:
        _stress(state)
    with right:
        _liquidity(state)
    _squeeze(state)
    left, right = st.columns([3, 2])
    with left:
        _fx(state)
    with right:
        _alerts(state)
