"""Busca lexical de passagens versionadas com orçamento explícito."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import dataclass

LINHAS_PASSAGEM = 14
BYTES_PASSAGEM = 1800
_PASSO = 4
_STOP = set(
    "a ao aos as com como da das de do dos e em essa esse esta isto mais na nas no nos "
    "o os ou para pela pelo por qual quais que se sem sobre tem um uma usa usar "
    "consigo posso pode devo existe onde alguem caso faria poderia".split()
)


def normalizar(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)
    )


def frequencias(s: str, *, paradas: set[str] = _STOP) -> Counter[str]:
    termos = (t for t in re.findall(r"[a-z0-9]{2,}", normalizar(s)) if t not in paradas)
    return Counter(
        t[:-3] + "ao" if len(t) > 4 and t.endswith("oes") else
        t[:-1] if len(t) > 4 and t[-2:] in ("as", "es", "is", "os", "us") else t
        for t in termos
    )


@dataclass(frozen=True)
class Local:
    caminho: str
    inicio: int
    fim: int
    sha256: str

    def json(self) -> dict:
        return {"caminho": self.caminho, "inicio": self.inicio, "fim": self.fim,
                "sha256": self.sha256}


def localizar(caminho: str, inicio: int, linhas: tuple[str, ...]) -> Local:
    trecho = "\n".join(linhas).encode()
    return Local(caminho, inicio, inicio + len(linhas) - 1, hashlib.sha256(trecho).hexdigest())


def ampliar(ancora: Local, linhas: tuple[str, ...]) -> Local:
    """Inclui o contexto adjacente que couber sem deslocar a âncora."""
    for margem in (3, 2, 1):
        inicio = max(1, ancora.inicio - margem)
        fim = min(len(linhas), ancora.fim + margem)
        trecho = linhas[inicio - 1:fim]
        if len(trecho) <= LINHAS_PASSAGEM and len("\n".join(trecho).encode()) <= BYTES_PASSAGEM:
            return localizar(ancora.caminho, inicio, trecho)
    return ancora


@dataclass(frozen=True)
class _Janela:
    caminho: str
    inicio: int
    linhas: tuple[str, ...]
    termos: Counter[str]
    tamanho: int


def _janelas(caminho: str, linhas: tuple[str, ...]) -> Iterable[_Janela]:
    for pos in range(0, len(linhas), _PASSO):
        janela = linhas[pos:pos + LINHAS_PASSAGEM]
        corpo = "\n".join(janela)
        if len(corpo.encode()) > BYTES_PASSAGEM:
            continue
        contagem = frequencias(corpo)
        if contagem:
            yield _Janela(caminho, pos + 1, janela, contagem, contagem.total())


def redundante(a: Local, b: Local) -> bool:
    if a.caminho != b.caminho:
        return False
    intersecao = min(a.fim, b.fim) - max(a.inicio, b.inicio) + 1
    menor = min(a.fim - a.inicio + 1, b.fim - b.inicio + 1)
    return intersecao > 0 and intersecao * 4 >= menor * 3


class IndicePassagens:
    """BM25 por escopo com vocabulário, frequências e desempate determinísticos."""

    def __init__(self, fontes: Iterable[tuple[str, tuple[str, ...]]]):
        self._janelas = [j for caminho, linhas in fontes for j in _janelas(caminho, linhas)]
        self._df: Counter[str] = Counter()
        for janela in self._janelas:
            self._df.update(janela.termos.keys())
        self._media = sum(j.tamanho for j in self._janelas) / max(1, len(self._janelas))

    def buscar(self, consulta: str, limite: int) -> list[Local]:
        q = frequencias(consulta).keys()
        n = len(self._janelas)
        idf = {t: math.log1p((n - self._df[t] + 0.5) / (self._df[t] + 0.5))
               for t in sorted(q) if self._df[t]}
        ranqueadas = []
        for janela in self._janelas:
            comuns = [t for t in idf if t in janela.termos]
            if len(comuns) < min(2, len(q)) or len(comuns) * 4 < len(q) or not comuns:
                continue
            # Robertson e Zaragoza, k1=1,2 e b=0,75.
            normalizacao = 1.2 * (0.25 + 0.75 * janela.tamanho / self._media)
            pontos = sum(idf[t] * 2.2 * janela.termos[t] / (janela.termos[t] + normalizacao)
                         for t in comuns)
            ranqueadas.append((-pontos, -len(comuns), janela.caminho, janela.inicio, janela))
        selecionadas: list[Local] = []
        for *_, j in sorted(ranqueadas, key=lambda linha: linha[:4]):
            local = localizar(j.caminho, j.inicio, j.linhas)
            if not any(redundante(local, anterior) for anterior in selecionadas):
                selecionadas.append(local)
                if len(selecionadas) == limite:
                    break
        return selecionadas


def intercalar(diretas: list[Local], ancoras: list[list[Local]], limite: int) -> list[Local]:
    """Preserva a primeira fonte direta e intercala âncoras de notas distintas."""
    selecionadas: list[Local] = []
    fontes = deque(diretas)
    rodizio = deque(deque(grupo) for grupo in ancoras if grupo)

    def inserir(candidatas: deque[Local]) -> bool:
        while candidatas:
            local = candidatas.popleft()
            if not any(redundante(local, anterior) for anterior in selecionadas):
                selecionadas.append(local)
                return True
        return False

    while len(selecionadas) < limite:
        inseriu_direta = inserir(fontes)
        if len(selecionadas) == limite:
            break
        inseriu_ancora = False
        while rodizio:
            grupo = rodizio.popleft()
            if inserir(grupo):
                inseriu_ancora = True
                if grupo:
                    rodizio.append(grupo)
                break
        if not inseriu_direta and not inseriu_ancora:
            break
    return selecionadas
