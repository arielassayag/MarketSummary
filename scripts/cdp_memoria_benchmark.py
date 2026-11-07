#!/usr/bin/env python3
"""Compara a busca direta e a híbrida do CDP com corpus externo congelado."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from random import Random
from statistics import fmean

from cdp.memoria import Catalogo, Fontes, Local, _chaves_unicas, raiz_repo
from cdp.memoria_avaliacao import (
    CasoReservado,
    CorpusReservado,
    K,
    _atingidos,
    _grupos,
    _medir,
    _medir_destino,
    _resumo_destinos,
)
from cdp.memoria_busca import BYTES_PASSAGEM, LINHAS_PASSAGEM, _janelas

MODOS = ("direta", "memoria")
TETO_BYTES = 4_500
SEMENTE = 20261107
REAMOSTRAGENS = 10_000
Lote = tuple[str, CorpusReservado, dict[str, str], str]


def _sha(bruto: bytes) -> str:
    return hashlib.sha256(bruto).hexdigest()


def _ler_corpus(arquivo: Path, revisao: str) -> tuple[CorpusReservado, dict[str, str], str]:
    bruto = arquivo.read_bytes()
    dados = json.loads(bruto, object_pairs_hook=_chaves_unicas)
    if dados.pop("revisao_fontes", revisao) != revisao:
        raise ValueError(f"a revisão do corpus diverge da solicitada: {arquivo}")
    familias = {caso["id"]: caso.pop("familia") for caso in dados["casos"]}
    for caso in dados["casos"]:
        caso.pop("expectativa", None)
    if any(not isinstance(f, str) or not f.strip() for f in familias.values()):
        raise ValueError(f"família ausente ou inválida em {arquivo}")
    corpus = CorpusReservado.model_validate_json(json.dumps(dados, ensure_ascii=False))
    return corpus, familias, _sha(bruto)


def _passagens_limitadas(fontes: Fontes, passagens: list[Local]) -> tuple[list[Local], int]:
    if len(passagens) > K:
        raise ValueError("quantidade de passagens fora do orçamento de produção")
    prefixo = []
    bytes_total = 0
    truncado = False
    for passagem in passagens:
        fonte = fontes.linhas(passagem.caminho)
        if not 1 <= passagem.inicio <= passagem.fim <= len(fonte):
            raise ValueError("coordenadas de passagem fora da fonte fixada")
        linhas = fonte[passagem.inicio - 1:passagem.fim]
        trecho = "\n".join(linhas).encode()
        if len(linhas) > LINHAS_PASSAGEM or len(trecho) > BYTES_PASSAGEM:
            raise ValueError("passagem fora do orçamento de produção")
        if _sha(trecho) != passagem.sha256:
            raise ValueError("passagem divergente do Git fixado")
        bytes_total += len(trecho) + int(bytes_total > 0)
        truncado = truncado or bytes_total > TETO_BYTES
        if not truncado:
            prefixo.append(passagem)
    return prefixo, bytes_total


def _validar_gabarito(catalogo: Catalogo, lotes: list[Lote]) -> dict[str, list[list[Local]]]:
    fontes = catalogo.fontes
    grupos_por_id = {}
    janelas_por_caminho: dict[str, list[Local]] = {}
    for _, corpus, _, _ in lotes:
        for caso in corpus.casos:
            grupos = _grupos(fontes, caso)
            for grupo in grupos:
                for ev in grupo:
                    if ev.caminho not in janelas_por_caminho:
                        janelas_por_caminho[ev.caminho] = [
                            Local(ev.caminho, j.inicio, j.inicio + len(j.linhas) - 1, "")
                            for j in _janelas(ev.caminho, fontes.linhas(ev.caminho))
                        ]
                janelas = [j for ev in grupo if ev.caminho in catalogo.fontes_por_escopo[caso.escopo]
                           for j in janelas_por_caminho[ev.caminho]]
                if not _atingidos(janelas, [grupo])[0]:
                    raise ValueError(f"gabarito fora das janelas diretas: {caso.id}")
            grupos_por_id[caso.id] = grupos
    return grupos_por_id


def _componentes(casos: list[dict], ouro: dict[str, list[list[Local]]]) -> list[list[dict]]:
    por_familia = defaultdict(list)
    donos = defaultdict(set)
    for caso in casos:
        chave = caso["familia"]
        por_familia[chave].append(caso)
        for grupo in ouro[caso["id"]]:
            for ev in grupo:
                donos[ev.caminho, ev.sha256].add(chave)

    vizinhos = {f: set() for f in por_familia}
    for familias in donos.values():
        for a, b in combinations(sorted(familias), 2):
            vizinhos[a].add(b)
            vizinhos[b].add(a)

    componentes = []
    while vizinhos:
        pendentes = [min(vizinhos)]
        bloco = []
        while pendentes:
            f = pendentes.pop()
            if f in vizinhos:
                pendentes.extend(sorted(vizinhos.pop(f)))
                bloco.extend(por_familia[f])
        componentes.append(bloco)
    return componentes


def _delta(caso: dict, metrica: str = "completo_5") -> int:
    a, b = (caso["modos"][modo][metrica] for modo in MODOS)
    return int(b) - int(a)


def _pares(casos: list[dict], metrica: str) -> dict:
    ganhos = sorted(c["id"] for c in casos if _delta(c, metrica) == 1)
    perdas = sorted(c["id"] for c in casos if _delta(c, metrica) == -1)
    acertos_a, acertos_b = (sum(c["modos"][m][metrica] for c in casos) for m in MODOS)
    ambos = acertos_a - len(perdas)
    return {
        "n": len(casos), "direta": acertos_a, "memoria": acertos_b,
        "ganhos": ganhos, "perdas": perdas, "ambos": ambos,
        "nenhum": len(casos) - ambos - len(ganhos) - len(perdas),
        "delta_pp": (100 * (acertos_b - acertos_a) / len(casos) if casos else None),
    }


def _incerteza(baterias: list[list[list[dict]]]) -> dict:
    blocos = [[(sum(map(_delta, bloco)), len(bloco)) for bloco in bateria]
              for bateria in baterias]
    pares = [par for bateria in blocos for par in bateria]
    saldo, n = map(sum, zip(*pares, strict=True))
    sem_um = [100 * (saldo - d) / (n - qtd) for d, qtd in pares if n > qtd]
    rng = Random(SEMENTE)
    amostras = []
    for _ in range(REAMOSTRAGENS):
        reamostra = [par for bateria in blocos for par in rng.choices(bateria, k=len(bateria))]
        d, qtd = map(sum, zip(*reamostra, strict=True))
        amostras.append(100 * d / qtd)
    amostras.sort()
    return {
        "blocos_por_bateria": [len(b) for b in blocos],
        "bootstrap_95_pp": [amostras[249], amostras[9749]],
        "sem_um_bloco_pp": [min(sem_um), max(sem_um)] if sem_um else None,
    }


def _medir_caso(catalogo: Catalogo, caso: CasoReservado, ouro: list[list[Local]], familia: str,
                bateria: str) -> dict:
    ancoras = [p for reg in catalogo.ativos if caso.escopo in reg.nota.escopos
               for p, ev in zip(reg.locais, reg.nota.evidencias, strict=True)
               if p.fim - p.inicio + 1 <= LINHAS_PASSAGEM
               and len(ev.trecho.encode()) <= BYTES_PASSAGEM]
    grupos_cobertos = sum(_atingidos(ancoras, ouro))
    direta = catalogo.indice.buscar(caso.escopo, caso.consulta, K)
    hibrida = catalogo.buscar(caso.escopo, caso.consulta, K)
    memoria = [Local(**p) for p in hibrida["passagens"]]
    modos = {
        "direta": _medir(direta, ouro),
        "memoria": _medir(memoria, ouro, encaminhou=bool(hibrida["orientacao_atual"]),
                           notas=bool(hibrida["notas"])) | _medir_destino(caso, hibrida),
    }
    for modo, passagens in zip(MODOS, (direta, memoria), strict=True):
        prefixo, tamanho = _passagens_limitadas(catalogo.fontes, passagens)
        modos[modo]["bytes_evidencia"] = tamanho
        modos[modo]["completo_4500b"] = all(_atingidos(prefixo, ouro)) if ouro else None
        modos[modo]["grupos_atingidos"] = _atingidos(passagens, ouro)
    if caso.tipo == "estado_atual":
        explicita = catalogo.buscar(caso.escopo, caso.consulta, K, estado_atual=True)
        modos["memoria"]["explicito_sem_memoria"] = bool(explicita["orientacao_atual"]) and not (
            explicita["notas"] or explicita["passagens"]
        )
        if caso.destinos_aceitos is not None:
            modos["memoria"]["destino_explicito"] = _medir_destino(caso, explicita)
    return {
        "id": caso.id, "bateria": bateria, "familia": familia, "escopo": caso.escopo,
        "consulta": caso.consulta, "tipo": caso.tipo, "grupos": len(ouro),
        "grupos_cobertos_catalogo": grupos_cobertos, "modos": modos,
        "gabarito": [[e.json() for e in grupo] for grupo in ouro],
        **({"destinos_aceitos": caso.destinos_aceitos} if caso.destinos_aceitos is not None else {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revisao", required=True, help="commit completo do código e do acervo")
    parser.add_argument("corpora", nargs="+", type=Path, help="baterias JSON congeladas")
    args = parser.parse_args()
    fontes = Fontes(raiz_repo(), revisao=args.revisao)
    for arquivo in (
        "memoria", "memoria_busca", "memoria_avaliacao", "memoria_linhagem", "memoria_secoes",
        "memoria_selecao", "memoria_reforcos",
    ):
        caminho = f"src/cdp/{arquivo}.py"
        if (fontes.raiz / caminho).read_bytes() != fontes.ler(caminho, 256 * 1024):
            raise ValueError(f"o código local diverge da revisão: {caminho}")

    lotes = [(p.stem, *_ler_corpus(p, fontes.revisao)) for p in args.corpora]
    datas = {corpus.data for _, corpus, _, _ in lotes}
    consultas = [c for _, corpus, _, _ in lotes for c in corpus.casos]
    if len(lotes) < 2 or len({nome for nome, *_ in lotes}) != len(lotes) or len(datas) != 1:
        raise ValueError("informe ao menos duas baterias distintas com a mesma data")
    if (len({c.id for c in consultas}) != len(consultas)
            or len({c.consulta.casefold().strip() for c in consultas}) != len(consultas)):
        raise ValueError("ID ou consulta duplicada entre baterias")

    catalogo = Catalogo(fontes, datas.pop())
    if catalogo.problemas:
        raise ValueError("catálogo com ressalvas")
    ouro = _validar_gabarito(catalogo, lotes)
    manifesto_fontes = {
        caminho: _sha(fontes.ler(caminho, 1024 * 1024))
        for caminho in sorted({p for caminhos in catalogo.fontes_por_escopo.values()
                               for p in caminhos})
    }
    casos = [_medir_caso(catalogo, caso, ouro[caso.id], familias[caso.id], nome)
             for nome, corpus, familias, _ in lotes for caso in corpus.casos]
    positivos = [c for c in casos if c["tipo"] == "evidencia"]
    estados = [c["modos"]["memoria"] for c in casos if c["tipo"] == "estado_atual"]
    fora = [c for c in casos if c["tipo"] == "fora_escopo"]
    por_bateria = {nome: [c for c in positivos if c["bateria"] == nome]
                   for nome, *_ in lotes}
    if any(not bloco for bloco in por_bateria.values()):
        raise ValueError("cada bateria precisa de perguntas de evidência")
    principal = _pares(positivos, "completo_5")
    baterias = {nome: _pares(c, "completo_5") for nome, c in por_bateria.items()}
    destinos = _resumo_destinos(estados)
    resultado = {
        "revisao": fontes.revisao, "data": catalogo.data.isoformat(),
        "corpora": {nome: sha for nome, _, _, sha in lotes},
        "fontes": manifesto_fontes, "fontes_por_escopo": catalogo.fontes_por_escopo,
        "notas_ativas": {r.nota.id: _sha(catalogo.fontes.ler(
            f"docs/cdp/memoria/notas/{r.nota.id}.json", 16384)) for r in catalogo.ativos},
        "limite_passagens": K, "limite_sensibilidade_bytes": TETO_BYTES,
        "principal": principal, "por_bateria": baterias,
        "criterio_principal_atingido": (principal["delta_pp"] >= 5
                                        and all(b["delta_pp"] > 0 for b in baterias.values())),
        "incerteza": _incerteza([_componentes(c, ouro) for c in por_bateria.values()]),
        "sensibilidade": {m: _pares(positivos, m)
                           for m in ("completo_1", "completo_3", "completo_4500b")},
        "cobertura_media_grupos_5": {m: fmean(c["modos"][m]["cobertura_5"] for c in positivos)
                                    for m in MODOS},
        "por_cobertura_catalogo": {chave: _pares([
            c for c in positivos if bool(c["grupos_cobertos_catalogo"]) == coberta
        ], "completo_5") for chave, coberta in (("com_ancora", True), ("sem_ancora", False))},
        "controles": {
            "estado_n": len(estados), "fora_n": len(fora),
            "estado_automatico": sum(e["encaminhou"] for e in estados),
            "estado_explicito_sem_memoria": sum(e["explicito_sem_memoria"] for e in estados),
            "estado_com_notas": sum(e["retornou_notas"] for e in estados),
            "estaticas_encaminhadas": sum(c["modos"]["memoria"]["encaminhou"] for c in positivos),
            "fora_abstencao": {m: sum(c["modos"][m]["abstencao"] for c in fora) for m in MODOS},
            **destinos,
            **({"estado_destinos_explicitos": _resumo_destinos(
                [e.get("destino_explicito", {}) for e in estados]
            )} if destinos else {}),
        },
        "casos": casos,
    }
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
