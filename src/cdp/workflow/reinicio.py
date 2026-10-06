"""Pré-início do fundo (DESIGN §15.2, workstream F'). Operação interna, uma única vez; nunca
aparece em texto para o investidor.

``cdp reinicio [--executar] [--pesquisa DIR]`` — rodado SÓ pelo clone da rotina (escritor
único), na primeira vez em que ``cdp agenda`` informa ``reinicio.pendente``: o livro vivo tem
chaves (semanas do livro ou registros diários) anteriores a ``fund.inception_date`` e ainda não
tem gênese. Sem ``--executar`` é uma simulação: imprime o plano (cada arquivo a remover com o
sha256, os caminhos mantidos e o motivo) e não grava nada.

Com ``--executar``:

1. Guardas (recusa com código 1, sem gravar): nenhuma área temporária de uma execução
   interrompida (``.cdp_reinicio.tmp`` ao lado do livro — verificada antes de qualquer outra
   coisa, inclusive da gênese e das chaves); nenhuma chave viva ``>= fund.inception_date``;
   kill switch desligado (o pré-início nunca desliga o kill switch: só o gestor, à mão);
   ``cdp verify`` íntegro antes.
2. Estado anterior (só na saída do comando, para o commit da rotina): sha256 de
   ``book/audit_log.jsonl``, a lista dos arquivos removidos com o sha256 de cada um (o
   manifesto, com caminhos relativos à pasta que contém o livro, impresso e nunca gravado na
   árvore viva; o commit da rotina leva só o sha256 dele) e ``git rev-parse HEAD`` quando houver
   repositório. A trilha anterior continua íntegra no histórico público do repositório.
3. Remove, de forma preparada (cada caminho é movido para a área temporária ao lado do livro;
   qualquer falha ou interrupção devolve tudo ao lugar), os relatórios derivados da carteira com
   data anterior ao início (``reports/{daily,weekly,risk,semanal}/<data>``), o material de
   pesquisa da mente com data anterior ao início (``pesquisa/<data>``) e, por último, todo o
   conteúdo de ``book/`` (as semanas e os ``track_record*``, que identificam o livro anterior, no
   fim). Mantém a pesquisa de metodologia (``reports/backtest``), qualquer outra pasta de
   ``reports/`` e ``data/`` (dados públicos de mercado). O painel (``artifacts/painel``) é
   regenerado por ``cdp painel``, que só lê o livro e os relatórios.
4. Abre a trilha nova: ``book/genese.json`` e o evento ``FUND_GENESIS`` (seq 0) com
   ``{inception_date, config_hash, codigo, ancora_sha256}`` — ``codigo`` é o commit do código
   (``git rev-parse HEAD``) e ``ancora_sha256`` o sha256 de ``book/audit_log.jsonl`` nesse commit
   (``None`` sem trilha), conferível por qualquer um no histórico do repositório.
5. ``cdp verify`` íntegro depois; senão, desfaz tudo e recusa.

Idempotente: com a gênese gravada, uma nova chamada não altera nada e diz por quê.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..hashing import sha256_file, sha256_obj
from .book import GENESIS_EVENT, GENESIS_FILE

if TYPE_CHECKING:  # pragma: no cover
    from .runtime import Runtime

RECUSADO = 1

STAGING_NAME = ".cdp_reinicio.tmp"
"""Área temporária (irmã do livro, mesmo sistema de arquivos) da remoção preparada."""
REPORT_DIRS_CARTEIRA = ("daily", "weekly", "risk", "semanal")
"""Subpastas de ``reports/`` derivadas da carteira: pastas ``<AAAA-MM-DD>`` anteriores ao
início são removidas."""
REPORT_DIRS_METODOLOGIA = ("backtest",)
"""Subpastas de ``reports/`` de pesquisa de metodologia (calibração): sempre mantidas."""
DEFAULT_PESQUISA = Path("pesquisa")
GENESIS_ACTOR = "CDP"
AUDIT_NAME = "audit_log.jsonl"


def _data(nome: str) -> date | None:
    try:
        return date.fromisoformat(nome)
    except ValueError:
        return None


def _rotulo(path: Path, base: Path) -> str:
    """Caminho como aparece no manifesto: relativo a ``base`` (a pasta que contém o livro, a
    raiz do repositório) — o mesmo em qualquer pasta corrente, para o sha256 da lista ser
    reproduzível; absoluto só fora de ``base``."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _arquivos(path: Path) -> list[Path]:
    if path.is_file() or path.is_symlink():
        return [path]
    return sorted(p for p in path.rglob("*") if p.is_file() or p.is_symlink())


@dataclass
class Plano:
    """Plano do pré-início (determinístico; só leitura)."""

    inicio: date
    estado: str  # "pendente" | "iniciado" | "nada" | "conflito"
    motivo: str
    base: Path
    alvos: list[Path] = field(default_factory=list)
    mantidos: list[dict[str, str]] = field(default_factory=list)
    chaves_anteriores: list[date] = field(default_factory=list)
    chaves_posteriores: list[date] = field(default_factory=list)
    genese: dict[str, Any] | None = None

    def manifesto(self) -> list[dict[str, str]]:
        """Cada arquivo a remover com o sha256 (ordem de caminho)."""
        out = [{"caminho": _rotulo(f, self.base), "sha256": sha256_file(f)}
               for alvo in self.alvos for f in _arquivos(alvo)]
        return sorted(out, key=lambda x: x["caminho"])


def chaves_vivas(rt: Runtime) -> list[date]:
    """Chaves do livro vivo: semanas (pastas ``AAAA-MM-DD``) e datas dos registros diários."""
    root = Path(rt.book_root)
    out: set[date] = set()
    if not root.is_dir():
        return []
    for p in root.iterdir():
        d = _data(p.name) if p.is_dir() else None
        if d is not None:
            out.add(d)
    for sub in ("track_record", "track_record_shadow"):
        rec = root / sub / "records"
        if rec.is_dir():
            out.update(d for d in (_data(p.stem) for p in rec.glob("*.json")) if d is not None)
    return sorted(out)


def _genese_registrada(rt: Runtime) -> dict[str, Any] | None:
    """Payload da gênese (arquivo) ou um marcador se só o evento existir; ``None`` sem gênese."""
    root = Path(rt.book_root)
    path = root / GENESIS_FILE
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {"ilegivel": True}
    audit = root / AUDIT_NAME
    if audit.exists():
        from ..audit import AuditLog

        try:
            if any(ev.event_type == GENESIS_EVENT for ev in AuditLog(audit).events()):
                return {"sem_arquivo": True}
        except ValueError:
            return None
    return None


def _base(rt: Runtime) -> Path:
    """Pasta que contém o livro (raiz do repositório): base dos caminhos do manifesto."""
    return Path(rt.book_root).resolve().parent


def _staging(rt: Runtime) -> Path:
    return _base(rt) / STAGING_NAME


def _motivo_interrompida(staging: Path) -> str:
    return (f"execução interrompida do pré-início (área temporária {staging}): intervenção "
            "manual — confira o livro, os relatórios e a área temporária (cdp reinicio recusa)")


MOTIVO_KILL_SWITCH = ("kill switch ativo: intervenção manual (o pré-início não desliga o kill "
                      "switch; só o gestor decide); recusado")
_PENDENTE_KILL_SWITCH = ("kill switch ativo: intervenção manual (cdp reinicio recusa: o pré-início "
                         "não desliga o kill switch; só o gestor decide)")


def situacao(rt: Runtime) -> dict[str, Any]:
    """``{pendente, motivo}`` para a agenda (leve: sem hashes).

    A área temporária de uma execução interrompida vem antes de tudo: com ela, o livro pode
    estar vazio (sem chaves) e sem gênese, e só ela denuncia a interrupção."""
    inicio = rt.cfg.fund.inception_date
    staging = _staging(rt)
    if staging.exists():
        return {"pendente": True, "motivo": _motivo_interrompida(staging)}
    try:
        if _genese_registrada(rt) is not None:
            return {"pendente": False, "motivo": None}
        chaves = chaves_vivas(rt)
    except OSError as exc:  # pragma: no cover - disco
        return {"pendente": False, "motivo": f"livro ilegível: {exc}"}
    antes = [d for d in chaves if d < inicio]
    if not antes:
        return {"pendente": False, "motivo": None}
    depois = [d for d in chaves if d >= inicio]
    if depois:
        return {"pendente": True,
                "motivo": (f"livro com chaves anteriores e posteriores à data de início "
                           f"({inicio}): intervenção manual (cdp reinicio recusa)")}
    if rt.kill_switch_active():
        return {"pendente": True, "motivo": _PENDENTE_KILL_SWITCH}
    return {"pendente": True,
            "motivo": (f"livro com chaves anteriores à data de início ({inicio}): rode "
                       "`cdp reinicio --executar` antes de qualquer outra etapa")}


def _alvos_relatorios(reports: Path, inicio: date, base: Path
                      ) -> tuple[list[Path], list[dict[str, str]]]:
    alvos: list[Path] = []
    mantidos: list[dict[str, str]] = []
    if not reports.is_dir():
        return alvos, mantidos
    for sub in sorted(reports.iterdir()):
        if not sub.is_dir():
            mantidos.append({"caminho": _rotulo(sub, base), "motivo": "arquivo solto em reports/"})
            continue
        if sub.name in REPORT_DIRS_METODOLOGIA:
            mantidos.append({"caminho": _rotulo(sub, base),
                             "motivo": "pesquisa de metodologia (calibração); não deriva da "
                                       "carteira"})
            continue
        if sub.name not in REPORT_DIRS_CARTEIRA:
            mantidos.append({"caminho": _rotulo(sub, base),
                             "motivo": "pasta não derivada da carteira"})
            continue
        for child in sorted(sub.iterdir()):
            d = _data(child.name)
            if d is not None and d < inicio:
                alvos.append(child)
            else:
                mantidos.append({"caminho": _rotulo(child, base),
                                 "motivo": "sem data anterior ao início"})
    return alvos, mantidos


def _alvos_pesquisa(pesquisa: Path, inicio: date, base: Path
                    ) -> tuple[list[Path], list[dict[str, str]]]:
    alvos: list[Path] = []
    mantidos: list[dict[str, str]] = []
    if not pesquisa.is_dir():
        return alvos, mantidos
    for child in sorted(pesquisa.iterdir()):
        d = _data(child.name)
        if d is not None and d < inicio:
            alvos.append(child)
        else:
            mantidos.append({"caminho": _rotulo(child, base),
                             "motivo": "sem data anterior ao início"})
    return alvos, mantidos


def _alvos_livro(book: Path) -> list[Path]:
    """Conteúdo de ``book/`` na ordem de remoção: as semanas e os ``track_record*`` (as chaves
    que identificam o livro anterior) por último, para uma interrupção nunca deixar um livro
    sem chaves e sem gênese (a área temporária também denuncia a interrupção)."""
    if not book.is_dir():
        return []

    def chave(p: Path) -> bool:
        return (p.is_dir() and _data(p.name) is not None) or p.name.startswith("track_record")

    filhos = sorted(book.iterdir())
    return [p for p in filhos if not chave(p)] + [p for p in filhos if chave(p)]


def plano(rt: Runtime, pesquisa: Path | str = DEFAULT_PESQUISA) -> Plano:
    """Plano do pré-início (não grava nada)."""
    inicio = rt.cfg.fund.inception_date
    book = Path(rt.book_root)
    base = _base(rt)
    staging = _staging(rt)
    if staging.exists():
        return Plano(inicio, "conflito", _motivo_interrompida(staging), base)
    genese = _genese_registrada(rt)
    if genese is not None:
        return Plano(inicio, "iniciado",
                     f"livro já aberto na data de início ({genese.get('inception_date', inicio)}); "
                     "nada a fazer", base, genese=genese)
    chaves = chaves_vivas(rt)
    antes = [d for d in chaves if d < inicio]
    depois = [d for d in chaves if d >= inicio]
    if not antes:
        return Plano(inicio, "nada", "nenhuma chave do livro anterior à data de início; nada a "
                                     "fazer", base, chaves_posteriores=depois)
    r_alvos, r_mant = _alvos_relatorios(Path(rt.reports_root), inicio, base)
    p_alvos, p_mant = _alvos_pesquisa(Path(pesquisa), inicio, base)
    alvos = r_alvos + p_alvos + _alvos_livro(book)
    mantidos = [{"caminho": _rotulo(Path(rt.market_root), base),
                 "motivo": "dados públicos de mercado"}, *r_mant, *p_mant]
    if depois:
        return Plano(inicio, "conflito",
                     f"o livro tem chaves na data de início ou depois ({', '.join(map(str, depois))});"
                     " recusado", base, alvos, mantidos, antes, depois)
    if rt.kill_switch_active():
        return Plano(inicio, "conflito", MOTIVO_KILL_SWITCH, base, alvos, mantidos, antes, depois)
    return Plano(inicio, "pendente",
                 f"{len(antes)} chave(s) do livro anteriores à data de início ({inicio})",
                 base, alvos, mantidos, antes, depois)


def _git_head(cwd: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True,
                             text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) >= 40 else None


def _rollback(staging: Path, alvos: list[Path], novos: list[Path]) -> list[str]:
    """Desfaz: apaga o que foi criado e devolve ao lugar tudo o que está na área temporária
    (``<i>_<nome>`` ⇒ ``alvos[i]``; pelo conteúdo da área, não por uma lista em memória, para
    não perder um caminho movido no instante de uma interrupção). Nunca apaga a área com
    conteúdo: o que não voltar fica nela (e a guarda da próxima execução denuncia)."""
    erros: list[str] = []
    for p in novos:
        try:
            p.unlink(missing_ok=True)
        except OSError as exc:
            erros.append(f"{p}: {exc}")
    for destino in sorted(staging.iterdir(), reverse=True) if staging.is_dir() else []:
        try:
            origem = alvos[int(destino.name[:4])]
            origem.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destino), str(origem))
        except (OSError, ValueError, IndexError) as exc:
            erros.append(f"{destino}: {exc}")
    try:
        if staging.is_dir():
            staging.rmdir()  # só vazia
    except OSError as exc:
        erros.append(f"{staging}: {exc}")
    return erros


def executar(rt: Runtime, pesquisa: Path | str = DEFAULT_PESQUISA) -> tuple[int, dict[str, Any]]:
    """Executa o pré-início (ver docstring do módulo). Devolve ``(código, relatório)``."""
    p = plano(rt, pesquisa)
    out = _relatorio(p, executado=False)
    if p.estado in ("iniciado", "nada"):
        return 0, out
    if p.estado == "conflito":
        return RECUSADO, out
    staging = _staging(rt)
    ok, msgs = rt.verify_all()
    out["verificacao_antes"] = msgs
    if not ok:
        out["motivo"] = "verificação de integridade falhou antes do pré-início; recusado"
        return RECUSADO, out

    book = Path(rt.book_root)
    audit_path = book / AUDIT_NAME
    manifesto = out["remover"]
    git_head = _git_head(p.base)
    ancora = sha256_file(audit_path) if audit_path.exists() else None
    estado_anterior = {"git_head": git_head, "audit_log_sha256": ancora,
                       "n_arquivos_removidos": len(manifesto),
                       "lista_sha256": sha256_obj(manifesto)}
    # Gênese: só o necessário para conferir a abertura do livro (o resto fica na saída do
    # comando e no commit da rotina).
    genese = {"inception_date": p.inicio, "config_hash": rt.cfg.config_hash(),
              "codigo": git_head, "ancora_sha256": ancora}

    staging.mkdir(parents=True, exist_ok=False)
    novos: list[Path] = []
    try:
        for i, alvo in enumerate(p.alvos):
            shutil.move(str(alvo), str(staging / f"{i:04d}_{alvo.name}"))
        from .book import Book, _write_exclusive
        from .book import dump_json as _dump

        book.mkdir(parents=True, exist_ok=True)
        gpath = book / GENESIS_FILE
        payload = json.loads(json.dumps(genese, default=str))
        novos.append(gpath)
        _write_exclusive(gpath, _dump(payload))
        novos.append(audit_path)
        Book(book, config=rt.cfg).audit.append(
            GENESIS_EVENT, GENESIS_ACTOR, payload,
            summary=(f"Gênese do fundo: carteira inaugural em {p.inicio:%d/%m/%Y}, ao preço de "
                     "fechamento."), ts=rt.now())
        ok, msgs = rt.verify_all()
        out["verificacao_depois"] = msgs
        if not ok:
            raise RuntimeError("verificação de integridade falhou depois do pré-início")
    except BaseException as exc:  # noqa: BLE001 - qualquer falha ou interrupção desfaz tudo
        erros = _rollback(staging, p.alvos, novos)
        if not isinstance(exc, Exception):  # Ctrl-C, SystemExit: desfeito; propaga
            raise
        out["motivo"] = f"falha ({type(exc).__name__}: {exc}); estado anterior restaurado"
        if erros:
            out["motivo"] += f"; ATENÇÃO, restauração incompleta: {'; '.join(erros)}"
        return RECUSADO, out
    shutil.rmtree(staging, ignore_errors=True)
    out.update({"executado": True, "estado": "iniciado",
                "motivo": f"livro aberto na data de início ({p.inicio}); trilha nova",
                "estado_anterior": estado_anterior, "genese": payload,
                "area_temporaria_restante": staging.exists()})
    return 0, out


def _relatorio(p: Plano, *, executado: bool) -> dict[str, Any]:
    manifesto = p.manifesto() if p.estado in ("pendente", "conflito") else []
    return {
        "executado": executado, "estado": p.estado, "motivo": p.motivo,
        "data_de_inicio": p.inicio, "carteira_inaugural": f"{p.inicio:%d/%m/%Y}",
        "chaves_anteriores": p.chaves_anteriores, "chaves_posteriores": p.chaves_posteriores,
        "caminhos": sorted(_rotulo(a, p.base) for a in p.alvos),
        "remover": manifesto, "n_arquivos": len(manifesto),
        "lista_sha256": sha256_obj(manifesto) if manifesto else None,
        "mantidos": p.mantidos,
    }


def cmd_reinicio(args: argparse.Namespace) -> int:
    """``cdp reinicio`` (``args.executar``: ``False`` = simulação sem gravar; ``args.book``,
    ``args.reports``, ``args.pesquisa``)."""
    from .runtime import Runtime

    rt = Runtime.from_args(args)
    pesquisa = Path(getattr(args, "pesquisa", None) or DEFAULT_PESQUISA)
    if args.executar:
        code, out = executar(rt, pesquisa)
    else:
        p = plano(rt, pesquisa)
        out = _relatorio(p, executado=False)
        code = RECUSADO if p.estado == "conflito" else 0
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return code


__all__ = ["DEFAULT_PESQUISA", "MOTIVO_KILL_SWITCH", "RECUSADO", "chaves_vivas",
           "REPORT_DIRS_CARTEIRA", "REPORT_DIRS_METODOLOGIA", "STAGING_NAME", "Plano",
           "cmd_reinicio", "executar", "plano", "situacao"]
