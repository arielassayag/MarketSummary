"""Margem EBIT somente entre fluxos de mesma janela, moeda e base.

Os valores reportados permanecem no pacote. Este módulo puro certifica a razão que pode
entrar no contexto e na projeção; não escolhe outro exercício para completar uma margem.
A política é ativada nos parâmetros e o caminho histórico não chama este módulo.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .reinvestimento import _periodo_valido

METODO = "periodo_moeda_base"
ITENS = ("receita", "ebit")


def _mapa(v: Any) -> Mapping[str, Any]:
    return v if isinstance(v, Mapping) else {}


def _numero(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _linha(p: Mapping[str, Any], item: str, ano: str | None) -> dict[str, Any]:
    if ano is None:
        valor = p.get(f"t.{item}")
        periodo = _mapa(p.get("periodos_fluxos")).get(item)
        moeda = _mapa(p.get("moedas_fluxos")).get(item)
        base = _mapa(p.get("bases_fluxos")).get(item)
        fonte = _mapa(p.get("fontes")).get(f"t.{item}")
    else:
        valor = _mapa(_mapa(p.get("historico")).get(item)).get(ano)
        periodo = _mapa(_mapa(p.get("historico_periodos")).get(item)).get(ano)
        moeda = _mapa(_mapa(p.get("historico_moedas")).get(item)).get(ano)
        base = _mapa(_mapa(p.get("historico_bases")).get(item)).get(ano)
        fonte = _mapa(_mapa(p.get("historico_fontes")).get(item)).get(ano)
    periodo_canonico = _periodo_valido(periodo)
    # A e TTM são ambos declarações canônicas de 12 meses. A janela comparável é
    # o fim desses 12 meses; a frequência reportada continua íntegra no diagnóstico.
    janela_12m = None if periodo_canonico is None else periodo_canonico.split("|")[1]
    return {"item": item, "valor": _numero(valor), "moeda_valor": p.get("moeda"),
            "periodo": periodo, "periodo_canonico": periodo_canonico, "fim_janela_12m": janela_12m,
            "moeda_fonte": moeda, "base_contabil": base,
            "fonte": deepcopy(dict(fonte)) if isinstance(fonte, Mapping) else None}


def _par(p: Mapping[str, Any], ano: str | None = None) -> dict[str, Any]:
    linhas = {k: _linha(p, k, ano) for k in ITENS}
    motivos = []
    for item, r in linhas.items():
        if r["valor"] is None:
            motivos.append(f"{item}: valor ausente ou não finito")
        if r["periodo_canonico"] is None:
            motivos.append(f"{item}: período de 12 meses não demonstrado")
        elif ano is not None and (not r["periodo_canonico"].startswith("A|")
                                 or r["periodo_canonico"].split("|")[1][:4] != ano):
            motivos.append(f"{item}: período anual não corresponde ao exercício {ano}")
        moeda = r["moeda_fonte"]
        if not isinstance(moeda, str) or re.fullmatch(r"[A-Z]{3}", moeda) is None:
            motivos.append(f"{item}: moeda da fonte não demonstrada")
        if r["base_contabil"] not in ("consolidado", "individual"):
            motivos.append(f"{item}: base contábil não demonstrada")
        if ano is not None:
            fonte = r["fonte"]
            # O preparador registra o valor convertido na mesma linha que fornece o histórico.
            # Sem essa ligação não há trilha que autorize usar o par na margem de ciclo.
            if fonte is None or _numero(fonte.get("valor_modelo")) != r["valor"]:
                motivos.append(f"{item}: proveniência histórica não corresponde ao valor")
    receita, ebit = (linhas[k] for k in ITENS)
    for campo, nome in (("fim_janela_12m", "janelas de 12 meses"),
                        ("moeda_fonte", "moedas"), ("base_contabil", "bases contábeis")):
        a, b = receita[campo], ebit[campo]
        if a is not None and b is not None and a != b:
            motivos.append(f"receita e EBIT com {nome} diferentes")
    if receita["valor"] is not None and receita["valor"] <= 0:
        motivos.append("receita não positiva: margem indisponível")
    margem = None if motivos else ebit["valor"] / receita["valor"]
    if margem is not None and not math.isfinite(margem):
        margem = None
        motivos.append("razão EBIT/receita não finita")
    return {"metodo": METODO, "status": "comparavel" if not motivos else "ausente",
            "margem": margem, "motivos": motivos,
            "motivo": "; ".join(motivos) or "receita e EBIT de mesma janela, moeda e base",
            "insumos": linhas}


def margens_alinhadas(p: Mapping[str, Any]) -> dict[str, Any]:
    """Ponte corrente e pares anuais auditáveis, sem modificar qualquer valor do pacote."""
    h = _mapa(p.get("historico"))
    anos = sorted(set(_mapa(h.get("receita"))) | set(_mapa(h.get("ebit"))))
    return {"metodo": METODO, "corrente": _par(p),
            "historico": {str(ano): _par(p, str(ano)) for ano in anos}}
