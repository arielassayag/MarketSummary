"""Modelo de risco fatorial estilo Barra para ações LatAm em USD.

Estimação (ver docs/latam_ls/ARQUITETURA.md §5):

1. Regressão cross-section diária ``r_t = X_{t-1} f_t + e_t`` por WLS com peso ``√mcap_{t-1}``,
   apenas com emissores que têm retorno observado em ``t``. Retornos são truncados em ±25%
   (contagem registrada); o resíduo usa o mesmo retorno truncado — eventos extremos continuam
   visíveis no VaR histórico e nos testes de estresse, que usam retornos brutos.
2. Identificação: ``Σ_c w_c f_c = 0`` (países) e ``Σ_s w_s f_s = 0`` (setores), com ``w`` = pesos
   de capitalização do dia, impostas por reparametrização ``f = R g`` (matriz de restrição).
   Assim ``market`` ≈ retorno da carteira de mercado e países/setores são relativos a ela.
3. Fatores de país/setor com menos de ``min_names_per_sector`` observações no dia e estilos sem
   dispersão ficam fora da regressão do dia (``f = NaN``, nunca zero). Dias com menos de
   2 × (fatores ativos) observações ou com posto deficiente são pulados (registrados).
4. Covariância fatorial: EWMA com média zero (meia-vida de vol e de correlação separadas),
   ajuste Newey-West (assincronia de fechamento entre mercados), anualizada × 252, projetada
   para PSD por corte de autovalores. Ausências são tratadas por pares (somas mascaradas).
5. Risco específico: EWMA de ``e²/(1 − h_ii)`` anualizada, em que ``h_ii`` é a alavancagem do
   emissor na regressão WLS do dia (correção HC2: um nome dominante no seu país/setor tem o
   resíduo "absorvido" pelo fator e pareceria sem risco; ``h`` é limitado a ``MAX_LEVERAGE``).
   Shrinkage bayesiano linear (intensidade ``specific_shrinkage``) para a média ponderada por
   capitalização do grupo país × tercil de tamanho, piso de (10%)². Emissor com histórico curto
   recebe a média do grupo (flag).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type

import numpy as np
import pandas as pd

from ..analytics.panel import AssetPanel
from ..config import FundConfig
from ..market import MarketData
from .exposures import (
    NON_PIT_NOTES,
    FactorStructure,
    StyleInputs,
    factor_structure,
    prepare_style_inputs,
    standardized_styles,
)
from .types import MARKET_FACTOR, STYLE_FACTORS, TRADING_DAYS, RiskModel

RETURN_WINSOR = 0.25
MAX_LEVERAGE = 0.9
SPECIFIC_VOL_FLOOR = 0.10
MIN_FACTOR_OBS = 60
MIN_PAIR_OBS = 20
EIGEN_FLOOR_REL = 1e-10


# ==========================================================
# Utilitários numéricos (puros)
# ==========================================================

def ewma_weights(n: int, halflife: float) -> np.ndarray:
    """Pesos EWMA por idade em pregões: a última linha tem peso 1."""
    age = np.arange(n - 1, -1, -1, dtype=float)
    return 0.5 ** (age / float(halflife))


def _masked_lag_cov(z: np.ndarray, mask: np.ndarray, w: np.ndarray, lag: int):
    """Covariância EWMA (média zero) entre ``f_t`` e ``f_{t-lag}`` por pares observados.

    ``z`` tem zeros onde ``mask`` é falso apenas como artifício algébrico de somas mascaradas;
    o denominador conta somente pares observados (nenhum dado ausente vira zero no resultado).
    """
    if lag == 0:
        a, b, wl, ma, mb = z, z, w, mask, mask
    else:
        a, b, wl = z[lag:], z[:-lag], w[lag:]
        ma, mb = mask[lag:], mask[:-lag]
    num = (a * wl[:, None]).T @ b
    den = (ma * wl[:, None]).T @ mb.astype(float)
    cnt = ma.T.astype(float) @ mb.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = np.where(den > 0, num / den, np.nan)
    return cov, cnt


def newey_west_ewma_cov(f: np.ndarray, halflife: float, lags: int) -> tuple[np.ndarray, np.ndarray]:
    """Covariância diária EWMA + Newey-West (pesos de Bartlett) com ausências por pares.

    Retorna (cov, n_pares_lag0). Pares com menos de ``MIN_PAIR_OBS`` observações conjuntas
    ficam ``NaN`` (tratados por quem chama). Termos de defasagem sem pares observados não
    ajustam a covariância (equivale a não haver autocorrelação estimável).
    """
    mask = np.isfinite(f)
    z = np.where(mask, f, 0.0)
    w = ewma_weights(len(f), halflife)
    c0, cnt = _masked_lag_cov(z, mask, w, 0)
    cov = c0.copy()
    for lag in range(1, lags + 1):
        cl, cnt_l = _masked_lag_cov(z, mask, w, lag)
        cl = np.where(np.isfinite(cl) & (cnt_l >= MIN_PAIR_OBS), cl, 0.0)
        cov = cov + (1.0 - lag / (lags + 1.0)) * (cl + cl.T)
    cov = np.where(cnt >= MIN_PAIR_OBS, cov, np.nan)
    # Ajuste NW pode tornar a variância não positiva em amostras pequenas: volta ao lag 0.
    diag = np.diag(cov).copy()
    bad = ~(diag > 0)
    diag[bad] = np.diag(c0)[bad]
    np.fill_diagonal(cov, diag)
    return cov, cnt


def nearest_psd(cov: np.ndarray, floor_rel: float = EIGEN_FLOOR_REL) -> tuple[np.ndarray, int]:
    """Simetriza e corta autovalores abaixo de ``floor_rel × λ_max``; retorna (Σ_psd, n_cortes)."""
    sym = 0.5 * (cov + cov.T)
    if sym.size == 0:
        return sym, 0
    vals, vecs = np.linalg.eigh(sym)
    floor = max(float(vals.max()), 0.0) * floor_rel
    n_clip = int((vals < floor).sum())
    vals = np.maximum(vals, floor)
    out = (vecs * vals) @ vecs.T
    return 0.5 * (out + out.T), n_clip


def factor_covariance(
    f: np.ndarray, halflife_vol: float, halflife_corr: float, lags: int,
) -> tuple[np.ndarray, dict]:
    """Covariância fatorial anualizada: vol (meia-vida curta) × correlação (meia-vida longa)."""
    c_vol, cnt = newey_west_ewma_cov(f, halflife_vol, lags)
    c_corr, _ = newey_west_ewma_cov(f, halflife_corr, lags)
    sd = np.sqrt(np.diag(c_vol))
    sd_c = np.sqrt(np.diag(c_corr))
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = c_corr / np.outer(sd_c, sd_c)
    n_missing_pairs = int((~np.isfinite(corr)).sum())
    corr = np.where(np.isfinite(corr), np.clip(corr, -1.0, 1.0), 0.0)
    np.fill_diagonal(corr, 1.0)
    cov = np.outer(sd, sd) * corr * TRADING_DAYS
    cov, n_clip = nearest_psd(cov)
    return cov, {"psd_clipped_eigenvalues": n_clip,
                 "factor_pairs_without_overlap": n_missing_pairs,
                 "min_pair_obs": int(cnt.min()) if cnt.size else 0}


def _restriction_matrix(
    active: np.ndarray, blocks: list[np.ndarray], block_weights: list[np.ndarray],
) -> np.ndarray:
    """Matriz ``R`` (K_ativos × K_livres) tal que ``f = R g`` satisfaz ``Σ w_j f_j = 0`` por bloco.

    Em cada bloco o fator de maior peso (pivô) é expresso pelos demais:
    ``f_pivô = −Σ_{j≠pivô} (w_j / w_pivô) f_j``.
    """
    act = np.flatnonzero(active)
    pos_in_act = {k: n for n, k in enumerate(act)}
    pivots: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for idx, wts in zip(blocks, block_weights, strict=True):
        if len(idx) == 0:
            continue
        p = int(idx[int(np.argmax(wts))])
        pivots[p] = (idx, wts)
    free = [k for k in act if k not in pivots]
    col = {k: n for n, k in enumerate(free)}
    R = np.zeros((len(act), len(free)))
    for k in free:
        R[pos_in_act[k], col[k]] = 1.0
    for p, (idx, wts) in pivots.items():
        wp = float(wts[list(idx).index(p)])
        for k, wk in zip(idx, wts, strict=True):
            if k != p:
                R[pos_in_act[p], col[k]] = -float(wk) / wp
    return R


# ==========================================================
# Estimador
# ==========================================================

@dataclass(frozen=True)
class _DayFit:
    status: str
    n_obs: int
    n_winsorized: int
    r_squared: float


class RiskModelEstimator:
    """Pré-computa as regressões diárias UMA vez e devolve ``RiskModel`` em qualquer data.

    - Exposições são recalculadas a cada ``exposure_refresh_days`` pregões (ancoradas no início
      do painel) com dados <= a data do recálculo e mantidas constantes no intervalo; a
      regressão do dia ``t`` usa as exposições do último recálculo <= ``t-1``.
    - ``model_at(d)`` usa apenas retornos fatoriais/específicos com data <= ``d`` e exposições
      recalculadas exatamente em ``d`` (previsão de risco para a carteira montada em ``d``).
    - O universo de estimação (``issuers``) é fixo; o padrão são os elegíveis do painel no seu
      ``as_of`` (no backtest, passe uma lista explícita para evitar viés de sobrevivência).
    - ``start``/``end`` (opcionais) limitam as datas de regressão (uso interno de
      ``estimate_risk_model``); os resultados por data são idênticos aos do estimador completo.
    """

    def __init__(
        self,
        panel: AssetPanel,
        cfg: FundConfig,
        md: MarketData | None = None,
        issuers: list[str] | None = None,
        exposure_refresh_days: int = 5,
        *,
        start: date_type | pd.Timestamp | None = None,
        end: date_type | pd.Timestamp | None = None,
    ) -> None:
        if exposure_refresh_days < 1:
            raise ValueError("exposure_refresh_days precisa ser >= 1.")
        self.panel = panel
        self.cfg = cfg
        self.md = md
        self.refresh_days = int(exposure_refresh_days)
        ids = list(dict.fromkeys(issuers if issuers is not None else panel.eligible))
        if not ids:
            raise ValueError("Universo de estimação vazio.")
        self.issuers = ids
        rm = cfg.risk_model
        self.min_names = rm.min_names_per_sector
        self.structure: FactorStructure = factor_structure(panel, ids, self.min_names)
        self.inputs: StyleInputs = prepare_style_inputs(panel, md, cfg, ids)
        self.styles = [s for s in STYLE_FACTORS if s in self.inputs.available_styles]
        self.factors = ([MARKET_FACTOR] + self.structure.country_factors
                        + self.structure.sector_factors + self.styles)
        self.factor_groups: dict[str, str] = {MARKET_FACTOR: "market"}
        self.factor_groups.update({f: "country" for f in self.structure.country_factors})
        self.factor_groups.update({f: "sector" for f in self.structure.sector_factors})
        self.factor_groups.update({s: "style" for s in self.styles})
        self.dates = self.inputs.dates
        self._dummies = self.structure.dummies(ids).to_numpy(dtype=float)
        k = len(self.factors)
        nc, ns = len(self.structure.country_factors), len(self.structure.sector_factors)
        self._country_idx = np.arange(1, 1 + nc)
        self._sector_idx = np.arange(1 + nc, 1 + nc + ns)
        self._dummy_idx = np.arange(1, 1 + nc + ns)
        self._style_idx = np.arange(1 + nc + ns, k)

        T, N = len(self.dates), len(ids)
        self._f = np.full((T, k), np.nan)
        self._e = np.full((T, N), np.nan)
        self._e2 = np.full((T, N), np.nan)  # e² corrigido por alavancagem (HC2)
        self._cw = np.full((T, k), np.nan)  # pesos de restrição (países e setores) por dia
        self._fits: dict[int, _DayFit] = {}
        self._x_cache: dict[int, tuple[np.ndarray, dict]] = {}
        self._model_cache: dict[int, RiskModel] = {}

        p0 = 1 if start is None else max(1, self.inputs.position(start))
        p1 = T - 1 if end is None else self.inputs.position(end)
        self._first_pos, self._last_pos = p0, p1
        for p in range(p0, p1 + 1):
            self._fit_day(p)

    # ------------------------------------------------------------------ exposições
    def _refresh_pos(self, p: int) -> int:
        return (p // self.refresh_days) * self.refresh_days

    def exposures_at_pos(self, pos: int) -> tuple[np.ndarray, dict]:
        """Matriz completa (N × K) de exposições com dados <= ``pos`` (cacheada)."""
        if pos not in self._x_cache:
            std, meta = standardized_styles(self.inputs, pos, self.cfg.alpha.winsor_z)
            x = np.column_stack([
                np.ones(len(self.issuers)), self._dummies,
                std[self.styles].to_numpy(dtype=float),
            ]) if self.styles else np.column_stack([np.ones(len(self.issuers)), self._dummies])
            self._x_cache[pos] = (x, meta)
        return self._x_cache[pos]

    # ------------------------------------------------------------------ regressão diária
    def _fit_day(self, p: int) -> None:
        x_all, _ = self.exposures_at_pos(self._refresh_pos(p - 1))
        r_raw = self.inputs.returns[p]
        cap = self.inputs.mcap[p - 1]
        obs = np.isfinite(r_raw) & np.isfinite(cap) & (cap > 0) & np.isfinite(x_all).all(axis=1)
        n_obs = int(obs.sum())
        r_w = np.clip(r_raw, -RETURN_WINSOR, RETURN_WINSOR)
        n_wins = int((np.abs(r_raw[obs]) > RETURN_WINSOR).sum())
        k = len(self.factors)
        if n_obs == 0:
            self._fits[p] = _DayFit("pulado:sem_observacoes", 0, 0, np.nan)
            return
        xo = x_all[obs]
        active = np.zeros(k, dtype=bool)
        active[0] = True
        if len(self._dummy_idx):
            members = (xo[:, self._dummy_idx] != 0).sum(axis=0)
            active[self._dummy_idx] = members >= self.min_names
        if len(self._style_idx):
            xs = xo[:, self._style_idx]
            nonzero = (xs != 0).sum(axis=0)
            active[self._style_idx] = (nonzero >= self.min_names) & (xs.std(axis=0) > 1e-12)
        n_act = int(active.sum())
        if n_obs < 2 * n_act:
            self._fits[p] = _DayFit("pulado:poucas_observacoes", n_obs, n_wins, np.nan)
            return
        capo = cap[obs]
        blocks, weights = [], []
        for idx in (self._country_idx, self._sector_idx):
            idx_a = idx[active[idx]]
            if len(idx_a) == 0:
                continue
            w_b = (xo[:, idx_a] * capo[:, None]).sum(axis=0) / capo.sum()
            blocks.append(idx_a)
            weights.append(w_b)
            self._cw[p, idx_a] = w_b
        R = _restriction_matrix(active, blocks, weights)
        v = np.sqrt(capo)                 # peso WLS = √mcap
        sw = np.sqrt(v)                   # escala das linhas = √peso
        A = (xo[:, active] @ R) * sw[:, None]
        g, _, rank, _ = np.linalg.lstsq(A, r_w[obs] * sw, rcond=None)
        if rank < R.shape[1]:
            self._fits[p] = _DayFit("pulado:posto_deficiente", n_obs, n_wins, np.nan)
            self._cw[p] = np.nan
            return
        f_act = R @ g
        self._f[p, active] = f_act
        res_mask = np.isfinite(r_raw) & np.isfinite(x_all).all(axis=1)
        e = r_w[res_mask] - x_all[res_mask][:, active] @ f_act
        self._e[p, res_mask] = e
        # Alavancagem h_ii no espaço transformado (fora da regressão: h = 0).
        q, _ = np.linalg.qr(A)
        lev = np.zeros(len(r_raw))
        lev[obs] = np.minimum((q ** 2).sum(axis=1), MAX_LEVERAGE)
        self._e2[p, res_mask] = e ** 2 / (1.0 - lev[res_mask])
        fit = xo[:, active] @ f_act
        ro = r_w[obs]
        rbar = float((v * ro).sum() / v.sum())
        sst = float((v * (ro - rbar) ** 2).sum())
        sse = float((v * (ro - fit) ** 2).sum())
        r2 = 1.0 - sse / sst if sst > 0 else np.nan
        self._fits[p] = _DayFit("ok", n_obs, n_wins, r2)

    # ------------------------------------------------------------------ diagnósticos
    @property
    def factor_returns_all(self) -> pd.DataFrame:
        """Retornos fatoriais diários de todas as datas regredidas (NaN = fator fora do dia)."""
        ok = [p for p, fit in sorted(self._fits.items()) if fit.status == "ok"]
        return pd.DataFrame(self._f[ok], index=self.dates[ok], columns=self.factors)

    @property
    def constraint_weights(self) -> pd.DataFrame:
        """Pesos de capitalização usados nas restrições de país/setor por data regredida."""
        ok = [p for p, fit in sorted(self._fits.items()) if fit.status == "ok"]
        cols = self.structure.country_factors + self.structure.sector_factors
        idx = [self.factors.index(c) for c in cols]
        return pd.DataFrame(self._cw[np.ix_(ok, idx)], index=self.dates[ok], columns=cols)

    def regression_diagnostics(self) -> pd.DataFrame:
        rows = {self.dates[p]: {"status": fit.status, "n_obs": fit.n_obs,
                                "n_winsorized": fit.n_winsorized, "r_squared": fit.r_squared}
                for p, fit in sorted(self._fits.items())}
        return pd.DataFrame.from_dict(rows, orient="index")

    # ------------------------------------------------------------------ modelo numa data
    def model_at(self, d: date_type | pd.Timestamp) -> RiskModel:
        """``RiskModel`` com dados <= ``d`` (último pregão do painel <= ``d``)."""
        pos = self.inputs.position(d)
        if pos > self._last_pos:
            raise ValueError(
                f"Estimador calculado até {self.dates[self._last_pos].date()}; pedido {d}.")
        if pos not in self._model_cache:
            self._model_cache[pos] = self._build_model(pos)
        return self._model_cache[pos]

    def _build_model(self, pos: int) -> RiskModel:
        rm = self.cfg.risk_model
        lo = max(self._first_pos, pos - rm.history_days + 1)
        win = np.arange(lo, pos + 1)
        ok_rows = np.array([p for p in win if self._fits.get(p) and self._fits[p].status == "ok"],
                           dtype=int)
        if len(ok_rows) < MIN_FACTOR_OBS:
            raise ValueError(
                f"Histórico insuficiente para o modelo de risco em {self.dates[pos].date()}: "
                f"{len(ok_rows)} dias regredidos (< {MIN_FACTOR_OBS}).")
        f_win = self._f[win]
        n_fac_obs = np.isfinite(f_win).sum(axis=0)
        keep = n_fac_obs >= MIN_FACTOR_OBS
        dropped = {self.factors[k]: f"apenas {int(n_fac_obs[k])} dias com retorno fatorial"
                   for k in np.flatnonzero(~keep)}
        kept = [self.factors[k] for k in np.flatnonzero(keep)]

        cov, cov_meta = factor_covariance(
            f_win[:, keep], rm.halflife_factor_vol, rm.halflife_factor_corr, rm.newey_west_lags)
        factor_cov = pd.DataFrame(cov, index=kept, columns=kept)

        active = np.isfinite(self.inputs.price[pos])
        ids = [i for i, a in zip(self.issuers, active, strict=True) if a]
        x_full, x_meta = self.exposures_at_pos(pos)
        X = pd.DataFrame(x_full[active][:, keep], index=pd.Index(ids, name="issuer_id"),
                         columns=kept)
        spec_var, spec_meta = self._specific_variance(pos, win, active)

        dates_ok = self.dates[ok_rows]
        factor_returns = pd.DataFrame(self._f[np.ix_(ok_rows, np.flatnonzero(keep))],
                                      index=dates_ok, columns=kept)
        specific_returns = pd.DataFrame(self._e[np.ix_(ok_rows, np.flatnonzero(active))],
                                        index=dates_ok, columns=ids)
        r2 = pd.Series([self._fits[p].r_squared for p in ok_rows], index=dates_ok,
                       name="r_squared")
        skipped = {str(self.dates[p].date()): self._fits[p].status
                   for p in win if self._fits.get(p) and self._fits[p].status != "ok"}
        groups = {f: self.factor_groups[f] for f in kept}
        meta = {
            "data_date": str(self.dates[pos].date()),
            "history_days": rm.history_days,
            "window_start": str(self.dates[lo].date()),
            "n_dates_window": int(len(win)),
            "n_dates_regression": int(len(ok_rows)),
            "first_regression_date": str(dates_ok[0].date()),
            "last_regression_date": str(dates_ok[-1].date()),
            "skipped_dates": skipped,
            "n_factors": len(kept),
            "dropped_factors": dropped,
            "n_assets": len(ids),
            "estimation_universe": list(self.issuers),
            "regression": ("WLS peso √mcap(t-1); restrições Σ w_c f_c = 0 e Σ w_s f_s = 0 por "
                           "reparametrização; retornos truncados em ±25%"),
            "winsorized_returns": int(sum(self._fits[p].n_winsorized for p in ok_rows)),
            "mean_r_squared": float(np.nanmean(r2.to_numpy())) if len(r2) else np.nan,
            "exposure_refresh_days": self.refresh_days,
            "halflife_factor_vol": rm.halflife_factor_vol,
            "halflife_factor_corr": rm.halflife_factor_corr,
            "halflife_specific": rm.halflife_specific,
            "newey_west_lags": rm.newey_west_lags,
            "specific_shrinkage": rm.specific_shrinkage,
            "specific_vol_floor": SPECIFIC_VOL_FLOOR,
            "specific_leverage_correction": f"HC2: e²/(1−h), h ≤ {MAX_LEVERAGE}",
            "style_imputations": x_meta["style_imputations"],
            "value_source": dict(self.inputs.value_source),
            "style_flags": dict(self.inputs.flags),
            "non_point_in_time": [NON_PIT_NOTES["size"]] + (
                [NON_PIT_NOTES["value"]] if "value" in self.styles else []),
            **cov_meta,
            **spec_meta,
            **self.structure.meta(),
        }
        if self.md is not None and self.md.is_synthetic:
            meta["data_notice"] = "DADOS SIMULADOS"
        return RiskModel(
            as_of=self.dates[pos].date(), exposures=X, factor_cov=factor_cov,
            specific_var=spec_var, factor_returns=factor_returns,
            specific_returns=specific_returns, factor_groups=groups, r_squared=r2, meta=meta,
        )

    # ------------------------------------------------------------------ risco específico
    def _specific_variance(
        self, pos: int, win: np.ndarray, active: np.ndarray,
    ) -> tuple[pd.Series, dict]:
        rm = self.cfg.risk_model
        e2 = self._e2[win][:, active]
        ids = [i for i, a in zip(self.issuers, active, strict=True) if a]
        mask = np.isfinite(e2)
        n_obs = mask.sum(axis=0)
        w = ewma_weights(len(win), rm.halflife_specific)
        z = np.where(mask, e2, 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            var_d = (w[:, None] * z).sum(axis=0) / (w[:, None] * mask).sum(axis=0)
        vol = np.sqrt(var_d * TRADING_DAYS)
        reliable = (n_obs >= rm.min_obs_days) & np.isfinite(vol)

        cap = self.inputs.mcap[pos][active]
        country = self.structure.country.reindex(ids).fillna("SEM_PAIS").astype(str).to_numpy()
        tercile = np.full(len(ids), -1)
        ok_cap = np.isfinite(cap) & (cap > 0)
        if ok_cap.sum() >= 3:
            ranks = pd.Series(cap[ok_cap]).rank(method="first").to_numpy()
            tercile[ok_cap] = np.minimum((3 * (ranks - 1) / ok_cap.sum()).astype(int), 2)
        capw = np.where(ok_cap, cap, np.nan)

        def group_mean(sel: np.ndarray) -> float:
            s = sel & reliable
            if s.sum() == 0:
                return np.nan
            ww = capw[s]
            if np.isfinite(ww).sum() == s.sum() and np.nansum(ww) > 0:
                return float(np.sum(ww * vol[s]) / np.sum(ww))
            return float(np.mean(vol[s]))

        glob = group_mean(np.ones(len(ids), dtype=bool))
        target = np.full(len(ids), np.nan)
        level = np.empty(len(ids), dtype=object)
        for n in range(len(ids)):
            same_c = country == country[n]
            grp = same_c & (tercile == tercile[n]) & (tercile[n] >= 0)
            for name, sel in (("pais_x_tamanho", grp), ("pais", same_c)):
                if (sel & reliable).sum() >= 2:
                    target[n] = group_mean(sel)
                    level[n] = name
                    break
            else:
                target[n] = glob
                level[n] = "global"
        s = rm.specific_shrinkage
        shrunk = np.where(reliable, (1.0 - s) * vol + s * target, target)
        imputed = [i for i, r in zip(ids, reliable, strict=True) if not r]
        if not np.isfinite(shrunk).all():
            bad = [i for i, v in zip(ids, shrunk, strict=True) if not np.isfinite(v)]
            raise ValueError(f"Risco específico indefinido (sem grupo com histórico): {bad}")
        var = np.maximum(shrunk, SPECIFIC_VOL_FLOOR) ** 2
        floored = [i for i, v in zip(ids, shrunk, strict=True) if v < SPECIFIC_VOL_FLOOR]
        meta = {
            "specific_imputed_group_mean": imputed,
            "specific_floored": floored,
            "specific_obs": {i: int(n) for i, n in zip(ids, n_obs, strict=True)},
            "specific_shrinkage_level": {i: str(lv) for i, lv in zip(ids, level, strict=True)},
        }
        return pd.Series(var, index=pd.Index(ids, name="issuer_id"), name="specific_var"), meta


def estimate_risk_model(
    panel: AssetPanel,
    cfg: FundConfig,
    md: MarketData | None = None,
    as_of: date_type | pd.Timestamp | None = None,
    issuers: list[str] | None = None,
) -> RiskModel:
    """Modelo de risco com dados <= ``as_of`` (padrão: ``panel.as_of``) nos últimos
    ``cfg.risk_model.history_days`` pregões. Idêntico a ``RiskModelEstimator.model_at``."""
    d = pd.Timestamp(as_of if as_of is not None else panel.as_of)
    if d > pd.Timestamp(panel.as_of):
        raise ValueError(f"as_of {d.date()} posterior ao painel ({panel.as_of}).")
    dates = pd.DatetimeIndex(panel.returns.index)
    pos = int(dates.searchsorted(d, side="right")) - 1
    if pos < 1:
        raise ValueError("Painel sem histórico suficiente antes de as_of.")
    start = dates[max(1, pos - cfg.risk_model.history_days + 1)]
    est = RiskModelEstimator(panel, cfg, md=md, issuers=issuers, start=start, end=dates[pos])
    return est.model_at(d)
