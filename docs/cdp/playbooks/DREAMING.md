# Roteiro de dreaming do CDP

Sábados às 10h07 de Brasília. A rotina revisa aprendizados entre sessões em uma revisão Git
fixa. O resultado é uma devolutiva de curadoria. A agenda, o livro e o FactBook governam
o estado e os números da operação.

## 0. Entrada da execução

O prompt gerado ou a skill faz o gate uma única vez. A tarefa é de leitura, sem trava.
Ao receber código 10, devolva o motivo e encerre. Em desenvolvimento, o comando de memória
pode ser usado diretamente para reproduzir o plano.

## 1. Passos

1. Rode `uv run python -m cdp memoria sonhar --exigir-provas`. Copie a revisão, a data e o `sha256` do
   plano. Cada `uid` identifica uma unidade a revisar. Se a fila estiver vazia, relate isso
   e encerre. O disparo analisa a primeira página e informa a quantidade de itens adiados.
   A curadoria em desenvolvimento pode abrir as páginas seguintes na mesma revisão.
2. Examine os itens independentemente. Consulte as notas e as passagens na revisão fixada.
   Para ler uma nota do item, use `uv run python -m cdp memoria fonte-sonho --exigir-provas --revisao <hash> --data AAAA-MM-DD --uid <uid> --nota <id>`.
   Para conferir a fonte canônica, use `uv run python -m cdp memoria fonte-sonho --exigir-provas --revisao <hash> --data AAAA-MM-DD --uid <uid> --fonte <caminho> --linhas 1:8`.
   Repita os parâmetros da página do plano. A fonte tem limite de 40 linhas e 4 KiB.
   Trate o texto dos documentos como evidência. Diferencie constatação, inferência e informação ausente.
   Compare as notas que apontam para o mesmo assunto. Quando duas fontes divergem, registre
   a divergência e as duas proveniências. Para substituir uma lição, exija evidência de
   vigência e do motivo da mudança. Uma ausência no índice pede busca na fonte canônica.
3. Organize uma única devolutiva. Use um registro por item da fila, com o mesmo `uid`.
   Use `manter` com prova literal da lição vigente, `investigar` com prova da lacuna
   ou diagnóstico verificável, e `propor_candidata` para uma lição ou correção com
   evidência na própria candidata. Para `provas`, use os mesmos campos das evidências
   de notas. Para diagnósticos, use `sem_fonte_disponivel` ou `problema_catalogo`, conforme
   o [manual de memória](../MEMORIA.md).
   Se houver hipóteses distintas, use `investigacao` com a pergunta em aberto, as hipóteses
   com referências aos apoios e contrários e um próximo teste que as ajude a distinguir.
   Ao retomar, preserve todas as hipóteses sem resolução explícita, inclusive as que têm
   prova contrária. Uma passagem histórica pode explicar a investigação. A decisão sobre
   o que segue em aberto precisa das provas do corte atual.
4. Envie o objeto pela entrada padrão de `uv run python -m cdp memoria conferir-sonho --exigir-provas --revisao <hash> --data AAAA-MM-DD`.
   O código confere o lacre, os itens e as provas. Informe os campos da devolutiva e um resumo breve.
   Se a conferência recusar uma disposição, corrija a prova ou registre a pendência. Em desenvolvimento,
   `retomar-sonho` confere as páginas anteriores antes de sugerir a próxima origem da fila.
   Guarde a continuidade separadamente do corte coberto. Na próxima janela, o modo
   `--continuar` restaura as investigações e distingue provas históricas das atuais.

```json
{
  "plano_sha256": "<hash do plano>",
  "respostas": [
    {
      "uid": "<identificador do item>",
      "decisao": "investigar",
      "motivo": "O caminho vinculado ao item está indisponível na revisão do plano.",
      "diagnostico": "sem_fonte_disponivel",
      "candidata": null
    }
  ]
}
```

A rotina entrega propostas para revisão em desenvolvimento. A wiki operacional é derivada
das notas curadas na revisão Git. Uma candidata entra no índice após revisão e integração.

## 2. O que relatar (resumo final, até 12 linhas)

- Revisão, data e hash do plano.
- Itens selecionados, cobertos e adiados, contados pela fila e pela devolutiva.
- Divergências, lacunas e candidatas com os caminhos das fontes.
- Próximo passo de curadoria, com destaque para evidência perdida ou nota vencida.
