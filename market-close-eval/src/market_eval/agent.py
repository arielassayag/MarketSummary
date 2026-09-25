"""Montagem do pacote entregue ao modelo candidato e das mensagens.

O pacote contém SOMENTE: data, fatos (com unidades e fontes) e instruções do
prompt. Nunca contém: referência, importâncias, must_mention, conclusões
proibidas ou notas do avaliador. A ordenação é determinística por
(categoria, fact_id) — nunca por importância escondida.
"""

from __future__ import annotations

from pathlib import Path

from .schemas import Case, OutputParseError, parse_agent_output, sha256_text

PROMPT_FILES = {
    "common": "common_system.md",
    "v1": "candidate_v1.md",
    "v2": "candidate_v2.md",
    "judge_absolute": "judge_absolute.md",
    "judge_pairwise": "judge_pairwise.md",
}

MEASURE_LABELS_PT = {
    "level": "nível",
    "return_pct": "retorno",
    "change_pct": "variação",
    "change_bps": "variação em pontos-base",
    "contribution_bps": "contribuição em pontos-base",
    "absolute_value": "valor absoluto",
    "text_only": "informação",
}


def load_prompt(prompts_dir: Path, key: str) -> str:
    filename = PROMPT_FILES.get(key)
    if filename is None:
        raise KeyError(f"prompt desconhecido: {key}")
    path = prompts_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8")


def prompt_hash(prompts_dir: Path, key: str) -> str:
    return sha256_text(load_prompt(prompts_dir, key))


def format_fact_value(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    text = f"{value:+.2f}" if unit in ("pct", "bps") else f"{value:,.2f}"
    text = text.replace(",", "@").replace(".", ",").replace("@", ".")
    suffix = {"pct": "%", "bps": " bps", "points": " pts", "brl_per_usd": " R$/US$", "brl": " R$", "usd": " US$"}
    return text + suffix.get(unit, "")


def build_package(case: Case) -> str:
    lines = [
        f"PACOTE DE FECHAMENTO — {case.date}",
        "Use exclusivamente os fatos abaixo. Não use conhecimento externo.",
        "",
    ]
    for f in sorted(case.facts, key=lambda x: (x.category.value, x.fact_id)):
        if f.measure_kind.value == "text_only":
            value_part = ""
        else:
            value_part = (
                f" | {MEASURE_LABELS_PT[f.measure_kind.value]}: "
                f"{format_fact_value(f.value, f.unit.value)} "
                f"(measure_kind={f.measure_kind.value}; unit={f.unit.value})"
            )
        lines.append(
            f"[{f.fact_id}] {f.subject}{value_part} | Direção: {f.direction.value} | "
            f"Fonte: {f.source.name} (tier {f.source.source_tier}) | Observado em: {f.observed_at}"
        )
        lines.append(f"  {f.statement}")
    lines.append("")
    lines.append("Escreva o comentário seguindo as instruções do sistema. Responda apenas com o JSON.")
    return "\n".join(lines)


def compose_messages(case: Case, prompt_version: str, prompts_dir: Path) -> list[dict[str, str]]:
    if prompt_version not in ("v1", "v2"):
        raise ValueError(f"prompt_version inválida: {prompt_version}")
    system = load_prompt(prompts_dir, "common") + "\n\n---\n\n" + load_prompt(prompts_dir, prompt_version)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": build_package(case)},
    ]


__all__ = [
    "OutputParseError",
    "build_package",
    "compose_messages",
    "load_prompt",
    "parse_agent_output",
    "prompt_hash",
]
