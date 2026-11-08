"""Controles de destinos de estado e revalidação de provas documentais."""

import hashlib
import json
import subprocess
from datetime import date
from importlib import import_module
from pathlib import Path

import pytest
from pydantic import ValidationError

from cdp import memoria_avaliacao as avaliacao
from cdp.memoria import Catalogo, Fontes, MemoriaErro, MemoriaGitIndisponivel
from cdp.memoria_avaliacao import CasoReservado, _medir_destino

_CASO = {
    "id": "consulta-executor",
    "escopo": "desenvolvimento",
    "consulta": "Quem é o executor designado do CDP neste momento?",
    "tipo": "estado_atual",
    "grupos": [],
}


@pytest.mark.parametrize("campos", [
    {"destinos_aceitos": []},
    {"destinos_aceitos": ["a1", "a2", "a3", "a4", "a5"]},
    {"destinos_aceitos": ["estado-executor", "estado-executor"]},
    {"destinos_aceitos": ["Comando não canônico"]},
    {"destinos_aceitos": ["estado-executor"], "tipo": "fora_escopo"},
])
def test_gabarito_de_destino_exige_consulta_de_estado_e_codigos_validos(campos):
    with pytest.raises(ValidationError):
        CasoReservado.model_validate({**_CASO, **campos})


def test_avaliacao_cobra_destino_exato_encaminhamento_e_contexto_vazio():
    caso = CasoReservado.model_validate({**_CASO, "destinos_aceitos": ["estado-executor", "executor-remoto"]})
    base = {"destino_atual": "executor-remoto", "orientacao_atual": "Consulte a fonte.",
            "fontes": [], "notas": [], "passagens": []}
    criterio = "estado_destino_correto_sem_contexto"
    assert _medir_destino(caso, base)[criterio]
    for campo, valor in (
        ("destino_atual", "estado-agenda"), ("orientacao_atual", None),
        ("fontes", [{"caminho": "AGENTS.md"}]), ("notas", [{}]), ("passagens", [{}]),
    ):
        assert not _medir_destino(caso, {**base, campo: valor})[criterio]
    assert _medir_destino(CasoReservado.model_validate(_CASO), {}) == {}


def test_destino_fica_fora_do_pacote_e_erros_reprovam_o_ensaio(monkeypatch):
    raiz = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(raiz / "scripts"))
    guiada = import_module("cdp_memoria_guiada_avaliar")
    auditor = import_module("cdp_memoria_auditar_guiada")
    catalogo = Catalogo(Fontes(raiz), date(2026, 11, 7))

    for esperado, acerto in (("estado-executor", True), ("estado-agenda", False)):
        caso = CasoReservado.model_validate({**_CASO, "destinos_aceitos": [esperado]})
        pacote, publico, _ = guiada._pacote(catalogo, ("sintetica", "executor", caso, ""), "0001",
                                           explorar_fontes=True)
        assert b"destinos_aceitos" not in publico and b"destino_atual" not in publico
        resposta = {"lacre": pacote["lacre"], "ids": [], "intencao": "estado_atual"}
        medido = guiada._medir_caso(catalogo, caso, [], "executor", "sintetica")
        selecao = guiada._medir_guiada(catalogo, pacote, resposta, [], caso)
        medido["modos"]["guiada"] = selecao
        for modo in ("memoria", "guiada"):
            assert medido["modos"][modo]["destino_atual"] == "estado-executor"
            assert medido["modos"][modo]["destino_aceito"] is acerto
        assert guiada._resumir([medido])["integral"] is acerto
        medido["modos"]["guiada"] = {k: v for k, v in selecao.items() if k not in auditor._CAMPOS_DESTINO}
        assert not guiada._resumir([medido])["integral"]
        assert guiada._resumir([medido])["modos"]["guiada"]["estado_destino_n"] == 1
        assert auditor._conferir_destino(selecao, [esperado], True) == (acerto, acerto)
        with pytest.raises(AssertionError):
            auditor._conferir_destino({**selecao, "destino_aceito": not acerto}, [esperado], True)


def test_classificacao_evidencia_vazia_nao_conta_como_abstencao_externa(monkeypatch):
    raiz = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(raiz / "scripts"))
    guiada = import_module("cdp_memoria_guiada_avaliar")
    sem_contexto = {"abstencao": True, "encaminhou": False}
    for intencao, esperado in (("evidencia", False), ("fora_escopo", True)):
        externo = {"tipo": "fora_escopo", "modos": {
            "guiada": {**sem_contexto, "intencao": intencao},
            "direta": sem_contexto, "memoria": sem_contexto,
        }}
        assert guiada._resumir([externo])["integral"] is esperado


_FONTE = "docs/cdp/AUTOMACAO.md"
_ANTES = "A rotina recusa a gravação quando a trava está inacessível e aguarda a reserva."
_DEPOIS = "Com a trava inacessível, a rotina recusa a gravação."
_RESERVA = "A reserva da montagem consulta a trava no próximo disparo aplicável."
_INTACTA = "O executor comprova a origem das publicações usando recibos."


def _evidencia(trecho):
    return {"caminho": _FONTE, "trecho": trecho, "sha256": hashlib.sha256(trecho.encode()).hexdigest()}


@pytest.fixture
def ensaio_revalidacao(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args]).decode().strip()

    def commit():
        git("add", ".")
        git("-c", "user.email=teste@example.invalid", "-c", "user.name=Teste", "-c", "commit.gpgsign=false",
            "commit", "-qm", "DADOS SIMULADOS")
        return git("rev-parse", "HEAD")

    def gravar(caminho, bruto):
        destino = tmp_path / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(bruto)

    git("init", "-q")
    casos = [
        {"id": "regra-trava", "escopo": "operador", "tipo": "evidencia",
         "consulta": "Como a rotina trata a trava inacessível na reserva da montagem?",
         "grupos": [[_evidencia(_ANTES)]]},
        {"id": "origem-publicacao", "escopo": "operador", "tipo": "evidencia",
         "consulta": "Como o executor comprova a origem das publicações?", "grupos": [[_evidencia(_INTACTA)]]},
        {"id": "fora-escopo", "escopo": "operador", "tipo": "fora_escopo",
         "consulta": "Onde consultar o cardápio da cantina?", "grupos": []},
    ]
    bruto = json.dumps({"versao": 1, "data": "2026-11-07", "casos": casos}).encode()
    gravar(avaliacao.CORPUS, bruto)
    gravar(_FONTE, f"# DADOS SIMULADOS\n\n{_ANTES}\n\n{_INTACTA}\n".encode())
    anterior = commit()
    gravar(_FONTE, f"# DADOS SIMULADOS\n\n{_DEPOIS}\n\n{_RESERVA}\n\n{_INTACTA}\n".encode())
    alvo = commit()

    class CatalogoSintetico:
        problemas = []
        fontes_por_escopo = {"operador": (_FONTE,)}

        def __init__(self, fontes, data):
            self.indice = avaliacao.BuscaCanonica(fontes, self.fontes_por_escopo)

        def buscar(self, escopo, consulta, limite):
            return {"passagens": [p.json() for p in self.indice.buscar(escopo, consulta, limite)],
                    "orientacao_atual": None, "notas": []}

    monkeypatch.setattr(avaliacao, "Catalogo", CatalogoSintetico)
    monkeypatch.setattr(avaliacao, "ONTEM", anterior)
    fontes = Fontes(tmp_path, revisao=alvo)
    manifesto = {"versao": 1, "revisao_alvo": alvo, "sha256_corpus": hashlib.sha256(bruto).hexdigest(),
                 "casos": [{"id": "regra-trava", "justificativa": "A prova atual está em dois trechos.",
                            "grupos": [[_evidencia(_DEPOIS)], [_evidencia(_RESERVA)]]}]}
    return fontes, manifesto


def test_revalidacao_retem_ouro_historico_e_separa_cortes(ensaio_revalidacao):
    fontes, manifesto = ensaio_revalidacao
    historico = avaliacao.avaliar_reservada(Fontes(fontes.raiz, revisao=avaliacao.ONTEM))
    assert "revalidacao" not in historico and set(historico["resumo"]) == set(avaliacao.MODOS)
    with pytest.raises(MemoriaErro, match="gabarito indisponível para regra-trava"):
        avaliacao.avaliar_reservada(fontes)

    bruto = json.dumps(manifesto).encode()
    resultado = avaliacao.avaliar_reservada(fontes, revalidacao=bruto)
    prova, = resultado["revalidacao"]["casos"]
    assert resultado["revalidacao"]["sha256"] == hashlib.sha256(bruto).hexdigest()
    assert resultado["revalidacao"]["casos_intactos"] == 2
    assert resultado["revisoes"]["corpus"] == historico["revisoes"]["corpus"]
    assert prova["grupos_ontem"][0][0]["sha256"] == _evidencia(_ANTES)["sha256"]
    assert [grupo[0]["sha256"] for grupo in prova["grupos_hoje"]] == [
        _evidencia(_DEPOIS)["sha256"], _evidencia(_RESERVA)["sha256"],
    ]
    linha = resultado["casos"][0]
    assert linha["tipo"] == "evidencia" and linha["grupos_ontem"] == 1 and linha["grupos"] == 2
    assert linha["modos"]["ontem"] == historico["casos"][0]["modos"]["ontem"]
    intactas = resultado["resumo"]["provas_intactas"]
    assert {modo: med["perguntas_com_evidencia"] for modo, med in intactas.items()} == dict.fromkeys(avaliacao.MODOS, 1)
    revalidadas = resultado["resumo"]["provas_revalidadas"]
    assert {modo: med["perguntas_com_evidencia"] for modo, med in revalidadas.items()} == {"direta": 1, "memoria": 1}


@pytest.mark.parametrize(("campo", "valor", "motivo"), [
    ("revisao_alvo", "f" * 40, "diverge da revisão"),
    ("sha256_corpus", "f" * 64, "diverge da revisão"),
    ("versao", True, "manifesto de revalidação inválido"),
    ("id", "fora-escopo", "exige um caso documental"),
    ("id", "fora-do-corpus", "exige um caso documental"),
    ("id", "origem-publicacao", "gabarito original intacto"),
    ("tipo", "fora_escopo", "manifesto de revalidação inválido"),
    ("grupos", [[_evidencia("Trecho inexistente na revisão alvo.")]], "gabarito indisponível para regra-trava"),
    ("grupos", [[_evidencia(_DEPOIS)], [_evidencia(_DEPOIS)]], "grupos revalidados inválidos"),
])
def test_revalidacao_recusa_manifesto_invalido(ensaio_revalidacao, campo, valor, motivo):
    fontes, manifesto = ensaio_revalidacao
    alvo = manifesto if campo in manifesto else manifesto["casos"][0]
    alvo[campo] = valor
    with pytest.raises(MemoriaErro, match=motivo):
        avaliacao.avaliar_reservada(fontes, revalidacao=json.dumps(manifesto).encode())


def test_revalidacao_recusa_duplicatas_e_excesso(ensaio_revalidacao):
    fontes, manifesto = ensaio_revalidacao
    valido = json.dumps(manifesto).encode()
    manifesto["casos"] *= 2
    repeticao = json.dumps(manifesto).encode()
    for bruto in (repeticao, valido.replace(b'"versao": 1', b'"versao": 1, "versao": 1')):
        with pytest.raises(MemoriaErro, match="manifesto de revalidação inválido"):
            avaliacao.avaliar_reservada(fontes, revalidacao=bruto)
    with pytest.raises(MemoriaErro, match="bytes limitados"):
        avaliacao.avaliar_reservada(fontes, revalidacao=b" " * (avaliacao.MAX_BYTES_REVALIDACAO + 1))


def test_revalidacao_nao_substitui_falha_de_infraestrutura(ensaio_revalidacao, monkeypatch):
    fontes, manifesto = ensaio_revalidacao
    localizar = avaliacao._localizar

    def indisponivel(origem, evidencia):
        if origem.revisao == fontes.revisao and evidencia.trecho == _ANTES:
            raise MemoriaGitIndisponivel("objeto indisponível")
        return localizar(origem, evidencia)

    monkeypatch.setattr(avaliacao, "_localizar", indisponivel)
    with pytest.raises(MemoriaErro, match="gabarito indisponível para regra-trava") as erro:
        avaliacao.avaliar_reservada(fontes, revalidacao=json.dumps(manifesto).encode())
    assert isinstance(erro.value.__cause__, MemoriaGitIndisponivel)
