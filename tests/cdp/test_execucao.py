"""Execução no leilão de fechamento: fórmula de capacidade, volume desconhecido, mercados
fechados, congelamento e roteamento por ADR, fechamento antecipado, preenchimento, custos,
implementation shortfall, período de montagem e estresse de liquidez (DADOS SIMULADOS)."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest
from test_calendar import ativado

from cdp.contracts import BookedPosition, BookEntry
from cdp.data.synthetic import make_synthetic_market
from cdp.portfolio.costs import custos_fechamento
from cdp.portfolio.execucao import (
    OrdemLinha,
    adv_fechamento_usd,
    capacidade_fechamento_usd,
    capacidade_por_janela,
    categoria_da_linha,
    emissores_congelados,
    estatistica_t,
    estresse_liquidez,
    fechamentos_necessarios,
    janela_execucao,
    janela_regular,
    lado_da_ordem,
    mic_da_linha,
    preencher,
    preenchimentos_esperados,
    rotear_linhas,
    shortfall,
    tabela_capacidade,
    trajetoria_montagem,
    valor_negociado_usd,
)
from cdp.portfolio.trades import build_trades

FRI = date(2024, 11, 8)           # sexta comum
B3_CLOSED = date(2024, 11, 15)    # sexta, B3 fechada (Proclamação da República), NYSE aberta
EARLY = date(2024, 11, 29)        # sexta pós-Ação de Graças: NYSE fecha às 13h00


@pytest.fixture(scope="module")
def md():
    return make_synthetic_market(seed=7, start=date(2023, 1, 2), as_of=date(2024, 12, 2))


@pytest.fixture(scope="module")
def cfg():
    return ativado()


def _lines(md, tickers):
    return md.universe.lines.reindex(list(tickers))


def _br_pair(md):
    lines = md.universe.lines
    loc = next(t for t in lines.index if t.endswith(".SA")
               and (lines["issuer_id"] == lines.at[t, "issuer_id"]).sum() > 1)
    iid = lines.at[loc, "issuer_id"]
    adr = next(t for t in lines.index if lines.at[t, "issuer_id"] == iid and t != loc)
    return iid, loc, adr


def test_mic_and_category_mapping():
    assert mic_da_linha("PETR4.SA", "B3") == "BVMF"
    assert mic_da_linha("PBR", "NYSE") == "XNYS" and mic_da_linha("MELI", "NASDAQ") == "XNAS"
    assert mic_da_linha("SBR01.SA", "BR") == "BVMF"  # bolsa desconhecida ⇒ sufixo
    assert mic_da_linha("X", "NYSE American") == "XASE"
    assert categoria_da_linha("PBR", "ADR") == "ADR"
    assert categoria_da_linha("MELI", "US_LISTED") == "US_STOCK"
    assert categoria_da_linha("WALMEX.MX", "LOCAL") == "MX"


def test_capacity_formula_matches_hand_computation(md, cfg):
    _iid, loc, adr = _br_pair(md)
    j = janela_execucao(FRI, cfg)
    cap_l = capacidade_fechamento_usd(_lines(md, [loc, adr]), md, j, cfg, lado="long")
    cap_s = capacidade_fechamento_usd(_lines(md, [loc, adr]), md, j, cfg, lado="short")
    tv = valor_negociado_usd(md, [loc])[loc]
    px = md.close[loc]
    obs = tv[(tv.index < pd.Timestamp(FRI)) & px.notna().to_numpy()]
    win = px.index[(px.index < pd.Timestamp(FRI)) & px.notna().to_numpy()][-20:]
    p25 = float(obs.reindex(win).dropna().quantile(0.25))
    frac = 0.10 * 0.08 + 0.10 * 0.25  # B3: leilão 8% do volume; pré-fechamento 25%
    assert cap_l[loc] == pytest.approx(frac * p25)
    assert frac == pytest.approx(0.033)
    assert cap_s[loc] == pytest.approx(0.75 * frac * p25)
    tab = tabela_capacidade(_lines(md, [adr]), md, j, cfg, lado="long")
    assert tab.at[adr, "categoria"] == "ADR" and tab.at[adr, "fracao_volume"] == pytest.approx(
        0.10 * 0.06 + 0.025)


def test_unknown_volume_means_zero_capacity_never_filled(md, cfg):
    _iid, loc, _ = _br_pair(md)
    vol = md.volume.copy()
    vol.loc[vol.index < pd.Timestamp(FRI), loc] = np.nan
    md2 = replace(md, volume=vol)
    j = janela_execucao(FRI, cfg)
    adv = adv_fechamento_usd(md2, [loc], FRI, cfg)
    assert math.isnan(adv.at[loc, "adv_usd"]) and adv.at[loc, "n_obs"] == 0
    tab = tabela_capacidade(_lines(md2, [loc]), md2, j, cfg, lado="long")
    assert tab.at[loc, "capacidade_usd"] == 0.0 and tab.at[loc, "motivo"] == "volume desconhecido"
    # Volume zero com preço válido também é ausência (nunca liquidez zero inventada).
    vol0 = md.volume.copy()
    vol0.loc[vol0.index < pd.Timestamp(FRI), loc] = 0.0
    assert math.isnan(adv_fechamento_usd(replace(md, volume=vol0), [loc], FRI, cfg).at[
        loc, "adv_usd"])


def test_closed_market_has_no_capacity_and_freezes_held_lines(md, cfg):
    iid, loc, adr = _br_pair(md)
    j = janela_execucao(B3_CLOSED, cfg)
    cap = capacidade_fechamento_usd(_lines(md, [loc, adr]), md, j, cfg, lado="long")
    assert cap[loc] == 0.0 and cap[adr] > 0
    tab = tabela_capacidade(_lines(md, [loc]), md, j, cfg, lado="long")
    assert "B3: sem pregão" in tab.at[loc, "motivo"]
    sides = pd.DataFrame({"long_ticker": [loc], "short_ticker": [adr]}, index=[iid])
    entry = BookEntry(week=date(2024, 11, 8), proposal_id="p", approval_hash="a" * 64,
                      booked_at=datetime(2024, 11, 8, 21, tzinfo=UTC), nav_usd=1e8,
                      positions=[BookedPosition(issuer_id=iid, ticker=loc, weight=0.01,
                                                notional_usd=1e6, shares=1000, currency="BRL")])
    frozen = emissores_congelados(sides, entry, j, cfg)
    assert iid in frozen and loc in frozen[iid]
    # Sem posição e com ADR elegível: não congela (ADR negocia).
    assert emissores_congelados(sides, None, j, cfg) == {}
    only_local = pd.DataFrame({"long_ticker": [loc], "short_ticker": [None]}, index=[iid])
    assert "mercado local" in emissores_congelados(only_local, None, j, cfg)[iid]
    strict = ativado(base=cfg).model_copy(update={"execution": cfg.execution.model_copy(
        update={"local_closed_policy": "freeze"})})
    assert iid in emissores_congelados(sides, None, j, strict)
    # Dia comum: nada congelado.
    assert emissores_congelados(sides, entry, janela_execucao(FRI, cfg), cfg) == {}


def test_adr_routing_on_closed_local_market(md, cfg):
    iid, loc, adr = _br_pair(md)
    lines = md.universe.lines.copy()
    lines["has_data"] = True
    lines["adtv_usd"] = 1e7
    sides = pd.DataFrame({"long_ticker": [loc], "long_line_type": ["LOCAL"],
                          "long_currency": ["BRL"], "adtv_long_usd": [2e7],
                          "short_ticker": [None]}, index=[iid])
    routed = rotear_linhas(sides, lines, janela_execucao(B3_CLOSED, cfg), cfg)
    assert routed.at[iid, "long_ticker"] == adr and routed.at[iid, "long_currency"] == "USD"
    same = rotear_linhas(sides, lines, janela_execucao(FRI, cfg), cfg)
    assert same.at[iid, "long_ticker"] == loc


def test_early_close_halves_capacity_only_where_the_market_closes_early(md, cfg):
    _iid, loc, adr = _br_pair(md)
    j = janela_execucao(EARLY, cfg)
    assert j.fechamento_antecipado and j.multiplicador_capacidade == 0.5
    tab = tabela_capacidade(_lines(md, [loc, adr]), md, j, cfg, lado="long")
    assert tab.at[adr, "multiplicador"] == 0.5   # NYSE antecipada
    assert tab.at[loc, "multiplicador"] == 1.0   # B3 em horário normal


def test_closes_needed_and_fills():
    assert fechamentos_necessarios(3e6, 1e6) == pytest.approx(3.0)
    assert fechamentos_necessarios(0.0, 0.0) == 0.0
    assert fechamentos_necessarios(1e6, 0.0) is None
    assert fechamentos_necessarios(1e6, float("nan")) is None
    assert preencher(1000, 50_000.0, 100.0) == 500
    assert preencher(-1000, 1e9, 100.0) == -1000
    assert preencher(1000, 0.0, 100.0) == 0
    assert lado_da_ordem(0, -100) == "short" and lado_da_ordem(-100, -50) == "long"
    assert lado_da_ordem(100, 300) == "long"


def test_close_costs_apply_auction_discount_and_closed_home_spread(cfg):
    trades = pd.DataFrame({
        "notional_usd": [1e6, 1e6], "adtv_usd": [2e7, 2e7], "sigma_d": [0.02, 0.02],
        "market": ["US", "US"], "currency": ["USD", "USD"], "categoria": ["ADR", "CO"],
        "local_fechado": [True, False]}, index=["A", "B"])
    res = custos_fechamento(trades, cfg)
    imp = 0.6 * 0.02 * math.sqrt(1e6 / 2e7) * 1e4
    assert res.at["A", "impact_bps"] == pytest.approx(imp * 0.6)
    assert res.at["B", "impact_bps"] == pytest.approx(imp * 1.0)
    assert res.at["A", "half_spread_bps"] == pytest.approx(1.5 * res.at["B", "half_spread_bps"])
    assert res.at["A", "cost_usd"] == pytest.approx(1e6 * res.at["A", "total_bps"] / 1e4)


def test_implementation_shortfall_and_t_stat():
    sf = shortfall([
        {"ordem": 1000, "executadas": 600, "preco_decisao": 10.0, "preco_fechamento": 10.5,
         "fx": 1.0, "custo_modelo_usd": 12.6, "volume_acoes": 100_000, "fatia_leilao": 0.1},
        {"ordem": -500, "executadas": -500, "preco_decisao": 20.0, "preco_fechamento": 19.0,
         "fx": 1.0, "custo_modelo_usd": 9.5, "volume_acoes": 50_000, "fatia_leilao": 0.1}])
    exec_usd = 600 * 10.5 + 500 * 19.0
    assert sf["nocional_executado_usd"] == pytest.approx(exec_usd)
    assert sf["deriva_usd"] == pytest.approx(600 * 0.5 + (-500) * (-1.0))  # ambos adversos
    assert sf["oportunidade_usd"] == pytest.approx(400 * 0.5)
    assert sf["deriva_bps"] == pytest.approx(800 / exec_usd * 1e4)
    assert sf["shortfall_bps"] == pytest.approx((800 + 22.1) / exec_usd * 1e4)
    assert sf["taxa_execucao"] == pytest.approx(exec_usd / (1000 * 10.5 + 500 * 19.0))
    assert sf["participacao_leilao_max"] == pytest.approx(0.1)
    assert estatistica_t([1.0, 2.0]) is None
    xs = [1.0, 2.0, 3.0]
    assert estatistica_t(xs) == pytest.approx(2.0 / (1.0 / math.sqrt(3)))
    assert estatistica_t([None, 1.0, float("nan"), 2.0]) is None


def test_ramp_path_from_close_capacity():
    w = {"A": 0.01, "B": -0.01, "C": 0.005}
    cap = {"A": 0.005, "B": 0.01, "C": 0.0}  # C sem capacidade: fica fixo
    t = trajetoria_montagem(w, cap, vol_ex_ante=0.01, vol_alvo=0.03)
    assert t["nomes_sem_capacidade"] == ["C"]
    vols = [r["vol"] for r in t["trajetoria"]]
    assert vols[0] == pytest.approx(0.01)
    assert vols[1] == pytest.approx(0.015)          # A limita: (0,01 + 0,005)/0,01 = 1,5
    assert vols[4] == pytest.approx(0.03)           # escala 3 alcançada no 4º fechamento
    assert t["fechamentos_ate_meta"] == 4
    assert trajetoria_montagem(w, cap, None, 0.05)["trajetoria"] == []


def test_liquidity_stress_counts_closes_with_latam_volume_haircut():
    w = {"A": 0.02, "B": -0.01}
    cap = {"A": 0.01, "B": 0.0}
    s = estresse_liquidez(w, cap, 1e8)
    assert s["fator_volume"] == pytest.approx(0.7)
    assert s["fracao_liquidavel"][1] == pytest.approx(0.007 / 0.03)
    assert s["fracao_liquidavel"][3] == pytest.approx(0.02 / 0.03)  # B sem capacidade
    assert s["fechamentos_p90"] is None and s["nomes_sem_capacidade"] == ["B"]


def test_line_without_price_series_has_zero_capacity_and_never_crashes(md, cfg):
    """Linha do universo ainda sem pregão (nova listagem): volume desconhecido ⇒ capacidade
    zero como restrição; a tabela e o ADV nunca levantam erro."""
    _iid, loc, _ = _br_pair(md)
    adv = adv_fechamento_usd(md, ["NAO_EXISTE", loc], FRI, cfg)
    assert math.isnan(adv.at["NAO_EXISTE", "adv_usd"]) and adv.at["NAO_EXISTE", "n_obs"] == 0
    assert adv.at["NAO_EXISTE", "ultimo"] is None and adv.at[loc, "adv_usd"] > 0
    lines = md.universe.lines.reindex([loc]).copy()
    novo = lines.rename(index={loc: "NAO_EXISTE"})
    tab = tabela_capacidade(pd.concat([lines, novo]), md, janela_execucao(FRI, cfg), cfg,
                            lado="long")
    assert tab.at["NAO_EXISTE", "capacidade_usd"] == 0.0
    assert tab.at["NAO_EXISTE", "motivo"] == "volume desconhecido"
    cap = capacidade_fechamento_usd(pd.concat([lines, novo]), md, janela_execucao(FRI, cfg),
                                    cfg, lado="short")
    assert cap["NAO_EXISTE"] == 0.0 and cap[loc] > 0


def test_adr_routing_unfreezes_issuer_and_trades_on_the_adr(md, cfg):
    """Dia de montagem com a B3 fechada e a NYSE aberta (como 01/05/2026): o emissor sem posição
    cuja linha escolhida é a local passa à ADR — não fica congelado, tem capacidade de compra
    pela ADR e executa ao fechamento da ADR (o custo com spread × 1,5 da bolsa local fechada
    está em ``test_close_costs_apply_auction_discount_and_closed_home_spread``)."""
    iid, loc, adr = _br_pair(md)
    lines = md.universe.lines.copy()
    lines["has_data"] = True
    lines["adtv_usd"] = 1e7
    sides = pd.DataFrame({"long_ticker": [loc], "long_line_type": ["LOCAL"],
                          "long_currency": ["BRL"], "adtv_long_usd": [2e7],
                          "short_ticker": [loc]}, index=[iid])
    j = janela_execucao(B3_CLOSED, cfg)
    assert iid in emissores_congelados(sides, None, j, cfg)  # sem roteamento: congelado
    routed = rotear_linhas(sides, lines, j, cfg)
    assert routed.at[iid, "long_ticker"] == adr
    assert emissores_congelados(routed, None, j, cfg) == {}
    cap = capacidade_fechamento_usd(_lines(md, [adr, loc]), md, j, cfg, lado="long")
    assert cap[adr] > 0 and cap[loc] == 0.0
    # Emissor DETIDO na linha local não muda de linha: fica congelado como está.
    held = BookEntry(week=date(2024, 11, 8), proposal_id="p", approval_hash="a" * 64,
                     booked_at=datetime(2024, 11, 8, 21, tzinfo=UTC), nav_usd=1e8,
                     positions=[BookedPosition(issuer_id=iid, ticker=loc, weight=0.01,
                                               notional_usd=1e6, shares=1000,
                                               currency="BRL")])
    kept = rotear_linhas(sides, lines, j, cfg, held)
    assert kept.at[iid, "long_ticker"] == loc and iid in emissores_congelados(kept, held, j, cfg)
    px = float(md.close.at[pd.Timestamp(B3_CLOSED), adr])
    fills = preenchimentos_esperados([OrdemLinha(iid, adr, 0, 10, px, 1.0)], md, j, cfg,
                                     nav_pre=1e4, decidido_em=None)
    assert fills[0].executadas == 10 and fills[0].mic in ("XNYS", "XASE", "ARCX", "XNAS")


def test_expected_fills_follow_the_single_rule(md, cfg):
    iid, loc, adr = _br_pair(md)
    j = janela_execucao(B3_CLOSED, cfg)
    ts = pd.Timestamp(B3_CLOSED)
    px = float(md.close.at[ts, adr])
    ordens = [OrdemLinha(iid, loc, 1000, 0, None, None),       # detida na B3 fechada
              OrdemLinha(iid, adr, 0, 50, px, 1.0),             # mesmo emissor ⇒ congelado
              OrdemLinha("OUTRO", adr, 0, 10 ** 9, px, 1.0)]    # acima da capacidade
    out = {(f.emissor, f.ticker): f for f in preenchimentos_esperados(
        ordens, md, j, cfg, nav_pre=1e8, decidido_em=None)}
    assert out[(iid, loc)].situacao == "congelado" and out[(iid, adr)].situacao == "congelado"
    big = out[("OUTRO", adr)]
    assert big.situacao == "parcial" and 0 < big.executadas < 10 ** 9, big
    assert big.executadas * px <= big.capacidade_usd * (1 + 1e-9)
    late = preenchimentos_esperados(
        [OrdemLinha("OUTRO", adr, 0, 10, px, 1.0)], md, janela_execucao(FRI, cfg), cfg,
        nav_pre=1e4, decidido_em=janela_execucao(FRI, cfg).corte_moc["XNYS"]
        + pd.Timedelta(minutes=1))
    assert late[0].situacao == "apos_corte" and late[0].executadas == 0
    tiny = preenchimentos_esperados([OrdemLinha("OUTRO", adr, 0, 1, px, 1.0)], md,
                                    janela_execucao(FRI, cfg), cfg, nav_pre=1e9,
                                    decidido_em=None)
    assert tiny[0].situacao == "banda"


def test_early_close_flag_is_about_the_deadline_markets_only(cfg):
    """31/12/2026: NYSE em pregão integral; só Buenos Aires fecha mais cedo ⇒ não é dia de
    fechamento antecipado (o prazo continua 15h00); 27/11 e 24/12: NYSE antecipada."""
    from cdp.portfolio.execucao import mics_antecipados

    dez31 = janela_execucao(date(2026, 12, 31), cfg)
    assert dez31.fechamento_antecipado is False
    assert dez31.prazo_decisao.strftime("%H:%M") == "15:00"
    assert "XBUE" in mics_antecipados(dez31, cfg)
    for d in (date(2026, 11, 27), date(2026, 12, 24)):
        assert janela_execucao(d, cfg).fechamento_antecipado is True


def test_structural_capacity_ignores_one_day_holidays(md, cfg):
    """Estresse e trajetória medem a liquidez estrutural: num pregão regular a B3 tem
    capacidade mesmo quando o próximo dia de montagem é feriado nela; o feriado entra só na
    janela daquele dia."""
    _iid, loc, adr = _br_pair(md)
    md_d = md.truncate(FRI)
    reg = janela_regular(date(2024, 11, 11), cfg)
    base = tabela_capacidade(_lines(md, [loc, adr]), md_d, reg, cfg, lado="long")
    assert base.at[loc, "capacidade_usd"] > 0 and base.at[adr, "capacidade_usd"] > 0
    seq = capacidade_por_janela(base, [janela_execucao(B3_CLOSED, cfg),
                                       janela_execucao(date(2024, 11, 22), cfg),
                                       janela_execucao(EARLY, cfg)], cfg)
    assert seq[0][loc] == 0.0 and seq[0][adr] == pytest.approx(base.at[adr, "capacidade_usd"])
    assert seq[1][loc] == pytest.approx(base.at[loc, "capacidade_usd"])
    assert seq[2][adr] == pytest.approx(0.5 * base.at[adr, "capacidade_usd"])
    w = {"A": 0.02}
    t = trajetoria_montagem(w, [{"A": 0.0}, {"A": 0.02}], vol_ex_ante=0.01, vol_alvo=0.02)
    assert [r["vol"] for r in t["trajetoria"][:3]] == pytest.approx([0.01, 0.01, 0.02])
    assert t["fechamentos_ate_meta"] == 2 and t["nomes_sem_capacidade"] == []


def test_ramp_is_flat_when_the_book_is_already_at_target():
    t = trajetoria_montagem({"A": 0.02}, {"A": 0.01}, vol_ex_ante=0.06, vol_alvo=0.05)
    assert t["fechamentos_ate_meta"] == 0
    assert all(r["vol"] == pytest.approx(0.06) for r in t["trajetoria"])


def test_closing_window_participation_respects_the_stated_cap():
    sf = shortfall([{"ordem": 330, "executadas": 330, "preco_decisao": 10.0,
                     "preco_fechamento": 10.0, "fx": 1.0, "custo_modelo_usd": 0.0,
                     "volume_acoes": 10_000, "fatia_leilao": 0.08, "fatia_pre": 0.25}])
    # 330 = (0,10·0,08 + 0,10·0,25) × 10.000 ⇒ 10% da janela de fechamento (41% "do leilão")
    assert sf["participacao_janela_mediana"] == pytest.approx(0.10)
    assert sf["participacao_leilao_mediana"] == pytest.approx(330 / 800)


def test_trade_list_counts_closes_and_skips_frozen_issuers():
    from cdp.contracts import LineType, PositionTarget, Side

    def pos(iid, tk, w, sh):
        return PositionTarget(issuer_id=iid, name=iid, country="BR", sector="X",
                              side=Side.LONG if w > 0 else Side.SHORT, weight=w,
                              notional_usd=abs(w) * 1e8, execution_ticker=tk,
                              line_type=LineType.ADR, currency="USD", price_local=10.0,
                              shares=sh, adtv_usd=1e7)

    targets = [pos("A", "AAA", 0.01, 100_000), pos("B", "BBB", -0.01, -100_000)]
    legacy = build_trades(targets, None, 1e8, participation=0.2)
    assert legacy[0].est_days == pytest.approx(1e6 / (0.2 * 1e7))
    caps_l = pd.Series({"AAA": 2.5e5, "BBB": 1e5})
    caps_s = pd.Series({"AAA": 1e5, "BBB": 2e5})
    tr = {t.ticker: t for t in build_trades(targets, None, 1e8, participation=0.2,
                                            capacidade_long=caps_l, capacidade_short=caps_s)}
    assert tr["AAA"].est_days == pytest.approx(4.0)     # compra: capacidade de long
    assert tr["BBB"].est_days == pytest.approx(5.0)     # venda a descoberto: de short
    none_cap = build_trades(targets, None, 1e8, capacidade_long=pd.Series({"AAA": 0.0}),
                            capacidade_short=pd.Series(dtype=float))
    assert all(t.est_days is None for t in none_cap)
    assert [t.ticker for t in build_trades(targets, None, 1e8, congelados={"B"})] == ["AAA"]


def test_fixed_cost_band_per_market(md, cfg):
    """Com mínimo por ordem e ``max_fixed_cost_bps``, a banda sobe por mercado: uma ordem de
    US$ 2 mil executa nos EUA (banda de 0,10% do NAV = US$ 1 mil) e não na BMV (mínimo de
    US$ 3,5 a 10 bps ⇒ US$ 3,5 mil); encerrar uma posição é sempre permitido."""
    small = cfg.with_overrides({
        "costs": {"min_order_cost_usd": {"US": 1.0, "BR": 0.0, "MX": 3.5}},
        "execution": {"min_trade_weight": 0.001, "max_fixed_cost_bps": 10.0}})
    lines = md.universe.lines
    us = next(t for t in lines.index if t.endswith("ADR"))
    mx = next(t for t in lines.index if t.endswith(".MX"))
    j = janela_execucao(FRI, small)
    ts = pd.Timestamp(FRI)
    px_us, px_mx = float(md.close.at[ts, us]), float(md.close.at[ts, mx])
    fx_mx = 0.05  # USD por MXN (o teste só usa o nocional em USD)
    q_us = max(int(2_000 / px_us), 1)
    q_mx = max(int(2_000 / (px_mx * fx_mx)), 1)
    out = preenchimentos_esperados(
        [OrdemLinha("U", us, 0, q_us, px_us, 1.0), OrdemLinha("M", mx, 0, q_mx, px_mx, fx_mx),
         OrdemLinha("M2", mx, q_mx, 0, px_mx, fx_mx)],
        md, j, small, nav_pre=1e6, decidido_em=None)
    by = {f.emissor: f for f in out}
    assert by["U"].situacao in ("executada", "parcial")
    assert by["M"].situacao == "banda"
    assert by["M2"].situacao != "banda"          # encerramento: nunca barrado pela banda
    # sem max_fixed_cost_bps (regra da seção execution anterior): só min_trade_weight
    base = preenchimentos_esperados([OrdemLinha("M", mx, 0, q_mx, px_mx, fx_mx)], md, j,
                                    cfg, nav_pre=1e6, decidido_em=None)
    assert base[0].situacao != "banda"


def test_liquidity_limit_counts_closes_in_compliance():
    """Execução só no fechamento: ``LIQ_DAYS_*`` conta fechamentos à capacidade estrutural da
    linha (coluna ``cap_liquidez_*``); capacidade desconhecida reprova."""
    from cdp.portfolio.compliance import run_compliance
    from cdp.risk.types import RiskModel

    cfg = ativado()
    ids = ["A", "B"]
    cons = pd.DataFrame({
        "can_long": [True, False], "can_short": [False, True], "max_long": [0.04, 0.0],
        "max_short": [0.0, 0.025], "max_trade": [0.04, 0.025], "borrow_fee": [np.nan, 0.01],
        "beta": [1.0, 1.0], "country": ["BR", "BR"], "sector": ["X", "X"], "reasons": ["", ""],
        "shortable": [False, True], "adtv_long_usd": [5e6, np.nan],
        "adtv_short_usd": [np.nan, 5e6], "cap_liquidez_long": [0.01, 0.0],
        "cap_liquidez_short": [0.0, 0.004]}, index=ids)
    w = pd.Series({"A": 0.02, "B": -0.01})
    assets = pd.DataFrame({"country": ["BR", "BR"], "sector": ["X", "X"],
                           "adtv_usd": [5e6, 5e6]}, index=ids)
    B = pd.DataFrame({"market": [1.0, 1.0]}, index=ids)
    model = RiskModel(as_of=date(2026, 10, 9), exposures=B,
                      factor_cov=pd.DataFrame([[0.04]], index=["market"], columns=["market"]),
                      specific_var=pd.Series([0.09, 0.09], index=ids),
                      factor_returns=pd.DataFrame(), specific_returns=pd.DataFrame(),
                      factor_groups={"market": "market"})
    checks = {c.check_id: c for c in run_compliance(
        w, model, cons, None, assets, cfg, 1e6, None, True, date(2026, 10, 8),
        date(2026, 10, 9), None, True)}
    lo, sh = checks["LIQ_DAYS_LONG"], checks["LIQ_DAYS_SHORT"]
    assert lo.passed and lo.value == pytest.approx(2.0) and "fechamentos" in lo.name.lower()
    assert not sh.passed and sh.value == pytest.approx(2.5)          # 0,01 / 0,004 > 2
    unknown = cons.copy()
    unknown.loc["A", "cap_liquidez_long"] = 0.0
    chk = {c.check_id: c for c in run_compliance(
        w, model, unknown, None, assets, cfg, 1e6, None, True, date(2026, 10, 8),
        date(2026, 10, 9), None, True)}["LIQ_DAYS_LONG"]
    assert not chk.passed and "sem volume" in chk.details
