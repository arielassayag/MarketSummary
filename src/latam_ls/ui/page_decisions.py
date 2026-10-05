"""Página 6 — Decisões semanais autônomas: decisão, hashes, caminho, relatório, mudanças,
compliance, ordens, hedges, memo e comparação com a sombra só-quant."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import components as ui
from . import data, fmt
from .state import AppState


def _decision_block(state: AppState, wd: data.WeekData) -> None:
    d = wd.decision
    p = wd.proposal
    tz = state.cfg.fund.timezone
    mind = wd.mind or fmt.NA
    st.markdown(f"**Mente que conduziu a semana:** :violet-badge[{fmt.escape_md(mind)}] · "
                f"**Caminho:** {fmt.escape_md(fmt.PATH_PT.get(wd.path_taken or '', wd.path_taken or fmt.NA))}"
                f" · **Estado:** {fmt.code(wd.state or fmt.NA)}")
    if d is None:
        st.warning("Semana sem decisão gravada.", icon=":material/pending:")
        return
    left, right = st.columns([2, 3])
    with left:
        ui.section("Decisão autônoma")
        rows = [("Decisão", d.decision.value), ("Modo", d.mode.value), ("Assinada por", d.approver),
                ("Mente", d.mind or fmt.NA), ("Decidida em", fmt.dt_local(d.decided_at, tz)),
                ("Prazo do mandato", f"{state.cfg.fund.decision_deadline_local} (Brasília)"),
                ("Convicção", str(d.conviction) if d.conviction else fmt.NA),
                ("Falhas SOFT cientes", ", ".join(d.acknowledged_soft_checks) or "nenhuma"),
                ("Proposta", f"{d.proposal_id} (v{p.version})" if p else d.proposal_id)]
        ui.table(pd.DataFrame(rows, columns=["Item", "Valor"]))
        st.markdown(f"**Racional** {ui.IA_BADGE}")
        ui.plain(d.rationale)
    with right:
        ui.section("Hashes de vinculação", ui.CALC_BADGE,
                   help="Qualquer alteração posterior em proposta, snapshot, mandato, pesquisa, "
                        "decisão do PM ou gates invalida a decisão (verificada pelo livro).")
        hashes = [("approval_hash", d.approval_hash), ("proposal_hash", d.proposal_hash),
                  ("snapshot_hash", d.snapshot_hash), ("config_hash", d.config_hash),
                  ("research_hash", d.research_hash), ("pm_decision_hash", d.pm_decision_hash),
                  ("risk_gate_hash", d.risk_gate_hash), ("audit_head_hash", d.audit_head_hash)]
        ui.table(pd.DataFrame([(k, v or fmt.NA) for k, v in hashes], columns=["Hash", "Valor"]))
        cur = state.config.config_hash
        if d.config_hash == cur:
            st.caption("Mandato atual idêntico ao da decisão (config_hash confere).")
        else:
            st.warning("O mandato atual difere do vigente na decisão (config_hash diferente): "
                       "decisões futuras usam o novo mandato.", icon=":material/info:")


def _attempts(wd: data.WeekData) -> None:
    att = (wd.attempts or {}).get("attempts") or []
    ui.section("Caminho percorrido (gates determinísticos)", ui.CALC_BADGE,
               help="Ordem: carteira do CDP → só restrições da IA/PM → só-quant → manter. A "
                    "primeira alternativa sem falha HARD é decidida.")
    if not att:
        st.caption("Sem registro de tentativas (attempts.json).")
        return
    rows = [{"Tentativa": fmt.PATH_PT.get(str(a.get("label")), str(a.get("label"))),
             "Motivo": str(a.get("why", "")),
             "Vol ex-ante": fmt.pct(a.get("vol")),
             "Longs / shorts": f"{a.get('n_long', fmt.NA)} / {a.get('n_short', fmt.NA)}",
             "Falhas HARD": ", ".join(a.get("hard") or []) or "nenhuma",
             "Resultado": "decidida" if str(a.get("label")) == wd.path_taken else "reprovada"}
            for a in att if isinstance(a, dict)]
    ui.table(pd.DataFrame(rows))
    issues = (wd.attempts or {}).get("input_issues") or []
    if issues:
        with st.expander(f"Apontamentos de validação dos insumos da mente ({len(issues)})"):
            ui.bullet_list([str(i) for i in issues])


def _changes(state: AppState, wd: data.WeekData) -> None:
    p = wd.proposal
    assert p is not None
    prev = state.book.previous(wd.week)
    names = data.issuer_meta(state.book)
    df = data.portfolio_changes(p, prev.proposal if prev else None, names)
    st.caption("Comparação dos pesos-alvo com a semana anterior "
               + (f"({fmt.date_br(prev.week)})" if prev else "(inception: tudo é entrada)")
               + f"; redimensionamento = |Δ peso| ≥ {fmt.pct(data.RESIZE_THRESHOLD)} "
               + ui.CALC_BADGE)
    if df.empty:
        st.info("Sem mudanças relevantes de carteira.")
        return
    counts = df["change"].value_counts()
    c = st.columns(5)
    for col, k in zip(c, ("Entrada", "Saída", "Inversão de lado", "Aumento", "Redução"),
                      strict=False):
        ui.kpi(col, k, str(int(counts.get(k, 0))))
    ui.table(ui.formatted(df, {"w_old": lambda v: fmt.pct(v, signed=True),
                               "w_new": lambda v: fmt.pct(v, signed=True),
                               "delta": lambda v: fmt.pct(v, signed=True)}).rename(
        columns={"issuer_id": "Emissor", "name": "Nome", "change": "Mudança",
                 "w_old": "Peso anterior", "w_new": "Peso novo", "delta": "Δ peso"}))


def _compliance(wd: data.WeekData) -> None:
    p = wd.proposal
    assert p is not None
    df = data.compliance_frame(p)
    if df.empty:
        st.caption("Sem verificações de compliance (carteira mantida).")
        return
    n_hard = int(((df["Severidade"] == "HARD") & (df["Status"] == "FALHA")).sum())
    n_soft = int(((df["Severidade"] == "SOFT") & (df["Status"] == "FALHA")).sum())
    c = st.columns(3)
    ui.kpi(c[0], "Verificações", str(len(df)))
    ui.kpi(c[1], "Falhas HARD", str(n_hard), fmt.Status("bloqueiam a execução",
                                                        "red" if n_hard else "green"))
    ui.kpi(c[2], "Falhas SOFT", str(n_soft), fmt.Status("ciência automática registrada",
                                                        "orange" if n_soft else "green"))
    ui.table(ui.formatted(df, {"Valor": lambda v: fmt.num(v, 4), "Limite": lambda v: fmt.num(v, 4)}),
             height=min(640, 36 * (len(df) + 1)))


def _orders(wd: data.WeekData) -> None:
    p = wd.proposal
    assert p is not None
    ui.section("Ordens (execução no fechamento — MOC)", ui.CALC_BADGE)
    if p.trades:
        ui.table(data.trades_frame(p), height=min(520, 36 * (len(p.trades) + 1)))
    else:
        st.caption("Sem ordens nesta semana.")
    ui.section("Hedges cambiais (NDF)", ui.CALC_BADGE)
    if p.fx_hedges:
        ui.table(data.hedges_frame(p))
    else:
        st.caption("Sem hedges sugeridos.")


def _shadow(wd: data.WeekData) -> None:
    p, s = wd.proposal, wd.shadow
    if p is None or s is None:
        st.caption("Sem carteira-sombra só-quant gravada para esta semana.")
        return
    st.caption("A sombra só-quant usa os mesmos dados e otimizador, sem pesquisa de IA nem decisão "
               "do PM; é executada numa série paralela para medir o valor agregado pela mente "
               + ui.CALC_BADGE)
    ui.table(data.proposal_comparison(p, s))


def _journal(wd: data.WeekData) -> None:
    d = wd.decision
    j = d.journal if d is not None else None
    if j is None:
        st.caption("Sem diário de decisão.")
        return
    st.markdown(f"**Situação** {ui.IA_BADGE}")
    ui.plain(j.situation)
    if j.sizing_rationale:
        st.markdown("**Dimensionamento**")
        ui.plain(j.sizing_rationale)
    if j.ai_vs_quant_vs_pm:
        st.markdown("**IA × quant × PM**")
        ui.plain(j.ai_vs_quant_vs_pm)
    if j.premortem:
        st.markdown("**Premortem**")
        ui.plain(j.premortem)
    if j.positions:
        rows = [{"Emissor": x.issuer_id, "Tese": x.thesis,
                 "Critério de invalidação": x.invalidation_criteria, "Premortem": x.premortem}
                for x in j.positions]
        st.markdown(f"**Diário por posição** {ui.IA_BADGE}")
        ui.table(pd.DataFrame(rows))


def render(state: AppState) -> None:
    st.markdown("### Decisões semanais")
    book = state.book
    weeks = [w for w in book.weeks if w.proposal is not None or w.decisions]
    if not weeks:
        ui.empty_state("Nenhuma decisão semanal ainda",
                       "No primeiro pregão de cada semana na B3 o CDP pesquisa, decide sozinho e "
                       f"grava a decisão até {fmt.escape_md(state.cfg.fund.decision_deadline_local)} "
                       "(Brasília); a execução hipotética ocorre no fechamento.")
        return
    options = [w.week for w in reversed(weeks)]
    week = st.selectbox("Semana", options, format_func=fmt.date_br, key="dec_week")
    wd = book.week(week) or weeks[-1]
    ui.issues(wd.issues)
    _decision_block(state, wd)
    _attempts(wd)
    if wd.proposal is None:
        return
    tabs = st.tabs(["Relatório semanal", "O que mudou", "Compliance", "Ordens e hedges",
                    "Sombra só-quant", "Memo", "Diário de decisão"])
    with tabs[0]:
        reports = [r for r in state.reports if r.kind == "weekly" and r.key == wd.week]
        text = data.read_text(reports[0].md) if reports else None
        if text:
            st.caption(f"`{reports[0].md.as_posix()}` — números formatados pelo código; textos "
                       "de IA rotulados [IA] no próprio relatório.")
            with st.container(border=True, height=900):
                st.markdown(fmt.report_md(text, demote=2))
        else:
            st.caption("Relatório semanal ainda não publicado para esta semana.")
    with tabs[1]:
        _changes(state, wd)
    with tabs[2]:
        _compliance(wd)
    with tabs[3]:
        _orders(wd)
    with tabs[4]:
        _shadow(wd)
    with tabs[5]:
        memo = wd.proposal.memo_markdown
        if memo:
            with st.container(border=True, height=900):
                st.markdown(fmt.report_md(memo, demote=2))
        else:
            st.caption("Proposta sem memo.")
    with tabs[6]:
        _journal(wd)
