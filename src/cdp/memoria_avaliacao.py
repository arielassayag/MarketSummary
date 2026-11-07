"""Avaliação reservada de recuperação de passagens em dois retratos do CDP."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .memoria import (
    BuscaCanonica,
    Catalogo,
    Escopo,
    Evidencia,
    Fontes,
    Local,
    MemoriaErro,
    Slug,
    _chaves_unicas,
    _git,
    _localizar,
    _Modelo,
    _primarias,
)

CORPUS = "docs/cdp/memoria/avaliacao_reservada.json"
ONTEM = "afee26ce4442ee5b30943b318d9640416ba02586"
REPLICA = "docs/cdp/memoria/avaliacao_replica.json"
K = 5
MODOS = ("ontem", "direta", "memoria")


class CasoReservado(_Modelo):
    id: Slug
    escopo: Escopo
    consulta: str = Field(min_length=1, max_length=240)
    tipo: Literal["evidencia", "estado_atual", "fora_escopo"]
    grupos: list[list[Evidencia]] = Field(max_length=4)

    @model_validator(mode="after")
    def conferir(self) -> CasoReservado:
        if (self.tipo == "evidencia") != bool(self.grupos) or any(not g for g in self.grupos):
            raise ValueError("cada grupo exige uma evidência ou alternativas")
        chaves = [(ev.caminho, ev.sha256) for grupo in self.grupos for ev in grupo]
        if len(set(chaves)) != len(chaves):
            raise ValueError("evidência repetida no caso")
        if any(not any(ev.caminho in _primarias(self.escopo) for ev in grupo)
               for grupo in self.grupos):
            raise ValueError("cada grupo precisa de pelo menos uma fonte no índice direto")
        return self


class CorpusReservado(_Modelo):
    versao: Literal[1]
    data: date
    casos: list[CasoReservado] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def conferir(self) -> CorpusReservado:
        if len({c.id for c in self.casos}) != len(self.casos):
            raise ValueError("casos com ID repetido")
        if len({c.consulta.casefold().strip() for c in self.casos}) != len(self.casos):
            raise ValueError("consultas repetidas")
        return self


def _grupos(fontes: Fontes, caso: CasoReservado) -> list[list[Local]]:
    try:
        return [[_localizar(fontes, ev) for ev in alternativas] for alternativas in caso.grupos]
    except MemoriaErro as exc:
        raise MemoriaErro(f"gabarito indisponível para {caso.id} em {fontes.revisao[:8]}") from exc


def _atingidos(passagens: list[Local], grupos: list[list[Local]]) -> list[bool]:
    return [any(p.caminho == ev.caminho and p.inicio <= ev.inicio <= ev.fim <= p.fim
                for p in passagens for ev in alternativas) for alternativas in grupos]


def _medir(passagens: list[Local], grupos: list[list[Local]], *,
           encaminhou: bool = False, notas: bool = False) -> dict:
    if grupos:
        completo_1 = all(_atingidos(passagens[:1], grupos))
        atingidos_3 = _atingidos(passagens[:3], grupos)
        atingidos_5 = _atingidos(passagens[:K], grupos)
        completo_3, completo_5 = all(atingidos_3), all(atingidos_5)
        cobertura_3 = sum(atingidos_3) / len(grupos)
        cobertura_5 = sum(atingidos_5) / len(grupos)
        abstencao = None
    else:
        completo_1 = completo_3 = completo_5 = cobertura_3 = cobertura_5 = None
        abstencao = not passagens and not notas
    return {"completo_1": completo_1, "completo_3": completo_3, "cobertura_3": cobertura_3,
            "completo_5": completo_5, "cobertura_5": cobertura_5,
            "abstencao": abstencao, "encaminhou": encaminhou, "retornou_notas": notas,
            "passagens": [p.json() for p in passagens]}


def _resumo(casos: list[dict], modo: str) -> dict:
    positivos = [c["modos"][modo] for c in casos if c["tipo"] == "evidencia"]
    controles = [c["modos"][modo] for c in casos if c["tipo"] != "evidencia"]
    atuais = [c["modos"][modo] for c in casos if c["tipo"] == "estado_atual"]
    return {
        "perguntas_com_evidencia": len(positivos),
        "completo_1": sum(c["completo_1"] for c in positivos),
        "completo_3": sum(c["completo_3"] for c in positivos),
        "completo_5": sum(c["completo_5"] for c in positivos),
        "cobertura_media_3": (sum(c["cobertura_3"] for c in positivos) / len(positivos)
                              if positivos else None),
        "cobertura_media_5": (sum(c["cobertura_5"] for c in positivos) / len(positivos)
                              if positivos else None),
        "encaminhamentos_em_perguntas_estaticas": sum(c["encaminhou"] for c in positivos),
        "controles": len(controles),
        "abstencoes": sum(c["abstencao"] for c in controles),
        "consultas_estado": len(atuais),
        "encaminhamentos": sum(c["encaminhou"] for c in atuais),
    }


def avaliar_reservada(fonte_corpus: Fontes, *, replica: bool = False) -> dict:
    caminho_corpus = REPLICA if replica else CORPUS
    bruto = fonte_corpus.ler(caminho_corpus, 256 * 1024)
    json.loads(bruto, object_pairs_hook=_chaves_unicas)
    corpus = CorpusReservado.model_validate_json(bruto)
    ontem = Fontes(fonte_corpus.raiz, revisao=ONTEM)
    hoje = fonte_corpus
    catalogo = Catalogo(hoje, corpus.data)
    # O controle recebe os mesmos caminhos. As notas continuam disponíveis só no braço híbrido.
    direta_ontem = BuscaCanonica(ontem, catalogo.fontes_por_escopo)
    if catalogo.problemas:
        raise MemoriaErro("catálogo com ressalvas durante a avaliação reservada")
    for caminho in sorted({p for caminhos in catalogo.fontes_por_escopo.values()
                           for p in caminhos}):
        ontem.linhas(caminho)
        hoje.linhas(caminho)
    casos = []
    for c in corpus.casos:
        gold_ontem, gold_hoje = _grupos(ontem, c), _grupos(hoje, c)
        hibrida = catalogo.buscar(c.escopo, c.consulta, K)
        casos.append({
            "id": c.id, "escopo": c.escopo, "tipo": c.tipo, "grupos": len(c.grupos),
            "modos": {
                "ontem": _medir(direta_ontem.buscar(c.escopo, c.consulta, K), gold_ontem),
                "direta": _medir(catalogo.indice.buscar(c.escopo, c.consulta, K), gold_hoje),
                "memoria": _medir([Local(**p) for p in hibrida["passagens"]], gold_hoje,
                                  encaminhou=bool(hibrida["orientacao_atual"]),
                                  notas=bool(hibrida["notas"])),
            },
        })
    return {
        "revisoes": {"ontem": ontem.revisao, "hoje": hoje.revisao, "codigo": _git(hoje.raiz, "rev-parse", "--verify", "HEAD").decode().strip(),
                     "corpus": hashlib.sha256(bruto).hexdigest()},
        "data": corpus.data.isoformat(), "limite": K, "corpus": caminho_corpus,
        "resumo": {modo: _resumo(casos, modo) for modo in MODOS}, "casos": casos,
    }
