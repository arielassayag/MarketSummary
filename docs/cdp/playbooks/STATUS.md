# Roteiro de estado do CDP — saúde da operação (segundas, 8h30 de Brasília; ou a qualquer hora)

Só leitura, em qualquer harness: não grave arquivos, não faça commit, pull nem push e não mexa
no kill switch. Números copiados das saídas da CLI. Numa rotina agendada, a entrada vem da skill
`cdp-status`; no PC local, a skill `cdp:status` do plugin faz o mesmo.

## Passos

```sh
uv run python -m cdp estado --formato md
uv run python -m cdp status
uv run python -m cdp verify
uv run python -m cdp nota agenda
uv run python -m cdp rotinas proximas --n 12
```

`estado` já reúne fase, executor designado × este ambiente, trava das rotinas, integridade,
últimos registros, últimas execuções (com a procedência de cada commit), pendências, incidentes
e o próximo passo. Com acesso à rede, `uv run python -m cdp estado --rede --formato md` consulta
também o remoto, a trava e o portal publicado.

## O que relatar (resumo final, até 12 linhas)

- **Integridade** e **kill switch**.
- **Fase**: em pré-início, a data da carteira inaugural; com a abertura do livro pendente,
  destaque que a próxima rotina diária a faz.
- **Executor**: quem grava o livro e desde quando; se este ambiente não é o executor, diga
  "somente leitura".
- **Incidentes** por severidade (alta primeiro), com a ação indicada.
- **Pendências**: fechamentos, relatórios, tese da semana, relatório semanal, retrato da
  cobertura, a fila de notas (`pendentes` de `nota agenda`) e os rascunhos entregues ainda não
  adotados ou obsoletos (`rascunhos_pendentes`, `rascunhos_obsoletos`).
- **Próximas rotinas** e se vão agir.
- **Portal**: a URL pública e, com `--rede`, se a versão publicada corresponde a `origin/main`.
