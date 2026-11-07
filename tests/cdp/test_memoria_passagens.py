"""Regressões da recuperação por passagem e do encaminhamento de estado."""

from __future__ import annotations

import hashlib

import pytest

from cdp.memoria import _fonte_atual
from cdp.memoria_avaliacao import _medir
from cdp.memoria_busca import Local, ampliar, intercalar


def test_avaliacao_exige_trecho_inteiro_e_todos_os_grupos():
    fonte = "docs/cdp/playbooks/DIARIO.md"
    a = Local(fonte, 10, 12, "")
    b = Local(fonte, 40, 42, "")
    primeira = Local(fonte, 9, 13, "")
    parcial = Local(fonte, 35, 41, "")
    completa = Local(fonte, 35, 44, "")
    parcial_medida = _medir([primeira, parcial], [[a], [b]])
    assert parcial_medida["completo_1"] is False
    assert parcial_medida["completo_3"] is False
    assert parcial_medida["cobertura_3"] == 0.5
    assert _medir([primeira, completa], [[a], [b]])["completo_3"] is True


def test_intercalacao_preserva_tres_diretas_e_ignora_redundancia():
    diretas = [Local("a", i, i + 13, "") for i in (1, 40, 60, 80)]
    repetida = Local("a", 3, 7, "")
    nova = Local("b", 5, 8, "")
    ancoras = [[repetida, nova]]
    assert intercalar(diretas, ancoras, 3) == diretas[:3]
    assert intercalar(diretas, ancoras, 5) == [*diretas[:3], nova, diretas[3]]
    assert ancoras == [[repetida, nova]]


def test_contexto_adjacente_preserva_ancora_e_hash():
    linhas = tuple(f"Linha {i}" for i in range(1, 20))
    a = ampliar(Local("a", 5, 9, ""), linhas)
    assert (a.inicio, a.fim) == (2, 12)
    assert a.sha256 == hashlib.sha256("\n".join(linhas[1:12]).encode()).hexdigest()


@pytest.mark.parametrize("consulta", [
    "Quem é o executor designado atual?",
    "Onde está o retorno em dólar do índice agora?",
    "Qual foi a última cotação do índice local?",
    "O e-mail do fechamento já chegou?",
])
def test_estado_pede_fonte_oficial(consulta):
    assert _fonte_atual(consulta)


@pytest.mark.parametrize("consulta", [
    "Como confiro se o portal está atualizado?",
    "No dia de montagem o monitor mede a carteira vigente?",
    "Qual é a regra de uso da moeda no comentário?",
])
def test_pergunta_de_procedimento_pode_recuperar_memoria(consulta):
    assert _fonte_atual(consulta) is None
