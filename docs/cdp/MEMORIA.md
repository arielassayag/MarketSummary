# Memória do CDP

A memória conserva lições e procedimentos entre sessões do Codex, Claude, Gemini e outros
aplicativos. Cada nota ajuda a localizar a evidência de uma alegação. A decisão da rotina vem do
gate e do roteiro. Fase, pendências, posições e números vêm do estado, da agenda, do livro e do
FactBook da etapa. Para o desenho e os experimentos que motivaram a escolha, veja a
[pesquisa de arquitetura](MEMORIA_PESQUISA.md).

## Consultar ao retomar

Siga primeiro o [roteiro de retomada](playbooks/RETOMAR.md). Em rotina agendada, respeite a
decisão do gate antes de consultar a memória. O código 10 encerra o disparo. Escolha o escopo
da tarefa para ver o índice breve ou procurar uma lição específica.

```sh
uv run python -m cdp memoria contexto --escopo desenvolvimento
uv run python -m cdp memoria contexto --escopo diario --formato json
uv run python -m cdp memoria contexto --escopo diario --consulta 'moeda do benchmark índice local'
uv run python -m cdp memoria buscar --escopo diario --consulta 'moeda do benchmark índice local' --limite 3
```

Use `--orcamento-estrito` na busca de evidências quando a saída precisar
caber em 4.500 bytes de texto. O cálculo usa UTF-8 e conta um byte entre
passagens. Cada passagem preservada tem até 14 linhas e 1.800 bytes.
O código conserva a ordem da busca e pula passagens inteiras que
ultrapassariam o teto. O limite se aplica aos trechos referenciados em
`passagens`; os metadados do JSON têm orçamento separado.
Busca, triagem e seleção aceitam consultas em uma linha de até 480
caracteres. O mesmo limite vale para o pacote lacrado e para o avaliador.

Os escopos são `desenvolvimento`, `operador`, `status`, `semanal`, `diario`, `risco`, `cobertura`
e `calibracao`. `contexto` mostra até três notas curadas em destaque no escopo, com orçamento de
6 KiB de saída em Markdown e JSON. `buscar` retorna separadamente notas elegíveis e
fontes primárias do escopo. O limite de resultados por lista vai de um a dez e o padrão é cinco.
Com `--consulta`, `contexto` seleciona até três notas pertinentes mesmo quando elas não
estão destacadas. Ele mantém o corte por data e revisão e o mesmo orçamento de saída.
A busca combina BM25 direto, passagens ranqueadas com contexto da seção e âncoras das notas.
A busca estrutural usa títulos, parágrafos e seções vizinhas dos mesmos documentos canônicos.
Seções Markdown curtas também podem ser recuperadas integralmente quando o corpo sustenta a consulta.
Ela pode ampliar uma passagem por inclusão literal ou ocupar uma vaga que ficou livre
quando uma passagem já estava integralmente contida em outra.
Flexões em português, títulos, etiquetas, resumos e trechos validados ajudam a localizar lições.
A lista `passagens` aproveita referências complementares da nota mais pertinente e reduz janelas
com forte sobreposição. Âncoras próximas da mesma nota podem ser reunidas sem cortar a evidência.
Uma passagem ocupa até 14 linhas e 1.800 bytes. Títulos e resumos ajudam na ordenação. O hash
continua vinculado ao trecho literal da fonte.
O retorno `fontes` contém os caminhos da busca direta, enquanto `notas` identifica os
registros recuperados. Cada passagem vem com linhas inclusivas e SHA-256.

Quando a busca reconhece um pedido de estado, `orientacao_atual` indica a fonte a consultar e
`destino_atual` oferece um identificador estável para auditoria. O retorno fica sem notas,
fontes históricas ou passagens. Use `--estado-atual` quando a intenção já estiver estabelecida.
A classificação automática depende da redação da pergunta.

Abra a fonte na revisão indicada e confira o trecho e seu contexto antes de usar a lição. O
resultado inclui caminho, linhas inclusivas e SHA-256 para as evidências das notas. Se faltarem
notas, houver ressalva ou o catálogo estiver indisponível, prossiga com o roteiro e suas fontes
canônicas. Para verificar o estado da operação, use o caminho indicado pelo próprio roteiro.

## Revisão Git e data

`contexto`, `buscar`, `propor` e `avaliar` capturam o `HEAD` local no início e leem os arquivos
dessa revisão do Git. Uma mudança de arquivo ainda fora do commit, inclusive no estágio do Git,
fica visível em `auditar` e fora das consultas. O `HEAD` local pode ser de um ramo de trabalho.
O hash da revisão informa os bytes consultados. A integração revisável é o processo que
estabelece a aceitação das notas operacionais.

`--data` usa `AAAA-MM-DD` e, quando omitido, usa o calendário de Brasília. É uma data para aplicar
revisão, vencimento e substituição às notas da revisão Git selecionada. Para uma consulta reproduzível, informe `--revisao` com o hash completo do commit Git
local e a `--data` de aplicação. Para um ensaio histórico, selecione a revisão que existia
no corte. A data filtra a elegibilidade dentro da revisão escolhida. Ela, sozinha, é
insuficiente para estabelecer disponibilidade histórica ou origem *point-in-time*.
A avaliação usa a data fixa do corpus.

## Seleção guiada de evidências

Use a seleção guiada para entregar ao agente trechos canônicos numerados. O pacote
combina as buscas direta, contextual e estrutural, as âncoras e as funções Python
pertinentes ao escopo. Ele inclui a consulta, a revisão, a data, os tamanhos em bytes
e o lacre do conjunto. Cada corpo é dado para leitura e referência.

```sh
uv run python -m cdp memoria buscar --escopo diario --consulta 'moeda do benchmark índice local' --candidatas
```

O agente devolve um JSON com `lacre` e `ids`, usando o lacre do pacote e os números
das passagens que, juntas, sustentam a consulta. O código valida a devolutiva e
resolve até cinco referências dentro do orçamento agregado de 4.500 bytes. Para
conferir, use a revisão e a data retornadas no pacote, repita a consulta e passe
o JSON pela entrada padrão.

Quando sobra espaço, a conferência pode incluir um bloco Markdown já lacrado
que completa a margem cortada de uma passagem selecionada. As escolhas recebidas
permanecem na mesma ordem.

O pacote preserva até 64 candidatas iniciais e acrescenta até 20 referências do
mesmo escopo. Elas recuperam itens de lista, trechos de código delimitados por
comentários e condições que começam antes de uma janela. Os complementos recebem
novos IDs. O teto da seleção permanece em cinco passagens e 4.500 bytes.

```sh
uv run python -m cdp memoria buscar --escopo diario --consulta 'moeda do benchmark índice local' \
  --revisao "$REVISAO_DO_PACOTE" --data "$DATA_DO_PACOTE" --conferir-selecao < selecao.json
```

Em consultas de estado ou fora do escopo, a lista de candidatas fica vazia.
O pacote e a conferência funcionam localmente a partir do Git.

Use `--explorar-fontes` nas duas chamadas para revisar também a intenção e
consultar as fontes que o pacote autoriza. O agente pode declarar `intencao`
como `evidencia`, `estado_atual` ou `fora_escopo`. Para evidência, pode enviar
`recortes` com `caminho`, `inicio` e `fim`, além de `ids`. Use intervalos de
linhas inclusivos da revisão indicada. O código lê cada recorte no Git, resolve
seu hash e conta as passagens e os bytes de toda a seleção. Uma passagem tem até
14 linhas e 1.800 bytes. Pedidos de estado ou fora do escopo exigem seleção vazia.
Para estado, o leitor pode enviar `destino_atual` com um dos códigos de
`destinos_permitidos`. O código devolve a orientação canônica do destino, sem
passagens históricas, e mantém o encaminhamento automático quando o leitor
omite o campo. Os bloqueios explícitos de escopo e segurança continuam prevalecendo.

Ao redigir uma resposta a partir dos recortes, associe cada afirmação à passagem que
a sustenta. Quando o procedimento documentado e a implementação vigente divergirem,
descreva a diferença e a fonte que sustenta cada versão. Para fatos operacionais,
consulte o destino indicado e faça o corte na execução pedida.

### Triar antes de recuperar

Para perguntas livres, `rotear` prepara uma devolutiva curta de intenção e destino.
O pacote contém a consulta, o escopo, as orientações canônicas e o lacre. O leitor
trata esse conteúdo como dados e devolve `lacre`, `intencao` e `destino_atual`.
O destino é obrigatório em `estado_atual` e nulo em `evidencia`, `fora_escopo` e
`indeterminado`. Para consultar o mapa com proveniência, use `--com-autoridades`.
Uma âncora que perdeu validade retira o cartão correspondente do pacote.
O formato `--formato prompt` reúne as instruções e o pacote lacrado para um leitor
em qualquer aplicativo. A conferência continua usando a devolutiva JSON.

```sh
uv run python -m cdp memoria rotear --escopo risco --consulta 'Que VaR consta no monitor de hoje?'
uv run python -m cdp memoria rotear --escopo risco --consulta 'Que VaR consta no monitor de hoje?' \
  --revisao "$REVISAO_DO_PACOTE" --data "$DATA_DO_PACOTE" --conferir < rota.json
```

A conferência de estado e a abstenção terminam com `notas`, `fontes` e `passagens`
vazias. O campo `catalogo_com_ressalvas` fica nulo porque o catálogo não foi lido.
O encaminhamento indica a autoridade a consultar. Uma decisão `indeterminado`
inclui `esclarecimento` para pedir o fato ou procedimento que a pessoa quer consultar
antes de selecionar uma autoridade. A execução segue os gates do CDP.
Pedidos explícitos para gravar, adulterar ou publicar registros operacionais ficam
fora da memória consultiva. Consultas sobre como o procedimento funciona continuam
passando pela busca documental. Para pedidos coordenados ou dirigidos ao agente,
a guarda compara o verbo, o efeito pretendido e o alvo protegido na mesma frase.
Citações e relatos de ocorrências servem de contexto para a consulta. Os
bloqueios determinísticos das rotinas continuam decidindo a execução.

Na busca automática, uma consulta já reconhecida como estado pode ter seu destino
refinado pelos critérios versionados de objeto e atributo. Uma alternativa só
substitui a orientação inicial quando os dois critérios aparecem em trechos
distintos da pergunta, a autoridade tem âncoras válidas e há margem sobre as demais.
O campo `refinamento_destino` registra o destino anterior, os critérios encontrados
e a origem verificada. Revisões antigas, cartões vencidos e empates conservam a
orientação inicial.

### Pontes documentais entre papéis

`rotear --candidatas --com-pontes` pode acrescentar até seis trechos curados
de outro papel depois de validar uma triagem de evidência. O mapa Git em
[`memoria/pontes.json`](memoria/pontes.json) registra o papel de origem,
os papéis de destino, os gatilhos, a validade e a prova literal com SHA-256.
O caminho precisa pertencer ao catálogo da origem. O trecho precisa ter
uma ocorrência exata na revisão consultada. Vencimento, mudança ou
ambiguidade da prova deixam a ponte fora do pacote.

Cada ponte aparece como um ID de candidata. `fontes_permitidas` conserva
os caminhos de origem da consulta e governa os recortes livres. Um ID de
ponte resolve somente o seu intervalo. A lista de candidatas usuais fica
na mesma ordem. A seleção final continua limitada a cinco passagens e
4.500 bytes. As saídas de estado, fora do escopo e indeterminado continuam
sem consultar o mapa de pontes.

```sh
uv run python -m cdp memoria rotear --escopo calibracao \
  --consulta 'Como verificar a procedência de uma versão publicada no portal?' \
  --revisao "$REVISAO" --data "$DATA" --candidatas --com-pontes < triagem.json
uv run python -m cdp memoria rotear --escopo calibracao \
  --consulta 'Como verificar a procedência de uma versão publicada no portal?' \
  --revisao "$REVISAO" --data "$DATA" --conferir-selecao --com-pontes < selecao-roteada.json
```

Use a mesma revisão, data e opção nas duas chamadas. A segunda entrada
contém `triagem` e `selecao`. O lacre vincula a lista de pontes à seleção.
O mapa é curado por revisão de Git e o leitor o recebe apenas como
trechos para citar. A opção é experimental.

Na revisão da memória, use a auditoria para separar uma ponte vencida,
uma fonte que perdeu autoridade na origem, um destino que já ganhou
acesso direto e uma prova ausente ou ambígua. A saída tem os IDs, os
papéis, as datas, o estado de cada ponte e o hash do mapa. Ela serve
de fila para a curadoria e para a próxima avaliação de recuperação.

```sh
uv run python -m cdp memoria auditar --pontes --revisao "$REVISAO" --data "$DATA"
```

O código de saída 1 indica um item que exige revisão. Valide a nova
prova e o papel destinatário antes de alterar o mapa em Git.

### Rever pedidos de alteração antes da triagem

`--pacote-escopo` prepara uma leitura opcional de pedidos de mutação ou burla.
O pacote contém a consulta e o lacre. Se `bloqueio_escopo` já for verdadeiro,
`--conferir-escopo` aplica a regra sem esperar uma leitura. Nos demais casos,
entregue o prompt a um leitor e devolva seu JSON à conferência.

```sh
uv run python -m cdp memoria rotear --escopo operador --consulta "$CONSULTA" \
  --revisao "$REVISAO_DO_PACOTE" --data "$DATA_DO_PACOTE" --pacote-escopo --formato prompt
uv run python -m cdp memoria rotear --escopo operador --consulta "$CONSULTA" \
  --revisao "$REVISAO_DO_PACOTE" --data "$DATA_DO_PACOTE" --conferir-escopo < escopo.json
```

Para recusar, o leitor identifica trechos literais de pedido, efeito e alvo.
A conferência exige ocorrências únicas, efeito dentro do pedido e um pedido
que vá além de uma citação isolada. Os recortes aparecem como posições da
consulta, com início inclusivo e fim exclusivo. O julgamento semântico continua
com o leitor. A recusa retorna `fora_escopo` com histórico vazio. Uma consulta
preservada retorna `triagem_necessaria` e segue para a escolha normal de intenção
e destino. As proteções das rotinas continuam governando a execução.

### Verificar uma ambiguidade antes de abrir fontes

Para uma triagem inicial de estado ou evidência, `--pacote-ambiguidade` recebe o
JSON da triagem. Repita a consulta, a revisão, a data, o limite e as opções do
pacote original. Com `--formato prompt`, a saída pode ser entregue a outra
sessão de leitura. Ela recebe a pergunta e os destinos, com um lacre vinculado
à triagem inicial. O pacote omite a decisão inicial e os trechos históricos.

```sh
uv run python -m cdp memoria rotear --escopo diario --consulta 'A versão de ontem já saiu?' \
  --revisao "$REVISAO_DO_PACOTE" --data "$DATA_DO_PACOTE" \
  --pacote-ambiguidade --formato prompt < triagem.json
uv run python -m cdp memoria rotear --escopo diario --consulta 'A versão de ontem já saiu?' \
  --revisao "$REVISAO_DO_PACOTE" --data "$DATA_DO_PACOTE" \
  --conferir-ambiguidade < verificacao.json
```

`verificacao.json` contém as chaves `triagem` e `verificacao` com os dois
objetos originais. A conferência aceita duas interpretações com intenções
ou destinos diferentes, uma lacuna a esclarecer e o lacre do pacote. A
triagem resultante é compatível com `--conferir` e `--candidatas`.
Esse passo opcional conserva a decisão inicial ou pede esclarecimento.
A plausibilidade das duas leituras é avaliada pelo leitor. O código confere
a estrutura, o vínculo e os destinos permitidos. Se o segundo leitor devolver
uma análise inválida, a conferência a rejeita.

Use `--ancorar-ambiguidade` tanto ao preparar quanto ao conferir para exigir
um `ato` em cada interpretação. O código recorta trechos literais da consulta,
numera os recortes e lacra as posições. Uma mudança para indeterminado exige que
as duas leituras apontem para o mesmo ato. Esse vínculo pode ser conferido sem
ler o catálogo. A regra semântica continua sendo responder ao mesmo objeto e
atributo, distinguindo informação incidental de um pedido independente.

### Recuperar após a triagem

Para uma triagem de evidência, `--conferir` faz a recuperação automática. Se precisar
da seleção guiada, use `--candidatas` com a mesma `rota.json`. O pacote de candidatas
carrega `lacre_rota` e conserva o teto de cinco passagens e 4.500 bytes. Para conferir
a seleção, use `--conferir-selecao` e passe um único objeto com `triagem` e `selecao`.
Repita consulta, revisão, data, limite e a opção `--com-autoridades` do pacote original.
O código reconstrói e confere os dois lacres. A seleção conserva a intenção da triagem.

## Registrar uma lição

Em desenvolvimento, escolha uma descoberta reutilizável com evidência em `AGENTS.md`, em um
Markdown de `docs/cdp/` ou em código Python de `src/cdp/` e `tests/cdp/`. O conteúdo da própria
memória e seus manuais ficam fora desse conjunto. O catálogo registra contexto durável e aponta
para fontes do repositório. Informação efêmera de mercado, dados brutos, transcrições de
aplicativos e recibos privados pertencem às respectivas fontes e não entram nas notas.

Numere as linhas da fonte com `git show HEAD:src/cdp/research/factbook.py | nl -ba`. Neste exemplo,
as linhas 432 e 433 no `HEAD` usado na implementação dão a unidade dos indicadores de nível.
Reconfirme as linhas quando a fonte mudar. O comando gera a candidata em stdout para revisão.

```sh
uv run python -m cdp memoria propor --escopo diario --id benchmark-nivel-indice --tipo licao \
  --evidencia src/cdp/research/factbook.py --linhas 432:433 --data 2026-11-07 \
  --titulo 'Indicadores em nível de índice' \
  --resumo 'A variação de indicadores dessa classe é expressa em nível de índice.'
```

O resultado tem os seguintes campos. O arquivo pode ser salvo em desenvolvimento como
`docs/cdp/memoria/notas/<id>.json`, com o mesmo identificador no nome e no corpo.

```json
{
  "id": "benchmark-nivel-indice",
  "tipo": "licao",
  "estado": "candidata",
  "titulo": "Indicadores em nível de índice",
  "resumo": "A variação de indicadores dessa classe é expressa em nível de índice.",
  "escopos": ["diario"],
  "tags": [],
  "registrada_em": "2026-11-07",
  "revisada_em": null,
  "rever_em": null,
  "destaque": false,
  "substitui": [],
  "evidencias": [
    {
      "caminho": "src/cdp/research/factbook.py",
      "trecho": "    if symbol in _LEVEL_INDICATORS:\n        return \"variação do nível do índice\"",
      "sha256": "7fe6f48fd67713fa8a4982495410689343f249fcae48d2791221b7138bcfd1da"
    }
  ]
}
```

Use um identificador de 2 a 64 caracteres, com letras minúsculas ASCII, dígitos e hífens entre
partes. Os tipos são `procedimento`, `licao` e `episodio`. Título, resumo e etiquetas são texto
simples em uma linha, com limites respectivos de 100, 420 e 48 caracteres. Uma nota pode ter
até oito etiquetas, até oito substituições e de uma a quatro evidências. O trecho de cada
evidência deve ocorrer uma única vez na fonte, como sequência de linhas inteiras, e o SHA-256
corresponde aos bytes UTF-8 do trecho unido por LF, sem quebra final. Para outras evidências,
gere candidatas da mesma forma e reúna seus objetos de evidência na nota sob revisão.

## Auditar, revisar e retirar

```sh
uv run python -m cdp memoria auditar
uv run python -m cdp memoria auditar --data 2026-11-07
uv run python -m cdp memoria auditar --revisao-git
```

`auditar` lê a árvore de trabalho e imprime contagens, problemas e `fila_de_revisao`. Use
`--revisao-git` para auditar o `HEAD`; no Windows, essa é a forma disponível. A fila
inclui candidatas, validade vencida, duplicidade de resumo no mesmo escopo, similaridade lexical
e problemas de fonte ou vínculo. A saída é 1 quando há problemas de validação ou a leitura
falha. Uma fila com sugestões de revisão pode coexistir com saída 0. O comando produz o
diagnóstico de consolidação. A reflexão sobre relevância, contradição semântica e suficiência da
evidência cabe a quem revisa, com as fontes abertas.

1. Compare o resumo com a evidência e com notas existentes. Confira se a lição continua correta
   e se o escopo é necessário. Descarte uma candidata redundante ou ajuste o texto e as fontes.
2. Para aceitar a nota, proponha no diff `estado: "curada"`, `revisada_em` e `rever_em`, com
   `registrada_em` até `revisada_em`, e `rever_em` posterior à revisão. `destaque` serve a lições
   cuja descoberta antecipada vale o espaço no índice. A consulta admite uma nota curada desde a
   data de revisão e deixa de admiti-la a partir da data `rever_em`, inclusive.
3. Para substituir uma lição, use um novo ID, data de registro posterior e escopos que cubram
   os da nota anterior. Inclua o ID anterior em `substitui` e valide a evidência na mesma
   revisão Git que registra a sucessora como curada. A sucessão comprovada persiste quando
   a sucessora vence, perde sua evidência atual ou é retirada. Se a prova falhar na primeira
   revisão, corrija e registre a sucessora em outro commit. A leitura precisa de histórico
   local completo e verifica até 128 revisões e 1.024 mudanças de arquivos de notas.
4. Uma nota curada que perdeu utilidade pode passar a `retirada`, mantendo datas, fonte e
   histórico no Git e com `destaque: false`. Para renovar a validade, confira a fonte atual e
   proponha novas datas. Preserve a razão da mudança no diff e no registro da integração.
5. Audite antes de integrar. No checkout da revisão aceita, repita a consulta de exemplo e a
   avaliação para verificar o que ficou elegível.

Os cinco comandos leem arquivos e imprimem resultados. A proposta e a fila não gravam arquivos,
promovem notas, agendam revisões ou publicam. A consolidação pode aproveitar ajuda de um agente
em sessão de desenvolvimento, com suas mudanças apresentadas como diff para revisão.

## Dreaming e wiki de leitura

A rotina [dreaming](playbooks/DREAMING.md) revisa o catálogo aos sábados. O plano usa
uma revisão Git, limita a fila a 12 unidades por página e registra data, origens e
hashes. A ordem começa por problemas de evidência e linhagem, passa por vencimentos,
candidatas e semelhanças, e termina em fontes alteradas. A janela padrão de 14 dias
se sobrepõe entre sábados. Quando for necessário cobrir um intervalo maior, informe
a última revisão examinada com `--desde` e use `--pagina` para alcançar os itens
adiados na mesma revisão. O índice identifica os tópicos que já têm notas curadas.

```sh
uv run python -m cdp memoria sonhar --exigir-provas
uv run python -m cdp memoria wiki --escopo desenvolvimento
```

A rotina usa `fonte-sonho` para ler apenas as notas e as passagens autorizadas pelo
item na revisão fixada. A leitura por intervalo limita o retorno a 40 linhas e 4 KiB.
Cada item exige uma disposição e sua justificativa. A devolutiva traz o SHA-256 do
plano, cobre todos os IDs selecionados e pode anexar novas notas candidatas
no esquema deste manual. A curadoria compara fontes quando elas divergem.
Valide o JSON da devolutiva pela entrada padrão, com os mesmos parâmetros do plano.

```sh
uv run python -m cdp memoria conferir-sonho --exigir-provas \
  --revisao "$REVISAO_DO_PLANO" --data "$DATA_DO_PLANO" < /tmp/devolutiva-cdp.json
```

O validador confere cobertura da fila, escopo e evidência antes de devolver as
candidatas para revisão. A aceitação de uma lição segue o diff revisável e a
integração ao Git. A vista wiki usa notas já curadas, agrupadas por etiqueta, com
links por ID para suas âncoras e predecessoras. Para detalhes e limites do
desenho, consulte a [pesquisa de arquitetura](MEMORIA_PESQUISA.md).

Em desenvolvimento, `retomar-sonho` confere devolutivas anteriores em JSONL na ordem das
páginas, com data e revisão obrigatórias. Repita o limite e a origem `--desde` do plano, se
usados. O resultado traz o plano seguinte ou `cobertura_completa`, com `desde_sugerido`
somente depois da última página. As investigações em aberto permanecem no resumo.

```sh
jq -c . /tmp/pagina-1.json /tmp/pagina-2.json | uv run python -m cdp memoria retomar-sonho \
  --revisao "$REVISAO_DO_PLANO" --data "$DATA_DO_PLANO"
```

Para revisar com provas obrigatórias, use `--exigir-provas` ao planejar, ler, conferir e retomar.
O parâmetro muda o lacre. `manter` exige uma prova literal em `provas`, no mesmo formato de
`evidencias` das notas, e que a nota esteja sem falha conhecida. `investigar` admite prova
literal ou um `diagnostico` verificável (`sem_fonte_disponivel` ou `problema_catalogo`). Uma
`propor_candidata` usa as evidências da própria candidata. O código valida a origem do trecho.
O curador avalia se o trecho sustenta a disposição.

### Levar investigações ao próximo corte

`desde_sugerido` indica até onde a fila foi examinada. Uma disposição `investigar` continua
aberta. Pode incluir `investigacao` com uma `pergunta`, até três `hipoteses` e um
`proximo_teste` que ajude a distinguir as hipóteses. Em cada hipótese, `apoios` e
`contrarios` apontam para provas do item pelo par `caminho` e `sha256`. Listas vazias
registram hipóteses ainda sem prova. O código confere os vínculos. A interpretação das
passagens e a escolha do teste ficam com o curador.

Com `--exigir-provas`, a saída de `retomar-sonho` ao cobrir todas as páginas traz
`continuidade` se houver investigações ou se o corte recebeu uma continuidade anterior.
Guarde o objeto e seu SHA-256 em registros separados. Na janela seguinte, forneça o objeto
na primeira linha da entrada e o lacre esperado em `--continuar`. Use como origem a revisão
coberta. A fila recupera o item em aberto mesmo quando a fonte fica fora do novo diff.

```sh
jq -c '.continuidade' /tmp/rodada-anterior.json | uv run python -m cdp memoria sonhar \
  --exigir-provas --revisao "$REVISAO_ATUAL" --data "$DATA_ATUAL" \
  --desde "$REVISAO_COBERTA" --continuar "$LACRE_ANTERIOR"
```

Repita os mesmos parâmetros em `fonte-sonho`, `conferir-sonho` e `retomar-sonho`. Envie as
devolutivas depois da primeira linha, conforme a entrada de cada comando. O código
reconstitui o item de origem no Git, exige que as revisões pertençam à mesma história e
reconfere as provas na revisão em que foram registradas. O novo plano marca cada trecho
histórico como localizado ou desatualizado na revisão atual. Para encerrar a investigação,
use `manter` com prova atual e explique a conclusão no motivo. A continuidade conserva essa
resolução. Se uma prova de encerramento deixar de conferir, o item volta à fila com o motivo
e a prova históricos. Uma saída de página isolada contém a continuidade daquela página.

`retomar-sonho` também devolve `lacres_devolutivas` dos bytes das respostas JSONL, excluindo
o separador de linha. Ao reconferir páginas arquivadas, passe um `--lacre-pagina` por
devolutiva na ordem original. Guarde os lacres junto aos recibos da revisão e separados dos
bytes que serão reconferidos. Preserve as rodadas anteriores para auditar mudanças nas
hipóteses. A consulta de rotina e a wiki continuam lendo apenas notas curadas.

### Curadoria no harness Codex

No projeto Codex, a tarefa nativa de dreaming faz a leitura e a síntese aos
sábados. O Codex compara os recortes, formula a lição, registra a contraprova
e propõe como testar a transferência. A devolutiva com revisão, hash do plano
e itens cobertos fica no resultado da tarefa. O gate, o catálogo e os
validadores delimitam o acesso e conferem os vínculos com o Git.

Uma tarefa nativa distinta revê as propostas aos domingos. Ela lê pelo
histórico do Codex o disparo concluído e as decisões posteriores sobre suas
candidatas. Confere cada prova, distingue hipóteses de fatos e guarda o
recibo de propostas revisadas em `.cdp/memoria-codex/propostas/`, fora do
clone executor. O recibo preserva o estado `candidata`. A aceitação no
catálogo segue o diff revisável e os critérios desta seção.

O ensaio de análise usa sessões Codex independentes. As duas recebem os
mesmos dados históricos, com corte e fontes fixados. Uma também recebe
procedimentos aprendidos e revisados em tarefas anteriores. As respostas
são avaliadas em outras sessões com rubrica fixada e braços ocultos.

#### Fazer o eval retroalimentar o dreaming

Uma falha corrigida é um episódio de aprendizagem. Preserve a resposta,
o critério e a evidência disponível no corte. Na sessão de dreaming, peça
ao Codex que confronte a omissão com a carta vigente e com a fonte. A
correção precisa dizer quando se aplica, como pode ser refutada e onde
parar. A rubrica mostra a omissão. A fonte sustenta a regra.

Uma segunda sessão Codex confere a alteração sem acesso aos casos novos.
Se ela aceitar uma substituição, teste a transferência em três braços
com os mesmos fatos, sem cartas, com as cartas originais e com as cartas
revisadas. Mantenha o número de cartas e um orçamento comparável. Use
casos com contraindicações para detectar aplicação excessiva da regra.
Lacre a rubrica antes da análise e esconda a origem das respostas na
correção. Registre os acertos ganhos e perdidos, além da nota agregada.

#### Consultar lições durante a revisão

O agente revisor começa com o rascunho e os fatos do caso. Um índice
curto oferece indícios de quando abrir cada ficha. Abra só as fichas
pertinentes, confira a condição de uso e procure a contraprova no caso
atual. Preserve o que o rascunho já demonstrou. No recibo, indique as
fichas abertas e as verificações que motivaram cada mudança relevante.

Para medir essa etapa, congele um único rascunho e entregue os mesmos
fatos a dois revisores independentes. Um faz a segunda leitura com o
dossiê. O outro pode consultar o índice. Corrija também o rascunho para
medir o efeito da segunda leitura e acompanhe separadamente os casos
em que uma lição anterior poderia induzir uma extrapolação.

Quando já existe uma resposta de referência, a memória pode produzir
propostas pontuais. Cada proposta aponta um trecho único da resposta e
uma prova no dossiê atual. Um revisor independente verifica a pertinência
da mudança, a preservação dos fatos válidos e a compatibilidade com as
outras mudanças aceitas. A aplicação se limita aos trechos aprovados.
Se nenhuma proposta for aceita, o texto de referência é preservado.
Para medir essa etapa, use também um braço de propostas pontuais que
receba o mesmo dossiê e a mesma referência sem fichas de memória.

Outra forma de usar as fichas é escolher o que conferir antes de editar.
Grave as perguntas de cobertura e classifique cada uma pela situação da
resposta. Distinga uma resposta já sustentada, uma omissão demonstrável
e a falta de prova no dossiê. Vincule cada correção a uma pergunta que
continua aberta. Uma pergunta sem prova atual pode explicitar a condição
que falta para agir. A memória orienta a pergunta e os dados atuais
sustentam a resposta.

## Avaliar recuperação

O [benchmark operacional](memoria/benchmark-operacional.json) e o [benchmark de auditoria](memoria/benchmark-auditoria.json)
fixam as perguntas e os trechos esperados da comparação por passagem. O teste
`tests/cdp/test_memoria_benchmark.py` confere seus hashes e a recuperação com a política atual.
A revisão atual usa o roteiro de status com a primeira rotina elegível para abertura do livro.
O corpus anterior à mudança permanece em `e4359c45`, com as fontes de `ac5f8481`.
O [qualificador](../../scripts/cdp_memoria_qualificar.py) permite indicar separadamente a revisão
do código e a das fontes do gabarito. Ele comprova a igualdade dos bytes das fontes e compara
busca direta, busca contextual sem notas e busca com notas, sob o mesmo limite de cinco passagens.
Esse corpus serviu ao diagnóstico da implementação. A validação prospectiva é medida separadamente.

O [benchmark externo](../../scripts/cdp_memoria_benchmark.py) aceita
`--preflight-conjunto` para validar o gabarito antes da busca. Cada
grupo precisa de uma janela direta de fonte permitida. Todos os grupos
de uma pergunta precisam caber juntos em até cinco janelas e 4.500
bytes, contando um byte entre passagens. O pré-teste fixa a revisão das
fontes e informa os hashes do código local. A saída tem totais e lacres.

```sh
uv run python scripts/cdp_memoria_benchmark.py --preflight-conjunto --revisao "$REVISAO" \
  docs/cdp/memoria/benchmark-operacional.json docs/cdp/memoria/benchmark-auditoria.json
```

### Corpora iniciais

```sh
uv run python -m cdp memoria avaliar
uv run python -m cdp memoria avaliar --reservada
uv run python -m cdp memoria avaliar --replica
```

O primeiro comando usa o corpus e o catálogo iniciais, em `d60cc15f`, para medir por caminho.
Os dois conjuntos posteriores foram congelados separadamente e usam por padrão a revisão
`42f19b27ff7842d36f475a05785e408701ec12f8`. Com `--revisao`, a avaliação exige que a revisão
indicada contenha as evidências do gabarito. Se uma âncora esperada perdeu a validade, o
comando interrompe a comparação. As perguntas vieram de um anotador que não recebeu os
resultados de recuperação. Cada pergunta estática tem um ou mais grupos de evidências. Uma
passagem satisfaz um grupo quando contém integralmente um trecho aceito. Um acerto completo
exige todos os grupos. A avaliação também mede cobertura parcial e abstenção em perguntas de
estado ou fora do acervo.

A comparação usa três braços com até cinco passagens cada. A busca direta BM25 é executada
no commit de 06/11 (`afee26ce`) e na revisão atual. O terceiro braço consulta a memória na
revisão atual. As duas buscas diretas recebem a mesma lista de caminhos, inclusive caminhos
citados nas notas, para separar o efeito das referências do acesso aos arquivos. O relatório
registra as revisões, o hash do corpus e as passagens recuperadas. São medidas descritivas
do corpus, com a pergunta como unidade. Elas avaliam localização de evidência e abstenção
da busca, sem medir a resposta de um agente em operação. O teste de estado separa
encaminhamento inferido do encaminhamento com `--estado-atual`. Neste último a intenção é
fornecida pelo teste, como numa chamada estruturada. Consultas estáticas também contam
sugestões de encaminhamento indevidas.

As figuras da entrega usam a revisão `42f19b27` e os dois conjuntos. A primeira leitura
mostrou que a fusão descartava referências úteis. O ajuste posterior passou a preservar
as três primeiras passagens diretas. As figuras mostram a medição após esse ajuste.
A revisão da fonte e o código aparecem separadamente no rodapé.

Quando uma fonte muda, preserve o corpus histórico. A execução normal exige
que os trechos do gabarito ainda confiram. Para medir uma revisão nova com uma
prova atualizada, forneça um manifesto JSON explicitamente revisado.

```sh
uv run python -m cdp memoria avaliar --reservada --revisao "$REVISAO_ALVO" \
  --revalidacao "$MANIFESTO_JSON"
```

O manifesto declara `versao` 1, `revisao_alvo`, `sha256_corpus` e `casos`.
Cada caso informa `id`, `justificativa` e `grupos` de evidências com caminho,
trecho literal e hash. A conferência exige que a prova original do caso tenha
deixado de conferir no alvo. A medição preserva a prova original no braço
histórico e usa a prova nova nas buscas do alvo. O relatório separa os pares
com provas intactas dos casos revalidados e identifica o manifesto usado.

A partir da raiz de um checkout na revisão histórica `42f19b27`, gere os relatórios e as duas
figuras. O renderizador requer Matplotlib. [Código das figuras](../../scripts/cdp_memoria_figuras.py).

```sh
mkdir -p outputs/cdp-memoria
uv run python -m cdp memoria avaliar --reservada --revisao 42f19b27ff7842d36f475a05785e408701ec12f8 > outputs/cdp-memoria/reservada.json
uv run python -m cdp memoria avaliar --replica --revisao 42f19b27ff7842d36f475a05785e408701ec12f8 > outputs/cdp-memoria/replica.json
python3 scripts/cdp_memoria_figuras.py outputs/cdp-memoria/replica.json --primeira outputs/cdp-memoria/reservada.json
```

A avaliação de dreaming executa a comparação em um repositório Git temporário.
O ensaio separa busca direta, memória ativa antes da revisão e memória após a
reaplicação de decisões editoriais predefinidas. O plano e a devolutiva são
conferidos antes dessa reaplicação.

```sh
mkdir -p outputs/cdp-memoria
uv run python -m cdp memoria avaliar --sonho > outputs/cdp-memoria/ensaio-sonho.json
python3 scripts/cdp_memoria_figuras_sonho.py outputs/cdp-memoria/ensaio-sonho.json
```

O ensaio usa as mesmas fontes canônicas e o mesmo orçamento nos três braços.
Entre as cinco primeiras passagens, a evidência completa apareceu em 6 de 9
perguntas com busca direta, em 6 de 9 com a memória antes da revisão e em 8 de 9
depois das decisões editoriais. As três primeiras passagens ficaram em 6 de 9
nos três braços. A fila identificou os quatro casos predefinidos e a validação
recebeu uma candidata sem ativá-la. Os números medem o efeito da revisão
predefinida nesse cenário. O desempenho das decisões feitas pelo agente no
agendador exige avaliação própria.
