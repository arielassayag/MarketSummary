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
| Wiki derivada e vinculada | Ajuda quando um problema exige relacionar várias notas ou documentos. | O CDP usa um índice derivado, vínculos de evidência e substituições explícitas. Uma wiki narrativa exigiria prova de ganho, pois multiplica material a revisar. |
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


## Qualificação posterior por passagem

A unidade de avaliação passou de arquivo para trecho. Uma pergunta sobre vários registros
só recebe crédito completo se a consulta localizar pelo menos uma âncora de cada grupo
obrigatório. O desenho separa recuperação, atualizações temporais e abstenção, conforme
as dimensões do LongMemEval. Para perguntas de estado, mede-se se a busca deixa de oferecer
passagens históricas e indica uma fonte canônica. A experiência de seleção sob mudanças de
domínio reforça a necessidade de testar a abstenção em conjuntos separados.
[LongMemEval](https://arxiv.org/abs/2410.10813).
[Selective Question Answering](https://aclanthology.org/2020.acl-main.503/).

A busca direta usa BM25 em janelas limitadas. As notas acrescentam vocabulário de tarefa e
referências para evidência textual. O primeiro resultado direto fica reservado e as vagas
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
