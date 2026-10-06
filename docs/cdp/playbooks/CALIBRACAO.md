# Roteiro de calibração do CDP — backtest mensal (dia 1, 9h15 de Brasília)

Procedimento único da calibração mensal, igual em **qualquer harness**. O backtest é **código**
(`src/cdp/backtest/`); a mente executa, lê `metrics.json` e escreve um resumo comparativo. As
skills (`cdp-calibracao`, `/cdp:calibracao`) e o prompt da rotina `cdp-calibracao` só fazem a
entrada e a saída da execução. Contexto: `docs/cdp/METODOLOGIA.md` e a calibração-base em
`reports/backtest/2026-10-05/CALIBRACAO.md`.

## Regras

- **Nunca altere** `configs/cdp/fund.yaml` nem código: mudanças de mandato são só **propostas**,
  para decisão humana (qualquer mudança altera o `config_hash` e precisa ser auditada).
- Números **copiados** de `metrics.json`, lado a lado; nunca calcule diferenças.
- O backtest usa só sinais point-in-time; a camada de IA e a escada de drawdown não entram.
- **Só os comandos deste roteiro** (a CLI do CDP) e leitura de arquivos; nunca
  `python -c`, `jq`, `sleep` nem laços de espera; nenhum comando `git` que grave. Você só escreve
  `reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md`.

## 0. Entrada da execução (uma vez por execução)

Numa rotina agendada, a skill ou o prompt da rotina já fez estes três passos (tarefa
compartilhada: sem trava). **Nunca rode o gate de novo na mesma execução.** Numa sessão de
operador, rode-os à mão com `--manual` no gate:

```sh
uv sync --frozen --extra dev --extra ai
uv run python -m cdp rotinas gate --tarefa cdp-calibracao
uv run python -m cdp sincronizar --executar
```

O gate só executa no dia 1 sem a calibração do mês. `executar: false` ⇒ encerre. Guarde
`execucao` e `mente`. `sincronizar` com `acao: "parar"` ⇒ encerre relatando. **Modo executor.**
Se o prompt disser que a agenda, a sincronização e a publicação são do executor, pule esta seção
e o passo 5.

## Passos

1. Data de hoje (Brasília) = `agora_brasilia` de `uv run python -m cdp agenda`. Se
   `reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md` de hoje existe, encerre ("calibração do mês
   já feita"). Se `reports/backtest/AAAA-MM-DD/mensal/metrics.json` existe (o script de rotina
   rodou o backtest antes, ou uma execução anterior parou depois dele), pule o passo 2: nos dois
   casos, `cdp publicar` leva a pasta `mensal/` junto com o resumo.
2. Backtest com todo o histórico (demora; rode-o uma vez, sem laços de espera e nunca dois ao
   mesmo tempo):

   ```sh
   uv run python -m cdp backtest --start 2021-01-04 --out reports/backtest/AAAA-MM-DD/mensal
   ```

   Se o seu harness limita a duração de um comando (no Claude Code, 10 minutos no primeiro plano,
   ou 30 com `BASH_MAX_TIMEOUT_MS`), rode-o em segundo plano pelo próprio harness e retome do
   passo 3 quando ele terminar — sem `sleep` nem consultas repetidas. Falha: pare e relate.
3. Execução anterior: a pasta `reports/backtest/*/mensal/` mais recente antes de hoje; sem
   nenhuma, a variante escolhida em `reports/backtest/2026-10-05/CALIBRACAO.md`.
4. Escreva `reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md` (pt-BR): período, número de
   rebalanceamentos e a pasta de comparação; tabela atual × anterior com retorno anualizado, vol
   anualizada, Sharpe (excesso e bruto), drawdown máximo, custos, giro semanal, resultado
   específico e fatorial, PSR, Sharpe deflacionado, fração do tempo com vol na banda e IC médio
   por sinal; leitura qualitativa e **propostas** marcadas "para revisão humana — não
   aplicadas".
5. Integridade e publicação (uma vez por execução; esta rotina não regenera o painel):

   ```sh
   uv run python -m cdp verify
   uv run python -m cdp publicar --tarefa cdp-calibracao --mensagem "CDP: calibração mensal AAAA-MM-DD" --execucao <execucao> --mente <mente>
   ```

   Sem push, relate o `motivo`; nunca tente outro caminho.

## Resumo final (até 10 linhas)

Pasta do resultado; principais métricas atuais × anteriores (copiadas); propostas para revisão
humana (ou "nenhuma"); integridade e publicação.
