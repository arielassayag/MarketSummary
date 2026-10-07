"""Cadência dos modelos da cobertura na agenda (``cobertura`` em ``cdp agenda``).

- dia de montagem (inclusive a carteira inaugural): retrato completo da data-base antes do
  ``weekly prepare`` (``atualizar_antes_da_decisao``, etapa ``cobertura``), sem look-ahead;
- véspera do dia de montagem: nada à noite (a manhã seguinte cobre); noite do dia de montagem sem
  a atualização: retrato completo de recuperação;
- resultado divulgado depois do último modelo ⇒ execução parcial no pregão seguinte; evento macro
  de impacto alto ⇒ execução completa no pregão que reagiu; nota de pós-resultado;
- revisão mensal no último dia de montagem do mês; o calendário macro público é válido.

Retratos de mentira (só ``manifest.json`` e ``eventos.jsonl``, o que a agenda lê); fontes de datas
de resultado e calendário macro injetados: nada de rede nem do arquivo público.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd

from cdp import rotinas as ro
from cdp.calendar import next_rebalance_after, previous_data_session
from cdp.config import load_config
from cdp.workflow import agenda as A
from cdp.workflow.runtime import Runtime

BRT = ZoneInfo("America/Sao_Paulo")
CFG = load_config()
INICIO = CFG.fund.inception_date
R2 = next_rebalance_after(INICIO, CFG)
SEM_MACRO = {"eventos": [], "publicado_ate": {}, "erro": None}


def _at(d: date, h: int, m: int = 0) -> datetime:
    return datetime.combine(d, time(h, m), BRT)


def _proximo_pregao(d: date) -> date:
    d += timedelta(days=1)
    while not A.is_close_session(d):
        d += timedelta(days=1)
    return d


def _rt(tmp: Path, at: datetime, mercado: date | None = None) -> Runtime:
    rt = Runtime(CFG, tmp / "book", tmp / "market", tmp / "reports", clock=lambda: at,
                 teses_root=None)
    rt.store_last_date = lambda: mercado  # type: ignore[method-assign]
    return rt


def _retrato(tmp: Path, d: date, *, parcial: bool = False,
             emissores: tuple[str, ...] = ("BR_AAA", "BR_BBB", "BR_CCC"),
             concluido: datetime | None = None, sintetico: bool = False) -> None:
    pasta = tmp / "book" / "cobertura" / d.isoformat()
    pasta.mkdir(parents=True)
    (pasta / "manifest.json").write_text(json.dumps(
        {"as_of": d.isoformat(), "parcial": parcial, "emissores": list(emissores),
         "is_synthetic": sintetico}), encoding="utf-8")
    quando = (concluido or _at(d, 21)).astimezone(ZoneInfo("UTC")).isoformat()
    (pasta / "eventos.jsonl").write_text(json.dumps({"concluido_em": quando}) + "\n",
                                         encoding="utf-8")


def _fonte(*linhas: tuple[str, date, bool]):
    def f(emissores, desde, ate, as_of):
        return pd.DataFrame([{"issuer_id": i, "data": d, "tipo": "resultado", "estimada": est,
                              "fonte": "CVM", "url": None, "documento": "ITR"}
                             for i, d, est in linhas])
    return f


def _cob(rt: Runtime, at: datetime, fonte=None, macro=None) -> dict:
    return A.coverage_status(rt, at, fonte_eventos=fonte or _fonte(),
                             eventos_macro=macro if macro is not None else SEM_MACRO)


# ----------------------------------------------------------------------------- dia de montagem


def test_rebalance_day_refreshes_the_models_before_the_decision(tmp_path):
    """Na carteira inaugural (e em todo dia de montagem), antes do ``weekly prepare``: retrato
    completo da data-base (o pregão anterior), nunca do próprio dia (sem look-ahead)."""
    base = previous_data_session(INICIO)
    genese = previous_data_session(base)
    _retrato(tmp_path, genese, sintetico=True)
    at = _at(INICIO, 11, 7)
    rt = _rt(tmp_path, at, mercado=base)
    cob = _cob(rt, at)
    assert cob["atualizar_antes_da_decisao"] is True
    assert cob["data_base_decisao"] == base < INICIO
    assert cob["passo_antes_da_decisao"] == f"cdp cobertura run --date {base}"
    assert cob["modelos_em_dia_para_a_decisao"] is False
    ag = A.agenda(rt, at)
    sem = ag["semanal"]
    assert sem["acao"] == "montar" and sem["etapa"] == "cobertura"
    dec = ro.avaliar_gate("semanal", ag, ro.ContextoGate(hoje=INICIO))
    assert dec.executar and "etapa=cobertura" in dec.itens
    # base de mercado ainda no pregão anterior à data-base: depois do prepare
    rt = _rt(tmp_path, at, mercado=genese)
    cob = _cob(rt, at)
    assert cob["atualizar_antes_da_decisao"] is False and cob["aguardando_base_de_mercado"]
    assert A.agenda(rt, at)["semanal"]["etapa"] == "prepare"
    # pouco tempo até o prazo efetivo: a decisão não espera a cobertura
    tarde = _at(INICIO, 13, 30)
    cob = _cob(_rt(tmp_path, tarde, mercado=base), tarde)
    assert cob["atualizar_antes_da_decisao"] is False
    assert "minutos até o prazo" in cob["motivo_antes_da_decisao"]
    # retrato completo da data-base já gravado: modelos em dia
    _retrato(tmp_path, base, sintetico=True)
    cob = _cob(_rt(tmp_path, at, mercado=base), at)
    assert cob["atualizar_antes_da_decisao"] is False and cob["modelos_em_dia_para_a_decisao"]


def test_eve_defers_to_the_morning_and_the_rebalance_night_recovers(tmp_path):
    base = previous_data_session(INICIO)
    genese = previous_data_session(base)
    _retrato(tmp_path, genese)
    macro = {"eventos": [_ev("x", base, time(9, 0), "alto")], "publicado_ate": {}, "erro": None}
    fonte = _fonte(("BR_AAA", base, False))
    noite = _at(base, 19, 30)
    cob = _cob(_rt(tmp_path, noite, mercado=base), noite, fonte, macro)
    assert cob["snapshot_pendente"] is False and cob["adiado_para_a_decisao"] == INICIO
    assert cob["motivos"] and "véspera do dia de montagem" in cob["motivo"]
    noite = _at(INICIO, 19, 30)
    cob = _cob(_rt(tmp_path, noite, mercado=INICIO), noite)
    assert cob["snapshot_pendente"] is True and cob["tipo"] == "completo"
    assert cob["data"] == INICIO and cob["passo"] == f"cdp cobertura run --date {INICIO}"
    assert any("não foi gravada" in m for m in cob["motivos"])
    # com a atualização da manhã gravada, a noite do dia de montagem fica livre
    _retrato(tmp_path, base, concluido=_at(INICIO, 11, 15))
    cob = _cob(_rt(tmp_path, noite, mercado=INICIO), noite)
    assert cob["snapshot_pendente"] is False and "em dia" in cob["motivo"]


def test_genesis_without_any_snapshot(tmp_path):
    noite_d = previous_data_session(previous_data_session(INICIO))
    assert noite_d >= A.COBERTURA_INICIO
    noite = _at(noite_d, 19, 30)
    cob = _cob(_rt(tmp_path, noite, mercado=noite_d), noite)
    assert cob["snapshot_pendente"] and cob["tipo"] == "completo"
    assert any("gênese" in m for m in cob["motivos"])


# ----------------------------------------------------------------------------- ad hoc


def _semana_seguinte() -> tuple[date, date]:
    """Dois pregões depois da carteira inaugural, antes da véspera da montagem seguinte."""
    n1 = _proximo_pregao(INICIO)
    n2 = _proximo_pregao(n1)
    assert n2 < previous_data_session(R2)
    return n1, n2


def test_results_after_the_model_ask_for_a_partial_run(tmp_path):
    n1, _n2 = _semana_seguinte()
    _retrato(tmp_path, INICIO, concluido=_at(INICIO, 21, 30))  # mesma noite do dia do resultado
    fonte = _fonte(("BR_AAA", INICIO, False),      # divulgado no dia do modelo, à noite
                   ("BR_BBB", n1, True),           # data estimada: nunca dispara
                   ("BR_ZZZ", n1, False))          # fora da cobertura
    noite = _at(n1, 19, 30)
    cob = _cob(_rt(tmp_path, noite, mercado=n1), noite, fonte)
    assert cob["snapshot_pendente"] and cob["tipo"] == "parcial"
    assert cob["emissores"] == ["BR_AAA"] and cob["data"] == n1
    assert cob["passo"] == f"cdp cobertura run --date {n1} --emissores BR_AAA"
    assert cob["adhoc"]["itens"][0]["fonte"] == "CVM"
    # modelo concluído na manhã seguinte (atualização do dia de montagem): já incorporado
    (tmp_path / "book" / "cobertura" / INICIO.isoformat() / "eventos.jsonl").write_text(
        json.dumps({"concluido_em": _at(n1, 11).isoformat()}) + "\n", encoding="utf-8")
    cob = _cob(_rt(tmp_path, noite, mercado=n1), noite, fonte)
    assert cob["snapshot_pendente"] is False and cob["adhoc"]["emissores"] == []


def test_many_results_become_a_full_run(tmp_path):
    n1, _n2 = _semana_seguinte()
    ids = tuple(f"BR_E{i:03d}" for i in range(A.MAX_EMISSORES_PARCIAL + 1))
    _retrato(tmp_path, INICIO, emissores=ids, concluido=_at(n1, 9))
    fonte = _fonte(*((i, n1, False) for i in ids))
    noite = _at(n1, 19, 30)
    cob = _cob(_rt(tmp_path, noite, mercado=n1), noite, fonte)
    assert cob["tipo"] == "completo" and cob["emissores"] is None
    assert len(cob["adhoc"]["emissores"]) == len(ids)


def test_unavailable_result_dates_are_a_failure_not_zero(tmp_path):
    n1, _n2 = _semana_seguinte()
    _retrato(tmp_path, INICIO)

    def quebra(*_a):
        raise FileNotFoundError("arquivo público local ausente neste clone")

    noite = _at(n1, 19, 30)
    cob = _cob(_rt(tmp_path, noite, mercado=n1), noite, quebra)
    assert cob["adhoc"]["falha"] and "indisponíveis" in cob["adhoc"]["falha"]
    assert cob["adhoc"]["emissores"] == [] and cob["snapshot_pendente"] is False


def test_post_result_notes_follow_the_reassessed_models(tmp_path):
    n1, n2 = _semana_seguinte()
    _retrato(tmp_path, INICIO, concluido=_at(n1, 9))
    _retrato(tmp_path, n1, parcial=True, emissores=("BR_AAA",), concluido=_at(n1, 21))
    fonte = _fonte(("BR_AAA", INICIO, False))
    noite = _at(n2, 19, 30)
    rt = _rt(tmp_path, noite, mercado=n2)
    cob = _cob(rt, noite, fonte)
    assert cob["adhoc"]["emissores"] == []  # o parcial de n1 já incorporou o resultado
    assert [x["issuer_id"] for x in cob["notas_pos_resultado"]] == ["BR_AAA"]
    assert cob["notas_pos_resultado"][0]["modelo"] == n1
    nota = tmp_path / "book" / "cobertura" / "notas" / "BR_AAA" / n1.isoformat()
    nota.mkdir(parents=True)
    (nota / "nota_publicada.json").write_text("{}", encoding="utf-8")
    assert _cob(rt, noite, fonte)["notas_pos_resultado"] == []


# ----------------------------------------------------------------------------- macro


def _ev(nome: str, d: date, hora: time | None, impacto: str, fuso: str = "America/Sao_Paulo"):
    ev = {"id": f"{nome}-{d}", "serie": nome, "data": d, "hora": hora, "fuso": fuso, "pais": "BR",
          "orgao": "BCB", "nome": nome, "impacto": impacto,
          "fonte": "https://www.bcb.gov.br/controleinflacao/calendarioreunioescopom"}
    ev["sessao_de_reacao"] = A.sessao_de_reacao(ev)
    return ev


def test_reaction_session_of_a_macro_event():
    quarta = date(2026, 11, 4)
    assert A.sessao_de_reacao(_ev("copom", quarta, time(18, 30), "alto")) == date(2026, 11, 5)
    assert A.sessao_de_reacao(_ev("ipca", quarta, time(9, 0), "alto")) == quarta
    assert A.sessao_de_reacao(_ev("fomc", quarta, time(14, 0), "alto",
                                  "America/New_York")) == quarta
    assert A.sessao_de_reacao(_ev("sem_hora", quarta, None, "alto")) == date(2026, 11, 5)
    sabado = date(2026, 11, 7)
    assert A.sessao_de_reacao(_ev("sabado", sabado, time(9, 0), "alto")) == date(2026, 11, 9)


def test_high_impact_macro_event_asks_for_a_full_run(tmp_path):
    n1, _n2 = _semana_seguinte()
    _retrato(tmp_path, INICIO, concluido=_at(n1, 9))
    alto = _ev("copom", n1, time(9, 0), "alto")
    medio = _ev("bcch", n1, time(9, 0), "medio")
    noite = _at(n1, 19, 30)
    rt = _rt(tmp_path, noite, mercado=n1)
    cob = _cob(rt, noite, macro={"eventos": [medio], "publicado_ate": {}, "erro": None})
    assert cob["snapshot_pendente"] is False and cob["macro"]["pendentes"] == []
    cob = _cob(rt, noite, macro={"eventos": [alto, medio], "publicado_ate": {}, "erro": None})
    assert cob["snapshot_pendente"] and cob["tipo"] == "completo"
    assert [e["id"] for e in cob["macro"]["pendentes"]] == [alto["id"]]
    # coberto por um retrato completo da sessão de reação: nada pendente
    _retrato(tmp_path, n1, concluido=_at(n1, 21))
    cob = _cob(rt, noite, macro={"eventos": [alto], "publicado_ate": {}, "erro": None})
    assert cob["snapshot_pendente"] is False and cob["macro"]["pendentes"] == []


def test_public_macro_calendar_is_valid():
    m = A.carregar_eventos_macro()
    assert m["erro"] is None and m["eventos"]
    series = {e["serie"] for e in m["eventos"]}
    assert {"copom", "ipca", "fomc", "cpi_eua", "banxico", "inegi_inpc", "bcch",
            "banrep"} <= series
    oficiais = ("bcb.gov.br", "ibge.gov.br", "federalreserve.gov", "bls.gov", "banxico.org.mx",
                "inegi.org.mx", "bcentral.cl", "banrep.gov.co")
    for e in m["eventos"]:
        assert date(2026, 10, 1) <= e["data"] <= date(2027, 12, 31), e["id"]
        host = urlparse(e["fonte"]).hostname or ""
        assert e["fonte"].startswith("https://") and host.endswith(oficiais), e["fonte"]
        assert e["impacto"] in A.IMPACTOS_MACRO and e["sessao_de_reacao"] >= e["data"]
    for s in ("copom", "ipca", "fomc", "cpi_eua", "banxico"):
        datas = [e["data"] for e in m["eventos"] if e["serie"] == s]
        assert all(e["impacto"] == "alto" for e in m["eventos"] if e["serie"] == s)
        assert any(d.year == 2026 and d.month in (11, 12) for d in datas), s
        assert s in m["publicado_ate"]
    assert len({e["id"] for e in m["eventos"]}) == len(m["eventos"])
    assert m["lacunas"]  # calendário não publicado fica ausente e declarado (nunca estimado)


# ----------------------------------------------------------------------------- rotinas e revisão


def test_daily_gate_runs_the_pending_snapshot(tmp_path):
    n1, _n2 = _semana_seguinte()
    _retrato(tmp_path, INICIO, concluido=_at(INICIO, 21))
    noite = _at(n1, 19, 30)
    cob = _cob(_rt(tmp_path, noite, mercado=n1), noite, _fonte(("BR_AAA", n1, False)))
    ag = {"fase": "operacao", "cobertura": cob}
    dec = ro.avaliar_gate("diario", ag, ro.ContextoGate(hoje=n1))
    assert dec.executar and any("retrato da cobertura" in i for i in dec.itens)


def test_monthly_review_on_the_last_rebalance_of_the_month(tmp_path):
    from cdp.cobertura import revisao

    ultimo = revisao.ultimo_rebalanceamento_do_mes(INICIO.year, INICIO.month, CFG)
    assert ultimo is not None and ultimo >= INICIO
    _retrato(tmp_path, INICIO)
    antes = A.monthly_review_status(_rt(tmp_path, _at(ultimo, 11)), _at(ultimo, 11))
    assert antes["pendente"] is False and antes["proxima"] == ultimo
    noite = _at(ultimo, 19, 30)
    st = A.monthly_review_status(_rt(tmp_path, noite), noite)
    assert st["pendente"] and st["data"] == ultimo and st["etapa"] == "preparar"
    assert f"revisao-mensal preparar --date {ultimo}" in st["passos"]
    seguinte = _at(_proximo_pregao(ultimo), 19, 30)
    assert A.monthly_review_status(_rt(tmp_path, seguinte), seguinte)["pendente"]  # retomada
    pub = revisao.pasta_revisao(tmp_path / "book", ultimo)
    pub.mkdir(parents=True)
    (pub / revisao.PUBLICADA_JSON).write_text("{}", encoding="utf-8")
    assert A.monthly_review_status(_rt(tmp_path, seguinte), seguinte)["pendente"] is False
    assert revisao.e_ultimo_rebalanceamento_do_mes(ultimo, CFG)
    assert not revisao.e_ultimo_rebalanceamento_do_mes(INICIO, CFG) or INICIO == ultimo
