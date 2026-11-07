"""Regressões para o gabarito privado de destinos de consultas de estado."""

from datetime import date
from importlib import import_module
from pathlib import Path

import pytest
from pydantic import ValidationError

from cdp.memoria import Catalogo, Fontes
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
