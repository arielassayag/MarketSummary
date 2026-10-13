"""Recepção nominal de arquivos pelos leitores nativos, sem substituir ``open`` global.

Fora de um contexto recebido, os helpers mantêm a leitura legada. Dentro dele, somente
membros declarados podem ser lidos; o corpo usado pelo parser é o corpo recebido pelo FD.
"""

from __future__ import annotations

import hashlib
import io
import os
import stat
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path, PosixPath

_ATIVO: ContextVar[ReceptorArquivos | None] = ContextVar("cdp_receptor_leitura", default=None)
MAX_MEMBROS = 512
MAX_BYTES = 33554432


def validar_modo(somente_leitura: bool) -> bool:
    if type(somente_leitura) is not bool:
        raise TypeError("somente_leitura exige bool literal")
    return somente_leitura


def recusar_escrita(somente_leitura: bool = False) -> None:
    validar_modo(somente_leitura)
    if somente_leitura or _ATIVO.get() is not None:
        from .workflow.leitura_contratos import TentativaDeEfeitoLeitura

        raise TentativaDeEfeitoLeitura("Escrita/prepare/aquisição recusada no modo de leitura")


def em_leitura(somente_leitura: bool = False) -> bool:
    return validar_modo(somente_leitura) or _ATIVO.get() is not None


def ler_parquet(path, *args, **kwargs):
    import pandas as pd

    receiver = _ATIVO.get()
    if receiver is not None:
        return pd.read_parquet(io.BytesIO(receiver.ler(path)), *args, **kwargs)
    return pd.read_parquet(path, *args, **kwargs)


def fonte_arrow(path):
    receiver = _ATIVO.get()
    return io.BytesIO(receiver.ler(path)) if receiver is not None else path


def _path_exato(path: str | Path) -> Path:
    if type(path) is not str and type(path) is not PosixPath:
        raise TypeError("Path não é str/Path nativo exato")
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts:
        raise ValueError("Path deve ser absoluto sem travessia")
    return p


def _m6(st):
    return (
        st.st_dev,
        st.st_ino,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
        stat.S_IMODE(st.st_mode),
        st.st_nlink,
    )


def receber_fd(path: str | Path, limite: int = MAX_BYTES) -> tuple[bytes, tuple]:
    """Abre cada componente por dir_fd/O_NOFOLLOW; nenhuma resolução de symlink."""
    p = _path_exato(path)
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in p.parts[1:-1]:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = nxt
        fd = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limite:
                raise ValueError("Membro não regular ou excede limite")
            chunks, total = [], 0
            while True:
                block = os.read(fd, min(1048576, limite + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > limite:
                    raise ValueError("Corpo excede limite")
            after = os.fstat(fd)
            named = os.stat(p.name, dir_fd=directory, follow_symlinks=False)
            if _m6(before) != _m6(after) or _m6(named) != _m6(after):
                raise ValueError("Membro mudou durante recepção")
            return b"".join(chunks), _m6(after)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


class ReceptorArquivos:
    """Instância nominal criada pelo receptor de contexto, não por argumento MCP."""

    def __init__(self, raizes: dict[str, Path], membros: dict[str, tuple[str, str, str]]):
        self.raizes = dict(raizes)
        self.membros = dict(membros)
        self.por_path = {raizes[root] / rel: mid for mid, (root, rel, _) in membros.items()}
        if len(self.por_path) != len(membros):
            raise ValueError("Membro físico declarado em duplicidade")
        self.recebidos: dict[str, tuple[bytes, tuple, str]] = {}
        self.falha = None
        self.total = 0
        self.nomes = None

    def _recusar(self, codigo, mensagem, membros=()):
        from .workflow.leitura_contratos import FalhaLeitura, TentativaDeEfeitoLeitura

        self.falha = FalhaLeitura(codigo, mensagem, tuple(membros))
        raise TentativaDeEfeitoLeitura(mensagem)

    def ler(self, path: str | Path) -> bytes:
        self.conferir_recusa()
        try:
            p = _path_exato(path)
        except (ValueError, TypeError):
            self._recusar("SELETOR_INCOMPATIVEL", "Path fora da fronteira recebida")
        mid = self.por_path.get(p)
        if mid is None:
            self._recusar("ARQUIVO_AUSENTE", "Path consumido sem membro declarado")
        root, rel, expected = self.membros[mid]
        try:
            body, m6 = receber_fd(p)
        except FileNotFoundError:
            self._recusar("ARQUIVO_AUSENTE", "Membro declarado ausente", (mid,))
        except (OSError, ValueError):
            self._recusar("LEITURA_INSTAVEL", "Membro inseguro/instável na recepção", (mid,))
        sha = hashlib.sha256(body).hexdigest()
        if sha != expected:
            self._recusar("INTEGRIDADE_DA_FONTE", "SHA físico diverge do declarado", (mid,))
        previous = self.recebidos.get(mid)
        if previous is not None:
            if previous[:2] != (body, m6):
                self._recusar("LEITURA_INSTAVEL", "Membro mudou na mesma consulta", (mid,))
            return previous[0]
        if len(self.recebidos) >= MAX_MEMBROS or self.total + len(body) > MAX_BYTES:
            self._recusar("LIMITE_DE_LEITURA", "Readset excede limite fechado", (mid,))
        at = datetime.now(UTC).isoformat()
        self.recebidos[mid] = (body, m6, at)
        self.total += len(body)
        return body

    def conferir_recusa(self):
        if self.falha is not None:
            from .workflow.leitura_contratos import TentativaDeEfeitoLeitura

            raise TentativaDeEfeitoLeitura(self.falha.mensagem)

    def fechar(self):
        self.conferir_recusa()
        for mid in tuple(self.recebidos):
            root, rel, _ = self.membros[mid]
            self.ler(self.raizes[root] / rel)

    def referencias(self):
        from .workflow.leitura_contratos import ReferenciaFonte

        refs = []
        for mid, (_body, m6, at) in self.recebidos.items():
            root, rel, expected = self.membros[mid]
            dev, ino, size, mtime, ctime, mode, nlink = m6
            refs.append(
                ReferenciaFonte(
                    mid,
                    root,
                    rel,
                    expected,
                    size,
                    str(dev),
                    str(ino),
                    str(mtime),
                    str(ctime),
                    mode,
                    nlink,
                    at,
                )
            )
        return tuple(refs)


@contextmanager
def ativar_receptor(receptor: ReceptorArquivos):
    if type(receptor) is not ReceptorArquivos or _ATIVO.get() is not None:
        raise TypeError("Receptor nominal único obrigatório")
    token = _ATIVO.set(receptor)
    try:
        yield receptor
    finally:
        _ATIVO.reset(token)


def ler_bytes(path: str | Path) -> bytes:
    receiver = _ATIVO.get()
    return receiver.ler(path) if receiver is not None else Path(path).read_bytes()


def ler_texto_exclusivo(path: str | Path) -> str:
    """Texto NET recebido pelo mesmo FD, conservando a exigência nativa nlink=1."""
    receiver = _ATIVO.get()
    if receiver is None:
        raise RuntimeError("Custódia exclusiva exige receptor ativo")
    body = receiver.ler(path)
    mid = receiver.por_path[_path_exato(path)]
    if receiver.recebidos[mid][1][-1] != 1:
        receiver._recusar("INTEGRIDADE_DA_FONTE", "Prova NET sem custódia exclusiva", (mid,))
    return body.decode("utf-8")


def ler_texto(path: str | Path, encoding=None, errors=None) -> str:
    receiver = _ATIVO.get()
    if receiver is None:
        return Path(path).read_text(encoding=encoding, errors=errors)
    return receiver.ler(path).decode(encoding or "utf-8", errors or "strict")


def abrir_leitura(path: str | Path, mode="r", encoding=None, newline=None):
    receiver = _ATIVO.get()
    if receiver is None:
        return Path(path).open(mode, encoding=encoding, newline=newline)
    if mode not in ("r", "rb"):
        recusar_escrita()
    raw = receiver.ler(path)
    return (
        io.BytesIO(raw)
        if mode == "rb"
        else io.StringIO(raw.decode(encoding or "utf-8"), newline=newline)
    )


def ler_csv(path, *args, **kwargs):
    import pandas as pd

    receiver = _ATIVO.get()
    if receiver is not None and type(path) in (str, PosixPath):
        return pd.read_csv(io.BytesIO(receiver.ler(path)), *args, **kwargs)
    return pd.read_csv(path, *args, **kwargs)


def nomes_recebidos():
    receiver = _ATIVO.get()
    if receiver is None:
        return None
    if type(receiver.nomes) is not dict:
        receiver._recusar("PREPARADO_AUSENTE", "Nomes canônicos não recebidos")
    return receiver.nomes
