# Avaliação pareada de memória no Codex

Este ensaio compara três textos por caso. A é a referência relida. B e C
recebem a mesma referência, o mesmo dossiê e um orçamento de cinco perguntas
de cobertura. C também pode consultar até três fichas curadas de episódios
encerrados. Cada intervenção aponta a uma pergunta ainda aberta e a um trecho
literal do caso. Quando falta prova, o agente explicita a lacuna ou a condição
necessária para decidir.

## Tarefas no app

1. Lacre casos e rubricas separadamente. Em uma tarefa de dreaming do Codex,
   produza fichas a partir de experiências anteriores. Em outra tarefa, confira
   cada ficha e decida sua elegibilidade antes de abrir os casos aos revisores.
2. Faça uma tarefa de análise entregar a referência. Abra duas tarefas de
   revisão, uma por condição. Peça que registrem as cinco perguntas de cada
   caso antes de propor até três intervenções localizadas. Guarde os planos
   e as propostas separadamente, com SHA-256 e recibos das tarefas.
3. Confira o vínculo com o plano. Entregue o pacote mascarado a uma tarefa
   independente do Codex para julgar as intervenções contra o dossiê e a
   referência. Aplique as intervenções aceitas em uma cópia.
4. Lacre os textos finais, abra a rubrica e prepare o pacote de correção cega.
   Use duas tarefas independentes do Codex. Compare C com B dentro de cada
   correção e registre os ganhos, as perdas e as violações fatais.

A síntese das fichas, a seleção de perguntas, a revisão e os julgamentos são
trabalho do agente no app. Os utilitários conferem estrutura, provas, lacres e
identidade dos insumos, preparam pacotes e agregam as decisões registradas.
Mantenha a chave de cada mascaramento com a custódia e fora das tarefas cegas.
Use apenas uma pasta de ensaio. As intervenções deste fluxo ficam fora do livro
e a promoção de fichas segue o [manual de memória](../../docs/cdp/MEMORIA.md).

## Conferência e reprodução

Com o pacote de evidências de uma rodada extraído, rode a partir da raiz do
repositório. `EVIDENCIAS` aponta para a pasta que contém `lacres.json`, os
arquivos de entrada por trilha e o subdiretório `consolidado`. O resultado deve
ser um arquivo novo.

```sh
for trilha in risco valuation; do
  for condicao in B C; do
    python3 scripts/cdp_memoria_harness/conferir_cobertura.py "$EVIDENCIAS" "$trilha" "$condicao"
  done
done
python3 scripts/cdp_memoria_harness/agregar.py "$EVIDENCIAS/consolidado" resultado-novo.json
```

Em uma rodada nova, `montar_indice.py` prepara a vista da biblioteca,
`remendos.py preparar` produz as opções cegas e `remendos.py aplicar` recebe o
parecer da tarefa independente. `montar_cega.py` monta os pacotes finais depois
do lacre. A opção `--help` descreve os parâmetros de cada utilitário. O sorteio
dos rótulos é novo a cada preparação. Para reproduzir um julgamento já
registrado, use a chave e os pacotes congelados da própria rodada.
