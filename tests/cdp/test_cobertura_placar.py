"""Placar de acertos: TPMET12/TPMETANY calculados à mão, alvo baixista atingido na queda,
censura de Kaplan–Meier, IC perfeito ≈ 1 e ruído ≈ 0, Newey–West e Wilson."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from cdp.cobertura.placar import (
    calcular_placar,
    erro_assinado,
    kaplan_meier,
    newey_west_t,
    spearman,
    tpmet12,
    tpmetany,
    wilson,
)


def test_tpmet12_and_any_by_hand():
    assert tpmet12(100, 120, 125) and not tpmet12(100, 120, 110)
    # alvo baixista: atingido na queda (d = −1)
    assert tpmet12(100, 80, 75) and not tpmet12(100, 80, 90)
    assert tpmetany(100, 120, [105, 121, 110]) and not tpmetany(100, 120, [105, 119, 110])
    assert tpmetany(100, 80, [95, 79, 90])
    assert erro_assinado(110, 100) == pytest.approx(0.10)


def test_kaplan_meier_with_censoring():
    km = kaplan_meier([10, 20, 20, 30, 40], [True, True, False, False, True])
    # t=10: 4/5; t=20: × (1 − 1/4); t=40: × (1 − 1/1)
    assert km[0] == (10.0, pytest.approx(0.8))
    assert km[1] == (20.0, pytest.approx(0.6))
    assert km[2] == (40.0, pytest.approx(0.0))


def test_ic_perfect_signal_and_noise():
    rng = np.random.default_rng([11, 2])
    x = rng.normal(size=200)
    assert spearman(x, x * 2 + 1) == pytest.approx(1.0)
    ics = [spearman(rng.normal(size=100), rng.normal(size=100)) for _ in range(200)]
    assert abs(float(np.mean(ics))) < 0.02


def test_newey_west_equals_ols_without_lags_and_shrinks_with_autocorrelation():
    rng = np.random.default_rng([5, 3])
    x = rng.normal(0.02, 0.05, 300)
    t0 = newey_west_t(x, 0)
    ols = x.mean() / (x.std(ddof=0) / math.sqrt(len(x)))
    assert t0 == pytest.approx(ols, rel=1e-9)
    e = np.zeros(300)
    for i in range(1, 300):  # AR(1) positivo ⇒ erro-padrão maior, t menor
        e[i] = 0.8 * e[i - 1] + rng.normal(0, 0.05)
    y = 0.02 + e
    assert newey_west_t(y, 8) < newey_west_t(y, 0)


def test_wilson_bounds():
    lo, hi = wilson(30, 100)
    assert 0.22 < lo < 0.30 < hi < 0.38
    assert wilson(0, 10)[0] == 0.0 and wilson(10, 10)[1] == 1.0
    assert wilson(0, 0) is None


def _ev(seq, iid, d, preco, tp, rating="Neutro", alpha_rel=0.0):
    return {"seq": seq, "issuer_id": iid, "as_of": d.isoformat(), "linha": f"{iid}.SA",
            "preco_ref": {"fechamento": preco}, "alvo": {"base": tp}, "rating": rating,
            "alpha_rel": alpha_rel, "vencimento": (d + timedelta(days=365)).isoformat()}


def test_placar_from_ledger_events():
    d0 = date(2026, 10, 8)
    evs = []
    seq = 0
    # 3 previsões: atingida, não atingida, baixista atingida
    for iid, p0, tp, caminho in [("A", 100, 120, [110, 125]), ("B", 50, 60, [52, 55]),
                                 ("C", 40, 30, [35, 29])]:
        evs.append(_ev(seq, iid, d0, p0, tp))
        seq += 1
        for j, p in enumerate(caminho):
            evs.append(_ev(seq, iid, d0 + timedelta(days=200 + 165 * j), p, tp))
            seq += 1
    pl = calcular_placar(evs, None, date(2027, 10, 30))
    assert pl["n_vencidas"] == 3
    assert pl["tpmet12"]["k"] == 2  # A (125 ≥ 120) e C (29 ≤ 30); B não
    assert pl["tpmetany"]["k"] == 2
    assert pl["em_maturacao"] is True and pl["exibir_taxas"] is False  # N < 20
    vazio = calcular_placar([], None, d0)
    assert vazio["n_previsoes"] == 0 and vazio["tpmet12"]["taxa"] is None


def test_weekly_ic_perfect_ranking():
    d0 = date(2026, 10, 8)
    evs = []
    seq = 0
    rng = np.random.default_rng([1, 9])
    for w in range(6):
        d = d0 + timedelta(days=7 * w)
        for i in range(15):
            # α_rel ordena exatamente o retorno da semana seguinte
            preco = 100 * (1 + 0.01 * i) ** w
            evs.append(_ev(seq, f"I{i:02d}", d, preco, preco * 1.1, alpha_rel=float(i) + rng.normal(0, 1e-6)))
            seq += 1
    pl = calcular_placar(evs, None, d0 + timedelta(days=60))
    assert pl["ic_resumo"]["semanas"] == 5
    assert pl["ic_resumo"]["media"] == pytest.approx(1.0)


def _ev2(seq, iid, d, preco, alpha_rel, pais, setor, ret=None, desde=None, parcial=False, fator=None):
    e = _ev(seq, iid, d, preco, preco * 1.1, alpha_rel=alpha_rel)
    e.update({"pais": pais, "setor": setor, "parcial": parcial})
    if ret is not None:
        e["preco_ref"]["retorno_total_usd"] = {"desde": desde.isoformat(), "valor": ret}
    if fator is not None:
        e["preco_ref"]["fator_split"] = {"desde": desde.isoformat(), "valor": fator}
    return e


def test_country_only_move_has_no_residual_ic():
    # α_rel alto só no Brasil e o Brasil sobe 5% inteiro: o IC bruto seria alto, o residual ≈ 0
    d0 = date(2026, 10, 9)
    rng = np.random.default_rng([4, 2])
    evs, seq = [], 0
    for w in range(12):
        d = d0 + timedelta(days=7 * w)
        for i in range(40):
            pais = "BR" if i < 20 else "MX"
            ar = (0.2 if pais == "BR" else -0.2) + float(rng.normal(0, 0.01))
            ret = None if w == 0 else (0.05 if pais == "BR" else -0.05) + float(rng.normal(0, 0.02))
            evs.append(_ev2(seq, f"I{i:02d}", d, 100.0, ar, pais, "Materials", ret, d - timedelta(days=7)))
            seq += 1
    pl = calcular_placar(evs, None, d0 + timedelta(days=90))
    assert pl["ic_resumo"]["semanas"] == 11
    assert abs(pl["ic_resumo"]["media"]) < 0.1
    # sem residualização (grupos ausentes) o mesmo painel teria IC alto
    from cdp.cobertura.placar import residualizar, spearman

    xs = [0.2] * 20 + [-0.2] * 20
    rs = [0.05] * 20 + [-0.05] * 20
    assert spearman(xs, rs) > 0.8
    assert np.allclose(residualizar(rs, ["BR|M"] * 20 + ["MX|M"] * 20, ["BR"] * 20 + ["MX"] * 20), 0.0)


def test_partial_run_between_fridays_keeps_the_weekly_observation():
    d0 = date(2026, 10, 9)
    evs, seq = [], 0
    for i in range(15):
        evs.append(_ev2(seq, f"I{i:02d}", d0, 100.0, float(i), "BR", "Energy"))
        seq += 1
    for i in range(3):  # execução parcial após resultados (terça)
        evs.append(_ev2(seq, f"I{i:02d}", d0 + timedelta(days=4), 100.0, float(i), "BR", "Energy", parcial=True))
        seq += 1
    d1 = d0 + timedelta(days=7)
    for i in range(15):
        evs.append(_ev2(seq, f"I{i:02d}", d1, 100.0 + i, float(i), "BR", "Energy", 0.01 * i, d0))
        seq += 1
    pl = calcular_placar(evs, None, d1)
    assert len(pl["ic_semanal"]) == 1 and pl["ic_semanal"][0]["data"] == d0.isoformat()
    assert pl["ic_semanal"][0]["ic"] == pytest.approx(1.0)


def test_split_during_window_rescales_the_price_path():
    # alvo de 120 sobre 100; desdobramento 2:1 depois: fechamento 62 ≡ 124 na base da emissão
    d0 = date(2026, 10, 9)
    evs = [_ev(0, "A", d0, 100.0, 120.0)]
    e1 = _ev(1, "A", d0 + timedelta(days=200), 62.0, 60.0)
    e1["preco_ref"]["fator_split"] = {"desde": d0.isoformat(), "valor": 2.0}
    e2 = _ev(2, "A", d0 + timedelta(days=366), 61.0, 60.0)
    e2["preco_ref"]["fator_split"] = {"desde": e1["as_of"], "valor": 1.0}
    pl = calcular_placar(evs + [e1, e2], None, date(2027, 11, 1))
    assert pl["tpmetany"]["k"] == 1          # 62 × 2 = 124 ≥ 120
    assert pl["tpmet12"]["k"] == 1           # 61 × 2 = 122 ≥ 120 no vencimento
    sem = calcular_placar([evs[0], {**e1, "preco_ref": {"fechamento": 62.0}},
                           {**e2, "preco_ref": {"fechamento": 61.0}}], None, date(2027, 11, 1))
    assert sem["tpmetany"]["k"] == 0          # sem o fator, o desdobramento pareceria queda de 38%
