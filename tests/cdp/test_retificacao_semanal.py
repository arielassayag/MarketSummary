"""DADOS SIMULADOS: retificação editorial finita, sem MOC/NAV/modelos/coleta."""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from cdp.__main__ import build_parser
from cdp.audit import AuditLog
from cdp.contracts import Fact, FactBook
from cdp.hashing import sha256_file
from cdp.research.comentario_semanal import (
    ComentarioSemanal,
    MudancaComentada,
    carregar_comentario,
    lado_depois,
    problemas_lado,
    render_comentario,
    verificar_comentario,
)
from cdp.site import coletar_dados
from cdp.workflow.painel import _daily_reports, _Issues
from cdp.workflow.painel_publicacao import Limites, _Cortes, _reports
from cdp.workflow.retificacao_semanal import (
    EVENT,
    RetificacaoSemanal,
    _autorizar_cli,
    listar,
    publicar,
    status,
    validar,
    verificar,
)

D = date(2026, 10, 9)
IID = "BR_SIMULADA"
OLD = "Empresa simulada entrou comprada; decisão apoiada nos fatos publicados."


def _fb(weight=-0.2, unit="pct"):
    fid = f"mud.{IID}.depois"
    fact = Fact(fact_id=fid, issuer_id=IID, name="Peso DADOS SIMULADOS",
                value=weight, unit=unit, formatted=(f"{weight * 100:+.2f}%".replace(".", ",")
                                                  if weight is not None else "n/d"),
                formula="DADOS SIMULADOS: peso recebido, nenhum retorno calculado")
    name = Fact(fact_id=f"mud.{IID}.nome", issuer_id=IID, name="Nome",
                value=None, unit="count", formatted="Empresa simulada", formula="DADOS SIMULADOS")
    return FactBook(as_of=D, snapshot_id="DADOS SIMULADOS", facts={fid: fact, name.fact_id: name},
                    is_synthetic=True)


def _comment(rationale=OLD, side=None):
    return ComentarioSemanal(mind="codex", resumo="DADOS SIMULADOS: comentário de teste.",
        desempenho_semana=["Resultado conforme os fatos publicados."],
        atribuicao=["Atribuição conforme os fatos publicados."],
        risco_nova_carteira=["Risco conforme os fatos publicados."],
        execucao=["Execução conforme os fatos publicados."],
        mudancas_carteira=[MudancaComentada(emissor=IID, tipo="entrada", racional=rationale,
                                          lado_depois=side)])


@pytest.fixture
def case(tmp_path):
    book, reports = tmp_path / "book", tmp_path / "reports"
    book.mkdir()
    folder = reports / "semanal" / D.isoformat()
    folder.mkdir(parents=True)
    fb = _fb()
    comment = _comment().model_dump(mode="json")
    comment["mudancas_carteira"][0].pop("lado_depois")  # JSON legado literal, anterior à defesa.
    (folder / "comentario.json").write_text(json.dumps(comment, ensure_ascii=False))
    (folder / "factbook.json").write_text(fb.model_dump_json())
    md = "# DADOS SIMULADOS — relatório original\n\n" + OLD + "\n"
    markup = "<!doctype html><pre>" + html.escape(md) + "</pre>"
    (folder / "relatorio.md").write_text(md)
    (folder / "relatorio.html").write_text(markup)
    (book / "ledger.csv").write_text("data,NAV,aviso\n2026-10-09,1000000,DADOS SIMULADOS\n")
    (book / "booked.json").write_text('{"aviso":"DADOS SIMULADOS","imutavel":true}')
    (book / "registro.json").write_text('{"aviso":"DADOS SIMULADOS","NAV":1000000}')
    receipt = {"md": str(folder / "relatorio.md"), "html": str(folder / "relatorio.html"),
               "md_sha256": sha256_file(folder / "relatorio.md"),
               "html_sha256": sha256_file(folder / "relatorio.html"),
               "registro": "d" * 64, "factbook": fb.factbook_hash(),
               "comentario_da_mente": True, "apontamentos": [], "tipo": "montagem"}
    log = AuditLog(book / "audit_log.jsonl")
    log.append("DADOS_SIMULADOS_PREEXISTENTE", "CDP", {"aviso": "DADOS SIMULADOS"})
    event = log.append("WEEKLY_CLOSE_REPORT", "CDP", receipt, week=D)
    entry = RetificacaoSemanal(schema_version="cdp.weekly.editorial/v1", data=D, mind="codex",
        evento_original=event.event_hash, recibo_original=receipt,
        comentario_original_sha256=sha256_file(folder / "comentario.json"),
        factbook_original_sha256=sha256_file(folder / "factbook.json"),
        correcoes=[{"emissor": IID, "texto_original": OLD}])
    rt = SimpleNamespace(book_root=book, reports_root=reports,
                         cfg=SimpleNamespace(fund=SimpleNamespace(inception_date=D)))
    return rt, entry, folder, log


def test_append_only_nav_original_bytes_audit_prefix_and_hash_links(case):
    rt, entry, folder, log = case
    before = {path: path.read_bytes() for path in folder.iterdir()}
    monetary = {path: path.read_bytes() for path in Path(rt.book_root).iterdir()
                if path.name != "audit_log.jsonl"}
    audit_prefix = log.path.read_bytes()
    result = publicar(rt, entry, expected_mind="codex")
    assert all(path.read_bytes() == content for path, content in before.items())
    assert all(path.read_bytes() == content for path, content in monetary.items())
    assert log.path.read_bytes().startswith(audit_prefix)
    assert len(log.events()) == 3 and log.events()[-1].event_type == EVENT
    assert log.events()[-1].actor == "codex" and log.verify_chain()[0]
    assert verificar(rt) == []
    note = folder / "retificacoes" / result["id"]
    artifact = json.loads((note / "retificacao.json").read_bytes())
    assert artifact["entrada"]["recibo_original"]["md_sha256"] == entry.recibo_original.md_sha256
    assert artifact["correcoes_calculadas"][0]["lado_depois"] == "vendida"
    assert artifact["correcoes_calculadas"][0]["peso_publicado"] == -0.2
    assert artifact["correcoes_calculadas"][0]["peso_fact_id"] == f"mud.{IID}.depois"
    assert "DADOS SIMULADOS" in (note / "retificacao.md").read_text()
    assert (note / "../../relatorio.html").resolve() == folder / "relatorio.html"
    assert "Onde se lê:" in (note / "retificacao.html").read_text()
    assert "Leia-se:" in (note / "retificacao.html").read_text()
    assert "posição vendida" in (note / "retificacao.html").read_text()
    with pytest.raises(FileExistsError):
        publicar(rt, entry, expected_mind="codex")
    assert len(log.events()) == 3


@pytest.mark.parametrize("file", ["relatorio.md", "relatorio.html", "factbook.json", "comentario.json"])
def test_original_tampering_refuses_without_new_files_or_events(case, file):
    rt, entry, folder, log = case
    before = log.path.read_bytes()
    with (folder / file).open("a") as handle:
        handle.write("ADULTERADO DADOS SIMULADOS")
    assert validar(rt, entry, expected_mind="codex")
    with pytest.raises(ValueError):
        publicar(rt, entry, expected_mind="codex")
    assert log.path.read_bytes() == before
    assert not (folder / "retificacoes").exists()


@pytest.mark.parametrize("key", ["registro", "factbook", "md_sha256", "html_sha256"])
def test_false_receipt_refused_against_original_event(case, key):
    rt, entry, folder, log = case
    data = entry.model_dump(mode="json")
    data["recibo_original"][key] = "e" * 64
    wrong = RetificacaoSemanal.model_validate(data)
    assert validar(rt, wrong, expected_mind="codex")
    assert not (folder / "retificacoes").exists()
    assert len(log.events()) == 2


def test_mind_original_target_and_additional_economic_field_refused(case):
    rt, entry, folder, log = case
    assert validar(rt, entry, expected_mind="gemini")
    bad = entry.model_dump(mode="json")
    bad["correcoes"][0]["texto_original"] = "Outro texto não publicado."
    assert validar(rt, RetificacaoSemanal.model_validate(bad), expected_mind="codex")
    bad["correcoes"][0]["NAV"] = 2000000
    with pytest.raises(ValidationError):
        RetificacaoSemanal.model_validate(bad)
    assert not (folder / "retificacoes").exists() and len(log.events()) == 2


@pytest.mark.parametrize("file", ["retificacao.json", "retificacao.md", "retificacao.html"])
def test_retification_adulteration_is_not_presented_as_verified(case, file):
    rt, entry, folder, log = case
    result = publicar(rt, entry, expected_mind="codex")
    path = folder / "retificacoes" / result["id"] / file
    with path.open("a") as handle:
        handle.write("ADULTERADO DADOS SIMULADOS")
    assert verificar(rt)
    assert listar(rt, D) == []
    assert status(rt)["pendente"]
    assert len(log.events()) == 3


def test_artifact_without_event_detected(case):
    rt, entry, folder, log = case
    result = publicar(rt, entry, expected_mind="codex")
    payload = json.loads((folder / "retificacoes" / result["id"] / "retificacao.json").read_bytes())
    # DADOS SIMULADOS: preservar como negativo de integridade, sem reparar o livro.
    original_events = log.path.read_text().splitlines()
    log.path.write_text("\n".join(original_events[:-1]) + "\n")
    assert verificar(rt) and payload["entrada"]["evento_original"] == entry.evento_original


def test_event_without_artifact_detected(case):
    rt, _, _, log = case
    log.append(EVENT, "codex", {"aviso": "DADOS SIMULADOS: evento órfão"}, week=D)
    assert verificar(rt) == ["Evento de retificação sem artefato correspondente"]


def test_unpublished_bad_comment_not_misrepresented_as_report_pending(case):
    rt, _, folder, _ = case
    (folder / "relatorio.md").write_text("DADOS SIMULADOS: comentário-modelo publicado.")
    (folder / "relatorio.html").write_text("<pre>DADOS SIMULADOS: comentário-modelo publicado.</pre>")
    assert not status(rt)["pendente"]  # A frase recusada não integra o relatório selado.


@pytest.mark.parametrize(("weight", "side", "text"), [
    (-0.2, "vendida", "Empresa simulada entrou vendida."),
    (0.2, "comprada", "Empresa simulada entrou comprada."),
    (0.0, "zerada", "Empresa simulada ficou zerada."),
])
def test_direction_is_deterministic_buy_sell_and_zero(weight, side, text):
    fb = _fb(weight)
    out = _comment(text, side)
    assert lado_depois(fb, IID) == side
    assert verificar_comentario(out, fb, [{"emissor": IID, "tipo": "entrada"}]) == []
    assert f"Posição após o fechamento: {side}." in render_comentario(out, fb)["mudancas_carteira"][IID]
    other = "comprada" if side != "comprada" else "vendida"
    assert problemas_lado(MudancaComentada(emissor=IID, tipo="entrada", racional=text, lado_depois=other), fb)


@pytest.mark.parametrize("weight", [None, float("nan"), float("inf")])
def test_absence_nonfinite_does_not_become_zero(weight):
    fb = _fb(weight)
    assert lado_depois(fb, IID) is None
    assert problemas_lado(_comment("Empresa simulada ficou zerada.").mudancas_carteira[0], fb)


def test_wrong_unit_and_wrong_claim_reject_even_if_structured_side_correct():
    assert lado_depois(_fb(-0.2, unit="usd"), IID) is None
    out = _comment(OLD, "vendida")
    assert problemas_lado(out.mudancas_carteira[0], _fb())
    fb = _fb()
    fid = f"mud.{IID}.depois"
    foreign = fb.model_copy(update={"facts": {**fb.facts, fid: fb.facts[fid].model_copy(
        update={"issuer_id": "BR_OUTRO_SIMULADO"})}})
    assert lado_depois(foreign, IID) is None
    assert problemas_lado(out.mudancas_carteira[0], foreign)


def test_legacy_bad_direction_cannot_pass_commentary_before_seal(case):
    rt, entry, folder, _ = case
    out, authored, issues = carregar_comentario(folder / "comentario.json", _fb(),
        [{"emissor": IID, "tipo": "entrada"}], montagem=True, mente_esperada="codex")
    assert not authored and any("direcional" in issue for issue in issues)
    assert all("entrou comprada" not in item.racional for item in out.mudancas_carteira)
    assert entry.recibo_original.comentario_da_mente is True  # Legado preservado, não regravado.


def test_grammar_scope_does_not_claim_all_natural_language():
    # Forma deliberadamente fora do contrato finito; não alegar revisão semântica universal.
    assert problemas_lado(_comment("A leitura da gestão se inclina para o lado comprador.").mudancas_carteira[0], _fb()) == []
    assert problemas_lado(_comment("Saiu da posição comprada anterior.").mudancas_carteira[0], _fb()) == []


def test_editorial_pending_vs_corrected_and_portal_original_notice(case):
    rt, entry, folder, _ = case
    pending = status(rt)
    assert pending["pendente"] and pending["relatorios"][0]["pendentes"] == [IID]
    result = publicar(rt, entry, expected_mind="codex")
    completed = status(rt)
    assert not completed["pendente"] and completed["relatorios"][0]["corrigidos"] == [IID]
    _, index = _daily_reports(rt, rt.cfg, [], _Issues(), 10)
    weekly = next(item for item in index if item["kind"] == "semanal")
    assert weekly["retificacoes"][0]["id"] == result["id"]
    _, published = _reports([], index, Limites(), _Cortes())
    assert next(item for item in published if item["kind"] == "semanal")["retificacoes"] == weekly["retificacoes"]
    inventory = coletar_dados(rt, Path(rt.book_root).parent, desde_o_inicio=False)
    destinations = {artifact.destino for _, artifact in inventory}
    assert f"dados/relatorios/semanal/{D}/relatorio.html" in destinations
    assert f"dados/relatorios/semanal/{D}/retificacoes/{result['id']}/retificacao.html" in destinations
    assert folder.joinpath("relatorio.md").read_text().endswith(OLD + "\n")


def test_cli_normal_contract_no_gate_or_publish_execution():
    args = build_parser().parse_args(["weekly", "rectify-report", "--date", str(D), "--mind", "codex"])
    assert args.action == "rectify-report" and args.date == D and not args.publish
    assert args.arquivo is None
    for argv in (["weekly", "rectify-report"], ["weekly", "rectify-report", "--date", str(D)]):
        with pytest.raises(SystemExit):
            build_parser().parse_args(argv)


def test_cli_authorization_requires_normal_gate_and_clone_paths(case, monkeypatch):
    rt, _, _, _ = case
    args = SimpleNamespace(execucao=None, trava=None, raiz=Path(rt.book_root).parent)
    with pytest.raises(ValueError, match="execução e trava"):
        _autorizar_cli(args, "codex", rt)
    from cdp import executor
    calls = []
    monkeypatch.setattr(executor, "verificar", lambda *args, **kw: calls.append("GET proibido"))
    args.execucao, args.trava = "DADOS-SIMULADOS", "TRAVA-SIMULADA"
    monkeypatch.setattr(executor, "ler_execucao", lambda *args: {"tarefa": "cdp-diario", "mente": "codex", "trava": args[1]})
    with pytest.raises(ValueError, match="vinculadas"):
        _autorizar_cli(args, "codex", rt)
    assert calls == []


def test_exclusive_publisher_carries_original_and_errata_with_current_gate(case, monkeypatch):
    """Transportes simulados: contrato real de seleção, zero Git/rede/publicação."""
    from cdp import executor
    from cdp.rotinas import carregar

    rt, entry, folder, log = case
    root = Path(rt.book_root).parent
    old_receipt = {"execucao": "DIARIA-ANTERIOR-SIMULADA", "aviso": "DADOS SIMULADOS",
                   "instantaneo": {}}  # Retrato anterior NÃO é inventário terminal.
    old_literal = json.dumps(old_receipt, sort_keys=True)
    original_files = {str(path.relative_to(root)): sha256_file(path)
                      for path in root.rglob("*") if path.is_file()}
    current_gate = {"tarefa": "cdp-diario", "mente": "codex", "trava": "TRAVA-NOVA",
                    "ensaio": False, "sem_trava": False, "instantaneo": dict(original_files)}
    preserved = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()
                 and path != log.path}
    publicar(rt, entry, expected_mind="codex")
    current_files = {str(path.relative_to(root)): sha256_file(path)
                     for path in root.rglob("*") if path.is_file()}
    task = carregar(Path(__file__).resolve().parents[2] / "configs/cdp/rotinas.yaml").tarefa("cdp-diario")
    assert task.exclusiva
    transport = []
    monkeypatch.setattr(executor, "git", lambda *args, **kw: SimpleNamespace(stdout="", returncode=0))
    monkeypatch.setattr(executor, "verificar", lambda *args, **kw: (executor.OK, {"sou_o_executor": True}))
    monkeypatch.setattr(executor, "ler_execucao", lambda *args: current_gate)
    monkeypatch.setattr(executor, "estado_dos_caminhos", lambda *args: current_files)
    monkeypatch.setattr(executor, "_confirmar_trava", lambda *args: {"estado": "renovada"})

    def capture(*args, **kw):
        transport.append(kw)
        return executor.OK, args[3]

    monkeypatch.setattr(executor, "_publicar_delta", capture)
    code, out = executor.publicar(root, task, "CDP: DADOS SIMULADOS retificação",
                                 rt=rt, env={}, execucao="DIARIA-NOVA", trava="TRAVA-NOVA", mente="codex")
    assert code == executor.OK and len(transport) == 1
    assert transport[0]["delta"] == sorted(current_files)
    assert transport[0]["exec_id"] == "DIARIA-NOVA" and transport[0]["exige"]
    assert transport[0]["trava_id"] == "TRAVA-NOVA" and transport[0]["verificar_livro"]
    assert f"reports/semanal/{D}/relatorio.md" in out["anteriores"]
    assert f"reports/semanal/{D}/relatorio.html" in out["anteriores"]
    assert any("/retificacoes/" in path for path in transport[0]["delta"])
    assert all(path.read_bytes() == body for path, body in preserved.items())
    assert json.dumps(old_receipt, sort_keys=True) == old_literal
    assert log.events()[-1].event_type == EVENT and len(log.events()) == 3
    transport.clear()
    monkeypatch.setattr(executor, "_confirmar_trava", lambda *args: {"estado": "perdida"})
    assert executor.publicar(root, task, "CDP: DADOS SIMULADOS", rt=rt, env={},
                             execucao="DIARIA-NOVA", trava="TRAVA-PERDIDA")[0] == executor.TRAVA_AUSENTE
    assert transport == []


def test_editorial_gate_only_item_does_not_reopen_moc_close_or_original_report(case):
    from cdp.rotinas import ContextoGate, gate_diario

    rt, entry, _, _ = case
    agenda = {"fase": "operacao", "reinicio": {"pendente": False},
              "semanal": {"acao": "nada", "semana": D},
              "fechamentos_pendentes": [], "publicacoes_pendentes": [],
              "teses_pendentes": [], "relatorio_semanal": {"pendente": False},
              "cobertura": {"snapshot_pendente": False}, "retificacao_editorial": status(rt)}
    decision = gate_diario(agenda, ContextoGate(hoje=D))
    assert decision.executar and decision.itens == ["retificação editorial semanal pendente (sem repetir fechamento)"]
    publicar(rt, entry, expected_mind="codex")
    agenda["retificacao_editorial"] = status(rt)
    assert not gate_diario(agenda, ContextoGate(hoje=D)).executar
    assert agenda["fechamentos_pendentes"] == [] and not agenda["relatorio_semanal"]["pendente"]


@pytest.mark.parametrize("field", ["evento_original", "comentario_original_sha256", "factbook_original_sha256"])
def test_false_source_event_or_input_hash_never_creates_note(case, field):
    rt, entry, folder, log = case
    data = entry.model_dump(mode="json")
    data[field] = "a" * 64
    assert validar(rt, RetificacaoSemanal.model_validate(data), expected_mind="codex")
    assert not (folder / "retificacoes").exists() and len(log.events()) == 2


def test_native_report_renderer_preserves_target_as_authenticated_text(case):
    from cdp.workflow.reports import Document, Section, to_html, to_markdown

    rt, entry, folder, _ = case
    section = Section("Comentário DADOS SIMULADOS", ai=True)
    section.p(OLD, ai=True)
    doc = Document(title="DADOS SIMULADOS", subtitle="Relatório de teste", labels=[],
                   synthetic=True, data_notice="DADOS SIMULADOS", sections=[section])
    md, markup = to_markdown(doc), to_html(doc)
    assert OLD in md and html.escape(OLD) in markup
    # Layout nativo não executa nenhuma API de carteira ou cálculo financeiro.
    (folder / "relatorio.md").write_text(md)
    (folder / "relatorio.html").write_text(markup)
    receipt = entry.recibo_original.model_dump(mode="json")
    receipt.update(md_sha256=sha256_file(folder / "relatorio.md"), html_sha256=sha256_file(folder / "relatorio.html"))
    log = AuditLog(Path(rt.book_root) / "audit_log.jsonl")
    event = log.append("WEEKLY_CLOSE_REPORT", "CDP", receipt, week=D)
    data = entry.model_dump(mode="json")
    data.update(evento_original=event.event_hash, recibo_original=receipt)
    real_layout = RetificacaoSemanal.model_validate(data)
    assert validar(rt, real_layout, expected_mind="codex") == []
    assert publicar(rt, real_layout, expected_mind="codex")["id"]
    assert verificar(rt) == []


def test_cli_authorization_checks_identity_and_lock_after_matching_current_receipt(case, monkeypatch):
    from cdp import executor

    rt, _, _, _ = case
    args = SimpleNamespace(execucao="DIARIA-NOVA", trava="TRAVA-NOVA", raiz=Path(rt.book_root).parent)
    record = {"tarefa": "cdp-diario", "mente": "codex", "trava": "TRAVA-NOVA",
              "ensaio": False, "sem_trava": False}
    monkeypatch.setattr(executor, "ler_execucao", lambda *args: record)
    calls = []
    monkeypatch.setattr(executor, "verificar", lambda *args: (executor.OK, {"sou_o_executor": True}))
    monkeypatch.setattr(executor, "_confirmar_trava", lambda *args: calls.append(args[1]) or {"estado": "renovada"})
    _autorizar_cli(args, "codex", rt)
    assert calls == ["TRAVA-NOVA"]
    record["mente"] = None  # Fallback do harness documentado em AGENTS, sem alterar recibo antigo.
    _autorizar_cli(args, "codex", rt)
    record["mente"] = "gemini"
    with pytest.raises(ValueError, match="vinculadas"):
        _autorizar_cli(args, "codex", rt)
    record["mente"] = "codex"
    monkeypatch.setattr(executor, "verificar", lambda *args: (executor.OUTRO_EXECUTOR, {"sou_o_executor": False}))
    with pytest.raises(ValueError, match="executor autorizado"):
        _autorizar_cli(args, "codex", rt)
    monkeypatch.setattr(executor, "verificar", lambda *args: (executor.OK, {"sou_o_executor": True}))
    monkeypatch.setattr(executor, "_confirmar_trava", lambda *args: {"estado": "perdida"})
    with pytest.raises(ValueError, match="não confirmada"):
        _autorizar_cli(args, "codex", rt)
