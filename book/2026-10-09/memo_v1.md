# CDP — Cabra da Peste — Proposta da semana de 09/10/2026 (v1)

> Dados de mercado: retrato `store-2026-10-02+4-2026-10-08`. Dados reais (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética.

| Campo | Valor |
|---|---|
| Estado | **EM REVISÃO** |
| Proposta | CDP-2026-10-09-cdp (versão 1) |
| Criada em / por | 09/10/2026 11:53 (Brasília) — CDP — motor quantitativo |
| PL de referência | USD 1,00 mm |
| Retrato dos dados de mercado | store-2026-10-02+4-2026-10-08 — `e0dae242a7c0` |
| Hash do mandato | `2ddf7d89ac76` |
| Hash da pesquisa | `25e88011886f` |

## Resumo de risco

| Métrica | Valor | Referência |
|---|---|---|
| Vol ex-ante (a.a.) | 3,64% | meta aplicada 3,64% (mandato 5,00%); banda 3,00%–7,00% — dentro da banda |
| Vol fatorial (a.a.) | 0,49% | 4,65% da variância com κ_F no modelo base (limite 10,00%) |
| Vol específica (a.a.) | 3,60% | fonte pretendida do retorno (alpha puro) |
| Beta previsto | 0,004 | limite ±0,050 |
| Exposição bruta (% do PL) | 64,42% | faixa 50%–250% |
| Exposição líquida (% do PL) | +0,90% | limite ±1,00% |
| Comprado / vendido (% do PL) | 32,66% / -31,76% |  |
| Nº de posições compradas / vendidas | 37 / 36 |  |
| VaR 1d 99% | 0,53% (USD 5,3 mil) | paramétrico/histórico (modelo de risco) |
| ES 1d 99% | 0,61% (USD 6,1 mil) |  |
| VaR 1 semana 99% | 1,19% (USD 11,9 mil) |  |
| N efetivo | 49,6 | diversificação (1/Σw² normalizado) |
| Máx. fechamentos para liquidar | 0,4 fech. | long ≤ 3,0 fech.; short ≤ 2,0 fech. |
| % do gross liquidável em 1 fechamento | 100,00% | capacidade estrutural do leilão e da janela pré-fechamento |
| Fatia idiossincrática — modelo de decisão | 97,34% | meta 90%; piso 85% (com janelas de evento) |
| Fatia idiossincrática — modelo base | 95,35% | meta 90%; piso 85% (sem janelas de evento) |
| Inflação de 2ª ordem do risco fatorial (κ_F) | 1,45 | aplicada à variância fatorial na medida idiossincrática |

### Decomposição da variância ex-ante por grupo (modelo de decisão, κ_F no bloco fatorial)

| Grupo | Fração da variância |
|---|---|
| Mercado | 0,11% |
| País | 0,10% |
| Setor | 1,30% |
| Estilo | 0,82% |
| Macro (commodities e dólar) | 0,33% |
| Específico (idiossincrático) | 97,34% |

### Testes de estresse (resultado estimado)

| Cenário | % do PL | US$ |
|---|---|---|
| Quebra: 5 maiores posições compradas −30% | -3,62% | USD -36,2 mil |
| Squeeze: 5 maiores posições vendidas +30% | -2,60% | USD -26,0 mil |
| Tarifas dos EUA (abr/2025) | -0,23% | USD -2,3 mil |
| Eleição México jun/2024 | -0,23% | USD -2,3 mil |
| Gap México −13% | -0,13% | USD -1,3 mil |
| Gap Argentina +41% | -0,11% | USD -1,1 mil |
| Gap Chile −15% | -0,07% | USD -0,7 mil |
| Mercado da América Latina −20% | -0,04% | USD -0,4 mil |
| Brasil −15% | -0,04% | USD -0,4 mil |
| Commodities −15% | -0,04% | USD -0,4 mil |
| Eleição Brasil out/2022 (2º turno) | -0,03% | USD -0,3 mil |
| Gap Brasil −10% | -0,03% | USD -0,3 mil |
| Gap Peru −10% | 0,00% | USD 0,00 mm |
| Gap Colômbia −11% | 0,00% | USD 0,0 mil |
| Gap Brasil +10% | +0,03% | USD +0,3 mil |
| México −15% | +0,04% | USD +0,4 mil |
| Gap Argentina −56% | +0,15% | USD +1,5 mil |
| Colapso do fator momentum −3σ | +0,15% | USD +1,5 mil |
| Estresse de juros nos EUA jun/2022 | +0,39% | USD +3,9 mil |
| Choque fiscal BRL dez/2024 | +0,84% | USD +8,4 mil |
| Crise da covid (fev-mar/2020) | n/d | n/d |
| Estallido social Chile (out-nov/2019) | n/d | n/d |
| Joesley Day (mai/2017) | n/d | n/d |
| PASO Argentina 2019 | n/d | n/d |
| Taper tantrum (mai-jun/2013) | n/d | n/d |

### Maiores contribuições fatoriais (fração da variância)

| Fator | Contribuição |
|---|---|
| Setor — Tecnologia | 0,33% |
| Setor — Consumo discricionário | 0,27% |
| Macro — petróleo Brent | 0,23% |
| Estilo — Momentum | 0,21% |
| Estilo — Tamanho (size) | 0,20% |
| Estilo — Liquidez | 0,10% |
| Setor — Consumo básico | 0,10% |
| Estilo — Vol residual | 0,09% |
| País — Argentina | 0,08% |
| Mercado da América Latina | 0,08% |

### Maiores contribuições de risco por empresa (fração da variância)

| Empresa | Contribuição |
|---|---|
| Sigma Lithium | 7,71% |
| PagSeguro Digital | 7,62% |
| Patria Investments | 7,60% |
| Petrobras | 7,49% |
| Tenda | 7,46% |
| Genomma Lab | 6,52% |
| Inter&Co | 6,32% |
| Riachuelo (ex-Guararapes) | 3,95% |
| Suzano | 3,67% |
| Grupo Aeroméxico | 3,41% |

## Controles do mandato

101 controles; 0 fora do limite (0 obrigatórios, 0 de alerta).

| Resultado | Tipo | Controle | Valor | Limite | Detalhe |
|---|---|---|---|---|---|
| dentro | obrigatório | Beta previsto | 0,0045 | 0,0500 | Beta previsto +0,004 (limite ±0,050). |
| dentro | obrigatório | Taxa de aluguel das posições vendidas | 0,0171 | 0,0500 | Taxas de aluguel dentro do limite de 5,00% a.a. |
| dentro | obrigatório | Exposição líquida por país (Argentina) | -0,0026 | 0,0200 | Líquido no país Argentina: −0,26% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Brasil) | 0,0025 | 0,0200 | Líquido no país Brasil: 0,25% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Chile) | 0,0050 | 0,0200 | Líquido no país Chile: 0,50% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Colômbia) | 0,0000 | 0,0200 | Líquido no país Colômbia: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Regional (América Latina)) | -0,0016 | 0,0200 | Líquido no país Regional (América Latina): −0,16% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (México) | 0,0100 | 0,0200 | Líquido no país México: 1,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Panamá) | 0,0000 | 0,0200 | Líquido no país Panamá: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Peru) | 0,0000 | 0,0200 | Líquido no país Peru: 0,00% do PL (limite ±2,00%). |
| dentro | obrigatório | Exposição líquida por país (Uruguai) | -0,0043 | 0,0200 | Líquido no país Uruguai: −0,43% do PL (limite ±2,00%). |
| dentro | obrigatório | Defasagem dos dados de mercado | 0,0000 | 4,0000 | Dados de mercado de 09/10/2026 para a semana de 09/10/2026: 0 dias corridos (máximo 4). |
| dentro | obrigatório | Stop de drawdown (corte da exposição bruta) | 0,0000 | -0,0500 | Drawdown 0,00% (stop −5,00%, zeragem −7,50%). |
| dentro | obrigatório | Exposição bruta máxima | 0,6442 | 2,5000 | Exposição bruta 0,64x do PL (máximo 2,50x). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo de decisão) | 0,9734 | 0,8500 | Fatia idiossincrática 97,34% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Piso da fatia idiossincrática (modelo base) | 0,9535 | 0,8500 | Fatia idiossincrática 95,35% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (piso 85,00%, nunca relaxado). |
| dentro | obrigatório | Prazo de liquidação das posições compradas | 0,3557 | 3,0000 | Máximo de 0,36 fechamentos à capacidade estrutural do leilão (limite 3,0). |
| dentro | obrigatório | Prazo de liquidação das posições vendidas | 0,0676 | 2,0000 | Máximo de 0,07 fechamentos à capacidade estrutural do leilão (limite 2,0). |
| dentro | obrigatório | Compra só em nomes elegíveis e sem veto | 0,0000 | 0,0000 | Todas as compras são permitidas. |
| dentro | obrigatório | Peso máximo por nome (posição comprada) | 0,0337 | 0,0400 | Nenhuma posição comprada acima do teto por nome. |
| dentro | obrigatório | Peso máximo por nome (posição vendida) | 0,0223 | 0,0250 | Nenhuma posição vendida acima do teto por nome. |
| dentro | obrigatório | Exposição líquida | 0,0090 | 0,0100 | Líquido 0,90% do PL (limite ±1,00%); comprado 32,66%, vendido −31,76%. |
| dentro | obrigatório | Cobertura do modelo de risco | 0,0000 | 0,0000 | Todos os nomes com peso têm risco modelado. |
| dentro | obrigatório | Exposição líquida por setor (comunicações) | -0,0037 | 0,0250 | Líquido no setor Comunicações: −0,37% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo discricionário) | 0,0150 | 0,0250 | Líquido no setor Consumo discricionário: 1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (consumo básico) | 0,0150 | 0,0250 | Líquido no setor Consumo básico: 1,50% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (energia) | -0,0017 | 0,0250 | Líquido no setor Energia: −0,17% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (financeiro) | -0,0081 | 0,0250 | Líquido no setor Financeiro: −0,81% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (saúde) | 0,0002 | 0,0250 | Líquido no setor Saúde: 0,02% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (industriais) | 0,0021 | 0,0250 | Líquido no setor Industriais: 0,21% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (tecnologia) | 0,0063 | 0,0250 | Líquido no setor Tecnologia: 0,63% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (materiais) | 0,0000 | 0,0250 | Líquido no setor Materiais: 0,00% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (imobiliário) | -0,0080 | 0,0250 | Líquido no setor Imobiliário: −0,80% do PL (limite ±2,50%). |
| dentro | obrigatório | Exposição líquida por setor (utilidades públicas) | -0,0081 | 0,0250 | Líquido no setor Utilidades públicas: −0,81% do PL (limite ±2,50%). |
| dentro | obrigatório | Sem nova venda a descoberto em nome vetado | 0,0000 | 0,0000 | Nenhuma venda a descoberto nova ou aumentada em nome com resultado próximo ou free float baixo. |
| dentro | obrigatório | Venda a descoberto só em linhas alugáveis e sem veto | 0,0000 | 0,0000 | Todas as posições vendidas são alugáveis e sem veto. |
| dentro | obrigatório | Sem posição vendida com risco alto de squeeze | 0,0000 | 0,0000 | Nenhuma posição vendida em nome com risco de squeeze alto. |
| dentro | obrigatório | Teto da posição vendida com risco médio de squeeze | 0,0043 | 0,0125 | Posições vendidas com risco de squeeze médio ou sem dado dentro do teto de 1,25%. |
| dentro | obrigatório | Exposição ao estilo (beta de mercado) | -0,0134 | 0,1000 | Exposição líquida −0,013 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (sensibilidade cambial) | 0,0169 | 0,1000 | Exposição líquida +0,017 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (liquidez) | -0,0255 | 0,1000 | Exposição líquida −0,026 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (momentum) | -0,0330 | 0,1000 | Exposição líquida −0,033 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (vol residual) | 0,0242 | 0,1000 | Exposição líquida +0,024 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (tamanho (size)) | -0,0500 | 0,1000 | Exposição líquida −0,050 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição ao estilo (valor (value)) | -0,0046 | 0,1000 | Exposição líquida −0,005 desvios-padrão × PL (limite ±0,10). |
| dentro | obrigatório | Exposição líquida ao tema (estatais) | 0,0100 | 0,0100 | Líquido 1,00% no tema estatais (limite ±1,00%). |
| dentro | obrigatório | Volatilidade ex-ante máxima | 0,0364 | 0,0700 | Volatilidade ex-ante 3,64% a.a. (teto da banda 7,00%). |
| dentro | obrigatório | Pesos numéricos válidos | 0,0000 | 0,0000 | Todos os pesos são finitos. |
| dentro | alerta | Beta previsto (limite operacional) | 0,0045 | 0,0200 | Beta previsto +0,004 (limite operacional ±0,020). |
| dentro | alerta | Sensibilidade a commodity (cobre) | -0,0047 | 0,0300 | Σ w·β = −0,0047 (limite ±0,03); 10% na commodity ⇒ −0,05% do PL. |
| dentro | alerta | Sensibilidade a commodity (ouro) | -0,0057 | 0,0300 | Σ w·β = −0,0057 (limite ±0,03); 10% na commodity ⇒ −0,06% do PL. |
| dentro | alerta | Sensibilidade a commodity (petróleo) | 0,0008 | 0,0300 | Σ w·β = +0,0008 (limite ±0,03); 10% na commodity ⇒ +0,01% do PL. |
| dentro | alerta | Sensibilidade a commodity, limite operacional (cobre) | -0,0047 | 0,0100 | Σ w·β = −0,0047 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (ouro) | -0,0057 | 0,0100 | Σ w·β = −0,0057 (limite operacional ±0,010). |
| dentro | alerta | Sensibilidade a commodity, limite operacional (petróleo) | 0,0008 | 0,0100 | Σ w·β = +0,0008 (limite operacional ±0,010). |
| dentro | alerta | Perda em gap de país | -0,0013 | -0,0150 | Pior cenário: Gap MX −13% com −0,13% do PL (limite −1,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Argentina) | -0,0026 | 0,0050 | Líquido no país Argentina: −0,26% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Brasil) | 0,0025 | 0,0100 | Líquido no país Brasil: 0,25% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Chile) | 0,0050 | 0,0050 | Líquido no país Chile: 0,50% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Colômbia) | 0,0000 | 0,0050 | Líquido no país Colômbia: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Regional (América Latina)) | -0,0016 | 0,0050 | Líquido no país Regional (América Latina): −0,16% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (México) | 0,0100 | 0,0100 | Líquido no país México: 1,00% do PL (limite operacional ±1,00%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Panamá) | 0,0000 | 0,0050 | Líquido no país Panamá: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Peru) | 0,0000 | 0,0050 | Líquido no país Peru: 0,00% do PL (limite operacional ±0,50%). |
| dentro | alerta | Exposição líquida por país, limite operacional (Uruguai) | -0,0043 | 0,0050 | Líquido no país Uruguai: −0,43% do PL (limite operacional ±0,50%). |
| dentro | alerta | Nível de revisão do drawdown | 0,0000 | -0,0250 | Drawdown 0,00% (gatilho de revisão −2,50%). |
| dentro | alerta | Exposição ao choque de evento | 0,0003 | 0,0015 | Reação residual ao choque do evento replicada na carteira: +0,030% do PL (limite ±0,15%). |
| dentro | alerta | Parcela fatorial do risco | 0,0266 | 0,1000 | Risco fatorial = 2,66% da variância com inflação de 2ª ordem κ_F = 1,45 no bloco fatorial (limite 10,00%); o restante é específico (alpha puro). |
| dentro | alerta | Exposição bruta mínima | 0,6442 | 0,5000 | Exposição bruta 0,64x do PL (mínimo recomendado 0,50x). |
| dentro | alerta | Meta da fatia idiossincrática (modelo de decisão) | 0,9734 | 0,9000 | Fatia idiossincrática 97,34% da variância ex-ante no modelo de decisão (com janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Meta da fatia idiossincrática (modelo base) | 0,9535 | 0,9000 | Fatia idiossincrática 95,35% da variância ex-ante no modelo base (sem janelas de evento), κ_F = 1,45 (meta 90,00%). |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0000 | 0,0400 | Comprado 0,00% (teto 4,00%), vendido 0,00% (teto 2,50%) somando CSN Siderúrgica Nacional, CSN Mineração: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0059 | 0,0400 | Comprado 0,59% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Metalúrgica Gerdau, Gerdau: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0027 | 0,0400 | Comprado 0,27% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Itaúsa, Itaú Unibanco: holding e controlada contam como um só nome. |
| dentro | alerta | Grupo de controle (holding e controladas) | 0,0058 | 0,0400 | Comprado 0,58% (teto 4,00%), vendido 0,00% (teto 2,50%) somando Bradespar, Vale: holding e controlada contam como um só nome. |
| dentro | alerta | Exposição líquida por setor, limite operacional (comunicações) | -0,0037 | 0,0150 | Líquido no setor Comunicações: −0,37% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo discricionário) | 0,0150 | 0,0150 | Líquido no setor Consumo discricionário: 1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (consumo básico) | 0,0150 | 0,0150 | Líquido no setor Consumo básico: 1,50% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (energia) | -0,0017 | 0,0150 | Líquido no setor Energia: −0,17% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (financeiro) | -0,0081 | 0,0150 | Líquido no setor Financeiro: −0,81% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (saúde) | 0,0002 | 0,0150 | Líquido no setor Saúde: 0,02% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (industriais) | 0,0021 | 0,0150 | Líquido no setor Industriais: 0,21% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (tecnologia) | 0,0063 | 0,0150 | Líquido no setor Tecnologia: 0,63% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (materiais) | 0,0000 | 0,0150 | Líquido no setor Materiais: 0,00% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (imobiliário) | -0,0080 | 0,0150 | Líquido no setor Imobiliário: −0,80% do PL (limite operacional ±1,50%). |
| dentro | alerta | Exposição líquida por setor, limite operacional (utilidades públicas) | -0,0081 | 0,0150 | Líquido no setor Utilidades públicas: −0,81% do PL (limite operacional ±1,50%). |
| dentro | alerta | Contribuição máxima de um nome ao risco | 0,0771 | 0,0800 | Maior contribuição: Sigma Lithium com 7,71% da variância (limite 8,00%). |
| dentro | alerta | Exposição ao estilo, limite operacional (beta de mercado) | -0,0134 | 0,0500 | Exposição líquida −0,013 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (sensibilidade cambial) | 0,0169 | 0,0500 | Exposição líquida +0,017 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (liquidez) | -0,0255 | 0,0500 | Exposição líquida −0,026 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (momentum) | -0,0330 | 0,0500 | Exposição líquida −0,033 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (vol residual) | 0,0242 | 0,0500 | Exposição líquida +0,024 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (tamanho (size)) | -0,0500 | 0,0500 | Exposição líquida −0,050 (limite operacional ±0,05). |
| dentro | alerta | Exposição ao estilo, limite operacional (valor (value)) | -0,0046 | 0,0500 | Exposição líquida −0,005 (limite operacional ±0,05). |
| dentro | alerta | Ordens dentro da capacidade do fechamento | 0,0000 | 0,0000 | Toda abertura ou aumento cabe na capacidade do leilão e da janela pré-fechamento. |
| dentro | alerta | Giro semanal | 0,6442 | n/d | Carteira inaugural: montagem inicial de 64,42% do PL (sem limite de giro). |
| dentro | alerta | Volatilidade ex-ante mínima | 0,0364 | 0,0300 | Volatilidade ex-ante 3,64% a.a. (piso da banda 3,00%). |
| na meta | indicador | Emissores sem fechamento negociável | 0,0000 | n/d | Nenhum emissor congelado. |
| na meta | indicador | Dados dos vetos de venda a descoberto | 17,0000 | n/d | 17 emissores sem data de resultado ou free float conhecidos (sem data: sinalizado, sem veto; sem free float em nome pequeno: vetado). Participação máxima do controlador sem fonte pública estruturada: não avaliada. |
| na meta | indicador | Origem dos dados | 0,0000 | n/d | Dados reais de snapshot imutável (hash verificado). |
| na meta | indicador | Distância à meta de volatilidade | 0,0364 | 0,0364 | Volatilidade ex-ante 3,64% contra a meta 3,64% (diferença 0,00 p.p.). |

## Principais posições

### 10 maiores posições compradas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Petrobras | Brasil | Energia | +3,37% | USD 33,7 mil | PBR (ADR) | 0,0% | baixo (18) | +2,28 |
| 2 | Genomma Lab | México | Consumo básico | +2,77% | USD 27,7 mil | LABB.MX (local) | 1,1% | n/d (33) | +2,56 |
| 3 | PagSeguro Digital | Brasil | Financeiro | +2,27% | USD 22,7 mil | PAGS (listada nos EUA) | 0,1% | baixo (38) | +0,80 |
| 4 | Suzano | Brasil | Materiais | +1,90% | USD 19,0 mil | SUZB3.SA (local) | 0,0% | baixo (15) | +0,09 |
| 5 | Grupo Aeroméxico | México | Industriais | +1,75% | USD 17,5 mil | AERO (ADR) | 0,4% | baixo (18) | +0,92 |
| 6 | Tenda | Brasil | Consumo discricionário | +1,62% | USD 16,2 mil | TEND3.SA (local) | 0,1% | baixo (27) | +2,21 |
| 7 | Riachuelo (ex-Guararapes) | Brasil | Consumo discricionário | +1,31% | USD 13,1 mil | RIAA3.SA (local) | 0,5% | alto (70) | +2,27 |
| 8 | BB Seguridade | Brasil | Financeiro | +1,18% | USD 11,8 mil | BBSE3.SA (local) | 0,0% | baixo (30) | +1,33 |
| 9 | ISA Energia Brasil | Brasil | Utilidades públicas | +1,07% | USD 10,7 mil | ISAE4.SA (local) | 0,0% | baixo (38) | +1,09 |
| 10 | Fortuna Mining | Regional (América Latina) | Materiais | +1,00% | USD 10,0 mil | FSM (listada nos EUA) | 0,0% | baixo (23) | +0,52 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **Petrobras**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Petrobras. Rating Neutro e confiança C. A confiança reduzida na cobertura impede tratar o preço-alvo como confirmação independente do sinal quantitativo. A normalização das margens depende do ciclo da commodity, do câmbio e da execução operacional; lucro corrente não demonstra margem sustentável.
- **Genomma Lab**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Genomma Lab. Rating Neutro e confiança C. A confiança reduzida na cobertura impede tratar o preço-alvo como confirmação independente do sinal quantitativo. A conversão do lucro em caixa e o reinvestimento exigem acompanhamento; consenso de mercado não demonstra a realização dos resultados futuros.
- **PagSeguro Digital**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Visão positiva de convicção moderada para PagSeguro Digital. O modelo aponta alvo de US$ 20,02, upside de +87,49% e dispersão de 3,97%. A concordância entre métodos não é evidência independente, pois as premissas de rentabilidade são compartilhadas. A tese depende de rentabilidade sustentável, custo de crédito e competição nos pagamentos. O calendário consultado não exibiu data confirmada do próximo resultado; a estimativa do modelo permanece condicionada.
- **Suzano**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Suzano. Rating Neutro e confiança C. A confiança reduzida na cobertura impede tratar o preço-alvo como confirmação independente do sinal quantitativo. A normalização das margens depende do ciclo da commodity, do câmbio e da execução operacional; lucro corrente não demonstra margem sustentável.
- **Grupo Aeroméxico**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Grupo Aeroméxico. Rating Em revisão e confiança C. A cobertura não sustenta preço-alvo citável para decisão direcional adicional. A conversão do lucro em caixa e o reinvestimento exigem acompanhamento; consenso de mercado não demonstra a realização dos resultados futuros.
- **Tenda**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Tenda. Rating Compra e confiança B. A cobertura é informativa, mas não basta, isoladamente, para uma inclinação adicional à seleção quantitativa. A conversão de vendas em caixa e a necessidade de capital de giro podem divergir do lucro contábil; a realização do valor patrimonial permanece incerta.
- **Riachuelo (ex-Guararapes)**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Riachuelo (ex-Guararapes). Rating Em revisão e confiança C. A cobertura não sustenta preço-alvo citável para decisão direcional adicional. A conversão do lucro em caixa e o reinvestimento exigem acompanhamento; consenso de mercado não demonstra a realização dos resultados futuros.
- **BB Seguridade**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em BB Seguridade. Rating Neutro e confiança C. A confiança reduzida na cobertura impede tratar o preço-alvo como confirmação independente do sinal quantitativo. O resultado financeiro e a sinistralidade podem deslocar a rentabilidade; a leitura de consenso não substitui a confirmação dos resultados.
- **ISA Energia Brasil**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Visão positiva de convicção moderada para ISA Energia Brasil. A energização de projetos informada pela companhia em 03/08/2026 favorece a entrada de receita regulada. O alvo de R$ 48,32 apresenta upside de +61,16%, mas a dispersão de 45,12% e o investimento necessário limitam a confiança. A tese depende da conversão do investimento em receita e caixa, com risco de endividamento e de remuneração regulatória.
- **Fortuna Mining**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão adicional de Fortuna Mining, selecionada na prévia. A leitura do modelo de cobertura não foi acompanhada de confirmação suficiente de catalisador para inclinação fundamental adicional. Abstenho-me de juízo direcional adicional. A seleção residual permanece sujeita a risco de câmbio, geração de caixa e revisão das premissas.

### 10 maiores posições vendidas

| # | Empresa | País | Setor | Peso | Nocional | Linha | % do volume médio | Risco de squeeze | Sinal quant. (z) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Patria Investments | Brasil | Financeiro | -2,23% | USD -22,3 mil | PAX (listada nos EUA) | 0,2% | baixo (31) | -2,17 |
| 2 | Inter&Co | Brasil | Financeiro | -2,06% | USD -20,6 mil | INTR (listada nos EUA) | 0,1% | baixo (27) | -2,63 |
| 3 | Ultrapar | Brasil | Energia | -1,81% | USD -18,1 mil | UGPA3.SA (local) | 0,0% | baixo (11) | -0,30 |
| 4 | Banco Bradesco | Brasil | Financeiro | -1,34% | USD -13,4 mil | BBDC4.SA (local) | 0,0% | baixo (30) | -1,15 |
| 5 | FEMSA | México | Consumo básico | -1,25% | USD -12,5 mil | FMX (ADR) | 0,0% | baixo (13) | +0,66 |
| 6 | Equatorial | Brasil | Utilidades públicas | -1,25% | USD -12,5 mil | EQTL3.SA (local) | 0,0% | baixo (16) | -1,12 |
| 7 | Cemex | México | Materiais | -1,25% | USD -12,5 mil | CX (ADR) | 0,0% | baixo (5) | -0,34 |
| 8 | YPF | Argentina | Energia | -1,24% | USD -12,4 mil | YPF (ADR) | 0,0% | baixo (11) | +1,01 |
| 9 | Allos | Brasil | Imobiliário | -1,17% | USD -11,7 mil | ALOS3.SA (local) | 0,0% | baixo (33) | -0,61 |
| 10 | Vibra Energia | Brasil | Energia | -1,12% | USD -11,2 mil | VBBR3.SA (local) | 0,0% | baixo (7) | -0,01 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **Patria Investments**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Patria Investments. Rating Compra e confiança B. A cobertura é informativa, mas não basta, isoladamente, para uma inclinação adicional à seleção quantitativa. A conversão do lucro em caixa e o reinvestimento exigem acompanhamento; consenso de mercado não demonstra a realização dos resultados futuros.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **sem restrição** —
    > Sentinela de Patria Investments: squeeze em 31,1, dias para cobrir em 4,7 dias e custo de aluguel em 0,30%. Não identifiquei impedimento adicional de squeeze nos dados consultados. A disponibilidade efetiva de aluguel e o free float não foram confirmados independentemente; o juízo permanece condicionado aos controles de execução e a eventos posteriores.
- **Inter&Co**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Inter&Co. Rating Neutro e confiança B. A cobertura é informativa, mas não basta, isoladamente, para uma inclinação adicional à seleção quantitativa. A rentabilidade depende do custo de crédito e da disciplina de capital; a comparabilidade entre lucro realizado e consenso exige acompanhamento.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **sem restrição** —
    > Sentinela de Inter&Co: squeeze em 26,6, dias para cobrir em 2,6 dias e custo de aluguel em 0,30%. Não identifiquei impedimento adicional de squeeze nos dados consultados. A disponibilidade efetiva de aluguel e o free float não foram confirmados independentemente; o juízo permanece condicionado aos controles de execução e a eventos posteriores.
- **Ultrapar**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Ultrapar. Rating Neutro e confiança A. A cobertura é informativa, mas não basta, isoladamente, para uma inclinação adicional à seleção quantitativa. A conversão do lucro em caixa e o reinvestimento exigem acompanhamento; consenso de mercado não demonstra a realização dos resultados futuros.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **sem restrição** —
    > Sentinela de Ultrapar: squeeze em 11,0, dias para cobrir em 3,1 dias e custo de aluguel em 0,42%. Não identifiquei impedimento adicional de squeeze nos dados consultados. A disponibilidade efetiva de aluguel e o free float não foram confirmados independentemente; o juízo permanece condicionado aos controles de execução e a eventos posteriores.
- **Banco Bradesco**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Banco Bradesco. Rating Neutro e confiança A. A cobertura é informativa, mas não basta, isoladamente, para uma inclinação adicional à seleção quantitativa. A rentabilidade depende do custo de crédito e da disciplina de capital; a comparabilidade entre lucro realizado e consenso exige acompanhamento.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **sem restrição** —
    > Sentinela de Banco Bradesco: squeeze em 30,3, dias para cobrir em 14,0 dias e custo de aluguel em 0,59%. Não identifiquei impedimento adicional de squeeze nos dados consultados. A disponibilidade efetiva de aluguel e o free float não foram confirmados independentemente; o juízo permanece condicionado aos controles de execução e a eventos posteriores.
- **FEMSA**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão adicional de FEMSA, selecionada na prévia. A leitura do modelo de cobertura não foi acompanhada de confirmação suficiente de catalisador para inclinação fundamental adicional. Abstenho-me de juízo direcional adicional. A seleção residual permanece sujeita a risco de câmbio, geração de caixa e revisão das premissas.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Sentinela adicional de FEMSA: os indicadores de squeeze e aluguel não estão disponíveis para fundamentar juízo adicional nesta pesquisa. Controlador, free float e disponibilidade efetiva de aluguel não foram confirmados independentemente. Mantenho cautela e condiciono a posição aos controles determinísticos de execução e à revisão de catalisadores posteriores.
- **Equatorial**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão adicional de Equatorial, selecionada na prévia. A leitura do modelo de cobertura não foi acompanhada de confirmação suficiente de catalisador para inclinação fundamental adicional. Abstenho-me de juízo direcional adicional. A seleção residual permanece sujeita a risco de câmbio, geração de caixa e revisão das premissas.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Sentinela adicional de Equatorial: os indicadores de squeeze e aluguel não estão disponíveis para fundamentar juízo adicional nesta pesquisa. Controlador, free float e disponibilidade efetiva de aluguel não foram confirmados independentemente. Mantenho cautela e condiciono a posição aos controles determinísticos de execução e à revisão de catalisadores posteriores.
- **Cemex**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão adicional de Cemex, selecionada na prévia. A leitura do modelo de cobertura não foi acompanhada de confirmação suficiente de catalisador para inclinação fundamental adicional. Abstenho-me de juízo direcional adicional. A seleção residual permanece sujeita a risco de câmbio, geração de caixa e revisão das premissas.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Sentinela adicional de Cemex: os indicadores de squeeze e aluguel não estão disponíveis para fundamentar juízo adicional nesta pesquisa. Controlador, free float e disponibilidade efetiva de aluguel não foram confirmados independentemente. Mantenho cautela e condiciono a posição aos controles determinísticos de execução e à revisão de catalisadores posteriores.
- **YPF**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em YPF. Rating Neutro e confiança C. A confiança reduzida na cobertura impede tratar o preço-alvo como confirmação independente do sinal quantitativo. A normalização das margens depende do ciclo da commodity, do câmbio e da execução operacional; lucro corrente não demonstra margem sustentável.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **sem restrição** —
    > Sentinela de YPF: squeeze em 11,1, dias para cobrir em 3,7 dias e custo de aluguel em 0,30%. Não identifiquei impedimento adicional de squeeze nos dados consultados. A disponibilidade efetiva de aluguel e o free float não foram confirmados independentemente; o juízo permanece condicionado aos controles de execução e a eventos posteriores.
- **Allos**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Revisão adicional de Allos, selecionada na prévia. A leitura do modelo de cobertura não foi acompanhada de confirmação suficiente de catalisador para inclinação fundamental adicional. Abstenho-me de juízo direcional adicional. A seleção residual permanece sujeita a risco de câmbio, geração de caixa e revisão das premissas.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **cautela** —
    > Sentinela adicional de Allos: os indicadores de squeeze e aluguel não estão disponíveis para fundamentar juízo adicional nesta pesquisa. Controlador, free float e disponibilidade efetiva de aluguel não foram confirmados independentemente. Mantenho cautela e condiciono a posição aos controles determinísticos de execução e à revisão de catalisadores posteriores.
- **Vibra Energia**
  - Tese _(pesquisa da gestão (IA), análise fundamentalista)_:
    > Abstenção de inclinação fundamental adicional em Vibra Energia. Rating Neutro e confiança A. A cobertura é informativa, mas não basta, isoladamente, para uma inclinação adicional à seleção quantitativa. A conversão do lucro em caixa e o reinvestimento exigem acompanhamento; consenso de mercado não demonstra a realização dos resultados futuros.
  - Risco de squeeze _(pesquisa da gestão (IA), risco da venda a descoberto)_: **sem restrição** —
    > Sentinela de Vibra Energia: squeeze em 7,1, dias para cobrir em 2,7 dias e custo de aluguel em 0,09%. Não identifiquei impedimento adicional de squeeze nos dados consultados. A disponibilidade efetiva de aluguel e o free float não foram confirmados independentemente; o juízo permanece condicionado aos controles de execução e a eventos posteriores.

## Exposições

### Por país (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| México | 4,82% | -3,82% | +1,00% | 8,64% | ±2,00% |
| Chile | 1,47% | -0,97% | +0,50% | 2,44% | ±2,00% |
| Uruguai | 0,00% | -0,43% | -0,43% | 0,43% | ±2,00% |
| Argentina | 3,09% | -3,35% | -0,26% | 6,44% | ±2,00% |
| Brasil | 21,48% | -21,22% | +0,25% | 42,70% | ±2,00% |
| Regional (América Latina) | 1,00% | -1,16% | -0,16% | 2,16% | ±2,00% |
| Colômbia | 0,80% | -0,81% | 0,00% | 1,61% | ±2,00% |

### Por setor (% do PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Consumo discricionário | 3,67% | -2,17% | +1,50% | 5,83% | ±2,50% |
| Consumo básico | 3,84% | -2,34% | +1,50% | 6,19% | ±2,50% |
| Financeiro | 7,40% | -8,21% | -0,81% | 15,61% | ±2,50% |
| Utilidades públicas | 2,98% | -3,78% | -0,81% | 6,76% | ±2,50% |
| Imobiliário | 0,37% | -1,17% | -0,80% | 1,54% | ±2,50% |
| Tecnologia | 0,63% | 0,00% | +0,63% | 0,63% | ±2,50% |
| Comunicações | 0,30% | -0,67% | -0,37% | 0,96% | ±2,50% |
| Industriais | 2,95% | -2,74% | +0,21% | 5,68% | ±2,50% |
| Energia | 5,10% | -5,26% | -0,17% | 10,36% | ±2,50% |
| Saúde | 0,60% | -0,59% | +0,02% | 1,19% | ±2,50% |
| Materiais | 4,83% | -4,83% | 0,00% | 9,67% | ±2,50% |

### Fatores de estilo (σ × PL)

| Nome | Comprado | Vendido | Líquido | Bruto | Limite |
|---|---|---|---|---|---|
| Tamanho (size) | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| Momentum | 0,000 | 0,000 | -0,033 | 0,033 | ±0,100 |
| Liquidez | 0,000 | 0,000 | -0,026 | 0,026 | ±0,100 |
| Vol residual | 0,000 | 0,000 | +0,024 | 0,024 | ±0,100 |
| Sensibilidade cambial | 0,000 | 0,000 | +0,017 | 0,017 | ±0,100 |
| Beta de mercado | 0,000 | 0,000 | -0,013 | 0,013 | ±0,100 |
| Valor (value) | 0,000 | 0,000 | -0,005 | 0,005 | ±0,100 |

## Hedges cambiais sugeridos

| Moeda | Exposição | Hedge | Instrumento | Racional |
|---|---|---|---|---|
| ARS | USD -2,6 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em ARS: -0,26% do PL (USD -2.646), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| BRL | USD +2,5 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em BRL: +0,25% do PL (USD 2.549), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 120.833, shorts USD 145.074; excedente líquido em BRL ≈ USD 24.241 (garantias/conversão). |
| CLP | USD +5,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em CLP: +0,50% do PL (USD 5.000), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| COP | USD 0,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em COP: -0,00% do PL (USD -49), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| MXN | USD +10,0 mil | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em MXN: +1,00% do PL (USD 10.000), somando linhas locais e ADRs. Dentro do limiar de 1,00%: sem hedge. Liquidação local: compras USD 27.728, shorts USD 0; necessidade líquida de comprar MXN à vista ≈ USD 27.728. |

## Ordens

| Item | Valor |
|---|---|
| Nº de ordens | 73 (compra 37, venda a descoberto 36) |
| Volume bruto negociado | USD 644,2 mil (64,42% do PL) |
| Giro (Σ\|Δw\|) | 64,42% |
| Custo estimado | USD 1.157 (18,0 bps do volume; 0,116% do PL) |
| Maior % do volume médio diário | 1,1% |
| Maior prazo estimado de execução | 0,4 fech. |
| Ordens na B3 com perna no fracionário (sufixo F) | 32 de 32 |
| Ordens na BMV com perna em pico (abaixo do lote que forma preço) | 1 de 1 |
| Maior erro do arredondamento a ações inteiras | -0,072% do PL (MELI); soma 0,113% |

## Pesquisa e visões

Autoria: pesquisa da gestão; 169 notas por empresa (169 com apoio de IA), 7 notas macro, 40 visões.

### Notas macro

#### AR — regime: cauteloso (viés +0)
_(pesquisa da gestão (IA))_

> O plano público do Banco Central argentino prioriza desinflação e estabilidade monetária. O retorno do ARGT em -8,47% não demonstra conclusão da normalização. Comparabilidade contábil, inflação e câmbio limitam a confiança nas estimativas das empresas.

Riscos:
- Inflação, custo de capital, câmbio e eventos políticos; dados ainda não confirmados permanecem ausentes.

Implicações para a carteira:
- Preservar neutralidade e restrições do mandato; não ampliar convicção diante de evidência insuficiente.

#### BR — regime: defensivo (viés +0)
_(pesquisa da gestão (IA))_

> O Banco Central descreveu desaceleração da inflação com riscos ainda relevantes no relatório de setembro. A Selic de 13,75% e a janela eleitoral recomendam prudência. O retorno do EWZ em +12,42% evidencia força recente, sem confirmar continuidade. O resultado corrente do IPCA não foi confirmado nesta pesquisa.

Riscos:
- Inflação, custo de capital, câmbio e eventos políticos; dados ainda não confirmados permanecem ausentes.

Implicações para a carteira:
- Preservar neutralidade e restrições do mandato; não ampliar convicção diante de evidência insuficiente.

Eventos:
- Eleição brasileira (25/10/2026; incerto)

#### CL — regime: cauteloso (viés +0)
_(pesquisa da gestão (IA))_

> A leitura do Banco Central do Chile destaca riscos para a inflação ligados a combustíveis e ao ambiente externo. O retorno do ECH em -4,99% reforça a cautela; concessões e imóveis devem ser avaliados por geração de caixa, sem pressupor alívio imediato do custo de capital.

Riscos:
- Inflação, custo de capital, câmbio e eventos políticos; dados ainda não confirmados permanecem ausentes.

Implicações para a carteira:
- Preservar neutralidade e restrições do mandato; não ampliar convicção diante de evidência insuficiente.

#### CO — regime: restritivo (viés -1)
_(pesquisa da gestão (IA))_

> O Banco de la República elevou a taxa na reunião de 30/09/2026. O aperto monetário amplia a incerteza sobre atividade e custo de crédito. O retorno do COLO em -6,16% não confirma oportunidade direcional.

Riscos:
- Inflação, custo de capital, câmbio e eventos políticos; dados ainda não confirmados permanecem ausentes.

Implicações para a carteira:
- Preservar neutralidade e restrições do mandato; não ampliar convicção diante de evidência insuficiente.

Eventos:
- Decisão de política monetária colombiana (30/10/2026; incerto)

#### GLOBAL — regime: defensivo (viés -1)
_(pesquisa da gestão (IA))_

> O Federal Reserve descreveu atividade robusta, inflação elevada e incerteza geopolítica na decisão de 16/09/2026. A valorização do índice do dólar em +3,05% constitui risco para exposições regionais. Prefiro postura defensiva diante da inflação americana e dos eventos brasileiros.

Riscos:
- Inflação, custo de capital, câmbio e eventos políticos; dados ainda não confirmados permanecem ausentes.

Implicações para a carteira:
- Preservar neutralidade e restrições do mandato; não ampliar convicção diante de evidência insuficiente.

Eventos:
- Inflação americana (14/10/2026; incerto)

#### MX — regime: cauteloso (viés +0)
_(pesquisa da gestão (IA))_

> O Banco de México manteve a taxa na decisão de 24/09/2026. O retorno do EWW em -5,22% e o risco cambial recomendam seletividade. A pausa monetária não demonstra recuperação dos lucros corporativos.

Riscos:
- Inflação, custo de capital, câmbio e eventos políticos; dados ainda não confirmados permanecem ausentes.

Implicações para a carteira:
- Preservar neutralidade e restrições do mandato; não ampliar convicção diante de evidência insuficiente.

#### PE — regime: abstenção (viés +0)
_(pesquisa da gestão (IA))_

> O retorno do EPU em -2,34% é apenas uma referência de mercado. Não foi possível confirmar o comunicado monetário vigente do Banco Central de Reserva do Peru nas fontes consultadas. Abstenho-me de inclinação macro adicional e preservo a incerteza sobre política monetária e demanda externa.

Riscos:
- Inflação, custo de capital, câmbio e eventos políticos; dados ainda não confirmados permanecem ausentes.

Implicações para a carteira:
- Preservar neutralidade e restrições do mandato; não ampliar convicção diante de evidência insuficiente.

### Visões aplicadas

| Empresa | Origem | Visão | Confiança | Restrições | Autoria |
|---|---|---|---|---|---|
| Allos | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Assaí Atacadista | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Aura Minerals | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Auren Energia | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banrisul | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Banco do Brasil | pesquisa (IA) | 0 | 100% | sem venda | pesquisa da gestão |
| Bemobi | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Companhia Brasileira de Alumínio | pesquisa (IA) | -1 | 40% | — | pesquisa da gestão |
| Cemig | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Copasa | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Cosan | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Embraer | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Energisa | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Equatorial | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| EZTec | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Fleury | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| GPS Participações | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| ISA Energia Brasil | pesquisa (IA) | +1 | 55% | — | pesquisa da gestão |
| Klabin | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Locaweb (LWSA) | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Magazine Luiza | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Mills | pesquisa (IA) | +1 | 40% | — | pesquisa da gestão |
| Movida | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| PagSeguro Digital | pesquisa (IA) | +1 | 50% | — | pesquisa da gestão |
| Randoncorp | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Rede D'Or São Luiz | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Sabesp | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Simpar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Smart Fit | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Unipar | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| XP Inc | pesquisa (IA) | -1 | 35% | — | pesquisa da gestão |
| Banco de Chile | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Arcos Dorados | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| dLocal | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| MercadoLibre | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Grupo Aeroportuario del Sureste | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Cemex | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| FEMSA | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Buenaventura | pesquisa (IA) | 0 | 0% | \|peso\| ≤ 1,25% | pesquisa da gestão |
| Hudbay Minerals | pesquisa (IA) | -1 | 45% | — | pesquisa da gestão |

## Otimizador

| Item | Valor |
|---|---|
| Situação / solver | ótimo / CLARABEL |
| Tempo de solução | 0,90 s |
| Alpha esperado (a.a.) | 2,46% |
| Custo esperado (a.a.) | 0,85% |
| Candidatos | 216 |
| Excluídos | bloqueio free float: 6, bloqueio resultado estimado: 3, sem linha short: 67, squeeze alto: 41, squeeze medio teto: 11, squeeze na teto: 44, visao no long: 3, visao no short: 5, visao teto peso: 32 |
| Restrições ativas | meta de vol, setor: Consumo discricionário, setor: Consumo básico, estilo: Tamanho (size), país (limite operacional): Chile, país (limite operacional): México, tema: estatais, participação do país: Argentina, teto vendido: Equatorial, teto vendido: Patria Investments, teto comprado: Petrobras, teto vendido: Sigma Lithium, teto vendido: Cemex, teto vendido: FEMSA |

Observações do otimizador:
- Meta de vol ajustada pelo gestor: 3,64% (mandato 5,00%).
- Exposição bruta máxima efetivo: 2,00x (definido pelo gestor).
- Teto de risco fatorial na carteira atingida (fatia fatorial máxima 10%): 1 passo(s); fatia idiossincrática: modelo de decisão 97,3%, modelo base 95,4%.
- Passadas de otimização: 2.
- Perna comprada 32,66%, vendida 31,76%; custo pontual 11,4 bps do PL; aluguel 10,5 bps a.a.
- Bloco macro no modelo de risco: petróleo Brent, cobre, ouro, índice do dólar (DXY) (0 emissores com beta pela média do setor).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (×1,50 na vol de BR)
- Carteira inaugural: carteira montada a partir do caixa.
- Carteira do CDP: pesquisa e decisão da gestão.
- [visões] IC das visões de IA = 0,01 (fase S1, teto 0,03).
- [visões] Aura Minerals: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Banco do Brasil: 2 visões de pesquisa agregadas pela média das inclinações.
- [visões] Companhia Brasileira de Alumínio: visão do gestor substitui a inclinação de 1 visão da pesquisa.
- [visões] ISA Energia Brasil: visão do gestor substitui a inclinação de 1 visão da pesquisa.
- [visões] Mills: visão do gestor substitui a inclinação de 1 visão da pesquisa.
- [visões] PagSeguro Digital: visão do gestor substitui a inclinação de 1 visão da pesquisa.
- [visões] XP Inc: visão do gestor substitui a inclinação de 1 visão da pesquisa.
- [visões] Hudbay Minerals: visão do gestor substitui a inclinação de 1 visão da pesquisa.
- [visões] Allos: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Assaí Atacadista: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Aura Minerals: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Auren Energia: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banrisul: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Banco do Brasil: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Bemobi: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Companhia Brasileira de Alumínio: inclinação do gestor z=−0,15 ⇒ α −0,20% a.a.
- [visões] Cemig: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Copasa: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cosan: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Embraer: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Energisa: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Equatorial: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] EZTec: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Fleury: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] GPS Participações: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] ISA Energia Brasil: inclinação do gestor z=+0,30 ⇒ α +0,25% a.a.
- [visões] Klabin: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Locaweb (LWSA): inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Magazine Luiza: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Mills: inclinação do gestor z=+0,15 ⇒ α +0,17% a.a.
- [visões] Movida: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] PagSeguro Digital: inclinação do gestor z=+0,30 ⇒ α +0,33% a.a.
- [visões] Randoncorp: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Rede D'Or São Luiz: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Sabesp: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Simpar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Smart Fit: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Unipar: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] XP Inc: inclinação do gestor z=−0,15 ⇒ α −0,14% a.a.
- [visões] Banco de Chile: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_ARCOS: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_DLOCAL: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] LA_MELI: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Grupo Aeroportuario del Sureste: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Cemex: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] FEMSA: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Buenaventura: inclinação da pesquisa z=+0,00 ⇒ α +0,00% a.a.
- [visões] Hudbay Minerals: inclinação do gestor z=−0,30 ⇒ α −0,20% a.a.
- [visões] Companhia Brasileira de Alumínio: coerência de sinal com a visão negativa ⇒ no_long
- [visões] ISA Energia Brasil: coerência de sinal com a visão positiva ⇒ no_short
- [visões] Mills: coerência de sinal com a visão positiva ⇒ no_short
- [visões] PagSeguro Digital: coerência de sinal com a visão positiva ⇒ no_short
- [visões] Após as visões: Ortogonalização WLS (pesos 1/σ²): 0,0% da variância ponderada do alpha bruto era explicada por fatores e foi removida.
- [risco por nome] passo 1: Petrobras com 8,70% da variância (limite 8,00%); teto max_long reduzido para 3,37%

## Decisões pendentes do gestor

- [ ] Validar posições vendidas com risco de squeeze médio ou alto: dLocal (médio).
- [ ] Confirmar a disponibilidade de aluguel para as 36 posições vendidas antes da execução.
- [ ] Revisar 169 notas da pesquisa com apoio de IA.
- [ ] Validar 34 restrições propostas pela pesquisa (sem venda / sem compra / teto de peso).
- [ ] Decidir sobre os hedges cambiais sugeridos: ARS, BRL, CLP, COP, MXN.
- [ ] Revisar observações/relaxamentos do otimizador.
- [ ] Obter co-assinatura independente de Risco/Compliance (quatro olhos): Nova posição vendida com risco de squeeze: dLocal (médio). Volatilidade ex-ante 3,64% fora de [4,00%, 6,00%].
- [ ] Aprovar ou rejeitar com justificativa — a decisão fica vinculada aos hashes dos dados de mercado, do mandato, da pesquisa e da proposta.

---

_Todos os números deste memo foram calculados e formatados por código a partir da proposta; textos de pesquisa são citados como fornecidos e rotulados pela origem._

---

_Hash da proposta (SHA-256): `df9d4d38ea75d0a77b4b39e3a8b84f17867114b4b7ce3cec930d3b144ae7f79f`_
