# Rascunhos de notas de pesquisa entregues fora do clone das rotinas

O livro (`book/`) tem um único escritor: o clone que roda as rotinas. Uma nota de pesquisa
escrita em outro lugar — uma sessão de desenvolvimento, o Codex, ou qualquer assistente com o
pacote de `cdp mente pacote` — chega aqui como rascunho versionado:

```
docs/cdp/notas/<IID>/<AAAA-MM-DD>.json
```

com o mesmo schema de `book/cobertura/notas/<IID>/<data>/nota.json` (`NotaEmpresa`,
`docs/cdp/NOTAS.md`) e `"mind"` preenchido (`claude-code`, `codex`, `chatgpt`, `gemini` ou
`outro`).

- `cdp nota agenda` põe todo rascunho com data até hoje e ainda não publicado na frente da fila
  (`data_nota` = a data do rascunho; um rascunho por emissor por execução) e o lista em
  `rascunhos_pendentes`; a rotina `cdp-cobertura` roda `nota prepare` nessa data e adota o
  rascunho quando a nota ainda não tem `nota.json`: copia byte a byte (`rascunho_adotado:
  true`), nunca sobrescreve um `nota.json` existente e nunca publica. A mente roda
  `validate-nota` antes de escrever qualquer coisa: `ok: true` ⇒ publica sem reescrever; senão
  corrige só a cópia no livro.
- A validação usa o FactBook calculado pelo código **da própria rotina** na data da nota: um
  rascunho com fato inexistente, número livre ou fonte inválida não passa.
- A data do arquivo é a data da nota; um rascunho para uma data já publicada é ignorado, e um
  rascunho com data anterior à última nota publicada do emissor fica obsoleto
  (`rascunhos_obsoletos` em `nota agenda`; nunca é adotado). Rascunho com data futura espera a
  data chegar.
- Nunca faça commit de `book/` fora do clone das rotinas (a sincronização de todas as rotinas
  pararia) e nunca edite esta pasta a partir do clone das rotinas.

Fluxo para escrever o rascunho com qualquer assistente (fatos preparados numa cópia do livro):

```sh
uv run python -m cdp --book /tmp/cdp-copia/book nota prepare --issuer IID --date AAAA-MM-DD
uv run python -m cdp --book /tmp/cdp-copia/book mente pacote --etapa nota --emissor IID --data AAAA-MM-DD --saida /tmp/pacote_nota.md
uv run python -m cdp --book /tmp/cdp-copia/book validate-nota --issuer IID --date AAAA-MM-DD
```

Depois de `ok: true`, copie `book/cobertura/notas/<IID>/<data>/nota.json` da cópia para
`docs/cdp/notas/<IID>/<AAAA-MM-DD>.json` e faça commit só desse arquivo.

## Estudos de ETFs entregues em 11/10/2026

Os diretórios `ETF_ARGT`, `ETF_BOVA11`, `ETF_COLO`, `ETF_ECH`, `ETF_EPU`, `ETF_EWW`,
`ETF_EWZ` e `ETF_ILF` contêm rascunhos de iniciação. Cada estudo reúne hipótese de
investimento, condição decisiva, contraponto, cenários qualitativos, riscos, interpretação
do modelo, produto, exposição, custos, aderência ao índice e acompanhamento. Os documentos
preservam as lacunas de prospecto, replicação e negociação; visão neutra não equivale a
recomendação nem a diligência concluída. Fontes públicas dos administradores foram
consultadas na data da nota; data de consulta não é data de publicação.

A extensão de notas aceita o produto somente com identidade e modelo íntegros no retrato,
na fila existente e no mesmo limite de execução. Verificação de desenvolvimento não é
publicação: o executor continua responsável pela adoção, validação e trilha imutável.

## Estudos de empresas entregues em 11/10/2026

Os diretórios `BR_AMBEV`, `BR_GERDAU`, `BR_ITAUSA` e `BR_COPEL` contêm estudos com
hipótese própria, condição decisiva, posição competitiva a comprovar, qualidade do
resultado, alocação de capital, contraponto e indicadores de revisão. Todos os preços,
cenários e retornos citados são referências ao FactBook. Os perfis e materiais públicos
de RI foram consultados; o último resultado, as notas explicativas e os projetos não
foram integralmente reconciliados. Os textos são rascunhos de baixa convicção, com
lacunas explícitas, e aguardam adoção e validação pelo executor.

## Segundo lote de empresas em 11/10/2026

`LA_FORTUNA`, `BR_STONE`, `BR_VIVO` e `BR_CEMIG` acrescentam pesquisas próprias de
mineração, pagamentos, telecomunicações e energia sob controle estatal. Documentos de
RI consultados e lacunas acompanham cada estudo. A orientação de produção da Fortuna
não equivale a retorno dos projetos; o lucro ajustado básico da Stone não substitui a
reconciliação diluída. A consulta atual do perfil da Vivo não comprova publicação
histórica. A análise da Cemig não incorpora mudança de controle não confirmada.

## Lotes seguintes de empresas em 11/10/2026

- `BR_SUZANO`, `BR_KLABIN`, `BR_USIMINAS` e `BR_GOAU`: produtividade,
  manutenção, custo completo e caixa atribuível. Suzano distingue valor justo,
  derivativos e integração posterior. Klabin preserva diferenças entre fluxo
  livre, ajustes e financiamento. Usiminas separa itens extraordinários e
  recuperação de caixa. GOAU distingue holding, consolidado e minoritários;
  inconsistências do release ficam documentadas sem correção da fonte.
- `BR_VALE`, `BR_CSN`, `BR_CMIN` e `BR_BRADESPAR`: custo mineral completo,
  reposição, reparação, liquidez e transmissão de valor pela holding. Vale
  distingue subprodutos, caixa de contratos e obrigações fora da dívida
  expandida. CSN preserva financiamento na medida gerencial de fluxo livre e
  alienações condicionais. CMIN separa produção, compras e perímetro do grupo;
  volume e custo têm revisões diferentes. Bradespar mantém a divergência de
  período sobre a dívida da Vale e não presume recebimento de provento programado.
- `BR_PETROBRAS`, `BR_PRIO`, `BR_BRAVA` e `BR_RECV`: produção econômica,
  custo completo, capital e caixa após financiamento. Petrobras separa fluxo da
  política de remuneração e arrendamentos. PRIO distingue produção mensal
  preliminar, participação e recurso prospectivo; Brava documenta mudança de
  controle concluída e poço em estabilização. PetroReconcavo separa acesso
  contratado ao processamento, marcação financeira e liquidação de proteção.
  Resultado posterior e pagamento programado conservam seus estados próprios.
- `BR_TAESA`, `BR_ISAENERGIA`, `BR_CPFL` e `BR_ENEVA`: retorno das redes,
  investimento, geração contratada e caixa após financiamento. Taesa distingue
  lucro regulatório e societário; ISA separa dívida, aferição contratual e
  reorganização posterior ao trimestre. CPFL preserva a contribuição excepcional
  do seguro e uma divergência de bases da geração. Eneva distingue a venda
  concluída de Pecém, a permuta condicional de Itaqui e a opção cancelada;
  anúncio não equivale a monetização recorrente ou caixa disponível.
- `BR_ALUPAR`, `BR_AUREN`, `BR_AXIA` e `BR_ENERGISA`: remuneração das redes,
  margem realizada de energia, implantação e caixa após obrigações. As bases
  regulatória e societária, recursos restritos e participações têm leituras
  próprias. O protocolo posterior da CESP não comprova fechamento da etapa
  societária; o aviso de dividendos da Alupar fixa data passada sem comprovar
  crédito efetivo. Axia preserva estados divergentes de Três Irmãos no release,
  e Energisa distingue projeções retiradas e mantidas, sem direção agregada.
- `BR_CYRELA`, `BR_COPASA`, `BR_MOTIVA` e `MX_WALMEX`: economia dos projetos
  imobiliários, obrigações do saneamento, perímetro após venda de aeroportos e
  contribuição do varejo depois de estoque e contratos de uso. A composição
  atual da Copasa exige documentos de controle e direitos; a consulta parcial
  do perfil da Cyrela não equivale a arquivo primário integral recebido.
- `BR_TIM`, `BR_MULTIPLAN`, `BR_SANTANDER` e `BR_PAGS`: retorno após investimento
  em redes, receitas e participação econômica de shopping centers, lucro
  atribuível e capital bancário, e monetização de pagamentos depois do risco.
  Direitos de capital, OPA, distribuição e recompras não são presumidos por
  títulos de comunicados.
- `MX_FEMSA`, `CL_CENCOSUD`, `CL_CMPC` e `MX_BANORTE`: caixa por negócio e
  participação, comparabilidade do varejo, retorno industrial ao longo do ciclo,
  e capital por atividade financeira. O anexo consultado de Banorte detalha
  financiamentos; não substitui demonstrações completas de resultado e capital.
- `BR_SABESP`, `PE_CREDICORP`, `PE_BVN` e `PE_SCCO`: remuneração contratual e
  financiamento da universalização, monetização bancária após perdas e capital,
  maturação das minas e caixa das associadas, e execução de expansão do cobre.
  A correção retrospectiva de resultado da Buenaventura exige base reconciliada;
  recurso captado pela Southern Copper não prova financiamento integral ou retorno.
- `AR_PAMPA`, `AR_CRESUD`, `AR_IRSA` e `AR_YPF`: retorno depois de infraestrutura
  e financiamento, produtividade rural e recebimentos das participações, renda
  imobiliária e monetização dos projetos, e caixa por ação depois de reinvestimento.
  Perímetro de afiliadas, avaliações, permutas e direitos de capital exigem
  conciliação. O anual completo da Cresud não foi recebido com HTTPS válido;
  o estatuto da YPF não substitui seu último resultado.
- `CL_COPEC`, `CL_ENELAM`, `CL_ENELCHILE` e `CO_ECOPETROL`: retorno recebido do
  portfólio após expansão, remuneração das redes e capital das controladas,
  geração contratada e monetização regulatória, e contribuição do refino e dos
  recebíveis de combustíveis. Declaração de financiamento, conversão cambial,
  instrumento recebido e caixa têm significados distintos. A análise de Enel
  Chile foi consultada na fonte; o download separado foi recusado e não há
  cópia local recebida. Demonstrações, unidades e obrigações exigem reconciliação.
- `MX_CEMEX`, `MX_AMX`, `MX_KOF` e `MX_ASUR`: eficiência ao longo do ciclo,
  monetização da rede, retorno da distribuição franqueada e remuneração de
  concessões após expansão. A Cemex distingue orientação elevada e efeito
  excepcional; América Móvil exige bases comparáveis e liquidez por entidade;
  Coca-Cola FEMSA distingue ação, unidade e recibo. A aquisição da Motiva pela
  ASUR foi concluída depois do trimestre e está fora daquelas demonstrações;
  reorganização e dívida posterior exigem conciliação própria. O release de
  Coca-Cola FEMSA foi consultado na pesquisa, mas não recebido no download separado.
- `MX_AC`, `MX_GAP`, `MX_OMA` e `MX_ORBIA`: caixa por território, retorno após
  integração e emissão de capital, manutenção e desenvolvimento de concessões,
  e conversão da recuperação industrial em caixa. A GAP já descreve ações
  emitidas e combinação concluída; o perfil institucional antigo não representa
  sozinho a estrutura atual. A OMA distingue provisão de manutenção e desembolso;
  Orbia distingue defasagem de custos e rentabilidade durável. Arca Continental
  e Orbia têm eventos futuros datados em material primário; o calendário não
  antecipa conteúdo ou resultado do evento.

- `LA_MELI`, `LA_DLOCAL`, `LA_ARCOS`, `LA_COPA`, `BR_VTEX`, `BR_AFYA`,
  `BR_YDUQS`, `AR_GLOBANT` e `BR_PATRIA`: monetização de plataformas, risco
  de crédito e pagamentos, franquias e operação aérea, software, educação,
  serviços de tecnologia e gestão de investimentos. Receita ajustada, atividade,
  capital de clientes e lucro atribuível têm perímetros próprios.
- `AR_ADECOAGRO`, `AR_CAAP`, `AR_CEPU`, `AR_LAR`, `AR_LOMA`, `AR_TEO` e
  `AR_TGS`: agricultura e indústria, concessões aeroportuárias, energia, lítio,
  cimento, telecomunicações e gás. Inflação, controle, moeda, recebíveis,
  infraestrutura e financiamento exigem conciliação específica; anúncio não
  equivale a caixa recebido ou projeto em operação.
- `CL_ANDINA`, `CL_CENCOMALLS`, `CL_FALABELLA`, `CL_MALLPLAZA`, `CL_PARAUCO`,
  `CL_LATAM` e `CL_SQM`: distribuição de bebidas, imóveis, varejo, transporte
  aéreo e materiais. O memorando entre Falabella e Mallplaza era não vinculante
  no comunicado consultado; não comprova transferência concluída. Participação
  econômica, contratos de uso, caixa e exposição de projetos ficam separados.
- `CL_COLBUN`, `CL_ECL`, `CL_EISA`, `CO_GEOPARK`, `CO_GRANTIERRA`,
  `CO_TECNOGLASS` e `PE_NEXA`: geração, distribuição, exploração de petróleo,
  materiais para construção e metais. Contratos, disponibilidade, reservas,
  capital de giro e maturação precisam sustentar caixa depois do reinvestimento.
- `CO_CEMARGOS`, `CO_GRUPOARGOS`, `CO_SURA`, `CO_ISA`, `CO_CIBEST`, `LA_LILA`
  e `LA_MILLICOM`: reorganização de portfólios e participações, capital financeiro,
  infraestrutura e telecomunicações. Direitos da holding, reorganizações e
  dividendos não são presumidos equivalentes ao resultado das controladas.
- `AR_SUPERVIELLE`, `AR_MACRO`, `AR_GALICIA` e `AR_BBVA`: resultado real,
  crédito e funding, integração de negócios e capital bancário. Resultado
  estrutural ou ajustado não substitui retorno efetivo; provisão menor não
  comprova atraso menor. A norma local, a base do retorno e os direitos por
  instrumento precisam ser compatíveis com o modelo.
- `CL_BCHILE`, `CL_BCI`, `CL_BSAC` e `CL_ITAU`: retorno além da inflação,
  capital por país, transformação e direitos societários. Bci Group já aparece
  no retrato posterior de acionistas diretos, sem comprovar todas as etapas de
  reorganização. Itaú Colombia registra cessão de parte do varejo e efeitos de
  reestruturação posteriores ao trimestre. Projeções com direções diferentes
  não são classificadas como melhora uniforme de guidance.

- `LA_BLADEX` e `PE_IFS`: intermediação e comércio exterior, capital e crédito
  por negócio. Caixa bancário e recursos das controladas não são presumidos
  disponíveis ao acionista; retorno e financiamento precisam ter bases compatíveis.
- `MX_BAJIO`, `MX_REGIONAL`, `MX_INBURSA`, `MX_GENTERA`, `MX_QUALITAS` e
  `MX_BMV`: crédito, capital, seguros e infraestrutura de mercado. Safras de
  crédito, qualidade da carteira, reservas, resultado de investimentos e volumes
  negociados exigem reconciliações próprias; lucro maior não comprova risco menor.
- `MX_FIBRAPL`, `MX_FMTY`, `MX_FUNO`, `MX_VESTA`, `MX_PINFRA` e `MX_GCC`:
  renda imobiliária, direitos por certificado, concessões e materiais. Oferta
  autorizada não comprova liquidação; aquisição no período não tem a mesma base
  temporal de todos os certificados emitidos. Transferência de receitas e ativos,
  incentivos, recursos não sacados e capex estratégico permanecem distintos.
- `MX_VISTA`, `MX_TERNIUM`, `MX_GMEXICO`, `MX_PENOLES`, `MX_FIRSTMAJ`,
  `MX_ENDEAVOUR` e `MX_ALPEK`: energia, metais e petroquímica. Reservas não
  são produção; caixa gerencial antes de aquisições, resultado ajustado e caixa
  livre atribuível têm perímetros diferentes. Misturas de períodos, custo por
  equivalente metálico, minoritários e eventos posteriores ao trimestre ficam
  explícitos. Comunicados da First Majestic e Endeavour Silver foram consultados
  na fonte, mas o download separado foi recusado, sem cópia local recebida.

- `MX_AEROMEXICO` e `MX_VOLARIS`: economia da frota, manutenção, arrendamentos
  e capital. Margem gerencial não equivale a caixa; uma decisão judicial relatada
  pela emissora e combinações aprovadas por acionistas conservam seus limites.
- `MX_BIMBO`, `MX_ALSEA`, `MX_CHEDRAUI`, `MX_GRUMA` e `MX_SIGMA`: consumo,
  canais e produção de alimentos. Moeda, aquisições, produtividade, seguros,
  operações descontinuadas e dividendos anunciados têm bases distintas. Sigma
  Foods é a antiga Alfa, com estatísticas próprias da holding e da subsidiária.

- `MX_CARSO`, `MX_GENOMMA`, `MX_KIMBER`, `MX_MEGACABLE` e `MX_TELEVISA`:
  conglomerados, marcas de consumo e telecomunicações. As narrativas distinguem
  alienações concluídas, aprovações pendentes, lucro financeiro e operacional,
  indicadores gerenciais, investimento não corrente e capital conversível.
  O calendário de Kimber tem evento futuro confirmado; datas não comprovadas
  permanecem ausentes. Inconsistências do texto do emissor são preservadas.

- `BR_ABC`, `BR_PINE`, `BR_INTER`, `BR_PICPAY`, `BR_BANRISUL` e
  `BR_BRADESCO`: retorno da franquia bancária, perdas por safra, provisões,
  capital e direitos por ação. Recuperação de crédito e reversão não equivalem
  à melhora recorrente da margem. A janela dos recibos do Inter, a integração
  da seguradora do PicPay e o crédito programado de ações do Bradesco preservam
  seus estados. O contrato de folha do Banrisul tem custo e vigência próprios.

- `BR_BBSEG`, `BR_CXSEG`, `BR_PORTO`, `BR_IRB` e `BR_BRADSAUDE`: seguros,
  resseguro e saúde. As teses separam subscrição e rendimento de reservas,
  bases gerenciais e contábeis, capital por entidade e caixa da holding.
  Reversões, retrocessão e perímetro após reorganização têm análise própria.
  Bradsaúde conserva lacuna de base por ação; dividendos, dívida e datas
  futuras não foram antecipados como concluídos.

Todos são rascunhos com hipóteses próprias, contraponto, indicadores e lacunas.
Mesmo a consulta do último release não encerra a reconciliação financeira com o
modelo, a comparação competitiva e a diligência do capital. Nenhum dado externo
foi incorporado automaticamente ao FactBook. A fila preserva a data de cada
rascunho até a adoção pelo executor; não há publicação direta desta pasta.
