from hashlib import sha256

from cdp.memoria_busca import BYTES_PASSAGEM, LINHAS_PASSAGEM, localizar
from cdp.memoria_reforcos import IndiceReforcos
from cdp.memoria_secoes import IndiceSecoes


def test_busca_por_simbolo_inclui_retorno_de_funcao_descrita_na_docstring():
    caminho = "src/cdp/agenda.py"
    linhas = ("def pendentes():", '    """Seleção de pregões sem registro diário."""',
              *("    pass",) * 15, "    return fechamentos")
    indice = IndiceSecoes([(caminho, linhas)])
    candidatas = indice.simbolos("Como selecionar pregões sem registro diário?")
    assert any(p.caminho == caminho and p.fim == len(linhas) for p in candidatas)
    assert all(p.fim - p.inicio + 1 <= 14 for p in candidatas)


def test_busca_por_simbolo_prioriza_assinatura_que_nomeia_acao_e_formato():
    linhas = ("def exportar_aplicativo():", '    """Exportar agenda em JSON, com campos calculados."""',
              "    return carregar_dados()", "", "def exportar_json():",
              "    return {'quando': calcular_horario()}")
    indice = IndiceSecoes([("src/cdp/rotinas.py", linhas)])
    (primeira, *_) = indice.simbolos("Quais campos vêm ao exportar a agenda em JSON?")

    assert (primeira.inicio, primeira.fim) == (5, 6)


def test_reforcos_completam_item_e_condicao_nas_fontes_permitidas():
    roteiro = "docs/cdp/ROTINA.md"
    codigo = "src/cdp/rotina.py"
    fontes = {
        roteiro: ("# Agenda", "- Confira o limite da fila.", "  Use o limite efetivo.",
                  "- Só então trate os fechamentos."),
        codigo: ("def conferir_risco():", "    if risco and pregao:",
                 "        reporte_risco()", "    return risco"),
    }
    base = [localizar(roteiro, 3, fontes[roteiro][2:]),
            localizar(codigo, 3, fontes[codigo][2:]),
            localizar("docs/cdp/FORA.md", 1, ("risco e limite",))]
    indice = IndiceReforcos(fontes.__getitem__, fontes)
    saida = indice.buscar("Qual limite da fila e condição de risco no pregão?", base)

    assert saida == indice.buscar("Qual limite da fila e condição de risco no pregão?", base)
    assert not set(base) & set(saida)
    assert any(p.caminho == roteiro and p.inicio == 2 and p.fim >= 3 for p in saida)
    assert any(p.caminho == codigo and p.inicio <= 2 and p.fim >= 3 for p in saida)


def test_busca_por_secoes_diversifica_fontes_e_recupera_vizinha():
    fontes = {
        "Roteiro.md": (
            "# Publicação",
            "",
            "Confira o recibo e a publicação autenticada.",
            "",
            "## Retomada",
            "",
            "Uma nova execução preserva a trilha anterior.",
        ),
        "Auditoria.md": (
            "# Verificação",
            "",
            "O recibo da publicação autenticada inclui a revisão.",
        ),
    }
    indice = IndiceSecoes(fontes.items())
    passagens = indice.buscar("Como conferir o recibo da publicação?")
    assert {p.caminho for p in passagens[:3]} == set(fontes)
    assert any(p.caminho == "Roteiro.md" and p.inicio <= 7 <= p.fim for p in passagens)
    assert indice.buscar("Como conferir o recibo da publicação?", 2) == passagens[:2]


def test_passagens_sao_literais_e_respeitam_os_limites():
    linhas = (
        "# Validação",
        "",
        "Confira o manifesto antes de concluir a revisão.",
        "",
        "```sh",
        "# Comando de validação, parte do bloco",
        "cdp verify",
        "```",
        "",
        "Validação " + "ç" * BYTES_PASSAGEM,
        "",
        *(f"Passo {i}: manifeste a revisão." for i in range(30)),
    )
    passagens = IndiceSecoes([("Roteiro.md", linhas)]).buscar("Manifesto e comando de validação")
    assert any(p.inicio <= 5 and p.fim >= 8 for p in passagens)
    for p in passagens:
        trecho = linhas[p.inicio - 1:p.fim]
        bruto = "\n".join(trecho).encode()
        assert p.caminho == "Roteiro.md"
        assert len(trecho) <= LINHAS_PASSAGEM
        assert len(bruto) <= BYTES_PASSAGEM
        assert p.sha256 == sha256(bruto).hexdigest()


def test_compactas_preservam_a_secao_inteira_e_pulam_excesso_de_bytes():
    linhas = (
        "# Dados de mercado",
        "",
        "A observação ausente deve continuar ausente.",
        "",
        "Considere somente informações disponíveis até o corte.",
        "# Observação sem cotação",
        "Observação ausente sem cotação " + "á" * BYTES_PASSAGEM,
    )
    indice = IndiceSecoes([("Dados.md", linhas), ("rascunho.py", linhas[:5])])
    passagens = indice.compactas("Observação ausente", limite=1)

    assert len(passagens) == 1
    assert indice.compactas("Observação ausente") == passagens
    passagem = passagens[0]
    assert (passagem.caminho, passagem.inicio, passagem.fim) == ("Dados.md", 1, 5)
    assert passagem.sha256 == sha256("\n".join(linhas[:5]).encode()).hexdigest()
