"""Ponte do preço-alvo entre dois snapshots (substituição sequencial, ordem fixa).

Parte do pacote de insumos e do contexto do snapshot anterior e troca, um grupo por vez, pelos
do snapshot atual: rolagem (data de referência) → estimativas (demonstrativos, consenso,
dividendos) → parâmetros de valuation (taxa livre de risco e contexto setorial) → estrutura de
capital → câmbio → preço → mix de métodos (demais mudanças). Cada componente é a variação do
preço-alvo determinístico na troca; o resíduo é a diferença de reprocessamento (alvo anterior
publicado × alvo anterior refeito com o código e a configuração atuais) e fecha a conta:
``alvo anterior + Σ componentes + resíduo = alvo novo``. O componente dominante dá o motivo.
Um componente sem alvo intermediário reprodutível fica ``None`` (n/d), nunca zero, e o seu
efeito é somado explicitamente ao próximo componente calculável (registrado em ``notas``).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from .formato import r6

GRUPOS: dict[str, tuple[str, ...]] = {
    "rolagem": ("as_of",),
    "estimativas": ("eps_fy1", "eps_fy2", "eps_ttm", "bvps", "dps_12m", "dps_fonte", "g_receita_fy1",
                    "g_receita_fy2", "g_receita_historico", "historico", "receita_ano_anterior",
                    "consenso", "tem_demonstrativos", "pit_ok", "max_data_publicacao"),
    "estrutura_capital": ("divida_liquida", "divida_bruta", "minoritarios", "unidades", "valor_mercado",
                          "d_e_mercado", "acoes_por_linha", "status_unidades", "soma_partes"),
    "cambio": ("fator_moeda", "fx_usd_moeda", "status_moeda"),
    "preco": ("preco", "data_preco", "defasagem_preco_dias", "vol_12m", "beta_regressao",
              "beta_regressao_semanas", "adtv_usd"),
}
MOTIVOS = {"rolagem": "ROLAGEM", "estimativas": "RESULTADO", "parametros": "JUROS_MACRO",
           "estrutura_capital": "ESTRUTURA_CAPITAL", "cambio": "CAMBIO", "preco": "PRECO",
           "metodos": "MUDANCA_METODO", "residuo": "CORRECAO_MODELO"}
ORDEM = ("rolagem", "estimativas", "parametros", "estrutura_capital", "cambio", "preco", "metodos")

Avaliar = Callable[[Mapping[str, Any], Mapping[str, Any], float | None], float | None]


def ponte(tp_ant: float, pac_ant: Mapping[str, Any], pac_novo: Mapping[str, Any],
          ctx_ant: Mapping[str, Any], ctx_novo: Mapping[str, Any], rf_ant: float | None,
          rf_novo: float | None, tp_novo: float, avaliar: Avaliar) -> dict[str, Any]:
    """``avaliar(pacote, contexto, rf)`` devolve o preço-alvo determinístico (ou ``None``)."""
    base = avaliar(pac_ant, ctx_ant, rf_ant)
    if base is None:
        return {"componentes": None, "motivo": "MUDANCA_METODO", "alvo_anterior": r6(tp_ant),
                "alvo_novo": r6(tp_novo), "nota": "modelo anterior sem preço-alvo reprodutível"}
    pac: dict[str, Any] = dict(pac_ant)
    ctx, rf = ctx_ant, rf_ant
    ultimo = base
    comp: dict[str, float | None] = {}
    notas: list[str] = []
    pendentes: list[str] = []
    for nome in ORDEM:
        if nome == "parametros":
            ctx, rf = ctx_novo, rf_novo
        elif nome == "metodos":
            pac = dict(pac_novo)
        else:
            pac.update({k: pac_novo.get(k) for k in GRUPOS[nome]})
            if nome == "estimativas":
                for k in set(pac) | set(pac_novo):
                    if k.startswith("t."):
                        pac[k] = pac_novo.get(k)
        v = avaliar(pac, ctx, rf)
        if v is None:
            # componente sem alvo intermediário: n/d; o efeito entra no próximo passo calculável
            comp[nome] = None
            pendentes.append(nome)
            continue
        comp[nome] = v - ultimo
        if pendentes:
            notas.append(f"{nome} inclui o efeito de {', '.join(pendentes)} (sem alvo intermediário reprodutível)")
            pendentes = []
        ultimo = v
    if pendentes:
        notas.append(f"resíduo inclui o efeito de {', '.join(pendentes)} (sem alvo intermediário reprodutível)")
    comp["residuo"] = (tp_novo - ultimo) + (base - tp_ant)
    validos = {k: v for k, v in comp.items() if v is not None and math.isfinite(v)}
    dom = max(validos, key=lambda k: abs(validos[k])) if validos else "residuo"
    return {"componentes": {k: (None if v is None else r6(v)) for k, v in comp.items()}, "motivo": MOTIVOS[dom],
            "alvo_anterior": r6(tp_ant), "alvo_novo": r6(tp_novo), "notas": notas,
            "residuo_relativo": r6(abs(comp["residuo"]) / abs(tp_novo) if tp_novo else None)}


__all__ = ["GRUPOS", "MOTIVOS", "ORDEM", "ponte"]
