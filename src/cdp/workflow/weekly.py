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

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from .. import SIMULATED_DATA_NOTICE
from ..alpha.combine import AlphaResult, build_alpha, reresidualize
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
    ComplianceCheck,
    ExposureLine,
    OptimizerDiagnostics,
    Proposal,
    ResearchPack,
    RiskSummary,
    Severity,
    View,
)
from ..hashing import sha256_obj
from ..market import MarketData
from ..portfolio.compliance import passive_checks, run_compliance
from ..portfolio.costs import CostModel, build_cost_model, estimate_rebalance_costs
from ..portfolio.optimizer import (
    OptimizationError,
    OptimizationResult,
    build_asset_constraints,
    metodologia_ativa,
    model_implied_betas,
    optimize,
    portfolio_risk_parts,
    sig,
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
from .memo import fmt_pct, render_memo

SYSTEM_CREATOR = "CDP — motor quantitativo"
# O modo de meta de vol vem do mandato (risk.risk_target_mode); mantido vazio por compatibilidade.
MATCH: dict = {}
THEMES_PATH = "data/universe/themes.csv"
#: Kill switch: risco (vol ex-ante com κ_F) e gross da nova carteira ≤ esta fração da atual.
KILL_SWITCH_RISK_MULT = 0.5


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
    commodity_betas: pd.DataFrame = field(default_factory=pd.DataFrame)
    event_exposures: dict = field(default_factory=dict)
    drawdown: float | None = None
    notes: list[str] = field(default_factory=list)
    # --- construção com limites operacionais (vazios/None no mandato legado) ---
    model_base: RiskModel | None = None          # modelo sem janelas de evento (gate "base")
    kappa_f: float = 1.0                         # inflação de 2ª ordem do bloco fatorial
    kappa_info: dict = field(default_factory=dict)
    current_entry: BookEntry | None = None
    squeeze_stops: dict[str, str] = field(default_factory=dict)   # emissor -> motivo
    entry_blocks: pd.DataFrame | None = None     # vetos de short novo (risk.limites)
    commodity_imputed: dict[str, list[str]] = field(default_factory=dict)
    #: Janela, capacidades e emissores congelados do pregão de execução (calculados uma vez
    #: por semana em :func:`_execution`; ``None`` = ainda não consultado).
    execucao_cache: dict | None = field(default=None, repr=False)

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


def commodity_betas(panel: AssetPanel, md: MarketData, cfg: FundConfig, issuers: list[str],
                    window: int = 252, min_obs: int = 126) -> pd.DataFrame:
    """β de cada emissor a cada commodity (controlando pelo mercado LatAm), dados <= ``as_of``.

    Regressão diária r_i = a + b_m·r_mkt + b_c·r_commodity nos últimos ``window`` pregões.
    Sem histórico suficiente ⇒ ``NaN`` (registrado; o otimizador não presume sensibilidade).
    """
    from ..risk.exposures import market_return_series

    proxies = cfg.risk.commodity_proxies or {}
    if not proxies:
        return pd.DataFrame(index=issuers)
    end = pd.Timestamp(panel.as_of)
    rets = panel.returns.loc[:end, issuers].tail(window)
    mkt = market_return_series(panel, issuers).reindex(rets.index)
    out = {}
    for name, sym in proxies.items():
        if sym not in md.benchmarks.columns:
            continue
        px = md.benchmarks[sym].loc[:end].dropna()
        rc = px.pct_change(fill_method=None).reindex(rets.index)
        betas = {}
        for i in issuers:
            df = pd.DataFrame({"y": rets[i], "m": mkt, "c": rc}).dropna()
            if len(df) < min_obs:
                betas[i] = np.nan
                continue
            X = np.column_stack([np.ones(len(df)), df["m"].to_numpy(), df["c"].to_numpy()])
            coef, *_ = np.linalg.lstsq(X, df["y"].to_numpy(), rcond=None)
            betas[i] = float(coef[2])
        out[name] = pd.Series(betas)
    return pd.DataFrame(out).reindex(issuers)


def impute_commodity_betas(betas: pd.DataFrame, sector: pd.Series
                           ) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """β de commodity ausente ⇒ mediana do setor (prior), senão mediana geral — usado na
    restrição e na checagem (nunca contribuição zero em silêncio). Devolve os imputados."""
    if betas.empty:
        return betas, {}
    out = betas.copy()
    imputed: dict[str, list[str]] = {}
    sec = sector.reindex(out.index)
    for c in out.columns:
        col = pd.to_numeric(out[c], errors="coerce")
        miss = col.isna()
        if not miss.any():
            continue
        med_sec = col.groupby(sec).median()
        overall = float(col.median()) if col.notna().any() else float("nan")
        fill = sec.map(med_sec).astype(float).where(lambda s: s.notna(), overall)
        out[c] = col.where(~miss, fill)
        imputed[c] = sorted(map(str, col.index[miss & fill.notna()]))
    return out, imputed


def event_reaction_exposures(panel: AssetPanel, cfg: FundConfig, betas: pd.Series,
                             market_w: pd.Series, on: date) -> dict[str, dict]:
    """Exposição a eventos binários medida pela reação residual no pregão de reação.

    Para cada janela de evento ativa com ``reaction_date`` disponível nos dados (inclusive a barra
    intradiária provisória do momento da análise), e_i = r_i − β_i·r_mkt nesse pregão para os
    emissores do país do evento (demais = 0). Devolve ``{nome: {exposures, limit, date}}``.
    """
    from ..risk.event_scaling import active_event_windows

    out: dict[str, dict] = {}
    for w in active_event_windows(cfg, on):
        rd = w.get("reaction_date")
        lim = w.get("reaction_exposure_max_abs")
        if not rd or lim is None:
            continue
        ts = pd.Timestamp(date.fromisoformat(str(rd)))
        if ts not in panel.returns.index:
            continue
        r = panel.returns.loc[ts]
        mw = market_w.reindex(r.index).fillna(0.0)
        valid = r.notna() & (mw > 0)
        if not valid.any():
            continue
        r_mkt = float((r[valid] * mw[valid]).sum() / mw[valid].sum())
        b = betas.reindex(r.index)
        members = panel.assets["country"].reindex(r.index) == w["country"]
        e = (r - b * r_mkt).where(members & r.notna() & b.notna())
        out[f"evento:{w['country']}:{rd}"] = {
            "exposures": e.dropna().to_dict(), "limit": float(lim), "date": str(rd),
            "name": w.get("name", ""), "market_return": r_mkt}
    return out


def prepare_week(md: MarketData, cfg: FundConfig, week: date, *, nav: float | None = None,
                 current_entry: BookEntry | None = None,
                 current_drifted_w: dict[str, float] | None = None,
                 drawdown: float | None = None, themes: dict[str, list[str]] | None = None,
                 squeeze_stops: Mapping[str, str] | None = None,
                 ) -> WeekContext:
    """Monta o contexto quantitativo da semana com dados até ``md.as_of`` (pregão anterior).

    ``squeeze_stops``: shorts em stop de squeeze (``risk.limites.stops_de_squeeze``), aplicados
    por nome quando ``squeeze.stop_scope = "name"``."""
    provisional = week in md.manifest.provisional_dates
    if md.as_of > week or (md.as_of == week and not provisional):
        raise ValueError(f"Snapshot {md.as_of} inválido para a decisão de {week}: a decisão usa "
                         "dados até o momento da análise (pregão anterior + barra provisória do dia).")
    notes: list[str] = []
    panel = build_asset_panel(md, cfg)
    issuers = panel.eligible
    model_base = estimate_risk_model(panel, cfg, md, as_of=md.as_of, issuers=issuers)
    if cfg.risk_model.macro_factors:
        from ..risk.macro import augment_with_macro

        model_base = augment_with_macro(model_base, md, cfg, panel)
        mac = model_base.meta.get("macro", {})
        if mac.get("ativo"):
            notes.append(f"Bloco macro no modelo de risco: {', '.join(mac['fatores'])} "
                         f"({len(mac.get('imputados', []))} emissores com beta pela média do "
                         "setor).")
    model = apply_event_windows(model_base, panel.assets["country"], cfg, week)
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
    if cfg.execution is not None:
        # adr_if_eligible_else_freeze: emissor cuja linha comprada não negocia no fechamento do
        # dia de montagem (mercado local fechado) passa à ADR elegível ANTES do custo, da
        # capacidade, do congelamento e das posições (docs/cdp/EXECUCAO.md §6).
        from ..portfolio.execucao import janela_execucao, rotear_linhas

        sides = rotear_linhas(sides, panel.lines, janela_execucao(week, cfg), cfg,
                              current_entry)
    squeeze = squeeze_table(panel, md, availability, cfg)
    daily_vol = panel.returns.loc[:as_of_ts].tail(63).std()
    nav = float(nav if nav is not None else cfg.fund.inception_nav_usd)
    cost_model = build_cost_model(sides, panel.assets, daily_vol, cfg, nav)
    current_w = current_weights_from_book(current_entry, nav, current_drifted_w)
    inception = current_entry is None and not current_drifted_w
    if inception:
        notes.append("Inception: carteira montada a partir do caixa.")
    cbetas = commodity_betas(panel, md, cfg, list(model.assets))
    imputed: dict[str, list[str]] = {}
    extended = metodologia_ativa(cfg)
    if extended and cfg.risk.operational is not None and not cbetas.empty:
        cbetas, imputed = impute_commodity_betas(cbetas, panel.assets["sector"])
        n_imp = sum(len(v) for v in imputed.values())
        if n_imp:
            notes.append(f"Sensibilidade a commodities sem histórico suficiente imputada pela "
                         f"mediana do setor em {n_imp} pares emissor × commodity.")
    kappa, kinfo = 1.0, {}
    if extended:
        from ..risk.idio import kappa_f

        kappa, kinfo = kappa_f(model_base, cfg)
    blocks = None
    if cfg.squeeze.enforce_entry_blocks:
        from ..risk.limites import earnings_calendar, free_float_table, short_entry_blocks

        ids = list(model.assets)
        earn = earnings_calendar(ids, week, md.as_of, squeeze, md)
        ff = free_float_table(ids, md, md.as_of)
        blocks = short_entry_blocks(ids, week=week, earnings=earn, free_float=ff,
                                    market_cap_usd=panel.assets["market_cap_usd"], cfg=cfg)
    return WeekContext(
        week=week, cfg=cfg, md=md, snapshot_id=md.manifest.snapshot_id,
        snapshot_hash=md.manifest.content_hash(), panel=panel, model=model, market_w=mkt_w,
        betas=betas, signals_raw=signals, alpha=alpha, availability=availability, sides=sides,
        squeeze=squeeze, cost_model=cost_model, daily_vol=daily_vol, nav=nav,
        current_w=current_w, current_positions=list(current_entry.positions) if current_entry
        else None, inception=inception, themes=themes if themes is not None else load_themes(),
        drawdown=drawdown, notes=notes,
        commodity_betas=cbetas,
        event_exposures=event_reaction_exposures(panel, cfg, betas, mkt_w, week),
        model_base=model_base, kappa_f=kappa, kappa_info=kinfo, current_entry=current_entry,
        squeeze_stops=dict(squeeze_stops or {}), entry_blocks=blocks, commodity_imputed=imputed,
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


def _commodity_lines(w: pd.Series, betas: pd.DataFrame, cfg: FundConfig) -> list[ExposureLine]:
    out: list[ExposureLine] = []
    for c in betas.columns:
        b = betas[c].reindex(w.index)
        known = b.notna()
        net = float((w[known] * b[known]).sum())
        out.append(ExposureLine(group="market", name=f"commodity:{c}", long=0.0, short=0.0,
                                net=net, gross=abs(net), limit=cfg.risk.commodity_beta_max_abs))
    return out


def _portfolio_beta(ctx: WeekContext, w: pd.Series) -> float:
    """β previsto com a mesma imputação da compliance: implícito do modelo, senão 1,0 (nunca 0)."""
    b = ctx.betas.reindex(w.index)
    return float(b.fillna(1.0) @ w)


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
    beta = _portfolio_beta(ctx, w)
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
        exposures=_exposure_lines(w, ctx.panel.assets, model, cfg, ctx.themes)
        + _commodity_lines(w, ctx.commodity_betas, cfg),
        factor_contributions={str(k): float(v) for k, v in by_factor.head(15).items()},
        stress_tests=stress,
        top_risk_contributors={str(k): float(v) for k, v in top_assets.items()},
    )


def _effective_cfg_for_views(cfg: FundConfig) -> FundConfig:
    """``apply_views`` já aplica min(teto, IC da fase) às visões de IA; nada a sobrescrever."""
    return cfg


def theme_checks(ctx: WeekContext, w: pd.Series) -> list:
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
    op = ctx.cfg.risk.operational
    for line in _commodity_lines(w, ctx.commodity_betas, ctx.cfg):
        lim = line.limit or 0.0
        name = line.name.split(':', 1)[1]
        extra = ""
        imp = ctx.commodity_imputed.get(name, [])
        if imp:
            nav_w = float(w.reindex(imp).abs().sum())
            extra = (f" β imputado pela mediana do setor em {len(imp)} emissores "
                     f"({nav_w:.2%} do NAV em posições).")
        out.append(ComplianceCheck(
            check_id=f"COMMODITY:{name}",
            name=f"Sensibilidade líquida a {line.name}", passed=abs(line.net) <= lim + 1e-6,
            severity=Severity.SOFT, value=line.net, limit=lim,
            details=f"Σ w·β = {line.net:+.4f} (limite ±{lim:.2f}); 10% na commodity ⇒ "
                    f"{line.net * 0.10:+.2%} do NAV.{extra}"))
        if op is not None:
            lim_op = min(op.commodity_beta, lim)
            out.append(ComplianceCheck(
                check_id=f"COMMODITY_OP:{name}",
                name=f"Sensibilidade líquida a {line.name} (operacional)",
                passed=abs(line.net) <= lim_op + 1e-6, severity=Severity.SOFT, value=line.net,
                limit=lim_op, details=f"Σ w·β = {line.net:+.4f} (limite operacional "
                                      f"±{lim_op:.3f})."))
    for name, spec in ctx.event_exposures.items():
        e = pd.Series(spec["exposures"], dtype=float).reindex(w.index)
        v = float((w[e.notna()] * e.dropna()).sum())
        out.append(ComplianceCheck(
            check_id=f"EVENT:{name}", name=f"Exposição ao choque de evento ({spec['name']})",
            passed=abs(v) <= spec["limit"] + 1e-6, severity=Severity.SOFT, value=v,
            limit=spec["limit"],
            details=f"Reação residual de {spec['date']} replicada na carteira: {v:+.3%} do NAV "
                    f"(limite ±{spec['limit']:.2%})."))
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


# ---------------------------------------------------------------- limites por emissor


def _execution(ctx: WeekContext) -> dict | None:
    """Janela de execução, capacidades do fechamento por lado e emissores congelados
    (``portfolio.execucao``, seção ``execution``), consultados uma vez por semana.

    ``None`` sem a seção ``execution``; ``{"disponivel": False, "motivo": ...}`` quando a
    capacidade não está disponível nesta versão (limites de liquidez anteriores valem)."""
    cfg = ctx.cfg
    if cfg.execution is None:
        return None
    if ctx.execucao_cache is None:
        from ..portfolio import execucao

        try:
            janela = execucao.janela_execucao(ctx.week, cfg)
            cap_l = execucao.capacidade_fechamento_usd(ctx.panel.lines, ctx.md, janela, cfg,
                                                       lado="long")
            cap_s = execucao.capacidade_fechamento_usd(ctx.panel.lines, ctx.md, janela, cfg,
                                                       lado="short")
            frozen = execucao.emissores_congelados(ctx.sides, ctx.current_entry, janela, cfg)
        except NotImplementedError:
            ctx.execucao_cache = {"disponivel": False,
                                  "motivo": "capacidade de fechamento indisponível nesta versão"}
        else:
            ctx.execucao_cache = {"disponivel": True, "janela": janela, "cap_long": cap_l,
                                  "cap_short": cap_s,
                                  "congelados": {str(k): str(v) or "sem_fechamento"
                                                 for k, v in sorted(frozen.items())}}
    return ctx.execucao_cache


def frozen_book(ctx: WeekContext) -> dict:
    """Parte da carteira atual em emissores congelados (sem fechamento negociável na janela):
    ``{"pesos", "vol", "gross"}`` — o piso de qualquer teto de risco ou de gross relativo, já
    que essas posições ficam como estão nesta decisão."""
    ex = _execution(ctx)
    out = {"pesos": pd.Series(dtype=float), "vol": 0.0, "gross": 0.0}
    if not ex or not ex.get("disponivel") or not len(ctx.current_w):
        return out
    w = ctx.current_w[ctx.current_w != 0]
    wf = w[w.index.isin(list(ex["congelados"]))]
    if wf.empty:
        return out
    try:
        vol = portfolio_risk_parts(wf, ctx.model).vol
    except (ValueError, KeyError):
        vol = 0.0
    return {"pesos": wf, "vol": float(vol), "gross": float(wf.abs().sum())}


def _capacity_caps(ctx: WeekContext, c: pd.DataFrame, ex: dict) -> pd.DataFrame:
    """Aumentos de cada perna ≤ capacidade do fechamento da linha usada (volume desconhecido ⇒
    0); reduções até zero continuam permitidas."""
    c = c.copy()
    nav = ctx.nav
    sides = ctx.sides.reindex(c.index)
    cur = pd.to_numeric(c["current"], errors="coerce").fillna(0.0)

    def cap_for(col: str, caps: pd.Series) -> pd.Series:
        t = sides[col] if col in sides.columns else pd.Series(np.nan, index=c.index)
        vals = [float(caps.get(x)) if isinstance(x, str) and x in caps.index
                and np.isfinite(caps.get(x)) else 0.0 for x in t]
        return pd.Series(vals, index=c.index, dtype=float)  # sem volume conhecido ⇒ 0

    cl = cap_for("long_ticker", ex["cap_long"]) / nav
    cs = cap_for("short_ticker", ex["cap_short"]) / nav
    c["cap_fechamento_long"] = cl
    c["cap_fechamento_short"] = cs
    c["max_long"] = np.minimum(c["max_long"].astype(float), cur.clip(lower=0.0) + cl)
    c["max_short"] = np.minimum(c["max_short"].astype(float), (-cur).clip(lower=0.0) + cs)
    liq = np.maximum(cl, cs)
    before = pd.to_numeric(c["max_trade_liq"], errors="coerce")
    c["max_trade_liq"] = liq
    if "origem_negociacao" in c.columns:
        c.loc[liq < before - ORIGIN_EPS, "origem_negociacao"] = "capacidade_fechamento"
    c["max_trade"] = np.maximum(liq, cur.abs())
    c["can_long"] = c["max_long"] > 0
    c["can_short"] = c["max_short"] > 0
    return c


def _freeze(c: pd.DataFrame, ex: dict, info: dict) -> pd.DataFrame:
    """Emissores sem linha negociável na janela ficam EXATAMENTE como estão (``w = w⁰``). Vem
    por último e prevalece sobre os demais limites por nome: um stop de squeeze num nome
    congelado fica pendente para o próximo rebalanceamento (registrado), nunca torna a decisão
    inteira inviável."""
    c = c.copy()
    cur = pd.to_numeric(c["current"], errors="coerce").fillna(0.0)
    c["congelado"] = ""
    stops = dict(info.get("stops_squeeze", {}))
    pend: dict[str, str] = {}
    for iid, motivo in ex["congelados"].items():
        if iid not in c.index:
            continue
        w0 = float(cur.get(iid, 0.0))
        c.at[iid, "max_long"] = max(w0, 0.0)
        c.at[iid, "max_short"] = max(-w0, 0.0)
        c.at[iid, "max_trade"] = 0.0
        c.at[iid, "max_trade_liq"] = 0.0
        c.at[iid, "congelado"] = motivo
        for col in ("origem_long", "origem_short", "origem_negociacao"):
            if col in c.columns:
                c.at[iid, col] = "congelado"
        if iid in stops:
            pend[iid] = stops.pop(iid)
    if pend:
        info["stops_squeeze"] = stops
        info["stops_squeeze_pendentes"] = pend
        c["stop_pendente"] = [pend.get(str(i), "") for i in c.index]
    c["can_long"] = c["max_long"] > 0
    c["can_short"] = c["max_short"] > 0
    return c


ORIGIN_EPS = 1e-12


def _initial_origins(c: pd.DataFrame, cfg: FundConfig) -> pd.DataFrame:
    """Origem de cada teto por emissor na tabela do mandato (``origem_long``/``origem_short``/
    ``origem_negociacao``): ``mandato``, ``liquidez``, ``visao``, ``squeeze`` ou
    ``elegibilidade`` (sem linha, inelegível, sem aluguel, aluguel, porte)."""
    from ..portfolio.optimizer import normalize_squeeze_bucket

    c = c.copy()
    rk = cfg.risk
    ml = pd.to_numeric(c["max_long"], errors="coerce").fillna(0.0)
    ms = pd.to_numeric(c["max_short"], errors="coerce").fillna(0.0)
    vmax = pd.to_numeric(c.get("view_max_abs", pd.Series(np.nan, index=c.index)),
                         errors="coerce")
    no_l = c.get("view_no_long", pd.Series(False, index=c.index)).fillna(False).astype(bool)
    no_s = c.get("view_no_short", pd.Series(False, index=c.index)).fillna(False).astype(bool)
    bucket = normalize_squeeze_bucket(c.get("squeeze_bucket", pd.Series("NA", index=c.index)))

    def near(a: pd.Series, b: pd.Series | float) -> pd.Series:
        return pd.Series(np.isclose(a, b, rtol=1e-9, atol=1e-15), index=a.index)

    long_tok = np.where(ml <= 0, np.where(no_l, "visao", "elegibilidade"),
                        np.where(vmax.notna() & near(ml, vmax.fillna(-1.0)), "visao",
                                 np.where(near(ml, rk.max_long_weight), "mandato",
                                          "liquidez")))
    squeezed = bucket.isin(["MEDIUM", "NA"]) & (cfg.squeeze.medium_short_cap_multiplier < 1)
    short_tok = np.where(
        ms <= 0, np.where(no_s, "visao", np.where(bucket == "HIGH", "squeeze", "elegibilidade")),
        np.where(squeezed, "squeeze",
                 np.where(vmax.notna() & near(ms, vmax.fillna(-1.0)), "visao",
                          np.where(near(ms, rk.max_short_weight), "mandato", "liquidez"))))
    c["origem_long"] = long_tok
    c["origem_short"] = short_tok
    c["origem_negociacao"] = "liquidez"
    return c


def _mark_origin(before: pd.DataFrame, after: pd.DataFrame, token: str) -> pd.DataFrame:
    """Marca ``token`` como origem dos tetos que a etapa apertou."""
    if "origem_long" not in after.columns:
        return after
    out = after.copy()
    for side in ("long", "short"):
        b = pd.to_numeric(before[f"max_{side}"], errors="coerce").reindex(out.index)
        a = pd.to_numeric(out[f"max_{side}"], errors="coerce")
        out.loc[(a < b - ORIGIN_EPS).to_numpy(dtype=bool), f"origem_{side}"] = token
    return out


def construction_constraints(ctx: WeekContext, view_cons: pd.DataFrame | None,
                             vol_target: float) -> tuple[pd.DataFrame, dict]:
    """Limites por emissor exatamente como na decisão (também usado pela tese para explicar o
    tamanho de cada posição): mandato e liquidez → ADTV mínimo → teto de risco específico →
    capacidade do fechamento → vetos de short novo → stop de squeeze por nome → emissores
    congelados (por último: ficam como estão e prevalecem sobre os demais limites).

    Com a metodologia ativa a tabela traz a origem de cada teto (``origem_long``,
    ``origem_short``, ``origem_negociacao``), publicada no dimensionamento por posição."""
    cfg = ctx.cfg
    extended = metodologia_ativa(cfg)
    issuers = list(ctx.model.assets)
    current = ctx.current_w.reindex(issuers).fillna(0.0) if len(ctx.current_w) else None
    c = build_asset_constraints(
        issuers, ctx.sides, ctx.squeeze, view_cons, ctx.betas, ctx.panel.assets, cfg, ctx.nav,
        current=current, inception=ctx.inception)
    if extended:
        c = _initial_origins(c, cfg)
    prev = c
    c = _mark_origin(prev, apply_liquidity_minimums(c, cfg, ctx.nav), "adtv_minimo")
    prev = c
    c = _mark_origin(prev, apply_specific_risk_caps(c, ctx.model.specific_vol, cfg, vol_target),
                     "risco_especifico")
    info: dict = {}
    ex = _execution(ctx)
    if ex is not None:
        if ex.get("disponivel"):
            prev = c
            c = _mark_origin(prev, _capacity_caps(ctx, c, ex), "capacidade_fechamento")
            janela = ex["janela"]
            info["capacidade"] = {
                "disponivel": True, "sessao": ctx.week.isoformat(),
                "multiplicador": sig(janela.multiplicador_capacidade),
                "fechamento_antecipado": bool(janela.fechamento_antecipado),
                "congelados": dict(ex["congelados"])}
        else:
            info["capacidade"] = {"disponivel": False, "motivo": ex.get("motivo")}
    if cfg.squeeze.enforce_entry_blocks and ctx.entry_blocks is not None:
        from ..risk.limites import apply_short_entry_blocks

        blk = ctx.entry_blocks.reindex(c.index)
        prev = c
        c, applied = apply_short_entry_blocks(c, blk)
        c = _mark_origin(prev, c, "veto_short")
        c["entry_block"] = (blk["catalyst_block"].fillna(False).astype(bool)
                            | blk["float_block"].fillna(False).astype(bool))
        c["entry_block_dado_ausente"] = blk["dado_ausente"].fillna("").astype(str)
        info["vetos_short"] = applied
        info["vetos_short_ausentes"] = int((c["entry_block_dado_ausente"] != "").sum())
    if cfg.squeeze.stop_scope == "name" and ctx.squeeze_stops:
        from ..risk.limites import apply_squeeze_name_stops

        prev = c
        c, applied = apply_squeeze_name_stops(c, ctx.squeeze_stops)
        c = _mark_origin(prev, c, "stop_squeeze")
        info["stops_squeeze"] = applied
    if ex is not None and ex.get("disponivel"):
        c = _freeze(c, ex, info)
    return c, info


def _neutrality_cost_bp(formulacao: dict) -> float | None:
    """Σ preço-sombra × limite (bp a.a.) das restrições de neutralidade QUE VINCULAM: quanto o
    objetivo ganharia, na margem, se esses limites afrouxassem proporcionalmente (as que não
    vinculam têm preço-sombra zero por complementaridade)."""
    rows = formulacao.get("restricoes") or []
    exact = ("net_exposure", "beta", "factor_risk")
    prefixes = ("country:", "op_country:", "sector:", "style:", "factor_risk:", "theme:")
    tot = 0.0
    seen = False
    for r in rows:
        k = str(r.get("chave", ""))
        if not (k in exact or k.startswith(prefixes)):
            continue
        seen = True
        v = r.get("custo_bp_1pct")
        if r.get("vinculante") and v is not None:
            tot += float(v) * 100.0
    return tot if seen else None


def _labels_pt(ctx: WeekContext, form: dict) -> dict:
    """Nomes públicos das restrições em pt-BR (países, setores, estilos, temas, commodities,
    reação a evento e grupos de controle pelos nomes dos emissores)."""
    from .tese_analise import (
        commodity_label,
        country_label,
        sector_label,
        style_label,
        theme_label,
    )

    rows = form.get("restricoes")
    if not rows:
        return form
    names = ctx.panel.assets.get("issuer_name", pd.Series(dtype=object))

    def item(raw: str) -> str:
        if raw.startswith("commodity:"):
            return f"Sensibilidade a {commodity_label(raw.split(':', 1)[1]).lower()}"
        if raw.startswith("evento:"):
            spec = ctx.event_exposures.get(raw, {})
            return f"Reação ao evento: {spec.get('name') or raw.split(':', 2)[-1]}"
        return f"Exposição ao tema: {theme_label(raw).lower()}"

    def group(g: str) -> str:
        members = ctx.cfg.risk_model.linked_groups.get(g, [])
        shown = [str(names.get(m)) if isinstance(names.get(m), str) and names.get(m) else m
                 for m in members]
        return " e ".join(shown) if shown else g

    out = []
    for r in rows:
        key = str(r.get("chave", ""))
        pre, _, raw = key.partition(":")
        nome = r.get("nome")
        if pre == "country":
            nome = f"Exposição líquida do país: {country_label(raw)}"
        elif pre == "op_country":
            nome = f"Exposição líquida do país: {country_label(raw)} (limite operacional)"
        elif pre == "country_share":
            nome = f"Fatia do gross no país: {country_label(raw)}"
        elif pre == "sector":
            nome = f"Exposição líquida do setor: {sector_label(raw)}"
        elif pre == "style":
            nome = f"Exposição ao estilo: {style_label(raw)}"
        elif pre == "theme":
            nome = item(raw)
        elif pre == "linked_long":
            nome = f"Grupo de controle ({group(raw)}): pernas compradas"
        elif pre == "linked_short":
            nome = f"Grupo de controle ({group(raw)}): pernas vendidas"
        out.append({**r, "nome": nome})
    return {**form, "restricoes": out}


def build_proposal(ctx: WeekContext, *, views: list[View], overrides: dict | None,
                   research_hash: str, version: int, label: str,
                   pack: ResearchPack | None = None, created_at: datetime | None = None,
                   extra_notes: list[str] | None = None,
                   drawdown_ref_vol: float | None = None,
                   risk_extra: dict | None = None) -> ProposalBuild:
    """``drawdown_ref_vol``: σ_ref da escada de drawdown por volatilidade (compliance);
    ``risk_extra``: campos adicionais do bloco ``overrides["risco"]`` (ex.: ``escada``)."""
    cfg = ctx.cfg
    overrides = dict(overrides or {})
    extended = metodologia_ativa(cfg)
    cfg_v = _effective_cfg_for_views(cfg)
    spec_vol = ctx.model.specific_vol
    alpha_adj, vcons, vlog = apply_views(ctx.alpha.alpha, views, spec_vol, cfg_v)
    if cfg.alpha.reresidualize_after_views and views:
        alpha_adj, rlog = reresidualize(alpha_adj, ctx.model)
        vlog = list(vlog) + rlog
    issuers = list(ctx.model.assets)
    current = ctx.current_w.reindex(issuers).fillna(0.0) if len(ctx.current_w) else None
    vol_target = float(overrides.get("vol_target", cfg.risk.vol_target_annual))
    constraints, cinfo = construction_constraints(ctx, vcons, vol_target)
    opt_overrides = dict(overrides)
    if ctx.themes:
        opt_overrides["themes"] = ctx.themes
    if not ctx.commodity_betas.empty:
        opt_overrides["exposure_limits"] = {
            f"commodity:{c}": {"exposures": ctx.commodity_betas[c].dropna().to_dict(),
                               "limit": cfg.risk.commodity_beta_max_abs}
            for c in ctx.commodity_betas.columns}
    if ctx.event_exposures:
        opt_overrides.setdefault("exposure_limits", {})
        for name, spec in ctx.event_exposures.items():
            opt_overrides["exposure_limits"][name] = {"exposures": spec["exposures"],
                                                      "limit": spec["limit"]}
    opt_kw: dict = {}
    if extended:
        opt_kw = {"model_base": ctx.model_base if "base" in cfg.risk.idio_gate_models else None,
                  "kappa_f": ctx.kappa_f}

    def solve(c: pd.DataFrame, prev: OptimizationResult | None = None) -> OptimizationResult:
        kw = dict(opt_kw)
        if prev is not None and prev.ccp_lin:
            kw["ccp_warm"] = prev.ccp_lin  # reparo parte da linearização anterior
        return optimize(alpha_adj, ctx.model, c, ctx.cost_model, cfg, ctx.nav, current=current,
                        inception=ctx.inception, market_w=ctx.market_w,
                        overrides=opt_overrides, **kw)

    result = solve(constraints)
    constraints, result, repair_log = _repair_single_name_risk(ctx, constraints, result, solve)
    w = result.weights[result.weights.abs() > 0]
    comp_kw: dict = {}
    if extended:
        # Só redução: kill switch ou degraus de redução da escada (nenhuma posição abre/aumenta).
        reduce_only = bool(overrides.get("reduce_only", False)) or any(
            str(r).startswith("degross") for r in result.relaxations)
        comp_kw = {"model_base": ctx.model_base, "kappa_f": ctx.kappa_f,
                   "drawdown_ref_vol": drawdown_ref_vol, "reduce_only": reduce_only}
    checks = run_compliance(w, ctx.model, constraints, ctx.squeeze, ctx.panel.assets, cfg,
                            ctx.nav, current, ctx.inception, ctx.as_of, ctx.week, ctx.market_w,
                            ctx.is_synthetic, drawdown=ctx.drawdown, **comp_kw)
    checks = list(checks) + theme_checks(ctx, w)
    summary = risk_summary(ctx, w)
    fx_last = fx_for_lines(ctx.md).ffill().iloc[-1]
    view_scores = pd.Series({v.issuer_id: v.score for v in views if v.score != 0}, dtype=float)
    ex_cap = _execution(ctx)
    ex_cap = ex_cap if ex_cap and ex_cap.get("disponivel") else None
    positions = build_positions(
        w, ctx.sides, ctx.panel.lines, ctx.panel.assets, ctx.squeeze, alpha_adj,
        ctx.alpha.composite_z, view_scores, None, ctx.betas, ctx.nav, fx_last,
        participation=cfg.liquidity.participation_rate,
        short_participation=cfg.liquidity.short_participation_rate,
        capacidade_fechamento=ex_cap["cap_long"] if ex_cap else None)
    dec_contrib = risk_decomposition(w, ctx.model).asset_contrib if len(w) else pd.Series()
    positions = [p.model_copy(update={"risk_contribution": float(dec_contrib.get(p.issuer_id))})
                 if p.issuer_id in dec_contrib.index else p for p in positions]
    cost_by_issuer = estimate_rebalance_costs(w.reindex(issuers).fillna(0.0), current,
                                              ctx.cost_model)
    traded = (w.reindex(issuers).fillna(0.0) - (current if current is not None else 0.0)).abs()
    cost_bps = (cost_by_issuer / traded.replace(0, np.nan) * 1e4).dropna()
    trades = build_trades(positions, ctx.current_positions, ctx.nav, cost_bps=cost_bps,
                          participation=cfg.liquidity.participation_rate,
                          line_adtv=ctx.panel.lines["adtv_usd"],
                          capacidade_long=ex_cap["cap_long"] if ex_cap else None,
                          capacidade_short=ex_cap["cap_short"] if ex_cap else None,
                          congelados=set(ex_cap["congelados"]) if ex_cap else None)
    hedges = fx_hedges(positions, ctx.nav)
    diag = result.diagnostics
    notes = (list(diag.notes) + list(ctx.notes) + list(extra_notes or [])
             + [f"[visões] {x}" for x in vlog] + [f"[risco por nome] {x}" for x in repair_log])
    diag = OptimizerDiagnostics(**{**diag.model_dump(), "notes": notes})
    week_id = ctx.week.isoformat()
    recorded: dict = {"label": label, **overrides}
    if extended:
        recorded.update(_open_model_overrides(ctx, w, result, cinfo, risk_extra))
    proposal = Proposal(
        proposal_id=f"CDP-{week_id}-{label}", week=ctx.week, version=version,
        created_at=created_at or datetime.now(UTC), created_by=SYSTEM_CREATOR, nav_usd=ctx.nav,
        snapshot_id=ctx.snapshot_id, snapshot_hash=ctx.snapshot_hash,
        config_hash=cfg.config_hash(), research_hash=research_hash,
        overrides=recorded, positions=positions, trades=trades,
        fx_hedges=hedges, risk=summary, compliance=checks, optimizer=diag,
        is_synthetic=ctx.is_synthetic,
        data_notice=SIMULATED_DATA_NOTICE + " — mercado sintético" if ctx.is_synthetic
        else "Dados reais (Yahoo Finance, B3, FINRA, BCB); paper trading com execução hipotética.",
    )
    memo = render_memo(proposal, pack, None, config=cfg)
    proposal = proposal.model_copy(update={"memo_markdown": memo})
    return ProposalBuild(proposal=proposal, result=result, constraints=constraints,
                         alpha_used=alpha_adj, view_log=vlog)


def _open_model_overrides(ctx: WeekContext, w: pd.Series, result: OptimizationResult,
                          cinfo: dict, risk_extra: dict | None) -> dict:
    """Blocos públicos da construção (``risco``, ``formulacao``, ``construcao``): números do
    código como floats puros com 6 algarismos significativos."""
    from ..risk.idio import parametros_modelo, risco_da_decisao

    cfg = ctx.cfg
    form = dict(result.formulacao or {})
    risco = risco_da_decisao(
        w, ctx.model, ctx.model_base, cfg, kappa=ctx.kappa_f, kappa_info=ctx.kappa_info,
        binding=list(result.diagnostics.binding_constraints),
        custo_neutralidade_bp=_neutrality_cost_bp(form))
    if risk_extra:
        risco.update(risk_extra)
    form = _labels_pt(ctx, form)
    form["modelo_risco"] = parametros_modelo(ctx.model, cfg)
    contrib = {}
    if len(w):
        dec = risk_decomposition(w, ctx.model).asset_contrib
        contrib = {str(k): sig(v) for k, v in dec.sort_values(key=lambda s: -s.abs()).items()}
    construcao = {
        "contribuicao_risco_por_nome": contrib,
        "vetos_short": dict(cinfo.get("vetos_short", {})),
        "vetos_short_dados_ausentes": cinfo.get("vetos_short_ausentes"),
        "stops_squeeze": dict(cinfo.get("stops_squeeze", {})),
        "stops_squeeze_pendentes": dict(cinfo.get("stops_squeeze_pendentes", {})),
        "capacidade_fechamento": cinfo.get("capacidade"),
        "commodities_beta_imputado": {k: len(v) for k, v in ctx.commodity_imputed.items()},
    }
    return {"risco": risco, "formulacao": form, "construcao": construcao}


SINGLE_NAME_REPAIR_ITERS = 3
SINGLE_NAME_REPAIR_MARGIN = 0.97


def _repair_single_name_risk(ctx: WeekContext, constraints: pd.DataFrame,
                             result: OptimizationResult, solve
                             ) -> tuple[pd.DataFrame, OptimizationResult, list[str]]:
    """Reotimiza enquanto algum nome passar da participação máxima na variância (Euler).

    O teto convexo de risco específico não enxerga a covariância fatorial do nome; aqui, para cada
    nome acima do limite, o teto do lado é reduzido para |w|·√(limite/participação)·margem e a
    carteira é reotimizada (no máximo ``SINGLE_NAME_REPAIR_ITERS`` vezes). Só aperta limites.
    """
    limit = float(ctx.cfg.risk.max_single_name_risk_share)
    log: list[str] = []
    c = constraints
    frozen = set()
    if "congelado" in c.columns:
        frozen = {str(i) for i, v in c["congelado"].items() if isinstance(v, str) and v}
    deferred: set[str] = set()
    for it in range(1, SINGLE_NAME_REPAIR_ITERS + 1):
        w = result.weights[result.weights.abs() > 0]
        if w.empty:
            break
        share = risk_decomposition(w, ctx.model).asset_contrib.dropna()
        over = share[share > limit]
        # Nome congelado fica como está nesta decisão: o corte espera o próximo fechamento.
        for iid in sorted(set(over.index) & frozen - deferred):
            deferred.add(iid)
            log.append(f"{iid} com {fmt_pct(float(over[iid]))} da variância, sem fechamento "
                       "negociável nesta decisão: redução adiada para o próximo rebalanceamento")
        over = over[~over.index.isin(list(frozen))]
        if over.empty:
            break
        c = c.copy()
        for iid, sh in over.sort_values(ascending=False).items():
            col = "max_long" if w[iid] > 0 else "max_short"
            cap = abs(float(w[iid])) * float(np.sqrt(limit / sh)) * SINGLE_NAME_REPAIR_MARGIN
            c.loc[iid, col] = min(float(c.loc[iid, col]), cap)
            if f"origem_{col[4:]}" in c.columns:
                c.loc[iid, f"origem_{col[4:]}"] = "risco_por_nome"
            log.append(f"passo {it}: {iid} com {sh:.2%} da variância (limite {limit:.2%}); "
                       f"teto {col} reduzido para {cap:.2%}")
        result = solve(c, result)
    return c, result, log


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


def apply_specific_risk_caps(constraints: pd.DataFrame, specific_vol: pd.Series,
                             cfg: FundConfig, vol_target: float) -> pd.DataFrame:
    """|w_i|·σ_esp,i ≤ √(participação máx. de risco por nome)·σ_alvo (forma convexa; só aperta)."""
    c = constraints.copy()
    sv = specific_vol.reindex(c.index)
    cap = (np.sqrt(cfg.risk.max_single_name_risk_share) * vol_target / sv).fillna(0.0)
    c["max_long"] = np.minimum(c["max_long"].astype(float), cap)
    c["max_short"] = np.minimum(c["max_short"].astype(float), cap)
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


# ---------------------------------------------------------------- decisão autônoma

@dataclass
class PMDecisionBundle:
    """Saída já validada e convertida do agente PM (visões PM, overrides e diário)."""

    views: list[View]
    overrides: dict
    journal: object | None
    pm_output_hash: str
    posture: str = "neutra"
    posture_vol_target: float | None = None
    abstain: bool = False
    rationale: str = ""
    conviction: int | None = None


@dataclass
class WeeklyOutcome:
    final: Proposal
    shadow_quant: Proposal
    decision: object
    path_taken: str
    attempts: list[dict]
    research_hash: str


def tighten_only(views: list[View]) -> list[View]:
    """Mantém só as restrições (no_short/no_long/teto), sem inclinação de alpha."""
    out = []
    for v in views:
        if v.no_short or v.no_long or v.max_abs_weight is not None:
            out.append(v.model_copy(update={"score": 0, "confidence": 0.0}))
    return out


def _hold_checks(ctx: WeekContext, w: pd.Series) -> list[ComplianceCheck]:
    """Checagens da carteira MANTIDA como INFO ``PASSIVO:`` (nunca bloqueiam a decisão de
    manter; nunca derrubam o último recurso)."""
    try:
        issuers = list(ctx.model.assets)
        current = ctx.current_w.reindex(issuers).fillna(0.0) if len(ctx.current_w) else None
        cons = build_asset_constraints(issuers, ctx.sides, ctx.squeeze, None, ctx.betas,
                                       ctx.panel.assets, ctx.cfg, ctx.nav, current=current,
                                       inception=ctx.inception)
        checks = run_compliance(w, ctx.model, cons, ctx.squeeze, ctx.panel.assets, ctx.cfg,
                                ctx.nav, current, ctx.inception, ctx.as_of, ctx.week,
                                ctx.market_w, ctx.is_synthetic, drawdown=ctx.drawdown,
                                model_base=ctx.model_base, kappa_f=ctx.kappa_f)
        checks = list(checks) + theme_checks(ctx, w)
        passive = passive_checks(checks)
    except Exception as exc:  # noqa: BLE001 - o último recurso nunca falha por diagnóstico
        return [ComplianceCheck(
            check_id="PASSIVO:INDISPONIVEL", name="Checagens da carteira mantida",
            passed=False, severity=Severity.INFO, value=None, limit=None,
            details=f"Checagens da carteira mantida não calculadas: {type(exc).__name__}.")]
    if not passive:
        return [ComplianceCheck(
            check_id="PASSIVO:OK", name="Checagens da carteira mantida", passed=True,
            severity=Severity.INFO, value=0.0, limit=None,
            details="A carteira mantida respeita todos os limites do mandato.")]
    return passive


def hold_proposal(ctx: WeekContext, research_hash: str, version: int,
                  reason: str, created_at: datetime | None = None,
                  label: str = "manter") -> Proposal:
    """Mantém a carteira atual (ou caixa na inception) quando nenhuma alternativa passa nos gates.

    Com a metodologia ativa, as violações passivas da carteira mantida ficam registradas como
    checagens INFO ``PASSIVO:`` (visíveis, sem bloquear)."""
    w = ctx.current_w[ctx.current_w != 0]
    if w.empty:
        summary = RiskSummary(
            ex_ante_vol=0.0, factor_vol=0.0, specific_vol=0.0, factor_risk_share=0.0, beta=0.0,
            gross=0.0, net=0.0, long_exposure=0.0, short_exposure=0.0, n_long=0, n_short=0,
            var_1d_99=0.0, es_1d_99=0.0, var_1w_99=0.0, effective_n=0.0,
            max_days_to_liquidate=0.0, pct_nav_liquidated_1d=1.0)
        checks = []
    else:
        summary = risk_summary(ctx, w)
        checks = _hold_checks(ctx, w) if metodologia_ativa(ctx.cfg) else []
    diag = OptimizerDiagnostics(status="hold", solver="none", solve_seconds=0.0,
                                notes=[reason] + list(ctx.notes))
    p = Proposal(
        proposal_id=f"CDP-{ctx.week.isoformat()}-{label}", week=ctx.week, version=version,
        created_at=created_at or datetime.now(UTC), created_by=SYSTEM_CREATOR, nav_usd=ctx.nav,
        snapshot_id=ctx.snapshot_id, snapshot_hash=ctx.snapshot_hash,
        config_hash=ctx.cfg.config_hash(), research_hash=research_hash,
        overrides={"label": label}, positions=[], trades=[], fx_hedges=[], risk=summary,
        compliance=checks, optimizer=diag, is_synthetic=ctx.is_synthetic,
        data_notice=SIMULATED_DATA_NOTICE if ctx.is_synthetic else "Dados reais.")
    return p.model_copy(update={"memo_markdown": render_memo(p, None, None, config=ctx.cfg)})


def current_book_vol(ctx: WeekContext) -> float | None:
    """Vol ex-ante da carteira atual no modelo de decisão (a mesma medida da restrição de vol do
    otimizador); ``None`` sem posições ou se o risco não é calculável (nome fora do modelo)."""
    w = ctx.current_w[ctx.current_w != 0]
    if w.empty:
        return None
    try:
        parts = portfolio_risk_parts(w, ctx.model)
    except (ValueError, KeyError):
        return None
    return parts.vol if parts.total_var > 0 else None


#: Chaves que o kill switch acrescenta às do gestor (retiradas na resolução de referência da
#: escada de drawdown, que é a mesma tentativa no estágio normal).
KILL_SWITCH_KEYS = ("reduce_only", "risk_target_mode", "vol_cap", "gross_max",
                    "gross_multiplier")
#: Folga relativa sobre o risco/gross das posições congeladas (que ficam como estão): o
#: conjunto viável precisa de interior para o solver.
FROZEN_MARGIN = 0.01
STAGE_PT = {"soft_stop": "stop suave", "hard_stop": "stop duro", "stop_out": "stop-out",
            "normal": "normal", "desconhecido": "drawdown desconhecido"}


def kill_switch_overrides(ctx: WeekContext, pm_ov: dict) -> tuple[dict, str]:
    """Overrides do caminho ``reduzir-risco`` (kill switch).

    Metodologia ativa: só redução por nome, vol ex-ante ≤ 0,5 × a da carteira atual, gross
    ≤ 0,5 × o atual, meta de vol como teto (sem busca de κ) e giro pelo mandato. Posições sem
    fechamento negociável na janela (congeladas) ficam como estão: os tetos nunca ficam abaixo
    do risco e do gross dessa parte (a redução recai sobre o que pode ser negociado).
    Legado: gross do mandato × 0,5 (o giro segue o mandato fora da inception)."""
    if not metodologia_ativa(ctx.cfg):
        ov = {k: v for k, v in pm_ov.items() if k != "max_weekly_turnover"}
        ov["gross_multiplier"] = 0.5
        return ov, "KILL_SWITCH ativo: apenas redução de risco."
    ov = {k: v for k, v in pm_ov.items()
          if k not in ("max_weekly_turnover", "gross_multiplier", "gross_max")}
    ov["reduce_only"] = True
    ov["risk_target_mode"] = "cap"
    fb = frozen_book(ctx)
    vol = current_book_vol(ctx)
    if vol is not None:
        ov["vol_cap"] = sig(max(KILL_SWITCH_RISK_MULT * vol, fb["vol"] * (1 + FROZEN_MARGIN)))
    gross0 = float(ctx.current_w.abs().sum())
    if gross0 > 0:
        ov["gross_max"] = sig(min(max(KILL_SWITCH_RISK_MULT * gross0,
                                      fb["gross"] * (1 + FROZEN_MARGIN)), ctx.cfg.risk.gross_max))
    why = ("KILL_SWITCH ativo: só redução de posições, risco e gross até metade da carteira "
           "atual.")
    if fb["gross"] > 0:
        why += (f" {len(fb['pesos'])} posições sem fechamento negociável ficam como estão "
                f"({fmt_pct(fb['gross'])} do NAV em gross); a redução recai sobre as demais.")
    return ov, why


def attempt_specs(ctx: WeekContext, pack: ResearchPack, pm: PMDecisionBundle, *,
                  vt_default: float, pm_ov: dict, kill_switch: bool
                  ) -> list[tuple[str, list[View], dict, str]]:
    """Tentativas em ordem de preferência ``(rótulo, visões, overrides, motivo)``."""
    ai_views = list(pack.views)
    specs: list[tuple[str, list[View], dict, str]] = []
    if kill_switch:
        ov, why = kill_switch_overrides(ctx, pm_ov)
        specs.append(("reduzir-risco", tighten_only(ai_views + pm.views), ov, why))
        return specs
    if not pm.abstain:
        specs.append(("cdp", ai_views + pm.views, pm_ov,
                      "Carteira do CDP: pesquisa de IA + decisão do agente PM."))
    specs.append(("cdp-restricoes", tighten_only(ai_views + pm.views), pm_ov,
                  "Fallback 1: apenas restrições da IA/PM (sem inclinações)."))
    specs.append(("quant", [], {"vol_target": vt_default, **MATCH},
                  "Fallback 2: carteira só-quant."))
    return specs


def _error_code(exc: OptimizationError) -> str:
    """Código determinístico + primeira linha da mensagem (sem tempos de solver)."""
    first = str(exc).splitlines()[0] if str(exc) else ""
    return f"{getattr(exc, 'codigo', 'OTIMIZACAO')}: {first[:200]}"


def _ladder(ctx: WeekContext) -> tuple[str, float] | None:
    """Estágio e multiplicador da escada de drawdown por vol (``None`` se inativa/normal)."""
    if ctx.cfg.drawdown.risk_reference != "normal_book_vol":
        return None
    from ..risk.drawdown import stage, stage_multiplier

    stg = stage(ctx.drawdown, ctx.cfg)
    m = stage_multiplier(stg, ctx.cfg)
    return (stg, m) if m < 1.0 else None


def reference_overrides(ov: dict, label: str) -> dict:
    """Overrides da resolução de referência da escada (a MESMA tentativa no estágio normal):
    sem teto de risco e, no kill switch, sem as chaves de redução que ele acrescenta — σ_ref é
    o livro normal, nunca o livro já reduzido (os cortes não se multiplicam)."""
    drop = KILL_SWITCH_KEYS if label == "reduzir-risco" else ("vol_cap",)
    return {k: v for k, v in ov.items() if k not in drop}


def ladder_overrides(ctx: WeekContext, ov: dict, stage_name: str, sigma_ref: float | None,
                     fonte: str) -> tuple[dict, dict, str]:
    """Overrides com o teto de vol da escada: ``min(m·σ_ref, teto do kill switch)``, nunca
    abaixo do risco das posições congeladas. Registra a regra que vincula. σ_ref ausente,
    nulo ou não finito ⇒ sem teto da escada (o teto do kill switch, se houver, continua)."""
    from ..risk.drawdown import stage_multiplier, vol_cap

    m = stage_multiplier(stage_name, ctx.cfg)
    ref = sigma_ref if sigma_ref is not None and np.isfinite(sigma_ref) else None
    cap = vol_cap(stage_name, ref, ctx.cfg)
    prev = ov.get("vol_cap")
    candidates: list[tuple[float, str]] = []
    if cap is not None:
        candidates.append((float(cap), "escada de drawdown"))
    if prev is not None:
        candidates.append((float(prev), "kill switch"))
    escada = {"estagio": stage_name, "multiplicador": sig(m), "sigma_ref": sig(ref),
              "fonte_sigma_ref": fonte, "sigma_teto": None, "regra_vinculante": None}
    if not candidates:
        return dict(ov), {"escada": escada}, (
            f"Escada de drawdown ({STAGE_PT.get(stage_name, stage_name)}): vol de referência "
            "indisponível; sem teto adicional de vol.")
    eff, regra = min(candidates)
    floor = frozen_book(ctx)["vol"] * (1 + FROZEN_MARGIN)
    if eff < floor:
        eff, regra = floor, "posições sem fechamento negociável"
    eff = float(sig(eff))
    escada.update({"sigma_teto": eff, "regra_vinculante": regra})
    if ref is None:
        detail = f" ({regra})"
    elif regra == "escada de drawdown":
        detail = f" = {fmt_pct(m, 0)} × {fmt_pct(ref)} ({fonte})"
    else:
        detail = f" ({regra}; escada: {fmt_pct(m, 0)} × {fmt_pct(ref)}, {fonte})"
    note = (f"Escada de drawdown ({STAGE_PT.get(stage_name, stage_name)}): vol ex-ante limitada "
            f"a {fmt_pct(eff)}{detail}.")
    return {**ov, "vol_cap": eff}, {"escada": escada}, note


def _build_attempt(ctx: WeekContext, *, views: list[View], ov: dict, label: str,
                   research_hash: str, version: int, pack: ResearchPack | None,
                   why: str, created_at: datetime | None) -> ProposalBuild:
    """Uma tentativa, com a escada de drawdown por vol quando ativa: a mesma tentativa é
    resolvida no estágio normal (σ_ref, sem as chaves de redução do kill switch) e a decisão
    usa ``vol_cap = min(m·σ_ref, teto do kill switch)``. σ_ref: livro normal resolvido; sem
    ele (inviável ou vazio), a vol da carteira atual; sem carteira, a meta de vol da semana."""
    ladder = _ladder(ctx)
    if ladder is None:
        return build_proposal(ctx, views=views, overrides=ov, research_hash=research_hash,
                              version=version, label=label, pack=pack, extra_notes=[why],
                              created_at=created_at)
    stg, _m = ladder
    sigma_ref: float | None = None
    fonte = ""
    try:
        ref_build = build_proposal(ctx, views=views, overrides=reference_overrides(ov, label),
                                   research_hash=research_hash, version=version, label=label,
                                   pack=None, created_at=created_at)
        v = float(ref_build.proposal.risk.ex_ante_vol)
        if np.isfinite(v) and v > 0:
            sigma_ref, fonte = v, "mesma tentativa no estágio normal"
    except OptimizationError:
        pass
    if sigma_ref is None:
        v0 = current_book_vol(ctx)
        if v0 is not None and np.isfinite(v0) and v0 > 0:
            sigma_ref, fonte = float(v0), "carteira atual"
    if sigma_ref is None:
        sigma_ref = float(ov.get("vol_target", ctx.cfg.risk.vol_target_annual))
        fonte = "meta de vol da semana"
    ov2, escada, note = ladder_overrides(ctx, ov, stg, sigma_ref, fonte)
    return build_proposal(ctx, views=views, overrides=ov2, research_hash=research_hash,
                          version=version, label=label, pack=pack, extra_notes=[why, note],
                          created_at=created_at, drawdown_ref_vol=sigma_ref, risk_extra=escada)


def run_weekly_decision(ctx: WeekContext, pack: ResearchPack, pm: PMDecisionBundle, *,
                        version: int, live_weeks: int = 0, kill_switch: bool = False,
                        audit_head_hash: str | None = None,
                        decided_at: datetime | None = None,
                        created_at: datetime | None = None) -> WeeklyOutcome:
    """Gera sombra só-quant e a carteira do CDP; aplica fallback por gates e decide sozinho.

    Uma tentativa inviável (``OptimizationError``) passa para a próxima e, se nenhuma passar nos
    gates HARD, a carteira é mantida (caixa na inception) — a decisão nunca é interrompida.
    ``created_at``/``decided_at``: relógio da rotina (padrão: agora, UTC).
    """
    from ..hashing import combine_hashes
    from .autonomy import effective_vol_target, make_autonomous_decision

    research_hash = combine_hashes(pack.research_hash(), pm.pm_output_hash)
    vt_default = effective_vol_target(ctx.cfg, None, live_weeks)
    vt_pm = effective_vol_target(ctx.cfg, pm.posture_vol_target, live_weeks)
    pm_ov = {**MATCH, **pm.overrides,
             "vol_target": min(vt_pm, float(pm.overrides.get("vol_target", vt_pm)))}
    try:
        shadow = build_proposal(ctx, views=[], overrides={"vol_target": vt_default, **MATCH},
                                research_hash=research_hash, version=version,
                                label="sombra-quant", pack=pack, created_at=created_at).proposal
    except OptimizationError as exc:
        shadow = hold_proposal(ctx, research_hash, version,
                               f"Carteira-sombra só-quant não resolvida ({_error_code(exc)}); "
                               "mantida a carteira atual como referência.",
                               created_at=created_at, label="sombra-quant")
    attempts: list[dict] = []
    final: Proposal | None = None
    path = ""
    for label, views, ov, why in attempt_specs(ctx, pack, pm, vt_default=vt_default,
                                               pm_ov=pm_ov, kill_switch=kill_switch):
        try:
            b = _build_attempt(ctx, views=views, ov=ov, label=label,
                               research_hash=research_hash, version=version, pack=pack,
                               why=why, created_at=created_at)
        except OptimizationError as exc:
            attempts.append({"label": label, "why": why, "erro": _error_code(exc),
                             "hard": ["OPTIMIZATION_FAILED"],
                             "relaxations": list(exc.relaxations)})
            continue
        attempts.append({"label": label, "why": why, **proposal_fingerprint(b.proposal)})
        if proposal_ok(b.proposal):
            final, path = b.proposal, label
            break
    if final is None:
        final = hold_proposal(ctx, research_hash, version,
                              "Fallback 3: nenhuma alternativa passou nos gates HARD; mantida a "
                              "carteira anterior (ou caixa na inception).", created_at=created_at)
        path = "manter"
    rationale = (pm.rationale or "Decisão autônoma do CDP.") + f" Caminho: {path}."
    decision = make_autonomous_decision(
        final, research_hash=research_hash, pm_decision_hash=pm.pm_output_hash,
        rationale=rationale, journal=pm.journal, conviction=pm.conviction,
        decided_at=decided_at, audit_head_hash=audit_head_hash)
    return WeeklyOutcome(final=final, shadow_quant=shadow, decision=decision, path_taken=path,
                         attempts=attempts, research_hash=research_hash)
