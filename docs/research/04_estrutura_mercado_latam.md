# 04 — Estrutura de Mercado para um Book Long/Short de Ações LatAm em USD

> **Data de referência:** segunda-feira, 05/10/2026 (último pregão completo: sexta-feira, 02/10/2026)
> **Escopo:** Brasil, México, Chile, Colômbia, Peru, Argentina e ADRs/linhas listadas nos EUA
> **Fundo-alvo:** USD 100 mm de capital inicial, vol ex-ante alvo 5% a.a. (banda 3%-7%), *net neutral* (dólar e beta/fatores), rebalanceamento semanal às segundas-feiras
> **Status:** documento de pesquisa (insumo para `configs/` e para os módulos de universo, liquidez, risco e execução). Não é recomendação de investimento.

**Convenção de evidência usada no documento**

| Marcador | Significado |
|---|---|
| **[F]** | Fato verificado em fonte primária ou secundária confiável (ver lista numerada de fontes) |
| **[C]** | Dado **calculado por nós** a partir de dados reais (Yahoo Finance via `yfinance`, CVM Dados Abertos, BCB/SGS), com metodologia descrita no Apêndice A |
| **[I]** | Inferência/recomendação nossa (julgamento profissional, não é fato) |
| **[V]** | Ponto que precisa de verificação adicional antes de ir para produção (fonte desatualizada, conflitante ou não obtida) |

---

## Sumário executivo

1. **O universo investível real é bem menor que o número de empresas listadas.** O MSCI EM Latin America tinha **82 constituintes e US$ 815,7 bi de capitalização ajustada por free float** em 30/09/2026; **Brasil 61,5%, México 23,6%, Chile 6,3%, Peru 6,1%, Colômbia 2,5%**; os 10 maiores nomes somam **43,2%** do índice **[F, 1]**. Com o critério de ADTV mediano ≥ US$ 5 mm/dia (63 pregões até 02/10/2026), contamos **~84 linhas locais no Brasil, ~18 no México, 2 na Colômbia, 2 na Argentina** em amostras amplas **[C]**. Somando ADRs e nomes listados só nos EUA (NU, MELI, XP, STNE, PAGS, INTR), o universo prático de um fundo de US$ 100 mm fica em **~120-140 nomes compráveis e ~80-100 vendáveis** **[I]**.
2. **O Brasil é o único mercado local LatAm com empréstimo de ações profundo e centralizado** (B3 BTC, com a B3 como contraparte central). As taxas são livremente negociadas; a B3 cobra 0,25% a.a. do tomador, mínimo de R$ 10 **[F, 9]**. Os nomes líquidos custam de 0,03% a 5% a.a., e casos *special* passam de 25%-100% a.a.: Ambipar 105,3%, Hapvida 39,1%, CPFL 28,1% e Raízen 26,7% **[F, 14, 15, 17]**. No México, no Chile, na Colômbia e no Peru a venda a descoberto é legal, mas **na prática o short se faz via ADR (borrow nos EUA), swap de *prime broker* ou ETF/futuro de índice** **[F, 21-26; I]**. Na Argentina, a venda a descoberto local é residual e o short se faz via ADR **[F, 21]**.
3. **O risco de *short squeeze* em LatAm é concreto e documentado.** Os gatilhos típicos são concentração de controle + recompra/compra de aliados + baixo free float (Ambipar 2024: de ~R$ 8 para pico de R$ 268, ~33×; depois recuperação judicial e **-99%** até nov/2025 **[F, 12, 13; C]**), aumento de capital que afasta a tese (IRB 2022: aluguel a 45% a.a., short perto do limite de 25%→30% do free float, **+24,7% em um dia** em 21/12/2022 **[F, 11; C]**) e **eventos políticos binários**. Exemplos: ADRs argentinos **+24% a +41% em 27/10/2025** e **-34% a -56% em 12/08/2019**; ADRs brasileiros **+10% a +13% em 03/10/2022** **[C]**.
4. **Alerta de calendário para esta semana:** o 1º turno da eleição presidencial brasileira (04/10/2026) teve **Flávio Bolsonaro 47,03% contra Lula 45,16%** dos votos válidos (TSE, 100% das seções totalizadas), contra pesquisas que davam Lula à frente. O **2º turno é em 25/10/2026** **[F, 34, 36, 45]**. O Ibovespa fechou a sexta (02/10) em **192.114,55 pts (+2,63% no dia, +4,71% na semana)** e o USD/BRL em **5,2165** **[F, 35]**. O análogo de 2022 (surpresa no 1º turno) produziu *gap* de +8% a +13% em estatais e bancos **[C]**. **Recomendação [I]:** começar a carteira no **terço inferior da banda de vol (3,5%-4%)**, com beta Brasil ≈ 0 e **sem novos shorts em estatais e domésticos muito vendidos** até o 2º turno.
5. **Câmbio:** num book *net neutral* com neutralidade **por país e por moeda**, a exposição cambial se cancela quase toda. O resíduo custa caro de carregar: diferencial de juros ≈ **+9,9 p.p. (BRL), +8,4 (COP), +2,6 (MXN), +0,6 (CLP), +0,4 (PEN)** contra Fed Funds de 3,75%-4,00% **[F, 28-33; I para o carry]**. A vol cambial em 1 ano foi de **11,5% (BRL), 8,3% (MXN), 12,0% (CLP), 15,6% (COP)** **[C]**. Assim, **10% do PL líquido em BRL consomem ~1,15 p.p. de vol, ~23% do orçamento de 5%**. Limite proposto: **|exposição líquida por moeda| ≤ 5% do PL**.
6. **Hedges líquidos:** EWZ (ADTV mediano **US$ 789 mm**), BOVA11 (US$ 112 mm), EWW (US$ 80 mm), ILF (US$ 72 mm), ECH (US$ 15 mm), ARGT (US$ 11 mm), COLO (US$ 5,6 mm), EPU (US$ 2,9 mm) **[C]**. Futuro de Ibovespa: IND a R$ 1,00/pt e WIN a R$ 0,20/pt, meses pares, vencimento na quarta-feira mais próxima do dia 15 **[F, 40]**. O próximo vencimento é **14/10/2026** **[I, pela regra]**.
7. **O que os L/S profissionais efetivamente rodam (dados CVM, 3 anos, out/2023-out/2026) [C]:** a vol diária anualizada fica entre **3%-9%** (mediana ~5% nos Direcionais). O retorno anualizado dos *masters* L/S Neutro foi de **12,5%-15,7% contra CDI de 13,0%**, ou seja, excesso de **-0,5 a +2,7 p.p.**; a mediana dos Direcionais foi de **-0,2 p.p.** e o melhor caso **+8,5 p.p. com 6,6% de vol**. Em jun/2026, mediana de **45 nomes comprados e 22 vendidos**, **gross local de 87%** (IQR 75%-127%) + ~11% offshore, **maior posição comprada 6,9% e maior vendida 3,6% do PL** (medianas). Nos últimos 12 meses os Neutros renderam **~3%-8% contra CDI de ~14,4%-14,5%** (o piso da faixa é sensível a ±2 dias na janela; ver "Verificação independente"): o rali penalizou os shorts.
8. **Liquidação e horários:** EUA e México em **T+1** desde 27-28/05/2024 **[F, 20]**. A B3 segue em **D+2**, com migração para D+1 prevista para **fev/2028** **[F, 19]**. Chile, Colômbia e Peru em T+2 **[F/V, 21]**. A sobreposição com a NYSE em 02/10/2026 foi de **~6h25 na B3, 6h30 (integral) na BMV e na BVC, 6h na BYMA e 5h30 em Santiago** **[C]**.
9. **Tributos relevantes para o desenho:** o Brasil passou a reter **10% de IR sobre dividendos pagos a não residentes desde jan/2026** (Lei 15.270/2025), com mecanismo de crédito quando a carga combinada passa de 34%/40%/45% **[F, 8]**. O IOF-câmbio é 0% no ingresso e no retorno de investimento de não residente no mercado financeiro **[F, 7]**. Retenção sobre dividendos: México 10%, Peru 5%, Colômbia 20%, Chile 35% com crédito do imposto de 1ª categoria **[F/V, 21]**. **Isso afeta o *carry* de shorts em pagadores de dividendos:** o tomador paga ao doador o valor **bruto** **[F, 9]**.

---

## 1. Universo investível, tamanho e liquidez (item a)

### 1.1 Visão consolidada por país

| País | Peso MSCI EM LatAm (30/09/2026) [F,1] | Cap. float MSCI derivada (US$ bi) [C] | Linhas locais na amostra / com ADTV ≥ US$ 5 mm / ≥ US$ 20 mm [C] | ADTV mediano da amostra local (US$ mm) [C] | Observações |
|---|---|---|---|---|---|
| Brasil | 61,54% | ~502 | 110 / 84 / 40 | 13,9 (p75 32,5; p90 81,3) | B3: ADTV à vista de **R$ 34,8 bi no 1T26** e **R$ 37 bi em abr/2026** (~US$ 6,7-7,1 bi), **estrangeiros ~60% do volume** [F, 2, 3, 5] |
| México | 23,55% | ~192 | 39 / 18 / 8 | 4,2 (p90 26,2) | Volume Yahoo cobre só a BMV (sem BIVA), o que subestima o local [V]. Muita liquidez nos ADRs (AMX, FMX, CX, KOF, ASR, PAC) |
| Chile | 6,32% | ~52 | n/d (dados locais Yahoo congelados) [V] | n/d | ADRs: SQM 66, LTM 36, BCH 11, BSAC 9,6 [C] |
| Peru | 6,09% | ~50 | n/d (dados BVL Yahoo congelados) [V] | n/d | Liquidez nas linhas NYSE: SCCO 202, BAP 102, BVN 29, IFS 12 [C] |
| Colômbia | 2,50% | ~20 | 17 / 2 / 0 | 0,9 | Ecopetrol 17,8 e PF Cibest 6,6 no local; ADRs EC 31 e CIB 25 [C] |
| Argentina | fora do índice MSCI EM [F, 1]; Standalone mantido na revisão de jun/2026 [NÃO VERIFICADO, 37] | — | 23 / 2 / 0 | 0,4 | ADRs: YPF 52, GGAL 34, BMA 21, PAM 13; VIST 65 (NYSE) [C] |
| EUA (LatAm sem linha local relevante) | NU está no índice como "Brasil" | — | — | — | NU 1.025, MELI 785, XP 95, STNE 42, PAGS 26, INTR 23, ARCO 8,5, VTEX 2,9 [C] |

Características do índice em 30/09/2026 **[F, 1]**:
- Maior constituinte: US$ 49,5 bi (Vale). Mediano: US$ 5,4 bi. Menor: US$ 1,7 bi.
- Top 10: Vale 6,07%, Itaú PN 5,68%, Nu 5,61%, Petrobras PN 5,39%, Petrobras ON 4,75%, Grupo México 4,53%, Credicorp 3,15%, Banorte 3,10%, Bradesco PN 2,45%, FEMSA 2,44%. Soma: 43,16%.
- Setores: Financeiro 35,2%, Materiais 19,6%, Energia 11,3%, Consumo básico 10,0%, Industriais 8,7%, Utilities 7,8%.
- Risco: desvio-padrão anualizado de **19,5% (3 anos)** e 22,3% (5 anos); MSCI EM 17,2% (3 anos).
- Valuation: P/L 10,9×, P/L projetado 9,7×, dividend yield 4,75%.
- Retorno: **+55,7% em 2025** (USD, bruto) e +15,2% no acumulado de 2026 até setembro.

### 1.2 Brasil: maiores ADTVs da linha local (US$ mm/dia, mediana de 63 pregões até 02/10/2026) [C]

PETR4 320 · VALE3 261 · ITUB4 175 · BBDC4 122 · AXIA3 (Eletrobras/Axia) 121 · B3SA3 110 · BPAC11 106 · BBAS3 104 · PETR3 94 · EMBJ3 90 · PRIO3 89 · SBSP3 80 · ABEV3 75 · VBBR3 69 · WEGE3 69 · UGPA3 65 · RENT3 63 · EQTL3 61 · ITSA4 54 · SUZB3 50 · ENEV3 46 · CPLE3 45 · BBSE3 43 · GGBR4 41 · RDOR3 40 · LREN3 36 · CYRE3 35 · RADL3 34 · RAIL3 28 · MOTV3 28 · TIMS3 28 · CMIG4 27 · VIVT3 27 · TOTS3 26 · SMFT3 25 · MGLU3 22 · SANB11 22 · CURY3 22 · MULT3 22 · ALOS3 21.

### 1.3 México: maiores ADTVs da linha local na BMV (US$ mm/dia) [C]

GMEXICOB 59 · GFNORTEO 54 · WALMEX 37 · AMXB 35 · CEMEXCPO 24 · FEMSAUBD 23 · AC 20 · GAPB 20 · PE&OLES 14 · ASURB 8,8 · GENTERA 8,5 · Q 8,4 · OMAB 8,3 · KIMBERA 6,0 · FUNO11 5,8 · BIMBOA 5,8 · KOFUBL 5,5 · VESTA 5,1.

### 1.4 Concentração e implicações [I]

- **Concentração setorial e de nomes:** bancos, commodities (petróleo, minério, cobre, celulose, aço) e utilities dominam. Um book neutro sem controle de fatores vira, sem querer, uma aposta **commodities vs. domésticos** ou **estatais vs. privadas**. O motor de risco precisa de fatores de país, setor, estilo e **"estatal/político"**.
- **Capacidade:** com vol de 5% e risco idiossincrático típico de ~25%-30% por nome, um book de 60-80 nomes exige gross de ~**130%-200%**, ou seja, US$ 130-200 mm de gross e posição média de US$ 2-3 mm. Pelas regras de liquidez da Seção 9, isso pede ADTV mínimo de ~US$ 5 mm para longs e ~US$ 10 mm para shorts. O universo da Seção 1.1 comporta isso, mas **não sobra muito fora do Brasil**.
- **Mercados *thin* (Colômbia, Peru local, Argentina local, Chile local):** devem ser acessados pelos ADRs ou ficar fora do book de shorts.

---

## 2. Linha local vs. ADR (item b)

### 2.1 Participação do ADR na liquidez combinada e razão ADR implícita [C]

ADTV mediano em US$ mm (63 pregões até 02/10/2026). A coluna "Razão implícita" vem de preço do ADR ÷ (preço local ÷ câmbio) e confirma o ratio do *deposit agreement*.

| Empresa | ADR | Local | Ratio (ações por ADR) | ADTV ADR | ADTV local | % ADR | Razão implícita |
|---|---|---|---|---|---|---|---|
| Petrobras ON | PBR | PETR3 | 2 | 341 | 94 | 78% | 2,00 |
| Petrobras PN | PBR-A | PETR4 | 2 | 119 | 320 | 27% | 2,00 |
| Vale | VALE | VALE3 | 1 | 354 | 261 | 58% | 1,00 |
| Itaú PN | ITUB | ITUB4 | 1 | 169 | 175 | 49% | 1,00 |
| Bradesco PN | BBD | BBDC4 | 1 | 99 | 122 | 45% | 0,99 |
| Ambev | ABEV | ABEV3 | 1 | 67 | 75 | 47% | 0,99 |
| Embraer | **EMBJ** (antigo ERJ) | EMBJ3 | 4 | 89 | 90 | 50% | 4,00 |
| Sabesp | SBS | SBSP3 | 1 | 35 | 80 | 30% | 1,00 |
| Gerdau PN | GGB | GGBR4 | 1 | 57 | 41 | 58% | 1,00 |
| Suzano | SUZ | SUZB3 | 1 | 23 | 50 | 31% | 1,00 |
| Ultrapar | UGP | UGPA3 | 1 | 22 | 65 | 25% | 1,01 |
| Santander BR | BSBR | SANB11 | 1 unit | 17 | 22 | 44% | 1,00 |
| Telefônica BR | VIV | VIVT3 | **2 (implícito)** [V] | 14 | 27 | 34% | 2,00 |
| TIM | TIMB | TIMS3 | 5 | 9 | 28 | 25% | 5,02 |
| Cemig PN | CIG | CMIG4 | 1 | 9 | 27 | 26% | 0,98 |
| CSN | SID | CSNA3 | 1 | 4 | 16 | 19% | 0,98 |
| Banco do Brasil | BDORY (OTC) | BBAS3 | 1 | 1,7 | 104 | 2% | 1,01 |
| América Móvil B | AMX | AMXB | 20 | 49 | 35 | 58% | 20,2 |
| FEMSA | FMX | FEMSAUBD | 10 units | 51 | 23 | 69% | 10,1 |
| Coca-Cola FEMSA | KOF | KOFUBL | 10 units | 13 | 5,5 | 71% | 10,1 |
| Cemex | CX | CEMEXCPO | 10 CPOs | 68 | 24 | 74% | 10,0 |
| Televisa | TV | TLEVISACPO | 5 CPOs | 2,3 | 1,4 | 63% | 5,1 |
| ASUR | ASR | ASURB | 10 | 16 | 8,8 | 65% | 10,1 |
| GAP | PAC | GAPB | 10 | 28 | 20 | 58% | 10,1 |
| OMA | OMAB | OMAB | 8 | 8,3 | 8,3 | 50% | 8,1 |
| Banorte | GBOOY (OTC) | GFNORTEO | 5 | 1,7 | 54 | 3% | 5,1 |
| Walmex | WMMVY (OTC) | WALMEX | 10 | 3,6 | 37 | 9% | 10,1 |
| Southern Copper | SCCO (NYSE) | SCCO (BMV/BVL) | 1 | 202 | ~0 | ~100% | 1,05 |
| SQM B | SQM | SQM-B | 1 | 66 | n/d | — | 0,97 |
| Banco de Chile | BCH | CHILE | 200 | 11 | n/d [V] | — | ~191 [V] |
| Santander Chile | BSAC | BSANTANDER | 400 | 9,6 | n/d [V] | — | ~384 [V] |
| LATAM | LTM | LTM | 2000 | 36 | n/d | — | ~1.897 [V] |
| Bancolombia/Grupo Cibest | CIB | PFCIBEST | 4 | 25 | 6,6 | 79% | 4,07 |
| Ecopetrol | EC | ECOPETROL | 20 | 31 | 18 | 63% | 20,4 |
| Credicorp | BAP (NYSE) | BAP (BVL) | 1 | 102 | ~0,2 | ~100% | 1,00 |
| Buenaventura | BVN | BUENAVC1 | 1 | 29 | n/d | — | — |
| YPF | YPF | YPFD | 1 | 52 | dado inconsistente [V] | — | — |
| Galicia | GGAL | GGAL | 10 | 34 | 9,1 | 79% | 9,38 (ao câmbio oficial) |
| Macro | BMA | BMA | 10 | 21 | 1,8 | 92% | 9,37 |
| Pampa | PAM | PAMP | 25 | 13 | 3,3 | 80% | 23,4 |
| BBVA Argentina | BBAR | BBAR | 3 | 8,2 | 1,1 | 88% | 2,80 |

Notas:
- **Argentina:** usando o *ratio* nominal, o câmbio implícito nos pares ADR/local é de **~ARS 1.626/USD (CCL implícito, mediana de 10 pares) contra ARS 1.524,9 oficial**, um *gap* de **~6,7%** em 02/10/2026 **[C]**.
- **Chile e Peru (linhas locais):** o feed do Yahoo veio com volume zero e preço congelado, então não serve. Precisa de fonte alternativa (Bloomberg, nuam ou Bolsa de Santiago/BVL) **[V]**.
- Os pares brasileiros implicam USD/BRL entre 5,18 e 5,32, contra spot de 5,2226 **[C]**. As divergências pequenas vêm de horários de fechamento diferentes.
- **Tickers que mudaram e quebram pipelines:** o ADR da Embraer agora é **EMBJ**; a Eletrobras é **AXIA3** na B3 e o ADR antigo (EBR) não retorna dados no Yahoo; Bancolombia virou **Grupo Cibest (PFCIBEST/CIBEST)**; BRF + Marfrig = **MBRF3** **[C/V]**.

### 2.2 Horários de negociação e sobreposição (medidos pelos timestamps intradiários de 02/10/2026, EUA em horário de verão) [C]

| Mercado | Sessão contínua (UTC) | Hora local | Sobreposição com NYSE (13:30-20:00 UTC) |
|---|---|---|---|
| NYSE/Nasdaq (ADRs) | 13:30-20:00 | 09:30-16:00 ET | — |
| B3 | ~13:00-19:55 (+ call de fechamento até 20:00) | 10:00-16:55 BRT [F, 18]; futuros de índice 09:00-18:25 [F, 18]; pré-abertura 09:45 e after-market 17:30-18:00 [NÃO VERIFICADO: não constam da fonte 18] | ~6h25 |
| BMV | 13:30-20:00 | 07:30-14:00 CDMX (alinhada à NYSE; o México não tem mais horário de verão) | 6h30 (integral) |
| BVC (Colômbia) | 13:30-20:00 | 08:30-15:00 Bogotá | 6h30 (integral) |
| BYMA (Argentina) | 14:00-20:00 | 11:00-17:00 ART | 6h00 |
| Bolsa de Santiago | 12:30-19:00 | 09:30-16:00 (Chile em horário de verão) | 5h30 |
| BVL (Peru) | n/d [V] | 09:30-15:52 (RBC, 2023) [F/V, 21] | ~integral |

- A B3 **ajusta o horário duas vezes por ano acompanhando o horário de verão dos EUA** **[F, 18]**. No horário-padrão dos EUA (a partir do início de novembro), o pregão regular volta a ir até ~17:55 BRT.
- **[I] Implicação para o rebalanceamento de segunda-feira:** concentrar a execução na janela de sobreposição (13:30-19:55 UTC no horário de verão dos EUA). Isso permite usar ADR e linha local na mesma janela e fazer hedge com EWZ/EWW/futuros enquanto ambos estão abertos.

### 2.3 Ciclo de liquidação

| Mercado | Ciclo | Fonte |
|---|---|---|
| EUA (ADRs, ETFs) | T+1 desde 28/05/2024 | [F, 20] |
| México (BMV/BIVA e SIC) | T+1 desde 27/05/2024 (antes T+2 desde 2017) | [F, 20] |
| Brasil (B3, ações) | **D+2**; migração para D+1 prevista para **fev/2028** | [F, 19] |
| Argentina (BYMA) | T+0/T+1 por acordo (T+1 é o padrão) | [F/V, 21] |
| Chile | T+2 (PH/PM permitidos) | [F/V, 21] |
| Colômbia | T+2 | [F/V, 21] |
| Peru | T+2 | [F/V, 21] |

**[I]** O descasamento T+1 (ADR) contra D+2 (B3) cria **necessidade de *funding* de um dia** em pares ADR/local e em trocas de linha. O módulo de caixa precisa projetar as liquidações por mercado.

### 2.4 Conversibilidade cambial e registro de investidor estrangeiro

- **Brasil.** A **Resolução Conjunta BCB/CVM nº 13 (03/12/2024)**, em vigor desde **01/01/2025**, **revogou a Res. CMN 4.373/2014** **[F, 6]**.
  - Extinguiu o **RDE-Portfólio** e a obrigatoriedade de **operações de câmbio simultâneas**.
  - Dispensou a nomeação prévia de custodiante e permite **conta em reais de não residente** em instituições de pagamento e corretoras.
  - Ampliou os ativos elegíveis a programas de DR **[F, 6]**.
  - A dispensa de representante vale para **pessoas físicas** em casos específicos (recursos próprios, ou conta em reais com limite de R$ 2 mm/mês por intermediário). Para um **fundo institucional**, o cadastro na CVM/B3, o CNPJ e um intermediário/custodiante seguem necessários na prática **[F, 6, 21; V para detalhes pós-2025]**.
  - O BRL é de câmbio flutuante e conversível *onshore*; *offshore* ele é negociado via **NDF** **[I, prática de mercado]**.
- **IOF-câmbio.** O Decreto 12.499/2025 manteve **alíquota zero** no ingresso de não residente para aplicação no mercado financeiro e de capitais, no **retorno** desses recursos e na remessa de dividendos e JCP **[F, 7]**. A regra geral de outras operações passou a 3,5% (saída) e 0,38% (entrada) **[F, 7]**. Isso é irrelevante para a conta de portfólio, desde que o enquadramento esteja correto **[I]**.
- **México.** Sem controles de câmbio; MXN é *free float* e entregável **[F, 21]**. Ações série "A" com restrição a estrangeiros são acessadas via fideicomisso neutro (NAFIN) **[F, 21]**.
- **Chile.** Registro pelo Capítulo XIV (Compêndio de Normas de Câmbio). O câmbio passa pelo mercado formal e há restrição à especulação com moeda local por não residentes **[F, 21]**.
- **Colômbia.** O investidor de portfólio estrangeiro se registra no Banco de la República via custodiante local, e operações especulativas de câmbio são vedadas a não residentes **[F, 21]**.
- **Peru.** PEN livremente conversível; exige código CAVALI (RUT) **[F, 21]**.
- **Argentina.** Os controles para pessoas físicas foram levantados em abr/2025, mas **persistem para empresas e para investidores não residentes** **[F, 38]**.
  - Em 2026 houve flexibilizações. A **RG CNV 1128 (abr/2026)** permite enviar ao exterior títulos mantidos por **≥ 365 dias** sem o teto diário de ARS 200 mm, com exceção específica para não residentes **[F, 38]**. O suposto fim do prazo mínimo de permanência de 6 meses para investimento financeiro de não residente via MLC não consta das fontes citadas **[NÃO VERIFICADO]**.
  - A Com. "A" 8417 (abr/2026) eliminou o limite de USD 50 para saques no exterior. Em certas transferências de divisas ao exterior, passou a exigir declaração do cliente de **não comprar títulos em USD por 90 dias** **[F, 38]**. A "restrição cruzada" geral de 90 dias (quem compra no oficial não opera nos mercados financeiros) segue vigente **[F, 38 — Infobae 11/03/2026]**.
  - **[I] Conclusão operacional:** para um fundo offshore, **Argentina = ADRs em Nova York**.

### 2.5 Tributos (não residente) [F salvo indicação]

| País | Dividendos | Outros proventos | Ganho de capital em bolsa (não residente) |
|---|---|---|---|
| Brasil | **10% de IRRF desde 01/01/2026** (Lei 15.270/2025), qualquer valor e qualquer residência. Isenção de transição para lucros até 2025 com distribuição aprovada até 31/12/2025. Crédito "análogo" se a carga efetiva combinada passar de 34% (geral), 40% (seguradoras/financeiras) ou 45% (bancos) [F, 8] | **JCP: 15%** (25% para jurisdição de tributação favorecida). A MP 1.303/2025 previa 20%; **verificar a alíquota vigente** [V] | Em regra **isento** para não residente fora de paraíso fiscal (regime de portfólio) [I/V] |
| México | 10% (redução por tratado com documentação) [F, 21] | — | 10% em bolsa; 0% com tratado [F, 21] |
| Chile | 35% com crédito do imposto de 1ª categoria: 100% para países com tratado, 65% para os demais [F, 21] | — | Institucional isento se cumprir requisitos; não institucional 10% (art. 107, desde fev/2022) [F, 21] |
| Colômbia | 20% para não residentes (desde 01/01/2023); alíquotas maiores se distribuído de lucros não tributados [F/V, 21] | — | Regime específico de portfólio [V] |
| Peru | 5% [F, 21] | — | 5% em bolsa [F, 21] |
| Argentina | 7% (lucros a partir de 2018/2021; RBC cita 13%/7%) [V, 21] | — | Regime e isenções mudaram várias vezes [V] |
| ADRs | Retenção do país de origem aplicada na fonte | Taxas do depositário (custódia/dividendo) por ADS [I/V] | — |

**[I] Implicações de modelagem:**
1. O retorno esperado dos longs deve ser **líquido de retenção**.
2. O short paga ao doador o **dividendo/JCP integral**: na B3 o tomador é debitado do valor **bruto** e o doador recebe o líquido conforme o tipo de investidor **[F, 9]**.
3. Shorts em pagadores de dividendos altos (bancos, utilities, Petrobras) carregam **custo de carregamento ≈ dividend yield bruto + taxa de aluguel**. Isso deve entrar no *alpha net-of-costs*.

### 2.6 Como fundos profissionais escolhem a linha de execução [I, prática de mercado sintetizada]

1. **Liquidez e custo total:** spread + corretagem + impacto + conversão de câmbio + taxa de ADR + tributos. Regra prática: **usar como linha principal a que tem ≥ 50% da liquidez combinada** (tabela 2.1). PBR ON, VALE, GGB, AMX, FMX, CX e CIB → ADR. PETR4, SBSP3, UGPA3, SUZB3, CMIG4 e BBAS3 → local.
2. **Disponibilidade e custo de *borrow*:** para shorts, comparar o aluguel no BTC (B3) com o *borrow* do ADR no PB. Ver também se o PB oferece **swap sintético** (comum em fundos offshore, porque elimina registro local e entrega financiamento e *borrow* num só contrato).
3. **Janela de notícias:** o ADR negocia após o fechamento local e reage a eventos dos EUA (resultados após o fechamento, Fed).
4. **Operacional:** ADR liquida T+1 em USD via DTC, sem conta local; a linha local exige custódia, representante e câmbio.
5. **Arbitragem e conversão:** a criação/cancelamento de ADR (taxas tipicamente de até US$ 0,05/ADS **[V]**) permite trocar de linha. Quando o *borrow* do ADR aperta, o PB pode criar ADRs a partir de ações locais emprestadas.
6. **Restrições estruturais:** Argentina só via ADR. Peru/Credicorp/SCCO via NYSE. Banorte, Grupo México e Walmex só via linha local (ADRs OTC ilíquidos).
7. **Política proposta:** guardar no cadastro de cada emissor `primary_line`, `secondary_line`, `adr_ratio`, `adr_share_liquidity` e `borrow_line_preference`. Recalcular mensalmente a partir dos ADTVs e congelar a escolha no *snapshot* semanal (hash).

---

## 3. Venda a descoberto e empréstimo de ações (item c)

### 3.1 Brasil: B3 BTC (Banco de Títulos)

**Mecânica [F, 9]**
- A **B3 é contraparte central** do empréstimo.
- **Taxa:** negociada livremente, capitalizada em 252 dias úteis e paga no vencimento ou na liquidação antecipada. Taxa da B3: **0,25% a.a. do tomador** (mínimo R$ 10), ou **0,50% a.a.** no empréstimo automático.
- **Prazo:** mínimo de 1 dia, sem máximo. Liquidação mínima em T+1.
- **Tipos de contrato:** **reversível pelo tomador** e **reversível pelo tomador e pelo doador** (*recall*).
- **Recall:** pedido do doador até 09:30 → o tomador devolve até **10:00 de T+2**. Pedido após 09:30 → até **10:00 de T+3**.
- **Proventos:** dividendos e JCP são reembolsados ao doador (o tomador paga bruto). Direito a voto vai para o tomador. Subscrições e OPAs têm procedimentos e janelas próprias.
- **Falha de entrega:** multa → postergação → ***buy-in*** → liquidação financeira.
- **Venda a descoberto:** só é permitida para ativos do programa de empréstimo. Falhas pagam multa mínima de **0,5% (limitada a R$ 50 mil)**, com multas adicionais em reincidência **[F, 21]**.
- **Regra de preço:** **não há *uptick rule*** **[F, 21]**. Leilões e túneis de preço da B3 limitam saltos **[I]**.

**Limites de posição em aberto (página da B3 consultada em 05/10/2026) [F, 10]**
- **Fórmula:** Limite1 = mín[Pcirc × FF ; máx(P1 × Q ; L1)] e Limite2 = mín[Pcirc × FF ; máx(P2 × Q ; L2)], com P1 = 25 e P2 = 50, FF = ações em circulação do Formulário de Referência e Q = mediana da quantidade negociada.
- **Por comitente ou grupo:** **Pcirc = 10% do free float** no empréstimo (tomador), no termo e em opções.
- **Mercado como um todo:** **35% do free float** no empréstimo. Limites customizados vigentes em 05/10/2026: **BHIA3 50%, SOJA3 50%, MOVI3 45%, RAIZ4 40%**.
- **Excesso:** gera **margem adicional** de 11% a 54% sobre o Limite 1, conforme os dias para liquidar, e **100% sobre o Limite 2**.
- **Histórico:** em 2022 o teto de mercado era 25% do free float (elevado para 30% no caso IRB), e a imprensa citava 5% do free float por investidor **[F, 11]**. As regras mudam, então **o sistema deve ler os parâmetros vigentes, não codificá-los fixos** **[I]**.

**Tamanho e taxas observadas**
- O mercado de aluguel na B3 somou **R$ 347,1 bi em 2025 (+51% a/a)** **[F, 16 — via resumo, página com acesso bloqueado; V]**.
- Faixa típica: **0,03%-5% a.a.** nos nomes líquidos; **50%-100%+ a.a.** em nomes muito disputados **[F, 17]**.
- O Brasil é descrito como mercado de *specials*, com taxa média acima de 100 bp **[F, busca B3 FAQ/SFT; V]**.
- **Fotografias recentes:**
  - **18/11/2025:** Hapvida 39,1% a.a., short de 15,7% das ações em circulação (R$ 1,28 bi), *days to cover* subindo de 8 para 12,48 em uma semana; Ambipar (em RJ) **105,3% a.a.**, a maior da B3 **[F, 14]**.
  - **28/01/2026:** maiores taxas CPFE3 28,1%, RAIZ4 26,7%, CSDE3 26,6%; PCAR3 e MGLU3 a 19%. Maior *short interest*: **Casas Bahia 42,5%, Raízen 32%, Boa Safra 28,6%** **[F, 15]**.
- **[I] Faixas de trabalho para o Brasil:**
  - GC: ≤ 1% a.a. (taxa doador) + 0,25% B3.
  - *Warm*: 1%-5%.
  - *Hard-to-borrow*: > 5%.
  - *Special/squeeze zone*: > 15%-20%.
- **[I] Selic alta (13,75%)** aumenta o custo de oportunidade do doador. Ao mesmo tempo, o fundo que vende a descoberto e mantém a garantia em títulos públicos (LFT) **recebe a Selic sobre o colateral**, o que é economicamente relevante para a conta de *carry* em BRL.

### 3.2 México

- **Permitido, com empréstimo prévio obrigatório.** *Naked short* é proibido. A corretora deve verificar a disponibilidade, e a regra alcança ações de **alta e média negociabilidade** **[F, 24]**.
- **Quem empresta:** **apenas bancos e corretoras mexicanos** atuam como doador, tomador ou intermediário. Custodiantes estrangeiros não participam diretamente **[F, 24]**.
- **Infraestrutura:** Indeval Valpre (desde 1997), Accipresval (2002) e Circular Banxico 1/2004, atualizada pela **Circular 16/2024** **[F, 21, 23]**.
- **Regra de preço:** o RBC não menciona *uptick rule* **[F, 21]**. A regra da BMV para a modalidade "venta en corto" deve ser checada **[V]**.
- **[I] Na prática:** oferta de empréstimo limitada (Afores e fundos locais emprestam pouco). Fundos offshore fazem short via **ADRs (AMX, FMX, CX, KOF, ASR, PAC, OMAB)**, swaps de PB ou **EWW/futuro do IPC**.

### 3.3 Chile

- **Permitido.** "Venda curta" é a venda em bolsa de valores obtidos em empréstimo (Lei 18.045, Título XXII; NCG 187) **[F, 22]**.
- **Regra de preço (tick rule):** "a venda curta só pode ser feita a **preço maior que o da última transação**", exceto quando a última transação teve preço maior que a anterior, caso em que pode sair **ao mesmo preço** **[F, 22]**.
- **Ativos elegíveis:** só ações selecionadas por presença, volume e comportamento de preço (Lista A) **[F, 21, 22]**.
- **Garantia:** mínima de **100%** do valor emprestado + diferenças diárias (a Bolsa pode exigir mais; o RBC cita 125%).
- **Prazo e divulgação:** prazo de até **360 dias**. A Bolsa publica periodicamente as posições curtas e pode fixar limites máximos por papel **[F, 21, 22]**.
- **[I] Na prática:** pouca oferta e pouco ADTV local. Short via **SQM, BCH, BSAC, LTM** (ADR) ou **ECH**.

### 3.4 Colômbia

- **Permitido**, desde que o investidor tenha recebido o título via **TTV (Transferência Temporária de Valores), simultânea ou repo antes da liquidação** **[F, 21, 26]**.
- **Regras da TTV:** prazo máximo de 1 ano, garantias administradas pela BVC/CRCC, receptor paga prêmio ao originador **[F, 26]**.
- **[I] Na prática:** liquidez local mínima (mediana US$ 0,9 mm/dia). Short **só via EC/CIB (ADRs) ou COLO**, com tamanho pequeno.

### 3.5 Peru

- **Permitido** para ações da Tabela de Valores de Referência, com empréstimo de valores pela BVL (Lei 30.052, até 360 dias) **[F, 21, 25]**.
- **Regra de preço:** a venda a descoberto deve ser executada a **preço igual ou superior ao último preço** **[F, 25]**.
- Houve reforma de negociação na BVL (Res. SMV 018-2025) **[F, 25]**.
- **[I] Na prática:** short via **BAP, SCCO, BVN, IFS** (NYSE) ou EPU (ilíquido, US$ 2,9 mm/dia).

### 3.6 Argentina

- **Localmente:** short só por corretoras locais com empréstimo do programa do Merval/BYMA na data da operação. O programa existe sobretudo para cobrir falhas **[F, 21]**.
- **[I] Conclusão:** short **apenas via ADR nos EUA**, com limites de tamanho severos por causa do risco de *gap* (Seção 4.2).

### 3.7 ADRs e linhas listadas nos EUA

- **Regulation SHO [F, 27]:**
  - **Locate** (Rule 203(b)): o broker precisa de base razoável para crer que o papel pode ser emprestado.
  - **Close-out** (Rule 204): falha em short fechada até a abertura do pregão do dia seguinte à liquidação.
  - **Circuit breaker** (Rule 201): queda ≥ **10%** no dia ativa o teste de preço (*alternative uptick*) **pelo resto do dia e no dia seguinte**.
  - **Threshold securities:** FTD ≥ 10.000 ações e ≥ 0,5% das ações por 5 pregões.
- **Short interest:** a FINRA publica duas vezes por mês **[I]**. O novo relatório Rule 13f-2/Form SHO teve o *compliance* adiado; **verificar a data vigente** **[V]**.
- **[I] Borrow:** ADRs *large cap* (PBR, VALE, ITUB, BBD, ABEV, AMX, FMX, CX, BAP, SCCO) costumam ser GC no PB (≈ 0,25%-0,50% a.a.). ADRs pequenos e argentinos podem virar HTB em episódios. **Coletar a taxa do PB diariamente; não há fonte pública confiável gratuita** (as tentativas de acesso a agregadores públicos foram bloqueadas) **[V]**.

### 3.8 Regras de divulgação (resumo) [I/V]

- **Brasil:** a B3 publica diariamente posições em aberto de empréstimo por ativo (agregado). O regime de participação relevante (Res. CVM 44, faixas de 5%) é voltado a participações acionárias e derivativos equivalentes; o tratamento de posições vendidas precisa ser confirmado **[V]**. Pelo que levantamos, **não há regime público de divulgação individual de short** comparável ao europeu (0,5%) **[I/V]**.
- **Chile:** a Bolsa divulga posições curtas periodicamente **[F, 22]**.
- **EUA:** sem divulgação individual pública hoje; existe agregado FINRA **[I]**.

---

## 4. Risco de *short squeeze* (item d)

### 4.1 Episódios documentados

| Episódio | O que aconteceu | Números |
|---|---|---|
| **Ambipar (AMBP3), mai-dez/2024** | Controlador (Tércio Borlenghi Jr., **72,68%**) + Trustee DTVM (ligada a Nelson Tanure, **~15%**) + recompras secaram o free float; aluguel em **três dígitos**; CVM e mercado viram suspeita de manipulação [F, 12, 13] | De ~R$ 8 (mai/24) para pico de **R$ 268 (dez/24)** (~33×); **+718,9% em 2 meses**; queda de 27,7% em 13/08/2024 [F, 12, 13]. Depois **recuperação judicial**, **-61,5% em 02/10/2025** e mínima ~-99% em nov/2025 (preços ajustados) [C]; aluguel 105,3% a.a. em nov/2025 [F, 14] |
| **IRB (IRBR3), 2022** | Short em **25,1% do free float** (316 mm de ações), perto do teto de mercado de 25% (a B3 elevou para 30%); aluguel de 20% → **45% a.a.** em um mês; risco de cobertura se a capitalização saísse sem desconto forte [F, 11] | Maior alta diária do 2º semestre de 2022: **+24,7% em 21/12/2022** [C]. Não atribuímos causa específica a esse dia [I] |
| **Hapvida (HAPV3), nov/2025** | Short de 8,1% → **15,7% das ações em circulação** em uma semana; *days to cover* 8 → 12,5; aluguel **39,1%** [F, 14] | Exemplo de "crowding" rápido: risco de squeeze em notícia positiva [I] |
| **Casas Bahia / Raízen / Boa Safra, jan/2026** | *Short interest* de **42,5% / 32% / 28,6%**; Raízen com aluguel de 26,7% [F, 15] | Nomes em zona proibida para novos shorts pelos nossos limites [I] |
| **Argentina, PASO 12/08/2019** | Choque político negativo | GGAL **-56,1%**, BMA -52,7%, PAM -53,8%, BBAR -55,9%, YPF -34,1%, ARGT -24,4% [C] |
| **Argentina, vitória de Milei em 20/11/2023** | Choque positivo (squeeze em shorts) | YPF **+39,9%**, BMA +20,2%, BBAR +18,6%, PAM +17,9%, GGAL +17,2% [C] |
| **Argentina, eleição da Prov. de Buenos Aires em 08/09/2025** | Choque negativo | GGAL -23,6%, BMA -23,5%, BBAR -24,4%, PAM -16,7%, YPF -15,3% [C] |
| **Argentina, *midterms* de 27/10/2025** | LLA com ~41% dos votos [F, 39] | BBAR **+40,8%**, GGAL +38,7%, BMA +37,6%, YPF +23,8%, PAM +23,7%, ARGT +18,8% [C] |
| **Brasil, 1º turno em 03/10/2022** (surpresa vs. pesquisas) | Estatais e bancos dispararam | PBR **+12,6%**, ITUB +10,9%, BDORY +10,4%, EWZ +9,9%, PETR4 +8,0%, BBAS3 +7,6%, Ibovespa +5,5% [C] |
| **Brasil, 2º turno em 31/10/2022** | Reversão nas estatais | PETR4 -8,5%, PBR -4,7%, BBAS3 -4,6%; ITUB +5,4% [C] |
| **México, cancelamento do NAIM em 29/10/2018** | Choque regulatório | OMAB -9,4%, GFNORTEO -8,6%, PAC -7,8%, EWW -7,1% [C] |
| **México, eleição em 03/06/2024** (supermaioria) | Choque político | PAC **-13,2%**, GFNORTEO -11,2%, EWW -10,7%, ASR -10,1% [C] |
| **Chile, vitória de Boric em 20/12/2021** | Choque político | SQM -15,3%, ECH -11,0%, BSAC -8,3%, BCH -7,8% [C] |
| **Peru, Castillo em 07/06/2021** | Choque político | BAP -9,9%, EPU -8,5%, BVN -7,3% [C] |
| **Colômbia, vitória de Petro em 21/06/2022** | Choque político | EC -11,0%, COLO -8,0%, CIB -5,3% [C] |

**Lição [I]:** em LatAm, o "squeeze" mais frequente **não é técnico, como no caso GameStop. É político ou corporativo**: eleição, controlador comprando, OPA, capitalização ou reestruturação. Os limites precisam cobrir **concentração de controle, catalisadores com data e gaps de evento**, não só *short interest*.

### 4.2 Métricas usadas por profissionais e como medi-las aqui

| Métrica | Definição operacional | Fonte de dado |
|---|---|---|
| **SI / free float** | Ações em aberto no BTC ÷ ações em circulação (Formulário de Referência) | B3 (posições em aberto diárias) [I]; FINRA para ADRs |
| ***Days to cover* (DTC)** | Ações vendidas ÷ ADTV em ações (mediana 20-63 dias) | B3 + ADTV calculado |
| **Taxa de aluguel e variação** | Taxa média do tomador; Δ em 5 e 20 dias | B3 / PB |
| **Utilização** | Ações emprestadas ÷ oferta disponível para empréstimo | PB / provedores pagos (B3 não publica oferta) [V] |
| **Proximidade do teto B3** | SI de mercado ÷ limite de mercado (35% FF, ou o customizado) | B3 [F, 10] |
| **Concentração de controle** | % do controlador + acordos de acionistas + top-5 holders; free float | Formulário de Referência / CVM |
| **Catalisadores datados** | Resultado, AGE, OPA, M&A, recompra, *follow-on*, rebalanceamento de índice, vencimento de opções, eleição | Calendário corporativo + agenda política |
| **Crowding de hedge funds** | Sobreposição de shorts com fundos locais (CDA/CVM mostra "Obrigações por ações recebidas em empréstimo") | CVM CDA [F, 42] |
| **Gap histórico de evento** | Pior retorno de 1 dia em eventos similares (tabela 4.1) | Yahoo / histórico interno |

### 4.3 Limites práticos propostos [I, calibrados com os episódios acima]

| Métrica | Verde (normal) | Amarelo (tamanho ≤ 50% do normal + aprovação do PM) | Vermelho (proibido abrir / reduzir) |
|---|---|---|---|
| Taxa de aluguel (a.a., tomador, sem a taxa B3) | ≤ 1% | 1%-5% | > 5% em novos shorts (tolerar até 10% em posição existente, com teto de 0,5% do PL) |
| Δ da taxa em 5 dias | < +3 p.p. e < 2× | +3 a +10 p.p. ou 2×-3× | > +10 p.p. ou > 3× |
| SI / free float | ≤ 10% | 10%-20% | > 20% (ou > 70% do teto de mercado B3) |
| *Days to cover* | ≤ 5 | 5-10 | > 10 |
| Free float | ≥ 35% | 20%-35% | < 20%, ou controlador ≥ 70%, ou "aliado" acumulando > 5% em 3 meses |
| Catalisador datado | > 10 pregões | 5-10 pregões | ≤ 5 pregões, ou OPA/M&A/capitalização em curso |
| Eventos políticos binários | — | País com eleição em ≤ 30 dias: gross ≤ 50% do normal | Argentina: short single-name ≤ 0,5% do PL; sem short em estatal brasileira até o 2º turno de 25/10/2026 |
| *Stop* de squeeze | Perda < 15% na posição | Perda de 15%-25%: revisão obrigatória | Perda > 25% ou > 1% do PL: corte compulsório de ≥ 50% |
| Risco de recall (B3) | Contrato só reversível pelo tomador, ou prazo fixo ≥ 30 dias | Contrato com recall | Doador único com > 30% do empréstimo do papel [V: dado disponível só via corretora] |

---

## 5. Câmbio em um book *net neutral* em USD (item e)

### 5.1 Onde nasce a exposição cambial [I]

- **Long local:** USD → moeda local, compra da ação. Exposição **+1** na moeda local.
- **Short local:** venda de ação emprestada. O fundo recebe **moeda local** (que fica como caixa ou colateral) e tem um passivo na mesma moeda. Exposição líquida ≈ **0 no início**, só o P&L do short fica em moeda local, **desde que o caixa não seja convertido para USD**.
- **Book dólar-neutro dentro do mesmo país, autofinanciado** (longs pagos com os recursos dos shorts): exposição cambial ≈ **0 + P&L acumulado**.
- **Pares entre países** (long Brasil / short México): exposição **+BRL / -MXN** pelo valor dos notionais.
- **ADRs:** cotados em USD, mas **economicamente expostos à moeda do ativo subjacente** (o preço do ADR ≈ preço local × ratio ÷ câmbio). **Para risco, ADR = ação local + exposição na moeda local.**
- **Swaps de PB:** exposição = notional líquido por moeda.
- **Regra de sistema:** `fx_exposure[ccy] = Σ (valor de mercado assinado dos ativos cuja moeda de risco é ccy) + caixa em ccy`. Os ADRs mapeiam para a moeda do subjacente.

### 5.2 Níveis atuais de câmbio, juros e vol (para *carry* e risco)

| Moeda | Spot 02/10/2026 [C] | Taxa de política (última decisão) [F] | Diferencial vs. Fed (3,75%-4,00%, ponto médio 3,875%) [I] | Vol realizada 1a [C] | Instrumentos de hedge [I/F] |
|---|---|---|---|---|---|
| BRL | 5,2226 (spot do fechamento: 5,2165 [F, 35]) | Selic **13,75%** (corte de 25 bp em 16/09/2026, 5º corte seguido) [F, 29] | ≈ **+9,9 p.p.** | 11,5% | NDF offshore; DOL/WDO (B3, US$ 50k/10k) [V specs]; CME BRL |
| MXN | 18,3143 | Banxico **6,50%** (mantida em 24/09/2026) [F, 30] | ≈ +2,6 p.p. | 8,3% | Forwards entregáveis; CME MXN |
| CLP | 981,21 | BCCh **4,50%** (mantida em 08/09/2026) [F, 31] | ≈ +0,6 p.p. | 12,0% | NDF |
| COP | 3.318,53 | BanRep **12,25%** (**alta** de 25 bp em 30/09/2026, vigência em 01/10; inflação de 6,2% em agosto) [F, 32] | ≈ +8,4 p.p. | 15,6% | NDF |
| PEN | 3,3491 | BCRP **4,25%** (mantida em set/2026) [F, 33] | ≈ +0,4 p.p. | dado Yahoo anômalo (25%) [V] | NDF |
| ARS | 1.524,9 oficial; **~1.626 CCL implícito** | regime próprio [V] | alto e volátil | — | Hedge offshore restrito; tratar ARS como risco de *gap* [I] |
| USD | — | **Fed: 3,75%-4,00%**, **alta** de 25 bp em 16/09/2026 (12-0) [F, 28] | — | — | — |

**Leitura [I]:**
- Hedgear um **long** em BRL ou COP (vendendo a moeda a termo) custa ~**8-10% a.a.** sobre o notional hedgeado. É proibitivo para posições de prazo longo. **Ficar vendido** em BRL/COP sem hedge, ao contrário, carrega *carry* negativo implícito.
- **A neutralidade por país resolve 90% do problema sem custo.** Hedgear só o **resíduo**, quando a exposição líquida da moeda passar de **2% do PL**.
- O NDF tem taxa implícita *offshore* que pode divergir da Selic/DI (cupom cambial). Para custo exato, usar a curva de NDF ou o cupom cambial da B3 **[V]**.
- **Orçamento de risco:** com vol do BRL a 11,5%, cada 1% do PL de exposição líquida em BRL adiciona ~0,115 p.p. de vol isolada. Limite **|net FX| ≤ 5% do PL por moeda** e **Σ|net FX| ≤ 10%**. Isso mantém a contribuição cambial abaixo de ~0,6-0,8 p.p. num orçamento de 5%.
- A correlação semanal do BRL com o EWZ foi de **-0,47** (BRL fraco ↔ EWZ fraco) **[C]**. Um long em ações brasileiras **não hedgeado** amplifica o beta em USD: a vol do EWZ foi de **25,8%** contra **17,8%** do Ibovespa em BRL **[C]**.

---

## 6. Benchmarks e instrumentos de hedge (item f)

| Instrumento | Exposição | Liquidez (ADTV mediano US$ mm, 63 pregões) [C] | Vol 1a [C] | Beta semanal vs. SPY 1a [C] | Uso sugerido [I] |
|---|---|---|---|---|---|
| **EWZ** | MSCI Brazil (USD) | **789** | 25,8% | 0,49 | Hedge beta Brasil em USD; opções líquidas |
| **BOVA11** | Ibovespa (BRL) | 112 | — | — | Hedge onshore |
| **IND / WIN** (futuro Ibovespa) | Ibovespa, **R$ 1,00/pt e R$ 0,20/pt**; tick de 5 pts; meses pares; vencimento na quarta-feira mais próxima do dia 15 [F, 40] | WIN entre os futuros de índice mais negociados [I] | 17,8% (índice em BRL) | — | Hedge mais barato de beta Brasil. 1 IND ≈ R$ 192 mil ≈ US$ 36,8 mil a 192.114 pts; **US$ 5 mm ≈ 136 IND ≈ 680 WIN** [C] |
| **EWW** | MSCI Mexico | 80 | 22,3% | 0,72 | Hedge beta México |
| NAFTRAC | IPC (BMV) | 7,4 (só BMV) | — | — | Hedge onshore México |
| Futuro do IPC (MexDer) | IPC | n/d | 16,9% (índice) | — | Verificar *specs* e liquidez [V] |
| **ILF** | S&P Latin America 40 | 72 | 23,1% | 0,63 | Hedge regional (correlação 0,94 com EWZ) |
| **ECH** | MSCI Chile | 15 | 25,9% | 1,20 | Hedge Chile (pequeno) |
| **ARGT** | MSCI All Argentina 25/50 | 11 | 33,1% | 1,01 | Hedge Argentina (tamanho limitado) |
| COLO | MSCI Colombia | 5,6 | 23,6% | 0,59 | Ilíquido; GXG não existe mais no Yahoo [C] |
| EPU | MSCI Peru | 2,9 | 32,5% | 1,36 | Muito ilíquido; preferir pares single-name |

Correlações semanais (1 ano) **[C]**: EWZ-EWW **0,60**, EWZ-ECH 0,58, EWZ-ILF 0,94, Ibovespa-EWZ 0,95, EWZ-SPY 0,23 (baixa no período).

**[I] Política de benchmark e hedge:**
1. O benchmark do fundo é **caixa em USD (SOFR/T-bill) + alpha**. O fundo é *market neutral* e não deve ser medido contra o MSCI EM LatAm. Este índice entra **apenas como referência de risco** e para cálculo de beta.
2. O beta deve ser medido contra o **MSCI EM LatAm (proxy ILF)** e contra o **índice do país** (EWZ, EWW etc.). A neutralidade é exigida **por país**, e não só no agregado.
3. **Hedge com índice só para o resíduo de beta.** O núcleo da neutralidade deve vir de shorts *single-name* com fatores casados, porque o alpha "puro" exige neutralizar setor e estilo, não só mercado.
4. **Futuros vencendo:** a rolagem do IND/WIN acontece a cada 2 meses. O próximo vencimento é **14/10/2026**, a quarta-feira mais próxima do dia 15 **[I, pela regra F, 40]**.

---

## 7. O que os L/S LatAm/Brasil efetivamente rodam (item g)

### 7.1 Evidência quantitativa dos fundos brasileiros (CVM Dados Abertos) [C]

**Método:** classes ativas com classificação ANBIMA "Multimercados L/S - Neutro" e "L/S - Direcional" no registro CVM (05/10/2026). Cotas diárias de out/2023 a 02/10/2026. Excluímos *feeders* (FIC/cotas) para não duplicar. CDI do BCB/SGS série 12. A categoria Direcional inclui fundos *long-biased*.

**3 anos (02/10/2023 → 02/10/2026), CDI anualizado = 12,99%**

| Fundo (master) | Categoria | PL (R$ mm) | Retorno a.a. | Excesso sobre CDI a.a. | Vol diária anualizada | Max drawdown |
|---|---|---|---|---|---|---|
| Ibiuna Long Short ST | Neutro | 1.666 | 12,9% | -0,1 p.p. | 8,0% | -11,8% |
| Oceana Equity Hedge | Neutro | 451 | 12,5% | -0,5 p.p. | 5,8% | -4,7% |
| Speedway Long Short | Neutro | 257 | 15,7% | +2,7 p.p. | 3,1% | -1,8% |
| Truxt Long Short | Direcional | 636 | 21,5% | **+8,5 p.p.** | 6,6% | -4,1% |
| AZ Quest Total Return | Direcional | 510 | 20,2% | +7,2 p.p. | 4,5% | -2,8% |
| Itaú Solana L&S | Direcional | 332 | 16,3% | +3,3 p.p. | 3,6% | -3,8% |
| Itaú L&S Plus | Direcional | 45 | 17,1% | +4,1 p.p. | 4,0% | -2,8% |
| AZ Quest Bayes L/S Sistemático | Direcional | 55 | 15,2% | +2,2 p.p. | 8,2% | -9,6% |
| Navi Long Short | Direcional | 67 | 11,2% | -1,8 p.p. | 4,8% | -3,5% |
| Moat Equity Hedge | Direcional | 87 | 8,2% | -4,8 p.p. | 4,9% | -3,5% |

Distribuição dos Direcionais (n = 19, PL ≥ R$ 20 mm, sem *feeders*):
- Excesso anual: mediana **-0,2 p.p.**, IQR **-2,8 a +2,7 p.p.**
- Vol: mediana **5,3%**, IQR 4,2%-7,7%
- Max drawdown: mediana -4,9%

**Últimos 12 meses (out/2025 → out/2026), CDI ≈ 14,4%-14,5%:** os L/S Neutro (16 classes com PL ≥ R$ 20 mm, incluindo *feeders*) renderam **~3,0%-7,8%** na janela 02/10/2025 → 01/10/2026 (último dia disponível no informe diário da CVM), com excesso de **≈ -6,6 a -11,4 p.p.** e vol de 3%-9% **[C, recalculado na verificação]**. A faixa original de 4,1%-8,0% (excesso de -6,5 a -10,4 p.p.) vale só para uma janela que começa em 29/09/2025; o piso (feeders Ibiuna) é sensível a ±2 dias. O período coincidiu com o Ibovespa **+33,5%** em 1 ano (02/10/2025 → 02/10/2026) **[C]** e o MSCI EM LatAm +55,7% em 2025 **[F, 1]**. Ou seja, **shorts sofreram no rali**.

**Exposições em jun/2026 (CDA/CVM, 18 *masters* L/S com PL ≥ R$ 50 mm) [C]:**

| Métrica | P25 | Mediana | P75 | Exemplos |
|---|---|---|---|---|
| Long à vista (% PL) | 53% | 61% | 75% | Moat 80%, XP Long Biased 154% |
| Short via empréstimo (% PL) | 15% | 30% | 51% | Moat 86%, Navi 68%, Ibiuna 56% |
| Gross local (sem futuros e offshore) | 75% | 87% | 127% | XP Long Biased 229% |
| Net local (sem futuros) | +15% | +31% | +46% | Speedway -0,1%, Moat -5,4%, Navi -11,4% |
| Offshore (% PL) | 2% | 11,5% | 17% | Moat 33% |
| Nº de nomes comprados | 38 | 45,5 | 58 | Claritas 81 |
| Nº de nomes vendidos | 15 | 22,5 | 40 | Navi 85, Moat 56 |
| Maior long (% PL) | 4,7% | 6,9% | 9,0% | máximo 13,8% |
| Maior short (% PL) | 2,6% | 3,6% | 5,2% | máximo 7,3% |

**Ressalvas [I]:**
1. O CDA **não captura o notional de futuros** (hedge com IND/WIN aparece só pelo ajuste). Por isso o "net local" de fundos Neutros como Oceana (+45%) superestima o net real.
2. Fundos podem manter posições **confidenciais** por um período.
3. **Viés de sobrevivência:** só fundos ativos hoje.
4. A categoria L/S Neutro é **pequena**: ~R$ 4,2 bi em 16 classes com PL ≥ R$ 20 mm, incluindo *feeders*.

### 7.2 L/S LatAm offshore [V]

Não conseguimos coletar dados primários de fundos offshore de LatAm L/S nesta rodada: o limite de buscas da sessão foi atingido. **[I, conhecimento de mercado, a verificar]** Os veículos offshore costumam:
- rodar gross de 150%-250% e net entre -10% e +30%;
- operar com vol de 6%-12%;
- acessar Brasil e México majoritariamente por ADRs e swaps de PB.

**Próximo passo:** levantar dados do índice HFRI Emerging Markets: Latin America e documentos de oferta de gestores de LatAm L/S.

### 7.3 Tradução para o nosso fundo [I]

- **Vol 5% (banda 3%-7%):** compatível com os melhores pares brasileiros (Truxt 6,6%, AZ Quest TR 4,5%, Solana 3,6%).
- **Alpha realista:** **+2 a +5 p.p. a.a. sobre caixa USD** (IR 0,5-1,0). O topo do mercado brasileiro entregou **+3 a +8,5 p.p.** sobre CDI em 3 anos, com 3,6%-6,6% de vol.
- **Gross esperado:** **130%-200%**, mais alto que o *gross local* mediano dos fundos brasileiros (87%). A razão é que exigimos **neutralidade em dólar e em beta com shorts single-name**, enquanto os brasileiros usam muito futuro de índice e "carregam" net positivo.
- **Número de nomes:** **35-50 longs e 30-45 shorts.** É mais diversificado que a mediana local (45/22) porque o foco é alpha puro com fatores neutralizados.
- **Concentração:** **long ≤ 5% do PL e short ≤ 3% do PL**, alinhado às medianas observadas de 6,9% e 3,6%, mas mais conservador.

---

## 8. Calendário e contexto em 05/10/2026 (itens sensíveis ao tempo)

- **Brasil, eleição:** 1º turno em 04/10/2026, Flávio Bolsonaro (PL) **47,03%** × Lula (PT) **45,16%** dos votos válidos (Wikipedia, com contagens de 56,1 mm × 53,9 mm). Outra fonte publicou 47,50% × 44,61% durante a apuração. **2º turno em 25/10/2026** **[F, 34]**.
- **Pesquisas da véspera:** Datafolha, Lula 45% × Flávio 42% (votos válidos); AtlasIntel, Lula 47% × 44,1% **[F, 36]**. O resultado **surpreendeu as pesquisas**, como em 2022.
- **Mercado antes da eleição:** Ibovespa 192.114,55 (+2,63%, +4,71% na semana), volume de R$ 31,2 bi, USD/BRL 5,2165 **[F, 35]**.
- **Juros:**
  - Selic 13,75% (16/09/2026). O Focus projeta 13,50% no fim de 2026 **[F, 29]**.
  - Fed 3,75%-4,00% (alta em 16/09/2026); o *dot plot* sinaliza mais uma alta em 2026 **[F, 28]**.
  - Banxico 6,50%, BCCh 4,50%, BanRep 12,25% (alta), BCRP 4,25% **[F, 30-33]**.
- **Argentina:** mantida como **Standalone** pela MSCI em 23/06/2026 **[F, 37]**. O controle cambial para empresas continua **[F, 38]**.
- **Vencimentos:** futuro de Ibovespa em 14/10/2026 **[I]**. Opções de ações listadas nos EUA no 3º vencimento de sexta-feira do mês (16/10/2026) **[I]**.
- **[I] Postura sugerida para a carteira inaugural (semana de 05/10):**
  - vol ex-ante alvo **3,5%-4,0%**;
  - **beta Brasil e exposição líquida a estatais ≈ 0**, com o hedge do resíduo via WIN/EWZ;
  - **nenhum short novo** em nomes com SI > 15% ou aluguel > 5%;
  - stress de **±10% para Brasil e ±13% para estatais**, que precisa caber em uma perda de ≤ 1,5% do PL.
  - Revisar após o 2º turno.

---

## 9. Tabela de parâmetros para codificar

Valores **[I]**, salvo marcação. Unidades explícitas. Sugestão de chave YAML entre crases.

| # | Parâmetro (`chave`) | Valor proposto | Racional / fonte |
|---|---|---|---|
| 1 | `fund.base_ccy` | USD | Mandato |
| 2 | `fund.nav_inception_usd` | 100.000.000 | Mandato |
| 3 | `risk.vol_target_annual` | 0,05 (banda 0,03-0,07); **0,035-0,040 até 25/10/2026** | Mandato; eleição BR (Seção 8) |
| 4 | `risk.net_dollar_max_abs` | ≤ 3% do PL | Neutralidade em dólar |
| 5 | `risk.net_beta_max_abs` | ≤ 0,05 (beta vs. ILF/MSCI EM LatAm) | Neutralidade em beta |
| 6 | `risk.country_net_max_abs` | ≤ 5% do PL por país (beta-ajustado ≤ 0,03) | Choques de país de ±10%-55% (Seção 4.1) |
| 7 | `risk.country_gross_max` | BR ≤ 70%, MX ≤ 35%, CL ≤ 15%, PE ≤ 10%, CO ≤ 8%, AR ≤ 10% do **gross** | Liquidez/universo (Seção 1) |
| 8 | `risk.sector_net_max_abs` | ≤ 5% do PL por setor GICS | Alpha puro |
| 9 | `risk.factor_exposure_max_abs` | ≤ 0,10 desvio-padrão (value, momentum, size, quality, low-vol, estatal) | Alpha puro |
| 10 | `risk.fx_net_max_abs_per_ccy` | ≤ 5% do PL; Σ \|FX\| ≤ 10%; hedge do resíduo se > 2% | Vol FX de 8%-16% (Seção 5) |
| 11 | `risk.gross_expected` | 130%-200% (teto 250%) | Vol alvo, idiossincrático de ~25%-30%, N de 60-90 |
| 12 | `pos.max_long_pct_nav` | 5% (rebalancear se > 6%) | Mediana dos pares 6,9% (Seção 7) |
| 13 | `pos.max_short_pct_nav` | 3% (rebalancear se > 4%); HTB ≤ 0,5%-1% | Mediana dos pares 3,6%; squeeze |
| 14 | `pos.max_short_pct_nav_argentina` | 0,5% por nome; Argentina gross ≤ 10% do gross | Gaps de -56% a +41% (Seção 4.1) |
| 15 | `liq.adtv_window_days` | 63 (mediana; usar também 20 dias para alertas) | Robustez |
| 16 | `liq.min_adtv_usd_long` | 5 mm | Capacidade (Seção 1.4) |
| 17 | `liq.min_adtv_usd_short` | 10 mm | Squeeze e recall |
| 18 | `liq.max_pos_pct_adtv_long` | 60% do ADTV (3 dias a 20% de participação) | Liquidação |
| 19 | `liq.max_pos_pct_adtv_short` | 30% do ADTV (2 dias a 15%) | Cobertura forçada |
| 20 | `liq.max_participation_rate` | 15%-20% do volume por dia | Impacto |
| 21 | `liq.book_liquidation` | ≥ 80% do gross em ≤ 3 dias; ≥ 95% em ≤ 5 dias | Prática de risco |
| 22 | `borrow.fee_green_max` | 1% a.a. (BR: taxa do tomador, + 0,25% B3 [F, 9]) | Seção 3.1 |
| 23 | `borrow.fee_red_min` | 5% a.a. para novos shorts; 10% para posição existente | Seção 4.3 |
| 24 | `borrow.fee_spike_red` | +10 p.p. ou 3× em 5 dias | Hapvida/IRB |
| 25 | `squeeze.si_float_yellow` / `red` | 10% / 20% (ou ≥ 70% do teto B3 de 35% do FF [F, 10]) | IRB 25%; Casas Bahia 42,5% |
| 26 | `squeeze.days_to_cover_yellow` / `red` | 5 / 10 | Hapvida 12,5 |
| 27 | `squeeze.free_float_min` | 20% (vermelho); 35% (verde) | Ambipar (controlador 72,7% + aliado 15%) |
| 28 | `squeeze.controller_max` | 70% | Ambipar |
| 29 | `squeeze.catalyst_block_days` | 5 pregões (vermelho); 10 (amarelo) | Resultados, OPA, capitalização |
| 30 | `squeeze.stop_position_loss` | -25% na posição ou 1% do PL → corte ≥ 50% | Disciplina |
| 31 | `recall.b3_notice_days` | 2-3 pregões (pedido antes/depois de 09:30 → devolução 10:00 T+2/T+3) [F, 9] | Planejar cobertura |
| 32 | `settle.cycle` | US 1, MX 1, AR 1, BR 2 (BR 1 a partir de fev/2028 [F, 19]), CL 2, CO 2, PE 2 | Seção 2.3 |
| 33 | `exec.window_utc` | 13:30-19:55 (horário de verão dos EUA); 14:30-20:55 (horário-padrão) | Sobreposição (Seção 2.2) |
| 34 | `exec.primary_line_rule` | Linha com ≥ 50% do ADTV combinado; Argentina → ADR; PE → NYSE | Tabela 2.1 |
| 35 | `tax.div_wht` | BR 10% (desde 01/2026) [F, 8]; JCP 15% [V]; MX 10%; PE 5%; CO 20%; CL 35% com crédito; AR 7% [V] | Seção 2.5 |
| 36 | `stress.event_gaps` | BR ±10% (estatais ±13%); MX -13%; CL -15%; PE -10%; CO -11%; AR -56% / +41% | Seção 4.1 [C] |
| 37 | `stress.max_loss_event_pct_nav` | ≤ 1,5% do PL por cenário de país | Tolerância |
| 38 | `fx.carry_estimate` | Diferencial de política: BRL 9,9, COP 8,4, MXN 2,6, CLP 0,6, PEN 0,4 p.p. (atualizar semanalmente com NDF) | Seção 5.2 |
| 39 | `hedge.instruments` | WIN/IND, EWZ, BOVA11, EWW, ILF, ECH, ARGT (COLO/EPU só residual) | Seção 6 |
| 40 | `hedge.futures_roll` | IND/WIN: meses pares, quarta-feira mais próxima do dia 15 (próximo: 14/10/2026) | [F, 40] |
| 41 | `universe.refresh` | Ratios ADR, tickers e free float mensais; ADTV e aluguel diários; snapshot semanal com hash | Governança (AGENTS.md) |

---

## 10. Lacunas e próximos passos [V]

1. **Taxas de aluguel B3 por ativo (diárias):** a API de arquivos da B3 respondeu, mas não identificamos o nome da tabela de empréstimo. Mapear o arquivo "Empréstimo de Ativos – Posições em Aberto" (taxa média, quantidade, SI) para o `data/real/`.
2. **Borrow de ADRs:** sem fonte pública confiável acessível. Integrar o arquivo do PB (ou IBKR *shortable/fee*) em produção.
3. **Liquidez local de Chile e Peru:** o feed do Yahoo veio congelado. Usar a nuam/Bolsa de Santiago/BVL ou um provedor pago.
4. **Brasil, alíquota de JCP pós-2025 e ganho de capital do não residente:** confirmar com assessor tributário.
5. **México, regra de preço da venda a descoberto na BMV e *specs* do futuro do IPC:** confirmar no regulamento da BMV e da MexDer.
6. **Ratio do ADR VIV (implícito 2:1) e ADR da Eletrobras/Axia:** confirmar no depositário.
7. **Fundos L/S LatAm offshore:** coletar dados do HFRI/Eurekahedge e de documentos de oferta.
8. **Form SHO / Rule 13f-2:** confirmar a data de *compliance* vigente.
9. **Resultado oficial do 1º turno (TSE)** e reação de mercado em 05/10/2026: atualizar no *snapshot* da semana.

---

## Apêndice A — Metodologia dos dados calculados [C]

- **Preços e volumes:** Yahoo Finance via `yfinance` (ambiente `.venv` do projeto), consultado em 05/10/2026. Janela de 25/06/2026 a 02/10/2026.
  - **ADTV** = mediana dos últimos 63 pregões de (Close × Volume) convertido para USD pelo spot do Yahoo do mesmo dia.
  - **Argentina (linha local):** convertida pelo CCL implícito (~1.626).
  - **Razão implícita** = preço do ADR ÷ (preço local ÷ câmbio) no último fechamento disponível.
  - **Limitações:** volumes da BMV sem BIVA; dados de Santiago e Lima congelados; ADR da Cosan com volume zero; YPFD com preço inconsistente.
- **Eventos:** retorno de 1 dia com preços ajustados (`auto_adjust=True`) no primeiro pregão após o evento.
- **Horários:** timestamps de barras de 5 minutos em 01-02/10/2026, convertidos para UTC.
- **Vol, beta e correlação:** log-retornos diários de 01/10/2025 a 02/10/2026 (vol anualizada por √252). Beta e correlação com retornos semanais (sexta-feira).
- **Fundos brasileiros:**
  - Fontes: CVM Dados Abertos `inf_diario_fi_YYYYMM.zip` (set/2023-out/2026), `registro_fundo_classe.zip` (classificação ANBIMA), `cda_fi_202606.zip` (carteiras).
  - CDI: BCB/SGS série 12.
  - Retorno = variação da cota (líquida de taxas). Vol = desvio-padrão diário × √252. *Masters* identificados pela exclusão de nomes com FIC/COTAS/CIC.
  - **Long** = TP_APLIC ∈ {Ações; Ações cedidas em empréstimo; Recibos de depósito; BDR}. **Short** = "Obrigações por ações e outros TVM recebidos em empréstimo".
- Scripts mantidos fora do repositório (scratchpad da sessão). Para reprodutibilidade em produção, devem virar módulos testados em `src/`, conforme o AGENTS.md.

---

## Fontes (numeradas, com data de publicação ou acesso)

1. MSCI — *Index Factsheet: MSCI Emerging Markets Latin America Index (USD)*, dados de 30/09/2026 (PDF gerado em 02/10/2026). https://www.msci.com/documents/10199/5b537e9c-ab98-49e4-88b5-bf0aed926b9b
2. ABES / B3 — "B3 registra volumes recordes durante o primeiro trimestre de 2026" (resultados do 1T26 divulgados em 13/05/2026). https://abes.org.br/en/b3-registra-volumes-recordes-durante-o-primeiro-trimestre-de-2026/
3. InfoMoney — "B3 registra volumes recordes em ações, mas derivativos decepcionam" (14/05/2026; ADTV de abr/2026 de R$ 37 bi). https://www.infomoney.com.br/mercados/b3-registra-volumes-recordes-em-acoes-mas-derivativos-decepcionam-entenda/
4. Seu Dinheiro — "Bolsa 'quebra a banca' com R$ 120 bilhões…" (pregão de 15/04/2026; média do 1T26 de R$ 24,9 bi; 2025 de R$ 18 bi). https://www.seudinheiro.com/2026/bolsa-dolar/b3-bate-recorde-em-cinco-anos-com-giro-de-r-120-bilhoes-em-um-unico-pregao-ccgg/
5. The Rio Times — "Foreign Trading Drove Brazil's Stock Volume in 2025 as Local Institutions Sold" (2026; estrangeiros com 62% do volume em 2025). https://www.riotimesonline.com/foreign-trading-drove-brazils-stock-volume-in-2025-as-local-institutions-sold/
6. Resolução Conjunta BCB/CVM nº 13, de 03/12/2024 (vigência em 01/01/2025): LegisWeb https://www.legisweb.com.br/legislacao/?id=469880 ; Lefosse (alerta, dez/2024) https://lefosse.com/noticias/alerta/bcb-e-cvm-publicam-resolucao-conjunta-que-busca-simplificar-o-acesso-aos-mercados-financeiro-e-de-valores-mobiliarios-por-investidores-nao-residentes/ ; Mattos Filho https://www.mattosfilho.com.br/unico/investimentos-estrangeiros-brasil/
7. Decreto nº 12.499, de 11/06/2025 (IOF): Planalto https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12499.htm ; PwC (jun/2025) https://www.pwc.com.br/pt/consultoria-tributaria-societaria/thinking-about-taxes/tax-legis/2025/iof-alteracoes-decreto-federal-12499-2025.html
8. Mayer Brown — "Sancionada a Lei nº 15.270/2025…" (dez/2025; lei de 26/11/2025). https://www.mayerbrown.com/pt/insights/publications/2025/12/enactment-of-law-no-15270-2025-which-establishes-dividend-taxation-expands-the-exemption-threshold-and-introduces-a-minimum-tax-on-high-incomes
9. B3 — *Securities Lending – Frequently Asked Questions (FAQ)* (PDF, consultado em 05/10/2026). https://www.b3.com.br/data/files/0C/71/18/5F/3317C6106B9896C6DC0D8AA8/Securities_Lending_-_Frequently_Asked_Questions__FAQ_.pdf
10. B3 — "Regras para Limites" (limites de posição em aberto; consultado em 05/10/2026). https://www.b3.com.br/pt_br/produtos-e-servicos/compensacao-e-liquidacao/clearing/administracao-de-riscos/consulta-limites-de-posicoes/regras-para-limites/
11. Brazil Journal — "IRB perto de atingir limite de short; taxa de aluguel bate 45%" (24/08/2022). https://braziljournal.com/irb-perto-de-atingir-limite-de-short-taxa-de-aluguel-bate-45/
12. Seu Dinheiro — "Ambipar (AMBP3) desaba mais de 30% hoje em meio à disputa entre comprados e vendidos" (13/08/2024). https://www.seudinheiro.com/2024/empresas/ambipar-ambp3-desaba-mais-de-30-hoje-em-meio-a-disputa-entre-comprados-e-vendidos-nas-acoes-na-bolsa-e-o-fim-da-disparada-historica-vinp-miql/
13. BPMoney — "Ambipar (AMBP3): com salto de 499% em 2024, ação segue em disparada" (2024/2025). https://bpmoney.com.br/mercado/ambipar-ambp3-salto-em-2024-acao-segue-disparada/
14. InfoMoney — "Taxa de aluguel de ações da Hapvida dispara e passa de 39% ao ano, a 2ª maior da B3" (18/11/2025). https://www.infomoney.com.br/onde-investir/taxa-de-aluguel-de-acoes-da-hapvida-dispara-e-passa-de-39-ao-ano-a-2a-maior-da-b3/
15. InfoMoney — "'Short selling': veja as ações da B3 que estão com mais demanda de aluguel" (28/01/2026). https://www.infomoney.com.br/mercados/short-selling-veja-as-acoes-da-b3-que-estao-com-mais-demanda-de-aluguel/
16. BB InvesTalk — "Aluguel de ações cresce 51% em 2025" (2026; acesso direto bloqueado, dado via resumo de busca) [V]. https://investalk.bb.com.br/noticias/mercado/aluguel-de-acoes-cresce-51-em-2025-conheca-essa-estrategia-e-seus-riscos
17. Renova Invest — "Venda descoberta…" (faixas de taxa e taxa B3; atualizado em 2026). https://renovainvest.com.br/blog/venda-descoberta-entenda-o-que-e-como-funciona-e-seus-riscos/
18. Seu Dinheiro — "A bolsa vai mudar de horário — novo cronograma da B3 a partir de 9 de março" (mar/2026). https://www.seudinheiro.com/2026/bolsa-dolar/b3-b3sa3-muda-horario-de-negociacao-a-partir-de-9-de-marco-veja-como-fica-lvgb/
19. B3 / Bora Investir — "B3 anuncia projeto para redução do ciclo de liquidação de ações para D+1" (2025; vigência prevista para fev/2028). https://borainvestir.b3.com.br/noticias/mercado/b3-anuncia-projeto-para-reducao-do-ciclo-de-liquidacao-de-acoes-para-d1/
20. CCV/AMIB (via DTCC) — anúncio do T+1 no México (2024) https://dtcc.com/ust1/-/media/Files/PDFs/T2/CCV-y-AMIB-T1-Anuncio-Ingles ; Expansión (27/05/2024) https://expansion.mx/mercados/2024/05/27/grupo-bolsa-mexicana-valores-liquidacion-t-1
21. RBC Investor Services — *Global Custody Market Profiles*: Brasil (atualizado em 03/10/2023), Chile (nov/2023), Colômbia (04/01/2023), Peru (31/01/2023), Argentina (27/05/2024), México (s/d). https://www.rbcis.com/en/gmi/global-custody/market-profiles/market.page?dcr=templatedata%2Fglobalcustody%2Fmarketprofiles%2Fdata%2Fbrazil (trocar o sufixo por `chile`, `colombia`, `peru`, `argentina`, `mexico`)
22. Bolsa de Santiago — *Manual de Operaciones de Venta Corta y Préstamo de Acciones* (PDF; consultado em 05/10/2026). http://publish.bolchile.cl/media/recursos/normativas/manuales/manualdeoperacionesdeventacortayprestamos.pdf
23. Banxico — Circular 16/2024 (préstamo de valores). https://www.banxico.org.mx/marco-normativo/normativa-emitida-por-el-banco-de-mexico/circular-prestamo-de-valores/%7B91270794-DF4C-2E1D-D8C8-BF9F664690EE%7D.pdf
24. Lexology — "Equity Derivatives in Mexico" (regras de venda a descoberto e empréstimo). https://www.lexology.com/library/detail.aspx?g=aad80d19-a73d-4464-bf8d-e65494fc63bd
25. BVL — *Reglamento de Operaciones en Rueda de Bolsa* https://s3.us-east-1.amazonaws.com/site.documents.cdn.prod.bvl.com.pe/p11204_10.pdf ; Infobae (13/11/2025, Res. SMV 018-2025) https://www.infobae.com/peru/2025/11/13/smv-reforma-la-negociacion-de-instrumentos-de-renta-variable-y-deuda-en-la-bolsa-de-valores-de-lima/
26. Banco de la República — *Manual Transferencia Temporal de Valores (TTV)* https://www.banrep.gov.co/economia/pli/Manual_Transferencia_Temporal_de_Valores_TTV.pdf ; Superfinanciera (boletim jurídico sobre vendas a descoberto/TTV) https://www.superfinanciera.gov.co/publicaciones/15672/
27. SEC — "Key Points About Regulation SHO". https://www.sec.gov/investor/pubs/regsho.htm
28. Federal Reserve — FOMC Statement, 16/09/2026 (meta de 3,75%-4,00%, 12-0). https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm
29. Itaú — "Copom reduz a Selic para 13,75%…" (16/09/2026) https://www.itau.com.br/investimentos/noticias/copom-corte-selic-1375/ ; O Povo/Focus (28/09/2026) https://opovo.com.br/noticias/economia/2026/09/28/selic-no-fim-de-2026-segue-em-1350-aponta-focus.html
30. El Financiero — "Banxico deja tasa sin cambios en 6.5%" (24/09/2026). https://www.elfinanciero.com.mx/economia/2026/09/24/tasa-del-banxico-hoy-24-de-septiembre-2026-en-cuanto-quedo/
31. Banco Central de Chile — Comunicado RPM de setembro de 2026 (08/09/2026). https://www.bcentral.cl/en/content/-/detalle/prensa/comunicados-rpm/comunicado-rpm-septiembre-2026
32. Banco de la República — decisão de 30/09/2026 (12,25%). https://www.banrep.gov.co/en/news/board-directors/september-2026
33. BCRP — programa monetário de setembro de 2026 (4,25%), via Peru Retail https://www.peru-retail.com/bcrp-mantiene-la-tasa-de-referencia-en-4-25-y-advierte-riesgos-para-la-inflacion/ ; histórico (10/07/2026) https://noticiassin.com/economia/2026/07/10/bcrp-mantiene-tasa-de-referencia-en-425-por-decimo-mes-2055071/
34. Wikipedia — "Eleição presidencial no Brasil em 2026" https://pt.wikipedia.org/wiki/Elei%C3%A7%C3%A3o_presidencial_no_Brasil_em_2026 e "2026 Brazilian general election" https://en.wikipedia.org/wiki/2026_Brazilian_general_election (consultadas em 05/10/2026) [verificar no TSE]
35. Times Brasil (CNBC) — "Ibovespa dispara 2,63% e fecha acima de 192 mil pontos antes das eleições; dólar fica estável a R$ 5,22" (02/10/2026). https://timesbrasil.com.br/investimentos/bolsa/ibovespa-dispara-263-e-fecha-acima-de-192-mil-pontos-antes-das-eleicoes-dolar-fica-estavel-a-r-522/
36. O Povo — Datafolha (03/10/2026) https://www.opovo.com.br/noticias/politica/eleicoes/2026/10/03/datafolha-lula-tem-45-dos-votos-validos-no-1-turno-flavio-bolsonaro-tem-42.html ; CNN Brasil — AtlasIntel https://www.cnnbrasil.com.br/eleicoes/atlas-lula-tem-47-dos-votos-validos-no-1o-turno-flavio-441/
37. MSCI — "MSCI Announces the Results of the MSCI 2026 Market Classification Review" (23/06/2026) https://ir.msci.com/news-releases/news-release-details/msci-announces-results-msci-2026-market-classification-review ; Buenos Aires Herald https://buenosairesherald.com/economics/msci-keeps-argentina-as-standalone-market-without-reclassification
38. Infobae — "El Gobierno aprovechó la calma del dólar para relajar el cepo cambiario" (09/04/2026) https://www.infobae.com/economia/2026/04/09/el-gobierno-aprovecho-la-calma-del-dolar-para-relajar-el-cepo-cambiario/ ; Infobae (11/03/2026) https://www.infobae.com/economia/2026/03/11/cepo-cambiario-el-gobierno-confirmo-que-no-evalua-cambios-en-lo-inmediato-y-explico-por-que-mantiene-las-restricciones/
39. Bloomberg Law — "Argentina's Merval Index Surges Most Since 2023 After Milei Win" (27/10/2025). https://news.bloomberglaw.com/bankruptcy-law/argentinas-merval-index-surges-most-since-2023-after-milei-win
40. B3 — Futuro de Ibovespa https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/futuro-de-ibovespa.htm e Futuro Mini de Ibovespa https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/futuro-mini-de-ibovespa.htm (consultados em 05/10/2026)
41. B3 — "B3 moderniza regras de free float para os segmentos especiais de listagem" (01/02/2023; mínimo de 20%, 15% em exceções; ADTV ≥ R$ 20 mm). https://www.b3.com.br/pt_br/noticias/b3-moderniza-regras-de-free-float-para-os-segmentos-especiais-de-listagem.htm
42. CVM — Dados Abertos: Informe Diário https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/ ; CDA https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/ ; Registro de classes https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip (arquivos de 03-05/10/2026)
43. Banco Central do Brasil — SGS série 12 (CDI diário). https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json
44. Yahoo Finance (via `yfinance`) — preços, volumes e intradiário de 2018-10 a 2026-10-02, consultados em 05/10/2026. https://finance.yahoo.com
