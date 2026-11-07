"""Regressões da recuperação por passagem e do encaminhamento de estado."""

from __future__ import annotations

import hashlib

import pytest

from cdp.memoria import _fonte_atual
from cdp.memoria_avaliacao import _medir
from cdp.memoria_busca import (
    Local,
    _janelas,
    ampliar,
    ampliar_selecao,
    combinar_evidencias,
    completar_bloco,
    reunir_ancoras,
    termos_contextuais,
)


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


def test_fusao_conserva_grupos_complementares_e_ignora_janelas_repetidas():
    direta = Local("a", 1, 14, "")
    repetida = Local("a", 5, 18, "")
    principal = Local("b", 5, 8, "")
    complementar = Local("c", 42, 48, "")
    contextuais = [repetida, Local("d", 12, 25, "")]
    ancoras = [[principal, complementar]]
    assert combinar_evidencias([direta, repetida], contextuais, ancoras, 3) == [
        principal, repetida, complementar,
    ]
    assert combinar_evidencias([direta, repetida], contextuais, ancoras, 5) == [
        principal, repetida, complementar, contextuais[1], direta,
    ]
    assert combinar_evidencias([direta], [], ancoras, 1, priorizar_nota=False) == [direta]
    assert ancoras == [[principal, complementar]]


def test_ancoras_da_mesma_nota_cabem_sem_cortar_evidencia():
    linhas = tuple(f"Linha {i}" for i in range(1, 42))
    ancoras = [Local("a", 20, 24, ""), Local("a", 8, 12, ""), Local("a", 40, 41, "")]
    juntas = reunir_ancoras(ancoras, linhas)
    assert [(p.inicio, p.fim) for p in juntas] == [(5, 15), (17, 27), (37, 41)]
    juntas = reunir_ancoras([Local("a", 20, 21, ""), Local("a", 8, 12, "")], linhas)
    assert [(p.inicio, p.fim) for p in juntas] == [(8, 21)]
    assert juntas[0].sha256 == hashlib.sha256("\n".join(linhas[7:21]).encode()).hexdigest()


def test_segunda_nota_resgata_continuacao_na_mesma_fonte():
    primeira = Local("a", 1, 8, "")
    complementar = Local("a", 30, 37, "")
    continuacao = Local("a", 5, 16, "")
    direta = Local("b", 1, 14, "")
    contextual = Local("c", 3, 10, "")
    reserva = Local("d", 1, 10, "")
    assert combinar_evidencias(
        [direta, reserva], [contextual], [[primeira, complementar], [continuacao]], 5
    ) == [primeira, direta, complementar, contextual, continuacao]


def test_busca_contextual_preserva_bloco_que_cruza_limite_da_janela_lexical():
    linhas = tuple(["# Encerramento", *["" for _ in range(12)],
                    "Para reduzir a posição, veja as duas condições:",
                    "- A linha precisa ter fechamento elegível;",
                    "- a cotação deve ser da mesma linha e data.", ""])
    janelas = list(_janelas("fonte.md", linhas, contextual=True))
    bloco = next(j for j in janelas if j.bloco_inteiro)
    assert bloco.inicio == 14 and bloco.linhas == linhas[13:16]
    assert "encerr" in bloco.contexto
    assert not any(j.bloco_inteiro for j in _janelas("fonte.md", linhas))


def test_vocabulario_relaciona_parafrases_sem_confundir_superficies_de_publicacao():
    assert "@posicao-vendida" in termos_contextuais("encerrar a posição vendida")
    assert "@posicao-vendida" in termos_contextuais("recomprar o short")
    assert "@fuso" in termos_contextuais("conferir a virada de dia")
    assert "@fuso" in termos_contextuais("agendar em UTC")
    assert "@portal-publico" not in termos_contextuais("refazer o painel local")
    assert "@painel-local" not in termos_contextuais("comparar o portal do GitHub Pages")


def test_completa_bloco_preservando_a_evidencia_ja_encontrada():
    linhas = ("# Risco", "", "Confira a posição vigente antes do leilão.",
              "Depois do leilão, confira o registro de fechamento.", "", "Outro assunto.")
    recorte = Local("risco.md", 3, 3, "")
    inteiro = completar_bloco(recorte, linhas)
    assert (inteiro.inicio, inteiro.fim) == (3, 4)
    assert inteiro.sha256 == hashlib.sha256("\n".join(linhas[2:4]).encode()).hexdigest()
    grande = ("# Risco", "", "A" * 1500, "B" * 600)
    assert completar_bloco(recorte, grande) == recorte


def test_amplia_selecao_por_contencao_sem_cortar_ou_exceder_orcamento():
    linhas = {c: tuple(f"{c} {i}" for i in range(1, 21)) for c in "abcd"}
    antiga = Local("a", 8, 10, "")
    parcial = Local("a", 9, 16, "")
    completa = Local("a", 5, 16, "")
    assert ampliar_selecao([antiga], [parcial, completa], linhas.__getitem__) == [completa]
    linhas.update({c: (c * 1400,) for c in "bcd"})
    linhas["a"] = ("x" * 600, *linhas["a"][1:])
    longa = Local("a", 1, 10, "")
    base = [antiga, *(Local(c, 1, 1, "") for c in "bcd")]
    assert ampliar_selecao(base, [longa], linhas.__getitem__) == base


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
