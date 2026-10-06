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
  EV/Receita (nunca é tratada como zero).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from .formato import r6
from .parametros import ParametrosCobertura


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


def fundamentos(p: Mapping[str, Any], lim_g: tuple[float, float] = LIMITES_G) -> dict[str, float | None]:
    """Razões correntes do emissor a partir do pacote (moeda do modelo; nosso preço)."""
    def g(k: str) -> float | None:
        v = p.get(k)
        return None if v is None else float(v)

    preco, bvps, eps1, eps2, eps_ttm = g("preco"), g("bvps"), g("eps_fy1"), g("eps_fy2"), g("eps_ttm")
    dps = g("dps_12m")
    rec, ebit = g("t.receita"), g("t.ebit")
    hist = p.get("historico") or {}
    roe = None
    if eps_ttm is not None and bvps is not None and bvps > 0:
        roe = eps_ttm / bvps
    elif eps1 is not None and bvps is not None and bvps > 0:
        roe = eps1 / bvps
    roe_hist = None
    luc, pl = hist.get("lucro_liquido_controladores", {}), hist.get("patrimonio_controladores", {})
    anos = sorted(set(luc) & set(pl))
    rs = [luc[a] / pl[a] for a in anos if pl[a] and pl[a] > 0]
    if len(rs) >= 3:
        roe_hist = float(np.median(rs))
    margem = None if rec is None or ebit is None or rec <= 0 else ebit / rec
    rh, eh = hist.get("receita", {}), hist.get("ebit", {})
    ms = [eh[a] / rh[a] for a in sorted(set(rh) & set(eh)) if rh[a] and rh[a] > 0]
    margem_hist = float(np.median(ms)) if len(ms) >= 3 else None
    margem_sd = float(np.std(ms, ddof=1)) if len(ms) >= 3 else None
    g_eps = None if eps1 is None or eps2 is None or eps1 <= 0 else eps2 / eps1 - 1
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
    return {"roe": roe, "roe_hist": roe_hist, "margem": margem, "margem_hist": margem_hist,
            "margem_sd": margem_sd, "g": gr, "g_eps": g_eps, "payout": payout, "pb": pb, "pe": pe,
            "ev_receita": ev_rec, "alavancagem": alav, "d_e": g("d_e_mercado"), "roic_pre": roic_pre,
            "beta_reg": g("beta_regressao")}


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
               lim: tuple[float, float], min_obs: int, c: float, r2_min: float = 0.0) -> dict[str, Any] | None:
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
    out = {"nome": nome, "n": len(obs), "disponivel": True, "colunas": cols,
           "coef": [r6(b) for b in beta], "r2": r6(r2), "pais_base": base, "efeitos": efeitos,
           "regressores": regs, "alvo": alvo, "limites": list(lim)}
    if r2 < r2_min:
        out.update({"disponivel": False,
                    "motivo": f"R² de {r2:.2f} abaixo do mínimo de {r2_min:.2f}".replace(".", ",")})
    return out


def prever(reg: Mapping[str, Any] | None, f: Mapping[str, Any], pais: str) -> float | None:
    """Múltiplo justificado pela regressão para os fundamentos ``f`` (``None`` se faltar algo)."""
    if not reg or not reg.get("disponivel"):
        return None
    vals = [f.get(k) for k in reg["regressores"]]
    if any(v is None for v in vals):
        return None
    x = [1.0, *[float(v) for v in vals], *[1.0 if pais == p else 0.0 for p in reg["efeitos"]]]
    m = float(np.dot(x, reg["coef"]))
    lo, hi = reg["limites"]
    return m if lo <= m <= hi else None


def termos_previsao(reg: Mapping[str, Any], f: Mapping[str, Any], pais: str) -> list[tuple[str, float, float]]:
    """Parcelas da previsão ``[(regressor, coeficiente, valor do emissor)]``, inclusive
    constante (valor 1) e efeito país (valor 0 ou 1), na ordem das colunas."""
    vals = [1.0, *[float(f[k]) for k in reg["regressores"]],
            *[1.0 if pais == q else 0.0 for q in reg["efeitos"]]]
    return [(str(c), float(b), float(v)) for c, b, v in zip(reg["colunas"], reg["coef"], vals, strict=True)]


def montar_contexto(pacotes: Mapping[str, Mapping[str, Any]], params: ParametrosCobertura) -> dict[str, Any]:
    lim_g = tuple(float(x) for x in params.sec("projecao")["crescimento_limites"])
    linhas = []
    for iid in sorted(pacotes):
        p = pacotes[iid]
        f = fundamentos(p, lim_g)  # type: ignore[arg-type]
        linhas.append({"iid": iid, "pais": p["pais"], "setor": p["setor"],
                       "financeira": bool(p["financeira"]), **f})
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
        }
    universo = {
        "n": len(linhas),
        "roe_mediana": r6(_med([r["roe"] for r in linhas if r["roe"] is not None and r["roe"] > 0])),
        "g_mediana": r6(_med([r["g"] for r in linhas])),
        "g_sigma": r6(_iqr_sigma([r["g"] for r in linhas])),
        "payout_mediana": r6(_med([r["payout"] for r in linhas])),
        "d_e_mediana": r6(_med([r["d_e"] for r in linhas])),
        "margem_mediana": r6(_med([r["margem"] for r in linhas])),
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
    regs = {
        "pb_financeiras": _regressao("P/VPA (financeiras)", [r for r in linhas if r["financeira"]], "pb",
                                     ["roe", "g", "beta_reg", "payout"], pb_lim, n_min, c, r2_min),
        "pb_nao_financeiras": _regressao("P/VPA (não financeiras)", [r for r in linhas if not r["financeira"]],
                                         "pb", ["roe", "g", "beta_reg", "payout"], pb_lim, n_min, c, r2_min),
        "pl": _regressao("P/L à frente", linhas, "pe", ["g", "payout", "beta_reg"],
                         tuple(mp["pl_limites"]), n_min, c, r2_min),
        "ev_receita": _regressao("EV/Receita", [r for r in linhas if not r["financeira"]], "ev_receita",
                                 ["margem", "g", "alavancagem"], tuple(mp["ev_receita_limites"]), n_min, c, r2_min),
    }
    fund = {r["iid"]: {k: r6(v) if isinstance(v, float) else v for k, v in r.items()
                       if k not in ("iid",)} for r in linhas}
    return {"universo": universo, "setores": setores, "pais_setor": pais_setor, "beta_financeiras": beta_fin,
            "regressoes": regs, "fundamentos": fund}


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


def roe_alvo(ctx: Mapping[str, Any], pais: str, setor: str, roe_hist: float | None
             ) -> tuple[float | None, str, list[tuple[str, float, int | None]]]:
    """ROE de convergência (fim do horizonte explícito): mediana histórica setorial dos emissores
    lucrativos, encolhida 50% para a mediana corrente de país × setor (≥ 5 nomes) e, quando há
    ≥ 3 exercícios do próprio emissor, média com o ROE histórico próprio.

    Devolve ``(valor, descrição, componentes)``; componentes = ``[(rótulo, valor, n)]`` na ordem
    da conta (setor; país × setor; próprio)."""
    s = ctx.get("setores", {}).get(setor, {})
    comps: list[tuple[str, float, int | None]] = []
    if s.get("roe_hist_mediana") is not None:
        base, txt = float(s["roe_hist_mediana"]), "mediana do ROE histórico dos emissores lucrativos do setor"
        comps.append(("mediana histórica do setor", base, s.get("roe_hist_n")))
    elif s.get("roe_mediana") is not None:
        base, txt = float(s["roe_mediana"]), "mediana do ROE corrente dos emissores lucrativos do setor"
        comps.append(("mediana corrente do setor", base, s.get("roe_n")))
    else:
        return None, "sem ROE setorial", []
    ps = ctx.get("pais_setor", {}).get(f"{pais}|{setor}", {})
    if ps.get("roe_mediana") is not None:
        comps.append((f"mediana de {pais} × {setor}", float(ps["roe_mediana"]), ps.get("roe_n")))
        base = 0.5 * base + 0.5 * float(ps["roe_mediana"])
        txt += " encolhida 50% para a mediana de país × setor"
    if roe_hist is not None and roe_hist > 0:
        comps.append(("ROE histórico do emissor", float(roe_hist), None))
        base = 0.5 * base + 0.5 * roe_hist
        txt += ", média com o ROE histórico do emissor"
    return float(base), txt, comps


__all__ = ["LIMITES_G", "beta_pares", "fundamentos", "huber", "montar_contexto", "prever", "roe_alvo",
           "termos_previsao"]
