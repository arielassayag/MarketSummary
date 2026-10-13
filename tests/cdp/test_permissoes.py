"""Política local e parser: controles offline, sem chamar handler/gate/financeiro."""
from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from cdp import __version__
from cdp import permissoes as pe
from cdp import rotinas as ro
from cdp.__main__ import build_parser

ROOT = Path(__file__).resolve().parents[2]
ROT = ro.carregar(ROOT / "configs/cdp/rotinas.yaml")


def _settings():
    return json.loads((ROOT / ".claude/settings.json").read_text())


def _legacy_settings():
    settings = _settings()
    perm = settings["permissions"]
    # Simula a entrada anterior ao gerador; todos os demais grants são preservados.
    perm["allow"] = [v for v in perm["allow"] if not pe._cdp(v)]
    perm["allow"][1:1] = [f"Bash({f}*)" for f in pe.FORMAS]
    perm["ask"] = [v for v in perm["ask"] if v not in pe.ASK_ADICIONAL]
    perm["deny"] = [v for v in perm["deny"] if v not in pe.DENY_ADICIONAL]
    return settings


def _classify(settings, command):
    """Modelo declarado DENY > ASK > ALLOW; não prova enforcement real do host."""
    for level in ("deny", "ask", "allow"):
        for rule in settings["permissions"][level]:
            if rule.startswith("Bash(") and fnmatch.fnmatchcase(command, rule[5:-1]):
                return level
    return None


def _tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def development_tree(tmp_path):
    relative = [".claude/settings.json", "plugins/cdp/.claude-plugin/plugin.json"]
    relative += [f"plugins/cdp/skills/{f}/SKILL.md" for f in pe.FOLHAS if f != "retomar"]
    relative += list(ro.gerar_skills(ROT))
    relative += [p.replace(".agents/skills", ".claude/skills", 1) for p in ro.gerar_skills(ROT)]
    for r in relative:
        dest = tmp_path / r
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / r, dest)
    return tmp_path


def test_settings_preserves_every_other_grant_and_ask_deny_literal():
    original = _legacy_settings()
    original["permissions"]["allow"].append("Read(/custom/**)")
    original["permissions"]["ask"].append("Bash(custom review)")
    original["permissions"]["deny"].append("Bash(custom denied)")
    original["extra"] = {"untouched": ["literal"]}
    before = copy.deepcopy(original)
    output = pe.gerar_settings(ROT, original)
    assert original == before
    a, b = before["permissions"], output["permissions"]
    assert [v for v in b["allow"] if not pe._cdp(v)] == [v for v in a["allow"] if not pe._cdp(v)]
    assert set(v for v in b["allow"] if pe._cdp(v)) == set(pe.regras(ROT))
    assert b["ask"] == a["ask"] + list(pe.ASK_ADICIONAL)
    assert b["deny"] == a["deny"] + list(pe.DENY_ADICIONAL)
    assert b["defaultMode"] == a["defaultMode"]
    assert output["env"] == before["env"] and output["extra"] == before["extra"]
    assert pe.gerar_settings(ROT, output) == output


@pytest.mark.parametrize("family", tuple(pe.FOLHAS))
def test_task_catalog_matches_native_ids_and_has_no_broad_rule(family):
    leaves = pe.prefixos(ROT, family)
    assert all("*" not in leaf for leaf in leaves)
    ids = {t.id for t in ROT.familias().get(f"cdp-{family}", ())}
    assert {v.removeprefix("rotinas gate --tarefa ") for v in leaves
            if v.startswith("rotinas gate --tarefa ")} == ids
    expected_publish = ids if any(ROT.tarefa(i).grava for i in ids) else set()
    assert {v.removeprefix("publicar --tarefa ") for v in leaves
            if v.startswith("publicar --tarefa ")} == expected_publish
    for form in pe.FORMAS:
        assert f"Bash({form}*)" not in pe.regras(ROT, family)
        assert not any(_classify({"permissions": {"allow": pe.regras(ROT, family),
                                                "ask": [], "deny": []}}, form + denied)
                       for denied in ("reinicio --executar", "executor transferir --para outro",
                                      "executor registrar --como outro", "kill-switch off",
                                      "trava adquirir", "weekly unknown", "demo", "genese"))


@pytest.mark.parametrize("command,level", [
    ("weekly prepare --date 2026-10-09", "allow"),
    ("rotinas gate --tarefa cdp-diario --adquirir", "allow"),
    ("publicar --tarefa cdp-diario --mensagem x", "allow"),
    ("rotinas gate --tarefa cdp-diario-inventado", None),
    ("publicar --tarefa cdp-diario-inventado", None),
    ("reinicio --executar", "ask"),
    ("executor transferir --para outro", "ask"),
    ("executor registrar --como outro", "ask"),
    ("trava adquirir", "ask"),
    ("kill-switch off --reason x", "deny"),
    ("rotinas gate --tarefa cdp-diario --manual", "ask"),
    ("rotinas gate --tarefa cdp-diario --agora 2026-10-09T12:00:00-03:00", "ask"),
    ("rotinas gate --tarefa cdp-diario --ensaio", "ask"),
    ("rotinas gate --tarefa cdp-diario --sem-trava", "ask"),
    ("publicar --tarefa cdp-diario --sem-trava", "ask"),
    ("weekly prepare --date 2026-10-09 --force", "deny"),
    ("executor transferir --para outro --forcar", "deny"),
    ("kill-switch senha", None),
])
@pytest.mark.parametrize("form", pe.FORMAS)
def test_declared_host_policy_interventions_are_not_autoapproved(command, level, form):
    assert _classify(_settings(), form + command) == level


def test_catalog_immutable_and_rejects_changed_role_or_unknown_family():
    with pytest.raises(TypeError):
        pe.FOLHAS["status"] = ("reinicio",)
    with pytest.raises(ValueError, match="Família"):
        pe.regras(ROT, "unknown")
    tasks = dict(ROT.tarefas)
    tasks["cdp-status"] = replace(tasks["cdp-status"], escreve_livro=True)
    with pytest.raises(ValueError, match="Contrato"):
        pe.regras(replace(ROT, tarefas=tasks), "status")


@pytest.mark.parametrize("family", [f for f in pe.FOLHAS if f != "retomar"])
def test_plugin_only_changes_cdp_tool_lines(family):
    p = ROOT / f"plugins/cdp/skills/{family}/SKILL.md"
    original = p.read_text()
    # Recria só o grant antigo para testar a transformação sem alterar o corpo.
    lines = original.splitlines(keepends=True)
    old = [i for i, line in enumerate(lines) if pe._cdp(line.removeprefix("  - ").strip())]
    legacy = "".join(lines[:old[0]] + [f"  - Bash({pe.FORMAS[0]}*)\n"]
                     + [line for i, line in enumerate(lines[old[0]:], old[0]) if i not in old])
    output = pe.gerar_plugin_skill(ROT, family, legacy)
    assert output == original
    a, body_a = legacy.split("\n---\n", 1)
    b, body_b = output.split("\n---\n", 1)
    assert body_a == body_b
    def strip(text):
        return [line for line in text.splitlines()
                if not pe._cdp(line.removeprefix("  - ").strip())]
    assert strip(a) == strip(b)
    fm = yaml.safe_load(b.removeprefix("---\n"))
    assert set(v for v in fm["allowed-tools"] if pe._cdp(v)) == set(
        pe.regras(ROT, family, formas=(pe.FORMAS[0],)))


def test_derivatives_in_sync_and_manifest_tracks_single_version():
    assert pe.sincronizar_permissoes(ROT, ROOT, verificar_apenas=True)["ok"]
    assert ro.sincronizar_skills(ROT, ROOT, claude=True, permissoes=True,
                                verificar_apenas=True)["ok"]
    assert json.loads((ROOT / "plugins/cdp/.claude-plugin/plugin.json").read_text())["version"] == __version__


@pytest.mark.parametrize("level,index", [(k, i) for k, values in (
    ("ask", pe._ASK_MINIMOS), ("deny", pe._DENY_MINIMOS)) for i in range(len(values))])
def test_any_missing_previous_policy_ends_before_writing(development_tree, level, index):
    path = development_tree / ".claude/settings.json"
    settings = json.loads(path.read_text())
    required = {"ask": pe._ASK_MINIMOS, "deny": pe._DENY_MINIMOS}[level][index]
    settings["permissions"][level].remove(required)
    path.write_text(json.dumps(settings))
    before = _tree(development_tree)
    with pytest.raises(ValueError, match="anterior incompleta"):
        ro.sincronizar_skills(ROT, development_tree, claude=True, permissoes=True)
    assert _tree(development_tree) == before


@pytest.mark.parametrize("relative", [".claude/settings.json", "plugins/cdp/skills/status/SKILL.md",
                                      ".agents/skills/cdp-diario/SKILL.md"])
def test_symlink_precondition_ends_before_writing(development_tree, relative):
    path = development_tree / relative
    saved = path.read_bytes()
    original = path.with_name("original.txt")
    path.rename(original)
    path.symlink_to(original)
    before = _tree(development_tree)
    with pytest.raises(ValueError, match="Link simbólico"):
        ro.sincronizar_skills(ROT, development_tree, claude=True, permissoes=True)
    assert _tree(development_tree) == before and original.read_bytes() == saved


@pytest.mark.parametrize("protected", ["book", "data", "reports", "artifacts"])
def test_official_destination_refused_before_read_or_write(tmp_path, protected):
    with pytest.raises(ValueError, match="Destino oficial"):
        pe.sincronizar_permissoes(ROT, tmp_path / protected)
    assert not (tmp_path / protected).exists()


def test_parser_class_and_all_native_subparsers_disable_abbreviations():
    assert not pe.ArgumentParserCDP(allow_abbrev=True).allow_abbrev
    pending = [("", build_parser())]
    seen = set()
    paths = set()
    while pending:
        path, p = pending.pop()
        paths.add(path)
        if id(p) in seen:
            continue
        seen.add(id(p))
        assert type(p) is pe.ArgumentParserCDP and p.allow_abbrev is False
        for action in p._actions:
            if isinstance(action, argparse._SubParsersAction):
                pending.extend((f"{path} {name}".strip(), parser)
                               for name, parser in action.choices.items())
    assert {"rotinas gate", "weekly prepare", "publicar", "skills sincronizar",
            "executor transferir", "kill-switch"} <= paths
    assert build_parser().parse_args(["kill-switch", "off"]).state == "off"


@pytest.mark.parametrize("base,full,partial,tail", [
    (["rotinas", "gate", "--tarefa", "cdp-diario"], "--manual", "--man", []),
    (["rotinas", "gate", "--tarefa", "cdp-diario"], "--sem-trava", "--sem-t", []),
    (["rotinas", "gate", "--tarefa", "cdp-diario"], "--ensaio", "--ens", []),
    (["rotinas", "gate", "--tarefa", "cdp-diario"], "--agora", "--ago",
     ["2026-10-09T12:00:00-03:00"]),
    (["weekly", "prepare", "--date", "2026-10-09", "--mind", "codex"], "--force", "--f", []),
    (["publicar", "--tarefa", "cdp-diario", "--mensagem", "x"], "--sem-trava", "--sem-t", []),
    (["skills", "sincronizar", "--claude", "--verificar"], "--permissoes", "--perm", []),
])
def test_full_flags_parse_but_abbreviations_refuse_without_handler(base, full, partial, tail, capsys):
    parser = build_parser()
    parsed = parser.parse_args(base + [full] + tail)
    assert callable(parsed.func)  # Referência somente: jamais chama args.func.
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(base + [partial] + tail)
    assert exc.value.code == 2
    assert partial in capsys.readouterr().err
