# CDP — Cabra da Peste — Proposta da semana de 23/10/2026 (v1)

> Dados de mercado: retrato `store-2026-10-02+14-2026-10-22`. Dados reais (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética.

| Campo | Valor |
|---|---|
| Estado | **EM REVISÃO** |
| Proposta | CDP-2026-10-23-cdp-restricoes (versão 1) |
| Criada em / por | 23/10/2026 11:37 (Brasília) — CDP — motor quantitativo |
| PL de referência | USD 1,01 mm |
| Retrato dos dados de mercado | store-2026-10-02+14-2026-10-22 — `c9ee5f2ed83b` |
| Hash do mandato | `2ddf7d89ac76` |
| Hash da pesquisa | `874fd0fe5c72` |

## Resumo de risco

| Métrica | Valor | Referência |
|---|---|---|
| Vol ex-ante (a.a.) | 3,64% | meta aplicada 3,64% (mandato 5,00%); banda 3,00%–7,00% — dentro da banda |
| Vol fatorial (a.a.) | 0,77% | 10,81% da variância com κ_F no modelo base (limite 10,00%) |
| Vol específica (a.a.) | 3,55% | fonte pretendida do retorno (alpha puro) |
| Beta previsto | 0,002 | limite ±0,050 |
| Exposição bruta (% do PL) | 68,32% | faixa 50%–250% |
| Exposição líquida (% do PL) | +1,00% | limite ±1,00% |
| Comprado / vendido (% do PL) | 34,66% / -33,66% |  |
| Nº de posições compradas / vendidas | 39 / 36 |  |
| VaR 1d 99% | 0,53% (USD 5,4 mil) | paramétrico/histórico (modelo de risco) |
| ES 1d 99% | 0,61% (USD 6,1 mil) |  |
| VaR 1 semana 99% | 1,19% (USD 12,0 mil) |  |
| N efetivo | 64,2 | diversificação (1/Σw² normalizado) |
| Máx. fechamentos para liquidar | 0,2 fech. | long ≤ 3,0 fech.; short ≤ 2,0 fech. |
| % do gross liquidável em 1 fechamento | 100,00% | capacidade estrutural do leilão e da janela pré-fechamento |
| Fatia idiossincrática — modelo de decisão | 93,70% | meta 90%; piso 85% (com janelas de evento) |
| Fatia idiossincrática — modelo base | 89,19% | meta 90%; piso 85% (sem janelas de evento) |
| Inflação de 2ª ordem do risco fatorial (κ_F) | 1,45 | aplicada à variância fatorial na medida idiossincrática |

### Decomposição da variância ex-ante por grupo (modelo de decisão, κ_F no bloco fatorial)

| Grupo | Fração da variância |
|---|---|
| Mercado | 0,06% |
| País | 0,21% |
| Setor | 2,02% |
| Estilo | 3,54% |
| Macro (commodities e dólar) | 0,47% |
| Específico (idiossincrático) | 93,70% |

### Testes de estresse (resultado estimado)

| Cenário | % do PL | US$ |
|---|---|---|
| Quebra: 5 maiores posições compradas −30% | -2,08% | USD -21,0 mil |
| Squeeze: 5 maiores posições vendidas +30% | -1,87% | USD -18,9 mil |
| Tarifas dos EUA (abr/2025) | -0,30% | USD -3,0 mil |
| Gap Argentina +41% | -0,20% | USD -2,1 mil |
| Eleição México jun/2024 | -0,13% | USD -1,3 mil |
| Estresse de juros nos EUA jun/2022 | -0,12% | USD -1,2 mil |
| Commodities −15% | -0,11% | USD -1,1 mil |
| Gap Chile −15% | -0,07% | USD -0,8 mil |
| Brasil −15% | -0,07% | USD -0,8 mil |
| Gap México −13% | -0,05% | USD -0,6 mil |
| Gap Brasil −10% | -0,03% | USD -0,3 mil |
| Gap Colômbia −11% | -0,03% | USD -0,3 mil |
| Mercado da América Latina −20% | -0,02% | USD -0,3 mil |
| Gap Brasil +10% | +0,03% | USD +0,3 mil |
| Gap Peru −10% | +0,05% | USD +0,5 mil |
| Eleição Brasil out/2022 (2º turno) | +0,08% | USD +0,8 mil |
| México −15% | +0,20% | USD +2,0 mil |
| Gap Argentina −56% | +0,28% | USD +2,8 mil |
| Colapso do fator momentum −3σ | +0,28% | USD +2,9 mil |
| Choque fiscal BRL dez/2024 | +0,66% | USD +6,7 mil |
| Crise da covid (fev-mar/2020) | n/d | n/d |
| Estallido social Chile (out-nov/2019) | n/d | n/d |
| Joesley Day (mai/2017) | n/d | n/d |
| PASO Argentina 2019 | n/d | n/d |
| Taper tantrum (mai-jun/2013) | n/d | n/d |

### Maiores contribuições fatoriais (fração da variância)

| Fator | Contribuição |
|---|---|
| Estilo — Vol residual | 0,82% |
| Estilo — Momentum | 0,59% |
| Estilo — Liquidez | 0,55% |
| Setor — Industriais | 0,36% |
| Setor — Comunicações | 0,29% |
| Estilo — Beta de mercado | 0,24% |
| Setor — Saúde | 0,23% |
| Setor — Energia | 0,22% |
| Macro — petróleo Brent | 0,22% |
| Estilo — Sensibilidade cambial | 0,17% |

### Maiores contribuições de risco por empresa (fração da variância)

| Empresa | Contribuição |
|---|---|
| Riachuelo (ex-Guararapes) | 7,54% |
| Sigma Lithium | 7,46% |
| Tenda | 4,29% |
| Banco Pine | 3,81% |
| Lithium Argentina | 3,26% |
| Alpargatas | 3,07% |
| PagSeguro Digital | 2,58% |
| Cury | 2,56% |
| Fleury | 2,56% |
| Embraer | 2,50% |

## Controles do mandato

101 controles; 1 fora do limite (0 obrigatórios, 1 de alerta).

| Resultado | Tipo | Controle | Valor | Limite | Detalhe |
|---|---|---|---|---|---|
| fora | alerta | Meta da fatia idiossincrática (modelo base) | 0,8919 | 0,9000 | Fatia idiossincrática 89,19% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | obrigatório | Beta previsto | 0,0019 | 0,0500 | Beta previsto +0,002 (limite ±0,050). |
| dentro | obrigatório | Taxa de aluguel das posições vendidas | 0,0157 | 0,0500 | Taxas de aluguel dentro do limite de 5,00% a.a. |
| dentro | obrigatório | Exposição líquida por país (Argentina) | -0,0050 | 0,0200 | Líquido no país Argentina: −0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Brasil) | 0,0033 | 0,0200 | Líquido no país Brasil: 0,33% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Chile) | 0,0050 | 0,0200 | Líquido no país Chile: 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Colômbia) | 0,0024 | 0,0200 | Líquido no país Colômbia: 0,24% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Regional (América Latina)) | 0,0002 | 0,0200 | Líquido no país Regional (América Latina): 0,02% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (México) | 0,0042 | 0,0200 | Líquido no país México: 0,42% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Panamá) | 0,0050 | 0,0200 | Líquido no país Panamá: 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Peru) | -0,0050 | 0,0200 | Líquido no país Peru: −0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Uruguai) | 0,0000 | 0,0200 | Líquido no país Uruguai: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Defasagem dos dados de mercado | 0,0000 | 4,0000 | Dados de mercado de 23/10/2026 para a semana de 23/10/2026: 0 dias corridos (máximo 4). |
| dentro | obrigatório | Stop de drawdown (corte da exposição bruta) | 0,0000 | -0,0500 | Drawdown 0,00% (stop −5,00%, zeragem −7,50%). |
| dentro | obrigatório | Exposição bruta máxima | 0,6832 | 2,5000 | Exposição bruta 0,68x do PL (máximo 2,50x). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo de decisão) | 0,9370 | 0,8500 | Fatia idiossincrática 93,70% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo base) | 0,8919 | 0,8500 | Fatia idiossincrática 89,19% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Prazo de liquidação das posições compradas | 0,1554 | 3,0000 | Máximo de 0,16 fechamentos à capacidade estrutural do leilão (limite 3,0). |
| dentro | obrigatório | Prazo de liquidação das posições vendidas | 0,0835 | 2,0000 | Máximo de 0,08 fechamentos à capacidade estrutural do leilão (limite 2,0). |
| dentro | obrigatório | Compra só em nomes elegíveis e sem veto | 0,0000 | 0,0000 | Todas as compras são permitidas. |
| dentro | obrigatório | Peso máximo por nome (posição comprada) | 0,0186 | 0,0400 | Nenhuma posição comprada acima do teto por nome. |
| dentro | obrigatório | Peso máximo por nome (posição vendida) | 0,0125 | 0,0250 | Nenhuma posição vendida acima do teto por nome. |
| dentro | obrigatório | Exposição líquida | 0,0100 | 0,0100 | Líquido 1,00% do PL (limite ±1,00%); comprado 34,66%, vendido −33,66%. |
| dentro | obrigatório | Cobertura do modelo de risco | 0,0000 | 0,0000 | Todos os nomes com peso têm risco modelado. |
| dentro | obrigatório | Exposição líquida por setor (comunicações) | -0,0078 | 0,0250 | Líquido no setor Comunicações: −0,78% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo discricionário) | 0,0120 | 0,0250 | Líquido no setor Consumo discricionário: 1,20% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo básico) | 0,0106 | 0,0250 | Líquido no setor Consumo básico: 1,06% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (energia) | 0,0059 | 0,0250 | Líquido no setor Energia: 0,59% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (financeiro) | 0,0150 | 0,0250 | Líquido no setor Financeiro: 1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (saúde) | -0,0090 | 0,0250 | Líquido no setor Saúde: −0,90% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (industriais) | -0,0150 | 0,0250 | Líquido no setor Industriais: −1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (tecnologia) | 0,0027 | 0,0250 | Líquido no setor Tecnologia: 0,27% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (materiais) | 0,0067 | 0,0250 | Líquido no setor Materiais: 0,67% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (imobiliário) | 0,0039 | 0,0250 | Líquido no setor Imobiliário: 0,39% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (utilidades públicas) | -0,0150 | 0,0250 | Líquido no setor Utilidades públicas: −1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Sem nova venda a descoberto em nome vetado | 0,0000 | 0,0000 | Nenhuma venda a descoberto nova ou aumentada em nome com resultado próximo ou free float baixo. |
| dentro | obrigatório | Venda a descoberto só em linhas alugáveis e sem veto | 0,0000 | 0,0000 | Todas as posições vendidas são alugáveis e sem veto. |
| dentro | obrigatório | Sem posição vendida com risco alto de squeeze | 0,0000 | 0,0000 | Nenhuma posição vendida em nome com risco de squeeze alto. |
| dentro | obrigatório | Teto da posição vendida com risco médio de squeeze | 0,0062 | 0,0125 | Posições vendidas com risco de squeeze médio ou sem dado dentro do teto de 1,25%. |
| dentro | obrigatório | Exposição ao estilo (beta de mercado) | -0,0178 | 0,1000 | Exposição líquida −0,018 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (sensibilidade cambial) | -0,0124 | 0,1000 | Exposição líquida −0,012 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (liquidez) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (momentum) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (vol residual) | 0,0457 | 0,1000 | Exposição líquida +0,046 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (tamanho (size)) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (valor (value)) | -0,0132 | 0,1000 | Exposição líquida −0,013 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição líquida ao tema (estatais) | 0,0026 | 0,0100 | Líquido 0,26% no tema estatais (limite ±1,00%). |
| dentro | obrigatório | Volatilidade ex-ante máxima | 0,0364 | 0,0700 | Volatilidade ex-ante 3,64% a.a. (teto da banda 7,00%). |
| dentro | obrigatório | Pesos numéricos válidos | 0,0000 | 0,0000 | Todos os pesos são finitos. |
| dentro | alerta | Beta previsto (limite operacional) | 0,0019 | 0,0200 | Beta previsto +0,002 (limite operacional ±0,020). |
| dentro | alerta | Sensibilidade a commodity (cobre) | 0,0023 | 0,0300 | Σ w·β = +0,0023 (limite ±0,03); 10% na commodity ⇒ +0,02% do PL. |
| dentro | alerta | Sensibilidade a commodity (ouro) | -0,0072 | 0,0300 | Σ w·β = −0,0072 (limite ±0,03); 10% na commodity ⇒ −0,07% do PL. |
| dentro | alerta | Sensibilidade a commodity (petróleo) | 0,0020 | 0,0300 | Σ w·β = +0,0020 (limite ±0,03); 10% na commodity ⇒ +0,02% do PL. |
| dentro | alerta | Sensibilidade a commodity, limite operacional (cobre) | 0,0023 | 0,0100 | Σ w·β = +0,0023 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (ouro) | -0,0072 | 0,0100 | Σ w·β = −0,0072 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (petróleo) | 0,0020 | 0,0100 | Σ w·β = +0,0020 (limite operacional ±0,010). |
| dentro | alerta | Perda em gap de país | -0,0020 | -0,0150 | Pior cenário: Gap AR +41% com −0,20% do PL (limite −1,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Argentina) | -0,0050 | 0,0050 | Líquido no país Argentina: −0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Brasil) | 0,0033 | 0,0100 | Líquido no país Brasil: 0,33% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Chile) | 0,0050 | 0,0050 | Líquido no país Chile: 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Colômbia) | 0,0024 | 0,0050 | Líquido no país Colômbia: 0,24% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Regional (América Latina)) | 0,0002 | 0,0050 | Líquido no país Regional (América Latina): 0,02% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (México) | 0,0042 | 0,0100 | Líquido no país México: 0,42% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Panamá) | 0,0050 | 0,0050 | Líquido no país Panamá: 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Peru) | -0,0050 | 0,0050 | Líquido no país Peru: −0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Uruguai) | 0,0000 | 0,0050 | Líquido no país Uruguai: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Nível de revisão do drawdown | 0,0000 | -0,0250 | Drawdown 0,00% (gatilho de revisão −2,50%). |
| dentro | alerta | Exposição ao choque de evento | -0,0011 | 0,0015 | Reação residual ao choque do evento replicada na carteira: −0,106% do PL (limite ±0,15%). |
| dentro | alerta | Parcela fatorial do risco | 0,0630 | 0,1000 | Risco fatorial = 6,30% da variância com inflação de 2ª ordem κ_F = 1,45 no bloco fatorial (limite 10,00%); o restante é específico (alpha puro). |
| dentro | alerta | Exposição bruta mínima | 0,6832 | 0,5000 | Exposição bruta 0,68x do PL (mínimo recomendado 0,50x). |
| dentro | alerta | Meta da fatia idiossincrática (modelo de decisão) | 0,9370 | 0,9000 | Fatia idiossincrática 93,70% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0000 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 0,00% (teto 2,50%) somando CSN Siderúrgica Nacional, CSN Mineração: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0088 | 0,0400 | Comprado 0,88% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Metalúrgica Gerdau, Gerdau: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0000 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Itaúsa, Itaú Unibanco: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0125 | 0,0400 | Comprado 0,52% (teto 4,00%), vendido 1,25% (teto 2,50%) somando Bradespar, Vale: holding e controlada contam como um só nome. |
| dentro | alerta | Exposição líquida por setor, limite operacional (comunicações) | -0,0078 | 0,0150 | Líquido no setor Comunicações: −0,78% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo discricionário) | 0,0120 | 0,0150 | Líquido no setor Consumo discricionário: 1,20% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo básico) | 0,0106 | 0,0150 | Líquido no setor Consumo básico: 1,06% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (energia) | 0,0059 | 0,0150 | Líquido no setor Energia: 0,59% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (financeiro) | 0,0150 | 0,0150 | Líquido no setor Financeiro: 1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (saúde) | -0,0090 | 0,0150 | Líquido no setor Saúde: −0,90% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (industriais) | -0,0150 | 0,0150 | Líquido no setor Industriais: −1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (tecnologia) | 0,0027 | 0,0150 | Líquido no setor Tecnologia: 0,27% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (materiais) | 0,0067 | 0,0150 | Líquido no setor Materiais: 0,67% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (imobiliário) | 0,0039 | 0,0150 | Líquido no setor Imobiliário: 0,39% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (utilidades públicas) | -0,0150 | 0,0150 | Líquido no setor Utilidades públicas: −1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Contribuição máxima de um nome ao risco | 0,0754 | 0,0800 | Maior contribuição: Riachuelo (ex-Guararapes) com 7,54% da variância (limite 8,00%). |
| dentro | alerta | Exposição ao estilo, limite operacional (beta de mercado) | -0,0178 | 0,0500 | Exposição líquida −0,018 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (sensibilidade cambial) | -0,0124 | 0,0500 | Exposição líquida −0,012 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (liquidez) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (momentum) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (vol residual) | 0,0457 | 0,0500 | Exposição líquida +0,046 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (tamanho (size)) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (valor (value)) | -0,0132 | 0,0500 | Exposição líquida −0,013 (limite operacional ±0,05). |
| dentro | alerta | Ordens dentro da capacidade do fechamento | 0,0000 | 0,0000 | Toda abertura ou aumento cabe na capacidade do leilão e da janela pré-fechamento. |
| dentro | alerta | Giro semanal | 0,3000 | 0,3000 | Giro Σ\|Δw\| = 30,00% do PL (limite 30,00%). |
| dentro | alerta | Volatilidade ex-ante mínima | 0,0364 | 0,0300 | Volatilidade ex-ante 3,64% a.a. (piso da banda 3,00%). |
| na meta | indicador | Emissores sem fechamento negociável | 0,0000 | n/d | Nenhum emissor congelado. |
| na meta | indicador | Dados dos vetos de venda a descoberto | 21,0000 | n/d | 21 emissores sem data de resultado ou free float conhecidos (sem data: sinalizado, sem veto; sem free float em nome pequeno: vetado). Participação máxima do controlador sem fonte pública estruturada: não avaliada. |
| na meta | indicador | Origem dos dados | 0,0000 | n/d | Dados reais de snapshot imutável (hash verificado). |
| na meta | indicador | Distância à meta de volatilidade | 0,0364 | 0,0364 | Volatilidade ex-ante 3,64% contra a meta 3,64% (diferença 0,00 p.p.). |

## Principais posições

### 10 maiores posições compradas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Riachuelo (ex-Guararapes) | Brasil | Consumo discricionário | +1,86% | USD 18,8 mil | RIAA3.SA (local) | 0,6% | alto (70) | +2,04 |
| 2 | Hypera | Brasil | Saúde | +1,32% | USD 13,2 mil | HYPE3.SA (local) | 0,1% | baixo (18) | +1,59 |
| 3 | Millicom (Tigo) | Regional (América Latina) | Comunicações | +1,27% | USD 12,8 mil | TIGO (listada nos EUA) | 0,0% | baixo (15) | +0,24 |
| 4 | Genomma Lab | México | Consumo básico | +1,25% | USD 12,6 mil | LABB.MX (local) | 0,5% | n/d (35) | +1,86 |
| 5 | Tenda | Brasil | Consumo discricionário | +1,25% | USD 12,6 mil | TEND3.SA (local) | 0,1% | baixo (30) | +2,19 |
| 6 | Grupo Aeroméxico | México | Industriais | +1,25% | USD 12,6 mil | AERO (ADR) | 0,2% | baixo (16) | +1,13 |
| 7 | Petrobras | Brasil | Energia | +1,25% | USD 12,6 mil | PBR (ADR) | 0,0% | baixo (22) | +2,55 |
| 8 | PagSeguro Digital | Brasil | Financeiro | +1,25% | USD 12,6 mil | PAGS (listada nos EUA) | 0,0% | médio (40) | +0,72 |
| 9 | Suzano | Brasil | Materiais | +1,25% | USD 12,6 mil | SUZB3.SA (local) | 0,0% | baixo (18) | +0,12 |
| 10 | ISA Energia Brasil | Brasil | Utilidades públicas | +1,25% | USD 12,6 mil | ISAE4.SA (local) | 0,1% | baixo (38) | +1,01 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **Riachuelo (ex-Guararapes)**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Grupo Guararapes com indústria, lojas Riachuelo e marcas complementares, canais digitais e Midway Financeira. O perímetro corrente distingue mercadorias e serviços financeiros; a base comparativa gerencial exclui Midway Mall, enquanto demonstrações originais preservam seu perímetro histórico. Integração permite coordenar coleção, produção e entrega, com capital de estoque, ocupação e crédito próprio. A hipótese é que integração industrial, coleção e canais sustentem preço cheio, produtividade e crédito rentável. A condição decisiva é obter caixa depois de juros, aluguel, tecnologia e expansão. Lucro crescente não confirma a tese quando a carteira e investimentos absorvem recursos; venda de ativos e pagamentos de proventos precisam manter estados próprios. O modelo atualizado classifica o emissor como Em revisão; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
- **Hypera**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Grupo farmacêutico com marcas de prescrição, produtos sem prescrição, genéricos e especialidades, produção industrial e pesquisa de portfólio. Distribuição e demanda final têm prazos distintos. O retorno depende de mix, inovação, capacidade industrial, gasto comercial e estoque, sob regulação sanitária e de preços. Parcerias e marcas adquiridas ampliam opções, mas exigem desembolso e validação econômica, além de aprovação e execução comercial. A hipótese é que marcas, inovação e disciplina de estoque ampliem rentabilidade e conversão econômica do portfólio. A condição decisiva é manter demanda final e caixa depois de marketing, reinvestimento e juros, sem deslocar estoques para os canais. Redução de dívida apoiada por aporte de acionistas e pela operação deve ser distinguida para avaliar criação de valor por ação. O modelo atualizado classifica o emissor como Neutro; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
- **Millicom (Tigo)**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > A revisão pré-trade examina a nota publicada em 2026-10-11. Grupo de telecomunicações que opera serviços móveis, banda larga e conectividade empresarial na América Latina sob a marca Tigo. Aquisições, associadas e grupos de financiamento exigem bases próprias para avaliar o retorno e o caixa do acionista. A hipótese é que integração e disciplina comercial sustentem monetização depois de espectro, rede, arrendamentos e financiamento. A expansão precisa acrescentar caixa por unidade de capital, além de volume consolidado. Migração para planos recorrentes só cria valor quando melhora retenção e rentabilidade depois de atendimento e risco de recebimento. Mantém-se neutralidade qualitativa de baixa convicção. A revisão não representa nova conferência integral dos documentos primários.
- **Genomma Lab**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-21: Genomma reúne medicamentos de venda livre, cuidado pessoal, bebidas e nutrição infantil. Marcas e distribuição precisam remunerar promoção, fabricação e financiamento do canal. A administração relata retomada do sell-out mexicano. O avanço precisa persistir após gastos promocionais e converter-se em recebimentos. O modelo atualizado classifica o emissor como Neutro; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
- **Tenda**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Construtora e incorporadora de habitação popular ligada ao Minha Casa Minha Vida, com construção padronizada e mão de obra direta. Tenda e Alea têm sistemas construtivos, estágios e participações diferentes. A Alea desenvolve modelo industrial de casas e busca estabilizar a economia das unidades. Repasses bancários, pró-soluto pós-chaves e programas públicos mantêm riscos próprios de crédito e recebimento. Vendas, obra concluída e resultado reconhecido não são etapas equivalentes. A hipótese é que padronização e disciplina das safras sustentem margem e caixa depois de custos completos, perdas e financiamento. A condição decisiva é demonstrar retorno recorrente na Tenda sem extrapolar economias de entrega, enquanto Alea estabiliza execução dentro do capital disponível. A redução do crédito direto pode proteger qualidade da venda, mas também altera preço nominal e conversão. Recuperação de lucro exige controle de recebíveis, provisões e obrigações; geração gerencial beneficiada por derivativos não demonstra sozinha caixa estrutural. O modelo atualizado classifica o emissor como Compra; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
- **Grupo Aeroméxico**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-19: Holding mexicana de aviação comercial e fidelidade, com conexões domésticas e internacionais. A hipótese competitiva combina rede, oferta premium e receitas complementares; sua validade depende do retorno econômico após o custo completo da frota. O comunicado da Aeroméxico de 2026-10-19 atribui expansão da receita à operação internacional e informa reconhecimento de receita por revisão das estimativas de resgate na fidelidade. Nossa leitura exige separar esse efeito da demanda recorrente. O modelo atualizado classifica o emissor como Em revisão; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
- **Petrobras**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-19: Companhia integrada de petróleo, gás e refino. Nossa hipótese é que a escala e a produtividade do pré-sal remunerem o capital ao longo do ciclo; Brent favorável não comprova retorno dos novos projetos. Petrobras, 2026-08-06, relata produção maior, refino elevado e fortalecimento do caixa operacional. Nossa avaliação exige confrontar esse desempenho com desembolsos e obrigações de uso dos ativos. O modelo atualizado classifica o emissor como Compra; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
- **PagSeguro Digital**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: O PagBank oferece banco digital, crédito, cartões e aceitação de pagamentos para consumidores e empreendedores no Brasil. Seu perfil inclui comerciantes de pequeno porte e soluções presenciais e digitais. A economia combina remuneração de pagamentos, serviços, antecipação, captação e crédito. A integração deve ser examinada pela contribuição do cliente depois de custos, perdas e capital necessário. A hipótese é que pagamentos e relacionamento bancário ampliem contribuição por cliente depois de captação, risco e custo de servir. A condição decisiva é uso retido com retorno após perdas e financiamento. Volume de pagamentos, novas contas ou expansão do crédito não comprovam monetização nem vantagem econômica sustentável. O modelo atualizado classifica o emissor como Compra; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
- **Suzano**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Produtora de celulose de eucalipto e papéis, com base florestal, fábricas e canais no Brasil e exterior. Exportações expõem receitas a preço internacional, frete e câmbio; manutenção florestal e industrial preserva capacidade econômica. Tissue, embalagens e participação em outros produtores têm perímetros próprios. A aquisição posterior de controle da Arbex não compõe o trimestre apresentado, e minoritários conservam direitos sobre caixa e resultado. A hipótese é que produtividade florestal, escala industrial e disciplina comercial sustentem caixa por ação ao longo do ciclo. A condição decisiva é retorno depois de manutenção, terras, logística, proteção financeira e investimento. Diversificação em bens de consumo pode reduzir a dependência da celulose, mas precisa remunerar preço de aquisição e integração; capacidade maior e EBITDA ajustado não demonstram, isoladamente, criação de valor. O modelo atualizado classifica o emissor como Neutro; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
- **ISA Energia Brasil**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Transmissora de energia que opera concessões e desenvolve novas redes e reforços no Brasil. Remuneração de disponibilidade, construção e componentes financeiros têm naturezas próprias. Investidas de controle compartilhado não são integralmente atribuíveis. O ativo sob cobertura é uma ação preferencial; conversão de classes e oferta primária alteram a leitura por titular. A hipótese é que novos projetos e reforços gerem recebimentos com retorno suficiente depois de capital, dívida e emissão de ações. A condição decisiva é expansão econômica atribuível por ação, preservando disponibilidade. Construção e remuneração financeira do ativo contratual não comprovam crescimento equivalente de caixa livre; componentes com prazo determinado não foram perpetuados. O modelo atualizado classifica o emissor como Compra; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.

### 10 maiores posições vendidas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Auren Energia | Brasil | Utilidades públicas | -1,25% | USD -12,6 mil | AURE3.SA (local) | 0,1% | baixo (29) | -2,20 |
| 2 | Fleury | Brasil | Saúde | -1,25% | USD -12,6 mil | FLRY3.SA (local) | 0,1% | baixo (37) | +0,44 |
| 3 | Brava Energia | Brasil | Energia | -1,25% | USD -12,6 mil | BRAV3.SA (local) | 0,1% | baixo (31) | -0,95 |
| 4 | Lithium Argentina | Argentina | Materiais | -1,25% | USD -12,6 mil | LAR (listada nos EUA) | 0,1% | baixo (25) | -0,15 |
| 5 | Ultrapar | Brasil | Energia | -1,25% | USD -12,6 mil | UGPA3.SA (local) | 0,0% | baixo (11) | -0,27 |
| 6 | Adecoagro | Argentina | Consumo básico | -1,25% | USD -12,6 mil | AGRO (listada nos EUA) | 0,2% | baixo (20) | +0,59 |
| 7 | Liberty Latin America | Regional (América Latina) | Comunicações | -1,25% | USD -12,6 mil | LILAK (listada nos EUA) | 0,1% | baixo (24) | -1,75 |
| 8 | Energisa | Brasil | Utilidades públicas | -1,25% | USD -12,6 mil | ENGI11.SA (local) | 0,0% | baixo (22) | -0,74 |
| 9 | MercadoLibre | Brasil | Consumo discricionário | -1,25% | USD -12,6 mil | MELI (listada nos EUA) | 0,0% | baixo (9) | -0,80 |
| 10 | Sanepar | Brasil | Utilidades públicas | -1,25% | USD -12,6 mil | SAPR11.SA (local) | 0,1% | baixo (19) | -1,14 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **Auren Energia**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-12: Geradora de energia com portfólio hidrelétrico, eólico e solar e atividade de comercialização e soluções no mercado livre. A integração dos negócios adquiridos exige distinguir entidade operadora, holding e participações econômicas. Geração física divulgada pode incluir ativos de propriedade compartilhada em base diferente do resultado atribuível. A hipótese é que portfólio e contratação reduzam o custo de atender clientes e gerem caixa recorrente após investimento e financiamento. A condição decisiva é margem realizada, com proteção e geração compatíveis com as obrigações. Receita maior, marcação de contratos e dividendos declarados por investidas não comprovam recuperação equivalente de caixa. O modelo atualizado classifica o emissor como Neutro; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 28,6 e aluguel em 0,07%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Hidrologia, vento, restrições e preços regionais podem elevar compras ou reduzir margem. Dívida, garantias e integração exigem caixa. Marcação de contratos e compensações estimadas não comprovam recebimento ou liquidez livre.
- **Fleury**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Serviços de medicina diagnóstica em unidades de atendimento e atendimento móvel; exames para laboratórios e hospitais; novos elos ambulatoriais, infusão e plataformas digitais. Marcas locais e a combinação com Pardini ampliam a rede técnica e de distribuição. O resultado depende de utilização, mix, relacionamento médico e com fontes pagadoras, controle de glosas e integração. Aquisições regionais e novos elos têm desembolsos, riscos e direitos próprios. A hipótese é que marcas, rede técnica e integração ampliem utilização e margem com reinvestimento disciplinado. A condição decisiva é transformar crescimento orgânico e adquirido em caixa depois de juros, arrendamentos e aquisição. A melhora do resultado consolidado precisa ser atribuível ao acionista e sustentar retorno econômico, sem confundir entrada de novos ativos com produtividade recorrente. O modelo atualizado classifica o emissor como Venda; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 37,3 e aluguel em 0,69%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Glosas, concentração em pagadores, custos de pessoal e integração podem limitar conversão. Aquisições e novos elos exigem capital; caixa livre antes de juros e aluguel pode exagerar disponibilidade econômica.
- **Brava Energia**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Empresa integrada de produção de petróleo e gás em terra e no mar, processamento, logística e refino. O portfólio combinado reúne operações com participações e custos distintos. Vendas entre negócios são eliminadas no consolidado; produção própria, compra de petróleo e margem de derivados não devem ser somadas como contribuições independentes. O controle foi adquirido pela Ecopetrol em operação concluída depois do trimestre. A hipótese é que confiabilidade dos campos, novos poços e integração industrial sustentem caixa depois de proteção financeira, manutenção e obrigações de aquisição. A condição decisiva é margem realizada com capital suficiente e transmissão ao minoritário sob o novo controle. Aumento de EBITDA, capacidade e preço do petróleo não demonstra melhora uniforme da produção, rentabilidade por barril ou liquidez livre. O modelo atualizado classifica o emissor como Neutro; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 30,6 e aluguel em 1,00%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Paradas, integridade, preço do petróleo, proteção financeira e obrigações de aquisição podem absorver caixa. Saldo restrito não é liquidez livre; novo controle e partes relacionadas exigem verificar retorno e direitos do minoritário.
- **Lithium Argentina**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Companhia com interesses em ativos de lítio argentinos, operando Cauchari-Olaroz com Ganfeng e desenvolvendo outros projetos. Indicadores físicos do projeto e direitos econômicos da companhia listada não são a mesma base. A hipótese é que produtividade e disciplina de capital permitam gerar caixa atribuível em um ciclo de preços adverso, preservando capacidade de financiar desenvolvimento. A expansão é uma opção condicionada: retorno exige engenharia, licenças, financiamento e recuperação industrial comprovados, sem diluição que absorva o benefício. O modelo atualizado classifica o emissor como Em revisão; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 24,8 e aluguel em 0,30%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Preço do lítio, execução industrial e financiamento podem impedir retorno. A expansão envolve risco de tecnologia e licenças; acesso ao caixa do projeto depende de parceiros e obrigações, enquanto financiamento conversível pode diluir direitos econômicos.
- **Ultrapar**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-20: Ultrapar aloca capital em distribuição de combustíveis, GLP, armazenagem e logística por Ipiranga, Ultragaz, Ultracargo e Hidrovias. Contratos, suprimento, giro e utilização têm economias distintas, exigindo controle do perímetro consolidado e de minoritários. O release do 2T26 atribui parte da geração de caixa à liberação de giro na Ipiranga. Nossa hipótese exige repetição da geração depois de manutenção e compromissos comerciais, sem extrapolar essa liberação. O modelo atualizado classifica o emissor como Neutro; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 10,9 e aluguel em 0,21%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Normalização das margens, giro e refinanciamento podem absorver recursos. Capacidade nova sem retorno e direitos de minoritários limitam caixa atribuível.
- **Adecoagro**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Grupo agroindustrial com açúcar, etanol, energia, alimentos, agricultura e fertilizantes. A leitura de diversificação exige mapear ativos, participações e segmentos que efetivamente pertencem ao acionista listado. A hipótese é que ativos integrados convertam produtividade e flexibilidade de produtos em caixa após manutenção e capital de giro. A diversificação só acrescenta valor se cada investimento remunerar seu capital, inclusive em condições adversas de preço e clima. A expansão de perímetro, isoladamente, não demonstra melhora econômica. O modelo atualizado classifica o emissor como Neutro; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 19,7 e aluguel em 0,30%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Clima, preços agrícolas, energia e execução industrial podem se combinar com necessidade de giro. A integração de novas operações amplia a importância de garantias, participação de parceiros e disciplina de capital; a rentabilidade da expansão permanece a comprovar.
- **Liberty Latin America**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Operadora de banda larga, telefonia, vídeo e conectividade empresarial na América Latina e Caribe, com rede submarina e terrestre. Grupos de financiamento, participações de minoritários e classes de ações precisam ser avaliados para determinar o caixa atribuível. A hipótese é que qualidade da rede e atendimento sustentem retenção e preço líquido depois de manutenção, equipamentos e financiamento. Melhor resultado comercial só cria valor se a geração residual chega ao acionista da classe coberta. O custo de renovar a rede e restaurar ativos precisa permanecer na avaliação através do ciclo. O modelo atualizado classifica o emissor como Em revisão; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 24,4 e aluguel em 0,30%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Concorrência, danos climáticos e reinvestimento podem pressionar margem e caixa. Refinanciamento, juros e obrigações por grupo podem limitar distribuição. Ganhos projetados de contratos de tecnologia precisam de comprovação, sem incorporar valor presente calculado pela gestão ao modelo.
- **Energisa**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Grupo de distribuição e transmissão de eletricidade, distribuição de gás, geração e soluções de energia. Negócios financeiros e de comercialização têm riscos diferentes das redes reguladas. As participações em gás combinam consolidação e equivalência patrimonial. A unidade negociada e os minoritários exigem conciliar resultado e direitos de capital por titular. A hipótese é que investimento em redes e qualidade do serviço sustente remuneração regulatória e caixa por unidade depois de financiamento. A condição decisiva é retorno da base investida efetivamente recebido com perdas, despesas e capital compatíveis. Reajuste da conta do consumidor e reversão de contingências não comprovam melhora recorrente da margem atribuível. O modelo atualizado classifica o emissor como Venda; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 22,0 e aluguel em 0,03%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Qualidade, perdas, inadimplência e reconhecimento regulatório podem exigir investimento adicional. Dívida e custo financeiro consomem resultado. Reversões, créditos setoriais e capital de minoritários não são caixa livre integralmente atribuível.
- **MercadoLibre**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-19: Ecossistema latino-americano de comércio, logística, publicidade e serviços financeiros. Nossa leitura exige avaliar a complementaridade das atividades junto do capital e do financiamento que cada negócio demanda. MercadoLibre, 2026-08-05: a carta associa crescimento do engajamento ao investimento comercial, enquanto resultado operacional e lucro caíram na comparação anual. Testar se a retenção persiste com economia unitária suficiente. O modelo atualizado classifica o emissor como Em revisão; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 9,3 e aluguel em 0,30%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Subsídios permanentes, perdas de crédito e financiamento podem impedir transmissão do crescimento ao caixa econômico.
- **Sanepar**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11: Prestadora de tratamento e distribuição de água, coleta e tratamento de esgoto em concessões municipais. Economias atendidas, volume, tarifa e eficiência determinam receita. Universalização e redes exigem investimento; contratos, regulação e controle público limitam a livre destinação de recursos. A hipótese é que expansão e eficiência sustentem remuneração adequada das redes. A condição decisiva é gerar caixa depois de obras e juros sem atribuir ao acionista valores destinados à modicidade tarifária. Resultado ajustado, precatório e capital regulado possuem obrigações próprias. O modelo atualizado classifica o emissor como Neutro; sua classificação não substitui as lacunas documentais. Mantém-se abstenção direcional de baixa convicção.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Squeeze em 18,9 e aluguel em 0,05%. Controle, free float, disponibilidade efetiva de empréstimo e eventos não foram integralmente requalificados nesta sessão. Regulação, recursos hídricos, perdas e obras podem reduzir retorno. Controle público e modicidade tarifária limitam distribuição. Caixa de precatório e ajuste de lucro não eliminam obrigações; contratos e investimento exigem capital.

## Exposições

### Por país (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Chile | 0,50% | 0,00% | +0,50% | 0,50% | ±2,00% |
| Panamá | 0,50% | 0,00% | +0,50% | 0,50% | ±2,00% |
| Peru | 0,00% | -0,50% | -0,50% | 0,50% | ±2,00% |
| Argentina | 3,17% | -3,67% | -0,50% | 6,83% | ±2,00% |
| México | 2,84% | -2,42% | +0,42% | 5,26% | ±2,00% |
| Brasil | 24,07% | -23,75% | +0,33% | 47,82% | ±2,00% |
| Colômbia | 1,06% | -0,83% | +0,24% | 1,89% | ±2,00% |
| Regional (América Latina) | 2,52% | -2,50% | +0,02% | 5,02% | ±2,00% |

### Por setor (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Utilidades públicas | 4,48% | -5,98% | -1,50% | 10,47% | ±2,50% |
| Industriais | 3,14% | -4,64% | -1,50% | 7,78% | ±2,50% |
| Financeiro | 6,09% | -4,59% | +1,50% | 10,68% | ±2,50% |
| Consumo discricionário | 4,95% | -3,75% | +1,20% | 8,70% | ±2,50% |
| Consumo básico | 2,31% | -1,25% | +1,06% | 3,56% | ±2,50% |
| Saúde | 1,32% | -2,22% | -0,90% | 3,53% | ±2,50% |
| Comunicações | 2,30% | -3,08% | -0,78% | 5,39% | ±2,50% |
| Materiais | 4,75% | -4,08% | +0,67% | 8,83% | ±2,50% |
| Energia | 4,27% | -3,68% | +0,59% | 7,95% | ±2,50% |
| Imobiliário | 0,39% | 0,00% | +0,39% | 0,39% | ±2,50% |
| Tecnologia | 0,66% | -0,39% | +0,27% | 1,05% | ±2,50% |

### Fatores de estilo (σ × PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Momentum | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Tamanho (size) | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Liquidez | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Vol residual | 0,000 | 0,000 | +0,046 | 0,046 | ±0,100 |
| Beta de mercado | 0,000 | 0,000 | -0,018 | 0,018 | ±0,100 |
| Valor (value) | 0,000 | 0,000 | -0,013 | 0,013 | ±0,100 |
| Sensibilidade cambial | 0,000 | 0,000 | -0,012 | 0,012 | ±0,100 |

## Hedges cambiais sugeridos

| Moeda | Exposição | Hedge | Instrumento | Racional |
|---|---|---|---|---|
| ARS | USD -5,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em ARS: -0,50% do PL (USD -5.035), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| BRL | USD +3,3 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em BRL: +0,33% do PL (USD 3.277), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 177.134, shorts USD 186.086; excedente líquido em BRL ≈ USD 8.952 (garantias/conversão). |
| CLP | USD +5,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em CLP: +0,50% do PL (USD 5.035), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| COP | USD +2,4 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em COP: +0,24% do PL (USD 2.383), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| MXN | USD +4,2 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em MXN: +0,42% do PL (USD 4.238), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 12.588, shorts USD 0; necessidade líquida de comprar MXN à vista ≈ USD 12.588. |
| PEN | USD -5,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em PEN: -0,50% do PL (USD -5.035), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |

## Ordens

| Item | Valor |
|---|---|
| Nº de ordens | 89 (compra 24, recompra 15, venda 18, venda a descoberto 32) |
| Volume bruto negociado | USD 306,0 mil (30,39% do PL) |
| Giro (Σ\|Δw\|) | 30,39% |
| Custo estimado | USD 498 (16,3 bps do volume; 0,049% do PL) |
| Maior % do volume médio diário | 0,2% |
| Maior prazo estimado de execução | 0,1 fech. |
| Ordens na B3 com perna no fracionário (sufixo F) | 41 de 41 |
| Ordens na BMV com perna em pico (abaixo do lote que forma preço) | 1 de 1 |
| Maior erro do arredondamento a ações inteiras | +0,010% do PL (BAP); soma 0,055% |

## Pesquisa e visões

Autoria: pesquisa da gestão; 240 notas por empresa (240 com apoio de IA), 7 notas macro, 118 visões.

4 manchetes consideradas — conteúdo NÃO confiável, não reproduzido neste memo.

### Notas macro

#### AR — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O BCRA lista divulgação do relatório de dívida externa privada em 2026-10-29 e do mercado de câmbio em 2026-10-30, com datas estimadas. A exposição exige cautela com conversibilidade e financiamento, sem projetar reservas ou preços.

Riscos:
- Moeda, inflação, acesso ao caixa e financiamento.

Implicações para a carteira:
- Preservar postura defensiva e neutralidade; dimensionamento e limites exclusivamente pelo modelo quantitativo.

Eventos:
- Relatórios de setor externo e câmbio (29/10/2026; incerto)

#### BR — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> A janela eleitoral brasileira exige cautela com estatais, concessões e custo de capital. O TSE confirma a etapa final da campanha; não se adota previsão do resultado eleitoral.

Riscos:
- Risco fiscal, regulatório e de abertura com descontinuidade de preços.

Implicações para a carteira:
- Preservar postura defensiva e neutralidade; dimensionamento e limites exclusivamente pelo modelo quantitativo.

Eventos:
- Eleição brasileira (25/10/2026; incerto)

#### CL — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O calendário primário do Banco Central de Chile prevê reunião concluída em 2026-10-27. Não se antecipa a decisão; inflação e remuneração regulada continuam riscos relevantes para os emissores.

Riscos:
- Juros, moeda e preços de metais.

Implicações para a carteira:
- Preservar postura defensiva e neutralidade; dimensionamento e limites exclusivamente pelo modelo quantitativo.

Eventos:
- Decisão de política monetária (27/10/2026; incerto)

#### CO — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O Banco de la República anuncia reunião de taxa em 2026-10-30. A leitura é defensiva para crédito e financiamento; o resultado futuro permanece incerto.

Riscos:
- Inflação, crédito, câmbio e custo de capital.

Implicações para a carteira:
- Preservar postura defensiva e neutralidade; dimensionamento e limites exclusivamente pelo modelo quantitativo.

Eventos:
- Decisão da taxa de intervenção (30/10/2026; incerto)

#### GLOBAL — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O calendário do Federal Reserve confirma reunião em 2026-10-27 e 2026-10-28. Mantém-se neutralidade direcional e postura defensiva diante do risco de juros e dólar para a região.

Riscos:
- Juros americanos, dólar, commodities e aversão a risco.

Implicações para a carteira:
- Preservar postura defensiva e neutralidade; dimensionamento e limites exclusivamente pelo modelo quantitativo.

Eventos:
- Decisão do FOMC (28/10/2026; incerto)

#### MX — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O calendário primário do Banxico prevê a próxima decisão em 2026-11-05. Resultados empresariais e financiamento americano recomendam neutralidade, sem presumir nova mudança de juros.

Riscos:
- Câmbio, demanda americana e execução industrial.

Implicações para a carteira:
- Preservar postura defensiva e neutralidade; dimensionamento e limites exclusivamente pelo modelo quantitativo.

Eventos:
- Decisão de política monetária (05/11/2026; incerto)

#### PE — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> A consulta ao portal do BCRP não entregou material suficiente para requalificar o calendário monetário restante. Mantém-se neutralidade, com atenção ao ciclo dos metais e aos direitos econômicos das participações.

Riscos:
- Lacuna do calendário primário e dependência de commodities.

Implicações para a carteira:
- Preservar postura defensiva e neutralidade; dimensionamento e limites exclusivamente pelo modelo quantitativo.

### Visões aplicadas

| Empresa | Origem | Visão | Confiança | Restrições | Autoria |
|---|---|---|---|---|---|
| Adecoagro | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| BBVA Argentina | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Corporación América Airports | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Central Puerto | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Cresud | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Grupo Financiero Galicia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Globant | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| IRSA | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Lithium Argentina | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco Macro | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Pampa Energía | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Supervielle | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Transportadora de Gas del Sur | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| YPF | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Afya | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Allos | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Alpargatas | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Alupar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Ambev | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Aura Minerals | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Auren Energia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Axia Energia (ex-Eletrobras) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banrisul | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco do Brasil | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| BB Seguridade | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Bemobi | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco Bradesco | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Bradespar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Braskem | pesquisa (IA) | 0 | 100% | sem venda, sem compra | pesquisa da gestão |
| Brava Energia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Companhia Brasileira de Alumínio | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| C&A Modas | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Cemig | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Copasa | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Copel | pesquisa (IA) | 0 | 100% | sem compra | pesquisa da gestão |
| Cosan | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Cury | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Caixa Seguridade | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Embraer | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Energisa | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Eneva | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Equatorial | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| EZTec | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Fleury | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Gerdau | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| GPS Participações | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Hypera | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Inter&Co | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| ISA Energia Brasil | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Itaú Unibanco | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| JBS N.V. | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Klabin | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Magazine Luiza | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Marcopolo | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Mateus | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Movida | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Nu Holdings | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Orizon | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| PagSeguro Digital | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Pague Menos | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Patria Investments | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Petrobras | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Petz-Cobasi | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| PicPay (PicS N.V.) | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Banco Pine | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Plano & Plano | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Porto Seguro | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| PRIO | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Randoncorp | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Rede D'Or São Luiz | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Riachuelo (ex-Guararapes) | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Rumo | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Sabesp | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Sanepar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco Santander Brasil | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| São Martinho | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Sigma Lithium | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Simpar | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Smart Fit | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| StoneCo | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Suzano | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Tenda | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| TIM Brasil | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Totvs | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Tupy | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Ultrapar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Unipar | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Usiminas | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Vale | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Vibra Energia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Telefônica Brasil (Vivo) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| VTEX | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco de Chile | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Banco Santander-Chile | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Enel Chile | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| LATAM Airlines Group | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| SQM | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Cibest (ex-Bancolombia) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| GeoPark | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Arcos Dorados | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Fortuna Mining | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Liberty Latin America | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| MercadoLibre | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Aeroméxico | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| América Móvil | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Aeroportuario del Sureste | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Cemex | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| FEMSA | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| First Majestic Silver | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Aeroportuario del Pacífico | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Genomma Lab | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Aeroportuario Centro Norte | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Orbia | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Vista Energy | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Volaris | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Credicorp | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Hudbay Minerals | pesquisa (IA) | 0 | 100% | sem compra | pesquisa da gestão |
| Nexa Resources | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |

## Otimizador

| Item | Valor |
|---|---|
| Situação / solver | ótimo / CLARABEL |
| Tempo de solução | 3,78 s |
| Alpha esperado (a.a.) | 2,28% |
| Custo esperado (a.a.) | 0,39% |
| Candidatos | 230 |
| Excluídos | bloqueio free float: 5, bloqueio resultado: 5, bloqueio resultado estimado: 1, sem linha short: 67, squeeze alto: 45, squeeze medio teto: 10, squeeze na teto: 44, visao no long: 3, visao no short: 47, visao teto peso: 70 |
| Restrições ativas | net exposure, meta de vol, setor: Financeiro, setor: Industriais, setor: Utilidades públicas, estilo: Tamanho (size), estilo: Momentum, estilo: Liquidez, país (limite operacional): Argentina, país (limite operacional): Chile, país (limite operacional): Panamá, país (limite operacional): Peru, participação do país: Argentina, participação do país: Brasil, turnover, teto vendido: Adecoagro, teto vendido: Grupo Financiero Galicia, teto vendido: Lithium Argentina, teto vendido: Alpargatas, teto vendido: Auren Energia, teto vendido: Bradespar, teto vendido: Brava Energia, teto vendido: Energisa, teto vendido: Fleury, teto comprado: ISA Energia Brasil, teto vendido: Nu Holdings, teto vendido: Orizon, teto comprado: PagSeguro Digital, teto comprado: Petrobras, teto comprado: Riachuelo (ex-Guararapes), teto vendido: Sanepar, teto vendido: Sigma Lithium, teto comprado: Suzano, teto comprado: Tenda, teto vendido: TIM Brasil, teto vendido: Ultrapar, teto vendido: Grupo Cibest (ex-Bancolombia), teto vendido: Arcos Dorados, teto comprado: Fortuna Mining, teto vendido: Liberty Latin America, teto vendido: MercadoLibre, teto comprado: Grupo Aeroméxico, teto vendido: Grupo Aeroportuario del Sureste, teto comprado: Genomma Lab |

Observações do otimizador:
- Meta de vol ajustada pelo gestor: 3,64% (mandato 5,00%).
- Exposição bruta máxima efetivo: 2,00x (definido pelo gestor).
- Teto de risco fatorial: passo inviável; mantida a solução anterior.
- Teto de risco fatorial na carteira atingida (fatia fatorial máxima 10%): 1 passo(s); fatia idiossincrática: modelo de decisão 93,7%, modelo base 89,2%.
- Passadas de otimização: 3.
- Reparo de complementaridade: 9 emissores tinham perna comprada e vendida simultâneas (custo subestimado) e foram re-otimizados com uma única perna.
- Perna comprada 34,66%, vendida 33,66%; custo pontual 4,5 bps do PL; aluguel 9,6 bps a.a.
- Bloco macro no modelo de risco: petróleo Brent, cobre, ouro, índice do dólar (DXY) (0 emissores com beta pela média do setor).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (×1,50 na vol de BR)
- Fallback 1: apenas restrições da IA/PM (sem inclinações).
- [visões] IC das visões de IA = 0,01 (fase S1, teto 0,03).
- [visões] Cresud: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Globant: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Transportadora de Gas del Sur: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] YPF: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Afya: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Allos: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Ambev: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Banco do Brasil: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Banco Bradesco: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Braskem: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Companhia Brasileira de Alumínio: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] C&A Modas: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Copel: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Cosan: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] EZTec: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Gerdau: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] GPS Participações: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Hypera: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Inter&Co: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Itaú Unibanco: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Klabin: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Magazine Luiza: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Grupo Mateus: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Movida: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Pague Menos: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Patria Investments: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Petz-Cobasi: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] PicPay (PicS N.V.): 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Banco Pine: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Plano & Plano: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Randoncorp: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Riachuelo (ex-Guararapes): 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Banco Santander Brasil: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Simpar: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Smart Fit: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Unipar: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Usiminas: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Vale: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Banco de Chile: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Banco Santander-Chile: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Enel Chile: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Cemex: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] FEMSA: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Grupo Aeroportuario Centro Norte: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Orbia: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Vista Energy: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Volaris: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Hudbay Minerals: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Nexa Resources: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Adecoagro: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] BBVA Argentina: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Corporación América Airports: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Central Puerto: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cresud: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Financiero Galicia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Globant: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] IRSA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Lithium Argentina: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Macro: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Pampa Energía: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Supervielle: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Transportadora de Gas del Sur: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] YPF: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Afya: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Allos: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Alpargatas: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Alupar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Ambev: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Aura Minerals: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Auren Energia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Axia Energia (ex-Eletrobras): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banrisul: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco do Brasil: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] BB Seguridade: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Bemobi: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Bradesco: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Bradespar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Braskem: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Brava Energia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Companhia Brasileira de Alumínio: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] C&A Modas: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cemig: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Copasa: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Copel: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cosan: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cury: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Caixa Seguridade: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Embraer: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Energisa: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Eneva: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Equatorial: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] EZTec: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Fleury: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Gerdau: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] GPS Participações: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Hypera: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Inter&Co: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] ISA Energia Brasil: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Itaú Unibanco: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] JBS N.V.: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Klabin: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Magazine Luiza: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Marcopolo: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Mateus: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Movida: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Nu Holdings: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Orizon: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] PagSeguro Digital: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Pague Menos: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Patria Investments: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Petrobras: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Petz-Cobasi: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] PicPay (PicS N.V.): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Pine: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Plano & Plano: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Porto Seguro: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] PRIO: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Randoncorp: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Rede D'Or São Luiz: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Riachuelo (ex-Guararapes): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Rumo: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Sabesp: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Sanepar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Santander Brasil: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] São Martinho: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Sigma Lithium: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Simpar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Smart Fit: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] StoneCo: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Suzano: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Tenda: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] TIM Brasil: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Totvs: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Tupy: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Ultrapar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Unipar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Usiminas: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Vale: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Vibra Energia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Telefônica Brasil (Vivo): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] VTEX: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco de Chile: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Santander-Chile: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Enel Chile: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LATAM Airlines Group: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] SQM: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Cibest (ex-Bancolombia): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] GeoPark: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_ARCOS: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_FORTUNA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_LILA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_MELI: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Aeroméxico: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] América Móvil: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Aeroportuario del Sureste: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cemex: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] FEMSA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] First Majestic Silver: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Aeroportuario del Pacífico: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Genomma Lab: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Aeroportuario Centro Norte: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Orbia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Vista Energy: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Volaris: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Credicorp: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Hudbay Minerals: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Nexa Resources: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Braskem: visões proíbem compra e venda — posição limitada a zero.
- [visões] Após as visões: Ortogonalização WLS (pesos 1/σ²): 0,0% da variância ponderada do alpha bruto era explicada por fatores e foi removida.
- [risco por nome] passo 1: Riachuelo (ex-Guararapes) com 8,20% da variância (limite 8,00%); teto max_long reduzido para 1,86%

## Decisões pendentes do gestor

- [ ] Dar ciência explícita aos limites de alerta atingidos: meta da fatia idiossincrática (modelo base).
- [ ] Validar posições vendidas com risco de squeeze médio ou alto: Grupo Financiero Galicia (médio).
- [ ] Confirmar a disponibilidade de aluguel para as 36 posições vendidas antes da execução.
- [ ] Revisar 240 notas da pesquisa com apoio de IA.
- [ ] Validar 118 restrições propostas pela pesquisa (sem venda / sem compra / teto de peso).
- [ ] Decidir sobre os hedges cambiais sugeridos: ARS, BRL, CLP, COP, MXN, PEN.
- [ ] Revisar observações/relaxamentos do otimizador.
- [ ] Obter co-assinatura independente de Risco/Compliance (quatro olhos): Limites de alerta reconhecidos: meta da fatia idiossincrática (modelo base). Nova posição vendida com risco de squeeze: Grupo Financiero Galicia (médio). Volatilidade ex-ante 3,64% fora de [4,00%, 6,00%].
- [ ] Aprovar ou rejeitar com justificativa — a decisão fica vinculada aos hashes dos dados de mercado, do mandato, da pesquisa e da proposta.

---

_Todos os números deste memo foram calculados e formatados por código a partir da proposta; textos de pesquisa são citados como fornecidos e rotulados pela origem._

---

_Hash da proposta (SHA-256): `fcd7aae2317838b41f827f778c004a0ad5d13f2a9ddec792cc2a843ebd48e7b2`_
