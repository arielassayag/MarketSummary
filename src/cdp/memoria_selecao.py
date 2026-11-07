"""Prepara candidatas versionadas e confere uma seleção de referências."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from itertools import chain, zip_longest
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from .memoria import (
    ESCOPO,
    Catalogo,
    Escopo,
    MemoriaErro,
    Sha,
    _caminho,
    _chaves_unicas,
    _consulta,
    _Modelo,
    _sha,
)
from .memoria_busca import BYTES_PASSAGEM, LINHAS_PASSAGEM, Local, completar_bloco

MAX_BYTES_RESPOSTA = 4096
LIMITE_CANDIDATAS = 64
_LIMITE_PASSAGENS = 5
_LIMITE_BYTES = 4500
_LARGURA_CANONICA = 20


class _Candidata(_Modelo):
    id: int = Field(ge=1, le=LIMITE_CANDIDATAS)
    caminho: str
    inicio: int = Field(ge=1)
    fim: int = Field(ge=1)
    sha256: Sha
    bytes: int = Field(ge=1, le=BYTES_PASSAGEM)
    trecho: str = Field(min_length=1, max_length=BYTES_PASSAGEM)

    @field_validator("caminho")
    @classmethod
    def caminho_valido(cls, valor: str) -> str:
        return _caminho(valor)

    @model_validator(mode="after")
    def conferir(self) -> _Candidata:
        linhas = self.trecho.count("\n") + 1
        if (linhas != self.fim - self.inicio + 1 or linhas > LINHAS_PASSAGEM
                or len(self.trecho.encode()) != self.bytes
                or not self.trecho.strip() or _sha(self.trecho) != self.sha256):
            raise ValueError("trecho não corresponde à referência")
        return self

    def referencia(self) -> dict:
        return Local(self.caminho, self.inicio, self.fim, self.sha256).json()


class _Pacote(_Modelo):
    versao: Literal[1]
    revisao: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    consulta: str = Field(min_length=1, max_length=240)
    escopo: Escopo
    limite: int = Field(ge=1, le=_LIMITE_PASSAGENS)
    orcamento_bytes: int = Field(ge=_LIMITE_BYTES, le=_LIMITE_BYTES)
    candidatas: list[_Candidata] = Field(max_length=LIMITE_CANDIDATAS)
    base: dict
    lacre: Sha

    @model_validator(mode="after")
    def conferir(self) -> _Pacote:
        if [p.id for p in self.candidatas] != list(range(1, len(self.candidatas) + 1)):
            raise ValueError("candidatas sem numeração consecutiva")
        if any(self.base.get(k) != getattr(self, k) for k in ("revisao", "data", "escopo")):
            raise ValueError("a busca base diverge do pacote")
        if self.candidatas and not _tem_contexto(self.base):
            raise ValueError("busca sem contexto não pode oferecer candidatas")
        return self


class _Resposta(_Modelo):
    lacre: Sha
    ids: list[int] = Field(max_length=_LIMITE_PASSAGENS)


def _lacre(pacote: dict) -> str:
    corpo = {chave: valor for chave, valor in pacote.items() if chave != "lacre"}
    return _sha(json.dumps(corpo, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False))


def _tem_contexto(busca: dict) -> bool:
    return not busca.get("orientacao_atual") and any(
        busca.get(campo) for campo in ("passagens", "fontes", "notas")
    )


def _intercalar(*vias: list[Local]) -> Iterator[Local]:
    return (p for fila in zip_longest(*vias) for p in fila if p is not None)


def _candidatas(catalogo: Catalogo, escopo: Escopo, consulta: str, busca: dict) -> list[dict]:
    ler = catalogo.fontes.linhas
    base = [Local(**p) for p in busca["passagens"]]
    notas = [Local(**ev) for nota in busca["notas"] for ev in nota["evidencias"]]
    diretas = catalogo.indice.buscar(escopo, consulta, _LARGURA_CANONICA)
    contextuais = catalogo.indice.buscar(escopo, consulta, _LARGURA_CANONICA, contextual=True)
    estruturais = catalogo.indice.estruturais(escopo, consulta)
    completas = catalogo.indice.estruturais(escopo, consulta, completas=True)
    simbolos = catalogo.indice.simbolos(escopo, consulta)
    # A primeira rodada inclui todas as vias. O restante de D20 e C20 tem
    # precedência sobre as caudas para que vias complementares não o cortem.
    alternadas = chain(
        _intercalar(notas[:4], diretas[:5], contextuais[:5], estruturais[:5],
                   completas[:5], simbolos[:5]),
        _intercalar(diretas[5:], contextuais[5:]),
        _intercalar(notas[4:], estruturais[5:], completas[5:], simbolos[5:]),
    )
    vistos: set[Local] = set()
    candidatas: list[dict] = []
    for local, expandir in chain(((p, False) for p in base), ((p, True) for p in alternadas)):
        if not 0 < local.fim - local.inicio + 1 <= LINHAS_PASSAGEM:
            continue
        linhas = ler(local.caminho)
        trecho = "\n".join(linhas[local.inicio - 1:local.fim])
        if len(trecho.encode()) > BYTES_PASSAGEM or not trecho.strip():
            continue
        if not 1 <= local.inicio <= local.fim <= len(linhas) or _sha(trecho) != local.sha256:
            raise MemoriaErro("referência diverge da fonte canônica")
        if expandir:
            local = completar_bloco(local, linhas)
        if local in vistos:
            continue
        vistos.add(local)
        trecho = "\n".join(linhas[local.inicio - 1:local.fim])
        candidatas.append({"id": len(candidatas) + 1, **local.json(),
                           "bytes": len(trecho.encode()), "trecho": trecho})
        if len(candidatas) == LIMITE_CANDIDATAS:
            break
    return candidatas


def preparar(catalogo: Catalogo, escopo: Escopo, consulta: str, limite: int) -> dict:
    """Lê uma revisão Git e lacra o conjunto ordenado de candidatas e a busca base."""
    if catalogo.fontes.trabalho:
        raise MemoriaErro("a seleção exige fontes de uma revisão Git")
    if escopo not in ESCOPO or type(limite) is not int or not 1 <= limite <= _LIMITE_PASSAGENS:
        raise MemoriaErro("a seleção exige escopo válido e limite entre um e cinco")
    if not isinstance(consulta, str):
        raise MemoriaErro("consulta exige texto")
    try:
        consulta = _consulta(consulta)
    except argparse.ArgumentTypeError as exc:
        raise MemoriaErro(str(exc)) from exc
    busca = catalogo.buscar(escopo, consulta, limite)
    candidatas = _candidatas(catalogo, escopo, consulta, busca) if _tem_contexto(busca) else []
    pacote = {"versao": 1, "revisao": catalogo.fontes.revisao, "data": catalogo.data.isoformat(),
              "consulta": consulta, "escopo": escopo, "limite": limite,
              "orcamento_bytes": _LIMITE_BYTES, "candidatas": candidatas, "base": busca}
    pacote["lacre"] = _lacre(pacote)
    return pacote


def aplicar(pacote: dict, bruto: bytes) -> dict:
    """Valida a devolutiva e resolve apenas IDs do pacote preparado pelo chamador."""
    if not isinstance(bruto, bytes):
        raise MemoriaErro("a resposta exige JSON em bytes")
    if len(bruto) > MAX_BYTES_RESPOSTA:
        raise MemoriaErro("a resposta excede o limite de bytes")
    try:
        objeto = json.loads(bruto.decode(), object_pairs_hook=_chaves_unicas)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MemoriaErro("JSON inválido na resposta") from exc
    try:
        selada = _Pacote.model_validate(pacote)
        resposta = _Resposta.model_validate(objeto)
    except ValidationError as exc:
        raise MemoriaErro("esquema inválido de pacote ou resposta") from exc
    try:
        lacre = _lacre(pacote)
    except (TypeError, ValueError, RecursionError) as exc:
        raise MemoriaErro("JSON inválido no pacote") from exc
    if resposta.lacre != selada.lacre or selada.lacre != lacre:
        raise MemoriaErro("o lacre da seleção diverge do pacote")
    ids = resposta.ids
    if len(ids) > selada.limite or len(ids) != len(set(ids)):
        raise MemoriaErro("a seleção excede o limite ou repete IDs")
    candidatas = {p.id: p for p in selada.candidatas}
    if any(i not in candidatas for i in ids):
        raise MemoriaErro("a seleção usa ID desconhecido")
    escolhidas = [candidatas[i] for i in ids]
    total = sum(p.bytes for p in escolhidas) + max(0, len(escolhidas) - 1)
    if total > selada.orcamento_bytes:
        raise MemoriaErro("a seleção excede o orçamento de 4.500 bytes")
    return {**selada.base, "passagens": [p.referencia() for p in escolhidas]}
