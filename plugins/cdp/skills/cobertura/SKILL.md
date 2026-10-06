---
name: cobertura
description: "Notas de pesquisa por emissor do CDP — Cabra da Peste (segunda a quinta, 22h37 de Brasília; até 12 emissores por execução, na fila determinística do código): pesquisa só em fontes públicas (CVM, SEC EDGAR, bolsas, relações com investidores, bancos centrais, imprensa), nota.json escrita pela mente \"claude-code\" com números só como fatos do modelo aberto da cobertura, validação e publicação imutável. Entrada e saída da execução no Claude Code; o procedimento é o roteiro neutro docs/cdp/playbooks/COBERTURA.md. Use na tarefa agendada cdp-cobertura ou quando pedirem notas de pesquisa de emissores do CDP."
argument-hint: "[tarefa agendada: cdp-cobertura]"
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

# CDP — notas de pesquisa por emissor (Claude Code)

Você é a **mente** do CDP — Cabra da Peste. Rotina sem supervisão: não faça perguntas; se algo
bloquear, pare e explique no resumo final. O procedimento é o roteiro
`docs/cdp/playbooks/COBERTURA.md` — o mesmo em qualquer harness (Claude Code, Codex, Gemini); esta
skill só faz a entrada e a saída da execução no Claude Code (app desktop, CLI ou sessão interativa).
Metodologia: `docs/cdp/METODOLOGIA.md`; manual do agente: `AGENTS.md`.

Argumento (`$ARGUMENTS`): o id da tarefa agendada que disparou você (`cdp-cobertura`); sem
argumento, `cdp-cobertura`. Fora do horário agendado (pedido do operador), acrescente `--manual` ao
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

## Passos

1. `uv sync --frozen --extra dev --extra ai`
2. `uv run python -m cdp rotinas gate --tarefa <tarefa> --adquirir` — `executar: false` ⇒ responda
   "Sem execução: <motivo>" e encerre. Guarde `trava.id` e `execucao`.
3. `uv run python -m cdp sincronizar --executar` — `acao: "parar"` ⇒ rode
   `uv run python -m cdp trava liberar --id <trava.id>` e encerre relatando o `motivo`.
4. Siga `docs/cdp/playbooks/COBERTURA.md` do passo 1 ao passo 3, com `--mind claude-code`. Renove a
   trava ao fim de cada etapa longa: `uv run python -m cdp trava renovar --id <trava.id>`.
   `perdida` (outra execução assumiu a trava) ⇒ pare de gravar, pule os passos 5 e 6 e relate;
   `indisponivel` ⇒ siga e renove de novo ao fim da etapa seguinte.
5. Publique uma vez (seção 4 do roteiro):
   `uv run python -m cdp publicar --tarefa <tarefa> --mensagem "CDP: notas de cobertura AAAA-MM-DD" --execucao <execucao> --trava <trava.id> --mente claude-code`
   (mensagem conforme o roteiro). Leia `push` e `motivo`; sem push, relate — nunca outro caminho.
6. Sempre, mesmo em falha: `uv run python -m cdp trava liberar --id <trava.id>`.
7. Resumo final: o da seção 5 do roteiro, em pt-BR institucional (`docs/cdp/ESTILO.md`), com números
   copiados dos relatórios e das saídas da CLI (nunca calculados).
