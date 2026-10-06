"""Construção com limites operacionais, risco fatorial na carteira atingida e formulação aberta
(otimizador e compliance; DADOS SIMULADOS).

Modelo de risco B/F/D sintético sobre o painel simulado (como em ``test_portfolio``), com um
modelo "base" sem a janela de evento (vol específica de BR reduzida) para o gate duplo.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cdp.analytics.panel import build_asset_panel
from cdp.config import FundConfig, OperationalLimits
from cdp.contracts import Severity
from cdp.data.synthetic import make_synthetic_market
from cdp.portfolio.compliance import hard_failures, passive_checks, run_compliance
from cdp.portfolio.costs import build_cost_model
from cdp.portfolio.optimizer import (
    OptimizationError,
    _resolve_settings,
    build_asset_constraints,
    metodologia_ativa,
    model_implied_betas,
    optimize,
    portfolio_risk_parts,
    sig,
)
from cdp.risk.types import STYLE_FACTORS, RiskModel, country_factor, sector_factor

NAV = 100_000_000.0
AS_OF = date(2026, 10, 2)
WEEK = date(2026, 10, 5)
TOL = 1e-6


def _sides(panel) -> pd.DataFrame:
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


def _model(assets: pd.DataFrame, seed: int = 3, br_spec_mult: float = 1.0) -> RiskModel:
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
    D = D * np.where(assets["country"].reindex(ids) == "BR", br_spec_mult, 1.0)
    groups = {c: "market" if c == "market" else c.split(":")[0] if ":" in c else "style"
              for c in cols}
    fr = pd.DataFrame(rng.standard_t(5, size=(400, len(cols))) * 0.01, columns=cols,
                      index=pd.bdate_range("2025-01-01", periods=400))
    return RiskModel(as_of=AS_OF, exposures=B, factor_cov=F, specific_var=D,
                     factor_returns=fr, specific_returns=pd.DataFrame(),
                     factor_groups=groups)


ACTIVE = {
    "risk": {"max_factor_risk_share": 0.10, "idio_share_goal": 0.90, "idio_share_floor": 0.85,
             "factor_risk_basis": "achieved", "factor_risk_aversion_multiplier": 5.0,
             "second_order_inflation": 1.45, "idio_gate_models": ["decisao", "base"],
             "vol_floor_alpha_scaling": False, "style_exposure_max_abs": 0.10,
             "country_net_max_abs": 0.02, "sector_net_max_abs": 0.025,
             "operational": {"beta": 0.02, "style": 0.05, "sector_net": 0.015,
                             "country_net": {"BR": 0.01, "MX": 0.01, "*": 0.005},
                             "commodity_beta": 0.01}},
}


@pytest.fixture(scope="module")
def env():
    legacy = FundConfig()
    active = legacy.with_overrides(ACTIVE)
    md = make_synthetic_market(seed=11, start=date(2024, 1, 2))
    panel = build_asset_panel(md, legacy)
    assets = panel.assets
    sides = _sides(panel)
    model = _model(assets, br_spec_mult=2.25)     # "decisão": BR com janela de evento
    base = _model(assets, br_spec_mult=1.0)       # "base": sem janela
    market_w = assets["market_cap_usd"]
    betas = model_implied_betas(model, market_w)
    cov = model.cov_matrix()
    daily_vol = pd.Series(np.sqrt(np.diag(cov)) / np.sqrt(252), index=cov.index)
    alpha = pd.Series(np.random.default_rng(5).normal(0.0, 0.15, len(assets)),
                      index=assets.index)
    squeeze = pd.DataFrame({"squeeze_score": 20.0, "bucket": "LOW"}, index=assets.index)
    cm = build_cost_model(sides, assets, daily_vol, legacy, NAV)
    return dict(legacy=legacy, active=active, panel=panel, assets=assets, sides=sides,
                model=model, base=base, market_w=market_w, betas=betas, alpha=alpha,
                squeeze=squeeze, cm=cm)


def _cons(env, cfg, current=None, inception=True):
    return build_asset_constraints(list(env["assets"].index), env["sides"], env["squeeze"],
                                   None, env["betas"], env["assets"], cfg, NAV, current,
                                   inception)


def _opt(env, cfg, cons=None, current=None, inception=True, **kw):
    cons = _cons(env, cfg, current, inception) if cons is None else cons
    return optimize(env["alpha"], env["model"], cons, env["cm"], cfg, NAV, current, inception,
                    env["market_w"], model_base=env["base"], **kw), cons


def _share(w: pd.Series, model: RiskModel, kappa: float) -> float:
    parts = portfolio_risk_parts(w[w != 0], model)
    f = kappa * parts.factor_var
    return f / (f + parts.specific_var)


@pytest.fixture(scope="module")
def solved(env):
    return _opt(env, env["active"])


# ----------------------------------------------------------------------------- ativação


def test_methodology_flag_and_legacy_are_distinct(env):
    assert not metodologia_ativa(env["legacy"])
    assert metodologia_ativa(env["active"])
    res, _ = _opt(env, env["legacy"])
    assert res.formulacao == {} and res.idio == {}


def test_achieved_basis_cap_holds_on_both_models(env, solved):
    res, _ = solved
    w = res.weights
    k = res.kappa_f
    assert k == pytest.approx(1.45)
    for m in (env["model"], env["base"]):
        assert _share(w, m, k) <= 0.10 + 1e-3  # fatia fatorial ≤ s na carteira ATINGIDA
    assert res.idio["base"] == pytest.approx(1 - _share(w, env["base"], k), abs=1e-9)
    assert res.idio["base"] >= 0.90 - 1e-3 and res.idio["decisao"] >= 0.90 - 1e-3
    worst = max(_share(w, m, k) for m in (env["model"], env["base"]))
    binds = any(b.startswith("factor_risk:") for b in res.diagnostics.binding_constraints)
    assert binds == (worst >= 0.10 * (1 - 1e-3))  # vinculante ⇔ fatia no teto
    assert res.ex_ante_vol > 0.005  # carteira de verdade (sem espiral de encolhimento)


def test_operating_limits_are_min_of_mandate_and_operational(env, solved):
    res, cons = solved
    w = res.weights
    op = env["active"].risk.operational
    assert abs(float((cons["beta"] * w).sum())) <= op.beta + TOL
    x = env["model"].factor_exposure(w)
    assert x[STYLE_FACTORS].abs().max() <= op.style + TOL
    assert w.groupby(cons["sector"]).sum().abs().max() <= op.sector_net + TOL
    br = cons.index[cons["country"] == "BR"]
    assert abs(float(w[br].sum())) <= 0.01 + TOL
    assert w.groupby(cons["country"]).sum().abs().max() <= 0.02 + TOL  # mandato por país


def test_formulacao_is_plain_data_with_duals(env, solved):
    res, _ = solved
    f = res.formulacao
    assert set(f) >= {"objetivo", "restricoes", "por_nome", "parametros"}
    text = json.dumps(f, ensure_ascii=False)  # serializável sem tipos numpy
    assert "NaN" not in text and "Infinity" not in text
    keys = {r["chave"] for r in f["restricoes"]}
    assert {"net_exposure", "beta", "vol_target", "gross", "factor_risk:decisao",
            "factor_risk:base"} <= keys
    assert any(k.startswith("op_country:") for k in keys)
    for r in f["restricoes"]:
        assert set(r) == {"chave", "nome", "expressao", "limite", "valor", "folga",
                          "vinculante", "preco_sombra", "custo_bp_1pct"}
        for v in (r["limite"], r["valor"], r["folga"], r["preco_sombra"]):
            assert v is None or type(v) is float
        if r["preco_sombra"] is not None:
            assert r["preco_sombra"] >= 0
        if not r["vinculante"] and r["preco_sombra"] is not None:
            # complementaridade: o resíduo do ponto interior não vira preço-sombra publicado
            assert r["preco_sombra"] == 0.0 and r["custo_bp_1pct"] == 0.0
        if r["folga"] is not None:
            assert r["folga"] == 0.0 or abs(r["folga"]) >= 1e-6
    # Restrições ativas = linhas vinculantes da formulação (mesmas chaves), mais os tetos por nome.
    bind = [r["chave"] for r in f["restricoes"] if r["vinculante"]]
    agg = [b for b in res.diagnostics.binding_constraints
           if not b.startswith(("max_long:", "max_short:", "max_trade"))]
    assert agg == bind
    assert f["parametros"]["kappa_f"] == pytest.approx(1.45)
    assert f["parametros"]["solver"] and f["parametros"]["versoes"]["cvxpy"]
    lim = f["limites_por_nome"]
    held = set(res.weights.index[res.weights != 0])
    assert held <= set(lim)
    for iid, row in lim.items():
        assert row["vinculante"] in (None, "long", "short", "negociacao")
        if row["vinculante"] in ("long", "short"):
            assert f"max_{row['vinculante']}:{iid}" in res.diagnostics.binding_constraints


def test_sig_rounds_to_six_significant_digits():
    assert sig(np.float64(0.123456789)) == 0.123457 and type(sig(np.float64(1.0))) is float
    assert sig(float("nan")) is None and sig(None) is None and sig(0.0) == 0.0
    assert sig(123456789.0) == 123457000.0


def test_factor_penalty_is_invariant_to_match_scaling(env):
    cfg = env["active"].with_overrides({"risk": {"risk_target_mode": "match"}})
    res, _ = _opt(env, cfg)
    lam_f = res.formulacao["parametros"]["lambda_f"]
    assert lam_f == pytest.approx(5.0 * cfg.risk.risk_aversion)  # nunca dividido pelo κ do match
    par = res.formulacao["parametros"]
    assert par["lambda_mandato"] == pytest.approx(cfg.risk.risk_aversion)
    assert par["lambda_efetivo"] <= cfg.risk.risk_aversion
    assert par["lambda_efetivo"] * par["divisor_aversao"] == pytest.approx(
        cfg.risk.risk_aversion, rel=1e-5)
    assert par["divisor_maximo"] == 64.0 and par["meta_vol_atingida"] in (True, False)


def test_alpha_is_never_scaled_to_the_band_floor_when_disabled(env):
    """P0-6: com ``vol_floor_alpha_scaling = False`` o alpha não é escalado (VOL_MIN honesto)."""
    weak = env["alpha"] * 0.02
    for flag in (True, False):
        cfg = env["legacy"].with_overrides({"risk": {"risk_target_mode": "match",
                                                     "vol_floor_alpha_scaling": flag}})
        cons = _cons(env, cfg)
        res = optimize(weak, env["model"], cons, env["cm"], cfg, NAV, None, True,
                       env["market_w"])
        scaled = any("alpha escalado" in n for n in res.diagnostics.notes)
        if flag:
            assert scaled or res.ex_ante_vol >= cfg.risk.vol_band_min * 0.99
        else:
            assert not scaled
            assert any("alpha não escalado" in n for n in res.diagnostics.notes)
            assert res.alpha_scale <= 64.0 + 1e-9


# ----------------------------------------------------------------------------- escada


def _stuck_book(env, cfg):
    """Carteira atual com BR líquido de +3% presa por teto de negociação (contraditória)."""
    cons = _cons(env, cfg, inception=False)
    assets = env["assets"]
    br = [i for i in cons.index if cons.loc[i, "country"] == "BR"
          and cons.loc[i, "max_long"] >= 0.01]
    stuck = br[:3]
    current = pd.Series(0.01, index=stuck)
    cons.loc[stuck, "max_trade"] = 0.0035       # só consegue reduzir até 0,65% cada
    cons.loc[stuck, "max_short"] = 0.0
    others = [i for i in cons.index if assets.loc[i, "country"] == "BR" and i not in stuck]
    cons.loc[others, ["max_long", "max_short"]] = 0.0
    return cons, current


def test_ladder_relaxes_operational_up_to_mandate_only(env):
    cfg = env["active"]
    cons, current = _stuck_book(env, cfg)  # BR ≥ 1,95% > 1% operacional, < 2% mandato
    res = optimize(env["alpha"], env["model"], cons, env["cm"], cfg, NAV, current, False,
                   env["market_w"], model_base=env["base"])
    assert "country_sector" in res.relaxations or "mandate" in res.relaxations
    br = [i for i in cons.index if cons.loc[i, "country"] == "BR"]
    br_net = float(res.weights[br].sum())
    assert 0.01 < br_net <= 0.02 + TOL           # nunca acima do mandato
    assert abs(res.weights.sum()) <= cfg.risk.net_exposure_max_abs + TOL
    turnover = float((res.weights - current.reindex(res.weights.index).fillna(0)).abs().sum())
    assert turnover <= 2 * cfg.liquidity.max_weekly_turnover + TOL  # giro nunca ilimitado


def test_infeasible_at_mandate_raises_with_deterministic_code(env):
    cfg = env["active"]
    cons, current = _stuck_book(env, cfg)
    cons.loc[current.index, "max_trade"] = 0.0   # BR preso em +3% > 2% do mandato
    with pytest.raises(OptimizationError) as exc:
        optimize(env["alpha"], env["model"], cons, env["cm"], cfg, NAV, current, False,
                 env["market_w"], model_base=env["base"])
    assert exc.value.codigo == "INVIAVEL"
    assert exc.value.relaxations[-1] == "degross_25"
    assert "mandate" in exc.value.relaxations


def test_legacy_ladder_unchanged(env):
    cfg = env["legacy"]
    cons = _cons(env, cfg, inception=False)
    iid = cons.index[cons["max_long"] > 0.01][0]
    current = pd.Series({iid: 0.06})
    cons.loc[iid, "max_long"] = 0.04
    cons.loc[iid, "max_trade"] = 0.01
    with pytest.raises(OptimizationError) as exc:
        optimize(env["alpha"], env["model"], cons, env["cm"], cfg, NAV, current, False)
    assert exc.value.relaxations == ["turnover", "style", "country_sector", "beta"]


def test_reduce_only_and_vol_cap_overrides(env, solved):
    res0, _ = solved
    current = res0.weights[res0.weights != 0]
    vol0 = portfolio_risk_parts(current, env["model"]).vol
    cfg = env["active"]
    res, _ = _opt(env, cfg, current=current, inception=False,
                  overrides={"reduce_only": True, "vol_cap": 0.5 * vol0,
                             "risk_target_mode": "cap"})
    w = res.weights
    cur = current.reindex(w.index).fillna(0.0)
    assert (w.abs() <= cur.abs() + TOL).all()
    assert ((w * cur) >= -TOL).all()          # nenhum sinal invertido
    assert res.ex_ante_vol <= 0.5 * vol0 + 1e-6
    # Só redução com piso idiossincrático: risco fatorial nunca acima do atual (cada modelo).
    holds = {r["chave"]: r for r in res.formulacao["restricoes"]
             if r["chave"].startswith("factor_hold:")}
    assert set(holds) == {"factor_hold:decisao", "factor_hold:base"}
    for m in (env["model"], env["base"]):
        f_new = portfolio_risk_parts(w[w != 0], m).factor_var
        f_cur = portfolio_risk_parts(current, m).factor_var
        assert f_new <= f_cur * (1 + 2.5e-3)
    normal, _ = _opt(env, cfg, current=current, inception=False)
    assert not any(r["chave"].startswith("factor_hold:")
                   for r in normal.formulacao["restricoes"])


def test_risk_floor_step_makes_derisking_caps_feasible(env, solved):
    """Teto de vol da redução abaixo do que as posições presas permitem: o degrau final sobe o
    teto até o menor risco viável (nunca acima da meta da semana), em vez de inviabilizar."""
    res0, _ = solved
    current = res0.weights[res0.weights != 0]
    cfg = env["active"]
    cons = _cons(env, cfg, current, inception=False)
    stuck = current.abs().sort_values(ascending=False).index[:6]
    cons["congelado"] = ""
    cons.loc[stuck, "congelado"] = "mercado local fechado"
    vol_stuck = portfolio_risk_parts(current[stuck], env["model"]).vol
    res = optimize(env["alpha"], env["model"], cons, env["cm"], cfg, NAV, current, False,
                   env["market_w"], model_base=env["base"],
                   overrides={"reduce_only": True, "vol_cap": 0.2 * vol_stuck,
                              "risk_target_mode": "cap"})
    assert "risk_floor" in res.relaxations
    assert any("menor nível viável" in n for n in res.diagnostics.notes)
    for iid in stuck:
        assert res.weights[iid] == pytest.approx(current[iid], abs=1e-9)
    assert res.ex_ante_vol <= cfg.risk.vol_target_annual


def test_every_override_set_passes_settings_resolution(env):
    """Os overrides das tentativas (inclusive kill switch) são válidos na inception e fora."""
    from cdp.workflow.weekly import KILL_SWITCH_RISK_MULT  # noqa: F401 - contrato público

    for cfg in (env["legacy"], env["active"]):
        sets = [{"vol_target": 0.045}, {"vol_target": 0.045, "gross_multiplier": 0.5},
                {"vol_target": 0.045, "reduce_only": True, "vol_cap": 0.01,
                 "risk_target_mode": "cap", "gross_max": 0.2}]
        for ov in sets:
            for inception in (True, False):
                _resolve_settings(cfg, ov, inception)


# ----------------------------------------------------------------------------- compliance


def test_style_hard_at_mandate_soft_at_operating(env, solved):
    res, cons = solved
    w = res.weights.copy()
    cfg = env["active"]
    base = run_compliance(w, env["model"], cons, env["squeeze"], env["assets"], cfg, NAV, None,
                          True, AS_OF, WEEK, env["market_w"], True, model_base=env["base"],
                          kappa_f=1.45)
    by = {c.check_id: c for c in base}
    assert by["STYLE:momentum"].severity == Severity.HARD
    assert by["STYLE_OP:momentum"].severity == Severity.SOFT
    assert by["IDIO_FLOOR"].severity == Severity.HARD and by["IDIO_FLOOR"].passed
    assert by["IDIO_FLOOR_BASE"].passed and by["IDIO_SHARE_BASE"].severity == Severity.SOFT
    assert "BETA_OP" in by and any(k.startswith("COUNTRY_OP:") for k in by)
    legacy = run_compliance(w, env["model"], cons, env["squeeze"], env["assets"],
                            env["legacy"], NAV, None, True, AS_OF, WEEK, env["market_w"], True)
    lby = {c.check_id: c for c in legacy}
    assert lby["STYLE:momentum"].severity == Severity.SOFT
    assert not any(k.startswith(("IDIO_", "STYLE_OP", "BETA_OP")) for k in lby)


def test_idio_floor_fails_hard_on_a_factor_heavy_book(env):
    cfg = env["active"]
    cons = _cons(env, cfg)
    br = cons.index[cons["country"] == "BR"][:20]
    w = pd.Series(0.01, index=br)  # 20% líquido em BR: risco quase todo fatorial
    checks = run_compliance(w, env["model"], cons, env["squeeze"], env["assets"], cfg, NAV,
                            None, True, AS_OF, WEEK, env["market_w"], True,
                            model_base=env["base"], kappa_f=1.45)
    failed = {c.check_id for c in hard_failures(checks)}
    assert {"IDIO_FLOOR", "IDIO_FLOOR_BASE"} <= failed


def test_idio_floor_on_a_reduce_only_decision_blocks_only_new_factor_risk(env):
    """Decisão só de redução (kill switch): abaixo do piso, passa se a variância fatorial não
    aumenta em relação à carteira atual; aumentar o risco fatorial continua bloqueado."""
    cfg = env["active"]
    cons = _cons(env, cfg, inception=False)
    br = cons.index[cons["country"] == "BR"][:20]
    current = pd.Series(0.01, index=br)
    kw = dict(model_base=env["base"], kappa_f=1.45, reduce_only=True)

    def floor(w):
        checks = run_compliance(w, env["model"], cons, env["squeeze"], env["assets"], cfg, NAV,
                                current, False, AS_OF, WEEK, env["market_w"], True, **kw)
        return {c.check_id: c for c in checks}

    cut = floor(current * 0.5)
    assert cut["IDIO_FLOOR"].passed and cut["IDIO_FLOOR_BASE"].passed
    assert "sem risco fatorial novo" in cut["IDIO_FLOOR"].details
    assert not cut["IDIO_SHARE"].passed  # a meta continua sinalizada
    more = current.copy()
    more.iloc[0] = 0.02
    grown = floor(more)
    assert not grown["IDIO_FLOOR"].passed and grown["IDIO_FLOOR"].severity == Severity.HARD


def test_passive_checks_are_info_only(env, solved):
    res, cons = solved
    checks = run_compliance(res.weights * 40, env["model"], cons, env["squeeze"], env["assets"],
                            env["active"], NAV, None, True, AS_OF, WEEK, env["market_w"], True)
    passive = passive_checks(checks)
    assert passive and all(c.severity == Severity.INFO for c in passive)
    assert all(c.check_id.startswith("PASSIVO:") for c in passive)
    assert not hard_failures(passive)


def test_linked_groups_constraint_and_check(env):
    assets = env["assets"]
    br = list(assets.index[assets["country"] == "BR"][:2])
    cfg = env["active"].with_overrides({"risk_model": {"linked_groups": {"grupo": br}}})
    alpha = env["alpha"].copy()
    alpha[br] = 0.9  # o otimizador quer comprar os dois
    cons = _cons(env, cfg)
    res = optimize(alpha, env["model"], cons, env["cm"], cfg, NAV, None, True, env["market_w"],
                   model_base=env["base"])
    assert float(res.weights[br].clip(lower=0).sum()) <= cfg.risk.max_long_weight + 1e-5
    checks = run_compliance(res.weights, env["model"], cons, env["squeeze"], assets, cfg, NAV,
                            None, True, AS_OF, WEEK, env["market_w"], True)
    lg = next(c for c in checks if c.check_id == "LINKED_GROUP:grupo")
    assert lg.severity == Severity.SOFT and lg.passed


def test_short_entry_block_check(env, solved):
    res, cons = solved
    cfg = env["active"].with_overrides({"squeeze": {"enforce_entry_blocks": True}})
    c = cons.copy()
    shorts = res.weights[res.weights < 0].index[:2]
    c["entry_block"] = c.index.isin(shorts)
    c["entry_block_dado_ausente"] = ""
    checks = run_compliance(res.weights, env["model"], c, env["squeeze"], env["assets"], cfg,
                            NAV, None, True, AS_OF, WEEK, env["market_w"], True)
    blk = next(x for x in checks if x.check_id == "SHORT_ENTRY_BLOCK")
    assert blk.severity == Severity.HARD and not blk.passed
    # short existente pode ser mantido/coberto, nunca aumentado
    current = res.weights[shorts]
    ok = run_compliance(res.weights, env["model"], c, env["squeeze"], env["assets"], cfg, NAV,
                        current, False, AS_OF, WEEK, env["market_w"], True)
    assert next(x for x in ok if x.check_id == "SHORT_ENTRY_BLOCK").passed


def test_drawdown_vol_reference_compliance(env, solved):
    res, cons = solved
    cfg = env["active"].with_overrides({"drawdown": {"risk_reference": "normal_book_vol"}})
    vol = res.ex_ante_vol
    kw = dict(model_base=env["base"], kappa_f=1.45)

    def dd_checks(w, ref, dd):
        out = run_compliance(w, env["model"], cons, env["squeeze"], env["assets"], cfg, NAV,
                             None, True, AS_OF, WEEK, env["market_w"], True, drawdown=dd,
                             drawdown_ref_vol=ref, **kw)
        return {c.check_id: c for c in out}

    hard = dd_checks(res.weights, vol, -0.06)
    assert not hard["DRAWDOWN_HARD"].passed  # vol não foi cortada à metade
    cut = dd_checks(res.weights * 0.49, vol, -0.06)
    assert cut["DRAWDOWN_HARD"].passed
    normal = dd_checks(res.weights, vol, -0.01)
    assert normal["DRAWDOWN_HARD"].passed and normal["DRAWDOWN_SOFT"].passed


def test_kappa_config_mode_and_inflated_factor_share_check(env, solved):
    res, cons = solved
    checks = run_compliance(res.weights, env["model"], cons, env["squeeze"], env["assets"],
                            env["active"], NAV, None, True, AS_OF, WEEK, env["market_w"], True,
                            kappa_f=1.45)
    frs = next(c for c in checks if c.check_id == "FACTOR_RISK_SHARE")
    assert frs.value == pytest.approx(_share(res.weights, env["model"], 1.45), rel=1e-6)
    assert "κ_F" in frs.details


def test_operational_limits_validation():
    with pytest.raises(ValueError):
        OperationalLimits(country_net={"BR": -0.01})
    assert OperationalLimits().country_net_limit("CL") == 0.005
    assert math.isclose(OperationalLimits().country_net_limit("BR"), 0.01)


def test_hard_contracts_untouched_by_new_fields():
    """Nenhum campo novo em contratos com hash: os diagnósticos vivem em ``Proposal.overrides``."""
    from cdp.contracts import ComplianceCheck, Proposal, RiskSummary

    assert "overrides" in Proposal.model_fields
    assert set(RiskSummary.model_fields) >= {"ex_ante_vol", "factor_vol", "specific_vol"}
    assert "risco" not in Proposal.model_fields and "formulacao" not in Proposal.model_fields
    assert set(ComplianceCheck.model_fields) == {"check_id", "name", "passed", "severity",
                                                 "value", "limit", "details"}
    assert replace  # noqa: B018 - import usado em outros testes do módulo


# ----------------------------------------------------------------------------- países finos


def test_thin_country_without_model_factor_gets_the_operating_limit(env):
    """País com poucos emissores (sem fator próprio no modelo) recebe o limite operacional
    ``"*"`` pelo rótulo do painel, no otimizador e na compliance."""
    cfg = env["active"]
    cons = _cons(env, cfg)
    assert "ZZ" not in set(cons["country"])
    thin = [i for i in cons.index if cons.loc[i, "max_long"] > 0.01][:2]
    cons.loc[thin, "country"] = "ZZ"  # país sem fator de país no modelo
    alpha = env["alpha"].copy()
    alpha[thin] = 0.8  # inclinação forte: sem o limite operacional, ZZ iria ao teto do mandato
    res = optimize(alpha, env["model"], cons, env["cm"], cfg, NAV, None, True, env["market_w"],
                   model_base=env["base"])
    rows = {r["chave"]: r for r in res.formulacao["restricoes"]}
    assert rows["op_country:ZZ"]["limite"] == pytest.approx(0.005)
    assert abs(float(res.weights[thin].sum())) <= 0.005 + TOL
    assets = env["assets"].copy()
    assets.loc[thin, "country"] = "ZZ"
    checks = {c.check_id: c for c in run_compliance(
        res.weights, env["model"], cons, env["squeeze"], assets, cfg, NAV, None, True, AS_OF,
        WEEK, env["market_w"], True, model_base=env["base"], kappa_f=1.45)}
    assert checks["COUNTRY_OP:ZZ"].limit == pytest.approx(0.005)
    assert checks["COUNTRY_OP:ZZ"].passed


# ----------------------------------------------------------------------------- congelados


def _frozen_cons(env, cfg, current: pd.Series, frozen: list[str]) -> pd.DataFrame:
    cons = _cons(env, cfg, current, inception=False)
    cons["congelado"] = ""
    for iid in frozen:
        w0 = float(current.get(iid, 0.0))
        cons.loc[iid, ["max_long", "max_short"]] = [max(w0, 0.0), max(-w0, 0.0)]
        cons.loc[iid, ["max_trade", "max_trade_liq"]] = 0.0
        cons.loc[iid, "congelado"] = "mercado local fechado"
    return cons


def test_frozen_name_stays_put_even_when_excluded_by_the_manager(env, solved):
    cfg = env["active"]
    res0, _ = solved
    w0 = res0.weights[res0.weights != 0]
    frozen = [w0.abs().idxmax()]
    cons = _frozen_cons(env, cfg, w0, frozen)
    res = optimize(env["alpha"], env["model"], cons, env["cm"], cfg, NAV, w0, False,
                   env["market_w"], model_base=env["base"],
                   overrides={"exclude_issuers": frozen})
    assert res.weights[frozen[0]] == pytest.approx(w0[frozen[0]], abs=1e-7)


def test_degross_steps_never_go_below_the_frozen_gross(env, solved):
    """Degraus de redução: gross ≤ max(fração × atual, gross congelado) — nunca contraditório
    com posições que não podem negociar."""
    from cdp.portfolio.optimizer import _limits, _Relax

    cfg = env["active"]
    res0, _ = solved
    w0 = res0.weights[res0.weights != 0]
    frozen = list(w0.abs().sort_values(ascending=False).index[: max(3, len(w0) // 2)])
    cons = _frozen_cons(env, cfg, w0, frozen)
    pinned = float(w0[frozen].abs().sum())
    assert pinned > 0.25 * float(w0.abs().sum())
    import cdp.portfolio.optimizer as opt

    settings = opt._resolve_settings(cfg, None, False)
    p = opt._build_problem(env["alpha"].reindex(cons.index).fillna(0.0), env["model"], cons,
                           env["cm"], cfg, settings, w0.reindex(cons.index).fillna(0.0),
                           model_base=env["base"], kappa=1.45, pinned_gross=pinned)
    lim = _limits(p, _Relax().step("degross_25"))
    assert lim.gross >= pinned


def test_close_capacity_check_is_per_leg(env, solved):
    """``TRADE_CLOSE_CAPACITY`` (SOFT): aumento da perna comprada contra a capacidade da linha
    comprada e o da vendida contra a da vendida; reduzir nunca reprova."""
    cfg = env["active"]
    res, cons = solved
    w = res.weights[res.weights != 0]
    c = cons.copy()
    c["cap_fechamento_long"] = 1.0
    c["cap_fechamento_short"] = 1.0
    ok = {x.check_id: x for x in run_compliance(
        w, env["model"], c, env["squeeze"], env["assets"], cfg, NAV, None, True, AS_OF, WEEK,
        env["market_w"], True, model_base=env["base"], kappa_f=1.45)}
    assert ok["TRADE_CLOSE_CAPACITY"].passed and ok["TRADE_CLOSE_CAPACITY"].severity == \
        Severity.SOFT
    big_long = w[w > 0].idxmax()
    big_short = w[w < 0].idxmin()
    c.loc[big_long, "cap_fechamento_long"] = 0.5 * float(w[big_long])
    c.loc[big_short, "cap_fechamento_long"] = 0.0      # perna errada: não conta para o short
    bad = {x.check_id: x for x in run_compliance(
        w, env["model"], c, env["squeeze"], env["assets"], cfg, NAV, None, True, AS_OF, WEEK,
        env["market_w"], True, model_base=env["base"], kappa_f=1.45)}
    chk = bad["TRADE_CLOSE_CAPACITY"]
    assert not chk.passed and chk.value == 1.0 and big_long in chk.details
    # Reduções (carteira atual maior) nunca reprovam.
    red = {x.check_id: x for x in run_compliance(
        w * 0.5, env["model"], c, env["squeeze"], env["assets"], cfg, NAV, w, False, AS_OF,
        WEEK, env["market_w"], True, model_base=env["base"], kappa_f=1.45)}
    assert red["TRADE_CLOSE_CAPACITY"].passed
