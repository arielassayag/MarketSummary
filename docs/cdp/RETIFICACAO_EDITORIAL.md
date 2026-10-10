# Retificação editorial vinculada do relatório semanal

Um relatório semanal selado nunca é regravado. Este fluxo anexa uma nota que corrige somente
a indicação do lado final de um emissor. O texto novo vem do código usando o fato publicado
`mud.<emissor>.depois`, sem refazer decisão, efetivação, marcação, registro diário ou NAV.

## Entrada e autenticação

O comando `weekly rectify-report --date AAAA-MM-DD --mind <mente>` mostra o schema
`RetificacaoSemanal`. Escreva um JSON novo em `.cdp/retificacoes/<data>.json`. Use a mente da
execução, o hash do evento original `WEEKLY_CLOSE_REPORT`, um corpo completo que confira com
o hash do payload daquele evento e os hashes atuais dos arquivos originais `comentario.json`
e `factbook.json`.

O payload original contém `md`, `html`, `md_sha256`, `html_sha256`, `registro`, `factbook`,
`comentario_da_mente`, `apontamentos` e `tipo`. Este fluxo admite somente comentário da mente
sem apontamentos no recibo original. O evento guarda o hash do payload, não seu corpo. A saída
de `weekly close-report --publish` contém `relatorio`, `comentario_da_mente`,
`apontamentos_comentario` e `tipo`, mas omite `registro` e `factbook`; a saída de preparação
também não fornece esses dois hashes. Não prometa recuperar o corpo completo de uma única
saída nem afirme que esse corpo foi persistido originalmente.

Se o corpo original completo não foi observado, admitem-se somente cópias determinísticas
de campos observados, com a recomposição declarada como derivada:

- `md`, `html`, `md_sha256` e `html_sha256`: os quatro campos de `relatorio` na saída original
  da publicação local; os arquivos físicos preservados devem conferir com eles.
- `registro`: o valor literal de “Registro diário do fechamento” na seção Integridade do
  relatório selado, conferido com `record_hash` do registro diário original quando disponível.
- `factbook`: o valor literal de “Base de fatos da semana” na mesma seção. A validação o
  confronta com `FactBook.factbook_hash()` do corpo preservado de `factbook.json`; esse hash de
  objeto é distinto do SHA-256 do arquivo, que vai em `factbook_original_sha256`.
- `comentario_da_mente` e `tipo`: os campos homônimos da saída original da publicação local;
  `apontamentos`: cópia literal de `apontamentos_comentario` daquela saída.

Registre quais evidências forneceram cada campo e que o corpo é recomposto, sem atribuir
autoria, data de coleta ou persistência histórica ao recibo novo. Falta de qualquer fonte
necessária, corpo incompleto ou divergência do hash ao evento bloqueia a retificação. Não
inferir valores só do hash, nem chamar preparação, `calcular_semana`, modelos, fechamento ou
publicação do relatório para reconstruir o recibo. O código cruza o corpo completo com o
evento encadeado, os hashes dos relatórios e o FactBook
preservado. Os hashes atuais dos insumos não comprovam quando foram coletados ou quem os
escreveu; o trecho corrigido deve constar nos dois relatórios originalmente autenticados.

Em `correcoes`, informe o `emissor` e seu `texto_original` exato, copiado do racional selado.
Não escreva peso novo, retorno, NAV ou texto substituto: o código produz a indicação final de
comprada, vendida ou zerada. Peso ausente, não finito, com unidade distinta de percentual ou
de outro emissor é recusado, sem inventar posição zero. O racional precisa conter uma
contradição direcional canônica comprovada no texto renderizado; frase correta ou neutra não
autoriza errata. Cada par de evento original e emissor admite uma única retificação, ainda
que a mente, o texto ou o id de uma tentativa posterior mudem. Emissores distintos do mesmo
relatório podem receber suas próprias correções legítimas.

Valide sem escrita:

```sh
uv run python -m cdp weekly rectify-report --date AAAA-MM-DD --mind <mente> --arquivo .cdp/retificacoes/AAAA-MM-DD.json
```

## Execução e retomada da publicação

Após a integração em `main`, uma sessão de operador explicitamente autorizada pode precisar
atualizar somente as fontes do executor antes do primeiro gate novo, pois o gate de uma
versão antiga não conhece a pendência editorial. Nesse caso, use a sincronização canônica
`uv run python -m cdp sincronizar --executar`, preserve as diferenças do livro e interrompa
se o comando devolver `acao: "parar"`. Essa atualização pertence à sessão de operador,
antes de adquirir a execução/trava nova; não autoriza gravação financeira, edição do livro
ou contato automático com outro chat. Rotina agendada com `executar: false` responde o
motivo e encerra, sem sincronizar, repetir gate ou usar `--manual` como recuperação.

Somente no executor designado e com gate diário normal que devolva `executar: true`, use a
execução nova e sua trava legítima. A agenda expõe `retificacao_editorial`; o gate reconhece
a pendência sem recolocar fechamentos ou o relatório original entre as etapas financeiras.
Se um operador autorizado pelo humano atuar fora do horário, a entrada é a prevista no
roteiro diário com `--manual`; este documento não autoriza um novo disparo ou contornar no-op.

Com os valores devolvidos pelo gate, anexe a nota:

```sh
uv run python -m cdp weekly rectify-report --date AAAA-MM-DD --mind <mente> --arquivo .cdp/retificacoes/AAAA-MM-DD.json --publish --execucao <execucao> --trava <trava.id>
uv run python -m cdp agenda
uv run python -m cdp verify
```

`--publish` deste comando cria somente a nota local e o evento
`WEEKLY_EDITORIAL_RECTIFICATION`; não faz commit nem push. A nota fica em
`reports/semanal/<data>/retificacoes/<id>/`, com JSON, Markdown e HTML novos. O original e os
eventos anteriores permanecem literais. Uma tentativa repetida não sobrescreve a nota.

Depois da integridade e do painel previstos no roteiro diário, use exclusivamente o
publicador normal:

```sh
uv run python -m cdp publicar --tarefa <tarefa-diaria> --mensagem "CDP: retificação editorial semanal" --execucao <execucao> --trava <trava.id>
uv run python -m cdp trava liberar --id <trava.id>
```

O contrato existente do escritor exclusivo publica todas as diferenças locais nos caminhos
da tarefa, incluindo o conjunto anterior que ainda não foi publicado e a nota nova. O campo
`anteriores` identifica diferenças que já existiam no retrato inicial do gate novo. Não
atribui autoria passada a esse retrato e não modifica o recibo da execução antiga. Preserve
um recibo atual literal da saída de `cdp publicar` com `execucao`, `trava`, `arquivos`,
`anteriores`, `commit`, `push` e `verify`. Sem push confirmado, a publicação continua local.
Nenhuma adoção genérica ou caminho alternativo de Git foi acrescentado.

O portal mantém o relatório original e mostra uma indicação explícita com link para a nota.
A agenda distingue emissores pendentes de corrigidos. Divergência dos originais, da nota ou
da trilha impede a integridade e a publicação remota. Falha parcial ao anexar pode deixar
artefato/evento órfão; isso é detectado e exige diagnóstico, sem limpeza ou reparo tácito.

## Defesa para relatórios futuros e limites

O schema do comentário passa a admitir `lado_depois`. Quando presente, esse campo deve
conferir com o fato; o código acrescenta a indicação determinística ao racional renderizado.
Também confere no texto final renderizado um vocabulário finito, como “entrou comprada”,
“está vendida”, “ficou zerada” e “posição final comprada”, incluindo as palavras trazidas por
placeholders. Token ausente, inválido ou aninhado não ganha aceite; o comentário inválido
continua a seguir o fallback determinístico. Agenda, necessidade da errata e comentário
futuro compartilham essa leitura finita. Não valida toda linguagem natural nem garante todas as explicações
financeiras do comentário. O FactBook futuro ganha um fato textual de lado; os pesos e demais
cálculos financeiros permanecem os do código. Os FactBooks históricos não são regenerados.

Texto da mente que foi recusado e não integrou os relatórios selados não é mostrado como
pendência editorial. Relatórios sem insumos observáveis são `nao_observados`, sem transformar
ausência em aprovação. Uma correção íntegra não representa revisão financeira, PIT ou P0.
