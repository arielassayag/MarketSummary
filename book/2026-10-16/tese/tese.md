# Tese de investimento — CDP — Cabra da Peste — semana de 2026-10-16

_Narrativa da gestão (IA) · decisão de 2026-10-16 · preços até 2026-10-15 · publicada em 2026-10-16T14:53:41.357588+00:00_

## Seleção quantitativa defensiva na América Latina, com neutralidade e disciplina de caixa

DADOS SIMULADOS: carteira simulada com preços reais e execução hipotética. A decisão reúne 38 compras e 35 vendas, com exposição bruta de 67,51%, líquida de +0,04% e beta previsto de 0,000. A volatilidade ex-ante é 3,52% ao ano; o alpha projetado é +2,29%, antes de custos de 0,43%, e +1,86% após custos. São estimativas do modelo, sem garantia de resultado.

A pesquisa permanece neutra e o PM se abstém de inclinações direcionais, preservando vetos por eventos e insuficiência de evidência. O código escolhe os sinais e os pesos. A decisão está aprovada para o leilão de fechamento de 2026-10-16; não equivale à efetivação. A tese descreve a carteira decidida, com 70 posições geradoras de alpha, 2 que também diversificam o risco e 1 destinada à neutralização.

## Números-chave

| Indicador | Valor |
|---|---|
| PL | US$ 1,00 mi |
| Posições (compras / vendas) | 38 / 35 |
| Exposição comprada / vendida | 33,78% / -33,74% |
| Exposição bruta / líquida | 67,51% / +0,04% |
| Beta previsto (limite) | 0,000 (±0,050) |
| Vol ex-ante (fatorial / específica) | 3,52% (0,65% / 3,46%) |
| Participação fatorial na variância | 8,09% |
| VaR 1 dia / ES 1 dia / VaR 1 semana | 0,52% / 0,59% / 1,15% |
| Alpha esperado / custo / líquido (a.a.) | +2,29% / 0,43% / +1,86% |
| Número efetivo de posições | 60,9 |
| Giro da semana | 31,17% |
| Dez maiores posições (% da exposição bruta) | 20,94% |

## Contexto e postura

A postura defensiva responde à incerteza monetária, cambial e de eventos. O material institucional da semana sustenta prudência nos Estados Unidos e Brasil, decisões dependentes dos dados no Chile, manutenção monetária no México e aperto na Colômbia. A estabilização argentina continua condicionada ao câmbio e à transmissão de caixa; a documentação peruana permanece incompleta. Essas leituras não originam apostas direcionais por país.

A janela eleitoral brasileira está ativa até 2026-10-26. A exposição à reação residual de referência é -0,089%, ante limite de 0,150%. A neutralização é estimada e pode mudar em estresse. Os preços de fechamento vão até 2026-10-15; a decisão também usou a barra intradiária provisória de 2026-10-16, registrada no retrato da análise. A pesquisa revisou notas já publicadas e fontes selecionadas; não houve releitura integral de todos os documentos primários. Ausência de notícia selecionada não comprova ausência de evento.

## Construção e dimensionamento

O universo elegível tem 231 emissores; 216 mantêm capacidade positiva após os controles e 73 compõem a carteira. O alpha residual combina sinais quantitativos depois da neutralização dos fatores. Postura neutra na pesquisa não altera o sinal residual escolhido pelo código; classificação do modelo de valuation não constitui ordem de compra ou venda.

O otimizador equilibra alpha, covariância, custos e limites. Há 44 posições no ótimo interior, 2 limitadas pelo risco por nome e 27 pelo teto da visão ou sentinela. A meta do mandato de 5,00% passa a 4,00% pela postura defensiva e a 3,64% após o ajuste pelo viés a priori de 1,10. O risco atingido, 3,52%, resulta dessas condições; não se força exposição para preencher a meta.

Os vetos preservam disciplina diante de squeeze, eventos próximos ou comprovação fundamental insuficiente. O encerramento das inclinações discricionárias anteriores deixa a seleção sob sinais quantitativos e restrições qualitativas. Contra a sombra quantitativa de 84 nomes, há 69 emissores na mesma ponta, sobreposição de 75,78% e active share de 24,22%. A diferença é efeito dos controles; não comprova superioridade futura.

**Cadeia do orçamento de volatilidade**

| Etapa | Valor | Leitura |
|---|---|---|
| Meta do mandato | 5,00% | Meta de volatilidade ex-ante anual do mandato. |
| Meta da postura | 4,00% | Postura defensiva (regime neutro). |
| Meta aplicada | 3,64% | Meta da postura dividida pelo viés a priori de 1,10: carteiras otimizadas subestimam o risco nas primeiras 26 semanas de histórico. |
| Piso da banda | 3,00% | Piso da banda do mandato: abaixo dele o orçamento de risco fica subutilizado. |
| Vol ex-ante atingida | 3,52% | Abaixo da meta aplicada. O alpha líquido de custos não sustentou a meta aplicada dentro dos limites da carteira. Neutralidades ativas no ótimo: setor Consumo discricionário, setor Financeiro, setor Utilidades públicas, estilo tamanho (size), estilo momentum, op_country:CL, op_country:LATAM, theme:state_owned, country_share:AR, giro semanal. 29 nomes no teto individual (peso, risco, liquidez, visão ou squeeze). |

**Funil:** universo elegível 231 → candidatos 216 → carteira 73 (38 compras, 35 vendas).

| Motivo de exclusão (um nome pode ter vários) | Nomes |
|---|---|
| Visão com teto de peso | 93 |
| Sem linha para venda a descoberto | 70 |
| Squeeze sem dados (teto de venda reduzido) | 44 |
| Risco de squeeze alto (venda vetada) | 38 |
| Liquidez abaixo do mínimo do mandato para venda | 17 |
| Visão ou exclusão: venda vetada | 10 |
| Risco de squeeze médio (teto de venda reduzido) | 9 |
| bloqueio_free_float | 5 |
| bloqueio_resultado | 5 |
| Visão ou exclusão: compra vetada | 3 |
| bloqueio_resultado_estimado | 2 |
| Liquidez abaixo do mínimo do mandato para compra | 2 |

## Temas da carteira

### Receita que precisa converter-se em caixa depois do reinvestimento (compras)

_Nomes:_ Grupo Aeroméxico, PRIO, Tenda, Cury, Suzano, Gerdau, Fortuna Mining. _Líquida_ +9,98%, _bruta_ 9,98%, participação no risco +20,82%, contribuição ao alpha +0,48%.

As compras selecionadas pelo código têm alpha residual positivo, sujeito à confirmação econômica. Em Aeroméxico, a rede e a oferta premium precisam remunerar frota e arrendamentos; em PRIO, produtividade e disponibilidade precisam converter-se em caixa atribuível. Nas incorporadoras, margem depende de custo por safra, repasses e crédito. Em produtores de materiais, realização e custo completo precisam financiar manutenção. Aeroméxico pesa +2,53% e PRIO +1,61%. A condição comum é geração de caixa depois das obrigações; crescimento de receita isolado não confirma a hipótese.

**Riscos:** Frota, manutenção, crédito habitacional, ciclo de preços e obras podem absorver caixa. O resultado de Aeroméxico em 2026-10-19 torna a revisão de disponibilidade e custo completo prioritária.

### Vendas quantitativas sujeitas a recuperação operacional e squeeze (vendas)

_Nomes:_ Patria Investments, Auren Energia, Lithium Argentina, Ultrapar, Brava Energia, Cemex, Usiminas, Embraer, FEMSA, Fleury, Nu Holdings, Orizon. _Líquida_ -15,00%, _bruta_ 15,00%, participação no risco +27,26%, contribuição ao alpha +0,54%.

A ponta vendida decorre de alpha residual negativo sob neutralização, sem promoção da pesquisa neutra a conclusão de deterioração fundamental. Pátria depende de captação e realização; Auren de margem contratada e caixa após integração; Lithium Argentina de recuperação industrial, financiamento e distribuição de caixa. Ultrapar, Brava, Cemex e Usiminas exigem disciplina de ciclo e capital. O peso de Pátria é -1,25% e o de Auren -1,25%. O teto da sentinela contém a exposição; não assegura disponibilidade de aluguel.

**Riscos:** Surpresas favoráveis de caixa, reorganização, aquisição ou mudança de controle podem reverter o sinal. Dados incompletos de controle, free float e aluguel exigem reconfirmação; o estresse dos maiores shorts é -1,87%.

### Intermediação e seguros: retorno depois das perdas e do capital (compras e vendas)

_Nomes:_ PagSeguro Digital, Banco Pine, BB Seguridade, Caixa Seguridade, Porto Seguro, Itaú Unibanco, PicPay (PicS N.V.), BBVA Argentina, Banco Macro, Grupo Cibest (ex-Bancolombia), Banco de Chile, Banco Santander-Chile, Banrisul. _Líquida_ +4,00%, _bruta_ 9,37%, participação no risco +11,86%, contribuição ao alpha +0,30%.

A seleção cruza compras e vendas em serviços financeiros. Margem, comissões ou lucro contábil precisam sobreviver a perdas por safra, sinistros, custo de captação e capital requerido. A comparação considera moeda, inflação e direitos nas subsidiárias; crescimento de carteira não comprova retorno incremental. Banco Macro, com +0,34%, combina geração de alpha com diversificação no modelo. A venda de Cibest, -0,84%, expressa sinal residual quantitativo, sujeito a revisão por margem recorrente e qualidade do crédito.

**Riscos:** Maturação tardia de perdas, títulos soberanos, indexação, reservas e bases contábeis distintas podem ocultar risco econômico. Resultados gerenciais precisam ser reconciliados ao capital e ao caixa.

### Infraestrutura: remuneração contratada exige execução e recebimento (compras e vendas)

_Nomes:_ ISA Energia Brasil, Axia Energia (ex-Eletrobras), Eneva, Alupar, Central Puerto, Transportadora de Gas del Sur, Equatorial, Energisa, Sanepar, Copasa, Sabesp, Cemig, Rumo. _Líquida_ -0,39%, _bruta_ 9,76%, participação no risco +7,60%, contribuição ao alpha +0,20%.

A carteira combina lados em energia, saneamento e transporte para selecionar retorno residual sem uma aposta setorial agregada. Disponibilidade, contratos e tarifa só criam valor com recebimento, investimento reconhecido e financiamento compatível. Cemig tem peso -0,40% e função de neutralização: sua venda não é uma afirmação de alpha fundamental negativo. Eneva depende do início econômico dos contratos e do caixa após expansão; Rumo exige confrontar preço, produtividade e obras por corredor.

**Riscos:** Indisponibilidade, regulação, hidrologia, penalidades e atrasos de obra podem consumir caixa. Controle estatal e revisões tarifárias introduzem eventos que os fatores históricos podem não captar.

### Clientes, distribuição e redes: crescimento condicionado ao retorno (compras e vendas)

_Nomes:_ Riachuelo (ex-Guararapes), Genomma Lab, Hypera, VTEX, MercadoLibre, Arcos Dorados, Allos, IRSA, América Móvil, Liberty Latin America, Grupo Aeroportuario del Sureste, Grupo Aeroportuario Centro Norte. _Líquida_ -0,15%, _bruta_ 10,39%, participação no risco +13,59%, contribuição ao alpha +0,34%.

Compras e vendas confrontam monetização com o custo de atender, reter e financiar clientes. A hipótese econômica de Riachuelo depende do varejo e da qualidade do crédito; Genomma e Hypera exigem demanda final e giro, além da venda ao canal. Plataformas, restaurantes, imóveis e concessões precisam remunerar reinvestimento. América Móvil, +0,31%, gera alpha e diversifica o risco no modelo; os resultados previstos para 2026-10-20 requerem conferência. A venda de ASUR é quantitativa e permanece exposta a surpresa de resultado.

**Riscos:** Estoque, promoções, crédito, competição e obrigações contratuais podem romper a conversão de receita em caixa. A agenda pública contém estimativas sujeitas a confirmação pelo emissor.

## Posições

| # | Emissor | Lado | Peso | Papel | Dimensionamento | Alpha | Alpha quant | Visões | Risco | Beta | Próx. resultado |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Grupo Aeroméxico | Compra | +2,53% | Geradora de alpha | Teto de risco por nome | +6,93% | +6,93% | 0,00% | +7,47% | +0,62 | 2026-10-19 |
| 2 | PRIO | Compra | +1,61% | Geradora de alpha | Ótimo interior (sem teto ativo) | +1,34% | +1,34% | 0,00% | +2,73% | +0,88 | 2026-11-04 |
| 3 | Riachuelo (ex-Guararapes) | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +10,12% | +10,12% | 0,00% | +3,98% | +1,62 | 2026-11-09 |
| 4 | Genomma Lab | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +6,82% | +6,82% | 0,00% | +1,36% | +0,36 | 2026-10-21 |
| 5 | Patria Investments | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -5,42% | -5,42% | 0,00% | +1,86% | +1,12 | 2026-11-11 |
| 6 | Tenda | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +11,40% | +11,40% | 0,00% | +4,69% | +1,52 | 2026-11-04 |
| 7 | Petrobras | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +5,93% | +5,93% | 0,00% | +0,89% | +1,09 | 2026-11-10 |
| 8 | Auren Energia | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -9,98% | -9,98% | 0,00% | +1,79% | +1,40 | n/d |
| 9 | Lithium Argentina | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -6,08% | -6,08% | 0,00% | +3,87% | +1,17 | 2026-11-10 |
| 10 | PagSeguro Digital | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +5,39% | +5,39% | 0,00% | +2,53% | +1,58 | 2026-11-16 |
| 11 | Suzano | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +3,59% | +3,59% | 0,00% | +1,71% | +0,83 | 2026-11-05 |
| 12 | Ultrapar | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -3,69% | -3,69% | 0,00% | +2,07% | +1,12 | 2026-11-11 |
| 13 | Brava Energia | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -4,03% | -4,03% | 0,00% | +3,13% | +1,11 | 2026-11-09 |
| 14 | Cemex | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -0,96% | -0,96% | 0,00% | +0,94% | +0,58 | 2026-10-26 |
| 15 | Usiminas | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -2,23% | -2,23% | 0,00% | +4,13% | +1,26 | n/d |
| 16 | SQM | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +2,59% | +2,59% | 0,00% | +1,37% | +0,57 | 2026-11-17 |
| 17 | Embraer | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -2,30% | -2,30% | 0,00% | +2,75% | +1,16 | 2026-11-10 |
| 18 | FEMSA | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -0,71% | -0,71% | 0,00% | +0,64% | +0,31 | 2026-10-28 |
| 19 | ISA Energia Brasil | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +3,02% | +3,02% | 0,00% | +1,31% | +1,28 | n/d |
| 20 | Fleury | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -4,07% | -4,07% | 0,00% | +2,56% | +1,33 | 2026-11-05 |
| 21 | BB Seguridade | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +2,51% | +2,51% | 0,00% | +1,10% | +1,04 | 2026-11-03 |
| 22 | Equatorial | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -2,54% | -2,54% | 0,00% | +0,88% | +1,42 | 2026-11-11 |
| 23 | Energisa | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -2,54% | -2,54% | 0,00% | +1,08% | +1,52 | n/d |
| 24 | Fortuna Mining | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +1,57% | +1,57% | 0,00% | +0,52% | +1,15 | 2026-11-04 |
| 25 | Hypera | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +4,24% | +4,24% | 0,00% | +2,12% | +1,37 | 2026-10-27 |
| 26 | Axia Energia (ex-Eletrobras) | Compra | +1,25% | Geradora de alpha | Teto da visão/sentinela | +1,23% | +1,23% | 0,00% | +1,40% | +1,36 | 2026-11-04 |
| 27 | Nu Holdings | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -0,81% | -0,81% | 0,00% | +1,79% | +1,46 | 2026-11-12 |
| 28 | Orizon | Venda | -1,25% | Geradora de alpha | Teto da visão/sentinela | -2,68% | -2,68% | 0,00% | +1,71% | +1,46 | n/d |
| 29 | YPF | Venda | -1,24% | Geradora de alpha | Ótimo interior (sem teto ativo) | -1,67% | -1,67% | 0,00% | +0,94% | +0,28 | 2026-10-28 |
| 30 | Cury | Compra | +1,16% | Geradora de alpha | Ótimo interior (sem teto ativo) | +5,40% | +5,40% | 0,00% | +2,72% | +1,48 | n/d |
| 31 | Adecoagro | Venda | -1,14% | Geradora de alpha | Ótimo interior (sem teto ativo) | -2,44% | -2,44% | 0,00% | +2,43% | +0,43 | 2026-11-11 |
| 32 | Allos | Venda | -1,11% | Geradora de alpha | Ótimo interior (sem teto ativo) | -0,19% | -0,19% | 0,00% | +0,96% | +1,37 | n/d |
| 33 | Arcos Dorados | Venda | -1,10% | Geradora de alpha | Ótimo interior (sem teto ativo) | -0,21% | -0,21% | 0,00% | +1,09% | +0,74 | 2026-11-18 |
| 34 | MercadoLibre | Venda | -1,06% | Geradora de alpha | Ótimo interior (sem teto ativo) | -0,32% | -0,32% | 0,00% | +0,84% | +1,13 | 2026-11-04 |
| 35 | Grupo Aeroportuario del Sureste | Venda | -1,05% | Geradora de alpha | Teto da visão/sentinela | -0,11% | -0,11% | 0,00% | +0,34% | +0,46 | 2026-10-22 |
| 36 | Vale | Compra | +1,04% | Geradora de alpha | Ótimo interior (sem teto ativo) | +0,58% | +0,58% | 0,00% | +0,70% | +1,26 | 2026-10-29 |
| 37 | Vibra Energia | Venda | -1,04% | Geradora de alpha | Ótimo interior (sem teto ativo) | -1,75% | -1,75% | 0,00% | +1,45% | +1,15 | 2026-11-04 |
| 38 | Sanepar | Venda | -1,04% | Geradora de alpha | Ótimo interior (sem teto ativo) | -1,61% | -1,61% | 0,00% | +1,45% | +1,40 | n/d |
| 39 | Banco Pine | Compra | +1,00% | Geradora de alpha | Ótimo interior (sem teto ativo) | +6,88% | +6,88% | 0,00% | +3,33% | +1,50 | n/d |
| 40 | Central Puerto | Compra | +0,98% | Geradora de alpha | Ótimo interior (sem teto ativo) | +4,10% | +4,10% | 0,00% | +0,36% | +0,77 | 2026-11-11 |
| 41 | Sigma Lithium | Venda | -0,96% | Geradora de alpha | Teto de risco por nome | -13,54% | -13,54% | 0,00% | +7,63% | +1,72 | 2026-11-13 |
| 42 | Gerdau | Compra | +0,93% | Geradora de alpha | Ótimo interior (sem teto ativo) | +1,46% | +1,46% | 0,00% | +0,98% | +1,17 | 2026-10-26 |
| 43 | Rede D'Or São Luiz | Venda | -0,91% | Geradora de alpha | Ótimo interior (sem teto ativo) | -0,74% | -0,74% | 0,00% | +0,74% | +1,36 | 2026-11-11 |
| 44 | Grupo Cibest (ex-Bancolombia) | Venda | -0,84% | Geradora de alpha | Ótimo interior (sem teto ativo) | -2,16% | -2,16% | 0,00% | +0,48% | +0,76 | 2026-11-09 |
| 45 | GeoPark | Compra | +0,81% | Geradora de alpha | Ótimo interior (sem teto ativo) | +3,62% | +3,62% | 0,00% | +0,99% | +0,56 | 2026-11-03 |
| 46 | Caixa Seguridade | Compra | +0,76% | Geradora de alpha | Ótimo interior (sem teto ativo) | +2,40% | +2,40% | 0,00% | +0,50% | +1,07 | 2026-11-09 |
| 47 | Vista Energy | Compra | +0,72% | Geradora de alpha | Ótimo interior (sem teto ativo) | +1,75% | +1,75% | 0,00% | +0,13% | +0,07 | 2026-10-28 |
| 48 | Banco de Chile | Venda | -0,72% | Geradora de alpha | Ótimo interior (sem teto ativo) | -1,22% | -1,22% | 0,00% | +0,14% | +0,73 | 2026-10-29 |
| 49 | Banco Santander-Chile | Venda | -0,72% | Geradora de alpha | Ótimo interior (sem teto ativo) | -1,24% | -1,24% | 0,00% | +0,13% | +0,72 | 2026-10-30 |
| 50 | Porto Seguro | Compra | +0,71% | Geradora de alpha | Ótimo interior (sem teto ativo) | +2,83% | +2,83% | 0,00% | +0,62% | +1,15 | 2026-11-05 |
| 51 | LATAM Airlines Group | Compra | +0,69% | Geradora de alpha | Ótimo interior (sem teto ativo) | +2,13% | +2,13% | 0,00% | +0,26% | +0,58 | 2026-11-03 |
| 52 | VTEX | Compra | +0,68% | Geradora de alpha | Ótimo interior (sem teto ativo) | +7,41% | +7,41% | 0,00% | +2,02% | +0,89 | 2026-11-05 |
| 53 | Liberty Latin America | Venda | -0,65% | Geradora de alpha | Ótimo interior (sem teto ativo) | -0,55% | -0,55% | 0,00% | +0,81% | +0,13 | 2026-11-04 |
| 54 | PicPay (PicS N.V.) | Compra | +0,64% | Geradora de alpha | Ótimo interior (sem teto ativo) | +6,25% | +6,25% | 0,00% | +2,62% | +2,13 | 2026-11-12 |
| 55 | Eneva | Compra | +0,51% | Geradora de alpha | Ótimo interior (sem teto ativo) | +0,09% | +0,09% | 0,00% | +0,19% | +1,27 | 2026-11-11 |
| 56 | BBVA Argentina | Compra | +0,48% | Geradora de alpha | Ótimo interior (sem teto ativo) | +2,42% | +2,42% | 0,00% | +0,13% | +1,05 | 2026-11-24 |
| 57 | Alupar | Compra | +0,47% | Geradora de alpha | Ótimo interior (sem teto ativo) | +2,74% | +2,74% | 0,00% | +0,19% | +1,30 | n/d |
| 58 | JBS N.V. | Compra | +0,46% | Geradora de alpha | Ótimo interior (sem teto ativo) | +2,68% | +2,68% | 0,00% | +0,37% | +1,00 | 2026-11-09 |
| 59 | Marcopolo | Compra | +0,45% | Geradora de alpha | Ótimo interior (sem teto ativo) | +4,92% | +4,92% | 0,00% | +0,52% | +1,37 | n/d |
| 60 | Copasa | Venda | -0,42% | Geradora de alpha | Ótimo interior (sem teto ativo) | -1,18% | -1,18% | 0,00% | +0,33% | +1,23 | 2026-11-09 |
| 61 | Klabin | Venda | -0,42% | Geradora de alpha | Ótimo interior (sem teto ativo) | -1,21% | -1,21% | 0,00% | +0,02% | +0,87 | n/d |
| 62 | Banrisul | Venda | -0,41% | Geradora de alpha | Ótimo interior (sem teto ativo) | -0,46% | -0,46% | 0,00% | +0,27% | +1,55 | n/d |
| 63 | Cemig | Venda | -0,40% | Hedge / neutralidade | Ótimo interior (sem teto ativo) | +0,14% | +0,14% | 0,00% | +0,14% | +1,24 | 2026-11-12 |
| 64 | IRSA | Compra | +0,39% | Geradora de alpha | Ótimo interior (sem teto ativo) | +2,28% | +2,28% | 0,00% | +0,06% | +0,69 | 2026-11-04 |
| 65 | Sabesp | Venda | -0,37% | Geradora de alpha | Ótimo interior (sem teto ativo) | -1,58% | -1,58% | 0,00% | +0,12% | +1,29 | 2026-11-05 |
| 66 | Rumo | Venda | -0,36% | Geradora de alpha | Ótimo interior (sem teto ativo) | -0,18% | -0,18% | 0,00% | +0,13% | +1,38 | 2026-11-11 |
| 67 | Banco Macro | Compra | +0,34% | Alpha que diversifica | Ótimo interior (sem teto ativo) | +1,21% | +1,21% | 0,00% | -0,01% | +0,93 | 2026-11-25 |
| 68 | São Martinho | Compra | +0,32% | Geradora de alpha | Ótimo interior (sem teto ativo) | +4,33% | +4,33% | 0,00% | +0,36% | +1,19 | 2026-11-09 |
| 69 | Ambev | Compra | +0,32% | Geradora de alpha | Ótimo interior (sem teto ativo) | +0,63% | +0,63% | 0,00% | +0,07% | +1,12 | 2026-10-29 |
| 70 | América Móvil | Compra | +0,31% | Alpha que diversifica | Ótimo interior (sem teto ativo) | +1,07% | +1,07% | 0,00% | -0,03% | +0,29 | 2026-10-20 |
| 71 | Grupo Aeroportuario Centro Norte | Venda | -0,30% | Geradora de alpha | Ótimo interior (sem teto ativo) | -0,21% | -0,21% | 0,00% | +0,04% | +0,47 | 2026-10-27 |
| 72 | Itaú Unibanco | Compra | +0,26% | Geradora de alpha | Ótimo interior (sem teto ativo) | +0,49% | +0,49% | 0,00% | +0,02% | +1,41 | 2026-11-03 |
| 73 | Transportadora de Gas del Sur | Compra | +0,21% | Geradora de alpha | Ótimo interior (sem teto ativo) | +1,53% | +1,53% | 0,00% | +0,01% | +0,56 | 2026-10-29 |

**Grupo Aeroméxico** — Compra quantitativa com peso de +2,53% e alpha residual de +6,93%. O dimensionamento é limitado pelo orçamento de risco por nome. A contribuição ao risco é +7,47%. A diligência econômica permanece condicional.
- Risco: Combustível, moeda, disponibilidade de aeronaves e demanda podem reduzir margem.
- Gatilho: Revisar no resultado de 2026-10-19 a realização por capacidade, combustível e caixa após manutenção, frota e arrendamentos.

**PRIO** — Compra quantitativa com peso de +1,61% e alpha residual de +1,34%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +2,73%. A diligência econômica permanece condicional.
- Risco: Paradas, integridade, declínio, exploração e preço do petróleo podem reduzir retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar disponibilidade, declínio e produtividade por campo, distinguindo participação econômica e volume total.

**Riachuelo (ex-Guararapes)** — Compra quantitativa com peso de +1,25% e alpha residual de +10,12%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +3,98%. A diligência econômica permanece condicional.
- Risco: Demanda, estoque e utilização industrial podem reduzir margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Vendas e margem por coleção, utilização industrial, estoque e retorno de reformas; carteira, safras, provisões e recebimento da Midway.

**Genomma Lab** — Compra quantitativa com peso de +1,25% e alpha residual de +6,82%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,36%. A diligência econômica permanece condicional.
- Risco: Demanda, promoção e distribuição podem impedir retorno das marcas.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar venda ao distribuidor e consumidor por categoria, margem após promoção e giro de recebíveis e estoques.

**Patria Investments** — Venda quantitativa com peso de -1,25% e alpha residual de -5,42%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,86%. A diligência econômica permanece condicional.
- Risco: Captação e realização de investimentos dependem do ciclo e da confiança dos clientes.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar captação, taxas efetivas, retenção e resultado realizado dos veículos.

**Tenda** — Compra quantitativa com peso de +1,25% e alpha residual de +11,40%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +4,69%. A diligência econômica permanece condicional.
- Risco: Inadimplência, crédito e custos podem limitar margem e repasse.
- Gatilho: Revisar com novos dados operacionais e de caixa. Conciliar custo e margem por safra, economias de entrega, distratos, repasses e preço após crédito direto.

**Petrobras** — Compra quantitativa com peso de +1,25% e alpha residual de +5,93%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +0,89%. A diligência econômica permanece condicional.
- Risco: Ciclo do petróleo, indisponibilidade, precificação doméstica, recebíveis públicos e obrigações de capital podem reduzir caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar disponibilidade das plataformas, declínio, novos poços e reposição de reservas.

**Auren Energia** — Venda quantitativa com peso de -1,25% e alpha residual de -9,98%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,79%. A diligência econômica permanece condicional.
- Risco: Hidrologia, vento, restrições e preços regionais podem elevar compras ou reduzir margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar geração e compras por fonte, obrigações contratadas, modulação, margem realizada e risco de contraparte.

**Lithium Argentina** — Venda quantitativa com peso de -1,25% e alpha residual de -6,08%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +3,87%. A diligência econômica permanece condicional.
- Risco: Preço do lítio, execução industrial e financiamento podem impedir retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar recuperação industrial, especificação do produto, preço realizado e caixa distribuído à companhia.

**PagSeguro Digital** — Compra quantitativa com peso de +1,25% e alpha residual de +5,39%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +2,53%. A diligência econômica permanece condicional.
- Risco: Competição, preço, fraude, perdas de crédito e captação podem reduzir contribuição.
- Gatilho: Revisar com novos dados operacionais e de caixa. Separar retenção, pagamentos, monetização, custo de atendimento e contribuição por cliente; acompanhar captação, perdas, crédito e capital.

**Suzano** — Compra quantitativa com peso de +1,25% e alpha residual de +3,59%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,71%. A diligência econômica permanece condicional.
- Risco: Ciclo de celulose, câmbio, insumos e logística podem comprimir caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar produtividade florestal, disponibilidade, preço realizado e custo completo por produto.

**Ultrapar** — Venda quantitativa com peso de -1,25% e alpha residual de -3,69%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +2,07%. A diligência econômica permanece condicional.
- Risco: Normalização de margens, energia, demanda e logística podem reduzir caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar volume, margem comparável, suprimento, mix e crédito por negócio.

**Brava Energia** — Venda quantitativa com peso de -1,25% e alpha residual de -4,03%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +3,13%. A diligência econômica permanece condicional.
- Risco: Paradas, integridade, preço do petróleo, proteção financeira e obrigações de aquisição podem absorver caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar disponibilidade, restrições, produção e custo por participação.

**Cemex** — Venda quantitativa com peso de -1,25% e alpha residual de -0,96%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +0,94%. A diligência econômica permanece condicional.
- Risco: Demanda e energia podem deteriorar rentabilidade enquanto reinvestimento continua necessário.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar volumes, preços, energia, economias recorrentes e manutenção por mercado.

**Usiminas** — Venda quantitativa com peso de -1,25% e alpha residual de -2,23%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +4,13%. A diligência econômica permanece condicional.
- Risco: Importações, insumos, demanda e logística podem reduzir margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar mix, preço realizado, utilização e consumo de insumos na siderurgia.

**SQM** — Compra quantitativa com peso de +1,25% e alpha residual de +2,59%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,37%. A diligência econômica permanece condicional.
- Risco: Preço mineral, recuperação industrial e investimento podem deteriorar caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar preço realizado, recuperação, especificação e caixa atribuível por operação e produto.

**Embraer** — Venda quantitativa com peso de -1,25% e alpha residual de -2,30%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +2,75%. A diligência econômica permanece condicional.
- Risco: Fornecedores, certificação, cancelamento e tarifas podem afetar entregas.
- Gatilho: Revisar com novos dados operacionais e de caixa. Carteira, entregas, mix, serviços e margem sem efeitos extraordinários.

**FEMSA** — Venda quantitativa com peso de -1,25% e alpha residual de -0,71%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +0,64%. A diligência econômica permanece condicional.
- Risco: Tráfego, competição, custos e maturação podem pressionar retorno por loja.
- Gatilho: Revisar com novos dados operacionais e de caixa. Separar tráfego, composição, margem e contribuição por loja e negócio; acompanhar maturação e capital das expansões.

**ISA Energia Brasil** — Compra quantitativa com peso de +1,25% e alpha residual de +3,02%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,31%. A diligência econômica permanece condicional.
- Risco: Obras, penalidades, inflação da dívida e revisão de remuneração podem absorver caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar disponibilidade, penalidades, recebimento por concessão e efeitos de revisão tarifária.

**Fleury** — Venda quantitativa com peso de -1,25% e alpha residual de -4,07%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +2,56%. A diligência econômica permanece condicional.
- Risco: Glosas, concentração em pagadores, custos de pessoal e integração podem limitar conversão.
- Gatilho: Revisar com novos dados de glosas, recebimento, utilização técnica e caixa após juros, arrendamentos e aquisições.

**BB Seguridade** — Compra quantitativa com peso de +1,25% e alpha residual de +2,51%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,10%. A diligência econômica permanece condicional.
- Risco: Crédito rural, sinistros, resgates e descasamentos de índices podem reduzir resultado.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar prêmios emitidos e ganhos, sinistralidade, comissões, despesas e resultado financeiro por negócio.

**Equatorial** — Venda quantitativa com peso de -1,25% e alpha residual de -2,54%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +0,88%. A diligência econômica permanece condicional.
- Risco: Regulação, perdas, crédito e restrição de geração podem pressionar margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Perdas, continuidade, tarifa e margem por distribuidora; geração e restrição de despacho.

**Energisa** — Venda quantitativa com peso de -1,25% e alpha residual de -2,54%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,08%. A diligência econômica permanece condicional.
- Risco: Qualidade, perdas, inadimplência e reconhecimento regulatório podem exigir investimento adicional.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar qualidade e perdas por distribuidora, energia faturada, inadimplência recorrente, custos e investimento reconhecido.

**Fortuna Mining** — Compra quantitativa com peso de +1,25% e alpha residual de +1,57%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +0,52%. A diligência econômica permanece condicional.
- Risco: Teor, recuperação, contratação de serviços, acesso operacional e custos locais podem deteriorar a geração de caixa.
- Gatilho: Revisar com teor, recuperação, custos por mina e caixa após manutenção; conferir licenças, financiamento e compromissos de fechamento.

**Hypera** — Compra quantitativa com peso de +1,25% e alpha residual de +4,24%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +2,12%. A diligência econômica permanece condicional.
- Risco: Concorrência, regulação, execução industrial e custo comercial podem limitar retorno.
- Gatilho: Revisar com demanda final, venda ao canal, estoques e recebíveis; conferir caixa após juros e investimento, dívida e realização tributária.

**Axia Energia (ex-Eletrobras)** — Compra quantitativa com peso de +1,25% e alpha residual de +1,23%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,40%. A diligência econômica permanece condicional.
- Risco: Hidrologia, preços, compras e indisponibilidade podem reduzir margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar energia disponível, vendas e compras por contrato, preços líquidos, risco hidrológico e margem realizada.

**Nu Holdings** — Venda quantitativa com peso de -1,25% e alpha residual de -0,81%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,79%. A diligência econômica permanece condicional.
- Risco: Maturação de safras e expansão em risco maior podem pressionar perdas.
- Gatilho: Revisar com novos dados operacionais e de caixa. Atividade, receita por cliente, margem depois de perdas e safras por país.

**Orizon** — Venda quantitativa com peso de -1,25% e alpha residual de -2,68%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +1,71%. A diligência econômica permanece condicional.
- Risco: Licenças, contratos públicos, integração e maturação energética podem limitar retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Volumes, tarifas, recebimento e margem por negócio; legado, pro forma e consolidado separados.

**YPF** — Venda quantitativa com peso de -1,24% e alpha residual de -1,67%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,94%. A diligência econômica permanece condicional.
- Risco: Preço, custo, transporte, financiamento e obrigações podem afetar retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Separar produção, preço realizado e produtividade de refino e comercialização.

**Cury** — Compra quantitativa com peso de +1,16% e alpha residual de +5,40%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +2,72%. A diligência econômica permanece condicional.
- Risco: Crédito, elegibilidade, renda e concentração regional podem limitar vendas e repasses.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar vendas, distratos, produção, custo por safra e repasses, preservando participação econômica.

**Adecoagro** — Venda quantitativa com peso de -1,14% e alpha residual de -2,44%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +2,43%. A diligência econômica permanece condicional.
- Risco: Clima, preços agrícolas, energia e execução industrial podem se combinar com necessidade de giro.
- Gatilho: Revisar com produtividade agrícola e industrial, mix de açúcar e etanol, disponibilidade de gás e caixa após manutenção e giro, respeitando restrições das subsidiárias.

**Allos** — Venda quantitativa com peso de -1,11% e alpha residual de -0,19%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,96%. A diligência econômica permanece condicional.
- Risco: Consumo, crédito de lojistas, vacância e juros podem limitar caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Conciliar participações, aluguel, ocupação, descontos e inadimplência por base comparável.

**Arcos Dorados** — Venda quantitativa com peso de -1,10% e alpha residual de -0,21%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +1,09%. A diligência econômica permanece condicional.
- Risco: Consumo, insumos e salários podem restringir acessibilidade e margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar visitas, vendas comparáveis e produtividade dos restaurantes.

**MercadoLibre** — Venda quantitativa com peso de -1,06% e alpha residual de -0,32%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,84%. A diligência econômica permanece condicional.
- Risco: Competição pode exigir subsídios persistentes.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar frequência, retenção, custo de entrega e monetização.

**Grupo Aeroportuario del Sureste** — Venda quantitativa com peso de -1,05% e alpha residual de -0,11%. O teto da visão ou sentinela limita o dimensionamento. A contribuição ao risco é +0,34%. A diligência econômica permanece condicional.
- Risco: Demanda turística, regras de concessão e compromissos de expansão podem reduzir o caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar tráfego e receita comercial em bases comparáveis, desembolsos de concessões, dívida por entidade e retorno das operações adquiridas.

**Vale** — Compra quantitativa com peso de +1,04% e alpha residual de +0,58%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,70%. A diligência econômica permanece condicional.
- Risco: Ciclo mineral, câmbio, transporte, paradas e qualidade podem reduzir margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar produção, disponibilidade, qualidade e preço realizado por mineral.

**Vibra Energia** — Venda quantitativa com peso de -1,04% e alpha residual de -1,75%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +1,45%. A diligência econômica permanece condicional.
- Risco: Normalização de margem, suprimento, crédito e energia podem reduzir caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Conciliar rede líquida, volume, mix, margem e crédito por segmento.

**Sanepar** — Venda quantitativa com peso de -1,04% e alpha residual de -1,61%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +1,45%. A diligência econômica permanece condicional.
- Risco: Regulação, recursos hídricos, perdas e obras podem reduzir retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Economias, volume, tarifa, perdas e qualidade de água e esgoto.

**Banco Pine** — Compra quantitativa com peso de +1,00% e alpha residual de +6,88%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +3,33%. A diligência econômica permanece condicional.
- Risco: Maturação de safras, empregadores, processos de cobrança e regras do consignado podem elevar perdas.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar perdas e cobrança por safra de consignado, margem depois de crédito, custo de captação e dependência de parceiros.

**Central Puerto** — Compra quantitativa com peso de +0,98% e alpha residual de +4,10%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,36%. A diligência econômica permanece condicional.
- Risco: Hidrologia, indisponibilidade, combustível, remuneração e atraso de recebíveis podem pressionar caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar geração, disponibilidade com e sem manutenção, mix de contratos e receitas efetivamente cobradas.

**Sigma Lithium** — Venda quantitativa com peso de -0,96% e alpha residual de -13,54%. O dimensionamento é limitado pelo orçamento de risco por nome. A contribuição ao risco é +7,63%. A diligência econômica permanece condicional.
- Risco: Ciclo de lítio, liquidez, obrigações ambientais e execução podem comprometer caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Conciliar qualidade, produção, estoque, embarque, recebimento e ajuste de preço.

**Gerdau** — Compra quantitativa com peso de +0,93% e alpha residual de +1,46%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,98%. A diligência econômica permanece condicional.
- Risco: Preços, custos de sucata e energia, concorrência externa e utilização das plantas podem reduzir margens de forma simultânea.
- Gatilho: Revisar com preços, volumes, sucata e energia por região; confrontar giro e investimentos com caixa disponível.

**Rede D'Or São Luiz** — Venda quantitativa com peso de -0,91% e alpha residual de -0,74%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,74%. A diligência econômica permanece condicional.
- Risco: Glosas, custo assistencial, reajustes insuficientes, expansão antes da maturação e dívida crescente podem reduzir caixa atribuível.
- Gatilho: Revisar com ocupação, receita recebida, glosas e sinistralidade; confrontar expansão, juros e caixa disponível por entidade.

**Grupo Cibest (ex-Bancolombia)** — Venda quantitativa com peso de -0,84% e alpha residual de -2,16%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,48%. A diligência econômica permanece condicional.
- Risco: Crédito, funding, mercados e câmbio podem reduzir retorno e exigir capital.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar margem de carteira e títulos separadamente, custo de depósitos, migração de risco e recuperações.

**GeoPark** — Compra quantitativa com peso de +0,81% e alpha residual de +3,62%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,99%. A diligência econômica permanece condicional.
- Risco: Petróleo, câmbio, declínio de reservatórios e execução podem reduzir caixa durante o pico de investimento.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar produção econômica atribuível, declínio, reservas, custo por poço e caixa depois de reposição.

**Caixa Seguridade** — Compra quantitativa com peso de +0,76% e alpha residual de +2,40%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,50%. A diligência econômica permanece condicional.
- Risco: Dependência da rede, parceiros, habitação e regras dos produtos pode reduzir receita.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar emissão e prêmio ganho por ramo, comissões, rede e marca, sinistralidade e combinado antes dos rendimentos.

**Vista Energy** — Compra quantitativa com peso de +0,72% e alpha residual de +1,75%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,13%. A diligência econômica permanece condicional.
- Risco: Declínio, custo de perfuração e gargalos de infraestrutura podem absorver o crescimento.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar produtividade e declínio por área, custo de desenvolvimento e transporte, realizações após hedges e frete.

**Banco de Chile** — Venda quantitativa com peso de -0,72% e alpha residual de -1,22%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,14%. A diligência econômica permanece condicional.
- Risco: Inflação, juros e gestão de balanço podem reduzir receitas antes de o crédito recuperar.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar depósitos transacionais, comissões e margem com clientes, separando inflação e tesouraria.

**Banco Santander-Chile** — Venda quantitativa com peso de -0,72% e alpha residual de -1,24%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,13%. A diligência econômica permanece condicional.
- Risco: Normalização da inflação, deterioração de crédito e despesas digitais podem reduzir o retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar margem com clientes, exposição indexada e custo de funding, preservando inflação e hedge.

**Porto Seguro** — Compra quantitativa com peso de +0,71% e alpha residual de +2,83%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,62%. A diligência econômica permanece condicional.
- Risco: Sinistros, crédito, custo médico e comissões podem absorver receitas.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar sinistralidade, combinado e resultado antes de finanças; no banco, perdas, garantias, safras e captação.

**LATAM Airlines Group** — Compra quantitativa com peso de +0,69% e alpha residual de +2,13%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,26%. A diligência econômica permanece condicional.
- Risco: Combustível, câmbio e capacidade concorrente podem reduzir margem antes de a companhia ajustar tarifas ou frota.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar receita e custo unitários na mesma base, ocupação, disponibilidade de frota e margem de carga.

**VTEX** — Compra quantitativa com peso de +0,68% e alpha residual de +7,41%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +2,02%. A diligência econômica permanece condicional.
- Risco: Consumo e pressão comercial podem reduzir monetização, enquanto desenvolvimento e suporte mantêm custos.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar retenção, expansão por cliente, custo de atendimento e retorno comercial.

**Liberty Latin America** — Venda quantitativa com peso de -0,65% e alpha residual de -0,55%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,81%. A diligência econômica permanece condicional.
- Risco: Concorrência, danos climáticos e reinvestimento podem pressionar margem e caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar retenção, qualidade da rede, preço líquido, custo de servir e investimento por operação.

**PicPay (PicS N.V.)** — Compra quantitativa com peso de +0,64% e alpha residual de +6,25%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +2,62%. A diligência econômica permanece condicional.
- Risco: Crédito parcialmente garantido, cartões e safras novas podem revelar perdas com atraso.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar safras, perda final, atraso e renegociação, sem somar medidas sobrepostas.

**Eneva** — Compra quantitativa com peso de +0,51% e alpha residual de +0,09%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,19%. A diligência econômica permanece condicional.
- Risco: Indisponibilidade, suprimento, reservas, restrições e crédito podem reduzir margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar disponibilidade e remuneração fixa por usina, despacho e margem variável depois de combustível e compras.

**BBVA Argentina** — Compra quantitativa com peso de +0,48% e alpha residual de +2,42%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,13%. A diligência econômica permanece condicional.
- Risco: Inflação, moeda, crédito e títulos afetam lucro e capital.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar margem real depois de perdas, custo de depósitos por moeda e retorno por segmento.

**Alupar** — Compra quantitativa com peso de +0,47% e alpha residual de +2,74%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,19%. A diligência econômica permanece condicional.
- Risco: Atrasos, penalidades, custo de obra e financiamento podem reduzir retorno das concessões.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar disponibilidade, parcela variável, receita regulatória, custos, licenças e energização por projeto.

**JBS N.V.** — Compra quantitativa com peso de +0,46% e alpha residual de +2,68%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,37%. A diligência econômica permanece condicional.
- Risco: Ciclo bovino, doença animal, comércio, frete e custos podem limitar margens.
- Gatilho: Revisar com novos dados operacionais e de caixa. Conciliar margens e custos por proteína, origens e base contábil.

**Marcopolo** — Compra quantitativa com peso de +0,45% e alpha residual de +4,92%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,52%. A diligência econômica permanece condicional.
- Risco: Calendário público, demanda, câmbio e mix podem reduzir margens.
- Gatilho: Revisar com novos dados operacionais e de caixa. Pedidos, entregas e mix por mercado; contratos públicos, exportações e operações externas separados.

**Copasa** — Venda quantitativa com peso de -0,42% e alpha residual de -1,18%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,33%. A diligência econômica permanece condicional.
- Risco: Tarifas, perdas, cobrança, qualidade e execução de obras podem pressionar caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar perdas, cobrança, qualidade, cobertura e prazo de obras por concessão; reconciliar remuneração regulatória, caixa após investimentos e financiamento.

**Klabin** — Venda quantitativa com peso de -0,42% e alpha residual de -1,21%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,02%. A diligência econômica permanece condicional.
- Risco: Câmbio, insumos, clima e demanda podem reduzir margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar mix e margem por celulose, papéis e embalagens, com eliminações internas.

**Banrisul** — Venda quantitativa com peso de -0,41% e alpha residual de -0,46%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,27%. A diligência econômica permanece condicional.
- Risco: Concentração regional, crédito, contingências e custo da folha podem reduzir retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar margem de clientes e tesouraria, captação, crédito problemático e recuperação em caixa.

**Cemig** — Venda de -0,40% destinada à neutralização dos fatores, apesar do alpha próprio de +0,14%. O otimizador a mantém pelo efeito conjunto sobre risco e restrições, sem teto ativo; não é uma tese de deterioração do negócio.
- Risco: Regulação, obras, hidrologia e financiamento podem pressionar caixa e distribuição.
- Gatilho: Revisar com novos dados operacionais e de caixa. Separar caixa, remuneração regulatória, qualidade e capital investido de distribuição, geração, transmissão e gás.

**IRSA** — Compra quantitativa com peso de +0,39% e alpha residual de +2,28%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,06%. A diligência econômica permanece condicional.
- Risco: Consumo, locatários, inflação, moeda e custos podem afetar renda e caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Separar renda, ocupação, recebimento e manutenção por segmento.

**Sabesp** — Venda quantitativa com peso de -0,37% e alpha residual de -1,58%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,12%. A diligência econômica permanece condicional.
- Risco: Prazos de obras, serviço, disponibilidade hídrica e cobrança podem afetar caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar entrega e operação das obras, perdas, qualidade, volume faturado e recebimento.

**Rumo** — Venda quantitativa com peso de -0,36% e alpha residual de -0,18%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,13%. A diligência econômica permanece condicional.
- Risco: Safra, clima, concorrência, preço e obras podem reduzir retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Volume, distância, preço e mix por corredor; manutenção, capacidade e produtividade.

**Banco Macro** — Compra quantitativa com peso de +0,34% e alpha residual de +1,21%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. Também diversifica o risco conjunto; sua participação na variância é -0,01%.
- Risco: Títulos soberanos, inflação e câmbio podem gerar volatilidade de lucro e capital.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar depósitos por origem, moeda e prazo, margem depois do risco e títulos por classificação contábil.

**São Martinho** — Compra quantitativa com peso de +0,32% e alpha residual de +4,33%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,36%. A diligência econômica permanece condicional.
- Risco: Clima, preço, compra de matéria-prima e comercialização podem limitar margem.
- Gatilho: Revisar com novos dados operacionais e de caixa. Monitorar moagem, produtividade, ATR, mix e vendas por produto no calendário da safra.

**Ambev** — Compra quantitativa com peso de +0,32% e alpha residual de +0,63%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,07%. A diligência econômica permanece condicional.
- Risco: Perda persistente de volumes ou aumento de custos comerciais e industriais pode reduzir caixa mesmo com receita sustentada por preço.
- Gatilho: Revisar com volume, preço, mix e despesas por operação; confrontar margem recorrente e caixa após investimento com a monetização das marcas.

**América Móvil** — Compra quantitativa com peso de +0,31% e alpha residual de +1,07%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. Também diversifica o risco conjunto; sua participação na variância é -0,03%.
- Risco: Concorrência, exigências regulatórias e renovação de rede podem consumir a receita adicional.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar receita de serviços, retenção, investimento e caixa por operação em bases comparáveis.

**Grupo Aeroportuario Centro Norte** — Venda quantitativa com peso de -0,30% e alpha residual de -0,21%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,04%. A diligência econômica permanece condicional.
- Risco: Demanda e regras tarifárias podem restringir caixa enquanto compromissos continuam exigíveis.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar tráfego, receita comercial por passageiro, direitos de uso e custos por aeroporto.

**Itaú Unibanco** — Compra quantitativa com peso de +0,26% e alpha residual de +0,49%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,02%. A diligência econômica permanece condicional.
- Risco: Crédito e menor crescimento de serviços podem pressionar retorno.
- Gatilho: Revisar com novos dados operacionais e de caixa. Margem depois de perdas, serviços e seguros, inadimplência, renegociação e eficiência.

**Transportadora de Gas del Sur** — Compra quantitativa com peso de +0,21% e alpha residual de +1,53%. O peso resulta do equilíbrio entre alpha, custos e covariâncias, sem teto ativo. A contribuição ao risco é +0,01%. A diligência econômica permanece condicional.
- Risco: Remuneração regulada, preços de líquidos, disponibilidade e custo de energia podem deteriorar caixa.
- Gatilho: Revisar com novos dados operacionais e de caixa. Acompanhar capacidade contratada, disponibilidade, tarifas reais, composição de líquidos e custos energéticos.

## Exposições

A exposição bruta é 67,51% e a líquida +0,04%. Por país, as exposições líquidas incluem Brasil +0,34%, México +0,23%, Argentina -0,50% e Chile +0,50%. As restrições admitem pequenos resíduos; não equivalem a imunidade econômica. Em setores, consumo discricionário e financeiro ficam em +1,50% e +1,50%, enquanto utilidades fica em -1,50%.

Momentum registra -0,050, tamanho -0,050 e liquidez -0,048. As cargas em petróleo, cobre e ouro são -0,002, 0,000 e -0,002. O tema estatais está em -1,00%, ante limite de 1,00%. A moeda de cotação não esgota a exposição cambial econômica do negócio.

| País | Compra | Venda | Net | Gross | Limite |
|---|---|---|---|---|---|
| Brasil | 22,57% | -22,23% | +0,34% | 44,80% | 2,00% |
| México | 4,09% | -3,85% | +0,23% | 7,94% | 2,00% |
| Argentina | 3,13% | -3,63% | -0,50% | 6,75% | 2,00% |
| Chile | 1,94% | -1,44% | +0,50% | 3,38% | 2,00% |
| Regional (América Latina) | 1,25% | -1,75% | -0,50% | 3,00% | 2,00% |
| Colômbia | 0,81% | -0,84% | -0,03% | 1,64% | 2,00% |

| Setor | Compra | Venda | Net | Gross | Limite |
|---|---|---|---|---|---|
| Financeiro | 6,69% | -5,19% | +1,50% | 11,87% | 2,50% |
| Materiais | 5,72% | -5,13% | +0,59% | 10,85% | 2,50% |
| Utilidades públicas | 4,47% | -5,97% | -1,50% | 10,44% | 2,50% |
| Energia | 4,60% | -4,78% | -0,17% | 9,38% | 2,50% |
| Industriais | 3,67% | -4,21% | -0,54% | 7,88% | 2,50% |
| Consumo discricionário | 3,66% | -2,16% | +1,50% | 5,82% | 2,50% |
| Consumo básico | 2,35% | -2,39% | -0,04% | 4,74% | 2,50% |
| Saúde | 1,25% | -2,16% | -0,91% | 3,41% | 2,50% |
| Imobiliário | 0,39% | -1,11% | -0,73% | 1,50% | 2,50% |
| Comunicações | 0,31% | -0,65% | -0,34% | 0,95% | 2,50% |
| Tecnologia | 0,68% | 0,00% | +0,68% | 0,68% | 2,50% |

| Estilo | Exposição (z × NAV) | Limite |
|---|---|---|
| Momentum | -0,050 | 0,100 |
| Tamanho (size) | -0,050 | 0,100 |
| Liquidez | -0,048 | 0,100 |
| Vol residual | +0,041 | 0,100 |
| Valor (value) | -0,035 | 0,100 |
| Sensibilidade cambial | +0,027 | 0,100 |
| Beta de mercado | -0,001 | 0,100 |

| Commodity | Σ w·β | P&L para alta de 10% | Limite |
|---|---|---|---|
| Petróleo | -0,002 | -0,02% | 0,030 |
| Cobre | 0,000 | 0,00% | 0,030 |
| Ouro | -0,002 | -0,02% | 0,030 |

| Tema / evento | Exposição | Limite |
|---|---|---|
| Estatais | -1,00% | 1,00% |
| Eleição Brasil 2026 (2º turno 25/out) | -0,089% | 0,150% |

| Moeda | Exposição econômica (USD) | % do NAV |
|---|---|---|
| CLP | +US$ 5.020 | +0,50% |
| ARS | -US$ 5.019 | -0,50% |
| BRL | +US$ 3.390 | +0,34% |
| MXN | +US$ 2.330 | +0,23% |
| COP | -US$ 304 | -0,03% |

## Sensibilidade de mercado

O beta previsto é 0,000. No choque de mercado definido no FactBook, a resposta linear é 0,00%, equivalente a +US$ 32. Reprecificar os pesos atuais no histórico produz beta contra ILF de +0,003 em 449 pregões. Trata-se de diagnóstico retrospectivo de pesos constantes, com preenchimento de retornos ausentes pelo modelo; não é o histórico realizado do fundo.

A neutralidade depende de covariâncias e exposições estimadas, que podem romper em evento. Commodities são representadas por petróleo, cobre e ouro; outras matérias-primas não têm proxy específica. Juros não constituem fator próprio no modelo. Não se infere ausência de risco de taxa, financiamento ou curva a partir do beta baixo. A sensibilidade ao sol peruano está indisponível e permanece sem estimativa.

| Referência | Base | Beta | Correlação | Choque | P&L | P&L (USD) | Observações |
|---|---|---|---|---|---|---|---|
| Mercado LatAm (beta do modelo) | modelo | 0,000 | n/d | -10% | 0,00% | +US$ 32 | n/d |
| América Latina (ILF) | histórico | +0,003 | +0,02 | -10% | -0,03% | -US$ 256 | 449 |
| Brasil (EWZ) | histórico | +0,002 | +0,02 | -10% | -0,02% | -US$ 167 | 449 |
| México (EWW) | histórico | +0,004 | +0,04 | -10% | -0,04% | -US$ 412 | 449 |
| EUA (SPY) | histórico | +0,004 | +0,03 | -10% | -0,04% | -US$ 432 | 449 |
| Emergentes (EEM) | histórico | +0,004 | +0,04 | -10% | -0,04% | -US$ 407 | 448 |
| Dólar global (DXY) | histórico | -0,005 | -0,01 | +5% | -0,03% | -US$ 271 | 448 |
| Real (BRL) | histórico | -0,008 | -0,04 | -10% | +0,08% | +US$ 801 | 449 |
| Peso mexicano (MXN) | histórico | +0,012 | +0,05 | -10% | -0,12% | -US$ 1.199 | 449 |
| Peso chileno (CLP) | histórico | +0,010 | +0,05 | -10% | -0,10% | -US$ 981 | 449 |
| Peso colombiano (COP) | histórico | +0,003 | +0,02 | -10% | -0,03% | -US$ 340 | 449 |
| Peso argentino (ARS) | histórico | -0,002 | -0,01 | -10% | +0,02% | +US$ 173 | 449 |
| Petróleo Brent | histórico | 0,000 | -0,01 | -10% | 0,00% | +US$ 36 | 448 |
| Cobre | histórico | +0,003 | +0,04 | -10% | -0,03% | -US$ 317 | 448 |
| Ouro | histórico | +0,001 | +0,01 | -10% | -0,01% | -US$ 126 | 448 |

Vol realizada da carteira atual reprecificada: 2,59% (449 pregões, 2024-11-08 a 2026-10-16).

## Volatilidade e orçamento de risco

A volatilidade ex-ante é 3,52%, composta por risco específico de 3,46% e fatorial de 0,65%; esses componentes não se somam aritmeticamente. O modelo base, vinculante para a concentração, atribui 91,91% da variância ao risco idiossincrático; o modelo de decisão indica 95,12%. A meta é 90,00% e o piso 85,00%.

O número efetivo de posições é 60,9. A escala de um desvio-padrão semanal é 0,50%, ou US$ 4.982. VaR diário de 0,52% e expected shortfall de 0,59% são estimativas condicionais, sem limite garantido de perda. A banda de volatilidade é 3,00% a 7,00%. Concentração específica pode continuar alta mesmo com muitas posições e beta próximo da neutralidade.

| Horizonte | Um desvio-padrão (%) | Um desvio-padrão (USD) |
|---|---|---|
| Um dia | 0,22% | US$ 2.228 |
| Uma semana (5 pregões) | 0,50% | US$ 4.982 |
| Um mês (21 pregões) | 1,02% | US$ 10.211 |

| Grupo | Participação na variância |
|---|---|
| Mercado LatAm | 0,00% |
| Países | +0,71% |
| Setores | +2,72% |
| Estilos | +4,18% |
| Macro (commodities e dólar) | +0,48% |
| Específico (seleção de ações) | +91,91% |

| Fator | Participação na variância |
|---|---|
| Estilo — Momentum | +1,52% |
| Estilo — Liquidez | +1,09% |
| Estilo — Vol residual | +0,97% |
| Setor — Tecnologia | +0,88% |
| Setor — Consumo discricionário | +0,70% |
| Estilo — Tamanho (size) | +0,42% |
| Setor — Saúde | +0,38% |
| País — Argentina | +0,35% |
| Setor — Utilidades públicas | +0,35% |
| País — Regional (América Latina) | +0,31% |
| Macro — GC=F | +0,28% |
| Estilo — Valor (value) | +0,25% |

## Estresse

| Cenário | Tipo | P&L | P&L (USD) | Observação |
|---|---|---|---|---|
| Quebra: 5 maiores longs -30% | Idiossincrático | -2,37% | -US$ 23.759 | Choque específico simultâneo nos maiores nomes da ponta: Grupo Aeroméxico, PRIO, Riachuelo (ex-Guararapes), Genomma Lab, Tenda. |
| Squeeze: 5 maiores shorts +30% | Idiossincrático | -1,87% | -US$ 18.827 | Choque específico simultâneo nos maiores nomes da ponta: Patria Investments, Auren Energia, Lithium Argentina, Ultrapar, Brava Energia. |
| Tarifas dos EUA (abr/2025) | Histórico | -0,25% | -US$ 2.502 | Réplica estática de 2025-04-02 a 2025-04-08. Maior perda individual: PRIO (-0,29 p.p.). |
| Gap Argentina +41% | Gap de país | -0,20% | -US$ 2.058 | Gap simultâneo de todos os emissores do país (exposição líquida × choque). |
| Eleição México jun/2024 | Histórico | -0,12% | -US$ 1.207 | Réplica estática de 2024-05-31 a 2024-06-12. Maior perda individual: Grupo Aeroméxico (-0,31 p.p.). |
| Gap Chile −15% | Gap de país | -0,07% | -US$ 753 | Gap simultâneo de todos os emissores do país (exposição líquida × choque). |
| Brasil -15% | Hipotético | -0,05% | -US$ 538 | Choque fatorial com propagação condicional pela covariância do modelo. |
| Commodities -15% | Hipotético | -0,04% | -US$ 433 | Choque fatorial com propagação condicional pela covariância do modelo. |
| Gap Brasil −10% | Gap de país | -0,03% | -US$ 339 | Gap simultâneo de todos os emissores do país (exposição líquida × choque). |
| Gap México −13% | Gap de país | -0,03% | -US$ 303 | Gap simultâneo de todos os emissores do país (exposição líquida × choque). |
| Gap Peru −10% | Gap de país | 0,00% | US$ 0 | Gap simultâneo de todos os emissores do país (exposição líquida × choque). |
| Gap Colômbia −11% | Gap de país | 0,00% | +US$ 33 | Gap simultâneo de todos os emissores do país (exposição líquida × choque). |
| Mercado LatAm -20% | Hipotético | +0,01% | +US$ 136 | Choque fatorial com propagação condicional pela covariância do modelo. |
| Gap Brasil +10% | Gap de país | +0,03% | +US$ 339 | Gap simultâneo de todos os emissores do país (exposição líquida × choque). |
| Eleição Brasil out/2022 (2º turno) | Histórico | +0,04% | +US$ 415 | Réplica estática de 2022-10-28 a 2022-11-11. Maior ganho individual: Fortuna Mining (0,30 p.p.). |
| México -15% | Hipotético | +0,12% | +US$ 1.225 | Choque fatorial com propagação condicional pela covariância do modelo. |
| Taper/estresse jun/2022 | Histórico | +0,23% | +US$ 2.354 | Réplica estática de 2022-06-08 a 2022-07-14. Maior ganho individual: Brava Energia (0,55 p.p.). |
| Gap Argentina −56% | Gap de país | +0,28% | +US$ 2.811 | Gap simultâneo de todos os emissores do país (exposição líquida × choque). |
| Momentum crash -3σ | Hipotético | +0,29% | +US$ 2.900 | Choque fatorial com propagação condicional pela covariância do modelo. |
| Choque fiscal BRL dez/2024 | Histórico | +0,82% | +US$ 8.251 | Réplica estática de 2024-11-26 a 2024-12-18. Maior ganho individual: Nu Holdings (0,32 p.p.). |
| COVID crash (fev-mar/2020) | Histórico | n/d | n/d | Réplica estática de 2020-02-19 a 2020-03-23. Sem dados: sem retorno observado nem implícito pelo modelo para Rede D'Or São Luiz, VTEX. |
| Estallido social Chile (out-nov/2019) | Histórico | n/d | n/d | Réplica estática de 2019-10-17 a 2019-11-12. Sem dados: sem retorno observado nem implícito pelo modelo para Grupo Aeroméxico, Patria Investments, Auren Energia, Brava Energia, Nu Holdings, Orizon, Cury, Rede D'Or São Luiz, Caixa Seguridade, VTEX, PicPay (PicS N.V.), JBS N.V.. |
| Joesley Day (mai/2017) | Histórico | n/d | n/d | Réplica estática de 2017-05-17 a 2017-05-18. Sem dados: o histórico de preços não cobre a janela. |
| PASO Argentina 2019 | Histórico | n/d | n/d | Réplica estática de 2019-08-09 a 2019-08-12. Sem dados: sem retorno observado nem implícito pelo modelo para Grupo Aeroméxico, Patria Investments, Auren Energia, Brava Energia, Nu Holdings, Orizon, Cury, Rede D'Or São Luiz, Caixa Seguridade, VTEX, PicPay (PicS N.V.), JBS N.V.. |
| Taper tantrum (mai-jun/2013) | Histórico | n/d | n/d | Réplica estática de 2013-05-22 a 2013-06-24. Sem dados: o histórico de preços não cobre a janela. |

## Liquidez

| Ponta | Liquidável em 1 dia | Em 3 dias | Máximo de dias |
|---|---|---|---|
| Compras | 100,00% | 100,00% | 0,0 dias |
| Vendas | 100,00% | 100,00% | 0,0 dias |

## Carteira quantitativa de referência

| Indicador | Valor |
|---|---|
| Alpha esperado da referência | +3,35% |
| Vol ex-ante da referência | 4,55% |
| Posições da referência | 84 |
| Nomes em comum (mesma ponta) | 69 |
| Sobreposição de pesos | 75,78% |
| Active share | 24,22% |

## Riscos

- Quebra simultânea dos maiores longs: -2,37%. Squeeze simultâneo dos maiores shorts: -1,87%. São cenários determinísticos, sem probabilidades atribuídas.
- Valor, qualidade e revisões de analistas usam retratos atuais, sem validação histórica point-in-time equivalente à dos sinais de preço. O alpha estimado pode refletir viés de dados e erros de modelo.
- A consulta histórica de aluguel da B3 teve falhas e preservou o último arquivo disponível. SEC apresentou recusas de acesso. Ausências de calendário, controle e free float permanecem lacunas, sem preenchimento por inferência.
- O volume ordinário do modelo indica liquidação em prazo curto, mas não comprova disponibilidade de aluguel, preço executável, ausência de gap ou saída durante evento.
- Os resultados próximos de Aeroméxico, América Móvil, Genomma e ASUR podem produzir saltos antes de nova otimização. Algumas datas da agenda são estimadas e exigem confirmação.
- Moedas, eleição, controle estatal, commodities e curvas de juros podem gerar perdas por correlações novas, apesar das neutralidades estimadas.

## Pré-mortem

A carteira pode perder se os sinais residuais anteciparem uma conversão de caixa que não ocorre nas compras e penalizarem negócios cujos resultados surpreendem positivamente nas vendas. Eventos de resultado, reorganização ou restrição de aluguel podem tornar a correlação histórica pouco útil. A eleição pode ampliar o risco comum entre empresas mesmo com a exposição residual limitada. Custos de 0,43% podem consumir o alpha de +2,29%, sobretudo se o giro necessário aumentar ou a oferta de aluguel diminuir. Os cenários dos maiores longs e shorts, -2,37% e -1,87%, não esgotam as perdas possíveis. Neutralidade estimada não impede choque agregado. O erro a evitar é tratar uma classificação quantitativa, uma estimativa de calendário ou crédito contratado como comprovação de caixa ou execução.

## Gatilhos de revisão

- Reavaliar a carteira se a volatilidade sair da banda de 3,00% a 7,00% ou se o orçamento de concentração específico violar os gates do código.
- Reavaliar posições quando novos documentos alterarem caixa atribuível, capital requerido, direitos por instrumento ou premissas dos sinais.
- Rever vendas diante de alteração de controle, recompra, oferta pública, custo ou disponibilidade de aluguel; qualquer evento HARD segue o tratamento determinístico.
- Conferir a reação de Aeroméxico ao resultado de 2026-10-19 e as divulgações previstas de América Móvil, Genomma e ASUR antes de tratar o calendário como realizado.
- Monitorar a janela eleitoral até 2026-10-26 e aplicar os gates se a exposição ao evento exceder o limite de 0,150%.

## O que monitorar

No fechamento de 2026-10-16, a rotina diária deve efetivar a execução hipotética e registrar preços, custos e eventual recusa; esta tese não antecipa essa confirmação. Aeroméxico divulga resultado após o fechamento de 2026-10-19, com chamada em 2026-10-20. A agenda aponta América Móvil em 2026-10-20, Genomma em 2026-10-21 e ASUR em 2026-10-22, sujeitas à confirmação de cada emissor. A eleição brasileira está prevista para 2026-10-25. Depois, acompanhar Cemex e Gerdau em 2026-10-26, Hypera e OMA em 2026-10-27 e os eventos subsequentes do calendário arquivado.

Acompanhar diariamente covariâncias, beta, risco específico, custos, aluguel e notícias de controle. Na divulgação de resultados, reconciliar margem operacional com giro, manutenção, financiamento e caixa atribuível. A avaliação prospectiva desta decisão só amadurece em 2026-10-23; não preencher resultados futuros. As justificativas individuais abaixo distinguem a seleção quantitativa da diligência econômica ainda condicional.

| Data | Tipo | Evento |
|---|---|---|
| 2026-10-19 | Resultado | Divulgação de resultados: Grupo Aeroméxico |
| 2026-10-19 | Catalisador | Grupo Aeroméxico: Resultado anunciado para depois do fechamento; revisar caixa após contratos de frota e monetização da rede. |
| 2026-10-20 | Resultado | Divulgação de resultados: América Móvil |
| 2026-10-21 | Resultado | Divulgação de resultados: Genomma Lab |
| 2026-10-22 | Resultado | Divulgação de resultados: Grupo Aeroportuario del Sureste |
| 2026-10-25 | Macro | Brasil: Eleição brasileira prevista na janela de evento do mandato. |
| 2026-10-26 | Evento | Fim da janela de evento: Eleição Brasil 2026 (2º turno 25/out) |
| 2026-10-26 | Resultado | Divulgação de resultados: Cemex, Gerdau |
| 2026-10-27 | Resultado | Divulgação de resultados: Grupo Aeroportuario Centro Norte, Hypera |
| 2026-10-28 | Resultado | Divulgação de resultados: FEMSA, Vista Energy, YPF |
| 2026-10-28 | Catalisador | Klabin: Informações trimestrais programadas; rever custo completo, giro, caixa após manutenção e dívida nas bases de moeda. |
| 2026-10-28 | Catalisador | Vista Energy: Divulgação de resultados anunciada pela companhia; revisar produtividade, dívida e caixa após expansão. |
| 2026-10-29 | Resultado | Divulgação de resultados: Ambev, Banco de Chile, Transportadora de Gas del Sur, Vale |
| 2026-10-30 | Resultado | Divulgação de resultados: Banco Santander-Chile |
| 2026-10-30 | Catalisador | Banco Santander-Chile: Disponibilização de demonstrações trimestrais prevista no calendário oficial; revisar inflação, crédito e capital. |
| 2026-11-03 | Resultado | Divulgação de resultados: BB Seguridade, GeoPark, Itaú Unibanco, LATAM Airlines Group |
| 2026-11-03 | Catalisador | BB Seguridade: Divulgação programada de resultados; conciliar bases contábeis, subscrição, reservas e comissões. |
| 2026-11-03 | Catalisador | ISA Energia Brasil: Divulgação programada de resultados; rever novo perímetro, emissão, recebimentos e obrigações de financiamento. |
| 2026-11-04 | Resultado | Divulgação de resultados: Axia Energia (ex-Eletrobras), Fortuna Mining, IRSA, Liberty Latin America, MercadoLibre, PRIO, Tenda, Vibra Energia |
| 2026-11-04 | Catalisador | PRIO: Divulgação programada de resultados; rever produção atribuível, vendas, custo completo, dívida e caixa depois do investimento. |
| 2026-11-05 | Resultado | Divulgação de resultados: Fleury, Porto Seguro, Sabesp, Suzano, VTEX |
| 2026-11-05 | Catalisador | Catalisadores da pesquisa: Alupar, Porto Seguro, Suzano |
| 2026-11-09 | Resultado | Divulgação de resultados: Brava Energia, Caixa Seguridade, Copasa, Grupo Cibest (ex-Bancolombia), JBS N.V., Riachuelo (ex-Guararapes), São Martinho |
| 2026-11-10 | Resultado | Divulgação de resultados: Embraer, Lithium Argentina, Petrobras |
| 2026-11-10 | Catalisador | Auren Energia: Divulgação programada de resultados; rever margem realizada, integração, restrições e serviço da dívida. |
| 2026-11-10 | Catalisador | Lithium Argentina: Divulgação e discussão de resultado anunciadas pelo emissor; revisar caixa, financiamento e desenvolvimento sem antecipar o resultado. |
| 2026-11-11 | Resultado | Divulgação de resultados: Adecoagro, Central Puerto, Eneva, Equatorial, Patria Investments, Rede D'Or São Luiz, Rumo, Ultrapar |
| 2026-11-11 | Catalisador | Eneva: Divulgação programada de resultados; rever contratos iniciados, novo perímetro, disponibilidade, expansão e caixa. |
| 2026-11-12 | Resultado | Divulgação de resultados: Cemig, Nu Holdings, PicPay (PicS N.V.) |
| 2026-11-12 | Catalisador | Klabin: Parcela de dividendos previamente declarada e programada, sujeita aos direitos e condições da deliberação. |
| 2026-11-13 | Resultado | Divulgação de resultados: Sigma Lithium |
| 2026-11-16 | Resultado | Divulgação de resultados: PagSeguro Digital |
| 2026-11-17 | Resultado | Divulgação de resultados: SQM |
| 2026-11-17 | Catalisador | Caixa Seguridade: Pagamento de dividendos programado no aviso específico, sujeito à posição acionária e regras informadas; conferir efetivo crédito. |
| 2026-11-18 | Resultado | Divulgação de resultados: Arcos Dorados |
| 2026-11-24 | Resultado | Divulgação de resultados: BBVA Argentina |
| 2026-11-25 | Resultado | Divulgação de resultados: Banco Macro |

## Notas metodológicas

- Números recalculados com os pesos aprovados, sem reotimizar; conferem com o risco registrado na decisão.
- Sensibilidade realizada não calculada (série ausente ou curta): Sol peruano (PEN).
- Janela de evento ativa (Eleição Brasil 2026 (2º turno 25/out)): volatilidade do país Brasil multiplicada por 1,50 no modelo de risco.
- Sinais com retrato atual dos dados (não point-in-time): valor, qualidade, revisões de analistas; o alpha desses sinais não tem validação histórica equivalente à dos sinais de preço.
- Cobertura de pesquisa fundamental: 73 de 73 nomes; os demais são mantidos pelo modelo quantitativo e pelas restrições da carteira.
- Commodities medidas: petróleo, cobre, ouro; demais commodities não têm proxy no modelo.
- Sensibilidade a juros não é modelada: o modelo de risco não tem fator de juros (curva local ou Treasuries).
- Beta do modelo medido contra a carteira de mercado LatAm ponderada por valor de mercado; betas realizados reprecificam os pesos atuais sobre o histórico (retornos ausentes completados pelo modelo).
- Dias para liquidar com a participação de cada ponta no volume médio: compras 20%, vendas 15%.
- Preços de fechamento até 2026-10-15; a decisão usou também a barra intradiária provisória de 2026-10-16 (cotações do momento da análise).

## Aviso

Natureza: carteira simulada com preços reais — execução hipotética no leilão de fechamento, com custos estimados pelo modelo; não representa resultado de fundo real nem oferta ou recomendação de investimento. Todos os números foram calculados por código a partir dos dados da semana; a narrativa apenas os cita.
