"""Motor point-in-time comum (CVM, SEC, Yahoo): fatos brutos → linhas canônicas A/Q/TTM.

Entrada: fatos com ``FATO_COLUNAS`` (:mod:`.publico_cvm`) mais ``fonte`` e ``sha256`` (do arquivo
bruto de origem). Em ``as_of``:

1. só fatos com ``received_date <= as_of`` (data de publicação: CVM ``DT_RECEB``; SEC ``filed``);
2. **moeda vigente**: por entidade, só a moeda de apresentação do documento mais recente
   publicado até ``as_of`` (quem muda de moeda — ARS → USD, MXN → USD — nunca tem séries que
   misturam moedas; períodos só disponíveis na moeda antiga ficam ausentes e a troca é
   registrada em ``attrs['moeda_trocada']``);
3. por (entidade, item, início, fim), a publicação mais recente (data, depois versão);
4. **fluxos** — ``A``: valor de 12 meses (350–380 dias) do período; ``Q``: trimestre discreto
   (3 meses reportado; senão diferença de acumulados do mesmo exercício; Q4 = anual − 9M);
   ``TTM``: anual quando o período fecha o exercício, senão soma de 4 trimestres discretos.
   ``consolidado`` de ``Q``/``TTM`` derivados = todos os documentos usados consolidados (base
   mista registrada em ``nota``);
5. **saldos** (CVM/SEC) — só em datas-base de períodos (fins de mês com fluxo do emissor):
   ``Q`` em toda data-base; ``A`` só no fim de exercício (data com fluxo de 12 meses). Saldos
   em datas avulsas (abertura IFRS 16, entidade antes de reorganização, data de capa) não
   viram período.

``data_publicacao`` de uma linha derivada = publicação do documento do próprio ``period_end``
(o mais recente dos documentos usados). Derivados calculados por código: ``ebitda = ebit + d_a``,
``fcf = cfo − capex``, ``divida_liquida = divida_bruta − caixa − aplicacoes_cp`` (aplicações
ausentes ⇒ só caixa, com nota). Componente ausente ⇒ derivado ausente (nunca zero).
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from .fundamentals_pit import _QUARTER_DAYS as _QUARTER_DIAS
from .fundamentals_pit import _quarter_value, _ttm_value

FLUXOS = frozenset({
    "receita", "lucro_bruto", "ebit", "ebitda", "d_a", "resultado_financeiro", "lucro_antes_ir",
    "ir_csll", "lucro_liquido", "lucro_liquido_controladores", "cfo", "capex", "fcf",
    "dividendos_pagos", "recompras", "margem_financeira", "receita_servicos", "despesa_pdd",
})

SAIDA_COLUNAS = [
    "entidade", "demonstrativo", "freq", "period_end", "item", "value", "currency", "escala",
    "consolidado", "fonte", "url", "documento", "data_publicacao", "sha256", "pit_estimado",
    "nota",
]

_ANUAL = (350, 380)


def _texto(v) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return None
    return str(v) or None


def _meta(row) -> dict:
    return {
        "demonstrativo": row.demonstrativo, "currency": row.currency,
        "consolidado": bool(row.consolidado), "fonte": row.fonte, "url": row.url,
        "documento": row.documento, "data_publicacao": row.received_date, "sha256": row.sha256,
        "pit_estimado": bool(getattr(row, "pit_estimado", False)),
        "nota": _texto(getattr(row, "nota", None)),
    }


def _moeda_vigente(f: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Mantém, por entidade, só a moeda do documento mais recente (ações não têm moeda)."""
    trocas: dict[str, dict] = {}
    com = f[f["currency"].notna()]
    if com.empty:
        return f, trocas
    manter = pd.Series(True, index=f.index)
    for ent, g in com.groupby("entidade", sort=False):
        moedas = set(g["currency"])
        if len(moedas) <= 1:
            continue
        ult = g[g["received_date"] == g["received_date"].max()]["currency"]
        atual = ult.value_counts().sort_index().idxmax()
        fora = g.index[g["currency"] != atual]
        manter.loc[fora] = False
        desde = g.loc[g["currency"] == atual, "received_date"].min()
        trocas[str(ent)] = {"moeda": atual, "anteriores": sorted(moedas - {atual}),
                            "desde": pd.Timestamp(desde).date().isoformat(),
                            "fatos_descartados": int(len(fora))}
    return f[manter], trocas


def _datas_base(f: pd.DataFrame) -> tuple[dict[str, set], dict[str, set]]:
    """Por entidade: fins de períodos com fluxo (80–380 dias) e fins de exercício (12 meses),
    sempre em fim de mês (datas avulsas — ex.: data de uma reorganização — não são datas-base)."""
    fl = f[f["item"].isin(FLUXOS) & f["period_start"].notna()]
    if fl.empty:
        return {}, {}
    dur = (fl["period_end"] - fl["period_start"]).dt.days + 1
    fl = fl.assign(_dur=dur)
    fl = fl[fl["_dur"].between(80, _ANUAL[1])
            & (fl["period_end"] + pd.Timedelta(days=1)).dt.is_month_start]
    todas = fl.groupby("entidade")["period_end"].agg(lambda x: set(x.dt.date)).to_dict()
    anuais = (fl[fl["_dur"].between(*_ANUAL)].groupby("entidade")["period_end"]
              .agg(lambda x: set(x.dt.date)).to_dict())
    return todas, anuais


def selecionar_pit(fatos: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Linhas canônicas (``SAIDA_COLUNAS``) conhecidas em ``as_of`` — sem look-ahead."""
    if fatos is None or fatos.empty:
        return pd.DataFrame(columns=SAIDA_COLUNAS)
    f = fatos.copy()
    if "pit_estimado" not in f.columns:
        f["pit_estimado"] = False
    # fatos de fontes oficiais concatenados com os do Yahoo chegam com NaN aqui (≠ estimado)
    f["pit_estimado"] = f["pit_estimado"].astype("boolean").fillna(False).astype(bool)
    f["received_date"] = pd.to_datetime(f["received_date"])
    f["period_end"] = pd.to_datetime(f["period_end"])
    f["period_start"] = pd.to_datetime(f["period_start"])
    f = f[(f["received_date"] <= pd.Timestamp(as_of)) & f["value"].notna()]
    f = f[np.isfinite(f["value"].astype(float))]
    if f.empty:
        return pd.DataFrame(columns=SAIDA_COLUNAS)
    f, trocas = _moeda_vigente(f)
    f = f.sort_values(["entidade", "item", "received_date", "version", "period_end"],
                      kind="stable")
    datas, anuais = _datas_base(f)
    oficiais = set(f.loc[f["fonte"].isin(["CVM", "SEC"]), "entidade"]) \
        if "fonte" in f.columns else set()
    linhas: list[dict] = []
    for (ent, item), g in f.groupby(["entidade", "item"], sort=True):
        if item in FLUXOS:
            linhas.extend(_fluxo(ent, item, g))
        elif ent in oficiais:
            linhas.extend(_saldo(ent, item, g, datas.get(ent, set()), anuais.get(ent, set())))
        else:
            linhas.extend(_saldo(ent, item, g, None, None))
    out = pd.DataFrame(linhas)
    if out.empty:
        vazio = pd.DataFrame(columns=SAIDA_COLUNAS)
        vazio.attrs["moeda_trocada"] = trocas
        return vazio
    out = pd.concat([out, _derivados(out)], ignore_index=True)
    out["escala"] = 1
    if "nota" not in out.columns:
        out["nota"] = None
    out["value"] = out["value"].astype(float) + 0.0  # -0.0 ⇒ 0.0
    out = (out[SAIDA_COLUNAS]
           .sort_values(["entidade", "item", "freq", "period_end"], kind="stable")
           .reset_index(drop=True))
    out.attrs["moeda_trocada"] = trocas
    return out


def _base_janela(meta_end: dict[date, dict], fim: date, dias: int) -> tuple[bool, str | None]:
    """``consolidado`` = todos os documentos da janela ``(fim − dias, fim]`` consolidados."""
    ms = [m for e, m in meta_end.items() if fim - pd.Timedelta(days=dias).to_pytimedelta() < e
          <= fim]
    flags = {bool(m["consolidado"]) for m in ms}
    if len(flags) > 1:
        return False, "base mista: componentes individuais e consolidados"
    return (flags.pop() if flags else True), None


def _juntar(*notas: str | None) -> str | None:
    vistas: list[str] = []
    for n in notas:
        if n and n not in vistas:
            vistas.append(n)
    return "; ".join(vistas) or None


def _fluxo(ent: str, item: str, g: pd.DataFrame) -> list[dict]:
    g = g.dropna(subset=["period_start", "period_end"])
    by_end: dict[date, dict[date, float]] = {}
    meta_end: dict[date, dict] = {}
    meta_anual: dict[date, dict] = {}
    for row in g.itertuples(index=False):
        s, e = row.period_start.date(), row.period_end.date()
        by_end.setdefault(e, {})[s] = float(row.value)
        meta_end[e] = _meta(row)  # ordenado por publicação ⇒ o último é o mais recente
        dur = (e - s).days + 1
        if _ANUAL[0] <= dur <= _ANUAL[1]:
            meta_anual[e] = _meta(row)
    out = []
    for e in sorted(by_end):
        flows = by_end[e]
        anual = [(abs((e - s).days + 1 - 365), v) for s, v in flows.items()
                 if _ANUAL[0] <= (e - s).days + 1 <= _ANUAL[1]]
        if anual:
            out.append({"entidade": ent, "item": item, "freq": "A",
                        "period_end": pd.Timestamp(e), "value": min(anual)[1],
                        **meta_anual.get(e, meta_end[e])})
        q = _quarter_value(by_end, e)
        if math.isfinite(q):
            direto = any(_QUARTER_DIAS[0] <= (e - s0).days + 1 <= _QUARTER_DIAS[1]
                         for s0 in flows)
            cons, nota_base = _base_janela(meta_end, e, 1 if direto else 100)
            out.append({"entidade": ent, "item": item, "freq": "Q",
                        "period_end": pd.Timestamp(e), "value": q,
                        **{**meta_end[e], "consolidado": cons,
                           "nota": _juntar(meta_end[e].get("nota"), nota_base)}})
        t, how = _ttm_value(by_end, e)
        if math.isfinite(t):
            cons, nota_base = _base_janela(meta_end, e, 1 if how == "12m" else 370)
            out.append({"entidade": ent, "item": item, "freq": "TTM",
                        "period_end": pd.Timestamp(e), "value": t,
                        **{**meta_end[e], "consolidado": cons,
                           "nota": _juntar(meta_end[e].get("nota"), nota_base)}})
    return out


def _saldo(ent: str, item: str, g: pd.DataFrame, datas: set | None,
           anuais_ent: set | None) -> list[dict]:
    """Saldos por data-base. ``datas``/``anuais_ent`` (CVM/SEC): só datas com fluxo do emissor
    viram período ``Q`` e só fins de exercício viram ``A``; ``None`` (Yahoo, colunas já são
    datas de período): ``A`` quando a coluna é anual."""
    out = []
    for e, ge in g.groupby("period_end", sort=True):
        d = pd.Timestamp(e).date()
        if datas is not None and d not in datas:
            continue
        row = list(ge.itertuples(index=False))[-1]
        base = {"entidade": ent, "item": item, "period_end": pd.Timestamp(e),
                "value": float(row.value), **_meta(row)}
        out.append({**base, "freq": "Q"})
        anuais = ge[ge["anual"].astype(bool)]
        if anuais_ent is not None:
            if d not in anuais_ent:
                continue
            ra = list((anuais if not anuais.empty else ge).itertuples(index=False))[-1]
        elif anuais.empty:
            continue
        else:
            ra = list(anuais.itertuples(index=False))[-1]
        out.append({"entidade": ent, "item": item, "period_end": pd.Timestamp(e),
                    "value": float(ra.value), **_meta(ra), "freq": "A"})
    return out


def derivados(df: pd.DataFrame) -> pd.DataFrame:
    """Itens calculados (``ebit`` na falta, ``ebitda``, ``fcf``, ``divida_liquida``) por
    (entidade, freq, period_end) — usado de novo depois do complemento e da conferência."""
    return _derivados(df)


def _derivados(df: pd.DataFrame) -> pd.DataFrame:
    """``ebitda``, ``fcf`` e ``divida_liquida`` por (entidade, freq, period_end)."""
    k = ["entidade", "freq", "period_end"]
    w = df.pivot_table(index=k, columns="item", values="value", aggfunc="first")
    meta_cols = ["demonstrativo", "currency", "consolidado", "fonte", "url", "documento",
                 "data_publicacao", "sha256", "pit_estimado", "nota"]
    if "nota" not in df.columns:
        df = df.assign(nota=None)
    meta = df.set_index(k + ["item"])[meta_cols]
    meta = meta[~meta.index.duplicated(keep="last")]
    out = []

    def add(nome: str, comp: list[str], valor: pd.Series, demonstrativo: str, nota: str,
            opcionais: tuple[str, ...] = ()) -> None:
        for idx, v in valor.dropna().items():
            if not math.isfinite(float(v)):
                continue
            ms = [meta.loc[(*idx, c)] for c in comp if (*idx, c) in meta.index]
            ms += [meta.loc[(*idx, c)] for c in opcionais if (*idx, c) in meta.index
                   and pd.notna(w.loc[idx, c] if c in w.columns else np.nan)]
            if not ms:
                continue
            pub = max(m["data_publicacao"] for m in ms)
            m0 = ms[0]
            notas = [_texto(m["nota"]) for m in ms]
            notas = [n for n in notas if n and not n.startswith("calculado")]
            out.append({"entidade": idx[0], "freq": idx[1], "period_end": idx[2], "item": nome,
                        "value": float(v), "demonstrativo": demonstrativo,
                        "currency": m0["currency"],
                        "consolidado": all(bool(m["consolidado"]) for m in ms),
                        "fonte": m0["fonte"], "url": m0["url"],
                        "documento": m0["documento"], "data_publicacao": pub,
                        "sha256": m0["sha256"],
                        "pit_estimado": any(bool(m["pit_estimado"]) for m in ms),
                        "nota": _juntar(nota, *notas)})

    def col(c: str) -> pd.Series:
        return w[c] if c in w.columns else pd.Series(np.nan, index=w.index)

    sem_ebit = col("ebit").isna()
    add("ebit", ["lucro_antes_ir", "resultado_financeiro"],
        (col("lucro_antes_ir") - col("resultado_financeiro")).where(sem_ebit), "DRE",
        "calculado: lucro_antes_ir − resultado_financeiro (inclui equivalência patrimonial)")
    ebit_tot = col("ebit").where(~sem_ebit, col("lucro_antes_ir") - col("resultado_financeiro"))
    add("ebitda", ["ebit", "d_a", "lucro_antes_ir", "resultado_financeiro"],
        (ebit_tot + col("d_a")).where(col("ebitda").isna()), "DRE", "calculado: ebit + d_a")
    add("fcf", ["cfo", "capex"], (col("cfo") - col("capex")).where(col("fcf").isna()), "DFC",
        "calculado: cfo − capex")
    liq_com_aplic = col("divida_bruta") - col("caixa") - col("aplicacoes_cp")
    liq_so_caixa = (col("divida_bruta") - col("caixa")).where(col("aplicacoes_cp").isna())
    add("divida_liquida", ["divida_bruta", "caixa", "aplicacoes_cp"], liq_com_aplic, "BP",
        "calculado: divida_bruta − caixa − aplicacoes_cp")
    add("divida_liquida", ["divida_bruta", "caixa"], liq_so_caixa, "BP",
        "calculado: divida_bruta − caixa (aplicações de curto prazo não informadas)")
    return pd.DataFrame(out)


__all__ = ["FLUXOS", "SAIDA_COLUNAS", "derivados", "selecionar_pit"]
