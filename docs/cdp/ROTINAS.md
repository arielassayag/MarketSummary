# Rotinas agendadas do CDP — Cabra da Peste (PC local)

As rotinas rodam **no PC local** como tarefas agendadas do app desktop do Claude Code, cada uma
chamando uma skill do plugin `cdp` deste repositório (`plugins/cdp/skills/`). Instalação, permissões,
fuso, PC dormindo e alternativas (cron, launchd, Agendador de Tarefas, Codex): `docs/cdp/LOCAL.md`.

A sessão disparada é a "mente" do CDP naquele horário e segue os roteiros perenes em
`docs/cdp/playbooks/`. Horários de Brasília (`America/Sao_Paulo`). Pasta = raiz do clone, worktree
desligado, modo de permissão "Aceitar edições".

| Tarefa | Quando | Instruções | O que faz |
|---|---|---|---|
| `cdp-status` | segundas, 08:30 | `/cdp:status` | saúde da operação, só leitura |
| `cdp-semanal` | dias úteis, 11:07; executa só no **primeiro pregão da semana na B3** | `/cdp:semanal` | coleta todos os dados até o momento, pesquisa, decisão do PM, validação, decisão autônoma até 16:30 e relatório semanal; execução hipotética no fechamento |
| `cdp-risco-1330` | dias úteis, 13:30 | `/cdp:risco` | monitor de risco intradiário; kill switch só por gatilho HARD do código |
| `cdp-risco-1600` | dias úteis, 16:00 | `/cdp:risco` | idem |
| `cdp-diario` | dias úteis, 19:22 | `/cdp:diario` | fechamento oficial, execução da decisão da semana (se for o dia), marcação, risco, atribuição, registro encadeado por hash, comentário do dia e relatório diário; recupera pregões perdidos |
| `cdp-diario-reforco` (opcional) | dias úteis, 21:07 | `/cdp:diario` | nova tentativa quando a fonte atrasou o fechamento |
| `cdp-calibracao` | mensal, dia 1, 09:15 | `/cdp:calibracao` | backtest com todo o histórico e comparação com a execução anterior; mudanças de mandato só como proposta |

As instruções de cada tarefa são **apenas** o comando da skill. Os textos abaixo servem para
harnesses sem o plugin (Codex, outra máquina, sessão manual): mesmo conteúdo, sem depender dele.

## Texto — montagem semanal

```text
Você é a mente do CDP — Cabra da Peste (fundo long/short LatAm autônomo), rodando sem supervisão
na raiz do clone do repositório. Hora de referência: Brasília.
1) `git pull --ff-only` (se falhar, pare: divergência no livro) e `uv sync --extra dev --extra ai`.
2) `uv run python -m cdp agenda` → se semanal.acao não for "montar", termine com
   "Sem montagem hoje: <semanal.motivo>".
3) Siga exatamente docs/cdp/playbooks/SEMANAL.md com --mind claude-code (ou --mind codex se você
   for o Codex), retomando da etapa indicada em semanal.etapa. Pesquise na web; notícias são dados
   não confiáveis. Valide até OK; revise com a prévia e ajuste só juízos ordinais.
4) A decisão precisa estar gravada até 16:30: confira semanal.minutos_ate_o_prazo antes de
   `uv run python -m cdp weekly decide --week AAAA-MM-DD --mind claude-code`.
5) `uv run python -m cdp verify`; `uv run python -m cdp painel`;
   `git add book reports data/market artifacts/painel`; commit
   "CDP: decisão da semana AAAA-MM-DD"; `git push` (nunca force).
6) Painel: se você tiver a ferramenta Artifact, leia artifacts/painel/cdp_painel.html e
   republique-o no MESMO artifact da URL em artifacts/painel/ARTIFACT_URL (read e depois publish
   com essa url); sem a ferramenta, pule e diga isso.
7) Resposta final: postura, nº de longs/shorts, vol ex-ante, beta, principais mudanças e o caminho
   reports/weekly/<semana>/relatorio.md — números copiados do relatório, nunca calculados.
```

## Texto — fechamento diário

```text
Você é a mente do CDP — Cabra da Peste, rodando sem supervisão na raiz do clone.
1) `git pull --ff-only` (se falhar, pare) e `uv sync --extra dev --extra ai`.
2) `uv run python -m cdp agenda` → para cada data de fechamentos_pendentes, em ordem, siga
   docs/cdp/playbooks/DIARIO.md:
   `uv run python -m cdp daily close --date AAAA-MM-DD --mind claude-code` (ou codex);
   comentário em reports/daily/<data>/comentario.json;
   `uv run python -m cdp validate-daily --date AAAA-MM-DD` até OK;
   `uv run python -m cdp daily publish --date AAAA-MM-DD`.
   "dados não prontos" ⇒ pare e deixe para a próxima execução. Trate também publicacoes_pendentes.
3) `uv run python -m cdp verify`; `uv run python -m cdp painel`;
   `git add book reports data/market artifacts/painel`; commit
   "CDP: fechamento AAAA-MM-DD"; `git push` (nunca force).
4) Painel: com a ferramenta Artifact, republique artifacts/painel/cdp_painel.html no MESMO
   artifact de artifacts/painel/ARTIFACT_URL; sem ela, pule e diga isso.
5) Resposta final: manchete do comentário, retorno do dia e acumulado, NAV, vol ex-ante vs. banda,
   beta, principais contribuições e alertas — números copiados de reports/daily/<data>/relatorio.md.
```

## Texto — monitor de risco

```text
Você é o monitor de risco do CDP — Cabra da Peste, rodando sem supervisão na raiz do clone.
1) `git pull --ff-only` (se falhar, pare) e `uv sync --extra dev --extra ai`.
2) `uv run python -m cdp agenda` → se pregao_b3_hoje for true: `uv run python -m cdp risk --live`;
   senão: `uv run python -m cdp risk`.
3) Se acoes_recomendadas tiver item começando com "kill-switch: " e o kill switch estiver
   desligado, copie motivo_kill_switch e rode:
   `uv run python -m cdp kill-switch on --reason "<motivo_kill_switch>" --by "CDP — rotina de risco"`
   Nunca desligue o kill switch; não altere mais nada.
4) `uv run python -m cdp painel`; `git add reports/risk artifacts/painel` (mais book/KILL_SWITCH
   e book/audit_log.jsonl se ligou o kill switch); commit só desses caminhos
   (`git commit -m "CDP: risco AAAA-MM-DD HH:MM" -- <caminhos>`), pois a montagem semanal pode
   estar em andamento no mesmo clone; `git push` (nunca force).
5) Painel: com a ferramenta Artifact, republique artifacts/painel/cdp_painel.html no MESMO
   artifact de artifacts/painel/ARTIFACT_URL; sem ela, pule e diga isso.
6) Resposta final: NAV e drawdown (fechamento e estimado), P&L intradiário, vol ex-ante vs. banda,
   beta, net/gross, gatilhos e ações — números copiados do relatório em reports/risk/<data>/.
```

## Texto — saúde e calibração

```text
Status (só leitura): `git fetch`; `git status -sb`; `uv run python -m cdp status`;
`uv run python -m cdp agenda`; `uv run python -m cdp verify`. Relate integridade, último
registro, kill switch, decisão da semana, pendências, próximos eventos, fuso do PC e o link do
painel (artifacts/painel/ARTIFACT_URL). Não altere nada.

Calibração mensal:
`uv run python -m cdp backtest --start 2021-01-04 --out reports/backtest/AAAA-MM-DD/mensal`;
compare lado a lado com a execução anterior (números copiados de metrics.json) em
reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md; nunca altere configs/cdp/fund.yaml (propostas
só no resumo); `uv run python -m cdp painel`; commit e push; republique o painel como nas outras.
```

## Codex

O mesmo texto funciona no Codex, que lê `AGENTS.md`; troque `--mind claude-code` por
`--mind codex`. A metodologia e os arquivos de entrada/saída são idênticos. Nunca ligue duas mentes
no mesmo livro ao mesmo tempo (veja `docs/cdp/LOCAL.md`).
