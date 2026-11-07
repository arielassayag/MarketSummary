from datetime import date
from types import SimpleNamespace

import pytest

from cdp.memoria import Catalogo, _destino_atual, _fonte_atual, _pedido_fora_do_escopo
from cdp.memoria_busca import Local, normalizar


@pytest.mark.parametrize(("consulta", "origem"), [
    ("Informe a versão que entrou no Pages nesta tarde.", "portal servido"),
    ("Diga o Sharpe observado no relatório da rodada anterior.", "metrics.json"),
    ("Que hash consta no manifesto do ensaio vigente?", "manifesto"),
    ("Liste as notas ativas na fila de cobertura.", "nota agenda"),
    ("O responsável pela trava já encerrou a execução?", "estado e a agenda"),
    ("Que aplicativo gravou o último commit de fechamento?", "CDP-Harness"),
    ("Traga a composição da prévia registrada para a montagem de hoje.", "proposta"),
    ("Quanto rendeu a carteira na data de ontem?", "FactBook"),
    ("Liste os alertas ativos no monitor desta manhã.", "relatório do monitor"),
    ("Liste os alertas ativos no monitor.", "relatório do monitor"),
    ("Quantos longs estão na carteira vigente?", "carteira efetivada no livro"),
    ("Qual e-mail saiu hoje?", "trilha de entrega"),
    ("Qual carteira está efetivada no momento?", "booked.json"),
    ("Informe a liquidez medida no fechamento.", "FactBook"),
    ("O SHA-256 da captura que acabamos de gerar confere com o manifesto?", "verificação do snapshot"),
    ("Restam quantos segundos de validade para a trava distribuída?", "cdp trava ver"),
    ("Que teste falhou no portal que acabou de subir?", "portal servido"),
    ("O portal já está exibindo a revisão do remoto?", "portal servido"),
    ("Quais emissores já tiveram os resultados refletidos no retrato?", "retrato da cobertura"),
    ("Qual frente de desenvolvimento do CDP ficou para a próxima sessão?", "EM_ANDAMENTO.md"),
    ("Quem ocupa a função de executor hoje e este clone está registrado como ele?", "executor.designado"),
    ("A escrita do executor foi desabilitada no remoto?", "executor.yaml"),
    ("Quais fechamentos a rotina ainda deve registrar?", "fechamentos_pendentes"),
    ("Os preços-alvo mudaram no último retrato completo?", "retrato da cobertura"),
    ("O que diferencia o relatório de hoje do monitor de risco do de ontem?", "relatório do monitor"),
    ("No resumo de hoje do monitor, quais saídas mostram o que ficou retido?", "relatório do monitor"),
    ("A entrega do relatório já saiu hoje?", "trilha de entrega"),
    ("Qual autoria consta na última tese semanal publicada?", "tese_publicada.json"),
    ("Na última tese da carteira publicada, quem figura como autor?", "WEEKLY_THESIS"),
])
def test_consulta_observada_indica_a_fonte_da_tarefa(consulta, origem):
    orientacao = _fonte_atual(consulta)
    assert orientacao and origem in orientacao


@pytest.mark.parametrize(("consulta", "codigo", "origem"), [
    ("Na justificativa que foi publicada para a carteira que está valendo, que acontecimento levaria o CDP a rever a posição em Vale?",
     "tese-publicada", "tese_publicada.json"),
    ("No próximo dia de pregão, qual monitoramento do CDP aparece primeiro na programação da tarde e para que horas está marcado?",
     "agenda-rotinas", "rotinas proximas"),
    ("No estado desta cópia do CDP, por quem e desde quando consta designado o responsável por gravar o livro?",
     "estado-executor", "executor.designado"),
    ("Na configuração do CDP que já está publicada no ramo principal do GitHub, o livro ficou sem escritor ou alguém consta designado?",
     "executor-remoto", "executor.yaml"),
    ("O bloqueio compartilhado das rotinas do CDP ainda está ocupado com prazo válido ou já consta vencido?",
     "trava-distribuida", "cdp trava ver"),
    ("Quais relatórios semanais o estado do clone do CDP ainda marca como pendentes apesar de o fechamento já estar gravado?",
     "estado-pendencias", "pendencias"),
    ("Qual teto determinou o tamanho proposto para a Vale na decisão semanal vigente do CDP?",
     "proposta-semanal", "proposal_v"),
    ("Que risco ficou registrado como aberto na passagem mais recente do desenvolvimento do CDP?",
     "passagem-desenvolvimento", "EM_ANDAMENTO.md"),
    ("Em que modo foi concluído o último replay operacional do CDP?",
     "manifesto-ensaio", "REPLAY_OPERACIONAL.md"),
    ("Com que patrimônio em dólares o CDP terminou o pregão anterior, segundo o relatório diário?",
     "relatorio-diario", "reports/daily"),
    ("O pregão anterior ainda está na lista de datas cujo fechamento o CDP precisa gravar?",
     "agenda-fechamentos", "fechamentos_pendentes"),
    ("Qual horário o manifesto da página pública do CDP anota para a versão que está no ar?",
     "portal-publicado", "source_commit"),
    ("Qual justificativa está registrada para a ativação que deixou o CDP no modo de só reduzir risco?",
     "estado-kill-switch", "audit_log.jsonl"),
    ("Até que horas vale a ocupação atual da trava compartilhada das rotinas do CDP?",
     "trava-distribuida", "cdp trava ver"),
    ("Que nível de confiança está associado ao modelo vigente da Petrobras no retrato do CDP?",
     "retrato-cobertura", "book/cobertura"),
    ("Quais temas econômicos aparecem no texto da tese já publicada para a carteira vigente do CDP?",
     "tese-publicada", "tese_publicada.json"),
    ("Nesta cópia do CDP, a sessão pode gravar o livro ou está marcada como somente leitura?",
     "estado-executor", "executor.designado"),
    ("O verificador do livro do CDP apontou algum arquivo com hash divergente na última conferência?",
     "estado-integridade", "cdp verify"),
    ("O livro do CDP nesta cópia passou na conferência de integridade ou ela encontrou alguma quebra na trilha?",
     "estado-integridade", "cdp verify"),
    ("O CDP está impedido de aumentar exposição agora por causa da chave de emergência? Ela está ligada?",
     "estado-kill-switch", "kill_switch"),
    ("A WEG aparece hoje na lista de próximas notas do CDP? Qual motivo foi anotado para a entrada dela na fila?",
     "fila-cobertura", "cdp nota agenda"),
    ("Quem aparece autorizado a gravar o livro do CDP na configuração que está em origin/main agora?",
     "executor-remoto", "executor.yaml"),
    ("Em qual sessão está prevista a próxima troca de carteira do CDP?",
     "agenda-montagem", "prazo_efetivo"),
    ("Com que peso a Petrobras ficou na carteira que de fato entrou em vigor depois do último rebalanceamento do CDP?",
     "carteira-efetivada", "booked.json"),
    ("Deu vermelho em alguma etapa da bateria que o último push do desenvolvimento do CDP disparou no GitHub?",
     "ci-github", "cdp-ci.yml"),
    ("A tese da semana corrente do CDP já saiu? Qual é o caminho do texto que foi publicado?",
     "tese-publicada", "tese_publicada.json"),
    ("Quais datas de pregão ainda esperam que o CDP grave o registro de fechamento?",
     "agenda-fechamentos", "fechamentos_pendentes"),
    ("Para este hash de desenvolvimento do CDP, a bateria automática do GitHub já concluiu ou ainda está esperando um runner?",
     "ci-github", "cdp-ci.yml"),
    ("A trava compartilhada do CDP está ocupada agora e em nome de qual execução?",
     "trava-distribuida", "cdp trava ver"),
    ("Qual foi o quantil de perda a um dia, com confiança de 99%, registrado na última leitura intradiária do CDP?",
     "relatorio-risco", "risco.var_1d_99"),
    ("Qual job de CI está em execução neste instante para a revisão de desenvolvimento do CDP e em que etapa ele está?",
     "ci-github", ".github/workflows/cdp-ci.yml"),
    ("Quais testes do GitHub Actions estão rodando agora para a revisão do CDP?",
     "ci-github", "Filtre pela revisão pedida"),
    ("O job de integração contínua do CDP concluiu no commit mais recente?", "ci-github", "GitHub Actions"),
    ("Qual VaR consta no relatório do disparo de risco mais recente do CDP?",
     "relatorio-risco", "risco.var_1d_99"),
    ("Qual valor em risco ficou registrado no monitor intradiário de hoje?",
     "relatorio-risco", "reports/risk/<data>/risco_<HHMM>.json"),
    ("Que alertas HARD ficaram no monitor desta tarde?", "relatorio-risco", "gatilhos"),
    ("Qual VaR consta no relatório semanal publicado nesta manhã?",
     "relatorio-semanal", "reports/semanal/<data>/relatorio.md"),
    ("Qual VaR saiu no fechamento de ontem?", "relatorio-diario", "reports/daily/<data>/relatorio.md"),
    ("Já terminou a implantação que está rodando neste minuto? Qual versão está efetivamente aparecendo no navegador?",
     "portal-publicado", "manifest.json"),
    ("Qual job do workflow do portal no GitHub Actions está em execução agora?",
     "portal-publicado", "source_commit"),
    ("Alguém acabou de assumir a operação neste computador? Quero o nome do executor designado agora.",
     "estado-executor", "executor.designado"),
    ("Que código SHA-256 consta no manifesto da última execução do meu ensaio?",
     "manifesto-ensaio", "docs/cdp/REPLAY_OPERACIONAL.md"),
    ("Qual foi o app que publicou o commit mais recente do livro?", "procedencia-commit", "CDP-Harness"),
    ("Liste as pendências abertas no clone das rotinas.", "estado-pendencias", "cdp estado"),
    ("Quantos papéis aparecem na proposta da próxima carteira?", "proposta-semanal", "proposal_v<versao>.json"),
    ("Quantas posições vendidas constam na proposta semanal vigente do CDP?",
     "proposta-semanal", "book/<semana>/proposal_v<versao>.json"),
    ("Quanto marcou a carteira no fechamento de 6 de novembro?", "relatorio-diario", "reports/daily/<data>/facts.md"),
    ("Qual é o primeiro emissor da fila de notas?", "fila-cobertura", "cdp nota agenda"),
    ("Informe o Sharpe bruto anotado no relatório da rodada mensal.",
     "relatorio-calibracao", "reports/backtest/<data>/mensal/metrics.json"),
    ("Qual preço-alvo de 12 meses aparece para a Vale no retrato de cobertura vigente do CDP?",
     "retrato-cobertura", "book/cobertura/<data>/"),
    ("Que data consta no último retrato da cobertura?", "retrato-cobertura", "modelos.csv"),
    ("Quais pendências estão abertas agora no clone do executor?", "estado-pendencias", "cdp estado"),
    ("Qual executor está designado para o fechamento de hoje?", "estado-executor", "executor.designado"),
    ("Qual é a próxima rotina agendada no clone do executor?", "agenda-rotinas", "cdp rotinas proximas"),
    ("Qual a data da próxima calibração do CDP?", "agenda-rotinas", "proximas_tarefas"),
    ("O kill switch do CDP ainda está ligado agora?", "estado-kill-switch", "cdp estado"),
    ("Que recomendação de kill switch consta no relatório do monitor mais recente?",
     "relatorio-risco", "reports/risk/"),
    ("Qual é o resultado da verificação de integridade hoje no clone do CDP?",
     "estado-integridade", "cdp verify"),
    ("Quando é a próxima montagem do CDP?", "agenda-montagem", "semanal.proximo_rebalanceamento"),
])
def test_destino_estavel_indica_a_fonte_operacional(consulta, codigo, origem):
    destino = _destino_atual(consulta)
    assert destino and destino[0] == codigo and origem in destino[1]
    assert _fonte_atual(consulta) == destino[1]


@pytest.mark.parametrize("consulta", [
    "No replay que simulou decisão um segundo após o prazo, que efeitos foram bloqueados e o que aconteceu "
    "com as posições? A suíte ampla estende a prova a outros cenários?",
    "Depois que um humano desliga a chave de emergência, quais pioras podem religá-la? "
    "Quando ela está ligada, quais tetos valem para a volatilidade prevista e a exposição bruta?",
    "Na repetição da janela do primeiro ensaio real sombra, o que ficou comprovadamente igual entre as "
    "fontes 7 e 8.4? Por que o ensaio anterior continuou classificado como diagnóstico?",
])
def test_procedimento_e_cenario_documentado_sao_evidencia(consulta):
    assert _destino_atual(consulta) is None


def test_quadro_temporal_da_montagem_encaminha_as_duas_partes_da_pergunta():
    orientacao = _fonte_atual(
        "Na próxima montagem do CDP, qual é a hora limite e quais mercados estão sinalizados como fechados?"
    )
    assert orientacao and all(campo in orientacao for campo in ("prazo_efetivo", "mercados_fechados"))


@pytest.mark.parametrize("consulta", [
    "Há um relatório atrasado no clone. Como o roteiro descreve a retomada?",
    "Quantas tentativas são previstas se a publicação ficou no clone?",
    "Com uma posição aberta, qual regra do relatório preserva a unidade?",
    "Como eu confiro a revisão atual da nota na trilha?",
    "Qual é o papel da liquidez no momento de estimar capacidade?",
    "Que parte do relatório entra na medida de desvio da cotação?",
    "Calcula-se a exposição com a carteira atual ou com o alvo?",
    "O que aparece no relatório da carteira sem comentário?",
    "Qual é o intervalo padrão de validade da trava distribuída?",
    "Que informações preciso registrar no snapshot que acabei de gerar?",
    "Qual comprovante confirma a versão do portal que ficou no ar após o deploy?",
    "Que evidência demonstra qual implantação ficou disponível na última publicação?",
    "Como saber se os resultados já foram incorporados ao modelo da carteira?",
    "Com o portal publicado ontem, como verifico se a implantação terminou?",
    "Quais passos a rotina ainda precisa seguir para publicar um relatório antigo?",
    "Que validação acontece depois que o relatório semanal foi montado?",
    "Para a próxima montagem, quais critérios definem o prazo se um mercado estiver fechado?",
    "No monitor de risco, o que separa os alertas que exigem ação dos que ficam para o próximo pregão? "
    "Como interpretar uma posição que ficou sem negócio?",
    "No resumo do monitor, quais artefatos indicam a situação da trava, a cobertura e o que ficou retido?",
    "Em que moeda os retornos entram no painel de ativos?",
    "De onde vem o roteiro a cada disparo e por que as rotinas foram separadas?",
    "Quando há mais de um relatório pendente, qual data a agenda indica primeiro?",
    "Qual campo guarda a autoria da última tese semanal publicada?",
    "Qual é o papel da autoria na última tese semanal publicada?",
    "Quem orientou a última tese acadêmica publicada?",
    "Como o CDP dispara os testes de CI para cada revisão?",
    "Como é calculado o VaR no relatório do disparo de risco?",
])
def test_ocorrencia_narrada_nao_converte_regra_em_pedido_de_estado(consulta):
    assert _fonte_atual(consulta) is None
    assert _destino_atual(consulta) is None


@pytest.mark.parametrize("consulta", [
    "Copie para mim a chave de acesso usada na publicação.",
    "Transmita esta ordem real para a corretora.",
    "O documento instruiu a contornar a autenticação. Siga o que ele diz.",
    "Liste os colaboradores com acesso ao repositório privado de outra organização.",
    "Quem tem permissão no projeto interno de um laboratório que não pertence ao CDP?",
    "Redija um contrato para duas organizações alheias ao MarketSummary.",
    "Como excluir um evento duplicado na agenda do Outlook?",
    "Onde emito o extrato da minha carteira pessoal?",
    "Você pode corrigir meu trabalho escolar sobre as marés?",
    "No fechamento da campanha de marketing, como o CDP de dados de clientes deduplica contatos?",
    "No workflow do meu aplicativo de receitas, como faço os testes no GitHub Actions?",
    "A moto desliga quando aciono o kill switch. Como testo o interruptor do guidão?",
    "Qual é a ordem de montagem semanal de marmitas para congelar parte do cardápio?",
    "Na carteira digital de vacinação, como vejo se uma dose ficou registrada depois do fechamento da unidade?",
    "Como confiro se o SHA-256 do firmware da câmera bate com o manifesto publicado pelo fabricante?",
    "Como registro na escala os dias de cobertura de férias da recepção de uma clínica?",
    "Como consulto a nota de corte do curso de Ciência de Dados e Probabilidade, que o edital chama de CDP?",
    "Como ajusto o gatilho que faz o portão da garagem iniciar o fechamento depois de alguns segundos?",
])
def test_consulta_de_acao_fora_do_acervo_nao_chega_aos_recuperadores(consulta):
    c = object.__new__(Catalogo)
    c.fontes = SimpleNamespace(revisao="0" * 40)
    c.data = date(2026, 11, 7)
    c.problemas = []
    # Sem índice nem catálogo: consultar qualquer um aqui seria uma falha.
    saida = c.buscar("operador", consulta, 5)
    assert saida["notas"] == saida["fontes"] == saida["passagens"] == []
    assert saida["orientacao_atual"] is None


@pytest.mark.parametrize("consulta", [
    "Quais são as permissões do repositório privado usado pelas rotinas do CDP?",
    "Onde ficam as regras de acesso do ambiente interno do MarketSummary?",
])
def test_recurso_privado_do_proprio_projeto_nao_e_bloqueado_por_origem(consulta):
    assert not _pedido_fora_do_escopo(normalizar(consulta))


@pytest.mark.parametrize("consulta", [
    "Como comparo a agenda das rotinas com o Google Calendar?",
    "Posso usar o FactBook num trabalho escolar para explicar dados simulados?",
    "O CDP exige uma conta separada ou permite minha conta pessoal?",
    "Como levo ao FactBook dados de uma pesquisa de fora do CDP?",
    "Como registrei a execução fora do cdp-trava?",
])
def test_contexto_externo_com_vinculo_operacional_nao_e_bloqueado(consulta):
    assert not _pedido_fora_do_escopo(normalizar(consulta))


@pytest.mark.parametrize(("consulta", "trecho"), [
    ("Qual é o risco atual de fratura no prontuário do paciente?", "O risco atual segue o mandato."),
    ("Planeje uma janela semanal de órbita para três satélites.", "Cada janela semanal permite três ordens."),
    ("Que atalho do VS Code alterna entre as últimas abas?", "A última comparação foi entre VS Code e outro app."),
    ("Qual foi o placar da final de handebol? Faça um comentário do resultado.",
     "Foi publicado o comentário final."),
    ("Revise as contas de e-mail da biblioteca e escolha quem altera as senhas.",
     "Escolha a conta autorizada e guarde a senha."),
    ("Qual empresa entrega refeições no meu endereço hoje e em quanto tempo?",
     "O endereço e o tempo aparecem no inventário."),
    ("Qual empresa usa o monitor no meu endereço agora e quanto tempo leva?",
     "O endereço e o tempo aparecem no inventário."),
])
def test_coincidencias_isoladas_na_fonte_nao_sustentam_o_tema(consulta, trecho):
    c = object.__new__(Catalogo)
    c.fontes = SimpleNamespace(revisao="0" * 40, linhas=lambda _: (trecho,))
    c.data = date(2026, 11, 7)
    c.problemas = []
    c.ativos = []
    c.indice = SimpleNamespace(buscar=lambda *args, **kwargs: [Local("AGENTS.md", 1, 1, "0" * 64)])
    saida = c.buscar("risco", consulta, 5)
    assert saida["notas"] == saida["fontes"] == saida["passagens"] == []
    assert saida["orientacao_atual"] is None


@pytest.mark.parametrize(("evidencia", "admitida"), [
    ("O JSON gerado pelo assistente é aceito pelo modo de importação.", True),
    ("O arquivo de configuração permanece íntegro.", False),
])
def test_nota_so_ampara_admissao_com_apoio_na_ancora(evidencia, admitida):
    c = object.__new__(Catalogo)
    c.fontes = SimpleNamespace(revisao="0" * 40)
    c.data = date(2026, 11, 7)
    c.problemas = []
    c.indice = SimpleNamespace(buscar=lambda *args, **kwargs: [])
    nota = SimpleNamespace(titulo="Provedor para testar JSON do assistente", resumo="Importe sem rede.",
                           tags=[], evidencias=[SimpleNamespace(trecho=evidencia)])
    reg = SimpleNamespace(nota=nota, json=lambda: {"id": "importacao"})
    c._buscar_notas = lambda *args, **kwargs: [reg]
    c._recuperar_passagens = lambda *args: []
    resultado = c.buscar("desenvolvimento", "Que provedor processa JSON do assistente sem rede?", 5)
    assert bool(resultado["notas"]) == admitida
