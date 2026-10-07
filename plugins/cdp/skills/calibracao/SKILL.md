---
name: calibracao
description: "Calibração mensal do núcleo quantitativo do CDP — Cabra da Peste (dia 1, 9h15 de Brasília): backtest walk-forward com todo o histórico em reports/backtest/<data>/mensal (ou o que o script de rotina já rodou), comparação lado a lado com a execução anterior (números copiados de metrics.json) e propostas de mudança de mandato só para revisão humana; nunca altera a configuração. Entrada e saída da execução no Claude Code; o procedimento é o roteiro neutro docs/cdp/playbooks/CALIBRACAO.md. Use na tarefa agendada cdp-calibracao ou quando pedirem a recalibração do CDP."
argument-hint: "[tarefa agendada: cdp-calibracao]"
allowed-tools:
  - Read
  - Write
  - Grep
  - Glob
  - Bash(uv sync *)
  - Bash(uv run python -m cdp *)
  - Bash(git status *)
  - Bash(git log *)
---

# CDP — calibração mensal (Claude Code)

Você é a **mente** do CDP — Cabra da Peste. Rotina sem supervisão: não faça perguntas; se algo
bloquear, pare e explique no resumo final. O procedimento é o roteiro
`docs/cdp/playbooks/CALIBRACAO.md` — o mesmo em qualquer harness (Claude Code, Codex, Gemini); esta
skill só faz a entrada e a saída da execução no Claude Code (app desktop, CLI ou sessão interativa).
Metodologia: `docs/cdp/METODOLOGIA.md`; manual do agente: `AGENTS.md`.

Argumento (`$ARGUMENTS`): o id da tarefa agendada que disparou você (`cdp-calibracao`); sem
argumento, `cdp-calibracao`. Fora do horário agendado (pedido do operador), substitua `--aguardar-horario` por `--manual` no
gate.

## Regras desta skill

- Mente `claude-code`: `--mind claude-code` na CLI, `"mind": "claude-code"` nos JSON e
  `--mente claude-code` na publicação.
- Rode o gate **uma vez só** por execução (passo 2); nunca de novo dentro do roteiro.
- **Modo executor:** se o prompt disser que a agenda, a trava, a sincronização e a publicação são do
  executor (script de rotina ou workflow), faça só o passo 4 e o resumo — nenhum gate,
  `cdp sincronizar`, `cdp publicar`, `cdp trava` nem `git` que grave.
- Nenhum comando `git` que grave (commit, push, pull, merge): a sincronização e a publicação são só
  por `cdp sincronizar` e `cdp publicar`.
- **Só os comandos das `allowed-tools`**; para ler saídas, use `Read`/`Grep` nos arquivos gravados
  pelo código. Nunca `python -c`, `jq`, `sleep` nem laços de espera: um pedido de permissão deixa a
  tarefa parada e o app pula as rotinas seguintes. Se um passo exigir outra coisa, pare e relate.
- Nunca publique artifacts numa rotina. O espelho privado do painel no claude.ai é só a pedido do
  operador, numa sessão interativa (`docs/cdp/LOCAL.md`, seção 10).
- Nunca desligue o kill switch; nunca use `--force`.
- O backtest leva mais que o limite de um comando: rode-o em segundo plano (Bash com
  `run_in_background`) e **encerre o turno sem esperar** — a notificação de término reabre a sessão;
  então siga do passo 3 do roteiro. Sem interface (`claude -p`), uma tarefa em segundo plano morre
  quando a resposta termina: por isso o script de rotina (`scripts/cdp_rotina.sh`, chamado por
  `scripts/cdp_run_task.sh`) registra a execução e só então roda o backtest, antes da skill. O
  gate do passo 2 devolve essa mesma `execucao` (variável `CDP_EXECUCAO`), e `cdp publicar` leva
  a pasta `mensal/` junto com o resumo.

## Passos

1. `uv sync --frozen --extra dev --extra ai`
2. `uv run python -m cdp rotinas gate --tarefa <tarefa> --aguardar-horario` — `executar: false` ⇒ responda "Sem
   execução: <motivo>" e encerre. Guarde `execucao`.
3. `uv run python -m cdp sincronizar --executar` — `acao: "parar"` ⇒ encerre relatando o `motivo`.
4. Siga `docs/cdp/playbooks/CALIBRACAO.md` do passo 1 ao passo 4, com `--mind claude-code`.
5. Publique uma vez (passo 5 do roteiro):
   `uv run python -m cdp publicar --tarefa <tarefa> --mensagem "CDP: calibração mensal AAAA-MM-DD" --execucao <execucao> --mente claude-code`
   (mensagem conforme o roteiro). Leia `push` e `motivo`; sem push, relate — nunca outro caminho.
6. Resumo final: o do roteiro, em pt-BR institucional (`docs/cdp/ESTILO.md`), com números copiados
   dos relatórios e das saídas da CLI (nunca calculados).
