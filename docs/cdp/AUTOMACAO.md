# Automação do CDP — rotinas dentro do app de IA (Claude Code, Codex, Gemini)

As rotinas do CDP rodam **dentro do app de IA** de quem opera, com a capacidade do próprio plano:
o app agenda, abre o repositório, lê `AGENTS.md` e segue o roteiro da tarefa. O app escolhido
pelo titular é o **Codex** (tarefas agendadas do app desktop num clone dedicado, seção 5); este
guia ensina, passo a passo, a fazer o mesmo no **Claude Code** (rotinas na nuvem ou app desktop)
e no **Gemini** (Antigravity e Gemini CLI). O projeto se
comporta igual em qualquer um deles, porque o que decide é o código: o gate (agir agora?), a
trava (uma execução por vez), a sincronização e a publicação são comandos da CLI, e o prompt de
cada tarefa sai pronto de `cdp rotinas`.

**GitHub Actions não roda a IA das rotinas**: só faz a integração contínua
(`cdp-ci.yml`) e publica o portal (`cdp-site.yml`). Quem quiser, mesmo assim, rodar a IA no
Actions encontra o desenho no apêndice A (opcional).

Manual do agente: `AGENTS.md`. Agenda (fonte única): `configs/cdp/rotinas.yaml`. Roteiros:
`docs/cdp/playbooks/`. PC local com o app desktop do Claude Code: `docs/cdp/LOCAL.md`. Tabela
das rotinas: `docs/cdp/ROTINAS.md`. Portal público: `docs/cdp/SITE.md`.

## 1. Como uma rotina funciona (igual em qualquer app)

```text
 agendador DO APP (rotinas na nuvem do Claude Code | tarefas agendadas do Codex | Antigravity)
   └─ prompt neutro gerado por `cdp rotinas` (o mesmo texto em qualquer app)
        1. uv sync --frozen
        2. cdp rotinas gate --tarefa T --adquirir   ← código: executor? atrasada? há trabalho?
           │                                          trava distribuída (ramo cdp-trava):
           │                                          sem a trava, o escritor exclusivo não roda
           ├─ executar: false → "Sem execução: <motivo>" (custo mínimo de modelo)
           └─ executar: true (guarda trava.id e execucao)
        3. cdp sincronizar --executar                ← código: o remoto mudou o livro? parar
        4. roteiro docs/cdp/playbooks/<T>.md          ← a mente: pesquisa, juízos, textos (JSON)
        5. cdp publicar --tarefa T --mensagem "CDP: …" --execucao E --trava ID
                                                      ← código: verify, trava confirmada, só o
                                                        que esta execução gravou, commit com
                                                        trailers, push em main (nunca force)
        6. cdp trava liberar --id ID
   push em main ──► GitHub Actions cdp-site.yml (sem IA) ──► GitHub Pages (portal público)
```

- **Quem grava**: só o executor designado em `configs/cdp/executor.yaml` (hoje, `local-pc`).
  Cada ambiente diz quem é por `CDP_EXECUTOR` (nuvem) ou por `.cdp/local.yaml` (clone num
  computador, gravado por `uv run python -m cdp executor registrar --como local-pc`). Um
  ambiente que não é o executor sai no gate, sem gravar nada. Ligue as rotinas em **um** app por
  vez.
- **Quem publica o git**: a própria mente, pelos comandos do código (`cdp rotinas gate`,
  `cdp sincronizar`, `cdp publicar`, `cdp trava`) — modo "agente", o padrão nos apps. Quando o
  app protege `.git` no sandbox (o `codex exec` em `workspace-write`, por exemplo), o script
  `scripts/cdp_rotina.sh` faz o git por fora — modo "executor" — e o prompt diz à mente que
  gate, trava e publicação não são dela.
- **Quando**: `uv run python -m cdp rotinas listar` (tabela em `AGENTS.md`, seção 4). Horários
  de Brasília (sem horário de verão); em UTC, some 3 h — 21:07 de Brasília vira terça a sábado
  em UTC.
- **O que mudou**: cada commit de rotina leva os trailers `CDP-Tarefa`, `CDP-Executor`,
  `CDP-Harness` e `CDP-Execucao`, e `CDP-Sessao` quando o app expõe a sessão (URL da rotina na
  nuvem ou do GitHub Actions; nos apps locais, o identificador da conversa quando o app o exporta
  — `CODEX_THREAD_ID`, por exemplo — ou `CDP_SESSAO` definido pelo script de rotina; sem isso, o
  trailer é omitido); `uv run python -m cdp estado` lê esse histórico.

## 2. Qual opção escolher (outubro de 2026)

| App e recurso | Onde roda | Agenda | Usa o plano? | Publica (push em `main`)? | Veredito |
|---|---|---|---|---|---|
| **Codex — tarefas agendadas do app** (desktop) | o seu computador (app aberto) | diária, semanal ou RRULE | **sim** | sim, com acesso total num clone dedicado | **a escolha do titular** (seção 5) |
| **Claude Code — rotinas na nuvem** (claude.ai/code) | nuvem da Anthropic, máquina nova a cada execução | cron em UTC (intervalo mínimo de 1 h) | **sim** | sim (com a sua identidade no GitHub) | melhor opção no Claude Code (seção 3) |
| Claude Code — tarefas agendadas do app desktop | o seu computador (app aberto) | horário local | sim | sim | alternativa local no Claude Code (seção 4) |
| Codex — tarefas agendadas da web | nuvem | sim | sim | não: não acessa o repositório | não serve |
| Codex Cloud (tarefas) | nuvem | **sem agenda** | sim | por pull request | só sob demanda (desenvolvimento) |
| Codex CLI (`codex exec`) + agendador do sistema | o seu computador | cron, launchd ou Windows | sim (`codex login`) | sim (o script publica fora do sandbox) | alternativa no Codex (seção 5.3) |
| **Antigravity — tarefas agendadas do app** | o seu computador (app aberto) | cron | sim (plano Google) | sim, com permissões do projeto | experimental; modelo fixo (seção 6.1) |
| **Antigravity CLI (`agy`) + agendador do sistema** | o seu computador | cron, launchd ou Windows | sim (login Google, uma vez) | sim | **melhor opção no Gemini** (seção 6.2; experimental) |
| Gemini CLI + agendador do sistema | o seu computador | cron, launchd ou Windows | **não**: chave paga, Vertex ou Code Assist Standard/Enterprise | sim | alternativa paga (seção 6.3) |
| Jules — tarefas agendadas | nuvem (Google) | diária ou semanal, sem horário exato | sim (Google AI Pro/Ultra) | por branch e pull request | não serve de executor (seção 6.4) |
| Outro app com modo sem interface | o seu computador | agendador do sistema | depende | sim | `scripts/cdp_rotina.sh --harness custom` (seção 7) |
| GitHub Actions | — | — | — | — | só CI e portal (seção 8); IA só no apêndice A |

O conhecimento não depende do app: `AGENTS.md` (canônico), roteiros neutros,
`configs/cdp/rotinas.yaml` e skills abertas (Agent Skills) geradas em `.agents/skills/`
(espelho em `.claude/skills/`). `CLAUDE.md`, `GEMINI.md` e `.gemini/settings.json` só apontam
para eles.

## 3. Claude Code — rotinas na nuvem

**Passo 1 — pré-requisitos.** Plano com rotinas (Pro, Max, Team ou Enterprise; recurso em
prévia). App GitHub do Claude conectado ao repositório: sem a conexão, as execuções são
**puladas** e, depois de 72 h, a rotina é desligada — confira antes de cada dia de montagem.
**Regra do ramo `main` no GitHub — crie antes de ligar qualquer rotina** (Settings → Rules →
Rulesets → New branch ruleset, alvo `main`): bloquear force push e exclusão; **não** exigir pull
request (as rotinas publicam direto em `main` por `cdp publicar`); não incluir o ramo
`cdp-trava` (a trava precisa ser regravada). Confira com
`gh api repos/<dono>/<repositório>/rulesets`: lista vazia quer dizer `main` sem proteção. O
proxy do GitHub da nuvem aceita o push do ramo `cdp-trava` e de `HEAD:main`, limitado só pelas
regras do repositório — sem a regra, só pelo código.

**Passo 2 — ambientes** (claude.ai/code → Environments → New environment): **CDP** e
**CDP-ensaio**, só para as rotinas. Sessões interativas usam o ambiente **Default** (sem
`CDP_EXECUTOR`): uma sessão aberta no "CDP" passaria por executora (`cdp estado` avisa).

- Rede: **Total** (a pesquisa usa dezenas de domínios públicos). Alternativa: "Personalizada +
  padrões" com a lista `rede` de `configs/cdp/rotinas.yaml`.
- Variáveis: `CDP_EXECUTOR=claude-cloud`, `CDP_HARNESS=claude-code`, `TZ=America/Sao_Paulo`,
  `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `BASH_DEFAULT_TIMEOUT_MS=600000`,
  `BASH_MAX_TIMEOUT_MS=1800000`; no CDP-ensaio, também `CDP_ENSAIO=1` (nada é publicado).
- Script de preparação: `uv python install 3.12` (o `uv sync --frozen` roda no passo 1 de cada
  rotina). **Nenhum segredo** no ambiente: o push usa o proxy do GitHub da própria sessão.

**Passo 3 — gerar os prompts.** Os corpos saem prontos, um por tarefa, desligados:

```sh
uv run python -m cdp rotinas exportar --alvo claude-routines --formato md
uv run python -m cdp rotinas exportar --alvo claude-routines --ambiente env_ID_DO_CDP --saida rotinas.json
```

O primeiro dá o texto legível (nome, agenda e prompt de cada rotina, para colar na interface);
o segundo, o JSON da API de rotinas (`name`, `cron_expression` em UTC, `enabled: false`,
`job_config.ccr` com o repositório, as ferramentas e o prompt). Níveis de modelo:
`--modelo forte=<id> --modelo leve=<id>` (os identificadores nunca ficam no repositório).
Ensaio: `--ensaio` gera prompts que nunca publicam.

**Passo 4 — criar as rotinas.** Uma por linha da agenda, **desligadas** até a troca de executor
(seção 13):

1. claude.ai/code → Routines → New routine → **Cloud**.
2. Nome (`CDP · cdp-diario (19:22 BRT)` etc.), repositório `arielassayag/MarketSummary` (um só
   por rotina), ambiente **CDP**, modelo do nível da tarefa (`forte`: semanal, diário,
   cobertura; `leve`: risco, estado, calibração), nenhum conector.
3. Prompt: cole o bloco da tarefa gerado no passo 3.
4. Agenda: a interface converte do horário local e só oferece agendas prontas (de hora em hora,
   diária, dias úteis, semanal). `cdp-cobertura` (segunda a quinta) e `cdp-calibracao` (dia 1)
   precisam do `cron_expression` exato: crie pela API (o corpo exportado) ou escolha a agenda
   mais próxima e ajuste com `/schedule update` no Claude Code.

Também dá para criar tudo pelo próprio Claude Code (`/schedule`, com o corpo exportado) ou pela
API; o `uuid` do evento já sai novo em cada exportação.

**Passo 5 — agenda em UTC** (a API e o `/schedule` usam UTC):

| Rotina | Brasília | cron (UTC) |
|---|---|---|
| `cdp-status` | segundas, 08:30 | `30 11 * * 1` |
| `cdp-semanal` / `-b` / `-c` / `-d` | dias úteis, 11:07 / 12:07 / 13:07 / 14:07 | `7 14 * * 1-5` / `7 15 * * 1-5` / `7 16 * * 1-5` / `7 17 * * 1-5` |
| `cdp-risco-1330` / `cdp-risco-1603` | dias úteis, 13:30 / 16:03 | `30 16 * * 1-5` / `3 19 * * 1-5` |
| `cdp-diario` | dias úteis, 19:22 | `22 22 * * 1-5` |
| `cdp-diario-reforco` | dias úteis, 21:07 | `7 0 * * 2-6` (terça a sábado em UTC) |
| `cdp-diario-sabado` | sábados, 10:07 | `7 13 * * 6` |
| `cdp-cobertura` | segunda a quinta, 22:37 | `37 1 * * 2-5` (terça a sexta em UTC) |
| `cdp-calibracao` | dia 1 de cada mês, 09:15 | `15 12 1 * *` |

**Passo 6 — validar.** "Run now" numa tarefa sem trabalho pendente: o gate sai cedo e prova
clone, `uv` e rede. Leia a transcrição: verde na lista de execuções não quer dizer sucesso.
Faça o ensaio completo no ambiente CDP-ensaio (seção 13) antes de ligar no CDP.

**Passo 7 — monitorar.** `uv run python -m cdp estado --rede --formato md` (remoto, trava,
portal e incidentes; seção 9), a lista de execuções e as transcrições em claude.ai/code, os
trailers dos commits e o manifesto do portal (`manifest.json` → `source_commit`).

## 4. Claude Code — tarefas agendadas do app desktop (reserva local)

Roda no seu computador, com o app aberto e a máquina acordada (uma repescagem por tarefa ao
acordar). É o executor atual até a troca para a nuvem e, depois, a reserva quente. Guia
completo: `docs/cdp/LOCAL.md`.

1. Clone dedicado às rotinas (nunca o da sua sessão de desenvolvimento) e
   `uv sync --extra dev --extra ai`; o script `scripts/cdp_setup_local.sh` (Windows:
   `scripts\cdp_setup_local.ps1`) confere tudo e testa o push.
2. Identidade do clone: `uv run python -m cdp executor registrar --como local-pc --harness claude-code`.
3. Tabela das tarefas: `uv run python -m cdp rotinas exportar --alvo claude-desktop`.
4. No app desktop: Routines → New routine → **Local** (tarefa agendada): pasta = raiz do clone,
   worktree desligado, modo de permissão indicado na tabela, instrução = o comando da skill com
   o id da tarefa.
5. Nunca deixe as tarefas do app desktop e as rotinas da nuvem ligadas ao mesmo tempo como
   escritoras: só o executor designado grava, os outros saem no gate.

## 5. Codex

### 5.1 Tarefas agendadas do app do Codex (melhor opção no Codex)

As tarefas agendadas do app desktop do Codex rodam **no seu computador** (app aberto e máquina
acordada), na pasta do projeto ou num worktree, e **herdam o sandbox padrão** da instalação.
Para o roteiro poder sincronizar, fazer commit e push (gate com trava, `cdp sincronizar`,
`cdp publicar`), o Codex precisa de rede e de escrita em `.git` — e o modo `workspace-write`
deixa `.git` sempre só de leitura e a rede desligada por padrão. Por isso o arranjo é: **acesso
total, numa conta de usuário do sistema dedicada às rotinas, com um clone dedicado**. As
proteções do CDP continuam valendo pelo código (gate, escopo de caminhos, `cdp verify` antes de
publicar, nunca force) e pela regra do ramo `main` — que precisa estar criada antes (seção 3,
passo 1).

Passo a passo:

1. **Conta e clone dedicados.** Numa conta de usuário do sistema só para as rotinas:
   `git clone https://github.com/arielassayag/MarketSummary.git ~/cdp-rotinas`, depois
   `uv sync --extra dev --extra ai`. Configure uma credencial do Git que possa fazer push em
   `main` e no ramo `cdp-trava` (por exemplo, `gh auth login`) e teste com
   `git push --dry-run`. Confira que a regra do ramo `main` existe (seção 3, passo 1): com
   acesso total e sem ela, nada fora do código impede um push forçado.
2. **Identidade do clone:** `uv run python -m cdp executor registrar --como local-pc --harness codex`
   (grava `.cdp/local.yaml`, ignorado pelo git).
3. **Configuração do Codex dessa conta** (`~/.codex/config.toml`; nunca no repositório):

   ```toml
   sandbox_mode = "danger-full-access"   # "Acesso total": rede e escrita em .git
   approval_policy = "never"              # sem perguntas numa execução agendada

   [shell_environment_policy]
   inherit = "all"
   set = { CDP_HARNESS = "codex", TZ = "America/Sao_Paulo", PYTHONUTF8 = "1" }
   ```

   Entre com a conta do plano (`codex login` ou pelo app). O Codex lê `AGENTS.md` (até 32 KiB)
   e as skills de `.agents/skills/`.
4. **Projeto no app:** abra a pasta do clone como projeto e use a **pasta do projeto** (sem
   worktree isolado): a identidade, a trava e o livro precisam do clone único, e worktrees de
   tarefas frequentes se acumulam.
5. **Gerar as tarefas:** `uv run python -m cdp rotinas exportar --alvo codex --formato md` —
   um bloco por tarefa com nome, agenda (RRULE em horário de Brasília) e o prompt a colar. O
   prompt de uma tarefa avulsa sai de
   `uv run python -m cdp rotinas prompt --tarefa cdp-diario --harness codex --publicacao agente`.
6. **Criar uma tarefa agendada por linha da agenda** (nome, projeto, agenda, prompt, modelo do
   nível da tarefa). Agendas (o relógio do computador precisa estar no fuso
   America/Sao_Paulo):

   | Tarefa | Agenda (RRULE, Brasília) | Nível |
   |---|---|---|
   | `cdp-status` | `RRULE:FREQ=WEEKLY;BYDAY=MO;BYHOUR=8;BYMINUTE=30` | leve |
   | `cdp-semanal` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=11;BYMINUTE=7` | forte |
   | `cdp-semanal-b` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=12;BYMINUTE=7` | forte |
   | `cdp-semanal-c` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=13;BYMINUTE=7` | forte |
   | `cdp-semanal-d` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=14;BYMINUTE=7` | forte |
   | `cdp-risco-1330` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=13;BYMINUTE=30` | leve |
   | `cdp-risco-1603` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=16;BYMINUTE=3` | leve |
   | `cdp-diario` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=19;BYMINUTE=22` | forte |
   | `cdp-diario-reforco` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=21;BYMINUTE=7` | forte |
   | `cdp-diario-sabado` | `RRULE:FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=7` | forte |
   | `cdp-cobertura` | `RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH;BYHOUR=22;BYMINUTE=37` | forte |
   | `cdp-calibracao` | `RRULE:FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9;BYMINUTE=15` | leve |

7. **Validar:** execute agora uma tarefa sem pendência (resposta "Sem execução: …") e confira
   `uv run python -m cdp estado --formato md`. Para o ensaio completo, acrescente
   `CDP_ENSAIO = "1"` ao `set` acima enquanto durar o ensaio (nada é publicado; seção 13).

**Limites (honestos):** roda só com o computador ligado e o app aberto; o gate recusa
disparos muito atrasados (`atraso_max_min`), e as reservas cobrem falhas curtas. Acesso total
dispensa aprovações — por isso a conta dedicada. As tarefas agendadas da **web** não acessam o
repositório, e o **Codex Cloud** ainda não agenda tarefas: nenhum dos dois serve de executor.

### 5.2 Codex Cloud

Útil para desenvolvimento sob demanda (o Codex Cloud lê `AGENTS.md` e as skills do
repositório e entrega por pull request). Nunca grava o livro: sessões de desenvolvimento seguem
`AGENTS.md`, seção 6.

### 5.3 Alternativa: Codex CLI pelo agendador do sistema

Sem o app aberto: `codex login` uma vez na máquina e o agendador do sistema chamando o script de
rotina, que roda o `codex exec` em `workspace-write` com rede e faz gate, trava, sincronização e
publicação **fora** do sandbox (modo executor):

```sh
uv run python -m cdp rotinas exportar --alvo cron --harness codex
```

(ou `--alvo launchd` / `--alvo windows`; seção 7).

## 6. Gemini

Desde 18/06/2026, o Gemini CLI não atende mais os planos de consumo (Google AI Pro/Ultra,
Code Assist gratuito): exige chave paga do Gemini, Vertex AI ou Code Assist
Standard/Enterprise. O plano de consumo continua valendo no **Antigravity** (app e CLI). Por
isso, para quem usa o Gemini pelo plano, a melhor opção hoje é o Antigravity.

### 6.1 Tarefas agendadas do app Antigravity (experimental)

O Antigravity 2.0 agenda tarefas no próprio app (painel "Scheduled Tasks" ou `/schedule`), com
agenda cron, prompt e projeto, e as permissões precisam estar concedidas de antemão no projeto.
Passo a passo:

1. Conta e clone dedicados, credencial do Git com push em `main` e no ramo `cdp-trava`
   (como na seção 5.1, passo 1) e
   `uv run python -m cdp executor registrar --como local-pc --harness antigravity`.
2. No app, abra o clone como projeto e dê a ele a predefinição de segurança que permite rodar
   comandos no terminal e acessar a rede sem perguntar ("Full machine" ou equivalente).
3. Gere as tarefas: `uv run python -m cdp rotinas exportar --alvo gemini --formato md` (nome,
   agenda cron em horário de Brasília e o prompt de cada tarefa).
4. Crie uma tarefa agendada por linha (agenda, prompt, projeto) e valide com uma tarefa sem
   pendência.

**Limites:** o modelo das tarefas agendadas do app é fixo (um modelo Flash) e não pode ser
escolhido — use-o só para tarefas leves (`cdp-risco-*`, `cdp-status`) ou prefira o `agy` pelo
agendador do sistema (6.2) para as tarefas fortes. A documentação pública não diz se as
tarefas rodam sem o app aberto: trate como local (computador ligado e app aberto) e confirme
num ensaio.

### 6.2 Antigravity CLI (`agy`) pelo agendador do sistema (melhor opção no Gemini)

1. Instale o `agy` pelo instalador oficial e entre **uma vez**, de forma interativa, com a conta
   Google do plano (a sessão fica guardada no chaveiro do sistema).
2. Conta e clone dedicados e identidade, como em 6.1.
3. Agendador: `uv run python -m cdp rotinas exportar --alvo cron --harness agy` (ou `launchd` /
   `windows`). O script chama `agy -p "<prompt>" --dangerously-skip-permissions --print-timeout <minutos>m`
   (o padrão do `--print-timeout` é curto demais para a montagem); confira as opções com
   `agy --help` e faça um ensaio antes de ligar.

### 6.3 Gemini CLI pelo agendador do sistema (chave paga)

`.gemini/settings.json` faz o Gemini CLI ler `AGENTS.md` e `GEMINI.md`; skills em
`.agents/skills/`. Com `GEMINI_API_KEY` (ou Vertex) no ambiente da conta dedicada:

```sh
uv run python -m cdp rotinas exportar --alvo cron --harness gemini
```

O script chama `gemini -p "<prompt>" --approval-mode yolo` — só nesse clone dedicado. Use
`--mind gemini` (Gemini CLI e Antigravity).

### 6.4 Jules

As tarefas agendadas do Jules rodam na nuvem do Google, com cadência diária ou semanal **sem
horário exato** documentado, e entregam por branch e pull request (uma tarefa agendada não
pode ser editada: apaga-se e cria-se outra). Não servem aos escritores do livro, que dependem de horário e de push em `main`. Use o
Jules para desenvolvimento (ele lê `AGENTS.md`).

## 7. Qualquer outro app — o script de rotina

`scripts/cdp_rotina.sh <tarefa> --harness claude|codex|gemini|agy|custom` (Windows:
`scripts\cdp_rotina.ps1`; também aceita `claude-code`, `antigravity` e `outro`, os mesmos nomes
de `CDP_HARNESS`) faz, nesta ordem: trava local, `uv sync`, gate (sem trabalho pendente ou com a
trava de outra execução, nenhuma chamada de modelo), pré-comando da tarefa (backtest da
calibração), prompt neutro, app sem interface, liberação da trava distribuída e conferência de
progresso. Dois modos de publicação:

- `--publicacao agente` (padrão no Claude Code, Gemini CLI, Antigravity e `custom`): a mente
  segue o prompt inteiro (gate com a trava → sincronizar → roteiro → publicar → liberar);
- `--publicacao executor` (padrão no `codex exec`): o script pega a trava, sincroniza, chama a
  mente com o prompt sem git, publica (`cdp publicar --trava … --execucao …`) e libera a trava.
  Use-o com qualquer app cujo sandbox proteja `.git`.

`--seco` mostra o comando sem rodar o app. App próprio:
`CDP_HARNESS_CMD='meu-agente --arquivo {prompt_file}'` com `--harness custom`.

| Agendador do sistema | Exportação |
|---|---|
| cron (Linux) | `uv run python -m cdp rotinas exportar --alvo cron` (`CRON_TZ=America/Sao_Paulo`; `--utc` para servidores sem esse suporte) |
| launchd (macOS) | `uv run python -m cdp rotinas exportar --alvo launchd --saida ~/Library/LaunchAgents` |
| Agendador do Windows | `uv run python -m cdp rotinas exportar --alvo windows` (PowerShell com `Register-ScheduledTask`) |

## 8. GitHub Actions: só integração contínua e portal

- `.github/workflows/cdp-ci.yml`: lint, testes, integridade do livro, agenda das rotinas, skills
  em dia e o portal da demonstração (DADOS SIMULADOS) como artefato de revisão. Sem segredos,
  só leitura.
- `.github/workflows/cdp-site.yml`: a cada push em `main` (e numa rede de segurança agendada),
  monta o portal a partir do repositório com `cdp site construir`, confere e publica no GitHub
  Pages. Não usa IA e não grava no repositório (`docs/cdp/SITE.md`).

Nenhum workflow roda a mente nas rotinas. O workflow com IA gerado por
`--alvo github-actions` existe só como alternativa opcional, desarmada (apêndice A).

## 9. Monitoramento

- `uv run python -m cdp estado --formato md` (com `--rede`, consulta remoto, trava e portal;
  `--sla` sai com 1 quando há incidente de severidade alta).
- A lista de execuções e as transcrições do app (claude.ai/code, aba de tarefas agendadas do
  Codex ou do Antigravity); trailers dos commits; o manifesto do portal (`manifest.json` →
  `source_commit`).

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

## 10. Falhas, reservas e recuperação

- **Montagem**: reservas às 12:07, 13:07 e 14:07 retomam se a principal parou (a trava impede
  duas ao mesmo tempo; uma trava abandonada sem renovação expira em 50 min, antes da reserva
  seguinte — `cdp rotinas verificar` recusa validade que alcance a próxima reserva —, e a
  renovação usa a validade da tarefa e nunca a encurta). Passado o prazo efetivo sem decisão, o
  código não decide: a carteira anterior é mantida — na carteira inaugural, o fundo segue sem
  carteira (`decisao_perdida` na agenda; `weekly decide` devolve `status: "prazo_vencido"`).
- **Prepare interrompido** (rede, fonte, modelo): o briefing é montado numa área temporária e
  promovido de uma vez só no fim, então nada parcial fica para trás e a reserva seguinte refaz
  o `weekly prepare`. Cotação intradiária vazia é falha de coleta (a análise usa o fechamento
  anterior, sem barra provisória, e a falha aparece em `falhas_coleta`).
- **Trava inacessível** (GitHub fora do ar, disputa): o escritor exclusivo **não executa**
  (falha fechada); a reserva seguinte tenta de novo. Só uma sessão de operador,
  explicitamente, usa `--sem-trava` (no gate e em `cdp publicar`).
- **Kill switch pela rotina de risco**: o relatório de risco é arquivo novo (mesclável) e sai
  sempre, junto com o pedido de kill switch (`reports/risk/<data>/kill_switch_<HHMM>.yaml`,
  gravado por `cdp kill-switch on` antes de tocar no livro). O kill switch e o evento na trilha
  exigem a trava exclusiva — `cdp publicar` espera até 10 min por ela e, se outra rotina a
  segura, publica só o relatório e o pedido e relata os arquivos retidos. A execução exclusiva
  seguinte (montagem ou fechamento) aplica o pedido antes de gravar qualquer coisa
  (`cdp kill-switch aplicar-pedidos` faz o mesmo numa sessão de operador no executor; a agenda
  lista os pendentes em `kill_switch_pedidos`). Não é preciso intervir à mão.
- **Fechamento**: reforço às 21:07 e repescagem no sábado às 10:07; "dados não prontos" é
  tentado de novo pela execução seguinte; a agenda lista todos os pregões pendentes.
- **Execução atrasada**: o gate recusa disparos muito depois do horário (`atraso_max_min`);
  para rodar fora do horário, numa sessão de operador no executor, use `--manual`:
  `uv run python -m cdp rotinas gate --tarefa cdp-diario --manual --adquirir`.
- **Executor pausado** (`nenhum`) ou trocado no meio da execução: `cdp publicar` relê
  `origin/main` antes do push e não publica.
- **Push recusado** por corrida: `cdp publicar` sincroniza e tenta uma vez; se o remoto gravou o
  livro, para e relata (nunca mescla à força, reescreve nem força).

## 11. Capacidade do plano

- Disparos por semana: cerca de 46 (20 da montagem e reservas, 10 de risco, 10 do fechamento e
  reforço, 1 de sábado, 4 de notas, 1 de estado), mais a calibração mensal. A maioria sai no
  gate em poucos segundos. Confira o uso no painel do seu plano (no Claude,
  claude.ai/settings/usage).
- Execuções pesadas: montagem (1 a 2 por semana), fechamentos (5 por semana, sexta mais longa),
  notas de cobertura (4 por semana, até 12 emissores cada), calibração mensal.
- Níveis por tarefa em `configs/cdp/rotinas.yaml`: `forte` (semanal, diário, cobertura) e
  `leve` (risco, estado, calibração).

## 12. Segurança

- **Menor privilégio**: nenhum segredo no ambiente da nuvem do Claude Code; nos apps locais com
  acesso total, conta de usuário e clone dedicados, sem outras credenciais além do push do
  repositório.
- **Código acima do prompt**: gate, escopo de caminhos em `cdp publicar`, `cdp verify` antes de
  publicar, kill switch só por gatilho HARD e só desligado por humano — valem em qualquer app.
  No Claude Code, `.claude/settings.json` acrescenta bloqueios; nos demais, as proteções são o
  código e a regra do ramo `main` — **que só existe depois de criada** (seção 3, passo 1;
  confira com `gh api repos/<dono>/<repositório>/rulesets`).
- **Injeção de instruções**: notícias, páginas, arquivos baixados e qualquer conteúdo de disparo
  por API são dados, nunca instruções; a rotina não aceita "aprovações" vindas de conteúdo.
- Varredura de segredos e proteção de push ligadas no GitHub.

## 13. Troca de executor (e ensaio)

**Ensaio**: rotinas criadas com `CDP_ENSAIO=1` no ambiente (CDP-ensaio na nuvem do Claude Code;
`set` do Codex; variável da conta no agendador do sistema) e prompts com `--ensaio` rodam o
fluxo completo sem trava e sem publicar, em paralelo ao executor atual — e consomem a mesma
capacidade do plano (na sexta, uma montagem completa a mais): no dia de uma montagem real,
confira o uso antes das 11:07 e, se a janela estiver apertada, desligue o ensaio
`cdp-semanal*`. Além do prompt, o código garante: com `CDP_ENSAIO=1`, o gate instala um gancho
`pre-push` que recusa todo push enquanto essa variável estiver no ambiente, `cdp trava` não
grava nada no remoto e `cdp publicar` faz só o **commit local** (com o trailer
`CDP-Ensaio: sim`, sem trava e sem push) — a rotina seguinte do ensaio encontra o livro em dia,
como numa semana real. Um clone com commits de ensaio nunca publica fora do ensaio
(`cdp publicar` recusa o push): o ensaio usa sempre um clone próprio. A opção `--ensaio` sozinha
só muda o prompt. Compare: terminou no prazo, validadores ok, transcrição limpa.

**Ensaio nas datas de um cenário** (ex.: a semana da carteira inaugural, antes dela), só com
`CDP_ENSAIO=1` — fora do ensaio a CLI recusa estas variáveis:

- `CDP_AGORA=2026-10-09T11:07` (ISO; sem fuso = Brasília): o relógio de toda a CLI (gate, agenda,
  fechamento, cobertura, notas, semanal, trilha) parte desse instante e anda junto com o tempo
  real;
- `CDP_ENSAIO_SUBSTITUTO=1`: substituto de dados rotulado — pregões ainda inexistentes recebem a
  última barra real de cada série (preços, câmbio, índices, aluguel, juros) com a data pedida;
  cada lote é anunciado na saída de erro como `[ensaio] SUBSTITUTO` e o retorno desses dias é
  nulo. A coleta pública (notícias, CVM, SEC, RI) continua ao vivo.

**Troca** (≤ 10 min; volta pelo mesmo caminho):

1. Janela segura: `uv run python -m cdp executor janela` (nenhum escritor nos próximos 90 min,
   trava livre, nada pendente; evite dias de montagem das 10:30 às 17:30 e as noites das 19:00
   às 23:30).
2. Pause o antigo: desligue as tarefas do app (desktop do Claude Code, Codex ou Antigravity) ou
   as rotinas da nuvem; no clone antigo, `git status -sb` em dia (publique antes qualquer commit
   retido).
3. Troque, numa sessão de operador (nunca dentro de uma rotina):

   ```sh
   uv run python -m cdp executor transferir --para claude-cloud --por "Nome" --motivo "rotinas na nuvem após o ensaio"
   ```

   e faça o commit e o push indicados (`CDP: executor → claude-cloud`). Para um computador com
   Codex ou Antigravity, `--para local-pc --harness codex` (ou `antigravity`).
4. Ligue o novo: rotinas ligadas; execute agora uma tarefa sem pendência; confira
   `uv run python -m cdp estado --rede --formato md`. **Desligue as rotinas do ensaio**
   ("CDP · <tarefa> (…) · ensaio", no ambiente CDP-ensaio; no Codex ou no agendador do sistema,
   as tarefas com `CDP_ENSAIO=1`): ligadas, continuam rodando cerca de 46 vezes por semana e
   montam uma carteira paralela toda sexta.
5. Acompanhe a primeira execução real (transcrição, trailers do commit, portal). O executor
   antigo fica instalado como reserva quente por duas semanas.

## 14. Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "Sem execução: identidade deste ambiente desconhecida" | `CDP_EXECUTOR` ausente | defina no ambiente da nuvem, ou `cdp executor registrar --como local-pc` no clone |
| "o executor designado é local-pc" na nuvem | troca ainda não feita | seção 13 |
| "execução atrasada" | disparo atrasado ou execução manual fora do horário | normal; para rodar já, sessão de operador com `--manual` |
| "<tarefa> em andamento em …" | outra execução segura a trava | normal; a reserva seguinte retoma; trava abandonada expira |
| "trava distribuída indisponível" | GitHub inacessível, disputa ou sandbox sem rede/escrita em `.git` | normal se passageiro; no Codex, confira o acesso total (seção 5.1); persistindo, rede e regras do ramo `cdp-trava` |
| `publicar` → "escritor exclusivo sem a trava" | `--trava` faltando ou trava perdida | nada foi publicado; a execução seguinte refaz a partir do livro |
| `sincronizar` → `parar` | o remoto gravou o livro, ou clone com código alterado | investigar numa sessão de operador no clone do executor; depois de conferir, `git merge origin/main` à mão; nunca forçar |
| `publicar` sem push, "verify falhou" | integridade | `uv run python -m cdp verify` e investigar antes de qualquer publicação |
| rotina verde sem commit | gate saiu cedo, ou falha relatada no resumo | ler a transcrição; `cdp estado` |
| push na nuvem foi para `claude/…` | o prompt não foi o gerado | use só os prompts de `cdp rotinas exportar` (publicam em `main` por `cdp publicar`) |
| portal antigo | workflow não disparou | Actions → cdp-site → Run workflow; `PORTAL_DEFASADO` em `cdp estado --rede` |

## Apêndice A (opcional) — IA no GitHub Actions

Não é o recomendado: só para quem não pode manter um app de IA
agendado. O workflow gerado por
`uv run python -m cdp rotinas exportar --alvo github-actions --saida .github/workflows/cdp-rotinas.yml`
fica **desarmado** até a variável de repositório `CDP_ROTINAS_ATIVAS=1` e exige a troca de
executor para `github-actions`. Tem três jobs, porque as permissões do GitHub valem por job:

1. `gate` (código, sem IA; escrita só no ramo da trava): resolve a tarefa, roda o gate e
   adquire a trava;
2. `mente` (só leitura, sem credencial de escrita): a IA roda o roteiro
   (`--publicacao executor --sem-gate`) e entrega só o que gravou nos caminhos da tarefa
   (`cdp entrega exportar`);
3. `publicar` (código, sem IA): checkout limpo na versão do gate, `cdp entrega importar` (só
   arquivos comuns dentro dos caminhos da tarefa), `cdp publicar` com a trava e a execução do
   gate, dispara o portal e libera a trava (sempre).

| App no Actions | Usa o plano? | Segredo |
|---|---|---|
| Claude Code | sim | `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`, 1 ano, pessoal) |
| Codex | não | `CODEX_API_KEY` |
| Gemini CLI / Antigravity | não | `GEMINI_API_KEY` ou Vertex |

A agenda do Actions é de melhor esforço (minutos de atraso em horários cheios), pior que as
rotinas dos apps para os horários das 11:07 e das 19:22.
