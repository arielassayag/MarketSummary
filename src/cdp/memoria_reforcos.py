"""Completa unidades estruturais canônicas cortadas pelo índice por janelas."""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from io import StringIO
from itertools import chain, pairwise
from tokenize import COMMENT, generate_tokens

from .memoria_busca import (
    BYTES_PASSAGEM,
    LINHAS_PASSAGEM,
    Local,
    localizar,
    normalizar,
    termos_contextuais,
)
from .memoria_secoes import _pesos, _relevancia

_FUNCOES = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPOSTOS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
_LIMITE_MARGENS = 8
_LIMITE_ETAPAS = 4
_LIMITE_CONDICOES = 8
LIMITE_REFORCOS = _LIMITE_MARGENS + _LIMITE_ETAPAS + _LIMITE_CONDICOES
_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s")
_CERCA = ("```", "~~~")
_TEMAS_CODIGO = {
    "tempo-tardio": re.compile(r"\b(?:tarde|tardi[oa]s?|atras\w*|toleranc\w*|demor\w*)\b"),
    "rotina-agendada": re.compile(r"\b(?:agend\w*|dispar\w*|rotina\w*|cron)\b"),
    "gate": re.compile(r"\b(?:gate|guarda|admissao|verific\w*)\b"),
}


@dataclass(frozen=True)
class _Bloco:
    local: Local
    tamanho: int
    termos: Counter[str]
    titulo: Counter[str]


def _termos_codigo(texto: str) -> Counter[str]:
    termos = termos_contextuais(texto)
    separada = normalizar(texto).replace("_", " ")
    termos.update("@" + k for k, p in _TEMAS_CODIGO.items() if p.search(separada))
    return termos


def _listas(linhas: tuple[str, ...]) -> Iterable[tuple[int, int, str]]:
    itens: list[tuple[int, int]] = []
    titulo, em_codigo = "", False
    for i, linha in enumerate((*linhas, ""), 1):
        if linha.lstrip().startswith(_CERCA):
            em_codigo = not em_codigo
        if em_codigo:
            continue
        if _ITEM.match(linha):
            itens.append((i, i))
        elif itens and linha.startswith(" ") and linha.strip():
            itens[-1] = itens[-1][0], i
        else:
            for j, (a, _) in enumerate(itens):
                yield from ((a, b, titulo) for _, b in itens[j:j + 4])
            itens.clear()
            if linha.startswith("#"):
                titulo = linha


def _irmas(funcao: ast.AST, linhas: tuple[str, ...]) -> Iterable[tuple[int, int]]:
    for no in ast.walk(funcao):
        for _, corpo in ast.iter_fields(no):
            if not isinstance(corpo, list) or not corpo or not all(isinstance(n, ast.stmt) for n in corpo):
                continue
            for i, irma in enumerate(corpo):
                inicio = irma.lineno
                antes = inicio
                while (antes > 1 and inicio - antes < 2
                       and linhas[antes - 2].lstrip().startswith("#")):
                    antes -= 1
                for j in range(i, len(corpo)):
                    fim = corpo[j].end_lineno
                    if fim - inicio >= LINHAS_PASSAGEM:
                        break
                    if antes != inicio:
                        yield antes, fim
                    yield inicio, fim


def _comentadas(funcao: ast.FunctionDef | ast.AsyncFunctionDef,
                linhas: tuple[str, ...], comentarios: dict[int, list[int]]) -> Iterable[tuple[int, int]]:
    marcas = [i for i in comentarios.get(funcao.body[0].col_offset, ())
              if funcao.lineno <= i < funcao.end_lineno]
    for a, b in pairwise([*marcas, funcao.end_lineno]):
        while b > a and not linhas[b - 1].strip():
            b -= 1
        yield a + 1, b


def _bloco(caminho: str, linhas: tuple[str, ...], a: int, b: int, titulo: Counter[str],
           tokenizar: Callable[[str], Counter[str]]) -> _Bloco | None:
    if not 1 <= a <= b <= len(linhas) or b - a >= LINHAS_PASSAGEM:
        return None
    recorte = linhas[a - 1:b]
    texto = "\n".join(recorte)
    tamanho = len(texto.encode())
    if not texto.strip() or tamanho > BYTES_PASSAGEM:
        return None
    return _Bloco(localizar(caminho, a, recorte), tamanho, tokenizar(texto), titulo)


_Vias = tuple[tuple[_Bloco, ...], tuple[_Bloco, ...], tuple[_Bloco, ...]]


def _indexar(caminho: str, linhas: tuple[str, ...]) -> _Vias:
    if caminho.endswith(".md"):
        margens = tuple(
            b for a, z, titulo in _listas(linhas)
            if (b := _bloco(caminho, linhas, a, z, termos_contextuais(titulo),
                            termos_contextuais)) is not None
        )
        return margens, (), ()
    if not caminho.endswith(".py"):
        return (), (), ()
    fonte = "\n".join(linhas)
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        return (), (), ()
    marcas: dict[int, list[int]] = defaultdict(list)
    for token in generate_tokens(StringIO(fonte).readline):
        linha, coluna = token.start
        if (token.type == COMMENT and not linhas[linha - 1][:coluna].strip()
                and re.match(r"#+\s+\w", token.string)):
            marcas[coluna].append(linha - 1)
    irmas: dict[tuple[int, int], _Bloco] = {}
    comentarios = []
    for no in ast.walk(arvore):
        if not isinstance(no, _FUNCOES):
            continue
        titulo = no.name + " " + (ast.get_docstring(no) or "")
        comum, codigo = termos_contextuais(titulo), _termos_codigo(titulo)
        for a, z in _irmas(no, linhas):
            if (a, z) not in irmas:
                if b := _bloco(caminho, linhas, a, z, comum, termos_contextuais):
                    irmas[a, z] = b
        comentarios.extend(
            b for a, z in _comentadas(no, linhas, marcas)
            if a < z and (b := _bloco(caminho, linhas, a, z, codigo, _termos_codigo))
        )
    condicoes = tuple(
        b for no in ast.walk(arvore) if isinstance(no, _COMPOSTOS)
        if no.lineno < no.end_lineno and (
            b := _bloco(caminho, linhas, no.lineno, no.end_lineno, Counter(), _termos_codigo)
        )
    )
    return tuple(irmas.values()), tuple(comentarios), condicoes


class IndiceReforcos:
    """Recupera blocos completos nas fontes autorizadas já tocadas pela busca."""

    def __init__(self, ler: Callable[[str], tuple[str, ...]], fontes_permitidas: Iterable[str]):
        self._ler = ler
        self._permitidas = frozenset(fontes_permitidas)
        self._vias: dict[str, _Vias] = {}

    def _por_fonte(self, caminho: str) -> _Vias:
        if caminho not in self._vias:
            self._vias[caminho] = _indexar(caminho, self._ler(caminho))
        return self._vias[caminho]

    def buscar(self, consulta: str, candidatas: Iterable[Local]) -> list[Local]:
        por_fonte: dict[str, list[tuple[int, Local]]] = defaultdict(list)
        for pos, local in enumerate(candidatas, 1):
            if local.caminho in self._permitidas:
                por_fonte[local.caminho].append((pos, local))
        if not por_fonte:
            return []
        vistos = {p for ps in por_fonte.values() for _, p in ps}
        margens, comentarios, condicoes = zip(
            *(self._por_fonte(caminho) for caminho in por_fonte), strict=True
        )
        codigo = _termos_codigo(consulta)
        listas_completas = _ordenar(
            [b for b in chain.from_iterable(margens) if b.local not in vistos],
            termos_contextuais(consulta), por_fonte, _nota_margem, _LIMITE_MARGENS, referencia=35,
            diversificar=True,
        )
        etapas_comentadas = _ordenar(
            list(chain.from_iterable(comentarios)), codigo, por_fonte, _nota_comentario, _LIMITE_ETAPAS,
            referencia=40,
        )
        condicionais = _ordenar(
            list(chain.from_iterable(condicoes)), codigo, por_fonte, _nota_condicao, _LIMITE_CONDICOES,
            referencia=32,
        )
        return list(dict.fromkeys(
            p for p in chain(listas_completas, etapas_comentadas, condicionais) if p not in vistos
        ))


def _ordenar(blocos: list[_Bloco], consulta: Counter[str], por_fonte: dict[str, list[tuple[int, Local]]],
             nota: Callable[[Local, list[tuple[int, Local]], float], float], limite: int, *,
             referencia: int, diversificar: bool = False) -> list[Local]:
    df: Counter[str] = Counter()
    for b in blocos:
        df.update(b.termos.keys() | b.titulo.keys())
    pesos = _pesos(consulta, df, len(blocos))
    ranking = []
    for b in blocos:
        rel = _relevancia(b.termos, pesos, referencia)
        ponto = nota(b.local, por_fonte[b.local.caminho], rel)
        if ponto > 0:
            ranking.append((-ponto, b.tamanho if diversificar else 0, b.local))
    saida: list[Local] = []
    for _, _, p in sorted(ranking, key=lambda x: (x[0], x[1], x[2].caminho, x[2].inicio, x[2].fim)):
        if diversificar and any(_sobreposicao(p, q) for q in saida):
            continue
        saida.append(p)
        if len(saida) == limite:
            break
    return saida


def _sobreposicao(p: Local, q: Local) -> bool:
    inter = min(p.fim, q.fim) - max(p.inicio, q.inicio) + 1
    menor = min(p.fim - p.inicio + 1, q.fim - q.inicio + 1)
    return p.caminho == q.caminho and 5 * inter >= 3 * menor


def _nota_margem(p: Local, candidatas: list[tuple[int, Local]], relevancia: float) -> float:
    esquerda = direita = 0.0
    tamanho = p.fim - p.inicio + 1
    for pos, q in candidatas:
        inter = min(q.fim, p.fim) - max(q.inicio, p.inicio) + 1
        if inter < 2:
            continue
        peso = (inter / tamanho) ** .7 / (1 + pos / 10) ** .7
        ini, fim = q.inicio - p.inicio, p.fim - q.fim
        if 0 < ini <= 6:
            esquerda = max(esquerda, peso / (1 + max(0, ini - 2) * .12))
        if 0 < fim <= 6:
            direita = max(direita, peso / (1 + max(0, fim - 2) * .12))
    contato = max(esquerda, direita) + .35 * min(esquerda, direita)
    return contato * (1 + relevancia / 8)


def _nota_comentario(_p: Local, _candidatas: list[tuple[int, Local]], relevancia: float) -> float:
    return relevancia


def _nota_condicao(p: Local, candidatas: list[tuple[int, Local]], relevancia: float) -> float:
    corte = max((1 / (1 + pos / 16) for pos, q in candidatas
                 if p.inicio < q.inicio < p.fim <= q.fim and q.inicio - p.inicio <= 8),
                default=0.)
    return relevancia + 6 * corte if corte and relevancia else 0.
