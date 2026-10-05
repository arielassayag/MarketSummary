"""Plugin local do CDP (marketplace + skills), permissões do projeto, scripts e documentação.

Garante que os manifestos são válidos e apontam para caminhos existentes, que cada skill tem
frontmatter correto, que todo comando ``uv run python -m cdp ...`` citado em skills e docs é aceito
pela CLI real (``cdp.__main__.build_parser``) e que nenhum arquivo cita identificadores de modelo.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

import pytest
import yaml

from cdp.__main__ import build_parser

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN = ROOT / "plugins" / "cdp"
SKILLS = {"semanal", "diario", "risco", "status", "calibracao"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCRIPTS = ["cdp_setup_local.sh", "cdp_setup_local.ps1", "cdp_run_task.sh", "cdp_run_task.ps1"]
MODEL_RE = re.compile(r"(?i)\b(?:claude-(?:opus|sonnet|haiku)[\w.-]*|opus|sonnet|haiku|gpt-[\w.-]+)\b")


def _skill_files() -> list[Path]:
    return sorted(PLUGIN.glob("skills/*/SKILL.md"))


def _project_skill_files() -> list[Path]:
    return sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))


def _doc_files() -> list[Path]:
    docs = ROOT / "docs" / "cdp"
    return [*_skill_files(), *_project_skill_files(), PLUGIN / "README.md", docs / "LOCAL.md",
            docs / "ROTINAS.md", *sorted((docs / "playbooks").glob("*.md")), ROOT / "AGENTS.md",
            ROOT / "CLAUDE.md"]


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: sem frontmatter YAML"
    end = text.index("\n---\n", 4)
    data = yaml.safe_load(text[4:end])
    assert isinstance(data, dict), f"{path}: frontmatter não é um mapa"
    return data


# ----------------------------------------------------------------------------- manifestos


def test_marketplace_manifest_points_to_plugin():
    m = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    assert ID_RE.match(m["name"]) and m["owner"]["name"] and m.get("description")
    assert [p["name"] for p in m["plugins"]] == ["cdp"]
    entry = m["plugins"][0]
    assert entry["source"].startswith("./") and ".." not in entry["source"]
    plugin_dir = (ROOT / entry["source"]).resolve()
    assert plugin_dir == PLUGIN.resolve() and (plugin_dir / ".claude-plugin" / "plugin.json").is_file()
    assert "version" not in entry  # a versão vive só no plugin.json (evita aviso do validate)


def test_plugin_manifest():
    p = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert p["name"] == "cdp" and ID_RE.match(p["name"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", p["version"])
    assert p["description"] and p["author"]["name"]
    for key in ("skills", "commands", "agents", "hooks"):
        assert key not in p  # diretórios padrão (skills/) — sem caminhos fora do plugin
    assert {d.name for d in (PLUGIN / "skills").iterdir() if d.is_dir()} == SKILLS


@pytest.mark.parametrize("path", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_frontmatter(path: Path):
    fm = _frontmatter(path)
    assert fm["name"] == path.parent.name and SKILL_NAME_RE.match(fm["name"])
    desc = fm["description"]
    assert isinstance(desc, str) and 80 <= len(desc) <= 1536
    tools = fm.get("allowed-tools", [])
    assert isinstance(tools, list) and all(isinstance(t, str) for t in tools)
    assert not any(t.strip() in {"Bash", "Bash(*)"} for t in tools)  # nunca shell irrestrito
    body = path.read_text(encoding="utf-8")
    assert "docs/cdp/METODOLOGIA.md" in body  # metodologia perene, fora do harness
    assert "Resumo final" in body or "resumo final" in body.lower()
    assert "--force" not in body.replace("`git push --force`", "")


def test_skills_use_claude_code_mind_only():
    for path in _skill_files():
        minds = set(re.findall(r"--mind\s+([\w-]+)", path.read_text(encoding="utf-8")))
        assert minds <= {"claude-code"}, (path, minds)


def test_project_skills_delegate_to_plugin():
    files = {p.parent.name: p for p in _project_skill_files()}
    assert set(files) == {"cdp-semanal", "cdp-diario"}
    for name, path in files.items():
        fm = _frontmatter(path)
        assert fm["name"] == name and fm["description"]
        body = path.read_text(encoding="utf-8")
        target = name.replace("cdp-", "cdp:")
        assert target in body and "docs/cdp/playbooks/" in body


# ----------------------------------------------------------------------------- comandos

_INLINE = re.compile(r"`(uv run (?:python -m )?cdp(?: [^`\n]*)?)`")
_FENCE = re.compile(r"^```([\w-]*)\s*$")
_SHELL_LANGS = {"", "sh", "bash", "console", "powershell"}


def _commands(text: str) -> list[str]:
    cmds = [m.group(1) for m in _INLINE.finditer(text)]
    lang: str | None = None
    for line in text.splitlines():
        m = _FENCE.match(line.strip())
        if m:
            lang = None if lang is not None else m.group(1)
            continue
        st = line.strip()
        if lang in _SHELL_LANGS and (st.startswith("uv run python -m cdp")
                                     or st.startswith("uv run cdp ")):
            cmds.append(st)
    return cmds


def _argv(cmd: str) -> list[str]:
    cmd = cmd.split(" #")[0]
    for sep in ("&&", ";", "|"):
        cmd = cmd.split(sep)[0]
    cmd = cmd.replace("AAAA-MM-DD", "2026-10-05")
    cmd = re.sub(r"<[^<>]+>", "X", cmd)
    toks = shlex.split(cmd)
    if toks[:5] == ["uv", "run", "python", "-m", "cdp"]:
        return toks[5:]
    assert toks[:3] == ["uv", "run", "cdp"], cmd
    return toks[3:]


def _all_commands() -> list[tuple[str, str]]:
    out = []
    for path in _doc_files():
        for c in _commands(path.read_text(encoding="utf-8")):
            out.append((str(path.relative_to(ROOT)), c))
    return out


def test_every_cli_command_in_skills_and_docs_parses():
    cmds = _all_commands()
    assert len(cmds) >= 40
    seen: set[str] = set()
    for where, cmd in cmds:
        argv = _argv(cmd)
        assert argv, f"{where}: comando sem subcomando: {cmd}"
        try:
            args = build_parser().parse_args(argv)
        except SystemExit:  # pragma: no cover - mensagem útil na falha
            pytest.fail(f"{where}: a CLI rejeita `{cmd}`")
        seen.add(args.cmd)
    assert {"agenda", "risk", "validate-daily", "daily", "weekly", "validate", "verify",
            "kill-switch", "backtest", "status"} <= seen


def test_skill_commands_cover_their_workflow():
    by_skill = {p.parent.name: " ".join(_commands(p.read_text(encoding="utf-8")))
                for p in _skill_files()}
    assert "weekly prepare" in by_skill["semanal"] and "weekly decide" in by_skill["semanal"]
    assert "validate --week" in by_skill["semanal"]
    assert "daily close" in by_skill["diario"] and "daily publish" in by_skill["diario"]
    assert "validate-daily" in by_skill["diario"]
    assert "risk --live" in by_skill["risco"] and "kill-switch on" in by_skill["risco"]
    assert "kill-switch off" not in " ".join(by_skill.values())
    assert "verify" in by_skill["status"] and "agenda" in by_skill["status"]
    assert "backtest" in by_skill["calibracao"]
    for name in SKILLS:
        assert "agenda" in by_skill[name] or name == "calibracao" and "backtest" in by_skill[name]


# ----------------------------------------------------------------------------- permissões


def _rule_regex(pattern: str) -> re.Pattern[str]:
    """Regra ``Edit(/x/**)`` do settings (ancorada na raiz do projeto) → regex de caminho."""
    p = pattern.lstrip("/")
    out = ""
    i = 0
    while i < len(p):
        if p.startswith("**", i):
            out += ".*"
            i += 2
        elif p[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(p[i])
            i += 1
    return re.compile(out + r"\Z")


def _edit_rules(rules: list[str]) -> list[re.Pattern[str]]:
    return [_rule_regex(r[5:-1]) for r in rules if r.startswith("Edit(") and r.endswith(")")]


def _matches(rules: list[re.Pattern[str]], path: str) -> bool:
    return any(r.match(path) for r in rules)


def test_project_settings_permissions():
    s = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    perm = s["permissions"]
    assert perm["defaultMode"] in {"default", "acceptEdits", "plan", "auto", "dontAsk"}
    allow, ask, deny = perm["allow"], perm.get("ask", []), perm["deny"]
    for needed in ("Bash(uv sync *)", "Bash(uv run python -m cdp *)", "Bash(git pull *)",
                   "Bash(git add *)", "Bash(git commit *)", "Bash(git push *)", "WebSearch",
                   "WebFetch"):
        assert needed in allow, needed
    assert "Bash" not in allow and "Bash(*)" not in allow and "Read" not in allow
    for blocked in ("Bash(uv run python -m cdp kill-switch off*)", "Bash(git push --force*)",
                    "Bash(git push *--force*)", "Bash(rm -rf *)"):
        assert blocked in deny, blocked
    assert not any(r.startswith("Write(") for r in allow + ask + deny)  # não consultadas
    a, k, d = _edit_rules(allow), _edit_rules(ask), _edit_rules(deny)
    for mind_file in ("book/2026-10-05/inputs/research_pack.json",
                      "book/2026-10-05/inputs/pm_decision.json",
                      "reports/daily/2026-10-05/comentario.json",
                      "reports/backtest/2026-11-02/CALIBRACAO_MENSAL.md"):
        assert _matches(a, mind_file) and not _matches(d, mind_file), mind_file
    for code_file in ("book/audit_log.jsonl", "book/KILL_SWITCH",
                      "book/track_record/records/2026-10-05.json",
                      "book/2026-10-05/decision_v1.json", "book/2026-10-05/proposal_v1.json",
                      "book/2026-10-05/booked.json", "book/2026-10-05/briefing/context.json",
                      "book/2026-10-05/research_pack_abc.json",
                      "data/market/base/2026-10-02/manifest.json",
                      "reports/daily/2026-10-05/relatorio.md",
                      "reports/daily/2026-10-05/facts.md",
                      "reports/weekly/2026-10-05/relatorio.md",
                      "reports/risk/2026-10-05/risco_1330.md"):
        assert _matches(d, code_file), code_file
    assert _matches(k, "configs/cdp/fund.yaml") and not _matches(a, "configs/cdp/fund.yaml")
    assert s["env"]["PYTHONUTF8"] == "1"


# ----------------------------------------------------------------------------- scripts e repo


def test_local_scripts_exist_and_call_plugin_skills():
    for name in SCRIPTS:
        path = ROOT / "scripts" / name
        assert path.is_file(), name
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        if name.endswith(".ps1"):
            assert raw.startswith(b"\xef\xbb\xbf"), f"{name}: UTF-8 com BOM (PowerShell 5.1)"
        else:
            assert text.startswith("#!/usr/bin/env bash") and "\r\n" not in text
            if os.name == "posix":
                assert os.access(path, os.X_OK), f"{name} sem permissão de execução"
        if "run_task" in name:
            assert "/cdp:" in text and "--permission-mode" in text and "logs" in text
            assert "--bare" not in text  # --bare não carrega plugins nem skills
        else:
            assert "uv sync --extra dev --extra ai" in text
            assert "cdp@cdp-cabra-da-peste" in text


def test_repo_files_for_local_operation():
    assert "logs/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for line in ("book/** -text", "data/** -text", "reports/** -text"):
        assert line in attrs
    local = (ROOT / "docs" / "cdp" / "LOCAL.md").read_text(encoding="utf-8")
    for needle in ("claude plugin marketplace add", "claude plugin install cdp@cdp-cabra-da-peste",
                   "/cdp:semanal", "/cdp:diario", "/cdp:risco", "/cdp:status", "/cdp:calibracao",
                   "11:07", "13:30", "16:00", "19:22", "Worktree", "pc_menos_brasilia_horas",
                   "kill-switch off", "cron", "launchd", "schtasks", "--mind codex"):
        assert needle in local, needle


def test_no_model_identifiers_in_local_operation_files():
    files = [MARKETPLACE, *PLUGIN.rglob("*"), ROOT / ".claude" / "settings.json",
             *_project_skill_files(), ROOT / "docs" / "cdp" / "LOCAL.md",
             ROOT / "docs" / "cdp" / "ROTINAS.md", *(ROOT / "scripts" / n for n in SCRIPTS)]
    for path in files:
        if path.is_file():
            hits = MODEL_RE.findall(path.read_bytes().decode("utf-8-sig"))
            assert not hits, f"{path}: {hits}"
