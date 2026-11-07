"""Comprovação das substituições de notas na história local do catálogo."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from .memoria import Fontes, Nota, Registro

MAX_REVISOES = 128
MAX_MUDANCAS = 1024


@dataclass(frozen=True)
class _Ligacao:
    anterior: str
    sucessora: str
    revisada_em: date


def _historico(fontes: Fontes) -> list[tuple[str, list[tuple[bytes, str]]]]:
    from .memoria import PASTA, MemoriaErro, _git

    if _git(fontes.raiz, "rev-parse", "--is-shallow-repository").strip() != b"false":
        raise MemoriaErro("a linhagem da memória exige histórico Git completo")

    bruto = _git(
        fontes.raiz, "log", "--first-parent", "--full-history", "--root",
        f"--max-count={MAX_REVISOES + 1}", "--format=%x1e%H", "--name-status", "-z",
        "--diff-merges=first-parent", "--no-renames", "--no-show-signature", "--no-notes",
        "--no-ext-diff", "--no-textconv",
        "--no-decorate", "--color=never", fontes.revisao, "--", PASTA,
    )
    revisoes: list[tuple[str, list[tuple[bytes, str]]]] = []
    mudancas: list[tuple[bytes, str]] = []
    partes = iter(bruto.split(b"\0"))
    total = 0
    for parte in partes:
        if not parte:
            continue
        if re.fullmatch(rb"\x1e(?:[0-9a-f]{40}|[0-9a-f]{64})", parte):
            mudancas = []
            revisoes.append((parte[1:].decode("ascii"), mudancas))
            if len(revisoes) > MAX_REVISOES:
                raise MemoriaErro("histórico da memória acima do limite de revisões")
            continue
        estado = parte.lstrip(b"\n")
        caminho = next(partes, b"")
        if not revisoes or estado not in {b"A", b"D", b"M", b"T"} or not caminho:
            raise MemoriaErro("histórico Git da memória ilegível")
        # Um arquivo com outro formato não é uma nota e não pode criar linhagem.
        if re.fullmatch(re.escape(PASTA.encode()) + rb"/[a-z0-9]+(?:-[a-z0-9]+)*\.json",
                        caminho):
            total += 1
            if total > MAX_MUDANCAS:
                raise MemoriaErro("histórico da memória acima do limite de mudanças")
            mudancas.append((estado, caminho.decode("ascii")))
    return revisoes[::-1]


def _ler_nota(fontes: Fontes, caminho: str, id_: str) -> Nota | None:
    from .memoria import MAX_BYTES_NOTA, MemoriaGitIndisponivel, Nota, _chaves_unicas

    try:
        bruto = fontes.ler(caminho, MAX_BYTES_NOTA)
        json.loads(bruto, object_pairs_hook=_chaves_unicas)
        nota = Nota.model_validate_json(bruto)
    except MemoriaGitIndisponivel:
        raise
    except (ValueError, OSError, RuntimeError):
        return None
    return nota if nota.id == id_ else None


def _ligacoes(nota: Nota, notas: Mapping[str, Nota]) -> set[_Ligacao]:
    if nota.estado != "curada" or not nota.substitui or nota.revisada_em is None:
        return set()
    for id_ in nota.substitui:
        anterior = notas.get(id_)
        if (anterior is None or anterior.revisada_em is None
                or anterior.revisada_em > nota.revisada_em
                or anterior.registrada_em >= nota.registrada_em
                or not set(anterior.escopos).issubset(nota.escopos)):
            return set()
    return {_Ligacao(id_, nota.id, nota.revisada_em) for id_ in nota.substitui}


def substituicoes_confirmadas(
    fontes: Fontes, data: date, notas: Mapping[str, Nota], registros: Mapping[str, Registro],
) -> tuple[set[str], list[dict[str, str]]]:
    """Retorna supressões comprovadas e recusas, sem alterar arquivos ou referências Git."""
    from .memoria import Fontes, MemoriaErro, MemoriaGitIndisponivel, _localizar

    revisoes = _historico(fontes)
    so_adicoes = all(estado == b"A" for _, mudancas in revisoes for estado, _ in mudancas)
    if so_adicoes and not fontes.trabalho and not any(n.substitui for n in notas.values()):
        return set(), []
    comprovadas: set[_Ligacao] = set()
    vigentes: dict[str, Nota] = {}
    for revisao, mudancas in revisoes:
        fonte = Fontes(fontes.raiz, revisao=revisao)
        alteradas: list[Nota] = []
        for estado, caminho in mudancas:
            id_ = caminho.rsplit("/", 1)[-1].removesuffix(".json")
            nota = None if estado == b"D" else _ler_nota(fonte, caminho, id_)
            if nota is None:
                vigentes.pop(id_, None)
            else:
                vigentes[id_] = nota
                alteradas.append(nota)
        for nota in alteradas:
            novas = _ligacoes(nota, vigentes) - comprovadas
            if not novas:
                continue
            try:
                for evidencia in nota.evidencias:
                    _localizar(fonte, evidencia)
            except MemoriaGitIndisponivel:
                raise
            except MemoriaErro:
                continue
            comprovadas.update(novas)

    if fontes.trabalho:
        # Audita a proposta corrente para revisão, sem conferir autoridade fora do HEAD.
        for id_ in registros:
            comprovadas.update(_ligacoes(notas[id_], notas))

    problemas = []
    for id_, nota in notas.items():
        if nota.estado == "candidata" or not nota.substitui:
            continue
        atuais = {_Ligacao(alvo, id_, nota.revisada_em) for alvo in nota.substitui}
        if atuais - comprovadas:
            problemas.append({"id": id_, "codigo": "linhagem",
                              "detalhe": "substituição sem prova na revisão que a registrou"})
    return {link.anterior for link in comprovadas if link.revisada_em <= data}, problemas
