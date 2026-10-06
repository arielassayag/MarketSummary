"""Custo de capital (abordagem λ de Damodaran em dólar, convertida pela inflação relativa).

``ke_USD = (rf_UST10 − spread_EUA) + β_aj × ERP + λ × CRP_país``;
``β_aj = 0,67 × β + 0,33`` limitado a [0,5; 1,8], ``β = β_u × (1 + (1 − t) × D/E)`` (não
financeiras; β desalavancado setorial de Damodaran) ou mediana dos betas de regressão dos pares
(financeiras, sem realavancar);
``ke_local = (1 + ke_USD)(1 + π_local)/(1 + π_EUA) − 1``; ``ke_real = (1 + ke_local)/(1 + π_local) − 1``;
``WACC = E/V × ke + D/V × kd × (1 − t)``, ``kd`` em dólar = rf + spread soberano + spread
corporativo (rating sintético pela cobertura de juros estimada em base dólar), convertido como o ke e
limitado ao ke; ``g = (1 + g_real)(1 + π_local) − 1``, limitado a ``rf_local`` e a ``ke − 3 p.p.``.
``δ`` (ajuste de nível do modelo por país, do contexto) entra no ke em dólar; as sensibilidades (ERP
estático, prêmio implícito) são de um fator a partir do ke oficial.

Dívida ``D`` (realavancagem e pesos do WACC) = dívida bruta + passivos de arrendamento (IFRS 16),
a mesma definição da dívida líquida descontada do valor da firma; sem arrendamentos publicados,
só a dívida bruta (registrado no passo).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .formato import mult, num, operando, pct, pp, total
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


def erp_oficial(cc: dict[str, Any]) -> tuple[float, str]:
    """ERP oficial pelo ``modo_erp``: ``contemporaneo`` (par de Damodaran da mesma data do UST) ou
    ``estatico`` (prêmio maduro da tabela semestral de risco-país). Devolve ``(erp, chave da fonte)``."""
    if str(cc.get("modo_erp", "estatico")) == "contemporaneo":
        return float(cc["erp_contemporaneo"]), "damodaran_erp_mensal"
    return float(cc["erp_maduro"]), "damodaran_ctryprem"


def wacc(ke: float, kd: float, imposto: float, e: float, d: float) -> float:
    v = e + d
    if v <= 0:
        raise ValueError("Capital total não positivo.")
    return e / v * ke + d / v * kd * (1 - imposto)


def spread_corporativo(pac: dict[str, Any], cc: dict[str, Any], rf: float | None = None,
                       spread_pais: float | None = None) -> tuple[float, str | None, float | None, str]:
    """Spread corporativo pelo rating sintético de Damodaran: cobertura de juros = EBIT ÷ despesa de
    juros estimada, com a despesa = dívida bruta (com arrendamentos) × custo de referência em dólar
    (``rf + spread soberano + spread de reserva``) — a cobertura fica em base dólar (a tabela de
    Damodaran é de empresas dos EUA; juros nominais em moeda de inflação alta a deprimiriam) e nunca
    usa o resultado financeiro líquido (que mistura variação cambial, derivativos, correção monetária e
    receita de aplicações). Sem EBIT positivo, sem dívida, com caixa líquido ou sem os insumos, o spread
    de reserva da política. Devolve ``(spread, rating, cobertura, motivo)``."""
    tab = cc.get("spread_sintetico")
    reserva = float(cc["spread_credito_corporativo"])
    ebit, db, arr = pac.get("t.ebit"), pac.get("divida_bruta"), pac.get("arrendamentos")
    nd = pac.get("divida_liquida")
    if not tab or ebit is None or db is None or rf is None or spread_pais is None:
        return reserva, None, None, "EBIT ou dívida bruta indisponível"
    ebit = float(ebit)
    d = float(db) + (float(arr) if arr is not None else 0.0)
    if d <= 0:
        return reserva, None, None, "sem dívida bruta"
    if nd is not None and float(nd) <= 0:
        return reserva, None, None, "caixa líquido (dívida líquida não positiva)"
    if ebit <= 0:
        return reserva, None, None, "EBIT de 12 meses não positivo (cobertura indefinida)"
    k_ref = rf + spread_pais + reserva
    cob = ebit / (d * k_ref)
    for minimo, rating, spread in tab:
        if cob >= float(minimo):
            return float(spread), str(rating), cob, ""
    return float(tab[-1][2]), str(tab[-1][1]), cob, ""


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
    ke_estatico: float           # ke com o ERP estático (sensibilidade exibida)
    erp_estatico: float
    delta_pais: float = 0.0      # ajuste do prêmio implícito pelo mercado do país (κ × gap), em dólar
    ke_implicito_pais: float | None = None   # sensibilidade: ke com o gap integral do prêmio implícito
    delta_calibracao: float = 0.0            # calibração de nível do país (mediana de V0 ÷ P0 = 1)
    ke_sem_calibracao: float | None = None

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def pp_txt(x: float) -> str:
    """``0.03`` → ``3 p.p.``"""
    return f"{num(x * 100, 0)} p.p."


def _pais_crp(pais: str, cc: dict[str, Any]) -> str:
    return pais if pais in cc["crp"] else "LATAM"


def calcular(pac: dict[str, Any], params: ParametrosCobertura, rf_ust: float | None,
             rf_fonte: dict[str, Any], beta_pares: float | None, n_pares_beta: int,
             reg: Registro | None = None, lista_pares: list[list[Any]] | None = None,
             premio_pais: dict[str, Any] | None = None,
             calibracao: dict[str, Any] | None = None) -> CustoCapital:
    """Monta o custo de capital do emissor e registra cada passo (``ke.*``).

    ``premio_pais`` (do contexto transversal): prêmio total implícito pelo mercado do país e o
    do motor; entra no ke em dólar com peso κ (``premio_implicito_pais.kappa``) e é sempre exibido
    como sensibilidade com o gap integral."""
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

    erp, chave_erp = erp_oficial(cc)
    erp_est = float(cc["erp_maduro"])
    crp = float(cc["crp"][pais_crp])
    lam = float(pac.get("lambda") or cc["lambda_padrao"])
    if chave_erp == "damodaran_erp_mensal":
        rf_par = float(cc.get("rf_par_erp", rf_ust))
        tol_par = float(cc.get("rf_par_tolerancia", 0.0025))
        prem = (f"par contemporâneo de Damodaran de {cc.get('erp_contemporaneo_data')}: prêmio implícito com o UST de "
                f"{pct(rf_par)}; UST do dia {pct(rf_ust)}")
        if abs(rf_ust - rf_par) > tol_par:
            prem += (f"; diferença de {pp(rf_ust - rf_par, 2)} acima de {pp(tol_par, 2, False)}: par a revisar na "
                     "próxima atualização mensal")
        reg.add("ke.erp", "Prêmio de risco de mercado maduro (ERP contemporâneo)",
                "ERP = prêmio implícito do mercado maduro na mesma data do UST − spread de default dos EUA",
                f"ERP = prêmio implícito de {cc.get('erp_contemporaneo_data')} (Damodaran, série mensal)", erp, "%",
                [params.fonte(chave_erp)], premissas=prem)
    else:
        reg.add("ke.erp", "Prêmio de risco de mercado maduro (ERP)", "ERP = prêmio implícito de mercado maduro",
                "ERP = prêmio de mercado maduro (Damodaran, tabela de risco-país vigente)", erp, "%", [f_ctry])
    reg.add("ke.crp", f"Prêmio de risco país ({pais_crp}) × exposição λ",
            "λ × CRP (CRP = spread soberano × volatilidade relativa ações/títulos)",
            f"λ × CRP = {num(lam)} × {pct(crp)}", lam * crp, "%", [f_ctry])
    k_usd_puro = ke_usd(rf, beta_aj, erp, lam, crp)
    delta, ke_impl, ke_impl_gap = 0.0, None, None
    pip = cc.get("premio_implicito_pais") or {}
    if premio_pais and premio_pais.get("premio_implicito") is not None:
        kappa = float(pip.get("kappa", 0.0))
        lim_d = float(pip.get("limite", 0.01))
        gap = float(premio_pais["premio_implicito"]) - float(premio_pais["premio_motor"])
        gap_lim = min(max(gap, -lim_d), lim_d)
        delta = kappa * gap_lim if int(premio_pais.get("n", 0)) >= int(pip.get("n_min", 8)) else 0.0
        ke_impl_gap = gap_lim - delta
    d_cal = 0.0
    if calibracao and calibracao.get("delta") is not None:
        d_cal = float(calibracao["delta"])
        regional = calibracao.get("grupo") == "regional"
        if regional:
            reg.add("ke.calibracao_pais", "Ajuste de nível do modelo (regional): viés dos fluxos da casa, não prêmio de risco",
                    "δ = mediana ponderada pelo nº de emissores dos δ dos países calibrados",
                    "δ = mediana ponderada dos δ dos países calibrados", d_cal, "%",
                    [prov_codigo("ajustes de nível dos países com ao menos 8 emissores com preço-alvo")],
                    premissas=(f"{calibracao.get('paises_txt')}; {calibracao.get('n')} emissor(es) do país com preço-alvo, "
                               f"mediana de V0 ÷ P0 sem o ajuste = {num(calibracao.get('mediana_v_p_sem_calibracao'), 3)}, "
                               f"com o ajuste regional = {num(calibracao.get('mediana_v_p'), 3)}. Os preços-alvo absolutos "
                               "são relativos ao mercado"))
        else:
            reg.add("ke.calibracao_pais", f"Ajuste de nível do modelo ({pais}): viés dos fluxos da casa, não prêmio de risco",
                    "δ tal que mediana(V0 ÷ P0) = 1 nos emissores do país com preço-alvo, limitado a ±1,5 p.p.",
                    f"δ tal que mediana(V0 ÷ P0) = 1 (sem o ajuste: {num(calibracao.get('mediana_v_p_sem_calibracao'), 3)}; "
                    f"com o ajuste: {num(calibracao.get('mediana_v_p'), 3)})",
                    d_cal, "%",
                    [prov_codigo("mediana de V0 ÷ P0 dos emissores cobertos do país, com as premissas do modelo")],
                    premissas=(f"{calibracao.get('n')} emissores com preço-alvo; mediana de V0 ÷ P0 sem o ajuste = "
                               f"{num(calibracao.get('mediana_v_p_sem_calibracao'), 3)}; deslocamento necessário "
                               f"{pp(calibracao.get('delta_bruto'), 2)}"
                               + ("; limitado a ±1,5 p.p." if calibracao.get("limitado") else "")
                               + f"; ponto fixo em {calibracao.get('passadas')} passada(s)"
                               + ". É um ajuste do nível dos fluxos do modelo (o mercado do país é tomado como "
                                 "corretamente apreçado na mediana), não um prêmio de risco: a carteira é neutra a país e "
                                 "o rating é relativo a país × setor; os preços-alvo absolutos são relativos ao mercado"))
    k_usd = k_usd_puro + delta + d_cal
    if ke_impl_gap is not None:
        ke_impl = fisher(k_usd_puro + delta + d_cal + ke_impl_gap, float(cc["inflacao_lp"].get(moeda, cc["inflacao_lp"]["USD"])),
                         float(cc["inflacao_lp"]["USD"]))
    if d_cal:
        reg.add("ke.usd", "Custo de capital próprio em dólar",
                "ke_USD = rf + β_aj × ERP + λ × CRP + δ (ajuste de nível do modelo)",
                f"ke_USD = {pct(rf)} + {num(beta_aj)} × {pct(erp)} + {num(lam)} × {pct(crp)} + {operando(pct(d_cal + delta))}",
                k_usd, "%")
    elif delta:
        reg.add("ke.usd", "Custo de capital próprio em dólar",
                "ke_USD = rf + β_aj × ERP + λ × CRP + κ × (prêmio implícito do país − prêmio do motor)",
                f"ke_USD = {pct(rf)} + {num(beta_aj)} × {pct(erp)} + {num(lam)} × {pct(crp)} + {operando(pct(delta))}",
                k_usd, "%")
    else:
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

    perp = params.sec("perpetuidade")
    g_real = min(float(perp["g_real"]), float(perp["g_real_max"]))
    g = (1 + g_real) * (1 + pi_local) - 1
    g_bruto = g
    termos = [f"(1 + {pct(g_real)}) × (1 + {pct(pi_local)}) − 1"]
    if perp.get("g_menor_que_rf", True):
        termos.append(f"rf_local: {pct(rf_local)}")
        g = min(g, rf_local)
    spread_min = float(perp["spread_min_ke_g"])
    termos.append(f"ke − {pp_txt(spread_min)}: {pct(ke - spread_min)}")
    g = min(g, ke - spread_min)
    reg.add("ke.g", "Crescimento nominal na perpetuidade",
            "g = mín((1 + g_real) × (1 + π_local) − 1; rf_local; ke − 3 p.p.)",
            f"g = mín({'; '.join(termos)})", g, "%", [params.fonte_config("perpetuidade")],
            premissas=f"sem limite: {pct(g_bruto)}")

    kd = w = peso_d = None
    rating_sint = None
    if not pac["financeira"]:
        spread_pais = float(cc["spread_default_pais"].get(pais_crp, cc["spread_default_pais"]["LATAM"]))
        spread_corp, rating_sint, cob, motivo_kd = spread_corporativo(pac, cc, rf, spread_pais)
        reserva = float(cc["spread_credito_corporativo"])
        if rating_sint is not None:
            d_tot = float(pac["divida_bruta"]) + float(pac.get("arrendamentos") or 0.0)
            prem_kd = (f"rating sintético {rating_sint}: cobertura de juros = EBIT ÷ (dívida bruta com arrendamentos × "
                       f"custo de referência em dólar) = {total(pac.get('t.ebit'), moeda)} ÷ ({total(d_tot, moeda)} × "
                       f"({pct(rf)} + {pct(spread_pais)} + {pct(reserva)})) = {num(cob)}x (tabela de Damodaran, empresas "
                       "não financeiras de grande porte, janeiro de 2026; cobertura em base dólar, sem o resultado "
                       "financeiro líquido)")
            fontes_kd = [f_ctry, params.fonte("damodaran_ratings")]
        else:
            prem_kd = f"{motivo_kd}: spread corporativo de reserva da política"
            fontes_kd = [f_ctry, params.fonte_config("custo da dívida")]
        kd_usd = rf + spread_pais + spread_corp
        kd_bruto = fisher(kd_usd, pi_local, pi_us)
        kd = min(kd_bruto, ke)
        if kd < kd_bruto:
            prem_kd += f"; limitado ao ke ({pct(kd_bruto)} sem o limite): a dívida nunca custa mais que o capital próprio"
        reg.add("ke.kd", f"Custo da dívida em {moeda} (antes de impostos)",
                "kd = mín((1 + rf + spread soberano + spread corporativo) × (1 + π_local)/(1 + π_EUA) − 1; ke)",
                f"kd = mín((1 + {pct(rf)} + {pct(spread_pais)} + {pct(spread_corp)}) × (1 + {pct(pi_local)}) / "
                f"(1 + {pct(pi_us)}) − 1; {pct(ke)})",
                kd, "%", fontes_kd, premissas=prem_kd)
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

    # sensibilidades de um fator a partir do ke oficial (o ajuste de nível do país mantido)
    k_est = fisher(k_usd + beta_aj * (erp_est - erp), pi_local, pi_us)
    k_sem_cal = fisher(k_usd_puro + delta, pi_local, pi_us)
    if d_cal:
        reg.add("ke.sem_calibracao", "Sensibilidade: ke sem a calibração de nível do país",
                "ke' = (1 + rf + β_aj × ERP + λ × CRP) × (1 + π_local) / (1 + π_EUA) − 1",
                f"ke' = (1 + {pct(rf)} + {num(beta_aj)} × {pct(erp)} + {num(lam)} × {pct(crp)}) × "
                f"(1 + {pct(pi_local)}) / (1 + {pct(pi_us)}) − 1", k_sem_cal, "%")
    if chave_erp == "damodaran_erp_mensal":
        reg.add("ke.estatico", "Sensibilidade: ke com o ERP estático (tabela semestral), um fator",
                "ke' = (1 + ke_USD + β_aj × (ERP_estático − ERP)) × (1 + π_local) / (1 + π_EUA) − 1",
                f"ke' = (1 + {pct(k_usd)} + {num(beta_aj)} × ({pct(erp_est)} − {pct(erp)})) × "
                f"(1 + {pct(pi_local)}) / (1 + {pct(pi_us)}) − 1", k_est, "%", [f_ctry],
                premissas=("só o ERP muda (ajuste de nível do país mantido); ERP maduro da tabela de risco-país de "
                           "julho, calculado quando o UST era menor; exibido como sensibilidade, não usado no "
                           "preço-alvo. Numa reestimação completa com o ERP estático, o ajuste de nível do país "
                           "reabsorveria a maior parte do efeito (dentro do limite de ±1,5 p.p.)"))
    if ke_impl is not None and premio_pais is not None:
        gap = float(premio_pais["premio_implicito"]) - float(premio_pais["premio_motor"])
        lim_d = float(pip.get("limite", 0.01))
        reg.add("ke.implicito_pais", f"Sensibilidade: ke com o prêmio implícito pelo mercado ({pais}), um fator",
                "ke'' = (1 + ke_USD + (1 − κ) × mín(máx(prêmio implícito − prêmio do motor; −1 p.p.); 1 p.p.)) × "
                "(1 + π_local) / (1 + π_EUA) − 1",
                f"ke'' = (1 + {pct(k_usd)} + {operando(pct(ke_impl_gap))}) × "
                f"(1 + {pct(pi_local)}) / (1 + {pct(pi_us)}) − 1", ke_impl, "%",
                [prov_codigo("prêmio total implícito agregado dos emissores cobertos do país (LPA de consenso, "
                             "payout em caixa, g = rf local)")],
                premissas=(f"prêmio implícito do país {pct(premio_pais['premio_implicito'])} (taxa implícita local "
                           f"{pct(premio_pais.get('r_local'))}, {premio_pais.get('n')} emissores) contra "
                           f"{pct(premio_pais['premio_motor'])} do motor (média ponderada por valor de mercado de "
                           f"β × ERP + λ × CRP); peso no ke oficial κ = {num(float(pip.get('kappa', 0.0)), 2)}"))
    _ = (mult, operando)  # noqa: F841 - formatação usada por outros módulos
    return CustoCapital(rf_ust=rf_ust, rf=rf, erp=erp, crp=crp, lam=lam, beta=beta_aj, beta_fonte=fonte_b,
                        ke_usd=k_usd, pi_local=pi_local, pi_us=pi_us, ke=ke, ke_real=ke_r,
                        rf_local=rf_local, g=g, g_real=(1 + g) / (1 + pi_local) - 1, imposto=imposto,
                        kd=kd, wacc=w, peso_divida=peso_d, ke_estatico=k_est, erp_estatico=erp_est,
                        delta_pais=delta, ke_implicito_pais=ke_impl, delta_calibracao=d_cal, ke_sem_calibracao=k_sem_cal)


__all__ = ["CustoCapital", "beta_realavancado", "blume", "calcular", "erp_oficial", "fisher", "ke_usd", "real",
           "spread_corporativo",
           "wacc", "MOEDA_PAIS"]
