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
uv run python -m cdp memoria buscar --escopo diario --consulta 'moeda do benchmark índice local' --limite 3
```

Os escopos são `desenvolvimento`, `operador`, `status`, `semanal`, `diario`, `risco`, `cobertura`
e `calibracao`. `contexto` mostra até três notas curadas em destaque no escopo, com orçamento de
6 KiB de saída em Markdown e JSON. `buscar` retorna separadamente notas elegíveis e
fontes primárias do escopo. O limite de resultados por lista vai de um a dez e o padrão é cinco.
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

Quando a busca reconhece um pedido de estado, `orientacao_atual` indica a fonte a consultar.
O encaminhamento inferido deixa a busca direta disponível e omite as notas. Use
`--estado-atual` para obter apenas o encaminhamento quando a intenção já estiver estabelecida.
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
uv run python -m cdp memoria sonhar
uv run python -m cdp memoria wiki --escopo desenvolvimento
```

A rotina usa `fonte-sonho` para ler apenas as notas e as passagens autorizadas pelo
item na revisão fixada. A leitura por intervalo limita o retorno a 40 linhas e 4 KiB.
Cada item exige uma disposição e sua justificativa. A devolutiva traz o SHA-256 do
plano, cobre todos os IDs selecionados e pode anexar novas notas candidatas
no esquema deste manual. A curadoria compara fontes quando elas divergem.
Em desenvolvimento, valide o JSON da devolutiva pela entrada padrão, com a
mesma revisão, data, origem e página do plano.

```sh
uv run python -m cdp memoria conferir-sonho < /tmp/devolutiva-cdp.json
```

O validador confere cobertura da fila, escopo e evidência antes de devolver as
candidatas para revisão. A aceitação de uma lição segue o diff revisável e a
integração ao Git. A vista wiki usa notas já curadas, agrupadas por etiqueta, com
links por ID para suas âncoras e predecessoras. Para detalhes e limites do
desenho, consulte a [pesquisa de arquitetura](MEMORIA_PESQUISA.md).

## Avaliar recuperação

O [benchmark operacional](memoria/benchmark-operacional.json) e o [benchmark de auditoria](memoria/benchmark-auditoria.json)
fixam as perguntas e os trechos esperados da comparação por passagem. O teste
`tests/cdp/test_memoria_benchmark.py` confere seus hashes e a recuperação com a política atual.
O [qualificador](../../scripts/cdp_memoria_qualificar.py) permite indicar separadamente a revisão
do código e a das fontes do gabarito. Ele comprova a igualdade dos bytes das fontes e compara
busca direta, busca contextual sem notas e busca com notas, sob o mesmo limite de cinco passagens.
Esse corpus serviu ao diagnóstico da implementação. A validação prospectiva é medida separadamente.

### Corpora iniciais

```sh
uv run python -m cdp memoria avaliar
uv run python -m cdp memoria avaliar --reservada
uv run python -m cdp memoria avaliar --replica
```

O primeiro comando usa o corpus e o catálogo iniciais, em `d60cc15f`, para medir por caminho. Os dois conjuntos posteriores
foram congelados separadamente. As perguntas vieram de um anotador que não recebeu os
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
