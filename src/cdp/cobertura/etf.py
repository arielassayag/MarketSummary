"""Cobertura dos ETFs latino-americanos: retorno esperado de 12 meses e preço-alvo.

- **Bottom-up (BU)**: ``R_BU = Σ w_i[(1+u_i)(1+φ_i) − 1 + y_i(1+φ_i)] + c·r_caixa − TER``, com
  ``u_i`` do preço-alvo da casa, ``φ_i`` o câmbio esperado (paridade de inflação relativa),
  ``y_i`` o dividend yield líquido de retenção; posição sem modelo ou sem mapeamento recebe o
  retorno top-down do próprio ETF e é sinalizada ("imputada"). Comparador: alvos de consenso com
  desconto κ = 0,5.
- **Top-down 1**: P/L justificado de Gordon com o payout sustentável do índice,
  ``PE* = (1 − g/ROE_índice)/(k − g)`` (``ROE_índice`` = lucro agregado ÷ patrimônio agregado das
  posições), limitado a [0,6; 1,6] × o P/L corrente (fora da faixa, aviso), com reversão parcial
  (meia-vida de 3 anos): ``R = (PE_12/PE_0)(1 + g_LPA)(1 + φ) − 1 + DY(1 + φ)``. Num índice em
  regime estacionário (payout = 1 − g/ROE e PE_0 = PE*), ``ΔPE = 0``.
- **Top-down 2** (Grinold–Kroner): ``E[R] = D/P − ΔS + i + g + ΔPE`` em moeda local, convertido
  pelo câmbio esperado.
- **Combinação**: ``R_e = ω·R_BU + (1 − ω)·R_TD``, ``ω = 0,5 × mín(1, cobertura/0,90)``;
  ``TP_e = P_e(1 + R_e − DY_distribuído)``; banda de 90% por ``σ`` realizada; visão relativa ao ILF
  por ``IR = (R_e − R_ILF)/TE`` com limiar ±0,3 (Positiva/Neutra/Negativa); portão bloqueante ⇒
  "Em revisão".
- Sem composição pública na semana ⇒ BU "indisponível" e top-down pela carteira aproximada do
  universo (valor de mercado do país), sinalizada; nunca uma aproximação silenciosa.

O cálculo (:func:`calcular_etf`) é função pura de um pacote de insumos do ETF
(:func:`insumos_etf`: preço, volatilidade, erro de acompanhamento contra o ILF, taxa de caixa e
composição), arquivado no snapshot para que ``cobertura verify`` refaça cada ETF.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from ..market import MarketData
from .fontes import DadosPublicos
from .formato import inteiro, mult, num, operando, pct, preco, r6
from .insumos import _serie_usd_semanal, fx_usd, vol_realizada
from .parametros import ParametrosCobertura
from .passos import Registro, prov_codigo
from .qualidade import bloqueios, portoes_etf

COLS_COMP = ("ticker_bruto", "nome", "peso", "setor", "pais", "issuer_id", "classe_ativo")


def pl_gordon(b: float, k: float, g: float) -> float:
    """P/L justificado de um índice: ``b/(k − g)`` (exige ``k > g``)."""
    if g >= k:
        raise ValueError("g ≥ k no P/L justificado.")
    return b / (k - g)


def payout_sustentavel(roe: float, g: float) -> float:
    """Payout que sustenta o crescimento ``g`` com retorno ``roe``: ``1 − g/ROE``."""
    if roe <= 0:
        raise ValueError("ROE do índice não positivo.")
    return 1 - g / roe


def reversao_pl(pe0: float, pe_star: float, meia_vida: float) -> float:
    """P/L em 12 meses com reversão parcial ao justificado (meia-vida em anos)."""
    frac = 1 - 2 ** (-1 / meia_vida)
    return pe0 * (pe_star / pe0) ** frac


def grinold_kroner(dp: float, delta_s: float, i: float, g: float, delta_pe: float) -> float:
    """Grinold–Kroner–Siegel: ``D/P − ΔS + i + g + ΔPE``."""
    return dp - delta_s + i + g + delta_pe


def agregar_bu(linhas: list[dict[str, Any]], caixa: float, r_caixa: float, ter: float) -> float:
    """Soma ponderada exata dos retornos por posição (pesos já normalizados com o caixa)."""
    return sum(x["peso"] * x["retorno"] for x in linhas) + caixa * r_caixa - ter


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _fx_fator_12m(params: ParametrosCobertura, moeda: str) -> float:
    """``E[USD por moeda em 12m] ÷ hoje`` pela paridade de inflação relativa."""
    infl = params.cc["inflacao_lp"]
    pi_us = float(infl["USD"])
    return (1 + pi_us) / (1 + float(infl.get(moeda, pi_us)))


def _te_ir(md: MarketData, a: str, b: str, as_of: date) -> float | None:
    sa, sb = _serie_usd_semanal(md, a, as_of), _serie_usd_semanal(md, b, as_of)
    if sa.empty or sb.empty:
        return None
    r = pd.concat([sa.pct_change(), sb.pct_change()], axis=1, keys=["a", "b"]).dropna().tail(104)
    if len(r) < 26:
        return None
    return float((r["a"] - r["b"]).std(ddof=1) * math.sqrt(52))


def _preco_etf(md: MarketData, t: str, as_of: date) -> tuple[float | None, date | None]:
    if t not in md.benchmarks.columns:
        return None, None
    s = md.benchmarks[t].loc[:pd.Timestamp(as_of)].dropna()
    s = s[s > 0]
    return (float(s.iloc[-1]), s.index[-1].date()) if len(s) else (None, None)


def _composicao_aproximada(pacotes: Mapping[str, Mapping[str, Any]], pais: str) -> pd.DataFrame:
    rows = []
    for iid, p in pacotes.items():
        if pais not in ("LATAM",) and p["pais"] != pais:
            continue
        mc, fx = _f(p.get("valor_mercado")), _f(p.get("fx_usd_moeda"))
        if mc is None or fx is None:
            continue
        rows.append({"ticker_bruto": p["linha"], "nome": p["nome"], "peso": mc * fx, "issuer_id": iid,
                     "setor": p["setor"], "pais": p["pais"]})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["peso", "issuer_id"], ascending=[False, True]).head(40)
    df["peso"] = df["peso"] / df["peso"].sum()
    return df


def _registros(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for _, r in df.iterrows():
        d = {}
        for c in COLS_COMP:
            v = r.get(c) if c in df.columns else None
            if isinstance(v, float) and not math.isfinite(v):
                v = None
            if c == "peso":
                v = _f(v)
            elif v is not None and not isinstance(v, (int, float)):
                v = str(v)
            d[c] = v
        out.append(d)
    return out


def insumos_etf(cfg: Mapping[str, Any], md: MarketData, dados: DadosPublicos, params: ParametrosCobertura,
                pacotes: Mapping[str, Mapping[str, Any]], as_of: date) -> dict[str, Any]:
    """Pacote de insumos do ETF (tudo o que :func:`calcular_etf` usa além dos pacotes e modelos
    dos emissores), arquivado no snapshot."""
    ec = params.sec("etf")
    t = str(cfg["ticker"])
    moeda = str(cfg.get("moeda", "USD"))
    p0, d0 = _preco_etf(md, t, as_of)
    comp = dados.etfs.get(t)
    aprox = comp is None or comp.empty
    if aprox:
        comp = _composicao_aproximada(pacotes, str(cfg.get("pais", "LATAM")))
    rcx_serie = "SELIC" if moeda == "BRL" else "USD_3M"
    rcx = None
    if rcx_serie in md.rates.columns:
        s = md.rates[rcx_serie].loc[:pd.Timestamp(as_of)].dropna()
        rcx = _f(s.iloc[-1]) if len(s) else None
    ref = str(ec["referencia"])
    simulado = bool(md.is_synthetic) or dados.origem == "SIMULADO"
    if aprox:
        fonte_c = prov_codigo("carteira aproximada do universo (composição pública indisponível na semana)")
    elif simulado:
        fonte_c = {"fonte": "SIMULADO", "url": None, "documento": "composição simulada (DADOS SIMULADOS)",
                   "data_publicacao": None, "data_coleta": None, "sha256": None}
    else:
        fonte_c = {"fonte": str(cfg.get("emissor")), "url": cfg.get("url"),
                   "documento": "arquivo público de composição do ETF", "data_publicacao": None,
                   "data_coleta": None, "sha256": None}
    return {
        "schema": "cdp.cobertura.etf_insumos/v1", "ticker": t, "iid": f"ETF_{t.split('.')[0]}",
        "nome": cfg.get("nome"), "indice": cfg.get("indice"), "moeda": moeda, "pais": str(cfg.get("pais", "LATAM")),
        "ter": _f(cfg.get("ter")) or 0.0, "as_of": as_of.isoformat(), "preco": r6(p0),
        "data_preco": d0.isoformat() if d0 else None, "vol_12m": r6(vol_realizada(md, t, as_of, 252)),
        "te_ilf": None if t == ref else r6(_te_ir(md, t, ref, as_of)), "taxa_caixa": r6(rcx),
        "composicao": [] if comp is None or comp.empty else _registros(comp), "composicao_aproximada": bool(aprox),
        "simulado": simulado, "fonte_composicao": fonte_c,
        "fonte_preco": {"fonte": "SIMULADO" if simulado else "YAHOO",
                        "url": None if simulado else f"https://finance.yahoo.com/quote/{t}",
                        "documento": "fechamento do ETF" + (" (DADOS SIMULADOS)" if simulado else ""),
                        "data_publicacao": d0.isoformat() if d0 else None, "data_coleta": None, "sha256": None},
    }


def calcular_etf(ins: Mapping[str, Any], params: ParametrosCobertura, pacotes: Mapping[str, Mapping[str, Any]],
                 modelos: Mapping[str, Mapping[str, Any]], rf_ust: float | None,
                 r_ilf: float | None = None) -> dict[str, Any]:
    """Modelo do ETF a partir do pacote de insumos (função pura; ver docstring do módulo)."""
    ec = params.sec("etf")
    cc = params.cc
    reg = Registro()
    t, moeda, pais = str(ins["ticker"]), str(ins["moeda"]), str(ins["pais"])
    p0 = _f(ins.get("preco"))
    out: dict[str, Any] = {"schema": "cdp.cobertura.etf/v1", "ticker": t, "iid": ins["iid"], "nome": ins.get("nome"),
                           "indice": ins.get("indice"), "moeda": moeda, "pais": pais, "as_of": ins["as_of"],
                           "preco": p0, "data_preco": ins.get("data_preco"), "lacunas": [], "avisos": []}
    if p0 is None:
        out["lacunas"].append({"insumo": "preco", "nome": "preço do ETF", "motivo": "sem preço do ETF na base"})
        out["tem_alvo"] = False
        out["passos"] = reg.passos
        out["portoes"] = portoes_etf(out, params)
        return out
    reg.add("etf.preco", "Preço de referência do ETF", "P_e = fechamento", f"P_e = fechamento de {t} em {ins.get('data_preco')}",
            p0, f"preco:{moeda}", [ins["fonte_preco"]])
    aprox = bool(ins.get("composicao_aproximada"))
    comp = pd.DataFrame(ins.get("composicao") or [], columns=list(COLS_COMP))
    if aprox:
        out["lacunas"].append({"insumo": "composicao", "nome": "composição do ETF",
                               "motivo": "composição pública indisponível na semana: bottom-up indisponível; "
                                         "top-down pela carteira aproximada do universo"})
    comp["peso"] = pd.to_numeric(comp["peso"], errors="coerce")
    comp = comp.dropna(subset=["peso"])
    if comp["peso"].sum() > 1.5:  # pesos em %
        comp["peso"] = comp["peso"] / 100.0
    tot = float(comp["peso"].sum()) if len(comp) else 0.0
    if tot <= 0:
        out["tem_alvo"] = False
        out["lacunas"].append({"insumo": "composicao", "nome": "composição do ETF", "motivo": "composição vazia"})
        out["passos"] = reg.passos
        out["portoes"] = portoes_etf(out, params)
        return out
    comp["peso"] = comp["peso"] / tot
    is_caixa = comp.apply(lambda r: str(r.get("setor") or "").lower() in ("caixa", "cash", "cash and/or derivatives")
                          or str(r.get("classe_ativo") or "").lower() in ("cash", "money market", "futures",
                                                                          "cash collateral and margins")
                          or str(r.get("ticker_bruto") or "").upper() in ("USD", "BRL", "MXN", "CLP", "COP"), axis=1)
    caixa = float(comp.loc[is_caixa, "peso"].sum())
    pos = comp.loc[~is_caixa]
    # --- agregados para o top-down (posições com pacote)
    fx12_etf = _fx_fator_12m(params, moeda)
    ey = dy = by = gw = ds_w = 0.0
    w_ey = w_dy = w_by = w_g = w_ds = 0.0
    for _, r in pos.iterrows():
        iid = r.get("issuer_id")
        if not isinstance(iid, str) or iid not in pacotes:
            continue
        p = pacotes[iid]
        pr, e1, e2 = _f(p.get("preco")), _f(p.get("eps_fy1")), _f(p.get("eps_fy2"))
        dps, bv = _f(p.get("dps_12m")), _f(p.get("bvps"))
        w = float(r["peso"])
        if pr and e1 is not None:
            ey += w * e1 / pr
            w_ey += w
            if bv is not None and bv > 0:
                by += w * bv / pr
                w_by += w
        if pr and dps is not None:
            dy += w * dps / pr
            w_dy += w
        if e1 and e2 is not None and e1 > 0:
            gw += w * min(max(e2 / e1 - 1, -0.2), 0.3)
            w_g += w
        h = (p.get("historico") or {}).get("acoes_em_circulacao") or {}
        anos = sorted(h)
        if len(anos) >= 2 and h[anos[-2]]:
            ds_w += w * (h[anos[-1]] / h[anos[-2]] - 1)
            w_ds += w
    pais_ke = pais if pais in cc["crp"] else "LATAM"
    rf = (rf_ust if rf_ust is not None else float(cc["rf_usd_reserva"])) - float(cc["spread_default_eua"])
    k_usd = rf + float(cc["erp_maduro"]) + float(cc["crp"][pais_ke])
    moeda_loc = {"BR": "BRL", "MX": "MXN", "CL": "CLP", "CO": "COP", "PE": "PEN", "AR": "ARS"}.get(pais, "USD")
    pi_loc = float(cc["inflacao_lp"].get(moeda_loc, cc["inflacao_lp"]["USD"]))
    pi_us = float(cc["inflacao_lp"]["USD"])
    phi = _fx_fator_12m(params, moeda_loc) / fx12_etf - 1
    reg.add("etf.ke", "Custo de capital do índice em dólar (β = 1)", "k = rf + ERP + CRP",
            f"k = {pct(rf)} + {pct(cc['erp_maduro'])} + {pct(cc['crp'][pais_ke])}", k_usd, "%",
            [params.fonte("damodaran_ctryprem")])
    reg.add("etf.cambio", "Câmbio esperado (paridade de inflação relativa)",
            "φ = (1 + π_EUA)/(1 + π_local) − 1 (relativo à moeda do ETF)",
            f"φ = (1 + {pct(pi_us)}) / (1 + {pct(pi_loc)}) − 1", phi, "%", [params.fonte("damodaran_inflacao")])
    td = []
    td1 = td2 = None
    pe0 = pe12 = None
    lim_lo, lim_hi = params.sec("qualidade").get("etf_pl_razao_limites", [0.6, 1.6])
    if w_ey > 0.5 and w_dy > 0.5 and ey > 0:
        ey_a, dy_a = ey / w_ey, dy / w_dy
        g_eps = gw / w_g if w_g > 0.5 else (1 + float(params.sec("perpetuidade")["g_real"])) * (1 + pi_loc) - 1
        g_us = (1 + float(params.sec("perpetuidade")["g_real"])) * (1 + pi_us) - 1
        pe0 = 1 / ey_a
        roe_idx = (ey / w_ey) / (by / w_by) if w_by > 0.5 and by > 0 else None
        try:
            if roe_idx is None:
                raise ValueError("patrimônio agregado das posições indisponível")
            b_bruto = payout_sustentavel(roe_idx, g_us)
            b = min(max(b_bruto, 0.05), 0.95)
            no_limite = b != b_bruto
            pe_bruto = pl_gordon(b, k_usd, g_us)
            razao = pe_bruto / pe0
            pe_star = pe0 * min(max(razao, float(lim_lo)), float(lim_hi))
            if pe_star != pe_bruto:
                out["avisos"].append(f"P/L justificado de {mult(pe_bruto, 1)} limitado a {mult(pe_star, 1)} "
                                     f"({num(lim_lo, 1)} a {num(lim_hi, 1)} × o P/L corrente de {mult(pe0, 1)})")
            hl = float(ec["meia_vida_pl_anos"])
            pe12 = reversao_pl(pe0, pe_star, hl)
            td1 = (pe12 / pe0) * (1 + g_eps) * (1 + phi) - 1 + dy_a * (1 + phi)
            reg.add("etf.payout", "Payout sustentável do índice", "b = 1 − g ÷ ROE_índice (ROE = lucro ÷ patrimônio agregados)",
                    f"b = 1 − {pct(g_us)} ÷ {pct(roe_idx)}", b, "%",
                    premissas=("limitado a [5%; 95%]" if no_limite else None))
            reg.add("etf.pl_justificado", "P/L justificado do índice (limitado em relação ao corrente)",
                    f"PE* = mín(máx(b ÷ (k − g); {num(lim_lo, 1)} × PE_0); {num(lim_hi, 1)} × PE_0)",
                    f"PE* = mín(máx({pct(b)} ÷ ({pct(k_usd)} − {pct(g_us)}); {num(lim_lo, 1)} × {mult(pe0, 1)}); "
                    f"{num(lim_hi, 1)} × {mult(pe0, 1)})", pe_star, "x",
                    premissas=f"P/L corrente PE_0 = 1 ÷ lucro por preço agregado = {mult(pe0, 1)}")
            reg.add("etf.td1", "Top-down 1: P/L justificado com reversão parcial",
                    "R = (PE_12 ÷ PE_0) × (1 + g_LPA) × (1 + φ) − 1 + DY × (1 + φ); PE_12 = PE_0 × (PE* ÷ PE_0)^(1 − 2^(−1/3))",
                    f"R = ({mult(pe12, 2)} ÷ {mult(pe0, 2)}) × (1 + {operando(pct(g_eps))}) × (1 + {operando(pct(phi))}) − 1 + "
                    f"{pct(dy_a)} × (1 + {operando(pct(phi))})", td1, "%")
            td.append(td1)
            out["agregados"] = {"pl": r6(pe0), "pl_justificado": r6(pe_star), "pl_justificado_bruto": r6(pe_bruto),
                                "pl_justificado_sobre_corrente_bruto": r6(razao), "dy": r6(dy_a), "payout": r6(b),
                                "payout_no_limite": bool(no_limite), "roe_indice": r6(roe_idx),
                                "g_lpa": r6(g_eps), "cobertura_lpa": r6(w_ey)}
        except ValueError as exc:
            out["avisos"].append(f"top-down 1 indisponível: {exc}")
        if w_ds > 0.5:
            ds = ds_w / w_ds
            g_real = float(params.sec("perpetuidade")["g_real"])
            dpe = 0.0 if td1 is None else math.log(pe12 / pe0)
            r_loc = grinold_kroner(dy_a, ds, pi_loc, g_real, dpe)
            td2 = (1 + r_loc) * (1 + phi) - 1
            reg.add("etf.td2", "Top-down 2: Grinold–Kroner",
                    "E[R] = (1 + D/P − ΔS + i + g + ΔPE) × (1 + φ) − 1, com ΔPE = ln(PE_12 ÷ PE_0)",
                    f"E[R] = (1 + {pct(dy_a)} − {operando(pct(ds))} + {pct(pi_loc)} + {pct(g_real)} + "
                    f"{operando(pct(dpe))}) × (1 + {operando(pct(phi))}) − 1", td2, "%")
            td.append(td2)
        else:
            out["lacunas"].append({"insumo": "delta_s", "nome": "variação do número de ações",
                                   "motivo": "histórico de ações insuficiente: Grinold–Kroner indisponível"})
    r_td = float(np.mean(td)) if td else None
    if r_td is not None:
        reg.add("etf.td", "Top-down combinado", "R_TD = média(TD1, TD2 disponíveis)",
                f"R_TD = média({'; '.join(pct(x) for x in td)})", r_td, "%")
    # --- bottom-up
    r_bu = None
    cobertura = 0.0
    linhas: list[dict[str, Any]] = []
    rcx = _f(ins.get("taxa_caixa"))
    ret_caixa = rcx if rcx is not None else rf
    kappa = float(ec["kappa_consenso"])
    if not aprox:
        ret_street = 0.0
        w_street = 0.0
        for _, r in pos.iterrows():
            iid = r.get("issuer_id")
            w = float(r["peso"])
            linha: dict[str, Any] = {"ticker_bruto": str(r.get("ticker_bruto")), "nome": str(r.get("nome") or ""),
                                     "issuer_id": iid if isinstance(iid, str) else None, "peso": r6(w)}
            m = modelos.get(iid) if isinstance(iid, str) else None
            if m is not None and m.get("tem_alvo") and m.get("rating") not in ("Em revisão", "Sem preço-alvo"):
                p = pacotes[iid]
                pr = float(p["preco"])
                u = float(m["tp"]) / pr - 1
                pais_i = str(p["pais"])
                ret = float(params.sec("etf")["retencao_dividendos"].get(pais_i, 0.0))
                y = float(m.get("dps12") or 0.0) / pr * (1 - ret)
                phi_i = _fx_fator_12m(params, str(p["moeda"])) / fx12_etf - 1
                ri = (1 + u) * (1 + phi_i) - 1 + y * (1 + phi_i)
                linha.update({"u": r6(u), "fx": r6(phi_i), "dy_liquido": r6(y), "retorno": r6(ri), "imputado": False})
                cobertura += w
                cons = p.get("consenso") or {}
                if cons.get("plausivel") and cons.get("upside") is not None:
                    ret_street += w * ((1 + kappa * float(cons["upside"])) * (1 + phi_i) - 1 + y * (1 + phi_i))
                    w_street += w
            else:
                motivo = ("posição sem mapeamento" if not isinstance(iid, str) else
                          "emissor em revisão ou sem preço-alvo" if m is not None else "sem modelo da casa")
                linha.update({"retorno": r6(r_td) if r_td is not None else None, "imputado": True, "motivo": motivo})
            linhas.append(linha)
        out["posicoes"] = linhas
        if all(x.get("retorno") is not None for x in linhas):
            r_bu = agregar_bu([{"peso": float(x["peso"]), "retorno": float(x["retorno"])} for x in linhas],
                              caixa, ret_caixa, float(ins.get("ter") or 0.0))
            reg.add("etf.bu", "Bottom-up (alvos da casa por posição)",
                    "R_BU = Σ w_i × [(1 + u_i)(1 + φ_i) − 1 + y_i(1 + φ_i)] + c × r_caixa − TER",
                    f"R_BU = Σ das {inteiro(len(linhas))} posições + {pct(caixa)} × {pct(ret_caixa)} − "
                    f"{pct(ins.get('ter') or 0.0)}", r_bu, "%",
                    premissas=f"peso coberto por modelos da casa {pct(cobertura)}; posições sem modelo recebem o "
                              f"retorno top-down")
            if w_street > 0:
                out["bottom_up_consenso"] = r6(ret_street / w_street)
        else:
            out["lacunas"].append({"insumo": "bottom_up", "nome": "retorno bottom-up",
                                   "motivo": "posições sem modelo e sem top-down para imputar"})
    omega = float(ec["omega_bu"]) * min(1.0, cobertura / float(ec["cobertura_plena"])) if r_bu is not None else 0.0
    if r_bu is None and r_td is None:
        out["tem_alvo"] = False
        out["passos"] = reg.passos
        out["portoes"] = portoes_etf(out, params)
        return out
    r_e = (omega * r_bu if r_bu is not None else 0.0) + (1 - omega) * (r_td if r_td is not None else r_bu)
    reg.add("etf.combinado", "Retorno esperado de 12 meses",
            "R_e = ω × R_BU + (1 − ω) × R_TD; ω = 0,5 × mín(1; cobertura ÷ 0,90)",
            f"R_e = {num(omega, 3)} × {operando(pct(r_bu))} + {num(1 - omega, 3)} × {operando(pct(r_td))}"
            if r_bu is not None and r_td is not None else
            (f"R_e = {pct(r_td)}" if r_bu is None else f"R_e = {pct(r_bu)}"), r_e, "%")
    dy_dist = (dy / w_dy) if w_dy > 0.5 else 0.0
    tp = p0 * (1 + r_e - dy_dist)
    reg.add("etf.alvo", "Preço-alvo de 12 meses do ETF", "TP_e = P_e × (1 + R_e − DY_distribuído)",
            f"TP_e = {preco(p0, moeda)} × (1 + {operando(pct(r_e))} − {pct(dy_dist)})", tp, f"preco:{moeda}")
    vol = _f(ins.get("vol_12m"))
    banda = None
    if vol is not None:
        z = float(ec["banda_z"])
        banda = [tp * math.exp(-z * vol), tp * math.exp(z * vol)]
        reg.add("etf.banda", "Faixa de 90% do preço em 12 meses", "TP_e × exp(± 1,645 × σ)",
                f"{preco(tp, moeda)} × exp(± {num(z, 3)} × {pct(vol)})", banda[1], f"preco:{moeda}",
                texto=f"{preco(banda[0], moeda)} a {preco(banda[1], moeda)}",
                premissas="σ = volatilidade realizada de 12 meses")
    te = None
    visao = "Referência" if t == str(ec["referencia"]) else None
    if visao is None and r_ilf is not None:
        te = _f(ins.get("te_ilf"))
        if te:
            ir = (r_e - r_ilf) / te
            lim = float(ec["ir_limiar"])
            visao = "Positiva" if ir >= lim else ("Negativa" if ir <= -lim else "Neutra")
            reg.add("etf.visao", "Visão relativa ao ILF", "IR = (R_e − R_ILF) ÷ TE; limiar ±0,3",
                    f"IR = ({pct(r_e)} − {operando(pct(r_ilf))}) ÷ {pct(te)}", ir, "n",
                    premissas=f"visão {visao.lower()}")
            out["ir"] = r6(ir)
    out.update({"tem_alvo": True, "metodo": "combinado" if r_bu is not None and r_td is not None else
                ("bottom_up" if r_bu is not None else "top_down"), "r_bu": r6(r_bu), "r_td": r6(r_td),
                "td1": r6(td1), "td2": r6(td2), "omega_bu": r6(omega), "cobertura": r6(cobertura),
                "caixa": r6(caixa), "retorno_esperado": r6(r_e), "preco_alvo": r6(tp), "upside": r6(tp / p0 - 1),
                "banda_90": [r6(x) for x in banda] if banda else None, "vol_12m": r6(vol), "te_ilf": r6(te),
                "visao_ilf": visao, "composicao_aproximada": aprox, "ter": ins.get("ter"),
                "fonte_composicao": ins.get("fonte_composicao")})
    out["texto"] = {"preco": preco(p0, moeda), "preco_alvo": preco(tp, moeda), "upside": pct(tp / p0 - 1, 1, True),
                    "retorno_esperado": pct(r_e, 1, True), "r_bu": pct(r_bu, 1, True), "r_td": pct(r_td, 1, True),
                    "cobertura": pct(cobertura, 0), "caixa": pct(caixa, 1),
                    "banda_90": None if not banda else f"{preco(banda[0], moeda)} a {preco(banda[1], moeda)}",
                    "te_ilf": pct(te, 1), "ter": pct(ins.get("ter"), 2)}
    for x in out.get("posicoes", []):
        x["texto"] = {"peso": pct(x.get("peso"), 2), "retorno": pct(x.get("retorno"), 1, True),
                      "u": pct(x.get("u"), 1, True) if x.get("u") is not None else None}
    out["portoes"] = portoes_etf(out, params)
    bl = bloqueios(out["portoes"])
    if bl:
        out["visao_ilf"] = "Em revisão"
        out["visao_motivo"] = "portão de qualidade bloqueante: " + ", ".join(bl)
    reg.nota("etf.qualidade", "Portões de qualidade do ETF",
             "; ".join(f"{p['codigo']} {p['nome']}: {p['status']} ({p['detalhe']})" for p in out["portoes"]) + ".")
    out["passos"] = reg.passos
    return out


def avaliar_etf(cfg: Mapping[str, Any], md: MarketData, dados: DadosPublicos, params: ParametrosCobertura,
                pacotes: Mapping[str, Mapping[str, Any]], modelos: Mapping[str, Mapping[str, Any]],
                rf_ust: float | None, as_of: date, r_ilf: float | None = None) -> dict[str, Any]:
    """Insumos do ETF a partir do mercado + :func:`calcular_etf`."""
    ins = insumos_etf(cfg, md, dados, params, pacotes, as_of)
    return calcular_etf(ins, params, pacotes, modelos, rf_ust, r_ilf)


def calcular_etfs(insumos: Mapping[str, Mapping[str, Any]], params: ParametrosCobertura,
                  pacotes: Mapping[str, Mapping[str, Any]], modelos: Mapping[str, Mapping[str, Any]],
                  rf_ust: float | None) -> dict[str, dict[str, Any]]:
    """Todos os ETFs a partir dos pacotes de insumos (a referência ILF primeiro)."""
    ref = str(params.sec("etf")["referencia"])
    ordem = sorted(insumos.values(), key=lambda c: (c["ticker"] != ref, c["ticker"]))
    out: dict[str, dict[str, Any]] = {}
    r_ilf = None
    for ins in ordem:
        e = calcular_etf(ins, params, pacotes, modelos, rf_ust, r_ilf)
        if ins["ticker"] == ref and e.get("tem_alvo") and e.get("visao_ilf") != "Em revisão":
            r_ilf = float(e["retorno_esperado"])
        out[e["iid"]] = e
    return out


def avaliar_etfs(md: MarketData, dados: DadosPublicos, params: ParametrosCobertura,
                 pacotes: Mapping[str, Mapping[str, Any]], modelos: Mapping[str, Mapping[str, Any]],
                 rf_ust: float | None, as_of: date) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """``(modelos dos ETFs, pacotes de insumos dos ETFs)`` por ``iid``."""
    cfgs = [c for c in params.etfs.get("etfs", []) if c["ticker"] in md.benchmarks.columns]
    insumos = {}
    for c in cfgs:
        ins = insumos_etf(c, md, dados, params, pacotes, as_of)
        insumos[ins["iid"]] = ins
    _ = fx_usd
    return calcular_etfs(insumos, params, pacotes, modelos, rf_ust), insumos


__all__ = ["agregar_bu", "avaliar_etf", "avaliar_etfs", "calcular_etf", "calcular_etfs", "grinold_kroner",
           "insumos_etf", "payout_sustentavel", "pl_gordon", "reversao_pl"]
