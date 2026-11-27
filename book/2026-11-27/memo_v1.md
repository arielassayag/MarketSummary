# CDP — Cabra da Peste — Proposta da semana de 27/11/2026 (v1)

> Dados de mercado: retrato `store-2026-10-02+39-2026-11-26`. Dados reais (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética.

| Campo | Valor |
|---|---|
| Estado | **EM REVISÃO** |
| Proposta | CDP-2026-11-27-cdp-restricoes (versão 1) |
| Criada em / por | 27/11/2026 12:05 (Brasília) — CDP — motor quantitativo |
| PL de referência | USD 988,7 mil |
| Retrato dos dados de mercado | store-2026-10-02+39-2026-11-26 — `a0d028d9a56b` |
| Hash do mandato | `2ddf7d89ac76` |
| Hash da pesquisa | `1b81530894bd` |

## Resumo de risco

| Métrica | Valor | Referência |
|---|---|---|
| Vol ex-ante (a.a.) | 3,64% | meta aplicada 3,64% (mandato 5,00%); banda 3,00%–7,00% — dentro da banda |
| Vol fatorial (a.a.) | 0,65% | 4,51% da variância com κ_F no modelo de decisão (limite 10,00%) |
| Vol específica (a.a.) | 3,58% | fonte pretendida do retorno (alpha puro) |
| Beta previsto | 0,001 | limite ±0,050 |
| Exposição bruta (% do PL) | 93,80% | faixa 50%–250% |
| Exposição líquida (% do PL) | +0,77% | limite ±1,00% |
| Comprado / vendido (% do PL) | 47,28% / -46,51% |  |
| Nº de posições compradas / vendidas | 45 / 47 |  |
| VaR 1d 99% | 0,53% (USD 5,3 mil) | paramétrico/histórico (modelo de risco) |
| ES 1d 99% | 0,68% (USD 6,7 mil) |  |
| VaR 1 semana 99% | 1,19% (USD 11,8 mil) |  |
| N efetivo | 67,0 | diversificação (1/Σw² normalizado) |
| Máx. fechamentos para liquidar | 0,3 fech. | long ≤ 3,0 fech.; short ≤ 2,0 fech. |
| % do gross liquidável em 1 fechamento | 100,00% | capacidade estrutural do leilão e da janela pré-fechamento |
| Fatia idiossincrática — modelo de decisão | 95,49% | meta 90%; piso 85% (com janelas de evento) |
| Fatia idiossincrática — modelo base | 95,49% | meta 90%; piso 85% (sem janelas de evento) |
| Inflação de 2ª ordem do risco fatorial (κ_F) | 1,45 | aplicada à variância fatorial na medida idiossincrática |

### Decomposição da variância ex-ante por grupo (modelo de decisão, κ_F no bloco fatorial)

| Grupo | Fração da variância |
|---|---|
| Mercado | 0,08% |
| País | 0,02% |
| Setor | 1,25% |
| Estilo | 2,19% |
| Macro (commodities e dólar) | 0,98% |
| Específico (idiossincrático) | 95,49% |

### Testes de estresse (resultado estimado)

| Cenário | % do PL | US$ |
|---|---|---|
| Squeeze: 5 maiores posições vendidas +30% | -3,52% | USD -34,8 mil |
| Quebra: 5 maiores posições compradas −30% | -3,51% | USD -34,7 mil |
| Eleição México jun/2024 | -0,89% | USD -8,8 mil |
| Choque fiscal BRL dez/2024 | -0,15% | USD -1,5 mil |
| Commodities −15% | -0,10% | USD -1,0 mil |
| Estresse de juros nos EUA jun/2022 | -0,06% | USD -0,6 mil |
| Gap México −13% | -0,06% | USD -0,6 mil |
| Gap Brasil −10% | -0,04% | USD -0,4 mil |
| Brasil −15% | -0,04% | USD -0,4 mil |
| Gap Argentina +41% | -0,03% | USD -0,3 mil |
| Mercado da América Latina −20% | -0,02% | USD -0,2 mil |
| Gap Peru −10% | -0,01% | USD -0,1 mil |
| Gap Colômbia −11% | 0,00% | USD 0,00 mm |
| Gap Chile −15% | 0,00% | USD 0,0 mil |
| Gap Brasil +10% | +0,04% | USD +0,4 mil |
| Gap Argentina −56% | +0,05% | USD +0,4 mil |
| México −15% | +0,10% | USD +1,0 mil |
| Colapso do fator momentum −3σ | +0,23% | USD +2,2 mil |
| Tarifas dos EUA (abr/2025) | +0,30% | USD +2,9 mil |
| Eleição Brasil out/2022 (2º turno) | +0,90% | USD +8,9 mil |
| Crise da covid (fev-mar/2020) | n/d | n/d |
| Estallido social Chile (out-nov/2019) | n/d | n/d |
| Joesley Day (mai/2017) | n/d | n/d |
| PASO Argentina 2019 | n/d | n/d |
| Taper tantrum (mai-jun/2013) | n/d | n/d |

### Maiores contribuições fatoriais (fração da variância)

| Fator | Contribuição |
|---|---|
| Estilo — Vol residual | 0,71% |
| Estilo — Momentum | 0,46% |
| Macro — ouro | 0,31% |
| Setor — Saúde | 0,30% |
| Macro — petróleo Brent | 0,24% |
| Estilo — Valor (value) | 0,17% |
| Setor — Utilidades públicas | 0,17% |
| Setor — Tecnologia | 0,16% |
| Setor — Imobiliário | 0,15% |
| Estilo — Tamanho (size) | 0,10% |

### Maiores contribuições de risco por empresa (fração da variância)

| Empresa | Contribuição |
|---|---|
| Liberty Latin America | 7,69% |
| Tenda | 6,25% |
| PagSeguro Digital | 5,28% |
| PicPay (PicS N.V.) | 5,22% |
| Fleury | 4,81% |
| Patria Investments | 4,16% |
| Aura Minerals | 4,06% |
| Grupo Aeroméxico | 3,69% |
| Auren Energia | 3,19% |
| Genomma Lab | 2,64% |

## Controles do mandato

100 controles; 0 fora do limite (0 obrigatórios, 0 de alerta).

| Resultado | Tipo | Controle | Valor | Limite | Detalhe |
|---|---|---|---|---|---|
| dentro | obrigatório | Beta previsto | 0,0010 | 0,0500 | Beta previsto +0,001 (limite ±0,050). |
| dentro | obrigatório | Taxa de aluguel das posições vendidas | 0,0089 | 0,0500 | Taxas de aluguel dentro do limite de 5,00% a.a. |
| dentro | obrigatório | Exposição líquida por país (Argentina) | -0,0008 | 0,0200 | Líquido no país Argentina: −0,08% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Brasil) | 0,0042 | 0,0200 | Líquido no país Brasil: 0,42% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Chile) | -0,0003 | 0,0200 | Líquido no país Chile: −0,03% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Colômbia) | 0,0000 | 0,0200 | Líquido no país Colômbia: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Regional (América Latina)) | -0,0012 | 0,0200 | Líquido no país Regional (América Latina): −0,12% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (México) | 0,0049 | 0,0200 | Líquido no país México: 0,49% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Panamá) | 0,0050 | 0,0200 | Líquido no país Panamá: 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Peru) | 0,0009 | 0,0200 | Líquido no país Peru: 0,09% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Uruguai) | -0,0050 | 0,0200 | Líquido no país Uruguai: −0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Defasagem dos dados de mercado | 0,0000 | 4,0000 | Dados de mercado de 27/11/2026 para a semana de 27/11/2026: 0 dias corridos (máximo 4). |
| dentro | obrigatório | Stop de drawdown (corte da exposição bruta) | -0,0207 | -0,0500 | Drawdown −2,07% (stop −5,00%, zeragem −7,50%). |
| dentro | obrigatório | Exposição bruta máxima | 0,9380 | 2,5000 | Exposição bruta 0,94x do PL (máximo 2,50x). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo de decisão) | 0,9549 | 0,8500 | Fatia idiossincrática 95,49% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo base) | 0,9549 | 0,8500 | Fatia idiossincrática 95,49% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Prazo de liquidação das posições compradas | 0,2521 | 3,0000 | Máximo de 0,25 fechamentos à capacidade estrutural do leilão (limite 3,0). |
| dentro | obrigatório | Prazo de liquidação das posições vendidas | 0,1076 | 2,0000 | Máximo de 0,11 fechamentos à capacidade estrutural do leilão (limite 2,0). |
| dentro | obrigatório | Compra só em nomes elegíveis e sem veto | 0,0000 | 0,0000 | Todas as compras são permitidas. |
| dentro | obrigatório | Peso máximo por nome (posição comprada) | 0,0265 | 0,0400 | Nenhuma posição comprada acima do teto por nome. |
| dentro | obrigatório | Peso máximo por nome (posição vendida) | 0,0250 | 0,0250 | Nenhuma posição vendida acima do teto por nome. |
| dentro | obrigatório | Exposição líquida | 0,0077 | 0,0100 | Líquido 0,77% do PL (limite ±1,00%); comprado 47,28%, vendido −46,51%. |
| dentro | obrigatório | Cobertura do modelo de risco | 0,0000 | 0,0000 | Todos os nomes com peso têm risco modelado. |
| dentro | obrigatório | Exposição líquida por setor (comunicações) | -0,0008 | 0,0250 | Líquido no setor Comunicações: −0,08% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo discricionário) | 0,0066 | 0,0250 | Líquido no setor Consumo discricionário: 0,66% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo básico) | 0,0150 | 0,0250 | Líquido no setor Consumo básico: 1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (energia) | -0,0025 | 0,0250 | Líquido no setor Energia: −0,25% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (financeiro) | -0,0061 | 0,0250 | Líquido no setor Financeiro: −0,61% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (saúde) | -0,0122 | 0,0250 | Líquido no setor Saúde: −1,22% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (industriais) | 0,0036 | 0,0250 | Líquido no setor Industriais: 0,36% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (tecnologia) | 0,0057 | 0,0250 | Líquido no setor Tecnologia: 0,57% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (materiais) | 0,0032 | 0,0250 | Líquido no setor Materiais: 0,32% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (imobiliário) | 0,0102 | 0,0250 | Líquido no setor Imobiliário: 1,02% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (utilidades públicas) | -0,0150 | 0,0250 | Líquido no setor Utilidades públicas: −1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Sem nova venda a descoberto em nome vetado | 0,0000 | 0,0000 | Nenhuma venda a descoberto nova ou aumentada em nome com resultado próximo ou free float baixo. |
| dentro | obrigatório | Venda a descoberto só em linhas alugáveis e sem veto | 0,0000 | 0,0000 | Todas as posições vendidas são alugáveis e sem veto. |
| dentro | obrigatório | Sem posição vendida com risco alto de squeeze | 0,0000 | 0,0000 | Nenhuma posição vendida em nome com risco de squeeze alto. |
| dentro | obrigatório | Teto da posição vendida com risco médio de squeeze | 0,0050 | 0,0125 | Posições vendidas com risco de squeeze médio ou sem dado dentro do teto de 1,25%. |
| dentro | obrigatório | Exposição ao estilo (beta de mercado) | -0,0044 | 0,1000 | Exposição líquida −0,004 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (sensibilidade cambial) | 0,0042 | 0,1000 | Exposição líquida +0,004 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (liquidez) | -0,0180 | 0,1000 | Exposição líquida −0,018 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (momentum) | -0,0451 | 0,1000 | Exposição líquida −0,045 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (vol residual) | 0,0500 | 0,1000 | Exposição líquida +0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (tamanho (size)) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (valor (value)) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição líquida ao tema (estatais) | 0,0100 | 0,0100 | Líquido 1,00% no tema estatais (limite ±1,00%). |
| dentro | obrigatório | Volatilidade ex-ante máxima | 0,0364 | 0,0700 | Volatilidade ex-ante 3,64% a.a. (teto da banda 7,00%). |
| dentro | obrigatório | Pesos numéricos válidos | 0,0000 | 0,0000 | Todos os pesos são finitos. |
| dentro | alerta | Beta previsto (limite operacional) | 0,0010 | 0,0200 | Beta previsto +0,001 (limite operacional ±0,020). |
| dentro | alerta | Sensibilidade a commodity (cobre) | 0,0100 | 0,0300 | Σ w·β = +0,0100 (limite ±0,03); 10% na commodity ⇒ +0,10% do PL. |
| dentro | alerta | Sensibilidade a commodity (ouro) | 0,0002 | 0,0300 | Σ w·β = +0,0002 (limite ±0,03); 10% na commodity ⇒ +0,00% do PL. |
| dentro | alerta | Sensibilidade a commodity (petróleo) | 0,0012 | 0,0300 | Σ w·β = +0,0012 (limite ±0,03); 10% na commodity ⇒ +0,01% do PL. |
| dentro | alerta | Sensibilidade a commodity, limite operacional (cobre) | 0,0100 | 0,0100 | Σ w·β = +0,0100 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (ouro) | 0,0002 | 0,0100 | Σ w·β = +0,0002 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (petróleo) | 0,0012 | 0,0100 | Σ w·β = +0,0012 (limite operacional ±0,010). |
| dentro | alerta | Perda em gap de país | -0,0006 | -0,0150 | Pior cenário: Gap MX −13% com −0,06% do PL (limite −1,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Argentina) | -0,0008 | 0,0050 | Líquido no país Argentina: −0,08% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Brasil) | 0,0042 | 0,0100 | Líquido no país Brasil: 0,42% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Chile) | -0,0003 | 0,0050 | Líquido no país Chile: −0,03% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Colômbia) | 0,0000 | 0,0050 | Líquido no país Colômbia: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Regional (América Latina)) | -0,0012 | 0,0050 | Líquido no país Regional (América Latina): −0,12% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (México) | 0,0049 | 0,0100 | Líquido no país México: 0,49% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Panamá) | 0,0050 | 0,0050 | Líquido no país Panamá: 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Peru) | 0,0009 | 0,0050 | Líquido no país Peru: 0,09% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Uruguai) | -0,0050 | 0,0050 | Líquido no país Uruguai: −0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Nível de revisão do drawdown | -0,0207 | -0,0250 | Drawdown −2,07% (gatilho de revisão −2,50%). |
| dentro | alerta | Parcela fatorial do risco | 0,0451 | 0,1000 | Risco fatorial = 4,51% da variância com inflação de 2ª ordem κ_F = 1,45 no bloco fatorial (limite 10,00%); o restante é específico (alpha puro). |
| dentro | alerta | Exposição bruta mínima | 0,9380 | 0,5000 | Exposição bruta 0,94x do PL (mínimo recomendado 0,50x). |
| dentro | alerta | Meta da fatia idiossincrática (modelo de decisão) | 0,9549 | 0,9000 | Fatia idiossincrática 95,49% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Meta da fatia idiossincrática (modelo base) | 0,9549 | 0,9000 | Fatia idiossincrática 95,49% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0000 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 0,00% (teto 2,50%) somando CSN Siderúrgica Nacional, CSN Mineração: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0036 | 0,0400 | Comprado 0,36% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Metalúrgica Gerdau, Gerdau: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0032 | 0,0400 | Comprado 0,32% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Itaúsa, Itaú Unibanco: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0196 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 1,96% (teto 2,50%) somando Bradespar, Vale: holding e controlada contam como um só nome. |
| dentro | alerta | Exposição líquida por setor, limite operacional (comunicações) | -0,0008 | 0,0150 | Líquido no setor Comunicações: −0,08% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo discricionário) | 0,0066 | 0,0150 | Líquido no setor Consumo discricionário: 0,66% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo básico) | 0,0150 | 0,0150 | Líquido no setor Consumo básico: 1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (energia) | -0,0025 | 0,0150 | Líquido no setor Energia: −0,25% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (financeiro) | -0,0061 | 0,0150 | Líquido no setor Financeiro: −0,61% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (saúde) | -0,0122 | 0,0150 | Líquido no setor Saúde: −1,22% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (industriais) | 0,0036 | 0,0150 | Líquido no setor Industriais: 0,36% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (tecnologia) | 0,0057 | 0,0150 | Líquido no setor Tecnologia: 0,57% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (materiais) | 0,0032 | 0,0150 | Líquido no setor Materiais: 0,32% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (imobiliário) | 0,0102 | 0,0150 | Líquido no setor Imobiliário: 1,02% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (utilidades públicas) | -0,0150 | 0,0150 | Líquido no setor Utilidades públicas: −1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Contribuição máxima de um nome ao risco | 0,0769 | 0,0800 | Maior contribuição: LA_LILA com 7,69% da variância (limite 8,00%). |
| dentro | alerta | Exposição ao estilo, limite operacional (beta de mercado) | -0,0044 | 0,0500 | Exposição líquida −0,004 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (sensibilidade cambial) | 0,0042 | 0,0500 | Exposição líquida +0,004 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (liquidez) | -0,0180 | 0,0500 | Exposição líquida −0,018 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (momentum) | -0,0451 | 0,0500 | Exposição líquida −0,045 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (vol residual) | 0,0500 | 0,0500 | Exposição líquida +0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (tamanho (size)) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (valor (value)) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Ordens dentro da capacidade do fechamento | 0,0000 | 0,0000 | Toda abertura ou aumento cabe na capacidade do leilão e da janela pré-fechamento. |
| dentro | alerta | Giro semanal | 0,2198 | 0,3000 | Giro Σ\|Δw\| = 21,98% do PL (limite 30,00%). |
| dentro | alerta | Volatilidade ex-ante mínima | 0,0364 | 0,0300 | Volatilidade ex-ante 3,64% a.a. (piso da banda 3,00%). |
| na meta | indicador | Emissores sem fechamento negociável | 0,0000 | n/d | Nenhum emissor congelado. |
| na meta | indicador | Dados dos vetos de venda a descoberto | 32,0000 | n/d | 32 emissores sem data de resultado ou free float conhecidos (sem data: sinalizado, sem veto; sem free float em nome pequeno: vetado). Participação máxima do controlador sem fonte pública estruturada: não avaliada. |
| na meta | indicador | Origem dos dados | 0,0000 | n/d | Dados reais de snapshot imutável (hash verificado). |
| na meta | indicador | Distância à meta de volatilidade | 0,0364 | 0,0364 | Volatilidade ex-ante 3,64% contra a meta 3,64% (diferença 0,00 p.p.). |

## Principais posições

### 10 maiores posições compradas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | PagSeguro Digital | Brasil | Financeiro | +2,65% | USD 26,2 mil | PAGS (listada nos EUA) | 0,1% | médio (43) | +0,54 |
| 2 | Axia Energia (ex-Eletrobras) | Brasil | Utilidades públicas | +2,57% | USD 25,4 mil | AXIA3.SA (local) | 0,0% | baixo (7) | +0,06 |
| 3 | BB Seguridade | Brasil | Financeiro | +2,28% | USD 22,5 mil | BBSE3.SA (local) | 0,0% | baixo (33) | +1,53 |
| 4 | Petrobras | Brasil | Energia | +2,17% | USD 21,5 mil | PBR (ADR) | 0,0% | baixo (19) | +2,74 |
| 5 | Suzano | Brasil | Materiais | +2,02% | USD 20,0 mil | SUZB3.SA (local) | 0,0% | baixo (22) | -0,28 |
| 6 | Porto Seguro | Brasil | Financeiro | +1,97% | USD 19,5 mil | PSSA3.SA (local) | 0,1% | baixo (15) | +0,84 |
| 7 | Tenda | Brasil | Consumo discricionário | +1,89% | USD 18,7 mil | TEND3.SA (local) | 0,1% | baixo (28) | +1,45 |
| 8 | Millicom (Tigo) | Regional (América Latina) | Comunicações | +1,76% | USD 17,4 mil | TIGO (listada nos EUA) | 0,0% | baixo (14) | +0,87 |
| 9 | Fortuna Mining | Regional (América Latina) | Materiais | +1,76% | USD 17,4 mil | FSM (listada nos EUA) | 0,0% | baixo (22) | +0,59 |
| 10 | Genomma Lab | México | Consumo básico | +1,68% | USD 16,6 mil | LABB.MX (local) | 0,6% | n/d (27) | +1,48 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **PagSeguro Digital**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > PagSeguro: a leitura da nota de 2026-10-11 mantém o teste de contribuição após captação, perdas e capital. A notícia corrente de movimento pré-mercado não confirma melhora econômica. Abstenção enquanto a ponte de resultados não for reconciliada integralmente.
- _Sem nota de pesquisa:_ Axia Energia (ex-Eletrobras), BB Seguridade, Petrobras, Suzano, Porto Seguro, Tenda, Millicom (Tigo), Fortuna Mining, Genomma Lab

### 10 maiores posições vendidas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Auren Energia | Brasil | Utilidades públicas | -2,50% | USD -24,7 mil | AURE3.SA (local) | 0,2% | baixo (28) | -2,15 |
| 2 | Liberty Latin America | Regional (América Latina) | Comunicações | -2,50% | USD -24,7 mil | LILAK (listada nos EUA) | 0,2% | baixo (28) | -1,83 |
| 3 | Fleury | Brasil | Saúde | -2,50% | USD -24,7 mil | FLRY3.SA (local) | 0,1% | baixo (29) | +0,37 |
| 4 | Patria Investments | Brasil | Financeiro | -2,44% | USD -24,1 mil | PAX (listada nos EUA) | 0,2% | baixo (33) | -1,93 |
| 5 | Cemex | México | Materiais | -1,78% | USD -17,6 mil | CX (ADR) | 0,0% | baixo (7) | -0,95 |
| 6 | Banco do Brasil | Brasil | Financeiro | -1,71% | USD -16,9 mil | BBAS3.SA (local) | 0,0% | baixo (26) | -0,47 |
| 7 | Aura Minerals | Brasil | Materiais | -1,67% | USD -16,5 mil | AUGO (listada nos EUA) | 0,0% | baixo (33) | +1,14 |
| 8 | Grupo Aeroportuario del Sureste | México | Industriais | -1,45% | USD -14,3 mil | ASR (ADR) | 0,1% | baixo (21) | -1,36 |
| 9 | Brava Energia | Brasil | Energia | -1,38% | USD -13,6 mil | BRAV3.SA (local) | 0,1% | baixo (27) | -0,63 |
| 10 | TIM Brasil | Brasil | Comunicações | -1,36% | USD -13,5 mil | TIMS3.SA (local) | 0,0% | baixo (16) | -0,45 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- _Sem nota de pesquisa:_ Auren Energia, Liberty Latin America, Fleury, Patria Investments, Cemex, Banco do Brasil, Aura Minerals, Grupo Aeroportuario del Sureste, Brava Energia, TIM Brasil

## Exposições

### Por país (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Panamá | 0,50% | 0,00% | +0,50% | 0,50% | ±2,00% |
| Uruguai | 0,00% | -0,50% | -0,50% | 0,50% | ±2,00% |
| México | 4,95% | -4,46% | +0,49% | 9,42% | ±2,00% |
| Brasil | 33,04% | -32,62% | +0,42% | 65,66% | ±2,00% |
| Regional (América Latina) | 3,51% | -3,63% | -0,12% | 7,14% | ±2,00% |
| Peru | 1,26% | -1,17% | +0,09% | 2,44% | ±2,00% |
| Argentina | 3,35% | -3,43% | -0,08% | 6,77% | ±2,00% |
| Chile | 0,67% | -0,70% | -0,03% | 1,37% | ±2,00% |

### Por setor (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Consumo básico | 2,89% | -1,39% | +1,50% | 4,27% | ±2,50% |
| Utilidades públicas | 5,91% | -7,41% | -1,50% | 13,32% | ±2,50% |
| Saúde | 2,04% | -3,26% | -1,22% | 5,29% | ±2,50% |
| Imobiliário | 1,02% | 0,00% | +1,02% | 1,02% | ±2,50% |
| Consumo discricionário | 4,35% | -3,70% | +0,66% | 8,05% | ±2,50% |
| Financeiro | 11,10% | -11,71% | -0,61% | 22,81% | ±2,50% |
| Tecnologia | 0,57% | 0,00% | +0,57% | 0,57% | ±2,50% |
| Industriais | 4,63% | -4,28% | +0,36% | 8,91% | ±2,50% |
| Materiais | 7,51% | -7,19% | +0,32% | 14,70% | ±2,50% |
| Energia | 2,89% | -3,14% | -0,25% | 6,02% | ±2,50% |
| Comunicações | 4,37% | -4,45% | -0,08% | 8,82% | ±2,50% |

### Fatores de estilo (σ × PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Vol residual | 0,000 | 0,000 | +0,050 | 0,050 | ±0,100 |
| Tamanho (size) | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Valor (value) | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Momentum | 0,000 | 0,000 | -0,045 | 0,045 | ±0,100 |
| Liquidez | 0,000 | 0,000 | -0,018 | 0,018 | ±0,100 |
| Beta de mercado | 0,000 | 0,000 | -0,004 | 0,004 | ±0,100 |
| Sensibilidade cambial | 0,000 | 0,000 | +0,004 | 0,004 | ±0,100 |

## Hedges cambiais sugeridos

| Moeda | Exposição | Hedge | Instrumento | Racional |
|---|---|---|---|---|
| ARS | USD -0,8 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em ARS: -0,08% do PL (USD -803), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| BRL | USD +4,1 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em BRL: +0,42% do PL (USD 4.145), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 241.420, shorts USD 241.933; excedente líquido em BRL ≈ USD 513 (garantias/conversão). |
| CLP | USD -0,3 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em CLP: -0,03% do PL (USD -254), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| MXN | USD +4,8 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em MXN: +0,49% do PL (USD 4.808), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 16.607, shorts USD 0; necessidade líquida de comprar MXN à vista ≈ USD 16.607. |
| PEN | USD +0,9 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em PEN: +0,09% do PL (USD 850), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |

## Ordens

| Item | Valor |
|---|---|
| Nº de ordens | 102 (compra 16, recompra 36, venda 34, venda a descoberto 16) |
| Volume bruto negociado | USD 258,9 mil (26,18% do PL) |
| Giro (Σ\|Δw\|) | 26,18% |
| Custo estimado | USD 431 (16,7 bps do volume; 0,044% do PL) |
| Maior % do volume médio diário | 0,1% |
| Maior prazo estimado de execução | 0,1 fech. |
| Ordens na B3 com perna no fracionário (sufixo F) | 53 de 54 |
| Ordens na BMV com perna em pico (abaixo do lote que forma preço) | 2 de 2 |
| Maior erro do arredondamento a ações inteiras | -0,042% do PL (MELI); soma 0,102% |

## Pesquisa e visões

Autoria: pesquisa da gestão; 16 notas por empresa (16 com apoio de IA), 7 notas macro, 12 visões.

4 manchetes consideradas — conteúdo NÃO confiável, não reproduzido neste memo.

### Notas macro

#### AR — regime: cautela (viés +0)
_(pesquisa da gestão (IA))_

> O informe monetário de outubro do BCRA descreve compras de divisas e esterilização de excedentes. Julgamento: avaliar transmissão a depósitos, crédito e lucro recorrente; não inferir estabilização definitiva ou retorno do acionista.

#### BR — regime: cautela (viés +0)
_(pesquisa da gestão (IA))_

> Copom manteve a taxa na reunião de novembro. A ata destaca incerteza externa e necessidade de perseverança na convergência da inflação. Julgamento: convicção baixa para direção de mercado; postura defensiva.

Riscos:
- Persistência inflacionária, risco fiscal e sensibilidade a juros.

#### CL — regime: cautela (viés +0)
_(pesquisa da gestão (IA))_

> O comunicado do Banco Central de Chile de 2026-10-27 manteve a taxa e destacou choques de energia e alimentos. Julgamento: risco de custo e atividade exige seleção relativa, sem aposta direcional adicional.

#### CO — regime: cautela (viés +0)
_(pesquisa da gestão (IA))_

> O relatório de outubro do Banco de la República descreve inflação pressionada e moderação da atividade, com incerteza fiscal e climática. Julgamento: postura defensiva e convicção baixa para direção de mercado.

#### GLOBAL — regime: cautela (viés +0)
_(pesquisa da gestão (IA))_

> As fontes oficiais consultadas apontam incerteza de inflação e política monetária. Julgamento: convicção baixa para direção global; preservar neutralidade e liquidez diante do fechamento antecipado indicado pela agenda.

Riscos:
- Energia, alimentos, câmbio e reversão da liquidez.

#### MX — regime: cautela (viés +0)
_(pesquisa da gestão (IA))_

> Banxico, em 2026-11-05, descreve redução pontual dos juros e manutenção prolongada como apoio à convergência da inflação. Julgamento: não extrapolar ciclo de cortes; convicção direcional baixa.

Riscos:
- Depreciação, política comercial e persistência da inflação.

#### PE — regime: abstencao (viés +0)
_(pesquisa da gestão (IA))_

> O documento primário do programa monetário de novembro não pôde ser consultado. A agenda preserva lacuna no calendário oficial; não se afirma taxa corrente nem ausência de evento. Abstenção direcional.

Riscos:
- Calendário monetário não reconciliado e sensibilidade a metais.

### Visões aplicadas

| Empresa | Origem | Visão | Confiança | Restrições | Autoria |
|---|---|---|---|---|---|
| Grupo Financiero Galicia | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Globant | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Assaí Atacadista | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Cosan | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| EZTec | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Itaú Unibanco | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Minerva | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| MRV Engenharia | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Smart Fit | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Tupy | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Vamos | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Volaris | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |

## Otimizador

| Item | Valor |
|---|---|
| Situação / solver | ótimo / CLARABEL |
| Tempo de solução | 3,36 s |
| Alpha esperado (a.a.) | 2,27% |
| Custo esperado (a.a.) | 0,35% |
| Candidatos | 231 |
| Excluídos | bloqueio free float: 7, bloqueio free float desconhecido: 1, bloqueio resultado: 1, bloqueio resultado estimado: 2, sem linha short: 83, squeeze alto: 30, squeeze medio teto: 10, squeeze na teto: 44, visao no long: 1, visao no short: 12 |
| Restrições ativas | meta de vol, setor: Consumo básico, setor: Utilidades públicas, estilo: Tamanho (size), estilo: Vol residual, estilo: Valor (value), país (limite operacional): Panamá, país (limite operacional): Uruguai, tema: estatais, tema: commodity:copper, participação do país: Brasil, teto vendido: Banco Macro, teto vendido: Auren Energia, teto vendido: Fleury, teto vendido: Liberty Latin America |

Observações do otimizador:
- Meta de vol ajustada pelo gestor: 3,64% (mandato 5,00%).
- Exposição bruta máxima efetivo: 2,00x (definido pelo gestor).
- Teto de risco fatorial na carteira atingida (fatia fatorial máxima 10%): 1 passo(s); fatia idiossincrática: modelo de decisão 95,5%, modelo base 95,5%.
- Passadas de otimização: 3.
- Reparo de complementaridade: 17 emissores tinham perna comprada e vendida simultâneas (custo subestimado) e foram re-otimizados com uma única perna.
- Perna comprada 47,28%, vendida 46,51%; custo pontual 3,5 bps do PL; aluguel 12,3 bps a.a.
- Bloco macro no modelo de risco: petróleo Brent, cobre, ouro, índice do dólar (DXY) (0 emissores com beta pela média do setor).
- Fallback 1: apenas restrições da IA/PM (sem inclinações).
- [visões] IC das visões de IA = 0,01 (fase S1, teto 0,03).
- [visões] Grupo Financiero Galicia: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Globant: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Assaí Atacadista: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Cosan: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] EZTec: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Itaú Unibanco: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Minerva: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] MRV Engenharia: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Smart Fit: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Tupy: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Vamos: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Volaris: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Grupo Financiero Galicia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Globant: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Assaí Atacadista: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cosan: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Ero Copper: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] EZTec: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Itaú Unibanco: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Minerva: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] MRV Engenharia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Smart Fit: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Tupy: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Vamos: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Volaris: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Após as visões: Ortogonalização WLS (pesos 1/σ²): 0,0% da variância ponderada do alpha bruto era explicada por fatores e foi removida.

## Decisões pendentes do gestor

- [ ] Validar posições vendidas com risco de squeeze médio ou alto: dLocal (médio).
- [ ] Confirmar a disponibilidade de aluguel para as 47 posições vendidas antes da execução.
- [ ] Revisar 16 notas da pesquisa com apoio de IA.
- [ ] Validar 12 restrições propostas pela pesquisa (sem venda / sem compra / teto de peso).
- [ ] Decidir sobre os hedges cambiais sugeridos: ARS, BRL, CLP, MXN, PEN.
- [ ] Revisar observações/relaxamentos do otimizador.
- [ ] Obter co-assinatura independente de Risco/Compliance (quatro olhos): Nova posição vendida com risco de squeeze: dLocal (médio). Volatilidade ex-ante 3,64% fora de [4,00%, 6,00%].
- [ ] Aprovar ou rejeitar com justificativa — a decisão fica vinculada aos hashes dos dados de mercado, do mandato, da pesquisa e da proposta.

---

_Todos os números deste memo foram calculados e formatados por código a partir da proposta; textos de pesquisa são citados como fornecidos e rotulados pela origem._

---

_Hash da proposta (SHA-256): `234af88c384cee3bbf341004378adb5dd5aed02f7a7cf5711512c1c1b434170f`_
