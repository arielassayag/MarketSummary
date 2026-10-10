"""DADOS SIMULADOS: novos oráculos de lado renderizado, necessidade e repetição."""

import html
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from cdp.audit import AuditLog
from cdp.contracts import Fact, FactBook
from cdp.hashing import sha256_file
from cdp.research.comentario_semanal import (
    ComentarioSemanal,
    MudancaComentada,
    render_comentario,
    verificar_comentario,
)
from cdp.workflow.retificacao_semanal import (
    RetificacaoSemanal,
    listar,
    publicar,
    status,
    validar,
    verificar,
)

DAY = date(2026, 10, 9)
IID = "BR_ORACULO"
OTHER = "BR_OUTRO_ORACULO"


def factbook(weight=-0.2):
    fid = f"mud.{IID}.depois"
    formatted = {-0.2: "-20,00%", 0.2: "+20,00%", 0.0: "0,00%"}[weight]
    return FactBook(as_of=DAY, snapshot_id="DADOS SIMULADOS — oráculo não autor",
        is_synthetic=True, facts={fid: Fact(fact_id=fid, issuer_id=IID,
            name="Peso fixo DADOS SIMULADOS", value=weight, unit="pct", formatted=formatted,
            formula="Constante de teste; nenhum NAV/retorno/MOC calculado")})


def commentary(text, side=None):
    return ComentarioSemanal(mind="codex", resumo="DADOS SIMULADOS: oráculo editorial.",
        desempenho_semana=["Fatos publicados da semana."], atribuicao=["Fatos publicados de atribuição."],
        risco_nova_carteira=["Fatos publicados de risco."], execucao=["Fatos publicados de execução."],
        mudancas_carteira=[MudancaComentada(emissor=IID, tipo="entrada", racional=text, lado_depois=side)])


def record(tmp_path, name, payload):
    (tmp_path / (name + ".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def original_case(tmp_path, text, weight=-0.2, actor="CDP"):
    fb = factbook(weight)
    comment = commentary(text).model_dump(mode="json")
    comment["mudancas_carteira"][0].pop("lado_depois")
    book = tmp_path / "book"
    book.mkdir()
    folder = tmp_path / "reports/semanal" / DAY.isoformat()
    folder.mkdir(parents=True)
    (folder / "factbook.json").write_text(fb.model_dump_json())
    (folder / "comentario.json").write_text(json.dumps(comment, ensure_ascii=False))
    md = "# DADOS SIMULADOS — relatório original\n\n" + text + "\n"
    (folder / "relatorio.md").write_text(md)
    (folder / "relatorio.html").write_text("<!doctype html><pre>" + html.escape(md) + "</pre>")
    (book / "NAV.txt").write_text("DADOS SIMULADOS: NAV fixo literal, sem cálculo.\n")
    receipt = dict(md=str(folder / "relatorio.md"), html=str(folder / "relatorio.html"),
        md_sha256=sha256_file(folder / "relatorio.md"), html_sha256=sha256_file(folder / "relatorio.html"),
        registro="d" * 64, factbook=fb.factbook_hash(), comentario_da_mente=True,
        apontamentos=[], tipo="montagem")
    audit = AuditLog(book / "audit_log.jsonl")
    audit.append("DADOS_SIMULADOS_PREEXISTENTES", "CDP", {"aviso": "DADOS SIMULADOS"})
    event = audit.append("WEEKLY_CLOSE_REPORT", actor, receipt, week=DAY)
    entry = RetificacaoSemanal(schema_version="cdp.weekly.editorial/v1", data=DAY, mind="codex",
        evento_original=event.event_hash, recibo_original=receipt,
        comentario_original_sha256=sha256_file(folder / "comentario.json"),
        factbook_original_sha256=sha256_file(folder / "factbook.json"),
        correcoes=[{"emissor": IID, "texto_original": text}])
    rt = SimpleNamespace(book_root=book, reports_root=tmp_path / "reports",
        cfg=SimpleNamespace(fund=SimpleNamespace(inception_date=DAY)))
    record(tmp_path, "entrada_minima", {"entrada": entry.model_dump(mode="json"),
        "factbook": fb.model_dump(mode="json"), "comentario": comment, "original_md": md,
        "aviso": "DADOS SIMULADOS"})
    return rt, entry, folder, audit


@pytest.mark.parametrize("declared", [None, "vendida"])
def test_canonical_side_from_placeholder_must_be_checked_after_render(tmp_path, declared):
    fb = factbook()
    fid = f"mud.{OTHER}.lado_depois"
    source = Fact(fact_id=fid, issuer_id=OTHER, name="Lado de outro emissor simulado",
                  value=None, unit="count", formatted="comprada", formula="DADOS SIMULADOS")
    fb = fb.model_copy(update={"facts": {**fb.facts, fid: source}})
    text = "Empresa simulada entrou {{fact:" + fid + "}}; contexto publicado."
    comment = commentary(text, declared)
    issues = verificar_comentario(comment, fb, [{"emissor": IID, "tipo": "entrada"}])
    rendered = render_comentario(comment, fb)["mudancas_carteira"][IID]
    record(tmp_path, "saida_literal", dict(factbook=fb.model_dump(mode="json"),
        comentario=comment.model_dump(mode="json"), problemas=issues, renderizado=rendered,
        esperado="Recusar indicação canônica renderizada comprada contra peso negativo do emissor alvo"))
    assert "entrou comprada" in rendered
    assert issues, "Oráculo: placeholder produziu afirmação canônica contrária e passou sem problemas"


def test_matching_own_side_placeholder_is_valid_control(tmp_path):
    fb = factbook()
    fid = f"mud.{IID}.lado_depois"
    source = Fact(fact_id=fid, issuer_id=IID, name="Lado próprio simulado",
                  value=None, unit="count", formatted="vendida", formula="DADOS SIMULADOS")
    fb = fb.model_copy(update={"facts": {**fb.facts, fid: source}})
    text = "Empresa simulada entrou {{fact:" + fid + "}}; contexto publicado."
    comment = commentary(text, "vendida")
    issues = verificar_comentario(comment, fb, [{"emissor": IID, "tipo": "entrada"}])
    rendered = render_comentario(comment, fb)["mudancas_carteira"][IID]
    record(tmp_path, "saida_literal", dict(problemas=issues, renderizado=rendered))
    assert issues == [] and "entrou vendida" in rendered


@pytest.mark.parametrize("text", ["Empresa simulada entrou vendida; fatos publicados.",
                                  "Empresa simulada apresentou seu racional apoiado nos fatos."])
def test_editorial_correction_requires_actual_directional_divergence(tmp_path, text):
    rt, entry, folder, audit = original_case(tmp_path, text)
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    pending_before = status(rt)
    issues = validar(rt, entry, expected_mind="codex")
    published = None
    if not issues:
        published = publicar(rt, entry, expected_mind="codex")
    record(tmp_path, "saida_literal", dict(pendente_antes=pending_before, problemas=issues,
        publicado=published, verificacao=verificar(rt), n_eventos=len(audit.events()),
        originais_literais=all((folder / name).read_bytes() == body for name, body in before.items()),
        esperado="Recusar errata espúria: texto correto ou sem divergência direcional finita"))
    assert issues, "Oráculo: texto sem pendência editorial admitiu errata publicada"


def test_same_target_cannot_be_rectified_again_by_other_mind(tmp_path):
    rt, entry, _, audit = original_case(tmp_path, "Empresa simulada entrou comprada; fatos publicados.")
    first = publicar(rt, entry, expected_mind="codex")
    data = entry.model_dump(mode="json")
    data["mind"] = "gemini"
    second_entry = RetificacaoSemanal.model_validate(data)
    issues = validar(rt, second_entry, expected_mind="gemini")
    second = None
    if not issues:
        second = publicar(rt, second_entry, expected_mind="gemini")
    record(tmp_path, "saida_literal", dict(primeira=first, segunda=second, problemas=issues,
        notas=listar(rt, DAY), verificacao=verificar(rt), n_eventos=len(audit.events()),
        esperado="Recusar repetição do mesmo alvo/evento ainda que o hash mude pela mente"))
    assert issues, "Oráculo: alvo já corrigido aceitou segunda errata ao trocar a mente"


@pytest.mark.parametrize(("weight", "text", "side"), [(0.0, "Empresa simulada entrou comprada.", "zerada"),
    (0.2, "Empresa simulada entrou vendida.", "comprada")])
def test_real_divergence_zero_and_long_append_only_controls(tmp_path, weight, text, side):
    rt, entry, folder, audit = original_case(tmp_path, text, weight)
    nav = (Path(rt.book_root) / "NAV.txt").read_bytes()
    prefix = audit.path.read_bytes()
    original = {path.name: path.read_bytes() for path in folder.iterdir()}
    issues = validar(rt, entry, expected_mind="codex")
    result = publicar(rt, entry, expected_mind="codex")
    artifact = json.loads((folder / "retificacoes" / result["id"] / "retificacao.json").read_text())
    record(tmp_path, "saida_literal", dict(problemas=issues, publicado=result, artefato=artifact,
        verificacao=verificar(rt), status=status(rt)))
    assert issues == [] and artifact["correcoes_calculadas"][0]["lado_depois"] == side
    assert verificar(rt) == [] and not status(rt)["pendente"]
    assert (Path(rt.book_root) / "NAV.txt").read_bytes() == nav and audit.path.read_bytes().startswith(prefix)
    assert all((folder / name).read_bytes() == body for name, body in original.items())


def test_complete_payload_with_wrong_original_actor_is_refused(tmp_path):
    rt, entry, folder, audit = original_case(tmp_path, "Empresa simulada entrou comprada.", actor="gemini")
    issues = validar(rt, entry, expected_mind="codex")
    record(tmp_path, "saida_literal", dict(problemas=issues, n_eventos=len(audit.events())))
    assert issues and not (folder / "retificacoes").exists() and len(audit.events()) == 2


@pytest.mark.parametrize("kind", ["unknown", "malformed", "unavailable", "nested", "empty", "nonfinite"])
def test_invalid_or_unobserved_token_refuses_and_keeps_fallback_safe(tmp_path, kind):
    from cdp.research.comentario_semanal import carregar_comentario, problemas_lado

    fb = factbook()
    fid = f"mud.{OTHER}.lado_depois"
    text = "Empresa simulada entrou {{fact:" + fid + "}}; fatos publicados."
    if kind == "malformed":
        text = "Empresa simulada entrou {{fact:incompleto}; fatos publicados."
    elif kind != "unknown":
        f = Fact(fact_id=fid, issuer_id=OTHER, name="DADOS SIMULADOS: token recebido",
                 value=float("nan") if kind == "nonfinite" else None, unit="count",
                 formatted={"unavailable":"n/d", "nested":"{{fact:outro}}", "empty":"", "nonfinite":"vendida"}[kind],
                 formula="Constante de teste")
        fb = fb.model_copy(update={"facts": {**fb.facts, fid: f}})
    comment = commentary(text)
    path = tmp_path / "comentario.json"
    path.write_text(comment.model_dump_json())
    issues = problemas_lado(comment.mudancas_carteira[0], fb)
    out, authored, fallback_issues = carregar_comentario(path, fb,
        [{"emissor": IID, "tipo": "entrada"}], montagem=True, mente_esperada="codex")
    record(tmp_path, "saida_literal", dict(problemas=issues, problemas_fallback=fallback_issues,
        da_mente=authored, modelo=out.model_dump(mode="json")))
    assert issues and not authored and fallback_issues
    assert all(item.racional != text for item in out.mudancas_carteira)


def test_unobserved_weight_cannot_certify_neutral_rationale():
    from cdp.research.comentario_semanal import problemas_lado

    fb = factbook()
    fid = f"mud.{IID}.depois"
    fb = fb.model_copy(update={"facts": {fid: fb.facts[fid].model_copy(
        update={"value": None, "formatted": "n/d"})}})
    assert problemas_lado(commentary("Racional conforme os fatos.").mudancas_carteira[0], fb)


def _authenticate_fixture(rt, entry, folder, audit, fb, comment, text):
    """Somente fixture DADOS SIMULADOS, antes de qualquer nota; sem cálculo financeiro."""
    (folder / "factbook.json").write_text(fb.model_dump_json())
    (folder / "comentario.json").write_text(comment.model_dump_json())
    md = "# DADOS SIMULADOS — relatório original\n\n" + text + "\n"
    (folder / "relatorio.md").write_text(md)
    (folder / "relatorio.html").write_text("<!doctype html><pre>" + html.escape(md) + "</pre>")
    receipt = entry.recibo_original.model_dump(mode="json")
    receipt.update(md_sha256=sha256_file(folder / "relatorio.md"),
        html_sha256=sha256_file(folder / "relatorio.html"), factbook=fb.factbook_hash())
    event = audit.append("WEEKLY_CLOSE_REPORT", "CDP", receipt, week=DAY)
    data = entry.model_dump(mode="json")
    data.update(evento_original=event.event_hash, recibo_original=receipt,
        comentario_original_sha256=sha256_file(folder / "comentario.json"),
        factbook_original_sha256=sha256_file(folder / "factbook.json"))
    return RetificacaoSemanal.model_validate(data)


def test_token_contradiction_pending_and_portal_share_rendered_validation(tmp_path):
    from cdp.research.guardrails import render_placeholders
    from cdp.rotinas import ContextoGate, gate_diario
    from cdp.workflow.painel import _daily_reports, _Issues

    text = "Empresa simulada entrou {{fact:" + f"mud.{OTHER}.lado_depois" + "}}; fatos publicados."
    rt, entry, folder, audit = original_case(tmp_path, text)
    fb = factbook()
    fid = f"mud.{OTHER}.lado_depois"
    other = Fact(fact_id=fid, issuer_id=OTHER, name="DADOS SIMULADOS", value=None,
        unit="count", formatted="comprada", formula="Texto constante de outro emissor")
    fb = fb.model_copy(update={"facts": {**fb.facts, fid: other}})
    comment = commentary(text, "vendida")
    entry = _authenticate_fixture(rt, entry, folder, audit, fb, comment, render_placeholders(text, fb))
    pending = status(rt)
    assert pending["pendente"] and pending["relatorios"][0]["pendentes"] == [IID]
    agenda = {"fase":"operacao", "reinicio":{"pendente":False}, "semanal":{"acao":"nada","semana":DAY},
        "fechamentos_pendentes":[], "publicacoes_pendentes":[], "teses_pendentes":[],
        "relatorio_semanal":{"pendente":False}, "cobertura":{"snapshot_pendente":False},
        "retificacao_editorial":pending}
    assert gate_diario(agenda, ContextoGate(hoje=DAY)).executar
    assert validar(rt, entry, expected_mind="codex") == []
    result = publicar(rt, entry, expected_mind="codex")
    assert not status(rt)["pendente"] and verificar(rt) == []
    _, index = _daily_reports(rt, rt.cfg, [], _Issues(), 10)
    report = next(item for item in index if item["kind"] == "semanal")
    assert report["retificacoes"][0]["id"] == result["id"]


def test_authenticated_duplicate_history_detected_without_writer_or_recursion(tmp_path, monkeypatch):
    from cdp.hashing import sha256_obj
    from cdp.workflow import retificacao_semanal as module

    rt, entry, folder, audit = original_case(tmp_path, "Empresa simulada entrou comprada; fatos publicados.")
    first = publicar(rt, entry, expected_mind="codex")
    first_folder = folder / "retificacoes" / first["id"]
    artifact = json.loads((first_folder / "retificacao.json").read_bytes())
    artifact["entrada"]["mind"] = "gemini"
    artifact["audit_head_anterior"] = audit.events()[-1].event_hash
    second_id = sha256_obj(artifact["entrada"])
    second_folder = folder / "retificacoes" / second_id
    second_folder.mkdir()
    (second_folder / "retificacao.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2)+'\n')
    for name in ("retificacao.md", "retificacao.html"):
        (second_folder / name).write_bytes((first_folder / name).read_bytes())
    payload = {"data":str(DAY), "id":second_id, "arquivos":{
        name:sha256_file(second_folder/name) for name in ("retificacao.json","retificacao.md","retificacao.html")}}
    audit.append(module.EVENT, "gemini", payload, week=DAY)
    before = {path:path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    monkeypatch.setattr(module, "publicar", lambda *a, **kw: pytest.fail("Verifier chamou writer"))
    issues = verificar(rt)
    assert issues and "mais de uma vez" in issues[0]
    assert listar(rt, DAY) == [] and status(rt)["pendente"]
    assert all(path.read_bytes() == body for path, body in before.items())


def test_distinct_issuers_same_original_event_can_be_corrected_once_each(tmp_path):
    rt, entry, folder, audit = original_case(tmp_path, "Empresa simulada entrou comprada; fatos publicados.")
    fb = factbook()
    fid = f"mud.{OTHER}.depois"
    other = Fact(fact_id=fid, issuer_id=OTHER, name="DADOS SIMULADOS: outro peso",
        value=0.2, unit="pct", formatted="+20,00%", formula="Constante de teste")
    fb = fb.model_copy(update={"facts": {**fb.facts, fid:other}})
    comment = commentary(entry.correcoes[0].texto_original)
    other_text = "Outra empresa simulada entrou vendida; fatos publicados."
    comment = comment.model_copy(update={"mudancas_carteira": [*comment.mudancas_carteira,
        MudancaComentada(emissor=OTHER, tipo="entrada", racional=other_text)]})
    entry = _authenticate_fixture(rt, entry, folder, audit, fb, comment,
        entry.correcoes[0].texto_original + "\n" + other_text)
    original = {p:p.read_bytes() for p in folder.iterdir()}
    prefix = audit.path.read_bytes()
    first = publicar(rt, entry, expected_mind="codex")
    data = entry.model_dump(mode="json")
    data.update(mind="gemini", correcoes=[{"emissor":OTHER,"texto_original":other_text}])
    second = RetificacaoSemanal.model_validate(data)
    assert validar(rt, second, expected_mind="gemini") == []
    result = publicar(rt, second, expected_mind="gemini")
    assert first["id"] != result["id"] and len(listar(rt, DAY)) == 2
    assert verificar(rt) == [] and not status(rt)["pendente"]
    assert all(p.read_bytes() == body for p,body in original.items())
    assert audit.path.read_bytes().startswith(prefix)
    with pytest.raises(FileExistsError):
        publicar(rt, second, expected_mind="gemini")
