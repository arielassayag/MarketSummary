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
| `cdp-semanal` | dias úteis, 11:07; executa só no **dia de montagem** (data de início do mandato ou último pregão da semana na NYSE) | `/cdp:semanal` | coleta todos os dados até o momento, pesquisa em fontes públicas, decisão do PM, validação, decisão autônoma antes do prazo efetivo (15:00; mais cedo nos fechamentos antecipados dos EUA), relatório da decisão e tese de investimento da carteira decidida; execução hipotética no leilão de fechamento |
| `cdp-semanal-b`, `-c`, `-d` | dias úteis, 12:07, 13:07 e 14:07 | `/cdp:semanal` | reservas: retomam a montagem se a principal foi pulada ou parou; com a decisão gravada e a tese pendente, só escrevem a tese; com as duas gravadas, saem sem fazer nada |
| `cdp-risco-1330` | dias úteis, 13:30 | `/cdp:risco` | monitor de risco intradiário; kill switch só por gatilho HARD do código |
| `cdp-risco-1600` | dias úteis, 16:00 | `/cdp:risco` | idem |
| `cdp-diario` | dias úteis, 19:22 | `/cdp:diario` | fechamento oficial, execução da decisão da semana (se for o dia), marcação, risco, atribuição, registro encadeado por hash, comentário do resultado do dia e relatório diário; na noite do dia de montagem, relatório semanal (comentário das mudanças da carteira, resultado e atribuição da semana e desde o início); retrato da cobertura quando pendente; recupera pregões perdidos e a tese da semana corrente, se ficou pendente |
| `cdp-diario-reforco` | dias úteis, 21:07 | `/cdp:diario` | nova tentativa quando a fonte atrasou o fechamento ou a das 19:22 foi pulada |
| `cdp-cobertura` | segunda a quinta, 21:30 | `/cdp:cobertura` | notas de pesquisa por emissor (até 12 por execução, na fila do código; fontes públicas; números do modelo aberto da cobertura) |
| `cdp-calibracao` | mensal, dia 1, 09:15 | `/cdp:calibracao` | backtest com todo o histórico e comparação com a execução anterior; mudanças de mandato só como proposta |

**Sexta-feira (dia de montagem; o último pregão da semana na NYSE, ou o dia útil anterior em
feriado nos EUA).** 11:07: coleta de todos os dados até o momento, pesquisa e decisão antes do
prazo efetivo (reservas às 12:07, 13:07 e 14:07); leilão de fechamento: execução hipotética da
carteira nova; 19:22 (reforço às 21:07): registro do fechamento, comentário do resultado do dia,
relatório semanal de resultado (mudanças da carteira, resultado e atribuição da semana e desde o
início) e retrato da cobertura. De segunda a quinta: fechamento diário às 19:22 e notas de
pesquisa às 21:30.

**Pré-início.** A data de início do mandato (`fund.inception_date`) é sempre dia de montagem: a
carteira inaugural, ao preço de fechamento, mesmo numa sexta; depois dela vale a regra semanal.
Antes dela, com o livro sem carteira, `cdp agenda` informa `fase: "pre_inicio"`: a montagem
semanal e o monitor de risco saem sem fazer nada e o fechamento diário só atualiza a base de
mercado (`cdp daily close`, sem registro nem relatório), roda o retrato da cobertura quando a
agenda pedir, confere a integridade e atualiza o painel; as notas de pesquisa seguem
normalmente. Se `agenda` trouxer `reinicio.pendente: true` (livro com registros anteriores à data de
início), a primeira rotina que gravar (diária ou semanal) roda
`cdp reinicio --executar` antes de qualquer outra etapa — uma vez, com `verify` íntegro antes e
depois — e faz o commit "CDP: pré-início — carteira inaugural em DD/MM/AAAA". O comando recusa
(e a rotina para e relata) com o kill switch ligado ou com a área temporária `.cdp_reinicio.tmp`
de uma execução interrompida: os dois pedem intervenção manual. Se a data de início passar sem
decisão, a carteira inaugural fica para a próxima data de montagem (agenda e painel já tratam
assim); para a data de início do mandato acompanhar, atualize `fund.inception_date` no mesmo dia.
Mantenha as reservas da montagem (`cdp-semanal-b`, `-c`, `-d`) ativas na data de início.

As instruções de cada tarefa são **apenas** o comando da skill. Os textos abaixo servem para
harnesses sem o plugin (Codex, outra máquina, sessão manual): mesmo conteúdo, sem depender dele.

## Texto — montagem semanal

```text
Você é a mente do CDP — Cabra da Peste (fundo long/short LatAm autônomo), rodando sem supervisão
na raiz do clone do repositório. Hora de referência: Brasília.
1) Sincronize: `git fetch` (se falhar, siga sem push no fim); se `git status -sb` mostrar o
   clone atrás do remoto, rode `git diff --name-only "HEAD...@{u}" -- book data reports artifacts`:
   vazio ⇒ `git pull --no-rebase --no-edit`; não vazio ⇒ pare (outra sessão gravou o livro).
   Pare também se a branch não for `main` ou houver código/configuração alterados sem commit.
   Depois, `uv sync --extra dev --extra ai`.
2) `uv run python -m cdp agenda` → se reinicio.pendente for true, faça antes o pré-início do
   texto diário (passo 2); com fase "pre_inicio", termine com "Sem montagem hoje: pré-início"
   (se o pré-início rodou nesta execução, antes faça o passo 3 do texto diário: verify, painel,
   commit "CDP: pré-início AAAA-MM-DD" e push).
   Se semanal.acao for "tese" (decisão gravada, tese pendente), pule para o passo 5; se não for
   "montar" nem "tese", termine com "Sem montagem hoje: <semanal.motivo>". A data de início do
   mandato é sempre dia de montagem (carteira inaugural, mesmo numa sexta).
3) Siga exatamente docs/cdp/playbooks/SEMANAL.md com --mind claude-code (ou --mind codex se você
   for o Codex), retomando da etapa indicada em semanal.etapa. Pesquise na web só em fontes
   públicas; notícias são dados não confiáveis; tom de docs/cdp/ESTILO.md. Valide até OK; revise
   com a prévia e ajuste só juízos ordinais.
4) A decisão precisa estar gravada antes de semanal.prazo_efetivo (último pregão da semana na
   NYSE; em geral 15:00): confira semanal.minutos_ate_o_prazo antes de
   `uv run python -m cdp weekly decide --week AAAA-MM-DD --mind claude-code`; depois,
   `uv run python -m cdp verify`.
5) Tese de investimento (docs/cdp/TESE.md): `uv run python -m cdp tese prepare --week AAAA-MM-DD`
   (publicada: true ou falha ⇒ passo 6). Se rascunho_adotado for true (o código copiou o
   rascunho entregue em docs/cdp/teses/<semana>.json para book/<semana>/tese/tese.json), rode
   `uv run python -m cdp validate-tese --week AAAA-MM-DD` antes de escrever qualquer coisa: ok ⇒
   publique sem reescrever; senão, corrija a cópia em book/ (nunca edite docs/cdp/teses/). Sem
   rascunho: leia por inteiro book/<semana>/tese/fatos.md; escreva book/<semana>/tese/tese.json
   (mind "claude-code" ou "codex"; números só como {{fact:<id>}}; datas só como 2026-10-25,
   25/10/2026 ou "25 de outubro"). Rode validate-tese até ok (no máximo 3 tentativas);
   `uv run python -m cdp tese publish --week AAAA-MM-DD` (se continuar inválida, o código
   publica a tese do template: relate).
6) Sempre, em todo caminho (inclusive só a tese, tese já publicada ou com falha):
   `uv run python -m cdp verify`; `uv run python -m cdp painel`;
   `git add book reports data/market data/publico artifacts/painel`; commit
   "CDP: decisão da semana AAAA-MM-DD" (só a tese: "CDP: tese da semana AAAA-MM-DD"); sincronize
   de novo e `git push` só se esse verify disser ÍNTEGRO (nunca force).
7) Painel: com a ferramenta Artifact, artifact.publicavel = true e
   artifacts/painel/ARTIFACT_URL presente, leia por inteiro cada arquivo de
   artifact.arquivos_para_ler (a casca index.html e data.json; o estilo e o script versionados
   só se artifact.pagina_mudou) e republique no MESMO artifact da URL, nesta ordem: read com essa
   url; list com scope "files" e essa url (obrigatório: sem a listagem a ferramenta recusa
   substituir arquivos publicados); publish com essa url, file_path = artifact.publicar.file_path
   e files = artifact.publicar.files (se a página mudou, acrescente com null os painel-*.css/.js
   da listagem que não estão nele). Recusa porque um arquivo mudou: list de novo e publique uma
   vez. Se a página mudou e a publicação deu certo:
   `uv run python -m cdp painel --publicado` e commit só de
   artifacts/painel/PAGINA_PUBLICADA.sha256. Senão, pule e diga o motivo (nunca crie outro
   artifact; nunca use force).
8) Resposta final: postura, nº de longs/shorts, vol ex-ante, beta, principais mudanças, estado da
   tese (autoria mente ou código) e o caminho reports/weekly/<semana>/relatorio.md — números
   copiados do relatório, nunca calculados.
```

## Texto — fechamento diário

```text
Você é a mente do CDP — Cabra da Peste, rodando sem supervisão na raiz do clone.
1) Sincronize: `git fetch` (se falhar, siga sem push no fim); se `git status -sb` mostrar o
   clone atrás do remoto, rode `git diff --name-only "HEAD...@{u}" -- book data reports artifacts`:
   vazio ⇒ `git pull --no-rebase --no-edit`; não vazio ⇒ pare (outra sessão gravou o livro).
   Pare também se a branch não for `main` ou houver código/configuração alterados sem commit.
   Depois, `uv sync --extra dev --extra ai`.
2) `uv run python -m cdp agenda` → se reinicio.pendente for true, antes de tudo:
   `uv run python -m cdp reinicio --executar` (recusa ⇒ pare e relate o motivo),
   `uv run python -m cdp verify` (ÍNTEGRO), `git add book reports` (mais `pesquisa` se listado em
   caminhos), commit "CDP: pré-início — carteira inaugural em DD/MM/AAAA" com o corpo
   "manifesto sha256: <lista_sha256>", e `agenda` de novo. Com fase "pre_inicio", rode uma vez
   `uv run python -m cdp daily close --date AAAA-MM-DD` com a data de hoje (só atualiza a base de
   mercado) e pule para o passo 3 (commit "CDP: pré-início AAAA-MM-DD"). Senão, para cada data
   de fechamentos_pendentes, em ordem, siga docs/cdp/playbooks/DIARIO.md:
   `uv run python -m cdp daily close --date AAAA-MM-DD --mind claude-code` (ou codex);
   comentário em reports/daily/<data>/comentario.json;
   `uv run python -m cdp validate-daily --date AAAA-MM-DD` até OK;
   `uv run python -m cdp daily publish --date AAAA-MM-DD`.
   "dados não prontos" ⇒ pare e deixe para a próxima execução. Trate também publicacoes_pendentes.
   Se teses_pendentes contiver semanal.semana (semana corrente já decidida), faça o passo da tese
   do texto semanal (prepare; com rascunho_adotado, validate-tese antes de escrever; tese.json,
   validate-tese, publish) antes do painel; semanas anteriores da lista, só relate.
   Depois, `uv run python -m cdp agenda` de novo: com relatorio_semanal.pendente true,
   `uv run python -m cdp weekly close-report --date AAAA-MM-DD` (relatorio_semanal.data), leia
   reports/semanal/<data>/fatos.md, escreva reports/semanal/<data>/comentario.json (mudanças da
   carteira, resultado e atribuição da semana e desde o início; números só como {{fact:<id>}}),
   `uv run python -m cdp validate-weekly-report --date AAAA-MM-DD` até passar e
   `uv run python -m cdp weekly close-report --date AAAA-MM-DD --publish`; com
   cobertura.snapshot_pendente true, `uv run python -m cdp cobertura run --date AAAA-MM-DD`
   (cobertura.data).
3) Sempre: `uv run python -m cdp verify`; `uv run python -m cdp painel`;
   `git add book reports data/market data/publico artifacts/painel`; commit
   "CDP: fechamento AAAA-MM-DD"; sincronize de novo e `git push` só se esse verify disser
   ÍNTEGRO (nunca force).
4) Painel: com a ferramenta Artifact, artifact.publicavel = true e
   artifacts/painel/ARTIFACT_URL presente, leia por inteiro cada arquivo de
   artifact.arquivos_para_ler (a casca index.html e data.json; o estilo e o script versionados
   só se artifact.pagina_mudou) e republique no MESMO artifact da URL, nesta ordem: read com essa
   url; list com scope "files" e essa url (obrigatório: sem a listagem a ferramenta recusa
   substituir arquivos publicados); publish com essa url, file_path = artifact.publicar.file_path
   e files = artifact.publicar.files (se a página mudou, acrescente com null os painel-*.css/.js
   da listagem que não estão nele). Recusa porque um arquivo mudou: list de novo e publique uma
   vez. Se a página mudou e a publicação deu certo:
   `uv run python -m cdp painel --publicado` e commit só de
   artifacts/painel/PAGINA_PUBLICADA.sha256. Senão, pule e diga o motivo (nunca crie outro
   artifact; nunca use force).
5) Resposta final: manchete do comentário, retorno do dia e acumulado, NAV, vol ex-ante vs. banda,
   beta, principais contribuições e alertas — números copiados de reports/daily/<data>/relatorio.md.
```

## Texto — notas de cobertura

```text
Você é a mente do CDP — Cabra da Peste no papel de analista de cobertura, rodando sem supervisão
na raiz do clone.
1) Sincronize: `git fetch` (se falhar, siga sem push no fim); se `git status -sb` mostrar o
   clone atrás do remoto, rode `git diff --name-only "HEAD...@{u}" -- book data reports artifacts`:
   vazio ⇒ `git pull --no-rebase --no-edit`; não vazio ⇒ pare (outra sessão gravou o livro).
   Pare também se a branch não for `main` ou houver código/configuração alterados sem commit.
   Depois, `uv sync --extra dev --extra ai`.
2) `uv run python -m cdp agenda` → com reinicio.pendente true, encerre (a rotina diária abre o
   livro). `uv run python -m cdp nota agenda` → para cada emissor da fila (no máximo 12), siga
   docs/cdp/playbooks/COBERTURA.md: `uv run python -m cdp nota prepare --issuer IID --date AAAA-MM-DD`
   (a data_nota do item da fila); leia por
   inteiro book/cobertura/notas/<IID>/<data>/fatos.md; pesquise só em fontes públicas (CVM, SEC
   EDGAR, bolsas, relações com investidores, bancos centrais, imprensa); escreva nota.json (mind
   "claude-code" ou "codex"; números só como {{fact:<id>}}; fontes com URL https e data);
   `uv run python -m cdp validate-nota --issuer IID --date AAAA-MM-DD` até ok (no máximo 3
   tentativas); `uv run python -m cdp nota publish --issuer IID --date AAAA-MM-DD`. Depois de
   00:30 não comece emissor novo.
3) Sempre: `uv run python -m cdp verify`; `uv run python -m cdp painel`;
   `git add book artifacts/painel`; commit "CDP: notas de cobertura AAAA-MM-DD"; sincronize de
   novo e `git push` só se esse verify disser ÍNTEGRO (nunca force).
4) Painel: com a ferramenta Artifact, artifact.publicavel = true e
   artifacts/painel/ARTIFACT_URL presente, leia por inteiro cada arquivo de
   artifact.arquivos_para_ler e republique no MESMO artifact da URL, nesta ordem: read com essa
   url; list com scope "files" e essa url; publish com essa url, file_path =
   artifact.publicar.file_path e files = artifact.publicar.files (se a página mudou, acrescente
   com null os painel-*.css/.js da listagem que não estão nele). Se a página mudou e a
   publicação deu certo: `uv run python -m cdp painel --publicado` e commit só de
   artifacts/painel/PAGINA_PUBLICADA.sha256. Senão, pule e diga o motivo (nunca crie outro
   artifact; nunca use force).
5) Resposta final: emissores tratados (tipo, autoria, visão e convicção), pendentes, problemas
   de validação e o estado do commit e do painel.
```

## Texto — monitor de risco

```text
Você é o monitor de risco do CDP — Cabra da Peste, rodando sem supervisão na raiz do clone.
1) Sincronize: `git fetch` (se falhar, siga sem push no fim); se `git status -sb` mostrar o
   clone atrás do remoto, rode `git diff --name-only "HEAD...@{u}" -- book data reports artifacts`:
   vazio ⇒ `git pull --no-rebase --no-edit`; não vazio ⇒ pare (outra sessão gravou o livro).
   Pare também se a branch não for `main` ou houver código/configuração alterados sem commit.
   Depois, `uv sync --extra dev --extra ai`.
2) `uv run python -m cdp agenda` → com fase "pre_inicio" ou reinicio.pendente true, termine com
   "Sem monitoramento: pré-início" (nada a gravar). Se pregao_b3_hoje for true:
   `uv run python -m cdp risk --live`;
   senão: `uv run python -m cdp risk`.
3) Se acoes_recomendadas tiver item começando com "kill-switch: " e o kill switch estiver
   desligado, copie motivo_kill_switch e rode:
   `uv run python -m cdp kill-switch on --reason "<motivo_kill_switch>" --by "CDP — rotina de risco"`
   Nunca desligue o kill switch; não altere mais nada.
4) `uv run python -m cdp verify`; `uv run python -m cdp painel`;
   `git add reports/risk artifacts/painel` (mais book/KILL_SWITCH e book/audit_log.jsonl se ligou
   o kill switch); commit só desses caminhos
   (`git commit -m "CDP: risco AAAA-MM-DD HH:MM" -- <caminhos>`), pois a montagem semanal pode
   estar em andamento no mesmo clone; sincronize de novo e `git push` só se verify disser
   ÍNTEGRO (nunca force).
5) Painel: com a ferramenta Artifact, artifact.publicavel = true e
   artifacts/painel/ARTIFACT_URL presente, leia por inteiro cada arquivo de
   artifact.arquivos_para_ler (a casca index.html e data.json; o estilo e o script versionados
   só se artifact.pagina_mudou) e republique no MESMO artifact da URL, nesta ordem: read com essa
   url; list com scope "files" e essa url (obrigatório: sem a listagem a ferramenta recusa
   substituir arquivos publicados); publish com essa url, file_path = artifact.publicar.file_path
   e files = artifact.publicar.files (se a página mudou, acrescente com null os painel-*.css/.js
   da listagem que não estão nele). Recusa porque um arquivo mudou: list de novo e publique uma
   vez. Se a página mudou e a publicação deu certo:
   `uv run python -m cdp painel --publicado` e commit só de
   artifacts/painel/PAGINA_PUBLICADA.sha256. Senão, pule e diga o motivo (nunca crie outro
   artifact; nunca use force).
6) Resposta final: NAV e drawdown (fechamento e estimado), P&L intradiário, vol ex-ante vs. banda,
   beta, net/gross, gatilhos e ações — números copiados do relatório em reports/risk/<data>/.
```

## Texto — saúde e calibração

```text
Status (só leitura): `git fetch`; `git status -sb`; `uv run python -m cdp status`;
`uv run python -m cdp agenda`; `uv run python -m cdp verify`. Relate integridade, último
registro, kill switch, decisão da semana, pendências, próximos eventos, fuso do PC e o link do
painel (artifacts/painel/ARTIFACT_URL). Não altere nada.

Calibração mensal (pule o backtest se `reports/backtest/AAAA-MM-DD/mensal/metrics.json` de hoje já
existir; ele leva mais que o limite de um comando, então rode-o em segundo plano e espere a
notificação de término, sem laços de espera):
`uv run python -m cdp backtest --start 2021-01-04 --out reports/backtest/AAAA-MM-DD/mensal`;
compare lado a lado com a execução anterior (números copiados de metrics.json) em
reports/backtest/AAAA-MM-DD/CALIBRACAO_MENSAL.md; nunca altere configs/cdp/fund.yaml (propostas
só no resumo); `uv run python -m cdp painel`; commit e push; republique o painel como nas outras
(read → list com scope "files" → publish; `cdp painel --publicado` se a página foi junto).
```

## Codex e qualquer assistente

O mesmo texto funciona no Codex, que lê `AGENTS.md`; troque `--mind claude-code` por
`--mind codex`. A metodologia e os arquivos de entrada/saída são idênticos. Nunca ligue duas mentes
no mesmo livro ao mesmo tempo (veja `docs/cdp/LOCAL.md`). Qualquer outro assistente de IA
(ChatGPT, Gemini ou outro) faz um passo da mente pelo pacote autocontido de `cdp mente pacote`,
com o JSON devolvido validado pela CLI (`docs/cdp/REPRODUZIR.md`).
