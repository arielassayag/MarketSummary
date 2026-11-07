"""Trechos canônicos curados para consulta documental entre papéis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, field_validator, model_validator

from .memoria import (
    ESCOPO,
    Catalogo,
    Escopo,
    Evidencia,
    MemoriaErro,
    MemoriaGitIndisponivel,
    Slug,
    _chaves_unicas,
    _localizar,
    _Modelo,
    _texto_simples,
)
from .memoria_busca import BYTES_PASSAGEM, LINHAS_PASSAGEM, Local, termos_contextuais

MAPA_PONTES = "docs/cdp/memoria/pontes.json"
MAX_BYTES_PONTES = 64 * 1024
LIMITE_PONTES = 6
_Termo = Annotated[str, Field(min_length=1, max_length=64), AfterValidator(_texto_simples)]


class _Ponte(_Modelo):
    id: Slug
    origem: Escopo
    escopos: list[Escopo] = Field(min_length=1, max_length=len(ESCOPO))
    gatilhos: list[_Termo] = Field(min_length=1, max_length=8)
    revisada_em: date
    rever_em: date
    evidencia: Evidencia

    @model_validator(mode="after")
    def conferir(self) -> _Ponte:
        texto = self.evidencia.trecho
        if not self.evidencia.caminho.startswith("docs/cdp/") or not self.evidencia.caminho.endswith(".md"):
            raise ValueError("ponte exige documento canônico do CDP")
        if len(texto.split("\n")) > LINHAS_PASSAGEM or len(texto.encode()) > BYTES_PASSAGEM:
            raise ValueError("ponte excede o limite por passagem")
        if (self.origem in self.escopos or len(self.escopos) != len(set(self.escopos))
                or self.revisada_em >= self.rever_em):
            raise ValueError("escopo repetido ou validade inválida")
        chaves = [frozenset(termos_contextuais(g)) for g in self.gatilhos]
        if any(not c for c in chaves) or len(chaves) != len(set(chaves)):
            raise ValueError("gatilho vazio ou repetido")
        return self


class _Mapa(_Modelo):
    versao: Literal[1]
    pontes: list[_Ponte] = Field(max_length=48)

    @field_validator("versao", mode="before")
    @classmethod
    def inteiro(cls, valor):
        if type(valor) is not int:
            raise ValueError("versão exige um inteiro")
        return valor

    @model_validator(mode="after")
    def conferir(self) -> _Mapa:
        if len({p.id for p in self.pontes}) != len(self.pontes):
            raise ValueError("ID de ponte repetido")
        return self


@dataclass(frozen=True)
class PonteResolvida:
    id: str
    origem: Escopo
    local: Local
    trecho: str


def candidatas_pontes(catalogo: Catalogo, escopo: Escopo, consulta: str) -> list[PonteResolvida]:
    """Verifica o Git e devolve apenas os recortes explicitamente curados."""
    fontes = catalogo.fontes
    if fontes.trabalho:
        raise MemoriaErro("as pontes exigem uma revisão Git")
    bruto = fontes.ler(MAPA_PONTES, MAX_BYTES_PONTES)
    try:
        json.loads(bruto, object_pairs_hook=_chaves_unicas)
        mapa = _Mapa.model_validate_json(bruto)
    except (ValueError, RecursionError) as exc:
        raise MemoriaErro("mapa de pontes inválido") from exc
    permitidas = set(catalogo.fontes_por_escopo[escopo])
    termos = termos_contextuais(consulta).keys()
    candidatas = []
    for ponte in mapa.pontes:
        ev = ponte.evidencia
        if (escopo not in ponte.escopos or ev.caminho in permitidas
                or ev.caminho not in catalogo.fontes_por_escopo[ponte.origem]
                or not ponte.revisada_em <= catalogo.data < ponte.rever_em):
            continue
        if not any(termos_contextuais(g).keys() <= termos for g in ponte.gatilhos):
            continue
        apoio = termos & termos_contextuais(ev.trecho).keys()
        candidatas.append((-len(apoio), ponte.id, ponte.origem, ev))

    resultado = []
    vistos = set()
    for _, id_, origem, ev in sorted(candidatas):
        try:
            local = _localizar(fontes, ev)
        except MemoriaGitIndisponivel:
            raise
        except MemoriaErro:
            continue  # A prova mudou ou deixou de ter uma ocorrência única.
        if local in vistos:
            continue
        vistos.add(local)
        resultado.append(PonteResolvida(id_, origem, local, ev.trecho))
        if len(resultado) == LIMITE_PONTES:
            break
    return resultado
