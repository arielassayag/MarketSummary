"""Calendário do CDP: regra do último pregão da semana na NYSE, prazo efetivo, horários oficiais
de fechamento (fixados), fechamentos antecipados, mercados fechados e horário de verão dos EUA."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from cdp.calendar import (
    chave_da_semana,
    chave_valida,
    dia_de_montagem,
    is_data_session,
    is_early_close,
    is_rebalance_day,
    is_session,
    last_session_of_week,
    next_rebalance_after,
    previous_data_session,
    previous_session,
    rebalance_date_of_week,
    rebalance_schedule,
    resumo_cronograma,
    week_id,
)
from cdp.config import FundConfig, load_config
from cdp.portfolio.execucao import (
    janela_execucao,
    mercados_elegiveis,
    motivo_inelegivel,
    prazo_efetivo,
)

BRT = ZoneInfo("America/Sao_Paulo")
NY = ZoneInfo("America/New_York")

#: Horários oficiais conferidos (docs/cdp/EXECUCAO.md §4). Qualquer alteração do mandato nesta
#: tabela precisa de nova conferência nas fontes oficiais e da atualização deste teste.
HORARIOS_OFICIAIS = {
    "XNYS": {"tz": "America/New_York", "close": "16:00", "moc_cutoff": "15:50"},
    "XNAS": {"tz": "America/New_York", "close": "16:00", "moc_cutoff": "15:55"},
    "ARCX": {"tz": "America/New_York", "close": "16:00", "moc_cutoff": "15:59"},
    "BVMF": {"tz": "America/New_York", "close": "16:00", "moc_cutoff": "15:55"},
    "XMEX": {"tz": "America/New_York", "close": "16:00", "moc_cutoff": "15:40"},
    "XSGO": {"tz": "America/Santiago", "close": "16:00", "moc_cutoff": "15:45"},
    "XBOG": {"tz": "America/New_York", "close": "16:00", "moc_cutoff": "15:55"},
    "XLIM": {"tz": "America/New_York", "close": "16:00", "moc_cutoff": "15:52"},
    "XBUE": {"tz": "America/Argentina/Buenos_Aires", "close": "17:00", "moc_cutoff": "16:57"},
}
ATIVACAO = {
    "fund": {
        "rebalance_weekday": "LAST_US_SESSION",
        "rebalance_rule": ("último pregão da semana na NYSE (sexta-feira ou, com feriado nos "
                           "EUA, o pregão anterior)"),
        "decision_deadline_local": "15:00",
    },
    "execution": {"rebalance_calendar": "XNYS", "decision_deadline_cap_local": "15:00",
                  "decision_buffer_minutes": 45, "close_times": HORARIOS_OFICIAIS},
}


LEGADO = Path(__file__).resolve().parent / "fixtures" / "fund_legado.yaml"


def ativado(base: FundConfig | None = None, **fund) -> FundConfig:
    """Regra da NYSE e execução no fechamento sobre o mandato legado fixado nos testes (as
    demais chaves de construção ficam como no mandato legado: o teste isola o cronograma e a
    execução)."""
    raw = (base or load_config(LEGADO)).model_dump(mode="json")
    raw["fund"].update(ATIVACAO["fund"])
    raw["fund"].update(fund)
    raw["execution"] = dict(ATIVACAO["execution"])
    return FundConfig.model_validate(raw)


@pytest.fixture(scope="module")
def cfg() -> FundConfig:
    return ativado(inception_date="2026-10-09")


def _brt(dt: datetime) -> str:
    return dt.astimezone(BRT).strftime("%H:%M")


# ----------------------------------------------------------------------------- regra semanal


def test_q4_2026_rebalance_dates(cfg):
    assert rebalance_schedule(date(2026, 10, 5), date(2026, 12, 31), cfg) == [
        date(2026, 10, 9), date(2026, 10, 16), date(2026, 10, 23), date(2026, 10, 30),
        date(2026, 11, 6), date(2026, 11, 13), date(2026, 11, 20), date(2026, 11, 27),
        date(2026, 12, 4), date(2026, 12, 11), date(2026, 12, 18), date(2026, 12, 24),
        date(2026, 12, 31)]
    assert date(2026, 12, 24).weekday() == 3 and date(2026, 12, 31).weekday() == 3


def test_us_holiday_friday_moves_to_thursday(cfg):
    assert rebalance_date_of_week(date(2027, 3, 22), cfg) == date(2027, 3, 25)  # Sexta Santa
    assert last_session_of_week(date(2027, 3, 26)) == date(2027, 3, 25)
    assert not is_rebalance_day(date(2027, 3, 26), cfg)


def test_next_rebalance_and_inception_key(cfg):
    assert next_rebalance_after(date(2026, 10, 5), cfg) == date(2026, 10, 9)
    assert next_rebalance_after(date(2026, 10, 9), cfg) == date(2026, 10, 16)
    assert chave_da_semana(date(2026, 10, 6), cfg) == date(2026, 10, 9) == week_id(
        date(2026, 10, 6), cfg)
    assert chave_valida(date(2026, 10, 9), cfg)
    assert not chave_valida(date(2026, 10, 5), cfg)  # segunda não é chave na regra da NYSE
    assert not chave_valida(date(2026, 10, 12), cfg)
    assert dia_de_montagem(date(2026, 10, 9), cfg) and not dia_de_montagem(date(2026, 10, 8), cfg)


def test_inception_off_rule_is_still_the_key():
    c = ativado(inception_date="2026-10-14")  # quarta: carteira inaugural fora da regra
    assert chave_valida(date(2026, 10, 14), c) and dia_de_montagem(date(2026, 10, 14), c)
    assert not dia_de_montagem(date(2026, 10, 16), c)  # na semana do início, só o início
    assert chave_da_semana(date(2026, 10, 12), c) == date(2026, 10, 14)
    assert next_rebalance_after(date(2026, 10, 14), c) == date(2026, 10, 23)


def test_legacy_rule_without_config_is_unchanged():
    assert is_rebalance_day(date(2026, 10, 13))  # 12/10 feriado na B3 ⇒ terça
    assert is_rebalance_day(date(2026, 10, 13), "BVMF")
    assert chave_valida(date(2026, 10, 5)) and not chave_valida(date(2026, 10, 9))
    assert rebalance_date_of_week(date(2026, 10, 14)) == date(2026, 10, 13)


def test_calendar_known_past_default_horizon(cfg):
    assert not is_session(date(2027, 11, 25), "XNYS")  # Thanksgiving 2027
    assert is_early_close(date(2027, 11, 26), "XNYS")
    assert rebalance_date_of_week(date(2027, 11, 22), cfg) == date(2027, 11, 26)
    assert not is_session(date(2027, 12, 24), "XNYS")  # Natal observado (sexta)
    assert rebalance_date_of_week(date(2027, 12, 20), cfg) == date(2027, 12, 23)


def test_b3_holiday_with_nyse_open_is_a_data_session():
    d = date(2026, 10, 12)
    assert not is_session(d, "BVMF") and is_session(d, "XNYS") and is_data_session(d)
    assert previous_data_session(date(2026, 10, 13)) == d
    assert previous_session(date(2026, 10, 13)) == date(2026, 10, 9)


# ----------------------------------------------------------------------------- horários


def test_official_close_table_pinned_in_brt_with_us_dst(cfg):
    oct9 = janela_execucao(date(2026, 10, 9), cfg)
    assert {m: _brt(t) for m, t in oct9.fechamentos.items()} == {
        "XNYS": "17:00", "XNAS": "17:00", "ARCX": "17:00", "BVMF": "17:00", "XMEX": "17:00",
        "XSGO": "16:00", "XBOG": "17:00", "XLIM": "17:00", "XBUE": "17:00"}
    assert {m: _brt(t) for m, t in oct9.corte_moc.items()} == {
        "XNYS": "16:50", "XNAS": "16:55", "ARCX": "16:59", "BVMF": "16:55", "XMEX": "16:40",
        "XSGO": "15:45", "XBOG": "16:55", "XLIM": "16:52", "XBUE": "16:57"}
    nov6 = janela_execucao(date(2026, 11, 6), cfg)  # depois do fim do horário de verão dos EUA
    assert {m: _brt(t) for m, t in nov6.fechamentos.items()} == {
        "XNYS": "18:00", "XNAS": "18:00", "ARCX": "18:00", "BVMF": "18:00", "XMEX": "18:00",
        "XSGO": "16:00", "XBOG": "18:00", "XLIM": "18:00", "XBUE": "17:00"}
    assert all(mercados_elegiveis(oct9, cfg).values())


def test_effective_deadline_and_early_closes(cfg):
    assert _brt(prazo_efetivo(date(2026, 10, 9), cfg)) == "15:00"
    nov27 = janela_execucao(date(2026, 11, 27), cfg)
    assert nov27.fechamento_antecipado and nov27.multiplicador_capacidade == 0.5
    assert _brt(nov27.fechamentos["XNYS"]) == "15:00" and _brt(nov27.corte_moc["XNYS"]) == "14:50"
    assert _brt(nov27.prazo_decisao) == "14:15"
    dec24 = janela_execucao(date(2026, 12, 24), cfg)
    assert _brt(dec24.prazo_decisao) == "14:15"
    assert motivo_inelegivel("XSGO", dec24, cfg)  # Santiago antecipada: fecha antes de 15h00
    # Legado (sem a seção execution): o prazo do mandato.
    legacy = load_config(LEGADO)
    assert legacy.execution is None
    assert prazo_efetivo(date(2026, 10, 9), legacy).strftime("%H:%M") == \
        legacy.fund.decision_deadline_local


def test_decision_cutoff_is_the_latest_eligible_moc_cutoff(cfg):
    from cdp.workflow.daily import close_datetime, decision_cutoff

    assert _brt(decision_cutoff(date(2026, 10, 9), cfg)) == "16:59"   # NYSE Arca
    assert _brt(close_datetime(date(2026, 10, 9), cfg)) == "17:00"
    nov27 = date(2026, 11, 27)                                           # NYSE antecipada
    assert _brt(decision_cutoff(nov27, cfg)) == "17:55"                  # B3 (call 17:55)
    assert _brt(janela_execucao(nov27, cfg).corte_moc["XNYS"]) == "14:50"
    assert _brt(close_datetime(nov27, cfg)) == "18:00"
    legacy = load_config(LEGADO)
    assert _brt(decision_cutoff(date(2026, 10, 9), legacy)) == "17:00"


def test_closed_markets_on_rebalance_days(cfg):
    nov20 = janela_execucao(date(2026, 11, 20), cfg)
    assert nov20.abertos["BVMF"] is False and nov20.abertos["XNYS"] is True
    assert "B3: sem pregão" in (motivo_inelegivel("BVMF", nov20, cfg) or "")
    dec24 = janela_execucao(date(2026, 12, 24), cfg)
    assert dec24.abertos["BVMF"] is False
    dec31 = janela_execucao(date(2026, 12, 31), cfg)
    assert {m for m, ok in dec31.abertos.items() if not ok} >= {"BVMF", "XSGO", "XBOG"}
    elig = mercados_elegiveis(dec31, cfg)
    assert elig["XNYS"] and not elig["BVMF"] and not elig["XSGO"] and not elig["XBOG"]


def test_resumo_cronograma(cfg):
    r = resumo_cronograma(cfg, date(2026, 10, 6))
    assert r["proximo_rebalanceamento"] == date(2026, 10, 9)
    assert r["dia_da_semana"] == "sexta-feira" and r["regra_codigo"] == "LAST_US_SESSION"
    assert r["prazo_decisao"] == datetime(2026, 10, 9, 15, 0, tzinfo=BRT)
    assert r["mercados_fechados"] == [] and r["fechamento_antecipado"] is False
    assert r["proximas_datas"][:2] == [date(2026, 10, 9), date(2026, 10, 16)]
    r2 = resumo_cronograma(cfg, date(2026, 11, 23))
    assert r2["proximo_rebalanceamento"] == date(2026, 11, 27)
    assert r2["fechamento_antecipado"] is True and r2["prazo_decisao"].strftime("%H:%M") == "14:15"


def test_mandate_close_table_matches_verified_sources_when_active():
    """Quando o mandato ativa a seção ``execution``, os horários são os conferidos."""
    raw = yaml.safe_load(Path("configs/cdp/fund.yaml").read_text(encoding="utf-8")) or {}
    if "execution" not in raw:
        pytest.skip("mandato sem a seção execution (regra legada)")
    cfg = load_config()
    got = {m: ct.model_dump(mode="json") for m, ct in cfg.execution.close_times.items()}
    assert got == HORARIOS_OFICIAIS
    assert cfg.fund.rebalance_weekday == "LAST_US_SESSION"
