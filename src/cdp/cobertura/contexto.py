"""Contexto transversal da cobertura (pares, medianas setoriais e regressões de múltiplos).

Tudo é derivado dos pacotes de insumos do próprio snapshot (dados públicos), de forma
determinística, e arquivado em ``contexto.json`` para que ``cobertura verify`` refaça cada
modelo sem depender de nada externo.

- Medianas por setor GICS (e por país × setor com ≥ 5 nomes): ROE, ROE histórico, crescimento
  de receita, margem EBIT, payout, D/E de mercado.
- β das financeiras: mediana dos betas de regressão (USD, semanal) por país × setor, setor ou
  universo financeiro.
- Regressões transversais robustas (Huber, IRLS) com efeito fixo de país:
  ``P/VPA ~ ROE + g + β + payout`` (financeiras e não financeiras em separado),
  ``P/L ~ g + payout + β`` e ``EV/Receita ~ margem EBIT + g + alavancagem``. Regressão com
  R² abaixo do mínimo configurado fica indisponível (o método sai da média).
- Crescimento ``g`` usado como regressor: não financeiras, receita de consenso (ano 1) ou, sem
  ela, histórica; financeiras, crescimento do LPA de consenso (ano 2 ÷ ano 1) — a receita de
  instituições financeiras não é comparável entre fontes. Sempre limitado à faixa da projeção.
- Observação sem participação de não controladores publicada não entra na regressão de
  EV/Receita (nunca é tratada como zero). O múltiplo previsto é limitado ao P5–P95 da amostra.
- ROE próprio de longo prazo: mediana dos 5 últimos exercícios publicados (patrimônio positivo),
  com o desvio-padrão e a marca de prejuízo que definem a classe de estabilidade.
- Custo de capital de cada emissor (mesma função do modelo) e, com ele, as normas de ROE em
  spread sobre o ke sem o ajuste de nível (setor × arquétipo; setor encolhido para país × setor), a
  inclinação de porte (Theil–Sen do ROE de 5 anos contra o log do patrimônio contábil em dólar, dentro
  do setor, só quando significativa), o painel de persistência do ROE, o prêmio total implícito pelo
  mercado de cada país (sensibilidade) e o ajuste de nível do modelo por país (ponto fixo da mediana de
  V0 ÷ P0; grupo regional para os países com menos de 8 emissores).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy.stats import theilslopes

from .formato import r6
from .parametros import ParametrosCobertura
from .passos import Registro


def _med(xs: list[float]) -> float | None:
    v = [x for x in xs if x is not None and math.isfinite(x)]
    return float(np.median(v)) if v else None


def _iqr_sigma(xs: list[float]) -> float | None:
    v = [x for x in xs if x is not None and math.isfinite(x)]
    if len(v) < 5:
        return None
    q75, q25 = np.percentile(v, [75, 25])
    return float((q75 - q25) / 1.349)


LIMITES_G = (-0.20, 0.30)


def _limitar(x: float | None, lim: tuple[float, float]) -> float | None:
    return None if x is None else min(max(float(x), lim[0]), lim[1])


def fracao_exercicio(p: Mapping[str, Any]) -> float | None:
    """Fração decorrida do exercício corrente na data do snapshot: ``(as_of − fim do exercício
    anterior ao "ano 1" do consenso) ÷ 365``, limitada a [0; 1]. O fim do exercício segue o calendário
    do emissor (``fim_exercicio_consenso``: o último encerramento até a data, salvo dentro do prazo de
    entrega das demonstrações anuais), não só o último exercício presente no arquivo. Sem exercício
    publicado ⇒ ``None``."""
    from datetime import date as _date

    fye, d = p.get("fim_exercicio_consenso") or p.get("fim_exercicio"), p.get("as_of")
    if not fye or not d:
        return None
    dias = (_date.fromisoformat(str(d)) - _date.fromisoformat(str(fye)[:10])).days
    return min(max(dias / 365.0, 0.0), 1.0)


def roe_historico(p: Mapping[str, Any], anos_max: int = 5) -> dict[str, Any]:
    """ROE dos últimos ``anos_max`` exercícios publicados (lucro dos controladores ÷ patrimônio dos
    controladores do mesmo exercício, patrimônio positivo): mediana, desvio-padrão, anos com
    prejuízo e a lista ``[(ano, ROE)]``."""
    hist = p.get("historico") or {}
    luc, pl = hist.get("lucro_liquido_controladores", {}), hist.get("patrimonio_controladores", {})
    anos = sorted(set(luc) & set(pl))[-anos_max:]
    pares = [(a, luc[a] / pl[a]) for a in anos if pl[a] and pl[a] > 0 and luc[a] is not None]
    rs = [r for _, r in pares]
    return {"mediana": float(np.median(rs)) if len(rs) >= 3 else None,
            "sigma": float(np.std(rs, ddof=1)) if len(rs) >= 3 else None,
            "prejuizo": int(sum(1 for a in anos if luc.get(a) is not None and luc[a] < 0)),
            "n": len(rs), "serie": [[a, r6(r)] for a, r in pares]}


def reinvestimento_observado(p: Mapping[str, Any], imposto: float, anos: int = 3, *,
                            metodo: str | None = None, regime: str = "recente") -> dict[str, Any] | None:
    """Política selecionada pelos parâmetros arquivados de cada retrato.

    ``capitalizacao_arrendamentos`` usa a identidade de capital operacional (capex + adições ROU
    − D&A da DFC + ΔWC operacional) e exige componentes publicados no mesmo período. Sem a chave,
    preserva a fórmula histórica ``1 − Σ(CFO − capex − pagamentos de arrendamentos) ÷ Σ NOPAT``.
    A rubrica genérica de pagamentos da política histórica não certifica principal isolado.
    """
    if metodo == "capitalizacao_arrendamentos":
        from .reinvestimento import reinvestimento_capitalizado

        return reinvestimento_capitalizado(p, imposto, anos, regime)
    if metodo is not None:
        raise ValueError(f"Método de reinvestimento desconhecido: {metodo}.")
    # Política histórica: permanece idêntica para recálculos dos retratos anteriores à 2026-10.5.
    hist = p.get("historico") or {}
    cfo, capex, ebit = (hist.get(k) or {} for k in ("cfo", "capex", "ebit"))
    arr = hist.get("arrendamentos_pagos") or {}
    comuns = sorted(set(cfo) & set(capex) & set(ebit))[-anos:]
    if len(comuns) == anos and all(v is not None for a in comuns for v in (cfo[a], capex[a], ebit[a])):
        com_arr = all(arr.get(a) is not None for a in comuns)
        arr_s = sum(abs(float(arr[a])) for a in comuns) if com_arr else None
        fcf = sum(float(cfo[a]) - abs(float(capex[a])) for a in comuns) - (arr_s or 0.0)
        nopat = sum(float(ebit[a]) * (1 - imposto) for a in comuns)
        if nopat > 0:
            return {"rr": 1 - fcf / nopat, "base": f"{anos} exercícios", "anos": [str(a) for a in comuns],
                    "fcf": fcf, "nopat": nopat, "arrendamentos": arr_s}
    c, k, e = p.get("t.cfo"), p.get("t.capex"), p.get("t.ebit")
    if c is None or k is None or e is None or float(e) <= 0:
        return None
    la = p.get("t.arrendamentos_pagos")
    arr_t = None if la is None else abs(float(la))
    fcf, nopat = float(c) - abs(float(k)) - (arr_t or 0.0), float(e) * (1 - imposto)
    return {"rr": 1 - fcf / nopat, "base": "12 meses", "anos": [], "fcf": fcf, "nopat": nopat, "arrendamentos": arr_t}


def fundamentos(p: Mapping[str, Any], lim_g: tuple[float, float] = LIMITES_G,
                anos_roe: int = 5, calendarizar: bool = True) -> dict[str, float | None]:
    """Razões correntes do emissor a partir do pacote (moeda do modelo; nosso preço). Com
    ``calendarizar`` (``projecao.calendarizacao``), o LPA de consenso entra em 12 meses à frente
    (``(1 − f) × FY1 + f × FY2``), como no modelo."""
    def g(k: str) -> float | None:
        v = p.get(k)
        return None if v is None else float(v)

    preco, bvps, eps1, eps2, eps_ttm = g("preco"), g("bvps"), g("eps_fy1"), g("eps_fy2"), g("eps_ttm")
    g_eps = None if eps1 is None or eps2 is None or eps1 <= 0 else eps2 / eps1 - 1
    f_ex = fracao_exercicio(p) if calendarizar else None
    if eps1 is not None and eps2 is not None and f_ex is not None:
        eps1 = (1 - f_ex) * eps1 + f_ex * eps2
    dps = g("dps_12m")
    rec, ebit = g("t.receita"), g("t.ebit")
    hist = p.get("historico") or {}
    roe = None
    if eps_ttm is not None and bvps is not None and bvps > 0:
        roe = eps_ttm / bvps
    elif eps1 is not None and bvps is not None and bvps > 0:
        roe = eps1 / bvps
    rhist = roe_historico(p, anos_roe)
    roe_hist = rhist["mediana"]
    margem = None if rec is None or ebit is None or rec <= 0 else ebit / rec
    rh, eh = hist.get("receita", {}), hist.get("ebit", {})
    ms = [eh[a] / rh[a] for a in sorted(set(rh) & set(eh)) if rh[a] and rh[a] > 0]
    margem_hist = float(np.median(ms)) if len(ms) >= 3 else None
    margem_sd = float(np.std(ms, ddof=1)) if len(ms) >= 3 else None
    if p.get("financeira"):
        gr = g_eps
    else:
        gr = g("g_receita_fy1")
        if gr is None:
            gr = g("g_receita_historico")
    gr = _limitar(gr, lim_g)
    eps_ref = eps1 if eps1 is not None else eps_ttm
    payout = None
    if dps is not None and eps_ref is not None and eps_ref > 0:
        payout = min(max(dps / eps_ref, 0.0), 1.0)
    pb = None if preco is None or bvps is None or bvps <= 0 else preco / bvps
    pe = None if preco is None or eps1 is None or eps1 <= 0 else preco / eps1
    mcap, nd = g("valor_mercado"), g("divida_liquida")
    mino = g("minoritarios")
    ev = None if mcap is None or nd is None or mino is None else mcap + nd + mino
    ev_rec = None if ev is None or rec is None or rec <= 0 else ev / rec
    ebitda = g("t.ebitda")
    if ebitda is None and ebit is not None and g("t.d_a") is not None:
        ebitda = ebit + abs(g("t.d_a") or 0.0)
    alav = None if nd is None or ebitda is None or ebitda <= 0 else nd / ebitda
    pl_t = g("t.patrimonio_controladores")
    roic_pre = None if ebit is None or pl_t is None or nd is None or pl_t + nd <= 0 else ebit / (pl_t + nd)
    fx = g("fx_usd_moeda")
    mcap_usd = None if mcap is None or fx is None or mcap <= 0 else mcap * fx
    # porte pelo patrimônio contábil em dólar (nunca pelo valor de mercado, que carrega o próprio preço)
    pl_porte = g(f"t.{p.get('item_patrimonio') or 'patrimonio_controladores'}")
    pl_usd = None if pl_porte is None or fx is None or pl_porte <= 0 else pl_porte * fx
    return {"roe": roe, "roe_hist": roe_hist, "roe_hist_sigma": rhist["sigma"],
            "roe_hist_prejuizo": rhist["prejuizo"], "roe_hist_n": rhist["n"], "margem": margem, "margem_hist": margem_hist,
            "margem_sd": margem_sd, "g": gr, "g_eps": g_eps, "payout": payout, "pb": pb, "pe": pe,
            "ev_receita": ev_rec, "alavancagem": alav, "d_e": g("d_e_mercado"), "roic_pre": roic_pre,
            "beta_reg": g("beta_regressao"), "ln_mcap_usd": None if mcap_usd is None else float(np.log(mcap_usd)),
            "ln_pl_usd": None if pl_usd is None else float(np.log(pl_usd))}


def huber(x: np.ndarray, y: np.ndarray, c: float = 1.345, it: int = 50) -> tuple[np.ndarray, float]:
    """Regressão robusta de Huber por IRLS (escala MAD); devolve coeficientes e R² ponderado."""
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    w = np.ones(len(y))
    for _ in range(it):
        res = y - x @ beta
        s = np.median(np.abs(res - np.median(res))) / 0.6745
        if not np.isfinite(s) or s <= 1e-12:
            break
        u = np.abs(res / s)
        w = np.where(u <= c, 1.0, c / u)
        sw = np.sqrt(w)
        novo = np.linalg.lstsq(x * sw[:, None], y * sw, rcond=None)[0]
        if np.allclose(novo, beta, rtol=1e-10, atol=1e-12):
            beta = novo
            break
        beta = novo
    res = y - x @ beta
    ybar = np.average(y, weights=w)
    r2 = 1 - float(np.sum(w * res ** 2) / max(np.sum(w * (y - ybar) ** 2), 1e-18))
    return beta, r2


def _regressao(nome: str, linhas: list[dict[str, Any]], alvo: str, regs: list[str],
               lim: tuple[float, float], min_obs: int, c: float, r2_min: float = 0.0,
               faixa_pct: tuple[float, float] = (5.0, 95.0)) -> dict[str, Any] | None:
    obs = [r for r in linhas if r.get(alvo) is not None and lim[0] <= r[alvo] <= lim[1]
           and all(r.get(k) is not None for k in regs)]
    if len(obs) < min_obs:
        return {"nome": nome, "n": len(obs), "disponivel": False,
                "motivo": f"menos de {min_obs} observações completas"}
    contagem: dict[str, int] = {}
    for r in obs:
        contagem[r["pais"]] = contagem.get(r["pais"], 0) + 1
    paises = sorted(p for p, n in contagem.items() if n >= 2)
    base = paises[0] if paises else None
    efeitos = [p for p in paises if p != base]
    cols = ["const", *regs, *[f"pais_{p}" for p in efeitos]]
    x = np.array([[1.0, *[float(r[k]) for k in regs], *[1.0 if r["pais"] == p else 0.0 for p in efeitos]]
                  for r in obs])
    y = np.array([float(r[alvo]) for r in obs])
    beta, r2 = huber(x, y, c)
    p_lo, p_hi = (float(v) for v in np.percentile(y, list(faixa_pct)))
    out = {"nome": nome, "n": len(obs), "disponivel": True, "colunas": cols,
           "coef": [r6(b) for b in beta], "r2": r6(r2), "pais_base": base, "efeitos": efeitos,
           "regressores": regs, "alvo": alvo, "limites": list(lim),
           "faixa_amostra": [r6(p_lo), r6(p_hi)], "faixa_percentis": list(faixa_pct)}
    if r2 < r2_min:
        out.update({"disponivel": False,
                    "motivo": f"R² de {r2:.2f} abaixo do mínimo de {r2_min:.2f}".replace(".", ",")})
    return out


def prever_bruto(reg: Mapping[str, Any] | None, f: Mapping[str, Any], pais: str) -> float | None:
    """Múltiplo da regressão para os fundamentos ``f`` antes do limite à faixa da amostra."""
    if not reg or not reg.get("disponivel"):
        return None
    vals = [f.get(k) for k in reg["regressores"]]
    if any(v is None for v in vals):
        return None
    x = [1.0, *[float(v) for v in vals], *[1.0 if pais == p else 0.0 for p in reg["efeitos"]]]
    return float(np.dot(x, reg["coef"]))


def prever(reg: Mapping[str, Any] | None, f: Mapping[str, Any], pais: str) -> float | None:
    """Múltiplo justificado pela regressão para os fundamentos ``f`` (``None`` se faltar algo),
    limitado ao P5–P95 dos múltiplos da amostra (``faixa_amostra``); fora dos limites de
    plausibilidade da regressão ⇒ ``None``."""
    m = prever_bruto(reg, f, pais)
    if m is None:
        return None
    fa = reg.get("faixa_amostra")
    if fa:
        m = min(max(m, float(fa[0])), float(fa[1]))
    lo, hi = reg["limites"]
    return m if lo <= m <= hi else None


def termos_previsao(reg: Mapping[str, Any], f: Mapping[str, Any], pais: str) -> list[tuple[str, float, float]]:
    """Parcelas da previsão ``[(regressor, coeficiente, valor do emissor)]``, inclusive
    constante (valor 1) e efeito país (valor 0 ou 1), na ordem das colunas."""
    vals = [1.0, *[float(f[k]) for k in reg["regressores"]],
            *[1.0 if pais == q else 0.0 for q in reg["efeitos"]]]
    return [(str(c), float(b), float(v)) for c, b, v in zip(reg["colunas"], reg["coef"], vals, strict=True)]


def montar_contexto(pacotes: Mapping[str, Mapping[str, Any]], params: ParametrosCobertura,
                    rf_ust: float | None = None, rf_fonte: dict[str, Any] | None = None) -> dict[str, Any]:
    """Contexto transversal da execução (ver docstring do módulo). ``rf_ust``: UST 10 anos da data
    (o mesmo do modelo), usado no custo de capital de cada emissor que ancora as normas de ROE."""
    proj = params.sec("projecao")
    lim_g = tuple(float(x) for x in proj["crescimento_limites"])
    anos_roe = int(proj.get("roe_hist_anos", 5))
    cal = bool(proj.get("calendarizacao", False))
    linhas = []
    for iid in sorted(pacotes):
        p = pacotes[iid]
        f = fundamentos(p, lim_g, anos_roe, cal)  # type: ignore[arg-type]
        cc_ = params.cc
        imp = float(cc_["imposto_marginal"].get(p["pais"], cc_["imposto_marginal"]["LATAM"]))
        rr = None if p["financeira"] else reinvestimento_observado(
            p, imp, int(proj.get("reinvestimento_anos_observados", 3)),
            metodo=proj.get("reinvestimento_metodo"), regime=str(proj.get("reinvestimento_regime", "recente")))
        linhas.append({"iid": iid, "pais": p["pais"], "setor": p["setor"], "arquetipo": p.get("arquetipo"),
                       "financeira": bool(p["financeira"]), **f, "rr_obs": None if rr is None else rr["rr"]})
    setores: dict[str, Any] = {}
    for s in sorted({r["setor"] for r in linhas}):
        sub = [r for r in linhas if r["setor"] == s]
        lucr = [r for r in sub if r["roe"] is not None and r["roe"] > 0]
        setores[s] = {
            "n": len(sub),
            "roe_mediana": r6(_med([r["roe"] for r in lucr])),
            "roe_hist_mediana": r6(_med([r["roe_hist"] for r in sub if r["roe_hist"] is not None and r["roe_hist"] > 0])),
            "roe_hist_n": len([r for r in sub if r["roe_hist"] is not None and r["roe_hist"] > 0]),
            "roe_n": len(lucr),
            "g_mediana": r6(_med([r["g"] for r in sub])),
            "g_sigma": r6(_iqr_sigma([r["g"] for r in sub])),
            "margem_mediana": r6(_med([r["margem"] for r in sub])),
            "payout_mediana": r6(_med([r["payout"] for r in sub])),
            "d_e_mediana": r6(_med([r["d_e"] for r in sub])),
            "roic_pre_mediana": r6(_med([r["roic_pre"] for r in sub if r["roic_pre"] is not None
                                          and 0 < r["roic_pre"] < 1.5])),
            "rr_mediana": r6(_med([r["rr_obs"] for r in sub if r.get("rr_obs") is not None
                                   and -1.0 <= r["rr_obs"] <= 1.5])),
        }
    universo = {
        "n": len(linhas),
        "roe_mediana": r6(_med([r["roe"] for r in linhas if r["roe"] is not None and r["roe"] > 0])),
        "g_mediana": r6(_med([r["g"] for r in linhas])),
        "g_sigma": r6(_iqr_sigma([r["g"] for r in linhas])),
        "payout_mediana": r6(_med([r["payout"] for r in linhas])),
        "d_e_mediana": r6(_med([r["d_e"] for r in linhas])),
        "margem_mediana": r6(_med([r["margem"] for r in linhas])),
        "rr_mediana": r6(_med([r["rr_obs"] for r in linhas if r.get("rr_obs") is not None
                               and -1.0 <= r["rr_obs"] <= 1.5])),
    }
    pais_setor: dict[str, Any] = {}
    for key in sorted({f"{r['pais']}|{r['setor']}" for r in linhas}):
        pa, se = key.split("|", 1)
        sub = [r for r in linhas if r["pais"] == pa and r["setor"] == se]
        lucr = [r["roe"] for r in sub if r["roe"] is not None and r["roe"] > 0]
        pais_setor[key] = {"n": len(sub), "roe_mediana": r6(_med(lucr)) if len(lucr) >= 5 else None,
                           "roe_n": len(lucr)}
    # β das financeiras (mediana dos betas de regressão, sem ajuste)
    fin = [r for r in linhas if r["financeira"] and r["beta_reg"] is not None]

    def _grupo(sub: list[dict[str, Any]]) -> dict[str, Any]:
        return {"beta": r6(_med([r["beta_reg"] for r in sub])), "n": len(sub),
                "emissores": [[r["iid"], r6(r["beta_reg"])] for r in sorted(sub, key=lambda r: r["iid"])]}

    beta_fin: dict[str, Any] = {"universo": _grupo(fin)}
    for key in sorted({f"{r['pais']}|{r['setor']}" for r in fin}):
        pa, se = key.split("|", 1)
        beta_fin[key] = _grupo([r for r in fin if r["pais"] == pa and r["setor"] == se])
    for se in sorted({r["setor"] for r in fin}):
        beta_fin[f"*|{se}"] = _grupo([r for r in fin if r["setor"] == se])
    mp = params.sec("multiplos")
    c = float(mp["huber_c"])
    n_min = int(mp["min_observacoes"])
    r2_min = float(mp.get("r2_min", 0.0))
    pb_lim = tuple(mp["pb_limites"])
    fp = tuple(float(x) for x in mp.get("faixa_percentis", [5, 95]))
    regs = {
        "pb_financeiras": _regressao("P/VPA (financeiras)", [r for r in linhas if r["financeira"]], "pb",
                                     ["roe", "g", "beta_reg", "payout"], pb_lim, n_min, c, r2_min, fp),
        "pb_nao_financeiras": _regressao("P/VPA (não financeiras)", [r for r in linhas if not r["financeira"]],
                                         "pb", ["roe", "g", "beta_reg", "payout"], pb_lim, n_min, c, r2_min, fp),
        "pl": _regressao("P/L à frente", linhas, "pe", ["g", "payout", "beta_reg"],
                         tuple(mp["pl_limites"]), n_min, c, r2_min, fp),
        "ev_receita": _regressao("EV/Receita", [r for r in linhas if not r["financeira"]], "ev_receita",
                                 ["margem", "g", "alavancagem"], tuple(mp["ev_receita_limites"]), n_min, c, r2_min, fp),
    }
    ctx: dict[str, Any] = {"universo": universo, "setores": setores, "pais_setor": pais_setor,
                           "beta_financeiras": beta_fin, "regressoes": regs}
    kes = custos_capital(pacotes, ctx, params, rf_ust, rf_fonte)
    for r in linhas:
        cc = kes.get(r["iid"])
        r["ke"] = None if cc is None else cc.ke
    ctx["normas_roe"] = normas_roe(linhas, params)
    ctx["persistencia_roe_painel"] = persistencia_painel(pacotes, params)
    ctx["porte"] = inclinacao_porte(linhas, params)
    ctx["premio_implicito"] = premio_implicito(pacotes, linhas, kes, params, rf_ust)
    ctx["fundamentos"] = {r["iid"]: {k: r6(v) if isinstance(v, float) else v for k, v in r.items()
                                     if k not in ("iid",)} for r in linhas}
    ctx["calibracao_pais"] = calibrar_nivel_pais(pacotes, ctx, params, rf_ust, rf_fonte)
    return ctx


def _razoes_v_p(pacotes: Mapping[str, Mapping[str, Any]], ctx: Mapping[str, Any], params: ParametrosCobertura,
                rf_ust: float | None, rf_fonte: dict[str, Any] | None, ids_alvo: list[str], grade: np.ndarray
                ) -> tuple[list[str], np.ndarray]:
    """``V0 ÷ P0`` do caso-base de cada emissor de ``ids_alvo`` com preço-alvo (holdings entram com o
    valor da soma das partes, que não depende do ke) para cada deslocamento ``δ`` da grade (em dólar,
    convertido ao ke local pelo diferencial de inflação)."""
    from .modelo import Avaliador, Drivers

    ids, linhas = [], []
    for iid in ids_alvo:
        p = pacotes[iid]
        if p.get("preco") in (None, 0):
            continue
        sp = p.get("soma_partes")
        if isinstance(sp, Mapping) and "visao_casa" in sp:  # a calibração usa o NAV a mercado
            p = {**p, "soma_partes": {k: v for k, v in sp.items() if k != "visao_casa"}}
        try:
            av = Avaliador(p, ctx, params, rf_ust, rf_fonte or {})
            av.preparar_metodos()
            validos = av.metodos_validos()
            if not validos or av.dps12 is None:
                continue
            cc = av.cc
            d_local = ((1 + cc.ke_usd + grade) * (1 + cc.pi_local) / (1 + cc.pi_us) - 1) - cc.ke
            av._estrito = False
            vals = {}
            for m in validos:
                try:
                    vals[m] = np.broadcast_to(np.asarray(av._valor_metodo(m, Drivers(d_ke=d_local)), dtype=float),
                                              grade.shape)
                except (ValueError, ZeroDivisionError):
                    continue
            v0 = av.combinar(vals) if vals else None
        except (KeyError, ValueError, TypeError, ZeroDivisionError):
            continue
        if v0 is None:
            continue
        r = np.asarray(v0, dtype=float) / float(p["preco"])
        if not np.all(np.isfinite(r)):
            continue
        ids.append(iid)
        linhas.append(r)
    return ids, (np.vstack(linhas) if linhas else np.empty((0, len(grade))))


def calibrar_nivel_pais(pacotes: Mapping[str, Mapping[str, Any]], ctx: dict[str, Any], params: ParametrosCobertura,
                        rf_ust: float | None, rf_fonte: dict[str, Any] | None) -> dict[str, Any]:
    """Ajuste de nível do modelo por país: ``δ`` (deslocamento do ke em dólar) que faz a mediana de
    ``V0 ÷ P0`` dos emissores do país com preço-alvo igual a 1 com as premissas da casa, limitado a
    ``±limite``. É o viés de nível dos fluxos do modelo no país (o mercado é tomado como apreçado na
    mediana), não um prêmio de risco. Ponto fixo: a mediana é recalculada com o ``δ`` já aplicado até
    ``|mediana − 1| ≤ tolerancia`` (no máximo ``passadas`` vezes); a norma de longo prazo do ROE não
    depende de ``δ``. Países com menos de ``n_min`` emissores elegíveis (o nível do país não é
    estimável) recebem o ajuste regional — mediana ponderada pelo número de emissores dos ``δ`` dos
    países calibrados (o viés comum dos fluxos da casa) — e ficam fora das medianas de pares de outros
    países (``grupo = "regional"``). Registra a mediana de ``V0 ÷ P0`` sem e com o ajuste."""
    cfg = (params.cc.get("calibracao_pais") or {})
    if not cfg.get("ativo"):
        return {}
    lo, hi, passo = (float(x) for x in cfg["grade"])
    grade = np.round(np.arange(lo, hi + passo / 2, passo), 10)
    i0 = int(np.argmin(np.abs(grade)))
    lim = float(cfg["limite"])
    n_min = int(cfg["n_min"])
    tol = float(cfg.get("tolerancia", 0.001))
    passadas = int(cfg.get("passadas", 8))
    ctx["calibracao_pais"] = {}
    grupos: dict[str, list[str]] = {}
    pequenos: dict[str, tuple[list[str], np.ndarray]] = {}
    estado: dict[str, dict[str, Any]] = {}
    for pa in sorted({str(p["pais"]) for p in pacotes.values()}):
        ids, r = _razoes_v_p(pacotes, ctx, params, rf_ust, rf_fonte,
                             [i for i in sorted(pacotes) if str(pacotes[i]["pais"]) == pa], grade)
        if len(ids) >= n_min:
            grupos[pa] = ids
            med = np.median(r, axis=0)
            estado[pa] = {"delta": 0.0, "bruto": 0.0, "sem": float(med[i0]), "med": float(med[i0]), "curva": med,
                          "passadas": 1, "convergiu": abs(float(med[i0]) - 1) <= tol, "limitado": False}
        elif ids:
            pequenos[pa] = (ids, np.median(r, axis=0))

    def raiz(med: np.ndarray) -> float:
        idx = np.where(np.diff(np.sign(med - 1.0)) != 0)[0]
        if len(idx):
            k = int(idx[0])
            return float(grade[k] + (1.0 - med[k]) * (grade[k + 1] - grade[k]) / (med[k + 1] - med[k]))
        return float(grade[0] if med[0] < 1.0 else grade[-1])

    def publicar() -> dict[str, Any]:
        return {pa: {"delta": r6(e["delta"]), "delta_bruto": r6(e["bruto"]), "limitado": bool(e["limitado"]),
                     "n": len(grupos[pa]), "mediana_v_p": r6(e["med"]), "mediana_v_p_sem_calibracao": r6(e["sem"]),
                     "passadas": e["passadas"], "convergiu": bool(e["convergiu"]), "grupo": pa}
                for pa, e in estado.items()}

    for _ in range(passadas):
        pend = [g for g, e in estado.items() if not e["convergiu"] and not e["limitado"]]
        if not pend:
            break
        for g in pend:
            e = estado[g]
            e["bruto"] = e["delta"] + raiz(e["curva"])
            e["delta"] = min(max(e["bruto"], -lim), lim)
            e["limitado"] = abs(e["bruto"]) > lim + 1e-12
        ctx["calibracao_pais"] = publicar()
        for g in pend:
            e = estado[g]
            med = np.median(_razoes_v_p(pacotes, ctx, params, rf_ust, rf_fonte, grupos[g], grade)[1], axis=0)
            e["curva"], e["med"], e["passadas"] = med, float(med[i0]), e["passadas"] + 1
            e["convergiu"] = abs(e["med"] - 1) <= tol
    out = publicar()
    if estado and pequenos:
        # ajuste regional: mediana ponderada (nº de emissores) dos δ dos países calibrados
        pares = sorted((e["delta"], len(grupos[g])) for g, e in estado.items())
        tot = sum(n for _, n in pares)
        acum, d_reg = 0, pares[-1][0]
        for d, n in pares:
            acum += n
            if acum >= tot / 2:
                d_reg = d
                break
        base_txt = ", ".join(f"{g} {e['delta'] * 100:+.2f} p.p. ({len(grupos[g])})".replace(".", ",")
                             for g, e in sorted(estado.items()))
        for pa, (ids, med) in sorted(pequenos.items()):
            out[pa] = {"delta": r6(d_reg), "delta_bruto": r6(d_reg), "limitado": False, "n": len(ids),
                       "mediana_v_p": r6(float(np.interp(d_reg, grade, med))),
                       "mediana_v_p_sem_calibracao": r6(float(med[i0])), "passadas": 0, "convergiu": False,
                       "grupo": "regional",
                       "paises_txt": (f"menos de {n_min} emissores no país: ajuste regional = mediana ponderada dos "
                                      f"países calibrados ({base_txt}); fora das medianas de pares de outros países")}
    ctx.pop("calibracao_pais", None)
    return out


def custos_capital(pacotes: Mapping[str, Mapping[str, Any]], ctx: Mapping[str, Any], params: ParametrosCobertura,
                   rf_ust: float | None, rf_fonte: dict[str, Any] | None) -> dict[str, Any]:
    """Custo de capital de cada emissor com a mesma função e os mesmos insumos do modelo (D/E dos
    pares quando o próprio falta; β das financeiras pela mediana dos pares)."""
    from .custo_capital import calcular

    minimo = int(params.sec("rating")["pares_min"])
    setores, univ = ctx.get("setores", {}), ctx.get("universo", {})
    out: dict[str, Any] = {}
    for iid in sorted(pacotes):
        pac = dict(pacotes[iid])
        if pac.get("d_e_mercado") is None:
            pac["d_e_pares"] = (setores.get(pac["setor"], {}) or {}).get("d_e_mediana") or univ.get("d_e_mediana")
        bp, nbp, lista = beta_pares(ctx, pac["pais"], pac["setor"], minimo)
        try:
            out[iid] = calcular(pac, params, rf_ust, rf_fonte or {}, bp, nbp, Registro(), lista)
        except (KeyError, ValueError, TypeError, ZeroDivisionError):
            continue
    return out


def normas_roe(linhas: list[dict[str, Any]], params: ParametrosCobertura) -> dict[str, Any]:
    """Spread de longo prazo do ROE sobre o ke (mediana de ``ROE de 5 anos − ke`` dos emissores com
    ROE de 5 anos positivo) por setor × arquétipo, setor, país × setor e universo, com os nomes."""
    pr = params.sec("persistencia_roe")
    excl = set(pr.get("excluir_paises", []) or [])
    ok = [r for r in linhas if r["pais"] not in excl and r.get("roe_hist") is not None and r["roe_hist"] > 0
          and r.get("ke") is not None]

    def grupo(sub: list[dict[str, Any]]) -> dict[str, Any]:
        return {"spread": r6(float(np.median([r["roe_hist"] - r["ke"] for r in sub]))), "n": len(sub),
                "emissores": sorted(r["iid"] for r in sub)}

    out: dict[str, Any] = {"universo": grupo(ok) if ok else None, "setor_arquetipo": {}, "setor": {}, "pais_setor": {}}
    n_arq, n_ps = int(pr["n_min_arquetipo"]), int(pr["n_min_pais_setor"])
    for s in sorted({r["setor"] for r in ok}):
        sub = [r for r in ok if r["setor"] == s]
        out["setor"][s] = grupo(sub)
        for a in sorted({str(r["arquetipo"]) for r in sub}):
            sa = [r for r in sub if str(r["arquetipo"]) == a]
            if len(sa) >= n_arq:
                out["setor_arquetipo"][f"{s}|{a}"] = grupo(sa)
    for k in sorted({f"{r['pais']}|{r['setor']}" for r in ok}):
        pa, se = k.split("|", 1)
        sub = [r for r in ok if r["pais"] == pa and r["setor"] == se]
        if len(sub) >= n_ps:
            out["pais_setor"][k] = grupo(sub)
    return out


def persistencia_painel(pacotes: Mapping[str, Mapping[str, Any]], params: ParametrosCobertura,
                        k_max: int = 4) -> dict[str, Any]:
    """Painel de ROE dos emissores cobertos (histórico anual arquivado nos pacotes do snapshot:
    lucro dos controladores ÷ patrimônio dos controladores do exercício, patrimônio positivo; fora os
    países de ``persistencia_roe.excluir_paises``) e a persistência do desvio ao setor: ``ρ_k`` =
    coeficiente (MQO pela origem) do desvio em ``t + k`` contra o desvio em ``t`` (desvios contra a
    mediana do setor no ano, limitados a ±50 p.p.), ajustado a ``ρ_k = θ + (1 − θ) × ω^k`` por mínimos
    quadrados numa grade (passo 0,01). Diagnóstico refeito a cada execução: é a evidência arquivada
    dos parâmetros de política θ e ω por classe de estabilidade (``persistencia_roe.classes``)."""
    excl = set(params.sec("persistencia_roe").get("excluir_paises", []) or [])
    roe: dict[tuple[str, int], float] = {}
    setor: dict[str, str] = {}
    for iid in sorted(pacotes):
        p = pacotes[iid]
        if p["pais"] in excl:
            continue
        h = p.get("historico") or {}
        luc, pl = h.get("lucro_liquido_controladores") or {}, h.get("patrimonio_controladores") or {}
        for a in sorted(set(luc) & set(pl)):
            if luc[a] is not None and pl[a] and pl[a] > 0:
                roe[(iid, int(a))] = float(luc[a]) / float(pl[a])
                setor[iid] = str(p["setor"])
    if not roe:
        return {"n_emissor_anos": 0}
    grupos: dict[tuple[str, int], list[float]] = {}
    for (iid, a), r in roe.items():
        grupos.setdefault((setor[iid], a), []).append(r)
    med = {k: float(np.median(v)) for k, v in grupos.items() if len(v) >= 3}
    dev = {(iid, a): min(max(r - med[(setor[iid], a)], -0.5), 0.5) for (iid, a), r in roe.items()
           if (setor[iid], a) in med}
    rho: dict[str, Any] = {}
    for k in range(1, k_max + 1):
        pares = [(d, dev[(iid, a + k)]) for (iid, a), d in dev.items() if (iid, a + k) in dev]
        if len(pares) >= 30:
            x = np.array([q[0] for q in pares])
            y = np.array([q[1] for q in pares])
            rho[str(k)] = {"rho": r6(float(np.dot(x, y) / np.dot(x, x))), "n": len(pares)}
    theta = omega = None
    if len(rho) >= 2:
        ks = np.array([int(k) for k in rho])
        rs = np.array([float(v["rho"]) for v in rho.values()])
        grade = np.round(np.arange(0.0, 1.0001, 0.01), 2)
        melhor = None
        for t in grade:
            for w in grade[:-1]:
                e = float(np.sum((rs - (t + (1 - t) * w ** ks)) ** 2))
                if melhor is None or e < melhor[0] - 1e-15:
                    melhor = (e, float(t), float(w))
        theta, omega = melhor[1], melhor[2]
    anos = sorted({a for _, a in dev})
    return {"n_emissor_anos": len(dev), "n_emissores": len({i for i, _ in dev}), "anos": [anos[0], anos[-1]] if anos else None,
            "rho": rho, "theta": theta, "omega": omega,
            "nota": "desvios ao setor no ano; ρ_k pelo MQO pela origem; θ e ω na grade de 0,01"}


def inclinacao_porte(linhas: list[dict[str, Any]], params: ParametrosCobertura) -> dict[str, Any]:
    """Inclinação de Theil–Sen do ROE de 5 anos contra o log do patrimônio contábil em dólar (porte
    contábil, nunca o valor de mercado: P/VPA e ROE são correlacionados mecanicamente e o preço do
    próprio emissor voltaria à sua norma), ambos como desvio da mediana do setor (todos os emissores
    com ROE de 5 anos, inclusive os com prejuízo). Estimada a cada execução; só é aplicada quando o
    intervalo de 95% da inclinação exclui zero (senão ``b = 0``, "não significativa") e fica limitada à
    faixa da configuração. Também a mediana do log do patrimônio de cada setor."""
    pr = params.sec("persistencia_roe")
    excl = set(pr.get("excluir_paises", []) or [])
    var = str(pr.get("tamanho_variavel", "ln_pl_usd"))
    med_lm: dict[str, float] = {}
    for s in sorted({r["setor"] for r in linhas}):
        v = [r[var] for r in linhas if r["setor"] == s and r.get(var) is not None]
        if v:
            med_lm[s] = float(np.median(v))
    ok = [r for r in linhas if r["pais"] not in excl and r.get("roe_hist") is not None
          and r.get(var) is not None and r["setor"] in med_lm]
    med_roe = {s: float(np.median([r["roe_hist"] for r in ok if r["setor"] == s])) for s in {r["setor"] for r in ok}}
    x = np.array([r[var] - med_lm[r["setor"]] for r in ok])
    y = np.array([r["roe_hist"] - med_roe[r["setor"]] for r in ok])
    lo, hi = (float(v) for v in pr["tamanho_inclinacao_limites"])
    b_bruto = ic = None
    significativa = False
    if len(ok) >= int(pr["tamanho_n_min"]) and np.ptp(x) > 0:
        ts = theilslopes(y, x, alpha=0.95)
        b_bruto, ic = float(ts[0]), [float(ts[2]), float(ts[3])]
        significativa = bool(ic[0] > 0 or ic[1] < 0)
    b = 0.0 if b_bruto is None or not significativa else min(max(b_bruto, lo), hi)
    return {"b": r6(b), "b_bruto": r6(b_bruto), "ic95": None if ic is None else [r6(v) for v in ic],
            "significativa": significativa, "n": len(ok), "limites": [lo, hi], "variavel": var,
            "mediana_ln_porte_setor": {s: r6(v) for s, v in sorted(med_lm.items())}}


MOEDA_LOCAL_PAIS = {"BR": "BRL", "MX": "MXN", "CL": "CLP", "CO": "COP", "PE": "PEN"}


def _tir_dois_estagios(p: float, e: list[float], k0: float, roe: float, g: float) -> float | None:
    """Taxa que iguala o preço agregado ao valor presente dos dividendos: lucros ``e`` dos anos
    1–n, payout de ``k0`` convergindo linearmente a ``1 − g ÷ ROE`` no ano n e perpetuidade a ``g``."""
    n = len(e)
    ks = 1 - g / roe

    def f(r: float) -> float:
        v = sum(e[t - 1] * (k0 + (ks - k0) * (t - 1) / (n - 1)) / (1 + r) ** t for t in range(1, n + 1))
        return v + e[-1] * (1 + g) * ks / ((r - g) * (1 + r) ** n) - p

    lo, hi = g + 0.002, 0.60
    flo, fhi = f(lo), f(hi)
    if not (np.isfinite(flo) and np.isfinite(fhi)) or flo * fhi > 0:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


def premio_implicito(pacotes: Mapping[str, Mapping[str, Any]], linhas: list[dict[str, Any]],
                     kes: Mapping[str, Any], params: ParametrosCobertura, rf_ust: float | None) -> dict[str, Any]:
    """Prêmio total implícito pelo mercado por país (Damodaran, agregado): preço agregado dos
    emissores cobertos na moeda local (sem holdings, com insumos coerentes, recompras e proventos
    publicados — ausente é desconhecido, nunca zero — e exercício publicado) contra o LPA de consenso
    calendarizado dos anos 1–2 (``projecao.calendarizacao``), crescimento linear até ``g = rf local`` no
    ano 5, payout em caixa (dividendos + recompras ÷ lucro de 12 meses) convergindo ao sustentável
    ``1 − g ÷ ROE``; país só com ``premio_implicito_pais.n_min`` emissores. Prêmio
    em dólar = ``(1 + r)(1 + π_EUA)/(1 + π_local) − 1 − rf``; prêmio do motor = média ponderada pelo
    valor de mercado de ``β × ERP + λ × CRP``."""
    from .custo_capital import erp_oficial, fisher

    cc = params.cc
    pip = cc.get("premio_implicito_pais") or {}
    n_anos = int(pip.get("anos", 5))
    n_min = int(pip.get("n_min", 8))
    cal = bool(params.sec("projecao").get("calendarizacao", False))
    rf = (rf_ust if rf_ust is not None else float(cc["rf_usd_reserva"])) - float(cc["spread_default_eua"])
    infl = cc["inflacao_lp"]
    pi_us = float(infl["USD"])
    erp, _ = erp_oficial(cc)
    lim_q = params.sec("qualidade")
    pb_lo, pb_hi = lim_q.get("pb_plausivel", [0.1, 15.0])
    out: dict[str, Any] = {}
    for pais, moe in MOEDA_LOCAL_PAIS.items():
        agg = []
        for iid in sorted(pacotes):
            p = pacotes[iid]
            if p["pais"] != pais or p["moeda"] != moe or p.get("arquetipo") == "holding" or iid not in kes:
                continue
            if p.get("status_moeda") not in ("ok", "fx_corrigido") or (p.get("contagem") or {}).get("status") == "bloqueio":
                continue
            e1, e2, et, b, pr, u = (p.get(k) for k in ("eps_fy1", "eps_fy2", "eps_ttm", "bvps", "preco", "unidades"))
            if None in (e1, e2, et, b, pr, u) or b <= 0 or e1 <= 0 or e2 <= 0 or et <= 0:
                continue
            if not (pb_lo <= pr / b <= pb_hi) or e1 / b > 1.0 or not 0.2 <= e1 / et <= 5.0:
                continue
            rec = p.get("t.recompras")
            if rec is None:  # recompra não publicada: desconhecida, nunca zero ⇒ fora do agregado
                continue
            f_ex = fracao_exercicio(p) if cal else 0.0
            if f_ex is None:  # sem exercício publicado: calendarização indefinida ⇒ fora do agregado
                continue
            g_i = kes[iid].g
            g12 = min(max(e2 / e1 - 1, -0.2), 0.3)
            e3 = e2 * (1 + 0.5 * g12 + 0.5 * g_i)
            n1 = (1 - f_ex) * e1 + f_ex * e2
            n2 = (1 - f_ex) * e2 + f_ex * e3
            dps = p.get("dps_12m")
            if dps is None:
                continue
            dist = float(dps) * u + abs(float(rec))
            k = kes[iid]
            agg.append((pr * u, n1 * u, n2 * u, et * u, b * u, dist, k.beta * erp + k.lam * k.crp))
        if len(agg) < n_min:
            continue
        a = np.array(agg)
        P, E1, E2, Et, B, D = (float(a[:, j].sum()) for j in range(6))
        k0 = min(max(D / Et, 0.0), 1.0)
        roe = E1 / B
        pi_l = float(infl.get(moe, pi_us))
        g_l = fisher(rf, pi_l, pi_us)
        if roe <= g_l:
            continue
        g12 = E2 / E1 - 1
        es = [E1, E2]
        for t_ in range(3, n_anos + 1):
            es.append(es[-1] * (1 + g12 + (g_l - g12) * (t_ - 2) / (n_anos - 2)))
        r = _tir_dois_estagios(P, es, k0, roe, g_l)
        if r is None:
            continue
        pm = float((a[:, 0] * a[:, 6]).sum() / P)
        pimp = (1 + r) * (1 + pi_us) / (1 + pi_l) - 1 - rf
        out[pais] = {"n": len(agg), "r_local": r6(r), "premio_implicito": r6(pimp), "premio_motor": r6(pm),
                     "gap": r6(pimp - pm), "payout_caixa": r6(k0), "roe_agregado": r6(roe), "g": r6(g_l),
                     "pl_agregado": r6(P / E1), "pvpa_agregado": r6(P / B)}
    return out


def alvo_roe(ctx: Mapping[str, Any], params: ParametrosCobertura, iid: str, pais: str, setor: str,
             arquetipo: str, ke: float, roe2: float | None) -> dict[str, Any] | None:
    """ROE de convergência (persistência por classe de estabilidade; ver ``persistencia_roe``).

    ``norma = ke + spread de referência + ajuste de porte``; ``R̄ = média(ROE de 5 anos, ROE_2)``
    limitado a [norma − 5 p.p.; norma + 15 p.p.]; ``alvo = norma + θ × (R̄ − norma)``; ω (fator do
    decaimento exponencial do caminho) pela mesma classe. Devolve todos os componentes (para os
    passos do modelo aberto) ou ``None`` sem norma."""
    pr = params.sec("persistencia_roe")
    nr = ctx.get("normas_roe") or {}
    comp: dict[str, Any] = {}
    sa = (nr.get("setor_arquetipo") or {}).get(f"{setor}|{arquetipo}")
    if sa:
        s_ref = float(sa["spread"])
        comp["referencia"] = {"tipo": "setor_arquetipo", "rotulo": f"{setor} × {arquetipo}", "spread": s_ref,
                              "n": sa["n"]}
    else:
        se = (nr.get("setor") or {}).get(setor) or nr.get("universo")
        if not se:
            return None
        s_ref = float(se["spread"])
        rot = setor if (nr.get("setor") or {}).get(setor) else "universo"
        comp["referencia"] = {"tipo": "setor", "rotulo": rot, "spread": s_ref, "n": se["n"]}
        ps = (nr.get("pais_setor") or {}).get(f"{pais}|{setor}")
        if ps:
            w = float(pr["encolhimento_pais_setor"])
            comp["pais_setor"] = {"rotulo": f"{pais} × {setor}", "spread": float(ps["spread"]), "n": ps["n"], "peso": w}
            s_ref = (1 - w) * s_ref + w * float(ps["spread"])
    comp["spread"] = s_ref
    f = (ctx.get("fundamentos") or {}).get(iid, {})
    porte = ctx.get("porte") or {}
    b = float(porte.get("b") or 0.0)
    var = str(porte.get("variavel") or "ln_mcap_usd")
    meds = porte.get("mediana_ln_porte_setor") or porte.get("mediana_ln_mcap_setor") or {}
    lm, med = f.get(var), meds.get(setor)
    lim_t = float(pr["tamanho_limite"])
    adj = 0.0
    if lm is not None and med is not None and b:
        adj = min(max(b * (float(lm) - float(med)), -lim_t), lim_t)
    comp["porte"] = {"b": b, "delta_ln": None if lm is None or med is None else float(lm) - float(med), "ajuste": adj,
                     "b_bruto": porte.get("b_bruto"), "ic95": porte.get("ic95"),
                     "significativa": porte.get("significativa"), "n": porte.get("n")}
    norma = ke + s_ref + adj
    comp["norma"] = norma
    roe5 = f.get("roe_hist")
    partes = [float(x) for x in (roe5, roe2) if x is not None]
    rbar = float(np.mean(partes)) if partes else None
    sigma, prej, n = f.get("roe_hist_sigma"), int(f.get("roe_hist_prejuizo") or 0), int(f.get("roe_hist_n") or 0)
    cl = pr["classes"]
    if n < int(pr.get("min_anos_historico", 3)) or sigma is None:
        classe, motivo = "instavel", f"histórico de {n} exercício(s), abaixo de {int(pr.get('min_anos_historico', 3))}"
    elif prej > 0:
        classe, motivo = "instavel", f"{prej} exercício(s) com prejuízo nos últimos 5"
    elif sigma > float(cl["instavel"]["sigma_min"]):
        classe, motivo = "instavel", f"desvio-padrão do ROE de 5 anos acima de {float(cl['instavel']['sigma_min']):.0%}"
    elif sigma <= float(cl["estavel"]["sigma_max"]):
        classe, motivo = "estavel", f"desvio-padrão do ROE de 5 anos até {float(cl['estavel']['sigma_max']):.0%}, sem prejuízo"
    else:
        classe, motivo = "normal", "desvio-padrão do ROE de 5 anos intermediário, sem prejuízo"
    theta, omega = float(cl[classe]["theta"]), float(cl[classe]["omega"])
    lo, hi = (float(x) for x in params.sec("projecao")["roe_proprio_faixa"])
    rbar_lim = None if rbar is None else min(max(rbar, norma + lo), norma + hi)
    alvo = norma if rbar_lim is None else norma + theta * (rbar_lim - norma)
    comp.update({"roe5": roe5, "roe2": roe2, "rbar": rbar, "rbar_limitado": rbar_lim, "faixa": [lo, hi],
                 "sigma": sigma, "prejuizo": prej, "n_anos": n, "classe": classe, "classe_motivo": motivo.replace(".", ","),
                 "theta": theta, "omega": omega, "alvo": alvo, "ke": ke})
    return comp


def beta_pares(ctx: Mapping[str, Any], pais: str, setor: str, minimo: int
               ) -> tuple[float | None, int, list[list[Any]]]:
    """β mediano das financeiras pares (país × setor, setor ou universo com ≥ ``minimo`` nomes),
    o número de pares e a lista ``[[emissor, β], ...]`` usada na mediana."""
    bf = ctx.get("beta_financeiras", {})
    for key in (f"{pais}|{setor}", f"*|{setor}", "universo"):
        e = bf.get(key)
        if e and e.get("beta") is not None and int(e.get("n", 0)) >= minimo:
            return float(e["beta"]), int(e["n"]), list(e.get("emissores") or [])
    return None, 0, []


__all__ = ["LIMITES_G", "MOEDA_LOCAL_PAIS", "alvo_roe", "calibrar_nivel_pais", "beta_pares", "custos_capital", "fracao_exercicio",
           "fundamentos", "huber", "inclinacao_porte", "montar_contexto", "normas_roe", "premio_implicito",
           "prever", "prever_bruto", "reinvestimento_observado", "roe_historico", "termos_previsao"]
