"""Confere provas e expõe por índice somente fichas aprovadas no ensaio."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path

CAMPOS_FICHA = {"id", "titulo", "indicio", "checagem", "preservar", "nao_aplicar", "provas"}


def ler(path: Path):
    return json.loads(path.read_bytes())


def texto(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validar(treino: dict, fichas: dict) -> dict:
    fontes = defaultdict(list)
    for fonte in treino["provas_canonicas"]:
        fontes[fonte["id"]].append(fonte["texto"])
        if fonte["natureza"] == "tabelas do caso anterior, transcritas das fontes primárias":
            declaradas = {item["id"] for item in fonte["fontes"]}
            for tabela in json.loads(fonte["texto"]):
                id_fonte = tabela["fonte"]
                recorte = json.dumps([tabela], ensure_ascii=False, indent=2)
                if id_fonte in declaradas and recorte[2:-2] in fonte["texto"]:
                    fontes[id_fonte].append(recorte)
    por_id = {}
    if set(fichas) != {"fichas"} or not 3 <= len(fichas["fichas"]) <= 5:
        raise ValueError("Quantidade ou formato inválido")
    for ficha in fichas["fichas"]:
        id_ = ficha["id"]
        if (
            set(ficha) != CAMPOS_FICHA
            or not isinstance(id_, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,50}", id_)
            or id_ in por_id
            or not all(texto(ficha[k]) for k in CAMPOS_FICHA - {"provas"})
            or len(ficha["indicio"].encode()) > 240
            or sum(len(ficha[k].split()) for k in ("checagem", "preservar", "nao_aplicar")) > 135
        ):
            raise ValueError(f"Formato ou orçamento inválido em {id_}")
        provas = ficha["provas"]
        if not 1 <= len(provas) <= 3:
            raise ValueError(f"Quantidade de provas inválida em {id_}")
        for prova in provas:
            fonte, trecho = prova["fonte"], prova["trecho"]
            if not texto(trecho) or not any(trecho in recorte for recorte in fontes.get(fonte, ())):
                raise ValueError(f"Prova não é trecho literal da fonte em {id_}/{fonte}")
        por_id[id_] = ficha
    return por_id


def selecionar(revisao: dict, sha: str, fichas: dict) -> list[dict]:
    if revisao["fichas_sha256"] != sha:
        raise ValueError("O parecer corresponde a outro lote")
    decisoes = {item["id"]: item for item in revisao["decisoes"]}
    if decisoes.keys() != fichas.keys() or len(decisoes) != len(revisao["decisoes"]):
        raise ValueError("Revisão precisa deliberar cada ficha uma vez")
    for item in decisoes.values():
        if item["decisao"] not in ("aceitar", "rejeitar") or not texto(item["motivo"]):
            raise ValueError(f"Decisão inválida em {item['id']}")
    aprovadas = [ficha for id_, ficha in fichas.items() if decisoes[id_]["decisao"] == "aceitar"]
    if not aprovadas:
        raise ValueError("Nenhuma ficha elegível para o braço com memória")
    return aprovadas


def gravar(path: Path, data: dict) -> str:
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(raw)
    path.chmod(0o444)
    return hashlib.sha256(raw).hexdigest()


def montar(pasta: Path, trilha: str, fichas: list[dict]) -> str:
    destino = pasta / f"wiki-{trilha}"
    if destino.exists():
        raise FileExistsError(destino)
    with tempfile.TemporaryDirectory(dir=pasta) as staging:
        temp = Path(staging) / "wiki"
        temp.mkdir()
        registros = []
        for ficha in fichas:
            id_ = ficha["id"]
            nome = f"{id_}.json"
            visivel = {k: ficha[k] for k in ("id", "checagem", "preservar", "nao_aplicar")}
            sha = gravar(temp / nome, visivel)
            registros.append({k: ficha[k] for k in ("id", "titulo", "indicio")} | {
                "arquivo": nome,
                "sha256": sha,
            })
        hash_indice = gravar(temp / "indice.json", {"fichas": registros})
        temp.rename(destino)
    return hash_indice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pasta", type=Path)
    parser.add_argument("trilha", choices=("risco", "valuation"))
    parser.add_argument("--com-revisao", action="store_true")
    parser.add_argument("--parecer", type=Path)
    args = parser.parse_args()
    trilha, pasta = args.trilha, args.pasta
    fichas_path = pasta / f"fichas-{trilha}.json"
    sha = hashlib.sha256(fichas_path.read_bytes()).hexdigest()
    fichas = validar(ler(pasta / f"insumo-curadoria-{trilha}.json"), ler(fichas_path))
    print(f"{len(fichas)} fichas com provas verificadas. SHA-256 {sha}")
    if args.com_revisao:
        parecer = args.parecer or pasta / f"parecer-fichas-{trilha}.json"
        aprovadas = selecionar(ler(parecer), sha, fichas)
        hash_indice = montar(pasta, trilha, aprovadas)
        print(f"{len(aprovadas)}/{len(fichas)} aceitas. Índice SHA-256 {hash_indice}")


if __name__ == "__main__":
    main()
