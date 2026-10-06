"""Portões de qualidade da cobertura (determinísticos; bloqueio ⇒ rating "Em revisão").

| Portão | Regra | Efeito |
|---|---|---|
| G1 | identidades contábeis (EBITDA = EBIT + D&A; FCF = CFO − capex; PL = controladores + minoritários) | aviso |
| G2 | nenhum insumo publicado depois da data do snapshot | bloqueio |
| G3 | valor intrínseco e preço-alvo finitos | sem alvo |
| G4 | ke dentro do envelope P10–P90 dos demais emissores do país × setor (± 1 p.p.) | informativo |
| G5 | g ≤ rf local, ke − g ≥ 3 p.p.; valor terminal ≤ 85% (aviso) / 95% (método excluído) | aviso |
| G6 | otimista ≥ base ≥ pessimista | bloqueio |
| G7 | resíduo da ponte do alvo ≤ 0,5% do alvo | aviso |
| G8 | moeda dos insumos coerente (ok ou corrigida pelo câmbio) | bloqueio |
| G9 | preço-alvo ÷ preço − 1 dentro de [−70%; +200%] | bloqueio |
| G10 | largura dos cenários dentro de [0,5 × P25; 2 × P75] do universo | aviso |
| G11 | retorno ponderado por probabilidade dentro de ±60% | bloqueio |
| G12 | preço com no máximo 5 pregões de defasagem | bloqueio |
| G13 | insumos por ação plausíveis (P/VPA em [0,1; 15], ROE_1 em módulo ≤ 100%, LPA de consenso coerente com o lucro de 12 meses quando métodos patrimoniais pesam > 50%) — armadilha de unidade/moeda | bloqueio |
| G14 | FCFF do ano 1 ÷ fluxo de caixa livre observado (CFO − capex) em [0,5; 2]; com fluxo observado não positivo, FCFF do ano 1 também não positivo (anos com reinvestimento limitado são sinalizados no detalhe) | aviso |
| G15 | fluxos de 12 meses e balanço na mesma data-base (defasagem ≤ 100 dias) | aviso |

"Informativo": exibido no modelo aberto, sem efeito na confiança nem no rating. "Aviso": rebaixa a
confiança para C (sem Compra ou Venda). "Bloqueio": rating "Em revisão" e preço-alvo não citável.

ETFs (``portoes_etf``): E1 preço-alvo finito e positivo; E2 retorno esperado em [−50%; +100%];
E3 P/L justificado ÷ P/L corrente dentro de [0,6; 1,6] (aviso); E4 top-down com componentes
plausíveis (bloqueio quando o payout do índice fica no limite do intervalo).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from .formato import num, pct
from .parametros import ParametrosCobertura


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _portao(cod: str, nome: str, ok: bool | None, efeito: str, detalhe: str) -> dict[str, Any]:
    status = "nao_aplicavel" if ok is None else ("ok" if ok else efeito)
    return {"codigo": cod, "nome": nome, "status": status, "detalhe": detalhe}


def portoes_emissor(pac: Mapping[str, Any], mod: Mapping[str, Any], params: ParametrosCobertura) -> list[dict[str, Any]]:
    q = params.sec("qualidade")
    tol = float(q["identidade_tolerancia"])
    out: list[dict[str, Any]] = []
    # G1 identidades
    falhas = []

    def ident(a: str, b: list[tuple[str, float]], nome: str) -> None:
        va = _f(pac.get(f"t.{a}"))
        vs = [(_f(pac.get(f"t.{k}")), s) for k, s in b]
        if va is None or any(v is None for v, _ in vs):
            return
        soma = sum(s * v for v, s in vs)  # type: ignore[operator]
        if abs(va) > 0 and abs(soma - va) / abs(va) > tol:
            falhas.append(nome)

    ident("ebitda", [("ebit", 1.0), ("d_a", 1.0)], "EBITDA ≠ EBIT + D&A")
    if _f(pac.get("t.capex")) is not None and _f(pac.get("t.capex")) < 0:  # type: ignore[operator]
        ident("fcf", [("cfo", 1.0), ("capex", 1.0)], "FCF ≠ CFO − capex")
    else:
        ident("fcf", [("cfo", 1.0), ("capex", -1.0)], "FCF ≠ CFO − capex")
    ident("patrimonio_liquido", [("patrimonio_controladores", 1.0), ("participacao_minoritarios", 1.0)],
          "PL ≠ controladores + minoritários")
    out.append(_portao("G1", "Identidades contábeis", None if not pac.get("tem_demonstrativos") else not falhas,
                       "aviso", "; ".join(falhas) or "identidades conferidas onde publicadas"))
    # G2 point-in-time
    mx = pac.get("max_data_publicacao")
    ok2 = None if mx is None else mx <= pac["as_of"]
    out.append(_portao("G2", "Insumos publicados até a data", ok2, "bloqueio",
                       f"publicação mais recente: {mx}" if mx else "sem demonstrativos"))
    tem = bool(mod.get("tem_alvo"))
    # G3 finito
    out.append(_portao("G3", "Valor finito", tem if mod.get("metodos") else None, "sem_alvo",
                       mod.get("motivo_sem_alvo") or "valor intrínseco e preço-alvo finitos"))
    # G5 perpetuidade e valor terminal
    fts = [_f(m.get("fracao_terminal")) for m in mod.get("metodos", []) if m.get("valor") is not None]
    fts = [x for x in fts if x is not None]
    mx_ft = max(fts) if fts else None
    ok5 = None if mx_ft is None else mx_ft <= float(q["tv_aviso"])
    out.append(_portao("G5", "Perpetuidade e valor terminal", ok5, "aviso",
                       "sem método com valor terminal" if mx_ft is None else f"maior fração terminal: {pct(mx_ft, 0)}"))
    # G6 ordem dos cenários
    if tem:
        tp, b, p = _f(mod.get("tp")), _f(mod.get("tp_otimista")), _f(mod.get("tp_pessimista"))
        ok6 = None if None in (tp, b, p) else (b >= tp * 0.999 and tp >= p * 0.999)  # type: ignore[operator]
        out.append(_portao("G6", "Otimista ≥ base ≥ pessimista", ok6, "bloqueio",
                           "ordem dos cenários conferida" if ok6 else "cenários fora de ordem"))
    # G8 moeda
    st = pac.get("status_moeda")
    out.append(_portao("G8", "Coerência de moeda", st in ("ok", "fx_corrigido"), "bloqueio", f"status: {st}"))
    # G9 faixa do upside
    lo, hi = q["upside_limites"]
    if tem:
        up = _f(mod.get("upside"))
        ok9 = None if up is None else lo <= up <= hi
        out.append(_portao("G9", "Upside dentro da faixa plausível", ok9, "bloqueio",
                           f"upside {pct(up)} (faixa {pct(lo, 0)} a {pct(hi, 0)})"))
        pwr = _f(mod.get("pwr"))
        ok11 = None if pwr is None else abs(pwr) <= float(q["pwr_max_abs"])
        out.append(_portao("G11", "Retorno ponderado plausível", ok11, "bloqueio", f"PWR {pct(pwr)}"))
    # G12 defasagem do preço
    d = pac.get("defasagem_preco_dias")
    ok12 = None if d is None else d <= int(q["defasagem_max_dias"])
    out.append(_portao("G12", "Preço atualizado", ok12, "bloqueio",
                       f"{int(d)} pregão(ões) de defasagem" if d is not None else "sem preço"))
    # G13 plausibilidade dos insumos por ação (armadilha de unidade/moeda)
    if tem:
        out.append(_g13(pac, mod, params))
    # G14 FCFF do ano 1 contra o fluxo de caixa livre observado (CFO − capex)
    razao = _f(mod.get("fcff_ano1_vs_observado"))
    obs, fc1 = _f(mod.get("fcf_observado")), _f(mod.get("fcff_ano1"))
    lim_anos = [a for a in (mod.get("reinvestimento_limitado_anos") or []) if a <= 2]
    if tem and fc1 is not None and obs is not None:
        lo14, hi14 = q.get("fcff_observado_faixa", [0.5, 2.0])
        if obs > 0:
            ok14 = razao is not None and lo14 <= razao <= hi14
            det = f"FCFF do ano 1 = {num(razao)} × (CFO − capex) observado (faixa {num(lo14, 1)} a {num(hi14, 1)})"
        else:
            ok14 = fc1 <= 0
            det = ("fluxo de caixa livre observado não positivo e FCFF do ano 1 também não positivo" if ok14 else
                   "fluxo de caixa livre observado não positivo, mas o modelo projeta FCFF positivo no ano 1")
        if lim_anos:
            det += f"; reinvestimento limitado nos anos {', '.join(str(a) for a in lim_anos)}"
        out.append(_portao("G14", "Fluxo de caixa do ano 1 coerente com o observado", ok14, "aviso", det))
    # G15 mesma data-base de fluxos e balanço
    dd = pac.get("defasagem_fluxos_dias")
    if dd is not None:
        lim15 = int(q.get("defasagem_fluxos_max_dias", 100))
        out.append(_portao("G15", "Fluxos e balanço na mesma data-base", int(dd) <= lim15, "aviso",
                           f"fluxos de 12 meses {int(dd)} dias anteriores ao último balanço (limite {lim15})"))
    return out


def _g13(pac: Mapping[str, Any], mod: Mapping[str, Any], params: ParametrosCobertura) -> dict[str, Any]:
    """Insumos por ação plausíveis: P/VPA, ROE do ano 1 e coerência do LPA (bloqueio)."""
    q = params.sec("qualidade")
    lo, hi = q.get("pb_plausivel", [0.1, 15.0])
    roe_max = float(q.get("roe1_max_abs", 1.0))
    excecoes = set(q.get("excecoes_insumos", []) or [])
    peso_pat = _f(mod.get("peso_patrimonial")) or 0.0
    falhas = []
    if pac.get("issuer_id") not in excecoes and peso_pat > 0:
        p0, b0 = _f(pac.get("preco")), _f(mod.get("b0"))
        if p0 is not None and b0 is not None and b0 > 0:
            pb = p0 / b0
            if not lo <= pb <= hi:
                falhas.append(f"P/VPA de {num(pb)}x fora de [{num(lo, 1)}; {num(hi, 0)}] (provável unidade ou moeda "
                              "do patrimônio)")
        roe1 = _f(mod.get("roe1"))
        if roe1 is not None and abs(roe1) > roe_max:
            falhas.append(f"ROE do ano 1 de {pct(roe1, 0)} acima de {pct(roe_max, 0)} em módulo")
    if mod.get("lpa_diverge") and peso_pat > float(q.get("peso_patrimonial_lpa", 0.5)) \
            and pac.get("issuer_id") not in excecoes:
        falhas.append("LPA de consenso incoerente com o lucro de 12 meses em modelo com métodos patrimoniais "
                      f"respondendo por {pct(peso_pat, 0)} do peso")
    if peso_pat <= 0 and not mod.get("lpa_diverge"):
        return _portao("G13", "Insumos por ação plausíveis", None, "bloqueio", "sem método patrimonial")
    return _portao("G13", "Insumos por ação plausíveis", not falhas, "bloqueio",
                   "; ".join(falhas) or "P/VPA, ROE do ano 1 e LPA coerentes")


def portoes_transversais(modelos: dict[str, dict[str, Any]], pacotes: Mapping[str, Mapping[str, Any]],
                         params: ParametrosCobertura) -> None:
    """G4 (envelope de ke dos demais emissores do país × setor, ± tolerância; informativo) e G10
    (largura dos cenários) — in place."""
    grupos: dict[str, list[tuple[str, float]]] = {}
    for iid, m in modelos.items():
        k = _f(m.get("custo_capital", {}).get("ke"))
        if k is not None:
            grupos.setdefault(f"{pacotes[iid]['pais']}|{pacotes[iid]['setor']}", []).append((iid, k))
    larg = [x for x in (_f(m.get("largura_cenarios")) for m in modelos.values()) if x is not None]
    p25, p75 = (float(np.percentile(larg, 25)), float(np.percentile(larg, 75))) if len(larg) >= 8 else (None, None)
    lo_w, hi_w = params.sec("qualidade")["largura_cenario"]
    tol = float(params.sec("qualidade").get("envelope_ke_tolerancia", 0.01))
    for iid, m in modelos.items():
        outros = [k for j, k in grupos.get(f"{pacotes[iid]['pais']}|{pacotes[iid]['setor']}", []) if j != iid]
        k = _f(m.get("custo_capital", {}).get("ke"))
        if k is not None and len(outros) >= 4:
            p10, p90 = float(np.percentile(outros, 10)), float(np.percentile(outros, 90))
            ok = p10 - tol - 1e-12 <= k <= p90 + tol + 1e-12
            det = (f"ke {pct(k)} vs envelope dos outros {len(outros)} emissores {pct(p10)}–{pct(p90)} "
                   f"(tolerância de {pct(tol, 0)})")
        else:
            ok, det = None, "menos de 4 outros emissores no país × setor"
        m["portoes"].append(_portao("G4", "ke no envelope dos pares", ok, "informativo", det))
        w = _f(m.get("largura_cenarios"))
        if w is not None and p25 is not None:
            okw = (float(lo_w) * p25) <= w <= (float(hi_w) * p75)
            m["portoes"].append(_portao("G10", "Largura dos cenários", okw, "aviso",
                                        f"largura {pct(w, 0)} (universo P25 {pct(p25, 0)}, P75 {pct(p75, 0)})"))


def portoes_etf(e: Mapping[str, Any], params: ParametrosCobertura) -> list[dict[str, Any]]:
    """Portões do ETF (E1–E4; ver docstring do módulo)."""
    q = params.sec("qualidade")
    out = []
    tp, p0, re_ = _f(e.get("preco_alvo")), _f(e.get("preco")), _f(e.get("retorno_esperado"))
    out.append(_portao("E1", "Preço-alvo finito e positivo", None if p0 is None else (tp is not None and tp > 0),
                       "bloqueio", "preço-alvo do ETF" if tp is not None else "sem preço-alvo"))
    lo, hi = q.get("etf_retorno_limites", [-0.5, 1.0])
    out.append(_portao("E2", "Retorno esperado plausível", None if re_ is None else lo <= re_ <= hi, "bloqueio",
                       f"retorno esperado {pct(re_)} (faixa {pct(lo, 0)} a {pct(hi, 0)})"))
    ag = e.get("agregados") or {}
    razao = _f(ag.get("pl_justificado_sobre_corrente_bruto"))
    lo3, hi3 = q.get("etf_pl_razao_limites", [0.6, 1.6])
    out.append(_portao("E3", "P/L justificado coerente com o corrente", None if razao is None else lo3 <= razao <= hi3,
                       "aviso", f"P/L justificado ÷ P/L corrente = {num(razao)} (faixa {num(lo3, 1)} a {num(hi3, 1)}; "
                                "fora dela, limitado)" if razao is not None else "top-down 1 indisponível"))
    b_lim = ag.get("payout_no_limite")
    out.append(_portao("E4", "Top-down com componentes plausíveis", None if b_lim is None else not b_lim, "bloqueio",
                       "payout sustentável do índice no limite do intervalo" if b_lim else
                       "payout sustentável, crescimento e retorno do índice dentro dos limites"))
    return out


def bloqueios(portoes: list[dict[str, Any]]) -> list[str]:
    return [p["codigo"] for p in portoes if p["status"] == "bloqueio"]


def avisos(portoes: list[dict[str, Any]]) -> list[str]:
    return [p["codigo"] for p in portoes if p["status"] == "aviso"]


__all__ = ["avisos", "bloqueios", "portoes_emissor", "portoes_etf", "portoes_transversais"]
