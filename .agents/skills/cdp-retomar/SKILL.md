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
  - "Bash(uv run cdp agenda *)"
  - "Bash(uv run cdp agenda)"
  - "Bash(uv run cdp estado *)"
  - "Bash(uv run cdp estado)"
  - "Bash(uv run cdp executor janela *)"
  - "Bash(uv run cdp executor janela)"
  - "Bash(uv run cdp memoria contexto --escopo desenvolvimento)"
  - "Bash(uv run cdp memoria contexto --escopo operador)"
  - "Bash(uv run cdp rotinas verificar *)"
  - "Bash(uv run cdp rotinas verificar)"
  - "Bash(uv run cdp skills sincronizar --claude --verificar *)"
  - "Bash(uv run cdp skills sincronizar --claude --verificar)"
  - "Bash(uv run python -m cdp agenda *)"
  - "Bash(uv run python -m cdp agenda)"
  - "Bash(uv run python -m cdp estado *)"
  - "Bash(uv run python -m cdp estado)"
  - "Bash(uv run python -m cdp executor janela *)"
  - "Bash(uv run python -m cdp executor janela)"
  - "Bash(uv run python -m cdp memoria contexto --escopo desenvolvimento)"
  - "Bash(uv run python -m cdp memoria contexto --escopo operador)"
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

Siga `docs/cdp/playbooks/RETOMAR.md` desde o início. O roteiro reúne estado, agenda,
identificação do papel e consulta de memória por escopo.

O operador começa em leitura. Em desenvolvimento, preserve `book/`, `data/`, `reports/`
e `artifacts/` e atualize `docs/cdp/EM_ANDAMENTO.md` ao encerrar a sessão.

Arquivo gerado — não edite à mão (`uv run python -m cdp skills sincronizar`).
