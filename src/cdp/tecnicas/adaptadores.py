"""Adaptadores de técnicas gerados de recursos empacotados; sem runtime operacional."""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from cdp import __version__

SKILLS = (
    "tecnica-cdp-auditoria-reproducao", "tecnica-cdp-avaliacao-latam",
    "tecnica-cdp-comunicacao-institucional", "tecnica-cdp-construcao-fatores",
    "tecnica-cdp-custo-capital", "tecnica-cdp-execucao-moc", "tecnica-cdp-nota-pesquisa",
    "tecnica-cdp-risco-long-short", "tecnica-cdp-tese-investimento",
)


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def gerar_adaptadores() -> dict[str, str]:
    """Retorna corpos relativos fechados, sem ler clone/CWD ou escrever arquivos."""
    source = resources.files("cdp").joinpath("recursos", "tecnicas", "skills")
    if {p.name for p in source.iterdir()} != set(SKILLS):
        raise ValueError("Catálogo de técnicas empacotado divergente")
    out = {}
    for name in SKILLS:
        skill = source.joinpath(name)
        if {p.name for p in skill.iterdir()} != {"SKILL.md"}:
            raise ValueError(f"Membros inesperados na técnica {name}")
        body = skill.joinpath("SKILL.md").read_text(encoding="utf-8")
        for dest in (".agents/skills", ".claude/skills", "plugins/cdp-tecnicas/skills",
                     "extensions/cdp-tecnicas/skills"):
            out[f"{dest}/{name}/SKILL.md"] = body
    out["plugins/cdp-tecnicas/.claude-plugin/plugin.json"] = _json({
        "name": "cdp-tecnicas", "displayName": "Técnicas do CDP", "version": __version__,
        "description": "Nove técnicas de pesquisa pública e cálculo determinístico, em leitura ou rascunho privado.",
        "author": {"name": "CDP — Cabra da Peste"}, "license": "CC-BY-4.0",
    })
    out["extensions/cdp-tecnicas/gemini-extension.json"] = _json({
        "name": "cdp-tecnicas", "version": __version__,
        "description": "Nove técnicas de leitura e rascunho privado do CDP.",
    })
    changelog = resources.files("cdp").joinpath("recursos", "tecnicas", "CHANGELOG.md").read_text(encoding="utf-8")
    for base in ("plugins/cdp-tecnicas", "extensions/cdp-tecnicas"):
        out[f"{base}/CHANGELOG.md"] = changelog
    return dict(sorted(out.items()))


def conferir_adaptadores(raiz: Path) -> list[str]:
    """Lista faltas/divergências sem criar diretórios ou modificar o destino."""
    root = Path(raiz)
    differences = []
    for relative, body in gerar_adaptadores().items():
        p = root / relative
        if p.is_symlink() or not p.is_file() or p.read_text(encoding="utf-8") != body:
            differences.append(relative)
    return differences


def gravar_adaptadores(raiz: Path) -> list[str]:
    """Exporta somente o catálogo declarado em destino explícito de desenvolvimento."""
    root = Path(raiz).absolute()
    protected = {"book", "data", "reports", "artifacts"}
    if protected.intersection(root.parts) or protected.intersection(root.resolve().parts):
        raise ValueError("Destino oficial recusado: use pasta de rascunho ou de desenvolvimento")
    bodies = gerar_adaptadores()
    # Valide todos os membros antes do primeiro efeito; não siga symlinks do destino.
    for relative in bodies:
        p = root / relative
        for ancestor in (p, *p.parents):
            if ancestor.is_symlink():
                raise ValueError(f"Link simbólico recusado no destino: {ancestor}")
            if ancestor == root.parent:
                break
        if p.exists() and not p.is_file():
            raise ValueError(f"Destino não regular: {p}")
    written = []
    for relative, body in bodies.items():
        p = root / relative
        if p.is_file() and p.read_text(encoding="utf-8") == body:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
        written.append(relative)
    return written
