"""Camada de gestão de risco: vetos de short novo, stop de squeeze por nome, escada de drawdown
sobre a vol, gatilhos de velocidade de perda, κ_F e medidas idiossincráticas (DADOS SIMULADOS)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from cdp.config import FundConfig
from cdp.contracts import DailyPosition, DailyRecord, DailyRisk, Side
from cdp.risk import drawdown as dd
from cdp.risk import gatilhos, idio, limites

CFG = FundConfig()
WEEK = date(2026, 10, 9)
AS_OF = date(2026, 10, 8)


# ----------------------------------------------------------------------------- vetos


def _blocks(earn: dict, ff: dict, mcap: dict, cfg: FundConfig = CFG) -> pd.DataFrame:
    ids = sorted(set(earn) | set(ff) | set(mcap))
    e = pd.DataFrame({"data": [earn.get(i, (None, False))[0] for i in ids],
                      "estimada": [earn.get(i, (None, False))[1] for i in ids],
                      "fonte": "SIMULADO"}, index=ids)
    f = pd.DataFrame({"free_float": [ff.get(i, np.nan) for i in ids], "fonte": "SIMULADO"},
                     index=ids)
    return limites.short_entry_blocks(ids, week=WEEK, earnings=e, free_float=f,
                                      market_cap_usd=pd.Series(mcap, dtype=float), cfg=cfg)


def test_catalyst_window_is_seven_calendar_days():
    assert limites.catalyst_window_days(CFG) == 7
    b = _blocks({"A": (WEEK + timedelta(days=7), False), "B": (WEEK + timedelta(days=8), False),
                 "C": (WEEK, False)},
                {"A": 0.5, "B": 0.5, "C": 0.5}, {"A": 5e9, "B": 5e9, "C": 5e9})
    assert bool(b.loc["A", "catalyst_block"]) and bool(b.loc["C", "catalyst_block"])
    assert not bool(b.loc["B", "catalyst_block"])


def test_estimated_dates_block_with_half_window():
    b = _blocks({"E": (WEEK + timedelta(days=12), True), "F": (WEEK + timedelta(days=15), True)},
                {"E": 0.5, "F": 0.5}, {"E": 5e9, "F": 5e9})
    assert bool(b.loc["E", "catalyst_block"])          # 12 − 7 = 5 ≤ 7
    assert "estimado" in b.loc["E", "motivo"]
    assert not bool(b.loc["F", "catalyst_block"])      # 15 − 7 = 8 > 7


def test_wide_estimate_windows_only_flag():
    ids = ["W"]
    e = pd.DataFrame({"data": [WEEK + timedelta(days=3)], "estimada": [True],
                      "fonte": ["SIMULADO"], "janela_dias": [28]}, index=ids)
    f = pd.DataFrame({"free_float": [0.5], "fonte": ["SIMULADO"]}, index=ids)
    b = limites.short_entry_blocks(ids, week=WEEK, earnings=e, free_float=f,
                                   market_cap_usd=pd.Series({"W": 5e9}), cfg=CFG)
    assert not bool(b.loc["W", "catalyst_block"])
    assert "data_resultado_incerta" in b.loc["W", "dado_ausente"]


def test_missing_date_is_flagged_never_silent():
    b = _blocks({}, {"G": 0.5}, {"G": 5e9})
    assert not bool(b.loc["G", "catalyst_block"])
    assert "data_resultado" in b.loc["G", "dado_ausente"]


def test_free_float_rules_fail_closed_for_small_caps():
    b = _blocks({}, {"LOW": 0.11, "OK": 0.30}, {"LOW": 5e9, "OK": 5e9, "NA_SMALL": 4e8,
                                                  "NA_BIG": 3e9, "NA_NOMCAP": np.nan})
    assert bool(b.loc["LOW", "float_block"]) and not bool(b.loc["OK", "float_block"])
    assert bool(b.loc["NA_SMALL", "float_block"])       # falha fechada
    assert bool(b.loc["NA_NOMCAP", "float_block"])      # porte desconhecido também
    assert not bool(b.loc["NA_BIG", "float_block"])     # grande: só sinalizado
    assert "free_float" in b.loc["NA_BIG", "dado_ausente"]


class _FakeMD:
    is_synthetic = False
    universe = None


def _calendar(monkeypatch, rows: list[dict], squeeze_days: dict | None = None,
              ids: tuple[str, ...] = ("X",)) -> pd.DataFrame:
    """Calendário com uma fonte pública falsa (mesmo filtro ``data ≥ desde`` da real)."""
    import types

    def eventos_corporativos(issuer_ids, desde, ate, *, offline=False, as_of=None,
                             universe=None):
        df = pd.DataFrame(rows)
        return df[(df["data"] >= desde) & (df["data"] <= ate)].reset_index(drop=True) \
            if len(df) else df

    fake = types.SimpleNamespace(eventos_corporativos=eventos_corporativos)
    monkeypatch.setattr(limites, "_publico", lambda: fake)
    sq = (pd.DataFrame({"days_to_earnings": squeeze_days}) if squeeze_days is not None
          else None)
    return limites.earnings_calendar(list(ids), WEEK, AS_OF, sq, _FakeMD())


def _ev(d: date, est: bool, width: int = 0, src: str = "CVM") -> dict:
    return {"issuer_id": "X", "data": d, "tipo": "resultado", "estimada": est, "fonte": src,
            "janela_inicio": d - timedelta(days=width // 2),
            "janela_fim": d + timedelta(days=width // 2)}


def _block_from(earn: pd.DataFrame) -> pd.Series:
    b = limites.short_entry_blocks(["X"], week=WEEK, earnings=earn,
                                   free_float=pd.DataFrame({"free_float": [0.5], "fonte": ["x"]},
                                                           index=["X"]),
                                   market_cap_usd=pd.Series({"X": 5e9}), cfg=CFG)
    return b.loc["X"]


def test_estimate_a_few_days_before_the_decision_still_blocks(monkeypatch):
    """Estimativa (ano anterior + 52 semanas, ±7 dias) 3 dias ANTES da decisão, empresa ainda
    sem divulgar: a janela da estimativa alcança a de veto ⇒ veto (nunca "sem evento")."""
    earn = _calendar(monkeypatch, [_ev(WEEK - timedelta(days=3), True, 14)])
    row = _block_from(earn)
    assert bool(row["catalyst_block"]) and row["motivo"] == "bloqueio_resultado_estimado"
    assert row["dado_ausente"] == ""
    # 8 dias antes: a janela de ±7 dias já não alcança a decisão (irrelevante, sem veto).
    earn = _calendar(monkeypatch, [_ev(WEEK - timedelta(days=8), True, 14)])
    assert not bool(_block_from(earn)["catalyst_block"])


def test_wide_estimate_never_displaces_a_confirmed_date(monkeypatch):
    """Estimativa larga (±14, sem histórico) um dia antes de uma data confirmada dentro da
    janela: a confirmada prevalece e veta."""
    yahoo = (WEEK + timedelta(days=7) - AS_OF).days
    earn = _calendar(monkeypatch, [_ev(WEEK + timedelta(days=6), True, 28, "YAHOO")],
                     squeeze_days={"X": yahoo})
    assert len(earn.loc["X", "candidatos"]) == 2
    assert earn.loc["X", "data"] == WEEK + timedelta(days=7) and not earn.loc["X", "estimada"]
    row = _block_from(earn)
    assert bool(row["catalyst_block"]) and row["motivo"] == "bloqueio_resultado"
    # Só a estimativa larga: sinalizada, sem veto.
    earn = _calendar(monkeypatch, [_ev(WEEK + timedelta(days=6), True, 28, "YAHOO")])
    row = _block_from(earn)
    assert not bool(row["catalyst_block"]) and "data_resultado_incerta" in row["dado_ausente"]


def test_recent_confirmed_result_is_not_flagged_missing(monkeypatch):
    earn = _calendar(monkeypatch, [_ev(WEEK - timedelta(days=10), False)])
    assert bool(earn.loc["X", "resultado_recente"]) and earn.loc["X", "data"] is None
    row = _block_from(earn)
    assert not bool(row["catalyst_block"]) and row["dado_ausente"] == ""
    earn = _calendar(monkeypatch, [])
    assert "data_resultado" in _block_from(earn)["dado_ausente"]


def test_apply_blocks_allows_covering_never_increasing():
    cons = pd.DataFrame({"max_long": 0.04, "max_short": 0.025, "current": [-0.01, 0.0],
                         "reasons": "", "can_short": True}, index=["X", "Y"])
    blk = pd.DataFrame({"catalyst_block": [True, True], "float_block": [False, False],
                        "motivo": ["bloqueio_resultado"] * 2, "dado_ausente": ["", ""]},
                       index=["X", "Y"])
    c, applied = limites.apply_short_entry_blocks(cons, blk)
    assert c.loc["X", "max_short"] == pytest.approx(0.01)  # mantém/cobre, não aumenta
    assert c.loc["Y", "max_short"] == 0.0 and not bool(c.loc["Y", "can_short"])
    assert set(applied) == {"X", "Y"} and "bloqueio_resultado" in c.loc["Y", "reasons"]


def test_squeeze_name_stop_halves_the_short_and_forbids_longs():
    cons = pd.DataFrame({"max_long": 0.04, "max_short": 0.025, "current": [-0.02, 0.01],
                         "reasons": "", "can_long": True}, index=["S", "L"])
    c, applied = limites.apply_squeeze_name_stops(cons, {"S": "stop", "L": "stop"})
    assert c.loc["S", "max_short"] == pytest.approx(0.01) and c.loc["S", "max_long"] == 0.0
    assert applied == {"S": "stop"}                     # long não é afetado por stop de short


NAME_CFG = CFG.with_overrides({"squeeze": {"stop_scope": "name"}})


def _short_rec(d: date, px: float, shares: float = -200.0) -> DailyRecord:
    """Registro com um short em X (ticker XX, USD) ao preço ``px``; ``shares=0`` = zerado."""
    nav = 1_000_000.0
    pos = []
    if shares:
        mv = shares * px
        pos.append(DailyPosition(issuer_id="X", ticker="XX", currency="USD", side=Side.SHORT,
                                 shares=shares, price_local=px, price_usd=px,
                                 market_value_usd=mv, weight=mv / nav, day_pnl_usd=0.0))
    return DailyRecord(date=d, fund_name="CDP", track_record_type="paper", nav_start_usd=nav,
                       nav_end_usd=nav, pnl_usd=0.0, ret=0.0, positions=pos,
                       risk=DailyRisk(gross=0.03, net=-0.03, long_exposure=0.0,
                                      short_exposure=-0.03, n_long=0, n_short=len(pos)),
                       is_synthetic=True, data_notice="DADOS SIMULADOS",
                       prev_record_hash="0" * 64)


# Entrada na sexta a 100; stop na terça (130 = +30%); o preço recua a 120 na quinta (+20%).
_WEEK = [_short_rec(date(2026, 10, 9), 100.0), _short_rec(date(2026, 10, 12), 110.0),
         _short_rec(date(2026, 10, 13), 130.0), _short_rec(date(2026, 10, 14), 125.0),
         _short_rec(date(2026, 10, 15), 120.0)]


def test_mid_week_squeeze_stop_is_cut_at_the_next_rebalance():
    """Stop atingido no meio da semana vale na montagem mesmo com o preço já abaixo do stop na
    véspera: corte à metade das ações do stop e compra vedada até revisão humana."""
    eps = limites.episodios_de_squeeze(_WEEK, NAME_CFG)
    assert len(eps) == 1 and eps[0].data_stop == date(2026, 10, 13)
    assert eps[0].acoes_no_stop == 200.0 and eps[0].corte_pendente
    spec = limites.acoes_de_squeeze(eps, {})["X"]
    assert spec["fracao_maxima_short"] == pytest.approx(0.5) and spec["veto_compra"]
    assert "13/10/2026" in spec["motivo"] and "revisão humana" in spec["motivo"]


def test_squeeze_cut_happens_once_per_episode_and_partial_fills_stay_pending():
    """Depois do corte, o mesmo short ainda em stop (mesmo preço médio de entrada) não é cortado
    de novo; execução parcial deixa o corte pendente, sempre contra as ações do stop."""
    cut = _WEEK + [_short_rec(date(2026, 10, 16), 131.0, -100.0),
                   _short_rec(date(2026, 10, 22), 131.0, -100.0)]
    eps = limites.episodios_de_squeeze(cut, NAME_CFG)
    assert len(eps) == 1 and eps[0].cortado_em == date(2026, 10, 16)
    spec = limites.acoes_de_squeeze(eps, {})["X"]
    assert spec["fracao_maxima_short"] is None and spec["veto_compra"]
    partial = _WEEK + [_short_rec(date(2026, 10, 16), 131.0, -150.0)]
    spec = limites.acoes_de_squeeze(limites.episodios_de_squeeze(partial, NAME_CFG), {})["X"]
    assert spec["fracao_maxima_short"] == pytest.approx(100.0 / 150.0)   # alvo: 100 ações


def test_squeeze_long_veto_survives_the_cover_until_a_human_review():
    """Short zerado: o veto de compra continua até a revisão humana; um stop posterior à
    revisão reabre o veto."""
    closed = _WEEK + [_short_rec(date(2026, 10, 16), 131.0, 0.0)]
    eps = limites.episodios_de_squeeze(closed, NAME_CFG)
    assert eps[0].encerrado_em == date(2026, 10, 16) and not eps[0].corte_pendente
    spec = limites.acoes_de_squeeze(eps, {})
    cons = pd.DataFrame({"max_long": 0.04, "max_short": 0.025, "current": [0.0], "reasons": "",
                         "can_long": True}, index=["X"])
    c, applied = limites.apply_squeeze_name_stops(cons, spec)
    assert c.loc["X", "max_long"] == 0.0 and not bool(c.loc["X", "can_long"])
    assert c.loc["X", "max_short"] == pytest.approx(0.025) and "X" in applied
    assert limites.acoes_de_squeeze(eps, {"X": date(2026, 10, 16)}) == {}
    reopened = closed + [_short_rec(date(2026, 10, 23), 100.0),
                         _short_rec(date(2026, 10, 26), 130.0)]
    eps = limites.episodios_de_squeeze(reopened, NAME_CFG)
    assert [e.data_stop for e in eps] == [date(2026, 10, 13), date(2026, 10, 26)]
    assert limites.acoes_de_squeeze(eps, {"X": date(2026, 10, 16)})["X"]["veto_compra"]


def test_squeeze_reviews_come_from_the_audit_chain():
    """Revisão humana na trilha: o registro-base é o último registro diário ancorado antes dela."""
    from types import SimpleNamespace

    from cdp.workflow.track_record import DAILY_RECORD_EVENT

    def ev(kind, h="", summary=""):
        return SimpleNamespace(event_type=kind, payload_hash=h, summary=summary)

    events = [ev(DAILY_RECORD_EVENT, "h1"), ev(limites.SQUEEZE_REVIEW_EVENT, summary=(
        limites.SQUEEZE_REVIEW_SUMMARY.format(emissor="X", motivo="revisado pelo gestor"))),
        ev(DAILY_RECORD_EVENT, "h2"),
        ev(limites.SQUEEZE_REVIEW_EVENT, summary="Stop de squeeze revisado por humano [Y]: ok")]
    out = limites.revisoes_de_squeeze(events, {"h1": date(2026, 10, 15),
                                               "h2": date(2026, 10, 16)})
    assert out == {"X": date(2026, 10, 15), "Y": date(2026, 10, 16)}
    assert limites.revisoes_de_squeeze(events[1:2], {}) == {}   # sem registro: nada revisado


def test_escalation_requires_two_stops_in_five_sessions():
    sessions = [date(2026, 10, d) for d in (12, 13, 14, 15, 16, 19, 20)]
    one = {"A": [date(2026, 10, 19)]}
    assert not limites.escalar_para_kill_switch(one, sessions, CFG)
    two = {"A": [date(2026, 10, 14)], "B": [date(2026, 10, 20)]}
    assert limites.escalar_para_kill_switch(two, sessions, CFG)
    old = {"A": [date(2026, 10, 12)], "B": [date(2026, 10, 20)]}
    assert not limites.escalar_para_kill_switch(old, sessions, CFG)


# ----------------------------------------------------------------------------- escada


def test_drawdown_multipliers_from_config():
    assert dd.stage_multiplier("soft_stop", CFG) == 0.75
    assert dd.stage_multiplier("hard_stop", CFG) == 0.5
    assert dd.d_max(CFG) == pytest.approx(0.10)
    assert dd.stage_multiplier("stop_out", CFG) == pytest.approx(0.25)
    assert dd.stage_multiplier("normal", CFG) == 1.0
    assert dd.stage_multiplier("desconhecido", CFG) == 1.0


def test_vol_cap_only_in_vol_mode_and_never_compounds():
    assert dd.vol_cap("hard_stop", 0.031, CFG) is None   # legado: gross do mandato
    cfg = CFG.with_overrides({"drawdown": {"risk_reference": "normal_book_vol"}})
    assert dd.vol_cap("soft_stop", 0.031, cfg) == pytest.approx(0.02325)
    assert dd.vol_cap("normal", 0.031, cfg) is None
    assert dd.vol_cap("soft_stop", None, cfg) is None
    # sem memória: mesma referência ⇒ mesmo teto
    assert dd.vol_cap("soft_stop", 0.031, cfg) == dd.vol_cap("soft_stop", 0.031, cfg)
    assert dd.stage(-0.03, cfg) == "soft_stop" and dd.stage(None, cfg) == "desconhecido"


# ----------------------------------------------------------------------------- gatilhos


def _rec(d: date, ret: float, *, fv=0.008, sv=0.03, rv=None, positions=()) -> DailyRecord:
    return DailyRecord(
        date=d, fund_name="CDP", track_record_type="paper", nav_start_usd=1e8,
        nav_end_usd=1e8 * (1 + ret), pnl_usd=1e8 * ret, ret=ret,
        pnl_components={"specific": 1e8 * ret * 0.9, "factor": 1e8 * ret * 0.1},
        positions=list(positions),
        risk=DailyRisk(ex_ante_vol=math.hypot(fv, sv), factor_vol=fv, specific_vol=sv,
                       gross=0.5, net=0.0, long_exposure=0.25, short_exposure=-0.25, n_long=10,
                       n_short=10, realized_vol_21d=rv),
        is_synthetic=True, data_notice="DADOS SIMULADOS", prev_record_hash="0" * 64)


def test_sigma_is_book_based_and_clipped():
    r = _rec(date(2026, 10, 13), 0.0, fv=0.008, sv=0.03)
    k = 1.0
    ex = math.sqrt(k * 0.008 ** 2 + 0.03 ** 2)
    assert gatilhos.sigma_diaria(r, CFG) == pytest.approx(ex / math.sqrt(252))
    tiny = _rec(date(2026, 10, 13), 0.0, fv=0.001, sv=0.002)
    assert gatilhos.sigma_diaria(tiny, CFG) == pytest.approx(0.02 / math.sqrt(252))


def test_loss_velocity_boundaries():
    sd = 0.031 / math.sqrt(252)  # σ ≈ 3,1% a.a.
    days = [date(2026, 10, 13) - timedelta(days=i) for i in range(6)]
    days = [d for d in days if d.weekday() < 5]

    def run(r0: float):
        recs = [_rec(days[0], r0, fv=0.0, sv=0.031)] + [_rec(d, 0.0, fv=0.0, sv=0.031)
                                                        for d in days[1:]]
        return {t["codigo"]: t for t in gatilhos.loss_velocity(recs, CFG)}

    assert "perda_diaria" in run(-3.2 * sd) and "perda_diaria_extrema" not in run(-3.2 * sd)
    hard = run(-5.2 * sd)
    assert hard["perda_diaria_extrema"]["nivel"] == "HARD"
    assert hard["perda_diaria_extrema"]["acao"].startswith(gatilhos.KILL_SWITCH_PREFIX)
    assert run(-0.011)["perda_diaria_extrema"]["nivel"] == "HARD"  # backstop absoluto −1%
    assert run(-2.0 * sd) == {} or set(run(-2.0 * sd)) <= {"janela_incompleta"}


def test_five_day_window_and_gaps_are_not_zero_filled():
    d0 = date(2026, 10, 16)
    recs = [_rec(d0 - timedelta(days=i), -0.005, fv=0.0, sv=0.031) for i in (0, 1, 2, 3, 4)]
    out = {t["codigo"]: t for t in gatilhos.loss_velocity(recs, CFG)}
    assert out["perda_5_pregoes"]["nivel"] == "SOFT"
    short = {t["codigo"] for t in gatilhos.loss_velocity(recs[:3], CFG)}
    assert "janela_incompleta" in short


def _pos(ticker: str, weight: float, repriced: bool = True) -> DailyPosition:
    side = Side.LONG if weight > 0 else Side.SHORT
    return DailyPosition(issuer_id=ticker.split(".")[0], ticker=ticker, currency="USD", side=side,
                         market_value_usd=weight * 1e8, weight=weight, day_pnl_usd=0.0,
                         repriced=repriced)


def test_holiday_scales_threshold_by_sqrt_sessions():
    """Seg 12/10 é feriado na B3 com a NYSE aberta: há registro no dia 12 (só as linhas dos EUA
    reprecificadas) e o retorno de 13/10 das linhas brasileiras carrega dois pregões."""
    sd = 0.031 / math.sqrt(252)

    def book(br_repriced: bool):
        return [_pos("BRA.SA", 0.35, br_repriced), _pos("BRB.SA", -0.35, br_repriced),
                _pos("USA", 0.15), _pos("USB", -0.15)]

    fri = _rec(date(2026, 10, 9), 0.0, fv=0.0, sv=0.031, positions=book(True))
    mon = _rec(date(2026, 10, 12), 0.0, fv=0.0, sv=0.031, positions=book(False))
    tue = _rec(date(2026, 10, 13), -3.5 * sd, fv=0.0, sv=0.031, positions=book(True))
    assert gatilhos.sessoes_de_informacao([tue, mon, fri]) == pytest.approx(0.7 * 2 + 0.3 * 1)
    out = {t["codigo"] for t in gatilhos.loss_velocity([tue, mon, fri], CFG)}
    assert "perda_diaria" not in out  # limite × √1,7 ≈ −3,91σ
    # No dia do feriado só as linhas abertas contam (um pregão).
    assert gatilhos.sessoes_de_informacao([mon, fri]) == pytest.approx(1.0)
    # Sem feriado (todas as linhas reprecificadas no dia 12), o mesmo retorno aciona o alerta.
    mon_open = _rec(date(2026, 10, 12), 0.0, fv=0.0, sv=0.031, positions=book(True))
    out = {t["codigo"] for t in gatilhos.loss_velocity([tue, mon_open, fri], CFG)}
    assert "perda_diaria" in out


def test_corporate_action_detector():
    from cdp.data.synthetic import make_synthetic_market

    md = make_synthetic_market(seed=3, start=date(2026, 1, 2), as_of=date(2026, 10, 2))
    t = md.close.columns[0]
    d = md.close.index[-1].date()
    close = md.close.copy()
    close.iloc[-1, 0] = close.iloc[-2, 0] * 0.5   # grupamento/desdobramento sem ajuste
    md2 = md.__class__(**{**{f: getattr(md, f) for f in md.__dataclass_fields__},
                          "close": close})
    pos = DailyPosition(issuer_id="X", ticker=t, currency="USD", side=Side.LONG, shares=100.0,
                        price_local=1.0, price_usd=1.0, market_value_usd=100.0, weight=0.01,
                        day_pnl_usd=0.0)
    out = {x["codigo"]: x for x in gatilhos.price_jumps(_rec(d, 0.0, positions=[pos]), md2)}
    assert out[f"possivel_evento_societario:{t}"]["nivel"] == "SOFT"
    assert out[f"movimento_extremo:{t}"]["nivel"] == "INFO"
    clean = gatilhos.price_jumps(_rec(d, 0.0, positions=[pos]), md)
    assert clean == []


# ----------------------------------------------------------------------------- κ_F


def test_kappa_formula_golden():
    k26, t = idio.kappa_formula(26, 252, 3, 4.0)
    assert t == pytest.approx(181.8, abs=0.1)
    assert k26 == pytest.approx(1.362, abs=1e-3)
    k30, _ = idio.kappa_formula(30, 252, 3, 4.0)
    assert k30 == pytest.approx(1.434, abs=1e-3)
    nan, _ = idio.kappa_formula(500, 252, 3, 4.0)
    assert math.isnan(nan)


def test_kappa_modes_and_bounds():
    from cdp.risk.types import RiskModel

    rng = np.random.default_rng(1)
    fr = pd.DataFrame(rng.standard_t(5, size=(800, 26)) * 0.01,
                      columns=[f"f{i}" for i in range(26)])
    m = RiskModel(as_of=date(2026, 10, 2), exposures=pd.DataFrame(), factor_cov=pd.DataFrame(),
                  specific_var=pd.Series(dtype=float), factor_returns=fr,
                  specific_returns=pd.DataFrame())
    cfg = CFG.with_overrides({"risk": {"second_order_inflation": 1.45}})
    val, info = idio.kappa_f(m, cfg)
    assert val == 1.45 and info["fonte"] == "config"
    an = cfg.with_overrides({"risk": {"second_order_inflation_mode": "analytic"}})
    val, info = idio.kappa_f(m, an)
    assert 1.2 <= val <= 1.6 and info["fonte"] == "analitico" and info["k"] == 26
    empty = RiskModel(as_of=date(2026, 10, 2), exposures=pd.DataFrame(),
                      factor_cov=pd.DataFrame(), specific_var=pd.Series(dtype=float),
                      factor_returns=pd.DataFrame(), specific_returns=pd.DataFrame())
    val, info = idio.kappa_f(empty, an)
    assert val == 1.45 and info["fonte"] == "fallback"


def test_config_new_keys_are_legacy_inert():
    raw = FundConfig().model_dump(mode="json")
    for sec, key in (("risk", "vol_floor_alpha_scaling"), ("risk", "second_order_inflation_mode"),
                     ("squeeze", "enforce_entry_blocks"), ("squeeze", "stop_scope"),
                     ("drawdown", "risk_reference"), ("alpha", "reresidualize_after_views"),
                     ("risk_model", "linked_groups")):
        assert key not in raw[sec]
    with pytest.raises(ValueError):
        FundConfig().with_overrides({"risk_model": {"linked_groups": {"g": ["A"]}}})
    with pytest.raises(ValueError):
        FundConfig().with_overrides({"risk_model": {"linked_groups": {"g": ["A", "B"],
                                                                      "h": ["B", "C"]}}})
    with pytest.raises(ValueError):
        FundConfig().with_overrides({"risk": {"second_order_inflation_bounds": [1.5, 1.2]}})


# ----------------------------------------------------------------------------- série idio


def test_serie_idio_three_measures():
    from cdp.data.synthetic import make_synthetic_market

    md = make_synthetic_market(seed=3, start=date(2026, 1, 2), as_of=date(2026, 10, 2))
    days = [d.date() for d in md.close.index[-70:]]
    rng = np.random.default_rng(0)
    recs = [_rec(d, float(rng.normal(0, 0.002))) for d in days]
    out = idio.serie_idio(recs, md, CFG)
    assert len(out["datas"]) == 70 and out["ex_ante"][0] is not None
    assert out["realizada_63d"][0] is None and out["realizada_63d"][-1] == pytest.approx(0.9)
    assert out["sem_modelo_63d"][-1] is None or 0.0 <= out["sem_modelo_63d"][-1] <= 1.0
    assert idio.serie_idio([], md, CFG)["datas"] == []


def test_model_free_idio_is_unbiased_under_the_null():
    """Fundo sem exposição aos 11 regressores: o 1 − R² bruto ficaria perto de 1 − k/(n − 1)
    (≈ 82% com n = 63, abaixo do piso só por construção); o ajustado fica perto de 100%, e o
    alerta (piso menos a margem de 95%) quase nunca dispara. Sem 30 graus de liberdade, ausente."""
    rng = np.random.default_rng(7)
    k = len(idio.REGRESSORES_SEM_MODELO)
    vals = []
    for _ in range(300):
        X = pd.DataFrame(rng.standard_normal((63, k)) * 0.01,
                         columns=list(idio.REGRESSORES_SEM_MODELO))
        y = pd.Series(rng.standard_normal(63) * 0.003)
        vals.append(idio._one_minus_r2(y, X))
    v = np.array(vals)
    assert v.mean() > 0.93 and (v >= 0).all() and (v <= 1).all()
    band = idio.banda_sem_modelo(63, k)
    assert band == pytest.approx(0.0824, abs=2e-3)
    assert (v < 0.85 - idio.Z_BANDA_SEM_MODELO * band).mean() < 0.02
    X = pd.DataFrame(rng.standard_normal((41, k)), columns=list(idio.REGRESSORES_SEM_MODELO))
    assert math.isnan(idio._one_minus_r2(pd.Series(rng.standard_normal(41)), X))   # gl = 29
    assert idio.banda_sem_modelo(41, k) is None


# ----------------------------------------------------------------------------- bloco macro


def test_macro_block_recovers_betas_and_preserves_the_factor_block():
    from types import SimpleNamespace

    from cdp.risk.macro import augment_with_macro
    from cdp.risk.types import RiskModel

    rng = np.random.default_rng(7)
    n_days, ids = 600, [f"I{i:02d}" for i in range(30)]
    idx = pd.bdate_range("2024-01-01", periods=n_days)
    fr = pd.DataFrame(rng.normal(0, 0.01, (n_days, 3)), index=idx, columns=["market", "a", "b"])
    oil = rng.normal(0, 0.02, n_days)
    true_b = np.where(np.arange(30) < 10, 0.5, 0.0)          # 10 petroleiras
    resid = pd.DataFrame(np.outer(oil, true_b) + rng.normal(0, 0.015, (n_days, 30)),
                         index=idx, columns=ids)
    F = pd.DataFrame(np.cov(fr.to_numpy().T) * 252, index=fr.columns, columns=fr.columns)
    expo = pd.DataFrame(rng.normal(0, 1, (30, 3)), index=ids, columns=fr.columns)
    D = pd.Series(resid.var().to_numpy() * 252, index=ids)
    model = RiskModel(as_of=idx[-1].date(), exposures=expo, factor_cov=F, specific_var=D,
                      factor_returns=fr, specific_returns=resid,
                      factor_groups={"market": "market", "a": "style", "b": "style"})
    px = pd.DataFrame({"BZ=F": 80 * np.cumprod(1 + oil)}, index=idx)
    md = SimpleNamespace(benchmarks=px)
    assert augment_with_macro(model, md, CFG) is model         # legado: sem fatores macro
    cfg = CFG.with_overrides({"risk_model": {"macro_factors": ["BZ=F", "XX=F"]}})
    sector = pd.Series(["Energy"] * 10 + ["Other"] * 20, index=ids)
    out = augment_with_macro(model, md, cfg, SimpleNamespace(assets=pd.DataFrame(
        {"sector": sector})))
    b = out.exposures["macro:BZ=F"]
    assert b[:10].mean() == pytest.approx(0.5, abs=0.05)
    assert b[10:].abs().mean() < 0.05
    np.testing.assert_allclose(out.factor_cov.loc[F.index, F.columns].to_numpy(), F.to_numpy())
    assert np.linalg.eigvalsh(out.factor_cov.to_numpy()).min() >= -1e-12
    assert (out.specific_var <= D + 1e-15).all() and (out.specific_var >= 0.5 * D - 1e-15).all()
    assert out.specific_var[:10].mean() < D[:10].mean()        # parte explicada saiu do específico
    assert out.factor_groups["macro:BZ=F"] == "macro"
    assert out.meta["macro"]["ausentes"] == ["XX=F"]
    from cdp.risk.analytics import risk_decomposition

    w = pd.Series(0.01, index=ids[:10])
    assert "macro" in risk_decomposition(w, out).by_group
    assert "macro" not in risk_decomposition(w, model).by_group
