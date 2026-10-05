# 02 — IA generativa / agentes de LLM para gestão de ações: revisão acadêmica e de mercado (2023–2026)

| Campo | Valor |
|---|---|
| Documento | `docs/research/02_ia_gestao_academico.md` |
| Data de referência | **segunda-feira, 2026-10-05** (último pregão completo: sexta-feira, 2026-10-02) |
| Escopo | LLMs e agentes para *equity investing* e *portfolio management*; viés de *look-ahead*; avaliação de uma camada de pesquisa com LLM; papéis de agentes e *schemas* para o processo semanal de um fundo long/short LatAm *market neutral* (USD, US$ 100 mi, vol-alvo 5% a.a., banda 3%–7%) |
| Método | Leitura direta dos PDFs (arXiv/alphaXiv, NBER, SSRN, KDD/ICAIF/CIKM) e de fontes de mercado (Man Group, Hedgeweek/Bloomberg, Bridgewater); números transcritos dos artigos; cada afirmação é marcada como **[V] verificado na fonte** ou **[I] inferência nossa** |
| Status | Pesquisa concluída para subsidiar a arquitetura; não contém recomendação de investimento |
| Invariantes do repositório respeitados | Números de portfólio só vêm de código determinístico e testado (o LLM nunca calcula retornos, rankings ou contribuições); offline-first; aprovação humana vinculada a SHA-256; sem autoaprovação; dados brutos imutáveis; dados simulados sempre sinalizados |

---

## 0. Sumário executivo

1. **[V] A evidência mais robusta é para o LLM como *medidor de texto*, não como *gestor*.** Classificar manchetes (Lopez-Lira & Tang) ou extrair *embeddings* de notícias (Chen–Kelly–Xiu) gera sinais com previsibilidade fora da amostra, *após* o *cutoff* de treino do modelo. GPT-4: Sharpe anualizado de 2,97 antes de custos no *drift* do dia seguinte (out/2021–mai/2024, 4.123 ações dos EUA) [1]. Modelos cronologicamente consistentes, sem nenhum dado futuro, entregam Sharpe semelhante ao do Llama 3.1 (4,80–4,92 contra 4,90, *long-short* diário em decis, 2008–2023) [12]. O viés de *look-ahead* nessa aplicação específica é **modesto**.
2. **[V] O sinal é de curtíssimo prazo, caro de implementar e está decaindo.** O Sharpe da estratégia GPT-4 caiu de 6,54 (4T21) para 3,68 (2022), 2,33 (2023) e 1,22 (jan–mai/2024). Com custo de 20 bps por *round trip*, a estratégia diária deixa de ser lucrativa. A previsibilidade se concentra em ações pequenas e em notícias negativas [1], e a maior parte do retorno de notícia é incorporada aos preços em 1 a 2 dias [12]. **[I]** Num rebalanceamento **semanal** de ações LatAm (custos maiores, *borrow* restrito), o *drift* de notícias diárias é essencialmente inaproveitável. O valor do LLM está em: (a) texto de baixa frequência (teleconferências de resultados, *guidance*, fatos relevantes); (b) filtros de risco e eventos (*short squeeze*, governança, controlador, regulação); (c) produtividade de pesquisa.
3. **[V] Agentes LLM que decidem compra e venda de ponta a ponta não têm evidência robusta.** TradingAgents foi testado em 3 meses com 3 a 5 *mega-caps* [16]; FinMem e FinAgent, em 6 meses com 5 a 6 ativos [17][18]. Reavaliações independentes mostram colapso: no FINSABER (20 anos, mais de 100 ativos), as vantagens "desaparecem", e FinMem e FinAgent têm Sharpe de −0,97 e −0,38 em mercados de baixa [29]. No *Profit Mirage*, o Sharpe cai de 51% a 62% depois do *cutoff* do GPT-4o, e 69% a 82% das decisões não mudam quando os *inputs* são perturbados contrafactualmente, o que indica decisões guiadas por memória [14].
4. **[V] Memorização é o risco metodológico número 1.**
   - O GPT-4o "lembra" níveis do S&P 500 com erro médio absoluto (MAPE) de 0,61% antes do *cutoff*.
   - A instrução "ignore informações após 2010" não funciona: 98% de acerto após o falso *cutoff*, contra 40% de acerto real depois do *cutoff* verdadeiro [10].
   - Mascarar nomes não basta: o GPT-4 reidentifica 70% das empresas em teleconferências anonimizadas (61% mesmo sem produtos) [9].
   - **Regra prática:** só vale avaliação pós-*cutoff* ou com modelos *point-in-time*, e o teste LAP de Gao–Jiang–Yan [11] deve ser aplicado a qualquer *backtest* histórico.
5. **[V] Os LLMs têm vieses de estilo e de origem que contaminam o "alfa".**
   - Preferem tecnologia, *large caps* e postura contrária ao *momentum* (*contrarian*) [31].
   - Uma *persona* "short seller" desloca o *score* "neutro de evidência" mesmo com evidência idêntica: 69% do efeito persiste com recuperação fixa [32].
   - O ChatGPT é sistematicamente otimista com ações estrangeiras de baixa cobertura, com previsões de preço 12,5% acima das do DeepSeek para ações chinesas; o viés some quando notícias no idioma local são injetadas e se atenua em ações com listagem cruzada [33].
   - **[I]** Para LatAm: alimentar o modelo com fontes em PT/ES (CVM, CMF, BMV, SMV, SFC, CNV), residualizar o *score* do LLM contra fatores de estilo, setor, país e tamanho, e nunca dar *persona* ao analista que pontua.
6. **[V] Mineração de alfa com LLM em *loop* fechado de código e *backtest* tem evidência moderada e adoção institucional.**
   - R&D-Agent(Q), da Microsoft, foi testado fora da amostra em 2024–jun/2025 (IR de 1,3 a 2,2 no CSI 500 e no NASDAQ 100, a menos de US$ 10 por execução) [24].
   - O AlphaGPT do Man Group tem "várias dezenas" de sinais aprovados para operação ao vivo, com humano no circuito [43][44].
   - Há risco explícito de *p-hacking* industrializado: 30.000 sinais minerados resultaram em 96 "anomalias" e centenas de *papers* gerados por LLM [42].
7. **Arquitetura recomendada [I], ancorada no que tem evidência:**
   1. Dados *point-in-time* com *hash*.
   2. Motor quantitativo determinístico: fatores, risco, liquidez e *borrow*.
   3. LLMs em papéis de **extração e análise com saída estruturada e citações obrigatórias**.
   4. Debate *bull/bear* apenas para gerar argumentos, nunca o *score*.
   5. Verificador (código mais LLM) que reprova afirmação sem evidência, número fora do FactBook ou evidência datada após o `as_of`.
   6. Combinação determinística do *score* do LLM com peso inicial **0% (modo sombra)**, subindo gradualmente só depois de IC semanal comprovado.
   7. Otimizador com neutralidade de beta, fatores, setor e país.
   8. Aprovação do gestor vinculada a *hash*.
8. **Avaliação [I]:**
   - Métrica principal: *rank IC* semanal do *score* LLM contra o retorno residual da semana seguinte.
   - Testes complementares: IC incremental sobre os fatores quantitativos, decaimento por horizonte (1/5/20 dias), calibração (Brier), consistência entre amostras, ablações e LAP.
   - Poder estatístico: com IC médio de 0,03 e desvio-padrão de 0,10–0,12 por semana, são necessárias **~44–64 semanas** para t = 2. Por isso o modo sombra começa já na carteira de 2026-10-05, e o peso do LLM permanece pequeno por pelo menos 13 semanas.

---

## 1. Convenções, método e escala de evidência

**Escala de qualidade de evidência usada nas fichas (definição nossa [I]):**

| Nota | Critério |
|---|---|
| **A** | Fora da amostra **após o *cutoff*** do LLM (ou modelo *point-in-time*), universo amplo (≳ 500 ações ou ≳ 2 anos), custos discutidos e resultado corroborado por terceiros |
| **B** | Pós-*cutoff* ou metodologicamente sólido, mas com período ou universo limitado, ou sem replicação independente |
| **C** | *Backtest* dentro da janela de treino do LLM, poucos ativos, período curto, sem custos ou com *cherry-picking* de ativos |
| **D** | Sem evidência quantitativa de investimento (só arquitetura ou plataforma) **ou** trabalho retirado |

**Validade fora da amostra (OOS):** classificamos como "pós-*cutoff*", "parcial" (amostra cruza o *cutoff*) ou "dentro do treino".

**Custo:** quando o artigo informa (chamadas, US$, GPU-horas); caso contrário, estimativa qualitativa marcada **[I]**.

---

## 2. Mapa da literatura (linha do tempo)

| Data (1ª versão) | Trabalho | Tipo | Mensagem central |
|---|---|---|---|
| 2023-04 | Lopez-Lira & Tang [1] | Previsão de retornos (*prompt*) | GPT-4 prevê o *drift* pós-notícia; habilidade emerge com o tamanho do modelo; o retorno decai com a adoção |
| 2023-04 (SSRN) | Chen, Kelly & Xiu [2][3] | Previsão (*embeddings*) | *Embeddings* > *bag-of-words*; 16 mercados, 13 idiomas; *ensemble* de LLMs é o melhor |
| 2023-06 | FinGPT [25] | LLM financeiro aberto | Adaptação barata com LoRA (~US$ 300 por *fine-tune*) contra ~US$ 3 mi do BloombergGPT |
| 2023-08 | Alpha-GPT [22] | Mineração de alfa | Humano + LLM + programação genética; top-10 no WorldQuant IQC 2024 |
| 2023-09 | Glasserman & Lin [8] | *Look-ahead* | "Efeito distração" > *look-ahead*; anonimizar ajuda |
| 2023-11 | FinMem [17] | Agente *trader* | Memória em camadas; testes curtos e dentro da janela de treino |
| 2023-11 | FinanceBench [30] | *Benchmark* QA | GPT-4-Turbo com recuperação compartilhada: 81% errado ou recusado |
| 2024-02 | FinAgent [18], QuantAgent [23], FinBen [26] | Agente / alfa / *benchmark* | Multimodal com reflexão; *loop* interno e externo; LLMs fracos em previsão |
| 2024-03 | Sarkar & Vafa [9] | *Look-ahead* | Testes diretos de vazamento; *prompting* e mascaramento não resolvem |
| 2024-05 | FinRobot [19] | Plataforma | Quatro camadas e *Smart Scheduler*; sem avaliação de retorno |
| 2024-07 | Kim, Muhn & Nikolaev [6] | Análise de demonstrações financeiras | **Retirado em 2025-02-20** por inconsistências nos dados |
| 2024-12 | TradingAgents [16], INVESTORBENCH [27] | Multiagente / *benchmark* | Debate *bull/bear*; 13 LLMs com dados até 2021 |
| 2025-01 | Novy-Marx & Velikov [42] | Crítica | LLM industrializa HARKing |
| 2025-02 | MarketSenseAI 2.0 [20], ChronoBERT/GPT [12] | Agente / PIT | Seleção S&P 100/500; modelos sem *look-ahead* |
| 2025-04 | Memorization Problem [10], LLM-BLM [38] | *Look-ahead* / otimizador | Recordação exata pré-*cutoff*; *views* do LLM no Black-Litterman |
| 2025-05 | FINSABER [29], R&D-Agent(Q) [24] | Crítica / mineração de alfa | Vantagens somem em 20 anos; *loop* fator-modelo |
| 2025-07 | Man Group AlphaGPT [43] | Prática | Dezenas de sinais em produção, com supervisão humana |
| 2025-07/08 | Lee et al. [31], AlphaAgents/BlackRock [21] | Vieses / multiagente | Vieses de setor, tamanho e *contrarian*; debate até consenso |
| 2025-10 | StockBench [28], Profit Mirage [14] | *Benchmark* / crítica | Livre de contaminação; vazamento de informação em agentes |
| 2025-12 | LAP test [11] | *Look-ahead* | Diagnóstico barato via *logprobs* |
| 2026-01 | Chen & Pu [36] | *Nowcasting* agêntico ao vivo | Top-20 do Russell 1000: α diário de 18,4 bps, Sharpe 2,43, sem lado vendido útil |
| 2026-02 | Kong et al. [15] | *Checklist* | "Cinco pecados"; só 26,8% dos *papers* tratam *look-ahead* |
| 2026-07 | Kelly et al. PIT LMs [13] | PIT em escala | Modelo de 4B parâmetros e 1T *tokens* fecha a maior parte do *gap* |
| 2026-09 | Asaad et al. [32] | Viés de *persona* | O papel atribuído altera a leitura de evidência idêntica |

---

## 3. Fichas por estudo

> Formato: **Afirmação · Método · Qualidade da evidência · Validade OOS · Custo · O que reaproveitamos**.

### 3.1 Previsão de retornos com LLM

#### 3.1.1 Lopez-Lira & Tang — "Can ChatGPT Forecast Stock Price Movements?" [1]

- **Afirmação [V]:** sem treino financeiro, o GPT-4 identifica a reação inicial às manchetes (taxa de acerto diária do portfólio de 93,3% *overnight* e 88,8% *intraday*, não negociável) e prevê o *drift* seguinte.
- **Método [V]:**
  - *Prompt* que classifica cada manchete como boa, ruim ou neutra para a ação.
  - 159.137 observações firma–manchete–dia, 4.123 ações dos EUA, out/2021 a mai/2024, cruzadas com a RavenPack.
  - Carteira *long-short* rebalanceada diariamente (compra positivas, vende negativas).
  - Doze LLMs comparados.
- **Números-chave [V]:**
  - *Drift overnight*: 0,34% ao dia, Sharpe 2,97 antes de custos; perna comprada com Sharpe 0,78 e perna vendida com Sharpe 2,01.
  - Alfa FF5 diário de 0,33% (t = 4,62).
  - Sharpe do *drift* por modelo: GPT-3.5 1,66; DistilBART 1,26; Llama2-70B 0,97; FinBERT −0,33.
  - Previsibilidade muito maior em ações pequenas (interação de 0,404, t = 4,75).
  - Custos: com 5 bps, ainda há retorno acumulado de cerca de 300%; com 20 bps, a estratégia não é lucrativa. *Value-weighted* já fica negativo com 5 bps (Sharpe −0,40).
  - Decaimento do Sharpe: 6,54 (4T21) → 3,68 (2022) → 2,33 (2023) → 1,22 (jan–mai/2024).
- **Qualidade:** **A−**. Pós-*cutoff* por construção, amostra ampla, custos e decaimento analisados, *baseline* replicado por Gao–Jiang–Yan [11] (coeficiente de 0,21% ao dia, t = 12,18).
- **OOS:** pós-*cutoff* (treino até set/2021), **mas** a janela pós-*cutoff* é curta.
- **Custo [I]:** baixo por manchete, uma chamada curta. O custo relevante é de execução, com *turnover* de cerca de 190% ao dia.
- **Reaproveitamos:**
  1. Tarefa simples, estruturada e com saída categórica.
  2. Agregação por firma e dia.
  3. Verificar decaimento por ano.
  4. Separar perna comprada e vendida.
  5. Usar **apenas** como *feature* lenta ou filtro de risco em horizonte semanal **[I]**.

#### 3.1.2 Chen, Kelly & Xiu — "Expected Returns and Large Language Models" [2][3][4][5]

- **Afirmação [V]:** *embeddings* contextuais de LLMs (BERT, RoBERTa, OPT, LLaMA, ChatGPT) aplicados a notícias da Thomson Reuters/Refinitiv superam *bag-of-words* (LM, SESTM) e Word2Vec na previsão de retornos.
  - A análise cobre **16 mercados acionários e 13 idiomas** ("*polyglot portfolios*").
  - A previsibilidade dura vários dias em ações pequenas e some rápido nas grandes.
  - Notícias ligadas a analistas são as mais lucrativas.
  - Resumos gerados por IA dão o melhor desempenho (versão revisada em fev/2026).
- **Método [V]:** *embedding* por artigo, regressão *ridge* do retorno de 1 dia contra o *embedding* com janela móvel, ordenação em decis e carteira *long-short*. Há também previsões mensais ("conteúdo rápido e lento"). Um *ensemble* de modelos supera o melhor modelo individual.
- **Números [V, fonte secundária [5]]:** Sharpe diário *equal-weighted* de ~4,62 (ChatGPT), ~4,16 (LLaMA2), 3,43 (SESTM), 2,29 (LMMD); *ensemble* de 5,11. **Atenção:** números transcritos de material de curso, não do PDF original, que não conseguimos ler.
- **Crítica do debatedor [V] [4]:**
  - Rótulos de 3 dias são ruidosos.
  - É preciso comparar com o *news momentum* de Jiang–Li–Wang: Sharpe líquido de ~1,5 com custos de 10 a 20 bps.
  - A previsibilidade pode estar concentrada nos primeiros minutos do pregão (*front-loaded*).
- **Qualidade:** **A−**. Universo amplo e internacional; o *look-ahead* é modesto segundo a corroboração independente com ChronoGPT [12] e com modelos PIT [13].
- **OOS:** parcial. Parte da amostra está dentro do treino, mas os autores afirmam que o resultado não é dirigido por *look-ahead*.
- **Custo [I]:** *embeddings* são baratos e determinísticos (temperatura irrelevante), o que os torna ideais para reprodutibilidade.
- **Reaproveitamos:**
  1. *Embeddings* com regressão linear regularizada são o caminho mais robusto para transformar texto em sinal.
  2. *Ensemble* de modelos.
  3. Suporte multilíngue (relevante para PT/ES).
  4. Previsão também em frequência mensal.

#### 3.1.3 Kirtac & Germano — "Sentiment trading with large language models" (Finance Research Letters, 2024) [37]

- **[V]** 965.375 notícias dos EUA de 2010 a 2023. O OPT com *fine-tune* atinge 74,4% de acurácia; a carteira *long-short* com custo de 10 bps tem Sharpe de 3,05 e ganho de 355% entre ago/2021 e jul/2023.
- **Qualidade:** **B−**. Um único conjunto de dados; período de teste parcialmente posterior ao treino do OPT.
- **Reaproveitamos:** *fine-tune* de modelo aberto pequeno (com rótulos de mercado) é competitivo com LLMs grandes por *prompt*, o que importa para custo e soberania de dados **[I]**.

#### 3.1.4 Kim, Muhn & Nikolaev — "Financial Statement Analysis with LLMs" [6][7]

- **Afirmação original [V]:**
  - GPT-4-Turbo com *chain-of-thought* sobre demonstrações **anonimizadas** prevê a direção do lucro com 60,35% de acurácia (F1 de 63,45%), contra 52,71% dos analistas e 60,45% de uma rede neural artificial (ANN).
  - Sem *chain-of-thought*, a acurácia é de 52,33%.
  - Teste fora do treino (dados de 2022 para prever 2023): 58,96%.
  - Recuperação da identidade da firma a partir do texto anonimizado: 0,07%.
- **Status [V]: RETIRADO.**
  - O arXiv v3 de 2025-02-20 traz a nota: "*A co-author identified inconsistencies in the data and analyses... temporarily withdrawn*".
  - A página de Muhn (fev/2025) acrescenta que os autores decidiram revisar "*certain other LLM-based working papers*".
- **Qualidade:** **D** (retirado). Não usar os números como evidência.
- **Reaproveitamos:** só a **ideia de processo**: pedir ao LLM análise de tendências e índices a partir de demonstrações padronizadas e anonimizadas, com os índices **calculados por código** (nosso FactBook) e não pelo LLM. É também um alerta concreto sobre replicabilidade **[I]**.

#### 3.1.5 Chen & Pu — "Autonomous Market Intelligence: Agentic AI Nowcasting Predicts Stock Returns" [36]

- **Afirmação [V]:**
  - Um LLM com busca na *web* avalia diariamente cada ação do Russell 1000 (abr/2025–jan/2026, ~156 mil previsões), com *prompt* fixo e saída em lista Python lida por *regex*.
  - Top-20 *value-weighted*: alfa diário FF5 + MOM de **18,4 bps** (t = 2,46), Sharpe de **2,43** e ~50% de retorno acumulado contra ~26% do índice.
  - **As ações piores do ranking não têm alfa** (assimetria).
  - Custos de cerca de 1,6 bps por operação, menos de 10% do alfa bruto.
- **Método [V]:** consulta noturna após o fechamento de t−1 e retorno medido de abertura a abertura, ou seja, **sem *look-ahead* por construção** (*nowcasting* ao vivo).
- **Qualidade:** **B**. OOS genuíno e universo líquido, mas um só modelo (não nomeado), 9 meses, preliminar e não reprodutível.
- **Reaproveitamos:**
  1. **Registrar previsões no momento da decisão com carimbo de tempo é o único teste realmente limpo**; nosso modo sombra replica isso.
  2. Assimetria: o LLM serviu para comprados, não para vendidos. **[I]** No nosso livro vendido, o LLM entra como **filtro e veto** (riscos, catalisadores), não como gerador primário de *shorts*.
  3. Divergência com Lopez-Lira & Tang, onde o lado vendido era o mais forte: **[I]** a assimetria é dependente de horizonte e universo e deve ser medida no nosso próprio modo sombra.

#### 3.1.6 Mercado brasileiro — Jesus, Medeiros, Godeiro & Proque (Computational Economics, 2025) [40]

- **[V]** Para o Ibovespa, um índice de sentimento baseado em ChatGPT **não melhora** a previsão fora da amostra. Já um índice de sentimento de notícias com **dicionário variável no tempo** melhora, e o indicador técnico *Accumulation–Distribution* foi o melhor modelo.
- **Qualidade:** **B** (resultado negativo publicado). A previsão é de **índice** (série temporal), não de *cross-section*.
- **Reaproveitamos:** **[I]** não esperar ganho em *market timing* agregado; nosso fundo é neutro em beta, então a aplicação relevante é o *cross-section* intrapaís, ainda não testada para LatAm na literatura revisada. Fica como **lacuna** que o nosso próprio modo sombra vai medir.

### 3.2 Viés de *look-ahead*, memorização e "distração"

#### 3.2.1 Glasserman & Lin — "Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis" [8]

- **[V]** O artigo separa *look-ahead* (o modelo sabe o que aconteceu depois) de **efeito distração** (o conhecimento geral sobre a empresa interfere na leitura da manchete).
  - Anonimizar (substituir nome e produtos por "Blahblahblah" com *fuzzy match* InDel acima de 80) **melhorou** o resultado dentro da amostra: +5,9 bps ao dia na base *scraped* (p = 0,066) e +3,1 bps ao dia na base Thomson Reuters (p = 0,017; Tabela 3).
  - Conclusão: o efeito distração domina o *look-ahead* com GPT-3.5.
  - Fora da amostra, a diferença é limítrofe (p = 0,064 na base Thomson Reuters), mas o beta de mercado cai: a estratégia anonimizada tem beta ≈ 0 (0,02–0,09).
  - Os efeitos são mais fortes em *large caps*, sobre as quais o modelo "sabe mais".
- **Qualidade:** **B** (metodológico, GPT-3.5, uma tarefa).
- **Reaproveitamos:** anonimização como **ablação obrigatória** e, para tarefas de sentimento, como modo de produção. **[I]** Em LatAm, *large caps* e ADRs são os nomes em que o modelo mais "sabe", portanto mais sujeitos à distração.

#### 3.2.2 Sarkar & Vafa — "Lookahead Bias in Pretrained Language Models" [9]

- **[V]**
  - Instruído a prever riscos de 2020 a partir de teleconferências de set–nov/2019, o Llama-2 70B escreve "COVID-19" em 6,8% das gerações; sem a instrução de "não usar o futuro", em 12,2%.
  - Em eleições disputadas por margens de 0,5% a 2%, o modelo acerta o vencedor 70% a 80% das vezes.
  - O GPT-4 reidentifica **70%** das firmas em trechos com o nome mascarado (61% mascarando também os produtos) e infere o **ano** da teleconferência com correlação de 0,79.
  - Remédio proposto: modelos pré-treinados só com texto anterior ao período de análise e **sem viés de sobrevivência** no *corpus*.
- **Qualidade:** **A** (evidência direta e conservadora).
- **Reaproveitamos:** *prompting* ("não use informação futura") **não** é controle. Mascaramento é mitigação parcial, não garantia.

#### 3.2.3 Lopez-Lira, Tang & Zhu — "The Memorization Problem" [10]

- **[V]**
  - Antes do *cutoff* (out/2023), o GPT-4o recorda o S&P 500 diário com MAPE de 0,61% e direção mensal com 79,5% a 85,2% de acerto. Após o *cutoff*, o MAPE vai a 13% a 20% e a direção cai a 44% a 49%, nível de acaso.
  - Recorda preços de ações individuais, mais precisamente as proeminentes (META: MAPE de 0,37% sem contexto).
  - "Ignore dados após 2010": 98,0% de acerto pós-falso-*cutoff*, contra 40% no pós-*cutoff* real.
  - A memorização se estende a ***embeddings***: valores do S&P podem ser invertidos a partir deles.
  - Prova formal de **não identificação**: o desempenho pré-*cutoff* não separa habilidade de memória, e pequenas amostras pós-*cutoff* usadas como "robustez" não têm poder.
- **Qualidade:** **A**.
- **Reaproveitamos:**
  1. Avaliação **principal** só pós-*cutoff*.
  2. Tarefas de **extração invariante ao futuro** (por exemplo, "qual o *guidance* de capex informado neste documento?") são relativamente seguras; tarefas de **julgamento** não são.
  3. **[I]** Isso orienta nossos papéis: extratores podem rodar sobre o histórico; analistas que julgam só são avaliados prospectivamente.

#### 3.2.4 Gao, Jiang & Yan — "Detecting Lookahead Bias in LLM Forecasts" (LAP) [11]

- **[V]**
  - Consulta só com nome, *ticker* e data: "subiu ou caiu? senão, *unknown*".
  - *Lookahead Propensity*: LAP = P(*up*) + P(*down*), lida nos *logprobs* do primeiro *token*.
  - No Llama-3.3-70B, o LAP médio no período de treino é de 0,414 e **desaba para ~7×10⁻⁶** após o *cutoff* (dez/2023).
  - Em regressão de retorno contra sinal LLM × LAP, a interação é de 0,162 (t = 3,64): com LAP = 1, o efeito marginal do sinal **dobra** (0,303% contra 0,141%).
  - Fora da amostra, a interação deixa de ser significativa (t = 1,06), mas o sinal "puro" sobrevive (0,436, t = 6,47).
  - Na previsão de capex a partir de teleconferências, a interação é de 0,512 (t = 2,01).
  - A "confiança interna" (probabilidade do rótulo) também amplifica o sinal: interação de 0,602, t = 2,79.
- **Qualidade:** **B+** (diagnóstico barato, replicável com modelo aberto).
- **Custo:** uma chamada curta por par firma–data, com *logprobs*.
- **Reaproveitamos:** **teste obrigatório** antes de aceitar qualquer *backtest* histórico do nosso pipeline LLM, mais o uso da probabilidade do rótulo como medida de confiança.

#### 3.2.5 He, Lv, Manela & Wu — ChronoBERT / ChronoGPT [12] e Kelly, Malamud, Schwab & Xu — "Scaling Point-in-Time Language Models" [13]

- **[V] [12]**
  - Modelos treinados ano a ano (1999–2024) só com texto disponível na data.
  - Carteira *long-short* em decis, diária, com notícias de 2008 a jul/2023: Sharpe de 4,80 (ChronoBERT *realtime*), 4,92 (ChronoGPT *realtime*) e 4,90 (Llama 3.1 8B); diferença não significativa (p = 0,315 e 0,547).
  - O retorno de notícia decai fortemente nos dias 1–2.
  - Conclusão: *look-ahead* modesto nessa tarefa; impacto "específico de modelo e aplicação".
- **[V] [13]**
  - Modelo PIT de 4B parâmetros e 1T *tokens* (FineWeb), com *checkpoints* **mensais** de 2013 a 2024, aproxima-se de Gemma-3-4B e LLaMA-7B (HellaSwag de 72,2% contra 77% e 76%).
  - Carteira de *embeddings* de notícias (Dow Jones, 2014–mai/2020): Sharpe OOS de 1,02 (PIT-4B) e 1,53 (PIT-4B-FT), contra 0,82 e 1,18 nas versões *full-sample*, que violam a temporalidade.
  - Custo de pré-treino de ~28.000 GPU-horas; código e modelos são públicos.
- **Qualidade:** **A−** [12] e **B+** [13].
- **Reaproveitamos:**
  1. Para *backtests* históricos de *embeddings*, usar modelos PIT (ChronoGPT ou PIT-4B, ambos no Hugging Face) como **controle**.
  2. A diferença de Sharpe entre o modelo de fronteira e o modelo PIT dá uma estimativa do viés.
  3. **[I]** Modelos PIT são em inglês; para PT/ES é preciso validar a cobertura (lacuna).

#### 3.2.6 Li et al. — "Profit Mirage" (FinLake-Bench / FactFin) [14]

- **[V]**
  - Agentes publicados (FinMem, FinAgent, QuantAgent, FinCon, TradingAgents) com GPT-4o: queda de Sharpe de **51,5% a 62,2%** e de retorno total de **50,2% a 71,9%** entre o 2T–3T/2021 (dentro do treino) e o 3T–4T/2024 (após), em mercados com retorno semelhante (+13,8% contra +13,4%).
  - Consistência de predição sob perturbação contrafactual de 0,69 a 0,82.
  - GPT-4o, Claude 3.7 e Grok-3 acertam de 85% a 93% de perguntas de memória factual de mercado (jan/2022–jun/2023).
- **Qualidade:** **B** (crítico, bem desenhado; o FactFin proposto pelos próprios autores tem a força de evidência usual de um artigo que avalia o próprio método).
- **Reaproveitamos:**
  1. **Teste contrafactual:** perturbar *inputs* e exigir que o *score* mude de forma coerente. Pouca mudança significa que o LLM está "recitando".
  2. Usar o LLM como **gerador de estratégia ou código** e não como decisor direto reduz o vazamento.

#### 3.2.7 Kong et al. — "Evaluating LLMs in Finance Requires Explicit Bias Consideration" [15]

- **[V]**
  - Revisão de 164 *papers* (2023–2025): só **26,8%** mencionam *look-ahead*, **1,2%** viés de sobrevivência, 11,6% viés narrativo, 12,2% viés de objetivo e 28,0% custos.
  - Propõem o *Structural Validity Framework*, com cinco *checks* de passa/falha:
    1. Sanitização temporal: pesos, RAG e ferramentas *point-in-time*; *snapshots* com *as-of*; proibido usar busca ao vivo em *backtest*.
    2. Universo dinâmico com deslistadas.
    3. Robustez da justificativa, com trilha de citações verificável.
    4. Calibração epistêmica, com permissão de abstenção ("não sei").
    5. Custos, latência e custo de inferência.
- **Reaproveitamos:** adotar o *checklist* **literalmente** como *gate* de aprovação de qualquer componente LLM.

### 3.3 Agentes de pesquisa e de *trading*

#### 3.3.1 TradingAgents (Xiao, Sun, Luo & Wang; Tauric/UCLA/MIT) [16]

- **Afirmação [V]:** organização de uma *trading firm* em sete papéis:
  - Analistas: fundamentos, sentimento, notícias e técnico.
  - Pesquisadores *bull* e *bear*, em debate de *n* rodadas com um facilitador que escolhe a perspectiva vencedora.
  - Um *trader*.
  - Uma equipe de risco com três perfis (agressivo, neutro, conservador), também em debate.
  - Um *fund manager* que aprova.
  - Comunicação por **documentos estruturados** (para evitar o "efeito telefone sem fio"); diálogo em linguagem natural só nos debates.
  - Modelos "*quick-thinking*" (gpt-4o-mini, gpt-4o) para recuperação de dados e "*deep-thinking*" (o1-preview) para decisões; padrão ReAct.
- **Evidência [V]:** jan–mar/2024, AAPL, NVDA, MSFT, META e GOOGL (com gráficos de AAPL, GOOGL e AMZN). Os próprios autores notam que o Sharpe observado "excede o intervalo empírico esperado" e que **11 chamadas de LLM e mais de 20 de ferramentas por previsão** limitaram o *backtest* a 3 meses.
- **Qualidade:** **C**. Período curtíssimo, *mega-caps* vencedoras, dentro da janela de conhecimento do o1/GPT-4o (*cutoff* out/2023 para o GPT-4o). No Profit Mirage [14], o Sharpe cai 55,7% após o *cutoff*.
- **Custo [V/I]:** ~11 chamadas de LLM (várias com modelo de raciocínio) por ativo e por decisão. Para 200 nomes por semana, seriam ~2.200 chamadas, aceitável em frequência semanal **[I]**.
- **Reaproveitamos:**
  1. **Estrutura organizacional** (analistas → pesquisa → risco → gestor).
  2. **Estado global estruturado** em vez de *chat* livre.
  3. Roteamento por custo (modelo rápido contra modelo de raciocínio).
  4. **Não** reaproveitamos o *trader* LLM nem o debate como fonte do *score* (ver 3.6.2).

#### 3.3.2 FinMem (Yu et al., Stevens) [17]

- **[V]**
  - Memória em três camadas com decaimentos diferentes: rasa para notícias (~30 dias), intermediária para 10-Q (~90 dias) e profunda para 10-K (~365 dias); α = 0,9 / 0,967 / 0,988.
  - *Ranking* por recência, relevância e importância, com promoção de memórias "decisivas".
  - *Profiling* de risco autoadaptativo.
  - Testes em TSLA e afins, 2021–2023, com GPT-3.5/4.
- **Qualidade:** **C**. No FINSABER, sobre os mesmos ativos e 20 anos, o Sharpe do FinMem fica abaixo do *buy-and-hold* em 3 de 4 ativos, e em mercados de baixa o Sharpe médio é de −0,97 [29].
- **Reaproveitamos:** a **ideia de memória com decaimento por tipo de documento** para o nosso *store* de evidências (fato relevante e balanço com meia-vida longa, notícia com meia-vida curta) **[I]**.

#### 3.3.3 FinAgent (Zhang et al., NTU; KDD'24) [18]

- **[V]** Multimodal (texto, preço e *K-line* via GPT-4V), com reflexão em dois níveis (preço e decisões passadas), recuperação "diversificada" (consultas separadas por horizonte), ferramentas (MACD, KDJ+RSI) e "orientação de especialistas". Seis conjuntos de dados (ações e cripto); 92,27% de retorno em TSLA, com ablações por módulo.
- **Qualidade:** **C** (seis ativos, dentro do treino). No Profit Mirage, é dos agentes mais resilientes, por usar ferramentas [14].
- **Reaproveitamos:** **separar o campo "consulta para recuperação" do campo "resumo para decisão"** na saída do extrator, e as ablações por módulo como padrão de avaliação.

#### 3.3.4 FinRobot (Yang et al., AI4Finance) [19]

- **[V]** Plataforma aberta em quatro camadas: agentes, algoritmos de LLM financeiros, LLMOps/DataOps e modelos de base multifonte. Inclui um *Smart Scheduler* que escolhe o modelo por "*task score*" num *golden dataset*, um *Financial Chain-of-Thought* e papéis de Diretor, Assistente, Analista LLM e Analistas Financeiros.
- **Qualidade:** **D** (sem avaliação de retorno).
- **Reaproveitamos:** a ideia de um ***golden dataset* interno para escolher e trocar o modelo** de cada papel (o *Smart Scheduler*), coerente com a avaliação da seção 4.5 **[I]**.

#### 3.3.5 MarketSenseAI 2.0 (Fatouros et al.) [20]

- **[V]** Cinco agentes: notícias (resumo progressivo), fundamentos (*Chain-of-Agents* sobre 10-Q/10-K e teleconferências, mais 5 trimestres de números), dinâmica de preço, macro (RAG com HyDE sobre relatórios de bancos centrais e de investimento) e sinal (*chain-of-thought* para comprar, manter ou vender). GPT-4o; *backtest* em VectorBTPro com 10 bps por operação.
  - S&P 100 (2023–2024), carteira ponderada por capitalização: 125,9% contra 73,5% do índice.
  - S&P 500 (2024), *equal-weight*: 25,8% contra 12,8%.
  - **Análise de fatores:** beta de 0,92–0,96 nas carteiras *equal-weight* (1,24–1,27 nas ponderadas por capitalização), SMB negativo, HML positivo, MOM de 0,18.
  - Alfa de 8,0% (S&P 100, *equal-weight*) e de 18,9% (S&P 500, *equal-weight*).
- **Qualidade:** **C+**. Só comprada, com beta alto; 2023 está **dentro** da janela de conhecimento do GPT-4o; sem replicação independente.
- **Reaproveitamos:**
  1. RAG macro com HyDE e recuperação de 5 a 7 *chunks* (*recall* de 0,79–0,91 e fidelidade de 0,94–0,98 no Ragas).
  2. Processamento hierárquico de documentos longos.
  3. **[I] Lição central:** um "alfa" de LLM só comprado é em grande parte beta e estilo; **sempre decompor em fatores** antes de acreditar.

#### 3.3.6 AlphaAgents (Zhao et al., BlackRock) [21]

- **[V]** Três agentes: fundamentos (RAG sobre 10-K/10-Q), sentimento (resumo com reflexão sobre notícias da Bloomberg) e valuation (ferramenta **calculadora** de retorno e volatilidade para evitar alucinação numérica).
  - Implementado em AutoGen, com debate *round-robin* até consenso: cada agente fala pelo menos duas vezes e nenhum decide pelo grupo.
  - Perfis de risco (avesso e neutro) definidos no *prompt*; perfis "adjacentes" saem indistinguíveis.
  - Avaliação de RAG com Arize Phoenix (fidelidade e relevância) e revisão humana dos debates.
  - 15 ações de tecnologia, 4 meses (fev–mai/2024), *equal-weight*. Os autores sugerem usar as saídas como *views* para Black-Litterman ou média-variância.
- **Qualidade:** **C** (amostra minúscula).
- **Reaproveitamos:**
  1. **Ferramentas determinísticas para qualquer número**, alinhado ao nosso FactBook.
  2. Monitoramento por *traces* (Phoenix ou similar).
  3. *Log* completo dos debates para auditoria e *override* humano.
  4. O LLM como **fornecedor de *views*** para um otimizador, não como otimizador.

### 3.4 Mineração de alfa com LLM

#### 3.4.1 Alpha-GPT (Wang et al., HKUST/IDEA) [22]

- **[V]** Fluxo em três etapas: ideação (o *Trading Idea Polisher* com RAG sobre literatura e campos de dados), implementação (o *Quant Developer* gera expressões "semente", depois aprimoradas por programação genética) e revisão (*Analyst* com *backtest*, IC e Sharpe). Usa Llama3-70B.
  - O IC da semente sobe de 0,58% para 1,23% após 10 rodadas de busca e para 2,23% com 1 rodada de interação mais busca.
  - Competição de alta frequência (JoinQuant): entre os top 5%–10%.
  - WorldQuant IQC 2024 (avaliação **em tempo real** na competição): top-10 global entre mais de 41 mil equipes, maior *score* dentro da amostra (65.505) e *score* fora da amostra de 43.319.
- **Qualidade:** **B−**. OOS da competição é genuíno, mas a métrica é da plataforma; parte da avaliação de "qualidade" usa o GPT-4 como juiz.
- **Reaproveitamos:** **humano no circuito**, RAG hierárquico sobre dicionário de dados, deduplicação e descorrelação de alfas, e controle de sobreajuste com IC fora da amostra que "estabiliza após ~15 iterações".

#### 3.4.2 QuantAgent (Wang, Yuan, Ni & Guo) [23]

- **[V]** *Loop* interno (escritor e juiz LLM com base de conhecimento) e *loop* externo (*backtest* real atualiza a base). Prova de eficiência sob hipóteses de RL. Experimento em 500 ações A-share em 2023 com gpt-4-0125-preview; métricas de IC, retorno e Sharpe com "tendência" de melhora.
- **Qualidade:** **C** (um ano, ganhos visualmente modestos).
- **Reaproveitamos:** a base de conhecimento de sinais com metadados (ideia, código, métricas, revisão) como **registro de pesquisa auditável** **[I]**.

#### 3.4.3 R&D-Agent(Q) (Li et al., Microsoft Research Asia; NeurIPS 2025) [24]

- **[V]** Cinco unidades: especificação, síntese de hipóteses (floresta de conhecimento), implementação (agente de código Co-STEER), validação (*backtest* em Qlib) e análise (*bandit* de dois braços escolhendo entre fator e modelo).
  - **O LLM vê só o *schema*, nunca dados brutos nem datas.**
  - CSI 300 (teste 2017–ago/2020): IC de 0,0532, ARR de 14,2% e IR de 1,74 (o3-mini), contra Alpha158 com IC de 0,0341 e IR de 0,85, com 70% menos fatores.
  - **OOS 2024–jun/2025:** CSI 500 com IR de 2,17 e MDD de −6,6%; NASDAQ 100 com IR de 1,77 (o4-mini), IC de 0,016–0,029.
  - Custo **abaixo de US$ 10** por execução; *bandit* superior a escolha aleatória ou por LLM.
  - *Health checks* de fatores (sem vazamento, não triviais).
- **Qualidade:** **B**. OOS recente e código aberto, mas avaliação dos próprios autores, *long-short* diário em mercado A-share com muitas pernas.
- **Reaproveitamos:**
  1. Isolar o LLM dos dados (só *schema*), o que reduz o *look-ahead* via contexto.
  2. *Health checks* automáticos.
  3. *Bandit* para alocar orçamento de pesquisa.
  4. **[I]** Uso em P&D *off-line* (não no ciclo semanal), sempre com *holdout* temporal e correção de múltiplos testes.

#### 3.4.4 Prática de mercado: Man Group (AlphaGPT), Bridgewater (AIA Labs), Balyasny [43][44][45][46]

- **Man Group [V]:**
  - O AlphaGPT do Man Numeric gera hipóteses, escreve código Python de produção e faz *backtest*: uma "equipe digital de três pessoas".
  - "Várias dezenas de sinais" foram aprovados para operação ao vivo (Bloomberg via Hedgeweek, 2025-07-11).
  - "*I wouldn't call it autopilot*" (Z. Fang).
  - Cada sinal passa por comitê de investimento e por tecnologia **com os mesmos limiares** da pesquisa humana.
  - Riscos declarados: *data mining* acelerado ("resultados de sorte") e alucinação de implementação (a ideia é uma, o código é outro).
- **Bridgewater [V, imprensa]:** fundo de ~US$ 2 bi gerido com ML (AIA Labs), iniciado em 2024. O CEO afirmou em 2025 que gera "alfa único, não correlacionado com o que nossos humanos fazem". Números de retorno anual circulam em fontes secundárias; **não verificados** em fonte primária.
- **Balyasny [fonte secundária, não verificada; página da OpenAI retornou 403]:** agentes de "*deep research*" e de análise de discursos de bancos centrais (de 2 dias para ~30 minutos) e um equipe de *Applied AI* que avalia modelos de fronteira.
- **Reaproveitamos:** o padrão institucional convergente é **IA como acelerador de pesquisa sob governança idêntica à humana**, com *checkpoints*, comitê e mesmos limiares, e não como *autopilot*.

#### 3.4.5 Novy-Marx & Velikov — "AI-Powered (Finance) Scholarship" (NBER w33363, jan/2025) [42]

- **[V]** Mineração de 30.000 sinais contábeis, dos quais 96 passaram no protocolo *Assaying Anomalies*. Um LLM escreveu três versões de *paper* para cada um, com nomes criativos, "teorias" diferentes e citações por vezes **inventadas**: HARKing industrializado.
- **Reaproveitamos:** toda ideia vinda de LLM entra num **registro de testes** que conta tentativas (para *deflated Sharpe* e correção de múltiplos testes) e exige racional econômico **pré-registrado** antes do *backtest* **[I]**.

### 3.5 LLMs financeiros e *benchmarks*

| Trabalho | O que mede | Resultado-chave [V] | Qualidade | Uso para nós |
|---|---|---|---|---|
| **FinGPT** [25] | LLM financeiro aberto (*data-centric*, LoRA, RLSP com rótulos de preço) | ~US$ 300 por *fine-tune*, contra ~US$ 3 mi (1,3 mi GPU-h) do BloombergGPT; Llama-3.1-8B com LoRA (r = 8, 8,3 mi parâmetros) atinge F1 macro de 77,3 (80,9 com RLSP), contra 69,9 do FinBERT e 61,7 do ChatGPT *zero-shot* em 620 mil manchetes | C (benchmark próprio) | Caminho de baixo custo para um **classificador PT/ES próprio** com rótulos de mercado |
| **FinBen** [26] | 36 *datasets*, 24 tarefas, 7 áreas | LLMs são bons em extração e análise textual e fracos em previsão: acurácia de movimento de ~0,50–0,57, MCC ≈ 0 | B | Não usar LLM para "prever subida ou queda" diretamente; usar para extrair |
| **INVESTORBENCH** [27] | 13 LLMs em ações, cripto e ETFs (base FinMem) | Modelos proprietários e maiores (≥ 67B) são melhores; dados de ações de 2020–2021, **dentro do treino** | C | Pouco útil (contaminado) |
| **StockBench** [28] | 20 ações do DJIA, mar–jun/2025 (pós-*cutoff*), US$ 100 mil, decisões diárias, 14 modelos | Retornos de −2,8% a +2,5% contra +0,4% do *buy-and-hold* em 82 pregões; 8 de 13 modelos acima em retorno e 11 de 13 acima no *ranking* composto, todos com *drawdown* menor; **todos** perderam do passivo na janela de queda; sem custos nem liquidez. O resumo diz que "a maioria não supera" o *buy-and-hold*, o que conflita com a tabela v2. Inconsistência a notar | B− | Usar *benchmarks* **vivos e pós-*cutoff***; resultados ainda pouco informativos |
| **FINSABER** [29] | Reavaliação de 20 anos, mais de 100 símbolos, viés de sobrevivência e *data-snooping* | Vantagens dos LLMs "deterioram significativamente"; conservadores em alta e agressivos em baixa (Sharpe: FinAgent 0,12 em alta e −0,38 em baixa; FinMem −0,19 e −0,97); ARIMA e regras simples competitivos | A− | Exigir avaliação longa, com regimes e universo dinâmico |
| **FinanceBench** [30] | 10.231 perguntas sobre *filings*; 150 avaliadas por especialistas | GPT-4-Turbo com *vector store* compartilhado: 19% certo, 13% errado e 68% recusou (81% errado ou recusado); *long context*: 79% certo; *oracle*: 85%; contexto **antes** da pergunta: 78% contra 25% | A (QA) | Recuperação por emissor (*store* por documento), contexto antes da pergunta, verificação obrigatória |

### 3.6 Vieses comportamentais dos LLMs relevantes para gestão

#### 3.6.1 Lee et al. — "Your AI, Not Your View" (ICAIF'25) [31]

- **[V]** Seis LLMs (GPT-4.1, Gemini-2.5-flash, DeepSeek-V3, Qwen3-235B, Llama4-Scout, Mistral-Small) mostram:
  - Viés de **setor**, com tecnologia preferida na maioria.
  - Viés de **tamanho**, com o *score* caindo do quartil maior para o menor; um modelo fica negativo nos quartis 3 e 4.
  - Preferência **contrária ao *momentum***, significativa em todos os modelos.
  - Viés de **confirmação**: com evidência mista, a taxa de reversão cai fortemente mesmo com mais contra-evidência.
- **Reaproveitamos:** **residualizar** o *score* LLM contra setor, tamanho, *momentum*, beta e país antes de qualquer uso. Para LatAm (muitas *mid/small caps* pouco cobertas), o viés de tamanho é especialmente perigoso **[I]**.

#### 3.6.2 Asaad et al. — "The Analyst in the Prompt" [32]

- **[V]** 3.575 *filings*, 12 LLMs, saída JSON com *EvidenceScore* (neutro) e *PersonalizedScore*.
  - Com recuperação **idêntica**, 69% do efeito de *persona* sobre o *score* "neutro" persiste: é deriva **interpretativa**, não de recuperação.
  - Na *persona* *ShortSeller*, a mediana retida é de 89%.
  - Colocar a mentalidade como "perfil do usuário" em vez de "papel do assistente" reduz o efeito; separar os dois *scores* também ajuda, mas nenhum dos dois o elimina.
  - Modelos maiores não são uniformemente mais invariantes.
- **Reaproveitamos (decisão de *design*) [I]:**
  1. O **analista que emite o *score* é neutro**, sem *persona*.
  2. Os agentes *bull* e *bear* produzem **argumentos e evidências**, nunca o *score*.
  3. O *score* final é recalculado por um analista neutro a partir do conjunto de evidências **já** verificado.

#### 3.6.3 Cao, Wang & Xiang — "When LLMs Go Abroad: Foreign Bias in AI Financial Predictions" [33]

- **[V]**
  - O ChatGPT (EUA) é mais otimista que o DeepSeek (China) com ações chinesas em preço, lucro e descrições qualitativas, e menos preciso: previsão de preço 2,415 RMB acima, ou 12,53% do preço médio.
  - O viés acompanha o **gap de cobertura de notícias**, atenua-se em firmas com **listagem cruzada**, **desaparece ao injetar notícias locais** e não existe para firmas dos EUA.
- **Reaproveitamos [I]:** em LatAm, o "otimismo por ignorância" é risco direto nas *small/mid caps* sem ADR. Mitigação:
  1. **RAG obrigatório** com fontes locais em PT/ES (fatos relevantes da CVM, *hechos esenciales* da CMF, eventos relevantes da BMV, *hechos de importancia* da SMV, informação relevante da SFC, *hechos relevantes* da CNV).
  2. Proibir que o analista julgue sem evidência local.
  3. Monitorar o viés médio do *score* por país e por "tem ADR / não tem ADR".

#### 3.6.4 Extrapolação e (des)calibração

- **[V via 34] [35]** Chen, Green, Gulen & Zhou (2024) mostram que o ChatGPT-4 **extrapola** retornos recentes ao prever retornos, e que *prompting* "racional" não corrige.
- **[V] [34]** Gao, Jiang & Yan (2026) corrigem com LoRA sobre Qwen3-32B (treino 2001–2011, validação 2012–2015, teste 2016–2024; anonimizado):
  - O coeficiente no retorno do mês anterior passa de **+0,394 para −0,120**.
  - O previsor passa a refletir reversão de curto prazo.
  - Custo de "algumas centenas de dólares".
- **Reaproveitamos:** **nunca pedir ao LLM previsões numéricas de retorno a partir de séries de preço.** Séries numéricas são domínio do motor quantitativo; o LLM fica com texto **[I]**.

### 3.7 Mercados emergentes e textos em português e espanhol

| Trabalho | Achado [V] | Implicação [I] |
|---|---|---|
| Chen, Kelly & Xiu [2][3] | Previsibilidade por *embeddings* em 16 mercados e 13 idiomas; "*polyglot portfolios*" | Abordagem multilíngue funciona; a lista de mercados não foi confirmada no PDF, então não sabemos se há LatAm |
| FinBERT-PT-BR (Santos, Bianchi & Costa, USP/FEI, 2023) [39] | BERT para sentimento financeiro em PT-BR: pré-treino com 1,4 mi de textos e 500 rotulados; supera o estado da arte da época; disponível no Hugging Face (`turing-usp/FinBertPTBR`, marcado como *depreciated*) | *Baseline* barato e local para sentimento em PT; comparar com LLMs e *embeddings* multilíngues |
| Jesus et al. (Comput. Econ., 2025) [40] | O sentimento via ChatGPT **não** melhora a previsão OOS do Ibovespa; o dicionário variável no tempo melhora | Evidência negativa para *timing* de índice; nosso uso é *cross-section* |
| Toisón de Oro / FinMA-ES / FLARE-ES (KDD'24) [41] | Primeiro *framework* bilíngue ES/EN: 144 mil instruções, 15 *datasets*, 7 tarefas; *benchmark* com 21 *datasets* e 9 tarefas; **gap** e viés multilíngue nos LLMs; FinMA-ES supera o GPT-4 em tarefas financeiras em espanhol | Validar a qualidade em ES (México, Chile, Colômbia, Peru, Argentina) separadamente de PT |
| Cao, Wang & Xiang [33] | Viés estrangeiro por falta de cobertura local; some com notícias locais | RAG local obrigatório; ADRs menos enviesados |

**Lacuna explícita [I]:** não encontramos estudo revisado por pares que avalie *cross-section* de retornos com LLM em ações latino-americanas (B3, BMV, BCS, BVC, BVL, BYMA). Nossa operação em modo sombra será, na prática, o primeiro teste. Por isso o peso inicial do componente LLM é zero.

### 3.8 Combinação de *views* de LLM com otimizadores quantitativos

#### 3.8.1 Lee et al. — "LLM-Enhanced Black-Litterman Portfolio Optimization" (CIKM'25 FinAI) [38]

- **[V]**
  - Para cada ação (50 maiores do S&P 500), o LLM recebe 2 semanas de retornos (ação, setor, mercado) e metadados, e prevê o retorno médio diário das 2 semanas seguintes.
  - O LLM é consultado **N = 100 vezes**: a média vira a *view* **q**; a **variância das 100 respostas vira Ω** (diagonal); **P = I** (visões absolutas); **τ** é ajustado numa validação de 3 meses.
  - Teste de set/2024 a jun/2025, rebalanceamento quinzenal, *long-only* com soma 1.
  - Sharpe anualizado: Llama-3.1-8B 1,23; Qwen-2-7B 1,06; Gemma-7B 0,64; GPT-4o-mini 0,36; *equal-weight* 0,89; média-variância 0,28.
  - Os autores mostram que o desempenho vem do "**estilo**" de cada LLM (otimismo estável contra pessimismo persistente) **alinhado ao regime de alta** do período.
- **Qualidade:** **C**. Um regime, modelos pequenos, 10 meses, só comprado; o próprio artigo atribui o resultado a viés direcional.
- **Reaproveitamos:**
  1. **Ω a partir da dispersão de amostras repetidas** é uma forma barata de transformar incerteza do LLM em confiança.
  2. **[I]** Para um fundo *market neutral*, o *prior* de equilíbrio por capitalização não faz sentido: usamos *prior* **zero** (sem alfa) e encolhimento (*shrinkage*) da *view* proporcional à confiança. Com π = 0, o BL equivale a um encolhimento tipo *ridge* das *views*.
  3. A lição de que "o LLM tem estilo" reforça a residualização contra fatores.

#### 3.8.2 Síntese de *design* para a combinação [I]

1. O LLM produz *views* **ordinais e estruturadas** (seção 4.6), nunca pesos.
2. O código converte a *view* em sinal: s_i = *stance*_i × *confidence*_i (ou 2·p_i − 1).
3. **Residualização cross-sectional** de s contra exposições de beta, tamanho, valor, *momentum*, liquidez, setor, país e moeda; z-score com *winsorização* em ±3; abstenção resulta em z = 0.
4. **Refinamento de alfa no padrão Grinold–Kahn** (fórmula clássica de livro-texto): α_i = IC_llm × σ_resid,i × z_i, com IC_llm *a priori* de 0,01–0,02 até haver evidência própria.
5. Alfa composto: α = w_q·α_quant + w_llm·α_llm, com **w_llm = 0 durante as primeiras 12 semanas (sombra)**.
6. Bandeiras de risco (*squeeze*, *borrow*, governança) entram como **restrições** do otimizador (limite de vendido, exclusão), não como alfa.
7. O otimizador (outro documento) impõe neutralidade *dollar*/beta/fatores e o alvo de volatilidade de 5%.

---

## 4. Síntese

### 4.1 Quais arquiteturas têm evidência robusta?

| Nível | Arquitetura | Evidência | Veredito para o nosso fundo [I] |
|---|---|---|---|
| **1 (robusta)** | **LLM como medidor**: texto → rótulo, *score* ou *embedding* → modelo estatístico simples (*ridge*, ordenação) → carteira | Lopez-Lira & Tang [1], Chen, Kelly & Xiu [2], Chrono [12], PIT [13], Kirtac & Germano [37]: pós-*cutoff*, amplo e corroborado | **Adotar** como *feature* e filtro, em horizonte semanal; esperar IC pequeno; medir decaimento |
| **2 (moderada)** | **LLM gerador de hipóteses e código** com validação programática e humano no circuito | R&D-Agent(Q) [24], Alpha-GPT [22], Man AlphaGPT [43][44] | **Adotar em P&D *off-line*** (não no ciclo semanal), com registro de tentativas e *holdout* |
| **3 (moderada para tarefas não preditivas)** | **LLM extrator e analista com RAG e citações** (documentos longos, eventos, riscos) | FinanceBench [30] (com a recuperação certa: 79%–85%), MarketSenseAI (RAG HyDE) [20], AlphaAgents (ferramentas) [21] | **Adotar** como **produtividade e controle de risco**; o valor está em não perder eventos e em documentar a tese |
| **4 (fraca)** | **Agente LLM decisor ponta a ponta** (comprar/vender/manter diário; *trader* com memória e reflexão) | TradingAgents [16], FinMem [17], FinAgent [18], INVESTORBENCH [27], contestados por FINSABER [29], Profit Mirage [14] e StockBench [28] | **Não adotar** como decisor; aproveitar só a organização em papéis e o estado estruturado |
| **5 (inconclusiva)** | **Debate multiagente *bull/bear*** como mecanismo de decisão | Evidência de melhora de factualidade em tarefas gerais (Du et al., citado em [21]); em finanças, só amostras pequenas [16][21]; viés de *persona* documentado [32] | **Adotar só como gerador de argumentos e de perguntas abertas** para o gestor, sem influência no *score* |

**Expectativa realista de magnitude [I] (aritmética ilustrativa; não é previsão):**
- Pela "lei fundamental" (IR ≈ IC × √*breadth* × TC), com ~150 nomes rebalanceados semanalmente, √(150 × 52) ≈ 88.
- Para IC de 0,02 e coeficiente de transferência de 0,3–0,5, o IR fica entre **0,53 e 0,88**; para IC de 0,03, entre **0,79 e 1,32**. É um teto otimista, porque as apostas não são independentes.
- Com vol-alvo de 5%, isso corresponde a ~2,5%–6,5% a.a. de alfa bruto *se* o IC se materializar. A contribuição marginal do LLM sobre um bom motor quantitativo deve ser uma **fração** disso.

### 4.2 Descasamento de horizonte (crítico para um processo semanal)

- **[V]** O *drift* pós-notícia se concentra em 1 a 2 dias [1][12]; Chen, Kelly & Xiu reportam conteúdo "rápido e lento", com previsões mensais também lucrativas [3].
- **[V]** Chen & Pu encontram alfa em horizontes diário, semanal e mensal no lado comprado [36].
- **[I] Consequências para o desenho:**
  1. O *score* do LLM deve focar em informação **lenta**: mudança de *guidance*, tom e conteúdo de teleconferências, revisões de analistas, fatos relevantes estruturais (M&A, recompra, emissão), riscos regulatórios e políticos.
  2. Notícias da semana anterior entram principalmente como **bandeira de risco** e **contexto**.
  3. Horizonte padrão de avaliação de 5 dias úteis (abertura de segunda a abertura da segunda seguinte), com decaimento medido em 1, 5, 20 e 60 dias.
  4. Ajustes intrassemana só para **reduzir** risco (evento de *squeeze*, *recall* de aluguel), nunca para aumentar exposição sem nova aprovação.

### 4.3 Como prevenir viés de *look-ahead* (protocolo)

| # | Controle | Fundamento |
|---|---|---|
| 1 | **Avaliação principal só prospectiva** (modo sombra desde 2026-10-05) ou estritamente após o *cutoff* do modelo, com margem de 1 mês **[I]** | [10] (não identificação), [9], [36] |
| 2 | Registrar *model_id* e versão exata, *cutoff* declarado, *hash* do *prompt*, temperatura e *seed*; nunca usar *alias* "latest" | [15], [11] |
| 3 | **Teste LAP** em qualquer *backtest* histórico: interação sinal × LAP precisa ser não significativa | [11] |
| 4 | **Controle com modelo PIT** (ChronoGPT ou PIT-4B) para tarefas de *embedding*; o *gap* de Sharpe estima o viés | [12][13] |
| 5 | **Anonimização** (nome, *ticker*, produtos, datas) em tarefas de sentimento e como ablação; ciente de que reidentifica 61%–70% | [8][9] |
| 6 | **RAG *point-in-time*:** só documentos com `published_at` ≤ `as_of`; *snapshots* arquivados com *hash*; **proibido** usar busca na *web* ao vivo em *backtest*; o verificador reprova evidência datada após o `as_of` | [15] |
| 7 | **Universo dinâmico** com deslistadas, mudanças de índice, fusões e aquisições | [15][29] |
| 8 | **Teste contrafactual:** perturbar fatos-chave da evidência; o *score* deve mudar de forma coerente; consistência de predição acima de ~0,7 sob perturbação relevante sinaliza memória **[I, limiar inspirado em 14]** | [14] |
| 9 | Tarefas **invariantes ao futuro** (extração) podem rodar no histórico; tarefas de **julgamento** só são avaliadas prospectivamente | [10] |
| 10 | Não pedir ao LLM recordação de preços ou indicadores; todo número vem do FactBook | [10], invariante 1 do repositório |

### 4.4 Como prevenir alucinação e manipulação

1. **Números somente por referência:** o LLM escreve `{{FB:<metric_id>}}` (por exemplo, `{{FB:PETR4.net_debt_ebitda_ltm}}`), e o código substitui os valores. Qualquer *token* numérico livre nas afirmações é reprovado pelo verificador (exceções: datas, nomes de trimestre e campos ordinais do *schema*) **[I; 21 usa calculadora pelo mesmo motivo]**.
2. **Citação obrigatória:** toda afirmação tem `evidence_ids`; o verificador confere que o ID existe, que `published_at` ≤ `as_of` e que a citação textual (até 300 caracteres) aparece literalmente no documento, via *hash* do trecho **[I; 15 "*rationale robustness*"]**.
3. **Recuperação por emissor** (*store* por documento ou emissor) e **contexto antes da pergunta**; evitar *vector store* único global **[30]**.
4. **Abstenção explícita:** `abstain = true` com motivo (dados insuficientes, conflito de fontes). Abstenção é preferível a resposta errada (FinanceBench: Llama2 errava em vez de recusar) **[30][15]**.
5. **Autoconsistência:** n = 5 amostras (temperatura 0,3–0,7) para julgamentos; se a concordância de sinal for menor que 80%, abster-se. A dispersão alimenta a confiança, ao estilo de Ω no LLM-BLM **[38; limiares I]**. Para extração, temperatura 0 e uma amostra.
6. **Confiança calibrada:** usar a probabilidade do rótulo (*logprobs*) quando disponível, porque amplifica o poder preditivo **[11]**, e medir calibração (Brier/ECE) prospectivamente.
7. **Injeção de *prompt*:** notícias e documentos são **dados não confiáveis**, delimitados e nunca executados como instruções; nenhuma ferramenta é acionada pelo conteúdo; *scanner* de padrões ("ignore as regras...") registra o evento sem alterar o estado (invariante 2 do repositório; OWASP LLM01 [47]).
8. **Sem *persona* no avaliador:** *score* neutro e argumentos de debate em canais separados **[32]**.
9. ***Logging* integral:** *prompts*, documentos recuperados, saídas brutas, *hashes* e carimbos de tempo, que permitem auditoria e o teste "não reprodutível" de Chen & Pu (refazer com modelo mais novo e medir a diferença) **[36][15]**.

### 4.5 Como avaliar a camada de pesquisa LLM

**Métrica primária:**
- *Rank IC* semanal (Spearman), em cada data t, entre o *score* LLM residualizado (ŝ) e o retorno **residual** (pós-fatores, setor, país e FX em USD) da semana t → t+1.
- Reportar média, desvio-padrão, ICIR = média/desvio × √52, t de Newey-West (4 defasagens) e taxa de acerto do IC (% de semanas com IC > 0).

**Métricas secundárias:**

| Métrica | Definição | Para quê |
|---|---|---|
| **IC incremental** | Coeficiente de ŝ na regressão *cross-sectional* do retorno residual contra [α_quant, ŝ], ou IC de ŝ ortogonalizado em relação a α_quant | Saber se o LLM agrega **além** do quantitativo |
| **Decaimento** | IC em 1, 5, 20 e 60 dias úteis | Calibrar horizonte e *turnover* (4.2) |
| **IC por perna e por país** | IC no terço superior contra o inferior; por BR, MX, CL, CO, PE, AR; com e sem ADR | Assimetria comprado/vendido [36] e viés estrangeiro [33] |
| **Cobertura e abstenção** | % de nomes com *view* válida; % de abstenções | Abstenção alta em uma subamostra indica lacuna de dados |
| **Calibração** | Brier e ECE de `p_outperform` contra o resultado observado | Confiança utilizável no encolhimento |
| **Consistência** | Concordância de sinal entre as 5 amostras; estabilidade semana a semana sem evidência nova | Ruído contra sinal |
| **Qualidade de citação** | % de afirmações com citação válida; taxa de correspondência dos trechos citados; números fora do FactBook (meta: 0) | Alucinação |
| **Contrafactual e LAP** | Consistência de predição sob perturbação; interação LAP | Memória e *look-ahead* [11][14] |
| **Viés de estilo** | Correlação de s (antes da residualização) com tamanho, setor, *momentum* e país | Vieses [31][33] |
| **Custo** | US$ e *tokens* por nome por semana; latência total do ciclo | Viés de custo [15] |

**Poder estatístico (aritmética [I]):** semanas necessárias para t ≈ 2 com IC médio μ e desvio semanal σ: T ≈ (2σ/μ)².

| μ (IC médio) | σ = 0,10 | σ = 0,12 |
|---|---|---|
| 0,02 | 100 semanas | 144 semanas |
| 0,03 | 44 semanas | 64 semanas |
| 0,05 | 16 semanas | 23 semanas |

Implicação: um ano de modo sombra mal separa IC de 0,03 do zero. Por isso o peso do LLM sobe devagar e com *gates* intermediários baseados também em qualidade (citação, calibração, ausência de viés), não só em IC.

**Ablações obrigatórias (cada uma no próprio modo sombra, em paralelo, já que o custo é só de *tokens*) [I]:**
1. Só quantitativo contra quantitativo + LLM (IC e IR incrementais).
2. *Score* LLM bruto contra residualizado.
3. Com e sem anonimização [8].
4. Analista único neutro contra analista mais debate (o debate não pode piorar a calibração) [32].
5. Fontes locais PT/ES contra só inglês ou ADR [33].
6. Modelo A contra modelo B contra *ensemble* (Chen, Kelly & Xiu: o *ensemble* venceu) [3].
7. *Prompt* (rótulo) contra *embedding* com *ridge* (se houver histórico textual *point-in-time* suficiente) [2].
8. Temperatura e número de amostras (1 contra 5).

**Protocolo de *paper trading* e modo sombra [I]:**

| Fase | Semanas | w_llm | *Gate* para avançar |
|---|---|---|---|
| S0 — Sombra | 1–12 (a partir de 2026-10-05) | 0% | Zero violações de *look-ahead*/citação; números fora do FactBook = 0; cobertura ≥ 80%; custo dentro do orçamento |
| S1 — Piloto | 13–25 | ≤ 10% | IC médio > 0 com ICIR anualizado ≥ 0,5; Brier melhor que o *baseline* constante; viés de estilo residual não significativo |
| S2 — Ativo limitado | 26–51 | ≤ 20% | IC incremental > 0 com t ≥ 1,5; nenhum país com IC significativamente negativo |
| S3 — Pleno | ≥ 52 | ≤ 30% | t ≥ 2 no IC incremental; estabilidade por regime |
| Rebaixamento | qualquer | volta a 0% | IC acumulado de 13 semanas < 0 com t ≤ −1,5, **ou** incidente de alucinação ou *look-ahead* |

### 4.6 Papéis de agentes e *schemas* para o processo semanal (segunda-feira)

**Princípio [I]:** separar **o que é determinístico** (dados, números, risco, otimização, aprovação) **do que é linguístico** (extração, síntese, argumentação). LLMs só produzem JSON validado por *schema*; nada de LLM chega ao otimizador sem passar pelo verificador e pela conversão determinística (3.8.2).

**Fluxo semanal (horários de Brasília) [I]:**
1. **Domingo, 18h:** *snapshot* de dados e documentos (corte `as_of` = sexta, fechamento, mais documentos publicados até domingo, 23h59).
2. **Segunda, 06h–08h30:**
   1. Motor quantitativo determinístico.
   2. Extratores LLM sobre documentos novos.
   3. Analistas LLM.
   4. Debate (apenas nomes candidatos e posições atuais).
   5. Sentinela de risco.
   6. Verificador.
   7. Conversão determinística.
   8. Otimizador.
   9. Memorando.
3. **Segunda, 08h30–09h45:** revisão e aprovação do gestor, com *hash* vinculado.
4. **Execução** a partir da abertura (B3 às 10h; NYSE às 10h30, horário de Brasília). Ordens e custos registrados.

| # | Papel | Tipo | Entrada | Saída (*schema*) | Pode / Não pode |
|---|---|---|---|---|---|
| R0 | **Data Steward** | Código | Fontes de preço, fundamentos, aluguel e documentos | `Snapshot` (*manifest* com SHA-256 por arquivo) | Não altera dados brutos; marca dados simulados |
| R1 | **Quant Engine** | Código | `Snapshot` | `FactBook` (métricas com `metric_id`), α_quant, exposições, risco, liquidez, métricas de *squeeze* | Único produtor de números |
| R2 | **Document & News Extractor** | LLM (temp. 0) | Documento ou notícia nova (PT/ES/EN) de um emissor | `EventRecord[]` | Extrai fatos invariantes ao futuro; **não** julga retorno |
| R3 | **Fundamental Analyst (neutro)** | LLM (n = 5) | `EventRecord`s verificados, referências do FactBook, tese anterior | `AnalystView` | Emite *stance* e confiança; **sem *persona***; números só via `{{FB:…}}` |
| R4 | **Bull / Bear Researchers** | LLM (1–2 rodadas) | `AnalystView` e evidências | `DebateSummary` (argumentos, conflitos, perguntas) | **Não** alteram o *score*; servem ao gestor e ao re-*score* neutro |
| R5 | **Macro & Country Analyst** | LLM | Comunicados de bancos centrais, calendário eleitoral, câmbio (via FactBook) | `CountryNote` com bandeiras | Gera bandeiras e contexto; não gera alfa |
| R6 | **Risk & Short-Squeeze Sentinel** | Regras + LLM | Métricas de *squeeze* do FactBook; eventos (controlador, ofertas, mudanças de índice, recompras) | `RiskFlag[]` | Propõe **restrições** (limite de vendido, exclusão); a decisão é do otimizador e do gestor |
| R7 | **Verifier / Red Team** | Código + LLM | Todas as saídas LLM e o *store* de evidências | `VerificationReport` | Reprova sem citação, com número fora do FactBook, com evidência posterior ao `as_of` ou com suspeita de injeção |
| R8 | **PM Copilot (redator)** | LLM | Saídas aprovadas e resultados do otimizador | `WeeklyMemo` (rascunho) | Redige; **não** altera pesos; números via FactBook |
| R9 | **Gestor (humano)** | Humano | Memorando, carteira proposta e bandeiras | `Approval` vinculada a *hashes* | Único que aprova; sem autoaprovação |

**Schemas (JSON; `schema_version` = "1.0") [I]** — sugeridos para implementação com *structured outputs* e validação Pydantic.

```jsonc
// EvidenceItem — gerado pelo Data Steward (R0); imutável
{
  "evidence_id": "EV-2026W41-000123",
  "issuer_id": "BR:VALE3",
  "source_type": "filing|news|transcript|regulator|company_presentation",
  "source_name": "CVM Fato Relevante",
  "url": "https://...",
  "language": "pt|es|en",
  "published_at": "2026-10-02T21:14:00Z",
  "retrieved_at": "2026-10-04T21:00:00Z",
  "content_sha256": "…",
  "is_simulated": false
}
```

```jsonc
// EventRecord — saída do Extractor (R2)
{
  "schema_version": "1.0",
  "event_id": "EVT-…",
  "issuer_id": "BR:VALE3",
  "evidence_id": "EV-2026W41-000123",
  "event_type": "earnings|guidance|m_and_a|buyback|dividend|equity_offering|block_trade|index_change|management_change|controller_action|regulatory|litigation|political|rating_change|short_report|other",
  "event_date": "2026-10-02",
  "direction_hint": -1,
  "materiality": "low|medium|high",
  "verbatim_quote": "≤ 300 caracteres, no idioma original",
  "quote_sha256": "…",
  "factbook_refs": ["VALE3.capex_guidance_2026"],
  "future_invariant": true,
  "retrieval_query": "texto curto para recuperação futura (separado do resumo)"
}
```

```jsonc
// AnalystView — saída do Fundamental Analyst neutro (R3)
{
  "schema_version": "1.0",
  "view_id": "AV-2026W41-BR:VALE3",
  "as_of": "2026-10-05T06:00:00-03:00",
  "issuer_id": "BR:VALE3",
  "instrument_ids": ["VALE3.SA", "VALE"],
  "horizon_days": 5,
  "stance": 1,                  // inteiro em [-2, +2], relativo ao setor/país (não ao mercado)
  "p_outperform": 0.56,         // probabilidade de superar o retorno residual mediano do setor/país no horizonte
  "confidence": 0.4,            // [0, 1]; combinado à dispersão das n amostras pelo código
  "abstain": false,
  "abstain_reason": null,
  "drivers": [
    {"claim": "Guidance de volume revisado para cima ({{FB:VALE3.vol_guidance_delta}})",
     "evidence_ids": ["EV-2026W41-000123"], "direction": 1, "materiality": "medium"}
  ],
  "risks": [
    {"claim": "…", "evidence_ids": ["…"], "direction": -1, "materiality": "low"}
  ],
  "catalysts": [{"event": "Resultado 3T26", "expected_date": "2026-10-23", "evidence_ids": ["…"]}],
  "kill_criteria": ["Revisão negativa de guidance de custo C1"],
  "data_gaps": ["Sem teleconferência transcrita do 2T26 em PT"],
  "sources_languages": ["pt", "en"],
  "model": {"provider": "…", "model_id": "…@versão-fixa", "knowledge_cutoff": "YYYY-MM",
            "temperature": 0.5, "n_samples": 5, "prompt_sha256": "…"},
  "input_bundle_sha256": "…"
}
```

```jsonc
// DebateSummary — saída dos Bull/Bear Researchers (R4); sem score
{
  "schema_version": "1.0",
  "issuer_id": "BR:VALE3",
  "rounds": 2,
  "bull_points": [{"argument": "…", "evidence_ids": ["…"]}],
  "bear_points": [{"argument": "…", "evidence_ids": ["…"]}],
  "evidence_conflicts": ["Fonte A vs Fonte B sobre …"],
  "open_questions_for_pm": ["…"],
  "new_evidence_requested": ["…"]
}
```

```jsonc
// RiskFlag — saída do Risk & Short-Squeeze Sentinel (R6)
{
  "schema_version": "1.0",
  "issuer_id": "MX:XXXX",
  "flag_type": "short_squeeze|borrow_recall|liquidity|governance|controller_action|regulatory|political|accounting|event_gap|index_event",
  "severity": 4,                       // 1–5
  "metric_refs": ["XXXX.short_interest_pct_float", "XXXX.days_to_cover", "XXXX.borrow_fee_bps", "XXXX.utilization_pct"],
  "rationale": "texto sem números livres",
  "evidence_ids": ["…"],
  "suggested_constraint": "none|cap_short|exclude_short|reduce_gross|hedge|pm_review"
}
```

```jsonc
// VerificationReport — saída do Verifier (R7); decide se a view segue para a conversão
{
  "schema_version": "1.0",
  "target_id": "AV-2026W41-BR:VALE3",
  "claims_total": 6,
  "claims_with_valid_citation": 6,
  "quote_match_rate": 1.0,
  "free_numeric_tokens": 0,
  "evidence_after_as_of": 0,
  "injection_suspected": false,
  "persona_contamination_check": "pass",
  "status": "pass|fail",
  "failures": []
}
```

```jsonc
// WeeklyMemo — rascunho do PM Copilot (R8); aprovação pelo gestor (R9)
{
  "schema_version": "1.0",
  "week_id": "2026-W41",
  "as_of": "2026-10-05",
  "hashes": {"snapshot": "…", "factbook": "…", "config": "…", "views_bundle": "…", "portfolio": "…", "memo_text": "…"},
  "llm_component_weight": 0.0,
  "phase": "S0-shadow",
  "summary_md": "…texto com {{FB:…}}…",
  "top_long_theses": ["AV-…"],
  "top_short_theses": ["AV-…"],
  "risk_flags": ["RF-…"],
  "changes_vs_last_week": ["…"],
  "is_simulated_data": false,
  "approval": {"approved_by": null, "approved_at": null, "approved_hashes": null}
}
```

**Regras de orquestração [I]:**
- Estado global estruturado, ao estilo TradingAgents [16]; nenhum agente lê o "*chat*" de outro, apenas objetos validados.
- Roteamento de custo: extração e triagem com modelo rápido; análise e debate com modelo de raciocínio. O *golden set* interno decide o modelo por papel, ao estilo do *Smart Scheduler* do FinRobot [19].
- Debate apenas para posições atuais, novos candidatos e nomes com bandeira de severidade ≥ 3, o que controla custo.
- O re-*score* neutro pós-debate só pode mudar o *stance* em até ±1 e **somente** se houver evidência nova verificada.
- Saídas que falham no verificador viram `abstain` (z = 0) e são listadas no memorando: a falha é visível, não silenciosa.

### 4.7 Tabela de parâmetros

| Parâmetro | Valor recomendado | Racional / fonte |
|---|---|---|
| Papel do LLM na decisão | *Views* estruturadas; **nunca** pesos nem números | Níveis 1 e 3 de evidência; FINSABER [29], Profit Mirage [14]; invariante do repositório |
| Peso do componente LLM no alfa composto | 0% (S0) → ≤ 10% (S1) → ≤ 20% (S2) → ≤ 30% (S3) | Poder estatístico (4.5); ausência de evidência para LatAm (3.7) **[I]** |
| IC *a priori* do LLM (Grinold–Kahn) | 0,01–0,02 | Magnitudes de IC diário de 0,016–0,05 em [24]; decaimento [1] **[I]** |
| Horizonte de avaliação primário | 5 dias úteis (segunda, abertura → segunda seguinte, abertura) | Rebalanceamento semanal; o *drift* de notícia dura 1–2 dias [1][12] |
| Horizontes de decaimento | 1, 5, 20 e 60 dias úteis | Chen, Kelly & Xiu: conteúdo rápido e lento [3] |
| Janela de notícias por ciclo | `published_at` ∈ (*as_of* anterior, *as_of* atual] | RAG *point-in-time* [15] |
| Temperatura (extração) | 0; 1 amostra | Determinismo; tarefa invariante ao futuro [10] |
| Temperatura (julgamento) | 0,3–0,7; **n = 5** amostras | Dispersão vira confiança, como Ω no LLM-BLM (que usou N = 100) [38]; custo **[I]** |
| Concordância mínima entre amostras | ≥ 80% no sinal do *stance*, senão abstenção | **[I]** |
| Escala do *stance* | Inteiro de −2 a +2, mais `p_outperform` ∈ [0, 1] e `confidence` ∈ [0, 1] | Saída categórica funciona melhor que número livre [1][26] |
| Rodadas de debate | 1–2 | TradingAgents (*n* rodadas) [16]; AlphaAgents (≥ 2 falas por agente) [21]; custo **[I]** |
| Mudança máxima do *stance* pós-debate | ±1, só com evidência nova verificada | Viés de *persona* [32] **[I]** |
| *Persona* no analista que pontua | **Proibida** (neutro); preferências como "perfil do usuário" só no memorando | [32] |
| Citações por afirmação | ≥ 1 `evidence_id` válido; correspondência de trecho = 100% | [15] (*rationale robustness*) |
| Números livres nas saídas LLM | 0 (somente `{{FB:metric_id}}`) | Invariante 1; AlphaAgents usa calculadora [21] |
| Evidência posterior ao *as_of* | 0 (reprovação automática) | [15] |
| Tamanho máximo do trecho citado | 300 caracteres, idioma original | Verificabilidade **[I]** |
| Recuperação | *Store* por emissor ou documento; *top-k* = 5–8 *chunks*; *chunk* de ~400 *tokens* com sobreposição de 80; contexto antes da pergunta | FinanceBench [30]; MarketSenseAI (k 3–7) [20]; Asaad et al. (k = 8; 400/80) [32] |
| Idiomas das fontes | PT, ES e EN obrigatórios; um nome sem fonte local recebe abstenção ou rebaixamento de confiança | Viés estrangeiro [33]; FLARE-ES [41] |
| Residualização do *score* | Contra beta, tamanho, valor, *momentum*, liquidez, setor, país e moeda (*cross-section* semanal) | Vieses [31]; MarketSenseAI beta ~0,95 [20] |
| *Winsorização* do z-score | ±3 | Padrão quantitativo **[I]** |
| Anonimização | Ativa para sentimento de manchete; ablação semanal para o analista | [8]; limite de reidentificação de 61%–70% [9] |
| Teste LAP | Obrigatório em *backtests* históricos; interação não significativa (p > 0,10) | [11] |
| Teste contrafactual | Mensal, 20 nomes; consistência de predição sob perturbação material ≤ 0,7 | [14] **[I, limiar]** |
| Margem pós-*cutoff* para *backtest* | ≥ 1 mês após o *cutoff* declarado; modelo com versão fixa | [10][15] **[I]** |
| *Gates* de fase | ICIR ≥ 0,5 (S1); t ≥ 1,5 incremental (S2); t ≥ 2 (S3) | Aritmética de 4.5 **[I]** |
| Gatilho de rebaixamento | IC de 13 semanas < 0 com t ≤ −1,5, ou incidente de alucinação ou *look-ahead* | **[I]** |
| Registro de tentativas de alfa (P&D) | Obrigatório; correção de múltiplos testes; racional pré-registrado | [42][44] |
| Orçamento de chamadas | ~6–11 chamadas por nome por semana (extração, análise ×5 amostras, debate seletivo, verificação) | TradingAgents usa ~11 chamadas + 20 ferramentas por decisão [16] **[I]** |
| Versionamento | `model_id@versão`, `prompt_sha256`, `schema_version`, `config_sha256` em cada saída | [15]; invariante 3 do repositório |

---

## 5. Riscos, limitações e questões em aberto

1. **[I] Ausência de evidência LatAm.** Nenhum estudo revisado testa *cross-section* de ações LatAm com LLM; o único estudo brasileiro encontrado é negativo para o índice [40]. O modo sombra é um experimento, não uma premissa.
2. **[V] Decaimento por adoção.** O próprio Lopez-Lira & Tang documenta Sharpe caindo à medida que LLMs se difundem [1]. Esperar o mesmo para qualquer sinal textual simples.
3. **[V] Replicabilidade.** Um artigo de alto impacto foi retirado [6]; o StockBench tem inconsistência entre resumo e tabela [28]. Tratar resultados de *preprints* como hipóteses.
4. **[I] Mudança de modelo.** Provedores atualizam modelos; fixar versões e reexecutar o *golden set* a cada troca. O teste de Chen & Pu (modelo novo × decisões antigas) mede quanto do "alfa" vira memória [36].
5. **[I] Custo e latência.** O ciclo de segunda precisa terminar antes da abertura; extração na madrugada de domingo para segunda e debate seletivo.
6. **[V] Dados *point-in-time* em PT/ES.** Modelos PIT públicos são majoritariamente em inglês [12][13]; a validade de *embeddings* PIT em PT/ES é desconhecida.
7. **[I] Interação com *short squeeze*.** A previsibilidade de notícias negativas é maior em ações pequenas [1], exatamente onde o aluguel é caro e o *squeeze* é provável. O LLM deve **aumentar** cautela no vendido (bandeiras), não sugerir mais *shorts* em pequenas.

---

## 6. Fontes (numeradas; datas de publicação ou versão; acesso em 2026-10-05)

1. Lopez-Lira, A.; Tang, Y. *Can ChatGPT Forecast Stock Price Movements? Return Predictability and Large Language Models.* arXiv:2304.07619, v1 2023-04-06; **v6 2025-10-28**. https://arxiv.org/abs/2304.07619
2. Chen, Y.; Kelly, B.; Xiu, D. *Expected Returns and Large Language Models.* SSRN 4416687 (postado em abr/2023; revisado em fev/2026, segundo o índice do SSRN). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416687
3. Kelly, B. *Expected Returns and Large Language Models* (slides), Wharton Jacobs Levy Center, set/2024. https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2024/09/Kelly-WhartonJL.pdf
4. Li, S. Z. *Discussion: Expected Returns and Large Language Models* (slides), Wharton Jacobs Levy Center, set/2024. https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2024/09/ExpectedReturnAndLLM_Discussion_SophiaZhengziLi_NoPause.pdf
5. FINM 33200 (UChicago), *LLMs for Return Prediction: Prompts vs. Embeddings* (material de curso; **fonte secundária** dos Sharpe de Chen, Kelly & Xiu). https://finm-33200.github.io/discussions/expected_returns_llms.html
6. Kim, A.; Muhn, M.; Nikolaev, V. *Financial Statement Analysis with Large Language Models.* arXiv:2407.17866, v1 2024-07-25, v2 2024-11-10, **retirado (v3) em 2025-02-20**. https://arxiv.org/abs/2407.17866
7. Muhn, M. *Research* (nota de retirada, fev/2025). https://mmuhn.github.io/research/
8. Glasserman, P.; Lin, C. *Assessing Look-Ahead Bias in Stock Return Predictions Generated by GPT Sentiment Analysis.* arXiv:2309.17322, 2023-09-29. https://arxiv.org/abs/2309.17322
9. Sarkar, S. K.; Vafa, K. *Lookahead Bias in Pretrained Language Models.* SSRN 4754678; 1ª versão 2024-03-11, versão de 2024-06-28 (NBER). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4754678 · PDF: https://conference.nber.org/conf_papers/f205530/f205530.pdf
10. Lopez-Lira, A.; Tang, Y.; Zhu, M. *The Memorization Problem: Can We Trust LLMs' Economic Forecasts?* arXiv:2504.14765, v1 2025-04-15, v2 2025-12-15. https://arxiv.org/abs/2504.14765
11. Gao, Z.; Jiang, W.; Yan, Y. *Detecting Lookahead Bias in LLM Forecasts* (antes "A Test of Lookahead Bias in LLM Forecasts"). arXiv:2512.23847, v1 dez/2025, v2 2026-06-12. https://arxiv.org/abs/2512.23847
12. He, S.; Lv, L.; Manela, A.; Wu, J. *Chronologically Consistent Large Language Models.* arXiv:2502.21206, v1 fev/2025, v3 2025-07-06. https://arxiv.org/abs/2502.21206
13. Kelly, B.; Malamud, S.; Schwab, J.; Xu, T. A. *Scaling Point-in-Time Language Models.* arXiv:2607.11889, v2 2026-07-17. https://arxiv.org/abs/2607.11889
14. Li, X. et al. *Profit Mirage: Revisiting Information Leakage in LLM-based Financial Agents.* arXiv:2510.07920, 2025-10-09. https://arxiv.org/abs/2510.07920
15. Kong, Y.; Lee, H.; Hwang, Y.; Lopez-Lira, A.; Levy, B.; Mehta, D.; Wen, Q.; Choi, C.; Lee, Y.; Zohren, S. *Evaluating LLMs in Finance Requires Explicit Bias Consideration.* arXiv:2602.14233, 2026-02-15. https://arxiv.org/abs/2602.14233
16. Xiao, Y.; Sun, E.; Luo, D.; Wang, W. *TradingAgents: Multi-Agents LLM Financial Trading Framework.* arXiv:2412.20138, v7 2025-06-03. https://arxiv.org/abs/2412.20138
17. Yu, Y. et al. *FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design.* arXiv:2311.13743, v2 2023-12-03. https://arxiv.org/abs/2311.13743
18. Zhang, W. et al. *A Multimodal Foundation Agent for Financial Trading: Tool-Augmented, Diversified, and Generalist (FinAgent).* KDD'24; arXiv:2402.18485, v3 2024-06-28. https://arxiv.org/abs/2402.18485
19. Yang, H. et al. *FinRobot: An Open-Source AI Agent Platform for Financial Applications using LLMs.* arXiv:2405.14767, v2 2024-05-27. https://arxiv.org/abs/2405.14767
20. Fatouros, G.; Metaxas, K.; Soldatos, J.; Karathanassis, M. *MarketSenseAI 2.0: Enhancing Stock Analysis through LLM Agents.* arXiv:2502.00415, v2 2025-10-03. https://arxiv.org/abs/2502.00415
21. Zhao, T.; Lyu, J.; Jones, S.; Garber, H.; Pasquali, S.; Mehta, D. (BlackRock). *AlphaAgents: Large Language Model based Multi-Agents for Equity Portfolio Constructions.* arXiv:2508.11152, 2025-08-15. https://arxiv.org/abs/2508.11152
22. Wang, S. et al. *Alpha-GPT: Human-AI Interactive Alpha Mining for Quantitative Investment.* arXiv:2308.00016, v2 2025-09-20. https://arxiv.org/abs/2308.00016
23. Wang, S.; Yuan, H.; Ni, L. M.; Guo, J. *QuantAgent: Seeking Holy Grail in Trading by Self-Improving Large Language Model.* arXiv:2402.03755, 2024-02-06. https://arxiv.org/abs/2402.03755
24. Li, Y. et al. (Microsoft Research Asia). *R&D-Agent-Quant: A Multi-Agent Framework for Data-Centric Factors and Model Joint Optimization.* NeurIPS 2025; arXiv:2505.15155, v2 2025-09-25. https://arxiv.org/abs/2505.15155 · Código: https://github.com/microsoft/RD-Agent
25. Yang, H.; Liu, X.-Y.; Wang, C. D. *FinGPT: Open-Source Financial Large Language Models.* FinLLM@IJCAI 2023; arXiv:2306.06031, v2 2025-11-15. https://arxiv.org/abs/2306.06031
26. Xie, Q. et al. *FinBen: An Holistic Financial Benchmark for Large Language Models.* arXiv:2402.12659, v2 2024-06-19. https://arxiv.org/abs/2402.12659
27. Li, H. et al. *INVESTORBENCH: A Benchmark for Financial Decision-Making Tasks with LLM-based Agent.* arXiv:2412.18174, 2024-12-24. https://arxiv.org/abs/2412.18174
28. Chen, Y. et al. *StockBench: Can LLM Agents Trade Stocks Profitably in Real-world Markets?* arXiv:2510.02209, v2 2026-03-02. https://arxiv.org/abs/2510.02209
29. Li, W. W.; Kim, H.; Cucuringu, M.; Ma, T. *Can LLM-based Financial Investing Strategies Outperform the Market in Long Run? (FINSABER).* KDD'26; arXiv:2505.07078, v6 2026-06-26. https://arxiv.org/abs/2505.07078
30. Islam, P. et al. *FinanceBench: A New Benchmark for Financial Question Answering.* arXiv:2311.11944, 2023-11-20. https://arxiv.org/abs/2311.11944
31. Lee, H. et al. *Your AI, Not Your View: The Bias of LLMs in Investment Analysis.* ICAIF'25; arXiv:2507.20957, v4 2025-10-16. https://arxiv.org/abs/2507.20957
32. Asaad, A.; Mohamed, A.; Zhang, Y.; Abdelsalam, O. *The Analyst in the Prompt: Role, Retrieval, and Memory Biases in LLM Financial Analysis.* arXiv:2609.03218, 2026-09-02. https://arxiv.org/abs/2609.03218
33. Cao, S.; Wang, C. C. Y.; Xiang, Y. *When LLMs Go Abroad: Foreign Bias in AI Financial Predictions.* SSRN 5440116 (2025). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5440116 · Resumo HBS Working Knowledge: https://www.library.hbs.edu/working-knowledge/chatgpt-vs-deepseek-what-chinese-stocks-reveal-about-ais-limits
34. Gao, Z.; Jiang, W.; Yan, Y. *Debiasing LLMs by Fine-tuning.* arXiv:2604.02921, 2026-04-03 https://arxiv.org/abs/2604.02921
35. Chen, S.; Green, T. C.; Gulen, H.; Zhou, D. *What does ChatGPT make of historical stock returns? Extrapolation and miscalibration in LLM stock return forecasts.* arXiv:2409.11540, 2024 (lido via citação/replicação em [34]). https://arxiv.org/abs/2409.11540
36. Chen, Z.; Pu, D. *Autonomous Market Intelligence: Agentic AI Nowcasting Predicts Stock Returns.* arXiv:2601.11958, 2026-01-17 (resultados atualizados em https://github.com/mapledust0/AI-Stock-Nowcasting/). https://arxiv.org/abs/2601.11958
37. Kirtac, K.; Germano, G. *Sentiment trading with large language models.* Finance Research Letters 62 (2024), art. 105227. https://eprints.lse.ac.uk/128664/
38. Lee, Y.; Kim, Y.; Kim, J.; Kim, S.; Lee, Y. *LLM-Enhanced Black-Litterman Portfolio Optimization.* CIKM'25 FinAI Workshop; arXiv:2504.14345, v2 2025-10-19. https://arxiv.org/abs/2504.14345
39. Santos, L. L.; Bianchi, R. A. C.; Costa, A. H. R. *FinBERT-PT-BR: Análise de Sentimentos de Textos em Português do Mercado Financeiro.* BWAIF/SBC, 2023. https://sol.sbc.org.br/index.php/bwaif/article/view/24960 · Modelo: https://huggingface.co/turing-usp/FinBertPTBR
40. Jesus, D. P.; Medeiros, E. H. O.; Godeiro, L. L.; Proque, A. L. *Forecasting Brazilian Stock Market Using Sentiment Indices from Textual Data, Chat-GPT-Based and Technical Indicators.* Computational Economics 66(5):3735–3780, nov/2025. https://link.springer.com/article/10.1007/s10614-024-10835-7
41. Zhang, X. et al. *Dólares or Dollars? Unraveling the Bilingual Prowess of Financial LLMs Between Spanish and English (Toisón de Oro, FinMA-ES, FLARE-ES).* KDD'24; arXiv:2402.07405. https://arxiv.org/abs/2402.07405
42. Novy-Marx, R.; Velikov, M. *AI-Powered (Finance) Scholarship.* NBER Working Paper 33363, jan/2025. https://www.nber.org/papers/w33363
43. Hedgeweek. *Man Group deploys agentic AI for quant signal discovery* (citando a Bloomberg), 2025-07-11. https://www.hedgeweek.com/man-group-deploys-agentic-ai-for-quant-signal-discovery/
44. Fang, Z.; Moore, J. (Man Group). *What AI Can (and Can't Yet) Do for Alpha* (data indicada na página: set/2026). https://www.man.com/insights/what-ai-can-do-for-alpha
45. Bloomberg Professional. *Bridgewater now has $2bn fund run by machine learning* (2024); AI Street, *Bridgewater's AI Fund Generating "Unique Alpha"* (mar/2025). https://www.bloomberg.com/professional/insights/trading/bridwater-now-has-2bn-fund-run-by-machine-learning/ · https://www.ai-street.co/p/bridgewater-ceo-ai-fund-generating-unique-alpha
46. OpenAI. *How Balyasny Asset Management built an AI research engine* (estudo de caso; **não lido diretamente**, retornou HTTP 403; fatos via resultado de busca). https://openai.com/index/balyasny-asset-management/
47. OWASP GenAI Security Project. *LLM01:2025 Prompt Injection* (Top 10 for LLM Applications 2025). https://genai.owasp.org/llmrisk/llm01-prompt-injection/

*Trabalhos citados apenas indiretamente (não lidos; mencionados nas fontes acima):* Du et al. (2023), debate multiagente, arXiv:2305.14325 (via [21]); Engelberg, Manela, Mullins & Vulicevic (2025), *Entity Neutering* (via [10][34]); Yan et al. (2026), *DatedGPT*, arXiv:2603.11838 (via [13][34]); Didisheim et al. (2026), anomalia de "notícia pura" verificada com ChronoBERT (via [13]); Chen, Didisheim & Somoza (2024), confiança interna do LLM (via [11]).
