"""Página 8 — Relatórios diários e semanais publicados (Markdown/HTML), com download."""

from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from . import components as ui
from . import data, fmt
from .state import AppState

_KINDS = {"Todos": None, "Diários": "daily", "Semanais": "weekly"}


def render(state: AppState) -> None:
    st.markdown("### Relatórios")
    reports = state.reports
    if not reports:
        ui.empty_state("Nenhum relatório publicado",
                       "O relatório diário é publicado após o comentário do dia "
                       "(reports/daily/<data>/relatorio.md|html) e o semanal após a decisão "
                       "(reports/weekly/<semana>/).")
        return
    kind = st.segmented_control("Tipo", list(_KINDS), default="Todos", key="rep_kind") or "Todos"
    shown = [r for r in reports if _KINDS[kind] is None or r.kind == _KINDS[kind]]
    if not shown:
        st.info("Nenhum relatório deste tipo.")
        return
    labels = [r.label for r in shown]
    choice = st.selectbox("Relatório", labels, key="rep_choice")
    rep = shown[labels.index(choice)] if choice in labels else shown[0]
    md_text = data.read_text(rep.md)
    html_text = data.read_text(rep.html)
    c = st.columns([1, 1, 3])
    if md_text is not None:
        c[0].download_button("Baixar .md", data=md_text.encode("utf-8"),
                             file_name=f"{rep.kind}_{rep.key.isoformat()}.md",
                             mime="text/markdown", icon=":material/download:", key="rep_dl_md")
    if html_text is not None:
        c[1].download_button("Baixar .html", data=html_text.encode("utf-8"),
                             file_name=f"{rep.kind}_{rep.key.isoformat()}.html",
                             mime="text/html", icon=":material/download:", key="rep_dl_html")
    rel = data.relative_to(rep.folder, state.paths.reports)
    c[2].caption(f"Pasta {fmt.code(rel)} · arquivos imutáveis gerados pelo código (números "
                 "formatados; textos de IA rotulados [IA]).")
    active = data.html_active_content(html_text) if html_text is not None else []
    as_html = html_text is not None and st.toggle("Ver versão HTML (autocontida, sem scripts)",
                                                  key="rep_html")
    if as_html and active:
        st.error("HTML não exibido: o arquivo contém conteúdo ativo ou externo ("
                 + fmt.escape_md(", ".join(active)) + "), o que um relatório gerado pelo código "
                 "nunca tem. Exibindo a versão Markdown.", icon=":material/gpp_bad:")
    with st.container(border=True, height=1100):
        if as_html and html_text is not None and not active:
            components.html(html_text, height=1100, scrolling=True)
        elif md_text is not None:
            st.markdown(fmt.report_md(md_text, demote=1))
        else:
            st.caption("Relatório sem versão Markdown.")
    with st.expander(f"Todos os relatórios ({len(reports)})"):
        ui.table(_index_table(reports))


def _index_table(reports: list[data.ReportInfo]) -> pd.DataFrame:
    return pd.DataFrame([{"Tipo": "Diário" if r.kind == "daily" else "Semanal",
                          "Data": fmt.date_br(r.key),
                          "Markdown": r.md.name if r.md else "—",
                          "HTML": r.html.name if r.html else "—",
                          "Pasta": f"{r.kind}/{r.key.isoformat()}"} for r in reports])
