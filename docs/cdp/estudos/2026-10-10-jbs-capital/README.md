# JBS N.V. — capital e EPS: divergências documentais em aberto

Leitura de 10/10/2026 com Public Equity Investing, controle de fontes e confronto
documental. **Nenhuma quantidade foi escolhida para valuation. G13, P0 e PIT
permanecem abertos.** Esta passagem registra pesquisa; não modifica fatos
financeiros, cobertura ou o livro.

## Corpos primários recebidos

O [Results Center da JBS](https://ir.jbsglobal.com/results-and-presentations/results-center/)
vincula a documentação de resultados. Os corpos abaixo foram conservados
separadamente, com hashes dos bytes completos:

| Corpo | SHA-256 | Limite de evidência |
|---|---|---|
| [PDF anual composto 2025](https://api.mziq.com/mzfilemanager/v2/d/fdb59571-9620-473a-8f8d-a9c27ebf7d44/ec904eac-6058-5b32-f24d-23e0b7929795?origin=2) | `68358b15b13b4053bdb9435b5ecae78eb1ae74b1fa6ff8690f6932b811856322` | 127 páginas; USD nas 1–67, BRL a partir da 68. Recebido por HTTP em 09/10/2026, 13:12:48.935042Z |
| [HTML SEC 20-F anual arquivado](https://www.sec.gov/Archives/edgar/data/1791942/000121390026034213/ea0282342-20f_jbsnv.htm) | `c26b08196f75cab06ca9dd6202176dd36355471b7458a027903a9b88ba81948d` | Corpo completo de 8.100.451 bytes; mtime local não é recibo HTTP nem data de publicação |
| [HTML SEC Q2 2026 arquivado](https://www.sec.gov/Archives/edgar/data/1791942/000179194226000004/jbsay-20260630.htm) | `faa27c1738aa563eae86505480b55c5c408f458aeeb14e04bd15c6b7ea8692b9` | Corpo completo de 4.556.900 bytes; proveniência local preservada |
| [PDF RI trimestral USD](https://api.mziq.com/mzfilemanager/v2/d/fdb59571-9620-473a-8f8d-a9c27ebf7d44/7489b5dc-c4eb-2f17-9c08-4f7d33144a7e?origin=2) | `966810f8629c3111053fbb370f93ab647f9d036e290f543950b97937806d37c7` | 51 páginas; recepções de 08/10 e 10/10 têm recibos distintos |

A consulta SEC de 10/10 retornou HTTP403, corpo de erro com SHA
`fd289f9adfb766294f7db7143eb2789bd09614198fda65411cdd94b8a897fe31`.
O erro foi preservado e não substitui o HTML anterior. Não houve nova coleta
de documentos para esta leitura. Tamanhos indicados pelos índices SEC divergem
dos corpos locais; a causa não foi presumida.

## Políticas e quantidades anuais

As páginas físicas 12/14 do PDF anual descrevem a reorganização sob controle
comum e demonstrações IFRS/IASB apresentadas em USD. O histórico de JBS S.A.
precede o consolidado JBS N.V.; a política ajusta retrospectivamente as ações
para EPS desde 01/01/2023. Isso não demonstra perímetro econômico constante.
A página 31 chama BRL de moeda de apresentação sob cabeçalho USD: o conflito
permanece observado, sem conversão ou correção presumida.

Na mesma data de referência, **31/12/2025**, a nota 20, página 42, apresenta
814.216.001 ações A e 294.842.184 B; a capa anual apresenta 773.666.610 A e
294.842.267 B. A tabela de principais acionistas tem data distinta, 18/03/2026;
não preenche o estoque de dezembro ou junho.
A capa fica em `/html/body/div/p[53]`, fatos `ixv-88286/88287`, contextos
`c2/c3`, unidade shares, scale0. A nota20 fica no quadro HTML1088.

O quadro de tesouraria, página 43, publica fechamento Quantity 94.537.534 e
valor monetário 598.423 em milhares de USD. O fato digital da quantidade usa
NumberOfSharesIssued, apesar do contexto de tesouraria; o valor monetário usa
TreasuryShares, USD, scale3. Tag, contexto e legenda foram preservados juntos.

Na página 44, o denominador médio anual de EPS é publicado diretamente como
1.068.508.877 nos três anos 2025/2024/2023. A legenda indica ações em milhares,
mas os fatos digitais usam unidade shares, scale0. Os numeradores monetários
usam USD, scale3. O confronto em Python/Decimal reproduz o EPS publicado ao
arredondamento; coincidência aritmética não resolve a unidade nem a diferença
entre estoque e média anual. Nenhuma média foi aplicada ao trimestre.

## Junho de 2026 e critério para retomar

A capa Q2 vincula outstanding a **30/06/2026**, A 776.086.920 e B 294.842.267.
Os fatos digitais usam shares, scale3; lexemas e aplicação da escala divergem.
O CSV primário CVM da mesma data informa capital integralizado 1.070.929.187
e tesouraria 92.117.224. Correspondência aritmética não demonstra equivalência
conceitual entre capital integralizado e outstanding. O HTML capital recebido
com seis valores 0,00 permanece separado e não foi usado como dado financeiro.

O [ZIP ITR CVM 2026](https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_2026.zip)
tem SHA `0e1ef74291d2143e7bb55247b01c8bbd94995d995536f70f0d19de1d79d7e38c`.
O membro `itr_cia_aberta_composicao_capital_2026.csv` tem SHA
`73748b0cb8e0b8d9da75c0f24b9205a57ba9aa0c8d8ee73da83689ce728c15ed`.
Locador: registro959 sem cabeçalho, linha física960 com cabeçalho, JBS N.V.,
CNPJ49.115.815/0001-05, data30/06/2026, versão1; campos CAP_INTEGR e TESOURO.

Na leitura delimitada dos quadros trimestrais completos, não foi localizado
denominador médio interino ou quadro consolidado de tesouraria em quantidades.
Outros fatos NumberOfSharesOutstanding pertencem a quantidades de contratos
derivativos de gado/grãos, com contextos próprios; não são ações da JBS.
O Q2 explica que a adoção voluntária de formulários domésticos preserva o status
de emissor privado estrangeiro e o padrão IFRS/IASB anual e IAS34 interino.

Para selecionar um denominador, falta conciliação primária das definições,
classes, tesouraria, datas e escalas no mesmo grão, além de denominadores
interinos publicados diretamente. Não reconstruir ações por EPS arredondado
ou dividendos. Datas de auditoria, metadados PDF, recepção local e publicação
primária são evidências distintas; não retroagir posse operacional.

Os quadros inteiros, localizadores, imagens, recibos e confrontos em código
ficam no estudo interno `.cdp/estudos/20261010-jbs-ponte-capital-anual/`.
O ROOT recebeu 58 artefatos, 20 origens e 19 cópias; os 31 artefatos do estudo
trimestral anterior permanecem intactos. Essa custódia local não comprova
qualificação financeira nativa ou disponibilidade histórica para a operação.

## Adendo documental — DFP2025 e Item 16E

Na composição de capital da DFP2025, JBS N.V. (CNPJ 49.115.815/0001-05), em 31/12/2025, versão 1, informa 1.109.058.185 ações de capital integralizado e 94.537.534 em tesouraria. JBS S.A. aparece em registro distinto, com outro CNPJ. Esses campos não foram adotados como substitutos de ações outstanding.

Locador: [ZIP CVM DFP2025](https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_2025.zip), membro `dfp_cia_aberta_composicao_capital_2025.csv`, linha física 505 com cabeçalho; S.A. na linha 86. Cabeçalho identifica campos QT_ACAO_TOTAL_CAP_INTEGR e QT_ACAO_TOTAL_TESOURO. Os hashes do ZIP e do membro estão registrados na custódia abaixo.

A nota 20 anual distingue quantidades de ações e valores em milhares de USD. A abertura de tesouraria aparece como travessão e permanece numericamente ausente. O Item 16E divulga a recompra de 41.008.292 ações classe A no programa descrito; esse fluxo não substitui o estoque final de tesouraria. A divergência de quantidades por classe entre capa e nota 20 permanece em aberto, assim como a conciliação entre estoque, tesouraria e média anual de EPS. Nenhuma quantidade foi selecionada para valuation.

Locador: [20-F anual SEC](https://www.sec.gov/Archives/edgar/data/1791942/000121390026034213/ea0282342-20f_jbsnv.htm), nota 20 a/c1, Item 16E, nota 23 para a definição da média de EPS e capa para outstanding. Não transportar moeda BRL do outro bloco do PDF composto nem converter legenda/scale por inferência. A data de referência é 31/12/2025; primeira publicação UTC e posse operacional não foram autenticadas por este estudo.

Custódia deste adendo: ZIP DFP2025 SHA-256 `d7aec54e7c67998e4cd3ef94c463ab247f09a6baaa2254878d1e431f28130e2a`; membro composição de capital SHA-256 `f29b0e4bf6004cbb6d0758460d92cab5eb4807181786d668eb7c7cfe14593e6f`. O confronto final V2 conserva abertura numérica ausente e rollforward não autenticado; não foi reexecutado nesta passagem. Nenhuma adoção de quantidade, alteração financeira, OP, P0 ou PIT.
