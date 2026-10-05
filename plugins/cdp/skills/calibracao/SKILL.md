---
name: calibracao
description: Calibração mensal do núcleo quantitativo do CDP — Cabra da Peste — roda o backtest walk-forward com todo o histórico em reports/backtest/<data>/mensal (ou aproveita o que o agendador do sistema já rodou), compara as métricas lado a lado com a execução anterior (números copiados de metrics.json) e propõe, só no resumo, eventuais mudanças de mandato para revisão humana. Nunca altera a configuração. Atualiza o painel, faz commit e push e republica o painel no artifact. Use na tarefa agendada mensal ou quando pedirem a recalibração do CDP.
argument-hint: "[sem argumentos]"
allowed-tools:
  - Read
  - Write
  - Grep
  - Glob
  - Bash(uv sync *)
  - Bash(uv run python -m cdp *)
  - Bash(git branch --show-current)
  - Bash(git status *)
  - Bash(git fetch *)
  - Bash(git pull --no-rebase --no-edit)
  - Bash(git log *)
  - Bash(git diff *)
  - Bash(git add *)
  - Bash(git commit *)
  - Bash(git push)
  - Artifact
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
- **Só os comandos deste roteiro** (os de `allowed-tools`). Para ler saídas, use `Read`/`Grep`/
  `Glob`; nunca rode `python -c`, `jq`, `sleep` nem laços de espera (um pedido de permissão deixa a
  tarefa parada e o app pula as rotinas seguintes).
- Nunca use `git push --force`, `rebase` nem `reset`. O único merge permitido é o
  `git pull --no-rebase --no-edit` da sincronização, quando o remoto não mexeu no livro.

## Passos

1. Confirme a raiz do repositório e o clone dedicado: `git branch --show-current` = `main` e
   `git status --porcelain` sem arquivos rastreados alterados fora de `book/`, `reports/`,
   `data/market/` e `artifacts/painel/` (senão, pare: "clone em desenvolvimento"). Sincronize:
   `git fetch` (se falhar, siga sem push no fim); `git status -sb`; se estiver atrás, rode
   `git diff --name-only "HEAD...@{u}" -- book data reports artifacts` — vazio ⇒
   `git pull --no-rebase --no-edit`; não vazio ⇒ pare (outra sessão gravou o livro). Depois,
   `uv sync --extra dev --extra ai`.
2. Hoje (Brasília) = campo `agora_brasilia` de `uv run python -m cdp agenda`. Com `Glob`, veja
   `reports/backtest/AAAA-MM-DD/` de hoje:
   - `CALIBRACAO_MENSAL.md` existe → encerre: "Calibração de hoje já feita".
   - `mensal/metrics.json` existe (o agendador do sistema roda o backtest antes, ou uma execução
     anterior foi interrompida depois dele) → pule o passo 3.
3. Backtest com todo o histórico desde o primeiro rebalanceamento viável usado na calibração-base:

   ```sh
   uv run python -m cdp backtest --start 2021-01-04 --out reports/backtest/AAAA-MM-DD/mensal
   ```

   Leva mais que o tempo-limite de um comando: rode-o em segundo plano (Bash com
   `run_in_background`) e **encerre o turno sem esperar** — nada de `sleep`, laços ou consultas
   repetidas. A notificação de término reabre a sessão; então siga do passo 4. Nunca rode dois
   backtests ao mesmo tempo. Se falhar, pare e relate a mensagem. (Sem interface, com `claude -p`,
   uma tarefa em segundo plano morre quando a resposta termina: por isso `scripts/cdp_run_task.*
   calibracao` roda o backtest antes de chamar a skill.)

4. Execução anterior: a pasta `reports/backtest/*/mensal/` mais recente antes de hoje; se não
   houver, a variante escolhida em `reports/backtest/2026-10-05/CALIBRACAO.md` (pasta indicada lá).
5. Escreva `reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md` (pt-BR) com:
   - período, nº de rebalanceamentos e a pasta de comparação;
   - tabela lado a lado (atual × anterior), valores copiados de `metrics.json`: retorno a.a.,
     vol a.a., Sharpe (excesso e bruto), max drawdown, custos a.a., giro semanal, P&L específico
     e fatorial a.a., PSR, Sharpe deflacionado, % do tempo com vol na banda, IC médio por sinal;
   - leitura qualitativa (estabilidade dos sinais, custos, risco) e **propostas** de mudança, se
     houver, marcadas como "para revisão humana — não aplicadas".
6. Integridade e painel (código; o painel inclui os backtests):
   `uv run python -m cdp verify` e `uv run python -m cdp painel` (grava `artifacts/painel/data.json`,
   `index.html` — só quando o template muda — e a cópia local; anote o bloco `artifact`). Se o
   painel falhar, siga sem ele.
7. Publicação:

   ```sh
   git add reports/backtest artifacts/painel
   git commit -m "CDP: calibração mensal AAAA-MM-DD" -- reports/backtest artifacts/painel
   ```

   Push só se `verify` disse `ÍNTEGRO` e o `git fetch` funcionou: repita a sincronização do passo 1
   e então rode `git push`. Se não, ou se o push for rejeitado: não force; relate.

8. Painel no artifact, **no mesmo artifact** (URL em `artifacts/painel/ARTIFACT_URL`, também em
   `artifact.url`; a rotina nunca cria um artifact novo): sem a ferramenta `Artifact` nesta sessão,
   pule e anote no resumo. Se `cdp painel` falhou ou trouxe `artifact.publicavel: false`, não
   leia nem publique nada; anote o `artifact.motivo`. Sem `artifacts/painel/ARTIFACT_URL`
   (`artifact.url` nulo), não publique e anote "sem ARTIFACT_URL". Com `publicavel: true`: leia por
   inteiro, com `Read` (em partes com `offset`/`limit`, até a última linha), cada arquivo de
   `artifact.arquivos_para_ler` — sempre `artifacts/painel/data.json`; `artifacts/painel/index.html`
   só quando `artifact.pagina_mudou` for `true`. Chame `Artifact` com essa `url`, nesta ordem:
   `action: "read"` (uma vez); `action: "list"` com `scope: "files"` (obrigatório: a ferramenta
   só substitui um arquivo publicado que a sessão leu pelo caminho, viu numa listagem ou
   publicou); e `action: "publish"` com `files: {"data.json": "artifacts/painel/data.json"}` e,
   só quando `pagina_mudou` for `true`, `file_path: "artifacts/painel/index.html"`. Se a
   ferramenta recusar a atualização só com `files`, leia `index.html` por inteiro e publique de
   novo com `file_path` e `files`. Se a recusa disser que `data.json` mudou desde a listagem,
   repita o `list` com `scope: "files"` uma vez e publique uma única vez. Recusa por conflito na
   página: rode `uv run python -m cdp painel` de novo, leia o que `artifact.arquivos_para_ler`
   pedir, repita o `list` e publique uma única vez; nunca use `force`. Só depois de uma
   publicação bem-sucedida que incluiu `index.html`, com `pagina_mudou: true`:
   `uv run python -m cdp painel --publicado`,
   `git add artifacts/painel/PAGINA_PUBLICADA.sha256` e
   `git commit -m "CDP: painel publicado" -- artifacts/painel/PAGINA_PUBLICADA.sha256` (sem esse
   registro, `pagina_mudou` continua `true` e a próxima rotina publica a página de novo). Falha
   ou recusa: não insista; relate.

## Resumo final (até 10 linhas)

Pasta do resultado; principais métricas atuais × anteriores (copiadas); propostas para revisão
humana (ou "nenhuma"); estado do commit/push; painel (URL republicada ou o motivo de não ter sido).
