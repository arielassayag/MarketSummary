"""Componentes visuais compartilhados: cabeçalho, banners, KPIs, selos e estados vazios.

``unsafe_allow_html`` só é usado com HTML/CSS estático do próprio app e números formatados pelo
código; textos externos (notícias, textos de IA, motivos digitados) passam sempre por
:func:`latam_ls.ui.fmt.escape_md` e são exibidos como texto puro.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pandas as pd
import streamlit as st

from . import fmt
from .state import AppState, clear_caches

IA_BADGE = ":violet-badge[:material/smart_toy: IA]"
CALC_BADGE = ":blue-badge[:material/calculate: Calculado]"
UNTRUSTED_BADGE = ":orange-badge[:material/warning: não confiável]"
SIM_BADGE = ":red-badge[DADOS SIMULADOS]"

_CSS = """
<style>
  .block-container {padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1500px;}
  .cdp-header {display:flex; align-items:baseline; justify-content:space-between;
               border-bottom: 3px solid #1D3557; padding-bottom: .45rem; margin-bottom: .6rem;}
  .cdp-title {font-size: 1.75rem; font-weight: 750; color: #1D3557; letter-spacing: .2px;}
  .cdp-sub {color: #4A5568; font-size: .92rem;}
  .cdp-tag {display:inline-block; background:#EEF2F7; color:#1D3557; border-radius: 4px;
            padding: 2px 8px; font-size: .78rem; font-weight: 600; margin-left: 6px;}
  .cdp-banner-sim {background:#B42318; color:#FFF; font-weight:700; letter-spacing:.6px;
                   padding:6px 14px; border-radius:4px; margin:.2rem 0 .6rem 0;
                   font-size:.85rem; text-transform: uppercase;}
  div[data-testid="stMetric"] {background:#FFFFFF;}
  div[data-testid="stMetricValue"] {font-size: 1.45rem;}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def header(state: AppState) -> None:
    """Cabeçalho comum: nome do fundo, natureza do track record e avisos de estado."""
    cfg = state.cfg
    rec = state.track.latest
    week = state.book.live_week(rec)
    mind = week.mind if week is not None else None
    last = fmt.date_br(rec.date) if rec is not None else "antes da inception"
    st.markdown(
        f"<div class='cdp-header'><div><span class='cdp-title'>CDP — Cabra da Peste</span>"
        f"<span class='cdp-tag'>paper trading com preços reais</span>"
        f"<span class='cdp-tag'>Long/short LatAm · USD · net neutral</span></div>"
        f"<div class='cdp-sub'>Último fechamento: {last}</div></div>",
        unsafe_allow_html=True)
    if fmt.escape_md(cfg.fund.name) and cfg.fund.name != "CDP — Cabra da Peste":
        st.caption(f"Mandato carregado: {fmt.escape_md(cfg.fund.name)}")
    if state.synthetic:
        st.markdown("<div class='cdp-banner-sim'>DADOS SIMULADOS — artefatos sintéticos "
                    "carregados (não representam preços reais)</div>", unsafe_allow_html=True)
        st.caption("Sintéticos: " + fmt.escape_md(", ".join(state.synthetic[:6])))
    ks = state.kill_switch
    if ks.active:
        st.error(f"**KILL SWITCH LIGADO** — só operações que reduzem risco. Motivo: "
                 f"{fmt.escape_md(ks.reason) or 'n/d'} · por {fmt.escape_md(ks.by) or 'n/d'} · "
                 f"{fmt.escape_md(ks.created_at) or 'n/d'}", icon=":material/emergency:")
    if not state.config.from_file:
        st.warning("Mandato não carregado do arquivo "
                   f"`{state.paths.config.as_posix()}`: exibindo os padrões do código "
                   f"({fmt.escape_md(state.config.error)}).", icon=":material/warning:")
    st.caption(f"Fundo 100% autônomo: o CDP decide sozinho sob gates determinísticos (sem botão "
               f"de aprovação). Mente da semana: **{fmt.escape_md(mind) or 'n/d'}** · "
               f"vol-alvo {fmt.pct(cfg.risk.vol_target_annual, 0)} (banda "
               f"{fmt.pct(cfg.risk.vol_band_min, 0)}–{fmt.pct(cfg.risk.vol_band_max, 0)}) · "
               f"NAV inicial {fmt.usd_mm(cfg.fund.inception_nav_usd, 0)}.")


def sidebar(state: AppState) -> None:
    cfg = state.cfg
    with st.sidebar:
        st.markdown("**CDP — Cabra da Peste**")
        st.caption(f"{fmt.escape_md(cfg.fund.track_record_type)}")
        ks = state.kill_switch
        if ks.active:
            st.error("KILL SWITCH LIGADO", icon=":material/emergency:")
        else:
            st.success("KILL SWITCH desligado", icon=":material/check_circle:")
        st.caption("Decisão semanal até "
                   f"{fmt.escape_md(cfg.fund.decision_deadline_local)} (Brasília) no primeiro "
                   f"pregão da semana; fechamento diário às "
                   f"{fmt.escape_md(cfg.fund.daily_close_run_local)}.")
        with st.expander("Fontes de dados"):
            for label, path in state.paths.describe():
                st.caption(f"{label}: `{path}`")
            st.caption(f"Mandato (config_hash): `{state.config.config_hash[:16]}…`")
        if st.button("Atualizar dados", icon=":material/refresh:", key="cdp_refresh"):
            clear_caches()
            st.rerun()


def section(title: str, *badges: str, help: str | None = None) -> None:
    st.subheader(" ".join([title, *badges]), help=help, anchor=False)


def empty_state(title: str, body: str) -> None:
    st.info(f"**{title}**\n\n{body}", icon=":material/hourglass_empty:")


def kpi(col: Any, label: str, value: str, status: fmt.Status | str | None = None,
        help: str | None = None) -> None:
    """Indicador com borda; ``status`` colore a linha de referência (verde/laranja/vermelho)."""
    if isinstance(status, fmt.Status):
        col.metric(label, value, delta=status.label, delta_color=status.color,
                   delta_arrow="off", border=True, help=help)
    elif status:
        col.metric(label, value, delta=status, delta_color="gray", delta_arrow="off",
                   border=True, help=help)
    else:
        col.metric(label, value, border=True, help=help)


def plain(text: object, *, prefix: str = "") -> None:
    """Texto externo (IA, notícias, motivos) exibido como texto puro."""
    st.markdown(prefix + fmt.escape_md(text))


def bullet_list(items: Sequence[object], empty: str = "Nenhum.") -> None:
    if not items:
        st.caption(empty)
        return
    st.markdown("\n".join(f"- {fmt.escape_md(x)}" for x in items))


def formatted(df: pd.DataFrame, spec: Mapping[str, Callable[[Any], str]]) -> pd.DataFrame:
    """Cópia do DataFrame com as colunas de ``spec`` formatadas em pt-BR (texto)."""
    out = df.copy()
    for col, f in spec.items():
        if col in out.columns:
            out[col] = [f(v) for v in out[col]]
    return out


def table(df: pd.DataFrame, *, height: int | str = "auto", key: str | None = None,
          column_config: Mapping[str, Any] | None = None) -> None:
    st.dataframe(df, hide_index=True, width="stretch", height=height, key=key,
                 column_config=dict(column_config) if column_config else None)


def checks(results: Sequence[Any]) -> None:
    """Resultado de verificações de integridade (verde/vermelho com mensagens)."""
    for r in results:
        msgs = "\n".join(f"- {fmt.escape_md(m)}" for m in r.messages)
        if r.ok:
            st.success(f"**{r.label}: íntegro**\n\n{msgs}", icon=":material/verified:")
        else:
            st.error(f"**{r.label}: FALHA DE INTEGRIDADE**\n\n{msgs}", icon=":material/error:")


def issues(items: Sequence[str], title: str = "Apontamentos de leitura") -> None:
    if items:
        with st.expander(f"{title} ({len(items)})", icon=":material/report:"):
            bullet_list(items)
