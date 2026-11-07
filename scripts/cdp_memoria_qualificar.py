#!/usr/bin/env python3
"""Qualifica uma revisão da memória sem alterar as fontes do gabarito congelado."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cdp_memoria_benchmark import (
    _ler_corpus,
    _medir_caso,
    _pares,
    _passagens_limitadas,
    _sha,
    _validar_gabarito,
)

from cdp.memoria import MAX_BYTES_FONTE, Catalogo, Fontes, raiz_repo
from cdp.memoria_avaliacao import K, _atingidos, _medir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revisao", required=True, help="commit do código e do catálogo")
    parser.add_argument("--revisao-fontes", required=True, help="commit canônico do gabarito")
    parser.add_argument("corpora", nargs="+", type=Path)
    args = parser.parse_args()

    raiz = raiz_repo()
    fontes = Fontes(raiz, revisao=args.revisao)
    base = Fontes(raiz, revisao=args.revisao_fontes)
    for caminho in (
        "src/cdp/memoria.py",
        "src/cdp/memoria_busca.py",
        "src/cdp/memoria_avaliacao.py",
        "src/cdp/memoria_linhagem.py",
        "src/cdp/memoria_secoes.py",
        "src/cdp/memoria_selecao.py",
        "scripts/cdp_memoria_benchmark.py",
        "scripts/cdp_memoria_qualificar.py",
    ):
        if (raiz / caminho).read_bytes() != fontes.ler(caminho, 256 * 1024):
            raise ValueError(f"código local diferente da revisão: {caminho}")
    lotes = [(p.stem, *_ler_corpus(p, base.revisao)) for p in args.corpora]
    datas = {lote.data for _, lote, _, _ in lotes}
    consultas = [c for _, lote, _, _ in lotes for c in lote.casos]
    if (len(datas) != 1 or len({c.id for c in consultas}) != len(consultas)
            or len({c.consulta.casefold().strip() for c in consultas}) != len(consultas)):
        raise ValueError("corpora com datas diferentes, IDs repetidos ou consultas duplicadas")

    catalogo = Catalogo(fontes, datas.pop())
    if catalogo.problemas:
        raise ValueError(f"catálogo com ressalvas: {catalogo.problemas}")
    caminhos = {c for lista in catalogo.fontes_por_escopo.values() for c in lista}
    manifesto = {}
    for caminho in sorted(caminhos):
        bruto = fontes.ler(caminho, MAX_BYTES_FONTE)
        if bruto != base.ler(caminho, MAX_BYTES_FONTE):
            raise ValueError(f"a fonte canônica mudou desde o congelamento: {caminho}")
        manifesto[caminho] = _sha(bruto)

    ouro = _validar_gabarito(catalogo, lotes)
    casos = []
    for nome, corpus, familias, _ in lotes:
        for caso in corpus.casos:
            evidencias = ouro[caso.id]
            resultado = _medir_caso(catalogo, caso, evidencias, familias[caso.id], nome)
            if caso.tipo == "evidencia":
                diretas = catalogo.indice.buscar(caso.escopo, caso.consulta, K)
                contextuais = catalogo._recuperar_passagens(caso.escopo, caso.consulta, K, diretas, [])
                prefixo, tamanho = _passagens_limitadas(fontes, contextuais)
                resultado["contextual_sem_notas"] = {
                    **_medir(contextuais, evidencias),
                    "bytes_evidencia": tamanho,
                    "completo_4500b": all(_atingidos(prefixo, evidencias)),
                }
            casos.append(resultado)

    evidencias = [c for c in casos if c["tipo"] == "evidencia"]
    estados = [c["modos"]["memoria"] for c in casos if c["tipo"] == "estado_atual"]
    externos = [c["modos"]["memoria"] for c in casos if c["tipo"] == "fora_escopo"]
    principal = _pares(evidencias, "completo_5")
    estado_ok = sum(e["encaminhou"] and not e["retornou_notas"] for e in estados)
    externo_ok = sum(e["abstencao"] and not e["encaminhou"] for e in externos)
    falsas_orientacoes = sum(c["modos"]["memoria"]["encaminhou"] for c in evidencias)
    print(json.dumps({
        "revisao": fontes.revisao,
        "revisao_fontes": base.revisao,
        "data": catalogo.data.isoformat(),
        "corpora": {nome: sha for nome, _, _, sha in lotes},
        "fontes": manifesto,
        "notas_ativas": len(catalogo.ativos),
        "limite_passagens": K,
        "principal": principal,
        "contextual_sem_notas": sum(c["contextual_sem_notas"]["completo_5"] for c in evidencias),
        "contextual_sem_notas_4500b": sum(c["contextual_sem_notas"]["completo_4500b"] for c in evidencias),
        "sensibilidade": {m: _pares(evidencias, m) for m in ("completo_1", "completo_3", "completo_4500b")},
        "controles": {
            "estado_sem_notas": estado_ok,
            "estado_explicito_sem_contexto": sum(e["explicito_sem_memoria"] for e in estados),
            "estado_n": len(estados),
            "fora_abstencao": externo_ok,
            "fora_n": len(externos),
            "falsas_orientacoes_estaticas": falsas_orientacoes,
        },
        "integral": (principal["memoria"] == len(evidencias) and not falsas_orientacoes
                     and estado_ok == len(estados) and externo_ok == len(externos)),
        "casos": casos,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
