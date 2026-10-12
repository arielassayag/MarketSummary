# Galicia e Supervielle — classes e ADS contra o grão F2

O recorte documental está encerrado. Os corpos primários declaram **ADS de dez ações Classe B para Galicia e de cinco ações Classe B para Supervielle**. Isso confirma a declaração nos relatórios recebidos, mas não fecha a cadeia de vigência até o preço de 08/10/2026 ou um denominador operacional. A divergência de **20 ações da Supervielle permanece**, e há conflito adicional entre a quantidade primária de Galicia para dezembro/2024 e o campo Yahoo participante do F2. Nenhuma quantidade, razão operacional, NI, owners, ROE, BVPS, G13, P0 ou PIT foi adotada.

Esta entrega aplica `model-audit-tieout` e `financial-source-of-truth` do Public Equity Investing. Yahoo fica identificado como provedor padronizado; os PDFs dos emissores sustentam as declarações primárias. Os artefatos são suporte interno, sem recomendação ou modelo. Escrever a pasta não altera o checkout congelado, os produtores ou os dados oficiais.

## Corpo, recepção e limite da leitura

Foram recebidos **34 arquivos íntegros**, incluindo seis PDFs primários, os seis recibos originais, Yahoo/índice/universo e os dois produtos de mercado do F2. Cada cópia usa leitura FD com `O_NOFOLLOW`, SHA-256 e M6 antes/depois: device, inode, bytes, mtime_ns, **st_mode inteiro**, nlink. A cópia possui inode próprio. A recepção começou em `2026-10-10T19:20:01.468348+00:00` e encerrou em `19:22:01.142666+00:00`; o recibo conserva o UTC de cada corpo. São instantes desta leitura, não da posse do executor em 09/10.

O texto de cada uma das **1.356 páginas** foi extraído. O pypdf emitiu sete avisos de texto rotacionado incompleto; não houve OCR nem inspeção visual de todas as páginas. As três páginas dos lexemas da divergência Supervielle foram rasterizadas e vistas integralmente. Nenhuma ausência abaixo pretende ser global.

| ID/corpo integral próprio | SHA-256 | Captura original declarada UTC | URL primária e principais locadores PDF |
|---|---|---|---|
| G_J26 — `fontes/GALICIA_202606_EEFF.pdf` | `ff2b65222f2591c8fd9354d05b50020ee8879528233e4b0cce8a9b5b83921886` | 08/10/2026 21:45:45.191663 | [Galicia junho/2026](https://b.gfgsa.com/app/uploads/2026/09/EEFF-GFG-30-06-2026-INGLES.pdf), p3 e p39, nota20.1 |
| G_A25 — `fontes/GALICIA_202512_EEFF.pdf` | `5589b6bf1f3e695625f0ed85e8a841becb8610fd8f46101646000b5f3c5bacf2` | 08/10/2026 21:51:16.304225 | [Galicia dezembro/2025](https://b.gfgsa.com/app/uploads/2026/03/GRUPO-FINANCIERO-GALICIA-SA-31-12-2025-BYMA.pdf), p2 e p50, nota31.1 |
| G_IFRS25 — `fontes/GALICIA_20F2025.pdf` | `c4baaf5d3135f4de40b210eead8fa289d74428c63e6c01b795a32749aeb1bd66` | 09/10/2026 13:03:29.643759 | [Galicia 20-F/2025](https://b.gfgsa.com/app/uploads/2026/04/GGAL_20F_2025.pdf), p2 capa; p184 contrato; p197 Item9.A; p318 e p408/ScheduleK |
| S_J26 — `fontes/SUPV_202606_COMPLETO.pdf` | `320a78c3c35e4c62cb957690435d130897f7e3d0ba0ca1696dbc11a427dc67ee` | 09/10/2026 00:56:43.337390 | [Supervielle junho/2026](https://s26.q4cdn.com/426641508/files/doc_financials/2026/q2/Financial-Statements-06-30-26.pdf), p4 e p41/nota15 |
| S_A25 — `fontes/SUPV_202512_FS.pdf` | `8f58fc084261c11abb635c3bbfa8303ed2fbac0b6c9e56c1525e2a2e6285aea7` | 08/10/2026 21:51:55.994170 | [Supervielle dezembro/2025](https://s26.q4cdn.com/426641508/files/doc_financials/2025/q4/FS-Grupo-Supervielle-31-12-2025.pdf), p4/CapitalStock; p66, p78, p130 |
| S_IFRS25 — `fontes/SUPV_20F2025.pdf` | `6f5f32eeb39801e1c64e668a5b6bfc064b42630f9736494f829bdaca3a7524fd` | 08/10/2026 21:45:09.214367 | [Supervielle 20-F/2025](https://s26.q4cdn.com/426641508/files/doc_financials/2025/ar/20F2025-Final.pdf), p1–2/capa; p5; p37; p230–231/Item7.A; p238; p295; p373/F77 e p393/F97 |

O `Source_Index.csv` liga os seis PDFs e quatro corpos Yahoo à recepção própria. `RECIBO_RECEPCAO_E_EXTRACAO.json` cobre também parquets, manifestos e controles íntegros. As cópias `.cdp` locais não pressupõem disponibilidade em outro clone.

## Classes, razão e datas: o que a fonte declara

| Conceito | Galicia | Supervielle | Estoque, intervalo e limite de unidade |
|---|---|---|---|
| Classe A / B | Ambas ordinárias; A cinco votos, B um; nominal ARS1. G_J26 p3,p39; G_IFRS25 p408 | Ambas ordinárias; A cinco votos, B um; nominal Ps1. S_A25/S_J26 p4; S_IFRS25 p230 | Votos e valor nominal não são contagem. Ações do grupo não são ações do banco subsidiário. |
| ADS e subjacente | Dez **Classe B** por ADS, capa p2; declaração de negociação p197 | Cinco **Classe B** por ADS, capa p1, definição p5 e histórico p37 | A razão é quantidade de ações Classe B por ADS; não é ARS, USD, índice de inflação ou soma A+B. |
| Negociação histórica | Nasdaq National desde 24/07/2000; Capital Market desde agosto/2002, p197 | NYSE desde 19/05/2016, p37,p238 | São datas de negociação declaradas. Não preencher início/fim de vigência do ratio só por essas datas. |
| Contrato mencionado | Second Amended and Restated Deposit Agreement de 22/06/2000, p184; corpo referenciado no F4, p238 | Deposit Agreement de 18/05/2016 incorporado do 20-F/2017, p295 | Corpo contratual e cadeia de alterações integral não recebidos. Vigência operacional até08Oct permanece `null`. |
| Estoque junho/2026 | A `281,221,650`; B `1,325,032,079`; total `1,606,253,729`; declaração sem ações próprias, p3,p39 | A `61,738,188`; B `380,933,642`; total `442,671,830`, p4 | Estoques 30/06. Declaração de inexistência não vira célula inventada zero. Parágrafo SUPV p41 refere treasury à publicação; não deslocar esse instante para junho. |
| Estoque dezembro/2025 | Mesmo A/B/total, G_A25 p2 e G_IFRS25 p408 | Emitidas A `61,738,188`, B `382,673,523`, total `444,411,711`, S_A25 p4; capa20F exclui treasury e declara B `375,992,997`, p2 | Mesmo fechamento não elimina conflito ou iguala emitidas a circulação. |
| Eventos após fechamento | Emissão B `17,740,028` em 13/02/2025; registro07/05/2025, G_J26 p39 | S_IFRS25 p393 descreve canceladas B `12,310,611` até31/12/2025 e `1,739,881` entre02/01–07/02/2026; p230 descreve outro intervalo agregado até10/02 | Datas e intervalos ficam literais; não corrigir um pelo outro. Não substituir quantidade de dezembro por quantidade de março/junho. |
| Contagem × poder monetário | G_J26 p3 exclui “quantity” e votos da legenda milhares-ARS; p39 distingue Quantity de ShareCapital | S_A25/S_J26 p4 distingue Quantity de capital subscrito/integrado em milhares; treasury p373 distingue ações de custo monetário | Contagem não recebe ajuste IAS29. O contexto monetário junho/2026 ou dezembro/2025 das rubricas financeiras fica separado. Estoque não é média do intervalo de NI. |

O quadro completo possui **43 fatos literais**, com corpo, URL, SHA, página, locator, data de estoque/intervalo e limite. O arquivo `Quadro_Final_Classes_ADS.csv` explicita classes, mantendo os valores do primeiro quadro. A capa de Galicia p2 contém ainda texto “New York Stock Exchange” na disposição de sua segunda tabela, embora p197 declare Nasdaq; esse texto recebido não foi corrigido ou usado para mudar a linha.

## As 20 ações da Supervielle

O programa `documentar.py` fez apenas o diagnóstico de identidade documental por Decimal: emitidas Classe B `382673523` (S_A25 p4), treasury `6680546` (S_IFRS25 p373), circulação implícita QA `375992977`, contra circulação B publicada na capa `375992997` (p2); o delta registrado é `20`. As três páginas rasterizadas confirmam esses lexemas. O programa não produziu um denominador operacional.

A tesouraria em p373 usa rótulo genérico; a ponte Classe B conserva o programa de recompra e os cancelamentos descritos na nota32 p392–393. O QA testa essa ponte documental recebida. Mesmo sem conceder a classificação da ponte, o denominador continua não qualificado. Não escolher a capa, o QA, o número de março ou uma tolerância para satisfazer G13.

O “outstanding” de p230 é explicitamente **incluindo treasury** em31/03/2026 (`442,671,830` total; B `380,933,642`; treasury `4,940,665`). A capa p2 exclui treasury em31/12/2025. As duas definições/datas ficam separadas. Treasury à data de publicação em S_A25 p78/S_J26 p41 conserva data primária desconhecida; a nota S_A25 p66/p130 diz literalmente dezembro/2024, que não foi corrigido para2025.

Dois resultados de buscas primárias SEC apontaram a mesma quantidade `375,992,997` na capa2025 e também em20F/A2024. Foram conservados **como descoberta** em `BUSCAS_01_RESPOSTA_INTEGRAL.json`; não há corpo integral adquirido de nenhum deles. [Resultado SEC2025](https://www.sec.gov/Archives/edgar/data/1517399/000110465926040713/supv-20251231x20f.htm), [resultado SEC20F/A2024](https://www.sec.gov/Archives/edgar/data/1517399/000151739925000055/supv-20241231x20fa.htm). Isso não prova erro de cópia ou uma retificação da quantidade.

A tentativa única pré-registrada de GET integral do SEC2025 recebeu403 em `2026-10-10T19:24:18.276663+00:00`: 4.819 bytes, SHA `d371bceae5d5e06e0b2407a49b54b3adc061fa45c9f7a536de6732fa8223ddda`. Esse corpo é resposta de erro, **não fonte utilizável**. Não houve retry/contorno. O recorte externo encerrou com **duas buscas, uma aquisição tentada e nenhuma aquisição primária utilizável**, dentro do limite quatro/duas.

Há ainda alerta literal independente: S_IFRS25 p295 incorpora bylaw de20F/A “filed on November25,2026”, posterior à captura declarada08Oct. O ano permanece literal; não há correção presumida, sequência de publicação certificada ou posse09 inferida.

## Os campos Yahoo e os usos F2

O F2 parou na primeira negativa Galicia e **não alcançou consumo Supervielle**. Seus cinco fatos `acoes_em_circulacao` vieram de GGAL.BA `Ordinary Shares Number`: trimestral30/06/2026 e anual2022–2025. O corpo integral possui SHA `1039b5c67ffea6ecca5b70db99e26c7f1d788c6da2137193c3d44c74fc958b9b`; locators exatos e 23 campos de diagnóstico estão em `Campos_Yahoo_F2.csv`. Os registros integrais por SHA, incluindo múltiplas coletas de corpo idêntico, permanecem em `YAHOO_REGISTROS_INTEGRAIS.json`; nenhum registro foi substituído por data conveniente.

| Grão/campo recebido | Fato literal | Conclusão sustentada / limite |
|---|---|---|
| GGAL.BA OrdinaryShares2025 e June26 | `1606253729.0` | Igualdade numérica com total A+B primário, não apenas B. Rótulo nativo `acoes_em_circulacao` não prova por si uma classe. |
| GGAL.BA OrdinaryShares2024 | `1593110474.0` | Diverge de Quantity total comparativa `1,588,513,701`, G_J26 p39/31Dec2024. `CONFLITO_GALICIA_2024.json` conserva ambos; causa não qualificada. |
| GGAL.BA OrdinaryShares2022/2023 | `1478888638.0` em cada coluna | Não há confirmação de estoque específico dessas datas neste recorte. Narrativa histórica de capital, média de EPS ou capital monetário não substituem essa fonte. |
| GGAL.BA info/sharesOutstanding | `1325032079` | Coincide numericamente com B primária; o raw não declara classe ou vigência. Não qualificar apenas pela coincidência. |
| GGAL.BA info/impliedSharesOutstanding | `1606253729` | Coincide com total A+B; não substitui sharesOutstanding ou fluxo/intervalo. |
| GGAL info | sharesOutstanding `132503208`; implied `169453445`; float `837356131`; moeda cotaçãoUSD, financialCurrencyARS | Unidade dos três campos não é declarada no raw. Não converter float/total entre ações e ADS por semelhança ou escolher implied para marketCap. |
| SUPV info | sharesOutstanding `75198595`; implied `94508205`; float `38593881`; USD/ARS | Apenas diagnóstico secundário; nenhuma declaração primária de quantidade ADS efetivamente depositada/emitida ou data de estoque desses campos foi recebida. |

O índice e o universo F2 recebidos não contêm SUPV.BA. A ausência fica restrita a esses recipientes. O `financialCurrency=ARS` do info GGAL.BA é dependência da moeda dos demonstrativos, não certificação da unidade econômica da contagem.

Os dois grãos de mercado F2 pertencem a **GGAL ADR**: `market_cap` literal `6481593856.0` é o produto `FUNDAMENTALS_20261005.parquet`, SHA `0e2fd53232f337ea3c2aacfb2bd950b0de107562b62cd8289f808d83b0836f97`, captura declarada05Oct22:24:47.049031Z; `close`08Oct literal `36.7599983215332` está em `PRICES_20261008.parquet`, SHA `93fa0479fc5b794351e17da2c729a176c9dcb41cec6a4019a6cdd91ce3663648`, captura08Oct22:24:00.967822Z. O `price_yahoo=38.25` do retrato05Oct não substitui o fechamento08Oct. Os produtos e seus manifestos próprios foram recebidos, mas este estudo não reexecutou a cadeia de mercado. A resposta integral Ticker.info que originou esse market cap não está recebida: o info público não arquiva marketCap.

## Evidência, inferência e ausência para a continuação

**Evidência:** classe B/razões declaradas10 e5; datas históricas de negociação e contratos mencionados; lexemas de estoque/cancelamento/treasury; dois conflitos documentais; grãos nativos F2 e corpos físicos distintos do mercado. A recepção local é de10Oct e tem SHA/M6 próprios.

**Inferência não adotada:** associar sharesOutstanding Yahoo a B pelo número igual; tratar toda B como ADS emitido/depositado; estender a razão ao preço08Oct sem cadeia de vigência; atribuir treasury da publicação ao fechamento; explicar as20 por cópia de capa ou explicar OrdinaryShares2024 por ponderação/diluição. São hipóteses, não fatos resolvidos.

**Ausência no recorte:** retificação primária que resolva as20; corpo dos contratos e cadeia de alterações da razão até08Oct; contagem ADS efetiva e data/classe dos três campos info; confirmação primária dos estoques OrdinaryShares2022/2023 e causa2024; raw original marketCap; publicação primária/posse histórica. Não converter essas ausências em zero, “não houve” ou habilitação.

`PLANO_MINIMO_CONSUMIDORES.json` entrega seis pontos de trabalho futuros: cadastro de instrumentos, confirmação por classe/data, cinco grãos Yahoo, dois donos físicos do mercado, consumo Supervielle efetivamente alcançado e ponte financeira separada. **Implementação e ativação zero**. Razão operacional/quantidade/vigência permanecem `null`. A implementação de metadados que corre em outra tarefa pode fechar origem prospectiva, mas conserva estes bloqueios econômicos; este estudo não liga consumidores, muda configurações ou repete F2.
