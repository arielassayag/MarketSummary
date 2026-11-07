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
A busca compara termos com os títulos, as etiquetas, os resumos e trechos dos documentos de
referência do escopo. Consultas sem correspondência suficiente podem retornar listas vazias. Em perguntas diretas
sobre o estado atual reconhecidas pela busca, `orientacao_atual` aponta onde verificar e a
lista de notas fica vazia.

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
revisão, vencimento e substituição às notas da revisão Git selecionada. Para um ensaio histórico,
use também um checkout isolado da revisão que existia no corte. A opção `--data` em um checkout
atual conserva os arquivos atuais e, sozinha, é insuficiente para estabelecer disponibilidade
histórica ou origem *point-in-time*. `avaliar` usa a data fixa do seu próprio corpus.

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
3. Para substituir uma lição, use um novo ID, data de registro posterior e escopos que cubram os
   da nota anterior. Inclua o ID anterior em `substitui`. Quando a sucessora curada chega à data
   de revisão, a versão anterior sai da consulta. Uma quebra posterior de evidência ou expiração
   da sucessora mantém o bloqueio da anterior. Retirar a sucessora também conserva esse efeito
   enquanto o vínculo de substituição permanecer válido.
4. Uma nota curada que perdeu utilidade pode passar a `retirada`, mantendo datas, fonte e
   histórico no Git e com `destaque: false`. Para renovar a validade, confira a fonte atual e
   proponha novas datas. Preserve a razão da mudança no diff e no registro da integração.
5. Audite antes de integrar. No checkout da revisão aceita, repita a consulta de exemplo e a
   avaliação para verificar o que ficou elegível.

Os cinco comandos leem arquivos e imprimem resultados. A proposta e a fila não gravam arquivos,
promovem notas, agendam revisões ou publicam. A consolidação pode aproveitar ajuda de um agente
em sessão de desenvolvimento, com suas mudanças apresentadas como diff para revisão.

## Avaliar recuperação

```sh
uv run python -m cdp memoria avaliar
```

O corpus de [avaliação](memoria/avaliacao.json) fixa a data e os casos. Para cada consulta, a
comparação dá o mesmo orçamento de até três caminhos às duas abordagens. A primeira usa busca
nos documentos e no código canônicos do escopo. A segunda prioriza evidências das notas recuperadas e
preenche as vagas com a busca canônica, sem repetir caminhos. As medidas incluem recuperação de
pelo menos uma nota esperada, abstenção de nota em perguntas fora do acervo, abstenção de nota em
perguntas respondíveis pela busca direta e recuperação de pelo menos uma fonte esperada em cada
abordagem. Um caso pode listar fontes alternativas.

A avaliação funciona offline, sem chamada a modelo. O resultado é reproduzível para a mesma
revisão e o mesmo corpus. O código de saída indica problema no catálogo ou na leitura. As taxas
precisam ser lidas no relatório. Esta comparação mede recuperação de caminhos no corpus inicial.
Aderência de agentes, tempo de resolução e qualidade de respostas exigem um ensaio separado em
sessões novas, com casos reservados e a mesma base para as duas abordagens.
