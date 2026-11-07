---
name: dreaming
description: "Revisão semanal da memória do CDP — Cabra da Peste aos sábados, 10:07 de Brasília. Examina candidatas e evidências com o roteiro neutro docs/cdp/playbooks/DREAMING.md e devolve sugestões de curadoria para revisão. Use na tarefa agendada cdp-dreaming."
argument-hint: "[tarefa agendada: cdp-dreaming]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(uv sync *)
  - Bash(uv run python -m cdp memoria fonte-sonho *)
  - Bash(uv run python -m cdp memoria fonte-sonho)
  - Bash(uv run python -m cdp memoria sonhar)
  - Bash(uv run python -m cdp rotinas gate --tarefa cdp-dreaming *)
  - Bash(uv run python -m cdp rotinas gate --tarefa cdp-dreaming)
---

# CDP — revisão semanal da memória

A tarefa `cdp-dreaming` reúne sugestões de curadoria em leitura. Siga o roteiro
`docs/cdp/playbooks/DREAMING.md` e o manual `AGENTS.md`. A metodologia do fundo está em
`docs/cdp/METODOLOGIA.md`.

Rode o gate **uma vez só**. Em sessão de operador fora do horário, o gate usa
`--manual`. Quando o executor fizer o gate, siga direto para o roteiro.

1. `uv sync --frozen --extra dev --extra ai`
2. `uv run python -m cdp rotinas gate --tarefa <tarefa> --aguardar-horario`
   Com `executar: false`, responda "Sem execução: <motivo>" e encerre.
3. Siga `docs/cdp/playbooks/DREAMING.md`.
4. Resumo final conforme o roteiro, com as propostas e as fontes consultadas.
