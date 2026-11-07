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
from pathlib import Path
from typing import Annotated, Literal
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
    r"\b(?:agora|hoje|ontem|atual(?:mente|is)?|ultim[oa]s?|mais recente|proxim[oa]s?|"
    r"neste (?:momento|instante|minuto)|no momento(?! (?:d[aeo]s?|em que)\b)|"
    r"(?:dest[ea]|nest[ea]) (?:manha|tarde|noite|semana|mes)|"
    r"em vigor|vigentes?)\b"
    r"|\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
    r"\d{1,2} de (?:janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro))\b"
)
_OCORRENCIA = re.compile(
    r"\b(?:ja|ainda) (?:rodou|executou|fechou|entregou|publicou|consta|subiu|saiu|"
    r"chegou|encerrou|concluiu|terminou|foi publicado|foi enviado)\b"
    r"|\b(?:acab(?:ei|amos|ou|aram) de|consta(?:m)?|gravou|publicou|"
    r"selad[oa]s?|anotad[oa]s?|observad[oa]s?|registrad[oa]s?|designad[oa]s?|"
    r"abert[oa]s?|ativ[oa]s?|ficou|ficaram|marcou|primeir[oa]s?)\b"
    r"|\bmedid[oa]s? (?:em|n[oa]s?|pel[oa]s?|durante)\b"
    r"|\b(?:ja|ainda) (?:esta|estao) \w+(?:ando|endo|indo)\b"
    r"|\b(?:foi|foram|esta|estao) (?:\w+ ){0,3}\w+(?:ad|id)[oa]s?\b"
    r"|\bja (?:teve|tiveram) (?:\w+ ){0,7}\w+(?:ad|id)[oa]s?\b"
    r"|\bja (?:voltou|voltaram)\b"
)
_QUANTIFICA_TEMPO = re.compile(r"\b(?:quanto(?: tempo)?|quant[oa]s (?:segundos?|minutos?|horas?|dias?))\b")
_TEMPO_PENDENTE = re.compile(r"\b(?:faltam?|restam?)\b")
_OBRIGACAO_PENDENTE = re.compile(r"\bainda (?:precis(?:a|am)|deve(?:m)?|tem (?:de|que))\b")
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
_ARTEFATO_COBERTURA = re.compile(r"\b(?:modelos?|retratos?)\b")
_SAIDA_COBERTURA = re.compile(r"\b(?:balancos?|resultados?|ratings?|precos?[- ]alvo)\b")
_ENTREGA_DOCUMENTAL = re.compile(
    r"\b(?:e-?mails?|entregas? d[oa]s? (?:relatorios?|pdfs?|comentarios?|notas?|resumos?))\b"
)


def _pedido_fora_do_escopo(q: str) -> bool:
    """Filtra pedidos de execução ou acesso que a memória consultiva não atende."""
    nega_vinculo = _SEM_VINCULO_CDP.search(q)
    if nega_vinculo and not _REFERENCIA_EXPLICITA_CDP.search(_SEM_VINCULO_CDP.sub(" ", q)):
        return True
    return bool((_BURLA.search(q) and _CONTROLES.search(q)) or _EXTRACAO_SEGREDO.search(q)
                or (_NEGOCIACAO_REAL.search(q) and _PEDIDO_NEGOCIACAO.search(q))
                or (_RECURSO_PRIVADO.search(q) and (nega_vinculo or _ORGANIZACAO_EXTERNA.search(q))
                    and _ACESSO_A_RECURSO.search(q))
                or (_CONTEXTO_ALHEIO.search(q) and not _VINCULO_CDP.search(q)))


def _tema_do_cdp(q: str) -> bool:
    return bool(_DOMINIO.search(q) or _MERCADO.search(q) or _TEMA_CDP.search(q)
                or len(set(_VOCABULARIO_TRABALHO.findall(q))) >= 2)


def _sobre_retrato_de_cobertura(q: str) -> bool:
    return bool(_ARTEFATO_COBERTURA.search(q) and _SAIDA_COBERTURA.search(q))


def _termos_de_observacao(q: str) -> set[str]:
    temas = _DOMINIO.findall(q) + _MERCADO.findall(q)
    if _sobre_retrato_de_cobertura(q):
        temas.extend(_ARTEFATO_COBERTURA.findall(q) + _SAIDA_COBERTURA.findall(q))
    return set(termos_contextuais(" ".join(temas)))


def _pede_estado(q: str) -> bool:
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
        if not (_MERCADO.search(assunto) or _DOMINIO.search(assunto) or _VINCULO_CDP.search(assunto)
                or _sobre_retrato_de_cobertura(assunto)):
            continue
        pedido = _PEDIDO_OBSERVACAO.search(frase) or frase.endswith("?")
        enunciado = _SUBORDINADA.split(frase, maxsplit=1)[0]
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
                       or _OBRIGACAO_PENDENTE.search(enunciado) or tempo_restante):
            return True
    return False


def _fonte_atual(consulta: str, *, forcar: bool = False) -> str | None:
    """Reconhece pedidos de observação e distingue instruções de procedimento."""
    q = _normalizar(consulta).strip()
    if not forcar and not _pede_estado(q):
        return None
    if re.search(r"\b(?:frentes? de desenvolvimento|passagem de bastao|em_andamento)\b", q):
        return "Consulte a passagem corrente em docs/cdp/EM_ANDAMENTO.md na revisão atual."
    if re.search(r"\b(?:portal|pages|implantacao|deploy)\b", q):
        return "Confira o portal servido e a procedência em docs/cdp/SITE.md."
    if _ENTREGA_DOCUMENTAL.search(q) or (_VINCULO_CDP.search(q) and re.search(r"\bentregas?\b", q)):
        return "Confira a trilha de entrega descrita em docs/cdp/playbooks/DIARIO.md."
    if re.search(r"\bcommits?\b", q):
        return ("Consulte a procedência do commit gravado. O trailer CDP-Harness identifica "
                "o aplicativo e CDP-Executor identifica o executor.")
    if re.search(r"\bexecutor\b", q) and re.search(r"\b(?:remoto|origin/main)\b", q):
        return "Consulte configs/cdp/executor.yaml na revisão remota e a identidade local em cdp estado."
    if re.search(r"\b(?:manifesto|hash|sha[- ]?256)\b", q):
        if re.search(r"\b(?:ensaio|replay)\b", q):
            return "Consulte o manifesto e a verificação da execução solicitada do ensaio isolado."
        if re.search(r"\b(?:snapshot|captura)\b", q):
            return "Consulte o manifesto e a verificação do snapshot ou da captura solicitada."
    if re.search(r"\btrava\b", q) and _QUANTIFICA_TEMPO.search(q) and _TEMPO_PENDENTE.search(q):
        return "Consulte cdp trava ver para conferir a ocupação e a expiração da trava distribuída."
    if _OBRIGACAO_PENDENTE.search(q) and re.search(r"\b(?:preg(?:ao|oes)|fechamentos?)\b", q):
        return "Consulte fechamentos_pendentes em cdp agenda no clone de operação."
    if _sobre_retrato_de_cobertura(q):
        return "Consulte o retrato da cobertura da data solicitada e os campos de cobertura em cdp agenda."
    if re.search(r"\b(?:cobertura|emissor(?:es)?)\b", q) and re.search(
        r"\b(?:fila|notas?|retrato|emissor(?:es)?)\b", q
    ):
        return "Consulte a fila da nota na saída corrente de nota agenda no clone de operação."
    if re.search(r"\b(?:calibracao|sharpe|rodada mensal)\b", q):
        return "Consulte o metrics.json ou o relatório da calibração correspondente à rodada."
    if re.search(r"\b(?:propostas?|previa)\b", q):
        return ("Consulte a proposta da montagem efetivamente gravada. "
                "Se não houver proposta para essa etapa, registre a ausência.")
    if re.search(r"\b(?:montagem|rebalanceamento)\b", q) and re.search(
        r"\b(?:agenda|prazos?|mercados?)\b", q
    ):
        return "Consulte semanal.prazo_efetivo e semanal.mercados_fechados na saída de cdp agenda."
    if re.search(r"\b(?:alertas?|monitor|hard|soft)\b", q) and not re.search(
        r"\bkill[- ]switch\b", q
    ):
        return "Consulte o relatório do monitor de risco da rodada solicitada."
    if re.search(r"\b(?:longs?|shorts?|posic(?:ao|oes))\b", q) and re.search(
        r"\b(?:carteira|livro)\b", q
    ):
        return "Consulte a carteira efetivada no livro ou o relatório correspondente ao corte."
    if _MERCADO.search(q) or re.search(r"\bquanto (?:marcou|rendeu|valeu|fechou)\b", q):
        return "Consulte o relatório oficial da data ou os fatos correspondentes no FactBook."
    return "Consulte o estado e a agenda no clone de operação."


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

    def contexto(self, escopo: Escopo) -> dict:
        destacados = sorted((r for r in self.ativos if escopo in r.nota.escopos and r.nota.destaque),
                             key=lambda r: (len(r.nota.escopos), r.nota.id))
        out = {"revisao": self.fontes.revisao, "data": self.data.isoformat(), "escopo": escopo,
               "aviso": _AVISO, "catalogo_com_ressalvas": bool(self.problemas),
               "fontes": list(_primarias(escopo)[:3]), "notas": []}
        for reg in destacados[:LIMITE_CONTEXTO]:
            out["notas"].append(reg.json())
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
        estruturais = self.indice.estruturais(escopo, consulta)
        ampliadas = ampliar_selecao(selecionadas, estruturais, self.fontes.linhas)
        return reaproveitar_vagas(ampliadas, estruturais, self.fontes.linhas)

    def _tem_apoio_no_acervo(self, escopo: Escopo, q: str, diretas: list[Local], notas: list[Registro], *,
                            observacao: bool) -> bool:
        termos = {t for t in termos_contextuais(q) if not t.startswith("@") and not t.isdigit()}
        termos -= _TERMOS_INCIDENTAIS
        base = min(3, len(termos)) if _tema_do_cdp(q) else 4
        minimo = 2 if observacao else max(2, len(termos) // 5, base)
        topicos = _termos_de_observacao(q) if observacao else set()

        def termos_em(texto: str) -> set[str]:
            return termos & termos_contextuais(texto).keys()

        def apoia(p: Local) -> bool:
            comuns = termos_em("\n".join(self.fontes.linhas(p.caminho)[p.inicio - 1:p.fim]))
            return len(comuns) >= minimo and (not observacao or bool(comuns & topicos))

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

    def buscar(self, escopo: Escopo, consulta: str, limite: int, *,
               estado_atual: bool = False) -> dict:
        q = _normalizar(consulta).strip()
        fora = _pedido_fora_do_escopo(q)
        atual = None if fora else _fonte_atual(consulta, forcar=estado_atual)
        diretas = [] if fora or estado_atual else self.indice.buscar(escopo, consulta, limite)
        notas = [] if fora or atual else self._buscar_notas(escopo, consulta, limite, expandir=True)
        vinculo = _VINCULO_CDP.search(q) or (atual and _MEDICAO_DE_ATIVO.search(q))
        if not (fora or estado_atual or vinculo):
            fora = not self._tem_apoio_no_acervo(escopo, q, diretas, notas, observacao=bool(atual))
            if fora:
                diretas = []
                notas = []
                atual = None
        if atual and not estado_atual:
            atual = "Se a pergunta for sobre o estado efetivo, consulte a fonte oficial. " + atual
        passagens = [] if fora or estado_atual else self._recuperar_passagens(
            escopo, consulta, limite, diretas, notas
        )
        caminhos = {}
        for local in diretas:
            caminhos.setdefault(local.caminho, local.json())
        return {"revisao": self.fontes.revisao, "data": self.data.isoformat(), "escopo": escopo,
                "aviso": _AVISO, "catalogo_com_ressalvas": bool(self.problemas),
                "notas": [r.json() for r in notas], "fontes": list(caminhos.values()),
                "passagens": [local.json() for local in passagens], "orientacao_atual": atual}

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

    def buscar(self, escopo: Escopo, consulta: str, limite: int, *,
               contextual: bool = False) -> list[Local]:
        return self.para_escopo(escopo, contextual=contextual).buscar(consulta, limite)

    def para_escopo(self, escopo: Escopo, *, contextual: bool) -> IndicePassagens:
        chave = (escopo, contextual)
        if chave not in self.indices:
            self.indices[chave] = IndicePassagens(self._documentos(escopo), contextual=contextual)
        return self.indices[chave]

    def estruturais(self, escopo: Escopo, consulta: str) -> list[Local]:
        if escopo not in self._indices_secoes:
            self._indices_secoes[escopo] = IndiceSecoes(self._documentos(escopo))
        return self._indices_secoes[escopo].buscar(consulta)

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
    if not contexto["notas"]:
        linhas += ["Sem notas destacadas e válidas para este escopo nesta data.", ""]
    for nota in contexto["notas"]:
        fontes = "; ".join(f"{e['caminho']}:{e['inicio']}–{e['fim']} (SHA-256 {e['sha256']})"
                           for e in nota["evidencias"])
        linhas += [f"- **{nota['titulo']}** ({nota['id']}): {nota['resumo']}",
                   f"  Evidência: {fontes}."]
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
        c = Catalogo(fontes, args.data or _hoje())
        if acao in ("sonhar", "conferir-sonho", "fonte-sonho"):
            from .memoria_sonho import MAX_BYTES_RESPOSTA, conferir_sonho, ler_fonte_sonho, sonhar

            plano = sonhar(c, limite=args.limite, desde=args.desde, pagina=args.pagina)
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
            out = c.contexto(args.escopo)
            if args.formato == "md":
                print(render_contexto(out), end="")
            else:
                _json(out)
        elif acao == "buscar":
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
        ("propor", "imprime um rascunho de nota com evidência da revisão Git"),
        ("auditar", "verifica a árvore de trabalho e gera uma fila de consolidação"),
        ("avaliar", "executa a comparação offline do corpus da revisão Git"),
        ("sonhar", "gera um plano de revisão de memória na revisão Git"),
        ("conferir-sonho", "valida na entrada padrão uma devolutiva vinculada ao plano"),
        ("fonte-sonho", "lê uma nota ou trecho Git permitido pelo item do plano"),
        ("wiki", "mostra tópicos e evidências do catálogo curado por escopo"),
    ):
        s = acoes.add_parser(acao, help=ajuda)
        s.set_defaults(func=_comando)
        if acao in ("contexto", "buscar", "avaliar", "wiki", "sonhar", "conferir-sonho",
                    "fonte-sonho"):
            s.add_argument("--revisao", required=acao == "fonte-sonho",
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
            s.add_argument("--data", type=_data, required=acao == "fonte-sonho",
                           help="data de referência (padrão: Brasília)")
        if acao in ("contexto", "buscar", "propor", "wiki"):
            s.add_argument("--escopo", choices=tuple(ESCOPO), required=True)
        if acao in ("sonhar", "conferir-sonho", "fonte-sonho"):
            s.add_argument("--desde", help="hash completo da última revisão examinada")
            s.add_argument("--limite", type=int, choices=range(1, 13), default=12,
                           help="quantidade máxima de itens do plano")
            s.add_argument("--pagina", type=int, default=1,
                           help="página da fila na revisão fixada")
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
        if acao == "buscar":
            s.add_argument("--consulta", required=True, type=_consulta)
            s.add_argument("--limite", type=int, choices=range(1, 11), default=5)
            s.add_argument("--estado-atual", action="store_true",
                           help="encaminha à fonte do estado sem recuperar memória")
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
