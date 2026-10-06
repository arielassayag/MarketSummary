"""Página "Cobertura de ativos" do app local (Streamlit): o mesmo conteúdo da aba do portal.

Lê o livro da cobertura com :func:`cdp.workflow.painel_cobertura.carregar` e mostra os dados já
exportados (:func:`~cdp.workflow.painel_cobertura.exportar`): resumo, tabela do universo e o
modelo aberto de um ativo (memória de cálculo, insumos com fontes, lacunas e portões). Como no
portal, nenhum número é calculado aqui: os textos chegam formatados do exportador.

Registro no app (fora deste arquivo): ``PageSpec("cobertura", "Cobertura de ativos",
":material/query_stats:", page_cobertura.render)`` em ``cdp/ui/app.py``.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from ..workflow import painel_cobertura as PC
from ..workflow.painel_publicacao import expandir
from . import components as ui
from .state import AppState


@st.cache_data(show_spinner=False)
def _exportar(book: str, fp: str) -> dict[str, Any]:
    ent = PC.carregar(book)
    arqs = PC.exportar(ent, niveis=(PC.Limites(revisoes=10**6, etf_top=10**6, ic_semanas=10**6),))
    return {n: expandir(json.loads(t)) for n, t in arqs.items()}


def _impressao(book: Any) -> str:
    from ..cobertura.livro import datas_snapshots

    return ",".join(d.isoformat() for d in datas_snapshots(book))


def render(state: AppState) -> None:
    from ..cobertura.livro import LivroErro

    st.markdown("### Cobertura de ativos")
    try:
        docs = _exportar(str(state.paths.book), _impressao(state.paths.book))
    except LivroErro:
        ui.empty_state("Cobertura em conferência",
                       "Os modelos da cobertura estão em conferência; a página volta com o próximo retrato conferido.")
        return
    c = docs.get(PC.ARQUIVO) or {}
    meta = c.get("meta") or {}
    if meta.get("estado") != "publicado":
        ui.empty_state("Cobertura ainda não publicada",
                       "A cobertura aparece a partir do primeiro retrato semanal dos modelos de valuation.")
        return
    if meta.get("is_synthetic"):
        st.warning(f"**{meta.get('simulated_label')}** — demonstração com mercado sintético.")
    cols = st.columns(len(c.get("kpis") or []) or 1)
    for col, k in zip(cols, c.get("kpis") or [], strict=False):
        ui.kpi(col, k["label"], k["value"], help=k.get("sub"))
    st.caption(f"{meta.get('data_notice')} {meta.get('aviso_cvm')}")
    uni = pd.DataFrame(c.get("universe") or [])
    if uni.empty:
        return
    ui.section("Tabela de cobertura")
    vis = uni[["nome", "ticker", "pais_nome", "setor_nome", "rating", "preco_texto", "alvo_texto", "upside_texto",
               "etr_texto", "ke_texto", "confianca", "incerteza", "vs_consenso_texto"]].rename(columns={
        "nome": "Ativo", "ticker": "Ticker", "pais_nome": "País", "setor_nome": "Setor", "rating": "Rating",
        "preco_texto": "Preço", "alvo_texto": "Preço-alvo", "upside_texto": "Potencial",
        "etr_texto": "Retorno esperado", "ke_texto": "ke", "confianca": "Confiança", "incerteza": "Incerteza",
        "vs_consenso_texto": "Frente ao consenso"})
    ui.table(vis, height=420, key="cob_tab")
    ui.section("Ficha do ativo", help="Modelo aberto: insumos, fórmulas com os números usados e fontes.")
    nomes = {f"{r['nome']} · {r['ticker']}": r["iid"] for r in c["universe"]}
    escolha = st.selectbox("Ativo", list(nomes), key="cob_ativo")
    iid = nomes.get(escolha)
    linha = next((r for r in c["universe"] if r["iid"] == iid), None)
    if linha is None:
        return
    modelo = (docs.get(f"{PC.PREFIXO_MODELO}{linha['mk']}.json") or {}).get("modelos", {}).get(iid)
    if not modelo:
        st.info("Modelo indisponível nesta publicação.")
        return
    if not modelo.get("citavel"):
        st.warning("Modelo em revisão ou sem preço-alvo: a memória de cálculo é pública para auditoria, mas não "
                   "constitui preço-alvo citável.")
    ui.table(pd.DataFrame(modelo.get("cabecalho") or []).rename(columns={"t": "Item", "v": "Valor"}), key="cob_cab")
    fontes = modelo.get("fontes") or []
    with st.expander(f"Memória de cálculo · {len(modelo.get('passos') or [])} passos"):
        for k, p in enumerate(modelo.get("passos") or [], start=1):
            st.markdown(f"**{k}. {p.get('t')}**")
            if p.get("f"):
                ui.plain(p["f"], prefix="Fórmula: ")
            ui.plain(p.get("s"), prefix="Substituição: " if p.get("f") else "")
            if p.get("p"):
                st.caption(p["p"])
            for i in p.get("fo") or []:
                f = fontes[i]
                st.caption(" · ".join(x for x in (f.get("fonte"), f.get("doc"), f.get("url"),
                                                   f"publicado em {f['pub']}" if f.get("pub") else None) if x))
    with st.expander(f"Insumos e fontes · {len(modelo.get('insumos') or [])}"):
        ui.table(pd.DataFrame(modelo.get("insumos") or []).rename(columns={
            "t": "Insumo", "v": "Valor", "u": "Unidade", "per": "Período", "pub": "Publicação"}).drop(
            columns=["fo", "est"], errors="ignore"), key="cob_ins")
    with st.expander(f"Lacunas e portões de qualidade · {modelo.get('portoes_resumo')}"):
        ui.bullet_list([f"{x.get('t')}: {x.get('m')}" for x in modelo.get("lacunas") or []], empty="Sem lacunas.")
        ui.table(pd.DataFrame(modelo.get("portoes") or []).rename(columns={
            "c": "Portão", "t": "Verificação", "s": "Situação", "d": "Detalhe"}).drop(columns=["tom"], errors="ignore"),
            key="cob_port")


__all__ = ["render"]
