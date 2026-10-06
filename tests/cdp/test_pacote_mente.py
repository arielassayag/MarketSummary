"""``cdp mente pacote``: qualquer assistente de IA como mente (DADOS SIMULADOS, offline).

Ida e volta para cada etapa: o pacote é exportado pela CLI, a "resposta do assistente" é o
esqueleto do próprio pacote (JSON enlatado, com a mente ``chatgpt``/``gemini``/``outro``), salva
no caminho indicado e validada pelos validadores das rotinas; JSON malformado recebe apontamentos
precisos. O pacote só lê arquivos preparados pelo código e nunca grava no livro.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import warnings
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cdp.__main__ import build_parser, main
from cdp.config import load_config
from cdp.research.guardrails import style_issues
from cdp.research.prompts import ESTILO_REGRAS
from cdp.workflow import notas as N
from cdp.workflow.demo import DEMO_FIRST_WEEK, DEMO_SEED, DemoStore, demo_sessions, run_demo
from cdp.workflow.pacote import ETAPAS_PACOTE
from cdp.workflow.runtime import Runtime

W = DEMO_FIRST_WEEK
WS = W.isoformat()
IID = "SIM001"
BRT = ZoneInfo("America/Sao_Paulo")
#: Mandato fixo dos testes (datas de demonstração em segundas-feiras): a regra de montagem
#: de `configs/cdp/fund.yaml` pode mudar sem mexer nestes testes.
LEGACY = Path(__file__).resolve().parent / "fixtures" / "fund_legado.yaml"


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("cdp_pacote_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_demo(out, days=1, cfg=load_config(LEGACY))
    return out


@pytest.fixture(scope="module")
def market():
    from cdp.data.synthetic import make_synthetic_market
    from cdp.workflow.demo import DEMO_HISTORY_START

    return make_synthetic_market(seed=DEMO_SEED, start=DEMO_HISTORY_START,
                                 as_of=demo_sessions(1)[-1])


@pytest.fixture()
def copia(demo, tmp_path) -> Path:
    dst = tmp_path / "copia"
    shutil.copytree(demo / "book", dst / "book")
    shutil.copytree(demo / "reports", dst / "reports")
    return dst


def _rt(root: Path, market) -> Runtime:
    return Runtime(load_config(LEGACY), root / "book", root / "market", root / "reports",
                   store_override=DemoStore(market),
                   clock=lambda: datetime(2024, 3, 4, 21, 30, tzinfo=BRT), teses_root=None)


def _base(root: Path) -> list[str]:
    return ["--config", str(LEGACY), "--book", str(root / "book"), "--reports",
            str(root / "reports"), "--market", str(root / "market")]


def _pacote(root: Path, capsys, *args: str) -> tuple[str, dict]:
    saida = root.parent / f"pacote_{args[1]}.md"
    rc = main(_base(root) + ["mente", "pacote", "--etapa", *args, "--saida", str(saida)])
    out = capsys.readouterr()
    assert rc == 0, out.err
    return saida.read_text(encoding="utf-8"), json.loads(out.out)


def _section(md: str, n: int) -> str:
    start = md.index(f"\n## {n}. ")
    nxt = md.find("\n## ", start + 5)
    return md[start:nxt if nxt > 0 else None]


def _example(md: str) -> dict:
    block = re.search(r"```json\n(.*?)\n```", _section(md, 6), re.S)
    assert block, "pacote sem esqueleto de exemplo"
    return json.loads(block.group(1))


def _run_validation(cmd: str, capsys) -> tuple[int, str]:
    argv = shlex.split(cmd)
    assert argv[:5] == ["uv", "run", "python", "-m", "cdp"], cmd
    extra = [] if "--config" in argv else ["--config", str(LEGACY)]
    rc = main(extra + argv[5:])
    out = capsys.readouterr()
    return rc, out.out + out.err


def _assert_self_contained(md: str, info: dict, mente: str) -> None:
    for n, title in ((1, "Como usar"), (2, "Instruções para o assistente"),
                     (3, "Regras invioláveis"), (5, "Schema JSON obrigatório"),
                     (6, "Esqueleto de exemplo"), (7, "Entrega e validação"), (8, "Procedência")):
        assert f"## {n}. {title}" in md, title
    assert all(r in md for r in ESTILO_REGRAS)  # o guia de estilo vai no pacote
    assert "DADOS SIMULADOS" in md
    schema = re.search(r"```json\n(.*?)\n```", _section(md, 5), re.S)
    assert schema and json.loads(schema.group(1))["type"] == "object"
    assert f'`"{mente}"`' in md
    assert info["validacao"] in md and info["salvar_json_em"] in md
    build_parser().parse_args(shlex.split(info["validacao"])[5:])  # comando exato e aceito
    if info["publicacao"]:
        build_parser().parse_args(shlex.split(info["publicacao"])[5:])
    for word in ("quar" + "tr",):  # nenhum canal proprietário
        assert word not in md.lower()


# ----------------------------------------------------------------------------- ida e volta


def test_tese_round_trip(copia, capsys):
    md, info = _pacote(copia, capsys, "tese", "--semana", WS, "--mente", "chatgpt")
    _assert_self_contained(md, info, "chatgpt")
    assert info["salvar_json_em"].endswith(f"book/{WS}/tese/tese.json")
    resposta = _example(md)
    assert resposta["mind"] == "chatgpt" and resposta["week"] == WS
    Path(info["salvar_json_em"]).write_text(json.dumps(resposta, ensure_ascii=False),
                                            encoding="utf-8")
    rc, out = _run_validation(info["validacao"], capsys)
    assert rc == 0 and json.loads(out)["ok"] is True, out
    # malformado: campo obrigatório ausente ⇒ apontamento de schema preciso
    sem_titulo = {k: v for k, v in resposta.items() if k != "titulo"}
    Path(info["salvar_json_em"]).write_text(json.dumps(sem_titulo), encoding="utf-8")
    rc, out = _run_validation(info["validacao"], capsys)
    assert rc == 1 and "titulo" in out
    # número livre e fato inexistente
    ruim = {**resposta, "resumo": "Carteira com 23 nomes e {{fact:nao.existe}}."}
    Path(info["salvar_json_em"]).write_text(json.dumps(ruim, ensure_ascii=False),
                                            encoding="utf-8")
    rc, out = _run_validation(info["validacao"], capsys)
    problemas = json.loads(out)["problemas"]
    assert rc == 1
    assert "resumo: número fora de placeholder ['23']" in problemas
    assert "resumo: fato inexistente no FactBook ['nao.existe']" in problemas


def test_nota_round_trip(copia, market, capsys):
    N.prepare_note(_rt(copia, market), IID, W)
    md, info = _pacote(copia, capsys, "nota", "--emissor", IID, "--data", WS,
                       "--mente", "gemini")
    _assert_self_contained(md, info, "gemini")
    assert "Fontes públicas sugeridas" in md and "https://dados.cvm.gov.br/" in md
    resposta = _example(md)
    assert resposta["mind"] == "gemini" and resposta["issuer_id"] == IID
    path = Path(info["salvar_json_em"])
    path.write_text(json.dumps(resposta, ensure_ascii=False), encoding="utf-8")
    rc, out = _run_validation(info["validacao"], capsys)
    assert rc == 0 and json.loads(out)["ok"] is True, out
    ruim = {**resposta, "resumo": "Upside de 35% com resultado incrível.",
            "fontes": [{"id": "F1", "tipo": "regulatorio", "instituicao": "CVM",
                        "titulo": "Formulário de referência", "url": "http://www.cvm.gov.br/",
                        "publicado_em": "2030-01-01"}]}
    path.write_text(json.dumps(ruim, ensure_ascii=False), encoding="utf-8")
    rc, out = _run_validation(info["validacao"], capsys)
    problemas = json.loads(out)["problemas"]
    assert rc == 1
    assert "resumo: número fora de placeholder ['35%']" in problemas
    assert "fontes[0].url: use uma URL https pública" in problemas
    assert any("posterior à nota 2024-03-04 (look-ahead)" in p for p in problemas)
    assert any("tom promocional" in p for p in problemas)
    path.write_text("[]", encoding="utf-8")
    rc, out = _run_validation(info["validacao"], capsys)
    assert rc == 1 and "o arquivo precisa conter um objeto JSON" in out
    # a publicação de uma nota feita fora das rotinas segue o mesmo caminho
    path.write_text(json.dumps(resposta, ensure_ascii=False), encoding="utf-8")
    pub = N.publish_note(_rt(copia, market), IID, W)
    assert pub["autoria"] == "mente" and pub["mind"] == "gemini"


def test_comentario_diario_round_trip(copia, market, capsys):
    from cdp.workflow.agenda import validate_daily_commentary

    md, info = _pacote(copia, capsys, "comentario-diario", "--data", WS)
    _assert_self_contained(md, info, "outro")  # mente padrão
    resposta = _example(md)
    assert resposta["mind"] == "outro"
    path = Path(info["salvar_json_em"])
    path.write_text(json.dumps(resposta, ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_daily_commentary(_rt(copia, market), W)
    assert ok, issues
    path.write_text(json.dumps({**resposta, "headline": "Fundo sobe 1,2% 🚀"},
                               ensure_ascii=False), encoding="utf-8")
    ok, issues = validate_daily_commentary(_rt(copia, market), W)
    assert not ok and any("['1,2%']" in i for i in issues) and any("emoji" in i for i in issues)


def test_pesquisa_validates_alone_before_the_decision_exists(copia, market, capsys):
    """A etapa de pesquisa valida só o research_pack.json (a decisão ainda não existe ou ficou
    velha); o pacote diz que a decisão é refeita depois."""
    inputs = copia / "book" / WS / "inputs"
    (inputs / "pm_decision.json").unlink()
    md_p, info_p = _pacote(copia, capsys, "pesquisa", "--semana", WS, "--mente", "outro")
    assert info_p["validacao"].endswith(f"validate --week {WS} --mind outro --so-pesquisa")
    assert "refaça a decisão da semana" in md_p and "--etapa decisao" in md_p
    Path(info_p["salvar_json_em"]).write_text(json.dumps(_example(md_p), ensure_ascii=False),
                                              encoding="utf-8")
    args = build_parser().parse_args(shlex.split(info_p["validacao"])[5:])
    assert args.so_pesquisa is True and args.mind == "outro"
    rt = _rt(copia, market)
    ok, issues = rt.validate_inputs(W, mind="outro", so_pesquisa=True)
    assert ok, issues
    # sem --so-pesquisa, a semana inteira acusa a decisão ausente
    ok, issues = rt.validate_inputs(W, mind="outro")
    assert not ok and any("pm_decision.json: arquivo ausente" in i for i in issues)


def test_pesquisa_e_decisao_round_trip(copia, market, capsys):
    md_p, info_p = _pacote(copia, capsys, "pesquisa", "--semana", WS, "--mente", "outro")
    md_d, info_d = _pacote(copia, capsys, "decisao", "--semana", WS, "--mente", "outro")
    for md, info in ((md_p, info_p), (md_d, info_d)):
        _assert_self_contained(md, info, "outro")
    assert info_p["validacao"].endswith(f"validate --week {WS} --mind outro --so-pesquisa")
    assert info_d["validacao"].endswith(f"validate --week {WS} --mind outro")
    assert "## 10. Regras invioláveis" not in md_p  # o briefing entra sem as regras do PM
    assert "Pesquisa da semana já gravada (resumo" in md_d  # a decisão vê a pesquisa gravada
    assert '"notes": [' not in md_d  # resumo, não o JSON integral
    assert info_d["anexos"] == [(copia / "book" / WS / "inputs" / "research_pack.json").as_posix()]
    pack, dec = _example(md_p), _example(md_d)
    assert pack["mind"] == dec["mind"] == "outro"
    Path(info_p["salvar_json_em"]).write_text(json.dumps(pack, ensure_ascii=False),
                                              encoding="utf-8")
    Path(info_d["salvar_json_em"]).write_text(json.dumps(dec, ensure_ascii=False),
                                              encoding="utf-8")
    rt = _rt(copia, market)
    ok, issues = rt.validate_inputs(W, mind="outro")
    assert ok, issues
    ok, issues = rt.validate_inputs(W, mind="chatgpt")
    assert not ok and any("mind esperado 'chatgpt'" in i for i in issues)


def test_comentario_semanal_needs_the_close_report(copia, capsys):
    saida = copia.parent / "semanal.md"
    d = "2024-03-08"
    rc = main(_base(copia) + ["mente", "pacote", "--etapa", "comentario-semanal", "--data", d,
                              "--saida", str(saida)])
    err = capsys.readouterr().err
    assert rc == 1 and "weekly close-report --date 2024-03-08" in err and not saida.exists()
    folder = copia / "reports" / "semanal" / d
    folder.mkdir(parents=True)
    (folder / "fatos.md").write_text("# Fatos da semana\n\n> **DADOS SIMULADOS**\n\n"
                                     "| fact_id | Valor |\n|---|---|\n| `wk.ret` | +0,40% |\n",
                                     encoding="utf-8")
    (folder / "comentario.schema.json").write_text(json.dumps({"type": "object"}),
                                                   encoding="utf-8")
    md, info = _pacote(copia, capsys, "comentario-semanal", "--data", d, "--mente", "chatgpt")
    assert info["validacao"].endswith(f"validate-weekly-report --date {d}")
    assert info["publicacao"].endswith(f"weekly close-report --date {d} --publish")
    assert "`wk.ret`" in md and all(r in md for r in ESTILO_REGRAS)


# ----------------------------------------------------------------------------- argumentos


@pytest.mark.parametrize("argv", [
    ["--etapa", "tese"],                                         # sem --semana
    ["--etapa", "tese", "--semana", WS, "--data", WS],           # argumento a mais
    ["--etapa", "nota", "--data", WS],                           # sem --emissor
    ["--etapa", "comentario-diario", "--semana", WS],
])
def test_bad_argument_combinations(copia, capsys, argv):
    rc = main(_base(copia) + ["mente", "pacote", *argv, "--saida", str(copia.parent / "x.md")])
    assert rc == 2 and "Erro:" in capsys.readouterr().err


def test_parser_rejects_unknown_stage_and_mind(capsys):
    for argv in (["mente", "pacote", "--etapa", "carteira", "--saida", "x.md"],
                 ["mente", "pacote", "--etapa", "tese", "--semana", WS, "--mente", "x",
                  "--saida", "x.md"],
                 ["mente", "pacote", "--etapa", "nota", "--emissor", "br_vale", "--data", WS,
                  "--saida", "x.md"]):
        with pytest.raises(SystemExit):
            build_parser().parse_args(argv)
    capsys.readouterr()
    assert set(ETAPAS_PACOTE) == {"pesquisa", "decisao", "tese", "nota", "comentario-diario",
                                  "comentario-semanal"}


def test_package_never_written_inside_the_book(copia, capsys):
    for inside in (copia / "book" / "pacote.md", copia / "reports" / "daily" / "p.md"):
        rc = main(_base(copia) + ["mente", "pacote", "--etapa", "tese", "--semana", WS,
                                  "--saida", str(inside)])
        assert rc == 2 and not inside.exists()
        assert "grave o pacote fora" in capsys.readouterr().err


def test_missing_prepared_files_say_what_to_run(copia, capsys):
    rc = main(_base(copia) + ["mente", "pacote", "--etapa", "nota", "--emissor", "SIM002",
                              "--data", WS, "--saida", str(copia.parent / "n.md")])
    err = capsys.readouterr().err
    assert rc == 1 and "nota prepare --issuer SIM002 --date 2024-03-04" in err


def test_demo_templates_follow_the_style_guide(demo):
    """Textos de código que chegam ao investidor (tese publicada, comentário do dia sem a linha
    interna de procedência) não trazem jargão de tecnologia, coloquialismo nem tom promocional."""
    tese = json.loads((demo / "book" / WS / "tese" / "tese_publicada.json")
                      .read_text(encoding="utf-8"))
    assert style_issues(json.dumps(tese["rendered"], ensure_ascii=False)) == []
    rep = (demo / "reports" / "daily" / WS / "relatorio.md").read_text(encoding="utf-8")
    section = rep[rep.index("## Comentário"):]
    nxt = section.find("\n## ", 4)
    section = section[:nxt if nxt > 0 else None]
    assert "Autoria:" in section and style_issues(section) == []  # inteira, com a autoria
    assert date.fromisoformat(WS) == W


# ----------------------------------------------------------------------------- revisão (fixer B)


def _big_pack(n: int) -> dict:
    long = ("Texto longo da pesquisa com fontes locais e argumentos detalhados sobre o emissor, "
            "o setor e o país, sem números livres. ") * 12
    notes = [{
        "note_id": f"{WS}-SIM{i:03d}-fundamental", "issuer_id": f"SIM{i:03d}",
        "role": "fundamental", "provider": "outro", "stance": 1, "confidence": 0.6,
        "horizon_weeks": 8, "thesis": long, "bull_points": [long] * 4, "bear_points": [long] * 4,
        "catalysts": [{"description": long, "expected_date": None, "direction": "uncertain"}] * 4,
        "key_risks": [long] * 4, "squeeze": {"verdict": "caution", "rationale": long},
        "evidence": [{"kind": "source", "ref_id": f"https://www.gov.br/cvm/{k}", "note": long}
                     for k in range(8)], "created_at": f"{WS}T12:00:00-03:00"}
        for i in range(n)]
    macro = [{"note_id": f"{WS}-{c}-macro", "scope": c, "stance": 0, "regime": long,
              "summary": long, "key_events": [], "risks": [long] * 4,
              "portfolio_implications": [long] * 4, "evidence": [], "provider": "outro",
              "created_at": f"{WS}T12:00:00-03:00"} for c in ("BR", "MX", "CL", "CO", "PE", "AR")]
    return {"mind": "outro", "notes": notes, "macro": macro, "views": []}


def test_decision_package_summarises_a_large_research_pack(copia, capsys):
    """Pacote da decisão com uma pesquisa do tamanho da real (~160 notas longas): o resumo
    limita o tamanho por nota, o comando informa os tokens estimados e o cabeçalho a janela."""
    from cdp.workflow.pacote import ALERTA_TOKENS, resumo_pesquisa

    rp = copia / "book" / WS / "inputs" / "research_pack.json"
    rp.write_text(json.dumps(_big_pack(160), ensure_ascii=False, indent=2), encoding="utf-8")
    raw_bytes = rp.stat().st_size
    resumo = resumo_pesquisa(rp)
    assert len(resumo.encode("utf-8")) < raw_bytes / 8
    assert len(resumo.encode("utf-8")) / 160 < 1_400  # bytes por nota, com macro e cabeçalho
    assert "{{" not in resumo.replace("{{fact:", "") and "squeeze: caution" in resumo
    md, info = _pacote(copia, capsys, "decisao", "--semana", WS, "--mente", "chatgpt")
    assert info["tokens_estimados"] < ALERTA_TOKENS and "alerta_tamanho" not in info
    m = re.search(r"Tamanho estimado: cerca de (\d+) mil tokens", md)
    assert m and abs(int(m.group(1)) * 1000 - info["tokens_estimados"]) < 2_000
    assert "anexe também" in md and rp.as_posix() in md


def test_synthetic_package_header_never_claims_real_prices(copia, capsys):
    md, _ = _pacote(copia, capsys, "tese", "--semana", WS)
    head = md[:md.index("## 1. ")]
    assert "preços reais" not in head and "mercado sintético — DADOS SIMULADOS" in head


def test_package_output_policy(copia, capsys, tmp_path):
    base = _base(copia) + ["mente", "pacote", "--etapa", "tese", "--semana", WS, "--saida"]
    # só .md
    rc = main(base + [str(tmp_path / "pacote.txt")])
    assert rc == 2 and ".md" in capsys.readouterr().err
    # arquivo existente que não é pacote: nunca sobrescrito
    alheio = tmp_path / "AGENTS.md"
    alheio.write_text("# Regras do projeto\n", encoding="utf-8")
    rc = main(base + [str(alheio)])
    assert rc == 2 and "não é um pacote" in capsys.readouterr().err
    assert alheio.read_text(encoding="utf-8") == "# Regras do projeto\n"
    # pacote anterior: substituído
    saida = tmp_path / "pacote.md"
    assert main(base + [str(saida)]) == 0
    capsys.readouterr()
    assert main(base + [str(saida)]) == 0
    capsys.readouterr()
    # dentro do repositório (fora de outputs/): recusado, nada gravado
    repo = Path(__file__).resolve().parents[2]
    for inside in (repo / "pacote_teste_fixer.md", repo / "configs" / "cdp" / "pacote.md"):
        rc = main(base + [str(inside)])
        assert rc == 2 and "fora do repositório" in capsys.readouterr().err
        assert not inside.exists()


def test_instructions_show_the_effective_deadline():
    """INSTRUCTIONS.md mostra o prazo efetivo do dia de montagem (o mesmo de
    ``semanal.prazo_efetivo``): legado 16:30; com a janela de execução, até 15:00 e mais cedo
    no pregão encurtado dos EUA."""
    from types import SimpleNamespace

    from cdp.research.pm_agent import _deadline_text

    legado = load_config(LEGACY)
    if legado.execution is None:
        assert _deadline_text(SimpleNamespace(week=date(2026, 10, 9), cfg=legado)) == \
            legado.fund.decision_deadline_local
    ativo = legado.with_overrides({"fund": {"rebalance_weekday": "LAST_US_SESSION"},
                                   "execution": {}})
    sexta = _deadline_text(SimpleNamespace(week=date(2026, 10, 9), cfg=ativo))
    meio_pregao = _deadline_text(SimpleNamespace(week=date(2026, 11, 27), cfg=ativo))
    assert sexta <= "15:00" and meio_pregao < sexta


def test_mind_swap_above_s1_is_treated_as_abstention(copia):
    """CR-3.5: com as visões de IA em S2/S3, uma mente diferente da incumbente não herda a fase
    (decisão tratada como abstenção, só-quant); em S0/S1 nada muda."""
    from types import SimpleNamespace

    from cdp.research.pm_agent import PMDecisionOutput, _apply_mind_governance

    raw = json.loads((copia / "book" / WS / "inputs" / "pm_decision.json")
                     .read_text(encoding="utf-8"))
    out = PMDecisionOutput.model_validate({**raw, "mind": "gemini"})
    assert out.views and not out.abstain
    prev = PMDecisionOutput.model_validate({**raw, "mind": "claude-code"})
    base = load_config(LEGACY)
    for phase, swapped in (("S1", False), ("S2", True), ("S3", True)):
        cfg = base.with_overrides({"research": {"llm_phase": phase}})
        issues: list[str] = []
        res = _apply_mind_governance(out, SimpleNamespace(cfg=cfg, previous_pm_output=prev),
                                     issues)
        assert (res.abstain and not res.views) is swapped, phase
        assert bool(issues) is swapped and (not issues or "no máximo em S1" in issues[0])
    cfg = base.with_overrides({"research": {"llm_phase": "S3"}})
    same = PMDecisionOutput.model_validate({**raw, "mind": "claude-code"})
    assert _apply_mind_governance(same, SimpleNamespace(cfg=cfg, previous_pm_output=prev),
                                  []) == same
    abst = prev.model_copy(update={"abstain": True})  # abstenção não define incumbente
    assert _apply_mind_governance(out, SimpleNamespace(cfg=cfg, previous_pm_output=abst),
                                  []) == out
