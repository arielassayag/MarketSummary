"""Busca lexical de passagens versionadas com orçamento explícito."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

LINHAS_PASSAGEM = 14
BYTES_PASSAGEM = 1800
_BYTES_AMPLIACAO = 4500
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
# Equivalências usadas no vocabulário dos roteiros. Os conceitos são sinais de busca e
# não entram no texto da passagem nem determinam o procedimento a executar.
_CONCEITOS = {
    "agendador": r"agendador(?:es)?|cron|launchd|tarefas? agendadas?|disparos? automaticos?",
    "aluguel": r"alugue(?:l|is)|emprestimo de acoes|taxa de aluguel|disponibilidade de short",
    "arquivo-orfa": r"orfa(?:o|os|s)?|sem par|artefato isolado|evento isolado|arquivo avulso",
    "autoria": r"autoria|autor(?:es)?|autor[ai]s?|quem (?:redigiu|escreveu|produziu)|mind",
    "congelamento": r"congelad[oa]s?|congelamento|freeze|posicao mantida|linha detida sem",
    "cotacao": r"cotac(?:ao|oes)|preco(?:s)? de (?:mercado|fechamento)|barra (?:diaria|provisoria)",
    "defasagem": r"defasad[oa]s?|defasagem|desatualizad[oa]s?|atrasad[oa]s?|retrato antigo",
    "desfecho": r"desfechos?|outcomes?|resultado observado|realizacao da previsao",
    "divulgacao": r"divulgac(?:ao|oes)|data (?:de|da) publicacao|release(?:s)?|data de publicacao",
    "efetivacao": r"efetivac(?:ao|oes)|efetiv(?:ar|ad[oa]s?)|fills?|preenchimento(?:s)? de ordem",
    "errata": r"erratas?|retificac(?:ao|oes)|correc(?:ao|oes) editoria(?:l|is)",
    "espelho-privado": r"espelho privado|artifact(?:s)? do claude|painel privado",
    "fato": r"factbook|fatos? citave(?:l|is)|placeholder(?:s)? de fato|referencia de fato",
    "fuso": r"utc|fusos?(?: horarios?)?|horario de brasilia|virada d[eo] dia|dia seguinte",
    "impressao-digital": r"hash(?:es)?|sha[- ]?256|checksum(?:s)?|digest(?:s)?|impressao digital",
    "incerteza": r"incert[oa]s?|incertezas?|conviccao ordinal|linguagem ordinal|confianca qualitativa",
    "integridade": r"integridade|cdp verify|trilha encadeada|cadeia de auditoria",
    "janela": r"prazo efetivo|janela operacional|limite de horario|corte da decisao|tempo restante",
    "kill-switch": r"kill[- ]switch|bloqueio de risco|bloqueio de risco novo|ligar o bloqueio",
    "nota": r"nota de (?:pesquisa|emissor|cobertura)|analise de emissor|nota pos[- ]resultado",
    "noticia": r"noticias?|materias?|manchetes?|texto jornalistico|conteudo externo",
    "operador": r"operador(?:es)?|sess(?:ao|oes) interativas?|sess(?:ao|oes) manua(?:l|is)",
    "ordens": r"ordens?|acoes[- ]alvo|quantidade (?:de acoes|planejada)|roteamento da linha",
    "painel-local": r"painel local|dashboard local|espelho local|painel interno",
    "parametro": r"parametros?|premissas?|ajustes recomendados|hipoteses? de modelo",
    "pendencia": r"pendencias?|pendentes?|faltantes?|na fila|sem registro",
    "posicao-vendida": r"shorts?|posic(?:ao|oes) vendid[ao]s?|ponta vendida|venda a descoberto",
    "portal-publico": r"portal(?:is)?|github pages|publicado no ar|pagina publica",
    "procedencia": r"procedencia|proveniencia|origem comprovada|tra(?:iler|ilers)|fonte original",
    "proposta": r"propostas?|carteira sugerida|previa(?:s)? de decisao|proposta aprovada",
    "replay": r"replays?|reexecuc(?:ao|oes)|reproduzir uma montagem|ensaio retrospectivo",
    "retrato": r"retratos?|snapshots?|base do modelo|modelos atualizados",
    "relatorio-arquivado": r"relatorios? (?:antigos?|arquivad[oa]s?|historicos?)|dados/relatorios|texto integral",
    "rotina": r"rotinas?|tarefas? recorrentes?|agendamentos?|disparos?",
    "saida-automatica": r"texto automatico|nota automatica|autoria.{0,6}codigo|fallback editorial",
    "sincronizacao": r"sincroniz\w*|reconcili\w*|atualizar (?:o clone|do remoto)",
    "trava": r"travas?|bloqueio de escrita|escritor exclusivo|lock",
    "validacao": r"validadores?|validac(?:ao|oes)|valida(?:r|do|da)|texto invalid[oa]|reprovad[oa]",
}
_ALIASES = tuple(("@" + id_, re.compile(rf"\b(?:{alternativas})\b"))
                 for id_, alternativas in _CONCEITOS.items())


def termos_contextuais(s: str) -> Counter[str]:
    """Normaliza flexões produtivas usadas nas consultas e nos procedimentos."""
    texto = normalizar(s)
    palavras = _frequencias_normalizadas(texto, _STOP_CONSULTA)
    termos = Counter()
    for palavra, peso in palavras.items():
        for sufixo in ("amento", "imento", "acao", "icao", "idade", "ando", "endo", "indo",
                       "ado", "ada", "ido", "ida", "ador", "ar", "er", "ir"):
            if palavra.endswith(sufixo) and len(palavra) - len(sufixo) >= 4:
                palavra = palavra[:-len(sufixo)]
                break
        termos[palavra] += peso
    termos.update(id_ for id_, alias in _ALIASES if alias.search(texto))
    return termos


def normalizar(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)
    )


def frequencias(s: str, *, paradas: set[str] = _STOP) -> Counter[str]:
    return _frequencias_normalizadas(normalizar(s), paradas)


def _frequencias_normalizadas(texto: str, paradas: set[str]) -> Counter[str]:
    termos = (t for t in re.findall(r"[a-z0-9]{2,}", texto) if t not in paradas)
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


def completar_bloco(local: Local, linhas: tuple[str, ...]) -> Local:
    """Completa um bloco Markdown cortado, preservando integralmente a seleção."""
    if not local.caminho.endswith(".md") or local.fim - local.inicio + 1 >= LINHAS_PASSAGEM:
        return local
    inicio, fim = local.inicio, local.fim
    for primeiro, ultimo in _blocos_markdown(linhas):
        if primeiro >= local.fim:
            break
        if ultimo < local.inicio:
            continue
        a, b = min(inicio, primeiro + 1), max(fim, ultimo)
        trecho = linhas[a - 1:b]
        if len(trecho) <= LINHAS_PASSAGEM and len("\n".join(trecho).encode()) <= BYTES_PASSAGEM:
            inicio, fim = a, b
    return (local if (inicio, fim) == (local.inicio, local.fim)
            else localizar(local.caminho, inicio, linhas[inicio - 1:fim]))


def ampliar_selecao(passagens: list[Local], candidatas: Iterable[Local],
                    ler: Callable[[str], tuple[str, ...]]) -> list[Local]:
    """Usa superjanelas canônicas sem perder evidência ou exceder 4.500 bytes."""
    def tamanho(p: Local) -> int:
        return len("\n".join(ler(p.caminho)[p.inicio - 1:p.fim]).encode())

    selecionadas = list(passagens)
    total = sum(map(tamanho, selecionadas)) + max(0, len(selecionadas) - 1)
    if total >= _BYTES_AMPLIACAO:
        return selecionadas
    por_fonte: dict[str, list[Local]] = {}
    for p in candidatas:
        por_fonte.setdefault(p.caminho, []).append(p)
    for i, atual in enumerate(selecionadas):
        tamanho_atual = tamanho(atual)
        for candidata in por_fonte.get(atual.caminho, []):
            if (candidata == atual or candidata.inicio > atual.inicio or candidata.fim < atual.fim
                    or candidata.fim - candidata.inicio + 1 > LINHAS_PASSAGEM):
                continue
            maior = tamanho(candidata)
            if maior <= BYTES_PASSAGEM and total + maior - tamanho_atual <= _BYTES_AMPLIACAO:
                selecionadas[i] = candidata
                total += maior - tamanho_atual
                break
    return selecionadas


def reaproveitar_vagas(passagens: list[Local], candidatas: Iterable[Local],
                       ler: Callable[[str], tuple[str, ...]]) -> list[Local]:
    """Troca recortes já contidos por evidência adicional sem perder linhas."""
    selecionadas: list[Local] = []
    for p in passagens:
        if not any(a.caminho == p.caminho and a.inicio <= p.inicio <= p.fim <= a.fim
                   for a in selecionadas):
            selecionadas.append(p)
    if len(selecionadas) == len(passagens):
        return selecionadas

    def tamanho(p: Local) -> int:
        return len("\n".join(ler(p.caminho)[p.inicio - 1:p.fim]).encode())

    total = sum(map(tamanho, selecionadas)) + len(selecionadas) - 1
    for p in candidatas:
        if len(selecionadas) == len(passagens):
            break
        custo = tamanho(p) + 1
        if (total + custo <= _BYTES_AMPLIACAO
                and not any(redundante(p, a, diverso=True) for a in selecionadas)):
            selecionadas.append(p)
            total += custo
    return selecionadas


def _janelas(caminho: str, linhas: tuple[str, ...], *, contextual: bool = False) -> Iterable[_Janela]:
    titulos_por_linha: list[Counter[str]] = []
    if contextual:
        titulos: dict[int, str] = {}
        termos_do_titulo: Counter[str] = Counter()
        for linha in linhas:
            if caminho.endswith(".md") and (titulo := _TITULO.match(linha)):
                nivel = len(titulo[1])
                titulos = {n: t for n, t in titulos.items() if n < nivel}
                titulos[nivel] = titulo[2]
                termos_do_titulo = termos_contextuais(" ".join(titulos.values()))
            titulos_por_linha.append(termos_do_titulo)
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
            cabecalho = titulos_por_linha[pos] if contextual else Counter()
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
        # Vocabulário fora do acervo não conta como evidência contra uma janela do índice contextual.
        tamanho_consulta = len(idf) if self.contextual else len(q)
        ranqueadas = []
        for janela in self._janelas:
            comuns = [t for t in idf if t in janela.termos]
            minimo = 6 if self.contextual else 4
            if (not comuns or len(comuns) < min(2, tamanho_consulta)
                    or len(comuns) * minimo < tamanho_consulta):
                continue
            # Robertson e Zaragoza, k1=1,2 e b=0,75.
            normalizacao = 1.2 * (0.25 + 0.75 * janela.tamanho / self._media)
            pontos = sum((0.8 if t.startswith("@") else 1) * idf[t] * 2.2 * janela.termos[t]
                         / (janela.termos[t] + normalizacao)
                         for t in comuns)
            if self.contextual:
                pontos += 0.65 * sum(idf[t] for t in idf if t in janela.contexto)
                if janela.bloco_inteiro:
                    pontos *= 1.12
                if (janela.caminho == "docs/cdp/EM_ANDAMENTO.md"
                        and not q & {"andamento", "frente", "passagem", "historico"}):
                    pontos *= 0.85
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
    fontes_da_licao = {p.caminho for p in primaria}
    complementares = [p for grupo in ancoras[1:] for p in grupo if p.caminho in fontes_da_licao]
    lexicais = (contextuais[:1], diretas[:1]) if contextuais and diretas and redundante(
        contextuais[0], diretas[0], diverso=True
    ) else (diretas[:1], contextuais[:1])
    if priorizar_nota:
        primeiras = (primaria[:1], lexicais[0], primaria[1:2], lexicais[1])
    else:
        primeiras = (*lexicais, primaria[:1], contextuais[1:2], diretas[1:2], primaria[1:2])
    ordem = (*primeiras, complementares, diretas[1:2], contextuais[1:3],
             *(grupo[:1] for grupo in ancoras[1:]), diretas[2:], contextuais[3:], primaria[2:],
             *(grupo[1:] for grupo in ancoras[1:]))
    for grupo in ordem:
        for local in grupo:
            # Uma segunda nota pode ampliar a regra na mesma fonte sem repeti-la por inteiro.
            diverso = grupo is not complementares
            if any(redundante(local, anterior, diverso=diverso) for anterior in selecao):
                sobrepostas.append(local)
                continue
            selecao.append(local)
            if len(selecao) == limite:
                return selecao
            if grupo is complementares:
                break
    for local in sobrepostas:
        if not any(redundante(local, anterior) for anterior in selecao):
            selecao.append(local)
            if len(selecao) == limite:
                break
    return selecao
