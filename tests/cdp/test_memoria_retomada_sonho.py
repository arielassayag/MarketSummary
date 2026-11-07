"""A revisão por páginas é retomável, vinculada ao Git e somente leitura."""

import hashlib
import json
import subprocess
from datetime import date, timedelta

import pytest

from cdp.memoria import MAX_NOTAS, PASTA, Catalogo, Fontes, MemoriaErro
from cdp.memoria_sonho import LIMITE_SONHO, conferir_sonho, retomar_sonho, sonhar

DATA = date(2026, 11, 7)
FONTE = "docs/cdp/playbooks/DIARIO.md"
TRECHO = "DADOS SIMULADOS. Confira a moeda registrada no fechamento."


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def _commit(repo):
    _git(repo, "add", "--all")
    _git(repo, "-c", "user.email=teste@example.invalid", "-c", "user.name=Teste",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "teste")
    return Fontes(repo).revisao


def _nota(id_, estado):
    return {
        "id": id_, "tipo": "procedimento", "estado": estado, "titulo": "Moeda do fechamento",
        "resumo": f"Procedimento de teste {id_}.", "escopos": ["diario"], "tags": [],
        "registrada_em": DATA.isoformat(),
        "revisada_em": None if estado == "candidata" else DATA.isoformat(),
        "rever_em": None if estado == "candidata" else "2027-01-01",
        "destaque": False, "substitui": [],
        "evidencias": [{"caminho": FONTE, "trecho": TRECHO,
                        "sha256": hashlib.sha256(TRECHO.encode()).hexdigest()}],
    }


def _gravar_nota(repo, nota):
    (repo / PASTA / f"{nota['id']}.json").write_text(json.dumps(nota), encoding="utf-8")


def _prova(caminho=FONTE, trecho=TRECHO):
    return {"caminho": caminho, "trecho": trecho, "sha256": hashlib.sha256(trecho.encode()).hexdigest()}


def _responder(plano, decisoes=None, *, padrao=None):
    decisoes = decisoes or {}
    padrao = {"decisao": "manter", "motivo": "Trecho conferido."} | (padrao or {})
    respostas = [{"uid": item["uid"]} | padrao | decisoes.get(item["uid"], decisoes.get(item["id"], {}))
                 for item in plano["fila"]]
    return json.dumps({"plano_sha256": plano["sha256"], "respostas": respostas}).encode()


@pytest.fixture
def repo_sonho(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / FONTE).parent.mkdir(parents=True)
    (tmp_path / PASTA).mkdir(parents=True)
    (tmp_path / FONTE).write_text(f"# Fonte anterior\n{TRECHO}\n", encoding="utf-8")
    _gravar_nota(tmp_path, _nota("procedimento", "curada"))
    anterior = _commit(tmp_path)
    (tmp_path / FONTE).write_text(f"# Fonte revista\n{TRECHO}\n", encoding="utf-8")
    for i in range(3):
        _gravar_nota(tmp_path, _nota(f"candidata-{i}", "candidata"))
    _commit(tmp_path)
    return tmp_path, anterior


def test_retomada_prova_cobertura_e_conserva_pendencia(repo_sonho):
    repo, anterior = repo_sonho
    for i in range(3, 2 * LIMITE_SONHO + 1):
        _gravar_nota(repo, _nota(f"candidata-{i:02}", "candidata"))
    _commit(repo)
    catalogo = Catalogo(Fontes(repo), DATA)
    opcoes = {"limite": LIMITE_SONHO, "desde": anterior}
    inicio = retomar_sonho(catalogo, **opcoes, devolutivas=iter(()))
    assert inicio["proximo_plano"] == sonhar(catalogo, **opcoes)
    assert inicio["paginas_conferidas"] == inicio["itens_conferidos"] == 0
    assert "desde_sugerido" not in inicio
    assert inicio["total"] == 2 * LIMITE_SONHO + 2

    primeira = inicio["proximo_plano"]
    investigar = {"decisao": "investigar", "motivo": "Revisão humana pendente."}
    item = primeira["fila"][0]
    devolutivas = [_responder(primeira, {item["id"]: investigar})]
    pendencia = {"uid": item["uid"], "acao": item["acao"], "id": item["id"],
                 "motivo": investigar["motivo"]}

    for pagina in (2, 3):
        retomada = retomar_sonho(catalogo, **opcoes, devolutivas=iter(devolutivas))
        assert retomada["estado"] == "em_andamento"
        assert "desde_sugerido" not in retomada
        assert retomada["paginas_conferidas"] == pagina - 1
        assert retomada["itens_conferidos"] == (pagina - 1) * LIMITE_SONHO
        assert retomada["pendencias"] == [pendencia]
        proximo = retomada["proximo_plano"]
        assert proximo == sonhar(catalogo, **opcoes, pagina=pagina)
        devolutivas.append(_responder(proximo))
    assert proximo["fila"][-1]["id"] == FONTE

    fim = retomar_sonho(catalogo, **opcoes, devolutivas=iter(devolutivas))
    assert fim["estado"] == "cobertura_completa"
    assert fim["itens_conferidos"] == fim["total"] == 2 * LIMITE_SONHO + 2
    assert fim["paginas_conferidas"] == 3
    assert fim["desde_sugerido"] == catalogo.fontes.revisao
    assert fim["pendencias"] == [pendencia]
    assert fim["proximo_plano"] is None
    assert Fontes(repo).revisao == fim["revisao"]
    assert _git(repo, "status", "--porcelain") == b""


def test_retomada_recusa_repeticao_buraco_lacre_e_excedente(repo_sonho):
    repo, anterior = repo_sonho
    catalogo = Catalogo(Fontes(repo), DATA)
    opcoes = {"limite": 1, "desde": anterior}
    devolutivas = [_responder(sonhar(catalogo, **opcoes, pagina=i)) for i in range(1, 5)]
    primeira, segunda, terceira, _ = devolutivas
    adulterada = json.loads(segunda) | {"plano_sha256": "0" * 64}
    for lote in ([segunda], [primeira, primeira], [primeira, terceira],
                 [primeira, json.dumps(adulterada).encode()]):
        with pytest.raises(MemoriaErro, match="outro plano"):
            retomar_sonho(catalogo, **opcoes, devolutivas=lote)
    with pytest.raises(MemoriaErro, match="além da fila"):
        retomar_sonho(catalogo, **opcoes, devolutivas=[*devolutivas, primeira])


def test_retomada_exige_o_mesmo_corte_mesmo_com_itens_iguais(repo_sonho):
    repo, anterior = repo_sonho
    original = Catalogo(Fontes(repo), DATA)
    plano = sonhar(original, desde=anterior)
    bruto = _responder(plano)
    (repo / "alheio.txt").write_text("DADOS SIMULADOS", encoding="utf-8")
    _commit(repo)
    novas_bases = [Catalogo(Fontes(repo), DATA), Catalogo(original.fontes, DATA + timedelta(days=1))]
    for outra_base in novas_bases:
        novo = sonhar(outra_base, desde=anterior)
        assert novo["fila"] == plano["fila"]
        assert novo["sha256"] != plano["sha256"]
        with pytest.raises(MemoriaErro, match="outro plano"):
            retomar_sonho(outra_base, desde=anterior, devolutivas=[bruto])
    assert retomar_sonho(original, desde=anterior, devolutivas=[bruto])["estado"] == "cobertura_completa"


def test_retomada_de_fila_vazia_nao_exige_devolutiva(repo_sonho):
    repo, anterior = repo_sonho
    catalogo = Catalogo(Fontes(repo, revisao=anterior), DATA)
    fim = retomar_sonho(catalogo, desde=anterior, devolutivas=[])
    assert fim["estado"] == "cobertura_completa" and fim["total"] == 0
    assert fim["desde_sugerido"] == anterior and fim["proximo_plano"] is None
    with pytest.raises(MemoriaErro, match="além da fila"):
        retomar_sonho(catalogo, desde=anterior, devolutivas=[b"{}"])


def test_investigacao_sobrevive_ao_corte_e_a_prova_antiga_nao_fecha_o_item(repo_sonho):
    repo, anterior = repo_sonho
    contraria = "DADOS SIMULADOS. A moeda da fonte primária não foi alterada."
    fonte = repo / FONTE
    fonte.write_text(f"{TRECHO}\n{contraria}\n", encoding="utf-8")
    revisao = _commit(repo)
    catalogo = Catalogo(Fontes(repo), DATA)
    opcoes = {"desde": anterior, "exigir_provas": True}
    plano = sonhar(catalogo, **opcoes)
    provas = [_prova(), _prova(trecho=contraria)]
    refs = [{k: p[k] for k in ("caminho", "sha256")} for p in provas]
    investigacao = {
        "pergunta": "A divergência vem da fonte ou da apresentação?",
        "hipoteses": [
            {"enunciado": "Mudança na fonte.", "apoios": [], "contrarios": [refs[1]]},
            {"enunciado": "Moeda trocada na apresentação.", "apoios": [refs[0]], "contrarios": []},
        ],
        "proximo_teste": "Comparar a unidade do FactBook com a unidade do relatório.",
    }
    padrao = {"provas": [_prova()]}
    bruto = _responder(plano, {FONTE: {"decisao": "investigar", "provas": provas,
                                      "investigacao": investigacao}}, padrao=padrao)
    fim = retomar_sonho(catalogo, **opcoes, devolutivas=[bruto])
    continuidade = json.dumps(fim["continuidade"]).encode()
    assert fim["desde_sugerido"] == revisao
    assert fim["pendencias"][0]["investigacao"] == investigacao

    (repo / "alheio.txt").write_text("DADOS SIMULADOS", encoding="utf-8")
    corte = _commit(repo)
    novo = Catalogo(Fontes(repo), DATA + timedelta(days=1))
    opcoes = {"desde": revisao, "exigir_provas": True}
    assert FONTE not in {item["id"] for item in sonhar(novo, **opcoes)["fila"]}
    com_historia = sonhar(novo, **opcoes, continuidade=continuidade)
    item = next(i for i in com_historia["fila"] if i["id"] == FONTE)
    pendencia = item["pendencia_anterior"]
    assert pendencia["origem"]["revisao"] == revisao
    assert pendencia["investigacao"] == investigacao
    assert not pendencia["na_fila_atual"]
    assert [p["situacao"] for p in pendencia["provas"]] == ["localizada", "localizada"]
    assert sum(i["id"] == FONTE for i in com_historia["fila"]) == 1
    assert com_historia["revisao"] == corte

    fonte.write_text(f"{TRECHO}\nDADOS SIMULADOS. A unidade foi corrigida no relatório.\n",
                     encoding="utf-8")
    _commit(repo)
    novo = Catalogo(Fontes(repo), DATA + timedelta(days=2))
    opcoes["desde"] = corte
    plano = sonhar(novo, **opcoes, continuidade=continuidade)
    item = next(i for i in plano["fila"] if i["id"] == FONTE)
    assert sum(i["id"] == FONTE for i in plano["fila"]) == 1
    assert [p["situacao"] for p in item["pendencia_anterior"]["provas"]] == ["localizada", "desatualizada"]
    with pytest.raises(MemoriaErro):
        conferir_sonho(novo, plano, _responder(plano, {FONTE: {"provas": [provas[1]]}}, padrao=padrao))
    solucao = _prova(trecho="DADOS SIMULADOS. A unidade foi corrigida no relatório.")
    bruto = _responder(plano, {FONTE: {"provas": [solucao]}}, padrao=padrao)
    fim = retomar_sonho(novo, **opcoes, continuidade=continuidade, devolutivas=[bruto])
    assert fim["continuidade"]["itens"] == []
    assert fim["resolucoes"][0]["provas"][0]["sha256"] == solucao["sha256"]
    assert _git(repo, "status", "--porcelain") == b""


def test_continuidade_recusa_lacre_origem_e_prova_adulterados(repo_sonho):
    from cdp.memoria_sonho import _digestir

    repo, anterior = repo_sonho
    catalogo = Catalogo(Fontes(repo), DATA)
    opcoes = {"desde": anterior, "exigir_provas": True}
    plano = sonhar(catalogo, **opcoes)
    resposta = _responder(plano, {FONTE: {"decisao": "investigar"}}, padrao={"provas": [_prova()]})
    checkpoint = conferir_sonho(catalogo, plano, resposta)["continuidade"]
    for alvo in ("lacre", "origem", "prova"):
        alterado = json.loads(json.dumps(checkpoint))
        registro = alterado["itens"][0]
        if alvo in ("lacre", "origem"):
            registro["origem"]["id"] = "docs/cdp/METODOLOGIA.md"
        else:
            registro["resposta"]["provas"] = [_prova(trecho="DADOS SIMULADOS. Trecho inexistente.")]
        if alvo != "lacre":
            alterado["sha256"] = _digestir({k: v for k, v in alterado.items() if k != "sha256"})
        with pytest.raises(MemoriaErro):
            sonhar(catalogo, **opcoes, continuidade=json.dumps(alterado).encode())


def test_propostas_podem_exceder_vagas_sem_promocao(repo_sonho):
    repo, anterior = repo_sonho
    for i in range(MAX_NOTAS - len(Fontes(repo).catalogo()) - 2):
        _gravar_nota(repo, _nota(f"retirada-{i:03}", "retirada"))
    (repo / PASTA / "id-ocupado.json").write_text("{", encoding="utf-8")
    _commit(repo)
    catalogo = Catalogo(Fontes(repo), DATA)
    plano = sonhar(catalogo, desde=anterior)
    decisoes = {f"candidata-{i}": {"decisao": "propor_candidata",
                                  "candidata": _nota(f"proposta-{i}", "candidata")}
                for i in range(2)}
    bruto = _responder(plano, decisoes)
    resposta = conferir_sonho(catalogo, plano, bruto)
    assert resposta["vagas_catalogo"] == 1
    assert [n["id"] for n in resposta["candidatas"]] == ["proposta-0", "proposta-1"]
    fim = retomar_sonho(catalogo, desde=anterior, devolutivas=[bruto])
    assert fim["candidatas"] == resposta["candidatas"]
    assert {n["id"] for n in fim["candidatas"]}.isdisjoint(catalogo.notas)
    assert _git(repo, "status", "--porcelain") == b""

    decisoes["candidata-1"]["candidata"]["id"] = "id-ocupado"
    with pytest.raises(MemoriaErro, match="ID novo"):
        conferir_sonho(catalogo, plano, _responder(plano, decisoes))


def test_retomada_recusa_id_de_candidata_repetido_em_duas_paginas(repo_sonho):
    repo, anterior = repo_sonho
    catalogo = Catalogo(Fontes(repo), DATA)
    opcoes = {"limite": 1, "desde": anterior}
    devolutivas = []
    for pagina in range(1, 3):
        plano = sonhar(catalogo, **opcoes, pagina=pagina)
        id_ = plano["fila"][0]["id"]
        decisoes = {id_: {"decisao": "propor_candidata", "candidata": _nota("repetida", "candidata")}}
        devolutivas.append(_responder(plano, decisoes))
    with pytest.raises(MemoriaErro, match="repetido entre páginas"):
        retomar_sonho(catalogo, **opcoes, devolutivas=devolutivas)


def test_modo_com_provas_muda_lacre_sem_alterar_plano_legado(repo_sonho):
    repo, anterior = repo_sonho
    catalogo = Catalogo(Fontes(repo), DATA)
    legado = sonhar(catalogo, desde=anterior)
    estrito = sonhar(catalogo, desde=anterior, exigir_provas=True)
    assert legado == sonhar(catalogo, desde=anterior, exigir_provas=False)
    assert "exigir_provas" not in legado and estrito["exigir_provas"] is True
    assert legado["fila"] == estrito["fila"] and legado["sha256"] != estrito["sha256"]
    assert conferir_sonho(catalogo, legado, _responder(legado))["ok"]
    with pytest.raises(MemoriaErro, match="outro plano"):
        retomar_sonho(catalogo, desde=anterior, exigir_provas=True, devolutivas=[_responder(legado)])
    with pytest.raises(MemoriaErro, match="manter exige ao menos uma prova literal"):
        conferir_sonho(catalogo, estrito, _responder(estrito))
    resposta = _responder(estrito, padrao={"provas": [_prova()]})
    fim = retomar_sonho(catalogo, desde=anterior, exigir_provas=True, devolutivas=[resposta])
    assert fim["estado"] == "cobertura_completa" and fim["exigir_provas"] is True


def test_prova_literal_precisa_ser_autorizada_exata_e_unica(repo_sonho):
    repo, anterior = repo_sonho
    catalogo = Catalogo(Fontes(repo), DATA)
    plano = sonhar(catalogo, desde=anterior, exigir_provas=True)
    for provas, mensagem in (
        ([_prova(caminho="docs/cdp/playbooks/SEMANAL.md")], "fora das fontes"),
        ([_prova(trecho="Trecho de teste ausente.")], "ausente ou ambíguo"),
        ([_prova(), _prova()], "prova repetida"),
        ([_prova() | {"sha256": "0" * 64}], "hash divergente"),
    ):
        with pytest.raises(ValueError, match=mensagem):
            conferir_sonho(catalogo, plano, _responder(plano, padrao={"provas": provas}))


def test_retomada_conserva_ancora_de_investigacao_e_prova_da_candidata(repo_sonho):
    repo, anterior = repo_sonho
    catalogo = Catalogo(Fontes(repo), DATA)
    opcoes = {"desde": anterior, "limite": 2, "exigir_provas": True}
    primeira = sonhar(catalogo, **opcoes)
    investigar, propor = primeira["fila"]
    decisao = {"decisao": "investigar", "motivo": "O trecho deixa uma questão para revisão."}
    proposta = _nota("proposta-conferida", "candidata")
    decisoes = {investigar["uid"]: decisao,
                propor["uid"]: {"decisao": "propor_candidata", "candidata": proposta}}
    sem_prova = _responder(primeira, decisoes)
    with pytest.raises(MemoriaErro, match="investigar exige prova literal ou diagnóstico"):
        retomar_sonho(catalogo, **opcoes, devolutivas=[sem_prova])
    decisao["provas"] = [_prova()]
    bruto = _responder(primeira, decisoes)
    parcial = retomar_sonho(catalogo, **opcoes, devolutivas=[bruto])
    pendencias = parcial["pendencias"]
    assert pendencias[0]["uid"] == investigar["uid"]
    assert pendencias[0]["provas"] == [{"caminho": FONTE, "inicio": 2, "fim": 2,
                                        "sha256": _prova()["sha256"]}]
    assert parcial["candidatas"] == [proposta]
    segunda = _responder(parcial["proximo_plano"], padrao={"provas": [_prova()]})
    fim = retomar_sonho(catalogo, **opcoes, devolutivas=[bruto, segunda])
    assert fim["estado"] == "cobertura_completa" and fim["pendencias"] == pendencias
    assert fim["candidatas"] == [proposta] and "proposta-conferida" not in catalogo.notas


def test_manter_recusa_problema_conhecido_em_outro_item_da_mesma_nota(repo_sonho):
    repo, anterior = repo_sonho
    trecho_novo = "DADOS SIMULADOS. O roteiro novo exige conferir a data de corte."
    (repo / FONTE).write_text(f"# Fonte revista\n{trecho_novo}\n", encoding="utf-8")
    _commit(repo)
    catalogo = Catalogo(Fontes(repo), DATA)
    plano = sonhar(catalogo, desde=anterior, exigir_provas=True)
    nota_id = "candidata-0"
    itens = {i["acao"]: i["uid"] for i in plano["fila"] if i["id"] == nota_id}
    padrao = {"decisao": "investigar", "provas": [_prova(trecho=trecho_novo)]}
    for acao in ("evidencia", "revisar_candidata"):
        with pytest.raises(MemoriaErro, match="manter não resolve problema conhecido"):
            conferir_sonho(catalogo, plano, _responder(plano, {itens[acao]: {"decisao": "manter"}},
                                                       padrao=padrao))


def test_diagnostico_distingue_fonte_ausente_de_catalogo_invalido(repo_sonho):
    repo, anterior = repo_sonho
    (repo / FONTE).unlink()
    (repo / PASTA / "invalida.json").write_text("{", encoding="utf-8")
    _commit(repo)
    catalogo = Catalogo(Fontes(repo), DATA)
    opcoes = {"desde": anterior, "exigir_provas": True}
    plano = sonhar(catalogo, **opcoes)
    fonte = next(i for i in plano["fila"] if i["id"] == FONTE)
    invalida = next(i for i in plano["fila"] if i["id"] == "invalida")
    assert fonte["origens"] == [{"caminho": FONTE, "sha256": None}]
    assert invalida["acao"] == "arquivo" and invalida["origens"] == []
    investigar = {"decisao": "investigar", "diagnostico": "problema_catalogo"}
    sem_fonte = {"diagnostico": "sem_fonte_disponivel"}
    decisoes = {fonte["uid"]: sem_fonte}
    bruto = _responder(plano, decisoes, padrao=investigar)
    fim = retomar_sonho(catalogo, **opcoes, devolutivas=[bruto])
    diagnosticos = {p["uid"]: p["diagnostico"] for p in fim["pendencias"]}
    assert diagnosticos[fonte["uid"]] == "sem_fonte_disponivel"
    assert diagnosticos[invalida["uid"]] == "problema_catalogo"
    with pytest.raises(MemoriaErro, match="problema do catálogo diverge"):
        conferir_sonho(catalogo, plano, _responder(plano, padrao=investigar))
    decisoes[invalida["uid"]] = sem_fonte
    with pytest.raises(MemoriaErro, match="fonte indisponível diverge"):
        conferir_sonho(catalogo, plano, _responder(plano, decisoes, padrao=investigar))


def test_fonte_legivel_nao_aceita_diagnostico_de_indisponibilidade(repo_sonho):
    repo, anterior = repo_sonho
    catalogo = Catalogo(Fontes(repo), DATA)
    plano = sonhar(catalogo, desde=anterior, exigir_provas=True)
    padrao = {"decisao": "investigar", "diagnostico": "sem_fonte_disponivel"}
    with pytest.raises(MemoriaErro, match="fonte indisponível diverge"):
        conferir_sonho(catalogo, plano, _responder(plano, padrao=padrao))
