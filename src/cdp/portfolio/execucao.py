"""Execução no fechamento (MOC) com capacidade de liquidez — contrato congelado no W0
(dono: workstream D; consumidor: E no otimizador e na compliance).

Por linha ℓ, mercado m e pregão s (DESIGN §D.4):
``cap_ℓ(s) = mult(s) · [p_leilão · fatia_leilão(m) + p_pré · fatia_pré] · ADV_P25,20d(ℓ)``
(shorts × ``short_multiplier``); 0 se o mercado está fechado, se a linha não tem fechamento
oficial ou se o fechamento é anterior a ``prazo_decisao + buffer``. Volume desconhecido ⇒
capacidade 0 como RESTRIÇÃO (nunca um dado preenchido). Parâmetros em
``FundConfig.execution`` (:class:`cdp.config.ExecutionSection`).

Contrato relacionado em arquivo do dono (D): ``calendar.resumo_cronograma(cfg, hoje)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

    from ..config import FundConfig
    from ..contracts import BookEntry
    from ..market import MarketData


@dataclass(frozen=True)
class JanelaExecucao:
    """Janela de execução de um pregão de rebalanceamento (horários tz-aware).

    ``abertos``: MIC -> mercado aberto no pregão; ``fechamentos``: MIC -> fechamento oficial;
    ``corte_moc``: MIC -> corte de ordens MOC; ``prazo_decisao``: prazo efetivo
    ``min(teto local, fechamento mais cedo entre XNYS/BVMF/XMEX − buffer)``;
    ``fechamento_antecipado``: algum mercado relevante fecha mais cedo;
    ``multiplicador_capacidade``: 1,0 ou ``early_close_multiplier``."""

    sessao: date
    abertos: dict[str, bool]
    fechamentos: dict[str, datetime]
    corte_moc: dict[str, datetime]
    prazo_decisao: datetime
    fechamento_antecipado: bool
    multiplicador_capacidade: float


def janela_execucao(sessao: date, cfg: FundConfig) -> JanelaExecucao:
    """Janela do pregão ``sessao`` com os horários de ``cfg.execution.close_times`` (horário não
    verificado ⇒ mercado sem fechamento elegível)."""
    raise NotImplementedError("portfolio.execucao.janela_execucao: em implementação (workstream D)")


def capacidade_fechamento_usd(lines: pd.DataFrame, md: MarketData, janela: JanelaExecucao,
                              cfg: FundConfig, *, lado: Literal["long", "short"]) -> pd.Series:
    """Capacidade em USD por ticker no fechamento da janela (fórmula do módulo); ``0.0`` para
    linha sem volume conhecido, mercado fechado ou fechamento antes do prazo + buffer."""
    raise NotImplementedError(
        "portfolio.execucao.capacidade_fechamento_usd: em implementação (workstream D)")


def emissores_congelados(sides: pd.DataFrame, atual: BookEntry | None, janela: JanelaExecucao,
                         cfg: FundConfig) -> dict[str, str]:
    """Emissores sem linha negociável na janela (mercado local fechado sem ADR elegível, conforme
    ``execution.local_closed_policy``): ``issuer_id -> motivo``. O otimizador fixa ``w = w0``."""
    raise NotImplementedError(
        "portfolio.execucao.emissores_congelados: em implementação (workstream D)")


def fechamentos_necessarios(nocional_usd: float, capacidade_usd: float) -> float | None:
    """Fechamentos necessários para executar ``nocional_usd`` com ``capacidade_usd`` por
    fechamento; ``None`` quando a capacidade é zero ou desconhecida."""
    raise NotImplementedError(
        "portfolio.execucao.fechamentos_necessarios: em implementação (workstream D)")


__all__ = ["JanelaExecucao", "capacidade_fechamento_usd", "emissores_congelados",
           "fechamentos_necessarios", "janela_execucao"]
