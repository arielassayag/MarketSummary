# IA / GenAI / Agentes LLM na Gestão de Ações: o que a Indústria Faz e o que Funcionou (2023–2026)

> **Documento de pesquisa 01 — Fundo Long/Short Equities LatAm (USD, market neutral)**
> **Data de referência:** segunda-feira, 2026-10-05 (último pregão completo: sexta-feira, 2026-10-02)
> **Escopo:** como as gestoras líderes usam IA, IA generativa e agentes LLM na gestão de **ações**; resultados reportados; padrões de sucesso e de fracasso; desenho organizacional; recomendações para um fundo L/S LatAm com rebalanceamento semanal.
> **Convenção de evidência:** **[F]** = fato verificado em fonte primária ou jornalística identificada; **[S]** = fato de fonte secundária (blog/newsletter/agregador) não confirmado em fonte primária; **[I]** = inferência/recomendação nossa. Números de desempenho de fundos são os reportados pela imprensa ou pelos próprios gestores e **não foram auditados por nós**.

---

## Sumário executivo

1. **O padrão dominante que funciona é "centauro", não "robô gestor".** Nas firmas que divulgam resultados concretos (Man Group, Balyasny, BlackRock, JPMorgan AM, Millennium, Morgan Stanley), o LLM atua como **analista-copiloto**: lê documentos não estruturados (filings, transcrições, notícias, research sell-side, discursos de BC) e devolve **saídas estruturadas e rastreáveis**. Essas saídas entram num **processo quantitativo de risco e otimização** já existente, e quem decide é um **PM humano responsável**. Robyn Grew (CEO da Man Group), em jul/2024: *"I don't think of AI as making investment decisions anytime soon"*. A JPMAM descreve analistas como *"content editors, rather than content creators"*. **[F]**
2. **Os ganhos mais bem documentados são de produtividade e cobertura, não de alfa autônomo.** Exemplos: no Balyasny, a análise de discursos de bancos centrais caiu de cerca de 2 dias para cerca de 30 minutos, com a plataforma usada por cerca de 95% de ~180 times de investimento. O AlphaGPT da Man Numeric gera, programa e testa sinais "em minutos em vez de dias", e "várias dezenas" desses sinais foram aprovadas para trading real. Ken Griffin (Citadel), em out/2025, disse que a GenAI "fica aquém" para gerar alfa; em mai/2026, relatou agentes automatizando tarefas de nível PhD em horas ou dias. **[F]**
3. **A exceção é a Bridgewater, e ela confirma a regra.** O fundo AIA (macro, não ações) usa a IA como decisor primário. Rendeu cerca de +11–12% em 2025 e +16,4% no acumulado até set/2026, com mais de US$ 4,5 bi. Isso só ocorre depois de mais de uma década sistematizando princípios (desde 2012), com **humanos no controle de risco, dados e execução** e com modelos próprios (o AIA Forecaster e um modelo ajustado com a Thinking Machines). Não é um caminho replicável para um fundo novo. **[F]**
4. **O padrão de fracasso é o LLM escolhendo ações de ponta a ponta.** Um estudo da Pomona College (Smith & Wyatt, ago/2024) mostra que os **11 fundos "100% IA"** dos EUA renderam **−1,8% a.a.** contra +7,6% do S&P 500, e 6 dos 11 fecharam. O AIEQ ficou atrás do S&P desde 2017, com alfa anualizado de −5,08% segundo análise de terceiros. Na Alpha Arena (Nof1, dinheiro real, out/2025), 4 de 6 LLMs perderam dinheiro (o GPT-5 perdeu −63%); o *overtrading* consumiu o P&L. **[F]/[S]**
5. **A evidência acadêmica mostra sinal real, mas frágil.** O GPT-4 lendo manchetes previu o *drift* de 1–2 dias com Sharpe de 2,97 antes de custos. Esse Sharpe caiu de 6,54 (2021T4) para 1,22 (jan–mai/2024) e **zera com custo de 20 bps por round-trip** (Lopez-Lira & Tang). O sinal se concentra em *small caps* e notícias negativas. A análise de demonstrações financeiras com *chain-of-thought* acerta **60,35%** da direção dos lucros, contra **52,71%** dos analistas (Kim, Muhn & Nikolaev). **[F]**
6. **O risco metodológico nº 1 é a contaminação temporal.** LLMs **memorizam** preços, índices e dados macro anteriores ao seu *knowledge cutoff*. Instruir o modelo a "não usar dados após X" **não funciona**: 97,6% de acerto antes do corte fictício, 98,0% depois, contra 40% no período realmente fora da amostra. Backtests de sinais LLM só valem **após o cutoff do modelo** (Lopez-Lira, Tang & Zhu). Agentes que geram muitas hipóteses **inflam o overfitting**, ponto levantado pela própria Two Sigma em jan/2026. Sob avaliação honesta, com Deflated Sharpe e PBO indexados ao número real de tentativas, **nenhuma** estratégia descoberta por LLM sobreviveu (Gençay, ago/2026). **[F]**
7. **O risco de portfólio vem antes do alfa.** Neutralidade a fatores, monitoramento de *crowding* e regras de *drawdown* são o que separa sobreviventes. Quants de ações perderam −4,2% em jun–jul/2025 num mercado em alta de ~8%, por desmonte de fatores crowded (Goldman Sachs Prime, via MSCI). O RIEF da Renaissance perdeu −14,4% em out/2025. A Numerai perdeu −17% em 2023 e depois rendeu +25,45% em 2024 com Sharpe de 2,75, rodando um livro **neutro a fatores**. Nas plataformas *multi-manager*, o padrão reportado de *drawdown* é **−5% → corte de 50% do capital; −7,5% → encerramento** (Millennium, segundo o WSJ). **[F]/[S]**
8. **Na América Latina há pouca divulgação pública de uso de LLM no processo de ações.** As casas quant relevantes (Giant Steps, a maior quant da região com cerca de R$ 6,5–7 bi; Kadima, com cerca de R$ 5 bi; XP Atalaia Quant) usam ML e sistematização há anos. Não encontramos casos públicos e auditáveis de LLM no núcleo de decisão de fundos L/S LatAm. Isso é uma **oportunidade de diferenciação**, desde que executada com a disciplina das casas globais. **[F]/[I]**

**Conclusão operacional [I].** Para um fundo L/S LatAm de US$ 100 mi, com vol-alvo de 5% e decisão semanal na segunda-feira, a arquitetura recomendada tem cinco camadas:

- **(a)** agentes LLM de pesquisa que produzem fichas estruturadas por ativo, com citações, em português, espanhol e inglês;
- **(b)** um motor quantitativo determinístico de sinais, risco e otimização, com neutralidade de dólar, beta e fatores e restrições de liquidez e *short squeeze*;
- **(c)** um agente de risco independente que **explica** (mas não calcula) as mudanças de risco;
- **(d)** um PM humano que decide e aprova, com aprovação vinculada a hash;
- **(e)** governança de avaliação: *point-in-time*, avaliação só após o cutoff do modelo, ledger de tentativas e Deflated Sharpe.

O LLM **nunca** calcula retornos, pesos ou riscos, o que já é um invariante do repositório (AGENTS.md).

---

## 1. Metodologia e limites desta pesquisa

- **Fontes:** comunicados oficiais (man.com, bamfunds.com, jpmorganchase.com, aima.org, twosigma.com, SEC), artigos acadêmicos (arXiv/SSRN, lidos diretamente), imprensa financeira (Reuters, Institutional Investor, Hedgeweek, Bloomberg Línea, The TRADE) e newsletters especializadas (AI Street).
- **Limites:**
  1. Hedge funds divulgam pouco. Os números de fundos privados vêm de "fontes" da imprensa.
  2. Várias páginas primárias bloquearam a leitura automatizada (HTTP 403), entre elas OpenAI/Balyasny, CNBC, Forbes e Dividend.com. Nesses casos, usamos reproduções da mesma fonte por terceiros e marcamos **[S]**.
  3. Algumas afirmações circulam só em blogs e foram marcadas como **[S]**. Exemplos: as regras de *stop* das plataformas *multi-manager*, os "AI twins" da Millennium e o número de 61,3% do modelo de *earnings calls* da BlackRock.
  4. Não encontramos documentação pública detalhada de uso de LLM por D. E. Shaw, Citadel (no investimento) ou Renaissance.

---

## 2. Panorama da adoção (o "pano de fundo")

| Indicador | Valor | Fonte / data |
|---|---|---|
| Gestores alternativos que usam GenAI | **95%** (86% em 2023) | AIMA, *Charting the course*, 150 gestores / US$ 788 bi, 16/09/2025 **[F]** |
| Gestores que esperam papel maior da GenAI no **processo de investimento** no próximo ano | **58%** (20% em 2023) | AIMA, 16/09/2025 **[F]** |
| Investidores institucionais mais propensos a alocar em quem investe seriamente em GenAI | **~60%** | AIMA, 16/09/2025 **[F]** |
| Gestores pequenos (< US$ 1 bi) **sem política de uso** de GenAI | **50%** (lacuna de governança) | AIMA, 16/09/2025 **[F]** |

Leitura: a adoção é quase universal, mas concentrada em **pesquisa e análise de dados**. O movimento para o *front office* e a decisão de investimento é recente, gradual e cobrado por **evidência** ("Investors are rewarding evidence over rhetoric", Tom Kehoe, AIMA).

---

## 3. Estudos de caso por firma

### 3.1 Man Group / Man Numeric — AlphaGPT, ManGPT e parceria com a Anthropic

- **AlphaGPT (Man Numeric, braço quant de ações) [F].** É um sistema agêntico que **gera hipóteses, escreve o código e roda o backtest** de sinais, imitando o fluxo de um pesquisador quant. A arquitetura descrita tem três agentes:
  1. *Idea Generator*;
  2. *Code Implementer*, que escreve Python de produção para o stack da casa;
  3. *Evaluator*, que faz checagens de "significância, risco e sentido econômico".

  Os sinais aprovados passam pelo **comitê de pesquisa e investimento padrão**, com os **mesmos limiares exigidos da pesquisa humana**. Em jul/2025, Ziang Fang (PM sênior) relatou "várias dezenas" de sinais **aprovados para trading real**. Fang sobre o grau de autonomia: *"I wouldn't call it autopilot… we have a lot of checkpoints in place"*.

  As salvaguardas citadas são controles de *look-ahead* e de *data mining*, contenção de *p-hacking* e alucinação, revisão humana e **log do porquê de cada decisão do agente**. A própria firma reconhece que testar mais hipóteses aumenta a chance de achar sinais espúrios. Fontes: Hedgeweek, 11/07/2025; AI Street, 20/11/2025 e 18/12/2025.
- **ManGPT [F]/[S].** É o assistente interno lançado em 2023, para código, rascunhos de documentos e fluxos de PM. Segundo a AI Street (20/03/2025), cerca de **50% da firma o usa mensalmente**; a Resonanz cita ~40% **[S]**. Em dez/2023, o CTO Gary Collier e Anthony Ledford (cientista-chefe da Man AHL) se mostraram **cautelosos quanto à capacidade de a IA gerar alfa** e situaram o ganho em acelerar processos. Fonte: Hedgeweek, 08/12/2023.
- **Parceria com a Anthropic (11/02/2026) [F].** A Man Group (US$ 213,9 bi de AUM em 30/09/2025) passa a usar Claude para três frentes: geração de alfa em universos maiores; processamento de texto e relatórios automatizados; e fluxos descritos em linguagem natural, com acesso a dados por **execução de código**, síntese e entrega aos times de PM.
- **Lição:** a IA **amplia o funil de pesquisa**, mas a porta de entrada para capital continua sendo o **mesmo comitê e os mesmos limiares estatísticos** aplicados a humanos. Os registros de raciocínio são parte do controle.

### 3.2 Bridgewater — AIA Labs (o caso de "IA decisora")

- **Estrutura [F].** A divisão *Artificial Investment Associate* (AIA) Labs foi formada em 2023, liderada pelo co-CIO Greg Jensen. Combina LLMs (OpenAI, Anthropic, Perplexity), ML e ferramentas de raciocínio sobre relações causais. Nesse fundo, "**humanos treinam a máquina que determina as regras**" e a IA é a **decisora primária**, mas **humanos supervisionam risco, aquisição de dados e execução**. Fontes: AI Street, 28/02/2025; Institutional Investor, 08/01/2026.
- **Resultados reportados [F].** O fundo AIA rendeu **+11,9% em 2025** (a Institutional Investor cita "AIA Labs 15 grew 11%"), **+8,1% no 1S26** e **+16,4% em 2026 até o fim de setembro**, com AUM acima de **US$ 4,5 bi**. A Reuters (01/10/2026) cita **13,2% a.a.** "desde o lançamento no fim de 2023". Outras fontes datam o fundo de meados de 2024, com US$ 2 bi; a discrepância não foi resolvida. O CEO Nir Bar Dea diz que o fundo gera "*unique alpha that is uncorrelated to what our humans do*". Para comparação, a média dos hedge funds globais estava em +7,25% no ano (Reuters).
- **Componentes publicados [F].**
  - *AIA Forecaster* (arXiv 2511.07678, nov/2025): busca agêntica em notícias, um **agente supervisor** que reconcilia previsões divergentes e **calibração estatística** contra vieses do LLM. Empata com *superforecasters* humanos no ForecastBench. **Fica abaixo do consenso dos mercados de previsão, mas o ensemble "AIA + consenso" supera o consenso sozinho**, ou seja, a informação é aditiva.
  - Parceria com a Thinking Machines (jul/2026): um modelo menor e especializado em triagem de documentos atinge **84,7%** de acurácia média em 6 tarefas, contra 78,2% do GPT-5.5, a um custo **13,8x menor** por tarefa (HedgeFund Alpha, 02/07/2026).
- **Lição [I].** A IA "decisora" funcionou em **macro**, numa firma com **décadas de princípios explícitos e dados proprietários**, com humanos donos do risco. Para um fundo novo de ações LatAm, o aprendizado transferível é técnico: supervisor que reconcilia agentes, calibração estatística das probabilidades do LLM, combinação com o consenso de mercado e modelos pequenos especializados para triagem. A autonomia de decisão **não** é transferível.

### 3.3 Balyasny (BAM) — BAMChatGPT e agentes de *deep research*

- **Organização [F].** O Balyasny tem um time **central** de *Applied AI* criado no fim de 2022, com cerca de **20 pesquisadores, engenheiros e especialistas de domínio** e liderado pelo Chief AI Officer Charlie Flanagan (ex-Google). O BAMChatGPT foi liberado em jun/2023, com ~80% de adoção reportada **[S]**. O modelo é **federado**: plataforma central com customização por time.
- **Agentes descritos (estudo de caso da OpenAI, 06/03/2026) [F]/[S].**
  1. Um agente de *deep research* que sintetiza dezenas de milhares de documentos (filings, research de corretoras, transcrições, *expert calls*) em **saídas estruturadas**.
  2. Um *Central Bank Speech Analyst*, que reduziu a análise de cenários de **~2 dias para ~30 min**.
  3. Um *Merger Arbitrage Superforecaster*, que atualiza continuamente a probabilidade de fechamento de operações de M&A.

  A plataforma está em **~95% de ~180 times** de investimento.
- **Governança [F]/[S].** Avaliação de modelos em **12+ dimensões**: acurácia de previsão, raciocínio numérico, análise de cenários e robustez a ruído. Escolha de modelo **por tarefa**. **Acesso a ferramentas com escopo e mínimo privilégio**, raciocínio auditável, agentes testáveis e *feedback loops* com auditoria de resultados. Frase-síntese: *"turning information into a structured view you can trust, fast enough to act"*.
- **Lição:** é o modelo mais próximo do que precisamos. **Plataforma central + agentes de pesquisa por caso de uso + evals próprios + saída estruturada + PM decide.**

### 3.4 Millennium — plataforma de pods, risco e IA no risco

- **Desenho organizacional [S].** Mais de 320 times (pods) com capital alocado. A regra reportada pelo WSJ e reproduzida em fontes secundárias é: **perda de 5% → capital cortado pela metade; 7,5% → saída do PM**. Na prática, o risco começa a reduzir capital por volta de −2,5% a −3% do pico **[S]**. Os pods operam sob limites centrais de net/gross, beta, setor e fatores.
- **IA [F].** Em 06–07/08/2026, a Millennium anunciou parceria com a Anthropic para um **"digital risk analyst"**. Engenheiros da Anthropic trabalham com o time de risco para acelerar a análise de posições, **explicar mudanças diárias de risco**, interrogar dados e formar opinião sobre exposições, com memória entre interações. A frase do CIO Vlad Torgovnik: *"keeping human judgment at the centre of decision-making"*. Há também um laboratório interno de IA e, segundo a Business Insider (set/2026), "AI twins" para mais de 7.000 funcionários, com piloto de 97% de uso diário, sem poder de decisão autônoma, com credenciais e trilhas de auditoria próprias **[S]**.
- **Lição:** o primeiro grande uso de LLM numa plataforma de pods é **no risco**, como **explicador** das exposições, não como gerador de trades. Isso é diretamente aplicável ao nosso "agente de risco".

### 3.5 Citadel — ceticismo sobre alfa, entusiasmo sobre produtividade

- **[F]** Ken Griffin, em 16/10/2025 (conferência JPMorgan): a GenAI tem uso claro de produtividade, mas sua capacidade de gerar retorno em excesso *"just falls short"* e **não substituiu a pesquisa profunda** da Citadel.
- **[F]** O mesmo Griffin, em 16/05/2026 (Stanford): disse ter visto um **salto de capacidade interno**, com tarefas de profissionais com mestrado ou PhD feitas por **agentes em horas ou dias** em vez de semanas ou meses (*"extraordinarily high skilled jobs being… automated by agentic AI"*).
- **[S]** Contraexemplo histórico: o laboratório de IA da Citadel em Seattle (Li Deng, ex-Microsoft) foi encerrado, com atrito cultural entre cientistas e PMs citado como causa.
- **Lição:** sem integração ao fluxo do PM, o investimento em IA não vira P&L. A curva de capacidade de agentes está subindo rápido, o que justifica uma arquitetura modular para trocar de modelo.

### 3.6 Point72 — IA para produtividade; Turion é *tema*, não *gestor*

- **[F]** O fundo **Turion** (PM Eric Sanchez) rendeu ~30% em 2025, com ~US$ 3 bi (Hedgeweek, 12/11/2025). **Atenção:** o Turion é **stock-picking temático em IA** (semicondutores e hardware), gerido por humanos, e **não** um fundo gerido por IA. Não deve ser usado como evidência de "IA que gera alfa".
- **[F]/[S]** Steve Cohen (Sohn, abr/2024): o CTO estimou que LLMs poderiam economizar ~**US$ 25 mi** à firma, um ganho de custo. A unidade *Market Intelligence* usa AI/ML sobre dados alternativos e *channel checks*. Há vagas de "AI Engineer, Long/Short Equities" e de chefia de GenAI.
- **Lição:** IA integrada aos pods de L/S como infraestrutura de pesquisa, com governança central.

### 3.7 Two Sigma — alerta de overfitting e lição dura de governança de modelos

- **[F]** Outlook de IA 2026 (21/01/2026, assinado por CTO, Chief AI Innovation Officer e outros):
  - os LLMs aceleraram a engenharia de features ("insights que levariam meses, em dias");
  - porém, *"With AI agents, researchers can easily generate a large number of hypotheses and backtest them, which can exacerbate the overfitting issue"*;
  - e é preciso *"be especially cautious trusting backtest results that predate the model's knowledge cutoff"*.
- **[F]** Em jan/2025, a SEC aplicou multa de **US$ 90 mi**, mais US$ 165 mi de ressarcimento a clientes. Funcionários tinham **acesso de leitura e escrita a parâmetros de modelos em produção** desde ao menos 2019, e um pesquisador alterou parâmetros sem autorização. O monitoramento só começou em ago/2023.
- **Lição:** **parâmetros e configs de modelos precisam ser imutáveis, versionados, com hash e controle de acesso**, exatamente como o invariante de aprovação por hash do AGENTS.md.

### 3.8 D. E. Shaw — pouca divulgação

- **[F]** Há um time de *Generative AI Services* que constrói "agentes sob medida" com os usuários internos (vagas de *Applied AI Engineer*) e uma frente de GenAI em RH. A gestora também é investidora de OpenAI e Anthropic.
- **[S]** A Resonanz descreve um stack "Assistants – LLM Gateway – DocLab" com modelo federado e *guardrails* centrais. Não confirmamos em fonte primária.
- **Lição [I]:** um gateway LLM central (roteamento, logging, política) mais apps por mesa é o padrão de infraestrutura.

### 3.9 Renaissance — o contraste

- **[F]/[S]** A Renaissance é ML e estatística pura há décadas, sem narrativa de LLM, com o Medallion fechado a terceiros. Mesmo assim, os fundos institucionais sofreram: **RIEF −14,39% e RIDA −15,6% em out/2025** (Institutional Investor, 12/11/2025). Antes, em abr/2025, o RIEF caiu ~8% no choque tarifário.
- **Lição:** sofisticação de modelo **não** elimina risco de fatores e de *crowding*. Gestão de risco e regras de desalavancagem são insubstituíveis.

### 3.10 BlackRock — LLMs especializados, Aladdin Copilot e o paper AlphaAgents

- **Systematic Active Equity [F].** A BlackRock usa LLMs **ajustados para tarefas específicas**. O exemplo divulgado é um modelo de reação a *earnings calls*, treinado em **400 mil+ transcrições de 17 mil+ empresas** com duas décadas de dados. Ele supera os modelos GPT num teste com 500 calls do 1T24 (BlackRock, 29/07/2024). Uma fonte secundária cita 61,3% de acurácia na direção do retorno em 40 dias, contra 49,7–54,9% dos GPTs **[S]**. A BlackRock também tem o "Thematic Robot" para cestas temáticas, com supervisão de PM.
- **Aladdin Copilot [F]/[S].**
  - Arquitetura de **supervisor**, escolhida explicitamente em vez de agentes autônomos conversando entre si, por confiabilidade e testabilidade.
  - **Registro de plugins** por onde 50–60 times contribuem.
  - Filtro de ferramentas por permissão: de milhares para 20–30 relevantes.
  - Guardrails de entrada (PII, fora de tópico) e de saída (detecção de alucinação).
  - ***Evaluation-driven development***: evals no CI diariamente e a cada PR, com LLM-as-judge.

  Construído com LangGraph.
- **AlphaAgents (arXiv 2508.11152, 15/08/2025) [F].**
  - **Arquitetura:** três agentes (*Fundamental*, com RAG sobre 10-K/10-Q; *Sentiment*, sobre notícias; *Valuation*, sobre preço e volume, **com ferramenta de cálculo determinística** para retorno e volatilidade, para evitar números alucinados). O *debate* em *round-robin* segue até o consenso, e os logs ficam disponíveis para revisão e *override* humano. A implementação usa AutoGen e GPT-4o.
  - **Teste:** pequeno, com **15 ações de tecnologia**, carteira formada em 01/02/2024 e 4 meses de avaliação.
  - **Resultado:** o multiagente bateu o benchmark e os agentes individuais no perfil neutro a risco. **Todos os portfólios avessos a risco perderam do benchmark.**
  - **Ressalva dos autores:** *"not yet a full portfolio optimization engine"*. Eles sugerem usar o sistema **como insumo** para Mean-Variance ou **Black-Litterman**.
- **Lição:** o paper mais citado de "multiagente para ações" defende o LLM **como fonte de visões que alimenta um otimizador**, com números calculados por ferramentas e humano revisando. A amostra (15 ações, 4 meses, dentro do período de treino do GPT-4o) não comprova alfa.

### 3.11 JPMorgan — LLM Suite, SpectrumGPT e aposta na Numerai

- **[F]** O LLM Suite foi lançado no verão de 2024 e chegou a **200 mil usuários em 8 meses**. É agnóstico de modelo (OpenAI e Anthropic) e serve para ideação e redação (JPMorganChase, 03/06/2025).
- **[F]** O **SpectrumGPT** da JPMAM roda GPT-4 em nuvem própria. Decompõe a pergunta do analista, busca documentos, compara com o *sell-side* e devolve um **rascunho de nota com citações**. A responsável, Arezu Moghadam: *"I'm still the decision maker here, I'm still the accountable person"*. O PM continua dono da decisão (Institutional Investor, 06/10/2023).
- **[F]** A JPMAM garantiu **US$ 500 mi de capacidade** na Numerai (ago/2025), um voto de confiança em ML *ensemble* neutro a fatores (ver 3.15).

### 3.12 Goldman Sachs

- **[F]** O GS AI Assistant foi liberado para toda a firma em jun/2025, depois de um piloto com ~10 mil de ~46,5 mil funcionários. Roda vários LLMs dentro do perímetro de compliance. Agentes ainda estavam em teste em 2025, com monitoramento de qualidade de dados e controles de risco antes do uso.
- **[F]** A GSAM lançou o **AlphaAI** (30/07/2026). Atenção: é uma plataforma para **identificar oportunidades ligadas à IA** (dispersão intrassetorial causada pela IA), não um gestor automatizado.

### 3.13 Morgan Stanley

- **[F]/[S]** O *AI @ Morgan Stanley Assistant* tem **98% de adoção** entre os times de assessores e acesso a mais de 100 mil documentos internos. O *Debrief* resume reuniões. O ponto central é o **framework de avaliação**: evals de sumarização graduados por assessores e engenheiros de prompt. O enquadramento oficial é ganho de produtividade, não corte de custo.
- **Lição:** **evals humanos graduados** antes de colocar em produção.

### 3.14 Fundos e ETFs "geridos por IA" — o histórico

- **[F]** **Smith & Wyatt (Pomona College; Scientific American, 23/08/2024):** todos os fundos e ETFs de IA lançados nos EUA desde out/2017.
  - **11 "totalmente IA"** (sem intervenção humana): **−1,8% a.a.**, contra +7,6% do S&P 500. Todos perderam do índice e 6 dos 11 perderam dinheiro. **6 dos 11 foram encerrados.**
  - **43 "parcialmente IA":** 7,11% a.a. contra 12,43% do S&P. Só 10 dos 43 bateram o índice e 25 dos 43 foram encerrados.
  - Exemplos: AIEQ +63% contra +108% do S&P; MIND −12% contra +65%.
- **[S]** **AIEQ** (Amplify, out/2017): giro de ~804%, taxa de 0,75%, **alfa anualizado de −5,08%** e beta de 1,13 contra o S&P. Em 2025, rendeu 13,96% contra 17,72% do SPY.
- **[F]** **Contraponto recente: Pictet PQUS** (lançado em 25/02/2026, taxa de 22 bps). O modelo de IA é **transparente e neutro a fatores** em relação ao mercado, com 250+ features, baixo *tracking error* e **PMs humanos como guardrails institucionais**. Remove viés de estilo, tamanho, setor e região para isolar alfa "puro". Ainda não tem histórico relevante.
- **Lição:** "IA escolhe ações sozinha" tem **histórico ruim, documentado e público**. A geração nova que atrai capital é **IA + neutralização de fatores + supervisão humana + baixo giro**.

### 3.15 Numerai — ML *crowdsourced*, livro neutro a fatores

- **[F]** É um fundo global de ações long/short. Milhares de cientistas de dados submetem previsões sobre dados ofuscados, com *staking* em token, e os sinais são combinados num *meta-model*.
- **Resultados:** **2024 +25,45% líquido, Sharpe de 2,75**, com um único mês negativo; **2023 −17%**; 2025 cerca de +6% a +8% até out. O AUM passou de US$ 60 mi (2022) para ~US$ 450 mi, e a JPMAM comprometeu US$ 500 mi (Numerai blog, 26/08/2025; Hedgeweek, 28/08/2025).
- **[S]** O drawdown de 2023 foi associado a **desalavancagem de hedge funds e exposição a fatores**. A Numerai neutraliza a muitas exposições de fatores.
- **Lição:** **muitos sinais fracos + neutralização a fatores + ensemble** funcionam, mas mesmo assim exigem tolerância a drawdowns de *crowding*. Neutralizar só beta e dólar não basta.

### 3.16 América Latina

- **Giant Steps Capital [F]/[S].** Descrita como a **maior gestora quant da América Latina**, com R$ 6,5–7 bi (~US$ 1,1–1,5 bi) segundo fontes recentes. Fundada em 2012, com escritórios em NY e SF. Processo **100% sistemático**: o Zarathustra roda ~40 estratégias, nem todas com ML, e envia 20–30 mil ordens por dia. Tem stack próprio de deep learning e RL. Não encontramos divulgação pública de LLM no núcleo de decisão. Rodrigo Terni (2020): *"o fundo quant nada mais é do que um fundo que usa a tecnologia para tomar melhores decisões."* Pedro Simonetti (2023): a IA está "longe de acabar com o trabalho do gestor".
- **Kadima [F].** Cerca de R$ 5 bi (2022–2024), 100% quant, com fundo **long-short de ações**. A casa é "obcecada com a análise do robô": o risco **operacional** (erro de execução) preocupa mais que o de mercado. A construção começa pelas **exposições a fatores desejadas** e só depois escolhe os papéis.
- **XP Atalaia Quant e outros [F].** O InvestNews (abr/2023) identificou 40 fundos "quant" no Brasil, dos quais 27 superaram o Ibovespa desde o início. O levantamento sofre de viés de sobrevivência, ressalva nossa.
- **AWT [F]/[S].** Gestora que se apresenta como "nascida da IA", com 48 agentes artificiais e 12 humanos e R$ 200 mi (2024). É focada em relacionamento e alocação, não em L/S de ações, e o registro na CVM mostra estrutura pequena.
- **Bancos [F].** O Itaú tem o "Itaú Investment Intelligence"/ia.i, um agente de GenAI para clientes de varejo, com piloto em 10 mil clientes.
- **Inferências para LatAm [I]:**
  1. O processamento **multilíngue** (fatos relevantes da CVM, ITR/DFP, CMF do Chile, BMV/CNBV do México, SMV do Peru, 20-F e 6-K das ADRs) é uma vantagem natural dos LLMs. Chen, Kelly & Xiu mostram previsibilidade de notícias via embeddings de LLM em **16 mercados e 13 idiomas** **[F]**.
  2. A literatura indica **mais sub-reação em ações menores, menos líquidas e com notícia negativa** (Lopez-Lira & Tang) **[F]**. Isso sugere mais sinal em LatAm, mas também **custos e restrições de aluguel muito maiores**, sobretudo do lado vendido.
  3. Não há caso público de LLM-PM L/S LatAm com histórico. Somos *first movers*, e por isso precisamos de disciplina de validação acima da média.

---

## 4. O que a evidência acadêmica diz (2023–2026)

| Estudo | Achado quantitativo | Implicação para nós |
|---|---|---|
| **Lopez-Lira & Tang** (arXiv 2304.07619; v6 out/2025) | GPT-4 em manchetes **pós-cutoff** acerta ~90% da reação inicial (não negociável). O *drift* de 1–2 dias dá Sharpe pré-custo de **2,97**, com perna vendida de Sharpe 2,01 e comprada de 0,78. **Lucrativo a 10 bps, não a 20 bps** por round-trip. Sharpe ponderado por valor de **0,56**. O Sharpe cai de **6,54 (2021T4) → 3,68 (2022) → 2,33 (2023) → 1,22 (jan–mai/2024)**, consistente com a difusão de LLMs. Sinal concentrado em **small caps e notícia negativa**; *large caps* sem *drift* após notícia negativa. | Sinais de notícia de 1–2 dias **não sobrevivem** a custos LatAm nem ao horizonte semanal. Usar LLM para **sinais mais lentos** e para **risco de evento**. |
| **Kim, Muhn & Nikolaev** (Chicago Booth, arXiv 2407.17866) | GPT-4 com **CoT** em demonstrações **anonimizadas** acerta **60,35%** da direção dos lucros, contra **52,71%** dos analistas e 60,45% de uma ANN dedicada. **Sem CoT: 52,33%.** Estratégia L/S com **alfa > 12% a.a.** (FF3). Pós-cutoff: 58,96%. | Análise estruturada de ITR/DFP/20-F com **prompt de analista passo a passo** e **números calculados em código** é um sinal plausível de horizonte trimestral, compatível com rebalanceamento semanal. |
| **Chen, Kelly & Xiu** (*Expected Returns and LLMs*, SSRN 4416687) | Embeddings de LLM sobre notícias superam sentimento por dicionário e sinais técnicos. Os preços reagem devagar. Resultado em **16 mercados e 13 idiomas**. | Base para usar **embeddings multilíngues** como feature, e não "opinião" do LLM. |
| **Glasserman & Lin** (arXiv 2309.17322) | **Anonimizar** a empresa na manchete **melhora** o desempenho: o efeito de "distração" do conhecimento prévio supera o viés de *look-ahead*, mais forte em *large caps*. Beta da estratégia anonimizada **≈ 0**. | **Anonimizar entidades** ao pontuar texto, em backtest e possivelmente em produção. |
| **Lopez-Lira, Tang & Zhu — *Memorization Problem*** (arXiv 2504.14765) | O GPT-4o lembra valores exatos de índices, macro e preços antes do cutoff. Com instrução "ignore pós-2010": **97,6% vs 98,0%** de acerto, contra **40%** no período realmente pós-cutoff. **Mascarar não resolve**, porque o modelo reconstrói a entidade; a memorização vale até para embeddings. | **Backtests de sinais LLM só após o cutoff do modelo usado.** Registrar o cutoff de cada modelo na config. |
| **Chen, Green, Gulen & Zhou** (2024); **Gao, Jiang & Yan** (2026) | LLMs **extrapolam** retornos passados (coeficiente 0,394 no último mês); prompts não corrigem. | Nunca pedir ao LLM previsão de retorno a partir de série de preços. |
| **FINSABER** (Li et al., KDD'26, arXiv 2505.07078) | Vantagens de LLM-traders (FinMem, FinAgent) **desaparecem** em 20 anos e 100+ ativos. LLMs são **conservadores demais em alta e agressivos demais em queda**. "*Not model scale, but lack of domain-aware financial logic*." | Regime e risco ficam no motor quant; não confiar em "agente trader". |
| **Gençay — *What survives honest evaluation?*** (arXiv 2608.27734, ago/2026) | Com feature registry à prova de *look-ahead* e **ledger de todas as tentativas**, o melhor achado do agente (SR 1,69 *in-sample*) tem **DSR 0,86 < 0,95** e cai a SR 0,18 fora da amostra. **0 de 5** rodadas sobrevivem. Um oráculo com vazamento e **SR 35 passa** em DSR e PBO, então vazamento só se evita **estruturalmente**. Com SR verdadeiro de 0,6, são **~11 anos** para t ≈ 2. | Ledger de tentativas + DSR/PBO obrigatórios; features *point-in-time* por construção; expectativas realistas sobre o tempo de validação. |
| **AIA Forecaster** (Bridgewater, arXiv 2511.07678) | LLM agêntico + supervisor + calibração **≈ superforecasters**. Fica abaixo do mercado sozinho, mas é **aditivo** em ensemble. | Usar probabilidades do LLM **calibradas** e **combinadas** com o consenso, nunca sozinhas. |
| **Alpha Arena (Nof1)**, S1 out–nov/2025 (cripto, US$ 10 mil/modelo) e S1.5 (ações dos EUA) | S1: 4 de 6 modelos perderam (GPT-5 −63%, Gemini −57%, Grok −45%, Claude Sonnet −31%; só Qwen3 Max +22% e DeepSeek +5% lucraram), com P&L "dominado por custos" por *overtrading*. S1.5: carteira agregada perdeu ~1/3, e só 6 de 32 resultados foram lucrativos (Bloomberg Línea, 09/05/2026). | LLM operando sozinho, com alta frequência e sem controle de custos, **destrói valor**. |

---

## 5. Síntese: padrão de sucesso vs. padrões de fracasso

### 5.1 O padrão dominante de sucesso

```
Dados brutos (point-in-time, imutáveis)
   │
   ├─► [Agentes LLM de pesquisa]  — leem filings/calls/notícias (PT/ES/EN)
   │      saída: JSON estruturado + citações + confiança calibrada
   │      (nunca calculam números; usam ferramentas determinísticas)
   │
   ├─► [Motor quant determinístico] — sinais, modelo de risco de fatores,
   │      otimizador com neutralidade (US$, beta, setor, estilos),
   │      vol-target, limites de liquidez/borrow/squeeze
   │
   ├─► [Agente de risco] — EXPLICA mudanças de risco calculadas em código
   │
   └─► [PM humano] — decide, sobrescreve com justificativa registrada,
          aprova versão com hash; exportação bloqueada sem aprovação
```

Elementos comuns a Man, Balyasny, BlackRock, JPMAM, Millennium e Morgan Stanley **[F]**, com a síntese em diagrama sendo **[I]**:

1. **Plataforma central e uso federado**: gateway, logs e política; os times customizam.
2. **Saída estruturada e auditável** (*"structured view you can trust"*), com citações à fonte.
3. **Ferramentas determinísticas** para qualquer número: o *Valuation Agent* do AlphaAgents usa uma calculadora; a Man usa *code execution*.
4. **Mesmo comitê e mesmos limiares** para ideias humanas e de IA (Man).
5. **Evals contínuos**: 12+ dimensões no Balyasny; CI diário na BlackRock; graduação humana no Morgan Stanley.
6. **Humano responsável pela decisão** ("I'm still the decision maker"); a IA amplia o funil e acelera.
7. **Risco central forte**: neutralidade de fatores, *crowding*, *stops* de drawdown.

### 5.2 Padrões de fracasso

| Padrão | Evidência | Mecanismo |
|---|---|---|
| LLM escolhe e dimensiona posições de ponta a ponta | Fundos 100% IA (−1,8% a.a.), AIEQ, Alpha Arena, FINSABER | Sem lógica financeira de domínio, sem controle de regime e custo, *overtrading* |
| Backtest dentro do período de treino do LLM | Memorization Problem; Two Sigma 2026 | Memorização; prompts de "corte" não funcionam |
| Busca agêntica massiva sem correção por tentativas | Gençay 2026; Two Sigma; Man reconhece o risco | Inflação por seleção (DSR/PBO) |
| Sinal de altíssima frequência em mercado caro | Lopez-Lira & Tang (morre a 20 bps) | Custos e *price impact* |
| Ignorar fatores e *crowding* | Quants −4,2% em jun–jul/2025; RIEF −14,4% em out/2025; Numerai −17% em 2023 | Desmonte simultâneo de posições populares |
| Governança fraca de modelos | SEC vs Two Sigma (US$ 90 mi) | Parâmetros de produção editáveis sem controle |
| IA isolada do usuário final | Laboratório de IA da Citadel encerrado **[S]** | Atrito cultural; ninguém usa |
| Arquitetura multiagente "livre" | A BlackRock escolheu supervisor; FINSABER: "complexidade não é a resposta" | Difícil testar, depurar e auditar |

---

## 6. Desenho organizacional observado e aplicável

| Elemento | Prática observada | Adaptação proposta para nosso fundo **[I]** |
|---|---|---|
| Estrutura | Pods com PM dono do P&L, sob risco central (Millennium, Citadel, Balyasny, Point72) | 1 PM humano (decisor), 1 "pod" sistemático; risco independente (humano + agente explicador) |
| Time de IA | Central, ~20 pessoas no Balyasny; *Applied AI* / *GenAI Services* | Módulo central `research_ai` com agentes por caso de uso, provedor de LLM plugável e modo Demo offline |
| Limites de exposição | Pods fundamentais com net entre −20% e +20% e gross de 4–8x do capital alocado **[S]**; livros *factor-neutral* via modelo de risco tipo Barra | Fundo **market neutral**: net em US$ ≈ 0, beta ≈ 0, fatores ≈ 0 (ver tabela 8) |
| Drawdown | −5% → −50% do capital; −7,5% → saída (Millennium/WSJ) **[S]**; ação real a partir de −2,5%/−3% | Escada de drawdown calibrada ao vol-alvo de 5% (tabela 8) |
| Risco | "Digital risk analyst" explica mudanças diárias (Millennium + Anthropic) | Agente de risco gera **narrativa** sobre métricas calculadas em código |
| Pesquisa | *Deep research agent*, notas de manhã, alertas de mudança em 10-K (Balyasny); rascunhos com fontes (JPMAM) | Ficha semanal por ativo: tese, catalisadores, riscos, bull/bear, eventos, com citações |
| Ideias quant | AlphaGPT: ideia → código → avaliador → comitê | Fase 2: gerador de hipóteses só com feature registry *point-in-time* + ledger + DSR |
| Avaliação de IA | Evals por dimensão, CI, LLM-as-judge, graduação humana | Golden set de documentos LatAm; métricas de extração e citação; regressão a cada mudança de prompt ou modelo |
| Governança | Mínimo privilégio, trilhas de auditoria, sem decisão autônoma (Millennium, Balyasny) | Aprovação vinculada a hash (texto, FactBook, evidências, config); sem autoaprovação; notícias como conteúdo não confiável |

---

## 7. Práticas a copiar — lista priorizada para um L/S LatAm semanal

### P0 — essenciais desde o dia 1

1. **Separação rígida de papéis (Man, BlackRock, JPMAM, AGENTS.md).** O LLM **extrai e estrutura**. O código **calcula** retornos, scores, riscos e pesos. O otimizador **constrói** o portfólio. O PM **decide e aprova**.
2. **Construção market neutral de verdade (Numerai, Pictet, pods).** Neutralidade de dólar, beta (ex-ante, contra MSCI EM LatAm ou mercados locais em USD), setor e país e estilos principais (tamanho, valor, momentum, beta, volatilidade, liquidez), com fração-alvo de risco idiossincrático. Vol-alvo de 5% ex-ante.
3. **Disciplina *point-in-time* e de avaliação (Two Sigma, Gençay, Lopez-Lira):**
   - **(a)** dados *as-of* imutáveis;
   - **(b)** sinais LLM avaliados **somente após o cutoff do modelo**;
   - **(c)** **ledger de tentativas** com DSR e PBO antes de qualquer sinal entrar no alfa;
   - **(d)** anonimização de entidades em backtests de texto;
   - **(e)** período de *paper trading* / *shadow* antes de peso relevante.
4. **Risco de *crowding*, liquidez e *short squeeze* como restrições duras (MSCI, Resonanz):** short interest / days-to-cover, custo e disponibilidade de aluguel (BTC B3; borrow das ADRs), % do livro vendido em nomes *hard-to-borrow*, concentração top-10, % do ADV e dias para liquidar.
5. **Escada de drawdown pré-definida e automática (pods)**, com a decisão de desalavancar registrada e aprovada.
6. **Governança de modelo e config (lição Two Sigma):** parâmetros versionados, com hash, somente leitura em produção, mudanças via PR e aprovação humana.

### P1 — no primeiro trimestre

7. **Agente de *deep research* semanal por ativo (Balyasny / JPMAM):** gera a ficha estruturada que alimenta a reunião de segunda-feira, com fontes em PT, ES e EN e citações verificáveis.
8. **Debate bull/bear entre agentes (AlphaAgents)** como **insumo de visões** com peso limitado (estilo Black-Litterman), nunca como ordem.
9. **Sinais de texto de horizonte compatível com a semana:**
   - análise CoT de demonstrações (Kim et al.);
   - variação de tom e de *guidance* em *calls*;
   - revisão de estimativas;
   - eventos corporativos (fatos relevantes).

   Evitar depender de *drift* de notícia de 1–2 dias.
10. ***Evaluation-driven development* (BlackRock, Morgan Stanley, Balyasny):** golden set LatAm; métricas de fidelidade de extração, cobertura de citações, calibração e robustez a texto adversarial (prompt injection em notícias); evals no CI.
11. **Agente de risco explicador (Millennium):** narrativa diária e semanal das mudanças de exposição e P&L por fator, sempre sobre números do FactBook.

### P2 — evolução (6–12 meses)

12. **Gerador de hipóteses tipo AlphaGPT** sobre um feature registry tipado e *point-in-time*, com ledger e DSR e com comitê humano.
13. **Modelos pequenos e especializados para triagem** de notícias e documentos (Bridgewater + Thinking Machines: −13,8x de custo), avaliados contra o modelo grande.
14. **Calibração e ensemble** das probabilidades do LLM com o consenso de mercado (AIA Forecaster).
15. **Embeddings multilíngues** como features num modelo de ML neutro a fatores (Chen-Kelly-Xiu), validados pós-cutoff.

---

## 8. Tabela de parâmetros (prática observada → valor proposto)

| Parâmetro | Valor proposto | Base / justificativa | Tipo |
|---|---|---|---|
| Vol-alvo ex-ante | **5% a.a.** (banda 3–7%) | Mandato do fundo | Mandato |
| Exposição líquida em US$ | **\|net\| ≤ 2% do NAV** (meta 0) | Mandato net neutral; pods fundamentais toleram ±20%, mas um fundo market neutral precisa de banda estreita | [I] |
| Beta ex-ante ao mercado | **\|β\| ≤ 0,05** | Neutralidade de beta para "alfa puro" (Pictet e Numerai neutralizam fatores) | [I] |
| Exposição a fatores de estilo | **\|z\| ≤ 0,10–0,20 σ** por fator | Livros *factor-neutral* via modelo de risco; *crowding* de 2025 | [I] |
| Fração de risco idiossincrático | **≥ 70–80%** da variância ex-ante | Prática comum de pods de mercado neutro **[S]**; "alfa puro" | [I]/[S] |
| Exposição líquida por setor e país | **≤ 3–5% do NAV** | Evitar macro LatAm (BRL, MXN, CLP) disfarçada de alfa | [I] |
| Escada de drawdown (do pico) | **−2,5%:** revisão de risco e corte de gross de 25%; **−5%:** corte de gross de 50%; **−7,5%:** gross mínimo e revisão completa do processo | Regra reportada da Millennium (−5% → −50% de capital; −7,5% → saída), ação a partir de −2,5%/−3% **[S]**, escalada para vol de 5% (≈ 0,5σ / 1σ / 1,5σ anual) | [I]/[S] |
| Validação de novo sinal | **DSR ≥ 0,95** sobre o nº real de tentativas; **PBO < 0,5** (CSCV, S = 16) | Bailey & López de Prado; Gençay 2026 | [F]→[I] |
| Janela de backtest de sinal LLM | **Somente após o knowledge cutoff** do modelo usado | Lopez-Lira, Tang & Zhu; Two Sigma | [F] |
| Expectativa de validação | SR 0,6 → **~11 anos** para t ≈ 2; com SR 1,0 → ~4 anos | Gençay (t ≈ SR·√anos) | [F] |
| Custo de referência de sinal de notícia | Sinal de 1–2 dias **inviável acima de ~10–20 bps** por round-trip | Lopez-Lira & Tang | [F] |
| Horizonte dos sinais de texto | **Semanas a trimestres** (fundamentos, *guidance*, eventos) | Rebalanceamento semanal + custos LatAm | [I] |
| Prompting de análise de demonstrações | **CoT estruturado** (60,35% vs 52,33% sem CoT); números via código | Kim, Muhn & Nikolaev | [F] |
| Anonimização no backtest de texto | Substituir nome, ticker e produtos por token neutro | Glasserman & Lin | [F] |
| Evals de agentes | **≥ 12 dimensões**; rodar a cada mudança de prompt ou modelo e diariamente | Balyasny; BlackRock (CI diário e por PR) | [F]→[I] |
| Ferramentas expostas ao agente | **Mínimo privilégio**; ~20–30 ferramentas filtradas por contexto | Balyasny; Aladdin Copilot | [F]→[I] |
| Ledger e log de decisões de agentes | Todo *rationale* registrado (Man) + hash da versão aprovada | Man Group; AGENTS.md | [F] |
| Monitores de *crowding* | % do short em HTB, top-10 % do gross, sobreposição com fatores populares, z-score de *crowding* | Resonanz (nov/2025); MSCI (jul/2025) | [F]→[I] |

---

## 9. O que **evitar** (lista explícita)

1. **LLM escolhendo, dimensionando ou executando posições sozinho.** O histórico público é negativo: fundos 100% IA a −1,8% a.a., AIEQ, Alpha Arena, FINSABER.
2. **LLM calculando qualquer número** (retorno, risco, peso, contribuição, valuation). Use ferramentas determinísticas testadas; o AlphaAgents fez isso por causa de alucinação numérica.
3. **Backtest de sinais LLM dentro do período de treino** e confiança em prompts do tipo "ignore dados após X". Está provado que não funciona.
4. **Busca agêntica de sinais sem ledger e sem DSR/PBO.** A produtividade do agente vira amplificador de viés.
5. **Sinais de notícia de altíssimo giro** em mercados com custo e *price impact* altos (LatAm, especialmente *small/mid caps* e o lado vendido).
6. **Neutralizar só dólar.** Sem neutralidade de beta, setor, país e fatores, o "alfa" vira aposta macro ou de estilo e fica exposto a desmontes de *crowding* como os de 2025.
7. **Short em nomes *crowded* ou de aluguel caro sem limite.** O *short squeeze* é risco de cauda, e os perfis de alta volatilidade residual e baixa liquidez concentraram as perdas de 2025 (MSCI).
8. **Configs e parâmetros editáveis em produção sem trilha** (caso Two Sigma, US$ 90 mi de multa).
9. **Autoaprovação ou aprovação não vinculada à versão** (texto, FactBook, evidências e config com hash).
10. **Notícia tratada como instrução.** Conteúdo externo é não confiável, e prompt injection é um vetor real em agentes com ferramentas.
11. **Arquitetura multiagente "conversacional" sem supervisor, sem testes e sem evals.** Prefira o padrão supervisor + ferramentas tipadas.
12. **Confundir "fundo temático de IA" com "fundo gerido por IA"** (Turion, GSAM AlphaAI) ao buscar evidência.
13. **Overtrading.** Em várias competições de LLM, as taxas comeram o P&L. Restrinja o giro no otimizador.
14. **Prometer alfa de IA a investidores** sem *track record* fora da amostra. Os alocadores pedem "evidence over rhetoric" (AIMA).

---

## 10. Implicações diretas para a arquitetura do projeto [I]

- **Módulos:** `data` (snapshots *point-in-time* imutáveis) → `analytics/risk` (modelo de fatores, beta, vol, liquidez, *crowding*) → `alpha` (sinais quant + sinais estruturados de texto com peso limitado) → `optimizer` (neutralidades, vol-alvo, limites) → `research_ai` (agentes de ficha por ativo, bull/bear e risco explicador, todos com saída JSON validada por schema e citações) → `workflow` (reunião de segunda, overrides com justificativa, aprovação por hash, exportação bloqueada sem aprovação).
- **Provedores de LLM plugáveis**, com `DemoProvider` determinístico para testes offline e registro do *knowledge cutoff* de cada modelo na config, para bloquear avaliações contaminadas.
- **Ledger de experimentos** (todas as variantes testadas) e relatório de DSR/PBO como pré-requisito para um sinal entrar em produção.
- **Dashboard de segunda-feira**: exposições (US$, beta, setor, país, fatores), contribuição de risco idiossincrático vs fatorial, liquidez (dias para liquidar, % do ADV), painel de *squeeze* (short interest, days-to-cover, custo de aluguel), escada de drawdown e fichas de pesquisa com citações.

---

## 11. Fontes (numeradas, com data)

1. Man Group — "Man Group teams up with Anthropic to put AI at the centre of investing", 11/02/2026. https://www.man.com/news-centre/man-group-anthropic-partnership
2. Hedgeweek — "Man Group deploys agentic AI for quant signal discovery", 11/07/2025. https://www.hedgeweek.com/man-group-deploys-agentic-ai-for-quant-signal-discovery/
3. AI Street (M. Robinson) — "Man Group Details its AlphaGPT", 20/11/2025. https://www.ai-street.co/p/man-group-details-its-alphagpt
4. AI Street — "Inside Man Group's AlphaGPT", 18/12/2025. https://www.ai-street.co/p/inside-man-group-s-alphagpt
5. AI Street — "Man Group Builds Internal AlphaGPT" (inclui ManGPT 50% e Morgan Stanley/Goldman), 20/03/2025. https://www.ai-street.co/p/man-group-s-alphagpt
6. Hedgeweek — "Man technologists cautious on AI's ability to generate alpha", 08/12/2023. https://www.hedgeweek.com/man-technologists-cautious-on-ais-ability-to-generate-alpha/
7. CNN Business (via ABC17) — "AI won't be making decisions anytime soon, says head of a top hedge fund" (Robyn Grew), 26/07/2024. https://abc17news.com/money/cnn-business-consumer/2024/07/26/ai-wont-be-making-decisions-anytime-soon-says-head-of-a-top-hedge-fund/
8. Reuters (via Y94) — "Bridgewater's flagship macro fund posts double-digit gains this year", 01/10/2026. https://y94.com/2026/10/01/bridgewaters-flagship-macro-fund-posts-robust-double-digit-gains-this-year-sources-say/
9. Institutional Investor — "Behind Bridgewater's Surge", 08/01/2026. https://www.institutionalinvestor.com/article/behind-bridgewaters-surge
10. AI Street — "Bridgewater's AI Fund Generating 'Unique Alpha'", 28/02/2025. https://www.ai-street.co/p/bridgewater-ceo-ai-fund-generating-unique-alpha
11. Bridgewater AIA Labs — "AIA Forecaster: Technical Report", arXiv 2511.07678, 10/11/2025. https://arxiv.org/abs/2511.07678
12. HedgeFund Alpha — "Bridgewater Teams Up With Ex-OpenAI CEO To Build AI…", 02/07/2026. https://hedgefundalpha.com/news/bridgewater-thinking-machines-ai/
13. Gend.co (reprodução do estudo de caso OpenAI) — "Balyasny's AI Research Engine: GPT-5.4", ~06/03/2026. https://www.gend.co/blog/balyasny-ai-research-engine-gpt-5-4 ; original (403 para fetch): https://openai.com/index/balyasny-asset-management/
14. Balyasny — "Balyasny Applied AI Team Featured in OpenAI Customer Story", 06/03/2026. https://www.bamfunds.com/news-and-insights/balyasny-openai-feature
15. eFinancialCareers — "Hedge fund Balyasny hiring Google AI experts…", 2024. https://www.efinancialcareers.com/news/balyasny-hedge-fund-generative-ai-google
16. Resonanz Capital — "AI Use by Hedge Funds Made Tangible", 03/06/2025. https://resonanzcapital.com/insights/ai-use-by-hedge-funds-made-tangible-from-lego-bots-to-alpha-assistants
17. The TRADE — "Millennium rolls out AI-powered digital risk analyst", 07/08/2026. https://www.thetradenews.com/millennium-rolls-out-ai-powered-digital-risk-analyst/
18. Bloomberg — "Millennium Partners With Anthropic to Develop AI Risk Analyst", 06/08/2026. https://www.bloomberg.com/news/articles/2026-08-06/millennium-partners-with-anthropic-to-develop-ai-risk-analyst
19. Hyper.ai (resumo de Business Insider) — "Millennium Deploys Personalized AI Twins To All Employees", ~set/2026. https://hyper.ai/en/stories/e35677020f55acfdfef504c690ab571e
20. Motley Fool (citando WSJ) — Millennium: regra de 5% / 7,5%. https://www.fool.com/investing/how-to-invest/famous-investors/millennium-management/ ; complemento: https://hedgefundinterview.com/pod-shop-risk-limits
21. StartupHub (vídeo Bloomberg) — "Ken Griffin: Generative AI Falls Short on Hedge Fund Alpha", 16/10/2025. https://www.startuphub.ai/ai-news/ai-video/2025/ken-griffin-generative-ai-falls-short-on-hedge-fund-alpha/
22. The Deep Dive — "Citadel's Ken Griffin Recasts AI Risk Inside High Finance", 16/05/2026. https://thedeepdive.ca/ken-griffin-ai-citadel-shift/
23. Hedgeweek — "Point72's Turion fund posts 30% gain", 12/11/2025. https://www.hedgeweek.com/point72s-turion-fund-posts-30-gain/
24. Benzinga/CNBC — "Steve Cohen's Point72 can save $25M by using AI", 03/04/2024. https://www.cnbc.com/2024/04/03/steve-cohen-says-his-financial-firm-can-already-save-25-million-by-using-ai-.html
25. Two Sigma — "AI in Investment Management: 2026 Outlook (Part II)", 21/01/2026. https://www.twosigma.com/articles/ai-in-investment-management-2026-outlook-part-ii/
26. Charltons Quantum / SEC — "US SEC charges Two Sigma… $90m penalty", 17/01/2025. https://charltonsquantum.com/us-sec-charges-two-sigma-with-failing-to-address-model-vulnerabilities-imposes-90m-penalty/
27. D. E. Shaw — vaga "Applied AI Engineer" (GenAI Services). https://www.deshaw.com/careers/software-developer-generative-ai-5375
28. Institutional Investor — "Renaissance Suffers Huge Losses in October", 12/11/2025. https://www.institutionalinvestor.com/article/renaissance-suffers-huge-losses-october
29. Hedgeweek — "Renaissance quant funds see steep losses amid tariff turmoil", abr/2025. https://www.hedgeweek.com/renaissance-quant-funds-see-steep-losses-amid-tariff-turmoil/
30. BlackRock — "How AI is Transforming Investing", 29/07/2024. https://www.blackrock.com/institutions/en-apac/insights/thought-leadership/ai-investing
31. Zhao et al. (BlackRock) — "AlphaAgents: LLM based Multi-Agents for Equity Portfolio Constructions", arXiv 2508.11152, 15/08/2025. https://arxiv.org/abs/2508.11152
32. ZenML LLMOps DB — "BlackRock: Agentic AI Architecture for Investment Management Platform" (Aladdin Copilot). https://www.zenml.io/llmops-database/agentic-ai-architecture-for-investment-management-platform
33. Welcome.ai — "BlackRock's AI Model Surpasses GPT-4 in Earnings Predictions" [S]. https://www.welcome.ai/content/article-1756823353.347338
34. JPMorganChase — "LLM Suite named 2025 'Innovation of the Year'", 03/06/2025. https://www.jpmorganchase.com/about/technology/blog/llmsuite-ab-award
35. Institutional Investor — "J.P. Morgan Promises Its Fundamental PMs an AI 'Co-Pilot,' Not a Boss", 06/10/2023. https://www.institutionalinvestor.com/article/2ca5f0pgripub280t9hxc/corner-office/j-p-morgan-promises-its-fundamental-portfolio-managers-an-ai-co-pilot-not-a-boss
36. Numerai — "JPMorgan Secures $500m Capacity in Numerai Following Breakthrough Year", 26/08/2025. https://blog.numer.ai/jpmorgan-secures-500m-capacity/
37. Hedgeweek — "Quant hedge fund Numerai secures $500m JPMorgan allocation", 28/08/2025. https://www.hedgeweek.com/quant-hedge-fund-numerai-secures-500m-jpmorgan-allocation/
38. Numerai docs — OHwA S01E04 (drawdown de 2023, neutralidade de fatores). https://docs.numer.ai/office-hours-with-arbitrage/office-hours-recaps/ohwa-4
39. Storyboard18 / Fortune — "Goldman Sachs rolls out Generative AI Assistant firmwide", 24/06/2025. https://fortune.com/2025/06/24/goldman-sachs-internal-ai-assistant
40. Hubbis — "Goldman Sachs Asset Management Launches AlphaAI Investment Platform", 30/07/2026. https://hubbis.com/news/goldman-sachs-asset-management-launches-alphaai-investment-platform
41. OpenAI — "Morgan Stanley" (estudo de caso: evals, 98% de adoção). https://openai.com/index/morgan-stanley/
42. Scientific American (G. Smith & S. Wyatt) — "Don't Trust AI for Important Things Such As Investment Decisions", 23/08/2024. https://www.scientificamerican.com/article/ai-makes-unreliable-investment-decisions
43. Pluang/Seeking Alpha — "AIEQ: Unconvincing AI-Driven Strategy Still Lagging The Market" [S], 2026. https://seekingalpha.com/article/4949900-aieq-unconvincing-ai-driven-strategy-still-lagging-the-market
44. Business Wire — "Pictet Asset Management Launches Pictet AI Enhanced US Equity ETF PQUS", 25/02/2026. https://www.businesswire.com/news/home/20260225293290/en/Pictet-Asset-Management-Launches-Pictet-AI-Enhanced-US-Equity-ETF-PQUS
45. AIMA — "Front-office Gen AI adoption shifts from 'if' to 'when'…" (*Charting the course*), 16/09/2025. https://www.aima.org/article/press-release-front-office-gen-ai-adoption-shifts-from-if-to-when-for-leading-fund-managers-aima-research-finds.html
46. MSCI — "Unraveling Summer 2025's Quant Fund Wobble", 2025. https://www.msci.com/research-and-insights/blog-post/unraveling-summer-2025s-quant-fund-wobble
47. Resonanz Capital — "Understanding the 2025 Quant Unwind: A Practical Guide for Allocators and Managers", 24/11/2025. https://resonanzcapital.com/insights/crowding-deleveraging-a-manual-for-the-next-quant-unwind
48. Lopez-Lira & Tang — "Can ChatGPT Forecast Stock Price Movements?", arXiv 2304.07619 (v6, 28/10/2025). https://arxiv.org/abs/2304.07619
49. Kim, Muhn & Nikolaev — "Financial Statement Analysis with Large Language Models", arXiv 2407.17866 (2024). https://arxiv.org/abs/2407.17866
50. Chen, Kelly & Xiu — "Expected Returns and Large Language Models", SSRN 4416687 (2022–2024). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416687
51. Glasserman & Lin — "Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis", arXiv 2309.17322, 29/09/2023. https://arxiv.org/abs/2309.17322
52. Lopez-Lira, Tang & Zhu — "The Memorization Problem: Can We Trust LLMs' Economic Forecasts?", arXiv 2504.14765 (v2, 15/12/2025). https://arxiv.org/abs/2504.14765
53. Gao, Jiang & Yan — "Debiasing LLMs by Fine-tuning" (extrapolação; cita Chen, Green, Gulen & Zhou 2024), arXiv 2604.02921, 03/04/2026. https://arxiv.org/abs/2604.02921
54. Li, Kim, Cucuringu & Ma — "Can LLM-based Financial Investing Strategies Outperform the Market in Long Run?" (FINSABER), KDD'26, arXiv 2505.07078 (v6, 26/06/2026). https://arxiv.org/abs/2505.07078
55. Gençay — "What survives honest evaluation? Leakage-safe, search-aware assessment of LLM-driven trading strategy discovery", arXiv 2608.27734, 27/08/2026. https://arxiv.org/abs/2608.27734
56. Protos — "LLM crypto trading contest finds LLMs can't trade crypto" (Alpha Arena S1), 04/11/2025. https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/
57. Bloomberg Línea — "IA vai substituir gestores de ações? Maioria dos modelos perde dinheiro em competições", 09/05/2026. https://www.bloomberglinea.com.br/2026/05/09/ia-vai-substituir-gestores-de-acoes-maioria-dos-modelos-perde-dinheiro-em-competicoes/
58. InvestNews — "Na era do ChatGPT, fundos quant acumulam retornos (bem) acima do Ibovespa", 07/04/2023. https://investnews.com.br/financas/na-era-do-chatgpt-fundos-quant-acumulam-retornos-bem-acima-do-ibovespa/
59. Empiricus — painel de fundos quantitativos (Kadima), 29/03/2022 (atualizado em 19/02/2024). https://www.empiricus.com.br/artigos/investimentos/nos-fundos-quantitativos-construcao-de-modelos-e-controle-de-riscos-operacionais-sao-determinantes-somos-obcecados-nas-analises-do-robo-diz-rodrigo-maranhao-da-kadima/
60. InfoMoney — "'A classe de fundos quantitativos no Brasil vai acabar', diz gestor da Giant Steps", 26/06/2020. https://www.infomoney.com.br/?p=1475545
61. TraderMath / Altss — perfil da Giant Steps Capital (AUM, stack) [S]. https://www.tradermath.org/firms/giant-steps-capital
62. Computer Weekly Brasil — "A AWT é a primeira gestora brasileira que nasce da inteligência artificial", 2024. https://www.computerweekly.com/br/noticias/366614097/A-AWT-e-a-primeira-gestora-brasileira-que-nasce-da-inteligencia-artificial
63. NeoFeed — "Itaú 'aplica' na IA generativa como agente de investimentos", 2025. https://neofeed.com.br/wealth-management/itau-aplica-na-ia-generativa-como-agente-de-investimentos/

---

*Documento de pesquisa. Não constitui recomendação de investimento. Números de desempenho de terceiros são os reportados pelas fontes citadas e não foram auditados. Itens [S] devem ser revalidados antes de uso externo.*
