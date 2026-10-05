"""Testes do módulo de carteira: custos, otimizador, compliance, ordens e hedge (DADOS SIMULADOS).

O modelo de risco é construído diretamente (B/F/D sintéticos) sobre o painel simulado, para
não depender do módulo de risco; tamanhos pequenos (60 emissores) mantêm o tempo baixo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import cvxpy as cp
import numpy as np
import pandas as pd
import pytest

from latam_ls.analytics.panel import AssetPanel, build_asset_panel
from latam_ls.config import FundConfig
from latam_ls.contracts import (
    BookedPosition,
    LineType,
    PositionTarget,
    Severity,
    Side,
    TradeAction,
)
from latam_ls.data.synthetic import make_synthetic_market
from latam_ls.market import MarketData
from latam_ls.portfolio.compliance import hard_failures, run_compliance
from latam_ls.portfolio.costs import (
    CostModel,
    adtv_tier,
    build_cost_model,
    cost_bps_of_traded,
    cost_expr,
    estimate_costs,
    estimate_rebalance_costs,
)
from latam_ls.portfolio.optimizer import (
    OptimizationError,
    OptimizationResult,
    build_asset_constraints,
    model_implied_betas,
    optimize,
    portfolio_risk_parts,
)
from latam_ls.portfolio.trades import (
    build_positions,
    build_trades,
    fx_hedges,
    lot_size,
    round_to_lot,
)
from latam_ls.risk.types import STYLE_FACTORS, RiskModel, country_factor, sector_factor

NAV = 100_000_000.0
AS_OF = date(2026, 10, 2)
WEEK = date(2026, 10, 5)
TOL = 1e-6


# ==========================================================
# Fixtures
# ==========================================================

@dataclass
class Env:
    cfg: FundConfig
    md: MarketData
    panel: AssetPanel
    sides: pd.DataFrame
    squeeze: pd.DataFrame
    views: pd.DataFrame
    model: RiskModel
    betas: pd.Series
    market_w: pd.Series
    daily_vol: pd.Series
    cost_model: CostModel
    alpha: pd.Series
    special: dict[str, str]


def _make_sides(panel: AssetPanel) -> pd.DataFrame:
    """Linha long = maior ADTV; short = linha alugável (ADR/US ou local B3) de maior ADTV."""
    rows = {}
    for iid, g in panel.lines.groupby("issuer_id"):
        g = g.assign(_adr=(g["line_type"] != "LOCAL").astype(int))
        g = g.sort_values(["adtv_usd", "_adr"], ascending=[False, False])
        lg = g.iloc[0]
        row = dict(long_ticker=lg.name, long_line_type=lg["line_type"],
                   long_currency=lg["currency"], adtv_long_usd=lg["adtv_usd"])
        sh = g[(g["line_type"] != "LOCAL") | (g["market"] == "BR")]
        if len(sh):
            s = sh.iloc[0]
            row.update(short_ticker=s.name, short_line_type=s["line_type"],
                       short_currency=s["currency"], adtv_short_usd=s["adtv_usd"],
                       can_short=True, borrow_fee_annual=0.006, fee_source="SIMULADO")
        else:
            row.update(short_ticker=np.nan, short_line_type=np.nan, short_currency=np.nan,
                       adtv_short_usd=np.nan, can_short=False, borrow_fee_annual=np.nan,
                       fee_source="")
        rows[iid] = row
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("issuer_id")


def _make_model(assets: pd.DataFrame, seed: int = 3) -> RiskModel:
    rng = np.random.default_rng(seed)
    ids = list(assets.index)
    countries = sorted(assets["country"].unique())
    sectors = sorted(assets["sector"].unique())
    cols = (["market"] + [country_factor(c) for c in countries]
            + [sector_factor(s) for s in sectors] + STYLE_FACTORS)
    B = pd.DataFrame(0.0, index=ids, columns=cols)
    B["market"] = 1.0
    for i in ids:
        B.loc[i, country_factor(assets.loc[i, "country"])] = 1.0
        B.loc[i, sector_factor(assets.loc[i, "sector"])] = 1.0
    for s in STYLE_FACTORS:
        B[s] = rng.normal(0.0, 1.0, len(ids))
    var = {"market": 0.20 ** 2}
    var.update({country_factor(c): 0.12 ** 2 for c in countries})
    var.update({sector_factor(s): 0.07 ** 2 for s in sectors})
    var.update({s: 0.04 ** 2 for s in STYLE_FACTORS})
    sd = np.sqrt([var[c] for c in cols])
    corr = np.full((len(cols), len(cols)), 0.1) + 0.9 * np.eye(len(cols))
    F = pd.DataFrame(corr * np.outer(sd, sd), index=cols, columns=cols)
    D = pd.Series(rng.uniform(0.28, 0.45, len(ids)) ** 2, index=ids)
    groups = {c: "market" if c == "market" else c.split(":")[0] if ":" in c else "style"
              for c in cols}
    return RiskModel(as_of=AS_OF, exposures=B, factor_cov=F, specific_var=D,
                     factor_returns=pd.DataFrame(), specific_returns=pd.DataFrame(),
                     factor_groups=groups)


@pytest.fixture(scope="module")
def env() -> Env:
    cfg = FundConfig()
    md = make_synthetic_market(seed=11, start=date(2024, 1, 2))
    panel = build_asset_panel(md, cfg)
    assets = panel.assets
    sides = _make_sides(panel)
    model = _make_model(assets)
    market_w = assets["market_cap_usd"]
    betas = model_implied_betas(model, market_w)
    cov = model.cov_matrix()
    daily_vol = pd.Series(np.sqrt(np.diag(cov)) / np.sqrt(252), index=cov.index)

    eligible = [i for i in assets.index if assets.loc[i, "eligible"]]
    shortable = [i for i in eligible if bool(sides.loc[i, "can_short"])
                 and sides.loc[i, "adtv_short_usd"] > 20e6]
    rng = np.random.default_rng(5)
    alpha = pd.Series(rng.normal(0.0, 0.15, len(assets)), index=assets.index)
    special = {
        "high": shortable[0], "medium": shortable[1], "no_short": shortable[2],
        "fee": shortable[3], "na": shortable[4],
        "no_long": [i for i in eligible if i not in shortable][0],
        "cap": [i for i in eligible if i not in shortable][1],
    }
    for key in ("high", "no_short", "fee", "medium", "na"):
        alpha[special[key]] = -0.8  # o otimizador "quer" vender a descoberto
    alpha[special["no_long"]] = 0.8
    alpha[special["cap"]] = 0.8
    sides.loc[special["fee"], "borrow_fee_annual"] = 0.12

    squeeze = pd.DataFrame({"squeeze_score": 20.0, "bucket": "LOW"}, index=assets.index)
    squeeze.loc[special["high"], ["squeeze_score", "bucket"]] = [85.0, "HIGH"]
    squeeze.loc[special["medium"], ["squeeze_score", "bucket"]] = [50.0, "MEDIUM"]
    squeeze = squeeze.drop(index=special["na"])  # sem dado ⇒ NA (tratado como MEDIUM)

    views = pd.DataFrame({"no_short": False, "no_long": False, "max_abs_weight": np.nan},
                         index=assets.index)
    views.loc[special["no_short"], "no_short"] = True
    views.loc[special["no_long"], "no_long"] = True
    views.loc[special["cap"], "max_abs_weight"] = 0.01

    cm = build_cost_model(sides, assets, daily_vol, cfg, NAV)
    return Env(cfg, md, panel, sides, squeeze, views, model, betas, market_w, daily_vol, cm,
               alpha, special)


def _constraints(env: Env, cfg: FundConfig | None = None, current: pd.Series | None = None,
                 inception: bool = True) -> pd.DataFrame:
    return build_asset_constraints(
        list(env.panel.assets.index), env.sides, env.squeeze, env.views, env.betas,
        env.panel.assets, cfg or env.cfg, NAV, current, inception)


@pytest.fixture(scope="module")
def inception(env: Env) -> tuple[OptimizationResult, pd.DataFrame]:
    cons = _constraints(env)
    res = optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                   env.market_w)
    return res, cons


def _assert_feasible(res: OptimizationResult, cons: pd.DataFrame, env: Env, cfg: FundConfig,
                     current: pd.Series | None = None, vol_target: float | None = None,
                     check_turnover: bool = False) -> None:
    w = res.weights
    rk = cfg.risk
    assert abs(w.sum()) <= rk.net_exposure_max_abs + TOL
    assert abs(float((cons["beta"] * w).sum())) <= rk.beta_max_abs + TOL
    vt = vol_target if vol_target is not None else rk.vol_target_annual
    assert env.model.portfolio_vol(w) <= vt + TOL
    assert res.ex_ante_vol == pytest.approx(env.model.portfolio_vol(w), abs=1e-9)
    assert w.abs().sum() <= rk.gross_max + TOL
    assert (w <= cons["max_long"] + TOL).all()
    assert (-w <= cons["max_short"] + TOL).all()
    for grp, lim in (("country", rk.country_net_max_abs), ("sector", rk.sector_net_max_abs)):
        assert w.groupby(cons[grp]).sum().abs().max() <= lim + TOL
    x = env.model.factor_exposure(w)
    assert x[STYLE_FACTORS].abs().max() <= rk.style_exposure_max_abs + TOL
    w0 = (current if current is not None else pd.Series(dtype=float)).reindex(w.index)
    dw = (w - w0.fillna(0.0)).abs()
    assert (dw <= cons["max_trade"] + TOL).all()
    if check_turnover:
        assert dw.sum() <= cfg.liquidity.max_weekly_turnover + TOL
    # liquidez por linha
    liq = cfg.liquidity
    longs, shorts = w[w > 0], w[w < 0]
    days_l = longs * NAV / (liq.participation_rate * cons.loc[longs.index, "adtv_long_usd"])
    days_s = -shorts * NAV / (liq.short_participation_rate
                              * cons.loc[shorts.index, "adtv_short_usd"])
    assert (days_l <= liq.max_days_to_liquidate_long + 1e-4).all()
    assert (days_s <= liq.max_days_to_liquidate_short + 1e-4).all()


# ==========================================================
# Custos
# ==========================================================

def test_adtv_tier_boundaries() -> None:
    s = pd.Series([60e6, 50e6, 20e6, 5e6, 1e6, np.nan])
    assert adtv_tier(s, [50e6, 15e6, 5e6]).tolist() == ["T1", "T1", "T2", "T3", "T4", "T4"]


def test_cost_model_components_by_market_and_currency(env: Env) -> None:
    cm, cfg = env.cost_model, env.cfg
    comp = cm.components
    for iid in cm.index[:20]:
        ticker = env.sides.loc[iid, "long_ticker"]
        adtv = env.sides.loc[iid, "adtv_long_usd"]
        tier = adtv_tier(pd.Series([adtv]), cfg.costs.tier_adtv_breaks_usd).iloc[0]
        market = "BR" if ticker.endswith(".SA") else ("US" if "." not in ticker else None)
        if market is None:
            continue
        ccy_bps = 0.0 if env.sides.loc[iid, "long_currency"] == "USD" else cfg.costs.fx_cost_bps
        expected = (cfg.costs.half_spread_bps_by_tier[tier] + cfg.costs.commission_bps[market]
                    + ccy_bps) / 1e4
        assert cm.linear_rate_long[iid] == pytest.approx(expected)
        k = cfg.costs.impact_coefficient * env.daily_vol[iid] * np.sqrt(NAV / adtv)
        assert cm.impact_k_long[iid] == pytest.approx(k)
        assert comp.loc[iid, ("long", "market")] == market
    # curva combinada é o pior caso entre as linhas utilizáveis
    assert (cm.linear_rate >= cm.linear_rate_long - 1e-15).all()
    assert (cm.impact_k >= cm.impact_k_long - 1e-15).all()


def test_cost_expr_matches_numeric_estimate(env: Env) -> None:
    cm = env.cost_model
    rng = np.random.default_rng(0)
    t = pd.Series(rng.normal(0, 0.01, len(cm.index)), index=cm.index)
    var = cp.Variable(len(cm.index))
    var.value = t.to_numpy()
    expr = cost_expr(var, cm)
    assert expr.is_convex()
    assert float(expr.value) == pytest.approx(float(estimate_costs(t, cm).sum()), rel=1e-9)
    # custo fracionário = linear·|t| + k·|t|^1.5
    i = cm.index[0]
    assert estimate_costs(t, cm)[i] == pytest.approx(
        cm.linear_rate[i] * abs(t[i]) + cm.impact_k[i] * abs(t[i]) ** 1.5)


def test_cost_bps_and_rebalance_legs(env: Env) -> None:
    cm = env.cost_model
    ids = list(cm.index[:3])
    t = pd.Series([0.01, 0.0, -0.02], index=ids)
    costs = estimate_costs(t, cm)
    bps = cost_bps_of_traded(t, costs)
    assert np.isnan(bps[ids[1]])
    assert bps[ids[0]] == pytest.approx(costs[ids[0]] / 0.01 * 1e4)
    # cruzar o zero: zera a perna comprada e abre a vendida, cada uma com sua curva
    w0 = pd.Series([0.02], index=[ids[0]])
    w1 = pd.Series([-0.01], index=[ids[0]])
    reb = estimate_rebalance_costs(w1, w0, cm)
    exp = (estimate_costs(pd.Series([0.02], index=[ids[0]]), cm, "long")
           + estimate_costs(pd.Series([0.01], index=[ids[0]]), cm, "short"))
    assert reb[ids[0]] == pytest.approx(exp[ids[0]])
    with pytest.raises(ValueError):
        estimate_rebalance_costs(pd.Series([np.nan], index=[ids[0]]), None, cm)


def test_cost_model_missing_data_is_flagged_not_zero(env: Env) -> None:
    sides = env.sides.copy()
    iid = sides.index[0]
    sides.loc[iid, "adtv_long_usd"] = np.nan
    vol = env.daily_vol.copy()
    vol[iid] = np.nan
    cm = build_cost_model(sides, env.panel.assets, vol, env.cfg, NAV)
    comp = cm.components
    assert "adtv_emissor" in comp.loc[iid, ("long", "flags")]
    assert bool(comp.loc[iid, ("issuer", "daily_vol_imputed")])
    assert comp.loc[iid, ("issuer", "daily_vol")] == pytest.approx(env.daily_vol.drop(iid)
                                                                   .quantile(0.9))
    assert cm.impact_k[iid] > 0 and np.isfinite(cm.impact_k[iid])
    with pytest.raises(KeyError):
        cm.reindex(["NAO_EXISTE"])


# ==========================================================
# Restrições por ativo
# ==========================================================

def test_asset_constraints_rules(env: Env) -> None:
    cons = _constraints(env)
    cfg, sp = env.cfg, env.special
    liq = cfg.liquidity
    # squeeze HIGH ⇒ sem short; MEDIUM/NA ⇒ teto × 0,5
    assert cons.loc[sp["high"], "max_short"] == 0.0
    assert "squeeze_alto" in cons.loc[sp["high"], "reasons"]
    for key in ("medium", "na"):
        iid = sp[key]
        base = min(cfg.risk.max_short_weight, liq.short_participation_rate
                   * env.sides.loc[iid, "adtv_short_usd"] * liq.max_days_to_liquidate_short / NAV)
        assert cons.loc[iid, "max_short"] == pytest.approx(base * 0.5)
    assert cons.loc[sp["na"], "squeeze_bucket"] == "NA"
    # visões só restringem
    assert cons.loc[sp["no_short"], "max_short"] == 0.0
    assert cons.loc[sp["no_long"], "max_long"] == 0.0
    assert cons.loc[sp["cap"], "max_long"] <= 0.01 + 1e-12
    # aluguel acima do limite ⇒ sem short
    assert cons.loc[sp["fee"], "max_short"] == 0.0
    assert "aluguel_acima_limite" in cons.loc[sp["fee"], "reasons"]
    # liquidez long: participação × ADTV × dias / NAV, limitado ao teto por nome
    expected = np.minimum(cfg.risk.max_long_weight, liq.participation_rate
                          * cons["adtv_long_usd"] * liq.max_days_to_liquidate_long / NAV)
    ok = cons["can_long"] & ~cons.index.isin([sp["cap"]])
    assert np.allclose(cons.loc[ok, "max_long"], expected[ok])
    # inelegível (preço defasado) não abre posição
    stale = env.panel.assets.index[~env.panel.assets["eligible"]]
    assert (cons.loc[stale, ["max_long", "max_short"]] == 0.0).all().all()
    # sem linha alugável ⇒ sem short
    no_line = env.sides.index[~env.sides["can_short"].astype(bool)]
    assert (cons.loc[no_line, "max_short"] == 0.0).all()


def test_max_trade_inception_vs_weekly_and_exit_floor(env: Env) -> None:
    liq = env.cfg.liquidity
    iid = env.special["cap"]  # sem short: ADTV de referência = linha long
    adtv = env.sides.loc[iid, "adtv_long_usd"]
    inc = _constraints(env, inception=True)
    wk = _constraints(env, inception=False)
    assert inc.loc[iid, "max_trade"] == pytest.approx(
        liq.participation_rate * adtv * liq.max_trade_days_inception / NAV)
    assert wk.loc[iid, "max_trade"] == pytest.approx(
        liq.participation_rate * adtv * liq.max_trade_days_weekly / NAV)
    # posição atual grande sempre pode ser zerada
    cur = pd.Series({iid: 0.9})
    wk2 = _constraints(env, current=cur, inception=False)
    assert wk2.loc[iid, "max_trade"] >= 0.9


def test_missing_beta_and_external_holdings(env: Env) -> None:
    betas = env.betas.drop(env.panel.assets.index[0])
    cons = build_asset_constraints(
        list(env.panel.assets.index[1:]), env.sides, env.squeeze, None, betas,
        env.panel.assets, env.cfg, NAV, pd.Series({env.panel.assets.index[0]: 0.01}), False)
    first = env.panel.assets.index[0]
    assert first in cons.index  # posição atual entra para poder sair
    assert cons.loc[first, "beta"] == 1.0
    assert "beta_imputado_1" in cons.loc[first, "flags"]


# ==========================================================
# Otimizador
# ==========================================================

def test_optimizer_satisfies_every_constraint(env: Env, inception) -> None:
    res, cons = inception
    _assert_feasible(res, cons, env, env.cfg)
    w = res.weights
    sp = env.special
    assert w[sp["high"]] >= -TOL          # squeeze HIGH ⇒ nenhum short
    assert w[sp["no_short"]] >= -TOL      # visão no_short respeitada
    assert w[sp["no_long"]] <= TOL        # visão no_long respeitada
    assert w[sp["fee"]] >= -TOL           # aluguel caro ⇒ sem short
    assert abs(w[sp["cap"]]) <= 0.01 + TOL
    assert -w[sp["medium"]] <= env.cfg.risk.max_short_weight * 0.5 + TOL
    assert res.diagnostics.status in ("optimal", "optimal_inaccurate")
    assert res.diagnostics.solver == "CLARABEL"
    assert res.diagnostics.n_candidates > 30
    assert res.diagnostics.n_excluded.get("squeeze_alto") == 1
    assert res.relaxations == []
    assert res.expected_alpha == pytest.approx(float((env.alpha * w).sum()))
    assert res.expected_cost > 0
    assert (w != 0).sum() >= 10


def test_vol_close_to_target_with_strong_alpha(env: Env, inception) -> None:
    res0, _ = inception
    assert res0.ex_ante_vol <= env.cfg.risk.vol_target_annual + TOL
    cons = _constraints(env)
    strong = env.alpha * 4.0
    res = optimize(strong, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                   env.market_w)
    assert res.ex_ante_vol == pytest.approx(env.cfg.risk.vol_target_annual, abs=1e-4)
    assert "vol_target" in res.diagnostics.binding_constraints
    _assert_feasible(res, cons, env, env.cfg)


def test_match_mode_reaches_target_with_weak_alpha(env: Env) -> None:
    cons = _constraints(env)
    weak = env.alpha * 0.1
    capped = optimize(weak, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                      env.market_w)
    assert capped.ex_ante_vol < 0.03          # custos dominam: abaixo da banda
    assert capped.alpha_scale == 1.0
    matched = optimize(weak, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                       env.market_w, overrides={"risk_target_mode": "match"})
    vt = env.cfg.risk.vol_target_annual
    assert vt * 0.99 <= matched.ex_ante_vol <= vt + TOL
    assert matched.alpha_scale > 1.0
    assert any("Modo 'match'" in n for n in matched.diagnostics.notes)
    assert matched.expected_alpha == pytest.approx(float((weak * matched.weights).sum()))
    _assert_feasible(matched, cons, env, env.cfg)
    with pytest.raises(ValueError, match="risk_target_mode"):
        optimize(weak, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                 overrides={"risk_target_mode": "auto"})


def test_vol_target_override_inside_band(env: Env) -> None:
    cons = _constraints(env)
    res = optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                   env.market_w, overrides={"vol_target": 0.03})
    assert res.ex_ante_vol <= 0.03 + TOL
    assert res.vol_target == 0.03
    with pytest.raises(ValueError, match="banda"):
        optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                 overrides={"vol_target": 0.08})
    with pytest.raises(ValueError, match="desconhecidos"):
        optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                 overrides={"alavancagem": 3})
    with pytest.raises(ValueError, match="apertar"):
        optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, None, True,
                 overrides={"gross_max": 3.0})


def test_two_pass_removes_tiny_positions(env: Env) -> None:
    rng = np.random.default_rng(42)
    alpha = pd.Series(rng.normal(0.0, 0.03, len(env.alpha)), index=env.alpha.index)
    cfg0 = env.cfg.with_overrides({"risk": {"min_position_weight": 0.0}})
    cons = _constraints(env, cfg0)
    one_pass = optimize(alpha, env.model, cons, env.cost_model, cfg0, NAV, None, True)
    w1 = one_pass.weights
    tiny_threshold = 0.004
    assert ((w1.abs() > 0) & (w1.abs() < tiny_threshold)).any(), "cenário precisa de residuais"

    cfg = env.cfg.with_overrides({"risk": {"min_position_weight": tiny_threshold}})
    res = optimize(alpha, env.model, cons, env.cost_model, cfg, NAV, None, True)
    w = res.weights
    nz = w[w != 0]
    assert (nz.abs() >= tiny_threshold - 1e-9).all()
    assert res.passes >= 2
    assert any("Passadas" in n for n in res.diagnostics.notes)
    _assert_feasible(res, cons, env, cfg)


def test_weekly_turnover_limited_but_not_at_inception(env: Env, inception) -> None:
    res0, _ = inception
    current = res0.weights[res0.weights != 0]
    rng = np.random.default_rng(99)
    new_alpha = pd.Series(rng.normal(0.0, 0.15, len(env.alpha)), index=env.alpha.index)
    limit = 0.20
    cons_wk = _constraints(env, current=current, inception=False)
    weekly = optimize(new_alpha, env.model, cons_wk, env.cost_model, env.cfg, NAV, current,
                      False, env.market_w, overrides={"max_weekly_turnover": limit})
    turnover = float((weekly.weights - current.reindex(weekly.weights.index).fillna(0.0))
                     .abs().sum())
    assert turnover <= limit + TOL
    assert "turnover" in weekly.diagnostics.binding_constraints
    _assert_feasible(weekly, cons_wk, env, env.cfg, current=current)

    cons_inc = _constraints(env, inception=True)
    inc = optimize(new_alpha, env.model, cons_inc, env.cost_model, env.cfg, NAV, None, True,
                   env.market_w)
    assert float(inc.weights.abs().sum()) > limit  # inception: sem limite de giro


def test_relaxation_ladder_turnover_when_forced_exits(env: Env, inception) -> None:
    res0, _ = inception
    current = res0.weights[res0.weights != 0]
    cons = _constraints(env, current=current, inception=False)
    res = optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, current, False,
                   env.market_w, overrides={"exclude_issuers": list(current.index),
                                            "max_weekly_turnover": 0.10})
    assert res.relaxations == ["turnover"]
    assert any("Relaxamento 1" in n for n in res.diagnostics.notes)
    assert (res.weights.reindex(current.index) == 0).all()  # saída total permitida


def test_relaxation_ladder_country_sector_on_contradictory_inputs(env: Env) -> None:
    cons = _constraints(env, inception=False)
    assets = env.panel.assets
    br = [i for i in cons.index if cons.loc[i, "country"] == "BR"
          and cons.loc[i, "max_long"] >= 0.03 and i not in env.special.values()]
    stuck = br[:4]
    assert len(stuck) == 4
    current = pd.Series(0.03, index=stuck)
    cons.loc[stuck, "max_trade"] = 0.0125       # só consegue reduzir até 1,75% cada
    cons.loc[stuck, "max_short"] = 0.0
    others_br = [i for i in cons.index if assets.loc[i, "country"] == "BR" and i not in stuck]
    cons.loc[others_br, ["max_long", "max_short"]] = 0.0   # BR líquido ≥ 7% > 5%
    res = optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, current, False,
                   env.market_w)
    assert "country_sector" in res.relaxations
    assert res.relaxations.index("country_sector") > res.relaxations.index("turnover")
    assert "beta" not in res.relaxations
    br_net = float(res.weights[[i for i in cons.index if cons.loc[i, "country"] == "BR"]].sum())
    assert 0.05 < br_net <= 0.075 + TOL
    assert abs(res.weights.sum()) <= env.cfg.risk.net_exposure_max_abs + TOL  # nunca relaxado
    assert any("Relaxamento 3" in n for n in res.diagnostics.notes)


def test_infeasible_beyond_ladder_raises(env: Env) -> None:
    cons = _constraints(env, inception=False)
    iid = env.special["cap"]
    current = pd.Series({iid: 0.06})
    cons.loc[iid, "max_long"] = 0.04
    cons.loc[iid, "max_trade"] = 0.01   # não consegue chegar ao teto: contraditório
    with pytest.raises(OptimizationError) as exc:
        optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, current, False)
    assert exc.value.relaxations == ["turnover", "style", "country_sector", "beta"]
    assert exc.value.diagnostics is not None
    assert "inviável" in exc.value.diagnostics.notes[-1]


def test_missing_alpha_only_allows_hold_or_reduce(env: Env) -> None:
    iid = env.special["cap"]
    new = env.special["no_short"]  # sem posição: sem alpha não pode abrir
    alpha = env.alpha.drop([iid, new])
    current = pd.Series({iid: 0.005})
    cons = _constraints(env, current=current, inception=False)
    res = optimize(alpha, env.model, cons, env.cost_model, env.cfg, NAV, current, False)
    assert 0.0 <= res.weights[iid] <= 0.005 + TOL
    assert res.weights[new] == 0.0
    assert res.diagnostics.n_excluded.get("alpha_ausente") == 2


def test_legacy_short_without_borrow_data_is_handled(env: Env) -> None:
    no_line = env.sides.index[~env.sides["can_short"].astype(bool)
                              & env.panel.assets["eligible"].reindex(env.sides.index)]
    iid = no_line[0]  # sem linha alugável: short legado precisa ser recomprado
    current = pd.Series({iid: -0.004})
    cons = _constraints(env, current=current, inception=False)
    assert np.isnan(cons.loc[iid, "borrow_fee"]) and cons.loc[iid, "max_short"] == 0.0
    res = optimize(env.alpha, env.model, cons, env.cost_model, env.cfg, NAV, current, False)
    assert res.weights[iid] >= -TOL  # short zerado (teto de short = 0)


def test_risk_parts_match_model(env: Env, inception) -> None:
    res, _ = inception
    parts = portfolio_risk_parts(res.weights, env.model)
    assert parts.vol == pytest.approx(env.model.portfolio_vol(res.weights), rel=1e-10)
    assert parts.contributions.sum() == pytest.approx(1.0)
    with pytest.raises(KeyError):
        portfolio_risk_parts(pd.Series({"FORA": 0.01}), env.model)


# ==========================================================
# Compliance
# ==========================================================

def _run(env: Env, w: pd.Series, cons: pd.DataFrame, **kw) -> list:
    args = dict(current=None, inception=True, snapshot_as_of=AS_OF, week=WEEK,
                market_w=env.market_w, is_synthetic=True)
    args.update(kw)
    return run_compliance(w, env.model, cons, env.squeeze, env.panel.assets, env.cfg, NAV,
                          **args)


def test_compliance_passes_optimizer_output(env: Env, inception) -> None:
    res, cons = inception
    checks = _run(env, res.weights, cons)
    assert hard_failures(checks) == []
    ids = {c.check_id for c in checks}
    for required in ("NET_EXPOSURE", "GROSS_MAX", "GROSS_MIN", "BETA", "VOL_MAX", "VOL_MIN",
                     "VOL_TARGET", "NAME_LONG_MAX", "NAME_SHORT_MAX", "LIQ_DAYS_LONG",
                     "LIQ_DAYS_SHORT", "SHORT_NOT_ALLOWED", "SQUEEZE_HIGH",
                     "SQUEEZE_MEDIUM_CAP", "BORROW_FEE", "LONG_NOT_ALLOWED", "TURNOVER",
                     "SINGLE_NAME_RISK", "FACTOR_RISK_SHARE", "DATA_STALENESS",
                     "SYNTHETIC_DATA", "COUNTRY_NET:BR", "STYLE:momentum"):
        assert required in ids
    syn = next(c for c in checks if c.check_id == "SYNTHETIC_DATA")
    assert syn.severity == Severity.INFO and "DADOS SIMULADOS" in syn.details
    assert all(c.details for c in checks)
    vt = next(c for c in checks if c.check_id == "VOL_TARGET")
    assert vt.passed and vt.limit == env.cfg.risk.vol_target_annual
    vt6 = next(c for c in _run(env, res.weights, cons, vol_target=0.06)
               if c.check_id == "VOL_TARGET")
    assert vt6.limit == 0.06


def test_compliance_flags_bad_portfolio(env: Env) -> None:
    cons = _constraints(env)
    sp = env.special
    assets = env.panel.assets
    used = set(sp.values())
    illiquid = cons[cons["can_long"] & (cons["adtv_long_usd"] < 8e6)
                    & ~cons.index.isin(used)].index[0]
    used.add(illiquid)
    not_shortable = cons[~cons["shortable"] & assets["eligible"]
                         & ~cons.index.isin(used)].index[0]
    used.add(not_shortable)
    liquid = cons[(cons["adtv_long_usd"] > 50e6) & ~cons.index.isin(used)].index[0]
    w = pd.Series({
        liquid: 0.06,            # acima do teto de 4%
        illiquid: 0.039,         # dentro do teto, mas acima de 3 dias de liquidez
        sp["no_long"]: 0.01,     # visão no_long
        sp["high"]: -0.02,       # squeeze HIGH
        sp["medium"]: -0.02,     # MEDIUM acima do teto reduzido de 1,25%
        sp["fee"]: -0.01,        # aluguel acima do limite
        sp["no_short"]: -0.01,   # visão no_short
        not_shortable: -0.01,    # sem aluguel
    })
    checks = _run(env, w, cons, snapshot_as_of=date(2026, 9, 25))
    failed = {c.check_id for c in hard_failures(checks)}
    expected = {"NET_EXPOSURE", "NAME_LONG_MAX", "LIQ_DAYS_LONG", "LONG_NOT_ALLOWED",
                "SQUEEZE_HIGH", "SQUEEZE_MEDIUM_CAP", "BORROW_FEE", "SHORT_NOT_ALLOWED",
                "DATA_STALENESS"}
    assert expected <= failed
    by_id = {c.check_id: c for c in checks}
    assert by_id["NET_EXPOSURE"].value == pytest.approx(float(w.sum()))
    assert sp["high"] in by_id["SQUEEZE_HIGH"].details
    assert not_shortable in by_id["SHORT_NOT_ALLOWED"].details
    assert sp["no_short"] in by_id["SHORT_NOT_ALLOWED"].details

    # alavancagem excessiva ⇒ vol e gross acima dos tetos
    big = _run(env, w * 15, cons)  # gross 0,179 × 15 ≈ 2,7x
    failed_big = {c.check_id for c in hard_failures(big)}
    assert {"VOL_MAX", "GROSS_MAX"} <= failed_big


def test_compliance_data_and_drawdown_rules(env: Env, inception) -> None:
    res, cons = inception
    w = res.weights
    future = _run(env, w, cons, snapshot_as_of=date(2026, 10, 6))
    assert "DATA_STALENESS" in {c.check_id for c in hard_failures(future)}

    soft = _run(env, w, cons, drawdown=-0.035)
    by_id = {c.check_id: c for c in soft}
    assert not by_id["DRAWDOWN_SOFT"].passed and by_id["DRAWDOWN_SOFT"].severity == Severity.SOFT
    assert by_id["DRAWDOWN_HARD"].passed

    current = w[w != 0]
    hard = _run(env, w, cons, current=current, inception=False, drawdown=-0.06)
    assert "DRAWDOWN_HARD" in {c.check_id for c in hard_failures(hard)}
    cut = _run(env, w * 0.5, cons, current=current, inception=False, drawdown=-0.06)
    assert "DRAWDOWN_HARD" not in {c.check_id for c in hard_failures(cut)}

    real = _run(env, w, cons, is_synthetic=False)
    syn = next(c for c in real if c.check_id == "SYNTHETIC_DATA")
    assert "DADOS SIMULADOS" not in syn.details

    nan_w = w.copy()
    nan_w.iloc[0] = np.nan
    bad = _run(env, nan_w, cons)
    assert "WEIGHTS_VALID" in {c.check_id for c in hard_failures(bad)}


# ==========================================================
# Posições, ordens e hedge cambial
# ==========================================================

@pytest.fixture(scope="module")
def targets(env: Env, inception) -> list[PositionTarget]:
    res, _ = inception
    parts = portfolio_risk_parts(res.weights, env.model)
    return build_positions(
        res.weights, env.sides, env.panel.lines, env.panel.assets, env.squeeze, env.alpha,
        None, None, parts.contributions, env.betas, NAV, env.md.fx.iloc[-1])


def test_round_to_lot_and_lot_size() -> None:
    assert lot_size("SBR01.SA") == 100
    assert lot_size("SBR01ADR") == 1
    assert round_to_lot(1249.0, 100) == 1200
    assert round_to_lot(1250.0, 100) == 1300
    assert round_to_lot(-1251.0, 100) == -1300
    assert round_to_lot(49.0, 100) == 0


def test_build_positions_lots_lines_and_metadata(env: Env, targets, inception) -> None:
    res, _ = inception
    assert len(targets) == int((res.weights != 0).sum())
    longs = [t for t in targets if t.side == Side.LONG]
    shorts = [t for t in targets if t.side == Side.SHORT]
    assert longs and shorts
    assert [t.weight for t in longs] == sorted([t.weight for t in longs], reverse=True)
    br_local = [t for t in targets if t.execution_ticker.endswith(".SA")]
    assert br_local, "cenário precisa de linha local B3"
    for t in targets:
        exp_ticker = env.sides.loc[t.issuer_id, "long_ticker" if t.weight > 0 else "short_ticker"]
        assert t.execution_ticker == exp_ticker
        assert t.shares is not None
        assert np.sign(t.shares) == np.sign(t.weight)
        line = env.panel.lines.loc[t.execution_ticker]
        fx = 1.0 if t.currency == "USD" else float(env.md.fx[t.currency].iloc[-1])
        lot = 100 if t.execution_ticker.endswith(".SA") else 1
        assert t.shares % lot == 0
        assert abs(t.shares * line["last_price_local"] * fx - t.notional_usd) <= (
            lot * line["last_price_local"] * fx / 2 + 1e-6)
        assert t.pct_adtv == pytest.approx(abs(t.notional_usd) / t.adtv_usd)
        assert t.days_to_liquidate == pytest.approx(t.pct_adtv / 0.20)
        if t.side == Side.SHORT:
            assert t.borrow_fee_annual is not None
            assert t.squeeze_bucket != "HIGH"
        else:
            assert t.borrow_fee_annual is None
        assert t.risk_contribution is not None and t.alpha_annual is not None
    assert all(t.line_type in (LineType.LOCAL, LineType.ADR, LineType.US_LISTED)
               for t in targets)


def test_build_positions_short_without_line_raises(env: Env) -> None:
    iid = env.sides.index[~env.sides["can_short"].astype(bool)][0]
    with pytest.raises(ValueError, match="sem linha de short"):
        build_positions(pd.Series({iid: -0.01}), env.sides, env.panel.lines, env.panel.assets,
                        env.squeeze, None, None, None, None, None, NAV, env.md.fx.iloc[-1])
    with pytest.raises(ValueError, match="NaN"):
        build_positions(pd.Series({iid: np.nan}), env.sides, env.panel.lines, env.panel.assets,
                        env.squeeze, None, None, None, None, None, NAV, env.md.fx.iloc[-1])


def _pt(iid: str, ticker: str, w: float, shares: int | None, country: str = "BR",
        currency: str = "BRL", line_type: LineType = LineType.LOCAL) -> PositionTarget:
    return PositionTarget(
        issuer_id=iid, name=iid, country=country, sector="Financials",
        side=Side.LONG if w > 0 else Side.SHORT, weight=w, notional_usd=w * NAV,
        execution_ticker=ticker, line_type=line_type, currency=currency, shares=shares,
        adtv_usd=20e6)


def _bp(iid: str, ticker: str, w: float, shares: int | None, currency: str = "BRL"
        ) -> BookedPosition:
    return BookedPosition(issuer_id=iid, ticker=ticker, weight=w, notional_usd=w * NAV,
                          shares=shares, currency=currency)


def test_build_trades_actions_and_line_switch() -> None:
    targets = [
        _pt("A", "A.SA", 0.03, 3000),                                  # aumenta long
        _pt("B", "BADR", -0.01, -100, currency="USD", line_type=LineType.ADR),  # reduz short
        _pt("C", "CADR", -0.02, -500, currency="USD", line_type=LineType.ADR),  # troca linha
        _pt("E", "E.SA", -0.01, -1000),                                # cruza o zero
        _pt("F", "F.SA", 0.01, 1000),                                  # sem mudança de ações
    ]
    current = [
        _bp("A", "A.SA", 0.02, 2000),
        _bp("B", "BADR", -0.02, -200, currency="USD"),
        _bp("C", "C.MX", 0.02, 4000, currency="MXN"),
        _bp("D", "D.SA", 0.01, 1000),                                  # sai da carteira
        _bp("E", "E.SA", 0.01, 1000),
        _bp("F", "F.SA", 0.011, 1000),
    ]
    cost = pd.Series({"A": 12.0, "CADR": 20.0})
    trades = build_trades(targets, current, NAV, cost_bps=cost, participation=0.2)
    got = [(t.issuer_id, t.ticker, t.action, t.shares) for t in trades]
    assert ("A", "A.SA", TradeAction.BUY, 1000) in got
    assert ("B", "BADR", TradeAction.COVER, 100) in got
    assert ("C", "C.MX", TradeAction.SELL, 4000) in got
    assert ("C", "CADR", TradeAction.SHORT, 500) in got
    assert ("D", "D.SA", TradeAction.SELL, 1000) in got
    assert ("E", "E.SA", TradeAction.SELL, 1000) in got
    assert ("E", "E.SA", TradeAction.SHORT, 1000) in got
    assert not any(t.issuer_id == "F" for t in trades)
    # fechamento antes da abertura para o mesmo emissor
    c_actions = [t.action for t in trades if t.issuer_id == "C"]
    assert c_actions == [TradeAction.SELL, TradeAction.SHORT]
    a = next(t for t in trades if t.issuer_id == "A")
    assert a.notional_usd == pytest.approx(0.01 * NAV)
    assert a.weight_change == pytest.approx(0.01)
    assert a.est_cost_bps == 12.0
    assert a.pct_adtv == pytest.approx(0.01 * NAV / 20e6)
    assert a.est_days == pytest.approx(a.pct_adtv / 0.2)
    c_short = next(t for t in trades if t.ticker == "CADR")
    assert c_short.est_cost_bps == 20.0
    d = next(t for t in trades if t.issuer_id == "D")
    assert d.pct_adtv is None and d.weight_change == pytest.approx(-0.01)


def test_build_trades_inception_from_targets(targets) -> None:
    trades = build_trades(targets, None, NAV)
    assert len(trades) == len(targets)
    for t in trades:
        assert t.action in (TradeAction.BUY, TradeAction.SHORT)
        assert (t.action == TradeAction.BUY) == (t.weight_change > 0)


def test_fx_hedges_sign_and_threshold() -> None:
    targets = [
        _pt("A", "A.SA", 0.03, 3000),
        _pt("B", "BADR", 0.01, 100, currency="USD", line_type=LineType.ADR),   # ADR BR: BRL
        _pt("C", "C.MX", -0.005, -100, country="MX", currency="MXN"),
        _pt("D", "DREG", 0.02, 100, country="LATAM", currency="USD",
            line_type=LineType.US_LISTED),
        _pt("E", "E.SN", -0.02, -100, country="CL", currency="CLP"),
    ]
    hedges = {h.currency: h for h in fx_hedges(targets, NAV, threshold=0.01)}
    assert "USD" not in hedges
    brl = hedges["BRL"]
    assert brl.exposure_usd == pytest.approx(0.04 * NAV)       # local + ADR
    assert brl.hedge_notional_usd == pytest.approx(-0.04 * NAV)
    assert brl.instrument == "NDF 1M"
    assert "comprar BRL à vista" in brl.rationale             # caixa para a compra local
    assert hedges["MXN"].hedge_notional_usd == 0.0             # abaixo do limiar
    clp = hedges["CLP"]
    assert clp.hedge_notional_usd == pytest.approx(0.02 * NAV)  # short ⇒ hedge comprado
    assert "comprar CLP a termo" in clp.rationale


# ==========================================================
# Revisão adversarial: regressões de bugs encontrados
# ==========================================================

def _true_objective(res: OptimizationResult, alpha: pd.Series, cons: pd.DataFrame,
                    current: pd.Series, env: Env) -> float:
    """Objetivo recalculado a partir dos pesos LÍQUIDOS (custo por perna real, sem caixas)."""
    w = res.weights
    w0 = current.reindex(w.index).fillna(0.0)
    cost = float(estimate_rebalance_costs(w, w0, env.cost_model.reindex(w.index)).sum())
    fee = cons["borrow_fee"].reindex(w.index)
    short = (-w).clip(lower=0.0)
    assert not fee[short > 0].isna().any()
    borrow = float((fee[short > 0] * short[short > 0]).sum())
    amort = 52.0 / env.cfg.costs.amortization_weeks
    var = env.model.portfolio_variance(w)
    return (float((alpha.reindex(w.index) * w).sum()) - amort * cost - borrow
            - env.cfg.risk.risk_aversion * var)


def test_rebalance_has_no_split_legs_and_objective_matches_net_weights(env: Env,
                                                                       inception) -> None:
    """Bug: l > 0 e s > 0 no mesmo emissor dividiam a ordem (impacto superaditivo) e o
    otimizador subestimava o custo real; o objetivo reportado não batia com os pesos líquidos."""
    res0, _ = inception
    current = res0.weights[res0.weights != 0]
    alpha = -env.alpha  # inverte o sinal: reduz/inverte longs e shorts existentes
    cons = _constraints(env, current=current, inception=False)
    res = optimize(alpha, env.model, cons, env.cost_model, env.cfg, NAV, current, False,
                   env.market_w)
    true_obj = _true_objective(res, alpha, cons, current, env)
    assert res.diagnostics.objective == pytest.approx(true_obj, rel=1e-6, abs=1e-8)
    assert any("complementaridade" in n for n in res.diagnostics.notes)
    assert not any("ATENÇÃO" in n for n in res.diagnostics.notes)
    _assert_feasible(res, cons, env, env.cfg, current=current, check_turnover=True)


def test_exit_floor_does_not_allow_oversized_increase(env: Env) -> None:
    """Bug: max_trade com piso |w₀| (para permitir saída) também permitia AUMENTAR a posição
    além do teto de negociação por liquidez."""
    cfg = env.cfg.with_overrides({"liquidity": {"max_days_to_liquidate_long": 10.0}})
    liq = cfg.liquidity
    base = _constraints(env, cfg, inception=False)
    cand = base[(base["max_long"] >= 0.04 - 1e-12) & (base["max_trade_liq"] < 0.02)
                & ~base.index.isin(list(env.special.values()))]
    iid = cand.index[0]
    mtl = liq.participation_rate * base.loc[iid, "adtv_long_usd"] * liq.max_trade_days_weekly / NAV
    assert base.loc[iid, "max_trade_liq"] == pytest.approx(mtl)
    start = 1.5 * mtl
    current = pd.Series({iid: start})
    cons = _constraints(env, cfg, current=current, inception=False)
    assert cons.loc[iid, "max_trade"] == pytest.approx(start)  # piso de saída preservado
    alpha = env.alpha.copy()
    alpha[iid] = 2.0
    res = optimize(alpha, env.model, cons, env.cost_model, cfg, NAV, current, False, env.market_w)
    assert res.weights[iid] - start <= mtl + TOL
    assert res.weights[iid] - start == pytest.approx(mtl, abs=1e-6)  # usa o teto, não o piso
    assert f"max_trade_liq:{iid}" in res.diagnostics.binding_constraints
    # saída total (redução > teto de liquidez) continua permitida
    out = optimize(alpha, env.model, cons, env.cost_model, cfg, NAV, current, False,
                   env.market_w, overrides={"exclude_issuers": iid})  # string única
    assert out.weights[iid] == 0.0


def test_model_implied_betas_missing_specific_var_is_nan(env: Env) -> None:
    """Bug: variância específica ausente virava zero no beta implícito."""
    m = env.model
    iid = m.assets[0]
    D = m.specific_var.copy()
    D[iid] = np.nan
    broken = RiskModel(as_of=m.as_of, exposures=m.exposures, factor_cov=m.factor_cov,
                       specific_var=D, factor_returns=m.factor_returns,
                       specific_returns=m.specific_returns, factor_groups=m.factor_groups)
    betas = model_implied_betas(broken, env.market_w)
    assert np.isnan(betas[iid])
    assert betas.drop(iid).notna().all()
    # equivalente a excluir o nome da carteira de mercado
    ref = model_implied_betas(m, env.market_w.drop(iid))
    assert np.allclose(betas.drop(iid), ref.drop(iid))


def test_compliance_liquidity_uses_line_adtv_and_short_participation(env: Env,
                                                                     inception) -> None:
    """Bugs: ADTV da linha ausente caía no ADTV agregado do emissor (otimista) e shorts eram
    medidos a 20% de participação em vez de ``short_participation_rate`` (15%)."""
    res, cons = inception
    w = res.weights[res.weights != 0]
    liq = env.cfg.liquidity
    long_id = w[w > 0].index[0]
    c2 = cons.copy()
    c2.loc[long_id, "adtv_long_usd"] = np.nan
    by_id = {c.check_id: c for c in _run(env, w, c2)}
    assert not by_id["LIQ_DAYS_LONG"].passed and long_id in by_id["LIQ_DAYS_LONG"].details
    # sem a coluna de ADTV por linha: usa o agregado e avisa no detalhe
    c3 = cons.drop(columns=["adtv_long_usd"])
    det = {c.check_id: c for c in _run(env, w, c3)}["LIQ_DAYS_LONG"].details
    assert "agregado do emissor" in det
    # short dimensionado para 2 dias a 20% do ADTV (= 2,67 dias a 15%) reprova
    sid = cons[cons["can_short"] & (cons["squeeze_bucket"] == "LOW")].index[0]
    size = 0.99 * liq.participation_rate * cons.loc[sid, "adtv_short_usd"] \
        * liq.max_days_to_liquidate_short / NAV
    bad = pd.Series({sid: -size, long_id: size})
    chk = {c.check_id: c for c in _run(env, bad, cons)}["LIQ_DAYS_SHORT"]
    assert not chk.passed
    assert chk.value == pytest.approx(0.99 * liq.participation_rate
                                      * liq.max_days_to_liquidate_short
                                      / liq.short_participation_rate)
    # e o teto do otimizador já respeita a participação de short do mandato
    assert cons.loc[sid, "max_short"] <= (liq.short_participation_rate
                                          * cons.loc[sid, "adtv_short_usd"]
                                          * liq.max_days_to_liquidate_short / NAV) + 1e-12


def test_drawdown_hard_does_not_ratchet_and_stop_out_caps_gross(env: Env, inception) -> None:
    """Bugs: o stop duro exigia novo corte de 50% do gross a cada semana enquanto o drawdown
    persistisse; o stop-out (gross máximo) não era verificado; o gatilho soft era exclusivo."""
    res, cons = inception
    w = res.weights[res.weights != 0]
    dds = env.cfg.drawdown
    vol = portfolio_risk_parts(w, env.model).vol
    cut = w * (0.9 * dds.degross_multiplier * env.cfg.risk.vol_target_annual / vol)
    # semana seguinte ao corte: mesma carteira (já com risco cortado) continua aprovável
    again = {c.check_id: c for c in _run(env, cut, cons, current=cut, inception=False,
                                         drawdown=-0.06)}
    assert again["DRAWDOWN_HARD"].passed
    # stop-out: gross acima de stop_out_gross reprova mesmo cortando 50% do gross atual
    prop = w * (0.8 / float(w.abs().sum()))           # gross 0,8x > stop_out_gross (0,5x)
    cur = prop * 2.0                                   # corte de 50% em relação ao atual
    out = {c.check_id: c for c in _run(env, prop, cons, current=cur, inception=False,
                                       drawdown=-0.08)}
    assert not out["DRAWDOWN_HARD"].passed and "Stop-out" in out["DRAWDOWN_HARD"].details
    hard_only = {c.check_id: c for c in _run(env, prop, cons, current=cur, inception=False,
                                             drawdown=-0.06)}
    assert hard_only["DRAWDOWN_HARD"].passed           # sem stop-out, o corte basta
    small = prop * (0.95 * dds.stop_out_gross / 0.8)
    ok = {c.check_id: c for c in _run(env, small, cons, current=cur, inception=False,
                                      drawdown=-0.08)}
    assert ok["DRAWDOWN_HARD"].passed
    # gatilho soft inclusivo: drawdown exatamente no stop aciona a revisão
    edge = {c.check_id: c for c in _run(env, w, cons, drawdown=dds.soft_stop)}
    assert not edge["DRAWDOWN_SOFT"].passed


def test_build_trades_share_driven_notional_is_consistent() -> None:
    """Bug: com ações conhecidas, a ação seguia as ações, mas notional/variação de peso
    seguiam a diferença de pesos (deriva de preço) — ex.: VENDA com variação positiva."""
    targets = [_pt("A", "A.SA", 0.012, 1000)]          # preço subiu: 1000 ações = 1,2%
    current = [_bp("A", "A.SA", 0.010, 1100)]          # peso registrado no preço antigo
    trades = build_trades(targets, current, NAV)
    assert len(trades) == 1
    t = trades[0]
    assert t.action == TradeAction.SELL and t.shares == 100
    px = 0.012 * NAV / 1000
    assert t.notional_usd == pytest.approx(100 * px)
    assert t.weight_change == pytest.approx(-100 * px / NAV)
    # sem ações conhecidas: segue a diferença de pesos
    t2 = build_trades([_pt("A", "A.SA", 0.012, None)], [_bp("A", "A.SA", 0.010, None)], NAV)
    assert t2[0].action == TradeAction.BUY and t2[0].weight_change == pytest.approx(0.002)


def test_build_positions_short_participation(env: Env, targets, inception) -> None:
    res, _ = inception
    alt = build_positions(
        res.weights, env.sides, env.panel.lines, env.panel.assets, env.squeeze, env.alpha,
        None, None, None, env.betas, NAV, env.md.fx.iloc[-1], participation=0.20,
        short_participation=0.15)
    for a, b in zip(alt, targets, strict=True):
        if a.side == Side.SHORT:
            assert a.days_to_liquidate == pytest.approx(a.pct_adtv / 0.15)
        else:
            assert a.days_to_liquidate == pytest.approx(b.days_to_liquidate)
