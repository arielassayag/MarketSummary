# Contexto Macro e de Mercado LatAm: briefing para a 1ª carteira semanal

> **Documento de pesquisa 05: Fundo Long/Short Equities LatAm (USD, net neutral, vol-alvo 5% a.a., banda de 3% a 7%)**
> **Data de referência:** segunda-feira, **2026-10-05**, antes da abertura. Último pregão completo: **sexta-feira, 2026-10-02**.
> **Escopo:**
> - resultado do 1º turno das eleições gerais do Brasil (2026-10-04);
> - política monetária e fiscal, inflação e câmbio de Brasil, México, Chile, Colômbia, Peru e Argentina;
> - contexto global (Fed, USD, Treasuries, petróleo, minério, cobre, lítio, China, fluxos EM, VIX);
> - desempenho de índices e ETFs;
> - calendário de eventos de 05 a 30/out/2026;
> - riscos e oportunidades para um livro net neutral, apresentados como **hipóteses de pesquisa**.
>
> **Natureza dos dados:** dados **REAIS**, de fontes públicas. **Não são dados simulados.** Os números foram **transcritos das fontes**. O LLM não calculou nenhum retorno, diferença, ranking ou contribuição (AGENTS.md, invariante 1). Quando aparece uma variação percentual, ela é a **reportada pela fonte**. Antes de qualquer uso quantitativo no FactBook ou no otimizador, preços e níveis de mercado precisam ser **re-obtidos pela camada de dados determinística**.
>
> **Convenção de evidência** (a mesma dos documentos 01 e 02):
> - **[F]**: fato verificado numa página lida diretamente (fonte primária ou jornalística identificada).
> - **[S]**: fato de fonte secundária ou agregador, ou conhecido **apenas pelo trecho (snippet) de busca** porque a página bloqueou a leitura (HTTP 403, 451 ou 503, paywall). Precisa de confirmação.
> - **[K]**: conhecimento prévio do modelo, **não re-verificado** nesta sessão. Confirmar antes de usar.
> - **[I]**: inferência ou hipótese nossa. **Não é fato.**
>
> **Limites desta sessão:**
> 1. Várias fontes primárias bloquearam a leitura automatizada: Bloomberg, CNBC, CNN, NPR, Poder360, White & Case, IBGE. Nesses casos, os números vêm de trechos de busca ou de reproduções em outros veículos.
> 2. O orçamento de buscas da sessão acabou no meio da pesquisa. As datas de balanços do 3T26 **não foram confirmadas** e aparecem como padrão histórico **[K]/[I]**.
> 3. Um trecho de busca afirmou um "resultado do 2º turno de 25/10" (Lula 50,90% × 49,10%). Esses números são do **2º turno de 2022**, contaminando o resultado da busca. **O 2º turno de 2026 ainda não aconteceu** (será em 2026-10-25).
> 4. **Passe de verificação adversarial (2026-10-05):** as afirmações numéricas e datadas foram re-checadas contra fontes primárias quando acessíveis (JSON oficial do TSE, API SGS do BCB, Treasury, BLS, Fed, Banxico). Os trechos corrigidos estão marcados no texto e o resultado item a item está na seção **"Verificação independente"**, no fim. Itens sem confirmação independente estão marcados **[NÃO VERIFICADO]**.

---

## Sumário executivo

1. **Brasil: Flávio Bolsonaro (PL) liderou o 1º turno, e há 2º turno em 25/out.** Com 100% das urnas apuradas, Flávio teve **47,03%** dos votos válidos (56,1 mi de votos) e Lula (PT) **45,16%** (53,9 mi). Votaram 78,92% dos eleitores. O resultado está **confirmado no JSON oficial do TSE** [103] e por várias fontes independentes [1][2][4][5]. As pesquisas da véspera traziam Lula à frente (Datafolha/Quaest em 03/out: Lula 45–46% dos válidos, Flávio 42–45%), e Bloomberg e CNBC classificaram o resultado como surpresa. A direita ganhou peso no Senado, na Câmara e nos governos estaduais: Tarcísio foi reeleito em SP com **62,65%** (TSE, final; os 62,85% eram parciais), e há 2º turno para governador em **7 estados** (AC, AM, DF, ES, RJ, RN, TO) [103][2]. **[F]**
2. **Reação esperada: rali de ativos brasileiros nesta segunda-feira.** Na noite de domingo, em negociação *overnight*, o EWZ subiu **+8,72% (US$ 41,52)** [9] e chegou a **+10,29% (US$ 42,12)** [2]. Ele havia fechado a sexta em US$ 38,19 [15]. A gestão da ASA espera "alta forte da bolsa, valorização do real e fechamento dos juros nominais e reais" [9]. Ressalva: a liquidez *overnight* é fina e a formação de preço real ocorre na abertura. **[F]/[S]**
3. **O mercado entrou na eleição com risco de evento muito alto já precificado.** A vol implícita de 1 mês do EWZ estava em **~46%**, perto da máxima em 4 anos. A vol realizada estava em ~24%, e o spread implícita–realizada era o maior em 8 anos. O *open interest* em calls de EWZ chegou a **~US$ 20 bi** no início de setembro, o maior desde 2007 [14]. **[S] [NÃO VERIFICADO]**: a fonte (blog OptionBeast) foi relida e diz exatamente isso, mas não houve confirmação independente (dados de opções da Cboe/OCC não acessíveis nesta sessão). Para um livro com vol-alvo de 5%, isso significa que **modelos de risco baseados só em covariância histórica subestimam o risco do Brasil até 26/out**. **[I]**
4. **Brasil macro:**
   - Selic em **13,75%** depois do 5º corte seguido de 25 bp (16/set, unânime). O Copom manteve a porta aberta, mas pediu "serenidade e cautela" [17].
   - **Não há Copom em outubro.** As próximas reuniões são em **3–4/nov** e **8–9/dez** [20].
   - IPCA de agosto: −0,32% m/m e 4,22% em 12 meses (bônus de Itaipu) [21]. IPCA-15 de setembro: **+0,70%**, com 4,47% em 12 meses, perto do teto de 4,5% [22].
   - Dívida bruta: **82,9% do PIB** em agosto (SGS 13762: 82,86%), o maior nível desde **mar/2021** (85,1%) [23][104].
   - O dólar fechou a sexta perto de **R$ 5,21–5,22** [10][32].
   - **[F]/[S]**
5. **Global: regime "Fed voltando a subir, petróleo a US$ 100".**
   - O FOMC **subiu os juros em 25 bp para 3,75%–4,00%** em 16/set (12–0), a primeira alta desde 2023 [36]. A mediana do *dot plot* aponta mais uma alta em 2026 [38].
   - O payroll de setembro veio fraco (+29 mil, desemprego 4,2%; julho revisado para −10 mil e agosto para +133 mil) [106]. A probabilidade de alta em outubro de ~25–28% (contra 70% uma semana antes) foi publicada **antes** do payroll [40]; a probabilidade pós-payroll **[NÃO VERIFICADO]**.
   - O UST 10y bateu **5,34%** intradiário (01/out), o maior nível desde 2002 [40][108]. O fechamento oficial (Treasury CMT) foi **5,28% na sexta, 02/out**, e 5,29% em 30/set, o maior fechamento desde mai/2002 [105]. O DXY está perto de ~102, a máxima em 17 meses [40][108].
   - O Brent está em **~US$ 101–103** por causa das interrupções em Hormuz [42][10][108]. A alta de **+54%** reportada pelo TE é a variação **em 12 meses**, não no ano (YTD) [42].
   - O VIX está baixo, em 15,31 [41].
   - **[F]/[S]**
6. **Commodities muito dispersas:**
   - **cobre** perto do recorde: LME a US$ 14.253,50/t em 01/out, com recorde de ~US$ 14.860–14.875/t em setembro. Em **Escondida**, as operações pararam em 23/set depois da **morte de um terceirizado**, com retomada gradual a partir do dia seguinte. Os supervisores aprovaram com 95% a autorização de greve, mas a lei exige mediação antes de uma greve legal. **Não há greve em curso confirmada, e a afirmação anterior de "mina parada desde 23/set" estava errada** [46].
   - **minério** fraco: US$ 91,35/t, −8,12% no mês, com Simandou entrando em produção [44][45].
   - **lítio** caindo: −22,5% no mês [48].
   - **petróleo** alto [42].
   - **[F]**
   - Isso torna **essenciais os fatores de sensibilidade a commodities** no modelo de risco. **[I]**
7. **México:**
   - Banxico em **6,50%** (3ª manutenção seguida, 24/set). O banco disse que não precisa reagir "mecanicamente" ao Fed [55][56].
   - O peso teve a **4ª semana seguida de queda**, fechando em **18,16** em 02/out, com mínima intradiária de 18,43, a pior desde nov/2025 [60][61][62].
   - USMCA: em 01/jul os EUA **não renovaram** o acordo, o que abriu o regime de **revisões anuais**. O acordo segue em vigor até 2036 [64].
   - As tarifas da Seção 232 continuam: aço e alumínio a 50%, autos fora do USMCA a 25%. Há negociação de um acordo antes das *midterms* dos EUA (03/nov) [65][66][67].
   - **[F]/[S]**
8. **Chile:**
   - José Antonio Kast é presidente desde **11/mar/2026** [77].
   - O BCCh mantém a TPM em **4,50%** (08/set, unânime) e cortou o PIB 2026 para **0,25%–0,75%** [73][74]. Próxima reunião: **27/out** [75].
   - O desemprego está em 9,6% [76].
   - **[F]/[S]**
9. **Colômbia:**
   - **Abelardo de la Espriella** (direita) tomou posse em 07/ago depois de vencer o 2º turno com 49,66% contra 48,70% [81].
   - O BanRep **subiu os juros** para **12,25%** em 30/set (placar 4–2–1). A inflação está em 6,2% [83][84].
   - A situação fiscal é crítica: déficit de 7,2% do PIB projetado para 2026 e de 9,4%–9,5% no orçamento de 2027 antes do ajuste [85].
   - **[F]**
10. **Peru:** **Keiko Fujimori** tomou posse em 28/jul, depois de vencer com 50,14% contra 49,86% [89]. O BCRP está em 4,25%, parado há 12 reuniões. Próxima reunião: 07/out [91][92]. **[F]/[S]**
11. **Argentina:**
    - O risco-país passou de **600 pb**: estava em 607 pb em 30/set, com alta de 95 pb no mês [96].
    - Os ADRs de bancos caíram de 15% a 18% em setembro [96].
    - O governo anunciou uma "bazuca" de US$ 75 bi para conter o câmbio antes de 2027, mas a credibilidade foi contestada [99].
    - A inflação está em ~1,7% ao mês [101].
    - **[F]/[S]**
12. **Implicação central [I]:** a primeira carteira será montada **dentro de uma janela de evento binário** (o 2º turno no Brasil em 25/out) e num **regime global de juros e dólar em alta**. A recomendação de pesquisa:
    - **(a)** começar na parte baixa da banda de vol;
    - **(b)** medir e limitar explicitamente a exposição ao "fator eleição";
    - **(c)** buscar alfa em **dispersão intra-setor e intra-commodity**, e não em apostas direcionais de país;
    - **(d)** redobrar o cuidado com *short squeeze* em estatais e *small caps* brasileiras e em ADRs argentinos que já caíram muito.

---

## 1. Brasil

### 1.1 Eleições gerais, 1º turno (domingo, 2026-10-04)

**Status de confirmação.** O resultado presidencial está **confirmado na fonte primária**: o JSON oficial de resultados do TSE (eleição 6257, arquivo gerado em 05/10/2026 às 02h59, 100% das seções totalizadas) [103]. Também está confirmado por Wikipedia [1], The Rio Times [2], Bloomberg [4] e CNBC [5], e bate com a cobertura ao vivo da InfoMoney [3]. O Rio Times traz contagens de votos ligeiramente diferentes (56.104.049 e 53.876.219), mas os percentuais são iguais; **usar os números do TSE**. Os números de 22h07 de 04/out (47,50 × 44,61, na InfoMoney) eram **parciais**. Governadores, Senado e Câmara foram re-checados no JSON do TSE (eleição 6259) [103]. A Câmara ainda não tinha status final de eleitos em SP, MG e AM no momento da consulta.

**Presidente** (votos válidos, 100% das seções; TSE [103]):

| Candidato | Partido | % válidos | Votos | Fonte | Evid. |
|---|---|---|---|---|---|
| Flávio Bolsonaro | PL | **47,03%** | 56.104.503 | [103]; [1]; [2] | [F] |
| Luiz Inácio Lula da Silva | PT | **45,16%** | 53.879.538 | [103]; [1]; [2] | [F] |
| Augusto Cury | Avante | 2,89% | 3.448.569 | [103]; [2] | [F] |
| Renan Santos | Missão | 2,24% | 2.675.887 | [103]; [2] | [F] |
| Ronaldo Caiado | PSD | 2,18% | 2.605.148 | [103]; [2] | [F] |
| Romeu Zema | Novo | 0,27% | 326.488 | [103]; [2] | [F] |

- **Comparecimento:** 78,92% (125.275.835 eleitores), abstenção de 21,08% [103][2]. **[F]**
- **2º turno:** **domingo, 2026-10-25**, entre Flávio Bolsonaro e Lula [1][2][5]. **[F]**
- **Surpresa frente às pesquisas:** os últimos Datafolha e Quaest (publicados em 03/out) traziam Lula com 45% e 46% dos válidos e Flávio com 42% e 45% [trecho de busca citando Bloomberg/Wikipedia, [1][4]]. Bloomberg: *"a far better showing than investors were positioned for"* [4]. **[S]**
- **Pesquisas de 2º turno anteriores ao 1º turno** (todas pré-04/out, já defasadas):

| Instituto | Lula | Flávio | Fonte | Evid. |
|---|---|---|---|---|
| Datafolha | 47% (a Forbes Brasil reporta **48%**) | 45% | [14]; [10] | [S] (fontes divergem) |
| AtlasIntel | 47,7% | 47,4% | [14] | [S] |
| Quaest (24–27/set) | 42% | 42% | [12] | [F] |
| BTG/Nexus | 46% | 44% | [12] | [F] |

- **Temas da campanha:** crime, corrupção e a relação com Trump [8]. **[S]**
- **Falas:** Flávio declarou "a era do PT está terminando". Lula reconheceu o resultado "inesperado" [3] e disse ser "muito bom no mata-mata" (trecho do Observador, PT). **[F]/[S]**

**Congresso** (TSE [103], ainda incompleto na consulta):
- **Câmara:** o Rio Times diz que o PL elegeu **121** de 513 deputados [2]. **[NÃO VERIFICADO]**: no JSON do TSE, o PL tinha **79 eleitos em 24 UFs**, e SP (70 cadeiras), MG (53) e AM (8) ainda estavam sem status de eleitos. O total de 121 é plausível, mas não foi confirmado.
- **Senado:** 54 das 81 cadeiras estavam em disputa. O número de **16** senadores do PL (InfoMoney, 22h07 [3]) era **parcial**. No JSON do TSE, com 52 das 54 vagas definidas (faltava AM), o **PL elegeu 19 senadores**, seguido por PT (6) e MDB (6) [103]. **[F]** O Rio Times projeta o PL com **28 de 81** cadeiras no total [2]. **[NÃO VERIFICADO]** Michelle Bolsonaro (29,05%) e Bia Kicis (27,44%), ambas do PL, foram eleitas pelo DF [103][3]. **[F]**
- **Leitura de mercado:** uma "onda de direita garantiu bancadas de peso no Congresso capazes de aprovar medidas de corte de gastos" [9]. **[F]**

**Governadores** (TSE, final, 100% das seções [103]; os números de 22h07 da InfoMoney [3] eram parciais). Foram **20 estados decididos no 1º turno e 7 com 2º turno**, como diz o Rio Times [2]:

| Estado | Resultado | Evid. |
|---|---|---|
| São Paulo | **Tarcísio de Freitas** (Republicanos), reeleito com **62,65%** (InfoMoney parcial: 62,85%) | [F] [103] |
| Minas Gerais | Cleitinho Azevedo (Republicanos), 55,40% | [F] [103] |
| Rio Grande do Sul | Luciano Zucco (PL), 58,05% | [F] [103] |
| Paraná | Sergio Moro (PL), 50,10% | [F] [103] |
| Santa Catarina | Jorginho Mello (PL), 68,98% | [F] [103] |
| Bahia | Jerônimo Rodrigues (PT), 55,80% | [F] [103] |
| Ceará | Elmano de Freitas (PT), 53,19% | [F] [103] |
| Pernambuco | Raquel Lyra (PSD), 53,27% | [F] [103] |
| **Rio de Janeiro (2º turno)** | Douglas Ruas (PL, **49,27%**) × Eduardo Paes (PSD, **42,76%**) | [F] [103] |
| **DF (2º turno)** | Celina Leão (PP, 49,93%) × Leandro Grass (PT, **34,47%**) | [F] [103] |
| **Outros 2º turnos** | ES: Pazolini (Republicanos, 49,65%) × Ferraço (MDB, 34,06%). RN: Allyson (União, 36,94%) × Cadu de Lula (PT, 36,16%). AC: Mailza Assis (PP, 49,76%) × Alan Rick (Republicanos, 32,27%). TO: Professora Dorinha (União, 45,52%) × Vicentinho Júnior (PSDB, 43,94%). **AM**: Omar Aziz (PSD, 40,63%) × Professora Maria do Carmo (PL, 24,49%), ainda sem status oficial no TSE, mas sem maioria absoluta. | [F] [103] |

### 1.2 Mercado na véspera e reação esperada

**Fechamento de sexta, 2026-10-02:**
- **Ibovespa** em **192.114,55 pts (+2,63%)**, o maior fechamento desde 22/abr (192.888,96) [10][11][108]. **[F]**
  - Volume de R$ 43,7 bi [10]. **[F]**
  - Na semana, as fontes divergem: +4,71% [11] contra +5,81% [10]. O script de verificação, rodado sobre a série de fechamentos do Yahoo Finance (25/set: 183.477; 02/out: 192.115), reproduz **+4,71%**, então o número da Forbes parece errado [108]. Mesmo assim, o FactBook deve recalcular o valor pela camada de dados.
- **Dólar à vista** entre **R$ 5,2165 e R$ 5,2173**, dependendo da fonte [10][11]. Em 28/set o dólar havia batido R$ 5,2264, a máxima em 6 meses [12]. Em 05/out, o TradingEconomics mostra R$ 5,2139 [32]. **[F]**
- **ADRs:** PBR em US$ 21,65 (+3,19%), VALE em US$ 13,76 (+2,30%), EWZ em US$ 38,19 (+2,83%) [15][16]. **[F]**
- **Petrobras** subiu 2,81% (PN) e 3,25% (ON) com uma nova descoberta em águas profundas [10]. **[F]**
- **Bancos:** Bradesco PN +3,64%, BB ON +3,04%, Itaú PN +1,54% [10]. **[F]**
- **Setembro:** o Ibovespa fechou o mês em 186.340 pts, com alta de ~5% segundo a Nord [13]. A InfoMoney reportou +3,14% no mês e +13,57% no ano em 28/set [12]. A divergência é só de data: o script de verificação sobre a série do Yahoo Finance reproduz os dois números (+3,14% até 28/set e cerca de +5,0% até 30/set) [108]. O FactBook deve recalcular. **[F]**
- **Em 30/set**, o SMLL subiu 1,93%, e Itaú, BB e Bradesco subiram entre 4,1% e 4,7%. A Nord chamou o movimento de "trade eleitoral", ou seja, de posicionamento para uma vitória da oposição [13]. **[F]**

**Reação ao resultado** (noite de domingo e pré-abertura de segunda):
- **EWZ overnight:** +8,72% (US$ 41,52) [9] e +10,29% (US$ 42,12) [2], em horários diferentes. Os dois números são coerentes com o fechamento de US$ 38,19. Na madrugada de segunda, o Yahoo Finance mostrava o EWZ em ~US$ 42,66–42,74 (+11,6% a +11,9%) e a PBR em ~US$ 24,00 (+10,9%) no pregão estendido. São retratos de horários diferentes e de liquidez fina [108]. **ADRs no aftermarket:** PBR +5,08%, VALE +5% [3]. **[F]/[S]**
- **Bloomberg:** *"Brazilian assets are set to jump"*, com rali esperado em bolsa, real e juros [4]. **[S]**
- **ASA (Felipe Balassiano):** "Esperamos alta forte da bolsa, valorização do real e fechamento dos juros nominais e reais" [9]. **[F]**
- **Lógica do mercado:** o mercado aposta que Flávio herdará os votos de Cury, Renan Santos, Zema e Caiado e fará do ajuste fiscal uma prioridade [9]. **[F]** Isso é uma **expectativa**, não um fato sobre o 2º turno. **[I]**
- **Opções:** o EWZ tinha vol implícita de 1 mês de ~46% contra realizada de ~24%. As calls fora do dinheiro mais negociadas são as de *strike* US$ 43 e US$ 45, com vencimento em 20/nov (~1,37 mi de contratos) [14]. **[S] [NÃO VERIFICADO]**: confere com a fonte, mas a fonte é única (blog), sem confirmação independente.

**Cenários de valuation publicados** (pré-eleição, por regime fiscal e não por candidato) [29], todos **[F]**:

| Casa | Cenário adverso | Cenário positivo |
|---|---|---|
| Itaú BBA | juro real de 8,5%; P/L do Ibovespa de 7,3x | juro real de 5%; P/L de 11,5x |
| XP | ~165,6 mil pts (juro real de 8,5%) | ~248,4 mil pts (juro real de 6%); cenário-base de ~201 mil pts |
| Bradesco BBI (MSCI Brazil) | −44% sem reformas | +76% com reformas; +25% com consolidação fiscal |

### 1.3 Política econômica em disputa

- **Plano de Flávio Bolsonaro** (Gazeta do Povo, 18/ago [26]):
  - substituir o arcabouço fiscal por uma regra de "estabilização e posterior redução da dívida", com superávits primários e limites ao crédito subsidiado, ainda sem detalhamento;
  - reforma administrativa, com a eliminação de "pelo menos dez ministérios";
  - revisão da reforma tributária, com IVA menor;
  - retomada do Programa Nacional de Desestatização, "caso a caso".
  - **[F]**
- **Coordenação econômica:** Daniella Marques (16/set) [27]:
  - propõe uma PEC de contenção de gastos envolvendo os três Poderes;
  - colocou o **Banco do Brasil** entre as estatais que **poderiam ser privatizadas**, com o argumento de que o banco "negocia abaixo de uma vez seu patrimônio";
  - **excluiu a Caixa** da lista;
  - diz que mais de 20 estatais dependem do Tesouro.
  - **[F]**
  - A Petrobras **não** foi citada nos documentos lidos. **[F]**
- **Lula:** a hipótese de trabalho é a continuidade do arcabouço vigente (LC 200/2023) e da política atual das estatais. O programa de Lula **não foi pesquisado em profundidade** nesta sessão. **[I]**

### 1.4 Fiscal

- **Dívida bruta do governo geral:** **82,9% do PIB** em agosto (R$ 11,1 tri [NÃO VERIFICADO]), o maior nível desde **mar/2021** (85,1%), com alta de 0,3 p.p. no mês, puxada pelos juros nominais [23]. A série SGS 13762 do BCB confirma **82,86%** em agosto, contra 82,56% em julho [104]. **[F]** A CNBC (03/out) citou 81,9% "desde que Lula assumiu" [6], um número de outra data ou base. **[S]**
- **Primário consolidado de agosto:** déficit de R$ 10 bi, melhor que o consenso Reuters de −R$ 15,7 bi [23]. **[S]**
- **Arcabouço (LC 200/2023):**
  - meta de **superávit de 0,25% do PIB em 2026**, com banda de ±0,25 p.p. [24];
  - o PLOA 2027 prevê meta de **0,5% do PIB (R$ 73,2 bi)** [24]. A Times Brasil reporta superávit de R$ 18,6 bi **com exclusões** de despesas da meta [25];
  - a despesa no PLOA 2027 está limitada a 0,6% acima da inflação.
  - **[S]**
- **Leitura [I]:** o mercado precifica o regime fiscal de 2027–2030. Um Congresso mais à direita reduz o risco de cauda fiscal **qualquer que seja** o vencedor, mas não o elimina. O 2º turno decide a direção do Executivo, como regra fiscal nova e privatizações.

### 1.5 Política monetária

- **Selic em 13,75%.** Corte de 25 bp em **16/set/2026**, unânime, o **5º corte seguido** de 25 bp desde **mar/2026**, somando 1,25 p.p. no ciclo (de 15,00% para 13,75%) [17][104]. **[F]**
- **Comunicado:** "A continuidade do ciclo de calibração [...] fica dependente da evolução do cenário". O texto fala em "significativo aumento da incerteza, desancoragem das expectativas e riscos elevados", que "demanda serenidade e cautela" [17]. **[F]**
- **Ata (22/set):**
  - projeções de IPCA do Copom: **5,2% para 2026** (antes 5,1%) e **3,9% para 2027** (antes 3,8%), segundo a InfoMoney [18]. **[F]**
  - O Itaú lê que o BC "mantém em aberto" os próximos passos [18]. **[F]**
  - As projeções de economistas para a Selic no fim de 2026 vão de 13,00% a 13,75% [18]. **[F]**
- **Focus (28/set):** Selic de **13,50%** no fim de 2026, **12,00%** no fim de 2027 e 10,50% no fim de 2028 [19]. Os dados de IPCA do Focus de 04/set (5,00% para 2026, câmbio de R$ 5,20) vêm só de trecho de busca. **[F]/[S]**
- **Calendário do Copom 2026:** 27–28/jan, 17–18/mar, 28–29/abr, 16–17/jun, 4–5/ago, 15–16/set, **3–4/nov** e **8–9/dez** [20]. **Não há reunião em outubro.** A série SGS 432 (Selic meta) do BCB mostra as mudanças em vigor em 19/mar, 30/abr, 18/jun, 06/ago e 17/set, o dia seguinte a cada reunião listada. A Selic de 13,75% aparece vigente até 04/nov, o que confirma a reunião de 3–4/nov e a ausência de reunião em outubro [104]. **[F]** A data de 8–9/dez não foi confirmada em fonte primária. **[S]**
- **Atividade:** PIB do 2T26 de **+0,5% t/t** (1T26: +1,1%). Consumo das famílias de **−0,4%**. Inadimplência de **4,9%**, recorde [17]. **[F]**

### 1.6 Inflação

- **IPCA de agosto/2026:** **−0,32% m/m**. Em 12 meses, caiu de 4,44% para **4,22%** (confirmado nas séries SGS 433 e 13522 do BCB [104]). No ano, **3,11%**. A deflação veio do **bônus de Itaipu** na energia: administrados −1,25%, livres +0,02% [21]. **[F]** para m/m e 12 meses; **[S]** para o resto.
- **IPCA-15 de setembro/2026:** **+0,70% m/m**, acima do consenso de 0,53%. Em 12 meses, **4,47%**. Alimentação subiu 1,51% e habitação 2,07% [22]. O m/m está confirmado na série SGS 7478 do BCB, e o script de verificação reproduz os 4,47% em 12 meses a partir da mesma série [104]. **[F]** para m/m e 12 meses; **[S]** para consenso e grupos.
- **Meta:** contínua de **3,0% com tolerância de ±1,5 p.p.**, ou seja, teto de 4,5% [22]. **[S]**
- **Leitura [I]:** a reversão do bônus de Itaipu e o petróleo a ~US$ 100 pressionam o IPCA de setembro, que sai em 09/out. Isso limita os cortes de juros no curto prazo e explica um Copom cauteloso.

### 1.7 Câmbio

- **USD/BRL:** R$ 5,2139 em 05/out, com −1,86% no ano e o real perto da mínima de 6 meses na semana anterior, segundo o TradingEconomics [32]. A Forbes reporta o dólar com **−4,95% no ano** até 02/out [10]. As bases diferem, e o número deve ser recalculado pela camada de dados. **[F]**
- **Reação esperada [I]:** com uma vitória de Flávio vista como mais provável, o real tende a se apreciar e a curva de juros a fechar no curto prazo [9]. Uma reversão é possível se as pesquisas de 2º turno mostrarem Lula à frente.

### 1.8 Implicações setoriais no Brasil

| Setor / nomes | O que dizem as fontes | Leitura para L/S [I] |
|---|---|---|
| **Petrobras** (PETR3/PETR4; ADRs PBR e PBR-A) | PETR4 com **+70,33% no ano** e +9,06% em setembro [30]. Está na cesta "Challenger" do Bradesco BBI [28] e na lista de "proteção em deterioração fiscal" [29]. Para analistas, "a eleição importa muito, mas disputa espaço com [...] o preço do petróleo" [30]. Nova descoberta em águas profundas [10]. | Nome com **momentum e crowding** muito altos e beta duplo (petróleo e eleição). Num livro neutro, o beta ao petróleo precisa de hedge. Há risco de reversão de momentum depois do evento. |
| **Banco do Brasil** (BBAS3) | Possível privatização mencionada pela equipe de Flávio [27]. "Reagiu mais claramente ao componente eleitoral" [30]. **+11,62% em setembro**, +6,58% no ano [30]. Subiu nos 4 ciclos eleitorais de 2010 a 2022 [30]. Está na cesta Challenger [28]. | Provavelmente o **maior beta eleitoral individual** entre as large caps. Exposição binária em 25/out. O ADR (BDORY) é OTC e de baixa liquidez, então o local é preferível. |
| **Axia Energia (ex-Eletrobras)** | Privatizada em 2022. O governo tem ~39,14% e golden share. Foi renomeada Axia Energia em 2025 [31]. Perdeu lugar para a Sabesp nas carteiras recomendadas de outubro [35]. | Menor beta eleitoral que o BB. Exposição maior a juros reais e preço de energia. Os tickers da B3 após a renomeação devem ser confirmados no cadastro de securities (historicamente ELET3/ELET6; ADR EBR) **[K]**. |
| **Sabesp** (SBSP3; SBS) | Privatizada em 2024 **[K]**. Tarcísio foi reeleito em SP com 62,65% [103]. Está na cesta "All-Weather" do BBI [28] e entre os beneficiados por um fiscal positivo [29]. É uma das ações mais recomendadas de outubro [35]. | Continuidade regulatória em SP reduz o risco idiossincrático. Ação sensível a juros reais. Sozinha, não é uma aposta eleitoral federal. |
| **Bancos privados** (Itaú, Bradesco, BTG, Nu, Inter) | Itaú está nas cestas Incumbent e All-Weather do BBI [28]. Os bancos subiram de 4% a 5% em 30/set [13]. | Itaú é o "*hedge* de qualidade" contra o BB num par que neutraliza o setor. Os bancos médios têm beta alto à curva. |
| **Utilities e *bond proxies*** (CPFL, Equatorial, Taesa, Copasa) | Estão na cesta "Incumbent" do BBI, a de continuidade do governo [28]. | São sensíveis a juros reais. Num cenário de vitória de Flávio, o fechamento de juros também ajuda esses nomes, então a sensibilidade eleitoral líquida é ambígua. |
| **Consumo doméstico, juros e *small caps*** (MRV, Grupo Mateus, Vamos, Hypera, RD Saúde, Petz/Cobasi) | Estão na cesta Challenger [28]. SMLL +1,93% em 30/set [13]. Consumo das famílias de −0,4% no 2T e inadimplência recorde [17]. | Têm alto beta à curva de juros. Há **risco de squeeze** nos shorts de *small caps* com alta taxa de aluguel durante o rali eleitoral. |
| **Exportadoras** (Suzano, Gerdau, WEG, Aura, Embraer, Vale) | Suzano, Gerdau, WEG e Aura estão na lista de "proteção em deterioração fiscal" [29]. O minério caiu −8,12% no mês [44]. Vale cortou o guidance de produção de 2026 para 335–345 Mt [45]. | Funcionam como *hedge* natural do fator BRL. Um real apreciado pós-eleição as prejudica em termos relativos. A Vale tem vento contrário próprio (minério e Simandou). |
| **Mercado de capitais** (B3, XP) | Estão na cesta Challenger [28]. | Têm alto beta a volume e a fluxo estrangeiro. |

---

## 2. México

### 2.1 Política monetária e inflação

- **Banxico em 6,50%**, mantida em **24/set/2026** por unanimidade, a **3ª manutenção seguida** depois de 25/jun e 06/ago [55][56]. **[F]**
  - O ciclo de 2026 teve manutenção em 7,00% (05/fev), cortes de 25 bp em 26/mar e 07/mai, e depois manutenção [55]. **[F]**
- **Comunicado** [56], **[F]**:
  - a inflação geral subiu de **3,10% para 3,42%** entre a 1ª quinzena de julho e a 1ª quinzena de setembro, por causa da não subjacente;
  - a subjacente **caiu de 3,95% para 3,79%**;
  - o banco cita a "ausência de pressões de demanda" e diz que a política monetária **não teria que reagir de forma mecânica** às altas do Fed.
- **Próxima decisão:** **05/nov/2026** [58]. **[S]**
- **PIB do 2T26:** +1,4% t/t e +2,1% a/a, segundo a prévia do INEGI de 30/jul [63]. **[S]**
- **Leitura [I]:** o diferencial de juros entre México e EUA está **encolhendo** (Banxico parado, Fed subindo), o que enfraquece o *carry* em MXN [59]. Isso é coerente com o peso fraco.

### 2.2 Câmbio e bolsa

- **USD/MXN:**
  - **18,1637** no fechamento de 02/out, segundo referência do Banxico [62]. Um ganho de 0,71% no dia, mas **−2,58% na semana** e a **4ª semana seguida de depreciação** [60]. **[F]** Na releitura, El CEO [60] confirma, e o fechamento oficial anterior de 18,2928, reportado pela N+ [61], é coerente com a alta de 0,71% do peso no dia.
  - Mínima intradiária de 18,4330, a pior desde nov/2025, com o DXY na máxima de 17 meses [61]. **[F]**
  - O TradingEconomics mostra 18,1638 em 05/out e o peso com **−7,36% no mês** [59]. **[F]**
  - O peso estava em 17,15 em 17/set [66]. **[F]**
- **S&P/BMV IPC:** **64.531,68 (+1,10%)** em 02/out, com −0,71% na semana [70]. **[F]**: nível confirmado na série ^MXX do Yahoo, e o script de verificação reproduz as variações de +1,10% e −0,71% [108].
  - O acumulado no ano é **controverso**: +4,28% segundo a EBC, sem data clara [71], e +12,17% segundo o Rio Times [63b]. **Não usar nenhum dos dois.**
  - A favor da faixa mais baixa: o **EWW (em USD) tinha +2,13% no ano em 01/out**, segundo a iShares [53]. Este é o número oficial mais confiável. **[F]**

### 2.3 Comércio: USMCA e tarifas

- **Revisão conjunta de 01/jul/2026:** os EUA **não concordaram em renovar** o USMCA "na forma atual". México e Canadá apoiaram a prorrogação por mais 16 anos. Isso aciona **revisões anuais** (art. 34.7). O acordo **continua em vigor**, com prazo até 01/jul/2036, e todos os direitos (tarifas preferenciais, regras de origem, solução de controvérsias) continuam operando [64]. **[S]**
- **Rodadas bilaterais EUA–México:**
  - a 1ª foi em 16/mar;
  - a 3ª, em julho, terminou sem acordo sobre regras de origem automotivas e a Seção 232 [65];
  - Trump e Sheinbaum falaram por telefone em 16/set ("construtivo");
  - a **4ª rodada foi em 28–29/set, em Washington** [66].
  - **[F]**
- **Pontos de conflito** [65][66], **[F]**:
  - os EUA pedem **50% de conteúdo especificamente norte-americano** nos veículos, contra a regra regional atual de 75%;
  - há uma exigência trabalhista de 40% da produção a ≥ US$ 16/h;
  - na energia, há disputa sobre o acesso ao mercado elétrico. O México defende a prioridade da CFE, com mínimo estatal de 54%.
- **Tarifas vigentes:** **50%** sobre aço e alumínio (Seção 232) e **25%** sobre autos e autopeças não conformes ao USMCA. **[F]** O México teria proposto **5%–10%** para veículos norte-americanos sem conformidade total. **[NÃO VERIFICADO]**: o dado não aparece em [65] nem em [66] na releitura.
- **Bloomberg (30/set):** o México está "cada vez mais confiante" num acordo para cortar as tarifas sobre aço, alumínio e veículos leves. Os dois lados querem um *framework* **antes das *midterms* dos EUA (03/nov)** [67]. **[S] [NÃO VERIFICADO]**: a página da Bloomberg retornou 403 e não houve fonte independente acessível.

### 2.4 Reforma judicial e Estado de Direito

- A reforma judicial foi promulgada em 15/set/2024 [69]. A eleição judicial de **01/jun/2025** teve **comparecimento de ~13%**, o menor da história democrática do México, e mais de 20% de votos nulos ou brancos. O Morena passou a ter **controle dominante** das cortes federais, incluindo as 9 cadeiras da Suprema Corte [68]. **[F]**
- **Leitura [I]:** há um prêmio de risco institucional persistente para setores regulados e de concessões (telecom, energia, mineração, aeroportos) e para disputas tributárias. A Seção 232 e o USMCA dominam o fluxo de notícias de curto prazo. A reforma judicial é um risco de cauda lento, sem catalisador datado em outubro.

### 2.5 Nearshoring e setores

- **Leitura [I]** (nossas inferências, sem números verificados nesta sessão):
  - **Exportadores e empresas com receita em USD** (Grupo México/Southern Copper, Cemex com operação nos EUA, Gruma com receita nos EUA, aeroportos com tarifas indexadas ao USD) se beneficiam do peso fraco. **[K]/[I]**
  - **Consumo doméstico** (Walmex, FEMSA) é defensivo, mas exposto à desaceleração e aos múltiplos. **[I]**
  - **FIBRAs industriais e Vesta** (ADR VTMX) e **siderurgia/autopeças** (Ternium, Nemak) são os nomes mais sensíveis a um acordo da Seção 232. Nemak tem liquidez baixa. **[I]**
  - No pregão de 01/out, GAP caiu 3,39%, Grupo México subiu 0,35% e GFNorte subiu 1,18%, segundo o Rio Times [63b], de confiabilidade moderada. **[S]**

---

## 3. Chile

- **Governo:**
  - **José Antonio Kast** tomou posse em **11/mar/2026**, depois de vencer em dez/2025 com 58%. O mandato vai até mar/2030. O ministro da Fazenda é **Jorge Quiroz** [77]. **[F]**
  - Aprovação: 57% no início, 42% em abril, 34% em junho e 35%–40% em agosto [77]. **[F]**
  - Medidas: corte de 3% nos orçamentos ministeriais (~US$ 6 bi), mudança no MEPCO (estabilização de combustíveis) e congelamento de tarifas de transporte em Santiago até dez/2026 [77]. **[F]**
- **Reforma "Reconstrução Nacional":** aprovada pelo Congresso em **04/ago/2026**. Reduz o **IR corporativo de 27% para 23% até 2029** (25,5% em 2027, 24% em 2028). Fonte: trecho de busca de cobertura do Rio Times, URL exata não confirmada. **[S] [NÃO VERIFICADO]**: a página da Wikipedia sobre o governo Kast [77] não menciona a reforma.
- **Orçamento 2027** (enviado em 30/set): gasto **+1,5%** sobre 2026, "a menor alta em pelo menos duas décadas", fora a pandemia. São mais de 90 tri de pesos (~US$ 92,5 bi a CLP 972,53) [78]. **[F]**
- **BCCh:**
  - **TPM em 4,50%**, mantida em **08/set/2026** por unanimidade [73][75]. **[S]/[F]** Na releitura, o TE confirma o dado. O comunicado do BCCh bloqueou a leitura automatizada.
  - O IPoM de setembro cortou o PIB 2026 de 1,0%–1,75% para **0,25%–0,75%**. A inflação ficaria um pouco acima de 4% no fim de 2026 e convergiria a 3% no 2T27 [74]. **[S]**
  - IPC de agosto: **4,1%**, com subjacente de **3,3%** [75]. **[F]**
  - **Próxima RPM: 27/out/2026** [75]. **[S]**
- **Atividade e câmbio:** desemprego de **9,6%** em agosto. **USD/CLP 979,51** em 05/out, com o peso chileno −4,81% no mês [76]. **[F]**
- **Cobre:**
  - o LME 3M bateu recorde em setembro: **~US$ 14.858,50/t em 10/set** (trecho de busca) ou US$ 14.875/t (Copper Weekly) [46]. O COMEX bateu **US$ 6,83/lb em 22/set** [46];
  - o LME fechou em **US$ 14.253,50/t em 01/out**, ~4% abaixo do recorde. Subiu ~30% em 12 meses e mais de 4% no 3T [46];
  - o TradingEconomics mostra **US$ 6,55/lb** em 05/out [47]. A variação de **+30,6%–30,9%** que o TE reporta é **em 12 meses ("yearly")**, não no ano. Pela série COMEX front-month do Yahoo (HG=F; 31/12/2025: US$ 5,63/lb), a alta YTD é bem menor, perto de +17% segundo o script de verificação [108]. O FactBook deve recalcular.
  - **[F]**
- **Oferta de cobre:**
  - **CORRIGIDO:** a **Escondida (BHP)**, maior mina do mundo, parou as operações em 23/set depois da **morte de um terceirizado** e iniciou uma **retomada gradual no dia seguinte**. Os supervisores votaram com 95% pela **autorização** de greve, mas a mediação obrigatória vem antes de qualquer greve legal [46]. Não há greve em curso confirmada;
  - os trabalhadores de Centinela (Antofagasta) também votaram greve, e a produção chilena está no menor nível desde fev/2011 [47];
  - a Cochilco projeta produção chilena de 5,27 Mt em 2026 (−2,6%) [trecho em 46/47].
  - **[F]**
- **Tarifa e estoques:** o prazo da tarifa americana sobre cobre refinado passou em 28/set **sem decisão**, e o prêmio COMEX–LME praticamente sumiu. Os estoques na COMEX estão em ~700 mil t [46]. **[F]**
- **Lítio:** carbonato a **122.800 CNY/t** em 30/set, **−22,52% no mês** e +66,96% no ano. Fatores: a SMM elevou os estoques chineses em 175 mil t, minas australianas foram reabertas, e as licenças da mina Jianxiawo da CATL (~4% da oferta global) foram revogadas [48]. **[F]**
- **Leitura [I]:** o Chile tem atividade fraca, BC parado e alívio tributário corporativo pela frente. Bancos e varejo dependem do ciclo doméstico. O cobre é um *driver* de país, mas os produtores listados no Chile são poucos (Codelco é estatal e não listada). Para cobre, os veículos líquidos são SCCO e Grupo México. Para lítio, o veículo é SQM.

---

## 4. Colômbia

- **Eleição presidencial de 2026** [81], **[F]**:
  - 1º turno (31/mai): De la Espriella 43,75%, Cepeda 40,90%, Paloma Valencia 6,92% e Fajardo 4,26%;
  - **2º turno (21/jun): Abelardo de la Espriella com 49,66% contra Iván Cepeda com 48,70%**;
  - o vice é José Manuel Restrepo. A posse foi em **07/ago/2026**, para mandato até 07/ago/2030;
  - comparecimento de 63,60% no 2º turno.
- **Agenda:**
  - a campanha propunha estabilizar o déficit em **4,8% do PIB em 360 dias** e levá-lo abaixo de **3,5% até 2030**, com crescimento de 5% [86]. **[S]**
  - Apoio à **expansão de carvão e petróleo**, em contraste com o governo Petro [87]. **[F]**
  - O ministro da Fazenda é **Miguel Gómez** [83]. **[F]**
- **Fiscal** [85], **[F]**:
  - o **Orçamento (PGN) 2027 de COP 634,9 tri** (~US$ 206,7 bi, 29,9% do PIB) foi **reapresentado em 29/ago**, depois que o Congresso devolveu a versão inicial de COP 575,6 tri. Prevê **déficit de 9,4%–9,5% do PIB**, financiado por dívida. O déficit projetado para **2026 é de 7,2% do PIB**. **CORRIGIDO:** a fonte **não** confirma a aprovação final pelo Congresso (o prazo legal costuma ser 20/out) **[NÃO VERIFICADO]**;
  - o presidente do comitê da regra fiscal estima que seria preciso um **ajuste de ~4 p.p. do PIB em 12 a 18 meses** para voltar à regra em 2028;
  - o governo prepara uma "Ley de Rescate" (tributária e de gastos) para levar 2027 a ~7,2% (trecho de busca).
- **BanRep:**
  - **alta surpresa de 25 bp para 12,25% em 30/set/2026**, a primeira decisão sob o novo governo. Placar: **4 votos pela alta, 2 pela manutenção e 1 por +50 bp** [83][84]. **[F]**
  - IPC de agosto em **6,2%** (6,24% no TradingEconomics), subjacente em 6,1% e serviços em 7,2% [83]. **[F]**
  - A expectativa de mercado é 6,8% no fim de 2026 [83]. **[F]**
  - PIB do 2T de +3,4% a/a e desemprego urbano de 9,1% [83][84]. **[F]**
  - **Próxima reunião: 30/out/2026** [84]. **[S]**
- **Câmbio:** **USD/COP 3.308,89** em 05/out, com o peso colombiano −6,11% no mês e +14,26% de apreciação em 12 meses [87]. **[F]** O texto narrativo do TradingEconomics é internamente inconsistente e não deve ser usado.
- **Leitura [I]:** a combinação de governo pró-mercado e pró-petróleo, Brent a ~US$ 100, BC subindo juros e fiscal muito frágil cria uma **assimetria**. Ecopetrol (EC) se beneficia do petróleo e da agenda pró-exploração, mas corre risco de extração de dividendos pelo Tesouro. Bancolombia (CIB) ganha margem com a alta de juros, mas tem risco de crédito com desemprego de ~9%.

---

## 5. Peru

- **Eleições de 2026** [89], **[F]**:
  - 1º turno (12/abr): Keiko Fujimori 17,19%, Roberto Sánchez 12,03% e López-Aliaga 11,91%;
  - **2º turno (07/jun): Keiko Fujimori (Fuerza Popular) com 50,14% contra Roberto Sánchez (Juntos por el Perú) com 49,86%**, uma diferença de 49.641 votos (9.223.396 × 9.173.755). A Wikipedia em inglês [110] arredonda para **50,13% × 49,87%**, que é o que os votos implicam (50,135%). A diferença é só de arredondamento;
  - proclamação pelo JNE em 03/jul [90]. **Posse em 28/jul/2026**. Keiko é a primeira mulher eleita presidente.
- **Congresso bicameral:** Fuerza Popular tem 22 de 60 senadores e 41 de 130 deputados. Juntos por el Perú tem 14 e 32 [89]. **[F]** Isso é um risco de governabilidade com maioria apertada. **[I]**
- **Gabinete e BC:**
  - o ministro da Economia é **Elmer Cuba** desde 28/jul (trecho da Wikipedia) [95]. **[S]**
  - O governo **ratificou Julio Velarde** no comando do BCRP [93]. **[S]**
  - Avalia eliminar a **lei de tetos de juros** [94], o que seria positivo para os bancos se aprovado. **[S]/[I]**
- **BCRP:**
  - **4,25%**, mantida em **10/set/2026**, a **12ª manutenção seguida** desde set/2025 [91][92]. **[F]/[S]**
  - IPC de agosto em **4,4% a/a**, por efeito-base. A subjacente sem transporte está em 1,8%, e a expectativa de 12 meses em 3,1% [92]. **[F]**
  - O banco cita o **risco de El Niño** [92]. **[F]**
  - **Próxima decisão: 07/out/2026** [92]. **[S]**
- **Leitura [I]:** Credicorp (BAP), Southern Copper (SCCO), Buenaventura (BVN) e Intercorp (IFS) são os veículos líquidos. Os termos de troca seguem favoráveis com o cobre alto [91].

---

## 6. Argentina

- **Risco-país:** **607 pb em 30/set**, com +95 pb no mês (+18,6%) e +36 pb no ano. É a primeira vez acima de 600 pb desde 07/abr [96]. **[F]**
  - O índice subiu de 485 pb (11/set) para 611 pb, a máxima em 5 meses [97][100]. **[S]**
  - Em 23/set havia **8 quedas seguidas** dos bonds soberanos. Os fatores apontados foram o UST 10y em 5,1%, o Brent em US$ 103,70 e a aversão a risco em EM [98]. **[F]**
- **Câmbio** (30/set) [96], **[F]**:
  - **mayorista em ARS 1.517**, com +0,6% no mês e máxima do ano de 1.525,50 em 25/set;
  - **MEP em 1.542,56** e **CCL em 1.616,44**;
  - o **teto da banda está em 1.919,40**. Outra fonte cita 1.910,11 [100] e diz que o mayorista estava ~26% abaixo do teto. **[S]**
- **Reservas:** as brutas estavam em **US$ 48,933 bi em 23/set**. O BCRA comprou só US$ 6 mi naquele dia [98]. **[F]** As reservas líquidas, descontado o FMI, estão **negativas em ~US$ 3 bi** [100], ou em −US$ 3,9 bi, segundo a EcoGo [99]. **[S]/[F]**
- **"Bazuca" de US$ 75 bi** (anunciada por Milei e Caputo, reportada em 03/out) [99], **[F]**:
  - composição: US$ 20 bi de compras de reservas, US$ 20 bi de swap com os EUA, US$ 20 bi de swap com a China e US$ 15 bi em intervenção no mercado futuro;
  - o objetivo é evitar uma corrida cambiária antes das eleições de **2027**;
  - críticas: a EcoGo estima a capacidade efetiva em US$ 25–45 bi. A intervenção em futuros tem teto de US$ 9 bi pelo FMI, e os swaps exigem autorização política.
- **Mercado em setembro** [96], **[F]**:
  - o S&P Merval fechou em 2.819.323 pts. A matéria traz números internamente conflitantes em USD (+1,2% e −8,2%), então **não usar**;
  - **piores do mês:** Supervielle −18,1%, BBVA Argentina −15,3% e Macro −15,1%;
  - bonds: AL35 −7,6%, AL41 −7%.
- **Inflação:** **1,7% m/m em agosto** (julho: 2,1%) e **33,5% a/a**, segundo o TradingEconomics [101]. **[F]** O IPC de setembro sai em **13/out** [102]. **[S]**
- **Leitura [I]:**
  - os ADRs argentinos têm o maior beta a risco global e o maior risco de cauda política da região;
  - **depois de quedas de 15% a 18% nos bancos, shorts nesses ADRs carregam risco elevado de *short squeeze*** com anúncios de apoio externo (swap EUA/China) ou mudanças no regime cambial;
  - nomes de energia com receita em USD (YPF, Vista, Pampa) têm *driver* distinto, ligado ao petróleo e a Vaca Muerta.

---

## 7. Contexto global

| Variável | Nível / evento | Fonte | Evid. |
|---|---|---|---|
| **Fed funds** | **+25 bp para 3,75%–4,00%** em 16/set/2026, voto **12–0**, primeira alta desde 2023. "Inflation remains elevated. Today's policy action will support a timelier return to the Committee's 2 percent goal." | [36] | [F] |
| **Dot plot (set)** | Mediana de **4,1%** no fim de 2026 (+25 bp adicionais) e 4,1% no fim de 2027. 3,9% em 2028 e 3,2% no longo prazo. | [38][107] | [F] (Tabela 1 do SEP) |
| **Presidente do Fed** | **Kevin Warsh**, desde 22/mai/2026. A página do Board lista Warsh como *Chairman*; a data vem só da Wikipedia. | [39][111] | [F] |
| **Próximo FOMC** | **27–28/out/2026**, depois 8–9/dez | [37] | [F] |
| **Payroll de setembro** | +29 mil (consenso +90 mil). Revisões: julho de +21 mil para −10 mil e agosto de +162 mil para +133 mil. Desemprego de 4,2%. | [106][10][40] | [F] (BLS) |
| **Probabilidade de alta em outubro** | ~25%–28% (contra 70% uma semana antes), número **anterior ao payroll** (o artigo é de sexta antes do dado). A probabilidade pós-payroll **[NÃO VERIFICADO]**. | [40] | [F] (pré-payroll) |
| **UST 10y** | Pico intradiário de **5,34%** (01/out), o maior desde 2002 [40][108]. **CORRIGIDO:** o fechamento oficial (Treasury CMT) foi **5,28%** na sexta, 02/out, e não 5,175%. O fechamento de 5,29% em 30/set foi o mais alto desde mai/2002 (5,32%) [105]. A TradingView falava em "near 5.25%" antes do payroll. | [40][105][108] | [F] |
| **DXY** | ~**102,0**, perto da máxima de 17 meses, 3ª semana seguida de alta. EUR/USD em ~1,124 e USD/JPY em ~158. | [40] | [F] |
| **VIX** | **15,31** (02/out) | [41][108] | [F] |
| **Brent** | **US$ 102,25** em 02/out [10][108] e **US$ 100,83** em 05/out, um retrato intradiário do TE (na releitura, US$ 103,07; no Yahoo, ~US$ 101,9–102,3) [42][108]. **CORRIGIDO:** os "+54%" (agora +57,43%) do TE são a variação **em 12 meses**; o TE mostra o mesmo número nos campos YTD e 12 meses. O front-month fechou 2025 em US$ 60,85 (Yahoo BZ=F), então a alta YTD é bem maior. O FactBook deve recalcular. Fatores: interrupções em Hormuz e Bab el-Mandeb, liberação de 100 mi de barris pelo G7, exportações do Golfo de volta ao nível pré-conflito no fim de setembro, OPEP+ com cotas inalteradas. A EIA estimou *shut-ins* de 6,7 mb/d em agosto [43]. | [10][42][43] | [F]/[S] |
| **Minério de ferro (62%)** | **US$ 91,35/t** (02/out), −8,12% no mês e −12,47% em 12 meses. Simandou entrando. Consenso de 2026 em ~US$ 94/t. | [44][45] | [F]/[S] |
| **Cobre** | LME a US$ 14.253,50/t (01/out). COMEX a US$ 6,55/lb (05/out). Recordes em setembro. Ver a seção 3. | [46][47] | [F] |
| **China** | PMI industrial de **50,1** em setembro (agosto: 49,8), a primeira expansão desde junho | [49] | [F] |
| **Fluxos EM (EPFR, início de setembro)** | Fundos de ações EM: +US$ 467 mi na semana (antes +US$ 2,2 bi). LatAm: +US$ 8 mi. **Brasil: +US$ 523 mi.** O Brasil tem **22 gestores líquidos *overweight*** (antes 17). México é *overweight* de consenso. | [50] | [F] |
| **Volatilidade implícita do Brasil** | EWZ 1M em ~46% (máxima em 4 anos) e realizada em ~24% | [14] | [S] [NÃO VERIFICADO] (fonte única: blog) |

**Leitura do regime [I]:**
- O Fed voltou a apertar e o UST 10y está acima de 5%, com o dólar forte. Isso é **vento contrário para moedas e *carry* de EM**, mais evidente no MXN.
- O VIX baixo (~15) contrasta com a vol implícita alta do Brasil. O risco em LatAm é **idiossincrático e de evento**, não sistêmico.
- O choque de oferta de petróleo é um *driver* setorial forte. Neutralizar o beta ao petróleo vai além de neutralizar o setor de energia: atinge aéreas, logística, químicos e consumo.

---

## 8. Desempenho de índices e ETFs

> Números **reportados pelas fontes**. Nenhum foi calculado aqui. As janelas de 1M e 3M **devem ser calculadas pela camada de dados determinística** a partir de séries de preço. Há divergências entre fontes, listadas abaixo.

| Ativo | Nível (data) | 1M | 3M | Ano (YTD) | Fonte | Evid. |
|---|---|---|---|---|---|---|
| **EWZ** (iShares MSCI Brazil) | NAV de US$ 38,1152 (02/out). Mercado a US$ 38,19 (02/out). | n/d | n/d | **+17,76%** (retorno total do NAV, até 01/out). Na releitura, o iShares confirma, e é coerente com os ~+18,0% de retorno ajustado do Yahoo até 01/out. | [51][15][108] | [F] |
| **EWZ, 12 meses** | n/d | n/d | n/d | 1 ano: +25,47% (NAV) | [51] | [F] |
| **EWW** (iShares MSCI Mexico) | NAV de US$ 71,1752 (02/out) | n/d | n/d | **+2,13%** (NAV, até 01/out). Na releitura, o iShares confirma, e o Yahoo dá ~+2,12% ajustado até 01/out. | [53][108] | [F] |
| **ILF** (iShares LatAm 40) | NAV de US$ 34,9952 (02/out). Brasil 56,74%, México 24,15%, Chile 7,35%, Peru 6,89%, Colômbia 2,78%. | n/d | n/d | **+13,87%** (NAV). **CORRIGIDO:** a data provável é **01/out**, e não 02/out. O retorno ajustado do Yahoo dá ~+14,0% até 01/out e ~+16,3% até 02/out, e o iShares mostra o YTD com data D−1 também em EWZ e EWW [108]. | [52][108] | [F] |
| **Ibovespa** | 192.114,55 (02/out) | Setembro: +3,14% [12] ou ~+5% [13] (divergente) | n/d | +13,57% até 28/set [12] | [10][12][13] | [F] |
| **S&P/BMV IPC** | 64.531,68 (02/out) | Semana: −0,71% | n/d | **Divergente**: +4,28% [71] ou +12,17% [63b]. **Os dois parecem errados**: pela série ^MXX do Yahoo (31/12/2025: 64.308,29), o índice está praticamente estável no ano, segundo o script de verificação. Usar a série de preço. | [70][71][108] | [F] (nível) |
| **IPSA** | 10.916,57 (02/out), segundo o Rio Times | n/d | n/d | n/d | [16] | [S] |
| **S&P Merval** | 2.819.323 (30/set) | Setembro: números conflitantes na fonte | n/d | n/d | [96] | [F] (nível) |

- Um artigo da AOL/Yahoo citava o EWZ com ~+26% e o EWW com ~+15% no ano, numa data anterior não identificada. **Esses números foram descartados** porque conflitam com a iShares oficial.

---

## 9. Calendário de eventos, 2026-10-05 a 2026-10-30

> As datas de dados vêm do calendário do TradingEconomics [34][54][72][80][88][102] **[S]**. As datas de bancos centrais vêm de fonte oficial quando indicado. Os feriados estão marcados **[K]** e precisam ser confirmados no calendário de cada bolsa. As datas de balanços do 3T26 **não foram confirmadas** e aparecem como janela histórica **[K]/[I]**.

| Data | País | Evento | Relevância para o livro | Fonte / Evid. |
|---|---|---|---|---|
| **Seg 05/out** | BR | 1º pregão pós-1º turno. Focus. PMI de serviços. | **Gap de abertura e rebalanceamento inaugural** | [4][34] [S] |
| Seg 05/out | US / MX | ISM serviços (US). Investimento fixo e balança fiscal (MX). | Juros e USD | [54][72] [S] |
| Ter 06/out | BR / US | Balança comercial (BR). Balança comercial e ADP (US). | Baixa | [34][54] [S] |
| **Qua 07/out** | US | **Ata do FOMC** (reunião de setembro) | Trajetória do Fed, UST e USD | [54] [S] |
| Qua 07/out | PE | **Decisão do BCRP** (4,25%) | BAP, IFS | [92] [S] |
| Qua 07/out | CO | IPC de setembro | Trajetória do BanRep | [88] [S] |
| Qui 08/out | MX | **INPC de setembro** e **ata do Banxico** | Peso e bancos | [72] [S] |
| Qui 08/out | CL | IPC de setembro | Trajetória do BCCh | [80] [S] |
| Qui 08/out | PE | Feriado (Combate de Angamos): **BVL fechada** | Execução no Peru | [K] |
| **Sex 09/out** | BR | **IPCA de setembro** (IBGE) | Juros e Copom de novembro | [34] [S] |
| **Seg 12/out** | BR / CL / CO / AR | **Feriados:** N. Sra. Aparecida (BR, **B3 fechada**), Encuentro de Dos Mundos (CL), Día de la Raza (CO), Diversidad Cultural (AR). Nos EUA, Columbus Day: NYSE aberta, mercado de bonds fechado. | **A 2ª segunda-feira de decisão cai com a B3 fechada.** Executar Brasil na terça (13/out), ou via ADRs na segunda. | [K] |
| Ter 13/out | AR | IPC de setembro (INDEC) | ADRs argentinos | [102] [S] |
| **Qua 14/out** | US | **CPI de setembro** | Fed de 28/out | [54] [S] |
| Qui 15/out | BR / US | Varejo de agosto (BR). Varejo (US). | Consumo | [34][54] [S] |
| Sex 16/out | BR | IBC-Br de agosto | Atividade | [34] [S] |
| Qua 21/out | MX | Varejo de agosto | Consumo MX | [72] [S] |
| Qui 22/out | BR | Reunião do CMN | Baixa a média | [34] [S] |
| Qui 22/out | MX | INPC da 1ª quinzena de outubro e desemprego | Banxico de 05/nov | [72] [S] |
| **Sex 23/out** | BR | **IPCA-15 de outubro** | Juros | [34] [S] |
| Sex 23/out | MX | IGAE de agosto | Atividade | [72] [S] |
| **Dom 25/out** | BR | **2º TURNO PRESIDENCIAL** e 2º turno para governador em **7 estados**: RJ, DF, ES, RN, AC, TO e AM. O AM ainda estava sem status oficial, mas o primeiro colocado teve 40,63%. | **Evento binário principal** | [1][2][103] [F] |
| **Seg 26/out** | BR | 1º pregão pós-2º turno. Focus. | **Gap e rebalanceamento semanal no dia seguinte ao evento** | [34] [S] |
| **Ter 27/out** | CL | **RPM do BCCh** (TPM em 4,50%) | Bancos chilenos e CLP | [75][80] [S] |
| Ter 27/out | BR | Transações correntes e IDP de setembro | BRL | [34] [S] |
| **Ter 27 e qua 28/out** | US | **FOMC**, com decisão em 28/out | Global, USD e EM | [37] [F] |
| Qui 29/out | US | **PIB do 3T (preliminar)**, PCE | Global | [54] [S] |
| Qui 29/out | BR | CAGED de setembro | Atividade | [34] [S] |
| **Sex 30/out** | CO | **Decisão do BanRep** (12,25%) | CIB, EC e COP | [84][88] [S] |
| Sex 30/out | MX | **PIB do 3T (prévia)** | Peso e bolsa | [72] [S] |
| Sex 30/out | BR | PNAD (desemprego) e dívida bruta/PIB de setembro | Fiscal | [34] [S] |
| *Fora da janela* | BR / MX / US | Seg 02/nov: Finados (B3 fechada, 3ª segunda-feira de decisão afetada) **[K]**. Ter 03/nov: *midterms* dos EUA, prazo político do acordo da Seção 232 [67]. Ter 3 e qua 4/nov: Copom [20]. Qui 05/nov: Banxico [58]. | | |

**Temporada de balanços do 3T26 (não confirmada) [K]/[I]:**
- Pelo padrão histórico, as grandes mexicanas (Walmex, GFNorte, Grupo México, América Móvil, Cemex, FEMSA) costumam divulgar **da metade ao fim de outubro**.
- No Brasil, Vale e Santander Brasil costumam divulgar **no fim de outubro**. Itaú, BB e Petrobras, **no começo e meio de novembro**.
- **Ação requerida:** carregar as datas confirmadas dos sites de RI no módulo de calendário antes de dimensionar posições com evento de resultado na semana. Proposta de regra [I]: sinalizar no app toda posição com resultado dentro do horizonte de 5 pregões.

---

## 10. Riscos e oportunidades para um livro net neutral

> ⚠️ **HIPÓTESES DE PESQUISA. NÃO SÃO FATOS NEM RECOMENDAÇÕES DE INVESTIMENTO.** Toda tese abaixo é **[I]**. Os números citados como evidência têm fonte. Pesos, betas, exposições, rankings e tamanhos **têm de ser calculados pelo motor quantitativo determinístico** e aprovados pelo PM humano (aprovação vinculada a hash). O LLM não calculou nenhum deles.

### 10.1 Considerações de regime

- **R1. Evento binário no Brasil (05 a 26/out).**
  - O 1º turno moveu a probabilidade a favor de Flávio, mas o 2º turno segue **incerto**. Antes de 04/out, as pesquisas de 2º turno mostravam empate técnico [12][14].
  - Um livro net neutral **em dólar** pode carregar uma exposição grande ao "fator eleição", via BB, Petrobras, *small caps* e utilities.
  - Hipótese: **medir esse fator de forma determinística** e limitar a exposição líquida a ele. Um *proxy* possível é o spread entre as cestas Challenger e Incumbent do Bradesco BBI [28], ou a sensibilidade de cada ação aos dias de pesquisa.
- **R2. Volatilidade sob regime de evento.**
  - A vol implícita do EWZ (~46%) está perto do dobro da realizada (~24%) [14]. Uma covariância EWMA treinada em dados históricos **subestima** o risco ex-ante do Brasil até 26/out.
  - Hipóteses:
    - **(a)** começar a carteira inaugural na **parte baixa da banda de vol** (3% a 7%);
    - **(b)** usar, para nomes brasileiros, a vol que for maior entre a realizada e a implícita escalada, durante a janela de evento;
    - **(c)** estressar a carteira com cenários de gap de ±10% no EWZ, ordem de grandeza do movimento *overnight* de 04/out [2][9].
- **R3. Fed, dólar e juros americanos.**
  - Com UST 10y acima de 5%, DXY na máxima de 17 meses e o FOMC de 28/out com ~25%–28% de chance de alta (número anterior ao payroll) [40], o fator "EM FX / *carry*" está estressado.
  - O MXN já caiu 4 semanas seguidas [60].
  - Hipótese: neutralizar a **sensibilidade a moeda** (beta de cada ação ao FX local contra o USD) além do beta de mercado.
- **R4. Dispersão de commodities.**
  - Petróleo a ~US$ 100, minério em queda (−8% no mês), cobre perto do recorde e lítio −22% no mês [42][44][46][48].
  - Hipótese: incluir **fatores de commodity** (petróleo, cobre, minério, lítio) no modelo de risco, além dos *dummies* setoriais. Um "materiais neutro" pode esconder uma aposta longa em cobre e vendida em minério.
- **R5. Momentum e crowding.**
  - PETR4 subiu +70% no ano [30], e o *open interest* de calls de EWZ está no maior nível desde 2007 [14].
  - Hipótese: há **risco de reversão do fator momentum** depois do evento ("*sell the news*") e de squeeze nos shorts contra o rali. Monitorar a exposição a momentum e cortar quando ela passar do limite.
- **R6. Liquidez e calendário.**
  - B3, Santiago, BVC e BYMA estão fechadas em 12/out; a BVL, em 08/out **[K]**.
  - O 2º turno é num domingo, e o rebalanceamento de segunda (26/out) cai no gap.
  - Hipótese: usar **ADRs** como instrumento de *hedge* e execução nos dias de bolsa local fechada. Limitar a participação no volume (ADV) com mais rigor nos pregões de evento.

### 10.2 Ideias de pares por país e setor (hipóteses)

| # | Ideia (long / short) | Racional (evidência) | O que neutraliza | Fator residual (a aposta) | Riscos principais |
|---|---|---|---|---|---|
| **BR-1** | **Long BBAS3 / short ITUB4** | O BB tem beta eleitoral alto e possível privatização sob Flávio [27][30]. O Itaú é o banco de qualidade, presente nas cestas Incumbent e All-Weather [28]. | O setor bancário e parte do beta de mercado | **Eleição e privatização**, além de valuation (BB abaixo de 1x patrimônio, segundo [27]) | **Binário em 25/out.** Uma vitória de Lula reverte o par. O BB tem crédito agro. Tamanho de risco pequeno até o evento. |
| **BR-2** | **Cesta Challenger / cesta Incumbent** (BBI) | As cestas foram desenhadas para os dois cenários [28] | Mercado, se o par for montado neutro em beta | **Puro fator eleição**: aposta direcional, **não é alfa puro** | Só como decisão explícita do PM, com orçamento de risco limitado. Outra opção é usar o par como **hedge** para zerar o fator eleição do restante do livro. |
| **BR-3** | **Long PRIO3 / short VALE3** | Petróleo a ~US$ 100 [42], minério −8% no mês e Simandou [44][45]. As duas são exportadoras em USD e têm baixo beta eleitoral. | O fator BRL, o fator "exportadora" e grande parte do fator eleição | **Petróleo contra minério** (dispersão de commodities) | Normalização de Hormuz derruba o Brent [42]. Estímulo na China pode recuperar o minério. A PRIO3 tem liquidez boa, mas menor que a da VALE3. |
| **BR-4** | **Long domésticas sensíveis a juros / short exportadoras de celulose** (por exemplo, Suzano) | Real mais forte e curva fechando são a expectativa pós-1º turno [9]. Suzano está entre as "proteções" [29]. | O mercado | **Juros domésticos e BRL**, correlacionados com a eleição | **Correlacionado a R1.** Squeeze em *small caps*. Contar como exposição ao fator eleição. |
| **MX-1** | **Long receita em USD (Grupo México, Gruma, Cemex) / short consumo doméstico (Walmex ou FEMSA)** | Peso com −7,36% no mês [59], 4 semanas de queda [60]. Banxico parado com o Fed subindo [56]. | O mercado mexicano | **Fator MXN e exportação** | Um acordo da Seção 232 ou do USMCA antes de 03/nov pode **apreciar o peso** e virar o par [67]. O Grupo México também carrega beta a cobre, que precisa de hedge. |
| **MX-2** | **Long beneficiários de acordo na Seção 232 (Ternium, FIBRAs industriais e Vesta) / short pares domésticos** | Negociação avançando, com o México "confiante" [67]. Tarifas de 50% em aço e 25% em autos [66]. | Mercado e setor | **Notícia comercial** | Notícias binárias e possível atraso até 2027 [65]. Liquidez local de FIBRAs e Nemak. |
| **CL/PE-1** | **Long cobre (SCCO ou Grupo México) / short lítio (SQM)** | Cobre com alta de ~30% em 12 meses (não YTD) [46][47]. Risco de greve em Escondida: autorização aprovada, sujeita a mediação, mas a mina **não está parada por greve** [46]. Oferta chilena na mínima desde 2011 [47]. Lítio −22,5% no mês, com estoques chineses revisados para cima [48]. | O fator "mineração LatAm" | **Cobre contra lítio** | **Squeeze em SQM**: o lítio tem saltos ligados à oferta chinesa, como a revogação da mina da CATL [48]. Desfecho da mediação em Escondida: um acordo derrubaria o prêmio de oferta, e uma greve efetiva o elevaria. Verificar *short interest* e custo de aluguel da SQM. |
| **CL-1** | **Long domésticas com alívio do IR corporativo / short exportadoras chilenas** | IR corporativo de 27% para 23% até 2029 (trecho [S], **[NÃO VERIFICADO]**). BCCh parado com atividade fraca [74]. | O mercado chileno | **Reforma tributária contra ciclo** | Desemprego de 9,6% [76]. Fonte da reforma ainda não confirmada. Liquidez de Santiago e ADRs (BCH, BSAC). |
| **CO-1** | **Long Ecopetrol (EC) / short Bancolombia (CIB)**, ou o contrário | Governo pró-petróleo com Brent a ~US$ 100 [87][42]. BanRep subindo juros [83]. Fiscal de 7,2%–9,4% do PIB [85]. | O fator Colômbia (soberano e COP) | **Petróleo contra crédito e margem** | Extração de dividendos da EC pelo Tesouro. Rebaixamento soberano. COP. Liquidez local baixa: usar os ADRs. |
| **PE-1** | **Long Credicorp (BAP) / short banco LatAm comparável** (por exemplo, Bancolombia) | Governo Keiko pró-mercado, Velarde ratificado, possível fim dos tetos de juros [93][94]. BCRP estável [91]. | Setor bancário regional | **Regime político e regulatório do Peru** | Margem eleitoral mínima e Congresso fragmentado [89]. El Niño [92]. Risco cambial cruzado no par. |
| **AR-1** | **Long energia com receita em USD (YPF, Vista) / short ADRs de bancos (GGAL, BMA, SUPV)** | Risco-país acima de 600 pb, bancos −15% a −18% em setembro [96]. Petróleo alto [42]. | O fator Argentina e parte do beta global | **Petróleo e USD contra crédito doméstico e câmbio** | **Squeeze nos bancos**, que já caíram muito, com qualquer anúncio de swap ou apoio [99]. Custo e disponibilidade de aluguel. *Gaps* em feriados. Tamanho pequeno. |

### 10.3 Riscos específicos de *short squeeze* e liquidez (hipóteses)

1. **Estatais e *small caps* brasileiras** no rali pós-1º turno: BB, Petrobras e a cesta Challenger [28]. Os shorts diretos nesses nomes até 25/out carregam **risco de gap**. Hipótese: preferir **hedge via índice ou ETF** (EWZ, futuro de Ibovespa) para o beta, e reservar os shorts single-name a nomes com **baixa utilização de aluguel** e ADV alto.
2. **Calls de EWZ** com *open interest* recorde [14]: há convexidade positiva dos compradores. Um *gamma squeeze* é possível se a probabilidade de vitória de Flávio subir mais.
3. **ADRs argentinos de bancos** depois de −15% a −18% [96], e **SQM** com o lítio volátil [48]: os dois têm historicamente *short interest* relevante **[K]**. Verificar o *days-to-cover* no módulo de squeeze antes de qualquer short.
4. **Feriados assimétricos** (12/out e 02/nov no BR; 08/out no PE) **[K]**: posições locais ficam sem negociação enquanto os ADRs negociam. Monitorar o risco de *basis* entre ADR e ação local.

### 10.4 O que mudaria as hipóteses (gatilhos de revisão)

- Pesquisas de 2º turno do Brasil (Datafolha, Quaest, AtlasIntel), esperadas a partir da semana de 05/out.
- Apoios formais de Cury, Renan Santos, Caiado e Zema.
- IPCA de setembro (09/out) e IPCA-15 de outubro (23/out).
- CPI dos EUA (14/out) e FOMC (28/out), sobretudo a probabilidade de alta.
- Anúncio de acordo EUA–México na Seção 232 (antes de 03/nov).
- Desfecho da mediação e da autorização de greve em Escondida (a mina não está parada por greve).
- Decisões de BCCh (27/out) e BanRep (30/out).
- Anúncios de swap na Argentina.

---

## 11. Tabela de parâmetros (snapshot macro para ingestão)

> Valores **como reportados pelas fontes**, para referência e auditoria. Esta tabela **não substitui** a obtenção determinística de dados de mercado. Na ingestão, cada linha deve virar evidência com URL e data, e o FactBook deve usar a série de preço da fonte de dados oficial do sistema.

| # | Parâmetro | Valor | Data de referência | Fonte | Evid. |
|---|---|---|---|---|---|
| P1 | Flávio Bolsonaro, % válidos, 1º turno | 47,03% | 2026-10-04 | [103][1][2] | F |
| P2 | Lula, % válidos, 1º turno | 45,16% | 2026-10-04 | [103][1][2] | F |
| P3 | Data do 2º turno (BR) | 2026-10-25 | n/a | [1][5] | F |
| P4 | Selic meta | 13,75% | 2026-09-16 (vigente desde 17/09) | [17][33][104] | F |
| P5 | Próximo Copom | 2026-11-03 e 04 | n/a | [20][104] | F |
| P6 | Focus: Selic no fim de 2026 e de 2027 | 13,50% e 12,00% | 2026-09-28 | [19] | F |
| P7 | Projeção de IPCA do Copom para 2026 e 2027 | 5,2% e 3,9% | 2026-09-22 | [18] | F |
| P8 | IPCA em 12 meses | 4,22% | ago/2026 | [21][104] | F |
| P9 | IPCA-15 m/m e em 12 meses | 0,70% e 4,47% | set/2026 | [22][104] | F |
| P10 | Meta de inflação (BR) | 3,0% ±1,5 p.p. | n/a | [22] | S |
| P11 | Dívida bruta / PIB (BR) | 82,9% (SGS 13762: 82,86%) | ago/2026 | [23][104] | F |
| P12 | Meta de primário 2026 e PLOA 2027 | +0,25% e +0,5% do PIB | n/a | [24][25] | S |
| P13 | PIB BR do 2T26, t/t | +0,5% | 2T26 | [17] | F |
| P14 | USD/BRL | 5,2173 e 5,2139 | 2026-10-02 e 2026-10-05 | [10][32] | F |
| P15 | Ibovespa | 192.114,55 | 2026-10-02 | [10][108] | F |
| P16 | Vol implícita 1M do EWZ e vol realizada | ~46% e ~24% | ~2026-10-01 | [14] | S [NÃO VERIFICADO] |
| P17 | EWZ YTD (NAV TR) | +17,76% | 2026-10-01 | [51] | F |
| P18 | Banxico (meta) | 6,50% | 2026-09-24 | [55] | F |
| P19 | Próximo Banxico | 2026-11-05 | n/a | [58] | S |
| P20 | INPC geral e subjacente (1ª quinzena de set) | 3,42% e 3,79% | set/2026 | [56] | F |
| P21 | USD/MXN | 18,1637 e 18,1638 | 2026-10-02 e 2026-10-05 | [62][59] | S/F |
| P22 | S&P/BMV IPC | 64.531,68 | 2026-10-02 | [70] | S |
| P23 | EWW YTD (NAV TR) | +2,13% | 2026-10-01 | [53] | F |
| P24 | Seção 232: aço e alumínio; autos fora do USMCA | 50% e 25% | set/2026 | [66] | F |
| P25 | TPM do BCCh | 4,50% | 2026-09-08 | [73][75] | S/F |
| P26 | Próxima RPM do BCCh | 2026-10-27 | n/a | [75] | S |
| P27 | IPC Chile, geral e subjacente | 4,1% e 3,3% | ago/2026 | [75] | F |
| P28 | IPoM: PIB 2026 do Chile | 0,25%–0,75% | set/2026 | [74] | S |
| P29 | USD/CLP | 979,51 | 2026-10-05 | [76] | F |
| P30 | Cobre LME 3M | US$ 14.253,50/t | 2026-10-01 | [46] | F |
| P31 | Cobre COMEX | US$ 6,55/lb (retrato intradiário; os +30,9% do TE são em 12 meses, não YTD) | 2026-10-05 | [47][108] | F |
| P32 | Carbonato de lítio (China) | 122.800 CNY/t | 2026-09-30 | [48] | F |
| P33 | Taxa do BanRep | 12,25% (+25 bp) | 2026-09-30 | [83][84] | F |
| P34 | Próximo BanRep | 2026-10-30 | n/a | [84] | S |
| P35 | IPC Colômbia | 6,24% | ago/2026 | [84] | F |
| P36 | Déficit da Colômbia em 2026 e no PGN 2027 | 7,2% e 9,4%–9,5% do PIB (PGN reapresentado em 29/ago; aprovação final não verificada) | set/2026 | [85] | F |
| P37 | USD/COP | 3.308,89 | 2026-10-05 | [87] | F |
| P38 | Taxa do BCRP | 4,25% | 2026-09-10 | [91][92] | F/S |
| P39 | Próximo BCRP | 2026-10-07 | n/a | [92] | S |
| P40 | IPC Peru | 4,4% | ago/2026 | [92] | F |
| P41 | Risco-país da Argentina | 607 pb | 2026-09-30 | [96] | F |
| P42 | USD/ARS mayorista e teto da banda | 1.517 e 1.919,40 | 2026-09-30 | [96] | F |
| P43 | ARS CCL e MEP | 1.616,44 e 1.542,56 | 2026-09-30 | [96] | F |
| P44 | Inflação da Argentina, m/m e a/a | 1,7% e 33,5% | ago/2026 | [101] | F |
| P45 | Fed funds | 3,75%–4,00% | 2026-09-16 | [36] | F (Fed) |
| P46 | Mediana do *dot plot* no fim de 2026 | 4,1% | 2026-09-16 | [38][107] | F |
| P47 | Próximo FOMC | 2026-10-27 e 28 | n/a | [37] | F |
| P48 | UST 10y (fechamento e pico) | **5,28%** (CMT em 02/out; CORRIGIDO, antes 5,175%) e 5,34% (intradiário em 01/out) | semana até 2026-10-02 | [105][40][108] | F |
| P49 | DXY | ~102,0 | 2026-10-02 | [40] | F |
| P50 | VIX | 15,31 | 2026-10-02 | [41][108] | F |
| P51 | Brent | US$ 102,25 e US$ 100,83 (o de 05/out é intradiário) | 2026-10-02 e 2026-10-05 | [10][42][108] | F |
| P52 | Minério de ferro 62% | US$ 91,35/t | 2026-10-02 | [44] | F |
| P53 | PMI industrial da China | 50,1 | set/2026 | [49] | F |

**Parâmetros de regime sugeridos (HIPÓTESES [I], para decisão do PM e implementação no motor determinístico):**

| Parâmetro sugerido | Valor proposto | Justificativa |
|---|---|---|
| Janela de evento Brasil | 2026-10-05 a 2026-10-26 (fechamento) | Do 1º pregão pós-1º turno até o 1º pregão pós-2º turno |
| Vol-alvo ex-ante inicial | Parte baixa da banda de 3% a 7%; por exemplo, ≤ 4% até o 2º turno, a decidir pelo PM | Inception, evento binário e vol implícita do Brasil perto do dobro da realizada [14] |
| Exposição líquida ao fator eleição | Perto de zero, ou orçamento de risco explícito e pequeno aprovado pelo PM | Preservar o objetivo de alfa puro (BR-2 e R1) |
| Vol de nomes brasileiros no risco | O maior valor entre a vol realizada (EWMA) e a vol implícita escalada, durante a janela | Covariância histórica subestima o evento (R2) |
| Cenários de stress obrigatórios | Gap do EWZ de ±10%; Brent ±15%; USD/MXN +5%; risco-país da Argentina +150 pb | Ordem de grandeza dos movimentos recentes [2][9][59][96]. Os valores exatos ficam a cargo do PM. |
| Execução em feriado local | Usar ADRs e evitar rebalancear localmente em 12/out (BR, CL, CO, AR) e em 08/out (PE) | Calendário [K] |
| Flag de resultado | Sinalizar posições com balanço do 3T26 nos próximos 5 pregões | Temporada de balanços (datas a confirmar) |

---

## 12. Conflitos de dados e limitações conhecidas

1. **Eleição no Brasil:** os números parciais de 22h07 (47,50% × 44,61%) diferem dos finais (47,03% × 45,16%). **Usar os finais.** Os detalhes de Congresso e governadores vêm de 1 ou 2 fontes. A contagem de estados com 2º turno é **7** (AC, AM, DF, ES, RJ, RN, TO), segundo o JSON do TSE [103]. Ela confirma o Rio Times [2]. A InfoMoney [3] listava 6 porque o AM ainda não estava classificado. Os percentuais de governador da InfoMoney às 22h07 eram parciais e foram trocados pelos finais do TSE. O total de 121 deputados do PL [2] **não foi confirmado** pelo TSE, onde faltava o status de SP, MG e AM.
2. **Contaminação de busca:** um trecho afirmou que "Lula venceu o 2º turno de 25/out com 50,90%". **Isso é falso para 2026**: são os números de 2022, e o 2º turno de 2026 **ainda não ocorreu**.
3. **Brent:** o Rio Times [16] reporta US$ 88,88 em 02/out. A Forbes Brasil (US$ 102,25 [10]), o TradingEconomics (US$ 100,83 [42]) e a Infobae (US$ 103,70 em 23/set [98]) divergem. **O Rio Times foi descartado** para commodities. Na verificação, o Yahoo BZ=F confirma o fechamento de US$ 102,25 em 02/out [108]. A variação "no ano" do TE é, na verdade, em 12 meses. Os preços de ações individuais reportados pelo Rio Times (por exemplo, BBAS3) também conflitam com a Exame [30] e foram tratados como **[S]** ou descartados.
4. **YTD do IPC México:** +4,28% [71] contra +12,17% [63b]. A iShares, para o EWW em USD (+2,13% [53]), sugere a faixa baixa. **Usar a série de preço.**
5. **Ibovespa:** setembro com +3,14% (até 28/set) [12] contra ~+5% (até 30/set) [13]. A semana até 02/out com +4,71% [11] contra +5,81% [10]. Calcular pela série de preço.
6. **USD/BRL no ano:** −1,86% [32] contra −4,95% [10]. As bases diferem.
7. **Merval em setembro:** a mesma matéria [96] traz números em USD conflitantes. Usar só o nível.
8. **Colômbia:** a narrativa do TradingEconomics sobre o COP é inconsistente com o próprio nível [87]. Usar só o nível e as variações.
9. **Balanços do 3T26:** **nenhuma data confirmada** nesta sessão (orçamento de buscas esgotado). Os feriados são **[K]**.
10. **Programa de Lula** e **impactos setoriais quantitativos** (elasticidades, betas) **não foram pesquisados**. Devem ser estimados pelo motor quantitativo.
11. **Fontes de confiabilidade moderada:** o Rio Times aparece muitas vezes nos resultados de busca e tem números internamente inconsistentes. Quando é a única fonte, o dado está marcado **[S]**.

---

## 13. Fontes (numeradas; data de publicação ou de referência; acesso em 2026-10-05)

**Brasil: eleição e mercado**
1. Wikipedia, *2026 Brazilian general election* (resultados do TSE). https://en.wikipedia.org/wiki/2026_Brazilian_general_election (acesso em 2026-10-05)
2. The Rio Times, *Brazil Election Results 2026: Live Updates, Vote Count and Runoff Scenarios* (publicado em 2026-09-05, atualizado em 2026-10-05). https://www.riotimesonline.com/brazil-election-results-2026/
3. InfoMoney, *AO VIVO: Eleições gerais, primeiro turno 2026* (2026-10-04, 22h07). https://www.infomoney.com.br/politica/ao-vivo-eleicoes-gerais-primeiro-turno-2026/
4. Bloomberg, *Brazil Assets Poised to Rally After Bolsonaro's First-Round Election Lead* (2026-10-05), trecho de busca. https://www.bloomberg.com/news/articles/2026-10-05/bolsonaro-s-first-round-lead-sets-brazil-assets-for-monday-surge
5. CNBC, *Brazil election headed to runoff, projection shows, as Bolsonaro lead narrows* (2026-10-04), trecho de busca. https://www.cnbc.com/amp/2026/10/04/brazil-presidential-election-lula-bolsonaro.html
6. CNBC, *Lula or Bolsonaro: Wall Street braces for two wildly different results in Brazil election* (2026-10-03), trecho de busca. https://www.cnbc.com/2026/10/03/lula-or-bolsonaro-wall-street-braces-for-two-wildly-different-results-in-brazil-election.html
7. NPR, *Brazil's presidential race heads to Lula–Bolsonaro run-off as right gains ground* (2026-10-04), trecho de busca. https://www.npr.org/2026/10/04/nx-s1-5981181/brazil-presidential-lula-bolsonaro
8. CNN, *Brazil election heads to runoff between Bolsonaro and Lula...* (2026-10-04), trecho de busca. https://www.cnn.com/2026/10/04/americas/brazil-president-elections-2026-latam-intl
9. Estado de Minas / PlatôBR, *Resultado do primeiro turno deve derrubar o dólar e provocar um rally na bolsa* (2026-10-04, 23h12). https://www.em.com.br/politica/platobr/2026/10/7514657-resultado-do-primeiro-turno-deve-derrubar-o-dolar-e-provocar-um-rally-na-bolsa.html
10. Forbes Brasil, *Ibovespa Acelera no Final do Pregão e Fecha Acima de 190 Mil Pontos* (2026-10-02). https://forbes.com.br/forbes-money/2026/10/ibovespa-acelera-no-final-do-pregao-e-fecha-acima-de-190-mil-pontos/
11. Finance News, *Ibovespa fecha em +2,63%; na semana acumulou alta de 4,71%* (2026-10-02), trecho de busca. https://financenews.com.br/2026/10/ibovespa-fecha-em-263-na-semana-acumulou-alta-de-471/
12. InfoMoney, *Em compasso de espera, Bolsa perde força e dólar sobe na reta final do 1º turno* (c. 2026-09-28). https://www.infomoney.com.br/mercados/ibovespa-dolar-primeiro-turno-eleicoes-2026-4-pregoes/
13. Nord Investimentos, *Small caps e bancos dispararam: o que isso revela sobre a eleição* (2026-10-01). https://www.nordinvestimentos.com.br/blog/bolsa-precificando-antes-eleicao-2026/
14. OptionBeast, *Petrobras and Vale Are Priced for a Winner. Sunday May Not Deliver One.* (2026-10-01). https://wp.optionbeast.com/2026/10/01/petrobras-and-vale-are-priced-for-a-winner-sunday-may-not-deliver-one/
15. The Rio Times, *What Brazil's Election Means for US Investors* (2026-10-04). https://www.riotimesonline.com/what-brazil-election-means-for-us-investors-ibovespa-real-2026/
16. The Rio Times, *Brazil Runoff Set; Ibovespa Entered Vote at 192,115* (2026-10-05). https://www.riotimesonline.com/brazil-election-markets-real-ibovespa-adrs-2026

**Brasil: juros, inflação e fiscal**

17. CNN Brasil, *BC reduz juros a 13,75% e deixa "porta aberta" para novos cortes* (2026-09-16). https://www.cnnbrasil.com.br/economia/money/macroeconomia/bc-copom-selic-juros-setembro-2026/
18. InfoMoney, *Selic vai cair mais em 2026? BC mantém suspense...* (ata do Copom, 2026-09-22). https://www.infomoney.com.br/economia/ata-do-copom-projecoes-selic-setembro2026/
19. DGABC, *Selic no fim de 2026 segue em 13,50%, aponta Focus* (2026-09-28). https://dgabc.com.br/Noticia/4349437/selic-no-fim-de-2026-segue-em-13-50-aponta-focus
20. Okai, *BC publica calendário de reuniões do Copom em 2026* (2025-06-24), trecho de busca, com confirmação cruzada em amdjus.com.br. https://okai.com.br/noticia/2025-06-24/bc-publica-calendario-de-reunioes-do-copom-em-2026
21. QuintoAndar Guias, *IPCA: inflação varia −0,32% em agosto de 2026* (set/2026), trecho de busca. https://www.quintoandar.com.br/guias/dados-indices/ipca-acumulado-reajuste-de-aluguel-2026/
22. ADVFN, *IPCA-15 acelera para 0,70% em setembro e inflação acumulada em 12 meses chega a 4,47%* (set/2026), trecho de busca. https://br.advfn.com/jornal/2026/09/ipca-15-acelera-para-0-70-em-setembro-e-inflacao-acumulada-em-12-meses-chega-a-4-47
23. O Tempo, *Dívida bruta do Brasil atinge 82,9% do PIB em agosto, maior nível em cinco anos* (2026-09-30), trecho de busca. https://www.otempo.com.br/economia/2026/9/30/divida-bruta-do-brasil-atinge-82-9-do-pib-em-agosto-maior-nivel-em-cinco-anos-mostra-bc
24. Renova Invest, *Meta Fiscal 2026: arcabouço fiscal e meta de superávit de 0,25% do PIB* (s/d), trecho de busca. https://renovainvest.com.br/blog/meta-fiscal/
25. Times Brasil, *Orçamento de 2027 prevê superávit de R$ 18,6 bilhões com exclusões de despesas da meta fiscal* (set/2026), trecho de busca. https://timesbrasil.com.br/brasil/orcamento-de-2027-preve-superavit-de-r-186-bilhoes-com-exclusoes-de-despesas-da-meta-fiscal/
26. Gazeta do Povo, *Em plano de governo, Flávio prevê corte de gastos e de impostos* (2026-08-18). https://www.gazetadopovo.com.br/eleicoes/2026/plano-de-governo-flavio-bolsonaro-economia/
27. Jornal Pequeno, *Equipe de Flávio Bolsonaro prepara ajuste fiscal e admite privatização do BB* (2026-09-16). https://jornalpequeno.com.br/2026/09/16/equipe-de-flavio-bolsonaro-prepara-ajuste-fiscal-e-admite-privatizacao-do-bb/
28. InfoMoney, *Eleição: 3 cestas de ações para diferentes resultados nas urnas, segundo Bradesco BBI* (2026-09-28). https://www.infomoney.com.br/mercados/eleicao-3-cestas-de-acoes-para-diferentes-resultados-nas-urnas-segundo-bradesco-bbi/
29. InfoMoney, *Eleições importam, mas o grande trade para a Bolsa será o fiscal; veja os cenários* (2026-10-02). https://www.infomoney.com.br/mercados/eleicoes-importam-mas-o-grande-trade-para-a-bolsa-sera-o-fiscal-veja-os-cenarios/
30. Exame, *Petrobras e Banco do Brasil: quanto a eleição ainda mexe com as estatais da Bolsa* (2026-10-01). https://exame.com/invest/mercados/petrobras-e-banco-do-brasil-quanto-a-eleicao-ainda-mexe-com-as-estatais-da-bolsa/
31. Wikipedia, *Eletrobras* (renomeada Axia Energia em 2025) (acesso em 2026-10-05). https://en.wikipedia.org/wiki/Eletrobras
32. TradingEconomics, *Brazilian Real* (2026-10-05). https://tradingeconomics.com/brazil/currency
33. TradingEconomics, *Brazil Interest Rate* (2026-10-05). https://tradingeconomics.com/brazil/interest-rate
34. TradingEconomics, *Brazil Calendar* (2026-10-05). https://tradingeconomics.com/brazil/calendar
35. InfoMoney, *As 7 ações mais recomendadas antes do 1º turno das eleições* (out/2026), trecho de busca. https://www.infomoney.com.br/onde-investir/as-7-acoes-mais-recomendadas-outubro-2026/

**Global**

36. Federal Reserve, *FOMC Statement* (2026-09-16). https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm
37. Federal Reserve, *Meeting calendars* (2026). https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
38. PNC Economics, *FOMC Hikes as Expected, as Dot Plot Points to Additional...* (2026-09-16), e Raisin, *Fed Dot Plot Analysis September 2026*, trechos de busca. https://www.pnc.com/content/dam/pnc-com/pdf/aboutpnc/EconomicReports/EconomicUpdates/2026/PNC_Economics_Research_FOMC_Statement_16_September_2026.pdf ; https://www.raisin.com/en-us/news/fed-decision-dot-plot-breakdown-september-2026/
39. Wikipedia, *Chair of the Federal Reserve* (acesso em 2026-10-05). https://en.wikipedia.org/wiki/Chair_of_the_Federal_Reserve
40. TradingView News, *DXY: Dollar Holds Near 17-Month High Despite Falling Yields. Nonfarm Payrolls Up Next.* (2026-10-02). https://www.tradingview.com/news/tradingview:441382ff9094b:0-dxy-dollar-holds-near-17-month-high-despite-falling-yields-nonfarm-payrolls-up-next/
41. StreetStats, *VIX S&P 500 Volatility and MOVE* (2026-10-02), trecho de busca. https://streetstats.finance/markets/volatility
42. TradingEconomics, *Brent crude oil* (2026-10-05). https://tradingeconomics.com/commodity/brent-crude-oil
43. U.S. EIA, *Short-Term Energy Outlook: Global oil markets* (set/2026), trecho de busca. https://www.eia.gov/outlooks/steo/report/global_oil.php
44. TradingEconomics, *Iron Ore* (2026-10-02). https://tradingeconomics.com/commodity/iron-ore
45. GMK Center, *Iron ore prices may fall to $94 per tonne in 2026: consensus forecast* (2026), trecho de busca. https://gmk.center/en/news/iron-ore-prices-may-fall-to-94-per-tonne-in-2026-consensus-forecast/
46. Copper.com.au, *Copper Weekly Brief: week ending 2 October 2026* (2026-10-02). https://copper.com.au/news/mining/copper-weekly-brief-week-ending-2-october-2026/
47. TradingEconomics, *Copper* (2026-10-05). https://tradingeconomics.com/commodity/copper
48. TradingEconomics, *Lithium* (2026-09-30). https://tradingeconomics.com/commodity/lithium
49. TradingEconomics, *China Business Confidence (NBS Manufacturing PMI)* (2026-09-30). https://tradingeconomics.com/china/business-confidence
50. Macrostream (dados EPFR), *Emerging Market Flows Slow as ETF Inflows Diverge from Active Money...* (início de set/2026). https://www.macrostream.ai/articles/6a9a709053fce5578f9108b9
51. iShares, *iShares MSCI Brazil ETF (EWZ)*, página do produto (dados de 2026-10-01 e 02). https://www.ishares.com/us/products/239612/ishares-msci-brazil-capped-etf
52. iShares, *iShares Latin America 40 ETF (ILF)*, página do produto (2026-10-02). https://www.ishares.com/us/products/239761/ishares-latin-america-40-etf
53. iShares, *iShares MSCI Mexico ETF (EWW)*, página do produto (2026-10-01 e 02). https://www.ishares.com/us/products/239670/ishares-msci-mexico-capped-etf
54. TradingEconomics, *United States Calendar* (2026-10-05). https://tradingeconomics.com/united-states/calendar

**México**

55. Banco de México, *Anuncios de las decisiones de política monetaria* (2026). https://www.banxico.org.mx/publicaciones-y-prensa/anuncios-de-las-decisiones-de-politica-monetaria/anuncios-politica-monetaria-t.html
56. Infobae, *Banxico mantiene tasa de interés en el 6,5% y condiciona futuras decisiones a la inflación* (2026-09-24). https://www.infobae.com/america/agencias/2026/09/24/banxico-mantiene-tasa-de-interes-en-el-65-y-condiciona-futuras-decisiones-a-la-inflacion/
57. El Financiero, *Banxico se desmarca de la Fed y mantiene tasa de interés en 6.5 por ciento* (2026-09-25), trecho de busca. https://www.elfinanciero.com.mx/economia/2026/09/25/banxico-se-desmarca-de-la-fed-y-mantiene-tasa-de-interes-en-65-por-ciento/
58. TradingEconomics, *Mexico Interest Rate* (próxima reunião em 2026-11-05) (2026-10-05). https://tradingeconomics.com/mexico/interest-rate
59. TradingEconomics, *Mexican Peso* (2026-10-05). https://tradingeconomics.com/mexico/currency
60. El CEO, *Precio del dólar hoy 2 de octubre de 2026: peso mexicano cierra su cuarta semana depreciándose* (2026-10-02). https://elceo.com/mercados/tipo-de-cambio-peso-dolar-hoy-2-de-octubre-de-2026/
61. N+ (nmas), *Peso mexicano, en caída libre frente al dólar* (2026-10-02). https://www.nmas.com.mx/economia/dolar/tipo-de-cambio-peso-dolar-estadounidense-mexico-viernes-2-octubre-2026/
62. Infobae México, *Dólar hoy en México: cotización de cierre del 2 de octubre* (2026-10-02), trecho de busca. https://www.infobae.com/mexico/2026/10/02/dolar-hoy-en-mexico-cotizacion-de-cierre-del-2-de-octubre/
63. TradingEconomics, *Mexico GDP Growth Rate*, e Mexico Business News, *Mexico's Economy Grew 1.4% in the 2Q26* (jul a ago/2026), trechos de busca. https://tradingeconomics.com/mexico/gdp-growth ; https://mexicobusiness.news/trade-and-investment/news/mexicos-economy-grew-14-2q26
63b. The Rio Times, *Mexico Markets: IPC & the Peso, October 2, 2026* (2026-10-02), com confiabilidade moderada e números inconsistentes. https://www.riotimesonline.com/mexico-markets-ipc-peso-friday-october-2-2026
64. White & Case, *USMCA 2026 Joint Review: United States declines to extend Agreement, triggering annual reviews* (jul/2026), trecho de busca. https://www.whitecase.com/insight-alert/usmca-2026-joint-review-united-states-declines-extend-agreement-triggering-annual
65. Mexico Business News, *Mexico, US Set Fourth Round of USMCA Review Talks for September* (2026-07-27). https://mexicobusiness.news/trade-and-investment/news/mexico-us-set-fourth-round-usmca-review-talks-september
66. The Rio Times, *Mexico and US Close In on Trade Deal After Trump–Sheinbaum Call* (2026-09-18). https://www.riotimesonline.com/trump-sheinbaum-call-mexico-us-trade-deal-september-2026/
67. Bloomberg, *US, Mexico Negotiating Deal to Cut Tariffs on Steel, Aluminum, Vehicles* (2026-09-30), trecho de busca. https://www.bloomberg.com/news/articles/2026-09-30/mexico-grows-confident-on-us-deal-to-cut-steel-auto-tariffs
68. Wikipedia, *2025 Mexican judicial elections* (acesso em 2026-10-05). https://en.wikipedia.org/wiki/2025_Mexican_judicial_elections
69. Wikipedia, *2024 Mexican judicial reform* (acesso em 2026-10-05). https://en.wikipedia.org/wiki/2024_Mexican_judicial_reform
70. Investing.com México, *Las bolsas de valores de México cerraron con subidas; el S&P/BMV IPC ganó un 1.10%* (2026-10-02), e El Diario de Chihuahua, *Cae BMV 0.71% en la semana* (2026-10-02), trechos de busca. https://mx.investing.com/news/stock-market-news/las-bolsas-de-valores-de-mexico-cerraron-con-subidas-el-spbmv-ipc-gano-un-110-3785365 ; https://www.eldiariodechihuahua.mx/economia/2026/oct/02/cae-bmv-071-en-la-semana-843672.html
71. EBC Financial Group, *El S&P/BMV IPC avanza 4.28% en 2026 y resiste la volatilidad global* (s/d), trecho de busca. https://www.ebc.com/es/forex/el-sp-bmv-ipc-avanza-en-2026-y-resiste-la-volatilidad-global
72. TradingEconomics, *Mexico Calendar* (2026-10-05). https://tradingeconomics.com/mexico/calendar

**Chile**

73. Banco Central de Chile, *Comunicado de la Reunión de Política Monetaria, 8 de septiembre de 2026*, trecho de busca. https://www.bcentral.cl/documents/33528/8618392/Comunicado+RPM+septiembre+2026.pdf/3cec1aa3-00d3-8486-98d6-1eeddb7d997e?t=1788898567406
74. Banco Central de Chile, *Banco Central publica el IPoM de septiembre de 2026*, trecho de busca. https://www.bcentral.cl/en/content/-/detalle/prensa/nota-de-prensa/bcch-publica-ipom-septiembre-2026
75. TradingEconomics, *Chile Interest Rate* (próxima RPM em 2026-10-27) (2026-10-05). https://tradingeconomics.com/chile/interest-rate
76. TradingEconomics, *Chilean Peso* (2026-10-05). https://tradingeconomics.com/chile/currency
77. Wikipedia, *Presidency of José Antonio Kast* (acesso em 2026-10-05). https://en.wikipedia.org/wiki/Presidency_of_Jos%C3%A9_Antonio_Kast
78. The Rio Times, *Chile 2027 Budget: Kast Raises Spending 1.5% and Vows to Check Every Peso* (2026-10-01). https://www.riotimesonline.com/chile-kast-budget-2027-verify-every-peso-2026
79. *(Reforma "Reconstrução Nacional", IR corporativo de 27% para 23%)*: trecho de busca atribuído à cobertura do Rio Times sobre o governo Kast. URL exata não confirmada. Ver [78] e https://www.riotimesonline.com/chile-unemployment-crisis-kast-stimulus-cabinet-2026/
80. TradingEconomics, *Chile Calendar* (2026-10-05). https://tradingeconomics.com/chile/calendar

**Colômbia**

81. Wikipedia (es), *Elecciones presidenciales de Colombia de 2026* (acesso em 2026-10-05). https://es.wikipedia.org/wiki/Elecciones_presidenciales_de_Colombia_de_2026
82. El Tiempo, *Resultados elecciones presidenciales Colombia 2026: De la Espriella, presidente electo* (jun/2026), trecho de busca. https://www.eltiempo.com/politica/elecciones-colombia-2026/resultados-segunda-vuelta-presidencial-2026-siga-el-minuto-a-minuto-del-preconteo-de-la-registraduria-nacional-3565893
83. Valora Analitik, *Banco de la República aumenta las tasas de interés en Colombia en septiembre de 2026* (2026-09-30). https://www.valoraanalitik.com/banco-de-la-republica-aumenta-tasas-de-interes-septiembre-2026/
84. TradingEconomics, *Colombia Interest Rate* (próxima reunião em 2026-10-30) (2026-10-05). https://tradingeconomics.com/colombia/interest-rate
85. The Rio Times, *Colombia's 2027 Budget Points to Its Largest Deficit on Record* (2026-09-13). https://www.riotimesonline.com/colombia-2027-budget-634-9-trillion-record-deficit-2026/
86. Infobae, *De La Espriella propone ajuste fiscal: déficit de 4,8% en 360 días y crecimiento de 5%* (2026-06-24), trecho de busca. https://www.infobae.com/colombia/2026/06/24/de-la-espriella-propone-ajuste-fiscal-deficit-de-48-en-360-dias-y-crecimiento-de-5/
87. TradingEconomics, *Colombian Peso* (2026-10-05). https://tradingeconomics.com/colombia/currency
88. TradingEconomics, *Colombia Calendar* (2026-10-05). https://tradingeconomics.com/colombia/calendar

**Peru**

89. Wikipedia (es), *Elecciones generales de Perú de 2026* (acesso em 2026-10-05). https://es.wikipedia.org/wiki/Elecciones_generales_de_Per%C3%BA_de_2026
90. TV Perú, *Elecciones 2026: JNE proclamará mañana resultados oficiales de la segunda vuelta* (2026-07-02), trecho de busca. https://www.tvperu.gob.pe/noticias/politica/elecciones-2026-jne-proclamara-manana-resultados-oficiales-de-la-segunda-vuelta
91. Infobae Perú, *BCRP lleva más de un año con tasa de referencia a 4,25%* (2026-09-11), trecho de busca. https://www.infobae.com/peru/2026/09/11/bcrp-lleva-mas-de-un-ano-con-tasa-de-referencia-a-425-terminos-de-intercambio-siguen-favoreciendo-al-peru/
92. TradingEconomics, *Peru Interest Rate* (próxima reunião em 2026-10-07) (2026-10-05). https://tradingeconomics.com/peru/interest-rate
93. Gestión, *Gobierno de Keiko Fujimori ratifica a Julio Velarde como presidente del BCRP* (2026), trecho de busca. https://gestion.pe/economia/gobierno-de-keiko-fujimori-ratifica-a-julio-velarde-como-presidente-del-bcrp-noticia/
94. RPP, *Gobierno de Keiko Fujimori evalúa eliminar ley que fija topes a tasas de interés* (2026), trecho de busca. https://rpp.pe/economia/economia/topes-a-tasas-de-interes-gobierno-de-keiko-fujimori-busca-eliminar-ley-que-actualmente-fija-que-bancos-cobren-hasta-114-noticia-1699453
95. Wikipedia (es), *Gobierno de Keiko Fujimori* (2026), trecho de busca. https://es.wikipedia.org/wiki/Gobierno_de_Keiko_Fujimori

**Argentina**

96. La Nación, *El dólar oficial abandona su valor más alto del año y el riesgo país cierra septiembre por encima de los 600 puntos* (2026-09-30). https://www.lanacion.com.ar/economia/la-suba-del-riesgo-pais-fue-la-noticia-negativa-de-un-mes-que-golpeo-a-las-finanzas-nid30092026/
97. La Nación, *El riesgo país subió 18% en el mes: las tres preocupaciones de los inversores...* (2026-09-29), trecho de busca. https://www.lanacion.com.ar/economia/el-riesgo-pais-subio-18-en-el-mes-las-tres-preocupaciones-de-los-inversores-sobre-la-economia-de-nid29092026/
98. Infobae, *Jornada financiera: el riesgo país subió por octavo día consecutivo y alcanzó un máximo en cinco meses* (2026-09-23). https://www.infobae.com/economia/2026/09/23/jornada-financiera-el-riesgo-pais-subio-por-octavo-dia-consecutivo-y-alcanzo-un-maximo-en-cinco-meses/
99. Infobae, *Dólar y elecciones: las dudas detrás de la "bazuca" de Milei para evitar una corrida cambiaria en 2027* (2026-10-03). https://www.infobae.com/economia/2026/10/03/dolar-y-elecciones-las-dudas-detras-de-la-bazuca-de-milei-para-evitar-una-corrida-cambiaria-en-2027/
100. Perfil, *Reservas, elecciones y tasas de Estados Unidos: por qué el riesgo país argentino volvió a superar los 600 puntos* (set/2026), trecho de busca. https://www.perfil.com/noticias/economia/reservas-elecciones-tasas-estados-unidos-riesgo-pais-argentino-volvio-superar-600-puntos-a40.phtml
101. TradingEconomics, *Argentina Inflation Rate* (dado de ago/2026; acesso em 2026-10-05). https://tradingeconomics.com/argentina/inflation-cpi
102. TradingEconomics, *Argentina Calendar* (2026-10-05). https://tradingeconomics.com/argentina/calendar

**Fontes adicionadas na verificação independente (acesso em 2026-10-05)**

103. TSE, JSON oficial de resultados. Presidente: eleição 6257, arquivo gerado em 05/10/2026 às 02h59, 100% das seções totalizadas. Governador, Senador e Deputado Federal: eleição 6259, um arquivo por UF. https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json ; padrão por UF: https://resultados.tse.jus.br/oficial/ele2026/6259/dados/{uf}/{uf}-c{0003|0005|0006}-e006259-u.json
104. Banco Central do Brasil, API SGS: séries 432 (Selic meta), 13762 (DBGG/PIB), 7478 (IPCA-15), 433 e 13522 (IPCA) e 1 (PTAX venda; 02/out: 5,2238). https://api.bcb.gov.br/dados/serie/bcdata.sgs.{série}/dados?formato=json
105. U.S. Department of the Treasury, *Daily Treasury Par Yield Curve Rates* (2026; comparação com 2002, 2006, 2007, 2023 e 2025). https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026
106. U.S. BLS, *The Employment Situation: September 2026* (2026-10-02). https://www.bls.gov/news.release/empsit.nr0.htm
107. Federal Reserve, *Summary of Economic Projections*, Tabela 1 (2026-09-16). https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm
108. Yahoo Finance, API de gráficos (agregador; usado só para checagem cruzada de níveis e datas: EWZ, PBR, VALE, EWW, ILF, ^BVSP, ^MXX, ^MERV, ^TNX, ^VIX, DX-Y.NYB, BZ=F, HG=F, BRL=X, MXN=X). https://query1.finance.yahoo.com/v8/finance/chart/{ticker}
109. Wikipedia, *United States–Mexico–Canada Agreement* (revisão conjunta de 01/07/2026). https://en.wikipedia.org/wiki/United_States%E2%80%93Mexico%E2%80%93Canada_Agreement
110. Wikipedia (en), *2026 Colombian presidential election* e *2026 Peruvian general election*. https://en.wikipedia.org/wiki/2026_Colombian_presidential_election ; https://en.wikipedia.org/wiki/2026_Peruvian_general_election
111. Federal Reserve Board, *Board Members*. https://www.federalreserve.gov/aboutthefed/bios/board/default.htm

---

## Verificação independente

> **Passe adversarial, 2026-10-05, segunda-feira, antes da abertura.**
>
> **Método.** Cada afirmação datada ou numérica prioritária foi re-checada, quando possível, numa **fonte primária diferente** da original: JSON oficial do TSE, API SGS do BCB, Treasury, BLS, Fed, Banxico e iShares. Para níveis de mercado, a checagem cruzada usou a série do Yahoo Finance [108].
>
> **Limites.**
> - O orçamento de WebSearch da sessão estava esgotado, então a verificação usou leitura direta de URLs (WebFetch e APIs públicas).
> - Bloomberg, White & Case, ADVFN, Okai, BanRep, BCRP e BCCh bloquearam a leitura automatizada.
> - As variações percentuais citadas como "script de verificação" foram calculadas **por código** (Python, sobre as séries baixadas), **só para testar as fontes**. Elas **não** substituem o FactBook, que deve recalcular tudo pela camada de dados determinística (AGENTS.md, invariante 1).
>
> **Legenda.**
> - **CONFIRMADO**: bate com uma fonte independente ou primária.
> - **CORRIGIDO**: o texto foi alterado.
> - **NÃO VERIFICADO**: não houve confirmação independente, e o trecho foi marcado no corpo do documento.

| # | Afirmação verificada | Status | Resultado da verificação | Fontes |
|---|---|---|---|---|
| V1 | Flávio 47,03% (56.104.503) × Lula 45,16% (53.879.538); 2º turno em 25/out | **CONFIRMADO** | O JSON do TSE (100% das seções, gerado em 05/10 às 02h59) traz exatamente esses votos e percentuais. O Rio Times tem contagens ligeiramente diferentes (56.104.049 e 53.876.219); usar as do TSE. O 2º turno em 25/out está confirmado na Wikipedia e no Rio Times. | [103][1][2] |
| V2 | Comparecimento de 78,92%; Cury 2,89%, Renan Santos 2,24%, Caiado 2,18%, Zema 0,27% | **CONFIRMADO** | Tudo confere no TSE: comparecimento de 78,92% (125.275.835), Cury com 3.448.569 votos, Renan com 2.675.887, Caiado com 2.605.148 e Zema com 326.488. | [103] |
| V3 | PL com 121 deputados | **NÃO VERIFICADO** | O TSE mostra o PL com 79 eleitos em 24 UFs. SP, MG e AM ainda estavam sem status de eleitos. O número é plausível, mas não está confirmado. | [103][2] |
| V4 | Tarcísio reeleito em SP com 62,85% | **CORRIGIDO** | Foi reeleito, mas com **62,65%** (TSE, final). Os 62,85% eram parciais da InfoMoney. | [103] |
| V5 | RJ: Ruas 49,31% × Paes 42,72%; DF: Celina 49,93% × Grass 34,48% | **CORRIGIDO** | Finais do TSE: **RJ com 49,27% × 42,76%** e DF com 49,93% × **34,47%**. Os demais governadores também foram atualizados para os finais (MG 55,40%, RS 58,05%, SC 68,98%, BA 55,80%, CE 53,19%, PE 53,27%; PR 50,10% confere). | [103] |
| V6 | 2º turno de governador em 6 ou 7 estados | **CORRIGIDO** | São **7**: AC, AM, DF, ES, RJ, RN e TO. O AM aparece sem status, mas o líder teve 40,63%. Há 20 estados decididos no 1º turno, como diz o Rio Times. | [103][2] |
| V7 | PL elegeu 16 senadores (parcial às 22h07) | **CORRIGIDO** | No TSE, com 52 das 54 vagas definidas (falta AM), o **PL tem 19 senadores**, contra 6 do PT e 6 do MDB. Michelle Bolsonaro e Bia Kicis estão eleitas pelo DF. A projeção de 28 de 81 cadeiras no total (Rio Times) é **NÃO VERIFICADO**. | [103][3][2] |
| V8 | EWZ +8,72% (US$ 41,52) no *overnight* de domingo | **CONFIRMADO** (retrato) | O PlatôBR/EM (04/10, 23h12) diz exatamente isso, e o número é coerente com o fechamento de US$ 38,19 de 02/out (Yahoo). Em horários posteriores: +10,29% (Rio Times) e ~US$ 42,66–42,74 (+11,6% a +11,9%) no Yahoo na madrugada de segunda. A liquidez é fina. | [9][2][108] |
| V9 | Vol implícita 1M do EWZ ~46% (máxima em 4 anos), realizada ~24%, OI de calls ~US$ 20 bi (maior desde 2007) | **NÃO VERIFICADO** | Na releitura, o OptionBeast (01/10) diz exatamente isso, inclusive o spread de ~22,5 vols, o maior em 8 anos, e o OI do início de setembro. Mas é fonte única (blog) e não houve dado independente da Cboe/OCC. Marcado [NÃO VERIFICADO] no corpo. | [14] |
| V10 | Ibovespa em 192.114,55 (+2,63%) em 02/out; Brent a US$ 102,25; payroll +29 mil | **CONFIRMADO** | O Yahoo mostra ^BVSP em 192.114,55 (+2,627%) e BZ=F com fechamento de 102,25. O BLS confirma +29 mil, desemprego de 4,2%, julho revisado para −10 mil e agosto para +133 mil. Extra: a variação semanal do Ibovespa é de **+4,71%** (script sobre o Yahoo), então os +5,81% da Forbes parecem errados. | [10][106][108] |
| V11 | Copom cortou de 14,00% para 13,75% em 16/set, unânime, 5º corte seguido desde março | **CONFIRMADO** | A série SGS 432 mostra 15,00% para 14,75% (19/03), 14,50% (30/04), 14,25% (18/06), 14,00% (06/08) e 13,75% (17/09). A CNN Brasil confirma a unanimidade e o "5º corte seguido desde março". | [104][17] |
| V12 | Próximos Copom em 3–4/nov e 8–9/dez; sem reunião em outubro | **CONFIRMADO** (nov) / **NÃO VERIFICADO** (dez) | A SGS 432 já publica 13,75% vigente até 04/11, o que é coerente com uma reunião em 3–4/nov e nenhuma em outubro. A data de 8–9/dez não foi confirmada em fonte primária, porque as páginas do BCB e da Okai bloquearam a leitura. | [104][20] |
| V13 | Dívida bruta de 82,9% do PIB em ago/2026 | **CONFIRMADO** (com ajuste) | A SGS 13762 dá 82,86% (jul: 82,56%). **Ajuste:** é o maior nível desde **mar/2021** (85,1%), e não "desde 2020". O valor de R$ 11,1 tri **NÃO VERIFICADO**. | [104][23] |
| V14 | IPCA-15 de set/2026 em +0,70% m/m e 4,47% em 12 meses | **CONFIRMADO** | A SGS 7478 mostra 0,70% em setembro. O script reproduz os 4,47% em 12 meses a partir da mesma série. O consenso de 0,53% e os grupos (alimentação e habitação) não foram re-checados. | [104][22] |
| V15 | FOMC +25 bp para 3,75%–4,00% em 16/set, 12–0 | **CONFIRMADO** | O comunicado do Fed diz "raise the target range... by 1/4 percentage point to 3-3/4 to 4 percent", com voto de 12–0. A mediana do *dot plot* de 4,1% para 2026 está confirmada na Tabela 1 do SEP. | [36][107] |
| V16 | Kevin Warsh é presidente do Fed desde 22/mai/2026 | **CONFIRMADO** | A página oficial do Board lista Warsh como *Chairman* (e Powell segue como governador). A data de 22/mai/2026 vem da Wikipedia, que dá o fim do mandato de Powell como chair nesse dia. | [111][39] |
| V17 | UST 10y com pico de 5,34% (maior desde 2002), DXY ~102 (máxima de 17 meses), probabilidade de alta em outubro de 25–28% | **CORRIGIDO** (parcial) | O pico de 5,34% é intradiário (máxima do ^TNX em 01/out: 5,342). No Treasury CMT, 5,29% em 30/set é o maior fechamento desde mai/2002. **O fechamento de 02/out foi 5,28%, e não 5,175%** (esse número não aparece nem na fonte, que fala em "near 5.25%"). O DXY ~102 está confirmado: 102,19 em 05/out, e o último nível ≥ 102 foi em abr/2025. Os 25–28% estão na fonte, mas são **anteriores ao payroll**. | [105][108][40] |
| V18 | Brent a US$ 100,83 em 05/out, +54% no ano | **CORRIGIDO** | O preço é um retrato intradiário: na releitura, o TE mostra US$ 103,07, e o Yahoo ~101,9–102,3. Os "+54%" são **variação em 12 meses** (o TE agora mostra +57,43% tanto em "YTD" quanto em "same time last year"). O front-month fechou 2025 em US$ 60,85, então o YTD é bem maior. | [42][108] |
| V19 | Escondida paralisada desde 23/set; LME a US$ 14.253,50/t em 01/out; recorde em setembro | **CORRIGIDO** | A própria fonte [46] diz que as operações pararam em 23/set depois da **morte de um terceirizado**, com **retomada gradual no dia seguinte**. Os supervisores votaram com 95% para **autorizar** greve, sujeita a mediação. **A mina não está parada por greve.** O LME a US$ 14.253,50 e o recorde de ~US$ 14.875/t conferem na fonte. O pico do COMEX em US$ 6,83/lb em 22/set confere no Yahoo (HG=F). Extra: os "+30,9% no ano" do cobre no TE são **em 12 meses**, não YTD. | [46][47][108] |
| V20 | Banxico manteve 6,50% em 24/set (unânime, 3ª manutenção) | **CONFIRMADO** | A página oficial do Banxico lista manutenção em 24/09, 06/08 e 25/06 e cortes em 07/05 e 26/03. A Infobae confirma a unanimidade e a inflação geral subindo de 3,10% para 3,42%, com a subjacente caindo de 3,95% para 3,79%. | [55][56] |
| V21 | Próxima decisão do Banxico em 05/nov | **CONFIRMADO** [S] | O calendário do TE mostra 05/11 e depois 17/12. O calendário oficial do Banxico não foi lido. | [58] |
| V22 | USMCA: os EUA não renovaram em 01/jul, o que abriu revisões anuais; acordo em vigor até 2036 | **CONFIRMADO** | A Wikipedia diz: "On July 1, 2026, the United States announced it would not renew"; as revisões anuais seguem até 01/07/2036. A White & Case bloqueou a leitura (403). | [109][64] |
| V23 | México confiante num acordo para cortar as tarifas da Seção 232 antes das *midterms* | **NÃO VERIFICADO** | A Bloomberg bloqueou a leitura (403) e não houve fonte independente acessível. Também **NÃO VERIFICADO**: a proposta mexicana de 5%–10% para veículos, ausente de [65] e [66]. Confirmados: as tarifas de 50% (aço e alumínio) e 25% (autos), a exigência de 50% de conteúdo dos EUA, a regra de 40% a ≥ US$ 16/h e o mínimo estatal de 54% na energia [65][66]. | [67][65][66] |
| V24 | USD/MXN em 18,1637 em 02/out; 4ª semana seguida de depreciação | **CONFIRMADO** | El CEO (releitura) dá 18,1637 (Banxico), +0,71% para o peso no dia, −2,58% na semana e 4 semanas seguidas. A N+ dá o fechamento oficial anterior em 18,2928 e a mínima intradiária em 18,4330, a pior desde nov/2025, o que é coerente. | [60][61] |
| V25 | YTD (NAV TR): EWZ +17,76% (até 01/out), ILF +13,87% (até 02/out), EWW +2,13% (até 01/out) | **CORRIGIDO** (data do ILF) | Os três números conferem no iShares. EWZ e EWW batem com o retorno ajustado do Yahoo até 01/out (~18,0% e ~2,12%). Para o ILF, o Yahoo dá ~14,0% até 01/out contra ~16,3% até 02/out, então os **+13,87% são, provavelmente, até 01/out**. | [51][52][53][108] |
| V26 | BCCh manteve a TPM em 4,50% em 08/set; próxima RPM em 27/out | **CONFIRMADO** [S] | Na releitura, o TE confirma 4,50% em 08/09 por unanimidade, inflação de 4,1% (subjacente de 3,3%) e próxima reunião em 27/10. O comunicado e o calendário do BCCh bloquearam a leitura automatizada. | [75] |
| V27 | Kast tomou posse em 11/mar/2026; o ministro da Fazenda é Jorge Quiroz | **CONFIRMADO** | Na releitura, a Wikipedia confirma: posse em 11/03/2026, vitória em 14/12/2025 com mais de 58%, Quiroz na Fazenda e aprovação de 57%, 42%, 34% e 35–40%. Também **NÃO VERIFICADO**: a reforma do IR corporativo de 27% para 23%, que não aparece na fonte. | [77] |
| V28 | De la Espriella venceu o 2º turno com 49,66% × 48,70% (21/jun) e tomou posse em 07/ago | **CONFIRMADO** | As Wikipedias em espanhol e em inglês trazem 12.960.166 votos (49,66%) contra 12.708.312 (48,70%). A posse em 07/08/2026 aparece na versão em espanhol. | [81][110] |
| V29 | BanRep subiu para 12,25% em 30/set (placar 4–2–1) | **CONFIRMADO** | A Valora Analitik confirma a alta surpresa para 12,25% em 30/09, com o mercado esperando 12%. O TE confirma o placar: 4 votos pela alta, 2 pela manutenção e 1 por +50 bp. Nota: a Valora cita desemprego de 9,4% em agosto, e o TE cita 9,1% para o urbano. | [83][84] |
| V30 | Orçamento 2027 da Colômbia de COP 634,9 tri; déficit de 9,4%–9,5% do PIB; déficit de 2026 de 7,2% | **CORRIGIDO** | Os números conferem, mas a fonte diz que o PGN foi **reapresentado em 29/ago**, depois que o Congresso devolveu a versão de COP 575,6 tri. **Não confirma a aprovação final**, então o texto "o Congresso aprovou" foi removido. | [85] |
| V31 | Keiko Fujimori venceu com 50,14% × 49,86% (07/jun) e tomou posse em 28/jul | **CONFIRMADO** (arredondamento) | Os votos são 9.223.396 contra 9.173.755, uma diferença de 49.641. A Wikipedia em inglês traz 50,13% × 49,87%, que é o que os votos implicam. A posse em 28/07 e a proclamação em 03/07 vêm da Wikipedia em espanhol. | [89][110] |
| V32 | BCRP em 4,25% (10/set, 12ª manutenção); próxima reunião em 07/out | **CONFIRMADO** (taxa) / **CONFIRMADO** [S] (data) | A Infobae confirma 4,25% em 10/09, mantida desde set/2025. O TE confirma a 12ª pausa seguida e a próxima decisão em 07/10. O calendário do BCRP bloqueou a leitura. | [91][92] |
| V33 | Risco-país da Argentina em 607 pb em 30/set (+95 no mês); mayorista em 1.517; bancos de −15% a −18% em setembro | **CONFIRMADO** | Na releitura, La Nación confirma: 607 pb, +95 no mês (+18,6%), o primeiro nível acima de 600 desde 07/04, mayorista em 1.517, MEP em 1.542,56, CCL em 1.616,44, teto da banda em 1.919,40, Supervielle −18,1%, BBVA −15,3% e Macro −15,1%. O Merval em 2.819.323 também confere no Yahoo. | [96][108] |
| V34 | "Bazuca" de US$ 75 bi; a EcoGo estima capacidade de US$ 25–45 bi | **CONFIRMADO** | Na releitura, a Infobae (03/10) confirma: 20 + 20 (swap EUA) + 20 (swap China) + 15 (futuros), EcoGo com US$ 25–45 bi e teto do FMI para futuros de US$ 9 bi. | [99] |
| V35 | FOMC em 27–28/out/2026 | **CONFIRMADO** | O calendário oficial do Fed traz 27–28/out e depois 8–9/dez (este com SEP). | [37] |

**Resumo.** Foram verificadas 35 afirmações:
- **23 CONFIRMADAS**: V1, V2, V8, V10, V11, V12 (nov), V13, V14, V15, V16, V20, V21, V22, V24, V26, V27, V28, V29, V31, V32, V33, V34 e V35. Destas, V21, V26 e V32 (data) dependem só de fonte secundária, o TE. V13 teve um ajuste de redação (de "desde 2020" para "desde mar/2021").
- **9 CORRIGIDAS**: V4, V5, V6, V7, V17, V18, V19, V25 e V30.
- **3 NÃO VERIFICADAS**: V3, V9 e V23. Também ficaram sem verificação a data de dezembro do Copom (V12), os R$ 11,1 tri (V13), a reforma do IR corporativo no Chile (V27) e a proposta mexicana de 5%–10% (V23).

**Impacto para o livro [I]:**
- A correção de **Escondida** muda a leitura do par CL/PE-1. O prêmio de oferta de cobre depende de uma greve **potencial**, sujeita a mediação, e não de uma paralisação em curso.
- A correção do **UST 10y** (5,28% no fechamento, e não 5,175%) reforça o regime de juros americanos altos.
- A vol implícita do EWZ, que justifica começar na parte baixa da banda de vol, é **[NÃO VERIFICADO]**. Recomenda-se medir a vol implícita diretamente na camada de dados (cadeia de opções do EWZ) antes de usá-la no modelo de risco.

---

*Fim do documento 05. Próxima atualização recomendada: segunda-feira, 2026-10-12. Como a B3 estará fechada nesse dia, a atualização é necessária para o rebalanceamento de terça. Antes disso, incorporar as pesquisas de 2º turno, o IPCA de setembro e a ata do FOMC.*
