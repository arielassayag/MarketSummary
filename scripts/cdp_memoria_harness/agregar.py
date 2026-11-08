"""Agrega a correção cega e confere a igualdade de notas para textos iguais."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import agregar_base as base

POLITICAS = {"risco": "registrar", "valuation": "zerar_caso"}


def consolidar(pacote: dict, chave: dict, correcoes: dict) -> dict:
    originais = base.indexar(pacote["casos"], "id")
    for id_, caso in originais.items():
        politica = POLITICAS.get(caso.get("trilha"))
        if politica is None or politica != caso.get("politica_porta_fatal"):
            raise ValueError(f"Política de porta fatal inválida em {id_}")

    resultado = base.consolidar(pacote, chave, correcoes)
    for caso in resultado["casos"]:
        original = originais[caso["id"]]
        conferir_textos_iguais(caso, original, chave[caso["id"]])
        trilha, politica = original["trilha"], original["politica_porta_fatal"]
        caso.update(trilha=trilha, politica_porta_fatal=politica)
        caso["portas_fatais_detalhes"] = original.get("portas_fatais_detalhes", [])
        if politica == "registrar":
            restaurar_notas(caso, resultado["corretores"])
    return resultado


def conferir_textos_iguais(caso: dict, original: dict, mascara: dict) -> None:
    for corretor, criterios in caso["criterios"].items():
        por_texto = {}
        for opcao in original["opcoes"]:
            braco = mascara[opcao["rotulo"]]
            analise = opcao["analise"]
            julgamento = (
                {id_: item["pontos"] for id_, item in criterios[braco].items()},
                set(caso["portas_fatais"][corretor][braco]),
            )
            if analise in por_texto and por_texto[analise] != julgamento:
                raise ValueError(f"Textos idênticos com julgamentos diferentes em {caso['id']}/{corretor}")
            por_texto[analise] = julgamento


def restaurar_notas(caso: dict, totais: dict) -> None:
    for corretor, notas in caso["notas"].items():
        brutas = caso["notas_sem_porta_fatal"][corretor]
        for braco in base.BRACOS:
            totais[corretor]["totais"][braco] += brutas[braco] - notas[braco]
        for par in base.PARES:
            antes, depois = par
            transicao = caso["transicoes"][corretor][par]
            delta = brutas[depois] - brutas[antes]
            totais[corretor]["transicoes"][par]["pontos_delta"] += delta - transicao["pontos_delta"]
            transicao["pontos_delta"] = delta
        notas.update(brutas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidencias", type=Path)
    parser.add_argument("resultado", type=Path)
    args = parser.parse_args()
    raiz = args.evidencias
    resultado = consolidar(
        base.ler(raiz / "casos-para-correcao-cega.json"),
        base.ler(raiz / "chave-de-mascaramento.json"),
        {i: base.ler(raiz / f"correcao-cega-{i}.json") for i in ("1", "2")},
    )
    with args.resultado.open("x", encoding="utf-8") as arquivo:
        json.dump(resultado, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


if __name__ == "__main__":
    main()
