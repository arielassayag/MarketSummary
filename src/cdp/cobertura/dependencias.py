"""Prova conservadora de independência de capex/D&A nos modelos financeiros.

Este primeiro contrato só certifica a ausência desses dois itens nas famílias conhecidas.
Não tenta deduzir dependências por nomes de emissores nem pela ausência de um método no peso
final: todos os métodos configurados e reportados são examinados, inclusive dissidentes.
Uma estrutura não reconhecida conserva a severidade histórica do alerta.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .parametros import ParametrosCobertura

ITENS_CERTIFICAVEIS = frozenset({"capex", "d_a"})
_RAIZES = {
    "rim": "patrimônio, LPA/ROE, payout e ke",
    "rim_real": "patrimônio, LPA/ROE, payout, ke e inflação",
    "pb_justificado": "patrimônio, ROE sustentável, ke e crescimento terminal",
    "ddm": "LPA, payout, ROE sustentável, ke e crescimento terminal",
    "ddm_real": "LPA, payout, ROE sustentável, ke, crescimento terminal e inflação",
    "multiplo_justificado": "LPA, crescimento, ROE sustentável e ke",
    "regressao_pb_roe": "patrimônio e regressão de ROE, crescimento, beta e payout",
    "regressao_pl": "LPA e regressão de crescimento, beta e payout",
    "soma_partes": "NAV de participações externas, dívida/unidades e desconto histórico",
}
_FONTES_BETA = (
    "mediana dos betas de regressão de ",
    "regressão própria (sem pares suficientes)",
    "β setorial de Damodaran (sem regressão)",
)


def _finito(x: Any) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def dependencia_fluxos_financeiros(pac: Mapping[str, Any], mod: Mapping[str, Any],
                                  params: ParametrosCobertura) -> dict[str, Any]:
    """Certifica ``nao_usado`` somente no contrato financeiro conhecido; senão indeterminado.

Capex/D&A não entram no beta financeiro, ke, norma de ROE ou prêmio implícito. D&A pode
produzir o diagnóstico DL/EBITDA, mas a regressão que o consome exclui financeiras. SOTP
consome valores das investidas externas, não os fluxos consolidados da própria holding.
"""
    out: dict[str, Any] = {"schema": "cdp.cobertura.dependencias_fluxos/v1",
                           "itens": sorted(ITENS_CERTIFICAVEIS), "classificacao": "indeterminado",
                           "metodos": [], "caminhos": []}

    def conservar(motivo: str) -> dict[str, Any]:
        return {**out, "motivo": motivo}

    if pac.get("financeira") is not True:
        return conservar("independência de capex/D&A só certificada para modelos financeiros")
    try:
        pesos = params.pesos(str(pac["arquetipo"]))
    except (KeyError, TypeError, ValueError):
        return conservar("família de métodos configurada desconhecida")
    ms = mod.get("metodos")
    if not isinstance(ms, list) or not ms or any(not isinstance(m, Mapping) for m in ms):
        return conservar("métodos reportados ausentes ou desconhecidos")
    nomes = [m.get("m") for m in ms]
    if any(not isinstance(m, str) for m in nomes):
        return conservar("identificação de método reportado desconhecida")
    if any(not _finito(m.get("peso")) or float(m["peso"]) < 0 for m in ms):
        return conservar("peso de método reportado desconhecido")
    metodos = sorted(set(pesos) | set(nomes))
    out["metodos"] = metodos
    if not pesos or not set(pesos).issubset(nomes) or any(not _finito(w) or w < 0 for w in pesos.values()):
        return conservar("conjunto completo dos métodos configurados não demonstrado")
    desconhecidos = [m for m in metodos if m not in _RAIZES]
    if desconhecidos:
        return conservar("dependência de fluxo ou método não certificada: " + ", ".join(desconhecidos))
    cc = mod.get("custo_capital")
    if not isinstance(cc, Mapping) or any(k not in cc for k in ("kd", "wacc", "peso_divida", "beta_fonte")):
        return conservar("custo de capital financeiro incompleto ou desconhecido")
    if any(cc[k] is not None for k in ("kd", "wacc", "peso_divida")):
        return conservar("custo da dívida ou WACC presente: dependência financeira não certificada")
    if not all(_finito(cc.get(k)) for k in ("ke", "beta", "imposto")):
        return conservar("direcionadores do custo de capital financeiro desconhecidos")
    fonte_beta = str(cc["beta_fonte"])
    if not (fonte_beta.startswith(_FONTES_BETA[0]) or fonte_beta in _FONTES_BETA[1:]):
        return conservar("origem do beta financeiro desconhecida")
    var_porte = params.sec("persistencia_roe").get("tamanho_variavel", "ln_pl_usd")
    if var_porte not in ("ln_pl_usd", "ln_mcap_usd"):
        return conservar("dependência transversal de porte não certificada: " + str(var_porte))
    if "soma_partes" in metodos:
        sp = pac.get("soma_partes")
        if not isinstance(sp, Mapping) or not _finito(sp.get("nav")):
            return conservar("NAV da soma das partes desconhecido")
        partes = sp.get("partes")
        if not isinstance(partes, list) or not partes:
            return conservar("dependências transitivas da soma das partes desconhecidas")
        ids = set()
        for p in partes:
            if not isinstance(p, Mapping) or not isinstance(p.get("emissor"), str) or not p["emissor"] \
                    or p["emissor"] == pac.get("issuer_id") or not _finito(p.get("valor_participacao")):
                return conservar("participação externa não demonstrada: dependência transitiva conservada")
            ids.add(p["emissor"])
        visao = sp.get("visao_casa")
        if visao is not None:
            if not isinstance(visao, Mapping) or not _finito(visao.get("fator")) \
                    or not isinstance(visao.get("partes"), list):
                return conservar("dependências da visão da casa sobre as investidas desconhecidas")
            for p in visao["partes"]:
                if not isinstance(p, Mapping) or p.get("emissor") not in ids or not _finito(p.get("razao_v0_p0")):
                    return conservar("dependência transitiva da visão da casa não certificada")
    out["caminhos"] = [f"{m} → {_RAIZES[m]} (sem capex/D&A do emissor)" for m in metodos] + [
        "ke financeiro → beta de regressão/setorial, ERP, CRP e inflação; sem kd/WACC",
        "contexto financeiro → ROE, LPA, crescimento, beta, payout e porte patrimonial/de mercado",
        "D&A → DL/EBITDA diagnóstico; regressão EV/Receita e RR observado excluem financeiras",
    ]
    return {**out, "classificacao": "nao_usado",
            "motivo": "capex/D&A do emissor não alimentam os métodos financeiros nem seus intermediários econômicos"}
