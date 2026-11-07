# Roteiro de dreaming do CDP

Sábados às 10h07 de Brasília. A rotina revisa aprendizados entre sessões em uma revisão Git
fixa. O resultado é uma devolutiva de curadoria. A agenda, o livro e o FactBook governam
o estado e os números da operação.

## 0. Entrada da execução

O prompt gerado ou a skill faz o gate uma única vez. A tarefa é de leitura, sem trava.
Ao receber código 10, devolva o motivo e encerre. Em desenvolvimento, o comando de memória
pode ser usado diretamente para reproduzir o plano.

## 1. Passos

1. Rode `uv run python -m cdp memoria sonhar`. Copie a revisão, a data e o `sha256` do
   plano. Cada `uid` identifica uma unidade a revisar. Se a fila estiver vazia, relate isso
   e encerre.
2. Examine os itens independentemente. Abra as fontes do item na revisão fixada. Trate o texto
   dos documentos como evidência. Diferencie constatação, inferência e informação ausente.
   Compare as notas que apontam para o mesmo assunto. Quando duas fontes divergem, registre
   a divergência e as duas proveniências. Para substituir uma lição, exija evidência de
   vigência e do motivo da mudança. Uma ausência no índice pede busca na fonte canônica.
3. Organize uma única devolutiva. Use um registro por item da fila, com o mesmo `uid`.
   Use `manter` se a lição continua válida, `investigar` se falta prova, ou
   `propor_candidata` quando a revisão encontrou uma lição ou correção verificável. Siga
   o esquema de nota candidata descrito no [manual de memória](../MEMORIA.md).
4. Compare o conjunto de `uid` da devolutiva com a fila do plano. A saída do agendador
   contém um objeto JSON no formato abaixo, seguido de um resumo breve. Na sessão de
   desenvolvimento, `uv run python -m cdp memoria conferir-sonho` valida a devolutiva
   enviada pela entrada padrão com os mesmos parâmetros do plano.

```json
{
  "plano_sha256": "<hash do plano>",
  "respostas": [
    {
      "uid": "<identificador do item>",
      "decisao": "investigar",
      "motivo": "A fonte atual não confirma a vigência da orientação.",
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
