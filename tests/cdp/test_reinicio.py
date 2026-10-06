"""Pré-início do fundo (``cdp reinicio``), agenda e painel antes da data de início, offline.

Livro sintético da demonstração (DADOS SIMULADOS) em pasta temporária, com datas anteriores à
data de início do mandato. Cobre: o plano (simulação sem gravar), a execução (trilha nova com a
gênese, ``verify`` íntegro), a idempotência, as guardas (chave viva na data de início ou depois,
área temporária de execução interrompida, ``verify`` com falha), a reversão em caso de falha, a
agenda e o monitor de risco antes do início, a carteira inaugural numa sexta e o painel de
pré-início.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import warnings
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cdp.__main__ import main
from cdp.audit import AuditLog
from cdp.calendar import (
    chave_da_semana,
    chave_valida,
    dia_de_montagem,
    proximas_montagens,
    week_id,
)
from cdp.config import FundConfig, load_config
from cdp.hashing import sha256_obj
from cdp.workflow.agenda import agenda
from cdp.workflow.book import GENESIS_EVENT, GENESIS_FILE, Book, _check_week
from cdp.workflow.demo import (
    DEMO_HISTORY_START,
    DEMO_MIND,
    DEMO_SEED,
    DemoStore,
    run_demo,
    write_demo_inputs,
)
from cdp.workflow.reinicio import MOTIVO_KILL_SWITCH, STAGING_NAME, executar, plano, situacao
from cdp.workflow.risk_monitor import PRE_INICIO, run_risk_monitor
from cdp.workflow.runtime import Runtime

ROOT = Path(__file__).resolve().parents[2]
FUND = ROOT / "configs" / "cdp" / "fund.yaml"
# Mandato com a regra legada (primeiro pregão da semana na B3): o livro de demonstração e a
# mecânica do pré-início (plano, execução, guardas) usam datas fixas (semana 2024-03-04).
LEGADO = Path(__file__).resolve().parent / "fixtures" / "fund_legado.yaml"
BRT = ZoneInfo("America/Sao_Paulo")
INICIO = date(2026, 10, 9)  # sexta-feira
WEEK = date(2024, 3, 4)


def _cfg(inicio: date = INICIO, fonte: Path = FUND) -> FundConfig:
    """Mandato de ``fonte`` com a data de início dada. Padrão: o mandato ATIVADO do repositório
    (montagem no último pregão da semana na NYSE, prazo efetivo das 15:00)."""
    cfg = load_config(fonte)
    return cfg.model_copy(update={"fund": cfg.fund.model_copy(
        update={"inception_date": inicio})})


def _legado(inicio: date = INICIO) -> FundConfig:
    """Mandato legado (:data:`LEGADO`) com a data de início dada, para as datas esperadas da
    mecânica não dependerem da regra em vigor."""
    return _cfg(inicio, LEGADO)


def _at(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=BRT)


def _rt(root: Path, cfg: FundConfig | None = None, **kw) -> Runtime:
    return Runtime(cfg or _legado(), root / "book", root / "market", root / "reports",
                   teses_root=None, **kw)


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("cdp_reinicio_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_demo(out, days=2, cfg=load_config(LEGADO))
    # Material de pesquisa datado, risco datado e pesquisa de metodologia (mantida).
    (out / "pesquisa" / "2024-03-04").mkdir(parents=True)
    (out / "pesquisa" / "2024-03-04" / "notas.json").write_text('{"x": 1}\n', encoding="utf-8")
    (out / "pesquisa" / "LEIAME.md").write_text("pasta de material da mente\n", encoding="utf-8")
    (out / "reports" / "risk" / "2024-03-05").mkdir(parents=True)
    (out / "reports" / "risk" / "2024-03-05" / "risco_1900.md").write_text("risco\n",
                                                                            encoding="utf-8")
    (out / "reports" / "backtest" / "calib").mkdir(parents=True)
    (out / "reports" / "backtest" / "calib" / "metrics.json").write_text("{}\n", encoding="utf-8")
    return out


@pytest.fixture
def copia(demo, tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(demo, root)
    return root


# ----------------------------------------------------------------------------- plano


def test_plan_is_a_dry_run_listing_every_file(copia):
    rt = _rt(copia)
    before = _tree(copia)
    p = plano(rt, copia / "pesquisa")
    assert p.estado == "pendente" and p.chaves_anteriores[0] == WEEK
    # Caminhos relativos à pasta que contém o livro (a raiz do repositório), em qualquer cwd.
    files = {x["caminho"] for x in p.manifesto()}
    assert "book/audit_log.jsonl" in files and "book/2024-03-04/booked.json" in files
    assert any(f.startswith("book/track_record/records/") for f in files)
    assert any(f.startswith("reports/daily/2024-03-04/") for f in files)
    assert any(f.startswith("reports/weekly/2024-03-04/") for f in files)
    assert "reports/risk/2024-03-05/risco_1900.md" in files
    assert "pesquisa/2024-03-04/notas.json" in files
    assert not any(f.startswith(("reports/backtest", "pesquisa/LEIAME")) for f in files)
    kept = {Path(m["caminho"]).name for m in p.mantidos}
    assert {"backtest", "LEIAME.md", "market"} <= kept
    assert all(len(x["sha256"]) == 64 for x in p.manifesto())
    assert situacao(rt) == {"pendente": True, "motivo": situacao(rt)["motivo"]}
    assert _tree(copia) == before  # simulação não grava nada
    # Ordem de remoção: relatórios e pesquisa antes; no livro, as chaves (semanas e
    # track_record*) por último — uma interrupção nunca deixa um livro sem chaves nem gênese.
    names = [a.relative_to(copia).as_posix() for a in p.alvos]
    i_book = next(i for i, n in enumerate(names) if n.startswith("book/"))
    assert all(not n.startswith("book/") for n in names[:i_book])
    assert all(n.startswith("book/") for n in names[i_book:])
    assert names[-3:] == ["book/2024-03-04", "book/track_record", "book/track_record_shadow"]


def test_manifest_hash_is_independent_of_cwd(copia, tmp_path, monkeypatch):
    rt = _rt(copia)
    monkeypatch.chdir(copia)
    here = plano(rt, copia / "pesquisa").manifesto()
    monkeypatch.chdir(tmp_path)
    assert plano(rt, copia / "pesquisa").manifesto() == here
    assert all(not x["caminho"].startswith("/") for x in here)


def test_cli_dry_run_prints_plan_without_writing(copia, monkeypatch, capsys):
    cfg_path = copia.parent / "fund_inicio.yaml"
    _write_cfg(cfg_path, INICIO, LEGADO)
    monkeypatch.chdir(copia)
    before = _tree(copia)
    rc = main(["--config", str(cfg_path), "reinicio"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["executado"] is False and out["estado"] == "pendente"
    assert out["carteira_inaugural"] == "09/10/2026"
    assert "book/2024-03-04/booked.json" in {x["caminho"] for x in out["remover"]}
    assert out["lista_sha256"] == sha256_obj(out["remover"])
    assert _tree(copia) == before


def _write_cfg(path: Path, inicio: date, fonte: Path = FUND) -> None:
    import yaml

    raw = yaml.safe_load(fonte.read_text(encoding="utf-8"))
    raw["fund"]["inception_date"] = inicio.isoformat()
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")


# ----------------------------------------------------------------------------- execução


def test_execute_opens_fresh_chain_and_is_idempotent(copia):
    rt = _rt(copia, clock=lambda: datetime(2026, 10, 6, 22, 22, tzinfo=UTC))
    manifest = plano(rt, copia / "pesquisa").manifesto()
    audit_sha = hashlib.sha256((copia / "book" / "audit_log.jsonl").read_bytes()).hexdigest()
    code, out = executar(rt, copia / "pesquisa")
    assert code == 0 and out["executado"] is True, out["motivo"]
    assert sorted(p.name for p in (copia / "book").iterdir()) == ["audit_log.jsonl", GENESIS_FILE]
    assert not (copia / "reports" / "daily" / "2024-03-04").exists()
    assert not (copia / "reports" / "weekly" / "2024-03-04").exists()
    assert not (copia / "reports" / "risk" / "2024-03-05").exists()
    assert not (copia / "pesquisa" / "2024-03-04").exists()
    assert (copia / "reports" / "backtest" / "calib" / "metrics.json").exists()
    assert (copia / "pesquisa" / "LEIAME.md").exists()
    assert not (copia / STAGING_NAME).exists()

    events = AuditLog(copia / "book" / "audit_log.jsonl").events()
    assert [e.event_type for e in events] == [GENESIS_EVENT] and events[0].seq == 0
    assert "09/10/2026" in events[0].summary
    raw = (copia / "book" / GENESIS_FILE).read_text(encoding="utf-8")
    gen = json.loads(raw)
    assert sha256_obj(gen) == events[0].payload_hash
    # Gênese enxuta: só o necessário para conferir a abertura do livro (DESIGN §15.2).
    assert set(gen) == {"inception_date", "config_hash", "codigo", "ancora_sha256"}
    assert gen["inception_date"] == "2026-10-09" and gen["config_hash"] == rt.cfg.config_hash()
    assert gen["ancora_sha256"] == audit_sha
    for word in ("anterior", "removid", "arquivos", "lista", "reinicio", "reinício"):
        assert word not in raw.lower(), word
    # O manifesto (n.º de arquivos e sha256 da lista) fica só na saída do comando.
    prev = out["estado_anterior"]
    assert prev["audit_log_sha256"] == audit_sha
    assert prev["n_arquivos_removidos"] == len(manifest) == out["n_arquivos"]
    assert prev["lista_sha256"] == sha256_obj(manifest) == out["lista_sha256"]
    assert gen["codigo"] == prev["git_head"]
    ok, msgs = rt.verify_all()
    assert ok, msgs
    assert situacao(rt) == {"pendente": False, "motivo": None}

    snap = _tree(copia)
    code2, out2 = executar(rt, copia / "pesquisa")
    assert code2 == 0 and out2["executado"] is False and out2["estado"] == "iniciado"
    assert "nada a fazer" in out2["motivo"] and _tree(copia) == snap


def test_genesis_tampering_is_detected(copia):
    rt = _rt(copia, clock=lambda: datetime(2026, 10, 6, 22, 22, tzinfo=UTC))
    assert executar(rt, copia / "pesquisa")[0] == 0
    path = copia / "book" / GENESIS_FILE
    gen = json.loads(path.read_text(encoding="utf-8"))
    gen["inception_date"] = "2026-10-16"
    path.write_text(json.dumps(gen), encoding="utf-8")
    ok, msgs = Book(copia / "book").verify_integrity()
    assert not ok and any(GENESIS_FILE in m for m in msgs)
    path.unlink()
    ok, msgs = Book(copia / "book").verify_integrity()
    assert not ok and any("sem o arquivo" in m for m in msgs)


def test_guard_refuses_live_key_on_or_after_inception(copia):
    rt = _rt(copia, cfg=_legado(date(2024, 3, 5)))  # registro de 05/03 = data de início
    before = _tree(copia)
    p = plano(rt, copia / "pesquisa")
    assert p.estado == "conflito" and p.chaves_posteriores == [date(2024, 3, 5)]
    code, out = executar(rt, copia / "pesquisa")
    assert code == 1 and out["executado"] is False and "recusado" in out["motivo"]
    assert _tree(copia) == before


def test_guard_refuses_leftover_staging_area(copia):
    (copia / STAGING_NAME).mkdir()
    rt = _rt(copia)
    before = _tree(copia)
    code, out = executar(rt, copia / "pesquisa")
    assert code == 1 and "execução interrompida" in out["motivo"]
    assert _tree(copia) == before


def test_guard_refuses_when_verify_fails(copia):
    path = copia / "book" / "2024-03-04" / "booked.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"nav_usd"', '"nav_usd" ', 1),
                    encoding="utf-8")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["nav_usd"] = raw["nav_usd"] * 2
    path.write_text(json.dumps(raw), encoding="utf-8")
    rt = _rt(copia)
    before = _tree(copia)
    code, out = executar(rt, copia / "pesquisa")
    assert code == 1 and "antes do pré-início" in out["motivo"]
    assert _tree(copia) == before and not (copia / STAGING_NAME).exists()


def test_guard_refuses_while_kill_switch_is_on(copia, capsys):
    """O pré-início nunca desliga o kill switch (só o gestor, à mão): recusa sem mexer em nada."""
    rt = _rt(copia, clock=lambda: datetime(2026, 10, 6, 18, 0, tzinfo=UTC))
    rt.set_kill_switch(True, "gestor: suspender operações até revisão", "gestor")
    before = _tree(copia)
    sit = situacao(rt)
    assert sit["pendente"] is True and "kill switch ativo" in sit["motivo"]
    p = plano(rt, copia / "pesquisa")
    assert p.estado == "conflito" and p.motivo == MOTIVO_KILL_SWITCH
    code, out = executar(rt, copia / "pesquisa")
    assert code == 1 and out["executado"] is False and "kill switch ativo" in out["motivo"]
    assert _tree(copia) == before and rt.kill_switch_active()
    a = agenda(rt, _at(date(2026, 10, 6), 19, 30))
    assert a["kill_switch"] is True and a["reinicio"]["pendente"] is True
    cfg_path = copia.parent / "fund_inicio.yaml"
    _write_cfg(cfg_path, INICIO, LEGADO)
    base = ["--book", str(copia / "book"), "--market", str(copia / "market"),
            "--reports", str(copia / "reports")]
    assert main(["--config", str(cfg_path), *base, "reinicio", "--executar"]) == 1
    assert "kill switch ativo" in json.loads(capsys.readouterr().out)["motivo"]
    assert _tree(copia) == before


@pytest.mark.parametrize("depois_de_mover", [False, True])
def test_interrupted_run_restores_everything_and_propagates(copia, monkeypatch, depois_de_mover):
    """Ctrl-C (ou SystemExit) no meio da remoção — inclusive no instante entre mover um caminho
    e registrá-lo: tudo volta ao lugar (pelo conteúdo da área temporária) e a interrupção
    segue."""
    import cdp.workflow.reinicio as mod

    rt = _rt(copia)
    before = _tree(copia)
    real = shutil.move
    calls = {"n": 0}

    def move(src, dst):
        calls["n"] += 1
        if calls["n"] == 5:
            if depois_de_mover:
                real(src, dst)
            raise KeyboardInterrupt
        return real(src, dst)

    monkeypatch.setattr(mod.shutil, "move", move)
    with pytest.raises(KeyboardInterrupt):
        executar(rt, copia / "pesquisa")
    monkeypatch.setattr(mod.shutil, "move", real)
    assert _tree(copia) == before and not (copia / STAGING_NAME).exists()
    assert situacao(rt)["pendente"] is True and "cdp reinicio --executar" in situacao(rt)["motivo"]


@pytest.mark.parametrize("n_movidos", [1, None])
def test_hard_kill_leftover_is_detected_everywhere(copia, capsys, n_movidos):
    """Execução morta sem reversão (energia, sessão fechada): a área temporária denuncia a
    interrupção antes de tudo — mesmo com o livro já vazio e sem gênese (``n_movidos=None``:
    todos os caminhos movidos)."""
    rt = _rt(copia)
    alvos = plano(rt, copia / "pesquisa").alvos
    staging = copia / STAGING_NAME
    staging.mkdir()
    for i, alvo in enumerate(alvos[:n_movidos]):
        shutil.move(str(alvo), str(staging / f"{i:04d}_{alvo.name}"))
    if n_movidos is None:
        assert not any((copia / "book").iterdir())  # livro vazio, sem gênese nem chaves
    before = _tree(copia)
    sit = situacao(rt)
    assert sit["pendente"] is True and "execução interrompida" in sit["motivo"]
    p = plano(rt, copia / "pesquisa")
    assert p.estado == "conflito" and "execução interrompida" in p.motivo
    code, out = executar(rt, copia / "pesquisa")
    assert code == 1 and out["executado"] is False and "execução interrompida" in out["motivo"]
    assert agenda(rt, _at(date(2026, 10, 6), 19, 30))["reinicio"]["pendente"] is True
    cfg_path = copia.parent / "fund_inicio.yaml"
    _write_cfg(cfg_path, INICIO, LEGADO)
    base = ["--book", str(copia / "book"), "--market", str(copia / "market"),
            "--reports", str(copia / "reports")]
    assert main(["--config", str(cfg_path), *base, "daily", "--date", "2026-10-06",
                 "--offline"]) == 1
    assert main(["--config", str(cfg_path), *base, "weekly", "prepare", "--date", "2026-10-09",
                 "--mind", "claude-code", "--offline"]) == 1
    assert main(["--config", str(cfg_path), *base, "reinicio", "--executar"]) == 1
    assert capsys.readouterr().err.count("execução interrompida") == 2
    assert _tree(copia) == before


def test_failure_after_moving_rolls_everything_back(copia, monkeypatch):
    rt = _rt(copia)
    before = _tree(copia)
    calls = {"n": 0}
    real = Runtime.verify_all

    def verify(self):
        calls["n"] += 1
        return real(self) if calls["n"] == 1 else (False, ["falha simulada"])

    monkeypatch.setattr(Runtime, "verify_all", verify)
    code, out = executar(rt, copia / "pesquisa")
    assert code == 1 and "estado anterior restaurado" in out["motivo"]
    assert _tree(copia) == before and not (copia / STAGING_NAME).exists()


def test_empty_book_has_nothing_to_do(tmp_path):
    rt = _rt(tmp_path)
    code, out = executar(rt, tmp_path / "pesquisa")
    assert code == 0 and out["estado"] == "nada" and not (tmp_path / "book").exists()
    assert situacao(rt) == {"pendente": False, "motivo": None}


# ----------------------------------------------------------------------------- calendário


def test_inception_date_is_always_an_assembly_day_even_on_friday():
    """Data de início fora da regra semanal (sexta na regra legada de segunda): ainda assim, dia
    de montagem e chave válida do livro."""
    cfg = _legado()
    assert dia_de_montagem(INICIO, cfg) and not dia_de_montagem(date(2026, 10, 5), cfg)
    assert chave_da_semana(date(2026, 10, 6), cfg) == INICIO == week_id(date(2026, 10, 6), cfg)
    assert chave_valida(INICIO, cfg) and not chave_valida(date(2026, 10, 8), cfg)
    assert not chave_valida(INICIO)  # sem configuração: só a regra semanal (legado)
    _check_week(INICIO, cfg)
    with pytest.raises(ValueError):
        _check_week(INICIO)
    # Depois do início, a regra semanal (12/10 é feriado na B3: terça 13/10).
    assert list(proximas_montagens(date(2026, 10, 6), cfg, semanas=1)) == [INICIO,
                                                                           date(2026, 10, 13)]
    assert chave_da_semana(date(2026, 10, 14), cfg) == date(2026, 10, 13)


def test_friday_inception_runs_end_to_end(tmp_path):
    """Carteira inaugural numa sexta (mercado sintético): prepare, decide e execução no
    fechamento do mesmo dia; a chave do livro é a sexta (mesmo na regra legada de segunda)."""
    from cdp.data.synthetic import make_synthetic_market

    friday = date(2024, 3, 8)
    cfg = _legado(friday)
    md = make_synthetic_market(seed=DEMO_SEED, start=DEMO_HISTORY_START, as_of=friday)
    clock = {"now": _at(friday, 11)}
    rt = _rt(tmp_path, cfg=cfg, store_override=DemoStore(md),
             clock=lambda: clock["now"].astimezone(UTC))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert agenda(rt, _at(friday, 11, 7))["semanal"]["acao"] == "montar"
        rt.weekly_prepare(friday, mind=DEMO_MIND, live=False)
        clock["now"] = _at(friday, 12)
        write_demo_inputs(rt, friday)
        clock["now"] = _at(friday, 15)
        rt.weekly_decide(friday, mind=DEMO_MIND)
        clock["now"] = _at(friday, 19, 20)
        close = rt.daily_close(friday, live=False, mind=DEMO_MIND)
    assert close["status"] == "registrado" and close["efetivacao"]
    assert rt.book.list_weeks() == [friday] and rt.book.load_booked(friday) is not None
    rec = rt.track().last()
    assert rec.date == friday and rec.live_book_week == friday
    assert not any("difere da data do mandato" in a for a in rec.alerts)
    ok, msgs = rt.verify_all()
    assert ok, msgs


# ----------------------------------------------------------------------------- agenda e risco


def _iniciado(tmp_path: Path, inicio: date = INICIO, **kw) -> Runtime:
    """Livro depois do pré-início: só a gênese."""
    rt = _rt(tmp_path, cfg=_cfg(inicio), clock=lambda: datetime(2026, 10, 6, 22, 22, tzinfo=UTC),
             **kw)
    book = Book(tmp_path / "book", config=rt.cfg)
    payload = {"inception_date": inicio.isoformat(), "config_hash": rt.cfg.config_hash(),
               "codigo": None, "ancora_sha256": None}
    from cdp.workflow.book import dump_json

    (tmp_path / "book" / GENESIS_FILE).write_text(dump_json(payload), encoding="utf-8")
    book.audit.append(GENESIS_EVENT, "CDP", payload, summary="Gênese do fundo.",
                      ts=datetime(2026, 10, 6, 22, 22, tzinfo=UTC))
    return rt


def test_agenda_before_inception(tmp_path):
    """Mandato ativado: a carteira inaugural é decidida na sexta 09/10 até o prazo efetivo das
    15:00 (teto local; o fechamento mais cedo entre NYSE/B3/BMV − 45 min é 16:15)."""
    rt = _iniciado(tmp_path)
    assert rt.cfg.fund.rebalance_weekday == "LAST_US_SESSION"
    a = agenda(rt, _at(date(2026, 10, 6), 19, 30))
    assert a["fase"] == "pre_inicio" and a["data_de_inicio"] == INICIO
    assert a["reinicio"] == {"pendente": False, "motivo": None}
    assert a["semanal"]["acao"] == "aguardar" and a["semanal"]["semana"] == INICIO
    assert a["semanal"]["motivo"].startswith("pré-início: carteira inaugural em 09/10/2026 "
                                             "(sexta-feira)")
    assert a["semanal"]["proximo_rebalanceamento"] == INICIO
    assert a["semanal"]["prazo_efetivo"] == _at(INICIO, 15, 0)
    assert a["fechamentos_pendentes"] == [] and a["publicacoes_pendentes"] == []
    first = a["proximos_eventos"][0]
    assert first["evento"].startswith("carteira inaugural")
    assert first["quando"] == _at(INICIO, 15, 0)
    assert all(e["quando"].date() >= INICIO for e in a["proximos_eventos"])


def test_agenda_on_inception_friday(tmp_path):
    rt = _iniciado(tmp_path)
    early = agenda(rt, _at(INICIO, 10))
    assert early["fase"] == "operacao" and early["semanal"]["acao"] == "aguardar"
    a = agenda(rt, _at(INICIO, 11, 7))["semanal"]
    assert a["acao"] == "montar" and a["etapa"] == "prepare" and a["semana"] == INICIO
    assert a["minutos_ate_o_prazo"] == 233  # 11:07 → 15:00 (prazo efetivo)
    assert agenda(rt, _at(INICIO, 14, 59))["semanal"]["acao"] == "montar"
    late = agenda(rt, _at(INICIO, 15, 0))["semanal"]
    assert late["acao"] == "prazo_vencido" and "prazo efetivo de 15:00" in late["motivo"]


def test_agenda_flags_pending_reset(copia):
    rt = _rt(copia)
    a = agenda(rt, _at(date(2026, 10, 6), 19, 30))
    assert a["reinicio"]["pendente"] is True and "cdp reinicio --executar" in a["reinicio"]["motivo"]


def test_daily_and_risk_before_inception(tmp_path, capsys):
    rt = _iniciado(tmp_path)
    out = rt.daily_close(date(2026, 10, 6), live=False)
    assert out["status"] == "pré-início" and "09/10/2026" in out["motivo"]
    res = run_risk_monitor(rt, as_of=date(2026, 10, 6), now=_at(date(2026, 10, 6), 14))
    assert res["status"] == PRE_INICIO and "09/10/2026" in res["mensagem"]
    assert res["gatilhos"] == [] and res["acoes_recomendadas"] == []
    base = ["--book", str(tmp_path / "book"), "--market", str(tmp_path / "market"),
            "--reports", str(tmp_path / "reports")]
    cfg_path = tmp_path / "fund_inicio.yaml"
    _write_cfg(cfg_path, INICIO)
    assert main(["--config", str(cfg_path), *base, "risk", "--date", "2026-10-06"]) == 0
    assert json.loads(capsys.readouterr().out)["relatorio"] is None
    assert not (tmp_path / "reports").exists()
    assert main(["--config", str(cfg_path), *base, "weekly", "prepare", "--date", "2026-10-07",
                 "--mind", "claude-code"]) == 0
    assert "Pré-início" in capsys.readouterr().out and not (tmp_path / "book" / "2026-10-07").exists()


def test_cli_refuses_assembly_and_close_while_reset_pending(copia, capsys):
    base = ["--book", str(copia / "book"), "--market", str(copia / "market"),
            "--reports", str(copia / "reports")]
    cfg_path = copia.parent / "fund_inicio.yaml"
    _write_cfg(cfg_path, INICIO, LEGADO)
    before = _tree(copia / "book")
    assert main(["--config", str(cfg_path), *base, "weekly", "prepare", "--date", "2026-10-09",
                 "--mind", "claude-code", "--offline"]) == 1
    assert main(["--config", str(cfg_path), *base, "daily", "--date", "2024-03-06",
                 "--offline"]) == 1
    assert capsys.readouterr().err.count("Pré-início pendente") == 2
    assert _tree(copia / "book") == before


# ----------------------------------------------------------------------------- painel


def test_painel_pre_inception_page(tmp_path):
    from cdp.workflow.painel import painel_data, write_painel

    rt = _iniciado(tmp_path)
    now = datetime(2026, 10, 6, 22, 40, tzinfo=UTC)
    d = painel_data(rt, now=now)
    st = d["status"]
    assert st["phase"] == "pre_inception"
    assert st["phase_label"] == ("Pré-início: carteira inaugural em 09/10/2026, ao preço de "
                                 "fechamento.")
    assert st["inaugural"] == {"date": "2026-10-09", "convention": "ao preço de fechamento"}
    assert st["alerts"] == [] and st["integrity"]["ok"] is True
    assert st["current_week"] == "2026-10-09" and st["is_rebalance_day"] is False
    ev = st["next_events"]
    assert ev[0]["label"].startswith("Decisão semanal") and ev[0]["when_local"].startswith(
        "2026-10-09T15:00")
    assert all(e["when_local"] >= "2026-10-09" for e in ev) and not any(e["overdue"] for e in ev)
    assert "reinicio" not in (st["agenda"] or {}) and st["agenda"]["fase"] == "pre_inicio"
    assert d["weeks"] == [] and d["latest_day"] is None and d["daily_reports"] == []
    assert d["risk"]["limit_checks"] == [] and d["issues"] == []
    assert d["audit"]["n_events"] == 1

    res = write_painel(rt, tmp_path / "painel", now=now)
    pub = (tmp_path / "painel" / "data.json").read_text(encoding="utf-8")
    local = (tmp_path / "painel" / "cdp_painel_local.html").read_text(encoding="utf-8")
    assert res["profile"] == "publicacao"
    for text in (pub, local):
        low = text.lower()
        assert "reinicio" not in low, [ln for ln in low.splitlines() if "reinicio" in ln][:3]
        assert "reinício" not in low and "estado_anterior" not in low
        assert "09/10/2026" in text
    assert GENESIS_EVENT not in pub


def test_painel_footer_names_public_sources_before_inception():
    """O rodapé lê o primeiro parêntese do aviso de dados como fontes: nunca a convenção de
    execução."""
    import re

    from cdp.workflow.daily import REAL_DATA_SOURCES
    from cdp.workflow.painel import _data_notice

    notice = _data_notice(False, None, [], [], {"available": True, "is_synthetic": False})
    first = re.search(r"\(([^)]+)\)", notice).group(1)
    assert first == REAL_DATA_SOURCES and "MOC" not in first


# ----------------------------------------------------------------------------- data de início
# a mais de uma semana, data de início perdida, dados de mercado antes do início


def test_inception_more_than_a_week_away(tmp_path, capsys):
    """Data de início a duas semanas: nenhum dia de montagem antes dela (agenda, eventos do
    painel, CLI) e, com a gênese, o livro recusa qualquer semana anterior à data de início."""
    from cdp.ui.data import next_events
    from cdp.workflow.painel import painel_data

    inicio = date(2026, 10, 23)
    rt = _iniciado(tmp_path, inicio)
    regular = date(2026, 10, 9)  # regra semanal (último pregão da semana na NYSE) antes do início
    assert dia_de_montagem(regular, rt.cfg)  # calendário puro: regra semanal
    a = agenda(rt, _at(date(2026, 10, 7), 19, 30))
    assert a["fase"] == "pre_inicio" and a["semanal"]["acao"] == "aguardar"
    assert a["proximos_eventos"][0]["evento"].startswith("carteira inaugural")
    assert all(e["quando"].date() >= inicio for e in a["proximos_eventos"])
    assert agenda(rt, _at(regular, 11, 10))["semanal"]["acao"] == "aguardar"
    ev = next_events(_at(date(2026, 10, 7), 19, 30), rt.cfg, set())
    dec = [e for e in ev if e.label.startswith("Decisão semanal")]
    assert dec[0].when.date() == inicio and "carteira inaugural" in dec[0].note
    st = painel_data(rt, now=_at(regular, 10).astimezone(UTC))["status"]
    assert st["is_rebalance_day"] is False and st["inaugural"]["date"] == inicio.isoformat()

    cfg_path = tmp_path / "fund_inicio.yaml"
    _write_cfg(cfg_path, inicio)
    base = ["--config", str(cfg_path), "--book", str(tmp_path / "book"), "--market",
            str(tmp_path / "market"), "--reports", str(tmp_path / "reports")]
    assert main([*base, "weekly", "prepare", "--date", regular.isoformat(), "--mind",
                 "claude-code", "--offline"]) == 0
    assert "Pré-início" in capsys.readouterr().out
    assert main([*base, "status", "--date", regular.isoformat()]) == 0
    assert json.loads(capsys.readouterr().out)["dia_de_rebalanceamento"] is False
    for week in (regular, date(2026, 10, 16)):  # nem com --force (nem a última sexta antes)
        with pytest.raises(ValueError, match="anterior"):
            main([*base, "weekly", "prepare", "--date", week.isoformat(), "--mind",
                  "claude-code", "--offline", "--force"])
        with pytest.raises(ValueError, match="anterior"):
            rt.book.check_key(week)
    assert sorted(p.name for p in (tmp_path / "book").iterdir()) == ["audit_log.jsonl",
                                                                     GENESIS_FILE]
    rt.book.check_key(inicio)


def test_missed_inaugural_date_keeps_the_portfolio_inaugural(tmp_path):
    """Data de início sem decisão: a agenda e o painel tratam a próxima data de montagem como a
    carteira inaugural (sem data passada nem "carteira anterior")."""
    from cdp.workflow.painel import painel_data

    rt = _iniciado(tmp_path)
    w = agenda(rt, _at(INICIO, 11, 10))["semanal"]
    assert w["acao"] == "montar" and w["motivo"] == ("carteira inaugural, dentro da janela de "
                                                      "decisão")
    late = agenda(rt, _at(INICIO, 17))["semanal"]
    assert late["acao"] == "prazo_vencido" and "carteira inaugural não montada" in late["motivo"]
    assert "carteira anterior" not in late["motivo"] and "fundo sem carteira" in late["motivo"]
    nxt = next(proximas_montagens(INICIO + timedelta(days=1), rt.cfg))
    a = agenda(rt, _at(nxt, 11, 10))
    assert a["fase"] == "operacao" and a["semanal"]["acao"] == "montar"
    assert a["semanal"]["motivo"].startswith("carteira inaugural")
    st = painel_data(rt, now=_at(nxt, 10).astimezone(UTC))["status"]
    assert st["phase"] == "pre_inception" and st["inaugural"]["date"] == nxt.isoformat()
    assert st["phase_label"] == (f"Pré-início: carteira inaugural em {nxt:%d/%m/%Y}, ao preço "
                                 "de fechamento.")
    dec = [e for e in st["next_events"] if e["label"].startswith("Decisão semanal")
           and not e["overdue"]]
    assert dec[0]["when_local"].startswith(nxt.isoformat()) and "inaugural" in dec[0]["note"]


class _FakeStore:
    """Base de mercado mínima: ``catch_up`` devolve um incremento por pregão pedido."""

    def __init__(self, last: date, fail: Exception | None = None):
        self.last, self.fail, self.calls = last, fail, []

    def catch_up(self, until):
        self.calls.append(until)
        if self.fail is not None:
            raise self.fail
        from types import SimpleNamespace

        out = [SimpleNamespace(session_date=until, manifest_hash="ab" * 32)]
        self.last = until
        return out

    def last_date(self):
        return self.last

    def verify_chain(self):
        return True, []


def test_daily_close_before_inception_keeps_market_data_current(tmp_path):
    """Antes do início: sem registro nem relatório, mas a base de mercado é incrementada (e o
    incremento ancorado na trilha depois da gênese)."""
    from cdp.data.store import DataNotReadyError

    session = date(2026, 10, 6)
    store = _FakeStore(date(2026, 10, 5))
    rt = _iniciado(tmp_path, store_override=store)
    out = rt.daily_close(session, live=True)
    assert out["status"] == "pré-início" and store.calls == [session]
    assert out["dados_de_mercado"]["status"] == "atualizados"
    assert out["dados_de_mercado"]["ultimo_pregao"] == session
    events = AuditLog(tmp_path / "book" / "audit_log.jsonl").events()
    assert [e.event_type for e in events] == [GENESIS_EVENT, "MARKET_INCREMENT"]
    assert not (tmp_path / "reports").exists() and rt.track().dates() == []
    ok, msgs = rt.verify_all()
    assert ok, msgs
    assert agenda(rt, _at(session, 19, 30))["fase"] == "pre_inicio"

    late = _FakeStore(session, fail=DataNotReadyError("fonte atrasada"))
    rt2 = _iniciado(tmp_path / "b", store_override=late)
    out = rt2.daily_close(date(2026, 10, 7), live=True)
    assert out["status"] == "pré-início" and out["dados_de_mercado"]["status"] == "não prontos"
    events = AuditLog(tmp_path / "b" / "book" / "audit_log.jsonl").events()
    assert [e.event_type for e in events] == [GENESIS_EVENT]
