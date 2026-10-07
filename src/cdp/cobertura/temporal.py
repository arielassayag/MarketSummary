"""Dois relógios explícitos: base de preços e conhecimento do modelo.

A política ausente conserva o contrato histórico. A data civil de conhecimento
não é uma prova de publicação intradiária; o catálogo RI continua limitado pelo
instante exato de conhecimento. Nenhuma captura é retrodatada.
"""
from __future__ import annotations

from datetime import date, datetime

from ..data.publico_arquivo import data_local
from ..data.publico_resultados import instante

METODO = "base_preco_conhecimento_explicitos"


def ativo(params) -> bool:
    metodo = params.sec("projecao").get("resultado_corte_metodo")
    if metodo not in (None, METODO):
        raise ValueError(f"Método de corte temporal desconhecido: {metodo!r}")
    return metodo == METODO


def construir(base_preco: date, conhecimento_ate: datetime) -> dict[str, str]:
    corte = instante(conhecimento_ate)
    modelo = data_local(corte)
    if base_preco > modelo:
        raise ValueError("corte temporal: base de preços posterior ao conhecimento")
    return {"metodo": METODO, "base_preco": base_preco.isoformat(),
            "data_modelo": modelo.isoformat(), "conhecimento_ate": corte.isoformat()}


def validar(corte, *, as_of: str | None = None) -> dict[str, str]:
    obrigatorios = {"metodo", "base_preco", "data_modelo", "conhecimento_ate"}
    etapas = {"coleta_inicio", "coleta_fim"}
    if (not isinstance(corte, dict) or not obrigatorios <= set(corte)
            or set(corte) - obrigatorios not in (set(), etapas)):
        raise ValueError("corte temporal: contrato ausente ou incompleto")
    if corte["metodo"] != METODO:
        raise ValueError("corte temporal: política desconhecida")
    refeito = construir(date.fromisoformat(corte["base_preco"]), instante(corte["conhecimento_ate"]))
    if etapas <= set(corte):
        inicio, fim = instante(corte["coleta_inicio"]), instante(corte["coleta_fim"])
        if not inicio <= fim <= instante(corte["conhecimento_ate"]):
            raise ValueError("corte temporal: etapas de coleta incompatíveis")
        refeito.update(coleta_inicio=inicio.isoformat(), coleta_fim=fim.isoformat())
    if corte != refeito or (as_of is not None and corte["data_modelo"] != as_of):
        raise ValueError("corte temporal: datas ou instante incompatíveis")
    return refeito
