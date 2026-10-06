"""Padronização, combinação e ortogonalização dos sinais em alpha anual puro.

Pipeline (ver docs/cdp/ARQUITETURA.md, seção 6):

1. Cada sinal bruto vira um z-score robusto (mediana/MAD, winsorizado em ``winsor_z``),
   opcionalmente dentro de grupos (ex.: setor).
2. Combinação ponderada pelos pesos da configuração, **renormalizados por emissor** sobre os
   sinais disponíveis. Sinal ausente não vira zero: ele simplesmente não entra na média
   daquele emissor. Emissor sem nenhum sinal fica ``NaN`` e é excluído. O composto de cada
   emissor é dividido pelo seu desvio esperado ``sqrt(aᵀCa)`` (C = correlação entre sinais),
   para que a cobertura parcial não infle o z.
3. O composto é re-padronizado (média 0, desvio 1) e limitado a ``±winsor_z``.
4. Alpha anual (Grinold): ``α = IC × σ_específico × z``.
5. Alpha puro: resíduo WLS de ``α`` contra as exposições do modelo de risco (pesos
   ``1/σ²_específico``), de modo que ``Bᵀ W α = 0`` — nenhum retorno esperado vem de fatores.

Todas as contas são determinísticas; nenhum número vem de LLM.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import FundConfig
from ..risk.types import RiskModel

MAD_TO_SIGMA = 1.4826
"""Fator de consistência do MAD para o desvio-padrão sob normalidade."""

MIN_CROSS_SECTION = 3
"""Mínimo de observações válidas para padronizar uma cross-section (abaixo disso: NaN)."""

MIN_GROUP_OBS = 5
"""Mínimo de observações válidas para padronizar dentro de um grupo; abaixo disso, o emissor
recebe o z-score da cross-section inteira (fallback documentado)."""

MIN_IC_OBS = 3
"""Mínimo de pares válidos para calcular um coeficiente de informação."""

ORTHOGONALITY_TOL = 1e-8
"""Tolerância relativa usada apenas para reportar a qualidade numérica da ortogonalização."""

MIN_CORR_OBS = 10
"""Mínimo de emissores com os dois sinais para estimar a correlação entre eles; abaixo disso o
par é tratado como independente (registrado nas notas)."""

CORR_EIGEN_FLOOR = 0.05
"""Piso dos autovalores da correlação entre sinais: garante matriz positiva definida (a
correlação por pares completos pode não ser) e limita a amplificação de compostos degenerados."""

MAX_WLS_WEIGHT_RATIO = 1e4
"""Teto do peso WLS (1/σ²) relativo à mediana: equivale a um piso de σ específico de 1% da
mediana. Evita que uma variância específica quase nula domine a regressão e destrua o posto
numérico; quando aplicado, é registrado nas notas."""


# ==========================================================
# Padronização robusta
# ==========================================================

def _robust_z_values(x: pd.Series, winsor: float) -> pd.Series:
    """z-score robusto de uma cross-section (sem grupos). ``NaN`` preservado.

    - Centro = mediana; escala = MAD × 1,4826 (fallback: desvio-padrão quando MAD = 0).
    - Winsoriza em ``±winsor``, re-padroniza (média 0, desvio 1) e limita de novo em
      ``±winsor`` para garantir o teto.
    - Menos de ``MIN_CROSS_SECTION`` observações: tudo ``NaN`` (sem informação suficiente).
    - Todos os valores iguais: z = 0 para os válidos (sem dispersão, todos na mediana).
    """
    out = pd.Series(np.nan, index=x.index, dtype=float)
    v = x.dropna()
    if len(v) < MIN_CROSS_SECTION:
        return out
    med = float(v.median())
    scale = float((v - med).abs().median()) * MAD_TO_SIGMA
    if not scale > 0:
        scale = float(v.std(ddof=0))
    if not scale > 0:
        out.loc[v.index] = 0.0
        return out
    z0 = ((v - med) / scale).clip(-winsor, winsor)
    sd = float(z0.std(ddof=0))
    if not sd > 0:
        out.loc[v.index] = 0.0
        return out
    z = ((z0 - float(z0.mean())) / sd).clip(-winsor, winsor)
    out.loc[v.index] = z.to_numpy(dtype=float)
    return out


def robust_zscore(raw: pd.Series, winsor: float, groups: pd.Series | None = None) -> pd.Series:
    """z-score robusto (mediana/MAD → winsorização → padronização), preservando ``NaN``.

    Com ``groups`` (ex.: setor por emissor), a padronização é feita dentro de cada grupo com
    pelo menos ``MIN_GROUP_OBS`` observações válidas; emissores de grupos pequenos ou sem
    grupo recebem o z-score da cross-section inteira. Valores ``±inf`` são tratados como
    ausentes. O resultado nunca excede ``±winsor``.
    """
    if not winsor > 0:
        raise ValueError("winsor precisa ser positivo.")
    x = pd.to_numeric(raw, errors="coerce").astype(float)
    x = x.where(np.isfinite(x))
    pooled = _robust_z_values(x, winsor)
    if groups is None:
        return pooled.rename(raw.name)
    g = groups.reindex(x.index)
    out = pooled.copy()
    valid_counts = x.notna().groupby(g, dropna=True).sum()
    for key in sorted(valid_counts.index, key=str):
        if valid_counts[key] < MIN_GROUP_OBS:
            continue
        members = g.index[(g == key).fillna(False).to_numpy(dtype=bool)]
        out.loc[members] = _robust_z_values(x.loc[members], winsor).to_numpy(dtype=float)
    return out.rename(raw.name)


# ==========================================================
# Neutralização (WLS)
# ==========================================================

def _wls_residual(
    y: pd.Series, exposures: pd.DataFrame, weights: pd.Series | None
) -> tuple[pd.Series, pd.Index, int]:
    """Resíduo WLS de ``y`` em ``exposures``; retorna (resíduo, índices usados, posto)."""
    idx = y.index
    X = exposures.reindex(idx).apply(pd.to_numeric, errors="coerce").astype(float)
    yv = pd.to_numeric(y, errors="coerce").astype(float)
    valid = yv.notna() & np.isfinite(yv)
    # Fatores sem nenhuma exposição definida entre os válidos não identificam nada: descartados.
    X = X.loc[:, X.loc[valid].notna().any(axis=0)]
    valid &= X.notna().all(axis=1) & np.isfinite(X).all(axis=1)
    if weights is not None:
        w = pd.to_numeric(weights.reindex(idx), errors="coerce").astype(float)
        valid &= w.notna() & np.isfinite(w) & (w > 0)
    else:
        w = pd.Series(1.0, index=idx)
    out = pd.Series(np.nan, index=idx, dtype=float, name=y.name)
    used = idx[valid.to_numpy(dtype=bool)]
    if len(used) == 0:
        return out, used, 0
    Xv = X.loc[used].to_numpy(dtype=float)
    keep = np.any(Xv != 0.0, axis=0)
    Xv = Xv[:, keep]
    yy = yv.loc[used].to_numpy(dtype=float)
    if Xv.shape[1] == 0:
        out.loc[used] = yy
        return out, used, 0
    sw = np.sqrt(w.loc[used].to_numpy(dtype=float))
    coef, _, rank, _ = np.linalg.lstsq(Xv * sw[:, None], yy * sw, rcond=None)
    out.loc[used] = yy - Xv @ coef
    return out, used, int(rank)


def neutralize(
    z: pd.Series, exposures: pd.DataFrame, weights: pd.Series | None = None
) -> pd.Series:
    """Resíduo WLS de ``z`` contra ``exposures`` (emissor × fator).

    Garante ``Xᵀ W r = 0`` no conjunto usado. Emissores com ``z`` ausente, exposição ausente
    ou peso inválido (``NaN``, ``≤ 0``) ficam ``NaN`` — nunca são neutralizados com zeros
    inventados. Colinearidade (ex.: mercado = soma dos países) é tratada por mínimos
    quadrados com pseudo-inversa; o resíduo é único mesmo com posto incompleto.
    """
    resid, _, _ = _wls_residual(z, exposures, weights)
    return resid


# ==========================================================
# Resultado e construção do alpha
# ==========================================================

@dataclass
class AlphaResult:
    """Alpha por emissor com rastreabilidade completa (unidades anuais em decimal).

    - ``signal_z``: z-score robusto de cada sinal usado (emissor × sinal).
    - ``weights_used``: pesos efetivos normalizados (soma 1) dos sinais usados.
    - ``composite_z``: composto re-padronizado e limitado a ``±winsor_z``.
    - ``alpha_raw``: ``IC × σ_específico × composite_z``.
    - ``alpha``: alpha puro (ortogonal às exposições fatoriais) ou igual a ``alpha_raw`` se a
      ortogonalização estiver desligada.
    - ``contributions``: decomposição linear de ``alpha_raw`` por sinal (``NaN`` = sinal
      indisponível para o emissor); a soma por linha é igual a ``alpha_raw``.
    - ``contributions_pure``: decomposição de ``alpha`` por sinal após a ortogonalização (a
      soma por linha é igual a ``alpha``).
    - ``coverage``: número de sinais usados no composto de cada emissor (0 = excluído).
    - ``exclusion_reason``: motivo de exclusão (``""`` quando o emissor tem alpha).
    """

    signal_z: pd.DataFrame
    weights_used: dict[str, float]
    composite_z: pd.Series
    alpha_raw: pd.Series
    alpha: pd.Series
    contributions: pd.DataFrame
    coverage: pd.Series
    notes: list[str]
    contributions_pure: pd.DataFrame = field(default_factory=pd.DataFrame)
    exclusion_reason: pd.Series = field(default_factory=lambda: pd.Series(dtype=object))

    @property
    def included(self) -> list[str]:
        """Emissores com alpha puro definido."""
        return list(self.alpha.index[self.alpha.notna()])

    def to_frame(self) -> pd.DataFrame:
        """Tabela por emissor para relatório/UI (z de cada sinal com prefixo ``z_``)."""
        base = pd.DataFrame({
            "composite_z": self.composite_z,
            "alpha_raw": self.alpha_raw,
            "alpha": self.alpha,
            "coverage": self.coverage,
            "exclusion_reason": self.exclusion_reason.reindex(self.alpha.index),
        })
        z = self.signal_z.add_prefix("z_")
        return base.join(z)


def _resolve_weights(
    requested: dict[str, float], available: list[str], notes: list[str]
) -> dict[str, float]:
    """Valida e normaliza os pesos sobre os sinais disponíveis (soma 1)."""
    for name, w in requested.items():
        ok = isinstance(w, numbers.Real) and not isinstance(w, bool)
        if not ok or not math.isfinite(float(w)) or float(w) < 0:
            raise ValueError(f"Peso inválido para o sinal '{name}': {w!r} (precisa ser ≥ 0).")
    missing = [s for s in requested if s not in available and requested[s] > 0]
    if missing:
        notes.append(f"Sinais com peso mas ausentes na entrada (ignorados): {missing}.")
    ignored = [s for s in available if s not in requested]
    if ignored:
        notes.append(f"Sinais presentes sem peso configurado (ignorados): {ignored}.")
    zero = [s for s in available if s in requested and float(requested[s]) == 0.0]
    if zero:
        notes.append(f"Sinais com peso zero (ignorados): {zero}.")
    used = {s: float(requested[s]) for s in requested if s in available and requested[s] > 0}
    if not used:
        raise ValueError("Nenhum sinal com peso positivo disponível para compor o alpha.")
    total = sum(used.values())
    return {s: w / total for s, w in used.items()}


def signal_correlation(z: pd.DataFrame, notes: list[str] | None = None) -> pd.DataFrame:
    """Correlação cross-section entre os z-scores dos sinais, positiva definida.

    Pares completos com pelo menos ``MIN_CORR_OBS`` emissores; par sem dado suficiente (ou sinal
    sem dispersão) ⇒ correlação 0 (independência, registrada). Autovalores limitados a
    ``CORR_EIGEN_FLOOR`` e diagonal re-normalizada para 1.
    """
    cols = list(z.columns)
    c = z.astype(float).corr(min_periods=MIN_CORR_OBS).reindex(index=cols, columns=cols)
    m = c.to_numpy(dtype=float, copy=True)
    unknown = ~np.isfinite(m)
    np.fill_diagonal(unknown, False)
    if unknown.any() and notes is not None:
        pairs = sorted({tuple(sorted((cols[i], cols[j]))) for i, j in zip(*np.nonzero(unknown),
                                                                        strict=True)})
        notes.append(f"Correlação entre sinais sem dados suficientes (assumida 0): {pairs}.")
    m[~np.isfinite(m)] = 0.0
    np.fill_diagonal(m, 1.0)
    m = (m + m.T) / 2.0
    if len(cols):
        vals, vecs = np.linalg.eigh(m)
        if vals.min() < CORR_EIGEN_FLOOR:
            m = (vecs * np.maximum(vals, CORR_EIGEN_FLOOR)) @ vecs.T
            d = np.sqrt(np.diag(m))
            m = m / np.outer(d, d)
    return pd.DataFrame(m, index=cols, columns=cols)


def coverage_scale(a: pd.DataFrame, corr: pd.DataFrame) -> pd.Series:
    """Desvio-padrão esperado do composto de cada emissor: ``sqrt(aᵢᵀ C aᵢ)``.

    ``a``: pesos renormalizados por emissor (0 para sinal indisponível; linha ``NaN`` = sem
    sinais). Dividir o composto por essa escala dá variância unitária a todos os emissores,
    qualquer que seja a cobertura — sem isso, um emissor com um único sinal teria dispersão
    ``1/sqrt(aᵀCa)`` vezes maior que um emissor com todos os sinais (≈2× com os pesos padrão)
    depois da re-padronização, ou seja, mais alpha justamente onde há menos informação.
    """
    cols = list(corr.columns)
    av = a.reindex(columns=cols).to_numpy(dtype=float)
    c = corr.to_numpy(dtype=float)
    row_ok = np.isfinite(av).all(axis=1) & (np.abs(av).sum(axis=1) > 0)
    av0 = np.where(row_ok[:, None], av, 0.0)
    v = np.einsum("ij,jk,ik->i", av0, c, av0)
    out = np.where(row_ok & (v > 0), np.sqrt(np.where(v > 0, v, 1.0)), np.nan)
    return pd.Series(out, index=a.index, dtype=float)


def _fmt_ids(ids: list[str], limit: int = 10) -> str:
    head = ", ".join(ids[:limit])
    return head + (f" … (+{len(ids) - limit})" if len(ids) > limit else "")


def build_alpha(
    signals_raw: pd.DataFrame,
    model: RiskModel,
    cfg: FundConfig,
    weights: dict[str, float] | None = None,
    sector: pd.Series | None = None,
) -> AlphaResult:
    """Combina sinais brutos (emissor × sinal) em alpha anual puro.

    ``weights`` substitui ``cfg.alpha.signal_weights`` (ex.: pesos por IC realizado). Com
    ``sector``, cada sinal é padronizado dentro do setor. Emissores fora do modelo de risco,
    sem sinais, sem risco específico ou sem exposições ficam ``NaN`` e são listados em
    ``exclusion_reason``. As entradas não são modificadas.
    """
    if signals_raw.index.has_duplicates:
        dups = signals_raw.index[signals_raw.index.duplicated()].unique().tolist()
        raise ValueError(f"Emissores duplicados nos sinais: {dups}")
    acfg = cfg.alpha
    winsor = float(acfg.winsor_z)
    # IC medido no horizonte de ``horizon_weeks`` semanas ⇒ alpha anualizado
    # = IC × σ_anual × √(52/H) × z  (Grinold com σ do horizonte, escalado para 1 ano).
    horizon_scale = float(np.sqrt(52.0 / float(acfg.horizon_weeks)))
    ic = float(acfg.information_coefficient) * horizon_scale
    notes: list[str] = []
    requested = dict(weights) if weights is not None else dict(acfg.signal_weights)
    weights_used = _resolve_weights(requested, list(signals_raw.columns), notes)
    sig_names = list(weights_used)
    full_idx = signals_raw.index
    reason = pd.Series("", index=full_idx, dtype=object)

    in_model = full_idx.isin(model.assets)
    universe = full_idx[in_model]
    outside = full_idx[~in_model].tolist()
    if outside:
        reason.loc[outside] = "fora_do_modelo_de_risco"
        notes.append(f"{len(outside)} emissor(es) fora do modelo de risco excluídos: "
                     f"{_fmt_ids([str(i) for i in outside])}.")

    raw = signals_raw.loc[universe, sig_names].apply(pd.to_numeric, errors="coerce")
    raw = raw.astype(float)
    n_inf = int((~np.isfinite(raw) & raw.notna()).sum().sum())
    if n_inf:
        notes.append(f"{n_inf} valor(es) infinito(s) tratados como ausentes.")
    raw = raw.where(np.isfinite(raw))
    grp = sector.reindex(universe) if sector is not None else None
    Z = pd.DataFrame({s: robust_zscore(raw[s], winsor, grp) for s in sig_names},
                     index=universe, columns=sig_names)

    # Pesos renormalizados por emissor sobre os sinais disponíveis (sem imputar sinais).
    avail = Z.notna()
    W = avail.astype(float).mul(pd.Series(weights_used), axis=1)
    wsum = W.sum(axis=1)
    A = W.div(wsum.where(wsum > 0), axis=0)
    coverage_u = avail.sum(axis=1).astype(int)
    # Normalização pela cobertura: cada composto passa a ter variância esperada unitária
    # (sqrt(aᵀCa)), para que poucos sinais não inflem o z depois da re-padronização.
    cscale = coverage_scale(A, signal_correlation(Z, notes)).where(coverage_u > 0)
    Zs = Z.div(cscale, axis=0)
    composite = (A * Zs).sum(axis=1, min_count=1).where(coverage_u > 0)
    no_signal = universe[(coverage_u == 0).to_numpy(dtype=bool)].tolist()
    if no_signal:
        reason.loc[no_signal] = "sem_sinais"
        notes.append(f"{len(no_signal)} emissor(es) sem nenhum sinal disponível excluídos: "
                     f"{_fmt_ids([str(i) for i in no_signal])}.")
    partial = int(((coverage_u > 0) & (coverage_u < len(sig_names))).sum())
    if partial:
        cs = cscale[(coverage_u > 0) & (coverage_u < len(sig_names))]
        notes.append(f"{partial} emissor(es) com cobertura parcial: pesos renormalizados "
                     "sobre os sinais disponíveis e composto normalizado pelo desvio esperado "
                     f"(sqrt(aᵀCa) entre {cs.min():.2f} e {cs.max():.2f}).")

    valid_c = composite.dropna()
    mu = float(valid_c.mean()) if len(valid_c) else float("nan")
    sd = float(valid_c.std(ddof=0)) if len(valid_c) else float("nan")
    if len(valid_c) < MIN_CROSS_SECTION or not sd > 0:
        notes.append("Cross-section do composto insuficiente ou sem dispersão: alpha indefinido.")
        cz_unclipped = pd.Series(np.nan, index=universe, dtype=float)
        reason.loc[valid_c.index] = "composto_degenerado"
    else:
        cz_unclipped = (composite - mu) / sd
    cz = cz_unclipped.clip(-winsor, winsor)
    n_clip = int((cz_unclipped.abs() > winsor).sum())
    if n_clip:
        notes.append(f"{n_clip} emissor(es) com composto limitado a ±{winsor:g} desvios.")
    shrink = (cz / cz_unclipped).where(cz_unclipped != 0, 1.0)

    spec_var = pd.to_numeric(model.specific_var.reindex(universe), errors="coerce").astype(float)
    spec_vol = np.sqrt(spec_var.where(spec_var > 0))
    bad_vol = universe[(spec_vol.isna() & cz.notna()).to_numpy(dtype=bool)].tolist()
    if bad_vol:
        reason.loc[bad_vol] = "sem_risco_especifico"
        notes.append(f"{len(bad_vol)} emissor(es) sem variância específica válida excluídos: "
                     f"{_fmt_ids([str(i) for i in bad_vol])}.")
    alpha_raw_u = ic * spec_vol * cz

    scale = (ic * spec_vol * shrink / sd) if sd > 0 else pd.Series(np.nan, index=universe)
    # Σ_s a_s (z_s/escala − μ) = composto − μ, pois Σ_s a_s = 1 ⇒ soma exata = alpha_raw.
    contrib_u = (A * (Zs - mu)).mul(scale, axis=0).where(Z.notna())
    contrib_u = contrib_u.where(alpha_raw_u.notna(), axis=0)

    if acfg.orthogonalize_to_factors:
        inv_var = wls_weights(spec_var, notes)
        alpha_u, used, rank = _wls_residual(alpha_raw_u, model.exposures, inv_var)
        lost = universe[(alpha_raw_u.notna() & alpha_u.isna()).to_numpy(dtype=bool)].tolist()
        if lost:
            reason.loc[lost] = "sem_exposicoes_fatoriais"
            notes.append(f"{len(lost)} emissor(es) sem exposições completas no modelo "
                         f"excluídos: {_fmt_ids([str(i) for i in lost])}.")
        if len(used) and len(used) <= rank:
            notes.append(f"Ortogonalização degenerada: {len(used)} emissores para posto {rank}; "
                         "o alpha puro tende a zero.")
        # Contribuições puras: o operador de resíduo é linear; um sinal não usado contribui
        # exatamente 0 antes da projeção (peso a_is = 0), por isso o preenchimento é exato.
        filled = contrib_u.fillna(0.0).where(alpha_raw_u.notna(), axis=0)
        pure_u = pd.DataFrame(
            {s: _wls_residual(filled[s], model.exposures, inv_var)[0] for s in sig_names},
            index=universe, columns=sig_names,
        )
        notes.extend(_orthogonality_notes(alpha_raw_u, alpha_u, model.exposures, inv_var, used))
    else:
        alpha_u = alpha_raw_u.copy()
        pure_u = contrib_u.copy()
        notes.append("Ortogonalização aos fatores desligada na configuração: alpha = alpha bruto.")

    included = int(alpha_u.notna().sum())
    notes.append(f"Alpha calculado para {included} de {len(full_idx)} emissores "
                 f"(IC={ic:g}, winsor=±{winsor:g}).")

    def full(s: pd.Series) -> pd.Series:
        return s.reindex(full_idx).astype(float)

    coverage = coverage_u.reindex(full_idx, fill_value=0).astype(int)
    return AlphaResult(
        signal_z=Z.reindex(full_idx),
        weights_used=weights_used,
        composite_z=full(cz),
        alpha_raw=full(alpha_raw_u),
        alpha=full(alpha_u),
        contributions=contrib_u.reindex(full_idx),
        coverage=coverage,
        notes=notes,
        contributions_pure=pure_u.reindex(full_idx),
        exclusion_reason=reason,
    )


def reresidualize(alpha: pd.Series, model: RiskModel) -> tuple[pd.Series, list[str]]:
    """Reortogonaliza aos fatores um alpha já inclinado pelas visões (a inclinação não é
    ortogonal): resíduo WLS (pesos 1/σ² limitados) nos emissores com alpha; emissor sem alpha
    continua ``NaN`` (nunca zero). Devolve o alpha puro e o diagnóstico de ortogonalidade."""
    notes: list[str] = []
    a = pd.to_numeric(alpha, errors="coerce").astype(float)
    if a.notna().sum() == 0:
        return a, ["Reortogonalização após as visões: sem alpha válido."]
    inv_var = wls_weights(model.specific_var.reindex(a.index), notes)
    res, used, _rank = _wls_residual(a, model.exposures, inv_var)
    lost = a.notna() & res.isna()
    out = res.where(~lost, np.nan)
    notes.extend(f"Após as visões: {m}" for m in
                 _orthogonality_notes(a, res, model.exposures, inv_var, used))
    if lost.any():
        notes.append(f"Reortogonalização após as visões: {int(lost.sum())} emissor(es) sem "
                     "exposições completas ficaram sem alpha.")
    out.name = alpha.name
    return out, notes


def wls_weights(specific_var: pd.Series, notes: list[str] | None = None) -> pd.Series:
    """Pesos da ortogonalização: ``1/σ²_específico``, limitados a ``MAX_WLS_WEIGHT_RATIO`` ×
    mediana. Variância ausente ou não positiva ⇒ ``NaN`` (emissor não ortogonalizável)."""
    var = pd.to_numeric(specific_var, errors="coerce").astype(float)
    w = 1.0 / var.where(var > 0)
    med = float(w.median()) if w.notna().any() else float("nan")
    if med > 0:
        cap = med * MAX_WLS_WEIGHT_RATIO
        capped = w.index[(w > cap).to_numpy(dtype=bool)].tolist()
        if capped and notes is not None:
            notes.append(f"Peso WLS limitado a {MAX_WLS_WEIGHT_RATIO:g}× a mediana para "
                         f"{len(capped)} emissor(es) com variância específica quase nula: "
                         f"{_fmt_ids([str(i) for i in capped])}.")
        w = w.clip(upper=cap)
    return w


def _orthogonality_notes(
    alpha_raw: pd.Series,
    alpha: pd.Series,
    exposures: pd.DataFrame,
    weights: pd.Series,
    used: pd.Index,
) -> list[str]:
    """Mede quanto do alpha bruto era fatorial e a precisão numérica de ``Bᵀ W α ≈ 0``.

    A precisão é o maior cosseno, na métrica ``W``, entre o alpha puro e cada coluna de
    exposição (invariante à escala de fatores e pesos).
    """
    if len(used) == 0:
        return ["Ortogonalização sem emissores válidos."]
    w = weights.loc[used].to_numpy(dtype=float)
    raw = alpha_raw.loc[used].to_numpy(dtype=float)
    pure = alpha.loc[used].to_numpy(dtype=float)
    ss_raw = float(np.sum(w * raw ** 2))
    removed = 1.0 - float(np.sum(w * pure ** 2)) / ss_raw if ss_raw > 0 else 0.0
    X = exposures.reindex(used).astype(float)
    X = X.loc[:, X.notna().all(axis=0)].to_numpy()
    norm_x = np.sqrt((w[:, None] * X ** 2).sum(axis=0))
    norm_a = float(np.sqrt(np.sum(w * pure ** 2)))
    cos = 0.0
    if X.shape[1] and norm_a > 0:
        dots = np.abs(X.T @ (w * pure))
        cos = float(np.max(np.where(norm_x > 0, dots / np.where(norm_x > 0, norm_x, 1.0), 0.0))
                    / norm_a)
    msgs = [f"Ortogonalização WLS (pesos 1/σ²): {removed:.1%} da variância ponderada do alpha "
            "bruto era explicada por fatores e foi removida."]
    if cos > ORTHOGONALITY_TOL:
        msgs.append(f"Aviso numérico: cosseno máximo entre alpha puro e fatores = {cos:.2e}.")
    return msgs


# ==========================================================
# Coeficiente de informação
# ==========================================================

def information_coefficient(
    signal: pd.Series, fwd_returns: pd.Series, method: str = "spearman"
) -> float:
    """Correlação cross-section entre sinal e retorno futuro (IC).

    ``method``: ``"spearman"`` (padrão, IC de rank) ou ``"pearson"``. Usa apenas pares com
    ambos os valores finitos; com menos de ``MIN_IC_OBS`` pares ou sem dispersão, retorna
    ``NaN`` (nunca zero).
    """
    if method not in ("spearman", "pearson"):
        raise ValueError(f"Método de IC desconhecido: {method!r} (use 'spearman' ou 'pearson').")
    s = pd.to_numeric(signal, errors="coerce").astype(float)
    r = pd.to_numeric(fwd_returns, errors="coerce").astype(float)
    df = pd.concat([s.rename("s"), r.rename("r")], axis=1, join="inner")
    df = df[np.isfinite(df).all(axis=1)]
    if len(df) < MIN_IC_OBS or df["s"].nunique() < 2 or df["r"].nunique() < 2:
        return float("nan")
    if method == "spearman":
        df = df.rank(method="average")
    return float(np.corrcoef(df["s"].to_numpy(), df["r"].to_numpy())[0, 1])
