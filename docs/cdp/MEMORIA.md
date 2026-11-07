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
A busca ordena passagens de fontes canônicas com BM25. Títulos, etiquetas, resumos e trechos
validados ajudam a localizar lições. A lista `passagens` preserva os três primeiros resultados diretos
e intercala referências de notas distintas. Uma passagem ocupa até 14 linhas e 1.800 bytes.
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

## Avaliar recuperação

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

A partir da raiz do repositório, gere o relatório e as duas figuras. O renderizador requer
Matplotlib. [Código das figuras](../../scripts/cdp_memoria_figuras.py).

```sh
mkdir -p outputs/cdp-memoria
uv run python -m cdp memoria avaliar --replica > outputs/cdp-memoria/replica.json
python3 scripts/cdp_memoria_figuras.py outputs/cdp-memoria/replica.json
```
