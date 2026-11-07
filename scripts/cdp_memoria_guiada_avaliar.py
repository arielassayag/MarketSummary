#!/usr/bin/env python3
"""Prepara pacotes opacos e mede seleções lacradas na revisão fixada."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from cdp_memoria_benchmark import (
    TETO_BYTES,
    _ler_corpus,
    _medir_caso,
    _pares,
    _passagens_limitadas,
    _sha,
    _validar_gabarito,
)

from cdp.memoria import MAX_BYTES_FONTE, Catalogo, Fontes, Local, _chaves_unicas, raiz_repo
from cdp.memoria_avaliacao import (
    CasoReservado,
    K,
    _atingidos,
    _medir,
    _medir_destino,
    _resumo_destinos,
)
from cdp.memoria_selecao import MAX_BYTES_RESPOSTA, _tem_contexto, aplicar, preparar

_CODIGO = (
    "src/cdp/memoria.py",
    "src/cdp/memoria_busca.py",
    "src/cdp/memoria_avaliacao.py",
    "src/cdp/memoria_linhagem.py",
    "src/cdp/memoria_reforcos.py",
    "src/cdp/memoria_secoes.py",
    "src/cdp/memoria_selecao.py",
    "scripts/cdp_memoria_benchmark.py",
    "scripts/cdp_memoria_guiada_avaliar.py",
    "scripts/cdp_memoria_auditar_guiada.py",
)
_CAMPOS_PUBLICOS = ("versao", "revisao", "data", "consulta", "escopo", "limite",
                    "orcamento_bytes", "candidatas", "lacre")
_MODOS = ("direta", "memoria", "guiada")
_Entrada = tuple[str, str, CasoReservado, str]


def _json_bytes(objeto: object) -> bytes:
    return (json.dumps(objeto, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n").encode()


def _gravar_exclusivo(arquivo: Path, bruto: bytes) -> None:
    fd = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as saida:
        saida.write(bruto)


def _arquivo_regular(arquivo: Path) -> None:
    if arquivo.is_symlink() or not arquivo.is_file():
        raise ValueError(f"esperado arquivo regular: {arquivo}")


def _diretorio(raiz: Path, caminho: Path) -> Path:
    if caminho.is_symlink():
        raise ValueError("o diretório da avaliação não pode ser um link")
    destino = caminho.resolve()
    if destino.is_relative_to(raiz) and not destino.is_relative_to(raiz / "outputs"):
        raise ValueError("use diretório descartável fora do repositório ou em outputs")
    return destino


def _carregar(args: argparse.Namespace, raiz: Path) -> tuple[
        Catalogo, dict[str, list[list[Local]]], list[_Entrada], dict]:
    fontes = Fontes(raiz, revisao=args.revisao)
    base = Fontes(raiz, revisao=args.revisao_fontes)
    for caminho in _CODIGO:
        if (raiz / caminho).read_bytes() != fontes.ler(caminho, 256 * 1024):
            raise ValueError(f"código local diferente da revisão: {caminho}")

    lotes = [(p.stem, *_ler_corpus(p, base.revisao)) for p in args.corpora]
    datas = {lote.data for _, lote, _, _ in lotes}
    consultas = [c for _, lote, _, _ in lotes for c in lote.casos]
    if (len(datas) != 1 or len({nome for nome, *_ in lotes}) != len(lotes)
            or len({c.id for c in consultas}) != len(consultas)
            or len({c.consulta.casefold().strip() for c in consultas}) != len(consultas)):
        raise ValueError("corpora com datas diferentes, nomes, IDs ou consultas duplicados")

    catalogo = Catalogo(fontes, datas.pop())
    if catalogo.problemas:
        raise ValueError("catálogo com ressalvas")
    caminhos = {p for caminhos in catalogo.fontes_por_escopo.values() for p in caminhos}
    hashes_fontes = {}
    for caminho in sorted(caminhos):
        bruto = fontes.ler(caminho, MAX_BYTES_FONTE)
        if bruto != base.ler(caminho, MAX_BYTES_FONTE):
            raise ValueError(f"a fonte canônica mudou desde o congelamento: {caminho}")
        hashes_fontes[caminho] = _sha(bruto)
    ouro = _validar_gabarito(catalogo, lotes)

    entradas = [(nome, familias[caso.id], caso, hash_corpus)
                for nome, corpus, familias, hash_corpus in lotes for caso in corpus.casos]
    # A ordem pública não revela a ordem do gabarito e é reproduzível.
    entradas.sort(key=lambda e: (_sha(f"{fontes.revisao}:{e[3]}:{e[2].id}".encode()), e[2].id))
    metadados = {
        "versao": 1, "revisao": fontes.revisao, "revisao_fontes": base.revisao,
        "data": catalogo.data.isoformat(), "limite_passagens": K, "orcamento_bytes": TETO_BYTES,
        "corpora": {nome: digest for nome, _, _, digest in lotes}, "fontes": hashes_fontes,
    }
    if args.explorar_fontes:
        metadados["explorar_fontes"] = True
    return catalogo, ouro, entradas, metadados


def _referencia(item: dict) -> tuple[str, int, int, str]:
    return item["caminho"], item["inicio"], item["fim"], item["sha256"]


def _pacote(catalogo: Catalogo, entrada: _Entrada, opaco: str, *,
            explorar_fontes: bool = False) -> tuple[dict, bytes, dict]:
    nome, familia, caso, _ = entrada
    if explorar_fontes:
        pacote = preparar(catalogo, caso.escopo, caso.consulta, K, explorar_fontes=True)
    else:
        pacote = preparar(catalogo, caso.escopo, caso.consulta, K)
    ids = {_referencia(p): p["id"] for p in pacote["candidatas"]}
    partida = [ids[ref] for p in pacote["base"]["passagens"] if (ref := _referencia(p)) in ids]
    campos = {**{k: pacote[k] for k in _CAMPOS_PUBLICOS}, "partida": partida}
    if explorar_fontes:
        base = pacote["base"]
        rota = "estado_atual" if base["orientacao_atual"] else (
            "evidencia" if _tem_contexto(base) else "fora_escopo"
        )
        campos.update(fontes_permitidas=pacote["fontes_permitidas"], rota_sugerida=rota,
                      destinos_permitidos=pacote["destinos_permitidos"])
    publico = _json_bytes(campos)
    vinculo = {"opaco": opaco, "id": caso.id, "bateria": nome, "familia": familia,
               "sha256_pacote": _sha(publico), "lacre": pacote["lacre"]}
    return pacote, publico, vinculo


def _preparar(diretorio: Path, catalogo: Catalogo, entradas: list[_Entrada], metadados: dict) -> dict:
    diretorio.mkdir(mode=0o700)
    pacotes, privado = diretorio / "pacotes", diretorio / "privado"
    pacotes.mkdir(mode=0o700)
    privado.mkdir(mode=0o700)
    vinculos = []
    for i, entrada in enumerate(entradas, 1):
        opaco = f"{i:04d}"
        _, publico, vinculo = _pacote(catalogo, entrada, opaco,
                                     explorar_fontes=metadados.get("explorar_fontes", False))
        _gravar_exclusivo(pacotes / f"{opaco}.json", publico)
        vinculos.append(vinculo)
    bruto = _json_bytes({**metadados, "pacotes": vinculos})
    _gravar_exclusivo(privado / "manifesto.json", bruto)
    return {"pacotes": len(vinculos), "diretorio_pacotes": str(pacotes),
            "sha256_manifesto": _sha(bruto)}


def _respostas(arquivo: Path, digest: str, diretorio: Path, ids: set[str]) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("informe o SHA-256 completo das respostas")
    _arquivo_regular(arquivo)
    if arquivo.resolve().is_relative_to(diretorio):
        raise ValueError("mantenha as respostas fora da pasta da avaliação")
    limite = (MAX_BYTES_RESPOSTA + 64) * len(ids) + 2
    with arquivo.open("rb") as entrada:
        bruto = entrada.read(limite + 1)
    if len(bruto) > limite or _sha(bruto) != digest:
        raise ValueError("o SHA-256 das respostas diverge ou o arquivo excede o limite")
    respostas = json.loads(bruto.decode(), object_pairs_hook=_chaves_unicas)
    if not isinstance(respostas, dict) or respostas.keys() != ids:
        raise ValueError("as respostas precisam cobrir exatamente os IDs opacos do manifesto")
    return respostas


def _medir_guiada(catalogo: Catalogo, pacote: dict, resposta: object, ouro: list[list[Local]],
                  caso: CasoReservado) -> dict:
    saida = aplicar(pacote, _json_bytes(resposta), ler=catalogo.fontes.linhas)
    passagens = [Local(**p) for p in saida["passagens"]]
    prefixo, tamanho = _passagens_limitadas(catalogo.fontes, passagens)
    if tamanho > TETO_BYTES:
        raise ValueError("a seleção excede o orçamento comum")
    return {
        **_medir(passagens, ouro, encaminhou=bool(saida["orientacao_atual"]), notas=bool(saida["notas"])),
        "bytes_evidencia": tamanho, "completo_4500b": all(_atingidos(prefixo, ouro)) if ouro else None,
        "grupos_atingidos": _atingidos(passagens, ouro),
        **({"intencao": resposta["intencao"]} if resposta.get("intencao") else {}),
        **_medir_destino(caso, saida),
    }


def _resumir(casos: list[dict]) -> dict:
    evidencias = [c for c in casos if c["tipo"] == "evidencia"]
    estados = [c for c in casos if c["tipo"] == "estado_atual"]
    externos = [c for c in casos if c["tipo"] == "fora_escopo"]
    n_destinos = sum("destinos_aceitos" in c for c in estados)
    modos = {}
    for modo in _MODOS:
        est = [c["modos"][modo] for c in estados]
        ext = [c["modos"][modo] for c in externos]
        positivos = [c["modos"][modo] for c in evidencias]
        destinos = _resumo_destinos(est)
        if n_destinos and modo != "direta":
            destinos = {"estado_destino_aceito": 0, "estado_destino_correto_sem_contexto": 0,
                        **destinos, "estado_destino_n": n_destinos}
        modos[modo] = {
            "n_evidencia": len(evidencias),
            **{m: sum(x[m] for x in positivos)
               for m in ("completo_1", "completo_3", "completo_5", "completo_4500b")},
            "grupos_atingidos": sum(sum(x["grupos_atingidos"]) for x in positivos),
            "grupos_total": sum(c["grupos"] for c in evidencias),
            "estado_encaminhado_sem_notas": sum(x["encaminhou"] and not x["retornou_notas"] for x in est),
            "estado_encaminhado_sem_contexto": sum(x["encaminhou"] and x["abstencao"] for x in est),
            "estado_n": len(est),
            "fora_abstencao": sum(x["abstencao"] and not x["encaminhou"]
                                  and x.get("intencao", "fora_escopo") == "fora_escopo" for x in ext),
            "fora_n": len(ext),
            "falsas_orientacoes_estaticas": sum(x["encaminhou"] for x in positivos),
            **destinos,
        }
    pares = {}
    comparaveis = [
        {"id": c["id"], "modos": {"direta": c["modos"]["memoria"], "memoria": c["modos"]["guiada"]}}
        for c in evidencias
    ]
    for metrica in ("completo_5", "completo_4500b"):
        par = _pares(comparaveis, metrica)
        par["guiada"], par["automatica"] = par.pop("memoria"), par.pop("direta")
        pares[metrica] = par
    guiada = modos["guiada"]
    return {"modos": modos, "guiada_vs_automatica": pares,
            "integral": (guiada["completo_4500b"] == len(evidencias)
                         and not guiada["falsas_orientacoes_estaticas"]
                         and guiada["estado_encaminhado_sem_contexto"] == len(estados)
                         and guiada.get("estado_destino_correto_sem_contexto", 0) == n_destinos
                         and guiada["fora_abstencao"] == len(externos))}


def _medir_ensaio(diretorio: Path, catalogo: Catalogo, ouro: dict[str, list[list[Local]]],
                   entradas: list[_Entrada], metadados: dict, arquivo: Path, digest: str) -> dict:
    pacotes, privado = diretorio / "pacotes", diretorio / "privado"
    if any(p.is_symlink() or not p.is_dir() for p in (pacotes, privado)):
        raise ValueError("pacotes e privado precisam ser diretórios regulares da avaliação")
    ids = {f"{i:04d}" for i in range(1, len(entradas) + 1)}
    if ({p.name for p in diretorio.iterdir()} != {"pacotes", "privado"}
            or {p.name for p in pacotes.iterdir()} != {f"{i}.json" for i in ids}
            or {p.name for p in privado.iterdir()} != {"manifesto.json"}):
        raise ValueError("arquivos inesperados, faltantes ou resultado já existente")
    manifesto = privado / "manifesto.json"
    _arquivo_regular(manifesto)
    respostas = _respostas(arquivo, digest, diretorio, ids)
    vinculos = []
    casos = []
    for i, entrada in enumerate(entradas, 1):
        opaco = f"{i:04d}"
        pacote, publico, vinculo = _pacote(catalogo, entrada, opaco,
                                          explorar_fontes=metadados.get("explorar_fontes", False))
        p = pacotes / f"{opaco}.json"
        _arquivo_regular(p)
        if p.read_bytes() != publico:
            raise ValueError(f"pacote público alterado: {opaco}")
        vinculos.append(vinculo)
        nome, familia, caso, _ = entrada
        evidencias = ouro[caso.id]
        resultado = _medir_caso(catalogo, caso, evidencias, familia, nome)
        resultado["opaco"] = opaco
        resultado["modos"]["guiada"] = _medir_guiada(catalogo, pacote, respostas[opaco], evidencias, caso)
        casos.append(resultado)

    bruto_manifesto = _json_bytes({**metadados, "pacotes": vinculos})
    if manifesto.read_bytes() != bruto_manifesto:
        raise ValueError("o manifesto não corresponde aos pacotes, revisões e corpora")
    resumo = _resumir(casos)
    bruto = _json_bytes({**metadados, **resumo, "sha256_respostas": digest,
                        "sha256_manifesto": _sha(bruto_manifesto), "casos": casos})
    resultado = privado / "resultado.json"
    _gravar_exclusivo(resultado, bruto)
    return {**resumo, "resultado": str(resultado), "sha256_resultado": _sha(bruto)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="acao", required=True)
    preparar_parser = sub.add_parser("preparar", help="lacra pacotes e manifesto em pasta nova")
    medir_parser = sub.add_parser("medir", help="confere e mede uma entrega completa de IDs")
    for p in (preparar_parser, medir_parser):
        p.add_argument("--revisao", required=True, help="commit do código e do catálogo")
        p.add_argument("--revisao-fontes", required=True, help="commit canônico do gabarito")
        p.add_argument("--diretorio", type=Path, required=True)
        p.add_argument("--explorar-fontes", action="store_true",
                       help="oferece as fontes autorizadas e uma sugestão de rota")
        p.add_argument("corpora", type=Path, nargs="+")
    medir_parser.add_argument("--respostas", type=Path, required=True)
    medir_parser.add_argument("--sha256-respostas", required=True)
    args = parser.parse_args()
    raiz = raiz_repo()
    destino = _diretorio(raiz, args.diretorio)
    if args.acao == "preparar" and destino.exists():
        parser.error("o diretório de preparação já existe")
    catalogo, ouro, entradas, meta = _carregar(args, raiz)
    if args.acao == "preparar":
        resumo = _preparar(destino, catalogo, entradas, meta)
    else:
        resumo = _medir_ensaio(destino, catalogo, ouro, entradas, meta,
                               args.respostas, args.sha256_respostas)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
