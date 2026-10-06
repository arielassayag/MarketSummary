"""Risco idiossincrático: decomposição da decisão e série monitorada (dono: workstream E;
consumidores: C no portal e D no relatório semanal).

Definição: ``S_idio = wᵀDw / (κ_F·wᵀBFBᵀw + wᵀDw)`` na carteira ATINGIDA, com a covariância
conservadora (mercado, país, setor, estilo e, quando configurado, o bloco macro) e a inflação de
2ª ordem κ_F (:func:`kappa_f`). Meta ``risk.idio_share_goal`` (SOFT) e piso
``risk.idio_share_floor`` (HARD, nunca relaxado), medidos em cada modelo de
``risk.idio_gate_models`` (decisão, com as janelas de evento; base, sem elas).

Gravação sem mudar contratos com hash: a decisão guarda ``Proposal.overrides["risco"]`` com
``idio_decisao``, ``idio_base``, ``kappa_f``, ``por_grupo`` e ``por_grupo_base`` (chaves
:data:`GRUPOS_IDIO`, frações da variância que somam 1, nos modelos de decisão e base),
``modelo_vinculante`` (o de menor fatia idiossincrática), ``custo_neutralidade_bp`` e
``vinculantes`` — floats puros com 6 algarismos significativos.

Monitoramento (:func:`serie_idio`): ex-ante diário (``DailyRisk.factor_vol``/``specific_vol``),
realizado em 63 pregões (x-sigma-rho ``cov(r_S, r_p)/var(r_p)`` a partir do P&L específico
diário) e sem modelo (``1 − R²`` AJUSTADO pelos graus de liberdade, dos retornos diários do fundo
contra ETFs e commodities). Com 11 regressores e no máximo 63 observações, o ``1 − R²`` bruto de
um fundo 100% idiossincrático fica perto de ``1 − k/(n − 1)`` (≈ 82% com n = 63): o ajuste
``(1 − R²)·(n − 1)/(n − k − 1)`` remove esse viés, a medida só é publicada com pelo menos
:data:`MIN_GL_SEM_MODELO` graus de liberdade no resíduo e vem com a banda de amostragem sob a
hipótese nula (:func:`banda_sem_modelo`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from ..config import FundConfig
    from ..contracts import DailyRecord, Proposal
    from ..market import MarketData
    from .types import RiskModel

#: Chave de ``Proposal.overrides`` com a decomposição de risco da decisão.
CHAVE_RISCO = "risco"
#: Grupos da decomposição da variância ex-ante (``por_grupo``).
GRUPOS_IDIO = ("mercado", "pais", "setor", "estilo", "macro", "especifico")
_GRUPO_DO_FATOR = {"market": "mercado", "country": "pais", "sector": "setor", "style": "estilo",
                   "macro": "macro"}
#: Regressores do teste sem modelo (ETFs LatAm e commodities/dólar).
REGRESSORES_SEM_MODELO = ("ILF", "EWZ", "EWW", "ECH", "EPU", "COLO", "ARGT", "BZ=F", "HG=F",
                          "GC=F", "DX-Y.NYB")
JANELA_REALIZADA = 63
MIN_OBS_REALIZADA = 21
#: Graus de liberdade mínimos do resíduo (n − k − 1) para publicar a medida sem modelo.
MIN_GL_SEM_MODELO = 30
#: Quantil unilateral de 95% da normal: abaixo do piso só conta fora da banda de amostragem.
Z_BANDA_SEM_MODELO = 1.645
KURTOSIS_CLIP = (3.0, 8.0)
SIG_DIGITS = 6


def _sig(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return 0.0 if v == 0 else float(f"{v:.{SIG_DIGITS - 1}e}")


# ----------------------------------------------------------------------------- κ_F


def ewma_kurtosis(x: pd.Series, halflife: float) -> float:
    """Curtose bruta (``m4/m2²``, normal = 3) com pesos EWMA de meia-vida ``halflife``;
    ``NaN`` com menos de 20 observações."""
    v = pd.to_numeric(x, errors="coerce").dropna().to_numpy(dtype=float)
    if len(v) < 20:
        return float("nan")
    wts = 0.5 ** ((len(v) - 1 - np.arange(len(v))) / float(halflife))
    wts = wts / wts.sum()
    mu = float(wts @ v)
    d = v - mu
    m2 = float(wts @ d ** 2)
    m4 = float(wts @ d ** 4)
    return m4 / (m2 * m2) if m2 > 0 else float("nan")


def kappa_formula(n_factors: int, halflife_corr: float, nw_lags: int, kurtosis: float
                  ) -> tuple[float, float]:
    """``(κ, T_ef)`` com ``T_ef = (2·HL/ln 2)·3/(2(L+1))·2/(k−1)`` e ``κ = (1 − K/T_ef)⁻²``
    (Shepard, 2009; heurística conservadora para carteiras com restrições). ``κ = NaN`` quando
    ``K ≥ T_ef``."""
    t_eff = (2.0 * halflife_corr / math.log(2.0)) * (3.0 / (2.0 * (nw_lags + 1))) \
        * (2.0 / (kurtosis - 1.0))
    if not (math.isfinite(t_eff) and t_eff > n_factors):
        return float("nan"), t_eff
    return (1.0 - n_factors / t_eff) ** -2, t_eff


def kappa_f(model: RiskModel, cfg: FundConfig) -> tuple[float, dict[str, Any]]:
    """Inflação de 2ª ordem da covariância fatorial e a origem do número.

    ``risk.second_order_inflation_mode = "config"``: o valor de ``risk.second_order_inflation``
    (o mandato fixa o número; ex.: 1,45, razão realizada/prevista medida em carteiras otimizadas).
    ``"analytic"``: :func:`kappa_formula` com K = fatores com retorno na última data, curtose =
    mediana entre fatores da curtose EWMA (meia-vida de correlação) limitada a [3, 8], limitada
    por ``second_order_inflation_bounds``; resultado não finito ⇒ valor de configuração
    (``fonte = "fallback"``)."""
    rk = cfg.risk
    base = float(rk.second_order_inflation)
    if rk.second_order_inflation_mode != "analytic":
        return base, {"valor": base, "fonte": "config"}
    rm = cfg.risk_model
    fr = model.factor_returns
    lo, hi = rk.second_order_inflation_bounds
    info: dict[str, Any] = {"fonte": "fallback"}
    if fr is None or fr.empty:
        info["valor"] = base
        return base, info
    last = fr.iloc[-1]
    k_fac = int(last.notna().sum())
    kurt = [ewma_kurtosis(fr[c], rm.halflife_factor_corr) for c in fr.columns]
    kurt = [k for k in kurt if math.isfinite(k)]
    if not kurt or k_fac == 0:
        info["valor"] = base
        return base, info
    k_med = float(np.median(kurt))
    k_use = min(max(k_med, KURTOSIS_CLIP[0]), KURTOSIS_CLIP[1])
    kap, t_eff = kappa_formula(k_fac, rm.halflife_factor_corr, rm.newey_west_lags, k_use)
    info.update({"t_ef": t_eff, "k": k_fac, "curtose_mediana": k_med})
    if not math.isfinite(kap):
        info["valor"] = base
        return base, info
    val = min(max(kap, lo), hi)
    info.update({"valor": val, "fonte": "analitico"})
    return val, info


# ----------------------------------------------------------------------------- medidas


def fatia_idio(w: pd.Series, model: RiskModel, kappa: float = 1.0) -> dict[str, float]:
    """Fatia idiossincrática da variância ex-ante (κ_F aplicado só ao bloco fatorial) e vols.

    Carteira vazia ⇒ fatia ``NaN`` (indefinida, nunca 100%)."""
    from ..portfolio.optimizer import portfolio_risk_parts

    parts = portfolio_risk_parts(w[w != 0], model)
    fvar = max(kappa, 1.0) * parts.factor_var
    svar = parts.specific_var
    tot = fvar + svar
    return {"idio": svar / tot if tot > 0 else float("nan"),
            "vol": math.sqrt(max(parts.total_var, 0.0)),
            "vol_fatorial": math.sqrt(max(parts.factor_var, 0.0)),
            "vol_especifica": math.sqrt(max(svar, 0.0))}


def por_grupo(w: pd.Series, model: RiskModel, kappa: float = 1.0) -> dict[str, float | None]:
    """Participação de Euler da variância por grupo (:data:`GRUPOS_IDIO`), com κ_F no bloco
    fatorial; soma 1. Grupo sem fatores no modelo ⇒ 0 (ausência de fator, não de dado);
    carteira vazia ⇒ ``None`` em todos."""
    wa = model.align(w[w != 0])
    B = model.exposures
    F = model.factor_cov.loc[B.columns, B.columns]
    x = B.T @ wa
    fx = F @ x
    contrib = x * fx  # soma = wᵀBFBᵀw
    spec = float((wa ** 2 * model.specific_var.reindex(wa.index)).sum())
    k = max(kappa, 1.0)
    total = k * float(contrib.sum()) + spec
    if not total > 0:
        return {g: None for g in GRUPOS_IDIO}
    out = {g: 0.0 for g in GRUPOS_IDIO}
    for f, c in contrib.items():
        g = _GRUPO_DO_FATOR.get(model.factor_groups.get(str(f), ""), "estilo")
        out[g] += k * float(c) / total
    out["especifico"] = spec / total
    return out


def risco_da_decisao(w: pd.Series, model: RiskModel, model_base: RiskModel | None,
                     cfg: FundConfig, *, kappa: float, kappa_info: dict[str, Any],
                     binding: Sequence[str] = (), custo_neutralidade_bp: float | None = None,
                     ) -> dict[str, Any]:
    """Bloco ``overrides["risco"]`` da proposta (floats puros, 6 algarismos significativos)."""
    w = w[w != 0]
    out: dict[str, Any] = {
        "kappa_f": {k: (_sig(v) if isinstance(v, (int, float)) else v)
                    for k, v in kappa_info.items()},
        "meta_idio": _sig(cfg.risk.idio_share_goal),
        "piso_idio": _sig(cfg.risk.idio_share_floor),
        "modelos_gate": list(cfg.risk.idio_gate_models),
    }
    if w.empty:
        out.update({"idio_decisao": None, "idio_base": None,
                    "por_grupo": {g: None for g in GRUPOS_IDIO}})
    else:
        dec = fatia_idio(w, model, kappa)
        out["idio_decisao"] = _sig(dec["idio"])
        out["vol_ex_ante"] = _sig(dec["vol"])
        out["vol_fatorial"] = _sig(dec["vol_fatorial"])
        out["vol_especifica"] = _sig(dec["vol_especifica"])
        out["idio_base"] = (_sig(fatia_idio(w, model_base, kappa)["idio"])
                            if model_base is not None else None)
        out["por_grupo"] = {g: _sig(v) for g, v in por_grupo(w, model, kappa).items()}
        if model_base is not None:
            out["por_grupo_base"] = {g: _sig(v)
                                     for g, v in por_grupo(w, model_base, kappa).items()}
    out["modelo_vinculante"] = modelo_vinculante(out)
    out["custo_neutralidade_bp"] = _sig(custo_neutralidade_bp)
    out["vinculantes"] = [b for b in binding
                          if not b.startswith(("max_long:", "max_short:", "max_trade"))]
    return out


def modelo_vinculante(risco: dict[str, Any]) -> str | None:
    """Modelo do gate com a MENOR fatia idiossincrática (o que vincula a meta e o piso):
    ``"decisao"`` ou ``"base"``; ``None`` sem medida."""
    vals = {k: risco.get(f"idio_{k}") for k in ("decisao", "base")}
    ok = {k: float(v) for k, v in vals.items()
          if isinstance(v, (int, float)) and math.isfinite(float(v))}
    if not ok:
        return None
    return min(ok, key=lambda k: (ok[k], k != "decisao"))


def base_vinculante(risco: dict[str, Any] | None) -> dict[str, Any] | None:
    """Medida idiossincrática publicada, na base κ_F do gate: modelo vinculante, fatia
    específica, fatia fatorial e decomposição por grupo DESSE modelo (``None`` sem o bloco
    ``overrides["risco"]`` ou sem medida)."""
    if not isinstance(risco, dict):
        return None
    nome = risco.get("modelo_vinculante") or modelo_vinculante(risco)
    if nome is None:
        return None
    idio = risco.get(f"idio_{nome}")
    if not isinstance(idio, (int, float)) or not math.isfinite(float(idio)):
        return None
    grupos = risco.get("por_grupo_base") if nome == "base" else risco.get("por_grupo")
    if not isinstance(grupos, dict):
        grupos = risco.get("por_grupo") if isinstance(risco.get("por_grupo"), dict) else {}
    rotulo = {"decisao": "modelo de decisão", "base": "modelo base"}[nome]
    return {"modelo": nome, "rotulo": rotulo, "idio": float(idio),
            "fatorial": 1.0 - float(idio), "por_grupo": dict(grupos)}


def parametros_modelo(model: RiskModel, cfg: FundConfig) -> dict[str, Any]:
    """Parâmetros públicos do modelo de risco (fatores por grupo, meias-vidas, histórico)."""
    rm = cfg.risk_model
    grupos: dict[str, list[str]] = {}
    for f in model.factor_names:
        grupos.setdefault(_GRUPO_DO_FATOR.get(model.factor_groups.get(f, ""), "estilo"),
                          []).append(f)
    return {
        "data": model.as_of.isoformat(), "n_emissores": len(model.assets),
        "n_fatores": len(model.factor_names), "fatores_por_grupo": grupos,
        "meia_vida_vol_fatores": rm.halflife_factor_vol,
        "meia_vida_correlacao": rm.halflife_factor_corr,
        "meia_vida_especifico": rm.halflife_specific, "newey_west": rm.newey_west_lags,
        "historico_pregoes": rm.history_days, "encolhimento_especifico": rm.specific_shrinkage,
        "proxy_mercado": rm.market_proxy, "fatores_macro": list(rm.macro_factors),
        "meia_vida_betas_macro": rm.macro_beta_halflife if rm.macro_factors else None,
        "janelas_evento": [{"nome": w.get("name"), "pais": w.get("country"),
                            "multiplicador": _sig(w.get("multiplier"))}
                           for w in model.meta.get("event_windows", []) or []],
    }


# ----------------------------------------------------------------------------- contratos E → C/D


def decomposicao_decisao(proposal: Proposal) -> dict[str, Any]:
    """Decomposição gravada na decisão (``proposal.overrides["risco"]``); propostas anteriores à
    regra (sem a chave) devolvem a decomposição indisponível, nunca recalculada com outro
    mandato."""
    raw = proposal.overrides.get(CHAVE_RISCO) if isinstance(proposal.overrides, dict) else None
    if not isinstance(raw, dict):
        return {"disponivel": False, "idio_decisao": None, "idio_base": None, "kappa_f": None,
                "por_grupo": {g: None for g in GRUPOS_IDIO}, "custo_neutralidade_bp": None,
                "vinculantes": [],
                "motivo": "decomposição idiossincrática não registrada nesta decisão"}
    out = {"disponivel": True}
    out.update(raw)
    grupos = raw.get("por_grupo") if isinstance(raw.get("por_grupo"), dict) else {}
    out["por_grupo"] = {g: grupos.get(g) for g in GRUPOS_IDIO}
    return out


def _records_frame(records: Sequence[DailyRecord]) -> pd.DataFrame:
    rows = []
    for r in sorted(records, key=lambda x: x.date):
        nav0 = float(r.nav_start_usd)
        comp = r.pnl_components or {}

        def ret(key: str, _c: dict = comp, _n: float = nav0) -> float:
            v = _c.get(key)
            return float(v) / _n if v is not None and _n > 0 else float("nan")

        rows.append({"date": pd.Timestamp(r.date), "ret": float(r.ret),
                     "specific": ret("specific"), "factor": ret("factor"),
                     "factor_vol": r.risk.factor_vol, "specific_vol": r.risk.specific_vol})
    df = pd.DataFrame(rows)
    return df.set_index("date") if len(df) else df


def _x_sigma_rho(r_s: np.ndarray, r_p: np.ndarray) -> float:
    ok = np.isfinite(r_s) & np.isfinite(r_p)
    if ok.sum() < MIN_OBS_REALIZADA:
        return float("nan")
    a, b = r_s[ok], r_p[ok]
    var_p = float(np.var(b, ddof=1))
    if not var_p > 0:
        return float("nan")
    return float(np.cov(a, b, ddof=1)[0, 1] / var_p)


def _regressao_sem_modelo(y: pd.Series, X: pd.DataFrame) -> tuple[float, int, int]:
    """``(1 − R²_aj, n, k)`` dos retornos do fundo contra os regressores (``nan`` com menos de
    :data:`MIN_GL_SEM_MODELO` graus de liberdade no resíduo). ``1 − R²_aj = (1 − R²)·(n − 1)/
    (n − k − 1)``, limitado a [0, 1]: sem viés para um fundo sem exposição aos regressores."""
    df = pd.concat([y.rename("_y"), X], axis=1).dropna()
    k, n = X.shape[1], len(df)
    if k == 0 or n - k - 1 < MIN_GL_SEM_MODELO:
        return float("nan"), n, k
    yy = df["_y"].to_numpy(dtype=float)
    xx = np.column_stack([np.ones(n), df.drop(columns="_y").to_numpy(dtype=float)])
    coef, *_ = np.linalg.lstsq(xx, yy, rcond=None)
    resid = yy - xx @ coef
    tss = float(np.sum((yy - yy.mean()) ** 2))
    if not tss > 0:
        return float("nan"), n, k
    adj = float(np.sum(resid ** 2) / tss) * (n - 1) / (n - k - 1)
    return min(max(adj, 0.0), 1.0), n, k


def _one_minus_r2(y: pd.Series, X: pd.DataFrame) -> float:
    """``1 − R²`` ajustado (:func:`_regressao_sem_modelo`)."""
    return _regressao_sem_modelo(y, X)[0]


def banda_sem_modelo(n: int, k: int) -> float | None:
    """Desvio-padrão de amostragem de ``1 − R²_aj`` sob a hipótese nula (fundo sem exposição aos
    ``k`` regressores, ``n`` observações): ``R² ~ Beta(k/2, (n − k − 1)/2)``, escalado por
    ``(n − 1)/(n − k − 1)``. ``None`` sem graus de liberdade suficientes."""
    if k <= 0 or n - k - 1 < MIN_GL_SEM_MODELO:
        return None
    a, b = k / 2.0, (n - k - 1) / 2.0
    var = a * b / ((a + b) ** 2 * (a + b + 1.0))
    return math.sqrt(var) * (n - 1) / (n - k - 1)


def serie_idio(records: Sequence[DailyRecord], md: MarketData, cfg: FundConfig) -> dict[str, Any]:
    """Série diária da fatia idiossincrática por três medidas: ex-ante (``DailyRisk.factor_vol``
    e ``specific_vol`` já gravados, com κ_F de configuração), realizada em 63 pregões (x-sigma-rho
    ``σ_S·ρ(r_S, r_p)/σ_p``) e sem modelo (``1 − R²`` ajustado dos retornos diários do fundo
    contra ILF, EWZ, EWW, ECH, EPU, COLO, ARGT, BZ=F, HG=F, GC=F e DX-Y.NYB, com a banda de
    amostragem sob a nula em ``sem_modelo_banda``); ausente fica ``None``."""
    df = _records_frame(records)
    out: dict[str, Any] = {"datas": [], "ex_ante": [], "realizada_63d": [], "sem_modelo_63d": [],
                           "sem_modelo_banda": [], "sem_modelo_obs": [],
                           "janela": JANELA_REALIZADA, "regressores": [],
                           "sem_modelo_ajustado": True,
                           "kappa_f": _sig(cfg.risk.second_order_inflation)}
    if df.empty:
        return out
    k = max(float(cfg.risk.second_order_inflation), 1.0)
    bench = md.benchmarks if md is not None and md.benchmarks is not None else pd.DataFrame()
    cols = [c for c in REGRESSORES_SEM_MODELO if c in bench.columns]
    out["regressores"] = cols
    rets = (bench[cols].sort_index().pct_change(fill_method=None) if cols else pd.DataFrame())
    for i, (d, row) in enumerate(df.iterrows()):
        fv, sv = row["factor_vol"], row["specific_vol"]
        ex = None
        if fv is not None and sv is not None and np.isfinite(fv) and np.isfinite(sv):
            tot = k * float(fv) ** 2 + float(sv) ** 2
            ex = _sig(float(sv) ** 2 / tot) if tot > 0 else None
        win = df.iloc[max(0, i + 1 - JANELA_REALIZADA): i + 1]
        real = _x_sigma_rho(win["specific"].to_numpy(dtype=float),
                            win["ret"].to_numpy(dtype=float))
        free, n_obs, k_reg = (_regressao_sem_modelo(win["ret"], rets.reindex(win.index))
                              if cols else (float("nan"), 0, 0))
        band = banda_sem_modelo(n_obs, k_reg) if math.isfinite(free) else None
        out["datas"].append(d.date().isoformat())
        out["ex_ante"].append(ex)
        out["realizada_63d"].append(_sig(real))
        out["sem_modelo_63d"].append(_sig(free))
        out["sem_modelo_banda"].append(_sig(band) if band is not None else None)
        out["sem_modelo_obs"].append(int(n_obs) if math.isfinite(free) else None)
    return out


__all__ = ["CHAVE_RISCO", "GRUPOS_IDIO", "MIN_GL_SEM_MODELO", "REGRESSORES_SEM_MODELO",
           "Z_BANDA_SEM_MODELO", "banda_sem_modelo", "base_vinculante",
           "decomposicao_decisao", "ewma_kurtosis", "fatia_idio", "kappa_f", "kappa_formula",
           "modelo_vinculante", "parametros_modelo", "por_grupo", "risco_da_decisao",
           "serie_idio"]
