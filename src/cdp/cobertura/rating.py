"""Etapa transversal: classe de incerteza, pares, alpha relativo, confiança e rating.

Rating de 12 meses relativo ao grupo de pares da cobertura:

- **Compra**: ``α_rel ≥ τ(incerteza)`` e ``α ≥ 0`` e, no caso-base, ``ETR ≥ ke`` e upside > 0, com
  confiança A ou B;
- **Venda**: ``α_rel ≤ −τ(incerteza)`` e ``α ≤ −5 p.p.`` e, no caso-base, ``ETR ≤ ke − 5 p.p.``,
  com confiança A ou B;
- **Neutro** nos demais casos; **Em revisão** quando um portão de qualidade bloqueia;
  **Sem preço-alvo** quando nenhum método tem insumos suficientes.

``α = PWR − ke`` (retorno ponderado por probabilidade menos o custo de capital), ``α_rel = α −
mediana(α dos pares)``; pares = país × setor com ≥ 5 nomes, senão setor (LatAm), senão país,
senão o universo. Histerese de 2 p.p.: quem já é Compra (Venda) só perde o rating quando ``α_rel``
volta abaixo de ``τ − 2 p.p.``. A distribuição de ratings é monitorada (faixas de 20–40%), nunca
forçada.

Confiança: **A** ≥ 3 métodos válidos, insumos point-in-time, moeda sem correção, CV ≤ 25% e
nenhum aviso de qualidade; **C** um único método, CV > 50%, avisos de qualidade, Argentina ou
holding com participações não conferidas no documento-fonte; **B** nos demais casos com
preço-alvo; **Insuficiente** sem preço-alvo. Portões informativos (G4) não afetam a confiança.

Execução parcial: os pares que não foram reavaliados entram na mediana com o α publicado no
último snapshot que os cobriu (a mesma tabela que o portal exibe).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from .formato import operando, pct, pp
from .parametros import ParametrosCobertura
from .passos import Registro
from .qualidade import avisos as avisos_q
from .qualidade import bloqueios

CLASSES = ("Baixa", "Média", "Alta", "Muito alta")
CONFIANCA_ORDEM = {"A": 3, "B": 2, "C": 1, "Insuficiente": 0}
CODIGO_RATING = {"Compra": 1.0, "Neutro": 0.0, "Venda": -1.0}
CODIGO_CONFIANCA = {"A": 3.0, "B": 2.0, "C": 1.0, "Insuficiente": 0.0}


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def self_p(x: Any, pac: Mapping[str, Any]) -> str:
    from .formato import preco

    return preco(_f(x), str(pac.get("moeda")))


def classes_incerteza(modelos: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, str], list[float]]:
    """Quartis da largura dos cenários ``(P90 − P10)/TP`` no universo ⇒ Baixa…Muito alta."""
    larg = {i: _f(m.get("largura_cenarios")) for i, m in modelos.items() if m.get("tem_alvo")}
    vals = [v for v in larg.values() if v is not None]
    if len(vals) < 4:
        return {i: "Média" for i in larg}, []
    q = [float(x) for x in np.percentile(vals, [25, 50, 75])]
    out = {}
    for i, v in larg.items():
        if v is None:
            out[i] = "Média"
        elif v <= q[0]:
            out[i] = "Baixa"
        elif v <= q[1]:
            out[i] = "Média"
        elif v <= q[2]:
            out[i] = "Alta"
        else:
            out[i] = "Muito alta"
    return out, q


def grupo_pares(iid: str, pacotes: Mapping[str, Mapping[str, Any]], com_alpha: set[str],
                minimo: int) -> tuple[str, list[str]]:
    p = pacotes[iid]
    regras = [
        (f"{p['pais']} × {p['setor']}", lambda q: q["pais"] == p["pais"] and q["setor"] == p["setor"]),
        (f"{p['setor']} (América Latina)", lambda q: q["setor"] == p["setor"]),
        (f"{p['pais']} (todos os setores)", lambda q: q["pais"] == p["pais"]),
    ]
    for nome, f in regras:
        ids = sorted(j for j in com_alpha if f(pacotes[j]))
        if len(ids) >= minimo:
            return nome, ids
    return "universo da cobertura", sorted(com_alpha)


def confianca(pac: Mapping[str, Any], mod: Mapping[str, Any], params: ParametrosCobertura) -> tuple[str, str]:
    if not mod.get("tem_alvo"):
        return "Insuficiente", "sem preço-alvo"
    q = params.sec("qualidade")
    n = int(mod.get("n_metodos") or 0)
    cv = _f(mod.get("cv"))
    av = avisos_q(mod.get("portoes", []))
    motivos = []
    sp = pac.get("soma_partes") or {}
    holding_ok = not (pac.get("arquetipo") == "holding" and sp and not sp.get("conferido"))
    if n >= 3 and pac.get("pit_ok") and pac.get("status_moeda") == "ok" and cv is not None \
            and cv <= float(q["cv_metodos_a"]) and not av and pac["pais"] != "AR" and holding_ok:
        return "A", f"{n} métodos, CV {pct(cv, 0)}, insumos point-in-time"
    if n <= 1:
        motivos.append("método único")
    if cv is not None and cv > float(q["cv_metodos_c"]):
        motivos.append(f"CV entre métodos de {pct(cv, 0)}")
    if av:
        motivos.append("avisos de qualidade " + ", ".join(av))
    if pac["pais"] == "AR":
        motivos.append("Argentina (contabilidade com inflação e câmbio)")
    sp = pac.get("soma_partes") or {}
    if pac.get("arquetipo") == "holding" and sp and not sp.get("conferido"):
        motivos.append("participações da holding não conferidas no documento-fonte")
    if motivos:
        return "C", "; ".join(motivos)
    return "B", f"{n} métodos, CV {pct(cv, 0) if cv is not None else 'n/d'}"


def _guardas(m: Mapping[str, Any], a: float, rcfg: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Guardas absolutas de Compra e de Venda que FALHARAM (texto pt-BR para o motivo)."""
    a_min_c, a_max_v = float(rcfg["guarda_compra_alpha_min"]), float(rcfg["guarda_venda_alpha_max"])
    ke = _f((m.get("custo_capital") or {}).get("ke"))
    etr, up = _f(m.get("etr")), _f(m.get("upside"))
    fc, fv = [], []
    if a < a_min_c:
        fc.append(f"α {pct(a)} < {pct(a_min_c, 0)}")
    if a > a_max_v:
        fv.append(f"α {pct(a)} > {pct(a_max_v, 0)}")
    g_etr_c = rcfg.get("guarda_compra_etr_menos_ke_min")
    g_up_c = rcfg.get("guarda_compra_upside_min")
    g_etr_v = rcfg.get("guarda_venda_etr_menos_ke_max")
    if ke is not None and etr is not None:
        if g_etr_c is not None and etr - ke < float(g_etr_c):
            fc.append(f"ETR do caso-base {pct(etr)} abaixo do ke de {pct(ke)}")
        if g_etr_v is not None and etr - ke > float(g_etr_v):
            fv.append(f"ETR do caso-base {pct(etr)} acima de ke {pp(float(g_etr_v), 0)} ({pct(ke + float(g_etr_v))})")
    if g_up_c is not None and up is not None and up <= float(g_up_c):
        fc.append(f"upside do caso-base {pct(up)} não positivo")
    return fc, fv


def aplicar(modelos: dict[str, dict[str, Any]], pacotes: Mapping[str, Mapping[str, Any]],
            params: ParametrosCobertura, anteriores: Mapping[str, str] | None = None,
            registros: Mapping[str, Registro] | None = None,
            alphas_publicados: Mapping[str, float | None] | None = None) -> dict[str, Any]:
    """Preenche incerteza, pares, α_rel, confiança e rating em cada modelo (in place).

    ``alphas_publicados`` (execução parcial): ``{emissor: α publicado ou None}`` dos pares que não
    foram reavaliados; entram na mediana dos pares no lugar do α recalculado."""
    rcfg = params.sec("rating")
    anteriores = anteriores or {}
    fixos = dict(alphas_publicados or {})
    classes, quartis = classes_incerteza(modelos)
    bloq = {i: bloqueios(m.get("portoes", [])) for i, m in modelos.items()}

    def alpha_par(j: str) -> float | None:
        if j in fixos:
            return _f(fixos[j])
        m = modelos[j]
        return _f(m.get("alpha")) if m.get("tem_alvo") and not bloq[j] else None

    com_alpha = {i for i in modelos if alpha_par(i) is not None}
    minimo = int(rcfg["pares_min"])
    h = float(rcfg["histerese"])
    a_min_c, a_max_v = float(rcfg["guarda_compra_alpha_min"]), float(rcfg["guarda_venda_alpha_max"])
    conf_min = CONFIANCA_ORDEM[str(rcfg["confianca_minima"])]
    cont: dict[str, int] = {}
    for iid in sorted(modelos):
        m = modelos[iid]
        reg = registros.get(iid) if registros else None
        conf, conf_txt = confianca(pacotes[iid], m, params)
        m["confianca"], m["confianca_motivo"] = conf, conf_txt
        if not m.get("tem_alvo"):
            m["rating"], m["rating_motivo"] = "Sem preço-alvo", m.get("motivo_sem_alvo") or "sem método disponível"
            m["incerteza"] = None
        else:
            inc = classes.get(iid, "Média")
            m["incerteza"] = inc
            larg = _f(m.get("largura_cenarios"))
            if reg is not None and larg is not None:
                q_txt = ("; ".join(f"{nm} {pct(v, 0)}" for nm, v in zip(("P25", "P50", "P75"), quartis, strict=False))
                         if quartis else "menos de 4 emissores com cenários: classe Média")
                reg.add("rating.incerteza", "Incerteza do preço-alvo (largura dos cenários)",
                        "largura = (P90 − P10) ÷ TP12; classe pelos quartis do universo",
                        f"largura = ({self_p(m.get('tp_otimista'), pacotes[iid])} − "
                        f"{self_p(m.get('tp_pessimista'), pacotes[iid])}) ÷ {self_p(m.get('tp'), pacotes[iid])}",
                        larg, "%", premissas=f"quartis do universo: {q_txt} ⇒ incerteza {inc.lower()}")
            nome_g, ids = grupo_pares(iid, pacotes, com_alpha, minimo)
            alphas = [alpha_par(j) if j != iid else _f(m.get("alpha")) for j in ids]
            alphas = [x for x in alphas if x is not None]
            med = float(np.median(alphas)) if alphas else None
            a = float(m["alpha"])
            arel = None if med is None else a - med
            m["pares"] = {"grupo": nome_g, "n": len(ids), "mediana_alpha": med, "emissores": ids,
                          "alphas": [[j, alpha_par(j) if j != iid else a] for j in ids]}
            m["alpha_rel"] = arel
            tau = float(rcfg["limiar_alpha_rel"][inc])
            prev = anteriores.get(iid)
            tau_c = tau - h if prev == "Compra" else tau
            tau_v = tau - h if prev == "Venda" else tau
            fc, fv = _guardas(m, a, rcfg)
            conf_ok = CONFIANCA_ORDEM[conf] >= conf_min
            if bloq[iid]:
                rt, motivo = "Em revisão", "portão de qualidade bloqueante: " + ", ".join(bloq[iid])
            elif arel is None:
                rt, motivo = "Neutro", "sem pares com alpha"
            elif arel >= tau_c and not fc and conf_ok:
                rt, motivo = "Compra", (f"α_rel {pct(arel)} ≥ {pct(tau_c)}, α {pct(a)} ≥ {pct(a_min_c, 0)} e "
                                        "ETR do caso-base ≥ ke com upside positivo")
            elif arel <= -tau_v and not fv and conf_ok:
                rt, motivo = "Venda", (f"α_rel {pct(arel)} ≤ −{pct(tau_v)}, α {pct(a)} ≤ {pct(a_max_v, 0)} e "
                                       "ETR do caso-base ≤ ke − 5 p.p.")
            else:
                partes = [f"α_rel {pct(arel)} vs limiar ±{pct(tau)} (incerteza {inc.lower()})"]
                if arel >= tau_c and fc:
                    partes.append("guarda de Compra não atendida: " + "; ".join(fc))
                if arel <= -tau_v and fv:
                    partes.append("guarda de Venda não atendida: " + "; ".join(fv))
                if not conf_ok:
                    partes.append(f"confiança {conf} abaixo do mínimo {rcfg['confianca_minima']}")
                rt, motivo = "Neutro", "; ".join(partes)
            m["rating"], m["rating_motivo"] = rt, motivo
            if reg is not None and arel is not None:
                reg.add("rating.alpha_rel", "Alpha relativo aos pares",
                        "α_rel = α − mediana(α dos pares)",
                        f"α_rel = {operando(pct(a))} − {operando(pct(med))}", arel, "%",
                        premissas=f"pares: {nome_g}, {len(ids)} nomes ({', '.join(ids)})")
        if reg is not None:
            reg.nota("rating.regra", "Rating de 12 meses",
                     f"{m['rating']}: {str(m['rating_motivo']).rstrip('.')}. Confiança {conf} ({conf_txt}).")
        cont[m["rating"]] = cont.get(m["rating"], 0) + 1
    rated = sum(cont.get(k, 0) for k in ("Compra", "Neutro", "Venda"))
    alertas = []
    for k, (lo, hi) in rcfg["distribuicao_monitorada"].items():
        if rated:
            s = cont.get(k, 0) / rated
            if not (lo <= s <= hi):
                alertas.append(f"{k}: {pct(s, 0)} fora da faixa monitorada {pct(lo, 0)}–{pct(hi, 0)}")
    return {"distribuicao": dict(sorted(cont.items())), "alertas_distribuicao": alertas,
            "quartis_incerteza": quartis}


__all__ = ["CLASSES", "CODIGO_CONFIANCA", "CODIGO_RATING", "aplicar", "classes_incerteza", "confianca",
           "grupo_pares"]
