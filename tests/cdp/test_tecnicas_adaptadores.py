"""Recursos e exportações portáveis; não executa rotina ou modelo financeiro."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from cdp import __version__
from cdp.tecnicas.adaptadores import (
    SKILLS,
    conferir_adaptadores,
    gerar_adaptadores,
    gravar_adaptadores,
)

ROOT = Path(__file__).resolve().parents[2]


def test_catalogo_fora_de_clone_e_sem_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bodies = gerar_adaptadores()
    assert len(SKILLS) == 9 and len(bodies) == 40
    for name in SKILLS:
        original = bodies[f".agents/skills/{name}/SKILL.md"]
        fm = yaml.safe_load(original.split("---\n", 2)[1])
        assert fm["name"] == name and 1 <= len(fm["description"]) <= 1024
        assert "allowed-tools" not in fm
        for base in (".claude/skills", "plugins/cdp-tecnicas/skills", "extensions/cdp-tecnicas/skills"):
            assert bodies[f"{base}/{name}/SKILL.md"] == original
    assert not list(tmp_path.iterdir())


def test_versao_unica_e_manifestos_sem_efeitos():
    bodies = gerar_adaptadores()
    for name in ("plugins/cdp-tecnicas/.claude-plugin/plugin.json",
                 "extensions/cdp-tecnicas/gemini-extension.json"):
        data = json.loads(bodies[name])
        assert data["version"] == __version__
        assert not set(data).intersection({"hooks", "mcpServers", "commands", "settings"})
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "version" in project["project"]["dynamic"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "cdp.__version__"}
    operational = json.loads((ROOT / "plugins/cdp/.claude-plugin/plugin.json").read_text())
    assert operational["version"] == __version__


def test_verificacao_nao_cria_destino_e_exportacao_idempotente(tmp_path):
    dest = tmp_path / "rascunho"
    assert len(conferir_adaptadores(dest)) == 40 and not dest.exists()
    assert len(gravar_adaptadores(dest)) == 40
    pins = {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in dest.rglob("*") if p.is_file()}
    assert conferir_adaptadores(dest) == [] and gravar_adaptadores(dest) == []
    assert pins == {str(p): (p.stat().st_mtime_ns, p.read_bytes()) for p in dest.rglob("*") if p.is_file()}
    altered = dest / ".agents/skills" / SKILLS[0] / "SKILL.md"
    altered.write_text("rascunho divergente")
    assert conferir_adaptadores(dest) == [str(altered.relative_to(dest))]


@pytest.mark.parametrize("name", ["book", "data", "reports", "artifacts"])
def test_destino_oficial_recusado_antes_de_efeito(tmp_path, name):
    dest = tmp_path / name / "rascunho"
    with pytest.raises(ValueError, match="Destino oficial recusado"):
        gravar_adaptadores(dest)
    assert not dest.exists()


def test_link_recusado_antes_da_primeira_escrita(tmp_path):
    external = tmp_path / "externo"
    external.mkdir()
    dest = tmp_path / "destino"
    dest.mkdir()
    (dest / "extensions").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="Link simbólico recusado"):
        gravar_adaptadores(dest)
    assert not (dest / ".agents").exists() and not list(external.iterdir())


def test_arquivo_nao_regular_recusado_antes_da_primeira_escrita(tmp_path):
    dest = tmp_path / "destino"
    collision = dest / ".claude/skills" / SKILLS[0] / "SKILL.md"
    collision.mkdir(parents=True)
    with pytest.raises(ValueError, match="Destino não regular"):
        gravar_adaptadores(dest)
    assert not (dest / ".agents").exists()


def test_adaptadores_versionados_sao_os_corpos_canonicos():
    assert conferir_adaptadores(ROOT) == []
