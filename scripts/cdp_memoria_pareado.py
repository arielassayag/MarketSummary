#!/usr/bin/env python3
"""Prepara e mede a ablação pareada das notas curadas com leitores equivalentes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import copy
from math import comb
from pathlib import Path
from random import Random

from cdp_memoria_benchmark import SEMENTE, _componentes, _incerteza, _medir_caso, _pares, _sha
from cdp_memoria_guiada_avaliar import (
    _carregar,
    _diretorio,
    _gravar_exclusivo,
    _json_bytes,
    _medir_guiada,
    _resumir,
)

from cdp.memoria import MAX_BYTES_FONTE, MemoriaErro, _chaves_unicas, raiz_repo
from cdp.memoria_avaliacao import K
from cdp.memoria_selecao import preparar

_MODOS = ("sem_notas", "com_notas")
_TAMANHO_LOTE = 8
_CANDIDATAS = 16


def _pacotes(catalogo, entradas, meta):
    sem_notas = copy(catalogo)
    sem_notas.ativos = []
    rng = Random(SEMENTE)
    vinculos = []
    pacotes = {}
    for modo, acervo in zip(_MODOS, (sem_notas, catalogo), strict=True):
        ordem = list(entradas)
        rng.shuffle(ordem)
        for i, (_, _, caso, _) in enumerate(ordem):
            opaco = _sha(f"{SEMENTE}:{modo}:{caso.id}".encode())[:12]
            lote = f"sessao-{2 * (i // _TAMANHO_LOTE) + _MODOS.index(modo):02}"
            pacote = preparar(acervo, caso.escopo, caso.consulta, K, explorar_fontes=True)
            publico = {
                k: pacote[k] for k in
                ("consulta", "escopo", "limite", "orcamento_bytes", "fontes_permitidas")
            }
            publico["candidatas"] = [
                {k: p[k] for k in ("caminho", "inicio", "fim", "trecho")}
                for p in pacote["candidatas"][:_CANDIDATAS]
            ]
            bruto = _json_bytes(publico)
            vinculos.append({"id": caso.id, "modo": modo, "lote": lote, "opaco": opaco,
                             "sha256": _sha(bruto), "lacre": pacote["lacre"]})
            pacotes[opaco] = (pacote, bruto)
    return pacotes, {**meta, "vinculos": vinculos, "candidatas_maximas": _CANDIDATAS}


def _preparar(diretorio, catalogo, manifesto, pacotes):
    diretorio.mkdir(mode=0o700)
    _gravar_exclusivo(diretorio / "manifesto.json", _json_bytes(manifesto))
    for v in manifesto["vinculos"]:
        lote = diretorio / v["lote"]
        (lote / "pacotes").mkdir(mode=0o700, parents=True, exist_ok=True)
        pacote, publico = pacotes[v["opaco"]]
        _gravar_exclusivo(lote / "pacotes" / (v["opaco"] + ".json"), publico)
        for caminho in pacote["fontes_permitidas"]:
            destino = lote / "fontes" / caminho
            if not destino.exists():
                destino.parent.mkdir(parents=True, exist_ok=True)
                _gravar_exclusivo(destino, catalogo.fontes.ler(caminho, MAX_BYTES_FONTE))


def _ler_respostas(arquivo):
    bruto = arquivo.read_bytes()
    dados = json.loads(bruto, object_pairs_hook=_chaves_unicas)
    if not isinstance(dados, dict) or set(dados) != {"respostas"} or not isinstance(dados["respostas"], list):
        raise ValueError("cada sessão entrega uma lista de respostas")
    saida = {}
    for resposta in dados["respostas"]:
        if not isinstance(resposta, dict) or not isinstance(resposta.get("id"), str):
            raise ValueError("resposta sem ID")
        opaco = resposta.pop("id")
        if opaco in saida:
            saida[opaco] = None
        else:
            saida[opaco] = resposta
    return saida, _sha(bruto)


def _falha(erro):
    return dict.fromkeys(("completo_1", "completo_3", "completo_5", "completo_4500b",
                          "encaminhou", "abstencao", "retornou_notas"), False) | {
        "grupos_atingidos": [], "erro": erro, "passagens": [], "bytes_evidencia": 0,
    }


def _medir_resposta(catalogo, caso, pacote, resposta, ouro):
    if not isinstance(resposta, dict) or set(resposta) != {"intencao", "recortes"}:
        return _falha("resposta ausente, duplicada ou com campos inválidos")
    if resposta["intencao"] not in ("evidencia", "estado_atual", "fora_escopo"):
        return _falha("intenção inválida")
    try:
        return _medir_guiada(catalogo, pacote, {**resposta, "lacre": pacote["lacre"], "ids": []},
                             ouro, caso) | {"intencao": resposta["intencao"]}
    except (MemoriaErro, ValueError) as exc:
        return _falha(str(exc))


def _par(casos, ouro, a, b):
    metrica = "completo_4500b"
    dados = [{**c, "modos": {"direta": c["modos"][a], "memoria": c["modos"][b]}} for c in casos]
    placar = _pares(dados, metrica)
    placar[a], placar[b] = placar.pop("direta"), placar.pop("memoria")
    ganhos, perdas = len(placar["ganhos"]), len(placar["perdas"])
    n = ganhos + perdas
    placar["p_mcnemar_bilateral"] = min(1.0, 2 * sum(comb(n, i) for i in
                                                    range(min(ganhos, perdas) + 1)) / 2**n)
    blocos = _componentes(dados, ouro)
    # A estatística já existente usa a chave completo_5 para o bootstrap.
    for c in dados:
        c["modos"] = {m: {"completo_5": d[metrica]} for m, d in c["modos"].items()}
    placar.update(_incerteza([blocos]))
    saldos = [sum(int(c["modos"]["memoria"]["completo_5"]) -
                  int(c["modos"]["direta"]["completo_5"]) for c in bloco) for bloco in blocos]
    distribuicao = Counter({0: 1})
    for saldo in saldos:
        proxima = Counter()
        for resultado, frequencia in distribuicao.items():
            proxima[resultado + saldo] += frequencia
            proxima[resultado - saldo] += frequencia
        distribuicao = proxima
    placar["p_permutacao_blocos_bilateral"] = sum(
        f for total, f in distribuicao.items() if abs(total) >= abs(sum(saldos))
    ) / 2**len(blocos)
    return placar


def _medir(diretorio, catalogo, ouro, entradas, manifesto, pacotes, pasta_respostas):
    if (diretorio / "manifesto.json").read_bytes() != _json_bytes(manifesto):
        raise ValueError("manifesto divergente do protocolo fixado")
    casos = {caso.id: (caso, _medir_caso(catalogo, caso, ouro[caso.id], familia, nome))
             for nome, familia, caso, _ in entradas}
    respostas, hashes = {}, {}
    for lote in sorted({v["lote"] for v in manifesto["vinculos"]}):
        arquivo = pasta_respostas / (lote + ".json")
        try:
            respostas[lote], hashes[lote] = _ler_respostas(arquivo)
        except (OSError, ValueError) as exc:
            respostas[lote], hashes[lote] = {}, {"erro": str(exc)}
    for v in manifesto["vinculos"]:
        opaco, lote = v["opaco"], v["lote"]
        pacote, publico = pacotes[opaco]
        raiz = diretorio / lote
        if (raiz / "pacotes" / (opaco + ".json")).read_bytes() != publico:
            raise ValueError(f"pacote alterado: {opaco}")
        for caminho in pacote["fontes_permitidas"]:
            if _sha((raiz / "fontes" / caminho).read_bytes()) != manifesto["fontes"][caminho]:
                raise ValueError(f"fonte copiada divergente: {caminho}")
        caso, registro = casos[v["id"]]
        registro["modos"][v["modo"]] = _medir_resposta(
            catalogo, caso, pacote, respostas[lote].get(opaco), ouro[caso.id]
        )
    registros = [registro for _, registro in casos.values()]
    resumo = {}
    for modo in ("direta", "memoria", *_MODOS):
        ajustados = [{**c, "modos": {**c["modos"], "guiada": c["modos"][modo]}} for c in registros]
        resumo[modo] = _resumir(ajustados)["modos"]["guiada"]
        resumo[modo]["falhas_de_entrega"] = sum("erro" in c["modos"][modo] for c in registros)
    positivos = [c for c in registros if c["tipo"] == "evidencia"]
    return {
        "manifesto_sha256": _sha(_json_bytes(manifesto)), "respostas_sha256": hashes,
        "modos": resumo, "principal": _par(positivos, ouro, *_MODOS),
        "secundarios": {
            modo: _par(positivos, ouro, modo, "com_notas") for modo in ("direta", "memoria")
        }, "casos": registros,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", choices=("preparar", "medir"))
    parser.add_argument("--revisao", required=True)
    parser.add_argument("--revisao-fontes", required=True)
    parser.add_argument("--diretorio", required=True, type=Path)
    parser.add_argument("--respostas", type=Path)
    parser.add_argument("corpora", nargs="+", type=Path)
    args = parser.parse_args()
    args.explorar_fontes = True
    raiz = raiz_repo()
    diretorio = _diretorio(raiz, args.diretorio)
    catalogo, ouro, entradas, meta = _carregar(args, raiz)
    caminho = "scripts/cdp_memoria_pareado.py"
    if (raiz / caminho).read_bytes() != catalogo.fontes.ler(caminho, 256 * 1024):
        raise ValueError(f"código local diferente da revisão: {caminho}")
    pacotes, manifesto = _pacotes(catalogo, entradas, meta)
    if args.acao == "preparar":
        _preparar(diretorio, catalogo, manifesto, pacotes)
        print(_sha(_json_bytes(manifesto)))
    else:
        if args.respostas is None:
            parser.error("medir exige --respostas")
        resultado = _medir(diretorio, catalogo, ouro, entradas, manifesto, pacotes, args.respostas)
        bruto = _json_bytes(resultado)
        _gravar_exclusivo(diretorio / "resultado.json", bruto)
        print(_json_bytes({k: v for k, v in resultado.items() if k != "casos"}).decode(), end="")


if __name__ == "__main__":
    main()
