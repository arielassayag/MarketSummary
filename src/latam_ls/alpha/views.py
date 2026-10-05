"""Visões qualitativas (IA e gestor) convertidas em inclinações de alpha limitadas e restrições.

Regras (ver docs/latam_ls/ARQUITETURA.md, princípio 2 — "IA só aperta, nunca afrouxa"):

- Inclinação por visão: ``z_tilt = (score/2) × max_view_tilt_z × confiança`` (|z_tilt| ≤
  ``max_view_tilt_z``) e ``α_add = IC_v × σ_específico × z_tilt``, com ``IC_v`` =
  ``min(view_information_coefficient, research.llm_view_ic)`` para IA (teto × fase de adoção;
  S0 ⇒ 0) e ``information_coefficient`` para o gestor.
- Várias visões da mesma fonte para um emissor: média das inclinações (continua limitada).
- Se houver visão do gestor (PM) para o emissor, ela SUBSTITUI a inclinação da IA (registrado).
- Restrições (``no_short``, ``no_long``, ``max_abs_weight``) são a união mais restritiva de
  todas as visões; ``max_abs_weight`` é sempre limitado ao mandato. Nenhuma visão consegue
  desfazer uma restrição imposta por outra (uma visão sem restrição não "libera" nada).
- Emissores fora do universo do alpha são registrados e ignorados. Emissor no universo sem
  alpha base (``NaN``) não recebe inclinação (a visão não cria alpha do nada), mas as
  restrições valem.
- As entradas nunca são modificadas.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from ..config import FundConfig
from ..contracts import AUTONOMOUS_DECIDER, View, ViewSource

CONSTRAINT_COLUMNS = ["no_short", "no_long", "max_abs_weight"]
TILT_COLUMNS = ["source", "n_views", "z_tilt", "ic", "alpha_add", "applied", "reason"]


def _finite(x: object) -> bool:
    """Verdadeiro para escalar numérico finito (``NaN``/``None``/texto ⇒ falso)."""
    try:
        return bool(np.isfinite(float(x)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _as_views(views: Iterable[View | dict]) -> list[View]:
    """Valida as visões pelo contrato (dicionários são aceitos e validados)."""
    return [v if isinstance(v, View) else View.model_validate(v) for v in views]


def mandate_max_abs_weight(cfg: FundConfig) -> float:
    """Maior peso absoluto permitido pelo mandato (teto para qualquer ``max_abs_weight``)."""
    return float(max(cfg.risk.max_long_weight, cfg.risk.max_short_weight))


def ai_view_ic(cfg: FundConfig) -> float:
    """IC efetivo das visões de IA: ``min(alpha.view_information_coefficient,
    research.llm_view_ic)``.

    ``view_information_coefficient`` é o teto (adoção plena, S3); o IC efetivo vem da fase de
    adoção ``research.llm_phase`` (S0 = shadow ⇒ 0: a IA não move o alpha, só restringe).
    O mínimo garante que nenhum chamador ultrapasse a fase, com ou sem override de config.
    """
    return float(min(cfg.alpha.view_information_coefficient, cfg.research.llm_view_ic))


def view_horizon_scale(cfg: FundConfig) -> float:
    """Mesma anualização do alpha quant: √(52 / horizonte em semanas) (alpha.combine)."""
    return float(np.sqrt(52.0 / float(cfg.alpha.horizon_weeks)))


def is_autonomous_view(view: View) -> bool:
    """Visão do PM escrita pela mente autônoma do CDP (IA), não por um gestor humano."""
    return view.author == AUTONOMOUS_DECIDER


def view_tilt_z(view: View, cfg: FundConfig) -> float:
    """Inclinação em unidades de z de uma visão: ``(score/2) × max_view_tilt_z × confiança``."""
    return float(view.score) / 2.0 * float(cfg.alpha.max_view_tilt_z) * float(view.confidence)


def _group_by_issuer(views: list[View]) -> dict[str, list[View]]:
    grouped: dict[str, list[View]] = {}
    for v in views:
        grouped.setdefault(v.issuer_id, []).append(v)
    return {k: grouped[k] for k in sorted(grouped)}


def view_tilt_table(
    alpha: pd.Series, views: Iterable[View | dict], specific_vol: pd.Series, cfg: FundConfig
) -> tuple[pd.DataFrame, list[str]]:
    """Tabela de inclinações por emissor com visão (somente emissores do universo do alpha).

    Colunas: ``source`` (``ai``/``pm``), ``n_views``, ``z_tilt``, ``ic``, ``alpha_add`` (anual,
    ``NaN`` se não aplicada), ``applied`` e ``reason`` (motivo de não aplicação).
    """
    log: list[str] = []
    rows: dict[str, dict] = {}
    ic_ai = ai_view_ic(cfg)
    vlist = _as_views(views)
    if any(v.source == ViewSource.AI for v in vlist):
        log.append(f"IC das visões de IA = {ic_ai:g} (fase {cfg.research.llm_phase}, teto "
                   f"{cfg.alpha.view_information_coefficient:g})"
                   + (" — modo shadow: IA não altera o alpha." if ic_ai == 0 else "."))
    for issuer, vs in _group_by_issuer(vlist).items():
        if issuer not in alpha.index:
            log.append(f"{issuer}: {len(vs)} visão(ões) ignorada(s) — emissor fora do universo "
                       "do alpha.")
            continue
        ai = [v for v in vs if v.source == ViewSource.AI]
        pm = [v for v in vs if v.source == ViewSource.PM]
        if pm:
            # PM autônomo (a mente de IA) segue a fase de adoção; gestor humano usa o IC do quant.
            ic_pm = (ic_ai if all(is_autonomous_view(v) for v in pm)
                     else float(cfg.alpha.information_coefficient))
            chosen, source, ic = pm, ViewSource.PM, ic_pm
            if ai:
                log.append(f"{issuer}: visão do gestor substitui a inclinação de "
                           f"{len(ai)} visão(ões) de IA.")
        else:
            chosen, source, ic = ai, ViewSource.AI, ic_ai
        z_tilt = float(np.mean([view_tilt_z(v, cfg) for v in chosen]))
        if len(chosen) > 1:
            log.append(f"{issuer}: {len(chosen)} visões de {source.value.upper()} agregadas "
                       "pela média das inclinações.")
        a = alpha.get(issuer, np.nan)
        sv = specific_vol.get(issuer, np.nan)
        reason = ""
        if not _finite(a):
            reason = "sem_alpha_base"
            log.append(f"{issuer}: sem alpha base — inclinação ignorada (restrições mantidas).")
        elif not (_finite(sv) and float(sv) > 0):
            reason = "sem_vol_especifica"
            log.append(f"{issuer}: sem volatilidade específica — inclinação ignorada "
                       "(restrições mantidas).")
        add = ic * view_horizon_scale(cfg) * float(sv) * z_tilt if reason == "" else np.nan
        rows[issuer] = {"source": source.value, "n_views": len(vs), "z_tilt": z_tilt, "ic": ic,
                        "alpha_add": add, "applied": reason == "", "reason": reason}
    table = pd.DataFrame.from_dict(rows, orient="index", columns=TILT_COLUMNS)
    table.index.name = "issuer_id"
    return table, log


def view_constraints(
    index: pd.Index, views: Iterable[View | dict], cfg: FundConfig
) -> tuple[pd.DataFrame, list[str]]:
    """Restrições por emissor (união mais restritiva das visões), para todo ``index``.

    ``no_short``/``no_long`` são OU lógico entre as visões; ``max_abs_weight`` é o menor teto
    informado, sempre limitado ao teto do mandato (``NaN`` = sem teto adicional de visão).
    ``no_short`` e ``no_long`` simultâneos zeram o teto (posição proibida).
    """
    log: list[str] = []
    cap = mandate_max_abs_weight(cfg)
    index = index.rename("issuer_id")  # novo objeto: nunca altera o índice de quem chamou
    no_short = pd.Series(False, index=index, dtype=bool)
    no_long = pd.Series(False, index=index, dtype=bool)
    max_abs = pd.Series(np.nan, index=index, dtype=float)
    for issuer, vs in _group_by_issuer(_as_views(views)).items():
        if issuer not in index:
            continue
        caps = []
        for v in vs:
            if v.max_abs_weight is None:
                continue
            if v.max_abs_weight > cap:
                who = "IA" if v.source == ViewSource.AI else "gestor"
                log.append(f"{issuer}: teto de {v.max_abs_weight:.2%} da visão de {who} "
                           f"limitado ao mandato ({cap:.2%}).")
            caps.append(min(float(v.max_abs_weight), cap))
        ns = any(v.no_short for v in vs)
        nl = any(v.no_long for v in vs)
        no_short[issuer] = ns
        no_long[issuer] = nl
        if caps:
            max_abs[issuer] = min(caps)
        if ns and nl:
            max_abs[issuer] = 0.0
            log.append(f"{issuer}: visões proíbem compra e venda — posição limitada a zero.")
    if not cfg.research.llm_can_only_tighten:
        log.append("llm_can_only_tighten=False ignorado: visões só podem restringir (invariante).")
    out = pd.DataFrame({"no_short": no_short, "no_long": no_long, "max_abs_weight": max_abs},
                       index=index, columns=CONSTRAINT_COLUMNS)
    return out, log


def apply_views(
    alpha: pd.Series, views: list[View], specific_vol: pd.Series, cfg: FundConfig
) -> tuple[pd.Series, pd.DataFrame, list[str]]:
    """Aplica as visões ao alpha (anual) e devolve (alpha ajustado, restrições, log).

    O alpha ajustado tem o mesmo índice de ``alpha``; as restrições cobrem todo o índice de
    ``alpha`` com colunas ``no_short``, ``no_long`` (bool) e ``max_abs_weight`` (fração do NAV,
    ``NaN`` = sem teto adicional). Nenhuma entrada é modificada.
    """
    if alpha.index.has_duplicates:
        raise ValueError("Índice de alpha com emissores duplicados.")
    vs = _as_views(views)
    table, log_t = view_tilt_table(alpha, vs, specific_vol, cfg)
    constraints, log_c = view_constraints(alpha.index, vs, cfg)
    adjusted = pd.to_numeric(alpha, errors="coerce").astype(float).copy()
    applied = table[table["applied"].astype(bool)] if len(table) else table
    if len(applied):
        adds = applied["alpha_add"].astype(float)
        adjusted.loc[adds.index] = adjusted.loc[adds.index] + adds
        for issuer, row in applied.iterrows():
            log_t.append(f"{issuer}: inclinação {row['source'].upper()} z={row['z_tilt']:+.2f} "
                         f"⇒ α {row['alpha_add']:+.2%} a.a.")
    adjusted.name = alpha.name
    log_s: list[str] = []
    if getattr(cfg.alpha, "view_sign_coherence", False):
        constraints, log_s = sign_coherence_constraints(constraints, vs)
    return adjusted, constraints, log_t + log_c + log_s


def final_view_sign(views: list[View]) -> dict[str, int]:
    """Sinal final da visão por emissor: o PM prevalece; senão Σ score·confiança da pesquisa."""
    pm: dict[str, int] = {}
    ai: dict[str, float] = {}
    for v in views:
        if v.score == 0:
            continue
        if v.source == ViewSource.PM:
            pm[v.issuer_id] = int(np.sign(v.score))
        else:
            ai[v.issuer_id] = ai.get(v.issuer_id, 0.0) + v.score * float(v.confidence)
    out = {k: int(np.sign(x)) for k, x in ai.items() if x != 0}
    out.update(pm)
    return out


def sign_coherence_constraints(constraints: pd.DataFrame, views: list[View]
                               ) -> tuple[pd.DataFrame, list[str]]:
    """Coerência de sinal: nunca vender um nome com visão final positiva nem comprar um com
    visão final negativa (o otimizador busca hedges em outros nomes). Só aperta."""
    c = constraints.copy()
    log: list[str] = []
    for issuer, sign in sorted(final_view_sign(views).items()):
        if issuer not in c.index:
            continue
        col = "no_short" if sign > 0 else "no_long"
        if not bool(c.at[issuer, col]):
            c.at[issuer, col] = True
            log.append(f"{issuer}: coerência de sinal com a visão "
                       f"{'positiva' if sign > 0 else 'negativa'} ⇒ {col}")
    return c, log
