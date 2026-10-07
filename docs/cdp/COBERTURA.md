# Cobertura de ações e ETFs — modelos abertos e preços-alvo de 12 meses

Modelos quantitativos internos da gestão do CDP — Cabra da Peste; não constituem relatório de
análise nos termos da Resolução CVM 20/2021. Todos os números são calculados por código
determinístico e testado a partir de dados públicos; a camada de linguagem nunca calcula.

## 1. Escopo, horizonte e calendário

- **Universo**: todos os 233 emissores latino-americanos do universo investível e os ETFs ILF,
  EWZ, EWW, ECH, EPU, COLO, ARGT e BOVA11.
- **Horizonte**: preço-alvo de 12 meses a partir do fechamento de referência, com vencimento
  registrado no livro.
- **Calendário**: retrato-gênese no fechamento de quarta-feira, 2026-10-07. Em cada dia de
  montagem da carteira, atualização completa **antes da decisão**, com a base até o fechamento
  anterior; a decisão, a tese e o portal usam esses modelos atualizados. No último dia de
  montagem de cada mês, revisão aprofundada na rotina diária da noite (`cdp cobertura
  revisao-mensal preparar|validar|publicar --date D`), publicada na seção "Revisão mensal da
  cobertura" do portal. Resultados publicados depois do último modelo acionam atualização
  parcial por emissor no fechamento seguinte; eventos macro de alto impacto acionam retrato
  completo no primeiro fechamento que reagiu (`configs/cdp/cobertura/eventos_macro.yaml`).
- **Moeda**: cada emissor é avaliado na moeda da linha cotada na moeda das demonstrações
  (a ação local, em regra); os alvos das demais linhas (ADR, outras classes) derivam desse alvo
  pela inflação relativa esperada e pela quantidade de ações por linha. Emissores argentinos são
  avaliados na linha em dólar.

## 2. Dados públicos

| Insumo | Fonte | Observação |
|---|---|---|
| Demonstrações (DRE, BP, DFC, DVA) | CVM dados abertos (DFP/ITR); SEC EDGAR (XBRL); Yahoo Finance para não arquivadores | point-in-time: só o que estava publicado na data |
| Contas suplementares da CVM: principal de arrendamentos pago (DFC) e receita de construção (DVA) | ZIPs DFP/ITR da CVM arquivados pela camada pública, lidos pela cobertura | exercícios e 12 meses (exercício + acumulado do ano − acumulado do ano anterior); conta não encontrada ⇒ ausente |
| Consenso (LPA, receita, preços-alvo, recomendação) | Yahoo Finance ("consenso público Yahoo Finance") | retrato arquivado na data da coleta |
| Proventos | Yahoo Finance (data ex) | por linha |
| Taxa livre de risco em dólar | FRED, série DGS10 | diária |
| Prêmio de risco, risco-país, betas setoriais, inflação esperada, alíquotas, spreads por cobertura de juros | Damodaran (NYU Stern), versões datadas em `configs/cdp/valuation.yaml` | revisão semestral; ERP mensal |
| Contagem oficial de ações (capital social) | CVM, Formulário de Referência (dados abertos) | versão mais recente recebida até a data |
| Participações das holdings | CVM (Formulário de Referência), SEC (6-K/20-F), demonstrações e relatórios publicados pelas companhias | cada fração com documento, endereço e datas em `sotp.yaml` |
| Composição de ETFs | arquivos públicos iShares, Global X e B3 | por data de referência |
| Calendário de resultados | CVM (IPE, calendário de eventos corporativos), SEC, Yahoo | data estimada sinalizada |
| Preços e câmbio | base de mercado do fundo (fechamentos oficiais) | sempre o nosso fechamento, nunca múltiplos prontos |

Quando um documento SEC pendente está indisponível ou contém só fatos da capa, a coleta pode
usar seu XBRL publicado no RI oficial, conforme `configs/cdp/sec_ri_xbrl.json` (schema
`cdp.sec_ri_xbrl/v1`). O catálogo declara CIK, accession, formulário, documento SEC, data de
arquivamento, data-base, página do RI, URL, SHA-256 e, para ZIP, o membro XML exato. CIK e
metadados precisam conferir com SEC submissions no corte; o ZIP bruto fica arquivado com
proveniência e data de coleta. A leitura admite apenas tags padrão e totais sem dimensões,
não cria períodos pela data da capa e exclui fatos monetários posteriores à data-base. O
catálogo inicial cobre o 20-F de 2025 da Supervielle; os demais documentos indisponíveis
preservam o dado anterior e o diagnóstico da falha. Nenhuma data do catálogo substitui o
histórico SEC, e os resultados são reproduzíveis pelo cache offline.

Todo arquivo público baixado é arquivado com SHA-256; cada insumo de cada modelo carrega
fonte, endereço, documento, data de publicação (marcada como "data estimada" quando a fonte não
informa a data efetiva de divulgação), data de coleta e hash. Dado ausente nunca vira zero: o
insumo fica em branco, o método que dependia dele fica "indisponível" com o motivo e o modelo
lista a lacuna — por exemplo, sem participação de não controladores publicada no último balanço
(nem derivável como patrimônio total menos o dos controladores), os métodos pelo valor da firma
ficam indisponíveis. Fluxos de 12 meses com data-base mais de 100 dias anterior ao último balanço
geram aviso e lacuna. Instituições financeiras não usam crescimento de receita (a receita de
intermediação não é comparável entre fontes); o crescimento histórico fora de [−20%; +30%] (efeitos
contábeis, como receita de construção de concessões) não é usado.

- **Fluxos de 12 meses**: o TTM publicado; senão a soma dos 4 últimos trimestres consecutivos; senão
  a identidade "último exercício + acumulado do exercício corrente − acumulado do mesmo período do
  exercício anterior" (emissores cujas fontes não trazem todos os trimestres).
- **Consolidado × individual por período**: o consolidado prevalece em cada (item, frequência,
  data-base) em que existe; períodos só com as demonstrações individuais (companhia que deixou de
  consolidar) entram como individuais, registradas na proveniência — nunca um consolidado mais antigo no
  lugar de um individual mais recente. Patrimônio e lucro dos controladores, salvo quando o total tem
  data-base mais recente (o individual não separa não controladores). **Portão G19**: último balanço ou
  fluxos de 12 meses com mais de 300 dias na data ⇒ aviso (confiança C); mais de 550 dias ⇒ bloqueio.
- **Em conferência na fonte**: quando a camada pública marca o período mais recente de um item como
  "em conferência" (valor ausente, nunca um palpite), o item fica ausente, com lacuna e portão G17 —
  o valor do período anterior nunca é usado em silêncio.
- **Consenso**: a receita de consenso é convertida da sua própria moeda para a das demonstrações
  antes da razão com a receita de 12 meses; a proveniência registra o arquivo de estimativas e o
  arquivo de cotação (hash e data de coleta de cada um). Entre as linhas do emissor (classes, ADR),
  vale a de consenso de LPA com mais analistas quando o seu LPA convertido (ações por linha e câmbio da
  moeda das estimativas) fica a ±35% do da linha de valuation; o número de analistas é registrado.
  Consenso de LPA de menos de 2 analistas não define o ROE dos anos 1–2 (vale o lucro de 12 meses,
  sinalizado) e confiança A exige ≥ 3 analistas. O consenso é **calendarizado em 12 meses à
  frente** (no modelo, no contexto transversal e no prêmio implícito): com f = fração decorrida do
  exercício corrente, `LPA_1 = (1 − f) × LPA_FY1 + f × LPA_FY2`,
  `LPA_2 = (1 − f) × LPA_FY2 + f × LPA_FY3`, `LPA_FY3 = LPA_FY2 × (1 + (g_FY2 + g) ÷ 2)`; a receita, pela
  mesma regra. f segue o calendário do emissor: conta do último encerramento do exercício (mês do
  exercício publicado) até a data; se as demonstrações anuais desse exercício não estão no arquivo 120
  dias depois do encerramento, o calendário segue o encerramento esperado (o consenso já rolou) e o
  atraso é sinalizado.
- **Receita de construção (ICPC 01)**: em utilidades reguladas e concessões, a receita da DRE inclui
  a receita de construção da infraestrutura (margem ~zero) e o consenso de receita não. Com a receita
  de construção da DVA (CVM), a base de 12 meses passa a ser a receita sem ela quando isso reconcilia o
  consenso (crescimento ≤ 15% em módulo e menor que contra a receita total; margem e EV/Receita na
  mesma base); sem essa reconciliação, crescimento de consenso acima de 15% em módulo não é usado
  (lacuna; nem o do ano 2).
- **Proventos e payout**: payout aos acionistas do emissor pela mediana dos payouts anuais dos 3
  últimos exercícios com lucro (proventos por ação pagos no ano × N ÷ lucro dos controladores do
  exercício, cada um limitado a [0; 1]) — os dividendos consolidados da DFC incluem os pagos a não
  controladores de controladas e não são usados (diferença acima de 25% é anotada); a mediana descarta
  o ano de uma distribuição extraordinária; ano sem proventos por ação e com dividendos na DFC (lacuna
  da série de proventos) usa a DFC daquele exercício; com menos de 2 anos, proventos de 12 meses × N ÷
  lucro de 12 meses.
- **Contagem de ações conciliada**: demonstrações (÷ ações por unidade), valor de mercado público ÷
  fechamento e, no Brasil, o capital social do Formulário de Referência. Vale a contagem sustentada
  por duas das três fontes a ±10%; sem par, portão G13c bloqueia. Sem a fonte oficial, divergência
  acima de 25% entre demonstrações e mercado ⇒ contagem do mercado com aviso (confiança C).
- **Alertas da fonte pública** (saltos de magnitude, complementos descartados, troca da moeda de
  apresentação) entram arquivados no snapshot (`insumos/alertas_fonte`) e alimentam o portão G17.
  Emissor que trocou a moeda de apresentação fica só com os exercícios na moeda nova (os insumos
  históricos ficam ausentes abaixo de 3 exercícios).
- **Inflação**: a do modelo é a esperada de longo prazo de Damodaran (configuração datada); a série
  pública IPCA de 12 meses não é usada — se vier a ser, a chave point-in-time é a data de
  disponibilidade (fim do mês de referência + 12 dias), como a camada pública já a data.

## 3. Custo de capital

- `ke_USD = (UST10 − spread de default dos EUA) + β_aj × ERP + λ × CRP_país + δ`
- **ERP oficial = par contemporâneo de Damodaran** (prêmio implícito mensal e UST da mesma data:
  3,70% em 2026-10-01). O ERP estático da tabela semestral de julho (4,20%, implícito quando o UST era
  menor) somado ao UST de outubro dobraria o efeito da alta de juros: ele fica como **sensibilidade
  exibida de um fator** — `ke' = ke_USD oficial + β_aj × (4,20% − 3,70%)`, convertido como o ke, com o
  ajuste de nível do país e a norma de ROE mantidos (numa reestimação completa o ajuste de nível
  reabsorveria a maior parte do efeito, dentro do limite). Diferença de mais de 25 bp entre o UST do dia
  e o do par gera aviso no passo do ERP. Os valores de Damodaran e do FRED são transcritos na
  configuração datada: a proveniência traz o endereço e o documento, sem hash (a planilha não é arquivada
  no snapshot).
- **Ajuste de nível do modelo por país (`δ`)**: o deslocamento do ke em dólar que faz o emissor
  mediano do país valer o preço (mediana de `V0 ÷ P0` = 1 com as premissas da casa; ponto fixo — a
  mediana é recalculada com o δ aplicado até ficar a 0,1% de 1, no máximo 8 passadas —, limitado a
  ±1,5 p.p.; países com ao menos 8 emissores com preço-alvo). **Não é um prêmio de risco**: é o viés de
  nível dos fluxos do modelo no país (o mercado do país é tomado como apreçado na mediana); a carteira
  é neutra a país e o rating é relativo a país × setor. Os preços-alvo absolutos são, portanto,
  relativos ao mercado. A norma de longo prazo do ROE não depende de δ (o spread é estimado contra o
  ke sem o ajuste). Países com menos de 8 emissores recebem o ajuste regional — mediana ponderada pelo
  número de emissores dos δ dos países calibrados — e seus emissores ficam fora das medianas de pares
  de outros países. O indicador de viés monitorado é a mediana de `V0 ÷ P0` **sem** o ajuste (alerta
  fora de 0,85–1,15) e o ajuste no limite. O ke sem o ajuste e o ke com o prêmio implícito pelo consenso
  (agregado de Damodaran com LPA de consenso, payout em caixa e `g = rf local`, só emissores com recompra
  publicada, ≥ 8 por país; peso κ = 0 na inauguração porque o consenso de mercados emergentes é
  otimista; sensibilidade de um fator a partir do ke oficial) são exibidos.
- `β_aj = 0,67 × β + 0,33`, limitado a [0,5; 1,8]; não financeiras: `β = β_u × (1 + (1 − t) × D/E)`
  com o β desalavancado setorial de Damodaran (indústria mais próxima, em
  `configs/cdp/cobertura/betas_setor.csv`) e o D/E de mercado; financeiras: mediana dos betas de
  regressão semanal (104 semanas, em dólar, contra o ILF) dos pares, sem realavancar.
- `λ`: exposição ao risco-país pela origem da receita/produção (1 por padrão; exceções curadas em
  `arquetipos.csv`); emissores regionais usam o CRP ponderado pelo PIB da região.
- `ke_local = (1 + ke_USD)(1 + π_local)/(1 + π_EUA) − 1`; `ke_real = (1 + ke_local)/(1 + π_local) − 1`.
- `WACC = E/V × ke + D/V × kd × (1 − t)`, `kd = mín(rf + spread soberano + spread corporativo; ke)`
  (convertido como o ke); o spread corporativo vem do **rating sintético** (tabela de Damodaran de
  janeiro de 2026 para empresas não financeiras de grande porte) pela cobertura de juros em base dólar,
  `EBIT de 12 meses ÷ (dívida bruta com arrendamentos × (rf + spread soberano + 1,5%))` — nunca o
  resultado financeiro líquido (variação cambial, derivativos, correção monetária, receita de
  aplicações) nem juros nominais de moeda de inflação alta; caixa líquido, EBIT não positivo ou sem os
  itens ⇒ 1,5% de reserva. A dívida `D` — na realavancagem do β e nos pesos do WACC — é a dívida
  bruta mais os passivos de arrendamento (IFRS 16), a mesma definição da dívida líquida descontada
  do valor da firma.
- Crescimento na perpetuidade: `g = (1 + 2%)(1 + π_local) − 1`, limitado à taxa livre de risco
  local e a `ke − 3 p.p.`
- Sensibilidades exibidas (um fator cada): ke e preço-alvo com o ERP estático; ke sem o ajuste de nível;
  ke com o prêmio implícito pelo consenso.

## 4. Métodos por arquétipo

| Arquétipo | Métodos (pesos) |
|---|---|
| Banco | lucro residual 50%, P/VPA justificado 30%, P/VPA de regressão 20% |
| Seguradora | dividendos 40%, lucro residual 40%, P/L de regressão 20% |
| Utilidade regulada | lucro residual real 40%, dividendos reais 20%, fluxo de caixa real 20%, P/VPA de regressão 20% |
| Concessão | fluxo de caixa até o fim da concessão 70%, lucro residual 30% |
| Commodity | fluxo de caixa com margem ao longo do ciclo 60%, lucro residual 20%, EV/Receita de regressão 20% |
| Corporativo | fluxo de caixa 50%, lucro residual 25%, P/L justificado 25% |
| Imobiliário | lucro residual 60%, P/VPA de regressão 40% |
| Holding | soma das partes 100% |

Métodos indisponíveis saem da média e os pesos são renormalizados. **Combinação robusta (G18)**: com
três ou mais métodos válidos, o que ficar fora de [1/3; 3] × a mediana dos demais (o mais distante) é
**limitado à borda do intervalo** (por sorteio e ponto da grade) — nunca retirado: a combinação fica
monótona no valor de cada método (um custo da dívida maior nunca eleva o preço-alvo). Só se limita
quando os demais concordam (CV ≤ 10%) e o discrepante não está do lado do preço (dissidência a favor do
mercado fica na média). Em todos os casos a dissidência — o discrepante pelo valor bruto e os métodos
com valor do patrimônio não positivo, como zero — entra na dispersão usada na confiança e na
corroboração do G11.

- **Lucro residual (GLS)**: `V0 = B0 + Σ_{t=1..12} (ROE_t − ke) × B_{t−1}/(1 + ke)^t + (ROE_alvo − ke) ×
  B_12/(ke × (1 + ke)^12) + (ROE_12 − ROE_alvo) × B_12 × ω/((1 + ke − ω) × (1 + ke)^12)`; ROE dos anos
  1–2 pelo consenso calendarizado; depois **decaimento exponencial** ao ROE de convergência,
  `ROE_t = ROE_alvo + (ROE_2 − ROE_alvo) × ω^(t−2)`, que continua na perpetuidade (o desvio residual do
  ano 12 decai à razão ω; patrimônio constante a partir de `B_12`, convenção GLS); lucro limpo com
  payout que converge ao sustentável `1 − g/ROE_alvo`. **Termos reais** (utilidades): ROE e ke reais
  (Fisher) e patrimônio real deflacionado, `B^r_t = B^r_{t−1} × (1 + ROE_nominal × (1 − k)) ÷ (1 + π)` — o
  mesmo valor do modelo nominal nos anos explícitos, com a perpetuidade constante em termos reais; nos
  dividendos reais, o DPS do ano 1 em moeda de hoje (`÷ (1 + π)`).
- **Persistência do ROE por qualidade**: norma de longo prazo `= ke sem o ajuste de nível + s + a`, com
  `s` = mediana de (ROE de 5 anos − ke) dos emissores lucrativos da classe setor × arquétipo (≥ 8; senão
  setor, encolhido 50% para país × setor com ≥ 5), estimada a cada execução, e `a` = ajuste de porte:
  Theil–Sen do ROE de 5 anos contra o log do **patrimônio contábil** em dólar dentro do setor (nunca o
  valor de mercado, que traria o próprio preço do emissor de volta à norma), estimado a cada execução e
  aplicado só quando o intervalo de 95% exclui zero (limitado a [0; 0,04] e a ±5 p.p.; na execução de
  2026-10-06, não significativo ⇒ `a = 0`). `R̄ = média(ROE de 5 anos; ROE_2)`, limitado a [norma − 5 p.p.; norma + 15
  p.p.]; `ROE_alvo = norma + θ × (R̄ − norma)`. Classes pelo desvio-padrão do ROE dos últimos 5
  exercícios: estável (≤ 4 p.p., sem prejuízo) θ = 0,60 e ω = 0,85; normal θ = 0,35 e ω = 0,70;
  instável (> 12 p.p., algum prejuízo ou menos de 3 exercícios) θ = 0,15 e ω = 0,55 (política).
  Evidência: o painel de ROE dos emissores cobertos (histórico anual arquivado no snapshot) com a
  persistência do desvio ao setor reestimada a cada execução (`contexto.json`,
  `persistencia_roe_painel`: `ρ_k = θ + (1 − θ)ω^k`; em 2026-10-06, 1.082 emissor-anos, θ ≈ 0,33 e
  ω ≈ 0,43 no conjunto); Fama & French (2000), Dechow, Hutton & Sloan (1999), Nissim & Penman (2001).
- **P/VPA justificado**: `(ROE_sust − g)/(ke − g) × B0`; **P/L justificado** com crescimento
  extraordinário de curto prazo (modelo H de Fuller e Hsia): `(1 − g/ROE_sust)/(ke − g) × LPA_1 × (1 +
  H × (g_c − g)/(1 + g))`, `g_c = LPA_2 ÷ LPA_1 − 1` limitado a [g; 25%], `H = mín(0,5 ÷ (1 − φ); 8)`
  anos (metade da duração equivalente do crescimento com a persistência φ do setor).
- **Dividendos**: dois estágios (5 anos a `ROE_sust × (1 − k)`, depois `g`).
- **Fluxo de caixa livre da firma**: anos 1–2 pelo consenso de receita calendarizado, anos 3–10 com
  convergência geométrica do crescimento (persistência setorial φ); margem EBIT corrente; nas
  commodities, a margem corrente reverte à mediana do ciclo com o mesmo perfil do choque de preço
  (plena nos anos 1–3, linear até o ano 5, perpetuidade na margem do ciclo). Reinvestimento ancorado no
  observado: nos anos 1–2, `1 − Σ(CFO − capex) ÷ Σ(EBIT × (1 − t))` dos 3 últimos exercícios (12
  meses sem eles), com o **principal de arrendamentos pago** (IFRS 16: na DFC de financiamento; a
  reposição dos ativos arrendados não passa pelo capex) descontado do fluxo quando publicado em todos
  os períodos (contas da DFC da CVM; sem ele, lacuna); abaixo de −100% (CFO com operações financeiras,
  como recebíveis de cartão ou banco cativo) vale a mediana do setor, com aviso G14; dos anos 3 a 10, convergência
  linear para `g ÷ RONIC`, com o RONIC convergindo do ROIC corrente ao retorno de longo prazo
  (média do ROIC próprio e do setor, nunca abaixo do WACC); limitado a [−50%; 95%] do NOPAT, com
  os anos limitados sinalizados. Perpetuidade pelo direcionador de valor
  `NOPAT × (1 − g/RONIC)/(WACC − g)`; concessões sem perpetuidade até o fim do prazo, com o
  crescimento real e o reinvestimento líquido convergindo a zero no último terço (sem renovação nem
  indenização); `V0 = (EV − dívida líquida) × PL dos controladores ÷ (PL dos controladores +
  minoritários) ÷ ações` — participação de não controladores a valor proporcional ao do patrimônio,
  não pelo valor contábil. O modelo aberto mostra o FCFF do ano 1 contra o fluxo de caixa livre
  observado.
- **Múltiplos de regressão**: regressões transversais robustas (Huber) com efeito fixo de país,
  `P/VPA ~ ROE + g + β + payout`, `P/L ~ g + payout + β`, `EV/Receita ~ margem + g + alavancagem`;
  regressores limitados à faixa da projeção; múltiplo previsto limitado ao P5–P95 dos múltiplos da
  amostra; regressão com R² abaixo de 0,25 fica indisponível. O modelo aberto mostra os
  coeficientes, os valores do emissor e o efeito país.
- **Soma das partes**: participações listadas a valor de mercado, ou ao **valor intrínseco da casa**
  (`V0 ÷ P0` da investida) quando o modelo da investida é citável com confiança A ou B e sem aviso de
  retorno extremo, patrimônio frágil ou demonstrações defasadas — a holding herda a visão da casa sobre a
  mesma exposição (fator `NAV da casa ÷ NAV de mercado` no modelo aberto); desconto da holding pela
  mediana semanal de 5 anos de (valor de mercado ÷ NAV) — invariante a erro proporcional
  constante na fração da participação; a janela começa na última mudança do conjunto de
  participações (`desde` curado em `sotp.yaml`) ou na última variação de mais de 5% das ações da
  holding fora de desdobramentos (detectada em código); abaixo de 52 semanas, desconto de reserva
  sinalizado. Cada fração cita o documento público (Formulário de Referência, 6-K/20-F,
  demonstrações), com datas; a conferência cruzada com a posição acionária no documento da investida
  (`fracao_investida`) é feita em código, com tolerância de 1 p.p. (`participacao_tolerancia`): acima
  dela, a participação não é conferida. Com todas
  as frações conferidas e ≥ 52 semanas de histórico a holding pode ter confiança B; senão C.
  Metalúrgica Gerdau e Simpar são holdings (soma das partes).
- **Diagnósticos**: custo de capital implícito (GLS, Easton, Gode–Mohanram, Claus–Thomas) e
  ROE implícito no preço (`g + P/VPA × (ke − g)`).

## 5. Preço-alvo, cenários e alpha

- `V0 = Σ w_m V_m / Σ w_m`; `TP12 = V0 × (1 + ke) − DPS12`; `ETR = (TP12 + DPS12)/P0 − 1`.
- **Cenários**: Monte Carlo de 2.000 sorteios por instrumento, reprodutíveis com semente fixa
  por emissor e data, com choques de média zero nos direcionadores: ke ± 0,5 p.p. (no WACC, pela
  fração de capital próprio), g ± 0,25 p.p., ROE ± 3 p.p. nos anos 1–2 (convergindo ao ROE de
  longo prazo), crescimento (σ setorial limitado a [3%; 5%], persistente pelo fade φ) e margem
  correlacionados (ρ = 0,3), preço da commodity ± 20% transitório (anos 1–3, revertendo até o
  ano 5, sem efeito na perpetuidade), desconto da holding ± 5 p.p. O modelo de cada sorteio
  preserva a média do caso-base: a receita do sorteio é a do caso-base mais o desvio acumulado de
  crescimento (aditivo), choques de margem incidem sobre a receita-base, o reinvestimento
  acompanha o crescimento adicional de forma simétrica (`ΔI_t = margem × (1 − t) × (ΔR_{t+1} − ΔR_t)
  ÷ máx(RONIC_t; WACC)`) e o P/L justificado responde ao ROE em primeira ordem; o piso de zero
  (responsabilidade limitada) vale só para o valor combinado do patrimônio. A diferença entre o
  retorno ponderado e o do caso-base fica restrita à convexidade das fórmulas e ao piso de zero.
  Pessimista = P10, otimista = P90 do preço-alvo simulado.
- **Retorno ponderado por probabilidade**: `PWR = média dos retornos simulados` **sem o piso de
  zero** (os sorteios são incerteza de parâmetros em torno do caso-base, não valores terminais; com o
  piso, a massa em zero inflaria a média de emissores alavancados); o retorno com responsabilidade
  limitada (com o piso) e a probabilidade de patrimônio não positivo são exibidos à parte (G16);
  **alpha** `α = PWR − ke`; `α_rel = α − mediana(α dos pares)`.
- **Probabilidade implícita pelo mercado** (exibida, não usada no alpha): lognormal com drift
  `ke − DY` e a volatilidade realizada de 12 meses.
- **Sensibilidade**: grade 5 × 5 do preço-alvo (ke × g; ke × ROE para financeiras; ke × preço da
  commodity para commodities).
- **Ponte do alvo** entre snapshots: rolagem → estimativas → parâmetros → estrutura de capital
  → câmbio → preço → mix de métodos → resíduo, com o motivo dominante.

## 6. Rating (12 meses, relativo aos pares)

- **Compra**: `α_rel ≥ τ`, `α_rel_estilo ≥ τ/2`, `α ≥ 0` e, no caso-base, `ETR ≥ ke` e upside
  positivo; confiança A ou B.
- **Venda**: `α_rel ≤ −τ`, `α_rel_estilo ≤ −τ/2`, `α ≤ −5 p.p.` e, no caso-base, `ETR ≤ ke − 5 p.p.`;
  confiança A ou B.
- **Exposição de estilo explícita**: a cada execução, `b̂` = inclinação de Theil–Sen de `α_rel`
  contra `Δln(P/VPA)` (desvio da mediana do grupo de pares) e `α_rel_estilo = α_rel − b̂ × Δln(P/VPA)`;
  a dupla condição impede que um rating publicado seja só uma aposta em P/VPA. `b̂` e a correlação de
  postos entram no manifesto como "exposição de estilo do rating".
- Quando o limiar é atingido mas uma guarda ou a confiança impede o rating, o motivo publicado
  diz qual.
- **Neutro**: demais casos. **Em revisão**: um portão de qualidade bloqueante.
  **Sem preço-alvo**: nenhum método com insumos suficientes (com a lista de lacunas).
- `τ` pela incerteza (quartis da largura dos cenários no universo): Baixa 8%, Média 10%, Alta
  15%, Muito alta 20%. Histerese de 2 p.p. para quem já tem o rating. Pares: país × setor com ao
  menos 5 nomes; senão setor; senão país; senão o universo. Emissores bloqueados, com retorno extremo
  (G11), patrimônio residual frágil (G16) ou demonstrações defasadas (G19) não entram na mediana dos
  pares; emissores de países com o ajuste de nível regional não entram na de outros países.
- **Confiança**: A — três ou mais métodos, insumos point-in-time (publicados até a data, sem
  datas de publicação estimadas), moeda sem correção, dispersão entre **todos os métodos calculados**
  (com a dissidência: discrepante pelo valor bruto, não positivos como zero) ≤ 25%, nenhuma
  dissidência nem aviso de qualidade e consenso de LPA de ≥ 3 analistas; C — método único, dispersão
  > 50%, avisos de qualidade, Argentina ou holding com participações não conferidas ou sem 52 semanas
  de histórico do desconto; B — demais casos com preço-alvo (G15, data-base dos fluxos, G18, método
  discrepante limitado ou mantido, a dissidência do método principal do arquétipo e o consenso de
  menos de 3 analistas limitam a B).
- Numa execução parcial (após resultados), os pares não reavaliados entram na mediana dos pares
  com o α publicado no último snapshot que os cobriu.
- A distribuição de ratings é monitorada (faixas de 15–35% para Compra e Venda entre os nomes
  publicáveis) e nunca forçada.
  Indicadores de calibração no manifesto: mediana de α por país (alerta fora de ±5 p.p.; centrada por
  construção quando o ajuste de nível não está no limite), o viés de nível do modelo por país (mediana
  de V0 ÷ P0 sem o ajuste, alerta fora de 0,85–1,15, e o ajuste no limite), fração "Em revisão" (alerta
  acima de 12%), fração com confiança C (alerta acima de 35%) e a exposição de estilo.
- ETFs: retorno esperado combinado (bottom-up pelos alvos da casa + top-down por P/L justificado
  e Grinold–Kroner) e visão relativa ao ILF por `IR = (R_e − R_ILF)/TE` (±0,3). No bottom-up entram só
  os alvos citáveis da casa com confiança A ou B e sem aviso de retorno extremo (G11), patrimônio frágil
  (G16) ou demonstrações defasadas (G19); as demais posições recebem o retorno top-down do próprio ETF
  (imputadas). Portão E5 (aviso): nenhuma posição contribui mais que 5 p.p. ao bottom-up além do
  top-down (`w × (r − R_TD)`). O P/L justificado
  do índice usa o payout sustentável `b = 1 − g/ROE_índice` (lucro e patrimônio agregados das
  posições), limitado a [0,6; 1,6] × o P/L corrente; num índice em regime estacionário a reversão
  do P/L é nula. Portão bloqueante ⇒ visão "Em revisão".
  A ficha e a memória de cálculo identificam explicitamente o índice de referência, com fonte
  pública e configuração arquivada: BOVA11 — Ibovespa; EWZ — MSCI Brazil 25/50; EWW — MSCI Mexico
  IMI 25/50; ECH — MSCI Chile IMI 25/50; EPU — MSCI All Peru Capped; COLO — MSCI All Colombia
  Select 25/50; ARGT — MSCI All Argentina 25/50; ILF — S&P Latin America 40. O modelo do índice
  aparece pelos fundamentos agregados e pelo retorno top-down; o preço-alvo é expresso na cota
  do ETF que o acompanha. Fichas em revisão ou sem preço-alvo continuam visíveis com as lacunas.
- Linhas do mesmo emissor na mesma moeda (outras classes ou units) recebem o alvo pela razão
  corrente de preços entre as classes; linhas em outra moeda, pelo câmbio esperado em 12 meses
  (paridade de inflação) e pela quantidade de ações por linha.

## 7. Portões de qualidade

G1 identidade PL = controladores + minoritários (aviso; EBITDA = EBIT + D&A e FCF = CFO − capex são
informativos, porque o modelo parte do EBIT e de CFO − capex); G2 nenhum insumo publicado depois da
data (bloqueio); G3 valor finito; G4 ke no envelope P10–P90 dos demais emissores do país × setor, ± 1
p.p. (informativo); G5 valor terminal ≤ 85% (aviso; acima de 95% o método é excluído); G6 otimista ≥
base ≥ pessimista (bloqueio); G7 resíduo da ponte ≤ 0,5% (aviso; avaliado antes do rating); G8
coerência de moeda (bloqueio); G9 upside em [−70%; +200%] (bloqueio; a única faixa de magnitude
bloqueante); G10 largura dos cenários (informativo); **G11 retorno extremo no caso-base, simétrico em
log**: fora de [−50%; +100%] o alvo só é citável (aviso, confiança C, fora da mediana dos pares) se
corroborado — por ≥ 3 métodos calculados (inclusive o discrepante limitado e os não positivos, como
dissidência) todos do mesmo lado do preço com CV ≤ 50%, ou pelo consenso público plausível do mesmo
lado com upside em módulo ≥ 25% e magnitude compatível (`||ln(1 + ETR)| − |ln(1 + upside)|| ≤ 0,4`);
sem corroboração ⇒ bloqueio; G12 preço com até 5 pregões de defasagem (bloqueio); G13
insumos por ação plausíveis — P/VPA em [0,1; 15], ROE do ano 1 até 100% em módulo e LPA de consenso
coerente com o lucro de 12 meses quando métodos patrimoniais pesam mais de 50% (bloqueio); **G13b**
LPA de consenso ÷ preço ≤ 50% nos anos 1 e 2, ROE do ano 2 ≤ 100% em módulo e margem EBIT ≤ 100% fora
de holdings e imobiliárias (bloqueio); **G13c** contagem de ações conciliada (bloqueio sem par entre
três fontes; aviso quando só duas divergem); **G14** reinvestimento observado acima de −100% do NOPAT
(aviso abaixo; o FCFF do ano 1 contra o fluxo observado é exibido); G15 fluxos e balanço na mesma
data-base (aviso, limita a B); **G16** probabilidade de patrimônio não positivo nos sorteios < 10%
(aviso); **G17** alertas da fonte pública sobre os períodos e itens usados (item em conferência,
salto de magnitude em item central, troca recente da moeda de apresentação: aviso; demais alertas
informativos); **G18** métodos coerentes (método discrepante limitado à borda ou mantido; aviso,
limita a B); **G19** demonstrações recentes (último balanço ou fluxos de 12 meses com mais de 300 dias
na data: aviso; mais de 550 dias: bloqueio); **G20** plausibilidade do alvo, com revisão analítica
sem ancorar a visão da casa no consenso.

No G20, alvo mais de 25% além do maior ou aquém do menor alvo do consenso público de pelo menos
3 analistas, ou retorno a menos de 5% do limite do G11, é sinal de revisão. Havendo pelo menos
2 métodos distintos do mesmo lado do preço que o alvo e coeficiente de variação ≤ 50% entre
**todos os valores brutos calculados**, o sinal é informativo e não rebaixa a confiança. Sem essa
corroboração, é aviso e limita a C. Valores limitados na combinação e métodos não positivos
continuam no cálculo da dispersão; repetir um método não conta como outra corroboração.

P10 acima do preço ou P90 abaixo dele, isoladamente, não torna um cenário implausível. A faixa
unilateral gera aviso somente com bloqueio dos insumos (G1, G8, G13, G13b, G13c ou G14) ou falha
comprovada da simulação: método do caso-base omitido, sorteio não finito ou choque zero que não
reproduz o alvo. O diagnóstico é gravado no modelo aberto. Os percentis não são deslocados para
envolver o preço. Avisos de conferência, como salto de magnitude (G17) ou contagem disponível de
uma fonte (G13c), continuam em seus próprios portões e não comprovam erro do cenário. As
configurações anteriores preservam sua regra no recálculo histórico.

No retrato real, monitoram-se Compra e Venda, cada uma entre 15% e 35% dos nomes publicáveis,
confiança C até 35% e Em revisão até 12% do universo de empresas, com motivos por emissor. São
critérios de validação, jamais cotas impostas aos ratings; teste sintético não comprova a
distribuição de um retrato real.
Bloqueio ⇒ "Em revisão": o preço-alvo existe no modelo aberto para auditoria, mas não é publicado na
tabela, não é citável nos fatos da pesquisa e não entra no placar; o motivo publicado cita o portão e
o número que o disparou.

## 8. Uso no alpha da carteira

O sinal `valuation_gap` (z de `α_rel_estilo` — o α relativo sem a exposição a P/VPA — dentro de
país × setor, winsorizado em ±3) e a tradução de
Grinold `α = IC × m_incerteza × m_confiança × m_frescor × σ_específica × z` são calculados em
sombra, com peso zero. O upside bruto do preço-alvo nunca entra no otimizador. Promoção somente
com IC residual semanal sem sobreposição, em 26 semanas ou mais, IC médio ≥ 0,01 e t de
Newey–West ≥ 1,5, com rebaixamento automático.

## 9. Placar de acertos

Por previsão: atingiu o alvo no vencimento (`1[d × (P_H − TP) ≥ 0]`, d = sentido do alvo),
atingiu em algum momento, erro assinado `P_H/TP − 1`, tempo até o alvo (Kaplan–Meier), com o
caminho de preços reescalado pelos desdobramentos e grupamentos registrados no livro. No corte
transversal: IC de postos de `α_rel` contra o retorno total em dólar da semana seguinte
residualizado dentro de país × setor (retorno menos a média do grupo; grupos com menos de 3 nomes
usam o país), só entre snapshots completos consecutivos (execuções parciais não interrompem a
semana), com média, ICIR e t de Newey–West. Intervalos de 90% (Wilson) em toda taxa; nada é exibido abaixo de 20
previsões vencidas, nenhum ranking abaixo de 30; "em maturação" até o primeiro vencimento.
Referências da literatura: 24–38% dos alvos atingidos no vencimento, 45–64% em algum momento,
erro absoluto de 36–45%.

## 10. Auditoria e reprodução

Cada snapshot (`book/cobertura/<D>/`) guarda o modelo aberto de cada instrumento — insumos com
fonte e hash, lacunas, cada passo com a fórmula e a mesma fórmula com os números usados,
métodos, combinação, rolagem, cenários, sensibilidade, rating e portões —, as tabelas públicas
da execução, os pacotes de insumos normalizados, o contexto transversal, a cópia da
configuração usada, o placar e um manifesto com o SHA-256 de cada arquivo, as versões de
Python, numpy, pandas e scipy e a versão do código. O livro `book/cobertura/livro.jsonl` é
encadeado por hash (um evento por instrumento por execução: iniciação, reiteração, revisão,
mudança de rating, suspensão, retomada, encerramento) e cada snapshot é selado na trilha de
auditoria do fundo.

Para conferir e reproduzir:

```
uv sync
uv run python -m cdp cobertura verify     # livro, selos, trilha, arquivos, placar e recálculo completo
# refazer os modelos a partir do arquivo público, num livro de trabalho separado:
uv run python -m cdp --book /tmp/livro-trabalho cobertura run --date AAAA-MM-DD --offline --raiz <pasta com publico/>
```

O livro de trabalho começa sem histórico: os preços-alvo, cenários e α de cada emissor coincidem
com os publicados (dependem só dos insumos, do contexto e da taxa livre de risco da data); o
rating pode diferir onde a histerese ou a ponte do alvo contra o snapshot anterior pesaram.
Nunca se executa `run` sobre o livro publicado para conferir: a data já coberta é recusada antes
do cálculo.

`verify` é versionado pela metodologia: refaz por completo os snapshots gravados com a versão da
configuração do repositório (`versao` de `valuation.yaml`, que sobe a cada mudança de metodologia); dos
gravados com outra versão confere hashes, livro, selos, trilha e placar e indica o recálculo como nota
("metodologia X: recálculo exige o código da versão X (git <sha>)"), sem falhar. `verify` exige que o
livro termine exatamente no último selo, que cada selo corresponda a um
evento da trilha do fundo (e vice-versa) e que os eventos de cada snapshot (`eventos.jsonl`)
coincidam com o livro; refaz os snapshots da versão corrente a partir dos insumos e da configuração
arquivados — contexto transversal, custo de capital (inclusive ke sem o ajuste, ke estático e prêmio
implícito), métodos, cenários com semente, PWR com e sem o piso, probabilidade de patrimônio não
positivo, α, α relativo e sem a exposição de estilo, preço-alvo com o ERP estático, confiança, rating e
ETFs — e confere a tabela pública `modelos.csv` (a que o sinal lê) contra o recálculo. A tolerância é relativa de 1e-5 (os números são armazenados com 6
algarismos significativos). Recalcular em outra plataforma pode diferir na sexta casa por
diferenças de biblioteca numérica; o hash dos arquivos arquivados é sempre exato. A execução
recusa, antes de calcular, uma data já coberta ou anterior ao último snapshot.

## 11. Limitações conhecidas

- Consenso público e parte das demonstrações de emissores fora da CVM/SEC vêm do Yahoo Finance;
  datas de publicação estimadas são sinalizadas.
- Emissores com demonstrações em moedas sem câmbio na base (sol peruano, dólar canadense) ficam
  sem preço-alvo até a inclusão da série pública de câmbio.
- Emissores com prejuízo recente ou patrimônio residual pequeno tendem a valores extremos; os
  portões G9, G11, G13 e G16 os colocam "Em revisão" ou em confiança C em vez de publicar um alvo
  implausível. O valor de opção do patrimônio de empresas muito alavancadas não é modelado. Com o custo
  da dívida em base dólar (convertido pela inflação de longo prazo, como o ke), o WACC de empresas muito
  alavancadas fica baixo e o patrimônio residual do fluxo de caixa, frágil: esses alvos tendem a G9/G11
  ("Em revisão") em vez de serem publicados.
- O ajuste de porte do ROE só existe quando o porte contábil o sustenta; sem ele, a visão de taxa de
  base sobre franquias de alta rentabilidade (persistência mais curta que a precificada) pesa mais
  nos grandes emissores de P/VPA alto.
- Visão da casa (taxa de base): a persistência do ROE é mais curta que a precificada pelo mercado
  para franquias de alta rentabilidade; a dupla condição de estilo e o rating relativo mantêm essa
  visão explícita, sem transformá-la em aposta de P/VPA.
- Concessões com prazo curado são avaliadas sem renovação nem indenização (premissa conservadora).
- O ajuste de nível por país centra o emissor mediano no preço (preços-alvo absolutos relativos ao
  mercado); a Argentina (trilha em dólar, contabilidade com inflação) fica no limite de ±1,5 p.p. e
  segue com confiança C; países com menos de 8 emissores usam o ajuste regional.
- Contas suplementares (principal de arrendamentos, receita de construção) só existem para emissores
  da CVM; para os demais, o fluxo observado não desconta a reposição de ativos arrendados (lacuna).
- Betas setoriais usam a indústria de Damodaran mais próxima da tabela curada; o β de regressão
  é exibido como diagnóstico.
- Frações das participações das holdings citam o documento-fonte; quando a fração da holding e a
  posição acionária da investida divergem mais de 1 p.p. (Simpar, conferência cruzada em código), a
  holding fica com confiança C.
- O prazo das concessões (`fim_concessao`) cita o documento público em `arquetipos.csv`; a Rumo usa o
  prazo da Malha Paulista (2058), por onde o corredor Norte chega a Santos (premissa conservadora).
