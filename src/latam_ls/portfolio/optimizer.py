"""Otimizador convexo da carteira long/short net neutral (cvxpy + CLARABEL).

Problema (pesos ``w`` em fração do NAV, separados em perna comprada ``l ≥ 0`` e vendida
``s ≥ 0`` com ``w = l − s``)::

    max  αᵀw − (52/H)·custo(l − l₀, s − s₀) − aluguelᵀs − λ·risco(w)

    risco(w) = ‖Lᵀ(Bᵀw)‖² + ‖√D ⊙ w‖²      (F = L Lᵀ, F corrigida para PSD)

    s.a. |Σw| ≤ net_max                      (net neutral)
         |βᵀw| ≤ beta_max
         √risco(w) ≤ σ_alvo                  (meta de vol; nunca relaxada)
         |Σ_{i∈país} w_i| ≤ país_max,  |Σ_{i∈setor} w_i| ≤ setor_max
         |B_estiloᵀw| ≤ estilo_max            (todos os estilos, inclusive ``beta``)
         Σ(l + s) ≤ gross_max
         0 ≤ l ≤ max_long,  0 ≤ s ≤ max_short (liquidez, squeeze, visões, mandato)
         |w − w₀| ≤ max_trade                 (dias de execução × participação × ADTV)
         min(w₀ − m, 0) ≤ w ≤ max(w₀ + m, 0)  (m = ``max_trade_liq``: aumentos limitados pela
                                               liquidez; reduções até zero sempre permitidas)
         Σ|w − w₀| ≤ turnover_max             (fora da inception)

Meta de vol: por padrão é um teto (``risk_target_mode="cap"``); o modo ``"match"`` calibra a
escala do alpha para que a carteira atinja a meta (ver :func:`optimize`).

Complementaridade: a separação ``w = l − s`` é uma relaxação convexa. Como o impacto é
superaditivo (|t|^1,5), o solver pode "dividir" uma redução/inversão entre as duas pernas
(l > 0 e s > 0 no mesmo emissor), subestimando o custo real da ordem líquida. Toda solução
passa por um reparo: emissores com as duas pernas abertas têm a perna oposta ao sinal líquido
fixada em zero e o problema é resolvido de novo (a solução líquida anterior continua viável).

Duas passadas: posições com |w| < ``min_position_weight`` são fixadas em zero e o problema é
resolvido de novo (até ``MAX_PASSES`` vezes). Se o problema for inviável, aplica-se a escada
de relaxamento documentada (turnover → estilos ×2 → país/setor ×1,5 → beta ×2), sempre
registrada. Net exposure, teto de vol, limites por nome, squeeze e liquidez nunca são relaxados.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import cvxpy as cp
import numpy as np
import pandas as pd

from ..config import FundConfig
from ..contracts import OptimizerDiagnostics
from ..risk.types import STYLE_FACTORS, RiskModel
from .costs import IMPACT_EXPONENT, CostModel, estimate_rebalance_costs

TOL = 1e-6
BINDING_REL_SLACK = 1e-4
WEIGHT_NOISE = 1e-9
MAX_PASSES = 3
BOX_TOL = 1e-7               # perna "aberta" para o reparo de complementaridade
MAX_BOX_REPAIRS = 6
WEEKS_PER_YEAR = 52.0
PSD_EIG_FLOOR = 1e-14
SOLVER_ORDER: tuple[str, ...] = ("CLARABEL", "SCS", "ECOS")
# Tolerâncias compatíveis com a escala do problema: o objetivo é fração do NAV ao ano
# (~1e-3), então 1e-7 de gap absoluto ≈ 0,001 bp. A viabilidade fica estrita (1e-8).
SOLVER_OPTIONS: dict[str, dict] = {
    "CLARABEL": {"tol_gap_abs": 1e-7, "tol_gap_rel": 1e-6, "tol_feas": 1e-8, "max_iter": 300},
    "SCS": {"eps_abs": 1e-7, "eps_rel": 1e-7, "max_iters": 50_000},
    "ECOS": {"abstol": 1e-8, "reltol": 1e-7, "feastol": 1e-8},
}
SQUEEZE_BUCKETS = ("LOW", "MEDIUM", "HIGH", "NA")
UNKNOWN_GROUP = "NA"

_OK = {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}
_INFEASIBLE = {cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE}

_ALLOWED_OVERRIDES = {
    "vol_target", "vol_target_annual", "gross_max", "gross_multiplier", "risk_aversion",
    "max_weekly_turnover", "exclude_issuers", "risk_target_mode", "themes", "exposure_limits",
}
RISK_TARGET_MODES = ("cap", "match")
MATCH_REL_TOL = 0.005        # "na meta": vol ≥ 99,5% da meta (o teto continua duro)
MAX_ALPHA_SCALE = 64.0
MATCH_BISECT_STEPS = 8

RELAXATION_STEPS: tuple[tuple[str, str], ...] = (
    ("turnover", "Relaxamento 1: limite de turnover semanal removido"),
    ("style", "Relaxamento 2: limites de exposição a estilos multiplicados por 2"),
    ("country_sector", "Relaxamento 3: limites líquidos de país/setor multiplicados por 1,5"),
    ("beta", "Relaxamento 4: limite de beta multiplicado por 2"),
)


class OptimizationError(RuntimeError):
    """Falha da otimização (inviável após a escada de relaxamento ou erro de todos os solvers)."""

    def __init__(self, message: str, diagnostics: OptimizerDiagnostics | None = None,
                 relaxations: list[str] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics
        self.relaxations = relaxations or []


@dataclass(frozen=True)
class OptimizationResult:
    weights: pd.Series
    ex_ante_vol: float
    diagnostics: OptimizerDiagnostics
    relaxations: list[str]
    expected_alpha: float
    expected_cost: float
    borrow_cost_annual: float = 0.0
    trades: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    factor_exposures: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    vol_target: float = float("nan")
    passes: int = 1
    alpha_scale: float = 1.0


# ==========================================================
# Utilidades de risco (PSD) — também usadas pela compliance
# ==========================================================

def psd_factor_root(factor_cov: pd.DataFrame) -> np.ndarray:
    """Raiz ``L`` (k × r) com ``L Lᵀ = F₊`` (autovalores negativos zerados)."""
    F = factor_cov.to_numpy(dtype=float)
    if not np.all(np.isfinite(F)):
        raise ValueError("Covariância fatorial com valores não finitos.")
    F = 0.5 * (F + F.T)
    eigval, eigvec = np.linalg.eigh(F)
    scale = max(float(np.max(np.abs(eigval))), 1.0e-300)
    keep = eigval > PSD_EIG_FLOOR * scale
    return eigvec[:, keep] * np.sqrt(eigval[keep])


@dataclass(frozen=True)
class RiskParts:
    total_var: float
    factor_var: float
    specific_var: float
    contributions: pd.Series      # contribuição de cada emissor para a variância total (Euler)
    factor_exposures: pd.Series   # Bᵀw

    @property
    def vol(self) -> float:
        return float(np.sqrt(max(self.total_var, 0.0)))

    @property
    def factor_share(self) -> float:
        return self.factor_var / self.total_var if self.total_var > 0 else float("nan")


def portfolio_risk_parts(w: pd.Series, model: RiskModel) -> RiskParts:
    """Decomposição de risco ex-ante (anual) com F corrigida para PSD.

    Emissores fora do modelo são erro explícito (sem risco zero silencioso).
    """
    w = pd.to_numeric(w, errors="coerce")
    if w.isna().any():
        raise ValueError("Pesos com NaN na decomposição de risco.")
    nz = w[w != 0]
    extra = sorted(set(nz.index) - set(model.exposures.index))
    if extra:
        raise KeyError(f"Pesos para emissores fora do modelo de risco: {extra}")
    ids = list(nz.index)
    factors = model.factor_names
    if not ids:
        zero_x = pd.Series(0.0, index=factors)
        return RiskParts(0.0, 0.0, 0.0, pd.Series(dtype=float), zero_x)
    B = model.exposures.loc[ids, factors].to_numpy(dtype=float)
    D = model.specific_var.reindex(ids).to_numpy(dtype=float)
    if not (np.all(np.isfinite(B)) and np.all(np.isfinite(D))):
        raise ValueError("Exposições ou variância específica não finitas para emissores com peso.")
    L = psd_factor_root(model.factor_cov.loc[factors, factors])
    wv = nz.to_numpy(dtype=float)
    x = B.T @ wv
    Lx = L.T @ x
    fvar = float(Lx @ Lx)
    svar = float(np.sum(D * wv ** 2))
    sigma_w = B @ (L @ Lx) + D * wv
    total = fvar + svar
    contrib = wv * sigma_w / total if total > 0 else np.full(len(ids), np.nan)
    return RiskParts(total, fvar, svar, pd.Series(contrib, index=ids),
                     pd.Series(x, index=factors))


def model_implied_betas(model: RiskModel, market_w: pd.Series) -> pd.Series:
    """β_i = (Σm)_i / (mᵀΣm) usando o modelo de risco e os pesos de mercado ``m``.

    Emissores sem exposições ou variância específica finitas ficam com β ``NaN`` (nunca risco
    específico zero) e saem da carteira de mercado, que é renormalizada nos nomes cobertos.
    """
    factors = model.factor_names
    ids = model.exposures.index
    B_all = model.exposures[factors].to_numpy(dtype=float)
    D_all = pd.to_numeric(model.specific_var.reindex(ids), errors="coerce").to_numpy(dtype=float)
    covered = np.all(np.isfinite(B_all), axis=1) & np.isfinite(D_all) & (D_all >= 0)
    m = pd.to_numeric(market_w, errors="coerce").dropna()
    m = m[m.index.isin(ids[covered]) & (m > 0)]
    if m.empty or m.sum() <= 0:
        raise ValueError("Pesos de mercado vazios ou não positivos para o beta implícito.")
    m = m / m.sum()
    B = B_all[covered]
    D = D_all[covered]
    L = psd_factor_root(model.factor_cov.loc[factors, factors])
    # Nomes cobertos sem peso de mercado: peso zero na carteira de mercado (não são dado ausente).
    mv = m.reindex(ids[covered]).fillna(0.0).to_numpy()
    Lx = L.T @ (B.T @ mv)
    sigma_m = B @ (L @ Lx) + D * mv
    var_m = float(mv @ sigma_m)
    if not var_m > 0:
        raise ValueError("Variância do portfólio de mercado não positiva.")
    out = pd.Series(np.nan, index=ids, dtype=float)
    out.iloc[np.flatnonzero(covered)] = sigma_m / var_m
    return out


# ==========================================================
# Restrições por ativo
# ==========================================================

def _as_bool(s: pd.Series, default: bool) -> pd.Series:
    def conv(v: object) -> bool:
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        return str(v).strip().lower() in {"true", "1", "yes", "sim", "y"}
    return s.map(conv).astype(bool)


def _has_text(s: pd.Series) -> pd.Series:
    return s.map(lambda v: isinstance(v, str) and v.strip() not in ("", "nan", "None"))


def _clean_current(current: pd.Series | None) -> pd.Series:
    if current is None:
        return pd.Series(dtype=float)
    cur = pd.to_numeric(current, errors="coerce")
    if cur.isna().any():
        raise ValueError("Pesos atuais com NaN: posição desconhecida não pode virar zero.")
    cur = cur.astype(float)
    cur.index = cur.index.map(str)
    if cur.index.duplicated().any():
        raise ValueError("Pesos atuais com emissores duplicados.")
    return cur


def _col(df: pd.DataFrame | None, name: str, idx: pd.Index, default: object = np.nan) -> pd.Series:
    if df is None or name not in df.columns:
        return pd.Series([default] * len(idx), index=idx, dtype=object)
    return df[name].reindex(idx)


def normalize_squeeze_bucket(bucket: pd.Series) -> pd.Series:
    """Bucket de squeeze normalizado; ausente ou desconhecido ⇒ ``NA`` (tratado como MEDIUM)."""
    b = bucket.map(lambda v: str(v).strip().upper() if isinstance(v, str) else "NA")
    return b.where(b.isin(SQUEEZE_BUCKETS), "NA")


def build_asset_constraints(
    issuers: Sequence[str], sides: pd.DataFrame, squeeze: pd.DataFrame | None,
    view_constraints: pd.DataFrame | None, betas: pd.Series | None,
    panel_assets: pd.DataFrame, cfg: FundConfig, nav: float,
    current: pd.Series | None = None, inception: bool = False,
) -> pd.DataFrame:
    """Limites por emissor (frações do NAV) para o otimizador e a compliance.

    Colunas principais: ``can_long``, ``can_short``, ``max_long``, ``max_short`` (tetos
    positivos), ``max_trade`` (teto de |Δw|), ``borrow_fee``, ``beta``, ``country``, ``sector``,
    ``reasons``. Colunas auxiliares: ``squeeze_bucket``, ``shortable``, ``view_no_long``,
    ``view_no_short``, ``view_max_abs``, ``adtv_long_usd``, ``adtv_short_usd``, ``current``,
    ``max_trade_liq`` (teto de negociação só pela liquidez, sem o piso de saída), ``flags``.

    Regras:
    - ``max_long = min(max_long_weight, part·ADTV_long·dias_long/NAV, teto da visão)``.
    - ``max_short = min(max_short_weight, part_short·ADTV_short·dias_short/NAV, teto da visão)``
      × multiplicador se squeeze MEDIUM/NA (``part_short`` = ``short_participation_rate``); zero se HIGH, sem aluguel, aluguel acima do limite,
      market cap abaixo do mínimo (ou ausente), visão ``no_short`` ou emissor inelegível.
    - ``max_trade = part·ADTV_ref·dias_exec/NAV`` (ADTV_ref = menor ADTV entre as linhas
      utilizáveis — conservador), nunca abaixo de |peso atual| (permite zerar). O otimizador
      usa ``max_trade_liq`` (sem o piso) para limitar AUMENTOS: o piso serve só para sair.
    - Emissores com posição atual entram mesmo fora de ``issuers`` (para poder sair).
    """
    if not nav > 0:
        raise ValueError("NAV precisa ser positivo.")
    rk, liq, sh, sq = cfg.risk, cfg.liquidity, cfg.shorting, cfg.squeeze
    cur = _clean_current(current)
    ids = sorted(set(map(str, issuers)) | set(cur.index[cur != 0].map(str)))
    idx = pd.Index(ids, name="issuer_id")
    # Emissor sem posição atual tem peso zero (ausência de posição, não dado faltante).
    cur = cur.reindex(idx).fillna(0.0)
    reasons: dict[str, list[str]] = {i: [] for i in ids}
    flags: dict[str, list[str]] = {i: [] for i in ids}

    def tag(mask: pd.Series, token: str, acc: dict[str, list[str]] = reasons) -> None:
        for i in mask.index[mask.to_numpy(dtype=bool)]:
            acc[i].append(token)

    # --- elegibilidade (painel) ---
    in_panel = pd.Series(idx.isin(panel_assets.index), index=idx)
    tag(~in_panel, "fora_do_painel")
    if "eligible" in panel_assets.columns:
        eligible = _as_bool(panel_assets["eligible"].reindex(idx), default=False) & in_panel
    else:
        eligible = in_panel.copy()
    excl = _col(panel_assets, "exclusion_reason", idx, "")
    for i in idx[in_panel & ~eligible]:
        motive = str(excl.get(i) or "").replace(";", "+") or "sem_motivo"
        reasons[i].append(f"inelegivel:{motive}")

    country = _col(panel_assets, "country", idx).map(
        lambda v: v if isinstance(v, str) and v else UNKNOWN_GROUP)
    sector = _col(panel_assets, "sector", idx).map(
        lambda v: v if isinstance(v, str) and v else UNKNOWN_GROUP)

    # --- visões (apenas restritivas) ---
    view_no_long = _as_bool(_col(view_constraints, "no_long", idx), default=False)
    view_no_short = _as_bool(_col(view_constraints, "no_short", idx), default=False)
    view_max = pd.to_numeric(_col(view_constraints, "max_abs_weight", idx), errors="coerce")
    view_max = view_max.where(view_max >= 0)
    tag(view_no_long, "visao_no_long")
    tag(view_no_short, "visao_no_short")
    tag(view_max.notna(), "visao_teto_peso")

    # --- linhas e liquidez ---
    has_long = _has_text(_col(sides, "long_ticker", idx))
    has_short = _has_text(_col(sides, "short_ticker", idx))
    adtv_long = pd.to_numeric(_col(sides, "adtv_long_usd", idx), errors="coerce")
    adtv_long = adtv_long.where(adtv_long > 0)
    adtv_short = pd.to_numeric(_col(sides, "adtv_short_usd", idx), errors="coerce")
    adtv_short = adtv_short.where(adtv_short > 0)
    tag(~has_long, "sem_linha_long")
    tag(has_long & adtv_long.isna(), "adtv_long_ausente")

    part = liq.participation_rate
    liq_long = (part * adtv_long * liq.max_days_to_liquidate_long / nav).fillna(0.0)
    max_long = np.minimum(rk.max_long_weight, liq_long)
    max_long = max_long.where(view_max.isna(), np.minimum(max_long, view_max))
    max_long = max_long.where(has_long & eligible & ~view_no_long, 0.0)

    # --- short: aluguel, custo, porte, squeeze ---
    lendable = _as_bool(_col(sides, "can_short", idx), default=False)
    tag(has_short & ~lendable, "sem_aluguel")
    tag(~has_short, "sem_linha_short")
    fee = pd.to_numeric(_col(sides, "borrow_fee_annual", idx), errors="coerce")
    short_type = _col(sides, "short_line_type", idx).map(lambda v: str(v).upper())
    gc = pd.Series(np.where(short_type.str.startswith("LOCAL"), sh.gc_borrow_fee_br,
                            sh.gc_borrow_fee_us), index=idx)
    impute_fee = lendable & has_short & fee.isna()
    tag(impute_fee, "aluguel_gc_estimado", flags)
    fee = fee.where(~impute_fee, gc)
    fee_high = fee > sh.max_borrow_fee
    tag(lendable & fee_high, "aluguel_acima_limite")

    mcap = pd.to_numeric(_col(panel_assets, "market_cap_usd", idx), errors="coerce")
    mcap_missing = mcap.isna()
    mcap_low = mcap < sh.min_market_cap_short_usd
    tag(has_short & lendable & mcap_missing, "mcap_ausente_short")
    tag(has_short & lendable & mcap_low, "mcap_baixo_short")

    bucket = normalize_squeeze_bucket(_col(squeeze, "bucket", idx))
    tag(bucket == "HIGH", "squeeze_alto")
    tag(bucket == "MEDIUM", "squeeze_medio_teto")
    tag(bucket == "NA", "squeeze_na_teto")

    shortable = has_short & lendable & ~mcap_missing & ~mcap_low & eligible
    tag(has_short & lendable & adtv_short.isna(), "adtv_short_ausente")
    # Shorts: participação própria do mandato (mais conservadora), coerente com a compliance.
    liq_short = (liq.short_participation_rate * adtv_short * liq.max_days_to_liquidate_short
                 / nav).fillna(0.0)
    max_short = np.minimum(rk.max_short_weight, liq_short)
    max_short = max_short.where(view_max.isna(), np.minimum(max_short, view_max))
    mult = np.where(bucket.isin(["MEDIUM", "NA"]), sq.medium_short_cap_multiplier, 1.0)
    max_short = max_short * mult
    short_ok = shortable & ~fee_high & ~view_no_short & (bucket != "HIGH")
    max_short = max_short.where(short_ok, 0.0)

    # --- negociação (execução da semana) ---
    days_exec = liq.max_trade_days_inception if inception else liq.max_trade_days_weekly
    adtv_ref = adtv_long.where(has_long)
    adtv_ref = pd.Series(np.fmin(adtv_ref, adtv_short.where(short_ok)), index=idx)
    # ADTV de negociação ausente ⇒ nenhum aumento (exclusão sinalizada); reduzir é permitido.
    max_trade_liq = (part * adtv_ref * days_exec / nav)
    tag(adtv_ref.isna(), "sem_adtv_negociacao")
    max_trade_liq = max_trade_liq.fillna(0.0)
    max_trade = np.maximum(max_trade_liq, cur.abs())

    # --- beta previsto ---
    beta = pd.to_numeric(betas.reindex(idx), errors="coerce") if betas is not None \
        else pd.Series(np.nan, index=idx)
    tag(beta.isna(), "beta_imputado_1", flags)
    beta = beta.fillna(1.0)

    out = pd.DataFrame({
        "can_long": max_long > 0,
        "can_short": max_short > 0,
        "max_long": max_long.astype(float),
        "max_short": max_short.astype(float),
        "max_trade": max_trade.astype(float),
        "borrow_fee": fee.astype(float),
        "beta": beta.astype(float),
        "country": country,
        "sector": sector,
        "reasons": [";".join(reasons[i]) for i in ids],
        "squeeze_bucket": bucket,
        "shortable": shortable,
        "view_no_long": view_no_long,
        "view_no_short": view_no_short,
        "view_max_abs": view_max.astype(float),
        "adtv_long_usd": adtv_long.astype(float),
        "adtv_short_usd": adtv_short.astype(float),
        "current": cur.astype(float),
        "max_trade_liq": max_trade_liq.astype(float),
        "flags": [";".join(flags[i]) for i in ids],
    }, index=idx)
    return out


# ==========================================================
# Problema de otimização
# ==========================================================

@dataclass(frozen=True)
class _Settings:
    vol_target: float
    gross_max: float
    risk_aversion: float
    turnover_max: float | None
    exclude: tuple[str, ...]
    notes: tuple[str, ...]
    risk_target_mode: str = "cap"
    themes: dict | None = None
    exposure_limits: dict | None = None


def _finite(name: str, value: object) -> float:
    """Override numérico finito; NaN/inf passariam pelas comparações e chegariam ao solver."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Override '{name}' não numérico: {value!r}") from exc
    if not np.isfinite(v):
        raise ValueError(f"Override '{name}' não finito: {value!r}")
    return v


def _resolve_settings(cfg: FundConfig, overrides: dict | None, inception: bool) -> _Settings:
    rk = cfg.risk
    ov = dict(overrides or {})
    unknown = sorted(set(ov) - _ALLOWED_OVERRIDES)
    if unknown:
        raise ValueError(f"Overrides desconhecidos: {unknown}. Permitidos: "
                         f"{sorted(_ALLOWED_OVERRIDES)}")
    for key in ("vol_target", "vol_target_annual", "gross_max", "gross_multiplier",
                "risk_aversion", "max_weekly_turnover"):
        if key in ov:
            ov[key] = _finite(key, ov[key])
    notes: list[str] = []
    vt = ov.get("vol_target", ov.get("vol_target_annual", rk.vol_target_annual))
    vt = float(vt)
    if not (rk.vol_band_min - TOL <= vt <= rk.vol_band_max + TOL):
        raise ValueError(f"Meta de vol {vt:.2%} fora da banda "
                         f"[{rk.vol_band_min:.2%}, {rk.vol_band_max:.2%}].")
    if vt != rk.vol_target_annual:
        notes.append(f"Meta de vol ajustada pelo gestor: {vt:.2%} "
                     f"(config {rk.vol_target_annual:.2%}).")
    gross = float(ov.get("gross_max", rk.gross_max))
    if gross > rk.gross_max + TOL or gross <= 0:
        raise ValueError(f"gross_max {gross} inválido: só pode apertar o mandato "
                         f"(≤ {rk.gross_max}).")
    mult = float(ov.get("gross_multiplier", 1.0))
    if not (0 < mult <= 1):
        raise ValueError("gross_multiplier precisa estar em (0, 1].")
    if gross != rk.gross_max or mult != 1.0:
        notes.append(f"Gross máximo efetivo: {gross * mult:.2f}x (override do gestor).")
    lam = float(ov.get("risk_aversion", rk.risk_aversion))
    if lam < 0:
        raise ValueError("risk_aversion não pode ser negativo.")
    turnover: float | None = None
    if not inception:
        turnover = float(ov.get("max_weekly_turnover", cfg.liquidity.max_weekly_turnover))
        if turnover > cfg.liquidity.max_weekly_turnover + TOL or turnover <= 0:
            raise ValueError("max_weekly_turnover só pode apertar o mandato.")
    raw_excl = ov.get("exclude_issuers", []) or []
    if isinstance(raw_excl, str):  # um único emissor (não iterar caractere a caractere)
        raw_excl = [raw_excl]
    excl = tuple(sorted(map(str, raw_excl)))
    if excl:
        notes.append(f"Emissores excluídos pelo gestor (apenas saída): {', '.join(excl)}.")
    mode = str(ov.get("risk_target_mode", getattr(rk, "risk_target_mode", "cap")))
    if mode not in RISK_TARGET_MODES:
        raise ValueError(f"risk_target_mode inválido: {mode!r} (use {RISK_TARGET_MODES}).")
    themes = ov.get("themes")
    if themes is not None and not isinstance(themes, dict):
        raise ValueError("themes precisa ser um dicionário tema -> lista de emissores.")
    limits = ov.get("exposure_limits")
    if limits is not None:
        if not isinstance(limits, dict):
            raise ValueError("exposure_limits precisa ser {nome: {'exposures': {...}, 'limit': x}}.")
        for k, v in limits.items():
            lim = _finite(f"exposure_limits[{k}]", v.get("limit"))
            if lim < 0:
                raise ValueError(f"Limite negativo em exposure_limits[{k}].")
    return _Settings(vt, gross * mult, lam, turnover, excl, tuple(notes), mode,
                     {str(k): [str(x) for x in v] for k, v in (themes or {}).items()},
                     limits)


@dataclass(frozen=True)
class _Problem:
    ids: list[str]
    alpha: np.ndarray
    w0: np.ndarray
    G: np.ndarray            # (r × n): ‖G w‖² = wᵀ B F Bᵀ w
    sd: np.ndarray           # √D
    beta: np.ndarray
    style_names: list[str]
    styles: np.ndarray       # (S × n)
    country_names: list[str]
    countries: np.ndarray    # (C × n) indicadoras
    sector_names: list[str]
    sectors: np.ndarray      # (K × n) indicadoras
    max_long: np.ndarray
    max_short: np.ndarray
    max_trade: np.ndarray
    trade_liq: np.ndarray | None  # teto de AUMENTO por liquidez (None = só |Δw| ≤ max_trade)
    fee: np.ndarray
    lin_l: np.ndarray
    k_l: np.ndarray
    lin_s: np.ndarray
    k_s: np.ndarray
    vol_target: float
    net_max: float
    beta_max: float
    gross_max: float
    style_max: float
    country_max: float
    sector_max: float
    turnover_max: float | None
    lam: float
    amort: float
    factor_vol_max: float | None = None   # ‖G w‖ ≤ √(fatia máx. de risco fatorial)·σ_alvo
    theme_names: tuple[str, ...] = ()
    themes: np.ndarray | None = None       # (T × n) indicadoras de tema (ex.: estatais)
    theme_max: np.ndarray | None = None    # (T) limites de exposição líquida
    country_share: np.ndarray | None = None  # (C) teto da fatia do gross por país (NaN = livre)


@dataclass(frozen=True)
class _Relax:
    turnover: bool = False
    style_mult: float = 1.0
    group_mult: float = 1.0
    beta_mult: float = 1.0

    def step(self, name: str) -> _Relax:
        if name == "turnover":
            return replace(self, turnover=True)
        if name == "style":
            return replace(self, style_mult=2.0)
        if name == "country_sector":
            return replace(self, group_mult=1.5)
        if name == "beta":
            return replace(self, beta_mult=2.0)
        raise ValueError(name)


@dataclass(frozen=True)
class _Outcome:
    status: str
    solver: str
    seconds: float
    w: np.ndarray | None
    objective: float | None
    infeasible: bool
    errors: tuple[str, ...] = ()
    long_leg: np.ndarray | None = None
    short_leg: np.ndarray | None = None
    box_repaired: int = 0         # emissores com pernas l e s simultâneas reparados
    box_unresolved: int = 0       # pernas simultâneas que o reparo não conseguiu eliminar


def _indicator(labels: pd.Series) -> tuple[list[str], np.ndarray]:
    names = sorted(set(labels))
    mat = np.vstack([(labels.to_numpy() == g).astype(float) for g in names]) if names \
        else np.zeros((0, len(labels)))
    return names, mat


def _available_solvers() -> list[str]:
    installed = set(cp.installed_solvers())
    return [s for s in SOLVER_ORDER if s in installed]


def _solve(p: _Problem, relax: _Relax, fixed_zero: np.ndarray,
           reduce_only: np.ndarray, zero_long: np.ndarray | None = None,
           zero_short: np.ndarray | None = None) -> _Outcome:
    n = len(p.ids)
    l0 = np.maximum(p.w0, 0.0)
    s0 = np.maximum(-p.w0, 0.0)
    ub_l = p.max_long.copy()
    ub_s = p.max_short.copy()
    ub_l[fixed_zero] = 0.0
    ub_s[fixed_zero] = 0.0
    if zero_long is not None:
        ub_l[zero_long] = 0.0
    if zero_short is not None:
        ub_s[zero_short] = 0.0
    ub_l[reduce_only] = np.minimum(ub_l[reduce_only], l0[reduce_only])
    ub_s[reduce_only] = np.minimum(ub_s[reduce_only], s0[reduce_only])
    # Posições acima do teto (ou já zeradas) só podem diminuir; nunca aumentar.
    ub_l = np.maximum(ub_l, 0.0)
    ub_s = np.maximum(ub_s, 0.0)

    lv = cp.Variable(n, nonneg=True, name="long")
    sv = cp.Variable(n, nonneg=True, name="short")
    w = lv - sv
    dl = cp.abs(lv - l0)
    ds = cp.abs(sv - s0)
    cost = (p.lin_l @ dl + p.k_l @ cp.power(dl, IMPACT_EXPONENT)
            + p.lin_s @ ds + p.k_s @ cp.power(ds, IMPACT_EXPONENT))
    sw = cp.multiply(p.sd, w)
    if p.G.shape[0]:
        gw = p.G @ w
        risk = cp.sum_squares(gw) + cp.sum_squares(sw)
        risk_vec = cp.hstack([gw, sw])
    else:
        risk = cp.sum_squares(sw)
        risk_vec = sw
    objective = p.alpha @ w - p.amort * cost - p.fee @ sv - p.lam * risk

    cons = [lv <= ub_l, sv <= ub_s]
    net = cp.sum(w)
    cons += [net <= p.net_max, net >= -p.net_max]
    bmax = p.beta_max * relax.beta_mult
    cons += [p.beta @ w <= bmax, p.beta @ w >= -bmax]
    cons += [cp.norm(risk_vec, 2) <= p.vol_target]
    cons += [cp.sum(lv + sv) <= p.gross_max]
    if p.countries.shape[0]:
        cm = p.country_max * relax.group_mult
        cons += [p.countries @ w <= cm, p.countries @ w >= -cm]
    if p.sectors.shape[0]:
        sm = p.sector_max * relax.group_mult
        cons += [p.sectors @ w <= sm, p.sectors @ w >= -sm]
    if p.styles.shape[0]:
        st = p.style_max * relax.style_mult
        cons += [p.styles @ w <= st, p.styles @ w >= -st]
    # Alpha puro: risco fatorial limitado (≥ 1 − fatia da variância é idiossincrática).
    if p.factor_vol_max is not None and p.G.shape[0]:
        cons += [cp.norm(p.G @ w, 2) <= p.factor_vol_max]
    # Temas (ex.: estatais) neutros — nunca relaxados.
    if p.themes is not None and p.themes.shape[0]:
        cons += [p.themes @ w <= p.theme_max, p.themes @ w >= -p.theme_max]
    # Concentração do gross por país (linear nas pernas l, s).
    if p.country_share is not None and p.countries.shape[0]:
        gross_expr = cp.sum(lv + sv)
        for k in range(p.countries.shape[0]):
            share = p.country_share[k]
            if np.isfinite(share):
                cons += [p.countries[k] @ (lv + sv) <= share * gross_expr]
    cons += [cp.abs(w - p.w0) <= p.max_trade]
    if p.trade_liq is not None:
        # Aumentos limitados pela liquidez; reduzir até zero (saída) é sempre permitido.
        cons += [w <= np.maximum(p.w0 + p.trade_liq, 0.0),
                 w >= np.minimum(p.w0 - p.trade_liq, 0.0)]
    if p.turnover_max is not None and not relax.turnover:
        cons += [cp.sum(cp.abs(w - p.w0)) <= p.turnover_max]

    prob = cp.Problem(cp.Maximize(objective), cons)
    errors: list[str] = []
    t0 = time.perf_counter()
    for solver in _available_solvers():
        try:
            prob.solve(solver=solver, **SOLVER_OPTIONS.get(solver, {}))
        except (cp.SolverError, ValueError, ArithmeticError) as exc:  # pragma: no cover
            errors.append(f"{solver}: {exc}")
            continue
        status = prob.status
        if status in _OK and lv.value is not None and sv.value is not None:
            lval = np.maximum(np.asarray(lv.value, dtype=float), 0.0)
            sval = np.maximum(np.asarray(sv.value, dtype=float), 0.0)
            wv = lval - sval
            wv[np.abs(wv) < WEIGHT_NOISE] = 0.0
            return _Outcome(status, solver, time.perf_counter() - t0, wv,
                            float(prob.value), False, tuple(errors), lval, sval)
        if status in _INFEASIBLE:
            return _Outcome(status, solver, time.perf_counter() - t0, None, None, True,
                            tuple(errors))
        errors.append(f"{solver}: status {status}")
    return _Outcome("solver_error", ",".join(_available_solvers()),
                    time.perf_counter() - t0, None, None, False, tuple(errors))


def _solve_clean(p: _Problem, relax: _Relax, fixed_zero: np.ndarray,
                 reduce_only: np.ndarray) -> _Outcome:
    """Resolve e repara pernas simultâneas (l > 0 e s > 0 no mesmo emissor).

    A cada rodada, emissores com as duas pernas abertas têm a perna oposta ao sinal líquido
    fixada em zero (líquido ≥ 0 ⇒ s = 0; líquido < 0 ⇒ l = 0). A solução líquida anterior
    continua viável, então o reparo nunca cria inviabilidade; ele só remove a economia
    artificial de custo de dividir uma ordem entre duas pernas.
    """
    n = len(p.ids)
    zl = np.zeros(n, dtype=bool)
    zs = np.zeros(n, dtype=bool)
    out = _solve(p, relax, fixed_zero, reduce_only)
    seconds = out.seconds
    repaired = 0
    for _ in range(MAX_BOX_REPAIRS):
        if out.w is None or out.long_leg is None or out.short_leg is None:
            break
        box = (out.long_leg > BOX_TOL) & (out.short_leg > BOX_TOL)
        if not box.any():
            break
        net = out.long_leg - out.short_leg
        zs = zs | (box & (net >= 0))
        zl = zl | (box & (net < 0))
        nxt = _solve(p, relax, fixed_zero, reduce_only, zl, zs)
        seconds += nxt.seconds
        if nxt.w is None:  # numericamente não deveria ocorrer: mantém a solução anterior
            break
        repaired += int(box.sum())
        out = nxt
    unresolved = 0
    if out.long_leg is not None and out.short_leg is not None:
        unresolved = int(((out.long_leg > BOX_TOL) & (out.short_leg > BOX_TOL)).sum())
    return replace(out, seconds=seconds, box_repaired=repaired, box_unresolved=unresolved)


def _build_problem(alpha: pd.Series, model: RiskModel, cons: pd.DataFrame, cm: CostModel,
                   cfg: FundConfig, settings: _Settings, w0: pd.Series) -> _Problem:
    ids = list(cons.index)
    factors = model.factor_names
    B = model.exposures.loc[ids, factors]
    L = psd_factor_root(model.factor_cov.loc[factors, factors])
    G = L.T @ B.to_numpy(dtype=float).T
    sd = np.sqrt(model.specific_var.loc[ids].to_numpy(dtype=float))

    style_names = model.factors_in_group("style") or [f for f in STYLE_FACTORS if f in factors]
    styles = B[style_names].to_numpy(dtype=float).T if style_names else np.zeros((0, len(ids)))
    c_names, c_mat = _indicator(cons["country"].fillna(UNKNOWN_GROUP))
    s_names, s_mat = _indicator(cons["sector"].fillna(UNKNOWN_GROUP))

    cmi = cm.reindex(ids)
    lin_l, k_l = cmi.leg_params("long")
    lin_s, k_s = cmi.leg_params("short")
    for what, s in (("custo linear long", lin_l), ("impacto long", k_l),
                    ("custo linear short", lin_s), ("impacto short", k_s)):
        if not np.all(np.isfinite(s.to_numpy(dtype=float))):
            raise ValueError(f"Parâmetro de {what} não finito: "
                             f"{list(s.index[~np.isfinite(s.to_numpy(dtype=float))])}")

    fee = pd.to_numeric(cons["borrow_fee"], errors="coerce")
    new_short = cons["max_short"] > 0
    bad_fee = fee.isna() & new_short
    if bad_fee.any():
        raise ValueError("Taxa de aluguel ausente para shorts possíveis: "
                         f"{list(fee.index[bad_fee])}")
    # Short legado sem taxa (aluguel não mais disponível): taxa máxima do mandato
    # (conservador, incentiva a recompra). Sem short possível nem legado: s ≡ 0.
    legacy = fee.isna() & (w0 < 0)
    fee = fee.where(~legacy, cfg.shorting.max_borrow_fee)
    fee = fee.where(new_short | (w0 < 0), 0.0)

    trade_liq = None
    if "max_trade_liq" in cons.columns:
        tl = pd.to_numeric(cons["max_trade_liq"], errors="coerce")
        if tl.isna().any():
            raise ValueError(f"Coluna 'max_trade_liq' com NaN: {list(tl.index[tl.isna()])}")
        trade_liq = tl.clip(lower=0.0).to_numpy(dtype=float)

    rk = cfg.risk
    share_max = float(getattr(rk, "max_factor_risk_share", 1.0))
    factor_vol_max = (float(np.sqrt(share_max)) * settings.vol_target
                      if 0 < share_max < 1 else None)
    theme_names: list[str] = []
    theme_rows: list[np.ndarray] = []
    theme_lims: list[float] = []
    for tname, members in sorted((settings.themes or {}).items()):
        lim = getattr(rk, "theme_net_max_abs", {}).get(tname)
        if lim is None:
            continue
        row = np.array([1.0 if i in set(members) else 0.0 for i in ids])
        if row.any():
            theme_names.append(tname)
            theme_rows.append(row)
            theme_lims.append(float(lim))
    for lname, spec in sorted((settings.exposure_limits or {}).items()):
        expo = spec.get("exposures", {}) or {}
        row = np.array([float(expo.get(i, 0.0)) if np.isfinite(float(expo.get(i, 0.0)))
                        else 0.0 for i in ids])
        if np.any(row != 0):
            theme_names.append(str(lname))
            theme_rows.append(row)
            theme_lims.append(float(spec["limit"]))
    shares_cfg = getattr(rk, "country_gross_share_max", {}) or {}
    country_share = np.array([float(shares_cfg.get(c, np.nan)) for c in c_names])
    return _Problem(
        ids=ids, alpha=alpha.to_numpy(dtype=float), w0=w0.to_numpy(dtype=float), G=G, sd=sd,
        beta=cons["beta"].to_numpy(dtype=float), style_names=style_names, styles=styles,
        country_names=c_names, countries=c_mat, sector_names=s_names, sectors=s_mat,
        max_long=cons["max_long"].to_numpy(dtype=float),
        max_short=cons["max_short"].to_numpy(dtype=float),
        max_trade=cons["max_trade"].to_numpy(dtype=float), trade_liq=trade_liq,
        fee=fee.to_numpy(dtype=float),
        lin_l=lin_l.to_numpy(dtype=float), k_l=k_l.to_numpy(dtype=float),
        lin_s=lin_s.to_numpy(dtype=float), k_s=k_s.to_numpy(dtype=float),
        vol_target=settings.vol_target, net_max=rk.net_exposure_max_abs,
        beta_max=rk.beta_max_abs, gross_max=settings.gross_max,
        style_max=rk.style_exposure_max_abs, country_max=rk.country_net_max_abs,
        sector_max=rk.sector_net_max_abs, turnover_max=settings.turnover_max,
        lam=settings.risk_aversion, amort=WEEKS_PER_YEAR / cfg.costs.amortization_weeks,
        factor_vol_max=factor_vol_max, theme_names=tuple(theme_names),
        themes=np.vstack(theme_rows) if theme_rows else None,
        theme_max=np.array(theme_lims) if theme_lims else None,
        country_share=country_share if np.isfinite(country_share).any() else None,
    )


def _binding(p: _Problem, relax: _Relax, w: np.ndarray) -> list[str]:
    out: list[str] = []

    def rel(limit: float, value: float) -> bool:
        return limit > TOL and (limit - abs(value)) / limit < BINDING_REL_SLACK

    if rel(p.net_max, float(w.sum())):
        out.append("net_exposure")
    if rel(p.beta_max * relax.beta_mult, float(p.beta @ w)):
        out.append("beta")
    vol = float(np.sqrt(np.sum((p.G @ w) ** 2) + np.sum((p.sd * w) ** 2)))
    if rel(p.vol_target, vol):
        out.append("vol_target")
    if rel(p.gross_max, float(np.abs(w).sum())):
        out.append("gross")
    if p.turnover_max is not None and not relax.turnover \
            and rel(p.turnover_max, float(np.abs(w - p.w0).sum())):
        out.append("turnover")
    for names, mat, lim, prefix in (
        (p.country_names, p.countries, p.country_max * relax.group_mult, "country"),
        (p.sector_names, p.sectors, p.sector_max * relax.group_mult, "sector"),
        (p.style_names, p.styles, p.style_max * relax.style_mult, "style"),
    ):
        if mat.shape[0]:
            vals = mat @ w
            out += [f"{prefix}:{g}" for g, v in zip(names, vals, strict=True) if rel(lim, v)]
    for i, iid in enumerate(p.ids):
        if w[i] > 0 and rel(p.max_long[i], w[i]):
            out.append(f"max_long:{iid}")
        if w[i] < 0 and rel(p.max_short[i], w[i]):
            out.append(f"max_short:{iid}")
        if w[i] != p.w0[i] and rel(p.max_trade[i], w[i] - p.w0[i]):
            out.append(f"max_trade:{iid}")
        elif p.trade_liq is not None and p.trade_liq[i] > TOL:
            hi = max(p.w0[i] + p.trade_liq[i], 0.0)
            lo = min(p.w0[i] - p.trade_liq[i], 0.0)
            gap = hi - w[i] if w[i] > p.w0[i] else w[i] - lo if w[i] < p.w0[i] else np.inf
            if gap / p.trade_liq[i] < BINDING_REL_SLACK:
                out.append(f"max_trade_liq:{iid}")
    return out


def _reason_counts(reasons: pd.Series) -> dict[str, int]:
    cnt: Counter[str] = Counter()
    for r in reasons:
        for tok in str(r).split(";"):
            if tok:
                cnt[tok] += 1
    return dict(sorted(cnt.items()))


def _diag(status: str, solver: str, seconds: float, objective: float | None,
          exp_alpha: float | None, exp_cost: float | None, binding: list[str],
          n_candidates: int, n_excluded: dict[str, int], notes: list[str]) -> OptimizerDiagnostics:
    return OptimizerDiagnostics(
        status=status, solver=solver, solve_seconds=round(seconds, 6), objective=objective,
        expected_alpha_annual=exp_alpha, expected_cost_annual=exp_cost,
        binding_constraints=binding, n_candidates=n_candidates, n_excluded=n_excluded,
        notes=notes,
    )


def _vol_of(p: _Problem, w: np.ndarray) -> float:
    gw = p.G @ w
    return float(np.sqrt(gw @ gw + np.sum((p.sd * w) ** 2)))


def _match_vol_target(p: _Problem, relax: _Relax, base: _Outcome
                      ) -> tuple[float, _Outcome, float, bool]:
    """Menor κ ≥ 1 tal que o portfólio com alpha κ·α atinja a meta de vol (teto ativo).

    Custos, aluguel e aversão a risco não mudam: escalar α equivale a reduzir proporcionalmente
    a aversão a custo/risco relativa ao alpha. Retorna ``(κ, solução, segundos, atingiu)``.
    Se a meta for inatingível até ``MAX_ALPHA_SCALE`` (capacidade de liquidez/aluguel), devolve
    a solução de maior vol encontrada.
    """
    no_fix = np.zeros(len(p.ids), dtype=bool)
    target = p.vol_target * (1 - MATCH_REL_TOL)
    secs = 0.0
    lo, best_lo = 1.0, base
    hi: float | None = None
    best_hi: _Outcome | None = None
    k = 2.0
    while k <= MAX_ALPHA_SCALE + TOL:
        o = _solve_clean(replace(p, alpha=p.alpha * k), relax, no_fix, no_fix)
        secs += o.seconds
        if o.w is None:
            break
        if _vol_of(p, o.w) >= target:
            hi, best_hi = k, o
            break
        lo, best_lo = k, o
        k *= 2.0
    if hi is None or best_hi is None:
        return lo, best_lo, secs, False
    for _ in range(MATCH_BISECT_STEPS):
        mid = float(np.sqrt(lo * hi))
        o = _solve_clean(replace(p, alpha=p.alpha * mid), relax, no_fix, no_fix)
        secs += o.seconds
        if o.w is None:
            break
        if _vol_of(p, o.w) >= target:
            hi, best_hi = mid, o
        else:
            lo = mid
    return hi, best_hi, secs, True


def optimize(alpha: pd.Series, model: RiskModel, constraints: pd.DataFrame,
             cost_model: CostModel, cfg: FundConfig, nav: float,
             current: pd.Series | None = None, inception: bool = False,
             market_w: pd.Series | None = None, overrides: dict | None = None,
             ) -> OptimizationResult:
    """Resolve a carteira-alvo da semana (pesos por emissor, fração do NAV).

    ``alpha``: retorno residual esperado anual por emissor (já ortogonalizado). Emissor sem
    alpha (``NaN``/ausente) não abre posição: só pode reduzir/zerar posição existente.
    ``constraints``: saída de :func:`build_asset_constraints` (ou tabela equivalente com as
    colunas obrigatórias). Coluna opcional ``max_trade_liq``: teto de AUMENTO por liquidez
    (reduções até zero sempre permitidas); sem ela vale só ``|w − w₀| ≤ max_trade``.
    Toda solução passa pelo reparo de complementaridade (sem perna comprada e vendida
    simultâneas no mesmo emissor), de modo que o custo otimizado é o custo da ordem líquida
    que ``trades.build_trades`` emite. ``market_w``: pesos de mercado, usados para o beta implícito do
    modelo quando ``constraints['beta']`` está ausente. ``overrides`` (do gestor, só apertam o
    mandato): ``vol_target`` (dentro da banda), ``gross_max``, ``gross_multiplier``,
    ``risk_aversion``, ``max_weekly_turnover``, ``exclude_issuers``, ``risk_target_mode``.

    ``risk_target_mode``: ``"cap"`` (padrão) trata a meta de vol como teto — com alpha fraco
    diante dos custos, a carteira fica abaixo da meta (a compliance alerta em ``VOL_MIN``).
    ``"match"`` calibra o menor multiplicador κ ≥ 1 do alpha que faz o teto de vol ficar ativo
    (equivale a reduzir a aversão a custo/risco relativa ao alpha); κ vai para
    ``alpha_scale`` e para as notas, e ``expected_alpha`` continua usando o alpha original.

    Levanta :class:`OptimizationError` se nenhum degrau da escada de relaxamento tornar o
    problema viável (nunca devolve carteira zerada silenciosamente).
    """
    if not nav > 0:
        raise ValueError("NAV precisa ser positivo.")
    required = ["max_long", "max_short", "max_trade", "borrow_fee", "country", "sector"]
    missing_cols = [c for c in required if c not in constraints.columns]
    if missing_cols:
        raise ValueError(f"Tabela de restrições sem colunas: {missing_cols}")
    settings = _resolve_settings(cfg, overrides, inception)
    notes: list[str] = list(settings.notes)

    cons = constraints.copy()
    cons.index = cons.index.map(str)
    if cons.index.duplicated().any():
        raise ValueError("Restrições com emissores duplicados.")
    cur = _clean_current(current)
    held_outside = sorted(set(cur.index[cur != 0]) - set(cons.index))
    if held_outside:
        raise ValueError(f"Posições atuais sem linha na tabela de restrições: {held_outside}")
    w0 = cur.reindex(cons.index).fillna(0.0)  # sem posição atual = peso zero
    if inception and (w0 != 0).any():
        notes.append("Inception com carteira atual não vazia: turnover não limitado.")
    extra_reasons: dict[str, list[str]] = {i: [] for i in cons.index}

    for col in ("max_long", "max_short", "max_trade"):
        vals = pd.to_numeric(cons[col], errors="coerce")
        if vals.isna().any():
            raise ValueError(f"Coluna '{col}' com NaN: {list(vals.index[vals.isna()])}")
        cons[col] = vals.clip(lower=0.0)

    # Cobertura do modelo de risco.
    B_ok = model.exposures.reindex(cons.index)[model.factor_names].notna().all(axis=1)
    D = pd.to_numeric(model.specific_var.reindex(cons.index), errors="coerce")
    in_model = B_ok & D.notna() & (D >= 0)
    outside = list(cons.index[~in_model])
    held_bad = [i for i in outside if w0[i] != 0]
    if held_bad:
        raise ValueError("Emissores com posição atual sem cobertura do modelo de risco: "
                         f"{held_bad}")
    for i in outside:
        extra_reasons[i].append("fora_do_modelo_risco")

    # Alpha: ausente ⇒ apenas redução/saída (nunca alpha zero silencioso para abrir posição).
    a = pd.to_numeric(alpha, errors="coerce")
    a.index = a.index.map(str)
    inf_alpha = a.notna() & ~np.isfinite(a.to_numpy(dtype=float))
    if inf_alpha.any():
        raise ValueError(f"Alpha infinito (dado inválido, não ausente): "
                         f"{list(a.index[inf_alpha])}")
    ignored = sorted(set(a.index) - set(cons.index))
    if ignored:
        notes.append(f"{len(ignored)} emissores com alpha fora da tabela de restrições "
                     "foram ignorados.")
    a = a.reindex(cons.index)
    no_alpha = a.isna()
    for i in cons.index[no_alpha]:
        extra_reasons[i].append("alpha_ausente")
    excluded_pm = cons.index.isin(settings.exclude)
    for i in cons.index[excluded_pm]:
        extra_reasons[i].append("excluido_gestor")
    # Sem alpha: pode manter ou reduzir, nunca aumentar/abrir. Excluído pelo gestor: zera.
    cons.loc[no_alpha, "max_long"] = np.minimum(cons.loc[no_alpha, "max_long"],
                                                w0[no_alpha].clip(lower=0.0))
    cons.loc[no_alpha, "max_short"] = np.minimum(cons.loc[no_alpha, "max_short"],
                                                 (-w0[no_alpha]).clip(lower=0.0))
    cons.loc[excluded_pm, ["max_long", "max_short"]] = 0.0
    a_obj = a.where(~no_alpha, 0.0)  # sem retorno esperado: só risco e custo pesam

    # Beta: preferir a coluna; lacunas ⇒ beta implícito do modelo (com market_w) ou 1,0.
    if "beta" in cons.columns:
        beta = pd.to_numeric(cons["beta"], errors="coerce")
    else:
        beta = pd.Series(np.nan, index=cons.index)
    if beta.isna().any():
        if market_w is not None:
            implied = model_implied_betas(model, market_w).reindex(cons.index)
            n_fill = int((beta.isna() & implied.notna()).sum())
            beta = beta.fillna(implied)
            if n_fill:
                notes.append("Beta implícito do modelo (pesos de mercado) usado para "
                             f"{n_fill} emissores.")
        n_one = int(beta.isna().sum())
        if n_one:
            notes.append(f"Beta ausente imputado em 1,0 para {n_one} emissores.")
            beta = beta.fillna(1.0)
    cons["beta"] = beta

    reasons_all = cons.get("reasons", pd.Series("", index=cons.index)).fillna("").astype(str)
    reasons_all = pd.Series(
        [";".join([r for r in [reasons_all[i]] + extra_reasons[i] if r]) for i in cons.index],
        index=cons.index)
    n_excluded = _reason_counts(reasons_all)

    work = cons.loc[in_model]
    if work.empty:
        raise OptimizationError("Nenhum emissor com cobertura do modelo de risco.")
    p = _build_problem(a_obj.loc[work.index], model, work, cost_model, cfg, settings,
                       w0.loc[work.index])
    n = len(p.ids)
    n_candidates = int(((work["max_long"] > 0) | (work["max_short"] > 0)).sum())
    if n_candidates == 0:
        notes.append("Nenhum candidato com limite positivo: só é possível reduzir posições.")

    # ---------- passada 1 + escada de relaxamento ----------
    relax = _Relax()
    relaxations: list[str] = []
    total_seconds = 0.0
    no_fix = np.zeros(n, dtype=bool)
    outcome = _solve_clean(p, relax, no_fix, no_fix)
    total_seconds += outcome.seconds
    steps = [s for s in RELAXATION_STEPS if not (s[0] == "turnover" and p.turnover_max is None)]
    step_iter = iter(steps)
    while outcome.infeasible:
        nxt = next(step_iter, None)
        if nxt is None:
            break
        relax = relax.step(nxt[0])
        relaxations.append(nxt[0])
        notes.append(nxt[1])
        outcome = _solve_clean(p, relax, no_fix, no_fix)
        total_seconds += outcome.seconds
    if outcome.w is None:
        reason = ("inviável mesmo após toda a escada de relaxamento" if outcome.infeasible
                  else "erro em todos os solvers: " + "; ".join(outcome.errors))
        diag = _diag(outcome.status, outcome.solver, total_seconds, None, None, None, [],
                     n_candidates, n_excluded, notes + [f"Otimização falhou: {reason}."])
        raise OptimizationError(f"Otimização falhou: {reason}.", diag, relaxations)
    if outcome.status == cp.OPTIMAL_INACCURATE:
        notes.append(f"Solver {outcome.solver} retornou solução imprecisa (optimal_inaccurate).")
    if outcome.errors:
        notes.append("Falhas de solver antes do sucesso: " + "; ".join(outcome.errors))

    # ---------- modo "match": calibra a escala do alpha para atingir a meta de vol ----------
    alpha_raw = p.alpha.copy()
    kappa = 1.0
    if settings.risk_target_mode == "match" and outcome.w is not None \
            and _vol_of(p, outcome.w) < p.vol_target * (1 - MATCH_REL_TOL):
        kappa, outcome, secs, reached = _match_vol_target(p, relax, outcome)
        total_seconds += secs
        p = replace(p, alpha=alpha_raw * kappa)
        if reached:
            notes.append(f"Modo 'match': alpha escalado em {kappa:.2f}x para atingir a meta de "
                         f"vol (custos, aluguel e limites inalterados).")
        else:
            notes.append(f"Modo 'match': meta de vol inatingível até {MAX_ALPHA_SCALE:.0f}x "
                         f"(capacidade de liquidez/aluguel); usado {kappa:.2f}x.")
    assert outcome.w is not None

    # ---------- passadas de limpeza (posição mínima) ----------
    min_pos = cfg.risk.min_position_weight
    w = outcome.w
    fixed = np.zeros(n, dtype=bool)
    passes = 1
    while min_pos > 0 and passes < MAX_PASSES:
        tiny = (np.abs(w) < min_pos) & ~fixed
        if not np.any(tiny & (w != 0)):
            break
        trial_fixed = fixed | tiny
        out2 = _solve_clean(p, relax, trial_fixed, no_fix)
        total_seconds += out2.seconds
        if out2.w is None:
            held_tiny = trial_fixed & (p.w0 != 0) & ~fixed
            fixed_wo_held = trial_fixed & ~held_tiny
            out2 = _solve_clean(p, relax, fixed_wo_held, held_tiny)
            total_seconds += out2.seconds
            if out2.w is None:
                notes.append("Passada de posição mínima inviável: mantida a solução anterior "
                             "(com posições residuais).")
                break
            notes.append("Posições residuais mantidas só para redução (necessárias à saída).")
            trial_fixed = fixed_wo_held
        passes += 1
        fixed = trial_fixed
        outcome = out2
        w = out2.w
    residual = (np.abs(w) > 0) & (np.abs(w) < min_pos)
    if residual.any():
        notes.append(f"{int(residual.sum())} posições abaixo do mínimo de {min_pos:.2%} "
                     "permaneceram (saída gradual ou limite de passadas).")
    notes.append(f"Passadas de otimização: {passes}.")
    if outcome.box_repaired:
        notes.append(f"Reparo de complementaridade: {outcome.box_repaired} emissores tinham "
                     "perna comprada e vendida simultâneas (custo subestimado) e foram "
                     "re-otimizados com uma única perna.")
    if outcome.box_unresolved:
        notes.append(f"ATENÇÃO: {outcome.box_unresolved} emissores mantêm pernas simultâneas "
                     "após o reparo; custo de negociação pode estar subestimado.")

    # ---------- resultados ----------
    weights = pd.Series(0.0, index=cons.index)
    weights.loc[p.ids] = w
    weights.name = "weight"
    trades = weights - w0
    l1 = np.maximum(w, 0.0)
    s1 = np.maximum(-w, 0.0)
    exp_alpha = float(alpha_raw @ w)  # alpha original (sem a escala κ do modo "match")
    one_off = float(estimate_rebalance_costs(weights, w0, cost_model.reindex(cons.index)).sum())
    borrow = float(p.fee @ s1)
    cost_annual = p.amort * one_off + borrow
    vol = _vol_of(p, w)
    if vol > p.vol_target * (1 + TOL) + TOL:
        notes.append(f"Vol ex-ante {vol:.4%} acima da meta {p.vol_target:.4%} "
                     "(imprecisão do solver).")
    binding = _binding(p, relax, w)
    x = pd.Series(model.exposures.loc[p.ids, model.factor_names].to_numpy().T @ w,
                  index=model.factor_names)
    notes.append(f"Perna comprada {l1.sum():.2%}, vendida {s1.sum():.2%}; "
                 f"custo pontual {one_off * 1e4:.1f} bps do NAV; "
                 f"aluguel {borrow * 1e4:.1f} bps a.a.")
    diag = _diag(outcome.status, outcome.solver, total_seconds, outcome.objective, exp_alpha,
                 cost_annual, binding, n_candidates, n_excluded, notes)
    return OptimizationResult(
        weights=weights, ex_ante_vol=vol, diagnostics=diag, relaxations=relaxations,
        expected_alpha=exp_alpha, expected_cost=one_off, borrow_cost_annual=borrow,
        trades=trades, factor_exposures=x, vol_target=p.vol_target, passes=passes,
        alpha_scale=kappa,
    )
