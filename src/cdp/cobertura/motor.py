"""Orquestração de uma execução da cobertura (todas as ações e ETFs do universo).

Etapas (todas determinísticas):

1. dados públicos da data (``fontes.coletar``) e pacotes de insumos por emissor;
2. contexto transversal (medianas, β das financeiras, regressões de múltiplos);
3. modelo de cada emissor (custo de capital, métodos, combinação, rolagem, cenários,
   sensibilidade, diagnósticos), portões de qualidade individuais e a ponte do preço-alvo contra
   o snapshot anterior (portão G7) — todos antes do rating;
4. portões transversais, classes de incerteza, pares, ``α_rel``, confiança e rating
   (com histerese contra o snapshot anterior; numa execução parcial, os pares não reavaliados
   entram com o α publicado);
5. alvos das demais linhas do emissor;
6. ETFs (bottom-up pelos alvos da casa + top-down), a partir de pacotes de insumos arquivados.

Os números saem só daqui; os JSON resultantes trazem os passos com fórmula e substituição.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..market import MarketData
from . import metodos as M
from .contexto import montar_contexto
from .etf import avaliar_etfs
from .fontes import DadosPublicos
from .formato import pct, pp, preco, r6, valor
from .insumos import fx_usd, preparar, taxa_publica, ultimo_preco
from .modelo import Avaliador
from .parametros import ParametrosCobertura
from .ponte import ponte
from .qualidade import bloqueios, portoes_emissor, portoes_transversais
from .rating import aplicar

SCHEMA_MODELO = "cdp.cobertura.modelo/v1"
AVISO_REAL = "dados públicos (CVM, SEC, RI, Yahoo Finance, BCB, FRED, Damodaran)"


def arredondar(obj: Any) -> Any:
    """Arredonda recursivamente floats a 6 algarismos significativos (NaN/inf ⇒ ``None``)."""
    if isinstance(obj, float):
        return r6(obj)
    if isinstance(obj, (np.floating,)):
        return r6(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, dict):
        return {str(k): arredondar(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [arredondar(v) for v in obj]
    return obj


@dataclass
class Anterior:
    """Estado anterior por instrumento (histerese do rating e ponte do preço-alvo).

    ``estado[iid] = (pacote, contexto, rf)`` do snapshot que produziu o último evento do emissor."""

    ratings: dict[str, str] = field(default_factory=dict)
    alvos: dict[str, float] = field(default_factory=dict)
    alphas: dict[str, float | None] = field(default_factory=dict)
    estado: dict[str, tuple[dict[str, Any], dict[str, Any], float | None]] = field(default_factory=dict)
    eventos: dict[str, dict[str, Any]] = field(default_factory=dict)
    data_completa: date | None = None
    linhas_completa: dict[str, str | None] = field(default_factory=dict)


@dataclass
class Execucao:
    as_of: date
    pacotes: dict[str, dict[str, Any]]
    contexto: dict[str, Any]
    modelos: dict[str, dict[str, Any]]
    etfs: dict[str, dict[str, Any]]
    rf: dict[str, Any]
    distribuicao: dict[str, Any]
    is_synthetic: bool
    emissores: list[str]
    registros: dict[str, Any] = field(default_factory=dict)
    insumos_etf: dict[str, dict[str, Any]] = field(default_factory=dict)
    referencias: dict[str, dict[str, Any]] = field(default_factory=dict)


def tp_deterministico(pac: Mapping[str, Any], ctx: Mapping[str, Any], params: ParametrosCobertura,
                      rf: float | None, rf_fonte: dict[str, Any] | None = None) -> float | None:
    """Preço-alvo do caso-base (sem Monte Carlo) — usado pela ponte e pela verificação."""
    av = Avaliador(pac, ctx, params, rf, rf_fonte or {})
    av.preparar_metodos()
    validos = av.metodos_validos()
    p0 = pac.get("preco")
    if not validos or p0 is None or av.dps12 is None:
        return None
    from .modelo import Drivers

    vals = {m: np.asarray(av._valor_metodo(m, Drivers()), dtype=float) for m in validos}
    v0 = av.combinar(vals)
    return float(M.rolagem(v0, av.cc.ke, av.dps12))


_CLASSE_PT = {"on": "ON", "ordinaria": "ON", "ordinárias": "ON", "ordinarias": "ON",
              "ordinária": "ON", "pn": "PN", "preferencial": "PN", "preferenciais": "PN",
              "unit": "UNIT", "units": "UNIT"}


def _classe(texto: str) -> str | None:
    return _CLASSE_PT.get(str(texto).strip().lower())


def classe_da_linha(lines: pd.DataFrame, ticker: str) -> str | None:
    """Classe da ação (ON, PN, UNIT) de uma linha, pela curadoria do universo (``notes``).

    Linha local: "classe ON"/"classe preferencial". ADR ou listagem externa: a razão declarada
    para o próprio ticker ("PBR=2 ON, PBR-A=2 PN", "CIB = 4 preferenciais"). Sem a indicação,
    ``None`` (a classe não é inferida)."""
    import re

    notas = str(lines.loc[ticker].get("notes", "") or "")
    if str(lines.loc[ticker, "line_type"]) == "LOCAL":
        m = re.search(r"classe\s+(\w+)", notas, flags=re.IGNORECASE)
        return _classe(m.group(1)) if m else None
    sym = re.escape(str(ticker))
    m = re.search(rf"(?<![\w-]){sym}\s*=\s*\d+(?:[.,]\d+)?\s+(\w+)", notas, flags=re.IGNORECASE)
    return _classe(m.group(1)) if m else None


def linha_local_da_classe(lines: pd.DataFrame, ticker: str) -> str | None:
    """Linha local da mesma classe da linha externa ``ticker`` (ex.: PBR → PETR3), ou ``None``."""
    cls = classe_da_linha(lines, ticker)
    if cls is None:
        return None
    locais = [t for t in lines.index if str(lines.loc[t, "line_type"]) == "LOCAL"
              and classe_da_linha(lines, t) == cls]
    return sorted(locais)[0] if len(locais) == 1 else None


def _alvos_linhas(md: MarketData, params: ParametrosCobertura, pac: Mapping[str, Any], mod: Mapping[str, Any],
                  as_of: date) -> list[dict[str, Any]]:
    """Preço-alvo de cada linha do emissor a partir do alvo da linha de valuation.

    - mesma moeda (outra classe ou unidade): ``TP × (preço da linha ÷ preço da linha de
      valuation)`` — a razão de preços corrente entre as classes é mantida (o modelo não projeta o
      prêmio ou desconto entre classes);
    - outra moeda (ADR, listagem estrangeira): ``TP da classe subjacente × (câmbio esperado em 12
      meses pela inflação relativa) × (ações por linha)``. A classe subjacente vem da curadoria do
      universo (ex.: PBR = 2 ON ⇒ alvo da PETR3; PBR-A = 2 PN ⇒ alvo da PETR4): emissor com dois
      ADRs de classes diferentes nunca recebe o mesmo alvo nos dois."""
    from .insumos import acoes_por_linha

    if not mod.get("tem_alvo"):
        return []
    infl = params.cc["inflacao_lp"]
    pi_us = float(infl["USD"])
    lv = str(pac["linha"])
    a_v, _ = acoes_por_linha(md, params, pac["issuer_id"], lv)
    fx_v, _ = fx_usd(md, pac["moeda"], as_of)
    p_v = _f(pac.get("preco"))
    out = []
    for t in pac["linhas"]:
        ln = md.universe.lines.loc[t]
        ccy = str(ln["currency"])
        p, d = ultimo_preco(md, t, as_of)
        fx_l, _ = fx_usd(md, ccy, as_of)
        if p is None or fx_l is None or fx_v is None:
            continue
        if t == lv:
            tp, conv = float(mod["tp"]), "linha de valuation"
        elif ccy == pac["moeda"] and p_v:
            tp = float(mod["tp"]) * (p / p_v)
            conv = f"TP × (preço de {t} ÷ preço de {lv}): razão corrente entre as classes mantida"
        else:
            a_l, _ = acoes_por_linha(md, params, pac["issuer_id"], t)
            f_v = fx_v * (1 + pi_us) / (1 + float(infl.get(pac["moeda"], pi_us)))
            f_l = fx_l * (1 + pi_us) / (1 + float(infl.get(ccy, pi_us)))
            base, origem = float(mod["tp"]), "TP"
            lines = md.universe.lines_for(pac["issuer_id"])
            u = linha_local_da_classe(lines, t)
            if u is not None and u != lv and str(lines.loc[u, "currency"]) == pac["moeda"] and p_v:
                p_u, _du = ultimo_preco(md, u, as_of)
                if p_u is not None:
                    base = float(mod["tp"]) * (p_u / p_v)
                    origem = f"alvo de {u} (classe subjacente: TP × preço de {u} ÷ preço de {lv})"
            tp = base * (f_v / f_l) * (a_l / a_v)
            conv = (f"{origem} × câmbio {pac['moeda']}→{ccy} esperado em 12 meses (paridade de "
                    f"inflação) × ações por linha ({a_l:g} ÷ {a_v:g})")
        out.append({"ticker": t, "tipo": str(ln["line_type"]), "moeda": ccy, "preco": r6(p),
                    "data_preco": d.isoformat() if d else None, "preco_alvo": r6(tp), "upside": r6(tp / p - 1),
                    "preco_texto": preco(p, ccy), "preco_alvo_texto": preco(tp, ccy),
                    "upside_texto": pct(tp / p - 1, 1, True), "linha_valuation": t == lv, "conversao": conv})
    return out


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _resumo(pac: Mapping[str, Any], mod: Mapping[str, Any], as_of: date) -> dict[str, Any]:
    cons = pac.get("consenso") or {}
    tp = mod.get("tp")
    diff = None
    if tp is not None and cons.get("plausivel") and cons.get("alvo_medio"):
        diff = float(tp) / float(cons["alvo_medio"]) - 1
    p0 = pac.get("preco")
    eps1, b0 = mod.get("eps1"), mod.get("b0")
    out = {
        "preco": p0, "data_preco": pac.get("data_preco"), "preco_alvo": tp, "upside": mod.get("upside"),
        "etr": mod.get("etr"), "pwr": mod.get("pwr"), "pwr_com_piso": mod.get("pwr_com_piso"),
        "p_patrimonio_zero": mod.get("p_patrimonio_zero"), "ke": mod.get("custo_capital", {}).get("ke"),
        "ke_estatico": mod.get("custo_capital", {}).get("ke_estatico"), "preco_alvo_ke_estatico": mod.get("tp_ke_estatico"),
        "alpha_rel_estilo": mod.get("alpha_rel_estilo"),
        "wacc": mod.get("custo_capital", {}).get("wacc"), "g": mod.get("custo_capital", {}).get("g"),
        "alpha": mod.get("alpha"), "alpha_rel": mod.get("alpha_rel"), "rating": mod.get("rating"),
        "rating_motivo": mod.get("rating_motivo"), "confianca": mod.get("confianca"),
        "confianca_motivo": mod.get("confianca_motivo"), "incerteza": mod.get("incerteza"),
        "alvo_otimista": mod.get("tp_otimista"), "alvo_pessimista": mod.get("tp_pessimista"),
        "prob_mercado_otimista": mod.get("prob_mercado_otimista"),
        "prob_mercado_pessimista": mod.get("prob_mercado_pessimista"),
        "prob_modelo_supera_ke": mod.get("prob_modelo_supera_ke"), "udr": mod.get("udr"),
        "assimetria": mod.get("assimetria"), "cv_metodos": mod.get("cv"), "n_metodos": mod.get("n_metodos"),
        "vencimento": (as_of + timedelta(days=365)).isoformat() if tp is not None else None,
        "consenso": cons or None, "diff_consenso": diff,
        "pl_fwd": None if p0 is None or not eps1 or eps1 <= 0 else p0 / eps1,
        "pb": None if p0 is None or not b0 or b0 <= 0 else p0 / b0,
        "proximo_resultado": pac.get("proximo_resultado"),
        "motivo_sem_alvo": mod.get("motivo_sem_alvo"),
        "alvo_citavel": bool(tp is not None and mod.get("rating") in ("Compra", "Neutro", "Venda")),
        "pit_ok": bool(pac.get("pit_ok")), "datas_estimadas": bool(pac.get("datas_estimadas")),
    }
    m = str(pac.get("moeda"))
    fmt = {"preco": f"preco:{m}", "preco_alvo": f"preco:{m}", "alvo_otimista": f"preco:{m}",
           "alvo_pessimista": f"preco:{m}", "upside": "%", "etr": "%", "pwr": "%", "ke": "%", "wacc": "%", "g": "%",
           "pwr_com_piso": "%", "p_patrimonio_zero": "prob", "ke_estatico": "%",
           "preco_alvo_ke_estatico": f"preco:{m}", "alpha_rel_estilo": "%",
           "alpha": "%", "alpha_rel": "%", "cv_metodos": "%", "diff_consenso": "%", "prob_mercado_otimista": "prob",
           "prob_mercado_pessimista": "prob", "prob_modelo_supera_ke": "prob", "pl_fwd": "x", "pb": "x", "udr": "x"}
    out["texto"] = {k: valor(out[k], u) for k, u in fmt.items()}
    for k in ("upside", "etr", "alpha", "alpha_rel", "alpha_rel_estilo", "diff_consenso"):
        out["texto"][k] = pct(out[k], 2, True)
    return out


def executar(md: MarketData, dados: DadosPublicos, params: ParametrosCobertura, as_of: date,
             emissores: Iterable[str] | None = None, anterior: Anterior | None = None) -> Execucao:
    ids = sorted(str(i) for i in md.universe.issuers.index)
    alvo_ids = sorted(set(emissores)) if emissores else ids
    desconhecidos = [i for i in alvo_ids if i not in ids]
    if desconhecidos:
        raise KeyError(f"Emissores fora do universo: {desconhecidos}")
    pacotes = preparar(md, dados, params, ids, as_of)
    rf, rf_data, rf_fonte = taxa_publica(dados, md, str(params.cc["rf_usd_serie"]), as_of)
    ctx = montar_contexto(pacotes, params, rf, rf_fonte)
    modelos, regs, dist = modelar(pacotes, ctx, params, rf, rf_fonte, anterior, alvo_ids)
    for iid in ids:
        mod, pac = modelos[iid], pacotes[iid]
        mod["alvos_linhas"] = _alvos_linhas(md, params, pac, mod, as_of)
        mod["resumo"] = _resumo(pac, mod, as_of)
    etfs, ins_etf = avaliar_etfs(md, dados, params, pacotes, modelos, rf, as_of)
    return Execucao(as_of=as_of, pacotes=pacotes, contexto=ctx, modelos=modelos, etfs=etfs,
                    rf={"valor": rf, "data": rf_data, "fonte": rf_fonte}, distribuicao=dist,
                    is_synthetic=bool(md.is_synthetic), emissores=alvo_ids, registros=regs,
                    insumos_etf=ins_etf, referencias=referencias_preco(md, pacotes, anterior, as_of))


def _ultimo(df, t: str, d: date) -> float | None:
    if t not in df.columns:
        return None
    s = df[t].loc[:pd.Timestamp(d)].dropna()
    s = s[s > 0]
    return float(s.iloc[-1]) if len(s) else None


def referencias_preco(md: MarketData, pacotes: Mapping[str, Mapping[str, Any]], anterior: Anterior | None,
                      as_of: date) -> dict[str, dict[str, Any]]:
    """Referências de preço de cada emissor para o placar, calculadas com a base de mercado da
    data (preços ajustados por proventos e desdobramentos até ``as_of``):

    - ``retorno_total_usd``: retorno total em dólar desde o último snapshot completo
      (``(P_aj,D × FX_D) ÷ (P_aj,ant × FX_ant) − 1``), mesma linha;
    - ``fator_split``: fator de desdobramento/grupamento desde o último evento do emissor,
      ``(P_ant registrado ÷ P_D) × (P_aj,D ÷ P_aj,ant)``; dentro de [0,8; 1,25] é efeito de
      proventos e o fator é 1."""
    out: dict[str, dict[str, Any]] = {}
    if anterior is None:
        return out
    for iid, pac in pacotes.items():
        t = str(pac["linha"])
        ccy = str(pac["moeda"])
        ref: dict[str, Any] = {}
        adj_d = _ultimo(md.adj_close, t, as_of)
        fx_d, _ = fx_usd(md, ccy, as_of)
        dc = anterior.data_completa
        if dc is not None and anterior.linhas_completa.get(iid) == t and adj_d is not None and fx_d is not None:
            adj_c = _ultimo(md.adj_close, t, dc)
            fx_c, _ = fx_usd(md, ccy, dc)
            if adj_c and fx_c:
                ref["retorno_total_usd"] = {"desde": dc.isoformat(), "valor": r6(adj_d * fx_d / (adj_c * fx_c) - 1)}
        ult = anterior.eventos.get(iid)
        p_d = _f(pac.get("preco"))
        if ult and ult.get("linha") == t and p_d and adj_d:
            adj_a = _ultimo(md.adj_close, t, date.fromisoformat(ult["as_of"]))
            p_a = _f(ult.get("fechamento"))
            if adj_a and p_a:
                f = (p_a / p_d) * (adj_d / adj_a)
                ref["fator_split"] = {"desde": ult["as_of"], "valor": r6(f) if not 0.8 <= f <= 1.25 else 1.0}
        out[iid] = ref
    return out


def modelar(pacotes: Mapping[str, dict[str, Any]], ctx: Mapping[str, Any], params: ParametrosCobertura,
            rf: float | None, rf_fonte: dict[str, Any], anterior: Anterior | None = None,
            alvo_ids: list[str] | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Modelos, portões e rating de todos os emissores a partir dos pacotes e do contexto
    (função pura: é o que ``cobertura verify`` refaz a partir dos insumos arquivados)."""
    ids = sorted(pacotes)
    alvo_ids = alvo_ids or ids
    modelos: dict[str, dict[str, Any]] = {}
    regs = {}
    holdings = [i for i in ids if pacotes[i].get("arquetipo") == "holding"
                and (pacotes[i].get("soma_partes") or {}).get("partes")]
    for h in holdings:  # a visão da casa sobre as participações é refeita abaixo, a partir das investidas
        pacotes[h]["soma_partes"].pop("visao_casa", None)

    def um(iid: str) -> None:
        av = Avaliador(pacotes[iid], ctx, params, rf, rf_fonte)
        mod = av.avaliar()
        mod["portoes"] = portoes_emissor(pacotes[iid], mod, params)
        mod["ponte"] = None
        if anterior and iid in anterior.alvos and mod.get("tem_alvo") and iid in anterior.estado:
            pac_a, ctx_a, rf_a = anterior.estado[iid]
            try:
                mod["ponte"] = ponte(
                    anterior.alvos[iid], pac_a, pacotes[iid], ctx_a, ctx, rf_a, rf,
                    float(mod["tp"]), lambda p, c, r: tp_deterministico(p, c, params, r))
            except Exception as exc:  # ponte é diagnóstico: nunca derruba o modelo
                mod["ponte"] = {"componentes": None, "nota": f"ponte indisponível: {type(exc).__name__}"}
            res = (mod["ponte"] or {}).get("residuo_relativo")
            lim = float(params.sec("qualidade")["ponte_residuo_max"])
            if res is not None:
                mod["portoes"].append({"codigo": "G7", "nome": "Resíduo da ponte do alvo",
                                       "status": "ok" if res <= lim else "aviso",
                                       "detalhe": f"resíduo {pct(res)} do alvo (limite {pct(lim)})"})
        modelos[iid] = mod
        regs[iid] = av.reg

    for iid in ids:
        if iid not in holdings:
            um(iid)
    for h in holdings:
        pacotes[h]["soma_partes"]["visao_casa"] = visao_casa(pacotes[h], pacotes, modelos, params)
        um(h)
    portoes_transversais(modelos, pacotes, params)
    fixos = None
    if anterior and sorted(alvo_ids) != ids:
        fixos = {j: anterior.alphas.get(j) for j in ids if j not in set(alvo_ids) and j in anterior.ratings}
    regionais = {pa for pa, c in (ctx.get("calibracao_pais") or {}).items() if c.get("grupo") == "regional"}
    dist = aplicar(modelos, pacotes, params, anterior.ratings if anterior else None, regs, fixos, regionais)
    vies = vies_modelo(ctx, params)
    dist["monitoramento"]["vies_modelo_pais"] = vies["paises"]
    dist["alertas_distribuicao"] = list(dist.get("alertas_distribuicao") or []) + vies["alertas"]
    for iid in ids:
        mod, reg = modelos[iid], regs[iid]
        bl = bloqueios(mod["portoes"])
        txt = "; ".join(f"{p['codigo']} {p['nome']}: {p['status']} ({p['detalhe']})" for p in mod["portoes"])
        reg.nota("qualidade", "Portões de qualidade", txt + (f". Bloqueio: {', '.join(bl)}." if bl else "."))
    return modelos, regs, dist


def visao_casa(pac_h: Mapping[str, Any], pacotes: Mapping[str, Mapping[str, Any]],
               modelos: Mapping[str, Mapping[str, Any]], params: ParametrosCobertura) -> dict[str, Any]:
    """Visão da casa sobre as participações listadas da holding: cada participação entra no NAV pelo
    valor intrínseco da casa (``V0 ÷ P0`` da investida × valor de mercado da participação) quando o
    modelo da investida é citável com confiança A ou B e sem aviso de retorno extremo, patrimônio
    frágil ou demonstrações defasadas; senão, a valor de mercado. ``fator = NAV da casa ÷ NAV de
    mercado`` multiplica o valor da soma das partes (o termo de reversão do desconto da holding fica
    como está). Assim a holding e as investidas não publicam visões contraditórias sobre a mesma
    exposição."""
    from .qualidade import avisos as _avisos
    from .qualidade import bloqueios as _bloqueios
    from .rating import confianca as _confianca

    excl = set(params.sec("soma_partes").get("visao_excluir_avisos") or ["G11", "G16", "G19"])
    sp = pac_h.get("soma_partes") or {}
    partes, nav_m, nav_c = [], 0.0, 0.0
    for q in sp.get("partes") or []:
        if "valor_participacao" not in q:
            continue
        sub = str(q["emissor"])
        v = float(q["valor_participacao"])
        m = modelos.get(sub)
        p = pacotes.get(sub) or {}
        razao, motivo = 1.0, "a valor de mercado"
        if m is not None and m.get("tem_alvo") and _f(m.get("v0")) and _f(p.get("preco")):
            conf, _ = _confianca(p, m, params)
            av = set(_avisos(m.get("portoes", []))) & excl
            if _bloqueios(m.get("portoes", [])):
                motivo = "investida com portão bloqueante: a valor de mercado"
            elif conf not in ("A", "B"):
                motivo = f"investida com confiança {conf}: a valor de mercado"
            elif av:
                motivo = f"investida com aviso {', '.join(sorted(av))}: a valor de mercado"
            else:
                razao = float(m["v0"]) / float(p["preco"])
                motivo = f"valor intrínseco da casa (V0 ÷ P0 = {razao:.3f})".replace(".", ",")
        partes.append({"emissor": sub, "razao_v0_p0": r6(razao), "motivo": motivo})
        nav_m += v
        nav_c += v * razao
    fator = nav_c / nav_m if nav_m > 0 else 1.0
    return {"fator": r6(fator), "partes": partes}


def vies_modelo(ctx: Mapping[str, Any], params: ParametrosCobertura) -> dict[str, Any]:
    """Indicador de viés de nível do modelo por país (monitorado, nunca forçado): mediana de V0 ÷ P0
    SEM o ajuste de nível e o próprio ajuste δ. A mediana de α por país é centrada por construção
    quando δ não está no limite; o viés real dos fluxos da casa é este."""
    mon = (params.sec("rating").get("monitoramento") or {})
    lo, hi = (float(x) for x in mon.get("vies_v_p_faixa", [0.85, 1.15]))
    out, alertas = {}, []
    for pa, c in sorted((ctx.get("calibracao_pais") or {}).items()):
        vp = _f(c.get("mediana_v_p_sem_calibracao"))
        out[pa] = {"mediana_v_p_sem_ajuste": vp, "ajuste_delta": _f(c.get("delta")), "limitado": bool(c.get("limitado")),
                   "grupo": c.get("grupo"), "n": c.get("n")}
        if c.get("grupo") == "regional":
            continue  # sem nível próprio estimável (menos de 8 emissores): exibido, sem alerta
        rot = pa
        if c.get("limitado"):
            alertas.append(f"ajuste de nível do modelo em {rot} no limite ({pct(_f(c.get('delta')), 2, True)}): viés "
                           "dos fluxos da casa não absorvido")
        if vp is not None and not lo <= vp <= hi:
            alertas.append(f"viés de nível do modelo em {rot}: mediana de V0 ÷ P0 sem o ajuste = {vp:.3f}".replace(".", ",")
                           + f" (fora de {lo:.2f}–{hi:.2f})".replace(".", ","))
    return {"paises": out, "alertas": alertas}


def modelo_json(ex: Execucao, iid: str, params: ParametrosCobertura) -> dict[str, Any]:
    """JSON completo e aberto do modelo de um emissor (o que a página exibe)."""
    pac, mod = ex.pacotes[iid], ex.modelos[iid]
    aviso = SIMULATED_DATA_NOTICE if ex.is_synthetic else AVISO_REAL
    out = {
        "schema": SCHEMA_MODELO, "issuer_id": iid, "nome": pac["nome"], "pais": pac["pais"], "setor": pac["setor"],
        "arquetipo": pac["arquetipo"], "industria": pac["industria"], "as_of": ex.as_of.isoformat(),
        "linha": pac["linha"], "moeda": pac["moeda"], "is_synthetic": ex.is_synthetic, "aviso_dados": aviso,
        "versao_metodologia": params.versao, "horizonte_meses": int(params.valuation.get("horizonte_meses", 12)),
        "resumo": mod["resumo"], "alvos_linhas": mod.get("alvos_linhas", []),
        "insumos": pac.get("tabela_insumos", []), "lacunas": mod.get("lacunas", []), "avisos": mod.get("avisos", []),
        "custo_capital": mod.get("custo_capital"), "metodos": mod.get("metodos", []),
        "persistencia_roe": mod.get("persistencia_roe"),
        "combinacao": {k: mod.get(k) for k in ("cv", "cv_todos", "dissidencia", "metodo_discrepante",
                                               "metodo_principal", "principal_dissidente", "n_metodos")}
        if mod.get("tem_alvo") else None,
        "consenso_lpa": {"n_analistas": mod.get("n_eps"), "poucos_analistas": mod.get("consenso_raso"),
                         "roe_pelo_consenso": mod.get("eps1_consenso"), "linhas": (pac.get("consenso") or {}).get(
                             "n_eps_linhas")},
        "contagem_acoes": pac.get("contagem"),
        "cenarios": {k: mod.get(k) for k in ("tp_pessimista", "tp_mediana_mc", "tp_otimista", "pwr", "pwr_com_piso",
                                             "p_patrimonio_zero", "ret_p10",
                                             "ret_p50", "ret_p90", "udr", "assimetria", "perda_esperada_cauda",
                                             "prob_modelo_supera_ke", "prob_mercado_otimista",
                                             "prob_mercado_pessimista", "largura_cenarios", "n_sorteios",
                                             "diagnostico_cenarios")}
        if mod.get("tem_alvo") else None,
        "sensibilidade": mod.get("sensibilidade"), "diagnosticos": {"icc": mod.get("icc"), "reverso": mod.get("reverso")},
        "fluxo_caixa_observado": {k: mod.get(k) for k in ("fcff_ano1", "fcf_observado", "fcff_ano1_vs_observado",
                                                          "reinvestimento_limitado_anos", "rr_observado",
                                                          "rr_observado_base", "rr_contaminado")}
        if mod.get("fcff_ano1") is not None
        else None,
        "pares": mod.get("pares"), "portoes": mod.get("portoes", []), "ponte": mod.get("ponte"),
        "passos": ex.registros[iid].passos,
    }
    return arredondar(out)


def resumo_linha(ex: Execucao, iid: str) -> dict[str, Any]:
    """Linha da tabela ``modelos.csv`` (uma por emissor)."""
    pac, mod = ex.pacotes[iid], ex.modelos[iid]
    r = mod["resumo"]
    linha = {
        "issuer_id": iid, "nome": pac["nome"], "pais": pac["pais"], "setor": pac["setor"],
        "arquetipo": pac["arquetipo"], "linha": pac["linha"], "moeda": pac["moeda"], "preco": r["preco"],
        "data_preco": r["data_preco"], "preco_alvo": r["preco_alvo"], "upside": r["upside"], "etr": r["etr"],
        "pwr": r["pwr"], "pwr_com_piso": r["pwr_com_piso"], "p_patrimonio_zero": r["p_patrimonio_zero"],
        "ke": r["ke"], "ke_estatico": r["ke_estatico"], "preco_alvo_ke_estatico": r["preco_alvo_ke_estatico"],
        "wacc": r["wacc"], "alpha": r["alpha"], "alpha_rel": r["alpha_rel"], "alpha_rel_estilo": r["alpha_rel_estilo"],
        "rating": r["rating"], "confianca": r["confianca"], "incerteza": r["incerteza"],
        "alvo_otimista": r["alvo_otimista"], "alvo_pessimista": r["alvo_pessimista"], "n_metodos": r["n_metodos"],
        "cv_metodos": r["cv_metodos"], "cv_metodos_todos": mod.get("cv_todos"),
        "n_analistas_lpa": mod.get("n_eps"), "consenso_alvo": (r["consenso"] or {}).get("alvo_medio"),
        "diff_consenso": r["diff_consenso"], "vol_12m": pac.get("vol_12m"),
        "portoes_bloqueio": ",".join(bloqueios(mod.get("portoes", []))),
        "motivo_sem_alvo": r["motivo_sem_alvo"],
    }
    for d in mod.get("metodos", []):
        linha[f"v_{d['m']}"] = d.get("valor")
    return arredondar(linha)


__all__ = ["Anterior", "Execucao", "arredondar", "executar", "modelar", "modelo_json", "resumo_linha",
           "tp_deterministico"]
_ = (preco, math, pp)
