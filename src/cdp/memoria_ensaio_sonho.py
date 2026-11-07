"""Ensaio isolado de consolidação. Nenhum artefato entra na operação."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .memoria import (
    ESCOPO,
    MAX_BYTES_FONTE,
    PASTA,
    Catalogo,
    Evidencia,
    Fontes,
    Local,
    MemoriaErro,
    Nota,
    Slug,
    _chaves_unicas,
    _git,
    _localizar,
    _Modelo,
    _primarias,
)
from .memoria_avaliacao import CasoReservado, K, _grupos, _medir, _resumo

CORPUS_SONHO = "docs/cdp/memoria/avaliacao_sonho.json"
MODOS = ("direta", "memoria", "apos_revisao")


class _Requisito(_Modelo):
    id: Slug
    acao: Literal["revisar_candidata", "rever_validade", "evidencia", "duplicata"]


class _Decisao(_Modelo):
    tipo: Literal["promocao", "renovacao", "substituicao", "fusao"]
    requer: list[_Requisito] = Field(min_length=1, max_length=4)
    atualizar: list[Nota] = Field(min_length=1, max_length=4)


class _CasoSonho(CasoReservado):
    notas_antes: list[Slug] = Field(max_length=5)
    notas_apos_revisao: list[Slug] = Field(max_length=5)


class _Ensaio(_Modelo):
    versao: Literal[1]
    data: date
    revisao_fontes: str = Field(pattern=r"^[0-9a-f]{40}$")
    deriva: list[Evidencia] = Field(min_length=1, max_length=8)
    notas_antes: list[Nota] = Field(min_length=1, max_length=32)
    decisoes: list[_Decisao] = Field(min_length=1, max_length=16)
    casos: list[_CasoSonho] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def conferir(self) -> _Ensaio:
        ids = {n.id for n in self.notas_antes}
        novos = [n.id for d in self.decisoes for n in d.atualizar]
        if len(ids) != len(self.notas_antes) or len(set(novos)) != len(novos):
            raise ValueError("notas repetidas no ensaio")
        if any(r.id not in ids for d in self.decisoes for r in d.requer):
            raise ValueError("revisão sem nota original")
        if any(not set(c.notas_antes) <= ids or not set(c.notas_apos_revisao) <= ids | set(novos)
               for c in self.casos):
            raise ValueError("caso aponta para nota ausente")
        if len({c.id for c in self.casos}) != len(self.casos):
            raise ValueError("caso repetido no ensaio")
        if len({ev.caminho for ev in self.deriva}) != len(self.deriva):
            raise ValueError("use uma alteração por fonte do ensaio")
        return self


def _git_isolado(raiz: Path, data: date, *args: str) -> bytes:
    instante = data.isoformat() + "T12:00:00+00:00"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_AUTHOR_NAME="Ensaio de memória do CDP",
        GIT_AUTHOR_EMAIL="ensaio@invalid.example",
        GIT_COMMITTER_NAME="Ensaio de memória do CDP",
        GIT_COMMITTER_EMAIL="ensaio@invalid.example",
        GIT_AUTHOR_DATE=instante,
        GIT_COMMITTER_DATE=instante,
        GIT_ALLOW_PROTOCOL="",
        GIT_NO_LAZY_FETCH="1",
    )
    try:
        return subprocess.run(
            ["git", "-C", str(raiz), "-c", "core.autocrlf=false", *args],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=15, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise MemoriaErro("não foi possível preparar a revisão Git isolada do ensaio") from exc


def _commit(raiz: Path, data: date, mensagem: str) -> None:
    _git_isolado(raiz, data, "add", "--", ".")
    _git_isolado(raiz, data, "commit", "--quiet", "--no-gpg-sign", "-m", mensagem)


def _gravar(raiz: Path, caminho: str, corpo: bytes) -> None:
    destino = raiz / caminho
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(corpo)


def _gravar_notas(raiz: Path, notas: list[Nota]) -> None:
    for nota in notas:
        _gravar(raiz, f"{PASTA}/{nota.id}.json", nota.model_dump_json(indent=2).encode() + b"\n")


def _preparar(raiz: Path, fonte: Fontes, ensaio: _Ensaio) -> Catalogo:
    _git_isolado(raiz, ensaio.data, "init", "--quiet", "--template=", "--object-format=sha1")
    primarias = {p for escopo in ESCOPO for p in _primarias(escopo)}
    ref_notas = {e.caminho for nota in ensaio.notas_antes for e in nota.evidencias}
    ref_revistas = {e.caminho for d in ensaio.decisoes for n in d.atualizar for e in n.evidencias}
    if not (ref_notas | ref_revistas | {e.caminho for e in ensaio.deriva}) <= primarias:
        raise MemoriaErro("o ensaio exige o mesmo universo de fontes nos três braços")
    corpos = {p: fonte.ler(p, MAX_BYTES_FONTE) for p in sorted(primarias)}
    obsoletos = {ev.caminho: ev.trecho.encode() for ev in ensaio.deriva}
    for caminho, corpo in corpos.items():
        complemento = b"\n" + obsoletos[caminho] + b"\n" if caminho in obsoletos else b""
        _gravar(raiz, caminho, corpo + complemento)
    _gravar_notas(raiz, ensaio.notas_antes)
    _commit(raiz, ensaio.data, "Ensaio: catálogo com versões anteriores dos trechos")
    fontes_anteriores = Fontes(raiz)
    for ev in ensaio.deriva:
        _localizar(fontes_anteriores, ev)
        _gravar(raiz, ev.caminho, corpos[ev.caminho])
    _commit(raiz, ensaio.data, "Ensaio: fontes canônicas no corte")
    return Catalogo(Fontes(raiz), ensaio.data)


def _propostas(relatorio: dict) -> set[tuple[str, str]]:
    return {(item["id"], item["acao"]) for item in relatorio["fila"]}


def _devolutiva(ensaio: _Ensaio, plano: dict) -> bytes:
    sucessoras = {(d.requer[0].id, d.requer[0].acao): d.atualizar[0] for d in ensaio.decisoes
                  if d.tipo == "substituicao"}
    respostas = []
    for item in plano["fila"]:
        nota = sucessoras.get((item["id"], item["acao"]))
        if nota is None:
            respostas.append({"uid": item["uid"], "decisao": "investigar",
                              "motivo": "Item sem proposta textual neste ensaio."})
            continue
        candidata = nota.model_dump(mode="json")
        candidata.update(estado="candidata", revisada_em=None, rever_em=None, destaque=False)
        respostas.append({"uid": item["uid"], "decisao": "propor_candidata",
                          "motivo": "O roteiro de teste propõe a sucessora com nova evidência.",
                          "candidata": candidata})
    return json.dumps({"plano_sha256": plano["sha256"], "respostas": respostas},
                      ensure_ascii=False).encode()


def _elegiveis(catalogo: Catalogo) -> list[str]:
    return sorted(reg.nota.id for reg in catalogo.ativos)


def _avaliar_caso(c: _CasoSonho, antes: Catalogo, depois: Catalogo) -> dict:
    grupos = _grupos(antes.fontes, c)
    modos = {"direta": _medir(antes.indice.buscar(c.escopo, c.consulta, K), grupos)}
    for nome, catalogo in (("memoria", antes), ("apos_revisao", depois)):
        resultado = catalogo.buscar(c.escopo, c.consulta, K)
        notas = [n["id"] for n in resultado["notas"]]
        leitura = _medir([Local(**p) for p in resultado["passagens"]], grupos,
                         encaminhou=bool(resultado["orientacao_atual"]), notas=bool(notas))
        leitura["notas"] = notas
        if c.tipo == "estado_atual":
            explicita = catalogo.buscar(c.escopo, c.consulta, K, estado_atual=True)
            leitura["encaminhou_explicito"] = bool(explicita["orientacao_atual"]) and not (
                explicita["notas"] or explicita["passagens"]
            )
        modos[nome] = leitura
    return {
        "id": c.id, "escopo": c.escopo, "tipo": c.tipo, "grupos": len(grupos),
        "notas_esperadas_antes": c.notas_antes,
        "notas_esperadas_apos_revisao": c.notas_apos_revisao,
        "modos": modos,
    }


def avaliar_sonho(fonte_corpus: Fontes) -> dict:
    from .memoria_sonho import conferir_sonho, sonhar

    if set(os.environ) & {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                          "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_INDEX_FILE"}:
        raise MemoriaErro("o ensaio não admite redirecionamento do repositório Git")
    bruto = fonte_corpus.ler(CORPUS_SONHO, 256 * 1024)
    json.loads(bruto, object_pairs_hook=_chaves_unicas)
    ensaio = _Ensaio.model_validate_json(bruto)
    fontes = Fontes(fonte_corpus.raiz, revisao=ensaio.revisao_fontes)
    with tempfile.TemporaryDirectory(prefix="cdp-ensaio-memoria-") as tmp:
        raiz = Path(tmp).resolve()
        antes = _preparar(raiz, fontes, ensaio)
        origem = _git_isolado(raiz, ensaio.data, "rev-parse", "HEAD^").decode().strip()
        plano = sonhar(antes, desde=origem)
        fila = _propostas(plano)
        devolutiva = conferir_sonho(antes, plano, _devolutiva(ensaio, plano))
        propostas = {p["id"] for p in devolutiva["candidatas"]}
        intacto = (not _git_isolado(raiz, ensaio.data, "status", "--porcelain", "--untracked-files=all")
                   and Fontes(raiz).revisao == antes.fontes.revisao)
        if not intacto:
            raise MemoriaErro("a proposta alterou o repositório isolado do ensaio")
        decisoes = []
        for decisao in ensaio.decisoes:
            requisitos = {(r.id, r.acao) for r in decisao.requer}
            diagnosticada = requisitos <= fila
            ids = {n.id for n in decisao.atualizar}
            proposta_conferida = ids <= propostas if decisao.tipo == "substituicao" else None
            revisada = diagnosticada and proposta_conferida is not False
            if revisada:
                _gravar_notas(raiz, decisao.atualizar)
            decisoes.append({
                "tipo": decisao.tipo, "diagnosticada": diagnosticada, "revisada": revisada,
                "proposta_conferida": proposta_conferida,
                "requisitos": [r.model_dump() for r in decisao.requer],
                "notas_resultantes": sorted(ids),
            })
        if any(d["revisada"] for d in decisoes):
            _commit(raiz, ensaio.data, "Ensaio: decisões explícitas do roteiro de revisão")
        depois = Catalogo(Fontes(raiz), ensaio.data)
        mudancas = _git_isolado(
            raiz, ensaio.data, "diff", "--name-only", "-z",
            antes.fontes.revisao, depois.fontes.revisao,
        ).decode().split("\0")
        if (any(p and not p.startswith(PASTA + "/") for p in mudancas)
                or antes.fontes_por_escopo != depois.fontes_por_escopo):
            raise MemoriaErro("as fontes canônicas devem permanecer iguais entre os braços")
        elegiveis_antes, elegiveis_depois = _elegiveis(antes), _elegiveis(depois)
        for decisao in decisoes:
            decisao["elegivel_apos_revisao"] = all(
                id_ in elegiveis_depois for id_ in decisao["notas_resultantes"]
            )
        casos = [_avaliar_caso(c, antes, depois) for c in ensaio.casos]
        pendentes = _propostas(sonhar(depois, desde=antes.fontes.revisao))
        esperado_antes = {id_ for c in ensaio.casos for id_ in c.notas_antes}
        esperado_depois = {id_ for c in ensaio.casos for id_ in c.notas_apos_revisao}
        return {
            "natureza": "DADOS SIMULADOS",
            "metodo": ("As três buscas consultam as mesmas fontes e perguntas. O terceiro braço "
                       "reproduz decisões editoriais predefinidas, condicionadas à fila de sonhar, "
                       "em Git temporário. A fila não promove notas por si."),
            "revisoes": {
                "fontes": fontes.revisao, "corpus": hashlib.sha256(bruto).hexdigest(),
                "codigo": _git(fonte_corpus.raiz, "rev-parse", "--verify", "HEAD").decode().strip(),
                "antes": antes.fontes.revisao, "apos_revisao": depois.fontes.revisao,
            },
            "data": ensaio.data.isoformat(), "limite": K, "corpus": CORPUS_SONHO,
            "resumo": {modo: _resumo(casos, modo) for modo in MODOS},
            "consolidacao": {
                "somente_leitura": intacto,
                "plano_sha256": plano["sha256"],
                "candidatas_conferidas": sorted(propostas),
                "elegibilidade_conferiu_antes": set(elegiveis_antes) == esperado_antes,
                "elegibilidade_conferiu_apos_revisao": set(elegiveis_depois) == esperado_depois,
                "fila_antes": [{"id": i, "acao": a} for i, a in sorted(fila)],
                "fila_apos_revisao": [{"id": i, "acao": a} for i, a in sorted(pendentes)],
                "decisoes": decisoes, "elegiveis_antes": elegiveis_antes,
                "elegiveis_apos_revisao": elegiveis_depois,
                "catalogo_antes": antes.contagens, "catalogo_apos_revisao": depois.contagens,
            },
            "casos": casos,
        }
