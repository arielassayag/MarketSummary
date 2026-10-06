# Automação do CDP em qualquer harness — nuvem, agendadores e troca de executor

Como as rotinas do CDP rodam sozinhas, em nuvem, usando a capacidade de IA do plano de quem
opera — no Claude Code (escolha atual) ou em qualquer outro harness. Manual do agente:
`AGENTS.md`. Agenda (fonte única): `configs/cdp/rotinas.yaml`. Roteiros: `docs/cdp/playbooks/`.
PC local (app desktop): `docs/cdp/LOCAL.md`. Portal público: `docs/cdp/SITE.md`.

## 1. Visão geral

```text
 agendador (nuvem do Claude Code | GitHub Actions | app desktop | cron/launchd/Windows)
   └─ prompt neutro gerado por `cdp rotinas exportar` (o mesmo texto em qualquer harness)
        1. uv sync --frozen
        2. cdp rotinas gate --tarefa T --adquirir   ← código: executor? atrasada? há trabalho?
           │                                          trava distribuída (ramo cdp-trava):
           │                                          sem a trava, o escritor exclusivo não roda
           ├─ executar: false → "Sem execução: <motivo>" (custo mínimo de modelo)
           └─ executar: true (guarda trava.id e execucao)
        3. cdp sincronizar --executar                ← código: remoto mudou o livro? parar
        4. roteiro docs/cdp/playbooks/<T>.md          ← a mente: pesquisa, juízos, textos (JSON)
        5. cdp publicar --tarefa T --mensagem "CDP: …" --execucao E --trava ID
                                                      ← código: verify, trava confirmada, só o
                                                        que esta execução gravou, commit com
                                                        trailers, push em main (nunca force)
        6. cdp trava liberar --id ID
   push em main ──► GitHub Actions cdp-site.yml ──► GitHub Pages (portal público)
```

- **Quem publica o git**: a própria mente (modo "agente": Claude Code, Gemini CLI, Antigravity)
  ou o executor em volta dela (modo "executor": o script de rotina no Codex, cujo sandbox deixa
  `.git` só de leitura, e o workflow do GitHub Actions). No modo executor, o prompt diz à mente
  que gate, trava, sincronização e publicação não são dela.
- **Quem grava**: só o executor designado em `configs/cdp/executor.yaml` (`local-pc` hoje).
  Cada ambiente diz quem é por `CDP_EXECUTOR` (ou `.cdp/local.yaml`, gravado por
  `uv run python -m cdp executor registrar --como local-pc`). Um ambiente que não é o executor
  sai no gate, sem gravar nada.
- **Quando**: `uv run python -m cdp rotinas listar` (tabela em `AGENTS.md`, seção 4). Horários
  de Brasília; em UTC, some 3 h (o código confere; 21:07 de Brasília vira terça a sábado em UTC).
- **O que mudou**: cada commit de rotina leva os trailers `CDP-Tarefa`, `CDP-Executor`,
  `CDP-Harness`, `CDP-Execucao` e `CDP-Sessao` (link da sessão na nuvem ou da execução no
  Actions); `uv run python -m cdp estado` lê esse histórico.

## 2. Matriz de harnesses (outubro de 2026)

| Harness | Agenda na nuvem? | Usa o plano? | Push neste repositório público? | Lê `AGENTS.md`? | Skills em | Veredito |
|---|---|---|---|---|---|---|
| **Claude Code — rotinas na nuvem** | sim (cron em UTC, mínimo 1 h) | **sim** | sim (proxy do GitHub, com a sua identidade) | sim (`CLAUDE.md` importa) | `.claude/skills/` (plugins não são instalados) | **recomendado** |
| Claude Code no GitHub Actions | sim (cron do Actions) | sim (`CLAUDE_CODE_OAUTH_TOKEN`, 1 ano) | sim (passo de código) | sim | `.claude/skills/` | alternativa |
| Claude Code — app desktop (PC) | não (PC ligado) | sim | sim | sim | plugin `cdp` + `.claude/skills/` | executor atual; reserva quente |
| Codex — `codex exec` pelo agendador do sistema (cron/launchd/Windows) | não (máquina ligada) | **sim** (`codex login` na máquina) | sim (o script publica fora do sandbox) | sim (até 32 KiB) | `.agents/skills/` | alternativa local |
| Codex — `codex exec` no GitHub Actions | sim (cron do Actions) | não: chave de API (`CODEX_API_KEY`) | sim (job publicador, sem IA) | sim (até 32 KiB) | `.agents/skills/` | alternativa paga |
| Codex — automações do app | só local (app aberto) | sim | **não** (sandbox sem push) | sim | `.agents/skills/` | não serve para publicar |
| Codex Cloud | tarefas sem agenda | sim | sim | sim | `.agents/skills/` | manual |
| Gemini CLI no Actions | sim (cron do Actions) | **não** (planos de consumo encerrados em 2026-06-18): chave paga ou Vertex | sim (job publicador, sem IA) | sim (`.gemini/settings.json`) | `.agents/skills/` | alternativa paga |
| Antigravity CLI (`agy`) no Actions | sim (cron do Actions) | não: chave paga do Gemini | sim (job publicador, sem IA) | sim | `.agents/skills/` | **experimental** (confirmar opções com `agy --help`) |
| Jules | cadência diária/semanal | sim (Google AI Pro/Ultra) | por PR | sim | — | só tarefas sem horário fixo |
| Cursor Automations | sim (cron) | uso do plano | por PR | sim | — | possível |
| Copilot automations | sim | sim | só repositórios privados | sim | `.agents/skills/` | indisponível (repositório público) |
| Qualquer CLI sem interface | via cron/launchd/Windows/Actions | depende | sim | depende | `.agents/skills/` | `scripts/cdp_rotina.sh --harness custom` |

O conhecimento do agente não depende do harness: `AGENTS.md` (canônico), roteiros neutros,
`configs/cdp/rotinas.yaml` e skills abertas (Agent Skills) geradas em `.agents/skills/`.
`CLAUDE.md`, `GEMINI.md` e `.gemini/settings.json` só apontam para eles.

## 3. Claude Code na nuvem, passo a passo (nossa escolha)

**a) Pré-requisitos.** Plano com rotinas (Pro, Max, Team ou Enterprise; recurso em prévia).
Confira os limites em claude.ai/settings/usage: a agenda completa dispara cerca de 10 execuções
por dia útil, e a maioria sai no gate com custo mínimo (seção 7). App GitHub do Claude conectado
ao repositório — sem a conexão, as execuções são **puladas** (fechamentos perdidos em silêncio)
e, depois de 72 h, a rotina é desligada; confira a conexão antes de cada dia de montagem. Regra
do ramo `main` no GitHub: bloquear force push e exclusão; **não** exigir PR (as rotinas publicam
direto em `main`). O proxy do GitHub da nuvem não restringe o ramo do push (recusa só exclusões
e o que não é ramo): o push do ramo `cdp-trava` e o de `HEAD:main` funcionam, limitados só pelas
regras do repositório.

**b) Ambientes** (claude.ai/code → Environments): **CDP** e **CDP-ensaio**, só para as
rotinas. Sessões interativas e de desenvolvimento na nuvem usam o ambiente **Default** (ou um
"CDP-dev" sem `CDP_EXECUTOR`): o seletor de ambiente da sessão define a identidade, e uma sessão
aberta no "CDP" passaria por executora (`cdp estado` avisa quando isso acontece).

- Rede: **Total** (a pesquisa usa dezenas de domínios públicos e buscas abertas). Alternativa:
  "Personalizada + padrões" com a lista `rede` de `configs/cdp/rotinas.yaml`.
- Variáveis: `CDP_EXECUTOR=claude-cloud`, `CDP_HARNESS=claude-code`, `TZ=America/Sao_Paulo`,
  `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `BASH_DEFAULT_TIMEOUT_MS=600000`,
  `BASH_MAX_TIMEOUT_MS=1800000`; no CDP-ensaio, também `CDP_ENSAIO=1` (nada é publicado).
- Script de preparação: `uv python install 3.12` (o `uv sync --frozen` roda no passo 1 de cada
  rotina). No CDP-ensaio, o gate instala um gancho `pre-push` que recusa todo push (seção 11).
  **Nenhum segredo** no ambiente: o push usa o proxy do GitHub da própria sessão.

**c) Criar as rotinas.** Os corpos saem prontos, um por tarefa, desligados:

```sh
uv run python -m cdp rotinas exportar --alvo claude-routines --ambiente env_ID_DO_CDP --saida rotinas.json
uv run python -m cdp rotinas exportar --alvo claude-routines --formato md
```

O primeiro gera o JSON da API de rotinas (`name`, `cron_expression` em UTC, `enabled: false`,
`job_config.ccr` com o repositório, as ferramentas e o prompt); o segundo, a mesma coisa legível,
para criar pela interface (Routines → New routine → Cloud: nome, horário e prompt; um repositório
por rotina; nenhum conector). A interface só oferece agendas prontas (de hora em hora, diária,
dias úteis, semanal): `cdp-cobertura` (segunda a quinta) e `cdp-calibracao` (dia 1 do mês)
precisam do `cron_expression` exato — crie pela API (o corpo exportado) ou escolha a agenda mais
próxima na interface e ajuste com `/schedule update` no Claude Code. Níveis de modelo: `--modelo forte=<id> --modelo leve=<id>` (os ids
nunca ficam no repositório). Ensaio: `--ensaio` gera prompts que nunca publicam. Pela API, cada
corpo vai num `create`; o `uuid` do evento já sai novo em cada exportação.

**d) Validar.** "Run now" numa tarefa sem trabalho pendente (o gate sai cedo e prova clone, uv e
rede) e leia a transcrição: verde na lista de execuções não quer dizer sucesso. Depois, a troca de
executor (seção 11).

**e) Fusos.** A interface converte do horário local; a API usa UTC (`cron_utc`). 21:07 de
Brasília = 00:07 UTC de terça a sábado; a repescagem de sábado 10:07 = 13:07 UTC; a cobertura
22:37 de segunda a quinta = 01:37 UTC de terça a sexta.

## 4. Codex

O sandbox `workspace-write` do `codex exec` deixa `.git` só de leitura: a mente do Codex nunca
roda gate com trava, `cdp sincronizar` nem `cdp publicar`. Por isso o Codex usa sempre a
**publicação pelo executor**: `scripts/cdp_rotina.sh --harness codex` (padrão
`--publicacao executor`) roda, fora do sandbox, o gate com a trava, a sincronização, o roteiro
pela mente (prompt sem git), `cdp publicar` e a liberação da trava.

- **Pelo plano** (ChatGPT): `codex login` uma vez na máquina dedicada às rotinas e o agendador
  do sistema chamando o script:

  ```sh
  uv run python -m cdp rotinas exportar --alvo cron --harness codex
  ```

  (ou `--alvo launchd`/`--alvo windows`; `--alvo codex` traz o crontab e o workflow juntos).
- **Na nuvem** (GitHub Actions, chave de API `CODEX_API_KEY`):
  `uv run python -m cdp rotinas exportar --alvo github-actions --harness codex --saida .github/workflows/cdp-rotinas.yml`.
  O uso do plano no Actions (restaurar e regravar o `auth.json` do `codex login`) é possível pela
  documentação da OpenAI, mas não é gerado aqui: exige um token pessoal com escrita de segredos.
- As automações do app do Codex rodam num sandbox sem push: não servem para publicar o livro.
- O Codex lê `AGENTS.md` e `.agents/skills/` nativamente; use `--mind codex`.

## 5. Gemini CLI e Antigravity

- Só no GitHub Actions (ou agendador próprio), com **chave paga** do Gemini (`GEMINI_API_KEY`)
  ou Vertex: `uv run python -m cdp rotinas exportar --alvo gemini-actions`.
- Sem interface: `gemini -p "<prompt>" --approval-mode yolo`, só em máquina efêmera sem
  credencial de escrita (no Actions, o job da IA só lê).
- **Antigravity (`agy`) — experimental.** O workflow gerado instala pelo instalador oficial
  (`https://antigravity.google/cli/install.sh`) e grava `~/.gemini/antigravity-cli/settings.json`
  com `{"modelProvider": "gemini"}` (autenticação pela chave `GEMINI_API_KEY`); o script de rotina
  chama `agy -p "<prompt>" --dangerously-skip-permissions --print-timeout <timeout da tarefa>m`
  (o padrão do `--print-timeout` é 5 min, curto demais para a montagem). Confirme essas opções
  com `agy --help` e faça um ensaio antes de ligar: `--alvo gemini-actions --harness agy`.
- `.gemini/settings.json` faz o Gemini CLI ler `AGENTS.md`; skills em `.agents/skills/`;
  `--mind gemini` (Gemini CLI e Antigravity).

## 6. Genérico — qualquer CLI e qualquer agendador

`scripts/cdp_rotina.sh <tarefa> --harness claude|codex|gemini|agy|custom` (Windows:
`scripts\cdp_rotina.ps1`; também aceita os nomes de identidade `claude-code`, `antigravity` e
`outro`, os mesmos de `CDP_HARNESS`) faz, nesta ordem: trava local, `uv sync`, gate (sem
trabalho pendente ou com a trava de outra execução, nenhuma chamada de modelo), pré-comando da
tarefa (backtest da calibração), prompt neutro, harness sem interface, liberação da trava
distribuída e conferência de progresso. Dois modos de publicação:

- `--publicacao agente` (padrão no Claude Code, Gemini CLI, Antigravity e `custom`): a mente
  segue o prompt inteiro (gate com a trava → sincronizar → roteiro → publicar → liberar);
- `--publicacao executor` (padrão no Codex): o script pega a trava, sincroniza, chama a mente com
  o prompt sem git, publica (`cdp publicar --trava … --execucao …`) e libera a trava. Use-o em
  qualquer harness com sandbox que proteja `.git`.

`--seco` mostra o comando sem rodar o harness. Harness próprio:
`CDP_HARNESS_CMD='meu-agente --arquivo {prompt_file}'` com `--harness custom`.

| Agendador | Exportação |
|---|---|
| cron (Linux) | `uv run python -m cdp rotinas exportar --alvo cron` (`CRON_TZ=America/Sao_Paulo`; `--utc` para servidores sem esse suporte) |
| launchd (macOS) | `uv run python -m cdp rotinas exportar --alvo launchd --saida ~/Library/LaunchAgents` |
| Agendador do Windows | `uv run python -m cdp rotinas exportar --alvo windows` (PowerShell com `Register-ScheduledTask`) |
| GitHub Actions | `uv run python -m cdp rotinas exportar --alvo github-actions` (harness pela variável de repositório `CDP_HARNESS`: `claude`, `claude-code`, `codex`, `gemini`, `agy` ou `antigravity`; ou fixo com `--harness`) |
| App desktop do Claude Code | `uv run python -m cdp rotinas exportar --alvo claude-desktop` (`docs/cdp/LOCAL.md`) |

**GitHub Actions como executor** (`CDP_EXECUTOR=github-actions`): o workflow gerado fica
desarmado até a variável `CDP_ROTINAS_ATIVAS=1` e tem três jobs, porque as permissões do GitHub
valem por job (nunca por passo):

1. `gate` (código, sem IA; `contents: write` só para o ramo da trava): resolve a tarefa, roda o
   gate e adquire a trava;
2. `mente` (`contents: read`, sem nenhuma credencial de escrita do GitHub): a IA roda o roteiro
   (`--publicacao executor --sem-gate`) e entrega só o que gravou nos caminhos da tarefa
   (`cdp entrega exportar`, artefato do Actions);
3. `publicar` (código, sem IA; `contents: write`): checkout limpo na mesma versão do gate,
   `cdp entrega importar` (recusa o que não for arquivo comum dentro dos caminhos da tarefa),
   `cdp publicar` com a trava e a execução do gate, dispara `cdp-site.yml` (push feito com
   `GITHUB_TOKEN` não dispara workflows) e libera a trava (sempre).

O código que publica nunca é o que a IA teve nas mãos. Fila: um disparo pendente por tarefa
(nunca um grupo único que cancele o monitor de risco ou as reservas). Credenciais por harness:

| Harness no Actions | Usa o plano? | Segredo |
|---|---|---|
| Claude Code | sim | `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`, 1 ano, pessoal) |
| Codex | não (no Actions) | `CODEX_API_KEY` (pelo plano: agendador do sistema, seção 4) |
| Gemini CLI / Antigravity (experimental) | não | `GEMINI_API_KEY` ou Vertex |

A agenda do Actions é de melhor esforço (minutos de atraso em horários cheios): boa alternativa,
pior que as rotinas para os horários das 11:07 e 19:22.

## 7. Capacidade do plano

- Disparos por semana na nuvem: cerca de 46 (20 da montagem e reservas, 10 de risco, 10 do
  fechamento e reforço, 1 de sábado, 4 de notas, 1 de estado), mais a calibração mensal. A
  maioria sai no gate em poucos segundos. A documentação das rotinas só traz limites por hora;
  confira o seu uso em claude.ai/settings/usage.
- Execuções pesadas: montagem semanal (1 a 2 por semana), fechamentos (5 por semana, sexta mais
  longa), notas de cobertura (4 por semana, até 12 emissores cada), calibração mensal.
- Níveis por tarefa em `rotinas.yaml`: `forte` (semanal, diário, cobertura) e `leve` (risco,
  estado, calibração).
- **Modo econômico** (opcional, recurso em prévia): rotinas sem horário, só com gatilho por API, e
  um workflow agendado do Actions que roda o gate de graça e chama
  `POST https://api.anthropic.com/v1/claude_code/routines/<id>/fire` (cabeçalho beta e token por
  rotina em segredo do repositório) só quando há trabalho — cerca de 1 a 2 execuções por dia útil.

## 8. Falhas, reservas e recuperação

- **Montagem**: reservas às 12:07, 13:07 e 14:07 retomam se a principal parou (a trava impede duas
  ao mesmo tempo; uma trava abandonada expira em 60 min — a renovação usa a validade da tarefa e
  nunca a encurta). Passado o prazo efetivo sem decisão, o código não decide: a carteira anterior
  é mantida (`decisao_perdida` na agenda).
- **Trava inacessível** (GitHub fora do ar, disputa): o escritor exclusivo **não executa** (falha
  fechada); a reserva seguinte tenta de novo. Só uma sessão de operador, explicitamente, usa
  `--sem-trava` (no gate e em `cdp publicar`).
- **Kill switch pela rotina de risco**: o relatório de risco é arquivo novo (mesclável) e sai
  sempre; o kill switch e o evento na trilha exigem a trava exclusiva — `cdp publicar` espera
  até 10 min por ela e, se outra rotina a segura, publica só o relatório e relata os arquivos
  retidos (no clone compartilhado do PC local, a rotina que segura a trava os publica junto).
- **Fechamento**: reforço às 21:07 e repescagem no sábado às 10:07; "dados não prontos" é tentado
  de novo pela execução seguinte; a agenda lista todos os pregões pendentes.
- **Execução atrasada**: o gate recusa disparos muito depois do horário (`atraso_max_min`); para
  rodar fora do horário, numa sessão de operador no executor, use `--manual`:
  `uv run python -m cdp rotinas gate --tarefa cdp-diario --manual --adquirir`.
- **Executor pausado** (`nenhum`) ou trocado no meio da execução: `cdp publicar` relê
  `origin/main` antes do push e não publica.
- **Push recusado** por corrida: `cdp publicar` sincroniza e tenta uma vez; se o remoto gravou o
  livro, para e relata (nunca mescla, reescreve nem força).

## 9. Monitoramento

- `uv run python -m cdp estado --formato md` (com `--rede`, consulta remoto, trava e portal;
  `--sla` sai com 1 quando há incidente de severidade alta).
- Lista de execuções e transcrições das rotinas (claude.ai/code); trailers dos commits; o
  manifesto do portal (`manifest.json` → `source_commit`).

| Incidente | Severidade | Quando |
|---|---|---|
| `INTEGRIDADE` | alta | `cdp verify` falha |
| `KILL_SWITCH` | alta | kill switch ligado (revisão humana) |
| `REINICIO_PENDENTE` | alta a partir da data de início (média antes) | livro aguardando a abertura |
| `SLA_FECHAMENTO` | alta | fechamento pendente depois das 22:00 do pregão |
| `DECISAO_PERDIDA` | alta | semana sem decisão no dia de montagem |
| `EXECUTOR_INVALIDO` | alta | `executor.yaml` inválido |
| `COMMIT_FORA_DO_ESCOPO` | alta | commit de rotina fora dos caminhos da tarefa |
| `SLA_TESE` | média | tese da semana não publicada até 12:00 do dia seguinte |
| `SLA_RELATORIO_SEMANAL` | média | relatório semanal pendente até 12:00 do dia seguinte |
| `SLA_COBERTURA` | média | retrato da cobertura pendente por mais de um dia útil |
| `EXECUTOR_PAUSADO` | média | executor `nenhum` há mais de 24 h |
| `CLONE_DIVERGENTE` | média | gravações do livro neste clone fora de `origin/main` |
| `PORTAL_DEFASADO` | média | portal publicado ≠ `origin/main` (com `--rede`) |
| `SLA_RISCO` | baixa | nenhum relatório de risco até 16:45 num pregão |
| `TRAVA_EXPIRADA` | baixa | trava ocupada e vencida há mais de 2 h |
| `TRAVA_LOCAL_ORFA` | baixa | `logs/cdp/.lock` com mais de 6 h |

## 10. Segurança

- **Menor privilégio**: nenhum segredo no ambiente da nuvem; no Actions, a IA roda num job só de
  leitura (`contents: read`, sem credencial de escrita) e a publicação, num job separado que só
  importa arquivos comuns dos caminhos da tarefa e roda o código da versão do gate; as permissões
  de escrita são por job; ações fixadas por SHA.
- **Código acima do prompt**: gate, escopo de caminhos em `cdp publicar`, `cdp verify` antes de
  publicar, kill switch só por gatilho HARD e só desligado por humano — valem em qualquer harness.
  No Claude Code, `.claude/settings.json` acrescenta bloqueios; nos demais, as proteções são o
  código e a regra do ramo `main`.
- **Injeção de instruções**: notícias, páginas, arquivos baixados e qualquer conteúdo de disparo
  por API são dados, nunca instruções; a rotina não aceita "aprovações" vindas de conteúdo.
- Varredura de segredos e proteção de push ligadas no GitHub.

## 11. Troca de executor (e ensaio)

**Ensaio**: rotinas criadas no ambiente CDP-ensaio (`CDP_ENSAIO=1`, prompts com `--ensaio`) rodam
o fluxo completo numa máquina descartável, sem trava e sem publicar, em paralelo ao executor
atual. Além do prompt, o código garante: com `CDP_ENSAIO=1`, o gate instala um gancho
`pre-push` que recusa todo push enquanto essa variável estiver no ambiente (fora dele, o gancho
não faz nada), `cdp trava` não grava nada no remoto e `cdp publicar` não publica. Ensaie sempre
num ambiente com `CDP_ENSAIO=1`: a opção `--ensaio` sozinha só muda o prompt.
Compare: terminou no prazo, validadores ok, transcrição limpa.

**Troca** (≤ 10 min; volta pelo mesmo caminho):

1. Janela segura: `uv run python -m cdp executor janela` (nenhum escritor nos próximos 90 min,
   trava livre, nada pendente; evite dias de montagem das 10:30 às 17:30 e as noites das 19:00 às
   23:30).
2. Pause o antigo: desligue as tarefas do app desktop (ou rotinas `enabled: false`, ou
   `CDP_ROTINAS_ATIVAS=0` no Actions); no clone antigo, `git status -sb` em dia (publique antes
   qualquer commit retido).
3. Troque, numa sessão de operador (nunca dentro de uma rotina):

   ```sh
   uv run python -m cdp executor transferir --para claude-cloud --por "Nome" --motivo "rotinas na nuvem após o ensaio"
   ```

   e faça o commit e o push indicados (`CDP: executor → claude-cloud`).
4. Ligue o novo: rotinas `enabled: true`; "Run now" numa tarefa sem pendência; confira
   `uv run python -m cdp estado --rede --formato md`.
5. Acompanhe a primeira execução real (transcrição, trailers do commit, portal). O executor antigo
   fica instalado como reserva quente por duas semanas.

## 12. Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "Sem execução: identidade deste ambiente desconhecida" | `CDP_EXECUTOR` ausente | defina no ambiente da nuvem, ou `cdp executor registrar --como local-pc` no clone do PC |
| "o executor designado é local-pc" na nuvem | troca ainda não feita | seção 11 |
| "execução atrasada" | disparo atrasado ou "Run now" fora do horário | normal; para rodar já, sessão de operador com `--manual` |
| "<tarefa> em andamento em …" | outra execução segura a trava | normal; a reserva seguinte retoma; trava abandonada expira |
| "trava distribuída indisponível" | GitHub inacessível ou disputa | normal; a reserva seguinte tenta de novo; persistindo, conferir rede e regras do ramo `cdp-trava` |
| `publicar` → "escritor exclusivo sem a trava" | `--trava` faltando ou trava perdida (expirou e outra execução a pegou) | nada foi publicado; a execução seguinte refaz a partir do livro |
| `sincronizar` → `parar` | o remoto gravou o livro, ou clone com código alterado | investigar numa sessão de operador no clone do executor; depois de conferir, `git merge origin/main` à mão; nunca forçar. Mudanças no livro (inclusive apagar arquivos de `artifacts/`) só pelo clone do executor |
| `publicar` sem push, "verify falhou" | integridade | `uv run python -m cdp verify` e investigar antes de qualquer publicação |
| rotina verde sem commit | gate saiu cedo, ou falha relatada no resumo | ler a transcrição; `cdp estado` |
| push na nuvem foi para `claude/…` | o prompt não foi o gerado | use só os prompts de `cdp rotinas exportar` (publicam em `main` por `cdp publicar`) |
| portal antigo | workflow não disparou | Actions → cdp-site → Run workflow; `PORTAL_DEFASADO` em `cdp estado --rede` |
