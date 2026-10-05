---
name: status
description: Checagem de saúde do CDP — Cabra da Peste, somente leitura — estado do fundo e do calendário, agenda (decisão da semana, prazos, fechamentos e publicações pendentes, próximos eventos), integridade da trilha de auditoria, do track record e da base de mercado, e estado do git (alterações locais, commits não enviados) e o link do painel (artifact). Não altera nada. Use na tarefa agendada de segunda cedo ou quando pedirem o status do CDP.
argument-hint: "[sem argumentos]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(uv sync *)
  - Bash(uv run python -m cdp *)
  - Bash(git status *)
  - Bash(git fetch *)
  - Bash(git log *)
  - Bash(git diff *)
  - Bash(git branch *)
---

# CDP — saúde da operação (somente leitura)

Rotina sem supervisão e **sem efeitos**: não escreva arquivos, não faça commit, pull ou push, não
mexa no kill switch. Números são copiados das saídas da CLI; nunca calculados. Contexto do mandato
e das rotinas: `docs/cdp/METODOLOGIA.md` e `docs/cdp/LOCAL.md`.

## Passos

1. Confirme a raiz do repositório (`pyproject.toml` e `src/cdp/`); senão, pare.
2. Git (sem alterar a cópia de trabalho):

   ```sh
   git fetch --quiet
   git status -sb
   git log -5 --oneline
   ```

   Anote: branch, commits à frente/atrás do remoto, alterações locais não commitadas.
3. Ambiente: `uv sync --extra dev --extra ai` (só instala dependências; não muda dados).
4. Estado do fundo:

   ```sh
   uv run python -m cdp status
   uv run python -m cdp agenda
   uv run python -m cdp verify
   ```

5. Painel (só leitura; não gere nem republique): leia `artifacts/painel/ARTIFACT_URL` (uma linha;
   se não existir, "painel ainda não publicado") e veja quando os dados do painel foram commitados:

   ```sh
   git log -1 --format=%ci -- artifacts/painel/data.json
   ```

## O que relatar (resumo final, até 12 linhas)

- **Integridade**: resultado de `verify` (`ÍNTEGRO` ou cada falha listada).
- **Fundo**: último registro diário, NAV atual (`nav_atual_usd`), kill switch.
- **Semana**: `semanal.semana`, decisão gravada?, `semanal.acao`/`motivo`; se `decisao_perdida`
  for `true`, destaque. Tese de investimento: semanas em `teses_pendentes` (decididas sem tese
  publicada; a da semana corrente é concluída pela skill `semanal` ou `diario`).
- **Pendências**: `fechamentos_pendentes` e `publicacoes_pendentes` (rode a skill `diario`).
- **Próximos eventos**: `proximos_eventos` (horários de Brasília).
- **Relógio**: se `pc_menos_brasilia_horas` ≠ 0, avise que o PC não está no fuso de Brasília e que
  os horários das tarefas agendadas precisam ser convertidos (ver `docs/cdp/LOCAL.md`).
- **Painel**: URL do artifact (ou "ainda não publicado") e a data do último commit de
  `artifacts/painel/data.json`; se for anterior ao último registro diário, avise que a rotina
  `diario` não atualizou o painel.
- **Git**: branch diferente de `main` ou alterações rastreadas fora de `book/`, `reports/`,
  `data/market/` e `artifacts/painel/` (as rotinas que gravam param nesse caso: precisam de um
  clone dedicado na `main`), atraso em relação ao remoto e commits não enviados (push retido por
  falha de `verify`, de rede ou por divergência — ver `docs/cdp/LOCAL.md`, solução de problemas).
