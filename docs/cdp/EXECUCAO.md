# Execução no leilão de fechamento — cronograma, prazo, capacidade e custos

Este documento descreve como a carteira do CDP é montada e rebalanceada: em que dia, até que
horário a decisão é tomada, como cada ordem é executada no leilão de fechamento e como a
liquidez limita o tamanho de cada negociação. Todos os números citados são calculados por
código (`src/cdp/calendar.py`, `src/cdp/portfolio/execucao.py`, `src/cdp/portfolio/costs.py`,
`src/cdp/workflow/daily.py`) e os parâmetros estão no mandato (`configs/cdp/fund.yaml`, seções
`fund` e `execution`).

## 1. Regra de rebalanceamento

- **Dia de montagem:** o último pregão da semana na NYSE — sexta-feira ou, com feriado nos EUA, o
  pregão anterior (ex.: quinta-feira 25/03/2027, véspera da Sexta-Feira Santa). A data de início
  do mandato (`fund.inception_date`, 09/10/2026) é sempre dia de montagem: a carteira inaugural.
- **Decisão antes do fechamento:** a pesquisa começa às 11h00 de Brasília do dia de montagem, com
  todos os dados disponíveis até o momento da análise (fechamento do pregão de dados anterior,
  cotações intradiárias e dados lentos atualizados), e a decisão é gravada até o **prazo
  efetivo** (§3). Decidir depois do prazo seria conhecer o fechamento: o código recusa
  (`Runtime.weekly_decide`) e a carteira vigente é mantida até o dia de montagem seguinte.
- **Execução no fechamento (MOC):** ordens em quantidade de ações, fixadas na decisão,
  executadas ao preço oficial de fechamento de cada linha, limitadas à capacidade do leilão e
  da janela pré-fechamento (§5). Um único leilão por dia de montagem; a parcela não executada não
  é carregada (a decisão seguinte parte da carteira efetiva).
- **Pregão de dados:** a base de mercado registra pregões da união B3 | NYSE | BMV. Um feriado só
  na B3 com a NYSE aberta (ex.: 12/10/2026) é pregão de dados: o retorno das linhas brasileiras no
  dia seguinte cobre dois pregões dos EUA.

Datas de montagem do 4º trimestre de 2026: 09/10, 16/10, 23/10, 30/10, 06/11, 13/11, 20/11 (B3
fechada), 27/11 (NYSE fecha às 13h00 de Nova York), 04/12, 11/12, 18/12, 24/12 (quinta; NYSE
antecipada, B3 fechada), 31/12 (quinta; B3, Santiago e Bogotá fechadas).

## 2. Cronograma do dia de montagem (horário de Brasília)

| Horário | Etapa |
|---|---|
| Véspera, após o fechamento | Fechamento diário (marcação, risco, atribuição, comentário de P&L) e retrato da cobertura |
| 11h00 | Pesquisa e preparação da semana com dados até o momento da análise |
| até o prazo efetivo (15h00; 14h15 em fechamento antecipado nos EUA) | Decisão gravada (tarefas de reserva às 12h07, 13h07 e 14h07) |
| 16h00–17h00 (até 01/11/2026); 18h00 a partir de 02/11/2026 | Leilões de fechamento: execução das ordens |
| noite (19h20 e reserva às 21h07) | Efetivação ao fechamento oficial, registro diário e comentário de P&L; em seguida o **relatório semanal de resultado** (§10) |

Os EUA saem do horário de verão em 01/11/2026: a NYSE, a B3 (alinhada a Nova York) e a BMV passam
a fechar às 18h00 de Brasília. A rotina diária roda depois disso e a base de mercado fecha o
pregão às 19h00, sem ajuste.

## 3. Prazo efetivo da decisão

```
prazo = min( teto de 15h00 (Brasília),
             prazo do mandato (fund.decision_deadline_local),
             fechamento mais cedo entre NYSE, B3 e BMV no dia − 45 minutos )
```

- 09/10/2026: 15h00. 27/11/2026 e 24/12/2026 (NYSE fecha às 13h00 de Nova York = 15h00 de
  Brasília): 14h15. O dia só é "de fechamento antecipado" quando NYSE, B3 ou BMV (os mercados
  que definem o prazo) fecham mais cedo; o fechamento antecipado de outro mercado não muda o
  prazo. Esse mercado executa com a capacidade reduzida (× `early_close_multiplier`, §5) só se
  ainda fechar em `prazo + 45 min` ou depois; se fechar antes, não executa nesse dia — é o caso
  de Buenos Aires em 31/12/2026 (13h00 de Brasília) e de Santiago em 25/03/2027 (13h30 de
  Brasília), ambos antes de 15h45: posições detidas nesses mercados ficam congeladas (§6).
- Um mercado só executa no fechamento do dia se estiver aberto, tiver horário oficial
  conferido e fechar em `prazo + 45 min` ou depois (corte de ordens posterior ao prazo). Com o
  teto de 15h00, Santiago (16h00 locais = 16h00 de Brasília em outubro) é elegível; em
  fechamentos antecipados com encerramento antes de 15h45, não.

## 4. Horários de fechamento e fontes

Os dias de pregão vêm do calendário de cada bolsa (biblioteca `exchange_calendars`, construída com
limites explícitos de 20 anos para trás e 2 para frente). Os **horários** vêm da tabela abaixo
(`execution.close_times`), porque a biblioteca não é confiável para os horários de B3, BMV e
BVL; os fechamentos antecipados vêm do calendário (NYSE em 27/11/2026 e 24/12/2026; Santiago e
Buenos Aires em 24/12/2026; Buenos Aires em 31/12/2026; Santiago em 25/03/2027) e o corte de
ordens antecipa na mesma distância. Os valores estão fixados em `tests/cdp/test_calendar.py`.

A coluna **Natureza** diz de onde vem cada horário: *oficial* (documento da própria bolsa),
*secundária* (imprensa ou corretora, conferida contra o horário de pregão publicado) ou
*inferência* (sem fonte publicada para o horário do leilão; valor conservador).

| Mercado | Fechamento (fuso) | Corte de ordens no fechamento | Natureza | Fonte |
|---|---|---|---|---|
| NYSE (XNYS) | 16:00 Nova York | MOC/LOC até 15:50 | oficial | NYSE, *Opening and closing auctions fact sheet*: https://www.nyse.com/publicdocs/nyse/markets/nyse/NYSE_Opening_and_Closing_Auctions_Fact_Sheet.pdf |
| Nasdaq (XNAS) | 16:00 Nova York | MOC até 15:55 (LOC até 15:58) | oficial | Nasdaq, *Opening and Closing Crosses*: https://www.nasdaqtrader.com/content/technicalsupport/specifications/TradingProducts/openclosequickguide.pdf |
| NYSE Arca (ARCX) | 16:00 Nova York | congelamento das ordens no fechamento às 15:59 | oficial | NYSE Arca, *Trading information*: https://www.nyse.com/markets/nyse-arca/trading-info |
| NYSE American | 16:00 Nova York | corte da NYSE (15:50; conservador) | oficial (NYSE) | idem NYSE |
| B3 (BVMF) | 17:00 Brasília com horário de verão nos EUA; 18:00 sem (alinhada a Nova York: 16:00) | call de fechamento 16:55–17:00 (17:55–18:00) | oficial; extensão de horário por imprensa | B3, horário de negociação de ações: https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/horario-de-negociacao/acoes/ ; extensão a partir de 03/11/2025: https://www.infomoney.com.br/mercados/b3-estende-horario-de-funcionamento-a-partir-de-3-de-novembro-2025-veja-como-fica/ |
| BMV (XMEX) | 14:00 Cidade do México com horário de verão nos EUA; 15:00 sem (alinhada a Nova York: 16:00) | ordens ao fechamento até 13:40 (= 15:40 Nova York); preço de fechamento pelo PPP de 13:40 a 14:00 | oficial; alinhamento a Nova York por imprensa | BMV, horários de negociação: https://www.bmv.com.mx/es/Grupo_BMV/Calendario_de_dias_festivos/_rid/662/_mod/TAB_HORARIOS_NEG ; https://expansion.mx/mercados/2025/10/31/bolsa-mexicana-regresa-horario-apertura-cierre |
| Bolsa de Santiago (XSGO) | 16:00 Santiago (pregão 09:30–16:00) | 15:45 | **inferência conservadora, sem fonte oficial do horário do leilão**: o horário de pregão é publicado; o corte supõe uma sessão de fechamento de 15 minutos, como a da sessão encurtada de fim de ano (12:45–13:00) | horário de pregão: https://www.rankia.cl/blog/analisis-ipsa/3269972-horario-bolsa-santiago-subasta-apertura-cierre ; sessão de fechamento em dia encurtado: https://elcomercio.pe/economia/peru/nuam-conoce-los-horarios-especiales-de-operacion-por-cierre-de-ano-l-nuam-l-ultimas-noticia/ ; https://www.df.cl/mercados/bolsa/bolsa-de-santiago-pone-en-marcha-nuevo-mecanismo-de-negociacion-de |
| BVC (XBOG) | 15:00 Bogotá com horário de verão nos EUA; 16:00 sem (alinhada a Nova York: 16:00) | leilão de fechamento 15:55–16:00 Nova York | secundária | https://www.larepublica.co/finanzas/apertura-de-la-negociacion-en-la-bolsa-de-valores-de-colombia-sera-desde-las-9-15-a-m-4262376 ; https://www.rankia.co/blog/analisis-colcap/4225444-calendario-bolsa-valores-colombia |
| BVL (XLIM) | 15:00 Lima com horário de verão nos EUA; 16:00 sem (alinhada a Nova York: 16:00) | leilão de fechamento 14:52–15:00 Lima (= 15:52 Nova York), fim aleatório de até 120 s | secundária (comunicado de corretora) | https://www.rankia.pe/blog/bvl-mercado-al-dia/6381154-horario-bolsa-peru ; https://www.btgpactual.com.pe/comunicado-al-cliente-nuevo-horario-de-negociacion-bvl/ |
| BYMA (XBUE) | 17:00 Buenos Aires | leilão de fechamento 16:57–17:00 | secundária | https://www.bloomberglinea.com/latinoamerica/argentina/la-bolsa-argentina-cambia-su-horario-de-negociacion-para-alinearse-con-estados-unidos/ |

Os horários de Santiago e das bolsas andinas mudam com a integração da nuam; cada alteração
oficial entra na tabela do mandato e no teste correspondente.

## 5. Capacidade de execução no fechamento

Por linha ℓ, no pregão s:

```
cap_ℓ(s) = mult(s) · [ p_leilão · fatia_leilão(categoria) + p_pré · fatia_pré ] · V_ℓ
```

| Parâmetro | Valor | Significado |
|---|---|---|
| `p_leilão` (`auction_participation`) | 10% (teto 15%) | participação máxima no leilão de fechamento |
| `fatia_leilão` | EUA 10%, ADR 6%, ETF 1%, BR 8%, MX 10%, CL 10%, CO/PE/AR 5% | fração esperada do volume do dia no leilão |
| `p_pré` · `fatia_pré` | 10% · 25% | participação na janela pré-fechamento (25% do volume do dia) |
| `V_ℓ` na decisão | P25 do valor negociado diário em USD nos 20 pregões anteriores com preço | volume conservador |
| `V_ℓ` na execução | valor negociado no próprio pregão | volume realizado |
| shorts | × 0,75 | aluguel e regra de preço |
| fechamento antecipado | × 0,5 nos mercados que fecham mais cedo (só neles) | leilão mais curto |

Ordem de grandeza: cerca de 3,3% do ADV numa ação da B3 e 3,5% numa ação listada nos EUA ou na BMV.
**Volume desconhecido ⇒ capacidade zero** — como restrição, nunca como dado: volume zero com
preço válido é tratado como ausente, e menos de dez observações na janela de 20 pregões tornam o
volume desconhecido. O otimizador limita cada aumento de posição à capacidade da linha usada; a
redução até zero continua permitida na construção, mas a execução também é limitada pela
capacidade.

`fechamentos_necessarios(nocional, capacidade)` = nocional / capacidade (sem capacidade, não
definido).

**Liquidez em fechamentos.** Com a execução só no leilão, a liquidez de cada posição é medida
em **fechamentos para zerá-la** à capacidade estrutural de redução da linha (a mesma fórmula num
pregão regular — `janela_regular` —, sem o multiplicador de short, porque zerar um short é uma
compra). Os limites do mandato `liquidity.max_days_to_liquidate_long` (3) e `_short` (2) contam
fechamentos: entram como teto de posição na construção (origem "liquidez"), na compliance
(`LIQ_DAYS_LONG`/`LIQ_DAYS_SHORT`, bloqueiam), no registro diário (`max_days_to_liquidate` e a
fração do gross liquidável em 1 fechamento), no monitor de risco, no memorando, no relatório
semanal e no app interno ("Fechamentos p/ liquidar"). Volume desconhecido ⇒ liquidez
desconhecida (reprova; nunca liquidez imediata). Um feriado no mercado da linha não muda essa
medida (é estrutural); o dia de montagem usa a capacidade do próprio dia.

**Dimensionamento para o PL de US$ 1,0 mi.** Com o PL inicial de US$ 1,0 mi, o teto de 4% por nome são
US$ 40 mil: cabe em um fechamento de qualquer linha com ADV acima de cerca de US$ 1,2 mi. Os
limites relativos (fechamentos para liquidar, capacidade do dia, participação no ADTV) é que
dimensionam a posição; os pisos absolutos de ADTV ficam como filtros de qualidade —
US$ 1 mi na elegibilidade, US$ 2 mi na linha comprada e US$ 5 mi na linha vendida (aluguel,
recall e squeeze pioram com a iliquidez).

## 6. Mercados fechados, congelamento e roteamento por ADR

- Linha cujo mercado não tem pregão elegível (fechado, horário não conferido ou fechamento antes
  do prazo mais a margem) não negocia. Emissor com **linha detida** nessa situação fica
  **congelado**: mantém as ações e nenhuma linha dele é negociada no dia (o otimizador fixa
  `w = w⁰`).
- Política `adr_if_eligible_else_freeze`: um emissor sem posição, com o mercado local fechado,
  pode ser negociado pela ADR/listagem nos EUA se houver linha elegível com dados; sem ela, fica
  congelado. O roteamento (`rotear_linhas`) troca a linha comprada do emissor pela linha elegível
  de maior ADTV antes da construção, de modo que capacidade, custo, ordem e execução usem a
  ADR; a linha vendida (aluguel) não muda. A ADR negociada com a bolsa local fechada tem
  spread × 1,5 no custo.
- Exemplo: em 20/11/2026 (B3 fechada) nenhuma linha local brasileira negocia; posições detidas
  em linhas locais ficam congeladas.

## 7. Efetivação, banda de não-negociação e custos

- Ordem por linha = ações-alvo da decisão − ações detidas; execução =
  `sinal × min(|ordem|, ⌊capacidade / preço⌋)`, ao **fechamento oficial do próprio pregão** —
  nunca a um preço defasado, nunca ao preço de outra linha.
- Ações-alvo arredondadas à ação inteira. Na B3 a ordem é dividida em lote padrão (múltiplos de
  100 ações, no código da linha) e mercado fracionário (1 a 99 ações, código com sufixo `F`,
  ex.: `PETR4F`) — `cdp.portfolio.trades.order_legs`; a posição é uma só, marcada ao fechamento
  oficial da linha. Com PL de US$ 1,0 mi, arredondar ao lote de 100 distorceria posições pequenas
  em até meio lote (até ~US$ 640 numa posição mínima de US$ 2 mil).
- Na BMV o lote é 1 título, mas só ordens de 100 títulos (5, com preço acima de MXN 200) formam
  preço; o resto é um "pico", executado ao último preço registrado — numa ordem ao fechamento, o
  próprio fechamento (Reglamento Interior da BMV:
  https://www.bmv.com.mx/docs-pub/MARCO_NORMATIVO/CTEN_MNRST/REGLAMENTO%20INTERIOR%20BMV%20VIGENTE-20250303.pdf ;
  glossário: https://blog.bmv.com.mx/glossary/lote/ ;
  exemplo de corretora: https://www.actinver.com/minisitioSEF/ayuda/sef/Preguntas_Frecuentes_BMV/lote_100_acciones_5_cuando_la_.htm).
  Em Santiago, na BVC, na BVL, na BYMA e nos EUA não há lote padrão: 1 ação. Ação cara (ex.:
  MELI, cerca de 0,19% do NAV por ação com PL de US$ 1 mi) é arredondada à ação inteira mais
  próxima; o maior erro de arredondamento e as posições que não chegam a uma ação ficam na
  proposta (`overrides.arredondamento`) e no memorando.
- **Banda de não-negociação**: ordens abaixo de 0,10% do NAV (`min_trade_weight`, US$ 1 mil) não
  são enviadas, salvo o encerramento de uma posição. Em cada mercado, a banda sobe até o nocional
  em que o custo fixo mínimo das ordens da linha cai a 10 bps (`max_fixed_cost_bps`): cerca de
  US$ 3,5 mil por ordem na BMV (US$ 7 mil quando a ordem tem lote padrão e pico, que pagam dois
  mínimos), US$ 22 mil na BVC e US$ 28 mil em Santiago. A posição mínima por nome é o maior entre
  0,2% do NAV e a banda do mercado da linha com o número máximo de ordens da linha (duas na B3 e
  na BMV, uma nos demais; `cdp.portfolio.trades.max_order_legs`): na BMV, US$ 7 mil. Assim, uma
  posição nova decidida nunca fica abaixo da banda que a execução aplica no fechamento.
- Ordem posterior ao corte de ordens do mercado não executa.
- `booked_at` = fechamento oficial mais tardio entre as linhas negociadas; a efetivação lista a
  carteira resultante (linhas negociadas, saldos de saídas parciais e emissores congelados).
- A regra de execução por linha é uma só (`preenchimentos_esperados`) e serve à rotina diária,
  ao livro e à verificação: o livro recalcula, com os dados do pregão, a execução esperada de
  cada linha e recusa (`BOOKING_REFUSED`) qualquer efetivação que negocie acima da capacidade
  pelo volume realizado, num mercado sem fechamento elegível, num emissor congelado, depois do
  corte de ordens ou abaixo da banda; `cdp verify` refaz a mesma conferência para todas as
  efetivações do livro.
- Na decisão, o prazo é conferido num único instante, que é também o horário gravado da
  proposta e da decisão: a decisão nunca é registrada depois do prazo efetivo.
- Custo por linha negociada, em bps do valor negociado: meio spread pela faixa de ADTV (× 1,5 na
  ADR com a bolsa local fechada) + comissão das ordens individuais + câmbio (3 bps fora do
  dólar) + impacto raiz quadrada `0,6 · σ_diária · √(Q / ADTV)` × desconto de leilão (0,6 em EUA,
  ADR, BR, MX e CL; 1,0 nos demais). Para cada ordem, a comissão em USD é o maior entre sua
  comissão variável e o mínimo do mercado. A comissão da linha soma esses valores e os divide
  pelo nocional total, convertendo para bps. Lote padrão e fracionário ou pico pagam seus
  próprios mínimos; uma ordem pequena não divide o mínimo com a ordem padrão.
- A estimativa da proposta decompõe as quantidades planejadas com o preço local corrente.
  Substitui somente a comissão já incluída na mesma base de custos pela soma por ordem;
  spread, impacto e câmbio dessa base permanecem. O débito usa as quantidades efetivamente
  preenchidas e preço/câmbio do fechamento. A previsão não certifica o débito futuro.
  Estimativa ausente continua indisponível; com cobertura parcial, apresenta somente o subtotal
  conhecido e identifica a limitação. O otimizador continua com a curva convexa (custo fixo
  não é convexo e entra pela banda e pela posição mínima).

**Mínimo por ordem (`costs.min_order_cost_usd`), de tabelas públicas:**

| Mercado | Mínimo (USD) | Base pública |
|---|---|---|
| EUA (ações e ADRs) | 1,00 | corretora global de acesso direto, plano fixo: US$ 0,005 por ação, mínimo de US$ 1,00 por ordem, tarifas incluídas — https://www.interactivebrokers.com/en/pricing/commissions-stocks.php |
| B3 | 0,00 | tarifas da B3 ad valorem (negociação 0,005% + liquidação 0,025% para os demais investidores), sem mínimo por ordem; já no custo em bps — https://b3.com.br/data/files/15/32/93/72/68E289100A29E189AC094EA8/Tarifacao_Produtos_Renda_Variavel_V2_PT_.pdf |
| BMV | 3,50 | 0,10% do valor com mínimo de MXN 60 por ordem na mesma corretora global (≈ US$ 3,3 a MXN 18,1 por dólar), arredondado para cima — https://brokerchooser.com/invest-long-term/diversification/mexican-stocks-at-interactive-brokers |
| Santiago | 28,00 | direitos de bolsa com mínimo de 0,5 UF por operação, mais IVA de 19%, e tarifa fixa de corretora (ex.: CLP 3.500 + IVA) — https://www.rankia.cl/blog/analisis-ipsa/1585223-bolsa-santiago-que-como-invertir-ella ; https://www.rankia.cl/blog/corredores-bolsa/7016987-costos-totales-invertir-chile-comisiones-derechos-iva |
| BVC | 22,00 | comissão mínima de COP 60 mil + IVA nas comissionistas de maior porte (COP 20 mil a 100 mil) — https://www.larepublica.co/finanzas/estas-son-las-tarifas-que-cobran-las-comisionistas-de-bolsa-por-transar-acciones-2959659 |
| BVL e BYMA | 25,00 | sem tabela pública padronizada: estimativa conservadora (os emissores desses países negociam pela ADR) |

Os valores são aproximações em dólar de tabelas em moeda local; uma mudança relevante de câmbio
ou de tabela entra no mandato com nova data. Mercado sem valor na tabela usa o maior mínimo
configurado (conservador).

**Hedge cambial.** A carteira é neutra por país, então a exposição cambial líquida por moeda é
pequena. Acima de 1% do NAV, o hedge sugerido usa contratos inteiros de minicontratos de bolsa:
BRL no Futuro Míni de Taxa de Câmbio de Reais por Dólar Comercial da B3 (WDO, US$ 10 mil por
contrato — https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/moedas/futuro-mini-de-taxa-de-cambio-de-reais-por-dolar-comercial.htm),
MXN no mini futuro do dólar da MexDer (US$ 1 mil; o contrato padrão é de US$ 10 mil —
https://www.bmv.com.mx/docs-pub/SALA_PRENSA/CTEN_BOLE/Nuevo%20Contrato%20Mini%20Futuro%20D%C3%B3lar%2028.05.25.pdf)
e COP no mini futuro TRM da BVC (US$ 5 mil; o padrão é de US$ 50 mil). O número de contratos é a
exposição dividida pelo tamanho do contrato, arredondada; o resíduo fica divulgado. CLP, PEN e
ARS ficam sem hedge, com a exposição divulgada: não há futuro de bolsa acessível de tamanho
compatível, e o NDF exige nocional mínimo muito acima do PL.

## 8. Implementation shortfall (execução em papel)

A execução ao fechamento oficial tende a lisonjear o resultado se não for medida. Em cada dia de
montagem o relatório semanal apura, por linha negociada:

- **deriva decisão→fechamento** = Σ ações executadas × (fechamento − preço de decisão) × câmbio
  (positivo = custo);
- **custo modelado** (§7) e **implementation shortfall** = deriva + custo modelado, em bps do
  valor executado. Em paper trading o custo debitado é o próprio custo modelado; a parcela
  mensurável do shortfall é a deriva;
- **custo de oportunidade** da parcela não executada;
- **participação na janela de fechamento** = ações executadas / ((fatia do leilão + fatia
  pré-fechamento) × volume do pregão), limitada a 10% pela regra de capacidade. Toda a execução,
  inclusive a parcela da janela pré-fechamento, é registrada ao preço oficial de fechamento;
- **estatística t da deriva decisão→fechamento** em janela móvel de até 13 semanas (média /
  erro-padrão da deriva semanal; mínimo de três semanas).

## 9. Período de montagem e liquidez em estresse

- **Período de montagem:** vai do dia da carteira inaugural até a vol ex-ante da carteira efetiva
  alcançar pela primeira vez o piso da banda. Nesse período, com a vol efetiva abaixo da meta, o
  relatório publica o risco efetivo contra a meta e uma trajetória **condicional**: se a
  composição atual fosse mantida, a escala alcançável após k fechamentos semanais é o menor
  `(|w_i| + Σ_{j≤k} c_ij)/|w_i|` entre os nomes com capacidade conhecida (`c_ij` = capacidade do
  nome no j-ésimo dia de montagem seguinte, em fração do NAV — zero no dia em que o mercado do
  nome não tem fechamento elegível). O texto só atribui o risco abaixo da meta à capacidade do
  leilão quando ela de fato limitou a carteira (teto de negociação ou de posição com origem na
  capacidade vinculante na decisão, ou execução abaixo da ordem); fora disso, a redação é
  neutra. Com a carteira na meta, ou depois do período de montagem, não há trajetória publicada.
- **Liquidez em estresse:** contada em leilões de fechamento de um pregão **regular** (liquidez
  estrutural: o feriado de um dia não torna os nomes do mercado fechado ilíquidos; os mercados
  sem fechamento elegível no próximo dia de montagem aparecem à parte, como nota operacional),
  com volume de 0,7 × ADV por nome (P10 da razão entre o volume diário e o ADV de 63 pregões nos
  episódios de estresse da região: COVID-2020, segundo turno de 2022 no Brasil, PASO-2019 na
  Argentina, estallido-2019 no Chile, carry de agosto de 2024, Americanas-2023) e cenário reverso
  de 0,5 × ADV. Publicam-se a fração do gross liquidável em 1, 3, 5 e 10 leilões nos dois
  cenários, o número de leilões para liquidar 90% do gross e o **custo estimado de liquidação em
  estresse**: cada nome liquidado em fechamentos sucessivos com 0,7 × capacidade por fechamento,
  custo do §7 com spreads × 2 e σ × 2 (impacto sobre o nocional por fechamento), em US$ e em bps
  do NAV e do gross coberto.

## 10. Relatórios

- **Diário (todo pregão, à noite):** resultado do dia com o comentário de P&L, risco e
  atribuição (`cdp daily close` → comentário → `cdp daily publish`).
- **Semanal (noite de todo dia de montagem):** `cdp weekly close-report --date D` grava os fatos
  da semana; o comentário é validado (`cdp validate-weekly-report --date D`) e publicado
  (`cdp weekly close-report --date D --publish`, com o modelo determinístico do código se o
  comentário for inválido). A semana vai do fechamento do dia de montagem anterior ao fechamento
  de D. Conteúdo: mudanças da carteira no fechamento (entradas, saídas, aumentos e reduções, com
  o racional da decisão), resultado e atribuição de performance da semana e desde o início
  (componentes, grupos de fatores, país, setor, lado e emissor — somas exatas dos registros
  diários), giro, custos, taxa de execução, todos os emissores detidos sem negociação no
  fechamento, implementation shortfall, risco ex-ante da carteira decidida e da efetiva (fatia
  idiossincrática na base do limite do mandato, com κ_F, e sem κ_F, rotuladas), período de
  montagem e liquidez em estresse. Sem decisão gravada no dia de montagem, o relatório é
  publicado do mesmo modo, com a carteira mantida e sem execução. Na semana da carteira
  inaugural é o relatório de montagem. A agenda lista todo relatório semanal pendente
  (`relatorio_semanal.pendentes`), do mais antigo ao mais recente.

## 11. Verificação

```
uv run python -m cdp agenda            # dia de montagem, prazo efetivo, mercados fechados, pendências
uv run --extra dev pytest tests/cdp/test_calendar.py tests/cdp/test_execucao.py tests/cdp/test_relatorio_semanal.py -q
uv run python -m cdp verify            # trilha, livro, track record e base de mercado
```

## 12. Kill switch: procedimento do operador

- **Ligar** (rotina de risco, por recomendação do código, ou operador):
  `uv run python -m cdp kill-switch on --reason "<motivo>" --by "<quem>"`. O comando grava
  `book/KILL_SWITCH`, o evento na trilha e um **pedido mesclável** em
  `reports/risk/<data>/kill_switch_<HHMM>.yaml`. Se a rotina não tiver a trava exclusiva do livro
  (clones separados na nuvem, outra rotina gravando), `cdp publicar` publica o pedido e retém o
  livro; a próxima execução exclusiva (`weekly prepare`, `weekly decide` ou `daily close`)
  aplica o pedido antes de qualquer decisão. `cdp agenda` lista os pedidos ainda não aplicados
  (`kill_switch_pedidos`); `uv run python -m cdp kill-switch aplicar-pedidos` aplica-os à mão
  numa execução exclusiva. Um pedido anterior a um desligamento humano fica só registrado.
- **Desligar** (só um humano, em qualquer app): abra um **terminal próprio** — não o terminal de
  um agente de IA (Claude Code, Codex, Gemini), não uma rotina, não o CI — no clone do executor,
  revise a condição no relatório de risco e rode
  `uv run python -m cdp kill-switch off --reason "<revisão em pelo menos 10 caracteres>" --by "<seu nome>"`.
  O comando recusa sem terminal interativo, com variáveis de rotina, CI ou agente
  (`CDP_EXECUTOR`, `CDP_HARNESS`, `CDP_TRAVA_ID`, `CI`, `GITHUB_ACTIONS`, `CLAUDECODE`,
  `CODEX_*`, `GEMINI_CLI`, `ANTIGRAVITY_*` e afins), pede que o motivo seja digitado de novo e
  exige a **senha do operador** — confirmação fora de banda: um agente com acesso total e
  pseudoterminal chega no máximo ao pedido da senha, que só o humano conhece. A senha é definida
  uma vez, no mesmo terminal próprio, com `uv run python -m cdp kill-switch senha` (trocá-la
  exige a atual); fica só o hash PBKDF2 com sal em `~/.config/cdp/operador.json`, fora do
  repositório. Nunca entregue a senha a um app de IA nem a grave em arquivo do clone. Depois:
  `uv run python -m cdp verify` e `cdp publicar` (ou commit e push manual do `book/` pelo
  operador, seguindo `docs/cdp/AUTOMACAO.md`). A condição revisada não religa o kill switch; só
  uma piora: estágio pior da escada de drawdown, perda diária extrema num registro de fechamento
  posterior ao revisado ou short novo em stop (outro emissor ou outro preço médio de entrada; a
  escalada de squeeze é revisada short a short, nunca só pelo emissor).
- **Kill switch no leilão do dia de montagem — regra de caducidade.** A decisão vale só para o
  leilão de fechamento do seu dia de montagem. Com o kill switch ligado nesse fechamento, a ordem
  não é executada (só redução de risco) e a rotina diária registra o próprio dia com a recusa
  (`daily close` → `status: "registrado"` com `efetivacao_recusada`; alerta "Efetivação
  recusada" no registro): grava `book/<semana>/efetivacao_recusada.json` e o evento
  `BOOKING_LAPSED` na trilha. A decisão **caduca**: nunca é efetivada depois, nem quando um
  humano desligar o kill switch (sem efetivação retroativa, que usaria um preço já conhecido). Na
  carteira inaugural, o histórico começa nesse dia em caixa (PL inicial, sem posições); numa
  semana regular, a carteira anterior segue marcada. A próxima data de montagem decide de novo,
  com dados novos (a partir da caixa, se a inaugural caducou). Recusa por dado ausente (preço ou
  câmbio) na carteira inaugural não caduca: nada é registrado e a reserva do mesmo fechamento
  tenta de novo.
- **Revisar um stop de squeeze por nome** (só um humano, como no desligamento): depois de um stop
  num fechamento, o emissor não pode ficar comprado até revisão humana — o relatório de risco
  lista os emissores nessa situação (`squeeze.vetos_compra`, gatilho
  `stop_squeeze_compra_vedada`). Revise o caso e rode, no mesmo terminal próprio,
  `uv run python -m cdp kill-switch revisar-squeeze --emissor "<emissor>" --reason "<revisão em pelo menos 10 caracteres>" --by "<seu nome>"`.
  O comando tem as mesmas recusas do desligamento, grava o evento `SQUEEZE_REVISADO` na trilha
  e libera o veto de compra dos stops até o último registro diário; um stop posterior reabre o
  veto. O corte à metade do short continua (é regra do código). Revisões gravadas depois da
  preparação de uma semana valem a partir da semana seguinte. Depois: `verify` e publicação, como
  acima.

## 13. Rotinas no app de IA (passo a passo)

As etapas deste documento rodam dentro do app de IA de quem opera, pelo agendador do próprio app;
o prompt de cada tarefa é gerado pelo código (`cdp rotinas exportar`) e é o mesmo em qualquer
app, e o código decide prazo, capacidade, execução e publicação — o resultado é idêntico em
qualquer um. O GitHub Actions só roda a integração contínua e publica o portal, nunca a IA.

1. **Claude Code** — rotinas na nuvem em claude.ai/code: ambiente "CDP" com rede total e
   as variáveis `CDP_EXECUTOR=claude-cloud` (identidade do ambiente; sem ela toda rotina para no
   gate com "identidade deste ambiente desconhecida") e `CDP_HARNESS=claude-code`; gere os blocos
   com `uv run python -m cdp rotinas exportar --alvo claude-routines --formato md` e crie uma
   rotina por bloco (Routines → New routine → Cloud), desligada até a troca de executor. Reserva:
   tarefas agendadas do app desktop (`docs/cdp/LOCAL.md`).
2. **Codex** — num clone e numa conta dedicados, registre a identidade uma vez com
   `uv run python -m cdp executor registrar --como local-pc --harness codex`; no
   `~/.codex/config.toml` dessa conta, acesso total (o roteiro sincroniza, faz commit e push),
   aprovação "never" e `CDP_HARNESS = "codex"`; tarefas agendadas do app desktop com os blocos de
   `uv run python -m cdp rotinas exportar --alvo codex --formato md`. Roda com o computador ligado
   e o app aberto.
3. **Gemini** — clone e conta dedicados, com a identidade registrada uma vez:
   `uv run python -m cdp executor registrar --como local-pc --harness antigravity` (Antigravity)
   ou `--harness gemini` (Gemini CLI), e `CDP_HARNESS` com o mesmo nome no ambiente das tarefas
   (as linhas geradas para o agendador do sistema já o passam com `--harness`). Antigravity:
   tarefas agendadas do app (`uv run python -m cdp rotinas exportar --alvo gemini --formato md`)
   ou `agy` pelo agendador do sistema
   (`uv run python -m cdp rotinas exportar --alvo cron --harness agy`); Gemini CLI com chave paga:
   `uv run python -m cdp rotinas exportar --alvo cron --harness gemini`.

Horários do dia de montagem: pesquisa a partir das 11h07, tarefas de reserva às 12h07, 13h07 e
14h07 (todas antes do prazo efetivo), fechamento diário às 19h22 com reserva às 21h07. Detalhes,
limites de cada app e solução de problemas: `docs/cdp/AUTOMACAO.md`.
