# CDP — Cabra da Peste — Proposta da semana de 13/11/2026 (v1)

> Dados de mercado: retrato `store-2026-10-02+29-2026-11-12`. Dados reais (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética.

| Campo | Valor |
|---|---|
| Estado | **EM REVISÃO** |
| Proposta | CDP-2026-11-13-cdp-restricoes (versão 1) |
| Criada em / por | 13/11/2026 11:15 (Brasília) — CDP — motor quantitativo |
| PL de referência | USD 1,01 mm |
| Retrato dos dados de mercado | store-2026-10-02+29-2026-11-12 — `375e1c799ba6` |
| Hash do mandato | `2ddf7d89ac76` |
| Hash da pesquisa | `123aa51eecab` |

## Resumo de risco

| Métrica | Valor | Referência |
|---|---|---|
| Vol ex-ante (a.a.) | 3,64% | meta aplicada 3,64% (mandato 5,00%); banda 3,00%–7,00% — dentro da banda |
| Vol fatorial (a.a.) | 0,71% | 5,43% da variância com κ_F no modelo de decisão (limite 10,00%) |
| Vol específica (a.a.) | 3,57% | fonte pretendida do retorno (alpha puro) |
| Beta previsto | 0,002 | limite ±0,050 |
| Exposição bruta (% do PL) | 90,39% | faixa 50%–250% |
| Exposição líquida (% do PL) | +0,68% | limite ±1,00% |
| Comprado / vendido (% do PL) | 45,53% / -44,86% |  |
| Nº de posições compradas / vendidas | 49 / 44 |  |
| VaR 1d 99% | 0,53% (USD 5,4 mil) | paramétrico/histórico (modelo de risco) |
| ES 1d 99% | 0,73% (USD 7,4 mil) |  |
| VaR 1 semana 99% | 1,19% (USD 12,0 mil) |  |
| N efetivo | 65,1 | diversificação (1/Σw² normalizado) |
| Máx. fechamentos para liquidar | 0,2 fech. | long ≤ 3,0 fech.; short ≤ 2,0 fech. |
| % do gross liquidável em 1 fechamento | 100,00% | capacidade estrutural do leilão e da janela pré-fechamento |
| Fatia idiossincrática — modelo de decisão | 94,57% | meta 90%; piso 85% (com janelas de evento) |
| Fatia idiossincrática — modelo base | 94,57% | meta 90%; piso 85% (sem janelas de evento) |
| Inflação de 2ª ordem do risco fatorial (κ_F) | 1,45 | aplicada à variância fatorial na medida idiossincrática |

### Decomposição da variância ex-ante por grupo (modelo de decisão, κ_F no bloco fatorial)

| Grupo | Fração da variância |
|---|---|
| Mercado | 0,10% |
| País | -0,09% |
| Setor | 0,92% |
| Estilo | 2,25% |
| Macro (commodities e dólar) | 2,24% |
| Específico (idiossincrático) | 94,57% |

### Testes de estresse (resultado estimado)

| Cenário | % do PL | US$ |
|---|---|---|
| Squeeze: 5 maiores posições vendidas +30% | -3,62% | USD -36,4 mil |
| Quebra: 5 maiores posições compradas −30% | -3,36% | USD -33,8 mil |
| Eleição México jun/2024 | -0,77% | USD -7,7 mil |
| Choque fiscal BRL dez/2024 | -0,32% | USD -3,2 mil |
| Commodities −15% | -0,14% | USD -1,4 mil |
| Gap México −13% | -0,10% | USD -1,0 mil |
| Brasil −15% | -0,06% | USD -0,6 mil |
| Gap Argentina +41% | -0,05% | USD -0,5 mil |
| Estresse de juros nos EUA jun/2022 | -0,05% | USD -0,5 mil |
| Mercado da América Latina −20% | -0,04% | USD -0,4 mil |
| Gap Peru −10% | -0,03% | USD -0,3 mil |
| Gap Brasil +10% | 0,00% | USD 0,0 mil |
| Gap Colômbia −11% | 0,00% | USD 0,00 mm |
| Gap Brasil −10% | 0,00% | USD 0,0 mil |
| Gap Chile −15% | +0,03% | USD +0,3 mil |
| Gap Argentina −56% | +0,07% | USD +0,7 mil |
| México −15% | +0,12% | USD +1,2 mil |
| Colapso do fator momentum −3σ | +0,23% | USD +2,3 mil |
| Tarifas dos EUA (abr/2025) | +0,31% | USD +3,2 mil |
| Eleição Brasil out/2022 (2º turno) | +0,42% | USD +4,2 mil |
| Crise da covid (fev-mar/2020) | n/d | n/d |
| Estallido social Chile (out-nov/2019) | n/d | n/d |
| Joesley Day (mai/2017) | n/d | n/d |
| PASO Argentina 2019 | n/d | n/d |
| Taper tantrum (mai-jun/2013) | n/d | n/d |

### Maiores contribuições fatoriais (fração da variância)

| Fator | Contribuição |
|---|---|
| Macro — ouro | 1,00% |
| Estilo — Vol residual | 0,56% |
| Estilo — Liquidez | 0,45% |
| Estilo — Momentum | 0,41% |
| Macro — petróleo Brent | 0,39% |
| Estilo — Tamanho (size) | 0,21% |
| Setor — Saúde | 0,20% |
| Setor — Tecnologia | 0,18% |
| Macro — cobre | 0,15% |
| Setor — Imobiliário | 0,11% |

### Maiores contribuições de risco por empresa (fração da variância)

| Empresa | Contribuição |
|---|---|
| Liberty Latin America | 7,92% |
| Tenda | 7,23% |
| PicPay (PicS N.V.) | 6,97% |
| PagSeguro Digital | 6,71% |
| Aura Minerals | 5,78% |
| Grupo Aeroméxico | 3,88% |
| Fleury | 3,53% |
| Patria Investments | 3,52% |
| Smart Fit | 3,03% |
| Auren Energia | 2,81% |

## Controles do mandato

100 controles; 0 fora do limite (0 obrigatórios, 0 de alerta).

| Resultado | Tipo | Controle | Valor | Limite | Detalhe |
|---|---|---|---|---|---|
| dentro | obrigatório | Beta previsto | 0,0019 | 0,0500 | Beta previsto +0,002 (limite ±0,050). |
| dentro | obrigatório | Taxa de aluguel das posições vendidas | 0,0300 | 0,0500 | Taxas de aluguel dentro do limite de 5,00% a.a. |
| dentro | obrigatório | Exposição líquida por país (Argentina) | -0,0013 | 0,0200 | Líquido no país Argentina: −0,13% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Brasil) | -0,0003 | 0,0200 | Líquido no país Brasil: −0,03% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Chile) | -0,0018 | 0,0200 | Líquido no país Chile: −0,18% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Colômbia) | 0,0000 | 0,0200 | Líquido no país Colômbia: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Regional (América Latina)) | -0,0001 | 0,0200 | Líquido no país Regional (América Latina): −0,01% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (México) | 0,0076 | 0,0200 | Líquido no país México: 0,76% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Panamá) | 0,0050 | 0,0200 | Líquido no país Panamá: 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Peru) | 0,0026 | 0,0200 | Líquido no país Peru: 0,26% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Uruguai) | -0,0050 | 0,0200 | Líquido no país Uruguai: −0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Defasagem dos dados de mercado | 0,0000 | 4,0000 | Dados de mercado de 13/11/2026 para a semana de 13/11/2026: 0 dias corridos (máximo 4). |
| dentro | obrigatório | Stop de drawdown (corte da exposição bruta) | -0,0029 | -0,0500 | Drawdown −0,29% (stop −5,00%, zeragem −7,50%). |
| dentro | obrigatório | Exposição bruta máxima | 0,9039 | 2,5000 | Exposição bruta 0,90x do PL (máximo 2,50x). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo de decisão) | 0,9457 | 0,8500 | Fatia idiossincrática 94,57% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo base) | 0,9457 | 0,8500 | Fatia idiossincrática 94,57% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Prazo de liquidação das posições compradas | 0,1717 | 3,0000 | Máximo de 0,17 fechamentos à capacidade estrutural do leilão (limite 3,0). |
| dentro | obrigatório | Prazo de liquidação das posições vendidas | 0,0825 | 2,0000 | Máximo de 0,08 fechamentos à capacidade estrutural do leilão (limite 2,0). |
| dentro | obrigatório | Compra só em nomes elegíveis e sem veto | 0,0000 | 0,0000 | Todas as compras são permitidas. |
| dentro | obrigatório | Peso máximo por nome (posição comprada) | 0,0302 | 0,0400 | Nenhuma posição comprada acima do teto por nome. |
| dentro | obrigatório | Peso máximo por nome (posição vendida) | 0,0250 | 0,0250 | Nenhuma posição vendida acima do teto por nome. |
| dentro | obrigatório | Exposição líquida | 0,0068 | 0,0100 | Líquido 0,68% do PL (limite ±1,00%); comprado 45,53%, vendido −44,86%. |
| dentro | obrigatório | Cobertura do modelo de risco | 0,0000 | 0,0000 | Todos os nomes com peso têm risco modelado. |
| dentro | obrigatório | Exposição líquida por setor (comunicações) | -0,0018 | 0,0250 | Líquido no setor Comunicações: −0,18% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo discricionário) | -0,0084 | 0,0250 | Líquido no setor Consumo discricionário: −0,84% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo básico) | 0,0053 | 0,0250 | Líquido no setor Consumo básico: 0,53% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (energia) | -0,0002 | 0,0250 | Líquido no setor Energia: −0,02% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (financeiro) | 0,0150 | 0,0250 | Líquido no setor Financeiro: 1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (saúde) | -0,0109 | 0,0250 | Líquido no setor Saúde: −1,09% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (industriais) | 0,0056 | 0,0250 | Líquido no setor Industriais: 0,56% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (tecnologia) | 0,0062 | 0,0250 | Líquido no setor Tecnologia: 0,62% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (materiais) | -0,0022 | 0,0250 | Líquido no setor Materiais: −0,22% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (imobiliário) | 0,0099 | 0,0250 | Líquido no setor Imobiliário: 0,99% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (utilidades públicas) | -0,0117 | 0,0250 | Líquido no setor Utilidades públicas: −1,17% do PL (limite ±2,50%). |
| dentro | obrigatório | Sem nova venda a descoberto em nome vetado | 0,0000 | 0,0000 | Nenhuma venda a descoberto nova ou aumentada em nome com resultado próximo ou free float baixo. |
| dentro | obrigatório | Venda a descoberto só em linhas alugáveis e sem veto | 0,0000 | 0,0000 | Todas as posições vendidas são alugáveis e sem veto. |
| dentro | obrigatório | Sem posição vendida com risco alto de squeeze | 0,0000 | 0,0000 | Nenhuma posição vendida em nome com risco de squeeze alto. |
| dentro | obrigatório | Teto da posição vendida com risco médio de squeeze | 0,0000 | 0,0125 | Posições vendidas com risco de squeeze médio ou sem dado dentro do teto de 1,25%. |
| dentro | obrigatório | Exposição ao estilo (beta de mercado) | 0,0015 | 0,1000 | Exposição líquida +0,002 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (sensibilidade cambial) | 0,0173 | 0,1000 | Exposição líquida +0,017 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (liquidez) | -0,0488 | 0,1000 | Exposição líquida −0,049 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (momentum) | -0,0387 | 0,1000 | Exposição líquida −0,039 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (vol residual) | 0,0500 | 0,1000 | Exposição líquida +0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (tamanho (size)) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (valor (value)) | -0,0300 | 0,1000 | Exposição líquida −0,030 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição líquida ao tema (estatais) | 0,0007 | 0,0100 | Líquido 0,07% no tema estatais (limite ±1,00%). |
| dentro | obrigatório | Volatilidade ex-ante máxima | 0,0364 | 0,0700 | Volatilidade ex-ante 3,64% a.a. (teto da banda 7,00%). |
| dentro | obrigatório | Pesos numéricos válidos | 0,0000 | 0,0000 | Todos os pesos são finitos. |
| dentro | alerta | Beta previsto (limite operacional) | 0,0019 | 0,0200 | Beta previsto +0,002 (limite operacional ±0,020). |
| dentro | alerta | Sensibilidade a commodity (cobre) | 0,0100 | 0,0300 | Σ w·β = +0,0100 (limite ±0,03); 10% na commodity ⇒ +0,10% do PL. |
| dentro | alerta | Sensibilidade a commodity (ouro) | -0,0057 | 0,0300 | Σ w·β = −0,0057 (limite ±0,03); 10% na commodity ⇒ −0,06% do PL. |
| dentro | alerta | Sensibilidade a commodity (petróleo) | 0,0025 | 0,0300 | Σ w·β = +0,0025 (limite ±0,03); 10% na commodity ⇒ +0,02% do PL. |
| dentro | alerta | Sensibilidade a commodity, limite operacional (cobre) | 0,0100 | 0,0100 | Σ w·β = +0,0100 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (ouro) | -0,0057 | 0,0100 | Σ w·β = −0,0057 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (petróleo) | 0,0025 | 0,0100 | Σ w·β = +0,0025 (limite operacional ±0,010). |
| dentro | alerta | Perda em gap de país | -0,0010 | -0,0150 | Pior cenário: Gap MX −13% com −0,10% do PL (limite −1,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Argentina) | -0,0013 | 0,0050 | Líquido no país Argentina: −0,13% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Brasil) | -0,0003 | 0,0100 | Líquido no país Brasil: −0,03% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Chile) | -0,0018 | 0,0050 | Líquido no país Chile: −0,18% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Colômbia) | 0,0000 | 0,0050 | Líquido no país Colômbia: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Regional (América Latina)) | -0,0001 | 0,0050 | Líquido no país Regional (América Latina): −0,01% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (México) | 0,0076 | 0,0100 | Líquido no país México: 0,76% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Panamá) | 0,0050 | 0,0050 | Líquido no país Panamá: 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Peru) | 0,0026 | 0,0050 | Líquido no país Peru: 0,26% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Uruguai) | -0,0050 | 0,0050 | Líquido no país Uruguai: −0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Nível de revisão do drawdown | -0,0029 | -0,0250 | Drawdown −0,29% (gatilho de revisão −2,50%). |
| dentro | alerta | Parcela fatorial do risco | 0,0543 | 0,1000 | Risco fatorial = 5,43% da variância com inflação de 2ª ordem κ_F = 1,45 no bloco fatorial (limite 10,00%); o restante é específico (alpha puro). |
| dentro | alerta | Exposição bruta mínima | 0,9039 | 0,5000 | Exposição bruta 0,90x do PL (mínimo recomendado 0,50x). |
| dentro | alerta | Meta da fatia idiossincrática (modelo de decisão) | 0,9457 | 0,9000 | Fatia idiossincrática 94,57% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Meta da fatia idiossincrática (modelo base) | 0,9457 | 0,9000 | Fatia idiossincrática 94,57% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0000 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 0,00% (teto 2,50%) somando CSN Siderúrgica Nacional, CSN Mineração: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0080 | 0,0400 | Comprado 0,80% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Metalúrgica Gerdau, Gerdau: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0020 | 0,0400 | Comprado 0,20% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Itaúsa, Itaú Unibanco: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0203 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 2,03% (teto 2,50%) somando Bradespar, Vale: holding e controlada contam como um só nome. |
| dentro | alerta | Exposição líquida por setor, limite operacional (comunicações) | -0,0018 | 0,0150 | Líquido no setor Comunicações: −0,18% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo discricionário) | -0,0084 | 0,0150 | Líquido no setor Consumo discricionário: −0,84% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo básico) | 0,0053 | 0,0150 | Líquido no setor Consumo básico: 0,53% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (energia) | -0,0002 | 0,0150 | Líquido no setor Energia: −0,02% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (financeiro) | 0,0150 | 0,0150 | Líquido no setor Financeiro: 1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (saúde) | -0,0109 | 0,0150 | Líquido no setor Saúde: −1,09% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (industriais) | 0,0056 | 0,0150 | Líquido no setor Industriais: 0,56% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (tecnologia) | 0,0062 | 0,0150 | Líquido no setor Tecnologia: 0,62% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (materiais) | -0,0022 | 0,0150 | Líquido no setor Materiais: −0,22% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (imobiliário) | 0,0099 | 0,0150 | Líquido no setor Imobiliário: 0,99% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (utilidades públicas) | -0,0117 | 0,0150 | Líquido no setor Utilidades públicas: −1,17% do PL (limite operacional ±1,50%). |
| dentro | alerta | Contribuição máxima de um nome ao risco | 0,0792 | 0,0800 | Maior contribuição: LA_LILA com 7,92% da variância (limite 8,00%). |
| dentro | alerta | Exposição ao estilo, limite operacional (beta de mercado) | 0,0015 | 0,0500 | Exposição líquida +0,002 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (sensibilidade cambial) | 0,0173 | 0,0500 | Exposição líquida +0,017 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (liquidez) | -0,0488 | 0,0500 | Exposição líquida −0,049 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (momentum) | -0,0387 | 0,0500 | Exposição líquida −0,039 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (vol residual) | 0,0500 | 0,0500 | Exposição líquida +0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (tamanho (size)) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (valor (value)) | -0,0300 | 0,0500 | Exposição líquida −0,030 (limite operacional ±0,05). |
| dentro | alerta | Ordens dentro da capacidade do fechamento | 0,0000 | 0,0000 | Toda abertura ou aumento cabe na capacidade do leilão e da janela pré-fechamento. |
| dentro | alerta | Giro semanal | 0,2257 | 0,3000 | Giro Σ\|Δw\| = 22,57% do PL (limite 30,00%). |
| dentro | alerta | Volatilidade ex-ante mínima | 0,0364 | 0,0300 | Volatilidade ex-ante 3,64% a.a. (piso da banda 3,00%). |
| na meta | indicador | Emissores sem fechamento negociável | 0,0000 | n/d | Nenhum emissor congelado. |
| na meta | indicador | Dados dos vetos de venda a descoberto | 26,0000 | n/d | 26 emissores sem data de resultado ou free float conhecidos (sem data: sinalizado, sem veto; sem free float em nome pequeno: vetado). Participação máxima do controlador sem fonte pública estruturada: não avaliada. |
| na meta | indicador | Origem dos dados | 0,0000 | n/d | Dados reais de snapshot imutável (hash verificado). |
| na meta | indicador | Distância à meta de volatilidade | 0,0364 | 0,0364 | Volatilidade ex-ante 3,64% contra a meta 3,64% (diferença 0,00 p.p.). |

## Principais posições

### 10 maiores posições compradas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | PagSeguro Digital | Brasil | Financeiro | +3,02% | USD 30,4 mil | PAGS (listada nos EUA) | 0,1% | médio (40) | +0,81 |
| 2 | BB Seguridade | Brasil | Financeiro | +2,19% | USD 22,1 mil | BBSE3.SA (local) | 0,0% | baixo (36) | +1,28 |
| 3 | Fortuna Mining | Regional (América Latina) | Materiais | +2,11% | USD 21,3 mil | FSM (listada nos EUA) | 0,0% | baixo (23) | +0,28 |
| 4 | Tenda | Brasil | Consumo discricionário | +2,08% | USD 20,9 mil | TEND3.SA (local) | 0,1% | baixo (34) | +1,45 |
| 5 | Axia Energia (ex-Eletrobras) | Brasil | Utilidades públicas | +1,79% | USD 18,0 mil | AXIA3.SA (local) | 0,0% | baixo (8) | +0,18 |
| 6 | Grupo Aeroméxico | México | Industriais | +1,64% | USD 16,5 mil | AERO (ADR) | 0,3% | baixo (20) | +0,01 |
| 7 | Telecom Argentina | Argentina | Comunicações | +1,53% | USD 15,4 mil | TEO (ADR) | 0,4% | baixo (10) | +1,92 |
| 8 | PicPay (PicS N.V.) | Brasil | Financeiro | +1,53% | USD 15,4 mil | PICS (listada nos EUA) | 0,2% | baixo (25) | +0,68 |
| 9 | Petrobras | Brasil | Energia | +1,51% | USD 15,2 mil | PBR (ADR) | 0,0% | baixo (20) | +2,33 |
| 10 | Millicom (Tigo) | Regional (América Latina) | Comunicações | +1,49% | USD 15,0 mil | TIGO (listada nos EUA) | 0,0% | baixo (15) | +0,57 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- _Sem nota de pesquisa:_ PagSeguro Digital, BB Seguridade, Fortuna Mining, Tenda, Axia Energia (ex-Eletrobras), Grupo Aeroméxico, Telecom Argentina, PicPay (PicS N.V.), Petrobras, Millicom (Tigo)

### 10 maiores posições vendidas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Auren Energia | Brasil | Utilidades públicas | -2,50% | USD -25,2 mil | AURE3.SA (local) | 0,2% | baixo (22) | -2,32 |
| 2 | Liberty Latin America | Regional (América Latina) | Comunicações | -2,50% | USD -25,2 mil | LILAK (listada nos EUA) | 0,2% | baixo (36) | -1,97 |
| 3 | Patria Investments | Brasil | Financeiro | -2,38% | USD -24,0 mil | PAX (listada nos EUA) | 0,2% | baixo (26) | -1,80 |
| 4 | Smart Fit | Brasil | Consumo discricionário | -2,38% | USD -24,0 mil | SMFT3.SA (local) | 0,1% | baixo (32) | -0,45 |
| 5 | Cemex | México | Materiais | -2,30% | USD -23,2 mil | CX (ADR) | 0,0% | baixo (7) | -1,09 |
| 6 | Fleury | Brasil | Saúde | -2,17% | USD -21,9 mil | FLRY3.SA (local) | 0,1% | baixo (24) | +0,60 |
| 7 | Aura Minerals | Brasil | Materiais | -2,00% | USD -20,2 mil | AUGO (listada nos EUA) | 0,0% | baixo (35) | +0,94 |
| 8 | Banco do Brasil | Brasil | Financeiro | -1,47% | USD -14,8 mil | BBAS3.SA (local) | 0,0% | baixo (29) | -0,31 |
| 9 | Brava Energia | Brasil | Energia | -1,44% | USD -14,5 mil | BRAV3.SA (local) | 0,1% | baixo (25) | -0,61 |
| 10 | Grupo Aeroportuario del Sureste | México | Industriais | -1,38% | USD -13,9 mil | ASR (ADR) | 0,1% | baixo (25) | -1,37 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- _Sem nota de pesquisa:_ Auren Energia, Liberty Latin America, Patria Investments, Smart Fit, Cemex, Fleury, Aura Minerals, Banco do Brasil, Brava Energia, Grupo Aeroportuario del Sureste

## Exposições

### Por país (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| México | 5,52% | -4,76% | +0,76% | 10,28% | ±2,00% |
| Panamá | 0,50% | 0,00% | +0,50% | 0,50% | ±2,00% |
| Uruguai | 0,00% | -0,50% | -0,50% | 0,50% | ±2,00% |
| Peru | 0,97% | -0,71% | +0,26% | 1,68% | ±2,00% |
| Chile | 0,52% | -0,70% | -0,18% | 1,21% | ±2,00% |
| Argentina | 3,60% | -3,73% | -0,13% | 7,33% | ±2,00% |
| Brasil | 30,82% | -30,85% | -0,03% | 61,67% | ±2,00% |
| Regional (América Latina) | 3,60% | -3,61% | -0,01% | 7,21% | ±2,00% |

### Por setor (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Financeiro | 11,22% | -9,72% | +1,50% | 20,94% | ±2,50% |
| Utilidades públicas | 4,92% | -6,10% | -1,17% | 11,02% | ±2,50% |
| Saúde | 1,73% | -2,82% | -1,09% | 4,56% | ±2,50% |
| Imobiliário | 0,99% | 0,00% | +0,99% | 0,99% | ±2,50% |
| Consumo discricionário | 4,73% | -5,58% | -0,84% | 10,31% | ±2,50% |
| Tecnologia | 0,62% | 0,00% | +0,62% | 0,62% | ±2,50% |
| Industriais | 4,26% | -3,71% | +0,56% | 7,97% | ±2,50% |
| Consumo básico | 2,30% | -1,77% | +0,53% | 4,08% | ±2,50% |
| Materiais | 7,60% | -7,83% | -0,22% | 15,43% | ±2,50% |
| Comunicações | 4,12% | -4,29% | -0,18% | 8,41% | ±2,50% |
| Energia | 3,02% | -3,04% | -0,02% | 6,06% | ±2,50% |

### Fatores de estilo (σ × PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Vol residual | 0,000 | 0,000 | +0,050 | 0,050 | ±0,100 |
| Tamanho (size) | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Liquidez | 0,000 | 0,000 | -0,049 | 0,049 | ±0,100 |
| Momentum | 0,000 | 0,000 | -0,039 | 0,039 | ±0,100 |
| Valor (value) | 0,000 | 0,000 | -0,030 | 0,030 | ±0,100 |
| Sensibilidade cambial | 0,000 | 0,000 | +0,017 | 0,017 | ±0,100 |
| Beta de mercado | 0,000 | 0,000 | +0,002 | 0,002 | ±0,100 |

## Hedges cambiais sugeridos

| Moeda | Exposição | Hedge | Instrumento | Racional |
|---|---|---|---|---|
| ARS | USD -1,3 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em ARS: -0,13% do PL (USD -1.323), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| BRL | USD -0,3 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em BRL: -0,03% do PL (USD -288), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 225.433, shorts USD 217.183; necessidade líquida de comprar BRL à vista ≈ USD 8.250. |
| CLP | USD -1,8 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em CLP: -0,18% do PL (USD -1.791), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| MXN | USD +7,7 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em MXN: +0,76% do PL (USD 7.698), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 21.609, shorts USD 0; necessidade líquida de comprar MXN à vista ≈ USD 21.609. |
| PEN | USD +2,6 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em PEN: +0,26% do PL (USD 2.638), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |

## Ordens

| Item | Valor |
|---|---|
| Nº de ordens | 83 (compra 26, recompra 20, venda 15, venda a descoberto 22) |
| Volume bruto negociado | USD 257,8 mil (25,61% do PL) |
| Giro (Σ\|Δw\|) | 25,61% |
| Custo estimado | USD 224 (16,5 bps do volume; 0,022% do PL) |
| Maior % do volume médio diário | 0,1% |
| Maior prazo estimado de execução | 0,1 fech. |
| Ordens na B3 com perna no fracionário (sufixo F) | 51 de 51 |
| Ordens na BMV com perna em pico (abaixo do lote que forma preço) | 2 de 2 |
| Maior erro do arredondamento a ações inteiras | +0,071% do PL (MELI); soma 0,120% |

_32 ordens sem estimativa de custo — excluídas da soma de custos (custo ausente)._

## Pesquisa e visões

Autoria: pesquisa da gestão; 3 notas por empresa (3 com apoio de IA), 7 notas macro, 3 visões.

2 manchetes consideradas — conteúdo NÃO confiável, não reproduzido neste memo.

### Notas macro

#### AR — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> O BCRA publicou relatório de política monetária de 3T26. Abstenção direcional: a revisão integral do documento e das condições cambiais não foi concluída.

Riscos:
- Liquidez, câmbio e estabilização monetária.

#### BR — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> Abstenção macro. O calendário do Banco Central identifica a reunião de novembro; a revisão integral da comunicação e sua transmissão setorial não foi concluída.

Riscos:
- Juros, inflação e financiamento corporativo.

#### CL — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> Abstenção macro. O calendário oficial de política monetária foi localizado, sem inferência de decisão futura ou de direção para os ativos.

Riscos:
- Juros locais, cobre e câmbio.

#### CO — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> Abstenção macro. A comunicação pública do Banco de la República mantém a inflação como tema de acompanhamento. Não inferimos prêmio direcional sem análise conjunta de juros e risco fiscal.

Riscos:
- Inflação, risco fiscal e exposição a petróleo.

#### GLOBAL — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> Sem inclinação macro. O comunicado do Federal Reserve de 2026-10-28 é referência pública; sua transmissão à carteira permanece incerta e não justifica aposta direcional nesta análise.

Riscos:
- Juros em dólar e correlações podem alterar o risco fatorial.

#### MX — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> Abstenção macro. A listagem pública de decisões do Banxico foi localizada; sem conciliação integral da comunicação vigente, não assumimos afrouxamento monetário ou valorização cambial.

Riscos:
- Inflação, câmbio e demanda externa.

#### PE — regime: neutro (viés +0)
_(pesquisa da gestão (IA))_

> Abstenção macro. A busca não confirmou nesta análise o documento primário corrente do programa monetário; não atribuímos decisão ou trajetória de juros ao BCRP.

Riscos:
- Lacuna de confirmação primária da política monetária e exposição a metais.

### Visões aplicadas

| Empresa | Origem | Visão | Confiança | Restrições | Autoria |
|---|---|---|---|---|---|
| Grupo Financiero Galicia | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Sigma Lithium | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Volaris | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |

## Otimizador

| Item | Valor |
|---|---|
| Situação / solver | ótimo / CLARABEL |
| Tempo de solução | 2,73 s |
| Alpha esperado (a.a.) | 2,19% |
| Custo esperado (a.a.) | 0,34% |
| Candidatos | 232 |
| Excluídos | bloqueio free float: 7, bloqueio free float desconhecido: 1, bloqueio resultado: 9, bloqueio resultado estimado: 1, sem linha short: 84, squeeze alto: 17, squeeze medio teto: 7, squeeze na teto: 44, visao no short: 3 |
| Restrições ativas | meta de vol, estilo: Tamanho (size), estilo: Vol residual, país (limite operacional): Panamá, país (limite operacional): Uruguai, tema: commodity:copper, teto vendido: Auren Energia, teto vendido: Rumo, teto vendido: Liberty Latin America |

Observações do otimizador:
- Meta de vol ajustada pelo gestor: 3,64% (mandato 5,00%).
- Exposição bruta máxima efetivo: 2,00x (definido pelo gestor).
- Teto de risco fatorial na carteira atingida (fatia fatorial máxima 10%): 1 passo(s); fatia idiossincrática: modelo de decisão 94,6%, modelo base 94,6%.
- 1 posição abaixo do mínimo de 0,20% (ou da posição mínima pelo custo fixo do mercado) permaneceram (saída gradual, limite de passadas ou passada recusada).
- Passadas de otimização: 3.
- Reparo de complementaridade: 7 emissores tinham perna comprada e vendida simultâneas (custo subestimado) e foram re-otimizados com uma única perna.
- Perna comprada 45,53%, vendida 44,86%; custo pontual 3,2 bps do PL; aluguel 13,4 bps a.a.
- Bloco macro no modelo de risco: petróleo Brent, cobre, ouro, índice do dólar (DXY) (1 emissor com beta pela média do setor).
- Fallback 1: apenas restrições da IA/PM (sem inclinações).
- [visões] IC das visões de IA = 0,01 (fase S1, teto 0,03).
- [visões] Grupo Financiero Galicia: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Sigma Lithium: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Volaris: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Grupo Financiero Galicia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Sigma Lithium: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Volaris: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Após as visões: Ortogonalização WLS (pesos 1/σ²): 0,0% da variância ponderada do alpha bruto era explicada por fatores e foi removida.

## Decisões pendentes do gestor

- [ ] Confirmar a disponibilidade de aluguel para as 44 posições vendidas antes da execução.
- [ ] Revisar 3 notas da pesquisa com apoio de IA.
- [ ] Validar 3 restrições propostas pela pesquisa (sem venda / sem compra / teto de peso).
- [ ] Decidir sobre os hedges cambiais sugeridos: ARS, BRL, CLP, MXN, PEN.
- [ ] Revisar observações/relaxamentos do otimizador.
- [ ] Obter co-assinatura independente de Risco/Compliance (quatro olhos): Volatilidade ex-ante 3,64% fora de [4,00%, 6,00%].
- [ ] Aprovar ou rejeitar com justificativa — a decisão fica vinculada aos hashes dos dados de mercado, do mandato, da pesquisa e da proposta.

---

_Todos os números deste memo foram calculados e formatados por código a partir da proposta; textos de pesquisa são citados como fornecidos e rotulados pela origem._

---

_Hash da proposta (SHA-256): `1a97fab8c408f8eeadb5a1fb2e33d7217575fbb55ca8b7d424c3f6200ec0aa10`_
