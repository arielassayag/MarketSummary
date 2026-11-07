from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest

from cdp.memoria import MemoriaErro
from cdp.memoria_busca import localizar
from cdp.memoria_selecao import LIMITE_CANDIDATAS, MAX_BYTES_RESPOSTA, aplicar, preparar

_REVISAO = "a" * 40
_DATA = date(2026, 11, 7)
_CONSULTA = "Como conferir o fechamento diário do CDP?"


def _catalogo(*textos, orientacao=None, sem_contexto=False):
    fontes = {f"docs/cdp/FONTE{i}.md": (texto,) for i, texto in enumerate(textos, 1)}
    locais = [localizar(caminho, 1, linhas) for caminho, linhas in fontes.items()]
    base = {
        "revisao": _REVISAO, "data": _DATA.isoformat(), "escopo": "diario",
        "passagens": [] if sem_contexto else [locais[0].json()],
        "fontes": [], "notas": [], "orientacao_atual": orientacao,
    }
    if len(locais) > 4 and not sem_contexto and not orientacao:
        base["notas"] = [{"evidencias": [locais[4].json()]}]

    def buscar(escopo, consulta, limite):
        assert escopo == "diario" and consulta == _CONSULTA and 1 <= limite <= 5
        return deepcopy(base)

    def buscar_amplo(escopo, consulta, limite, *, contextual=False):
        assert not (sem_contexto or orientacao)
        return locais[1:2] if contextual else locais[:1]

    def estruturais(escopo, consulta, *, completas=False):
        assert not (sem_contexto or orientacao)
        return locais[3:4] if completas else locais[2:3]

    def simbolos(escopo, consulta):
        assert not (sem_contexto or orientacao)
        return locais[5:6]

    return SimpleNamespace(
        data=_DATA, buscar=buscar,
        fontes=SimpleNamespace(revisao=_REVISAO, trabalho=False, linhas=fontes.__getitem__),
        indice=SimpleNamespace(buscar=buscar_amplo, estruturais=estruturais, simbolos=simbolos),
    )


def _resposta(pacote, ids, **extras):
    return json.dumps({"lacre": pacote["lacre"], "ids": ids, **extras}).encode()


def test_pacote_lacra_fontes_e_aplica_so_as_referencias_escolhidas():
    catalogo = _catalogo("Base", "Contexto", "Estrutura", "Seção inteira", "Âncora curada",
                        "Símbolo canônico")
    pacote = preparar(catalogo, "diario", _CONSULTA, 5)

    assert preparar(catalogo, "diario", _CONSULTA, 5) == pacote
    assert [p["trecho"] for p in pacote["candidatas"]] == [
        "Base", "Âncora curada", "Contexto", "Estrutura", "Seção inteira", "Símbolo canônico",
    ]
    assert [p["id"] for p in pacote["candidatas"]] == [1, 2, 3, 4, 5, 6]
    assert pacote["orcamento_bytes"] == 4500
    assert all(p["bytes"] == len(p["trecho"].encode()) for p in pacote["candidatas"])
    saida = aplicar(pacote, _resposta(pacote, [5, 2]))
    esperadas = [
        {k: p[k] for k in ("caminho", "inicio", "fim", "sha256")}
        for p in (pacote["candidatas"][4], pacote["candidatas"][1])
    ]
    assert saida == {**pacote["base"], "passagens": esperadas}
    assert pacote["base"]["passagens"] != saida["passagens"]


@pytest.mark.parametrize("orientacao,sem_contexto", [("Leia o relatório oficial.", False), (None, True)])
def test_estado_ou_ausencia_de_contexto_nao_ampliam_busca(orientacao, sem_contexto):
    catalogo = _catalogo("Base", orientacao=orientacao, sem_contexto=sem_contexto)
    pacote = preparar(catalogo, "diario", _CONSULTA, 5)
    assert pacote["candidatas"] == []
    assert aplicar(pacote, _resposta(pacote, []))["passagens"] == []
    with pytest.raises(MemoriaErro, match="desconhecido"):
        aplicar(pacote, _resposta(pacote, [1]))


@pytest.mark.parametrize(
    "ids,extras",
    [([1, 1], {}), ([False], {}), ([99], {}), ([1, 2, 3], {}), ([1], {"trecho": "novo"})],
)
def test_resposta_fechada_limite_e_ids(ids, extras):
    pacote = preparar(_catalogo("Base", "Contexto", "Estrutura"), "diario", _CONSULTA, 2)
    with pytest.raises(MemoriaErro):
        aplicar(pacote, _resposta(pacote, ids, **extras))


def test_lacre_rejeita_troca_de_consulta_e_chaves_repetidas():
    pacote = preparar(_catalogo("Base"), "diario", _CONSULTA, 5)
    resposta = _resposta(pacote, [1])
    with pytest.raises(MemoriaErro, match="lacre"):
        aplicar({**pacote, "consulta": "Outra pergunta"}, resposta)
    alterado = deepcopy(pacote)
    alterado["candidatas"][0]["bytes"] += 1
    with pytest.raises(MemoriaErro, match="esquema"):
        aplicar(alterado, resposta)
    with pytest.raises(MemoriaErro, match="repetida"):
        aplicar(pacote, resposta[:-1] + b', "ids": []}')
    with pytest.raises(MemoriaErro, match="limite de bytes"):
        aplicar(pacote, b" " * (MAX_BYTES_RESPOSTA + 1))


def test_selecao_aplica_orcamento_utf8_sem_truncar():
    catalogo = _catalogo("á" * 850, "é" * 850, "ô" * 850)
    pacote = preparar(catalogo, "diario", _CONSULTA, 5)
    assert len(aplicar(pacote, _resposta(pacote, [1, 2]))["passagens"]) == 2
    with pytest.raises(MemoriaErro, match="4.500"):
        aplicar(pacote, _resposta(pacote, [1, 2, 3]))


def test_teto_do_pacote_preserva_as_vinte_janelas_canonicas():
    catalogo = _catalogo(*(f"Passagem {i}" for i in range(100)))
    locais = [localizar(caminho, 1, catalogo.fontes.linhas(caminho))
              for caminho in (f"docs/cdp/FONTE{i}.md" for i in range(1, 101))]
    catalogo.indice.buscar = lambda *a, contextual=False: (
        locais[20:40] if contextual else locais[:20]
    )
    catalogo.indice.estruturais = lambda *a, completas=False: (
        locais[60:80] if completas else locais[40:60]
    )
    catalogo.indice.simbolos = lambda *a: locais[80:]

    pacote = preparar(catalogo, "diario", _CONSULTA, 5)
    caminhos = {p["caminho"] for p in pacote["candidatas"]}
    assert len(pacote["candidatas"]) == len(caminhos) == LIMITE_CANDIDATAS
    assert {p.caminho for p in locais[:40]} <= caminhos
    assert {p.caminho for p in locais[80:85]} <= caminhos
