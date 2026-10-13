---
name: cdp-retomar
description: "Retoma a operação ou o desenvolvimento do CDP — Cabra da Peste em qualquer harness: lê o estado (fase do fundo, executor, últimas execuções, pendências, incidentes, próximas rotinas) e indica o roteiro certo. Use ao abrir uma sessão neste repositório sem saber o que fazer, ou quando pedirem para continuar a operação ou o desenvolvimento do CDP."
compatibility: "Requer git, uv e rede para fontes públicas; qualquer harness com shell (Claude Code, Codex, Gemini CLI, Antigravity, Copilot, Cursor)."
allowed-tools:
  - "Read"
  - "Grep"
  - "Glob"
  - "Bash(uv sync *)"
  - "Bash(git status *)"
  - "Bash(git log *)"
  - "Bash(uv run cdp estado *)"
  - "Bash(uv run cdp estado)"
  - "Bash(uv run cdp executor janela *)"
  - "Bash(uv run cdp executor janela)"
  - "Bash(uv run cdp rotinas verificar *)"
  - "Bash(uv run cdp rotinas verificar)"
  - "Bash(uv run cdp skills sincronizar --claude --verificar *)"
  - "Bash(uv run cdp skills sincronizar --claude --verificar)"
  - "Bash(uv run python -m cdp estado *)"
  - "Bash(uv run python -m cdp estado)"
  - "Bash(uv run python -m cdp executor janela *)"
  - "Bash(uv run python -m cdp executor janela)"
  - "Bash(uv run python -m cdp rotinas verificar *)"
  - "Bash(uv run python -m cdp rotinas verificar)"
  - "Bash(uv run python -m cdp skills sincronizar --claude --verificar *)"
  - "Bash(uv run python -m cdp skills sincronizar --claude --verificar)"
metadata:
  gerado-por: "uv run python -m cdp skills sincronizar"
  playbook: "docs/cdp/playbooks/RETOMAR.md"
  tarefas: ""
---
# CDP — pegar o bonde andando

1. `uv sync --extra dev --extra ai`
2. `uv run python -m cdp estado --formato md` (para máquinas: sem `--formato`). Leia fase,
   executor (`sou_o_executor`), incidentes, pendências e `playbook_sugerido`.
3. Identifique o seu papel (`AGENTS.md`, seção 1): rotina agendada ⇒ a skill da tarefa;
   sessão de operador ⇒ leitura por padrão; sessão de desenvolvimento ⇒ nunca grave `book/`,
   `data/`, `reports/`, `artifacts/`; leia `docs/cdp/EM_ANDAMENTO.md` e `docs/cdp/DECISOES.md`.
4. Siga `docs/cdp/playbooks/RETOMAR.md`.
5. Ao encerrar uma sessão de desenvolvimento, atualize `docs/cdp/EM_ANDAMENTO.md`.

Arquivo gerado — não edite à mão (`uv run python -m cdp skills sincronizar`).
