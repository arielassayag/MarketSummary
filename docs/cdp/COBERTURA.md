# Cobertura de ações e ETFs — modelos abertos e preços-alvo de 12 meses

Modelos quantitativos internos da gestão do CDP — Cabra da Peste; não constituem relatório de
análise nos termos da Resolução CVM 20/2021. Todos os números são calculados por código
determinístico e testado a partir de dados públicos; a camada de linguagem nunca calcula.

## 1. Escopo, horizonte e calendário

- **Universo**: todos os 233 emissores latino-americanos do universo investível e os ETFs ILF,
  EWZ, EWW, ECH, EPU, COLO, ARGT e BOVA11.
- **Horizonte**: preço-alvo de 12 meses a partir do fechamento de referência, com vencimento
  registrado no livro.
- **Calendário**: execução completa nas noites dos pregões de rebalanceamento (depois do
  fechamento) e execuções parciais por emissor em até dois pregões depois de cada divulgação de
  resultados. O snapshot da data `D` alimenta somente a decisão seguinte. Primeiro snapshot: fechamento
  de quinta-feira, 2026-10-08.
- **Moeda**: cada emissor é avaliado na moeda da linha cotada na moeda das demonstrações
  (a ação local, em regra); os alvos das demais linhas (ADR, outras classes) derivam desse alvo
  pela inflação relativa esperada e pela quantidade de ações por linha. Emissores argentinos são
  avaliados na linha em dólar.

## 2. Dados públicos

| Insumo | Fonte | Observação |
|---|---|---|
| Demonstrações (DRE, BP, DFC, DVA) | CVM dados abertos (DFP/ITR); SEC EDGAR (XBRL); Yahoo Finance para não arquivadores | point-in-time: só o que estava publicado na data |
| Consenso (LPA, receita, preços-alvo, recomendação) | Yahoo Finance ("consenso público Yahoo Finance") | retrato arquivado na data da coleta |
| Proventos | Yahoo Finance (data ex) | por linha |
| Taxa livre de risco em dólar | FRED, série DGS10 | diária |
| Prêmio de risco, risco-país, betas setoriais, inflação esperada, alíquotas | Damodaran (NYU Stern), versões datadas em `configs/cdp/valuation.yaml` | revisão semestral |
| Composição de ETFs | arquivos públicos iShares, Global X e B3 | por data de referência |
| Calendário de resultados | CVM (IPE, calendário de eventos corporativos), SEC, Yahoo | data estimada sinalizada |
| Preços e câmbio | base de mercado do fundo (fechamentos oficiais) | sempre o nosso fechamento, nunca múltiplos prontos |

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

## 3. Custo de capital

- `ke_USD = (UST10 − spread de default dos EUA) + β_aj × ERP + λ × CRP_país`
- `β_aj = 0,67 × β + 0,33`, limitado a [0,5; 1,8]; não financeiras: `β = β_u × (1 + (1 − t) × D/E)`
  com o β desalavancado setorial de Damodaran (indústria mais próxima, em
  `configs/cdp/cobertura/betas_setor.csv`) e o D/E de mercado; financeiras: mediana dos betas de
  regressão semanal (104 semanas, em dólar, contra o ILF) dos pares, sem realavancar.
- `λ`: exposição ao risco-país pela origem da receita/produção (1 por padrão; exceções curadas em
  `arquetipos.csv`); emissores regionais usam o CRP ponderado pelo PIB da região.
- `ke_local = (1 + ke_USD)(1 + π_local)/(1 + π_EUA) − 1`; `ke_real = (1 + ke_local)/(1 + π_local) − 1`.
- `WACC = E/V × ke + D/V × kd × (1 − t)`, `kd = rf + spread soberano + spread corporativo`
  (convertido como o ke). A dívida `D` — na realavancagem do β e nos pesos do WACC — é a dívida
  bruta mais os passivos de arrendamento (IFRS 16), a mesma definição da dívida líquida descontada
  do valor da firma.
- Crescimento na perpetuidade: `g = (1 + 2%)(1 + π_local) − 1`, limitado à taxa livre de risco
  local e a `ke − 3 p.p.`
- Sensibilidade exibida: ke com o prêmio de risco contemporâneo (série mensal de Damodaran).

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

Métodos indisponíveis saem da média e os pesos são renormalizados.

- **Lucro residual (GLS)**: `V0 = B0 + Σ_{t=1..12} (ROE_t − ke) × B_{t−1}/(1 + ke)^t + (ROE_alvo − ke) × B_12/(ke × (1 + ke)^12)`;
  ROE dos anos 1–2 pelo consenso; convergência linear ao ROE de longo prazo do setor (mediana
  histórica dos emissores lucrativos, encolhida para país × setor e combinada com o histórico do
  próprio emissor); lucro limpo com payout que converge ao sustentável `1 − g/ROE_alvo`.
- **P/VPA justificado**: `(ROE_sust − g)/(ke − g) × B0`; **P/L justificado**: `(1 − g/ROE_sust)/(ke − g) × LPA_1`.
- **Dividendos**: dois estágios (5 anos a `ROE_sust × (1 − k)`, depois `g`).
- **Fluxo de caixa livre da firma**: anos 1–2 pelo consenso de receita, anos 3–10 com
  convergência geométrica do crescimento (persistência setorial φ); margem EBIT corrente (ou
  mediana do ciclo para commodities). Reinvestimento ancorado no observado: nos anos 1–2,
  `1 − (CFO − capex) ÷ (EBIT × (1 − t))` do último exercício; dos anos 3 a 10, convergência
  linear para `g ÷ RONIC`, com o RONIC convergindo do ROIC corrente ao retorno de longo prazo
  (média do ROIC próprio e do setor, nunca abaixo do WACC); limitado a [−50%; 95%] do NOPAT, com
  os anos limitados sinalizados. Perpetuidade pelo direcionador de valor
  `NOPAT × (1 − g/RONIC)/(WACC − g)`; concessões sem perpetuidade até o fim do prazo;
  `V0 = (EV − dívida líquida − não controladores)/ações`. O modelo aberto mostra o FCFF do ano 1
  contra o fluxo de caixa livre observado.
- **Múltiplos de regressão**: regressões transversais robustas (Huber) com efeito fixo de país,
  `P/VPA ~ ROE + g + β + payout`, `P/L ~ g + payout + β`, `EV/Receita ~ margem + g + alavancagem`;
  regressores limitados à faixa da projeção; regressão com R² abaixo de 0,25 fica indisponível. O
  modelo aberto mostra os coeficientes, os valores do emissor e o efeito país.
- **Soma das partes**: participações listadas a valor de mercado; desconto da holding pela
  mediana semanal de 5 anos de (valor de mercado ÷ NAV) — invariante a erro proporcional
  constante na fração da participação; a janela começa na última mudança do conjunto de
  participações quando curada (`desde` em `sotp.yaml`). Enquanto as frações não forem conferidas
  no documento-fonte, a holding tem confiança C (sem Compra ou Venda).
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
- **Retorno ponderado por probabilidade**: `PWR = média dos retornos simulados`;
  **alpha** `α = PWR − ke`; `α_rel = α − mediana(α dos pares)`.
- **Probabilidade implícita pelo mercado** (exibida, não usada no alpha): lognormal com drift
  `ke − DY` e a volatilidade realizada de 12 meses.
- **Sensibilidade**: grade 5 × 5 do preço-alvo (ke × g; ke × ROE para financeiras; ke × preço da
  commodity para commodities).
- **Ponte do alvo** entre snapshots: rolagem → estimativas → parâmetros → estrutura de capital
  → câmbio → preço → mix de métodos → resíduo, com o motivo dominante.

## 6. Rating (12 meses, relativo aos pares)

- **Compra**: `α_rel ≥ τ`, `α ≥ 0` e, no caso-base, `ETR ≥ ke` e upside positivo; confiança A ou B.
- **Venda**: `α_rel ≤ −τ`, `α ≤ −5 p.p.` e, no caso-base, `ETR ≤ ke − 5 p.p.`; confiança A ou B.
- Quando o limiar é atingido mas uma guarda ou a confiança impede o rating, o motivo publicado
  diz qual.
- **Neutro**: demais casos. **Em revisão**: um portão de qualidade bloqueante.
  **Sem preço-alvo**: nenhum método com insumos suficientes (com a lista de lacunas).
- `τ` pela incerteza (quartis da largura dos cenários no universo): Baixa 8%, Média 10%, Alta
  15%, Muito alta 20%. Histerese de 2 p.p. para quem já tem o rating. Pares: país × setor com ao
  menos 5 nomes; senão setor; senão país; senão o universo.
- **Confiança**: A — três ou mais métodos, insumos point-in-time (publicados até a data, sem
  datas de publicação estimadas), moeda sem correção, dispersão entre métodos ≤ 25% e nenhum aviso
  de qualidade; C — método único, dispersão > 50%, avisos de qualidade, Argentina ou holding com
  participações não conferidas; B — demais casos com preço-alvo.
- Numa execução parcial (após resultados), os pares não reavaliados entram na mediana dos pares
  com o α publicado no último snapshot que os cobriu.
- A distribuição de ratings é monitorada (faixas de 20–40% para Compra e Venda) e nunca forçada.
- ETFs: retorno esperado combinado (bottom-up pelos alvos da casa + top-down por P/L justificado
  e Grinold–Kroner) e visão relativa ao ILF por `IR = (R_e − R_ILF)/TE` (±0,3). O P/L justificado
  do índice usa o payout sustentável `b = 1 − g/ROE_índice` (lucro e patrimônio agregados das
  posições), limitado a [0,6; 1,6] × o P/L corrente; num índice em regime estacionário a reversão
  do P/L é nula. Portão bloqueante ⇒ visão "Em revisão".
- Linhas do mesmo emissor na mesma moeda (outras classes ou units) recebem o alvo pela razão
  corrente de preços entre as classes; linhas em outra moeda, pelo câmbio esperado em 12 meses
  (paridade de inflação) e pela quantidade de ações por linha.

## 7. Portões de qualidade

G1 identidades contábeis (aviso); G2 nenhum insumo publicado depois da data (bloqueio); G3
valor finito; G4 ke no envelope P10–P90 dos demais emissores do país × setor, ± 1 p.p.
(informativo, sem efeito na confiança); G5 perpetuidade e valor terminal ≤ 85% (aviso; acima de
95% o método é excluído); G6 otimista ≥ base ≥ pessimista (bloqueio); G7 resíduo da ponte ≤ 0,5%
(aviso; avaliado antes do rating); G8 coerência de moeda (bloqueio); G9 upside em [−70%; +200%]
(bloqueio); G10 largura dos cenários (aviso); G11 |PWR| ≤ 60% (bloqueio); G12 preço com até 5
pregões de defasagem (bloqueio); G13 insumos por ação plausíveis — P/VPA em [0,1; 15], ROE do ano
1 até 100% em módulo e, quando métodos patrimoniais pesam mais de 50%, LPA de consenso coerente
com o lucro de 12 meses (bloqueio; armadilha de unidade ou moeda; exceções curadas); G14 FCFF do
ano 1 entre 0,5 e 2 vezes o fluxo de caixa livre observado (aviso); G15 fluxos e balanço na mesma
data-base (aviso). Bloqueio ⇒ "Em revisão": o preço-alvo existe no modelo aberto para auditoria,
mas não é publicado na tabela, não é citável nos fatos da pesquisa e não entra no placar.

## 8. Uso no alpha da carteira

O sinal `valuation_gap` (z de `α_rel` dentro de país × setor, winsorizado em ±3) e a tradução de
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

`verify` exige que o livro termine exatamente no último selo, que cada selo corresponda a um
evento da trilha do fundo (e vice-versa) e que os eventos de cada snapshot (`eventos.jsonl`)
coincidam com o livro; refaz todos os snapshots a partir dos insumos e da configuração
arquivados — contexto transversal, custo de capital, métodos, cenários com semente, α relativo,
confiança, rating e ETFs. A tolerância é relativa de 1e-5 (os números são armazenados com 6
algarismos significativos). Recalcular em outra plataforma pode diferir na sexta casa por
diferenças de biblioteca numérica; o hash dos arquivos arquivados é sempre exato. A execução
recusa, antes de calcular, uma data já coberta ou anterior ao último snapshot.

## 11. Limitações conhecidas

- Consenso público e parte das demonstrações de emissores fora da CVM/SEC vêm do Yahoo Finance;
  datas de publicação estimadas são sinalizadas.
- Emissores com demonstrações em moedas sem câmbio na base (sol peruano, dólar canadense) ficam
  sem preço-alvo até a inclusão da série pública de câmbio.
- Emissores com prejuízo recente tendem a valores extremos no lucro residual; os portões G9, G11
  e G13 os colocam "Em revisão" em vez de publicar um alvo implausível.
- A dispersão dos cenários de emissores muito alavancados ou de commodities com margem baixa
  pode atingir o piso de zero do patrimônio; nesses casos o retorno ponderado fica acima do
  retorno do caso-base (valor de opção da responsabilidade limitada), e as guardas de Compra pelo
  caso-base impedem que essa diferença sozinha produza um rating.
- Betas setoriais usam a indústria de Damodaran mais próxima da tabela curada; o β de regressão
  é exibido como diagnóstico.
- Frações das participações das holdings estão marcadas para conferência no documento-fonte.
