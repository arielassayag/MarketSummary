"""Busca lexical de passagens versionadas com orçamento explícito."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
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
_STOP_CONSULTA = _STOP | set(
    "assim algo ainda apenas certo certa consigo fica ficou ficam fazer feito precisa "
    "qualquer quando saber usar onde quais quem vai vou tenho pode poderia caso dizer "
    "dizer aconteceu acontece tem faz mesmo mesma outras outro voce eu quero gostaria "
    "vale devem devo posso podem isso esse neste tambem alguma algum".split()
)
_TITULO = re.compile(r"^(#{1,6})\s+(.+)")


def termos_contextuais(s: str) -> Counter[str]:
    """Normaliza flexões produtivas usadas nas consultas e nos procedimentos."""
    palavras = frequencias(s, paradas=_STOP_CONSULTA)
    termos = Counter()
    for palavra, peso in palavras.items():
        for sufixo in ("amento", "imento", "acao", "icao", "idade", "ando", "endo", "indo",
                       "ado", "ada", "ido", "ida", "ador", "ar", "er", "ir"):
            if palavra.endswith(sufixo) and len(palavra) - len(sufixo) >= 4:
                palavra = palavra[:-len(sufixo)]
                break
        termos[palavra] += peso
    return termos


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


def reunir_ancoras(locais: list[Local], linhas: tuple[str, ...]) -> list[Local]:
    """Reúne referências próximas da mesma nota sem exceder o tamanho de uma passagem."""
    reunidas: list[Local] = []
    for local in sorted(locais, key=lambda p: p.inicio):
        if reunidas:
            anterior = reunidas[-1]
            fim = max(local.fim, anterior.fim)
            trecho = linhas[anterior.inicio - 1:fim]
            if len(trecho) <= LINHAS_PASSAGEM and len("\n".join(trecho).encode()) <= BYTES_PASSAGEM:
                reunidas[-1] = localizar(anterior.caminho, anterior.inicio, trecho)
                continue
        reunidas.append(local)
    return [ampliar(local, linhas) for local in reunidas]


@dataclass(frozen=True)
class _Janela:
    caminho: str
    inicio: int
    linhas: tuple[str, ...]
    termos: Counter[str]
    tamanho: int
    contexto: Counter[str]
    bloco_inteiro: bool


def _blocos_markdown(linhas: tuple[str, ...]) -> Iterable[tuple[int, int]]:
    """Localiza parágrafos, tabelas e listas contíguas sem cortar suas linhas."""
    inicio = 0
    em_codigo = False
    for pos, linha in enumerate((*linhas, "")):
        if linha.lstrip().startswith(("```", "~~~")):
            em_codigo = not em_codigo
        if em_codigo or (linha.strip() and not _TITULO.match(linha)):
            continue
        if 2 <= pos - inicio <= LINHAS_PASSAGEM:
            yield inicio, pos
        inicio = pos + 1


def _janelas(caminho: str, linhas: tuple[str, ...], *, contextual: bool = False) -> Iterable[_Janela]:
    titulos_por_linha: list[str] = []
    if contextual:
        titulos: dict[int, str] = {}
        for linha in linhas:
            if caminho.endswith(".md") and (titulo := _TITULO.match(linha)):
                nivel = len(titulo[1])
                titulos = {n: t for n, t in titulos.items() if n < nivel}
                titulos[nivel] = titulo[2]
            titulos_por_linha.append(" ".join(titulos.values()))
    limites = {(pos, min(pos + LINHAS_PASSAGEM, len(linhas))): False
               for pos in range(0, len(linhas), _PASSO)}
    if contextual and caminho.endswith(".md"):
        limites.update(dict.fromkeys(_blocos_markdown(linhas), True))
    for (pos, fim), bloco_inteiro in sorted(limites.items()):
        janela = linhas[pos:fim]
        corpo = "\n".join(janela)
        if len(corpo.encode()) > BYTES_PASSAGEM:
            continue
        contagem = termos_contextuais(corpo) if contextual else frequencias(corpo)
        if contagem:
            cabecalho = termos_contextuais(titulos_por_linha[pos]) if contextual else Counter()
            yield _Janela(caminho, pos + 1, janela, contagem, contagem.total(), cabecalho,
                          bloco_inteiro)


def redundante(a: Local, b: Local, *, diverso: bool = False) -> bool:
    if a.caminho != b.caminho:
        return False
    intersecao = min(a.fim, b.fim) - max(a.inicio, b.inicio) + 1
    menor = min(a.fim - a.inicio + 1, b.fim - b.inicio + 1)
    return intersecao > 0 and (intersecao * 2 >= menor if diverso else intersecao * 4 >= menor * 3)


class IndicePassagens:
    """BM25 por escopo com vocabulário, frequências e desempate determinísticos."""

    def __init__(self, fontes: Iterable[tuple[str, tuple[str, ...]]], *, contextual: bool = False):
        self.contextual = contextual
        self._janelas = [j for caminho, linhas in fontes
                         for j in _janelas(caminho, linhas, contextual=contextual)]
        self._df: Counter[str] = Counter()
        for janela in self._janelas:
            self._df.update(janela.termos.keys() | janela.contexto.keys())
        self._media = sum(j.tamanho for j in self._janelas) / max(1, len(self._janelas))

    def buscar(self, consulta: str, limite: int) -> list[Local]:
        q = (termos_contextuais(consulta) if self.contextual else frequencias(consulta)).keys()
        n = len(self._janelas)
        idf = {t: math.log1p((n - self._df[t] + 0.5) / (self._df[t] + 0.5))
               for t in sorted(q) if self._df[t]}
        ranqueadas = []
        for janela in self._janelas:
            comuns = [t for t in idf if t in janela.termos]
            minimo = 6 if self.contextual else 4
            if len(comuns) < min(2, len(q)) or len(comuns) * minimo < len(q) or not comuns:
                continue
            # Robertson e Zaragoza, k1=1,2 e b=0,75.
            normalizacao = 1.2 * (0.25 + 0.75 * janela.tamanho / self._media)
            pontos = sum(idf[t] * 2.2 * janela.termos[t] / (janela.termos[t] + normalizacao)
                         for t in comuns)
            if self.contextual:
                pontos += 0.65 * sum(idf[t] for t in idf if t in janela.contexto)
                if janela.bloco_inteiro:
                    pontos *= 1.12
            ranqueadas.append((-pontos, -len(comuns), janela.caminho, janela.inicio, janela))
        selecionadas: list[Local] = []
        for *_, j in sorted(ranqueadas, key=lambda linha: linha[:4]):
            local = localizar(j.caminho, j.inicio, j.linhas)
            if not any(redundante(local, anterior, diverso=self.contextual)
                       for anterior in selecionadas):
                selecionadas.append(local)
                if len(selecionadas) == limite:
                    break
        return selecionadas


def combinar_evidencias(diretas: list[Local], contextuais: list[Local],
                        ancoras: list[list[Local]], limite: int, *,
                        priorizar_nota: bool = True) -> list[Local]:
    """Combina a melhor janela direta, as âncoras de uma lição e passagens diversas."""
    selecao: list[Local] = []
    sobrepostas: list[Local] = []
    primaria = ancoras[0] if ancoras else []
    lexicais = (contextuais[:1], diretas[:1]) if contextuais and diretas and redundante(
        contextuais[0], diretas[0], diverso=True
    ) else (diretas[:1], contextuais[:1])
    if priorizar_nota:
        primeiras = (primaria[:1], lexicais[0], primaria[1:2], lexicais[1])
    else:
        primeiras = (*lexicais, primaria[:1], diretas[1:2], primaria[1:2])
    ordem = (*primeiras, diretas[1:2], contextuais[1:3],
             *(grupo[:1] for grupo in ancoras[1:]), diretas[2:], contextuais[3:], primaria[2:],
             *(grupo[1:] for grupo in ancoras[1:]))
    for grupo in ordem:
        for local in grupo:
            if any(redundante(local, anterior, diverso=True) for anterior in selecao):
                sobrepostas.append(local)
                continue
            selecao.append(local)
            if len(selecao) == limite:
                return selecao
    for local in sobrepostas:
        if not any(redundante(local, anterior) for anterior in selecao):
            selecao.append(local)
            if len(selecao) == limite:
                break
    return selecao
