---
name: diario
description: "Fechamento diário do CDP — Cabra da Peste depois do pregão: marcação a mercado, execução no leilão de fechamento no dia de montagem, risco, atribuição e registro encadeado por hash (código), comentário do dia escrito pela mente \"claude-code\" e relatório diário; recupera pregões perdidos e a tese pendente da semana corrente; na noite do dia de montagem, um relatório semanal de resultado para cada dia de montagem pendente (do mais antigo ao mais recente, inclusive sem decisão gravada); o retrato da cobertura quando pendente (parcial após resultados divulgados, completo após evento macro de juros ou inflação) e, no último dia de montagem do mês, a revisão mensal dos modelos (revisao.json escrito pela mente \"claude-code\"). Entrada e saída da execução no Claude Code; o procedimento é o roteiro neutro docs/cdp/playbooks/DIARIO.md. Use nas tarefas agendadas cdp-diario, cdp-diario-reforco e cdp-diario-sabado ou quando pedirem o fechamento do dia do CDP."
argument-hint: "[tarefa agendada: cdp-diario, cdp-diario-reforco, cdp-diario-sabado]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - WebSearch
  - WebFetch
  - Bash(uv sync *)
  - Bash(uv run python -m cdp *)
  - Bash(git status *)
  - Bash(git log *)
---

# CDP — fechamento diário (Claude Code)

Você é a **mente** do CDP — Cabra da Peste. Rotina sem supervisão: não faça perguntas; se algo
bloquear, pare e explique no resumo final. O procedimento é o roteiro `docs/cdp/playbooks/DIARIO.md`
— o mesmo em qualquer harness (Claude Code, Codex, Gemini); esta skill só faz a entrada e a saída da
execução no Claude Code (app desktop, CLI ou sessão interativa). Metodologia:
`docs/cdp/METODOLOGIA.md`; manual do agente: `AGENTS.md`.

Argumento (`$ARGUMENTS`): o id da tarefa agendada que disparou você (`cdp-diario`,
`cdp-diario-reforco` ou `cdp-diario-sabado`); sem argumento, `cdp-diario`. Fora do horário agendado
(pedido do operador), substitua `--aguardar-horario` por `--manual` no gate.

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

## Passos

1. `uv sync --frozen --extra dev --extra ai`
2. `uv run python -m cdp rotinas gate --tarefa <tarefa> --adquirir --aguardar-horario` — `executar: false` ⇒ responda
   "Sem execução: <motivo>" e encerre. Guarde `trava.id` e `execucao`.
3. `uv run python -m cdp sincronizar --executar` — `acao: "parar"` ⇒ rode
   `uv run python -m cdp trava liberar --id <trava.id>` e encerre relatando o `motivo`.
4. Siga `docs/cdp/playbooks/DIARIO.md` do passo 1 ao passo 7, com `--mind claude-code`. Renove a
   trava ao fim de cada etapa longa: `uv run python -m cdp trava renovar --id <trava.id>`.
   `perdida` (outra execução assumiu a trava) ⇒ pare de gravar, pule os passos 5 e 6 e relate;
   `indisponivel` ⇒ siga e renove de novo ao fim da etapa seguinte.
5. Publique uma vez (seção 8 do roteiro):
   `uv run python -m cdp publicar --tarefa <tarefa> --mensagem "CDP: fechamento AAAA-MM-DD" --execucao <execucao> --trava <trava.id> --mente claude-code`
   (mensagem conforme o roteiro). Leia `push` e `motivo`; sem push, relate — nunca outro caminho.
6. Sempre, mesmo em falha: `uv run python -m cdp trava liberar --id <trava.id>`.
7. Resumo final: o da seção 9 do roteiro, em pt-BR institucional (`docs/cdp/ESTILO.md`), com números
   copiados dos relatórios e das saídas da CLI (nunca calculados).
