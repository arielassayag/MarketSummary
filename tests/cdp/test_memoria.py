"""Controles de custódia, validade temporal e recuperação da memória derivada."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import date
from pathlib import Path

import pytest

from cdp.__main__ import build_parser
from cdp.memoria import (
    AVALIACAO,
    LIMITE_CONTEXTO_BYTES,
    PASTA,
    REVISAO_AVALIACAO_INICIAL,
    Catalogo,
    Fontes,
    MemoriaErro,
    _Avaliacao,
    avaliar,
    propor,
    render_contexto,
)

DATA = date(2026, 11, 7)
FONTE = "docs/cdp/playbooks/DIARIO.md"
TRECHO = "Confirme a moeda de origem do índice antes de redigir o comentário."
RAIZ = Path(__file__).resolve().parents[2]


def _git(raiz, *args):
    subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, check=True)


def _commit(raiz):
    _git(raiz, "add", "--all")
    _git(raiz, "-c", "user.email=teste@example.invalid", "-c", "user.name=Teste",
         "-c", "commit.gpgsign=false", "commit", "-qm", "teste")


def _gravar(raiz, caminho, conteudo):
    path = raiz / caminho
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(conteudo, encoding="utf-8")
    return path


def _nota(raiz, id_="moeda-original", **campos):
    nota = {
        "id": id_, "tipo": "procedimento", "estado": "curada", "titulo": "Moeda do índice",
        "resumo": "O comentário consulta a moeda registrada no índice.",
        "escopos": ["diario"], "tags": ["índice", "benchmark", "moeda"],
        "registrada_em": "2026-10-01", "revisada_em": "2026-10-02", "rever_em": "2027-01-01",
        "destaque": True, "substitui": [],
        "evidencias": [{"caminho": FONTE, "trecho": TRECHO,
                        "sha256": hashlib.sha256(TRECHO.encode()).hexdigest()}],
    } | campos
    return _gravar(raiz, f"{PASTA}/{id_}.json", json.dumps(nota, ensure_ascii=False))


@pytest.fixture
def repo(tmp_path):
    raiz = tmp_path.resolve()
    _git(raiz, "init", "-q")
    _gravar(raiz, FONTE, f"# Fechamento\n\n{TRECHO}\n")
    _nota(raiz)
    _commit(raiz)
    return raiz


def _ids(c, escopo="diario"):
    return [n["id"] for n in c.contexto(escopo)["notas"]]


@pytest.mark.skipif(os.name != "posix", reason="auditoria da árvore requer POSIX")
def test_captura_candidata_so_le_fonte_commitada_e_nao_escreve(repo):
    _gravar(repo, FONTE, "Texto da árvore de trabalho, fora da revisão Git.")
    antes = {p.relative_to(repo) for p in repo.rglob("*") if ".git" not in p.parts}
    f = Fontes(repo)
    nota = propor(f, id_="nova-moeda", escopo="diario", caminho=FONTE, inicio=3, fim=3,
                  data=DATA, tipo="licao", titulo="Uma lição", resumo="Lição para revisão.")
    assert nota.estado == "candidata"
    assert nota.revisada_em is None
    assert nota.evidencias[0].trecho == TRECHO
    assert {p.relative_to(repo) for p in repo.rglob("*") if ".git" not in p.parts} == antes
    (repo / PASTA / "nova-moeda.json").write_text(nota.model_dump_json(), encoding="utf-8")
    assert _ids(Catalogo(Fontes(repo), DATA)) == ["moeda-original"]
    assert Catalogo(Fontes(repo, trabalho=True), DATA).problemas
    _gravar(repo, FONTE, TRECHO + "\n")
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert _ids(c) == ["moeda-original"]
    assert c.contagens["candidata"] == 1
    assert [n["id"] for n in c.buscar("diario", "uma lição", 3)["notas"]] == []


def test_intervalo_renumerado_mas_conteudo_alterado_ou_ambiguo_sai(repo):
    _gravar(repo, FONTE, f"# Acrescentado\n\n\n{TRECHO}\n")
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert c.contexto("diario")["notas"][0]["evidencias"][0]["inicio"] == 4
    _gravar(repo, FONTE, f"{TRECHO}\n{TRECHO}\n")
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert c.problemas[0]["codigo"] == "evidencia"
    assert _ids(c) == []
    _gravar(repo, FONTE, TRECHO.replace("moeda", "unidade"))
    _commit(repo)
    assert _ids(Catalogo(Fontes(repo), DATA)) == []


def test_corte_de_revisao_expiracao_e_substituicao_sem_ressuscitar(repo):
    _nota(repo, "moeda-revisada", resumo="A fonte da etapa contém a moeda.",
          registrada_em="2026-10-10", revisada_em="2026-10-15", rever_em="2026-11-15",
          substitui=["moeda-original"])
    _commit(repo)
    f = Fontes(repo)
    assert _ids(Catalogo(f, date(2026, 10, 1))) == []
    assert _ids(Catalogo(f, date(2026, 10, 14))) == ["moeda-original"]
    assert _ids(Catalogo(f, date(2026, 10, 15))) == ["moeda-revisada"]
    assert _ids(Catalogo(f, date(2026, 11, 15))) == []


@pytest.mark.skipif(os.name != "posix", reason="auditoria da árvore requer POSIX")
def test_revisao_presa_a_head_e_auditoria_nao_concede_escopo(repo):
    f = Fontes(repo)
    _nota(repo, escopos=["cobertura"])
    assert _ids(Catalogo(Fontes(repo), DATA), "cobertura") == []
    assert _ids(Catalogo(Fontes(repo, trabalho=True), DATA), "cobertura") == ["moeda-original"]
    _commit(repo)
    assert _ids(Catalogo(f, DATA)) == ["moeda-original"]
    assert _ids(Catalogo(Fontes(repo), DATA)) == []
    assert _ids(Catalogo(Fontes(repo), DATA), "cobertura") == ["moeda-original"]


@pytest.mark.skipif(os.name != "posix", reason="auditoria da árvore requer POSIX")
def test_recusa_caminho_externo_e_link_sem_ler_alvo(repo):
    segredo = _gravar(repo, "segredo.txt", TRECHO + "\n")
    (repo / FONTE).unlink()
    (repo / FONTE).symlink_to(segredo)
    assert Catalogo(Fontes(repo, trabalho=True), DATA).problemas
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert _ids(c) == []
    assert c.problemas[0]["codigo"] == "evidencia"
    for caminho in ("../segredo.txt", str(segredo), "book/decisao.md", "docs/cdp/memoria/notas/x.md"):
        with pytest.raises(ValueError, match="caminho|evidência"):
            Fontes(repo).linhas(caminho)
    with pytest.raises(MemoriaErro, match="ilegível"):
        Fontes(repo).linhas(FONTE)


def test_anotacao_hostil_nao_vaza_erro_de_schema_nem_injeta_markdown(repo):
    segredo = "SEGREDO DE TESTE"
    _nota(repo, "payload", titulo=f"<script>{segredo}</script>")
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert c.problemas == [{"id": "payload", "codigo": "schema", "detalhe": "titulo"}]
    markdown = render_contexto(c.contexto("diario"))
    assert segredo not in markdown and TRECHO not in markdown
    assert "moeda-original" in markdown and "ressalvas" in markdown


def test_cli_contexto_e_busca_publicam_so_referencia(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    p = build_parser()
    for argv in (
        ["contexto", "--escopo", "diario", "--formato", "json"],
        ["buscar", "--escopo", "diario", "--consulta", "moeda do índice"],
    ):
        args = p.parse_args(["memoria", *argv, "--data", DATA.isoformat()])
        assert args.func(args) == 0
        texto = capsys.readouterr().out
        nota = json.loads(texto)["notas"][0]
        assert nota["id"] == "moeda-original"
        assert "trecho" not in nota["evidencias"][0]
        assert TRECHO not in texto
        if argv[0] == "contexto":
            assert len(texto.encode()) <= LIMITE_CONTEXTO_BYTES
    c = Catalogo(Fontes(repo), DATA)
    atual = c.buscar("diario", "Qual foi o retorno do índice hoje?", 3)
    assert atual["orientacao_atual"] and atual["notas"] == []
    manual = c.buscar("diario", "moeda do índice", 3, estado_atual=True)
    assert manual["orientacao_atual"] and manual["passagens"] == manual["notas"] == []


def test_corpus_do_projeto_mantem_abstencao_e_ganho_de_recuperacao():
    corrente = Catalogo(Fontes(RAIZ, trabalho=os.name == "posix"), DATA)
    assert not corrente.problemas, corrente.problemas
    f = Fontes(RAIZ, revisao=REVISAO_AVALIACAO_INICIAL)
    e = _Avaliacao.model_validate_json(f.ler(AVALIACAO, 65_536))
    c = Catalogo(f, e.data)
    assert not c.problemas, c.problemas
    rel = avaliar(c, e.casos)["medidas"]
    abstencao = rel["absteve_de_nota"]
    assert abstencao["acertos"] == abstencao["casos"] >= 8
    direto, ampliado = rel["fonte_direta_recuperada"], rel["fonte_com_memoria_recuperada"]
    assert ampliado["acertos"] == ampliado["casos"] >= 21
    assert ampliado["acertos"] >= direto["acertos"]
    direto_sem_nota = rel["absteve_em_busca_direta"]
    assert direto_sem_nota["acertos"] == direto_sem_nota["casos"] >= 3
    notas = rel["nota_esperada_recuperada"]
    assert notas["acertos"] == notas["casos"] >= 21



def test_json_ambiguo_nao_ativa_nota(repo):
    p = repo / PASTA / "moeda-original.json"
    p.write_text('{"estado":"candidata",' + p.read_text(encoding="utf-8")[1:], encoding="utf-8")
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert c.problemas and not c.contexto("diario")["notas"]


def test_retirada_preserva_substituicao_e_fonte_antiga(repo):
    _nota(repo, "moeda-retirada", resumo="A fonte da etapa contém a moeda.", registrada_em="2026-10-10",
          revisada_em="2026-10-15", rever_em="2026-11-15", substitui=["moeda-original"])
    _commit(repo)
    p = repo / PASTA / "moeda-retirada.json"
    nota = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(nota | {"estado": "retirada", "destaque": False}), encoding="utf-8")
    _commit(repo)
    c = Catalogo(Fontes(repo), DATA)
    assert c.contagens["substituida"] == c.contagens["retirada"] == 1
    assert _ids(c) == []


def test_sonho_cobre_fila_e_confere_candidatas_sem_ativacao(repo):
    from cdp.memoria_sonho import conferir_sonho, sonhar, wiki

    _nota(repo, "nova-licao", estado="candidata", revisada_em=None, rever_em=None,
          destaque=False, resumo="Uma hipótese sobre a consulta da moeda.")
    _commit(repo)
    catalogo = Catalogo(Fontes(repo), DATA)
    plano = sonhar(catalogo)
    assert plano == sonhar(catalogo)
    item = next(i for i in plano["fila"] if i["id"] == "nova-licao")
    assert item["acao"] == "revisar_candidata" and item["origens"][0]["sha256"]

    candidata = catalogo.notas["nova-licao"].model_dump(mode="json")
    candidata.update(id="licao-revisada", registrada_em=DATA.isoformat())
    respostas = [{"uid": i["uid"], "decisao": "manter", "motivo": "Fonte conferida."}
                 for i in plano["fila"]]
    resposta = next(r for r in respostas if r["uid"] == item["uid"])
    resposta.update(decisao="propor_candidata", candidata=candidata)
    payload = {"plano_sha256": plano["sha256"], "respostas": respostas}
    antes = {p.name for p in (repo / PASTA).iterdir()}
    ok = conferir_sonho(catalogo, plano, json.dumps(payload).encode())
    assert ok["estado"] == "propostas_para_revisao" and len(ok["candidatas"]) == 1
    assert {p.name for p in (repo / PASTA).iterdir()} == antes
    assert [n["id"] for n in wiki(catalogo, "diario")["notas"]] == ["moeda-original"]

    with pytest.raises(MemoriaErro, match="exatamente uma"):
        conferir_sonho(catalogo, plano, json.dumps(payload | {"respostas": []}).encode())
    candidata["escopos"] = ["risco"]
    with pytest.raises(MemoriaErro, match="fora do item"):
        conferir_sonho(catalogo, plano, json.dumps(payload).encode())


def test_sonho_identifica_fontes_mudadas_e_pagina_sem_perder_item(repo):
    from cdp.memoria_sonho import sonhar

    anterior = Fontes(repo).revisao
    _gravar(repo, FONTE, f"Versão revista do roteiro.\n{TRECHO}\n")
    _nota(repo, "candidata-teste", estado="candidata", revisada_em=None, rever_em=None,
          destaque=False)
    _commit(repo)
    catalogo = Catalogo(Fontes(repo), DATA)
    a = sonhar(catalogo, desde=anterior, limite=1)
    b = sonhar(catalogo, desde=anterior, limite=1, pagina=2)
    assert a["fila"][0]["acao"] == "revisar_candidata" and a["adiados"] == 1
    assert b["fila"][0]["id"] == FONTE and b["adiados"] == 0
    assert a["sha256"] != b["sha256"]
