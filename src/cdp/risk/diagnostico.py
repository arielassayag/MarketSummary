"""Comparação de κ_F em sombra, sem promoção para o mandato ou os gates.

O chamador declara modelo, configuração e unidade. A validação cobre apenas os
retornos consumidos por κ; não certifica custódia, PIT, B/F/D ou calibração.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

from ..config import FundConfig
from . import idio
from .types import RiskModel


@dataclass(frozen=True, slots=True)
class ComparacaoKappa:
    """Valores nativos e candidato diagnóstico; os limites não são um IC.

    ``valor_nativo_sombra`` conserva inclusive o fallback. Nesse caso,
    ``candidato_analitico`` é None, sem substituir dado ausente por zero.
    ``n_observacoes`` conta linhas, não observações válidas de cada fator.
    """

    corte: date
    unidade_retornos: Literal["decimal_diario"]
    config_hash: str
    config_sombra_hash: str
    modo_vigente: Literal["config", "analytic"]
    kappa_vigente: float
    origem_vigente: str
    valor_nativo_sombra: float
    origem_sombra: str
    candidato_disponivel: bool
    candidato_analitico: float | None
    formula_bruta: float | None
    t_ef: float | None
    k: int | None
    curtose_mediana: float | None
    curtose_usada: float | None
    limites_sombra: tuple[float, float]
    n_observacoes: int | None
    motivo: str | None


def _validar_insumos(model: RiskModel, cfg: FundConfig, unidade: str) -> None:
    if type(model) is not RiskModel or type(cfg) is not FundConfig:
        raise ValueError("Modelo e configuração devem ter os tipos nativos exatos")
    if type(unidade) is not str or unidade != "decimal_diario":
        raise ValueError("Unidade declarada deve ser decimal_diario")
    if type(model.as_of) is not date:
        raise ValueError("Corte deve ser uma data civil")
    escalares = (cfg.risk.second_order_inflation, *cfg.risk.second_order_inflation_bounds,
                 cfg.risk_model.halflife_factor_corr)
    if not all(math.isfinite(v) for v in escalares):
        raise ValueError("Escalares de configuração consumidos devem ser finitos")
    fr = model.factor_returns
    if fr is None:
        return
    if type(fr) is not pd.DataFrame:
        raise ValueError("Retornos devem ser um DataFrame nativo")
    if not fr.columns.is_unique or not all(type(c) is str for c in fr.columns):
        raise ValueError("Fatores devem ter nomes textuais únicos")
    for dtype in fr.dtypes:
        if not is_numeric_dtype(dtype) or is_bool_dtype(dtype) or is_complex_dtype(dtype):
            raise ValueError("Retornos devem ter dtypes numéricos reais, não booleanos")
    if np.isinf(fr.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("Retorno infinito não é dado ausente")
    if len(fr) == 0:
        return  # Sem datas observadas; aceitar também o RangeIndex vazio nativo.
    idx = fr.index
    if type(idx) is not pd.DatetimeIndex:
        raise ValueError("Índice deve ser DatetimeIndex diário")
    if idx.tz is not None or idx.hasnans or not idx.equals(idx.normalize()):
        raise ValueError("Índice diário deve ser civil, sem fuso, hora ou NaT")
    if not idx.is_unique or not idx.is_monotonic_increasing:
        raise ValueError("Índice diário deve ser único e ordenado")
    if len(idx) and idx[-1].date() > model.as_of:
        raise ValueError("Retorno posterior ao corte declarado")


def _finito_ou_ausente(valor: float) -> float | None:
    return float(valor) if math.isfinite(valor) else None


def comparar_kappa_sombra(
    model: RiskModel, cfg: FundConfig, *,
    unidade_retornos: Literal["decimal_diario"],
) -> ComparacaoKappa:
    """Compara o κ vigente com o ramo analítico nativo, somente em memória.

    A unidade diária decimal é declaração obrigatória, não comprovação externa.
    NaN permanece nos retornos. Histórico ausente, curtose indisponível e T_ef
    insuficiente geram candidato None com motivo e conservam o fallback nativo.
    Não há I/O, solver, escritor, default por diretório ou adaptação automática.
    """
    _validar_insumos(model, cfg, unidade_retornos)
    vigente, info_vigente = idio.kappa_f(model, cfg)
    sombra_cfg = cfg.with_overrides({"risk": {"second_order_inflation_mode": "analytic"}})
    sombra, info = idio.kappa_f(model, sombra_cfg)
    fr = model.factor_returns
    n_obs = None if fr is None else len(fr)
    k = None if fr is None or fr.empty else int(fr.iloc[-1].notna().sum())
    mediana = info.get("curtose_mediana")
    usada = None
    bruto = None
    t_ef = None
    if mediana is not None:
        usada = min(max(float(mediana), idio.KURTOSIS_CLIP[0]), idio.KURTOSIS_CLIP[1])
        bruto_nativo, t_nativo = idio.kappa_formula(
            info["k"], cfg.risk_model.halflife_factor_corr,
            cfg.risk_model.newey_west_lags, usada,
        )
        bruto = _finito_ou_ausente(bruto_nativo)
        t_ef = _finito_ou_ausente(t_nativo)
    disponivel = info["fonte"] == "analitico"
    motivo = None
    if not disponivel:
        if fr is None or fr.empty:
            motivo = "historico_ausente"
        elif k == 0:
            motivo = "sem_fatores_na_ultima_data"
        elif mediana is None:
            motivo = "curtose_indisponivel"
        else:
            motivo = "T_ef_insuficiente"
    return ComparacaoKappa(
        corte=model.as_of, unidade_retornos=unidade_retornos,
        config_hash=cfg.config_hash(), config_sombra_hash=sombra_cfg.config_hash(),
        modo_vigente=cfg.risk.second_order_inflation_mode,
        kappa_vigente=float(vigente), origem_vigente=info_vigente["fonte"],
        valor_nativo_sombra=float(sombra), origem_sombra=info["fonte"],
        candidato_disponivel=disponivel,
        candidato_analitico=float(sombra) if disponivel else None,
        formula_bruta=bruto, t_ef=t_ef, k=k,
        curtose_mediana=None if mediana is None else float(mediana),
        curtose_usada=usada,
        limites_sombra=tuple(float(v) for v in cfg.risk.second_order_inflation_bounds),
        n_observacoes=n_obs, motivo=motivo,
    )
