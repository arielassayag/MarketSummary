"""Guia de estilo (docs/cdp/ESTILO.md): fonte única no código, presente em todo prompt da mente e
respeitado pelos textos de código que chegam ao investidor.

- ``docs/cdp/ESTILO.md`` reproduz ``prompts.ESTILO_REGRAS`` e a versão.
- Regras da tese, do PM, do comentário diário, da nota por emissor, dos prompts de API e do
  pacote de ``cdp mente pacote`` carregam o guia inteiro.
- Os modelos de texto do código (nota automática, comentário automático, avisos e rótulos)
  passam no verificador de estilo; o verificador não acusa vocabulário financeiro legítimo.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from cdp.contracts import Fact, FactBook
from cdp.research import commentary, notas, pm_agent, prompts
from cdp.research.guardrails import find_markup, style_issues, style_problems
from cdp.research.prompts import ESTILO_REGRAS, ESTILO_VERSAO, estilo_bloco
from cdp.workflow import tese

ROOT = Path(__file__).resolve().parents[2]
ESTILO_MD = ROOT / "docs" / "cdp" / "ESTILO.md"


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_estilo_md_mirrors_the_code():
    doc = _flat(ESTILO_MD.read_text(encoding="utf-8"))
    assert ESTILO_VERSAO in doc
    for i, rule in enumerate(ESTILO_REGRAS, start=1):
        assert f"{i}. {_flat(rule)}" in doc, rule[:60]
    assert "investidor qualificado" in doc and "pt-BR" not in ESTILO_REGRAS[0]


@pytest.mark.parametrize("name,rules", [
    ("THESIS_RULES", tese.THESIS_RULES), ("PM_RULES", pm_agent.PM_RULES),
    ("COMMENTARY_RULES", commentary.COMMENTARY_RULES), ("NOTE_RULES", notas.NOTE_RULES)])
def test_every_rule_set_carries_the_style_guide(name, rules):
    assert rules[-len(ESTILO_REGRAS):] == ESTILO_REGRAS, name


def test_every_prompt_carries_the_style_guide():
    texts = {f"system_prompt({r})": prompts.system_prompt(r) for r in prompts.ROLE_INSTRUCTIONS}
    texts["pm_system_prompt"] = pm_agent.pm_system_prompt()
    texts["commentary_system_prompt"] = commentary.commentary_system_prompt()
    for where, text in texts.items():
        flat = _flat(text)
        assert all(_flat(r) in flat for r in ESTILO_REGRAS), where
    assert _flat(estilo_bloco()) in _flat(prompts.system_prompt("analyst"))


def test_field_guide_lists_only_schema_fields():
    """A lista de campos da nota só traz campos do schema (um campo inventado é recusado)."""
    schema_fields = set(notas.NotaEmpresa.model_fields)
    for key, _ in notas.FIELD_GUIDE:
        for name in (k.strip() for k in key.split(",")):
            assert name in schema_fields, name
    fb, ctx = _world()
    fatos = notas.render_fatos_md(fb, ctx, nota_path="nota.json", schema_name="nota.schema.json",
                                  validate_cmd="v", publish_cmd="p")
    assert "Tom: guia de estilo do fundo" in fatos and "- `tom`" not in fatos
    extra = {**notas.example_nota(fb, ctx, "chatgpt"), "tom": "institucional"}
    nota, issues = notas.parse_nota(extra)
    assert nota is None and any("tom" in i for i in issues)


def _world():
    def f(fid, iid, unit="pct", value=0.1, formatted="10,00%"):
        return Fact(fact_id=fid, issuer_id=iid, name=fid, value=value, unit=unit,
                    formatted=formatted, formula="teste")

    facts = [f("val.AAA.preco_alvo", "AAA", "preco", 45.2, "R$ 45,20"),
             f("val.AAA.preco", "AAA", "preco", 40.0, "R$ 40,00"), f("val.AAA.upside", "AAA"),
             f("val.AAA.ke", "AAA"), f("val.AAA.alpha_rel", "AAA"),
             f("val.AAA.sens.ke_menos_100bp", "AAA"), f("val.AAA.sens.ke_mais_100bp", "AAA"),
             f("val.AAA.alvo_otimista", "AAA", "preco", 55.0, "R$ 55,00"),
             f("val.AAA.alvo_pessimista", "AAA", "preco", 30.0, "R$ 30,00"),
             f("val.AAA.diff_consenso", "AAA"), f("AAA.ret_12m_usd", "AAA")]
    fb = FactBook(as_of=date(2026, 10, 14), snapshot_id="t",
                  facts={x.fact_id: x for x in facts}, is_synthetic=False)
    ctx = notas.ContextoNota(issuer_id="AAA", nome="Alfa", pais="BR", pais_pt="Brasil",
                             setor="Energy", setor_pt="Energia", data=date(2026, 10, 15),
                             dados_ate=date(2026, 10, 14), is_synthetic=False,
                             nomes={"AAA": "Alfa"})
    return fb, ctx


def test_note_briefing_and_package_carry_the_style_guide():
    from cdp.workflow.pacote import Pacote, render_pacote

    fb, ctx = _world()
    fatos = notas.render_fatos_md(fb, ctx, nota_path="nota.json", schema_name="nota.schema.json",
                                  validate_cmd="v", publish_cmd="p")
    assert all(_flat(r) in _flat(fatos) for r in ESTILO_REGRAS)
    p = Pacote(etapa="nota", alvo="Alfa", mente="outro", papel="Papel.", regras=("Regra.",),
               fatos_titulo="Fatos", fatos="# Fatos\n", schema='{"type": "object"}',
               exemplo=None, saida_json=Path("nota.json"), validacao="uv run python -m cdp verify",
               publicacao=None, is_synthetic=False)
    md = render_pacote(p, gerado_em="2026-10-06T12:00:00+00:00")
    assert all(_flat(r) in _flat(md) for r in ESTILO_REGRAS) and ESTILO_VERSAO in md
    assert "\n### Fatos\n" in md  # títulos do arquivo de fatos rebaixados sob a seção do pacote


def _investor_texts_of_the_note() -> list[str]:
    fb, ctx = _world()
    nota = notas.template_nota(fb, ctx)
    rendered = notas.render_nota(nota, fb, ctx, autoria="codigo", published_at="x")
    md = notas.render_markdown(rendered)
    return [md, json.dumps(rendered, ensure_ascii=False)]


def test_code_templates_follow_the_style_guide():
    texts = _investor_texts_of_the_note()
    fb, _ = _world()
    texts.append(commentary.deterministic_commentary(None, fb))  # inteiro, com a autoria
    texts += [commentary._provenance(commentary.DEMO_MIND), commentary.TEMPLATE_PROVENANCE]
    texts += [tese.DISCLAIMER, tese.SYNTHETIC_DISCLAIMER, *tese.AUTHORSHIP_PT.values(),
              *(t for _, t in tese.SECTION_TITLES), notas.DISCLAIMER, notas.SYNTHETIC_DISCLAIMER,
              *notas.AUTHORSHIP_PT.values(), *notas.TIPO_PT.values(), *notas.FONTE_PT.values(),
              *notas.STANCE_PT.values()]
    for text in texts:
        assert style_issues(text) == [], (style_issues(text), text[:120])
        assert "emoji" not in find_markup(text)


@pytest.mark.parametrize("text,category", [
    ("Resultado incrível no trimestre.", "tom promocional"),
    ("Retorno garantido em doze meses.", "tom promocional"),
    ("A galera do mercado gostou.", "registro coloquial"),
    ("Vamos pra cima.", "registro coloquial"),
    ("Os dados vêm de um pipeline em Python.", "jargão de tecnologia"),
    ("Conferido pelo hash do commit.", "jargão de tecnologia"),
    ("Texto revisado pelo ChatGPT.", "jargão de tecnologia"),
    ("Autoria: mente claude-code [IA]", "jargão de tecnologia"),
    ("Texto da Claude-Code.", "jargão de tecnologia"),
    ("Revisado no Gemini-2.5.", "jargão de tecnologia"),
    ("Modelo GPT da OpenAI.", "jargão de tecnologia"),
    ("Assistente da Anthropic.", "jargão de tecnologia"),
    ("Alta forte hoje!", "exclamação"),
])
def test_style_checker_flags_casual_hype_and_it_vocabulary(text, category):
    issues = style_issues(text)
    assert any(i.startswith(category) for i in issues), issues
    assert style_problems("resumo", text)[0].startswith("resumo: fora do guia de estilo (")


@pytest.mark.parametrize("text", [
    "Resultado pró-forma do 3T26 com road show em Nova York.",
    "A massa salarial sustenta o consumo; Natura atua em beleza.",
    "Dividendo mínimo obrigatório e taxa livre de risco nos EUA.",
    "O preço embute {{fact:val.AAA.upside}} de potencial; convicção média.",
    "Risco idiossincrático domina a vol ex-ante da carteira.",
])
def test_style_checker_accepts_financial_vocabulary(text):
    assert style_issues(text) == []


def test_emojis_are_markup_everywhere():
    from cdp.research.guardrails import text_format_issues

    assert text_format_issues("t", "Alta de {{fact:x}} 🚀") == [
        "t: marcação/URL não permitida em texto livre ['emoji']"]
    for ok in ("Seta → e símbolos × ≤ −", "Trimestre 3T26 · país"):
        assert text_format_issues("t", ok) == []


def test_rule_texts_have_no_bare_day_month_dates():
    """As regras ensinam só datas aceitas pelo validador (nunca "25/10")."""
    bare = re.compile(r"(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])")
    for rule in ESTILO_REGRAS:
        assert not bare.search(rule), rule


def test_daily_authorship_line_has_no_file_name_or_jargon():
    """A linha de autoria do relatório diário rotula o texto da IA ([IA]) sem nome de arquivo,
    jargão nem o nome do app (o campo ``mind`` e a trilha registram quem escreveu)."""
    for mind in ("claude-code", "codex", "gemini", "chatgpt", "outro"):
        line = commentary._file_provenance(mind)
        assert "app de IA da gestão [IA]" in line and mind not in line
        assert "json" not in line.lower() and "factbook" not in line.lower()
        assert style_issues(line) == [], (mind, style_issues(line))
    from cdp.ui.data import _commentary_meta

    assert _commentary_meta(commentary._file_provenance("gemini"))[0] is True


def _vocab_rows() -> list[tuple[str, str]]:
    doc = ESTILO_MD.read_text(encoding="utf-8")
    table = doc[doc.index("| Prefira | Evite |"):doc.index("## O que o validador rejeita")]
    rows = []
    for line in table.splitlines()[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2:
            rows.append((cells[0], cells[1]))
    return rows


def test_preferred_vocabulary_passes_the_validators():
    """O que o guia manda preferir passa nos validadores (sem números livres nem jargão)."""
    from cdp.research.pm_agent import text_problems

    fb, _ = _world()
    rows = _vocab_rows()
    assert len(rows) >= 8
    for prefira, _evite in rows:
        assert text_problems("t", prefira, fb) == [], prefira


def _fb_simple() -> FactBook:
    return FactBook(as_of=date(2026, 10, 14), snapshot_id="t", facts={}, is_synthetic=False)


@pytest.mark.parametrize("text", [
    "Dia incrível para o fundo, galera!",
    "O pipeline em Python confirmou o hash do commit, tá?",
    "Carteira imperdível com retorno garantido.",
])
def test_style_guide_applies_to_every_investor_text_validator(text):
    """O guia vale para tese, comentário diário, decisão do PM e comentário semanal (todos usam
    ``pm_agent.text_problems``), não só para a nota por emissor."""
    from cdp.research.pm_agent import text_problems

    problems = text_problems("headline", text, _fb_simple())
    assert any("fora do guia de estilo" in p for p in problems), problems
    out = commentary.DailyCommentaryOutput.model_validate({
        "mind": "claude-code", "headline": text,
        "paragraphs": ["Texto sóbrio sobre o dia.", "Outro parágrafo sóbrio."],
        "risk_flags": []})
    assert any("fora do guia de estilo" in i for i in commentary.verify_commentary(out, _fb_simple()))
