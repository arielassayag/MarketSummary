"""Modelo e decomposição de risco nativos; dados/configuração recebidos pelo chamador.

Exposições e pesos em fração; F e D são variâncias anuais, retornos diários em
fração. Estimar exige painel explícito e corte não posterior ao painel. Não há
collector, livro ou escrita nesta fachada.
"""
from cdp.risk.analytics import risk_decomposition as decompor_risco
from cdp.risk.model import estimate_risk_model as estimar_modelo_risco

__all__ = ["decompor_risco", "estimar_modelo_risco"]
