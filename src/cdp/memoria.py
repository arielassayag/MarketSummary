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
    ampliar,
    intercalar,
)
from .memoria_busca import (
    normalizar as _normalizar,
)

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
    r"cotac(?:ao|oes)|perdas?|ganhos?|drawdown|volatilidade|moedas?|pesos?|liquidez)\b"
)
_DOMINIO = re.compile(
    r"\b(?:kill[- ]switch|executor|rotinas?|agenda|carteira|posic(?:ao|oes)|exposicao|"
    r"montagem|pendencias?|fechamento|trava|cobertura|risco|relatorios?|calibracao|"
    r"publicacao|portal|pages|revisao|disparo|rodada|livro|emails?|entrega|snapshot)\b"
)
_AGORA = re.compile(r"\b(?:agora|hoje|ontem|neste momento|no momento|atualmente)\b")
_TEMPO = re.compile(
    r"\b(?:atual|ultim[oa]s?|mais recente)\b"
    r"|\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b"
)
_OCORRENCIA = re.compile(
    r"\b(?:ja|ainda) (?:rodou|executou|fechou|entregou|publicou|consta|"
    r"subiu|saiu|chegou|encerrou|concluiu|foi publicado|foi enviado)\b"
)
_INTERROGATIVA = re.compile(r"^(?:quem|qual|quais|quanto|quant[ao]s|onde|quando|como esta)\b")
_PROCEDIMENTO = re.compile(
    r"^(?:como (?!esta\b|estao\b|ficou\b|anda\b|se encontra\b)|"
    r"em (?:que situacao|que caso|qual situacao|qual caso)|"
    r"se\b|quando (?:um|uma|a fonte|os dados|a regra)\b|no dia (?:de|da|do)\b|"
    r"o que (?:fazer|faco|acontece quando)|qual (?:e )?[ao]s? "
    r"(?:procedimento|roteiro|comando|regra|diferenca|criterio|ordem|fluxo)\b)"
)
_VALOR = re.compile(
    r"^(?:quanto|quant[oa]s)\b|^qual(?: e| foi)? [oa] (?:ultim[oa] )?"
    r"(?:valor|pnl|p&l|pl|retorno|preco|cotacao|patrimonio|rentabilidade|drawdown|peso)\b"
)
_PEDIDO_DE_PROCEDIMENTO = re.compile(
    r"\b(?:como (?:eu )?(?:confiro|confirmo|verifico|faco|validar|usar|confirmar|proceder)|"
    r"posso|devo|permite|autoriza|atesta|serve para|replay|point-in-time|pit)\b"
)


def _fonte_atual(consulta: str, *, forcar: bool = False) -> str | None:
    """Reconhece pedidos de observação e distingue instruções de procedimento."""
    q = _normalizar(consulta).strip()
    mercado, dominio = bool(_MERCADO.search(q)), bool(_DOMINIO.search(q))
    if not forcar:
        if (not (mercado or dominio) or _PROCEDIMENTO.search(q)
                or _PEDIDO_DE_PROCEDIMENTO.search(q)):
            return None
        pergunta = bool(_INTERROGATIVA.match(q) or q.endswith("?"))
        medida_com_data = mercado and _VALOR.match(q) and _TEMPO.search(q)
        pessoa_ou_versao_atual = _INTERROGATIVA.match(q) and re.search(
            r"\b(?:executor|portal|pages)\b.*\batual\b", q)
        ocorrencia = _OCORRENCIA.search(q)
        if not (pergunta and (_AGORA.search(q) or medida_com_data
                              or pessoa_ou_versao_atual or ocorrencia)):
            return None
    if re.search(r"\b(?:portal|pages)\b", q):
        return "Confira o portal servido e a procedência em docs/cdp/SITE.md."
    if re.search(r"\b(?:e-?mails?|entrega)\b", q):
        return "Confira a trilha de entrega descrita em docs/cdp/playbooks/DIARIO.md."
    if mercado:
        return "Consulte o relatório oficial da data e os fatos calculados pelo código."
    if re.search(r"\b(?:cobertura|emissor(?:es)?)\b", q) and re.search(
        r"\b(?:fila|notas?|emissor(?:es)?)\b", q
    ):
        return "Consulte a agenda de cobertura e a fila da nota no clone de operação."
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
        termos = _tokens(consulta)
        notas = []
        if termos:
            for reg in self.ativos:
                n = reg.nota
                if escopo not in n.escopos:
                    continue
                chave = _tokens(n.titulo + " " + " ".join(n.tags))
                resumo = _tokens(n.resumo)
                ancora = set()
                if expandir:
                    ancora = _tokens(" ".join(ev.trecho for ev in n.evidencias))
                comuns = termos & (chave | resumo | ancora)
                # Sobreposição mínima evita forçar uma lembrança com coincidência incidental.
                if (len(comuns) >= min(2, len(termos)) and termos & chave
                        and len(comuns) * 3 >= len(termos)):
                    pontos = 6 * len(termos & chave) + 2 * len(termos & resumo) + len(termos & ancora)
                    notas.append((-pontos, -len(comuns), n.id, reg))
        notas.sort(key=lambda v: v[:3])
        return [r for *_, r in notas[:limite]]

    def buscar(self, escopo: Escopo, consulta: str, limite: int, *,
               estado_atual: bool = False) -> dict:
        atual = _fonte_atual(consulta, forcar=estado_atual)
        notas = [] if atual else self._buscar_notas(escopo, consulta, limite, expandir=True)
        diretas = [] if estado_atual else self.indice.buscar(escopo, consulta, limite)
        if atual and not estado_atual:
            atual = "Se a pergunta for sobre o estado efetivo, consulte a fonte oficial. " + atual
        termos = _tokens(consulta)
        ancoras = []
        for registro in notas:
            elegiveis = [(local, evidencia) for local, evidencia in
                         zip(registro.locais, registro.nota.evidencias, strict=True)
                         if local.fim - local.inicio + 1 <= LINHAS_PASSAGEM
                         and len(evidencia.trecho.encode()) <= BYTES_PASSAGEM]
            ordenadas = sorted(elegiveis, key=lambda par: -len(termos & _tokens(par[1].trecho)))
            ancoras.append([ampliar(local, self.fontes.linhas(local.caminho))
                            for local, _ in ordenadas])
        passagens = intercalar(diretas, ancoras, limite)
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
        self.indices: dict[Escopo, IndicePassagens] = {}

    def buscar(self, escopo: Escopo, consulta: str, limite: int) -> list[Local]:
        if escopo not in self.indices:
            fontes = []
            for caminho in self.caminhos[escopo]:
                try:
                    fontes.append((caminho, self.fontes.linhas(caminho)))
                except MemoriaErro:
                    continue
            self.indices[escopo] = IndicePassagens(fontes)
        return self.indices[escopo].buscar(consulta, limite)


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
        if acao == "avaliar" and not (args.reservada or args.replica) and revisao is None:
            revisao = REVISAO_AVALIACAO_INICIAL
        fontes = Fontes(raiz_repo(), trabalho=trabalho, revisao=revisao)
        if acao == "propor":
            inicio, fim = args.linhas
            nota = propor(fontes, id_=args.id, escopo=args.escopo, caminho=args.evidencia,
                          inicio=inicio, fim=fim, data=args.data or _hoje(), tipo=args.tipo,
                          titulo=args.titulo, resumo=args.resumo)
            print(nota.model_dump_json(indent=2))
            return 0
        if acao == "avaliar":
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
        if acao == "contexto":
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
    ):
        s = acoes.add_parser(acao, help=ajuda)
        s.set_defaults(func=_comando)
        if acao in ("contexto", "buscar", "avaliar"):
            s.add_argument("--revisao", help="hash completo do commit local a consultar")
        if acao == "avaliar":
            conjunto = s.add_mutually_exclusive_group()
            conjunto.add_argument("--reservada", action="store_true",
                                   help="mede recuperação de passagens no primeiro corpus reservado")
            conjunto.add_argument("--replica", action="store_true",
                                   help="mede recuperação de passagens no corpus de verificação")
        else:
            s.add_argument("--data", type=_data, help="data de referência (padrão: Brasília)")
        if acao in ("contexto", "buscar", "propor"):
            s.add_argument("--escopo", choices=tuple(ESCOPO), required=True)
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
