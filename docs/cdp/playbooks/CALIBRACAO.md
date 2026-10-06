# Roteiro de calibração do CDP — backtest mensal (dia 1, 9h15 de Brasília)

Vale para qualquer harness. O backtest é **código** (`src/cdp/backtest/`); a mente executa, lê
`metrics.json` e escreve um resumo comparativo. Contexto: `docs/cdp/METODOLOGIA.md` e a
calibração-base em `reports/backtest/2026-10-05/CALIBRACAO.md`. Numa rotina agendada, a entrada
e a publicação vêm da skill `cdp-calibracao` (gate → `cdp sincronizar` → este roteiro →
`cdp publicar`); no PC local, a skill `cdp:calibracao` do plugin faz o mesmo.

## Regras

- **Nunca altere** `configs/cdp/fund.yaml` nem código: mudanças de mandato são só **propostas**,
  para decisão humana (qualquer mudança altera o `config_hash` e precisa ser auditada).
- Números **copiados** de `metrics.json`, lado a lado; nunca calcule diferenças.
- O backtest usa só sinais point-in-time; a camada de IA e a escada de drawdown não entram.

## Passos

1. Data de hoje (Brasília) = `agora_brasilia` de `uv run python -m cdp agenda`. Se
   `reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md` de hoje existe, encerre ("calibração do mês
   já feita"). Se `reports/backtest/AAAA-MM-DD/mensal/metrics.json` existe (o executor rodou o
   backtest antes, ou uma execução anterior parou depois dele), pule o passo 2.
2. Backtest com todo o histórico (demora; rode-o uma vez, sem laços de espera e sem rodar dois
   ao mesmo tempo):

   ```sh
   uv run python -m cdp backtest --start 2021-01-04 --out reports/backtest/AAAA-MM-DD/mensal
   ```

3. Execução anterior: a pasta `reports/backtest/*/mensal/` mais recente antes de hoje; sem
   nenhuma, a variante escolhida em `reports/backtest/2026-10-05/CALIBRACAO.md`.
4. Escreva `reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md` (pt-BR): período, número de
   rebalanceamentos e a pasta de comparação; tabela atual × anterior com retorno anualizado, vol
   anualizada, Sharpe (excesso e bruto), drawdown máximo, custos, giro semanal, resultado
   específico e fatorial, PSR, Sharpe deflacionado, fração do tempo com vol na banda e IC médio
   por sinal; leitura qualitativa e **propostas** marcadas "para revisão humana — não
   aplicadas".
5. Integridade e publicação:

   ```sh
   uv run python -m cdp verify
   uv run python -m cdp publicar --tarefa cdp-calibracao --mensagem "CDP: calibração mensal AAAA-MM-DD"
   ```

## Resumo final (até 10 linhas)

Pasta do resultado; principais métricas atuais × anteriores (copiadas); propostas para revisão
humana (ou "nenhuma"); estado da publicação.
