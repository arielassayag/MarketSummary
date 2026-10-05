# 06 — Fontes de dados gratuitas e ferramentas (data-tooling)

| Campo | Valor |
|---|---|
| Data do documento | **segunda-feira, 2026-10-05** |
| Último pregão completo considerado | sexta-feira, 2026-10-02 |
| Escopo | Fontes **gratuitas** de dados (preços, liquidez, aluguel/short interest, macro/FX, fundamentos, notícias) e ferramentas Python (otimização, risco, LLM/agentes, app) para o PM long/short LatAm (USD, NAV inicial USD 100 mm, vol-alvo 5% a.a., banda 3–7%, net/beta neutral, rebalanceamento semanal às segundas) |
| Método | Testes **reais** de acesso (curl/Python) executados neste ambiente em 2026-10-05, em venv descartável (`uv venv`, Python 3.13.14) fora do repositório; leitura de documentação primária; benchmarks locais |
| Ambiente de teste | `/tmp/.../scratchpad/data_probe` (não versionado). Nenhum arquivo do repositório foi alterado além deste documento |
| Natureza dos dados | Os números citados como resultado de teste são **dados reais** coletados em 2026-10-05 (não simulados). Nada neste documento é recomendação de investimento |

**Legenda de evidência** usada em todo o texto:

- **[V]** verificado por execução neste ambiente em 2026-10-05 (status HTTP, latência, campos, valores).
- **[D]** afirmado por documentação primária (URL na lista de fontes).
- **[I]** inferência/recomendação do autor — tratar como hipótese a validar.

---

## Sumário executivo

1. **Yahoo Finance (yfinance 1.7.0 + chart API v8) funciona para todas as seis bolsas e ADRs** [V]: `.SA`, `.MX`, `.SN`, `.CL`, `.LM`, `.BA` e ADRs/ETFs nos EUA retornaram OHLCV diário, `Adj Close`, dividendos e splits/bonificações. Latência p50 de 83 ms e p95 de 0,55 s; 80 requisições em 1,2 s (8 threads) sem nenhum 429, **desde que** se envie `User-Agent`: sem ele, o primeiro request já devolve `429 Edge: Too Many Requests`. É uma fonte de pesquisa, não um feed licenciado. Os termos do Yahoo são para "uso pessoal" [D].
2. **A qualidade do Yahoo varia por bolsa e exige guardas explícitas** [V]:
   - Santiago (`.SN`): volume **zero** na maior parte de 2026 (SQM-B: 54 pregões com volume 0; FALABELLA/COPEC/CENCOSUD/ENELAM/LTM com mediana de volume 0 nos últimos 3 meses). Esse zero significa dado ausente, não falta de liquidez.
   - Lima (`.LM`): metadados quebrados (`currency=None`, `exchange=YHD`, `quoteType=MUTUALFUND` para BAP.LM e CREDITC1.LM). BAP.LM é cotado em USD.
   - `Ticker.info` mistura moedas e classes: P/B de CIB = 0,002; P/B de SQM-B.SN = 2.889; `floatShares` de PETR4 maior que `sharesOutstanding`.
   - Os campos de short interest só existem para listagens nos EUA.
   - Para B3, o volume do Yahoo bate com o arquivo oficial da B3 com diferença ≤ 0,04%.
3. **O endpoint `tabelas/table/LendingOpenPosition` não serve mais aluguel (BTC)**. O formato de data `YYYY-MM-DD` está correto: a mesma API funciona para `TradeInformationConsolidated` [V]. A tabela devolve vazio para todas as datas testadas (2022–2026), e o canal público UP2DATA hoje só publica 5 tipos de arquivo [V].
4. **O endpoint que funciona para BTC é a API do Boletim Diário (BDI)** [V]: `POST https://arquivos.b3.com.br/bdi/table/{BTBLendingOpenPosition|BTBLoanBalance|BTBTrade}/{data}/{data}/{página}/{take}` com corpo `{}`.
   - Volumes: 2.992 linhas de posição em aberto e 4.713 linhas de empréstimos registrados (com taxas doador/tomador mín/média/máx) para 2026-10-02, em 1,4 s e 3,1 s.
   - `take` máximo é 1000; acima disso a API devolve 400.
   - **A janela histórica é móvel, de ~21 pregões** (a data mais antiga disponível era 2026-09-03). Por isso **a coleta precisa ser diária**, senão o histórico se perde.
   - Publicação em D+1 até 08:00 (SLA de configuração). Observado: `lastUpdateDate` 2026-10-03 entre 04:52 e 06:12.
5. **Sinais reais de aluguel em 2026-10-02** [V]:
   - No IBrX-100, saldo BTC / quantidade teórica (proxy de free float): mediana **7,2%**, p90 **16,3%**. Máximos: MOVI3 26,9%, BEEF3 24,1%, PLPL3 23,6%, TAEE11 22,7%.
   - Taxa tomadora média nos nomes líquidos: YDUQ3 **36,4% a.a.**, BHIA3 35,8% (máx. 50%), CMIN3 25,4%, AZZA3 13,7%, ECOR3 12,8%. Para comparação: PETR4 0,08% e VALE3 0,02%.
   - **"Days-to-cover" calculado sobre o saldo BTC dá mediana de 6,1 dias** no universo líquido (114 nomes). O saldo BTC inclui arbitragem, ETF e hedge, então ele não é comparável ao short interest dos EUA [I]. **Os limiares atuais de `SqueezeSection` (DTC 3/7 dias, SI 5/15%) marcariam mais da metade da B3**; é preciso calibrar por mercado [I].
6. **Short interest de ADRs** [V]:
   - A FINRA Query API (`consolidatedShortInterest`) respondeu **sem credencial**, em 0,64 s, para 48 ADRs LatAm, com histórico desde 2021-12-15. A documentação descreve OAuth [D], então trate o acesso anônimo como frágil.
   - Última data de liquidação: **2026-09-15**. A próxima (2026-09-30) deve ser publicada por volta de **2026-10-09** (regra de 7º dia útil [D]; data [I]).
   - DTC mais altos: EDN 10,7; SCCO 9,2; GGAL 8,0; IRS 7,1; SUPV 6,1; PAGS 6,1.
   - Os campos de short do Yahoo para ADRs coincidem com a FINRA (GGAL 5.579.099; PAGS 19.375.233).
   - O endpoint de short interest da Nasdaq cobre só ações listadas na Nasdaq.
   - O arquivo diário Reg SHO (short **volume**) é gratuito, mas não é short interest.
7. **Macro/FX: todas as fontes testadas respondem** [V]:
   - Respondem sem chave: BCB SGS e PTAX (Olinda), FRED `fredgraph.csv`, BCRP (Peru), datos.gov.co (TRM Colômbia) e BCRA (Argentina).
   - Exigem cadastro: Banxico SIE (token; limites de 80 req/min para dado oportuno e 200 req/5 min para histórico [D]) e BCCh Chile (devolve 302 sem credencial).
   - Pegadinhas: o SGS limita séries diárias a 10 anos por consulta; a série 432 devolve datas futuras; o FRED com vários `id` devolve ZIP; o BCRP devolve `"n.d."`.
8. **Fundamentos** [V]:
   - CVM dados abertos: ITR 2026 (19,6 MB em 2,5 s), FCA (mapa CNPJ↔ticker), composição de capital por classe e IPE (fatos relevantes com atualização diária).
   - A CVM traz `DT_RECEB`/`Data_Entrega` e `VERSAO`, o que permite fundamentos **point-in-time** sem look-ahead.
   - SEC EDGAR (`companyfacts`, `submissions`): 0,2–0,6 s com `User-Agent` declarado e 403 sem ele. Limite de 10 req/s [D].
   - Emissores reestruturados (Grupo Cibest, CIK 2058897) ainda não têm fatos XBRL.
9. **Otimização**: `cvxpy 1.9.3 + CLARABEL` resolveu um problema dollar/beta-neutral com teto de vol de 5% (SOCP, N=150, K=12) em **0,04 s**, com vol ex-ante exatamente 5,00% [V].
   - SCS levou 1,9 s. OSQP parou em `user_limit` e violou o teto de gross. ECOS não vem instalado. HIGHS resolve a variante MILP de cardinalidade em 0,02 s.
   - `skfolio` e `riskfolio` com `budget=0` e objetivo de risco mínimo devolvem a carteira trivial w=0.
   - `PyPortfolioOpt` falhou no caso market-neutral com vol-alvo.
   - **Recomendação: núcleo próprio em cvxpy; skfolio/riskfolio só para pesquisa e relatórios** [I].
10. **Stack recomendada** [I]:
    - Dados: yfinance + fontes oficiais (B3 BDI/UP2DATA/índices, FINRA, BCB/FRED/BCRP/TRM/BCRA, CVM, SEC), cada uma com adaptador próprio.
    - Armazenamento: lake imutável `raw` (bytes + SHA-256), depois Parquet normalizado (pyarrow/zstd), consultado com DuckDB e validado com pandera.
    - Calendários: `exchange_calendars`.
    - Quant: cvxpy (CLARABEL, com SCS e HIGHS), statsmodels, arch, scikit-learn.
    - LLM: Anthropic SDK direto com structured outputs (`messages.parse` + Pydantic) e tools `strict` somente leitura sobre o FactBook. Batches para triagem de notícias. Manter o `DemoProvider` offline.
    - App: Streamlit multipage (`st.navigation`) + Plotly.
11. **Alerta operacional** [V via `exchange_calendars`]: a **próxima segunda (2026-10-12) é feriado em B3, Santiago, BVC e BYMA**; NYSE, BMV e BVL abrem. O ciclo semanal precisa de regra para segunda-feira feriado (decidir na segunda e executar ADRs no dia, locais no próximo pregão, ou antecipar para sexta) [I].

---

## 1. Metodologia e ambiente de teste

- **Ambiente** [V]: Linux, Python 3.13.14, `uv 0.8.17`, saída HTTPS via proxy corporativo com CA própria (todas as chamadas abaixo passaram pelo proxy; nenhum host foi bloqueado).
- **Pacotes testados (venv descartável)** [V]:

  | Pacote | Versão |
  |---|---|
  | yfinance | 1.7.0 |
  | curl-cffi | 0.16.3 |
  | pandas | 3.0.6 |
  | numpy | 2.5.3 |
  | pyarrow | 25.0.1 |
  | cvxpy | 1.9.3 |
  | clarabel | 0.11.1 |
  | osqp | 1.1.3 |
  | scs | 3.3.1 |
  | highspy | 1.15.1 |
  | riskfolio-lib | 7.4.0 |
  | skfolio | 1.4.11 |
  | pyportfolioopt | 1.6.0 |
  | statsmodels | 0.15.0 |
  | arch | 8.0.0 |
  | scikit-learn | 1.9.1 |
  | scipy | 1.18.1 |
  | feedparser | 6.0.14 |
  | exchange-calendars | 4.13.2 |
  | pandas-market-calendars | 5.5.0 |
  | duckdb | 1.5.6 |
  | pandera | 0.33.1 |
- **Latências** são de uma única execução (ou rajada) a partir deste ambiente e servem como ordem de grandeza, não como SLA.
- **Universos de teste**: ~25 tickers locais/ADRs/FX no histórico de 3 anos, 114 ações B3 (volume financeiro > R$ 30 mm em 2026-10-02 no arquivo oficial), IBrX-100 (carteira teórica B3), 52 símbolos de ADRs LatAm na FINRA.

---

## 2. Matriz de fontes testadas

| # | Fonte | Dado | Endpoint (resumo) | Auth | Limites | Latência [V] | Histórico | Status [V] |
|---|---|---|---|---|---|---|---|---|
| 1 | Yahoo chart v8 | OHLCV, adj close, dividendos, splits, meta | `query1.finance.yahoo.com/v8/finance/chart/{sym}` | Nenhuma (exige `User-Agent`) | Não documentado; 80 req/1,2 s ok; sem UA → 429 | 0,17–0,43 s por request; p50 83 ms em rajada | `max` (PETR4 desde 2000) | OK |
| 2 | yfinance 1.7.0 | Batch OHLCV, `info`, calendário, resultados, demonstrativos | Wrapper (chart + quoteSummary com crumb/cookie) | Crumb automático | `yf.config.network.retries` (backoff 1/2/4 s) [D] | 25 tickers × 3 anos: 2,85 s; `info` 0,4–1,0 s/ticker | Igual a 1 | OK (qualidade varia por bolsa) |
| 3 | B3 UP2DATA web (arquivos públicos) | Negócios consolidados, cadastro de instrumentos, posições em derivativos, cenários de margem | `arquivos.b3.com.br/api/download/requestname?fileName=…&date=YYYY-MM-DD&recaptchaToken=` → token → `api/download/?token=` | Nenhuma (reCAPTCHA desligado) | Não documentado | 5,5 MB em 0,56 s; 20 MB em 1,0 s | ~1 mês listado no canal | OK |
| 4 | B3 tabelas API | Mesmas tabelas paginadas (20 linhas/página) | `arquivos.b3.com.br/tabelas/table/{Nome}/{YYYY-MM-DD}/{pág}` | Nenhuma | 20 linhas/página (4.142 páginas para negócios) | 0,28 s/página | Curto | OK, mas **sem** `LendingOpenPosition` |
| 5 | **B3 BDI API** | **BTC: posição em aberto, empréstimos registrados (taxas), negócio a negócio** | `POST arquivos.b3.com.br/bdi/table/{Nome}/{d}/{d}/{pág}/{take}` body `{}` | Nenhuma | `take` ≤ 1000 (5000/2000/1500 → 400) | 1,35 s (2.992 linhas); 3,1 s (4.713) | **~21 pregões (D-21)** | OK |
| 6 | B3 índices (carteira do dia) | Composição IBOV/IBXX/SMLL, quantidade teórica (free float) | `sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{base64(json)}` | Nenhuma | Não documentado | 0,3–0,45 s | Dia corrente | OK |
| 7 | FINRA Query API | Short interest quinzenal (todas as ações listadas nos EUA + OTC) | `POST api.finra.org/data/group/otcMarket/name/consolidatedShortInterest` | Docs: OAuth [D]; teste: funcionou anônimo [V] | 1.200 req/min/IP; 5.000 registros/request (síncrono) [D] | 0,64 s (48 ADRs) | 5 anos rolantes [D] (NU desde 2021-12-15 [V]) | OK |
| 8 | FINRA Reg SHO daily | Short **volume** diário consolidado | `cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt` | Nenhuma | — | 0,40 s (554 KB) | Diário | OK |
| 9 | Nasdaq API | Short interest (só listadas na Nasdaq) | `api.nasdaq.com/api/quote/{SYM}/short-interest?assetClass=stocks` | UA de browser | Não documentado | 3,2 s | ~1 ano | Parcial (PBR: "only supported for Nasdaq Listed") |
| 10 | Nasdaq Trader / NYSE | Listas Reg SHO threshold | `nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth{YYYYMMDD}.txt`; `nyse.com/api/regulatory/threshold-securities/download?...` | Nenhuma | — | < 1 s | Diário | OK |
| 11 | BCB SGS | Selic, CDI, PTAX etc. | `api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados?formato=json&dataInicial=dd/mm/aaaa&dataFinal=…` | Nenhuma | Séries diárias: janela ≤ 10 anos por consulta [V] | 0,9–2,3 s | Longo | OK |
| 12 | BCB PTAX (Olinda) | PTAX compra/venda com timestamp | `olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarPeriodo(...)` | Nenhuma | — | 0,99 s | Longo | OK |
| 13 | Banxico SIE | FIX, TIIE, macro MX | `banxico.org.mx/SieAPIRest/service/v1/series/{ids}/datos/...` | **Token** (`Bmx-Token`) | 80/min e 40 mil/dia (oportuno); 200/5 min e 10 mil/dia (histórico) [D] | — | Longo | Sem token: 400 "Token inválido" [V] |
| 14 | FRED (fredgraph) | UST, Fed funds, VIX, dólar amplo | `fred.stlouisfed.org/graph/fredgraph.csv?id=…&cosd=…&coed=…` | Nenhuma (API JSON exige `api_key`) | — | 0,40 s | Longo | OK (vários `id` → ZIP) |
| 15 | BCRP | PEN/USD, macro Peru | `estadisticas.bcrp.gob.pe/estadisticas/series/api/{códigos}/json/{ini}/{fim}` | Nenhuma | — | 1,1 s | Longo | OK (`"n.d."` para dia sem dado) |
| 16 | datos.gov.co (Socrata) | TRM COP/USD | `datos.gov.co/resource/32sa-8pi3.json?$order=vigenciadesde DESC` | Nenhuma | Socrata padrão | 0,32 s | Longo | OK |
| 17 | BCRA | ARS oficial | `api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones/USD?fechadesde=…` | Nenhuma | — | < 1 s | Longo | OK |
| 18 | BCCh (SIETE) | CLP, macro Chile | `si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx?...` | Usuário/senha | — | — | — | 302 sem credencial [V] |
| 19 | CVM dados abertos | ITR/DFP, cadastro, FCA (tickers), IPE (fatos relevantes) | `dados.cvm.gov.br/dados/CIA_ABERTA/...` | Nenhuma | — | ITR 19,6 MB em 2,5 s; **cadastro 1,5 MB em 23 s** | 2010+ | OK (ITR com atualização semanal [D]) |
| 20 | SEC EDGAR | 20-F/6-K, XBRL company facts | `data.sec.gov/submissions/CIK##########.json`, `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | `User-Agent` com contato obrigatório | **10 req/s** [D] | 0,2–0,6 s | Longo | OK (sem UA → 403) |
| 21 | Google News RSS | Manchetes por empresa (pt-BR, es-419, en) | `news.google.com/rss/search?q=…&hl=…&gl=…&ceid=…` | Nenhuma | Não documentado; ≤ 100 itens por feed | 0,6–0,8 s | Operador `when:7d` | OK (links são redirects do Google) |

---

## 3. Yahoo Finance (yfinance 1.x e chart API)

### 3.1 Endpoints, autenticação e comportamento

- **Chart API v8** [V]: `GET https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`. Parâmetros `range` (`1d…max`) **ou** `period1`/`period2` (epoch), `interval` (`1d`; `60m` testado em PBR), `events=div,splits`, `includeAdjustedClose=true`.
  - Não exige crumb.
  - **Exige `User-Agent`**: com `requests` sem UA, a primeira chamada devolveu `429 Edge: Too Many Requests`.
  - Símbolo inexistente devolve `404 {"code":"Not Found","description":"No data found, symbol may be delisted"}`.
- **quoteSummary v10** (base de `Ticker.info`) [V]: sem crumb devolve `401 Invalid Crumb`. O yfinance 1.7.0 resolve cookie e crumb sozinho, usando `curl_cffi` (dependência obrigatória desde 0.15).
- **Search v1** [V]: `/v1/finance/search` devolveu lista vazia neste ambiente. Não serve para descoberta de tickers; use um security master próprio.
- **Configuração do yfinance** [D]: `yf.config.network.proxy`, `yf.config.network.retries` (backoff exponencial 1/2/4 s), `yf.config.debug.logging`, `yf.config.debug.hide_exceptions`. Há cache persistente de fuso horário e cookie em `~/.cache/py-yfinance` (`yf.set_tz_cache_location`).
- **Termos** [D]: o README do yfinance diz que o projeto não é afiliado ao Yahoo, é para pesquisa/educação, e que "the Yahoo! finance API is intended for personal use only".

### 3.2 Cobertura por bolsa (sufixos testados em 2026-10-05) [V]

| Bolsa | Sufixo | Exemplos que funcionaram | Falhas e observações |
|---|---|---|---|
| B3 | `.SA` | PETR4, PETR3, VALE3, ITUB4, ITUB3, BBDC4, ABEV3, WEGE3, B3SA3, MGLU3, **EMBJ3**, mais 114 nomes líquidos | **EMBR3 → 404** (ticker trocado para EMBJ3). Bonificações aparecem como splits (ITUB4: 110:100 em 2025-03-18 e 103:100 em 2025-12-26) |
| BMV | `.MX` | WALMEX, GFNORTEO, AMXB, FEMSAUBD | — |
| Santiago | `.SN` | SQM-B, CHILE, FALABELLA, CENCOSUD, COPEC, BSANTANDER, ENELAM, LTM | **Volume = 0** em 51–54 pregões de 2026 (último volume não-nulo de SQM-B em 2026-07-17; FALABELLA/COPEC em 2026-09-16). `^IPSA` → 404 |
| BVC | `.CL` | **CIBEST, PFCIBEST**, ECOPETROL, ISA, GRUPOSURA, NUTRESA, BVC, PFAVAL, CEMARGOS | **BCOLOMBIA.CL / PFBCOLOM.CL → 404** (Bancolombia → Grupo Cibest) |
| BVL | `.LM` | CREDITC1, ALICORC1, FERREYC1, BAP | Metadados quebrados: `currency=None`, `exchange=YHD`, `instrumentType=MUTUALFUND`. **BAP.LM é cotado em USD** (razão implícita BAP/BAP.LM × PEN = 3,33 ≈ PEN/USD). `^SPBLPGPT` → 404 |
| BYMA | `.BA` | GGAL, YPFD | Ver anomalia de YPFD.BA em §3.8 |
| EUA (ADRs/ETFs) | — | PBR, PBR-A, VALE, ITUB, BBD, NU, GGAL, YPF, CIB, BAP, PAGS, STNE, MELI, SQM, AMX, BSAC, EC, CX, ASR, PAC, FMX, BVN, SCCO, XP, SBS, SUZ, GGB, KOF, BMA, VIST, EWZ, EWW, ILF | **ERJ → 404** (provável troca de ticker da Embraer, como EMBR3→EMBJ3 [I]) |
| Índices | `^` | ^BVSP, ^MXX, ^MERV | ^IPSA, ^SPBLPGPT → 404 |

### 3.3 Latência e limites observados [V]

- Requests isolados ao chart API: 0,17–0,43 s.
- Rajada de 80 requests de 1 ano (20 ações B3 × 4) com 8 threads: **1,23 s** de parede. Códigos: 76 × 200 e 4 × 404 (EMBR3). p50 83 ms, p95 0,55 s, **zero 429**. Com `curl_cffi` impersonando Chrome: 1,86 s, p50 158 ms.
- `yf.download` de 25 tickers × 3 anos: **2,85 s** (782 × 201 colunas). 114 tickers B3 × 3 meses: 7,6 s.
- `Ticker.info`: 0,43–0,96 s por ticker, 45–184 chaves.
- [I] Não há limite oficial publicado. Use concorrência ≤ 8 por host, `User-Agent` sempre, retry com backoff, e cache em disco do dia (EOD imutável após D+1).

### 3.4 Preços ajustados, dividendos e splits [V]

- Com `auto_adjust=False`, `Close` vem ajustado **só por splits** e `Adj Close` por splits **e** dividendos. A razão `Adj/Close` na primeira observação (2023-10-02) mede o dividendo acumulado em 3 anos:

  | Ticker | `Adj/Close` em 2023-10-02 |
  |---|---|
  | PETR4 | 0,663 |
  | PBR | 0,710 |
  | CIB | 0,651 |
  | ECOPETROL | 0,684 |
  | CIBEST.CL | 0,758 |
  | SQM-B.SN | 0,9999 |
  | YPF | 1,000 |

  **Retorno total é obrigatório** para fatores e risco; usar `Close` puro distorce momentum e valor de nomes de alto dividendo.
- Eventos (2023-10 a 2026-10): PETR4 teve 14 dividendos; ITUB4 teve 49 dividendos e 2 "splits" (bonificações); GGAL.BA, 19 dividendos; CIBEST.CL, 11.
- [I] Guarde **as duas séries** (bruta e ajustada) e os eventos no raw. O ajuste do Yahoo é recalculado a cada novo dividendo, então o histórico ajustado **muda** retroativamente; por isso o hash precisa ser por snapshot.

### 3.5 `Ticker.info`: campos e qualidade [V]

| Campo | Local (PETR4.SA, WALMEX.MX, SQM-B.SN, CIBEST.CL, GGAL.BA) | ADR/EUA (PBR, CIB, GGAL, STNE, PAGS, NU, MELI, BAP, SQM) | Problemas encontrados |
|---|---|---|---|
| `marketCap`, `sharesOutstanding`, `floatShares` | Presentes | Presentes | PETR4: `floatShares` 7,88 bi > `sharesOutstanding` 5,45 bi (mistura PN/ON). GGAL: `floatShares` 837 mi em ações locais, enquanto `sharesShort` vem em ADS |
| `sharesShort`, `shortPercentOfFloat`, `shortRatio`, `dateShortInterest` | **None** em todas as linhas locais | Presentes, data 2026-09-15 (igual à FINRA) | SI% do ADR é calculado contra o float do ADR, não contra o float total da empresa |
| `trailingPE`, `forwardPE`, `priceToBook`, `returnOnEquity`, `enterpriseToEbitda` | Presentes (exceto CREDITC1.LM) | Presentes | **Moeda misturada**: CIB P/B = 0,00207 (preço USD / patrimônio COP); SQM-B.SN P/B = 2.889 e EV/EBITDA = 6.071 (preço CLP / demonstrativo USD); GGAL P/B 9,50 vs GGAL.BA 1,02 (ignora razão de ADR) |
| `beta` | Presente | Presente | PETR4/PBR β = −0,213 (beta de 5 anos contra o S&P; inútil para neutralidade LatAm) |
| `sector`, `industry` | Presentes | Presentes | CREDITC1.LM sem setor (`MUTUALFUND`) |
| `earningsTimestamp*`, `mostRecentQuarter` | Parcial | Presentes | `earningsTimestampStart` de PETR4.SA = 2025-08-07 (velho) |

**Conclusão [I]**: use `info` só para **metadados** (setor/indústria) e como checagem cruzada. Calcule múltiplos, betas e SI% no código, a partir de preço, FX, demonstrativos (CVM/SEC) e contagem de ações por classe. Respeite a invariante do repositório de que os números vêm do código.

### 3.6 Datas de resultado [V]

- `Ticker.calendar` traz a próxima data para ADRs e alguns locais:

  | Ticker | Próximo resultado |
  |---|---|
  | PBR | 2026-11-10 |
  | WALMEX.MX | 2026-10-27 |
  | CIB | 2026-11-09 |
  | GGAL | 2026-11-24 |
  | SQM | 2026-11-17 (via `earningsTimestamp`) |

  **Para PETR4.SA, `Earnings Date` vem vazio.**
- `Ticker.get_earnings_dates(limit=8)` traz histórico, estimativa e surpresa (PETR4.SA inclusive) em 0,5–1,5 s.
- [I] Regra: data de resultado da linha local = do ADR quando existir; para nomes só locais, use o **cronograma de eventos corporativos da CVM (IPE)** e o histórico de `get_earnings_dates`.

### 3.7 Câmbio (FX) [V]

- `BRL=X`, `MXN=X`, `CLP=X`, `COP=X`, `PEN=X` e `ARS=X` retornaram 780 observações em 3 anos.
  - Volume é sempre 0, como esperado para FX.
  - **O índice diário fica em Europe/London** (`2026-10-02 00:00+01:00`): o "close" do Yahoo **não** é o fechamento da B3 nem o fixing oficial.
- PTAX venda em 2026-10-02 = **5,2238** (BCB, boletim de fechamento ~13:03 BRT) vs `BRL=X` close **5,2226**.
- [I] Política recomendada:
  - Valorização (NAV/track record) com **um único snapshot de FX por dia** (mesmo horário, documentado no manifesto).
  - Fixings oficiais (PTAX, FIX Banxico, TRM, BCRP, BCRA) como trilha de auditoria.
  - Para ARS, guardar também o **CCL implícito** (ADR/local), já que o oficial diverge.
  - O padrão institucional (WM/Reuters 16h Londres) é pago.

### 3.8 Razões de ADR implícitas (ADR × FX / local) [V, preços de 2026-10-02]

| ADR | Linha local | ADR USD | Local | FX | Razão implícita | Leitura [I] |
|---|---|---|---|---|---|---|
| PBR | PETR3.SA | 21,65 | 56,62 | 5,223 | 1,997 | 1 ADS = 2 ON |
| PBR-A | PETR4.SA | 19,60 | 51,17 | 5,223 | 2,000 | 1 ADS = 2 PN |
| VALE | VALE3.SA | 13,76 | 72,10 | 5,223 | 0,997 | 1:1 |
| ITUB | ITUB4.SA | 8,59 | 44,83 | 5,223 | 1,001 | 1:1 |
| CIB | PFCIBEST.CL | 91,91 | 75.000 | 3.318,5 | 4,067 | 1 ADS = 4 pref. |
| EC | ECOPETROL.CL | 16,60 | 2.705 | 3.318,5 | 20,37 | 1 ADS = 20 |
| SQM | SQM-B.SN | 64,52 | 65.450 | 981,2 | 0,967 | 1:1 (gap de 3%: horário/CLP) |
| AMX | AMXB.MX | 21,29 | 19,35 | 18,31 | 20,15 | 1 ADS = 20 |
| FMX | FEMSAUBD.MX | 115,68 | 210,00 | 18,31 | 10,09 | 1 ADS = 10 units |
| GGAL | GGAL.BA | 35,89 | 5.835 | 1.524,9 (oficial) | 9,38 | 1 ADS = 10 → prêmio CCL ≈ 6,6% |
| YPF | YPFD.BA | 49,67 | 8.050 | 1.524,9 | 9,41 | **Anomalia**: a razão documentada pelo depositário é, até onde sabemos, 1:1 (verificar); série YPFD.BA suspeita |
| BAP | BAP.LM | 373,31 | 375,02 | 3,349 | 3,33 | Não é razão: BAP.LM já está em USD |

**Uso [I]**:

1. O security master guarda a razão **oficial** (depositário) e a moeda de cotação de cada linha.
2. O código calcula a razão implícita diariamente e alerta se `|implícita/oficial − 1| > 3%` (5% para ARS, após ajuste por CCL).
3. A paridade ADR↔local entra no risco: ADR e local do mesmo emissor nunca contam como diversificação.

### 3.9 Modos de falha do Yahoo e defesa

| Modo de falha [V] | Defesa [I] |
|---|---|
| 429 sem `User-Agent` | Sempre UA; `curl_cffi` via yfinance; ≤ 8 threads; retry exponencial |
| 404 por ticker renomeado (EMBR3, ERJ, BCOLOMBIA) | Security master com histórico de tickers (`valid_from/valid_to`) cruzado com CVM FCA (`Codigo_Negociacao`, `Data_Inicio/Fim_Negociacao`) e SEC `company_tickers_exchange.json` |
| Volume 0 com preço válido (Santiago) | Converter para **NaN + flag `volume_suspeito`**, nunca 0. A liquidez de CL vem do ADR (FINRA/Yahoo) ou é marcada como ausente; o nome fica fora do book até ter ADV confiável |
| Metadados errados (`.LM`) | Moeda/bolsa vêm do security master, nunca do `meta` |
| `info` com múltiplos em moedas cruzadas | Não usar múltiplos do Yahoo; calcular no código |
| Histórico ajustado muda com novos dividendos | Snapshot imutável com hash; comparar `Adj Close` entre snapshots só após reajuste |
| FX em fuso de Londres | Alinhar por data de pregão local; documentar o horário do snapshot |
| Série local suspeita (YPFD.BA) | Checagem de paridade ADR↔local; quarentena automática |
| `^IPSA` e outros índices ausentes | Benchmark de mercado por ETF (ILF/ECH/EWZ/EWW) ou índice construído no código a partir dos componentes |

### 3.10 Snippets funcionais [V]

```python
# Chart API v8 bruto (testado: ITUB4.SA, 750 barras, 49 dividendos, 2 bonificações)
import requests, pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (compatible; latam-ls-research)"}

def yahoo_chart(symbol: str, period1: int, period2: int, interval: str = "1d") -> dict | None:
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"period1": period1, "period2": period2, "interval": interval,
                             "events": "div,splits", "includeAdjustedClose": "true"},
                     headers=UA, timeout=20)
    if r.status_code == 404:
        return None                      # ticker inexistente/renomeado -> security master
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    tz = res["meta"]["exchangeTimezoneName"]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).normalize().date
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")}, index=idx)
    df["adjclose"] = res["indicators"]["adjclose"][0]["adjclose"]
    ev = res.get("events", {})
    return {"meta": res["meta"], "bars": df,
            "dividends": ev.get("dividends", {}), "splits": ev.get("splits", {})}
```

```python
# yfinance em lote (testado: 25 tickers x 3 anos em 2,85 s)
import yfinance as yf
df = yf.download(["PETR4.SA", "WALMEX.MX", "SQM-B.SN", "CIBEST.CL", "CREDITC1.LM", "GGAL.BA",
                  "PBR", "CIB", "BRL=X", "MXN=X"],
                 start="2023-10-01", end="2026-10-03", interval="1d",
                 auto_adjust=False, actions=True, group_by="column", threads=True, progress=False)
close, adj, vol = df["Close"], df["Adj Close"], df["Volume"]
vol = vol.mask((vol == 0) & close.notna())   # volume 0 com preço = dado ausente (nunca zero)
```

---

## 4. B3: dados oficiais públicos (liquidez, aluguel/BTC, índices)

### 4.1 Diagnóstico: por que `LendingOpenPosition` veio vazio [V]

- `GET https://arquivos.b3.com.br/tabelas/table/LendingOpenPosition/{data}/1` devolveu `{"name":null,…,"values":[],"pageCount":0}` para 2026-10-02, 2026-10-01, 2026-09-30, 2026-09-15, 2025-12-01, 2025-06-02, 2024-06-03, 2024-01-05 e 2023-06-01. Variantes (`LendingOpenPositionConsolidated`, `SecuritiesLendingOpenPosition`, `AssetLoan`) também vieram vazias.
- **O formato de data está certo**: `TradeInformationConsolidated`, `InstrumentsConsolidated`, `DerivativesOpenPosition` e `MarginScenarioLiquidAssets` responderam com dados para `2026-10-02` na mesma API.
- O canal público `Web/Consolidated` do UP2DATA (`/api/channels/.../publications`) lista apenas 5 tipos de arquivo de 2026-09-04 a 2026-10-05:
  - `InstrumentsConsolidatedFile`
  - `MarginScenarioLiquidAssetsFile`
  - `TradeInformationConsolidatedFile`
  - `TradeInformationConsolidatedAfterHoursFile`
  - `DerivativesOpenPositionFile`

  `download/requestname?fileName=LendingOpenPositionFile` devolve 400.
- [I] O dataset de aluguel saiu do UP2DATA web público e hoje é servido pelo **BDI** (Boletim Diário), em tabelas `BTB*`.

### 4.2 API do BDI para BTC (o endpoint que funciona) [V]

**Descoberta**: `GET https://arquivos.b3.com.br/bdi/table/classifications` lista 69 tabelas. A classificação "Empréstimos de ativos" contém:

| Tabela | Nome B3 | Colunas (API) |
|---|---|---|
| `BTBLendingOpenPosition` | Posições em aberto | `RptDt, DtRef, TckrSymb, ISIN, Company, Type, Market, StockBalance, AvgPric, Balance` |
| `BTBLoanBalance` | Empréstimos registrados | `RptDt, DtRef, TckrSymb, ISIN, Company, Market, QtyCtrctsDay, ValCtrctsDay, DnrMinRate, DnrAvrgRate, DnrMaxRate, TkrMinRate, TkrAvrgRate, TkrMaxRate, BRLValue, Dnr, Tkr` |
| `BTBTrade` | Negócio a negócio | `TckrSymb, Quantity, Rate, TradeId, MarketBTB, EntryDate, EntryTime, EntrySeller(Nm), EntryBuyer(Nm), UpdateAction, TradeSessionId, Seller, Buyer` (1.919 páginas de 20 em 2026-10-02) |
| `Renewals` | Renovações | (não inspecionada) |

**Chamada**: `POST https://arquivos.b3.com.br/bdi/table/{Nome}/{YYYY-MM-DD}/{YYYY-MM-DD}/{página}/{take}`, `Content-Type: application/json`, corpo `{}`. O mesmo app expõe `GetTablePaged` (GET, `?filter=RowKey startswith '...'`), exportação CSV (`/table/export/csv`, POST) e o status do boletim (`/download/status?dateRef=`).

**Comportamento medido**:

- `take` = 1000 funciona; 1500, 2000 e 5000 → **400**.
- Paginação por `table.pageCount`.
- 2.992 linhas de posição em 3 páginas (1,35 s); 4.713 de empréstimos em 5 páginas (3,1 s).
- **Janela histórica**: 2026-09-03 tinha dados (149 páginas de 20) e 2026-09-02 vinha vazio. São exatamente 21 pregões até 2026-10-02 (7/9 foi feriado), coerente com `limitDate: "D-21"` na configuração da tabela. 2026-10-05 (hoje) ainda vazio.
- **Publicação**: `configuration.SLA = "8:00:00"`, `NextDayDate = 1`. `lastUpdateDate` de 2026-10-02 foi 2026-10-03 04:52 (LoanBalance) e 06:12 (OpenPosition).
- PDFs do BDI: `https://arquivos.b3.com.br/bdi/download/bdi/2026-10-02/BDI_04-2_20261002.pdf` (740 KB, 11.782 linhas de texto) traz a mesma tabela de empréstimos registrados. Datas antigas (2025-06-02, 2024-01-05, 2022-03-02) → HTTP 500.

**Semântica e pegadinhas**:

- Taxas em **fração ao ano** (0,0516 = 5,16% a.a.) [V].
- Metodologia (texto do PDF) [V]: taxa média = média ponderada pela quantidade de negócios do dia; **em dias sem negociação, publica-se a última taxa calculada**. Portanto taxa sem contratos no dia é **taxa velha**: use `QtyCtrctsDay > 0` ou uma flag de defasagem.
- Em todas as linhas inspecionadas, `DnrAvrgRate == TkrAvrgRate` (doador = tomador) [V]. O spread de intermediação não aparece; trate como "taxa de referência", não como custo efetivo do prime broker [I].
- `ValCtrctsDay` é rotulado "Quantidade de ativos" (o nome da coluna engana) [V].
- `Market` ∈ {`Registro`, `Neg. Eletrônica D+0`, `Neg. Eletrônica D+1`, `Total`, `ETF Renda Fixa`}. Use a linha **`Total`** para saldo. `AvgPric` é NaN na linha `Total` [V].
- `Type` inclui ações (ON/PN, NM/N1/N2), BDRs (DRN/DRE), ETFs (CI) e outros. Filtre pelo security master [V].
- [I] **O saldo BTC não é short interest**: inclui aluguel para arbitragem (ON/PN, ADR, ETF, long-and-short, cobertura de opções). Exemplos: BOVA11/BOVV11/IVVB11, ITUB3 e TAEE11 no topo do "DTC". Use-o como **limite superior** do short e combine com a taxa.

**Snippet funcional [V]**:

```python
import requests, pandas as pd

BDI = "https://arquivos.b3.com.br/bdi/table"

def bdi_table(name: str, date: str, take: int = 1000, max_pages: int = 200) -> tuple[pd.DataFrame, dict]:
    """Pagina uma tabela do BDI (API V2, POST). date = YYYY-MM-DD (pregão de referência)."""
    frames, meta, page = [], {}, 1
    while page <= max_pages:
        r = requests.post(f"{BDI}/{name}/{date}/{date}/{page}/{take}", json={}, timeout=60)
        r.raise_for_status()
        d = r.json(); t = d["table"]
        if page == 1:
            meta = {"lastUpdateDate": d.get("lastUpdateDate"), "pageCount": t.get("pageCount"),
                    "columns": [c["name"] for c in t["columns"]], "limitDate": t.get("limitDate")}
        if not t["values"]:
            break                                   # fora da janela D-21 ou ainda não publicado
        frames.append(pd.DataFrame(t["values"], columns=meta["columns"]))
        if page >= (t.get("pageCount") or 1):
            break
        page += 1
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=meta.get("columns", []))
    return df, meta

open_pos, m1 = bdi_table("BTBLendingOpenPosition", "2026-10-02")   # 2.992 linhas
loans, m2 = bdi_table("BTBLoanBalance", "2026-10-02")              # 4.713 linhas
```

### 4.3 Resultados reais de 2026-10-02 (para calibrar o modelo de squeeze) [V]

**(a) Saldo BTC como % da quantidade teórica do IBrX-100.** A quantidade teórica do índice é uma proxy de free float (§4.5). Cobertura de 100/100 nomes; mediana 7,2%, p90 16,3%.

| Ticker | Empresa | Peso IBrX (%) | BTC/qtd. teórica (%) | Taxa tomador média (a.a.) |
|---|---|---|---|---|
| MOVI3 | Movida | 0,070 | 26,9 | 0,7% |
| BEEF3 | Minerva | 0,060 | 24,1 | 5,1% |
| PLPL3 | Plano & Plano | 0,014 | 23,6 | 0,5% |
| TAEE11 | Taesa | 0,326 | 22,7 | 0,6% |
| JHSF3 | JHSF | 0,107 | 19,6 | 0,9% |
| EZTC3 | EZTec | 0,061 | 18,7 | 0,1% |
| AURE3 | Auren | 0,153 | 18,7 | 0,1% |
| AZZA3 | Azzas 2154 | 0,089 | 18,1 | 13,7% |
| ANIM3 | Ânima | 0,025 | 17,6 | 1,5% |
| MRVE3 | MRV | 0,073 | 17,0 | 10,6% |
| MGLU3 | Magazine Luiza | 0,103 | 16,2 | 5,2% |
| SLCE3 | SLC Agrícola | 0,132 | 16,0 | 0,1% |

**(b) Maior custo de aluguel no universo líquido** (114 nomes com volume financeiro > R$ 30 mm em 2026-10-02; ADV de 20 pregões do Yahoo).

| Ticker | ADV20 (R$ mm) | "DTC" BTC (dias) | Taxa tomador média | Taxa máx. | Contratos no dia |
|---|---|---|---|---|---|
| YDUQ3 | 63,3 | 4,1 | 36,4% | 37,7% | 337 |
| BHIA3 | 9,5 | 3,9 | 35,8% | 50,0% | 182 |
| CMIN3 | 51,7 | 12,8 | 25,4% | 40,0% | 1.206 |
| AZZA3 | 55,4 | 6,4 | 13,7% | 20,0% | 1.921 |
| ECOR3 | 90,4 | 4,9 | 12,8% | 30,0% | 313 |
| NATU3 | 61,8 | 5,8 | 11,2% | 11,5% | 171 |
| MRVE3 | 67,3 | 5,2 | 10,6% | 12,1% | 283 |
| HAPV3 | 57,0 | 2,4 | 9,4% | 9,4% | 68 |

Referências: PETR4 0,08% a.a. (599 contratos em registro), VALE3 0,02%, MGLU3 5,16%, CASH3 0,78%, IRBR3 0,03%.

**(c) Distribuição**: no universo líquido de 112 nomes com BTC, a mediana de "DTC" BTC (saldo/ADV20 em ações) é **6,07 dias**, 69 nomes ficam acima de 5 dias, 15 nomes têm taxa > 5% a.a. e 8 têm taxa > 8% a.a.

**Implicação para `configs` [I]**: `SqueezeSection` usa `days_to_cover_medium=3`, `high=7`, `si_pct_float_medium=5%`, `high=15%`. Aplicados ao saldo BTC, esses limiares marcariam a maioria da B3 como risco médio. Recomendação: parametrizar **por mercado**.

- **BR (BTC)**: taxa tomadora como sinal primário (médio ≥ 5%, alto ≥ 15% a.a.), BTC/free float secundário (médio ≥ 15%, alto ≥ 25%) e "DTC" BTC só como terciário (médio ≥ 10, alto ≥ 20).
- **ADR (FINRA)**: manter DTC 3/7 e SI%float 5/15%, com SI convertido em ações-equivalentes. Mesmo assim, 21 de 48 ADRs LatAm têm DTC > 3 (§5.3), então "médio" com 3 dias é amplo; considere 5.

O `gc_borrow_fee_br=0,8%` "estimado quando sem dado" pode ser substituído pela taxa observada, mantendo o default só como fallback.

### 4.4 Arquivos oficiais de negociação: liquidez auditável [V]

- **Fluxo de token**:
  1. `GET https://arquivos.b3.com.br/api/download/requestname?fileName=TradeInformationConsolidatedFile&date=2026-10-02&recaptchaToken=` → `{"redirectUrl": "...", "token": "..."}`
  2. `GET https://arquivos.b3.com.br/api/download/?token=...` → CSV.
- `TradeInformationConsolidatedFile_20261002_1.csv` [V]: 5,5 MB em 0,56 s.
  - A primeira linha é `Status do Arquivo: Final` (pular). Separador `;`, decimal `,`.
  - Colunas: `RptDt;TckrSymb;ISIN;SgmtNm;MinPric;MaxPric;TradAvrgPric;LastPric;OscnPctg;AdjstdQt;AdjstdQtTax;RefPric;TradQty;FinInstrmQty;NtlFinVol`.
  - Segmentos: CASH 1.471, EQUITY CALL/PUT 36.683 cada, FINANCIAL, AGRIBUSINESS, ODD LOT, FORWARD, block trade.
- `InstrumentsConsolidatedFile_20261002_1.csv` [V]: 20,3 MB em 1,0 s (cadastro com ISIN, tipo, datas, lote etc.).
- **Reconciliação Yahoo × B3** (2026-10-02, `FinInstrmQty` ÷ volume Yahoo) [V]:

  | Ticker | Razão |
  |---|---|
  | PETR4 | 1,0000 |
  | ITUB4 | 1,0000 |
  | EMBJ3 | 1,0000 |
  | VALE3 | 0,9999 |
  | MGLU3 | 0,9996 |

  Os preços de fechamento são idênticos. [I] Use o Yahoo para histórico e o arquivo B3 para liquidez **oficial** do último pregão e para auditoria. `NtlFinVol` é o volume financeiro em BRL do dia.
- Caveat [V]: o canal público lista só ~1 mês de arquivos. [I] Snapshot diário obrigatório se quisermos ADV oficial histórico.

### 4.5 Carteiras teóricas de índices: universo e proxy de free float [V]

- `GET https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{base64(json)}` com `{"language":"pt-br","pageNumber":1,"pageSize":200,"index":"IBXX","segment":"1"}`. Resultados:

  | Índice | Ativos | Quantidade teórica total |
  |---|---|---|
  | IBOV | 76 | 93,8 bi |
  | IBXX | 100 | — |
  | SMLL | 104 | — |

  O header traz `date: "05/10/26"` e `reductor`. Cada linha traz `cod`, `asset`, `type`, `part` (peso %) e `theoricalQty`.
- [I] A metodologia B3 usa ações em circulação (free float) na quantidade teórica, o que serve de denominador para BTC/free float. Confirme por emissor com a composição de capital da CVM (§7.1).

### 4.6 Limitações da B3 gratuita

- Sem histórico longo de BTC [V]; sem taxa efetiva de prime broker [I]; sem dados intradiários de book [I].
- Aluguel local utilizável por um fundo offshore depende de estrutura de investidor não residente, custodiante e prime broker locais (fora do escopo deste documento) [I].

---

## 5. Short interest de ADRs: FINRA, Nasdaq e NYSE

### 5.1 FINRA: o que é e quando sai [D]

- Cobre **todas** as ações listadas em bolsa nos EUA e OTC (FINRA Rule 4560).
- Reporte **2× ao mês**: dia 15 (ou o dia útil de liquidação anterior) e último dia útil do mês. As firmas reportam até as 18h ET do 2º dia útil.
- **Publicação no 7º dia útil após a data de liquidação.** Grid e API com 5 anos rolantes.
- [I] Para a liquidação de 2026-09-30, a publicação esperada é **sexta, 2026-10-09**. Na segunda 2026-10-05 o dado mais recente utilizável é o de **2026-09-15**, defasado em 20 dias corridos.

### 5.2 Query API: funcionou sem credencial [V]

```python
import requests, pandas as pd

URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"

def finra_short_interest(symbols: list[str], settlement_date: str | None = None) -> pd.DataFrame:
    flt = ([{"compareType": "EQUAL", "fieldName": "settlementDate", "fieldValue": settlement_date}]
           if settlement_date else [])
    body = {"limit": 5000, "compareFilters": flt,
            "domainFilters": [{"fieldName": "symbolCode", "values": symbols}],
            "fields": ["settlementDate", "symbolCode", "issueName", "marketClassCode",
                       "currentShortPositionQuantity", "previousShortPositionQuantity",
                       "averageDailyVolumeQuantity", "daysToCoverQuantity", "changePercent",
                       "revisionFlag"]}
    r = requests.post(URL, json=body, headers={"Accept": "application/json"}, timeout=30)
    r.raise_for_status()                    # headers: record-total, record-max-limit: 5000
    return pd.DataFrame(r.json())

si = finra_short_interest(["PBR", "VALE", "GGAL", "PAGS", "STNE", "NU", "CIB", "BAP"], "2026-09-15")
```

- Ordenar (`sortFields`) exige filtro `EQUAL` na chave de partição `settlementDate`; sem ele, a API devolve 400 com mensagem explícita [V].
- Headers de resposta: `record-total`, `record-limit` e `record-max-limit: 5000` [V].
- A documentação descreve OAuth 2.0 (credencial "Public" provisionável para indivíduos), throttling de 1.200 req/min/IP no modo síncrono e 5.000 registros por request [D]. [I] Implemente o cliente com credencial opcional (`FINRA_CLIENT_ID/SECRET`) e caia para anônimo; se receber 401/403, use o histórico do lake e marque o dado como defasado.

### 5.3 Resultado real: ADRs LatAm, liquidação 2026-09-15 [V]

48 símbolos retornados de 52 consultados.

| ADR | Mercado | SI (ações) | ADV | DTC | Var. % vs anterior |
|---|---|---|---|---|---|
| EDN | NYSE | 681.351 | 63.484 | 10,73 | −10,7 |
| SCCO | NYSE | 10.320.349 | 1.125.825 | 9,17 | −2,7 |
| GGAL | Nasdaq (SC) | 5.579.099 | 696.860 | 8,01 | +2,4 |
| IRS | NYSE | 1.442.957 | 201.973 | 7,14 | +17,5 |
| SUPV | NYSE | 2.466.255 | 404.915 | 6,09 | −7,3 |
| PAGS | NYSE | 19.375.233 | 3.199.258 | 6,06 | +4,1 |
| ASR | NYSE | 271.134 | 46.362 | 5,85 | +20,6 |
| AFYA | Nasdaq | 1.411.623 | 274.094 | 5,15 | **+163,2** |
| FMX | NYSE | 1.763.219 | 346.188 | 5,09 | −5,3 |
| EC | NYSE | 7.618.780 | 1.607.714 | 4,74 | +7,1 |

- 21 dos 48 ADRs têm DTC > 3.
- O Yahoo `info` de GGAL (5.579.099, `dateShortInterest` 2026-09-15) e de PAGS (19.375.233) bate exatamente com a FINRA [V].

### 5.4 Fontes complementares [V]

- **Reg SHO daily short volume** (FINRA CDN): `Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market`, com quantidades fracionárias. Exemplos em 2026-10-02:

  | ADR | Short volume | Total | Short (%) |
  |---|---|---|---|
  | PBR | 3,79 mi | 8,07 mi | 47% |
  | NU | 25,4 mi | 40,8 mi | 62% |

  [I] Short volume inclui market making e hedge intradiário. Use só como sinal fraco ou de variação, nunca como posição.
- **Nasdaq** `api.nasdaq.com/.../short-interest`: STNE trouxe histórico quinzenal (DTC 2,90 em 2026-09-15). PBR: "only supported for Nasdaq Listed stocks". Latência de 3,2 s.
- **Listas Reg SHO threshold** (Nasdaq Trader e NYSE): arquivos diários `|`-delimitados, úteis como **flag de fail-to-deliver persistente** em ADRs.
- [I] **SI% de float para ADR**: compute `SI_ADS × razão_ADR / free_float_total_ações` (ou contra ADS em circulação, se disponível no 20-F). O `shortPercentOfFloat` do Yahoo mistura bases (GGAL: `floatShares` 837 mi em ações locais versus SI em ADS).

---

## 6. Macro e câmbio

| Fonte | Chamada testada [V] | Resultado em 2026-10-02 [V] | Pegadinhas [V] |
|---|---|---|---|
| BCB SGS 432 (Selic meta) | `.../bcdata.sgs.432/dados/ultimos/3?formato=json` | 13,75% | **Devolveu datas futuras** (02–04/11/2026): a série diária é preenchida até a próxima reunião. Filtrar `data ≤ as_of` |
| BCB SGS 11/12 (Selic/CDI diária) | idem | 0,050788% ao dia | Taxa diária em %; anualizar no código: (1+r)^252−1 |
| BCB SGS 4389 (CDI anualizado) | idem | 13,65% a.a. | Ordem invertida (mais recente primeiro) |
| BCB SGS 1 (PTAX venda) | idem | 5,2238 | — |
| BCB SGS (janela) | `dataInicial=01/01/2010&dataFinal=02/10/2026` | Erro | "janela de consulta de, no máximo, 10 anos em séries de periodicidade diária": fatiar por década |
| PTAX Olinda | `CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)?@dataInicial='09-28-2026'&@dataFinalCotacao='10-02-2026'&$format=json` | 5,22320/5,22380 às 13:03:16 | Datas em `MM-DD-YYYY` |
| FRED | `fredgraph.csv?id=DGS3MO&cosd=2026-09-25&coed=2026-10-02` | DGS3MO 4,17 (2026-10-01) | Último dia ainda ausente (defasagem de 1 dia); **vários `id` → ZIP** com `daily.csv`; a API JSON exige `api_key` |
| Banxico SIE | `.../series/SF43718,SF61745/datos/oportuno` | 400 "Token inválido" | Token gratuito por cadastro; limites [D]: 80/min e 40 mil/dia (oportuno), 200/5 min e 10 mil/dia (histórico); o bloqueio dura até o fim da janela (headers `Bmx-timeReset`, `Bmx-secondsToReset`) |
| BCRP | `.../api/PD04640PD-PD04722MD/json/2026-09-25/2026-10-02` | PEN venda 3,454 (2026-10-01) | 2026-10-02 = `"n.d."`: parse como NaN, nunca 0 |
| datos.gov.co TRM | `resource/32sa-8pi3.json?$order=vigenciadesde DESC&$limit=3` | 3.307,73 (vigência 2026-10-02); 3.273,49 (vigência 03–05/10) | TRM é a taxa **do dia de vigência** (calculada no dia útil anterior) |
| BCRA | `estadisticascambiarias/v1.0/Cotizaciones/USD?fechadesde=…&fechahasta=…` | 1.520,00 ARS | Oficial ≠ CCL; guardar ambos |
| BCCh | `SieteRestWS.ashx?function=GetSeries&...` | 302 (página de erro) | Exige usuário/senha de cadastro |

[I] Recomendação: macro serve para **contexto** (narrativa do LLM e regimes de risco), não como entrada direta do otimizador. O otimizador usa retornos em USD, que já embutem o FX. A taxa livre de risco do fundo em USD sai do FRED (DGS3MO ou DFF).

---

## 7. Fundamentos: CVM (Brasil) e SEC EDGAR (ADRs)

### 7.1 CVM dados abertos [V]

| Dataset | URL | Teste | Uso |
|---|---|---|---|
| Cadastro | `dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv` | 1,49 MB em **23 s** (servidor lento) | CNPJ, situação, setor, controle |
| ITR | `.../DOC/ITR/DADOS/itr_cia_aberta_2026.zip` | 19,6 MB em 2,5 s; 19 CSVs (BPA/BPP/DRE/DFC/DMPL/DVA, con/ind, composição de capital, parecer) | DRE trimestral, patrimônio, dívida |
| DFP | `.../DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip` | Mesmo layout (não baixado) | Anual |
| FCA | `.../DOC/FCA/DADOS/fca_cia_aberta_2026.zip` | 0,36 MB em 1,07 s | **Mapa CNPJ↔ticker** (`Codigo_Negociacao`, `Segmento`, `Data_Inicio/Fim_Negociacao`), ex.: EMBJ3, PETR3/PETR4, VALE3 |
| IPE | `.../DOC/IPE/DADOS/ipe_cia_aberta_2026.zip` | 1,69 MB em 1,35 s; 36.032 documentos; **1.988 fatos relevantes** em 2026; última entrega 2026-10-03 | Eventos e catalisadores primários (fato relevante, comunicado, cronograma) com `Link_Download` |

- **Point-in-time** [V]: o índice do ITR traz `DT_RECEB` (ex.: Petrobras 1T26 recebido em 2026-05-11, versões 1 e 2; 2T26 em 2026-08-06) e `VERSAO`. Assim dá para reconstituir "o que se sabia em t".
- Exemplo verificado: Petrobras 2T26 (`ESCALA_MOEDA=MIL`):

  | Conta | Período | Valor (R$ mil) |
  |---|---|---|
  | Receita 3.01 | Trimestre | 169.530.000 |
  | Receita 3.01 | Semestre | 293.216.000 |
  | Lucro 3.11 | Trimestre | 52.495.000 |

  Use `ORDEM_EXERC == "ÚLTIMO"` e diferencie trimestre (`DT_INI_EXERC`) de acumulado.
- Composição de capital: Petrobras 7.442.231.382 ON + 5.446.501.379 PN = 12.888.732.761 [V]. É a base correta para market cap por classe (o Yahoo mistura).
- Licença ODbL; ITR "Semanal" (última atualização 2026-09-28) [D].
- Cuidados [I]: encoding `latin-1`, separador `;`, valores em `ESCALA_MOEDA` (MIL/UNIDADE), contas não fixas variam por emissor (bancos e seguradoras têm plano próprio).

### 7.2 SEC EDGAR [V]

- **Sem `User-Agent` → 403.** Com UA `Nome contato@dominio`: `company_tickers_exchange.json` (523 KB, 0,51 s) mapeia ticker→CIK→bolsa. Exemplos:

  | Ticker | CIK | Emissor |
  |---|---|---|
  | PBR | 1119639 | — |
  | VALE | 917851 | — |
  | CIB | **2058897** | Grupo Cibest |
  | GGAL | 1114700 | — |
  | BAP | 1001290 | — |
  | NU | 1691493 | — |
  | MELI | 1099590 | — |
  | SQM | 909037 | — |
  | AMX | 1129137 | — |
  | EC | 1444406 | — |
  | ITUB | 1132597 | — |
- `submissions` (0,21 s): formulários e datas. PBR tem 890 6-K recentes e o 20-F mais recente em 2026-04-09 (exercício 2025); os 6-K mais recentes são de 2026-10-02.
- `companyfacts` (0,46–0,59 s, até 2,6 MB):

  | Emissor | Conceitos `ifrs-full` | Conceitos `us-gaap` | Observação |
  |---|---|---|---|
  | PBR | 397 | 266 | Tem fatos de 6-K/A (interinos) |
  | VALE | 380 | 337 | — |
  | BAP | 384 | — | Em PEN |
  | CIB | 0 | 0 | Só `dei`: CIK novo após reestruturação |
- Regras [D]: máximo de **10 req/s**, UA declarado, "download only what you need".
- [I] O pacote `edgartools` (5.60.0 no PyPI) encapsula isso, mas para o nosso escopo bastam 3 endpoints JSON. Evite dependência extra.
- [I] Para ADRs, fundamentos IFRS do 20-F são anuais e os 6-K são irregulares. Para emissores brasileiros com ADR, **prefira a CVM** (trimestral, PIT); use a SEC para MX/CL/CO/PE/AR, ou como checagem.

---

## 8. Notícias e eventos

### 8.1 Google News RSS [V]

```python
import feedparser, requests, urllib.parse as up

def google_news(query: str, hl: str = "pt-BR", gl: str = "BR", ceid: str = "BR:pt-419"):
    url = f"https://news.google.com/rss/search?q={up.quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    return [{"published": e.get("published"), "source": e.get("source", {}).get("title"),
             "title": e.title, "link": e.link} for e in feed.entries]

google_news("Petrobras PETR4 when:7d")                                   # 100 itens, 0,59 s
google_news('Walmex OR "Walmart de México" when:7d', "es-419", "MX", "MX:es-419")  # 17 itens
google_news("Credicorp OR BAP when:7d", "es-419", "PE", "PE:es-419")      # 53 itens
google_news("Grupo Galicia GGAL when:7d", "en-US", "US", "US:en")         # 4 itens
```

- Campos: `title`, `link`, `published`, `source`, `summary`. **Máximo de 100 itens por feed**. O `link` é um redirect `news.google.com/rss/articles/CBMi…`, não a URL do publisher.
- [I] Não há API oficial nem SLA. Faça dedupe por (título normalizado, fonte). O conteúdo é **não confiável** (prompt injection), conforme a invariante do repositório: passe ao LLM só como dado citado, nunca como instrução.

### 8.2 Fontes primárias de eventos (preferíveis para catalisadores) [V]

- **CVM IPE**: fatos relevantes e comunicados com data de entrega e link. Fonte primária para BR.
- **SEC `submissions`**: 6-K e 20-F com `filingDate`, para ADRs.
- `yfinance.Ticker("PBR").news` devolveu **0 itens** neste teste; não dependa dele.

---

## 9. Ferramentas quantitativas

### 9.1 Benchmark de otimização (problema L/S realista, dados sintéticos) [V]

Problema: N = 150 ativos, K = 12 fatores (coluna 0 = beta de mercado), alpha anual ~N(0, 2%), restrições:

- Σw = 0 (dollar neutral) e β·w = 0.
- |exposição| ≤ 2% em 3 fatores de estilo.
- ‖w‖₁ ≤ 2,0 (gross 200%), w ≤ 4% e w ≥ −2,5%.
- Liquidez: |w|·NAV ≤ 10% do ADV × 3 dias.
- Custo de transação de 15 bps × ‖Δw‖₁.

Vol ex-ante ≤ 5% como restrição SOCP (variância fatorial + específica via Cholesky).

| Formulação | Solver | Status | Tempo | Vol ex-ante | Gross |
|---|---|---|---|---|---|
| SOCP (max alpha − TC, s.a. vol ≤ 5%) | **CLARABEL** | optimal | **0,041 s** | **5,000%** | 1,683 |
| SOCP | SCS | optimal | 1,891 s | 4,9998% | 1,683 |
| SOCP | ECOS | — | — | — | "not installed" (não vem com cvxpy 1.9) |
| QP (mean-variance, λ = 5) | CLARABEL | optimal | 0,019 s | 5,92% | 2,000 |
| QP | SCS | optimal | 0,021 s | 5,92% | 2,000 |
| QP | HIGHS | optimal | 0,082 s | 5,92% | 2,000 |
| QP | OSQP | **user_limit** | 0,216 s | 5,93% | **2,009** (viola o teto) |
| MILP (cardinalidade ≤ 60, max alpha) | HIGHS | optimal | 0,02 s | — | 50 nomes |

Solvers instalados com cvxpy 1.9.3: `CLARABEL, SCS, SCIPY, HIGHS, OSQP` [V].

[I] Conclusões:

1. **A vol-alvo deve ser restrição SOCP explícita** (‖Lᵀw‖ ≤ σ*), não um λ de aversão: o QP com λ fixo errou o alvo (5,92%).
2. CLARABEL é o solver principal; SCS é fallback; HIGHS cobre LP/MILP (cardinalidade, lotes mínimos).
3. OSQP precisa de `max_iter`/`eps` ajustados e checagem pós-solve de restrições.
4. **Sempre verifique a solução no código** (vol, net, beta, gross, liquidez), independente do status do solver.

### 9.2 Bibliotecas de portfólio (testadas com retornos reais de 29 ADRs, 3 anos) [V]

| Biblioteca | Versão (PyPI) | Teste | Resultado | Papel recomendado [I] |
|---|---|---|---|---|
| skfolio | 1.4.11 (2026-10-03) | `MeanRisk(MAX_RATIO, VARIANCE, budget=0, ±10%)` | Rodou (0,1 s), net 0 | Pesquisa: validação cruzada temporal (CPCV/walk-forward), priors fatoriais, comparação de estimadores; API scikit-learn |
| skfolio | 1.4.11 | `MeanRisk(MIN_RISK, CVAR, budget=0)` | **w = 0** (gross 0) | Precisa de gross mínimo ou objetivo de alpha; não serve "pronto" para L/S neutro |
| riskfolio-lib | 7.4.0 (2026-10-04) | `Portfolio(sht=True, budget=0).optimization(MinRisk, MV)` | **w = 0** | Relatórios e medidas de risco (CVaR, CDaR, EVaR), risk parity; não é o núcleo |
| PyPortfolioOpt | 1.6.0 (2026-02-26) | `efficient_risk(0.05, market_neutral=True)` | **Erro** "minimum volatility is 0.154"; restrição custom com `abs` nativo falha | Evitar para L/S neutro com vol-alvo |
| scikit-learn | 1.9.1 | `LedoitWolf` | shrinkage 0,027 em 0,009 s | Shrinkage de covariância (complemento ao modelo fatorial) |
| statsmodels | 0.15.0 (2026-08-27) | OLS PBR vs ILF | β = 0,772 (t = 16,2) | Betas, regressões fatoriais (WLS por √cap), diagnósticos |
| arch | 8.0.0 (2025-10-21) | GARCH(1,1)-t em ILF | Vol anual prevista 20,4% (5 dias), 0,02 s | Previsão de vol de mercado e regime; escalar a vol-alvo dentro da banda 3–7% |
| cvxpy | 1.9.3 (2026-09-19) | — | Ver §9.1 | **Núcleo do otimizador** |

### 9.3 Calendários e armazenamento [V]

- `exchange_calendars 4.13.2`: códigos `BVMF`, `XMEX`, `XSGO`, `XBOG`, `XLIM`, `XBUE` e `XNYS` funcionaram. Feriados detectados em set–out/2026:

  | Data | Mercados fechados |
  |---|---|
  | 2026-09-07 | BVMF, XNYS |
  | 2026-09-16 | XMEX |
  | 2026-09-18 | XSGO |
  | 2026-10-08 | XLIM |
  | **2026-10-12** | BVMF, XSGO, XBOG, XBUE |

  `pandas_market_calendars 5.5.0` também expõe `BMF/B3/BVMF/XBOG/XBUE/XLIM/XMEX/XSGO`.
- `duckdb 1.5.6` consulta Parquet/DataFrames direto (testado no BTC). `pyarrow 25.0.1` grava Parquet. `pandera 0.33.1` faz validação de schema.

---

## 10. Ferramentas de LLM e agentes

| Ferramenta | Versão (PyPI, data) | O que entrega | Encaixe no projeto [I] |
|---|---|---|---|
| **Anthropic Python SDK** (`anthropic`) | 1.11.0 (2026-09-30) | Messages API; **structured outputs** (`client.messages.parse(..., output_format=PydanticModel)` → `response.parsed_output`; ou `output_config={"format": {"type": "json_schema", ...}}`); **strict tool use** (`"strict": True` + `additionalProperties: false`); citações em documentos; prompt caching (leitura ~0,1× do preço de input); Message Batches (50% do custo, assíncrono) [D: docs Anthropic via skill, cache 2026-09-25] | **Recomendado como núcleo.** Notas de research em JSON validado por Pydantic (já há `ResearchNote`, `SqueezeAssessment`, `View` em `cdp/contracts.py`); tools somente leitura `get_fact(fact_id)` e `search_news(ticker)` com `strict`; o LLM **cita** fatos do FactBook e nunca calcula |
| Modelos Claude (2026-09) | — | `claude-opus-5-5` US$ 4/20 por Mtok (in/out); `claude-sonnet-5-5` US$ 2/10; `claude-haiku-4-5` US$ 1/5 [D] | Opus 5.5 para a tese semanal do PM; Haiku/Sonnet para triagem em lote de notícias (Batches) |
| Comportamentos a respeitar | — | Opus 5.5: thinking adaptativo sempre ligado, controle por `output_config.effort` (default `medium`); `tool_choice` forçado (`any`/`tool`) devolve **400**; sem prefill; verificar `stop_reason == "refusal"` [D] | O código não pode depender de forçar tool; use `auto` + `strict`, ou structured outputs |
| **Claude Agent SDK** (`claude-agent-sdk`) | 0.2.163 (2026-09-30) | Harness do Claude Code como biblioteca: tools nativas (arquivos, bash, web), **hooks**, subagents, **MCP**, permissões, sessões [D] | Opcional: um "analista de pesquisa" interativo para o PM, com hooks que bloqueiam escrita fora de `data/research/`. Não é necessário para o pipeline semanal determinístico |
| **MCP** (SDK Python `mcp`) | 2.3.0 (2026-10-02) | Protocolo para expor tools e recursos a clientes LLM | [I] Expor um **MCP server próprio, somente leitura**, sobre o snapshot aprovado (`facts`, `prices`, `btc`, `short_interest`, `news`). Servidores MCP de terceiros para market data **não foram avaliados nesta sessão** (sem orçamento de busca); tratá-los como não confiáveis até auditoria |
| LangGraph | 1.2.12 (2026-09-21) | Grafos de estado, checkpoint, human-in-the-loop | [I] Não necessário: o workflow já é uma máquina de estados explícita (`ProposalState`), testável sem framework |
| Pydantic AI | 2.54.0 (2026-10-03) | Agentes tipados e multi-provedor | [I] Alternativa se precisarmos trocar de provedor (o repo já tem Gemini/OpenRouter). Pydantic puro + SDK nativo bastam |

**Padrão recomendado de chamada [I]** (só um esboço; a implementação real fica no módulo de research):

```python
# Esboço: nota de pesquisa estruturada, ancorada no FactBook (números só por fact_id)
from anthropic import Anthropic
from cdp.contracts import ResearchNote          # contrato Pydantic já existente

client = Anthropic()
resp = client.messages.parse(
    model="claude-opus-5-5",
    max_tokens=16000,
    output_config={"effort": "high"},
    system=[{"type": "text", "text": SYSTEM_RULES, "cache_control": {"type": "ephemeral"}}],
    messages=[{"role": "user", "content": factbook_and_news_payload}],   # notícias como dado citado
    output_format=ResearchNote,
)
if resp.stop_reason == "refusal":
    ...                                   # registrar e seguir sem a nota (nunca inventar)
note = resp.parsed_output                 # validado; números referenciados por fact_id
```

---

## 11. App de acompanhamento do gestor

- **Streamlit** (repo travado em 1.64.0; PyPI 1.65.0 em 2026-10-02) [V].
  - Padrão recomendado [D]: `st.Page` + `st.navigation`, com o entrypoint como roteador, em vez de `pages/`.
  - Navegar por URL cria nova sessão e zera `st.session_state`; para preservar estado, use `st.switch_page`/`st.page_link` [D].
- **Plotly 7.1.0** (já no lock) para exposições, fatores, risco e P&L.
- [I] Cache: `st.cache_data` com chave `snapshot_id` (hash), nunca por tempo. A aprovação do gestor fica vinculada a `snapshot_hash + factbook_hash + research_hash + config_hash` (invariante 3 do AGENTS.md).

---

## 12. Stack recomendada (resumo)

| Camada | Escolha | Alternativa/fallback | Motivo [I] |
|---|---|---|---|
| Preços/OHLCV/eventos (todas as bolsas + ADRs + FX) | yfinance 1.7 + chart API v8 | Arquivo oficial B3 (último pregão), Stooq ou fornecedor pago | Cobertura total, testada; guardas da §3.9 |
| Liquidez oficial B3 | `TradeInformationConsolidatedFile` (diário) | Yahoo | Auditável, bate com Yahoo |
| Aluguel/BTC | BDI `BTBLendingOpenPosition` + `BTBLoanBalance` (+ `BTBTrade`) | Fallback `gc_borrow_fee_br` | Única fonte gratuita; **job diário** por causa da janela D-21 |
| Free float BR | Carteira teórica IBXX/SMLL (B3) + composição de capital (CVM) | `floatShares` Yahoo (não confiável) | Denominador de BTC/FF |
| Short interest ADR | FINRA `consolidatedShortInterest` | Yahoo `info` (mesmo dado), Nasdaq API | Primária, 5 anos de histórico |
| Macro/FX oficial | BCB SGS/PTAX, FRED, BCRP, TRM, BCRA, Banxico (token) | Yahoo `=X` | Fixings auditáveis |
| Fundamentos | CVM ITR/DFP (BR, PIT) + SEC companyfacts (demais) | Yahoo `info` só como metadado | PIT e moeda corretos |
| Eventos/notícias | CVM IPE + SEC submissions + Google News RSS | — | Primário antes de agregador |
| Calendário | `exchange_calendars` | `pandas_market_calendars` | Feriados por bolsa |
| Armazenamento | Raw imutável + Parquet (pyarrow, zstd) + DuckDB; pandera | Polars (opcional) | Reprodutibilidade e hashes |
| Otimização | cvxpy + CLARABEL (SCS fallback; HIGHS para MILP) | — | Rápido, exato na vol-alvo |
| Estatística/risco | numpy/pandas, statsmodels, arch, scikit-learn | skfolio/riskfolio para pesquisa | Testável e determinístico |
| LLM | Anthropic SDK (structured outputs + strict tools + caching + Batches); `DemoProvider` offline | Gemini/OpenRouter (já no repo) via abstração | Contratos Pydantic; o LLM nunca calcula |
| Agente interativo (opcional) | Claude Agent SDK + MCP server próprio somente leitura | — | Pesquisa ad hoc do PM com hooks/permissões |
| App | Streamlit multipage (`st.navigation`) + Plotly | — | Já usado no repo |

---

## 13. Desenho de ingestão: cache, snapshots, proveniência e hashes [I]

### 13.1 Camadas

1. **raw/**: bytes exatamente como recebidos (CSV/JSON/ZIP/PDF/RSS), **imutáveis**, nomeados pelo SHA-256 do conteúdo, com um `.meta.json` de proveniência ao lado. Nunca sobrescrever (invariante 5).
2. **norm/**: Parquet tipado por dataset e `as_of`, gerado por um parser **versionado** (`parser_version`) a partir do raw. Reprocessável a qualquer momento.
3. **features/**: retornos em USD, ADV, BTC/FF, SI em ações-equivalentes, fatores, sempre calculados por código testado.
4. **snapshots/{as_of}/manifest.json**: lista fechada de arquivos norm/features com hash. `snapshot_id = sha256(manifest canônico)`. É isso que o FactBook, a proposta e a aprovação referenciam (já modelado em `SnapshotManifest`, `SnapshotFile` e `SourceRecord` de `cdp/contracts.py`).

### 13.2 Layout de diretórios proposto

```
data/lake/
  raw/{source}/{dataset}/asof=YYYY-MM-DD/{fetched_utc}__{sha256[:16]}.{ext}
  raw/{source}/{dataset}/asof=YYYY-MM-DD/{fetched_utc}__{sha256[:16]}.meta.json
  norm/{dataset}/asof=YYYY-MM-DD/part-0.parquet
  features/{feature_set}/asof=YYYY-MM-DD/part-0.parquet
  snapshots/YYYY-MM-DD/manifest.json          # versionado em git
  security_master/securities.parquet           # ticker history, razão ADR, moeda, bolsa, CNPJ/CIK
```

[I] Adicionar `data/lake/raw/`, `data/lake/norm/` e `data/lake/features/` ao `.gitignore` (volume). Versionar `snapshots/*/manifest.json` e o `security_master` (pequenos, auditáveis). **Não alterei o `.gitignore`**; isto é só recomendação.

### 13.3 Registro de proveniência (`.meta.json`)

| Campo | Exemplo | Observação |
|---|---|---|
| `source_id` | `b3_bdi` | Igual a `SourceRecord.source_id` |
| `dataset` | `BTBLoanBalance` | — |
| `url`, `method`, `params` | `POST .../BTBLoanBalance/2026-10-02/2026-10-02/{p}/1000` | Sem segredos (tokens mascarados) |
| `http_status`, `response_headers` | `200`, `record-total` | Guardar headers úteis (FINRA `record-total`, BDI `lastUpdateDate`) |
| `fetched_at_utc` | `2026-10-05T09:12:03Z` | Timezone obrigatório (o contrato já exige) |
| `as_of` | `2026-10-02` | Data do dado (pregão/liquidação) |
| `knowledge_time` | `2026-10-03T06:12:57-03:00` | **Quando o dado ficou público**: BDI `lastUpdateDate`, CVM `DT_RECEB`, FINRA liquidação + 7 d.u., SEC `filingDate` |
| `content_sha256`, `bytes`, `rows` | — | Hash dos bytes brutos |
| `parser_version` | `bdi_btc@1.0.0` | Para reprocessamento |
| `point_in_time` | `true`/`false` | `false` para retratos atuais (Yahoo `info`, carteira do índice) |
| `license_note` | "Yahoo: uso pessoal; pesquisa" | Compliance |
| `is_synthetic` | `false` | Demo → `true` + "DADOS SIMULADOS" (invariante 6) |

### 13.4 Point-in-time e look-ahead

- O backtest e o FactBook só usam linhas com `knowledge_time ≤ momento da decisão` (segunda, antes da abertura).
- FINRA: na segunda 2026-10-05 o último SI é o de 2026-09-15 (publicado ~2026-09-24). O de 2026-09-30 só entra a partir de ~2026-10-09.
- CVM: filtrar por `DT_RECEB` e escolher a maior `VERSAO` recebida até a data.
- Yahoo `Adj Close`: recalcular retornos totais a partir de `Close` + dividendos/splits do raw da época. Não confiar no ajuste retroativo do snapshot mais novo.

### 13.5 Cache e TTL

| Dataset | Política |
|---|---|
| EOD (preços, B3 consolidado, BDI) | Imutável após publicação final. Cache = o próprio raw, chaveado por (source, dataset, as_of). Refetch só se `knowledge_time` mudar (republicação; BDI mostrou "Republicado" em capítulos de RV) |
| Intraday (opcional) | TTL de 15 min |
| `Ticker.info`, carteira teórica | TTL de 24 h, sempre `point_in_time=false` |
| FINRA | 1 fetch por data de liquidação |
| CVM ITR/DFP | Semanal |
| CVM IPE e SEC submissions | Diário |
| Notícias | TTL de 1 h na semana; congeladas no snapshot de segunda |

### 13.6 Concorrência, rate limiting e retries

- Token bucket por host:

  | Host | Limite |
  |---|---|
  | Yahoo | ≤ 8 conexões simultâneas |
  | SEC | ≤ 8 req/s (margem sob 10) |
  | FINRA | ≤ 10 req/s (bem abaixo de 1.200/min) |
  | Banxico | ≤ 60/min |
  | B3 | ≤ 4 simultâneas |
  | CVM | 1 simultânea (servidor lento) |

- Retry com backoff exponencial e jitter (1, 2, 4, 8 s; máximo de 4 tentativas) só em 429, 5xx e timeouts. 404 nunca é retry: vira "ticker ausente" (`SnapshotManifest.missing_tickers`).
- Timeouts: 20–30 s; 120 s para ZIPs da CVM.

### 13.7 Regras de qualidade (pandera + checagens de domínio)

| Regra | Ação |
|---|---|
| `volume == 0` com preço válido em dia de pregão | NaN + flag (§3.9) |
| Preço inalterado por ≥ 5 pregões com bolsa aberta | Flag "stale"; excluir do book |
| \|retorno diário\| > 35% sem evento corporativo | Quarentena para revisão |
| `Adj/Close` com salto ≠ evento | Flag |
| Paridade ADR↔local fora da tolerância | Flag; checar razão e moeda |
| Moeda da linha ≠ security master | Erro (BAP.LM) |
| BTC: taxa com `QtyCtrctsDay == 0` | Marcar "taxa defasada" |
| Ausências | Sempre NaN explícito; nunca 0 nem ffill silencioso (invariante 5). Forward-fill só no código de features, com limite (ex.: ≤ 2 pregões) e registro |

### 13.8 Calendário operacional semanal (horário de Brasília)

| Quando | Job |
|---|---|
| Diário, 07:30 (D+1) | BDI BTC (OpenPosition, LoanBalance; BTBTrade opcional): **crítico, a janela é D-21**. Alerta se um pregão faltar |
| Diário, 21:00 | Arquivo B3 `TradeInformationConsolidatedFile` (publicado ~19:30–20:00), Yahoo EOD de todas as linhas e FX, CVM IPE, SEC submissions |
| Quinzenal | FINRA, no 7º dia útil após 15/fim do mês |
| Semanal (domingo) | CVM ITR/DFP/FCA, carteira teórica B3, `info` |
| **Segunda, 06:00–07:30** | Snapshot de decisão: congela o raw até sexta (ou último pregão), gera o manifesto, roda o FactBook e o research (LLM), e propõe a carteira para aprovação antes da abertura (B3 10:00, NYSE 10:30 BRT) |
| Segunda feriado (**2026-10-12**: B3/Santiago/BVC/BYMA fechados; NYSE/BMV/BVL abertos) | Política explícita no config. Sugestão: decidir na segunda, executar ADRs/EUA/MX/PE no dia e linhas locais fechadas no próximo pregão, com checagem de neutralidade intradiária; ou antecipar para sexta |

### 13.9 Snippet: gravação no raw com hash

```python
# Esboço do adaptador de raw (arquivo nunca sobrescrito; hash = identidade)
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def store_raw(root: Path, source: str, dataset: str, as_of: str, content: bytes, ext: str,
              meta: dict) -> Path:
    sha = hashlib.sha256(content).hexdigest()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = root / "raw" / source / dataset / f"asof={as_of}"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{ts}__{sha[:16]}.{ext}"
    if not any(p.name.endswith(f"__{sha[:16]}.{ext}") for p in d.iterdir()):   # dedupe por conteúdo
        path.write_bytes(content)
        (path.with_suffix(".meta.json")).write_text(json.dumps(
            {**meta, "source_id": source, "dataset": dataset, "as_of": as_of,
             "fetched_at_utc": ts, "content_sha256": sha, "bytes": len(content)},
            sort_keys=True, ensure_ascii=False, indent=2))
    return path
```

---

## 14. Tabela de parâmetros

| Parâmetro | Valor | Racional |
|---|---|---|
| `yahoo.user_agent` | Obrigatório (string fixa do projeto) | Sem UA → 429 imediato [V] |
| `yahoo.max_workers` | 8 | 80 req em 1,2 s sem 429 [V]; margem [I] |
| `yahoo.retries` | 3, backoff 1/2/4 s | Padrão `yf.config.network.retries` [D] |
| `yahoo.history_risk` | 3 anos diários (~750 pregões) | Suficiente para covariância fatorial e GARCH [I]; 2,85 s/25 tickers [V] |
| `yahoo.history_backtest` | 5–10 anos (`range=max` disponível) | PETR4 desde 2000 [V] |
| `volume_zero_policy` | `NaN + flag` | Santiago com volume 0 em 2026 [V]; invariante 5 |
| `adv_window_days` | 63 (config) + checagem com 20 | Mediana robusta; ADV20 para squeeze [I] |
| `b3.bdi.take` | 1000 | > 1000 → 400 [V] |
| `b3.bdi.window_sessions` | 21 (D-21) | 2026-09-03 era o mais antigo [V] |
| `b3.bdi.fetch_time` | 07:30 BRT em D+1 | SLA 08:00; observado 04:52–06:12 [V] |
| `b3.btc.rate_units` | Fração a.a. | 0,0516 = 5,16% a.a. [V] |
| `b3.btc.min_contracts_for_fresh_rate` | 1 | Sem negócio no dia, a taxa é a última calculada [V] |
| `squeeze.br.borrow_fee_medium/high` | 5% / 15% a.a. | 15/112 nomes líquidos > 5%; topo de 25–36% [V]; calibração [I] |
| `squeeze.br.btc_pct_ff_medium/high` | 15% / 25% | Mediana IBrX 7,2%, p90 16,3% [V]; calibração [I] |
| `squeeze.br.btc_dtc_medium/high` | 10 / 20 dias | Mediana 6,1 dias (inclui arbitragem) [V]; calibração [I] |
| `squeeze.adr.dtc_medium/high` | 3 (considerar 5) / 7 | 21/48 ADRs com DTC > 3; 4 com > 7 [V] |
| `squeeze.adr.si_pct_float_medium/high` | 5% / 15% (em ações-equivalentes) | Config atual; base corrigida [I] |
| `finra.limit` | 5000 | `record-max-limit` [V] |
| `finra.publication_lag` | 7 dias úteis após liquidação | [D] |
| `sec.rate_limit` | ≤ 8 req/s | Teto oficial de 10 [D] |
| `sec.user_agent` | `"<Fundo> <email>"` | Sem UA → 403 [V] |
| `bcb.sgs.max_window_daily` | 10 anos por request | Erro explícito [V] |
| `bcb.sgs.432.filter_future` | `data ≤ as_of` | Datas futuras devolvidas [V] |
| `banxico.rate_limit` | ≤ 60/min (oportuno), ≤ 40/min (histórico) | Limites 80/min e 200/5 min [D] |
| `fred.ids_per_request` | 1 (CSV) | Vários → ZIP [V] |
| `cvm.timeout_s` | 120 | Cadastro levou 23 s [V] |
| `news.window` | `when:7d`; ≤ 100 itens por consulta | Limite do feed [V] |
| `adr_ratio.tolerance` | 3% (5% para ARS com CCL) | SQM 3,3% de gap por horário/CLP [V] |
| `fx.nav_snapshot` | Um horário fixo por dia + fixings oficiais | Yahoo FX em fuso de Londres [V] |
| `parquet.compression` | zstd | [I] |
| `hash.algorithm` | SHA-256 sobre bytes brutos; manifesto canônico (chaves ordenadas, floats com 10 casas) | Alinhado a `cdp/hashing.py` |
| `optimizer.solver_primary/fallback` | CLARABEL / SCS; HIGHS para MILP | Benchmark §9.1 [V] |
| `optimizer.vol_constraint` | SOCP explícita (σ* = 5%, banda 3–7%) | QP com λ fixo errou o alvo (5,92%) [V] |
| `optimizer.post_solve_checks` | Net, beta, gross, vol, liquidez recalculados | OSQP violou o gross [V] |
| `llm.model_pm` | `claude-opus-5-5`, effort `high` | Default é `medium` [D] |
| `llm.tool_choice` | `auto` + `strict: true` | Forçado → 400 no Opus 5.5 [D] |
| `llm.batch_triage` | Message Batches (50%) | Triagem semanal de notícias [D] |

---

## 15. Riscos, compliance e lacunas

1. **Licenciamento** [D/I]: Yahoo é "personal use only" e o Google News RSS não tem API oficial. Para um fundo real de USD 100 mm, o protótipo pode usar fontes gratuitas, mas **produção exige feed licenciado** (preços, eventos e aluguel com SLA) e o mesmo pipeline de proveniência.
2. **Fragilidade de endpoints não documentados** [V/I]: chart v8 do Yahoo, BDI da B3 (a API é a do SPA, sem contrato público) e FINRA anônima podem mudar sem aviso. Mitigação: testes de contrato offline com fixtures gravadas (raw real versionado como fixture pequena), monitor de schema (pandera) e degradação controlada (dado ausente → nome fora do book, nunca valor inventado).
3. **Sem histórico gratuito de BTC além de 21 pregões** [V]: o modelo de squeeze BR começa "frio". Precisa de 3–6 meses de coleta diária para calibrar percentis próprios [I].
4. **Custo real de aluguel** [I]: as taxas B3 são referência; o prime broker cobra spread e pode não ter papel disponível (locate). O config deve manter um haircut e checagem manual de locate para shorts > X% do ADV.
5. **Chile e Peru** [V]: liquidez local ruim ou ausente no Yahoo. Sem fonte oficial testada (Bolsa de Santiago e BVL não foram probadas nesta sessão), dar preferência aos ADRs já testados na FINRA/Yahoo (SQM, BSAC, BCH, BAP, BVN, SCCO). Outros ADRs chilenos e peruanos devem ser confirmados no security master antes do uso [I].
6. **Argentina** [V/I]: FX oficial ≠ CCL e a série local de YPFD.BA é suspeita. Usar ADRs com paridade checada.
7. **Lacunas desta sessão**: o orçamento de busca web acabou durante o trabalho, por isso não foram avaliados servidores MCP de terceiros para market data, termos de uso da B3 para os endpoints BDI nem fontes oficiais de Santiago/BVL/BYMA. Marcados como pendências.

---

## 16. Fatos verificados vs. inferências (resumo)

- **Verificado por execução [V]**:
  - Todos os status, latências, campos, contagens e valores de mercado citados (preços, taxas BTC, SI FINRA, Selic/CDI/PTAX, TRM, BCRA, BCRP, FRED).
  - A janela D-21 do BDI, `take ≤ 1000`, 429 sem UA no Yahoo, 403 sem UA na SEC, ZIP do FRED, janela de 10 anos do SGS, datas futuras na série 432.
  - Volume 0 em Santiago, metadados de Lima, renomeações de tickers, reconciliação de volume Yahoo×B3, razões de ADR implícitas.
  - Benchmark de solvers e comportamento de skfolio/riskfolio/PyPortfolioOpt; feriados de 2026 por bolsa.
- **Documentação primária [D]**:
  - Regras da FINRA (2×/mês, 7º dia útil, 5 anos, limites da API, OAuth).
  - SEC 10 req/s + UA; limites Banxico; ITR CVM semanal/ODbL.
  - Termos do yfinance/Yahoo; Streamlit `st.navigation`; Claude Agent SDK; preços e comportamentos dos modelos Claude.
- **Inferência [I]**:
  - Migração do dataset de aluguel do UP2DATA para o BDI.
  - Interpretação do saldo BTC como limite superior do short.
  - Calibração dos limiares de squeeze por mercado; data esperada de publicação da FINRA (2026-10-09).
  - Arquitetura de ingestão, TTLs, limites de concorrência e a escolha da stack.

---

## 17. Fontes (com datas)

Todas acessadas em **2026-10-05** a partir deste ambiente, salvo indicação.

1. Yahoo Finance Chart API v8 (não documentada oficialmente). https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
2. Yahoo Finance quoteSummary v10 (exige crumb). https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}
3. yfinance, README e aviso legal. https://github.com/ranaroussi/yfinance (v1.7.0 publicada no PyPI em 2026-08-26)
4. yfinance docs, Config. https://ranaroussi.github.io/yfinance/advanced/config.html
5. yfinance docs, Caching. https://ranaroussi.github.io/yfinance/advanced/caching.html
6. B3 UP2DATA Web, configuração e canais. https://arquivos.b3.com.br/src/config.js ; https://arquivos.b3.com.br/api/channels?page=1&size=100&lang=pt
7. B3 UP2DATA, download por nome (token). https://arquivos.b3.com.br/api/download/requestname?fileName=TradeInformationConsolidatedFile&date=2026-10-02&recaptchaToken=
8. B3 tabelas API. https://arquivos.b3.com.br/tabelas/table/TradeInformationConsolidated/2026-10-02/1 (e `LendingOpenPosition`, vazio)
9. B3 Boletim Diário (BDI), classificações e tabelas. https://arquivos.b3.com.br/bdi/table/classifications ; https://arquivos.b3.com.br/bdi/table/BTBLendingOpenPosition/2026-10-02/2026-10-02/1/1000 (POST)
10. B3 BDI, PDF de Empréstimos de Ativos de 02/10/2026 (Nº 189). https://arquivos.b3.com.br/bdi/download/bdi/2026-10-02/BDI_04-2_20261002.pdf
11. B3, Glossário de dados públicos (inclui glossários de BTC do BDI). https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/dados-publicos-de-produtos-listados-e-de-balcao/glossario/
12. B3, carteira do dia dos índices (IBOV/IBXX/SMLL). https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/{base64}
13. FINRA, Equity Short Interest (cobertura, cronograma, 7º dia útil, 5 anos). https://www.finra.org/finra-data/browse-catalog/equity-short-interest
14. FINRA, Query API docs (OAuth, 1.200 req/min, 5.000 registros). https://developer.finra.org/docs
15. FINRA Query API, consolidatedShortInterest. https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest
16. FINRA Reg SHO Daily Short Sale Volume. https://cdn.finra.org/equity/regsho/daily/CNMSshvol20261002.txt
17. Nasdaq API, short interest. https://api.nasdaq.com/api/quote/STNE/short-interest?assetClass=stocks
18. Nasdaq Trader, Reg SHO threshold list. https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth20261002.txt
19. NYSE, Threshold securities. https://www.nyse.com/api/regulatory/threshold-securities/download?selectedDate=02-Oct-2026&market=NYSE
20. Banco Central do Brasil, SGS API. https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/3?formato=json
21. Banco Central do Brasil, PTAX (Olinda). https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/
22. Banxico SIE API, limites de consulta. https://www.banxico.org.mx/SieAPIRest/service/v1/doc/limiteConsultas
23. FRED, fredgraph.csv. https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO
24. BCRP, API de séries estatísticas. https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD-PD04722MD/json/2026-09-25/2026-10-02
25. datos.gov.co, TRM (Socrata). https://www.datos.gov.co/resource/32sa-8pi3.json
26. BCRA, API Estadísticas Cambiarias v1.0. https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones/USD
27. Banco Central de Chile, SIETE REST (exige cadastro). https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx
28. CVM Dados Abertos, ITR (atualização semanal; última em 2026-09-28; ODbL). https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr
29. CVM Dados Abertos, cadastro de companhias abertas. https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv
30. CVM Dados Abertos, FCA (valores mobiliários/tickers). https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_2026.zip
31. CVM Dados Abertos, IPE (fatos relevantes). https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_2026.zip
32. SEC, Accessing EDGAR Data (fair access, 10 req/s, UA; página revisada em 2024-06-26). https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
33. SEC, company_tickers_exchange.json. https://www.sec.gov/files/company_tickers_exchange.json
34. SEC, submissions e XBRL companyfacts. https://data.sec.gov/submissions/CIK0001119639.json ; https://data.sec.gov/api/xbrl/companyfacts/CIK0001119639.json
35. Google News RSS (search). https://news.google.com/rss/search?q=Petrobras%20PETR4%20when%3A7d&hl=pt-BR&gl=BR&ceid=BR:pt-419
36. PyPI JSON API (versões e datas de release de todos os pacotes citados). https://pypi.org/pypi/{pacote}/json
37. Streamlit, multipage apps (`st.navigation`/`st.Page`). https://docs.streamlit.io/develop/concepts/multipage-apps/overview
38. Anthropic, Claude Agent SDK overview. https://code.claude.com/docs/en/agent-sdk/overview
39. Anthropic, preços e modelos (via skill `claude-api`, cache de 2026-09-25). https://platform.claude.com/docs/en/about-claude/pricing.md ; https://platform.claude.com/docs/en/about-claude/models/overview.md
40. GitHub issue "Provider: B3 stock lending (BTC / aluguel)" (2026-09-25; registra que o brapi.dev não expõe aluguel). https://github.com/kapetim/data-science/issues/43
