import json
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest

from cdp.memoria import MemoriaErro, _sha
from cdp.memoria_busca import localizar
from cdp.memoria_pontes import MAPA_PONTES
from cdp.memoria_roteamento import (
    conferir_selecao_roteada,
    preparar_rota,
    preparar_selecao_roteada,
)
from cdp.memoria_selecao import _lacre, aplicar

_DATA = date(2026, 11, 7)
_FONTE = "docs/cdp/FONTE.md"
_DOADORA = "docs/cdp/OUTRO.md"
_TRECHO = "A prova do portal tem assinatura e data verificáveis."


@pytest.fixture
def cenario():
    linhas = {
        _FONTE: ("O procedimento local descreve a checagem do portal.",),
        _DOADORA: ("Conteúdo adjacente.", _TRECHO, "Outra linha adjacente."),
    }
    ativa = {
        "id": "conferir-portal", "origem": "status", "escopos": ["calibracao"],
        "gatilhos": ["portal"], "revisada_em": "2026-11-01", "rever_em": "2026-12-01",
        "evidencia": {"caminho": _DOADORA, "trecho": _TRECHO, "sha256": _sha(_TRECHO)},
    }
    mapa = {"versao": 1, "pontes": [ativa]}
    leituras = []

    def ler(caminho, _limite):
        assert caminho == MAPA_PONTES
        leituras.append(caminho)
        return json.dumps(mapa).encode()

    def ler_linhas(caminho):
        leituras.append(caminho)
        return linhas[caminho]

    fontes = SimpleNamespace(revisao="a" * 40, trabalho=False, ler=ler, linhas=ler_linhas)
    ref = localizar(_FONTE, 1, linhas[_FONTE])
    catalogo = SimpleNamespace(
        fontes=fontes, data=_DATA,
        fontes_por_escopo={"calibracao": [_FONTE], "status": [_DOADORA]},
        indice=SimpleNamespace(buscar=lambda *a, **kw: [], estruturais=lambda *a, **kw: [],
                              simbolos=lambda *a, **kw: [], reforcos=lambda *a, **kw: []),
        buscar=lambda *a, **kw: {
            "revisao": fontes.revisao, "data": _DATA.isoformat(), "escopo": "calibracao",
            "destino_atual": None, "orientacao_atual": None,
            "fontes": [], "notas": [], "passagens": [ref.json()],
        },
    )
    rota = preparar_rota(fontes, _DATA, "calibracao", "Como verificar o portal?", 5)
    return fontes, catalogo, rota, mapa, linhas, leituras


def _triagem(rota, intencao="evidencia", destino=None):
    return {"lacre": rota["lacre"], "intencao": intencao, "destino_atual": destino}


def _bruto(obj):
    return json.dumps(obj).encode()


def test_ponte_lacra_so_o_trecho_e_conferencia_reproduz_o_pacote(cenario):
    fontes, c, rota, _, _, leituras = cenario
    triagem = _triagem(rota)
    comum = preparar_selecao_roteada(fontes, rota, _bruto(triagem), catalogo=c)
    assert _DOADORA not in leituras and MAPA_PONTES not in leituras
    pacote = preparar_selecao_roteada(fontes, rota, _bruto(triagem), catalogo=c, com_pontes=True)
    assert pacote["fontes_permitidas"] == comum["fontes_permitidas"] == [_FONTE]
    assert pacote["candidatas"][:-1] == comum["candidatas"]
    assert pacote["pontes"] == [{"id": "conferir-portal", "origem": "status", "candidata": 2}]
    assert pacote["candidatas"][-1]["trecho"] == _TRECHO
    assert pacote["candidatas"][-1]["inicio"] == pacote["candidatas"][-1]["fim"] == 2

    escolha = {"lacre": pacote["lacre"], "ids": [2]}
    envelope = {"triagem": triagem, "selecao": escolha}
    leituras.clear()
    resultado = aplicar(pacote, _bruto(escolha), ler=fontes.linhas)
    assert leituras == []
    assert resultado["passagens"] == [
        {"caminho": _DOADORA, "inicio": 2, "fim": 2, "sha256": _sha(_TRECHO)}
    ]
    assert conferir_selecao_roteada(fontes, rota, _bruto(envelope), catalogo=c,
                                    com_pontes=True)["passagens"] == resultado["passagens"]
    with pytest.raises(MemoriaErro, match="lacre"):
        conferir_selecao_roteada(fontes, rota, _bruto(envelope), catalogo=c)

    escolha = {"lacre": pacote["lacre"], "ids": [], "intencao": "evidencia",
               "recortes": [{"caminho": _DOADORA, "inicio": 1, "fim": 3}]}
    with pytest.raises(MemoriaErro, match="fora do escopo"):
        aplicar(pacote, _bruto(escolha), ler=fontes.linhas)

    sem_autorizacao = deepcopy(pacote)
    del sem_autorizacao["pontes"]
    sem_autorizacao["lacre"] = _lacre(sem_autorizacao)
    with pytest.raises(MemoriaErro, match="esquema inválido"):
        aplicar(sem_autorizacao, _bruto({"lacre": sem_autorizacao["lacre"], "ids": [2]}))


@pytest.mark.parametrize(("intencao", "destino"), [
    ("estado_atual", "portal-publicado"), ("fora_escopo", None), ("indeterminado", None),
])
def test_ponte_nao_consulta_o_mapa_nem_a_fonte_sem_rota_documental(cenario, intencao, destino):
    fontes, c, rota, _, _, leituras = cenario
    with pytest.raises(MemoriaErro, match="triagem de evidência"):
        preparar_selecao_roteada(fontes, rota, _bruto(_triagem(rota, intencao, destino)),
                                 catalogo=c, com_pontes=True)
    assert leituras == []


@pytest.mark.parametrize("falha", ["prazo", "origem", "mudou", "duplicou", "gatilho"])
def test_ponte_ignora_trecho_desatualizado_ou_sem_autorizacao(cenario, falha):
    fontes, c, rota, mapa, linhas, leituras = cenario
    if falha == "prazo":
        mapa["pontes"][0]["rever_em"] = _DATA.isoformat()
    elif falha == "origem":
        c.fontes_por_escopo["status"].clear()
    elif falha == "mudou":
        linhas[_DOADORA] = ("Versão posterior da passagem.",)
    elif falha == "duplicou":
        linhas[_DOADORA] = (_TRECHO, _TRECHO)
    else:
        mapa["pontes"][0]["gatilhos"] = ["pregão antecipado"]
    pacote = preparar_selecao_roteada(fontes, rota, _bruto(_triagem(rota)), catalogo=c, com_pontes=True)
    assert pacote["pontes"] == []
    assert len(pacote["candidatas"]) == 1
    if falha in ("prazo", "origem", "gatilho"):
        assert _DOADORA not in leituras
