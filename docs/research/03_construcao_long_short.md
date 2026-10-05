# Construção e Gestão de Risco de uma Carteira Long/Short *Market Neutral* de Alfa Puro — Especificação Implementável para um Fundo LatAm

> **Documento de pesquisa 03 — Fundo Long/Short Equities LatAm (USD, *net neutral*)**
> **Data de referência:** segunda-feira, 2026-10-05 (último pregão completo: sexta-feira, 2026-10-02)
> **Mandato:** NAV inicial de US$ 100.000.000; vol-alvo *ex-ante* de 5% a.a. (banda de 3% a 7%); *dollar neutral*, com neutralidade de beta e de fatores; linhas locais (B3, BMV, Santiago, BVC, BVL, BYMA) e ADRs; rebalanceamento semanal decidido pelo PM humano na segunda-feira.
> **Escopo:** (1) modelos de risco; (2) alfa; (3) otimizador (cvxpy); (4) vol-target, alavancagem e controle de *drawdown*; (5) monitoramento e atribuição. Ao final há uma tabela de parâmetros *default* e uma lista numerada de fontes.
> **Convenção de evidência:**
> - **[F]**: fato verificado em fonte primária, lida nesta sessão.
> - **[S]**: fonte secundária (blog, tese, agregador) ou primária não relida nesta sessão.
> - **[R]**: referência canônica da literatura, citada de memória e não relida nesta sessão.
> - **[C]**: número que calculamos com código nesta sessão (simulação com semente fixa, ver §4.5).
> - **[I]**: inferência ou recomendação nossa.
>
> **Invariante do repositório (AGENTS.md):** todos os números de produção (retornos, riscos, pesos, contribuições, *rankings*) vêm de código Python determinístico e testado; o LLM **nunca** os calcula. Este documento especifica *o que* o código deve calcular.

---

## Sumário executivo

1. **Modelo de risco: fundamental, com camada estatística *híbrida*.** O núcleo deve ser um modelo multifatorial em USD, no estilo Barra USE4/EMM1: um fator de mercado regional, fatores de país (BR, MX, CL, CO, PE, AR), fatores de setor (GICS nível 1, fundidos quando ralos) e 8 *styles* (Beta, Size, Momentum, Residual Volatility, Value, Liquidity, Quality/Leverage e **FX Sensitivity**). A estimação é por WLS *cross-sectional* diária, com pesos √(market cap) e restrições de soma zero nos fatores de país e setor.
   - Parâmetros de partida, do USE4S: meia-vida de 84 dias para a vol dos fatores, 504 dias para a correlação (usaremos 252), *Newey-West* de 5 e 2 *lags*, *Volatility Regime Adjustment* com meia-vida de 42 dias, *Eigenfactor Risk Adjustment* com *a* = 1,4 e *shrinkage* bayesiano do risco específico com *q* = 0,1 **[F]**.
   - Por cima do núcleo, 3 fatores estatísticos (PCA dos retornos específicos) entram só na previsão de risco **[I]**.
   - Em emergentes, **país domina indústria** como fonte de risco (EMM1, 1997–2014) **[F]**. Por isso a neutralidade por país é obrigatória.
2. **ADR e ação local são o mesmo emissor.** O otimizador decide pesos **por emissor**, e a camada de execução escolhe a linha (ADR ou local) pelo menor custo total: *spread*, impacto, aluguel e câmbio. Tratar as duas linhas como ativos com risco específico independente cria uma falsa diversificação, que o otimizador exploraria **[I]**.
   - A exposição cambial é medida pela **moeda econômica do emissor**, não pela moeda de listagem: um ADR da Petrobras carrega BRL.
3. **O alfa é residualizado e escalado pela regra de Grinold.** O *pipeline*:
   1. *winsorize* em ±3σ (robusto);
   2. *z-score*;
   3. neutralização por país e setor;
   4. combinação ponderada por IC (com *shrinkage* para pesos *a priori*);
   5. **ortogonalização em relação a todos os fatores de risco** (alfa puro);
   6. α = IC × σ_residual × score (Grinold, 1994) **[F]**.

   Na prática, um IC "bom" é 0,05 e um "muito bom" é 0,10 **[F]**. Usamos IC *a priori* de 0,04 no horizonte de 8 semanas **[I]**.
4. **Os sinais com melhor evidência em emergentes e LatAm são:**
   - **momentum residual/idiossincrático** (funciona em emergentes; nos EUA, Sharpe de 0,48 contra 0,25 do momentum convencional) **[F]**;
   - **value** (CF/P) e **qualidade/rentabilidade** (lucratividade bruta, emissão líquida de ações) **[F]**;
   - **revisões de lucro** (retornos anormais em emergentes sem reversão em até 5 anos) **[F]**;
   - **baixa volatilidade** (evidência forte em EM agregado **[F]**, mas fraca ou ausente em LatAm segundo fonte secundária **[S]**);
   - ***short-term reversal*** (positivo em emergentes, porém concentrado em papéis pequenos, ilíquidos e voláteis, e caro de operar) **[F]**.
5. **O otimizador segue o "Markowitz++" (Boyd, Kahn et al., 2024)** **[F]**. Ele maximiza o alfa robusto, descontados o custo de transação (meio *spread* + impacto em |z|^{3/2}) e o custo de aluguel. A **vol entra como restrição explícita** (σ_wc ≤ σ_alvo), não como aversão a risco. As demais restrições, todas convexas:
   - *dollar-neutral* (|Σw| ≤ 1% do NAV) e *beta-neutral* (|Σwβ| ≤ 0,05);
   - neutralidade por país e setor (≤ 5% do NAV) e limites de *style* (≤ 0,15);
   - risco fatorial ≤ 0,6·σ_alvo (≤ 36% da variância);
   - limites assimétricos por papel (long 4%, short 2,5%);
   - ADV (20% de participação; 3 dias para liquidar longs, 2 dias para shorts);
   - *turnover* semanal;
   - teto de *short squeeze* e de taxa de aluguel.
6. **Para 5% de vol, o *gross* esperado fica entre 1,1x e 2,2x do NAV** **[C]**. Plataformas *multi-manager* rodam 400–600% de *gross* e fundos *market neutral* 200–400% **[F]**. LatAm exige muito menos alavancagem porque o risco específico por papel é maior, na ordem de 25–35% a.a. (hipótese a medir **[I]**). O teto de 2,5x do `fund.yaml` é adequado.
7. **Otimizadores subestimam o risco.** Carteiras otimizadas sistematicamente realizam mais vol do que o previsto (USE4: os 100 portfólios otimizados testados ficaram fora do intervalo de confiança, por subprevisão) **[F]**. A política proposta:
   - meta *ex-ante* = 5%/B̂, com B̂ = 1,10 *a priori* (meta efetiva de ≈ 4,55%) até haver 26 semanas de histórico;
   - depois disso, B̂ é a *bias statistic* móvel, com IC de 95% de 1 ± √(2/T) **[F]**;
   - banda de não-rebalanceamento de ±15% em torno da meta.
8. **Os *stops* de *drawdown* devem ser calibrados em unidades de vol.** Em simulação, com σ = 5% e Sharpe 1,0, a probabilidade de atingir o DD em 12 meses é **62% para −3%, 20% para −5% e 5% para −7%** **[C]**. Os *stops* do `fund.yaml` (−3% e −5%) disparam com frequência para um gestor *com* habilidade. Recomendamos:
   - *soft stop* em −4%: reduzir o risco para 70%;
   - *hard stop* em −7%: reduzir o risco para 40%, com nova aprovação do PM e do comitê de risco;
   - revisão obrigatória se o mês fechar em −2,5% **[I]**.

   Como referência, plataformas como a Millennium cortam metade do capital do *pod* em −5% e o encerram em −7,5% (WSJ via terceiros) **[S]**.
9. **Liquidez e *squeeze* são restrições de primeira classe.**
   - **Liquidez [F]:** a prática de mercado é modelar no máximo 20% do ADV de 60 dias, com testes de estresse a 10% e 5%. *Shorts* "grandes" ficam em torno de 5% do NAV e *longs* em torno de 10%. Usamos 2,5% e 4%, mais conservador.
   - **Aluguel [F]:** em *squeezes*, a taxa passa de 10% a.a. e pode superar 50% a.a. Na B3 (dez/2025), papéis líquidos como TAEE11 e ABEV3 chegaram a 9,38% e 5,32% a.a. de aluguel. O custo de aluguel **entra no objetivo** e há teto de 8% a.a.
   - ***Days-to-cover* [F]:** é o melhor preditor de retorno ruim entre as medidas de *short interest*. Por isso é também alfa para o lado vendido, e o tratamos com **limite de tamanho**, não com exclusão.
10. **O monitoramento e a atribuição separam P&L fatorial de específico.**
    - **Métricas:** Sharpe idiossincrático, *hit rate*, *slugging ratio*, TC realizado e alfa long × short.
    - **Riscos:** *crowding* (métricas MSCI: valuation, *short interest*, *turnover*, volatilidade, reversão), VaR 99% e ES 97,5% em 1 dia por *filtered historical simulation*, e estresses históricos LatAm repetidos com dados reais pelo código.

**Divergências em relação ao `configs/cdp/fund.yaml` atual (para decisão do orquestrador) [I]:**
- **Drawdown:** −3%/−5% → recomendamos −4%/−7%, com corte de risco escalonado (§4.4).
- **`max_weekly_turnover`:** 0,60 → recomendamos 0,30 do NAV (Σ|Δw|) como teto rígido. A 15 bps por US$ negociado, 60% do NAV por semana custam ≈ 4,7% a.a., mais que o alfa esperado [C].
- **`specific_shrinkage`:** 0,3 → no estilo USE4, *q* = 0,1 com *prior* por quintil de tamanho. A semântica é outra; ver §1.5.
- **`newey_west_lags`:** 2 → 3 para a vol dos fatores (preços defasados em LatAm), mantendo 2 para a correlação.
- **Itens novos:** vol *ex-ante* efetiva = 5%/B̂ (B̂ *a priori* = 1,10); restrição de risco fatorial em forma convexa (‖F^{1/2}Xᵀw‖ ≤ 0,6·σ_alvo); limite de risco por papel |w_i|·σ_ε,i ≤ √0,08·σ_alvo; ADTV mínimo de US$ 5 mi para shorts; exposição cambial por moeda econômica ≤ 5% do NAV.

---

## 0. Premissas, unidades e notação

- **Moeda-base e retornos.** Todos os retornos estão em **USD** e são retornos totais (com dividendos). A linha primária de cada emissor define o retorno usado na estimação.
- **Pesos.** w_i é o peso por emissor como fração do NAV, com sinal: positivo = long, negativo = short.
  - *Gross* = Σ|w_i|.
  - *Net* = Σw_i.
  - Beta da carteira = Σw_iβ_i, onde β_i é o beta contra o mercado LatAm.
- **Trades.** z = w − w_pre. *Turnover* semanal = Σ|z_i|, na convenção de dois lados, como fração do NAV.
- **Modelo de risco.** Σ = X F Xᵀ + Δ, com X a matriz de exposições N×K, F a covariância dos fatores K×K e Δ a matriz diagonal de variâncias específicas.
- **Universo de referência.** O MSCI EM Latin America teve vol anualizada de **19,48% (3 anos), 22,31% (5 anos) e 25,66% (10 anos)** até 30/09/2026 **[F]**. No índice "EM Latin America with Latin America Exposure" (82 papéis):
  - países: Brasil 60,88%, México 23,58%, Chile 6,36%, Peru 5,91% e Colômbia 3,27%;
  - setores: Financeiro 43,93% **[F]**.

  Ou seja, o universo é **concentrado em país e setor**, e várias células país×setor são ralas. Isso guia as regras de fusão de fatores (§1.4).

---

## 1. Modelos de risco

### 1.1 Fundamental multifatorial (Barra USE4/EMM1, Axioma)

**O que é [F].** O USE4 explica o retorno em excesso local de cada ação como:

```
r_n = f_c + Σ_i X_ni f_i + Σ_s X_ns f_s + u_n
```

Aqui f_c é o fator "Country" (exposição 1 para todas as ações), f_i são as indústrias, f_s os *styles* e u_n o retorno específico. Os fatores são estimados por **WLS**, supondo que a variância específica seja inversamente proporcional à **raiz quadrada da capitalização** (as maiores empresas têm menor risco idiossincrático). As somas das indústrias, ponderadas por capitalização, são restritas a zero. Os *styles* são padronizados com **média ponderada por capitalização = 0** e **desvio-padrão equiponderado = 1**, para que uma carteira de mercado tenha exposição ≈ 0 e as *large caps* não dominem a escala [1].

**Tratamento de *outliers* [F].** O algoritmo separa três grupos:
- valores tão extremos que são tratados como erro e removidos;
- valores legítimos mas grandes, aparados em ±3 desvios;
- o restante, sem ajuste.

Dados faltantes de exposição são imputados por regressão contra um subconjunto de fatores (indústria, tamanho), em nível de fator, não de descritor [1]. **Nota [I]:** em produção, a imputação deve ser **marcada** e nunca virar zero silencioso (invariante 5 do AGENTS.md).

**Parâmetros de covariância do USE4 (em dias úteis) [F] [1]:**

| Modelo | Meia-vida da vol dos fatores | *Lags* NW (vol) | Meia-vida da correlação | *Lags* NW (corr.) | Meia-vida do VRA |
|---|---|---|---|---|---|
| USE4S (curto prazo, horizonte de ~1 mês) | 84 | 5 | 504 | 2 | 42 |
| USE4L (longo prazo) | 252 | 5 | 504 | 2 | 168 |

| Modelo | Meia-vida da vol específica | *Lags* NW | Meia-vida da autocorrelação NW | Shrinkage bayesiano *q* | Meia-vida do VRA específico |
|---|---|---|---|---|---|
| USE4S | 84 | 5 | 252 | 0,1 | 42 |
| USE4L | 252 | 5 | 252 | 0,1 | 168 |

**Avanços do USE4 que devemos replicar [F] [1]:**
- **Eigenfactor Risk Adjustment.** Os autovetores de menor variância da covariância amostral têm risco subestimado, e as carteiras otimizadas "caem" justamente neles. Nos testes do USE4, as *bias statistics* de **100 carteiras otimizadas** ficaram **todas fora** do intervalo de confiança, por subprevisão. O ajuste é feito por Monte Carlo sobre a matriz amostral, com ajuste parabólico do viés simulado e escala empírica vS(k) = a·(vP(k) − 1) + 1, com **a = 1,4**. Os 15 primeiros autofatores recebem peso zero no ajuste.
- **Volatility Regime Adjustment (VRA).** Calcula a *bias statistic cross-sectional* dos fatores, B_t = √((1/K)Σ_k (f_kt/σ_kt)²), suavizada com meia-vida de 42 dias (USE4S). O resultado é um multiplicador λ_F que reescala as volatilidades sem alterar as correlações. Sem VRA, o padrão clássico é subprever o risco ao entrar numa crise e superprever depois.
- **Risco específico.** A série temporal de u_n é ponderada por EWMA (meia-vida de 84 dias) com ajuste NW. Para papéis com histórico curto, retornos com muitos zeros ou caudas excessivas, a série é combinada com um **modelo estrutural**, ln σ_n = Σ_k X_nk b_k + ε_n, com peso γ_n ∈ [0,1].
- **Shrinkage bayesiano.** Puxa o risco específico para a média ponderada por capitalização do **decil de tamanho**:

  ```
  σ_SH = v_n·σ̄(s_n) + (1−v_n)·σ̂_n
  v_n = q·|σ̂_n−σ̄| / (Δσ(s_n) + q·|σ̂_n−σ̄|)
  q = 0,1
  ```

  Sem esse ajuste, o modelo superprevê o risco dos papéis de alta volatilidade e subprevê o dos de baixa.

**EMM1 (Barra Emerging Markets) [F] [2].**
- Países, indústrias e *styles* são modelados como desvios em relação a um **fator de mercado regional**.
- Os fatores vêm de **regressões *cross-sectional* robustas diárias**, com EWMA de meias-vidas separadas e correção de correlação serial.
- Entre dez/1997 e jun/2014, **os fatores de país dominaram os de indústria** em emergentes, tanto em *mean absolute deviation* quanto em contribuição à volatilidade *cross-sectional*, embora a distância tenha diminuído com o tempo. Os *styles* tiveram importância comparável à das indústrias. Em 2012, um *sell-off* de alto beta fez os *styles* dominarem por um curto período.

**Axioma [F] [3].** Oferece variantes **fundamentais e estatísticas** para modelos regionais e globais. Os modelos estatísticos são descritos como "visão alternativa" capaz de captar fontes de risco ausentes do modelo fundamental. O AXEM4 (emergentes) usa **7 *styles* de mercado e 6 fundamentais**, com histórico desde 1997 e reestimação diária.

### 1.2 Modelos estatísticos (PCA/APCA)

- **Como funcionam [I]/[R].** Os fatores latentes são extraídos dos próprios retornos, por PCA ou PCA assintótica (Connor-Korajczyk). Precisam só de preços.
- **Vantagens:** captam fatores **transitórios** que não estão no modelo fundamental. Em LatAm, os exemplos são "trade eleitoral", choques de commodities, temas regulatórios e fluxo estrangeiro.
- **Desvantagens:**
  - a identidade dos fatores é instável (rotação, troca de sinal);
  - são pouco interpretáveis, o que atrapalha atribuição e restrições de neutralidade;
  - em janelas curtas, superajustam o ruído.
- **Uso recomendado:** **complemento**, não núcleo.

### 1.3 Modelos híbridos

- **Pesquisa recente [F] [4].** Tzikas, Candès, Hastie, Boyd, Kochenderfer e Kahn (arXiv 2605.12977, 13/05/2026) propõem **refinar e aumentar um modelo de fatores existente** com fatores estatísticos **transitórios** estimados por máxima verossimilhança. O método tem dois hiperparâmetros (número de fatores adicionais e meia-vida da ponderação dos retornos) e aceita retornos faltantes. Aplicado ao **Barra USE4 de curto prazo** em *large caps* dos EUA, captou estrutura que o modelo original não via.
- **Fator de alinhamento [F] [6].** Saxena e Stubbs propõem o *Alpha Alignment Factor* (AAF): um fator dinâmico adicionado ao modelo de risco **durante a otimização**. Ele corrige a subestimação de risco que surge da interação entre alfa, restrições e modelo de risco (os *Factor Alignment Problems*).
- **Recomendação [I]:**
  1. **Núcleo fundamental** (§1.4), usado nas restrições de neutralidade, nos limites e na atribuição.
  2. **Camada estatística**: **3 componentes principais** dos retornos específicos (janela de 252 dias, meia-vida de 126), adicionados a Σ **apenas** na restrição de risco.
  3. **Alarme** se o 1º PC dos resíduos explicar mais de 10% da variância específica *cross-sectional* por mais de 20 dias. Isso indica fator ausente: um tema político ou de commodity a investigar.
  4. **AAF opcional** na Fase 2, calibrado em *backtest*.

### 1.4 Estrutura de fatores proposta para LatAm (USD)

```
r_n(USD) = f_LatAm + f_país(n) + f_setor(n) + Σ_k X_nk·f_k + u_n
```

Há duas restrições: a soma ponderada por capitalização dos f_país é zero, e a dos f_setor também. Os pesos da regressão são √(mcap).

| Bloco | Fatores | Definição / descritores (*defaults* [I]) | Observações |
|---|---|---|---|
| Mercado | 1 (LatAm) | Exposição 1 para todos | Equivale ao "Country" do USE4 ou ao fator regional do EMM1 [1][2] |
| País | BR, MX, CL, CO, PE, AR | *Dummy* pelo **país de risco** (não pela bolsa). Ex.: Nu, MercadoLibre → país de risco dominante | Em USD, o fator país **já embute o câmbio** |
| Setor | GICS nível 1 (até 11) | Fundir setores com menos de 5 emissores ou peso efetivo pequeno (ex.: Saúde + Consumo Básico; Imobiliário + Utilidades), revendo a cada trimestre | O universo é 44% Financeiro [F][30] |
| Beta | 1 | Beta contra o índice LatAm, 252 dias, meia-vida de 63; com correção de Dimson (1 *lag*) para papéis com negociação defasada | Convenção Barra, de memória **[R]** |
| Size | 1 | ln(mcap em US$, *free float*) | — |
| Momentum | 1 | Retorno acumulado de 12 meses menos o último mês (convenção USE4: 504 dias, *lag* de 21, meia-vida de 126 **[R]**) | É **risco**; o alfa usa momentum **residual** (§2) |
| Residual Volatility | 1 | Combinação de vol diária (252 dias, meia-vida de 42), *range* acumulado de 12 meses e σ do resíduo da regressão de beta **[R]** | Fortemente colinear com Beta; ortogonalizar contra Beta e Size |
| Value | 1 | B/P e E/P (*trailing*, *point-in-time*) | — |
| Liquidity | 1 | *Turnover* de 1, 3 e 12 meses (log) **[R]** | Importante em LatAm |
| Quality/Leverage | 1 | Alavancagem (dívida/ativo) e ROE/ROA | — |
| **FX Sensitivity** | 1 | Beta do retorno em USD do papel contra a variação da moeda local/USD, **residual ao fator país**, em 252 dias, padronizado **dentro de cada país** | Separa exportadores (receita em USD) de domésticos; é o "fator câmbio" relevante para um fundo em USD [I] |

São cerca de 1 + 6 + ~9 + 8 ≈ **24 fatores** para algo como 150 a 250 emissores, ou seja, de 6 a 10 papéis por fator. Isso basta, desde que se respeite o mínimo de 5 papéis por fator de setor ou país. Argentina e Colômbia podem ter poucos nomes. Abaixo de 3 emissores com ADTV de pelo menos US$ 2 mi, o país é fundido num fator "Andino/Outros" para estimação, e o limite de exposição é aplicado por *dummy* de país (§3) [I].

**Fatores macro de monitoramento, fora da regressão [I].** Petróleo (Brent), minério de ferro, cobre, UST 10 anos e DXY. Calculamos betas de 252 dias com *shrinkage* e os usamos em **estresse** e em alertas, não como restrição dura.

**ADR × linha local [I].**
- **Uma variável por emissor.** O retorno de estimação vem da linha primária (a mais líquida em USD-ADV, ou a local).
- **Execução.** A escolha da linha minimiza meio *spread* + impacto (no tamanho planejado) + aluguel (shorts) + custo de câmbio (linha local).
- **Exposição cambial por moeda econômica.** A exposição em BRL de um ADR brasileiro é a mesma da ação local. O limite cambial é aplicado **por moeda econômica**.

### 1.5 Estimação passo a passo (especificação para o código)

1. **Universo de estimação (EU).** Emissores com mediana de ADTV de 63 dias ≥ US$ 2 mi, mcap ≥ US$ 300 mi e pelo menos 126 retornos válidos em 252 dias. Retornos com ≥ 5 zeros consecutivos são marcados como **stale**. Para eles, γ_n < 1 (*blend* estrutural) e o *lag* de beta é corrigido [I].
2. **Exposições.** Usar descritores *point-in-time*, com fundamentos defasados pela data de publicação mais 2 dias úteis. Então:
   - *winsorizar* a ±3σ, robusto (mediana ± 3 × 1,4826 × MAD);
   - padronizar: média ponderada por capitalização = 0, desvio-padrão equiponderado = 1 [1];
   - combinar os descritores e re-padronizar.
3. **Regressão diária.** WLS com pesos √mcap e restrições lineares (soma ponderada de país = 0, de setor = 0), resolvida por mínimos quadrados com restrição de igualdade. Na regressão, retornos com |resíduo| > 10σ são removidos (erro provável) e os entre 3σ e 10σ são aparados [1][I].
4. **Covariância dos fatores.**
   - vol EWMA com meia-vida de 84 dias e NW de **3** *lags* [I] (o USE4S usa 5 [F]; em LatAm o dado diário tem mais *stale prices*, mas 5 *lags* custam estabilidade com histórico curto);
   - correlação EWMA com meia-vida de **252 dias** e NW de 2 *lags* (o USE4S usa 504 [F], mas temos 3 anos de histórico e mais quebras de regime eleitorais);
   - VRA com meia-vida de 42 [F];
   - *Eigenfactor Adjustment* com a = 1,4 [F] e M = 1.000 simulações [I].
   - O número efetivo de observações de uma EWMA com meia-vida h é ≈ 2h/ln2 ≈ 2,9h: cerca de 242 obs. para h = 84 e 727 para h = 252 [C]. Com K ≈ 24, a matriz fica bem-condicionada.
5. **Risco específico.** EWMA com meia-vida de 84, NW de 5 *lags* e autocorrelação com meia-vida de 252 [F]. Depois:
   - *blend* estrutural para histórico < 126 obs. ou caudas excessivas;
   - *shrinkage* bayesiano com **q = 0,1**, com *prior* por **quintil** de tamanho (no USE4 são decis [F]; com ~200 nomes, decis teriam ~20 nomes) [I];
   - VRA específico com meia-vida de 42.
   - **Nota:** o `fund.yaml` hoje tem `specific_shrinkage: 0.3`. Se esse número representar um *blend* linear fixo de 30% para o *prior*, ele é mais simples porém mais agressivo que o USE4. Recomendamos o esquema adaptativo acima, ou documentar a semântica.
6. **Camada estatística (híbrida).** PCA dos resíduos u (252 dias, meia-vida de 126), com 3 fatores e variância residual reajustada para não contar o risco duas vezes [I].
7. **Validação contínua.**
   - ***Bias statistic*** B = desvio-padrão de (R_t/σ̂_{t−1}). Sob previsão perfeita, ≈ 95% dos valores ficam em **[1 − √(2/T), 1 + √(2/T)]** [F] [1]. Para T = 52 semanas, isso é **[0,80; 1,20]** [C]. Com curtose 5, só 86% dos valores caem no intervalo para T = 120 [F].
   - ***MRAD*** (*mean rolling absolute deviation*) da *bias statistic* de 12 meses. O ideal teórico sob normalidade é **0,17** [F] [1].
   - **Carteiras-teste:** testar fatores, autofatores, **carteiras otimizadas** e a própria carteira do fundo.

### 1.6 Requisitos mínimos de dados

| Dado | Mínimo | Ideal | Se faltar [I] |
|---|---|---|---|
| Preços diários ajustados (USD, linha primária) | 504 dias | 756–1.260 dias | Papel fora do EU; pode ser negociado só com risco estrutural e limites reduzidos à metade |
| Volume / ADTV em US$ | 63 dias | 252 dias | **Não negociável**: sem ADV não há limite de liquidez |
| Câmbio de fechamento coerente (mesmo horário das ações) | diário | WM/Reuters ou fechamento local | Bloquear |
| Capitalização e *free float* | trimestral | diário | Usar ações em circulação × preço, marcado como *proxy* |
| Fundamentos *point-in-time* (B/P, E/P, alavancagem, ROE) | 8 trimestres | 20+ trimestres | O fator correspondente vira faltante (imputado por regressão e **marcado**); **nunca zero** |
| Estimativas de analistas (revisões) | 6 meses | 5 anos | O sinal sai da combinação e os pesos são renormalizados, com aviso |
| *Short interest*, aluguel, utilização | quinzenal | diário | O *squeeze score* assume nível **médio** (conservador) para mcap < US$ 1 bi ou retorno de 1 mês > 15% (§5.5) |
| Classificação GICS / país de risco | atual | *point-in-time* | Classificação manual, com *log* |

**Alerta de *look-ahead* [I].** Fontes gratuitas (ex.: yfinance) trazem fundamentos **correntes**, não *point-in-time*. *Backtests* devem usar **só sinais de preço e volume** (momentum residual, reversão, baixa vol, liquidez). Os sinais fundamentais entram só em produção *live*, com selo de "não testado PIT".

---

## 2. Alfa

### 2.1 *Pipeline* de sinal → alfa (determinístico)

Para cada sinal k e data t:

1. **Descritor bruto** x_k, *point-in-time*.
2. ***Winsorização* robusta:** clip em mediana ± 3 × 1,4826 × MAD. O USE4 apara em ±3σ [1].
3. ***Z-score cross-sectional*** no universo investível: z = (x − média)/desvio. Alternativa: *rank* → normal inversa, mais robusta a caudas.
4. **Neutralização por país e setor:** z⊥ = z − D(DᵀVD)⁻¹DᵀVz, com D = *dummies* de país e setor e V = diag(√mcap). Opcionalmente, incluir Size e Beta em D. Re-padronizar.
5. **Combinação:** s = Σ_k ω_k z⊥_k, re-padronizado. Os pesos ω_k misturam:
   - 50% de pesos *a priori* (`fund.yaml`: momentum residual 0,25, reversão 0,15, value 0,20, quality 0,15, low-risk 0,10, revisões 0,15);
   - 50% proporcional ao **IC-IR** móvel de 36 meses (IC médio / desvio do IC), com ω_k limitado a [0; 0,40] e pesos negativos zerados [I].
   - A mistura com o *a priori* é um *shrinkage* contra *overfitting*. O IC de sinais individuais é ruidoso; com 36 observações mensais, o erro-padrão do IC médio é da ordem do próprio IC.
6. **Ortogonalização aos fatores de risco (alfa puro):** α⊥ = (I − X(XᵀWX)⁻¹XᵀW)·s, com X = **todas** as exposições do modelo de risco (mercado, país, setor, *styles*, FX) e W = diag(√mcap). É a projeção do score no espaço ortogonal aos fatores, ou seja, a parte do sinal que **não** é explicada por exposições sistemáticas [I], alinhado a [1][6].
7. **Escala de Grinold:**

   ```
   α_H,i = IC_H × σ_ε,i × √(H/52) × α⊥_i
   ```

   α_H,i é o retorno residual esperado no horizonte H, σ_ε,i o risco específico anualizado do modelo e IC_H o IC no horizonte H semanas [F] [7]. Para o otimizador semanal: α_sem,i = α_H,i / H. Os custos de transação são amortizados em H semanas (`amortization_weeks: 8` = H).
8. ***Trimming* final** de α em ±3 desvios *cross-sectional* e checagem de que |α_H| ≤ 2 × σ_ε,i·√(H/52), uma trava de sanidade [I].

**Por que ortogonalizar? [I].**
- Sem esse passo, um sinal de "value" alinhado ao *style* Value do modelo de risco faria o otimizador ou comprar o fator Value (proibido pela neutralidade) ou sofrer o *Factor Alignment Problem*: o alfa fica numa direção que o modelo de risco não "vê", e o risco realizado excede o previsto [6].
- A ortogonalização transforma value e momentum na **parte idiossincrática** desses sinais: value *dentro* do setor e país, além do *style* Value; momentum residual, além do momentum total.
- **Consequência prática:** medir o IC **após** a ortogonalização. Sinal sem IC residual sai da combinação.

**Portfólios característicos e fatores puros [R]/[F].**
- Grinold e Kahn definem o **portfólio característico** de um atributo a como h_a = Σ⁻¹a / (aᵀΣ⁻¹a). É a carteira de menor risco com exposição unitária a a.
- Num modelo de fatores, o retorno do fator obtido na regressão WLS é o retorno de um **portfólio de fator puro**: exposição 1 ao fator e 0 a todos os outros [1][2].
- **Teste de sinal recomendado [I]:** incluir o score como fator extra na regressão *cross-sectional* e acompanhar o retorno do "fator alfa puro", líquido de todos os fatores de risco. Esse é o retorno que o fundo realmente quer capturar.

### 2.2 Lei fundamental, *transfer coefficient* e expectativas

- **Lei generalizada [F] [5]:** IR = TC × IC × √BR (Clarke, de Silva e Thorley, 2002).
  - O TC mede quanto do sinal chega aos pesos. TC = 1 só na carteira ótima irrestrita; com restrições, TC < 1.
  - Restrições de *short* e de *turnover* são as mais restritivas.
- **Valores de referência [F] [7]:** IC "bom" = 0,05 e "muito bom" = 0,10 (MSCI Barra, 2010, citando Grinold).
- **Cálculo ilustrativo [C]**, com BR = N × 52/H, ou seja, apostas "independentes" por ano no horizonte H = 8 semanas. A premissa é **otimista**, porque sinais sobrepostos e correlacionados reduzem o BR efetivo:

| IC (8 sem.) | N emissores | TC = 0,4 | TC = 0,6 |
|---|---|---|---|
| 0,03 | 100 | IR 0,31 | IR 0,46 |
| 0,03 | 200 | 0,43 | 0,65 |
| 0,04 | 150 | 0,50 | 0,75 |
| 0,05 | 150 | 0,62 | 0,94 |
| 0,05 | 200 | 0,72 | 1,08 |

**Leitura [I].** A expectativa realista é um IR **bruto de custos** entre 0,5 e 0,9. Com σ = 5%, isso dá alfa bruto de 2,5% a 4,5% a.a. sobre o caixa. O **orçamento de custos** (transação + aluguel) deve ficar em até ~1/3 disso, ou seja, **≤ 1,0–1,5% do NAV ao ano**. Esse número dimensiona o teto de *turnover* (§3.4).

**Medir o TC realizado toda semana [I]:**

```
TC = corr(σ_ε,i·w_i , α_i/σ_ε,i)
```

A fórmula usa a aproximação diagonal [5]. Alarme se TC < 0,5 por 4 semanas: restrições demais "comendo" o alfa.

### 2.3 Sinais com evidência em emergentes e LatAm

| Sinal | Definição operacional (*default*) [I] | Evidência | Decaimento / horizonte [I] | Ressalvas |
|---|---|---|---|---|
| **Momentum residual (idiossincrático)** | Soma dos resíduos mensais (regressão de 36 meses contra mercado + país + setor) de t−12 a t−1, **dividida pelo σ dos resíduos** | Blitz, Hanauer e Vidojevic: retorno idiossincrático de 12 meses (excluindo o último) contra o FF3 de 36 meses, ajustado por vol. **Robusto em desenvolvidos e emergentes** (EM: 1992–2015). Nos EUA, Sharpe de 0,48 contra 0,25 do momentum convencional, com retorno mensal comparável (1,39% × 1,54%), vol menor e menos exposição a reversões. Enfraqueceu após o início dos anos 2000 **[F]** [9]. Original: Blitz, Huij e Martens (2011) **[R]** [10] | Meia-vida de 3 a 6 meses; bom para rebalanceamento semanal | Os *crashes* de momentum são menores na versão residual, mas existem |
| **Value** (CF/P, E/P, B/P dentro do setor) | Média dos *z* de CF/P e E/P *trailing* (B/P para financeiras) | Hanauer e Lauterbach (28 EM, jul/1995–jun/2016): **CF/P**, lucratividade bruta, emissão composta de ações e momentum são "pervasivos" (aparecem em *sorts* EW e VW e em regressões) **[F]** [8]. Em LatAm, value e momentum aparecem como os mais fortes e com correlação de −0,44 entre si (tese de mestrado, EUR) **[S]** [16] | Lento (anos) | Após a ortogonalização, sobra o value **idiossincrático** |
| **Quality / rentabilidade** | Lucratividade bruta / ativos, accruals (−), emissão líquida de ações (−) | Hanauer e Lauterbach **[F]** [8] | Lento | Fundamentos PIT são escassos em LatAm |
| **Revisões de lucro** | Variação de 1 e 3 meses do EPS de consenso FY1/FY2, escalada pelo preço; *breadth* de revisões | Em emergentes, estratégias de value, momentum e **revisões** geram excesso de retorno **não explicado** por risco local ou global; as revisões **não revertem** em até 5 anos (van der Hart, de Zwart e van Dijk, 2005) **[F]** [11] | 1 a 3 meses | Exige base de estimativas; sem ela, o sinal sai |
| **Baixa vol / *low-risk*** | −σ residual de 252 dias, **dentro de *buckets* de beta** | Em EM, o quintil de maior vol rende 4,4% a.a. menos que o de menor vol; *hedge* de baixa vol com alfa de 3 fatores de 5,7% a.a.; 15 de 19 países superam o mercado local em ≥ 5% a.a. (Blitz, Pang e van Vliet, 2012/13) **[F]** [12]. Hanauer e Lauterbach não acham relação positiva entre risco e retorno em EM **[F]** [8]. **Para LatAm (2003–2023), um estudo não encontra a anomalia** **[S]** [17] | Lento | **Conflito com beta-neutralidade:** dólar-neutro + beta-neutro impede a alavancagem do lado de baixo beta que monetiza o prêmio. Manter peso pequeno (0,10) e usar a versão residual |
| ***Short-term reversal*** (1 a 4 semanas) | −retorno residual das últimas 1–4 semanas, excluindo dias de *earnings* | Lucrativo em vários EM; **maior em papéis pequenos, ilíquidos e voláteis**, e quando a vol de mercado é alta (remuneração por prover liquidez) (Butt, Högholm e Sadaqat, 2021) **[F]** [13]. No Brasil, a lucratividade parece ter caído nos anos recentes (dissertação PUC-Rio) **[S]** [15] | **Rápido** (dias a semanas) | **Muito sensível a custos**: usar como *timing* de entrada e saída (*overlay* de execução) ou com peso baixo e penalização de *turnover* |
| ***Short interest / days-to-cover*** (lado vendido) | DTC = *short interest* / ADV (em ações) | DTC é melhor preditor de retorno ruim que o *short ratio*; o L/S por DTC rende **1,2% ao mês** (EUA) (Hong, Li, Ni, Scheinkman e Yan, NBER WP 21166, 2015) **[F]** [20] | Meses | **É também o principal indicador de risco de *squeeze***: entra como alfa **e** como limite de tamanho (§3.3, §5.5) |
| **Pesquisa de IA/LLM ("views")** | Score categórico −2..+2 com confiança, vindo de fichas estruturadas com citações | Ver doc 01: o padrão de sucesso é o LLM como **analista**, não decisor | 4 a 12 semanas | Convertido com **IC de 0,03** (`view_information_coefficient`), *tilt* ≤ 1,5 *z*; o LLM **só pode apertar** restrições de risco (`llm_can_only_tighten: true`) |

### 2.4 Integração com a decisão humana [I]

- **O que o otimizador gera.** Uma **proposta**: pesos por emissor, *trade list*, risco *ex-ante* e decomposição.
- **Como o PM ajusta.** Por meio de **views** (que viram α com IC_view) ou de **restrições** (proibir, limitar, forçar sinal). **Nunca editando pesos diretamente.** Isso preserva TC, rastreabilidade e o *hash* do FactBook.
- **Toda alteração gera nova otimização e novo *hash*.** A aprovação fica vinculada aos *hashes* (AGENTS.md, invariante 3).

---

## 3. Otimizador (cvxpy)

### 3.1 Restrição explícita de vol × aversão a risco

- **Recomendação de Boyd, Johansson, Kahn, Schiele e Schmelzer (JPM, 2024) [F] [14]:** impor o **risco como restrição dura** (σ_wc ≤ σ_tar) em vez de penalidade λσ².
  - Os parâmetros ficam **interpretáveis** (vol-alvo, limites de alavancagem e *turnover*), separados dos **dados** (Σ, *spreads*, volumes).
  - Os escalares de custo γ_hold e γ_trade começam em **≈ 1**.
- **Por que serve ao nosso mandato [I].** A vol-alvo de 5% **é** o mandato. Com λ, a vol realizada flutuaria com a escala do alfa, que muda toda semana com o IC e a dispersão dos scores. Com a restrição, o otimizador usa o orçamento de risco disponível. Pelo KKT, as formulações são equivalentes para algum λ, mas a restrição dispensa calibrar esse λ.
- **Robustez [F] [14]:**
  - **No retorno:** R_wc = αᵀw − ρᵀ|w|, com ρ_i = **percentil 20 de |α|**.
  - **No risco:**

    ```
    σ_wc² = σ² + ϱ(Σ_i Σ_ii^{1/2}|w_i|)²
    ```

    com **ϱ = 0,02**. Isso equivale a ±2% de incerteza nos elementos diagonais.
  - **Softening.** Risco, alavancagem e *turnover* podem virar penalidades com prioridades (γ_risk = 5×10⁻², γ_lev = 5×10⁻⁴ e γ_turn = 2,5×10⁻³ no paper, calibradas pelos multiplicadores de Lagrange). Isso evita inviabilidade em estresse.
  - **Resultados no paper (S&P 100, 17 anos fora da amostra, alfa sintético com IC de 0,15):**
    - Markowitz básico: Sharpe 0,19, alavancagem 9,3 e *drawdown* de 78,9%.
    - Markowitz++: Sharpe 4,32, *turnover* de 28, alavancagem de 1,8 e DD de 7%.
    - Os níveis absolutos não são implementáveis (viés de sobrevivência, alfa sintético); vale o contraste entre métodos.

### 3.2 Formulação (por emissor, semana t)

**Variáveis:** w ∈ ℝᴺ (peso por emissor) e z = w − w_pre. O caixa é implícito: c = 1 − Σw ≈ 1, porque o fundo é *dollar neutral*.

```
maximizar   α_semᵀ w − ρᵀ|w|                                    (alfa robusto, semanal)
            − γ_trade · [ κ_spreadᵀ|z| + κ_impactᵀ|z|^{3/2} ] / H_amort   (custo amortizado)
            − γ_hold  · κ_shortᵀ (−w)₊ / 52                       (aluguel semanal)
            − γ_soft  · (violações suavizadas)

sujeito a
 Risco        ‖ (L_Fᵀ Xᵀ w , D^{1/2} w , √ϱ·(s∘|w|)) ‖₂ ≤ σ_tar,eff = 5%/B̂      (hard: ≤ 7%)
 Fatorial     ‖ L_Fᵀ Xᵀ w ‖₂ ≤ 0,6 · σ_tar,eff                                  (≤ 36% da variância)
 Net          |1ᵀw| ≤ 0,01
 Beta         |βᵀw| ≤ 0,05   (meta operacional 0,02)
 País         |Σ_{i∈c} w_i| ≤ 0,05  ∀c ;  |Xᵀ_país w| (exposição ao fator) ≤ 0,05
 Setor        |Σ_{i∈s} w_i| ≤ 0,05  ∀s
 Styles       |Xᵀ_k w| ≤ 0,15  ∀k ∈ {Beta, Size, Mom, ResVol, Value, Liq, Qual, FX}
 Moeda econ.  |Σ_{i: moeda(i)=m} w_i| ≤ 0,05  ∀m
 Gross        ‖w‖₁ ≤ 2,5 ;   Σ(w)₊ ≤ 1,25 ;  Σ(−w)₊ ≤ 1,25
 Por papel    −s_i^max ≤ w_i ≤ l_i^max
              l_i^max = min(0,04 ; 0,20·ADV_i·3/NAV ; √0,08·σ_tar/σ_ε,i)
              s_i^max = min(0,025 ; 0,20·ADV_i·2/NAV ; √0,08·σ_tar/σ_ε,i ; cap_squeeze_i ; disponível_aluguel_i)
              s_i^max = 0 se não shortável, aluguel > 8% a.a., mcap < US$ 500 mi ou ADTV < US$ 5 mi
 Trade        |z_i| ≤ 0,20·ADV_i·D_trade/NAV ;  D_trade = 2 (semanal) ou 5 (inception)
 Turnover     ‖z‖₁ ≤ 0,30   (dispensado na inception)
 Views/PM     restrições adicionais do PM (só apertam)
```

- **Notação.** F = L_F L_Fᵀ (Cholesky) e s = vetor de vol total por emissor.
- **O limite de risco por papel é convexo e substitui o "risk share ≤ 8%" [I].** A condição |w_i|·σ_ε,i ≤ √0,08 · σ_tar garante que a contribuição específica de um papel à variância fique ≤ 8% da variância-alvo. Com σ_tar = 5%, isso é **|w_i|·σ_ε,i ≤ 1,41%**: σ_ε = 30% → |w| ≤ 4,7%; σ_ε = 50% → |w| ≤ 2,8%.
- **A restrição de risco fatorial também é convexa [I].** Exigir ‖L_FᵀXᵀw‖ ≤ 0,6·σ_tar limita a variância fatorial a ≤ 36% da variância-alvo, o que equivale a `max_factor_risk_share: 0.35`. A *razão* "fatorial/total" não é convexa; a forma absoluta é. A meta operacional é ≤ 25% de participação fatorial.
- **Dólar-neutro + beta-neutro simultâneos [I].** Com dólares iguais nos dois lados, a neutralidade de beta força o beta médio do lado comprado a igualar o do vendido. É exatamente o que queremos para alfa puro. O efeito colateral é anular a monetização do prêmio de baixo beta (*betting-against-beta* exige alavancar o lado de baixo beta), daí o peso pequeno do sinal *low-risk* (§2.3).

### 3.3 Restrições de liquidez, aluguel e *squeeze*

**Liquidez [F] [21].** "Muitos fundos" modelam a venda de **no máximo 20% do ADV dos últimos 60 pregões". Estimativas a **10% ou 5%** são mais conservadoras, para estresse. *Longs* em torno de **10% do NAV** e *shorts* em torno de **5%** são considerados "grandes". Nossos parâmetros [I]:
- **ADV.** Mediana de 63 dias, robusta a *block trades*; usa-se o **mínimo** entre as medianas de 21 e 63 dias.
- **Participação.** 20% no caso-base e 10% no estresse.
- **Dias para liquidar.** *Longs* ≤ 3 dias a 20% (≤ 6 dias no estresse); *shorts* ≤ 2 dias. A recompra forçada num *squeeze* acontece justamente quando o ADV "útil" some.
- **Carteira.** ≥ 80% do *gross* liquidável em 3 dias e 100% em 10 dias (caso-base).
- **Capacidade a US$ 100 mi [I].** Com *gross* de 2,0 e cerca de 120 emissores, a posição média é de US$ 1,7 mi. Um papel com ADV de US$ 3 mi comporta ~US$ 1,8 mi *long* (1,8% do NAV) e ~US$ 1,2 mi *short*. O universo LatAm líquido comporta o fundo com folga.

**Aluguel e *financing* [F] [21].**
- Papéis *hard-to-borrow* (pequenos, *crowded*, com muito varejo) têm taxas de *special* que "facilmente passam de 10% a.a." e podem superar **50% a.a. num *squeeze***.
- O *rebate* do caixa dos *shorts* subiu com os juros. Os *prime brokers* retêm **25–75 bps**.
- Episódios de desalavancagem (4T18, 1T20) elevaram margens e reduziram a disponibilidade de aluguel.

**B3 [F] [27].**
- O estoque de empréstimo de ações chegou a **R$ 180,14 bi em 10/12/2025** (recorde).
- Taxas de aluguel na mesma data: TAEE11 **9,38%**, ABEV3 **5,32%**, WEGE3 1,83% e BOVA11 1,38% a.a.
- Ou seja, **até *large caps* podem ter aluguel alto** na linha local. O ADR pode ser mais barato para o *short*, e a escolha de linha deve considerar isso.

**Infraestrutura de *short* por país [F] [26] (EquiLend, LatAm Securities Finance User Guide, out/2025):**
- **Brasil:** o empréstimo é **obrigatoriamente compensado por CCP** (B3/BTB). O tomador posta **100% do valor** mais margem adicional. Empréstimos são *pre-margined*, e a liquidação de *recall* pode demorar T+2/T+3. O acesso **sintético** (*swaps*) é em geral disponível para offshore. Regras de *short*: Resolução CVM 160/2022.
- **México:** empréstimo via Indeval/ValPre, liquidação T+0/T+1/T+2.
- **Chile:** empréstimo de ações permitido para *short*, em mercado OTC. Volume de **US$ 2,1 bi em 2024**.
- **Colômbia:** o **Decreto 1239/2024 eliminou a *uptick rule*** para *short*.
- **Peru:** exige *uptick/at-tick rule*. O empréstimo é incipiente. O sintético para estrangeiros fica em geral limitado a constituintes do MSCI.
- **Implicação [I]:** shorts locais concentrados em BR (e MX). Para CL, CO e PE, preferir **ADR** ou *swap*. Para AR, **só ADR** (ver doc 04).

***Squeeze*** — regras no otimizador e no *pre-trade* [I], com *thresholds* do `fund.yaml`:

| Indicador | Médio | Alto |
|---|---|---|
| *Short interest* % *free float* | 5% | 15% |
| *Days to cover* | 3 | 7 |
| Taxa de aluguel | 3% a.a. | 8% a.a. |
| Retorno de 1 mês | +15% | +30% |
| *Free float* mcap | — | < US$ 1 bi aumenta o score |

- **Score 0–100 (§5.5).** Médio (≥ 40) → s_i^max × 0,5 e sem novas aberturas. Alto (≥ 70) → **zerar em até 2 dias**. **Soma dos shorts com score ≥ médio ≤ 5% do NAV.**
- **A faixa 0–2 / 3–7 / 8+ dias de DTC é heurística de mercado [S] [33]**, coerente com os *thresholds* acima.
- **Catalisadores qualitativos.** OPA/fechamento de capital, M&A, inclusão em índice e recompra do controlador são **sinalizados pela pesquisa LLM**, só para **apertar** limites.

### 3.4 Modelo de custo de transação

**Forma funcional [F] [14][18]:**

```
custo_i (fração do NAV) = κ_spread,i·|z_i| + κ_impact,i·|z_i|^{3/2}
κ_impact,i = Y · σ_i,diária · (NAV / ADV_i)^{1/2}
```

- É a **lei da raiz quadrada**: o impacto médio de uma *metaordem* Q é Δ = Y·σ_diária·√(Q/V), com **Y "de ordem unitária"**.
- O expoente empírico δ varia entre **0,4 e 0,7**. Almgren et al. obtêm δ ≈ 0,6 em 700 mil ordens da Citigroup; na CFM (500 mil *trades* em futuros), δ ≈ 0,5 para *tick* pequeno e ≈ 0,6 para *tick* grande, com Q/V de alguns 10⁻⁴ a alguns %.
- **Regra de bolso:** negociar 1% do volume diário move o preço cerca de 1/10 da vol diária [F] [18].
- Boyd et al. usam κ_impact = a·s_i·v_i^{−1/2}, com **a de ordem 1** [F] [14].
- Frazzini, Israel e Moskowitz (US$ 1,7 tri de execuções reais, 21 mercados desenvolvidos, 1998–2016) acham custos reais **uma ordem de grandeza menores** que estudos anteriores, também com modelo de raiz quadrada [F] [19]. **Não cobre emergentes**: para LatAm, usamos coeficientes conservadores.

***Defaults* LatAm [I]** (iguais ao `fund.yaml`, que consideramos razoáveis):

| Componente | Valor | Justificativa |
|---|---|---|
| **Meio *spread*** por *tier* de ADTV (> US$ 50 mi / 15–50 / 5–15 / < 5 mi) | 4 / 8 / 15 / 25 bps | Calibrar com *spreads* observados (*quotes* de fechamento) assim que houver dado; recalibrar trimestralmente com o *implementation shortfall* realizado |
| **Y** (`impact_coefficient`) | 0,6 | Dentro de "ordem 1" [18]. Em LatAm, Y pode ser maior em *small caps* → usar Y = 1,0 no estresse |
| **Corretagem + emolumentos** (bps) | US 1, BR 3, MX 8, CL 10, CO/PE/AR 15 | Inclui emolumentos e taxas locais. Validar com o *prime broker* (doc 04) |
| **Câmbio** (linha local) | 3 bps por conversão | — |
| **Amortização** | 8 semanas (= horizonte do alfa) | — |
| **Orçamento de custos** | ≤ 1,0–1,5% do NAV a.a. | §2.2 |

**Turnover × custo [C]** (custo médio de ida, por US$ negociado):

| *Turnover* semanal (Σ\|z\|/NAV) | Anual | Custo a 10 bps | a 15 bps | a 25 bps |
|---|---|---|---|---|
| 10% | 5,2x NAV | 0,52% | 0,78% | 1,30% |
| 20% | 10,4x | 1,04% | 1,56% | 2,60% |
| 30% | 15,6x | 1,56% | 2,34% | 3,90% |
| **60% (`fund.yaml` atual)** | 31,2x | 3,12% | **4,68%** | 7,80% |

**Recomendação [I].** Teto rígido de **30% do NAV por semana** e regime típico de 10% a 20%, induzido pela penalidade de custo, não pelo teto. Se o 0,60 do `fund.yaml` foi pensado como fração do *gross* (≈ 1,2x NAV), ele é ainda mais folgado. A *inception* é isenta do teto, com rampa de até 5 dias a 20% do ADV.

**Aluguel no objetivo [F] [14].** φ_hold = κ_shortᵀ(−w)₊ (taxa anual/52 por semana). *Defaults* do `fund.yaml`: GC de 0,3% a.a. nos EUA e 0,8% a.a. no BR, teto de 8% a.a. O *rebate* do caixa entra na atribuição (§5.2), não no otimizador, porque é constante numa carteira dólar-neutra.

### 3.5 Lotes, posição mínima e não-convexidades

**Pós-processamento determinístico [I]:**
1. Resolver o problema contínuo.
2. **Posição mínima.** Zerar |w_i| < 0,2% do NAV (`min_position_weight`) e **re-resolver** com esses emissores fixos em zero. É a heurística convexa de Boyd et al. para *minimum nonzero holding* [F] [14].
3. **Escolha de linha** por emissor (§1.4).
4. **Arredondamento** para lote: 1 ação nos EUA/ADR; na B3, lote padrão (100 ações, com mercado fracionário disponível para o resto); nas demais bolsas, o lote local (validar no doc 04).
5. **Trade mínimo.** Ignorar |z_i| < 0,05% do NAV (US$ 50 mil), salvo zeragem.
6. **Reparo guloso** do *net* e do beta com os papéis mais líquidos, se o arredondamento violar |net| ≤ 1% ou |β| ≤ 0,05.
7. **Re-checar todas as restrições no código** e registrar no FactBook a diferença entre o contínuo e o arredondado.

### 3.6 Robustez operacional do otimizador [I]

- **Solver.** CLARABEL (já em `pyproject.toml`), com o ECOS ou o SCS como *fallback*. Tamanho do problema: N ≈ 250 e K ≈ 30, resolvido em menos de 1 s.
- **Inviabilidade.** Relaxar as restrições numa **ordem de prioridade documentada**: *turnover* → *styles* → setor → país → vol-alvo (até 7%). **Nunca** relaxar *net*, beta *hard*, limites de *short*/*squeeze* ou liquidez. Registrar o relaxamento no *audit log*.
- **Determinismo.** Mesmos inputs → mesmo output: ordenação estável dos emissores, tolerâncias fixas e versões travadas no `uv.lock`. O *hash* dos inputs entra na aprovação.
- **Teste de sanidade pós-solve.** Recalcular em numpy, fora do cvxpy, todas as métricas (vol, net, beta, exposições, liquidez) e comparar dentro da tolerância.

### 3.7 Esboço cvxpy (referência para `src/cdp/portfolio/`)

```python
import cvxpy as cp
import numpy as np

w = cp.Variable(n)                      # pesos por emissor (fração do NAV)
z = w - w_pre
fac = L_F.T @ (X.T @ w)                 # F = L_F L_F^T
spec = cp.multiply(np.sqrt(delta), w)   # delta = variância específica (anual)
rob = np.sqrt(varrho) * (vol_total @ cp.abs(w))
risk = cp.norm(cp.hstack([fac, spec, rob]), 2)

alpha_term = alpha_week @ w - rho @ cp.abs(w)
tcost = (k_spread @ cp.abs(z) + k_impact @ cp.power(cp.abs(z), 1.5)) / H_amort
hold = (k_short / 52) @ cp.pos(-w)
objective = cp.Maximize(alpha_term - g_trade * tcost - g_hold * hold)

cons = [
    risk <= sigma_tar_eff,
    cp.norm(fac, 2) <= 0.6 * sigma_tar_eff,
    cp.abs(cp.sum(w)) <= 0.01,
    cp.abs(beta @ w) <= 0.05,
    cp.abs(C_country.T @ w) <= 0.05,    # matriz indicadora emissor×país
    cp.abs(C_sector.T @ w) <= 0.05,
    cp.abs(C_ccy.T @ w) <= 0.05,        # moeda econômica
    cp.abs(X_style.T @ w) <= 0.15,
    cp.norm1(w) <= 2.5,
    cp.sum(cp.pos(w)) <= 1.25, cp.sum(cp.pos(-w)) <= 1.25,
    w <= long_cap, w >= -short_cap,     # short_cap = 0 se não shortável
    cp.abs(z) <= trade_cap,
    cp.norm1(z) <= turnover_cap,
]
prob = cp.Problem(objective, cons)
prob.solve(solver=cp.CLARABEL)
```

---

## 4. Vol-target, alavancagem e controle de *drawdown*

### 4.1 Como se chega a 5% de vol: *gross* implícito

**Referências de mercado [F]:**
- *Market neutral* clássico: *net* de −10% a +10%, *gross* de **200% a 400%**, vol "baixa" [21].
- Plataformas *multi-PM*: *gross* "tipicamente **400–600%**", *turnover* alto e vol realizada menor [21].
- *Pods* de ações *factor-neutral* operam com *dictated factor-neutral positioning or very tight constraints* (Mercer, mai/2023) [22]. A alavancagem varia de **< 1x a 6x** sob colateral regulatório [22].

**Aritmética do risco específico [C].** Com pesos iguais por emissor, N emissores, *gross* G e risco específico σ_ε, temos σ_p ≈ G·σ_ε/√N. Logo, o G necessário para σ_p = 5% (só risco específico) é:

| σ_ε \ N | 40 | 60 | 80 | 100 | 120 | 160 |
|---|---|---|---|---|---|---|
| 20% | 1,58 | 1,94 | 2,24 | 2,50 | 2,74 | 3,16 |
| 25% | 1,26 | 1,55 | 1,79 | 2,00 | 2,19 | 2,53 |
| 30% | 1,05 | 1,29 | 1,49 | 1,67 | 1,83 | 2,11 |
| 35% | 0,90 | 1,11 | 1,28 | 1,43 | 1,56 | 1,81 |

Com pesos **concentrados** pelo otimizador (N_efetivo ≈ 0,6N) e risco fatorial residual de 20% da variância:

| σ_ε \ N | 40 | 60 | 80 | 100 | 120 | 160 |
|---|---|---|---|---|---|---|
| 25% | 0,88 | 1,07 | 1,24 | 1,39 | 1,52 | 1,75 |
| 30% | 0,73 | 0,89 | 1,03 | 1,15 | 1,26 | 1,46 |

**Leitura [I].** Com 80 a 150 emissores e σ_ε de 25% a 35% (a medir no modelo), o *gross* para 5% fica em **≈ 1,1x–2,2x**. Os 400–600% das plataformas refletem livros em DM, com σ_ε menor e *hedges* setoriais apertados. Em LatAm, alavancar mais que isso concentraria risco em liquidez e aluguel. Mantém-se `gross_max: 2.5`, com o *gross* **resultando** da restrição de vol, não sendo meta.

### 4.2 *Ex-ante* × realizado: correção de viés [F]/[I]

- **Por que corrigir.** O otimizador explora erros de estimação e cai nos autofatores subestimados. No USE4, carteiras otimizadas sem *eigen adjustment* subprevêem o risco [1]. O Markowitz básico de Boyd et al. realizou vol "bem acima" da meta de 10% [14].
- **Política proposta [I]:**
  1. Meta *ex-ante* efetiva σ_tar,eff = 5%/B̂.
  2. **B̂ *a priori* = 1,10** (meta efetiva de 4,55%) até haver 26 semanas de retornos *live*.
  3. A partir daí, B̂ = *bias statistic* da carteira em 26–52 semanas (z_t = R_t/σ̂_{t−1}, semanal), limitada a [0,8; 1,25] e aplicada **só se** sair do IC de 95% (1 ± √(2/T): **[0,72; 1,28]** para T = 26 e **[0,80; 1,20]** para T = 52 [C]).
  4. Auditoria paralela da *bias statistic* das carteiras-teste (§1.5) e do ϱ robusto (0,02) [14].
- **Banda de não-rebalanceamento.** Se a vol *ex-ante* da carteira corrente ficar entre 4,25% e 5,75% (±15%) e não houver outro motivo para operar, **não reescalar**. Abaixo de 3% ou acima de 7% (limites do mandato) → **ação obrigatória**: alerta diário e proposta extraordinária ao PM.
- **Evidência de vol-targeting [F] [23].** Em 60 ativos (desde 1926 até 2017), o *vol targeting* elevou o Sharpe das ações de 0,40 para 0,48–0,51 e reduziu a probabilidade de retornos extremos, porque os eventos de cauda costumam vir com vol alta, quando a exposição já foi reduzida. Ver também Moreira e Muir (2017) **[R]** [24].

### 4.3 Monitoramento intra-semana [I]

A decisão é semanal, mas o risco é recalculado **todo dia** pelo código. Alertas ao PM:
- vol *ex-ante* > 6% ou < 3,5%;
- |beta| > 0,04 ou |net| > 1%;
- *squeeze score* alto em algum short;
- DTL acima do limite;
- perda diária > 2σ_diária (≈ 0,63% do NAV).

**Só os alertas *hard*** (vol > 7%, |net| > 2%, *squeeze* alto) geram proposta de ajuste fora de segunda-feira, e a proposta continua exigindo aprovação humana.

### 4.4 Controle de *drawdown*

**Prática observada:**
- **Millennium** (WSJ, via terceiros) **[S] [25]:** perda de **5%** do capital alocado → capital **cortado pela metade**; **7,5%** → PM em geral desligado. Rotatividade anual de PMs de 15–20% [S]. A Mercer cita rotatividade de **20–30%** em algumas plataformas [F] [22].
- **Aurum [F] [21]:** exemplo de política de reduzir o ***gross* em um terço após 5% de DD**. *Stop-losses* são **comuns em fundos de *net* baixo**, porque o *gross* alto exige gestão mais proativa.

**Simulação (σ = 5% a.a., passos semanais, 200 mil trajetórias, normal; semente 20261005) [C]:**

| Sharpe verdadeiro | P(DD ≤ −3% em 12m) | ≤ −4% | ≤ −5% | ≤ −7% | ≤ −10% | MDD mediano 12m |
|---|---|---|---|---|---|---|
| 0,0 | 84,7% | 65,9% | 48,1% | 22,4% | 5,1% | −4,9% |
| 0,5 | 74,1% | 50,8% | 32,4% | 11,6% | 1,7% | −4,0% |
| 1,0 | 61,5% | 36,3% | 20,0% | 5,4% | 0,6% | −3,4% |
| 1,5 | 48,2% | 24,0% | 11,2% | 2,2% | 0,1% | −2,9% |

Com caudas t(4) e Sharpe 1,0, as probabilidades ficam parecidas: 54,7% / 32,1% / 18,2% / 5,5% / 0,9% [C]. Em 36 meses e Sharpe 1,0: P(DD ≤ −5%) = 56,2% e P(DD ≤ −7%) = 23,2% [C].

**Leitura [I].** Um *hard stop* em −5% (`fund.yaml`) dispara em **1 de cada 5 anos** mesmo com Sharpe 1,0, e o *soft* em −3% dispara na **maioria** dos anos. O poder de discriminação entre gestor bom (SR 1) e sem habilidade (SR 0) é maior em −7% (5,4% contra 22,4%, razão ≈ 4,1x) que em −5% (20% contra 48%, ≈ 2,4x).

**Regras recomendadas [I]** (DD sobre o pico do NAV, diário; ações executadas na próxima rodada aprovada):

| Gatilho | Ação |
|---|---|
| Perda no mês-calendário ≤ −2,5% (≈ 1,7σ mensal) | Revisão obrigatória: atribuição fatorial × específica e checagem de *crowding*; sem corte automático |
| **DD ≤ −4% (≈ 0,8σ anual)** — *soft stop* | Vol-alvo → **3,5%** (×0,7); sem novas posições com *squeeze* ≥ médio |
| DD ≤ −5,5% | Vol-alvo → **3,0%** (piso da banda) |
| **DD ≤ −7% (≈ 1,4σ anual)** — *hard stop* | Vol-alvo → **2,0%** (*gross* ≤ ~0,6) e **re-aprovação formal do PM + comitê de risco** antes de qualquer re-risco. É exceção documentada à banda de 3%–7% |
| Re-risco | Em degraus de +25% do corte a cada 2 semanas, após recuperar ≥ 50% do DD **ou** 4 semanas sem novo mínimo, com *bias statistic* dentro do IC |

O `fund.yaml` atual (−3% / −5%, multiplicador de 0,5) é uma escolha **mais restritiva**, defensável se o patrocinador quiser perfil de *pod*. Deve ser escolhida conscientemente com a tabela acima.

**Por posição [I]:**
- perda específica acumulada de um papel ≥ **0,75% do NAV** → revisão obrigatória do caso;
- **short** com perda ≥ **1,0% do NAV**, ou alta ≥ **+30%** contra a entrada relativa ao mercado → **cortar 50%** salvo justificativa registrada;
- *long* com perda ≥ 1,25% do NAV → revisão e redução de 50%.

---

## 5. Monitoramento e atribuição

### 5.1 Painel *ex-ante* (todo dia, pelo código)

- **Vol total** e decomposição fatorial × específica (alvo ≥ 75% de específico).
- **Contribuições.**
  - Top-10 MCTR por emissor: contribuição % à variância = w_i(Σw)_i/σ².
  - Contribuição por fator e por bloco (país, setor, *style*, estatístico).
- **Exposições.** *Net*, beta, *gross* (long e short), país, setor, moeda econômica e *styles*, sempre contra os limites.
- **Liquidez.** Distribuição de DTL; % do *gross* liquidável em 1, 3 e 10 dias a 20% e a 10% do ADV.
- **Shorts.** *Squeeze score* de cada short, taxa de aluguel, DTC e SI % *float*; soma dos shorts ≥ médio.
- **VaR/ES** e estresses (§5.6).
- **Diagnóstico do modelo.** *Bias statistics* (carteira, fatores, carteiras-teste) e variância explicada pelo 1º PC dos resíduos.

### 5.2 Atribuição *ex-post* (diária, acumulada semanalmente)

```
R_p,t = Σ_k (Xᵀw)_k,t−1 · f_k,t        (P&L fatorial: mercado, país, setor, styles, FX, estatísticos)
      + Σ_i w_i,t−1 · u_i,t             (P&L específico = alfa de seleção)
      − custos de transação realizados  (spread + impacto + corretagem + câmbio)
      − aluguel pago + rebate/juros do caixa
```

**Regras [I]:**
- Usar as exposições de **início do dia** (t−1).
- O **resíduo de interação** (*intraday trading*) aparece numa linha própria, para nunca "sumir" no específico.
- O P&L específico se desdobra:
  - por **sinal**: regressão do retorno específico sobre os scores ortogonalizados de cada sinal (*Fama-MacBeth* semanal) ou carteiras-característica de cada sinal;
  - por **lado** (long × short);
  - por **país e setor**;
  - por **origem da ideia** (quant puro × *view* do PM × *view* LLM);
  - por **ajuste do PM** contra a proposta do otimizador.

### 5.3 KPIs de qualidade do alfa [I]

| KPI | Definição | Referência de gestão (inferência) |
|---|---|---|
| **Sharpe idiossincrático** | média/desvio anualizados do P&L específico (semanal) | Meta ≥ 0,75; alerta < 0 em 26 semanas |
| **Participação específica do P&L e do risco** | var. específica / var. total | Risco ≥ 75%; P&L específico explicando a maior parte do resultado |
| ***Hit rate*** | % de posições-semana com P&L específico > 0 (ponderado e não ponderado), separado long/short | Tipicamente perto de 50–55%; valor monitorado, não alvo |
| ***Slugging ratio*** | ganho médio das posições vencedoras / perda média das perdedoras (em US$) | > 1,0 compensa *hit rate* < 50% |
| **IC realizado** | correlação *rank* entre α⊥ (t) e retorno específico (t → t+H), por sinal e total | IC médio > 0 com t-stat > 2 em 52 semanas |
| **TC realizado** | §2.2 | ≥ 0,5 |
| ***Implementation shortfall*** | preço de decisão (fechamento de sexta ou abertura de segunda) × execução, em bps | Comparar ao modelo de custo; recalibrar κ por trimestre |
| ***Bias statistic*** | §1.5 / §4.2 | Dentro do IC de 95% |
| **Alfa long × short** | P&L específico por lado | Shorts com alfa ≤ 0 por 26 semanas → revisar o processo do lado vendido |

### 5.4 *Crowding*

**Modelo MSCI [F] [28].** O *Integrated Factor Crowding* combina **valuation spread**, **short interest spread**, **correlação par a par**, **volatilidade do fator** e **momentum do fator**. O modelo de *security crowding* tem duas camadas:
- **série temporal:** Value 40%, *Short Interest* 30%, Liquidity, Residual Volatility e Momentum com 10% cada;
- ***cross-sectional*:** estrutura análoga.

Os componentes avaliados são valuation, *short interest*, *turnover*, volatilidade e reversão. O doc 01 cita o desmonte de fatores *crowded* de jun–jul/2025 (quants −4,2%) como risco real.

**Implementação LatAm [I]:**
- ***Short interest*.** BTB/B3 para linhas locais e FINRA para ADRs.
- **Posicionamento estrangeiro.** Fluxo estrangeiro na B3 e 13F para ADRs: % de posse de *hedge funds*.
- ***Turnover* anormal** (volume de 20 dias / 252 dias).
- ***Valuation spread*** dos decis de cada sinal.
- **Correlação média par a par** dos nossos longs e dos nossos shorts, que sobe com *crowding*.

**Limite [I]:** emissores no decil mais *crowded* ≤ 20% do *gross* de cada lado. **Alerta** quando o *valuation spread* de um sinal está no percentil < 10 histórico, ou seja, o sinal está "caro".

### 5.5 *Squeeze score* (0–100, determinístico) [I]

```
score = 100 × [ 0,25·g(SI%float; 5%, 15%) + 0,25·g(DTC; 3, 7) + 0,20·g(aluguel; 3%, 8%)
              + 0,15·g(ret_1m; 15%, 30%) + 0,10·1{mcap_float < US$1 bi} + 0,05·flag_catalisador_LLM ]
```

- **Função g.** Rampa linear: 0 abaixo do limiar "médio", 1 acima do "alto".
- **Dado faltante.** Usa o valor **conservador** (o limiar médio), **nunca zero**, e o score recebe a marca "estimado".
- **Faixas.** Médio ≥ 40; alto ≥ 70 (`fund.yaml`).
- **Flag de catalisador.** Vem da pesquisa LLM e só pode **aumentar** o score.

### 5.6 Estresse, VaR e ES

**VaR/ES [I]/[R]:**
- **Métodos:**
  - **paramétrico pelo modelo de fatores**, com Cornish-Fisher para assimetria e curtose;
  - ***filtered historical simulation*** (FHS): 3 anos de retornos diários de fatores e resíduos, reescalados pela vol corrente (VRA).
- **Métricas.** **VaR 99% de 1 dia** e **ES 97,5% de 1 dia** (o ES 97,5% é o padrão do FRTB/Basileia **[R]** [32]).
- **Referência normal.** Com σ = 5% a.a., σ_diária ≈ 0,315% e VaR99 ≈ 2,33 × 0,315% ≈ **0,73% do NAV** [C].
- **Limites:** VaR99 (FHS) ≤ **1,0% do NAV**; ES97,5 ≤ **1,25% do NAV**. Acima disso, alerta e proposta de redução.

**Estresses históricos (replay com os retornos reais de fatores e resíduos, calculados pelo código; magnitudes não afirmadas aqui) [I]:**
- **2008:** crise financeira global (set–nov/2008).
- **Brasil, mai/2017:** dia seguinte à divulgação da gravação envolvendo o presidente Temer, com *circuit breaker* na B3.
- **Brasil, mai/2018:** greve dos caminhoneiros.
- **Argentina, 12/08/2019:** pós-PASO, colapso de ADRs e do peso.
- **Chile, out/2019:** *estallido social*.
- **Mar/2020:** COVID, com múltiplos *circuit breakers* na B3.
- **México, jun/2024:** pós-eleição, reforma judicial e choque do peso.
- **Brasil, dez/2024:** choque fiscal e de câmbio.
- **Fatoriais:** desmonte de momentum (*momentum crash*) e episódio de *crowding* quant (jun–jul/2025).

**Estresses hipotéticos [I]:**
- mercado LatAm −20% (testa o beta residual);
- BRL −15% e MXN −10% (testa o FX Sensitivity e a moeda econômica);
- petróleo −30% e minério −25%;
- fator momentum −3σ e value +3σ (rotação);
- ***squeeze*:** shorts com score ≥ médio +50% e demais shorts +20% em 5 dias;
- **liquidez:** ADV −50% e *spreads* ×3 (refaz o DTL e o custo de liquidação).

**Limites [I]:** perda em qualquer estresse histórico ≤ **3% do NAV**; estresse de *squeeze* ≤ **2,5% do NAV**; custo de liquidação total sob estresse de liquidez ≤ **1,5% do NAV**.

---

## 6. Tabela de parâmetros *default* (US$ 100 mi, vol 5%, semanal)

| # | Parâmetro | *Default* recomendado | `fund.yaml` atual | Justificativa | Tag |
|---|---|---|---|---|---|
| 1 | Vol-alvo *ex-ante* (nominal) | 5,0% a.a. | 0,05 | Mandato | — |
| 2 | Banda de vol (alerta / bloqueio) | < 3% alerta; > 7% bloqueio | 0,03 / 0,07 | Mandato | — |
| 3 | Viés *a priori* B̂ → meta efetiva | 1,10 → 4,55% (até 26 semanas *live*) | ausente | Otimizadores subprevêem o risco [1][14] | [I] |
| 4 | Banda de não-rebalanceamento | ±15% da meta (4,25%–5,75%) | ausente | Evitar *churn* | [I] |
| 5 | Robustez de risco ϱ / de retorno ρ | 0,02 / p20 de \|α\| | ausente | Boyd et al. [14] | [F] |
| 6 | \|Net\| | ≤ 1% do NAV | 0,01 | *Dollar neutral* | [I] |
| 7 | \|Beta\| (Σwβ) | ≤ 0,05 *hard*; meta 0,02 | 0,05 | 0,05 × 22% de vol de mercado ≈ 1,1% de vol | [I] |
| 8 | Net por país / setor / moeda econômica | ≤ 5% do NAV cada | 0,05 / 0,05 / — | País domina o risco em EM [2] | [I] |
| 9 | \|Exposição de *style*\| | ≤ 0,15 (*z*·NAV) | 0,15 | Alfa puro | [I] |
| 10 | Risco fatorial (absoluto) | ≤ 0,6·σ_tar (≤ 36% da var.); meta ≤ 25% | 0,35 (*share*) | Forma convexa equivalente | [I] |
| 11 | *Gross* | ≤ 2,5x; esperado 1,1–2,2x | 2,5 / mín. 0,5 | §4.1 | [C]/[I] |
| 12 | Lado long / lado short | ≤ 1,25x cada | ausente | Simetria | [I] |
| 13 | Peso máximo long / short | 4,0% / 2,5% | 0,04 / 0,025 | Assimetria: perda ilimitada no short; Aurum: 10%/5% já é "grande" [21] | [F]/[I] |
| 14 | Risco específico por papel | \|w\|·σ_ε ≤ √0,08·σ_tar (1,41%) | 0,08 (*share*) | Forma convexa | [I] |
| 15 | Posição mínima / trade mínimo | 0,2% / 0,05% do NAV | 0,002 / — | Heurística de Boyd [14] | [I] |
| 16 | ADV | Mín. das medianas de 21 e 63 dias | janela de 63 | Robustez | [I] |
| 17 | Participação | 20% (base); 10% (estresse) | 0,20 | Aurum: 20% de 60 dias; 10%/5% conservador [21] | [F] |
| 18 | Dias para liquidar long / short | ≤ 3 / ≤ 2 | 3 / 2 | *Squeeze* exige saída rápida | [I] |
| 19 | Dias de trade por rebalanceamento | 2 (semanal) / 5 (*inception*) | 2 / 5 | Capacidade | [I] |
| 20 | ADTV mínimo long / short | US$ 2 mi / US$ 5 mi | 2 mi / — | Short exige mais liquidez | [I] |
| 21 | Mcap mínimo short | US$ 500 mi | 500 mi | *Squeeze* | [I] |
| 22 | *Turnover* semanal (Σ\|z\|) | ≤ 30% do NAV (teto); típico 10–20% | **0,60** | Orçamento de custo ≤ 1–1,5% a.a. [C] | [C]/[I] |
| 23 | Meio *spread* por *tier* | 4 / 8 / 15 / 25 bps | igual | Calibrar com dados | [I] |
| 24 | Coeficiente de impacto Y | 0,6 (base); 1,0 (estresse) | 0,6 | Y "de ordem 1"; δ entre 0,4 e 0,7 [18] | [F]/[I] |
| 25 | Amortização de custo = horizonte do alfa | 8 semanas | 8 | Consistência | [I] |
| 26 | Taxa de aluguel máxima | 8% a.a. (teto); > 3% conta como "médio" | 0,08 | Aurum: *specials* > 10%, *squeeze* > 50% [21]; B3: até 9,38% [27] | [F]/[I] |
| 27 | *Squeeze* (SI%float, DTC, aluguel, ret_1m) | 5%/15%; 3/7; 3%/8%; 15%/30% | igual | DTC prevê retorno ruim [20]; heurística 3–7 dias [33] | [F]/[S] |
| 28 | Shorts com score ≥ médio (soma) | ≤ 5% do NAV | ausente | Estresse de *squeeze* ≤ 2,5% | [I] |
| 29 | IC *a priori* (8 semanas) / IC de *views* | 0,04 / 0,03 | 0,04 / 0,03 | "Bom" = 0,05 [7] | [F]/[I] |
| 30 | Pesos dos sinais | 50% *a priori* + 50% IC-IR (36 meses), ω ∈ [0; 0,4] | só *a priori* | *Shrinkage* contra *overfit* | [I] |
| 31 | *Winsor* | ±3σ robusto (MAD) | 3,0 | USE4 [1] | [F] |
| 32 | Ortogonalização aos fatores | Sim (todos os fatores) | true | Alfa puro / FAP [6] | [I] |
| 33 | Histórico do modelo / mín. por papel | 756 / 126 dias | 756 / 126 | — | [I] |
| 34 | Meia-vida da vol dos fatores / NW | 84 dias / 3 *lags* | 84 / 2 | USE4S: 84 / 5 [1] | [F]/[I] |
| 35 | Meia-vida da correlação / NW | 252 dias / 2 *lags* | 252 / 2 | USE4S: 504 / 2; histórico curto em LatAm | [F]/[I] |
| 36 | VRA (fatores e específico) | meia-vida de 42 dias | ausente | USE4S [1] | [F] |
| 37 | *Eigenfactor adjustment* | a = 1,4; M = 1.000 | ausente | USE4 [1] | [F]/[I] |
| 38 | Risco específico | meia-vida de 84; NW 5 *lags* (meia-vida de 252); *shrinkage q* = 0,1 por quintil de tamanho | 84 / *shrinkage* 0,3 | USE4S [1] | [F]/[I] |
| 39 | Fatores estatísticos (híbrido) | 3 PCs dos resíduos (252 dias, meia-vida de 126) | ausente | [4] | [I] |
| 40 | Mín. de emissores por fator de setor/país | 5 (fundir abaixo) | 3 | Estabilidade da regressão | [I] |
| 41 | *Drawdown*: mês / *soft* / intermediário / *hard* | −2,5% revisão / −4% (vol 3,5%) / −5,5% (vol 3%) / −7% (vol 2% + re-aprovação) | −3% / −5% (×0,5) | Simulação §4.4 [C]; Millennium −5%/−7,5% [25] | [C]/[S]/[I] |
| 42 | Stop por posição | Específico ≥ 0,75% do NAV → revisão; short ≥ 1,0% do NAV ou +30% → −50% | ausente | Assimetria do short | [I] |
| 43 | VaR99 / ES97,5 (1 dia, FHS) | ≤ 1,0% / ≤ 1,25% do NAV | 0,99 (conf.) | Normal: VaR99 ≈ 0,73% [C] | [C]/[I] |
| 44 | Estresse histórico / *squeeze* / liquidez | ≤ 3% / ≤ 2,5% / ≤ 1,5% do NAV | ausente | — | [I] |
| 45 | *Crowding* | Decil mais *crowded* ≤ 20% do *gross* de cada lado | ausente | MSCI [28] | [I] |
| 46 | Solver | CLARABEL (*fallback* ECOS/SCS) | — | Já é dependência | [I] |

---

## 7. Como isso se encaixa no ciclo semanal de segunda-feira [I]

1. **Sexta, após o fechamento (D−3).** *Snapshot* imutável de preços, volumes, câmbio, eventos corporativos e dados de aluguel e SI, com *hash* do dado bruto. Validação, sem preencher faltantes com zero.
2. **Sábado e domingo (*batch*).**
   - Reestimação do modelo de risco (§1.5) e validação (*bias statistics*).
   - Sinais e alfa (§2.1).
   - Pesquisa LLM: fichas, *views* e flags de catalisador, com citações.
   - **Proposta do otimizador** (§3) e estresses (§5.6).
   - FactBook determinístico.
3. **Segunda, antes da abertura (D0).**
   - O PM revisa a proposta, as diferenças contra a carteira atual e os riscos.
   - Ajusta *views* ou restrições; cada ajuste gera nova otimização e novo *hash*.
   - **Aprova** (sem autoaprovação). A exportação da ordem exige a aprovação vinculada aos *hashes*.
4. **Execução (D0–D1, *inception* até D4).** Fatiar a ≤ 20% do ADV por linha escolhida, com *implementation shortfall* registrado.
5. **Diário.** Risco, atribuição e alertas (§4.3, §5). Ação fora de segunda-feira só com alertas *hard* e nova aprovação.

**Primeira carteira (2026-10-05) [I].**
- Sem histórico *live*: B̂ = 1,10, meta efetiva de 4,55% e rampa de 5 dias.
- Só sinais de preço e volume com histórico validado. Sinais fundamentais e de revisão entram se a fonte for confiável, marcados como "não testados PIT".
- Shorts só em emissores com aluguel conhecido ou em ADRs de alta liquidez.
- *Squeeze score* conservador onde faltar dado.

---

## 8. Limitações e lacunas

- **Fontes primárias pagas não lidas:** documentação completa do Axioma AXEM4, *Empirical Notes* do USE4 (com as janelas dos descritores) e EMM1 Methodology. As janelas de descritores marcadas **[R]** seguem a convenção Barra de memória e devem ser validadas empiricamente no nosso universo.
- **Evidência de fatores específica de LatAm é escassa** e em parte vem de teses e blogs **[S]**. A evidência forte é de **EM agregado** [8][9][11][12][13]. O IC de cada sinal **no nosso universo** precisa ser medido em *backtest* *walk-forward*, com custos e *point-in-time*.
- **Regras de *pods*** (Millennium −5%/−7,5%) vêm da imprensa via terceiros **[S]**.
- **Custos de transação LatAm.** Não encontramos estudo público com *implementation shortfall* institucional por país. Os *defaults* são conservadores e **devem ser recalibrados** com execuções reais.
- **Simulações [C].** Supõem retornos i.i.d. (normal e t(4)), sem autocorrelação, regimes de vol ou mudança de alfa. Servem para **ordem de grandeza** e calibração de política, não para previsão.

---

## 9. Fontes (numeradas)

1. Menchero, J., Orr, D. J. e Wang, J. — *The Barra US Equity Model (USE4) Methodology Notes*, MSCI Research, ago/2011. Tabelas 4.1 e 5.1, Seção 4.2/App. B (a = 1,4), Seção 5.2 (q), App. A (IC da *bias statistic*, MRAD = 0,17). https://www.top1000funds.com/wp-content/uploads/2011/09/USE4_Methodology_Notes_August_2011.pdf **[F]**
2. Menchero, J. e Nagy, Z. — *The Relative Strength of Industries and Countries in Emerging Markets: A Case Study Using the Barra Emerging Markets Equity Model (EMM1)*, MSCI Global Market Report, set/2014. https://www.msci.com/documents/10199/6669d7e7-7768-4948-82b8-237bec0613e7 **[F]**
3. Hedgeweek — "Axioma launches emerging markets equity risk model" (AXEM4: 7 *styles* de mercado + 6 fundamentais; histórico desde 1997), s.d. (acesso em 05/10/2026). https://www.hedgeweek.com/axioma-launches-emerging-markets-equity-risk-model/ **[F]**
4. Tzikas, A. E., Candès, E. J., Hastie, T., Boyd, S. P., Kochenderfer, M. J. e Kahn, R. N. — "Enhancing a Risk Model by Adding Transient Statistical Factors", arXiv 2605.12977, 13/05/2026. https://arxiv.org/abs/2605.12977 **[F]**
5. Clarke, R., de Silva, H. e Thorley, S. — "Portfolio Constraints and the Fundamental Law of Active Management", *Financial Analysts Journal* 58(5):48–66, 2002. https://ideas.repec.org/a/taf/ufajxx/v58y2002i5p48-66.html **[F]**
6. Saxena, A. e Stubbs, R. A. — "The alpha alignment factor: a solution to the underestimation of risk for optimized active portfolios", *Journal of Risk*; e Ceria, Saxena e Stubbs — "Factor Alignment Problems and Quantitative Portfolio Management", *JPM*, 2012. https://www.risk.net/journal-of-risk/2253141/the-alpha-alignment-factor-a-solution-to-the-underestimation-of-risk-for-optimized-active-portfolios **[F]** (resumo)
7. Gleiser, I. e McKenna, D. — *Converting Scores into Alphas: A Barra Aegis Case Study*, MSCI Barra, mai/2010 (regra de Grinold, 1994, "Alpha is Volatility Times IC Times Score", *JPM*; IC 0,05 = "bom", 0,10 = "muito bom"). https://www.msci.com/documents/10199/1645561/PI_Converting_Scores_Into_Alphas.pdf/7adf1f42-10aa-40eb-9e8c-ecc11eeba2d4 **[F]**
8. Hanauer, M. X. e Lauterbach, J. G. — "The cross-section of emerging market stock returns", *Emerging Markets Review*, 2019 (28 países, jul/1995–jun/2016); resumo da Alpha Architect. https://alphaarchitect.com/the-cross-section-of-emerging-market-stock-returns/ **[F]** (via resumo)
9. Blitz, D., Hanauer, M. X. e Vidojevic, M. — "The Idiosyncratic Momentum Anomaly", SSRN, abr/2017 (publicado na *International Review of Economics & Finance*, 2020); resumo da CXO Advisory. https://www.cxoadvisory.com/momentum-investing/idiosyncratic-pure-or-residual-momentum-as-a-stock-return-predictor **[F]** (via resumo)
10. Blitz, D., Huij, J. e Martens, M. — "Residual Momentum", *Journal of Empirical Finance* 18(3), 2011. **[R]**
11. van der Hart, J., de Zwart, G. e van Dijk, D. — "The Success of Stock Selection Strategies in Emerging Markets: Is It Risk or Behavioral Bias?", ERIM Report Series, 2005. https://repub.eur.nl/pub/1922 **[F]**
12. Blitz, D., Pang, J. e van Vliet, P. — "The Volatility Effect in Emerging Markets", Robeco/SSRN, abr/2012 (*Emerging Markets Review*, 2013); resumos da CXO Advisory e da Robeco. https://www.cxoadvisory.com/volatility-effects/reward-for-risk-in-emerging-equity-markets/ **[F]** (via resumo)
13. Butt, H. A., Högholm, K. e Sadaqat, M. — "Reversal returns and expected returns from liquidity provision: Evidence from emerging markets", *Journal of Multinational Financial Management* 59, 100664, 2021. https://research.hanken.fi/en/publications/reversal-returns-and-expected-returns-from-liquidity-provision-ev/ **[F]**
14. Boyd, S., Johansson, K., Kahn, R., Schiele, P. e Schmelzer, T. — "Markowitz Portfolio Construction at Seventy", *Journal of Portfolio Management* 50(8):117–160, 2024; arXiv 2401.05080 (10/01/2024); código de referência em github.com/cvxgrp/markowitz-reference. https://arxiv.org/abs/2401.05080 **[F]**
15. Larisch, L. — dissertação de mestrado sobre *short-term reversal* no Brasil, PUC-Rio, s.d. https://www.econ.puc-rio.br/uploads/adm/trabalhos/files/Dissertacao_Luis_Larisch.pdf **[S]**
16. Garavito — tese de mestrado sobre anomalias (Value, Momentum, Low Vol, Quality) em Brasil, México, Chile, Peru e Colômbia, Erasmus University Rotterdam, s.d. https://thesis.eur.nl/pub/50422/ **[S]**
17. Evalueserve — "Is Low-Volatility Anomaly True for LatAm Markets Too?" (2003–2023), s.d. https://www.evalueserve.com/is-low-volatility-anomaly-true-for-latam-markets-too **[S]**
18. Tóth, B., Lempérière, Y., Deremble, C., de Lataillade, J., Kockelkoren, J. e Bouchaud, J.-P. — "Anomalous price impact and the critical nature of liquidity in financial markets", *Physical Review X* 1, 021006, 2011; arXiv 1105.1694. https://arxiv.org/abs/1105.1694 **[F]**
19. Frazzini, A., Israel, R. e Moskowitz, T. J. — "Trading Costs", AQR Working Paper, 23/08/2018. https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs **[F]**
20. Hong, H., Li, W., Ni, S. X., Scheinkman, J. A. e Yan, P. — "Days to Cover and Stock Returns", NBER WP 21166, mai/2015. https://www.nber.org/papers/w21166 **[F]**
21. Aurum — "Edge with hedge: primer for equity long/short funds", *Aurum Insight*, 30/09/2025. https://www.aurum.com/wp-content/uploads/250930-Equity-long-short-funds-primer.pdf **[F]**
22. Mercer — "Multi-Manager Platforms: A due diligence perspective", mai/2023. https://insightcommunity.mercer.com/api/v1/uploads/Multi_Manager_Hedge_Funds_614b3c4909.pdf?public=true **[F]**
23. Harvey, C. R., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M. e Van Hemert, O. — "The Impact of Volatility Targeting", *Journal of Portfolio Management* 45(1), 2018. https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf **[F]** (via resumo)
24. Moreira, A. e Muir, T. — "Volatility-Managed Portfolios", *Journal of Finance* 72(4), 2017. **[R]**
25. Reprodução de reportagem do *Wall Street Journal* sobre as regras de *stop* da Millennium (5% → capital pela metade; 7,5% → desligamento). The Motley Fool / AOL, s.d. https://www.fool.com/investing/how-to-invest/famous-investors/millennium-management ; https://www.aol.com/strategy-69-billion-hedge-fund-193733084.html **[S]**
26. EquiLend — *Latin America Securities Finance User Guide 2025*, out/2025. https://equilend.com/wp-content/uploads/2025/10/Latin-America-Securities-Finance-User-Guide-2025.pdf **[F]**
27. Rivero, E. — "Por que o empréstimo de ações renovou recordes", Bora Investir (B3), 16/12/2025. https://borainvestir.b3.com.br/colunistas/einar-rivero/einar-rivero-por-que-o-emprestimo-de-acoes-renovou-recordes/ **[F]**
28. MSCI — "MSCI Integrated Factor Crowding Model" (página de pesquisa) e *MSCI Security Crowding Factsheet* (pesos dos componentes; exemplos de maio/2021). https://www.msci.com/research-and-insights/paper/msci-integrated-factor-crowding-model ; https://www.msci.com/documents/1296102/25918384/MSCI-Security-Crowding-Model-Factsheet.pdf **[F]**
29. Newey, W. K. e West, K. D. — "A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix", *Econometrica* 55(3), 1987. **[R]**
30. MSCI — *MSCI EM Latin America with Latin America Exposure Index (USD) — Index Factsheet*, 30/09/2026 (vol de 3, 5 e 10 anos do MSCI EM Latin America; pesos por país e setor). https://www.msci.com/documents/10199/f4ae9c26-89d5-4a6f-afa0-f72bb04ee212 **[F]**
31. Grinold, R. C. e Kahn, R. N. — *Active Portfolio Management*, 2ª ed., McGraw-Hill, 2000 (portfólios característicos, lei fundamental). **[R]**
32. BIS / Comitê de Basileia — *Minimum capital requirements for market risk* (FRTB; ES a 97,5%), jan/2019. https://www.bis.org/bcbs/publ/d457.htm **[R]**
33. LuxAlgo — "Days to Cover Explained: A Crucial Metric for Short Squeeze Analysis" (faixas 0–2 / 3–7 / 8+ dias), s.d. https://www.luxalgo.com/blog/days-to-cover-explained-a-crucial-metric-for-short-squeeze-analysis/ **[S]**
34. Ledoit, O. e Wolf, M. — "Honey, I Shrunk the Sample Covariance Matrix", *Journal of Portfolio Management* 30(4), 2004 (alternativa de *shrinkage* para a matriz de fatores ou a camada estatística). http://www.ledoit.net/honey.pdf **[R]**

---

*Documento de pesquisa. Não constitui recomendação de investimento. Os números [C] vêm de simulação ilustrativa (semente 20261005) e não são previsões de desempenho. Itens [S] e [R] devem ser revalidados antes de virar parâmetro de produção. Qualquer alteração de parâmetros no `fund.yaml` muda o `config_hash` e invalida aprovações (AGENTS.md, invariante 3).*
