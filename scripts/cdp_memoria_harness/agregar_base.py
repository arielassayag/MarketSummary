"""Valida e agrega duas correções cegas de um ensaio Codex com três braços."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BRACOS = ("A", "B", "C")
ROTULOS = {"X", "Y", "Z"}
PARES = ("AB", "BC", "AC")
CLASSE = {
    (False, True): "ganhos",
    (True, False): "perdas",
    (True, True): "acertos_preservados",
    (False, False): "falhas_preservadas",
}


def texto(valor: object) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def indexar(itens: list[dict], campo: str) -> dict[str, dict]:
    indice = {}
    for item in itens:
        chave = item[campo]
        if not texto(chave) or chave in indice:
            raise ValueError(f"Identificador vazio ou repetido no campo {campo}: {chave!r}")
        indice[chave] = item
    return indice


def objeto_unico(pares: list[tuple[str, object]]) -> dict:
    objeto = dict(pares)
    if len(objeto) != len(pares):
        raise ValueError("Objeto JSON com chaves repetidas")
    return objeto


def ler(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"), object_pairs_hook=objeto_unico)


def validar_opcao(opcao: dict, analise: str, rubrica: dict, portas: set, ref: str) -> dict:
    criterios = indexar(opcao["criterios"], "id")
    if criterios.keys() != rubrica.keys():
        raise ValueError(f"Critérios incompatíveis em {ref}")
    for criterio, item in criterios.items():
        pontos, trecho, motivo = item["pontos"], item["trecho"], item["motivo"]
        if type(pontos) is not int or pontos not in (0, rubrica[criterio]["pontos"]):
            raise ValueError(f"Pontuação incompatível com a rubrica em {ref}/{criterio}")
        if not isinstance(trecho, str) or trecho not in analise or (pontos and not texto(trecho)):
            raise ValueError(f"Trecho inválido em {ref}/{criterio}")
        if not texto(motivo):
            raise ValueError(f"Motivo ausente em {ref}/{criterio}")
    violacoes = indexar(opcao["portas_fatais"], "regra")
    for regra, item in violacoes.items():
        trecho = item["trecho"]
        if regra not in portas or not texto(trecho) or trecho not in analise:
            raise ValueError(f"Porta fatal ou trecho inválido em {ref}/{regra}")
        if not texto(item["motivo"]):
            raise ValueError(f"Motivo ausente em {ref}/{regra}")
    return {"criterios": criterios, "portas_fatais": violacoes}


def validar_caso(caso: dict, mascara: dict, correcoes: dict) -> tuple[dict, dict, set]:
    caso_id = caso["id"]
    respostas = indexar(caso["opcoes"], "rotulo")
    if (
        respostas.keys() != ROTULOS
        or mascara.keys() != ROTULOS
        or set(mascara.values()) != set(BRACOS)
    ):
        raise ValueError(f"Máscara ou opções incompatíveis em {caso_id}")
    rubrica = indexar(caso["criterios"], "id")
    if not rubrica or any(
        type(item["pontos"]) is not int or item["pontos"] <= 0 for item in rubrica.values()
    ):
        raise ValueError(f"Rubrica vazia ou pontuação inválida em {caso_id}")
    portas = caso["portas_fatais"]
    if (
        not isinstance(portas, list)
        or not all(map(texto, portas))
        or len(set(portas)) != len(portas)
    ):
        raise ValueError(f"Portas fatais inválidas na rubrica de {caso_id}")
    autorizadas = set(portas)

    avaliados = {}
    for corretor, correcao in correcoes.items():
        opcoes = indexar(correcao[caso_id]["opcoes"], "rotulo")
        if opcoes.keys() != ROTULOS:
            raise ValueError(f"Rótulos incorretos em {corretor}/{caso_id}")
        avaliados[corretor] = {}
        for rotulo, opcao in opcoes.items():
            analise = respostas[rotulo]["analise"]
            ref = f"{corretor}/{caso_id}/{rotulo}"
            if not texto(analise):
                raise ValueError(f"Resposta ausente em {ref}")
            avaliados[corretor][mascara[rotulo]] = validar_opcao(
                opcao, analise, rubrica, autorizadas, ref
            )
    return rubrica, avaliados, autorizadas


def comparar(criterios: dict, notas: dict) -> dict:
    comparacoes = {}
    for par in PARES:
        antes, depois = par
        transicao = dict.fromkeys(CLASSE.values(), 0)
        for criterio, item in criterios[antes].items():
            pontos = item["pontos"], criterios[depois][criterio]["pontos"]
            transicao[CLASSE[tuple(map(bool, pontos))]] += 1
        transicao["pontos_delta"] = notas[depois] - notas[antes]
        comparacoes[par] = transicao
    return comparacoes


def consolidar(pacote: dict, chave: dict, correcoes: dict) -> dict:
    original = indexar(pacote["casos"], "id")
    por_corretor = {
        corretor: indexar(correcao["casos"], "id") for corretor, correcao in correcoes.items()
    }
    if (
        not original
        or chave.keys() != original.keys()
        or len(por_corretor) != 2
        or any(casos.keys() != original.keys() for casos in por_corretor.values())
    ):
        raise ValueError("O pacote, a chave e duas correções precisam conter os mesmos casos")

    totais = {
        corretor: {
            "totais": dict.fromkeys(BRACOS, 0),
            "portas_fatais": dict.fromkeys(BRACOS, 0),
            "respostas_com_portas_fatais": dict.fromkeys(BRACOS, 0),
            "transicoes": {
                par: dict.fromkeys((*CLASSE.values(), "pontos_delta"), 0) for par in PARES
            },
        }
        for corretor in por_corretor
    }
    concordancia = {
        "decisoes_iguais": 0,
        "decisoes_total": 0,
        "portas_fatais_iguais": 0,
        "portas_fatais_total": 0,
    }
    casos = []
    primeiro, segundo = por_corretor
    for caso_id, caso in original.items():
        rubrica, avaliacoes, autorizadas = validar_caso(caso, chave[caso_id], por_corretor)
        dado = caso.get("caso", {})
        nome = next(
            filter(
                texto, (caso.get("nome"), caso.get("titulo"), dado.get("nome"), dado.get("titulo"))
            ),
            caso_id,
        )
        linha = {
            "id": caso_id,
            "nome": nome,
            "maximo": sum(item["pontos"] for item in rubrica.values()),
            "notas": {},
            "notas_sem_porta_fatal": {},
            "criterios": {},
            "portas_fatais": {},
            "transicoes": {},
        }
        for corretor, opcoes in avaliacoes.items():
            criterios = {braco: opcoes[braco]["criterios"] for braco in BRACOS}
            violacoes = {braco: opcoes[braco]["portas_fatais"] for braco in BRACOS}
            notas_sem_porta = {
                braco: sum(item["pontos"] for item in criterios[braco].values()) for braco in BRACOS
            }
            notas = {braco: 0 if violacoes[braco] else notas_sem_porta[braco] for braco in BRACOS}
            transicoes = comparar(criterios, notas)
            linha["notas"][corretor] = notas
            linha["notas_sem_porta_fatal"][corretor] = notas_sem_porta
            linha["criterios"][corretor] = criterios
            linha["portas_fatais"][corretor] = violacoes
            linha["transicoes"][corretor] = transicoes
            for braco in BRACOS:
                totais[corretor]["totais"][braco] += notas[braco]
                totais[corretor]["portas_fatais"][braco] += len(violacoes[braco])
                totais[corretor]["respostas_com_portas_fatais"][braco] += bool(violacoes[braco])
            for par, transicao in transicoes.items():
                for tipo, numero in transicao.items():
                    totais[corretor]["transicoes"][par][tipo] += numero
        for braco in BRACOS:
            um, outro = (avaliacoes[corretor][braco] for corretor in (primeiro, segundo))
            concordancia["decisoes_iguais"] += sum(
                um["criterios"][id_]["pontos"] == outro["criterios"][id_]["pontos"]
                for id_ in rubrica
            )
            concordancia["decisoes_total"] += len(rubrica)
            if autorizadas:
                concordancia["portas_fatais_iguais"] += (
                    um["portas_fatais"].keys() == outro["portas_fatais"].keys()
                )
                concordancia["portas_fatais_total"] += 1
        casos.append(linha)
    return {
        "casos": casos,
        "corretores": totais,
        "concordancia": concordancia,
        "maximo": sum(caso["maximo"] for caso in casos),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidencias", type=Path)
    parser.add_argument("resultado", type=Path)
    args = parser.parse_args()
    raiz = args.evidencias
    resultado = consolidar(
        ler(raiz / "casos-para-correcao-cega.json"),
        ler(raiz / "chave-de-mascaramento.json"),
        {i: ler(raiz / f"correcao-cega-{i}.json") for i in ("1", "2")},
    )
    with args.resultado.open("x", encoding="utf-8") as arquivo:
        json.dump(resultado, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


if __name__ == "__main__":
    main()
