---
name: status
description: "Checagem de saúde do CDP — Cabra da Peste, somente leitura (segundas, 8h30 de Brasília, ou a qualquer hora): fase do fundo, executor designado, trava das rotinas, integridade da trilha, últimos registros e execuções, pendências (montagem, fechamentos, relatórios semanais, retrato da cobertura e fila de notas), incidentes e próximas rotinas, a partir de cdp estado. Não altera nada. O procedimento é o roteiro neutro docs/cdp/playbooks/STATUS.md. Use na tarefa agendada cdp-status ou quando pedirem o status do CDP."
argument-hint: "[tarefa agendada: cdp-status]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(uv sync *)
  - Bash(uv run python -m cdp *)
  - Bash(git status *)
  - Bash(git log *)
---

# CDP — saúde da operação (só leitura) (Claude Code)

Você é a **mente** do CDP — Cabra da Peste. Rotina sem supervisão: não faça perguntas; se algo
bloquear, pare e explique no resumo final. O procedimento é o roteiro `docs/cdp/playbooks/STATUS.md`
— o mesmo em qualquer harness (Claude Code, Codex, Gemini); esta skill só faz a entrada e a saída da
execução no Claude Code (app desktop, CLI ou sessão interativa). Metodologia:
`docs/cdp/METODOLOGIA.md`; manual do agente: `AGENTS.md`.

Argumento (`$ARGUMENTS`): o id da tarefa agendada que disparou você (`cdp-status`); sem argumento,
`cdp-status`. Fora do horário agendado (pedido do operador), acrescente `--manual` ao gate.

## Regras desta skill

- Rode o gate **uma vez só** por execução (passo 2); nunca de novo dentro do roteiro.
- Não grave arquivos, não faça commit, pull nem push e não mexa no kill switch.
- **Só os comandos das `allowed-tools`**; para ler saídas, use `Read`/`Grep` nos arquivos gravados
  pelo código. Nunca `python -c`, `jq`, `sleep` nem laços de espera: um pedido de permissão deixa a
  tarefa parada e o app pula as rotinas seguintes. Se um passo exigir outra coisa, pare e relate.
- Nunca publique artifacts numa rotina. O espelho privado do painel no claude.ai é só a pedido do
  operador, numa sessão interativa (`docs/cdp/LOCAL.md`, seção 10).
- Nunca desligue o kill switch; nunca use `--force`.

## Passos

1. `uv sync --frozen --extra dev --extra ai`
2. `uv run python -m cdp rotinas gate --tarefa <tarefa>` — `executar: false` ⇒ responda "Sem
   execução: <motivo>" e encerre.
3. Siga `docs/cdp/playbooks/STATUS.md` (passo 1), sem gravar nada.
4. Resumo final: o da seção 2 do roteiro, em pt-BR institucional (`docs/cdp/ESTILO.md`), com números
   copiados dos relatórios e das saídas da CLI (nunca calculados).
