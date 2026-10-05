# CDP — Cabra da Peste — Proposta da semana de 05/10/2026 (v1)

> Dados de mercado: snapshot `store-2026-10-02+0-2026-10-02`. Dados reais (Yahoo Finance, B3, FINRA, BCB); paper trading com execução hipotética.

| Campo | Valor |
|---|---|
| Estado | **EM REVISÃO** |
| Proposta | CDP-2026-10-05-cdp (versão 1) |
| Criada em / por | 05/10/2026 14:29 UTC — CDP — motor quantitativo |
| NAV de referência | USD 100,00 mm |
| Snapshot | store-2026-10-02+0-2026-10-02 — `eba7e32a8a6b` |
| Hash da configuração | `5b8bdd690f10` |
| Hash da pesquisa | `1d34b1ebda9a` |

## Resumo de risco

| Métrica | Valor | Referência |
|---|---|---|
| Vol ex-ante (a.a.) | 3,13% | alvo 5,00%; banda 3,00%–7,00% — dentro da banda |
| Vol fatorial (a.a.) | 1,08% | 11,94% da variância (alerta acima de 25,00%) |
| Vol específica (a.a.) | 2,94% | fonte pretendida do retorno (alpha puro) |
| Beta previsto | 0,019 | limite ±0,050 |
| Gross (% NAV) | 45,84% | faixa 50%–250% |
| Net (% NAV) | +1,00% | limite ±1,00% |
| Long / Short (% NAV) | 23,42% / -22,42% |  |
| Nº de posições long / short | 25 / 21 |  |
| VaR 1d 99% | 0,46% (USD 0,46 mm) | paramétrico/histórico (modelo de risco) |
| ES 1d 99% | 0,53% (USD 0,53 mm) |  |
| VaR 1 semana 99% | 1,03% (USD 1,03 mm) |  |
| N efetivo | 35,5 | diversificação (1/Σw² normalizado) |
| Máx. dias para liquidar | 0,7 d | long ≤ 3,0 d; short ≤ 2,0 d |
| % NAV liquidável em 1 dia | 100,00% | participação 20% do ADTV |

### Testes de estresse (P&L estimado)

| Cenário | % NAV | USD |
|---|---|---|
| Quebra: 5 maiores longs -30% | -2,80% | USD -2,80 mm |
| Squeeze: 5 maiores shorts +30% | -2,46% | USD -2,46 mm |
| Eleição Brasil out/2022 (2º turno) | -2,15% | USD -2,15 mm |
| Gap AR -56% | -0,65% | USD -0,65 mm |
| Taper/estresse jun/2022 | -0,41% | USD -0,41 mm |
| Mercado LatAm -20% | -0,37% | USD -0,37 mm |
| Gap CL -15% | -0,30% | USD -0,30 mm |
| Tarifas EUA abr/2025 (Liberation Day) | -0,29% | USD -0,29 mm |
| Commodities -15% | -0,22% | USD -0,22 mm |
| Gap BR -10% | -0,20% | USD -0,20 mm |
| Brasil -15% | -0,18% | USD -0,18 mm |
| Gap MX -13% | -0,06% | USD -0,06 mm |
| Momentum crash -3σ | +0,03% | USD +0,03 mm |
| Eleição México jun/2024 | +0,03% | USD +0,03 mm |
| Choque fiscal BRL dez/2024 | +0,11% | USD +0,11 mm |
| Gap PE -10% | +0,12% | USD +0,12 mm |
| Gap CO -11% | +0,17% | USD +0,17 mm |
| Gap BR +10% | +0,20% | USD +0,20 mm |
| México -15% | +0,43% | USD +0,43 mm |
| Gap AR +41% | +0,47% | USD +0,47 mm |
| COVID crash (fev-mar/2020) | n/d | n/d |
| Estallido social Chile (out-nov/2019) | n/d | n/d |
| Joesley Day (mai/2017) | n/d | n/d |
| PASO Argentina 2019 | n/d | n/d |
| Taper tantrum (mai-jun/2013) | n/d | n/d |

### Maiores contribuições fatoriais (fração da variância)

| Fator | Contribuição |
|---|---|
| sector:Energy | 2,13% |
| liquidity | 1,29% |
| country:BR | 1,10% |
| country:CO | 1,10% |
| country:PE | 1,00% |
| market | 0,99% |
| sector:Communication Services | 0,91% |
| resvol | 0,84% |
| sector:Health Care | 0,82% |
| country:AR | 0,68% |

### Maiores contribuições de risco por emissor (fração da variância)

| Emissor | Contribuição |
|---|---|
| BR_PETROBRAS | 7,77% |
| BR_PAGS | 7,69% |
| BR_SUZANO | 7,67% |
| BR_TENDA | 7,66% |
| BR_JBS | 7,62% |
| BR_EMBRAER | 7,18% |
| LA_LILA | 7,11% |
| MX_VISTA | 6,98% |
| MX_ENDEAVOUR | 5,99% |
| BR_USIMINAS | 4,09% |

## Compliance

58 verificações; 2 falha(s) (0 HARD, 1 SOFT).

| Status | Severidade | Verificação | Valor | Limite | Detalhes |
|---|---|---|---|---|---|
| FALHA | SOFT | Exposição bruta mínima (`GROSS_MIN`) | 0,4584 | 0,5000 | Gross 0.46x do NAV (mínimo recomendado 0.50x). Carteira subutiliza o orçamento de risco. |
| FALHA | INFO | Distância à meta de volatilidade (`VOL_TARGET`) | 0,0313 | 0,0500 | Vol ex-ante 3.13% vs. meta 5.00% (diferença -1.87 p.p.). |
| ok | HARD | Beta previsto da carteira (`BETA`) | 0,0193 | 0,0500 | Beta previsto +0.019 (limite ±0.050). |
| ok | HARD | Taxa de aluguel dos shorts (`BORROW_FEE`) | 0,0444 | 0,0500 | Taxas de aluguel dentro do limite de 5.00% a.a. |
| ok | HARD | Exposição líquida por país: AR (`COUNTRY_NET:AR`) | 0,0115 | 0,0200 | Net país AR: 1.15% do NAV (limite ±2.00%). |
| ok | HARD | Exposição líquida por país: BR (`COUNTRY_NET:BR`) | 0,0200 | 0,0200 | Net país BR: 2.00% do NAV (limite ±2.00%). |
| ok | HARD | Exposição líquida por país: CL (`COUNTRY_NET:CL`) | 0,0200 | 0,0200 | Net país CL: 2.00% do NAV (limite ±2.00%). |
| ok | HARD | Exposição líquida por país: CO (`COUNTRY_NET:CO`) | -0,0156 | 0,0200 | Net país CO: -1.56% do NAV (limite ±2.00%). |
| ok | HARD | Exposição líquida por país: LATAM (`COUNTRY_NET:LATAM`) | -0,0074 | 0,0200 | Net país LATAM: -0.74% do NAV (limite ±2.00%). |
| ok | HARD | Exposição líquida por país: MX (`COUNTRY_NET:MX`) | 0,0043 | 0,0200 | Net país MX: 0.43% do NAV (limite ±2.00%). |
| ok | HARD | Exposição líquida por país: PA (`COUNTRY_NET:PA`) | 0,0000 | 0,0200 | Net país PA: 0.00% do NAV (limite ±2.00%). |
| ok | HARD | Exposição líquida por país: PE (`COUNTRY_NET:PE`) | -0,0125 | 0,0200 | Net país PE: -1.25% do NAV (limite ±2.00%). |
| ok | HARD | Exposição líquida por país: UY (`COUNTRY_NET:UY`) | -0,0104 | 0,0200 | Net país UY: -1.04% do NAV (limite ±2.00%). |
| ok | HARD | Defasagem do snapshot de dados (`DATA_STALENESS`) | 0,0000 | 4,0000 | Snapshot de 2026-10-05 para a semana de 2026-10-05: 0 dias corridos (máximo 4). |
| ok | HARD | Stop de drawdown (corte de gross) (`DRAWDOWN_HARD`) | 0,0000 | -0,0500 | Drawdown -0.00% (stop -5.00%, stop-out -7.50%). |
| ok | HARD | Exposição bruta máxima (`GROSS_MAX`) | 0,4584 | 2,5000 | Gross 0.46x do NAV (máximo 2.50x). |
| ok | HARD | Dias para liquidar (ponta comprada) (`LIQ_DAYS_LONG`) | 0,5461 | 3,0000 | Máximo 0.55 dias a 20% do ADTV (limite 3.0). |
| ok | HARD | Dias para liquidar (ponta vendida) (`LIQ_DAYS_SHORT`) | 1,1819 | 2,0000 | Máximo 1.18 dias a 15% do ADTV (limite 2.0). |
| ok | HARD | Long somente em nomes elegíveis e sem veto (`LONG_NOT_ALLOWED`) | 0,0000 | 0,0000 | Todos os longs são permitidos. |
| ok | HARD | Peso máximo por nome (long) (`NAME_LONG_MAX`) | 0,0200 | 0,0400 | Nenhum long acima do teto por nome. |
| ok | HARD | Peso máximo por nome (short) (`NAME_SHORT_MAX`) | 0,0224 | 0,0250 | Nenhum short acima do teto por nome. |
| ok | HARD | Exposição líquida (net neutral) (`NET_EXPOSURE`) | 0,0100 | 0,0100 | Net 1.00% do NAV (limite ±1.00%); long 23.42%, short -22.42%. |
| ok | HARD | Cobertura do modelo de risco (`RISK_MODEL_COVERAGE`) | 0,0000 | 0,0000 | Todos os nomes com peso têm risco modelado. |
| ok | HARD | Exposição líquida por setor: Communication Services (`SECTOR_NET:Communication Services`) | -0,0199 | 0,0250 | Net setor Communication Services: -1.99% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Consumer Discretionary (`SECTOR_NET:Consumer Discretionary`) | 0,0187 | 0,0250 | Net setor Consumer Discretionary: 1.87% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Consumer Staples (`SECTOR_NET:Consumer Staples`) | 0,0080 | 0,0250 | Net setor Consumer Staples: 0.80% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Energy (`SECTOR_NET:Energy`) | 0,0250 | 0,0250 | Net setor Energy: 2.50% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Financials (`SECTOR_NET:Financials`) | -0,0032 | 0,0250 | Net setor Financials: -0.32% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Health Care (`SECTOR_NET:Health Care`) | -0,0178 | 0,0250 | Net setor Health Care: -1.78% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Industrials (`SECTOR_NET:Industrials`) | 0,0039 | 0,0250 | Net setor Industrials: 0.39% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Information Technology (`SECTOR_NET:Information Technology`) | 0,0000 | 0,0250 | Net setor Information Technology: 0.00% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Materials (`SECTOR_NET:Materials`) | -0,0031 | 0,0250 | Net setor Materials: -0.31% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Real Estate (`SECTOR_NET:Real Estate`) | -0,0110 | 0,0250 | Net setor Real Estate: -1.10% do NAV (limite ±2.50%). |
| ok | HARD | Exposição líquida por setor: Utilities (`SECTOR_NET:Utilities`) | 0,0094 | 0,0250 | Net setor Utilities: 0.94% do NAV (limite ±2.50%). |
| ok | HARD | Short somente em linhas alugáveis e sem veto (`SHORT_NOT_ALLOWED`) | 0,0000 | 0,0000 | Todos os shorts são alugáveis e sem veto. |
| ok | HARD | Sem short em risco de squeeze ALTO (`SQUEEZE_HIGH`) | 0,0000 | 0,0000 | Nenhum short em nome com risco de squeeze alto. |
| ok | HARD | Teto reduzido para short com squeeze MÉDIO/sem dado (`SQUEEZE_MEDIUM_CAP`) | 0,0104 | 0,0125 | Shorts MEDIUM/NA dentro do teto de 1.25%. |
| ok | HARD | Exposição líquida ao tema state_owned (`THEME_NET:state_owned`) | 0,0100 | 0,0100 | Líquido 1.00% no tema 'state_owned' (limite ±1.00%). |
| ok | HARD | Volatilidade ex-ante máxima (`VOL_MAX`) | 0,0313 | 0,0700 | Vol ex-ante 3.13% a.a. (teto da banda 7.00%). |
| ok | HARD | Pesos numéricos válidos (`WEIGHTS_VALID`) | 0,0000 | 0,0000 | Todos os pesos são finitos. |
| ok | SOFT | Sensibilidade líquida a commodity:copper (`COMMODITY:copper`) | 0,0043 | 0,0300 | Σ w·β = +0.0043 (limite ±0.03); 10% na commodity ⇒ +0.04% do NAV. |
| ok | SOFT | Sensibilidade líquida a commodity:gold (`COMMODITY:gold`) | 0,0300 | 0,0300 | Σ w·β = +0.0300 (limite ±0.03); 10% na commodity ⇒ +0.30% do NAV. |
| ok | SOFT | Sensibilidade líquida a commodity:oil (`COMMODITY:oil`) | 0,0173 | 0,0300 | Σ w·β = +0.0173 (limite ±0.03); 10% na commodity ⇒ +0.17% do NAV. |
| ok | SOFT | Pior gap de país (cenários de evento) (`COUNTRY_GAP_STRESS`) | -0,0065 | -0,0150 | Pior cenário: Gap AR -56% com -0.65% do NAV (limite −1.50%). |
| ok | SOFT | Stop de drawdown (revisão) (`DRAWDOWN_SOFT`) | 0,0000 | -0,0250 | Drawdown -0.00% (gatilho de revisão -2.50%). |
| ok | SOFT | Exposição ao choque de evento (Eleição Brasil 2026 (2º turno 25/out)) (`EVENT:evento:BR:2026-10-05`) | 0,0015 | 0,0015 | Reação residual de 2026-10-05 replicada na carteira: +0.150% do NAV (limite ±0.15%). |
| ok | SOFT | Fração do risco vinda de fatores (`FACTOR_RISK_SHARE`) | 0,1194 | 0,2500 | Risco fatorial = 11.94% da variância (limite 25.00%); o restante é específico (alpha puro). |
| ok | SOFT | Contribuição máxima de um nome para o risco (`SINGLE_NAME_RISK`) | 0,0777 | 0,0800 | Maior contribuição: BR_PETROBRAS com 7.77% da variância (limite 8.00%). |
| ok | SOFT | Exposição ao estilo beta (`STYLE:beta`) | 0,0165 | 0,1000 | Exposição líquida +0.016 desvios-padrão × NAV (limite ±0.10). |
| ok | SOFT | Exposição ao estilo fx_sens (`STYLE:fx_sens`) | -0,0190 | 0,1000 | Exposição líquida -0.019 desvios-padrão × NAV (limite ±0.10). |
| ok | SOFT | Exposição ao estilo liquidity (`STYLE:liquidity`) | 0,1000 | 0,1000 | Exposição líquida +0.100 desvios-padrão × NAV (limite ±0.10). |
| ok | SOFT | Exposição ao estilo momentum (`STYLE:momentum`) | -0,0188 | 0,1000 | Exposição líquida -0.019 desvios-padrão × NAV (limite ±0.10). |
| ok | SOFT | Exposição ao estilo resvol (`STYLE:resvol`) | 0,0520 | 0,1000 | Exposição líquida +0.052 desvios-padrão × NAV (limite ±0.10). |
| ok | SOFT | Exposição ao estilo size (`STYLE:size`) | -0,0500 | 0,1000 | Exposição líquida -0.050 desvios-padrão × NAV (limite ±0.10). |
| ok | SOFT | Exposição ao estilo value (`STYLE:value`) | -0,0001 | 0,1000 | Exposição líquida -0.000 desvios-padrão × NAV (limite ±0.10). |
| ok | SOFT | Giro semanal (`TURNOVER`) | 0,4584 | n/d | Inception: montagem inicial de 45.84% do NAV (sem limite de giro). |
| ok | SOFT | Volatilidade ex-ante mínima (`VOL_MIN`) | 0,0313 | 0,0300 | Vol ex-ante 3.13% a.a. (piso da banda 3.00%). |
| ok | INFO | Origem dos dados (`SYNTHETIC_DATA`) | 0,0000 | n/d | Dados reais de snapshot imutável (hash verificado). |

## Principais posições

### Top 10 compradas (long)

| # | Emissor | País | Setor | Peso | Nocional | Linha | % ADTV | Squeeze | Alpha z |
|---|---|---|---|---|---|---|---|---|---|
| 1 | LATAM Airlines Group (CL_LATAM) | CL | Industrials | +2,00% | USD 2,00 mm | LTM (ADR) | 5,0% | LOW (13) | +0,87 |
| 2 | Suzano (BR_SUZANO) | BR | Materials | +1,97% | USD 1,97 mm | SUZB3.SA (LOCAL) | 3,7% | LOW (15) | +0,06 |
| 3 | Petrobras (BR_PETROBRAS) | BR | Energy | +1,96% | USD 1,96 mm | PBR (ADR) | 0,5% | LOW (18) | +2,35 |
| 4 | Vista Energy (MX_VISTA) | AR | Energy | +1,82% | USD 1,82 mm | VIST (ADR) | 2,5% | LOW (10) | +1,81 |
| 5 | Endeavour Silver (MX_ENDEAVOUR) | MX | Materials | +1,57% | USD 1,57 mm | EXK (US_LISTED) | 2,1% | LOW (18) | +0,77 |
| 6 | JBS N.V. (BR_JBS) | BR | Consumer Staples | +1,56% | USD 1,56 mm | JBS (US_LISTED) | 2,3% | LOW (34) | -0,02 |
| 7 | PagSeguro Digital (BR_PAGS) | BR | Financials | +1,54% | USD 1,54 mm | PAGS (US_LISTED) | 5,7% | MEDIUM (41) | +0,57 |
| 8 | Caixa Seguridade (BR_CXSEG) | BR | Financials | +1,45% | USD 1,45 mm | CXSE3.SA (LOCAL) | 6,2% | LOW (30) | +0,96 |
| 9 | Tenda (BR_TENDA) | BR | Consumer Discretionary | +1,22% | USD 1,22 mm | TEND3.SA (LOCAL) | 6,1% | LOW (27) | +2,19 |
| 10 | ISA Energia Brasil (BR_ISAENERGIA) | BR | Utilities | +0,88% | USD 0,88 mm | ISAE4.SA (LOCAL) | 4,3% | LOW (39) | +0,98 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **LATAM Airlines Group (CL_LATAM)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > LATAM mostrou resiliência própria ao choque de combustível. Repassou custos às tarifas, reinstituiu e elevou o guidance anual no 2T26 e recebeu elevação de rating da S&P para um degrau abaixo do grau de investimento, com geração de caixa robusta e recompra em curso. A tese é de qualidade relativa frente às aéreas da região. Riscos: combustível alto por mais tempo, competição no doméstico brasileiro, overhang de vendas de acionistas e volatilidade do real em torno do segundo turno no Brasil.
- **Suzano (BR_SUZANO)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Visão idiossincrática moderadamente positiva: a Suzano lidera reajustes sucessivos da celulose com retomada das compras chinesas, gera caixa forte e anunciou plano de desalavancagem com corte de investimentos e dividendo mínimo; BTG, BofA e Bradesco BBI preferem o papel no setor. A ação acumulou longa sequência de quedas e está sobrevendida. Contra: rotação para fora de exportadoras com o real mais forte após o primeiro turno, nova oferta de celulose em 2027 e disputa tributária relevante.
- **Petrobras (BR_PETROBRAS)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Petrobras combina fundamentos fortes — produção e utilização de refino recordes no 2T26, lucro quase dobrado na comparação anual, geração de caixa robusta, dividendos relevantes e dívida abaixo do teto do plano — com nova descoberta na Foz do Amazonas e tese favorável de margens de refino em mercado de derivados apertado (JPMorgan). O primeiro turno favorece estatais e o ADR subiu forte no pós-mercado. Contrapesos: diesel e gasolina vendidos muito abaixo da paridade de importação com subvenções financiadas por imposto de exportação, valor de mercado recorde após forte alta no ano e volatilidade implícita elevada para o segundo turno. Visão idiossincrática levemente positiva, alinhada ao quant, com convicção moderada-baixa pelo evento binário.
- **JBS N.V. (BR_JBS)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Os sinais sobre a JBS se dividem. De um lado, o valuation está descontado, as recomendações de compra seguem predominando, a reabertura gradual ao gado mexicano e o fechamento de plantas ajudam a carne bovina nos EUA, e Brasil e Austrália vão bem. De outro, o 2T26 teve prejuízo, a carne bovina nos EUA segue com spreads negativos, a margem de frango (Pilgrim's) está em normalização, a alavancagem está acima da meta e o embargo europeu atinge carne bovina e suína brasileira. Pesam ainda a venda de toda a posição direta do CFO e a oferta em ações pela Pilgrim's, que pressionou o papel desde agosto. Com o 3T26 em meados de novembro, ainda sob pressão, a pesquisa não confirma o sinal comprado do quant: visão neutra e convicção baixa.
- **PagSeguro Digital (BR_PAGS)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > PagBank combina resultado resiliente no 2T26, com lucro ajustado e lucro por ação em alta, receita bancária acelerando, inadimplência abaixo da média do mercado e capital folgado, com retorno de capital agressivo: metas de dividendos para 2027 e 2028 e novo programa de recompra anunciados em 2026-09-01. Fraquezas: volume de pagamentos com crescimento modesto, receita total estável, provisões em alta, queda do caixa e gestão reconhecendo um ano mais difícil que o previsto; o fundador deixou a presidência do conselho, embora siga controlador. Visão idiossincrática levemente positiva, apoiada na recompra e na disciplina de capital, com o 3T26 como teste de crédito.
- **Tenda (BR_TENDA)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > A execução tem sido forte e previsível. O 2T26 superou o consenso em lucro, receita e EBITDA, e a companhia elevou todas as projeções de 2026 (vendas líquidas, EBITDA ajustado e lucro). A desalavancagem segue em curso, com intenção declarada de ampliar dividendos quando a dívida líquida zerar. O reajuste dos tetos de renda do MCMV favorece diretamente a base de clientes, e a entrada no Ibovespa amplia a base de investidores. A prévia operacional do 3T26 pode confirmar a retomada da velocidade de vendas. Os riscos são a forte valorização acumulada no ano com posicionamento já carregado, os prejuízos da Alea com projeção piorada e a dependência de um programa federal cujo desenho futuro passa pela eleição. Visão idiossincrática positiva, com convicção moderada.
- **ISA Energia Brasil (BR_ISAENERGIA)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Transmissora com receitas reguladas, protegidas da inflação e sem risco de volume ou de preço de energia. No 2T26, o Ebitda subiu com força com a entrada de novos ativos e entregas antecipadas. O grau de investimento permite captar abaixo do soberano. A oferta primária de julho, que financiou o descruzamento com a Axia, já foi absorvida, e há JCP com datas de corte em outubro e novembro. Do outro lado, o lucro líquido caiu por causa das despesas financeiras, a alavancagem é elevada, o BBI está neutro e a empresa abriu mão do próximo leilão de transmissão. Num rali eleitoral, transmissoras defensivas tendem a ficar atrás de utilities alavancadas, o que limita a convicção. A visão idiossincrática é levemente positiva.
- _Sem nota de pesquisa:_ MX_VISTA, MX_ENDEAVOUR, BR_CXSEG

### Top 10 vendidas (short)

| # | Emissor | País | Setor | Peso | Nocional | Linha | % ADTV | Squeeze | Alpha z |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Embraer (BR_EMBRAER) | BR | Industrials | -2,24% | USD -2,24 mm | EMBJ (ADR) | 2,6% | LOW (6) | -0,73 |
| 2 | Liberty Latin America (LA_LILA) | LATAM | Communication Services | -1,99% | USD -1,99 mm | LILAK (US_LISTED) | 17,7% | LOW (26) | -1,67 |
| 3 | Usiminas (BR_USIMINAS) | BR | Materials | -1,47% | USD -1,47 mm | USIM5.SA (LOCAL) | 9,7% | LOW (24) | -0,30 |
| 4 | Ultrapar (BR_ULTRAPAR) | BR | Energy | -1,25% | USD -1,25 mm | UGPA3.SA (LOCAL) | 1,7% | LOW (11) | -0,25 |
| 5 | Patria Investments (BR_PATRIA) | BR | Financials | -1,25% | USD -1,25 mm | PAX (US_LISTED) | 10,6% | LOW (28) | -2,22 |
| 6 | Southern Copper (PE_SCCO) | PE | Materials | -1,25% | USD -1,25 mm | SCCO (US_LISTED) | 0,6% | LOW (35) | -0,25 |
| 7 | Grupo Cibest (ex-Bancolombia) (CO_CIBEST) | CO | Financials | -1,25% | USD -1,25 mm | CIB (ADR) | 4,3% | LOW (5) | -0,05 |
| 8 | FEMSA (MX_FEMSA) | MX | Consumer Staples | -1,14% | USD -1,14 mm | FMX (ADR) | 2,1% | LOW (13) | +0,77 |
| 9 | Fleury (BR_FLEURY) | BR | Health Care | -1,14% | USD -1,14 mm | FLRY3.SA (LOCAL) | 7,7% | LOW (33) | +0,36 |
| 10 | Allos (BR_ALLOS) | BR | Real Estate | -1,10% | USD -1,10 mm | ALOS3.SA (LOCAL) | 4,5% | LOW (33) | -0,55 |

Teses de pesquisa (texto citado como fornecido; números vêm do código):

- **Embraer (BR_EMBRAER)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Os fundamentos seguem robustos. A carteira de pedidos é recorde, e no 2T26 a empresa elevou as projeções de margem e de geração de caixa. O curto prazo, porém, traz atritos idiossincráticos: as entregas do 3T26 ficaram abaixo do esperado pelos bancos, sobretudo na aviação executiva; a ação já não tem desconto relevante frente aos pares aeroespaciais; e a recomendação de compra do sell-side é quase unânime. Com o real tendendo a se fortalecer após o primeiro turno, a empresa perde atratividade relativa entre as ações brasileiras. Para as próximas semanas, a visão idiossincrática é neutra: as revisões positivas não sustentam uma aposta vendida, e a compra também não se justifica com boa parte da melhora já no preço.
  - Risco de short squeeze _(gerado por IA — provedor imported:claude-code, papel short_risk)_: **ok** —
    > A empresa não tem controlador definido e tem free float amplo. A ação está entre as mais negociadas da bolsa local e tem ADR líquido em Nova York, o que reduz o risco de squeeze e de falta de papel para aluguel. Não há catalisador corporativo conhecido na próxima semana, e o resultado do 3T26 ainda não tem data confirmada. Ressalva: o posicionamento comprado amplo e eventuais notícias de encomendas em defesa podem gerar repiques.
- **Ultrapar (BR_ULTRAPAR)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Ultrapar vive ciclo excepcional na distribuição de combustíveis (Ipiranga), com margens elevadas pela restrição global de derivados e pelo combate ao mercado irregular: 2T26 muito acima do consenso, geração de caixa recorde, alavancagem na mínima desde 2008, dividendos e recompra de ações. Itaú BBA e Safra elevaram alvos e esperam margens fortes no 3T26. Por outro lado, a ação está em máximas históricas e tecnicamente sobrecomprada, analistas projetam normalização de margens a partir de 2027 e preferem a Vibra, e há dúvida sobre alocação de capital após a participação na disputa pela fatia da Rumo. A pesquisa não endossa a venda sugerida pelo quant com convicção, pois os fundamentos de curto prazo seguem positivos; visão neutra.
  - Risco de short squeeze _(gerado por IA — provedor imported:claude-code, papel short_risk)_: **caution** —
    > Momento forte com máximas históricas, recompra de ações em andamento e revisões positivas de lucro; o 3T26 tende a vir forte. Liquidez local e em ADR reduz o risco extremo e não há catalisador datado identificado nos próximos pregões; condições de aluguel não verificadas nesta sessão.
- **Patria Investments (BR_PATRIA)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Os fundamentos recentes da Patria não sustentam um short idiossincrático: no 2T26 o FRE cresceu forte, a captação ficou no ritmo para superar a meta anual e o guidance de FRE de 2026 foi mantido. A ação, porém, caiu de forma contínua em setembro sem fato relevante identificado e não acompanhou o rali dos financeiros brasileiros antes do primeiro turno; um grande detentor institucional zerou a posição até o fim de agosto e houve troca no conselho. O lucro contábil segue bem abaixo do lucro distribuível. Com short interest relevante e estável e liquidez apenas moderada, o short fica arriscado em plena janela eleitoral. Visão neutra, com baixa convicção e discordância parcial do quant.
  - Risco de short squeeze _(gerado por IA — provedor imported:claude-code, papel short_risk)_: **caution** —
    > Short interest relevante e estável em relação à base de ações classe A, com dias para cobrir moderados segundo a FINRA e liquidez diária apenas moderada, próxima do mínimo exigido para shorts. A ação ficou para trás no rali pré-eleitoral e pode recuperar de forma abrupta num regime de risco Brasil favorável; o segundo turno ocorre em 2026-10-25. Não há catalisador corporativo conhecido nos próximos cinco pregões. Se mantido, o short deve ser pequeno.
- **Southern Copper (PE_SCCO)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Visão idiossincrática levemente negativa, em linha com o sinal vendido do quant. Os resultados do 2T26 foram recordes, mas vieram de preço: a produção de cobre caiu no trimestre e no semestre por teores menores nas minas peruanas, e zinco e molibdênio também recuaram. A ação negocia perto da máxima histórica e é vista como plenamente valorizada, enquanto o capex acelera. Tía María avança, mas carrega histórico recente de anulação de licença em abril de 2026 (revertida dias depois), diversas ações judiciais pedindo a anulação do projeto e divergência de cronograma entre a empresa (segundo semestre de 2027) e o ministério (início de 2028). A manchete de anulação datada de 2026-10-04 foi verificada e refere-se ao episódio de abril, não a fato novo. O controlador detém a vasta maioria do capital, o que reduz o free float e eleva o risco de squeeze, exigindo posição pequena.
  - Risco de short squeeze _(gerado por IA — provedor imported:claude-code, papel short_risk)_: **caution** —
    > Grupo México detém a vasta maioria do capital, deixando free float pequeno; dias para zerar as posições vendidas elevados em meados de setembro; ação perto da máxima histórica com cobre perto de recorde; resultado do 3T26 estimado para 2026-10-22, fora da janela imediata de pregões mas dentro do horizonte; aluguel normalmente disponível por ser papel listado nos Estados Unidos; sem exposição à eleição brasileira. Short apenas pequeno e monitorado.
- **Grupo Cibest (ex-Bancolombia) (CO_CIBEST)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Visão neutra para o Grupo Cibest frente aos pares financeiros andinos, divergindo da sugestão de short do quant. O 2T26 foi muito forte em lucro, margem financeira e rentabilidade, e o grupo devolve capital com o dividendo extraordinário já pago e a recompra em andamento. Mas parte da melhora veio de provisões menores por recuperações pontuais de grandes clientes, a carteira quase não cresceu no trimestre, e o próprio departamento econômico do grupo cortou a projeção de crescimento de 2027 por causa do ajuste fiscal. Sem catalisador corporativo próximo, a pesquisa não sustenta convicção direcional.
  - Risco de short squeeze _(gerado por IA — provedor imported:claude-code, papel short_risk)_: **caution** —
    > O short interest no ADR é baixo segundo a FINRA no FactBook e a linha é líquida, mas a recompra em execução cria demanda estrutural, o resultado do 2T26 sustenta revisões positivas e o controle concentrado reduz o free float das ordinárias. Não há evento corporativo nos próximos pregões, mas a apresentação da Ley de Rescate e o IPC de setembro podem mover as financeiras colombianas. Se houver short, que seja pequeno e via ADR.
- **FEMSA (MX_FEMSA)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > Visão neutra, divergindo em parte do sinal vendido do modelo. No 2T26 o OXXO México foi forte, com alta nas vendas mesmas lojas e a primeira melhora de tráfego após vários trimestres. Em contrapartida, houve contração de margem bruta por investimento em preço, colapso do lucro operacional em Américas e Mobilidade (OXXO Brasil e combustíveis), provisão relevante na divisão de Saúde e queda na Valora. O 3T26 perde o impulso da Copa do Mundo, e a administração reconhece consumo fraco no México. Por outro lado, a recompra acelerada de ADS, com liquidação até o fim de 2026, mantém um comprador constante no papel. O resultado do 3T26 sai em 2026-10-28.
  - Risco de short squeeze _(gerado por IA — provedor imported:claude-code, papel short_risk)_: **caution** —
    > ADR líquido, interesse vendido baixo em relação ao total e sem histórico de squeeze. Porém a recompra acelerada mantém um comprador relevante no ADS até o fim de 2026, e o resultado do 3T26, em 2026-10-28, cai dentro do horizonte, embora fora da janela imediata. O número de dias de volume para zerar o interesse vendido no ADR não é desprezível.
- **Fleury (BR_FLEURY)**
  - Tese _(gerado por IA — provedor imported:claude-code, papel fundamental)_:
    > O Fleury entregou um 2T26 acima do consenso, com crescimento orgânico forte, geração de caixa robusta e revisões de lucro para cima por várias casas. O caso vendido se apoia sobretudo em valuation esticado após a alta da ação, ponto já levantado por BTG e XP, que mantêm recomendação neutra com pouco potencial até o preço-alvo. No horizonte, a integração da Femme deve comprimir a margem do 3T26, com ITR em 2026-11-05, e parte do crescimento do 2T26 veio de surto de influenza, efeito não recorrente. Em contrapartida, revisões positivas, alavancagem baixa e opcionalidade estratégica ligada ao grupo Bradesco tornam um short arriscado. Visão idiossincrática neutra.
  - Risco de short squeeze _(gerado por IA — provedor imported:claude-code, papel short_risk)_: **caution** —
    > Bloco de controle formado pela Bradsaúde e por médicos fundadores reduz o free float efetivo; revisões de lucro para cima e opcionalidade de M&A, com fatos relevantes no passado envolvendo a Rede D'Or, aumentam o risco de alta abrupta. Não há catalisador da companhia nos próximos pregões, já que o ITR do 3T26 sai em 2026-11-05. Aluguel e posição vendida na B3 devem ser verificados pelo código.
- _Sem nota de pesquisa:_ LA_LILA, BR_USIMINAS, BR_ALLOS

## Exposições

### Por país (% NAV)

| Nome | Long | Short | Net | Gross | Limite |
|---|---|---|---|---|---|
| CL | 2,00% | 0,00% | +2,00% | 2,00% | ±2,00% |
| BR | 16,13% | -14,13% | +2,00% | 30,27% | ±2,00% |
| CO | 0,65% | -2,21% | -1,56% | 2,86% | ±2,00% |
| PE | 0,00% | -1,25% | -1,25% | 1,25% | ±2,00% |
| AR | 1,82% | -0,66% | +1,15% | 2,48% | ±2,00% |
| UY | 0,00% | -1,04% | -1,04% | 1,04% | ±2,00% |
| LATAM | 1,24% | -1,99% | -0,74% | 3,23% | ±2,00% |
| MX | 1,57% | -1,14% | +0,43% | 2,71% | ±2,00% |

### Por setor (% NAV)

| Nome | Long | Short | Net | Gross | Limite |
|---|---|---|---|---|---|
| Energy | 4,71% | -2,21% | +2,50% | 6,92% | ±2,50% |
| Communication Services | 0,00% | -1,99% | -1,99% | 1,99% | ±2,50% |
| Consumer Discretionary | 1,87% | 0,00% | +1,87% | 1,87% | ±2,50% |
| Health Care | 0,40% | -2,17% | -1,78% | 2,57% | ±2,50% |
| Real Estate | 0,00% | -1,10% | -1,10% | 1,10% | ±2,50% |
| Utilities | 1,66% | -0,72% | +0,94% | 2,38% | ±2,50% |
| Consumer Staples | 2,56% | -1,76% | +0,80% | 4,32% | ±2,50% |
| Industrials | 2,63% | -2,24% | +0,39% | 4,87% | ±2,50% |
| Financials | 4,09% | -4,41% | -0,32% | 8,50% | ±2,50% |
| Materials | 5,51% | -5,82% | -0,31% | 11,32% | ±2,50% |

### Fatores de estilo (σ × NAV)

| Nome | Long | Short | Net | Gross | Limite |
|---|---|---|---|---|---|
| liquidity | 0,000 | 0,000 | +0,100 | 0,100 | ±0,100 |
| resvol | 0,000 | 0,000 | +0,052 | 0,052 | ±0,100 |
| size | 0,000 | 0,000 | -0,050 | 0,050 | ±0,100 |
| fx_sens | 0,000 | 0,000 | -0,019 | 0,019 | ±0,100 |
| momentum | 0,000 | 0,000 | -0,019 | 0,019 | ±0,100 |
| beta | 0,000 | 0,000 | +0,016 | 0,016 | ±0,100 |
| value | 0,000 | 0,000 | 0,000 | 0,000 | ±0,100 |

## Hedges cambiais sugeridos

| Moeda | Exposição | Hedge | Instrumento | Racional |
|---|---|---|---|---|
| ARS | USD +1,15 mm | USD -1,15 mm | NDF 1M | Exposição econômica líquida em ARS: +1.15% do NAV (USD 1,153,872), somando linhas locais e ADRs. Acima do limiar de 1.0%: sugerido vender ARS a termo (USD 1,153,872). Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. ARS: NDF offshore com liquidez limitada; validar custo. |
| BRL | USD +2,00 mm | USD -2,00 mm | NDF 1M | Exposição econômica líquida em BRL: +2.00% do NAV (USD 1,999,999), somando linhas locais e ADRs. Acima do limiar de 1.0%: sugerido vender BRL a termo (USD 1,999,999). Liquidação local: compras USD 10,077,288, shorts USD 9,628,769; necessidade líquida de comprar BRL à vista ≈ USD 448,519. |
| CLP | USD +2,00 mm | USD -2,00 mm | NDF 1M | Exposição econômica líquida em CLP: +2.00% do NAV (USD 1,999,999), somando linhas locais e ADRs. Acima do limiar de 1.0%: sugerido vender CLP a termo (USD 1,999,999). Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| COP | USD -1,56 mm | USD +1,56 mm | NDF 1M | Exposição econômica líquida em COP: -1.56% do NAV (USD -1,555,290), somando linhas locais e ADRs. Acima do limiar de 1.0%: sugerido comprar COP a termo (USD 1,555,290). Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| MXN | USD +0,43 mm | USD 0,00 mm | sem hedge (abaixo do limiar) | Exposição econômica líquida em MXN: +0.43% do NAV (USD 432,297), somando linhas locais e ADRs. Dentro do limiar de 1.0%: sem hedge. Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |
| PEN | USD -1,25 mm | USD +1,25 mm | NDF 1M | Exposição econômica líquida em PEN: -1.25% do NAV (USD -1,249,999), somando linhas locais e ADRs. Acima do limiar de 1.0%: sugerido comprar PEN a termo (USD 1,249,999). Liquidação local: compras USD 0, shorts USD 0; sem necessidade líquida de caixa local. |

## Ordens

| Item | Valor |
|---|---|
| Nº de ordens | 46 (BUY 25, SHORT 21) |
| Volume bruto negociado | USD 45,84 mm (45,84% do NAV) |
| Turnover (Σ\|Δw\|) | 45,84% |
| Custo estimado | USD 182.583 (39,8 bps do volume; 0,183% do NAV) |
| Maior % do ADTV | 17,7% |
| Maior prazo estimado de execução | 0,9 d |

## Pesquisa e visões

Provedor: imported; 156 nota(s) por emissor (156 geradas por IA), 7 nota(s) macro, 82 visão(ões).

### Notas macro

#### AR — regime: Aversão a risco idiossincrática: risco-país em patamar elevado, bancos muito castigados e reservas líquidas frágeis, com apoio externo (Tesouro dos EUA, swaps) como cauda positiva relevante (viés -1)
_(gerado por IA — provedor imported:claude-code)_

> A Argentina entra na semana com o risco-país de volta a patamar elevado desde o fim de setembro, soberanos em queda e o S&P Merval em dólares de volta a níveis anteriores à eleição legislativa de 2025 (La Nación, Infobae, Ámbito). A piora é atribuída sobretudo ao choque global de juros e dólar (Treasury longo na máxima em cerca de duas décadas, Fed voltando a subir, petróleo alto) e à fraqueza doméstica: atividade em contração, renda real deprimida, compra de reservas lenta em setembro e incerteza sobre a eleição presidencial de 2027. Os bancos foram o setor mais punido no mês, com quedas perto do dobro do índice e preço próximo do valor patrimonial (Ámbito). Contrapesos recentes: o secretário do Tesouro dos EUA disse em 2026-10-04 que voltaria a apoiar financeiramente o país se necessário; o BCRA acelerou com força as compras de divisas na semana seguinte à missão do FMI; e o governo anunciou uma 'bazuca' de defesa cambial cuja capacidade efetiva é contestada por consultorias, com reservas líquidas negativas pela métrica do FMI (Infobae). Reação de hoje (2026-10-05): a expectativa local era de sessão positiva para bonds e ações por contágio do resultado no Brasil e pelo alinhamento político entre Milei e a direita brasileira; o indicador de risco-país aparecia levemente menor no retrato da manhã, sem fechamento confirmado no momento da análise (Infobae). Regime de aversão a risco com cauda positiva de apoio externo: configuração típica de squeeze em nomes muito vendidos.

Riscos:
- Squeeze em shorts de bancos argentinos (Galicia, Macro, BBVA Argentina, Supervielle): queda acumulada forte, preço perto do patrimônio e reação em saltos a anúncios de apoio externo ou de swaps (Ámbito, Infobae).
- Nova alta do risco-país se o Treasury longo e o dólar global continuarem subindo; os ativos argentinos estão entre os mais sensíveis da região ao juro americano (La Nación, Infobae).
- Rolagem da dívida em pesos concentrada no fim de outubro, com o Tesouro evitando emitir em dólar a custo elevado; uma troca mal recebida pressionaria juros locais e bancos (Ámbito).
- Credibilidade da 'bazuca' cambial: consultorias estimam poder de fogo efetivo bem menor que o anunciado, reservas líquidas negativas pela métrica do FMI e swaps dependentes de autorização política nos EUA e na China (Infobae).
- Aprovação ainda pendente da terceira revisão do acordo com o FMI e do desembolso associado; atraso seria lido como sinal negativo (Infobae).
- Contração da atividade e perda de renda real alimentam a incerteza sobre a eleição presidencial de 2027 (Ámbito, Infobae).
- Reversão do petróleo com expectativa de negociações com o Irã reduziria o suporte a nomes de energia com receita em dólar (Infobae, TradingEconomics).

Implicações para a carteira:
- Livro neutro por país: o otimizador deve zerar a exposição ao fator Argentina e ao beta global elevado dos ADRs argentinos; tamanho bruto pequeno pelo risco de cauda e de gap.
- Evitar abrir novos shorts em bancos argentinos nesta semana (sentinela em caution): combinação de queda acumulada forte, valuation perto do patrimônio e catalisadores positivos de cauda (apoio do Tesouro dos EUA, swaps, compras do BCRA, contágio de um Brasil mais à direita).
- Preferir dispersão intra-país a aposta de país: energia com receita em dólar ligada a Vaca Muerta (YPF, Vista, Pampa) tem driver distinto dos bancos e é citada como setor de fundamentos operacionais sólidos, mas carrega beta a petróleo que o modelo de risco precisa neutralizar.
- Neutralidade de estatais: YPF é controlada pelo Estado e sensível a política energética e ao ciclo eleitoral de 2027; tratar como tema de estatal, sem convicção específica alta.
- Grupo de alta sensibilidade a eventos: bancos e utilities reguladas (por exemplo, Edenor) concentram exposição a risco-país, regime cambial e rolagem da dívida em pesos; limitar risco específico por nome.
- Até o segundo turno brasileiro de 2026-10-25, ativos argentinos podem carregar parte do fator eleição do Brasil pelo alinhamento político citado por consultorias locais; o modelo de risco deve capturar essa correlação para o livro não acumular exposição oculta ao mesmo evento.

Eventos:
- Feriado do Dia da Diversidade Cultural: bolsa local possivelmente fechada enquanto ADRs negociam em Nova York (confirmar calendário da BYMA); coincide com a B3 fechada. (12/10/2026; uncertain)
- IPC de setembro (INDEC): teste da trajetória de desinflação e da credibilidade do programa econômico. (13/10/2026; uncertain)
- Vencimento de títulos do Tesouro em pesos a taxa fixa: primeiro teste de rolagem do mês. (15/10/2026; uncertain)
- EMAE de agosto: confirmação ou não da contração da atividade apontada por analistas locais. (21/10/2026; negative)
- Decisão do FOMC: um Fed mais duro reforça o principal vetor externo de alta do risco-país e de pressão sobre bancos. (28/10/2026; uncertain)
- Concentração de vencimentos em pesos (CER, dólar-linked, Lecap e Boncap) na virada do mês; mercado espera nova troca de dívida (canje) convocada pela Secretaria de Finanças na segunda quinzena. (30/10/2026; uncertain)
- Eleições de meio de mandato nos EUA: o apoio financeiro sinalizado pelo Tesouro americano depende do ambiente político em Washington. (03/11/2026; uncertain)

#### BR — regime: Evento binário eleitoral: reprecificação pró-ajuste fiscal após o primeiro turno, com distribuição bimodal até o segundo turno de 2026-10-25; juros globais nas máximas em décadas e Copom cauteloso limitam o alívio doméstico. (viés +0)
_(gerado por IA — provedor imported:claude-code)_

> O primeiro turno de 2026-10-04 terminou com Flávio Bolsonaro à frente de Lula por margem estreita, contrariando as pesquisas, e com onda de direita no Senado, na Câmara e nos estados. Antes da abertura da B3 de hoje, os ativos brasileiros negociados no exterior (EWZ, ETF do Ibovespa em Tóquio, ADRs de bancos, Petrobras e XP) e o real futuro mostram forte alta; analistas esperam bolsa em alta, dólar em queda e fechamento da curva, com estatais, bancos, small caps e domésticas sensíveis a juros à frente e exportadoras (Vale, Suzano, Klabin) para trás. A federação União-PP sinaliza apoio a Flávio, o PSD fica neutro e mercados de previsão passaram a dar ampla vantagem ao candidato do PL. Ainda assim o segundo turno é binário: um aperto nas pesquisas devolveria parte do movimento e uma vitória de Lula traria correção relevante segundo o BTG. O fiscal segue como pano de fundo (dívida em alta, ajuste grande e não detalhado por nenhum dos candidatos), e os juros longos globais elevados restringem a Selic; o próximo Copom só decide em 2026-11-04. Postura macro neutra: grande parte do cenário favorável tende a ser precificada já na abertura. Reação do pregão de hoje (barra intradiária capturada às 11h06 de Brasília): o ETF do Brasil em Nova York, o real e os nomes domésticos sensíveis a juros, os bancos e as estatais abriram em forte alta, confirmando que o mercado passou a precificar a vitória da oposição no segundo turno; exportadoras sobem menos. A neutralidade da carteira ao choque eleitoral é medida exatamente nessa reação.

Riscos:
- Reversão do trade eleitoral se as pesquisas do segundo turno mostrarem disputa apertada ou virada de Lula; o posicionamento já montado antes do primeiro turno em bancos, small caps, varejo e locadoras amplia a devolução, e o BTG projeta correção relevante de bolsa e real numa reeleição.
- Gap binário no primeiro pregão após 2026-10-25 maior do que o sugerido pela volatilidade histórica; casas como o Andbank esperam mercado volátil, com ataques, escândalos e boatos ao longo da campanha.
- Frustração fiscal: o ajuste necessário para estabilizar a dívida é grande, economistas duvidam da viabilidade política e nenhum dos candidatos detalhou medidas; o plano de Flávio fala em tesouraço sem quantificar cortes.
- Juros longos globais nas máximas em décadas, Fed com viés de aperto e dólar forte reduzem o diferencial de juros, limitam a apreciação do real e o espaço para cortes da Selic.
- Petróleo volátil: a liberação de estoques do G7 e a retomada das exportações do Oriente Médio pressionam o Brent hoje, e a Petrobras carrega beta duplo a petróleo e eleição após forte alta prévia.
- Crédito ao consumidor deteriorado: inadimplência em financiamento de veículos perto das máximas históricas, o que limita o alívio para bancos médios, varejo e locadoras mesmo com fechamento da curva.
- Governança das estatais: a União segue controladora; a privatização do Banco do Brasil é só possibilidade em estudo da campanha de Flávio, e mudanças de gestão podem alterar múltiplos antes de qualquer resultado.
- Risco institucional e externo: propostas de mudanças no STF e de anistia, apuração sobre possível interferência estrangeira e incerteza sobre relações comerciais em um eventual governo Flávio, segundo empresários.
- Calendário e liquidez: B3 fechada em 2026-10-12 e 2026-11-02 enquanto ADRs negociam, com risco de base entre ADR e ação local e rebalanceamentos em dias de gap ou de Copom.
- Estímulos de renda durante a campanha, como o reajuste do Bolsa Família, ampliam a pressão fiscal num quadro em que o ajuste necessário já é grande.

Implicações para a carteira:
- Manter o livro neutro em país e tratar a eleição como fator de risco, não como fonte de alpha: medir de forma determinística a exposição ao fator eleição (por exemplo, sensibilidade às cestas Desafiante e Incumbente do Bradesco BBI) e mantê-la próxima de zero.
- Postura de risco defensiva até depois de 2026-10-26, com o ajuste de janela de evento do modelo de risco para o Brasil ativo; convicções altas em nomes brasileiros só com concordância entre quant e pesquisa.
- Estatais (BBAS3, PETR3 e PETR4): neutralidade temática e sem visões direcionais fortes; o Banco do Brasil reage de forma mais clara ao componente eleitoral, e a Petrobras mistura petróleo e eleição e já subiu bastante.
- Não abrir shorts novos em nomes que sobem com vitória da oposição até após o segundo turno: Banco do Brasil, Petrobras, B3, XP, bancos médios, small caps domésticas da cesta Desafiante, construtoras e locadoras sensíveis a juros; catalisador dentro da janela e risco de squeeze.
- Pares bancários estatal contra privado (Banco do Brasil contra Itaú) são aposta no fator eleição, não alpha puro; o Itaú é visto como defensivo em qualquer resultado e não serve de hedge neutro de um long em BB.
- Exportadoras (Vale, Suzano, Klabin) tendem a ficar para trás com real mais forte: efeito de fator cambial a ser neutralizado pelo otimizador, não tese idiossincrática de short.
- Construtoras com canal duplo: ganham com o fechamento da curva, mas a política habitacional muda com o vencedor (Lula amplia o Minha Casa, Minha Vida; Flávio fala em retomar o Casa Verde e Amarela); baixa renda tem sensibilidade eleitoral ambígua.
- Varejo e consumo doméstico: suporte de renda de curto prazo com o Bolsa Família reajustado, mas inadimplência alta e custo de trabalho em disputa (Lula defende reduzir a jornada sem corte de salário; Flávio, jornada flexível negociada).
- Utilities e bond proxies (CPFL, Equatorial, Taesa, Copasa) estão na cesta Incumbente, mas se beneficiam do fechamento de juros: sensibilidade líquida ambígua; Sabesp tem continuidade regulatória em SP com a reeleição de Tarcísio e está na cesta All-Weather.
- Mercado de capitais (B3, XP) e small caps têm dupla alavancagem ao cenário de oposição segundo o Bradesco BBI: alta sensibilidade a fluxo; evitar shorts e moderar concentração de longs no mesmo fator.
- Educação: evidência macro fraca nesta janela; Vitru aparece na cesta Desafiante como small cap e o plano de Lula foca o ensino básico público; abster-se de visão setorial e deixar o quant decidir.
- Rebalanceamentos sensíveis: 2026-10-13 (terça, por feriado), 2026-10-26 (dia seguinte ao segundo turno) e 2026-11-03 (primeiro dia do Copom); limitar participação no volume e monitorar risco de base dos ADRs.
- Sem shorts novos em estatais com tese de privatização ligada ao resultado do segundo turno (Copasa, Sanepar, Cemig).
- Neutralidade ao choque eleitoral medida na reação de hoje; postura defensiva até o segundo turno.

Eventos:
- Primeiro pregão após o primeiro turno: abertura com gap de alta esperado em bolsa, real e juros; Focus do BCB e PMI no dia; rebalanceamento semanal do CDP no fechamento. (05/10/2026; positive)
- Reunião da federação União Brasil-PP com as bancadas eleitas para formalizar apoio no segundo turno, com tendência a Flávio; outros partidos do centrão podem seguir. (06/10/2026; positive)
- IPCA de setembro (IBGE): leitura de inflação corrente que condiciona a curva de juros e o Copom de novembro. (09/10/2026; uncertain)
- Feriado de Nossa Senhora Aparecida: B3 fechada enquanto ADRs negociam em Nova York; rebalanceamento semanal passa para 2026-10-13. (12/10/2026; uncertain)
- Pesquisa Mensal de Comércio (IBGE): termômetro do consumo doméstico e do varejo em ambiente de juros altos e inadimplência elevada. (15/10/2026; uncertain)
- Início do pagamento do Bolsa Família com reajuste anunciado em setembro: suporte de renda ao consumo de baixa renda durante a campanha, com custo fiscal. (19/10/2026; uncertain)
- IPCA-de outubro (IBGE), última leitura de inflação antes do segundo turno. (23/10/2026; uncertain)
- segundo turno presidencial entre Flávio Bolsonaro e Lula, além de segundo turno para governador em alguns estados, inclusive RJ e AM: principal evento binário da janela. (25/10/2026; uncertain)
- Primeiro pregão após o segundo turno: gap de abertura e rebalanceamento semanal do CDP no mesmo dia. (26/10/2026; uncertain)
- Decisão do FOMC (reunião de 2026-10-27 e 2026-10-28): trajetória do Fed, Treasuries e dólar, com efeito sobre real e espaço para a Selic. (28/10/2026; uncertain)
- Feriado de Finados com B3 fechada; rebalanceamento semanal passa para 2026-11-03, primeiro dia da reunião do Copom. (02/11/2026; uncertain)
- Decisão do Copom, primeira após a eleição: ritmo do ciclo de cortes dependente da leitura fiscal do vencedor e do cenário externo. (04/11/2026; uncertain)

#### CL — regime: Doméstico fraco e câmbio pressionado pelo choque global de juros; cobre forte com oferta chilena fragilizada; agenda pró-mercado em implementação e banco central parado (viés -1)
_(gerado por IA — provedor imported:claude-code)_

> O Chile chega à semana com atividade fraca: Imacec em queda em agosto, mineração em forte contração segundo o ministro da Fazenda Jorge Quiroz, desemprego alto e confiança do consumidor pior que há um ano (DF, TradingEconomics). O BCCh mantém a TPM, avalia reunião a reunião citando petróleo e riscos externos, e volta a decidir em 2026-10-27. O peso acumulou semanas seguidas de depreciação e fechou a sexta (2026-10-02) na máxima desde abril de 2025, entre as moedas emergentes mais fracas do dia; a bolsa interrompeu a sequência de quedas na sexta, mas acumula semanas de baixa em dólares e perda no ano (DF). Reação de hoje (2026-10-05): o retrato intradiário mostra o peso se apreciando com clareza, em linha com o apetite a risco pós-eleição no Brasil e o cobre em leve alta (TradingEconomics). No campo de política, o governo Kast prevê promulgar a Lei de Reconstrução nesta semana, a reforma do mercado de capitais avança na Câmara e o orçamento de 2027 tem crescimento de gasto contido. Em commodities, o cobre segue perto das máximas, mas a oferta chilena está fragilizada: supervisores de Escondida rejeitaram a oferta final e a empresa pediu mediação obrigatória, e Centinela tem conflito salarial; o lítio caiu com força em setembro com revisão de estoques chineses e reabertura de minas australianas. Regime: fraqueza doméstica sem evento binário nacional; o vetor principal é externo (juros americanos, dólar, contágio do Brasil).

Riscos:
- Nova depreciação do peso se o Treasury longo e o dólar global seguirem em alta; o peso esteve entre as moedas emergentes mais fracas na sexta (DF).
- Aprofundamento da recessão na mineração e no emprego, com efeito sobre bancos e varejo domésticos (DF, entrevista de Quiroz; TradingEconomics).
- Greve em Escondida ou em Centinela após a mediação: alta de preço do cobre, mas menor produção e exportação chilena (DF; Copper Weekly Brief).
- Lítio em queda forte com estoques chineses revisados para cima, mas sujeito a saltos por choques de oferta chinesa: risco de squeeze em shorts de SQM (TradingEconomics).
- Contágio do segundo turno brasileiro de 2026-10-25 sobre fluxos regionais e apetite por ativos latino-americanos (DF, Ámbito).

Implicações para a carteira:
- País neutro: não transformar o regime fraco em aposta vendida em Chile; buscar dispersão entre domésticas cíclicas (bancos, varejo) mais expostas a atividade e desemprego e nomes regulados e defensivos (utilities, sanitárias), neutralizando beta e sensibilidade cambial.
- Cobre forte contra lítio fraco é um fator de commodity, não alpha específico: o modelo de risco deve tratá-lo explicitamente; shorts em SQM pedem cautela de squeeze.
- O alívio tributário e a agenda pró-crescimento do governo Kast beneficiam o país de forma ampla; é fator de país e não diferencia emissores, portanto não deve sustentar convicção específica.
- Sensibilidade a eventos: bancos chilenos ao IPC de 2026-10-08 e ao BCCh de 2026-10-27; manter risco específico moderado nessas datas.
- Execução: ADRs chilenos (bancos, SQM, LATAM) são o instrumento preferencial em feriado local e quando a liquidez em Santiago for rasa.

Eventos:
- Fim aproximado do prazo de mediação obrigatória em Escondida (prorrogável); depois dele, greve legal dos supervisores passa a ser possível. Data aproximada. (08/10/2026; uncertain)
- IPC de setembro (INE): calibra a trajetória do BCCh e o custo de funding dos bancos. (08/10/2026; uncertain)
- Promulgação prevista da Lei de Reconstrução Nacional nesta semana, segundo o ministro da Fazenda. (09/10/2026; positive)
- Feriado do Encuentro de Dos Mundos: bolsa de Santiago possivelmente fechada (confirmar); ADRs chilenos negociam. (12/10/2026; uncertain)
- Reunião de política monetária do BCCh, com expectativa de manutenção. (27/10/2026; uncertain)
- Decisão do FOMC: principal vetor do peso chileno no momento. (28/10/2026; uncertain)
- Desemprego de setembro (INE). (29/10/2026; uncertain)
- Produção de cobre, produção industrial e varejo de setembro. (30/10/2026; uncertain)

#### CO — regime: Aperto monetário em curso, fragilidade fiscal aguda e governo pró-mercado e pró-petróleo; prêmio de risco soberano domina o país (viés -1)
_(gerado por IA — provedor imported:claude-code)_

> O BanRep surpreendeu com alta de juros em 2026-09-30, em decisão dividida, diante de inflação em aceleração e acima da meta; a ata sai nesta segunda e analistas esperam nova aceleração do IPC de setembro, a ser divulgado em 2026-10-07 (Valora Analitik, TradingEconomics, La República). O fiscal é o principal risco: o orçamento de 2027 reapresentado projeta déficit recorde e o comitê da regra fiscal fala em ajuste sem precedentes para voltar à regra (Rio Times). O governo De la Espriella promete cortar gastos em vez de subir impostos e prepara uma 'Lei de Resgate' fiscal para outubro, incluindo a redução gradual do imposto sobre movimentações financeiras, tema caro aos bancos (Valora Analitik). Na energia, a agenda é pró-exploração: a ANLA licenciou um novo desenvolvimento da Ecopetrol nos Llanos, a empresa tem novo presidente e alavancagem que cresceu mais que o patrimônio na década (Valora Analitik, La República). O peso se depreciou com força em setembro e recuperou parte na sexta (Valora Analitik). Reação de hoje (2026-10-05): o retrato intradiário indica peso colombiano mais fraco, na contramão do peso chileno, sinal a confirmar no fechamento (TradingEconomics). Regime: aversão a risco soberano com assimetria setorial (petróleo e juros altos contra crédito e consumo).

Riscos:
- Rebaixamento soberano ou perda de credibilidade fiscal se o orçamento e a Lei de Resgate não convencerem; abertura dos TES e depreciação do peso (Rio Times, Valora Analitik).
- Inflação acima da meta por mais tempo, com El Niño pressionando alimentos e energia, forçando mais altas do BanRep e pesando sobre crédito e consumo (La República, TradingEconomics).
- Extração de valor da Ecopetrol pelo Tesouro em contexto de liquidez fiscal apertada, somada à alavancagem crescente da empresa (La República, Valora Analitik).
- Reversão do petróleo por negociações com o Irã, liberação de estoques do G7 e recuperação das exportações do Golfo, retirando o principal suporte de termos de troca (TradingEconomics, Infobae).
- Liquidez local rasa na BVC e risco de base entre ADR e ação local em feriados.

Implicações para a carteira:
- Neutralidade de estatais: Ecopetrol (e ISA, controlada por ela) é estatal com beta a petróleo e exposta a decisões de dividendos do governo; tratar como tema de estatal e neutralizar junto com o fator petróleo, sem convicção específica alta até haver clareza sobre dividendos.
- Bancos (Bancolombia, Grupo Aval): margem favorecida por juros altos contra risco de crédito com desemprego elevado; a redução do imposto sobre movimentações financeiras seria catalisador positivo para o setor, mas ainda sem projeto protocolado.
- País neutro: o prêmio soberano colombiano é fator de país; o alpha deve vir da dispersão petróleo contra crédito e consumo, não de direção.
- Alta sensibilidade a eventos nas datas de IPC, BanRep e orçamento; não abrir shorts em nomes colombianos dentro da janela de proximidade de catalisador definida no mandato.
- Execução preferencial via ADRs; limitar participação no volume local.

Eventos:
- Ata da reunião do BanRep de setembro: sinal sobre continuidade do aperto. (05/10/2026; uncertain)
- IPC de setembro (DANE): consenso de analistas aponta nova aceleração. (07/10/2026; negative)
- Feriado do Día de la Raza: BVC possivelmente fechada (confirmar); ADRs de Ecopetrol e Bancolombia negociam. (12/10/2026; uncertain)
- Prazo legal habitual para o Congresso aprovar o orçamento de 2027 (data a confirmar). (20/10/2026; uncertain)
- Decisão do FOMC: vetor externo para o peso e para os TES. (28/10/2026; uncertain)
- Decisão do BanRep e desemprego de setembro. (30/10/2026; uncertain)
- Apresentação da Lei de Resgate fiscal ao Congresso prevista para outubro, sem data confirmada; inclui corte de gastos e redução gradual do imposto sobre movimentações financeiras. (30/10/2026; uncertain)

#### GLOBAL — regime: Aperto do Fed com dólar forte e juro longo americano nas máximas desde 2002; petróleo alto, mas com sinais de normalização de oferta; dispersão extrema entre metais; volatilidade implícita global baixa e risco latino-americano concentrado em eventos locais (viés -1)
_(gerado por IA — provedor imported:claude-code)_

> O pano de fundo global é de aperto: o Fed subiu juros em setembro afirmando que a inflação segue elevada, o juro longo americano tocou a máxima desde 2002 e o dólar está perto da máxima em mais de um ano, o que pressiona moedas e carry de emergentes. O payroll de setembro veio muito fraco, com revisões negativas, e o mercado passou a precificar majoritariamente manutenção em outubro, mas ainda vê alta provável em dezembro; a ata do FOMC em 2026-10-07, o CPI em 2026-10-14 e a decisão de 2026-10-28 são os pontos de virada. Nas commodities a dispersão é extrema: o Brent segue alto, mas cede com liberação de reservas emergenciais pelas grandes economias e exportações do Golfo voltando ao nível pré-conflito em vários dias; o cobre está perto do recorde com oferta chilena fraca, Escondida em retomada gradual sob autorização de greve sujeita a mediação e a decisão tarifária americana adiada; o minério de ferro caiu forte com a entrada de Simandou; o lítio despencou no mês com revisão de estoques na China e reabertura de minas australianas. A China está fechada pelo feriado nacional e reabre em 2026-10-08, o que pode gerar gaps nos metais. Na manhã de 2026-10-05, no pré-mercado de Nova York, o EWZ subia com força após a surpresa do primeiro turno brasileiro, enquanto o EWW ficava praticamente estável, o índice do dólar se firmava, o Brent cedia levemente, o cobre subia após o payroll fraco, os futuros do S&P ficavam estáveis e o VIX seguia baixo: o risco latino-americano é de evento local, não sistêmico.

Riscos:
- Reaceleração da inflação americana no CPI ou no PCE reacende a precificação de alta do Fed, com juro longo e dólar subindo de novo e pressionando valuations e moedas latino-americanas.
- Juro longo americano persistentemente nas máximas desde 2002 encarece o capital e pune setores de duração longa, como utilities, imobiliário e crescimento caro.
- Petróleo com risco nos dois sentidos: normalização em Hormuz e liberação de reservas podem derrubar o Brent rapidamente, enquanto nova interrupção no Golfo ou em Bab el-Mandeb pode dispará-lo.
- Cobre perto do recorde sustentado por choques de oferta: acordo na mediação de Escondida, fim da ameaça tarifária americana e estoques elevados nos EUA podem provocar reversão, com demanda chinesa ainda fraca.
- Lítio em queda forte, mas sujeito a saltos com notícias de oferta chinesa, como as licenças da mina da CATL, com risco de squeeze para vendidos no setor.
- Minério de ferro fraco com Simandou entrando e reabertura chinesa capaz de gerar gap em qualquer direção.
- Concentração de fluxo no Brasil: posicionamento já sobreposto de gestores globais e a alta forte de hoje deixam o mercado vulnerável a reversão se as pesquisas de segundo turno mudarem.

Implicações para a carteira:
- Regime e calendário (janela eleitoral no Brasil, CPI e FOMC dentro do horizonte) sustentam postura de risco defensiva na decisão do PM, sem afrouxar nenhum limite do mandato.
- Neutralizar separadamente as sensibilidades a petróleo, cobre, minério e lítio: um livro neutro em materiais pode esconder aposta comprada em cobre e vendida em minério ou lítio, e long em produtores de petróleo contra short em consumidores de combustível embute beta ao Brent.
- Neutralizar sensibilidade a juros e a moeda além do beta de mercado: utilities, imobiliário e nomes de duração longa têm alta exposição ao CPI de 2026-10-14 e ao FOMC de 2026-10-28.
- Shorts: evitar abrir posições vendidas em nomes com catalisador de manchete explosivo na janela, como lítio (oferta chinesa), mineradoras de cobre (greves no Chile) e, no Brasil, nomes que sobem com vitória da oposição (bancos e petroleira estatais, domésticas de pequena capitalização) até depois de 2026-10-25.
- Estatais: manter o tema neutro durante a janela eleitoral brasileira; o rali de hoje amplia o beta eleitoral desses nomes e o risco de gap no segundo turno.
- Com a China fechada até 2026-10-07, preços de metais e de ações ligadas a minério e lítio podem abrir com gap em 2026-10-08; não dimensionar posições novas nesses nomes com base apenas no preço pré-feriado.
- VIX baixo e risco concentrado em eventos locais indicam que o alpha deve vir de dispersão dentro de setores e de commodities, não de apostas direcionais de país ou de mercado.

Eventos:
- Reação ao primeiro turno no Brasil no pré-mercado de Nova York: forte alta do EWZ e de ADRs brasileiros, EWW estável, dólar firme e VIX baixo; ISM de serviços nos EUA no mesmo dia (05/10/2026; uncertain)
- Ata do FOMC da reunião de setembro (07/10/2026; uncertain)
- Reabertura dos mercados chineses após o feriado nacional, com descoberta de preço em minério, lítio e cobre (08/10/2026; uncertain)
- CPI de setembro nos EUA, chave para a precificação de nova alta do Fed (14/10/2026; uncertain)
- PPI e vendas no varejo de setembro nos EUA (15/10/2026; uncertain)
- Segundo turno presidencial no Brasil, principal evento binário para fluxos de emergentes na região (25/10/2026; uncertain)
- Decisão do FOMC (28/10/2026; uncertain)
- PIB preliminar do 3T26 e PCE de setembro nos EUA (29/10/2026; uncertain)
- Eleições legislativas nos EUA, também prazo político para um acordo tarifário com o México (03/11/2026; uncertain)

#### MX — regime: Desmonte do carry em peso, com Fed apertando e Banxico em pausa; incerteza comercial com os EUA (revisão anual do T-MEC e tarifas setoriais) e desfecho binário buscado antes das eleições legislativas americanas (viés -1)
_(gerado por IA — provedor imported:claude-code)_

> O México vive um regime de carry em desmonte: o Fed voltou a subir juros em setembro enquanto o Banxico manteve a taxa por unanimidade e afirmou que não reagirá de forma mecânica ao Fed, o que estreita o diferencial de juros e tira atratividade do peso. A moeda acumulou várias semanas seguidas de depreciação e tocou no início de outubro a região mais fraca em cerca de um ano. A inflação voltou a acelerar em agosto, o Banxico vê balanço de riscos inflacionários para cima e, ao mesmo tempo, estima moderação da atividade no 3T26 com folga na economia, o que deixa o banco central sem espaço claro para cortar nem motivo para subir. No comércio, a revisão do T-MEC caiu no regime de revisões anuais; seguem as tarifas americanas sobre aço, alumínio e veículos fora das regras, e as divergências centrais (conteúdo especificamente americano nos veículos, acesso ao mercado elétrico frente à prioridade da CFE) continuam abertas. Os dois governos buscam um acordo-quadro antes das eleições legislativas americanas de 2026-11-03, mas o representante comercial americano fala em arranjos interinos até o fim do ano, empurrando mudanças complexas para 2027, e montadoras chinesas pausaram projetos no país por incerteza sobre regras de origem. Na manhã de 2026-10-05, após a surpresa do primeiro turno no Brasil, o peso estava praticamente estável frente ao fechamento de sexta e o EWW quase parado no pré-mercado de Nova York, enquanto o EWZ subia com força: a reação está concentrada no Brasil, sem contágio positivo visível para o México. Leitura: viés de país levemente negativo, mas o CDP é neutro por país; o que importa para o livro é a alta sensibilidade de grupos de ações a manchetes comerciais, ao peso e aos dados de inflação.

Riscos:
- Aprofundamento do desmonte do carry: um Fed mais duro com o Banxico parado enfraqueceria mais o peso, com repasse cambial à inflação que o próprio Banxico monitora, pressionando consumo doméstico e bancos.
- Negociação comercial sem acordo ou só com arranjo interino, mantendo as tarifas setoriais sobre aço, alumínio e veículos e prolongando a pausa de investimentos ligados ao nearshoring, inclusive das montadoras chinesas.
- Acordo-surpresa antes de 2026-11-03: apreciação rápida do peso e gap de alta em siderúrgicas, autopeças e imóveis industriais, com risco de short squeeze para quem estiver vendido nesses nomes.
- Disputa sobre acesso ao mercado elétrico frente à prioridade da CFE na revisão do T-MEC, risco regulatório para energia e infraestrutura que se soma ao prêmio institucional deixado pela eleição judicial e pelo controle dominante do partido governista sobre as cortes federais.
- Inflação acima da meta com aceleração recente e atividade em moderação no 3T26: combinação que limita o Banxico e pesa sobre os lucros de empresas domésticas.
- Rotação de fluxo regional: com o México como sobreposição de consenso e o Brasil ganhando apetite após o primeiro turno, saídas do México podem pressionar ações locais de forma sistemática e contaminar sinais de curto prazo.

Implicações para a carteira:
- Carteira neutra por país: o viés macro levemente negativo não vira aposta de país; o otimizador deve neutralizar o fator México e o fator de sensibilidade cambial.
- Pares de exportadoras com receita em dólar contra consumo doméstico embutem aposta no peso que um acordo comercial pode reverter de forma abrupta; tratar essa exposição como fator cambial a neutralizar, não como alpha idiossincrático.
- Evitar shorts novos em nomes que disparam com um acordo tarifário (siderurgia, autopeças, imóveis industriais ligados ao nearshoring) até 2026-11-03; também não abrir longs cuja tese dependa só do acordo, porque o desfecho é binário e a data é política.
- Bancos e consumo têm alta sensibilidade a eventos datados (INPCs de 2026-10-08 e 2026-10-22, Banxico de 2026-11-05); preferir convicção baixa ou abstenção nesses nomes quando a tese depender da trajetória de juros.
- A temporada de resultados do 3T26 das grandes mexicanas tende a cair na segunda metade de outubro pelo padrão histórico, mas as datas não foram confirmadas nesta pesquisa; carregar as datas oficiais de RI antes de dimensionar e respeitar a regra de não abrir short com catalisador próximo.
- Estatais: no México a exposição ao tema é indireta, via concorrentes e fornecedores de Pemex e CFE (que não negociam ações) e via a disputa de energia no T-MEC; manter o tema neutro e não buscar alpha nele nesta janela.
- Setores regulados e de concessão (aeroportos, telecom, energia, mineração) carregam prêmio institucional sem catalisador datado; tratar como risco de cauda nos vetos e não como sinal de curto prazo.
- A fraqueza relativa de ações mexicanas hoje, enquanto o Brasil dispara, deve ser lida como fluxo de país e não como informação idiossincrática; sinais de reversão de curto prazo podem estar contaminados nesta semana.

Eventos:
- Primeiro pregão após o primeiro turno no Brasil: peso estável e EWW praticamente parado no pré-mercado, enquanto ativos brasileiros sobem com força; observar se há realocação de fluxo regional do México para o Brasil ao longo da semana (05/10/2026; uncertain)
- INPC de setembro (INEGI) e ata da decisão de setembro do Banxico; a inflação vinha acelerando e o banco vê riscos para cima (08/10/2026; uncertain)
- Vendas no varejo de agosto, termômetro do consumo doméstico (21/10/2026; uncertain)
- INPC da primeira quinzena de outubro e taxa de desemprego de setembro, insumos centrais para a decisão de novembro do Banxico (22/10/2026; uncertain)
- IGAE de agosto (atividade econômica mensal) (23/10/2026; uncertain)
- Decisão do FOMC: nova alta estreitaria ainda mais o diferencial de juros com o Banxico parado e pressionaria o peso (28/10/2026; uncertain)
- Estimativa preliminar do PIB do 3T26; o Banxico já sinaliza moderação da atividade no trimestre (30/10/2026; negative)
- Eleições legislativas nos EUA, prazo político buscado pelos dois governos para um acordo-quadro sobre tarifas de aço, alumínio e veículos; acordo seria positivo para o peso e para industriais, fracasso prolonga a incerteza (03/11/2026; uncertain)
- Decisão de política monetária do Banxico (05/11/2026; uncertain)

#### PE — regime: Estabilidade monetária e termos de troca favoráveis, com inflação acima da meta por combustíveis e El Niño e governabilidade fragilizada após revés municipal do partido do governo (viés +0)
_(gerado por IA — provedor imported:claude-code)_

> O BCRP mantém a taxa estável há mais de um ano e decide em 2026-10-07; o banco destaca termos de troca favoráveis e atividade firme, mas a inflação de setembro voltou a subir e segue acima da faixa-meta por combustíveis e efeitos do El Niño, enquanto o núcleo segue contido (TradingEconomics, Infobae). O sol teve em setembro a maior desvalorização em vários meses pelo choque de juros americanos, contida por oferta de dólares do BCRP (Gestión). Na política, as eleições regionais e municipais de 2026-10-04 foram um revés para o Fuerza Popular, partido da presidente Keiko Fujimori, que não elegeu nenhum candidato a prefeito em Lima Metropolitana, onde o Renovación Popular de López Aliaga venceu pela boca de urna; no Cusco, Verónika Mendoza, de esquerda, lidera para o governo regional, e várias regiões, inclusive mineiras como Arequipa, Áncash e Moquegua, podem ir a segundo turno regional em 2026-11-29 (Infobae). A Câmara de Deputados debate em 2026-10-06 a delegação de faculdades legislativas, que a comissão restringiu a segurança e El Niño; o premiê Galarreta a considerou insuficiente (Gestión). A proposta de eliminar o teto de juros, positiva para bancos, não aparece no escopo aprovado pela comissão (RPP, Gestión). Reação de hoje (2026-10-05) ao resultado brasileiro e ao pleito local não verificada. Regime: macro estável e bom para o cobre, com ruído político crescente.

Riscos:
- Governabilidade: o revés do partido do governo em Lima e um Congresso fragmentado podem travar a agenda econômica e as faculdades legislativas (Infobae, Gestión).
- Lideranças regionais de esquerda e segundos turnos regionais em regiões mineiras elevam o risco de conflitos socioambientais em torno de minas até o fim de novembro (Infobae).
- Inflação acima da meta por combustíveis e El Niño, que também ameaça agricultura e pesca (TradingEconomics, Infobae).
- Sol pressionado por juros americanos altos; alívio depende do Fed (Gestión).
- A expectativa de fim do teto de juros pode frustrar-se, já que o escopo de faculdades aprovado na comissão não inclui o tema (RPP, Gestión).

Implicações para a carteira:
- País neutro: o alpha peruano deve vir da dispersão entre mineração de cobre (termos de troca favoráveis) e financeiras domésticas (Credicorp, Intercorp), com o beta a cobre neutralizado pelo modelo de risco.
- Bancos peruanos: não atribuir convicção à eliminação do teto de juros enquanto ela não constar de texto legislativo; catalisador incerto.
- Mineradoras com operações no sul e em regiões com segundo turno regional ou nova liderança de esquerda passam a ter maior sensibilidade a eventos sociais até 2026-11-29; cautela com tamanho em longs e checagem de risco de paralisação.
- Shorts em nomes peruanos devem evitar a semana da decisão do BCRP e do debate das faculdades; liquidez da BVL rasa e feriado em 2026-10-08 favorecem execução via ADRs.

Eventos:
- Plenário da Câmara de Deputados debate a delegação de faculdades legislativas (segurança e El Niño); depois segue ao Senado. (06/10/2026; uncertain)
- Decisão do BCRP, com histórico longo de manutenção e inflação acima da meta. (07/10/2026; uncertain)
- Feriado do Combate de Angamos: BVL possivelmente fechada (confirmar); ADRs de Credicorp, Southern Copper e Buenaventura negociam. (08/10/2026; uncertain)
- PIB de agosto e desemprego (INEI). (15/10/2026; uncertain)
- Decisão do FOMC: vetor externo para o sol. (28/10/2026; uncertain)

### Visões aplicadas

| Emissor | Origem | Score | Confiança | Restrições | Autor |
|---|---|---|---|---|---|
| AR_ADECOAGRO | IA | -1 | 30% | sem short | imported:claude-code |
| AR_CEPU | IA | +1 | 40% | — | imported:claude-code |
| AR_CRESUD | IA | 0 | 100% | sem short | imported:claude-code |
| AR_YPF | IA | +1 | 45% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_3TENTOS | IA | +1 | 30% | — | imported:claude-code |
| BR_ALPARGATAS | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_ALUPAR | IA | +1 | 40% | — | imported:claude-code |
| BR_ANIMA | IA | 0 | 100% | sem short | imported:claude-code |
| BR_ASSAI | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_AURA | IA | +1 | 50% | — | imported:claude-code |
| BR_AUREN | IA | 0 | 100% | sem short | imported:claude-code |
| BR_AXIA | IA | +1 | 45% | — | imported:claude-code |
| BR_BB | IA | 0 | 100% | sem short | imported:claude-code |
| BR_BBSEG | IA | -1 | 35% | — | imported:claude-code |
| BR_BEMOBI | IA | +1 | 50% | sem short | imported:claude-code |
| BR_BRADESCO | IA | +1 | 35% | — | imported:claude-code |
| BR_BRADSAUDE | IA | +1 | 35% | — | imported:claude-code |
| BR_BRAVA | IA | +1 | 30% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_BTG | IA | +1 | 45% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_CMIN | IA | -1 | 45% | — | imported:claude-code |
| BR_COSAN | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_CSN | IA | 0 | 100% | sem short | imported:claude-code |
| BR_CURY | IA | -1 | 30% | — | imported:claude-code |
| BR_ECORODOVIAS | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_ENEVA | IA | -1 | 35% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_EQUATORIAL | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_FLEURY | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_GPA | IA | -1 | 30% | sem short | imported:claude-code |
| BR_HAPVIDA | IA | -1 | 35% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_IGUATEMI | IA | +1 | 35% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_INTER | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_ISAENERGIA | IA | +1 | 35% | — | imported:claude-code |
| BR_LOCALIZA | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_MAGALU | IA | -1 | 35% | sem short | imported:claude-code |
| BR_MARCOPOLO | IA | -1 | 30% | — | imported:claude-code |
| BR_MBRF | IA | -1 | 30% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_MOURADUBEUX | IA | +1 | 55% | — | imported:claude-code |
| BR_MOVIDA | IA | +1 | 35% | sem short | imported:claude-code |
| BR_MRV | IA | 0 | 100% | sem short | imported:claude-code |
| BR_NATURA | IA | +1 | 40% | — | imported:claude-code |
| BR_NU | IA | +1 | 50% | — | imported:claude-code |
| BR_ONCOCLINICAS | IA | 0 | 100% | sem short | imported:claude-code |
| BR_PAGS | IA | +1 | 45% | — | imported:claude-code |
| BR_PAGUEMENOS | IA | +1 | 40% | — | imported:claude-code |
| BR_PATRIA | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_PETROBRAS | IA | +1 | 35% | — | imported:claude-code |
| BR_PETZCOBASI | IA | 0 | 100% | sem short | imported:claude-code |
| BR_PICPAY | IA | +1 | 35% | — | imported:claude-code |
| BR_RIACHUELO | IA | +1 | 50% | — | imported:claude-code |
| BR_SABESP | IA | +1 | 45% | — | imported:claude-code |
| BR_SBF | IA | +1 | 45% | — | imported:claude-code |
| BR_SIGMALITH | IA | -1 | 35% | sem short | imported:claude-code |
| BR_SIMPAR | IA | 0 | 100% | sem short | imported:claude-code |
| BR_SMARTFIT | IA | -1 | 30% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_SUZANO | IA | +1 | 40% | — | imported:claude-code |
| BR_TENDA | IA | +1 | 50% | — | imported:claude-code |
| BR_TUPY | IA | +1 | 35% | sem short | imported:claude-code |
| BR_ULTRAPAR | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_UNIPAR | IA | -1 | 30% | sem short | imported:claude-code |
| BR_VALE | IA | -1 | 30% | — | imported:claude-code |
| BR_VAMOS | IA | 0 | 100% | sem short | imported:claude-code |
| BR_VIBRA | IA | +1 | 40% | — | imported:claude-code |
| BR_WEG | IA | +1 | 45% | — | imported:claude-code |
| BR_XP | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| BR_YDUQS | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| CL_LATAM | IA | +1 | 45% | — | imported:claude-code |
| CL_SQM | IA | -1 | 35% | — | imported:claude-code |
| CO_CIBEST | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| CO_GEOPARK | IA | +1 | 45% | — | imported:claude-code |
| CO_GRANTIERRA | IA | 0 | 100% | sem short | imported:claude-code |
| CO_TECNOGLASS | IA | -1 | 30% | — | imported:claude-code |
| LA_MELI | IA | +1 | 35% | — | imported:claude-code |
| LA_MILLICOM | IA | +1 | 40% | \|w\| ≤ 1,25% | imported:claude-code |
| MX_AMX | IA | +1 | 30% | \|w\| ≤ 1,25% | imported:claude-code |
| MX_CEMEX | IA | +1 | 40% | — | imported:claude-code |
| MX_FEMSA | IA | 0 | 0% | \|w\| ≤ 1,25% | imported:claude-code |
| MX_PENOLES | IA | +1 | 35% | — | imported:claude-code |
| MX_VOLARIS | IA | -1 | 35% | \|w\| ≤ 1,25% | imported:claude-code |
| MX_WALMEX | IA | -1 | 35% | — | imported:claude-code |
| PE_BVN | IA | +1 | 30% | — | imported:claude-code |
| PE_CREDICORP | IA | +1 | 45% | — | imported:claude-code |
| PE_SCCO | IA | -1 | 40% | \|w\| ≤ 1,25% | imported:claude-code |

## Otimizador

| Item | Valor |
|---|---|
| Status / solver | optimal / CLARABEL |
| Tempo de solução | 14,94 s |
| Alpha esperado (a.a.) | 1,47% |
| Custo esperado (a.a.) | 1,27% |
| Candidatos | 160 |
| Excluídos | sem_linha_short: 73, squeeze_alto: 28, squeeze_medio_teto: 14, squeeze_na_teto: 44, visao_no_long: 21, visao_no_short: 72, visao_teto_peso: 27 |
| Restrições ativas | net_exposure, country:BR, country:CL, sector:Energy, style:liquidity, max_short:BR_EMBRAER, max_long:BR_JBS, max_short:BR_MBRF, max_long:BR_PAGS, max_short:BR_PATRIA, max_long:BR_PETROBRAS, max_long:BR_SUZANO, max_long:BR_TENDA, max_short:BR_ULTRAPAR, max_short:CO_CIBEST, max_short:LA_LILA, max_short:PE_SCCO |

Observações do otimizador:
- Meta de vol ajustada pelo gestor: 3.64% (config 5.00%).
- Gross máximo efetivo: 2.00x (override do gestor).
- Modo 'match': meta de vol inatingível só reduzindo a aversão a risco (alpha líquido de custos insuficiente ou capacidade de liquidez/aluguel); usado 64.00x.
- Modo 'match': alpha escalado em 1.71x só para atingir o piso da banda de vol com margem (3.15%).
- Passadas de otimização: 2.
- Perna comprada 23.42%, vendida 22.42%; custo pontual 18.3 bps do NAV; aluguel 8.2 bps a.a.
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (×1.50 na vol de BR)
- Inception: carteira montada a partir do caixa.
- Carteira do CDP: pesquisa de IA + decisão do agente PM.
- [visões] IC das visões de IA = 0.01 (fase S1, teto 0.03).
- [visões] AR_CEPU: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_ALUPAR: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_ASSAI: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_AURA: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_AXIA: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_BBSEG: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_BRADESCO: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_BRADSAUDE: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_BTG: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_CMIN: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_COSAN: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_CURY: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_ECORODOVIAS: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_ENEVA: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_EQUATORIAL: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_INTER: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_ISAENERGIA: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_LOCALIZA: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_MARCOPOLO: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_MBRF: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_MOURADUBEUX: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_NATURA: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_NU: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_PAGS: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_PAGUEMENOS: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_PETROBRAS: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_PICPAY: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_RIACHUELO: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_SABESP: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_SBF: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_SMARTFIT: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_TENDA: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_VIBRA: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_WEG: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] BR_XP: 2 visões de AI agregadas pela média das inclinações.
- [visões] BR_YDUQS: 2 visões de AI agregadas pela média das inclinações.
- [visões] CL_LATAM: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] CL_SQM: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] CO_GEOPARK: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] CO_TECNOGLASS: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] LA_MELI: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] LA_MILLICOM: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] MX_CEMEX: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] MX_VOLARIS: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] PE_BVN: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] PE_CREDICORP: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] PE_SCCO: visão do gestor substitui a inclinação de 1 visão(ões) de IA.
- [visões] AR_ADECOAGRO: inclinação AI z=-0.22 ⇒ α -0.28% a.a.
- [visões] AR_CEPU: inclinação PM z=+0.45 ⇒ α +0.30% a.a.
- [visões] AR_CRESUD: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] AR_YPF: inclinação AI z=+0.34 ⇒ α +0.18% a.a.
- [visões] BR_3TENTOS: inclinação AI z=+0.22 ⇒ α +0.32% a.a.
- [visões] BR_AFYA: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_ALPARGATAS: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_ALUPAR: inclinação PM z=+0.45 ⇒ α +0.35% a.a.
- [visões] BR_ANIMA: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_ASSAI: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_AURA: inclinação PM z=+0.45 ⇒ α +0.75% a.a.
- [visões] BR_AUREN: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_AXIA: inclinação PM z=+0.30 ⇒ α +0.26% a.a.
- [visões] BR_BB: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_BBSEG: inclinação PM z=-0.30 ⇒ α -0.22% a.a.
- [visões] BR_BEMOBI: inclinação AI z=+0.38 ⇒ α +0.50% a.a.
- [visões] BR_BRADESCO: inclinação AI z=+0.13 ⇒ α +0.08% a.a.
- [visões] BR_BRADSAUDE: inclinação PM z=+0.30 ⇒ α +0.31% a.a.
- [visões] BR_BRAVA: inclinação AI z=+0.22 ⇒ α +0.29% a.a.
- [visões] BR_BTG: inclinação PM z=+0.30 ⇒ α +0.25% a.a.
- [visões] BR_CEMIG: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_CMIN: inclinação PM z=-0.30 ⇒ α -0.41% a.a.
- [visões] BR_COPASA: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_COSAN: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_CSN: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_CURY: inclinação PM z=-0.30 ⇒ α -0.34% a.a.
- [visões] BR_CVC: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_ECORODOVIAS: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_ENERGISA: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_ENEVA: inclinação AI z=-0.13 ⇒ α -0.13% a.a.
- [visões] BR_EQUATORIAL: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_EZTEC: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_FLEURY: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_GPA: inclinação AI z=-0.22 ⇒ α -0.52% a.a.
- [visões] BR_HAPVIDA: inclinação AI z=-0.26 ⇒ α -0.55% a.a.
- [visões] BR_IGUATEMI: inclinação AI z=+0.26 ⇒ α +0.24% a.a.
- [visões] BR_INTER: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_ISAENERGIA: inclinação PM z=+0.45 ⇒ α +0.37% a.a.
- [visões] BR_LOCALIZA: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_MAGALU: inclinação AI z=-0.26 ⇒ α -0.48% a.a.
- [visões] BR_MARCOPOLO: inclinação PM z=-0.30 ⇒ α -0.38% a.a.
- [visões] BR_MBRF: inclinação PM z=-0.30 ⇒ α -0.48% a.a.
- [visões] BR_MOURADUBEUX: inclinação PM z=+0.60 ⇒ α +0.75% a.a.
- [visões] BR_MOVIDA: inclinação AI z=+0.26 ⇒ α +0.42% a.a.
- [visões] BR_MRV: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_NATURA: inclinação PM z=+0.45 ⇒ α +0.66% a.a.
- [visões] BR_NU: inclinação PM z=+0.45 ⇒ α +0.45% a.a.
- [visões] BR_ONCOCLINICAS: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_PAGS: inclinação PM z=+0.45 ⇒ α +0.49% a.a.
- [visões] BR_PAGUEMENOS: inclinação PM z=+0.45 ⇒ α +0.64% a.a.
- [visões] BR_PATRIA: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_PETROBRAS: inclinação AI z=+0.13 ⇒ α +0.10% a.a.
- [visões] BR_PETZCOBASI: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_PICPAY: inclinação PM z=+0.30 ⇒ α +0.62% a.a.
- [visões] BR_RIACHUELO: inclinação PM z=+0.60 ⇒ α +0.77% a.a.
- [visões] BR_SABESP: inclinação PM z=+0.30 ⇒ α +0.24% a.a.
- [visões] BR_SANEPAR: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_SBF: inclinação PM z=+0.45 ⇒ α +0.55% a.a.
- [visões] BR_SIGMALITH: inclinação AI z=-0.26 ⇒ α -0.70% a.a.
- [visões] BR_SIMPAR: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_SMARTFIT: inclinação AI z=-0.11 ⇒ α -0.12% a.a.
- [visões] BR_STONE: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_SUZANO: inclinação AI z=+0.30 ⇒ α +0.28% a.a.
- [visões] BR_TENDA: inclinação PM z=+0.60 ⇒ α +0.86% a.a.
- [visões] BR_TUPY: inclinação AI z=+0.26 ⇒ α +0.37% a.a.
- [visões] BR_ULTRAPAR: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_UNIPAR: inclinação AI z=-0.22 ⇒ α -0.26% a.a.
- [visões] BR_VALE: inclinação AI z=-0.22 ⇒ α -0.18% a.a.
- [visões] BR_VAMOS: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_VIBRA: inclinação PM z=+0.30 ⇒ α +0.29% a.a.
- [visões] BR_WEG: inclinação PM z=+0.45 ⇒ α +0.42% a.a.
- [visões] BR_XP: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] BR_YDUQS: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] CL_LATAM: inclinação PM z=+0.45 ⇒ α +0.27% a.a.
- [visões] CL_SQM: inclinação PM z=-0.30 ⇒ α -0.27% a.a.
- [visões] CO_CIBEST: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] CO_GEOPARK: inclinação PM z=+0.45 ⇒ α +0.49% a.a.
- [visões] CO_GRANTIERRA: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] CO_TECNOGLASS: inclinação PM z=-0.30 ⇒ α -0.32% a.a.
- [visões] LA_MELI: inclinação PM z=+0.30 ⇒ α +0.29% a.a.
- [visões] LA_MILLICOM: inclinação PM z=+0.30 ⇒ α +0.24% a.a.
- [visões] MX_AMX: inclinação AI z=+0.22 ⇒ α +0.11% a.a.
- [visões] MX_CEMEX: inclinação PM z=+0.30 ⇒ α +0.20% a.a.
- [visões] MX_FEMSA: inclinação AI z=+0.00 ⇒ α +0.00% a.a.
- [visões] MX_PENOLES: inclinação AI z=+0.26 ⇒ α +0.20% a.a.
- [visões] MX_VOLARIS: inclinação PM z=-0.45 ⇒ α -0.44% a.a.
- [visões] MX_WALMEX: inclinação AI z=-0.26 ⇒ α -0.13% a.a.
- [visões] PE_BVN: inclinação PM z=+0.30 ⇒ α +0.20% a.a.
- [visões] PE_CREDICORP: inclinação PM z=+0.30 ⇒ α +0.18% a.a.
- [visões] PE_SCCO: inclinação PM z=-0.30 ⇒ α -0.14% a.a.
- [visões] BR_AFYA: visões proíbem compra e venda — posição limitada a zero.
- [visões] BR_YDUQS: visões proíbem compra e venda — posição limitada a zero.
- [visões] AR_ADECOAGRO: coerência de sinal com a visão negativa ⇒ no_long
- [visões] AR_CEPU: coerência de sinal com a visão positiva ⇒ no_short
- [visões] AR_YPF: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_3TENTOS: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_AURA: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_AXIA: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_BBSEG: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_BRADSAUDE: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_BRAVA: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_BTG: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_CMIN: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_CURY: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_ENEVA: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_GPA: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_HAPVIDA: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_IGUATEMI: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_ISAENERGIA: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_MAGALU: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_MARCOPOLO: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_MBRF: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_NU: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_SABESP: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_SIGMALITH: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_SMARTFIT: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_SUZANO: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_TENDA: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_UNIPAR: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_VALE: coerência de sinal com a visão negativa ⇒ no_long
- [visões] BR_VIBRA: coerência de sinal com a visão positiva ⇒ no_short
- [visões] BR_WEG: coerência de sinal com a visão positiva ⇒ no_short
- [visões] CL_LATAM: coerência de sinal com a visão positiva ⇒ no_short
- [visões] CL_SQM: coerência de sinal com a visão negativa ⇒ no_long
- [visões] CO_GEOPARK: coerência de sinal com a visão positiva ⇒ no_short
- [visões] CO_TECNOGLASS: coerência de sinal com a visão negativa ⇒ no_long
- [visões] LA_MELI: coerência de sinal com a visão positiva ⇒ no_short
- [visões] LA_MILLICOM: coerência de sinal com a visão positiva ⇒ no_short
- [visões] MX_AMX: coerência de sinal com a visão positiva ⇒ no_short
- [visões] MX_CEMEX: coerência de sinal com a visão positiva ⇒ no_short
- [visões] MX_PENOLES: coerência de sinal com a visão positiva ⇒ no_short
- [visões] MX_VOLARIS: coerência de sinal com a visão negativa ⇒ no_long
- [visões] MX_WALMEX: coerência de sinal com a visão negativa ⇒ no_long
- [visões] PE_BVN: coerência de sinal com a visão positiva ⇒ no_short
- [visões] PE_CREDICORP: coerência de sinal com a visão positiva ⇒ no_short
- [visões] PE_SCCO: coerência de sinal com a visão negativa ⇒ no_long
- [risco por nome] passo 1: BR_PETROBRAS com 15.71% da variância (limite 8.00%); teto max_long reduzido para 2.42%
- [risco por nome] passo 1: BR_TENDA com 15.56% da variância (limite 8.00%); teto max_long reduzido para 1.27%
- [risco por nome] passo 1: BR_SUZANO com 15.37% da variância (limite 8.00%); teto max_long reduzido para 1.97%
- [risco por nome] passo 1: LA_LILA com 11.05% da variância (limite 8.00%); teto max_short reduzido para 1.99%
- [risco por nome] passo 2: BR_JBS com 13.08% da variância (limite 8.00%); teto max_long reduzido para 1.63%
- [risco por nome] passo 2: BR_PAGS com 11.04% da variância (limite 8.00%); teto max_long reduzido para 1.62%
- [risco por nome] passo 2: BR_PETROBRAS com 10.33% da variância (limite 8.00%); teto max_long reduzido para 2.07%
- [risco por nome] passo 3: BR_PETROBRAS com 8.38% da variância (limite 8.00%); teto max_long reduzido para 1.96%
- [risco por nome] passo 3: BR_PAGS com 8.36% da variância (limite 8.00%); teto max_long reduzido para 1.54%
- [risco por nome] passo 3: BR_JBS com 8.26% da variância (limite 8.00%); teto max_long reduzido para 1.56%
- [risco por nome] passo 3: BR_TENDA com 8.20% da variância (limite 8.00%); teto max_long reduzido para 1.22%

## Decisões pendentes do gestor

- [ ] Dar ciência explícita às falhas SOFT: `GROSS_MIN` (Exposição bruta mínima).
- [ ] Validar shorts com risco de squeeze MEDIUM/HIGH: LA_DLOCAL (MEDIUM), BR_MBRF (MEDIUM).
- [ ] Confirmar locate/disponibilidade de aluguel para os 21 shorts antes da execução.
- [ ] Revisar as 156 nota(s) geradas por IA (citadas como fornecidas).
- [ ] Validar 45 restrição(ões) propostas por IA (sem short / sem long / teto de peso).
- [ ] Decidir sobre os hedges cambiais sugeridos: ARS, BRL, CLP, COP, MXN, PEN.
- [ ] Revisar observações/relaxamentos do otimizador.
- [ ] Obter co-assinatura independente de Risco/Compliance (quatro olhos): Falha(s) SOFT reconhecida(s): GROSS_MIN. Novo(s) short(s) com risco de squeeze: BR_MBRF (MEDIUM), LA_DLOCAL (MEDIUM). Vol ex-ante 3,13% fora de [4,00%, 6,00%].
- [ ] Aprovar ou rejeitar com justificativa — a decisão fica vinculada aos hashes de snapshot, configuração, pesquisa e proposta.

---

_Todos os números deste memo foram calculados e formatados por código a partir da proposta; textos de pesquisa são citados como fornecidos e rotulados pela origem._

---

_Hash da proposta (SHA-256): `8b5767db92806faa540d2d9bab71a32f6ed0ce695514d108b8f237bf73ef5dbb`_
