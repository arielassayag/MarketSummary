"""Planejamento e validação local de uma revisão de memória entre sessões."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from .memoria import (
    ESCOPO,
    MAX_BYTES_FONTE,
    MAX_NOTAS,
    Catalogo,
    Escopo,
    Evidencia,
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
MAX_BYTES_CONTINUIDADE = 512 * 1024
MAX_INVESTIGACOES = 48
DIAS_SOBREPOSICAO = 14
_PROBLEMAS_CATALOGO = {"arquivo", "schema", "evidencia", "linhagem", "duplicata", "rever_validade"}
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


def _fila_sonho(catalogo: Catalogo, limite: int, desde: str | None, *,
                exigir_provas: bool) -> list[dict]:
    if catalogo.fontes.trabalho:
        raise MemoriaErro("o dreaming exige uma revisão Git comprometida")
    if type(limite) is not int or not 1 <= limite <= LIMITE_SONHO:
        raise MemoriaErro(f"o plano aceita de 1 a {LIMITE_SONHO} itens")
    if type(exigir_provas) is not bool:
        raise MemoriaErro("a exigência de provas precisa ser um valor lógico")
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

    return _ordenar_fila(itens.values())


def _ordenar_fila(itens: Iterable[dict]) -> list[dict]:
    return sorted(itens, key=lambda x: (
        _PRIORIDADE.get(x["acao"], 0), "pendencia_anterior" not in x, x["id"], x["acao"]
    ))


def _recibo_item(catalogo: Catalogo, item: dict, recebidos: dict[str, str | None]) -> dict:
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
    return {**recibo, "uid": _digestir(recibo)}


def _plano_sonho(catalogo: Catalogo, todos: list[dict], *, limite: int, desde: str | None,
                 pagina: int, recebidos: dict[str, str | None], exigir_provas: bool) -> dict:
    inicio = (pagina - 1) * limite
    if pagina > 1 and inicio >= len(todos):
        raise MemoriaErro("página fora da fila de revisão")
    # O identificador reaparece em outra revisão quando o trabalho é o mesmo.
    fila = [_recibo_item(catalogo, item, recebidos) for item in todos[inicio:inicio + limite]]

    pacote = {
        "versao": 1, "revisao": catalogo.fontes.revisao, "data": catalogo.data.isoformat(),
        "desde": desde, "dias_sobreposicao": DIAS_SOBREPOSICAO if desde is None else None,
        "limite": limite, "pagina": pagina, "total": len(todos),
        "adiados": max(0, len(todos) - inicio - limite),
        "fila": fila, "contagens": dict(catalogo.contagens),
        "indice": {e: [r.nota.id for r in catalogo.ativos if e in r.nota.escopos]
                   for e in ESCOPO},
    }
    if exigir_provas:
        pacote["exigir_provas"] = True
    return {**pacote, "sha256": _digestir(pacote)}


def sonhar(catalogo: Catalogo, *, limite: int = LIMITE_SONHO, desde: str | None = None,
           pagina: int = 1, exigir_provas: bool = False, continuidade: bytes | None = None,
           lacre_continuidade: str | None = None) -> dict:
    """Monta um plano finito. A leitura operacional nunca adota uma resposta do plano."""
    if type(pagina) is not int or pagina < 1:
        raise MemoriaErro("a página precisa ser um inteiro positivo")
    todos, _ = _preparar_fila(catalogo, limite, desde, exigir_provas, continuidade, lacre_continuidade)
    return _plano_sonho(catalogo, todos, limite=limite, desde=desde, pagina=pagina, recebidos={},
                        exigir_provas=exigir_provas)


def ler_fonte_sonho(catalogo: Catalogo, plano: dict, uid: str, *,
                   caminho: str | None, linhas: tuple[int, int] | None,
                   nota_id: str | None) -> dict:
    item = next((i for i in plano["fila"] if i["uid"] == uid), None)
    if item is None:
        raise MemoriaErro("item fora da página selecionada")
    out = {"plano_sha256": plano["sha256"], "revisao": catalogo.fontes.revisao, "uid": uid}
    if nota_id is not None:
        if linhas is not None or nota_id not in {n["id"] for n in item["notas"]}:
            raise MemoriaErro("nota fora do item ou intervalo incompatível")
        return {**out, "nota": catalogo.notas[nota_id].model_dump(mode="json")}
    if caminho not in item["fontes"] or linhas is None:
        raise MemoriaErro("informe fonte do item e intervalo de linhas")
    inicio, fim = linhas
    todas = catalogo.fontes.linhas(caminho)
    if not 1 <= inicio <= fim <= len(todas) or fim - inicio >= 40:
        raise MemoriaErro("intervalo inválido ou acima de 40 linhas")
    corpo = "\n".join(todas[inicio - 1:fim])
    if len(corpo.encode()) > 4096:
        raise MemoriaErro("o trecho excede 4 KiB")
    return {**out, "caminho": caminho, "inicio": inicio, "fim": fim, "trecho": corpo,
            "sha256": hashlib.sha256(corpo.encode()).hexdigest()}


_Frase = Annotated[str, Field(min_length=1, max_length=420), AfterValidator(_texto_simples)]
_Revisao = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]


class ReferenciaProva(_Modelo):
    caminho: str
    sha256: Sha

    def chave(self) -> tuple[str, str]:
        return self.caminho, self.sha256


class Hipotese(_Modelo):
    enunciado: _Frase
    apoios: list[ReferenciaProva] = Field(default_factory=list, max_length=4)
    contrarios: list[ReferenciaProva] = Field(default_factory=list, max_length=4)


class Investigacao(_Modelo):
    pergunta: _Frase
    hipoteses: list[Hipotese] = Field(min_length=1, max_length=3)
    proximo_teste: _Frase

    @model_validator(mode="after")
    def conferir_hipoteses(self) -> Investigacao:
        if len({h.enunciado.casefold() for h in self.hipoteses}) != len(self.hipoteses):
            raise ValueError("hipóteses repetidas")
        return self


class ItemRevisado(_Modelo):
    uid: Sha
    decisao: Literal["manter", "investigar", "propor_candidata"]
    motivo: _Frase
    candidata: Nota | None = None
    provas: list[Evidencia] = Field(default_factory=list, max_length=4)
    diagnostico: Literal["sem_fonte_disponivel", "problema_catalogo"] | None = None
    investigacao: Investigacao | None = None

    @model_validator(mode="after")
    def conferir(self) -> ItemRevisado:
        if (self.candidata is not None) != (self.decisao == "propor_candidata"):
            raise ValueError("a decisão e a candidata devem concordar")
        if self.candidata is not None and self.candidata.estado != "candidata":
            raise ValueError("a devolutiva só aceita candidatas")
        provas = {(prova.caminho, prova.sha256) for prova in self.provas}
        if len(provas) != len(self.provas):
            raise ValueError("prova repetida")
        if self.diagnostico and (self.decisao != "investigar" or self.provas):
            raise ValueError("um diagnóstico sem prova literal só cabe em investigar")
        if self.investigacao is not None:
            if self.decisao != "investigar":
                raise ValueError("hipóteses em aberto só cabem em investigar")
            for h in self.investigacao.hipoteses:
                refs = [r.chave() for r in (*h.apoios, *h.contrarios)]
                if len(set(refs)) != len(refs) or not set(refs) <= provas:
                    raise ValueError("referência de hipótese repetida ou fora das provas do item")
        return self


class Devolutiva(_Modelo):
    plano_sha256: Sha
    respostas: list[ItemRevisado] = Field(max_length=LIMITE_SONHO)


class OrigemInvestigacao(_Modelo):
    revisao: _Revisao
    data: date
    desde: _Revisao | None
    acao: str = Field(min_length=1, max_length=40)
    id: str = Field(min_length=1, max_length=240)
    uid: Sha


class RetomadaInvestigacao(_Modelo):
    origem: OrigemInvestigacao
    revisao_da_prova: _Revisao
    data_da_prova: date
    resposta: ItemRevisado


class Continuidade(_Modelo):
    versao: Literal[1]
    itens: list[RetomadaInvestigacao] = Field(max_length=MAX_INVESTIGACOES)
    resolvidas: list[RetomadaInvestigacao] = Field(default_factory=list, max_length=MAX_INVESTIGACOES)
    sha256: Sha


def _tem_problema_catalogo(catalogo: Catalogo, item: dict) -> bool:
    nota = catalogo.notas.get(item["id"])
    vencida = nota is not None and nota.estado == "curada" and catalogo.data >= nota.rever_em
    return ((item["acao"] in _PROBLEMAS_CATALOGO
             and item.get("pendencia_anterior", {}).get("na_fila_atual", True)) or vencida or any(
        problema["id"] == item["id"] and problema["codigo"] in _PROBLEMAS_CATALOGO
        for problema in catalogo.problemas
    ))


def _tem_fonte_legivel(catalogo: Catalogo, item: dict) -> bool:
    for caminho in item["fontes"]:
        try:
            linhas = catalogo.fontes.linhas(caminho)
        except MemoriaGitIndisponivel:
            raise
        except MemoriaErro:
            continue
        if any(linha.strip() for linha in linhas):
            return True
    return False


def _conferir_provas(catalogo: Catalogo, item: dict, resposta: ItemRevisado, *,
                     exigir_provas: bool) -> list[dict]:
    if exigir_provas and resposta.decisao == "manter":
        if _tem_problema_catalogo(catalogo, item):
            raise MemoriaErro("manter não resolve problema conhecido do catálogo")
        if not resposta.provas:
            raise MemoriaErro("manter exige ao menos uma prova literal")
    if exigir_provas and resposta.decisao == "investigar" and not (
        resposta.provas or resposta.diagnostico
    ):
        raise MemoriaErro("investigar exige prova literal ou diagnóstico verificável")
    if resposta.diagnostico == "problema_catalogo" and not _tem_problema_catalogo(catalogo, item):
        raise MemoriaErro("o diagnóstico de problema do catálogo diverge do item")
    if resposta.diagnostico == "sem_fonte_disponivel" and (
        not item["fontes"] or _tem_fonte_legivel(catalogo, item)
    ):
        raise MemoriaErro("o diagnóstico de fonte indisponível diverge do item")
    if any(prova.caminho not in item["fontes"] for prova in resposta.provas):
        raise MemoriaErro("prova literal fora das fontes do item selecionado")
    return [_localizar(catalogo.fontes, prova).json() for prova in resposta.provas]


def _preparar_fila(catalogo: Catalogo, limite: int, desde: str | None, exigir_provas: bool,
                   bruto: bytes | None, lacre: str | None) -> tuple[list[dict], list[dict]]:
    fila = _fila_sonho(catalogo, limite, desde, exigir_provas=exigir_provas)
    if bruto is None and lacre is None:
        return fila, []
    if not exigir_provas or bruto is None or lacre is None:
        raise MemoriaErro("a continuidade exige provas e o lacre esperado")
    if len(bruto) > MAX_BYTES_CONTINUIDADE:
        raise MemoriaErro("a continuidade excede o limite de bytes")
    objeto = json.loads(bruto, object_pairs_hook=_chaves_unicas)
    continuidade = Continuidade.model_validate_json(bruto)
    if continuidade.sha256 != lacre or _digestir({
        k: v for k, v in objeto.items() if k != "sha256"
    }) != lacre:
        raise MemoriaErro("o lacre da continuidade diverge")
    if len(continuidade.itens) + len(continuidade.resolvidas) > MAX_INVESTIGACOES:
        raise MemoriaErro("há investigações além do limite de continuidade")
    itens = {(i["acao"], i["id"]): i for i in fila}
    preservadas = _retomar_investigacoes(catalogo, itens, continuidade)
    return _ordenar_fila(itens.values()), preservadas


def _retomar_investigacoes(catalogo: Catalogo, itens: dict[tuple[str, str], dict],
                           continuidade: Continuidade) -> list[dict]:
    raiz = catalogo.fontes.raiz
    catalogos = {(catalogo.fontes.revisao, catalogo.data): catalogo}
    filas: dict[tuple, dict[tuple[str, str], dict]] = {}
    vistos: set[tuple[str, str]] = set()
    preservadas = []

    def catalogo_de(revisao: str, data: date) -> Catalogo:
        chave = (revisao, data)
        if chave not in catalogos:
            catalogos[chave] = Catalogo(Fontes(raiz, revisao=revisao), data)
        return catalogos[chave]

    registros = [(r, "investigar") for r in continuidade.itens]
    registros.extend((r, "manter") for r in continuidade.resolvidas)
    for registro, disposicao in registros:
        origem, r = registro.origem, registro.resposta
        chave = (origem.acao, origem.id)
        if (chave in vistos or r.decisao != disposicao or r.uid != origem.uid
                or not origem.data <= registro.data_da_prova <= catalogo.data):
            raise MemoriaErro("origem, data ou disposição inválida na continuidade")
        vistos.add(chave)
        for antes, depois in ((origem.revisao, registro.revisao_da_prova),
                              (registro.revisao_da_prova, catalogo.fontes.revisao)):
            try:
                _git(raiz, "merge-base", "--is-ancestor", antes, depois)
            except MemoriaErro as exc:
                raise MemoriaErro("a continuidade precisa pertencer à história Git do plano") from exc
        antigo = catalogo_de(origem.revisao, origem.data)
        corte = (origem.revisao, origem.data, origem.desde)
        if corte not in filas:
            filas[corte] = {(i["acao"], i["id"]): i for i in _fila_sonho(
                antigo, LIMITE_SONHO, origem.desde, exigir_provas=True)}
        primeiro = filas[corte].get(chave)
        if primeiro is None or _recibo_item(antigo, primeiro, {})["uid"] != origem.uid:
            raise MemoriaErro("a investigação diverge do item de origem no Git")
        anterior = catalogo_de(registro.revisao_da_prova, registro.data_da_prova)
        na_fila_atual = chave in itens
        item = {**itens.get(chave, primeiro), "fontes": primeiro["fontes"]}
        contexto_anterior = {"na_fila_atual": anterior is antigo}
        _conferir_provas(anterior, {**primeiro, "pendencia_anterior": contexto_anterior},
                          r, exigir_provas=True)
        provas = []
        for prova in r.provas:
            try:
                _localizar(catalogo.fontes, prova)
            except MemoriaGitIndisponivel:
                raise
            except MemoriaErro:
                situacao = "desatualizada"
            else:
                situacao = "localizada"
            provas.append({**prova.model_dump(), "situacao": situacao})
        if disposicao == "manter" and not na_fila_atual and all(
            p["situacao"] == "localizada" for p in provas
        ):
            preservadas.append(registro.model_dump(mode="json"))
            continue
        itens[chave] = {**item, "pendencia_anterior": {
            **registro.model_dump(mode="json", exclude={"resposta"}),
            "disposicao_anterior": disposicao,
            "motivo": r.motivo, "investigacao": r.investigacao.model_dump() if r.investigacao else None,
            "diagnostico": r.diagnostico, "provas": provas, "na_fila_atual": na_fila_atual,
        }}
    return preservadas


def _continuidade(itens: list[dict], resolvidas: list[dict]) -> dict:
    if len(itens) + len(resolvidas) > MAX_INVESTIGACOES:
        raise MemoriaErro("há investigações além do limite de continuidade")
    corpo = {"versao": 1, "itens": itens}
    if resolvidas:
        corpo["resolvidas"] = resolvidas
    lacrado = {**corpo, "sha256": _digestir(corpo)}
    if len(json.dumps(lacrado, ensure_ascii=False).encode()) > MAX_BYTES_CONTINUIDADE:
        raise MemoriaErro("a continuidade excede o limite de bytes")
    return lacrado


def _registro_continuidade(plano: dict, item: dict, r: ItemRevisado) -> dict:
    anterior = item.get("pendencia_anterior")
    origem = anterior["origem"] if anterior else {
        "revisao": plano["revisao"], "data": plano["data"], "desde": plano["desde"],
        "acao": item["acao"], "id": item["id"], "uid": r.uid,
    }
    return {"origem": origem, "revisao_da_prova": plano["revisao"], "data_da_prova": plano["data"],
            "resposta": {**r.model_dump(mode="json"), "uid": origem["uid"]}}


def conferir_sonho(catalogo: Catalogo, plano: dict, bruto: bytes) -> dict:
    corpo = {k: v for k, v in plano.items() if k != "sha256"}
    exigir_provas = plano.get("exigir_provas", False)
    if (plano.get("sha256") != _digestir(corpo) or plano.get("revisao") != catalogo.fontes.revisao
            or plano.get("data") != catalogo.data.isoformat() or catalogo.fontes.trabalho
            or type(exigir_provas) is not bool):
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
    pendencias: list[dict] = []
    continuacoes: list[dict] = []
    resolucoes: list[dict] = []
    encerradas: list[dict] = []
    caminhos_notas = catalogo.fontes.catalogo()
    ids = {PurePosixPath(caminho).stem for caminho in caminhos_notas}
    vagas_catalogo = MAX_NOTAS - len(caminhos_notas)
    for r in resposta.respostas:
        nota, item = r.candidata, esperados[r.uid]
        provas = _conferir_provas(catalogo, item, r, exigir_provas=exigir_provas)
        anterior = item.get("pendencia_anterior")
        if anterior and nota is not None:
            raise MemoriaErro("a investigação retomada exige manter com prova ou continuar investigando")
        if anterior and anterior["investigacao"] and r.decisao == "investigar" and r.investigacao is None:
            raise MemoriaErro("a pendência exige hipóteses e próximo teste na nova devolutiva")
        if r.decisao == "investigar":
            pendencia = {"uid": r.uid, "acao": item["acao"], "id": item["id"], "motivo": r.motivo}
            if provas:
                pendencia["provas"] = provas
            if r.diagnostico:
                pendencia["diagnostico"] = r.diagnostico
            if r.investigacao:
                pendencia["investigacao"] = r.investigacao.model_dump()
            pendencias.append(pendencia)
            if exigir_provas:
                continuacoes.append(_registro_continuidade(plano, item, r))
        elif anterior:
            resolucoes.append({"origem": anterior["origem"], "motivo": r.motivo, "provas": provas})
            encerradas.append(_registro_continuidade(plano, item, r))
        if nota is None:
            continue
        if nota.id in ids or nota.registrada_em != catalogo.data:
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
    out = {"ok": True, "plano_sha256": plano["sha256"], "respostas": len(vistos),
           "candidatas": candidatas, "vagas_catalogo": vagas_catalogo,
           "pendencias": pendencias, "estado": "propostas_para_revisao"}
    if continuacoes or resolucoes:
        out["continuidade"] = _continuidade(continuacoes, encerradas)
    if resolucoes:
        out["resolucoes"] = resolucoes
    return out


def retomar_sonho(catalogo: Catalogo, *, limite: int = LIMITE_SONHO, desde: str | None = None,
                  devolutivas: Iterable[bytes], exigir_provas: bool = False,
                  continuidade: bytes | None = None, lacre_continuidade: str | None = None,
                  lacres_devolutivas: Iterable[str] | None = None) -> dict:
    """Confere as páginas em sequência na mesma revisão e oferece o próximo plano."""
    fila, encerradas = _preparar_fila(catalogo, limite, desde, exigir_provas, continuidade,
                                     lacre_continuidade)
    recebidos: dict[str, str | None] = {}
    candidatas: list[dict] = []
    pendencias: list[dict] = []
    continuacoes: list[dict] = []
    resolucoes: list[dict] = []
    ids_candidatas: set[str] = set()
    itens_conferidos = 0
    pagina = 1
    lacres = []
    esperados = tuple(lacres_devolutivas) if lacres_devolutivas is not None else None
    for bruto in devolutivas:
        if itens_conferidos == len(fila):
            raise MemoriaErro("há devolutivas além da fila de revisão")
        lacre = hashlib.sha256(bruto).hexdigest()
        if esperados is not None and (pagina > len(esperados) or lacre != esperados[pagina - 1]):
            raise MemoriaErro("a devolutiva diverge do lacre fixado para a página")
        lacres.append(lacre)
        plano = _plano_sonho(catalogo, fila, limite=limite, desde=desde, pagina=pagina,
                             recebidos=recebidos, exigir_provas=exigir_provas)
        resposta = conferir_sonho(catalogo, plano, bruto)
        for candidata in resposta["candidatas"]:
            if candidata["id"] in ids_candidatas:
                raise MemoriaErro("ID de candidata repetido entre páginas")
            ids_candidatas.add(candidata["id"])
        candidatas.extend(resposta["candidatas"])
        pendencias.extend(resposta["pendencias"])
        continuacoes.extend(resposta.get("continuidade", {}).get("itens", ()))
        encerradas.extend(resposta.get("continuidade", {}).get("resolvidas", ()))
        resolucoes.extend(resposta.get("resolucoes", ()))
        itens_conferidos += resposta["respostas"]
        pagina += 1
    if esperados is not None and len(esperados) != len(lacres):
        raise MemoriaErro("faltam devolutivas com lacre fixado")
    revisao = catalogo.fontes.revisao
    resumo = {"revisao": revisao, "data": catalogo.data.isoformat(), "desde": desde,
              "total": len(fila), "paginas_conferidas": pagina - 1,
              "itens_conferidos": itens_conferidos, "pendencias": pendencias,
              "candidatas": candidatas}
    if exigir_provas:
        resumo["exigir_provas"] = True
    if lacres:
        resumo["lacres_devolutivas"] = lacres
    if resolucoes:
        resumo["resolucoes"] = resolucoes
    if itens_conferidos == len(fila):
        if continuacoes or continuidade is not None:
            resumo["continuidade"] = _continuidade(continuacoes, encerradas)
        return {**resumo, "estado": "cobertura_completa", "proximo_plano": None,
                "desde_sugerido": revisao}
    proximo = _plano_sonho(catalogo, fila, limite=limite, desde=desde, pagina=pagina,
                           recebidos=recebidos, exigir_provas=exigir_provas)
    return {**resumo, "estado": "em_andamento", "proximo_plano": proximo}
