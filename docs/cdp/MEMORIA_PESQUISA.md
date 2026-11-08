# Memória de agentes no CDP — pesquisa e decisão de arquitetura

Pesquisa de 07/11/2026. A decisão deste trabalho é manter uma memória portátil, local e
versionada de aprendizados úteis para retomar o CDP. A camada derivada tem o papel de encaminhar
o agente às evidências, inclusive quando uma conclusão antiga precisa ser reavaliada. O mandato,
o livro, os validadores e as rotinas conservam seus próprios critérios de autoridade. Os comandos,
formatos e passos de revisão estão no [manual de memória](MEMORIA.md).

## O que os experimentos mostram

A Anthropic organiza a memória entre sessões em quatro camadas. O registro pesquisável preserva
o ocorrido, as notas registram descobertas, as representações interligadas organizam assuntos e
um índice curto entra na abertura. A revisão entre sessões, chamada *dreaming*, compara notas com
registros, corrige erros, reúne duplicatas e escolhe o que merece destaque. É um ciclo diferente
da compactação de uma conversa em andamento. [The components of agent memory, 06/11/2026](https://www.anthropic.com/research/components-of-agent-memory).

| Experimento | Resultado relatado pela Anthropic | Implicação para o CDP |
|---|---|---|
| Tarefa de banco de dados do CL-Bench | Opus 5 obteve recompensa média de 0,564 sem memória e 0,828 com memória. | Guardar o procedimento que resolveu a falha, a evidência do teste e seu escopo. Avaliar a memória em sequências de tarefas. |
| Pokémon Red | O caso de Mt. Moon mostrou uma correção de memória que mudou a rota. | Distinguir uma conclusão do agente do que a saída original mostrou. Estado visível no sistema deve ser consultado de novo. |
| Corpus da Stainless, 25 perguntas | Busca com wiki 61%, busca 53%, wiki 48%. | Conservar busca nas fontes e medir o valor incremental da síntese. |
| Fusão e tarefas do Harvey LAB | 87% com wiki contra 73% com busca em itens de síntese da fusão. Em uma tarefa de documento único, sem ganho claro. Uma wiki atingiu 1,77 vez o corpus. | Dar prioridade a procedimentos e relações difíceis de reconstruir. A síntese tem orçamento e precisa economizar trabalho. |
| Construção concorrente de uma wiki contratual | 41 de 57 critérios no primeiro arranjo, 57 de 57 depois de isolar páginas por contrato e conservar os termos. | Usar unidades de escrita independentes e vincular cada afirmação à passagem original. O experimento mudou dois fatores juntos. |

São comparações dos modelos, tarefas e condições do estudo, com parte das evidências em
exemplos exploratórios. O resultado da Stainless cobre critérios em 25 perguntas e o de Pokémon
é ilustrativo. Instrução detalhada ajudou um modelo antigo, mas registrar somente falhas reduziu
o ganho de modelos mais capazes. No CDP, a mente pode propor o que merece retenção, enquanto o
código controla elegibilidade e validade. [Figuras 3, 5, 8, 10–12 e 14 do estudo](https://www.anthropic.com/research/components-of-agent-memory).

A separação do trabalho imediato da consolidação tem fundamento independente. O estudo sobre
*sleep-time compute* compara pré-processamento com computação no momento da consulta em tarefas
de raciocínio adaptadas. Previsibilidade das consultas se associou ao benefício. A rotina
repetitiva do CDP torna plausível revisar aprendizados de falhas recorrentes e mudanças de
procedimento entre sessões. Cabe medir o custo e o valor da revisão no próprio CDP.
[Lin et al., *Sleep-time Compute*](https://arxiv.org/abs/2504.13171).

O CL-Bench 1.0 da equipe de Berkeley e Snorkel mede adaptação em sequências com tarefas
dependentes. O LongMemEval separa indexação, recuperação e leitura, e inclui atualização,
raciocínio temporal, combinação de sessões e abstenção. HaluMem mede separadamente extração,
atualização e resposta, localizando onde surgem e se propagam erros. Evo-Memory avalia reuso de
experiência em fluxos sequenciais. Juntos, motivam medir **o que entrou**, **o que foi recuperado**
e **o que o agente fez** como resultados distintos. [CL-Bench 1.0](https://sky.cs.berkeley.edu/project/continual-learning-bench/),
[LongMemEval](https://arxiv.org/abs/2410.10813), [HaluMem](https://arxiv.org/abs/2511.03506),
[Evo-Memory](https://arxiv.org/abs/2511.20857).

## Escolha para o CDP

| Abordagem | Onde ajuda | Custo e decisão |
|---|---|---|
| Busca lexical nas fontes | IDs, comandos, nomes de arquivos, símbolos e mensagens de erro conhecidos. | A referência de comparação usa documentos canônicos selecionados por escopo. A busca por palavras tem dificuldade com paráfrases. |
| Notas estruturadas no Git e busca lexical | Identifica aprendizados duráveis, preserva a trilha da mudança e funciona sem serviço externo. | É a implementação escolhida. A seleção depende da qualidade dos títulos, do vocabulário, do recorte por tarefa e das evidências. |
| Wiki derivada e vinculada | Ajuda quando um problema exige relacionar várias notas ou documentos. | O CDP usa um índice e páginas temáticas derivados do catálogo, com vínculos de evidência e substituições explícitas. Uma wiki narrativa independente ampliaria o material a revisar. |
| Índice lexical persistente, como SQLite FTS5 | Evita reler um corpus grande e permite busca ordenada por relevância. | O corpus inicial permite busca em arquivos. Se a latência justificar, usar um índice descartável e reconstruível a partir da mesma fonte versionada. |
| Busca híbrida com vetores | Encontra paráfrases e vocabulário distante da fonte. | Acrescenta um modelo, versão de embeddings e avaliação de ordenação. Comparar offline somente quando consultas reais mostrarem perdas lexicais. |
| Grafo temporal ou serviço especializado | Responde a relações recorrentes entre entidades e a mudanças de validade em escala. | Os estados e relações financeiras do CDP já têm representações canônicas. Para as notas, datas e vínculos explícitos atendem à necessidade inicial com revisão por diff. |
| Serviço de memória de um aplicativo | Persiste experiência entre sessões daquele aplicativo. | O CDP precisa compartilhar a mesma memória entre Codex, Claude, Gemini e outros ambientes, inclusive offline. A camada adotada pertence ao repositório. |

O BEIR encontrou no BM25 uma referência competitiva entre domínios, com melhor média de
algumas técnicas de reordenação e interação tardia a um custo maior. O FTS5 oferece tokenização
Unicode e ordenação BM25 se o corpus justificar uma migração. Os autores do Mem0 avaliaram
extração, consolidação e recuperação de diálogos no LoCoMo. Os do Zep avaliaram um grafo temporal
em DMR e LongMemEval. Esses resultados ajudam a escolher alternativas para comparar, com validade
limitada ao desenho de cada experimento. [BEIR](https://arxiv.org/abs/2104.08663),
[SQLite FTS5](https://www.sqlite.org/fts5.html), [Mem0](https://arxiv.org/abs/2504.19413),
[Zep](https://arxiv.org/abs/2501.13956).

Carregar o histórico inteiro troca uma consulta seletiva por atenção a um volume crescente de
texto. *Lost in the Middle* encontrou sensibilidade à posição da informação relevante em tarefas
de recuperação e perguntas sobre documentos. A documentação do Claude Code também estabelece
um limite para o índice carregado no início. O orçamento do CDP serve para apontar onde procurar,
com recuperação por tarefa em seguida. [Lost in the Middle](https://arxiv.org/abs/2307.03172),
[memória do Claude Code](https://code.claude.com/docs/en/memory),
[engenharia de contexto da Anthropic](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents).

## Como o desenho se encaixa na operação

1. **Evidência primária.** O catálogo ancora trechos em documentação canônica, código e testes
   de uma revisão Git. Uma nota pode explicar por que uma falha costuma ocorrer e apontar para
   o teste que a reproduziu. A operação consulta os registros próprios de cada etapa. O estado
   presente vem de `estado`, a próxima ação vem de `agenda` e do gate, e os números da mente vêm
   dos fatos produzidos por código.
2. **Nota.** Registrar uma descoberta com escopo, data, validade, situação de revisão e trechos
   verificáveis. Separar observação de inferência. Ancorar o trecho por SHA-256 permite detectar
   alteração de conteúdo. O vínculo prova quais bytes sustentam a nota e deixa a interpretação
   para revisão. A ausência de evidência suficiente deve produzir abstenção ou uma candidata.
3. **Representação e entrada.** Identificadores, assuntos e relações de substituição ajudam a
   encontrar notas por tarefa. A entrada curta aponta para o estado e a busca. Nas rotinas, a
   decisão do gate precede a consulta à experiência histórica.
4. **Consolidação.** A auditoria da árvore de trabalho enumera problemas de evidência ou
   referência, prazos vencidos, candidatas, duplicatas e possíveis sobreposições. Ela gera uma
   fila para orientar a revisão. Em desenvolvimento, quem mantém o acervo pode usar a fila e
   os trechos originais para propor correções, fusões ou substituições em um diff. Uma
   substituição conserva o rastro da versão anterior. A promoção passa pela revisão do
   repositório. A implementação automatiza a verificação estrutural e a fila, enquanto a
   interpretação e a mudança das notas ocorrem na revisão.

Exemplo de boa nota: ao revisar um fechamento, comparar a moeda da narrativa com a moeda do
fato consumido pelo validador e consultar o teste correspondente. Exemplo de informação para
buscar no dia: se houve fechamento, qual foi o retorno e se a publicação já chegou ao portal.
Essas perguntas apontam para evidências distintas. A trilha do livro, o remoto, o portal e o
recibo de envio têm alcances diferentes, mesmo quando se referem à mesma data.

## Limites de confiança e manutenção

Uma fonte pública é evidência a examinar. O material recuperado conserva esse papel após a
consolidação e ao circular entre aplicativos. Dados externos e transcrições integrais ficam
fora da ingestão automática. O fluxo de memória opera sobre caminhos autorizados no repositório
e produz contexto consultivo. Uma referência quebrada, vencida, substituída ou sem proveniência
adequada perde a elegibilidade operacional segundo as regras da camada. Nenhuma saída de
memória concede permissões, flexibiliza gates ou autoriza cálculo, execução ou publicação.

O estudo *Bad Memory* separa sucesso da injeção e persistência da carga. Um agente pode recusar
uma instrução e deixá-la disponível para outro modelo. O estudo inseriu a carga previamente no
ambiente sintético, por isso o resultado mede o risco da persistência após entrada. O guia da
Anthropic recomenda delimitar dados de ferramenta, identificar sua origem e restringir acesso a
ações e segredos. O exemplo de *dreaming* da Anthropic também documenta que seu agendamento
atualiza o acervo sem revisão por padrão. No CDP, a revisão ocorre sobre propostas e o conteúdo
recuperado permanece separado das instruções normativas. [Bad Memory](https://arxiv.org/abs/2607.14611),
[mitigação de injeção da Anthropic](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks),
[cookbook de dreaming](https://platform.claude.com/cookbook/managed-agents-cma-dreaming-with-a-dynamic-workflow).

O esforço de revisão deve se concentrar no que mudou e no que pode induzir um próximo passo
errado. Para diagnosticar regressões, registrar a revisão de código, o acervo e a data de
referência do ensaio. Tratar fonte ausente de modo distinto de fonte divergente. Separar a data
em que a experiência foi registrada da data em que passou a ser recuperável, sempre que o
cenário histórico exigir esse recorte. Usar checkout ou fixture do corte para impedir que uma
nota escrita depois influencie um ensaio anterior.

## Como medir efeito no CDP

Rodar uma sequência de retomadas com fonte e data fixas. Confrontar a busca direta com a busca
apoiada pelas notas, mantendo tarefa, acesso ao corpus e critério de correção equivalentes. Se
houver consolidação semântica, comparar também a mesma memória antes e depois da revisão. Separar
o conjunto usado para elaborar notas das perguntas reservadas para medir generalização.

| Dimensão | Evidência de acerto | Controle negativo |
|---|---|---|
| Recuperação | A nota e a fonte esperadas aparecem entre os primeiros resultados. | Uma candidata ou uma nota de outra tarefa fica fora da entrada operacional. |
| Temporalidade | A versão elegível no corte é recuperada. | Uma data anterior não recebe um aprendizado futuro. Uma versão velha não desloca a vigente. |
| Proveniência | O trecho vinculado está presente e confere com o hash. | Alteração, duplicação ambígua, retirada ou caminho indevido da evidência é detectado. |
| Abstenção | O agente aponta o dado ou verificação que falta. | Publicação do repositório, renderização do portal e recebimento são confundidos deliberadamente no enunciado. |
| Segurança e integridade | O gate e o livro preservam o comportamento para a mesma entrada. | Um texto armazenado tenta dar nova autoridade, mudar um limite ou obter um segredo. |
| Eficiência | A mesma tarefa exige menos buscas, bytes de contexto ou tempo com qualidade equivalente. | Pergunta respondida por uma única fonte mede o custo de carregar memória desnecessária. |

O corpus determinístico inicial compara recuperação de caminhos com o mesmo orçamento e mede
abstenção de notas. Os testes estruturais cobrem elegibilidade e invariantes próprios da camada.
Um ensaio posterior com agentes em sessões novas pode medir respostas com evidência, abstenção e
custo, registrando o modelo e a versão do acervo. Os resultados da literatura sustentam o desenho
e as hipóteses. Ganho de desempenho no CDP depende da comparação local sob essas condições.

Na ablação pareada, o mesmo preparador roda com e sem registros curados ativos. O índice
de fontes permanece idêntico. Leitores em sessões novas recebem as mesmas perguntas e o
mesmo modelo, instruções e orçamentos. O gabarito de cada grupo permanece com o avaliador.
O contraste isola o efeito de oferecer as notas à preparação. A comparação com busca
automática mede, em conjunto, a preparação e o trabalho adicional do leitor. Registre o
saldo por pergunta e agrupe famílias que compartilham evidência na análise de sensibilidade.
[Avaliador pareado](../../scripts/cdp_memoria_pareado.py).
[Teste exato para proporções pareadas](https://pmc.ncbi.nlm.nih.gov/articles/PMC9447366/).


## Qualificação posterior por passagem

A unidade de avaliação passou de arquivo para trecho. Uma pergunta sobre vários registros
só recebe crédito completo se a consulta localizar pelo menos uma âncora de cada grupo
obrigatório. O desenho separa recuperação, atualizações temporais e abstenção, conforme
as dimensões do LongMemEval. Para perguntas de estado, mede-se se a busca deixa de oferecer
notas históricas e indica uma fonte canônica. A experiência de seleção sob mudanças de
domínio reforça a necessidade de testar a abstenção em conjuntos separados.
[LongMemEval](https://arxiv.org/abs/2410.10813).
[Selective Question Answering](https://aclanthology.org/2020.acl-main.503/).

A busca direta usa BM25 em janelas limitadas. As notas acrescentam vocabulário de tarefa e
referências para evidência textual. Os três primeiros resultados diretos ficam reservados e as vagas
seguintes alternam fontes e âncoras. Isso limita a influência de uma nota com muitas
referências. A busca nas fontes é o controle também para as perguntas que só exigem um
documento. A mesma lista de caminhos serve aos dois modos na revisão atual.
[BM25](https://doi.org/10.1561/1500000019).
[Document Expansion by Query Prediction](https://arxiv.org/abs/1904.08375).

A verificação de linhagem distingue a primeira aceitação de uma substituição da validade
atual de sua evidência. A prova deve aparecer em um commit da história de primeiro pai da
revisão consultada. Um rascunho ou uma evidência ausente na aceitação não prova sucessão.
Uma relação já comprovada persiste após retirada ou remoção. Histórico incompleto bloqueia
essa prova. Os controles de recuperação medem sugestões indevidas em consultas do corpus.
Os testes de linhagem verificam separadamente a integridade do histórico.
[git log e primeiro pai](https://git-scm.com/docs/git-log).

## Consolidação e wiki a partir dos exemplos oficiais

O cookbook de *dreaming* entrega entradas fixadas a analisadores, um por transcrição. Um
organizador entra depois e reúne duplicatas, repara ligações e fecha o índice. O exemplo
confere os registros das tarefas contra o relatório do coordenador e entrega a memória
em leitura para as próximas sessões. Na execução registrada, 11 transcrições de exemplo
custaram US$ 0,36 e levaram cerca de dois minutos e meio. No agendamento mostrado, a
atualização ocorre na memória ativa antes de revisão e uma sessão ainda em andamento pode
ficar fora das janelas seguintes. Isso motiva separar proposta de integração e conservar
pendências explícitas de uma execução à outra. [Dreaming com fluxo dinâmico](https://platform.claude.com/cookbook/managed-agents-cma-dreaming-with-a-dynamic-workflow).

A revisão de 06/11/2026 do *knowledge wiki* monta o acervo em etapas de extração por lote,
resolução de lacunas, confronto das afirmações com os documentos e organização final.
A origem e a data acompanham a afirmação. Mudanças de versão e divergências permanecem
visíveis. As sessões de consulta leem a wiki em modo somente leitura. Quando falta a peça
necessária, a resposta identifica a lacuna. O próprio exemplo detectou perda de conteúdo
em cerca de 5% das linhas enviadas à página de entidade mais disputada entre escritores.
[Quickstart fixado em 4a4224bd](https://github.com/anthropics/claude-quickstarts/blob/4a4224bdf0e9cfb3332167b69c90457403813625/managed-agents/knowledge-wiki/README.md).

No *knowledge wiki*, a montagem registrada usa oito documentos principais, cerca de
2,8 MB de texto e US$ 16 a preço de lista. A avaliação do notebook usa 21 perguntas,
27 rodadas e dois modelos julgadores. O gabarito fica fora do repositório público.
As comparações com o mesmo modelo separam parte do efeito da wiki da escolha do leitor.
[Notebook fixado em 4a4224bd](https://github.com/anthropics/claude-quickstarts/blob/4a4224bdf0e9cfb3332167b69c90457403813625/managed-agents/knowledge-wiki/distill_documents_into_knowledge_wiki.ipynb).

| Leitor | Documentos brutos | Wiki |
|---|---:|---:|
| Claude Haiku 5.5 | 88,9 ± 0,6 e US$ 0,0066 por resposta | 91,9 ± 0,7 e US$ 0,0056 por resposta |
| Claude Sonnet 5.5 | 92,8 ± 0,5 e US$ 0,086 por resposta | 92,6 ± 0,6 e US$ 0,064 por resposta |

As pontuações vão até 100 e o notebook apresenta intervalos de 95%. O custo de cerca de
um quinze avos compara Haiku com wiki e Sonnet com documentos. A utilidade e a amortização
no CDP dependem das suas próprias tarefas, acervo e condições de uso.
[Medição e limites no notebook](https://github.com/anthropics/claude-quickstarts/blob/4a4224bdf0e9cfb3332167b69c90457403813625/managed-agents/knowledge-wiki/distill_documents_into_knowledge_wiki.ipynb).

| Função nos exemplos | Adaptação ao CDP |
|---|---|
| Coordenar a consolidação | Código local fixa a revisão e a data, gera uma fila limitada e explicita o trabalho pendente. A agenda e o gate conservam a autoridade sobre rotinas. |
| Analisar e resolver | Cada proposta tem um item de origem e evidências ancoradas. Trabalho em paralelo pode produzir propostas independentes. Lacunas, ausência de leitura e divergências ficam como situações distintas. |
| Organizar | Validação e consolidação estruturais ficam separadas do julgamento semântico. A revisão por diff decide o que aceitar e registra substituições comprováveis. |
| Entregar a wiki | A consulta usa a revisão registrada no Git, com índice, tópicos e referências derivados. As páginas conduzem às fontes canônicas e preservam a hierarquia de autoridade. |
| Verificar o trabalho | Conferir o conjunto de itens planejados, o que foi analisado e o que sobrou para revisão. Um relatório de agente descreve o que ele tentou. A validação de evidência e a revisão identificam o que pode ser integrado. |

A versão do CDP executa a coordenação e a renderização offline sobre o acervo permitido
no repositório. Os dados consultados são material de análise. As instruções continuam no
manual, nos roteiros e na configuração. Uma nota pode dizer onde verificar se houve entrega.
A evidência de entrega continua sendo o registro da entrega. A wiki apresenta o mapa da
investigação. O leitor confere as fontes quando a ausência ou a validade da informação
puder mudar a decisão. [Orientação de análise](https://github.com/anthropics/claude-quickstarts/blob/4a4224bdf0e9cfb3332167b69c90457403813625/managed-agents/knowledge-wiki/prompts/analyzer_system.md),
[orientação de organização](https://github.com/anthropics/claude-quickstarts/blob/4a4224bdf0e9cfb3332167b69c90457403813625/managed-agents/knowledge-wiki/prompts/organizer_system.md).

A retomada de uma revisão longa recompõe a mesma fila na revisão e data fixadas. Cada
devolutiva comprova a cobertura da sua página, e a próxima origem só é sugerida após a
cobertura de toda a fila. Uma investigação em aberto permanece identificada mesmo quando
a fila foi lida. O modo estrito exige uma fonte literal ou um diagnóstico verificável
por item. A curadoria ainda precisa decidir se a prova sustenta a manutenção ou mudança.

A janela de mudanças e o estado de uma investigação têm relógios diferentes. A primeira
avança com a cobertura das fontes. A segunda depende de uma conclusão apoiada. A
continuidade do CDP registra a pergunta, hipóteses concorrentes e um próximo teste,
reconstitui o item no Git e localiza de novo as provas no corte atual. Uma passagem
alterada continua acessível na revisão anterior e perde vigência no plano novo.
Uma resolução pede uma passagem atual. O caderno de pesquisa da Anthropic descreve
como anotar tentativas anteriores evita voltar aos mesmos caminhos sem saída.
[Componentes da memória](https://www.anthropic.com/research/components-of-agent-memory) ·
[Memória em pesquisas longas](https://www.anthropic.com/research/long-running-claude).

## Escolher a autoridade e testar quando pedir esclarecimento

A C22 congela pergunta, gabarito e âncoras antes de executar. Os mesmos 36 pedidos
passaram pelos braços offline, de triagem assistida seguida de busca automática e
de seleção guiada. O teto de evidência permaneceu em cinco passagens e 4.500
bytes. Os acertos conjuntos foram 17/36, 34/36 e 36/36, respectivamente. O
fluxo guiado fez leituras adicionais. Uma busca direta também recuperou 8/10
grupos documentais, ante 10/10 na seleção guiada. O ganho combinado inclui a
classificação do pedido, a autoridade de estado e a recuperação documental.

Na C26, acrescentar critérios de objeto e atributo após o gate de estado
elevou os destinos offline de 8/15 a 10/15, com dois ganhos e nenhuma perda.
O refinamento usa o mapa de autoridades e depende de âncoras válidas no Git.
Como o teste de intenção permanece separado, o ganho foi restrito a destino.
O total offline passou de 23/60 a 25/60.

Na C27, oito famílias inéditas continham cada uma uma consulta de estado,
uma documental, uma externa e uma ambígua. A pontuação começou após lacrar
as saídas da triagem única, da segunda leitura e de uma contraprova adicional.
A segunda leitura só propõe esclarecimento quando identifica duas intenções
ou autoridades plausíveis e o que falta para distingui-las. Passou de 26/32
a 32/32, com seis ganhos e nenhuma perda. Os 24 determinados continuaram
corretos e as ambiguidades passaram de 2/8 a 8/8. A contraprova descartou
quatro dos esclarecimentos corretos e chegou a 28/32. A segunda leitura
segue experimental porque, na C26 já aberta, a mesma abordagem também
introduziu duas abstenções indevidas. A C27 mede triagem e destino, com
uma rodada por desenho e famílias escolhidas para cobrir contrastes.

Na C28, a segunda leitura passou de 39/48 a 44/48. Corrigiu oito
ambiguidades e confundiu três pedidos documentais compostos. Uma variante
com os mesmos casos e cartões recuperados de contrastes anteriores chegou
a 43/48. Cartões podem reter o que um agente aprendeu. Neste ensaio, deram
contexto a 28 das 33 verificações e não melhoraram o acerto conjunto.

Um diagnóstico posterior mostrou que os três falsos esclarecimentos
opunham método a estado. A segunda interpretação isolava uma parte de
uma consulta composta ou acrescentava uma instância que o enunciado não
pedia. Um filtro retrospectivo de núcleos interrogativos preservou os
oito ganhos e chegou a 47/48. A próxima prova deve exigir que as duas
leituras apontem ao mesmo trecho interrogativo e preservem o objeto e
o atributo pedidos. Fixar uma passagem é verificável em código. Decidir
se as alternativas cobrem o mesmo pedido ainda exige julgamento.

Para mutação, a primeira ampliação da guarda recuperou sete casos na
C26 já aberta. Na C29 cega, tanto a base quanto essa candidata deixaram
passar os 12 pedidos proibidos. A correção passou em 36/36 na reexecução
C29. Na C30 cega, reconheceu 4/12 ordens frente a 3/12 na base. Preservou
as 24 consultas e retrospectivas legítimas. A diferença entre diagnóstico
e confirmação motiva manter o gabarito separado das lições recuperadas.

Na C31, o recorte literal tornou verificável que duas interpretações apontavam
ao mesmo trecho. A segunda leitura livre e a ancorada chegaram a 45/48, ante
36/48 na triagem inicial. Ambas recuperaram 12/12 ambiguidades e fizeram
três pedidos indevidos de esclarecimento. A conferência do trecho explica
qual pergunta o leitor interpretou. A existência do trecho não prova que a
interpretação era plausível.

Na C32, leitores assistidos acertaram 36/36, com e sem recortes obrigatórios.
Os dois bloquearam 12 ordens e preservaram 24 consultas ou relatos legítimos.
A versão com recortes deixou uma prova conferível de pedido, efeito e alvo.
A referência offline bloqueou zero ordens, e o protótipo ajustado na C29 e
C30 bloqueou três. A leitura assistida entrou como opção anterior à triagem
e o resolvedor reproduziu as 36 decisões com histórico vazio nos bloqueios.

## Revalidar a prova quando a fonte muda

As fontes de um gabarito também envelhecem. A regra de travamento permaneceu
fechada após a mudança de agenda, mas a prova literal da recuperação mudou.
O avaliador agora conserva a passagem histórica e pede um manifesto para
conferir o caso na revisão nova. Na primeira comparação, uma nota candidata
foi ativada somente no checkout do ensaio. Ela recuperou os dois grupos
exigidos e conservou os outros 41 casos. O caso usado para redigir a nota
estava aberto. Na C33 cega, com 16 consultas novas, a nota isolada elevou
os acertos de 9/16 a 14/16. Os cinco ganhos ficaram nos oito casos de
aquisição e retomada. Renovação, estado e burla conservaram 8/8 controles.

O diagnóstico C33 encontrou dois problemas distintos. Uma passagem curta
já reunia as provas de uma nota que ficou em segundo lugar na mistura.
No outro caso, a prova do identificador da tarefa chegou às candidatas
estruturais, mas não coube na seleção final. Repetir o teste já aberto com
uma prova adicional do roteiro na nota recuperou as duas consultas. Essa
versão segue candidata no acervo.

A C34 cruzou a nota com prova adicional e um seletor que separa pedidos
e avalia itens Markdown compactos. O desenho se inspira na diversificação
por aspectos de consulta. Os quatro braços receberam o mesmo teto real
de cinco passagens e 4.500 bytes. Os quatro acertaram 13/24. O seletor
recuperou mais um grupo de prova, de 19/32 para 20/32, sem completar
outra consulta. A forma experimental permanece fora do fluxo padrão.
[Diversificação explícita por subconsultas](https://theses.gla.ac.uk/4106/).

A CLI oferece `--orcamento-estrito` para conferir os bytes de cada
passagem antes de devolver a seleção e preservar seus intervalos.
O primeiro ensaio guiado da C34 também expôs seis perguntas acima do
limite anterior de 240 caracteres. Busca, triagem, seleção e avaliação
passaram a aceitar consultas em uma linha de até 480 caracteres.

Com os enunciados preservados, a C34 acertou 24/24 na triagem assistida.
A busca automática com essa triagem obteve 14/24, e a guiada 12/24.
Cada braço acertou os oito controles. Entre as 16 consultas documentais,
foram seis completas na busca automática e quatro na guiada.
As duas perdas foram consultas multigrupo. A leitura guiada produziu
menos bytes e perdeu cinco grupos que a automática havia recuperado,
ao mesmo tempo que acrescentou três. A cobertura de todos os grupos
foi a medida usada para decidir se uma resposta documental estava completa.
A combinação retrospectiva preservou todas as passagens automáticas e
acrescentou passagens guiadas quando cabiam no mesmo teto. A cobertura
passou de 19/32 para 21/32 grupos, com os mesmos 14/24 casos completos.

Uma auditoria da C34 reconstituiu o máximo possível antes de escolher
passagens. A revisão Git comporta os 16 casos documentais e 32 grupos
sob os limites de saída. Entre candidatas lacradas, fontes numeradas e
recortes permitidos, o máximo foi de 10 casos documentais e 26 grupos.
As fontes dos seis grupos ausentes estavam fora do catálogo do escopo.
Os outros nove grupos que faltaram na saída guiada estavam disponíveis
ao leitor. Alargar o acesso às fontes e escolher melhor dentro do pacote
exigem controles e métricas próprios.
As 243 âncoras compactas das notas ativas de todos os papéis não
cobriam os seis grupos ausentes. Uma ponte para esses grupos exige
curar os trechos de destino, além de vinculá-los ao papel pertinente.

Na C35, a segunda leitura ancorada obteve 46/48 rotas, ante 38/48
na triagem inicial. Exigir concordância entre duas segundas leituras
ficou em 45/48. Uma falha comum revelou que uma frase anterior fixava
o referente do pedido factual. Preservar o trecho do ato e o
antecedente necessário é a próxima hipótese de triagem.

### Wiki de procedimentos com passagens curadas

Para testar a relação entre etapas, a C36 congelou 16 páginas que apontam
para âncoras já validadas de notas curadas. Um vínculo descreve onde
procurar uma parte da prova. A fonte literal continua no Git. O braço
plano recebeu as mesmas passagens e o mesmo teto que o braço com wiki.
As três variantes compartilharam a triagem offline e a revisão de fontes.
O teste tem 24 pedidos inéditos em oito escopos e 40 grupos verificáveis.

A referência recuperou todas as provas em 6/16 casos multigrupo. A
lista plana e a wiki recuperaram em 5/16. Todos os braços acertaram os
quatro documentais simples. As relações mudaram duas seleções ante a
lista plana, com o mesmo placar. Todos os grupos tinham fonte no
escopo. A triagem offline errou os quatro controles em cada braço.
A versão permanece experimental.
Uma ponte prospectiva entre escopos deve autorizar somente a passagem
curada identificada, preservando o perímetro da leitura direta de fontes.
[Representações e busca combinadas na Anthropic](https://www.anthropic.com/research/components-of-agent-memory).

### Autorizar um trecho entre papéis

Uma ponte liga um papel de origem a papéis de destino e a um intervalo
literal de documento canônico. Validade, gatilhos e SHA-256 entram no
mapa Git. O recorte aparece como candidata depois da triagem documental,
sem adicionar caminhos à lista de fontes de leitura livre. Esse limite
segue a separação entre conteúdo curado e acesso ao arquivo inteiro.

O diagnóstico retrospectivo da C34 acrescentou os seis recortes
faltantes já conhecidos. O alcance passou de 26/32 a 32/32 grupos e de
10/16 a 16/16 casos documentais. Os seis recortes somaram 2.057 bytes.
O teste mede a capacidade física do mecanismo com curadoria perfeita
naquele conjunto. A C37 mede a transferência de um mapa diferente,
com 17 trechos curados antes de receber as perguntas inéditas.

A C37 usou a mesma triagem assistida e as mesmas fontes livres
numeradas. Os 12 pedidos de travessia passaram de 0 a 2 completos. Dos
13 grupos fora do papel da consulta, passaram de zero a três recuperados.
Nos seis documentais comuns, ambos os braços completaram quatro. Os
seis controles passaram em ambos. Em todos os 34 grupos, foram cinco
ganhos e três perdas, com saldo de 14/34 para 16/34. As duas seleções
foram feitas em sessões separadas. O teste mede a intervenção com
esse mapa, sob o mesmo orçamento final.

O diagnóstico retrospectivo separou os filtros da curadoria. O mapa
ofereceu quatro dos 13 grupos fora do papel da consulta. Dispensar os
gatilhos ofereceria cinco. Dispensar também o papel de destino conservaria
cinco. Oito grupos precisam de novos recortes, independentemente desses
dois filtros. Dos quatro grupos oferecidos, três chegaram à seleção.

Na C38, três curadores ampliaram o mapa de 17 para 45 trechos a
partir de etapas e exceções de tarefa. O mapa foi lacrado antes de
receber os 27 pedidos. Com as mesmas candidatas comuns, fontes livres,
triagem e teto, os dois mapas ofereceram 1/16 grupos fora do papel.
O braço ampliado completou 1/15 travessias, com uma ponte original
disponível nos dois braços, e perdeu um caso comum. Ambos ficaram em
11/27. O mapa maior ficou congelado como experimento.

Ao dispensar gatilhos retrospectivamente, mantendo os papéis, os
45 recortes cobrem 6/16 grupos fora do papel. Retirar o filtro do
destino conserva 6/16. Dez grupos ainda dependem de novos recortes.
O ensaio de oferta e a seleção do leitor devem continuar separados.

Na C39, o braço lexical preencheu vagas sem tirar as pontes escolhidas
pelos gatilhos. Um terceiro braço preencheu as vagas ainda livres com
recortes de 22 blocos literais revisados no laboratório. Cada recorte
tem o intervalo e o hash próprios, além da referência ao bloco. A
triagem e as fontes de acesso livre foram compartilhadas. A seleção
reaproveitou resultados quando a entrada visível era idêntica, para
que variação do leitor não parecesse efeito da oferta.
[Busca e wiki combinadas na Anthropic](https://www.anthropic.com/research/components-of-agent-memory).

Na C39, as travessias com provas viáveis no pacote foram 0/15, 1/15 e
2/15. Nenhuma ficou completa após a seleção. Os três braços acertaram
dois dos seis documentais comuns e os seis controles. O terceiro
braço selecionou uma prova externa ao papel. Dos 17 grupos externos,
seis tinham correspondência literal no acervo completo e dois foram
oferecidos. A falta de curadoria, a oferta e a escolha da prova final
têm efeitos observáveis em etapas diferentes.

Na C40, um planejador separado recebeu o enunciado e o papel, antes
de ver provas. Seus requisitos geraram buscas curtas. O experimento
comparou a busca pelo enunciado, a oferta por requisitos e a seleção
orientada pelos requisitos com a mesma oferta. Os três braços
compartilharam o acervo, a triagem, as fontes comuns e o teto de saída.
As 33 seções doadoras foram indexadas no laboratório. Das seções
de outros papéis, o leitor recebeu apenas recortes autorizados e
vinculados ao Git. O pré-teste confirmou que cada gabarito cabia
em até três passagens e 2.586 bytes.

A busca pelo enunciado e a busca por requisitos completaram 5/15
travessias cada. Mostrar os requisitos ao leitor, com a mesma oferta
do segundo braço, completou 2/15. Os três braços ofertaram os mesmos
nove grupos externos de 18 e recuperaram seis, sete e cinco na
seleção. Nos pedidos comuns, o acerto completo foi de 6/6, 5/6 e 4/6.
Os seis controles passaram nos três braços.

As 33 seções tinham dez dos 18 grupos externos, todos indexáveis.
As três ofertas tornaram viáveis as mesmas sete travessias. Das
sete provas perdidas entre o segundo e o terceiro braço, cinco
estavam nos recortes livres de fontes numeradas, uma no mapa
fixo e uma em seção. Isso separa a falta de fonte da perda de
prova que já estava à vista do leitor.

Na C41, a seleção estrita é compartilhada pelos três braços.
Quando o envelope passa e um recorte livre viola a visibilidade,
o segundo braço retira apenas esses recortes e confere o restante
com o validador canônico. O terceiro recebe as mesmas fontes e os
itens preservados, com uma única tentativa de acrescentar prova.
O código exige que cada item já preservado permaneça na seleção.
As tentativas não abrem caminhos de outro papel nem ativam
complementos de margem. A ideia de registrar a falha, testar uma
regra e aplicar a correção em outra sessão segue o ciclo de
aprendizado observado pela Anthropic.
[Artigo sobre memória de agentes](https://www.anthropic.com/research/components-of-agent-memory).

A C41 usou 30 pedidos inéditos e 39 grupos de prova. A recusa
integral, a preservação e a releitura completaram 6/15, 6/15
e 8/15 travessias. A preservação recuperou dois grupos locais
nas duas recusas. Cada releitura trouxe uma prova de outro
papel e completou a travessia, preservando todos os itens já
aceitos. Os documentais comuns ficaram em 6/7 e os controles
em 8/8. A oferta já tornava viáveis oito travessias, e a
releitura completou todas. A amostra dirigida observou duas
recusas naturais.

### Navegar referências entre procedimentos

O laboratório C42 segue um vínculo quando uma candidata local
contém a referência canônica. O alvo é um recorte revisado, com
origem, papéis receptores, validade e prova literal no Git. A
expansão faz um salto e oferece o alvo por ID. Regra e exceção
mantêm referências próprias. A lista de arquivos livres fica
idêntica. Quatro vínculos reais passaram nas verificações de
fronteira com consultas simuladas.

Um contraste prospectivo deve comparar o acervo corrente, o
mesmo acervo com os novos recortes em índice plano e os mesmos
recortes ativados pelos vínculos. O segundo contraste separa a
navegação da ampliação do acervo. Esse desenho adapta o uso de
relações e fontes conferíveis no quickstart da Anthropic.
[Knowledge wiki](https://github.com/anthropics/claude-quickstarts/tree/main/managed-agents/knowledge-wiki).

Na C42 prospectiva, foram congelados 28 vínculos com 27 alvos
distintos. Os braços de expansão preservaram as candidatas
locais e as pontes fixas da referência. Até duas vagas de
ponte podiam receber os novos recortes. A priorização por
vínculo exigia que as primeiras 12 candidatas locais
contivessem integralmente a âncora de origem. A busca plana
preencheu as vagas restantes.

Nas 22 consultas documentais, nenhuma relação se ativou nas
primeiras 12 candidatas. Os braços com acervo ampliado tiveram
as mesmas ofertas e reaproveitaram as mesmas leituras. A
auditoria cega encontrou 13 ocorrências de âncoras completas
entre as posições 14 e 64. Um diagnóstico adaptativo lacrado
antes da pontuação usou todas as candidatas locais expostas
como sementes e fez nova leitura em cinco pedidos.

A referência completou 5/15 travessias. A expansão completou
4/15 em ambos os braços e baixou a oferta de grupos externos
de 7/17 para 6/17. O acervo adicional cobria um dos 17
grupos externos, já coberto pela referência. O diagnóstico
com sementes mais profundas manteve os mesmos grupos
selecionados e pedidos completos dos braços de expansão.
Os oito controles passaram nos três braços.

### Buscar a prova que falta em uma segunda leitura

A C43 preserva todas as passagens aceitas na primeira leitura.
Se o leitor declarar uma lacuna e houver espaço, uma segunda
sessão escolhe IDs em um pacote lacrado ao prefixo. O braço
residual consulta seções doadoras autorizadas e exclui as
janelas que o leitor já viu integralmente. O índice recebe
apenas janelas restantes antes de ranquear e deduplicar.
As fontes de leitura livre continuam limitadas ao papel.

Os braços de segunda leitura compartilham lacunas, instruções
e teto. A expansão pode deslocar pontes do pacote da segunda
leitura. A união final conserva, na ordem original, todas as
passagens validadas no primeiro passe. Essa separação adapta a
combinação de busca e memória organizada descrita pela Anthropic.
[The components of agent memory](https://www.anthropic.com/research/components-of-agent-memory).

A C43 teve 30 pedidos inéditos. O primeiro passe e a releitura
simples completaram 2/15 travessias. A busca residual completou
4/15, com dois ganhos e nenhuma perda. Os grupos de prova
passaram de 22/40 para 25/40. Os três ganhos vieram de provas
de outro papel ausentes tanto das candidatas quanto das fontes
numeradas do primeiro passe. Os três braços completaram 6/7
documentais comuns e preservaram os oito controles.
As provas novas para o leitor vieram das seções já curadas.
Onze recortes ofertados vieram das 12 seções adicionais,
sem acrescentar grupo de prova. O teto retrospectivo
identificou cinco travessias inicialmente incompletas que
tinham solução no acervo. Duas ficaram sem segunda leitura
por falta de lacuna válida.

### Verificar a suficiência das provas em outra sessão

Na C44, uma sessão independente recebe o enunciado, o papel
e as passagens já validadas se o primeiro leitor ficar sem
lacuna válida e houver espaço. A devolutiva contém até três
lacunas. Cada uma precisa citar um trecho literal único da
pergunta. O verificador procura a regra aplicável em perguntas
condicionais e exige prova explícita de uma negativa.
O código confere a forma da lacuna e o vínculo com o pacote.
O gabarito mede à parte a pertinência semântica.

Os braços compartilham as releituras já acionadas pela
declaração inicial. O contraste mede o ganho da verificação
nos demais casos, com o mesmo acervo e mecanismo residual.
Isso adapta ao segundo passe a ideia de conferir uma conclusão
da memória com os registros que a sustentam.
[The components of agent memory](https://www.anthropic.com/research/components-of-agent-memory).

Na C44 prospectiva, as travessias completas passaram de 3/15
com a seleção inicial ou a busca por lacunas declaradas para
4/15 com a verificação independente. O verificador fez 12
leituras. Nove tinham prova suficiente e três estavam
incompletas. Acionou uma nova busca e recuperou o grupo
faltante em uma candidata já exposta. Os oito controles
passaram nos três braços.

O inventário adaptativo examinou os 11 casos em que a
revisão anterior ficou sem lacunas. Declarar cobertura
exigia citação literal de uma prova congelada. Nenhuma
busca adicional foi aberta. Duas respostas foram
recusadas por comprimento da citação. O limite de 240
caracteres não constava no prompt. Aparar somente as
citações longas para um trecho literal de 240 caracteres,
sem nova inferência, validou as duas respostas e manteve
o diagnóstico sem lacunas.

### Ampliar o acervo sem perder prova aceita

A C45 usa concessões por papel para indexar privadamente
documentos canônicos. Cada concessão tem uma relação com o
fluxo do CDP e pode restringir o intervalo da fonte. O
manifesto reproduz as 45 seções anteriores e acrescenta 60
intervalos sobrepostos e ligados ao Git. O leitor recebe
somente IDs de recortes que cabem no orçamento residual.

A seleção compara os dois acervos com o mesmo prefixo,
as mesmas lacunas e as mesmas instruções. Uma união sem
nova inferência mantém a seleção válida da referência e
acrescenta provas do braço ampliado que ainda cabem. A
avaliação separa presença no acervo, exposição, seleção
e preservação. Essa comparação leva em conta o ganho da
busca com memória estruturada e o custo de acervos grandes
observados pela Anthropic.
[The components of agent memory](https://www.anthropic.com/research/components-of-agent-memory).

A C45 comparou os acervos em 30 pedidos inéditos. A seleção
inicial completou 5/15 travessias. A busca residual de
referência, a ampliada e a união completaram 6/15 cada.
O teto dos acervos ficou em 9/15 grupos externos. A expansão
elevou de 11 para 13 os grupos com documento autorizado.
Dos seis grupos sem janela, quatro tinham documento autorizado
e ficaram fora dos intervalos aprovados. Quatro
das cinco travessias incompletas que ainda cabiam com o
prefixo fixado não receberam segunda busca. A extensão
ofertou 18 janelas e o leitor selecionou três. O único
grupo sustentado por elas já estava visível na referência.
As alternativas pré-registradas acrescentaram uma
travessia a todos os braços e mantiveram o contraste.

## Transferência de uma lição para outra sessão

O teste temporal do CDP usa uma fixture Git sem remoto. O revisor lê a fila lacrada
e propõe candidatas com trechos literais. A aprovação para integração é explícita e
limitada à fixture. Leitores novos recebem as mesmas fontes, perguntas, modelo e teto.
Somente as notas aprovadas mudam. Um dos casos verifica se a sessão consegue ligar
um apelido de operação a uma regra pública do ensaio. Os controles incluem validade,
conflito de escopo, ausência de fonte, episódio isolado e conhecimento introduzido no
futuro. Os leitores acertaram 7/7 casos após a revisão, ante 6/7 antes. A amostra
dirigida mede essa transferência sob o corte fixado.

A C23 verificou em cinco microcasos que uma investigação reaparece após avançar
o corte e que a perda de uma prova pode reabrir uma resolução com seu histórico.
A primeira candidata perdeu o vínculo com a resolução. A reexecução com o
mesmo gabarito conferiu os cinco controles após a correção. Em uma prova
comportamental posterior, a C25 comparou a mesma informação em prosa e registro
estruturado. Ambos passaram em 10/10 casos inéditos, ante 0/10 sem acesso ao
histórico. A vantagem do registro em código é permitir a verificação dos
vínculos e da vigência. O contraste comportamental confirmou o valor do acesso
ao histórico nessa amostra.

Na resposta, separe uma ausência documentada de uma pergunta que ficou sem prova.
A primeira é uma afirmação que deve citar a fonte que registra a ausência. A segunda
é uma lacuna de evidência na seleção. Essa diferença também protege a distinção
entre resultado documentado de um replay e estado de uma execução efetiva.
