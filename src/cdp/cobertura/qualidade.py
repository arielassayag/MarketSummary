"""Portões de qualidade da cobertura (determinísticos; bloqueio ⇒ rating "Em revisão").

| Portão | Regra | Efeito |
|---|---|---|
| G1 | identidade PL = controladores + minoritários (aviso); EBITDA = EBIT + D&A e FCF = CFO − capex (informativo: o modelo usa EBIT e CFO − capex diretamente) | aviso / informativo |
| G2 | nenhum insumo publicado depois da data do snapshot | bloqueio |
| G3 | valor intrínseco e preço-alvo finitos | sem alvo |
| G4 | ke dentro do envelope P10–P90 dos demais emissores do país × setor (± 1 p.p.) | informativo |
| G5 | g ≤ rf local, ke − g ≥ 3 p.p.; valor terminal ≤ 85% (aviso) / 95% (método excluído) | aviso |
| G6 | otimista ≥ base ≥ pessimista | bloqueio |
| G7 | resíduo da ponte do alvo ≤ 0,5% do alvo | aviso |
| G8 | moeda dos insumos coerente (ok ou corrigida pelo câmbio) | bloqueio |
| G9 | preço-alvo ÷ preço − 1 dentro de [−70%; +200%] (única faixa de magnitude bloqueante) | bloqueio |
| G10 | largura dos cenários dentro de [0,5 × P25; 2 × P75] do universo | informativo |
| G11 | retorno extremo no caso-base, simétrico em log: fora de [−50%; +100%] só citável (aviso, C) se corroborado por ≥ 3 métodos calculados (discrepante limitado e não positivos contam como dissidência) do mesmo lado com CV ≤ 50%, ou pelo consenso público plausível do mesmo lado com |upside| ≥ 25% e magnitude compatível (diferença em log ≤ 0,4); senão bloqueio | aviso / bloqueio |
| G12 | preço com no máximo 5 pregões de defasagem | bloqueio |
| G13 | insumos por ação plausíveis (P/VPA em [0,1; 15], ROE_1 em módulo ≤ 100%, LPA de consenso coerente com o lucro de 12 meses quando métodos patrimoniais pesam > 50%) — armadilha de unidade/moeda | bloqueio |
| G13b | consenso e margens plausíveis: LPA ÷ preço ≤ 50% nos anos 1 e 2, ROE_2 em módulo ≤ 100%, margem EBIT ≤ 100% (fora holdings e imobiliárias) | bloqueio |
| G13c | contagem de ações conciliada: duas de três fontes (demonstrações, valor de mercado público, Formulário de Referência da CVM) a ±10%; sem a oficial, divergência entre duas fontes ⇒ aviso | bloqueio / aviso |
| G14 | reinvestimento observado (3 exercícios) acima de −100% do NOPAT; abaixo (CFO com operações financeiras) ⇒ aviso e mediana do setor nos anos 1–2; FCFF do ano 1 contra o fluxo observado e anos limitados exibidos | aviso / informativo |
| G15 | fluxos de 12 meses e balanço na mesma data-base (defasagem ≤ 100 dias) | aviso |
| G16 | patrimônio residual robusto: P(valor do patrimônio ≤ 0) nos sorteios < 10% | aviso |
| G18 | métodos coerentes: com ≥ 3 métodos, o que ficar fora de [1/3; 3] × a mediana dos demais (o mais distante) é limitado à borda (demais com CV ≤ 10%, fora do lado do preço) ou mantido; limita a B | aviso |
| G19 | demonstrações recentes: último balanço ou fluxos de 12 meses com mais de 300 dias na data ⇒ aviso; mais de 550 ⇒ bloqueio | aviso / bloqueio |
| G17 | alertas da fonte pública sobre os períodos e itens usados (item em conferência, salto de magnitude ou classificação de capex a conferir, troca recente de moeda de apresentação) | aviso / informativo |

"Informativo": exibido no modelo aberto, sem efeito na confiança nem no rating. "Aviso": rebaixa a
confiança para C (sem Compra ou Venda), salvo os que só limitam a B (G15, G18; ``rating.avisos_limitam_b``).
"Bloqueio": rating "Em revisão" e preço-alvo não citável.

ETFs (``portoes_etf``): E1 preço-alvo finito e positivo; E2 retorno esperado em [−50%; +100%];
E3 P/L justificado ÷ P/L corrente dentro de [0,6; 1,6] (aviso); E4 top-down com componentes
plausíveis (bloqueio quando o payout do índice fica no limite do intervalo); E5 nenhuma posição
contribuindo mais que 5 p.p. ao bottom-up além do top-down, ``w × (r − R_TD)`` (aviso).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
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
    informativas = list(falhas)
    falhas.clear()
    ident("patrimonio_liquido", [("patrimonio_controladores", 1.0), ("participacao_minoritarios", 1.0)],
          "PL ≠ controladores + minoritários")
    if not pac.get("tem_demonstrativos"):
        out.append(_portao("G1", "Identidades contábeis", None, "aviso", "sem demonstrativos"))
    elif falhas:
        out.append(_portao("G1", "Identidades contábeis", False, "aviso",
                           "; ".join(falhas + informativas) + " (o patrimônio entra nos métodos)"))
    elif informativas:
        out.append(_portao("G1", "Identidades contábeis", False, "informativo",
                           "; ".join(informativas) + " (itens publicados não usados pelo modelo, que parte do EBIT e "
                           "de CFO − capex)"))
    else:
        out.append(_portao("G1", "Identidades contábeis", True, "aviso", "identidades conferidas onde publicadas"))
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
        out.append(_g11(pac, mod, params))
    # G12 defasagem do preço
    d = pac.get("defasagem_preco_dias")
    ok12 = None if d is None else d <= int(q["defasagem_max_dias"])
    out.append(_portao("G12", "Preço atualizado", ok12, "bloqueio",
                       f"{int(d)} pregão(ões) de defasagem" if d is not None else "sem preço"))
    # G13 plausibilidade dos insumos por ação (armadilha de unidade/moeda)
    if tem:
        out.append(_g13(pac, mod, params))
        out.append(_g13b(pac, mod, params))
    out.append(_g13c(pac))
    # G14 reinvestimento observado (CFO contaminado por operações financeiras) e FCFF do ano 1
    fc1 = _f(mod.get("fcff_ano1"))
    rr = _f(mod.get("rr_observado"))
    lim_anos = [a for a in (mod.get("reinvestimento_limitado_anos") or []) if a <= 2]
    if tem and fc1 is not None and rr is not None:
        rr_min = float(q.get("rr_observado_min", -1.0))
        razao = _f(mod.get("fcff_ano1_vs_observado"))
        det = (f"reinvestimento observado {pct(rr, 0)} do NOPAT ({mod.get('rr_observado_base') or 'n/d'}); "
               f"FCFF do ano 1 = " + (f"{num(razao)} × (CFO − capex) dos últimos 12 meses" if razao is not None
                                      else "n/d (CFO − capex não positivo)"))
        if lim_anos:
            det += f"; reinvestimento limitado nos anos {', '.join(str(a) for a in lim_anos)}"
        if rr < rr_min:
            out.append(_portao("G14", "Reinvestimento observado plausível", False, "aviso",
                               det + f"; abaixo de {pct(rr_min, 0)}: CFO − capex acima de 2 × NOPAT (operações "
                                     "financeiras ou liberação pontual de capital de giro no CFO); anos 1–2 pela "
                                     "mediana do setor"))
        else:
            out.append(_portao("G14", "Reinvestimento observado plausível", True, "aviso", det))
    # G15 mesma data-base de fluxos e balanço
    dd = pac.get("defasagem_fluxos_dias")
    if dd is not None:
        lim15 = int(q.get("defasagem_fluxos_max_dias", 100))
        out.append(_portao("G15", "Fluxos e balanço na mesma data-base", int(dd) <= lim15, "aviso",
                           f"fluxos de 12 meses {int(dd)} dias anteriores ao último balanço (limite {lim15})"))
    # G16 patrimônio residual robusto (piso de zero relevante nos sorteios)
    pz = _f(mod.get("p_patrimonio_zero"))
    if tem and pz is not None:
        lim16 = float(q.get("p_patrimonio_zero_max", 0.10))
        out.append(_portao("G16", "Patrimônio residual robusto", pz < lim16, "aviso",
                           f"probabilidade de patrimônio não positivo nos sorteios = {pct(pz, 1)} (limite {pct(lim16, 0)}); "
                           f"retorno com responsabilidade limitada {pct(_f(mod.get('pwr_com_piso')))} contra "
                           f"{pct(_f(mod.get('pwr')))} sem o piso"))
    out.append(_g17(pac, mod, params))
    # G18 métodos coerentes (método discrepante excluído da média)
    if tem:
        dsc = mod.get("metodo_discrepante")
        if dsc:
            from .parametros import NOME_METODO

            nome = NOME_METODO.get(dsc["metodo"], dsc["metodo"])
            cab = (f"{nome} = {num(dsc['razao'], 2)} × a mediana dos demais métodos (fora de "
                   f"[1/{num(dsc['fator'], 0)}; {num(dsc['fator'], 0)}])")
            if dsc.get("limitado"):
                det = (f"{cab}, com os demais concordando (CV {pct(dsc.get('cv_demais'), 0)}): limitado à borda do "
                       "intervalo na combinação")
            elif dsc.get("lado_preco"):
                det = f"{cab}, do lado do preço: mantido na média (dissidência a favor do mercado)"
            else:
                det = (f"{cab}, com os demais sem consenso (CV {pct(dsc.get('cv_demais'), 0)}): mantido na média")
            cvt = _f(mod.get("cv_todos"))
            det += (f"; confiança limitada a B, e C se a dispersão entre todos os métodos calculados passar de "
                    f"{pct(params.sec('qualidade')['cv_metodos_c'], 0)}"
                    + (f" (hoje {pct(cvt, 0)})" if cvt is not None else ""))
            out.append(_portao("G18", "Métodos coerentes", False, "aviso", det))
        else:
            out.append(_portao("G18", "Métodos coerentes", True, "aviso",
                               "nenhum método fora de [1/3; 3] × a mediana dos demais"))
    # G19 demonstrações recentes (idade do último balanço e dos fluxos de 12 meses contra a data)
    out.append(_g19(pac, params))
    return out


def _valores_calculados(mod: Mapping[str, Any]) -> list[float]:
    """Valores de TODOS os métodos calculados: o bruto do discrepante limitado e os não positivos
    (dissidência), nunca só os que sobraram na média."""
    out = []
    for m in mod.get("metodos", []):
        v = _f(m.get("valor_bruto")) if m.get("valor_bruto") is not None else _f(m.get("valor"))
        if v is None:
            v = _f(m.get("valor_calculado"))
        if v is not None:
            out.append(v)
    return out


def _g11(pac: Mapping[str, Any], mod: Mapping[str, Any], params: ParametrosCobertura) -> dict[str, Any]:
    """Retorno extremo no caso-base (ETR), simétrico em log. Fora da faixa de aviso, o alvo só é
    citável (com confiança C) se corroborado: por ≥ 3 métodos calculados — inclusive os limitados
    ou não positivos, que contam como dissidência — todos do mesmo lado do preço com CV ≤ 50%, ou
    pelo consenso público plausível do mesmo lado com |upside| ≥ 25% e magnitude compatível
    (``||ln(1 + ETR)| − |ln(1 + upside do consenso)|| ≤ 0,4``). Sem corroboração ⇒ bloqueio."""
    q = params.sec("qualidade")
    etr = _f(mod.get("etr"))
    if etr is None or etr <= -1:
        return _portao("G11", "Retorno extremo corroborado", None, "bloqueio", "sem retorno do caso-base")
    x = abs(math.log1p(etr))
    lo_a, hi_a = (float(v) for v in q["extremo_aviso"])
    lo_b, hi_b = (float(v) for v in q["extremo_bloqueio"])
    lim_a = max(abs(math.log1p(lo_a)), abs(math.log1p(hi_a)))
    lim_b = max(abs(math.log1p(lo_b)), abs(math.log1p(hi_b)))
    base = f"ETR {pct(etr, 1, True)} (|ln(1 + ETR)| = {num(x)}; aviso acima de {num(lim_a)}, faixa larga até {num(lim_b)})"
    if x <= lim_a:
        return _portao("G11", "Retorno extremo corroborado", True, "aviso", base)
    p0 = _f(pac.get("preco"))
    s = 1 if etr > 0 else -1
    vals = _valores_calculados(mod)
    cv = _f(mod.get("cv_todos")) if mod.get("cv_todos") is not None else _f(mod.get("cv"))
    cvmax = float(q.get("corroboracao_cv_max", 0.5))
    n_min = int(q.get("corroboracao_metodos_min", 3))
    metodos_ok = (p0 is not None and len(vals) >= n_min and all((v / p0 - 1) * s > 0 for v in vals)
                  and cv is not None and cv <= cvmax)
    c = pac.get("consenso") or {}
    cu = _f(c.get("upside"))
    cmin = float(q.get("corroboracao_consenso_min", 0.25))
    dlog = float(q.get("corroboracao_consenso_dlog_max", 0.4))
    dif = None if cu is None or cu <= -1 else abs(x - abs(math.log1p(cu)))
    cons_ok = bool(c.get("plausivel")) and cu is not None and cu * s >= cmin and dif is not None and dif <= dlog
    corrob = []
    if metodos_ok:
        corrob.append(f"{len(vals)} métodos calculados do mesmo lado do preço com CV {pct(cv, 0)}")
    if cons_ok:
        corrob.append(f"consenso público do mesmo lado e de magnitude compatível (upside {pct(cu, 0, True)}; "
                      f"diferença em log {num(dif)})")
    if corrob:
        faixa = "retorno elevado" if x <= lim_b else "retorno muito elevado"
        return _portao("G11", "Retorno extremo corroborado", False, "aviso",
                       base + f"; {faixa}, corroborado: {'; '.join(corrob)} ⇒ confiança C, fora da mediana dos pares")
    falta = []
    if not metodos_ok:
        falta.append(f"métodos sem corroboração ({len(vals)} calculado(s)" + (f", CV {pct(cv, 0)}" if cv is not None else "")
                     + (", nem todos do mesmo lado do preço" if p0 is not None and vals
                        and not all((v / p0 - 1) * s > 0 for v in vals) else "") + ")")
    if not cons_ok:
        if cu is None or not c.get("plausivel"):
            falta.append("consenso público ausente ou implausível")
        elif cu * s < cmin:
            falta.append(f"consenso público do outro lado ou fraco (upside {pct(cu, 0, True)})")
        else:
            falta.append(f"consenso público com magnitude incompatível (upside {pct(cu, 0, True)}; diferença em log "
                         f"{num(dif)} acima de {num(dlog)})")
    return _portao("G11", "Retorno extremo corroborado", False, "bloqueio", base + "; sem corroboração: " + "; ".join(falta))


def _g19(pac: Mapping[str, Any], params: ParametrosCobertura) -> dict[str, Any]:
    """Demonstrações recentes: último balanço e fluxos de 12 meses com no máximo ``idade_aviso_dias``
    contra a data do snapshot (aviso: confiança C); acima de ``idade_bloqueio_dias``, bloqueio."""
    q = params.sec("qualidade")
    ib, iflx = pac.get("idade_balanco_dias"), pac.get("idade_fluxos_dias")
    if ib is None and iflx is None:
        return _portao("G19", "Demonstrações recentes", None, "aviso", "sem demonstrações")
    lim_a = int(q.get("idade_aviso_dias", 300))
    lim_b = int(q.get("idade_bloqueio_dias", 550))
    idade = max(x for x in (ib, iflx) if x is not None)
    det = (f"balanço de {pac.get('data_balanco') or 'n/d'} ({ib if ib is not None else 'n/d'} dias) e fluxos de 12 meses até "
           f"{pac.get('data_fluxos') or 'n/d'} ({iflx if iflx is not None else 'n/d'} dias) na data do snapshot; aviso acima "
           f"de {lim_a} dias, bloqueio acima de {lim_b}")
    if idade > lim_b:
        return _portao("G19", "Demonstrações recentes", False, "bloqueio", det)
    return _portao("G19", "Demonstrações recentes", idade <= lim_a, "aviso", det)


def _g13b(pac: Mapping[str, Any], mod: Mapping[str, Any], params: ParametrosCobertura) -> dict[str, Any]:
    """Consenso e margens plausíveis (armadilha de moeda/unidade no LPA de consenso; EBIT com
    resultado de participações)."""
    q = params.sec("qualidade")
    falhas = []
    p0 = _f(pac.get("preco"))
    ep_max = float(q.get("ep_consenso_max", 0.5))
    if p0 and p0 > 0:
        for k, rot in (("eps_fy1", "ano 1"), ("eps_fy2", "ano 2")):
            e = _f(pac.get(k))
            if e is not None and e / p0 > ep_max:
                falhas.append(f"LPA de consenso do {rot} = {pct(e / p0, 0)} do preço (acima de {pct(ep_max, 0)}; "
                              "P/L abaixo de 2)")
    roe2 = _f(mod.get("roe2"))
    if roe2 is not None and abs(roe2) > float(q.get("roe2_max_abs", 1.0)) and pac.get("issuer_id") not in set(
            q.get("excecoes_insumos", []) or []):
        falhas.append(f"ROE do ano 2 de {pct(roe2, 0)} acima de {pct(q.get('roe2_max_abs', 1.0), 0)} em módulo")
    mg = _f(mod.get("margem"))
    mg_max = float(q.get("margem_ebit_max", 1.0))
    if mg is not None and mg > mg_max and pac.get("arquetipo") not in ("holding", "imobiliario"):
        falhas.append(f"margem EBIT de {pct(mg, 0)} acima de {pct(mg_max, 0)} (resultado de participações ou item "
                      "não operacional no EBIT)")
    return _portao("G13b", "Consenso e margens plausíveis", not falhas, "bloqueio",
                   "; ".join(falhas) or "LPA de consenso, ROE do ano 2 e margem EBIT plausíveis")


def _g13c(pac: Mapping[str, Any]) -> dict[str, Any]:
    """Contagem de ações conciliada entre fontes (ver :func:`cdp.cobertura.insumos.conciliar_contagem`).
    Sem nenhuma contagem e sem item total convertido por ação (insumos por ação do retrato público),
    o portão não se aplica."""
    c = pac.get("contagem") or {}
    st = c.get("status")
    if st is None:
        return _portao("G13c", "Contagem de ações conciliada", None, "bloqueio", "sem conciliação registrada")
    if pac.get("unidades") is None and pac.get("eps_ttm") is None and pac.get("divida_liquida") is None:
        return _portao("G13c", "Contagem de ações conciliada", None, "bloqueio",
                       "nenhuma contagem usada: patrimônio e lucro por ação do retrato público, sem item total "
                       "convertido por ação")
    if st == "ok":
        return _portao("G13c", "Contagem de ações conciliada", True, "bloqueio", str(c.get("detalhe")))
    return _portao("G13c", "Contagem de ações conciliada", False, "bloqueio" if st == "bloqueio" else "aviso",
                   str(c.get("detalhe")))


def rotulo_item(item: str) -> str:
    from .insumos import rotulo

    return rotulo(item)


def _g17(pac: Mapping[str, Any], mod: Mapping[str, Any], params: ParametrosCobertura) -> dict[str, Any]:
    """Alertas da fonte pública sobre os períodos e itens usados pelo modelo."""
    q = params.sec("qualidade")
    janela = int(q.get("qa_janela_dias", 400))
    # itens que movem o valor diretamente; saltos de caixa e aplicações (reclassificações entre si,
    # neutras na dívida líquida) e alertas de classificação do capex ficam informativos
    nucleo = {"receita", "ebit", "lucro_liquido_controladores", "lucro_liquido", "patrimonio_controladores",
              "patrimonio_liquido", "cfo", "capex", "d_a", "divida_bruta", "acoes_em_circulacao"}
    ref = pac.get("max_data_publicacao") or pac.get("as_of")
    avisos, infos = [], []
    for c in pac.get("em_conferencia") or []:
        avisos.append(f"{rotulo_item(c['item'])} em conferência na fonte em {c['data']} (valor do período ausente)")
    for a in pac.get("alertas_fonte") or []:
        tipo, txt, d, item = a.get("tipo"), str(a.get("texto")), a.get("data"), a.get("item")
        recente = bool(d and ref and (date.fromisoformat(str(ref)[:10]) - date.fromisoformat(str(d)[:10])).days <= janela)
        if tipo == "moeda_trocada":
            n = len((pac.get("historico") or {}).get("receita") or {})
            if n < int(q.get("moeda_trocada_min_anos", 3)):
                avisos.append(f"{txt}: {n} exercício(s) na moeda nova; insumos históricos indisponíveis")
            else:
                infos.append(txt)
        elif recente and item in nucleo and tipo == "salto":
            avisos.append(f"salto de magnitude a conferir na fonte: {txt}")
        else:
            infos.append(txt)
    if avisos:
        return _portao("G17", "Alertas da fonte pública", False, "aviso",
                       "; ".join(avisos[:4]) + (f" (e mais {len(avisos) - 4})" if len(avisos) > 4 else ""))
    if infos:
        return _portao("G17", "Alertas da fonte pública", False, "informativo",
                       f"{len(infos)} alerta(s) da fonte fora dos períodos ou itens usados; ex.: {infos[0]}")
    return _portao("G17", "Alertas da fonte pública", True, "aviso", "sem alertas da fonte sobre os períodos usados")


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
            m["portoes"].append(_portao("G10", "Largura dos cenários", okw, "informativo",
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
    cb = e.get("concentracao_bu") or {}
    c = _f(cb.get("contribuicao"))
    lim = _f(cb.get("limite"))
    out.append(_portao("E5", "Bottom-up sem concentração em uma posição", None if c is None or lim is None else c <= lim,
                       "aviso", "sem posições com alvo da casa" if c is None else
                       f"maior contribuição de uma posição além do top-down: {cb.get('emissor')} com {pct(c, 1)} "
                       f"(limite {pct(lim, 0)})"))
    return out


def bloqueios(portoes: list[dict[str, Any]]) -> list[str]:
    return [p["codigo"] for p in portoes if p["status"] == "bloqueio"]


def avisos(portoes: list[dict[str, Any]]) -> list[str]:
    return [p["codigo"] for p in portoes if p["status"] == "aviso"]


__all__ = ["avisos", "bloqueios", "portoes_emissor", "portoes_etf", "portoes_transversais"]
