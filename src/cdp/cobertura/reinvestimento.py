"""Reinvestimento não alavancado com arrendamentos capitalizados.

O fluxo usado pelo FCFF parte do NOPAT, não do CFO reportado, cuja classificação de juros,
impostos e encargos varia entre os regimes contábeis. A dívida de arrendamentos já integra a
ponte EV → patrimônio e o WACC: sua amortização não é investimento e nunca é subtraída de
novo. O investimento em ativos arrendados é a adição de direitos de uso publicada.

As observações são comparáveis somente quando todos os componentes têm a mesma data-base.
Um componente ausente não vira zero; zero de direitos de uso exige publicação explícita. A
posição de passivo no encerramento não comprova ausência de investimento durante o período.
Os modelos históricos usam a política anterior no
contexto, escolhida pelos parâmetros arquivados de cada retrato.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

COMPONENTES = ("ebit", "capex", "d_a_dfc", "variacao_capital_giro_operacional", "adicoes_direito_uso")


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _periodo_valido(x: Any) -> str | None:
    if not isinstance(x, str):
        return None
    m = re.fullmatch(r"(A|TTM)\|(\d{4}-\d{2}-\d{2})", x)
    if m is None:
        m = re.fullmatch(r"(anual|12 meses) até (\d{4}-\d{2}-\d{2})", x)
    if m is None:
        return None
    try:
        fim = date.fromisoformat(m[2])
    except ValueError:
        return None
    freq = {"anual": "A", "12 meses": "TTM"}.get(m[1], m[1])
    return f"{freq}|{fim.isoformat()}"


def _periodo(p: Mapping[str, Any], ano: str | None, imposto: float) -> dict[str, Any] | None:
    h = p.get("historico") or {}
    meta = p.get("periodos_fluxos") or {}

    def dado(k: str) -> float | None:
        return _f((h.get(k) or {}).get(ano)) if ano is not None else _f(p.get(f"t.{k}"))

    e, cap, da, giro, rou = (dado(k) for k in COMPONENTES)
    # A D&A da DFC restitui só a parcela que afetou o resultado do período. A D&A bruta
    # do imobilizado pode incluir depreciação capitalizada no estoque ou no próprio capex.
    if e is None or e <= 0 or cap is None or da is None or giro is None:
        return None
    if cap < 0 or da < 0:
        return None  # contrato canônico: capex e depreciação são magnitudes positivas
    if rou is None or rou < 0:
        return None
    periodo = ano
    exigidos = list(COMPONENTES)
    if ano is not None:
        hm = p.get("historico_periodos") or {}
        presentes = {_periodo_valido((hm.get(k) or {}).get(ano)) for k in exigidos}
        if None in presentes or len(presentes) != 1 or not next(iter(presentes)).startswith("A|"):
            return None
        periodo = next(iter(presentes))
        if periodo.split("|")[1][:4] != str(ano):
            return None
        bases = {((p.get("historico_bases") or {}).get(k) or {}).get(ano) for k in exigidos}
        moedas = {((p.get("historico_moedas") or {}).get(k) or {}).get(ano) for k in exigidos}
    if ano is None:
        presentes = {_periodo_valido(meta.get(k)) for k in COMPONENTES}
        # O contrato novo registra datas individuais. Pacotes feitos à mão sem datas não
        # podem certificar a identidade de fluxos; testes econômicos também as fornecem.
        if None in presentes or len(presentes) != 1:
            return None
        periodo = next(iter(presentes))
        bases = {(p.get("bases_fluxos") or {}).get(k) for k in exigidos}
        moedas = {(p.get("moedas_fluxos") or {}).get(k) for k in exigidos}
    if len(bases) != 1 or next(iter(bases)) not in ("consolidado", "individual"):
        return None
    if len(moedas) != 1 or not isinstance(next(iter(moedas)), str) or not re.fullmatch(r"[A-Z]{3}", next(iter(moedas))):
        return None
    if next(iter(moedas)) != p.get("moeda_demonstrativos"):
        return None  # o fator global do pacote precisa corresponder à moeda destes valores
    nopat = e * (1 - imposto)
    reinvest = cap + rou - da + giro
    fcff = nopat - reinvest
    return {"rr": reinvest / nopat, "base": "12 meses" if ano is None else "1 exercício",
            "anos": [] if ano is None else [ano], "periodo": periodo, "fcf": fcff, "nopat": nopat,
            "reinvestimento": reinvest, "capex": cap, "d_a": da, "variacao_capital_giro": giro,
            "adicoes_direito_uso": rou, "arrendamentos": None,
            "metodo": "capitalizacao_arrendamentos", "fontes_itens": list(COMPONENTES),
            "base_contabil": next(iter(bases)), "moeda_demonstrativos": next(iter(moedas)),
            "principal_descontado": False}


def reinvestimento_capitalizado(p: Mapping[str, Any], imposto: float, anos: int = 3,
                                regime: str = "recente") -> dict[str, Any] | None:
    """FCFF observado pelo capital investido; publicação parcial nunca fecha a identidade.

    ``recente`` usa os últimos 12 meses completos e alinhados, ou o último exercício completo.
    A média dos exercícios fica como diagnóstico do regime, sem impor sua manutenção na
    projeção. ``suavizado`` é uma política explícita, usando a soma dos últimos ``anos``
    exercícios completos. Nenhum dos regimes consulta o preço ou a distribuição de ratings.
    """
    if p.get("financeira") or not 0 <= imposto < 1 or anos < 1:
        return None
    h = p.get("historico") or {}
    comuns = sorted(set(h.get("ebit") or {}) & set(h.get("capex") or {}) & set(h.get("d_a_dfc") or {})
                    & set(h.get("variacao_capital_giro_operacional") or {}))
    observacoes = [r for a in comuns if (r := _periodo(p, str(a), imposto)) is not None]
    recentes = observacoes[-anos:]
    media = None
    if len(recentes) == anos:
        n = sum(r["nopat"] for r in recentes)
        i = sum(r["reinvestimento"] for r in recentes)
        media = {"rr": i / n, "base": f"{anos} exercícios", "anos": [r["anos"][0] for r in recentes],
                 "fcf": n - i, "nopat": n, "reinvestimento": i,
                 **{k: sum(r[k] for r in recentes) for k in ("capex", "d_a", "variacao_capital_giro",
                                                            "adicoes_direito_uso")},
                 "metodo": "capitalizacao_arrendamentos", "arrendamentos": None,
                 "fontes_itens": list(COMPONENTES), "principal_descontado": False}
    if regime not in ("recente", "suavizado"):
        raise ValueError("Regime de reinvestimento desconhecido: use recente ou suavizado.")
    ttm = _periodo(p, None, imposto)
    atual = ttm or (observacoes[-1] if observacoes else None)
    usado = (media or atual) if regime == "suavizado" else atual
    if usado is None:
        return None
    # Uma anual antiga não substitui observações recentes incompletas em silêncio.
    usado = dict(usado)
    usado.update({"regime": regime, "rr_historico": None if media is None else media["rr"],
                  "anos_historico": [] if media is None else media["anos"],
                  "ponte_historica": media,
                  "rr_12m": None if ttm is None else ttm["rr"],
                  "componentes_12m_incompletos": ttm is None})
    return usado


def giro_por_balancos_sombra(inicial: Mapping[str, Any], final: Mapping[str, Any]) -> dict[str, Any]:
    """Proxy de capital de giro por balanços, separada da variação reconciliada da DFC.

    NCWC = ativo circulante − caixa − aplicações − passivo circulante + dívida de curto prazo
    (incluindo arrendamentos) + dividendos a pagar. A diferença não distingue aquisição,
    alienação, câmbio e mudança de perímetro: fica em sombra mesmo com todos os saldos presentes.
    Nunca preenche ``variacao_capital_giro_operacional`` nem libera a identidade do FCFF.
    """
    campos = ("ativo_circulante", "caixa", "aplicacoes_cp", "passivo_circulante",
              "divida_curto_prazo", "dividendos_a_pagar")
    obs = []
    faltam = []
    for lado, p in (("inicial", inicial), ("final", final)):
        v = {k: _f(p.get(k)) for k in campos}
        faltam.extend(f"{lado}.{k}" for k, x in v.items() if x is None)
        if not p.get("data") or not p.get("moeda"):
            faltam.append(f"{lado}.data_ou_moeda")
        n = None if any(x is None for x in v.values()) else (v["ativo_circulante"] - v["caixa"] - v["aplicacoes_cp"]
             - v["passivo_circulante"] + v["divida_curto_prazo"] + v["dividendos_a_pagar"])
        obs.append({"data": p.get("data"), "moeda": p.get("moeda"), "ncwc": n,
                    "saldos": v, "fontes": p.get("fontes") or {}})
    moedas_iguais = bool(inicial.get("moeda") and inicial.get("moeda") == final.get("moeda"))
    try:
        if date.fromisoformat(str(final.get("data"))[:10]) <= date.fromisoformat(str(inicial.get("data"))[:10]):
            faltam.append("intervalo_nao_positivo")
    except ValueError:
        faltam.append("datas_invalidas")
    delta = None if faltam or not moedas_iguais else obs[1]["ncwc"] - obs[0]["ncwc"]
    return {"estado": "sombra", "usavel_fcff": False, "observacoes": obs, "delta_proxy": delta,
            "formula": "NCWC = AC − caixa − aplicações − PC + dívida CP (com leases) + dividendos a pagar",
            "faltam": faltam, "ajustes_a_conferir": ["aquisições e alienações", "câmbio", "perímetro", "tributos"],
            "motivo": "diferença de balanços não é variação de capital de giro reconciliada da DFC"}
