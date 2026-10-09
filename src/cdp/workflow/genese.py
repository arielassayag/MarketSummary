"""Abertura explícita de um livro vazio, no clone executor da própria réplica.

Não remove história, não reinicia um livro e não é chamado pela agenda. O plano só lê.
A execução exige registro de um gate exclusivo e sua trava distribuída vigente; o comando
não adquire, renova ou libera a trava, não publica e não desliga o kill switch.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..audit import GENESIS_HASH, AuditLog
from ..config import load_config
from ..hashing import sha256_obj
from .book import GENESIS_EVENT, GENESIS_FILE, Book, _write_exclusive, dump_json

if TYPE_CHECKING:
    from .runtime import Runtime

RECUSADO = 1
STAGING_NAME = ".cdp_genese.tmp"
AUDIT_NAME = "audit_log.jsonl"
_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40,64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def _book(rt: Runtime) -> Path:
    # A raiz do livro não é resolvida antes da guarda contra links simbólicos.
    return Path(rt.book_root).absolute()


def _base(rt: Runtime) -> Path:
    return _book(rt).parent.resolve()


def _genese_integra(book: Path, inicio: str) -> tuple[dict | None, str | None]:
    try:
        if any((book / n).is_symlink() for n in (GENESIS_FILE, AUDIT_NAME)):
            return None, "gênese e trilha precisam ser arquivos próprios, sem link simbólico"
        payload = json.loads((book / GENESIS_FILE).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("inception_date") != inicio:
            return None, "gênese ausente, inválida ou de outra data de início"
        if not _SHA.fullmatch(str(payload.get("config_hash", ""))):
            return None, "gênese sem hash válido da configuração"
        if not _COMMIT.fullmatch(str(payload.get("codigo", ""))):
            return None, "gênese sem commit válido do código"
        ancora = payload.get("ancora_sha256")
        if ancora is not None and not _SHA.fullmatch(str(ancora)):
            return None, "gênese com âncora inválida"
        # O diretório já existe: a leitura da trilha não cria o livro.
        audit = AuditLog(book / AUDIT_NAME)
        ok, msg = audit.verify_chain()
        events = audit.events()
        gens = [e for e in events if e.event_type == GENESIS_EVENT]
        if not ok or len(gens) != 1 or gens[0].seq != 0:
            return None, f"gênese/trilha inválida: {msg}"
        if gens[0].prev_hash != GENESIS_HASH or gens[0].payload_hash != sha256_obj(payload):
            return None, "arquivo de gênese não confere com o primeiro evento da trilha"
        ok_book, msgs = Book(book).verify_integrity()
        if not ok_book:
            return None, f"livro com gênese, mas sem integridade: {'; '.join(msgs)}"
        return payload, None
    except (OSError, ValueError, TypeError) as exc:
        return None, f"gênese/trilha ilegível ({type(exc).__name__})"


def plano(rt: Runtime) -> dict[str, Any]:
    """Classifica sem criar livro, relatório, área temporária ou evento."""
    book = _book(rt)
    inicio = rt.cfg.fund.inception_date.isoformat()
    out = {"executado": False, "estado": "vazio", "motivo": "livro vazio; abertura explícita",
           "data_de_inicio": inicio, "config_hash": rt.cfg.config_hash(),
           "arquivos_novos": [GENESIS_FILE, AUDIT_NAME], "remover": []}

    def recusar(motivo: str) -> dict[str, Any]:
        return {**out, "estado": "conflito", "motivo": motivo, "arquivos_novos": []}

    staging = _base(rt) / STAGING_NAME
    if staging.exists() or staging.is_symlink():
        return recusar("abertura interrompida: área temporária presente; intervenção humana")
    if book.is_symlink() or (book.exists() and not book.is_dir()):
        return recusar("o caminho do livro precisa ser um diretório próprio, sem link simbólico")
    if rt.kill_switch_active():
        return recusar("kill switch ativo; a abertura nunca o remove ou desliga")
    if not book.exists() or not any(book.iterdir()):
        return out
    if (book / GENESIS_FILE).is_file():
        payload, erro = _genese_integra(book, inicio)
        if erro:
            return recusar(erro)
        return {**out, "estado": "iniciado", "motivo": "livro já aberto; nenhuma alteração",
                "arquivos_novos": [], "genese": payload}
    return recusar("livro não vazio e sem gênese íntegra; não remover nem adotar história herdada")


def _autoridade(rt: Runtime, execucao: str | None, trava: str | None,
                env: Mapping[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    """Reutiliza identidade, registro e transporte da trava; falha fechada."""
    from .. import executor as ex
    from ..rotinas import carregar

    base = _base(rt)
    if env.get("CDP_ENSAIO") == "1":
        return None, "ensaio não autoriza abertura do livro da réplica"
    if not execucao or not _ID.fullmatch(execucao) or not trava or not _ID.fullmatch(trava):
        return None, "informe a execução registrada e a trava do gate exclusivo"
    code, ident = ex.verificar(base, env=env, remoto=True)
    if code:
        return None, ident.get("motivo") or "este ambiente não é o executor designado"
    if ident.get("remoto") == "indisponível":
        return None, "executor de origin/main indisponível; abertura recusada"
    cfg_path = base / "configs/cdp/fund.yaml"
    try:
        if cfg_path.is_symlink() or load_config(cfg_path).config_hash() != rt.cfg.config_hash():
            return None, "o mandato carregado difere do mandato do próprio clone executor"
        head = ex.git_head(base)
        if not head or not _COMMIT.fullmatch(head):
            return None, "o clone precisa de commit próprio com mandato e código"
        branch = ex.git(["branch", "--show-current"], base)
        remoto = ex.git(["rev-parse", "origin/main"], base)
        if branch.stdout.strip() != "main" or remoto.stdout.strip() != head:
            return None, "use o clone executor em main, sincronizado com origin/main"
        cfg_head = ex.git(["show", f"{head}:configs/cdp/fund.yaml"], base)
        if cfg_head.returncode or cfg_head.stdout != cfg_path.read_text(encoding="utf-8"):
            return None, "mandato não registrado no commit do próprio clone"
        dirty = ex.git(["status", "--porcelain", "--untracked-files=all", "--",
                        "src/cdp", "configs/cdp"], base)
        if dirty.returncode or dirty.stdout.strip():
            return None, "código ou configuração alterados; finalize o desenvolvimento antes"
        reg = ex.ler_execucao(base, execucao)
        if not isinstance(reg, dict) or reg.get("ensaio") or reg.get("sem_trava"):
            return None, "execução ausente, em ensaio ou sem trava; abertura recusada"
        tarefa = carregar(base / "configs/cdp/rotinas.yaml").tarefa(reg.get("tarefa"))
        if not tarefa.exclusiva or not tarefa.grava or "book" not in tarefa.caminhos:
            return None, "a execução precisa ser de tarefa exclusiva com escopo do livro"
        if reg.get("head") != head or reg.get("trava") != trava:
            return None, "a execução não corresponde ao commit e à trava atuais"
        estado, ponta, erro = ex.trava_ler(base, env)
        if erro or not estado or estado.get("estado") != "ocupada":
            return None, "trava distribuída indisponível ou livre; abertura recusada"
        if (estado.get("id") != trava or estado.get("tarefa") != tarefa.id
                or estado.get("executor") != ident["este_ambiente"]
                or estado.get("harness") != ident["harness"]):
            return None, "a trava não pertence à execução e ao executor informados"
        expira = datetime.fromisoformat(str(estado.get("expira")))
        if expira.tzinfo is None or expira.astimezone(UTC) <= rt.now():
            return None, "trava vencida ou sem fuso; abertura recusada"
        return {"codigo": head, "executor": ident["este_ambiente"],
                "execucao": execucao, "trava": trava, "ponta_trava": ponta}, None
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return None, f"autoridade/configuração inválida ({type(exc).__name__}); abertura recusada"


def executar(rt: Runtime, *, execucao: str | None = None, trava: str | None = None,
             env: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    """Abre somente livro vazio, após autorização explícita do chamador e guardas."""
    out = plano(rt)
    if out["estado"] == "conflito":
        return RECUSADO, out
    if out["estado"] == "iniciado":
        return 0, out
    ambiente = os.environ if env is None else env
    auth, erro = _autoridade(rt, execucao, trava, ambiente)
    if erro:
        return RECUSADO, {**out, "motivo": erro}
    assert auth is not None
    book = _book(rt)
    staging = _base(rt) / STAGING_NAME
    payload = {"inception_date": rt.cfg.fund.inception_date.isoformat(),
               "config_hash": rt.cfg.config_hash(), "codigo": auth["codigo"],
               "ancora_sha256": None}
    criada = False
    try:
        # Área exclusiva: jamais limpar uma área que já existia ou foi criada por outro.
        staging.mkdir(exist_ok=False)
        criada = True
        _write_exclusive(staging / GENESIS_FILE, dump_json(payload))
        Book(staging, config=rt.cfg).audit.append(
            GENESIS_EVENT, "CDP", payload,
            summary=(f"Gênese do fundo: carteira inaugural em {rt.cfg.fund.inception_date:%d/%m/%Y}, "
                     "ao preço de fechamento."), ts=rt.now())
        ok, msgs = Book(staging, config=rt.cfg).verify_integrity()
        if not ok:
            raise ValueError("a gênese preparada não passou na integridade do livro")
        # A trava e o estado são conferidos novamente antes da promoção atômica.
        auth_final, erro = _autoridade(rt, execucao, trava, ambiente)
        estado_final = plano_sem_staging(rt)
        if erro or auth_final != auth or estado_final["estado"] != "vazio":
            raise ValueError(erro or "autoridade ou livro mudou durante a abertura")
        os.rename(staging, book)  # ausência ou diretório vazio; nunca substitui conteúdo
    except BaseException as exc:  # noqa: BLE001 - interrupção não promove livro parcial
        if criada and staging.is_dir():
            shutil.rmtree(staging)
        if not isinstance(exc, Exception):
            raise
        return RECUSADO, {**out, "motivo": f"abertura recusada ({type(exc).__name__}: {exc})"}
    return 0, {**out, "estado": "iniciado", "executado": True,
               "motivo": "livro vazio aberto; gênese e primeiro evento íntegros",
               "genese": payload, "autoridade": auth, "integridade": msgs}


def plano_sem_staging(rt: Runtime) -> dict[str, Any]:
    """Confere apenas o destino na promoção; a área preparada pertence a esta chamada."""
    book = _book(rt)
    vazio = (not book.is_symlink() and (not book.exists()
              or (book.is_dir() and not any(book.iterdir()))))
    return {"estado": "vazio" if vazio and not rt.kill_switch_active() else "conflito"}


def cmd_genese(args: argparse.Namespace) -> int:
    from .runtime import Runtime

    rt = Runtime.from_args(args)
    if args.executar:
        code, out = executar(rt, execucao=args.execucao, trava=args.trava)
    else:
        out = plano(rt)
        code = RECUSADO if out["estado"] == "conflito" else 0
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return code
