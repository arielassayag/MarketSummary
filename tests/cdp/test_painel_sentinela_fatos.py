"""Regressão da sentinela pública: fatos renderizados sem alterar a pesquisa original."""

from datetime import UTC, date, datetime

import pytest

from cdp.contracts import ResearchNote, ResearchPack, SqueezeAssessment
from cdp.workflow.painel import _research_section
from cdp.workflow.painel_publicacao import compactar, expandir


def _pack(verdict="ok", rationale="DADOS SIMULADOS: {{fact:BR_TESTE.squeeze_score}}"):
    note = ResearchNote(
        note_id="sentinela-simulada", issuer_id="BR_TESTE", week=date(2026, 10, 16),
        role="short_risk", provider="demo", prompt_version="teste", stance=0,
        confidence=0.5, thesis="DADOS SIMULADOS", input_hash="a" * 64,
        created_at=datetime(2026, 10, 16, 14, tzinfo=UTC), is_synthetic=True,
        squeeze=(SqueezeAssessment(verdict=verdict, rationale=rationale)
                 if verdict is not None else None),
    )
    return ResearchPack(
        week=note.week, snapshot_id="DADOS SIMULADOS", provider="demo", mind="codex",
        notes=[note], is_synthetic=True,
    )


@pytest.mark.parametrize("verdict", ["ok", "caution", "veto"])
def test_sentinela_resolve_fatos_e_preserva_hash_e_juizo(verdict):
    pack = _pack(verdict, "DADOS SIMULADOS: squeeze {{fact:BR_TESTE.squeeze_score}}, "
                 "aluguel {{fact:BR_TESTE.borrow_fee}} e dias {{fact:BR_TESTE.days_to_cover}}.")
    raw = pack.model_dump_json()
    research_hash = pack.research_hash()
    facts = {"BR_TESTE.squeeze_score": "0,21", "BR_TESTE.borrow_fee": "3,00%",
             "BR_TESTE.days_to_cover": "2,5"}
    rendered = _research_section(pack, facts, full=True)
    # A publicação compacta e a página expande esse mesmo corpo, sem resolver fatos em JS.
    public = expandir(compactar(rendered))
    assert public["notes"][0]["squeeze"] == {
        "verdict": verdict,
        "rationale": "DADOS SIMULADOS: squeeze 0,21, aluguel 3,00% e dias 2,5.",
    }
    assert public["counts"]["squeeze_caution"] == (verdict == "caution")
    assert public["counts"]["squeeze_veto"] == (verdict == "veto")
    assert rendered["research_hash"] == research_hash == pack.research_hash()
    assert pack.model_dump_json() == raw
    assert facts["BR_TESTE.squeeze_score"] == "0,21"


def test_sentinela_fato_ausente_e_explicito_sem_inventar_zero():
    pack = _pack()
    rendered = _research_section(pack, {}, full=True)
    assert rendered["notes"][0]["squeeze"]["rationale"] == (
        "DADOS SIMULADOS: [fato BR_TESTE.squeeze_score indisponível]"
    )


def test_nota_sem_sentinela_continua_sem_avaliacao():
    pack = _pack(None)
    rendered = _research_section(pack, {}, full=True)
    assert rendered["notes"][0]["squeeze"] is None


@pytest.mark.parametrize("full,notes_detail", [(False, True), (True, False)])
def test_retrato_sem_detalhes_nao_introduz_textos_de_sentinela(full, notes_detail):
    rendered = _research_section(_pack(), {}, full=full, notes_detail=notes_detail)
    assert rendered.get("notes", []) == []
    assert "{{fact:" not in str(rendered)
