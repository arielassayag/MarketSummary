"""Montagem na sexta (último pregão da semana na NYSE), execução no leilão de fechamento com
capacidade e relatório semanal de resultado — demonstração offline (DADOS SIMULADOS)."""

from __future__ import annotations

import json
import shutil
import warnings
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from test_calendar import LEGADO, ativado

import cdp.workflow.demo as demo_mod
from cdp.config import FundConfig, load_config
from cdp.data.synthetic import make_synthetic_market
from cdp.portfolio.execucao import (
    conferir_efetivacao,
    janela_execucao,
    mic_da_linha,
    tabela_capacidade,
)
from cdp.research.comentario_semanal import build_weekly_factbook, modelo_valido
from cdp.workflow.agenda import agenda, weekly_report_status
from cdp.workflow.book import Book, _booking_mismatches_fechamento
from cdp.workflow.demo import DEMO_HISTORY_START, DEMO_MIND, DemoStore, run_demo, write_demo_inputs
from cdp.workflow.relatorio_semanal import (
    REPORT_EVENT,
    _causa_capacidade,
    calcular_semana,
    publicar,
    render_relatorio,
    report_dir,
    somar_atribuicao,
    validar,
)
from cdp.workflow.runtime import Runtime

BRT = ZoneInfo("America/Sao_Paulo")
W1, W2, W3 = date(2024, 3, 8), date(2024, 3, 15), date(2024, 3, 22)


@pytest.fixture(scope="module")
def cfg() -> FundConfig:
    return ativado()


@pytest.fixture(scope="module")
def demo(tmp_path_factory, cfg):
    out = tmp_path_factory.mktemp("cdp_demo_sexta")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summary = run_demo(out, days=6, first_week=date(2024, 3, 4), cfg=cfg)
    return out, summary


def _rt(out, cfg, reports=None, md_as_of=W2) -> Runtime:
    md = make_synthetic_market(seed=7, start=DEMO_HISTORY_START, as_of=md_as_of)
    return Runtime(cfg=cfg, book_root=out / "book", market_root=out / "market",
                   reports_root=reports or out / "reports", store_override=DemoStore(md),
                   teses_root=None)


def test_demo_runs_on_fridays_with_weekly_reports(demo):
    out, summary = demo
    assert summary["integridade"] is True, summary["verificacao"]
    assert summary["pregoes"][0] == "2024-03-08" and summary["pregoes"][-1] == "2024-03-15"
    weeks = [e["semana"] for e in summary["etapas"] if "semana" in e]
    assert weeks == [W1, W2]
    reps = [e["relatorio_semanal"] for e in summary["etapas"] if "relatorio_semanal" in e]
    assert [r["tipo"] for r in reps] == ["montagem", "semanal"]
    assert all(r["comentario_da_mente"] and not r["apontamentos"] for r in reps)
    first = (out / "reports" / "semanal" / "2024-03-08" / "relatorio.md").read_text("utf-8")
    second = (out / "reports" / "semanal" / "2024-03-15" / "relatorio.md").read_text("utf-8")
    assert "Relatório de montagem da carteira" in first and "DADOS SIMULADOS" in first
    assert "Relatório semanal de resultado" in second and "DADOS SIMULADOS" in second
    for txt in (first, second):
        for word in ("segunda", "reinício", "metodologia anterior", "reconstru"):
            assert word not in txt.lower()


def test_report_events_and_files(demo, cfg):
    out, _ = demo
    rt = _rt(out, cfg)
    evs = [e for e in rt.book.audit.events() if e.event_type == REPORT_EVENT]
    assert [e.week for e in evs] == [W1, W2]
    folder = report_dir(rt, W2)
    for name in ("fatos.md", "factbook.json", "comentario.schema.json", "comentario.json",
                 "relatorio.md", "relatorio.html"):
        assert (folder / name).exists(), name
    ok, msgs = rt.verify_all()
    assert ok, msgs


def test_week_and_inception_attribution_sum_the_daily_records(demo, cfg):
    out, _ = demo
    rt = _rt(out, cfg)
    dados = calcular_semana(rt, W2)
    recs = [r for r in rt.track().records() if r.date <= W2]
    week = [r for r in recs if r.date > W1]
    assert dados["semana"]["n"] == len(week) == 5 and dados["desde_inicio"]["n"] == len(recs)
    assert dados["semana"]["atribuicao"] == somar_atribuicao(week)
    assert dados["desde_inicio"]["atribuicao"] == somar_atribuicao(recs)
    assert dados["semana"]["pnl_usd"] == pytest.approx(sum(r.pnl_usd for r in week))
    comp = dados["semana"]["atribuicao"]["component"]
    assert sum(comp[k] for k in ("equity", "costs", "borrow", "financing") if k in comp) == \
        pytest.approx(dados["semana"]["pnl_usd"])
    assert dados["desde_inicio"]["ret"] == pytest.approx(
        recs[-1].nav_end_usd / recs[0].nav_start_usd - 1.0)
    assert dados["montagem"] is False and calcular_semana(rt, W1)["montagem"] is True
    assert {m["tipo"] for m in dados["mudancas"]} <= {"entrada", "saida", "aumento", "reducao"}
    ex = dados["execucao"]
    assert ex["giro"] > 0 and ex["custos_usd"] > 0 and 0 < ex["taxa_execucao"] <= 1.0
    assert len(ex["historico_deriva_bps"]) == 2
    rk = dados["risco"]
    assert 0 < rk["efetiva"]["idio"] <= 1 and rk["alvo"]["vol"] > 0


def test_every_fill_is_within_realized_close_capacity(demo, cfg):
    out, _ = demo
    rt = _rt(out, cfg)
    md = rt.store.load(as_of=W2)
    for d in (W1, W2):
        dados = calcular_semana(rt, d)
        lines = [ln for ln in dados["execucao"]["linhas"] if ln["executadas"]]
        assert lines
        j = janela_execucao(d, cfg)
        uni = md.universe.lines.reindex([ln["ticker"] for ln in lines])
        caps = {lado: tabela_capacidade(uni, md.truncate(d), j, cfg, lado=lado,
                                        volume="realizado") for lado in ("long", "short")}
        for ln in lines:
            usd = abs(ln["executadas"]) * ln["preco_fechamento"] * ln["fx"]
            # a capacidade de short só vale ao abrir/aumentar vendido; a de long é a maior
            assert usd <= caps["long"].at[ln["ticker"], "capacidade_usd"] * (1 + 1e-9), ln
            assert abs(ln["executadas"]) <= abs(ln["ordem"])


def test_booked_at_is_the_latest_official_close_of_traded_lines(demo, cfg):
    out, _ = demo
    rt = _rt(out, cfg)
    e1, e2 = rt.book.load_booked(W1), rt.book.load_booked(W2)
    # 08/03/2024: EUA ainda sem horário de verão ⇒ 18h00; 15/03/2024: com horário de verão ⇒ 17h00.
    assert e1.booked_at.astimezone(BRT).strftime("%H:%M") == "18:00"
    assert e2.booked_at.astimezone(BRT).strftime("%H:%M") == "17:00"
    d1 = rt.book.load_decision(W1)
    assert d1.decided_at.astimezone(BRT).time() == time(15, 0) and e1.booked_at >= d1.decided_at


def test_partial_fill_booking_check_accepts_between_and_refuses_beyond(demo, cfg):
    out, _ = demo
    rt = _rt(out, cfg)
    entry = rt.book.load_booked(W2)
    prop = next(p for p in rt.book.list_proposals(W2) if p.proposal_id == entry.proposal_id)
    held = rt.book.holdings_before(W2)
    assert _booking_mismatches_fechamento(entry, prop, held) == []
    pos = entry.positions[0]
    target = next((p.shares for p in prop.positions if p.issuer_id == pos.issuer_id
                   and p.execution_ticker == pos.ticker), 0) or 0
    worse = pos.model_copy(update={"shares": int(target) + (5000 if target >= 0 else -5000)})
    bad = entry.model_copy(update={"positions": [worse] + list(entry.positions[1:])})
    probs = _booking_mismatches_fechamento(bad, prop, held)
    assert any("fora do intervalo" in p for p in probs)


def test_pending_validation_template_fallback_and_immutability(demo, cfg, tmp_path):
    out, _ = demo
    copy = tmp_path / "copia"
    shutil.copytree(out / "book", copy / "book")
    rt = _rt(copy, cfg, reports=copy / "reports")
    st = weekly_report_status(rt, datetime.combine(W2, time(21, 0), tzinfo=BRT))
    # Nenhum relatório fica para trás: os dois dias de montagem sem relatório publicado são
    # pendentes, do mais antigo ao mais recente.
    assert st["pendente"] is True and st["pendentes"] == [W1, W2] and st["data"] == W1
    assert st["registro_do_fechamento"]
    folder = report_dir(rt, W2)
    folder.mkdir(parents=True)
    bad = {"mind": "claude-code", "resumo": "Retorno de 5% na semana.",
           "desempenho_semana": ["Texto."], "atribuicao": ["Texto."],
           "risco_nova_carteira": ["Texto."], "execucao": ["Texto."],
           "mudancas_carteira": [{"emissor": "NAO_EXISTE", "tipo": "entrada",
                                  "racional": "Sem base."}]}
    (folder / "comentario.json").write_text(json.dumps(bad), encoding="utf-8")
    ok, issues = validar(rt, W2)
    assert not ok and any("número fora de placeholder" in i for i in issues)
    assert any("não mudou de posição" in i for i in issues)
    pub = publicar(rt, W2)
    assert pub["comentario_da_mente"] is False and pub["apontamentos_comentario"]
    md_txt = (folder / "relatorio.md").read_text("utf-8")
    assert "modelo determinístico" in md_txt and "Retorno de 5% na semana" not in md_txt
    with pytest.raises(FileExistsError):
        publicar(rt, W2)
    st2 = weekly_report_status(rt, datetime.combine(W2, time(22, 0), tzinfo=BRT))
    assert st2["pendente"] is True and st2["pendentes"] == [W1] and st2["data"] == W1
    publicar(rt, W1)
    st3 = weekly_report_status(rt, datetime.combine(W2, time(22, 30), tzinfo=BRT))
    assert st3["pendente"] is False and st3["publicado"] and st3["data"] == W2


def test_agenda_friday_rule_and_effective_deadline(demo, cfg):
    out, _ = demo
    rt = _rt(out, cfg)
    thu = agenda(rt, datetime(2024, 3, 14, 12, 0, tzinfo=BRT))["semanal"]
    assert thu["semana"] == W2 and thu["acao"] == "nenhuma"
    assert thu["motivo"] == "a montagem desta semana é sexta-feira, 15/03"
    assert thu["prazo_efetivo"] == datetime(2024, 3, 15, 15, 0, tzinfo=BRT)
    fri = agenda(rt, datetime(2024, 3, 15, 12, 0, tzinfo=BRT))["semanal"]
    assert fri["hoje_e_dia_de_rebalanceamento"] and fri["acao"] == "tese" or fri["decisao_gravada"]


def test_decide_is_refused_after_the_effective_deadline(cfg, tmp_path):
    md = make_synthetic_market(seed=7, start=DEMO_HISTORY_START, as_of=W1)
    clock = {"t": datetime.combine(W1, time(11, 0), tzinfo=BRT)}
    rt = Runtime(cfg=cfg, book_root=tmp_path / "book", market_root=tmp_path / "market",
                 reports_root=tmp_path / "reports", store_override=DemoStore(md),
                 clock=lambda: clock["t"], teses_root=None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rt.weekly_prepare(W1, mind=DEMO_MIND, live=False)
        write_demo_inputs(rt, W1)
    clock["t"] = datetime.combine(W1, time(15, 1), tzinfo=BRT)
    with pytest.raises(ValueError, match="Prazo efetivo"):
        rt.weekly_decide(W1, mind=DEMO_MIND)
    assert not rt.book.list_decisions(W1)


def test_b3_holiday_rebalance_never_trades_b3_local_lines(cfg, tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summary = run_demo(tmp_path / "feriado", days=1, first_week=date(2024, 11, 11), cfg=cfg)
    assert summary["pregoes"] == ["2024-11-15"] and summary["integridade"]
    rt = _rt(tmp_path / "feriado", cfg, md_as_of=date(2024, 11, 15))
    entry = rt.book.load_booked(date(2024, 11, 15))
    assert entry is not None and entry.positions
    assert all(mic_da_linha(p.ticker) != "BVMF" for p in entry.positions)
    prop = rt.book.load_proposal(date(2024, 11, 15))
    assert all(not p.execution_ticker.endswith(".SA") for p in prop.positions)
    assert pd.Timestamp(entry.booked_at).tz is not None


# ----------------------------------------------------------------------------- dia sem decisão


@pytest.fixture(scope="module")
def perdida(tmp_path_factory, cfg):
    """Três sextas; a decisão de 15/03 não é tomada (prazo perdido): carteira mantida."""
    out = tmp_path_factory.mktemp("cdp_demo_perdida")
    orig = demo_mod._montagem
    mp = pytest.MonkeyPatch()
    mp.setattr(demo_mod, "_montagem", lambda s, c: orig(s, c) and s != W2)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            summary = run_demo(out, days=11, first_week=date(2024, 3, 4), cfg=cfg)
    finally:
        mp.undo()
    return out, summary


def test_missed_decision_friday_still_gets_its_weekly_report(perdida, cfg):
    out, summary = perdida
    assert summary["integridade"], summary["verificacao"]
    rt = _rt(out, cfg, md_as_of=W3)
    assert not rt.book.list_decisions(W2) and rt.book.list_decisions(W3)
    st = weekly_report_status(rt, datetime.combine(W3, time(21, 30), tzinfo=BRT))
    assert st["pendente"] and st["pendentes"] == [W2] and st["data"] == W2
    assert st["decisao_gravada"] is False
    dados = calcular_semana(rt, W2)
    assert dados["decisao"] is False and dados["mudancas"] == []
    assert dados["anterior"] == W1 and dados["semana"]["n"] == 5
    assert dados["execucao"]["manter"] and dados["execucao"]["congelados"] == {}
    pub = publicar(rt, W2)
    assert pub["tipo"] == "semanal" and pub["comentario_da_mente"] is False
    txt = (report_dir(rt, W2) / "relatorio.md").read_text("utf-8")
    assert "Sem decisão gravada no dia de montagem" in txt
    assert "Relatório semanal de resultado" in txt
    # A semana seguinte começa no fechamento do dia de montagem perdido: cinco pregões, não dez.
    d3 = calcular_semana(rt, W3)
    assert d3["anterior"] == W2 and d3["semana"]["n"] == 5
    assert weekly_report_status(rt, datetime.combine(W3, time(22, 0), tzinfo=BRT))[
        "pendente"] is False


def test_stress_uses_structural_capacity_not_the_next_holiday(perdida, cfg):
    """22/03/2024: o próximo dia de montagem é a Quinta-Feira Santa (28/03: BMV, BVC e Santiago
    fechadas). O estresse mede a liquidez estrutural — nenhum nome fica sem capacidade só pelo
    feriado — e o feriado aparece como nota operacional."""
    out, _ = perdida
    rt = _rt(out, cfg, md_as_of=W3)
    lq = calcular_semana(rt, W3)["liquidez"]
    assert lq["proximo_dia_de_montagem"] == date(2024, 3, 28)
    assert lq["nomes_sem_capacidade"] == []
    assert lq["fracao_liquidavel"][10] == pytest.approx(1.0)
    rev = lq["reverso"]["fracao_liquidavel"]
    assert all(rev[h] <= lq["fracao_liquidavel"][h] + 1e-12 for h in rev)
    assert lq["custo"]["custo_usd"] > 0 and lq["custo"]["cobertura"] == pytest.approx(1.0)


def test_weekly_report_is_never_pending_under_the_legacy_mandate(demo):
    out, _ = demo
    legado = load_config(LEGADO)
    assert legado.execution is None
    rt = _rt(out, legado)
    st = weekly_report_status(rt, datetime.combine(W2, time(21, 0), tzinfo=BRT))
    assert st["pendente"] is False and st["pendentes"] == [] and "execution" in st["motivo"]


def test_side_attribution_facts_and_template(demo, cfg):
    out, _ = demo
    rt = _rt(out, cfg)
    dados = calcular_semana(rt, W2)
    fb = build_weekly_factbook(dados)
    assert "semana.attr.lado.long" in fb.facts and "semana.attr.lado.short" in fb.facts
    out_txt = modelo_valido(fb, dados["mudancas"], montagem=False)
    assert any(t.startswith("Por lado, a ponta comprada") for t in out_txt.atribuicao)
    md_txt, _ = render_relatorio(dados, fb, {"resumo": "x", "desempenho_semana": [],
                                             "desempenho_desde_inicio": [], "atribuicao": [],
                                             "mudancas_carteira": {}, "risco_nova_carteira": [],
                                             "execucao": [], "perspectivas": [],
                                             "mind": "demo"},
                                 da_mente=False, problemas=[], cfg=cfg)
    for code in ("| LONG |", "| SHORT |", "| style |", "| market |", "| country |"):
        assert code not in md_txt
    assert "| Comprado |" in md_txt and "−" not in md_txt  # um só sinal de menos (hífen)


def test_build_up_block_is_gated_on_the_build_up_phase(demo, cfg):
    out, _ = demo
    rt = _rt(out, cfg)
    dados = calcular_semana(rt, W2)
    traj = dados["montagem_trajetoria"]
    assert traj["fase_montagem"] is True  # vol efetiva da demonstração abaixo do piso
    fb = build_weekly_factbook(dados)
    assert traj["publicar"] and "montagem.fechamentos" in fb.facts
    # Vol efetiva já acima do piso em algum fechamento ⇒ fim do período de montagem: nem bloco
    # nem fatos de montagem.
    piso = cfg.model_copy(update={"risk": cfg.risk.model_copy(update={"vol_band_min": 0.005})})
    d2 = calcular_semana(_rt(out, piso), W2)
    assert d2["montagem_trajetoria"]["fase_montagem"] is False
    assert not d2["montagem_trajetoria"]["publicar"]
    fb2 = build_weekly_factbook(d2)
    assert not any(f.startswith("montagem.") for f in fb2.facts)
    texto = modelo_valido(fb2, d2["mudancas"], montagem=False)
    assert not any("Período de montagem" in t for t in texto.risco_nova_carteira)


def test_capacity_causality_needs_binding_caps_or_partial_fills():
    from types import SimpleNamespace

    assert _causa_capacidade(None, {"parciais": [], "taxa_execucao": 1.0}) is False
    assert _causa_capacidade(None, {"parciais": ["X (1/2)"], "taxa_execucao": 0.9}) is True
    prop = SimpleNamespace(overrides={"formulacao": {"limites_por_nome": {
        "A": {"origem": "capacidade_fechamento", "vinculante": "long"},
        "B": {"origem": "mandato", "vinculante": None}}}})
    assert _causa_capacidade(prop, {"parciais": [], "taxa_execucao": 1.0}) is True
    prop2 = SimpleNamespace(overrides={"formulacao": {"limites_por_nome": {
        "A": {"origem": "capacidade_fechamento", "vinculante": None}}}})
    assert _causa_capacidade(prop2, {"parciais": [], "taxa_execucao": 1.0}) is False


def test_forced_booking_above_capacity_is_refused(demo, cfg):
    """O livro (e o ``cdp verify``) recalculam a execução esperada no pregão: uma efetivação
    forçada à ordem cheia numa linha limitada pela capacidade é recusada, embora fique entre a
    posição anterior e a ordem aprovada."""
    out, _ = demo
    rt = _rt(out, cfg)
    entry = rt.book.load_booked(W2)
    prop = next(p for p in rt.book.list_proposals(W2) if p.proposal_id == entry.proposal_id)
    dec = rt.book.load_decision(W2, prop.version)
    held = rt.book.holdings_before(W2)
    md = rt.store.load(as_of=W2)
    assert conferir_efetivacao(entry, prop, dec.decided_at, held, md, cfg) == []
    parcial = calcular_semana(rt, W2)["execucao"]["parciais"][0].split(" ")[0]
    alvo = next(p for p in prop.positions if p.execution_ticker == parcial)
    bad = entry.model_copy(update={"positions": [
        b.model_copy(update={"shares": alvo.shares}) if b.ticker == parcial else b
        for b in entry.positions]})
    probs = conferir_efetivacao(bad, prop, dec.decided_at, held, md, cfg)
    assert probs and parcial in probs[0] and "execução máxima" in probs[0]
    livro = Book(rt.book_root, config=cfg, mercado=lambda d: rt.store.load(as_of=d))
    with pytest.raises(ValueError, match="execução máxima"):
        livro._validate_booking(bad, prop.snapshot_hash, cfg.config_hash(), dec.research_hash)
    ok, msgs = rt.verify_all()
    assert ok, msgs
    assert "execução: 2 efetivações conferidas contra a execução esperada no fechamento" in msgs


def test_decided_at_is_the_instant_the_deadline_was_checked(cfg, tmp_path):
    md = make_synthetic_market(seed=7, start=DEMO_HISTORY_START, as_of=W1)
    clock = {"t": datetime.combine(W1, time(11, 0), tzinfo=BRT), "step": 0}

    def tick():
        t = clock["t"]
        clock["t"] = t + pd.Timedelta(seconds=clock["step"])
        return t

    rt = Runtime(cfg=cfg, book_root=tmp_path / "book", market_root=tmp_path / "market",
                 reports_root=tmp_path / "reports", store_override=DemoStore(md),
                 clock=tick, teses_root=None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rt.weekly_prepare(W1, mind=DEMO_MIND, live=False)
        write_demo_inputs(rt, W1)
        clock.update(t=datetime.combine(W1, time(14, 59, 30), tzinfo=BRT), step=20)
        rt.weekly_decide(W1, mind=DEMO_MIND)
    dec = rt.book.load_decision(W1)
    prop = rt.book.load_proposal(W1)
    assert dec.decided_at.astimezone(BRT).time() == time(14, 59, 30)
    assert dec.decided_at <= rt.decision_deadline(W1)
    assert prop.created_at == dec.decided_at


def test_daily_liquidity_counts_closes_at_structural_capacity(demo, cfg):
    """Com a execução no fechamento, o registro diário mede a liquidez em FECHAMENTOS para zerar
    cada emissor (capacidade estrutural de redução por fechamento da linha detida), não em dias
    a 20% do ADTV; o monitor de risco usa a mesma unidade."""
    from cdp.workflow.risk_monitor import run_risk_monitor

    out, _summary = demo
    rt = _rt(out, cfg)                       # mesmo mercado sintético da demonstração
    rec = rt.track().get(W1)
    runner = rt._runner()
    ctx = runner.context(W1, rt.store.load(as_of=W1), None, need_models=False)
    closes = runner._closes_by_issuer(ctx, list(rec.positions))
    assert closes and all(v is not None and v > 0 for v in closes.values())
    assert rec.risk.max_days_to_liquidate == pytest.approx(max(closes.values()))
    res = run_risk_monitor(rt, as_of=W1, now=datetime.combine(W1, time(21, 0), tzinfo=BRT))
    assert res["liquidez"]["unidade"] == "fechamentos"
