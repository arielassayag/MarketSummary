# MCP de leitura — técnicas portáteis

O extra opcional `mcp` usa o SDK Python oficial **2.3.0**. A entrada
`cdp-tecnicas-mcp` serve STDIO; também é possível iniciar
`python -B -m cdp.mcp_readonly`. O host fornece o processo e troca mensagens nos
pipes; não há porta, endpoint HTTP ou chave de API. A instalação e o comando
dependem do pacote escolhido pelo operador. O servidor nunca instala dependências
por conta própria. Sem o extra, a entrada encerra com código 2 e mensagem em stderr.

O módulo `build_server()` permite ensaio em memória com `Client(server)` do SDK.
Importar `cdp.mcp_readonly` não inicia o servidor. Stdout fica com o protocolo;
bytecode é desligado antes de importar SDK e técnicas na entrada STDIO.

## Ferramentas disponíveis

| Nome | Operandos declarados | Unidade de saída |
|---|---|---|
| `calcular_ke` | rf, beta, erp, lam, crp finitos | taxa decimal, base USD |
| `avaliar_pb_justificado` | roe, ke, g escalares/arrays; estrito | múltiplo adimensional x |
| `estimar_preenchimento` | ordem inteira assinada, capacidade e preço em USD | ações inteiras assinadas |

As três rotas delegam aos kernels de [TECNICAS.md](TECNICAS.md); não escolhem fonte,
premissa, quantidade de capital, classe ou razão ADS/ADR. Taxas usam decimais na
base temporal declarada pelo chamador; beta e lambda são adimensionais. Preço é
USD por ação da linha e capacidade é USD. Estimativa não efetiva ordem.

O servidor aplica schemas fechados, inclusive nos objetos aninhados, **antes** do
delegate e valida a saída antes do envio. Campo extra, bool no lugar de número,
texto numérico, ausência exigida e número não finito são recusados. A quantidade
inteira fica no intervalo seguro de JSON interoperável ±(2**53−1); esse limite é
do transporte. Hints read_only/open_world são informação para o host: não substituem
essas guardas. Nome desconhecido, shell, writer ou kill switch não tem delegate.

PB usa objetos `{tipo:"escalar",valor:numero}` ou
`{tipo:"array",forma:[inteiros],valores:[numero|{tipo:"ausente"}]}`. A forma é row-major, com
até quatro dimensões, eixo até 128 e até 10.000 células inclusive no broadcast.
Forma vazia é escalar de array; eixo vazio e forma inconsistente são recusados.
Ausência explicitamente declarada por `{tipo:"ausente"}` pode ocupar um operando
inteiro ou uma célula; vira apenas NaN no delegate, nunca zero. Null na entrada
numérica é recusado. O Client SDK observado normaliza NaN para null no transporte;
o objeto de ausência mantém essa normalização fora do ingresso numérico aceito.
No modo estrito, a recusa nativa de crescimento/custo é preservada. O retorno
conserva shape, valores e estados por célula. NaN/infinito produzidos pelo kernel
aparecem como null acompanhado de estado explícito; não são números JSON ilegais.

Capacidade ou preço finitos não positivos conservam o preenchimento zero nativo.
Operandos ausentes/não finitos são recusados mesmo com ordem zero. Nenhum recurso
de execução, conversão cambial, ADV ou book é completado automaticamente.

## Recursos

`cdp://tecnicas/catalogo` lista os três contratos, unidades e hashes dos schemas.
`cdp://exemplos/latam_simulado_v1/manifesto` e as nove URIs de membros do exemplo
entregam um envelope JSON com conteúdo UTF-8 original, MIME original, SHA-256,
**EXEMPLO / DADOS SIMULADOS**. A listagem apresenta todas as URIs aceitas.

Os corpos vêm dos recursos do pacote e do parser nativo, com conferência de
manifesto e membros. Nenhum caminho arbitrário é resolvido: não há fallback para
cwd/configs, URI file/http, query, fragmento, percent-encoding alternativo ou `..`.
Exemplo íntegro não prova premissa financeira, PIT ou autoridade do executor.

## Fronteira operacional ainda pendente

Estado, agenda, integridade, fatos operacionais, validação de documentos, carteira,
risco, modelos reais da cobertura e pacote da mente **não são ferramentas deste
MVP**. PASSAGEM §8.3 permanece uma próxima entrega. Runtime.book cria Book;
Book e AuditLog fazem mkdir na construção, inclusive através de TrackRecord.
Validar tese/nota pode chamar prepare quando fatos faltam. O comando de risco
grava relatório e pode consultar intraday; o pacote da mente CLI grava --saida.

O próximo delta precisa de ReadOnlyBook/Audit/Track/Store e configurações/raízes,
relógio, cortes e fontes explicitamente recebidos. Falta deve virar indisponível,
sem preparar ou coletar. Verificação semântica, disponibilidade/PIT e integridade
de bytes permanecem resultados distintos. Decomposição de risco requer facade
própria com índices/unidades e preservação de contribuições negativas/NaN.

## Verificação e compatibilidade

Os focais usam Client em memória, confronto com delegates nativos, schemas de
entrada/saída, recusas e leitura integral do exemplo. O ensaio STDIO usa a entrada
instalada e cwd vazio, com guarda de rede/escrita no processo filho; nenhum teste
HTTP é necessário. Essas guardas qualificam os ingressos ensaiados, sem afirmar
isolamento universal do processo. O extra fica separado das rotas existentes;
esta entrega não concede permissão de operação ou modifica agendamentos.

SDK: [v2](https://py.sdk.modelcontextprotocol.io/),
[Server de baixo nível](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/),
[Client em memória](https://py.sdk.modelcontextprotocol.io/get-started/testing/),
[publicação 2.3.0](https://pypi.org/project/mcp/2.3.0/).
Qualificação em hosts e sistemas adicionais continua pendente.
