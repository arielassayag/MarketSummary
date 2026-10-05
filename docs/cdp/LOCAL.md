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
sem fazer nada quando não é dia: por isso as tarefas podem rodar em todos os dias úteis. Todas
usam a **mesma pasta** (a raiz do clone dedicado, seção 3), **worktree desligado** e o modo de
permissão **Accept edits** ("Aceitar edições").

| Tarefa (nome) | Agenda | Instruções | O que faz |
|---|---|---|---|
| `cdp-status` | segundas, 08:30 | `/cdp:status` | saúde: integridade da trilha, pendências, próximos eventos, git (só leitura) |
| `cdp-semanal` | dias úteis, 11:07 | `/cdp:semanal` | só no 1º pregão da semana na B3: coleta, pesquisa, decisão do PM, validação, decisão autônoma até 16:30, commit e push |
| `cdp-semanal-b` | dias úteis, 12:37 | `/cdp:semanal` | reserva: se a montagem não começou ou parou no meio, retoma da etapa em que parou; com a decisão gravada, sai sem fazer nada |
| `cdp-risco-1330` | dias úteis, 13:30 | `/cdp:risco` | monitor de risco intradiário (`cdp risk --live`); liga o kill switch só se o código mandar |
| `cdp-semanal-c` | dias úteis, 14:07 | `/cdp:semanal` | reserva (idem) |
| `cdp-semanal-d` | dias úteis, 15:07 | `/cdp:semanal` | reserva (idem; com menos de 60 minutos de prazo a skill encurta a pesquisa) |
| `cdp-risco-1600` | dias úteis, 16:00 | `/cdp:risco` | idem, perto do fechamento |
| `cdp-diario` | dias úteis, 19:22 | `/cdp:diario` | fechamento oficial (execução MOC da semana, marcação, risco, atribuição, registro), comentário, relatório, commit e push; recupera pregões perdidos |
| `cdp-diario-reforco` | dias úteis, 21:07 | `/cdp:diario` | segunda tentativa se a fonte ainda não tinha publicado o fechamento às 19:22 ou se a das 19:22 foi pulada (sem pendência ⇒ não faz nada) |
| `cdp-calibracao` | mensal, dia 1, 09:15 | `/cdp:calibracao` | backtest com todo o histórico em `reports/backtest/<data>/mensal`, comparação com a execução anterior; nunca muda o mandato |

**Por que as reservas.** O app roda **uma tarefa por vez**: um disparo que encontra outra tarefa em
andamento (ou o PC dormindo) é **pulado**, não enfileirado, e ao acordar cada tarefa ganha só uma
execução de recuperação. Uma única tarefa semanal perderia a semana inteira se, por exemplo, a
recuperação do fechamento de sexta ainda estivesse rodando às 11:07 de segunda, ou se a coleta
falhasse por um erro de rede passageiro. As reservas são idempotentes (o `cdp agenda` diz se ainda
há o que fazer); nos outros dias úteis elas só conferem a agenda e saem. Se preferir economizar
essas execuções, deixe as reservas só às segundas e terças (cobre segunda-feira feriado), sabendo
que semanas com dois feriados seguidos (Carnaval) ficam só com a tarefa principal.

Skills do plugin (`plugins/cdp/skills/`): `semanal`, `diario`, `risco`, `status`, `calibracao`,
invocadas como `/cdp:<nome>`. As que gravam algo (`semanal`, `diario`, `risco`, `calibracao`)
terminam atualizando o **painel** de operação e risco e, quando possível, republicando-o no mesmo
artifact (seção 10); `status` só informa o link.

## 2. Pré-requisitos

- **Git** (no Windows: Git for Windows, que inclui o Git Bash usado pelo Claude Code).
- **uv** (gerenciador de Python): o script de preparação instala pelo instalador oficial se faltar.
- **Claude Code**: app desktop (as tarefas agendadas locais ficam na aba **Code → Routines**) e o
  CLI `claude` no PATH (para instalar o plugin pela linha de comando). Faça login uma vez.
- **Acesso de escrita ao GitHub** para o `git push` das rotinas: `gh auth login`, chave SSH ou o
  gerenciador de credenciais do Git (Windows). Teste com `git push --dry-run`.
- Computador **ligado e acordado** nos horários (veja a seção 8).

## 3. Clonar e preparar

Use um **clone dedicado às rotinas**, na `main`, separado do clone em que você desenvolve. As
skills que gravam param logo no início se a branch não for `main` ou se houver código ou
configuração alterados sem commit (o registro do dia seria calculado com código não commitado e
publicado fora da `main`).

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
DADOS SIMULADOS, testa o push (`--dry-run`), registra o marketplace e instala o plugin. Nada no
livro, na trilha ou nos dados é alterado. **Se o script instalou o uv, feche e reabra o app do
Claude** depois: o PATH novo só vale para processos novos, e as tarefas agendadas herdam o
ambiente do app.

Comandos equivalentes, à mão:

```sh
uv sync --extra dev --extra ai
uv run python -m cdp status
uv run python -m cdp agenda
uv run python -m cdp verify
uv run pytest tests/cdp/test_demo_runtime.py -q
```

**Sincronização com o GitHub (feita pelas skills).** No início e antes de cada push, as skills
rodam `git fetch` e comparam com o remoto:

- remoto igual ou só o local à frente ⇒ seguem;
- remoto à frente só com código/documentação (nada em `book/`, `data/`, `reports/` ou
  `artifacts/`) ⇒ `git pull --no-rebase --no-edit` (merge que não reescreve commits locais; os
  bytes do livro não mudam e a trilha continua íntegra) e seguem — um PR de documentação
  mesclado no GitHub durante a montagem semanal não trava as rotinas;
- remoto com mudanças no livro ⇒ param (outra máquina ou sessão gravou o livro);
- `git fetch` falhou (rede, token expirado) ⇒ seguem localmente, sem push, e relatam; a próxima
  rotina com rede envia os commits retidos.

> **Fins de linha (Windows).** Os arquivos de `book/`, `data/` e `reports/` têm hash na trilha de
> auditoria. O `.gitattributes` do repositório desliga a conversão automática de fim de linha
> nessas pastas. Se você clonou antes dele existir e o `verify` falhar, clone de novo.

## 4. Instalar o plugin `cdp`

O repositório é também um **marketplace** (`.claude-plugin/marketplace.json`, nome
`cdp-cabra-da-peste`) com um plugin (`plugins/cdp`). Registre o marketplace apontando para a
pasta do clone — um plugin de marketplace local é carregado direto da pasta (sem cópia em cache),
então cada `git pull` das rotinas já traz a versão nova na sessão seguinte:

```sh
claude plugin marketplace add /caminho/para/MarketSummary-rotinas
claude plugin install cdp@cdp-cabra-da-peste
claude plugin list
```

No Windows, use o caminho da pasta (ex.: `C:\Users\voce\MarketSummary-rotinas`). Dentro de uma
sessão do Claude Code, o equivalente é `/plugin marketplace add <pasta>` e
`/plugin install cdp@cdp-cabra-da-peste`. Para conferir, abra uma sessão na pasta do repositório e
rode `/cdp:status`.

Alternativa (sem depender da pasta local): `claude plugin marketplace add arielassayag/MarketSummary`
— o Claude Code guarda uma cópia, presa à `version` de `plugins/cdp/.claude-plugin/plugin.json`;
atualize com `claude plugin marketplace update cdp-cabra-da-peste` e
`claude plugin update cdp@cdp-cabra-da-peste` (a versão precisa subir quando as skills mudarem).
Para validar os manifestos: `claude plugin validate .`

As skills antigas do projeto (`.claude/skills/cdp-semanal` e `cdp-diario`) agora são atalhos: com
o plugin instalado, delegam para `cdp:semanal`/`cdp:diario`; sem ele (nuvem, Codex), seguem os
roteiros em `docs/cdp/playbooks/`.

## 5. Permissões para rodar sem supervisão

O arquivo versionado `.claude/settings.json` define o que as rotinas podem fazer sem perguntar:

- **Permitido**: `uv sync`, todos os subcomandos da CLI do CDP via `uv run` (exceto desligar o
  kill switch), `uv run pytest`, `uv run ruff check`, git
  (`status`, `pull`, `fetch`, `log`, `diff`, `add`, `commit`, `push`, `branch --show-current`),
  WebSearch, WebFetch, as skills do plugin, e escrever só os arquivos da mente
  (`book/<semana>/inputs/research_pack.json`, `pm_decision.json`,
  `reports/daily/<data>/comentario.json`, `reports/backtest/**`, `outputs/**`) e o link do painel
  (`artifacts/painel/ARTIFACT_URL`).
- **Sempre pergunta**: editar `configs/` (mandato) e `data/`, `git reset --hard`, `rebase`,
  `clean`, `restore`, `checkout --`.
- **Nunca**: `git push --force` (em qualquer forma), `rm -rf`, apagar `book/` ou `data/`,
  **desligar o kill switch**, editar arquivos gravados pelo código (trilha de auditoria, track
  record, decisões, propostas, briefing, base de mercado, relatórios publicados, HTML do painel).
- `defaultMode: acceptEdits` e `PYTHONUTF8=1` (acentos corretos no Windows).

Cada skill também declara no próprio `SKILL.md` (`allowed-tools`) as ferramentas que usa —
inclusive a ferramenta `Artifact`, que republica o painel —, pré-aprovadas enquanto a skill roda.
A ferramenta `Artifact` não entra no `.claude/settings.json` do projeto de propósito: fora das
skills, publicar ou apagar artifacts continua pedindo confirmação.

**O que ainda pode parar uma tarefa.** "Accept edits" só aprova sozinho edições de arquivos e
comandos simples de sistema de arquivos (`mkdir`, `touch`, `mv`, `cp`); qualquer outro comando
fora das regras acima pede aprovação, e no app a tarefa **fica parada esperando você** — e, como o
app roda uma tarefa por vez, as seguintes são puladas enquanto ela estiver aberta. O modo que nega
em vez de perguntar (`dontAsk`) só existe no CLI, não no app. Por isso as skills só usam os
comandos liberados (nada de `python -c`, `jq`, `sleep` ou laços de espera) e param, relatando,
quando precisariam de outro. Se uma tarefa aparecer parada na barra lateral, responda ao pedido
("always allow" só se o comando for seguro) e avise o mantenedor para ajustar a skill.

Abra a pasta uma vez no Claude Code e aceite a confiança na pasta ("trust"): sem isso as regras do
projeto não valem e a tarefa agendada não pode ser salva.

## 6. Criar as tarefas agendadas (app desktop)

Na aba **Code**, clique em **Routines** → **New routine** → **Local** e preencha, para cada linha
da tabela da seção 1:

- **Name**: o nome da tabela (ex.: `cdp-diario`).
- **Description**: a coluna "O que faz".
- **Instructions**: exatamente `/cdp:<skill>` (ex.: `/cdp:diario`). Se preferir texto livre:
  "Use a skill cdp:diario do plugin cdp; rotina agendada sem supervisão."
- **Permission mode**: **Accept edits** ("Aceitar edições", `acceptEdits`).
- **Model**: deixe o padrão.
- **Folder**: a raiz do clone dedicado (`MarketSummary-rotinas`).
- **Worktree**: **desligado** (as rotinas precisam gravar e publicar no próprio clone, na `main`).
- **Schedule**: `Weekdays` com a hora da tabela; `Weekly` (segunda) para o status. Para a
  calibração mensal, peça numa sessão do desktop: "agende a tarefa cdp-calibracao para o dia 1 de
  cada mês às 09:15".

Depois de criar, clique em **Run now** em `cdp-status` e em `cdp-risco-1330` (o risco também
publica) e acompanhe: se aparecer algum pedido de permissão — por exemplo, da ferramenta
`Artifact` —, escolha "always allow"; as próximas execuções daquela tarefa não perguntam. As
aprovações ficam no painel **Always allowed** de cada tarefa. As tarefas ficam em
`~/.claude/scheduled-tasks/<nome>/SKILL.md` (o corpo é o texto das instruções; agenda, pasta e
modo ficam no app).

**Antes de ligar as tarefas locais, desative as rotinas do CDP na nuvem** (claude.ai/code →
Routines), se existirem. Duas mentes gravando o mesmo livro divergem: as skills param quando o
remoto mudou o livro, e o dia fica sem rotina.

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
- Ao abrir o app ou acordar o PC, o app verifica as execuções perdidas nos últimos 7 dias e faz
  **uma** execução de recuperação por tarefa, a do horário perdido mais recente nesse período;
  as mais antigas são descartadas. Como as tarefas rodam uma por vez, recuperações que coincidem
  disputam a vez (daí as reservas da seção 1). As skills foram feitas para isso:
  - `diario` processa **todos** os pregões pendentes, em ordem (`cdp agenda` →
    `fechamentos_pendentes`), com o comentário de cada data. Para recuperar à mão, rode
    `/cdp:diario` numa sessão na pasta do repositório (ou `/cdp:diario AAAA-MM-DD` para uma data).
  - `semanal` só decide no primeiro pregão da semana **até 16:30**. Depois disso (ou em outro
    dia), não decide: a carteira anterior é mantida até a semana seguinte e o `status` destaca a
    decisão perdida. O código não permite decidir fora do primeiro pregão (seria look-ahead).
  - `risco` mede o estado no momento em que roda; execuções perdidas não são refeitas.
- Se a fonte ainda não publicou o fechamento (`dados não prontos`), o `diario` para e o reforço
  das 21:07 (ou o dia seguinte) retoma.

## 9. Acompanhamento e notificações

- Cada disparo gera uma notificação do desktop e uma sessão na seção **Scheduled** da barra
  lateral; a resposta final de cada skill é um resumo curto (números copiados dos relatórios).
  No histórico da tarefa, passe o mouse sobre uma execução pulada para ver o motivo.
- Relatórios: `reports/weekly/<semana>/relatorio.md`, `reports/daily/<data>/relatorio.md`,
  `reports/risk/<data>/risco_<HHMM>.md`, `reports/backtest/<data>/`.
- Painel publicado (artifact): seção 10. App local completo (Streamlit):
  `uv run streamlit run cdp_app.py --server.address 127.0.0.1`.
- Comandos úteis: `uv run python -m cdp agenda` (o que está pendente), `uv run python -m cdp risk`
  (risco do último fechamento), `uv run python -m cdp risk --live` (intradiário), `uv run python -m cdp verify`.

## 10. Painel (artifact)

O painel de operação e risco é gerado **pelo código** a partir do livro, da trilha e dos relatórios
(nenhum número é escrito pela IA) e publicado em dois arquivos — a página e os dados:

```sh
uv run python -m cdp painel
uv run python -m cdp painel --sem-local
uv run python -m cdp painel --publicado
```

- Saída em `artifacts/painel/` (versionada; vai em cada commit das rotinas):
  - `artifacts/painel/index.html` — a página, com o elemento de dados vazio (`null`) e a versão
    da página (SHA-256 do template) carimbada: ao abrir, ela busca `data.json` ao lado dela e
    mostra um estado de carregamento; se não conseguir, mostra "Não foi possível carregar
    data.json" (nunca uma página em branco). O arquivo só é regravado quando o template muda.
  - `artifacts/painel/data.json` — os dados publicados, no perfil **publicação**: JSON indentado
    com no máximo 260 KB e linhas de até 1.500 caracteres, para caber na leitura integral que a
    ferramenta de publicação exige. Mesmos números do retrato completo (nunca arredondados);
    textos longos terminam em "…" (`"_truncado": true`), históricos antigos viram resumos (meses
    consolidados no track record, semanas antigas em uma linha) e tudo o que foi cortado fica em
    `meta.truncations`. Formas sem perda que a página desfaz: tabelas em colunas (`_colunas`),
    colunas repetitivas em corridas (`_rep`), textos muito longos em partes (`_partes`) e
    períodos idênticos a outro (`_igual`). Se o retrato não couber, níveis progressivos de corte
    são aplicados até caber (`meta.publication.nivel`): primeiro o que a página quase não mostra
    ou repete (detalhe dos gates aprovados, racionais das visões agregadas, detalhe da semana
    anterior, tabela do mandato, execuções antigas de backtest), depois os textos da pesquisa e,
    só nos dois últimos níveis, o histórico diário — até o nível 6 ficam ao menos 60 pregões em
    linhas diárias e 5 comentários do dia. Do backtest vão a execução escolhida e as mais
    recentes (as demais só na contagem). `data.json` também traz `meta.page_sha256`, a versão
    da página para a qual foi gerado.
  - `artifacts/painel/cdp_painel_local.html` — cópia autônoma com o retrato **completo** embutido,
    para abrir direto no navegador, offline (`--sem-local` não a grava).
  - `artifacts/painel/PAGINA_PUBLICADA.sha256` — a versão da página publicada por último no
    artifact. É gravado por `uv run python -m cdp painel --publicado` (que não gera nada) **só
    depois** de uma publicação bem-sucedida que incluiu `index.html`.
- O comando só lê o livro, a trilha e os relatórios (grava apenas esses arquivos) e imprime, em
  JSON, caminhos, tamanhos, SHA-256, maior linha, `data_hash`, `page_changed`, `index_written`
  e o bloco `artifact`: `publicavel`, `motivo`, `arquivos_para_ler`, `tamanho_dados`,
  `linhas_max`, `pagina_mudou`, `pagina_publicada` e `url`.
- **Página publicada × página local.** `pagina_mudou` compara a versão atual da página com
  `PAGINA_PUBLICADA.sha256` — não com o `index.html` local. Assim, se o template mudar e o
  `index.html` novo for gerado e commitado por quem não publica (você conferindo a saída, o
  Codex, uma execução sem a ferramenta `Artifact`, uma publicação recusada), `pagina_mudou`
  continua `true` em todas as rotinas seguintes até a página ser de fato publicada e registrada.
  A página publicada também compara a sua versão com `meta.page_sha256` dos dados e mostra
  "Página desatualizada" no topo quando diferem (ou quando o esquema dos dados é outro).
- **Link fixo**: a URL do artifact fica em `artifacts/painel/ARTIFACT_URL` (uma linha,
  versionada). O artifact é criado uma única vez, fora das rotinas, com a página (`index.html`)
  publicada junto do `data.json` (`files`); quem o cria grava `ARTIFACT_URL` e roda
  `uv run python -m cdp painel --publicado`. As skills `semanal`, `diario`, `risco` e
  `calibracao`, no fim de cada execução, geram o painel, fazem o commit e o **republicam no mesmo
  artifact** com a ferramenta `Artifact`: leem por inteiro `data.json` (e `index.html`, só
  quando `pagina_mudou` é `true`) e, com a `url` do arquivo, fazem nesta ordem um `read`, um
  `list` com `scope: "files"` e o `publish` com `files: {"data.json": "artifacts/painel/data.json"}`
  — mais `file_path: artifacts/painel/index.html` quando a página mudou ou quando a ferramenta
  recusa a atualização só com `files`. A listagem é obrigatória: a ferramenta só substitui um
  arquivo publicado que a sessão leu pelo caminho, viu numa listagem ou publicou (o `read` da URL
  devolve a página, não o `data.json`); sem ela, a atualização dos dados seria recusada. Se a
  recusa disser que `data.json` mudou desde a listagem (outra rotina publicou no meio), a skill
  lista de novo e publica uma única vez; nunca usa `force`. Depois de uma publicação que incluiu
  a página, a skill roda `cdp painel --publicado` e faz um commit só do marcador. Nunca criam um
  artifact novo: sem `artifacts/painel/ARTIFACT_URL`, pulam a publicação e dizem isso no resumo.
- **Tamanho.** A ferramenta de publicação exige que a mente leia por inteiro cada arquivo
  publicado. Com `artifact.publicavel: false` (dados acima de 260 KB ou linha acima de 1.500
  caracteres; página acima de 260 KB ou linha acima de 2.000 caracteres, quando ela mudou), as
  skills não leem nem publicam nada (não gastam contexto) e relatam o `motivo`.
- A skill `status` só informa a URL e a data do último commit de `data.json`.
- Sem a ferramenta `Artifact` na sessão (agendador do sistema com `claude -p`, Codex) ou se a
  ferramenta recusar/falhar, a skill pula a republicação e diz isso no resumo — os arquivos
  commitados continuam valendo e a próxima rotina com a ferramenta publica a versão nova (com a
  página, se ela ainda não tiver sido registrada como publicada).
- A pasta `artifacts/painel/` existe no repositório (com `.gitkeep`), então o `git add` das
  rotinas funciona mesmo quando o painel falha.
- O artifact é privado por padrão; compartilhar o link é decisão sua, no claude.ai.

## 11. Kill switch

- A skill `risco` liga o kill switch **somente** quando `cdp risk` traz uma ação
  `kill-switch: <motivo>` — gatilhos HARD do mandato (escada de drawdown em `hard_stop`/`stop_out`,
  stops de squeeze). O motivo é o texto do código.
- O kill switch só bloqueia risco novo (redução continua permitida) e nunca afrouxa limites. O
  stop de squeeze de um short escala para o livro inteiro: só redução e, no rebalanceamento
  seguinte, carteira reconstruída com gross × 0,5 (o corte de 50% daquele nome não é automático;
  revise-o). Regra em `docs/cdp/METODOLOGIA.md`, seção 7.
- **Só um humano desliga**, no terminal, depois de revisar:

  ```sh
  uv run python -m cdp kill-switch off --reason "<motivo da revisão>" --by "<seu nome>"
  ```

  As regras do projeto impedem o Claude de rodar esse comando. Depois do desligamento, o monitor
  não religa o kill switch pela mesma condição que você revisou (ela aparece como SOFT "já
  revisado por humano", com o bloco `revisao_humana` no relatório); só uma piora religa — estágio
  pior da escada de drawdown ou um short novo no stop.

## 12. Sem o app aberto: agendador do sistema (alternativa)

`scripts/cdp_run_task.sh` (macOS/Linux) e `scripts/cdp_run_task.ps1` (Windows) rodam uma skill sem
interface com `claude -p "/cdp:<skill>" --permission-mode acceptEdits`, gravando o log em
`logs/cdp/<tarefa>_<data_hora>.log` (pasta ignorada pelo git). Use **uma** das duas formas (app ou
agendador do sistema), nunca as duas.

- Trava contra execuções simultâneas: `semanal` e `diario` esperam até 60 minutos
  (`CDP_LOCK_WAIT_MIN`) que a rotina em andamento termine; as outras não esperam. Se a trava
  continuar ocupada, o script sai com código 75 (o agendador mostra a execução como não
  concluída) e não roda a skill.
- Calibração: o script roda o backtest (`reports/backtest/<hoje>/mensal`) **antes** de chamar a
  skill — no modo `-p`, uma tarefa em segundo plano morre quando a resposta termina.
- O `claude` precisa estar logado no usuário que roda o agendador (ou com `ANTHROPIC_API_KEY`).
  Não use `--bare`: ele não carrega plugins nem skills.
- No modo `-p` ninguém aprova pedidos: o que não estiver liberado no `.claude/settings.json` é
  negado e a skill relata no resumo. `CDP_CLAUDE_ARGS="--permission-prompts none"` deixa isso
  explícito.
- O painel (seção 10) é sempre gerado e commitado; a republicação no artifact só acontece se a
  ferramenta `Artifact` estiver disponível nessa execução — senão a skill pula e relata no log.

**Linux (cron)** — `crontab -e` (com `CRON_TZ`, se o seu cron suportar; senão, converta os
horários). O cron não recupera execuções perdidas com o PC desligado; o `diario` seguinte processa
os pregões pendentes.

```text
CRON_TZ=America/Sao_Paulo
30 8 * * 1    /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh status
7 11 * * 1-5  /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh semanal
37 12 * * 1-5 /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh semanal
30 13 * * 1-5 /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh risco
7 14 * * 1-5  /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh semanal
7 15 * * 1-5  /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh semanal
0 16 * * 1-5  /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh risco
22 19 * * 1-5 /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh diario
7 21 * * 1-5  /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh diario
15 9 1 * *    /caminho/MarketSummary-rotinas/scripts/cdp_run_task.sh calibracao
```

**macOS (launchd)** — um arquivo por tarefa em `~/Library/LaunchAgents/` (horário local do Mac),
com os mesmos horários da tabela do cron. Exemplo do fechamento diário, `com.cdp.diario.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.cdp.diario</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/voce/MarketSummary-rotinas/scripts/cdp_run_task.sh</string>
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

**Windows (Agendador de Tarefas)** — no PowerShell (sem administrador), ajuste `$repo` e rode o
bloco. As tarefas rodam com a sua sessão do Windows aberta (como o app), em janela oculta, também
na bateria, e são recuperadas assim que possível quando o horário foi perdido:

```powershell
$repo = "C:\Users\voce\MarketSummary-rotinas"   # pasta do clone (pode ter espaços)
$script = Join-Path $repo "scripts\cdp_run_task.ps1"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 6) -MultipleInstances IgnoreNew
$weekdays = "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
function Add-CdpTask([string]$name, [string]$task, [string[]]$days, [string]$at) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $repo `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" $task"
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $at
    Register-ScheduledTask -TaskPath "\CDP\" -TaskName $name -Action $action -Trigger $trigger `
        -Settings $settings -Force | Out-Null
}
Add-CdpTask "status"     "status"  @("Monday") "08:30"
Add-CdpTask "semanal"    "semanal" $weekdays "11:07"
Add-CdpTask "semanal-b"  "semanal" $weekdays "12:37"
Add-CdpTask "risco1330"  "risco"   $weekdays "13:30"
Add-CdpTask "semanal-c"  "semanal" $weekdays "14:07"
Add-CdpTask "semanal-d"  "semanal" $weekdays "15:07"
Add-CdpTask "risco1600"  "risco"   $weekdays "16:00"
Add-CdpTask "diario"     "diario"  $weekdays "19:22"
Add-CdpTask "diario2107" "diario"  $weekdays "21:07"
```

A calibração mensal precisa do `schtasks` (o `New-ScheduledTaskTrigger` não tem gatilho mensal).
Escreva o caminho do clone por extenso (o `--%` repassa a linha sem interpretar variáveis) e depois
aplique as mesmas configurações:

```powershell
schtasks --% /Create /TN "CDP\calibracao" /SC MONTHLY /D 1 /ST 09:15 /TR "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"C:\Users\voce\MarketSummary-rotinas\scripts\cdp_run_task.ps1\" calibracao"
Set-ScheduledTask -TaskPath "\CDP\" -TaskName "calibracao" -Settings $settings | Out-Null
```

Confira com `Get-ScheduledTask -TaskPath "\CDP\"`; o resultado de cada execução aparece em "Último
resultado" (75 = não iniciada porque outra rotina estava rodando) e no log em `logs\cdp\`.

## 13. Codex como mente

O Codex lê `AGENTS.md` e segue a mesma metodologia e os mesmos roteiros. Os passos das skills em
`plugins/cdp/skills/<skill>/SKILL.md` valem para ele trocando `claude-code` por `codex` (use
`--mind codex` na CLI e `"mind": "codex"` nos JSON). Para agendar, use o agendador do sistema com o modo não
interativo do Codex CLI (consulte a documentação do Codex para as flags) e um texto como os de
`docs/cdp/ROTINAS.md`. Não ligue as duas mentes no mesmo livro ao mesmo tempo.

## 14. Solução de problemas

| Sintoma | Causa provável e correção |
|---|---|
| `/cdp:diario` desconhecido na tarefa | plugin não instalado/ativado: `claude plugin list`; repita a seção 4; confira se a tarefa usa a pasta do clone |
| `uv: command not found` nas tarefas do app | o app foi aberto antes da instalação do uv: feche e reabra o app (o PATH novo só vale para processos novos) |
| Tarefa parada esperando aprovação | um comando fora das regras (seção 5): responda ao pedido na sessão parada, use "Accept edits" e, no Run now, "always allow" só para comandos seguros |
| "clone em desenvolvimento" no resumo | a pasta da tarefa não está na `main` ou tem código/configuração alterados sem commit: use um clone dedicado às rotinas (seção 3) |
| "sem sincronizar" ou push não feito | `git fetch` falhou (rede, token) ou `verify` não disse `ÍNTEGRO`: o commit ficou local; a próxima rotina com rede e trilha íntegra envia. Confira com `git status -sb` |
| Rotina parou: "outra máquina ou sessão gravou o livro" | o remoto tem commits em `book/`, `data/`, `reports/` ou `artifacts/` que o clone não tem — duas mentes ou dois clones gravando. Não faça merge/rebase do livro (a trilha é encadeada por hash): mantenha uma só mente; se os commits locais ainda não foram enviados e o remoto é o livro oficial, guarde-os (`git branch backup-AAAA-MM-DD`) e só então alinhe o clone com o remoto, com revisão humana |
| Push rejeitado com o remoto à frente só em código/docs | a sincronização seguinte faz `git pull --no-rebase --no-edit` e envia; à mão: `git fetch`, `git diff --name-only "HEAD...@{u}" -- book data reports artifacts` (vazio) e `git pull --no-rebase --no-edit && git push` |
| `dados não prontos` no fechamento | a fonte ainda não publicou o fechamento; o reforço das 21:07 ou o dia seguinte recupera |
| `verify` acusa hash divergente após clonar no Windows | fins de linha convertidos: confira o `.gitattributes` e clone de novo |
| Acentos estranhos / `UnicodeEncodeError` no Windows | `PYTHONUTF8=1` (já no `.claude/settings.json` e nos scripts); para o terminal, `chcp 65001` |
| `uv`/`claude` não encontrados no agendador do sistema | PATH mínimo do cron/launchd/Agendador: use caminhos absolutos ou ajuste `CDP_CLAUDE_BIN`; os scripts já incluem `~/.local/bin`; o erro fica no log |
| Execução marcada como "skipped" no app | o PC dormia, a execução anterior ainda rodava ou outra tarefa estava em andamento (ex.: risco das 16:00 durante a montagem semanal); as reservas da semanal e o reforço do diário cobrem os casos importantes |
| Decisão da semana perdida | o PC estava desligado entre 11:00 e 16:30 do primeiro pregão; a carteira anterior segue até a próxima semana |
| "painel não republicado" no resumo | `artifact.publicavel: false` (dados grandes demais para a leitura integral), `artifacts/painel/ARTIFACT_URL` ausente, sem a ferramenta `Artifact` na sessão (ex.: `claude -p`, Codex) ou recusa da ferramenta; os arquivos commitados valem. Para publicar à mão: abra uma sessão na pasta e peça "republique artifacts/painel/data.json (e index.html, se mudou) no artifact de artifacts/painel/ARTIFACT_URL" |
| Painel mostra "Não foi possível carregar data.json" | a página foi publicada sem o `data.json` ao lado: rode `uv run python -m cdp painel` e republique com `files: {"data.json": "artifacts/painel/data.json"}` no mesmo artifact; offline, abra `artifacts/painel/cdp_painel_local.html` |
| Link do painel sumiu ou mudou | `artifacts/painel/ARTIFACT_URL` ausente ou apagado: restaure a URL antiga nele (uma linha) e faça commit; as rotinas nunca criam um artifact novo (sem o arquivo, só pulam a publicação) |
| Kill switch religado logo depois de você desligar | só acontece por piora (estágio pior da escada ou short novo no stop): veja `revisao_humana` e os gatilhos HARD no relatório de risco |
