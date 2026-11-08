"""Confere o plano de perguntas e o vínculo com as mudanças propostas."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from remendos import decodificar, hash_bytes, indexar, ler, texto

ESTADOS = {"coberta", "lacuna", "sem_prova"}
PERGUNTAS = {f"q{i}" for i in range(1, 6)}
PROPOSTAS = {"p1", "p2", "p3"}


def validar(casos, referencia, perguntas, propostas, indice, braco, sha_perguntas):
    if set(perguntas) != {"casos"} or set(propostas) != {"perguntas_sha256", "casos"}:
        raise ValueError("Estrutura externa do plano ou das propostas incompatível")
    if propostas["perguntas_sha256"] != sha_perguntas:
        raise ValueError("As propostas apontam para outro plano")
    ids = indexar(casos["casos"])
    base, plano, saida = (indexar(p["casos"]) for p in (referencia, perguntas, propostas))
    if any(x.keys() != ids.keys() for x in (base, plano, saida)):
        raise ValueError("Casos incompatíveis entre entradas")
    fichas_validas = {i["id"] for i in indice["fichas"]} if braco == "C" else set()
    resumo = {}
    for id_, item in plano.items():
        final = saida[id_]
        if set(item) != {"id", "fichas_lidas", "perguntas"} or set(final) != {
            "id", "fichas_lidas", "propostas", "ligacoes",
        }:
            raise ValueError(f"Campos incompatíveis em {id_}")
        fichas = item["fichas_lidas"]
        if (
            not isinstance(fichas, list)
            or not all(isinstance(f, str) for f in fichas)
            or len(fichas) != len(set(fichas))
            or len(fichas) > 3
            or not set(fichas) <= fichas_validas
            or final["fichas_lidas"] != fichas
        ):
            raise ValueError(f"Seleção de fichas incompatível em {id_}")
        por_pergunta = indexar(item["perguntas"])
        if por_pergunta.keys() != PERGUNTAS:
            raise ValueError(f"Esperadas exatamente cinco perguntas em {id_}")
        for pergunta in por_pergunta.values():
            if set(pergunta) != {"id", "pergunta", "estado", "motivo"}:
                raise ValueError(f"Campos de pergunta incompatíveis em {id_}")
            texto(pergunta["pergunta"], 260)
            texto(pergunta["motivo"], 400)
            if pergunta["estado"] not in ESTADOS:
                raise ValueError(f"Estado de pergunta inválido em {id_}")
        por_proposta = indexar(final["propostas"])
        ligacoes = final["ligacoes"]
        if (
            not isinstance(ligacoes, dict)
            or por_proposta.keys() - PROPOSTAS
            or ligacoes.keys() != por_proposta.keys()
        ):
            raise ValueError(f"Vínculos incompatíveis em {id_}")
        for ref in ligacoes.values():
            if ref not in por_pergunta or por_pergunta[ref]["estado"] == "coberta":
                raise ValueError(f"Proposta sem lacuna correspondente em {id_}")
        resumo[id_] = {
            "estados": dict(Counter(q["estado"] for q in por_pergunta.values())),
            "fichas": fichas,
            "propostas": len(por_proposta),
            "lacunas_com_proposta": len(set(ligacoes.values())),
        }
    return resumo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pasta", type=Path)
    parser.add_argument("trilha", choices=("risco", "valuation"))
    parser.add_argument("braco", choices=("B", "C"))
    args = parser.parse_args()
    raiz, trilha, braco = args.pasta, args.trilha, args.braco
    plano = (raiz / f"perguntas-{trilha}-{braco}.json").read_bytes()
    propostas = (raiz / f"propostas-{trilha}-{braco}.json").read_bytes()
    sha = hash_bytes(plano)
    indice = ler(raiz / f"wiki-{trilha}/indice.json") if braco == "C" else {"fichas": []}
    resumo = validar(
        ler(raiz / f"casos-{trilha}.json"), ler(raiz / f"referencia-{trilha}.json"),
        decodificar(plano), decodificar(propostas), indice, braco, sha,
    )
    print(json.dumps({
        "perguntas_sha256": sha, "propostas_sha256": hash_bytes(propostas), "casos": resumo,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
