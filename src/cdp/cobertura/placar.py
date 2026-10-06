"""Placar de acertos da cobertura (recalculável a partir do livro encadeado).

Cada evento do livro registra o preço de referência do instrumento na data, o fator de
desdobramento/grupamento desde o evento anterior do emissor e o retorno total em dólar desde o
último snapshot completo (ambos calculados na gravação com preços ajustados por proventos e
desdobramentos); o placar usa só o livro (sem dado externo) para medir, por previsão:

- ``TPMET12 = 1[d × (P_H − TP) ≥ 0]`` no vencimento (d = +1 se o alvo está acima do preço de
  emissão, −1 se abaixo), ``TPMETANY`` (alvo tocado em algum ponto até o vencimento), erro
  assinado ``P_H/TP − 1`` e tempo até o alvo (Kaplan–Meier, censurado na substituição/vencimento),
  com o caminho de preços reescalado à base da emissão pelos fatores de desdobramento;
- e, no corte transversal semanal (só snapshots completos, consecutivos no calendário de
  rebalanceamento; execuções parciais não interrompem a semana), o IC de postos (Spearman) de
  ``α_rel`` contra o retorno total em dólar da semana seguinte **residualizado dentro de país ×
  setor** (retorno menos a média do grupo; grupos com menos de 3 nomes usam o país, depois o
  universo), com média, desvio, ICIR e t de Newey–West.

Regras de amostra pequena: IC de 90% (Wilson) em toda taxa; nada é exibido abaixo de 20
previsões vencidas e nenhum ranking abaixo de 30; "em maturação" até o primeiro vencimento.
Referências de base (literatura): 24–38% dos alvos atingidos no vencimento, 45–64% em algum
momento, erro absoluto de 36–45%.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from typing import Any

import numpy as np
from scipy.stats import norm

N_MIN_EXIBIR = 20
N_MIN_RANKING = 30
BASE_RATES = {"tpmet12": [0.24, 0.38], "tpmetany": [0.45, 0.64], "erro_abs": [0.36, 0.45]}


def tpmet12(p0: float, tp: float, p_h: float) -> bool:
    d = 1.0 if tp >= p0 else -1.0
    return d * (p_h - tp) >= 0


def tpmetany(p0: float, tp: float, caminho: Sequence[float]) -> bool:
    d = 1.0 if tp >= p0 else -1.0
    return any(d * (p - tp) >= 0 for p in caminho)


def erro_assinado(p_h: float, tp: float) -> float:
    return p_h / tp - 1


def wilson(k: int, n: int, z: float = 1.6448536269514722) -> tuple[float, float] | None:
    """Intervalo de Wilson (90% por padrão) para uma proporção ``k/n``."""
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def kaplan_meier(duracoes: Sequence[float], eventos: Sequence[bool]) -> list[tuple[float, float]]:
    """Curva de sobrevivência ``[(t, S(t))]`` (evento = alvo atingido; censura caso contrário)."""
    pares = sorted(zip(duracoes, eventos, strict=True))
    n = len(pares)
    s = 1.0
    out: list[tuple[float, float]] = []
    i = 0
    while i < n:
        t = pares[i][0]
        d = sum(1 for x in pares[i:] if x[0] == t and x[1])
        c = sum(1 for x in pares[i:] if x[0] == t)
        risco = n - i
        if d:
            s *= 1 - d / risco
            out.append((float(t), s))
        i += c
    return out


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    a, b = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if len(a) < 3:
        return None
    ra = np.argsort(np.argsort(a, kind="mergesort"), kind="mergesort").astype(float)
    rb = np.argsort(np.argsort(b, kind="mergesort"), kind="mergesort").astype(float)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def newey_west_t(x: Sequence[float], lags: int = 0) -> float | None:
    """t da média com erro-padrão de Newey–West (pesos de Bartlett, ``lags`` defasagens)."""
    v = np.asarray([z for z in x if z is not None and math.isfinite(z)], dtype=float)
    n = len(v)
    if n < 3:
        return None
    e = v - v.mean()
    s = float(e @ e) / n
    for k in range(1, min(lags, n - 1) + 1):
        w = 1 - k / (lags + 1)
        s += 2 * w * float(e[k:] @ e[:-k]) / n
    if s <= 0:
        return None
    return float(v.mean() / math.sqrt(s / n))


def _fator(e: dict[str, Any]) -> float:
    f = ((e.get("preco_ref") or {}).get("fator_split") or {}).get("valor")
    try:
        v = float(f)
    except (TypeError, ValueError):
        return 1.0
    return v if math.isfinite(v) and v > 0 else 1.0


def residualizar(rs: Sequence[float], grupos: Sequence[str | None], paises: Sequence[str | None],
                 minimo: int = 3) -> np.ndarray:
    """Retorno menos a média do grupo país × setor (≥ ``minimo`` nomes), senão do país, senão do
    universo."""
    r = np.asarray(rs, dtype=float)
    out = r - r.mean()
    feito = np.zeros(len(r), dtype=bool)
    for chaves in (grupos, paises):
        cont: dict[Any, list[int]] = {}
        for i, k in enumerate(chaves):
            if k is not None and not feito[i]:
                cont.setdefault(k, []).append(i)
        for idx in cont.values():
            if len(idx) >= minimo:
                out[idx] = r[idx] - r[idx].mean()
                feito[idx] = True
    return out


def calcular_placar(evs: Sequence[dict[str, Any]], grupos: dict[str, str] | None, as_of: date) -> dict[str, Any]:
    """Placar a partir dos eventos do livro (só ações; ETFs ficam fora das taxas de acerto)."""
    acoes = [e for e in evs if not str(e.get("issuer_id", "")).startswith("ETF_")]
    por_inst: dict[str, list[dict[str, Any]]] = {}
    for e in acoes:
        por_inst.setdefault(e["issuer_id"], []).append(e)
    previsoes = []
    for iid, lst in sorted(por_inst.items()):
        lst = sorted(lst, key=lambda e: (e["as_of"], e["seq"]))
        for i, e in enumerate(lst):
            tp = (e.get("alvo") or {}).get("base")
            p0 = (e.get("preco_ref") or {}).get("fechamento")
            if tp is None or p0 is None or e.get("rating") in ("Em revisão", "Sem preço-alvo"):
                continue
            venc = date.fromisoformat(e["vencimento"]) if e.get("vencimento") else None
            caminho = []
            acum = 1.0
            for x in lst[i + 1:]:
                if x.get("linha") != e.get("linha"):
                    break
                acum *= _fator(x)
                px = (x.get("preco_ref") or {}).get("fechamento")
                if px is None:
                    continue
                dx = date.fromisoformat(x["as_of"])
                if venc is None or dx <= venc:
                    caminho.append((dx, float(px) * acum))
            vencida = venc is not None and venc <= as_of and bool(caminho)
            previsoes.append({"iid": iid, "emitida": e["as_of"], "p0": float(p0), "tp": float(tp),
                              "vencida": vencida, "caminho": caminho, "venc": venc,
                              "substituida": i + 1 < len(lst)})
    venc = [p for p in previsoes if p["vencida"]]
    k12 = sum(1 for p in venc if tpmet12(p["p0"], p["tp"], p["caminho"][-1][1]))
    kany = sum(1 for p in venc if tpmetany(p["p0"], p["tp"], [x[1] for x in p["caminho"]]))
    erros = [abs(erro_assinado(p["caminho"][-1][1], p["tp"])) for p in venc]
    # tempo até o alvo (dias), censurado no último ponto observado
    dur, ev = [], []
    for p in previsoes:
        if not p["caminho"]:
            continue
        d = 1.0 if p["tp"] >= p["p0"] else -1.0
        hit = next((x for x in p["caminho"] if d * (x[1] - p["tp"]) >= 0), None)
        t0 = date.fromisoformat(p["emitida"])
        if hit is not None:
            dur.append((hit[0] - t0).days)
            ev.append(True)
        else:
            dur.append((p["caminho"][-1][0] - t0).days)
            ev.append(False)
    km = kaplan_meier(dur, ev) if dur else []
    # IC semanal de α_rel vs. retorno residual (país × setor) da semana seguinte, só entre
    # snapshots completos consecutivos (execuções parciais não interrompem a semana)
    completos = [e for e in acoes if not e.get("parcial")]
    datas = sorted({e["as_of"] for e in completos})
    por_data: dict[str, dict[str, dict[str, Any]]] = {}
    for e in completos:
        por_data.setdefault(e["as_of"], {})[e["issuer_id"]] = e
    ics = []
    for a, b in zip(datas, datas[1:], strict=False):
        ea, eb = por_data[a], por_data[b]
        xs, rs, gs, ps = [], [], [], []
        for iid, e in ea.items():
            f = eb.get(iid)
            ar = e.get("alpha_rel")
            if f is None or ar is None or e.get("linha") != f.get("linha") \
                    or e.get("rating") not in ("Compra", "Neutro", "Venda"):
                continue
            rt = (f.get("preco_ref") or {}).get("retorno_total_usd") or {}
            if rt.get("desde") == a and rt.get("valor") is not None:
                ret = float(rt["valor"])
            else:  # eventos sem retorno total registrado: variação de preço com desdobramentos
                p_a = (e.get("preco_ref") or {}).get("fechamento")
                p_b = (f.get("preco_ref") or {}).get("fechamento")
                if not p_a or not p_b:
                    continue
                fator = 1.0
                for x in sorted(por_inst.get(iid, []), key=lambda z: (z["as_of"], z["seq"])):
                    if a < x["as_of"] <= b:
                        fator *= _fator(x)
                ret = p_b * fator / p_a - 1
            xs.append(float(ar))
            rs.append(ret)
            gs.append(f"{e.get('pais')}|{e.get('setor')}" if e.get("pais") and e.get("setor") else None)
            ps.append(e.get("pais"))
        if len(xs) >= 10:
            ic = spearman(xs, list(residualizar(rs, gs, ps)))
            if ic is not None:
                ics.append({"data": a, "ate": b, "ic": ic, "n": len(xs)})
    serie = [x["ic"] for x in ics]
    ic_res = None
    if serie:
        m = float(np.mean(serie))
        sd = float(np.std(serie, ddof=1)) if len(serie) > 1 else None
        ic_res = {"media": m, "dp": sd, "icir_anual": None if not sd else m / sd * math.sqrt(52),
                  "t_newey_west": newey_west_t(serie, 0), "semanas": len(serie),
                  "p_ic_positivo": None if not sd else float(norm.cdf(m / (sd / math.sqrt(len(serie)))))}
    ult = {}
    for e in acoes:
        ult[e["issuer_id"]] = e
    dist: dict[str, int] = {}
    for e in ult.values():
        dist[str(e.get("rating"))] = dist.get(str(e.get("rating")), 0) + 1
    obsoletos = sum(1 for e in ult.values() if (as_of - date.fromisoformat(e["as_of"])).days > 105)
    n = len(venc)
    primeiro_venc = min((p["venc"] for p in previsoes if p["venc"]), default=None)
    return {
        "as_of": as_of.isoformat(), "n_previsoes": len(previsoes), "n_vencidas": n,
        "em_maturacao": n < N_MIN_EXIBIR, "primeiro_vencimento": primeiro_venc.isoformat() if primeiro_venc else None,
        "exibir_taxas": n >= N_MIN_EXIBIR, "exibir_ranking": n >= N_MIN_RANKING,
        "tpmet12": {"k": k12, "n": n, "taxa": k12 / n if n else None, "ic90": wilson(k12, n)},
        "tpmetany": {"k": kany, "n": n, "taxa": kany / n if n else None, "ic90": wilson(kany, n)},
        "erro_abs_mediano": float(np.median(erros)) if erros else None,
        "tempo_ate_alvo_km": [{"dias": t, "sobrevivencia": s} for t, s in km],
        "ic_semanal": ics, "ic_resumo": ic_res, "distribuicao_ratings": dict(sorted(dist.items())),
        "obsoletos": obsoletos, "referencias_literatura": BASE_RATES,
        "metodo": "amostragem semanal dos preços de referência registrados no livro, reescalados por "
                  "desdobramentos; IC entre snapshots completos consecutivos contra o retorno total em dólar "
                  "menos a média do grupo país × setor",
    }


__all__ = ["BASE_RATES", "calcular_placar", "erro_assinado", "kaplan_meier", "newey_west_t", "residualizar",
           "spearman", "tpmet12", "tpmetany", "wilson"]
