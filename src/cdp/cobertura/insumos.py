"""Normalização dos insumos públicos por emissor (moeda e unidade da linha de valuation).

Para cada emissor monta um "pacote de insumos" (``dict`` JSON, números arredondados a 6
algarismos significativos) com tudo o que o modelo usa, cada valor com sua proveniência pública
(CVM/SEC/Yahoo/BCB/FRED/B3/Damodaran ou ``SIMULADO``) e cada ausência registrada em ``lacunas``
com o motivo. O motor de valuation é uma função pura desse pacote: ``cobertura verify`` refaz
cada modelo a partir dos pacotes arquivados.

Regras:

- **Linha de valuation**: a linha cotada na moeda das demonstrações (local antes de ADR, depois a
  mais líquida); sem nenhuma, a linha primária com conversão pelo câmbio à vista. Argentina:
  sempre a linha em dólar (trilha USD).
- **Unidades**: ações por linha = razão do ADR × ações por unidade (``unidades.csv``); conferidas
  contra o valor de mercado público da linha (tolerância de 25%); divergência ⇒ unidades pelo
  valor de mercado, com aviso.
- **Preço e câmbio**: sempre o nosso fechamento e o nosso câmbio (nunca múltiplos prontos da
  fonte).
- **Ausente nunca vira zero**: item sem dado fica ``None`` e entra em ``lacunas``.
- **Point-in-time**: ``pit_ok`` só quando há demonstrativos, todos publicados até a data e
  nenhum com data de publicação estimada (``pit_estimado``); datas estimadas aparecem como
  "data estimada" na tabela de insumos.
- **Mesma data-base**: fluxos de 12 meses defasados mais de 100 dias em relação ao último
  balanço geram aviso e lacuna (nunca misturados em silêncio); acima de 450 dias o item é
  descartado.
- **Crescimento**: financeiras não usam crescimento de receita (receita de intermediação não é
  comparável entre fontes); crescimento histórico fora de [−20%; +30%] (efeitos contábeis, como
  receita de construção de concessões) fica ausente, com lacuna.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from ..market import MarketData
from .fontes import DadosPublicos
from .formato import pct, r6
from .parametros import Arquetipo, ParametrosCobertura, arquetipo_padrao
from .passos import prov_codigo, prov_dict

FLUXOS = ("receita", "lucro_bruto", "ebit", "ebitda", "d_a", "resultado_financeiro", "lucro_antes_ir",
          "ir_csll", "lucro_liquido", "lucro_liquido_controladores", "cfo", "capex", "fcf",
          "dividendos_pagos", "recompras", "margem_financeira", "receita_servicos", "despesa_pdd")
ESTOQUES = ("caixa", "aplicacoes_cp", "divida_bruta", "divida_liquida", "arrendamentos",
            "patrimonio_liquido", "patrimonio_controladores", "participacao_minoritarios",
            "ativo_total", "acoes_emitidas", "acoes_tesouraria", "acoes_em_circulacao",
            "provisao_credito", "carteira_credito")
HIST_ITENS = ("receita", "ebit", "lucro_liquido_controladores", "patrimonio_controladores",
              "acoes_em_circulacao")
SEMANAS_ANO = 52
DEFASAGEM_AVISO_DIAS = 100
LIMITES_G_HIST = (-0.20, 0.30)

ROTULOS = {
    "receita": "receita", "lucro_bruto": "lucro bruto", "ebit": "EBIT", "ebitda": "EBITDA",
    "d_a": "depreciação e amortização", "resultado_financeiro": "resultado financeiro",
    "lucro_antes_ir": "lucro antes do imposto de renda", "ir_csll": "imposto de renda e contribuição social",
    "lucro_liquido": "lucro líquido", "lucro_liquido_controladores": "lucro líquido dos controladores",
    "cfo": "fluxo de caixa das operações", "capex": "investimento em ativo fixo e intangível (capex)",
    "fcf": "fluxo de caixa livre", "dividendos_pagos": "dividendos e juros sobre capital pagos",
    "recompras": "recompra de ações", "margem_financeira": "margem financeira",
    "receita_servicos": "receita de serviços", "despesa_pdd": "despesa de provisão para crédito",
    "caixa": "caixa e equivalentes", "aplicacoes_cp": "aplicações financeiras de curto prazo",
    "divida_bruta": "dívida bruta", "divida_liquida": "dívida líquida",
    "arrendamentos": "passivos de arrendamento", "patrimonio_liquido": "patrimônio líquido total",
    "patrimonio_controladores": "patrimônio líquido dos controladores",
    "participacao_minoritarios": "participação de não controladores", "ativo_total": "ativo total",
    "acoes_emitidas": "ações emitidas", "acoes_tesouraria": "ações em tesouraria",
    "acoes_em_circulacao": "ações em circulação", "provisao_credito": "provisão para crédito",
    "carteira_credito": "carteira de crédito", "preco": "preço de fechamento",
    "eps_fy1": "LPA de consenso (ano 1)", "eps_fy2": "LPA de consenso (ano 2)",
    "eps_ttm": "LPA dos últimos 12 meses", "bvps": "patrimônio por ação", "dps12": "dividendo esperado",
    "dps_12m": "dividendos dos últimos 12 meses", "unidades": "unidades em circulação",
    "demonstrativos": "demonstrações financeiras", "fx_demonstrativos_para_modelo": "câmbio das demonstrações",
    "soma_partes": "soma das partes", "g_receita_historico": "crescimento histórico da receita",
    "defasagem_fluxos": "data-base dos fluxos", "minoritarios": "participação de não controladores",
    "composicao": "composição do ETF", "delta_s": "variação do número de ações",
    "bottom_up": "retorno bottom-up",
}
FREQ_PT = {"TTM": "12 meses", "A": "anual", "Q": "trimestral"}
DOC_YAHOO_PT = {
    "quarterly_income_stmt": "demonstração de resultados trimestral",
    "quarterly_balance_sheet": "balanço patrimonial trimestral",
    "quarterly_cashflow": "demonstração dos fluxos de caixa trimestral",
    "ttm_income_stmt": "demonstração de resultados de 12 meses",
    "ttm_cashflow": "demonstração dos fluxos de caixa de 12 meses",
    "income_stmt": "demonstração de resultados anual",
    "balance_sheet": "balanço patrimonial anual",
    "cashflow": "demonstração dos fluxos de caixa anual",
}


def rotulo(chave: str) -> str:
    """Rótulo pt-BR de um item/insumo (identificadores internos nunca aparecem ao investidor)."""
    base = str(chave).removeprefix("t.")
    return ROTULOS.get(base, base.replace("_", " "))


def lacuna(insumo: str, motivo: str) -> dict[str, str]:
    return {"insumo": insumo, "nome": rotulo(insumo), "motivo": motivo}


def documento_pt(doc: Any) -> str:
    """Nomes de tabelas da fonte (``income_stmt``, ``quarterly_balance_sheet``…) em pt-BR."""
    if doc is None or (isinstance(doc, float) and math.isnan(doc)):
        return ""
    texto = str(doc)
    for k, v in DOC_YAHOO_PT.items():
        if k in texto:
            texto = texto.replace(k, v)
            break
    return texto.replace("Yahoo Finance ", "Yahoo Finance — ")


def _f(x: Any) -> float | None:
    """Número finito ou ``None`` (nunca zero por omissão)."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


# ============================================================ mercado (preço, câmbio, volume)

def ultimo_preco(md: MarketData, ticker: str, as_of: date) -> tuple[float | None, date | None]:
    if ticker not in md.close.columns:
        return None, None
    s = md.close[ticker].loc[:pd.Timestamp(as_of)].dropna()
    s = s[s > 0]
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1].date()


def fx_usd(md: MarketData, moeda: str, as_of: date) -> tuple[float | None, date | None]:
    """USD por 1 unidade da moeda (último valor ``<= as_of``)."""
    m = (moeda or "").upper()
    if m == "USD":
        return 1.0, as_of
    if m not in md.fx.columns:
        return None, None
    s = md.fx[m].loc[:pd.Timestamp(as_of)].dropna()
    s = s[s > 0]
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1].date()


def adtv_usd(md: MarketData, ticker: str, as_of: date, janela: int = 63) -> float | None:
    if ticker not in md.close.columns or ticker not in md.volume.columns:
        return None
    ccy = str(md.universe.lines.loc[ticker, "currency"]) if ticker in md.universe.lines.index else "USD"
    fx, _ = fx_usd(md, ccy, as_of)
    if fx is None:
        return None
    px = md.close[ticker].loc[:pd.Timestamp(as_of)].tail(janela)
    vol = md.volume[ticker].loc[:pd.Timestamp(as_of)].tail(janela)
    tv = (px * vol.where(vol > 0)).dropna()
    return float(tv.mean() * fx) if len(tv) else None


def _serie_usd_semanal(md: MarketData, ticker: str, as_of: date) -> pd.Series:
    if ticker in md.adj_close.columns:
        px = md.adj_close[ticker]
        ccy = str(md.universe.lines.loc[ticker, "currency"]) if ticker in md.universe.lines.index else "USD"
    elif ticker in md.benchmarks.columns:
        px, ccy = md.benchmarks[ticker], "USD"
    else:
        return pd.Series(dtype=float)
    px = px.loc[:pd.Timestamp(as_of)].dropna()
    if ccy != "USD":
        if ccy not in md.fx.columns:
            return pd.Series(dtype=float)
        fx = md.fx[ccy].reindex(px.index).ffill(limit=3)
        px = (px * fx).dropna()
    return px.resample("W-FRI").last().dropna()


def beta_regressao(md: MarketData, ticker: str, ref: str, as_of: date, semanas: int,
                   min_semanas: int) -> tuple[float | None, int]:
    """β de mercado por MQO de retornos semanais em USD (linha × referência), sem ajuste."""
    a = _serie_usd_semanal(md, ticker, as_of)
    b = _serie_usd_semanal(md, ref, as_of)
    if a.empty or b.empty:
        return None, 0
    r = pd.concat([a.pct_change(), b.pct_change()], axis=1, keys=["a", "b"]).dropna().tail(semanas)
    n = len(r)
    if n < min_semanas or float(r["b"].var()) <= 0:
        return None, n
    cov = float(np.cov(r["a"], r["b"], ddof=1)[0, 1])
    return cov / float(r["b"].var(ddof=1)), n


def vol_realizada(md: MarketData, ticker: str, as_of: date, janela: int) -> float | None:
    """Volatilidade anualizada dos log-retornos diários (moeda da linha), ``janela`` pregões."""
    src = md.adj_close if ticker in md.adj_close.columns else md.benchmarks
    if ticker not in src.columns:
        return None
    s = src[ticker].loc[:pd.Timestamp(as_of)].dropna()
    s = s[s > 0].tail(janela + 1)
    if len(s) < max(60, janela // 2):
        return None
    lr = np.log(s).diff().dropna()
    return float(lr.std(ddof=1) * math.sqrt(252))


# ============================================================ demonstrativos (point-in-time)

class Demonstrativos:
    """Acesso aos demonstrativos de um emissor (consolidados quando há; point-in-time).

    Fluxos: o período mais recente entre TTM e anual (TTM no empate); sem TTM recente, soma dos
    4 últimos trimestres consecutivos (TTM derivado em código). Estoques: o balanço mais recente.
    Item com data de referência mais de ``DEFASAGEM_MAX_DIAS`` anterior ao balanço/resultado mais
    recente do emissor é descartado (lacuna "item defasado"), nunca misturado silenciosamente."""

    DEFASAGEM_MAX_DIAS = 450
    ITENS_REFERENCIA = ("patrimonio_controladores", "patrimonio_liquido", "lucro_liquido_controladores",
                        "lucro_liquido", "receita")

    def __init__(self, df: pd.DataFrame, issuer_id: str) -> None:
        d = df[df["issuer_id"] == issuer_id].copy() if not df.empty else df.copy()
        self.defasados: list[str] = []
        if not d.empty:
            d["period_end"] = pd.to_datetime(d["period_end"], errors="coerce")
            d["value"] = pd.to_numeric(d["value"], errors="coerce")
            if "escala" in d.columns:
                esc = pd.to_numeric(d["escala"], errors="coerce").fillna(1.0)
                d["value"] = d["value"] * esc
            if "consolidado" in d.columns:
                cons = d["consolidado"].astype(str).str.lower().isin(["true", "1"])
                if cons.any():
                    d = d[cons]
            if "demonstrativo" in d.columns:
                d = d[d["demonstrativo"].astype(str) != "DFP_IND"]
            d = d.dropna(subset=["period_end", "value"])
            d = pd.concat([d, self._ttm_derivado(d)], ignore_index=True)
        self.df = d
        ref = d[d["item"].isin(self.ITENS_REFERENCIA)]["period_end"].max() if not d.empty else None
        self.ref = None if ref is None or pd.isna(ref) else ref

    @staticmethod
    def _ttm_derivado(d: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for item in FLUXOS:
            q = d[(d["item"] == item) & (d["freq"] == "Q")].sort_values("period_end")
            if len(q) < 4:
                continue
            ult4 = q.drop_duplicates("period_end", keep="last").tail(4)
            gaps = ult4["period_end"].diff().dropna().dt.days
            if len(ult4) < 4 or not gaps.between(80, 100).all():
                continue
            fim = ult4["period_end"].iloc[-1]
            outros = d[(d["item"] == item) & d["freq"].isin(["TTM", "A"])]
            if not outros.empty and outros["period_end"].max() >= fim:
                continue
            r = ult4.iloc[-1].to_dict()
            r.update({"freq": "TTM", "value": float(ult4["value"].sum()),
                      "documento": f"{r.get('documento') or ''} (soma dos 4 últimos trimestres)".strip(),
                      "data_publicacao": ult4["data_publicacao"].max()})
            rows.append(r)
        return pd.DataFrame(rows, columns=d.columns) if rows else d.iloc[0:0]

    @property
    def vazio(self) -> bool:
        return self.df.empty

    def _linha(self, item: str, freqs: Sequence[str]) -> pd.Series | None:
        if self.df.empty:
            return None
        sub = self.df[(self.df["item"] == item) & self.df["freq"].isin(freqs)]
        if sub.empty:
            return None
        prio = {f: i for i, f in enumerate(freqs)}
        sub = sub.assign(_p=sub["freq"].map(prio)).sort_values(
            ["period_end", "_p", "data_publicacao"], ascending=[True, False, True], kind="mergesort")
        row = sub.iloc[-1]
        if self.ref is not None and (self.ref - row["period_end"]).days > self.DEFASAGEM_MAX_DIAS:
            self.defasados.append(f"{item} ({pd.Timestamp(row['period_end']).date()})")
            return None
        return row

    def valor(self, item: str) -> tuple[float | None, pd.Series | None]:
        """Valor mais recente do item (fluxos: 12 meses ou anual; estoques: último balanço)."""
        freqs = ("TTM", "A") if item in FLUXOS else ("Q", "A", "TTM")
        row = self._linha(item, freqs)
        if row is None:
            return None, None
        return _f(row["value"]), row

    def ttm_ano_anterior(self, item: str) -> float | None:
        """Mesmo item TTM (ou anual) ~1 ano antes do último período (crescimento)."""
        if self.df.empty:
            return None
        for fq in ("TTM", "A"):
            sub = self.df[(self.df["item"] == item) & (self.df["freq"] == fq)].sort_values("period_end")
            if len(sub) >= 2:
                ult = sub.iloc[-1]["period_end"]
                alvo = ult - pd.DateOffset(years=1)
                prev = sub[(sub["period_end"] - alvo).abs() <= pd.Timedelta(days=20)]
                if not prev.empty:
                    return _f(prev.iloc[-1]["value"])
        return None

    def anual(self, item: str) -> dict[int, float]:
        if self.df.empty:
            return {}
        sub = self.df[(self.df["item"] == item) & (self.df["freq"] == "A")].sort_values(
            ["period_end", "data_publicacao"], kind="mergesort")
        out: dict[int, float] = {}
        for _, r in sub.iterrows():
            v = _f(r["value"])
            if v is not None:
                out[int(r["period_end"].year)] = v
        return out

    def moeda(self) -> str | None:
        if self.df.empty or "currency" not in self.df.columns:
            return None
        sub = self.df[~self.df["item"].isin(["acoes_em_circulacao", "acoes_emitidas", "acoes_tesouraria"])]
        c = sub.sort_values("period_end")["currency"].dropna()
        c = c[c.astype(str).str.len() == 3]
        return str(c.iloc[-1]).upper() if len(c) else None


def _bool(x: Any) -> bool:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return False
    if isinstance(x, str):
        return x.strip().lower() in ("true", "1", "sim")
    return bool(x)


def _prov_linha(row: pd.Series | None) -> dict[str, Any]:
    if row is None:
        return prov_codigo("sem linha de demonstrativo")
    freq = FREQ_PT.get(str(row.get("freq")), str(row.get("freq")))
    out = prov_dict({"fonte": row.get("fonte"), "url": row.get("url"),
                     "documento": f"{documento_pt(row.get('documento'))} ({row.get('demonstrativo')}, "
                                  f"{freq} até {pd.Timestamp(row['period_end']).date()})".strip(),
                     "data_publicacao": row.get("data_publicacao"), "data_coleta": row.get("data_coleta"),
                     "sha256": row.get("sha256")})
    out["data_estimada"] = _bool(row.get("pit_estimado"))
    return out


# ============================================================ escolha da linha e unidades

def _acoes_por_unidade(params: ParametrosCobertura, ticker: str) -> tuple[float, bool]:
    u = params.unidades.get(ticker)
    return (float(u["acoes_por_unidade"]), bool(u["conferido"])) if u else (1.0, True)


def acoes_por_linha(md: MarketData, params: ParametrosCobertura, issuer_id: str,
                    ticker: str) -> tuple[float, str]:
    """Ações por unidade negociada da linha (ADR: razão × ações por unidade local)."""
    lines = md.universe.lines
    ln = lines.loc[ticker]
    if ln["line_type"] == "ADR":
        ratio = _f(ln["adr_ratio"]) or 1.0
        locais = [t for t in md.universe.lines_for(issuer_id).index
                  if lines.loc[t, "line_type"] == "LOCAL" and t in params.unidades]
        apu = params.unidades[locais[0]]["acoes_por_unidade"] if len(locais) == 1 else 1.0
        return ratio * float(apu), f"ADR = {ratio:g} unidade(s) local(is) × {apu:g} ação(ões)"
    apu, _ = _acoes_por_unidade(params, ticker)
    return apu, ("1 ação por linha" if apu == 1 else f"unidade = {apu:g} ações")


def escolher_linha(md: MarketData, params: ParametrosCobertura, issuer_id: str,
                   moeda_dem: str | None, arq: Arquetipo, as_of: date) -> tuple[str, str]:
    lines = md.universe.lines_for(issuer_id)
    pais = str(md.universe.issuers.loc[issuer_id, "country"])
    if arq.linha_valuation and arq.linha_valuation in lines.index:
        return arq.linha_valuation, "linha definida na curadoria"

    def com_preco(t: str) -> bool:
        p, d = ultimo_preco(md, t, as_of)
        return p is not None and d is not None and (as_of - d).days <= 30

    cands = [t for t in lines.index if com_preco(t)]
    if not cands:
        return str(md.universe.issuers.loc[issuer_id, "primary_ticker"]), "sem preço recente"
    if pais == "AR":
        usd = [t for t in cands if lines.loc[t, "currency"] == "USD"]
        if usd:
            prim = [t for t in usd if bool(lines.loc[t, "primary_line"])]
            return (prim or sorted(usd))[0], "Argentina: trilha em dólar (linha nos EUA)"

    def chave(t: str) -> tuple:
        ln = lines.loc[t]
        match = moeda_dem is not None and str(ln["currency"]).upper() == moeda_dem
        liq = adtv_usd(md, t, as_of) or 0.0
        return (not match, ln["line_type"] != "LOCAL", -liq, not bool(ln["primary_line"]), t)

    esc = sorted(cands, key=chave)[0]
    ln = lines.loc[esc]
    if moeda_dem and str(ln["currency"]).upper() == moeda_dem:
        motivo = "linha cotada na moeda das demonstrações"
    else:
        motivo = "nenhuma linha na moeda das demonstrações: conversão pelo câmbio à vista"
    return str(esc), motivo


# ============================================================ pacote de insumos

class _Pacote:
    def __init__(self) -> None:
        self.v: dict[str, Any] = {}
        self.fontes: dict[str, dict[str, Any]] = {}
        self.lacunas: list[dict[str, str]] = []
        self.avisos: list[str] = []
        self.tabela: list[dict[str, Any]] = []

    def put(self, chave: str, valor: Any, fonte: dict[str, Any] | None = None, *,
            nome: str | None = None, unidade: str | None = None, periodo: str | None = None) -> Any:
        if isinstance(valor, float) or isinstance(valor, int) and not isinstance(valor, bool):
            valor = r6(valor)
        self.v[chave] = valor
        if fonte is not None:
            self.fontes[chave] = fonte
        if nome is not None:
            from .formato import valor as _fmt

            self.tabela.append({"id": chave, "nome": nome, "valor": valor,
                                "valor_texto": _fmt(valor, unidade or "n") if not isinstance(valor, (dict, list, str))
                                else str(valor), "unidade": unidade or "n",
                                "periodo": periodo, "data_estimada": False, **(fonte or prov_codigo(""))})
        return valor

    def falta(self, chave: str, motivo: str) -> None:
        self.v.setdefault(chave, None)
        self.lacunas.append(lacuna(chave, motivo))


def _conv(valor: float | None, fator: float | None) -> float | None:
    return None if valor is None or fator is None else valor * fator


def preparar_emissor(md: MarketData, dados: DadosPublicos, params: ParametrosCobertura,
                     issuer_id: str, as_of: date) -> dict[str, Any]:
    """Pacote de insumos normalizado de um emissor (ver docstring do módulo)."""
    uni = md.universe
    iss = uni.issuers.loc[issuer_id]
    pais = str(iss["country"])
    setor = str(iss["gics_sector"])
    arq = params.arquetipos.get(issuer_id) or arquetipo_padrao(issuer_id, setor)
    beta_setor = params.betas.get(arq.industria_damodaran) or params.betas["Total Market"]
    pk = _Pacote()
    pk.put("issuer_id", issuer_id)
    pk.put("nome", str(iss["issuer_name"]))
    pk.put("pais", pais)
    pk.put("setor", setor)
    pk.put("arquetipo", arq.arquetipo)
    pk.put("arquetipo_nota", arq.nota)
    pk.put("industria", beta_setor.industria)
    pk.put("financeira", bool(beta_setor.financeira or arq.arquetipo in ("banco", "seguradora")))
    pk.put("lambda", float(arq.lambda_))
    pk.put("fim_concessao", arq.fim_concessao)
    pk.put("as_of", as_of.isoformat())

    dem = Demonstrativos(dados.demonstrativos, issuer_id)
    moeda_dem = dem.moeda() or arq.moeda_demonstrativos
    if moeda_dem is None:
        prim = str(iss["primary_ticker"])
        fc = md.fundamentals.loc[prim, "financial_currency"] if prim in md.fundamentals.index \
            and "financial_currency" in md.fundamentals.columns else None
        moeda_dem = str(fc).upper() if isinstance(fc, str) and fc else None
    pk.put("moeda_demonstrativos", moeda_dem)

    linha, motivo_linha = escolher_linha(md, params, issuer_id, moeda_dem, arq, as_of)
    ln = uni.lines.loc[linha]
    moeda = str(ln["currency"]).upper()
    pk.put("linha", linha)
    pk.put("linha_tipo", str(ln["line_type"]))
    pk.put("linha_motivo", motivo_linha)
    pk.put("moeda", moeda)
    pk.put("linhas", sorted(str(t) for t in uni.lines_for(issuer_id).index))

    # --- preço e câmbio
    preco, data_preco = ultimo_preco(md, linha, as_of)
    fonte_mkt = {"fonte": "SIMULADO" if md.is_synthetic else "YAHOO", "url": None if md.is_synthetic
                 else f"https://finance.yahoo.com/quote/{linha}", "documento":
                 "fechamento simulado (DADOS SIMULADOS)" if md.is_synthetic else
                 "fechamento oficial (base de mercado do fundo)", "data_publicacao":
                 data_preco.isoformat() if data_preco else None, "data_coleta": None,
                 "sha256": md.manifest.content_hash() if md.manifest.files else None}
    if preco is None:
        pk.put("preco", None)
        pk.falta("preco", "sem fechamento da linha até a data")
    else:
        pk.put("preco", preco, fonte_mkt, nome=f"Fechamento {linha}", unidade=f"preco:{moeda}",
               periodo=data_preco.isoformat() if data_preco else None)
    pk.put("data_preco", data_preco.isoformat() if data_preco else None)
    defas = int(np.busday_count(data_preco, as_of)) if data_preco else None
    pk.put("defasagem_preco_dias", defas)

    fx_modelo, _ = fx_usd(md, moeda, as_of)
    fx_dem, _ = fx_usd(md, moeda_dem, as_of) if moeda_dem else (None, None)
    pk.put("fx_usd_moeda", fx_modelo)
    fator = None
    status_moeda = "ok"
    if moeda_dem is None:
        status_moeda = "moeda_demonstrativos_desconhecida"
    elif moeda_dem == moeda:
        fator = 1.0
    elif fx_dem is not None and fx_modelo is not None:
        fator = fx_dem / fx_modelo
        status_moeda = "fx_corrigido"
        pk.put("fx_demonstrativos_para_modelo", fator, {**fonte_mkt, "documento": f"câmbio {moeda_dem}→{moeda} (USD por unidade)"},
               nome=f"Câmbio {moeda_dem}→{moeda}", unidade=f"fx:{moeda_dem}/{moeda}", periodo=as_of.isoformat())
    else:
        status_moeda = "cambio_indisponivel"
        pk.falta("fx_demonstrativos_para_modelo", f"câmbio {moeda_dem}→{moeda} indisponível na base")
    pk.put("fator_moeda", fator)

    # --- unidades (ações por linha e quantidade de linhas)
    apl, apl_txt = acoes_por_linha(md, params, issuer_id, linha)
    pk.put("acoes_por_linha", apl, prov_codigo(apl_txt), nome="Ações por unidade negociada",
           unidade="n")
    acoes, row_acoes = dem.valor("acoes_em_circulacao")
    if acoes is None:
        emit, row_acoes = dem.valor("acoes_emitidas")
        tes, _ = dem.valor("acoes_tesouraria")
        if emit is not None and tes is not None:
            acoes = emit - tes
        elif emit is not None:
            acoes = emit
            pk.avisos.append("ações em tesouraria indisponíveis: usadas as ações emitidas")
    unidades = _div(acoes, apl)
    fonte_un = _prov_linha(row_acoes)
    mcap_pub = None
    if linha in md.fundamentals.index and "market_cap" in md.fundamentals.columns:
        mcap_pub = _f(md.fundamentals.loc[linha, "market_cap"])
    impl = _div(mcap_pub, preco)
    tol = float(params.sec("qualidade")["unidades_tolerancia"])
    status_unid = "demonstrativos"
    if unidades is not None and impl is not None and abs(unidades / impl - 1) > tol:
        alt = _div(acoes, 1.0)
        if alt is not None and abs(alt / impl - 1) <= tol:
            unidades, status_unid = alt, "demonstrativos_em_unidades"
        else:
            pk.avisos.append(f"unidades dos demonstrativos divergem do valor de mercado público em "
                             f"{abs(unidades / impl - 1):.0%}: unidades pelo valor de mercado")
            unidades, status_unid = impl, "valor_de_mercado"
            fonte_un = {**fonte_mkt, "documento": "valor de mercado público ÷ fechamento"}
    elif unidades is None and impl is not None:
        unidades, status_unid = impl, "valor_de_mercado"
        fonte_un = {**fonte_mkt, "documento": "valor de mercado público ÷ fechamento"}
    if unidades is None:
        pk.falta("unidades", "quantidade de ações indisponível (demonstrativos e valor de mercado)")
    else:
        pk.put("unidades", unidades, fonte_un, nome=f"Unidades em circulação ({linha})",
               unidade="acoes")
    pk.put("status_unidades", status_unid)

    # --- demonstrativos (convertidos para a moeda do modelo)
    tem_dem = not dem.vazio
    pk.put("tem_demonstrativos", tem_dem)
    if not tem_dem:
        pk.lacunas.append(lacuna("demonstrativos", "sem demonstrativos públicos até a data"))
    itens = {}
    periodos: dict[str, pd.Timestamp] = {}
    estimados = False
    for item in FLUXOS + ESTOQUES:
        if item in ("acoes_emitidas", "acoes_tesouraria", "acoes_em_circulacao"):
            continue
        v, row = dem.valor(item)
        if v is None:
            continue
        vv = _conv(v, fator)
        if vv is None:
            continue
        per = None if row is None else (f"{FREQ_PT.get(str(row.get('freq')), row.get('freq'))} até "
                                        f"{pd.Timestamp(row['period_end']).date()}")
        itens[item] = vv
        if row is not None:
            periodos[item] = pd.Timestamp(row["period_end"])
        prov = _prov_linha(row)
        estimados = estimados or bool(prov.get("data_estimada"))
        pk.put(f"t.{item}", vv, prov, nome=rotulo(item), unidade=f"total:{moeda}", periodo=per)
        if prov.get("data_estimada"):
            pk.tabela[-1]["data_estimada"] = True
    for x in dem.defasados:
        it = x.split(" ")[0]
        pk.lacunas.append(lacuna(it, f"item defasado em relação ao último balanço: {rotulo(it)} {x[len(it):].strip()}"))
    # mesma data-base: fluxos de 12 meses × último balanço
    estoque_ref = max((periodos[k] for k in ("patrimonio_controladores", "patrimonio_liquido") if k in periodos),
                      default=None)
    fluxo_ref = next((periodos[k] for k in ("lucro_liquido_controladores", "lucro_liquido", "receita", "ebit")
                      if k in periodos), None)
    defas_fluxos = None
    if estoque_ref is not None and fluxo_ref is not None:
        defas_fluxos = int((estoque_ref - fluxo_ref).days)
        if defas_fluxos > DEFASAGEM_AVISO_DIAS:
            msg = (f"fluxos de 12 meses até {fluxo_ref.date()} contra balanço de {estoque_ref.date()} "
                   f"({defas_fluxos} dias): ROE, ROIC, payout e LPA dos últimos 12 meses com datas-base distintas")
            pk.avisos.append(msg)
            pk.lacunas.append(lacuna("defasagem_fluxos", msg))
    pk.put("defasagem_fluxos_dias", defas_fluxos)
    pk.put("receita_ano_anterior", _conv(dem.ttm_ano_anterior("receita"), fator))
    hist = {}
    for item in HIST_ITENS:
        a = dem.anual(item)
        if a:
            f_item = 1.0 if item == "acoes_em_circulacao" else fator
            hist[item] = {str(k): r6(_conv(v, f_item)) for k, v in sorted(a.items())}
    pk.put("historico", hist)
    datas_pub = pd.to_datetime(dem.df["data_publicacao"], errors="coerce") if tem_dem else pd.Series(dtype="datetime64[ns]")
    est_col = dem.df["pit_estimado"].map(_bool) if tem_dem and "pit_estimado" in dem.df.columns else pd.Series(dtype=bool)
    pk.put("datas_estimadas", bool(estimados or (len(est_col) and est_col.any())))
    pk.put("pit_ok", bool(tem_dem and datas_pub.notna().all() and (datas_pub <= pd.Timestamp(as_of)).all()
                          and not pk.v["datas_estimadas"]))
    pk.put("max_data_publicacao", None if datas_pub.dropna().empty else datas_pub.max().date().isoformat())

    # --- por ação (moeda do modelo, por unidade da linha)
    pl_ctrl = itens.get("patrimonio_controladores", itens.get("patrimonio_liquido"))
    lucro = itens.get("lucro_liquido_controladores", itens.get("lucro_liquido"))
    bvps = _div(pl_ctrl, unidades)
    eps_ttm = _div(lucro, unidades)
    fonte_yh = {"fonte": "SIMULADO" if md.is_synthetic else "YAHOO",
                "url": None if md.is_synthetic else f"https://finance.yahoo.com/quote/{linha}/key-statistics",
                "documento": ("retrato simulado (DADOS SIMULADOS)" if md.is_synthetic
                              else "retrato público Yahoo Finance (não point-in-time)"), "data_publicacao": None,
                "data_coleta": md.manifest.created_at.isoformat(), "sha256": None}
    if bvps is None and linha in md.fundamentals.index and moeda_dem == moeda:
        bv = _f(md.fundamentals.loc[linha].get("book_value"))
        if bv is not None:
            bvps = bv
            pk.avisos.append("patrimônio por ação do retrato público" + (" simulado" if md.is_synthetic else " Yahoo Finance")
                             + " (sem demonstração financeira)")
            pk.put("bvps_fonte_yahoo", True)
    if bvps is None:
        pk.falta("bvps", "patrimônio por ação indisponível")
    else:
        pk.put("bvps", bvps, pk.fontes.get("t.patrimonio_controladores", fonte_yh),
               nome="Patrimônio por ação", unidade=f"preco:{moeda}")
    if eps_ttm is None:
        pk.falta("eps_ttm", "lucro dos últimos 12 meses indisponível")
    else:
        pk.put("eps_ttm", eps_ttm, pk.fontes.get("t.lucro_liquido_controladores"),
               nome="LPA últimos 12 meses", unidade=f"preco:{moeda}")

    # --- consenso público (Yahoo Finance)
    _consenso(md, dados, params, pk, issuer_id, linha, moeda, moeda_dem, preco, unidades, eps_ttm,
              itens, as_of)
    # --- dividendos
    _dividendos(md, dados, pk, issuer_id, linha, moeda, unidades, itens, as_of)

    # --- dívida e estrutura de capital (moeda do modelo)
    dbruta = itens.get("divida_bruta")
    caixa = itens.get("caixa")
    aplic = itens.get("aplicacoes_cp")
    arr = itens.get("arrendamentos")
    if dbruta is not None and caixa is not None:
        comp = ["dívida bruta"]
        dl = dbruta - caixa
        if arr is not None:
            dl += arr
            comp.append("+ arrendamentos")
        comp.append("− caixa")
        if aplic is not None:
            dl -= aplic
            comp.append("− aplicações de curto prazo")
        pk.put("divida_liquida", dl, prov_codigo(" ".join(comp) + " (componentes publicados)"),
               nome="Dívida líquida", unidade=f"total:{moeda}")
    elif itens.get("divida_liquida") is not None:
        pk.put("divida_liquida", itens["divida_liquida"], pk.fontes.get("t.divida_liquida"),
               nome="Dívida líquida (reportada)", unidade=f"total:{moeda}")
    elif not pk.v["financeira"]:
        pk.falta("divida_liquida", "dívida bruta ou caixa indisponível")
    mino = itens.get("participacao_minoritarios")
    if mino is not None:
        pk.put("minoritarios", mino, pk.fontes.get("t.participacao_minoritarios"))
    else:
        plt, plc = itens.get("patrimonio_liquido"), itens.get("patrimonio_controladores")
        mesma_data = ("patrimonio_liquido" in periodos and "patrimonio_controladores" in periodos
                      and periodos["patrimonio_liquido"] == periodos["patrimonio_controladores"])
        if plt is not None and plc is not None and mesma_data and plt - plc >= 0:
            pk.put("minoritarios", plt - plc, prov_codigo("patrimônio líquido total − patrimônio dos controladores "
                                                          "(mesmo balanço)"),
                   nome="Participação de não controladores (derivada)", unidade=f"total:{moeda}")
        else:
            pk.put("minoritarios", None)
            if not pk.v["financeira"]:
                pk.lacunas.append(lacuna("minoritarios", "participação de não controladores não publicada no último "
                                                         "balanço: métodos pelo valor da firma indisponíveis"))
    mcap = None if preco is None or unidades is None else preco * unidades
    pk.put("valor_mercado", mcap, prov_codigo("fechamento × unidades em circulação"),
           nome="Valor de mercado", unidade=f"total:{moeda}")
    pk.put("divida_bruta", dbruta)
    pk.put("arrendamentos", arr)
    d_total = None if dbruta is None else dbruta + (arr if arr is not None else 0.0)
    de = _div(d_total, mcap)
    pk.put("d_e_mercado", de)

    # --- crescimento
    rec, rec_ant = itens.get("receita"), pk.v.get("receita_ano_anterior")
    g_hist = None if rec is None or rec_ant is None or rec_ant <= 0 else rec / rec_ant - 1
    if pk.v["financeira"]:
        g_hist = None
    elif g_hist is not None and not LIMITES_G_HIST[0] <= g_hist <= LIMITES_G_HIST[1]:
        pk.lacunas.append(lacuna("g_receita_historico", f"crescimento histórico da receita de {pct(g_hist, 1)} fora "
                                 "da faixa plausível (provável efeito contábil): não usado"))
        g_hist = None
    pk.put("g_receita_historico", g_hist)

    # --- β e volatilidade (do nosso histórico de preços públicos)
    cc = params.cc
    ref = str(cc["beta"]["referencia"])
    b, n = beta_regressao(md, linha, ref, as_of, int(cc["beta"]["regressao_semanas"]),
                          int(cc["beta"]["regressao_min_semanas"]))
    pk.put("beta_regressao", b, prov_codigo(f"MQO de {n} retornos semanais em USD de {linha} contra {ref}"))
    pk.put("beta_regressao_semanas", n)
    pk.put("beta_u_setor", beta_setor.beta_u_global, {
        "fonte": "DAMODARAN", "url": beta_setor.url, "documento": f"β desalavancado (corrigido por caixa) — {beta_setor.industria}",
        "data_publicacao": beta_setor.data_ref, "data_coleta": None, "sha256": params.arquivos.get("cobertura/betas_setor.csv")},
        nome=f"β desalavancado setorial ({beta_setor.industria})", unidade="n")
    vol = vol_realizada(md, linha, as_of, int(params.sec("cenarios")["vol_janela_pregoes"]))
    pk.put("vol_12m", vol, prov_codigo(f"desvio-padrão anualizado dos log-retornos diários de {linha}"))
    pk.put("adtv_usd", adtv_usd(md, linha, as_of))

    # --- eventos e free float
    ev = dados.eventos
    prox = None
    if not ev.empty:
        e = ev[(ev["issuer_id"] == issuer_id) & (pd.to_datetime(ev["data"], errors="coerce") > pd.Timestamp(as_of))]
        e = e[e["tipo"].astype(str) == "resultado"] if "tipo" in e.columns else e
        if not e.empty:
            e = e.sort_values("data")
            prox = {"data": pd.Timestamp(e.iloc[0]["data"]).date().isoformat(),
                    "estimada": bool(e.iloc[0].get("estimada", False)),
                    "fonte": str(e.iloc[0].get("fonte") or "")}
    pk.put("proximo_resultado", prox)
    ff = dados.free_float
    ffv = None
    if not ff.empty:
        s = ff[ff["issuer_id"] == issuer_id]
        if not s.empty:
            ffv = _f(s.iloc[-1]["free_float_pct"])
    pk.put("free_float", ffv)

    pk.put("status_moeda", status_moeda)
    pk.put("avisos", list(pk.avisos))
    pk.put("lacunas", list(pk.lacunas))
    pk.put("fontes", dict(sorted(pk.fontes.items())))
    pk.put("tabela_insumos", list(pk.tabela))
    return pk.v


def _consenso(md: MarketData, dados: DadosPublicos, params: ParametrosCobertura, pk: _Pacote,
              issuer_id: str, linha: str, moeda: str, moeda_dem: str | None, preco: float | None,
              unidades: float | None, eps_ttm: float | None, itens: dict[str, float],
              as_of: date) -> None:
    con = dados.consenso
    lines = md.universe.lines
    row = None
    tick = linha
    if not con.empty:
        sub = con[con["ticker"] == linha]
        if sub.empty:
            for t in md.universe.lines_for(issuer_id).index:
                s2 = con[con["ticker"] == t]
                if not s2.empty and _f(s2.iloc[-1].get("eps_fy1")) is not None:
                    sub, tick = s2, str(t)
                    break
        if not sub.empty:
            row = sub.iloc[-1]
    fonte = {"fonte": "SIMULADO" if md.is_synthetic else "YAHOO",
             "url": None if md.is_synthetic else f"https://finance.yahoo.com/quote/{tick}/analysis",
             "documento": "consenso simulado (DADOS SIMULADOS)" if md.is_synthetic else "consenso público Yahoo Finance",
             "data_publicacao": None,
             "data_coleta": None if row is None else (row.get("data_coleta").isoformat()
                                                      if hasattr(row.get("data_coleta"), "isoformat")
                                                      else row.get("data_coleta")),
             "sha256": None}
    if row is None:
        pk.falta("eps_fy1", "sem consenso público de LPA")
        pk.put("consenso", None)
        return
    # conversão por paridade quando o consenso é de outra linha do emissor
    fator_linha = 1.0
    if tick != linha:
        a_ln, _ = acoes_por_linha(md, params, issuer_id, linha)
        a_tk, _ = acoes_por_linha(md, params, issuer_id, tick)
        fx_a, _ = fx_usd(md, str(lines.loc[tick, "currency"]), as_of)
        fx_b, _ = fx_usd(md, moeda, as_of)
        fator_linha = None if fx_a is None or fx_b is None else (fx_a / fx_b) * (a_ln / a_tk)
        pk.avisos.append(f"consenso da linha {tick} convertido por paridade para {linha}")
    e1 = _conv(_f(row.get("eps_fy1")), fator_linha)
    e2 = _conv(_f(row.get("eps_fy2")), fator_linha)
    status = "ok"
    # moeda das estimativas informada pela fonte (consenso de ADR costuma vir na moeda do balanço)
    m_est = row.get("moeda_estimativas")
    m_est = str(m_est).upper() if isinstance(m_est, str) and len(m_est) == 3 else None
    m_lin = str(lines.loc[tick, "currency"]).upper()
    if e1 is not None and m_est is not None and m_est != m_lin:
        fx_e, _ = fx_usd(md, m_est, as_of)
        fx_l, _ = fx_usd(md, moeda, as_of)
        if fx_e is None or fx_l is None:
            pk.avisos.append(f"LPA de consenso em {m_est} sem câmbio na base: descartado")
            e1 = e2 = None
            status = "cambio_indisponivel"
        else:
            f_est = fx_e / fx_l
            e1, e2 = e1 * f_est, (None if e2 is None else e2 * f_est)
            status = "fx_corrigido"
            pk.avisos.append(f"LPA de consenso em {m_est} convertido para {moeda}")
    def plausivel(e: float | None) -> bool:
        """LPA coerente em moeda e unidade: contra o LPA dos demonstrativos (|razão| em [0,2; 5])
        ou, sem ele, rendimento |LPA|/P0 em [0,05%; 100%] (prejuízo e lucro baixo são plausíveis)."""
        if e is None or preco is None or preco <= 0:
            return True
        if eps_ttm is not None and abs(eps_ttm) > 0.01 * preco:
            return 0.2 <= abs(e / eps_ttm) <= 5.0
        return 0.0005 <= abs(e) / preco <= 1.0

    if e1 is not None and not plausivel(e1):
        # unidade diferente (LPA por ação local num ADR, ou por ADR numa linha local) ou moeda
        a_ln, _ = acoes_por_linha(md, params, issuer_id, linha)
        fx_d, _ = fx_usd(md, moeda_dem, as_of) if moeda_dem else (None, None)
        fx_m, _ = fx_usd(md, moeda, as_of)
        cands = [c for c in ((a_ln if a_ln != 1.0 else None), (1.0 / a_ln if a_ln != 1.0 else None),
                             (fx_d / fx_m if fx_d and fx_m and moeda_dem != moeda else None)) if c]
        ok = next((c for c in cands if plausivel(e1 * c)), None)
        if ok is not None:
            e1, e2 = e1 * ok, (None if e2 is None else e2 * ok)
            status = "unidade_corrigida"
            pk.avisos.append("LPA de consenso em unidade ou moeda diferente da linha: convertido")
        else:
            status = "moeda_inconsistente"
            pk.avisos.append("LPA de consenso incoerente com o lucro dos demonstrativos: descartado")
            e1 = e2 = None
    if e1 is None:
        pk.falta("eps_fy1", "consenso de LPA indisponível ou inconsistente")
    else:
        pk.put("eps_fy1", e1, fonte, nome="LPA de consenso (ano 1)", unidade=f"preco:{moeda}")
    if e2 is not None:
        pk.put("eps_fy2", e2, fonte, nome="LPA de consenso (ano 2)", unidade=f"preco:{moeda}")
    r1, r2 = _f(row.get("receita_fy1")), _f(row.get("receita_fy2"))
    g1 = None
    rec = itens.get("receita")
    if pk.v.get("financeira"):  # receita de intermediação financeira não comparável entre fontes
        r1 = r2 = None
    if r1 is not None and rec is not None and rec > 0:
        rec_fin = rec / (pk.v.get("fator_moeda") or 1.0)
        razao = r1 / rec_fin
        if 0.5 <= razao <= 2.0:
            g1 = razao - 1
    g2 = None if r1 is None or r2 is None or r1 <= 0 or not (0.5 <= r2 / r1 <= 2.0) else r2 / r1 - 1
    pk.put("g_receita_fy1", g1)
    pk.put("g_receita_fy2", g2)
    alvo = _conv(_f(row.get("alvo_medio")), fator_linha)
    cons = {
        "ticker": tick, "alvo_medio": r6(alvo), "alvo_mediano": r6(_conv(_f(row.get("alvo_mediano")), fator_linha)),
        "alvo_alto": r6(_conv(_f(row.get("alvo_alto")), fator_linha)),
        "alvo_baixo": r6(_conv(_f(row.get("alvo_baixo")), fator_linha)),
        "n_alvo": _f(row.get("n_analistas_alvo")), "n_eps": _f(row.get("n_analistas_eps")),
        "recomendacao": r6(_f(row.get("recomendacao_media"))), "status_lpa": status,
    }
    up = _div(alvo, preco)
    lims = params.sec("qualidade")["upside_limites"]
    cons["upside"] = None if up is None else r6(up - 1)
    cons["plausivel"] = bool(up is not None and lims[0] <= up - 1 <= lims[1])
    if up is not None and not cons["plausivel"]:
        pk.avisos.append("preço-alvo de consenso fora da faixa plausível (provável unidade/moeda): não comparado")
    pk.put("consenso", cons, fonte)


def _dividendos(md: MarketData, dados: DadosPublicos, pk: _Pacote, issuer_id: str, linha: str,
                moeda: str, unidades: float | None, itens: dict[str, float], as_of: date) -> None:
    div = dados.dividendos
    ini = pd.Timestamp(as_of) - pd.Timedelta(days=365)
    fonte = {"fonte": "SIMULADO" if md.is_synthetic else "YAHOO",
             "url": None if md.is_synthetic else f"https://finance.yahoo.com/quote/{linha}/history?filter=div",
             "documento": "proventos por data ex (últimos 12 meses)" + (" — DADOS SIMULADOS" if md.is_synthetic else ""),
             "data_publicacao": None,
             "data_coleta": None, "sha256": None}
    if not div.empty:
        sub = div[div["ticker"] == linha].copy()
        if not sub.empty:
            dex = pd.to_datetime(sub["data_ex"], errors="coerce")
            janela = sub[(dex > ini) & (dex <= pd.Timestamp(as_of))]
            vals = pd.to_numeric(janela["valor_por_acao"], errors="coerce").dropna()
            dps = float(vals.sum()) if len(vals) else 0.0
            pk.put("dps_12m", dps, fonte, nome="Dividendos por ação (12 meses)", unidade=f"preco:{moeda}")
            pk.put("dps_fonte", "proventos")
            return
    dp = itens.get("dividendos_pagos")
    if dp is not None and unidades:
        pk.put("dps_12m", abs(dp) / unidades, pk.fontes.get("t.dividendos_pagos"),
               nome="Dividendos por ação (DFC, 12 meses)", unidade=f"preco:{moeda}")
        pk.put("dps_fonte", "dfc")
        return
    pk.falta("dps_12m", "sem histórico de proventos nem dividendos pagos no DFC")
    pk.put("dps_fonte", None)


# ============================================================ soma das partes (holdings)

def preparar_soma_partes(md: MarketData, params: ParametrosCobertura, pacote: dict[str, Any],
                         as_of: date) -> None:
    """Acrescenta ao pacote da holding o NAV de participações listadas e a razão histórica
    (valor de mercado da holding ÷ NAV) em base semanal, que dá o desconto da holding.

    A janela da mediana começa na data ``desde`` da curadoria (última mudança do conjunto de
    participações), quando informada: a mesma composição de hoje aplicada a um período em que a
    holding tinha outras participações distorceria a razão histórica."""
    iid = pacote["issuer_id"]
    cfg = params.sotp.get("holdings", {}).get(iid)
    if not cfg:
        pacote["soma_partes"] = None
        pacote["lacunas"].append(lacuna("soma_partes", "holding sem participações curadas"))
        return
    sp = params.sec("soma_partes")
    fund = md.fundamentals
    moeda = pacote["moeda"]
    fx_m, _ = fx_usd(md, moeda, as_of)
    hold_line = pacote["linha"]
    mcap_h = pacote.get("valor_mercado")
    if mcap_h is None and hold_line in fund.index:
        mcap_h = _f(fund.loc[hold_line].get("market_cap"))
    partes = []
    series = []
    ok = True
    for p in cfg.get("participacoes", []):
        sub = str(p["emissor"])
        if sub not in md.universe.issuers.index:
            ok = False
            partes.append({"emissor": sub, "motivo": "fora do universo"})
            continue
        st = str(md.universe.issuers.loc[sub, "primary_ticker"])
        px, dpx = ultimo_preco(md, st, as_of)
        mc = _f(fund.loc[st].get("market_cap")) if st in fund.index else None
        ccy = str(md.universe.lines.loc[st, "currency"])
        fx_s, _ = fx_usd(md, ccy, as_of)
        if px is None or mc is None or fx_s is None or fx_m is None:
            ok = False
            partes.append({"emissor": sub, "motivo": "preço, valor de mercado ou câmbio indisponível"})
            continue
        valor = float(p["fracao"]) * mc * fx_s / fx_m
        partes.append({"emissor": sub, "linha": st, "fracao": r6(float(p["fracao"])),
                       "valor_mercado": r6(mc), "moeda": ccy, "valor_participacao": r6(valor),
                       "conferido": bool(p.get("conferido", False)),
                       "fonte": {"fonte": "CONFIG", "url": p.get("url"), "documento": p.get("documento"),
                                 "data_publicacao": None, "data_coleta": None,
                                 "sha256": params.arquivos.get("cobertura/sotp.yaml")}})
        s = _serie_usd_semanal(md, st, as_of)
        if not s.empty:
            series.append((s / s.iloc[-1]) * valor * fx_m)  # valor em USD ao longo do tempo
    nav = sum(p["valor_participacao"] for p in partes if "valor_participacao" in p) if ok else None
    hs = _serie_usd_semanal(md, hold_line, as_of)
    razao_med = None
    n_sem = 0
    if ok and series and not hs.empty and mcap_h is not None and nav:
        nav_usd = pd.concat(series, axis=1).dropna().sum(axis=1)
        mh_usd = (hs / hs.iloc[-1]) * mcap_h * fx_m
        r = (mh_usd / nav_usd).dropna()
        r = r[r.index >= pd.Timestamp(as_of) - pd.DateOffset(years=int(sp["desconto_anos"]))]
        if cfg.get("desde"):
            r = r[r.index >= pd.Timestamp(str(cfg["desde"]))]
        n_sem = len(r)
        if n_sem >= int(sp["desconto_min_semanas"]):
            razao_med = float(r.median())
    pacote["soma_partes"] = {
        "partes": partes, "nav": r6(nav), "valor_mercado_holding": r6(mcap_h),
        "razao_atual": r6(_div(mcap_h, nav)), "razao_mediana": r6(razao_med), "semanas": n_sem,
        "desconto_reserva": float(sp["desconto_reserva"]), "nota": cfg.get("nota", ""),
        "desde": None if not cfg.get("desde") else str(cfg["desde"]),
        "conferido": all(p.get("conferido", False) for p in partes if "fracao" in p),
    }
    if not ok:
        pacote["lacunas"].append(lacuna("soma_partes", "participação sem preço ou valor de mercado"))


def preparar(md: MarketData, dados: DadosPublicos, params: ParametrosCobertura,
             issuer_ids: Iterable[str], as_of: date) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for iid in sorted(issuer_ids):
        p = preparar_emissor(md, dados, params, iid, as_of)
        if p["arquetipo"] == "holding":
            preparar_soma_partes(md, params, p, as_of)
        out[iid] = p
    return out


def taxa_publica(dados: DadosPublicos, md: MarketData, serie: str, as_of: date) -> tuple[float | None, str | None, dict[str, Any]]:
    """Último valor público de ``serie`` até ``as_of`` (taxas públicas; depois a base de mercado)."""
    t = dados.taxas
    if not t.empty:
        s = t[(t["serie"] == serie)].copy()
        s["data"] = pd.to_datetime(s["data"], errors="coerce")
        s = s[s["data"] <= pd.Timestamp(as_of)].sort_values("data")
        if not s.empty:
            r = s.iloc[-1]
            fonte = str(r.get("fonte") or "FRED")
            sim = fonte == "SIMULADO" or md.is_synthetic
            return _f(r["valor"]), r["data"].date().isoformat(), {
                "fonte": "SIMULADO" if sim else fonte.split(":")[0],
                "url": "https://fred.stlouisfed.org/series/DGS10" if serie == "USD_10Y" and not sim else None,
                "documento": f"série simulada {serie} (DADOS SIMULADOS)" if sim else f"série pública {serie}",
                "data_publicacao": r["data"].date().isoformat(), "data_coleta": None, "sha256": None}
    if serie in md.rates.columns:
        s = md.rates[serie].loc[:pd.Timestamp(as_of)].dropna()
        if len(s):
            return float(s.iloc[-1]), s.index[-1].date().isoformat(), {
                "fonte": "SIMULADO" if md.is_synthetic else "FRED", "url": None,
                "documento": f"série {serie} da base de mercado" + (" (DADOS SIMULADOS)" if md.is_synthetic else ""),
                "data_publicacao": s.index[-1].date().isoformat(), "data_coleta": None, "sha256": None}
    return None, None, prov_codigo(f"série {serie} indisponível")


__all__ = ["Demonstrativos", "acoes_por_linha", "adtv_usd", "beta_regressao", "escolher_linha",
           "fx_usd", "preparar", "preparar_emissor", "preparar_soma_partes", "taxa_publica",
           "ultimo_preco", "vol_realizada"]
