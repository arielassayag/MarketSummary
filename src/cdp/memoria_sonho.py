"""Planejamento e validação local de uma revisão de memória entre sessões."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Literal

from pydantic import Field, model_validator

from .memoria import (
    ESCOPO,
    MAX_BYTES_FONTE,
    MAX_NOTAS,
    Catalogo,
    Escopo,
    Fontes,
    MemoriaErro,
    MemoriaGitIndisponivel,
    Nota,
    Sha,
    _chaves_unicas,
    _git,
    _localizar,
    _Modelo,
    _relatorio,
    _texto_simples,
)

LIMITE_SONHO = 12
MAX_BYTES_RESPOSTA = 128 * 1024
DIAS_SOBREPOSICAO = 14
_PRIORIDADE = {
    "arquivo": 0, "schema": 0, "evidencia": 0, "linhagem": 0, "duplicata": 1,
    "rever_validade": 2, "revisar_candidata": 3, "comparar_semelhanca": 4, "revisar_fonte": 5,
}


def _digestir(objeto: object) -> str:
    return hashlib.sha256(json.dumps(objeto, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _fontes_alteradas(c: Catalogo, universo: tuple[str, ...], desde: str | None) -> list[str]:
    raiz, revisao = c.fontes.raiz, c.fontes.revisao
    if desde:
        Fontes(raiz, revisao=desde)
        try:
            _git(raiz, "merge-base", "--is-ancestor", desde, revisao)
        except MemoriaErro as exc:
            raise MemoriaErro("a revisão anterior precisa ser ancestral da revisão do plano") from exc
        bruto = _git(raiz, "diff", "--name-only", "-z", "--no-renames", "--no-ext-diff",
                     "--no-textconv", desde, revisao,
                     "--", *universo)
    else:
        corte = c.data - timedelta(days=DIAS_SOBREPOSICAO)
        # A sobreposição evita perder mudanças que chegaram depois de uma execução. O
        # pacote identifica o mesmo trabalho por hash quando o conteúdo não mudou.
        bruto = _git(raiz, "log", "--first-parent", "--format=", "--name-only", "-z",
                     "--no-renames", "--no-ext-diff", "--no-textconv", "--no-notes",
                     f"--since-as-filter={corte.isoformat()}T00:00:00-03:00",
                     revisao, "--", *universo)
    permitidos = set(universo)
    return sorted({p for p in bruto.decode().split("\0") if p in permitidos})


def wiki(c: Catalogo, escopo: Escopo) -> dict:
    """Vista derivada. Os registros curados e suas fontes continuam no Git."""
    registros = [r for r in c.ativos if escopo in r.nota.escopos]
    topicos: dict[str, list[str]] = {}
    notas = []
    for registro in registros:
        nota = registro.nota
        for termo in nota.tags:
            topicos.setdefault(termo.casefold(), []).append(nota.id)
        notas.append({**registro.json(), "substitui": nota.substitui})
    return {
        "versao": 1, "revisao": c.fontes.revisao, "data": c.data.isoformat(),
        "escopo": escopo, "ressalvas": bool(c.problemas), "notas": notas,
        "topicos": {tema: ids for tema, ids in sorted(topicos.items())},
    }


def sonhar(catalogo: Catalogo, *, limite: int = LIMITE_SONHO, desde: str | None = None,
           pagina: int = 1) -> dict:
    """Monta um plano finito. A leitura operacional nunca adota uma resposta do plano."""
    if catalogo.fontes.trabalho:
        raise MemoriaErro("o dreaming exige uma revisão Git comprometida")
    if type(limite) is not int or not 1 <= limite <= LIMITE_SONHO:
        raise MemoriaErro(f"o plano aceita de 1 a {LIMITE_SONHO} itens")
    if type(pagina) is not int or pagina < 1:
        raise MemoriaErro("a página precisa ser um inteiro positivo")
    fontes_por_escopo = catalogo.fontes_por_escopo
    universo = tuple(sorted({p for fontes in fontes_por_escopo.values() for p in fontes}))
    audit = _relatorio(catalogo)
    itens: dict[tuple[str, str], dict] = {}

    def incluir(acao: str, id_: str, detalhe: str, caminhos: set[str],
                escopos: set[Escopo], relacionadas: set[str]) -> None:
        item = itens.setdefault((acao, id_), {"acao": acao, "id": id_, "detalhe": [],
                                             "fontes": [], "escopos": [], "relacionadas": []})
        item["detalhe"] = sorted(set(item["detalhe"]) | {detalhe})
        item["fontes"] = sorted(set(item["fontes"]) | caminhos)
        item["escopos"] = sorted(set(item["escopos"]) | escopos)
        item["relacionadas"] = sorted(set(item["relacionadas"]) | relacionadas)

    for linha in audit["fila_de_revisao"]:
        id_, acao = linha["id"], linha["acao"]
        if id_ in catalogo.substituidas and acao in ("evidencia", "rever_validade"):
            continue
        nota = catalogo.notas.get(id_)
        relacionadas = {linha["detalhe"]} if acao == "comparar_semelhanca" else set()
        if nota:
            relacionadas.update(nota.substitui)
        notas = [catalogo.notas[i] for i in sorted(relacionadas | {id_}) if i in catalogo.notas]
        caminhos = {ev.caminho for n in notas for ev in n.evidencias}
        escopos = {e for n in notas for e in n.escopos}
        incluir(acao, id_, linha["detalhe"], caminhos, escopos, relacionadas)

    for caminho in _fontes_alteradas(catalogo, universo, desde):
        escopos = {e for e, caminhos in fontes_por_escopo.items() if caminho in caminhos}
        incluir("revisar_fonte", caminho, "fonte canônica mudou no intervalo", {caminho}, escopos, set())

    todos = sorted(itens.values(), key=lambda x: (_PRIORIDADE.get(x["acao"], 0), x["id"], x["acao"]))
    fila = []
    recebidos: dict[str, str | None] = {}
    inicio = (pagina - 1) * limite
    if pagina > 1 and inicio >= len(todos):
        raise MemoriaErro("página fora da fila de revisão")
    for item in todos[inicio:inicio + limite]:
        origens = []
        for caminho in item["fontes"]:
            if caminho not in recebidos:
                try:
                    corpo = catalogo.fontes.ler(caminho, MAX_BYTES_FONTE)
                except MemoriaGitIndisponivel:
                    raise
                except MemoriaErro:
                    recebidos[caminho] = None
                else:
                    recebidos[caminho] = hashlib.sha256(corpo).hexdigest()
            origens.append({"caminho": caminho, "sha256": recebidos[caminho]})
        notas = [{"id": id_, "sha256": _digestir(catalogo.notas[id_].model_dump(mode="json"))}
                 for id_ in sorted(set(item["relacionadas"]) | {item["id"]})
                 if id_ in catalogo.notas]
        recibo = {**item, "origens": origens, "notas": notas}
        # O identificador reaparece em uma nova revisão quando o trabalho é o mesmo.
        fila.append({**recibo, "uid": _digestir(recibo)})

    pacote = {
        "versao": 1, "revisao": catalogo.fontes.revisao, "data": catalogo.data.isoformat(),
        "desde": desde, "dias_sobreposicao": DIAS_SOBREPOSICAO if desde is None else None,
        "limite": limite, "pagina": pagina, "total": len(todos),
        "adiados": max(0, len(todos) - inicio - limite),
        "fila": fila, "contagens": catalogo.contagens,
        "indice": {e: [r.nota.id for r in catalogo.ativos if e in r.nota.escopos]
                   for e in ESCOPO},
    }
    return {**pacote, "sha256": _digestir(pacote)}


class ItemRevisado(_Modelo):
    uid: Sha
    decisao: Literal["manter", "investigar", "propor_candidata"]
    motivo: str = Field(min_length=1, max_length=420)
    candidata: Nota | None = None

    @model_validator(mode="after")
    def conferir(self) -> ItemRevisado:
        _texto_simples(self.motivo)
        if (self.candidata is not None) != (self.decisao == "propor_candidata"):
            raise ValueError("a decisão e a candidata devem concordar")
        if self.candidata is not None and self.candidata.estado != "candidata":
            raise ValueError("a devolutiva só aceita candidatas")
        return self


class Devolutiva(_Modelo):
    plano_sha256: Sha
    respostas: list[ItemRevisado] = Field(max_length=LIMITE_SONHO)


def conferir_sonho(catalogo: Catalogo, plano: dict, bruto: bytes) -> dict:
    corpo = {k: v for k, v in plano.items() if k != "sha256"}
    if (plano.get("sha256") != _digestir(corpo) or plano.get("revisao") != catalogo.fontes.revisao
            or plano.get("data") != catalogo.data.isoformat() or catalogo.fontes.trabalho):
        raise MemoriaErro("o plano diverge da revisão Git ou da data")
    if len(bruto) > MAX_BYTES_RESPOSTA:
        raise MemoriaErro("a devolutiva excede o limite de bytes")
    json.loads(bruto, object_pairs_hook=_chaves_unicas)
    resposta = Devolutiva.model_validate_json(bruto)
    if resposta.plano_sha256 != plano["sha256"]:
        raise MemoriaErro("a devolutiva pertence a outro plano")
    esperados = {item["uid"]: item for item in plano["fila"]}
    vistos = {item.uid for item in resposta.respostas}
    if len(vistos) != len(resposta.respostas) or vistos != esperados.keys():
        raise MemoriaErro("cada item selecionado exige exatamente uma resposta")
    candidatas: list[dict] = []
    ids = set(catalogo.notas)
    for r in resposta.respostas:
        nota, item = r.candidata, esperados[r.uid]
        if nota is None:
            continue
        if len(ids) >= MAX_NOTAS or nota.id in ids or nota.registrada_em != catalogo.data:
            raise MemoriaErro("a candidata exige ID novo e a data de referência do plano")
        ids.add(nota.id)
        predecessoras = set(item["relacionadas"]) | {item["id"]}
        if (not set(nota.escopos) <= set(item["escopos"])
                or not set(nota.substitui) <= (predecessoras & catalogo.notas.keys())
                or any(ev.caminho not in item["fontes"] for ev in nota.evidencias)):
            raise MemoriaErro("escopo, substituição ou evidência fora do item selecionado")
        for evidencia in nota.evidencias:
            _localizar(catalogo.fontes, evidencia)
        candidatas.append(nota.model_dump(mode="json"))
    return {"ok": True, "plano_sha256": plano["sha256"], "respostas": len(vistos),
            "candidatas": candidatas, "estado": "propostas_para_revisao"}
