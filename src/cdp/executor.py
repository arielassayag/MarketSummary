"""Escritor único do CDP em qualquer harness: executor designado, trava distribuída,
sincronização e publicação (``git``) feitas por código.

- ``configs/cdp/executor.yaml`` diz QUEM grava o livro (``local-pc``, ``claude-cloud``,
  ``github-actions``, …, ou ``nenhum`` = pausado). A identidade de cada ambiente é explícita:
  variável ``CDP_EXECUTOR`` (e ``CDP_HARNESS``) ou o arquivo ignorado ``.cdp/local.yaml`` gravado
  por ``cdp executor registrar``; nunca adivinhada (uma sessão de desenvolvimento na nuvem não
  pode passar por executora).
- ``cdp trava`` — trava distribuída no próprio GitHub: ramo ``cdp-trava`` com ``trava.json``,
  atualizado por compare-and-swap (push sem ``--force`` de um commit filho da ponta lida; push
  rejeitado = outro ganhou). Cobre execuções em máquinas separadas (rotinas na nuvem, reservas).
  Falha fechada: sem a trava, um escritor exclusivo não executa nem publica. A renovação nunca
  encurta a validade; em ensaio, nada é gravado no remoto.
- ``cdp sincronizar`` — classifica as mudanças do remoto (seguir, pull, parar, reavaliar) e, com
  ``--executar``, faz o merge sem reescrever nada.
- ``cdp publicar`` — verify → executor (relido de origin/main) → trava confirmada (escritores
  exclusivos; ``caminhos_exclusivos`` das compartilhadas) → ``git add`` do que ESTA execução
  gravou desde o retrato do gate (escritor exclusivo: também o que uma execução anterior deste
  clone gravou e não publicou) → commit com trailers de procedência → sincronizar → trava
  confirmada de novo → ``git push origin HEAD:main`` (nunca ``--force``).
- ``cdp entrega`` — pacote do que a mente gravou, do job da IA (sem escrita) ao job publicador
  do GitHub Actions; a importação só aceita arquivos comuns dentro dos caminhos da tarefa.

Credencial opcional ``CDP_GIT_TOKEN``: injetada por chamada (cabeçalho HTTP), nunca gravada em
``.git/config``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import yaml

if TYPE_CHECKING:  # pragma: no cover
    from .rotinas import Tarefa

EXECUTOR_PADRAO = Path("configs/cdp/executor.yaml")
LOCAL_YAML = Path(".cdp/local.yaml")
EXECUCOES_DIR = Path(".cdp/execucoes")
EXECUTORES = ("local-pc", "claude-cloud", "github-actions", "codex-cloud", "gemini-actions",
              "outro", "nenhum")
HARNESS_INFO = ("claude-code", "codex", "gemini", "antigravity", "copilot", "cursor", "outro")
REMOTO = "origin"
RAMO_TRAVA = "cdp-trava"
ARQUIVO_TRAVA = "trava.json"
FOLGA_RELOGIO = timedelta(minutes=2)
FUSO = ZoneInfo("America/Sao_Paulo")
#: Mudanças do remoto no livro que se mesclam sem conflito (só arquivos novos).
LIVRO_MESCLAVEL = ("reports/risk/", "reports/backtest/")
#: Arquivos cujo pull exige reinstalar o ambiente.
AMBIENTE = ("pyproject.toml", "uv.lock", "src/")
IDENT_TRAVA = {"GIT_AUTHOR_NAME": "CDP (trava)",
               "GIT_AUTHOR_EMAIL": "cdp-trava@users.noreply.github.com",
               "GIT_COMMITTER_NAME": "CDP (trava)",
               "GIT_COMMITTER_EMAIL": "cdp-trava@users.noreply.github.com"}
IDENT_ROTINA = ("CDP (rotina)", "cdp-rotina@users.noreply.github.com")

OK = 0
FALHA = 1
CONFIG = 2
SEM_PUSH = 3
FORA_DO_ESCOPO = 5
PARCIAL = 6           # publicou o que era mesclável; o que exige a trava ficou retido no clone
OUTRO_EXECUTOR = 10
PAUSADO = 11
IDENTIDADE_DESCONHECIDA = 12
MUDOU_NO_REMOTO = 13
TRAVA_AUSENTE = 14    # escritor exclusivo sem a trava distribuída: nada publicado


class ErroExecutor(ValueError):
    """``executor.yaml`` inválido."""


# ==========================================================================================
# git
# ==========================================================================================


def _git_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"LC_ALL": "C", "LANG": "C", "GIT_TERMINAL_PROMPT": "0"})
    if extra:
        env.update(extra)
    return env


def git(args: Sequence[str], raiz: Path | str, *, env: Mapping[str, str] | None = None,
        rede: bool = False, entrada: str | None = None, extra_env: Mapping[str, str] | None = None,
        timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """``git`` sem prompts, em inglês (saída estável) e, em chamadas de rede, com o token de
    ``CDP_GIT_TOKEN`` injetado só nesta chamada."""
    pre: list[str] = []
    token = (env or os.environ).get("CDP_GIT_TOKEN") if rede else None
    if token:
        cred = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        pre = ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {cred}"]
    try:
        return subprocess.run(["git", *pre, *args], cwd=str(raiz), capture_output=True,
                              text=True, input=entrada, timeout=timeout,
                              env=_git_env(extra_env), check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(["git", *args], 127, "", str(exc))


def _ok(r: subprocess.CompletedProcess[str]) -> str:
    return r.stdout.strip() if r.returncode == 0 else ""


def git_head(raiz: Path | str) -> str | None:
    return _ok(git(["rev-parse", "HEAD"], raiz)) or None


def _identidade_commit(raiz: Path | str) -> list[str]:
    """``-c user.*`` só quando o clone não tem identidade configurada (máquinas novas)."""
    if _ok(git(["config", "user.email"], raiz)):
        return []
    return ["-c", f"user.name={IDENT_ROTINA[0]}", "-c", f"user.email={IDENT_ROTINA[1]}"]


def _no_livro(path: str, caminhos: Sequence[str]) -> bool:
    return any(path == c or path.startswith(c.rstrip("/") + "/") for c in caminhos)


def _linhas(texto: str) -> list[str]:
    return [x for x in texto.splitlines() if x.strip()]


# ==========================================================================================
# Executor designado e identidade do ambiente
# ==========================================================================================


def ler_executor(texto: str) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(texto)
    except yaml.YAMLError as exc:
        raise ErroExecutor(f"YAML inválido: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("versao") != 1:
        raise ErroExecutor("esperado um mapa com versao: 1")
    if raw.get("executor") not in EXECUTORES:
        raise ErroExecutor(f"executor inválido: {raw.get('executor')!r} "
                           f"({' | '.join(EXECUTORES)})")
    return raw


def carregar_executor(raiz: Path | str, caminho: Path | None = None) -> dict[str, Any]:
    path = Path(raiz) / (caminho or EXECUTOR_PADRAO)
    try:
        return ler_executor(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ErroExecutor(f"não consegui ler {path}: {exc}") from exc


def executor_remoto(raiz: Path | str, env: Mapping[str, str] | None = None, *,
                    buscar: bool = True, ramo: str = "main") -> dict[str, Any] | None:
    """O ``executor.yaml`` de ``origin/<ramo>`` (``None`` se o remoto não responde)."""
    if buscar and git(["fetch", "--quiet", REMOTO, ramo], raiz, env=env, rede=True).returncode:
        return None
    r = git(["show", f"{REMOTO}/{ramo}:{EXECUTOR_PADRAO.as_posix()}"], raiz)
    if r.returncode:
        return None
    return ler_executor(r.stdout)


def detectar_ambiente(env: Mapping[str, str]) -> str | None:
    """Pista do ambiente (só informativa; nunca concede a escrita)."""
    if env.get("GITHUB_ACTIONS") == "true":
        return "github-actions"
    if env.get("CLAUDE_CODE_REMOTE") or env.get("CLAUDE_CODE_REMOTE_SESSION_ID"):
        return "claude-cloud"
    return None


def identidade(raiz: Path | str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Quem é este ambiente: ``CDP_EXECUTOR`` > ``.cdp/local.yaml`` > ``desconhecido``.

    ``harness`` (a mente que grava os registros) vem **só** de ``CDP_HARNESS``, que o executor
    (script de rotina, ambiente da nuvem, workflow) define: o clone pode ser usado por outro
    harness numa sessão de operador. O harness de ``.cdp/local.yaml`` é só informativo
    (``harness_registrado``)."""
    env = os.environ if env is None else env
    harness = env.get("CDP_HARNESS") or None
    base = {"harness": harness, "harness_registrado": None,
            "ambiente_detectado": detectar_ambiente(env)}
    if env.get("CDP_EXECUTOR"):
        return {"executor": env["CDP_EXECUTOR"], "origem": "CDP_EXECUTOR", **base}
    path = Path(raiz) / LOCAL_YAML
    if path.is_file():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            raw = {}
        if isinstance(raw, dict) and raw.get("executor"):
            return {"executor": str(raw["executor"]), "origem": LOCAL_YAML.as_posix(),
                    **{**base, "harness_registrado": raw.get("harness")}}
    return {"executor": "desconhecido", "origem": None, **base}


def verificar(raiz: Path | str, tarefa: Tarefa | None = None, *,
              env: Mapping[str, str] | None = None, remoto: bool = False
              ) -> tuple[int, dict[str, Any]]:
    """Este ambiente pode gravar o livro? (0 sim · 10 outro · 11 pausado · 12 identidade
    desconhecida · 13 designação mudou em origin/main · 2 arquivo inválido). Tarefas só de
    leitura sempre passam (0)."""
    env = os.environ if env is None else env
    ident = identidade(raiz, env)
    info: dict[str, Any] = {"designado": None, "este_ambiente": ident["executor"],
                            "harness": ident["harness"], "origem": ident["origem"],
                            "ambiente_detectado": ident["ambiente_detectado"],
                            "sou_o_executor": False, "motivo": None}
    try:
        cfg = carregar_executor(raiz)
    except ErroExecutor as exc:
        info["motivo"] = f"executor.yaml inválido: {exc}"
        return CONFIG, info
    info.update({"designado": cfg["executor"], "desde": cfg.get("desde"), "por": cfg.get("por")})
    info["sou_o_executor"] = cfg["executor"] == ident["executor"] and cfg["executor"] != "nenhum"
    if tarefa is not None and not tarefa.grava:
        info["motivo"] = "tarefa só de leitura"
        return OK, info
    if remoto:
        try:
            rem = executor_remoto(raiz, env)
        except ErroExecutor as exc:
            info["motivo"] = f"executor.yaml de origin/main inválido: {exc}"
            return CONFIG, info
        if rem is None:
            info["remoto"] = "indisponível"
        else:
            info["remoto"] = rem["executor"]
            if rem["executor"] != cfg["executor"]:
                info["motivo"] = (f"a designação mudou em origin/main ({cfg['executor']} → "
                                  f"{rem['executor']}): sincronize antes de gravar")
                info["sou_o_executor"] = False
                return MUDOU_NO_REMOTO, info
    if cfg["executor"] == "nenhum":
        info["motivo"] = "executor pausado (nenhum): ninguém grava o livro agora"
        return PAUSADO, info
    if ident["executor"] == "desconhecido":
        info["motivo"] = ("identidade deste ambiente desconhecida: defina CDP_EXECUTOR ou rode "
                          "`cdp executor registrar --como <executor>` no clone das rotinas")
        return IDENTIDADE_DESCONHECIDA, info
    if not info["sou_o_executor"]:
        info["motivo"] = (f"o executor designado é {cfg['executor']}; este ambiente é "
                          f"{ident['executor']}")
        return OUTRO_EXECUTOR, info
    info["motivo"] = "este ambiente é o executor designado"
    return OK, info


def sessao_url(env: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    sid = env.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if sid:
        return "https://claude.ai/code/" + sid.replace("cse_", "session_", 1)
    if env.get("GITHUB_RUN_ID") and env.get("GITHUB_REPOSITORY"):
        server = env.get("GITHUB_SERVER_URL", "https://github.com")
        return f"{server}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    return None


def trailers(tarefa_id: str, ident: Mapping[str, Any], execucao: str,
             env: Mapping[str, str] | None = None, mente: str | None = None) -> list[str]:
    """Trailers de procedência do commit. ``CDP-Harness``: ``CDP_HARNESS`` do ambiente, senão a
    mente declarada pela execução (``cdp publicar --mente``), senão ``não informado``."""
    harness = ident.get("harness") or mente or "não informado"
    out = [f"CDP-Tarefa: {tarefa_id}", f"CDP-Executor: {ident.get('executor')}",
           f"CDP-Harness: {harness}", f"CDP-Execucao: {execucao}"]
    url = sessao_url(env)
    if url:
        out.append(f"CDP-Sessao: {url}")
    return out


def registrar_execucao(raiz: Path | str, exec_id: str, dados: Mapping[str, Any]) -> None:
    pasta = Path(raiz) / EXECUCOES_DIR
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{exec_id}.json").write_text(json.dumps(dict(dados), ensure_ascii=False,
                                                          indent=1), encoding="utf-8")
    except OSError:  # pragma: no cover - disco somente leitura: o registro é auxiliar
        pass


def ler_execucao(raiz: Path | str, exec_id: str) -> dict[str, Any] | None:
    try:
        return json.loads((Path(raiz) / EXECUCOES_DIR / f"{exec_id}.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ultima_execucao(raiz: Path | str, tarefa_id: str) -> tuple[str, dict[str, Any]] | None:
    pasta = Path(raiz) / EXECUCOES_DIR
    if not pasta.is_dir():
        return None
    achadas = []
    for p in pasta.glob("*.json"):
        d = ler_execucao(raiz, p.stem)
        if d and d.get("tarefa") == tarefa_id:
            achadas.append((str(d.get("inicio") or ""), p.stem, d))
    if not achadas:
        return None
    _, eid, d = max(achadas)
    return eid, d


# ==========================================================================================
# Trava distribuída (ramo cdp-trava)
# ==========================================================================================


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _dt(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def trava_ler(raiz: Path | str, env: Mapping[str, str] | None = None
              ) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """``(estado, ponta, erro)``: estado ``None`` = ramo inexistente; erro = remoto inacessível."""
    r = git(["ls-remote", "--heads", REMOTO, RAMO_TRAVA], raiz, env=env, rede=True, timeout=60)
    if r.returncode:
        return None, None, (r.stderr.strip().splitlines() or ["remoto inacessível"])[-1]
    if not r.stdout.strip():
        return None, None, None
    ref = f"refs/remotes/{REMOTO}/{RAMO_TRAVA}"
    f = git(["fetch", "--quiet", REMOTO, f"+refs/heads/{RAMO_TRAVA}:{ref}"], raiz, env=env,
            rede=True, timeout=60)
    if f.returncode:
        return None, None, (f.stderr.strip().splitlines() or ["fetch da trava falhou"])[-1]
    ponta = _ok(git(["rev-parse", ref], raiz))
    show = git(["show", f"{ponta}:{ARQUIVO_TRAVA}"], raiz)
    if show.returncode:
        return {"estado": "livre"}, ponta, None
    try:
        estado = json.loads(show.stdout)
    except ValueError:
        estado = {"estado": "livre", "corrompida": True}
    return estado if isinstance(estado, dict) else {"estado": "livre"}, ponta, None


def _em_ensaio(env: Mapping[str, str] | None) -> bool:
    return (os.environ if env is None else env).get("CDP_ENSAIO") == "1"


ENSAIO_TRAVA = {"estado": "ensaio", "id": None,
                "motivo": "ensaio (CDP_ENSAIO=1): a trava distribuída nunca é tocada"}


def _trava_gravar(raiz: Path | str, estado: Mapping[str, Any], pai: str | None, msg: str,
                  env: Mapping[str, str] | None = None) -> bool:
    if _em_ensaio(env):  # ensaio nunca grava no remoto (nem a trava)
        return False
    texto = json.dumps(dict(estado), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    blob = _ok(git(["hash-object", "-w", "--stdin"], raiz, entrada=texto))
    tree = _ok(git(["mktree"], raiz, entrada=f"100644 blob {blob}\t{ARQUIVO_TRAVA}\n"))
    if not blob or not tree:
        return False
    args = ["commit-tree", tree, "-m", msg] + (["-p", pai] if pai else [])
    commit = _ok(git(args, raiz, extra_env=IDENT_TRAVA))
    if not commit:
        return False
    push = git(["push", "--quiet", REMOTO, f"{commit}:refs/heads/{RAMO_TRAVA}"], raiz, env=env,
               rede=True, timeout=60)
    return push.returncode == 0


def _ocupada(estado: Mapping[str, Any] | None, agora: datetime) -> bool:
    if not estado or estado.get("estado") != "ocupada":
        return False
    exp = _dt(estado.get("expira"))
    return exp is None or exp + FOLGA_RELOGIO > agora


def _hhmm(v: Any) -> str:
    d = _dt(v)
    return f"{d.astimezone(FUSO):%d/%m %H:%M}" if d else "?"


def ttl_da_tarefa(raiz: Path | str, tarefa_id: str | None, padrao: int = 45) -> int:
    """``trava_ttl_min`` da tarefa em ``configs/cdp/rotinas.yaml`` (``padrao`` se ilegível)."""
    if not tarefa_id:
        return padrao
    from .rotinas import ROTINAS_PADRAO, ErroRotinas, carregar

    try:
        return carregar(Path(raiz) / ROTINAS_PADRAO).tarefa(tarefa_id).trava_ttl_min
    except (ErroRotinas, OSError):
        return padrao


def trava_adquirir(raiz: Path | str, tarefa: Tarefa, *, agora: datetime | None = None,
                   env: Mapping[str, str] | None = None, ttl_min: int | None = None,
                   tentativas: int = 3, trava_id: str | None = None,
                   esperar_min: float = 0, intervalo_s: float = 30) -> dict[str, Any]:
    """Adquire a trava (livre ou expirada). Estados devolvidos: ``adquirida``,
    ``ocupada_por_outro``, ``indisponivel`` (remoto inacessível ou disputa) ou ``ensaio``.
    Só ``adquirida`` autoriza um escritor exclusivo (o gate pula nos demais).

    Reentrada: com ``trava_id`` (ou ``CDP_TRAVA_ID``) igual ao da trava em vigor, a mesma
    execução a renova e recebe ``adquirida`` com o mesmo id (ex.: o executor do GitHub Actions
    segura a trava e a mente roda o gate de novo). Com ``esperar_min``, tenta de novo a cada
    ``intervalo_s`` segundos enquanto outra execução a segura."""
    import time as _time

    env = os.environ if env is None else env
    if _em_ensaio(env):
        return dict(ENSAIO_TRAVA)
    fixo = agora is not None
    agora = agora or datetime.now(UTC)
    ttl = timedelta(minutes=ttl_min or tarefa.trava_ttl_min)
    ident = identidade(raiz, env)
    reentrada = trava_id or env.get("CDP_TRAVA_ID") or None
    novo_id = reentrada or str(uuid.uuid4())
    limite = agora + timedelta(minutes=esperar_min)
    disputas = 0
    while True:
        estado, ponta, erro = trava_ler(raiz, env)
        if erro:
            return {"estado": "indisponivel", "id": None, "motivo": f"trava inacessível: {erro}"}
        if reentrada and estado and estado.get("estado") == "ocupada" \
                and estado.get("id") == reentrada:
            r = trava_renovar(raiz, reentrada, ttl_min=ttl_min or tarefa.trava_ttl_min,
                              agora=agora, env=env)
            if r["estado"] == "renovada":
                return {"estado": "adquirida", "id": reentrada, "expira": r["expira"],
                        "tarefa": estado.get("tarefa"), "reentrada": True}
            return {"estado": "indisponivel", "id": None, "motivo": r.get("motivo")}
        if _ocupada(estado, agora):
            if agora < limite:
                _time.sleep(intervalo_s)
                agora = agora + timedelta(seconds=intervalo_s) if fixo else datetime.now(UTC)
                continue
            return {"estado": "ocupada_por_outro", "id": None, "atual": estado,
                    "motivo": (f"{estado.get('tarefa')} em andamento em "
                               f"{estado.get('executor')} desde {_hhmm(estado.get('inicio'))} "
                               f"(trava até {_hhmm(estado.get('expira'))})")}
        novo = {"versao": 1, "estado": "ocupada", "id": novo_id, "tarefa": tarefa.id,
                "executor": ident["executor"], "harness": ident["harness"],
                "sessao": sessao_url(env), "inicio": _iso(agora), "renovada": _iso(agora),
                "expira": _iso(agora + ttl)}
        if _trava_gravar(raiz, novo, ponta, f"CDP: trava {tarefa.id}", env):
            return {"estado": "adquirida", "id": novo_id, "expira": novo["expira"],
                    "tarefa": tarefa.id}
        disputas += 1
        if disputas >= tentativas:
            return {"estado": "indisponivel", "id": None,
                    "motivo": f"disputa pela trava: {tentativas} tentativas sem sucesso"}


def trava_renovar(raiz: Path | str, trava_id: str, *, ttl_min: int | None = None,
                  agora: datetime | None = None, env: Mapping[str, str] | None = None
                  ) -> dict[str, Any]:
    """Renova a trava desta execução. A validade nunca encolhe: ``max(expira atual, agora +
    ttl)``, com ``ttl`` da tarefa que segura a trava (``trava_ttl_min`` em ``rotinas.yaml``)
    quando não informado."""
    if _em_ensaio(env):
        return dict(ENSAIO_TRAVA)
    agora = agora or datetime.now(UTC)
    for _ in range(3):
        estado, ponta, erro = trava_ler(raiz, env)
        if erro:
            return {"estado": "indisponivel", "motivo": erro}
        if not estado or estado.get("id") != trava_id or estado.get("estado") != "ocupada":
            return {"estado": "perdida", "motivo": "a trava não é mais desta execução",
                    "atual": estado}
        ttl = ttl_min or ttl_da_tarefa(raiz, estado.get("tarefa"))
        alvo = agora + timedelta(minutes=ttl)
        atual = _dt(estado.get("expira"))
        expira = max(alvo, atual) if atual is not None else alvo
        novo = {**estado, "renovada": _iso(agora), "expira": _iso(expira)}
        if _trava_gravar(raiz, novo, ponta, f"CDP: trava renovada ({estado.get('tarefa')})",
                         env):
            return {"estado": "renovada", "id": trava_id, "expira": novo["expira"]}
    return {"estado": "indisponivel", "motivo": "disputa ao renovar a trava"}


def trava_liberar(raiz: Path | str, trava_id: str, *, agora: datetime | None = None,
                  env: Mapping[str, str] | None = None) -> dict[str, Any]:
    if _em_ensaio(env):
        return dict(ENSAIO_TRAVA)
    agora = agora or datetime.now(UTC)
    for _ in range(3):
        estado, ponta, erro = trava_ler(raiz, env)
        if erro:
            return {"estado": "indisponivel", "motivo": erro}
        if not estado or estado.get("id") != trava_id or estado.get("estado") != "ocupada":
            return {"estado": "nao_detentor", "motivo": "nada a liberar (não é o detentor)",
                    "atual": estado}
        novo = {"versao": 1, "estado": "livre", "id": None,
                "ultima": {k: estado.get(k) for k in ("tarefa", "executor", "inicio")},
                "liberada": _iso(agora)}
        if _trava_gravar(raiz, novo, ponta, f"CDP: trava liberada ({estado.get('tarefa')})",
                         env):
            return {"estado": "liberada", "id": trava_id}
    return {"estado": "indisponivel", "motivo": "disputa ao liberar a trava"}


ENSAIO_HOOK = """#!/bin/sh
# cdp-ensaio: instalado por `cdp rotinas gate` em ensaio. Com CDP_ENSAIO=1 no ambiente (o ambiente
# de ensaio inteiro), nenhum push sai deste clone; fora dele, o gancho não faz nada.
if [ "${CDP_ENSAIO:-}" = "1" ]; then
  echo "CDP: ensaio (CDP_ENSAIO=1) — push recusado: o ensaio nunca publica" >&2
  exit 1
fi
exit 0
"""


def proteger_ensaio(raiz: Path | str) -> dict[str, Any]:
    """Instala ``pre-push`` que recusa todo push enquanto ``CDP_ENSAIO=1`` (defesa além do
    prompt; inerte fora do ensaio). Não sobrescreve um gancho alheio."""
    pasta = _ok(git(["rev-parse", "--path-format=absolute", "--git-path", "hooks"], raiz))
    if not pasta:
        return {"instalado": False, "motivo": "fora de um repositório git"}
    hook = Path(pasta) / "pre-push"
    try:
        if hook.exists() and "cdp-ensaio" not in hook.read_text(encoding="utf-8",
                                                                  errors="replace"):
            return {"instalado": False, "motivo": f"gancho pre-push alheio em {hook}"}
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(ENSAIO_HOOK, encoding="utf-8", newline="\n")
        hook.chmod(0o755)
    except OSError as exc:
        return {"instalado": False, "motivo": f"{exc.__class__.__name__}: {exc}"}
    return {"instalado": True, "gancho": hook.as_posix()}


# ==========================================================================================
# Sincronização e publicação
# ==========================================================================================


def _caminhos_livro() -> tuple[str, ...]:
    from .rotinas import CAMINHOS_DO_LIVRO

    return CAMINHOS_DO_LIVRO


def sincronizar(raiz: Path | str, *, executar: bool = False, env: Mapping[str, str] | None = None,
                ramo: str = "main", buscar: bool = True) -> dict[str, Any]:
    """Classifica o remoto: ``seguir`` · ``pull`` · ``reavaliar`` · ``parar`` ·
    ``seguir_sem_push``; com ``executar``, faz o merge (``pull``/``reavaliar``)."""
    env = os.environ if env is None else env
    livro = _caminhos_livro()
    remoto = f"{REMOTO}/{ramo}"
    out: dict[str, Any] = {"acao": "seguir", "motivo": "", "arquivos": [], "executado": False}
    if buscar:
        f = git(["fetch", "--quiet", REMOTO, ramo], raiz, env=env, rede=True)
        if f.returncode:
            out.update({"acao": "seguir_sem_push",
                        "motivo": "fetch falhou: " + " ".join(f.stderr.split())[:200]})
            return out
    # 1) clone de rotina: nada de código alterado aqui
    st = git(["status", "--porcelain"], raiz).stdout
    sujos = []
    for linha in _linhas(st):
        xy, path = linha[:2], linha[3:].split(" -> ")[-1].strip('"')
        if xy == "??":
            if path.startswith(("src/", "configs/")):
                sujos.append(path)
        elif not _no_livro(path, livro):
            sujos.append(path)
    if sujos:
        out.update({"acao": "parar", "arquivos": sujos,
                    "motivo": "clone com código ou configuração alterados (desenvolvimento): as "
                              "rotinas precisam de um clone limpo"})
        return out
    locais = _linhas(git(["log", "--format=", "--name-only", f"{remoto}..HEAD"], raiz).stdout)
    fora = sorted({p for p in locais if not _no_livro(p, livro)})
    if fora:
        out.update({"acao": "parar", "arquivos": fora,
                    "motivo": "commits locais fora do livro (clone de desenvolvimento)"})
        return out
    # 2) o que mudou no remoto desde a base comum
    diff = git(["diff", "--name-status", f"HEAD...{remoto}"], raiz)
    if diff.returncode:
        out.update({"acao": "seguir_sem_push", "motivo": "sem base comum com " + remoto})
        return out
    mudancas = [(ln.split("\t")[0], ln.split("\t")[-1]) for ln in _linhas(diff.stdout)]
    nomes = [p for _, p in mudancas]
    out["arquivos"] = nomes
    if not mudancas:
        out["motivo"] = "em dia com " + remoto
        return out
    no_livro = [(s, p) for s, p in mudancas if _no_livro(p, livro)]
    if no_livro:
        alterados_aqui = {ln[3:] for ln in _linhas(st)}
        mesclavel = all(s.startswith("A") and p.startswith(LIVRO_MESCLAVEL)
                        and p not in alterados_aqui for s, p in no_livro)
        if not mesclavel:
            out.update({"acao": "parar", "arquivos": [p for _, p in no_livro],
                        "motivo": "outra sessão gravou o livro no remoto: nunca mesclar, "
                                  "reescrever nem forçar"})
            return out
    acao = "reavaliar" if EXECUTOR_PADRAO.as_posix() in nomes else "pull"
    out.update({"acao": acao, "motivo": ("o executor designado mudou no remoto"
                                         if acao == "reavaliar"
                                         else "remoto com código/documentação novos")})
    if not executar:
        return out
    m = git([*_identidade_commit(raiz), "merge", "--no-edit", remoto], raiz)
    if m.returncode:
        git(["merge", "--abort"], raiz)
        out.update({"acao": "parar", "motivo": "merge falhou: "
                    + " ".join((m.stdout + m.stderr).split())[:200]})
        return out
    out["executado"] = True
    if any(p == a or p.startswith(a) for p in nomes for a in AMBIENTE):
        try:
            u = subprocess.run(["uv", "sync", "--frozen", "--extra", "dev", "--extra", "ai", "-q"],
                               cwd=str(raiz), capture_output=True, text=True, timeout=900,
                               check=False)
            out["uv_sync"] = "ok" if u.returncode == 0 else "falhou"
        except (OSError, subprocess.SubprocessError):
            out["uv_sync"] = "indisponível"
    if acao == "reavaliar":
        code, info = verificar(raiz, None, env=env)
        out["executor"] = info
        if code != OK:
            out.update({"acao": "parar", "motivo": info.get("motivo") or "não sou o executor"})
    return out


def estado_dos_caminhos(raiz: Path | str, caminhos: Sequence[str]) -> dict[str, str | None]:
    """``{arquivo: hash do conteúdo atual}`` (``None`` = apagado) de tudo o que difere de
    ``HEAD`` (alterado, novo ou apagado) sob ``caminhos``. O gate guarda este retrato no
    registro da execução; ``cdp publicar`` publica só o que mudou desde então."""
    if not caminhos:
        return {}
    r = git(["status", "--porcelain=v1", "-z", "-uall", "--", *caminhos], raiz)
    toks = r.stdout.split("\0")
    nomes: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if len(t) < 4:
            continue
        xy, nome = t[:2], t[3:]
        nomes.append(nome)
        if "R" in xy or "C" in xy:
            i += 1  # o caminho de origem vem no token seguinte
    existentes = [n for n in nomes if (Path(raiz) / n).is_file()]
    hashes: dict[str, str] = {}
    if existentes:
        h = git(["hash-object", "--no-filters", "--stdin-paths"], raiz,
                entrada="\n".join(existentes) + "\n")
        hashes = dict(zip(existentes, h.stdout.split(), strict=False))
    return {n: hashes.get(n) for n in sorted(set(nomes))}


def _confirmar_trava(raiz: Path, trava_id: str | None, env: Mapping[str, str]
                     ) -> dict[str, Any]:
    """A trava ainda é desta execução? (renova por compare-and-swap: prova e estende)."""
    if not trava_id:
        return {"estado": "ausente", "motivo": "nenhuma trava informada (--trava)"}
    return trava_renovar(raiz, trava_id, env=env)


def publicar(raiz: Path | str, tarefa: Tarefa, mensagem: str, *, rt: Any = None,
             env: Mapping[str, str] | None = None, sem_push: bool = False,
             execucao: str | None = None, ramo: str = "main",
             verificar_livro: bool = True, trava: str | None = None, sem_trava: bool = False,
             mente: str | None = None, esperar_min: float | None = None
             ) -> tuple[int, dict[str, Any]]:
    """Publica o que ESTA execução gravou nos caminhos da tarefa (ver docstring do módulo).

    - Tarefa compartilhada: só entra o que mudou desde o retrato do gate (``instantaneo`` no
      registro da execução). Escritor exclusivo: tudo o que difere de ``HEAD`` nos caminhos da
      tarefa — o que já diferia no gate é gravação de uma execução anterior deste clone que não
      publicou (``anteriores`` na saída) e da qual esta execução retomou. Sem registro (ex.:
      entrega importada no GitHub Actions), tudo o que difere de ``HEAD`` nos caminhos da
      tarefa.
    - Escritor exclusivo: exige a trava distribuída (``trava``, ``CDP_TRAVA_ID`` ou a do
      registro da execução), confirmada antes do commit e de novo antes do push; sem ela, nada
      é publicado (``TRAVA_AUSENTE``). ``sem_trava`` é só para sessão de operador.
    - Tarefa compartilhada: arquivos de ``caminhos_exclusivos`` (ex.: kill switch e trilha)
      exigem a trava; ``publicar`` tenta adquiri-la (espera ``espera_trava_min``) e, sem ela,
      publica só os arquivos mescláveis e retém os demais (``PARCIAL``).

    Devolve ``(código, saída)``."""
    env = os.environ if env is None else env
    raiz = Path(raiz)
    out: dict[str, Any] = {"tarefa": tarefa.id, "commit": None, "push": False, "motivo": "",
                           "arquivos": [], "retidos": [], "trava": None}
    if _em_ensaio(env):
        out["motivo"] = "ensaio: nada é publicado"
        return OK, out
    if not tarefa.grava:
        out["motivo"] = "tarefa só de leitura: nada a publicar"
        return CONFIG, out
    if not mensagem.startswith("CDP: "):
        out["motivo"] = 'a mensagem precisa começar com "CDP: "'
        return CONFIG, out
    code, info = verificar(raiz, tarefa, env=env, remoto=not sem_push)
    out["executor"] = info
    if code != OK:
        out["motivo"] = info.get("motivo") or "este ambiente não é o executor"
        return code, out
    todos = tuple(tarefa.caminhos) + tuple(tarefa.caminhos_exclusivos)
    staged_antes = _linhas(git(["diff", "--cached", "--name-only"], raiz).stdout)
    fora = [p for p in staged_antes if not _no_livro(p, todos)]
    if fora:
        out.update({"arquivos": fora, "motivo": "há arquivos preparados fora dos caminhos da "
                                                "tarefa: nada foi publicado"})
        return FORA_DO_ESCOPO, out
    # 1) o que esta execução mudou (retrato do gate)
    reg: dict[str, Any] | None
    if execucao:
        reg_id, reg = execucao, ler_execucao(raiz, execucao)
    else:
        ult = ultima_execucao(raiz, tarefa.id)
        reg_id, reg = (ult if ult else (None, None))
    exec_id = reg_id or env.get("CDP_EXECUCAO") or str(uuid.uuid4())
    atual = estado_dos_caminhos(raiz, todos)
    antes = (reg or {}).get("instantaneo")
    if isinstance(antes, dict) and tarefa.exclusiva:
        # Escritor exclusivo (trava única do livro): o que já diferia de HEAD no gate é gravação
        # de uma execução anterior deste clone que não chegou a publicar (interrompida, ou kill
        # switch retido pelo risco). A execução atual retoma a partir dela (a agenda lê o livro
        # local), então ela sai junto, com a trava — senão a trilha publicada citaria arquivos
        # que não foram publicados.
        delta = sorted(atual)
        out["anteriores"] = sorted(p for p, h in atual.items() if antes.get(p, "") == h)
        out["base"] = "tudo o que difere da versão local nos caminhos da tarefa (escritor exclusivo)"
    elif isinstance(antes, dict):
        delta = sorted(p for p, h in atual.items() if p not in antes or antes[p] != h)
        # Pastas só de arquivos novos da própria tarefa (relatórios de risco, backtests): o que
        # uma execução anterior desta tarefa gravou ali e não publicou sai junto.
        anteriores = sorted(p for p in atual if p not in delta and p.startswith(LIVRO_MESCLAVEL)
                            and _no_livro(p, tarefa.caminhos))
        if anteriores:
            delta = sorted({*delta, *anteriores})
            out["anteriores"] = anteriores
        out["base"] = "retrato do gate desta execução"
    else:
        delta = sorted(atual)
        out["base"] = "tudo o que difere da versão local nos caminhos da tarefa"
    # 2) trava distribuída
    exige = [p for p in delta if tarefa.exclusiva or _no_livro(p, tarefa.caminhos_exclusivos)]
    trava_id = trava or env.get("CDP_TRAVA_ID") or (reg or {}).get("trava") or None
    propria = False
    if exige and not sem_trava:
        conf = _confirmar_trava(raiz, trava_id, env)
        ok_trava = conf.get("estado") == "renovada"
        if not ok_trava and not tarefa.exclusiva:
            espera = tarefa.espera_trava_min if esperar_min is None else esperar_min
            tr = trava_adquirir(raiz, tarefa, env=env, esperar_min=espera)
            if tr.get("estado") == "adquirida":
                trava_id, propria, ok_trava = tr["id"], True, True
            else:
                conf = tr
        if not ok_trava:
            motivo = conf.get("motivo") or conf.get("estado") or "sem trava"
            if tarefa.exclusiva:
                out.update({"arquivos": exige, "motivo": (
                    f"escritor exclusivo sem a trava distribuída ({motivo}): nada foi publicado. "
                    "A trava vem do gate (`cdp rotinas gate --tarefa ... --adquirir`) e entra "
                    "em `cdp publicar --trava <id>`")})
                return TRAVA_AUSENTE, out
            out["retidos"] = exige
            out["motivo_retidos"] = (f"arquivos que exigem a trava ficaram neste clone, sem "
                                     f"publicar ({motivo})")
            delta = [p for p in delta if p not in exige]
            exige = []
    out["trava"] = trava_id if exige else None
    try:
        return _publicar_delta(raiz, tarefa, mensagem, out, delta=delta, exige=bool(exige),
                               trava_id=trava_id, sem_trava=sem_trava, rt=rt, env=env,
                               sem_push=sem_push, exec_id=exec_id, ramo=ramo, mente=mente,
                               verificar_livro=verificar_livro)
    finally:
        if propria and trava_id:
            out["trava_liberada"] = trava_liberar(raiz, trava_id, env=env).get("estado")


def _publicar_delta(raiz: Path, tarefa: Tarefa, mensagem: str, out: dict[str, Any], *,
                    delta: list[str], exige: bool, trava_id: str | None, sem_trava: bool,
                    rt: Any, env: Mapping[str, str], sem_push: bool, exec_id: str, ramo: str,
                    mente: str | None, verificar_livro: bool) -> tuple[int, dict[str, Any]]:
    parcial = PARCIAL if out.get("retidos") else OK
    integro, msgs = True, []
    if verificar_livro and rt is not None:
        integro, msgs = rt.verify_all()
        out["verify"] = "ÍNTEGRO" if integro else "FALHA DE INTEGRIDADE"
    out["arquivos"] = delta
    if delta:
        spec = "\0".join(delta) + "\0"
        a = git(["add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul"], raiz,
                entrada=spec)
        if a.returncode:
            out["motivo"] = "git add falhou: " + " ".join((a.stdout + a.stderr).split())[:300]
            return FALHA, out
        anteriores = [p for p in out.get("anteriores") or [] if p in delta]
        corpo = (f"Inclui {len(anteriores)} arquivo(s) gravado(s) por execução anterior deste "
                 "clone e ainda não publicado(s).\n\n" if anteriores else "")
        texto = mensagem.rstrip() + "\n\n" + corpo + "\n".join(
            trailers(tarefa.id, identidade(raiz, env), exec_id, env, mente)) + "\n"
        c = git([*_identidade_commit(raiz), "commit", "--quiet", "-m", texto,
                 "--pathspec-from-file=-", "--pathspec-file-nul"], raiz, entrada=spec)
        if c.returncode:
            out["motivo"] = "commit falhou: " + " ".join((c.stdout + c.stderr).split())[:300]
            return FALHA, out
        out["commit"] = git_head(raiz)
    if not integro:
        out["motivo"] = "verify falhou: commit local, sem push (" + "; ".join(msgs[:3]) + ")"
        return FALHA, out
    if sem_push:
        out["motivo"] = "sem push (--sem-push)"
        return parcial, out
    remoto = f"{REMOTO}/{ramo}"
    for tentativa in range(2):
        s = sincronizar(raiz, executar=True, env=env, ramo=ramo)
        out["sincronizar"] = {k: s[k] for k in ("acao", "motivo")}
        if s["acao"] in ("parar", "seguir_sem_push"):
            out["motivo"] = f"sem push: {s['motivo']}"
            return SEM_PUSH, out
        locais = _linhas(git(["log", "--format=", "--name-only", f"{remoto}..HEAD"], raiz).stdout)
        if not locais and not _ok(git(["rev-list", f"{remoto}..HEAD"], raiz)):
            out["motivo"] = "nada a publicar" if not delta else "já publicado"
            return parcial, out
        escopo = [p for p in locais if not _no_livro(p, _caminhos_livro())]
        if escopo:
            out.update({"motivo": "commits locais fora do livro: sem push", "arquivos": escopo})
            return FORA_DO_ESCOPO, out
        if exige and not sem_trava:
            conf = _confirmar_trava(raiz, trava_id, env)
            if conf.get("estado") != "renovada":
                out["motivo"] = ("trava perdida antes do push: commit local retido, sem push ("
                                 + str(conf.get("motivo") or conf.get("estado")) + ")")
                return SEM_PUSH, out
        p = git(["push", "--quiet", REMOTO, f"HEAD:refs/heads/{ramo}"], raiz, env=env, rede=True,
                timeout=300)
        if p.returncode == 0:
            out.update({"push": True, "motivo": "publicado em " + remoto})
            return parcial, out
        out["motivo"] = "push recusado: " + " ".join(p.stderr.split())[:200]
        if tentativa == 0 and ("non-fast-forward" in p.stderr or "fetch first" in p.stderr
                               or "rejected" in p.stderr):
            continue
        break
    return SEM_PUSH, out


# ==========================================================================================
# Entrega entre jobs (GitHub Actions: a IA roda sem credencial de escrita)
# ==========================================================================================

LIMITE_ENTREGA = 512 * 1024 * 1024


def entrega_exportar(raiz: Path | str, tarefa: Tarefa, saida: Path | str) -> dict[str, Any]:
    """Empacota (tar) o que a mente gravou nos caminhos da tarefa: arquivos novos ou alterados
    e a lista dos apagados. Nada fora dos caminhos entra."""
    import tarfile

    raiz = Path(raiz)
    estado = estado_dos_caminhos(raiz, tuple(tarefa.caminhos) + tuple(tarefa.caminhos_exclusivos))
    arquivos = sorted(p for p, h in estado.items() if h is not None)
    apagados = sorted(p for p, h in estado.items() if h is None)
    man = {"versao": 1, "tarefa": tarefa.id, "head": git_head(raiz), "arquivos": arquivos,
           "apagados": apagados}
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(man, ensure_ascii=False, indent=1).encode("utf-8")
    with tarfile.open(saida, "w") as tar:
        info = tarfile.TarInfo("manifesto.json")
        info.size = len(texto)
        import io

        tar.addfile(info, io.BytesIO(texto))
        for rel in arquivos:
            tar.add(raiz / rel, arcname="arquivos/" + rel, recursive=False)
    return {"pacote": saida.as_posix(), **{k: man[k] for k in ("tarefa", "head")},
            "arquivos": len(arquivos), "apagados": len(apagados)}


def _rel_seguro(rel: str, caminhos: Sequence[str]) -> bool:
    partes = Path(rel).parts
    return (bool(rel) and not rel.startswith(("/", "\\")) and ".." not in partes
            and "\\" not in rel and ":" not in rel and ".git" not in partes
            and _no_livro(rel, caminhos))


def entrega_importar(raiz: Path | str, tarefa: Tarefa, pacote: Path | str
                     ) -> tuple[int, dict[str, Any]]:
    """Aplica um pacote de :func:`entrega_exportar` no clone limpo do publicador. Recusa
    tudo o que não for arquivo comum dentro dos caminhos da tarefa (sem ligações simbólicas,
    sem ``..``, sem ``.git``); nada é executado."""
    import tarfile

    raiz = Path(raiz).resolve()
    caminhos = tuple(tarefa.caminhos) + tuple(tarefa.caminhos_exclusivos)
    try:
        tar = tarfile.open(pacote, "r")
    except (OSError, tarfile.TarError) as exc:
        return CONFIG, {"motivo": f"pacote ilegível: {exc}"}
    with tar:
        membros = tar.getmembers()
        try:
            man = json.loads(tar.extractfile("manifesto.json").read().decode("utf-8"))
        except (KeyError, AttributeError, ValueError) as exc:
            return CONFIG, {"motivo": f"pacote sem manifesto válido: {exc}"}
        if man.get("tarefa") != tarefa.id:
            return CONFIG, {"motivo": f"pacote de outra tarefa: {man.get('tarefa')!r}"}
        recusados, aplicar, total = [], [], 0
        for m in membros:
            if m.name == "manifesto.json":
                continue
            rel = m.name.removeprefix("arquivos/")
            if (not m.name.startswith("arquivos/") or not m.isfile()
                    or not _rel_seguro(rel, caminhos)):
                recusados.append(m.name)
                continue
            total += m.size
            aplicar.append((rel, m))
        apagados = [str(x) for x in man.get("apagados") or []]
        recusados += [a for a in apagados if not _rel_seguro(a, caminhos)]
        if recusados or total > LIMITE_ENTREGA:
            return FORA_DO_ESCOPO, {"motivo": "pacote recusado: itens fora dos caminhos da tarefa "
                                              "ou que não são arquivos comuns",
                                    "recusados": recusados[:20], "bytes": total}
        for rel, m in aplicar:
            destino = raiz / rel
            for pai in [destino, *destino.parents]:
                if pai == raiz:
                    break
                if pai.is_symlink():
                    return FORA_DO_ESCOPO, {"motivo": f"ligação simbólica no caminho: {rel}"}
            destino.parent.mkdir(parents=True, exist_ok=True)
            dados = tar.extractfile(m)
            if dados is None:
                return FORA_DO_ESCOPO, {"motivo": f"membro ilegível: {rel}"}
            destino.write_bytes(dados.read())
        for rel in apagados:
            alvo = raiz / rel
            if alvo.is_file() and not alvo.is_symlink():
                alvo.unlink()
    return OK, {"tarefa": tarefa.id, "head_da_mente": man.get("head"), "arquivos": len(aplicar),
                "apagados": len(apagados)}


# ==========================================================================================
# Registrar, transferir e janela de troca
# ==========================================================================================


def _em_worktree(raiz: Path | str) -> bool:
    gd = _ok(git(["rev-parse", "--absolute-git-dir"], raiz))
    common = _ok(git(["rev-parse", "--path-format=absolute", "--git-common-dir"], raiz))
    return bool(gd and common and Path(gd).resolve() != Path(common).resolve())


def registrar_local(raiz: Path | str, como: str, harness: str | None = None, *,
                    forcar: bool = False) -> tuple[int, dict[str, Any]]:
    if como not in EXECUTORES or como == "nenhum":
        return CONFIG, {"motivo": f"executor inválido: {como!r}"}
    ramo = _ok(git(["branch", "--show-current"], raiz))
    if not forcar and (_em_worktree(raiz) or ramo != "main"):
        return CONFIG, {"motivo": "registre só no clone dedicado às rotinas (ramo main, fora de "
                                  "worktree); use --forcar se tiver certeza"}
    path = Path(raiz) / LOCAL_YAML
    path.parent.mkdir(parents=True, exist_ok=True)
    dados = {"executor": como, "harness": harness or "claude-code", "clone_dedicado": True,
             "registrado_em": datetime.now(UTC).isoformat(timespec="seconds")}
    path.write_text("# identidade deste clone para o CDP (ignorado pelo git)\n"
                    + yaml.safe_dump(dados, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return OK, {"arquivo": path.as_posix(), **dados}


def _cabecalho(texto: str) -> str:
    linhas = []
    for ln in texto.splitlines():
        if ln.startswith("#") or not ln.strip():
            linhas.append(ln)
        else:
            break
    return "\n".join(linhas).rstrip() + "\n"


def transferir(raiz: Path | str, para: str, por: str, motivo: str, *,
               harness: str | None = None, agora: datetime | None = None,
               env: Mapping[str, str] | None = None, checar_trava: bool = True
               ) -> tuple[int, dict[str, Any]]:
    """Reescreve ``executor.yaml`` para ``para`` (o commit e o push ficam com o humano)."""
    env = os.environ if env is None else env
    if para not in EXECUTORES:
        return CONFIG, {"motivo": f"executor inválido: {para!r}"}
    if env.get("CDP_EXECUTOR"):
        return CONFIG, {"motivo": "recusado dentro de uma rotina (CDP_EXECUTOR definido): a troca "
                                  "de executor é decisão humana, numa sessão de operador"}
    if len(motivo.strip()) < 10 or not por.strip():
        return CONFIG, {"motivo": "informe --por e um --motivo com pelo menos 10 caracteres"}
    agora = agora or datetime.now(UTC)
    if checar_trava:
        estado, _, erro = trava_ler(raiz, env)
        if not erro and _ocupada(estado, agora):
            return CONFIG, {"motivo": f"trava ocupada por {estado.get('tarefa')} até "
                                      f"{_hhmm(estado.get('expira'))}: espere ou escolha outra "
                                      "janela (`cdp executor janela`)"}
    path = Path(raiz) / EXECUTOR_PADRAO
    texto = path.read_text(encoding="utf-8")
    atual = ler_executor(texto)
    novo = {"versao": 1, "executor": para,
            "harness": harness or atual.get("harness") or "claude-code",
            "desde": agora.astimezone(FUSO).isoformat(timespec="seconds"), "por": por.strip(),
            "motivo": " ".join(motivo.split()),
            "anterior": {"executor": atual["executor"],
                         "ate": agora.astimezone(FUSO).isoformat(timespec="seconds")}}
    corpo = yaml.safe_dump(novo, allow_unicode=True, sort_keys=False, width=100)
    path.write_text(_cabecalho(texto) + corpo, encoding="utf-8", newline="\n")
    return OK, {"arquivo": path.as_posix(), "de": atual["executor"], "para": para,
                "proximos_passos": [
                    f"git add {EXECUTOR_PADRAO.as_posix()}",
                    f'git commit -m "CDP: executor → {para}" -- {EXECUTOR_PADRAO.as_posix()}',
                    "git push origin HEAD:main"]}


def janela(raiz: Path | str, *, rot: Any, rt: Any, agora: datetime,
           env: Mapping[str, str] | None = None, horizonte_min: int = 90) -> dict[str, Any]:
    """Agora é uma janela segura para trocar o executor?"""
    from .rotinas import avaliar_gate, contexto_do_runtime
    from .workflow.agenda import agenda

    motivos = []
    fim = agora + timedelta(minutes=horizonte_min)
    for q, t in rot.proximas(agora, 40):
        if q <= fim and t.exclusiva:
            motivos.append(f"{t.id} dispara às {q.astimezone(FUSO):%H:%M}")
    estado, _, erro = trava_ler(raiz, env)
    if erro:
        motivos.append(f"trava ilegível: {erro}")
    elif _ocupada(estado, agora):
        motivos.append(f"trava ocupada por {estado.get('tarefa')}")
    ag = agenda(rt, agora)
    ctx = contexto_do_runtime(rt, agora)
    for g in ("semanal", "diario"):
        d = avaliar_gate(g, ag, ctx)
        if d.executar:
            motivos.append(f"trabalho pendente ({g}): {d.motivo}")
    return {"segura": not motivos, "motivos": motivos,
            "agora_brasilia": agora.astimezone(FUSO).isoformat(timespec="minutes")}


# ==========================================================================================
# CLI
# ==========================================================================================


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _aware(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=FUSO)


def _tarefa(args: argparse.Namespace) -> Tarefa:
    from .rotinas import ROTINAS_PADRAO, carregar

    return carregar(Path(args.raiz) / (getattr(args, "rotinas", None) or ROTINAS_PADRAO)
                    ).tarefa(args.tarefa)


def cmd_executor(args: argparse.Namespace) -> int:
    raiz = Path(args.raiz)
    a = args.action
    if a == "mostrar":
        code, info = verificar(raiz, None, remoto=args.remoto)
        _print(info)
        return 0 if code in (OK, OUTRO_EXECUTOR, PAUSADO, IDENTIDADE_DESCONHECIDA) else code
    if a == "verificar":
        t = _tarefa(args) if args.tarefa else None
        code, info = verificar(raiz, t, remoto=args.remoto)
        _print({"codigo": code, **info})
        return code
    if a == "registrar":
        code, info = registrar_local(raiz, args.como, args.harness, forcar=args.forcar)
        _print(info)
        return code
    if a == "transferir":
        code, info = transferir(raiz, args.para, args.por, args.motivo, harness=args.harness)
        _print(info)
        return code
    from .rotinas import ROTINAS_PADRAO, carregar
    from .workflow.runtime import Runtime

    rot = carregar(raiz / ROTINAS_PADRAO)
    out = janela(raiz, rot=rot, rt=Runtime.from_args(args),
                 agora=args.agora or datetime.now(FUSO))
    _print(out)
    return 0 if out["segura"] else 1


def cmd_trava(args: argparse.Namespace) -> int:
    raiz = Path(args.raiz)
    agora = getattr(args, "agora", None) or datetime.now(UTC)
    if args.action == "ver":
        estado, ponta, erro = trava_ler(raiz)
        _print({"trava": estado, "ponta": ponta, "erro": erro,
                "ocupada": _ocupada(estado, agora)})
        return 0 if not erro else SEM_PUSH
    if args.action == "adquirir":
        out = trava_adquirir(raiz, _tarefa(args), ttl_min=args.ttl,
                             esperar_min=args.esperar_min or 0, trava_id=args.id)
        _print(out)
        return {"adquirida": 0, "ocupada_por_outro": 10}.get(out["estado"], SEM_PUSH)
    if args.action == "renovar":
        out = trava_renovar(raiz, args.id, ttl_min=args.ttl, agora=agora)
        _print(out)
        return 0 if out["estado"] == "renovada" else 1
    out = trava_liberar(raiz, args.id, agora=agora)
    _print(out)
    return 0 if out["estado"] in ("liberada", "nao_detentor") else SEM_PUSH


def cmd_sincronizar(args: argparse.Namespace) -> int:
    out = sincronizar(Path(args.raiz), executar=args.executar)
    _print(out)
    return 0 if out["acao"] != "parar" else 1


def cmd_publicar(args: argparse.Namespace) -> int:
    from .workflow.runtime import Runtime

    t = _tarefa(args)
    msg = args.mensagem
    if args.mensagem_automatica or not msg:
        msg = f"CDP: {t.id} {datetime.now(FUSO):%Y-%m-%d %H:%M}"
    code, out = publicar(Path(args.raiz), t, msg, rt=Runtime.from_args(args),
                         sem_push=args.sem_push, execucao=args.execucao, trava=args.trava,
                         sem_trava=args.sem_trava, mente=args.mente)
    _print(out)
    return code


def cmd_entrega(args: argparse.Namespace) -> int:
    t = _tarefa(args)
    if args.action == "exportar":
        _print(entrega_exportar(Path(args.raiz), t, args.saida))
        return 0
    code, out = entrega_importar(Path(args.raiz), t, args.pacote)
    _print(out)
    return code


def registrar(sub: argparse._SubParsersAction) -> None:
    """Registra ``executor``, ``trava``, ``sincronizar`` e ``publicar`` no parser principal."""
    e = sub.add_parser("executor", help="escritor único: quem grava o livro (configs/cdp/"
                                        "executor.yaml)")
    esub = e.add_subparsers(dest="action", required=True)
    for nome, ajuda in (("mostrar", "executor designado × este ambiente"),
                        ("verificar", "este ambiente pode gravar? (0 = sim)"),
                        ("registrar", "grava a identidade deste clone em .cdp/local.yaml"),
                        ("transferir", "troca o executor (sessão de operador; humano)"),
                        ("janela", "agora é seguro trocar o executor?")):
        s = esub.add_parser(nome, help=ajuda)
        s.add_argument("--raiz", default=".")
        s.set_defaults(func=cmd_executor)
        if nome in ("mostrar", "verificar"):
            s.add_argument("--remoto", action="store_true", help="relê origin/main")
        if nome == "verificar":
            s.add_argument("--tarefa", default=None)
            s.add_argument("--rotinas", default=None)
        if nome == "registrar":
            s.add_argument("--como", required=True, choices=[x for x in EXECUTORES
                                                             if x != "nenhum"])
            s.add_argument("--harness", choices=HARNESS_INFO, default=None)
            s.add_argument("--forcar", action="store_true")
        if nome == "transferir":
            s.add_argument("--para", required=True, choices=EXECUTORES)
            s.add_argument("--por", required=True)
            s.add_argument("--motivo", required=True)
            s.add_argument("--harness", choices=HARNESS_INFO, default=None)
        if nome == "janela":
            s.add_argument("--agora", type=_aware, default=None)

    t = sub.add_parser("trava", help="trava distribuída das rotinas (ramo cdp-trava)")
    tsub = t.add_subparsers(dest="action", required=True)
    s = tsub.add_parser("ver", help="estado da trava")
    s.add_argument("--raiz", default=".")
    s.set_defaults(func=cmd_trava)
    s = tsub.add_parser("adquirir", help="adquire a trava para uma tarefa")
    s.add_argument("--raiz", default=".")
    s.add_argument("--tarefa", required=True)
    s.add_argument("--rotinas", default=None)
    s.add_argument("--ttl", type=int, default=None, help="validade em minutos")
    s.add_argument("--esperar-min", type=float, default=0,
                   help="espera, em minutos, enquanto outra execução segura a trava")
    s.add_argument("--id", default=None, help="reentrada: id da trava já desta execução")
    s.set_defaults(func=cmd_trava)
    for nome in ("renovar", "liberar"):
        s = tsub.add_parser(nome, help=f"{nome} a trava desta execução")
        s.add_argument("--raiz", default=".")
        s.add_argument("--id", required=True)
        if nome == "renovar":
            s.add_argument("--ttl", type=int, default=None,
                           help="validade em minutos (padrão: a da tarefa; nunca encolhe)")
        s.set_defaults(func=cmd_trava)

    s = sub.add_parser("sincronizar", help="classifica o remoto (seguir/pull/parar) e, com "
                                           "--executar, mescla sem reescrever")
    s.add_argument("--raiz", default=".")
    s.add_argument("--executar", action="store_true")
    s.add_argument("--tarefa", default=None, help="(informativo)")
    s.set_defaults(func=cmd_sincronizar)

    s = sub.add_parser("publicar", help="commit dos caminhos da tarefa + push em main "
                                        "(verify, executor, escopo; nunca --force)")
    s.add_argument("--raiz", default=".")
    s.add_argument("--tarefa", required=True)
    s.add_argument("--rotinas", default=None)
    s.add_argument("--mensagem", default=None, help='mensagem do commit (começa com "CDP: ")')
    s.add_argument("--mensagem-automatica", action="store_true",
                   help="mensagem padrão (executores sem IA, ex.: GitHub Actions)")
    s.add_argument("--execucao", default=None, help="id da execução (padrão: a última da tarefa)")
    s.add_argument("--trava", default=None,
                   help="id da trava do gate (escritores exclusivos; padrão: CDP_TRAVA_ID ou o "
                        "registro da execução)")
    s.add_argument("--mente", default=None,
                   help="harness que gravou (trailer CDP-Harness quando CDP_HARNESS falta)")
    s.add_argument("--sem-trava", action="store_true",
                   help="só sessão de operador: publica um escritor exclusivo sem a trava")
    s.add_argument("--sem-push", action="store_true", help="só o commit local")
    s.set_defaults(func=cmd_publicar)

    e = sub.add_parser("entrega", help="pacote do que a mente gravou (GitHub Actions: passa do "
                                       "job da IA, sem escrita, ao job publicador)")
    esub = e.add_subparsers(dest="action", required=True)
    s = esub.add_parser("exportar", help="empacota os arquivos alterados nos caminhos da tarefa")
    s.add_argument("--raiz", default=".")
    s.add_argument("--tarefa", required=True)
    s.add_argument("--rotinas", default=None)
    s.add_argument("--saida", required=True)
    s.set_defaults(func=cmd_entrega)
    s = esub.add_parser("importar", help="aplica um pacote (só arquivos comuns nos caminhos)")
    s.add_argument("--raiz", default=".")
    s.add_argument("--tarefa", required=True)
    s.add_argument("--rotinas", default=None)
    s.add_argument("--pacote", required=True)
    s.set_defaults(func=cmd_entrega)


__all__ = ["EXECUTORES", "ErroExecutor", "carregar_executor", "entrega_exportar",
           "entrega_importar", "estado_dos_caminhos", "git", "git_head", "identidade",
           "janela", "proteger_ensaio", "publicar", "registrar", "registrar_local", "sessao_url", "sincronizar",
           "trailers", "transferir", "trava_adquirir", "trava_ler", "trava_liberar",
           "trava_renovar", "verificar"]
