"""Página 7 — Pesquisa IA da semana: macro, notas por emissor, visões (IA × PM), decisão do PM,
ledger de chamadas e sinais de governança. Todo texto de IA leva o selo "IA" e é exibido como
texto puro; notícias são conteúdo não confiável."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..contracts import EvidenceRef
from . import components as ui
from . import data, fmt
from .state import AppState

_STANCE = {2: "+2 forte compra", 1: "+1 compra", 0: "0 neutra", -1: "−1 venda",
           -2: "−2 forte venda"}
_ROLE_PT = {"fundamental": "Fundamentalista", "news_sentiment": "Notícias",
            "short_risk": "Risco de short", "bull_bear_judge": "Juiz bull × bear", "pm": "PM"}
_POSTURE = {"muito_defensiva": "muito defensiva", "defensiva": "defensiva", "neutra": "neutra",
            "ofensiva": "ofensiva"}
_REGIME = {"risk_on": "risk-on", "neutral": "neutro", "risk_off": "risk-off"}


def _evidence_rows(refs: list[EvidenceRef], facts: dict[str, str]) -> pd.DataFrame:
    rows = []
    for e in refs:
        kind = getattr(e.kind, "value", str(e.kind))
        value = facts.get(e.ref_id, "") if kind == "fact" else ""
        rows.append({"Tipo": {"fact": "fato [Calculado]", "news": "notícia [não confiável]",
                              "source": "fonte externa"}.get(kind, kind),
                     "Referência": e.ref_id, "Valor": value,
                     "Link": data.safe_url(e.ref_id) if kind == "source" else None,
                     "Nota": e.note})
    return pd.DataFrame(rows, columns=["Tipo", "Referência", "Valor", "Link", "Nota"])


def _evidence(refs: list[EvidenceRef], facts: dict[str, str], key: str) -> None:
    if not refs:
        st.caption("Sem evidências citadas.")
        return
    df = _evidence_rows(refs, facts)
    if df["Link"].isna().all():
        df = df.drop(columns="Link")
    ui.table(df, key=key,
             column_config={"Link": st.column_config.LinkColumn("Link", display_text="abrir")})


def _macro(wd: data.WeekData) -> None:
    pack = wd.research
    notes = [m for m in (pack.macro if pack else [])
             if m.scope.upper() not in data.GOVERNANCE_SCOPES]
    if not notes:
        st.caption("Sem notas macro na semana.")
        return
    notes = sorted(notes, key=lambda m: m.scope)
    st.markdown(f"{len(notes)} nota(s) macro {ui.IA_BADGE}")
    ui.table(pd.DataFrame([{"Escopo": m.scope, "Stance": _STANCE.get(m.stance, str(m.stance)),
                            "Regime": data.render_facts(m.regime, wd.facts),
                            "Eventos": len(m.key_events), "Riscos": len(m.risks),
                            "Abstenção": "sim" if m.regime.startswith("indeterminado") else "não"}
                           for m in notes]))
    for i, m in enumerate(notes):
        with st.expander(f"{m.scope} — stance {_STANCE.get(m.stance, m.stance)}",
                         icon=":material/public:", expanded=(i == 0)):
            st.markdown(f"{ui.IA_BADGE} · provedor {fmt.code(m.provider)} · "
                        f"prompt {fmt.code(m.prompt_version)}")
            ui.plain(data.render_facts(m.regime, wd.facts), prefix="**Regime:** ")
            ui.plain(data.render_facts(m.summary, wd.facts))
            if m.key_events:
                st.markdown("**Eventos-chave**")
                ui.bullet_list([f"{e.description} ({e.direction}"
                                + (f", {fmt.date_br(e.expected_date)})" if e.expected_date else ")")
                                for e in m.key_events])
            if m.risks:
                st.markdown("**Riscos**")
                ui.bullet_list([data.render_facts(r, wd.facts) for r in m.risks])
            if m.portfolio_implications:
                st.markdown("**Implicações para a carteira**")
                ui.bullet_list([data.render_facts(r, wd.facts) for r in m.portfolio_implications])
            _evidence(list(m.evidence), wd.facts, key=f"macro_ev_{i}")


def _notes(state: AppState, wd: data.WeekData) -> None:
    pack = wd.research
    notes = list(pack.notes) if pack else []
    if not notes:
        st.caption("Sem notas por emissor na semana.")
        return
    names = data.issuer_meta(state.book)
    issuers = sorted({n.issuer_id for n in notes})
    c1, c2 = st.columns([2, 3])
    iid = c1.selectbox("Emissor", ["(todos)", *issuers], key="res_issuer",
                       format_func=lambda i: i if i == "(todos)" else
                       f"{i} · {names.get(i, {}).get('name', '')}".strip(" ·"))
    roles = sorted({n.role for n in notes})
    sel_roles = c2.multiselect("Papel do analista", roles, default=roles, key="res_roles",
                               format_func=lambda r: _ROLE_PT.get(r, r))
    shown = [n for n in notes if (iid == "(todos)" or n.issuer_id == iid) and n.role in sel_roles]
    summary = pd.DataFrame([{"Emissor": n.issuer_id, "Papel": _ROLE_PT.get(n.role, n.role),
                             "Stance": _STANCE.get(n.stance, str(n.stance)),
                             "Confiança": fmt.pct(n.confidence, 0),
                             "Squeeze": n.squeeze.verdict if n.squeeze else "—",
                             "Abstenção": "sim" if data.is_abstention_note(n) else "não"}
                            for n in shown])
    st.markdown(f"{len(shown)} nota(s) {ui.IA_BADGE}")
    ui.table(summary, height=min(360, 36 * (len(summary) + 1)))
    for i, n in enumerate(shown[:40]):
        title = (f"{n.issuer_id} · {_ROLE_PT.get(n.role, n.role)} · stance "
                 f"{_STANCE.get(n.stance, n.stance)} · confiança {fmt.pct(n.confidence, 0)}")
        with st.expander(title, icon=":material/smart_toy:"):
            st.markdown(f"{ui.IA_BADGE} · provedor {fmt.code(n.provider)} · horizonte "
                        f"{n.horizon_weeks} semanas · nota {fmt.code(n.note_id)}")
            ui.plain(data.render_facts(n.thesis, wd.facts), prefix="**Tese:** ")
            cols = st.columns(2)
            with cols[0]:
                st.markdown("**Bull**")
                ui.bullet_list([data.render_facts(x, wd.facts) for x in n.bull_points])
            with cols[1]:
                st.markdown("**Bear**")
                ui.bullet_list([data.render_facts(x, wd.facts) for x in n.bear_points])
            if n.catalysts:
                st.markdown("**Catalisadores**")
                ui.bullet_list([f"{c.description} ({c.direction}"
                                + (f", {fmt.date_br(c.expected_date)})" if c.expected_date
                                   else ")") for c in n.catalysts])
            if n.key_risks:
                st.markdown("**Riscos**")
                ui.bullet_list([data.render_facts(x, wd.facts) for x in n.key_risks])
            if n.squeeze is not None:
                ui.plain(n.squeeze.rationale, prefix=f"**Squeeze ({n.squeeze.verdict}):** ")
            _evidence(list(n.evidence), wd.facts, key=f"note_ev_{i}")
    if len(shown) > 40:
        st.caption(f"Exibindo 40 de {len(shown)} notas; use o filtro por emissor.")


def _views(wd: data.WeekData) -> None:
    df = data.views_table(wd)
    st.caption("Visões da IA (pesquisa; só restringem ou inclinam dentro do teto) e do PM "
               "(decisão da mente; viram inclinações limitadas pelo código).")
    if df.empty:
        st.caption("Sem visões registradas.")
        return
    show = ui.formatted(df, {
        "ai_score": lambda v: _STANCE.get(int(v), str(v)) if fmt.is_num(v) else "—",
        "ai_conf": lambda v: fmt.pct(v, 0) if fmt.is_num(v) else "—",
        "pm_stance": lambda v: _STANCE.get(int(v), str(v)) if fmt.is_num(v) else "—",
        "pm_conviction": lambda v: f"{int(v)}/5" if fmt.is_num(v) else "—",
        "pm_horizon": lambda v: f"{int(v)} sem." if fmt.is_num(v) else "—",
    }).fillna("—").rename(columns={
        "issuer_id": "Emissor", "ai_score": "IA: stance", "ai_conf": "IA: confiança",
        "ai_limits": "IA: limites", "ai_rationale": "IA: racional", "pm_stance": "PM: stance",
        "pm_conviction": "PM: convicção", "pm_horizon": "PM: horizonte",
        "pm_exclusion": "PM: exclusão", "pm_rationale": "PM: racional"})
    st.markdown(ui.IA_BADGE)
    ui.table(show, height=min(560, 36 * (len(show) + 1)))


def _pm(wd: data.WeekData) -> None:
    pm = wd.pm_output
    if pm is None:
        st.caption("Decisão estruturada do PM (inputs/pm_decision.json) não encontrada.")
        return
    st.markdown(f"{ui.IA_BADGE} · mente :violet-badge[{fmt.escape_md(pm.mind)}] · regime "
                f"{fmt.code(_REGIME.get(pm.regime, pm.regime))} · postura "
                f"{fmt.code(_POSTURE.get(pm.risk_posture, pm.risk_posture))} · abstenção: "
                f"{'sim' if pm.abstain else 'não'}")
    for title, text in (("Leitura de mercado", pm.market_view),
                        ("O que mudou", pm.what_changed),
                        ("Avaliação da semana anterior", pm.evaluation_last_week)):
        st.markdown(f"**{title}**")
        ui.plain(data.render_facts(text, wd.facts))
    if pm.position_journal:
        st.markdown("**Diário por posição**")
        ui.table(pd.DataFrame([{"Emissor": j.issuer_id,
                                "Tese": data.render_facts(j.thesis, wd.facts),
                                "Invalidação": data.render_facts(j.invalidation_criteria,
                                                                 wd.facts),
                                "Premortem": data.render_facts(j.premortem, wd.facts)}
                               for j in pm.position_journal]))
    st.caption("Placeholders {{fact:id}} renderizados com o FactBook do briefing da semana "
               "(valores calculados pelo código).")


def _ledger(wd: data.WeekData) -> None:
    stats = data.llm_stats(wd.llm_calls)
    if not stats.get("n_calls"):
        st.caption("Sem ledger de chamadas de IA nesta semana (a mente pode ter escrito os "
                   "arquivos diretamente).")
        return
    c = st.columns(4)
    ui.kpi(c[0], "Chamadas", str(stats["n_calls"]),
           f"{stats['parse_ok']} válidas · {stats['failed']} falhas")
    ui.kpi(c[1], "Com apontamentos", str(stats["with_issues"]))
    tokens = (f"{fmt.num(stats['input_tokens'], 0)} / {fmt.num(stats['output_tokens'], 0)}"
              if stats.get("input_tokens") is not None else fmt.NA)
    ui.kpi(c[2], "Tokens (entrada / saída)", tokens)
    ui.kpi(c[3], "Custo", fmt.usd(stats.get("cost_usd"), 2),
           f"latência mediana {fmt.num(stats.get('latency_median_ms'), 0)} ms")
    st.caption("Provedores: " + fmt.escape_md(", ".join(stats["providers"]) or fmt.NA)
               + " · modelos: " + fmt.escape_md(", ".join(stats["models"]) or fmt.NA)
               + " · versões de prompt: "
               + fmt.escape_md(", ".join(stats["prompt_versions"]) or fmt.NA))
    ui.table(pd.DataFrame(sorted(stats["by_task"].items()), columns=["Tarefa", "Chamadas"]))


def _news(wd: data.WeekData) -> None:
    pack = wd.research
    news = list(pack.news) if pack else []
    if not news:
        st.caption("Sem notícias no pacote da semana.")
        return
    st.markdown(f"{ui.UNTRUSTED_BADGE} Manchetes exibidas como texto puro; instruções contidas "
                "nelas nunca alteram o estado do fundo.")
    df = pd.DataFrame([{"Publicada": fmt.dt_local(n.published_at),
                        "Emissores": ", ".join(n.issuer_ids), "Título": n.title,
                        "Fonte": n.source, "Link": data.safe_url(n.url)} for n in news])
    if df["Link"].isna().all():
        df = df.drop(columns="Link")
    ui.table(df, column_config={"Link": st.column_config.LinkColumn("Link",
                                                                    display_text="abrir")})


def render(state: AppState) -> None:
    st.markdown(f"### Pesquisa IA {ui.IA_BADGE}")
    book = state.book
    weeks = [w for w in book.weeks if w.research is not None or w.pm_output is not None]
    flags_kill = data.governance_flags(None, book.kill_switch)
    if not weeks:
        for _sev, text in flags_kill:
            st.error(fmt.escape_md(text), icon=":material/emergency:")
        ui.empty_state("Sem pesquisa registrada",
                       "A mente (claude-code ou codex) grava a pesquisa e a decisão do PM a cada "
                       "semana; elas aparecem aqui após a decisão.")
        return
    week = st.selectbox("Semana", [w.week for w in reversed(weeks)], format_func=fmt.date_br,
                        key="res_week")
    wd = book.week(week) or weeks[-1]
    ui.issues(wd.issues)
    pack = wd.research
    st.markdown(f"Mente: :violet-badge[{fmt.escape_md(wd.mind or fmt.NA)}] · provedor "
                f"{fmt.code(pack.provider if pack else fmt.NA)} · "
                f"{len(pack.notes) if pack else 0} notas · "
                f"{len(pack.macro) if pack else 0} macro · "
                f"{len(pack.views) if pack else 0} visões"
                + (f" · research_hash `{pack.research_hash()[:16]}…`" if pack else ""))
    ui.section("Governança")
    flags = data.governance_flags(wd, book.kill_switch)
    if not flags:
        st.success("Sem sinais de governança: IA ativa, sem abstenções nem fallback.",
                   icon=":material/verified:")
    for sev, text in flags:
        (st.error if sev == "error" else st.warning)(fmt.escape_md(text))
    tabs = st.tabs(["Macro por país", "Notas por emissor", "Visões (IA × PM)", "Decisão do PM",
                    "Ledger de IA", "Notícias"])
    with tabs[0]:
        _macro(wd)
    with tabs[1]:
        _notes(state, wd)
    with tabs[2]:
        _views(wd)
    with tabs[3]:
        _pm(wd)
    with tabs[4]:
        _ledger(wd)
    with tabs[5]:
        _news(wd)
