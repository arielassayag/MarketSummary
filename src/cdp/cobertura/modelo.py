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
from .contexto import (
    alvo_roe,
    beta_pares,
    fracao_exercicio,
    prever,
    prever_bruto,
    reinvestimento_observado,
    termos_previsao,
)
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
    "oficial": "capital social do Formulário de Referência",
    "nao_conciliada": "contagem não conciliada entre as fontes",
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
        self.k_pl = f"t.{pac.get('item_patrimonio') or 'patrimonio_controladores'}"
        self.k_luc = f"t.{pac.get('item_lucro') or 'lucro_liquido_controladores'}"
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
        premio = (ctx.get("premio_implicito") or {}).get(pac["pais"])
        cal = (ctx.get("calibracao_pais") or {}).get(pac["pais"])
        self.cc: CustoCapital = calcular(self.pac, params, rf_ust, rf_fonte, bp, nbp, self.reg, lista,
                                         premio_pais=premio, calibracao=cal)
        self.metodos: dict[str, dict[str, Any]] = {}
        self._estrito = True
        self._fcff_base: dict[str, M.ResultadoFCFF] = {}
        self._preparar_direcionadores()

    # ------------------------------------------------------------------ utilidades
    def _sintetico(self) -> bool:
        return (self.fontes.get("preco") or {}).get("fonte") == "SIMULADO" or "SIMULADO" in self.rotulo_consenso

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
            ct = p.get("contagem") or {}
            prem = f"origem: {STATUS_UNIDADES_PT.get(str(p.get('status_unidades')), '')}"
            if ct.get("detalhe"):
                prem += f"; conciliação: {ct['detalhe']}"
            self.reg.add("insumos.unidades", "Unidades em circulação da linha",
                         "N = ações em circulação ÷ ações por unidade negociada (contagem conciliada entre fontes)",
                         f"N = {contagem(float(p['unidades']) * apl)} ÷ {num(apl, 0)}", p["unidades"], "acoes",
                         self._fonte("unidades"), premissas=prem)
        if p.get("bvps") is not None:
            if p.get(self.k_pl) is not None and p.get("unidades"):
                sub = f"B0 = {self._t(p.get(self.k_pl))} ÷ {contagem(p.get('unidades'))}"
            else:
                sub = "B0 = patrimônio por ação do retrato público (sem demonstração)"
            self.reg.add("insumos.bvps", "Patrimônio líquido por unidade (B0)",
                         "B0 = patrimônio dos controladores ÷ N", sub,
                         p["bvps"], f"preco:{m}", self._fonte(self.k_pl) or self._fonte("bvps"),
                         premissas=(None if self.k_pl == "t.patrimonio_controladores" else
                                    "patrimônio líquido total: demonstrações sem a separação dos controladores na "
                                    "data-base mais recente"))
        if p.get("eps_ttm") is not None:
            self.reg.add("insumos.eps_ttm", "Lucro por unidade dos últimos 12 meses",
                         "LPA_12m = lucro dos controladores (12 meses) ÷ N",
                         f"LPA_12m = {self._t(p.get(self.k_luc))} ÷ {contagem(p.get('unidades'))}",
                         p["eps_ttm"], f"preco:{m}", self._fonte(self.k_luc))
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
        cal = bool(proj.get("calendarizacao", False))
        self.f_ex = fracao_exercicio(p) if cal else None
        f_ex = self.f_ex
        fye = p.get("fim_exercicio_consenso") or p.get("fim_exercicio")
        eps_fy1, eps_fy2 = _f(p.get("eps_fy1")), _f(p.get("eps_fy2"))
        # consenso de LPA de poucos analistas não define o ROE dos anos 1–2: abaixo do mínimo, o lucro
        # dos últimos 12 meses (sinalizado; confiança limitada)
        self.n_eps = _f((p.get("consenso") or {}).get("n_eps"))
        n_min_roe = int(self.params.sec("qualidade").get("analistas_min_roe", 2))
        self.consenso_raso = eps_fy1 is not None and self.n_eps is not None and self.n_eps < n_min_roe
        if self.consenso_raso and _f(p.get("eps_ttm")) is not None:
            reg.nota("dir.consenso_raso", "Consenso de LPA com poucos analistas",
                     f"LPA de consenso de {int(self.n_eps)} analista(s), abaixo do mínimo de {n_min_roe}: o ROE dos "
                     "anos 1–2 parte do lucro dos últimos 12 meses (o consenso fica só como referência).")
            self.avisos.append(f"consenso de LPA de {int(self.n_eps)} analista(s): ROE dos anos 1–2 pelo lucro de 12 meses")
            eps_fy1 = eps_fy2 = None
        eps1 = eps_fy1
        self.eps1_fonte = "consenso"
        self.calendarizado = False
        if eps_fy1 is not None and eps_fy2 is not None and f_ex is not None:
            eps1 = (1 - f_ex) * eps_fy1 + f_ex * eps_fy2
            self.calendarizado = True
            self.eps1_fonte = "consenso calendarizado em 12 meses à frente"
            reg.add("dir.lpa_12m", "LPA de consenso em 12 meses à frente (calendarização)",
                    "LPA_1 = (1 − f) × LPA_FY1 + f × LPA_FY2; f = fração decorrida do exercício corrente",
                    f"LPA_1 = (1 − {num(f_ex, 3)}) × {self._op(eps_fy1)} + {num(f_ex, 3)} × {self._op(eps_fy2)}",
                    eps1, f"preco:{self.moeda}",
                    premissas=(f"exercício anterior ao corrente encerrado em {fye}; f = dias decorridos até "
                               f"{p.get('as_of')} ÷ 365, limitado a [0; 1]"))
        if eps1 is None and self.eps_ttm is not None:
            eps1 = self.eps_ttm
            self.eps1_fonte = "lucro dos últimos 12 meses (sem consenso)"
            self.avisos.append("LPA do ano 1 = lucro dos últimos 12 meses (consenso indisponível)")
        self.eps1 = eps1
        # crescimento próprio (consenso de receita, senão histórico) encolhido para o setor
        g_cons = _f(p.get("g_receita_fy1"))
        g_hist = _f(p.get("g_receita_historico"))
        g2c = _f(p.get("g_receita_fy2"))
        lim_txt = f"limitado a [{pct(lo_g, 0)}; {pct(hi_g, 0)}]"
        g_rec_cal = None
        if g_cons is not None and g2c is not None and f_ex is not None:
            # receita de 12 meses à frente relativa à receita dos últimos 12 meses (a base das demonstrações)
            r1n = (1 - f_ex) * (1 + g_cons) + f_ex * (1 + g_cons) * (1 + g2c)
            g3 = 0.5 * (min(max(g2c, lo_g), hi_g) + cc.g)
            r2n = (1 - f_ex) * (1 + g_cons) * (1 + g2c) + f_ex * (1 + g_cons) * (1 + g2c) * (1 + g3)
            g_rec_cal = (r1n - 1, r2n / r1n - 1, g3, r1n, r2n)
        if g_rec_cal is not None:
            g1 = g_rec_cal[0]
            sub1 = (f"g1 = mín(máx((1 − {num(f_ex, 3)}) × (1 + {_op_pct(g_cons)}) + {num(f_ex, 3)} × "
                    f"(1 + {_op_pct(g_cons)}) × (1 + {_op_pct(g2c)}) − 1; {pct(lo_g, 0)}); {pct(hi_g, 0)})")
            prem1 = (f"receita de consenso do exercício corrente = {pct(g_cons)} sobre a receita dos últimos 12 meses e "
                     f"do exercício seguinte = {pct(g2c)} sobre a corrente ({self.rotulo_consenso}); receita dos 12 "
                     f"meses à frente pela calendarização, {lim_txt}")
        elif g_cons is not None:
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
        if g_rec_cal is not None:
            g2 = min(max(g_rec_cal[1], lo_g), hi_g)
            sub2 = f"g2 = mín(máx({num(g_rec_cal[4], 4)} ÷ {num(g_rec_cal[3], 4)} − 1; {pct(lo_g, 0)}); {pct(hi_g, 0)})"
            prem2 = (f"receita dos 12 meses seguintes ÷ receita dos 12 meses à frente, com o exercício posterior "
                     f"crescendo {pct(g_rec_cal[2])} (média do crescimento do exercício seguinte e de g)")
        elif g2c is not None:
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
        usa_g = not p.get("financeira") or eps_fy2 is None  # financeiras: só para LPA_2 sem consenso
        if g1 is not None and usa_g:
            reg.add("dir.g1", "Crescimento da receita — ano 1", "g1 = crescimento próprio, limitado à faixa da projeção",
                    sub1, g1, "%", premissas=prem1)
            reg.add("dir.g2", "Crescimento da receita — ano 2",
                    "g2 = consenso (ano 2, calendarizado) ou média de g1 com a mediana do setor", sub2, g2, "%",
                    premissas=prem2)
        # payout dos acionistas do emissor (proventos por ação × N, nunca os dividendos consolidados da DFC,
        # que incluem os pagos a não controladores de controladas): média de 3 anos; senão 12 meses
        pay, pay_sub, pay_form, pay_prem, pay_fontes = self._payout()
        if pay is None:
            pay = _f(self.setor_ctx.get("payout_mediana")) or _f(self.univ_ctx.get("payout_mediana"))
            pay_sub, pay_prem = f"k = {pct(pay)}", "mediana do setor (payout próprio indisponível)"
            pay_form, pay_fontes = "k = mediana do setor", []
        self.payout = pay
        if pay is not None:
            reg.add("dir.payout", "Payout", pay_form, pay_sub, pay, "%", pay_fontes, premissas=pay_prem)
        # ROE ano 1/2 e ROE de convergência (persistência por classe de estabilidade)
        self.roe1 = self.roe2 = self.roe_alvo = None
        self.omega = None
        self.alvo_roe_info: dict[str, Any] | None = None
        self.eps2 = None
        if self.b0 is not None and self.b0 > 0 and self.eps1 is not None and pay is not None:
            self.roe1 = self.eps1 / self.b0
            b1 = self.b0 + self.eps1 * (1 - (pay if self.eps1 > 0 else 0.0))
            eps2 = eps_fy2
            if self.calendarizado and eps_fy1 is not None and eps_fy2 is not None:
                g_fy2 = min(max(eps_fy2 / eps_fy1 - 1, lo_g), hi_g) if eps_fy1 > 0 else cc.g
                eps_fy3 = eps_fy2 * (1 + 0.5 * (g_fy2 + cc.g))
                eps2 = (1 - f_ex) * eps_fy2 + f_ex * eps_fy3
                reg.add("dir.lpa_12m_2", "LPA do ano 2 (calendarizado)",
                        "LPA_2 = (1 − f) × LPA_FY2 + f × LPA_FY3; LPA_FY3 = LPA_FY2 × (1 + (g_FY2 + g) ÷ 2)",
                        f"LPA_2 = (1 − {num(f_ex, 3)}) × {self._op(eps_fy2)} + {num(f_ex, 3)} × {self._op(eps_fy3)}",
                        eps2, f"preco:{self.moeda}",
                        premissas=(f"g_FY2 = LPA_FY2 ÷ LPA_FY1 − 1 = {pct(g_fy2)} ({lim_txt}); g = {pct(cc.g)}; "
                                   f"LPA_FY3 = {self._p(eps_fy2)} × (1 + ({pct(g_fy2)} + {pct(cc.g)}) ÷ 2)"))
            if eps2 is None and g2 is not None:
                eps2 = self.eps1 * (1 + g2)
            self.eps2 = eps2
            self.roe2 = None if eps2 is None or b1 <= 0 else eps2 / b1
            reg.add("dir.roe1", "ROE do ano 1", "ROE_1 = LPA_1 ÷ B0",
                    f"ROE_1 = {self._p(self.eps1)} ÷ {self._p(self.b0)}", self.roe1, "%",
                    premissas=f"LPA_1: {self.eps1_fonte}")
            if self.roe2 is not None:
                reg.add("dir.roe2", "ROE do ano 2", "ROE_2 = LPA_2 ÷ B1, B1 = B0 + LPA_1 × (1 − k)",
                        f"ROE_2 = {self._p(eps2)} ÷ {self._p(b1)}", self.roe2, "%")
            # a norma de longo prazo do ROE (spread sobre o ke, estimado contra o ke sem a calibração de
            # nível) não depende do ajuste de nível do país: ke sem a calibração + s + a
            ke_norma = cc.ke_sem_calibracao if cc.ke_sem_calibracao is not None else cc.ke
            info = alvo_roe(self.ctx, self.params, p["issuer_id"], p["pais"], p["setor"], p["arquetipo"],
                            ke_norma, self.roe2)
            if info is not None:
                self._passos_alvo_roe(info)
                self.roe_alvo, self.omega, self.alvo_roe_info = info["alvo"], info["omega"], info
            else:
                ra = _f(self.univ_ctx.get("roe_mediana"))
                self.roe_alvo = ra
                if ra is not None:
                    reg.add("dir.roe_alvo", "ROE de convergência (sem norma setorial)", "ROE_alvo = mediana do universo",
                            f"ROE_alvo = {pct(ra)}", ra, "%", premissas="mediana do ROE do universo")
        else:
            self.eps2 = eps_fy2
        self.payout_sust = None
        if self.roe_alvo is not None and self.roe_alvo > cc.g and pay is not None:
            self.payout_sust = min(max(1 - cc.g / self.roe_alvo, 0.0), 1.0)
            reg.add("dir.payout_sust", "Payout sustentável (convergência do lucro residual)",
                    "k_sust = 1 − g ÷ ROE_alvo (reinvestimento que sustenta o crescimento de longo prazo)",
                    f"k_sust = 1 − {pct(cc.g)} ÷ {pct(self.roe_alvo)}", self.payout_sust, "%")
        elif pay is not None:
            self.payout_sust = pay
        self.lpa_diverge = False
        if self.eps1 is not None and self.eps_ttm is not None and self.eps1_fonte != "lucro dos últimos 12 meses (sem consenso)":
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
        self.margem_fluxos = self.fund.get("margem_fluxos")
        if self.params.sec("qualidade").get("margem_fluxos_metodo") is not None:
            # A mesma guarda precede o contexto/calibração. Também fecha o caminho direto
            # do Avaliador quando recebe um contexto antigo sem o diagnóstico da política.
            from .margens import margens_alinhadas

            self.margem_fluxos = margens_alinhadas(p)
            corrente = self.margem_fluxos["corrente"]
            self.margem = corrente["margem"]
            hist_validos = [r["margem"] for r in self.margem_fluxos["historico"].values()
                            if r["margem"] is not None]
            self.margem_hist = float(np.median(hist_validos)) if len(hist_validos) >= 3 else None
            self.margem_sd = float(np.std(hist_validos, ddof=1)) if len(hist_validos) >= 3 else None
            # Regressões usam self.fund. Nunca recuperam a razão antiga de um contexto
            # recebido sem a política ou preparado antes da mudança dos insumos.
            self.fund = {**self.fund, "margem": self.margem, "margem_hist": self.margem_hist,
                         "margem_sd": self.margem_sd, "margem_fluxos": self.margem_fluxos}
            if corrente["status"] != "comparavel":
                self.lacunas.append({"insumo": "margem", "nome": "margem EBIT comparável",
                                     "motivo": corrente["motivo"]})
                reg.nota("dir.margem_comparabilidade", "Margem EBIT indisponível",
                         corrente["motivo"], [r["fonte"] for r in corrente["insumos"].values() if r["fonte"]])
            recusados = [a for a, r in self.margem_fluxos["historico"].items() if r["margem"] is None]
            if recusados:
                self.lacunas.append({"insumo": "margem_historica", "nome": "margem EBIT histórica comparável",
                                     "motivo": "pares anuais sem alinhamento/proveniência: " + ", ".join(recusados)})
        ebit = _f(p.get("t.ebit"))
        nd = _f(p.get("divida_liquida"))
        pl = _f(p.get(self.k_pl))
        self.roic0 = None
        if ebit is not None and pl is not None and nd is not None and pl + nd > 0:
            roic = ebit * (1 - cc.imposto) / (pl + nd)
            lo, hi = proj["roic_limites"]
            self.roic0 = min(max(roic, lo), hi)
            reg.add("dir.roic", "Retorno sobre o capital investido (ROIC)",
                    "ROIC = EBIT × (1 − t) ÷ (patrimônio + dívida líquida), limitado a [0%; 60%]",
                    f"ROIC = mín(máx({self._t(ebit)} × (1 − {pct(cc.imposto)}) ÷ ({self._t(pl)} + "
                    f"{operando(self._t(nd))}); 0%); 60%)", self.roic0, "%", self._fonte("t.ebit"))
        # reinvestimento observado (anos 1–2 do fluxo de caixa): 1 − Σ(CFO − capex − arrendamentos) ÷ Σ NOPAT
        self.rr_obs = self.fcf_obs = None
        self.rr_info = None
        self.rr_contaminado = False
        self.rr_metodo = proj.get("reinvestimento_metodo")
        cfo, capex = _f(p.get("t.cfo")), _f(p.get("t.capex"))
        arr_pag = _f(p.get("t.arrendamentos_pagos"))
        if self.rr_metodo is None and not p.get("financeira") and cfo is not None and capex is not None:
            self.fcf_obs = cfo - abs(capex) - (abs(arr_pag) if arr_pag is not None else 0.0)
        if not p.get("financeira"):
            self.rr_info = reinvestimento_observado(
                p, cc.imposto, int(proj.get("reinvestimento_anos_observados", 3)),
                metodo=self.rr_metodo, regime=str(proj.get("reinvestimento_regime", "recente")))
            if self.rr_metodo is None and arr_pag is None and (_f(p.get("arrendamentos")) or 0.0) > 0:
                self.lacunas.append({"insumo": "arrendamentos_pagos", "nome": "pagamentos de arrendamentos",
                                     "motivo": "principal dos arrendamentos pago (DFC) não publicado na fonte: o fluxo "
                                               "observado não desconta a reposição dos ativos arrendados"})
        if self.rr_info is not None:
            ri = self.rr_info
            rr_min = float(self.params.sec("qualidade").get("rr_observado_min", -1.0))
            com_arr = ri.get("arrendamentos") is not None
            if self.rr_metodo == "capitalizacao_arrendamentos":
                self.fcf_obs = ri["fcf"]
                self._passos_reinvestimento_capitalizado(ri)
            elif ri["base"] == "12 meses":
                sub_rr = (f"RR_obs = 1 − ({self._t(cfo)} − {self._t(abs(capex))}"
                          + (f" − {self._t(ri['arrendamentos'])}" if com_arr else "")
                          + f") ÷ ({self._t(ebit)} × (1 − {pct(cc.imposto)}))")
                form_rr = ("RR_obs = 1 − (CFO − capex" + (" − arrendamentos pagos" if com_arr else "")
                           + ") ÷ (EBIT × (1 − t)), últimos 12 meses")
            elif self.rr_metodo is None:
                sub_rr = f"RR_obs = 1 − {self._t(ri['fcf'])} ÷ {self._t(ri['nopat'])}"
                form_rr = ("RR_obs = 1 − Σ(CFO − capex" + (" − arrendamentos pagos" if com_arr else "")
                           + ") ÷ Σ(EBIT × (1 − t)), últimos 3 exercícios")
            if self.rr_metodo is None:
                arr_txt = (f"principal de arrendamentos pago (IFRS 16, DFC de financiamento) {self._t(ri['arrendamentos'])} "
                           "descontado como reposição dos ativos arrendados; " if com_arr else
                           "principal de arrendamentos pago não publicado em todos os períodos: não descontado; ")
                reg.add("dir.reinvestimento", "Reinvestimento observado (anos 1–2 do fluxo de caixa)", form_rr, sub_rr,
                        ri["rr"], "%", self._fonte("t.cfo") + self._fonte("t.capex") + self._fonte("t.arrendamentos_pagos"),
                        premissas=("exercícios " + ", ".join(ri["anos"]) + "; " if ri["anos"] else "") + arr_txt
                        + "dos anos 3 a 10 o reinvestimento converge linearmente para g ÷ RONIC")
            self.rr_obs = ri["rr"]
            if ri["rr"] < rr_min:
                med = _f(self.setor_ctx.get("rr_mediana"))
                med_txt = "mediana do setor"
                if med is None:
                    med, med_txt = _f(self.univ_ctx.get("rr_mediana")), "mediana do universo"
                self.rr_contaminado = True
                if med is not None:
                    self.rr_obs = med
                    reg.add("dir.reinvestimento_setor", "Reinvestimento dos anos 1–2 pela mediana do setor",
                            f"RR_1,2 = {med_txt} (RR observado abaixo de {pct(rr_min, 0)})", f"RR_1,2 = {pct(med)}",
                            med, "%", premissas=("CFO − capex acima de 2 × NOPAT: o fluxo operacional publicado inclui "
                                                 "operações financeiras ou liberação pontual de capital de giro"
                                                 if self.rr_metodo is None else
                                                 "reinvestimento líquido excepcionalmente negativo: mediana de "
                                                 "observações com a mesma identidade de capital investido"))
                    self.lacunas.append({"insumo": "reinvestimento", "nome": "reinvestimento observado",
                                         "motivo": (f"reinvestimento observado de {pct(ri['rr'], 0)} "
                                                   + ("(CFO − capex acima de 2 × NOPAT)" if self.rr_metodo is None
                                                      else "(investimento líquido negativo na identidade de capital investido)")
                                                   + f": substituído pela {med_txt}")})
        if self.rr_obs is None and not p.get("financeira"):
            if self.rr_metodo == "capitalizacao_arrendamentos":
                motivo = ("FCFF sem identidade observada completa de EBIT, capex, depreciação da DFC, variação "
                          "do capital de giro operacional e adições de direitos de uso no mesmo período, "
                          "base contábil e moeda: "
                          "reinvestimento projetado por g ÷ RONIC, sem substituir ausência por zero")
                self.avisos.append(motivo)
                self.lacunas.append({"insumo": "reinvestimento", "nome": "reinvestimento observado", "motivo": motivo})
            else:
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

    def _passos_reinvestimento_capitalizado(self, ri: dict[str, Any]) -> None:
        """Ponte de capital investido, com as fontes dos períodos usados e os termos abertos."""
        from .reinvestimento import COMPONENTES

        hfontes = self.pac.get("historico_fontes") or {}
        fontes = []
        for k in COMPONENTES:
            if ri["anos"]:
                fontes.extend(f for a in ri["anos"] if (f := (hfontes.get(k) or {}).get(a)))
            else:
                fontes.extend(self._fonte(f"t.{k}"))
        fontes = [g for f in fontes for g in [f, *(x["fonte"] for x in f.get("componentes_fluxo", []))]]
        periodo = ", ".join(ri["anos"]) if ri["anos"] else str(ri.get("periodo"))
        self.reg.add("dir.investimento_liquido", "Reinvestimento líquido no capital operacional",
                     "I = capex + adições de direitos de uso − depreciação da DFC + variação do capital de giro operacional",
                     f"I = {self._t(ri['capex'])} + {self._t(ri['adicoes_direito_uso'])} − {self._t(ri['d_a'])} "
                     f"+ {operando(self._t(ri['variacao_capital_giro']))}", ri["reinvestimento"],
                     f"total:{self.moeda}", fontes,
                     premissas=(f"período: {periodo}; arrendamentos capitalizados no EBIT, capital investido, "
                                "dívida e WACC; principal pago não é capex; juros pertencem ao financiamento"))
        self.reg.add("dir.fcff_observado", "Fluxo de caixa não alavancado observado",
                     "FCFF = NOPAT − I", f"FCFF = {self._t(ri['nopat'])} − {operando(self._t(ri['reinvestimento']))}",
                     ri["fcf"], f"total:{self.moeda}", fontes,
                     premissas="NOPAT = EBIT × (1 − alíquota marginal); o CFO reportado não substitui essa identidade")
        self.reg.add("dir.reinvestimento", "Reinvestimento observado (anos 1–2 do fluxo de caixa)",
                     "RR = I ÷ NOPAT", f"RR = {self._t(ri['reinvestimento'])} ÷ {self._t(ri['nopat'])}",
                     ri["rr"], "%", fontes,
                     premissas=(f"{ri['base']}, regime {ri['regime']}; dos anos 3 a 10 converge para g ÷ RONIC; "
                                "ausências e datas-base diferentes não fecham a identidade"))
        if ri.get("rr_historico") is not None:
            historica = ri["ponte_historica"]
            fs_hist = [f for k in COMPONENTES for a in ri["anos_historico"]
                       if (f := (hfontes.get(k) or {}).get(a))]
            self.reg.add("dir.reinvestimento_historico", "Sensibilidade: reinvestimento histórico",
                         "RR_hist = Σ I ÷ Σ NOPAT",
                         f"RR_hist = {self._t(historica['reinvestimento'])} ÷ {self._t(historica['nopat'])}",
                         ri["rr_historico"], "%", fs_hist, premissas=("exercícios " + ", ".join(ri["anos_historico"])
                         + "; média histórica exibida para comparar regimes, sem definir os fluxos projetados"))
        if ri.get("componentes_12m_incompletos"):
            self.lacunas.append({"insumo": "reinvestimento_12m", "nome": "ponte dos últimos 12 meses",
                                 "motivo": f"componentes de 12 meses incompletos ou com datas diferentes; usada a "
                                           f"última observação completa ({periodo}), sem misturar períodos, bases e moedas"})

    def _payout(self) -> tuple[float | None, str, str, str, list[dict[str, Any]]]:
        """Payout aos acionistas do emissor (proventos por ação × N, nunca os dividendos consolidados da
        DFC, que incluem os pagos a não controladores de controladas): mediana dos payouts anuais dos 3
        últimos exercícios com lucro (``proventos por ação pagos no ano × N ÷ lucro dos controladores do
        exercício``, cada um limitado a [0; 1]) — descarta o ano de uma distribuição extraordinária (venda
        de ativos, reservas) e independe da data de pagamento; com menos de 2 anos, ``proventos de 12
        meses × N ÷ lucro de 12 meses``; sem proventos por ação, os dividendos da DFC (sinalizado). A DFC
        consolidada é conferida contra os proventos por ação (diferença > 25% ⇒ nota)."""
        p = self.pac
        u = _f(p.get("unidades"))
        luc = _f(p.get(self.k_luc))
        dfc = _f(p.get("t.dividendos_pagos"))
        dps12 = _f(p.get("dps_12m"))
        proventos = p.get("dps_fonte") == "proventos"
        hist = ((p.get("historico") or {}).get("lucro_liquido_controladores") or {})
        dpa = p.get("dps_anual") or {}
        notas = []
        if proventos and dfc is not None and dps12 and u and abs(abs(dfc) / (dps12 * u) - 1) > 0.25:
            notas.append(f"dividendos pagos na DFC consolidada {self._t(abs(dfc))} contra proventos por ação × N "
                         f"{self._t(dps12 * u)} ({pct(abs(dfc) / (dps12 * u) - 1, 0, True)}): a DFC consolidada inclui "
                         "dividendos a não controladores de controladas e difere na data de pagamento; não usada")
        fontes = self._fonte("dps_12m")
        k12 = None if not proventos or dps12 is None or not u or luc is None or luc <= 0 else dps12 * u / luc
        anuais = []
        hist_dfc = ((p.get("historico") or {}).get("dividendos_pagos") or {})
        if proventos and u:
            for a in sorted(dpa):
                la = _f(hist.get(a))
                d = _f(dpa[a])
                if la is None or la <= 0 or d is None:
                    continue
                if d > 0:
                    anuais.append((a, min(max(d * u / la, 0.0), 1.0), f"{self._p(d)} × N ÷ {self._t(la)}"))
                elif _f(hist_dfc.get(a)) is not None and abs(float(hist_dfc[a])) > 0:
                    # sem proventos por ação no ano mas com dividendos pagos na DFC: lacuna da série de proventos;
                    # vale a DFC do exercício (sinalizada: pode incluir não controladores)
                    dv = abs(float(hist_dfc[a]))
                    anuais.append((a, min(max(dv / la, 0.0), 1.0), f"DFC {self._t(dv)} ÷ {self._t(la)}"))
                else:
                    anuais.append((a, 0.0, f"sem proventos ÷ {self._t(la)}"))
        if len(anuais) >= 2:
            k = float(np.median([x[1] for x in anuais]))
            lista = "; ".join(f"{pct(x[1])}" for x in anuais)
            notas.insert(0, "anos " + ", ".join(f"{a}: {txt} = {pct(v)}" for a, v, txt in anuais)
                         + "; payout de 12 meses = " + (pct(k12) if k12 is not None else "n/d (lucro de 12 meses não positivo)")
                         + ("; ano sem proventos por ação e com dividendos na DFC usa a DFC do exercício (lacuna da série "
                            "de proventos)" if any(t.startswith("DFC") for _, _, t in anuais) else ""))
            return (k, f"k = mediana({lista})",
                    "k = mediana dos payouts anuais dos 3 últimos exercícios com lucro (proventos por ação pagos no ano "
                    "× N ÷ lucro dos controladores do exercício, cada um limitado a [0; 1])", "; ".join(notas), fontes)
        if k12 is not None:
            notas.insert(0, "menos de 2 exercícios com lucro e histórico de proventos completo")
            return (min(max(k12, 0.0), 1.0), f"k = mín({self._p(dps12)} × {contagem(u)} ÷ {self._t(luc)}; 1)",
                    "k = proventos por ação de 12 meses × N ÷ lucro dos controladores de 12 meses, limitado a [0; 1]",
                    "; ".join(notas), fontes)
        if not proventos and dfc is not None and luc is not None and luc > 0:
            self.avisos.append("payout pelos dividendos pagos da DFC consolidada (sem histórico de proventos por "
                               "ação): pode incluir dividendos a não controladores")
            return (min(max(abs(dfc) / luc, 0.0), 1.0), f"k = mín({self._t(abs(dfc))} ÷ {self._t(luc)}; 1)",
                    "k = dividendos pagos (DFC) ÷ lucro dos controladores (12 meses), limitado a [0; 1]",
                    "sem proventos por ação: DFC consolidada, que pode incluir dividendos a não controladores",
                    self._fonte("t.dividendos_pagos"))
        pay = _f(self.fund.get("payout"))
        if pay is None:
            return None, "", "", "", []
        dps_, eps_ref = _f(p.get("dps_12m")), (self.eps1 if self.eps1 is not None else self.eps_ttm)
        sub = (f"k = mín({self._p(dps_)} ÷ {self._p(eps_ref)}; 1)" if dps_ is not None and eps_ref else f"k = {pct(pay)}")
        return pay, sub, "k = proventos de 12 meses ÷ LPA de referência, limitado a [0; 1]", \
            "lucro de 12 meses indisponível: LPA de referência", fontes

    def _passos_alvo_roe(self, i: dict[str, Any]) -> None:
        """Passos da norma de longo prazo e do ROE de convergência (persistência por classe)."""
        reg, cc = self.reg, self.cc
        ref = i["referencia"]
        sim = " (DADOS SIMULADOS)" if self._sintetico() else ""
        f_spread = prov_codigo("mediana de (ROE de 5 anos − ke sem a calibração) dos emissores cobertos da classe, "
                               f"estimada nesta execução (contexto.json, normas_roe){sim}")
        pp_ = self.ctx.get("persistencia_roe_painel") or {}
        f_norm = (prov_codigo("persistência do desvio do ROE estimada nesta execução sobre o histórico arquivado dos "
                              f"emissores cobertos (contexto.json, persistencia_roe_painel: {pp_.get('n_emissor_anos')} "
                              f"emissor-anos, θ ≈ {num(pp_.get('theta'))}, ω ≈ {num(pp_.get('omega'))}); θ e ω por classe "
                              f"são política da configuração{sim}"))
        if i.get("pais_setor"):
            ps = i["pais_setor"]
            reg.add("dir.roe_spread", "Spread de longo prazo do ROE sobre o ke (classe de referência)",
                    "s = (1 − w) × mediana(ROE_5a − ke) do setor + w × mediana(ROE_5a − ke) de país × setor",
                    f"s = {num(1 - ps['peso'])} × {_op_pct(ref['spread'])} + {num(ps['peso'])} × {_op_pct(ps['spread'])}",
                    i["spread"], "%", [f_spread],
                    premissas=(f"{ref['rotulo']}: {ref['n']} emissores com ROE de 5 anos positivo; "
                               f"{ps['rotulo']}: {ps['n']} emissores"))
        else:
            reg.add("dir.roe_spread", "Spread de longo prazo do ROE sobre o ke (classe de referência)",
                    "s = mediana(ROE de 5 anos − ke) dos emissores lucrativos da classe",
                    f"s = mediana de {ref['n']} emissores de {ref['rotulo']}", i["spread"], "%", [f_spread],
                    premissas=("classe setor × arquétipo (≥ 8 emissores)" if ref["tipo"] == "setor_arquetipo"
                               else "setor (classe setor × arquétipo com menos de 8 emissores)"))
        po = i["porte"]
        f_porte = (prov_codigo("inclinação de porte estimada nesta execução (Theil–Sen do ROE de 5 anos contra o "
                               "log do patrimônio contábil em US$, dentro do setor; emissores cobertos"
                               + (", DADOS SIMULADOS)" if self._sintetico() else ")")))
        ic = po.get("ic95")
        ic_txt = (f"; inclinação estimada {num(po.get('b_bruto'), 4)}, IC 95% [{num(ic[0], 4)}; {num(ic[1], 4)}], "
                  f"{po.get('n')} emissores" if ic else "")
        if po.get("delta_ln") is not None and po.get("b"):
            reg.add("dir.roe_porte", "Ajuste de porte da norma",
                    "a = mín(máx(b × (ln patrimônio em US$ − mediana do setor); −5 p.p.); 5 p.p.)",
                    f"a = mín(máx({num(po['b'], 4)} × {operando(num(po['delta_ln'], 2))}; −5 p.p.); 5 p.p.)",
                    po["ajuste"], "%", [f_porte],
                    premissas="b = inclinação de Theil–Sen do ROE de 5 anos contra o log do patrimônio contábil "
                              "em US$ dentro do setor, estimada nesta execução, significativa a 95% e limitada ao "
                              "intervalo da configuração" + ic_txt)
        elif po.get("significativa") is False and ic:
            reg.nota("dir.roe_porte", "Ajuste de porte da norma",
                     "Sem ajuste de porte: a inclinação do ROE de 5 anos contra o log do patrimônio contábil em US$ "
                     f"não é significativa nesta execução{ic_txt} (o intervalo de 95% contém zero).")
        k_txt = "ke sem a calibração de nível" if abs(i["ke"] - cc.ke) > 1e-12 else "ke"
        reg.add("dir.roe_norma", "Norma de longo prazo do ROE", f"norma = {k_txt} + s + a",
                f"norma = {pct(i['ke'])} + {_op_pct(i['spread'])} + {_op_pct(po['ajuste'])}", i["norma"], "%",
                premissas=("a norma não depende do ajuste de nível do país: o spread s foi estimado contra o ke sem "
                           "ele" if k_txt != "ke" else None))
        cl_pt = {"estavel": "estável", "normal": "normal", "instavel": "instável"}[i["classe"]]
        hist = f"ROE de 5 anos {pct(i['roe5'])}" if i.get("roe5") is not None else "sem ROE de 5 anos"
        if i.get("rbar") is not None:
            partes = [x for x in (i.get("roe5"), i.get("roe2")) if x is not None]
            expr = " + ".join(_op_pct(x) for x in partes)
            reg.add("dir.roe_proprio", "ROE próprio de referência (R̄)",
                    "R̄ = média(ROE de 5 anos; ROE_2), limitado a [norma − 5 p.p.; norma + 15 p.p.]",
                    f"R̄ = mín(máx(({expr}) ÷ {len(partes)}; {pct(i['norma'] + i['faixa'][0])}); "
                    f"{pct(i['norma'] + i['faixa'][1])})", i["rbar_limitado"], "%",
                    premissas=f"{hist}; desvio-padrão {pct(i.get('sigma'))}; {i['prejuizo']} exercício(s) com prejuízo")
            reg.add("dir.roe_alvo", "ROE de convergência (persistência por classe)",
                    "ROE_alvo = norma + θ × (R̄ − norma)",
                    f"ROE_alvo = {pct(i['norma'])} + {num(i['theta'])} × ({pct(i['rbar_limitado'])} − {_op_pct(i['norma'])})",
                    i["alvo"], "%", [f_norm],
                    premissas=(f"classe {cl_pt} ({i['classe_motivo']}): θ = {num(i['theta'])} (fração permanente do "
                               f"desvio), ω = {num(i['omega'])} (decaimento anual do caminho do ROE)"))
        else:
            reg.add("dir.roe_alvo", "ROE de convergência (sem histórico próprio)", "ROE_alvo = norma",
                    f"ROE_alvo = {pct(i['norma'])}", i["alvo"], "%",
                    premissas=f"sem ROE de 5 anos nem ROE do ano 2; classe {cl_pt}: ω = {num(i['omega'])}")

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
                                 int(proj["anos_rim"]), self.payout_sust, omega=self.omega, inflacao=pi).valor
            return M.rim_gls(self.b0, r1, r2, ra, ke, self.payout, int(proj["anos_rim"]), self.payout_sust,
                             omega=self.omega).valor
        if m == "pb_justificado":
            rs = self.roe_sust + d_rs
            return M.pb_gordon(rs, ke, g, self._estrito) * self.b0
        if m == "multiplo_justificado":
            # P/L justificado é hiperbólico no ROE (1 − g ÷ ROE): o choque de ROE entra pela
            # derivada (resposta linear, média preservada); ke e g pela fórmula exata
            base = M.pl_justificado(self.roe_sust, ke, g, self._estrito)
            deriv = (g / self.roe_sust ** 2) / (ke - g)
            h, gc = self._modelo_h()
            fator = M.fator_h(np.maximum(gc, g), g, h) if h else 1.0
            return (base + deriv * d_rs) * self.eps1 * fator
        if m in ("ddm", "ddm_real"):
            rs = self.roe_sust + d_rs
            g1 = np.clip(rs * (1 - self.payout), -0.05, 0.15)
            dps1 = self.eps1 * self.payout * (1 + d_rs / max(self.roe_sust, 1e-6))
            if m == "ddm_real":
                pi = cc.pi_local
                # dividendo do ano 1 em moeda de hoje (deflacionado), descontado ao ke real
                return M.ddm_dois_estagios(dps1 / (1 + pi), real(g1, pi), real(g, pi), (1 + ke) / (1 + pi) - 1,
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

    def _caminho_margem_ciclo(self, n_anos: int) -> np.ndarray | float:
        """Commodities: margem EBIT corrente revertendo à margem mediana do ciclo com o mesmo perfil
        do choque de preço (plena nos anos 1–3, linear até zero no ano 5, nenhuma na perpetuidade):
        ``margem_t = margem_ciclo + (margem_corrente − margem_ciclo) × w_t``. Sem margem corrente,
        a do ciclo em todos os anos."""
        if self.margem is None or self.margem_hist is None:
            return self.margem_hist if self.margem_hist is not None else self.margem
        mc = self.params.sec("cenarios")["monte_carlo"]
        w = M.perfil_transitorio(n_anos, int(mc.get("commodity_anos_plenos", 3)), int(mc.get("commodity_zero_em", 5)))
        return self.margem_hist + (self.margem - self.margem_hist) * w

    def _modelo_h(self) -> tuple[float, float]:
        """``(H, g_curto)`` do P/L justificado com crescimento extraordinário (modelo H): H = metade
        da duração equivalente do crescimento com persistência φ do setor (≤ ``h_max``); g_curto =
        LPA_2 ÷ LPA_1 − 1 limitado a [g; ``g_curto_max``]."""
        mh = self.params.sec("multiplo_h")
        phi = float(self.params.valuation["fade_phi"].get(self.pac["setor"], 0.85))
        h = min(float(mh["h_fator"]) / (1 - phi), float(mh["h_max"]))
        e1, e2 = self.eps1, self.eps2
        if e1 is None or e2 is None or e1 <= 0 or e2 <= 0:
            return 0.0, self.cc.g
        gc = min(max(e2 / e1 - 1, self.cc.g), float(mh["g_curto_max"]))
        return h, gc

    def _participacao_controladores(self) -> tuple[float, str]:
        """Fração do valor do patrimônio dos controladores nos métodos pelo valor da firma.
        ``proporcional``: PL dos controladores ÷ (PL dos controladores + minoritários), pelo balanço
        (minoritários a valor proporcional ao do patrimônio); ``contabil`` ou sem PL positivo: 1 e
        minoritários subtraídos pelo valor contábil (devolve fração ``None`` nesse caso)."""
        mino = float(self.pac["minoritarios"])
        pl = _f(self.pac.get(self.k_pl))
        modo = str(self.params.valuation.get("minoritarios", "contabil"))
        if modo == "proporcional" and pl is not None and pl > 0 and mino >= 0:
            return pl / (pl + mino), "proporcional"
        return 1.0, "contabil"

    def _patrimonio(self, ev: np.ndarray) -> np.ndarray:
        """Valor do patrimônio por unidade a partir do EV: ``(EV − DL) × fração dos controladores ÷ N``
        (minoritários proporcionais) ou ``(EV − DL − minoritários contábeis) ÷ N``."""
        nd = float(self.pac["divida_liquida"])
        mino = float(self.pac["minoritarios"])
        frac, modo = self._participacao_controladores()
        if modo == "proporcional":
            return (np.asarray(ev) - nd) * frac / float(self.pac["unidades"])
        return (np.asarray(ev) - nd - mino) / float(self.pac["unidades"])

    def _fcff_args(self, m: str) -> dict[str, Any]:
        """Argumentos do caso-base do FCFF (escalares; termos reais no ``fcff_real``)."""
        cc = self.cc
        proj = self.params.sec("projecao")
        phi = float(self.params.valuation["fade_phi"].get(self.pac["setor"], 0.85))
        margem = self.margem
        if m == "fcff_normalizado" and self.margem_hist is not None:
            margem = self._caminho_margem_ciclo(int(proj["anos_explicitos"]))
        spread = float(self.params.sec("perpetuidade")["spread_min_ke_g"])
        gt = min(cc.g, cc.wacc - spread)
        roic0 = self.roic0 if self.roic0 is not None else cc.wacc
        vida = None
        if m == "fcff_vida_finita" and self.pac.get("fim_concessao"):
            vida = int(self.pac["fim_concessao"]) - date.fromisoformat(self.pac["as_of"]).year
        a = {"receita0": self.receita0, "g1": self.g1, "g2": self.g2, "g_term": gt, "phi": phi, "margem": margem,
             "imposto": cc.imposto, "roic0": roic0, "wacc": cc.wacc, "anos": int(proj["anos_explicitos"]),
             "vida": vida, "reinvest_lim": tuple(proj["reinvestimento_limites"]), "ronic_final": self.ronic_final,
             "reinvest_obs": self.rr_obs,
             "runoff_fracao": float(proj.get("concessao_fracao_final", 0.0)) if vida is not None else None,
             "g_runoff": cc.pi_local, "ano_convergencia": proj.get("reinvestimento_convergencia_ano")}
        if m == "fcff_real":
            pi = cc.pi_local
            a.update({"g1": real(self.g1, pi), "g2": real(self.g2, pi), "g_term": real(gt, pi),
                      "roic0": real(roic0, pi), "wacc": real(cc.wacc, pi), "g_runoff": 0.0,
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
        return self._F(res, self._patrimonio(res.ev))

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
        return self._patrimonio(ev)

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
                        motivo = "valor do patrimônio não positivo (dissidência: conta na dispersão como zero)"
                        info["valor_calculado"] = v
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
        self._excluir_discrepante()

    def _excluir_discrepante(self) -> None:
        """Combinação robusta (G18): com ≥ ``metodo_discrepante_min`` métodos válidos, o método cujo valor
        fica fora de [1/f; f] × a mediana dos DEMAIS (o mais distante, um por emissor) é LIMITADO à borda
        do intervalo — nunca retirado: a combinação fica monótona no valor de cada método (um custo da
        dívida maior nunca eleva o preço-alvo). Só quando os demais concordam (CV ≤
        ``metodo_discrepante_cv_demais``) e o discrepante não está do lado do preço (dissidência a favor
        do mercado nunca é limitada); senão o método fica como está. Em todos os casos a dissidência
        conta na dispersão usada na confiança e no G11 (valores brutos; não positivos como zero)."""
        self.discrepante = None
        q = self.params.sec("qualidade")
        f = float(q.get("metodo_discrepante_fator", 3.0))
        n_min = int(q.get("metodo_discrepante_min", 3))
        cv_dem = float(q.get("metodo_discrepante_cv_demais", 0.10))
        val = {m: d["valor"] for m, d in self.metodos.items() if d.get("valor") is not None and d["peso"] > 0}
        if len(val) < n_min:
            return
        piores = []
        for m, v in val.items():
            outros = [x for k, x in val.items() if k != m]
            med = float(np.median(outros))
            if med > 0:
                r = v / med
                if r > f or r < 1 / f:
                    piores.append((abs(math.log(r)), m, r, med, outros))
        if not piores:
            return
        _, m, r, med, outros = max(piores)
        info = self.metodos[m]
        v = info["valor"]
        cv_o = float(np.std(outros, ddof=0) / np.mean(outros))
        p0 = _f(self.pac.get("preco"))
        lado_preco = p0 is not None and (v - med) * (p0 - med) > 0
        limitar = cv_o <= cv_dem and not lado_preco
        borda = med * f if r > f else med / f
        self.discrepante = {"metodo": m, "valor": v, "razao": r, "mediana_demais": med, "fator": f,
                            "cv_demais": cv_o, "lado_preco": bool(lado_preco), "limitado": bool(limitar),
                            "valor_limitado": borda if limitar else None}
        if limitar:
            info["valor_bruto"], info["valor"], info["limitado"] = v, borda, True
            motivo = (f"método discrepante: {self._p(v)} = {num(r, 2)} × a mediana dos demais ({self._p(med)}), fora de "
                      f"[1/{num(f, 0)}; {num(f, 0)}], com os demais concordando (CV {pct(cv_o, 0)}): limitado a "
                      f"{self._p(borda)} na combinação")
            info["motivo_limite"] = motivo
            self.reg.nota(f"metodo.{m}.discrepante", NOME_METODO[m], f"{motivo}.")
        else:
            why = ("do lado do preço (dissidência a favor do mercado)" if lado_preco
                   else f"demais métodos sem consenso (CV {pct(cv_o, 0)} > {pct(cv_dem, 0)})")
            self.reg.nota(f"metodo.{m}.discrepante", NOME_METODO[m],
                          f"Método discrepante ({self._p(v)} = {num(r, 2)} × a mediana dos demais, {self._p(med)}) "
                          f"mantido na média: {why}; a dispersão entre métodos reflete a dissidência.")

    def _limitar_discrepante(self, vals: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Aplica o limite do G18 por sorteio/ponto da grade: o método discrepante fica em
        [mediana dos demais ÷ f; f × mediana dos demais] (monótono no valor do próprio método)."""
        d = getattr(self, "discrepante", None)
        if not d or not d.get("limitado") or d["metodo"] not in vals or len(vals) < 2:
            return vals
        m, f = d["metodo"], float(d["fator"])
        outros = [np.asarray(vals[k], dtype=float) for k in vals if k != m]
        shp = np.broadcast_shapes(*[o.shape for o in outros], np.asarray(vals[m]).shape)
        med = np.median(np.stack([np.broadcast_to(o, shp) for o in outros]), axis=0)
        out = dict(vals)
        out[m] = np.clip(np.broadcast_to(np.asarray(vals[m], dtype=float), shp), med / f, med * f)
        return out

    def dispersao_todos(self) -> tuple[float | None, list[dict[str, Any]]]:
        """CV entre TODOS os métodos calculados (valores brutos, inclusive o discrepante limitado; não
        positivos como zero) e a lista de dissidências — usado na confiança e na corroboração do G11."""
        vs, dis = [], []
        for m, d in self.metodos.items():
            if d["peso"] <= 0:
                continue
            if d.get("valor") is not None:
                vb = d.get("valor_bruto", d["valor"])
                vs.append(float(vb))
                if d.get("limitado"):
                    dis.append({"metodo": m, "tipo": "limitado", "valor": vb})
            elif d.get("valor_calculado") is not None:
                vs.append(0.0)
                dis.append({"metodo": m, "tipo": "nao_positivo", "valor": d["valor_calculado"]})
        dsc = getattr(self, "discrepante", None)
        if dsc and not dsc.get("limitado"):
            dis.append({"metodo": dsc["metodo"], "tipo": "mantido", "valor": dsc["valor"]})
        if len(vs) < 2 or np.mean(vs) <= 0:
            return None, dis
        return float(np.std(vs, ddof=0) / np.mean(vs)), dis

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
        q = self.params.sec("qualidade")
        mg_max = float(q.get("margem_ebit_max", 1.0))
        if (m.startswith("fcff") or m == "regressao_ev_receita") and self.margem is not None \
                and self.margem > mg_max and p["arquetipo"] in ("holding", "imobiliario"):
            return (f"margem EBIT de {pct(self.margem, 0)} acima de {pct(mg_max, 0)} (resultado de participações ou "
                    "de propriedades para investimento no EBIT): método pelo valor da firma indisponível")
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
            fator = _f((sp.get("visao_casa") or {}).get("fator")) or 1.0
            if preco_ is not None and rm is not None and ra:
                self._sotp_base = preco_ * rm / ra * fator
            elif _f(p.get("unidades")):
                self._sotp_base = float(sp["nav"]) * (1 - float(sp["desconto_reserva"])) / float(p["unidades"]) * fator
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
            res = M.rim_gls(self.b0, r1, r2, ra, ke, self.payout, int(proj["anos_rim"]), self.payout_sust,
                            omega=self.omega, inflacao=pi if realm else 0.0)
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
            b_t, roe_t = float(res.b[-1]), float(res.roe[-1])
            disc = (1 + ke) ** n
            if self.omega is not None:
                form_t = (f"(ROE_alvo − ke) × B_{n} ÷ (ke × (1 + ke)^{n}) + (ROE_{n} − ROE_alvo) × B_{n} × ω ÷ "
                          f"((1 + ke − ω) × (1 + ke)^{n})")
                sub_t = (f"({pct(ra)} − {pct(ke)}) × {P(b_t)} ÷ ({pct(ke)} × {num(disc, 4)}) + ({pct(roe_t)} − {pct(ra)}) "
                         f"× {P(b_t)} × {num(self.omega)} ÷ ((1 + {pct(ke)} − {num(self.omega)}) × {num(disc, 4)})")
            else:
                form_t = f"(ROE_alvo − ke) × B_{n} ÷ (ke × (1 + ke)^{n})"
                sub_t = f"({pct(ra)} − {pct(ke)}) × {P(b_t)} ÷ ({pct(ke)} × {num(disc, 4)})"
            reg.add(f"metodo.{m}.perpetuidade", nome + sufixo + ": perpetuidade (valor presente)", form_t, sub_t,
                    float(res.pv_terminal), f"preco:{self.moeda}",
                    premissas=(f"patrimônio constante a partir de B_{n} (convenção GLS); perpetuidade ao ROE de "
                               f"convergência {pct(ra)}"
                               + (f" mais o desvio residual de {pp(roe_t - ra, 1)} no ano {n} decaindo à razão ω = "
                                  f"{num(self.omega)} ao ano" if self.omega is not None else "")
                               + ("; patrimônio real deflacionado pela inflação (B_t = B_{t−1} × (1 + ROE nominal × "
                                  f"(1 − k)) ÷ (1 + {pct(pi)}))" if realm else "")))
            reg.add(f"metodo.{m}", nome + sufixo,
                    f"V0 = B0 + Σ_{{t=1..{n}}} (ROE_t − ke) × B_{{t−1}} ÷ (1 + ke)^t + perpetuidade",
                    f"V0 = {P(self.b0)} + {Op(float(res.pv_explicito))} + {Op(float(res.pv_terminal))}",
                    v, f"preco:{self.moeda}",
                    premissas=(f"parcelas: patrimônio por ação, valor presente do lucro residual dos anos 1–{n} e da "
                               f"perpetuidade; ROE {pct(r1)} → {pct(r2)} → "
                               + (f"decaimento exponencial ao ROE de convergência {pct(ra)} "
                                  f"(ROE_t = ROE_alvo + (ROE_2 − ROE_alvo) × {num(self.omega)}^(t−2); "
                                  f"{pct(roe_t)} no ano {n})"
                                  if self.omega is not None else f"{pct(ra)} no ano {n}")
                               + f"; ke {pct(ke)}; payout {pct(self.payout)} → {pct(self.payout_sust)}"))
            return ft
        if m == "pb_justificado":
            pb = float(M.pb_gordon(self.roe_sust, cc.ke, cc.g))
            reg.add(f"metodo.{m}", nome, "V0 = B0 × (ROE_sust − g) ÷ (ke − g)",
                    f"V0 = {P(self.b0)} × ({pct(self.roe_sust)} − {pct(cc.g)}) ÷ ({pct(cc.ke)} − {pct(cc.g)})",
                    v, f"preco:{self.moeda}", premissas=f"P/VPA justificado = {mult(pb)}")
            return None
        if m == "multiplo_justificado":
            pe = float(M.pl_justificado(self.roe_sust, cc.ke, cc.g))
            h, gc = self._modelo_h()
            if h:
                fh = float(M.fator_h(max(gc, cc.g), cc.g, h))
                reg.add(f"metodo.{m}", nome,
                        "V0 = LPA_1 × (1 − g ÷ ROE_sust) ÷ (ke − g) × (1 + H × (g_c − g) ÷ (1 + g))",
                        f"V0 = {P(self.eps1)} × (1 − {pct(cc.g)} ÷ {pct(self.roe_sust)}) ÷ ({pct(cc.ke)} − {pct(cc.g)}) × "
                        f"(1 + {num(h, 2)} × ({pct(gc)} − {pct(cc.g)}) ÷ (1 + {pct(cc.g)}))",
                        v, f"preco:{self.moeda}",
                        premissas=(f"P/L justificado em regime = {mult(pe)}; modelo H (Fuller e Hsia): fator "
                                   f"{num(fh, 3)}, g_c = LPA_2 ÷ LPA_1 − 1 limitado a [g; "
                                   f"{pct(self.params.sec('multiplo_h')['g_curto_max'], 0)}], H = mín(0,5 ÷ (1 − φ); 8) "
                                   f"anos com φ do setor"))
            else:
                reg.add(f"metodo.{m}", nome, "V0 = LPA_1 × (1 − g ÷ ROE_sust) ÷ (ke − g)",
                        f"V0 = {P(self.eps1)} × (1 − {pct(cc.g)} ÷ {pct(self.roe_sust)}) ÷ ({pct(cc.ke)} − {pct(cc.g)})",
                        v, f"preco:{self.moeda}", premissas=f"P/L justificado = {mult(pe)}")
            return None
        if m in ("ddm", "ddm_real"):
            g1 = min(max(self.roe_sust * (1 - self.payout), -0.05), 0.15)
            realm = m == "ddm_real"
            dps1 = self.eps1 * self.payout / ((1 + cc.pi_local) if realm else 1.0)
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
                               f"{P(dps1)} (LPA_1 × payout" + (f" ÷ (1 + {pct(cc.pi_local)}), em moeda de hoje"
                                                                if realm else "") + f"); g1 = ROE_sust × (1 − k) = "
                               f"{pct(g1r)}; g = {pct(gg)}; ke = {pct(ke)}"))
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
                desc = (f"sem perpetuidade; fluxos até {int(self.pac['fim_concessao'])}" if self.pac.get("fim_concessao")
                        else "prazo de concessão não curado: carteira tratada como renovável (com perpetuidade)")
            elif m == "fcff_normalizado":
                desc = (f"margem EBIT corrente {pct(self.margem)} revertendo à mediana do ciclo {pct(self.margem_hist)} "
                        "(plena nos anos 1–3, linear até o ano 5; perpetuidade na margem do ciclo)"
                        if self.margem_hist is not None and self.margem is not None
                        else "margem corrente (histórico de menos de 3 exercícios)")
            elif m == "fcff_real":
                desc = "fluxos, WACC e crescimento em termos reais"
            else:
                desc = "margem EBIT corrente"
            mg = self.margem
            rr_txt = (f"reinvestimento observado {pct(self.rr_obs)} nos anos 1–2, convergindo a g ÷ RONIC"
                      if self.rr_obs is not None else "reinvestimento g ÷ RONIC desde o ano 1")
            lim_txt = ""
            if res.limite_atingido:
                lo, hi = self.params.sec("projecao")["reinvestimento_limites"]
                anos_l = ", ".join(str(a) for a in res.limite_atingido)
                lim_txt = f"; reinvestimento limitado a [{pct(lo, 0)}; {pct(hi, 0)}] do NOPAT nos anos {anos_l}"
                self.avisos.append(f"{nome}: reinvestimento limitado a [{pct(lo, 0)}; {pct(hi, 0)}] do NOPAT "
                                   f"nos anos {anos_l}")
            frac, modo_mi = self._participacao_controladores()
            if m == "fcff_vida_finita" and self.pac.get("fim_concessao"):
                desc += ("; no último terço do prazo o crescimento real e o reinvestimento líquido convergem a zero "
                         "(sem renovação nem indenização)")
            if modo_mi == "proporcional":
                form_v0 = ("EV = Σ FCFF_t ÷ (1 + WACC)^t + NOPAT_{T+1} × (1 − g ÷ RONIC) ÷ (WACC − g) ÷ (1 + WACC)^T; "
                           "V0 = (EV − DL) × PL_ctrl ÷ (PL_ctrl + minoritários) ÷ N")
                sub_v0 = (f"V0 = ({self._t(float(res.ev))} − {operando(self._t(self.pac['divida_liquida']))}) × "
                          f"{pct(frac)} ÷ {contagem(self.pac['unidades'])}")
                mi_txt = ("; minoritários a valor proporcional ao patrimônio (fração dos controladores = PL dos "
                          f"controladores {self._t(self.pac.get(self.k_pl))} ÷ (PL dos controladores + "
                          f"minoritários contábeis {self._t(self.pac['minoritarios'])}))")
            else:
                form_v0 = ("EV = Σ FCFF_t ÷ (1 + WACC)^t + NOPAT_{T+1} × (1 − g ÷ RONIC) ÷ (WACC − g) ÷ (1 + WACC)^T; "
                           "V0 = (EV − DL − minoritários) ÷ N")
                sub_v0 = (f"V0 = ({self._t(float(res.ev))} − {operando(self._t(self.pac['divida_liquida']))} − "
                          f"{operando(self._t(self.pac['minoritarios']))}) ÷ {contagem(self.pac['unidades'])}")
                mi_txt = ""
            reg.add(f"metodo.{m}", nome, form_v0, sub_v0,
                    v, f"preco:{moe}", self._fonte("fim_concessao") if m == "fcff_vida_finita" else [],
                    premissas=(f"EV = valor presente dos fluxos {self._t(float(res.pv_explicito))} + perpetuidade "
                               f"{self._t(float(res.pv_terminal))}; receita {self._t(self.receita0)}, g1 "
                               f"{pct(self.g1)}, g2 {pct(self.g2)}, margem {pct(mg)}, WACC {pct(self.cc.wacc)}, "
                               f"g {pct(self.cc.g)}, ROIC {pct(self.roic0)} → RONIC {pct(self.ronic_final)}; {rr_txt}"
                               f"{lim_txt}; {desc}{mi_txt}"))
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
            bruto = prever_bruto(r, self.fund, self.pac["pais"])
            fa = r.get("faixa_amostra")
            if fa and bruto is not None and abs(bruto - mm) > 1e-9:
                reg.add(f"metodo.{m}.multiplo", f"{nome}: múltiplo do emissor (limitado à faixa da amostra)",
                        f"{sigla} = mín(máx(a + {regs_txt} + efeito país; P5); P95) (Huber, n = {r['n']}, "
                        f"R² = {num(r['r2'])})",
                        f"{sigla} = mín(máx({' + '.join(partes)}; {mult(fa[0])}); {mult(fa[1])})", mm, "x",
                        premissas=f"{pais_txt}; previsão sem limite {mult(bruto)}; P5–P95 dos múltiplos da amostra")
            else:
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
                frac, modo_mi = self._participacao_controladores()
                if modo_mi == "proporcional":
                    sub = (f"V0 = ({mult(mm)} × {self._t(self.receita0)} − {operando(self._t(self.pac['divida_liquida']))}) × "
                           f"{pct(frac)} ÷ {contagem(self.pac['unidades'])}")
                    form = "V0 = (EV/Receita_reg × receita − DL) × PL_ctrl ÷ (PL_ctrl + minoritários) ÷ N"
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
            vc = sp.get("visao_casa") or {}
            fator = _f(vc.get("fator")) or 1.0
            if vc:
                reg.add(f"metodo.{m}.visao_casa", "Soma das partes: visão da casa sobre as participações",
                        "fator = Σ participação a mercado × (V0 ÷ P0 da investida) ÷ Σ participação a mercado",
                        "fator = " + " + ".join(f"{q['emissor']} {num(q['razao_v0_p0'], 3)}" for q in vc.get("partes", []))
                        + " (ponderados pelo valor de mercado de cada participação)", fator, "x",
                        premissas="; ".join(f"{q['emissor']}: {q['motivo']}" for q in vc.get("partes", []))
                        + ". A holding herda a visão da casa sobre as investidas citáveis (A ou B); o desconto da "
                          "holding reverte à mediana histórica à parte")
            if sp.get("razao_mediana") is not None:
                reg.add(f"metodo.{m}", nome,
                        "V0 = P0 × mediana(valor de mercado ÷ NAV) ÷ (valor de mercado ÷ NAV)_hoje × fator da casa",
                        f"V0 = {P(self.pac['preco'])} × {num(sp['razao_mediana'], 3)} ÷ {num(sp['razao_atual'], 3)} × "
                        f"{num(fator, 3)}",
                        v, f"preco:{self.moeda}",
                        premissas=f"NAV = {total(sp['nav'], self.moeda)}: {partes}; mediana de {janela}")
            else:
                reg.add(f"metodo.{m}", nome, "V0 = NAV × (1 − desconto de reserva) ÷ N × fator da casa",
                        f"V0 = {total(sp['nav'], self.moeda)} × (1 − {pct(sp['desconto_reserva'])}) ÷ "
                        f"{contagem(self.pac['unidades'])} × {num(fator, 3)}", v, f"preco:{self.moeda}",
                        premissas=f"histórico insuficiente para a mediana ({janela}); {partes}")
            return None
        return None

    # ------------------------------------------------------------------ 4. combinação e rolagem
    def combinar(self, vals: Mapping[str, np.ndarray], piso: bool = True) -> np.ndarray | None:
        """Média ponderada pelos pesos do arquétipo; por sorteio, só os métodos com valor finito
        (pesos renormalizados); sorteio sem nenhum método válido ⇒ ``NaN``. Sem piso por
        método: o piso de zero (responsabilidade limitada) vale só para o valor combinado e só
        quando ``piso`` (o alpha usa a média sem piso; ver :meth:`_cenarios`)."""
        if not vals:
            return None
        vals = self._limitar_discrepante(dict(vals))
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
        return np.maximum(out, 0.0) if piso else out

    def avaliar(self) -> dict[str, Any]:
        """Modelo completo do emissor (antes da etapa transversal de rating)."""
        self.preparar_metodos()
        reg, cc, P = self.reg, self.cc, self._p
        p0 = _f(self.pac.get("preco"))
        validos = self.metodos_validos()
        out: dict[str, Any] = {"tem_alvo": False}
        if not validos or p0 is None or self.dps12 is None:
            # Sem método válido, o motivo diz por quê, método a método (ex.: banco que publica só
            # em IFRS sem o patrimônio dos controladores no XBRL público).
            faltas = "; ".join(f"{i['nome']}: {i['motivo']}" for i in self.metodos.values()
                               if i.get("motivo"))
            motivo = (("nenhum método com insumos suficientes" + (f" ({faltas})" if faltas else ""))
                      if not validos else
                      "preço indisponível" if p0 is None else "dividendo esperado indisponível")
            reg.nota("alvo", "Preço-alvo de 12 meses", f"Sem preço-alvo: {motivo}.")
            out["motivo_sem_alvo"] = motivo
            return self._saida(out)
        base = Drivers()
        vals = self._limitar_discrepante({m: np.asarray(self._valor_metodo(m, base), dtype=float) for m in validos})
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
            reg.add("alvo.cv", "Dispersão entre métodos (valores combinados)", "CV = desvio-padrão(V_m) ÷ média(V_m)",
                    f"CV = desvio-padrão({lista}) ÷ média({lista})", cv, "%")
        cv_todos, dissid = self.dispersao_todos()
        if dissid and cv_todos is not None:
            brutos = [float(d.get("valor_bruto", d["valor"])) if d.get("valor") is not None else 0.0
                      for d in self.metodos.values() if d["peso"] > 0 and (d.get("valor") is not None
                                                                         or d.get("valor_calculado") is not None)]
            lista = "; ".join(P(x) for x in brutos)
            reg.add("alvo.cv_todos", "Dispersão entre todos os métodos calculados (com a dissidência)",
                    "CV_todos = desvio-padrão(V_m brutos; não positivos como 0) ÷ média",
                    f"CV_todos = desvio-padrão({lista}) ÷ média({lista})", cv_todos, "%",
                    premissas="dissidência: " + "; ".join(
                        f"{NOME_METODO[d['metodo']]} ({'limitado na combinação' if d['tipo'] == 'limitado' else 'valor do patrimônio não positivo' if d['tipo'] == 'nao_positivo' else 'discrepante mantido na média'})"
                        for d in dissid) + "; é a dispersão usada na confiança e na corroboração do G11")
        pesos = self.params.pesos(self.pac["arquetipo"])
        principal = max(sorted(pesos), key=lambda k: pesos[k])
        principal_dissidente = any(d["metodo"] == principal and d["tipo"] in ("limitado", "nao_positivo")
                                   for d in dissid)
        out.update({"tem_alvo": True, "v0": v0, "tp": tp, "etr": etr, "upside": up, "cv": cv,
                    "cv_todos": cv_todos if dissid else cv, "dissidencia": dissid,
                    "metodo_principal": principal, "principal_dissidente": bool(principal_dissidente),
                    "n_metodos": len(validos), "n_metodos_calculados": len(validos) + sum(
                        1 for d in dissid if d["tipo"] == "nao_positivo")})
        out.update(self._fcff_observado())
        out.update(self._cenarios(p0, tp, etr, validos))
        out.update(self._tp_ke_estatico(p0, tp))
        out["sensibilidade"] = self._sensibilidade(p0)
        out["icc"] = self._icc(p0)
        out["reverso"] = self._reverso(p0)
        return self._saida(out)

    def _tp_ke_estatico(self, p0: float, tp: float) -> dict[str, Any]:
        """Sensibilidade: preço-alvo do caso-base com o ke do ERP estático (tabela semestral)."""
        cc = self.cc
        d = cc.ke_estatico - cc.ke
        if abs(d) < 1e-12:
            return {}
        dr = Drivers(d_ke=d)
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
        if v0 is None or not np.isfinite(float(v0)):
            return {}
        tpe = float(M.rolagem(v0, cc.ke_estatico, self.dps12))
        self.reg.add("sensibilidade.ke_estatico", "Sensibilidade: preço-alvo com o ke do ERP estático",
                     "TP12' = V0(ke') × (1 + ke') − DPS12",
                     f"TP12' = {self._p(float(v0))} × (1 + {pct(cc.ke_estatico)}) − {self._p(self.dps12)}", tpe,
                     f"preco:{self.moeda}",
                     premissas=(f"ke' = {pct(cc.ke_estatico)} com ERP {pct(cc.erp_estatico)} (oficial {pct(cc.ke)} com "
                                f"ERP {pct(cc.erp)}); sensibilidade de um fator: só o ERP muda, com o ajuste de nível do "
                                f"país e a norma de ROE mantidos (numa reestimação completa o ajuste de nível "
                                f"reabsorveria a maior parte do efeito); upside {pct(tpe / p0 - 1, 1, True)} contra "
                                f"{pct(tp / p0 - 1, 1, True)}"))
        return {"tp_ke_estatico": tpe, "upside_ke_estatico": tpe / p0 - 1}

    def _fcff_observado(self) -> dict[str, Any]:
        """Ano 1 contra a identidade observada definida pelos parâmetros arquivados do retrato."""
        ms = [m for m in self.metodos_validos() if m.startswith("fcff")]
        if not ms:
            return {}
        res = self._fcff(ms[0], Drivers()).res
        fc1 = float(res.fcff[0])
        razao = None if self.fcf_obs is None or self.fcf_obs <= 0 else fc1 / self.fcf_obs
        ri = self.rr_info or {}
        return {"fcff_ano1": fc1, "fcf_observado": self.fcf_obs, "fcff_ano1_vs_observado": razao,
                "reinvestimento_limitado_anos": list(res.limite_atingido),
                "rr_observado": ri.get("rr"), "rr_observado_base": ri.get("base"),
                "rr_contaminado": bool(self.rr_contaminado),
                **({"reinvestimento_metodo": self.rr_metodo,
                    "reinvestimento_observado": dict(ri)} if self.rr_metodo is not None else {})}

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
        falhas_cenarios: list[str] = []
        self._estrito = False
        try:
            for m in validos:
                try:
                    vals[m] = np.broadcast_to(np.asarray(self._valor_metodo(m, dr), dtype=float), (n,))
                except (ValueError, ZeroDivisionError):
                    continue
        finally:
            self._estrito = True
        v0_bruto = self.combinar(vals, piso=False)
        ke = self._ke(dr)
        tps_bruto = np.asarray(M.rolagem(v0_bruto, ke, self.dps12), dtype=float)
        ok = np.isfinite(tps_bruto)
        diagnostico = None
        if "g20_corroboracao_metodos_min" in self.params.sec("qualidade"):
            faltantes = sorted(set(validos) - set(vals))
            if faltantes:
                falhas_cenarios.append("métodos do caso-base ausentes na simulação: " + ", ".join(faltantes))
            nao_finitos = {m: int(np.count_nonzero(~np.isfinite(v))) for m, v in vals.items()
                          if not np.isfinite(v).all()}
            if nao_finitos:
                falhas_cenarios.append("métodos com sorteios não finitos: "
                                      + "; ".join(f"{m}: {qt}" for m, qt in sorted(nao_finitos.items())))
            # Choque zero deve reproduzir o caso-base, com os mesmos métodos e pesos. O diagnóstico
            # não depende de onde o preço de mercado fica dentro da faixa de cenários.
            base = {m: np.asarray(self._valor_metodo(m, Drivers()), dtype=float) for m in validos}
            tp_zero = float(M.rolagem(self.combinar(base), self.cc.ke, self.dps12))
            erro_base = abs(tp_zero - tp) / max(abs(tp), 1e-12)
            if erro_base > float(self.params.sec("qualidade")["g20_cenarios_base_tolerancia"]):
                falhas_cenarios.append("choque zero não reproduz o preço-alvo do caso-base")
            diagnostico = {"falhas": falhas_cenarios, "metodos_esperados": list(validos),
                           "metodos_usados": sorted(vals), "sorteios_finitos": int(ok.sum()),
                           "sorteios_total": n, "erro_reproducao_base": erro_base}
        p_zero = float(np.mean(np.asarray(v0_bruto)[ok] <= 0)) if ok.any() else None
        rets_bruto = (tps_bruto[ok] + self.dps12) / p0 - 1
        tps = np.maximum(tps_bruto[ok], 0.0)
        rets = (tps + self.dps12) / p0 - 1
        p10, p50, p90 = (float(x) for x in np.percentile(tps, [10, 50, 90]))
        r10, r50, r90 = (float(x) for x in np.percentile(rets, [10, 50, 90]))
        # α pela média SEM o piso de zero: os sorteios são incerteza de parâmetros em torno do caso-base,
        # não valores terminais dos ativos; com o piso, a massa em zero inflaria a média (desigualdade de
        # Jensen) em emissores alavancados. O retorno com responsabilidade limitada é exibido à parte.
        pwr = float(np.mean(rets_bruto))
        pwr_piso = float(np.mean(rets))
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
        reg.add("cenarios.pwr", "Retorno ponderado por probabilidade (PWR)",
                "PWR = média de (V0^(k) × (1 + ke^(k)) − DPS12 + DPS12) ÷ P0 − 1, sem o piso de zero",
                f"PWR = média dos {inteiro(len(rets_bruto))} retornos simulados", pwr, "%",
                premissas=(f"retorno do caso-base (ETR) = {pct(etr)}; diferença = {pp(pwr - etr, 1)} (convexidade das "
                           f"fórmulas); probabilidade de patrimônio não positivo nos sorteios = {pct(p_zero, 1)}"))
        reg.add("cenarios.pwr_piso", "Retorno com responsabilidade limitada (exibido, não usado no alpha)",
                "PWR_piso = média de (máx(TP^(k); 0) + DPS12) ÷ P0 − 1",
                f"PWR_piso = média dos {inteiro(len(rets))} retornos simulados com piso de zero", pwr_piso, "%",
                premissas=f"valor de opção do piso = {pp(pwr_piso - pwr, 1)} sobre o PWR")
        reg.add("cenarios.alpha", "Alpha de valuation", "α = PWR − ke", f"α = {_op_pct(pwr)} − {pct(self.cc.ke)}",
                alpha, "%")
        vol = _f(self.pac.get("vol_12m"))
        pm_bull = pm_bear = None
        if vol is not None and vol > 0:
            dy = self.dps12 / p0
            mu = self.cc.ke - dy
            # Só quando a faixa de cenários envolve o preço (P10 ≤ P0 ≤ P90): com o cenário adverso
            # acima do preço (ou o favorável abaixo), a "probabilidade implícita" perde o sentido.
            envolve = p10 <= p0 <= p90
            pm_bull = (float(1 - norm.cdf((math.log(p90 / p0) - (mu - vol * vol / 2)) / vol))
                       if p90 > 0 and envolve else None)
            pm_bear = (float(norm.cdf((math.log(p10 / p0) - (mu - vol * vol / 2)) / vol))
                       if p10 > 0 and envolve else None)
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
                "pwr_com_piso": pwr_piso, "p_patrimonio_zero": p_zero,
                "ret_p10": r10, "ret_p50": r50, "ret_p90": r90, "udr": udr, "assimetria": skew,
                "perda_esperada_cauda": es, "prob_modelo_supera_ke": p_ke,
                "prob_mercado_otimista": pm_bull, "prob_mercado_pessimista": pm_bear,
                "largura_cenarios": largura, "n_sorteios": int(len(tps)),
                **({"diagnostico_cenarios": diagnostico} if diagnostico is not None else {})}

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
            out["gls"] = M.icc_gls(p0, self.b0, self.roe1, self.roe2, self.roe_alvo, self.payout,
                                   omega=self.omega)
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
        out["n_eps"], out["consenso_raso"] = self.n_eps, bool(self.consenso_raso)
        out["eps1_consenso"] = self.eps1_fonte != "lucro dos últimos 12 meses (sem consenso)"
        out["peso_patrimonial"] = self.peso_patrimonial()
        out["eps2_modelo"], out["roe2"], out["roe_alvo"] = self.eps2, self.roe2, self.roe_alvo
        out["fracao_exercicio"], out["calendarizado"] = self.f_ex, bool(self.calendarizado)
        out["persistencia_roe"] = None if self.alvo_roe_info is None else {
            k: (r6(v) if isinstance(v, float) else v) for k, v in self.alvo_roe_info.items()
            if k not in ("referencia", "pais_setor", "porte")} | {
            "referencia": self.alvo_roe_info.get("referencia"), "porte": self.alvo_roe_info.get("porte")}
        out["margem"] = self.margem
        if self.params.sec("qualidade").get("margem_fluxos_metodo") is not None:
            out["margem_fluxos"] = self.margem_fluxos
        out["metodo_discrepante"] = getattr(self, "discrepante", None)
        out["lacunas"] = self.lacunas + [{"insumo": f"metodo.{d['m']}", "nome": NOME_METODO[d["m"]],
                                          "motivo": d["motivo"]}
                                         for d in self.metodos.values() if d.get("motivo")]
        out["avisos"] = self.avisos
        return out


__all__ = ["Avaliador", "Drivers", "METODOS_PATRIMONIAIS", "semente"]
_ = (prov_codigo, METODOS_LUCRO)  # reexportados para quem monta passos externos
