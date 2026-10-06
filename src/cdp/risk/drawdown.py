"""Escada de drawdown aplicada ao risco efetivamente tomado (``drawdown.risk_reference``).

Com ``"normal_book_vol"`` a escada limita a VOLATILIDADE EX-ANTE da carteira:
``σ_teto = m(estágio)·σ_ref``, em que ``σ_ref`` é a vol ex-ante da MESMA tentativa resolvida no
estágio normal (uma resolução extra; sem ela, a vol da carteira atual) e

- stop suave: ``m = soft_degross_multiplier`` (0,75);
- stop duro: ``m = degross_multiplier`` (0,50);
- stop-out: ``m = max(0, 1 − |stop_out|/D_max)`` com ``D_max = |hard_stop|/(1 − degross_multiplier)``
  (0,25 com −7,5% e D_max = 10%) — a mesma reta de Grossman–Zhou que passa pelos dois stops.

Sem memória e sem composição: ``σ_ref`` é recalculado a cada semana no estágio normal, então o
risco volta sozinho quando o drawdown se recupera. Drawdown desconhecido ⇒ ``m = 1`` (a postura
já fica limitada a neutra pelo agente PM). Com ``"mandate_gross"`` (legado) nada muda aqui.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..config import FundConfig

STAGES = ("normal", "soft_stop", "hard_stop", "stop_out", "desconhecido")


def stage(drawdown: float | None, cfg: FundConfig) -> str:
    """Estágio da escada (mesma regra de ``research.pm_agent.ladder_stage``)."""
    from ..research.pm_agent import ladder_stage

    return ladder_stage(drawdown, cfg)


def d_max(cfg: FundConfig) -> float:
    """Perda em que a reta de Grossman–Zhou zera o risco: ``|hard_stop|/(1 − degross)``."""
    d = cfg.drawdown
    return abs(d.hard_stop) / (1.0 - d.degross_multiplier) if d.degross_multiplier < 1 \
        else float("inf")


def stage_multiplier(stage_name: str, cfg: FundConfig) -> float:
    """Multiplicador do risco por estágio (1,0 no normal ou desconhecido)."""
    d = cfg.drawdown
    if stage_name == "soft_stop":
        return float(d.soft_degross_multiplier)
    if stage_name == "hard_stop":
        return float(d.degross_multiplier)
    if stage_name == "stop_out":
        dm = d_max(cfg)
        return max(0.0, 1.0 - abs(d.stop_out) / dm) if dm != float("inf") \
            else float(d.degross_multiplier)
    return 1.0


def vol_cap(stage_name: str, sigma_ref: float | None, cfg: FundConfig) -> float | None:
    """``m·σ_ref`` fora do estágio normal; ``None`` no normal, sem referência ou no legado."""
    if cfg.drawdown.risk_reference != "normal_book_vol":
        return None
    m = stage_multiplier(stage_name, cfg)
    if m >= 1.0 or sigma_ref is None or not sigma_ref > 0:
        return None
    return max(m * float(sigma_ref), 1e-6)


__all__ = ["STAGES", "d_max", "stage", "stage_multiplier", "vol_cap"]
