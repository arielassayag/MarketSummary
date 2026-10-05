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
            "kill-switch", "backtest", "status", "painel"} <= seen


def test_painel_command_defaults():
    args = build_parser().parse_args(["painel"])
    assert Path(args.out_dir).as_posix() == "artifacts/painel" and args.sem_local is False
    assert args.publicado is False
    args = build_parser().parse_args(["painel", "--out-dir", "x", "--sem-local"])
    assert (args.out_dir, args.sem_local) == ("x", True)
    assert build_parser().parse_args(["painel", "--publicado"]).publicado is True


def test_cli_painel_delegates_to_write_painel(monkeypatch, tmp_path, capsys):
    """``cdp painel`` só repassa a pasta para ``write_painel`` e imprime o resultado (JSON) com o
    bloco ``artifact`` lido do disco."""
    import cdp.workflow.painel as painel
    from cdp.__main__ import main

    calls = []

    def fake(rt, out_dir, *, standalone=True, now=None, **kw):
        calls.append((rt, out_dir, standalone, now, kw))
        return {"out_dir": Path(out_dir).as_posix(), "page_changed": True}

    monkeypatch.setattr(painel, "write_painel", fake)
    out = tmp_path / "p"
    base = ["--book", str(tmp_path / "book"), "--market", str(tmp_path / "market"),
            "--reports", str(tmp_path / "reports")]
    assert main(base + ["painel", "--out-dir", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    check = printed.pop("artifact")
    assert printed == {"out_dir": out.as_posix(), "page_changed": True}
    assert check["publicavel"] is False and "ilegível" in check["motivo"]  # o falso não grava
    assert check["pagina_mudou"] is True
    (rt, out_dir, standalone, now, kw), = calls
    assert out_dir == out and standalone is True and now is None and kw == {}
    assert rt.book_root == tmp_path / "book"
    assert main(base + ["painel", "--out-dir", str(out), "--sem-local"]) == 0
    assert calls[-1][2] is False
    # --publicado não gera nada: só registra a página publicada (aqui não há index.html)
    n = len(calls)
    assert main(base + ["painel", "--out-dir", str(out), "--publicado"]) == 2
    assert len(calls) == n and "index.html" in capsys.readouterr().err


def test_painel_artifact_check_limits(tmp_path):
    """A skill só lê e publica quando os arquivos cabem na leitura integral; a página só entra
    na leitura quando mudou."""
    from cdp.__main__ import painel_artifact_check
    from cdp.workflow.painel_publicacao import DATA_MAX_BYTES, DATA_MAX_LINE, PAGE_MAX_LINE

    out = tmp_path / "painel"
    out.mkdir()
    data, index = out / "data.json", out / "index.html"
    data.write_text('{\n "meta": "DADOS SIMULADOS"\n}\n', encoding="utf-8")
    index.write_text("<title>x</title>\n" + "y" * (PAGE_MAX_LINE + 1) + "\n", encoding="utf-8")
    ok = painel_artifact_check(out, page_changed=False)
    assert ok["publicavel"] is True and ok["motivo"] == "ok" and ok["pagina_mudou"] is False
    assert ok["arquivos_para_ler"] == [data.as_posix()] and ok["url"] is None
    assert ok["pagina_publicada"] is None
    (out / "PAGINA_PUBLICADA.sha256").write_text("a" * 64 + "\n", encoding="utf-8")
    assert painel_artifact_check(out, page_changed=False)["pagina_publicada"] == "a" * 64
    assert ok["tamanho_dados"] == data.stat().st_size and ok["linhas_dados"] == 3
    assert ok["linhas_max"] == len(' "meta": "DADOS SIMULADOS"')
    page = painel_artifact_check(out, page_changed=True)  # página mudou: entra na leitura
    assert page["publicavel"] is False and "index.html com linha de" in page["motivo"]
    assert page["arquivos_para_ler"] == [index.as_posix(), data.as_posix()]
    index.write_text("<title>x</title>\n", encoding="utf-8")
    assert painel_artifact_check(out, page_changed=True)["publicavel"] is True
    (out / "ARTIFACT_URL").write_text("https://claude.ai/artifact/abc\n", encoding="utf-8")
    assert painel_artifact_check(out, page_changed=False)["url"] == "https://claude.ai/artifact/abc"
    data.write_text("x" * (DATA_MAX_LINE + 1), encoding="utf-8")
    bad = painel_artifact_check(out, page_changed=False)
    assert bad["publicavel"] is False and "data.json com linha de" in bad["motivo"]
    data.write_text(("y" * 99 + "\n") * (DATA_MAX_BYTES // 100 + 1), encoding="utf-8")
    assert "bytes" in painel_artifact_check(out, page_changed=False)["motivo"]
    data.unlink()
    gone = painel_artifact_check(out, page_changed=False)
    assert gone["publicavel"] is False and "ilegível" in gone["motivo"]


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


PAINEL_SKILLS = ("semanal", "diario", "risco", "calibracao")
PAINEL_HTML = "artifacts/painel/index.html"
PAINEL_DATA = "artifacts/painel/data.json"
PAINEL_FILES = 'files: {"data.json": "artifacts/painel/data.json"}'
PAINEL_URL = "artifacts/painel/ARTIFACT_URL"


@pytest.mark.parametrize("name", PAINEL_SKILLS)
def test_writer_skills_end_by_republishing_the_painel(name: str):
    path = PLUGIN / "skills" / name / "SKILL.md"
    body = path.read_text(encoding="utf-8")
    assert "Artifact" in _frontmatter(path)["allowed-tools"]
    cmds = _commands(body)
    assert "uv run python -m cdp painel" in cmds
    # Ordem: painel (código) → commit/push principal (inclui o HTML) → republicação no artifact.
    i_painel = body.index("uv run python -m cdp painel")
    i_commit = body.index('git commit -m "CDP: ')
    i_read, i_pub = body.index('action: "read"'), body.index('action: "publish"')
    # read → list dos arquivos publicados → publish: a ferramenta só substitui um arquivo
    # publicado (data.json) que a sessão leu pelo caminho, viu numa listagem ou publicou.
    i_list = body.index('action: "list"')
    assert i_painel < i_commit < i_read < i_list < i_pub
    flat0 = " ".join(body.split())
    assert 'action: "list"` com `scope: "files"`' in flat0
    assert flat0.count('`scope: "files"`') >= 2  # e de novo, se data.json mudou no meio
    assert "data.json` mudou desde a listagem" in flat0
    # página registrada como publicada só depois de publicar com sucesso (e commitada)
    i_mark = body.index("uv run python -m cdp painel --publicado")
    assert i_pub < i_mark
    assert "artifacts/painel/PAGINA_PUBLICADA.sha256" in flat0
    assert ('git commit -m "CDP: painel publicado" -- artifacts/painel/PAGINA_PUBLICADA.sha256'
            in flat0)
    assert re.search(r"^\s*git add .*\bartifacts/painel\b", body, re.MULTILINE)
    # Mesmo artifact: URL do arquivo; dados sempre lidos por inteiro e publicados em `files`; a
    # página só quando mudou. A rotina nunca cria artifact (sem a URL, não publica).
    flat = " ".join(body.split())
    assert PAINEL_URL in flat and PAINEL_DATA in flat and PAINEL_HTML in flat
    assert PAINEL_FILES in flat and "artifact.arquivos_para_ler" in flat
    assert "pagina_mudou" in flat and "por inteiro" in flat
    assert 'icon: "chart"' not in flat and "CDP: URL do painel" not in flat
    assert "não publique" in flat and "nunca cria um artifact novo" in flat
    assert "nunca use `force`" in flat
    assert "sem a ferramenta `artifact`" in flat.lower()  # headless/Codex: pula e relata
    assert "não insista" in flat  # falha ou recusa da ferramenta não bloqueia a rotina
    tail = body[body.lower().rindex("resumo final"):]
    assert "painel" in tail.lower()


WRITER_SKILLS = PAINEL_SKILLS
SYNC_DIFF = 'git diff --name-only "HEAD...@{u}" -- book data reports artifacts'


@pytest.mark.parametrize("name", WRITER_SKILLS)
def test_writer_skills_guard_the_clone_and_sync_safely(name: str):
    """Clone dedicado na main; fetch + merge só sem mudanças no livro; push só com verify íntegro."""
    path = PLUGIN / "skills" / name / "SKILL.md"
    body = path.read_text(encoding="utf-8")
    flat = " ".join(body.split())
    tools = _frontmatter(path)["allowed-tools"]
    for needed in ("Bash(git branch --show-current)", "Bash(git fetch *)",
                   "Bash(git pull --no-rebase --no-edit)", "Bash(git diff *)", "Bash(git push)"):
        assert needed in tools, needed
    assert "Bash(git pull --ff-only)" not in tools and "git pull --ff-only" not in body
    assert "git branch --show-current" in body and "`main`" in body
    assert "clone dedicado" in flat and "git status --porcelain" in body
    assert SYNC_DIFF in body and "git pull --no-rebase --no-edit" in body
    assert "git fetch" in body and ("sem push" in flat or "não** faça push" in flat)
    assert "uv run python -m cdp verify" in body and "Push só se `verify`" in flat
    assert re.search(r"Nunca use `git push --force`, `rebase` nem `reset`", flat)
    # Painel: só lê e publica quando o código diz que cabe na leitura integral.
    assert "artifact.publicavel" in flat and "não leia nem publique" in flat


@pytest.mark.parametrize("name", WRITER_SKILLS)
def test_writer_skills_never_wait_on_permission_prompts(name: str):
    """Comando fora das regras para a tarefa no app: as skills proíbem os casos comuns."""
    body = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    flat = " ".join(body.split())
    assert "`python -c`, `jq`, `sleep`" in flat and "laços de espera" in flat
    fences = re.findall(r"```(?:sh|bash)?\n(.*?)```", body, re.S)
    for block in fences:
        for line in block.splitlines():
            st = line.strip()
            if st:
                assert st.split()[0] in {"uv", "git"}, (name, st)


def test_calibration_is_idempotent_and_never_polls():
    body = (PLUGIN / "skills" / "calibracao" / "SKILL.md").read_text(encoding="utf-8")
    flat = " ".join(body.split())
    assert "`CALIBRACAO_MENSAL.md` existe → encerre" in flat
    assert "`mensal/metrics.json` existe" in flat and "pule o passo 3" in flat
    assert "run_in_background" in flat and "encerre o turno sem esperar" in flat
    for script in ("cdp_run_task.sh", "cdp_run_task.ps1"):
        text = (ROOT / "scripts" / script).read_bytes().decode("utf-8-sig")
        i_bt = text.index("cdp backtest --start 2021-01-04")
        i_claude = text.index("-p $prompt" if script.endswith(".ps1") else '-p "$PROMPT"')
        assert i_bt < i_claude, script  # backtest antes da skill (no -p o segundo plano morre)
        assert "CALIBRACAO_MENSAL.md" in text and "metrics.json" in text


def test_run_task_scripts_wait_for_the_lock_and_report_skips():
    for script in ("cdp_run_task.sh", "cdp_run_task.ps1"):
        text = (ROOT / "scripts" / script).read_bytes().decode("utf-8-sig")
        assert "CDP_LOCK_WAIT_MIN" in text and "exit 75" in text, script
        assert "semanal" in text and "diario" in text
    ps1 = (ROOT / "scripts" / "cdp_run_task.ps1").read_bytes().decode("utf-8-sig")
    assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in ps1
    assert re.search(r"try \{\s*& \$claude", ps1) and "CommandNotFoundException" in ps1


def test_painel_folder_exists_for_git_add():
    """``git add ... artifacts/painel`` não pode abortar quando o painel falha."""
    assert (ROOT / "artifacts" / "painel" / ".gitkeep").is_file()


def test_project_semanal_validates_with_mind():
    body = (ROOT / ".claude" / "skills" / "cdp-semanal" / "SKILL.md").read_text(encoding="utf-8")
    flat = " ".join(body.split())
    assert "validate --week AAAA-MM-DD --mind claude-code" in flat


def test_local_guide_schedules_backups_and_is_honest_about_prompts():
    local = (ROOT / "docs" / "cdp" / "LOCAL.md").read_text(encoding="utf-8")
    flat = " ".join(local.split())
    for needle in ("cdp-semanal-b", "cdp-semanal-c", "cdp-semanal-d", "12:37", "14:07", "15:07",
                   "cdp-diario-reforco", "21:07", "uma tarefa por vez", "últimos 7 dias",
                   "Register-ScheduledTask", "-AllowStartIfOnBatteries",
                   "-DontStopIfGoingOnBatteries", "-StartWhenAvailable", "-WindowStyle Hidden",
                   "feche e reabra o app", "git pull --no-rebase --no-edit", "clone dedicado",
                   "revisao_humana", "artifact.publicavel"):
        assert needle in flat, needle
    assert "(opcional)" not in local  # o reforço das 21:07 é parte da agenda
    assert "nada fica esperando aprovação" not in flat
    assert "`dontAsk`) só existe no CLI" in flat
    for script in ("cdp_setup_local.sh", "cdp_setup_local.ps1"):
        text = (ROOT / "scripts" / script).read_bytes().decode("utf-8-sig")
        for task in ("cdp-semanal-b", "cdp-semanal-c", "cdp-semanal-d", "cdp-diario-reforco",
                     "cdp-calibracao", "cdp-status"):
            assert task in text, (script, task)
        assert "feche e reabra o app do Claude" in text, script


def test_status_only_reports_the_painel_url():
    path = PLUGIN / "skills" / "status" / "SKILL.md"
    body = path.read_text(encoding="utf-8")
    assert PAINEL_URL in body and f"git log -1 --format=%ci -- {PAINEL_DATA}" in body
    assert "Artifact" not in _frontmatter(path).get("allowed-tools", [])
    assert 'action: "publish"' not in body
    assert not any(" painel" in c for c in _commands(body))


def test_risk_skill_commits_only_its_own_paths():
    """A montagem semanal pode estar em andamento no mesmo clone: o risco não leva o livro junto."""
    body = (PLUGIN / "skills" / "risco" / "SKILL.md").read_text(encoding="utf-8")
    assert 'git commit -m "CDP: risco AAAA-MM-DD HH:MM" -- reports/risk artifacts/painel' in body
    assert "git add reports/risk artifacts/painel" in body
    assert not re.search(r"^\s*git add .*\bbook\b", body, re.MULTILINE)
    assert "book/KILL_SWITCH" in body and "book/audit_log.jsonl" in body


def test_local_guide_documents_the_painel_artifact():
    local = (ROOT / "docs" / "cdp" / "LOCAL.md").read_text(encoding="utf-8")
    assert "## 10. Painel (artifact)" in local
    flat = " ".join(local.split())
    for needle in (PAINEL_URL, PAINEL_HTML, PAINEL_DATA, "artifacts/painel/cdp_painel_local.html",
                   "uv run python -m cdp painel", "--sem-local", "`read`", "`publish`",
                   '`list` com `scope: "files"`', "uv run python -m cdp painel --publicado",
                   "artifacts/painel/PAGINA_PUBLICADA.sha256", "meta.page_sha256",
                   "não com o `index.html` local", "Página desatualizada",
                   "Nunca criam um artifact novo", "Não foi possível carregar data.json",
                   "260 KB", "1.500 caracteres", "meta.truncations", "artifact.publicavel",
                   "arquivos_para_ler", "pagina_mudou", PAINEL_FILES.replace("files: ", "")):
        assert needle in flat, needle
    # o texto antigo ("avisa sempre que a página for mais antiga que os dados") era falso
    assert "Se a página publicada ficar mais antiga que os dados" not in flat
    for doc in ("ROTINAS.md", "playbooks/DIARIO.md", "playbooks/SEMANAL.md"):
        text = (ROOT / "docs" / "cdp" / doc).read_text(encoding="utf-8")
        assert "uv run python -m cdp painel" in text and PAINEL_URL in text, doc
        assert "cdp_painel.html" not in text and "arquivos_para_ler" in text, doc
        assert "list" in text, doc
    rotinas = " ".join((ROOT / "docs" / "cdp" / "ROTINAS.md").read_text(encoding="utf-8").split())
    assert rotinas.count('list com scope "files"') >= 3
    assert rotinas.count("uv run python -m cdp painel --publicado") >= 3


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
                      "reports/backtest/2026-11-02/CALIBRACAO_MENSAL.md", PAINEL_URL):
        assert _matches(a, mind_file) and not _matches(d, mind_file), mind_file
    # O HTML do painel é gerado pelo código; a ferramenta Artifact só vale dentro das skills.
    assert _matches(d, PAINEL_HTML) and not _matches(a, PAINEL_HTML)
    assert not any(r == "Artifact" or r.startswith("Artifact(") for r in allow)
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
                   "kill-switch off", "cron", "launchd", "schtasks", "Register-ScheduledTask",
                   "--mind codex"):
        assert needle in local, needle


def test_no_model_identifiers_in_local_operation_files():
    files = [MARKETPLACE, *PLUGIN.rglob("*"), ROOT / ".claude" / "settings.json",
             *_project_skill_files(), ROOT / "docs" / "cdp" / "LOCAL.md",
             ROOT / "docs" / "cdp" / "ROTINAS.md", *(ROOT / "scripts" / n for n in SCRIPTS)]
    for path in files:
        if path.is_file():
            hits = MODEL_RE.findall(path.read_bytes().decode("utf-8-sig"))
            assert not hits, f"{path}: {hits}"
