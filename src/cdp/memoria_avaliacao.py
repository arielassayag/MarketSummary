"""Avaliação reservada de recuperação de passagens em dois retratos do CDP."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, field_validator, model_validator

from .memoria import (
    LIMITE_CONSULTA,
    BuscaCanonica,
    Catalogo,
    Escopo,
    Evidencia,
    Fontes,
    Local,
    MemoriaErro,
    MemoriaGitIndisponivel,
    Sha,
    Slug,
    _chaves_unicas,
    _git,
    _localizar,
    _Modelo,
    _primarias,
    _texto_simples,
)

CORPUS = "docs/cdp/memoria/avaliacao_reservada.json"
ONTEM = "afee26ce4442ee5b30943b318d9640416ba02586"
REPLICA = "docs/cdp/memoria/avaliacao_replica.json"
K = 5
MODOS = ("ontem", "direta", "memoria")
MAX_BYTES_REVALIDACAO = 256 * 1024


class CasoReservado(_Modelo):
    id: Slug
    escopo: Escopo
    consulta: str = Field(min_length=1, max_length=LIMITE_CONSULTA)
    tipo: Literal["evidencia", "estado_atual", "fora_escopo"]
    grupos: list[list[Evidencia]] = Field(max_length=4)
    destinos_aceitos: list[Slug] | None = Field(default=None, min_length=1, max_length=4)

    @model_validator(mode="after")
    def conferir(self) -> CasoReservado:
        if self.destinos_aceitos is not None:
            if self.tipo != "estado_atual":
                raise ValueError("apenas consultas de estado atual admitem destinos aceitos")
            if len(set(self.destinos_aceitos)) != len(self.destinos_aceitos):
                raise ValueError("destino aceito repetido no caso")
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


class _ProvaRevalidada(_Modelo):
    id: Slug
    justificativa: Annotated[str, Field(min_length=1, max_length=600), AfterValidator(_texto_simples)]
    grupos: list[Annotated[list[Evidencia], Field(min_length=1, max_length=8)]] = Field(min_length=1, max_length=4)


class _ManifestoRevalidacao(_Modelo):
    versao: Literal[1]
    revisao_alvo: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    sha256_corpus: Sha
    casos: list[_ProvaRevalidada] = Field(min_length=1, max_length=128)

    @field_validator("versao", mode="before")
    @classmethod
    def conferir_versao(cls, valor):
        if type(valor) is not int:
            raise ValueError("a versão do manifesto exige um inteiro")
        return valor

    @model_validator(mode="after")
    def conferir_ids(self) -> _ManifestoRevalidacao:
        if len({c.id for c in self.casos}) != len(self.casos):
            raise ValueError("caso revalidado repetido")
        return self


def _grupos(fontes: Fontes, caso: CasoReservado) -> list[list[Local]]:
    try:
        return [[_localizar(fontes, ev) for ev in alternativas] for alternativas in caso.grupos]
    except MemoriaErro as exc:
        raise MemoriaErro(f"gabarito indisponível para {caso.id} em {fontes.revisao[:8]}") from exc


def _conferir_revalidacao(
    bruto: bytes, fontes: Fontes, corpus: CorpusReservado, sha256_corpus: str,
) -> dict[str, tuple[_ProvaRevalidada, list[list[Local]]]]:
    if fontes.trabalho or not isinstance(bruto, bytes) or len(bruto) > MAX_BYTES_REVALIDACAO:
        raise MemoriaErro("a revalidação exige bytes limitados e fontes Git congeladas")
    try:
        json.loads(bruto, object_pairs_hook=_chaves_unicas)
        manifesto = _ManifestoRevalidacao.model_validate_json(bruto)
    except (ValueError, RecursionError) as exc:
        raise MemoriaErro("manifesto de revalidação inválido") from exc
    if manifesto.revisao_alvo != fontes.revisao or manifesto.sha256_corpus != sha256_corpus:
        raise MemoriaErro("manifesto de revalidação diverge da revisão alvo ou do corpus")

    originais = {caso.id: caso for caso in corpus.casos}
    aprovadas = {}
    for prova in manifesto.casos:
        caso = originais.get(prova.id)
        if caso is None or caso.tipo != "evidencia":
            raise MemoriaErro(f"a revalidação exige um caso documental do corpus: {prova.id}")
        try:
            _grupos(fontes, caso)
        except MemoriaErro as exc:
            if isinstance(exc, MemoriaGitIndisponivel) or isinstance(exc.__cause__, MemoriaGitIndisponivel):
                raise
        else:
            raise MemoriaErro(f"gabarito original intacto na revisão alvo: {prova.id}")
        try:
            atualizado = CasoReservado.model_validate(caso.model_dump() | {"grupos": prova.grupos})
        except ValueError as exc:
            raise MemoriaErro(f"grupos revalidados inválidos para {prova.id}") from exc
        aprovadas[prova.id] = (prova, _grupos(fontes, atualizado))
    return aprovadas


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


def _medir_destino(caso: CasoReservado, saida: dict) -> dict:
    if caso.destinos_aceitos is None:
        return {}
    destino = saida["destino_atual"]
    aceito = destino in caso.destinos_aceitos
    retornou_fontes = bool(saida["fontes"])
    sem_contexto = not (retornou_fontes or saida["notas"] or saida["passagens"])
    return {
        "destino_atual": destino, "destino_aceito": aceito, "retornou_fontes": retornou_fontes,
        "estado_destino_correto_sem_contexto": aceito and bool(saida["orientacao_atual"]) and sem_contexto,
    }


def _resumo_destinos(medicoes: list[dict]) -> dict:
    anotadas = [m for m in medicoes if "destino_aceito" in m]
    if not anotadas:
        return {}
    return {
        "estado_destino_n": len(anotadas),
        "estado_destino_aceito": sum(m["destino_aceito"] for m in anotadas),
        "estado_destino_correto_sem_contexto": sum(m["estado_destino_correto_sem_contexto"] for m in anotadas),
    }


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
        "encaminhamentos_explicitos": sum(c.get("encaminhou_explicito", False) for c in atuais),
        **_resumo_destinos(atuais),
    }


def avaliar_reservada(fonte_corpus: Fontes, *, replica: bool = False, revalidacao: bytes | None = None) -> dict:
    caminho_corpus = REPLICA if replica else CORPUS
    bruto = fonte_corpus.ler(caminho_corpus, 256 * 1024)
    json.loads(bruto, object_pairs_hook=_chaves_unicas)
    corpus = CorpusReservado.model_validate_json(bruto)
    sha256_corpus = hashlib.sha256(bruto).hexdigest()
    revalidadas = (_conferir_revalidacao(revalidacao, fonte_corpus, corpus, sha256_corpus)
                  if revalidacao is not None else {})
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
    casos, provas = [], []
    for c in corpus.casos:
        gold_ontem = _grupos(ontem, c)
        revalidada = revalidadas.get(c.id)
        if revalidada is None:
            gold_hoje = _grupos(hoje, c)
        else:
            prova, gold_hoje = revalidada
            provas.append({"id": c.id, "justificativa": prova.justificativa,
                           "grupos_ontem": [[local.json() for local in grupo] for grupo in gold_ontem],
                           "grupos_hoje": [[local.json() for local in grupo] for grupo in gold_hoje]})
        hibrida = catalogo.buscar(c.escopo, c.consulta, K)
        memoria = _medir([Local(**p) for p in hibrida["passagens"]], gold_hoje,
                         encaminhou=bool(hibrida["orientacao_atual"]),
                         notas=bool(hibrida["notas"]))
        memoria.update(_medir_destino(c, hibrida))
        if c.tipo == "estado_atual":
            explicita = catalogo.buscar(c.escopo, c.consulta, K, estado_atual=True)
            memoria["encaminhou_explicito"] = bool(explicita["orientacao_atual"]) and not (
                explicita["notas"] or explicita["passagens"]
            )
        casos.append({
            "id": c.id, "escopo": c.escopo, "tipo": c.tipo, "grupos": len(gold_hoje),
            **({"grupos_ontem": len(gold_ontem)} if revalidada else {}),
            **({"destinos_aceitos": c.destinos_aceitos} if c.destinos_aceitos is not None else {}),
            "modos": {
                "ontem": _medir(direta_ontem.buscar(c.escopo, c.consulta, K), gold_ontem),
                "direta": _medir(catalogo.indice.buscar(c.escopo, c.consulta, K), gold_hoje),
                "memoria": memoria,
            },
        })
    relatorio = {
        "revisoes": {"ontem": ontem.revisao, "hoje": hoje.revisao, "codigo": _git(hoje.raiz, "rev-parse", "--verify", "HEAD").decode().strip(),
                     "corpus": sha256_corpus},
        "data": corpus.data.isoformat(), "limite": K, "corpus": caminho_corpus,
    }
    if revalidacao is None:
        relatorio["resumo"] = {modo: _resumo(casos, modo) for modo in MODOS}
    else:
        intactos = [c for c in casos if c["id"] not in revalidadas]
        atualizados = [c for c in casos if c["id"] in revalidadas]
        relatorio["resumo"] = {
            "provas_intactas": {modo: _resumo(intactos, modo) for modo in MODOS},
            "provas_revalidadas": {modo: _resumo(atualizados, modo) for modo in ("direta", "memoria")},
        }
        relatorio["revalidacao"] = {"sha256": hashlib.sha256(revalidacao).hexdigest(),
                                   "casos_intactos": len(intactos), "casos": provas}
    relatorio["casos"] = casos
    return relatorio
