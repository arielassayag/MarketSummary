# Enel Chile — perímetro documental de financiamento

Estudo documental recebido em 10/10/2026. **Composição financeira, dívida líquida, G19, P0 e PIT continuam sem aprovação.** O pacote anual opt-in integrado em `96c7594` não foi ativado no carregador operacional.

A fonte é o [20-F de 2025, instância completa na SEC](https://www.sec.gov/Archives/edgar/data/1659939/000110465926050251/enic-20251231x20f_htm.xml), CIK1659939, accession1104659-26-050251. Corpo integral: 38.598.294 bytes, SHA-256 `fe0cb64242a503309cf75c5a4ed292569073ea6c0014ec351c5d5c2485566102`. Recepção atual não demonstra posse histórica pelo executor. O período anual não substitui balanço interino.

Foram extraídos e lidos a Nota 6 inteira, a tabela de ativos financeiros e, em rodadas documentais separadas, as Notas 10, 4, 7, 20 e 23 inteiras. XML, contextos, cabeçalhos, períodos, moedas, células e ausências foram preservados em custódia local; não houve API financeira, modelo ou cálculo de dívida líquida.

| Fonte e grão | Conclusão documental | Consequência para a futura composição |
|---|---|---|
| Nota6(a), caixa e equivalentes | Depósitos curtos e recompras descritos na nota já pertencem ao caixa apresentado | Não deduzir esses instrumentos uma segunda vez como aplicações |
| Tabela de ativos financeiros | Recebíveis, participações e derivativos têm naturezas distintas | O rótulo de ativo financeiro não demonstra elegibilidade como caixa; os demais ativos a custo amortizado precisam de qualificação |
| Nota6(f), conciliação de financiamento | Relacionadas, empréstimos, hedges e arrendamentos aparecem em categorias distintas | O subtotal de empréstimos da Nota20.1 não estabelece sozinho todo o perímetro econômico |
| Nota10.1(b)/(e), empréstimos relacionados | Há empréstimos remunerados com Enel Finance International, contraparte com controladora comum | A relação de grupo não autoriza eliminar o saldo; demonstrar a exclusão mútua com a Nota20.1 antes de compor |
| Total de contas a pagar relacionadas | Também inclui dividendos, serviços e outras naturezas | Não promover o total geral a principal de empréstimos |
| Nota10.1(d), fluxos não descontados | Calendário contratual difere do saldo contábil | Não substituir saldo de dívida por fluxo futuro nem somar as duas apresentações |
| Nota10.1(e)(iv–v), linhas comprometidas | Disponibilidade de linhas é apresentada separadamente | Limite disponível não comprova principal sacado |

A companhia declara eliminação das transações internas ao perímetro consolidado. Essa declaração não elimina automaticamente uma contraparte externa ao perímetro apenas por compartilhar a controladora. Recebível e obrigação com a mesma contraparte não demonstram direito de compensação.

As quatro notas adicionais esclarecem a classificação, mas não completam a composição:

| Fonte | Evidência recebida | Limite de uso |
|---|---|---|
| Nota 4, políticas | Caixa exige liquidez, conversibilidade e baixo risco; classificação corrente possui prazo distinto. Passivos a custo amortizado, leases e derivativos têm mensurações próprias | Ativo corrente ou a custo amortizado não se torna aplicação elegível por esse rótulo |
| Nota 7 inteira | Outros ativos amortizados aparecem por prazo de apresentação | Natureza, finalidade, prazo original, liquidez e restrições não foram identificados; não selecionar a rubrica nem substituí-la por zero |
| Notas 20.1 e 20.2 | Empréstimos bancários e títulos são apresentados em subtotal e detalhe | Não somar o detalhe novamente; principal, juros, taxas e saldo contábil ainda exigem ponte |
| Notas 20.4 e 20.5 | Limites disponíveis e fluxos contratuais futuros são apresentações distintas | Não promover disponibilidade ou fluxo não descontado a dívida efetivamente sacada |
| Nota 23 | Categorias relacionadas, empréstimos e derivativos são separadas; hedges têm finalidades de dívida, receita e imobilizado | Valor justo e nocional de derivativo não são principal; relação de hedge não autoriza compensação automática |
| Nota 4, compensação | A política geral exige direito legal e intenção de liquidação líquida ou simultânea | Direito e intenção específicos não foram demonstrados para o agregado estudado |

Falta a ponte determinística entre principal, juros, custos de mensuração e saldos canônicos, com exclusão mútua dos participantes. A documentação recebida ainda não justifica composição financeira completa. O perfil anual integrado cobre somente empréstimos e arrendamentos, mantém a composição desabilitada e não autentica caixa ou aplicações por extensão. O contexto genérico de outro provedor e moeda não substitui um contrato próprio para SEC/USD.

G19 depende das datas dos fatos de patrimônio e resultado efetivamente selecionados pelo percurso nativo. A data de dívida ou a existência do documento anual não fornece essas datas. Contexto ativo, mercado, parâmetros e consumo completo continuam sem prova. Nenhuma ausência foi preenchida por zero, nenhum alvo ou confiança foi alterado e nenhum passivo foi excluído por hipótese.

A leitura aplica a disciplina de fonte primária e conciliação do plugin Public Equity Investing. Ela qualifica a pesquisa recebida; não aprova os modelos nem a publicação operacional.

## Adendo de 10/10/2026 — ponte reportada da Nota 6(f)

A conferência posterior, recebida e validada independentemente pela ROOT, confirmou em Python **sete correspondências entre notas e cinco fechamentos aritméticos** da reconciliação reportada. A fonte permanece o [XML anual completo da SEC](https://www.sec.gov/Archives/edgar/data/1659939/000110465926050251/enic-20251231x20f_htm.xml), SHA-256 `fe0cb64242a503309cf75c5a4ed292569073ea6c0014ec351c5d5c2485566102`. O quadro abaixo transcreve quatro categorias e seu total; **não calcula dívida líquida do CDP**.

| Linha reportada em 31/12/2025 | Total literal, ThUS$ | Remissão primária |
|---|---|---|
| Empréstimo relacionado específico EFI | `1,028,632` | Nota 10.1(b), linha de Enel Finance International NV, descrição Loan payable |
| Empréstimos com juros | `2,420,827` | Nota 20.1; os bonds da 20.2 são detalhe, não participante adicional |
| Hedges de fluxo de caixa de financiamento | `52,334` | Nota 23.2(a), finalidade Finance debt, com ativo e passivos separados |
| Arrendamentos | `410,197` | Nota 21, remissão expressa na reconciliação |
| Fechamento reportado | `3,911,990` | Nota 6(f) |

Locadores da extração documental: bloco IFRS2025 `DisclosureOfCashAndCashEquivalentsExplanatory`, ordinal global XML 6130; tabela 10, linhas 16–20, índices zero-based. As parcelas EFI corrente/não corrente correspondem à Nota 10.1(b), tabela 3, linha 25; os empréstimos à Nota 20.1, tabela 1, linha 7; os hedges à Nota 23.2(a), tabela 9, linha 5. Isso sustenta categorias distintas na própria ponte reportada, sem depender somente da ausência de EFI na lista bancária. O ativo de hedge com sinal invertido nessa reconciliação **não comprova direito legal de compensação nem autoriza netting econômico**.

A Nota 10.1(e)(i–iii) descreve principais de US$400 milhões, US$300 milhões e US$322 milhões, juros de ThUS$4,070 e ThUS$1,934 e ausência explícita de juros acumulados no terceiro contrato. A comparação determinística dessas parcelas, `1,028,004` ThUS$, com o saldo EFI reportado, `1,028,632` ThUS$, deixa **residual de 628 ThUS$, causa desconhecida**. Não foi atribuído a fee, arredondamento, hedge ou custo por hipótese; não houve ajuste do saldo.

Aplicações adicionais continuam desconhecidas: a Nota 7, tabela 0, linha 6, reporta `648` corrente e `2,714` não corrente em ThUS$, sem demonstrar natureza, prazo original, liquidez ou restrições. Caixa ainda exige contexto primário próprio; o tratamento econômico dos hedges e a mensuração completa permanecem pendentes. **E2/E3 não foram executados; G19, P0 e PIT continuam abertos.** A data desta conferência não certifica posse em 09/10; G19 continua dependente dos fatos de patrimônio e resultado realmente consumidos.

O estudo privado `20261010-enel-e2e3-ponte-primary` está em `.cdp/estudos` no host de origem e não acompanha este arquivo pelo Git. Para examiná-lo em outro host, obter o pacote integral com recibos e selos e conferir seus corpos/M6 localmente. Para reproduzir pela fonte pública, receber o XML inteiro acima com data real de recepção, conferir bytes/SHA, extrair os blocos indicados preservando contextos, cabeçalhos, unidades e células, e conferir a aritmética em código Decimal; o resultado não habilita composição financeira. A pesquisa adicional fechou com três buscas e duas aquisições: o único corpo novo conservado era HTML de interrupção HTTP 200, não demonstração financeira, e não fundamentou o quadro.
