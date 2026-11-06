# CDP — Cabra da Peste — Proposta da semana de 06/11/2026 (v1)

> Dados de mercado: retrato `store-2026-10-02+24-2026-11-05`. Dados reais (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética.

| Campo | Valor |
|---|---|
| Estado | **EM REVISÃO** |
| Proposta | CDP-2026-11-06-cdp-restricoes (versão 1) |
| Criada em / por | 06/11/2026 11:34 (Brasília) — CDP — motor quantitativo |
| PL de referência | USD 1,00 mm |
| Retrato dos dados de mercado | store-2026-10-02+24-2026-11-05 — `902f5156fcde` |
| Hash do mandato | `2ddf7d89ac76` |
| Hash da pesquisa | `c877e7df5838` |

## Resumo de risco

| Métrica | Valor | Referência |
|---|---|---|
| Vol ex-ante (a.a.) | 3,61% | meta aplicada 3,64% (mandato 5,00%); banda 3,00%–7,00% — dentro da banda |
| Vol fatorial (a.a.) | 0,80% | 6,92% da variância com κ_F no modelo de decisão (limite 10,00%) |
| Vol específica (a.a.) | 3,53% | fonte pretendida do retorno (alpha puro) |
| Beta previsto | 0,003 | limite ±0,050 |
| Exposição bruta (% do PL) | 80,10% | faixa 50%–250% |
| Exposição líquida (% do PL) | +0,23% | limite ±1,00% |
| Comprado / vendido (% do PL) | 40,16% / -39,93% |  |
| Nº de posições compradas / vendidas | 43 / 40 |  |
| VaR 1d 99% | 0,53% (USD 5,3 mil) | paramétrico/histórico (modelo de risco) |
| ES 1d 99% | 0,65% (USD 6,5 mil) |  |
| VaR 1 semana 99% | 1,18% (USD 11,9 mil) |  |
| N efetivo | 57,5 | diversificação (1/Σw² normalizado) |
| Máx. fechamentos para liquidar | 0,2 fech. | long ≤ 3,0 fech.; short ≤ 2,0 fech. |
| % do gross liquidável em 1 fechamento | 100,00% | capacidade estrutural do leilão e da janela pré-fechamento |
| Fatia idiossincrática — modelo de decisão | 93,08% | meta 90%; piso 85% (com janelas de evento) |
| Fatia idiossincrática — modelo base | 93,08% | meta 90%; piso 85% (sem janelas de evento) |
| Inflação de 2ª ordem do risco fatorial (κ_F) | 1,45 | aplicada à variância fatorial na medida idiossincrática |

### Decomposição da variância ex-ante por grupo (modelo de decisão, κ_F no bloco fatorial)

| Grupo | Fração da variância |
|---|---|
| Mercado | 0,05% |
| País | 0,05% |
| Setor | 1,63% |
| Estilo | 2,66% |
| Macro (commodities e dólar) | 2,53% |
| Específico (idiossincrático) | 93,08% |

### Testes de estresse (resultado estimado)

| Cenário | % do PL | US$ |
|---|---|---|
| Squeeze: 5 maiores posições vendidas +30% | -3,63% | USD -36,5 mil |
| Quebra: 5 maiores posições compradas −30% | -3,47% | USD -34,9 mil |
| Eleição México jun/2024 | -0,78% | USD -7,8 mil |
| Estresse de juros nos EUA jun/2022 | -0,49% | USD -5,0 mil |
| Choque fiscal BRL dez/2024 | -0,44% | USD -4,4 mil |
| Commodities −15% | -0,18% | USD -1,9 mil |
| Brasil −15% | -0,10% | USD -1,0 mil |
| Gap Chile −15% | -0,07% | USD -0,8 mil |
| Mercado da América Latina −20% | -0,06% | USD -0,6 mil |
| Gap Argentina +41% | -0,05% | USD -0,5 mil |
| Gap Brasil +10% | -0,03% | USD -0,3 mil |
| Gap Peru −10% | -0,01% | USD -0,1 mil |
| Gap Brasil −10% | +0,03% | USD +0,3 mil |
| Gap Colômbia −11% | +0,05% | USD +0,6 mil |
| Gap México −13% | +0,06% | USD +0,6 mil |
| Gap Argentina −56% | +0,07% | USD +0,8 mil |
| Tarifas dos EUA (abr/2025) | +0,11% | USD +1,1 mil |
| Colapso do fator momentum −3σ | +0,26% | USD +2,6 mil |
| México −15% | +0,31% | USD +3,1 mil |
| Eleição Brasil out/2022 (2º turno) | +0,68% | USD +6,8 mil |
| Crise da covid (fev-mar/2020) | n/d | n/d |
| Estallido social Chile (out-nov/2019) | n/d | n/d |
| Joesley Day (mai/2017) | n/d | n/d |
| PASO Argentina 2019 | n/d | n/d |
| Taper tantrum (mai-jun/2013) | n/d | n/d |

### Maiores contribuições fatoriais (fração da variância)

| Fator | Contribuição |
|---|---|
| Macro — ouro | 1,22% |
| Estilo — Momentum | 0,63% |
| Estilo — Liquidez | 0,47% |
| Estilo — Vol residual | 0,47% |
| Setor — Saúde | 0,31% |
| Macro — cobre | 0,30% |
| Macro — petróleo Brent | 0,28% |
| Setor — Energia | 0,27% |
| Estilo — Tamanho (size) | 0,26% |
| Setor — Tecnologia | 0,25% |

### Maiores contribuições de risco por empresa (fração da variância)

| Empresa | Contribuição |
|---|---|
| PagSeguro Digital | 7,98% |
| Aura Minerals | 7,86% |
| PicPay (PicS N.V.) | 7,78% |
| Tenda | 7,70% |
| Liberty Latin America | 7,60% |
| Grupo Aeroméxico | 5,38% |
| Fortuna Mining | 4,53% |
| Fleury | 3,17% |
| Cemex | 3,16% |
| Banco Pine | 3,04% |

## Controles do mandato

100 controles; 0 fora do limite (0 obrigatórios, 0 de alerta).

| Resultado | Tipo | Controle | Valor | Limite | Detalhe |
|---|---|---|---|---|---|
| dentro | obrigatório | Beta previsto | 0,0031 | 0,0500 | Beta previsto +0,003 (limite ±0,050). |
| dentro | obrigatório | Taxa de aluguel das posições vendidas | 0,0103 | 0,0500 | Taxas de aluguel dentro do limite de 5,00% a.a. |
| dentro | obrigatório | Exposição líquida por país (Argentina) | -0,0013 | 0,0200 | Líquido no país Argentina: −0,13% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Brasil) | -0,0030 | 0,0200 | Líquido no país Brasil: −0,30% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Chile) | 0,0050 | 0,0200 | Líquido no país Chile: 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Colômbia) | -0,0050 | 0,0200 | Líquido no país Colômbia: −0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Regional (América Latina)) | 0,0050 | 0,0200 | Líquido no país Regional (América Latina): 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (México) | -0,0046 | 0,0200 | Líquido no país México: −0,46% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Panamá) | 0,0050 | 0,0200 | Líquido no país Panamá: 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Peru) | 0,0012 | 0,0200 | Líquido no país Peru: 0,12% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Uruguai) | 0,0000 | 0,0200 | Líquido no país Uruguai: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Defasagem dos dados de mercado | 0,0000 | 4,0000 | Dados de mercado de 06/11/2026 para a semana de 06/11/2026: 0 dias corridos (máximo 4). |
| dentro | obrigatório | Stop de drawdown (corte da exposição bruta) | -0,0048 | -0,0500 | Drawdown −0,48% (stop −5,00%, zeragem −7,50%). |
| dentro | obrigatório | Exposição bruta máxima | 0,8010 | 2,5000 | Exposição bruta 0,80x do PL (máximo 2,50x). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo de decisão) | 0,9308 | 0,8500 | Fatia idiossincrática 93,08% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo base) | 0,9308 | 0,8500 | Fatia idiossincrática 93,08% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Prazo de liquidação das posições compradas | 0,1596 | 3,0000 | Máximo de 0,16 fechamentos à capacidade estrutural do leilão (limite 3,0). |
| dentro | obrigatório | Prazo de liquidação das posições vendidas | 0,0761 | 2,0000 | Máximo de 0,08 fechamentos à capacidade estrutural do leilão (limite 2,0). |
| dentro | obrigatório | Compra só em nomes elegíveis e sem veto | 0,0000 | 0,0000 | Todas as compras são permitidas. |
| dentro | obrigatório | Peso máximo por nome (posição comprada) | 0,0318 | 0,0400 | Nenhuma posição comprada acima do teto por nome. |
| dentro | obrigatório | Peso máximo por nome (posição vendida) | 0,0250 | 0,0250 | Nenhuma posição vendida acima do teto por nome. |
| dentro | obrigatório | Exposição líquida | 0,0023 | 0,0100 | Líquido 0,23% do PL (limite ±1,00%); comprado 40,16%, vendido −39,93%. |
| dentro | obrigatório | Cobertura do modelo de risco | 0,0000 | 0,0000 | Todos os nomes com peso têm risco modelado. |
| dentro | obrigatório | Exposição líquida por setor (comunicações) | -0,0080 | 0,0250 | Líquido no setor Comunicações: −0,80% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo discricionário) | -0,0150 | 0,0250 | Líquido no setor Consumo discricionário: −1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo básico) | 0,0077 | 0,0250 | Líquido no setor Consumo básico: 0,77% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (energia) | 0,0051 | 0,0250 | Líquido no setor Energia: 0,51% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (financeiro) | 0,0150 | 0,0250 | Líquido no setor Financeiro: 1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (saúde) | -0,0122 | 0,0250 | Líquido no setor Saúde: −1,22% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (industriais) | 0,0043 | 0,0250 | Líquido no setor Industriais: 0,43% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (tecnologia) | 0,0064 | 0,0250 | Líquido no setor Tecnologia: 0,64% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (materiais) | 0,0021 | 0,0250 | Líquido no setor Materiais: 0,21% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (imobiliário) | 0,0033 | 0,0250 | Líquido no setor Imobiliário: 0,33% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (utilidades públicas) | -0,0064 | 0,0250 | Líquido no setor Utilidades públicas: −0,64% do PL (limite ±2,50%). |
| dentro | obrigatório | Sem nova venda a descoberto em nome vetado | 0,0000 | 0,0000 | Nenhuma venda a descoberto nova ou aumentada em nome com resultado próximo ou free float baixo. |
| dentro | obrigatório | Venda a descoberto só em linhas alugáveis e sem veto | 0,0000 | 0,0000 | Todas as posições vendidas são alugáveis e sem veto. |
| dentro | obrigatório | Sem posição vendida com risco alto de squeeze | 0,0000 | 0,0000 | Nenhuma posição vendida em nome com risco de squeeze alto. |
| dentro | obrigatório | Teto da posição vendida com risco médio de squeeze | 0,0000 | 0,0125 | Posições vendidas com risco de squeeze médio ou sem dado dentro do teto de 1,25%. |
| dentro | obrigatório | Exposição ao estilo (beta de mercado) | 0,0072 | 0,1000 | Exposição líquida +0,007 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (sensibilidade cambial) | 0,0277 | 0,1000 | Exposição líquida +0,028 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (liquidez) | -0,0442 | 0,1000 | Exposição líquida −0,044 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (momentum) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (vol residual) | 0,0500 | 0,1000 | Exposição líquida +0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (tamanho (size)) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (valor (value)) | 0,0034 | 0,1000 | Exposição líquida +0,003 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição líquida ao tema (estatais) | 0,0100 | 0,0100 | Líquido 1,00% no tema estatais (limite ±1,00%). |
| dentro | obrigatório | Volatilidade ex-ante máxima | 0,0361 | 0,0700 | Volatilidade ex-ante 3,61% a.a. (teto da banda 7,00%). |
| dentro | obrigatório | Pesos numéricos válidos | 0,0000 | 0,0000 | Todos os pesos são finitos. |
| dentro | alerta | Beta previsto (limite operacional) | 0,0031 | 0,0200 | Beta previsto +0,003 (limite operacional ±0,020). |
| dentro | alerta | Sensibilidade a commodity (cobre) | 0,0100 | 0,0300 | Σ w·β = +0,0100 (limite ±0,03); 10% na commodity ⇒ +0,10% do PL. |
| dentro | alerta | Sensibilidade a commodity (ouro) | -0,0100 | 0,0300 | Σ w·β = −0,0100 (limite ±0,03); 10% na commodity ⇒ −0,10% do PL. |
| dentro | alerta | Sensibilidade a commodity (petróleo) | 0,0014 | 0,0300 | Σ w·β = +0,0014 (limite ±0,03); 10% na commodity ⇒ +0,01% do PL. |
| dentro | alerta | Sensibilidade a commodity, limite operacional (cobre) | 0,0100 | 0,0100 | Σ w·β = +0,0100 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (ouro) | -0,0100 | 0,0100 | Σ w·β = −0,0100 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (petróleo) | 0,0014 | 0,0100 | Σ w·β = +0,0014 (limite operacional ±0,010). |
| dentro | alerta | Perda em gap de país | -0,0007 | -0,0150 | Pior cenário: Gap CL −15% com −0,07% do PL (limite −1,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Argentina) | -0,0013 | 0,0050 | Líquido no país Argentina: −0,13% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Brasil) | -0,0030 | 0,0100 | Líquido no país Brasil: −0,30% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Chile) | 0,0050 | 0,0050 | Líquido no país Chile: 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Colômbia) | -0,0050 | 0,0050 | Líquido no país Colômbia: −0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Regional (América Latina)) | 0,0050 | 0,0050 | Líquido no país Regional (América Latina): 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (México) | -0,0046 | 0,0100 | Líquido no país México: −0,46% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Panamá) | 0,0050 | 0,0050 | Líquido no país Panamá: 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Peru) | 0,0012 | 0,0050 | Líquido no país Peru: 0,12% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Uruguai) | 0,0000 | 0,0050 | Líquido no país Uruguai: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Nível de revisão do drawdown | -0,0048 | -0,0250 | Drawdown −0,48% (gatilho de revisão −2,50%). |
| dentro | alerta | Parcela fatorial do risco | 0,0692 | 0,1000 | Risco fatorial = 6,92% da variância com inflação de 2ª ordem κ_F = 1,45 no bloco fatorial (limite 10,00%); o restante é específico (alpha puro). |
| dentro | alerta | Exposição bruta mínima | 0,8010 | 0,5000 | Exposição bruta 0,80x do PL (mínimo recomendado 0,50x). |
| dentro | alerta | Meta da fatia idiossincrática (modelo de decisão) | 0,9308 | 0,9000 | Fatia idiossincrática 93,08% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Meta da fatia idiossincrática (modelo base) | 0,9308 | 0,9000 | Fatia idiossincrática 93,08% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0000 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 0,00% (teto 2,50%) somando CSN Siderúrgica Nacional, CSN Mineração: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0079 | 0,0400 | Comprado 0,79% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Metalúrgica Gerdau, Gerdau: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0000 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Itaúsa, Itaú Unibanco: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0114 | 0,0400 | Comprado 0,49% (teto 4,00%), vendido 1,14% (teto 2,50%) somando Bradespar, Vale: holding e controlada contam como um só nome. |
| dentro | alerta | Exposição líquida por setor, limite operacional (comunicações) | -0,0080 | 0,0150 | Líquido no setor Comunicações: −0,80% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo discricionário) | -0,0150 | 0,0150 | Líquido no setor Consumo discricionário: −1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo básico) | 0,0077 | 0,0150 | Líquido no setor Consumo básico: 0,77% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (energia) | 0,0051 | 0,0150 | Líquido no setor Energia: 0,51% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (financeiro) | 0,0150 | 0,0150 | Líquido no setor Financeiro: 1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (saúde) | -0,0122 | 0,0150 | Líquido no setor Saúde: −1,22% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (industriais) | 0,0043 | 0,0150 | Líquido no setor Industriais: 0,43% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (tecnologia) | 0,0064 | 0,0150 | Líquido no setor Tecnologia: 0,64% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (materiais) | 0,0021 | 0,0150 | Líquido no setor Materiais: 0,21% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (imobiliário) | 0,0033 | 0,0150 | Líquido no setor Imobiliário: 0,33% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (utilidades públicas) | -0,0064 | 0,0150 | Líquido no setor Utilidades públicas: −0,64% do PL (limite operacional ±1,50%). |
| dentro | alerta | Contribuição máxima de um nome ao risco | 0,0798 | 0,0800 | Maior contribuição: PagSeguro Digital com 7,98% da variância (limite 8,00%). |
| dentro | alerta | Exposição ao estilo, limite operacional (beta de mercado) | 0,0072 | 0,0500 | Exposição líquida +0,007 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (sensibilidade cambial) | 0,0277 | 0,0500 | Exposição líquida +0,028 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (liquidez) | -0,0442 | 0,0500 | Exposição líquida −0,044 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (momentum) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (vol residual) | 0,0500 | 0,0500 | Exposição líquida +0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (tamanho (size)) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (valor (value)) | 0,0034 | 0,0500 | Exposição líquida +0,003 (limite operacional ±0,05). |
| dentro | alerta | Ordens dentro da capacidade do fechamento | 0,0000 | 0,0000 | Toda abertura ou aumento cabe na capacidade do leilão e da janela pré-fechamento. |
| dentro | alerta | Giro semanal | 0,3000 | 0,3000 | Giro Σ\|Δw\| = 30,00% do PL (limite 30,00%). |
| dentro | alerta | Volatilidade ex-ante mínima | 0,0361 | 0,0300 | Volatilidade ex-ante 3,61% a.a. (piso da banda 3,00%). |
| na meta | indicador | Emissores sem fechamento negociável | 0,0000 | n/d | Nenhum emissor congelado. |
| na meta | indicador | Dados dos vetos de venda a descoberto | 26,0000 | n/d | 26 emissores sem data de resultado ou free float conhecidos (sem data: sinalizado, sem veto; sem free float em nome pequeno: vetado). Participação máxima do controlador sem fonte pública estruturada: não avaliada. |
| na meta | indicador | Origem dos dados | 0,0000 | n/d | Dados reais de snapshot imutável (hash verificado). |
| na meta | indicador | Distância à meta de volatilidade | 0,0361 | 0,0364 | Volatilidade ex-ante 3,61% contra a meta 3,64% (diferença −0,02 p.p.). |

## Principais posições

### 10 maiores posições compradas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | PagSeguro Digital | Brasil | Financeiro | +3,18% | USD 31,9 mil | PAGS (listada nos EUA) | 0,1% | baixo (31) | +1,02 |
| 2 | Fortuna Mining | Regional (América Latina) | Materiais | +2,69% | USD 27,1 mil | FSM (listada nos EUA) | 0,0% | baixo (20) | +0,47 |
| 3 | Tenda | Brasil | Consumo discricionário | +2,12% | USD 21,3 mil | TEND3.SA (local) | 0,1% | baixo (29) | +1,73 |
| 4 | Grupo Aeroméxico | México | Industriais | +2,02% | USD 20,3 mil | AERO (ADR) | 0,3% | baixo (20) | +0,16 |
| 5 | Petrobras | Brasil | Energia | +1,58% | USD 15,8 mil | PBR (ADR) | 0,0% | baixo (25) | +2,56 |
| 6 | PicPay (PicS N.V.) | Brasil | Financeiro | +1,56% | USD 15,7 mil | PICS (listada nos EUA) | 0,2% | baixo (19) | +0,71 |
| 7 | Telecom Argentina | Argentina | Comunicações | +1,47% | USD 14,8 mil | TEO (ADR) | 0,4% | baixo (10) | +1,92 |
| 8 | Suzano | Brasil | Materiais | +1,40% | USD 14,1 mil | SUZB3.SA (local) | 0,0% | baixo (28) | -0,79 |
| 9 | Genomma Lab | México | Consumo básico | +1,32% | USD 13,3 mil | LABB.MX (local) | 0,5% | n/d (48) | +0,83 |
| 10 | Banco Pine | Brasil | Financeiro | +1,28% | USD 12,9 mil | PINE4.SA (local) | 0,4% | baixo (22) | +1,50 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- _Sem nota de pesquisa:_ PagSeguro Digital, Fortuna Mining, Tenda, Grupo Aeroméxico, Petrobras, PicPay (PicS N.V.), Telecom Argentina, Suzano, Genomma Lab, Banco Pine

### 10 maiores posições vendidas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Smart Fit | Brasil | Consumo discricionário | -2,50% | USD -25,1 mil | SMFT3.SA (local) | 0,1% | baixo (28) | -0,74 |
| 2 | Patria Investments | Brasil | Financeiro | -2,50% | USD -25,1 mil | PAX (listada nos EUA) | 0,2% | baixo (28) | -2,12 |
| 3 | Cemex | México | Materiais | -2,50% | USD -25,1 mil | CX (ADR) | 0,0% | baixo (14) | -1,20 |
| 4 | Liberty Latin America | Regional (América Latina) | Comunicações | -2,36% | USD -23,8 mil | LILAK (listada nos EUA) | 0,2% | baixo (25) | -1,84 |
| 5 | Aura Minerals | Brasil | Materiais | -2,25% | USD -22,6 mil | AUGO (listada nos EUA) | 0,0% | baixo (33) | +0,79 |
| 6 | Fleury | Brasil | Saúde | -2,10% | USD -21,1 mil | FLRY3.SA (local) | 0,1% | baixo (28) | +0,55 |
| 7 | Grupo Aeroportuario del Sureste | México | Industriais | -1,34% | USD -13,5 mil | ASR (ADR) | 0,1% | baixo (23) | -1,23 |
| 8 | Embraer | Brasil | Industriais | -1,27% | USD -12,8 mil | EMBJ3.SA (local) | 0,0% | baixo (12) | -1,21 |
| 9 | Lithium Argentina | Argentina | Materiais | -1,20% | USD -12,1 mil | LAR (listada nos EUA) | 0,1% | baixo (29) | -0,32 |
| 10 | TIM Brasil | Brasil | Comunicações | -1,19% | USD -12,0 mil | TIMS3.SA (local) | 0,0% | baixo (14) | -0,76 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- _Sem nota de pesquisa:_ Smart Fit, Patria Investments, Cemex, Liberty Latin America, Aura Minerals, Fleury, Grupo Aeroportuario del Sureste, Embraer, Lithium Argentina, TIM Brasil

## Exposições

### Por país (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Chile | 0,50% | 0,00% | +0,50% | 0,50% | ±2,00% |
| Panamá | 0,50% | 0,00% | +0,50% | 0,50% | ±2,00% |
| Regional (América Latina) | 3,98% | -3,48% | +0,50% | 7,45% | ±2,00% |
| Colômbia | 0,00% | -0,50% | -0,50% | 0,50% | ±2,00% |
| México | 4,65% | -5,11% | -0,46% | 9,76% | ±2,00% |
| Brasil | 26,40% | -26,70% | -0,30% | 53,09% | ±2,00% |
| Argentina | 3,53% | -3,67% | -0,13% | 7,20% | ±2,00% |
| Peru | 0,61% | -0,48% | +0,12% | 1,09% | ±2,00% |

### Por setor (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Financeiro | 8,63% | -7,13% | +1,50% | 15,76% | ±2,50% |
| Consumo discricionário | 4,32% | -5,82% | -1,50% | 10,14% | ±2,50% |
| Saúde | 1,51% | -2,73% | -1,22% | 4,25% | ±2,50% |
| Comunicações | 3,27% | -4,07% | -0,80% | 7,34% | ±2,50% |
| Consumo básico | 2,32% | -1,55% | +0,77% | 3,86% | ±2,50% |
| Tecnologia | 0,64% | 0,00% | +0,64% | 0,64% | ±2,50% |
| Utilidades públicas | 3,45% | -4,09% | -0,64% | 7,54% | ±2,50% |
| Energia | 3,10% | -2,59% | +0,51% | 5,69% | ±2,50% |
| Industriais | 3,98% | -3,54% | +0,43% | 7,52% | ±2,50% |
| Imobiliário | 0,33% | 0,00% | +0,33% | 0,33% | ±2,50% |
| Materiais | 8,61% | -8,40% | +0,21% | 17,02% | ±2,50% |

### Fatores de estilo (σ × PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Momentum | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Vol residual | 0,000 | 0,000 | +0,050 | 0,050 | ±0,100 |
| Tamanho (size) | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Liquidez | 0,000 | 0,000 | -0,044 | 0,044 | ±0,100 |
| Sensibilidade cambial | 0,000 | 0,000 | +0,028 | 0,028 | ±0,100 |
| Beta de mercado | 0,000 | 0,000 | +0,007 | 0,007 | ±0,100 |
| Valor (value) | 0,000 | 0,000 | +0,003 | 0,003 | ±0,100 |

## Hedges cambiais sugeridos

| Moeda | Exposição | Hedge | Instrumento | Racional |
|---|---|---|---|---|
| ARS | USD -1,3 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em ARS: -0,13% do PL (USD -1.341), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| BRL | USD -3,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em BRL: -0,30% do PL (USD -2.989), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 168.274, shorts USD 188.565; excedente líquido em BRL ≈ USD 20.291 (garantias/conversão). |
| CLP | USD +5,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em CLP: +0,50% do PL (USD 5.024), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| COP | USD -5,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em COP: -0,50% do PL (USD -5.024), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| MXN | USD -4,6 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em MXN: -0,46% do PL (USD -4.630), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 21.263, shorts USD 0; necessidade líquida de comprar MXN à vista ≈ USD 21.263. |
| PEN | USD +1,2 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em PEN: +0,12% do PL (USD 1.239), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |

## Ordens

| Item | Valor |
|---|---|
| Nº de ordens | 66 (compra 22, recompra 15, venda 12, venda a descoberto 17) |
| Volume bruto negociado | USD 338,0 mil (33,64% do PL) |
| Giro (Σ\|Δw\|) | 33,64% |
| Custo estimado | USD 263 (21,2 bps do volume; 0,026% do PL) |
| Maior % do volume médio diário | 0,2% |
| Maior prazo estimado de execução | 0,1 fech. |
| Ordens na B3 com perna no fracionário (sufixo F) | 44 de 44 |
| Ordens na BMV com perna em pico (abaixo do lote que forma preço) | 2 de 2 |
| Maior erro do arredondamento a ações inteiras | -0,006% do PL (CPA); soma 0,025% |

_22 ordens sem estimativa de custo — excluídas da soma de custos (custo ausente)._

## Pesquisa e visões

Autoria: pesquisa da gestão; 4 notas por empresa (4 com apoio de IA), 7 notas macro, 4 visões.

### Notas macro

#### AR — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O Banco Central da República Argentina descreve política monetária prudente no informe do terceiro trimestre. A avaliação permanece de baixa convicção diante dos riscos de inflação, câmbio e transmissão financeira.

Riscos:
- Volatilidade cambial e risco de liquidez.

#### BR — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O calendário do Banco Central confirma reunião do Copom em novembro. O teor integral da decisão mais recente não foi confirmado nesta pesquisa; não se atribui surpresa monetária nem direção ao mercado.

Riscos:
- Reprecificação dos juros e do câmbio.

#### CL — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O comunicado de outubro do Banco Central de Chile informa manutenção dos juros. A leitura de investimento permanece neutra, com convicção baixa quanto ao efeito sobre retornos residuais.

Riscos:
- Inflação e sensibilidade às commodities.

#### CO — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O informe de outubro do Banco de la República descreve manutenção dos juros após elevação em setembro. Julgamento de baixa convicção sobre o retorno residual das ações; preservar cautela com juros e risco fiscal.

Riscos:
- Persistência inflacionária e custo de financiamento.

#### GLOBAL — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O Federal Reserve publicou decisão em 2026-10-28. A existência do comunicado não sustenta, isoladamente, previsão direcional para a região; manter baixa convicção e atenção à inflação americana.

Riscos:
- Reprecificação de juros globais e dólar.

#### MX — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> A página de anúncios do Banco de México foi consultada, mas não forneceu confirmação suficiente do teor da decisão mais recente. Convicção baixa sobre a reação dos ativos mexicanos.

Riscos:
- Surpresa monetária e variação cambial.

#### PE — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> A busca pelo comunicado recente do Banco Central de Reserva del Perú não permitiu confirmar seu conteúdo integral. Sem convicção para inclinação macro discricionária no Peru.

Riscos:
- Lacuna de confirmação da política monetária.

### Visões aplicadas

| Empresa | Origem | Visão | Confiança | Restrições | Autoria |
|---|---|---|---|---|---|
| Grupo Financiero Galicia | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Globant | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Orizon | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Taesa | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |

## Otimizador

| Item | Valor |
|---|---|
| Situação / solver | ótimo / CLARABEL |
| Tempo de solução | 4,34 s |
| Alpha esperado (a.a.) | 2,11% |
| Custo esperado (a.a.) | 0,47% |
| Candidatos | 231 |
| Excluídos | bloqueio free float: 6, bloqueio free float desconhecido: 2, bloqueio resultado: 51, bloqueio resultado estimado: 2, sem linha short: 85, squeeze alto: 17, squeeze medio teto: 6, squeeze na teto: 44, visao no short: 4 |
| Restrições ativas | setor: Consumo discricionário, setor: Financeiro, estilo: Tamanho (size), estilo: Momentum, estilo: Vol residual, país (limite operacional): Chile, país (limite operacional): Colômbia, país (limite operacional): Regional (América Latina), país (limite operacional): Panamá, tema: estatais, tema: commodity:copper, tema: commodity:gold, turnover, teto vendido: Adecoagro, teto vendido: Lithium Argentina, teto vendido: Alpargatas, teto vendido: Auren Energia, teto vendido: Banrisul, teto vendido: Bradespar, teto vendido: Brava Energia, teto vendido: Cemig, teto vendido: Embraer, teto vendido: Energisa, teto vendido: Equatorial, teto vendido: Nu Holdings, teto vendido: Patria Investments, teto comprado: PicPay (PicS N.V.), teto vendido: Rede D'Or São Luiz, teto vendido: Rumo, teto vendido: Sanepar, teto vendido: Sigma Lithium, teto vendido: Smart Fit, teto vendido: StoneCo, teto comprado: Tenda, teto vendido: TIM Brasil, teto vendido: Ultrapar, teto vendido: Telefônica Brasil (Vivo), teto vendido: Arcos Dorados, teto vendido: Liberty Latin America, teto vendido: Cemex, teto vendido: Credicorp |

Observações do otimizador:
- Meta de vol ajustada pelo gestor: 3,64% (mandato 5,00%).
- Exposição bruta máxima efetivo: 2,00x (definido pelo gestor).
- Modo 'match': meta de vol não atingida com a aversão a risco dividida por até 64 (limite da busca); divisor usado 64,00.
- Teto de risco fatorial na carteira atingida (fatia fatorial máxima 10%): 1 passo(s); fatia idiossincrática: modelo de decisão 93,1%, modelo base 93,1%.
- Passadas de otimização: 2.
- Perna comprada 40,16%, vendida 39,93%; custo pontual 5,6 bps do PL; aluguel 10,9 bps a.a.
- Bloco macro no modelo de risco: petróleo Brent, cobre, ouro, índice do dólar (DXY) (0 emissores com beta pela média do setor).
- Fallback 1: apenas restrições da IA/PM (sem inclinações).
- [visões] IC das visões de IA = 0,01 (fase S1, teto 0,03).
- [visões] Grupo Financiero Galicia: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Globant: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Orizon: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Taesa: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Grupo Financiero Galicia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Globant: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Orizon: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Taesa: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Após as visões: Ortogonalização WLS (pesos 1/σ²): 0,0% da variância ponderada do alpha bruto era explicada por fatores e foi removida.
- [risco por nome] passo 1: PicPay (PicS N.V.) com 9,99% da variância (limite 8,00%); teto max_long reduzido para 1,56%
- [risco por nome] passo 1: Tenda com 9,14% da variância (limite 8,00%); teto max_long reduzido para 2,12%
- [risco por nome] passo 1: LA_LILA com 8,41% da variância (limite 8,00%); teto max_short reduzido para 2,36%

## Decisões pendentes do gestor

- [ ] Confirmar a disponibilidade de aluguel para as 40 posições vendidas antes da execução.
- [ ] Revisar 4 notas da pesquisa com apoio de IA.
- [ ] Validar 4 restrições propostas pela pesquisa (sem venda / sem compra / teto de peso).
- [ ] Decidir sobre os hedges cambiais sugeridos: ARS, BRL, CLP, COP, MXN, PEN.
- [ ] Revisar observações/relaxamentos do otimizador.
- [ ] Obter co-assinatura independente de Risco/Compliance (quatro olhos): Volatilidade ex-ante 3,61% fora de [4,00%, 6,00%].
- [ ] Aprovar ou rejeitar com justificativa — a decisão fica vinculada aos hashes dos dados de mercado, do mandato, da pesquisa e da proposta.

---

_Todos os números deste memo foram calculados e formatados por código a partir da proposta; textos de pesquisa são citados como fornecidos e rotulados pela origem._

---

_Hash da proposta (SHA-256): `72b02ea1f5bceaff2e10b11610b34356f8403ad641be965313d287363f6155a0`_
