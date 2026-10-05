"""Pipeline semanal autônomo do CDP — Cabra da Peste (segunda-feira, antes do fechamento).

Sequência (todas as contas em código determinístico):

1. ``prepare_week``: dados até o pregão anterior (sexta), painel em USD, modelo de risco
   (com escala de janela de evento), sinais, alpha puro, aluguel/squeeze, custos e livro atual.
2. ``build_proposal``: visões → alpha ajustado → limites por emissor → otimizador (vol-alvo) →
   compliance → posições/ordens/hedges → resumo de risco → memo.
3. ``run_weekly_decision``: carteira-sombra só-quant + carteira do CDP (pesquisa de IA + decisão do
   agente PM). Se a carteira do CDP falhar em algum gate HARD, cai em sequência para (a) só as
   restrições da IA, (b) só-quant e (c) manter a carteira anterior. A decisão autônoma é gravada
   com hash; a execução hipotética ocorre no fechamento do mesmo dia (MOC) pela rotina diária.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..alpha.combine import AlphaResult, build_alpha
from ..alpha.signals import compute_signals
from ..alpha.views import apply_views
from ..analytics.liquidity import liquidity_profile, liquidity_summary
from ..analytics.panel import AssetPanel, build_asset_panel, fx_for_lines
from ..analytics.shortability import issuer_side_lines, short_availability
from ..analytics.squeeze import squeeze_table
from ..config import FundConfig
from ..contracts import (
    BookedPosition,
    BookEntry,
    ExposureLine,
    OptimizerDiagnostics,
    Proposal,
    ResearchPack,
    RiskSummary,
    Severity,
    Side,
    View,
)
from ..hashing import sha256_obj
from ..market import MarketData
from ..portfolio.compliance import run_compliance
from ..portfolio.costs import CostModel, build_cost_model, estimate_rebalance_costs
from ..portfolio.optimizer import (
    OptimizationResult,
    build_asset_constraints,
    model_implied_betas,
    optimize,
)
from ..portfolio.trades import build_positions, build_trades, fx_hedges
from ..risk.analytics import (
    effective_n,
    historical_var_es,
    parametric_var_es,
    risk_decomposition,
)
from ..risk.event_scaling import apply_event_windows
from ..risk.exposures import market_weights
from ..risk.model import estimate_risk_model
from ..risk.stress import stress_tests
from ..risk.types import STYLE_FACTORS, RiskModel
from .memo import render_memo

SYSTEM_CREATOR = "CDP — motor quantitativo"
THEMES_PATH = "data/universe/themes.csv"


# ---------------------------------------------------------------- contexto da semana

@dataclass
class WeekContext:
    week: date
    cfg: FundConfig
    md: MarketData
    snapshot_id: str
    snapshot_hash: str
    panel: AssetPanel
    model: RiskModel
    market_w: pd.Series
    betas: pd.Series
    signals_raw: pd.DataFrame
    alpha: AlphaResult
    availability: pd.DataFrame
    sides: pd.DataFrame
    squeeze: pd.DataFrame
    cost_model: CostModel
    daily_vol: pd.Series
    nav: float
    current_w: pd.Series
    current_positions: list[BookedPosition] | None
    inception: bool
    themes: dict[str, list[str]] = field(default_factory=dict)
    drawdown: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def as_of(self) -> date:
        return self.md.as_of

    @property
    def is_synthetic(self) -> bool:
        return self.md.is_synthetic


def load_themes(path: str = THEMES_PATH) -> dict[str, list[str]]:
    """Temas (ex.: estatais) por emissor a partir de ``issuer_id,theme``; ausente ⇒ vazio."""
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        return {}
    return {t: sorted(g["issuer_id"].astype(str)) for t, g in df.groupby("theme")}


def current_weights_from_book(entry: BookEntry | None, nav: float,
                              drifted: dict[str, float] | None = None) -> pd.Series:
    """Pesos atuais por emissor: marcação mais recente (``drifted``) ou pesos efetivados."""
    if drifted:
        return pd.Series(drifted, dtype=float)
    if entry is None:
        return pd.Series(dtype=float)
    w: dict[str, float] = {}
    for p in entry.positions:
        w[p.issuer_id] = w.get(p.issuer_id, 0.0) + p.notional_usd / nav
    return pd.Series(w, dtype=float)


def prepare_week(md: MarketData, cfg: FundConfig, week: date, *, nav: float | None = None,
                 current_entry: BookEntry | None = None,
                 current_drifted_w: dict[str, float] | None = None,
                 drawdown: float | None = None, themes: dict[str, list[str]] | None = None,
                 ) -> WeekContext:
    """Monta o contexto quantitativo da semana com dados até ``md.as_of`` (pregão anterior)."""
    if md.as_of >= week:
        raise ValueError(f"Snapshot {md.as_of} não é anterior à data de decisão {week}: "
                         "a decisão de segunda usa dados até o pregão anterior.")
    notes: list[str] = []
    panel = build_asset_panel(md, cfg)
    issuers = panel.eligible
    model = estimate_risk_model(panel, cfg, md, as_of=md.as_of, issuers=issuers)
    model = apply_event_windows(model, panel.assets["country"], cfg, week)
    if model.meta.get("event_windows"):
        notes.append("Janela de evento ativa: " + "; ".join(
            f"{w['name']} (×{w['multiplier']:.2f} na vol de {w['country']})"
            for w in model.meta["event_windows"]))
    mkt_w = market_weights(panel, model.assets)
    betas = model_implied_betas(model, mkt_w)
    as_of_ts = pd.Timestamp(md.as_of)
    signals = compute_signals(panel, md, model, as_of_ts, model.assets)
    alpha = build_alpha(signals, model, cfg, sector=panel.assets["sector"])
    availability = short_availability(panel, md, cfg)
    sides = issuer_side_lines(panel, availability)
    squeeze = squeeze_table(panel, md, availability, cfg)
    daily_vol = panel.returns.loc[:as_of_ts].tail(63).std()
    nav = float(nav if nav is not None else cfg.fund.inception_nav_usd)
    cost_model = build_cost_model(sides, panel.assets, daily_vol, cfg, nav)
    current_w = current_weights_from_book(current_entry, nav, current_drifted_w)
    inception = current_entry is None and not current_drifted_w
    if inception:
        notes.append("Inception: carteira montada a partir do caixa.")
    return WeekContext(
        week=week, cfg=cfg, md=md, snapshot_id=md.manifest.snapshot_id,
        snapshot_hash=md.manifest.content_hash(), panel=panel, model=model, market_w=mkt_w,
        betas=betas, signals_raw=signals, alpha=alpha, availability=availability, sides=sides,
        squeeze=squeeze, cost_model=cost_model, daily_vol=daily_vol, nav=nav,
        current_w=current_w, current_positions=list(current_entry.positions) if current_entry
        else None, inception=inception, themes=themes if themes is not None else load_themes(),
        drawdown=drawdown, notes=notes,
    )


# ---------------------------------------------------------------- risco e proposta

def theme_exposures(w: pd.Series, themes: dict[str, list[str]]) -> dict[str, float]:
    return {t: float(w.reindex(members).fillna(0.0).sum()) for t, members in themes.items()}


def country_gap_stress(w: pd.Series, assets: pd.DataFrame, cfg: FundConfig) -> dict[str, float]:
    """Gap simultâneo de todos os emissores de um país (cenários calibrados em eventos reais)."""
    out: dict[str, float] = {}
    country = assets["country"].reindex(w.index)
    for c, gaps in cfg.risk.country_gap_scenarios.items():
        exposure = float(w[country == c].sum())
        for g in gaps:
            out[f"Gap {c} {g:+.0%}"] = exposure * float(g)
    return out


def _exposure_lines(w: pd.Series, assets: pd.DataFrame, model: RiskModel, cfg: FundConfig,
                    themes: dict[str, list[str]]) -> list[ExposureLine]:
    lines: list[ExposureLine] = []
    for group, col, limit in (("country", "country", cfg.risk.country_net_max_abs),
                              ("sector", "sector", cfg.risk.sector_net_max_abs)):
        keys = assets[col].reindex(w.index)
        for k in sorted(keys.dropna().unique()):
            ww = w[keys == k]
            lines.append(ExposureLine(group=group, name=str(k), long=float(ww[ww > 0].sum()),
                                      short=float(ww[ww < 0].sum()), net=float(ww.sum()),
                                      gross=float(ww.abs().sum()), limit=limit))
    x = model.factor_exposure(w)
    for s in STYLE_FACTORS:
        if s in x.index:
            lines.append(ExposureLine(group="style", name=s, long=0.0, short=0.0,
                                      net=float(x[s]), gross=abs(float(x[s])),
                                      limit=cfg.risk.style_exposure_max_abs))
    for t, members in themes.items():
        ww = w.reindex(members).dropna()
        lines.append(ExposureLine(group="market", name=f"tema:{t}", long=float(ww[ww > 0].sum()),
                                  short=float(ww[ww < 0].sum()), net=float(ww.sum()),
                                  gross=float(ww.abs().sum()),
                                  limit=cfg.risk.theme_net_max_abs.get(t)))
    return lines


def risk_summary(ctx: WeekContext, w: pd.Series) -> RiskSummary:
    cfg, model = ctx.cfg, ctx.model
    w = w[w != 0]
    dec = risk_decomposition(w, model)
    var1, es1 = parametric_var_es(w, model, cfg.risk.var_confidence, 1)
    try:
        hvar1, hes1 = historical_var_es(w, ctx.panel, model, cfg.risk.var_confidence, 1)
    except Exception:  # noqa: BLE001 - VaR histórico é complementar; o paramétrico prevalece
        hvar1, hes1 = float("nan"), float("nan")
    var5, _ = parametric_var_es(w, model, cfg.risk.var_confidence, 5)
    adtv = ctx.panel.assets["adtv_usd"]
    prof = liquidity_profile(w, adtv, ctx.nav, cfg.liquidity.participation_rate)
    summ = liquidity_summary(prof)
    pct_1d = float(summ.loc[1.0, "gross"]) if 1.0 in summ.index else float("nan")
    stress = {k: float(v) for k, v in stress_tests(w, ctx.panel, model, ctx.market_w).items()}
    stress.update(country_gap_stress(w, ctx.panel.assets, cfg))
    by_factor = dec.by_factor.sort_values(key=lambda s: -s.abs())
    top_assets = dec.asset_contrib.sort_values(key=lambda s: -s.abs()).head(10)
    beta = float(ctx.betas.reindex(w.index).fillna(0.0) @ w)
    return RiskSummary(
        ex_ante_vol=dec.total_vol, factor_vol=dec.factor_vol, specific_vol=dec.specific_vol,
        factor_risk_share=dec.factor_share, beta=beta, gross=float(w.abs().sum()),
        net=float(w.sum()), long_exposure=float(w[w > 0].sum()),
        short_exposure=float(w[w < 0].sum()), n_long=int((w > 0).sum()),
        n_short=int((w < 0).sum()),
        var_1d_99=float(np.nanmax([var1, hvar1])), es_1d_99=float(np.nanmax([es1, hes1])),
        var_1w_99=float(var5), effective_n=float(effective_n(w)),
        max_days_to_liquidate=float(prof["days_to_liquidate"].max()) if len(prof) else 0.0,
        pct_nav_liquidated_1d=pct_1d,
        exposures=_exposure_lines(w, ctx.panel.assets, model, cfg, ctx.themes),
        factor_contributions={str(k): float(v) for k, v in by_factor.head(15).items()},
        stress_tests=stress,
        top_risk_contributors={str(k): float(v) for k, v in top_assets.items()},
    )


def _effective_cfg_for_views(cfg: FundConfig) -> FundConfig:
    """IC das visões de IA conforme a fase de adoção (research.llm_phase)."""
    return cfg.with_overrides({"alpha": {"view_information_coefficient": cfg.research.llm_view_ic}})


def theme_checks(ctx: WeekContext, w: pd.Series) -> list:
    from ..contracts import ComplianceCheck  # local para manter o topo enxuto

    out = []
    exp = theme_exposures(w, ctx.themes)
    for t, limit in ctx.cfg.risk.theme_net_max_abs.items():
        if t not in exp:
            continue
        v = exp[t]
        out.append(ComplianceCheck(
            check_id=f"THEME_NET:{t}", name=f"Exposição líquida ao tema {t}",
            passed=abs(v) <= limit + 1e-6, severity=Severity.HARD, value=v, limit=limit,
            details=f"Líquido {v:.2%} no tema '{t}' (limite ±{limit:.2%})."))
    gaps = country_gap_stress(w, ctx.panel.assets, ctx.cfg)
    worst = min(gaps.values()) if gaps else 0.0
    lim = ctx.cfg.risk.country_stress_max_loss
    out.append(ComplianceCheck(
        check_id="COUNTRY_GAP_STRESS", name="Pior gap de país (cenários de evento)",
        passed=-worst <= lim + 1e-6, severity=Severity.SOFT, value=worst, limit=-lim,
        details="Pior cenário: " + (min(gaps, key=gaps.get) if gaps else "n/d")
                + f" com {worst:.2%} do NAV (limite −{lim:.2%})."))
    return out


@dataclass
class ProposalBuild:
    proposal: Proposal
    result: OptimizationResult
    constraints: pd.DataFrame
    alpha_used: pd.Series
    view_log: list[str]


def build_proposal(ctx: WeekContext, *, views: list[View], overrides: dict | None,
                   research_hash: str, version: int, label: str,
                   pack: ResearchPack | None = None, created_at: datetime | None = None,
                   extra_notes: list[str] | None = None) -> ProposalBuild:
    cfg = ctx.cfg
    overrides = dict(overrides or {})
    cfg_v = _effective_cfg_for_views(cfg)
    spec_vol = ctx.model.specific_vol
    alpha_adj, vcons, vlog = apply_views(ctx.alpha.alpha, views, spec_vol, cfg_v)
    issuers = list(ctx.model.assets)
    current = ctx.current_w.reindex(issuers).fillna(0.0) if len(ctx.current_w) else None
    constraints = build_asset_constraints(
        issuers, ctx.sides, ctx.squeeze, vcons, ctx.betas, ctx.panel.assets, cfg, ctx.nav,
        current=current, inception=ctx.inception)
    constraints = apply_liquidity_minimums(constraints, cfg, ctx.nav)
    result = optimize(alpha_adj, ctx.model, constraints, ctx.cost_model, cfg, ctx.nav,
                      current=current, inception=ctx.inception, market_w=ctx.market_w,
                      overrides=overrides)
    w = result.weights[result.weights.abs() > 0]
    checks = run_compliance(w, ctx.model, constraints, ctx.squeeze, ctx.panel.assets, cfg,
                            ctx.nav, current, ctx.inception, ctx.as_of, ctx.week, ctx.market_w,
                            ctx.is_synthetic, drawdown=ctx.drawdown)
    checks = list(checks) + theme_checks(ctx, w)
    summary = risk_summary(ctx, w)
    fx_last = fx_for_lines(ctx.md).ffill().iloc[-1]
    view_scores = pd.Series({v.issuer_id: v.score for v in views if v.score != 0}, dtype=float)
    positions = build_positions(
        w, ctx.sides, ctx.panel.lines, ctx.panel.assets, ctx.squeeze, alpha_adj,
        ctx.alpha.composite_z, view_scores, None, ctx.betas, ctx.nav, fx_last,
        participation=cfg.liquidity.participation_rate)
    dec_contrib = risk_decomposition(w, ctx.model).asset_contrib if len(w) else pd.Series()
    positions = [p.model_copy(update={"risk_contribution": float(dec_contrib.get(p.issuer_id))})
                 if p.issuer_id in dec_contrib.index else p for p in positions]
    cost_by_issuer = estimate_rebalance_costs(w.reindex(issuers).fillna(0.0), current,
                                              ctx.cost_model)
    traded = (w.reindex(issuers).fillna(0.0) - (current if current is not None else 0.0)).abs()
    cost_bps = (cost_by_issuer / traded.replace(0, np.nan) * 1e4).dropna()
    trades = build_trades(positions, ctx.current_positions, ctx.nav, cost_bps=cost_bps,
                          participation=cfg.liquidity.participation_rate,
                          line_adtv=ctx.panel.lines["adtv_usd"])
    hedges = fx_hedges(positions, ctx.nav)
    diag = result.diagnostics
    notes = list(diag.notes) + list(ctx.notes) + list(extra_notes or []) + [f"[visões] {x}" for x in vlog]
    diag = OptimizerDiagnostics(**{**diag.model_dump(), "notes": notes})
    week_id = ctx.week.isoformat()
    proposal = Proposal(
        proposal_id=f"CDP-{week_id}-{label}", week=ctx.week, version=version,
        created_at=created_at or datetime.now(UTC), created_by=SYSTEM_CREATOR, nav_usd=ctx.nav,
        snapshot_id=ctx.snapshot_id, snapshot_hash=ctx.snapshot_hash,
        config_hash=cfg.config_hash(), research_hash=research_hash,
        overrides={"label": label, **overrides}, positions=positions, trades=trades,
        fx_hedges=hedges, risk=summary, compliance=checks, optimizer=diag,
        is_synthetic=ctx.is_synthetic,
        data_notice=SIMULATED_DATA_NOTICE + " — mercado sintético" if ctx.is_synthetic
        else "Dados reais (Yahoo Finance, B3, FINRA, BCB); paper trading com execução hipotética.",
    )
    memo = render_memo(proposal, pack, None, config=cfg)
    proposal = proposal.model_copy(update={"memo_markdown": memo})
    return ProposalBuild(proposal=proposal, result=result, constraints=constraints,
                         alpha_used=alpha_adj, view_log=vlog)


def apply_liquidity_minimums(constraints: pd.DataFrame, cfg: FundConfig,
                             nav: float) -> pd.DataFrame:
    """ADTV mínimo por lado (long/short) e participação reduzida para shorts (docs/research/04).

    Só aperta limites: nunca aumenta ``max_long``/``max_short``. ADTV ausente bloqueia o lado.
    """
    c = constraints.copy()
    liq = cfg.liquidity
    if "adtv_long_usd" in c.columns:
        adtv_l = pd.to_numeric(c["adtv_long_usd"], errors="coerce")
        low_long = ~(adtv_l >= liq.min_adtv_long_usd)
        c.loc[low_long, "max_long"] = 0.0
        c.loc[low_long, "can_long"] = False
    if "adtv_short_usd" in c.columns:
        adtv_s = pd.to_numeric(c["adtv_short_usd"], errors="coerce")
        low_short = ~(adtv_s >= liq.min_adtv_short_usd)
        c.loc[low_short, "max_short"] = 0.0
        c.loc[low_short, "can_short"] = False
        cap = (liq.short_participation_rate * adtv_s * liq.max_days_to_liquidate_short / nav)
        c["max_short"] = np.minimum(c["max_short"].astype(float), cap.fillna(0.0))
    return c


def proposal_ok(p: Proposal) -> bool:
    return not p.hard_failures


def hold_weights(ctx: WeekContext) -> pd.Series:
    return ctx.current_w.copy()


def proposal_fingerprint(p: Proposal) -> dict:
    return {"proposal_hash": p.proposal_hash(), "n_long": p.risk.n_long, "n_short": p.risk.n_short,
            "vol": p.risk.ex_ante_vol, "hard": [c.check_id for c in p.hard_failures]}


def risk_gate_hash(p: Proposal) -> str:
    return sha256_obj([c.model_dump(mode="json") for c in p.compliance])
