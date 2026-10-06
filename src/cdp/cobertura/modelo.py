"""Modelo de um emissor: custo de capital, métodos do arquétipo, combinação, rolagem para 12
meses, cenários (Monte Carlo com semente), sensibilidade e o registro aberto de passos.

Função pura de ``(pacote de insumos, contexto transversal, parâmetros, taxa livre de risco)``:
mesmos insumos ⇒ mesmo resultado, byte a byte. A parte transversal (classe de incerteza, pares,
``α_rel``, rating) é feita depois, em :mod:`cdp.cobertura.rating`, sobre todos os emissores.

Cenários (Monte Carlo centrado no caso-base): os choques nos direcionadores têm média zero e o
modelo de cada sorteio preserva a média do caso-base — no fluxo de caixa, a receita do sorteio é
a do caso-base mais o desvio acumulado de crescimento (aditivo), o reinvestimento acompanha o
crescimento adicional de forma simétrica e o choque de preço de commodity é transitório (anos
1–3, revertendo até o ano 5, sem efeito na perpetuidade); o piso de zero (responsabilidade
limitada) vale só para o valor combinado do patrimônio. A diferença entre o retorno ponderado
(PWR) e o retorno do caso-base (ETR) fica restrita à convexidade das fórmulas.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from scipy.stats import norm

from . import metodos as M
from .contexto import beta_pares, prever, roe_alvo, termos_previsao
from .custo_capital import CustoCapital, calcular, real
from .formato import contagem, inteiro, mult, num, operando, pct, pp, preco, r6, total
from .parametros import NOME_METODO, ParametrosCobertura
from .passos import Registro, prov_codigo

METODOS_PATRIMONIAIS = ("rim", "rim_real", "pb_justificado", "regressao_pb_roe")
"""Métodos ancorados no patrimônio por ação (expostos a erro de unidade/moeda em B0)."""
METODOS_LUCRO = ("multiplo_justificado", "ddm", "ddm_real", "regressao_pl")
STATUS_UNIDADES_PT = {
    "demonstrativos": "ações em circulação das demonstrações",
    "demonstrativos_em_unidades": "demonstrações já em unidades negociadas",
    "valor_de_mercado": "valor de mercado público ÷ fechamento",
}
ROTULO_REGRESSOR = {"roe": "ROE", "g": "g", "beta_reg": "β", "payout": "payout", "margem": "margem EBIT",
                    "alavancagem": "DL/EBITDA"}


@dataclass(frozen=True)
class Drivers:
    """Choques nos direcionadores (escalares no caso-base; vetores no Monte Carlo/grades)."""

    d_ke: Any = 0.0
    d_g: Any = 0.0
    d_roe: Any = 0.0          # choque permanente no ROE (grade de sensibilidade)
    d_roe_trans: Any = 0.0    # choque transitório (anos 1–2, convergindo ao ROE de longo prazo; Monte Carlo)
    d_cres: Any = 0.0
    d_marg: Any = 0.0
    d_comm: Any = 0.0
    d_razao: Any = 0.0


def semente(issuer_id: str, as_of: str) -> int:
    return int(hashlib.sha256(f"{issuer_id}|{as_of}".encode()).hexdigest()[:16], 16)


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def d_rt_reg(dr: Drivers) -> np.ndarray:
    return np.asarray(dr.d_roe_trans, dtype=float)


def _zero(x: Any) -> bool:
    return bool(np.all(np.asarray(x, dtype=float) == 0.0))


def _op_pct(x: float | None, casas: int = 2) -> str:
    return operando(pct(x, casas))


class Avaliador:
    """Constrói o modelo aberto de um emissor (ver docstring do módulo)."""

    def __init__(self, pac: Mapping[str, Any], ctx: Mapping[str, Any], params: ParametrosCobertura,
                 rf_ust: float | None, rf_fonte: dict[str, Any]) -> None:
        self.pac = dict(pac)
        self.ctx = ctx
        self.params = params
        self.reg = Registro()
        self.lacunas: list[dict[str, str]] = list(pac.get("lacunas", []))
        self.avisos: list[str] = list(pac.get("avisos", []))
        self.moeda = str(pac["moeda"])
        self.fontes = pac.get("fontes", {})
        self.fund = ctx.get("fundamentos", {}).get(pac["issuer_id"], {})
        self.setor_ctx = ctx.get("setores", {}).get(pac["setor"], {})
        self.univ_ctx = ctx.get("universo", {})
        f_eps = (self.fontes.get("eps_fy1") or {}).get("fonte")
        self.rotulo_consenso = ("consenso público (DADOS SIMULADOS)" if f_eps == "SIMULADO"
                                else "consenso público Yahoo Finance")
        self._registrar_insumos()
        if self.pac.get("d_e_mercado") is None:
            self.pac["d_e_pares"] = self.setor_ctx.get("d_e_mediana") or self.univ_ctx.get("d_e_mediana")
        bp, nbp, lista = beta_pares(ctx, pac["pais"], pac["setor"], int(params.sec("rating")["pares_min"]))
        self.cc: CustoCapital = calcular(self.pac, params, rf_ust, rf_fonte, bp, nbp, self.reg, lista)
        self.metodos: dict[str, dict[str, Any]] = {}
        self._estrito = True
        self._fcff_base: dict[str, M.ResultadoFCFF] = {}
        self._preparar_direcionadores()

    # ------------------------------------------------------------------ utilidades
    def _fonte(self, chave: str) -> list[dict[str, Any]]:
        f = self.fontes.get(chave)
        return [f] if f else []

    def _p(self, x: float | None) -> str:
        return preco(x, self.moeda)

    def _op(self, x: float | None) -> str:
        return operando(preco(x, self.moeda))

    def _t(self, x: float | None) -> str:
        return total(x, self.moeda)

    # ------------------------------------------------------------------ 1. insumos
    def _registrar_insumos(self) -> None:
        p, m = self.pac, self.moeda
        self.reg.nota("insumos.linha", "Linha de valuation",
                      f"{p['linha']} ({p['linha_tipo']}, {m}): {p['linha_motivo']}.")
        if p.get("preco") is not None:
            self.reg.add("insumos.preco", "Preço de referência", "P0 = fechamento oficial da linha",
                         f"P0 = fechamento de {p['linha']} em {p.get('data_preco')}", p["preco"],
                         f"preco:{m}", self._fonte("preco"))
        if p.get("fator_moeda") not in (None, 1.0):
            self.reg.add("insumos.cambio", f"Conversão {p['moeda_demonstrativos']} → {m}",
                         "fator = (USD por 1 moeda das demonstrações) ÷ (USD por 1 moeda da linha)",
                         f"fator = (USD por 1 {p['moeda_demonstrativos']}) ÷ (USD por 1 {m}) em {p.get('as_of')}",
                         p["fator_moeda"], f"fx:{p['moeda_demonstrativos']}/{m}",
                         self._fonte("fx_demonstrativos_para_modelo"))
        if p.get("unidades") is not None:
            apl = _f(p.get("acoes_por_linha")) or 1.0
            self.reg.add("insumos.unidades", "Unidades em circulação da linha",
                         "N = ações em circulação ÷ ações por unidade negociada",
                         f"N = {contagem(float(p['unidades']) * apl)} ÷ {num(apl, 0)}", p["unidades"], "acoes",
                         self._fonte("unidades"),
                         premissas=f"origem: {STATUS_UNIDADES_PT.get(str(p.get('status_unidades')), '')}")
        if p.get("bvps") is not None:
            if p.get("t.patrimonio_controladores") is not None and p.get("unidades"):
                sub = f"B0 = {self._t(p.get('t.patrimonio_controladores'))} ÷ {contagem(p.get('unidades'))}"
            else:
                sub = "B0 = patrimônio por ação do retrato público (sem demonstração)"
            self.reg.add("insumos.bvps", "Patrimônio líquido por unidade (B0)",
                         "B0 = patrimônio dos controladores ÷ N", sub,
                         p["bvps"], f"preco:{m}", self._fonte("t.patrimonio_controladores") or self._fonte("bvps"))
        if p.get("eps_ttm") is not None:
            self.reg.add("insumos.eps_ttm", "Lucro por unidade dos últimos 12 meses",
                         "LPA_12m = lucro dos controladores (12 meses) ÷ N",
                         f"LPA_12m = {self._t(p.get('t.lucro_liquido_controladores'))} ÷ {contagem(p.get('unidades'))}",
                         p["eps_ttm"], f"preco:{m}", self._fonte("t.lucro_liquido_controladores"))
        for k, t, n in (("eps_fy1", "LPA de consenso (ano 1)", 1), ("eps_fy2", "LPA de consenso (ano 2)", 2)):
            if p.get(k) is not None:
                self.reg.add(f"insumos.{k}", t, f"LPA_{n} = consenso público por unidade da linha",
                             f"LPA_{n} = {self.rotulo_consenso}", p[k], f"preco:{m}", self._fonte(k))
        if p.get("dps_12m") is not None:
            self.reg.add("insumos.dps", "Dividendos por unidade (12 meses)",
                         "DPS_12m = Σ proventos com data ex nos últimos 12 meses",
                         f"DPS_12m = soma dos proventos com data ex nos 12 meses até {p.get('as_of')}",
                         p["dps_12m"], f"preco:{m}", self._fonte("dps_12m"))
        if p.get("divida_liquida") is not None:
            partes = []
            for k, s in (("t.divida_bruta", "+"), ("t.arrendamentos", "+"), ("t.caixa", "−"),
                         ("t.aplicacoes_cp", "−")):
                if p.get(k) is not None:
                    partes.append((s, self._t(p[k])))
            if p.get("t.divida_bruta") is not None and p.get("t.caixa") is not None:
                expr = partes[0][1] + "".join(f" {s} {v}" for s, v in partes[1:])
                sub = f"DL = {expr}"
            else:
                sub = "DL = dívida líquida reportada"
            self.reg.add("insumos.divida_liquida", "Dívida líquida",
                         "DL = dívida bruta + arrendamentos − caixa − aplicações de curto prazo",
                         sub, p["divida_liquida"], f"total:{m}", self._fonte("divida_liquida"))

    # ------------------------------------------------------------------ 2. direcionadores
    def _preparar_direcionadores(self) -> None:
        p, cc, reg = self.pac, self.cc, self.reg
        proj = self.params.sec("projecao")
        lo_g, hi_g = proj["crescimento_limites"]
        shrink = float(proj["encolhimento_crescimento"])
        g_set = _f(self.setor_ctx.get("g_mediana"))
        g_set_txt = "mediana do setor"
        if g_set is None:
            g_set, g_set_txt = _f(self.univ_ctx.get("g_mediana")), "mediana do universo"
        self.b0 = _f(p.get("bvps"))
        self.eps_ttm = _f(p.get("eps_ttm"))
        eps1 = _f(p.get("eps_fy1"))
        self.eps1_fonte = "consenso"
        if eps1 is None and self.eps_ttm is not None:
            eps1 = self.eps_ttm
            self.eps1_fonte = "lucro dos últimos 12 meses (sem consenso)"
            self.avisos.append("LPA do ano 1 = lucro dos últimos 12 meses (consenso indisponível)")
        self.eps1 = eps1
        # crescimento próprio (consenso de receita, senão histórico) encolhido para o setor
        g_cons = _f(p.get("g_receita_fy1"))
        g_hist = _f(p.get("g_receita_historico"))
        lim_txt = f"limitado a [{pct(lo_g, 0)}; {pct(hi_g, 0)}]"
        if g_cons is not None:
            g1 = g_cons
            sub1 = f"g1 = mín(máx({pct(g_cons)}; {pct(lo_g, 0)}); {pct(hi_g, 0)})"
            prem1 = f"crescimento de consenso da receita do ano 1 ({self.rotulo_consenso}), {lim_txt}"
        elif g_hist is not None and g_set is not None:
            g1 = (1 - shrink) * g_hist + shrink * g_set
            sub1 = f"g1 = {num(1 - shrink)} × {_op_pct(g_hist)} + {num(shrink)} × {_op_pct(g_set)}"
            prem1 = (f"receita dos últimos 12 meses contra 12 meses antes ({pct(g_hist)}) encolhida para a "
                     f"{g_set_txt} ({pct(g_set)}), {lim_txt}")
        elif g_hist is not None:
            g1, sub1, prem1 = g_hist, f"g1 = {pct(g_hist)}", "receita dos últimos 12 meses contra 12 meses antes"
        elif g_set is not None:
            g1, sub1, prem1 = g_set, f"g1 = {pct(g_set)}", f"{g_set_txt} (sem crescimento próprio)"
        else:
            g1, sub1, prem1 = None, "", ""
        g1 = None if g1 is None else min(max(g1, lo_g), hi_g)
        g2c = _f(p.get("g_receita_fy2"))
        if g2c is not None:
            g2 = min(max(g2c, lo_g), hi_g)
            sub2 = f"g2 = mín(máx({pct(g2c)}; {pct(lo_g, 0)}); {pct(hi_g, 0)})"
            prem2 = f"crescimento de consenso da receita do ano 2 ({self.rotulo_consenso})"
        elif g1 is not None:
            alvo2 = g_set if g_set is not None else g1
            g2 = min(max((1 - shrink) * g1 + shrink * alvo2, lo_g), hi_g)
            sub2 = f"g2 = {num(1 - shrink)} × {_op_pct(g1)} + {num(shrink)} × {_op_pct(alvo2)}"
            prem2 = f"média de g1 com a {g_set_txt}"
        else:
            g2, sub2, prem2 = None, "", ""
        self.g1, self.g2 = g1, g2
        usa_g = not p.get("financeira") or _f(p.get("eps_fy2")) is None  # financeiras: só para LPA_2 sem consenso
        if g1 is not None and usa_g:
            reg.add("dir.g1", "Crescimento da receita — ano 1", "g1 = crescimento próprio, limitado à faixa da projeção",
                    sub1, g1, "%", premissas=prem1)
            reg.add("dir.g2", "Crescimento da receita — ano 2",
                    "g2 = consenso (ano 2) ou média de g1 com a mediana do setor", sub2, g2, "%", premissas=prem2)
        # payout: dividendos pagos ÷ lucro (DFC, 12 meses); senão proventos ÷ LPA; senão o setor
        divp, luc = _f(p.get("t.dividendos_pagos")), _f(p.get("t.lucro_liquido_controladores"))
        if divp is not None and luc is not None and luc > 0:
            pay = min(max(abs(divp) / luc, 0.0), 1.0)
            pay_sub = f"k = mín({self._t(abs(divp))} ÷ {self._t(luc)}; 1)"
            pay_prem = "dividendos pagos ÷ lucro dos controladores (12 meses)"
        else:
            pay = _f(self.fund.get("payout"))
            dps_, eps_ref = _f(p.get("dps_12m")), (self.eps1 if self.eps1 is not None else self.eps_ttm)
            pay_sub = (f"k = mín({self._p(dps_)} ÷ {self._p(eps_ref)}; 1)" if pay is not None and dps_ is not None
                       and eps_ref else f"k = {pct(pay)}")
            pay_prem = "proventos dos últimos 12 meses ÷ LPA de referência"
        if pay is None:
            pay = _f(self.setor_ctx.get("payout_mediana")) or _f(self.univ_ctx.get("payout_mediana"))
            pay_sub, pay_prem = f"k = {pct(pay)}", "mediana do setor (payout próprio indisponível)"
        self.payout = pay
        if pay is not None:
            reg.add("dir.payout", "Payout", "k = dividendos ÷ lucro, limitado a [0; 1]", pay_sub, pay, "%",
                    self._fonte("t.dividendos_pagos"), premissas=pay_prem)
        # ROE ano 1/2 e ROE de convergência
        self.roe1 = self.roe2 = self.roe_alvo = None
        if self.b0 is not None and self.b0 > 0 and self.eps1 is not None and pay is not None:
            self.roe1 = self.eps1 / self.b0
            b1 = self.b0 + self.eps1 * (1 - (pay if self.eps1 > 0 else 0.0))
            eps2 = _f(p.get("eps_fy2"))
            if eps2 is None and g2 is not None:
                eps2 = self.eps1 * (1 + g2)
            self.eps2 = eps2
            self.roe2 = None if eps2 is None or b1 <= 0 else eps2 / b1
            ra, ra_txt, comps = roe_alvo(self.ctx, p["pais"], p["setor"], _f(self.fund.get("roe_hist")))
            ra_sub = ""
            if comps:
                expr = pct(comps[0][1])
                for _, v, _n in comps[1:]:
                    expr = f"0,5 × {'(' + expr + ')' if ' ' in expr else expr} + 0,5 × {pct(v)}"
                ra_sub = f"ROE_alvo = {expr}"
            ra_prem = "; ".join(f"{lab} {pct(v)}" + (f" ({n} emissores)" if n else "") for lab, v, n in comps)
            if ra is None:
                ra = _f(self.univ_ctx.get("roe_mediana"))
                ra_txt, ra_sub, ra_prem = "mediana do universo", f"ROE_alvo = {pct(ra)}", "mediana do ROE do universo"
            self.roe_alvo = ra
            reg.add("dir.roe1", "ROE do ano 1", "ROE_1 = LPA_1 ÷ B0",
                    f"ROE_1 = {self._p(self.eps1)} ÷ {self._p(self.b0)}", self.roe1, "%",
                    premissas=f"LPA_1: {self.eps1_fonte}")
            if self.roe2 is not None:
                reg.add("dir.roe2", "ROE do ano 2", "ROE_2 = LPA_2 ÷ B1, B1 = B0 + LPA_1 × (1 − k)",
                        f"ROE_2 = {self._p(eps2)} ÷ {self._p(b1)}", self.roe2, "%")
            if ra is not None:
                reg.add("dir.roe_alvo", "ROE de convergência (ano 12)",
                        "ROE_alvo = mediana setorial de longo prazo, encolhida para país × setor e para o histórico "
                        "próprio", ra_sub, ra, "%", premissas=f"{ra_txt}: {ra_prem}")
        else:
            self.eps2 = _f(p.get("eps_fy2"))
        self.payout_sust = None
        if self.roe_alvo is not None and self.roe_alvo > cc.g and pay is not None:
            self.payout_sust = min(max(1 - cc.g / self.roe_alvo, 0.0), 1.0)
            reg.add("dir.payout_sust", "Payout sustentável (convergência do lucro residual)",
                    "k_sust = 1 − g ÷ ROE_alvo (reinvestimento que sustenta o crescimento de longo prazo)",
                    f"k_sust = 1 − {pct(cc.g)} ÷ {pct(self.roe_alvo)}", self.payout_sust, "%")
        elif pay is not None:
            self.payout_sust = pay
        self.lpa_diverge = False
        if self.eps1 is not None and self.eps_ttm is not None and self.eps1_fonte == "consenso":
            if (self.eps1 > 0) != (self.eps_ttm > 0) or (self.eps_ttm > 0 and not 0.2 <= self.eps1 / self.eps_ttm <= 5):
                self.lpa_diverge = True
                self.avisos.append("LPA de consenso diverge do lucro dos últimos 12 meses (sinal ou ordem de grandeza)")
        self.roe_sust = None
        if self.roe2 is not None and self.roe_alvo is not None:
            self.roe_sust = 0.5 * self.roe2 + 0.5 * self.roe_alvo
            reg.add("dir.roe_sust", "ROE sustentável", "ROE_sust = (ROE_2 + ROE_alvo) ÷ 2",
                    f"ROE_sust = ({pct(self.roe2)} + {_op_pct(self.roe_alvo)}) ÷ 2", self.roe_sust, "%")
        # dividendos esperados nos próximos 12 meses
        dps_trail = _f(p.get("dps_12m"))
        if self.eps1 is not None and self.eps1 > 0 and pay is not None:
            self.dps12 = self.eps1 * pay
            dtxt, dprem = f"DPS12 = {self._p(self.eps1)} × {pct(pay)}", "LPA_1 × payout"
        elif dps_trail is not None:
            self.dps12 = dps_trail
            dtxt, dprem = "DPS12 = proventos dos últimos 12 meses", "lucro esperado não positivo ou payout indisponível"
        else:
            self.dps12 = 0.0 if (self.eps1 is not None and self.eps1 <= 0) else None
            dtxt, dprem = "DPS12 = 0 (lucro esperado não positivo)", "sem lucro para distribuir"
        if self.dps12 is not None:
            reg.add("dir.dps12", "Dividendos esperados em 12 meses", "DPS12 = LPA_1 × k", dtxt, self.dps12,
                    f"preco:{self.moeda}", premissas=dprem)
        else:
            self.lacunas.append({"insumo": "dps12", "nome": "dividendo esperado",
                                 "motivo": "dividendo esperado indisponível"})
        # margens e ROIC (não financeiras)
        rec = _f(p.get("t.receita"))
        self.receita0 = rec
        self.margem = _f(self.fund.get("margem"))
        self.margem_hist = _f(self.fund.get("margem_hist"))
        self.margem_sd = _f(self.fund.get("margem_sd"))
        ebit = _f(p.get("t.ebit"))
        nd = _f(p.get("divida_liquida"))
        pl = _f(p.get("t.patrimonio_controladores"))
        self.roic0 = None
        if ebit is not None and pl is not None and nd is not None and pl + nd > 0:
            roic = ebit * (1 - cc.imposto) / (pl + nd)
            lo, hi = proj["roic_limites"]
            self.roic0 = min(max(roic, lo), hi)
            reg.add("dir.roic", "Retorno sobre o capital investido (ROIC)",
                    "ROIC = EBIT × (1 − t) ÷ (patrimônio + dívida líquida), limitado a [0%; 60%]",
                    f"ROIC = mín(máx({self._t(ebit)} × (1 − {pct(cc.imposto)}) ÷ ({self._t(pl)} + "
                    f"{operando(self._t(nd))}); 0%); 60%)", self.roic0, "%", self._fonte("t.ebit"))
        # reinvestimento observado (anos 1–2 do fluxo de caixa): 1 − (CFO − capex) ÷ NOPAT
        self.rr_obs = self.fcf_obs = None
        cfo, capex = _f(p.get("t.cfo")), _f(p.get("t.capex"))
        if not p.get("financeira") and cfo is not None and capex is not None:
            self.fcf_obs = cfo - abs(capex)
            if ebit is not None and ebit > 0:
                self.rr_obs = 1 - self.fcf_obs / (ebit * (1 - cc.imposto))
                reg.add("dir.reinvestimento", "Reinvestimento observado (anos 1–2 do fluxo de caixa)",
                        "RR_obs = 1 − (CFO − capex) ÷ (EBIT × (1 − t))",
                        f"RR_obs = 1 − ({self._t(cfo)} − {self._t(abs(capex))}) ÷ ({self._t(ebit)} × "
                        f"(1 − {pct(cc.imposto)}))", self.rr_obs, "%",
                        self._fonte("t.cfo") + self._fonte("t.capex"),
                        premissas="dos anos 3 a 10 o reinvestimento converge linearmente para g ÷ RONIC")
        if self.rr_obs is None and not p.get("financeira"):
            self.avisos.append("FCFF sem reinvestimento observado (CFO ou capex não publicados, ou EBIT não positivo): "
                               "reinvestimento = g ÷ RONIC desde o ano 1")
        # RONIC de longo prazo: média do ROIC próprio com a mediana do setor, nunca abaixo do WACC
        self.ronic_final = None
        if cc.wacc is not None:
            rs = _f(self.setor_ctx.get("roic_pre_mediana"))
            rs = None if rs is None else rs * (1 - cc.imposto)
            partes = [x for x in (self.roic0, rs) if x is not None]
            alvo = float(np.mean(partes)) if partes else cc.wacc
            lo, hi = proj["roic_limites"]
            self.ronic_final = max(min(alvo, hi), cc.wacc)
            media = (f"({' + '.join(pct(x) for x in partes)}) ÷ {len(partes)}" if len(partes) > 1
                     else (pct(partes[0]) if partes else pct(cc.wacc)))
            reg.add("dir.ronic", "Retorno sobre o capital novo na perpetuidade (RONIC)",
                    "RONIC = máx(WACC; (ROIC próprio + ROIC mediano do setor após IR) ÷ 2)",
                    f"RONIC = máx({pct(cc.wacc)}; {media})", self.ronic_final, "%",
                    premissas="ROIC próprio e mediana setorial do ROIC antes de IR × (1 − t)")

    # ------------------------------------------------------------------ 3. métodos
    def _ke(self, dr: Drivers) -> np.ndarray:
        return np.asarray(self.cc.ke + np.asarray(dr.d_ke, dtype=float))

    def _g(self, dr: Drivers, ke: np.ndarray) -> np.ndarray:
        g = self.cc.g + np.asarray(dr.d_g, dtype=float)
        lim = float(self.params.sec("perpetuidade")["spread_min_ke_g"])
        return np.minimum(g, ke - lim)

    def valores(self, dr: Drivers) -> dict[str, np.ndarray]:
        """V0 de cada método disponível sob os choques ``dr`` (vetorizado)."""
        out: dict[str, np.ndarray] = {}
        for m in self.metodos_validos():
            out[m] = self._valor_metodo(m, dr)
        return out

    def metodos_validos(self) -> list[str]:
        return [m for m, d in self.metodos.items() if d.get("valor") is not None and d["peso"] > 0]

    def _valor_metodo(self, m: str, dr: Drivers) -> np.ndarray:
        cc = self.cc
        ke = self._ke(dr)
        g = self._g(dr, ke)
        proj = self.params.sec("projecao")
        d_rt = np.asarray(dr.d_roe_trans, dtype=float)
        d_rs = np.asarray(dr.d_roe, dtype=float) + 0.5 * d_rt   # ROE_sust = (ROE_2 + ROE_alvo) ÷ 2
        if m in ("rim", "rim_real"):
            r1 = self.roe1 + np.asarray(dr.d_roe) + d_rt
            r2 = self.roe2 + np.asarray(dr.d_roe) + d_rt
            ra = self.roe_alvo + np.asarray(dr.d_roe)
            if m == "rim_real":
                pi = cc.pi_local
                kr = (1 + ke) / (1 + pi) - 1
                return M.rim_gls(self.b0, real(r1, pi), real(r2, pi), real(ra, pi), kr, self.payout,
                                 int(proj["anos_rim"]), self.payout_sust).valor
            return M.rim_gls(self.b0, r1, r2, ra, ke, self.payout, int(proj["anos_rim"]), self.payout_sust).valor
        if m == "pb_justificado":
            rs = self.roe_sust + d_rs
            return M.pb_gordon(rs, ke, g, self._estrito) * self.b0
        if m == "multiplo_justificado":
            # P/L justificado é hiperbólico no ROE (1 − g ÷ ROE): o choque de ROE entra pela
            # derivada (resposta linear, média preservada); ke e g pela fórmula exata
            base = M.pl_justificado(self.roe_sust, ke, g, self._estrito)
            deriv = (g / self.roe_sust ** 2) / (ke - g)
            return (base + deriv * d_rs) * self.eps1
        if m in ("ddm", "ddm_real"):
            rs = self.roe_sust + d_rs
            g1 = np.clip(rs * (1 - self.payout), -0.05, 0.15)
            dps1 = self.eps1 * self.payout * (1 + d_rs / max(self.roe_sust, 1e-6))
            if m == "ddm_real":
                pi = cc.pi_local
                return M.ddm_dois_estagios(dps1, real(g1, pi), real(g, pi), (1 + ke) / (1 + pi) - 1,
                                           int(proj["anos_ddm"]), self._estrito)
            return M.ddm_dois_estagios(dps1, g1, g, ke, int(proj["anos_ddm"]), self._estrito)
        if m in ("fcff", "fcff_real", "fcff_vida_finita", "fcff_normalizado"):
            return self._fcff(m, dr).ev_equity
        if m in ("regressao_pb_roe", "regressao_pl", "regressao_ev_receita"):
            return self._regressao(m, dr)
        if m == "soma_partes":
            return np.asarray(self._sotp_base * (1 + np.asarray(dr.d_razao, dtype=float)))
        raise KeyError(m)

    class _F:
        def __init__(self, res: M.ResultadoFCFF, eq: np.ndarray) -> None:
            self.res, self.ev_equity = res, eq

    def _fcff_args(self, m: str) -> dict[str, Any]:
        """Argumentos do caso-base do FCFF (escalares; termos reais no ``fcff_real``)."""
        cc = self.cc
        proj = self.params.sec("projecao")
        phi = float(self.params.valuation["fade_phi"].get(self.pac["setor"], 0.85))
        margem = self.margem_hist if m == "fcff_normalizado" and self.margem_hist is not None else self.margem
        spread = float(self.params.sec("perpetuidade")["spread_min_ke_g"])
        gt = min(cc.g, cc.wacc - spread)
        roic0 = self.roic0 if self.roic0 is not None else cc.wacc
        vida = None
        if m == "fcff_vida_finita" and self.pac.get("fim_concessao"):
            vida = int(self.pac["fim_concessao"]) - date.fromisoformat(self.pac["as_of"]).year
        a = {"receita0": self.receita0, "g1": self.g1, "g2": self.g2, "g_term": gt, "phi": phi, "margem": margem,
             "imposto": cc.imposto, "roic0": roic0, "wacc": cc.wacc, "anos": int(proj["anos_explicitos"]),
             "vida": vida, "reinvest_lim": tuple(proj["reinvestimento_limites"]), "ronic_final": self.ronic_final,
             "reinvest_obs": self.rr_obs}
        if m == "fcff_real":
            pi = cc.pi_local
            a.update({"g1": real(self.g1, pi), "g2": real(self.g2, pi), "g_term": real(gt, pi),
                      "roic0": real(roic0, pi), "wacc": real(cc.wacc, pi),
                      "ronic_final": None if self.ronic_final is None else real(self.ronic_final, pi)})
        return a

    def _fcff(self, m: str, dr: Drivers) -> _F:
        cc = self.cc
        a = self._fcff_args(m)
        if all(_zero(x) for x in (dr.d_ke, dr.d_g, dr.d_cres, dr.d_marg, dr.d_comm)):
            if m not in self._fcff_base:
                self._fcff_base[m] = M.fcff_tres_estagios(**a)
            res = self._fcff_base[m]
        else:
            lo_g, hi_g = self.params.sec("projecao")["crescimento_limites"]
            spread = float(self.params.sec("perpetuidade")["spread_min_ke_g"])
            d_ke = np.asarray(dr.d_ke, dtype=float)
            # choque no custo do capital próprio: o WACC varia pela fração de capital próprio
            peso_e = 1.0 - (cc.peso_divida or 0.0)
            wacc_n = cc.wacc + peso_e * d_ke
            gt_n = np.minimum(np.minimum(cc.g + np.asarray(dr.d_g, dtype=float), cc.ke + d_ke - spread),
                              wacc_n - spread)
            g1_n = np.clip(self.g1 + np.asarray(dr.d_cres, dtype=float), lo_g, hi_g)
            g2_n = np.clip(self.g2 + np.asarray(dr.d_cres, dtype=float), lo_g, hi_g)
            if m == "fcff_real":
                pi = cc.pi_local
                g1_n, g2_n, gt_n, wacc_n = real(g1_n, pi), real(g2_n, pi), real(gt_n, pi), real(wacc_n, pi)
            trans = None
            if m == "fcff_normalizado" and not _zero(dr.d_comm):
                mc = self.params.sec("cenarios")["monte_carlo"]
                n_anos = a["anos"] if a["vida"] is None else a["vida"]
                w = M.perfil_transitorio(n_anos, int(mc.get("commodity_anos_plenos", 3)),
                                         int(mc.get("commodity_zero_em", 5)))
                c = np.asarray(dr.d_comm, dtype=float)
                trans = w.reshape((-1,) + (1,) * c.ndim) * c[None, ...]
            cen = M.CenarioFCFF(g1=g1_n, g2=g2_n, g_term=gt_n, wacc=wacc_n,
                                d_margem=np.asarray(dr.d_marg, dtype=float), d_margem_trans=trans)
            res = M.fcff_tres_estagios(**a, cenario=cen)
        nd = float(self.pac["divida_liquida"])
        mino = float(self.pac["minoritarios"])
        eq = (res.ev - nd - mino) / float(self.pac["unidades"])
        return self._F(res, eq)

    def _regressao(self, m: str, dr: Drivers) -> np.ndarray:
        regs = self.ctx.get("regressoes", {})
        f = dict(self.fund)
        if m == "regressao_pb_roe":
            r = regs.get("pb_financeiras" if self.pac["financeira"] else "pb_nao_financeiras")
            base = prever(r, f, self.pac["pais"])
            coef = dict(zip(r["colunas"], r["coef"], strict=False)) if r and r.get("disponivel") else {}
            mult_ = base + coef.get("roe", 0.0) * (np.asarray(dr.d_roe, dtype=float) + d_rt_reg(dr))
            return mult_ * self.b0
        if m == "regressao_pl":
            r = regs.get("pl")
            base = prever(r, f, self.pac["pais"])
            coef = dict(zip(r["colunas"], r["coef"], strict=False))
            mult_ = base + coef.get("g", 0.0) * np.asarray(dr.d_cres, dtype=float)
            return mult_ * self.eps1
        r = regs.get("ev_receita")
        base = prever(r, f, self.pac["pais"])
        coef = dict(zip(r["colunas"], r["coef"], strict=False))
        mult_ = base + coef.get("margem", 0.0) * np.asarray(dr.d_marg, dtype=float) \
            + coef.get("g", 0.0) * np.asarray(dr.d_cres, dtype=float)
        ev = mult_ * self.receita0
        return (ev - float(self.pac["divida_liquida"]) - float(self.pac["minoritarios"])) \
            / float(self.pac["unidades"])

    # ------------------------------------------------------------------ disponibilidade + passos
    def preparar_metodos(self) -> None:
        pesos = self.params.pesos(self.pac["arquetipo"])
        base = Drivers()
        for m, w in pesos.items():
            info: dict[str, Any] = {"m": m, "nome": NOME_METODO[m], "peso": w, "valor": None,
                                    "motivo": None, "fracao_terminal": None, "projecao": []}
            motivo = self._requisitos(m)
            if motivo is None:
                try:
                    v = float(np.asarray(self._valor_metodo(m, base)))
                    if not math.isfinite(v):
                        motivo = "valor não finito"
                    elif v <= 0:
                        motivo = "valor do patrimônio não positivo"
                    else:
                        info["valor"] = v
                except (ValueError, ZeroDivisionError, TypeError) as exc:
                    motivo = str(exc)
            if motivo is None:
                ft = self._passos_metodo(m, info)
                q = self.params.sec("qualidade")
                if ft is not None and ft > float(q["tv_bloqueio"]):
                    motivo = f"valor terminal responde por {pct(ft, 0)} do valor (acima de {pct(q['tv_bloqueio'], 0)})"
                    info["valor"] = None
                elif ft is not None and ft > float(q["tv_aviso"]):
                    self.avisos.append(f"{NOME_METODO[m]}: valor terminal = {pct(ft, 0)} do valor")
            if motivo is not None:
                info["motivo"] = motivo
                info["valor"] = None
                self.reg.nota(f"metodo.{m}", NOME_METODO[m], f"Indisponível: {motivo}.")
            self.metodos[m] = info

    def _requisitos(self, m: str) -> str | None:
        p = self.pac
        need_rim = (self.b0, self.roe1, self.roe2, self.roe_alvo, self.payout)
        if m in ("rim", "rim_real"):
            if self.b0 is None:
                return "patrimônio por ação indisponível"
            if self.b0 <= 0:
                return "patrimônio líquido negativo"
            if any(x is None for x in need_rim):
                return "LPA, payout ou ROE de convergência indisponível"
            return None
        if m in ("pb_justificado",):
            if self.b0 is None or self.b0 <= 0 or self.roe_sust is None:
                return "patrimônio ou ROE sustentável indisponível"
            return None
        if m == "multiplo_justificado":
            if self.eps1 is None or self.eps1 <= 0 or self.roe_sust is None:
                return "LPA positivo ou ROE sustentável indisponível"
            return None
        if m in ("ddm", "ddm_real"):
            if self.eps1 is None or self.eps1 <= 0 or self.payout is None or not self.payout or self.roe_sust is None:
                return "LPA positivo, payout ou ROE sustentável indisponível"
            return None
        if m.startswith("fcff"):
            if p["financeira"]:
                return "fluxo de caixa da firma não se aplica a financeiras"
            faltam = [n for n, v in (("receita", self.receita0), ("margem EBIT", self.margem),
                                     ("crescimento", self.g1), ("dívida líquida", _f(p.get("divida_liquida"))),
                                     ("participação de não controladores", _f(p.get("minoritarios"))),
                                     ("unidades", _f(p.get("unidades"))), ("WACC", self.cc.wacc)) if v is None]
            if faltam:
                return "indisponível: " + ", ".join(faltam)
            return None
        if m == "regressao_pb_roe":
            r = self.ctx.get("regressoes", {}).get("pb_financeiras" if p["financeira"] else "pb_nao_financeiras")
            if not r or not r.get("disponivel"):
                return "regressão transversal indisponível" + (f" ({r.get('motivo')})" if r else "")
            if self.b0 is None or self.b0 <= 0 or prever(r, self.fund, p["pais"]) is None:
                return "fundamentos do emissor incompletos para a regressão"
            return None
        if m == "regressao_pl":
            r = self.ctx.get("regressoes", {}).get("pl")
            if not r or not r.get("disponivel"):
                return "regressão transversal indisponível" + (f" ({r.get('motivo')})" if r else "")
            if self.eps1 is None or self.eps1 <= 0 or prever(r, self.fund, p["pais"]) is None:
                return "fundamentos do emissor incompletos para a regressão"
            return None
        if m == "regressao_ev_receita":
            r = self.ctx.get("regressoes", {}).get("ev_receita")
            if not r or not r.get("disponivel"):
                return "regressão transversal indisponível" + (f" ({r.get('motivo')})" if r else "")
            if _f(p.get("minoritarios")) is None:
                return "participação de não controladores não publicada"
            if (self.receita0 is None or _f(p.get("divida_liquida")) is None or _f(p.get("unidades")) is None
                    or prever(r, self.fund, p["pais"]) is None):
                return "fundamentos do emissor incompletos para a regressão"
            return None
        if m == "soma_partes":
            sp = p.get("soma_partes")
            if not sp or sp.get("nav") is None:
                return "participações sem preço ou não curadas"
            preco_ = _f(p.get("preco"))
            rm, ra = _f(sp.get("razao_mediana")), _f(sp.get("razao_atual"))
            if preco_ is not None and rm is not None and ra:
                self._sotp_base = preco_ * rm / ra
            elif _f(p.get("unidades")):
                self._sotp_base = float(sp["nav"]) * (1 - float(sp["desconto_reserva"])) / float(p["unidades"])
            else:
                return "unidades da holding indisponíveis"
            return None
        return f"método desconhecido {m}"

    def _fmt_regressor(self, k: str, v: float) -> str:
        if k.startswith("pais_") or k == "const":
            return num(v, 0)
        if k in ("roe", "g", "payout", "margem"):
            return operando(pct(v))
        return operando(num(v))

    def _passos_metodo(self, m: str, info: dict[str, Any]) -> float | None:
        """Registra a fórmula substituída do método no caso-base; devolve a fração terminal."""
        cc, reg, P, Op = self.cc, self.reg, self._p, self._op
        proj = self.params.sec("projecao")
        v = info["valor"]
        nome = NOME_METODO[m]
        if m in ("rim", "rim_real"):
            pi = cc.pi_local
            realm = m == "rim_real"
            ke = cc.ke_real if realm else cc.ke
            r1, r2, ra = ((real(self.roe1, pi), real(self.roe2, pi), real(self.roe_alvo, pi)) if realm
                          else (self.roe1, self.roe2, self.roe_alvo))
            res = M.rim_gls(self.b0, r1, r2, ra, ke, self.payout, int(proj["anos_rim"]), self.payout_sust)
            info["projecao"] = [{"ano": t, "roe": r6(float(res.roe[t - 1])), "b_inicio": r6(float(res.b[t - 1])),
                                 "lucro_residual": r6(float(res.ri[t - 1])),
                                 "vp": r6(float(res.ri[t - 1] / (1 + ke) ** t)),
                                 "texto": {"roe": pct(float(res.roe[t - 1])), "b_inicio": P(float(res.b[t - 1])),
                                           "lucro_residual": P(float(res.ri[t - 1])),
                                           "vp": P(float(res.ri[t - 1] / (1 + ke) ** t))}}
                                for t in range(1, len(res.ri) + 1)]
            ft = float(res.fracao_terminal)
            info["fracao_terminal"] = r6(ft)
            sufixo = " (termos reais)" if realm else ""
            n = int(proj["anos_rim"])
            reg.add(f"metodo.{m}", nome + sufixo,
                    f"V0 = B0 + Σ_{{t=1..{n}}} (ROE_t − ke) × B_{{t−1}} ÷ (1 + ke)^t + (ROE_alvo − ke) × B_{n} ÷ "
                    f"(ke × (1 + ke)^{n})",
                    f"V0 = {P(self.b0)} + {Op(float(res.pv_explicito))} + {Op(float(res.pv_terminal))}",
                    v, f"preco:{self.moeda}",
                    premissas=(f"parcelas: patrimônio por ação, valor presente do lucro residual dos anos 1–{n} e da "
                               f"perpetuidade; ROE {pct(r1)} → {pct(r2)} → {pct(ra)} no ano {n}; ke {pct(ke)}; "
                               f"payout {pct(self.payout)} → {pct(self.payout_sust)}"))
            return ft
        if m == "pb_justificado":
            pb = float(M.pb_gordon(self.roe_sust, cc.ke, cc.g))
            reg.add(f"metodo.{m}", nome, "V0 = B0 × (ROE_sust − g) ÷ (ke − g)",
                    f"V0 = {P(self.b0)} × ({pct(self.roe_sust)} − {pct(cc.g)}) ÷ ({pct(cc.ke)} − {pct(cc.g)})",
                    v, f"preco:{self.moeda}", premissas=f"P/VPA justificado = {mult(pb)}")
            return None
        if m == "multiplo_justificado":
            pe = float(M.pl_justificado(self.roe_sust, cc.ke, cc.g))
            reg.add(f"metodo.{m}", nome, "V0 = LPA_1 × (1 − g ÷ ROE_sust) ÷ (ke − g)",
                    f"V0 = {P(self.eps1)} × (1 − {pct(cc.g)} ÷ {pct(self.roe_sust)}) ÷ ({pct(cc.ke)} − {pct(cc.g)})",
                    v, f"preco:{self.moeda}", premissas=f"P/L justificado = {mult(pe)}")
            return None
        if m in ("ddm", "ddm_real"):
            g1 = min(max(self.roe_sust * (1 - self.payout), -0.05), 0.15)
            dps1 = self.eps1 * self.payout
            realm = m == "ddm_real"
            ke = cc.ke_real if realm else cc.ke
            gg = real(cc.g, cc.pi_local) if realm else cc.g
            g1r = real(g1, cc.pi_local) if realm else g1
            n = int(proj["anos_ddm"])
            d, pv1 = dps1, 0.0
            for t in range(1, n + 1):
                pv1 += d / (1 + ke) ** t
                if t < n:
                    d *= 1 + g1r
            pvt = d * (1 + gg) / ((ke - gg) * (1 + ke) ** n)
            reg.add(f"metodo.{m}", nome,
                    f"V0 = Σ_{{t=1..{n}}} DPS_1 × (1 + g1)^(t−1) ÷ (1 + ke)^t + DPS_{n + 1} ÷ ((ke − g) × (1 + ke)^{n})",
                    f"V0 = {P(pv1)} + {P(pvt)}", v, f"preco:{self.moeda}",
                    premissas=(f"parcelas: dividendos dos anos 1–{n} e perpetuidade, a valor presente; DPS_1 = "
                               f"{P(dps1)} (LPA_1 × payout); g1 = ROE_sust × (1 − k) = {pct(g1r)}; g = {pct(gg)}; "
                               f"ke = {pct(ke)}"))
            return None
        if m.startswith("fcff"):
            f = self._fcff(m, Drivers())
            res = f.res
            T = self._t
            info["projecao"] = [{"ano": t, "crescimento": r6(float(res.g[t - 1])), "receita": r6(float(res.receita[t - 1])),
                                 "nopat": r6(float(res.nopat[t - 1])), "reinvestimento": r6(float(res.reinvest[t - 1])),
                                 "fcff": r6(float(res.fcff[t - 1])),
                                 "texto": {"crescimento": pct(float(res.g[t - 1])), "receita": T(float(res.receita[t - 1])),
                                           "nopat": T(float(res.nopat[t - 1])),
                                           "reinvestimento": pct(float(res.reinvest[t - 1])),
                                           "fcff": T(float(res.fcff[t - 1]))}}
                                for t in range(1, len(res.receita) + 1)]
            ft = float(res.fracao_terminal)
            info["fracao_terminal"] = r6(ft)
            info["reinvestimento_limitado_anos"] = list(res.limite_atingido)
            moe = self.moeda
            if m == "fcff_vida_finita":
                desc = (f"sem perpetuidade; fluxos até {self.pac['fim_concessao']}" if self.pac.get("fim_concessao")
                        else "prazo de concessão não curado: carteira tratada como renovável (com perpetuidade)")
            elif m == "fcff_normalizado":
                desc = ("margem EBIT mediana dos exercícios disponíveis" if self.margem_hist is not None
                        else "margem corrente (histórico de menos de 3 exercícios)")
            elif m == "fcff_real":
                desc = "fluxos, WACC e crescimento em termos reais"
            else:
                desc = "margem EBIT corrente"
            mg = self.margem_hist if m == "fcff_normalizado" and self.margem_hist is not None else self.margem
            rr_txt = (f"reinvestimento observado {pct(self.rr_obs)} nos anos 1–2, convergindo a g ÷ RONIC"
                      if self.rr_obs is not None else "reinvestimento g ÷ RONIC desde o ano 1")
            lim_txt = ""
            if res.limite_atingido:
                lo, hi = self.params.sec("projecao")["reinvestimento_limites"]
                anos_l = ", ".join(str(a) for a in res.limite_atingido)
                lim_txt = f"; reinvestimento limitado a [{pct(lo, 0)}; {pct(hi, 0)}] do NOPAT nos anos {anos_l}"
                self.avisos.append(f"{nome}: reinvestimento limitado a [{pct(lo, 0)}; {pct(hi, 0)}] do NOPAT "
                                   f"nos anos {anos_l}")
            reg.add(f"metodo.{m}", nome,
                    "EV = Σ FCFF_t ÷ (1 + WACC)^t + NOPAT_{T+1} × (1 − g ÷ RONIC) ÷ (WACC − g) ÷ (1 + WACC)^T; "
                    "V0 = (EV − DL − minoritários) ÷ N",
                    f"V0 = ({self._t(float(res.ev))} − {operando(self._t(self.pac['divida_liquida']))} − "
                    f"{operando(self._t(self.pac['minoritarios']))}) ÷ {contagem(self.pac['unidades'])}",
                    v, f"preco:{moe}",
                    premissas=(f"EV = valor presente dos fluxos {self._t(float(res.pv_explicito))} + perpetuidade "
                               f"{self._t(float(res.pv_terminal))}; receita {self._t(self.receita0)}, g1 "
                               f"{pct(self.g1)}, g2 {pct(self.g2)}, margem {pct(mg)}, WACC {pct(self.cc.wacc)}, "
                               f"g {pct(self.cc.g)}, ROIC {pct(self.roic0)} → RONIC {pct(self.ronic_final)}; {rr_txt}"
                               f"{lim_txt}; {desc}"))
            return ft
        if m.startswith("regressao"):
            regs = self.ctx["regressoes"]
            chave = {"regressao_pb_roe": "pb_financeiras" if self.pac["financeira"] else "pb_nao_financeiras",
                     "regressao_pl": "pl", "regressao_ev_receita": "ev_receita"}[m]
            r = regs[chave]
            mm = prever(r, self.fund, self.pac["pais"])
            termos = termos_previsao(r, self.fund, self.pac["pais"])
            partes = []
            for col, coef, val in termos:
                if col == "const":
                    partes.append(num(coef, 3))
                elif col.startswith("pais_"):
                    if val:
                        partes.append(f"{operando(num(coef, 3))} × 1")
                else:
                    partes.append(f"{operando(num(coef, 3))} × {self._fmt_regressor(col, val)}")
            sigla = {"regressao_pb_roe": "P/VPA_reg", "regressao_pl": "P/L_reg", "regressao_ev_receita": "EV/Receita_reg"}[m]
            regs_txt = " + ".join(f"b × {ROTULO_REGRESSOR.get(k, k)}" for k in r["regressores"])
            pais_txt = (f"efeito país de {self.pac['pais']} incluído" if self.pac["pais"] in r["efeitos"]
                        else f"{self.pac['pais']} é o país-base (efeito zero)" if self.pac["pais"] == r.get("pais_base")
                        else f"{self.pac['pais']} sem efeito próprio (menos de 2 observações)")
            reg.add(f"metodo.{m}.multiplo", f"{nome}: múltiplo do emissor",
                    f"{sigla} = a + {regs_txt} + efeito país (Huber, n = {r['n']}, R² = {num(r['r2'])})",
                    f"{sigla} = {' + '.join(partes)}", mm, "x", premissas=pais_txt)
            if m == "regressao_pb_roe":
                sub = f"V0 = {mult(mm)} × {P(self.b0)}"
                form = "V0 = P/VPA_reg × B0"
            elif m == "regressao_pl":
                sub = f"V0 = {mult(mm)} × {P(self.eps1)}"
                form = "V0 = P/L_reg × LPA_1"
            else:
                sub = (f"V0 = ({mult(mm)} × {self._t(self.receita0)} − {operando(self._t(self.pac['divida_liquida']))} − "
                       f"{operando(self._t(self.pac['minoritarios']))}) ÷ {contagem(self.pac['unidades'])}")
                form = "V0 = (EV/Receita_reg × receita − DL − minoritários) ÷ N"
            reg.add(f"metodo.{m}", nome, form, sub, v, f"preco:{self.moeda}")
            return None
        if m == "soma_partes":
            sp = self.pac["soma_partes"]
            partes = "; ".join(f"{q['emissor']} {pct(q['fracao'], 1)} × {total(q['valor_mercado'], q['moeda'])}"
                               for q in sp["partes"] if "fracao" in q)
            janela = f"{sp['semanas']} semanas" + (f" desde {sp['desde']}" if sp.get("desde") else "")
            if sp.get("razao_mediana") is not None:
                reg.add(f"metodo.{m}", nome,
                        "V0 = P0 × mediana(valor de mercado ÷ NAV) ÷ (valor de mercado ÷ NAV)_hoje",
                        f"V0 = {P(self.pac['preco'])} × {num(sp['razao_mediana'], 3)} ÷ {num(sp['razao_atual'], 3)}",
                        v, f"preco:{self.moeda}",
                        premissas=f"NAV = {total(sp['nav'], self.moeda)}: {partes}; mediana de {janela}")
            else:
                reg.add(f"metodo.{m}", nome, "V0 = NAV × (1 − desconto de reserva) ÷ N",
                        f"V0 = {total(sp['nav'], self.moeda)} × (1 − {pct(sp['desconto_reserva'])}) ÷ "
                        f"{contagem(self.pac['unidades'])}", v, f"preco:{self.moeda}",
                        premissas=f"histórico insuficiente para a mediana ({janela}); {partes}")
            return None
        return None

    # ------------------------------------------------------------------ 4. combinação e rolagem
    def combinar(self, vals: Mapping[str, np.ndarray]) -> np.ndarray | None:
        """Média ponderada pelos pesos do arquétipo; por sorteio, só os métodos com valor finito
        (pesos renormalizados); sorteio sem nenhum método válido ⇒ ``NaN``. Sem piso por
        método: o piso de zero (responsabilidade limitada) vale só para o valor combinado."""
        if not vals:
            return None
        ms = list(vals)
        w = np.array([self.metodos[m]["peso"] for m in ms], dtype=float)
        if w.sum() <= 0:
            return None
        v = np.stack([np.asarray(vals[m], dtype=float) for m in ms])
        ok = np.isfinite(v)
        wv = w.reshape((-1,) + (1,) * (v.ndim - 1)) * ok
        tot = wv.sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.where(tot > 0, (wv * np.where(ok, v, 0.0)).sum(axis=0) / tot, np.nan)
        return np.maximum(out, 0.0)

    def avaliar(self) -> dict[str, Any]:
        """Modelo completo do emissor (antes da etapa transversal de rating)."""
        self.preparar_metodos()
        reg, cc, P = self.reg, self.cc, self._p
        p0 = _f(self.pac.get("preco"))
        validos = self.metodos_validos()
        out: dict[str, Any] = {"tem_alvo": False}
        if not validos or p0 is None or self.dps12 is None:
            motivo = ("nenhum método com insumos suficientes" if not validos else
                      "preço indisponível" if p0 is None else "dividendo esperado indisponível")
            reg.nota("alvo", "Preço-alvo de 12 meses", f"Sem preço-alvo: {motivo}.")
            out["motivo_sem_alvo"] = motivo
            return self._saida(out)
        base = Drivers()
        vals = {m: np.asarray(self._valor_metodo(m, base), dtype=float) for m in validos}
        tot = sum(self.metodos[m]["peso"] for m in validos)
        partes = " + ".join(f"{num(self.metodos[m]['peso'])} × {P(float(vals[m]))}" for m in validos)
        v0 = float(self.combinar(vals))
        reg.add("alvo.v0", "Valor intrínseco hoje (combinação dos métodos disponíveis)",
                "V0 = Σ w_m × V_m ÷ Σ w_m (pesos do arquétipo, renormalizados aos métodos disponíveis)",
                f"V0 = ({partes}) ÷ {num(tot)}", v0, f"preco:{self.moeda}")
        tp = float(M.rolagem(v0, cc.ke, self.dps12))
        reg.add("alvo.tp12", "Preço-alvo de 12 meses (rolagem)", "TP12 = V0 × (1 + ke) − DPS12",
                f"TP12 = {P(v0)} × (1 + {pct(cc.ke)}) − {P(self.dps12)}", tp, f"preco:{self.moeda}")
        etr = float(M.retorno_esperado(tp, self.dps12, p0))
        reg.add("alvo.etr", "Retorno total esperado em 12 meses", "ETR = (TP12 + DPS12) ÷ P0 − 1",
                f"ETR = ({P(tp)} + {P(self.dps12)}) ÷ {P(p0)} − 1", etr, "%")
        up = tp / p0 - 1
        reg.add("alvo.upside", "Potencial de valorização (upside)", "upside = TP12 ÷ P0 − 1",
                f"upside = {P(tp)} ÷ {P(p0)} − 1", up, "%")
        vs = np.array([float(vals[m]) for m in validos])
        cv = float(np.std(vs, ddof=0) / np.mean(vs)) if len(vs) >= 2 else None
        if cv is not None:
            lista = "; ".join(P(x) for x in vs)
            reg.add("alvo.cv", "Dispersão entre métodos", "CV = desvio-padrão(V_m) ÷ média(V_m)",
                    f"CV = desvio-padrão({lista}) ÷ média({lista})", cv, "%")
        out.update({"tem_alvo": True, "v0": v0, "tp": tp, "etr": etr, "upside": up, "cv": cv,
                    "n_metodos": len(validos)})
        out.update(self._fcff_observado())
        out.update(self._cenarios(p0, tp, etr, validos))
        out["sensibilidade"] = self._sensibilidade(p0)
        out["icc"] = self._icc(p0)
        out["reverso"] = self._reverso(p0)
        return self._saida(out)

    def _fcff_observado(self) -> dict[str, Any]:
        """FCFF do ano 1 do modelo contra o fluxo de caixa livre observado (CFO − capex)."""
        ms = [m for m in self.metodos_validos() if m.startswith("fcff")]
        if not ms:
            return {}
        res = self._fcff(ms[0], Drivers()).res
        fc1 = float(res.fcff[0])
        razao = None if self.fcf_obs is None or self.fcf_obs <= 0 else fc1 / self.fcf_obs
        return {"fcff_ano1": fc1, "fcf_observado": self.fcf_obs, "fcff_ano1_vs_observado": razao,
                "reinvestimento_limitado_anos": list(res.limite_atingido)}

    # ------------------------------------------------------------------ 5. cenários
    def _cenarios(self, p0: float, tp: float, etr: float, validos: list[str]) -> dict[str, Any]:
        mc = self.params.sec("cenarios")["monte_carlo"]
        n = int(mc["n"])
        rng = np.random.default_rng(semente(self.pac["issuer_id"], self.pac["as_of"]))
        z = rng.standard_normal((7, n))
        rho = float(mc["rho_crescimento_margem"])
        s_cres = min(max(_f(self.setor_ctx.get("g_sigma")) or 0.0, float(mc["sigma_crescimento_min"])),
                     float(mc["sigma_crescimento_max"]))
        s_marg = min(max(self.margem_sd or 0.0, float(mc["sigma_margem_min"])), float(mc["sigma_margem_max"]))
        lim_c = float(mc.get("commodity_limite", 0.6))
        commodity = self.pac["arquetipo"] == "commodity"
        dr = Drivers(
            d_ke=float(mc["sigma_ke"]) * z[0],
            d_g=float(mc["sigma_g"]) * z[1],
            d_roe_trans=float(mc["sigma_roe"]) * z[2],
            d_cres=s_cres * z[3],
            d_marg=s_marg * (rho * z[3] + math.sqrt(1 - rho * rho) * z[4]),
            d_comm=np.clip(float(mc["sigma_commodity"]) * z[5], -lim_c, lim_c) if commodity else 0.0,
            d_razao=float(mc["sigma_desconto_holding"]) * z[6],
        )
        vals = {}
        self._estrito = False
        try:
            for m in validos:
                try:
                    vals[m] = np.broadcast_to(np.asarray(self._valor_metodo(m, dr), dtype=float), (n,))
                except (ValueError, ZeroDivisionError):
                    continue
        finally:
            self._estrito = True
        v0 = self.combinar(vals)
        ke = self._ke(dr)
        tps = np.asarray(M.rolagem(v0, ke, self.dps12), dtype=float)
        ok = np.isfinite(tps)
        tps = np.maximum(tps[ok], 0.0)
        rets = (tps + self.dps12) / p0 - 1
        p10, p50, p90 = (float(x) for x in np.percentile(tps, [10, 50, 90]))
        r10, r50, r90 = (float(x) for x in np.percentile(rets, [10, 50, 90]))
        pwr = float(np.mean(rets))
        alpha = pwr - self.cc.ke
        reg, P = self.reg, self._p
        reg.add("cenarios.mc", "Cenários: Monte Carlo dos direcionadores (mediana)",
                "TP^(k) = máx(V0(direcionadores^(k)); 0) × (1 + ke^(k)) − DPS12; choques normais de média zero (1 desvio): "
                f"ke {pp(mc['sigma_ke'], 2, False)}, g {pp(mc['sigma_g'], 2, False)}, ROE {pp(mc['sigma_roe'], 1, False)} "
                "(anos 1–2, convergindo ao ROE de longo prazo), "
                f"crescimento {pp(s_cres, 1, False)} e margem {pp(s_marg, 1, False)} (correlação {num(rho, 1)})"
                + (f", preço da commodity {pct(mc['sigma_commodity'], 0)} (transitório: anos 1–3, revertendo até o ano 5)"
                   if commodity else ""),
                f"P50 dos {inteiro(len(tps))} preços-alvo simulados", p50, f"preco:{self.moeda}",
                premissas=(f"P10 = {P(p10)}; P90 = {P(p90)}; preço-alvo do caso-base = {P(tp)}; sorteios "
                           "reprodutíveis com semente fixa por emissor e data"))
        reg.add("cenarios.pwr", "Retorno ponderado por probabilidade (PWR)", "PWR = média de (TP^(k) + DPS12) ÷ P0 − 1",
                f"PWR = média dos {inteiro(len(rets))} retornos simulados", pwr, "%",
                premissas=f"retorno do caso-base (ETR) = {pct(etr)}; diferença = {pp(pwr - etr, 1)}")
        reg.add("cenarios.alpha", "Alpha de valuation", "α = PWR − ke", f"α = {_op_pct(pwr)} − {pct(self.cc.ke)}",
                alpha, "%")
        vol = _f(self.pac.get("vol_12m"))
        pm_bull = pm_bear = None
        if vol is not None and vol > 0:
            dy = self.dps12 / p0
            mu = self.cc.ke - dy
            pm_bull = float(1 - norm.cdf((math.log(p90 / p0) - (mu - vol * vol / 2)) / vol)) if p90 > 0 else None
            pm_bear = float(norm.cdf((math.log(p10 / p0) - (mu - vol * vol / 2)) / vol)) if p10 > 0 else None
            drift = f"({pct(self.cc.ke)} − {pct(dy)} − {pct(vol)}² ÷ 2)"
            if pm_bull is not None:
                reg.add("cenarios.prob_mercado", "Probabilidade implícita pelo mercado (otimista)",
                        "P(S12 ≥ TP_otimista) = 1 − Φ((ln(TP_otimista ÷ P0) − (ke − DY − σ²/2)) ÷ σ)",
                        f"P = 1 − Φ((ln({P(p90)} ÷ {P(p0)}) − {drift}) ÷ {pct(vol)})", pm_bull, "prob",
                        premissas="σ = volatilidade realizada de 12 meses; exibida, não usada no alpha")
            if pm_bear is not None:
                reg.add("cenarios.prob_mercado_pess", "Probabilidade implícita pelo mercado (pessimista)",
                        "P(S12 ≤ TP_pessimista) = Φ((ln(TP_pessimista ÷ P0) − (ke − DY − σ²/2)) ÷ σ)",
                        f"P = Φ((ln({P(p10)} ÷ {P(p0)}) − {drift}) ÷ {pct(vol)})", pm_bear, "prob",
                        premissas="σ = volatilidade realizada de 12 meses; exibida, não usada no alpha")
        udr = (max(r90, 0.0) / -r10) if r10 < 0 else None
        skew = (r90 - r50) / (r50 - r10) if (r50 - r10) != 0 else None
        es = float(np.mean(rets[rets <= r10])) if np.any(rets <= r10) else None
        p_ke = float(np.mean(rets >= self.cc.ke))
        largura = (p90 - p10) / tp if tp else None
        return {"tp_pessimista": p10, "tp_mediana_mc": p50, "tp_otimista": p90, "pwr": pwr, "alpha": alpha,
                "ret_p10": r10, "ret_p50": r50, "ret_p90": r90, "udr": udr, "assimetria": skew,
                "perda_esperada_cauda": es, "prob_modelo_supera_ke": p_ke,
                "prob_mercado_otimista": pm_bull, "prob_mercado_pessimista": pm_bear,
                "largura_cenarios": largura, "n_sorteios": int(len(tps))}

    # ------------------------------------------------------------------ 6. sensibilidade
    def _grade(self, linhas: list[float], colunas: list[float], fl, fc) -> list[list[float | None]]:
        out = []
        for a in linhas:
            row = []
            for b in colunas:
                dr = Drivers(**{**fl(a), **fc(b)})
                vals = {}
                self._estrito = False
                try:
                    for m in self.metodos_validos():
                        try:
                            vals[m] = np.asarray(self._valor_metodo(m, dr), dtype=float)
                        except (ValueError, ZeroDivisionError):
                            continue
                finally:
                    self._estrito = True
                v0 = self.combinar(vals) if vals else None
                tpv = None if v0 is None else float(M.rolagem(v0, self._ke(dr), self.dps12))
                row.append(r6(tpv) if tpv is not None and np.isfinite(tpv) else None)
            out.append(row)
        return out

    def _sensibilidade(self, p0: float) -> dict[str, Any]:
        s = self.params.sec("sensibilidade")
        arq = self.pac["arquetipo"]
        ke_p = [float(x) for x in s["ke_passos"]]
        if arq in ("banco", "seguradora"):
            col = [float(x) for x in s["roe_passos"]]
            nome_c, fc = "ROE (permanente)", (lambda b: {"d_roe": b})
            col_txt = [pp(c, 1) for c in col]
        elif arq == "commodity":
            col = [float(x) for x in s["commodity_passos"]]
            nome_c, fc = "preço da commodity (choque transitório)", (lambda b: {"d_comm": b})
            col_txt = [pct(c, 0, True) for c in col]
        else:
            col = [float(x) for x in s["g_passos"]]
            nome_c, fc = "g", (lambda b: {"d_g": b})
            col_txt = [pp(c, 2) for c in col]
        grade = self._grade(ke_p, col, lambda a: {"d_ke": a}, fc)
        ups = [[None if v is None else r6(v / p0 - 1) for v in row] for row in grade]
        self.reg.nota("sensibilidade", f"Sensibilidade do preço-alvo (ke × {nome_c})",
                      f"Grade 5 × 5 recalculada pelos mesmos métodos: ke {', '.join(pct(self.cc.ke + d) for d in ke_p)}; "
                      f"{nome_c} com choques {'; '.join(col_txt)}")
        return {"linhas": "ke", "colunas": nome_c, "ke": [r6(self.cc.ke + d) for d in ke_p],
                "choques_colunas": [r6(c) for c in col], "preco_alvo": grade, "upside": ups,
                "ke_texto": [pct(self.cc.ke + d) for d in ke_p], "colunas_texto": col_txt,
                "preco_alvo_texto": [[self._p(v) for v in row] for row in grade],
                "upside_texto": [[pct(v, 1, True) for v in row] for row in ups]}

    # ------------------------------------------------------------------ 7. diagnósticos
    def _icc(self, p0: float) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if None not in (self.b0, self.roe1, self.roe2, self.roe_alvo, self.payout) and self.b0 > 0:
            out["gls"] = M.icc_gls(p0, self.b0, self.roe1, self.roe2, self.roe_alvo, self.payout)
        if self.eps1 is not None and self.eps2 is not None:
            dps1 = (self.eps1 * self.payout) if self.payout is not None else 0.0
            out["mpeg"] = M.icc_mpeg(p0, self.eps1, self.eps2, dps1)
            out["gode_mohanram"] = M.icc_gode_mohanram(p0, self.eps1, self.eps2, dps1, self.cc.g)
            if self.b0 is not None and self.payout is not None and self.eps2 > 0:
                g5 = self.eps2 / self.eps1 - 1 if self.eps1 > 0 else 0.0
                eps = [self.eps1, self.eps2] + [self.eps2 * (1 + g5 * 0.5) ** k for k in range(1, 4)]
                out["claus_thomas"] = M.icc_claus_thomas(p0, self.b0, eps, self.payout, self.cc.g)
        vals = {k: float(v) for k, v in out.items() if v is not None}
        comp = float(np.median(list(vals.values()))) if vals else None
        out = {k: r6(v) for k, v in out.items()}
        out["composto"] = r6(comp)
        out["icc_menos_ke"] = r6(None if comp is None else comp - self.cc.ke)
        if comp is not None:
            nomes = {"gls": "GLS", "mpeg": "MPEG", "gode_mohanram": "Gode–Mohanram", "claus_thomas": "Claus–Thomas"}
            lista = "; ".join(f"{nomes[k]} {pct(v)}" for k, v in vals.items())
            self.reg.add("diagnostico.icc", "Custo de capital implícito no preço (diagnóstico)",
                         "ICC = mediana de {GLS, MPEG, Gode–Mohanram, Claus–Thomas}",
                         f"ICC = mediana({lista})", comp, "%",
                         premissas=f"ke = {pct(self.cc.ke)}; ICC − ke = {pp(comp - self.cc.ke, 1)}")
        return out

    def _reverso(self, p0: float) -> dict[str, Any]:
        """Valuation reversa: ROE implícito no P/VPA (``ROE = g + P/VPA × (ke − g)``)."""
        if self.b0 is None or self.b0 <= 0:
            return {}
        pb = p0 / self.b0
        roe_impl = self.cc.g + pb * (self.cc.ke - self.cc.g)
        self.reg.add("diagnostico.roe_implicito", "ROE implícito no preço (valuation reversa)",
                     "ROE_impl = g + (P0 ÷ B0) × (ke − g)",
                     f"ROE_impl = {pct(self.cc.g)} + {mult(pb)} × ({pct(self.cc.ke)} − {pct(self.cc.g)})",
                     roe_impl, "%")
        return {"pb": r6(pb), "roe_implicito": r6(roe_impl), "roe_sustentavel": r6(self.roe_sust)}

    # ------------------------------------------------------------------ saída
    def peso_patrimonial(self) -> float:
        """Fração do peso válido em métodos ancorados no patrimônio por ação."""
        validos = self.metodos_validos()
        tot = sum(self.metodos[m]["peso"] for m in validos)
        if tot <= 0:
            return 0.0
        return sum(self.metodos[m]["peso"] for m in validos if m in METODOS_PATRIMONIAIS) / tot

    def _saida(self, out: dict[str, Any]) -> dict[str, Any]:
        out["custo_capital"] = {k: r6(v) if isinstance(v, float) else v for k, v in self.cc.dict().items()}
        out["metodos"] = [{k: (r6(v) if isinstance(v, float) else v) for k, v in d.items()}
                          for d in self.metodos.values()]
        out["dps12"] = self.dps12
        out["eps1"], out["eps2"], out["b0"] = self.eps1, getattr(self, "eps2", None), self.b0
        out["eps_ttm"], out["roe1"] = self.eps_ttm, self.roe1
        out["roe_sust"], out["payout"] = self.roe_sust, self.payout
        out["lpa_diverge"] = bool(self.lpa_diverge)
        out["peso_patrimonial"] = self.peso_patrimonial()
        out["lacunas"] = self.lacunas + [{"insumo": f"metodo.{d['m']}", "nome": NOME_METODO[d["m"]],
                                          "motivo": d["motivo"]}
                                         for d in self.metodos.values() if d.get("motivo")]
        out["avisos"] = self.avisos
        return out


__all__ = ["Avaliador", "Drivers", "METODOS_PATRIMONIAIS", "semente"]
_ = (prov_codigo, METODOS_LUCRO)  # reexportados para quem monta passos externos
