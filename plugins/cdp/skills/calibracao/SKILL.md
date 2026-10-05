---
name: calibracao
description: Calibração mensal do núcleo quantitativo do CDP — Cabra da Peste — roda o backtest walk-forward com todo o histórico em reports/backtest/<data>/mensal, compara as métricas lado a lado com a execução anterior (números copiados de metrics.json) e propõe, só no resumo, eventuais mudanças de mandato para revisão humana. Nunca altera a configuração. Faz commit e push. Use na tarefa agendada mensal ou quando pedirem a recalibração do CDP.
argument-hint: "[sem argumentos]"
allowed-tools:
  - Read
  - Write
  - Grep
  - Glob
  - Bash(uv sync *)
  - Bash(uv run python -m cdp *)
  - Bash(git status *)
  - Bash(git pull --ff-only)
  - Bash(git fetch *)
  - Bash(git log *)
  - Bash(git diff *)
  - Bash(git add *)
  - Bash(git commit *)
  - Bash(git push)
---

# CDP — calibração mensal (rotina local)

Rotina sem supervisão: não faça perguntas; se algo bloquear, pare e explique no resumo. O
backtest é **código** (`src/cdp/backtest/`); você executa, lê `metrics.json` e escreve um resumo.
Contexto: `docs/cdp/METODOLOGIA.md` e a calibração-base em `reports/backtest/2026-10-05/CALIBRACAO.md`.

## Regras invioláveis

- **Nunca altere** `configs/cdp/fund.yaml` nem código: mudanças de mandato são só **propostas** no
  resumo, para decisão humana (qualquer mudança altera o `config_hash` e precisa ser auditada).
- Números **copiados** de `metrics.json`; apresente valores lado a lado, sem calcular diferenças.
- O backtest usa só sinais point-in-time; a camada de IA e a escada de drawdown não entram.
- Nunca use `git push --force`, `rebase`, `reset` ou `merge`.

## Passos

1. Confirme a raiz do repositório; `git pull --ff-only` (se falhar, pare); `uv sync --extra dev --extra ai`.
2. Hoje (Brasília) = campo `agora_brasilia` de `uv run python -m cdp agenda`. Se a pasta
   `reports/backtest/AAAA-MM-DD/mensal` de hoje já existir, encerre: "Calibração de hoje já feita".
3. Backtest com todo o histórico desde o primeiro rebalanceamento viável usado na calibração-base:

   ```sh
   uv run python -m cdp backtest --start 2021-01-04 --out reports/backtest/AAAA-MM-DD/mensal
   ```

4. Execução anterior: a pasta `reports/backtest/*/mensal/` mais recente antes de hoje; se não
   houver, a variante escolhida em `reports/backtest/2026-10-05/CALIBRACAO.md` (pasta indicada lá).
5. Escreva `reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md` (pt-BR) com:
   - período, nº de rebalanceamentos e a pasta de comparação;
   - tabela lado a lado (atual × anterior), valores copiados de `metrics.json`: retorno a.a.,
     vol a.a., Sharpe (excesso e bruto), max drawdown, custos a.a., giro semanal, P&L específico
     e fatorial a.a., PSR, Sharpe deflacionado, % do tempo com vol na banda, IC médio por sinal;
   - leitura qualitativa (estabilidade dos sinais, custos, risco) e **propostas** de mudança, se
     houver, marcadas como "para revisão humana — não aplicadas".
6. Publicação:

   ```sh
   git add reports/backtest
   git commit -m "CDP: calibração mensal AAAA-MM-DD"
   git push
   ```

## Resumo final (até 10 linhas)

Pasta do resultado; principais métricas atuais × anteriores (copiadas); propostas para revisão
humana (ou "nenhuma"); estado do commit/push.
