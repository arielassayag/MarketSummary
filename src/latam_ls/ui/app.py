"""Aplicação multipágina (``st.navigation``) do CDP — Cabra da Peste.

``main()`` monta a navegação; ``run_page(chave)`` renderiza uma página isolada com o mesmo
cabeçalho (usado nos testes com ``streamlit.testing.v1.AppTest``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

from . import components as ui
from . import (
    page_attribution,
    page_audit,
    page_decisions,
    page_overview,
    page_positions,
    page_reports,
    page_research,
    page_risk,
    page_track_record,
)
from .state import AppState

APP_TITLE = "CDP — Cabra da Peste"


@dataclass(frozen=True)
class PageSpec:
    key: str
    title: str
    icon: str
    render: Callable[[AppState], None]


PAGES: tuple[PageSpec, ...] = (
    PageSpec("visao-geral", "Visão geral", ":material/dashboard:", page_overview.render),
    PageSpec("track-record", "Track record diário", ":material/timeline:",
             page_track_record.render),
    PageSpec("atribuicao", "Atribuição de performance", ":material/donut_large:",
             page_attribution.render),
    PageSpec("risco", "Risco", ":material/shield:", page_risk.render),
    PageSpec("posicoes", "Posições", ":material/list_alt:", page_positions.render),
    PageSpec("decisoes", "Decisões semanais", ":material/gavel:", page_decisions.render),
    PageSpec("pesquisa", "Pesquisa IA", ":material/psychology:", page_research.render),
    PageSpec("relatorios", "Relatórios", ":material/description:", page_reports.render),
    PageSpec("auditoria", "Auditoria e mandato", ":material/verified_user:", page_audit.render),
)
PAGES_BY_KEY = {p.key: p for p in PAGES}


def configure() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=":material/monitoring:", layout="wide",
                       initial_sidebar_state="expanded")


def chrome(state: AppState) -> None:
    """Elementos comuns a todas as páginas (estilo, cabeçalho e barra lateral)."""
    ui.inject_css()
    ui.header(state)
    ui.sidebar(state)


def _runner(spec: PageSpec, state: AppState) -> Callable[[], None]:
    def run() -> None:
        spec.render(state)

    run.__name__ = spec.key.replace("-", "_")
    return run


def run_page(key: str) -> None:
    """Renderiza uma única página (sem navegação) — usado pelos testes."""
    configure()
    state = AppState()
    chrome(state)
    PAGES_BY_KEY[key].render(state)


def main() -> None:
    configure()
    state = AppState()
    pages = [st.Page(_runner(spec, state), title=spec.title, icon=spec.icon, url_path=spec.key,
                     default=(i == 0))
             for i, spec in enumerate(PAGES)]
    nav = st.navigation(pages, position="sidebar")
    chrome(state)
    nav.run()
