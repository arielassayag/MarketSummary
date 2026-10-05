# CDP no PC local — tarefas agendadas do Claude Code (plugin `cdp`)

Este guia põe o CDP — Cabra da Peste para rodar sozinho no seu computador: montagem semanal da
carteira, monitor de risco durante o pregão, fechamento diário com comentário e relatório, checagem
de saúde e calibração mensal. Tudo roda como **tarefas agendadas locais** do app desktop do Claude
Code, cada uma chamando uma **skill do plugin `cdp`** que vive neste repositório.

A metodologia e os roteiros continuam perenes e independentes do harness
(`docs/cdp/METODOLOGIA.md`, `docs/cdp/playbooks/`). O plugin só operacionaliza esses roteiros no
PC local: sincroniza o git, decide pelo relógio de Brasília o que fazer (`cdp agenda`), recupera
dias perdidos e publica (commit e push). Todo número continua vindo do código.

## 1. O que roda e quando

Horários de Brasília (`America/Sao_Paulo`). As skills checam o calendário da B3 no código e saem
sem fazer nada quando não é dia: por isso as tarefas podem rodar em todos os dias úteis.

| Tarefa (nome) | Agenda | Instruções | O que faz |
|---|---|---|---|
| `cdp-status` | segundas, 08:30 | `/cdp:status` | saúde: integridade da trilha, pendências, próximos eventos, git (só leitura) |
| `cdp-semanal` | dias úteis, 11:07 | `/cdp:semanal` | só no 1º pregão da semana na B3: coleta, pesquisa, decisão do PM, validação, decisão autônoma até 16:30, commit e push |
| `cdp-risco-1330` | dias úteis, 13:30 | `/cdp:risco` | monitor de risco intradiário (`cdp risk --live`); liga o kill switch só se o código mandar |
| `cdp-risco-1600` | dias úteis, 16:00 | `/cdp:risco` | idem, perto do fechamento |
| `cdp-diario` | dias úteis, 19:22 | `/cdp:diario` | fechamento oficial (execução MOC da semana, marcação, risco, atribuição, registro), comentário, relatório, commit e push; recupera pregões perdidos |
| `cdp-diario-reforco` (opcional) | dias úteis, 21:07 | `/cdp:diario` | segunda tentativa se a fonte ainda não tinha publicado o fechamento às 19:22 (sem pendência ⇒ não faz nada) |
| `cdp-calibracao` | mensal, dia 1, 09:15 | `/cdp:calibracao` | backtest com todo o histórico em `reports/backtest/<data>/mensal`, comparação com a execução anterior; nunca muda o mandato |

Skills do plugin (`plugins/cdp/skills/`): `semanal`, `diario`, `risco`, `status`, `calibracao`,
invocadas como `/cdp:<nome>`.

## 2. Pré-requisitos

- **Git** (no Windows: Git for Windows, que inclui o Git Bash usado pelo Claude Code).
- **uv** (gerenciador de Python): o script de preparação instala pelo instalador oficial se faltar.
- **Claude Code**: app desktop (as tarefas agendadas locais ficam na aba **Code → Routines**) e o
  CLI `claude` no PATH (para instalar o plugin pela linha de comando). Faça login uma vez.
- **Acesso de escrita ao GitHub** para o `git push` das rotinas: `gh auth login`, chave SSH ou o
  gerenciador de credenciais do Git (Windows). Teste com `git push --dry-run`.
- Computador **ligado e acordado** nos horários (veja a seção 8).

## 3. Clonar e preparar

macOS/Linux:

```sh
git clone https://github.com/arielassayag/MarketSummary.git
cd MarketSummary
git checkout main
bash scripts/cdp_setup_local.sh
```

Windows (PowerShell):

```powershell
git clone https://github.com/arielassayag/MarketSummary.git
cd MarketSummary
git checkout main
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_setup_local.ps1
```

O script confere o git, instala o uv se faltar, roda `uv sync --extra dev --extra ai`, mostra
`cdp status` e `cdp agenda`, roda `cdp verify` (precisa dizer `ÍNTEGRO`), um teste offline com
DADOS SIMULADOS, testa o push (`--dry-run`), registra o marketplace e instala o plugin. Nada no
livro, na trilha ou nos dados é alterado.

Comandos equivalentes, à mão:

```sh
uv sync --extra dev --extra ai
uv run python -m cdp status
uv run python -m cdp agenda
uv run python -m cdp verify
uv run pytest tests/cdp/test_demo_runtime.py -q
```

> **Fins de linha (Windows).** Os arquivos de `book/`, `data/` e `reports/` têm hash na trilha de
> auditoria. O `.gitattributes` do repositório desliga a conversão automática de fim de linha
> nessas pastas. Se você clonou antes dele existir e o `verify` falhar, clone de novo.

## 4. Instalar o plugin `cdp`

O repositório é também um **marketplace** (`.claude-plugin/marketplace.json`, nome
`cdp-cabra-da-peste`) com um plugin (`plugins/cdp`). Registre o marketplace apontando para a
pasta do clone — assim o Claude Code lê as skills direto do clone e cada `git pull` das rotinas já
traz a versão nova na sessão seguinte:

```sh
claude plugin marketplace add /caminho/para/MarketSummary
claude plugin install cdp@cdp-cabra-da-peste
claude plugin list
```

No Windows, use o caminho da pasta (ex.: `C:\Users\voce\MarketSummary`). Dentro de uma sessão do
Claude Code, o equivalente é `/plugin marketplace add <pasta>` e `/plugin install cdp@cdp-cabra-da-peste`.
Para conferir, abra uma sessão na pasta do repositório e rode `/cdp:status`.

Alternativa (sem depender da pasta local): `claude plugin marketplace add arielassayag/MarketSummary`
— o Claude Code guarda uma cópia; atualize com `claude plugin marketplace update cdp-cabra-da-peste`
e `claude plugin update cdp@cdp-cabra-da-peste` (a versão do plugin, em
`plugins/cdp/.claude-plugin/plugin.json`, precisa subir quando as skills mudarem). Para validar os
manifestos: `claude plugin validate .`

As skills antigas do projeto (`.claude/skills/cdp-semanal` e `cdp-diario`) agora são atalhos: com
o plugin instalado, delegam para `cdp:semanal`/`cdp:diario`; sem ele (nuvem, Codex), seguem os
roteiros em `docs/cdp/playbooks/`.

## 5. Permissões para rodar sem supervisão

O arquivo versionado `.claude/settings.json` define o que as rotinas podem fazer sem perguntar:

- **Permitido**: `uv sync`, todos os subcomandos da CLI do CDP via `uv run` (exceto desligar o
  kill switch), `uv run pytest`, `uv run ruff check`, git
  (`status`, `pull`, `fetch`, `log`, `diff`, `add`, `commit`, `push`), WebSearch, WebFetch, e
  escrever só os arquivos da mente (`book/<semana>/inputs/research_pack.json`,
  `pm_decision.json`, `reports/daily/<data>/comentario.json`, `reports/backtest/**`, `outputs/**`).
- **Sempre pergunta**: editar `configs/` (mandato) e `data/`, `git reset --hard`, `rebase`,
  `clean`, `restore`, `checkout --`.
- **Nunca**: `git push --force` (em qualquer forma), `rm -rf`, apagar `book/` ou `data/`,
  **desligar o kill switch**, editar arquivos gravados pelo código (trilha de auditoria, track
  record, decisões, propostas, briefing, base de mercado, relatórios publicados).
- `defaultMode: acceptEdits` e `PYTHONUTF8=1` (acentos corretos no Windows).

Abra a pasta uma vez no Claude Code e aceite a confiança na pasta ("trust"): sem isso as regras do
projeto não valem e a tarefa agendada não pode ser salva.

## 6. Criar as tarefas agendadas (app desktop)

Na aba **Code**, clique em **Routines** → **New routine** → **Local** e preencha, para cada linha
da tabela da seção 1:

- **Name**: o nome da tabela (ex.: `cdp-diario`).
- **Description**: a coluna "O que faz".
- **Instructions**: exatamente `/cdp:<skill>` (ex.: `/cdp:diario`). Se preferir texto livre:
  "Use a skill cdp:diario do plugin cdp; rotina agendada sem supervisão."
- **Permission mode**: **Aceitar edições** (`acceptEdits`). As regras do `.claude/settings.json`
  liberam o resto; nada fica esperando aprovação.
- **Model**: deixe o padrão.
- **Folder**: a raiz do clone (`MarketSummary`).
- **Worktree**: **desligado** (as rotinas precisam gravar e publicar no próprio clone, na `main`).
- **Schedule**: `Weekdays` com a hora da tabela; `Weekly` (segunda) para o status. Para a
  calibração mensal, peça numa sessão do desktop: "agende a tarefa cdp-calibracao para o dia 1 de
  cada mês às 09:15".

Depois de criar, clique em **Run now** em `cdp-status` (e, se quiser, em `cdp-risco-1330`): se
aparecer algum pedido de permissão, escolha "always allow"; as próximas execuções não perguntam.
As tarefas ficam em `~/.claude/scheduled-tasks/<nome>/SKILL.md` (o corpo é o texto das
instruções; agenda, pasta e modo ficam no app).

**Antes de ligar as tarefas locais, desative as rotinas do CDP na nuvem** (claude.ai/code →
Routines), se existirem. Duas mentes gravando o mesmo livro divergem: as skills fazem
`git pull --ff-only` e param quando isso acontece, mas o dia fica sem rotina.

## 7. Fuso horário

O app agenda pelo **relógio do PC**; o mandato é em Brasília. As skills decidem pelo relógio de
Brasília (calculado no código, independente do fuso do PC), mas os **disparos** dependem do fuso
do PC. Rode `uv run python -m cdp agenda` e veja `pc_menos_brasilia_horas`:

- `0` → use os horários da tabela.
- outro valor `h` → some `h` horas a cada horário (ex.: PC em Lisboa no inverno europeu, `h = 3`:
  19:22 → 22:22). Atenção ao horário de verão do PC (o Brasil não tem).

A skill `status` avisa quando o PC não está no fuso de Brasília.

## 8. PC dormindo ou desligado

- As tarefas só disparam com o **app aberto e o PC acordado**. Ative **Settings → This computer →
  System → Keep computer awake** (fechar a tampa do notebook ainda faz o PC dormir).
- Ao acordar, o app faz **uma** execução de recuperação do horário perdido mais recente (até 7
  dias). As skills foram feitas para isso:
  - `diario` processa **todos** os pregões pendentes, em ordem (`cdp agenda` →
    `fechamentos_pendentes`), com o comentário de cada data. Para recuperar à mão, rode
    `/cdp:diario` numa sessão na pasta do repositório (ou `/cdp:diario AAAA-MM-DD` para uma data).
  - `semanal` só decide no primeiro pregão da semana **até 16:30**. Depois disso (ou em outro
    dia), não decide: a carteira anterior é mantida até a semana seguinte e o `status` destaca a
    decisão perdida. O código não permite decidir fora do primeiro pregão (seria look-ahead).
  - `risco` mede o estado no momento em que roda; execuções perdidas não são refeitas.
- Se a fonte ainda não publicou o fechamento (`dados não prontos`), o `diario` para e a próxima
  execução (o reforço das 21:07 ou o dia seguinte) retoma.

## 9. Acompanhamento e notificações

- Cada disparo gera uma notificação do desktop e uma sessão na seção **Scheduled** da barra
  lateral; a resposta final de cada skill é um resumo curto (números copiados dos relatórios).
- Relatórios: `reports/weekly/<semana>/relatorio.md`, `reports/daily/<data>/relatorio.md`,
  `reports/risk/<data>/risco_<HHMM>.md`, `reports/backtest/<data>/`.
- Painel: `uv run streamlit run cdp_app.py --server.address 127.0.0.1`.
- Comandos úteis: `uv run python -m cdp agenda` (o que está pendente), `uv run python -m cdp risk`
  (risco do último fechamento), `uv run python -m cdp risk --live` (intradiário), `uv run python -m cdp verify`.

## 10. Kill switch

- A skill `risco` liga o kill switch **somente** quando `cdp risk` traz uma ação
  `kill-switch: <motivo>` — gatilhos HARD do mandato (escada de drawdown em `hard_stop`/`stop_out`,
  stops de squeeze). O motivo é o texto do código.
- O kill switch só bloqueia risco novo (redução continua permitida) e nunca afrouxa limites.
- **Só um humano desliga**, no terminal, depois de revisar:

  ```sh
  uv run python -m cdp kill-switch off --reason "<motivo da revisão>" --by "<seu nome>"
  ```

  As regras do projeto impedem o Claude de rodar esse comando.

## 11. Sem o app aberto: agendador do sistema (alternativa)

`scripts/cdp_run_task.sh` (macOS/Linux) e `scripts/cdp_run_task.ps1` (Windows) rodam uma skill sem
interface com `claude -p "/cdp:<skill>" --permission-mode acceptEdits`, gravando o log em
`logs/cdp/<tarefa>_<data_hora>.log` (pasta ignorada pelo git) e com trava contra execuções
simultâneas. Use **uma** das duas formas (app ou agendador do sistema), nunca as duas.

- O `claude` precisa estar logado no usuário que roda o agendador (ou com `ANTHROPIC_API_KEY`).
  Não use `--bare`: ele não carrega plugins nem skills.
- No modo `-p` ninguém aprova pedidos: o que não estiver liberado no `.claude/settings.json` é
  negado e a skill relata no resumo. Em versões recentes do CLI, `CDP_CLAUDE_ARGS="--permission-prompts none"`
  deixa isso explícito.

**Linux (cron)** — `crontab -e` (com `CRON_TZ`, se o seu cron suportar; senão, converta os horários):

```text
CRON_TZ=America/Sao_Paulo
30 8 * * 1    /caminho/MarketSummary/scripts/cdp_run_task.sh status
7 11 * * 1-5  /caminho/MarketSummary/scripts/cdp_run_task.sh semanal
30 13 * * 1-5 /caminho/MarketSummary/scripts/cdp_run_task.sh risco
0 16 * * 1-5  /caminho/MarketSummary/scripts/cdp_run_task.sh risco
22 19 * * 1-5 /caminho/MarketSummary/scripts/cdp_run_task.sh diario
7 21 * * 1-5  /caminho/MarketSummary/scripts/cdp_run_task.sh diario
15 9 1 * *    /caminho/MarketSummary/scripts/cdp_run_task.sh calibracao
```

**macOS (launchd)** — um arquivo por tarefa em `~/Library/LaunchAgents/` (horário local do Mac).
Exemplo do fechamento diário, `com.cdp.diario.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.cdp.diario</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/voce/MarketSummary/scripts/cdp_run_task.sh</string>
    <string>diario</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>22</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>22</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>22</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>22</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>19</integer><key>Minute</key><integer>22</integer></dict>
  </array>
</dict>
</plist>
```

Carregue com `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cdp.diario.plist`
(o launchd roda tarefas perdidas durante o sono quando o Mac acorda).

**Windows (Agendador de Tarefas)** — no PowerShell:

```powershell
$ps = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\voce\MarketSummary\scripts\cdp_run_task.ps1"
schtasks /Create /TN "CDP\status"     /TR "$ps status"     /SC WEEKLY  /D MON /ST 08:30
schtasks /Create /TN "CDP\semanal"    /TR "$ps semanal"    /SC WEEKLY  /D MON,TUE,WED,THU,FRI /ST 11:07
schtasks /Create /TN "CDP\risco1330"  /TR "$ps risco"      /SC WEEKLY  /D MON,TUE,WED,THU,FRI /ST 13:30
schtasks /Create /TN "CDP\risco1600"  /TR "$ps risco"      /SC WEEKLY  /D MON,TUE,WED,THU,FRI /ST 16:00
schtasks /Create /TN "CDP\diario"     /TR "$ps diario"     /SC WEEKLY  /D MON,TUE,WED,THU,FRI /ST 19:22
schtasks /Create /TN "CDP\calibracao" /TR "$ps calibracao" /SC MONTHLY /D 1 /ST 09:15
```

Em cada tarefa, marque "Executar assim que possível após uma inicialização agendada ter sido
perdida" (aba Configurações) para recuperar execuções com o PC desligado.

## 12. Codex como mente

O Codex lê `AGENTS.md` e segue a mesma metodologia e os mesmos roteiros. Os passos das skills em
`plugins/cdp/skills/<skill>/SKILL.md` valem para ele trocando `claude-code` por `codex` (use
`--mind codex` na CLI e `"mind": "codex"` nos JSON). Para agendar, use o agendador do sistema com o modo não
interativo do Codex CLI (consulte a documentação do Codex para as flags) e um texto como os de
`docs/cdp/ROTINAS.md`. Não ligue as duas mentes no mesmo livro ao mesmo tempo.

## 13. Solução de problemas

| Sintoma | Causa provável e correção |
|---|---|
| `/cdp:diario` desconhecido na tarefa | plugin não instalado/ativado: `claude plugin list`; repita a seção 4; confira se a tarefa usa a pasta do clone |
| Tarefa parada esperando aprovação | modo "Manual" ou ferramenta fora do `.claude/settings.json`: use "Aceitar edições", clique em Run now e "always allow" |
| `git pull --ff-only` falhou | outra máquina/sessão gravou o livro. Não faça merge/rebase do livro (a trilha é encadeada por hash): descubra quem gravou, mantenha uma só mente e alinhe o clone com o remoto |
| `dados não prontos` no fechamento | a fonte ainda não publicou o fechamento; o reforço das 21:07 ou o dia seguinte recupera |
| `verify` acusa hash divergente após clonar no Windows | fins de linha convertidos: confira o `.gitattributes` e clone de novo |
| Acentos estranhos / `UnicodeEncodeError` no Windows | `PYTHONUTF8=1` (já no `.claude/settings.json` e nos scripts); para o terminal, `chcp 65001` |
| `uv`/`claude` não encontrados no agendador do sistema | PATH mínimo do cron/launchd/Agendador: use caminhos absolutos ou ajuste `CDP_CLAUDE_BIN`; os scripts já incluem `~/.local/bin` |
| Execução marcada como "skipped" no app | o PC dormia, a execução anterior ainda rodava ou outra tarefa estava em andamento (ex.: risco das 16:00 durante a montagem semanal) |
| Decisão da semana perdida | o PC estava desligado entre 11:00 e 16:30 do primeiro pregão; a carteira anterior segue até a próxima semana |
