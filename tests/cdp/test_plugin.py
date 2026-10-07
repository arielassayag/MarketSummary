"""Plugin do Claude Code, skills, roteiros neutros, permissões do projeto, scripts e guias das rotinas.

O procedimento de cada rotina mora num só lugar — o roteiro neutro em ``docs/cdp/playbooks/`` —,
igual no Claude Code, no Codex, no Gemini ou em qualquer outro app. Este arquivo garante que:

- as skills (plugin ``cdp``, ``.claude/skills`` e ``.agents/skills``) só fazem a entrada (gate uma
  vez, trava, ``cdp sincronizar``) e a saída (``cdp publicar``, liberar a trava) e mandam seguir o
  roteiro; nenhuma roda ``git`` que grave nem publica artifacts;
- os roteiros seguem a mesma forma (entrada, passos, integridade, publicação pelo código, resumo),
  com a exceção do modo executor, e cobrem a montagem, o fechamento com os relatórios semanais
  pendentes, a cobertura, o risco (com os arquivos retidos), o estado e a calibração;
- todo comando ``uv run python -m cdp …`` citado é aceito pela CLI real, a tabela das rotinas é a
  gerada pelo código e os guias ensinam a configurar as rotinas no Claude Code, no Codex e no
  Gemini, em português;
- as permissões do projeto liberam as skills do CDP, bloqueiam o que só um humano decide e nunca
  bloqueiam um arquivo da mente; nenhum arquivo cita identificadores de modelo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

from cdp import rotinas as ro
from cdp.__main__ import build_parser

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN = ROOT / "plugins" / "cdp"
PLAYBOOKS = ROOT / "docs" / "cdp" / "playbooks"
DOCS = ROOT / "docs" / "cdp"
ROT = ro.carregar(ROOT / "configs" / "cdp" / "rotinas.yaml")
SKILLS = {"semanal", "diario", "cobertura", "risco", "status", "calibracao"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCRIPTS = ["cdp_setup_local.sh", "cdp_setup_local.ps1", "cdp_run_task.sh", "cdp_run_task.ps1"]
MODEL_RE = re.compile(r"(?i)\b(?:claude-(?:opus|sonnet|haiku)[\w.-]*|opus|sonnet|haiku|gpt-[\w.-]+)\b")
TESES = ROOT / "docs" / "cdp" / "teses"
#: Versão do plugin e resumo das skills nessa versão. A instalação pelo marketplace do GitHub guarda
#: uma cópia presa à ``version`` (docs/cdp/LOCAL.md): skills novas com a versão antiga nunca chegam
#: às rotinas. Mudou uma skill ⇒ suba a ``version`` em plugin.json e atualize os dois valores.
PLUGIN_VERSION = "1.5.2"
SKILLS_SHA256 = "f151cbdb91ab1cfdf385ea6fdf883300f55cf5a05f5071773fb13dc2d8af449c"
#: Roteiro de cada skill do plugin e a família de tarefas de ``configs/cdp/rotinas.yaml``.
ROTEIRO = {"semanal": "SEMANAL.md", "diario": "DIARIO.md", "cobertura": "COBERTURA.md",
           "risco": "RISCO.md", "status": "STATUS.md", "calibracao": "CALIBRACAO.md"}
ESCRITORES = ("semanal", "diario", "cobertura", "risco", "calibracao")
#: Comandos ``git`` que gravam: nunca num roteiro, numa skill ou num prompt (só ``cdp publicar``).
GIT_GRAVA = re.compile(r"\bgit (?:add|commit|push|pull|merge|rebase|reset|fetch|stash|checkout)\b")


def _familia(skill: str) -> list[ro.Tarefa]:
    return [t for t in ROT.tarefas.values() if t.skill == f"cdp-{skill}"]


def _skill_files() -> list[Path]:
    return sorted(PLUGIN.glob("skills/*/SKILL.md"))


def _project_skill_files() -> list[Path]:
    return sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))


def _playbook_files() -> list[Path]:
    return sorted(PLAYBOOKS.glob("*.md"))


def _doc_files() -> list[Path]:
    return [*_skill_files(), *_project_skill_files(), PLUGIN / "README.md", DOCS / "LOCAL.md",
            DOCS / "ROTINAS.md", DOCS / "TESE.md", TESES / "README.md", DOCS / "NOTAS.md",
            DOCS / "notas" / "README.md", DOCS / "ESTILO.md", DOCS / "REPRODUZIR.md",
            *_playbook_files()]


def _ler(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _plano(texto: str) -> str:
    return " ".join(texto.split())


def _skills_digest() -> str:
    """SHA-256 dos arquivos das skills do plugin (caminho + conteúdo, fins de linha LF)."""
    h = hashlib.sha256()
    files = [f for f in (PLUGIN / "skills").rglob("*") if f.is_file() and not f.name.startswith(".")]
    for f in sorted(files, key=lambda f: f.relative_to(PLUGIN).as_posix()):
        h.update(f.relative_to(PLUGIN).as_posix().encode("utf-8") + b"\0")
        h.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def _frontmatter(path: Path) -> dict:
    text = _ler(path)
    assert text.startswith("---\n"), f"{path}: sem frontmatter YAML"
    end = text.index("\n---\n", 4)
    data = yaml.safe_load(text[4:end])
    assert isinstance(data, dict), f"{path}: frontmatter não é um mapa"
    return data


def _corpo(path: Path) -> str:
    text = _ler(path)
    return text[text.index("\n---\n", 4) + 5:]


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


def _shell_lines(text: str) -> list[str]:
    """Linhas dos blocos de código de shell (onde ficam os comandos a rodar)."""
    out: list[str] = []
    lang: str | None = None
    for line in text.splitlines():
        m = _FENCE.match(line.strip())
        if m:
            lang = None if lang is not None else m.group(1)
            continue
        if lang in _SHELL_LANGS and line.strip():
            out.append(line.strip())
    return out


def _argv(cmd: str) -> list[str]:
    cmd = cmd.replace("<mente>", "claude-code")  # a mente do gate (valor do app)
    cmd = re.sub(r"<[^<>]+>", "X", cmd)  # marcadores (podem conter ";") antes dos separadores
    cmd = cmd.split(" #")[0]
    for sep in ("&&", ";", "|"):
        cmd = cmd.split(sep)[0]
    cmd = cmd.replace("AAAA-MM-DD", "2026-10-09")
    toks = shlex.split(cmd)
    if toks[:5] == ["uv", "run", "python", "-m", "cdp"]:
        return toks[5:]
    assert toks[:3] == ["uv", "run", "cdp"], cmd
    return toks[3:]


def _idx(texto: str, agulha: str, inicio: int = 0) -> int:
    i = texto.find(agulha, inicio)
    assert i >= 0, f"não encontrado: {agulha!r}"
    return i


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


def test_plugin_version_tracks_the_skills():
    """A cópia em cache do marketplace do GitHub só é trocada quando a ``version`` sobe: skills
    alteradas sem versão nova deixariam as rotinas com as instruções antigas."""
    p = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert p["version"] == PLUGIN_VERSION
    assert _skills_digest() == SKILLS_SHA256, (
        "as skills do plugin mudaram: suba `version` em plugins/cdp/.claude-plugin/plugin.json e "
        f"atualize PLUGIN_VERSION e SKILLS_SHA256 (novo resumo: {_skills_digest()})")
    assert "a versão precisa subir quando as skills mudarem" in _plano(_ler(DOCS / "LOCAL.md"))


# ----------------------------------------------------------------------------- skills


@pytest.mark.parametrize("path", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_frontmatter(path: Path):
    fm = _frontmatter(path)
    assert fm["name"] == path.parent.name and SKILL_NAME_RE.match(fm["name"])
    desc = fm["description"]
    assert isinstance(desc, str) and 80 <= len(desc) <= 1536
    tools = fm.get("allowed-tools", [])
    assert isinstance(tools, list) and all(isinstance(t, str) for t in tools)
    assert not any(t.strip() in {"Bash", "Bash(*)"} for t in tools)  # nunca shell irrestrito
    # nenhuma ferramenta de git que grave e nenhuma publicação de artifact numa rotina
    assert not any(GIT_GRAVA.search(t) for t in tools), tools
    assert "Artifact" not in tools
    assert {"Bash(uv sync *)", "Bash(uv run python -m cdp *)"} <= set(tools)
    body = _ler(path)
    assert "docs/cdp/METODOLOGIA.md" in body  # metodologia perene, fora do app
    assert "Resumo final" in body
    assert "--force" not in body.replace("nunca use `--force`", "")


def test_skills_use_claude_code_mind_only():
    for path in _skill_files():
        texto = _ler(path)
        minds = set(re.findall(r"--mind\s+([\w-]+)", texto)) | set(
            re.findall(r"--mente\s+([\w-]+)", texto))
        assert minds <= {"claude-code"}, (path, minds)


@pytest.mark.parametrize("nome", sorted(SKILLS))
def test_plugin_skills_are_thin_wrappers_of_the_playbooks(nome: str):
    """A skill do plugin só faz a entrada e a saída da execução no Claude Code: gate uma vez
    (com a trava nos escritores exclusivos), ``cdp sincronizar``, o roteiro neutro,
    ``cdp publicar`` e a liberação da trava; o procedimento é o do roteiro, o mesmo dos outros
    apps."""
    path = PLUGIN / "skills" / nome / "SKILL.md"
    body = _corpo(path)
    flat = _plano(body)
    familia = _familia(nome)
    assert familia, nome
    t0 = familia[0]
    roteiro = f"docs/cdp/playbooks/{ROTEIRO[nome]}"
    assert t0.playbook == roteiro and roteiro in flat
    assert len(body.splitlines()) < 80, "a skill do plugin deve ser fina (o roteiro tem o resto)"
    for t in familia:  # o argumento é a tarefa que disparou a execução
        assert f"`{t.id}`" in flat, t.id
    assert "uma vez só" in flat and "--manual" in flat
    gate = "uv run python -m cdp rotinas gate --tarefa <tarefa>"
    ordem = [_idx(body, "uv sync --frozen --extra dev --extra ai"), _idx(body, gate)]
    if t0.exclusiva:
        assert f"{gate} --adquirir" in body
    else:
        assert "--adquirir" not in body
    if t0.grava:
        ordem += [_idx(body, "uv run python -m cdp sincronizar --executar"),
                  _idx(body, f"`{roteiro}`", ordem[-1]),
                  _idx(body, "uv run python -m cdp publicar --tarefa <tarefa> --mensagem \"CDP: ")]
        pub = re.search(r"`(uv run python -m cdp publicar [^`]+)`", body).group(1)
        assert "--execucao <execucao>" in pub and "--mente claude-code" in pub
        assert ("--trava <trava.id>" in pub) is t0.exclusiva
        assert "**Modo executor:**" in flat and "faça só o passo 4 e o resumo" in flat
    if t0.exclusiva:
        ordem.append(_idx(body, "uv run python -m cdp trava liberar --id <trava.id>", ordem[-1]))
        assert "uv run python -m cdp trava renovar --id <trava.id>" in body
    ordem.append(_idx(body, "Resumo final", ordem[-1]))
    assert ordem == sorted(ordem), ordem
    assert not GIT_GRAVA.search(body.replace("`git` que grave", "")), "git que grave numa skill"
    assert 'action: "publish"' not in body and "Nunca publique artifacts numa rotina" in flat
    assert "docs/cdp/LOCAL.md`, seção 10" in flat  # espelho privado: só o operador
    assert "`python -c`, `jq`, `sleep`" in flat and "laços de espera" in flat


def test_project_skills_are_the_generated_neutral_wrappers():
    """``.claude/skills`` é o espelho exato de ``.agents/skills`` (gerado de rotinas.yaml): a
    nuvem do Claude Code não instala plugins e usa essas skills."""
    gerado = ro.gerar_skills(ROT)
    neutras = {p.parent.name: p for p in sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md"))}
    espelho = {p.parent.name: p for p in _project_skill_files()}
    assert set(espelho) == set(neutras) == {Path(r).parent.name for r in gerado}
    for nome, path in espelho.items():
        assert path.read_bytes() == neutras[nome].read_bytes(), (
            f".claude/skills/{nome} desatualizada: rode "
            "`uv run python -m cdp skills sincronizar --claude`")
        assert _ler(path) == gerado[f".agents/skills/{nome}/SKILL.md"]
    assert {f"cdp-{n}" for n in SKILLS} | {"cdp-retomar"} == set(espelho)
    for nome, path in espelho.items():
        texto = _plano(_ler(path))
        if nome == "cdp-retomar":
            continue
        assert "nunca rode o gate duas vezes" in texto and "Exceção:" in texto
        assert "uv run python -m cdp publicar" in texto or "Não grave arquivos" in texto
        assert not GIT_GRAVA.search(texto.replace("`git` que grave", ""))


# ----------------------------------------------------------------------------- comandos


def _all_commands() -> list[tuple[str, str]]:
    out = []
    for path in _doc_files():
        for c in _commands(_ler(path)):
            out.append((str(path.relative_to(ROOT)), c))
    return out


def test_every_cli_command_in_skills_and_docs_parses():
    cmds = _all_commands()
    assert len(cmds) >= 60
    seen: set[str] = set()
    for where, cmd in cmds:
        if cmd.rstrip().endswith("…"):  # menção genérica ("`uv run python -m cdp …`")
            continue
        argv = _argv(cmd)
        assert argv, f"{where}: comando sem subcomando: {cmd}"
        try:
            args = build_parser().parse_args(argv)
        except SystemExit:  # pragma: no cover - mensagem útil na falha
            pytest.fail(f"{where}: a CLI rejeita `{cmd}`")
        seen.add(args.cmd)
    assert {"agenda", "risk", "validate-daily", "daily", "weekly", "validate", "verify",
            "kill-switch", "backtest", "status", "painel", "tese", "validate-tese", "nota",
            "validate-nota", "mente", "cobertura", "validate-weekly-report", "rotinas",
            "sincronizar", "publicar", "trava", "executor", "estado", "skills",
            "reinicio"} <= seen


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
    assert check["publicavel"] is False and "ausentes" in check["motivo"]  # o falso não grava
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


# ----------------------------------------------------------------------------- roteiros neutros


@pytest.mark.parametrize("nome", ESCRITORES)
def test_writer_playbooks_follow_the_envelope(nome: str):
    """Forma única dos roteiros que gravam: entrada (gate uma vez, com a trava nos escritores
    exclusivos; ``cdp sincronizar``; exceção do modo executor), passos só com a CLI, integridade e
    publicação pelo código (``cdp publicar``), liberação da trava e resumo — sem nenhum ``git``
    que grave e sem artifacts."""
    path = PLAYBOOKS / ROTEIRO[nome]
    texto = _ler(path)
    flat = _plano(texto)
    t0 = _familia(nome)[0]
    assert "## 0. Entrada da execução (uma vez por execução)" in texto
    assert "**Nunca rode o gate de novo na mesma execução.**" in flat
    assert "**Modo executor.**" in flat
    gate = f"uv run python -m cdp rotinas gate --tarefa {t0.id}"
    linhas = _shell_lines(texto)
    assert (f"{gate} --adquirir" in linhas) is t0.exclusiva, linhas
    assert gate in linhas or f"{gate} --adquirir" in linhas
    assert "uv run python -m cdp sincronizar --executar" in linhas
    pub = next(ln for ln in linhas if ln.startswith("uv run python -m cdp publicar"))
    assert f"--tarefa {t0.id}" in pub and '--mensagem "CDP: ' in pub
    assert "--execucao <execucao>" in pub and "--mente <mente>" in pub
    assert ("--trava <trava.id>" in pub) is t0.exclusiva
    tem_liberar = "uv run python -m cdp trava liberar --id <trava.id>" in linhas
    assert tem_liberar is t0.exclusiva
    if t0.exclusiva:
        assert "uv run python -m cdp trava renovar --id <trava.id>" in flat
    # verify antes da publicação; painel só na montagem e no fechamento (sem a cópia local)
    i_pub = _idx(texto, pub)
    assert texto.rfind("uv run python -m cdp verify", 0, i_pub) >= 0
    tem_painel = any(ln.startswith("uv run python -m cdp painel") for ln in linhas)
    assert tem_painel is (nome in ("semanal", "diario")), nome
    if tem_painel:
        assert "uv run python -m cdp painel --sem-local" in linhas
        i_pnl = _idx(texto, "uv run python -m cdp painel --sem-local")
        assert texto.rfind("uv run python -m cdp verify", 0, i_pnl) >= 0 and i_pnl < i_pub
    # só a CLI do CDP: nada de git que grave, nada de comandos que pedem permissão
    for ln in linhas:
        assert ln.split()[0] == "uv", (nome, ln)
    assert not GIT_GRAVA.search(texto), nome
    assert "`python -c`, `jq`, `sleep`" in flat and "laços de espera" in flat
    assert 'action: "publish"' not in texto
    assert "## " in texto and "Resumo final" in texto


def test_status_playbook_is_read_only():
    texto = _ler(PLAYBOOKS / "STATUS.md")
    linhas = _shell_lines(texto)
    assert "uv run python -m cdp rotinas gate --tarefa cdp-status" in linhas
    assert "uv run python -m cdp estado --formato md" in linhas
    for proibido in ("publicar", "sincronizar", "painel", "trava", "kill-switch"):
        assert not any(f"cdp {proibido}" in ln for ln in linhas), proibido
    assert not GIT_GRAVA.search(texto)
    assert "relatorio_semanal.pendentes" in texto


def test_every_task_points_to_a_playbook_with_its_publish_task():
    """Cada tarefa da agenda aponta para um roteiro existente; a skill neutra e a do plugin da
    família apontam para o mesmo roteiro."""
    for t in ROT.tarefas.values():
        assert (ROOT / t.playbook).is_file(), t.id
        nome = t.skill.removeprefix("cdp-")
        assert ROTEIRO[nome] == Path(t.playbook).name
        assert t.plugin == f"/cdp:{nome}"


def test_thesis_step_follows_the_decision_and_precedes_the_painel():
    """Tese da carteira: depois de ``weekly decide`` + ``verify``, antes do painel e da
    publicação; a mente só escreve ``tese.json`` (números via ``{{fact:id}}``); retomada pela
    agenda (``semanal.acao: "tese"`` ou o fechamento, com ``teses_pendentes``)."""
    sem = _ler(PLAYBOOKS / "SEMANAL.md")
    passos = ("uv run python -m cdp tese prepare --week", "uv run python -m cdp validate-tese --week",
              "uv run python -m cdp tese publish --week", "uv run python -m cdp painel --sem-local",
              "uv run python -m cdp publicar --tarefa")
    i_decide = _idx(sem, "uv run python -m cdp weekly decide --week")
    idx = [i_decide, _idx(sem, "uv run python -m cdp verify", i_decide)]
    for s in passos:
        idx.append(_idx(sem, s, idx[-1]))
    assert idx == sorted(idx), idx
    flat = _plano(sem)
    assert re.search(r"Você só escreve .{0,200}book/<semana>/tese/tese\.json", flat)
    assert "docs/cdp/TESE.md" in flat and "fatos.md" in flat
    assert "no máximo 3 tentativas" in flat and 'autoria: "codigo"' in flat
    assert "`tese` → a decisão já está gravada" in flat
    dia = _ler(PLAYBOOKS / "DIARIO.md")
    i_pub = _idx(dia, "uv run python -m cdp daily publish --date")
    idx = [i_pub]
    for s in passos:
        idx.append(_idx(dia, s, idx[-1]))
    assert idx == sorted(idx), idx
    flat = _plano(dia)
    assert "teses_pendentes" in flat and "semanal.semana" in flat
    assert re.search(r"Você só escreve .{0,200}book/<semana>/tese/tese\.json", flat)
    tese = _plano(_ler(DOCS / "TESE.md"))
    for needle in ("tese.json", "fatos.md", "factbook.json", "analise.json", "tese.schema.json",
                   "tese_publicada.json", "tese.md", "WEEKLY_THESIS", "{{fact:", "DADOS SIMULADOS",
                   "Tese de investimento", "autoria", "teses_pendentes"):
        assert needle in tese, needle


@pytest.mark.parametrize("nome", ["SEMANAL.md", "DIARIO.md"])
def test_verify_runs_right_before_the_painel(nome: str):
    """Todo caminho que chega ao painel passa por um ``verify`` logo antes dele (retomada só da
    tese, tese já publicada ou com falha, pré-início)."""
    texto = _ler(PLAYBOOKS / nome)
    linhas = _shell_lines(texto)
    i = linhas.index("uv run python -m cdp painel --sem-local")
    assert linhas[i - 1] == "uv run python -m cdp verify"
    flat = _plano(texto)
    assert "esse `verify` confere a trilha depois da última gravação" in flat


def test_thesis_handoff_draft_is_documented_and_adopted_before_writing():
    """Tese escrita fora do clone das rotinas: entregue em ``docs/cdp/teses/<semana>.json`` (o
    livro tem um só escritor); o ``tese prepare`` a adota e a mente valida antes de escrever."""
    tese = _plano(_ler(DOCS / "TESE.md"))
    assert "## 11. Rascunho entregue fora do clone das rotinas" in tese
    for needle in ("docs/cdp/teses/<semana>.json", "rascunho_entregue", "rascunho_adotado",
                   "byte a byte", "nunca sobrescreve", "nunca publica", "único escritor",
                   "validate-tese` **primeiro**", "FactBook calculado pelo código **da própria",
                   "docs/cdp/teses/README.md"):
        assert needle in tese, needle
    readme = _plano(_ler(TESES / "README.md"))
    for needle in ("`<semana>.json`", "rascunho_adotado", "validate-tese", "docs/cdp/TESE.md",
                   "Nunca faça commit de `book/`"):
        assert needle in readme, needle
    for draft in sorted(TESES.glob("*.json")):  # rascunhos entregues (pode não haver nenhum)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", draft.stem), draft.name
        data = json.loads(draft.read_text(encoding="utf-8"))
        assert data["week"] == draft.stem and data["mind"] in {"claude-code", "codex"}, draft.name
        assert "{{fact:" in data["resumo"]
    sem = _ler(PLAYBOOKS / "SEMANAL.md")
    i_prep = _idx(sem, "uv run python -m cdp tese prepare --week")
    i_flag = _idx(sem, "rascunho_adotado: true", i_prep)
    i_val = _idx(sem, "uv run python -m cdp validate-tese --week", i_flag)
    i_write = _idx(sem, "Escreva `book/<semana>/tese/tese.json`", i_val)
    assert i_prep < i_flag < i_val < i_write  # valida o rascunho antes de escrever
    for doc in ("playbooks/SEMANAL.md", "playbooks/DIARIO.md"):
        flat = _plano(_ler(DOCS / doc))
        assert "docs/cdp/teses/<semana>.json" in flat and "rascunho_adotado" in flat, doc
        assert "**antes de escrever qualquer coisa**" in flat, doc
        assert "docs/cdp/teses/" in flat and "corrija só a cópia no livro" in flat, doc
    for doc in (PLUGIN / "README.md", DOCS / "LOCAL.md"):
        assert "docs/cdp/teses/<semana>.json" in _ler(doc), doc


#: Datas aceitas pelo validador da tese (``guardrails._ALLOWED_NUMERIC_RES``), como documentadas.
THESIS_DATES_OK = ("2026-10-25", "25/10/2026", "25 de outubro", "3T26")
_BARE_DDMM = re.compile(r"(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])")


def test_thesis_docs_list_only_dates_the_validator_accepts():
    """"25/10" não passa no ``validate-tese`` (o dia vira número livre): a documentação não pode
    ensiná-lo, senão a mente gasta as 3 tentativas e a semana fica com o texto do código."""
    from cdp.research.guardrails import find_free_numbers

    for ok in THESIS_DATES_OK:
        assert find_free_numbers(f"Resultado em {ok}.") == [], ok
    assert find_free_numbers("Resultado em 25/10.") == ["25"]
    files = [DOCS / "TESE.md", TESES / "README.md", *_skill_files(), *_playbook_files(),
             DOCS / "ROTINAS.md"]
    for path in files:
        text = _plano(_ler(path))
        for m in _BARE_DDMM.finditer(text):
            ctx = text[max(0, m.start() - 40):m.end() + 40]
            assert "nunca" in ctx or "não" in ctx, (path.name, ctx)  # só como contraexemplo


def test_calibration_is_idempotent_and_never_polls():
    texto = _plano(_ler(PLAYBOOKS / "CALIBRACAO.md"))
    assert "CALIBRACAO_MENSAL.md` de hoje existe, encerre" in texto
    assert "mensal/metrics.json` existe" in texto and "pule o passo 2" in texto
    assert "sem `sleep` nem consultas repetidas" in texto
    skill = _plano(_ler(PLUGIN / "skills" / "calibracao" / "SKILL.md"))
    assert "`run_in_background`" in skill and "encerre o turno sem esperar" in skill
    # sem interface, o script de rotina roda o backtest antes do app (pré-comando da tarefa)
    t = ROT.tarefa("cdp-calibracao")
    assert t.pre_comando and "cdp backtest --start 2021-01-04" in t.pre_comando
    assert "rotinas pre" in _ler(ROOT / "scripts" / "cdp_rotina.sh")
    assert "registrada antes do pré-comando" in (ROOT / "scripts" / "cdp_rotina.ps1").read_text(
        encoding="utf-8-sig")
    assert "`CDP_EXECUCAO`" in skill and "pasta `mensal/`" in skill


def test_runner_registers_the_execution_before_the_pre_command(tmp_path):
    """Sem interface (modo agente), o script roda o backtest antes da mente. A execução é
    registrada ANTES dele (o retrato do gate fica sem a pasta ``mensal/``) e a mente reutiliza
    a mesma execução (``CDP_EXECUCAO``): ``cdp publicar`` leva o backtest com o resumo."""
    import sys

    fake = tmp_path / "bin"
    fake.mkdir()
    registro = tmp_path / "uv.log"
    gate = json.dumps({"executar": True, "motivo": "dia 1", "grava": True, "exclusiva": False,
                       "timeout_min": 240, "execucao": "E1", "trava": None})
    pre = "uv run python -m cdp backtest --start 2021-01-04 --out reports/backtest/2026-11-02/mensal"
    (fake / "uv").write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{registro}"\n'
        f'if [ "$1 $2" = "run python" ] && [ "$3" != "-m" ]; then shift 2; exec "{sys.executable}" "$@"; fi\n'
        f"if [ \"$4 $5 $6\" = \"cdp rotinas gate\" ]; then echo '{gate}'; exit 0; fi\n"
        f'if [ "$4 $5 $6" = "cdp rotinas pre" ]; then echo "{pre}"; exit 0; fi\n'
        'if [ "$4 $5 $6" = "cdp rotinas prompt" ]; then echo "/cdp:calibracao cdp-calibracao"; exit 0; fi\n'
        "exit 0\n")
    marca = tmp_path / "claude.env"
    (fake / "claude").write_text(f'#!/usr/bin/env bash\necho "CDP_EXECUCAO=$CDP_EXECUCAO" > "{marca}"\n')
    for f in fake.iterdir():
        f.chmod(0o755)
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for n in ("cdp_rotina.sh", "cdp_run_task.sh"):
        (repo / "scripts" / n).write_bytes((ROOT / "scripts" / n).read_bytes())
        (repo / "scripts" / n).chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)}
    r = subprocess.run(["bash", str(repo / "scripts/cdp_run_task.sh"), "calibracao",
                        "cdp-calibracao"], env=env, capture_output=True, text=True, timeout=120,
                       check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    chamadas = registro.read_text().splitlines()

    def idx(trecho: str, inicio: int = 0) -> int:
        return next(i for i, c in enumerate(chamadas) if i >= inicio and trecho in c)

    i_previa = idx("rotinas gate --tarefa cdp-calibracao --previa")
    i_registro = next(i for i, c in enumerate(chamadas)
                      if "rotinas gate --tarefa cdp-calibracao" in c and "--previa" not in c)
    assert i_previa < i_registro < idx("cdp backtest --start 2021-01-04") \
        < idx("rotinas prompt --tarefa cdp-calibracao")
    assert marca.read_text().strip() == "CDP_EXECUCAO=E1"  # o gate da mente reutiliza a execução


def test_pre_inception_in_the_playbooks():
    """Pré-início: com ``reinicio.pendente`` o fechamento abre o livro na data de início antes de
    qualquer outra etapa (recusa ⇒ parar); a abertura sai na publicação do fechamento, com o
    sha256 do manifesto na mensagem; antes da data de início a montagem e o risco saem sem
    fazer nada e o fechamento só atualiza a base de mercado e o retrato da cobertura."""
    dia = _ler(PLAYBOOKS / "DIARIO.md")
    flat = _plano(dia)
    i_agenda = _idx(dia, "uv run python -m cdp agenda")
    i_reset = _idx(dia, "uv run python -m cdp reinicio --executar")
    i_close = _idx(dia, "uv run python -m cdp daily close --date AAAA-MM-DD --mind <mente>")
    assert i_agenda < i_reset < i_close
    assert "**antes de qualquer outra etapa**" in flat and "**pare** e relate o `motivo`" in flat
    assert ('"CDP: pré-início — carteira inaugural em DD/MM/AAAA (manifesto sha256: '
            '<lista_sha256>)"') in flat
    assert '`fase: "pre_inicio"`' in flat
    i6 = _idx(dia, "## 6. ")
    i7 = _idx(dia, "## 7. Integridade e painel")
    i_mkt = _idx(dia, "uv run python -m cdp daily close --date AAAA-MM-DD\n", i6)
    assert i_mkt < _idx(dia, "uv run python -m cdp cobertura run --date", i6) < i7
    assert i7 < _idx(dia, "uv run python -m cdp verify", i7) < _idx(dia, "## 8. ")
    sem = _plano(_ler(PLAYBOOKS / "SEMANAL.md"))
    assert "Sem montagem hoje: pré-início" in sem and "reinicio --executar" in sem
    assert sem.index("reinicio --executar") < sem.index("weekly prepare --date")
    risco = _plano(_ler(PLAYBOOKS / "RISCO.md"))
    assert "Sem monitoramento: pré-início" in risco
    assert risco.index("pre_inicio") < risco.index("uv run python -m cdp risk --live")
    for doc in (DOCS / "ROTINAS.md", PLAYBOOKS / "DIARIO.md", PLAYBOOKS / "SEMANAL.md"):
        text = _ler(doc)
        assert "pre_inicio" in text and "reinicio" in text, doc


def test_rebalance_on_the_last_nyse_session_with_the_effective_deadline():
    """Montagem no último pregão da semana na NYSE; prazo efetivo do código; reservas antes do
    prazo; nenhum horário antigo (16:30, 21:30, risco às 16:00) em skills, roteiros e guias."""
    old = re.compile(r"16h30|16:30|12:37|15:07|21:30|21h30|16:00|risco-1600|"
                     r"primeiro pregão da semana na B3")
    files = [*_skill_files(), *_project_skill_files(), PLUGIN / "README.md", DOCS / "ROTINAS.md",
             DOCS / "LOCAL.md", DOCS / "NOTAS.md", *_playbook_files(),
             *(ROOT / "scripts" / n for n in SCRIPTS)]
    for path in files:
        hits = old.findall(path.read_bytes().decode("utf-8-sig"))
        assert not hits, (path.name, hits)
    sem = _plano(_ler(PLAYBOOKS / "SEMANAL.md"))
    assert "último pregão da semana na NYSE" in sem and "`semanal.prazo_efetivo`" in sem
    assert "12:07, 13:07 e 14:07" in sem and "leilão de fechamento" in sem
    for doc in ("ROTINAS.md", "LOCAL.md", "playbooks/SEMANAL.md"):
        text = _plano(_ler(DOCS / doc))
        assert "último pregão da semana na NYSE" in text and "prazo efetivo" in text, doc


def test_friday_night_weekly_reports_and_coverage_snapshot_in_the_daily_playbook():
    """Noite do dia de montagem: um relatório semanal para cada dia de montagem pendente
    (``relatorio_semanal.pendentes``, do mais antigo ao mais recente, inclusive sem decisão
    gravada) e o retrato da cobertura, depois dos fechamentos e antes do verify, do painel e da
    publicação."""
    dia = _ler(PLAYBOOKS / "DIARIO.md")
    flat = _plano(dia)
    i6 = _idx(dia, "## 6. ")
    order = [_idx(dia, "uv run python -m cdp daily publish --date"),
             _idx(dia, "uv run python -m cdp tese publish --week"),
             _idx(dia, "uv run python -m cdp weekly close-report --date AAAA-MM-DD\n", i6),
             _idx(dia, "uv run python -m cdp validate-weekly-report --date", i6),
             _idx(dia, "uv run python -m cdp weekly close-report --date AAAA-MM-DD --publish", i6),
             _idx(dia, "uv run python -m cdp cobertura run --date", i6),
             _idx(dia, "uv run python -m cdp verify", i6),
             _idx(dia, "uv run python -m cdp painel --sem-local"),
             _idx(dia, "uv run python -m cdp publicar --tarefa cdp-diario")]
    assert order == sorted(order), order
    for needle in ("relatorio_semanal.pendentes", "do mais antigo ao mais recente",
                   "**inclusive os dias sem decisão gravada**", "nessa ordem",
                   "cobertura.snapshot_pendente", "cobertura.data",
                   "reports/semanal/<data>/comentario.json", "desde o início",
                   "mudanças da carteira", "carteira mantida", "docs/cdp/ESTILO.md"):
        assert needle in flat, needle
    assert re.search(r"Você só escreve .{0,120}reports/semanal/<data>/comentario\.json", flat)
    skill = _plano(_ler(PLUGIN / "skills" / "diario" / "SKILL.md"))
    assert "do mais antigo ao mais recente, inclusive sem decisão gravada" in skill


def test_cobertura_playbook_writes_only_notes_from_public_sources():
    texto = _ler(PLAYBOOKS / "COBERTURA.md")
    flat = _plano(texto)
    order = [_idx(texto, "uv run python -m cdp nota agenda"),
             _idx(texto, "uv run python -m cdp nota prepare --issuer IID"),
             _idx(texto, "uv run python -m cdp validate-nota --issuer IID --date AAAA-MM-DD"),
             _idx(texto, "uv run python -m cdp nota publish --issuer IID --date AAAA-MM-DD"),
             _idx(texto, "uv run python -m cdp verify"),
             _idx(texto, "uv run python -m cdp publicar --tarefa cdp-cobertura")]
    assert order == sorted(order), order
    assert re.search(r"Você só escreve `book/cobertura/notas/<IID>/<data>/nota\.json`", flat)
    for needle in ("**Só fontes públicas**", "CVM", "SEC EDGAR", "relações com investidores",
                   "Nenhuma base paga", "**dados não confiáveis**", "docs/cdp/ESTILO.md",
                   "docs/cdp/NOTAS.md", "rascunho_adotado: true",
                   "**antes de escrever qualquer coisa**", "docs/cdp/notas/<IID>/<data>.json",
                   'autoria: "codigo"', "no máximo 3 tentativas", "limite_por_execucao",
                   "00:30", '`"codex"` no Codex', "data_nota", "**fonte primária**",
                   "<nota_anterior.data>/nota.md"):
        assert needle in flat, needle
    notas = _plano(_ler(DOCS / "NOTAS.md"))
    for needle in ("COVERAGE_NOTE", "nota_publicada.json", "nota.md", "fatos.md", "{{fact:",
                   "rascunho_adotado", "val.<IID>", "fonte primária", "look-ahead",
                   "DADOS SIMULADOS", "cdp mente pacote", "22:37",
                   "docs/cdp/playbooks/COBERTURA.md"):
        assert needle in notas, needle


def test_risk_playbook_publishes_its_report_and_reports_retained_files():
    """O risco é tarefa compartilhada: publica o relatório (arquivo novo, mesclável); o kill
    switch e o evento da trilha só saem com a trava exclusiva e, sem ela, ficam retidos
    (código 6), relatados em destaque."""
    t = ROT.tarefa("cdp-risco-1330")
    assert not t.exclusiva and t.caminhos == ("reports/risk",)
    assert set(t.caminhos_exclusivos) == {"book/KILL_SWITCH", "book/audit_log.jsonl"}
    flat = _plano(_ler(PLAYBOOKS / "RISCO.md"))
    for needle in ("`retidos`", "código 6", "**Relate `retidos` em destaque no resumo**",
                   "`cdp-risco-1603` às 16h03", "**não** pega a trava", "kill-switch on --reason",
                   "**Nunca** o desligue"):
        assert needle in flat, needle
    assert "kill-switch off" not in " ".join(_ler(p) for p in [*_skill_files(), *_playbook_files()])
    skill = _plano(_ler(PLUGIN / "skills" / "risco" / "SKILL.md"))
    assert "Código 6 em `cdp publicar` (`retidos`)" in skill


def test_routine_paths_cover_what_each_playbook_writes():
    """Quem roda o retrato da cobertura grava ``data/publico``; quem regenera o painel grava
    ``artifacts/painel``: os caminhos da tarefa em rotinas.yaml cobrem isso (``cdp publicar``
    só publica dentro deles)."""
    for t in ROT.tarefas.values():
        texto = _ler(ROOT / t.playbook)
        if "uv run python -m cdp cobertura run" in texto:
            assert "data/publico" in t.caminhos and "book" in t.caminhos, t.id
        if "uv run python -m cdp painel --sem-local\n" in texto:
            assert "artifacts/painel" in t.caminhos, t.id
        if "uv run python -m cdp nota publish" in texto:
            assert any(c in t.caminhos for c in ("book", "book/cobertura")), t.id


def test_coverage_texts_match_the_queue_order():
    """Roteiro, especificação e código descrevem a mesma ordem da fila de notas."""
    from cdp.workflow import notas

    assert notas.GRUPOS_FILA == ("rascunho", "pos_resultado", "vencida", "nota_automatica")
    for path in (PLAYBOOKS / "COBERTURA.md", DOCS / "NOTAS.md"):
        flat = _plano(_ler(path))
        i = [flat.index(w) for w in ("rascunhos entregues", "pós-resultado", "vencidas",
                                     "automática do código")]
        assert i == sorted(i), path
    doc = _plano(notas.__doc__ or "")
    assert doc.index("rascunhos entregues") < doc.index("pós-resultado") < doc.index("SLA")


# ----------------------------------------------------------------------------- guias das rotinas


def test_rotinas_table_is_the_generated_one():
    """A tabela de ``docs/cdp/ROTINAS.md`` é exatamente a de
    ``cdp rotinas exportar --alvo markdown`` (fonte única: ``configs/cdp/rotinas.yaml``)."""
    texto = _ler(DOCS / "ROTINAS.md")
    ini = "<!-- inicio: tabela gerada por `cdp rotinas exportar --alvo markdown` -->\n"
    fim = "<!-- fim da tabela gerada -->"
    tabela = texto[_idx(texto, ini) + len(ini):_idx(texto, fim)]
    assert tabela == ro.exportar_markdown(ROT), (
        "tabela desatualizada: cole a saída de `uv run python -m cdp rotinas exportar --alvo "
        "markdown` em docs/cdp/ROTINAS.md")
    for t in ROT.tarefas.values():
        assert f"`{t.id}`" in tabela and t.quando() in tabela


def test_guides_teach_every_app_step_by_step():
    """Codex (o app das rotinas), Claude Code (rotinas na nuvem ou app desktop) e Gemini
    (Antigravity), passo a passo, com os prompts gerados pelo código; GitHub Actions só para CI
    e portal."""
    rot = _ler(DOCS / "ROTINAS.md")
    flat = _plano(rot)
    for titulo in ("## 3. Claude Code — rotinas na nuvem",
                   "## 4. Claude Code — app desktop",
                   "## 5. Codex — tarefas agendadas do app (o app das rotinas; passo a passo)",
                   "## 6. Gemini — Antigravity (passo a passo)",
                   "## 8. GitHub Actions: só integração contínua e portal"):
        assert titulo in rot, titulo
    for cmd in ("uv run python -m cdp rotinas exportar --alvo claude-routines --formato md",
                "uv run python -m cdp rotinas exportar --alvo claude-desktop",
                "uv run python -m cdp rotinas exportar --alvo codex --formato md",
                "uv run python -m cdp rotinas exportar --alvo gemini --formato md",
                "uv run python -m cdp rotinas exportar --alvo cron --harness agy",
                "uv run python -m cdp rotinas exportar --alvo cron --harness codex",
                "uv run python -m cdp executor registrar --como local-pc --harness codex",
                "uv run python -m cdp executor registrar --como local-pc --harness antigravity"):
        assert cmd in flat, cmd
    for needle in ('sandbox_mode = "danger-full-access"', 'approval_policy = "never"',
                   "[shell_environment_policy] inherit = \"all\" set = { CDP_HARNESS = \"codex\", "
                   "TZ = \"America/Sao_Paulo\", PYTHONUTF8 = \"1\" }",
                   "é fixo (um modelo Flash)", "cada id fica em um só agendador",
                   "uv run python -m cdp skills sincronizar --claude --verificar",
                   "**pasta do projeto** (sem worktree",
                   "acesso total numa conta de usuário e num clone dedicados", "Jules",
                   "18/06/2026", "**Uma vez só por execução.**", "nunca publicam artifacts",
                   "`.claude/skills/cdp-*`", "`.agents/skills/cdp-*`", "docs/cdp/AUTOMACAO.md"):
        assert needle in flat, needle
    local = _plano(_ler(DOCS / "LOCAL.md"))
    for needle in ("Claude Code", "Codex", "Antigravity", "cdp-trava", "com o id da tarefa",
                   "uv run python -m cdp executor registrar --como local-pc --harness claude-code",
                   "docs/cdp/ROTINAS.md`, seção 5", "docs/cdp/ROTINAS.md`, seção 6"):
        assert needle in local, needle
    readme = _plano(_ler(PLUGIN / "README.md"))
    assert "docs/cdp/playbooks/" in readme and "docs/cdp/ROTINAS.md" in readme


def test_local_guide_schedules_backups_and_is_honest_about_prompts():
    local = _ler(DOCS / "LOCAL.md")
    flat = _plano(local)
    for needle in ("cdp-semanal-b", "cdp-semanal-c", "cdp-semanal-d", "12:07", "13:07", "14:07",
                   "cdp-diario-reforco", "21:07", "cdp-diario-sabado", "uma tarefa por vez",
                   "últimos 7 dias", "último pregão da semana na NYSE", "prazo efetivo",
                   "Register-ScheduledTask", "-AllowStartIfOnBatteries",
                   "-DontStopIfGoingOnBatteries", "-StartWhenAvailable", "-WindowStyle Hidden",
                   "feche e reabra o app", "clone dedicado", "revisao_humana",
                   "`dontAsk`) só existe no CLI", "falha fechada", "`main` **e** em `cdp-trava`",
                   "/cdp-diario cdp-diario-reforco", "/cdp:diario cdp-diario-reforco",
                   "kill-switch off", "Keep computer awake", "pc_menos_brasilia_horas"):
        assert needle in flat, needle
    assert "(opcional)" not in local  # o reforço das 21:07 é parte da agenda
    assert "nada fica esperando aprovação" not in flat
    for script in ("cdp_setup_local.sh", "cdp_setup_local.ps1"):
        text = (ROOT / "scripts" / script).read_bytes().decode("utf-8-sig")
        for task in ("cdp-semanal-b", "cdp-semanal-c", "cdp-semanal-d", "cdp-diario-reforco",
                     "cdp-diario-sabado", "cdp-risco-1603", "cdp-cobertura", "cdp-calibracao",
                     "cdp-status"):
            assert task in text, (script, task)
        assert "feche e reabra o app do Claude" in text, script
        assert "executor registrar --como local-pc" in text and "cdp trava ver" in text, script
        assert "--alvo codex --formato md" in text, script


def test_local_guide_documents_the_painel_and_the_private_mirror():
    local = _ler(DOCS / "LOCAL.md")
    assert "## 10. Painel (artifact)" in local
    sec = local[_idx(local, "## 10. Painel (artifact)"):_idx(local, "## 11. ")]
    flat = _plano(sec)
    for needle in ("artifacts/painel/ARTIFACT_URL", "artifacts/painel/index.html",
                   "artifacts/painel/data.json", "artifacts/painel/cdp_painel_local.html",
                   "uv run python -m cdp painel --sem-local", "uv run python -m cdp painel --publicado",
                   "artifacts/painel/PAGINA_PUBLICADA.sha256", "meta.page_sha256",
                   "Página desatualizada", "260 KB", "1.500 caracteres", "meta.truncations",
                   "artifact.publicavel", "arquivos_para_ler", "pagina_mudou", "artifact.publicar",
                   "exige a página em toda publicação", "**Nenhuma rotina sem supervisão publica "
                   "artifacts**", "**sessão interativa do Claude**", "nunca cria um artifact novo",
                   '`<meta name="cdp-page-sha256" content="…">`', "valor `null`",
                   "Nunca use `force`", "Não foi possível carregar os dados do fundo"):
        assert needle in flat, needle
    i_read = _idx(sec, 'action: "read"')
    i_list = _idx(sec, 'action: "list"', i_read)
    i_pub = _idx(sec, 'action: "publish"', i_list)
    assert i_read < i_list < i_pub < _idx(sec, "uv run python -m cdp painel --publicado", i_pub)
    assert '`action: "list"` com `scope: "files"`' in flat


def test_reproduction_guide_covers_audit_recompute_and_any_ai():
    text = _ler(DOCS / "REPRODUZIR.md")
    flat = _plano(text)
    for needle in ("git clone https://github.com/arielassayag/MarketSummary.git", "uv sync",
                   "uv run python -m cdp verify", "uv run python -m cdp cobertura verify",
                   "weekly preview --week", "mente pacote --etapa", "validate-nota",
                   "validate-tese", "uv.lock", "tolerância", "1e-5", "fetch-base",
                   "cobertura run --date", "CVM", "SEC EDGAR", "Banco Central do Brasil",
                   "Damodaran", "ChatGPT", "Gemini", "DADOS SIMULADOS",
                   "docs/cdp/REPLICAR.md", 'docs/cdp/SITE.md`, seção "Conferir uma publicação"'):
        assert needle in flat, needle
    assert "## 8. Conferir o portal e operar a sua cópia" in text
    assert "## Conferir uma publicação" in _ler(DOCS / "SITE.md")
    assert not re.search(r"(?im)^#+ .*\b(english|summary)\b", text)  # sem seção em inglês
    from cdp.workflow.pacote import ETAPAS_PACOTE

    assert all(f"--etapa {e}" in flat for e in ETAPAS_PACOTE)
    # documento para o investidor: sem bastidores de reprocessamento nem carteira anterior
    for banned in ("reinicio", "pré-início", "ensaio", "rebuild", "segunda-feira, 05"):
        assert banned not in text.lower(), banned
    estilo = _ler(DOCS / "ESTILO.md")
    assert "cdp-estilo-" in estilo and "investidor qualificado" in estilo


_EN = re.compile(r"\b(?:the|and|with|should|which|this|that|from|into|when|where|each|every|"
                 r"must|will|would|have|has|are|is)\b")
_CODIGO = re.compile(r"```.*?```|`[^`\n]*`|https?://\S+|<[^>\n]+>", re.S)


#: Textos deste conjunto (skills, roteiros, guias das rotinas e scripts locais).
PROPRIOS = [*_skill_files(), PLUGIN / "README.md", *_playbook_files(), DOCS / "ROTINAS.md",
            DOCS / "LOCAL.md", DOCS / "REPRODUZIR.md", DOCS / "NOTAS.md", DOCS / "ESTILO.md",
            *(ROOT / "scripts" / n for n in SCRIPTS)]


@pytest.mark.parametrize("path", PROPRIOS, ids=lambda p: str(p.relative_to(ROOT)))
def test_owned_texts_are_in_portuguese(path: Path):
    """Skills, roteiros, guias e scripts das rotinas em português: nenhuma seção em inglês e
    nenhuma palavra funcional inglesa fora de código (nomes de menus dos apps e identificadores
    ficam como são)."""
    texto = path.read_bytes().decode("utf-8-sig")
    limpo = _CODIGO.sub(" ", texto)
    if path.suffix in (".sh", ".ps1"):  # só comentários e mensagens
        partes = re.findall(r"#\s(.*)|\"([^\"]*)\"", limpo)
        limpo = "\n".join(a or b for a, b in partes)
    hits = _EN.findall(limpo)
    assert not hits, (path.name, hits[:10])
    assert not re.search(r"(?im)^#+ .*\b(english|summary|overview)\b", texto)


# ----------------------------------------------------------------------------- exportação


def test_in_app_exports_for_codex_and_gemini():
    """Os prompts que se colam no agendador de cada app saem do código: Codex (automações do
    app, RRULE no horário de Brasília, modo Local, acesso total) e Gemini (tarefas agendadas do
    Antigravity, cron de Brasília); a alternativa pelo agendador do sistema vem junto."""
    codex = ro.exportar_codex(ROT)
    assert [a["tarefa"] for a in codex["automacoes_do_app"]] == list(ROT.tarefas)
    for a in codex["automacoes_do_app"]:
        t = ROT.tarefa(a["tarefa"])
        assert a["agenda"] == ro.rrule(t) and a["modo"].startswith("Local")
        assert a["permissoes"] == "Acesso total"
        assert a["prompt"] == ro.prompt(ROT, t.id, harness="codex")
        if t.grava:
            assert "--mind codex" in a["prompt"] and "--mente codex" in a["prompt"]
    assert "scripts/cdp_rotina.sh cdp-diario --harness codex" in codex[
        "alternativa_agendador_do_sistema"]
    gem = ro.exportar_gemini(ROT)
    for i in gem["tarefas_agendadas"]:
        t = ROT.tarefa(i["tarefa"])
        assert i["agenda"] == t.cron and i["fuso"] == "America/Sao_Paulo"
        if t.grava:
            assert "--mind gemini" in i["prompt"]
    assert "--harness agy" in gem["alternativa_agendador_do_sistema"]
    for spec in (codex, gem):
        assert any("executor registrar --como local-pc" in p for p in spec["preparacao"])
        assert "cdp-trava" in " ".join(spec["preparacao"])
    # o Codex só injeta variáveis pela tabela `set` de [shell_environment_policy]
    conf = " ".join(codex["preparacao"])
    assert 'set = { CDP_HARNESS = "codex", TZ = "America/Sao_Paulo", PYTHONUTF8 = "1" }' in conf
    assert 'inherit = "all"' in conf
    assert "modelo fixo" in gem["limites"] and "cdp-status" in gem["limites"]


def test_exports_from_the_cli(capsys):
    from cdp.__main__ import main

    assert main(["rotinas", "exportar", "--alvo", "codex", "--formato", "md"]) == 0
    md = capsys.readouterr().out
    assert md.count("```text\n") == len(ROT.tarefas)
    assert "RRULE:FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=7" in md
    assert main(["rotinas", "exportar", "--alvo", "gemini", "--formato", "md"]) == 0
    md = capsys.readouterr().out
    assert "`37 22 * * 1-4`" in md and "--mind gemini" in md
    assert main(["rotinas", "exportar", "--alvo", "codex"]) == 0
    assert json.loads(capsys.readouterr().out)["automacoes_do_app"]
    # modo plugin com o id da tarefa: o gate confere o horário da tarefa certa
    assert main(["rotinas", "prompt", "--tarefa", "cdp-risco-1603", "--modo", "plugin"]) == 0
    assert capsys.readouterr().out.strip() == "/cdp:risco cdp-risco-1603"
    assert main(["rotinas", "exportar", "--alvo", "claude-desktop"]) == 0
    desk = capsys.readouterr().out
    assert "`/cdp:diario cdp-diario-reforco`" in desk and "`/cdp-risco cdp-risco-1603`" in desk


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
    for needed in ("Bash(uv sync *)", "Bash(uv run python -m cdp *)", "WebSearch", "WebFetch"):
        assert needed in allow, needed
    assert "Bash" not in allow and "Bash(*)" not in allow and "Read" not in allow
    # as skills do CDP, nas formas documentadas (nome exato e nome com argumentos = a tarefa)
    for nome in sorted(SKILLS | {"retomar"}):
        assert f"Skill(cdp-{nome})" in allow and f"Skill(cdp-{nome} *)" in allow, nome
        if nome != "retomar":
            assert f"Skill(cdp:{nome})" in allow and f"Skill(cdp:{nome} *)" in allow, nome
    for blocked in ("Bash(uv run python -m cdp kill-switch off*)", "Bash(git push --force*)",
                    "Bash(git push *--force*)", "Bash(git push --no-verify*)",
                    "Bash(git push * --no-verify*)", "Bash(rm -rf *)",
                    "Edit(/configs/cdp/executor.yaml)", "Edit(/.cdp/**)"):
        assert blocked in deny, blocked
    for humano in ("Bash(uv run python -m cdp executor transferir*)",
                   "Bash(uv run python -m cdp executor registrar*)",
                   "Bash(uv run python -m cdp trava adquirir*)",
                   "Bash(uv run python -m cdp * --sem-trava*)"):
        assert humano in ask, humano
    # toda regra sobre um subcomando do CDP vale nas duas formas (`cdp` também é console script)
    for lista in (ask, deny):
        for r in lista:
            for a, b in (("Bash(uv run python -m cdp ", "Bash(uv run cdp "),
                         ("Bash(uv run cdp ", "Bash(uv run python -m cdp ")):
                if r.startswith(a):
                    assert b + r[len(a):] in lista, f"{r}: falta a forma {b}…"
    # git que grava: nunca pré-aprovado (só `cdp sincronizar`/`cdp publicar` gravam, por dentro)
    git_grava = re.compile(r"Bash\(git (?:\*|add|commit|push|pull|merge|rebase|reset|stash|"
                           r"checkout|restore|clean|rm|mv|tag|cherry-pick|revert|am|apply)\b")
    assert not [r for r in allow if git_grava.match(r)], allow
    for r in ("Bash(git add *)", "Bash(git commit *)", "Bash(git push *)", "Bash(git push)",
              "Bash(git pull *)", "Bash(git pull)", "Bash(git merge *)"):
        assert r in ask, r
    # limites do Bash iguais em todos os ambientes do Claude Code (o `cdp publicar` do risco
    # espera a trava por até 10 minutos e roda com timeout de 15)
    assert int(s["env"]["BASH_DEFAULT_TIMEOUT_MS"]) >= 600_000
    assert int(s["env"]["BASH_MAX_TIMEOUT_MS"]) >= 900_000
    assert ROT.tarefa("cdp-risco-1330").espera_trava_min * 60_000 < 900_000
    assert not any(r.startswith("Write(") for r in allow + ask + deny)  # não consultadas
    a, k, d = _edit_rules(allow), _edit_rules(ask), _edit_rules(deny)
    for mind_file in ("book/2026-10-09/inputs/research_pack.json",
                      "book/2026-10-09/inputs/pm_decision.json",
                      "book/2026-10-09/tese/tese.json",
                      "reports/daily/2026-10-09/comentario.json",
                      "reports/semanal/2026-10-09/comentario.json",
                      "book/cobertura/notas/BR_VALE/2026-10-15/nota.json",
                      "reports/backtest/2026-11-02/CALIBRACAO_MENSAL.md",
                      "artifacts/painel/ARTIFACT_URL"):
        assert _matches(a, mind_file) and not _matches(d, mind_file), mind_file
    for generated in ("artifacts/painel/index.html", "artifacts/painel/data.json",
                      "artifacts/painel/painel-0123456789abcdef.css",
                      "artifacts/painel/painel-0123456789abcdef.js",
                      "artifacts/painel/PAGINA_PUBLICADA.sha256", "configs/cdp/executor.yaml",
                      ".cdp/local.yaml", ".cdp/execucoes/x.json"):
        assert _matches(d, generated) and not _matches(a, generated), generated
    assert not any(r == "Artifact" or r.startswith("Artifact(") for r in allow)
    for generated in ("factbook.json", "fatos.md", "analise.json", "tese.schema.json",
                      "tese_publicada.json", "tese.md"):
        path = f"book/2026-10-09/tese/{generated}"
        assert _matches(d, path) and not _matches(a, path), path
    for code_file in ("book/audit_log.jsonl", "book/KILL_SWITCH",
                      "book/track_record/records/2026-10-09.json",
                      "book/2026-10-09/decision_v1.json", "book/2026-10-09/proposal_v1.json",
                      "book/2026-10-09/config_decisao.json",
                      "book/2026-10-09/booked.json", "book/2026-10-09/briefing/context.json",
                      "book/2026-10-09/research_pack_abc.json",
                      "data/market/base/2026-10-02/manifest.json",
                      "reports/daily/2026-10-09/relatorio.md",
                      "reports/daily/2026-10-09/facts.md",
                      "reports/weekly/2026-10-09/relatorio.md",
                      "reports/risk/2026-10-09/risco_1330.md",
                      "reports/semanal/2026-10-09/relatorio.md",
                      "reports/semanal/2026-10-09/fatos.md",
                      "reports/semanal/2026-10-09/factbook.json",
                      "reports/semanal/2026-10-09/comentario.schema.json",
                      "book/cobertura/livro.jsonl",
                      "book/cobertura/2026-10-09/manifest.json",
                      "book/cobertura/2026-10-09/selo.json",
                      "book/cobertura/2026-10-09/modelos.csv",
                      "book/cobertura/2026-10-09/modelos/BR_VALE.json",
                      "book/cobertura/2026-10-09/insumos/emissores.json.gz",
                      "data/publico/cvm/dfp_2025.zip"):
        assert _matches(d, code_file), code_file
    for generated in ("fatos.md", "factbook.json", "contexto.json", "nota.schema.json",
                      "nota_publicada.json", "nota.md"):
        path = f"book/cobertura/notas/BR_VALE/2026-10-15/{generated}"
        assert _matches(d, path) and not _matches(a, path), path
    assert not any(r.startswith("mcp__") or r.startswith("Mcp") for r in allow + ask + deny)
    assert _matches(k, "configs/cdp/fund.yaml") and not _matches(a, "configs/cdp/fund.yaml")
    assert s["env"]["PYTHONUTF8"] == "1"


def test_monthly_review_file_of_the_mind_is_never_denied():
    """``revisao.json`` (revisão mensal dos modelos) é arquivo da mente: nenhuma regra de
    bloqueio o cobre; os arquivos do pacote são do código."""
    s = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = _edit_rules(s["permissions"]["deny"])
    assert not _matches(deny, "book/cobertura/revisoes/2026-10-30/revisao.json")
    dia = _plano(_ler(PLAYBOOKS / "DIARIO.md"))
    assert re.search(r"Você só escreve .{0,400}book/cobertura/revisoes/<data>/revisao\.json", dia)


def test_settings_never_deny_a_mind_editable_file():
    """Bloqueio vence permissão: nenhuma regra de bloqueio pode cobrir um arquivo da mente."""
    s = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = _edit_rules(s["permissions"]["deny"])
    samples = {"*": "2026-10-09", "**": "x/y.md"}
    for rule in s["permissions"]["allow"]:
        if not (rule.startswith("Edit(") and rule.endswith(")")):
            continue
        path = rule[6:-1]
        concrete = re.sub(r"\*\*|\*", lambda m: samples[m.group(0)], path)
        assert not _matches(deny, concrete), (rule, concrete)


def test_settings_deny_every_code_written_coverage_file(tmp_path):
    """Todo arquivo que o retrato da cobertura grava no livro é bloqueado para a mente (o único
    arquivo editável da cobertura é ``nota.json``)."""
    import warnings
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from cdp.config import load_config
    from cdp.data.synthetic import make_synthetic_market
    from cdp.workflow.demo import (
        DEMO_FIRST_WEEK,
        DEMO_HISTORY_START,
        DEMO_SEED,
        DemoStore,
        demo_sessions,
        run_demo,
    )
    from cdp.workflow.runtime import Runtime

    try:
        from cdp.cobertura.demo import gerar
    except ImportError as exc:  # pragma: no cover - motor da cobertura ausente
        pytest.skip(f"cobertura indisponível: {exc!r}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_demo(tmp_path, days=1)
    market = make_synthetic_market(seed=DEMO_SEED, start=DEMO_HISTORY_START,
                                   as_of=demo_sessions(1)[-1])
    rt = Runtime(load_config(), tmp_path / "book", tmp_path / "market", tmp_path / "reports",
                 store_override=DemoStore(market), teses_root=None,
                 clock=lambda: datetime(2024, 3, 4, 21, 30, tzinfo=ZoneInfo("America/Sao_Paulo")))
    gerar(rt, [DEMO_FIRST_WEEK])
    written = sorted(p.relative_to(tmp_path).as_posix()
                     for p in (tmp_path / "book" / "cobertura").rglob("*") if p.is_file())
    assert written, "o retrato sintético não gravou nada"
    s = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = _edit_rules(s["permissions"]["deny"])
    allow = _edit_rules(s["permissions"]["allow"])
    for rel in written:
        assert _matches(deny, rel), f"arquivo do código sem bloqueio: {rel}"
        assert not _matches(allow, rel), rel


# ----------------------------------------------------------------------------- scripts e repo


def test_local_scripts_exist_and_delegate_to_the_routine_runner():
    """``cdp_run_task.*`` são atalhos do Claude Code com o plugin sobre o script de rotina
    (``--modo-prompt plugin``, com o id da tarefa); ``cdp_setup_local.*`` registram a identidade
    do clone e testam o push e a trava."""
    for name in SCRIPTS:
        path = ROOT / "scripts" / name
        assert path.is_file(), name
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        if name.endswith(".ps1"):
            assert raw.startswith(b"\xef\xbb\xbf"), f"{name}: UTF-8 com BOM (PowerShell 5.1)"
            assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in text
        else:
            assert text.startswith("#!/usr/bin/env bash") and "\r\n" not in text
            assert subprocess.run(["bash", "-n", str(path)], check=False).returncode == 0
            if os.name == "posix":
                assert os.access(path, os.X_OK), f"{name} sem permissão de execução"
        if "run_task" in name:
            assert "cdp_rotina" in text and "claude" in text and "plugin" in text
            # quem chama o app é o script de rotina (nenhuma chamada direta do claude aqui)
            assert not re.search(r'^\s*(?:&\s*\$\w+|"\$\w+"|claude)\s+-p\b', text, re.M)
            assert "--bare" not in text
            for t in ("cdp-semanal-b", "cdp-diario-sabado", "cdp-risco-1603"):
                assert t in text, (name, t)
        else:
            assert "uv sync --extra dev --extra ai" in text
            assert "cdp@cdp-cabra-da-peste" in text
    sh = (ROOT / "scripts" / "cdp_run_task.sh").read_text(encoding="utf-8")
    assert 'exec bash "$ROOT/scripts/cdp_rotina.sh" "$TAREFA" --harness claude --modo-prompt plugin' in sh
    ps = (ROOT / "scripts" / "cdp_run_task.ps1").read_bytes().decode("utf-8-sig")
    assert "& $rotina $Tarefa -Harness claude -ModoPrompt plugin @extra" in ps


def _uv_falso(pasta: Path, registro: Path) -> None:
    """``uv`` de mentira: registra a chamada; a prévia do gate manda executar."""
    (pasta / "uv").write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{registro}"\n'
        'case "$*" in\n'
        '  *"rotinas gate"*) echo \'{"executar": true, "motivo": "ok", "grava": true}\' ;;\n'
        '  *"rotinas prompt"*) echo "/cdp:risco cdp-risco-1603" ;;\n'
        "esac\n"
        "exit 0\n")
    (pasta / "uv").chmod(0o755)


def test_run_task_wrapper_calls_the_runner_with_the_task(tmp_path):
    """``cdp_run_task.sh risco cdp-risco-1603 --seco`` vira o script de rotina com o harness
    Claude, o prompt do plugin e o id da tarefa (nada roda de verdade: ``--seco``)."""
    fake = tmp_path / "bin"
    fake.mkdir()
    registro = tmp_path / "uv.log"
    _uv_falso(fake, registro)
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for n in ("cdp_rotina.sh", "cdp_run_task.sh"):
        (repo / "scripts" / n).write_bytes((ROOT / "scripts" / n).read_bytes())
        (repo / "scripts" / n).chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)}
    r = subprocess.run([str(repo / "scripts/cdp_run_task.sh"), "risco", "cdp-risco-1603",
                        "--seco"], env=env, capture_output=True, text=True, timeout=60,
                       check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "harness: claude" in r.stdout and "publicacao: agente" in r.stdout
    chamadas = registro.read_text(encoding="utf-8")
    assert "rotinas prompt --tarefa cdp-risco-1603 --harness claude --modo plugin" in chamadas
    r = subprocess.run([str(repo / "scripts/cdp_run_task.sh"), "risco", "cdp-diario"],
                       env=env, capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 2  # tarefa de outra família
    r = subprocess.run([str(repo / "scripts/cdp_run_task.sh"), "marte"], env=env,
                       capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 2


def test_painel_folder_exists():
    """``artifacts/painel`` existe no repositório (o painel é regenerado pelas rotinas)."""
    assert (ROOT / "artifacts" / "painel" / ".gitkeep").is_file()


def test_repo_files_for_local_operation():
    assert "logs/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for line in ("book/** -text", "data/** -text", "reports/** -text"):
        assert line in attrs
    local = _ler(DOCS / "LOCAL.md")
    for needle in ("claude plugin marketplace add", "claude plugin install cdp@cdp-cabra-da-peste",
                   "/cdp-diario cdp-diario", "Worktree", "kill-switch off", "launchd",
                   "Register-ScheduledTask", "--harness codex", "--harness antigravity",
                   "scripts/cdp_rotina.sh", "scripts/cdp_run_task.sh"):
        assert needle in local, needle


def test_no_model_identifiers_in_local_operation_files():
    files = [MARKETPLACE, *PLUGIN.rglob("*"), ROOT / ".claude" / "settings.json",
             *_project_skill_files(), DOCS / "LOCAL.md", DOCS / "ROTINAS.md",
             *_playbook_files(), *(ROOT / "scripts" / n for n in SCRIPTS)]
    for path in files:
        if path.is_file():
            hits = MODEL_RE.findall(path.read_bytes().decode("utf-8-sig"))
            assert not hits, f"{path}: {hits}"


def _arquivos_do_repositorio(pastas: tuple[str, ...]) -> list[Path]:
    """Arquivos versionados ou novos (não ignorados) nas pastas, pelo git: fora ficam os
    worktrees de outras sessões em ``.claude/worktrees/`` (ignorados) e os ambientes locais. Sem
    git, varre as pastas pulando ``.git``, ``.venv`` e ``worktrees``."""
    r = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                        "--", *pastas], cwd=ROOT, capture_output=True, check=False)
    if r.returncode == 0:
        nomes = [n for n in r.stdout.decode("utf-8", "surrogateescape").split("\0") if n]
        return [ROOT / n for n in nomes if (ROOT / n).is_file()]
    fora = {".git", ".venv", "worktrees", "node_modules"}
    return [p for d in pastas if (ROOT / d).exists() for p in (ROOT / d).rglob("*")
            if p.is_file() and not fora & set(p.relative_to(ROOT).parts)]


def test_no_skill_or_setting_depends_on_a_proprietary_tool():
    for path in [*_skill_files(), *_project_skill_files()]:
        tools = _frontmatter(path).get("allowed-tools", [])
        assert not any(t.startswith("mcp__") for t in tools), (path, tools)
    removed = "quar" + "tr"  # canal proprietário removido (o termo não aparece no repositório)
    pastas = ("src", "docs", "plugins", ".claude", "scripts", "tests", "configs", ".claude-plugin",
              ".agents")
    sufixos = {".py", ".md", ".json", ".yaml", ".yml", ".csv", ".sh", ".ps1", ".toml", ".txt",
               ".html", ".js", ".css"}
    files = [p for p in _arquivos_do_repositorio(pastas) if p.suffix in sufixos]
    files += [ROOT / n for n in ("AGENTS.md", "CLAUDE.md", "README.md", "pyproject.toml",
                                 ".gitignore") if (ROOT / n).is_file()]
    hits = [str(p.relative_to(ROOT)) for p in files
            if removed in p.read_bytes().decode("utf-8", "ignore").lower()]
    assert hits == []
