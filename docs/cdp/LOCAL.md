# CDP no PC local — o clone dedicado às rotinas (Claude Code, Codex ou Antigravity)

Este guia põe as rotinas do CDP — Cabra da Peste para rodar no seu computador, dentro do app de
IA: o **app desktop do Claude Code** (executor atual e, depois da troca para a nuvem, reserva
quente), as **tarefas agendadas do app do Codex** ou o **Antigravity** (Gemini). O que roda e
quando: `docs/cdp/ROTINAS.md`; nuvem do Claude Code e detalhes de cada app:
`docs/cdp/AUTOMACAO.md`. Em qualquer app, o procedimento é o mesmo roteiro neutro
(`docs/cdp/playbooks/`) e todo número vem do código.

## 1. Como funciona no PC

- Um **clone dedicado às rotinas**, na `main`, separado do clone em que você desenvolve. A
  identidade desse clone fica em `.cdp/local.yaml` (ignorado pelo git), gravada uma vez por
  `uv run python -m cdp executor registrar --como local-pc --harness claude-code` (ou
  `--harness codex` / `--harness antigravity`, conforme o app).
- Só o executor designado em `configs/cdp/executor.yaml` grava o livro; se ele não for
  `local-pc`, as rotinas do PC saem no gate sem gravar nada. Ligue as rotinas de **um** app por
  vez.
- Cada execução: gate (há o que fazer? sou o executor? trava distribuída) →
  `cdp sincronizar` → roteiro → `cdp publicar` (commit do que a execução gravou — e do que uma
  execução anterior interrompida deixou no clone — e push em `main`) → `cdp trava liberar`.
  Nenhuma skill roda `git` que grave: quem faz commit e push é o código.
- A trava distribuída é o ramo `cdp-trava` no GitHub e **falha fechada**: sem conseguir fazer
  push nesse ramo, um escritor exclusivo (montagem, fechamento, notas) não roda. O PC precisa
  poder fazer push em `main` **e** em `cdp-trava`.

## 2. Pré-requisitos

- **Git** (no Windows, Git for Windows, que inclui o Git Bash usado pelo Claude Code).
- **uv**: o script de preparação instala pelo instalador oficial se faltar.
- O app escolhido, logado com a conta do seu plano: Claude Code (app desktop e o CLI `claude`
  no PATH, para instalar o plugin), Codex (app desktop) ou Antigravity (app ou CLI `agy`).
- **Acesso de escrita ao GitHub** (`gh auth login`, chave SSH ou o gerenciador de credenciais do
  Git) com push em `main` e no ramo `cdp-trava`. O script de preparação testa os dois (seção 3).
- Computador **ligado e acordado** nos horários (seção 8).

## 3. Clonar e preparar

macOS/Linux:

```sh
git clone https://github.com/arielassayag/MarketSummary.git MarketSummary-rotinas
cd MarketSummary-rotinas
git checkout main
bash scripts/cdp_setup_local.sh
```

Windows (PowerShell):

```powershell
git clone https://github.com/arielassayag/MarketSummary.git MarketSummary-rotinas
cd MarketSummary-rotinas
git checkout main
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_setup_local.ps1
```

O script confere o git, instala o uv se faltar, roda `uv sync --extra dev --extra ai`, mostra
`cdp status` e `cdp agenda`, roda `cdp verify` (precisa dizer `ÍNTEGRO`), um teste offline com
DADOS SIMULADOS, testa o push em `main` (`git push --dry-run`) e faz um **push real no ramo
`cdp-trava`**: adquire a trava distribuída por 1 minuto, em nome da tarefa só de leitura
`cdp-status`, e a libera em seguida. Rode-o fora dos horários das rotinas (uma rotina que
dispare nesse instante encontra a trava ocupada e é pulada); para só ler a trava, use
`CDP_SKIP_TRAVA_TESTE=1` (Windows: `-SkipTravaTeste`). Depois, **registra a identidade do
clone** (`cdp executor registrar --como local-pc`; harness pela variável `CDP_HARNESS`, padrão
`claude-code`) e, com o Claude Code, registra o marketplace e instala o plugin. Nada no livro, na
trilha ou nos dados é alterado; no GitHub, só o ramo `cdp-trava` recebe os dois commits do teste.
**Se o script instalou o uv, feche e reabra o app do Claude** (ou do Codex/Antigravity): o PATH
novo só vale para processos novos.

Comandos equivalentes, à mão:

```sh
uv sync --extra dev --extra ai
uv run python -m cdp status
uv run python -m cdp agenda
uv run python -m cdp verify
uv run python -m cdp trava adquirir --tarefa cdp-status --ttl 1
uv run python -m cdp trava liberar --id <id da saída anterior>
uv run python -m cdp executor registrar --como local-pc --harness claude-code
uv run python -m cdp executor mostrar
uv run pytest tests/cdp/test_demo_runtime.py -q
```

> **Fins de linha (Windows).** Os arquivos de `book/`, `data/` e `reports/` têm hash na trilha.
> O `.gitattributes` desliga a conversão de fim de linha nessas pastas; se você clonou antes dele
> existir e o `verify` falhar, clone de novo.

## 4. Claude Code: plugin `cdp` e skills do projeto

As skills do projeto (`.claude/skills/cdp-*`, geradas de `configs/cdp/rotinas.yaml`) já estão no
clone e bastam: `/cdp-diario cdp-diario`. O plugin `cdp` (`plugins/cdp`) é a mesma entrada e
saída da execução, empacotada para o app desktop, com as ferramentas pré-aprovadas
(`allowed-tools`). Para instalá-lo, registre o marketplace apontando para a pasta do clone (o
plugin é carregado direto da pasta, então cada sincronização das rotinas já traz a versão nova):

```sh
claude plugin marketplace add /caminho/para/MarketSummary-rotinas
claude plugin install cdp@cdp-cabra-da-peste
claude plugin list
```

Dentro de uma sessão do Claude Code: `/plugin marketplace add <pasta>` e
`/plugin install cdp@cdp-cabra-da-peste`. Alternativa sem a pasta local:
`claude plugin marketplace add arielassayag/MarketSummary` — o Claude Code guarda uma cópia
presa à `version` de `plugins/cdp/.claude-plugin/plugin.json`, por isso a versão precisa subir
quando as skills mudarem (`tests/cdp/test_plugin.py` confere); atualize com
`claude plugin marketplace update cdp-cabra-da-peste` e `claude plugin update cdp@cdp-cabra-da-peste`.
Para validar os manifestos: `claude plugin validate .`

## 5. Claude Code: permissões para rodar sem supervisão

O `.claude/settings.json` versionado define o que as rotinas fazem sem perguntar:

- **Permitido**: `uv sync`, os subcomandos da CLI do CDP via `uv run` (exceto os da lista
  abaixo), `uv run pytest`, `uv run ruff check`, o git só de leitura (`git status`, `git log`,
  `git diff`, `git fetch`, `git rev-parse`), WebSearch, WebFetch, as skills do CDP
  (`Skill(cdp-diario)`, `Skill(cdp-diario *)`, `Skill(cdp:diario *)` e assim por diante) e
  escrever só os arquivos da mente (`research_pack.json`, `pm_decision.json`, `tese.json`,
  `comentario.json` do dia e da semana, `nota.json`, `reports/backtest/**`, `outputs/**`).
- **Sempre pergunta**: editar `configs/` e `data/`; `cdp executor transferir`,
  `cdp executor registrar` e `cdp trava adquirir` (decisões humanas) e qualquer comando do CDP com
  `--sem-trava` (só operador), nas duas formas (`uv run python -m cdp …` e `uv run cdp …`); o git
  que grava — `git add`, `git commit`, `git push`, `git pull`, `git merge` — e `git reset --hard`,
  `rebase`, `clean`, `restore`. Quem sincroniza e publica é o código (`cdp sincronizar` e
  `cdp publicar` rodam o git por dentro, com executor, trava, `verify` e escopo conferidos): numa
  rotina, um desses comandos deixa a tarefa parada no app ou é negado no `claude -p`; numa sessão
  de desenvolvimento, você aprova à mão.
- **Nunca**: `git push --force` em qualquer forma, `git push --no-verify`,
  `git commit --no-verify`, `rm -rf`, **desligar o kill switch**, editar
  `configs/cdp/executor.yaml` ou `.cdp/**` e editar arquivos gravados pelo código (trilha, track
  record, decisões, briefing, base de mercado, dados públicos arquivados, relatórios
  publicados, fatos, teses e notas publicadas, livro da cobertura, painel). Nenhuma regra de
  bloqueio cobre um arquivo da mente (o bloqueio venceria a permissão).
- `defaultMode: acceptEdits`, `PYTHONUTF8=1` (acentos corretos no Windows) e os limites do Bash,
  iguais no app, no CLI e na nuvem: `BASH_DEFAULT_TIMEOUT_MS=600000` (10 minutos por comando, em
  vez de 2) e `BASH_MAX_TIMEOUT_MS=1800000` (até 30 minutos quando o roteiro pede um limite maior,
  como o `cdp publicar` do risco, que espera a trava por até 10 minutos).

**O que ainda pode parar uma tarefa.** "Aceitar edições" só aprova edições de arquivos e
comandos simples de sistema de arquivos; qualquer outro comando fora das regras pede aprovação e,
no app, a tarefa **fica parada esperando você** — e, como o app roda uma tarefa por vez, as
seguintes são puladas. O modo que nega em vez de perguntar (`dontAsk`) só existe no CLI, não no
app. Por isso os roteiros só usam a CLI do CDP e leitura de arquivos (nada de
`python -c`, `jq`, `sleep` ou laços de espera). Abra a pasta uma vez no Claude Code e aceite a
confiança na pasta: sem isso as regras do projeto não valem.

## 6. Claude Code: criar as tarefas agendadas (app desktop)

A tabela pronta, com a instrução de cada tarefa:

```sh
uv run python -m cdp rotinas exportar --alvo claude-desktop
```

Na aba **Code**: **Routines** → **New routine** → **Local**, uma por linha:

- **Name**: o id da tarefa (ex.: `cdp-diario-reforco`).
- **Instructions**: o comando da skill **com o id da tarefa** — `/cdp-diario cdp-diario-reforco`
  (skill do projeto) ou `/cdp:diario cdp-diario-reforco` (plugin). O gate confere o horário da
  tarefa certa: sem o id, uma reserva ou o risco das 16:03 seriam tomados pela tarefa principal.
- **Permission mode**: "Aceitar edições" (`acceptEdits`). **Folder**: a raiz do clone dedicado.
  **Worktree**: desligado (a identidade, a trava e o livro são do clone).
- **Schedule**: o horário da tabela (dias úteis, semanal ou sábado). Para `cdp-cobertura`
  (segunda a quinta) e `cdp-calibracao` (dia 1 de cada mês), peça numa sessão do app: "agende a
  tarefa cdp-calibracao para o dia 1 de cada mês às 09:15".

Depois, **Run now** em `cdp-status` e acompanhe; um pedido de permissão aparece na sessão (escolha
"always allow" só para comandos seguros). O app roda **uma tarefa por vez**: um disparo que
encontra outra em andamento (ou o PC dormindo) é pulado; por isso existem as reservas da
montagem (`cdp-semanal-b`, `cdp-semanal-c`, `cdp-semanal-d` às 12:07, 13:07 e 14:07), o reforço
do fechamento (`cdp-diario-reforco`, 21:07) e a repescagem de sábado (`cdp-diario-sabado`,
10:07). **Antes de ligar as tarefas locais, desligue as rotinas do CDP em qualquer outro app**
(nuvem do Claude Code, Codex, Antigravity).

## 7. Codex ou Antigravity no PC

O mesmo clone serve a qualquer app, um por vez. Passo a passo:

- **Codex** (tarefas agendadas do app, com acesso total numa conta e num clone dedicados):
  `docs/cdp/ROTINAS.md`, seção 5. Prompts prontos:
  `uv run python -m cdp rotinas exportar --alvo codex --formato md`.
- **Antigravity** (`agy` pelo agendador do sistema, a melhor opção pelo plano Google; ou as
  tarefas agendadas do app, experimentais): `docs/cdp/ROTINAS.md`, seção 6.
  `uv run python -m cdp rotinas exportar --alvo cron --harness agy`.

Em todos, `"mind"` é o nome do app (`codex`, `gemini`), a identidade do clone é registrada com o
`--harness` certo e as tarefas agendadas usam a pasta do projeto, nunca um worktree.

## 8. PC dormindo ou desligado

- As tarefas só disparam com o **app aberto e o PC acordado**. No Claude Code, ative **Settings
  → This computer → System → Keep computer awake** (fechar a tampa ainda faz o PC dormir).
- Ao acordar, o app do Claude Code faz **uma** execução de recuperação por tarefa (a do horário
  perdido mais recente nos últimos 7 dias). O gate recusa disparos muito atrasados para a
  montagem e o risco (`atraso_max_min` em `configs/cdp/rotinas.yaml`); o fechamento aceita até 3
  dias de atraso e processa **todos** os pregões pendentes, em ordem.
- A montagem só decide no dia de montagem (último pregão da semana na NYSE) **antes do prazo
  efetivo**; depois, a carteira anterior é mantida e o estado destaca a decisão perdida. Se a
  execução parou depois da decisão, a reserva seguinte ou o fechamento do dia conclui a tese.
- `dados não prontos` no fechamento: o reforço das 21:07, a repescagem de sábado ou o dia
  seguinte retomam.

## 9. Fuso horário

Os apps agendam pelo **relógio do PC**; o mandato é em Brasília. O código decide pelo relógio de
Brasília, mas os **disparos** dependem do fuso do PC. Rode `uv run python -m cdp agenda` e veja
`pc_menos_brasilia_horas`: `0` → use os horários da tabela; outro valor `h` → some `h` horas a
cada horário (atenção ao horário de verão do PC; o Brasil não tem).

## 10. Painel (artifact)

O **portal público** é o site no GitHub Pages, montado pelo GitHub Actions a partir do livro a
cada push em `main` (`docs/cdp/SITE.md`). A montagem e o fechamento também regeneram
`artifacts/painel/` com `uv run python -m cdp painel --sem-local` (só código; a pasta fica fora
do git — cópia local, nunca no repositório público): `artifacts/painel/data.json` (perfil de publicação: no máximo 260 KB e linhas de até
1.500 caracteres, com os cortes listados em `meta.truncations`), a casca
`artifacts/painel/index.html` e o estilo e o script versionados
(`artifacts/painel/painel-<versão>.css` e `.js`). A cópia autônoma
`artifacts/painel/cdp_painel_local.html` só é gravada sem `--sem-local`, para abrir offline.

**Nenhuma rotina sem supervisão publica artifacts** (na nuvem, a publicação com arquivos de apoio
pede confirmação e a rotina ficaria parada; os outros apps não têm a ferramenta). O artifact
privado do claude.ai é só um **espelho opcional**, feito a pedido do operador numa **sessão
interativa do Claude**, com a ferramenta `Artifact`, seguindo os passos abaixo. A página publicada
compara a sua versão com `meta.page_sha256` dos dados e avisa "Página desatualizada" quando
diferem; se mostrar "Não foi possível carregar os dados do fundo", republique-a com o `data.json`
ao lado. Identidade visual: `docs/cdp/marca/IDENTIDADE.md`.

### 10.1 Gerar o painel (código)

Num clone em dia com `main` (o das rotinas serve):

```sh
uv run python -m cdp painel --sem-local
```

O comando só lê o livro, a trilha e os relatórios e grava `artifacts/painel/` (`data.json`, a
casca `index.html`, o estilo e o script versionados `painel-<versão>.css`/`.js`). Anote o bloco
`artifact`: `publicavel`, `motivo`, `arquivos_para_ler`, `pagina_mudou`, `pagina_publicada`,
`pagina_atual`, `publicar` e `url`.

- `artifact.publicavel: false` ⇒ **não leia nem publique** nada (a ferramenta exige ler por
  inteiro o que for publicado); relate `artifact.motivo`.
- Sem `artifacts/painel/ARTIFACT_URL` (`artifact.url` nulo) ⇒ **não publique**: o artifact é
  criado uma única vez, pelo operador, e o link fica nesse arquivo. Este roteiro nunca cria um
  artifact novo.

### 10.2 Ler o que será publicado

Leia por inteiro cada arquivo de `artifact.arquivos_para_ler`: sempre a casca
`artifacts/painel/index.html` e `artifacts/painel/data.json`; com `artifact.pagina_mudou: true`,
também o estilo e o script versionados. Leia em partes até a última linha. São gerados pelo
código: não os edite.

### 10.3 Publicar no mesmo artifact

Chame `Artifact` com a `url` de `artifacts/painel/ARTIFACT_URL`, nesta ordem:

1. `action: "read"` (uma vez). Confira a versão da página publicada, o valor de
   `<meta name="cdp-page-sha256" content="…">`:
   - igual a `artifact.pagina_publicada` ⇒ siga;
   - igual a `artifact.pagina_atual` (a página desta versão já foi publicada por outra sessão,
     sem o registro) ⇒ rode `uv run python -m cdp painel --publicado`, depois
     `uv run python -m cdp painel --sem-local` de novo, leia o que o novo
     `artifact.arquivos_para_ler` pedir e siga com o novo `artifact.publicar`;
   - outro valor ou ausente ⇒ **não publique**: outra sessão publicou uma página fora deste
     roteiro (por exemplo, uma reformulação em andamento) e republicar a desfaria. Relate.
2. `action: "list"` com `scope: "files"` — obrigatório: a ferramenta só substitui ou remove um
   arquivo publicado que a sessão leu pelo caminho, viu numa listagem ou publicou.
3. `action: "publish"` com `file_path` = `artifact.publicar.file_path` (a casca: a ferramenta
   exige a página em toda publicação) e `files` = `artifact.publicar.files`. Com
   `artifact.pagina_mudou: true`, acrescente em `files`, com valor `null`, cada `painel-*.css` ou
   `painel-*.js` da listagem que não esteja em `artifact.publicar.files` (remove a versão antiga).

Recusa porque um arquivo mudou desde a listagem: repita o `list` com `scope: "files"` uma vez e
publique uma única vez. Recusa por conflito na página: gere o painel de novo, leia o que for
pedido, repita o `list` e publique uma única vez. Nunca use `force`; falha ou recusa: não insista,
relate.

### 10.4 Registrar a página publicada

Só depois de uma publicação bem-sucedida com `artifact.pagina_mudou: true`:

```sh
uv run python -m cdp painel --publicado
```

O registro (`artifacts/painel/PAGINA_PUBLICADA.sha256`) vale para este clone e só serve a este
roteiro. Não faça commit dele à mão: quem grava o livro e o painel no repositório é a rotina
(`cdp publicar`); numa sessão de desenvolvimento, nunca faça commit de `artifacts/`.

## 11. Kill switch

- A rotina de risco liga o kill switch **somente** quando o código traz uma ação
  `kill-switch: <motivo>` (gatilhos HARD: escada de drawdown, stops de squeeze). Ele só bloqueia
  risco novo e nunca afrouxa limites (`docs/cdp/METODOLOGIA.md`, seção 7).
- **Só um humano desliga**, no terminal, depois de revisar:

  ```sh
  uv run python -m cdp kill-switch off --reason "<motivo da revisão>" --by "<seu nome>"
  ```

  As regras do projeto impedem o Claude de rodar esse comando. Depois do desligamento, o monitor
  não religa pela mesma condição revisada (bloco `revisao_humana`); só uma piora religa.

## 12. Sem o app aberto: agendador do sistema

`scripts/cdp_rotina.sh <tarefa> --harness claude|codex|gemini|agy` (Windows:
`scripts\cdp_rotina.ps1`) roda uma tarefa sem interface: trava local, `uv sync`, prévia do gate
(sem trabalho, nenhuma chamada de modelo), pré-comando (backtest da calibração, que no modo sem
interface não pode ficar em segundo plano; a execução é registrada antes dele, para o backtest
sair na publicação), o app com o prompt da tarefa, liberação da trava e conferência de
progresso; log em `logs/cdp/` (ignorado pelo git). O atalho do Claude Code com o
plugin é `scripts/cdp_run_task.sh <skill> <tarefa>` (Windows: `scripts\cdp_run_task.ps1`): chama
o script de rotina com `--modo-prompt plugin` (`/cdp:<skill> <tarefa>`).

As linhas prontas para cada agendador (com o `--harness` do seu app):

```sh
uv run python -m cdp rotinas exportar --alvo cron --harness claude
uv run python -m cdp rotinas exportar --alvo launchd --harness claude --saida ~/Library/LaunchAgents
uv run python -m cdp rotinas exportar --alvo windows --harness claude
```

O bloco do Windows usa `Register-ScheduledTask` com `-AllowStartIfOnBatteries`,
`-DontStopIfGoingOnBatteries` e `-StartWhenAvailable`, em janela oculta (`-WindowStyle Hidden`),
e o `schtasks` para a calibração mensal. Cada tarefa fica em **um** só agendador (o app ou o
do sistema), nunca nos dois; o normal é tudo num lugar só. A exceção documentada é o
Antigravity, cujas tarefas agendadas no app têm modelo fixo e servem só às leves (`cdp-status` e
o risco), com as demais no `agy` pelo agendador do sistema (`docs/cdp/ROTINAS.md`, seção 6).
Trava local: as rotinas que gravam esperam até 60 minutos
(`CDP_LOCK_WAIT_MIN`) a anterior terminar; depois, o script sai com código 75. No modo sem
interface ninguém aprova pedidos: o que não estiver liberado no `.claude/settings.json` é negado
e a rotina relata. Não use `--bare` (não carrega plugins nem skills).

## 13. Troca de executor

Para levar a operação do PC para a nuvem (ou de volta), siga `docs/cdp/AUTOMACAO.md`, seção 13:
janela segura (`uv run python -m cdp executor janela`), desligar as tarefas do PC, transferir o
executor numa sessão de operador e ligar as rotinas do novo app. O PC fica como reserva quente,
com as tarefas desligadas.

## 14. Solução de problemas

| Sintoma | Causa provável e correção |
|---|---|
| "Sem execução: este ambiente não é o executor designado" | o clone não tem identidade (`.cdp/local.yaml`) ou o executor em `configs/cdp/executor.yaml` é outro: `uv run python -m cdp executor mostrar`; registre com `cdp executor registrar` (seção 3) |
| "trava distribuída indisponível" | o PC não consegue fazer push no ramo `cdp-trava` (rede, credencial) ou outra execução segura a trava: confira com `uv run python -m cdp trava ver`; a reserva seguinte tenta de novo |
| "execução atrasada" no gate | o disparo veio muito depois do horário (PC dormindo): é o esperado; numa sessão de operador use `--manual` |
| `/cdp:diario` desconhecido | plugin não instalado: `claude plugin list` e a seção 4; ou use a skill do projeto `/cdp-diario cdp-diario` |
| `uv: command not found` nas tarefas do app | o app foi aberto antes da instalação do uv: feche e reabra o app |
| Tarefa parada esperando aprovação | um comando fora das regras (seção 5): responda na sessão parada e avise o mantenedor para ajustar o roteiro |
| `sincronizar` parou: "clone com código ou configuração alterados" | a pasta da tarefa não é um clone dedicado limpo: use um clone só para as rotinas |
| `sincronizar` parou: "outra sessão gravou o livro no remoto" | duas mentes ou dois clones gravando: mantenha um só executor; não faça merge nem rebase do livro (a trilha é encadeada por hash) |
| `publicar` sem push | `verify` falhou, sem rede ou a trava se perdeu: o commit ficou no clone e a próxima rotina reconcilia; confira com `git status -sb` |
| `publicar` com código 6 (`retidos`) | o risco ligou o kill switch enquanto outra execução segurava a trava: o relatório e o pedido de kill switch (`reports/risk/<data>/kill_switch_<HHMM>.yaml`) saíram; `book/KILL_SWITCH` e o evento da trilha ficaram no clone. A próxima montagem ou fechamento aplica o pedido (em outro clone, como na nuvem) ou publica o que ficou (neste clone, campo `anteriores` do `cdp publicar`) |
| `git status` mostra arquivos em `book/`, `reports/` ou `data/` sem nenhuma rotina rodando | uma execução gravou e não chegou a publicar (PC dormiu, app fechado, tempo esgotado) ou o kill switch ficou retido. A próxima montagem ou fechamento retoma e publica tudo junto (`anteriores`); a rotina de notas para e deixa para o fechamento. Para publicar antes: "Gravações de uma execução interrompida", abaixo |
| `dados não prontos` no fechamento | a fonte ainda não publicou o fechamento; o reforço, a repescagem ou o dia seguinte recuperam |
| `verify` acusa hash divergente após clonar no Windows | fins de linha convertidos: confira o `.gitattributes` e clone de novo |
| Acentos estranhos no Windows | `PYTHONUTF8=1` (já no `.claude/settings.json` e nos scripts); no terminal, `chcp 65001` |
| Decisão da semana perdida | o PC estava desligado entre 11:00 e o prazo efetivo do dia de montagem; a carteira anterior segue até a próxima semana |
| Tese da semana com o texto automático | `tese.json` não passou no `validate-tese` (o código publicou o template, `autoria: "codigo"`); a tese publicada é imutável. Escrita fora do clone das rotinas: entregue em `docs/cdp/teses/<semana>.json`, nunca em `book/` (`docs/cdp/TESE.md`) |
| Kill switch religado logo depois de você desligar | só acontece por piora: veja `revisao_humana` e os gatilhos HARD no relatório de risco |

### Gravações de uma execução interrompida

As rotinas publicam sozinhas o que uma execução interrompida deixou no clone (a próxima montagem
ou fechamento, com a trava). Para publicar antes, numa sessão de operador **no clone das
rotinas** e fora dos horários delas:

```sh
git status --short
uv run python -m cdp verify
uv run python -m cdp trava adquirir --tarefa cdp-diario
uv run python -m cdp publicar --tarefa cdp-diario --mensagem "CDP: publica gravações de execução interrompida" --execucao operador-AAAA-MM-DD --trava <id da trava>
uv run python -m cdp trava liberar --id <id da trava>
```

`verify` precisa dizer `ÍNTEGRO`; senão, não publique e investigue com
`uv run python -m cdp estado --formato md`. Uma `--execucao` sem registro faz o `cdp publicar`
levar tudo o que difere da versão local nos caminhos do fechamento (que cobrem todo o livro). No
Claude Code, `trava adquirir` pede a sua aprovação.
