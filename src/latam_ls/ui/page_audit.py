"""Página 9 — Auditoria e mandato: trilha encadeada, integridade, fund.yaml, invariantes e o
KILL SWITCH de emergência (a única ação de escrita do app, auditada)."""

from __future__ import annotations

import streamlit as st

from . import components as ui
from . import data, fmt
from .state import AppState

_FLASH = "cdp_kill_switch_flash"


def _audit(state: AppState) -> None:
    audit = state.audit
    ui.section("Trilha de auditoria", ui.CALC_BADGE,
               help="Eventos append-only encadeados por hash: editar, remover ou reordenar uma "
                    "linha quebra a cadeia.")
    if not audit.exists:
        st.caption(audit.chain_message)
        return
    if audit.error:
        st.error(f"Trilha ilegível: {fmt.escape_md(audit.error)}", icon=":material/error:")
        return
    if audit.chain_ok:
        st.success(f"Cadeia íntegra — {len(audit.events)} evento(s); topo "
                   f"{fmt.code(fmt.short_hash(audit.events[-1].event_hash, 16))}"
                   if audit.events else "Cadeia íntegra (vazia).", icon=":material/link:")
    else:
        st.error(f"Cadeia QUEBRADA: {fmt.escape_md(audit.chain_message)}",
                 icon=":material/link_off:")
    types = sorted({ev.event_type for ev in audit.events})
    sel = st.multiselect("Tipos de evento", types, default=types, key="audit_types")
    events = [ev for ev in audit.events if ev.event_type in sel]
    df = data.audit_frame(list(reversed(events)), state.cfg.fund.timezone)
    ui.table(df, height=min(560, 36 * (len(df) + 1)))
    if st.button("Verificar livro, track record e base de mercado", icon=":material/verified:",
                 key="verify_book", type="primary"):
        results = data.verify_book_integrity(state.paths.book)
        results += data.verify_track_integrity(state.paths.book)
        results.append(data.verify_market_integrity(state.paths.market))
        st.session_state["cdp_book_checks"] = results
    results = st.session_state.get("cdp_book_checks")
    if results:
        ui.checks(results)


def _mandate(state: AppState) -> None:
    info = state.config
    ui.section("Mandato (fund.yaml) — somente leitura")
    st.markdown(f"Arquivo {fmt.code(info.path.as_posix())} · config_hash "
                f"{fmt.code(info.config_hash)}")
    if info.error:
        st.warning(f"Mandato não carregado do arquivo: {fmt.escape_md(info.error)}. Exibindo os "
                   "padrões do código.", icon=":material/warning:")
    latest = state.book.latest
    d = latest.decision if latest is not None else None
    if d is not None:
        if d.config_hash == info.config_hash:
            st.caption(f"Igual ao mandato da última decisão ({fmt.date_br(d.week)}).")
        else:
            st.warning(f"Diferente do mandato da última decisão ({fmt.date_br(d.week)}: "
                       f"{fmt.code(fmt.short_hash(d.config_hash, 16))}): qualquer mudança de "
                       "limite invalida aprovações e vale a partir da próxima decisão.",
                       icon=":material/info:")
    with st.expander("Ver fund.yaml", expanded=False):
        st.code(info.text or "(arquivo ausente)", language="yaml")


def _invariants(state: AppState) -> None:
    ui.section("Invariantes do CDP")
    section, source = data.agents_invariants(state.paths.agents_md)
    if section:
        st.caption(f"Fonte: {fmt.code(source)}")
        with st.container(border=True):
            st.markdown(fmt.report_md(section, demote=2))
    else:
        st.caption(f"Fonte: invariantes do código ({fmt.escape_md(source)}).")
        ui.bullet_list(list(data.CDP_INVARIANTS))


def _kill_switch(state: AppState) -> None:
    ui.section("KILL SWITCH de emergência",
               help="Ligado ⇒ cria book/KILL_SWITCH: a decisão semanal só pode reduzir risco e o "
                    "livro recusa efetivações que aumentem posições. Ligar e desligar gera "
                    "eventos KILL_SWITCH_ON/OFF na trilha de auditoria.")
    flash = st.session_state.pop(_FLASH, None)
    if flash:
        (st.success if flash[0] == "ok" else st.error)(fmt.escape_md(flash[1]))
    ks = state.kill_switch
    if ks.active:
        st.error(f"**LIGADO** desde {fmt.escape_md(ks.created_at) or 'n/d'} por "
                 f"{fmt.escape_md(ks.by) or 'n/d'} — motivo: {fmt.escape_md(ks.reason) or 'n/d'}",
                 icon=":material/emergency:")
        if ks.error:
            st.caption(fmt.escape_md(ks.error))
    else:
        st.success("Desligado: o CDP opera normalmente sob os gates do mandato.",
                   icon=":material/check_circle:")
    turn_on = not ks.active
    with st.form("kill_switch_form", border=True):
        reason = st.text_area("Motivo (obrigatório, mínimo de "
                              f"{data.KILL_SWITCH_MIN_REASON} caracteres)", key="ks_reason")
        by = st.text_input("Responsável", key="ks_by")
        confirmed = st.checkbox("Confirmo que quero "
                                + ("LIGAR o kill switch (somente redução de risco)" if turn_on
                                   else "DESLIGAR o kill switch"), key="ks_confirm")
        submitted = st.form_submit_button("Ligar KILL SWITCH" if turn_on
                                          else "Desligar KILL SWITCH",
                                          type="primary", key="ks_submit",
                                          icon=":material/emergency:" if turn_on
                                          else ":material/power_settings_new:")
    if not submitted:
        return
    problems = data.validate_kill_switch_request(turn_on, reason or "", by or "", confirmed,
                                                 ks.active)
    if problems:
        st.error("Ação não executada:\n\n" + "\n".join(f"- {fmt.escape_md(p)}" for p in problems))
        return
    try:
        data.set_kill_switch(state.paths, state.cfg, turn_on, reason or "", by or "")
    except Exception as exc:  # noqa: BLE001 - erro de disco/permissão é exibido ao operador
        st.error(f"Falha ao gravar o kill switch: {fmt.escape_md(type(exc).__name__)}: "
                 f"{fmt.escape_md(exc)}")
        return
    st.session_state[_FLASH] = ("ok", "Kill switch " + ("LIGADO" if turn_on else "DESLIGADO")
                                + " e registrado na trilha de auditoria.")
    st.rerun()


def render(state: AppState) -> None:
    st.markdown("### Auditoria e mandato")
    _audit(state)
    left, right = st.columns(2)
    with left:
        _mandate(state)
        _invariants(state)
    with right:
        _kill_switch(state)
