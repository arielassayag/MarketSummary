"""Consistência da documentação do CDP com o código (integração de conhecimento, agnóstica ao app).

- Todo comando ``cdp …`` citado no ``AGENTS.md``, nos adaptadores (``CLAUDE.md``, ``GEMINI.md``),
  nos roteiros, nas skills (neutras, espelho do Claude e plugin) e nos documentos de integração
  existe no parser real (comando e subcomando); todo comando completo
  (``uv run python -m cdp …``) desses arquivos e de ``docs/cdp/`` — entre crases ou em blocos de
  código — passa pelo parser (nos documentos de integração, sem tolerar argumento faltando).
- Todo link relativo e todo caminho do repositório citado entre crases resolve.
- Nenhuma fonte proprietária removida é citada em texto do repositório — inclusive ``artifacts/``,
  ``reports/`` e o livro a partir da data de início; só ficam de fora o histórico anterior à data
  de início (encadeado por hash), os dados brutos de terceiros e uma exceção nominal — e nenhuma
  ferramenta paga de dados é citada no texto operacional do CDP.
- ``configs/cdp/rotinas.yaml`` × roteiros × skills × plugin × ``AGENTS.md`` × ``AUTOMACAO.md``.
- Os documentos de integração estão em português (heurística de palavras funcionais), sem
  seção em inglês e sem a regra antiga do dia de montagem.
- Licenças (propostas), ``NOTICE`` e o mesmo aviso legal fixo em README, REPLICAR e
  LICENSE-docs; a cópia do projeto sabe onde trocar endereço e marca; o rascunho de ativação do
  mandato, enquanto existir, carrega como configuração válida; o leitor que só tem o
  ``AGENTS.md`` sabe o que rodar agora, como publicar e o que nunca fazer.

Tudo offline e só de leitura.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex
import subprocess
from datetime import date
from functools import cache
from pathlib import Path

import pytest
import yaml

from cdp import rotinas as ro
from cdp.__main__ import build_parser

ROOT = Path(__file__).resolve().parents[2]
ROT = ro.carregar(ROOT / "configs" / "cdp" / "rotinas.yaml")

#: Documentos de integração (donos: integração) — conferidos com rigor máximo.
INTEGRACAO = ("AGENTS.md", "README.md", "docs/cdp/ARQUITETURA.md", "docs/cdp/AGENTE.md",
              "docs/cdp/AUTOMACAO.md", "docs/cdp/REPLICAR.md", "docs/cdp/EM_ANDAMENTO.md",
              "docs/cdp/DECISOES.md")
#: Dados brutos de terceiros e saídas locais do app Fechamento: fora da varredura de termos.
FORA_DA_VARREDURA = ("data/", "outputs/")
#: Áreas do executor em que só o histórico anterior à data de início (encadeado por hash, removido
#: da árvore pelo pré-início) fica fora da varredura de termos.
HISTORICO = ("book/", "pesquisa/", "reports/")
#: Exceções nominais (arquivo → motivo); cada uma tem pendência em docs/cdp/EM_ANDAMENTO.md.
LEGADO = {
    "artifacts/painel/cdp_painel_local.html": "painel local antigo, não mais regravado pelas "
    "rotinas (`cdp painel --sem-local`); sai da árvore no clone do executor",
}
INICIO = date.fromisoformat(str(yaml.safe_load(
    (ROOT / "configs" / "cdp" / "fund.yaml").read_text(encoding="utf-8"))["fund"]["inception_date"]))
_DATA_NO_CAMINHO = re.compile(r"(?:^|/)(\d{4}-\d{2}-\d{2})(?:/|$)")
TEXTO = {".md", ".py", ".yaml", ".yml", ".json", ".toml", ".txt", ".sh", ".ps1", ".html",
         ".js", ".css", ".csv", ".j2", ".cfg", ".ini", ""}


# ------------------------------------------------------------------------------ utilidades


@cache
def _arquivos_versionados() -> tuple[str, ...]:
    """Arquivos do repositório (versionados e novos não ignorados); sem git, varre a árvore."""
    try:
        r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                           cwd=ROOT, capture_output=True, check=True)
        nomes = [n for n in r.stdout.decode("utf-8").split("\0") if n]
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - sem git
        nomes = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                 if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts]
    return tuple(sorted(n for n in nomes if (ROOT / n).is_file()))


def _ler(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _docs_operacionais() -> list[str]:
    """AGENTS.md, adaptadores, roteiros e skills (onde um agente lê o que rodar)."""
    rels = ["AGENTS.md", "CLAUDE.md", "GEMINI.md"]
    for padrao in ("docs/cdp/playbooks/*.md", ".agents/skills/*/SKILL.md",
                   ".claude/skills/*/SKILL.md", "plugins/cdp/skills/*/SKILL.md"):
        rels += sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob(padrao))
    return rels


_CERCA = re.compile(r"^\s*```")


def _trechos_de_codigo(texto: str) -> list[str]:
    """Trechos entre crases e linhas de blocos de código (onde ficam comandos e caminhos)."""
    trechos = re.findall(r"`([^`\n]+)`", texto)
    dentro = False
    for linha in texto.splitlines():
        if _CERCA.match(linha):
            dentro = not dentro
            continue
        if dentro:
            trechos.append(linha)
    return trechos


@cache
def _arvore_cli() -> dict[str, frozenset[str] | None]:
    """Comando → subcomandos (ou escolhas do 1º posicional); ``None`` = sem subcomando."""
    arvore: dict[str, frozenset[str] | None] = {}
    raiz = build_parser()
    sub = next(a for a in raiz._actions if isinstance(a, argparse._SubParsersAction))
    for nome, p in sub.choices.items():
        filhos: set[str] = set()
        for a in p._actions:
            if isinstance(a, argparse._SubParsersAction):
                filhos |= set(a.choices)
            elif not a.option_strings and a.choices and a.dest not in ("help",):
                filhos |= {str(c) for c in a.choices}
        arvore[nome] = frozenset(filhos) if filhos else None
    return arvore


_MENCAO = re.compile(r"(?<![\w/:.@-])cdp\s+([a-z][a-z0-9-]*)((?:\s+[^\s`]+)?)")
_PALAVRA = re.compile(r"^[a-z][a-z0-9-]*(\|[a-z][a-z0-9-]*)*$")


def _mencoes_cli(texto: str) -> list[tuple[str, str | None]]:
    out = []
    for trecho in _trechos_de_codigo(texto):
        for m in _MENCAO.finditer(trecho):
            seguinte = m.group(2).strip() or None
            out.append((m.group(1), seguinte))
    return out


def _parse_completo(cmd: str) -> None:
    cmd = cmd.split(" #")[0]
    for sep in ("&&", ";", "|"):
        cmd = cmd.split(sep)[0]
    cmd = re.sub(r"<[^<>]+>", "X", cmd.replace("AAAA-MM-DD", "2026-10-09"))
    toks = shlex.split(cmd)
    assert toks[:5] == ["uv", "run", "python", "-m", "cdp"], cmd
    build_parser().parse_args(toks[5:])


_EN = frozenset("""the and of to is are be been being it its this that these those with from by on at
an when which if then than into only each every all any have has had will would can could should
must not or but we you your our they their there here where what how why does did was were also such
same other more most may might after before without within between about over under while because
using uses run runs returns instead per already still yet both either neither just like keep keeps
makes see never always""".split())
_PT = frozenset("""os da das dos é em na nos nas um uma uns umas para com por que não ao aos à às mais
ou quando só como sem pelo pela pelos pelas ser são foi este esta estes estas isso isto cada todo
toda todos todas entre sobre até depois antes também já ainda nunca sempre deve devem pode podem
fica ficam está estão seu sua seus suas quem qual quais onde porque mesmo mesma outra outro
outras outros""".split())
_RUIDO = re.compile(r"```.*?```|`[^`]*`|https?://\S+|\{\{[^}]*\}\}|<[^>\n]+>", re.S)
_PALAVRAS = re.compile(r"[A-Za-zÀ-ÿ']+")


def _contagem(texto: str) -> tuple[int, int, int]:
    palavras = [w.lower() for w in _PALAVRAS.findall(texto)]
    return (sum(w in _EN for w in palavras), sum(w in _PT for w in palavras), len(palavras))


# ------------------------------------------------------------------------- comandos da CLI


def test_cli_tree_has_the_operational_commands():
    arvore = _arvore_cli()
    for cmd in ("estado", "agenda", "rotinas", "executor", "trava", "sincronizar", "publicar",
                "entrega", "site", "skills", "cobertura", "nota", "mente", "reinicio", "weekly"):
        assert cmd in arvore, cmd
    assert {"gate", "prompt", "exportar"} <= arvore["rotinas"]
    assert {"close-report", "prepare", "decide"} <= arvore["weekly"]
    assert {"close", "publish"} <= arvore["daily"]


@pytest.mark.parametrize("doc", [*_docs_operacionais(), *INTEGRACAO])
def test_every_cdp_command_mentioned_exists_in_the_parser(doc: str):
    arvore = _arvore_cli()
    for cmd, seguinte in _mencoes_cli(_ler(doc)):
        assert cmd in arvore, f"{doc}: `cdp {cmd}` não existe na CLI"
        filhos = arvore[cmd]
        if filhos and seguinte and _PALAVRA.match(seguinte):
            for alt in seguinte.split("|"):
                assert alt in filhos, f"{doc}: `cdp {cmd} {alt}` não existe na CLI"


@pytest.mark.parametrize("doc", INTEGRACAO)
def test_full_commands_in_integration_docs_parse(doc: str):
    for c in re.findall(r"`(uv run python -m cdp [^`]+)`", _ler(doc)):
        _parse_completo(c)


_CMD_COMPLETO = re.compile(r"(uv run (?:--[\w-]+ \S+ )*python -m cdp\b.*)$")


def _comandos_completos(texto: str) -> list[str]:
    """``uv run … python -m cdp …`` entre crases e nas linhas de blocos de código (com ``\\``
    de continuação)."""
    out = re.findall(r"`(uv run (?:--[\w-]+ \S+ )*python -m cdp [^`]+)`", texto)
    dentro, buf = False, ""
    for linha in texto.splitlines():
        if _CERCA.match(linha):
            dentro, buf = not dentro, ""
            continue
        if not dentro:
            continue
        lin = f"{buf} {linha.strip()}".strip() if buf else linha.strip()
        buf = ""
        if lin.endswith("\\"):
            buf = lin[:-1].strip()
            continue
        m = _CMD_COMPLETO.search(lin)
        if m:
            out.append(m.group(1))
    return out


def _docs_com_comandos() -> list[str]:
    rels = {*_docs_operacionais(), *INTEGRACAO, "plugins/cdp/README.md"}
    rels |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "docs" / "cdp").rglob("*.md")}
    return sorted(r for r in rels if (ROOT / r).is_file())


@pytest.mark.parametrize("doc", _docs_com_comandos())
def test_every_full_cdp_command_in_the_docs_parses(doc: str):
    """Opções e subcomandos existem; espaço reservado (``<…>``) e argumento obrigatório omitido
    num exemplo são tolerados — opção desconhecida ou subcomando inexistente, não."""
    for c in _comandos_completos(_ler(doc)):
        cmd = re.sub(r"<[^<>]+>", "X", c.replace("AAAA-MM-DD", "2026-10-09"))
        cmd = cmd.split(" #")[0]
        for sep in ("&&", ";", "|", " 2>", " >"):
            cmd = cmd.split(sep)[0]
        if re.search(r"[…$\[{]|\.\.\.", cmd):
            continue
        toks = shlex.split(cmd)
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                build_parser().parse_args(toks[toks.index("cdp") + 1:])
        except SystemExit as exc:
            msg = err.getvalue()
            tolerado = ("are required" in msg or "invalid choice: 'X'" in msg
                        or re.search(r"invalid \w+ value: 'X'", msg))
            assert not exc.code or tolerado, f"{doc}: `{c}` → {msg.strip().splitlines()[-1:]}"


def test_architecture_covers_every_top_level_command():
    arq = _ler("docs/cdp/ARQUITETURA.md")
    faltam = [c for c in _arvore_cli() if not re.search(rf"\bcdp {re.escape(c)}\b", arq)]
    assert faltam == [], f"ARQUITETURA.md sem linha para: {faltam}"


# ------------------------------------------------------------------------------- links


_LINK_MD = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_CAMINHO = re.compile(r"^(?:docs|configs|scripts|src|plugins|tests|site|\.agents|\.claude|\.github|"
                      r"\.gemini)/[\w./-]*$|^(?:AGENTS|CLAUDE|GEMINI|README)\.md$|"
                      r"^(?:LICENSE(?:-docs)?|NOTICE)$")


def _docs_com_links() -> list[str]:
    rels = {*_docs_operacionais(), *INTEGRACAO}
    rels |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "docs" / "cdp").glob("*.md")}
    rels |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "docs" / "cdp" / "marca").glob("*.md")}
    return sorted(rels)


@pytest.mark.parametrize("doc", _docs_com_links())
def test_relative_links_and_repository_paths_resolve(doc: str):
    texto = _ler(doc)
    base = (ROOT / doc).parent
    for alvo in _LINK_MD.findall(texto):
        if re.match(r"^(?:[a-z]+:|#|mailto:)", alvo):
            continue
        caminho = alvo.split("#")[0]
        if caminho:
            assert (base / caminho).exists(), f"{doc}: link quebrado {alvo}"
    for trecho in re.findall(r"`([^`\s]+)`", texto):
        t = trecho.rstrip(".,;:")
        if not _CAMINHO.match(t) or re.search(r"[<>{}*…$]|AAAA|\.\.\.", t):
            continue
        assert (ROOT / t.rstrip("/")).exists(), f"{doc}: caminho inexistente `{t}`"


def test_agents_md_maps_every_doc_and_playbook():
    agents = _ler("AGENTS.md")
    for p in sorted((ROOT / "docs" / "cdp").glob("*.md")):
        assert f"docs/cdp/{p.name}" in agents, f"AGENTS.md não aponta para docs/cdp/{p.name}"
    for p in sorted((ROOT / "docs" / "cdp" / "playbooks").glob("*.md")):
        assert p.name in agents, f"AGENTS.md não aponta para o roteiro {p.name}"
    for n in ("LICENSE", "LICENSE-docs", "NOTICE", "docs/cdp/marca/IDENTIDADE.md"):
        assert n in agents, n


# ------------------------------------------------------------------------ termos proibidos

_REMOVIDO = "quar" + "tr"  # canal de dados proprietário removido (o termo não aparece no texto)
_FERRAMENTAS_PAGAS = ("bloomberg terminal", "terminal bloomberg", "fact" + "set", "capital iq",
                      "refini" + "tiv", "eik" + "on", "lseg workspace", "econo" + "matica",
                      "visible alpha", "alpha" + "sense", "dalo" + "opa", "teg" + "us", "koy" + "fin")
_OPERACIONAL = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", "LICENSE-docs", "docs/cdp/",
                ".agents/", ".claude/", ".claude-plugin/", ".gemini/", "plugins/", "configs/cdp/",
                "scripts/cdp_", "src/cdp/", "site/", ".github/")


def _historico_anterior_ao_inicio(rel: str) -> bool:
    """Livro, pesquisa e relatórios com data anterior à data de início do mandato."""
    if not rel.startswith(HISTORICO):
        return False
    m = _DATA_NO_CAMINHO.search(rel)
    return bool(m) and date.fromisoformat(m.group(1)) < INICIO


def _texto_do_repositorio(prefixos: tuple[str, ...] | None = None) -> list[tuple[str, str]]:
    out = []
    for rel in _arquivos_versionados():
        if (rel.startswith(FORA_DA_VARREDURA) or rel in LEGADO or _historico_anterior_ao_inicio(rel)
                or Path(rel).suffix.lower() not in TEXTO):
            continue
        if prefixos is not None and not rel.startswith(prefixos):
            continue
        try:
            out.append((rel, (ROOT / rel).read_text(encoding="utf-8").lower()))
        except (UnicodeDecodeError, OSError):
            continue
    return out


def test_removed_proprietary_source_is_not_mentioned_anywhere():
    hits = [rel for rel, txt in _texto_do_repositorio() if _REMOVIDO in txt]
    assert hits == [], hits


def test_term_scan_covers_outputs_and_the_live_book():
    assert not _historico_anterior_ao_inicio("book/2026-10-16/inputs/research_pack.json")
    assert not _historico_anterior_ao_inicio("book/cobertura/notas/BR_VALE/2026-10-15/nota.json")
    assert not _historico_anterior_ao_inicio("reports/semanal/2026-10-09/comentario.json")
    assert _historico_anterior_ao_inicio("pesquisa/2026-10-05/research_pack_final.json")
    assert not "artifacts/painel/index.html".startswith(FORA_DA_VARREDURA)
    for rel in LEGADO:  # exceção nominal só enquanto o arquivo existir na árvore
        assert rel.startswith("artifacts/"), rel


def test_operational_text_names_no_paid_data_tool():
    hits = [(rel, f) for rel, txt in _texto_do_repositorio(_OPERACIONAL)
            for f in _FERRAMENTAS_PAGAS if re.search(rf"\b{re.escape(f)}\b", txt)]
    assert hits == [], hits


# ------------------------------------------------- rotinas × roteiros × skills × documentos


def _frontmatter(path: Path) -> tuple[dict, str]:
    texto = path.read_text(encoding="utf-8")
    assert texto.startswith("---\n"), path
    fim = texto.index("\n---\n", 4)
    return yaml.safe_load(texto[4:fim]), texto[fim + 5:]


def test_routines_playbooks_and_skills_are_consistent():
    neutras = ROOT / ".agents" / "skills"
    usados: set[str] = set()
    skills_das_tarefas: set[str] = set()
    for t in ROT.tarefas.values():
        assert (ROOT / t.playbook).is_file(), (t.id, t.playbook)
        usados.add(Path(t.playbook).name)
        skills_das_tarefas.add(t.skill)
        sk = neutras / t.skill / "SKILL.md"
        assert sk.is_file(), (t.id, sk)
        fm, corpo = _frontmatter(sk)
        assert fm["name"] == t.skill
        assert fm["metadata"]["playbook"] == t.playbook and t.playbook in corpo, t.id
        assert t.id in fm["metadata"]["tarefas"].split(), t.id
        if t.plugin:
            assert re.fullmatch(r"/cdp:[a-z]+", t.plugin), t.plugin
            assert (ROOT / "plugins/cdp/skills" / t.plugin.split(":")[1] / "SKILL.md").is_file()
    roteiros = {p.name for p in (ROOT / "docs/cdp/playbooks").glob("*.md")}
    agents = _ler("AGENTS.md")
    assert "RETOMAR.md" in roteiros - usados
    for r in sorted(roteiros - usados):  # roteiros de sessão: mapeados no AGENTS.md
        assert r in agents, f"roteiro {r} sem tarefa e fora do mapa do AGENTS.md"
    nomes = {p.name for p in neutras.iterdir() if p.is_dir()}
    assert nomes == skills_das_tarefas | {"cdp-retomar"}, nomes
    for sk in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        nome = sk.parent.name
        assert nome in nomes, f".claude/skills/{nome} sem skill neutra correspondente"
        if nome != "cdp-retomar":
            playbook = next(t.playbook for t in ROT.tarefas.values() if t.skill == nome)
            assert playbook in sk.read_text(encoding="utf-8"), (nome, playbook)


def test_automacao_schedules_match_rotinas_yaml():
    texto = _ler("docs/cdp/AUTOMACAO.md")
    for t in ROT.tarefas.values():
        assert f"`{ro.rrule(t)}`" in texto, (t.id, ro.rrule(t))
        assert f"`{t.cron_utc}`" in texto, (t.id, t.cron_utc)
        assert f"`{t.id}`" in texto, t.id
    assert ro.exportar_markdown(ROT) in _ler("AGENTS.md")


# ----------------------------------------------------------------------------- idioma


@pytest.mark.parametrize("doc", [*INTEGRACAO, "LICENSE-docs"])
def test_integration_docs_are_in_portuguese(doc: str):
    texto = _ler(doc)
    limpo = _RUIDO.sub(" ", texto)
    blocos = [b for b in re.split(r"\n\s*\n|\n(?=\|)|\n(?=- )|\n(?=\d+\. )", limpo) if b.strip()]
    suspeitos = []
    for b in blocos:
        en, pt, n = _contagem(b)
        if n >= 6 and en >= 3 and en > pt:
            suspeitos.append(" ".join(b.split())[:120])
    assert suspeitos == [], f"{doc}: trechos em inglês: {suspeitos}"
    en, pt, _ = _contagem(limpo)
    assert en <= 0.05 * (en + pt), (doc, en, pt)
    for linha in texto.splitlines():
        if linha.startswith("#"):
            assert not re.search(r"(?i)\b(english|summary|overview|getting started)\b", linha), linha


@pytest.mark.parametrize("doc", INTEGRACAO)
def test_integration_docs_have_no_old_rebalance_rule(doc: str):
    texto = " ".join(_ler(doc).split()).lower()
    for antigo in ("rebalanceamento semanal (segunda", "fluxo semanal (segunda",
                   "primeiro pregão da semana", "decisão final do gestor humano"):
        assert antigo not in texto, (doc, antigo)


def test_generated_prompts_and_skill_descriptions_are_in_portuguese():
    for t in ROT.tarefas.values():
        for h in ("claude", "codex", "gemini"):
            en, pt, _ = _contagem(_RUIDO.sub(" ", ro.prompt(ROT, t.id, harness=h)))
            assert en <= 2 and pt > 10 * max(en, 1), (t.id, h, en, pt)
    for sk in sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md")):
        fm, _ = _frontmatter(sk)
        en, pt, _ = _contagem(fm["description"])
        assert en <= 1 and pt >= 3, (sk, en, pt)


# --------------------------------------------------------------- licenças e aviso legal


_AVISO = re.compile(r"O CDP é uma carteira simulada .*? Resultados simulados não garantem "
                    r"resultados futuros\.")


def _aviso_legal(rel: str) -> str:
    flat = " ".join(re.sub(r"\n[ \t]*>[ \t]?", "\n", _ler(rel)).split())
    m = _AVISO.search(flat)
    assert m, f"{rel}: aviso legal fixo não encontrado"
    return m.group(0)


def test_licenses_and_disclaimer():
    apache = _ler("LICENSE")
    assert apache.lstrip().startswith("Apache License") and "Version 2.0, January 2004" in apache
    assert "END OF TERMS AND CONDITIONS" in apache
    docs = _ler("LICENSE-docs")
    for agulha in ("Atribuição 4.0 Internacional", "Cláusula 8 – Interpretação",
                   "docs/cdp/marca/", "Apache License 2.0", ">>> marca", "indexar: false",
                   "https://creativecommons.org/licenses/by/4.0/legalcode.pt"):
        assert agulha in docs, agulha
    notice = _ler("NOTICE")
    for agulha in ("Apache License 2.0", ">>> marca", "src/cdp/workflow/painel_template.html",
                   "docs/cdp/marca/", "scripts/cdp_marca.py"):
        assert agulha in notice, agulha
    for rel in ("README.md", "docs/cdp/REPLICAR.md"):
        flat = " ".join(_ler(rel).split())
        for agulha in ("Apache", "CC BY 4.0", "LICENSE-docs", "NOTICE", "docs/cdp/marca/",
                       ">>> marca", "app Fechamento", "espelho não modificado"):
            assert agulha in flat, (rel, agulha)
    # um só aviso legal fixo, descritivo (sem conclusões jurídicas sobre o conteúdo)
    avisos = {rel: _aviso_legal(rel) for rel in ("README.md", "docs/cdp/REPLICAR.md",
                                                  "LICENSE-docs")}
    assert len(set(avisos.values())) == 1, avisos
    aviso = avisos["README.md"]
    for agulha in ("carteira simulada", "Não há oferta", "não é fundo de investimento",
                   "Resolução CVM nº 175/2022", "Resolução CVM nº 20/2021",
                   "modelos quantitativos internos", "não consideram objetivos"):
        assert agulha in aviso, agulha
    for conclusao in ("não é relatório de análise", "não constitui", "recomendação de investimento"):
        assert conclusao not in aviso, conclusao


def test_replica_guide_names_every_hardcoded_address():
    """Todo arquivo de código ou configuração do CDP com o endereço do repositório ou do portal
    originais aparece na lista de trocas de ``docs/cdp/REPLICAR.md``."""
    replicar = _ler("docs/cdp/REPLICAR.md")
    prefixos = ("src/cdp/", "configs/cdp/", "plugins/", ".claude-plugin/", "scripts/cdp_", "site/")
    faltam = []
    for rel, txt in _texto_do_repositorio(prefixos):
        if rel.endswith(".md") or rel.startswith("configs/cdp/historico/"):
            continue
        if "arielassayag/marketsummary" in txt or "arielassayag.github.io" in txt:
            if rel not in replicar:
                faltam.append(rel)
    assert faltam == [], f"docs/cdp/REPLICAR.md (seção 3) não cita: {faltam}"


# ------------------------------------------------------- ativação do mandato e adaptadores


ATIVACAO = ROOT / "docs" / "cdp" / "ativacao" / "fund_ativacao.yaml"


def _mesclar(base: dict, bloco: dict) -> dict:
    for k, v in bloco.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mesclar(base[k], v)
        else:
            base[k] = v
    return base


@pytest.mark.skipif(not ATIVACAO.is_file(), reason="ativação já aplicada em configs/cdp/fund.yaml")
def test_fund_activation_draft_merges_into_a_valid_config(tmp_path: Path):
    from cdp.calendar import dia_de_montagem
    from cdp.config import load_config

    texto = ATIVACAO.read_text(encoding="utf-8")
    assert texto.startswith("# RASCUNHO REVISÁVEL"), "cabeçalho do rascunho"
    base = yaml.safe_load((ROOT / "configs" / "cdp" / "fund.yaml").read_text(encoding="utf-8"))
    alvo = tmp_path / "fund.yaml"
    alvo.write_text(yaml.safe_dump(_mesclar(base, yaml.safe_load(texto)), allow_unicode=True,
                                   sort_keys=False), encoding="utf-8")
    cfg = load_config(alvo)
    assert str(getattr(cfg.fund.rebalance_weekday, "value", cfg.fund.rebalance_weekday)) \
        == "LAST_US_SESSION"
    assert dia_de_montagem(date(2026, 10, 9), cfg)  # carteira inaugural: sexta, 09/10
    assert "docs/cdp/ativacao/fund_ativacao.yaml" in _ler("docs/cdp/EM_ANDAMENTO.md")


@pytest.mark.xfail(strict=False, reason="GEMINI.md sem dono nesta onda: ainda descreve o GitHub "
                   "Actions como caminho sem supervisão (pendência em docs/cdp/EM_ANDAMENTO.md)")
def test_gemini_md_points_to_the_app_scheduler():
    texto = " ".join(_ler("GEMINI.md").split())
    assert "seção 5" not in texto  # a seção 5 da AUTOMACAO.md é o Codex
    assert "sem credencial de escrita" not in texto
    assert "seção 6" in texto and "cdp-trava" in texto


# ---------------------------------------------- leitor novo, só com o AGENTS.md (qualquer app)


def test_fresh_reader_with_only_agents_md_knows_what_to_do():
    agents = _ler("AGENTS.md")
    cdp = agents[agents.index("# CDP — Cabra da Peste"):]
    flat = " ".join(cdp.split())
    # o que rodar agora: estado → agenda → roteiro neutro
    i_estado = flat.index("uv run python -m cdp estado --formato md")
    i_agenda = flat.index("uv run python -m cdp agenda")
    i_roteiro = flat.index("docs/cdp/playbooks/<TAREFA>.md")
    assert i_estado < i_agenda < i_roteiro
    # como publicar: só por cdp publicar, com a trava do gate, e liberar a trava
    assert "publicação **só** por" in flat and "uv run python -m cdp publicar --tarefa" in flat
    assert "uv run python -m cdp trava liberar --id" in flat
    # o que nunca fazer
    nunca = cdp[cdp.index("## 9. Nunca"):]
    for agulha in ("--force", "fora do executor designado", "kill switch", "notícia",
                   "Calcular número", "fonte não pública"):
        assert agulha in nunca, agulha
    # onde agendar: dentro do app de IA; GitHub Actions só CI e portal
    for agulha in ("--alvo claude-routines", "--harness codex", "--harness gemini",
                   "nunca é a etapa de IA do caminho principal"):
        assert agulha in flat, agulha
    for inv in ("Números só em código", "Só dados públicos", "Modelos abertos",
                "Escritor único e trava", "Tom e idioma"):
        assert inv in flat, inv
