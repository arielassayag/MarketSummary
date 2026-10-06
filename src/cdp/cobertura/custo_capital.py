"""Custo de capital (abordagem λ de Damodaran em dólar, convertida pela inflação relativa).

``ke_USD = (rf_UST10 − spread_EUA) + β_aj × ERP + λ × CRP_país``;
``β_aj = 0,67 × β + 0,33`` limitado a [0,5; 1,8], ``β = β_u × (1 + (1 − t) × D/E)`` (não
financeiras; β desalavancado setorial de Damodaran) ou mediana dos betas de regressão dos pares
(financeiras, sem realavancar);
``ke_local = (1 + ke_USD)(1 + π_local)/(1 + π_EUA) − 1``; ``ke_real = (1 + ke_local)/(1 + π_local) − 1``;
``WACC = E/V × ke + D/V × kd × (1 − t)``, ``kd`` em dólar = rf + spread soberano + spread
corporativo, convertido como o ke; ``g = (1 + g_real)(1 + π_local) − 1``, limitado a ``rf_local``
e a ``ke − 3 p.p.``.

Dívida ``D`` (realavancagem e pesos do WACC) = dívida bruta + passivos de arrendamento (IFRS 16),
a mesma definição da dívida líquida descontada do valor da firma; sem arrendamentos publicados,
só a dívida bruta (registrado no passo).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .formato import mult, num, operando, pct, total
from .parametros import MOEDA_PAIS, ParametrosCobertura
from .passos import Registro, prov_codigo


def fisher(taxa_usd: float, pi_local: float, pi_us: float) -> float:
    """Converte uma taxa em dólar para a moeda local pelo diferencial de inflação."""
    return (1 + taxa_usd) * (1 + pi_local) / (1 + pi_us) - 1


def real(taxa_nominal: float, pi: float) -> float:
    return (1 + taxa_nominal) / (1 + pi) - 1


def beta_realavancado(beta_u: float, d_e: float, imposto: float) -> float:
    """Hamada: ``β = β_u × (1 + (1 − t) × D/E)``."""
    return beta_u * (1 + (1 - imposto) * d_e)


def blume(beta: float, a: float = 0.67, b: float = 0.33) -> float:
    return a * beta + b


def ke_usd(rf: float, beta: float, erp: float, lam: float, crp: float) -> float:
    return rf + beta * erp + lam * crp


def wacc(ke: float, kd: float, imposto: float, e: float, d: float) -> float:
    v = e + d
    if v <= 0:
        raise ValueError("Capital total não positivo.")
    return e / v * ke + d / v * kd * (1 - imposto)


@dataclass(frozen=True)
class CustoCapital:
    rf_ust: float
    rf: float
    erp: float
    crp: float
    lam: float
    beta: float
    beta_fonte: str
    ke_usd: float
    pi_local: float
    pi_us: float
    ke: float                    # moeda do modelo
    ke_real: float
    rf_local: float
    g: float                     # perpetuidade nominal na moeda do modelo
    g_real: float
    imposto: float
    kd: float | None
    wacc: float | None
    peso_divida: float | None
    ke_contemporaneo: float      # ERP contemporâneo (sensibilidade)

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def pp_txt(x: float) -> str:
    """``0.03`` → ``3 p.p.``"""
    return f"{num(x * 100, 0)} p.p."


def _pais_crp(pais: str, cc: dict[str, Any]) -> str:
    return pais if pais in cc["crp"] else "LATAM"


def calcular(pac: dict[str, Any], params: ParametrosCobertura, rf_ust: float | None,
             rf_fonte: dict[str, Any], beta_pares: float | None, n_pares_beta: int,
             reg: Registro | None = None, lista_pares: list[list[Any]] | None = None) -> CustoCapital:
    """Monta o custo de capital do emissor e registra cada passo (``ke.*``)."""
    reg = reg or Registro()
    cc = params.cc
    pais = str(pac["pais"])
    moeda = str(pac["moeda"])
    pais_crp = _pais_crp(pais, cc)
    imposto = float(cc["imposto_marginal"].get(pais_crp, cc["imposto_marginal"]["LATAM"]))
    f_ctry = params.fonte("damodaran_ctryprem")
    f_infl = params.fonte("damodaran_inflacao")
    f_tax = params.fonte("damodaran_impostos")

    if rf_ust is None:
        rf_ust = float(cc["rf_usd_reserva"])
        rf_fonte = {**params.fonte("damodaran_erp_mensal"),
                    "documento": f"UST 10 anos de reserva ({cc['rf_usd_reserva_data']}): série pública indisponível"}
    spread_eua = float(cc["spread_default_eua"])
    rf = rf_ust - spread_eua
    reg.add("ke.rf", "Taxa livre de risco em dólar",
            "rf = UST 10 anos − spread de default dos EUA",
            f"rf = {pct(rf_ust)} − {pct(spread_eua)}", rf, "%", [rf_fonte, f_ctry])

    lim = cc["beta"]["limites"]
    a, b = cc["beta"]["blume"]
    if pac["financeira"]:
        if beta_pares is not None:
            bruto, fonte_b = beta_pares, f"mediana dos betas de regressão de {n_pares_beta} pares"
            lista = "; ".join(f"{iid} {num(b)}" for iid, b in (lista_pares or []))
            reg.add("ke.beta_bruto", "β de mercado (financeiras: mediana dos pares)",
                    "β = mediana dos β de regressão semanal (USD, 104 semanas) dos pares contra o ILF",
                    f"β = mediana dos β de {n_pares_beta} pares", bruto, "n",
                    [prov_codigo("regressão semanal de retornos em USD (preços públicos)")],
                    premissas=f"pares e β de regressão: {lista}" if lista else None)
        elif pac.get("beta_regressao") is not None:
            bruto, fonte_b = float(pac["beta_regressao"]), "regressão própria (sem pares suficientes)"
            reg.add("ke.beta_bruto", "β de mercado (regressão própria)",
                    "β = cov(r_ação, r_ILF) / var(r_ILF), retornos semanais em USD",
                    f"β = regressão com {pac.get('beta_regressao_semanas')} semanas", bruto, "n",
                    [pac["fontes"].get("beta_regressao") or prov_codigo("regressão")])
        else:
            bruto, fonte_b = float(pac["beta_u_setor"]), "β setorial de Damodaran (sem regressão)"
            reg.add("ke.beta_bruto", "β setorial (sem regressão disponível)", "β = β setorial",
                    f"β = β desalavancado setorial de {pac.get('industria')}", bruto, "n",
                    [pac["fontes"].get("beta_u_setor", {})])
    else:
        bu = float(pac["beta_u_setor"])
        de = pac.get("d_e_mercado")
        arr_txt = ("dívida bruta + arrendamentos" if pac.get("arrendamentos") is not None
                   else "dívida bruta (arrendamentos não publicados)")
        if de is None:
            de = pac.get("d_e_pares")
            de_txt = "D/E mediano dos pares (D/E próprio indisponível)"
        else:
            de_txt = f"D/E de mercado: ({arr_txt}) ÷ valor de mercado"
        if pac.get("d_e_mercado") is None and pac.get("d_e_pares") is None:
            de_txt = "D/E indisponível: β desalavancado sem realavancagem"
            de = None
        if de is None:
            bruto = bu
            fonte_b = "β desalavancado setorial (Damodaran) sem realavancagem"
            reg.add("ke.beta_bruto", "β setorial sem realavancagem", "β = β_u (D/E indisponível)",
                    f"β = {num(bu)}", bruto, "n", [pac["fontes"].get("beta_u_setor", {})], premissas=de_txt)
        else:
            de = max(float(de), 0.0)
            bruto = beta_realavancado(bu, de, imposto)
            fonte_b = "β desalavancado setorial (Damodaran) realavancado"
            reg.add("ke.beta_bruto", "β realavancado (Hamada)",
                    "β = β_u × (1 + (1 − t) × D/E)",
                    f"β = {num(bu)} × (1 + (1 − {pct(imposto)}) × {num(de)})", bruto, "n",
                    [pac["fontes"].get("beta_u_setor", {}), f_tax], premissas=de_txt)
    beta_aj = min(max(blume(bruto, a, b), lim[0]), lim[1])
    reg.add("ke.beta", "β ajustado (Blume) e limitado",
            f"β_aj = mín(máx({num(a)} × β + {num(b)}; {num(lim[0])}); {num(lim[1])})",
            f"β_aj = mín(máx({num(a)} × {num(bruto)} + {num(b)}; {num(lim[0])}); {num(lim[1])})",
            beta_aj, "n", [prov_codigo(fonte_b)])

    erp = float(cc["erp_maduro"])
    crp = float(cc["crp"][pais_crp])
    lam = float(pac.get("lambda") or cc["lambda_padrao"])
    reg.add("ke.erp", "Prêmio de risco de mercado maduro (ERP)", "ERP = prêmio implícito de mercado maduro",
            "ERP = prêmio de mercado maduro (Damodaran, tabela de risco-país vigente)", erp, "%", [f_ctry])
    reg.add("ke.crp", f"Prêmio de risco país ({pais_crp}) × exposição λ",
            "λ × CRP (CRP = spread soberano × volatilidade relativa ações/títulos)",
            f"λ × CRP = {num(lam)} × {pct(crp)}", lam * crp, "%", [f_ctry])
    k_usd = ke_usd(rf, beta_aj, erp, lam, crp)
    reg.add("ke.usd", "Custo de capital próprio em dólar",
            "ke_USD = rf + β_aj × ERP + λ × CRP",
            f"ke_USD = {pct(rf)} + {num(beta_aj)} × {pct(erp)} + {num(lam)} × {pct(crp)}", k_usd, "%")

    infl = cc["inflacao_lp"]
    pi_us = float(infl["USD"])
    pi_local = float(infl.get(moeda, pi_us))
    if moeda not in infl:
        reg.nota("ke.inflacao_ausente", "Inflação da moeda do modelo",
                 f"Sem inflação de longo prazo para {moeda}: modelo tratado em base dólar.")
    ke = fisher(k_usd, pi_local, pi_us)
    reg.add("ke.local", f"Custo de capital próprio em {moeda} (diferencial de inflação)",
            "ke = (1 + ke_USD) × (1 + π_local) / (1 + π_EUA) − 1",
            f"ke = (1 + {pct(k_usd)}) × (1 + {pct(pi_local)}) / (1 + {pct(pi_us)}) − 1", ke, "%", [f_infl])
    ke_r = real(ke, pi_local)
    reg.add("ke.real", "Custo de capital próprio real", "ke_real = (1 + ke) / (1 + π_local) − 1",
            f"ke_real = (1 + {pct(ke)}) / (1 + {pct(pi_local)}) − 1", ke_r, "%")
    rf_local = fisher(rf, pi_local, pi_us)
    reg.add("ke.rf_local", f"Taxa livre de risco em {moeda}",
            "rf_local = (1 + rf) × (1 + π_local) / (1 + π_EUA) − 1",
            f"rf_local = (1 + {pct(rf)}) × (1 + {pct(pi_local)}) / (1 + {pct(pi_us)}) − 1", rf_local, "%")

    pp = params.sec("perpetuidade")
    g_real = min(float(pp["g_real"]), float(pp["g_real_max"]))
    g = (1 + g_real) * (1 + pi_local) - 1
    g_bruto = g
    termos = [f"(1 + {pct(g_real)}) × (1 + {pct(pi_local)}) − 1"]
    if pp.get("g_menor_que_rf", True):
        termos.append(f"rf_local: {pct(rf_local)}")
        g = min(g, rf_local)
    spread_min = float(pp["spread_min_ke_g"])
    termos.append(f"ke − {pp_txt(spread_min)}: {pct(ke - spread_min)}")
    g = min(g, ke - spread_min)
    reg.add("ke.g", "Crescimento nominal na perpetuidade",
            "g = mín((1 + g_real) × (1 + π_local) − 1; rf_local; ke − 3 p.p.)",
            f"g = mín({'; '.join(termos)})", g, "%", [params.fonte_config("perpetuidade")],
            premissas=f"sem limite: {pct(g_bruto)}")

    kd = w = peso_d = None
    if not pac["financeira"]:
        spread_pais = float(cc["spread_default_pais"].get(pais_crp, cc["spread_default_pais"]["LATAM"]))
        spread_corp = float(cc["spread_credito_corporativo"])
        kd_usd = rf + spread_pais + spread_corp
        kd = fisher(kd_usd, pi_local, pi_us)
        reg.add("ke.kd", f"Custo da dívida em {moeda} (antes de impostos)",
                "kd = (1 + rf + spread soberano + spread corporativo) × (1 + π_local)/(1 + π_EUA) − 1",
                f"kd = (1 + {pct(rf)} + {pct(spread_pais)} + {pct(spread_corp)}) × (1 + {pct(pi_local)}) / (1 + {pct(pi_us)}) − 1",
                kd, "%", [f_ctry, params.fonte_config("custo da dívida")])
        e_val = pac.get("valor_mercado")
        d_bruta = pac.get("divida_bruta")
        arr = pac.get("arrendamentos")
        d_val = None if d_bruta is None else float(d_bruta) + (float(arr) if arr is not None else 0.0)
        if e_val is not None and d_val is not None and e_val > 0:
            peso_d = d_val / (e_val + d_val)
            w = wacc(ke, kd, imposto, e_val, d_val)
            d_txt = (f"D = dívida bruta {total(d_bruta, moeda)} + arrendamentos {total(arr, moeda)}"
                     if arr is not None else f"D = dívida bruta {total(d_bruta, moeda)} (arrendamentos não publicados)")
            reg.add("ke.wacc", "Custo médio ponderado de capital (WACC)",
                    "WACC = E/V × ke + D/V × kd × (1 − t)",
                    f"WACC = {pct(1 - peso_d)} × {pct(ke)} + {pct(peso_d)} × {pct(kd)} × (1 − {pct(imposto)})",
                    w, "%", [f_tax], premissas=f"E = valor de mercado {total(e_val, moeda)}; {d_txt}")
        else:
            reg.nota("ke.wacc", "WACC", "WACC indisponível: valor de mercado ou dívida bruta ausente.")

    erp_c = float(cc["erp_contemporaneo"])
    k_c = fisher(ke_usd(rf, beta_aj, erp_c, lam, crp), pi_local, pi_us)
    reg.add("ke.contemporaneo", "Sensibilidade: ke com ERP contemporâneo",
            "ke' = (1 + rf + β_aj × ERP' + λ × CRP) × (1 + π_local) / (1 + π_EUA) − 1, com o ERP mensal",
            f"ke' = (1 + {pct(rf)} + {num(beta_aj)} × {pct(erp_c)} + {num(lam)} × {pct(crp)}) × "
            f"(1 + {pct(pi_local)}) / (1 + {pct(pi_us)}) − 1", k_c, "%",
            [params.fonte("damodaran_erp_mensal")])
    _ = (mult, operando)  # noqa: F841 - formatação usada por outros módulos
    return CustoCapital(rf_ust=rf_ust, rf=rf, erp=erp, crp=crp, lam=lam, beta=beta_aj, beta_fonte=fonte_b,
                        ke_usd=k_usd, pi_local=pi_local, pi_us=pi_us, ke=ke, ke_real=ke_r,
                        rf_local=rf_local, g=g, g_real=(1 + g) / (1 + pi_local) - 1, imposto=imposto,
                        kd=kd, wacc=w, peso_divida=peso_d, ke_contemporaneo=k_c)


__all__ = ["CustoCapital", "beta_realavancado", "blume", "calcular", "fisher", "ke_usd", "real",
           "wacc", "MOEDA_PAIS"]
