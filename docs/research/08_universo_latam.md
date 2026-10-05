# 08 — Universo investível LatAm (long/short equities): construção e validação com dados reais

| Campo | Valor |
|---|---|
| Documento | `docs/research/08_universo_latam.md` |
| Artefato de dados | `data/universe/latam_universe_draft.csv` (281 linhas × 34 colunas) |
| Data de referência | **segunda-feira, 2026-10-05**. Dados de mercado até o fechamento de **sexta-feira, 2026-10-02** |
| Natureza dos dados | **DADOS REAIS** (Yahoo Finance via `yfinance` 1.7.0, extraídos em 2026-10-05). Nenhum número deste documento é simulado |
| Escopo | Ações líquidas de Brasil, México, Chile, Colômbia, Peru e Argentina (linhas locais e ADRs), mais empresas LatAm-cêntricas listadas nos EUA. Fundo em USD, US$ 100 mi, vol-alvo 5% (banda 3–7%), *net neutral*, rebalanceamento semanal às segundas |
| Convenção de evidência | **[V]** verificado em dado de mercado extraído por nós ou em fonte primária/jornalística identificada. **[I]** inferência ou recomendação nossa |
| Status | **DRAFT** para revisão do gestor. Não é recomendação de investimento |

---

## 0. Sumário executivo

1. **[V] Universo validado: 281 linhas negociáveis de 233 emissores** com ADTV de 3 meses ≥ US$ 2 mi e dados até 2026-10-02.
   - **204 linhas** (167 emissores) têm ADTV ≥ US$ 5 mi. É o "núcleo negociável", dentro da faixa-alvo de 120–200 linhas.
   - **77 linhas** ficam entre US$ 2 e 5 mi (`below_5m = true`).
   - Ponto de partida: 430 linhas candidatas de 333 emissores, descobertas pelo *screener* do Yahoo e por curadoria manual.
   - Descartes: **44 linhas** por ausência de dados, deslistagem ou qualidade de dados, e **105 linhas** por ADTV < US$ 2 mi.
2. **[V] O Brasil domina: 157 linhas e 133 emissores, ~74% do ADTV agregado de US$ 10,8 bi/dia.**
   - Depois vêm México (50 linhas e 41 emissores), Chile (24/19), Argentina (21/17), Colômbia (14/9) e Peru (6/6).
   - Completam: Multi-LatAm (6/5), Panamá (2/2) e Uruguai (1/1).
   - A mediana de ADTV por linha é **US$ 11,7 mi** (p10 = 2,7; p90 = 80,1). A mediana de *market cap* por emissor é **US$ 3,2 bi**.
3. **[V] Eventos corporativos de 2024–2026 foram incorporados e verificados no dado.** Destaques:
   - **Eletrobras → Axia** (AXIA3; os ADRs AXIA e AXIA-P foram **deslistados da NYSE** em jun–ago/2026, com Form 25 e 15F na SEC);
   - **Embraer EMBR3/ERJ → EMBJ3/EMBJ** (03/11/2025);
   - **BRF + Marfrig → MBRF3** (23/09/2025);
   - **Copel**: somente ON (CPLE3) e ADS ELPC = 4 ON;
   - **Cosan**: ADR deslistado da NYSE em 18/09/2026, agora OTC;
   - **Gol** fechou capital (27/03/2026) e **Azul** passou a AZUL3 após o Chapter 11;
   - **Natura**: NTCO3 → NATU3;
   - **JBS**: NYSE desde 13/06/2025, com BDR JBSS32;
   - **Bancolombia → Grupo Cibest** (PFCIBEST/CIBEST, ADR CIB);
   - **Alfa → Sigma Foods** (SIGMAFA);
   - **Petz + Cobasi → AUAU3**;
   - IPOs de **PicPay** (PICS), **Agibank** (AGBK) e **Compass** (PASS3).
4. **[V] Os ratios de ADR foram verificados por preço** com a mediana dos últimos 20 pregões comuns de ADR × FX / local. Dos 36 ADRs não argentinos com linha local líquida (Brasil, México, Chile, Colômbia e Vista), 31 ficaram dentro de ±1% do ratio documentado e todos dentro de ±3,7%.
   - Dois **ratios mudaram sem aviso no ADR**, detectados pelo teste:
     - **YPF**: desdobramento 10:1 local em 03/08/2026, logo 1 ADS = 10 ações D;
     - **VIV**: desdobramento 1:2 de VIVT3 em 15/04/2025, logo 1 ADS = 2 ON.
   - Na Argentina, o ratio implícito fica ~5,5% abaixo do documentado em **todos** os 12 ADRs. Isso equivale a um **CCL ~5,8% acima do câmbio oficial** (ARS=X 1.524,9).
5. **[V] Achados de qualidade de dados que mudam decisões.**
   - **Chile:** o Yahoo tem **lacunas de volume** (só 10–13 de 64 pregões com volume na maioria dos `.SN`). Usamos a média dos dias com volume, sinalizada.
   - **Peru:** as linhas da BVL (`.LM`) vêm como MUTUALFUND/YHD, sem moeda, e foram **excluídas**. A exposição ao Peru fica via linhas nos EUA (BAP, SCCO, BVN, IFS, NEXA, HBM).
   - **Units brasileiras:** o `marketCap` do Yahoo **superestima** units em até ~5×, então corrigimos pelas classes ON/PN.
   - **YPF:** *short interest* no Yahoo inconsistente (72,4 "×"), descartado.
6. **[V] Risco de *short squeeze* mensurável nas linhas dos EUA.** 15 linhas têm *short interest* > 10% do *float* ou *days-to-cover* > 5 (dados de 15/09/2026). Exemplos: AFYA (29% SI; ADTV de apenas US$ 2,8 mi), GLOB (26%; 8,9 dias), GGAL (18%), JBS (17%), AUGO (17%), DLO (14%), PAGS (13%), SCCO (10%; 8,8 dias) e TGLS (10%).
7. **[I] Recomendação para o PM.**
   - Elegibilidade:
     - **long** com ADTV ≥ US$ 2 mi;
     - **short** apenas com ADTV ≥ US$ 10 mi (126 emissores), *borrow* confirmado e sem *flag* de *squeeze*.
   - Tamanho máximo de posição por liquidez:
     - **0,45 × ADTV** no long (3 dias a 15% de participação);
     - **0,30 × ADTV** no short (2 dias).
   - Linhas entre US$ 2 e 5 mi: no máximo ~0,5% do NAV e fora do short.

---

## 1. Escopo e definição do universo

**[I] Definição operacional adotada:**

- **Emissores elegíveis.** São empresas cuja receita, ativos ou risco-país estão predominantemente na América Latina. Classificamos cada um em três *tiers* (coluna `tier`):
  - `CORE`: emissor local com linha em bolsa LatAm e/ou ADR;
  - `US_LATAM`: empresa LatAm-cêntrica listada nos EUA sem linha local relevante (MELI, NU, STNE, PAGS, XP, INTR, VTEX, AFYA, PAX, VINP, DLO, ARCO, CPA, BLX, BAP, SCCO, IFS, TGLS, GLOB, CAAP, AGRO, PICS, AGBK, JBS, AUGO, SGML, ERO, NEXA, LAR, TX, BWMX, GPRK, GTE etc.);
  - `SATELLITE`: emissor estrangeiro, sobretudo mineradoras canadenses, com ativos majoritariamente LatAm (PAAS, AG, EXK, FSM, HBM, LILA/LILAK). É **opcional** e a gestão pode excluí-lo.
- **Linhas.** Uma linha por instrumento negociável:
  - `LOCAL`: B3, BMV, Bolsa de Santiago, BVC e BYMA, incluindo BDRs na B3 quando relevantes (JBSS32 com 1 BDR ≈ 1 ação JBS, implícito 0,998; AURA33 com 3 BDRs ≈ 1 ação AUGO, implícito 3,003);
  - `ADR`: ADS patrocinado listado na NYSE ou Nasdaq;
  - `US_LISTED`: ação ordinária listada nos EUA.
  - Programas apenas OTC (por exemplo, BDORY, WMMVY e os ADRs da Axia e da Cosan pós-deslistagem) **não** entram.
- **País (`country`).** É o **país de risco** (principal geração de receita ou ativos), não o domicílio legal. Valores possíveis: Brazil, Mexico, Chile, Colombia, Peru, Argentina, Panama, Uruguay e Multi-LatAm. Exemplos: MELI → Brazil (maior mercado), Vista → Argentina (domicílio no México, operação em Vaca Muerta), Ternium → Mexico.
- **Exclusões deliberadas.**
  - FIIs brasileiros, por serem fundos e não ações.
  - ETFs, que ficam listados separadamente como hedge.
  - BDRs de empresas não LatAm.
  - Tenaris (exposição global de OCTG).
  - Linhas BVL (dados não confiáveis no Yahoo).
  - Linhas OTC.

---

## 2. Metodologia (pipeline reprodutível)

Todo o processamento foi feito em código Python determinístico, num *venv* descartável. O LLM não calculou nenhum número; ele apenas escreveu este texto a partir das saídas do código.

### 2.1 Fonte e janela

- **[V] Fonte.** Yahoo Finance via `yfinance` 1.7.0, com `auto_adjust=False`.
  - O preço `Close` é ajustado a desdobramentos, mas não a dividendos. O volume vem em ações (ou ADS/units).
- **[V] Janela de liquidez.** De 2026-07-03 a 2026-10-02: 65 pregões na B3 e na BMV, 64 nos EUA e no Chile, 63 na Colômbia e 66 na Argentina.
- **[V] Câmbio.** `BRL=X`, `MXN=X`, `CLP=X`, `COP=X`, `PEN=X` e `ARS=X` (moeda local por USD, fechamento diário do Yahoo, com *forward-fill* nos feriados).
  - No fechamento de 02/10/2026: USD/BRL 5,2226; USD/MXN 18,314; USD/CLP 981,2; USD/COP 3.318,5; USD/PEN 3,349; USD/ARS 1.524,9 (oficial).

### 2.2 Descoberta de candidatos

- **[V] Screener do Yahoo** (`yf.screen`, filtros `region` e `intradaymarketcap` > ~US$ 250 mi em moeda local). Resultados:
  - Brasil: 918 instrumentos (262 do tipo EQUITY após remover BDRs; os FIIs remanescentes foram excluídos na curadoria);
  - México: 600 (~76 emissores mexicanos; o restante são listagens SIC de estrangeiros);
  - Chile: 82;
  - Argentina: 294 (a maioria CEDEARs).
- **[V] Lacuna do screener.** As regiões `co` e `pe` retornaram **0 resultados**, então Colômbia e Peru foram montados por curadoria. Ele também omitiu emissores relevantes, como GFNORTEO e IGTI11.
- **[V] Curadoria manual.** O arquivo final de metadados tem 333 emissores e 430 linhas e inclui:
  - classes múltiplas: PETR3/PETR4, ITUB3/ITUB4, BBDC3/BBDC4, PBR/PBR-A, CMIG3/CMIG4, KLBN11/KLBN4, SAPR11/SAPR4;
  - tickers antigos e novos, para testar a validade de ambos: ELET3/AXIA3, EMBR3/EMBJ3, ERJ/EMBJ, CCRO3/MOTV3, MRFG3/MBRF3, NTCO3/NATU3, PFBCOLOM/PFCIBEST, ALFAA/SIGMAFA, PETZ3/AUAU3;
  - os ADRs patrocinados conhecidos e as empresas LatAm listadas nos EUA.

### 2.3 Validação de "vida" da linha

- **[V] Regras de descarte, na ordem:**
  1. sem série no Yahoo ("possibly delisted; no timezone found");
  2. *override* manual documentado por fonte primária (AXIA, CSAN, AERO.MX, BUENAVC1.LM);
  3. linhas `.LM` (qualidade de dados);
  4. último pregão anterior a 2026-09-28 (mais de 4 dias corridos antes do *as-of*).
- **[V] Resultado.** Todas as 281 linhas do universo têm `last_date = 2026-10-02`. A coluna `n_sessions_3m` vai de 62 (ISA.CL) a 66.

### 2.4 ADTV (US$, 3 meses)

- **[V] Definição.** `adtv_usd_3m = média_t( Close_t × Volume_t / FX_t )` na janela de 3 meses, com câmbio do mesmo dia. Também reportamos:
  - `adtv_usd_3m_median`: mediana diária, robusta a picos;
  - `adtv_usd_3m_yahoo_avgvol`: método simples `averageDailyVolume3Month × último preço / último FX`, para conferência.
- **[V] Regra para o Chile.** Quando a linha `.SN` tem mais de 30% de dias com volume zero, usamos a média **apenas dos dias com volume** e sinalizamos em `volume_quality` (ver §8.1).
- **[V] Corte de inclusão.** ADTV ≥ US$ 2 mi. *Flag* `below_5m` para ADTV < US$ 5 mi. Faixas em `liq_bucket`: `A_>=20M`, `B_5-20M`, `C_2-5M`.

### 2.5 Market cap (nível emissor, US$)

- **[V] Regra geral.** `marketCap` do Yahoo da linha **local mais líquida**, convertido pelo câmbio de 02/10/2026. Na falta de linha local, usamos a linha dos EUA.
- **[V] Units brasileiras.** O Yahoo multiplica o preço da unit pelo total de ações e superestima o valor: KLBN11 dá ~US$ 25 bi, contra ~US$ 4,4 bi reais. Para BTG, Santander BR, Klabin, Energisa, Alupar e Sanepar usamos a **mediana das classes ON/PN**; para Taesa, o `fast_info`.
- **[V] Lacunas.** Banorte e Iguatemi ficaram como **limite inferior** (preço × `floatShares`); Megacable ficou indisponível. A coluna `mcap_source` documenta a origem de cada valor.
- **[I] Limitação.** Para emissores com classes de preços muito diferentes (Cemig ON vs. PN, BTG ON vs. PNA), o valor é aproximado (erro estimado de ±20%). É suficiente para a classificação de tamanho, mas não para cálculo de *weights* de índice.

### 2.6 Ratios de ADR

- **[V] Método.** `implied_adr_ratio = mediana( ADR_close × FX / local_close )` nos últimos 20 pregões comuns. Se o desvio ficar em até ±10% do ratio documentado (±15% para linhas em ARS), mantemos o **ratio documentado**. Fora disso, investigamos.
- **[V] Casos em que o ratio documentado não pode ser verificado por preço:**
  - **TX** (Ternium), sem linha local: 1 ADS = 10 ações, documentado;
  - **AERO** (Aeroméxico): a série AERO.MX no Yahoo está quebrada; 1 ADS = 10 ações, conforme o 8-A12B na SEC de 03/11/2025.

### 2.7 Setor GICS

- **[V] Atribuição manual** nos 11 setores GICS (nomes em inglês), cruzada com o `sector` do Yahoo, que segue a taxonomia Morningstar e é mapeado para nomes GICS.
  - Houve 39 divergências de linha. Todas são **diferenças conhecidas entre taxonomias**, e mantivemos a convenção GICS/MSCI:
    - incorporadoras (Cury, Direcional, MRV, Tenda...): GICS *Consumer Discretionary – Homebuilding*; Morningstar *Real Estate*;
    - educação (Cogna, Yduqs, Afya...): GICS *Consumer Discretionary*; Morningstar *Consumer Defensive*;
    - pagamentos (STNE, PAGS, DLO, PICS): GICS *Financials* desde a revisão de mar/2023; Morningstar *Technology*;
    - farmácias (RADL3, PGMN3): GICS *Consumer Staples – Drug Retail*;
    - Hapvida: GICS *Health Care – Managed Health Care*;
    - Itaúsa: holding *Financials*;
    - Vibra e Copec: *Energy – Refining & Marketing*;
    - Pampa: *Utilities*.
  - As colunas `yahoo_sector`, `gics_yahoo_mapped` e `gics_matches_yahoo` permitem auditar cada caso.
- **[I] Casos ambíguos** que merecem confirmação numa fonte GICS oficial (MSCI ou S&P) quando houver acesso: Genomma Lab (Staples ou Health Care), Cresud (Real Estate ou Staples; consolida a IRSA), Dexco, Tupy, Bemobi, 3tentos e Grupo Argos.

### 2.8 Linha primária

- **[V] Regra.** `primary_line = true` na linha de **maior ADTV** do emissor entre as linhas do universo. Uma por emissor, 233 no total:
  - 164 primárias LOCAL, 33 ADR e 36 US_LISTED;
  - em 37 emissores, a linha local e o ADR estão **ambos** no universo.
- **[I] Observação operacional.** Para um fundo em USD, a primária de **long** e a de **short** podem diferir. O aluguel na B3 (BTC) costuma ser mais profundo para nomes brasileiros, e o *borrow* nos EUA para ADRs muito líquidos. A coluna é um *default*, e a decisão de execução fica com o módulo de *trading*.

### 2.9 Short interest (linhas EUA)

- **[V] Fonte.** Campos `shortPercentOfFloat`, `shortRatio` (*days-to-cover*) e `dateShortInterest` do Yahoo. Data-base: 15/09/2026, a quinzena FINRA mais recente.
  - Há dados válidos para 72 linhas dos EUA (o valor da YPF foi descartado, ver §8.5).
  - Para linhas locais, o Yahoo não tem dados de aluguel. Ver §9.3.

---

## 3. Resultados — estatísticas do universo

### 3.1 Por país

| País | Linhas | Emissores | Linhas ≥ US$ 5 mi | Linhas US$ 2–5 mi | ADTV agregado (US$ mi/dia) |
|:--|--:|--:|--:|--:|--:|
| Brazil | 157 | 133 | 123 | 34 | 7.984 |
| Mexico | 50 | 41 | 34 | 16 | 1.054 |
| Chile | 24 | 19 | 13 | 11 | 266 |
| Argentina | 21 | 17 | 13 | 8 | 358 |
| Colombia | 14 | 9 | 7 | 7 | 133 |
| Multi-LatAm | 6 | 5 | 5 | 1 | 390 |
| Peru | 6 | 6 | 6 | 0 | 501 |
| Panama | 2 | 2 | 2 | 0 | 50 |
| Uruguay | 1 | 1 | 1 | 0 | 30 |
| **Total** | **281** | **233** | **204** | **77** | **10.766** |

Faixas de liquidez por país, em número de linhas:

| País | A ≥ US$ 20 mi | B US$ 5–20 mi | C US$ 2–5 mi |
|:--|--:|--:|--:|
| Brazil | 73 | 50 | 34 |
| Mexico | 15 | 19 | 16 |
| Chile | 3 | 10 | 11 |
| Argentina | 5 | 8 | 8 |
| Colombia | 2 | 5 | 7 |
| Peru | 4 | 2 | 0 |
| Multi-LatAm | 3 | 2 | 1 |
| Panama | 1 | 1 | 0 |
| Uruguay | 1 | 0 | 0 |
| **Total** | **107** | **97** | **77** |

ADTV da linha primária por país, em US$ mi/dia: Brasil (mediana 15,1; média 48,1; máx. 1.170 em NU), México (7,5; 21,9; 184,5 em AG), Chile (4,4; 10,6; 69,5 em SQM), Argentina (8,2; 19,5; 72,9 em VIST), Colômbia (7,6; 10,9; 31,5 em EC), Peru (74,9; 83,6; 214 em SCCO).

### 3.2 Por setor GICS

| Setor | Linhas | Emissores | ≥ US$ 5 mi | US$ 2–5 mi | ADTV agregado (US$ mi) |
|:--|--:|--:|--:|--:|--:|
| Financials | 54 | 42 | 44 | 10 | 3.069 |
| Materials | 46 | 36 | 35 | 11 | 2.360 |
| Industrials | 32 | 27 | 23 | 9 | 694 |
| Consumer Staples | 31 | 27 | 23 | 8 | 612 |
| Consumer Discretionary | 30 | 30 | 18 | 12 | 1.240 |
| Utilities | 28 | 23 | 20 | 8 | 694 |
| Energy | 20 | 14 | 19 | 1 | 1.461 |
| Real Estate | 15 | 14 | 7 | 8 | 111 |
| Communication Services | 13 | 8 | 8 | 5 | 325 |
| Health Care | 6 | 6 | 5 | 1 | 105 |
| Information Technology | 6 | 6 | 2 | 4 | 95 |

**[I] Implicação para a neutralidade setorial.** Health Care (6 emissores) e IT (6 emissores, só 2 com ADTV ≥ US$ 5 mi) são **rasos**. Uma restrição dura de neutralidade nesses setores tende a forçar posições ilíquidas. Recomendamos agrupá-los em "setores compostos" no modelo de risco (por exemplo, *Health Care + Staples defensivos* e *IT + Communication*), ou impor neutralidade com tolerância (±2–3% do NAV) em vez de igualdade.

### 3.3 Por tipo de linha e *tier*

| Tipo de linha | Linhas | Emissores | ≥ US$ 5 mi | ADTV agregado (US$ mi) |
|:--|--:|--:|--:|--:|
| LOCAL | 193 | 186 | 132 | 4.616 |
| ADR | 51 | 50 | 39 | 2.329 |
| US_LISTED | 37 | 36 | 33 | 3.821 |

| Tier | Linhas | Emissores | ADTV agregado (US$ mi) |
|:--|--:|--:|--:|
| CORE | 241 | 196 | 6.875 |
| US_LATAM | 33 | 31 | 3.243 |
| SATELLITE | 7 | 6 | 647 |

### 3.4 Distribuição de ADTV e de market cap

- **[V] ADTV por linha (US$ mi/dia).** p10 = 2,72; p25 = 4,65; **p50 = 11,67**; p75 = 32,0; p90 = 80,1; média = 38,3; máx. = 1.170,4 (NU).
- **[V] ADTV por emissor (soma das linhas).** p10 = 2,79; p25 = 4,76; **p50 = 11,69**; p75 = 40,1; p90 = 96,2.
- **[V] Histograma**, em número de linhas e de emissores:

| ADTV (US$ mi/dia) | Linhas | Emissores |
|:--|--:|--:|
| 2–5 | 77 | 63 |
| 5–10 | 47 | 42 |
| 10–20 | 50 | 36 |
| 20–50 | 56 | 44 |
| 50–100 | 29 | 25 |
| ≥ 100 | 22 | 23 |

- **[V] Market cap por emissor (US$ bi).** p10 = 0,65; p25 = 1,20; **p50 = 3,18**; p75 = 9,04; p90 = 20,1. São 43 emissores abaixo de US$ 1 bi, 135 entre US$ 1 e 10 bi e 54 acima de US$ 10 bi; 1 está sem dado (Megacable).

### 3.5 As 25 linhas mais líquidas

| Ticker | Emissor | País | Tipo | ADTV (US$ mi) |
|:--|:--|:--|:--|--:|
| NU | Nu Holdings | Brazil | US_LISTED | 1.170,4 |
| MELI | MercadoLibre | Brazil | US_LISTED | 903,9 |
| VALE | Vale | Brazil | ADR | 382,9 |
| PBR | Petrobras | Brazil | ADR | 363,3 |
| PETR4.SA | Petrobras | Brazil | LOCAL | 351,2 |
| VALE3.SA | Vale | Brazil | LOCAL | 277,9 |
| SCCO | Southern Copper | Peru | US_LISTED | 214,2 |
| PAAS | Pan American Silver | Multi-LatAm | US_LISTED | 201,2 |
| ITUB4.SA | Itaú Unibanco | Brazil | LOCAL | 196,4 |
| AG | First Majestic Silver | Mexico | US_LISTED | 184,5 |
| ITUB | Itaú Unibanco | Brazil | ADR | 179,2 |
| BBDC4.SA | Bradesco | Brazil | LOCAL | 131,7 |
| AXIA3.SA | Axia Energia (ex-Eletrobras) | Brazil | LOCAL | 131,0 |
| PBR-A | Petrobras | Brazil | ADR | 122,9 |
| BBAS3.SA | Banco do Brasil | Brazil | LOCAL | 119,6 |
| B3SA3.SA | B3 | Brazil | LOCAL | 116,6 |
| HBM | Hudbay Minerals | Peru | US_LISTED | 115,4 |
| BAP | Credicorp | Peru | US_LISTED | 115,3 |
| BPAC11.SA | BTG Pactual | Brazil | LOCAL | 114,6 |
| XP | XP Inc | Brazil | US_LISTED | 112,2 |
| TIGO | Millicom | Multi-LatAm | US_LISTED | 107,0 |
| BBD | Bradesco | Brazil | ADR | 102,8 |
| PETR3.SA | Petrobras | Brazil | LOCAL | 98,6 |
| SBSP3.SA | Sabesp | Brazil | LOCAL | 97,0 |
| EMBJ3.SA | Embraer | Brazil | LOCAL | 90,0 |

**[I] Observação.** Prata e cobre (PAAS, AG, EXK, HBM, SCCO, FSM) aparecem com liquidez muito alta. É coerente com o regime de metais de 2026 (GC=F ≈ 4.162 e SI=F ≈ 60 no fechamento de 02/10/2026), mas isso cria um **bloco de alto beta a commodities** no universo. O modelo de fatores precisa de um fator "metais preciosos/cobre" para que esses nomes não dominem o risco idiossincrático.

### 3.6 Composição por país (linha primária; `*` = ADTV < US$ 5 mi)

- **Argentina (17).** VIST, YPF, GLOB, GGAL, BMA, PAM, LAR, BBAR, AGRO, TGS, CAAP, SUPV\*, LOMA\*, TEO\*, CEPU\*, CRESY\*, IRS\*. Secundárias: YPFD.BA, GGAL.BA, PAMP.BA, BMA.BA.
- **Brasil (133).** NU, MELI, VALE, PBR, ITUB4, BBDC4, AXIA3, BBAS3, B3SA3, BPAC11, XP, SBSP3, EMBJ3, PRIO3, ABEV3, WEGE3, AUGO, RENT3, UGPA3, VBBR3, JBS, EQTL3, GGB, ITSA4, SUZB3, STNE, CPLE3, ENEV3, BBSE3, CSMG3, RDOR3, ERO, LREN3, RADL3, MOTV3, CYRE3, ENGI11, VIVT3, RAIL3, CMIG4, TIMS3, TOTS3, PAGS, SMFT3, MGLU3, INTR, SANB11, CXSE3, ALOS3, CURY3, MULT3, EGIE3, BRAV3, DIRR3, ISAE4, CSAN3, SGML, TEND3, ASAI3, CSNA3, MBRF3, KLBN11, GOAU4, PSSA3, USIM5, CEAB3, SAUD3, TAEE11, FLRY3, CPFE3, HYPE3, COGN3, POMO4, VIVA3, NATU3, HAPV3, BEEF3, MRVE3, IGTI11, PAX, MOVI3, VAMO3, ECOR3, CMIN3, AZZA3, SLCE3, YDUQ3, ORVR3, SAPR11, BRAP4, GGPS3, JHSF3, IRBR3, AURE3, BRKM5, MDNE3, EZTC3, SMTO3, ALUP11, PASS3, BRSR6, SIMH3\*, CBAV3\*, ALPA4\*, ANIM3\*, VULC3\*, ONCO3\*, PICS\*, TTEN3\*, SBFG3\*, GMAT3\*, RECV3\*, CVCB3\*, PGMN3\*, INTB3\*, VTEX\*, PLPL3\*, AFYA\*, PCAR3\*, AUAU3\*, SEER3\*, LWSA3\*, BMOB3\*, ABCB4\*, UNIP6\*, RAPT4\*, PINE4\*, MDIA3\*, LOGG3\*, RIAA3\*, MILS3\*, GRND3\*, TUPY3\*.
  - Secundárias: PETR4, VALE3, ITUB, PBR-A, BBD, PETR3, EMBJ, ABEV, GGBR4, SBS, UGP, SUZ, BBDC3, AURA33, BSBR, VIV, ITUB3, JBSS32, CIG, TIMB, SID, ELPC, BAK, KLBN4.
- **Chile (19).** SQM, LTM, BCH, FALABELLA, BSAC, BCI, CENCOSUD, COPEC, ITAUCL, ENELAM\*, PARAUCO\*, ENELCHILE\*, ANDINA-B\*, MALLPLAZA\*, CENCOMALLS\*, ECL\*, CMPC\*, COLBUN\*, EISA\*. Secundárias: SQM-B.SN, LTM.SN, CHILE.SN, BSANTANDER.SN, ENIC.
- **Colômbia (9).** EC, CIB, TGLS, GTE, GPRK, PFGRUPOARG\*, PFGRUPSURA\*, ISA\*, CEMARGOS\*. Secundárias: ECOPETROL.CL, PFCIBEST.CL, CIBEST.CL, GRUPOSURA.CL, GRUPOARGOS.CL.
- **México (41).** AG, EXK, CX, GFNORTEO, GMEXICOB, AMX, FMX, WALMEX, TX, PAC, AC, ASR, PE&OLES, KOF, SIGMAFA, OMAB, GENTERA, Q, ALPEKA, KIMBERA, FUNO11, BIMBOA, GRUMAB, VESTA, GFINBURO, FIBRAPL14, BBAJIOO, PINFRA\*, RA\*, AERO\*, CHDRAUIB\*, FMTY14\*, ORBIA\*, VLRS\*, MEGACPO\*, TLEVISACPO\*, ALSEA\*, GCC\*, LABB\*, BOLSAA\*, GCARSOA1\*. Secundárias: AMXB, CEMEXCPO, FEMSAUBD, GAPB, ASURB, OMAB.MX, KOFUBL, TV, VTMX.
- **Peru (6).** SCCO, HBM, BAP, BVN, IFS, NEXA.
- **Multi-LatAm (5).** PAAS, TIGO, FSM, LILAK, ARCO (+LILA).
- **Panamá (2).** CPA, BLX.
- **Uruguai (1).** DLO.

---

## 4. Eventos corporativos 2024–2026 refletidos no universo

| # | Evento | Efeito no universo | Evidência |
|--:|:--|:--|:--|
| 1 | **Eletrobras → Axia Energia** (10/11/2025): ELET3→AXIA3, ELET6→AXIA6, EBR→AXIA, EBR-B→AXIA PR | AXIA3 no universo (US$ 131 mi/dia). ELET3, EBR e AXIA6 sem série no Yahoo. ADRs **deslistados da NYSE**: Form 25 em 11/06/2026 (ADS de preferenciais B1) e em 27/07/2026 (ADS ON e "Class C Preferred"); 15F em 22/06 e 07/08/2026; último pregão do ADR AXIA no Yahoo em 06/08/2026 | [V] fontes [1][2][18][19]. **[I]** O sumiço de AXIA6 e a menção a "Class C Preferred ADS" indicam conversão das PNB (provável migração ao Novo Mercado com PN classe C resgatável, como na Copel). A confirmar no RI |
| 2 | **Embraer**: EMBR3→EMBJ3, ERJ→EMBJ (03/11/2025) | EMBJ3 (US$ 90 mi) e EMBJ (US$ 86 mi); ratio 1 ADS = 4 ON verificado (implícito 3,98) | [V] [3] e dado |
| 3 | **BRF incorporada pela Marfrig** → MBRF3 (23/09/2025; 0,8521 MBRF3 por BRFS3) | MBRF3 (US$ 19 mi). BRFS3, MRFG3 e BRFS sem série; não há ADR "MBRF" | [V] [4] e dado |
| 4 | **Copel**: Novo Mercado (22/12/2025), apenas ON (CPLE3); ADS ELP (PNB) trocado por **ELPC** (4 ON) em 26/12/2025 | CPLE3 (US$ 49 mi) e ELPC (US$ 5,6 mi; implícito 4,004). CPLE6 e ELP sem série | [V] [5][6] e dado |
| 5 | **Cosan**: deslistagem voluntária do ADR na NYSE; último pregão em 18/09/2026, segue como OTC Level I | CSAN (ADR) **excluído**; CSAN3 mantido (US$ 20,6 mi) | [V] [20] (6-K de 08/09/2026) |
| 6 | **Gol**: OPA concluída e saída da B3 em 27/03/2026 (Abra) | GOLL4 e GOLL54 sem série, excluídos | [V] [7] |
| 7 | **Azul**: Chapter 11, oferta de R$ 7,4 bi, AZUL4→AZUL54 e conversão das PN em ON (AZUL3); ADR deslistado em 2025 | AZUL3 com dado, mas ADTV de US$ 0,47 mi (abaixo do corte). AZUL4 e AZUL54 sem série | [V] [8] e dado |
| 8 | **Natura**: incorporação da Natura &Co (01/07/2025); NTCO3→NATU3 | NATU3 (US$ 12,4 mi). NTCO3 e NTCO sem série | [V] [9] e dado |
| 9 | **JBS**: NYSE (JBS) desde 13/06/2025; JBSS3 deslistada em 06/06/2025; BDR JBSS32 na B3; JBS S.A. pediu cancelamento na CVM em 21/09/2026, mas o BDR segue negociando | JBS (US$ 68 mi) primária; JBSS32 (US$ 16,5 mi; 1 BDR ≈ 1 ação, implícito 1,00) | [V] [10][11] e dado |
| 10 | **Bancolombia → Grupo Cibest** (16/05/2025): CIBEST/PFCIBEST; ADR CIB = 4 preferenciais | CIB (US$ 28 mi; implícito 4,006), PFCIBEST e CIBEST no universo; PFBCOLOM sem série | [V] [12] e dado |
| 11 | **Alfa**: spin-off da Alpek (04/2025) e nova razão social **Sigma Foods** (12/2025): ALFA A → SIGMAF A | SIGMAFA.MX (US$ 10,3 mi) e ALPEKA.MX (US$ 8,2 mi); ALFAA sem série | [V] [13] e dado |
| 12 | **Petz + Cobasi** → AUAU3 | AUAU3 (US$ 2,7 mi, `below_5m`); PETZ3 sem série | [V] dado (screener: "PETZCOBASI") |
| 13 | **IPOs**: PicPay (PICS, Nasdaq, 29/01/2026, US$ 19); Agibank (AGBK, NYSE, 11/02/2026, US$ 12); Compass (PASS3, B3, 11/05/2026, o primeiro IPO na B3 desde 2021) | PICS (US$ 4,5 mi) e PASS3 (US$ 5,1 mi) no universo; AGBK (US$ 1,6 mi) abaixo do corte | [V] [14][15][16] e dado |
| 14 | **LATAM** relistada na NYSE (25/07/2024); 1 ADS = 2.000 ações | LTM (US$ 40 mi; implícito 1.983) | [V] [17] e dado |
| 15 | **Saídas da B3 em 2025**: Santos Brasil (03/10/2025), Wilson Sons (23/10/2025), Carrefour Brasil, BRF, JBS, ClearSale, Serena, Eletromídia; **Neoenergia** (OPA com leilão em 09/04/2026) | STBP3 e NEOE3 sem série, excluídos | [V] [21][22] e dado. **[I]** Ausência de NEOE3 é consistente com OPA bem-sucedida |
| 16 | **Deslistagens / desregistros na SEC**: Sendas/Assaí (15F em 12/01/2026), Vasta (Form 25 em 20/01/2026), Lavoro (Form 25 em 24/02/2026 e 15-12G em 06/03/2026) | ASAI (ADR), VSTA e LVRO excluídos; ASAI3 mantido (US$ 19,8 mi) | [V] [23][24][25] |
| 17 | **Telefônica Brasil**: desdobramento 1:2 de VIVT3 (15/04/2025) sem ajuste no ADS | VIV: ratio corrigido para **2 ON por ADS** (implícito 1,990) | [V] dado (`splits` do Yahoo). **[I]** Ratio inferido; confirmar no aviso do depositário |
| 18 | **YPF**: desdobramento 10:1 das ações locais (03/08/2026) sem ajuste no ADS | YPF: ratio corrigido para **10 ações D por ADS** (implícito 9,45, com o mesmo desvio CCL de −5,5% dos demais ADRs argentinos) | [V] dado. **[I]** Ratio inferido; confirmar no aviso do depositário |
| 19 | **Aeroméxico**: relistagem em 11/2025 (NYSE e BMV); 1 ADS = 10 ações | AERO (ADR, US$ 4,5 mi) mantido; AERO.MX excluída (série do Yahoo sem volume e com preço incoerente) | [V] [26] |
| 20 | **Banamex**: IPO planejado para jan/2027 | Fora do universo; monitorar | [V] [27] |
| 21 | **Despegar** adquirida pela Prosus (2025); **Zenvia**, **Aris Mining** (ARMN) e **Grupo Elektra** sem série no Yahoo | Excluídos | [V] dado. **[I]** ARMN e ELEKTRA: possível mudança de listagem ou suspensão; a confirmar |
| 22 | **Bradesco Saúde (SAUD3)** aparece listada (US$ 15,1 mi), e ODPV3 (Odontoprev) não tem série | SAUD3 no universo (Health Care) | [V] dado. **[I]** Provável reorganização Odontoprev → Bradesco Saúde; confirmar fato relevante |

---

## 5. Verificação dos ratios de ADR

Método: mediana de 20 pregões de (preço ADR × FX) / preço local. Ratio = ações locais por ADS.

| ADR | Linha local de referência | Ratio adotado | Implícito | Desvio | Status |
|:--|:--|--:|--:|--:|:--|
| PBR | PETR3 | 2 | 1,994 | −0,3% | OK |
| PBR-A | PETR4 | 2 | 1,996 | −0,2% | OK |
| VALE | VALE3 | 1 | 0,996 | −0,4% | OK |
| ITUB | ITUB4 | 1 | 0,997 | −0,3% | OK |
| BBD | BBDC4 | 1 | 0,988 | −1,2% | OK |
| ABEV | ABEV3 | 1 | 0,985 | −1,5% | OK |
| SUZ | SUZB3 | 1 | 1,000 | 0,0% | OK |
| GGB | GGBR4 | 1 | 1,002 | +0,2% | OK |
| SID | CSNA3 | 1 | 0,963 | −3,7% | OK |
| SBS | SBSP3 | 1 | 0,998 | −0,2% | OK |
| CIG | CMIG4 | 1 | 0,979 | −2,1% | OK |
| ELPC | CPLE3 | 4 | 4,004 | +0,1% | OK |
| UGP | UGPA3 | 1 | 0,998 | −0,2% | OK |
| BAK | BRKM5 | 2 | 1,996 | −0,2% | OK |
| BSBR | SANB11 | 1 | 1,003 | +0,3% | OK |
| EMBJ | EMBJ3 | 4 | 3,981 | −0,5% | OK |
| TIMB | TIMS3 | 5 | 5,006 | +0,1% | OK |
| **VIV** | VIVT3 | **2** (antes 1) | 1,990 | −0,5% | **Corrigido** (desdobramento 2025) |
| AMX | AMXB | 20 | 19,952 | −0,2% | OK |
| FMX | FEMSAUBD | 10 | 10,006 | +0,1% | OK |
| KOF | KOFUBL | 10 | 9,995 | 0,0% | OK |
| CX | CEMEXCPO | 10 | 9,942 | −0,6% | OK |
| TV | TLEVISACPO | 5 | 5,017 | +0,3% | OK |
| PAC | GAPB | 10 | 9,985 | −0,1% | OK |
| ASR | ASURB | 10 | 9,973 | −0,3% | OK |
| OMAB | OMAB.MX | 8 | 8,002 | 0,0% | OK |
| VLRS | VOLARA | 10 | 9,907 | −0,9% | OK |
| VTMX | VESTA | 10 | 9,972 | −0,3% | OK |
| VIST | VISTAA | 1 | 0,996 | −0,4% | OK |
| SQM | SQM-B | 1 | 1,002 | +0,2% | OK |
| BCH | CHILE | 200 | 199,29 | −0,4% | OK |
| BSAC | BSANTANDER | 400 | 397,73 | −0,6% | OK |
| ENIC | ENELCHILE | 50 | 50,57 | +1,1% | OK |
| LTM | LTM.SN | 2.000 | 1.982,95 | −0,9% | OK |
| CIB | PFCIBEST | 4 | 4,006 | +0,1% | OK |
| EC | ECOPETROL | 20 | 20,025 | +0,1% | OK |
| BVN | BUENAVC1 (ilíquida) | 1 | 0,931 | −6,9% | OK (referência local defasada) |
| YPF | YPFD.BA | **10** (antes 1) | 9,454 | −5,5% | **Corrigido** (desdobramento 2026); desvio = CCL |
| GGAL | GGAL.BA | 10 | 9,428 | −5,7% | OK (CCL) |
| BMA | BMA.BA | 10 | 9,439 | −5,6% | OK (CCL) |
| BBAR | BBAR.BA | 3 | 2,831 | −5,6% | OK (CCL) |
| SUPV | SUPV.BA | 5 | 4,698 | −6,0% | OK (CCL) |
| PAM | PAMP.BA | 25 | 23,613 | −5,5% | OK (CCL) |
| TGS | TGSU2.BA | 5 | 4,726 | −5,5% | OK (CCL) |
| CEPU | CEPU.BA | 10 | 9,509 | −4,9% | OK (CCL) |
| TEO | TECO2.BA | 5 | 4,713 | −5,7% | OK (CCL) |
| LOMA | LOMA.BA | 5 | 4,729 | −5,4% | OK (CCL) |
| CRESY | CRES.BA | 10 | 9,467 | −5,3% | OK (CCL) |
| IRS | IRSA.BA | 10 | 9,470 | −5,3% | OK (CCL) |
| TX | — | 10 | n/d | — | Documentado, não verificável |
| AERO | (AERO.MX quebrada) | 10 | n/d | — | Documentado (SEC 8-A12B) |

**[V] Argentina.** A razão implícito/documentado tem média de 0,9448 (desvio-padrão de 0,0028) nos 12 ADRs. Isso implica **CCL/oficial ≈ 1,058**, uma brecha de ~5,8% em 02/10/2026.

**[I] Implicação.**
- Para um fundo em USD, a linha BYMA só faz sentido com acesso ao câmbio CCL/MEP. As linhas locais argentinas também têm ADTV baixo (só YPFD, GGAL, PAMP e BMA ≥ US$ 2 mi).
- A primária argentina deve ser **sempre o ADR**.
- A brecha CCL é um fator de risco próprio, relevante para *pairs* ADR vs. local e para o *mark-to-market*.

---

## 6. Tickers descartados

### 6.1 Sem dados, deslistados ou com qualidade de dados inadequada (44 linhas)

| Ticker | Emissor | Tipo | Motivo |
|:--|:--|:--|:--|
| `ELET3.SA`, `EBR` | Axia (ex-Eletrobras) | LOCAL/ADR | Tickers antigos; sem série (renomeados em 10/11/2025) |
| `AXIA6.SA` | Axia | LOCAL | Sem série no Yahoo (ver §4, item 1) |
| `AXIA` | Axia | ADR | Deslistado da NYSE (Form 25 em 27/07/2026; 15F em 07/08/2026); último pregão no Yahoo em 06/08/2026 |
| `AXIA-P` | Axia | ADR | Sem série; ADS de preferenciais deslistado (Form 25 em 11/06/2026) |
| `CPLE6.SA`, `ELP` | Copel | LOCAL/ADR | PNB convertidas (Novo Mercado em 22/12/2025); ADS trocado por ELPC |
| `NEOE3.SA` | Neoenergia | LOCAL | Sem série; OPA de cancelamento (leilão em 09/04/2026) |
| `CSAN` | Cosan | ADR | Deslistado da NYSE (último pregão em 18/09/2026); OTC Level I |
| `EMBR3.SA`, `ERJ` | Embraer | LOCAL/ADR | Tickers antigos (→ EMBJ3/EMBJ em 03/11/2025) |
| `CCRO3.SA` | Motiva (ex-CCR) | LOCAL | Ticker antigo (→ MOTV3) |
| `AZUL4.SA`, `AZUL54.SA` | Azul | LOCAL | PN convertidas em ON (AZUL3) |
| `GOLL4.SA`, `GOLL54.SA` | Gol | LOCAL | Fechamento de capital (27/03/2026) |
| `STBP3.SA` | Santos Brasil | LOCAL | Deslistada (03/10/2025; OPA da CMA CGM) |
| `BRFS3.SA`, `MRFG3.SA`, `BRFS`, `MBRF` | MBRF | LOCAL/ADR | Incorporação → MBRF3; sem ADR ativo |
| `ASAI` | Assaí | ADR | 15F (12/01/2026); ADR encerrado |
| `NTCO3.SA`, `NTCO` | Natura | LOCAL/ADR | → NATU3; ADR encerrado |
| `PETZ3.SA` | Petz-Cobasi | LOCAL | → AUAU3 |
| `ODPV3.SA` | Odontoprev / Bradesco Saúde | LOCAL | Sem série; ver SAUD3 |
| `BPAN4.SA` | Banco Pan | LOCAL | Sem série; fechamento de capital anunciado em 2025 |
| `LVRO` | Lavoro | US_LISTED | Form 25 (24/02/2026) e 15-12G (06/03/2026) |
| `ZENV` | Zenvia | US_LISTED | Sem série no Yahoo |
| `DESP` | Despegar | US_LISTED | Adquirida pela Prosus (2025) |
| `ARMN` | Aris Mining | US_LISTED | Sem série no Yahoo (verificar novo ticker ou listagem) |
| `ALFAA.MX` | Sigma Foods | LOCAL | Ticker antigo (→ SIGMAFA) |
| `ELEKTRA.MX` | Grupo Elektra | LOCAL | Sem série no Yahoo (verificar suspensão ou cancelamento) |
| `AERO.MX` | Aeroméxico | LOCAL | Série do Yahoo sem volume em 65/65 pregões e com preço incoerente com o ADS |
| `PFBCOLOM.CL` | Grupo Cibest | LOCAL | Ticker antigo (→ PFCIBEST) |
| `BAP.LM`, `BUENAVC1.LM`, `FERREYC1.LM`, `ALICORC1.LM`, `CVERDEC1.LM`, `UNACEMC1.LM`, `VOLCABC1.LM`, `MINSURI1.LM`, `INRETC1.LM` | Peru (BVL) | LOCAL | O Yahoo classifica a BVL como MUTUALFUND/"YHD", sem moeda; volumes não confiáveis |

### 6.2 Linhas válidas, mas com ADTV < US$ 2 mi (105 linhas; ADTV em US$ mi)

- **Argentina (23).** EDN 1,82; VISTAA.MX 1,68; BBAR.BA 1,17; TGSU2.BA 1,09; CEPU.BA 1,05; SUPV.BA 0,89; TRAN.BA 0,74; BYMA.BA 0,63; METR.BA 0,63; LOMA.BA 0,61; TXAR.BA 0,58; EDN.BA 0,55; TGNO4.BA 0,52; VALO.BA 0,48; TECO2.BA 0,36; CRES.BA 0,33; COME.BA 0,21; ALUA.BA 0,20; IRSA.BA 0,12; BIOX 0,11; CVH.BA 0,10; BHIP.BA 0,08; MIRG.BA 0,05.
- **Brasil (43).** OPCT3 1,99; DXCO3 1,98; DESK3 1,91; TGMA3 1,90; LIGT3 1,89; PNVL3 1,82; BHIA3 1,70; VTRU3 1,69; AGBK 1,63; SAPR4 1,62; TFCO4 1,62; JSLG3 1,55; LEVE3 1,51; AMER3 1,43; MYPK3 1,37; KEPL3 1,36; BMGB4 1,36; FESA4 1,25; LAVV3 1,16; FRAS3 1,01; QUAL3 0,96; HBSA3 0,95; EVEN3 0,94; CAML3 0,92; FIQE3 0,89; RANI3 0,87; RAIZ4 0,81; ARML3 0,75; DASA3 0,60; AGRO3 0,55; JALL3 0,49; BLAU3 0,47; POSI3 0,47; AZUL3 0,47; VINP 0,39; CMIG3 0,37; ITSA3 0,33; CINT 0,31; CSED3 0,29; BBDO 0,26; LND 0,17; AMBP3 0,15; CIG-C 0,01.
- **Chile (13).** CCU.SN 1,94; VAPORES 1,71; CCU 1,69; QUINENCO 1,64; AGUAS-A 1,60; ENTEL 1,50; RIPLEY 1,32; SMU 0,95; ILC 0,92; CAP 0,43; AKO-B 0,27; SONDA 0,10; SK 0,00.
- **Colômbia (13).** MINEROS 1,21; GEB 1,00; CORFICOLCF 1,00; AVAL 0,73; PFAVAL 0,50; CELSIA 0,34; PROMIGAS 0,19; BOGOTA 0,17; TERPEL 0,17; PFDAVVNDA 0,07; ETB 0,03; BVC 0,01; CNEC 0,00.
- **México (12).** VOLARA 1,86; LACOMERUBC 1,66; LIVEPOLC-1 1,42; CUERVO 1,30; BWMX 1,29; FIBRAMQ12 1,15; DANHOS13 0,87; SIM 0,46; NEMAKA 0,34; TRAXIONA 0,31; SIMECB 0,01; SORIANAB 0,01.
- **Multi-LatAm (1).** CDRO 0,25.

**[I] "Watch list" de promoção:** OPCT3, DXCO3, DESK3, TGMA3, LIGT3, EDN, AGBK, VOLARA e CCU (de US$ 1,6 a 2,0 mi). Devem ser reavaliadas no rebalanceamento mensal do universo.

---

## 7. Benchmarks e instrumentos de hedge (verificados em 02/10/2026)

| Ticker | Descrição | Status | Último pregão | Último preço | ADTV 3m (US$ mi) |
|:--|:--|:--|:--|--:|--:|
| `EWZ` | iShares MSCI Brazil ETF | OK | 2026-10-02 | 38,19 | 834,5 |
| `EWZS` | iShares MSCI Brazil Small-Cap ETF | OK | 2026-10-02 | 13,70 | 3,6 |
| `EWW` | iShares MSCI Mexico ETF | OK | 2026-10-02 | 71,09 | 86,1 |
| `ECH` | iShares MSCI Chile ETF | OK | 2026-10-02 | 37,10 | 17,3 |
| `GXG` | Global X MSCI Colombia (ticker antigo) | **Sem dados** | – | – | – |
| `COLO` | Global X MSCI Colombia ETF (substitui GXG) | OK | 2026-10-02 | 47,06 | 7,3 |
| `EPU` | iShares MSCI Peru and Global Exposure ETF | OK | 2026-10-02 | 89,56 | 3,4 |
| `ARGT` | Global X MSCI Argentina ETF | OK | 2026-10-02 | 84,52 | 11,9 |
| `ILF` | iShares Latin America 40 ETF | OK | 2026-10-02 | 34,98 | 89,5 |
| `FLLA` | Franklin FTSE Latin America ETF | OK | 2026-10-02 | 27,66 | 0,7 |
| `FLBR` | Franklin FTSE Brazil ETF | OK | 2026-10-02 | 23,93 | 3,9 |
| `EEM` | iShares MSCI Emerging Markets ETF | OK | 2026-10-02 | 67,67 | 1.327,9 |
| `SPY` | SPDR S&P 500 ETF | OK | 2026-10-02 | 769,60 | 33.565,8 |
| `BOVA11.SA` | iShares Ibovespa (B3) | OK | 2026-10-02 | 190,00 | 119,6 |
| `SMAL11.SA` | iShares Small Cap (B3) | OK | 2026-10-02 | 116,30 | 44,8 |
| `NAFTRACISHRS.MX` | iShares NAFTRAC (IPC, BMV) | OK | 2026-10-02 | 64,18 | 8,7 |
| `^BVSP` | Ibovespa | OK | 2026-10-02 | 192.115 | – |
| `^MXX` | S&P/BMV IPC | OK | 2026-10-02 | 64.532 | – |
| `^MERV` | S&P Merval | OK | 2026-10-02 | 2.767.663 | – |
| `^IPSA` | S&P IPSA | **Sem dados** | – | – | – |
| `^SPBLPGPT` | S&P/BVL Peru General | **Sem dados** | – | – | – |
| `^GSPC` | S&P 500 | OK | 2026-10-02 | 7.723 | – |
| `^VIX` | CBOE VIX | OK | 2026-10-02 | 15,31 | – |
| `BRL=X` | USD/BRL | OK | 2026-10-02 | 5,2226 | – |
| `MXN=X` | USD/MXN | OK | 2026-10-02 | 18,314 | – |
| `CLP=X` | USD/CLP | OK | 2026-10-02 | 981,21 | – |
| `COP=X` | USD/COP | OK | 2026-10-02 | 3.318,53 | – |
| `PEN=X` | USD/PEN | OK | 2026-10-02 | 3,349 | – |
| `ARS=X` | USD/ARS (oficial) | OK | 2026-10-02 | 1.524,88 | – |
| `DX-Y.NYB` | DXY | OK | 2026-10-02 | 101,93 | – |
| `HG=F` | Cobre COMEX (*front*) | OK | 2026-10-02 | 6,49 | – |
| `CL=F` / `BZ=F` | WTI / Brent (*front*) | OK | 2026-10-02 | 91,11 / 102,20 | – |
| `GC=F` / `SI=F` | Ouro / Prata COMEX (*front*) | OK | 2026-10-02 | 4.162 / 59,98 | – |

**[I] Uso recomendado.**

- **Hedges de beta/país:**
  - EWZ, BOVA11 e EWW (líquidos);
  - ILF como hedge regional;
  - ECH, ARGT e COLO como hedges de país de capacidade limitada (US$ 7–17 mi/dia);
  - EPU e FLLA são ilíquidos para hedge.
- **Benchmarks de atribuição:** ^BVSP, ^MXX e ^MERV. Para Chile e Peru, como os índices não estão no Yahoo, usar ECH e EPU como *proxies* ou outra fonte de dados (ver doc 06).
- **Commodities (HG=F, CL=F, GC=F, SI=F):** são fatores explicativos no modelo de risco, não instrumentos de hedge do fundo.

---

## 8. Qualidade de dados e limitações

### 8.1 Chile: lacunas de volume no Yahoo

- **[V] O problema.** Em 28 das 30 linhas `.SN` testadas, só **10 a 13 dos 64 pregões** têm volume > 0. Os dias com volume se concentram em 03–17/07 e 14–16/09/2026. Banco de Chile e Santander Chile têm 53/64 dias com volume.
  - Os zeros são **dados ausentes**, não ausência de negócio: Falabella e SQM-B negociam todos os dias.
  - O próprio `averageDailyVolume3Month` do Yahoo herda os zeros e **subestima** o ADTV em ~5×. SQM-B, por exemplo: US$ 3,8 mi pelo Yahoo contra US$ 26,4 mi nos dias com volume.
- **[V] Tratamento.** ADTV = média dos dias com volume, com `volume_quality = YAHOO_VOLUME_GAPS (...)` (17 linhas).
- **[I] Risco.** A amostra é pequena (10–13 dias) e possivelmente não representativa. Antes de dimensionar posições chilenas, recomendamos validar com dados da Bolsa de Santiago ou de um provedor pago. Enquanto isso, os ADRs chilenos (SQM, LTM, BCH, BSAC) são as linhas primárias de fato.

### 8.2 Peru: BVL inutilizável no Yahoo

- **[V]** O Yahoo devolve as linhas `.LM` como `instrumentType = MUTUALFUND`, bolsa "YHD" e moeda vazia; BUENAVC1 tem 58/64 dias sem volume.
- **[I]** As linhas BVL foram excluídas. A exposição ao Peru vem de SCCO, BAP, BVN, IFS, NEXA e HBM, todas listadas nos EUA e líquidas (US$ 9–214 mi/dia).

### 8.3 Argentina: câmbio oficial vs. CCL

- **[V]** ADTV e *market cap* de linhas BYMA usam o câmbio **oficial** (ARS=X). Os preços locais embutem o CCL, cerca de 5,8% acima.
- **[I]** O ADTV das linhas `.BA` em USD "CCL" é ~5,5% menor que o reportado. Isso não altera a inclusão de nenhuma linha.

### 8.4 Market cap de units e de multi-classes

- **[V]** O Yahoo superestima units: KLBN11 em ~5,8×, TAEE11 em ~3×. Corrigimos para seis emissores (§2.5).
- **[I]** Multi-classes com prêmio de ON (Cemig, BTG) têm erro residual estimado de ±20%.

### 8.5 Short interest

- **[V]** O `shortPercentOfFloat` da YPF veio como 72,36 (um erro de unidade após o desdobramento local) e foi descartado; `sharesPercentSharesOut` = 1,47%.
- **[I]** O *float* do Yahoo para emissores controlados (SCCO, ~89% do Grupo México; AFYA) amplia o percentual de SI. Isso é correto do ponto de vista de risco de *squeeze*, porque o *float* é pequeno.

### 8.6 Limitações gerais

- **[I]** O ADTV de 3 meses é uma janela única (jul–set/2026), com metais e Argentina em regime de alta atividade. Para o modelo de capacidade, recomendamos também ADTV de 6 e 12 meses e a mediana de 20 dias.
- **[I]** O universo **não é *point-in-time***. Ele reflete os sobreviventes de 02/10/2026. Para *backtest*, é preciso reconstruir o universo histórico (tickers antigos e deslistados) para evitar viés de sobrevivência. Os mapeamentos ticker antigo → novo do §4 são o ponto de partida.
- **[I]** O Yahoo não é fonte de produção para um fundo de US$ 100 mi. Para operar, recomendamos validar preços, volumes e ações corporativas com uma fonte licenciada (B3 Market Data, Bloomberg/Refinitiv/FactSet). Ver doc 06.

---

## 9. Implicações para a gestão: liquidez, capacidade e short squeeze

### 9.1 Capacidade por liquidez (NAV de US$ 100 mi)

- **[I] Regra de dimensionamento.** `dias_para_sair = |posição| / (taxa_participação × ADTV)`. Com participação de 15% do ADTV:

| Posição (% NAV) | ADTV US$ 2 mi | ADTV US$ 5 mi | ADTV US$ 10 mi | ADTV US$ 20 mi |
|:--|--:|--:|--:|--:|
| 0,5% (US$ 0,5 mi) | 1,7 dia | 0,7 | 0,3 | 0,2 |
| 1,0% (US$ 1 mi) | 3,3 dias | 1,3 | 0,7 | 0,3 |
| 2,0% (US$ 2 mi) | 6,7 dias | 2,7 | 1,3 | 0,7 |
| 3,0% (US$ 3 mi) | 10,0 dias | 4,0 | 2,0 | 1,0 |

- **[V/I] Cobertura pelo limite proposto.** Com limite de long de 0,45 × ADTV (≤ 3 dias a 15%), **226 dos 233 emissores** comportam uma posição de 1% do NAV e **179** comportam 2%. Com limite de short de 0,30 × ADTV (≤ 2 dias), 199 emissores comportam 1%.
- **[I] Contexto.** Com vol-alvo de 5% e *gross* tipicamente entre 150% e 250% num L/S *market neutral*, o tamanho médio de posição esperado é 0,5–2% do NAV. **O universo de ≥ US$ 5 mi é suficiente** para ~80–120 nomes simultâneos sem violar 3 dias de liquidação.

### 9.2 Elegibilidade para o lado vendido

- **[I] Regra sugerida.** Short apenas se:
  - ADTV da linha ≥ US$ 10 mi;
  - *borrow* confirmado (taxa e quantidade);
  - SI% do *float* ≤ 10% e *days-to-cover* ≤ 5 (linhas dos EUA);
  - nenhum evento binário (OPA, reestruturação, controlador comprando) nos próximos 30 dias.
- **[V]** Há **126 emissores** com ADTV de linha primária ≥ US$ 10 mi: Brasil 83, México 15, Argentina 8, Chile 5, Peru 5, Multi-LatAm 5, Colômbia 3, Panamá 1 e Uruguai 1.

### 9.3 Flags de short squeeze (linhas dos EUA; SI de 15/09/2026)

| Ticker | SI % *float* | *Days-to-cover* | ADTV (US$ mi) | Leitura [I] |
|:--|--:|--:|--:|:--|
| AFYA | 29,0% | 6,2 | 2,8 | **Risco alto**: *float* pequeno e ADTV baixo. Não vender |
| GLOB | 26,4% | 8,9 | 55,1 | Crowded short. Squeeze em notícia positiva |
| GGAL | 18,0% | 6,3 | 39,9 | Crowded; alta sensibilidade a política e FX argentinos |
| JBS | 16,8% | 7,8 | 68,1 | Crowded desde o *listing* na NYSE |
| AUGO | 16,7% | 5,7 | 72,6 | Mineradora de ouro; squeeze com o ouro |
| DLO | 13,9% | 7,1 | 29,7 | Crowded |
| PAGS | 12,8% | 7,1 | 27,1 | Crowded |
| SCCO | 10,4% | 8,8 | 214,2 | *Float* ~11% (controle do Grupo México); DTC alto |
| TGLS | 10,1% | 6,8 | 10,8 | Crowded |
| CAAP | 5,4% | 6,7 | 5,9 | DTC alto |
| IRS | 1,8% | 8,8 | 2,4 | DTC alto por ADTV baixo |
| CPA | 5,0% | 5,7 | 40,7 | DTC moderado |
| ASR | 3,9% | 6,0 | 16,7 | DTC moderado |
| TIMB | 2,0% | 5,5 | 10,2 | DTC moderado |
| LILAK | 4,6% | 5,3 | 11,2 | DTC moderado |

- **[V]** Das 72 linhas dos EUA com dados válidos, 9 têm SI > 10%, 15 têm SI > 5% e 15 têm DTC > 5. São 15 linhas com pelo menos um dos dois *flags*.
- **[I] Para as linhas locais**, o Yahoo não traz dados de aluguel. O módulo de risco deve ingerir:
  - **B3**: posições em aluguel (BTC) por ativo, taxa doadora/tomadora e % do *free float* alugado, da B3 Market Data / "Empréstimo de Ativos";
  - **BMV**: *préstamo de valores*;
  - **Chile**: *venta corta*.
- **[I] Gatilhos sugeridos para B3:** % do *free float* alugado > 10% **ou** taxa tomadora > 8% a.a. → *flag* de squeeze. São valores a calibrar.

---

## 10. Tabela de parâmetros

| Parâmetro | Valor adotado | Tipo | Justificativa |
|:--|:--|:--|:--|
| Data *as-of* | 2026-10-02 (fechamento) | Fixo | Último pregão completo antes da decisão de segunda, 05/10/2026 |
| Janela de ADTV | 2026-07-03 → 2026-10-02 (~63–66 pregões) | [V] | "3 meses", padrão de mercado para liquidez |
| Definição de ADTV | média de (Close × Volume / FX do dia) | [V] | Captura variações de preço e câmbio na janela |
| Corte de inclusão | ADTV ≥ **US$ 2 mi** | [V] | Especificação da tarefa; ~1,7 dia para 0,5% do NAV a 15% de participação |
| Faixa "núcleo" | ADTV ≥ **US$ 5 mi** (`below_5m = false`) | [V] | 204 linhas / 167 emissores |
| Faixas de liquidez | A ≥ 20; B 5–20; C 2–5 (US$ mi) | [I] | Faixas para limites de posição |
| Regra de "vida" | último pregão ≥ *as-of* − 4 dias corridos | [V] | Elimina deslistados e suspensos |
| Pregões mínimos | 40 na janela | [V] | Abaixo disso: `HISTORICO_INCOMPLETO` |
| Regra de volume (Chile) | > 30% de dias com volume zero → média dos dias com volume | [V] | Lacunas do Yahoo (§8.1) |
| Tolerância de ratio ADR | ±10% (±15% para ARS) sobre a mediana de 20 pregões | [V] | ±10% absorve assincronia de fechamento e FX; ARS absorve a brecha CCL |
| Câmbio | Yahoo USD/LCL (oficial para ARS) | [V] | Fonte única e auditável |
| *Market cap* | Yahoo, linha local mais líquida; units pela mediana das classes ON/PN | [V] | Corrige a superestimação das units |
| Linha primária | maior ADTV do emissor | [V] | *Default*; execução pode escolher outra |
| *Flag* de squeeze (EUA) | SI > 10% do *float* **ou** DTC > 5 | [I] | Limiares usuais de *prime brokers* e *crowding* |
| Elegível a short | ADTV ≥ US$ 10 mi + *borrow* + sem *flag* | [I] | 126 emissores |
| Posição máx. long (liquidez) | 0,45 × ADTV (3 dias a 15%) | [I] | Capacidade de saída em estresse |
| Posição máx. short (liquidez) | 0,30 × ADTV (2 dias a 15%) | [I] | O short exige saída mais rápida (risco de *recall* e squeeze) |
| Posição máx. na faixa C (2–5 mi) | 0,5% do NAV, apenas long | [I] | Conservadorismo de liquidez |
| Revisão do universo | mensal (1ª segunda do mês); eventos corporativos semanalmente | [I] | Captura IPOs, deslistagens e mudanças de ticker |

---

## 11. Próximos passos recomendados [I]

1. **Portar o pipeline para o pacote do projeto** (por exemplo, `src/.../universe/`) com testes *offline*: *fixtures* de preços e volumes, testes da regra de ratio de ADR, da regra do Chile e da correção de units. O CSV gerado deve entrar com hash SHA-256 no FactBook, conforme o invariante 3 do AGENTS.md.
2. **Construir o universo *point-in-time*** (mensal, 2018–2026) com o mapa de tickers antigos e novos do §4, para *backtest* sem viés de sobrevivência.
3. **Ingerir dados de aluguel** (B3 BTC, BMV, Santiago) e *short interest* dos EUA quinzenalmente (FINRA) no módulo de risco de squeeze.
4. **Validar o Chile** com fonte alternativa antes da primeira alocação relevante em linhas `.SN`.
5. **Confirmar os itens [I] em aberto**: classe AXIA6, ratio de VIV e YPF no aviso do depositário, SAUD3/ODPV3, ELEKTRA e ARMN, e a classificação GICS oficial dos casos ambíguos.
6. **Decidir sobre o *tier* SATELLITE** (PAAS, AG, EXK, FSM, HBM, LILA/LILAK). Esses nomes adicionam ~US$ 650 mi/dia de liquidez, mas importam beta de metais e Canadá. Sugestão: permitir apenas como hedge ou *pairs* contra produtores LatAm, por exemplo PAAS vs. Peñoles.

---

## 12. Fontes

Dados de mercado: Yahoo Finance via `yfinance` 1.7.0 (https://github.com/ranaroussi/yfinance), extraídos em 2026-10-05 para a janela 2026-05-25 → 2026-10-02 (preços, volumes, *splits*, `info`, `fast_info` e *screener* `yf.screen`). Todos os números das seções 3, 5, 6, 7 e 9 derivam desse extrato, salvo indicação.

1. Forbes Brasil — "Eletrobras vira Axia Energia e muda nome na B3 e NYSE" — https://forbes.com.br/forbes-money/2025/10/eletrobras-vira-axia-energia-e-muda-nome-na-b3-e-nyse/ — out/2025.
2. Times Brasil (CNBC) — "Eletrobras: Axia Energia, nova marca e tickers na B3 e NYSE" — https://timesbrasil.com.br/empresas-e-negocios/energia/eletrobras-axia-energia-nova-marca-tickers-b3-nyse/ — nov/2025.
3. Análise de Ações — "Embraer (EMBR3) mudará de ticker na B3 e na NYSE a partir de 3 de novembro" — https://www.analisedeacoes.com/noticias/embraer-embr3-mudara-de-ticker-na-b3-e-na-nyse-a-partir-de-3-de-novembro/ — out/2025.
4. Forbes Agro — "BRF e Marfrig criam a gigante de alimentos MBRF na B3" — https://forbes.com.br/forbesagro/2025/09/de-origem-pecuaria-brf-e-marfrig-criam-a-gigante-de-alimentos-mbrf-na-b3/ — set/2025. Ver também https://euqueroinvestir.com/negocios/marfrig-mbrf3-incorporacao-brf (set/2025).
5. Cleary Gottlieb — "Copel in Migration to the Novo Mercado" — https://www.clearygottlieb.com/news-and-insights/news-listing/copel-in-migration-to-the-novo-mercado — dez/2025.
6. AlphaQuery — Companhia Paranaense de Energia (ELPC), perfil (1 ADS = 4 ON; efetivo em 26/12/2025) — https://www.alphaquery.com/stock/ELPC/profile-key-metrics — consultado em 2026-10-05.
7. Economic News Brasil — "Saída da Gol da B3 encerra ciclo de mais de duas décadas" — https://economicnewsbrasil.com.br/2026/03/29/saida-da-gol-da-b3/ — 29/03/2026. Ver também Exame: https://exame.com/invest/mercados/gol-vai-sair-da-b3-o-que-vai-acontecer-com-as-acoes-da-companhia-aerea/ (2026).
8. TradingView/Money Times — "Azul muda ticker para AZUL54..." — https://br.tradingview.com/news/moneytimes:bc792eba9bc81:0/ — jan/2026. BPMoney — "Azul espera sair do Chapter 11 até início de 2026" — https://bpmoney.com.br/negocios/azul-azul4-espera-sair-do-chapter-11-ate-inicio-de-2026/ — 2025.
9. Acionista — "Natura (NATU3) troca ticker e revela novo caminho estratégico" — https://acionista.com.br/natura-natu3-troca-ticker-e-revela-novo-caminho-estrategico/ — jul/2025.
10. Swineweb — "JBS Finalizes Dual Listing: NYSE Debut Set for June 12" — https://www.swineweb.com/jbs-finalizes-dual-listing-nyse-debut-set-for-june-12/ — jun/2025.
11. The Rio Times — "Brazil Meatpacker JBS Asks to Deregister Local Unit; Receipts Still Trade" — https://www.riotimesonline.com/jbs-delisting-cvm-filing-september-2026/ — set/2026.
12. Bancolombia — "Grupo Cibest marca un nuevo comienzo..." — https://www.bancolombia.com/acerca-de/sala-prensa/noticias/resultados-corporativos/grupo-cibest-nueva-matriz-bancolombia — mai/2025. TipRanks: https://www.tipranks.com/news/company-announcements/bancolombia-completes-corporate-restructuring-with-grupo-cibest-as-new-holding — mai/2025.
13. MarketScreener — "Mexico's Alfa Changes Name to Sigma Foods" — https://www.marketscreener.com/news/mexico-s-alfa-changes-name-to-sigma-foods-ce7d51d2d881f127 — dez/2025. Sigma Foods, comunicado de 08/12/2025: https://www.sigmafoods.com/wp-content/uploads/2025/12/2025dec08-ALFA_to_SigmaFoods.pdf
14. IPO Scoop — "PicPay Prices IPO at $19..." — https://www.iposcoop.com/the-ipo-buzz-picpay-prices-ipo-at-19-top-of-range-in-first-brazilian-ipo-in-five-years/ — jan/2026.
15. FinTech Weekly — "Agibank Raises $240 Million in New York IPO" — https://www.fintechweekly.com/news/agibank-new-york-ipo-brazilian-fintech-listings — fev/2026.
16. InfoMoney — "Compass (PASS3) estreia na B3..." — https://www.infomoney.com.br/mercados/compass-pass3-estreia-na-bolsa-nesta-segunda-e-poe-fim-a-seca-de-5-anos-de-ipo-desempenho-acoes/ — mai/2026.
17. LATAM Airlines — "LATAM announces relisting on the New York Stock Exchange and pricing" — https://latamairlines.gcs-web.com/news-releases/news-release-details/latam-announces-relisting-new-york-stock-exchange-and-pricing — jul/2024. SEC 20-F FY2025: https://www.sec.gov/Archives/edgar/data/1047716/000104771626000046/ltm-20251231.htm
18. SEC EDGAR — AXIA Energia, Form 25 (27/07/2026) — https://www.sec.gov/Archives/edgar/data/1439124/000129281426003918/axia20260727_form25.htm. Form 25 (11/06/2026): https://www.sec.gov/Archives/edgar/data/1439124/000129281426003417/axia20260610_25.htm
19. SEC EDGAR — AXIA Energia, Form 15F (07/08/2026) — https://www.sec.gov/Archives/edgar/data/1439124/000129281426004140/axia20260807_15f.htm. F-6 POS (04/09/2026): https://www.sec.gov/Archives/edgar/data/1439124/000119380526001189/e665667_f6pos-axia.htm
20. SEC EDGAR — Cosan S.A., 6-K (08/09/2026; deslistagem da NYSE, último pregão em 18/09/2026) — https://www.sec.gov/Archives/edgar/data/1430162/000155485526001981/MainDocument.htm. Form 25: https://www.sec.gov/Archives/edgar/data/1430162/000095010326013642/dp252967_25.htm
21. Money Times — "Ano da debandada na B3? Confira as empresas que deram adeus à bolsa brasileira em 2025" — https://www.moneytimes.com.br/ano-da-debandada-na-b3-confira-as-empresas-que-deram-adeus-a-bolsa-brasileira-em-2025-grds/ — 05/12/2025.
22. Money Times — "Tchau, Novo Mercado: Neoenergia (NEOE3) marca leilão de OPA para 9 de abril" — https://www.moneytimes.com.br/tchau-novo-mercado-neoenergia-neoe3-marca-leilao-de-opa-para-9-de-abril-lmrs/ — mar/2026.
23. SEC EDGAR — Sendas Distribuidora, Form 15F (12/01/2026) — https://www.sec.gov/Archives/edgar/data/1834048/000129281426000076/asai20260112_form15f.htm
24. SEC EDGAR — Vasta Platform, Form 25 (20/01/2026) — https://www.sec.gov/Archives/edgar/data/1792829/000095010326000644/dp240098_25.htm
25. SEC EDGAR — Lavoro Ltd, Form 25 (24/02/2026) — https://www.sec.gov/Archives/edgar/data/1945711/000155485526000107/MainDocument.htm. 15-12G (06/03/2026): https://www.sec.gov/Archives/edgar/data/1945711/000155485526000204/MainDocument.htm
26. SEC EDGAR — Grupo Aeroméxico, Form 8-A12B (03/11/2025; "each ADS represents ten common shares") — https://www.sec.gov/Archives/edgar/data/1561861/000119312525261788/d25750d8a12b.htm
27. Caproasia — "Citigroup Plans IPO of Mexico Subsidiary Banamex..." — https://www.caproasia.com/2026/09/26/225-billion-citigroup-plans-ipo-of-mexico-subsidiary-banamex-financial-group-to-raise-3-billion-citigroup-acquired-banamex-for-12-5-billion-in-2001-owns-51-after-selling-49-stake/ — 26/09/2026.
28. SEC EDGAR full-text search (`efts.sec.gov/LATEST/search-index`), usada para varrer Forms 25, 15F e 15-12G de emissores LatAm entre 2025-10-01 e 2026-10-05 — https://efts.sec.gov/LATEST/search-index — consulta em 2026-10-05. **Limitação:** a varredura sem termo de busca é amostral e pode não captar todas as deslistagens.
29. MSCI — Global Industry Classification Standard (GICS), revisão de 2023 (*Transaction & Payment Processing Services* migrou para Financials, efetiva em mar/2023) — https://www.msci.com/our-solutions/indexes/gics — consultado em 2026-10-05 (fato de conhecimento geral; não reverificado nesta sessão).
