"""Decisão semanal com a construção nova: fallback que nunca interrompe, kill switch que só
reduz, carteira mantida com violações passivas visíveis, vetos de short, stop de squeeze por
nome, escada de drawdown sobre a vol e o bloco ``overrides["risco"]`` (DADOS SIMULADOS)."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from cdp.config import FundConfig
from cdp.contracts import ResearchPack, Severity, View, ViewSource
from cdp.data.synthetic import make_synthetic_market
from cdp.portfolio.optimizer import OptimizationError
from cdp.workflow import weekly
from cdp.workflow.weekly import PMDecisionBundle, prepare_week, run_weekly_decision

WEEK = date(2026, 10, 5)

ACTIVE = {
    "risk": {"max_factor_risk_share": 0.10, "idio_share_goal": 0.90, "idio_share_floor": 0.85,
             "factor_risk_basis": "achieved", "factor_risk_aversion_multiplier": 5.0,
             "second_order_inflation": 1.45, "idio_gate_models": ["decisao", "base"],
             "vol_floor_alpha_scaling": False,
             "operational": {"beta": 0.02, "style": 0.05, "sector_net": 0.015,
                             "country_net": {"BR": 0.01, "MX": 0.01, "*": 0.005},
                             "commodity_beta": 0.01}},
    "squeeze": {"enforce_entry_blocks": True, "stop_scope": "name"},
    "drawdown": {"risk_reference": "normal_book_vol"},
    "alpha": {"reresidualize_after_views": True},
    "risk_model": {"history_days": 300},
}


@pytest.fixture(scope="module")
def md():
    return make_synthetic_market(seed=7, start=date(2025, 3, 3), as_of=date(2026, 10, 2))


@pytest.fixture(scope="module")
def cfgs():
    legacy = FundConfig().with_overrides({"risk_model": {"history_days": 300}})
    return legacy, FundConfig().with_overrides(ACTIVE)


def _pack(ctx, views=()):
    return ResearchPack(week=WEEK, snapshot_id=ctx.snapshot_id, provider="demo", mind="demo",
                        is_synthetic=True, views=list(views))


PM = PMDecisionBundle(views=[], overrides={}, journal=None, pm_output_hash="0" * 64)


@pytest.fixture(scope="module")
def inception(md, cfgs):
    _legacy, active = cfgs
    ctx = prepare_week(md, active, WEEK, drawdown=0.0, themes={})
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1)
    return ctx, out


def _book(out) -> dict[str, float]:
    w: dict[str, float] = {}
    for p in out.final.positions:
        w[p.issuer_id] = w.get(p.issuer_id, 0.0) + p.weight
    return w


# ----------------------------------------------------------------------------- P0-1


def test_inception_decision_with_active_methodology(inception):
    ctx, out = inception
    p = out.final
    assert out.path_taken in ("cdp", "cdp-restricoes") and not p.hard_failures
    r = p.overrides["risco"]
    assert r["idio_decisao"] >= 0.85 and r["idio_base"] >= 0.85
    grupos = r["por_grupo"]
    assert sum(v for v in grupos.values() if v is not None) == pytest.approx(1.0, abs=1e-4)
    text = json.dumps(p.overrides, ensure_ascii=False)
    assert "NaN" not in text and "Infinity" not in text
    for key in ("risco", "formulacao", "construcao"):
        assert key in p.overrides
    assert p.overrides["formulacao"]["modelo_risco"]["n_fatores"] == len(ctx.model.factor_names)
    assert "DADOS SIMULADOS" in p.data_notice
    from cdp.risk.idio import decomposicao_decisao

    dec = decomposicao_decisao(p)
    assert dec["disponivel"] and dec["idio_base"] == r["idio_base"]


def test_failures_fall_through_to_hold_without_exceptions(md, cfgs, monkeypatch):
    _legacy, active = cfgs
    ctx = prepare_week(md, active, WEEK, drawdown=0.0, themes={})
    real = weekly.build_proposal

    def flaky(ctx_, **kw):
        if kw.get("label") == "cdp":
            raise OptimizationError("Otimização falhou: inviável.\nlinha 2", codigo="INVIAVEL")
        return real(ctx_, **kw)

    monkeypatch.setattr(weekly, "build_proposal", flaky)
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1)
    assert out.path_taken == "cdp-restricoes"
    first = out.attempts[0]
    assert first["label"] == "cdp" and first["erro"] == "INVIAVEL: Otimização falhou: inviável."
    assert first["hard"] == ["OPTIMIZATION_FAILED"]

    def broken(*a, **k):
        raise OptimizationError("Otimização falhou: inviável.", codigo="INVIAVEL")

    monkeypatch.setattr(weekly, "build_proposal", real)
    monkeypatch.setattr(weekly, "optimize", broken)
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1)
    assert out.path_taken == "manter"
    assert out.shadow_quant.proposal_id.endswith("sombra-quant")
    assert out.shadow_quant.optimizer.status == "hold"
    assert out.decision.proposal_hash == out.final.proposal_hash()
    assert all(a.get("erro", "").startswith("INVIAVEL") for a in out.attempts)


def test_hold_of_a_drifted_book_carries_passive_info_checks(md, cfgs, inception, monkeypatch):
    _legacy, active = cfgs
    _ctx, out0 = inception
    w = {k: v * 3.0 for k, v in _book(out0).items()}  # carteira derivada fora dos limites
    ctx = prepare_week(md, active, WEEK, drawdown=0.0, themes={}, current_drifted_w=w)

    def broken(*a, **k):
        raise OptimizationError("Otimização falhou.", codigo="INVIAVEL")

    monkeypatch.setattr(weekly, "optimize", broken)
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1)
    assert out.path_taken == "manter"
    passive = [c for c in out.final.compliance if c.check_id.startswith("PASSIVO:")]
    assert passive and all(c.severity == Severity.INFO for c in passive)
    assert not out.final.hard_failures


# ----------------------------------------------------------------------------- P0-0


@pytest.mark.parametrize("which", ["legacy", "active"])
def test_kill_switch_on_a_non_inception_week(md, cfgs, inception, which):
    legacy, active = cfgs
    cfg = legacy if which == "legacy" else active
    _ctx, out0 = inception
    w0 = _book(out0)
    ctx = prepare_week(md, cfg, WEEK, drawdown=0.0, themes={}, current_drifted_w=w0)
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1, kill_switch=True)
    assert out.path_taken in ("reduzir-risco", "manter")
    if which == "active":
        assert out.path_taken == "reduzir-risco"
        w = _book(out)
        for iid, v in w.items():
            assert abs(v) <= abs(w0.get(iid, 0.0)) + 1e-6 and v * w0.get(iid, 0.0) >= 0
        vol0 = weekly.current_book_vol(ctx)
        assert out.final.risk.ex_ante_vol <= 0.5 * vol0 + 1e-6
        assert out.final.overrides["reduce_only"] is True
        assert "max_weekly_turnover" not in out.final.overrides


# ----------------------------------------------------------------------------- vetos e stops


def test_entry_blocks_reach_the_constraints(md, cfgs, inception):
    ctx, out = inception
    assert ctx.entry_blocks is not None and len(ctx.entry_blocks) == len(ctx.model.assets)
    cons, info = weekly.construction_constraints(ctx, None, 0.045)
    assert "entry_block" in cons.columns and "vetos_short" in info
    blocked = cons.index[cons["entry_block"].astype(bool)]
    assert (cons.loc[blocked, "max_short"] <= 1e-12).all()  # inception: nenhum short vetado
    w = _book(out)
    assert all(w.get(i, 0.0) >= -1e-9 for i in blocked)


def test_squeeze_stop_is_applied_by_name(md, cfgs, inception):
    _legacy, active = cfgs
    _ctx, out0 = inception
    w0 = _book(out0)
    short = min(w0, key=w0.get)
    assert w0[short] < 0
    ctx = prepare_week(md, active, WEEK, drawdown=0.0, themes={}, current_drifted_w=w0,
                       squeeze_stops={short: "stop de squeeze (teste)"})
    cons, info = weekly.construction_constraints(ctx, None, 0.045)
    assert cons.loc[short, "max_short"] == pytest.approx(0.5 * abs(w0[short]))
    assert cons.loc[short, "max_long"] == 0.0 and info["stops_squeeze"] == {
        short: "stop de squeeze (teste)"}


def test_drawdown_ladder_caps_vol_on_the_real_book(md, cfgs, inception):
    _legacy, active = cfgs
    _ctx, out0 = inception
    w0 = _book(out0)
    ctx = prepare_week(md, active, WEEK, drawdown=-0.055, themes={}, current_drifted_w=w0)
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1)
    esc = out.final.overrides["risco"]["escada"]
    assert esc["estagio"] == "hard_stop" and esc["multiplicador"] == 0.5
    assert out.final.risk.ex_ante_vol <= esc["sigma_teto"] * (1 + 1e-4) + 1e-9
    assert not out.final.hard_failures


# ----------------------------------------------------------------------------- alpha


def test_alpha_is_reresidualized_after_views(md, cfgs):
    from cdp.alpha.combine import reresidualize, wls_weights

    _legacy, active = cfgs
    ctx = prepare_week(md, active, WEEK, drawdown=0.0, themes={})
    ids = ctx.alpha.alpha.dropna().index[:6]
    views = [View(issuer_id=i, source=ViewSource.PM, score=2 if k % 2 else -2, confidence=0.8,
                  rationale="Visão de teste.", author="gestor")
             for k, i in enumerate(ids)]
    from cdp.alpha.views import apply_views

    tilted, _c, _l = apply_views(ctx.alpha.alpha, views, ctx.model.specific_vol, active)
    pure, notes = reresidualize(tilted, ctx.model)
    X = ctx.model.exposures.reindex(pure.dropna().index).astype(float)
    wts = wls_weights(ctx.model.specific_var).reindex(X.index).to_numpy()
    resid = X.to_numpy().T @ (wts * pure.dropna().to_numpy())
    assert np.abs(resid).max() < 1e-8 * max(1.0, float(np.abs(tilted.dropna()).sum()))
    assert pure.isna().equals(tilted.isna())
    assert any("Após as visões" in n for n in notes)


def test_legacy_proposal_has_no_new_blocks(md, cfgs):
    legacy, _active = cfgs
    ctx = prepare_week(md, legacy, WEEK, drawdown=0.0, themes={})
    assert ctx.entry_blocks is None and ctx.kappa_f == 1.0
    b = weekly.build_proposal(ctx, views=[], overrides={"vol_target": 0.045},
                              research_hash="0" * 64, version=1, label="quant")
    assert set(b.proposal.overrides) == {"label", "vol_target"}
    from cdp.risk.idio import decomposicao_decisao

    assert decomposicao_decisao(b.proposal)["disponivel"] is False
    assert isinstance(pd.Series(dtype=float), pd.Series)


def test_every_attempt_override_set_resolves(md, cfgs, inception):
    """Todo conjunto de overrides montado pela decisão (inclusive o do kill switch) passa na
    validação do otimizador, na inception e fora dela (nunca um ``ValueError`` na decisão)."""
    from cdp.portfolio.optimizer import _resolve_settings
    from cdp.workflow.autonomy import effective_vol_target

    _ctx0, out0 = inception
    w0 = _book(out0)
    for cfg in cfgs:
        for current in (None, w0):
            ctx = prepare_week(md, cfg, WEEK, drawdown=0.0, themes={}, current_drifted_w=current)
            vt = effective_vol_target(cfg, None, 0)
            pm_ov = {"vol_target": vt, "gross_max": 1.0}
            for kill in (False, True):
                for _label, _views, ov, _why in weekly.attempt_specs(
                        ctx, _pack(ctx), PM, vt_default=vt, pm_ov=pm_ov, kill_switch=kill):
                    _resolve_settings(cfg, ov, ctx.inception)


# ----------------------------------------------------------------------------- congelados


def _patch_execution(monkeypatch, frozen: dict[str, str], cap_usd: float = 1e9) -> None:
    """Capacidade de fechamento e emissores congelados simulados (execução de D)."""
    from datetime import UTC, datetime

    import cdp.portfolio.execucao as ex

    jan = ex.JanelaExecucao(sessao=WEEK, abertos={}, fechamentos={}, corte_moc={},
                            prazo_decisao=datetime(2026, 10, 5, 18, tzinfo=UTC),
                            fechamento_antecipado=False, multiplicador_capacidade=1.0)
    monkeypatch.setattr(ex, "janela_execucao", lambda s, c: jan)
    monkeypatch.setattr(ex, "capacidade_fechamento_usd",
                        lambda lines, md, j, c, *, lado: pd.Series(cap_usd, index=lines.index))
    monkeypatch.setattr(ex, "emissores_congelados", lambda sides, atual, j, c: dict(frozen))


@pytest.fixture(scope="module")
def exec_cfg(cfgs):
    _legacy, active = cfgs
    return active.with_overrides({"execution": {}})


def test_frozen_name_with_squeeze_stop_defers_the_stop(md, exec_cfg, inception, monkeypatch):
    """Short congelado (mercado local fechado) e em stop de squeeze: a posição fica como está,
    o stop fica pendente (INFO) e o resto do livro é rebalanceado normalmente."""
    _ctx, out0 = inception
    w0 = _book(out0)
    short = min(w0, key=w0.get)
    _patch_execution(monkeypatch, {short: "mercado local fechado"})
    ctx = prepare_week(md, exec_cfg, WEEK, drawdown=0.0, themes={}, current_drifted_w=w0,
                       squeeze_stops={short: "stop de squeeze (teste)"})
    cons, info = weekly.construction_constraints(ctx, None, 0.045)
    assert cons.loc[short, "max_short"] == pytest.approx(abs(w0[short]))
    assert cons.loc[short, "max_trade"] == 0.0 and cons.loc[short, "origem_short"] == "congelado"
    assert info["stops_squeeze_pendentes"] == {short: "stop de squeeze (teste)"}
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1)
    assert out.path_taken in ("cdp", "cdp-restricoes") and not out.final.hard_failures
    assert _book(out)[short] == pytest.approx(w0[short], abs=1e-7)
    ids = {c.check_id: c for c in out.final.compliance}
    assert ids["SQUEEZE_STOP_PENDING"].severity == Severity.INFO
    assert "TRADE_CLOSE_CAPACITY" in ids and "CLOSED_MARKETS_FROZEN" in ids
    cons_pub = out.final.overrides["construcao"]
    assert cons_pub["stops_squeeze_pendentes"] == {short: "stop de squeeze (teste)"}
    assert out.final.overrides["formulacao"]["limites_por_nome"][short]["origem"] == "congelado"


def test_frozen_name_excluded_by_the_manager_stays_put(md, exec_cfg, inception, monkeypatch):
    _ctx, out0 = inception
    w0 = _book(out0)
    big = max(w0, key=lambda k: abs(w0[k]))
    _patch_execution(monkeypatch, {big: "mercado local fechado"})
    ctx = prepare_week(md, exec_cfg, WEEK, drawdown=0.0, themes={}, current_drifted_w=w0)
    pm = PMDecisionBundle(views=[], overrides={"exclude_issuers": [big]}, journal=None,
                          pm_output_hash="0" * 64)
    out = run_weekly_decision(ctx, _pack(ctx), pm, version=1)
    assert out.path_taken in ("cdp", "cdp-restricoes")
    assert _book(out)[big] == pytest.approx(w0[big], abs=1e-7)


def test_kill_switch_with_a_closed_market_reduces_what_can_trade(md, exec_cfg, inception,
                                                                 monkeypatch):
    """Kill switch com metade do gross congelado: a redução recai sobre as posições
    negociáveis (nunca "manter" por contradição com as congeladas)."""
    _ctx, out0 = inception
    w0 = _book(out0)
    order = sorted(w0, key=lambda k: -abs(w0[k]))
    frozen = {k: "mercado local fechado" for k in order[::2]}
    _patch_execution(monkeypatch, frozen)
    ctx = prepare_week(md, exec_cfg, WEEK, drawdown=0.0, themes={}, current_drifted_w=w0)
    fb = weekly.frozen_book(ctx)
    assert fb["gross"] > 0.4 * sum(abs(v) for v in w0.values())
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1, kill_switch=True)
    assert out.path_taken == "reduzir-risco"
    w = _book(out)
    for iid, v0 in w0.items():
        v = w.get(iid, 0.0)
        if iid in frozen:
            assert v == pytest.approx(v0, abs=1e-7)
        else:
            assert abs(v) <= abs(v0) + 1e-7 and v * v0 >= 0
    vol0 = weekly.current_book_vol(ctx)
    cap = max(0.5 * vol0, fb["vol"] * (1 + weekly.FROZEN_MARGIN))
    assert out.final.overrides["vol_cap"] == pytest.approx(cap, rel=1e-5)
    gross0 = sum(abs(v) for v in w0.values())
    assert out.final.risk.gross < gross0 and out.final.risk.ex_ante_vol < vol0
    floor_step = any("menor nível viável" in n for n in out.final.optimizer.notes)
    # Os tetos do kill switch valem, salvo quando as posições congeladas e o mandato (net)
    # impedem: aí sobem só até o menor risco viável (registrado), nunca acima do atual.
    assert out.final.risk.ex_ante_vol <= cap * (1 + 1e-5) or floor_step


# ----------------------------------------------------------------------------- escada × kill


def test_kill_switch_and_hard_stop_take_the_stricter_cap_not_the_product(md, cfgs, inception):
    _legacy, active = cfgs
    _ctx, out0 = inception
    w0 = _book(out0)
    ctx = prepare_week(md, active, WEEK, drawdown=-0.055, themes={}, current_drifted_w=w0)
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1, kill_switch=True)
    assert out.path_taken == "reduzir-risco" and not out.final.hard_failures
    esc = out.final.overrides["risco"]["escada"]
    vol0 = weekly.current_book_vol(ctx)
    kill_cap = 0.5 * vol0
    assert esc["fonte_sigma_ref"] == "mesma tentativa no estágio normal"
    assert esc["sigma_ref"] > kill_cap * 1.05      # σ_ref é o livro normal, não o reduzido
    expected = min(kill_cap, 0.5 * esc["sigma_ref"])
    assert esc["sigma_teto"] == pytest.approx(expected, rel=1e-5)
    assert esc["regra_vinculante"] in ("kill switch", "escada de drawdown")
    assert out.final.risk.ex_ante_vol <= esc["sigma_teto"] * (1 + 1e-4)
    assert out.final.risk.ex_ante_vol >= 0.25 * vol0  # nunca o produto dos dois cortes (≈0,25×)


def test_kill_switch_hard_stop_with_an_empty_book_never_crashes(md, cfgs):
    _legacy, active = cfgs
    ctx = prepare_week(md, active, WEEK, drawdown=-0.055, themes={},
                       current_drifted_w={"SIM001": 0.0})
    assert not ctx.inception and weekly.current_book_vol(ctx) is None
    out = run_weekly_decision(ctx, _pack(ctx), PM, version=1, kill_switch=True)
    assert out.path_taken in ("reduzir-risco", "manter")
    assert out.decision is not None


@pytest.mark.parametrize("dd", [-0.03, -0.055, -0.08])
def test_ladder_override_sets_resolve_for_every_stage(md, cfgs, inception, dd):
    """Toda combinação estágio × σ_ref (ausente, zero, não finito, positivo) × carteira
    (vazia ou não) × kill switch gera overrides válidos para o otimizador."""
    from cdp.portfolio.optimizer import _resolve_settings
    from cdp.risk.drawdown import stage

    _legacy, active = cfgs
    _ctx0, out0 = inception
    for current in ({"SIM001": 0.0}, _book(out0)):
        ctx = prepare_week(md, active, WEEK, drawdown=dd, themes={}, current_drifted_w=current)
        stg = stage(dd, active)
        for kill in (False, True):
            for _label, _views, ov, _why in weekly.attempt_specs(
                    ctx, _pack(ctx), PM, vt_default=0.045, pm_ov={"vol_target": 0.045},
                    kill_switch=kill):
                for ref in (None, 0.0, float("nan"), 0.031):
                    ov2, esc, note = weekly.ladder_overrides(ctx, ov, stg, ref, "teste")
                    _resolve_settings(active, ov2, ctx.inception)
                    assert "escada" in esc and note
                    if ov2.get("vol_cap") is not None:
                        assert ov2["vol_cap"] > 0


# ----------------------------------------------------------------------------- base publicada


def test_published_factor_share_uses_the_gate_basis(inception):
    """Memo, tese e referência publicam a participação fatorial na base do gate (κ_F, modelo
    que vincula) — a mesma do limite —, nunca a do RiskSummary sem κ_F ao lado do limite."""
    from cdp.risk.idio import base_vinculante
    from cdp.workflow.tese_analise import _factor_share

    _ctx, out = inception
    p = out.final
    r = p.overrides["risco"]
    basis = base_vinculante(r)
    worst = min(("decisao", "base"), key=lambda k: r[f"idio_{k}"])
    assert basis["modelo"] == r["modelo_vinculante"] == worst
    assert basis["fatorial"] == pytest.approx(1 - r[f"idio_{worst}"])
    grupos = r["por_grupo_base"] if worst == "base" else r["por_grupo"]
    assert basis["por_grupo"] == grupos
    assert sum(v for v in grupos.values() if v is not None) == pytest.approx(1.0, abs=1e-4)
    assert _factor_share(p) == pytest.approx(basis["fatorial"])
    assert basis["fatorial"] > p.risk.factor_risk_share  # κ_F e o modelo que vincula
    assert f"com κ_F no {basis['rotulo']}" in p.memo_markdown
