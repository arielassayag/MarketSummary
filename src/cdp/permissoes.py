"""Catálogo de folhas operacionais e geração de permissões de desenvolvimento.

Regras do host não substituem gates, executor ou trava e não provam isolamento do SO.
Este módulo não executa a CLI nem chama qualquer handler operacional.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from cdp import __version__

if TYPE_CHECKING:
    from cdp.rotinas import Rotinas

FORMAS = ("uv run python -m cdp ", "uv run cdp ")
FOLHAS = MappingProxyType({
    "status": ("estado", "status", "verify", "nota agenda", "agenda", "rotinas proximas"),
    "semanal": ("agenda", "status", "verify", "avaliacao status", "cobertura run",
                "weekly prepare", "weekly preview", "weekly decide", "validate", "tese prepare",
                "validate-tese", "tese publish", "painel --sem-local"),
    "diario": ("agenda", "verify", "daily close", "validate-daily", "daily publish",
               "tese prepare", "validate-tese", "tese publish", "weekly close-report",
               "validate-weekly-report", "cobertura run", "cobertura revisao-mensal preparar",
               "cobertura revisao-mensal validar", "cobertura revisao-mensal publicar",
               "painel --sem-local"),
    "cobertura": ("agenda", "nota agenda", "nota prepare", "validate-nota", "nota publish", "verify"),
    "risco": ("agenda", "risk", "kill-switch on", "status", "verify"),
    "calibracao": ("agenda", "backtest", "verify"),
    "retomar": ("estado", "executor janela", "rotinas verificar",
                "skills sincronizar --claude --verificar"),
})
_ESCRITORAS = frozenset({"semanal", "diario", "cobertura", "risco", "calibracao"})
_EXCLUSIVAS = frozenset({"semanal", "diario", "cobertura"})
_FERRAMENTAS = MappingProxyType({
    "status": ("Read", "Grep", "Glob"),
    "retomar": ("Read", "Grep", "Glob"),
    "calibracao": ("Read", "Write", "Grep", "Glob"),
    "risco": ("Read", "Grep", "Glob", "WebSearch", "WebFetch"),
    **{f: ("Read", "Write", "Edit", "Grep", "Glob", "WebSearch", "WebFetch")
       for f in ("semanal", "diario", "cobertura")},
})
ASK_ADICIONAL = tuple(f"Bash({form}{suffix})" for form in FORMAS for suffix in (
    "reinicio*", "* --manual*", "rotinas gate *--agora*", "rotinas gate *--ensaio*"))
DENY_ADICIONAL = tuple(f"Bash({form}{suffix})" for form in FORMAS for suffix in (
    "* --force*", "* --forcar*"))


class ArgumentParserCDP(argparse.ArgumentParser):
    """Subparsers herdam este construtor nativamente; flags precisam ser completas."""

    def __init__(self, *args, **kwargs):
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)


def prefixos(rot: Rotinas, familia: str) -> tuple[str, ...]:
    """Folhas + IDs exatos da agenda, sem wildcard na tarefa ou em subcomandos."""
    if familia not in FOLHAS:
        raise ValueError(f"Família sem catálogo de permissões: {familia}")
    families = rot.familias()
    if set(families) != {f"cdp-{f}" for f in FOLHAS if f != "retomar"}:
        raise ValueError("Famílias de rotinas divergentes do catálogo de permissões")
    tasks = families.get(f"cdp-{familia}", ())
    out = set(FOLHAS[familia])
    for task in tasks:
        if (task.grava != (familia in _ESCRITORAS)
                or task.exclusiva != (familia in _EXCLUSIVAS)
                or not task.id.startswith(f"cdp-{familia}")
                or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in task.id)):
            raise ValueError(f"Contrato de permissões divergente para {task.id}")
        out.add(f"rotinas gate --tarefa {task.id}")
        if task.grava:
            out.add(f"publicar --tarefa {task.id}")
    if familia in _ESCRITORAS:
        out.add("sincronizar --executar")
    if familia in _EXCLUSIVAS:
        out.update(("trava renovar --id", "trava liberar --id"))
    return tuple(sorted(out))


def regras(rot: Rotinas, familia: str | None = None, *,
           formas: tuple[str, ...] = FORMAS) -> tuple[str, ...]:
    """União global ou catálogo de uma família nas formas nativas declaradas."""
    if not formas or any(f not in FORMAS for f in formas):
        raise ValueError("Forma da CLI fora do catálogo")
    leaves = {p for f in ((familia,) if familia is not None else FOLHAS)
              for p in prefixos(rot, f)}
    return tuple(sorted({f"Bash({form}{leaf}{tail})" for form in formas
                         for leaf in leaves for tail in ("", " *")}))


def ferramentas_skill(rot: Rotinas, familia: str) -> tuple[str, ...]:
    """Ferramentas das skills neutras; o catálogo CDP é compartilhado com o plugin."""
    return (*_FERRAMENTAS[familia], "Bash(uv sync *)", "Bash(git status *)",
            "Bash(git log *)", *regras(rot, familia))


def _cdp(rule: str) -> bool:
    return any(rule.startswith(f"Bash({form}") for form in FORMAS)


def gerar_settings(rot: Rotinas, atual: dict) -> dict:
    """Conserva política anterior e regras extras; só substitui ALLOW CDP derivado."""
    out = copy.deepcopy(atual)
    perm = out["permissions"]
    for key, minimum in (("ask", _ASK_MINIMOS), ("deny", _DENY_MINIMOS)):
        values = perm[key]
        if not isinstance(values, list) or not all(type(v) is str for v in values):
            raise ValueError(f"Lista {key} inválida")
        missing = set(minimum) - set(values)
        if missing:
            raise ValueError(f"Política {key} anterior incompleta: {sorted(missing)}")
    grants = regras(rot)
    previous = perm["allow"]
    if not isinstance(previous, list) or not all(type(v) is str for v in previous):
        raise ValueError("Lista allow inválida")
    broad = {f"Bash({form}*)" for form in FORMAS}
    if any(_cdp(v) and v not in broad and v not in grants for v in previous):
        raise ValueError("Grant CDP fora do bloco derivado")
    # Inserção na posição do primeiro grant CDP: ordem dos demais permanece literal.
    insert = next((i for i, v in enumerate(previous) if _cdp(v)), len(previous))
    kept = [v for v in previous if not _cdp(v)]
    perm["allow"] = kept[:insert] + list(grants) + kept[insert:]
    for key, additions in (("ask", ASK_ADICIONAL), ("deny", DENY_ADICIONAL)):
        perm[key].extend(v for v in additions if v not in perm[key])
    return out


def gerar_plugin_skill(rot: Rotinas, familia: str, atual: str) -> str:
    """Troca somente linhas CDP de allowed-tools; todo o resto fica literal."""
    header, sep, body = atual.partition("\n---\n")
    if not header.startswith("---\n") or not sep:
        raise ValueError("Frontmatter de plugin ausente")
    lines = header.splitlines(keepends=True)
    start = lines.index("allowed-tools:\n") + 1
    end = start
    while end < len(lines) and lines[end].startswith("  - "):
        end += 1
    block = lines[start:end]
    grants = regras(rot, familia, formas=(FORMAS[0],))
    broad = f"Bash({FORMAS[0]}*)"
    old = [i for i, line in enumerate(block) if _cdp(line[4:].strip())]
    if not old or any(block[i][4:].strip() not in {broad, *grants} for i in old):
        raise ValueError("Bloco CDP de plugin fora do catálogo")
    insert = old[0]
    kept = [line for i, line in enumerate(block) if i not in old]
    new = kept[:insert] + [f"  - {g}\n" for g in grants] + kept[insert:]
    # A última linha do header original não tem LF antes do separador.
    if block and not block[-1].endswith("\n"):
        new[-1] = new[-1].removesuffix("\n")
    return "".join(lines[:start] + new + lines[end:]) + sep + body


def _destino(root: Path, relative: str) -> Path:
    path = root / relative
    for p in (path, *path.parents):
        if p.is_symlink():
            raise ValueError(f"Link simbólico recusado: {p}")
        if p == root.parent:
            break
    if not path.is_file():
        raise ValueError(f"Membro de desenvolvimento ausente/não regular: {relative}")
    return path


def sincronizar_permissoes(rot: Rotinas, raiz: Path, *,
                          verificar_apenas: bool = False) -> dict[str, list[str] | bool]:
    """Geração explícita de oito destinos fechados, após todas as precondições."""
    root = Path(raiz).absolute()
    if {"book", "data", "reports", "artifacts"}.intersection((*root.parts, *root.resolve().parts)):
        raise ValueError("Destino oficial recusado: use checkout de desenvolvimento")
    settings = ".claude/settings.json"
    manifest = "plugins/cdp/.claude-plugin/plugin.json"
    skills = {f"plugins/cdp/skills/{f}/SKILL.md": f for f in FOLHAS if f != "retomar"}
    paths = {r: _destino(root, r) for r in (settings, manifest, *skills)}
    current = {r: p.read_text(encoding="utf-8") for r, p in paths.items()}
    out = {settings: json.dumps(gerar_settings(rot, json.loads(current[settings])),
                               ensure_ascii=False, indent=2) + "\n"}
    plugin = json.loads(current[manifest])
    if plugin.get("name") != "cdp":
        raise ValueError("Manifesto operacional divergente")
    plugin["version"] = __version__
    out[manifest] = json.dumps(plugin, ensure_ascii=False, indent=2) + "\n"
    for relative, family in skills.items():
        out[relative] = gerar_plugin_skill(rot, family, current[relative])
    differences = [r for r, body in out.items() if body != current[r]]
    if not verificar_apenas:
        for relative in differences:
            paths[relative].write_text(out[relative], encoding="utf-8", newline="\n")
    return {"ok": not differences if verificar_apenas else True,
            "diferentes": differences, "gravados": [] if verificar_apenas else differences,
            "arquivos": list(out)}


# Política anterior mínima: removê-la não é uma operação de geração.
_ASK_MINIMOS = (
    'Edit(/configs/**)',
    'Edit(/data/**)',
    'Bash(git reset --hard*)',
    'Bash(git rebase *)',
    'Bash(git clean *)',
    'Bash(git restore *)',
    'Bash(git checkout -- *)',
    'Bash(uv run python -m cdp executor transferir*)',
    'Bash(uv run python -m cdp executor registrar*)',
    'Bash(uv run python -m cdp trava adquirir*)',
    'Bash(git add *)',
    'Bash(git commit *)',
    'Bash(git push)',
    'Bash(git push *)',
    'Bash(git pull)',
    'Bash(git pull *)',
    'Bash(git merge *)',
    'Bash(uv run cdp executor transferir*)',
    'Bash(uv run cdp executor registrar*)',
    'Bash(uv run cdp trava adquirir*)',
    'Bash(uv run python -m cdp * --sem-trava*)',
    'Bash(uv run cdp * --sem-trava*)',
)

_DENY_MINIMOS = (
    'Bash(git push --force*)',
    'Bash(git push *--force*)',
    'Bash(git push -f*)',
    'Bash(git push * -f)',
    'Bash(git push * -f *)',
    'Bash(git push * +*)',
    'Bash(rm -rf *)',
    'Bash(rm -r *)',
    'Bash(rm -fr *)',
    'Bash(rm book/*)',
    'Bash(rm * book/*)',
    'Bash(rm data/*)',
    'Bash(rm * data/*)',
    'Bash(uv run python -m cdp kill-switch off*)',
    'Bash(uv run cdp kill-switch off*)',
    'Edit(/book/KILL_SWITCH)',
    'Edit(/book/audit_log.jsonl)',
    'Edit(/book/avaliacao_manifest.json)',
    'Edit(/book/*/avaliacao/**)',
    'Edit(/book/track_record/**)',
    'Edit(/book/track_record_shadow/**)',
    'Edit(/book/*/briefing/**)',
    'Edit(/book/*/booked.json)',
    'Edit(/book/*/decision_v*.json)',
    'Edit(/book/*/proposal_v*.json)',
    'Edit(/book/*/research_pack*.json)',
    'Edit(/book/*/shadow_quant.json)',
    'Edit(/book/*/config_decisao.json)',
    'Edit(/book/*/tese/factbook.json)',
    'Edit(/book/*/tese/fatos.md)',
    'Edit(/book/*/tese/analise.json)',
    'Edit(/book/*/tese/tese.schema.json)',
    'Edit(/book/*/tese/tese_publicada.json)',
    'Edit(/book/*/tese/tese.md)',
    'Edit(/book/cobertura/livro.jsonl)',
    'Edit(/book/cobertura/*/manifest.json)',
    'Edit(/book/cobertura/*/selo.json)',
    'Edit(/book/cobertura/*/modelos.csv)',
    'Edit(/book/cobertura/*/modelos/**)',
    'Edit(/book/cobertura/*/etfs.csv)',
    'Edit(/book/cobertura/*/etfs/**)',
    'Edit(/book/cobertura/*/insumos/**)',
    'Edit(/book/cobertura/*/configuracao/**)',
    'Edit(/book/cobertura/*/contexto.json)',
    'Edit(/book/cobertura/*/placar.json)',
    'Edit(/book/cobertura/*/eventos.jsonl)',
    'Edit(/book/cobertura/publico/**)',
    'Edit(/book/cobertura/revisoes/*/fatos.md)',
    'Edit(/book/cobertura/revisoes/*/factbook.json)',
    'Edit(/book/cobertura/revisoes/*/pacote.json)',
    'Edit(/book/cobertura/revisoes/*/revisao.schema.json)',
    'Edit(/book/cobertura/revisoes/*/revisao_publicada.json)',
    'Edit(/book/cobertura/revisoes/*/revisao.md)',
    'Edit(/book/cobertura/notas/*/*/fatos.md)',
    'Edit(/book/cobertura/notas/*/*/factbook.json)',
    'Edit(/book/cobertura/notas/*/*/contexto.json)',
    'Edit(/book/cobertura/notas/*/*/nota.schema.json)',
    'Edit(/book/cobertura/notas/*/*/nota_publicada.json)',
    'Edit(/book/cobertura/notas/*/*/nota.md)',
    'Edit(/data/market/**)',
    'Edit(/data/publico/**)',
    'Edit(/reports/daily/*/facts.md)',
    'Edit(/reports/daily/*/factbook.json)',
    'Edit(/reports/daily/*/comentario.schema.json)',
    'Edit(/reports/daily/*/relatorio.*)',
    'Edit(/reports/semanal/*/fatos.md)',
    'Edit(/reports/semanal/*/factbook.json)',
    'Edit(/reports/semanal/*/comentario.schema.json)',
    'Edit(/reports/semanal/*/relatorio.*)',
    'Edit(/reports/weekly/**)',
    'Edit(/reports/risk/**)',
    'Edit(/artifacts/painel/*.html)',
    'Edit(/artifacts/painel/data.json)',
    'Edit(/artifacts/painel/PAGINA_PUBLICADA.sha256)',
    'Edit(/artifacts/painel/*.css)',
    'Edit(/artifacts/painel/*.js)',
    'Bash(git push --no-verify*)',
    'Bash(git push * --no-verify*)',
    'Bash(git commit --no-verify*)',
    'Bash(git commit * --no-verify*)',
    'Edit(/configs/cdp/executor.yaml)',
    'Edit(/.cdp/**)',
)
