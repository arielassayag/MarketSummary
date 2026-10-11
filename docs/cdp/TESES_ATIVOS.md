# Teses e análises por ativo

O portal oferece um documento próprio para cada empresa e ETF do retrato de cobertura
publicado. O índice `ativos/` permite buscar por nome, ticker ou país; cada endereço
`ativos/<iid-em-minusculas>/` funciona diretamente, sem carregar a aplicação do painel.
O documento pode ser baixado em Markdown e JSON ou impresso como PDF pelo navegador.

## Estrutura de pesquisa profissional

A estrutura usa como referência o [guia de relatório de análise de ações do CFA Institute](https://www.cfainstitute.org/sites/default/files/-/media/documents/support/research-challenge/challenge/rc-equity-research-report-essentials.pdf):
negócio, indústria e competição, síntese de investimento, valuation, qualidade financeira,
riscos e governança. Para ETFs, o [boletim educacional da SEC sobre ETFs](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-24)
orienta a diligência de exposição, composição, liquidez, spread e diferença entre preço e
patrimônio. O [boletim da SEC sobre despesas](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/mutual-fund-and-etf-fees-and-expenses-investor-bulletin)
complementa a leitura de taxas e custos de negociação. São referências de pesquisa;
não certificam o conteúdo do CDP nem substituem os documentos dos emissores.

O fluxo foi organizado com as orientações de iniciação de cobertura do plugin Public Equity
Investing, respeitando os insumos públicos, a linguagem e os gates canônicos do CDP.

| Tema | Conteúdo e evidência necessária |
|---|---|
| Negócio | Segmentos, clientes, formação de receita, custos e reinvestimento, apoiados em documentos do emissor |
| Posição competitiva | Indústria, concorrência e condições que sustentam ou enfraquecem o retorno do capital |
| Tese | Hipóteses causais, evidências favoráveis e contraponto; classificação setorial não comprova vantagem competitiva |
| Debate de investimento | Diferença fundamentada frente a uma percepção de mercado documentada; consenso público não comprova o que está precificado |
| Qualidade financeira | Recorrência, conversão em caixa, balanço, dívida, reservas e efeitos contábeis relevantes |
| Valuation | Métodos, premissas, custo de capital, condições de citabilidade e cenários fornecidos pelo código |
| Gestão e capital | Governança, incentivos, partes relacionadas, reinvestimento e distribuição |
| Catalisadores e riscos | Eventos confirmados, mecanismos de transmissão e condições que invalidam a hipótese |
| Acompanhamento | Indicadores específicos e critérios de revisão ligados às hipóteses, sem limiares inventados |
| ETF | Índice, carteira subjacente, concentração, moeda, custos, replicação, liquidez e aderência ao índice contratual |

## Estados de maturidade e datas

**Narrativa publicada da gestão** identifica uma nota da mente já publicada, íntegra e
anterior ou igual à data do retrato. A página reproduz todo o conteúdo dessa nota e conserva
seus cortes de publicação e de dados. Uma nota publicada não significa que todos os temas
da tabela estejam resolvidos: suas lacunas continuam visíveis.

**Análise quantitativa preliminar** identifica ativos sem essa nota. A página contém a
memória do modelo e uma agenda de diligência por método econômico, sem atribuir uma opinião
qualitativa concluída. As perguntas genéricas de diligência são identificadas como hipóteses
a testar. Uma nota automática do código também não conta como visão da gestão.

O retrato quantitativo, a data do preço, o período de cada insumo e a data da narrativa são
mostrados separadamente. Um sinal do modelo pode diferir de uma nota anterior; a montagem
do site não atualiza a opinião da nota nem dimensiona uma posição. Para ETFs, a comparação
com o ILF não é apresentada como medida de aderência ao índice contratual do produto.

## Integração e controles

- As páginas vêm da mesma cobertura pública conferida que alimenta o painel. Há uma página
  por identificador do universo; duplicatas, caminhos inválidos e modelos ausentes recusam
  a montagem. Cobertura indisponível ou em verificação não produz relatórios apresentados
  como válidos.
- Narrativas vêm apenas de notas publicadas vinculadas à trilha. Uma falha na verificação
  dessas notas retira as narrativas; nunca adota silenciosamente um rascunho. Fontes e datas
  da narrativa ficam visíveis, inclusive os identificadores de evidências.
- Números vêm da representação pública determinística do modelo. Os portões de qualidade
  conservam o bloqueio de preço-alvo citável. A memória por método é rotulada como memória
  de cálculo e não substitui a conclusão agregada.
- Texto externo é escapado; fontes têm links HTTPS. As páginas, dados e downloads estão
  vinculados ao manifesto e ao SHA-256 da publicação. A demonstração continua identificada
  como DADOS SIMULADOS e fora da indexação.
- Não há escrita em livro, dados operacionais ou relatórios durante a montagem. A tese
  semanal da carteira continua com finalidade própria, distinta da pesquisa de cada ativo.

O schema de [notas por emissor](NOTAS.md) ganhou complementos opcionais de posição competitiva,
qualidade dos resultados, alocação de capital, percepção variante, contratese e indicadores
de acompanhamento. Eles reutilizam os limites e as verificações de fatos e evidências dos
pilares. Os campos ausentes não alteram a renderização histórica das notas.

As pesquisas das empresas seguem a fila de `cdp-cobertura`, com até doze emissores por
execução, no executor interno `.cdp/rotinas`. Nenhuma automação adicional é necessária.
Sessões de desenvolvimento podem entregar rascunhos no caminho canônico documentado em
NOTAS.md; só o executor pode validar e publicar no livro. Os ETFs já têm o documento do
modelo, mas o fluxo de notas por emissor ainda não publica uma tese qualitativa específica
de ETF. Essa extensão exige schema, validação e fila próprios, sem substituir a pesquisa
do produto por texto genérico.
