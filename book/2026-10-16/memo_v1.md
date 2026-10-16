# CDP — Cabra da Peste — Proposta da semana de 16/10/2026 (v1)

> Dados de mercado: retrato `store-2026-10-02+9-2026-10-15`. Dados reais (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética.

| Campo | Valor |
|---|---|
| Estado | **EM REVISÃO** |
| Proposta | CDP-2026-10-16-cdp-restricoes (versão 1) |
| Criada em / por | 16/10/2026 11:44 (Brasília) — CDP — motor quantitativo |
| PL de referência | USD 1,00 mm |
| Retrato dos dados de mercado | store-2026-10-02+9-2026-10-15 — `c03aa00d1dcb` |
| Hash do mandato | `2ddf7d89ac76` |
| Hash da pesquisa | `e783a1d4715f` |

## Resumo de risco

| Métrica | Valor | Referência |
|---|---|---|
| Vol ex-ante (a.a.) | 3,52% | meta aplicada 3,64% (mandato 5,00%); banda 3,00%–7,00% — dentro da banda |
| Vol fatorial (a.a.) | 0,65% | 8,09% da variância com κ_F no modelo base (limite 10,00%) |
| Vol específica (a.a.) | 3,46% | fonte pretendida do retorno (alpha puro) |
| Beta previsto | 0,000 | limite ±0,050 |
| Exposição bruta (% do PL) | 67,51% | faixa 50%–250% |
| Exposição líquida (% do PL) | +0,04% | limite ±1,00% |
| Comprado / vendido (% do PL) | 33,78% / -33,74% |  |
| Nº de posições compradas / vendidas | 38 / 35 |  |
| VaR 1d 99% | 0,52% (USD 5,2 mil) | paramétrico/histórico (modelo de risco) |
| ES 1d 99% | 0,59% (USD 5,9 mil) |  |
| VaR 1 semana 99% | 1,15% (USD 11,6 mil) |  |
| N efetivo | 60,9 | diversificação (1/Σw² normalizado) |
| Máx. fechamentos para liquidar | 0,2 fech. | long ≤ 3,0 fech.; short ≤ 2,0 fech. |
| % do gross liquidável em 1 fechamento | 100,00% | capacidade estrutural do leilão e da janela pré-fechamento |
| Fatia idiossincrática — modelo de decisão | 95,12% | meta 90%; piso 85% (com janelas de evento) |
| Fatia idiossincrática — modelo base | 91,91% | meta 90%; piso 85% (sem janelas de evento) |
| Inflação de 2ª ordem do risco fatorial (κ_F) | 1,45 | aplicada à variância fatorial na medida idiossincrática |

### Decomposição da variância ex-ante por grupo (modelo de decisão, κ_F no bloco fatorial)

| Grupo | Fração da variância |
|---|---|
| Mercado | 0,00% |
| País | 0,46% |
| Setor | 1,61% |
| Estilo | 2,51% |
| Macro (commodities e dólar) | 0,30% |
| Específico (idiossincrático) | 95,12% |

### Testes de estresse (resultado estimado)

| Cenário | % do PL | US$ |
|---|---|---|
| Quebra: 5 maiores posições compradas −30% | -2,37% | USD -23,8 mil |
| Squeeze: 5 maiores posições vendidas +30% | -1,87% | USD -18,8 mil |
| Tarifas dos EUA (abr/2025) | -0,25% | USD -2,5 mil |
| Gap Argentina +41% | -0,20% | USD -2,1 mil |
| Eleição México jun/2024 | -0,12% | USD -1,2 mil |
| Gap Chile −15% | -0,07% | USD -0,8 mil |
| Brasil −15% | -0,05% | USD -0,5 mil |
| Commodities −15% | -0,04% | USD -0,4 mil |
| Gap Brasil −10% | -0,03% | USD -0,3 mil |
| Gap México −13% | -0,03% | USD -0,3 mil |
| Gap Peru −10% | 0,00% | USD 0,00 mm |
| Gap Colômbia −11% | 0,00% | USD 0,0 mil |
| Mercado da América Latina −20% | +0,01% | USD +0,1 mil |
| Gap Brasil +10% | +0,03% | USD +0,3 mil |
| Eleição Brasil out/2022 (2º turno) | +0,04% | USD +0,4 mil |
| México −15% | +0,12% | USD +1,2 mil |
| Estresse de juros nos EUA jun/2022 | +0,23% | USD +2,4 mil |
| Gap Argentina −56% | +0,28% | USD +2,8 mil |
| Colapso do fator momentum −3σ | +0,29% | USD +2,9 mil |
| Choque fiscal BRL dez/2024 | +0,82% | USD +8,3 mil |
| Crise da covid (fev-mar/2020) | n/d | n/d |
| Estallido social Chile (out-nov/2019) | n/d | n/d |
| Joesley Day (mai/2017) | n/d | n/d |
| PASO Argentina 2019 | n/d | n/d |
| Taper tantrum (mai-jun/2013) | n/d | n/d |

### Maiores contribuições fatoriais (fração da variância)

| Fator | Contribuição |
|---|---|
| Estilo — Momentum | 0,64% |
| Estilo — Liquidez | 0,46% |
| Estilo — Vol residual | 0,40% |
| Setor — Tecnologia | 0,37% |
| Setor — Consumo discricionário | 0,30% |
| Estilo — Tamanho (size) | 0,18% |
| País — Argentina | 0,16% |
| Setor — Saúde | 0,15% |
| Setor — Utilidades públicas | 0,14% |
| País — Regional (América Latina) | 0,13% |

### Maiores contribuições de risco por empresa (fração da variância)

| Empresa | Contribuição |
|---|---|
| Sigma Lithium | 7,63% |
| Grupo Aeroméxico | 7,47% |
| Tenda | 4,69% |
| Usiminas | 4,13% |
| Riachuelo (ex-Guararapes) | 3,98% |
| Lithium Argentina | 3,87% |
| Banco Pine | 3,33% |
| Brava Energia | 3,13% |
| Embraer | 2,75% |
| PRIO | 2,73% |

## Controles do mandato

101 controles; 0 fora do limite (0 obrigatórios, 0 de alerta).

| Resultado | Tipo | Controle | Valor | Limite | Detalhe |
|---|---|---|---|---|---|
| dentro | obrigatório | Beta previsto | -0,0003 | 0,0500 | Beta previsto 0,000 (limite ±0,050). |
| dentro | obrigatório | Taxa de aluguel das posições vendidas | 0,0171 | 0,0500 | Taxas de aluguel dentro do limite de 5,00% a.a. |
| dentro | obrigatório | Exposição líquida por país (Argentina) | -0,0050 | 0,0200 | Líquido no país Argentina: −0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Brasil) | 0,0034 | 0,0200 | Líquido no país Brasil: 0,34% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Chile) | 0,0050 | 0,0200 | Líquido no país Chile: 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Colômbia) | -0,0003 | 0,0200 | Líquido no país Colômbia: −0,03% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Regional (América Latina)) | -0,0050 | 0,0200 | Líquido no país Regional (América Latina): −0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (México) | 0,0023 | 0,0200 | Líquido no país México: 0,23% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Panamá) | 0,0000 | 0,0200 | Líquido no país Panamá: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Peru) | 0,0000 | 0,0200 | Líquido no país Peru: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Uruguai) | 0,0000 | 0,0200 | Líquido no país Uruguai: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Defasagem dos dados de mercado | 0,0000 | 4,0000 | Dados de mercado de 16/10/2026 para a semana de 16/10/2026: 0 dias corridos (máximo 4). |
| dentro | obrigatório | Stop de drawdown (corte da exposição bruta) | -0,0001 | -0,0500 | Drawdown −0,01% (stop −5,00%, zeragem −7,50%). |
| dentro | obrigatório | Exposição bruta máxima | 0,6751 | 2,5000 | Exposição bruta 0,68x do PL (máximo 2,50x). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo de decisão) | 0,9512 | 0,8500 | Fatia idiossincrática 95,12% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo base) | 0,9191 | 0,8500 | Fatia idiossincrática 91,91% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Prazo de liquidação das posições compradas | 0,2171 | 3,0000 | Máximo de 0,22 fechamentos à capacidade estrutural do leilão (limite 3,0). |
| dentro | obrigatório | Prazo de liquidação das posições vendidas | 0,0762 | 2,0000 | Máximo de 0,08 fechamentos à capacidade estrutural do leilão (limite 2,0). |
| dentro | obrigatório | Compra só em nomes elegíveis e sem veto | 0,0000 | 0,0000 | Todas as compras são permitidas. |
| dentro | obrigatório | Peso máximo por nome (posição comprada) | 0,0253 | 0,0400 | Nenhuma posição comprada acima do teto por nome. |
| dentro | obrigatório | Peso máximo por nome (posição vendida) | 0,0125 | 0,0250 | Nenhuma posição vendida acima do teto por nome. |
| dentro | obrigatório | Exposição líquida | 0,0004 | 0,0100 | Líquido 0,04% do PL (limite ±1,00%); comprado 33,78%, vendido −33,74%. |
| dentro | obrigatório | Cobertura do modelo de risco | 0,0000 | 0,0000 | Todos os nomes com peso têm risco modelado. |
| dentro | obrigatório | Exposição líquida por setor (comunicações) | -0,0034 | 0,0250 | Líquido no setor Comunicações: −0,34% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo discricionário) | 0,0150 | 0,0250 | Líquido no setor Consumo discricionário: 1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo básico) | -0,0004 | 0,0250 | Líquido no setor Consumo básico: −0,04% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (energia) | -0,0017 | 0,0250 | Líquido no setor Energia: −0,17% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (financeiro) | 0,0150 | 0,0250 | Líquido no setor Financeiro: 1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (saúde) | -0,0091 | 0,0250 | Líquido no setor Saúde: −0,91% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (industriais) | -0,0054 | 0,0250 | Líquido no setor Industriais: −0,54% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (tecnologia) | 0,0068 | 0,0250 | Líquido no setor Tecnologia: 0,68% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (materiais) | 0,0059 | 0,0250 | Líquido no setor Materiais: 0,59% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (imobiliário) | -0,0073 | 0,0250 | Líquido no setor Imobiliário: −0,73% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (utilidades públicas) | -0,0150 | 0,0250 | Líquido no setor Utilidades públicas: −1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Sem nova venda a descoberto em nome vetado | 0,0000 | 0,0000 | Nenhuma venda a descoberto nova ou aumentada em nome com resultado próximo ou free float baixo. |
| dentro | obrigatório | Venda a descoberto só em linhas alugáveis e sem veto | 0,0000 | 0,0000 | Todas as posições vendidas são alugáveis e sem veto. |
| dentro | obrigatório | Sem posição vendida com risco alto de squeeze | 0,0000 | 0,0000 | Nenhuma posição vendida em nome com risco de squeeze alto. |
| dentro | obrigatório | Teto da posição vendida com risco médio de squeeze | 0,0000 | 0,0125 | Posições vendidas com risco de squeeze médio ou sem dado dentro do teto de 1,25%. |
| dentro | obrigatório | Exposição ao estilo (beta de mercado) | -0,0005 | 0,1000 | Exposição líquida −0,001 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (sensibilidade cambial) | 0,0274 | 0,1000 | Exposição líquida +0,027 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (liquidez) | -0,0481 | 0,1000 | Exposição líquida −0,048 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (momentum) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (vol residual) | 0,0406 | 0,1000 | Exposição líquida +0,041 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (tamanho (size)) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (valor (value)) | -0,0349 | 0,1000 | Exposição líquida −0,035 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição líquida ao tema (estatais) | -0,0100 | 0,0100 | Líquido −1,00% no tema estatais (limite ±1,00%). |
| dentro | obrigatório | Volatilidade ex-ante máxima | 0,0352 | 0,0700 | Volatilidade ex-ante 3,52% a.a. (teto da banda 7,00%). |
| dentro | obrigatório | Pesos numéricos válidos | 0,0000 | 0,0000 | Todos os pesos são finitos. |
| dentro | alerta | Beta previsto (limite operacional) | -0,0003 | 0,0200 | Beta previsto 0,000 (limite operacional ±0,020). |
| dentro | alerta | Sensibilidade a commodity (cobre) | 0,0000 | 0,0300 | Σ w·β = 0,0000 (limite ±0,03); 10% na commodity ⇒ 0,00% do PL. |
| dentro | alerta | Sensibilidade a commodity (ouro) | -0,0018 | 0,0300 | Σ w·β = −0,0018 (limite ±0,03); 10% na commodity ⇒ −0,02% do PL. |
| dentro | alerta | Sensibilidade a commodity (petróleo) | -0,0022 | 0,0300 | Σ w·β = −0,0022 (limite ±0,03); 10% na commodity ⇒ −0,02% do PL. |
| dentro | alerta | Sensibilidade a commodity, limite operacional (cobre) | 0,0000 | 0,0100 | Σ w·β = 0,0000 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (ouro) | -0,0018 | 0,0100 | Σ w·β = −0,0018 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (petróleo) | -0,0022 | 0,0100 | Σ w·β = −0,0022 (limite operacional ±0,010). |
| dentro | alerta | Perda em gap de país | -0,0020 | -0,0150 | Pior cenário: Gap AR +41% com −0,20% do PL (limite −1,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Argentina) | -0,0050 | 0,0050 | Líquido no país Argentina: −0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Brasil) | 0,0034 | 0,0100 | Líquido no país Brasil: 0,34% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Chile) | 0,0050 | 0,0050 | Líquido no país Chile: 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Colômbia) | -0,0003 | 0,0050 | Líquido no país Colômbia: −0,03% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Regional (América Latina)) | -0,0050 | 0,0050 | Líquido no país Regional (América Latina): −0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (México) | 0,0023 | 0,0100 | Líquido no país México: 0,23% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Panamá) | 0,0000 | 0,0050 | Líquido no país Panamá: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Peru) | 0,0000 | 0,0050 | Líquido no país Peru: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Uruguai) | 0,0000 | 0,0050 | Líquido no país Uruguai: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Nível de revisão do drawdown | -0,0001 | -0,0250 | Drawdown −0,01% (gatilho de revisão −2,50%). |
| dentro | alerta | Exposição ao choque de evento | -0,0009 | 0,0015 | Reação residual ao choque do evento replicada na carteira: −0,089% do PL (limite ±0,15%). |
| dentro | alerta | Parcela fatorial do risco | 0,0488 | 0,1000 | Risco fatorial = 4,88% da variância com inflação de 2ª ordem κ_F = 1,45 no bloco fatorial (limite 10,00%); o restante é específico (alpha puro). |
| dentro | alerta | Exposição bruta mínima | 0,6751 | 0,5000 | Exposição bruta 0,68x do PL (mínimo recomendado 0,50x). |
| dentro | alerta | Meta da fatia idiossincrática (modelo de decisão) | 0,9512 | 0,9000 | Fatia idiossincrática 95,12% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Meta da fatia idiossincrática (modelo base) | 0,9191 | 0,9000 | Fatia idiossincrática 91,91% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0000 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 0,00% (teto 2,50%) somando CSN Siderúrgica Nacional, CSN Mineração: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0093 | 0,0400 | Comprado 0,93% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Metalúrgica Gerdau, Gerdau: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0026 | 0,0400 | Comprado 0,26% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Itaúsa, Itaú Unibanco: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0104 | 0,0400 | Comprado 1,04% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Bradespar, Vale: holding e controlada contam como um só nome. |
| dentro | alerta | Exposição líquida por setor, limite operacional (comunicações) | -0,0034 | 0,0150 | Líquido no setor Comunicações: −0,34% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo discricionário) | 0,0150 | 0,0150 | Líquido no setor Consumo discricionário: 1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo básico) | -0,0004 | 0,0150 | Líquido no setor Consumo básico: −0,04% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (energia) | -0,0017 | 0,0150 | Líquido no setor Energia: −0,17% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (financeiro) | 0,0150 | 0,0150 | Líquido no setor Financeiro: 1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (saúde) | -0,0091 | 0,0150 | Líquido no setor Saúde: −0,91% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (industriais) | -0,0054 | 0,0150 | Líquido no setor Industriais: −0,54% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (tecnologia) | 0,0068 | 0,0150 | Líquido no setor Tecnologia: 0,68% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (materiais) | 0,0059 | 0,0150 | Líquido no setor Materiais: 0,59% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (imobiliário) | -0,0073 | 0,0150 | Líquido no setor Imobiliário: −0,73% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (utilidades públicas) | -0,0150 | 0,0150 | Líquido no setor Utilidades públicas: −1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Contribuição máxima de um nome ao risco | 0,0763 | 0,0800 | Maior contribuição: Sigma Lithium com 7,63% da variância (limite 8,00%). |
| dentro | alerta | Exposição ao estilo, limite operacional (beta de mercado) | -0,0005 | 0,0500 | Exposição líquida −0,001 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (sensibilidade cambial) | 0,0274 | 0,0500 | Exposição líquida +0,027 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (liquidez) | -0,0481 | 0,0500 | Exposição líquida −0,048 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (momentum) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (vol residual) | 0,0406 | 0,0500 | Exposição líquida +0,041 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (tamanho (size)) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (valor (value)) | -0,0349 | 0,0500 | Exposição líquida −0,035 (limite operacional ±0,05). |
| dentro | alerta | Ordens dentro da capacidade do fechamento | 0,0000 | 0,0000 | Toda abertura ou aumento cabe na capacidade do leilão e da janela pré-fechamento. |
| dentro | alerta | Giro semanal | 0,3000 | 0,3000 | Giro Σ\|Δw\| = 30,00% do PL (limite 30,00%). |
| dentro | alerta | Volatilidade ex-ante mínima | 0,0352 | 0,0300 | Volatilidade ex-ante 3,52% a.a. (piso da banda 3,00%). |
| na meta | indicador | Emissores sem fechamento negociável | 0,0000 | n/d | Nenhum emissor congelado. |
| na meta | indicador | Dados dos vetos de venda a descoberto | 18,0000 | n/d | 18 emissores sem data de resultado ou free float conhecidos (sem data: sinalizado, sem veto; sem free float em nome pequeno: vetado). Participação máxima do controlador sem fonte pública estruturada: não avaliada. |
| na meta | indicador | Origem dos dados | 0,0000 | n/d | Dados reais de snapshot imutável (hash verificado). |
| na meta | indicador | Distância à meta de volatilidade | 0,0352 | 0,0364 | Volatilidade ex-ante 3,52% contra a meta 3,64% (diferença −0,11 p.p.). |

## Principais posições

### 10 maiores posições compradas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Grupo Aeroméxico | México | Industriais | +2,53% | USD 25,4 mil | AERO (ADR) | 0,5% | baixo (26) | +0,96 |
| 2 | PRIO | Brasil | Energia | +1,61% | USD 16,1 mil | PRIO3.SA (local) | 0,0% | baixo (13) | +0,43 |
| 3 | Riachuelo (ex-Guararapes) | Brasil | Consumo discricionário | +1,25% | USD 12,6 mil | RIAA3.SA (local) | 0,4% | alto (70) | +2,16 |
| 4 | Genomma Lab | México | Consumo básico | +1,25% | USD 12,6 mil | LABB.MX (local) | 0,5% | n/d (46) | +1,79 |
| 5 | Tenda | Brasil | Consumo discricionário | +1,25% | USD 12,6 mil | TEND3.SA (local) | 0,1% | baixo (26) | +2,30 |
| 6 | Petrobras | Brasil | Energia | +1,25% | USD 12,6 mil | PBR (ADR) | 0,0% | baixo (21) | +2,52 |
| 7 | PagSeguro Digital | Brasil | Financeiro | +1,25% | USD 12,6 mil | PAGS (listada nos EUA) | 0,0% | baixo (38) | +0,60 |
| 8 | Suzano | Brasil | Materiais | +1,25% | USD 12,6 mil | SUZB3.SA (local) | 0,0% | baixo (15) | -0,02 |
| 9 | SQM | Chile | Materiais | +1,25% | USD 12,6 mil | SQM (ADR) | 0,0% | baixo (10) | +1,17 |
| 10 | ISA Energia Brasil | Brasil | Utilidades públicas | +1,25% | USD 12,6 mil | ISAE4.SA (local) | 0,1% | baixo (39) | +1,08 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **Grupo Aeroméxico**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que conexões, fidelidade e diferenciação comercial sustentem receita suficiente para remunerar a frota ao longo do ciclo. A condição decisiva é caixa atribuível após manutenção, expansão, arrendamentos e financiamento. Ocupação e oferta premium precisam produzir retorno econômico, sem depender de liquidez contratada ou antecipação de passagens. A classificação atual é Em revisão, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
- **PRIO**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão pré-trade da nota publicada em 2026-10-11. A hipótese é que integração das instalações, novos poços e revitalização reduzam custo econômico e elevem caixa por ação depois de manutenção, dívida e reposição de reservas. A condição decisiva é produção comercial sustentada com retorno suficiente do capital empregado. Vazão inicial, aquisição e custo unitário de extração não comprovam rentabilidade completa nem eliminam risco de paradas e preço do petróleo. A evidência não sustenta inclinação fundamental adicional; as divergências entre seleção e avaliação são tratadas como incerteza, sem inferir arbitragem ou convergência garantida.
- **Riachuelo (ex-Guararapes)**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que integração industrial, coleção e canais sustentem preço cheio, produtividade e crédito rentável. A condição decisiva é obter caixa depois de juros, aluguel, tecnologia e expansão. Lucro crescente não confirma a tese quando a carteira e investimentos absorvem recursos; venda de ativos e pagamentos de proventos precisam manter estados próprios. A classificação atual é Em revisão, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
- **Genomma Lab**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que inovação e distribuição produzam demanda rentável depois de promoção, fabricação e capital de giro. A condição decisiva é converter a venda ao consumidor em recebimento recorrente, sem financiar persistentemente o canal. Expansão de marcas e fábrica precisa elevar retorno do capital, além da melhora financeira do lucro. A classificação atual é Neutro, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
- **Tenda**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que padronização e disciplina das safras sustentem margem e caixa depois de custos completos, perdas e financiamento. A condição decisiva é demonstrar retorno recorrente na Tenda sem extrapolar economias de entrega, enquanto Alea estabiliza execução dentro do capital disponível. A redução do crédito direto pode proteger qualidade da venda, mas também altera preço nominal e conversão. Recuperação de lucro exige controle de recebíveis, provisões e obrigações; geração gerencial beneficiada por derivativos não demonstra sozinha caixa estrutural. A classificação atual é Compra, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
- **Petrobras**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que produção do pré-sal e eficiência industrial sustentem retorno por ação depois de reposição de reservas, expansão, arrendamentos e dívida. A condição decisiva é caixa atribuível com disciplina de capital ao longo do ciclo do petróleo. Maior produção e distribuição declarada não resolvem sozinhas os riscos de precificação doméstica, intervenção do controlador e projetos com retorno ainda não demonstrado. A classificação atual é Em revisão, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
- **PagSeguro Digital**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que pagamentos e relacionamento bancário ampliem contribuição por cliente depois de captação, risco e custo de servir. A condição decisiva é uso retido com retorno após perdas e financiamento. Volume de pagamentos, novas contas ou expansão do crédito não comprovam monetização nem vantagem econômica sustentável. A classificação atual é Compra, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
- **Suzano**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que produtividade florestal, escala industrial e disciplina comercial sustentem caixa por ação ao longo do ciclo. A condição decisiva é retorno depois de manutenção, terras, logística, proteção financeira e investimento. Diversificação em bens de consumo pode reduzir a dependência da celulose, mas precisa remunerar preço de aquisição e integração; capacidade maior e EBITDA ajustado não demonstram, isoladamente, criação de valor. A classificação atual é Neutro, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
- **SQM**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese exige caixa atribuível em condições conservadoras de preço, após royalties, tributos, manutenção e capital. Diversificação mineral só reduz risco se remunera o investimento. Recursos, expansão e direitos de exploração não equivalem a caixa certo: licenças, tecnologia e participação econômica precisam sustentar a produção futura. A classificação atual é Neutro, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
- **ISA Energia Brasil**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que novos projetos e reforços gerem recebimentos com retorno suficiente depois de capital, dívida e emissão de ações. A condição decisiva é expansão econômica atribuível por ação, preservando disponibilidade. Construção e remuneração financeira do ativo contratual não comprovam crescimento equivalente de caixa livre; componentes com prazo determinado não foram perpetuados. A classificação atual é Compra, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.

### 10 maiores posições vendidas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Patria Investments | Brasil | Financeiro | -1,25% | USD -12,6 mil | PAX (listada nos EUA) | 0,1% | baixo (36) | -2,35 |
| 2 | Auren Energia | Brasil | Utilidades públicas | -1,25% | USD -12,6 mil | AURE3.SA (local) | 0,1% | baixo (33) | -3,00 |
| 3 | Lithium Argentina | Argentina | Materiais | -1,25% | USD -12,6 mil | LAR (listada nos EUA) | 0,1% | baixo (24) | -0,62 |
| 4 | Ultrapar | Brasil | Energia | -1,25% | USD -12,6 mil | UGPA3.SA (local) | 0,0% | baixo (10) | -0,14 |
| 5 | Brava Energia | Brasil | Energia | -1,25% | USD -12,6 mil | BRAV3.SA (local) | 0,1% | baixo (31) | -0,89 |
| 6 | Cemex | México | Materiais | -1,25% | USD -12,6 mil | CX (ADR) | 0,0% | baixo (10) | -0,58 |
| 7 | Usiminas | Brasil | Materiais | -1,25% | USD -12,6 mil | USIM5.SA (local) | 0,1% | baixo (25) | -0,56 |
| 8 | Embraer | Brasil | Industriais | -1,25% | USD -12,6 mil | EMBJ (ADR) | 0,0% | baixo (4) | -0,61 |
| 9 | FEMSA | México | Consumo básico | -1,25% | USD -12,6 mil | FMX (ADR) | 0,0% | baixo (16) | +0,65 |
| 10 | Fleury | Brasil | Saúde | -1,25% | USD -12,6 mil | FLRY3.SA (local) | 0,1% | baixo (34) | +0,50 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **Patria Investments**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que capacidade de investimento e relacionamento sustentem taxas recorrentes. A condição é converter essa proposta em caixa da gestora depois de custos, compromissos próprios e diluição, sem depender de realização de performance ainda incerta. A classificação atual é Compra, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **Auren Energia**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-12. A hipótese é que portfólio e contratação reduzam o custo de atender clientes e gerem caixa recorrente após investimento e financiamento. A condição decisiva é margem realizada, com proteção e geração compatíveis com as obrigações. Receita maior, marcação de contratos e dividendos declarados por investidas não comprovam recuperação equivalente de caixa. A classificação atual é Neutro, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **Lithium Argentina**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que produtividade e disciplina de capital permitam gerar caixa atribuível em um ciclo de preços adverso, preservando capacidade de financiar desenvolvimento. A expansão é uma opção condicionada: retorno exige engenharia, licenças, financiamento e recuperação industrial comprovados, sem diluição que absorva o benefício. A classificação atual é Em revisão, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **Ultrapar**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que qualidade do fornecimento, eficiência comercial e infraestrutura remunerem capital depois de manutenção, bonificações, financiamento e giro. A condição decisiva é caixa atribuível à holding e ao acionista, com retorno comparável por negócio. Margens favorecidas pela conjuntura não foram extrapoladas como permanentes. Diversificação pode ampliar fontes de resultado, mas exige disciplina de aquisições e projetos, sem confundir EBITDA consolidado com recurso livre para distribuição. A classificação atual é Neutro, com confiança A. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **Brava Energia**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que confiabilidade dos campos, novos poços e integração industrial sustentem caixa depois de proteção financeira, manutenção e obrigações de aquisição. A condição decisiva é margem realizada com capital suficiente e transmissão ao minoritário sob o novo controle. Aumento de EBITDA, capacidade e preço do petróleo não demonstra melhora uniforme da produção, rentabilidade por barril ou liquidez livre. A classificação atual é Neutro, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **Cemex**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que eficiência recorrente e disciplina de preço possam sustentar caixa através do ciclo. A condição decisiva é comprovar economias persistentes depois de manutenção, tributos e reinvestimento; recuperação cíclica isolada não basta. A classificação atual é Neutro, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **Usiminas**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que confiabilidade industrial, eficiência energética e mix sustentem caixa depois de manutenção e capital de giro. A condição decisiva é recuperação econômica demonstrada ao longo do ciclo, sem depender de indenização, venda de ativos ou proteção comercial permanente. A conclusão do projeto de injeção de carvão pode reduzir custo, mas ganho técnico precisa aparecer em produção, margem e retorno após investimento. A classificação atual é Neutro, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **Embraer**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que carteira e serviços sustentem entregas com retorno depois de desenvolvimento e financiamento. A condição decisiva é converter pedidos em margem e caixa recorrente, preservando qualidade e suporte. Adiantamentos de clientes e crédito tributário extraordinário não devem representar permanentemente a geração normal. A classificação atual é Venda, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **FEMSA**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que disciplina de expansão e melhoria operacional por negócio sustentem caixa atribuível depois de investimento, contratos de uso e financiamento. A condição decisiva é retorno recebido pela controladora, sem duplicar valor de participações. Escala de lojas, bebidas e usuários digitais não comprova eficiência nem retorno incremental das novas iniciativas. A classificação atual é Neutro, com confiança C. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.
- **Fleury**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão da nota publicada em 2026-10-11. A hipótese é que marcas, rede técnica e integração ampliem utilização e margem com reinvestimento disciplinado. A condição decisiva é transformar crescimento orgânico e adquirido em caixa depois de juros, arrendamentos e aquisição. A melhora do resultado consolidado precisa ser atribuível ao acionista e sustentar retorno econômico, sem confundir entrada de novos ativos com produtividade recorrente. A classificação atual é Venda, com confiança B. Sem comprovação adicional de retorno residual, mantenho abstenção direcional; a seleção quantitativa permanece sujeita aos controles de risco.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Cautela por reconfirmação incompleta de controle, free float, aluguel e calendário; o escore não substitui disponibilidade efetiva nem autoriza ignorar o gate de eventos.

## Exposições

### Por país (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Chile | 1,94% | -1,44% | +0,50% | 3,38% | ±2,00% |
| Regional (América Latina) | 1,25% | -1,75% | -0,50% | 3,00% | ±2,00% |
| Argentina | 3,13% | -3,63% | -0,50% | 6,75% | ±2,00% |
| Brasil | 22,57% | -22,23% | +0,34% | 44,80% | ±2,00% |
| México | 4,09% | -3,85% | +0,23% | 7,94% | ±2,00% |
| Colômbia | 0,81% | -0,84% | -0,03% | 1,64% | ±2,00% |

### Por setor (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Utilidades públicas | 4,47% | -5,97% | -1,50% | 10,44% | ±2,50% |
| Financeiro | 6,69% | -5,19% | +1,50% | 11,87% | ±2,50% |
| Consumo discricionário | 3,66% | -2,16% | +1,50% | 5,82% | ±2,50% |
| Saúde | 1,25% | -2,16% | -0,91% | 3,41% | ±2,50% |
| Imobiliário | 0,39% | -1,11% | -0,73% | 1,50% | ±2,50% |
| Tecnologia | 0,68% | 0,00% | +0,68% | 0,68% | ±2,50% |
| Materiais | 5,72% | -5,13% | +0,59% | 10,85% | ±2,50% |
| Industriais | 3,67% | -4,21% | -0,54% | 7,88% | ±2,50% |
| Comunicações | 0,31% | -0,65% | -0,34% | 0,95% | ±2,50% |
| Energia | 4,60% | -4,78% | -0,17% | 9,38% | ±2,50% |
| Consumo básico | 2,35% | -2,39% | -0,04% | 4,74% | ±2,50% |

### Fatores de estilo (σ × PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Momentum | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Tamanho (size) | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Liquidez | 0,000 | 0,000 | -0,048 | 0,048 | ±0,100 |
| Vol residual | 0,000 | 0,000 | +0,041 | 0,041 | ±0,100 |
| Valor (value) | 0,000 | 0,000 | -0,035 | 0,035 | ±0,100 |
| Sensibilidade cambial | 0,000 | 0,000 | +0,027 | 0,027 | ±0,100 |
| Beta de mercado | 0,000 | 0,000 | -0,001 | 0,001 | ±0,100 |

## Hedges cambiais sugeridos

| Moeda | Exposição | Hedge | Instrumento | Racional |
|---|---|---|---|---|
| ARS | USD -5,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em ARS: -0,50% do PL (USD -5.019), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| BRL | USD +3,4 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em BRL: +0,34% do PL (USD 3.390), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 161.334, shorts USD 165.310; excedente líquido em BRL ≈ USD 3.976 (garantias/conversão). |
| CLP | USD +5,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em CLP: +0,50% do PL (USD 5.020), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| COP | USD -0,3 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em COP: -0,03% do PL (USD -304), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| MXN | USD +2,3 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em MXN: +0,23% do PL (USD 2.330), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 12.551, shorts USD 0; necessidade líquida de comprar MXN à vista ≈ USD 12.551. |

## Ordens

| Item | Valor |
|---|---|
| Nº de ordens | 78 (compra 21, recompra 18, venda 19, venda a descoberto 20) |
| Volume bruto negociado | USD 313,0 mil (31,17% do PL) |
| Giro (Σ\|Δw\|) | 31,17% |
| Custo estimado | USD 536 (17,1 bps do volume; 0,053% do PL) |
| Maior % do volume médio diário | 0,7% |
| Maior prazo estimado de execução | 0,2 fech. |
| Ordens na B3 com perna no fracionário (sufixo F) | 39 de 39 |
| Ordens na BMV com perna em pico (abaixo do lote que forma preço) | 1 de 1 |
| Maior erro do arredondamento a ações inteiras | +0,046% do PL (MELI); soma 0,088% |

## Pesquisa e visões

Autoria: pesquisa da gestão; 228 notas por empresa (228 com apoio de IA), 7 notas macro, 103 visões.

11 manchetes consideradas — conteúdo NÃO confiável, não reproduzido neste memo.

### Notas macro

#### AR — regime: estabilização sob incerteza (viés +0)
_(pesquisa da gestão (IA))_

> O relatório institucional do BCRA do segundo trimestre descreve controle dos agregados e normalização financeira. São diretrizes, sem garantia de resultado. Inflação, câmbio, remessas e financiamento exigem bases comparáveis e avaliação do caixa atribuível.

Riscos:
- Diferenças entre câmbio implícito e oficial, inflação e acesso ao caixa.

Implicações para a carteira:
- Postura defensiva, neutralização de exposições e abstenção de inclinação agregada sem evidência adicional.

#### BR — regime: cautela e evento eleitoral (viés +0)
_(pesquisa da gestão (IA))_

> A ata do Copom de 2026-09-16 relata moderação gradual da atividade e inflação ainda acima da meta. A janela eleitoral está ativa na avaliação de risco. Priorizo neutralidade e disciplina de caixa; não atribuo causalidade a movimentos isolados de preço.

Riscos:
- Risco fiscal, cambial e eleitoral; efeitos heterogêneos entre emissores.

Implicações para a carteira:
- Postura defensiva, neutralização de exposições e abstenção de inclinação agregada sem evidência adicional.

Eventos:
- Eleição brasileira prevista na janela de evento do mandato. (25/10/2026; incerto)

#### CL — regime: decisões dependentes dos dados (viés +0)
_(pesquisa da gestão (IA))_

> O IPoM de setembro do Banco Central do Chile mantém avaliação das decisões conforme a evolução dos cenários. A reunião seguinte consta do calendário institucional. A incerteza de demanda, energia e câmbio recomenda evitar extrapolação de margens.

Riscos:
- Custos, consumo e financiamento dos investimentos.

Implicações para a carteira:
- Postura defensiva, neutralização de exposições e abstenção de inclinação agregada sem evidência adicional.

Eventos:
- Reunião de política monetária no calendário institucional. (27/10/2026; incerto)

#### CO — regime: aperto monetário (viés +0)
_(pesquisa da gestão (IA))_

> As minutas publicadas pelo Banco da República em 2026-10-05 apontam aumento da taxa diante de inflação e expectativas pressionadas. A leitura reforça cautela com crédito e custo de capital, sem atribuir retorno agregado ao país.

Riscos:
- Inflação, risco fiscal e depreciação cambial.

Implicações para a carteira:
- Postura defensiva, neutralização de exposições e abstenção de inclinação agregada sem evidência adicional.

#### GLOBAL — regime: juros restritivos (viés +0)
_(pesquisa da gestão (IA))_

> O comunicado do Federal Reserve de 2026-09-16 descreve atividade resiliente e inflação elevada, com aperto monetário. Julgo que a incerteza de juros, dólar e commodities favorece postura defensiva; isso não constitui previsão direcional de retorno regional.

Riscos:
- Inflação persistente e volatilidade das condições financeiras.

Implicações para a carteira:
- Postura defensiva, neutralização de exposições e abstenção de inclinação agregada sem evidência adicional.

#### MX — regime: prudência monetária (viés +0)
_(pesquisa da gestão (IA))_

> O anúncio do Banco de México de 2026-09-24 registra manutenção da taxa. A próxima divulgação de inflação indicada na agenda requer acompanhamento. A leitura favorece seleção por retorno do capital, sem aposta agregada no país.

Riscos:
- Inflação, comércio externo e demanda dependente das condições financeiras.

Implicações para a carteira:
- Postura defensiva, neutralização de exposições e abstenção de inclinação agregada sem evidência adicional.

Eventos:
- Divulgação da inflação da primeira quinzena pelo INEGI, conforme calendário público da agenda. (22/10/2026; incerto)

#### PE — regime: confirmação documental incompleta (viés +0)
_(pesquisa da gestão (IA))_

> A confirmação integral do programa monetário recente e do calendário oficial permanece incompleta nesta revisão. O material institucional encontrado não sustenta uma classificação nova de regime. Abstenho-me de inferir mudança de taxa e mantenho avaliação por emissor.

Riscos:
- Lacuna documental, política local e sensibilidade a metais.

Implicações para a carteira:
- Postura defensiva, neutralização de exposições e abstenção de inclinação agregada sem evidência adicional.

### Visões aplicadas

| Empresa | Origem | Visão | Confiança | Restrições | Autoria |
|---|---|---|---|---|---|
| Adecoagro | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| BBVA Argentina | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Corporación América Airports | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Central Puerto | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Cresud | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| IRSA | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Lithium Argentina | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco Macro | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Pampa Energía | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Supervielle | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Transportadora de Gas del Sur | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| YPF | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Allos | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Alpargatas | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Alupar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Ambev | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Aura Minerals | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Auren Energia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Axia Energia (ex-Eletrobras) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banrisul | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| BB Seguridade | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Bemobi | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco Bradesco | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Braskem | pesquisa (IA) | 0 | 100% | sem venda, sem compra | pesquisa da gestão |
| Brava Energia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Companhia Brasileira de Alumínio | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Cemig | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Copasa | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Copel | pesquisa (IA) | 0 | 100% | sem compra | pesquisa da gestão |
| Cosan | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Cury | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Caixa Seguridade | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Embraer | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Energisa | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Engie Brasil Energia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Equatorial | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| EZTec | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Fleury | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Gerdau | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| GPS Participações | pesquisa (IA) | 0 | 100% | sem venda, \|peso\| ≤ 1,25% | pesquisa da gestão |
| Hypera | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Inter&Co | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| ISA Energia Brasil | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Itaú Unibanco | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| JBS N.V. | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Klabin | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Locaweb (LWSA) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Magazine Luiza | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Marcopolo | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Movida | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Nu Holdings | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Orizon | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| PagSeguro Digital | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Patria Investments | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Petrobras | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Petz-Cobasi | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| PicPay (PicS N.V.) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco Pine | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Porto Seguro | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Randoncorp | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Rede D'Or São Luiz | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Riachuelo (ex-Guararapes) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Rumo | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Sabesp | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Sanepar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco Santander Brasil | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| São Martinho | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Sigma Lithium | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Simpar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Smart Fit | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| StoneCo | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Suzano | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Tenda | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Tupy | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Ultrapar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Unipar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Usiminas | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Vale | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Vibra Energia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| VTEX | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco de Chile | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco Santander-Chile | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Enel Chile | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| LATAM Airlines Group | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| SQM | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Cibest (ex-Bancolombia) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| GeoPark | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Arcos Dorados | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| dLocal | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Fortuna Mining | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Liberty Latin America | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| MercadoLibre | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Millicom (Tigo) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Aeroméxico | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| América Móvil | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Aeroportuario del Sureste | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Cemex | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| FEMSA | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Genomma Lab | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Aeroportuario Centro Norte | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Vista Energy | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Volaris | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Hudbay Minerals | pesquisa (IA) | 0 | 100% | sem compra | pesquisa da gestão |

## Otimizador

| Item | Valor |
|---|---|
| Situação / solver | ótimo / CLARABEL |
| Tempo de solução | 6,38 s |
| Alpha esperado (a.a.) | 2,29% |
| Custo esperado (a.a.) | 0,43% |
| Candidatos | 216 |
| Excluídos | bloqueio free float: 5, bloqueio resultado: 5, bloqueio resultado estimado: 2, sem linha short: 70, squeeze alto: 38, squeeze medio teto: 9, squeeze na teto: 44, visao no long: 3, visao no short: 10, visao teto peso: 93 |
| Restrições ativas | setor: Consumo discricionário, setor: Financeiro, setor: Utilidades públicas, estilo: Tamanho (size), estilo: Momentum, país (limite operacional): Chile, país (limite operacional): Regional (América Latina), tema: estatais, participação do país: Argentina, turnover, teto vendido: Lithium Argentina, teto vendido: Auren Energia, teto comprado: Axia Energia (ex-Eletrobras), teto comprado: BB Seguridade, teto vendido: Brava Energia, teto vendido: Embraer, teto vendido: Energisa, teto vendido: Equatorial, teto vendido: Fleury, teto comprado: Hypera, teto comprado: ISA Energia Brasil, teto vendido: Nu Holdings, teto vendido: Orizon, teto comprado: PagSeguro Digital, teto vendido: Patria Investments, teto comprado: Petrobras, teto comprado: Riachuelo (ex-Guararapes), teto vendido: Sigma Lithium, teto comprado: Suzano, teto comprado: Tenda, teto vendido: Ultrapar, teto vendido: Usiminas, teto comprado: SQM, teto comprado: Fortuna Mining, teto comprado: Grupo Aeroméxico, teto vendido: Grupo Aeroportuario del Sureste, teto vendido: Cemex, teto vendido: FEMSA, teto comprado: Genomma Lab |

Observações do otimizador:
- Meta de vol ajustada pelo gestor: 3,64% (mandato 5,00%).
- Exposição bruta máxima efetivo: 2,00x (definido pelo gestor).
- Modo 'match': meta de vol não atingida com a aversão a risco dividida por até 64 (limite da busca); divisor usado 64,00.
- Teto de risco fatorial na carteira atingida (fatia fatorial máxima 10%): 1 passo(s); fatia idiossincrática: modelo de decisão 95,1%, modelo base 91,9%.
- Passadas de otimização: 3.
- Perna comprada 33,78%, vendida 33,74%; custo pontual 4,9 bps do PL; aluguel 11,2 bps a.a.
- Bloco macro no modelo de risco: petróleo Brent, cobre, ouro, índice do dólar (DXY) (0 emissores com beta pela média do setor).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (×1,50 na vol de BR)
- Fallback 1: apenas restrições da IA/PM (sem inclinações).
- [visões] IC das visões de IA = 0,01 (fase S1, teto 0,03).
- [visões] Cresud: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Alpargatas: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Banco Bradesco: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Braskem: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Companhia Brasileira de Alumínio: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Copel: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] GPS Participações: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Inter&Co: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] GeoPark: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] LA_DLOCAL: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Grupo Aeroméxico: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Hudbay Minerals: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Adecoagro: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] BBVA Argentina: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Corporación América Airports: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Central Puerto: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cresud: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] IRSA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Lithium Argentina: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Macro: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Pampa Energía: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Supervielle: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Transportadora de Gas del Sur: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] YPF: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Allos: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Alpargatas: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Alupar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Ambev: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Aura Minerals: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Auren Energia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Axia Energia (ex-Eletrobras): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banrisul: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] BB Seguridade: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Bemobi: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Bradesco: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Braskem: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Brava Energia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Companhia Brasileira de Alumínio: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cemig: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Copasa: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Copel: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cosan: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cury: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Caixa Seguridade: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Embraer: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Energisa: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Engie Brasil Energia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
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
- [visões] Locaweb (LWSA): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Magazine Luiza: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Marcopolo: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Movida: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Nu Holdings: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Orizon: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] PagSeguro Digital: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Patria Investments: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Petrobras: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Petz-Cobasi: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] PicPay (PicS N.V.): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Pine: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Porto Seguro: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
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
- [visões] Tupy: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Ultrapar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Unipar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Usiminas: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Vale: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Vibra Energia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] VTEX: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco de Chile: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco Santander-Chile: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Enel Chile: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LATAM Airlines Group: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] SQM: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Cibest (ex-Bancolombia): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] GeoPark: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_ARCOS: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_DLOCAL: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_FORTUNA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_LILA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_MELI: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_MILLICOM: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Aeroméxico: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] América Móvil: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Aeroportuario del Sureste: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cemex: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] FEMSA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Genomma Lab: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Aeroportuario Centro Norte: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Vista Energy: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Volaris: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Hudbay Minerals: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Braskem: visões proíbem compra e venda — posição limitada a zero.
- [visões] Após as visões: Ortogonalização WLS (pesos 1/σ²): 0,0% da variância ponderada do alpha bruto era explicada por fatores e foi removida.
- [risco por nome] passo 1: Grupo Aeroméxico com 9,39% da variância (limite 8,00%); teto max_long reduzido para 2,53%
- [risco por nome] passo 1: Sigma Lithium com 8,11% da variância (limite 8,00%); teto max_short reduzido para 0,96%

## Decisões pendentes do gestor

- [ ] Confirmar a disponibilidade de aluguel para as 35 posições vendidas antes da execução.
- [ ] Revisar 228 notas da pesquisa com apoio de IA.
- [ ] Validar 103 restrições propostas pela pesquisa (sem venda / sem compra / teto de peso).
- [ ] Decidir sobre os hedges cambiais sugeridos: ARS, BRL, CLP, COP, MXN.
- [ ] Revisar observações/relaxamentos do otimizador.
- [ ] Obter co-assinatura independente de Risco/Compliance (quatro olhos): Volatilidade ex-ante 3,52% fora de [4,00%, 6,00%].
- [ ] Aprovar ou rejeitar com justificativa — a decisão fica vinculada aos hashes dos dados de mercado, do mandato, da pesquisa e da proposta.

---

_Todos os números deste memo foram calculados e formatados por código a partir da proposta; textos de pesquisa são citados como fornecidos e rotulados pela origem._

---

_Hash da proposta (SHA-256): `6356883ad3cf2f36bc8bfc8da0b427be4311c8ce883e5b756f16420c0eeee270`_
