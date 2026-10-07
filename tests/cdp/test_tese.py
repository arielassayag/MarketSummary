"""Tese de investimento da carteira decidida: preparação, validação e publicação (DADOS SIMULADOS).

Tudo offline sobre a demonstração (``run_demo``), que já publica a tese da mente ``demo`` em
cada semana decidida; os testes que mexem no livro usam cópias da pasta da demonstração.
"""

from __future__ import annotations

import json
import re
import shutil
import warnings
from dataclasses import replace
from datetime import date, datetime
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cdp.config import load_config
from cdp.hashing import sha256_file, sha256_obj
from cdp.workflow.demo import DEMO_FIRST_WEEK, DEMO_SEED, DemoStore, demo_sessions, run_demo
from cdp.workflow.runtime import Runtime
from cdp.workflow.tese import (
    ANALISE_JSON,
    AUDIT_EVENT,
    FACTBOOK_JSON,
    FATOS_MD,
    PUBLISHED_JSON,
    SCHEMA_JSON,
    TESE_JSON,
    TESE_MD,
    TeseOutput,
    load_prepared,
    template_thesis,
    thesis_dir,
    verify_thesis,
)
from cdp.workflow.tese_analise import position_role, sizing_driver

LEGACY = Path(__file__).resolve().parent / "fixtures" / "fund_legado.yaml"
WEEK = DEMO_FIRST_WEEK
DAYS = 2
BRT = ZoneInfo("America/Sao_Paulo")


@pytest.fixture(autouse=True)
def _configuracao_exata_no_cwd(request):
    """Pré-condição do caso chdir: mesmos configs congelados, sem valores inventados."""
    if request.node.name == "test_demo_never_adopts_repository_drafts":
        root = request.getfixturevalue("tmp_path")
        source = Path(__file__).resolve().parents[2] / "configs"
        shutil.copytree(source, root / "cwd" / "configs")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("cdp_tese_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summary = run_demo(out, days=DAYS, cfg=load_config(LEGACY))
    return out, summary


@pytest.fixture(scope="module")
def market():
    from cdp.data.synthetic import make_synthetic_market
    from cdp.workflow.demo import DEMO_HISTORY_START

    return make_synthetic_market(seed=DEMO_SEED, start=DEMO_HISTORY_START,
                                 as_of=demo_sessions(DAYS)[-1])


def _runtime(root: Path, market=None, teses: Path | None = None) -> Runtime:
    """Runtime da cópia; ``teses`` = pasta dos rascunhos entregues (padrão: inexistente)."""
    return Runtime(load_config(LEGACY), root / "book", root / "market", root / "reports",
                   clock=lambda: datetime(2024, 3, 4, 16, 0, tzinfo=BRT),
                   teses_root=teses if teses is not None else root / "teses")


def _unpublished_copy(demo, tmp_path: Path) -> Path:
    """Cópia do livro da demonstração sem a tese publicada (a trilha mantém o evento antigo)."""
    out, _ = demo
    dst = tmp_path / "copia"
    shutil.copytree(out / "book", dst / "book")
    shutil.copytree(out / "market", dst / "market")
    folder = thesis_dir(dst / "book", WEEK)
    for name in (PUBLISHED_JSON, TESE_MD, TESE_JSON):
        (folder / name).unlink(missing_ok=True)
    return dst


def _prepared(demo) -> tuple:
    out, _ = demo
    return load_prepared(thesis_dir(out / "book", WEEK))


def _valid_dict(demo) -> dict:
    fb, analysis = _prepared(demo)
    return template_thesis(analysis, fb, "claude-code").model_dump(mode="json")


def _strict_load(path: Path):
    def bad(token: str):
        raise ValueError(f"constante não estrita no JSON: {token}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=bad)


# ----------------------------------------------------------------------------- preparação


def test_prepare_writes_facts_analysis_briefing_and_schema(demo):
    out, summary = demo
    folder = thesis_dir(out / "book", WEEK)
    for name in (FACTBOOK_JSON, ANALISE_JSON, FATOS_MD, SCHEMA_JSON):
        assert (folder / name).is_file(), name
    fb, analysis = _prepared(demo)
    rt = _runtime(out)
    proposal = rt.book.load_proposal(WEEK)
    held = {p.issuer_id for p in proposal.positions}
    assert {r["iid"] for r in analysis["positions"]} == held
    for iid in held:  # fatos de emissor para TODOS os nomes detidos + fatos da tese
        assert f"{iid}.ret_1m_usd" in fb.facts
        assert f"tese.{iid}.peso" in fb.facts and f"tese.{iid}.alpha_quant" in fb.facts
    for fid in ("tese.vol", "tese.beta", "tese.gross", "tese.net", "tese.vol_meta_aplicada",
                "tese.sigma_dia_usd", "tese.funil.universo", "tese.liq.max_dias_short"):
        assert fid in fb.facts, fid
    assert all(" " not in fid and "}" not in fid for fid in fb.facts)
    assert analysis["check"]["ok"] is True  # recálculo confere com o RiskSummary gravado
    s = analysis["numbers"]["summary"]
    assert s["vol"] == pytest.approx(proposal.risk.ex_ante_vol)
    assert s["n_long"] == proposal.risk.n_long and s["n_short"] == proposal.risk.n_short
    schema = json.loads((folder / SCHEMA_JSON).read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False and "posicoes" in schema["properties"]
    fatos = (folder / FATOS_MD).read_text(encoding="utf-8")
    assert "DADOS SIMULADOS" in fatos and "validate-tese --week 2024-03-04" in fatos
    assert "## Dossiês por posição" in fatos
    assert all(f"`{iid}`" in fatos for iid in held)
    weekly = [e for e in summary["etapas"] if "semana" in e]
    assert weekly[0]["tese"] == "mente" and weekly[0]["tese_apontamentos"] == []
    assert weekly[0]["tese_rascunho_adotado"] is False


def test_prepare_is_deterministic(demo, market, tmp_path):
    out, _ = demo
    original = thesis_dir(out / "book", WEEK)
    dst = _unpublished_copy(demo, tmp_path)
    rt = _runtime(dst, market)
    for _ in range(2):
        res = rt.thesis_prepare(WEEK)
        assert res["publicada"] is False and res["n_posicoes"] > 0
        # sem rascunho entregue: nada adotado, e isso aparece na saída
        assert res["rascunho_entregue"] is None and res["rascunho_adotado"] is False
        assert not (thesis_dir(dst / "book", WEEK) / TESE_JSON).exists()
        folder = thesis_dir(dst / "book", WEEK)
        for name in (ANALISE_JSON, FACTBOOK_JSON):
            assert sha256_file(folder / name) == sha256_file(original / name), name
        fatos = (folder / FATOS_MD).read_text(encoding="utf-8")
        base = (original / FATOS_MD).read_text(encoding="utf-8")
        assert fatos.replace(folder.as_posix(), "<pasta>") == \
            base.replace(original.as_posix(), "<pasta>")


def test_prepare_requires_an_approved_decision(tmp_path):
    rt = _runtime(tmp_path)
    with pytest.raises(ValueError, match="decisão aprovada"):
        rt.thesis_prepare(WEEK)
    assert not thesis_dir(tmp_path / "book", WEEK).exists()


# ----------------------------------------------------------------------------- validação


def test_template_thesis_is_valid_and_complete(demo):
    fb, analysis = _prepared(demo)
    out = template_thesis(analysis, fb, "claude-code")
    assert verify_thesis(out, fb, analysis) == []
    assert {p.issuer_id for p in out.posicoes} == {r["iid"] for r in analysis["positions"]}
    assert 1 <= len(out.temas) <= 8 and out.riscos and out.gatilhos


def test_validation_accepts_a_valid_mind_file(demo, tmp_path):
    dst = _unpublished_copy(demo, tmp_path)
    rt = _runtime(dst)
    path = thesis_dir(dst / "book", WEEK) / TESE_JSON
    missing = rt.validate_thesis(WEEK)
    assert missing["ok"] is False and "ausente" in missing["problemas"][0]
    path.write_text(json.dumps(_valid_dict(demo), ensure_ascii=False), encoding="utf-8")
    res = rt.validate_thesis(WEEK)
    assert res["ok"] is True and res["problemas"] == []
    cov = res["cobertura"]
    assert cov["posicoes_com_texto"] == cov["posicoes_total"] and cov["faltando"] == []


@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d.update(resumo=d["resumo"] + " A vol caiu 3,5% na semana."), "número fora"),
    (lambda d: d.update(contexto="Alpha de {{fact:tese.inexistente}} no ano."),
     "fato inexistente"),
    (lambda d: d["posicoes"].append({**d["posicoes"][0], "issuer_id": "NAO_DETIDO"}),
     "não está na carteira"),
    (lambda d: d["posicoes"].append(dict(d["posicoes"][0])), "repetido"),
    (lambda d: d.update(week="2024-03-11"), "difere da semana"),
    (lambda d: d["temas"][0].update(emissores=["NAO_DETIDO"]), "fora da carteira"),
    (lambda d: d.update(premortem="Veja [aqui](https://exemplo.com)."), "marcação"),
    (lambda d: d.update(campo_extra="x"), "campo_extra"),
])
def test_validation_rejects_invalid_theses(demo, mutate, needle):
    from cdp.research.pm_agent import _validation_issues

    fb, analysis = _prepared(demo)
    data = _valid_dict(demo)
    mutate(data)
    try:
        out = TeseOutput.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - erro de schema também é rejeição
        problems = _validation_issues(exc)  # type: ignore[arg-type]
    else:
        problems = verify_thesis(out, fb, analysis)
    assert problems and any(needle in p for p in problems), problems


@pytest.mark.parametrize("ambiente", ["codex", "claude-code", "gemini"])
def test_cli_validate_tese_exit_codes(demo, tmp_path, capsys, monkeypatch, ambiente):
    monkeypatch.setenv("CDP_HARNESS", ambiente)
    from cdp.__main__ import main

    dst = _unpublished_copy(demo, tmp_path)
    args = ["--book", str(dst / "book"), "--market", str(dst / "market"), "--reports",
            str(dst / "reports"), "validate-tese", "--week", WEEK.isoformat(),
            "--mind", "claude-code"]
    assert main(args) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and set(out) == {"ok", "problemas", "cobertura"}
    (thesis_dir(dst / "book", WEEK) / TESE_JSON).write_text(
        json.dumps(_valid_dict(demo), ensure_ascii=False), encoding="utf-8")
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


# ----------------------------------------------------------------------------- publicação


def test_published_thesis_files_event_and_immutability(demo):
    out, _ = demo
    rt = _runtime(out)
    folder = thesis_dir(out / "book", WEEK)
    pub = _strict_load(folder / PUBLISHED_JSON)
    assert pub["autoria"] == "mente" and pub["mind"] == "demo" and pub["problems"] == []
    assert pub["is_synthetic"] is True
    events = [e for e in rt.book.audit.events() if e.event_type == AUDIT_EVENT]
    assert len(events) == 1 and events[0].week == WEEK and events[0].actor == "CDP"
    decision = rt.book.load_decision(WEEK)
    payload = {"tese_publicada": sha256_file(folder / PUBLISHED_JSON),
               "tese_md": sha256_file(folder / TESE_MD),
               "proposal_hash": decision.proposal_hash,
               "approval_hash": decision.approval_hash, "autoria": "mente"}
    assert events[0].payload_hash == sha256_obj(payload)
    before = sha256_file(folder / PUBLISHED_JSON)
    with pytest.raises(FileExistsError):
        rt.thesis_publish(WEEK)
    again = rt.thesis_prepare(WEEK)  # publicada ⇒ nada é regravado
    assert again["publicada"] is True and again["arquivos"] == {}
    assert again["rascunho_adotado"] is False
    assert sha256_file(folder / PUBLISHED_JSON) == before
    assert len([e for e in rt.book.audit.events() if e.event_type == AUDIT_EVENT]) == 1
    ok, msgs = rt.book.verify_integrity()
    assert ok, msgs


def test_published_shape_positions_and_no_placeholders(demo):
    out, _ = demo
    folder = thesis_dir(out / "book", WEEK)
    raw = (folder / PUBLISHED_JSON).read_text(encoding="utf-8")
    assert "{{fact:" not in raw and "NaN" not in raw and "Infinity" not in raw
    assert "[fato inexistente]" not in raw
    r = _strict_load(folder / PUBLISHED_JSON)["rendered"]
    assert {"week", "published_at", "as_of", "prices_as_of", "authorship", "is_synthetic",
            "title", "summary_md", "sections", "risks", "triggers", "themes", "positions",
            "numbers", "calendar", "notes", "disclaimer"} == set(r)
    assert [s["id"] for s in r["sections"]] == ["contexto", "construcao", "exposicoes",
                                                "sensibilidade", "volatilidade", "premortem",
                                                "monitoramento"]
    rt = _runtime(out)
    held = {p.issuer_id for p in rt.book.load_proposal(WEEK).positions}
    pos = r["positions"]
    assert {p["iid"] for p in pos} == held and len(pos) == len(held)
    weights = [abs(p["weight"]) for p in pos]
    assert weights == sorted(weights, reverse=True)
    for p in pos:
        assert p["side"] in ("LONG", "SHORT") and (p["weight"] > 0) == (p["side"] == "LONG")
        assert p["role"] in ("alpha", "alpha_div", "hedge")
        assert p["sizing"] in ("interior", "teto_nome", "teto_risco", "teto_visao", "liquidez",
                               "squeeze", "aluguel", "indeterminado")
        assert p["why_md"] and p["risk_md"] and p["trigger_md"] and p["author"] == "mente"
    n = r["numbers"]
    assert [v["step"] for v in n["vol_budget"]] == ["mandato", "postura", "aplicada", "piso",
                                                    "atingida"]
    assert {g["group"] for g in n["risk_groups"]} == {"mercado", "pais", "setor", "estilo",
                                                     "especifico"}
    assert sum(g["share"] for g in n["risk_groups"]) == pytest.approx(1.0, abs=1e-4)
    shares = [abs(f["share"]) for f in n["factors"] if f["share"] is not None]
    assert shares == sorted(shares, reverse=True)
    stress = [s["pnl"] for s in n["stress"]]
    known = [v for v in stress if v is not None]
    assert known == sorted(known) and stress[:len(known)] == known  # sem dados no fim
    assert all(s["kind"] in ("historico", "hipotetico", "idiossincratico", "gap")
               for s in n["stress"])
    dates = [c["date"] for c in r["calendar"]]
    assert dates == sorted(dates) and all(d >= WEEK.isoformat() for d in dates)
    assert r["themes"] and all(set(t["issuers"]) <= held for t in r["themes"])
    assert r["authorship"] == "mente"


def test_synthetic_thesis_carries_simulated_notice(demo):
    out, _ = demo
    folder = thesis_dir(out / "book", WEEK)
    md = (folder / TESE_MD).read_text(encoding="utf-8")
    r = _strict_load(folder / PUBLISHED_JSON)["rendered"]
    assert "DADOS SIMULADOS" in md and "DADOS SIMULADOS" in r["disclaimer"]
    assert r["is_synthetic"] is True
    for needle in ("## Posições", "## Exposições", "## Sensibilidade de mercado",
                   "## Volatilidade e orçamento de risco", "## Estresse", "## Aviso"):
        assert needle in md, needle


def test_publish_falls_back_to_code_template(demo, market, tmp_path):
    dst = _unpublished_copy(demo, tmp_path)
    rt = _runtime(dst, market)
    folder = thesis_dir(dst / "book", WEEK)
    bad = _valid_dict(demo)
    bad["resumo"] = "Retorno de 37,5% garantido no trimestre."
    (folder / TESE_JSON).write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    res = rt.thesis_publish(WEEK)
    assert res["autoria"] == "codigo" and res["publicada"] is True
    assert any("número fora" in p for p in res["problemas"])
    pub = _strict_load(folder / PUBLISHED_JSON)
    assert pub["autoria"] == "codigo" and pub["mind"] is None
    assert all(p["author"] == "codigo" for p in pub["rendered"]["positions"])
    assert "37,5%" not in json.dumps(pub["rendered"], ensure_ascii=False)
    with pytest.raises(FileExistsError):
        rt.thesis_publish(WEEK)


def test_publish_missing_file_and_partial_mind_coverage(demo, market, tmp_path):
    dst = _unpublished_copy(demo, tmp_path)
    rt = _runtime(dst, market)
    res = rt.thesis_publish(WEEK)  # sem tese.json ⇒ tese automática
    assert res["autoria"] == "codigo" and any("ausente" in p for p in res["problemas"])

    dst2 = _unpublished_copy(demo, tmp_path / "b")
    rt2 = _runtime(dst2, market)
    data = _valid_dict(demo)
    data["posicoes"] = data["posicoes"][:1]
    folder = thesis_dir(dst2 / "book", WEEK)
    (folder / TESE_JSON).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    res2 = rt2.thesis_publish(WEEK)
    assert res2["autoria"] == "mente" and res2["problemas"] == []
    authors = [p["author"] for p in _strict_load(folder / PUBLISHED_JSON)["rendered"]["positions"]]
    first = data["posicoes"][0]["issuer_id"]
    by_iid = dict(zip([p["iid"] for p in _strict_load(folder / PUBLISHED_JSON)["rendered"]
                       ["positions"]], authors, strict=True))
    assert by_iid[first] == "mente"
    assert {a for i, a in by_iid.items() if i != first} == {"codigo"}


# ----------------------------------------------------------------------------- agenda e CLI


def _at(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=BRT)


def test_agenda_requests_thesis_until_published(demo, market, tmp_path):
    from cdp.workflow.agenda import agenda

    out, _ = demo
    done = agenda(_runtime(out), _at(WEEK, 16))
    assert done["semanal"]["acao"] == "nenhuma" and done["semanal"]["tese_publicada"] is True
    assert done["teses_pendentes"] == []
    dst = _unpublished_copy(demo, tmp_path)
    rt = _runtime(dst, market)
    pending = agenda(rt, _at(WEEK, 16))
    assert pending["semanal"]["acao"] == "tese" and pending["teses_pendentes"] == [WEEK]
    tuesday = agenda(rt, _at(date(2024, 3, 5), 12))
    assert tuesday["semanal"]["acao"] == "tese"
    rt.thesis_publish(WEEK)
    after = agenda(rt, _at(WEEK, 16))
    assert after["semanal"]["acao"] == "nenhuma" and after["teses_pendentes"] == []


def test_cli_parses_thesis_commands():
    from cdp.__main__ import build_parser, cmd_tese, cmd_validate_tese

    p = build_parser()
    a = p.parse_args(["tese", "prepare", "--week", "2026-10-05"])
    assert a.func is cmd_tese and a.action == "prepare" and a.week == "2026-10-05"
    a = p.parse_args(["tese", "publish", "--week", "2026-10-05"])
    assert a.func is cmd_tese and a.action == "publish"
    a = p.parse_args(["validate-tese", "--week", "2026-10-05"])
    assert a.func is cmd_validate_tese
    with pytest.raises(SystemExit):
        p.parse_args(["tese", "publish"])


def test_cli_publish_refuses_when_published(demo, capsys):
    from cdp.__main__ import main

    out, _ = demo
    code = main(["--book", str(out / "book"), "--market", str(out / "market"), "--reports",
                 str(out / "reports"), "tese", "publish", "--week", WEEK.isoformat()])
    assert code == 1 and "já publicada" in capsys.readouterr().err


# ----------------------------------------------------------------------------- regras puras


def test_position_role_rules():
    assert position_role(0.01, 0.02, 0.05) == "alpha"
    assert position_role(-0.01, -0.02, -0.01) == "alpha_div"
    assert position_role(-0.01, 0.002, 0.03) == "hedge"
    assert position_role(0.01, None, 0.03) == "hedge"


def test_sizing_driver_rules():
    base = {"teto_nome": 0.025, "liquidez": 0.05, "teto_visao": None, "squeeze_mult": 1.0,
            "teto_risco": 0.03, "efetivo": 0.025, "execucao": 0.2, "atual": 0.0}
    assert sizing_driver("X", -0.025, base, []) == "teto_nome"
    assert sizing_driver("X", -0.010, base, []) == "interior"
    assert sizing_driver("X", -0.010, base, ["max_short:X"]) == "teto_risco"
    assert sizing_driver("X", -0.020, {**base, "teto_risco": 0.02, "efetivo": 0.02},
                         []) == "teto_risco"
    assert sizing_driver("X", -0.0125, {**base, "squeeze_mult": 0.5, "efetivo": 0.0125},
                         []) == "squeeze"
    assert sizing_driver("X", -0.0125, {**base, "teto_visao": 0.0125, "efetivo": 0.0125},
                         []) == "teto_visao"
    assert sizing_driver("X", 0.01, {**base, "liquidez": 0.01, "efetivo": 0.01},
                         []) == "liquidez"
    assert sizing_driver("X", 0.01, base, ["max_trade_liq:X"]) == "liquidez"
    assert sizing_driver("X", 0.01, None, []) == "indeterminado"


def test_template_cut_never_leaves_partial_placeholders():
    from cdp.workflow.tese import _cut

    text = "Alpha de {{fact:tese.alpha}} e vol de {{fact:tese.vol}} no ano."
    for limit in range(5, len(text) + 2):
        out = _cut(text, limit)
        assert len(out) <= limit
        assert out.count("{{") == out.count("}}")


# ----------------------------------------------------------------------------- rascunho entregue


def _draft_bytes(demo) -> bytes:
    data = _valid_dict(demo)
    data["titulo"] = "Rascunho entregue fora do clone da rotina"
    return (json.dumps(data, ensure_ascii=False, indent=4) + "\r\n").encode("utf-8")


def test_prepare_adopts_delivered_draft_only_when_absent(demo, market, tmp_path):
    dst = _unpublished_copy(demo, tmp_path)
    teses = tmp_path / "teses"
    teses.mkdir()
    draft = teses / f"{WEEK.isoformat()}.json"
    draft.write_bytes(_draft_bytes(demo))
    rt = _runtime(dst, market, teses=teses)
    folder = thesis_dir(dst / "book", WEEK)
    res = rt.thesis_prepare(WEEK)
    assert res["rascunho_adotado"] is True and res["rascunho_entregue"] == draft.as_posix()
    assert (folder / TESE_JSON).read_bytes() == draft.read_bytes()  # cópia byte a byte
    assert not (folder / PUBLISHED_JSON).exists()  # prepare nunca publica
    assert rt.validate_thesis(WEEK)["ok"] is True  # validado contra o FactBook da rotina
    (folder / TESE_JSON).write_text('{"mind": "codex"}', encoding="utf-8")
    again = rt.thesis_prepare(WEEK)  # tese.json existente nunca é sobrescrito
    assert again["rascunho_adotado"] is False and again["rascunho_entregue"] == draft.as_posix()
    assert (folder / TESE_JSON).read_text(encoding="utf-8") == '{"mind": "codex"}'


def test_demo_never_adopts_repository_drafts(tmp_path, monkeypatch):
    cfg = load_config(LEGACY)
    drafts = tmp_path / "cwd" / "docs" / "cdp" / "teses"
    drafts.mkdir(parents=True)
    (drafts / f"{WEEK.isoformat()}.json").write_text('{"mind": "codex"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path / "cwd")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summary = run_demo(tmp_path / "demo", days=1, cfg=cfg)
    weekly = [e for e in summary["etapas"] if "semana" in e]
    assert weekly[0]["tese_rascunho_adotado"] is False and weekly[0]["tese"] == "mente"
    pub = _strict_load(thesis_dir(tmp_path / "demo" / "book", WEEK) / PUBLISHED_JSON)
    assert pub["mind"] == "demo"


def test_cli_teses_root_option():
    from cdp.__main__ import build_parser

    a = build_parser().parse_args(["--teses", "outra/pasta", "tese", "prepare", "--week",
                                   "2026-10-05"])
    assert Runtime.from_args(a).teses_root == Path("outra/pasta")
    a = build_parser().parse_args(["tese", "prepare", "--week", "2026-10-05"])
    assert Runtime.from_args(a).teses_root == Path("docs/cdp/teses")


# ----------------------------------------------------------------------------- decisão do PM


def _decided_week(root: Path, market, *, mutate_pm=None, kill_switch: bool = False) -> Runtime:
    """Semana da demonstração decidida com a decisão bruta do PM alterada ANTES do ``decide``."""
    from cdp.workflow.demo import _Clock, write_demo_inputs

    clock = _Clock()
    rt = Runtime(load_config(LEGACY), root / "book", root / "market", root / "reports",
                 store_override=DemoStore(market, root=root / "market", cfg=load_config(LEGACY)),
                 clock=clock, teses_root=None)
    clock.set(WEEK, dtime(11, 0))
    rt.weekly_prepare(WEEK, mind="demo", live=False)
    clock.set(WEEK, dtime(12, 0))
    write_demo_inputs(rt, WEEK)
    if mutate_pm is not None:
        path = rt.week_dir(WEEK) / "inputs" / "pm_decision.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        mutate_pm(raw)
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    if kill_switch:
        rt.set_kill_switch(True, "teste", "teste")
    clock.set(WEEK, dtime(15, 0))
    rt.weekly_decide(WEEK, mind="demo")
    if kill_switch:
        rt.set_kill_switch(False, "teste", "teste")  # o estado vivo posterior não importa
    return rt


def test_thesis_uses_the_verified_pm_output_of_the_decision(market, tmp_path):
    from cdp.research.pm_agent import posture_limits

    def bogus_evidence(raw):
        assert raw["views"]
        for v in raw["views"]:
            v["evidence_ids"] = ["evidencia_inexistente"]
        raw["risk_posture"] = "neutra"

    rt = _decided_week(tmp_path, market, mutate_pm=bogus_evidence, kill_switch=True)
    rt.thesis_prepare(WEEK)
    folder = thesis_dir(tmp_path / "book", WEEK)
    fb, analysis = load_prepared(folder)
    dec = analysis["decision"]
    assert dec["pm_verified"] is True
    assert dec["posture"] == "muito_defensiva"  # a do kill switch na decisão, não a bruta
    budget = {v["step"]: v["value"] for v in analysis["numbers"]["vol_budget"]}
    assert budget["postura"] == pytest.approx(
        posture_limits("muito_defensiva", rt.cfg, None).vol_target)
    # o decide descartou todas as visões (sem evidência válida): nenhuma é publicada
    assert all(p["pm_stance"] is None and p["pm_conv"] is None for p in analysis["positions"])
    assert fb.facts["tese.n_visao_pm"].value == 0
    assert not any("reconstruídas" in n for n in analysis["notes"])
    assert "- Visão do PM:" not in (folder / FATOS_MD).read_text(encoding="utf-8")


def test_pm_file_changed_after_the_decision_is_never_published(demo, market, tmp_path):
    dst = _unpublished_copy(demo, tmp_path)
    path = dst / "book" / WEEK.isoformat() / "inputs" / "pm_decision.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["what_changed"] = raw["what_changed"] + " Ajuste escrito depois da decisão."
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    rt = _runtime(dst, market)
    rt.thesis_prepare(WEEK)
    fb, analysis = load_prepared(thesis_dir(dst / "book", WEEK))
    assert analysis["decision"]["pm_verified"] is False
    assert analysis["decision"]["posture"] is None
    assert all(p["pm_stance"] is None for p in analysis["positions"])
    n = fb.facts["tese.n_visao_pm"]
    assert n.value is None and n.formatted == "n/d"  # ausente, nunca zero
    assert any("não pôde ser reproduzida" in x for x in analysis["notes"])
    out = template_thesis(analysis, fb, "claude-code")
    assert "não está disponível" in out.contexto and verify_thesis(out, fb, analysis) == []


# ----------------------------------------------------------------------------- publicação robusta


def test_publish_recomputes_facts_instead_of_trusting_disk(demo, market, tmp_path):
    dst = _unpublished_copy(demo, tmp_path)
    rt = _runtime(dst, market)
    folder = thesis_dir(dst / "book", WEEK)
    original = (folder / ANALISE_JSON).read_text(encoding="utf-8")
    true_vol = json.loads(original)["numbers"]["summary"]["vol"]
    an = json.loads(original)
    an["numbers"]["summary"]["vol"] = 0.0101
    (folder / ANALISE_JSON).write_text(json.dumps(an), encoding="utf-8")
    raw_fb = json.loads((folder / FACTBOOK_JSON).read_text(encoding="utf-8"))
    raw_fb["facts"]["tese.vol"].update(value=0.0101, formatted="1,01%")
    (folder / FACTBOOK_JSON).write_text(json.dumps(raw_fb), encoding="utf-8")
    res = rt.thesis_publish(WEEK)
    assert any("regravados" in p for p in res["problemas"])
    rendered = _strict_load(folder / PUBLISHED_JSON)["rendered"]
    assert rendered["numbers"]["summary"]["vol"] == pytest.approx(true_vol)
    assert "| Vol ex-ante (fatorial / específica) | 1,01%" not in \
        (folder / TESE_MD).read_text(encoding="utf-8")
    assert (folder / ANALISE_JSON).read_text(encoding="utf-8") == original


def test_publish_rolls_back_when_the_audit_event_fails(demo, market, tmp_path, monkeypatch):
    from cdp.audit import AuditLog

    dst = _unpublished_copy(demo, tmp_path)
    rt = _runtime(dst, market)
    folder = thesis_dir(dst / "book", WEEK)
    append = AuditLog.append

    def failing(self, event_type, *args, **kwargs):
        if event_type == AUDIT_EVENT:
            raise OSError("disco cheio")
        return append(self, event_type, *args, **kwargs)

    monkeypatch.setattr(AuditLog, "append", failing)
    with pytest.raises(OSError, match="disco cheio"):
        rt.thesis_publish(WEEK)
    assert not (folder / PUBLISHED_JSON).exists() and not (folder / TESE_MD).exists()
    monkeypatch.setattr(AuditLog, "append", append)
    assert rt.thesis_publish(WEEK)["publicada"] is True


def test_interrupted_publication_is_resumed_only_when_files_match(demo, market, tmp_path):
    dst = _unpublished_copy(demo, tmp_path)
    rt = _runtime(dst, market)
    folder = thesis_dir(dst / "book", WEEK)
    first = rt.thesis_publish(WEEK)
    log = dst / "book" / "audit_log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines(keepends=True)
    log.write_text("".join(lines[:-1]), encoding="utf-8")  # morreu antes do evento…
    before = {n: sha256_file(folder / n) for n in (PUBLISHED_JSON, TESE_MD)}
    (folder / TESE_MD).unlink()  # … e antes do tese.md
    res = rt.thesis_publish(WEEK)
    assert res["retomada"] is True and res["autoria"] == first["autoria"]
    assert {n: sha256_file(folder / n) for n in before} == before
    decision = rt.book.load_decision(WEEK)
    payload = {"tese_publicada": before[PUBLISHED_JSON], "tese_md": before[TESE_MD],
               "proposal_hash": decision.proposal_hash,
               "approval_hash": decision.approval_hash, "autoria": first["autoria"]}
    events = [e for e in rt.book.audit.events() if e.event_type == AUDIT_EVENT]
    assert events[-1].week == WEEK and events[-1].payload_hash == sha256_obj(payload)
    with pytest.raises(FileExistsError):
        rt.thesis_publish(WEEK)
    n_events = len(rt.book.audit.events())
    (folder / TESE_MD).unlink()  # já ancorada e só o tese.md sumiu ⇒ nunca um segundo evento
    with pytest.raises(FileExistsError):
        rt.thesis_publish(WEEK)
    assert len(rt.book.audit.events()) == n_events and not (folder / TESE_MD).exists()
    # arquivo que o código não produziria e sem evento na trilha ⇒ recusa (nada é ancorado)
    log.write_text("".join(lines[:-1]), encoding="utf-8")
    doc = json.loads((folder / PUBLISHED_JSON).read_text(encoding="utf-8"))
    doc["rendered"]["title"] = "Título escrito fora do código"
    (folder / PUBLISHED_JSON).write_text(json.dumps(doc), encoding="utf-8")
    n_events = len(rt.book.audit.events())
    with pytest.raises(ValueError, match="não conferem"):
        rt.thesis_publish(WEEK)
    assert len(rt.book.audit.events()) == n_events


# ----------------------------------------------------------------------------- configuração


def test_config_drift_uses_decision_config_or_nulls_dependent_fields(demo, market, tmp_path):
    from cdp.workflow.runtime import DECISION_CONFIG

    out, _ = demo
    original = thesis_dir(out / "book", WEEK) / ANALISE_JSON
    dst = _unpublished_copy(demo, tmp_path)
    snapshot = dst / "book" / WEEK.isoformat() / DECISION_CONFIG
    assert snapshot.is_file()  # gravado pelo decide
    cfg = load_config(LEGACY)
    weights = dict(cfg.alpha.signal_weights)
    weights.update(value=0.40, quality=0.0)
    recalibrated = cfg.with_overrides({"alpha": {"signal_weights": weights}})
    assert recalibrated.config_hash() != cfg.config_hash()
    rt = replace(_runtime(dst, market), cfg=recalibrated)
    folder = thesis_dir(dst / "book", WEEK)
    rt.thesis_prepare(WEEK)  # configuração da decisão disponível ⇒ mesma análise
    assert sha256_file(folder / ANALISE_JSON) == sha256_file(original)
    snapshot.unlink()
    rt.thesis_prepare(WEEK)
    fb, a = load_prepared(folder)
    assert a["decision"]["config_drift"] is True
    for p in a["positions"]:
        assert p["alpha"] is not None  # alpha da proposta (gravado) continua
        assert p["alpha_quant"] is None and p["tilt"] is None and p["sizing"] == "indeterminado"
        assert all(p[f"z_{c}"] is None and p[f"c_{c}"] is None
                   for c in ("mom", "val", "qual", "lowrisk", "rev"))
    assert all(g["share"] is None for g in a["numbers"]["risk_groups"])
    assert all(f["share"] is None for f in a["numbers"]["factors"])
    share = a["numbers"]["summary"]["factor_share"]
    assert fb.facts["tese.risco_especifico"].value == pytest.approx(1.0 - share)
    assert any("recalibrado" in n for n in a["notes"])
    out_t = template_thesis(a, fb, "claude-code")
    assert verify_thesis(out_t, fb, a) == []
    assert "das visões" not in " ".join(p.por_que for p in out_t.posicoes)


# ----------------------------------------------------------------------------- números e rótulos


@pytest.fixture(scope="module")
def inputs(demo, market):
    from cdp.workflow.tese_analise import load_inputs

    out, _ = demo
    return load_inputs(_runtime(out, market), WEEK)


def test_turnover_is_zero_not_missing_without_trades(inputs):
    from cdp.workflow.tese_analise import build_analysis

    ti = replace(inputs, proposal=inputs.proposal.model_copy(update={"trades": []}))
    a = build_analysis(ti)
    assert a["numbers"]["summary"]["turnover"] == 0.0
    assert a["numbers"]["summary"]["exec_cost_bps"] is None
    assert any("giro é zero" in n for n in a["notes"])


def test_vol_target_sentence_only_credits_the_bias_prior_when_applied(demo):
    from cdp.workflow.tese import _vol_target_sentence
    from cdp.workflow.tese_analise import vol_target_basis

    cfg = load_config(LEGACY)
    rk = cfg.risk
    assert vol_target_basis(rk.vol_target_annual / rk.bias_prior, rk.vol_target_annual,
                            cfg) == "vies_postura"
    assert vol_target_basis(0.04, 0.04, cfg) == "postura"  # histórico suficiente
    assert vol_target_basis(rk.vol_band_min, 0.035, cfg) == "piso"
    assert vol_target_basis(None, 0.04, cfg) is None
    fb, analysis = _prepared(demo)
    assert "viés a priori" in _vol_target_sentence(fb, "vies_postura", True)
    for basis in ("postura", "mandato", "piso", "outro", None):
        assert "viés a priori" not in _vol_target_sentence(fb, basis, True), basis
    late = json.loads(json.dumps(analysis))
    late["decision"]["vol_basis"] = "postura"
    out = template_thesis(late, fb, "claude-code")
    assert "viés a priori" not in out.contexto and verify_thesis(out, fb, late) == []


def test_historical_stress_note_follows_the_direction_of_the_result():
    import pandas as pd

    from cdp.workflow.tese_analise import _top_contributor

    c = pd.Series({"A": -0.0037, "B": 0.0040, "C": 0.0008})
    gain = _top_contributor(c, float(c.sum()), {"A": "Alfa", "B": "Beta"})
    assert "Maior ganho individual: Beta (0,40 p.p.)" in gain
    loss = _top_contributor(c, -0.001, {"A": "Alfa", "B": "Beta"})
    assert "Maior perda individual: Alfa (-0,37 p.p.)" in loss


def test_template_themes_cover_every_name_of_large_sleeves():
    from cdp.contracts import FactBook
    from cdp.workflow.tese import MAX_TEMA_EMISSORES, MAX_TEMAS, TemaTese, _sleeve_themes

    fb = FactBook(as_of=WEEK, snapshot_id="teste", facts={}, is_synthetic=True)

    def rows(prefix: str, n: int) -> list[dict]:
        return [{"iid": f"{prefix}{i:02d}", "name": f"Nome {prefix}"} for i in range(n)]

    longs, shorts, hedges = rows("L", 45), rows("S", 21), rows("H", 3)
    themes = _sleeve_themes(fb, [(longs, "Compras", "long", "Lógica.", "Risco."),
                                 (shorts, "Vendas", "short", "Lógica.", "Risco."),
                                 (hedges, "Hedges", "long_short", "Lógica.", "Risco.")])
    assert len(themes) <= MAX_TEMAS
    assert all(len(t["emissores"]) <= MAX_TEMA_EMISSORES for t in themes)
    covered = [i for t in themes for i in t["emissores"]]
    assert sorted(covered) == sorted(r["iid"] for r in longs + shorts + hedges)
    assert [t["lado"] for t in themes] == ["long"] * 3 + ["short"] * 2 + ["long_short"]
    titles = [t["titulo"] for t in themes]
    assert len(set(titles)) == len(titles) and not any(ch.isdigit() for t in titles for ch in t)
    for t in themes:
        TemaTese.model_validate(t)


def test_published_numbers_keep_enough_digits_for_half_up_display():
    from cdp.workflow.tese import _round_floats

    assert abs(_round_floats(-0.006249998424956)) < 0.00625  # continua −0,62% no painel
    assert _round_floats({"x": [0.0012499994]})["x"][0] < 0.00125  # continua +0,12%


def test_labels_match_the_panel_and_hide_raw_codes(demo):
    from cdp.workflow.tese_analise import country_label, factor_label, gap_label, sector_label

    assert country_label("LATAM") == "Regional (América Latina)"
    assert country_label("OTHER") == "Outros" and factor_label("country:OTHER")[0] == "País — Outros"
    assert sector_label("Other") == "Outros" and factor_label("sector:Other")[0] == "Setor — Outros"
    assert gap_label("Gap BR -10%") == ("BR", "Gap Brasil −10%")
    assert gap_label("Gap AR +41%") == ("AR", "Gap Argentina +41%")
    out, _ = demo
    r = _strict_load(thesis_dir(out / "book", WEEK) / PUBLISHED_JSON)["rendered"]
    gaps = [x for x in r["numbers"]["stress"] if x["kind"] == "gap"]
    assert gaps and all(re.fullmatch(r"gap_[a-z]{2}_(menos|mais)_\d+", x["code"]) for x in gaps)
    assert not any(re.search(r"\bGap [A-Z]{2}\b", x["label"]) for x in gaps)
    assert not any("OTHER" in f["label"] or "Other" in f["label"] for f in r["numbers"]["factors"])


def test_published_numbers_export_signal_labels_utilization_and_plain_notes(demo):
    out, _ = demo
    r = _strict_load(thesis_dir(out / "book", WEEK) / PUBLISHED_JSON)["rendered"]
    n = r["numbers"]
    assert n["signals"] == [{"code": "mom", "label": "Momentum residual"},
                            {"code": "val", "label": "Valor"},
                            {"code": "qual", "label": "Qualidade"},
                            {"code": "lowrisk", "label": "Baixo risco"},
                            {"code": "rev", "label": "Revisões de analistas"}]
    for key, col in (("countries", "net"), ("sectors", "net"), ("styles", "net"),
                     ("themes_market", "net"), ("commodities", "beta")):
        for row in n[key]:
            assert "utilization" in row, key
            if row[col] is None or not row["limit"]:
                assert row["utilization"] is None
            else:
                assert row["utilization"] == pytest.approx(abs(row[col]) / abs(row["limit"]))
    assert any(c["utilization"] is not None for c in n["countries"])
    assert n["event"] is None or "utilization" in n["event"]
    text = " ".join(r["notes"]) + " " + " ".join(v["note"] for v in n["vol_budget"])
    for jargon in ("Analytics", "conferem com os valores gravados", "match"):
        assert jargon not in text, jargon
    assert "Números recalculados com os pesos aprovados, sem reotimizar" in text


class _OneWeekBook:
    """Livro mínimo com uma proposta e a sua decisão (para a regra da semana ``manter``)."""

    def __init__(self, proposal, decision):
        self.p, self.d = proposal, decision

    def list_proposals(self, week):
        return [self.p]

    def list_decisions(self, week):
        return {self.p.version: self.d}

    def load_booked(self, week):
        raise ValueError("sem efetivação")


def test_hold_week_has_no_thesis_to_publish(demo):
    """Decisão que manteve a carteira vigente: sem carteira nova, não há tese nem pendência."""
    from cdp.workflow.tese import thesis_applicable
    from cdp.workflow.tese_analise import HoldWeekError, approved_proposal, is_hold

    out, _ = demo
    rt = _runtime(out)
    p = rt.book.load_proposal(WEEK)
    d = rt.book.list_decisions(WEEK)[p.version]
    assert not is_hold(p)
    assert thesis_applicable(_OneWeekBook(p, d), WEEK)

    hold = p.model_copy(update={"proposal_id": f"CDP-{WEEK.isoformat()}-manter",
                                "overrides": {"label": "manter"}, "positions": [], "trades": []})
    d_hold = d.model_copy(update={"proposal_id": hold.proposal_id,
                                  "proposal_hash": hold.proposal_hash()})
    assert is_hold(hold)
    with pytest.raises(HoldWeekError, match="manteve a carteira vigente"):
        approved_proposal(_OneWeekBook(hold, d_hold), WEEK)
    assert not thesis_applicable(_OneWeekBook(hold, d_hold), WEEK)
