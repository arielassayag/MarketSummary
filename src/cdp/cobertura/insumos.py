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
  receita de construção de concessões) fica ausente, com lacuna. A receita de consenso é
  convertida da sua própria moeda (``moeda_receita``) para a das demonstrações antes da razão.
- **Contagem de ações conciliada**: demonstrações (÷ ações por unidade), valor de mercado público
  ÷ fechamento e, no Brasil, o capital social do Formulário de Referência (CVM). Vale a contagem
  sustentada por duas das três fontes a ±10% (preferência: demonstrações, depois a oficial);
  sem par ⇒ portão G13c bloqueia. Sem a fonte oficial, demonstrações e mercado a ±25%; divergência
  ⇒ contagem do mercado com aviso (confiança C). Nunca se reinterpreta a contagem das demonstrações
  como unidades negociadas só porque o valor de mercado de uma fonte de dados a confirma.
- **Em conferência na fonte**: uma linha de demonstrativo sem valor marcada "conferência:" pela
  camada pública, mais recente que o último valor válido do item, torna o item ausente (lacuna
  "em conferência na fonte"); o valor do período anterior nunca é usado em silêncio.
- **Fluxos de 12 meses**: TTM publicado; senão soma dos 4 últimos trimestres consecutivos; senão
  último exercício + trimestres do exercício corrente − os mesmos trimestres do exercício anterior.
- **Consolidado × individual**: por (item, frequência, data-base) — o consolidado prevalece onde existe;
  períodos só individuais entram, registrados na proveniência (nunca um consolidado mais antigo no
  lugar de um individual mais recente); idade do último balanço e dos fluxos contra a data (G19).
- **Consenso**: a linha de mais analistas de LPA (conferida contra a linha de valuation) e o número de
  analistas; calendário do "ano 1" pelo encerramento do exercício do emissor.
- **Proventos**: por ação, 12 meses e por ano-calendário (payout dos acionistas pela mediana anual).
- **Receita de construção** (utilidades e concessões): fora da base quando reconcilia o consenso.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from ..data.dimensoes_contabeis import CAMPOS, compativeis, dimensoes
from ..data.publico_contexto_documental import contexto_composicao, contexto_documental
from ..market import MarketData
from .disponibilidade_demonstrativos import _grupos
from .fontes import DadosPublicos
from .formato import num, pct, r6
from .parametros import Arquetipo, ParametrosCobertura, arquetipo_padrao
from .passos import prov_codigo, prov_curadoria, prov_dict

FLUXOS = ("receita", "lucro_bruto", "ebit", "ebitda", "d_a", "resultado_financeiro", "lucro_antes_ir",
          "ir_csll", "lucro_liquido", "lucro_liquido_controladores", "cfo", "capex", "fcf",
          "dividendos_pagos", "recompras", "margem_financeira", "receita_servicos", "despesa_pdd",
          "arrendamentos_pagos", "receita_construcao", "adicoes_direito_uso", "depreciacao_direito_uso",
          "d_a_dfc", "variacao_capital_giro_operacional", "juros_pagos_operacionais")
ESTOQUES = ("caixa", "aplicacoes_cp", "divida_bruta", "divida_liquida", "arrendamentos",
            "patrimonio_liquido", "patrimonio_controladores", "participacao_minoritarios",
            "ativo_total", "acoes_emitidas", "acoes_tesouraria", "acoes_em_circulacao",
            "provisao_credito", "carteira_credito")
HIST_ITENS = ("receita", "ebit", "lucro_liquido_controladores", "patrimonio_controladores",
              "acoes_em_circulacao", "cfo", "capex", "arrendamentos_pagos", "dividendos_pagos",
              "adicoes_direito_uso", "depreciacao_direito_uso", "d_a_dfc",
              "variacao_capital_giro_operacional", "arrendamentos")
SEMANAS_ANO = 52
DEFASAGEM_AVISO_DIAS = 100
NOTA_CONFERENCIA = "conferência"
LIMITES_G_HIST = (-0.20, 0.30)

ROTULOS = {
    "receita": "receita", "lucro_bruto": "lucro bruto", "ebit": "EBIT", "ebitda": "EBITDA",
    "d_a": "depreciação e amortização", "resultado_financeiro": "resultado financeiro",
    "lucro_antes_ir": "lucro antes do imposto de renda", "ir_csll": "imposto de renda e contribuição social",
    "lucro_liquido": "lucro líquido", "lucro_liquido_controladores": "lucro líquido dos controladores",
    "cfo": "fluxo de caixa das operações", "capex": "investimento em ativo fixo e intangível (capex)",
    "fcf": "fluxo de caixa livre", "dividendos_pagos": "dividendos e juros sobre capital pagos",
    "recompras": "recompra de ações", "margem_financeira": "margem financeira",
    "arrendamentos_pagos": "pagamentos de passivos de arrendamento (DFC)",
    "adicoes_direito_uso": "adições de ativos de direito de uso",
    "depreciacao_direito_uso": "depreciação de ativos de direito de uso",
    "d_a_dfc": "depreciação e amortização restituídas na DFC",
    "variacao_capital_giro_operacional": "variação do capital de giro operacional (uso de caixa positivo)",
    "juros_pagos_operacionais": "juros pagos nas atividades operacionais",
    "receita_construcao": "receita de construção da infraestrutura de concessão (DVA)",
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
        self.em_conferencia: list[tuple[str, pd.Timestamp]] = []
        self._conf: dict[str, pd.Timestamp] = {}
        if not d.empty:
            if any(k in d for k in CAMPOS):
                for _, row in d.iterrows():
                    dimensoes(row)
            d["period_end"] = pd.to_datetime(d["period_end"], errors="coerce")
            d["data_publicacao"] = pd.to_datetime(d["data_publicacao"], errors="coerce")
            d["value"] = pd.to_numeric(d["value"], errors="coerce")
            if "escala" in d.columns:
                esc = pd.to_numeric(d["escala"], errors="coerce").fillna(1.0)
                d["value"] = d["value"] * esc
            if "consolidado" in d.columns:
                # consolidado × individual por (item, frequência, data-base): o consolidado prevalece
                # no período em que existe; períodos só com as demonstrações individuais (companhia
                # que deixou de consolidar) entram como individuais, registradas na proveniência —
                # nunca um consolidado mais antigo no lugar de um individual mais recente
                cons = d["consolidado"].astype(str).str.lower().isin(["true", "1"])
                d = d.assign(_cons=cons.values)
                tem = d.groupby(["item", "freq", "period_end"], dropna=False)["_cons"].transform("any")
                d = d[d["_cons"] | ~tem].drop(columns="_cons")
            if "demonstrativo" in d.columns:
                d = d[d["demonstrativo"].astype(str) != "DFP_IND"]
            if "nota" in d.columns:  # marcadores "em conferência na fonte" (valor ausente, nunca palpite)
                marc = d[d["value"].isna() & d["period_end"].notna()
                         & d["nota"].astype(str).str.startswith(NOTA_CONFERENCIA)]
                for item, g in marc.groupby("item"):
                    self._conf[str(item)] = g["period_end"].max()
            d = d.dropna(subset=["period_end", "value"])
            d = pd.concat([d, self._ttm_derivado(d)], ignore_index=True)
        self.df = d
        ref = d[d["item"].isin(self.ITENS_REFERENCIA)]["period_end"].max() if not d.empty else None
        self.ref = None if ref is None or pd.isna(ref) else ref

    @staticmethod
    def _ttm_derivado(d: pd.DataFrame) -> pd.DataFrame:
        """Fluxos de 12 meses derivados em código quando a fonte não traz o TTM mais recente:
        (1) soma dos 4 últimos trimestres consecutivos; (2) senão, identidade ``anual + acumulado
        do exercício corrente − acumulado do mesmo período do exercício anterior`` (trimestres do
        exercício corrente consecutivos a partir do fim do último exercício e os mesmos trimestres
        um ano antes, todos publicados)."""
        def observados(linhas: list[pd.Series]) -> bool:
            return any(str(r.get('disponibilidade_tipo')) == 'recepcao_observada' for r in linhas)

        def tempo(linhas: list[pd.Series]) -> dict:
            if not observados(linhas):
                return {}
            out = {'disponibilidade_tipo': 'recepcao_observada'}
            for key in ('data_publicacao', 'disponivel_desde', 'data_recebimento_documento', 'received_date'):
                values = [r.get(key) for r in linhas]
                from ..data.publico_fatos import (
                    _max_disponibilidade_observada,
                    _max_recebimento_observado,
                )

                out[key] = (_max_recebimento_observado(values) if key == "received_date" else
                            _max_disponibilidade_observada(values) if key == "disponivel_desde" else
                            None if any(pd.isna(v) for v in values) else max(values))
            return out

        def componentes(linhas: list[tuple[pd.Series, float]]) -> str:
            return json.dumps([{"item": str(r["item"]), "freq": str(r["freq"]),
                                "period_end": pd.Timestamp(r["period_end"]).date().isoformat(),
                                "valor": float(r["value"]), "coeficiente": sinal,
                                "fonte": _prov_linha(r), **dimensoes(r), **contexto_documental(r)} for r, sinal in linhas], ensure_ascii=False)

        def comparaveis(linhas: list[pd.Series]) -> bool:
            if not compativeis(linhas):
                return False
            if any(dimensoes(row) for row in linhas):
                for row in linhas:
                    try:
                        for _, grupo in _grupos(row):
                            if not isinstance(grupo, list) or not grupo or not compativeis([row, *grupo]):
                                return False
                    except (TypeError, ValueError, AttributeError):
                        return False
            moedas = {str(r.get("currency")) for r in linhas}
            bases = {_base_linha(r) for r in linhas}
            conceitos = [set(re.findall(r"semantica_fluxo=([^;\s]*)", str(r.get("nota", ""))))
                         for r in linhas]
            if any(conceitos):
                # Uma quebra comprovada no provedor não pode ser recomposta aqui. Exige
                # conceito conhecido em cada componente; sem marcadores mantém o legado.
                if any(len(c) != 1 for c in conceitos):
                    return False
                unicos = set.union(*conceitos)
                if len(unicos) != 1 or not unicos <= {"receita_dre", "resultado_liquido_seguros"}:
                    return False
            return len(moedas) == 1 and bool(re.fullmatch(r"[A-Z]{3}", next(iter(moedas)))) and len(bases) == 1 \
                and next(iter(bases)) in ("consolidado", "individual")

        rows = []
        for item in FLUXOS:
            q = d[(d["item"] == item) & (d["freq"] == "Q")].drop_duplicates(
                "period_end", keep="last").sort_values("period_end")
            if q.empty:
                continue
            outros = d[(d["item"] == item) & d["freq"].isin(["TTM", "A"])]
            ult_outros = outros["period_end"].max() if not outros.empty else None
            if len(q) >= 4:
                ult4 = q.tail(4)
                gaps = ult4["period_end"].diff().dropna().dt.days
                fim = ult4["period_end"].iloc[-1]
                if gaps.between(80, 100).all():
                    if (ult_outros is None or ult_outros < fim) and comparaveis([rr for _, rr in ult4.iterrows()]):
                        r = ult4.iloc[-1].to_dict()
                        r.update({"freq": "TTM", "value": float(ult4["value"].sum()),
                                  "documento": f"{r.get('documento') or ''} (soma dos 4 últimos trimestres)".strip(),
                                  "data_publicacao": ult4["data_publicacao"].max(),
                                  "componentes_fluxo": componentes([(rr, 1.0) for _, rr in ult4.iterrows()]),
                                  **tempo([rr for _, rr in ult4.iterrows()])})
                        r.update(contexto_composicao(json.loads(r["componentes_fluxo"])))
                        rows.append(r)
                    continue
            a = d[(d["item"] == item) & (d["freq"] == "A")].sort_values("period_end")
            if a.empty:
                continue
            fye = a["period_end"].iloc[-1]
            cur = q[q["period_end"] > fye]
            if cur.empty:
                continue
            fim = cur["period_end"].iloc[-1]
            if ult_outros is not None and ult_outros >= fim:
                continue
            esperado = [pd.Timestamp(fye) + pd.offsets.MonthEnd(3 * k) for k in range(1, len(cur) + 1)]
            if [pd.Timestamp(x) for x in cur["period_end"]] != esperado:
                continue
            ant = []
            linhas_ant = []
            for pe in cur["period_end"]:
                m = q[(q["period_end"] - (pe - pd.DateOffset(years=1))).abs() <= pd.Timedelta(days=5)]
                if m.empty:
                    ant = None
                    break
                ant.append(float(m.iloc[-1]["value"]))
                linhas_ant.append(m.iloc[-1])
            if ant is None:
                continue
            participantes = [a.iloc[-1], *(rr for _, rr in cur.iterrows()), *linhas_ant]
            if not comparaveis(participantes):
                continue
            r = cur.iloc[-1].to_dict()
            r.update({"freq": "TTM", "value": float(a["value"].iloc[-1]) + float(cur["value"].sum()) - sum(ant),
                      "documento": (f"{r.get('documento') or ''} (anual + acumulado do exercício − acumulado do "
                                    "mesmo período do exercício anterior)").strip(),
                      "data_publicacao": max(pd.Timestamp(rr["data_publicacao"]) for rr in participantes),
                      "componentes_fluxo": componentes([(a.iloc[-1], 1.0)] + [(rr, 1.0) for _, rr in cur.iterrows()]
                                                        + [(rr, -1.0) for rr in linhas_ant]),
                      **tempo(participantes)})
            r.update(contexto_composicao(json.loads(r["componentes_fluxo"])))
            rows.append(r)
        return pd.DataFrame(rows, columns=[*d.columns, "componentes_fluxo"] if "componentes_fluxo" not in d else d.columns) \
            if rows else d.iloc[0:0]

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
        conf = self._conf.get(item)
        if conf is not None and conf > row["period_end"]:
            if (item, conf) not in self.em_conferencia:
                self.em_conferencia.append((item, conf))
            return None
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
        row = self.linha_ano_anterior(item)
        return None if row is None else _f(row["value"])

    def linha_ano_anterior(self, item: str) -> pd.Series | None:
        """Linha exata usada no crescimento, conservada para o contrato temporal."""
        if self.df.empty:
            return None
        for fq in ("TTM", "A"):
            sub = self.df[(self.df["item"] == item) & (self.df["freq"] == fq)].sort_values("period_end")
            if len(sub) >= 2:
                ult = sub.iloc[-1]["period_end"]
                alvo = ult - pd.DateOffset(years=1)
                prev = sub[(sub["period_end"] - alvo).abs() <= pd.Timedelta(days=20)]
                if not prev.empty:
                    return prev.iloc[-1]
        return None

    def linhas_anuais(self, item: str) -> dict[int, pd.Series]:
        """As linhas exatas que formam o histórico anual, após a preferência de consolidação.

        Havendo mais de um encerramento no ano civil, prevalecem o último encerramento e,
        no empate, a última publicação. Valor, período e proveniência usam a mesma seleção.
        """
        if self.df.empty:
            return {}
        sub = self.df[(self.df["item"] == item) & (self.df["freq"] == "A")].sort_values(
            ["period_end", "data_publicacao"], kind="mergesort")
        out: dict[int, pd.Series] = {}
        for _, r in sub.iterrows():
            if _f(r["value"]) is not None:
                out[int(r["period_end"].year)] = r
        return out

    def anual(self, item: str) -> dict[int, float]:
        return {ano: float(r["value"]) for ano, r in self.linhas_anuais(item).items()}

    def anual_individual(self, item: str) -> set[int]:
        """Exercícios cujo valor anual de ``item`` vem das demonstrações individuais (sem consolidadas)."""
        if self.df.empty or "consolidado" not in self.df.columns:
            return set()
        sub = self.df[(self.df["item"] == item) & (self.df["freq"] == "A")]
        ind = sub[~sub["consolidado"].astype(str).str.lower().isin(["true", "1"])]
        return {int(pd.Timestamp(d).year) for d in ind["period_end"]}

    def fim_exercicio(self) -> pd.Timestamp | None:
        """Fim do último exercício publicado (demonstrações anuais dos itens de referência)."""
        if self.df.empty:
            return None
        a = self.df[(self.df["freq"] == "A") & self.df["item"].isin(self.ITENS_REFERENCIA)]
        return None if a.empty else pd.Timestamp(a["period_end"].max())

    def linhas_serie_acoes(self) -> list[pd.Series]:
        """Ações em circulação por data-base (todas as frequências; a última publicação por data)."""
        if self.df.empty:
            return []
        s = self.df[self.df["item"] == "acoes_em_circulacao"].sort_values(["period_end", "data_publicacao"],
                                                                       kind="mergesort")
        s = s.drop_duplicates("period_end", keep="last")
        return [r for _, r in s.iterrows() if _f(r["value"]) is not None and float(r["value"]) > 0]

    def serie_acoes(self) -> list[tuple[pd.Timestamp, float]]:
        return [(pd.Timestamp(r["period_end"]), float(r["value"])) for r in self.linhas_serie_acoes()]

    def moeda(self) -> str | None:
        if self.df.empty or "currency" not in self.df.columns:
            return None
        sub = self.df[~self.df["item"].isin(["acoes_em_circulacao", "acoes_emitidas", "acoes_tesouraria"])]
        c = sub.sort_values("period_end")["currency"].dropna()
        c = c[c.astype(str).str.len() == 3]
        return str(c.iloc[-1]).upper() if len(c) else None

    def linha_moeda(self) -> pd.Series | None:
        """Linha que fornece a moeda usada; mesmas seleção e ordem de ``moeda``."""
        if self.df.empty or "currency" not in self.df.columns:
            return None
        s = self.df[~self.df["item"].isin(["acoes_em_circulacao", "acoes_emitidas", "acoes_tesouraria"])]
        s = s.sort_values("period_end")
        s = s[s["currency"].notna() & s["currency"].astype(str).str.len().eq(3)]
        return None if s.empty else s.iloc[-1]


def fim_exercicio_consenso(fye: pd.Timestamp | None, as_of: date, prazo_dias: int = 120
                           ) -> tuple[pd.Timestamp | None, str | None]:
    """Fim do exercício anterior ao "ano 1" do consenso: o último encerramento (mesmo mês do
    exercício publicado) até ``as_of``. Se as demonstrações anuais desse exercício não estão no
    arquivo e o prazo de entrega (``prazo_dias``) já passou, o calendário segue o encerramento esperado
    (o consenso já rolou) e o atraso é sinalizado; dentro do prazo, o exercício recém-encerrado ainda é
    o "ano 1" do consenso (calendário pelo último exercício publicado)."""
    if fye is None:
        return None, None
    fye = pd.Timestamp(fye)
    alvo = pd.Timestamp(year=as_of.year, month=fye.month, day=1) + pd.offsets.MonthEnd(0)
    if alvo > pd.Timestamp(as_of):
        alvo = pd.Timestamp(year=as_of.year - 1, month=fye.month, day=1) + pd.offsets.MonthEnd(0)
    if fye >= alvo:
        return fye, None
    atraso = (pd.Timestamp(as_of) - alvo).days
    if atraso <= prazo_dias:
        return fye, None
    return alvo, (f"demonstrações anuais do exercício encerrado em {alvo.date()} não encontradas no arquivo "
                  f"público ({atraso} dias depois do encerramento; último exercício publicado {fye.date()}): "
                  "calendário do consenso pelo encerramento esperado")


def _mais_recente(itens: dict[str, float], periodos: dict[str, pd.Timestamp], preferido: str, alternativo: str,
                  pk: _Pacote) -> tuple[float | None, str]:
    """Item dos controladores, salvo quando o total (consolidado ou individual) tem data-base mais
    recente — companhia sem consolidação no período (o individual não separa não controladores).
    Devolve ``(valor, item usado)``."""
    a, b = itens.get(preferido), itens.get(alternativo)
    if a is None:
        return b, alternativo
    if b is not None and preferido in periodos and alternativo in periodos and periodos[alternativo] > periodos[preferido]:
        pk.avisos.append(f"{rotulo(alternativo)} de {periodos[alternativo].date()} usado no lugar de "
                         f"{rotulo(preferido)} de {periodos[preferido].date()} (data-base mais recente)")
        return b, alternativo
    return a, preferido


def _bool(x: Any) -> bool:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return False
    if isinstance(x, str):
        return x.strip().lower() in ("true", "1", "sim")
    return bool(x)


def _base_linha(row: pd.Series) -> str | None:
    # O normalizador histórico sinaliza base mista com consolidado=False. Isso não certifica
    # demonstrações individuais homogêneas e não pode fechar a identidade nova de FCFF.
    if "base mista" in str(row.get("nota", "")).lower():
        return None
    b = str(row.get("consolidado")).lower()
    return "consolidado" if b in ("true", "1") else "individual" if b in ("false", "0") else None


def documento_proveniencia(row) -> str:
    """Rótulo determinístico existente; não é identificador ou documento novo."""
    freq = FREQ_PT.get(str(row.get("freq")), str(row.get("freq")))
    base = ""
    if "consolidado" in row and str(row.get("consolidado")).lower() in ("false", "0"):
        base = "; demonstrações individuais (sem consolidadas no período)"
    return f"{documento_pt(row.get('documento'))} ({row.get('demonstrativo')}, " \
           f"{freq} até {pd.Timestamp(row['period_end']).date()}{base})".strip()


def _prov_linha(row: pd.Series | None, *, detalhar_fluxos: bool = False, detalhar_resultados: bool = False) -> dict[str, Any]:
    if row is None:
        return prov_codigo("sem linha de demonstrativo")
    pub = row.get("data_publicacao")
    pub = pd.Timestamp(pub).date() if pd.notna(pub) else None
    out = prov_dict({"fonte": row.get("fonte"), "url": row.get("url"),
                     "documento": documento_proveniencia(row),
                     "data_publicacao": pub, "data_coleta": row.get("data_coleta"),
                     "sha256": row.get("sha256")})
    out.update(dimensoes(row))
    out.update(contexto_documental(row))
    out["data_estimada"] = _bool(row.get("pit_estimado"))
    if str(row.get('disponibilidade_tipo')) == 'recepcao_observada':
        for k in ('disponibilidade_tipo', 'disponivel_desde', 'data_recebimento_documento', 'received_date'):
            v = row.get(k)
            out[k] = None if pd.isna(v) else v.isoformat() if hasattr(v, 'isoformat') else v
    if str(row.get("fonte")) == "RI_OBSERVADA":
        out.update({k: row.get(k) for k in ("fato_id", "identity_binding_sha256", "disponivel_desde",
                                          "coluna", "lexema", "quantum", "locator", "received_date")})
        out["data_coleta"] = row.get("data_coleta")
        out["modo_disponibilidade"] = "captura_observada_publicacao_desconhecida"
    if detalhar_fluxos and isinstance(row.get("componentes_fluxo"), str):
        out["componentes_fluxo"] = json.loads(row["componentes_fluxo"])
    elif detalhar_fluxos and "componentes_fluxo=" in str(row.get("nota", "")):
        texto = str(row["nota"]).split("componentes_fluxo=", 1)[1]
        out["componentes_fluxo"], _ = json.JSONDecoder().raw_decode(texto)
    if detalhar_resultados:
        out.update({"moeda_fonte": row.get("currency"), "base_contabil": _base_linha(row),
                    "freq_fonte": str(row.get("freq")), "fim_fonte": pd.Timestamp(row["period_end"]).date().isoformat()})
        for k in ("fato_resultado_id", "disponivel_desde", "period_start"):
            v = row.get(k)
            if pd.notna(v):
                out[k] = v.isoformat() if hasattr(v, "isoformat") else v
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


# ============================================================ contagem de ações conciliada (G13c)

def _unidade_conferida(params: ParametrosCobertura, ticker: str) -> bool:
    u = params.unidades.get(ticker)
    return bool(u and u.get("conferido") and u.get("url"))


def _capital_oficial(dados: DadosPublicos, issuer_id: str, sintetico: bool) -> dict[str, Any] | None:
    cap = getattr(dados, "capital_oficial", None)
    if cap is None or cap.empty:
        return None
    s = cap[cap["issuer_id"] == issuer_id]
    if s.empty:
        return None
    r = s.iloc[-1]
    q = _f(r.get("qtd_total"))
    if q is None or q <= 0:
        return None
    result = {"qtd_total": q, "data_ref": str(r.get("data_ref")), "versao": _f(r.get("versao")),
            "data_publicacao": str(r.get("data_publicacao")), "tipo_capital": str(r.get("tipo_capital")),
            "fonte": prov_dict({"fonte": "SIMULADO" if sintetico else "CVM",
                                "url": None if sintetico else r.get("url"),
                                "documento": ("capital social simulado (DADOS SIMULADOS)" if sintetico else
                                              f"Formulário de Referência {str(r.get('data_ref'))[:4]} versão "
                                              f"{int(_f(r.get('versao')) or 0)}: {r.get('tipo_capital')} (item 12.1)"),
                                "data_publicacao": r.get("data_publicacao"), "data_coleta": None,
                                "sha256": r.get("sha256")})}
    if 'semantica_capital' in r:
        from ..data.publico_capital_semantica import ler
        result['semantica_capital'] = ler(r['semantica_capital'])
    return result


def _txt_n(x: float | None) -> str:
    from .formato import contagem as _c

    return _c(x) if x is not None else "n/d"


def conciliar_contagem(acoes_dem: float | None, apl: float, c_mkt: float | None, oficial: dict[str, Any] | None,
                       params: ParametrosCobertura, fonte_dem: dict[str, Any] | None, fonte_mkt: dict[str, Any],
                       unidade_conferida: bool, *, fontes_participantes: list[str] | None = None
                       ) -> tuple[float | None, str, dict[str, Any], dict[str, Any]]:
    """Unidades em circulação da linha a partir de até três fontes independentes.

    ``c_dem`` = ações das demonstrações ÷ ações por unidade; ``c_mkt`` = valor de mercado público ÷
    fechamento; ``c_ofi`` = capital social do FRE (CVM) ÷ ações por unidade. Com a oficial: vale o
    par a ±``contagem_tolerancia`` (preferência demonstrações, depois oficial); sem par ⇒ bloqueio.
    Sem a oficial: demonstrações e mercado a ±``unidades_tolerancia`` ⇒ demonstrações; divergência ⇒
    a contagem das demonstrações já em unidades negociadas só com composição da unidade conferida
    na curadoria; senão a do mercado, com aviso (confiança C)."""
    q = params.sec("qualidade")
    tol3 = float(q.get("contagem_tolerancia", 0.10))
    tol2 = float(q.get("unidades_tolerancia", 0.25))
    c_dem = _div(acoes_dem, apl)
    c_ofi = None if oficial is None else _div(oficial["qtd_total"], apl)
    cands = {"demonstracoes": c_dem, "valor_de_mercado": c_mkt, "oficial": c_ofi}
    info: dict[str, Any] = {"candidatos": {k: r6(v) for k, v in cands.items()}, "acoes_por_unidade": apl,
                            "tolerancia": tol3 if c_ofi is not None else tol2, "avisos_pacote": []}
    if oficial is not None:
        info["oficial"] = {k: oficial[k] for k in ("data_ref", "versao", "data_publicacao", "tipo_capital")}

    def perto(a: float | None, b: float | None, tol: float) -> bool:
        return a is not None and b is not None and b > 0 and abs(a / b - 1) <= tol

    fonte_ofi = None if oficial is None else oficial["fonte"]
    lista = (f"demonstrações {_txt_n(c_dem)}, valor de mercado público ÷ fechamento {_txt_n(c_mkt)}"
             + (f", Formulário de Referência {_txt_n(c_ofi)}" if oficial is not None else ""))

    def fim(valor: float | None, status: str, origem: str, fonte: dict[str, Any] | None, detalhe: str,
            portao: str, confirmadora: str | None = None
            ) -> tuple[float | None, str, dict[str, Any], dict[str, Any]]:
        if fontes_participantes is not None and valor is not None:
            escolhida = ("demonstrativos" if origem.startswith("demonstrações") else
                         "oficial" if origem == "Formulário de Referência" else "mercado")
            fontes_participantes.extend([escolhida] + ([confirmadora] if confirmadora else []))
            info["fontes_participantes"] = list(fontes_participantes)
        info.update({"escolhida": r6(valor), "origem": origem, "status": portao, "detalhe": detalhe})
        return valor, status, fonte or prov_codigo(origem), info

    if c_ofi is not None:
        if perto(c_dem, c_ofi, tol3):
            par = "valor de mercado" if perto(c_dem, c_mkt, tol3) else "Formulário de Referência"
            return fim(c_dem, "demonstrativos", "demonstrações", fonte_dem,
                       f"demonstrações confirmadas pelo {par} ({lista})", "ok",
                       "mercado" if par == "valor de mercado" else "oficial")
        if perto(c_dem, c_mkt, tol3):
            return fim(c_dem, "demonstrativos", "demonstrações", fonte_dem,
                       f"demonstrações confirmadas pelo valor de mercado ({lista}); Formulário de Referência "
                       "divergente", "ok", "mercado")
        if perto(c_mkt, c_ofi, tol3):
            return fim(c_ofi, "oficial", "Formulário de Referência", fonte_ofi,
                       f"demonstrações divergentes; Formulário de Referência confirmado pelo valor de mercado ({lista})",
                       "ok", "mercado")
        valor = c_dem if c_dem is not None else c_ofi
        return fim(valor, "nao_conciliada", "demonstrações" if c_dem is not None else "Formulário de Referência",
                   fonte_dem if c_dem is not None else fonte_ofi,
                   f"nenhum par de fontes a ±{pct(tol3, 0)}: {lista}", "bloqueio")
    if c_dem is not None and c_mkt is not None:
        if perto(c_dem, c_mkt, tol2):
            return fim(c_dem, "demonstrativos", "demonstrações", fonte_dem,
                       f"demonstrações confirmadas pelo valor de mercado a ±{pct(tol2, 0)} ({lista})", "ok", "mercado")
        alt = acoes_dem
        if apl != 1.0 and unidade_conferida and perto(alt, c_mkt, tol2):
            return fim(alt, "demonstrativos_em_unidades", "demonstrações (já em unidades negociadas)", fonte_dem,
                       f"demonstrações já em unidades negociadas, composição da unidade conferida ({lista})", "ok", "mercado")
        info["avisos_pacote"].append(f"contagem das demonstrações diverge do valor de mercado público em "
                                     f"{abs(c_dem / c_mkt - 1):.0%} sem fonte oficial: usada a do valor de mercado")
        return fim(c_mkt, "valor_de_mercado", "valor de mercado público ÷ fechamento", fonte_mkt,
                   f"duas fontes divergentes sem terceira oficial ({lista}): usada a do valor de mercado", "aviso")
    if c_dem is not None:
        return fim(c_dem, "demonstrativos", "demonstrações", fonte_dem,
                   f"só a contagem das demonstrações ({lista})", "ok")
    if c_mkt is not None:
        if apl != 1.0 and not unidade_conferida:
            return fim(c_mkt, "valor_de_mercado", "valor de mercado público ÷ fechamento", fonte_mkt,
                       f"contagem das demonstrações indisponível e unidade negociada de {num(apl, 0)} ações sem "
                       f"composição conferida: só a do valor de mercado ({lista})", "aviso")
        return fim(c_mkt, "valor_de_mercado", "valor de mercado público ÷ fechamento", fonte_mkt,
                   f"contagem das demonstrações indisponível: usada a do valor de mercado, sem divergência a "
                   f"conciliar ({lista})", "ok")
    return fim(None, "indisponivel", "indisponível", None, "nenhuma contagem de ações disponível", "bloqueio")


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
    from .temporal import ativo as temporal_ativo
    from .temporal import validar as validar_corte

    corte = None
    if temporal_ativo(params) and dados.corte_temporal is not None:
        corte = validar_corte(dados.corte_temporal)
        as_of = date.fromisoformat(corte["data_modelo"])
    from .ri_observada import ativo as ri_ativo
    if ri_ativo(params) and corte is not None:
        from ..data.ri_captura.adapter import autenticar

        contexto_ri = autenticar(dados.ri_contexto, md)
        if issuer_id == contexto_ri.document.issuer_id:
            md = md.truncate(date.fromisoformat(corte["base_preco"]))
    uni = md.universe
    iss = uni.issuers.loc[issuer_id]
    pais = str(iss["country"])
    setor = str(iss["gics_sector"])
    arq = params.arquetipos.get(issuer_id) or arquetipo_padrao(issuer_id, setor)
    beta_setor = params.betas.get(arq.industria_damodaran) or params.betas["Total Market"]
    pk = _Pacote()
    from .fontes import disponibilidade_observada

    observar_disponibilidade = disponibilidade_observada(params)
    registro = None
    if observar_disponibilidade:
        from .disponibilidade_demonstrativos import RegistroParticipantes

        registro = RegistroParticipantes(issuer_id)
    pk.put("issuer_id", issuer_id)
    pk.put("nome", str(iss["issuer_name"]))
    pk.put("pais", pais)
    pk.put("setor", setor)
    pk.put("arquetipo", arq.arquetipo)
    pk.put("arquetipo_nota", arq.nota)
    pk.put("industria", beta_setor.industria)
    pk.put("financeira", bool(beta_setor.financeira or arq.arquetipo in ("banco", "seguradora")))
    pk.put("lambda", float(arq.lambda_))
    if arq.fim_concessao is not None:
        doc, _, url = (arq.fim_concessao_fonte or "").rpartition("; ")
        doc, url = (doc, url) if url.startswith("http") else (arq.fim_concessao_fonte, None)
        pk.put("fim_concessao", arq.fim_concessao, {
            "fonte": "CONFIG", "url": url, "documento": (f"prazo da concessão curado em configs/cdp/cobertura/"
                                                         f"arquetipos.csv: {doc}" if doc else
                                                         "prazo da concessão curado (sem documento citado)"),
            "data_publicacao": None, "data_coleta": None, "sha256": params.arquivos.get("cobertura/arquetipos.csv")},
            nome="Fim da concessão (ano)", unidade="n")
    else:
        pk.put("fim_concessao", None)
    pk.put("as_of", as_of.isoformat())
    if corte is not None:
        pk.put("corte_temporal", corte)

    from .resultado import ativo as resultado_ativo
    detalhar_resultados = resultado_ativo(params)
    if detalhar_resultados and not dados.resultado_evidencias.empty:
        pk.put("resultado_evidencias", str(dados.resultado_evidencias.iloc[0]["catalogo_json"]))
    from .ri_observada import selecionar_demonstrativos
    dem_selecionados, ri_trace = selecionar_demonstrativos(md, dados, params, issuer_id)
    dem = Demonstrativos(dem_selecionados, issuer_id)
    moeda_dem = dem.moeda() or arq.moeda_demonstrativos
    if moeda_dem is None:
        prim = str(iss["primary_ticker"])
        fc = md.fundamentals.loc[prim, "financial_currency"] if prim in md.fundamentals.index \
            and "financial_currency" in md.fundamentals.columns else None
        moeda_dem = str(fc).upper() if isinstance(fc, str) and fc else None
    pk.put("moeda_demonstrativos", moeda_dem)
    if registro is not None:
        row_moeda = dem.linha_moeda()
        if row_moeda is not None:
            registro.registrar(row_moeda, "moeda_demonstrativos", fonte=_prov_linha(row_moeda))

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
    rows_acoes = [row_acoes] if acoes is not None else []
    if acoes is None:
        emit, row_acoes = dem.valor("acoes_emitidas")
        tes, row_tes = dem.valor("acoes_tesouraria")
        if emit is not None and tes is not None:
            acoes = emit - tes
            rows_acoes = [row_acoes, row_tes]
        elif emit is not None:
            acoes = emit
            rows_acoes = [row_acoes]
            pk.avisos.append("ações em tesouraria indisponíveis: usadas as ações emitidas")
    mcap_pub = None
    if linha in md.fundamentals.index and "market_cap" in md.fundamentals.columns:
        mcap_pub = _f(md.fundamentals.loc[linha, "market_cap"])
    fonte_mkt_un = {**fonte_mkt, "documento": ("valor de mercado simulado ÷ fechamento (DADOS SIMULADOS)"
                                               if md.is_synthetic else "valor de mercado público ÷ fechamento")}
    oficial = _capital_oficial(dados, issuer_id, md.is_synthetic)
    fontes_contagem = [] if observar_disponibilidade else None
    unidades, status_unid, fonte_un, contagem = conciliar_contagem(
        acoes, apl, _div(mcap_pub, preco), oficial, params, _prov_linha(row_acoes) if row_acoes is not None
        else None, fonte_mkt_un, _unidade_conferida(params, linha), fontes_participantes=fontes_contagem)
    semantica = getattr(dados, 'capital_semantica', None)
    if semantica is not None:
        from ..data.publico_capital_semantica import discriminacao_contagem, ler
        observacoes = [value for value in semantica.get('semantica_capital', pd.Series(dtype=str)).dropna()
                      if ler(value).get('issuer_id_cadastro') == issuer_id]
        mercado_contagem = md.fundamentals.loc[linha].to_dict() if linha in md.fundamentals.index else {}
        contagem['semantica'] = discriminacao_contagem(contagem=contagem, rows_acoes=rows_acoes,
            oficial=oficial, observacoes=observacoes, linha=linha, apl=apl,
            data_preco=data_preco, data_mercado=md.as_of, mercado=mercado_contagem,
            ratio_curado=params.unidades.get(linha))
    for a in contagem.get("avisos_pacote", []):
        pk.avisos.append(a)
    contagem.pop("avisos_pacote", None)
    if unidades is None:
        pk.falta("unidades", "quantidade de ações indisponível (demonstrativos, valor de mercado e fonte oficial)")
    else:
        pk.put("unidades", unidades, fonte_un, nome=f"Unidades em circulação ({linha})",
               unidade="acoes")
    pk.put("status_unidades", status_unid)
    pk.put("contagem", contagem)
    if registro is not None and unidades is not None:
        if "demonstrativos" in fontes_contagem:
            for r in rows_acoes:
                registro.registrar(r, f"contagem.demonstrativos.{r['item']}", "unidades", fonte=_prov_linha(r))
        if "oficial" in fontes_contagem:
            capital = dados.capital_oficial[dados.capital_oficial["issuer_id"] == issuer_id].iloc[-1]
            registro.registrar({**capital.to_dict(), "item": "qtd_total", "freq": "FRE",
                "period_end": capital.get("data_ref")}, "contagem.oficial.qtd_total", "unidades",
                origem="oficial", fonte=oficial["fonte"])
        if "mercado" in fontes_contagem:
            fm = md.fundamentals.loc[linha]
            for item, periodo, recibo, freq in (
                ("market_cap", md.as_of.isoformat(), fm.get("market_cap_disponivel_desde"), "SNAPSHOT"),
                ("preco", data_preco.isoformat() if data_preco else None, fm.get("preco_disponivel_desde"), "D")):
                registro.registrar({"item": item, "freq": freq, "period_end": periodo,
                    "disponivel_desde": recibo}, f"contagem.mercado.{item}", "unidades",
                    origem="mercado", fonte=fonte_mkt_un if item == "market_cap" else fonte_mkt)

    # --- demonstrativos (convertidos para a moeda do modelo)
    tem_dem = not dem.vazio
    pk.put("tem_demonstrativos", tem_dem)
    if not tem_dem:
        pk.lacunas.append(lacuna("demonstrativos", "sem demonstrativos públicos até a data"))
    itens = {}
    periodos: dict[str, pd.Timestamp] = {}
    bases_fluxos = {}
    moedas_fluxos = {}
    detalhar_fluxos = (params.sec("projecao").get("reinvestimento_metodo") is not None
                       or params.sec("qualidade").get("margem_fluxos_metodo") is not None)
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
            bases_fluxos[item] = _base_linha(row)
            moedas_fluxos[item] = row.get("currency")
        prov = _prov_linha(row, detalhar_fluxos=detalhar_fluxos, detalhar_resultados=detalhar_resultados)
        if observar_disponibilidade and row is not None:
            registro.registrar(row, f"t.{item}", fonte=_prov_linha(row))
        if detalhar_resultados and row is not None:
            prov.update({"fator_moeda_resultado": str(fator), "valor_modelo": r6(vv)})
        estimados = estimados or bool(prov.get("data_estimada"))
        pk.put(f"t.{item}", vv, prov, nome=rotulo(item), unidade=f"total:{moeda}", periodo=per)
        if prov.get("data_estimada"):
            pk.tabela[-1]["data_estimada"] = True
    for x in dem.defasados:
        it = x.split(" ")[0]
        pk.lacunas.append(lacuna(it, f"item defasado em relação ao último balanço: {rotulo(it)} {x[len(it):].strip()}"))
    conf_lista = []
    for it, dconf in dem.em_conferencia:
        conf_lista.append({"item": it, "data": pd.Timestamp(dconf).date().isoformat()})
        pk.lacunas.append(lacuna(it, f"em conferência na fonte em {pd.Timestamp(dconf).date().isoformat()}: valor "
                                 "do período ausente na fonte pública (o período anterior não é usado)"))
    pk.put("em_conferencia", conf_lista)
    fye = dem.fim_exercicio()
    pk.put("fim_exercicio", None if fye is None else fye.date().isoformat())
    # calendário do consenso: o "ano 1" do consenso é o exercício corrente pelo mês de encerramento do
    # emissor; demonstrações anuais atrasadas além do prazo de entrega não deslocam o calendário
    fye_c, nota_fye = fim_exercicio_consenso(fye, as_of, int(params.sec("projecao").get("prazo_exercicio_dias", 120)))
    pk.put("fim_exercicio_consenso", None if fye_c is None else fye_c.date().isoformat())
    if nota_fye:
        pk.avisos.append(nota_fye)
        pk.lacunas.append(lacuna("demonstrativos", nota_fye))
    al = dados.alertas
    alertas_iid = [] if al is None or al.empty else [
        {k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in r.items()}
        for r in al[al["issuer_id"] == issuer_id][["tipo", "texto", "data", "item"]].to_dict("records")]
    pk.put("alertas_fonte", alertas_iid)
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
    # idade das demonstrações contra a data do snapshot (portão G19)
    pk.put("idade_balanco_dias", None if estoque_ref is None else int((pd.Timestamp(as_of) - estoque_ref).days))
    pk.put("idade_fluxos_dias", None if fluxo_ref is None else int((pd.Timestamp(as_of) - fluxo_ref).days))
    pk.put("data_balanco", None if estoque_ref is None else estoque_ref.date().isoformat())
    pk.put("data_fluxos", None if fluxo_ref is None else fluxo_ref.date().isoformat())
    pk.put("receita_ano_anterior", _conv(dem.ttm_ano_anterior("receita"), fator))
    if observar_disponibilidade and pk.v["receita_ano_anterior"] is not None:
        row_receita_anterior = dem.linha_ano_anterior("receita")
        if row_receita_anterior is not None:
            registro.registrar(row_receita_anterior, "receita_ano_anterior", fonte=_prov_linha(row_receita_anterior))
    hist = {}
    hist_fontes = {}
    hist_periodos = {}
    hist_bases = {}
    hist_moedas = {}
    for item in HIST_ITENS:
        linhas = dem.linhas_anuais(item)
        if item == "lucro_liquido_controladores":
            # exercícios só com demonstrações individuais (sem não controladores): o lucro do exercício é o
            # dos controladores
            ind = dem.anual_individual("lucro_liquido")
            for ano, row in dem.linhas_anuais("lucro_liquido").items():
                if ano not in linhas and ano in ind:
                    linhas[ano] = row
        if linhas:
            f_item = 1.0 if item == "acoes_em_circulacao" else fator
            hist[item] = {str(ano): r6(_conv(float(r["value"]), f_item)) for ano, r in sorted(linhas.items())}
            if registro is not None:
                for ano, r in linhas.items():
                    if hist[item][str(ano)] is not None:
                        registro.registrar(r, f"historico.{item}.{ano}", fonte=_prov_linha(r))
            hist_fontes[item] = {str(ano): {**_prov_linha(r, detalhar_resultados=detalhar_resultados), "item_fonte": str(r["item"]),
                                 "moeda_fonte": str(r.get("currency")), "valor_fonte": float(r["value"]),
                                 "fator_moeda": f_item, "valor_modelo": hist[item][str(ano)],
                                 **({"fator_moeda_resultado": str(f_item)} if detalhar_resultados else {})}
                                 for ano, r in linhas.items()}
            hist_periodos[item] = {str(ano): f"A|{pd.Timestamp(r['period_end']).date().isoformat()}"
                                   for ano, r in linhas.items()}
            hist_bases[item] = {str(ano): _base_linha(r) for ano, r in linhas.items()}
            hist_moedas[item] = {str(ano): r.get("currency") for ano, r in linhas.items()}
    pk.put("historico", hist)
    if detalhar_fluxos or detalhar_resultados:
        pk.put("historico_fontes", hist_fontes)
        pk.put("historico_periodos", hist_periodos)
        pk.put("historico_bases", hist_bases)
        pk.put("historico_moedas", hist_moedas)
        pk.put("bases_fluxos", {k: v for k, v in bases_fluxos.items() if k in FLUXOS})
        pk.put("moedas_fluxos", {k: v for k, v in moedas_fluxos.items() if k in FLUXOS})
        pk.put("periodos_fluxos", {str(r["id"])[2:]: str(r["periodo"])
                                  for r in pk.tabela if str(r.get("id", "")).startswith("t.")
                                  and str(r["id"])[2:] in FLUXOS and r.get("periodo")})
    if arq.arquetipo == "holding":
        rows_serie = dem.linhas_serie_acoes()
        pk.put("serie_acoes", [[pd.Timestamp(r["period_end"]).date().isoformat(), r6(float(r["value"]))]
                               for r in rows_serie])
        if registro is not None:
            for r in rows_serie:
                registro.registrar(r, f"serie_acoes.{pd.Timestamp(r['period_end']).date().isoformat()}",
                                   fonte=_prov_linha(r))
    datas_pub = pd.to_datetime(dem.df["data_publicacao"], errors="coerce") if tem_dem else pd.Series(dtype="datetime64[ns]")
    est_col = dem.df["pit_estimado"].map(_bool) if tem_dem and "pit_estimado" in dem.df.columns else pd.Series(dtype=bool)
    pk.put("datas_estimadas", bool(estimados or (len(est_col) and est_col.any())))
    pk.put("pit_ok", bool(tem_dem and datas_pub.notna().all() and (datas_pub <= pd.Timestamp(as_of)).all()
                          and not pk.v["datas_estimadas"]))
    observado = tem_dem and 'disponibilidade_tipo' in dem.df and dem.df['disponibilidade_tipo'].eq('recepcao_observada').any()
    pk.put("max_data_publicacao", None if (observado and datas_pub.isna().any()) or datas_pub.dropna().empty
           else datas_pub.max().date().isoformat())

    # --- por ação (moeda do modelo, por unidade da linha)
    pl_ctrl, k_pl = _mais_recente(itens, periodos, "patrimonio_controladores", "patrimonio_liquido", pk)
    lucro, k_luc = _mais_recente(itens, periodos, "lucro_liquido_controladores", "lucro_liquido", pk)
    pk.put("item_patrimonio", k_pl)
    pk.put("item_lucro", k_luc)
    bvps = _div(pl_ctrl, unidades)
    ri_conflito_patrimonio = ri_trace is not None and any(
        d["estado"] == "conflito" and d["item"] in ("patrimonio_controladores", "patrimonio_liquido")
        and d["freq"] == "Q" for d in ri_trace["selecao"])
    if ri_conflito_patrimonio:
        bvps = None
    eps_ttm = _div(lucro, unidades)
    fonte_yh = {"fonte": "SIMULADO" if md.is_synthetic else "YAHOO",
                "url": None if md.is_synthetic else f"https://finance.yahoo.com/quote/{linha}/key-statistics",
                "documento": ("retrato simulado (DADOS SIMULADOS)" if md.is_synthetic
                              else "retrato público Yahoo Finance (não point-in-time)"), "data_publicacao": None,
                "data_coleta": md.manifest.created_at.isoformat(), "sha256": None}
    if bvps is None and not ri_conflito_patrimonio and linha in md.fundamentals.index and moeda_dem == moeda:
        bv = _f(md.fundamentals.loc[linha].get("book_value"))
        if bv is not None:
            bvps = bv
            pk.avisos.append("patrimônio por ação do retrato público" + (" simulado" if md.is_synthetic else " Yahoo Finance")
                             + " (sem demonstração financeira)")
            pk.put("bvps_fonte_yahoo", True)
    if bvps is None:
        pk.falta("bvps", "patrimônio por ação indisponível")
    else:
        pk.put("bvps", bvps, pk.fontes.get(f"t.{k_pl}", fonte_yh),
               nome="Patrimônio por ação", unidade=f"preco:{moeda}")
    if eps_ttm is None:
        pk.falta("eps_ttm", "lucro dos últimos 12 meses indisponível")
    else:
        pk.put("eps_ttm", eps_ttm, pk.fontes.get(f"t.{k_luc}"),
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
        ri_conflito_minoritarios = ri_trace is not None and any(
            d["estado"] == "conflito" and d["item"] == "participacao_minoritarios" and d["freq"] == "Q"
            for d in ri_trace["selecao"])
        mesma_data = ("patrimonio_liquido" in periodos and "patrimonio_controladores" in periodos
                      and periodos["patrimonio_liquido"] == periodos["patrimonio_controladores"])
        if plt is not None and plc is not None and mesma_data and plt - plc >= 0 and not ri_conflito_minoritarios:
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
    pk.put("beta_u_setor", beta_setor.beta_u_global, prov_curadoria(
        fonte="DAMODARAN", url=beta_setor.url,
        documento=f"β desalavancado (corrigido por caixa) — {beta_setor.industria}",
        data_publicacao=beta_setor.data_ref, arquivo="cobertura/betas_setor.csv",
        sha256_curadoria=params.arquivos.get("cobertura/betas_setor.csv")),
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
    if registro is not None:
        registro.finalizar(pk.v)
    pk.put("tabela_insumos", list(pk.tabela))
    from .ri_observada import finalizar_pacote
    return finalizar_pacote(pk.v, ri_trace)


def _consenso(md: MarketData, dados: DadosPublicos, params: ParametrosCobertura, pk: _Pacote,
              issuer_id: str, linha: str, moeda: str, moeda_dem: str | None, preco: float | None,
              unidades: float | None, eps_ttm: float | None, itens: dict[str, float],
              as_of: date) -> None:
    con = dados.consenso
    lines = md.universe.lines
    row = None
    tick = linha
    linhas_n: list[list[Any]] = []
    unidades_declaradas = params.valuation.get("consenso", {}).get("unidade_metodo") == "declaracao_fonte"

    def fator_de(r: pd.Series, t: str) -> float | None:
        """LPA por unidade da linha ``t`` na moeda das estimativas → por unidade da linha de valuation
        na moeda dela (ações por linha e câmbio)."""
        from ..data.publico_eps import autenticar_linha

        contexto_eps = autenticar_linha(r, getattr(dados, "raiz", None))
        if contexto_eps is not None and contexto_eps["moeda_comum"] is None:
            return None
        m_e = r.get("moeda_estimativas")
        if unidades_declaradas and not (isinstance(m_e, str) and len(m_e) == 3):
            return None
        m_e = str(m_e).upper() if isinstance(m_e, str) and len(m_e) == 3 else str(lines.loc[t, "currency"]).upper()
        fx_e, _ = fx_usd(md, m_e, as_of)
        fx_m, _ = fx_usd(md, moeda, as_of)
        if fx_e is None or fx_m is None:
            return None
        a_ln, _ = acoes_por_linha(md, params, issuer_id, linha)
        a_tk, _ = acoes_por_linha(md, params, issuer_id, t)
        return (fx_e / fx_m) * (a_ln / a_tk)

    if not con.empty:
        # a linha de valuation; outra linha do emissor (classe, ADR) só com mais analistas de LPA e LPA
        # convertido (ações por linha e câmbio) a ±35% do da linha de valuation — a de mais analistas
        # define o consenso sem trocar de emissor por erro de unidade; sem LPA na linha de valuation,
        # a linha com mais analistas
        cands = []
        for t in md.universe.lines_for(issuer_id).index:
            s2 = con[con["ticker"] == t]
            if s2.empty:
                continue
            r2 = s2.iloc[-1]
            n2 = _f(r2.get("n_analistas_eps"))
            e2_ = _f(r2.get("eps_fy1"))
            linhas_n.append([str(t), n2])
            f2 = fator_de(r2, str(t)) if e2_ is not None else None
            cands.append({"t": str(t), "row": r2, "n": n2 if n2 is not None else 0.0,
                          "e1": None if e2_ is None or f2 is None else e2_ * f2})
        v = next((c for c in cands if c["t"] == linha), None)
        com_lpa = [c for c in cands if c["e1"] is not None]
        if v is not None and v["e1"] is not None:
            esc = v
            for c in sorted(com_lpa, key=lambda c: (-c["n"], str(lines.loc[c["t"], "line_type"]) != "LOCAL", c["t"])):
                if c["t"] != linha and c["n"] > v["n"] and v["e1"] and 0.65 <= c["e1"] / v["e1"] <= 1.35:
                    esc = c
                    break
        elif com_lpa:
            esc = sorted(com_lpa, key=lambda c: (-c["n"], str(lines.loc[c["t"], "line_type"]) != "LOCAL", c["t"]))[0]
        else:
            esc = v if v is not None else (cands[0] if cands else None)
        if esc is not None:
            row, tick = esc["row"], esc["t"]
    def _iso(x: Any) -> Any:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return x.isoformat() if hasattr(x, "isoformat") else x

    def _sha(x: Any) -> str | None:
        return x if isinstance(x, str) and x else None

    fonte = {"fonte": "SIMULADO" if md.is_synthetic else "YAHOO",
             "url": None if md.is_synthetic else f"https://finance.yahoo.com/quote/{tick}/analysis",
             "documento": ("consenso simulado (DADOS SIMULADOS)" if md.is_synthetic
                           else "consenso público Yahoo Finance (arquivo de estimativas: LPA, receita e preços-alvo)"),
             "data_publicacao": None,
             "data_coleta": None if row is None else _iso(row.get("data_coleta")),
             "sha256": None if row is None else _sha(row.get("sha256"))}
    fonte_info = {**fonte, "url": None if md.is_synthetic else f"https://finance.yahoo.com/quote/{tick}",
                  "documento": ("consenso simulado (DADOS SIMULADOS)" if md.is_synthetic
                                else "consenso público Yahoo Finance (arquivo de cotação: recomendação média, "
                                     "número de analistas e moeda de cotação)"),
                  "data_coleta": None if row is None else _iso(row.get("data_coleta_info")),
                  "sha256": None if row is None else _sha(row.get("sha256_info"))}
    fonte_eps = fonte
    if row is not None:
        from ..data.publico_eps import autenticar_linha

        contexto_eps = autenticar_linha(row, getattr(dados, "raiz", None))
        if contexto_eps is not None:
            fonte_eps = {**fonte, "url": contexto_eps["url"],
                         "documento": "EPS por período no corpo HTTP público quoteSummary.earningsTrend",
                         "eps_contexto": contexto_eps}
            # Os preços-alvo vêm de info; o corpo EPS não lhes fornece autoridade.
            fonte = fonte_info
            pk.fontes["consenso_eps"] = fonte_eps
    if row is None:
        pk.falta("eps_fy1", "sem consenso público de LPA")
        pk.put("consenso", None)
        return
    # conversão por ações por linha e câmbio (moeda das estimativas → moeda da linha de valuation)
    status = "ok"
    m_est = row.get("moeda_estimativas")
    m_est = str(m_est).upper() if isinstance(m_est, str) and len(m_est) == 3 else None
    tem_lpa = _f(row.get("eps_fy1")) is not None or (unidades_declaradas and _f(row.get("eps_fy2")) is not None)
    fator_lpa = fator_de(row, tick) if tem_lpa else 1.0
    if fator_lpa is None:
        e1 = e2 = None
        if unidades_declaradas and m_est is None:
            status = "moeda_indeterminada"
            pk.avisos.append("moeda do LPA de consenso ausente na fonte: não inferida da cotação ou dos demonstrativos")
        else:
            status = "cambio_indisponivel"
            pk.avisos.append(f"LPA de consenso em {m_est or tick} sem câmbio na base: descartado")
    else:
        e1 = _conv(_f(row.get("eps_fy1")), fator_lpa)
        e2 = _conv(_f(row.get("eps_fy2")), fator_lpa)
        if tick != linha:
            pk.avisos.append(f"consenso de LPA da linha {tick} convertido para {linha} (ações por linha e câmbio)")
        if m_est is not None and m_est != moeda:
            status = "fx_corrigido"
            pk.avisos.append(f"LPA de consenso em {m_est} convertido para {moeda}")
    # preços-alvo de outra linha: paridade de ações por linha e câmbio da cotação
    fator_linha = 1.0
    if tick != linha:
        a_ln, _ = acoes_por_linha(md, params, issuer_id, linha)
        a_tk, _ = acoes_por_linha(md, params, issuer_id, tick)
        fx_a, _ = fx_usd(md, str(lines.loc[tick, "currency"]), as_of)
        fx_b, _ = fx_usd(md, moeda, as_of)
        fator_linha = None if fx_a is None or fx_b is None else (fx_a / fx_b) * (a_ln / a_tk)
    def plausivel(e: float | None) -> bool:
        """LPA coerente em moeda e unidade: contra o LPA dos demonstrativos (|razão| em [0,2; 5])
        ou, sem ele, rendimento |LPA|/P0 em [0,05%; 100%] (prejuízo e lucro baixo são plausíveis)."""
        if e is None or preco is None or preco <= 0:
            return True
        if eps_ttm is not None and abs(eps_ttm) > 0.01 * preco:
            return 0.2 <= abs(e / eps_ttm) <= 5.0
        return 0.0005 <= abs(e) / preco <= 1.0

    if unidades_declaradas:
        # A recuperação de um prejuízo pode gerar uma razão extrema entre LPA previsto e
        # realizado. Essa razão não demonstra outra moeda/unidade e nunca autoriza uma
        # segunda conversão. A declaração da fonte, o câmbio e a paridade da linha definem
        # a unidade; os portões de qualidade continuam avaliando o resultado econômico.
        if any(e is not None and not plausivel(e) for e in (e1, e2)):
            pk.avisos.append("LPA de consenso distante do lucro realizado: revisar premissas; moeda e unidade declaradas preservadas")
    elif e1 is not None and not plausivel(e1):
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
        pk.put("eps_fy1", e1, fonte_eps, nome="LPA de consenso (ano 1)", unidade=f"preco:{moeda}")
    if e2 is not None:
        pk.put("eps_fy2", e2, fonte_eps, nome="LPA de consenso (ano 2)", unidade=f"preco:{moeda}")
    r1, r2 = _f(row.get("receita_fy1")), _f(row.get("receita_fy2"))
    g1 = None
    rec = itens.get("receita")
    if pk.v.get("financeira"):  # receita de intermediação financeira não comparável entre fontes
        r1 = r2 = None
    # moeda da receita de consenso (da própria tabela da fonte); sem ela, a do LPA; sem ela, a da cotação
    m_rec = next((str(x).upper() for x in (row.get("moeda_receita"), row.get("moeda_estimativas"),
                                           row.get("moeda_cotacao"))
                  if isinstance(x, str) and len(x) == 3), None)
    if r1 is not None and m_rec is not None and moeda_dem is not None and m_rec != moeda_dem:
        fx_r, _ = fx_usd(md, m_rec, as_of)
        fx_dm, _ = fx_usd(md, moeda_dem, as_of)
        if fx_r is None or fx_dm is None:
            pk.lacunas.append(lacuna("g_receita_fy1", f"receita de consenso em {m_rec} sem câmbio na base: "
                                                      "crescimento de consenso não usado"))
            r1 = r2 = None
        else:
            f_rec = fx_r / fx_dm
            r1 = r1 * f_rec
            r2 = None if r2 is None else r2 * f_rec
            pk.avisos.append(f"receita de consenso em {m_rec} convertida para {moeda_dem} antes da razão com a receita "
                             "das demonstrações")
    if r1 is not None and rec is not None and rec > 0:
        fat = pk.v.get("fator_moeda") or 1.0
        rec_fin = rec / fat
        razao: float | None = r1 / rec_fin
        if pk.v.get("arquetipo") in ("utilidade_regulada", "concessao") and not pk.v.get("financeira"):
            razao = _receita_construcao(pk, params, itens, r1, rec, fat, razao)
        if razao is None:
            pass
        elif 0.5 <= razao <= 2.0:
            g1 = razao - 1
        else:
            pk.lacunas.append(lacuna("g_receita_fy1", f"receita de consenso do ano 1 = {num(razao)}× a receita de 12 "
                                                      "meses (fora de 0,5–2×): unidade, moeda ou perímetro "
                                                      "diferentes; não usada"))
    g2 = None if r1 is None or r2 is None or r1 <= 0 or not (0.5 <= r2 / r1 <= 2.0) else r2 / r1 - 1
    if pk.v.get("receita_consenso_rejeitada"):  # o conceito de receita do consenso não reconcilia com a base
        g2 = None
    pk.put("g_receita_fy1", g1)
    pk.put("g_receita_fy2", g2)
    pk.put("moeda_receita_consenso", m_rec)
    alvo = _conv(_f(row.get("alvo_medio")), fator_linha)
    cons = {
        "ticker": tick, "alvo_medio": r6(alvo), "alvo_mediano": r6(_conv(_f(row.get("alvo_mediano")), fator_linha)),
        "alvo_alto": r6(_conv(_f(row.get("alvo_alto")), fator_linha)),
        "alvo_baixo": r6(_conv(_f(row.get("alvo_baixo")), fator_linha)),
        "n_alvo": _f(row.get("n_analistas_alvo")), "n_eps": _f(row.get("n_analistas_eps")),
        "recomendacao": r6(_f(row.get("recomendacao_media"))), "status_lpa": status,
        "n_eps_linhas": sorted(linhas_n),
    }
    if unidades_declaradas:
        cons.update({"moeda_lpa": m_est, "fator_lpa": r6(fator_lpa),
                     "unidade_metodo": "declaracao_fonte"})
    if tick != linha:
        pk.avisos.append(f"consenso de LPA da linha {tick} ({int(cons['n_eps'] or 0)} analistas), a de mais analistas "
                         "entre as linhas do emissor")
    up = _div(alvo, preco)
    lims = params.sec("qualidade")["upside_limites"]
    cons["upside"] = None if up is None else r6(up - 1)
    cons["plausivel"] = bool(up is not None and lims[0] <= up - 1 <= lims[1])
    if up is not None and not cons["plausivel"]:
        pk.avisos.append("preço-alvo de consenso fora da faixa plausível (provável unidade/moeda): não comparado")
    pk.put("consenso", cons, fonte)
    pk.fontes["consenso_info"] = fonte_info


def _receita_construcao(pk: _Pacote, params: ParametrosCobertura, itens: dict[str, float], r1: float, rec: float,
                       fat: float, razao: float) -> float | None:
    """Utilidades reguladas e concessões: a receita da DRE inclui a receita de construção da
    infraestrutura (ICPC 01, margem ~zero) e o consenso de receita não. Com a receita de construção
    da DVA (CVM), a base dos 12 meses passa a ser a receita sem ela quando isso reconcilia o consenso
    (|crescimento| ≤ limite e menor que contra a receita total); sem essa reconciliação, crescimento de
    consenso acima do limite em módulo não é usado. Devolve a razão consenso ÷ base (ou ``None``)."""
    lim = float(params.sec("projecao").get("g1_consenso_concessao_max_abs", 0.15))
    rc = itens.get("receita_construcao")
    if rc is not None and 0 < rc < 0.6 * rec:
        razao_ex = r1 / ((rec - rc) / fat)
        if abs(razao_ex - 1) <= lim and abs(razao_ex - 1) < abs(razao - 1):
            itens["receita_com_construcao"] = rec
            itens["receita"] = rec - rc
            pk.v["t.receita_com_construcao"] = r6(rec)
            pk.fontes["t.receita_com_construcao"] = pk.fontes.get("t.receita", prov_codigo("receita da DRE"))
            pk.put("t.receita", rec - rc, prov_codigo(
                "receita de 12 meses da DRE − receita de construção da infraestrutura (DVA, ICPC 01)"),
                nome="Receita sem a receita de construção (ICPC 01)", unidade=f"total:{pk.v.get('moeda')}")
            pk.v["receita_ano_anterior"] = None
            pk.lacunas.append(lacuna("g_receita_historico", "crescimento histórico da receita com a receita de "
                                     "construção (não comparável com a base sem ela): não usado"))
            pk.avisos.append(f"receita de construção de {num(rc / rec * 100, 0)}% da receita excluída da base "
                             f"(consenso {num((razao - 1) * 100, 1)}% contra a receita total, {num((razao_ex - 1) * 100, 1)}% "
                             "contra a receita sem construção)")
            pk.put("receita_sem_construcao", True)
            return razao_ex
    if abs(razao - 1) > lim:
        pk.v["receita_consenso_rejeitada"] = True
        pk.lacunas.append(lacuna("g_receita_fy1", (
            f"crescimento de consenso da receita de {num((razao - 1) * 100, 1)}% contra a receita de 12 meses, acima "
            f"de {num(lim * 100, 0)}% em módulo numa concessão ou utilidade regulada (provável receita de construção "
            "da infraestrutura na receita da DRE, sem reconciliação pela DVA): não usado")))
        return None
    return razao


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
            # proventos por ação pagos (data ex) em cada um dos 3 últimos anos-calendário completos (payout
            # anual: a mediana dos 3 anos descarta o ano de uma distribuição extraordinária e independe da
            # data de pagamento); só com histórico de proventos anterior ao primeiro ano (soma completa)
            anos = range(as_of.year - 3, as_of.year)
            vals_all = pd.to_numeric(sub["valor_por_acao"], errors="coerce")
            if (dex < pd.Timestamp(year=anos[0], month=1, day=1)).any():
                pk.put("dps_anual", {str(a): r6(float(vals_all[dex.dt.year == a].dropna().sum())) for a in anos})
            else:
                pk.put("dps_anual", None)
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

def _razao_ajuste(md: MarketData, ticker: str, d: pd.Timestamp) -> float | None:
    """``fechamento ÷ fechamento ajustado`` na última data ≤ ``d`` (muda só com desdobramentos,
    grupamentos, bonificações e proventos)."""
    if ticker not in md.close.columns or ticker not in md.adj_close.columns:
        return None
    c = md.close[ticker].loc[:d].dropna()
    a = md.adj_close[ticker].loc[:d].dropna()
    if c.empty or a.empty or a.iloc[-1] <= 0:
        return None
    return float(c.iloc[-1] / a.iloc[-1])


def desde_por_acoes(md: MarketData, ticker: str, serie: list[list[Any]], limite: float,
                    as_of: date) -> tuple[str | None, str | None]:
    """Última data-base em que as ações em circulação da holding mudaram mais que ``limite`` sem ser
    desdobramento, grupamento ou bonificação (esses o preço ajustado absorve: a razão de ações vezes
    a variação de ``fechamento ÷ ajustado`` fica em 1 ± 3%). Devolve ``(data, motivo)``."""
    pontos = [(pd.Timestamp(d), float(v)) for d, v in serie if v and pd.Timestamp(d) <= pd.Timestamp(as_of)]
    ult = None
    for (d0, n0), (d1, n1) in zip(pontos, pontos[1:], strict=False):
        r = n1 / n0
        if abs(r - 1) <= limite:
            continue
        f0, f1 = _razao_ajuste(md, ticker, d0), _razao_ajuste(md, ticker, d1)
        if f0 and f1 and abs(r * (f1 / f0) - 1) <= 0.03:
            continue
        ult = (d1, f"ações da holding de {n0 / 1e6:,.1f} mi para {n1 / 1e6:,.1f} mi entre {d0.date()} e {d1.date()}"
               .replace(",", "\x00").replace(".", ",").replace("\x00", "."))
    return (None, None) if ult is None else (ult[0].date().isoformat(), ult[1])


def _participacao_conferida(p: dict[str, Any], as_of: date, meses: int = 15,
                            tolerancia: float = 0.01) -> tuple[bool, str]:
    """Fração conferida no documento-fonte: ``conferido`` na curadoria, endereço do documento, data
    de publicação até ``as_of``, data de referência com no máximo ``meses`` de idade e, quando a
    curadoria registra a posição acionária no documento da investida (``fracao_investida``), as
    duas frações a no máximo ``tolerancia`` (``soma_partes.participacao_tolerancia``) uma da outra."""
    if not p.get("conferido"):
        return False, "fração não conferida no documento-fonte"
    if not p.get("url"):
        return False, "sem endereço do documento-fonte"
    dp = p.get("data_publicacao")
    if not dp or str(dp) > as_of.isoformat():
        return False, "documento-fonte sem data de publicação até a data do snapshot"
    dr = p.get("data_referencia")
    if dr and (pd.Timestamp(as_of) - pd.Timestamp(str(dr))).days > meses * 31:
        return False, f"documento-fonte com data de referência {dr} (mais de {meses} meses)"
    fi = _f(p.get("fracao_investida"))
    cruz = ""
    if fi is not None:
        dif = abs(float(p["fracao"]) - fi)
        txt = (f"{pct(float(p['fracao']), 2)} no documento da holding contra {pct(fi, 2)} na posição acionária da "
               f"investida ({p.get('documento_investida') or 'documento da investida'})")
        if dif > tolerancia + 1e-12:
            return False, f"conferência cruzada falhou: {txt}, diferença acima de {pct(tolerancia, 0)}"
        cruz = f"; conferência cruzada: {txt}"
    return True, f"conferida em {p.get('documento')} ({dp}){cruz}"


def preparar_soma_partes(md: MarketData, params: ParametrosCobertura, pacote: dict[str, Any],
                         as_of: date) -> None:
    """Acrescenta ao pacote da holding o NAV de participações listadas e a razão histórica
    (valor de mercado da holding ÷ NAV) em base semanal, que dá o desconto da holding.

    A janela da mediana começa na última mudança do conjunto de participações (``desde`` da
    curadoria) ou na última variação relevante das ações da holding fora de desdobramentos
    (detectada em código pela série de ações das demonstrações): a composição de hoje aplicada a um
    período com outra base acionária ou outras participações distorceria a razão histórica. Cada
    fração cita o documento público (CVM FRE, 20-F na SEC, relatório anual) com as datas."""
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
        conf, conf_txt = _participacao_conferida(p, as_of, tolerancia=float(sp.get("participacao_tolerancia", 0.01)))
        partes.append({"emissor": sub, "linha": st, "fracao": r6(float(p["fracao"])),
                       "base": p.get("base", "capital total"),
                       "valor_mercado": r6(mc), "moeda": ccy, "valor_participacao": r6(valor),
                       "conferido": conf, "conferido_texto": conf_txt,
                       "fracao_investida": r6(_f(p.get("fracao_investida"))),
                       "data_referencia": p.get("data_referencia"), "data_publicacao": p.get("data_publicacao"),
                       "fonte": prov_curadoria(
                           fonte=str(p.get("fonte") or "CONFIG"), url=p.get("url"),
                           documento=p.get("documento"), data_publicacao=p.get("data_publicacao"),
                           arquivo="cobertura/sotp.yaml",
                           sha256_curadoria=params.arquivos.get("cobertura/sotp.yaml"))})
        s = _serie_usd_semanal(md, st, as_of)
        if not s.empty:
            series.append((s / s.iloc[-1]) * valor * fx_m)  # valor em USD ao longo do tempo
    nav = sum(p["valor_participacao"] for p in partes if "valor_participacao" in p) if ok else None
    hs = _serie_usd_semanal(md, hold_line, as_of)
    razao_med = None
    n_sem = 0
    desde_cfg = str(cfg["desde"]) if cfg.get("desde") else None
    desde_acoes, motivo_acoes = desde_por_acoes(md, hold_line, pacote.get("serie_acoes") or [],
                                                float(sp.get("mudanca_acoes_min", 0.05)), as_of)
    desde = max([d for d in (desde_cfg, desde_acoes) if d], default=None)
    if ok and series and not hs.empty and mcap_h is not None and nav:
        nav_usd = pd.concat(series, axis=1).dropna().sum(axis=1)
        mh_usd = (hs / hs.iloc[-1]) * mcap_h * fx_m
        r = (mh_usd / nav_usd).dropna()
        r = r[r.index >= pd.Timestamp(as_of) - pd.DateOffset(years=int(sp["desconto_anos"]))]
        if desde:
            r = r[r.index >= pd.Timestamp(desde)]
        n_sem = len(r)
        if n_sem >= int(sp["desconto_min_semanas"]):
            razao_med = float(r.median())
    pacote["soma_partes"] = {
        "partes": partes, "nav": r6(nav), "valor_mercado_holding": r6(mcap_h),
        "razao_atual": r6(_div(mcap_h, nav)), "razao_mediana": r6(razao_med), "semanas": n_sem,
        "desconto_reserva": float(sp["desconto_reserva"]), "nota": cfg.get("nota", ""),
        "desde": desde, "desde_curadoria": desde_cfg, "desde_acoes": desde_acoes,
        "desde_acoes_motivo": motivo_acoes,
        "conferido": bool(partes) and all(p.get("conferido", False) for p in partes if "fracao" in p),
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
                "documento": (f"série simulada {serie} (DADOS SIMULADOS)" if sim else
                              "Tesouro americano de 10 anos (FRED, série DGS10)" if serie == "USD_10Y"
                              else f"série pública {serie}"),
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
