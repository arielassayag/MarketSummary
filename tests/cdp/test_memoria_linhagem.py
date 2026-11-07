"""Provas da primeira integração e persistência da retirada de notas antigas."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import date

import pytest
from test_memoria import DATA, FONTE, TRECHO, _commit, _git, _gravar, _ids, _nota
from test_memoria import repo as repo

from cdp import memoria_linhagem
from cdp.memoria import Catalogo, Fontes, MemoriaErro, MemoriaGitIndisponivel

NOVA_FONTE = "Confirme a unidade e a moeda no FactBook da etapa."


def _sucessora(repo, *, estado="curada", tags=None):
    dados_candidata = {"revisada_em": None, "rever_em": None, "destaque": False}
    dados_revisada = {"revisada_em": "2026-11-05", "rever_em": "2027-01-01"}
    return _nota(
        repo, "moeda-sucessora", estado=estado, registrada_em="2026-11-04",
        resumo="A etapa registra unidade e moeda.", substitui=["moeda-original"],
        tags=["moeda"] if tags is None else tags,
        evidencias=[{"caminho": FONTE, "trecho": NOVA_FONTE,
                     "sha256": hashlib.sha256(NOVA_FONTE.encode()).hexdigest()}],
        **(dados_candidata if estado == "candidata" else dados_revisada),
    )


def test_promocao_so_substitui_com_prova_na_revisao_da_nota(repo):
    revisao_antiga = Fontes(repo).revisao
    _sucessora(repo, estado="candidata")
    _commit(repo)
    assert _ids(Catalogo(Fontes(repo), DATA)) == ["moeda-original"]
    path = _sucessora(repo)
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert _ids(c) == ["moeda-original"]
    assert {p["codigo"] for p in c.problemas} >= {"evidencia", "linhagem"}

    _gravar(repo, FONTE, f"{TRECHO}\n{NOVA_FONTE}\n")
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert _ids(c) == ["moeda-original"]
    assert {p["codigo"] for p in c.problemas} == {"linhagem"}

    _sucessora(repo, tags=["moeda", "unidade"])
    _commit(repo)
    assert _ids(Catalogo(Fontes(repo), DATA)) == ["moeda-sucessora"]
    path.unlink()
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert _ids(c) == []
    assert c.contagens["substituida"] == 1
    assert _ids(Catalogo(Fontes(repo, revisao=revisao_antiga), DATA)) == ["moeda-original"]


def test_linhagem_so_considera_a_integracao_no_primeiro_pai(repo):
    _gravar(repo, FONTE, f"{TRECHO}\n{NOVA_FONTE}\n")
    _commit(repo)
    _git(repo, "checkout", "-qb", "principal")
    _git(repo, "checkout", "-qb", "ensaio")
    path = _sucessora(repo)
    _commit(repo)
    assert _ids(Catalogo(Fontes(repo), DATA)) == ["moeda-sucessora"]
    path.unlink()
    _commit(repo)
    _git(repo, "checkout", "-q", "principal")
    _git(repo, "-c", "user.email=teste@example.invalid", "-c", "user.name=Teste",
         "-c", "commit.gpgsign=false", "merge", "--no-ff", "--no-edit", "ensaio")
    assert _ids(Catalogo(Fontes(repo), DATA)) == ["moeda-original"]

    _git(repo, "checkout", "-q", "ensaio")
    _sucessora(repo, tags=["moeda", "unidade"])
    _commit(repo)
    _git(repo, "checkout", "-q", "principal")
    _git(repo, "-c", "user.email=teste@example.invalid", "-c", "user.name=Teste",
         "-c", "commit.gpgsign=false", "merge", "--no-ff", "--no-edit", "ensaio")
    f = Fontes(repo)
    assert _ids(Catalogo(f, date(2026, 11, 4))) == ["moeda-original"]
    assert _ids(Catalogo(f, DATA)) == ["moeda-sucessora"]


def test_historico_incompleto_nao_pode_ressuscitar_versao_anterior(repo, monkeypatch):
    _gravar(repo, FONTE, f"{TRECHO}\n{NOVA_FONTE}\n")
    _sucessora(repo)
    _commit(repo)
    path = repo.parent / "raso"
    subprocess.run(["git", "clone", "--quiet", "--depth=1", repo.as_uri(), str(path)],
                   check=True, capture_output=True)
    with pytest.raises(MemoriaErro, match="histórico Git completo"):
        Catalogo(Fontes(path), DATA)
    monkeypatch.setattr(memoria_linhagem, "MAX_REVISOES", 1)
    with pytest.raises(MemoriaErro, match="limite de revisões"):
        Catalogo(Fontes(repo), DATA)


def test_indisponibilidade_de_blob_historico_impede_publicar_notas(repo, monkeypatch):
    _gravar(repo, FONTE, f"{TRECHO}\n{NOVA_FONTE}\n")
    path = _sucessora(repo)
    _commit(repo)
    revisao_promocao = Fontes(repo).revisao
    path.unlink()
    _commit(repo)

    ler = Fontes.ler

    def ler_com_blob_ausente(fontes, caminho, limite):
        if fontes.revisao == revisao_promocao and caminho.endswith(path.name):
            raise MemoriaGitIndisponivel("blob antigo indisponível")
        return ler(fontes, caminho, limite)

    monkeypatch.setattr(Fontes, "ler", ler_com_blob_ausente)
    with pytest.raises(MemoriaGitIndisponivel, match="blob antigo indisponível"):
        Catalogo(Fontes(repo), DATA)
