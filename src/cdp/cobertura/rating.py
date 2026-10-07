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

Confiança: **A** ≥ 3 métodos válidos, insumos point-in-time, moeda sem correção, CV entre TODOS os
métodos calculados (com a dissidência: discrepante pelo valor bruto, não positivos como zero) ≤ 25%,
nenhuma dissidência nem aviso de qualidade e consenso de LPA de ≥ 3 analistas; avisos de alinhamento
ou de combinação (G15 data-base dos fluxos; G18 método discrepante limitado ou mantido) e a
dissidência do método principal limitam a B; **C** um único método (exceto a holding com todas as
participações conferidas no documento-fonte e ≥ 52 semanas de histórico do desconto), CV > 50%,
avisos de qualidade, Argentina ou holding com participações não conferidas; **B** nos demais casos
com preço-alvo; **Insuficiente** sem preço-alvo. Portões informativos (G4, G10) não afetam a
confiança.

Exposição de estilo explícita: a cada execução, ``b̂`` = inclinação de Theil–Sen de ``α_rel``
contra ``Δln(P/VPA)`` (desvio da mediana do grupo de pares) e ``α_rel_estilo = α_rel − b̂ ×
Δln(P/VPA)``; Compra e Venda exigem também ``α_rel_estilo`` além de ``±τ × fração`` (dupla
condição: nenhum rating é só uma aposta em P/VPA). Higiene dos pares: emissores bloqueados, com
retorno extremo (G11) ou patrimônio residual frágil (G16) não entram na mediana dos pares.

Execução parcial: os pares que não foram reavaliados entram na mediana com o α publicado no
último snapshot que os cobriu (a mesma tabela que o portal exibe).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from .formato import num, operando, pct, pp
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
    """A: ≥ 3 métodos, insumos point-in-time, moeda sem correção, dispersão entre TODOS os métodos
    calculados (com a dissidência) ≤ 25%, nenhuma dissidência nem aviso de qualidade, consenso de LPA
    de ≥ 3 analistas (``analistas_min_a``) definindo o ROE dos anos 1–2; C: método único, dispersão >
    50%, avisos de qualidade (exceto os que só limitam a B), Argentina ou holding não conferida; B: os
    demais com preço-alvo (inclusive dissidência — método discrepante limitado ou mantido, método
    principal do arquétipo dissidente — e consenso de menos de 3 analistas ou ausente)."""
    if not mod.get("tem_alvo"):
        return "Insuficiente", "sem preço-alvo"
    q = params.sec("qualidade")
    n = int(mod.get("n_metodos") or 0)
    cv = _f(mod.get("cv_todos")) if mod.get("cv_todos") is not None else _f(mod.get("cv"))
    av = avisos_q(mod.get("portoes", []))
    motivos = []
    sp = pac.get("soma_partes") or {}
    holding = pac.get("arquetipo") == "holding"
    holding_ok = not (holding and sp and not sp.get("conferido"))
    holding_b = holding and bool(sp) and bool(sp.get("conferido")) and sp.get("razao_mediana") is not None
    n_eps = _f(mod.get("n_eps"))
    n_a = int(q.get("analistas_min_a", 3))
    consenso_a = bool(mod.get("eps1_consenso")) and n_eps is not None and n_eps >= n_a
    dissid = list(mod.get("dissidencia") or [])
    limites_b: list[str] = []
    if not holding and not consenso_a:
        limites_b.append(f"consenso de LPA de {int(n_eps)} analista(s), abaixo de {n_a}" if n_eps is not None and
                         mod.get("eps1_consenso") else "ROE dos anos 1–2 sem consenso de LPA verificável")
    if dissid:
        limites_b.append("dissidência entre métodos (" + ", ".join(sorted({d["tipo"].replace("_", " ") for d in dissid}))
                         + ")")
    if mod.get("principal_dissidente"):
        limites_b.append(f"método principal do arquétipo dissidente ({mod.get('metodo_principal')})")
    if n >= 3 and pac.get("pit_ok") and pac.get("status_moeda") == "ok" and cv is not None \
            and cv <= float(q["cv_metodos_a"]) and not av and pac["pais"] != "AR" and holding_ok and not limites_b:
        return "A", f"{n} métodos, CV {pct(cv, 0)}, insumos point-in-time, consenso de LPA de {int(n_eps)} analistas"
    if n <= 1 and not holding_b:
        motivos.append("método único" if not holding else
                       "holding sem 52 semanas de histórico do desconto com a composição atual")
    if cv is not None and cv > float(q["cv_metodos_c"]):
        motivos.append(f"CV entre os métodos calculados de {pct(cv, 0)}")
    so_b = set(params.sec("rating").get("avisos_limitam_b") or [])
    av_c = [a for a in av if a not in so_b]
    if av_c:
        motivos.append("avisos de qualidade " + ", ".join(av_c))
    if pac["pais"] == "AR":
        motivos.append("Argentina (contabilidade com inflação e câmbio)")
    if pac.get("arquetipo") == "holding" and sp and not sp.get("conferido"):
        motivos.append("participações da holding não conferidas no documento-fonte")
    if motivos:
        return "C", "; ".join(motivos)
    av_b = [a for a in av if a in so_b]
    extra = (f"; avisos que limitam a B: {', '.join(av_b)}" if av_b else "") + (
        f"; limitam a B: {'; '.join(limites_b)}" if limites_b else "")
    if holding_b:
        return "B", (f"soma das partes com todas as participações conferidas no documento-fonte e "
                     f"{sp.get('semanas')} semanas de histórico do desconto{extra}")
    return "B", f"{n} métodos, CV {pct(cv, 0) if cv is not None else 'n/d'}{extra}"


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


def _ln_pb(pac: Mapping[str, Any], m: Mapping[str, Any]) -> float | None:
    p0, b0 = _f(pac.get("preco")), _f(m.get("b0"))
    return None if p0 is None or b0 is None or p0 <= 0 or b0 <= 0 else math.log(p0 / b0)


def exposicao_estilo(modelos: Mapping[str, Mapping[str, Any]], pacotes: Mapping[str, Mapping[str, Any]],
                     ids: list[str], n_min: int) -> dict[str, Any]:
    """Inclinação de Theil–Sen de ``α_rel`` contra ``Δln(P/VPA)`` (desvio da mediana do grupo de
    pares) entre os emissores citáveis, e a correlação de postos correspondente."""
    from scipy.stats import spearmanr, theilslopes

    pontos = []
    grupos: dict[str, list[float]] = {}
    for i in ids:
        m = modelos[i]
        lp = _ln_pb(pacotes[i], m)
        if lp is not None and m.get("alpha_rel") is not None:
            grupos.setdefault(m["pares"]["grupo"], []).append(lp)
    med = {g: float(np.median(v)) for g, v in grupos.items()}
    for i in ids:
        m = modelos[i]
        lp = _ln_pb(pacotes[i], m)
        if lp is None or m.get("alpha_rel") is None:
            continue
        pontos.append((i, float(m["alpha_rel"]), lp - med[m["pares"]["grupo"]]))
    out: dict[str, Any] = {"n": len(pontos), "b": None, "rho": None, "delta_ln_pb": {i: d for i, _, d in pontos}}
    if len(pontos) >= n_min:
        a = np.array([x[1] for x in pontos])
        d = np.array([x[2] for x in pontos])
        if np.ptp(d) > 0:
            out["b"] = float(theilslopes(a, d)[0])
            out["rho"] = float(spearmanr(a, d).statistic)
    return out


def aplicar(modelos: dict[str, dict[str, Any]], pacotes: Mapping[str, Mapping[str, Any]],
            params: ParametrosCobertura, anteriores: Mapping[str, str] | None = None,
            registros: Mapping[str, Registro] | None = None,
            alphas_publicados: Mapping[str, float | None] | None = None,
            paises_regionais: set[str] | None = None) -> dict[str, Any]:
    """Preenche incerteza, pares, α_rel, exposição de estilo, confiança e rating em cada modelo
    (in place).

    ``alphas_publicados`` (execução parcial): ``{emissor: α publicado ou None}`` dos pares que não
    foram reavaliados; entram na mediana dos pares no lugar do α recalculado.
    ``paises_regionais``: países sem ajuste de nível próprio (menos de 8 emissores; ajuste regional):
    seus emissores não entram na mediana dos pares de emissores de outros países."""
    regionais = set(paises_regionais or ())
    rcfg = params.sec("rating")
    anteriores = anteriores or {}
    fixos = dict(alphas_publicados or {})
    classes, quartis = classes_incerteza(modelos)
    bloq = {i: bloqueios(m.get("portoes", [])) for i, m in modelos.items()}
    excl_av = set(rcfg.get("pares_excluir_avisos", []) or [])
    fora_pares = {i: sorted(set(avisos_q(m.get("portoes", []))) & excl_av) for i, m in modelos.items()}

    def alpha_par(j: str) -> float | None:
        if j in fixos:
            return _f(fixos[j])
        m = modelos[j]
        if not m.get("tem_alvo") or bloq[j] or fora_pares[j]:
            return None
        return _f(m.get("alpha"))

    com_alpha = {i for i in modelos if alpha_par(i) is not None}
    minimo = int(rcfg["pares_min"])
    h = float(rcfg["histerese"])
    a_min_c, a_max_v = float(rcfg["guarda_compra_alpha_min"]), float(rcfg["guarda_venda_alpha_max"])
    conf_min = CONFIANCA_ORDEM[str(rcfg["confianca_minima"])]
    est_cfg = rcfg.get("estilo") or {}
    # 1) incerteza, pares e α relativo
    for iid in sorted(modelos):
        m = modelos[iid]
        reg = registros.get(iid) if registros else None
        if not m.get("tem_alvo"):
            m["incerteza"] = None
            continue
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
        pa_i = str(pacotes[iid]["pais"])
        cand = {j for j in com_alpha if str(pacotes[j]["pais"]) == pa_i or str(pacotes[j]["pais"]) not in regionais}
        nome_g, ids = grupo_pares(iid, pacotes, cand, minimo)
        alphas = [alpha_par(j) if j != iid else _f(m.get("alpha")) for j in ids]
        alphas = [x for x in alphas if x is not None]
        med = float(np.median(alphas)) if alphas else None
        a = float(m["alpha"])
        m["pares"] = {"grupo": nome_g, "n": len(ids), "mediana_alpha": med, "emissores": ids,
                      "alphas": [[j, alpha_par(j) if j != iid else a] for j in ids],
                      "fora_da_mediana": fora_pares[iid] or None,
                      "regional": pa_i in regionais or None}
        m["alpha_rel"] = None if med is None else a - med
        if reg is not None and m["alpha_rel"] is not None:
            excl_txt = (f"; este emissor não entra na mediana dos demais ({', '.join(fora_pares[iid])})"
                        if fora_pares[iid] else "")
            if pa_i in regionais:
                excl_txt += ("; país com ajuste de nível regional (menos de 8 emissores): fora das medianas de pares "
                             "de outros países")
            reg.add("rating.alpha_rel", "Alpha relativo aos pares",
                    "α_rel = α − mediana(α dos pares)",
                    f"α_rel = {operando(pct(a))} − {operando(pct(med))}", m["alpha_rel"], "%",
                    premissas=f"pares: {nome_g}, {len(ids)} nomes ({', '.join(ids)}){excl_txt}")
    # 2) exposição de estilo (P/VPA) entre os citáveis
    citaveis = [i for i in sorted(modelos) if modelos[i].get("tem_alvo") and not bloq[i]
                and modelos[i].get("alpha_rel") is not None]
    est = exposicao_estilo(modelos, pacotes, citaveis, int(est_cfg.get("n_min", 30)))
    b_est = est["b"]
    for iid in citaveis:
        m = modelos[iid]
        d = est["delta_ln_pb"].get(iid)
        m["alpha_rel_estilo"] = (m["alpha_rel"] if b_est is None or d is None
                                 else float(m["alpha_rel"]) - b_est * d)
        reg = registros.get(iid) if registros else None
        if reg is not None and b_est is not None and d is not None:
            reg.add("rating.estilo", "Alpha relativo sem a exposição de estilo (P/VPA)",
                    "α_rel_estilo = α_rel − b̂ × (ln P/VPA − mediana do ln P/VPA dos pares)",
                    f"α_rel_estilo = {operando(pct(m['alpha_rel']))} − {operando(num(b_est, 3))} × "
                    f"{operando(num(d, 3))}", m["alpha_rel_estilo"], "%",
                    premissas=(f"b̂ = inclinação de Theil–Sen de α_rel contra Δln(P/VPA) nos {est['n']} emissores "
                               f"citáveis desta execução (correlação de postos {num(est['rho'], 2)})"))
    # 3) confiança e rating
    cont: dict[str, int] = {}
    frac_est = float(est_cfg.get("fracao_limiar", 0.5))
    dupla = bool(est_cfg.get("dupla_condicao", False))
    for iid in sorted(modelos):
        m = modelos[iid]
        reg = registros.get(iid) if registros else None
        conf, conf_txt = confianca(pacotes[iid], m, params)
        m["confianca"], m["confianca_motivo"] = conf, conf_txt
        if not m.get("tem_alvo"):
            m["rating"], m["rating_motivo"] = "Sem preço-alvo", m.get("motivo_sem_alvo") or "sem método disponível"
        else:
            inc = m["incerteza"]
            arel = m.get("alpha_rel")
            a = float(m["alpha"])
            tau = float(rcfg["limiar_alpha_rel"][inc])
            prev = anteriores.get(iid)
            tau_c = tau - h if prev == "Compra" else tau
            tau_v = tau - h if prev == "Venda" else tau
            fc, fv = _guardas(m, a, rcfg)
            ae = _f(m.get("alpha_rel_estilo"))
            if dupla and ae is not None and arel is not None:
                if arel >= tau_c and ae < frac_est * tau_c:
                    fc = fc + [f"sem a exposição de estilo α_rel {pct(ae)} < {pct(frac_est * tau_c)} (dupla condição)"]
                if arel <= -tau_v and ae > -frac_est * tau_v:
                    fv = fv + [f"sem a exposição de estilo α_rel {pct(ae)} > −{pct(frac_est * tau_v)} (dupla condição)"]
            conf_ok = CONFIANCA_ORDEM[conf] >= conf_min
            if bloq[iid]:
                rt, motivo = "Em revisão", "portão de qualidade bloqueante: " + ", ".join(bloq[iid])
            elif arel is None:
                rt, motivo = "Neutro", "sem pares com alpha"
            elif arel >= tau_c and not fc and conf_ok:
                rt, motivo = "Compra", (f"α_rel {pct(arel)} ≥ {pct(tau_c)}, α {pct(a)} ≥ {pct(a_min_c, 0)} e "
                                        "ETR do caso-base ≥ ke com upside positivo"
                                        + (f"; sem a exposição de estilo, α_rel {pct(ae)}" if dupla and ae is not None
                                           else ""))
            elif arel <= -tau_v and not fv and conf_ok:
                rt, motivo = "Venda", (f"α_rel {pct(arel)} ≤ −{pct(tau_v)}, α {pct(a)} ≤ {pct(a_max_v, 0)} e "
                                       "ETR do caso-base ≤ ke − 5 p.p."
                                       + (f"; sem a exposição de estilo, α_rel {pct(ae)}" if dupla and ae is not None
                                          else ""))
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
    mon = monitoramento(modelos, pacotes, est, rcfg)
    alertas.extend(mon.pop("alertas"))
    return {"distribuicao": dict(sorted(cont.items())), "alertas_distribuicao": alertas,
            "quartis_incerteza": quartis, "estilo": {"b": est["b"], "rho": est["rho"], "n": est["n"]},
            "monitoramento": mon}


def monitoramento(modelos: Mapping[str, Mapping[str, Any]], pacotes: Mapping[str, Mapping[str, Any]],
                  est: Mapping[str, Any], rcfg: Mapping[str, Any]) -> dict[str, Any]:
    """Indicadores de calibração da execução (monitorados, nunca forçados): mediana de α por país,
    fração "Em revisão", fração com confiança C e a exposição de estilo do rating."""
    mon_cfg = rcfg.get("monitoramento") or {}
    por_pais: dict[str, list[float]] = {}
    for i, m in modelos.items():
        if m.get("tem_alvo") and _f(m.get("alpha")) is not None:
            por_pais.setdefault(str(pacotes[i]["pais"]), []).append(float(m["alpha"]))
    med = {k: float(np.median(v)) for k, v in sorted(por_pais.items())}
    n = len(modelos)
    rev = sum(1 for m in modelos.values() if m.get("rating") == "Em revisão")
    c = sum(1 for m in modelos.values() if m.get("confianca") == "C")
    alertas = []
    lim_a = float(mon_cfg.get("alpha_pais_max_abs", 0.05))
    for k, v in med.items():
        if len(por_pais[k]) >= 8 and abs(v) > lim_a:
            alertas.append(f"mediana de α em {k} = {pct(v, 1, True)} fora de ±{pct(lim_a, 0)}")
    if n and rev / n > float(mon_cfg.get("em_revisao_max", 0.08)):
        alertas.append(f"Em revisão: {pct(rev / n, 0)} acima de {pct(float(mon_cfg.get('em_revisao_max', 0.08)), 0)}")
    if n and c / n > float(mon_cfg.get("confianca_c_max", 0.35)):
        alertas.append(f"confiança C: {pct(c / n, 0)} acima de {pct(float(mon_cfg.get('confianca_c_max', 0.35)), 0)}")
    return {"alpha_mediano_pais": {k: r for k, r in med.items()},
            "n_pais": {k: len(v) for k, v in sorted(por_pais.items())},
            "em_revisao": rev, "confianca_c": c, "n": n,
            "estilo_b": est.get("b"), "estilo_rho": est.get("rho"), "alertas": alertas}


__all__ = ["CLASSES", "CODIGO_CONFIANCA", "CODIGO_RATING", "aplicar", "classes_incerteza", "confianca",
           "exposicao_estilo", "grupo_pares", "monitoramento"]
