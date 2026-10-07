"""CVM dados abertos: demonstrações completas (DFP/ITR), free float (FRE) e eventos (IPE).

Fontes (``https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/``):

- ``DFP``/``ITR``: ``{doc}_cia_aberta_{ano}.zip`` com o índice (``DT_RECEB``, ``VERSAO``,
  ``LINK_DOC``) e as demonstrações ``DRE``, ``BPA``, ``BPP``, ``DFC_MD``/``DFC_MI``, ``DVA``
  (consolidado ``con`` com recurso ao individual ``ind``) e ``composicao_capital``.
- ``FRE``: ``fre_cia_aberta_{ano}.zip`` → ``distribuicao_capital`` (ações em circulação).
- ``IPE``: ``ipe_cia_aberta_{ano}.zip`` → assembleias, fatos relevantes e o documento
  "Calendário de Eventos Corporativos" (PDF padronizado lido por :mod:`.publico_pdf`).

Mapeamento para os itens canônicos (``publico.CANONICAL_ITEMS``), por descrição normalizada e
código de conta (válido nos layouts comercial, bancário e de seguradoras de 2017–2026):

========================  =========================================================================
item                      regra
========================  =========================================================================
receita                   DRE ``3.01``
lucro_bruto               DRE nível 1 "Resultado Bruto" (não financeiras)
ebit                      DRE nível 1 "Resultado Antes do Resultado Financeiro e dos Tributos"
resultado_financeiro      DRE nível 1 "Resultado Financeiro" (com sinal; negativo = despesa líquida)
lucro_antes_ir            DRE nível 1 "Resultado Antes dos Tributos sobre o Lucro"
ir_csll                   DRE nível 1 "Imposto de Renda e Contribuição Social" (negativo = despesa)
lucro_liquido             DRE nível 1 "Lucro/Prejuízo Consolidado do Período"
lucro_liquido_controladores  filha "Atribuído a Sócios da Empresa Controladora" (zero reservado ⇒
                          lucro consolidado − não controladores; sem a irmã ⇒ ausente)
d_a                       DVA ``7.04.01`` (módulo); na falta, soma das linhas de depreciação,
                          amortização e exaustão da DFC indireta (``6.01.01.xx``)
cfo                       DFC ``6.01``
capex                     −Σ aquisições de imobilizado, intangível, ativo de contrato de concessão,
                          ativo biológico (plantio e tratos) e infraestrutura em ``6.02.xx``
                          (valor positivo); alerta de conferência quando o capex é < 20% das
                          saídas de investimento e uma linha operacional não classificada domina
dividendos_pagos          −Σ dividendos e JCP pagos aos acionistas da companhia em ``6.03.xx``
                          (nunca uma linha já classificada como recompra)
recompras                 −Σ aquisições de ações em tesouraria/recompras em ``6.03.xx`` (exclui
                          amortização/recompra de dívida, cessão de recebíveis e minoritários)
caixa / aplicacoes_cp     BPA ``1.01.01`` / ``1.01.02`` (não financeiras)
ativo_total               BPA ``1``
divida_bruta              BPP ``2.01.04 + 2.02.01`` (empréstimos, financiamentos e debêntures),
                          excluídas as subcontas de arrendamento; exige as duas contas
arrendamentos             Σ contas de passivo de arrendamento (sem dupla contagem pai/filha)
patrimonio_liquido        BPP nível 1 "Patrimônio Líquido (Consolidado)"
participacao_minoritarios filha "Participação dos Acionistas Não Controladores"
patrimonio_controladores  filha do controlador; senão PL − não controladores; senão PL
acoes_*                   ``composicao_capital`` (unidade conferida pelo LPA e pelo PL/ação)
carteira_credito          BPA "Operações de Crédito" (financeiras)
provisao_credito          BPA provisões para perdas de crédito (módulo; financeiras)
despesa_pdd               DRE perdas de crédito esperadas/PDD (negativo = despesa; financeiras)
margem_financeira         DRE "Resultado Bruto da Intermediação Financeira" antes das perdas de
                          crédito (as linhas de perda dentro de ``3.02`` são somadas de volta)
receita_servicos          DRE receitas de prestação de serviços e tarifas (financeiras)
========================  =========================================================================

Valores em unidades da moeda (``ESCALA_MOEDA`` aplicada; ``escala = 1``). Ausência de conta ⇒
item ausente (nunca zero); contas duplicadas divergentes ⇒ ausente (regra herdada de
:mod:`.fundamentals_pit`).
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from collections.abc import Iterable
from datetime import date

import numpy as np
import pandas as pd

from .fundamentals_pit import (
    _capital_facts,
    _financial_docs,
    _flag_financial,
    _implied_shares,
    _prepare_statement,
)
from .security_master import CVM_DOC_BASE_URL, normalize_text, read_cvm_csv

logger = logging.getLogger(__name__)

PARSER_CVM = "publico-cvm-1"
TABELAS = ("DRE", "BPA", "BPP", "DFC_MD", "DFC_MI", "DVA")
_COLS_FLUXO = ["CNPJ_CIA", "DT_REFER", "VERSAO", "MOEDA", "ESCALA_MOEDA", "ORDEM_EXERC",
               "DT_INI_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA"]
_COLS_SALDO = ["CNPJ_CIA", "DT_REFER", "VERSAO", "MOEDA", "ESCALA_MOEDA", "ORDEM_EXERC",
               "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA"]
USECOLS = {"DRE": _COLS_FLUXO, "DFC_MD": _COLS_FLUXO, "DFC_MI": _COLS_FLUXO,
           "DVA": _COLS_FLUXO, "BPA": _COLS_SALDO, "BPP": _COLS_SALDO}

FATO_COLUNAS = [
    "entidade", "demonstrativo", "item", "period_start", "period_end", "value", "currency",
    "received_date", "version", "documento", "url", "consolidado", "anual",
]


def url_zip(doc: str, ano: int) -> str:
    doc = doc.upper()
    return f"{CVM_DOC_BASE_URL}/{doc}/DADOS/{doc.lower()}_cia_aberta_{int(ano)}.zip"


def validar_zip(conteudo: bytes) -> None:
    if not zipfile.is_zipfile(io.BytesIO(conteudo)):
        raise ValueError("Resposta da CVM não é um ZIP válido.")


def _membro(nomes: list[str], sufixo: str) -> str | None:
    s = sufixo.lower()
    return next((n for n in nomes if n.lower().endswith(s)), None)


# ======================================================================
# Leitura dos ZIPs DFP/ITR
# ======================================================================

def ler_zip_demonstracoes(conteudo: bytes, doc: str, ano: int,
                          cnpjs: Iterable[str] | None = None) -> dict[str, pd.DataFrame]:
    """Tabelas brutas (texto) do ZIP DFP/ITR, só ``ORDEM_EXERC = ÚLTIMO`` e os ``cnpjs``.

    Chaves: ``index``, ``<TAB>_con``/``<TAB>_ind`` para ``TABELAS`` e ``capital``.
    """
    alvo = None if cnpjs is None else {str(c).strip() for c in cnpjs}
    pref = f"{doc.lower()}_cia_aberta_"
    out: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        nomes = zf.namelist()
        n_idx = _membro(nomes, f"{pref}{ano}.csv")
        idx = (read_cvm_csv(zf.read(n_idx)) if n_idx
               else pd.DataFrame(columns=["CNPJ_CIA", "DT_REFER", "VERSAO", "DT_RECEB",
                                          "LINK_DOC"]))
        if alvo is not None:
            idx = idx[idx["CNPJ_CIA"].astype(str).str.strip().isin(alvo)]
        out["index"] = idx.reset_index(drop=True)
        for tab in TABELAS:
            cols = USECOLS[tab]
            for kind in ("con", "ind"):
                nome = _membro(nomes, f"{pref}{tab}_{kind}_{ano}.csv")
                if nome is None:
                    out[f"{tab}_{kind}"] = pd.DataFrame(columns=cols)
                    continue
                df = read_cvm_csv(zf.read(nome), usecols=lambda c, cols=cols: c in cols)
                for c in cols:
                    if c not in df.columns:
                        df[c] = pd.NA
                if alvo is not None:
                    df = df[df["CNPJ_CIA"].astype(str).str.strip().isin(alvo)]
                ordem = df["ORDEM_EXERC"].fillna("").map(normalize_text)
                out[f"{tab}_{kind}"] = df.loc[ordem == "ultimo", cols].reset_index(drop=True)
        n_cap = _membro(nomes, f"{pref}composicao_capital_{ano}.csv")
        cap = (read_cvm_csv(zf.read(n_cap)) if n_cap
               else pd.DataFrame(columns=["CNPJ_CIA", "DT_REFER", "VERSAO"]))
        if alvo is not None and not cap.empty:
            cap = cap[cap["CNPJ_CIA"].astype(str).str.strip().isin(alvo)]
        out["capital"] = cap.reset_index(drop=True)
    return out


# ======================================================================
# Extração dos itens canônicos
# ======================================================================

_K_FLUXO = ["cnpj", "dt_refer", "versao", "kind", "dt_ini", "dt_fim"]
_K_SALDO = ["cnpj", "dt_refer", "versao", "kind", "dt_fim"]


def _nivel(st: pd.DataFrame) -> pd.DataFrame:
    st = st.copy()
    st["level"] = st["cd"].str.count(r"\.")
    return st


def _primeira(df: pd.DataFrame, key: list[str], ordem: list[str] | None = None) -> pd.DataFrame:
    ordem = ordem or ["cd"]
    return df.sort_values(key + ordem, kind="stable").drop_duplicates(key, keep="first")


def _soma(df: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    if df.empty:
        return df.iloc[0:0][key + ["value", "currency"]]
    return (df.groupby(key, as_index=False, dropna=False)
            .agg(value=("value", "sum"), currency=("currency", "first")))


def _sem_ancestral(df: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """Remove linhas cuja conta-mãe (prefixo do código) também está no conjunto."""
    if df.empty:
        return df
    keep = []
    for _, g in df.groupby(key, sort=False, dropna=False):
        cds = set(g["cd"])
        for i, cd in zip(g.index, g["cd"], strict=True):
            partes = cd.split(".")
            if any(".".join(partes[:k]) in cds for k in range(1, len(partes))):
                continue
            keep.append(i)
    return df.loc[sorted(keep)]


def _item(df: pd.DataFrame, item: str, demonstrativo: str, key: list[str]) -> pd.DataFrame:
    cols = key + ["value", "currency"]
    out = df[cols].copy() if not df.empty else pd.DataFrame(columns=cols)
    out["item"] = item
    out["demonstrativo"] = demonstrativo
    return out


_RE_NI = (r"lucro|resultado liquido|prejuizo", r"periodo|exercicio",
          r"antes|continuad|por acao|participac")
_RE_PDD = r"(?:perda|provisao|provisoes).*(?:credito|esperada)|credito.*esperada|liquidacao duvidosa"


def _itens_dre(dre: pd.DataFrame, fin: pd.DataFrame) -> list[pd.DataFrame]:
    if dre.empty:
        return []
    d = _nivel(dre.dropna(subset=["dt_ini"]))
    d["financial"] = _flag_financial(d, fin)
    K = _K_FLUXO
    l1 = d[d["level"] == 1]
    receita = _primeira(d[d["cd"] == "3.01"], K)
    out = [_receita_reportada(d, receita, K)]
    nf1 = l1[~l1["financial"]]
    out.append(_item(_primeira(nf1[nf1["ds"].str.contains("resultado bruto")], K),
                     "lucro_bruto", "DRE", K))
    out.append(_item(_primeira(nf1[nf1["ds"].str.contains(
        "antes do resultado financeiro e dos tributos")], K), "ebit", "DRE", K))
    out.append(_item(_primeira(nf1[nf1["ds"].str.match(r"^resultado financeiro")], K),
                     "resultado_financeiro", "DRE", K))
    pre = l1[l1["ds"].str.contains(r"antes dos tributos|antes do imposto|antes dos impostos")
             & ~l1["ds"].str.contains("resultado financeiro")]
    out.append(_item(_primeira(pre, K), "lucro_antes_ir", "DRE", K))
    out.append(_item(_primeira(l1[l1["ds"].str.contains("imposto de renda")], K),
                     "ir_csll", "DRE", K))
    ni_mask = (l1["ds"].str.contains(_RE_NI[0]) & l1["ds"].str.contains(_RE_NI[1])
               & ~l1["ds"].str.contains(_RE_NI[2]))
    ni = _primeira(l1[ni_mask], K)
    out.append(_item(ni, "lucro_liquido", "DRE", K))
    filhas = d[(d["level"] == 2) & d["ds"].str.contains("controlador")
               & ~d["ds"].str.contains(r"nao controlador|nao-controlador")].copy()
    filhas["parent"] = filhas["cd"].str.rsplit(".", n=1).str[0]
    ctrl = ni[K + ["cd", "value"]].rename(columns={"value": "v_ni"}).merge(
        filhas[K + ["parent", "value", "currency"]], left_on=K + ["cd"],
        right_on=K + ["parent"], how="inner")
    ctrl = _primeira(ctrl, K, ["parent"])
    # 0 exato ao lado de lucro consolidado não nulo = espaço reservado do formulário: vale
    # lucro consolidado − não controladores (irmã "não controladores" no mesmo documento);
    # sem a irmã, o item fica ausente (nunca o lucro consolidado, que inclui os minoritários)
    nci = d[(d["level"] == 2) & d["ds"].str.contains(r"nao controlador|nao-controlador")].copy()
    nci["parent"] = nci["cd"].str.rsplit(".", n=1).str[0]
    nci = _primeira(nci, K + ["parent"]).rename(columns={"value": "v_nci"})
    ctrl = ctrl.merge(nci[K + ["parent", "v_nci"]], on=K + ["parent"], how="left")
    placeholder = (ctrl["value"] == 0) & (ctrl["v_ni"] != 0)
    ctrl["value"] = np.where(placeholder, ctrl["v_ni"] - ctrl["v_nci"], ctrl["value"])
    ctrl = ctrl[ctrl["value"].notna()]
    out.append(_item(ctrl, "lucro_liquido_controladores", "DRE", K))
    # financeiras
    fd = d[d["financial"]]
    if not fd.empty:
        l2 = fd[fd["level"] == 2]
        pdd = l2[l2["cd"].str.match(r"^3\.0[2-4]\.") & l2["ds"].str.contains(_RE_PDD)]
        out.append(_item(_soma(pdd, K), "despesa_pdd", "DRE", K))
        rep = _primeira(fd[(fd["level"] == 1) & fd["ds"].str.contains("resultado bruto")], K)
        pdd_302 = _soma(pdd[pdd["cd"].str.startswith("3.02.")], K).rename(
            columns={"value": "v_pdd302"})
        tem_pdd = pdd[K].drop_duplicates().assign(_tem=True)
        mg = rep.merge(pdd_302[K + ["v_pdd302"]], on=K, how="left").merge(tem_pdd, on=K,
                                                                          how="left")
        mg = mg[mg["_tem"].fillna(False).astype(bool)]
        mg["value"] = mg["value"] - mg["v_pdd302"].fillna(0.0)
        out.append(_item(mg, "margem_financeira", "DRE", K))
        serv = l2[l2["ds"].str.contains(r"prestacao de servicos|tarifas")].copy()
        if not serv.empty:
            serv["_abs"] = -serv["value"].abs()
            serv = serv.sort_values(K + ["_abs", "cd"]).drop_duplicates(K, keep="first")
            out.append(_item(serv, "receita_servicos", "DRE", K))
    return out


def _receita_reportada(d: pd.DataFrame, receita: pd.DataFrame,
                       key: list[str]) -> pd.DataFrame:
    """Preserva 3.01; identifica resultado líquido de seguros pela composição publicada.

    O código CVM da conta não prova comparabilidade. Receita de seguros menos despesa de
    seguros dentro da própria 3.01, conciliada ao subtotal, é resultado líquido, não vendas.
    Não remapeia a receita de seguros filha nem identifica um emissor pelo nome/ano.
    """
    out = _item(receita, "receita", "DRE", key)
    out["semantica_fluxo"] = "receita_dre"
    out["rubrica_reportada"] = (receita.get("rubrica_reportada", receita["ds"])
                               .reindex(out.index).map(lambda s: f"3.01: {s}"))
    if receita.empty:
        return out
    filhas = d[d["cd"].str.match(r"^3\.01\.\d+$")]
    for idx, row in receita.iterrows():
        filhos = filhas
        for k in key:
            filhos = filhos[filhos[k].eq(row[k])]
        seguro = filhos["ds"].str.contains(r"(?:seguro|resseguro)", regex=True)
        ingresos = seguro & filhos["ds"].str.contains(r"receit|ingress") & filhos["value"].gt(0)
        despesas = seguro & filhos["ds"].str.contains(r"despes|custo|gasto") & filhos["value"].lt(0)
        if not (ingresos.any() and despesas.any()):
            continue
        # As filhas diretas publicadas precisam explicar o subtotal; não pressupõe sinal.
        conciliado = np.isclose(float(filhos["value"].sum()), float(row["value"]),
                               rtol=1e-10, atol=1e-6)
        out.at[idx, "semantica_fluxo"] = ("resultado_liquido_seguros" if conciliado
                                          else "seguros_composicao_nao_conciliada")
    return out


def _rubricas_dre(dre: pd.DataFrame, tabelas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Descrição literal da fonte, alinhada à linha que o preparador selecionou."""
    rubricas = []
    for kind in ("con", "ind"):
        raw = tabelas.get(f"DRE_{kind}")
        if raw is None or raw.empty:
            continue
        rubricas.append(pd.DataFrame({
            "cnpj": raw["CNPJ_CIA"].astype(str).str.strip(),
            "dt_refer": pd.to_datetime(raw["DT_REFER"], errors="coerce"),
            "versao": pd.to_numeric(raw["VERSAO"], errors="coerce"), "kind": kind,
            "dt_ini": pd.to_datetime(raw["DT_INI_EXERC"], errors="coerce"),
            "dt_fim": pd.to_datetime(raw["DT_FIM_EXERC"], errors="coerce"),
            "cd": raw["CD_CONTA"].astype(str).str.strip(),
            "rubrica_reportada": raw["DS_CONTA"],
        }))
    if dre.empty or not rubricas:
        return dre
    key = _K_FLUXO + ["cd"]
    labels = pd.concat(rubricas, ignore_index=True).drop_duplicates(key, keep="last")
    return dre.merge(labels, on=key, how="left", validate="many_to_one")


_RE_CAPEX_VERBO = (r"^\(?(?:aquisi|adic|compra|investiment|aplicac|pagamento|gastos|desembolso|"
                   r"acrescimo|aumento|plantac|formacao)")
_RE_VENDA = r"venda|alienac|baixa|receb|distrato|resgate"
# Investimento em ativos operacionais: imobilizado e intangível, mas também o ativo de contrato
# das concessões (IFRS 15/ICPC 01: transmissão, distribuição, saneamento, gás), o ativo
# biológico (florestas, lavouras: plantio e tratos) e a infraestrutura em construção. Sem isso o
# capex de concessionárias e de papel/celulose/açúcar sai subestimado e o FCF superestimado.
_RE_CAPEX = (r"imobili?z|intangi|propriedades? para investimento|ativo nao circulante|"
             r"ativos? fixos?|ativos? (?:de|do|no|em) contratos?|ativos? contratua(?:l|is)|"
             r"ativos? da concessao|infraestrutura|ativos? biologicos?|plantio|tratos culturais|"
             r"lavoura|madeira em pe|linhas de transmissao|manutencao capitalizada")
_RE_CAPEX_FORA = r"titulos|valores mobiliarios|fundos?\b|aplicacoes financeiras|participac"
_RE_RECOMPRA = r"tesouraria|recompra de acoes|acoes propria|aquisicao de acoes|recompra"
_RE_RECOMPRA_FORA = (r"debentur|alienac|venda|entrega|recebid|receb|dividend|emprestim|"
                     r"financiament|divida|cessao|notes|bonds?\b|titulos|minoritari|"
                     r"controlad")
_RE_DIVIDENDO = (r"dividend|juros sobre (?:o )?capital|jcp|jscp|proventos|"
                 r"remuneracao aos acionistas|pagamentos? aos acionistas")
_RE_DIVIDENDO_FORA = r"recebid|nao controlador|minoritari|scps?\b|spes?\b"
# QA do capex: saídas de investimento tipicamente não operacionais (aplicações, M&A)
_RE_INV_FINANCEIRO = (r"aplica|titulo|valores mobiliarios|financeir|resgate|caixa restrito|"
                      r"investimento|controlad|coligad|combinacao|aquisicao de empresa|"
                      r"participac|mutuo|emprestim|partes relacionadas|debentur|derivativ|"
                      r"negocio|joint|tvm|vinculad|deposito|aporte|capital")
LIMITE_QA_CAPEX = 0.20


def _qa_capex(inv_all: pd.DataFrame, capex: pd.DataFrame, K: list[str]) -> list[dict]:
    """Capex < 20% das saídas de investimento (6.02) com uma única linha operacional não
    classificada dominando as saídas ⇒ alerta para conferência do mapa de contas."""
    if inv_all.empty:
        return []
    out = []
    saidas = inv_all[inv_all["value"] < 0]
    cap = capex.set_index(K)["value"] if not capex.empty else pd.Series(dtype=float)
    for key, g in saidas.groupby(K, dropna=False):
        total = -float(g["value"].sum())
        if total <= 0:
            continue
        cx = float(cap.get(key, 0.0)) if not cap.empty and key in cap.index else 0.0
        if cx >= LIMITE_QA_CAPEX * total:
            continue
        resto = g[~g["_capex"] & ~g["ds"].str.contains(_RE_INV_FINANCEIRO)]
        if resto.empty:
            continue
        maior = resto.loc[resto["value"].idxmin()]
        if -float(maior["value"]) < 0.5 * total:
            continue
        out.append({"cnpj": key[0], "dt_refer": key[1], "versao": key[2],
                    "msg": (f"capex {cx:,.0f} é {cx / total:.0%} das saídas de investimento; "
                            f"maior saída não classificada: '{maior['ds']}' "
                            f"{-float(maior['value']):,.0f}")})
    return out


def _itens_dfc(dfc: pd.DataFrame) -> tuple[list[pd.DataFrame], list[dict]]:
    if dfc.empty:
        return [], []
    d = dfc.dropna(subset=["dt_ini"])
    K = _K_FLUXO
    out = [_item(_primeira(d[d["cd"] == "6.01"], K), "cfo", "DFC", K)]
    inv_all = d[d["cd"].str.match(r"^6\.02\.\d{2}$")].copy()
    eh_capex = (inv_all["ds"].str.contains(_RE_CAPEX) & ~inv_all["ds"].str.contains(_RE_CAPEX_FORA)
                & (inv_all["value"] <= 0))
    eh_capex &= (inv_all["ds"].str.match(_RE_CAPEX_VERBO)
                 | ~inv_all["ds"].str.contains(_RE_VENDA))
    inv_all["_capex"] = eh_capex
    capex = _soma(inv_all[eh_capex], K)
    capex["value"] = -capex["value"]
    out.append(_item(capex, "capex", "DFC", K))
    qa = _qa_capex(inv_all, capex, K)
    fin = d[d["cd"].str.match(r"^6\.03\.\d{2}$") & (d["value"] <= 0)]
    # recompras e dividendos mutuamente exclusivos: "proventos/(recompra) de ações" (= emissão
    # líquida de recompras) é recompra, nunca dividendo; amortização/recompra de dívida,
    # cessão de recebíveis e participação de minoritários não são recompra de ações próprias
    eh_rec = (fin["ds"].str.contains(_RE_RECOMPRA) & ~fin["ds"].str.contains(_RE_RECOMPRA_FORA))
    rec = _soma(fin[eh_rec], K)
    rec["value"] = -rec["value"]
    div = fin[~eh_rec & fin["ds"].str.contains(_RE_DIVIDENDO)
              & ~fin["ds"].str.contains(_RE_DIVIDENDO_FORA)]
    div = _soma(div, K)
    div["value"] = -div["value"]
    out.append(_item(div, "dividendos_pagos", "DFC", K))
    out.append(_item(rec, "recompras", "DFC", K))
    da = d[d["cd"].str.match(r"^6\.01\.01\.\d{2}$") & d["ds"].str.contains(
        r"deprec|amortiz|exaust") & ~d["ds"].str.contains(
        r"custo|agio|mais.valia|antecipad|juros|emprestim|debentur|financiament|captacao|"
        r"transacao|premio")]
    da = _soma(da, K)
    da["value"] = da["value"].abs()
    out.append(_item(da, "d_a_dfc", "DFC", K))
    return out, qa


def _itens_dva(dva: pd.DataFrame) -> list[pd.DataFrame]:
    if dva.empty:
        return []
    d = _nivel(dva.dropna(subset=["dt_ini"]))
    K = _K_FLUXO
    da = d[(d["cd"] == "7.04.01") | ((d["level"] == 2) & d["cd"].str.startswith("7.04.")
                                     & d["ds"].str.contains(r"deprec|amortiz|exaust"))]
    da = _primeira(da, K).copy()
    da["value"] = da["value"].abs()
    return [_item(da, "d_a", "DVA", K)]


def _itens_bpa(bpa: pd.DataFrame, fin: pd.DataFrame) -> list[pd.DataFrame]:
    if bpa.empty:
        return []
    d = _nivel(bpa)
    d["financial"] = _flag_financial(d, fin)
    K = _K_SALDO
    out = [_item(_primeira(d[d["cd"] == "1"], K), "ativo_total", "BP", K)]
    nf = d[~d["financial"]]
    out.append(_item(_primeira(nf[(nf["cd"] == "1.01.01") & nf["ds"].str.contains("caixa")], K),
                     "caixa", "BP", K))
    out.append(_item(_primeira(nf[(nf["cd"] == "1.01.02") & nf["ds"].str.contains("aplica")],
                               K), "aplicacoes_cp", "BP", K))
    fd = d[d["financial"]]
    if not fd.empty:
        cart = fd[fd["ds"].str.match(r"^operacoes de credito") & (fd["value"] > 0)]
        out.append(_item(_primeira(cart, K, ["level", "cd"]), "carteira_credito", "BP", K))
        prov = fd[fd["cd"].str.startswith("1.") & fd["ds"].str.contains(
            r"provisao para (?:perda|credito)|perdas? (?:de credito )?esperada|liquidacao duvidosa")]
        prov = _soma(_sem_ancestral(prov, K), K)
        prov["value"] = prov["value"].abs()
        out.append(_item(prov, "provisao_credito", "BP", K))
    return out


def _itens_bpp(bpp: pd.DataFrame, fin: pd.DataFrame) -> list[pd.DataFrame]:
    if bpp.empty:
        return []
    d = _nivel(bpp)
    d["financial"] = _flag_financial(d, fin)
    K = _K_SALDO
    out = []
    eq = d[(d["level"] == 1) & d["ds"].str.contains("patrimonio liquido")].copy()
    eq["_cons"] = -eq["ds"].str.contains("consolidado").astype(int)
    eq = _primeira(eq, K, ["_cons", "cd"])
    out.append(_item(eq, "patrimonio_liquido", "BP", K))
    ch = d[d["level"] == 2].copy()
    ch["parent"] = ch["cd"].str.rsplit(".", n=1).str[0]
    ch = ch.merge(eq[K + ["cd"]].rename(columns={"cd": "parent"}), on=K + ["parent"])
    nci_mask = ch["ds"].str.contains(r"nao controlador|nao-controlador")
    nci = _primeira(ch[nci_mask], K)
    out.append(_item(nci, "participacao_minoritarios", "BP", K))
    ctrl = _primeira(ch[ch["ds"].str.contains("controlador") & ~nci_mask], K)
    pc = eq[K + ["value", "currency"]].merge(
        ctrl[K + ["value"]].rename(columns={"value": "v_ctrl"}), on=K, how="left").merge(
        nci[K + ["value"]].rename(columns={"value": "v_nci"}), on=K, how="left")
    pc["value"] = np.where(pc["v_ctrl"].notna(), pc["v_ctrl"],
                           np.where(pc["v_nci"].notna(), pc["value"] - pc["v_nci"], pc["value"]))
    out.append(_item(pc, "patrimonio_controladores", "BP", K))
    nf = d[~d["financial"]]
    if not nf.empty:
        div = nf[nf["cd"].isin(["2.01.04", "2.02.01"]) & nf["ds"].str.contains("emprestim")]
        div = _primeira(div, K + ["cd"], [])
        divg = (div.groupby(K, as_index=False, dropna=False)
                .agg(value=("value", "sum"), currency=("currency", "first"), n=("cd", "nunique")))
        divg = divg[divg["n"] == 2].drop(columns="n")
        arr_fil = nf[nf["cd"].str.match(r"^2\.0(1\.04|2\.01)\.\d{2}$")
                     & nf["ds"].str.contains("arrendamento")]
        arr_fil = _soma(arr_fil, K).rename(columns={"value": "v_arr"})
        divg = divg.merge(arr_fil[K + ["v_arr"]], on=K, how="left")
        divg["value"] = divg["value"] - divg["v_arr"].fillna(0.0)
        out.append(_item(divg, "divida_bruta", "BP", K))
        arr = nf[nf["cd"].str.match(r"^2\.0[12]\.") & (nf["level"] >= 2)
                 & nf["ds"].str.contains("arrendamento")
                 & ~nf["ds"].str.contains(r"a receber|ativo")]
        arr = _soma(_sem_ancestral(arr, K), K)
        out.append(_item(arr, "arrendamentos", "BP", K))
    return out


def _itens_capital(capital: pd.DataFrame, dre: pd.DataFrame, eq_doc: pd.DataFrame,
                   ni_flows: pd.DataFrame) -> pd.DataFrame:
    cols = ["cnpj", "dt_refer", "versao", "item", "value"]
    need = {"CNPJ_CIA", "DT_REFER", "VERSAO", "QT_ACAO_TOTAL_CAP_INTEGR", "QT_ACAO_TOTAL_TESOURO"}
    if capital is None or capital.empty or not need <= set(capital.columns):
        return pd.DataFrame(columns=cols)
    corr = _capital_facts(capital, _implied_shares(dre, ni_flows), eq_doc)
    if corr.empty:
        return pd.DataFrame(columns=cols)
    raw = pd.DataFrame({
        "cnpj": capital["CNPJ_CIA"].astype(str).str.strip(),
        "dt_refer": pd.to_datetime(capital["DT_REFER"], errors="coerce"),
        "versao": pd.to_numeric(capital["VERSAO"], errors="coerce"),
        "total": pd.to_numeric(capital["QT_ACAO_TOTAL_CAP_INTEGR"], errors="coerce"),
        "tes": pd.to_numeric(capital["QT_ACAO_TOTAL_TESOURO"], errors="coerce"),
    }).dropna(subset=["dt_refer", "versao"])
    raw["versao"] = raw["versao"].astype(int)
    m = corr.merge(raw, on=["cnpj", "dt_refer", "versao"], how="inner")
    m = m[(m["total"] - m["tes"]) > 0]
    fator = m["value"] / (m["total"] - m["tes"])
    linhas = []
    for item, v in (("acoes_em_circulacao", m["value"]), ("acoes_emitidas", m["total"] * fator),
                    ("acoes_tesouraria", m["tes"] * fator)):
        linhas.append(pd.DataFrame({"cnpj": m["cnpj"], "dt_refer": m["dt_refer"],
                                    "versao": m["versao"], "item": item, "value": v,
                                    "unidade": m["scale_check"]}))
    out = pd.concat(linhas, ignore_index=True)
    return out[cols + ["unidade"]]


def _preferir_dva(f: pd.DataFrame) -> pd.DataFrame:
    """D&A da DVA quando existe; senão a soma das linhas da DFC indireta (mesmo período)."""
    k = ["cnpj", "dt_refer", "versao", "dt_ini", "dt_fim"]
    dva = f[f["item"] == "d_a"][k].drop_duplicates().assign(_tem=True)
    dfc = f[f["item"] == "d_a_dfc"].merge(dva, on=k, how="left")
    usar = dfc[dfc["_tem"].isna()].drop(columns="_tem").assign(item="d_a")
    resto = f[f["item"] != "d_a_dfc"]
    return pd.concat([resto, usar], ignore_index=True)


def fatos_cvm(tabelas: dict[str, pd.DataFrame], doc: str) -> pd.DataFrame:
    """Fatos canônicos (``FATO_COLUNAS``) de um ZIP DFP/ITR já lido.

    ``received_date`` = ``DT_RECEB`` da versão do documento; ``url`` = ``LINK_DOC`` (documento
    no sistema da CVM). Linhas sem data de recebimento conhecida são descartadas.
    """
    doc_u = doc.upper()
    idx = tabelas.get("index", pd.DataFrame())
    if idx is None or idx.empty:
        return _com_qa(pd.DataFrame(columns=FATO_COLUNAS), [], doc_u)
    rec = pd.DataFrame({
        "cnpj": idx["CNPJ_CIA"].astype(str).str.strip(),
        "dt_refer": pd.to_datetime(idx["DT_REFER"], errors="coerce"),
        "versao": pd.to_numeric(idx["VERSAO"], errors="coerce"),
        "received_date": pd.to_datetime(idx["DT_RECEB"], errors="coerce"),
        "url": idx["LINK_DOC"].astype(str) if "LINK_DOC" in idx.columns else None,
    }).dropna(subset=["dt_refer", "versao", "received_date"])
    rec["versao"] = rec["versao"].astype(int)
    rec = rec.sort_values("received_date").drop_duplicates(["cnpj", "dt_refer", "versao"])
    dre = _rubricas_dre(_prepare_statement(tabelas, "DRE"), tabelas)
    bpa = _prepare_statement(tabelas, "BPA")
    bpp = _prepare_statement(tabelas, "BPP")
    dfc = pd.concat([_prepare_statement(tabelas, "DFC_MI"),
                     _prepare_statement(tabelas, "DFC_MD")], ignore_index=True)
    dva = _prepare_statement(tabelas, "DVA")
    fin = _financial_docs(bpa, dre)
    it_dre = _itens_dre(dre, fin)
    it_bpp = _itens_bpp(bpp, fin)
    it_dfc, qa_capex = _itens_dfc(dfc)
    partes = it_dre + it_dfc + _itens_dva(dva) + _itens_bpa(bpa, fin) + it_bpp
    partes = [p for p in partes if not p.empty]
    frames = []
    if partes:
        f = pd.concat(partes, ignore_index=True)
        if "dt_ini" not in f.columns:
            f["dt_ini"] = pd.NaT
        frames.append(_preferir_dva(f))
    # ações (composição do capital), com a unidade conferida
    ni = [p for p in it_dre if not p.empty and p["item"].iloc[0] == "lucro_liquido"]
    ni_flows = (ni[0].rename(columns={"dt_ini": "period_start", "dt_fim": "period_end"})
                if ni else pd.DataFrame(columns=["cnpj", "dt_refer", "versao", "kind",
                                                 "period_start", "period_end", "value"]))
    eq = [p for p in it_bpp if not p.empty and p["item"].iloc[0] == "patrimonio_liquido"]
    eq_doc = (eq[0].drop_duplicates(["cnpj", "dt_refer", "versao"])[
        ["cnpj", "dt_refer", "versao", "value"]] if eq else None)
    cap = _itens_capital(tabelas.get("capital", pd.DataFrame()), dre, eq_doc, ni_flows)
    if not cap.empty:
        cap = cap.assign(kind="con", dt_ini=pd.NaT, dt_fim=cap["dt_refer"], currency=None,
                         demonstrativo="BP")
        frames.append(cap)
    if not frames:
        return _com_qa(pd.DataFrame(columns=FATO_COLUNAS), [], doc_u)
    f = pd.concat(frames, ignore_index=True)
    for c in ("dt_refer", "dt_ini", "dt_fim"):
        f[c] = pd.to_datetime(f[c], errors="coerce")
    f["versao"] = pd.to_numeric(f["versao"], errors="coerce")
    f = f.dropna(subset=["versao"])
    f["versao"] = f["versao"].astype(int)
    f = f.merge(rec, on=["cnpj", "dt_refer", "versao"], how="inner")
    f = f.dropna(subset=["value", "dt_fim"])
    f = f[np.isfinite(f["value"].astype(float))]
    unidade = f["unidade"] if "unidade" in f.columns else pd.Series(None, index=f.index)
    documento = (doc_u + " " + f["dt_refer"].dt.strftime("%Y-%m-%d") + " v"
                 + f["versao"].astype(str))
    documento = documento.where(unidade.isna(), documento + " (ações: unidade " +
                                unidade.astype(str) + ")")
    out = pd.DataFrame({
        "entidade": f["cnpj"].astype(str),
        "demonstrativo": f["demonstrativo"].astype(str),
        "item": f["item"].astype(str),
        "period_start": pd.to_datetime(f["dt_ini"]),
        "period_end": pd.to_datetime(f["dt_fim"]),
        "value": f["value"].astype(float),
        "currency": f["currency"].where(f["currency"].notna(), None),
        "received_date": pd.to_datetime(f["received_date"]),
        "version": f["versao"].astype(int),
        "documento": documento,
        "url": f["url"],
        "consolidado": f["kind"].astype(str).eq("con"),
        "anual": doc_u == "DFP",
    })
    opcionais = [c for c in ("semantica_fluxo", "rubrica_reportada") if c in f.columns]
    for c in opcionais:
        out[c] = f[c]
    return _com_qa(out[FATO_COLUNAS + opcionais].reset_index(drop=True), qa_capex, doc_u)


def _com_qa(df: pd.DataFrame, qa: list[dict], doc: str) -> pd.DataFrame:
    """Anexa os alertas de conferência (``attrs['qa']``: ``cnpj``, ``documento``, ``msg``)."""
    df.attrs["qa"] = [{"cnpj": q["cnpj"],
                       "documento": f"{doc} {pd.Timestamp(q['dt_refer']).date()} v{int(q['versao'])}",
                       "msg": q["msg"]} for q in qa]
    return df


# ======================================================================
# FRE — ações em circulação (free float)
# ======================================================================

def free_float_fre(conteudo: bytes, ano: int, cnpjs: Iterable[str] | None = None,
                   ) -> pd.DataFrame:
    """``cnpj, data_ref, versao, free_float_pct, data_publicacao, url`` (fração 0–1).

    ``Percentual_Total_Acoes_Circulacao`` (item 15.3 do FRE) ÷ 100; publicação = ``DT_RECEB``
    da versão do FRE. Valores fora de (0, 100] ⇒ descartados (ausente, nunca zero).
    """
    cols = ["cnpj", "data_ref", "versao", "free_float_pct", "data_publicacao", "url"]
    alvo = None if cnpjs is None else {str(c).strip() for c in cnpjs}
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        nomes = zf.namelist()
        n_dist = _membro(nomes, f"fre_cia_aberta_distribuicao_capital_{ano}.csv")
        n_idx = _membro(nomes, f"fre_cia_aberta_{ano}.csv")
        if n_dist is None or n_idx is None:
            return pd.DataFrame(columns=cols)
        dist = read_cvm_csv(zf.read(n_dist))
        idx = read_cvm_csv(zf.read(n_idx))
    need = {"CNPJ_Companhia", "Data_Referencia", "Versao", "Percentual_Total_Acoes_Circulacao"}
    if not need <= set(dist.columns):
        return pd.DataFrame(columns=cols)
    d = pd.DataFrame({
        "cnpj": dist["CNPJ_Companhia"].astype(str).str.strip(),
        "data_ref": pd.to_datetime(dist["Data_Referencia"], errors="coerce"),
        "versao": pd.to_numeric(dist["Versao"], errors="coerce"),
        "free_float_pct": pd.to_numeric(dist["Percentual_Total_Acoes_Circulacao"],
                                        errors="coerce") / 100.0,
    }).dropna()
    if alvo is not None:
        d = d[d["cnpj"].isin(alvo)]
    d = d[(d["free_float_pct"] > 0) & (d["free_float_pct"] <= 1.0)]
    i = pd.DataFrame({
        "cnpj": idx["CNPJ_CIA"].astype(str).str.strip(),
        "data_ref": pd.to_datetime(idx["DT_REFER"], errors="coerce"),
        "versao": pd.to_numeric(idx["VERSAO"], errors="coerce"),
        "data_publicacao": pd.to_datetime(idx["DT_RECEB"], errors="coerce"),
        "url": idx["LINK_DOC"].astype(str) if "LINK_DOC" in idx.columns else None,
    }).dropna(subset=["data_ref", "versao", "data_publicacao"])
    d = d.merge(i, on=["cnpj", "data_ref", "versao"], how="inner")
    d["versao"] = d["versao"].astype(int)
    return d[cols].reset_index(drop=True)


# ======================================================================
# IPE — eventos (assembleias, fatos relevantes, calendário)
# ======================================================================

IPE_COLUNAS = ["cnpj", "categoria", "tipo", "especie", "data_referencia", "data_entrega",
               "versao", "url", "assunto"]


def ler_ipe(conteudo: bytes, ano: int, cnpjs: Iterable[str] | None = None) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        nome = _membro(zf.namelist(), f"ipe_cia_aberta_{ano}.csv")
        if nome is None:
            return pd.DataFrame(columns=IPE_COLUNAS)
        df = read_cvm_csv(zf.read(nome))
    alvo = None if cnpjs is None else {str(c).strip() for c in cnpjs}
    if alvo is not None:
        df = df[df["CNPJ_Companhia"].astype(str).str.strip().isin(alvo)]

    def col(c: str) -> pd.Series:
        return df[c] if c in df.columns else pd.Series(pd.NA, index=df.index)

    out = pd.DataFrame({
        "cnpj": col("CNPJ_Companhia").astype(str).str.strip(),
        "categoria": col("Categoria").fillna("").map(normalize_text),
        "tipo": col("Tipo").fillna("").map(normalize_text),
        "especie": col("Especie").fillna("").map(normalize_text),
        "data_referencia": pd.to_datetime(col("Data_Referencia"), errors="coerce"),
        "data_entrega": pd.to_datetime(col("Data_Entrega"), errors="coerce"),
        "versao": pd.to_numeric(col("Versao"), errors="coerce"),
        "url": col("Link_Download").astype(str),
        "assunto": col("Assunto").fillna("").astype(str).str.slice(0, 200),
    })
    return out.reset_index(drop=True)


def eventos_ipe(ipe: pd.DataFrame) -> pd.DataFrame:
    """Assembleias (edital de convocação ⇒ data da assembleia) e fatos relevantes."""
    cols = ["cnpj", "data", "tipo", "estimada", "url", "documento"]
    if ipe.empty:
        return pd.DataFrame(columns=cols)
    ass = ipe[(ipe["categoria"] == "assembleia") & ipe["especie"].str.contains(
        "edital de convocacao") & ipe["data_referencia"].notna()]
    ass = (ass.sort_values(["cnpj", "data_referencia", "tipo", "data_entrega"])
           .drop_duplicates(["cnpj", "data_referencia", "tipo"], keep="last"))
    a = pd.DataFrame({"cnpj": ass["cnpj"], "data": ass["data_referencia"], "tipo": "assembleia",
                      "estimada": False, "url": ass["url"],
                      "documento": "CVM IPE: edital de convocação (" + ass["tipo"].str.upper()
                      + ")"})
    fr = ipe[(ipe["categoria"] == "fato relevante") & ipe["data_entrega"].notna()]
    fr = fr.sort_values(["cnpj", "data_entrega"]).drop_duplicates(["cnpj", "data_entrega"])
    f = pd.DataFrame({"cnpj": fr["cnpj"], "data": fr["data_entrega"], "tipo": "fato_relevante",
                      "estimada": False, "url": fr["url"], "documento": "CVM IPE: fato relevante"})
    return pd.concat([a, f], ignore_index=True)[cols]


def calendarios_ipe(ipe: pd.DataFrame) -> pd.DataFrame:
    """Última versão do "Calendário de Eventos Corporativos" por companhia e ano de referência."""
    cols = ["cnpj", "ano", "versao", "url", "data_entrega"]
    cal = ipe[ipe["categoria"].str.startswith("calendario de eventos corporativos")]
    if cal.empty:
        return pd.DataFrame(columns=cols)
    cal = cal.assign(ano=cal["data_referencia"].dt.year)
    cal = cal.sort_values(["cnpj", "ano", "versao", "data_entrega"])
    cal = cal.drop_duplicates(["cnpj", "ano"], keep="last")
    return cal[cols].reset_index(drop=True)


_DATA_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_TRIM_RE = re.compile(r"(1|2|3|4)\s*[ºo°]?\s*trimestre")


def _secao(txt: str, atual: str) -> str:
    if "informacoes trimestrais" in txt:
        return "itr"
    if "demonstracoes financeiras anuais" in txt or "demonstracoes financeiras padronizadas" in txt:
        return "dfp"
    if "assembleia geral ordinaria" in txt and "realizacao" not in txt:
        return "ago"
    if "assembleia geral extraordinaria" in txt and "realizacao" not in txt:
        return "age"
    if "apresentacao publica" in txt or "reuniao publica" in txt:
        return "apresentacao"
    if any(k in txt for k in ("formulario de referencia", "codigo brasileiro",
                              "alteracoes efetuadas", "informe sobre")):
        return "outro"
    return atual


def eventos_do_calendario(celulas: list[tuple[int, float, float, str]],
                          x_min_data: float = 380.0, dy: float = 8.0) -> list[dict]:
    """Eventos do PDF padronizado "Calendário Anual de Eventos Corporativos".

    ``celulas`` = ``(página, y, x, texto)`` (:func:`.publico_pdf.celulas`). As datas programadas
    ficam na coluna da direita (``x >= x_min_data``); o rótulo é o texto da esquerda a até
    ``dy`` pontos da data (rótulos de duas linhas). Seções: DFP e ITR (``resultado``), AGO
    (``assembleia``, só a realização) e apresentação pública (``teleconferencia``). Datas dentro
    do texto (ex.: "findo em 31/12/2025") e a seção "Alterações efetuadas" são ignoradas.
    """
    out: list[dict] = []
    secao = ""
    for pg, y, x, bruto in celulas:
        txt = normalize_text(bruto)
        if x < x_min_data:
            secao = _secao(txt, secao)
            continue
        m = _DATA_RE.fullmatch(bruto.strip())
        if m is None:
            continue
        dd, mm, aa = m.groups()
        try:
            d = date(int(aa), int(mm), int(dd))
        except ValueError:
            continue
        rotulo = " ".join(normalize_text(t) for p2, y2, x2, t in celulas
                          if p2 == pg and x2 < x_min_data and abs(y2 - y) <= dy)
        if secao == "itr":
            t = _TRIM_RE.search(rotulo)
            if t:
                out.append({"data": d, "tipo": "resultado", "rotulo": f"ITR {t.group(1)}T"})
        elif secao == "dfp":
            out.append({"data": d, "tipo": "resultado", "rotulo": "DFP"})
        elif secao in ("ago", "age") and "realizacao" in rotulo:
            out.append({"data": d, "tipo": "assembleia", "rotulo": secao.upper()})
        elif secao == "apresentacao":
            t = _TRIM_RE.search(rotulo)
            rot = f"{t.group(1)}T" if t else ("anual" if "exercicio" in rotulo else "")
            out.append({"data": d, "tipo": "teleconferencia", "rotulo": rot})
    return out


def datas_resultado_cvm(indices: Iterable[pd.DataFrame], doc_por_indice: Iterable[str],
                        ) -> pd.DataFrame:
    """Datas efetivas de resultado: ``DT_RECEB`` da 1ª versão de cada ITR/DFP (``cnpj``...)."""
    cols = ["cnpj", "data", "dt_refer", "documento", "url"]
    frames = []
    for idx, doc in zip(indices, doc_por_indice, strict=True):
        if idx is None or idx.empty:
            continue
        f = pd.DataFrame({
            "cnpj": idx["CNPJ_CIA"].astype(str).str.strip(),
            "dt_refer": pd.to_datetime(idx["DT_REFER"], errors="coerce"),
            "versao": pd.to_numeric(idx["VERSAO"], errors="coerce"),
            "data": pd.to_datetime(idx["DT_RECEB"], errors="coerce"),
            "url": idx["LINK_DOC"].astype(str) if "LINK_DOC" in idx.columns else None,
        }).dropna(subset=["dt_refer", "versao", "data"])
        f = f.sort_values(["cnpj", "dt_refer", "versao", "data"]).drop_duplicates(
            ["cnpj", "dt_refer"], keep="first")
        f["documento"] = doc.upper() + " " + f["dt_refer"].dt.strftime("%Y-%m-%d")
        frames.append(f[cols])
    if not frames:
        return pd.DataFrame(columns=cols)
    return pd.concat(frames, ignore_index=True)


__all__ = [
    "FATO_COLUNAS", "IPE_COLUNAS", "PARSER_CVM", "TABELAS", "calendarios_ipe",
    "datas_resultado_cvm", "eventos_do_calendario", "eventos_ipe", "fatos_cvm",
    "free_float_fre", "ler_ipe", "ler_zip_demonstracoes", "url_zip", "validar_zip",
]
