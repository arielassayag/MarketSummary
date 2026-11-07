"""Gera candidatas canônicas a partir da estrutura dos documentos do CDP."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise, zip_longest
from math import log1p
from pathlib import PurePosixPath

from .memoria_busca import (
    _TITULO,
    BYTES_PASSAGEM,
    LINHAS_PASSAGEM,
    Local,
    localizar,
    redundante,
    termos_contextuais,
)

_MAX_DOCUMENTOS = 6
_MAX_SECOES = 9
_POR_SECAO = 4
_LINHAS_SECAO_CODIGO = 64
_CERCAS = ("```", "~~~")


@dataclass(frozen=True)
class _Secao:
    inicio: int
    fim: int
    corpo: Counter[str]
    titulo: Counter[str]
    contexto: Counter[str]
    paragrafos: tuple[tuple[int, int, Counter[str]], ...]


def _paragrafos(linhas: tuple[str, ...], inicio: int, fim: int) -> Iterable[tuple[int, int]]:
    """Mantém tabelas, listas e blocos cercados juntos, inclusive quando são longos."""
    comeco = inicio
    em_codigo = False
    for i in range(inicio, fim):
        linha = linhas[i]
        if linha.lstrip().startswith(_CERCAS):
            em_codigo = not em_codigo
        if not em_codigo and not linha.strip():
            if i > comeco:
                yield comeco, i
            comeco = i + 1
    if fim > comeco:
        yield comeco, fim


def _secoes(caminho: str, linhas: tuple[str, ...], nome: str) -> Iterable[_Secao]:
    marcadores: list[tuple[int, tuple[str, ...]]] = []
    if caminho.endswith(".md"):
        niveis: dict[int, str] = {}
        em_codigo = False
        for i, linha in enumerate(linhas):
            if linha.lstrip().startswith(_CERCAS):
                em_codigo = not em_codigo
            if not em_codigo and (titulo := _TITULO.match(linha)):
                nivel = len(titulo[1])
                niveis = {n: texto for n, texto in niveis.items() if n < nivel}
                niveis[nivel] = titulo[2]
                marcadores.append((i, tuple(niveis.values())))
        if not marcadores or marcadores[0][0]:
            marcadores.insert(0, (0, (nome,)))
    else:
        marcadores = [(i, (nome,)) for i in range(0, len(linhas), _LINHAS_SECAO_CODIGO)]
    for (inicio, titulos), (fim, _) in pairwise([*marcadores, (len(linhas), ())]):
        if inicio == fim:
            continue
        paragrafos = tuple((a, b, termos_contextuais("\n".join(linhas[a:b])))
                           for a, b in _paragrafos(linhas, inicio, fim))
        yield _Secao(inicio, fim, termos_contextuais("\n".join(linhas[inicio:fim])),
                     termos_contextuais(titulos[-1]),
                     termos_contextuais(" / ".join((nome, *titulos))), paragrafos)


def _pesos(consulta: Counter[str], frequencias: Counter[str], total: int) -> dict[str, float]:
    return {termo: log1p((total - frequencias[termo] + .5) / (frequencias[termo] + .5))
            for termo in sorted(consulta) if frequencias[termo]}


def _cobertura(termos: Counter[str], pesos: dict[str, float]) -> float:
    return sum(pesos[t] for t in sorted(termos.keys() & pesos.keys()))


def _relevancia(termos: Counter[str], pesos: dict[str, float], referencia: int) -> float:
    comuns = termos.keys() & pesos.keys()
    if not comuns:
        return 0.
    normalizacao = 1.2 * (.25 + .75 * termos.total() / referencia)
    return sum(pesos[t] * 2.2 * termos[t] / (termos[t] + normalizacao)
               for t in sorted(comuns))


def _intervalos(inicio: int, fim: int) -> set[tuple[int, int]]:
    """Oferece o parágrafo e margens contíguas dos dois lados da âncora."""
    candidatos = {(inicio, fim), (inicio - 2, fim + 2), (inicio - 4, fim + 4),
                  (fim - LINHAS_PASSAGEM, fim), (inicio, inicio + LINHAS_PASSAGEM)}
    candidatos.update((i, i + LINHAS_PASSAGEM) for i in range(inicio - 6, fim, 3))
    if fim - inicio > LINHAS_PASSAGEM:
        candidatos.update((i, min(fim, i + LINHAS_PASSAGEM)) for i in range(inicio, fim, 4))
    return candidatos


class IndiceSecoes:
    """Índice em memória de um escopo, com as mesmas fontes da busca canônica."""

    def __init__(self, fontes: Iterable[tuple[str, tuple[str, ...]]]):
        self._fontes = dict(fontes)
        self._documentos: dict[str, tuple[_Secao, ...]] = {}
        self._nomes: dict[str, Counter[str]] = {}
        self._df_secoes: Counter[str] = Counter()
        self._df_paragrafos: Counter[str] = Counter()
        self._n_secoes = self._n_paragrafos = 0
        for caminho, linhas in self._fontes.items():
            nome = PurePosixPath(caminho).stem
            self._nomes[caminho] = termos_contextuais(nome)
            secoes = tuple(_secoes(caminho, linhas, nome.replace("_", " ").replace("-", " ")))
            self._documentos[caminho] = secoes
            self._n_secoes += len(secoes)
            for secao in secoes:
                self._df_secoes.update(secao.corpo.keys() | secao.contexto.keys())
                self._n_paragrafos += len(secao.paragrafos)
                for _, _, termos in secao.paragrafos:
                    self._df_paragrafos.update(termos.keys())
        self._janela = lru_cache(maxsize=2048)(self._ler_janela)

    def _ler_janela(self, caminho: str, inicio: int,
                    fim: int) -> tuple[Local, Counter[str]] | None:
        if not 0 < fim - inicio <= LINHAS_PASSAGEM:
            return None
        linhas = self._fontes[caminho][inicio:fim]
        corpo = "\n".join(linhas)
        if len(corpo.encode()) > BYTES_PASSAGEM or not corpo.strip():
            return None
        return localizar(caminho, inicio + 1, linhas), termos_contextuais(corpo)

    def _escolher_secoes(self, pesos: dict[str, float]) -> list[tuple[str, _Secao]]:
        documentos: list[tuple[float, str, int, bool]] = []
        for caminho, secoes in self._documentos.items():
            melhor_secao = 0
            melhor_nota = 0.
            melhor_titulo = 0.
            nota_documento = 0.
            nome = _cobertura(self._nomes[caminho], pesos)
            for i, secao in enumerate(secoes):
                titulo = _cobertura(secao.titulo, pesos)
                melhor_paragrafo = max((_relevancia(t, pesos, 30) for _, _, t in secao.paragrafos),
                                       default=0.)
                nota = (.62 * melhor_paragrafo + .20 * _relevancia(secao.corpo, pesos, 120)
                        + .18 * _cobertura(secao.corpo, pesos) + .30 * titulo)
                if nota > melhor_nota:
                    melhor_secao, melhor_nota, melhor_titulo = i, nota, titulo
                nota_documento = max(nota_documento, nota + .70 * titulo + .55 * nome)
            if melhor_nota > 0:
                documentos.append((-nota_documento, caminho, melhor_secao, bool(nome or melhor_titulo)))

        escolhas = []
        for _, caminho, posicao, incluir_vizinhas in sorted(documentos)[:_MAX_DOCUMENTOS]:
            secoes = self._documentos[caminho]
            escolhas.append((caminho, secoes[posicao]))
            if incluir_vizinhas and len(escolhas) < _MAX_SECOES:
                escolhas.extend((caminho, secoes[i])
                                for i in (posicao - 1, posicao + 1) if 0 <= i < len(secoes))
        return escolhas[:_MAX_SECOES]

    def _candidatas(self, caminho: str, secao: _Secao, pesos: dict[str, float]) -> list[Local]:
        paragrafos = sorted(
            ((-_relevancia(t, pesos, 30), a, b) for a, b, t in secao.paragrafos),
        )
        notas: dict[Local, float] = {}
        for nota, inicio, fim in paragrafos[:6]:
            if nota >= 0:
                break
            for a, b in sorted(_intervalos(inicio, fim)):
                janela = self._janela(caminho, max(secao.inicio, a), min(secao.fim, b))
                if janela is None:
                    continue
                local, termos = janela
                pontos = (_relevancia(termos, pesos, 36) - .28 * nota
                          + .10 * _cobertura(termos, pesos) + .08 * (a == inicio and b == fim))
                notas[local] = max(pontos, notas.get(local, 0.))
        if (janela := self._janela(caminho, secao.inicio, secao.fim)) is not None:
            local, termos = janela
            notas[local] = max(1.16 * _relevancia(termos, pesos, 36), notas.get(local, 0.))
        escolhidas: list[Local] = []
        for local in sorted(notas, key=lambda p: (-notas[p], p.inicio, p.fim)):
            if not any(redundante(local, p) for p in escolhidas):
                escolhidas.append(local)
            if len(escolhidas) == _POR_SECAO:
                break
        return escolhidas

    def buscar(self, consulta: str, limite: int = _MAX_SECOES * _POR_SECAO) -> list[Local]:
        """Intercala as janelas válidas das melhores seções de fontes distintas."""
        termos = termos_contextuais(consulta)
        pesos_secoes = _pesos(termos, self._df_secoes, self._n_secoes)
        if limite <= 0 or not pesos_secoes:
            return []
        pesos_paragrafos = _pesos(termos, self._df_paragrafos, self._n_paragrafos)
        listas = [self._candidatas(caminho, secao, pesos_paragrafos)
                  for caminho, secao in self._escolher_secoes(pesos_secoes)]
        ordem = dict.fromkeys(local for fila in zip_longest(*listas)
                              for local in fila if local is not None)
        return list(ordem)[:limite]
