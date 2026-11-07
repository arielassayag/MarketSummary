"""Memória de procedimentos do CDP: notas derivadas, consultadas em uma revisão Git.

A recuperação usa apenas a revisão capturada no início do comando. A auditoria
da árvore de trabalho é separada e nunca torna um rascunho recuperável.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from functools import cached_property
from pathlib import Path
from typing import Annotated, BinaryIO, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .leitura_arquivos import receber_fd
from .memoria_busca import (
    BYTES_PASSAGEM,
    LINHAS_PASSAGEM,
    IndicePassagens,
    Local,
    ampliar_selecao,
    combinar_evidencias,
    completar_bloco,
    reaproveitar_vagas,
    reunir_ancoras,
    termos_contextuais,
)
from .memoria_busca import (
    normalizar as _normalizar,
)
from .memoria_reforcos import IndiceReforcos
from .memoria_secoes import IndiceSecoes

Escopo = Literal["desenvolvimento", "operador", "status", "semanal", "diario", "risco",
                 "cobertura", "calibracao"]
ESCOPO: dict[Escopo, tuple[str, ...]] = {
    "desenvolvimento": ("playbooks/RETOMAR", "ARQUITETURA", "DECISOES", "EM_ANDAMENTO",
                        "REPRODUZIR", "REPLAY_OPERACIONAL"),
    "operador": ("playbooks/RETOMAR", "AUTOMACAO", "EXECUCAO", "SITE", "EM_ANDAMENTO",
                 "RETIFICACAO_EDITORIAL"),
    "status": ("playbooks/STATUS", "AUTOMACAO", "SITE"),
    "semanal": ("playbooks/SEMANAL", "EXECUCAO", "TESE", "METODOLOGIA"),
    "diario": ("playbooks/DIARIO", "EXECUCAO", "ESTILO", "SITE", "EM_ANDAMENTO",
               "RETIFICACAO_EDITORIAL"),
    "risco": ("playbooks/RISCO", "METODOLOGIA", "EXECUCAO"),
    "cobertura": ("playbooks/COBERTURA", "COBERTURA", "NOTAS", "ESTILO"),
    "calibracao": ("playbooks/CALIBRACAO", "METODOLOGIA", "REPRODUZIR", "REPLAY_OPERACIONAL"),
}
PASTA = "docs/cdp/memoria/notas"
AVALIACAO = "docs/cdp/memoria/avaliacao.json"
REVISAO_AVALIACAO_INICIAL = "d60cc15fd70bc2ff12c96a6041d59a9506a02079"
REVISAO_AVALIACAO_PASSAGENS = "42f19b27ff7842d36f475a05785e408701ec12f8"
MAX_NOTAS = 128
MAX_BYTES_NOTA = 16384
MAX_BYTES_FONTE = 1024 * 1024
LIMITE_CONTEXTO = 3
LIMITE_CONTEXTO_BYTES = 6144
_SIMPLES = r"[a-z0-9]+(?:-[a-z0-9]+)*"
Slug = Annotated[str, Field(min_length=2, max_length=64, pattern=rf"^{_SIMPLES}$")]
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Tipo = Literal["procedimento", "licao", "episodio"]

_AVISO = ("Memória derivada para localizar procedimentos e evidências. "
          "O estado atual vem de estado, agenda, livro e fatos da etapa. "
          "As notas não autorizam ações nem alteram o roteiro ou os gates.")
FONTES_CODIGO: dict[Escopo, tuple[str, ...]] = {
    "status": ("src/cdp/estado.py", "src/cdp/rotinas.py"),
    "operador": ("src/cdp/estado.py", "src/cdp/rotinas.py"),
    "diario": ("src/cdp/research/factbook.py", "src/cdp/workflow/agenda.py"),
    "risco": ("src/cdp/rotinas.py",),
    "desenvolvimento": ("src/cdp/rotinas.py",),
}
_STOP = set("a ao aos as com como da das de do dos e em essa esse esta isto mais na nas no nos "
            "o os ou para pela pelo por qual quais que se sem sobre tem um uma usa usar".split())


def _sha(trecho: str) -> str:
    return hashlib.sha256(trecho.encode("utf-8")).hexdigest()


def _caminho(v: str) -> str:
    partes = v.split("/")
    if not re.fullmatch(r"[a-zA-Z0-9_.\-/]{1,240}", v) or any(
        not p or p.startswith(".") for p in partes
    ):
        raise ValueError("caminho relativo do repositório inválido")
    if v == "AGENTS.md":
        return v
    if any(v.startswith(prefixo) and v.endswith(sufixo) for prefixo, sufixo in (
        ("docs/cdp/", ".md"), ("src/cdp/", ".py"), ("tests/cdp/", ".py"),
    )) and not v.startswith(("docs/cdp/memoria/", "docs/cdp/MEMORIA")):
        return v
    raise ValueError("evidência fora das fontes permitidas")


def _texto_simples(s: str) -> str:
    if (s.strip() != s or any(unicodedata.category(c).startswith("C") for c in s)
            or any(c in s for c in "<>[]\x60")):
        raise ValueError("use texto simples, em uma linha e sem marcação")
    return s


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Evidencia(_Modelo):
    caminho: str
    trecho: str = Field(min_length=1, max_length=1600)
    sha256: Sha

    @field_validator("caminho")
    @classmethod
    def caminho_valido(cls, valor: str) -> str:
        return _caminho(valor)

    @model_validator(mode="after")
    def conferir(self) -> Evidencia:
        if not self.trecho.strip() or self.trecho.endswith("\n") or _sha(self.trecho) != self.sha256:
            raise ValueError("trecho vazio, com nova linha final ou hash divergente")
        return self


class Nota(_Modelo):
    id: Slug
    tipo: Tipo
    estado: Literal["candidata", "curada", "retirada"]
    titulo: str = Field(min_length=1, max_length=100)
    resumo: str = Field(min_length=1, max_length=420)
    escopos: list[Escopo] = Field(min_length=1, max_length=len(ESCOPO))
    tags: list[Annotated[str, Field(min_length=1, max_length=48)]] = Field(max_length=8)
    registrada_em: date
    revisada_em: date | None
    rever_em: date | None
    destaque: bool
    substitui: list[Slug] = Field(max_length=8)
    evidencias: list[Evidencia] = Field(min_length=1, max_length=4)

    @field_validator("titulo", "resumo")
    @classmethod
    def texto_simples(cls, valor: str) -> str:
        return _texto_simples(valor)

    @model_validator(mode="after")
    def conferir(self) -> Nota:
        for tags in (self.tags, self.escopos, self.substitui):
            if len(set(tags)) != len(tags):
                raise ValueError("lista com itens repetidos")
        for tag in self.tags:
            _texto_simples(tag)
        if self.id in self.substitui:
            raise ValueError("uma nota não pode substituir a si mesma")
        if len({(e.caminho, e.sha256) for e in self.evidencias}) != len(self.evidencias):
            raise ValueError("evidência repetida")
        if self.estado == "candidata":
            if self.revisada_em or self.rever_em or self.destaque:
                raise ValueError("candidata não tem revisão, prazo ou destaque")
        elif not (self.revisada_em and self.rever_em and
                  self.registrada_em <= self.revisada_em < self.rever_em):
            raise ValueError("datas de registro, revisão e prazo inconsistentes")
        if self.destaque and self.estado != "curada":
            raise ValueError("apenas notas curadas podem entrar em destaque")
        return self


class _Caso(_Modelo):
    id: Slug
    escopo: Escopo
    consulta: str = Field(min_length=1, max_length=240)
    notas_esperadas: list[Slug] = Field(max_length=10)
    fontes_esperadas: list[str] = Field(max_length=10)


class _Avaliacao(_Modelo):
    data: date
    casos: list[_Caso] = Field(min_length=1, max_length=128)


class MemoriaErro(ValueError):
    """O catálogo ou uma evidência não pôde ser lido."""


class MemoriaGitIndisponivel(MemoriaErro):
    """Git não pôde provar a revisão ou ler os objetos locais."""


def _chaves_unicas(pares: list[tuple[str, object]]) -> dict:
    out = dict(pares)
    if len(out) != len(pares):
        raise MemoriaErro("chave JSON repetida")
    return out


def _git(raiz: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", "--literal-pathspecs", "-C", str(raiz), *args],
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "",
                 "GIT_GRAFT_FILE": os.devnull},
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MemoriaGitIndisponivel("Git indisponível para a leitura local") from exc
    return proc.stdout


def raiz_repo() -> Path:
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip()).resolve()


class Fontes:
    def __init__(self, raiz: Path, *, trabalho: bool = False, revisao: str | None = None):
        self.raiz = raiz.resolve()
        self.trabalho = trabalho
        if revisao is not None and (
            trabalho or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revisao)
            or _git(self.raiz, "cat-file", "-t", revisao).strip() != b"commit"
        ):
            raise MemoriaErro("revisão exige o hash completo de um commit local")
        self.revisao = revisao or _git(self.raiz, "rev-parse", "--verify", "HEAD").decode().strip()
        self._cache: dict[str, tuple[str, ...] | None] = {}

    def catalogo(self) -> list[str]:
        if self.trabalho:
            pasta = self.raiz / PASTA
            if pasta.resolve() != pasta:
                raise MemoriaErro("o catálogo não pode ser um link")
            if not pasta.exists():
                raise MemoriaErro("catálogo de notas ausente")
            nomes = sorted(p.name for p in pasta.iterdir() if p.suffix == ".json")
        else:
            registros = _git(self.raiz, "ls-tree", "-r", "-z", "--name-only", self.revisao,
                             "--", PASTA).decode().split("\0")
            nomes = sorted(c.removeprefix(PASTA + "/") for c in registros if c.endswith(".json"))
        if not nomes or len(nomes) > MAX_NOTAS or any(
            not re.fullmatch(rf"{_SIMPLES}\.json", n) or len(n) > 69 for n in nomes
        ):
            raise MemoriaErro("catálogo vazio, excessivo ou com nomes inválidos")
        return [f"{PASTA}/{n}" for n in nomes]

    def ler(self, caminho: str, limite: int) -> bytes:
        if self.trabalho:
            arquivo = self.raiz / caminho
            # Recusa links e membros especiais antes da recepção, inclusive FIFOs.
            if arquivo.resolve() != arquivo or not stat.S_ISREG(arquivo.lstat().st_mode):
                raise MemoriaErro("fonte não é arquivo regular")
            return receber_fd(arquivo, limite)[0]
        registro = _git(self.raiz, "ls-tree", "--full-tree", "-l", self.revisao, "--", caminho)
        meta, separador, nome = registro.rstrip(b"\n").partition(b"\t")
        if not separador or nome != caminho.encode() or b"\n" in meta:
            raise MemoriaErro("fonte ausente na revisão")
        modo, tipo, objeto, tamanho = meta.split()
        if modo not in (b"100644", b"100755") or tipo != b"blob":
            raise MemoriaErro("fonte não regular")
        if not tamanho.isdigit():
            raise MemoriaGitIndisponivel("objeto Git indisponível para a leitura local")
        if int(tamanho) > limite:
            raise MemoriaErro("fonte acima do limite")
        return _git(self.raiz, "cat-file", "blob", objeto.decode())

    def linhas(self, caminho: str) -> tuple[str, ...]:
        _caminho(caminho)
        if caminho not in self._cache:
            try:
                self._cache[caminho] = tuple(
                    self.ler(caminho, MAX_BYTES_FONTE).decode("utf-8").splitlines()
                )
            except MemoriaGitIndisponivel:
                raise
            except (ValueError, OSError, RuntimeError):
                self._cache[caminho] = None
        valor = self._cache[caminho]
        if valor is None:
            raise MemoriaErro("fonte ausente, ilegível ou fora dos limites")
        return valor


def _localizar(fontes: Fontes, ev: Evidencia) -> Local:
    linhas = fontes.linhas(ev.caminho)
    trecho = tuple(ev.trecho.split("\n"))
    n = len(trecho)
    pos = [i for i, linha in enumerate(linhas)
           if linha == trecho[0] and linhas[i:i + n] == trecho]
    if len(pos) != 1:
        raise MemoriaErro("trecho ausente ou ambíguo na fonte")
    return Local(ev.caminho, pos[0] + 1, pos[0] + n, ev.sha256)


@dataclass(frozen=True)
class Registro:
    nota: Nota
    locais: tuple[Local, ...]

    def json(self) -> dict:
        return {
            "id": self.nota.id, "tipo": self.nota.tipo, "titulo": self.nota.titulo,
            "resumo": self.nota.resumo, "revisada_em": self.nota.revisada_em.isoformat(),
            "rever_em": self.nota.rever_em.isoformat(),
            "evidencias": [local.json() for local in self.locais],
        }


def _tokens(s: str) -> set[str]:
    termos = set(re.findall(r"[a-z0-9]{2,}", _normalizar(s))) - _STOP
    # Normalização leve de plural em português; não exige modelo, dicionário ou rede.
    return {t[:-3] + "ao" if len(t) > 4 and t.endswith("oes") else
            t[:-1] if len(t) > 4 and t[-2:] in ("as", "es", "is", "os", "us") else t
            for t in termos}


_MERCADO = re.compile(
    r"\b(?:p&l|pnl|retornos?|resultados?|pl|precos?|patrimonio|rentabilidade|"
    r"cotac(?:ao|oes)|perdas?|ganhos?|drawdown|volatilidade|moedas?|pesos?|liquidez|"
    r"sharpe|shorts?|longs?|papeis)\b"
)
_DOMINIO = re.compile(
    r"\b(?:kill[- ]switch|executor|rotinas?|agenda|carteira|posic(?:ao|oes)|exposicao|"
    r"montagem|pendencias?|fechamento|trava|cobertura|risco|relatorios?|calibracao|"
    r"publicacao|portal|pages|implantacao|deploy|revisao|disparo|rodada|livro|e-?mails?|"
    r"snapshot|ensaio|captura|manifesto|sha[- ]?256|commits?|fila|emissor(?:es)?|"
    r"incidentes?|monitor|alertas?)\b"
)
_TEMA_CDP = re.compile(
    r"\b(?:cdp|cabras? da peste|leilao|mandato|gate|benchmark|factbook|fundos?|"
    r"custodia|auditoria|origem|reproducao|linhagem|evidencias?|playbooks?|skills?|"
    r"replay|point-in-time|pit|validador(?:es)?|fontes? primarias?|recepcao|"
    r"substituic(?:ao|oes)|candidatas?|curadoria|proveniencia|hash|cortes?|"
    r"rebalanceamento|retificacao|selagem|agendamento|execucao|publicar|taxas?|"
    r"indices?|dados simulados|atestado|certificac(?:ao|oes)|backtest|bolsa|"
    r"corretagem|lotes? fracionarios?|xbrl|balancos?|brier|valuation|etfs?|cotistas?|"
    r"preg(?:ao|oes)|cambio|desfechos?)\b"
)
_VOCABULARIO_TRABALHO = re.compile(
    r"\b(?:arquivos?|coletas?|clones?|consultas?|fontes?|modelos?|notas?|dados?|"
    r"teses?|pesquisas?|rascunhos?|propostas?|previs(?:ao|oes)|decis(?:ao|oes)|"
    r"documentos?|comunicados?|divulgac(?:ao|oes)|publicad[oa]s?|fatos?|atrasos?|"
    r"etapas?|datas?|prazos?|vers(?:ao|oes)|gestor(?:es)?|saude|autoria|"
    r"testes?|validac(?:ao|oes)|resumos?|remot[oa]s?|autor(?:es)?)\b"
)
_TEMPO = re.compile(
    r"\b(?:agora|hoje|ontem|(?:pregao|dia) anterior|atual(?:mente|is)?|ultim[oa]s?|mais recente|proxim[oa]s?|"
    r"neste (?:momento|instante|minuto)|no momento(?! (?:d[aeo]s?|em que)\b)|"
    r"(?:dest[ea]|nest[ea]) (?:manha|tarde|noite|semana|mes)|"
    r"em vigor|vigentes?|esta valendo)\b"
    r"|\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
    r"\d{1,2} de (?:janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro))\b"
)
_OCORRENCIA = re.compile(
    r"\b(?:ja|ainda) (?:rodou|executou|fechou|entregou|publicou|consta|subiu|saiu|"
    r"chegou|encerrou|concluiu|terminou|foi publicado|foi enviado)\b"
    r"|\b(?:acab(?:ei|amos|ou|aram) de|consta(?:m)?|gravou|publicou|"
    r"selad[oa]s?|anotad[oa]s?|observad[oa]s?|registrad[oa]s?|designad[oa]s?|"
    r"abert[oa]s?|ficou|ficaram|marcou|primeir[oa]s?)\b"
    r"|\b(?:esta|estao|permanece(?:m)?|continua(?:m)?|"
    r"alertas?|sinais?|bloqueios?|gatilhos?|notas?|travas?|tarefas?|rotinas?|ordens?|posicoes)"
    r" ativ[oa]s?\b"
    r"|\bmedid[oa]s? (?:em|n[oa]s?|pel[oa]s?|durante)\b"
    r"|\b(?:ja|ainda) (?:esta|estao) \w+(?:ando|endo|indo)\b"
    r"|\b(?:foi|foram|esta|estao) (?:\w+ ){0,3}\w+(?:ad|id)[oa]s?\b"
    r"|\bja (?:teve|tiveram) (?:\w+ ){0,7}\w+(?:ad|id)[oa]s?\b"
    r"|\bpassou (?:na|pela) (?:conferencia|validacao|verificacao)\b"
    r"|\b(?:ainda (?:marca|aponta|lista) (?:como )?(?:pendentes?|abert[oa]s?)|esta no ar)\b"
    r"|\bja (?:voltou|voltaram)\b"
)
_QUANTIFICA_TEMPO = re.compile(r"\b(?:quanto(?: tempo)?|quant[oa]s (?:segundos?|minutos?|horas?|dias?))\b")
_TEMPO_PENDENTE = re.compile(r"\b(?:faltam?|restam?)\b")
_OBRIGACAO_PENDENTE = re.compile(r"\bainda (?:precis(?:a|am)|deve(?:m)?|tem (?:de|que))\b")
_ESPERA_FECHAMENTO = re.compile(
    r"\b(?:ainda espera(?:m)?(?: por| que)?|faltam? (?:registrar|gravar)|"
    r"aguarda(?:m)? (?:registro|fechamento))\b"
)
_LISTA_DE_FECHAMENTOS = re.compile(
    r"\b(?:lista|fila) de (?:datas|preg(?:ao|oes))\b[^?!]*\bfechamentos?\b[^?!]*\b(?:gravar|registrar)\b"
)
_EXPERIMENTO_DOCUMENTADO = re.compile(
    r"\b(?:replay|ensaio|experimento) (?:ja )?(?:documentado|publicado|que (?:simulou|testou|reproduziu))\b"
    r"|\b(?:primeir[oa]|segund[oa]) (?:replay|ensaio|experimento)\b"
)
_ALCANCE_DA_PROVA = re.compile(
    r"\b(?:limites? d[aoe] (?:prova|ensaio|replay|evidencia)|estende a prova|"
    r"outros? cenarios?|comprovadamente (?:igual|equivalente)|classificad[oa] como diagnostico|"
    r"o que (?:isso|ele|o teste|o ensaio) (?:prova|demonstra|sustenta))\b"
)
_SUBORDINADA = re.compile(r"\s+(?:se|caso|quando|depois que|antes que|assim que|logo que)\s+")
_QUADRO_TEMPORAL = re.compile(r"^(?:para|em|n[oa]s?)\b")
_PEDIDO_OBSERVACAO = re.compile(
    r"^(?:me )?(?:quem|qual|quais|quanto|quant[ao]s|onde|quando|em que|o que|que|como esta|"
    r"liste|informe|diga|identifique|mostre|traga|de (?:o|a|os|as))\b"
    r"|\bquero (?:saber|o nome|a data|o valor)\b"
)
_DISTINCAO_DE_TIPOS = re.compile(r"^o que (?:distingue|diferencia|separa|caracteriza)\b")
_RELATIVA_DE_TIPO = re.compile(r"\s+(?:d[oa]s? )?que\s+")
_FUNCAO_DA_SAIDA = re.compile(
    r"^qu(?:al|ais|e) (?:[ao]s? )?(?:saidas?|campos?|artefatos?|arquivos?|secoes?|colunas?) "
    r"(?:mostra(?:m)?|indica(?:m)?|informa(?:m)?|reune(?:m)?|contem|traz(?:em)?)\b"
)
_PROCEDIMENTO = re.compile(
    r"^(?:como (?!esta\b|estao\b|ficou\b|anda\b|se encontra\b)|"
    r"em (?:que situacao|que caso|qual situacao|qual caso)|"
    r"se\b|quando (?:um|uma|a fonte|os dados|a regra)\b|no dia (?:de|da|do)\b|"
    r"o que (?:fazer|faco|acontece quando)|qu(?:al|ais|e)(?: e| sao)? (?:[ao]s? )?"
    r"(?:(?:procedimentos?|roteiros?|comandos?|regras?|diferencas?|criterios?|ordem|fluxos?|"
    r"passos?|condic(?:ao|oes)|campos?)\b|"
    r"(?:verificac(?:ao|oes)|checagens?|evidencias?|provas?|testes?|recibos?|comprovantes?) "
    r"(?:comprova|confirma|demonstra|distingue)m?\b))"
    r"|^de onde (?:vem|saem?)\b[^.?!]*\b(?:a|em) cada\b"
    r"|^quando (?:ha|houver|exist(?:e|em|ir|irem))\b[^,?!]*,\s*(?:qual|quais|como|o que|que|onde)\b"
    r"|^quando (?:ela|ele|isso)\b[^,?!]*,\s*(?:qual|quais|como|o que|que|onde)\b"
)
_PEDIDO_DE_PROCEDIMENTO = re.compile(
    r"(?:^|[,;:]\s*|\b(?:e|ou|diga|explique|mostre|descreva|ensine|saber) )"
    r"como (?!esta\b|estao\b|ficou\b|anda\b|se encontra\b)|"
    r"\b(?:posso\b|podemos\b|pode(?:m)?\b(?! (?:me )?(?:dizer|informar|mostrar)\b)|"
    r"devo\b|deve(?:m)?\b|precis(?:o|a|amos|am)\b|permite\b|autoriza\b|atesta\b|serve para\b|"
    r"o que (?:faco|fazer|vale conferir)|de onde tiro|onde (?:consulto|confiro|preparo)|"
    r"(?:usa|mede|calcula|considera|aplica|define)-se\b|"
    r"(?:metodo|regra|criterio|passos?|roteiro) (?:para|de|da|do)\b)"
)
_CONTROLES = re.compile(r"\b(?:trava|gate|mandato|limites?|autenticacao|permiss(?:ao|oes))\b")
_MUTACAO_OPERACIONAL = re.compile(
    r"^(?:por favor[,:]?\s+)?(?:(?:quero|preciso|peco) que(?: voce)?\s+|"
    r"(?:pode|poderia|favor)\s+)?"
    r"(?:publique|publicar|republique|republicar|apague|apagar|exclua|excluir|"
    r"reescreva|reescrever|edite|editar|substitua|substituir|adultere|adulterar|"
    r"forje|forjar|falsifique|falsificar|assine|assinar|grave|gravar|"
    r"troque|trocar|altere|alterar|remova|remover|retifique|retificar)\b"
    r"[^.!?\n]{0,140}\b(?:livro|carteira|ordens?|relatorios?|dados?|"
    r"provas?|evidencias?|recibos?|hash(?:es)?|trilhas?|notas?|gates?|travas?)\b"
)
_BURLA = re.compile(
    r"(?:^|[.!?]\s+)(?:ignore|burle|contorne|drible)\b|"
    r"\b(?:como|mandou|instruiu a|disse para) (?:ignorar|burlar|contornar|driblar)\b"
)
_SEGREDO = r"(?:senhas?|credenciais|tokens?|chaves? (?:privadas?|de api|de acesso))"
_EXTRACAO_SEGREDO = re.compile(
    rf"\b(?:recupere|mostre|revele|divulgue|exiba|exponha|imprima|envie|copie|extraia)\b"
    rf"(?:[\w\s]{{0,40}})\b{_SEGREDO}\b|\bqual(?: e)? [oa] {_SEGREDO}\b"
)
_NEGOCIACAO_REAL = re.compile(
    r"\b(?:corretoras?|ord(?:em|ens) rea(?:l|is)|capital real|dinheiro de verdade|"
    r"conta real|dinheiro real)\b"
)
_PEDIDO_NEGOCIACAO = re.compile(
    r"(?:^|[.!?]\s+|\be\s+)(?:conecte|execute|mande|envie|emita|transmita|"
    r"negocie|compre|venda|opere)\b"
)
_RECURSO_PRIVADO = re.compile(
    r"\b(?:repositorios?|projetos?|sistemas?|contas?|ambientes?) "
    r"(?:privad[oa]s?|intern[oa]s?|restrit[oa]s?|confidencia(?:l|is))\b"
)
_ORGANIZACAO_EXTERNA = re.compile(r"\boutra (?:organizacao|empresa|instituicao)\b")
_NOME_CDP = r"cdp|marketsummary|cabras? da peste"
_REFERENCIAS_CDP = rf"{_NOME_CDP}|factbook|cdp-trava|backtest[- ]operacional"
_REFERENCIA_EXPLICITA_CDP = re.compile(rf"\b(?:{_REFERENCIAS_CDP})\b")
_SEM_VINCULO_CDP = re.compile(
    r"\b(?:fora d[oa]|alhei[oa]s? a[oa]|sem (?:vinculo|relacao) com(?: o| a)?|"
    r"nao (?:faz(?:em)? parte d[oa]|pertence(?:m)? a[oa]|integra(?:m)? [oa])) "
    rf"(?:{_NOME_CDP})\b(?!-[a-z0-9])"
)
_ACESSO_A_RECURSO = re.compile(r"\b(?:acessos?|permiss(?:ao|oes)|colaboradores?|membros?)\b")
_CONTEXTO_ALHEIO = re.compile(
    r"\b(?:(?:contas?|carteiras?|agendas?|calendarios?) pesso(?:al|ais)|"
    r"(?:relatorios?|trabalhos?|tarefas?|atividades?) (?:escolar(?:es)?|de escola|de aula)|"
    r"google (?:calendar|agenda|calendario)|(?:agenda|calendario) do (?:google|outlook|icloud)|"
    r"(?:outlook|icloud|apple) calendar)\b"
)
_HOMONIMO_CDP = re.compile(
    r"\b(?:cdp (?:de|para) dados de clientes|customer data platform|"
    r"(?:edital|curso) (?:chama|abrevia|denomina)(?: como| de)? cdp)\b"
)
_OUTRO_DOMINIO = re.compile(
    r"\b(?:aplicativ[oa]s? de receitas|marmitas?|cardapios?|interruptor d[eo] guidao|"
    r"ignicao (?:da moto|do motor)|album digital|cobertura residencial|feira rural|"
    r"carteiras? (?:(?:digital|digitais) )?de vacinacao|firmware d[ae] cameras?|"
    r"cobertura de ferias|portao d[ae] garagem)\b"
)
_VINCULO_CDP = re.compile(
    rf"\b(?:{_REFERENCIAS_CDP}|kill[- ]switch|carteira simulada|agenda das rotinas)\b"
)
_MEDICAO_DE_ATIVO = re.compile(
    r"\b(?:retornos?|rentabilidade|volatilidade|cotac(?:ao|oes)) d[aeo]s? "
    r"(?:indices?|benchmarks?|etfs?|carteiras?|ac(?:ao|oes))\b"
)
_TERMOS_INCIDENTAIS = frozenset(
    "cada meu minha meus minhas seu sua seus suas ele ela eles elas eu estao estava estavam entre "
    "mas num numa agora atual atualmente hoje ontem ultimo ultima ultimos ultimas ja "
    "dois duas tres quatro cinco seis sete oito nove dez foi foram era eram ser ter teve tiveram "
    "diga escolha faca identifique informe liste mostre revise traga".split()
)
_REVISAO_EDITORIAL = frozenset({"@texto-editorial", "@rejeicao-validacao", "@correcao"})
_ARTEFATO_COBERTURA = re.compile(r"\b(?:modelos?|retratos?)\b")
_SAIDA_COBERTURA = re.compile(r"\b(?:balancos?|resultados?|ratings?|precos?[- ]alvo)\b")
_CONFIANCA_DO_RETRATO = re.compile(r"\b(?:nivel|grau|classificacao) de confianca\b")
_ESCRITA_DO_CLONE = re.compile(r"\b(?:somente leitura|escrita habilitada|pode gravar o livro)\b")
_RESPONSAVEL_PELO_LIVRO = re.compile(r"\bresponsavel (?:por gravar o livro|pela escrita)\b")
_ENTREGA_DOCUMENTAL = re.compile(
    r"\b(?:e-?mails?|entregas? d[oa]s? (?:relatorios?|pdfs?|comentarios?|notas?|resumos?))\b"
)
_TESE_DO_CDP = re.compile(
    r"\b(?:tese_publicada|teses? (?:semana(?:l|is)|d[oa] (?:semana|carteira|montagem|cdp)|"
    r"(?:ja )?publicadas?))\b|\bjustificativa\b[^.?!]{0,100}\bcarteira\b"
)
_PUBLICADO = re.compile(r"\b(?:publicad[oa]s?|publicou|publicaram|publicac(?:ao|oes))\b")
_PEDIDO_METADADO = re.compile(
    r"^(?:(?:me )?quem\b|(?:(?:me )?(?:qual|quais|que)(?: e| sao| foi| foram)?|"
    r"(?:me )?(?:informe|diga|mostre|traga|liste|identifique)|em que)\s+"
    r"(?:[ao]s?\s+)?(?:autoria|autor(?:a|es|as)?|assinatura|mind|vers(?:ao|oes)|"
    r"identidad(?:e|es)|datas?|carimbo|horario|sha[- ]?256|hash)\b)"
)


def _pedido_fora_do_escopo(q: str) -> bool:
    """Filtra pedidos de execução ou acesso que a memória consultiva não atende."""
    nega_vinculo = _SEM_VINCULO_CDP.search(q)
    if nega_vinculo and not _REFERENCIA_EXPLICITA_CDP.search(_SEM_VINCULO_CDP.sub(" ", q)):
        return True
    if (_HOMONIMO_CDP.search(q) or _OUTRO_DOMINIO.search(q)) and not _REFERENCIA_EXPLICITA_CDP.search(
        _HOMONIMO_CDP.sub(" ", q)
    ):
        return True
    return bool(_MUTACAO_OPERACIONAL.search(q)
                or (_BURLA.search(q) and _CONTROLES.search(q)) or _EXTRACAO_SEGREDO.search(q)
                or (_NEGOCIACAO_REAL.search(q) and _PEDIDO_NEGOCIACAO.search(q))
                or (_RECURSO_PRIVADO.search(q) and (nega_vinculo or _ORGANIZACAO_EXTERNA.search(q))
                    and _ACESSO_A_RECURSO.search(q))
                or (_CONTEXTO_ALHEIO.search(q) and not _VINCULO_CDP.search(q)))


def _tema_do_cdp(q: str) -> bool:
    return bool(_DOMINIO.search(q) or _MERCADO.search(q) or _TEMA_CDP.search(q)
                or len(set(_VOCABULARIO_TRABALHO.findall(q))) >= 2)


def _sobre_retrato_de_cobertura(q: str) -> bool:
    return bool((_ARTEFATO_COBERTURA.search(q) and _SAIDA_COBERTURA.search(q))
                or (re.search(r"\bretratos?\b", q) and _CONFIANCA_DO_RETRATO.search(q)))


def _termos_de_observacao(q: str) -> set[str]:
    temas = _DOMINIO.findall(q) + _MERCADO.findall(q)
    if _sobre_retrato_de_cobertura(q):
        temas.extend(_ARTEFATO_COBERTURA.findall(q) + _SAIDA_COBERTURA.findall(q))
    if _PUBLICADO.search(q):
        temas.extend(_TESE_DO_CDP.findall(q))
    return set(termos_contextuais(" ".join(temas)))


def _pede_prova_de_experimento(q: str) -> bool:
    return bool(_EXPERIMENTO_DOCUMENTADO.search(q) and _ALCANCE_DA_PROVA.search(q))


def _pede_estado(q: str) -> bool:
    if _pede_prova_de_experimento(q):
        return False
    # Uma situação narrada antes da pergunta dá contexto, mas não muda a intenção.
    for frase in re.split(r"(?<=[.!?])\s+", q):
        quadro = ""
        if not _PEDIDO_OBSERVACAO.match(frase):
            fronteira = next((m for m in re.finditer(r",\s+", frase)
                              if _PEDIDO_OBSERVACAO.match(frase[m.end():])), None)
            if fronteira:
                inicio = frase[:fronteira.start()]
                if _QUADRO_TEMPORAL.match(inicio):
                    quadro = inicio
                frase = frase[fronteira.end():]
        assunto = f"{quadro} {frase}"
        metadado_da_tese = (_TESE_DO_CDP.search(assunto) and _PUBLICADO.search(assunto)
                            and _TEMPO.search(assunto) and _PEDIDO_METADADO.match(frase))
        if not (_MERCADO.search(assunto) or _DOMINIO.search(assunto) or _VINCULO_CDP.search(assunto)
                or _sobre_retrato_de_cobertura(assunto) or metadado_da_tese):
            continue
        pedido = _PEDIDO_OBSERVACAO.search(frase) or frase.endswith("?")
        enunciado = _SUBORDINADA.split(frase, maxsplit=1)[0]
        if (pedido and _ESCRITA_DO_CLONE.search(enunciado)
                and re.search(r"\b(?:neste|nesta|este|esta) (?:clone|copia|sessao|ambiente)\b", assunto)):
            return True
        if pedido and _RESPONSAVEL_PELO_LIVRO.search(assunto) and _OCORRENCIA.search(assunto):
            return True
        if pedido and _LISTA_DE_FECHAMENTOS.search(enunciado) and _TEMPO.search(enunciado):
            return True
        if re.search(r"\bpor padrao\b", enunciado) and not _TEMPO.search(enunciado):
            continue
        if _FUNCAO_DA_SAIDA.match(enunciado) and not _TEMPO.search(quadro):
            continue
        distincao = _DISTINCAO_DE_TIPOS.match(enunciado)
        if distincao:
            # A relativa descreve a categoria comparada, não data a observação.
            foco = _RELATIVA_DE_TIPO.split(enunciado[distincao.end():], maxsplit=1)[0]
            if not (_TEMPO.search(foco) or _OCORRENCIA.search(foco)):
                continue
        if _PROCEDIMENTO.search(frase) or _PEDIDO_DE_PROCEDIMENTO.search(
            _OBRIGACAO_PENDENTE.sub(" ", enunciado)
        ):
            continue
        tempo_restante = _QUANTIFICA_TEMPO.search(enunciado) and _TEMPO_PENDENTE.search(enunciado)
        if pedido and (_TEMPO.search(enunciado) or _TEMPO.search(quadro) or _OCORRENCIA.search(enunciado)
                       or _OBRIGACAO_PENDENTE.search(enunciado) or _ESPERA_FECHAMENTO.search(enunciado)
                       or tempo_restante):
            return True
    return False


_DESTINOS_ATUAIS = {
    "ci-github": (
        "Consulte as execuções de `.github/workflows/cdp-ci.yml` no GitHub Actions. Filtre pela revisão "
        "pedida e abra os jobs e etapas da execução correspondente."
    ),
    "passagem-desenvolvimento": (
        "Consulte a passagem corrente em docs/cdp/EM_ANDAMENTO.md na revisão atual."
    ),
    "portal-publicado": (
        "Confira o portal servido e o `source_commit` do `manifest.json`, conforme a procedência em "
        "docs/cdp/SITE.md."
    ),
    "trilha-entrega": "Confira a trilha de entrega descrita em docs/cdp/playbooks/DIARIO.md.",
    "procedencia-commit": (
        "Consulte a procedência do commit gravado. O trailer CDP-Harness identifica o aplicativo e "
        "CDP-Executor identifica o executor."
    ),
    "executor-remoto": (
        "Consulte configs/cdp/executor.yaml na revisão remota e a identidade local em cdp estado."
    ),
    "estado-executor": "Consulte `executor.designado` em `cdp estado` e a identidade deste ambiente.",
    "manifesto-ensaio": (
        "Consulte o manifesto e a verificação da execução solicitada do ensaio isolado, conforme "
        "docs/cdp/REPLAY_OPERACIONAL.md."
    ),
    "manifesto-snapshot": "Consulte o manifesto e a verificação do snapshot ou da captura solicitada.",
    "trava-distribuida": (
        "Consulte cdp trava ver para conferir a ocupação e a expiração da trava distribuída."
    ),
    "estado-kill-switch": (
        "Consulte o campo `kill_switch` em `cdp estado` para conferir o estado efetivo e os eventos de "
        "ativação em `book/audit_log.jsonl` para consultar o registro."
    ),
    "estado-integridade": (
        "Consulte o campo `integridade` em `cdp estado` ou o resultado de `cdp verify` no clone de "
        "operação."
    ),
    "agenda-fechamentos": "Consulte fechamentos_pendentes em cdp agenda no clone de operação.",
    "retrato-cobertura": (
        "Consulte o retrato da cobertura em `book/cobertura/<data>/`. A tabela `modelos.csv` registra os "
        "preços-alvo por emissor. Use os campos de cobertura em cdp agenda para identificar a data "
        "vigente."
    ),
    "fila-cobertura": (
        "Consulte a fila da nota na saída corrente de cdp nota agenda no clone de operação."
    ),
    "agenda-rotinas": (
        "Consulte `cdp rotinas proximas` ou o campo `proximas_tarefas` em `cdp estado` para conferir os "
        "próximos disparos."
    ),
    "relatorio-calibracao": (
        "Consulte `reports/backtest/<data>/mensal/metrics.json` ou o relatório da calibração "
        "correspondente à rodada."
    ),
    "proposta-semanal": (
        "Consulte a proposta da montagem em `book/<semana>/proposal_v<versao>.json`. Se não houver "
        "proposta para essa etapa, registre a ausência."
    ),
    "agenda-montagem": (
        "Consulte semanal.proximo_rebalanceamento, semanal.prazo_efetivo e semanal.mercados_fechados na "
        "saída de cdp agenda."
    ),
    "relatorio-risco": (
        "Consulte o relatório do monitor em `reports/risk/<data>/risco_<HHMM>.json`. Confira `gerado_em` "
        "para identificar o disparo, inclusive em arquivos com sufixo. O VaR registrado está em "
        "`risco.var_1d_99` e os alertas em `gatilhos`."
    ),
    "carteira-efetivada": "Consulte a carteira efetivada no livro em `book/<semana>/booked.json`.",
    "tese-publicada": (
        "Consulte a tese publicada no livro, em book/<semana>/tese/tese_publicada.json, e o evento "
        "WEEKLY_THESIS correspondente na trilha de auditoria."
    ),
    "estado-pendencias": "Consulte o campo `pendencias` em `cdp estado` no clone das rotinas.",
    "relatorio-semanal": "Consulte o relatório semanal em `reports/semanal/<data>/relatorio.md`.",
    "relatorio-diario": (
        "Consulte `reports/daily/<data>/relatorio.md` ou os fatos correspondentes no FactBook em "
        "`reports/daily/<data>/facts.md`."
    ),
    "estado-agenda": "Consulte o estado e a agenda no clone de operação.",
}


def _destino_atual(consulta: str, *, forcar: bool = False) -> tuple[str, str] | None:
    """Identifica o destino de leitura para uma consulta de estado."""
    codigo = _codigo_destino_atual(consulta, forcar=forcar)
    return (codigo, _DESTINOS_ATUAIS[codigo]) if codigo else None


def _codigo_destino_atual(consulta: str, *, forcar: bool) -> str | None:
    q = _normalizar(consulta).strip()
    if not forcar and not _pede_estado(q):
        return None
    if re.search(r"\b(?:ci|cdp[-_]ci|integracao continua)\b", q) or (
        re.search(r"\b(?:github|actions|pipeline)\b", q)
        and re.search(r"\b(?:checagens?|lint|testes?|jobs?|checks?|runners?|bateria(?: automatica)?)\b", q)
        and not re.search(r"\b(?:portal|pages|rotinas?|cdp[-_]site)\b", q)
    ):
        return "ci-github"
    if re.search(r"\b(?:frentes? de desenvolvimento|passagem (?:de bastao|(?:mais recente )?do desenvolvimento)|"
                 r"em_andamento)\b", q):
        return "passagem-desenvolvimento"
    if re.search(r"\b(?:portal|pages|implantacao|deploy|pagina publica)\b", q):
        return "portal-publicado"
    if _ENTREGA_DOCUMENTAL.search(q) or (_VINCULO_CDP.search(q) and re.search(r"\bentregas?\b", q)):
        return "trilha-entrega"
    if re.search(r"\bcommits?\b", q):
        return "procedencia-commit"
    executor = re.search(r"\bexecutor\b", q)
    permissao = re.search(r"\b(?:escrita|escritor|gravar o livro|executor\.yaml)\b", q)
    if re.search(r"\b(?:remoto|origin/main|ramo principal d[eo] github)\b", q) and (
        permissao or (executor and re.search(r"\b(?:designad[oa]s?|identidade)\b", q))
    ):
        return "executor-remoto"
    destino_executor = "estado-executor"
    if (_ESCRITA_DO_CLONE.search(q) or _RESPONSAVEL_PELO_LIVRO.search(q)
            or (executor and re.search(r"\b(?:designad[oa]s?|identidade|nome|quem)\b", q))):
        return destino_executor
    if re.search(r"\b(?:manifesto|hash|sha[- ]?256)\b", q):
        if re.search(r"\b(?:ensaio|replay)\b", q):
            return "manifesto-ensaio"
        if re.search(r"\b(?:snapshot|captura)\b", q):
            return "manifesto-snapshot"
    if re.search(r"\breplay operacional\b", q) and re.search(r"\b(?:modo|concluid[oa])\b", q):
        return "manifesto-ensaio"
    if re.search(r"\b(?:trava|bloqueio (?:compartilhado|distribuido))\b", q) and (
        (_QUANTIFICA_TEMPO.search(q) and _TEMPO_PENDENTE.search(q))
        or re.search(r"\b(?:ocupad[oa]s?|ocupacao|expira(?:cao|da|r)?|validade|titular|em nome de|"
                     r"adquirid[oa]s?|liberad[oa]s?)\b", q)
    ):
        return "trava-distribuida"
    if re.search(r"\b(?:kill[- ]switch|chave de emergencia|modo de so reduzir risco)\b", q) and not re.search(
        r"\b(?:relatorios?|gatilhos?|recomendac(?:ao|oes))\b", q
    ):
        return "estado-kill-switch"
    if re.search(r"\b(?:integridade|cdp verify|verificador d[eo] livro|hash divergente)\b", q):
        return "estado-integridade"
    if _LISTA_DE_FECHAMENTOS.search(q) or (
        (_OBRIGACAO_PENDENTE.search(q) or _ESPERA_FECHAMENTO.search(q))
        and re.search(r"\b(?:preg(?:ao|oes)|fechamentos?)\b", q)
    ):
        return "agenda-fechamentos"
    if _sobre_retrato_de_cobertura(q) or (
        re.search(r"\bcobertura\b", q) and re.search(r"\b(?:retratos?|snapshots?|precos?[- ]alvo)\b", q)
    ):
        return "retrato-cobertura"
    if ((re.search(r"\b(?:cobertura|emissor(?:es)?)\b", q) and re.search(
        r"\b(?:fila|notas?|emissor(?:es)?)\b", q)) or re.search(
            r"\b(?:(?:lista|fila) de (?:proximas? )?notas?|proximas? notas? (?:d[oa]|na) fila)\b", q)
    ):
        return "fila-cobertura"
    if re.search(r"\b(?:proxim[oa]s?|agendad[oa]s?|programad[oa]s?)\b", q) and re.search(
        r"\b(?:rotinas?|tarefas?|execuc(?:ao|oes)|disparos?|calibracao|monitoramentos?)\b", q
    ) and not re.search(r"\b(?:montagem|rebalanceamento|propostas?|previa)\b", q):
        return "agenda-rotinas"
    if re.search(r"\b(?:calibracao|sharpe|rodada mensal)\b", q):
        return "relatorio-calibracao"
    if re.search(r"\b(?:propost[ao]s?|previa)\b", q):
        return "proposta-semanal"
    if re.search(r"\b(?:montagem|rebalanceamento|troca de carteira)\b", q) and re.search(
        r"\b(?:agenda|prazos?|mercados?|datas?|dias?|horas?|quando|janelas?|sessao|previst[oa]s?)\b", q
    ):
        return "agenda-montagem"
    if re.search(r"\b(?:monitor|cdp-risco|(?:risco|leitura) intradiari[oa]|disparos? (?:de|do) risco)\b", q) or (
        re.search(r"\b(?:alertas?|hard|soft|var|valor em risco|quantil de perda|relatorios? de risco)\b", q)
        and not re.search(r"\b(?:kill[- ]switch|fechamento|relatorios? semana(?:l|is)|relatorios? diarios?)\b", q)
    ):
        return "relatorio-risco"
    if _TESE_DO_CDP.search(q) and _PUBLICADO.search(q):
        return "tese-publicada"
    if re.search(r"\b(?:carteira|livro)\b", q) and re.search(
        r"\b(?:longs?|shorts?|posic(?:ao|oes)|efetivad[oa]s?|entrou em vigor)\b", q
    ):
        return "carteira-efetivada"
    if re.search(r"\b(?:pendencias?|pendentes?)\b", q):
        return "estado-pendencias"
    if re.search(r"\brelatorios? semana(?:l|is)\b", q):
        return "relatorio-semanal"
    if _MERCADO.search(q) or re.search(
        r"\b(?:fechamento|relatorios? diarios?|quanto (?:marcou|rendeu|valeu|fechou))\b", q
    ):
        return "relatorio-diario"
    if executor:
        return destino_executor
    return "estado-agenda"


def _fonte_atual(consulta: str, *, forcar: bool = False) -> str | None:
    """Devolve a orientação de leitura no formato textual anterior."""
    destino = _destino_atual(consulta, forcar=forcar)
    return destino[1] if destino else None


class Catalogo:
    def __init__(self, fontes: Fontes, data: date):
        self.fontes, self.data = fontes, data
        self.problemas: list[dict[str, str]] = []
        self.contagens = dict.fromkeys(("candidata", "curada", "retirada", "vencida",
                                       "futura", "substituida", "disponivel"), 0)
        notas: dict[str, Nota] = {}
        registros: dict[str, Registro] = {}
        for caminho in fontes.catalogo():
            id_ = Path(caminho).stem
            try:
                bruto = fontes.ler(caminho, MAX_BYTES_NOTA)
                json.loads(bruto, object_pairs_hook=_chaves_unicas)
                nota = Nota.model_validate_json(bruto)
                if nota.id != id_:
                    raise MemoriaErro("ID diverge do nome do arquivo")
            except ValidationError as exc:
                campos = ", ".join(sorted({str(e["loc"][0]) if e["loc"] else "objeto"
                                           for e in exc.errors(include_input=False)}))
                self._problema(id_, "schema", campos)
                continue
            except MemoriaGitIndisponivel:
                raise
            except (ValueError, OSError, RuntimeError):
                self._problema(id_, "arquivo", "arquivo ilegível ou ID divergente")
                continue
            notas[id_] = nota
            self.contagens[nota.estado] += 1
            if nota.estado == "retirada":
                continue
            locais = []
            for ev in nota.evidencias:
                try:
                    locais.append(_localizar(fontes, ev))
                except MemoriaErro as exc:
                    self._problema(id_, "evidencia", f"{ev.caminho}: {exc}")
            if len(locais) == len(nota.evidencias):
                registros[id_] = Registro(nota, tuple(locais))

        from .memoria_linhagem import substituicoes_confirmadas

        self.notas = notas
        substitu, problemas = substituicoes_confirmadas(fontes, data, notas, registros)
        self.problemas.extend(problemas)
        self.substituidas = frozenset(substitu)
        invalidas = {p["id"] for p in self.problemas}
        self.ativos: list[Registro] = []
        for id_, nota in notas.items():
            if nota.estado != "curada":
                continue
            if id_ in substitu:
                self.contagens["substituida"] += 1
            elif data < nota.revisada_em:
                self.contagens["futura"] += 1
            elif data >= nota.rever_em:
                self.contagens["vencida"] += 1
            elif id_ not in invalidas:
                self.ativos.append(registros[id_])

        resumos: dict[str, list[Registro]] = {}
        for reg in self.ativos:
            resumos.setdefault(" ".join(reg.nota.resumo.lower().split()), []).append(reg)
        duplicatas = {a.nota.id for grupo in resumos.values() for a in grupo for b in grupo
                      if a != b and set(a.nota.escopos).intersection(b.nota.escopos)}
        for id_ in sorted(duplicatas):
            self._problema(id_, "duplicata", "resumo ativo repetido no mesmo escopo")
        self.ativos = [r for r in self.ativos if r.nota.id not in duplicatas]
        self.contagens["disponivel"] = len(self.ativos)
        self._primarias: dict[str, list[tuple[int, set[str]]]] = {}
        self.fontes_por_escopo = {
            escopo: tuple(dict.fromkeys((*_primarias(escopo), *(
                local.caminho for registro in self.ativos if escopo in registro.nota.escopos
                for local in registro.locais
            ))))
            for escopo in ESCOPO
        }
        self.indice = BuscaCanonica(fontes, self.fontes_por_escopo)

    def _problema(self, id_: str, codigo: str, detalhe: str) -> None:
        self.problemas.append({"id": id_, "codigo": codigo, "detalhe": detalhe})

    def contexto(self, escopo: Escopo, *, consulta: str | None = None) -> dict:
        out = {"revisao": self.fontes.revisao, "data": self.data.isoformat(), "escopo": escopo,
               "aviso": _AVISO, "catalogo_com_ressalvas": bool(self.problemas),
               "fontes": list(_primarias(escopo)[:3]), "notas": []}
        if consulta is None:
            destacados = sorted(
                (r for r in self.ativos if escopo in r.nota.escopos and r.nota.destaque),
                key=lambda r: (len(r.nota.escopos), r.nota.id),
            )
            notas = [r.json() for r in destacados[:LIMITE_CONTEXTO]]
        else:
            busca = self.buscar(escopo, consulta, LIMITE_CONTEXTO)
            notas = busca["notas"]
            caminhos = (p["caminho"] for p in (*busca["passagens"], *busca["fontes"]))
            ancoras = (ev["caminho"] for nota in notas for ev in nota["evidencias"])
            out.update(modo="por-consulta", destino_atual=busca["destino_atual"],
                       orientacao_atual=busca["orientacao_atual"],
                       fontes=list(dict.fromkeys((*caminhos, *ancoras)))[:3])
        for nota in notas:
            out["notas"].append(nota)
            if max(len((json.dumps(out, ensure_ascii=False, indent=2) + "\n").encode()),
                   len(render_contexto(out).encode())) > LIMITE_CONTEXTO_BYTES:
                out["notas"].pop()
                break
        return out

    def _buscar_notas(self, escopo: Escopo, consulta: str, limite: int, *,
                      expandir: bool = False) -> list[Registro]:
        if expandir:
            return self._buscar_notas_contextuais(escopo, consulta, limite)
        termos = _tokens(consulta)
        notas = []
        if termos:
            for reg in self.ativos:
                n = reg.nota
                if escopo not in n.escopos:
                    continue
                chave = _tokens(n.titulo + " " + " ".join(n.tags))
                resumo = _tokens(n.resumo)
                comuns = termos & (chave | resumo)
                # Sobreposição mínima evita forçar uma lembrança com coincidência incidental.
                if (len(comuns) >= min(2, len(termos)) and termos & chave
                        and len(comuns) * 3 >= len(termos)):
                    pontos = 6 * len(termos & chave) + 2 * len(termos & resumo)
                    notas.append((-pontos, -len(comuns), n.id, reg))
        notas.sort(key=lambda v: v[:3])
        return [r for *_, r in notas[:limite]]

    def _buscar_notas_contextuais(self, escopo: Escopo, consulta: str, limite: int) -> list[Registro]:
        termos = termos_contextuais(consulta).keys()
        referencias = _tokens(" ".join(re.findall(r"\b[A-Z][A-Z0-9]{1,}\b", consulta))) - {"cdp", "ia"}
        candidatas = []
        for registro in self.ativos:
            n = registro.nota
            if escopo not in n.escopos:
                continue
            chaves = termos_contextuais(n.titulo + " " + " ".join(n.tags)).keys()
            resumo = termos_contextuais(n.resumo).keys()
            fonte = termos_contextuais(" ".join(ev.trecho for ev in n.evidencias)).keys()
            candidatas.append((registro, chaves, resumo, fonte))
        pesos = {t: 1 / (1 + sum(t in ch or t in r for _, ch, r, _ in candidatas)) ** 0.5
                 for t in termos}
        ranking = []
        for registro, chaves, resumo, fonte in candidatas:
            comuns = termos & (chaves | resumo | fonte)
            if len(comuns) < 2 or not termos & (chaves | resumo):
                continue
            # Siglas explícitas ganham peso somente se a fonte literal as sustenta.
            pontos = sum(pesos[t] * (3 * (t in chaves) + 2 * (t in resumo) + (t in fonte)
                                     + 3 * (t in fonte and t in referencias)) for t in sorted(comuns))
            ranking.append((-pontos, -len(comuns), registro.nota.id, registro))
        ranking.sort(key=lambda valor: valor[:3])
        return [registro for *_, registro in ranking[:limite]]

    def _recuperar_passagens(self, escopo: Escopo, consulta: str, limite: int,
                             diretas: list[Local], notas: list[Registro]) -> list[Local]:
        termos = termos_contextuais(consulta).keys()
        ancoras = []
        priorizar_nota = False
        for registro in notas:
            fontes: dict[str, list[Local]] = {}
            termos_ancoras: dict[Local, bool] = {}
            for local, evidencia in zip(registro.locais, registro.nota.evidencias, strict=True):
                if (local.fim - local.inicio + 1 <= LINHAS_PASSAGEM
                        and len(evidencia.trecho.encode()) <= BYTES_PASSAGEM):
                    fontes.setdefault(local.caminho, []).append(local)
                    comuns = termos & termos_contextuais(evidencia.trecho).keys()
                    # Um conceito sintético e sua palavra de origem contam como um único sinal.
                    literais = sum(not t.startswith("@") for t in comuns)
                    termos_ancoras[local] = literais >= 2 or (literais == 1 and len(comuns) >= 3)
            reunidas = [p for caminho, locais in fontes.items()
                        for p in reunir_ancoras(locais, self.fontes.linhas(caminho))]
            if reunidas:
                apoio = {p: termos & termos_contextuais("\n".join(
                    self.fontes.linhas(p.caminho)[p.inicio - 1:p.fim]
                )).keys() for p in reunidas}
                primeira = max(reunidas, key=lambda p: len(apoio[p]))
                complementares = sorted((p for p in reunidas if p != primeira), key=lambda p: (
                    -len(apoio[p] - apoio[primeira]), p.caminho != primeira.caminho, -len(apoio[p]),
                ))
                if not ancoras:
                    priorizar_nota = any(tem_apoio and p.caminho == primeira.caminho
                                         and primeira.inicio <= p.inicio <= p.fim <= primeira.fim
                                         for p, tem_apoio in termos_ancoras.items())
                ancoras.append([primeira, *complementares])
        largura = max(limite, 5)
        indice_contextual = self.indice.para_escopo(escopo, contextual=True)
        contextuais = indice_contextual.buscar(consulta, max(largura, 10))
        escolhidas = combinar_evidencias(diretas, contextuais[:largura], ancoras, limite,
                                         priorizar_nota=priorizar_nota)
        janelas_bastao = [i for i, p in enumerate(escolhidas)
                          if p.caminho == "docs/cdp/EM_ANDAMENTO.md"]
        if (ancoras and len(escolhidas) == limite and len(janelas_bastao) >= 3
                and 2 * len(janelas_bastao) > limite
                and not re.search(r"\b(?:passagem(?: de bastao)?|frentes? em andamento|em[-_ ]andamento)\b",
                                  _normalizar(consulta))):
            # Uma terceira janela de histórico não desloca uma fonte nova da lição líder.
            fontes_escolhidas = {p.caminho for p in escolhidas}
            apoio = next((p for p in ancoras[0] if p.caminho not in fontes_escolhidas), None)
            if apoio is not None:
                escolhidas[janelas_bastao[-1]] = apoio
        blocos = [completar_bloco(p, self.fontes.linhas(p.caminho)) for p in escolhidas]
        if not any(p.fim - p.inicio + 1 < LINHAS_PASSAGEM for p in blocos):
            candidatas = (*diretas, *contextuais)
        else:
            diretas_amplas = self.indice.buscar(escopo, consulta, max(limite, 10))
            candidatas = (*diretas_amplas, *contextuais)
            blocos = ampliar_selecao(blocos, candidatas, self.fontes.linhas)
        recuperadas = reaproveitar_vagas(blocos, candidatas, self.fontes.linhas)
        selecionadas = indice_contextual.complementar_com_diretas(
            consulta, recuperadas, diretas, self.fontes.linhas,
        )
        if not selecionadas or all(p.fim - p.inicio + 1 == LINHAS_PASSAGEM for p in selecionadas):
            return selecionadas
        for completas in (False, True):
            estruturais = self.indice.estruturais(escopo, consulta, completas=completas)
            ampliadas = ampliar_selecao(selecionadas, estruturais, self.fontes.linhas)
            selecionadas = reaproveitar_vagas(ampliadas, estruturais, self.fontes.linhas)
        return selecionadas

    def _tem_apoio_no_acervo(self, escopo: Escopo, q: str, diretas: list[Local], notas: list[Registro], *,
                            observacao: bool) -> bool:
        consulta = termos_contextuais(q)
        termos = {t for t in consulta if not t.startswith("@") and not t.isdigit()}
        termos -= _TERMOS_INCIDENTAIS
        tema = _tema_do_cdp(q)
        base = min(3, len(termos)) if tema else 4
        minimo = 2 if observacao else max(2, len(termos) // 5, base)
        topicos = _termos_de_observacao(q) if observacao else set()
        revisao_editorial = not observacao and (tema or escopo in termos) and _REVISAO_EDITORIAL <= consulta.keys()

        def termos_em(texto: str) -> set[str]:
            return termos & termos_contextuais(texto).keys()

        def apoia(p: Local) -> bool:
            literais = termos_contextuais("\n".join(self.fontes.linhas(p.caminho)[p.inicio - 1:p.fim])).keys()
            comuns = termos & literais
            return (len(comuns) >= minimo and (not observacao or bool(comuns & topicos))
                    or revisao_editorial and bool(comuns) and _REVISAO_EDITORIAL <= literais)

        # Uma fonte deve sustentar os termos em conjunto. Etiquetas, aliases e títulos
        # do índice, sozinhos, não autorizam admitir um assunto novo no acervo.
        if any(apoia(p) for p in diretas) or any(
            apoia(p) for p in self.indice.buscar(escopo, q, 5, contextual=True)
        ):
            return True
        for registro in notas:
            nota = registro.nota
            descricao = " ".join((nota.titulo, nota.resumo, *nota.tags))
            if len(termos_em(descricao)) >= minimo and any(len(termos_em(ev.trecho)) >= 2 for ev in nota.evidencias):
                return True
        return False

    @cached_property
    def _refinador_autoridades(self):
        from .memoria_roteamento import RefinadorAutoridades

        return RefinadorAutoridades(self.fontes)

    def buscar(self, escopo: Escopo, consulta: str, limite: int, *,
               estado_atual: bool = False, evidencia_conferida: bool = False) -> dict:
        q = _normalizar(consulta).strip()
        fora = _pedido_fora_do_escopo(q)
        rota = None if fora or evidencia_conferida else _destino_atual(consulta, forcar=estado_atual)
        diretas = [] if fora or estado_atual else self.indice.buscar(escopo, consulta, limite)
        notas = [] if fora or rota else self._buscar_notas(escopo, consulta, limite, expandir=True)
        vinculo = _VINCULO_CDP.search(q) or (rota and _MEDICAO_DE_ATIVO.search(q))
        if not (fora or estado_atual or evidencia_conferida or vinculo):
            fora = not self._tem_apoio_no_acervo(escopo, q, diretas, notas, observacao=bool(rota))
            if fora:
                diretas = []
                notas = []
                rota = None
        refinamento = self._refinador_autoridades.refinar(consulta, rota[0]) if rota else None
        if refinamento:
            codigo = refinamento["codigo"]
            rota = codigo, _DESTINOS_ATUAIS[codigo]
        passagens = [] if fora or rota else self._recuperar_passagens(
            escopo, consulta, limite, diretas, notas
        )
        caminhos = {}
        for local in (() if rota else diretas):
            caminhos.setdefault(local.caminho, local.json())
        return {"revisao": self.fontes.revisao, "data": self.data.isoformat(), "escopo": escopo,
                "aviso": _AVISO, "catalogo_com_ressalvas": bool(self.problemas),
                "notas": [r.json() for r in notas], "fontes": list(caminhos.values()),
                "passagens": [local.json() for local in passagens],
                "destino_atual": rota[0] if rota else None,
                "orientacao_atual": rota[1] if rota else None,
                **({"refinamento_destino": refinamento} if refinamento else {})}

    def _buscar_fontes_v1(self, escopo: Escopo, consulta: str, limite: int) -> list[dict]:
        """Busca por caminho conservada apenas para reproduzir o corpus inicial."""
        termos = _tokens(consulta)
        achados = []
        if not termos:
            return []
        for ordem, caminho in enumerate(_primarias(escopo)):
            if caminho not in self._primarias:
                try:
                    linhas = self.fontes.linhas(caminho)
                except MemoriaErro:
                    continue
                janelas = [(i + 1, _tokens(" ".join(linhas[i:i + 6])))
                           for i, linha in enumerate(linhas) if linha.strip()]
                self._primarias[caminho] = janelas
            pontuado = [(len(termos & texto), -len(texto), -num)
                        for num, texto in self._primarias[caminho]]
            pontos, _, linha = max(pontuado, default=(0, 0, 0))
            if pontos >= min(2, len(termos)) and pontos * 3 >= len(termos):
                achados.append((-pontos, ordem, caminho, -linha))
        return [{"caminho": caminho, "inicio": linha}
                for _, _, caminho, linha in sorted(achados)[:limite]]


def _primarias(escopo: Escopo) -> tuple[str, ...]:
    return (tuple(f"docs/cdp/{nome}.md" for nome in ESCOPO[escopo]) + ("AGENTS.md",)
            + FONTES_CODIGO.get(escopo, ()))


class BuscaCanonica:
    def __init__(self, fontes: Fontes, caminhos: dict[Escopo, tuple[str, ...]]):
        self.fontes = fontes
        self.caminhos = caminhos
        self.indices: dict[tuple[Escopo, bool], IndicePassagens] = {}
        self._indices_secoes: dict[Escopo, IndiceSecoes] = {}
        self._indices_reforcos: dict[Escopo, IndiceReforcos] = {}

    def buscar(self, escopo: Escopo, consulta: str, limite: int, *,
               contextual: bool = False) -> list[Local]:
        return self.para_escopo(escopo, contextual=contextual).buscar(consulta, limite)

    def para_escopo(self, escopo: Escopo, *, contextual: bool) -> IndicePassagens:
        chave = (escopo, contextual)
        if chave not in self.indices:
            self.indices[chave] = IndicePassagens(self._documentos(escopo), contextual=contextual)
        return self.indices[chave]

    def estruturais(self, escopo: Escopo, consulta: str, *, completas: bool = False) -> list[Local]:
        indice = self._indice_estrutural(escopo)
        return indice.compactas(consulta) if completas else indice.buscar(consulta)

    def simbolos(self, escopo: Escopo, consulta: str) -> list[Local]:
        return self._indice_estrutural(escopo).simbolos(consulta)

    def reforcos(self, escopo: Escopo, consulta: str, candidatas: list[Local]) -> list[Local]:
        if escopo not in self._indices_reforcos:
            self._indices_reforcos[escopo] = IndiceReforcos(self.fontes.linhas, self.caminhos[escopo])
        return self._indices_reforcos[escopo].buscar(consulta, candidatas)

    def _indice_estrutural(self, escopo: Escopo) -> IndiceSecoes:
        if escopo not in self._indices_secoes:
            self._indices_secoes[escopo] = IndiceSecoes(self._documentos(escopo))
        return self._indices_secoes[escopo]

    def _documentos(self, escopo: Escopo) -> Iterable[tuple[str, tuple[str, ...]]]:
        for caminho in self.caminhos[escopo]:
            try:
                yield caminho, self.fontes.linhas(caminho)
            except MemoriaErro:
                continue


def _hoje() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def propor(fontes: Fontes, *, id_: str, escopo: Escopo, caminho: str, inicio: int, fim: int,
           data: date, tipo: Tipo, titulo: str, resumo: str) -> Nota:
    linhas = fontes.linhas(caminho)
    if not 1 <= inicio <= fim <= len(linhas):
        raise MemoriaErro("intervalo de linhas fora da fonte")
    trecho = "\n".join(linhas[inicio - 1:fim])
    ev = Evidencia(caminho=caminho, trecho=trecho, sha256=_sha(trecho))
    _localizar(fontes, ev)
    return Nota(id=id_, tipo=tipo, estado="candidata", titulo=titulo, resumo=resumo,
                escopos=[escopo], tags=[], registrada_em=data, revisada_em=None, rever_em=None,
                destaque=False, substitui=[], evidencias=[ev])


def avaliar(catalogo: Catalogo, casos: list[_Caso], limite: int = 3) -> dict:
    """Compara recuperação de caminhos com o mesmo orçamento nas duas abordagens."""
    resultados = []
    for caso in casos:
        notas = ([] if _fonte_atual(caso.consulta) else
                 catalogo._buscar_notas(caso.escopo, caso.consulta, limite))
        ids = [r.nota.id for r in notas]
        direta = [f["caminho"] for f in catalogo._buscar_fontes_v1(
            caso.escopo, caso.consulta, limite)]
        com_memoria = list(dict.fromkeys(
            [local.caminho for r in notas for local in r.locais] + direta
        ))[:limite]
        resultados.append({
            "id": caso.id, "notas": ids, "busca_direta": direta, "memoria_e_busca": com_memoria,
            "nota_esperada_recuperada": bool(set(ids) & set(caso.notas_esperadas))
            if caso.notas_esperadas else None,
            "absteve_de_nota": not ids if not caso.fontes_esperadas else None,
            "absteve_em_busca_direta": not ids if caso.fontes_esperadas
            and not caso.notas_esperadas else None,
            "fonte_direta_recuperada": bool(set(direta) & set(caso.fontes_esperadas))
            if caso.fontes_esperadas else None,
            "fonte_com_memoria_recuperada": bool(set(com_memoria) & set(caso.fontes_esperadas))
            if caso.fontes_esperadas else None,
        })
    medidas = {}
    for chave in ("nota_esperada_recuperada", "absteve_de_nota", "absteve_em_busca_direta",
                  "fonte_direta_recuperada", "fonte_com_memoria_recuperada"):
        validos = [r[chave] for r in resultados if r[chave] is not None]
        medidas[chave] = {"acertos": sum(validos), "casos": len(validos)}
    return {"revisao": catalogo.fontes.revisao, "data": catalogo.data.isoformat(),
            "limite": limite, "catalogo_com_ressalvas": bool(catalogo.problemas),
            "medidas": medidas, "casos": resultados}


def render_contexto(contexto: dict, *, nivel: int = 1) -> str:
    topo = "#" * nivel
    escopo = contexto["escopo"]
    linhas = [f"{topo} Memória do CDP — {escopo}", "", contexto["aviso"], "",
              f"Revisão Git: {contexto['revisao']} · referência: {contexto['data']}.", ""]
    if contexto["catalogo_com_ressalvas"]:
        linhas += ["O catálogo tem ressalvas; notas inválidas foram excluídas.", ""]
    if contexto.get("orientacao_atual"):
        return "\n".join([*linhas, contexto["orientacao_atual"], ""])
    if not contexto["notas"]:
        mensagem = ("Sem notas elegíveis para a consulta." if contexto.get("modo") == "por-consulta"
                    else "Sem notas destacadas e válidas para este escopo nesta data.")
        linhas += [mensagem, ""]
    for nota in contexto["notas"]:
        fontes = "; ".join(f"{e['caminho']}:{e['inicio']}–{e['fim']} (SHA-256 {e['sha256']})"
                           for e in nota["evidencias"])
        linhas += [f"- **{nota['titulo']}** ({nota['id']}): {nota['resumo']}",
                   f"  Evidência: {fontes}."]
    if contexto["fontes"]:
        linhas += ["", "Fontes para consulta: " + ", ".join(contexto["fontes"]) + ".", ""]
    return "\n".join(linhas)


def _relatorio(c: Catalogo) -> dict:
    fila = [{"id": p["id"], "acao": p["codigo"], "detalhe": p["detalhe"]} for p in c.problemas]
    for id_, nota in c.notas.items():
        if nota.estado == "candidata":
            fila.append({"id": id_, "acao": "revisar_candidata",
                         "detalhe": "conferir a alegação nas fontes; aceitar, corrigir ou descartar"})
        if nota.estado == "curada" and c.data >= nota.rever_em:
            fila.append({"id": id_, "acao": "rever_validade",
                         "detalhe": nota.rever_em.isoformat()})
    for i, a in enumerate(c.ativos):
        for b in c.ativos[i + 1:]:
            if not set(a.nota.escopos) & set(b.nota.escopos):
                continue
            ta, tb = _tokens(a.nota.resumo), _tokens(b.nota.resumo)
            if len(ta & tb) >= 5 and len(ta & tb) * 5 >= len(ta | tb) * 4:
                fila.append({"id": a.nota.id, "acao": "comparar_semelhanca", "detalhe": b.nota.id})
    return {"ok": not c.problemas, "base_git": c.fontes.revisao,
            "origem": "árvore de trabalho" if c.fontes.trabalho else "revisão Git",
            "data": c.data.isoformat(), "contagens": c.contagens,
            "problemas": c.problemas, "fila_de_revisao": fila,
            "aviso": "A fila propõe revisões. Nenhuma nota foi gravada, promovida ou descartada."}


def _data(valor: str) -> date:
    try:
        d = date.fromisoformat(valor)
        if d.isoformat() == valor:
            return d
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("use AAAA-MM-DD")


def _intervalo(s: str) -> tuple[int, int]:
    if not re.fullmatch(r"[1-9][0-9]{0,6}:[1-9][0-9]{0,6}", s):
        raise argparse.ArgumentTypeError("use N:M com os números inicial e final, inclusivos")
    return tuple(map(int, s.split(":")))


def _json(obj: object) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _devolutivas_sonho(entrada: BinaryIO, limite_bytes: int) -> Iterable[bytes]:
    for linha in iter(lambda: entrada.readline(limite_bytes + 2), b""):
        bruto = linha.removesuffix(b"\n").removesuffix(b"\r")
        if not bruto or len(bruto) > limite_bytes:
            raise MemoriaErro("informe uma devolutiva JSON por linha dentro do limite de bytes")
        yield bruto


def _comando(args: argparse.Namespace) -> int:
    try:
        acao = args.acao_memoria
        trabalho = acao == "auditar" and not args.revisao_git
        if trabalho and os.name != "posix":
            raise MemoriaErro("auditoria da árvore de trabalho requer POSIX; use --revisao-git")
        revisao = getattr(args, "revisao", None)
        if revisao is not None and acao != "avaliar" and args.data is None:
            raise MemoriaErro("a consulta por revisão exige a data explícita de referência")
        if acao == "avaliar" and revisao is None and not args.sonho:
            revisao = (REVISAO_AVALIACAO_PASSAGENS if args.reservada or args.replica
                       else REVISAO_AVALIACAO_INICIAL)
        fontes = Fontes(raiz_repo(), trabalho=trabalho, revisao=revisao)
        if acao == "propor":
            inicio, fim = args.linhas
            nota = propor(fontes, id_=args.id, escopo=args.escopo, caminho=args.evidencia,
                          inicio=inicio, fim=fim, data=args.data or _hoje(), tipo=args.tipo,
                          titulo=args.titulo, resumo=args.resumo)
            print(nota.model_dump_json(indent=2))
            return 0
        if acao == "avaliar":
            if args.sonho:
                from .memoria_ensaio_sonho import avaliar_sonho

                _json(avaliar_sonho(fontes))
                return 0
            if args.reservada or args.replica:
                from .memoria_avaliacao import avaliar_reservada

                _json(avaliar_reservada(fontes, replica=args.replica))
                return 0
            bruto = fontes.ler(AVALIACAO, 65536)
            json.loads(bruto, object_pairs_hook=_chaves_unicas)
            corpus = _Avaliacao.model_validate_json(bruto)
            if len({c.id for c in corpus.casos}) != len(corpus.casos):
                raise MemoriaErro("casos repetidos na avaliação")
            for caso in corpus.casos:
                if caso.notas_esperadas and not caso.fontes_esperadas:
                    raise MemoriaErro("caso de recuperação de notas exige fonte esperada")
                for caminho in caso.fontes_esperadas:
                    fontes.linhas(caminho)
            c = Catalogo(fontes, corpus.data)
            rel = avaliar(c, corpus.casos)
            _json(rel)
            return int(bool(c.problemas))
        if acao == "rotear":
            from .memoria_roteamento import (
                MAX_BYTES_AMBIGUIDADE,
                MAX_BYTES_ENVELOPE,
                MAX_BYTES_ROTA,
                conferir_ambiguidade,
                conferir_selecao_roteada,
                preparar_ambiguidade,
                preparar_rota,
                preparar_selecao_roteada,
                renderizar_ambiguidade,
                renderizar_rota,
                resolver_rota,
            )

            data = args.data or _hoje()
            pacote = preparar_rota(fontes, data, args.escopo, args.consulta, args.limite,
                                   com_autoridades=args.com_autoridades)
            if not any((args.conferir, args.candidatas, args.conferir_selecao,
                        args.pacote_ambiguidade, args.conferir_ambiguidade)):
                if args.formato == "prompt":
                    print(renderizar_rota(pacote), end="")
                else:
                    _json(pacote)
                return 0
            if args.formato != "json" and not args.pacote_ambiguidade:
                raise MemoriaErro("o formato prompt é exclusivo da preparação da leitura")
            if revisao is None:
                raise MemoriaErro("a conferência exige a revisão e a data do pacote")
            if args.pacote_ambiguidade:
                segunda = preparar_ambiguidade(pacote, sys.stdin.buffer.read(MAX_BYTES_ROTA + 1))
                if args.formato == "prompt":
                    print(renderizar_ambiguidade(segunda), end="")
                else:
                    _json(segunda)
            elif args.conferir_ambiguidade:
                decisao = conferir_ambiguidade(pacote, sys.stdin.buffer.read(MAX_BYTES_AMBIGUIDADE + 1))
                _json(decisao.model_dump())
            elif args.conferir_selecao:
                _json(conferir_selecao_roteada(fontes, pacote, sys.stdin.buffer.read(MAX_BYTES_ENVELOPE + 1)))
            else:
                bruto = sys.stdin.buffer.read(MAX_BYTES_ROTA + 1)
                _json(preparar_selecao_roteada(fontes, pacote, bruto) if args.candidatas
                      else resolver_rota(fontes, pacote, bruto))
            return 0
        c = Catalogo(fontes, args.data or _hoje())
        continuidade = None
        if getattr(args, "continuar", None) is not None:
            from .memoria_sonho import MAX_BYTES_CONTINUIDADE

            if revisao is None or not args.exigir_provas:
                raise MemoriaErro("a continuidade exige revisão, data e provas explícitas")
            linha = sys.stdin.buffer.readline(MAX_BYTES_CONTINUIDADE + 2).rstrip(b"\r\n")
            if not linha or len(linha) > MAX_BYTES_CONTINUIDADE:
                raise MemoriaErro("informe a continuidade em uma linha JSON dentro do limite")
            continuidade = linha
        if acao == "retomar-sonho":
            from .memoria_sonho import MAX_BYTES_RESPOSTA, retomar_sonho

            _json(retomar_sonho(
                c, limite=args.limite, desde=args.desde, exigir_provas=args.exigir_provas,
                devolutivas=_devolutivas_sonho(sys.stdin.buffer, MAX_BYTES_RESPOSTA),
                continuidade=continuidade, lacre_continuidade=args.continuar,
                lacres_devolutivas=args.lacre_pagina,
            ))
        elif acao in ("sonhar", "conferir-sonho", "fonte-sonho"):
            from .memoria_sonho import MAX_BYTES_RESPOSTA, conferir_sonho, ler_fonte_sonho, sonhar

            plano = sonhar(c, limite=args.limite, desde=args.desde, pagina=args.pagina,
                           exigir_provas=args.exigir_provas, continuidade=continuidade,
                           lacre_continuidade=args.continuar)
            if acao == "sonhar":
                _json(plano)
            elif acao == "fonte-sonho":
                _json(ler_fonte_sonho(c, plano, args.uid, caminho=args.fonte,
                                     linhas=args.linhas, nota_id=args.nota))
            else:
                _json(conferir_sonho(c, plano, sys.stdin.buffer.read(MAX_BYTES_RESPOSTA + 1)))
        elif acao == "wiki":
            from .memoria_sonho import wiki

            _json(wiki(c, args.escopo))
        elif acao == "contexto":
            out = c.contexto(args.escopo, consulta=args.consulta)
            if args.formato == "md":
                print(render_contexto(out), end="")
            else:
                _json(out)
        elif acao == "buscar":
            if args.candidatas or args.conferir_selecao:
                from .memoria_selecao import MAX_BYTES_RESPOSTA, aplicar, preparar

                if args.conferir_selecao and revisao is None:
                    raise MemoriaErro("a conferência exige a revisão e a data do pacote")
                pacote = preparar(c, args.escopo, args.consulta, args.limite,
                                  explorar_fontes=args.explorar_fontes)
                if args.candidatas:
                    _json(pacote)
                else:
                    bruto = sys.stdin.buffer.read(MAX_BYTES_RESPOSTA + 1)
                    _json(aplicar(pacote, bruto, ler=c.fontes.linhas))
            else:
                if args.explorar_fontes:
                    raise MemoriaErro("explorar fontes exige gerar ou conferir uma seleção guiada")
                _json(c.buscar(args.escopo, args.consulta, args.limite,
                               estado_atual=args.estado_atual))
        else:
            _json(_relatorio(c))
            return int(bool(c.problemas))
        return 0
    except ValidationError:
        print("Memória indisponível: formato de nota ou corpus inválido.", file=sys.stderr)
    except (ValueError, OSError, RuntimeError) as exc:
        detalhe = str(exc) if isinstance(exc, MemoriaErro) else "entrada ou fonte inválida"
        print(f"Memória indisponível: {detalhe}.", file=sys.stderr)
    return 1


def registrar(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("memoria", help="lições e evidências para continuidade entre sessões")
    acoes = p.add_subparsers(dest="acao_memoria", required=True)
    for acao, ajuda in (
        ("contexto", "mostra um índice breve e as notas destacadas de um escopo"),
        ("buscar", "busca notas curadas e fontes primárias do escopo"),
        ("rotear", "prepara ou confere uma triagem separada da busca histórica"),
        ("propor", "imprime um rascunho de nota com evidência da revisão Git"),
        ("auditar", "verifica a árvore de trabalho e gera uma fila de consolidação"),
        ("avaliar", "executa a comparação offline do corpus da revisão Git"),
        ("sonhar", "gera um plano de revisão de memória na revisão Git"),
        ("retomar-sonho", "confere páginas anteriores e devolve o próximo plano"),
        ("conferir-sonho", "valida na entrada padrão uma devolutiva vinculada ao plano"),
        ("fonte-sonho", "lê uma nota ou trecho Git permitido pelo item do plano"),
        ("wiki", "mostra tópicos e evidências do catálogo curado por escopo"),
    ):
        s = acoes.add_parser(acao, help=ajuda)
        s.set_defaults(func=_comando)
        revisao_obrigatoria = acao in ("fonte-sonho", "retomar-sonho")
        if acao in ("contexto", "buscar", "rotear", "avaliar", "wiki", "sonhar", "conferir-sonho",
                    "fonte-sonho", "retomar-sonho"):
            s.add_argument("--revisao", required=revisao_obrigatoria,
                           help="hash completo do commit local a consultar")
        if acao == "avaliar":
            conjunto = s.add_mutually_exclusive_group()
            conjunto.add_argument("--reservada", action="store_true",
                                   help="mede recuperação de passagens no primeiro corpus reservado")
            conjunto.add_argument("--replica", action="store_true",
                                   help="mede recuperação de passagens no corpus de verificação")
            conjunto.add_argument("--sonho", action="store_true",
                                   help="executa o ensaio de revisão em Git temporário")
        else:
            s.add_argument("--data", type=_data, required=revisao_obrigatoria,
                           help="data de referência (padrão: Brasília)")
        if acao in ("contexto", "buscar", "rotear", "propor", "wiki"):
            s.add_argument("--escopo", choices=tuple(ESCOPO), required=True)
        if acao in ("sonhar", "conferir-sonho", "fonte-sonho", "retomar-sonho"):
            s.add_argument("--exigir-provas", action="store_true",
                           help="vincula a revisão de cada item a evidência ou diagnóstico conferido")
            s.add_argument("--desde", help="hash completo da última revisão examinada")
            s.add_argument("--continuar", metavar="SHA256",
                           help="lacre da continuidade de investigações enviada na primeira linha")
            s.add_argument("--limite", type=int, choices=range(1, 13), default=12,
                           help="quantidade máxima de itens do plano")
        if acao in ("sonhar", "conferir-sonho", "fonte-sonho"):
            s.add_argument("--pagina", type=int, default=1,
                           help="página da fila na revisão fixada")
        if acao == "retomar-sonho":
            s.add_argument("--lacre-pagina", action="append", metavar="SHA256",
                           help="hash esperado dos bytes de uma devolutiva, na ordem das páginas")
        if acao == "fonte-sonho":
            s.add_argument("--uid", required=True, help="identificador do item do plano")
            origem = s.add_mutually_exclusive_group(required=True)
            origem.add_argument("--fonte", help="caminho da fonte do item")
            origem.add_argument("--nota", help="ID de uma nota do item")
            s.add_argument("--linhas", type=_intervalo, help="intervalo inclusivo da fonte")
        if acao == "auditar":
            s.add_argument("--revisao-git", action="store_true",
                           help="audita o HEAD em vez da árvore de trabalho")
        if acao == "contexto":
            s.add_argument("--formato", choices=("md", "json"), default="md")
            s.add_argument("--consulta", type=_consulta, help="seleciona contexto para a tarefa em mãos")
        if acao in ("buscar", "rotear"):
            s.add_argument("--consulta", required=True, type=_consulta)
            s.add_argument("--limite", type=int, choices=range(1, 11), default=5)
        if acao == "rotear":
            modo = s.add_mutually_exclusive_group()
            modo.add_argument("--conferir", action="store_true",
                              help="confere a devolutiva lacrada recebida na entrada padrão")
            modo.add_argument("--candidatas", action="store_true",
                              help="prepara candidatas após conferir a triagem de evidência")
            modo.add_argument("--conferir-selecao", action="store_true",
                              help="confere o envelope com triagem e seleção lacradas")
            modo.add_argument("--pacote-ambiguidade", action="store_true",
                              help="prepara a segunda leitura a partir da triagem na entrada padrão")
            modo.add_argument("--conferir-ambiguidade", action="store_true",
                              help="confere a segunda leitura e devolve a triagem resultante")
            s.add_argument("--com-autoridades", action="store_true",
                           help="inclui os cartões de autoridade com âncoras Git validadas")
            s.add_argument("--formato", choices=("json", "prompt"), default="json",
                           help="na preparação, emite dados ou instruções prontas para um leitor")
        if acao == "buscar":
            modo = s.add_mutually_exclusive_group()
            modo.add_argument("--estado-atual", action="store_true",
                              help="encaminha à fonte do estado sem recuperar memória")
            modo.add_argument("--candidatas", action="store_true",
                              help="gera um pacote lacrado para seleção de evidências pelo agente")
            modo.add_argument("--conferir-selecao", action="store_true",
                              help="confere os IDs recebidos na entrada padrão contra o pacote lacrado")
            s.add_argument("--explorar-fontes", action="store_true",
                           help="permite revisar a intenção e selecionar recortes de fontes do escopo")
        if acao == "propor":
            s.add_argument("--id", required=True)
            s.add_argument("--evidencia", required=True, help="caminho relativo da fonte")
            s.add_argument("--linhas", type=_intervalo, required=True, help="intervalo inclusivo N:M")
            s.add_argument("--tipo", choices=("procedimento", "licao", "episodio"), default="licao")
            s.add_argument("--titulo", default="Preencher após conferir a evidência")
            s.add_argument("--resumo", default="Descrever a lição e seus limites para revisão.")


def _consulta(valor: str) -> str:
    if 1 <= len(valor) <= 240 and not any(unicodedata.category(c).startswith("C") for c in valor):
        return valor
    raise argparse.ArgumentTypeError("use texto em uma linha de até 240 caracteres")
