"""Confere lacres e mascara rascunhos e revisões para correção cega."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from contextlib import ExitStack
from pathlib import Path

TRILHAS = ("risco", "valuation")
POLITICAS = {"risco": "registrar", "valuation": "zerar_caso"}


def texto(valor: object) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def objeto_unico(pares: list[tuple[str, object]]) -> dict:
    objeto = dict(pares)
    if len(objeto) != len(pares):
        raise ValueError("Objeto JSON com chaves repetidas")
    return objeto


def ler(caminho: Path, sha256: str | None = None) -> dict:
    raw = caminho.read_bytes()
    if sha256 is not None and hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError(f"Lacre divergente em {caminho.name}")
    objeto = json.loads(raw, object_pairs_hook=objeto_unico)
    if not isinstance(objeto, dict):
        raise ValueError(f"Objeto JSON esperado em {caminho.name}")
    return objeto


def lacre(valor: object, contexto: str) -> str:
    if not isinstance(valor, str) or len(valor) != 64:
        raise ValueError(f"Lacre SHA-256 ausente ou inválido em {contexto}")
    return valor


def por_id(itens: object, contexto: str) -> dict[str, dict]:
    if not isinstance(itens, list) or not itens:
        raise ValueError(f"Lista de registros ausente ou vazia em {contexto}")
    indice = {}
    for item in itens:
        id_ = item.get("id") if isinstance(item, dict) else None
        if not texto(id_) or id_ in indice:
            raise ValueError(f"ID ausente ou repetido em {contexto}: {id_!r}")
        indice[id_] = item
    return indice


def criterios(caso: dict) -> list[dict]:
    exigencias = por_id(caso.get("criterios"), caso["id"])
    resultado = []
    for id_, criterio in exigencias.items():
        pontos = criterio.get("pontos", 1)
        if type(pontos) is not int or pontos <= 0:
            raise ValueError(f"Pontuação inválida em {caso['id']}/{id_}")
        if not any(texto(criterio.get(campo)) for campo in ("descricao", "exigencia")):
            raise ValueError(f"Exigência ausente em {caso['id']}/{id_}")
        resultado.append(dict(criterio, pontos=pontos))
    return resultado


def portas_fatais(rubrica: dict, caso: dict) -> list[str]:
    portas = []
    for escopo in (rubrica, caso):
        for campo in ("falhas_fatais", "portas_fatais"):
            regras = escopo.get(campo, [])
            if not isinstance(regras, list) or not all(map(texto, regras)):
                raise ValueError(f"Portas fatais inválidas em {caso['id']}/{campo}")
            portas.extend(regras)
    return list(dict.fromkeys(portas))


def portas_risco(rubrica: dict, caso: dict) -> list[dict]:
    definicoes = rubrica.get("definicoes_portas_fatais")
    referencias = caso.get("portas_fatais")
    if (
        not isinstance(definicoes, dict)
        or not isinstance(referencias, list)
        or not all(map(texto, referencias))
        or len(set(referencias)) != len(referencias)
    ):
        raise ValueError(f"Definições ou referências de portas fatais inválidas em {caso['id']}")
    detalhes = []
    for id_ in referencias:
        definicao = definicoes.get(id_)
        if not isinstance(definicao, dict) or not texto(definicao.get("descricao")):
            raise ValueError(f"Definição ausente ou inválida em {caso['id']}/{id_}")
        evidencia = definicao.get("evidencia")
        if not isinstance(evidencia, list) or not all(map(texto, evidencia)):
            raise ValueError(f"Evidência de porta fatal inválida em {caso['id']}/{id_}")
        detalhes.append(
            {"id": id_, "regra": f"{id_} — {definicao['descricao']}", "definicao": definicao}
        )
    return detalhes


def casos_da_trilha(pasta: Path, trilha: str, lacres: dict, rng: secrets.SystemRandom):
    entrada = f"casos-{trilha}.json"
    nome_rubrica = f"rubrica-{trilha}.json"
    casos = por_id(
        ler(pasta / entrada, lacre(lacres.get("entrada_sha256"), entrada))["casos"], entrada
    )
    rubrica = ler(pasta / nome_rubrica, lacre(lacres.get("rubrica_sha256"), nome_rubrica))
    rubricas = por_id(rubrica["casos"], nome_rubrica)
    nomes = {
        "A": f"rascunho-{trilha}.json",
        "B": f"revisao-{trilha}-B.json",
        "C": f"revisao-{trilha}-C.json",
    }
    lacres_saidas = lacres.get("saidas_sha256", {})
    if not isinstance(lacres_saidas, dict) or lacres_saidas.keys() - set(nomes.values()):
        raise ValueError(f"Lacres de saídas incompatíveis em {trilha}")
    respostas = {}
    for braco, nome in nomes.items():
        esperado = lacre(lacres_saidas[nome], nome) if nome in lacres_saidas else None
        respostas[braco] = por_id(ler(pasta / nome, esperado)["casos"], nome)
    if rubricas.keys() != casos.keys() or any(
        itens.keys() != casos.keys() for itens in respostas.values()
    ):
        raise ValueError(f"IDs divergentes entre casos, rubrica e respostas em {trilha}")

    for id_, caso in casos.items():
        analises = {braco: itens[id_].get("analise") for braco, itens in respostas.items()}
        if not all(map(texto, analises.values())):
            raise ValueError(f"Análise ausente ou vazia em {id_}")
        bracos = list(nomes)
        rng.shuffle(bracos)
        mascara = dict(zip("XYZ", bracos, strict=True))
        exigencias = rubricas[id_]
        detalhes = portas_risco(rubrica, exigencias) if trilha == "risco" else []
        portas = (
            [item["regra"] for item in detalhes]
            if trilha == "risco"
            else portas_fatais(rubrica, exigencias)
        )
        regra = [
            escopo.get(campo)
            for escopo in (rubrica, exigencias)
            for campo in ("metrica", "correcao")
            if texto(escopo.get(campo))
        ]
        yield (
            {
                "id": id_,
                "trilha": trilha,
                "politica_porta_fatal": POLITICAS[trilha],
                "nome": next(
                    (
                        caso[campo]
                        for campo in ("nome", "titulo", "empresa")
                        if texto(caso.get(campo))
                    ),
                    id_,
                ),
                "caso": caso,
                "regra_correcao": "\n\n".join(dict.fromkeys(regra)) or None,
                "criterios": criterios(exigencias),
                "portas_fatais": portas,
                "portas_fatais_detalhes": detalhes,
                "opcoes": [
                    {"rotulo": rotulo, "analise": analises[braco]}
                    for rotulo, braco in mascara.items()
                ],
            },
            mascara,
        )


def gravar(pasta: Path, pacote: dict, chave: dict) -> None:
    documentos = (
        (pasta / "casos-para-correcao-cega.json", pacote, 0o444),
        (pasta / "chave-de-mascaramento.json", chave, 0o400),
    )
    arquivos = [
        (caminho, (json.dumps(objeto, ensure_ascii=False, indent=2) + "\n").encode(), modo)
        for caminho, objeto, modo in documentos
    ]
    criados = []
    try:
        with ExitStack() as pilha:
            handles = []
            for caminho, _, modo in arquivos:
                handle = pilha.enter_context(caminho.open("xb"))
                criados.append(caminho)
                caminho.chmod(modo)
                handles.append(handle)
            for handle, (_, raw, _) in zip(handles, arquivos, strict=True):
                handle.write(raw)
    except OSError:
        for caminho in criados:
            caminho.unlink(missing_ok=True)
        raise
    for caminho, raw, _ in arquivos:
        print(caminho.name, hashlib.sha256(raw).hexdigest())


def montar(pasta: Path, trilha: str | None = None) -> None:
    lacres = ler(pasta / "lacres.json")
    rng = secrets.SystemRandom()
    casos = []
    chave = {}
    for nome in (trilha,) if trilha else TRILHAS:
        for caso, mascara in casos_da_trilha(pasta, nome, lacres[nome], rng):
            if caso["id"] in chave:
                raise ValueError(f"ID repetido entre trilhas: {caso['id']}")
            casos.append(caso)
            chave[caso["id"]] = mascara
    rng.shuffle(casos)
    destino = pasta / trilha if trilha else pasta
    if trilha:
        destino.mkdir(mode=0o700, exist_ok=True)
    gravar(destino, {"casos": casos}, chave)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidencias", type=Path)
    parser.add_argument("--trilha", choices=TRILHAS)
    args = parser.parse_args()
    montar(args.evidencias, args.trilha)


if __name__ == "__main__":
    main()
