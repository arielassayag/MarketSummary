# Rotinas agendadas do CDP — Cabra da Peste

As rotinas do CDP rodam **dentro do app de IA** de quem opera, com a capacidade do próprio plano:
o app agenda a tarefa, abre o repositório, lê `AGENTS.md` e segue o roteiro. No nosso caso, o app
é o **Claude Code**, com as rotinas na nuvem de claude.ai/code; este guia ensina, passo a passo,
a fazer o mesmo no **Codex** e no **Gemini** (Antigravity). O projeto se comporta igual em
qualquer um deles: o que decide é o código (gate, trava, sincronização e publicação pela CLI), o
procedimento é o mesmo roteiro neutro (`docs/cdp/playbooks/`) e o prompt de cada tarefa sai
pronto de `cdp rotinas`. Detalhes de cada app, segurança, monitoramento e troca de executor:
`docs/cdp/AUTOMACAO.md`. PC local: `docs/cdp/LOCAL.md`.

## 1. O que roda e quando

Fonte única: `configs/cdp/rotinas.yaml`. Tabela gerada por
`uv run python -m cdp rotinas exportar --alvo markdown` (não edite à mão; o teste confere):

<!-- inicio: tabela gerada por `cdp rotinas exportar --alvo markdown` -->
| Tarefa | Quando (Brasília) | UTC | Roteiro | Grava |
|---|---|---|---|---|
| `cdp-status` | segundas, 08:30 | `30 11 * * 1` | `docs/cdp/playbooks/STATUS.md` | não |
| `cdp-semanal` | dias úteis, 11:07 | `7 14 * * 1-5` | `docs/cdp/playbooks/SEMANAL.md` | sim (trava exclusiva) |
| `cdp-semanal-b` | dias úteis, 12:07 | `7 15 * * 1-5` | `docs/cdp/playbooks/SEMANAL.md` | sim (trava exclusiva) |
| `cdp-semanal-c` | dias úteis, 13:07 | `7 16 * * 1-5` | `docs/cdp/playbooks/SEMANAL.md` | sim (trava exclusiva) |
| `cdp-semanal-d` | dias úteis, 14:07 | `7 17 * * 1-5` | `docs/cdp/playbooks/SEMANAL.md` | sim (trava exclusiva) |
| `cdp-risco-1330` | dias úteis, 13:30 | `30 16 * * 1-5` | `docs/cdp/playbooks/RISCO.md` | só arquivos novos |
| `cdp-risco-1603` | dias úteis, 16:03 | `3 19 * * 1-5` | `docs/cdp/playbooks/RISCO.md` | só arquivos novos |
| `cdp-diario` | dias úteis, 19:22 | `22 22 * * 1-5` | `docs/cdp/playbooks/DIARIO.md` | sim (trava exclusiva) |
| `cdp-diario-reforco` | dias úteis, 21:07 | `7 0 * * 2-6` | `docs/cdp/playbooks/DIARIO.md` | sim (trava exclusiva) |
| `cdp-diario-sabado` | sábados, 10:07 | `7 13 * * 6` | `docs/cdp/playbooks/DIARIO.md` | sim (trava exclusiva) |
| `cdp-cobertura` | segunda a quinta, 22:37 | `37 1 * * 2-5` | `docs/cdp/playbooks/COBERTURA.md` | sim (trava exclusiva) |
| `cdp-calibracao` | dia 1 de cada mês, 09:15 | `15 12 1 * *` | `docs/cdp/playbooks/CALIBRACAO.md` | só arquivos novos |
<!-- fim da tabela gerada -->

- **Montagem semanal** (`cdp-semanal` e reservas): age só no **dia de montagem** — o último
  pregão da semana na NYSE (sexta-feira, ou o dia útil anterior em feriado nos EUA) e a data de
  início do mandato (carteira inaugural). Coleta todos os dados até o momento, pesquisa, decisão
  do PM, validação e decisão autônoma antes do **prazo efetivo** (`semanal.prazo_efetivo` em
  `cdp agenda`: em geral 15:00; mais cedo nos fechamentos antecipados dos EUA), e a tese de
  investimento da carteira decidida. A execução hipotética é no leilão de fechamento. As reservas
  retomam de onde a principal parou; nos outros dias, o gate sai sem chamar o modelo.
- **Risco** (13:30 e 16:03): monitor intradiário; kill switch só por gatilho HARD do código.
- **Fechamento diário** (19:22, reforço às 21:07, repescagem no sábado às 10:07): registro do
  fechamento, comentário e relatório do dia, tese pendente da semana corrente, um relatório
  semanal de resultado para cada dia de montagem pendente (do mais antigo ao mais recente,
  inclusive sem decisão gravada) e o retrato diário da cobertura.
- **Cobertura** (segunda a quinta, 22:37): notas de pesquisa por emissor, até 12 por execução,
  na fila do código, só com fontes públicas.
- **Estado** (segundas, 08:30): só leitura.
- **Calibração** (dia 1, 09:15): grava só arquivos novos em `reports/backtest/`; backtest mensal
  comparado com o anterior, mudanças de mandato só como proposta.

**Sexta-feira (dia de montagem).** 11:07: coleta, pesquisa e decisão antes do prazo efetivo
(reservas às 12:07, 13:07 e 14:07); leilão de fechamento: execução hipotética da carteira nova;
19:22 (reforço às 21:07): registro do fechamento, comentário do dia, relatório semanal de
resultado (mudanças da carteira, resultado e atribuição da semana e desde o início) e retrato da
cobertura. De segunda a quinta: fechamento às 19:22 e notas de pesquisa às 22:37.

**Antes da data de início do mandato** (`fase: "pre_inicio"` em `cdp agenda`), a montagem e o
risco saem no gate; o fechamento diário só atualiza a base de mercado, roda o retrato da
cobertura quando pendente e publica; as notas de pesquisa seguem normalmente. A primeira rotina
que gravar com `reinicio.pendente: true` abre o livro na data de início (`cdp reinicio`, uma vez,
seção "Pré-início" de `docs/cdp/playbooks/DIARIO.md`).

## 2. Como cada execução funciona (igual em qualquer app)

1. `uv sync --frozen --extra dev --extra ai`
2. `uv run python -m cdp rotinas gate --tarefa <tarefa> --adquirir` — o código diz se há o que
   fazer, se este ambiente é o executor designado e, nos escritores exclusivos, pega a trava
   distribuída (ramo `cdp-trava`). Sem trabalho, a execução termina sem gastar o modelo. **Uma vez
   só por execução.**
3. `uv run python -m cdp sincronizar --executar` — o código decide se pode seguir (o remoto mudou o
   livro? parar).
4. O roteiro da tarefa, com a mente do app (`claude-code`, `codex` ou `gemini`).
5. `uv run python -m cdp publicar --tarefa <tarefa> --mensagem "CDP: …" --execucao <execucao> --trava <trava.id> --mente <mente>`
   — integridade, executor e trava conferidos, commit do que a execução gravou (nos escritores
   exclusivos, também o que uma execução anterior interrompida deixou no clone), push em `main`,
   nunca force.
6. `uv run python -m cdp trava liberar --id <trava.id>`, sempre.

Os passos 1 a 3, 5 e 6 ficam nas skills e nos prompts; o passo 4 é o roteiro, idêntico para
todos. Skills: `.claude/skills/cdp-*` (Claude Code, inclusive na nuvem), `.agents/skills/cdp-*`
(Codex, Gemini, Antigravity e outros; mesmo conteúdo, gerado por
`uv run python -m cdp skills sincronizar --claude`) e o plugin `cdp` (`/cdp:<skill> <tarefa>`, PC
local). Quando o app protege `.git` no sandbox, `scripts/cdp_rotina.sh` faz os passos de git por
fora e o prompt avisa a mente (modo executor). As tarefas de leitura (`cdp-status`) e as
compartilhadas (risco, calibração) não pegam a trava.

## 3. Claude Code — rotinas na nuvem

Passo a passo completo em `docs/cdp/AUTOMACAO.md`, seção 3:

1. Plano com rotinas e o app GitHub do Claude conectado ao repositório (sem a conexão, as
   execuções são puladas; depois de 72 h, a rotina é desligada).
2. Ambiente **CDP** em claude.ai/code (rede total; `CDP_EXECUTOR=claude-cloud`,
   `CDP_HARNESS=claude-code`, `TZ=America/Sao_Paulo`, `PYTHONUTF8=1`, `BASH_DEFAULT_TIMEOUT_MS`,
   `BASH_MAX_TIMEOUT_MS`; nenhum segredo).
3. Gere os prompts: `uv run python -m cdp rotinas exportar --alvo claude-routines --formato md`
   (texto para a interface) ou `--saida rotinas.json` com `--ambiente <id>` (corpos da API).
4. Uma rotina por linha da tabela: Routines → New routine → **Cloud**, repositório
   `arielassayag/MarketSummary`, ambiente CDP, o prompt da tarefa e a agenda. `cdp-cobertura` e
   `cdp-calibracao` precisam do cron exato: crie pela API ou ajuste com `/schedule update`.
   Deixe-as **desligadas** até a troca de executor.
5. "Run now" numa tarefa sem pendência (o gate sai cedo) e leia a transcrição; faça o ensaio
   completo no ambiente CDP-ensaio.
6. Troca de executor para `claude-cloud` (`docs/cdp/AUTOMACAO.md`, seção 13) e ligue as rotinas.

A nuvem não instala plugins: as rotinas usam as skills do projeto (`.claude/skills/cdp-*`) e o
prompt gerado. Rotinas sem supervisão **nunca publicam artifacts**: o portal público é o site no
GitHub Pages, montado pelo GitHub Actions a cada push (`docs/cdp/SITE.md`).

## 4. Claude Code — app desktop

No PC, com o app aberto: `docs/cdp/LOCAL.md`. Tabela das tarefas, com a instrução de cada uma
(o comando da skill **com o id da tarefa**, para o gate conferir o horário certo):

```sh
uv run python -m cdp rotinas exportar --alvo claude-desktop
```

## 5. Codex — tarefas agendadas do app (o app das rotinas; passo a passo)

As tarefas agendadas do app desktop do Codex rodam no seu computador, com o app aberto, e herdam
o sandbox padrão. Para sincronizar, fazer commit e push pelo código, o Codex precisa de rede e
de escrita em `.git`: use **acesso total numa conta de usuário e num clone dedicados**
(`docs/cdp/AUTOMACAO.md`, seção 5).

1. Conta do sistema e clone dedicados; `uv sync --extra dev --extra ai`; credencial do Git com
   push em `main` e no ramo `cdp-trava`. O script de preparação testa os dois
   (`CDP_HARNESS=codex bash scripts/cdp_setup_local.sh`; `docs/cdp/LOCAL.md`, seção 3).
2. Identidade do clone: `uv run python -m cdp executor registrar --como local-pc --harness codex`
   (o script de preparação já a registra).
3. `~/.codex/config.toml` dessa conta (nunca no repositório). As variáveis entram pela tabela
   `set` de `[shell_environment_policy]`:

   ```toml
   sandbox_mode = "danger-full-access"
   approval_policy = "never"

   [shell_environment_policy]
   inherit = "all"
   set = { CDP_HARNESS = "codex", TZ = "America/Sao_Paulo", PYTHONUTF8 = "1" }
   ```

   Entre com a conta do plano (`codex login`).
4. No app, abra o clone como projeto e use a **pasta do projeto** (sem worktree: a identidade e
   a trava são do clone).
5. Gere as tarefas: `uv run python -m cdp rotinas exportar --alvo codex --formato md` — um bloco
   por tarefa, com o nome, a agenda (RRULE no horário de Brasília) e o prompt a colar. Crie uma
   tarefa agendada por bloco.
6. Execute agora uma tarefa sem pendência (resposta "Sem execução: …") e confira
   `uv run python -m cdp estado --formato md`.

**Limites:** só com o computador ligado e o app aberto; as tarefas agendadas da web não acessam
o repositório e o Codex Cloud não agenda tarefas. Sem acesso total, use o Codex CLI pelo
agendador do sistema (o script publica fora do sandbox):
`uv run python -m cdp rotinas exportar --alvo cron --harness codex`.

## 6. Gemini — Antigravity (passo a passo)

O Gemini CLI não atende mais os planos de consumo desde 18/06/2026 (exige chave paga ou Vertex);
pelo plano Google, use o **Antigravity** (`docs/cdp/AUTOMACAO.md`, seção 6).

**Melhor opção — Antigravity CLI (`agy`) pelo agendador do sistema:**

1. Conta do sistema e clone dedicados, com push em `main` e no ramo `cdp-trava`.
2. Instale o `agy` pelo instalador oficial e entre **uma vez**, de forma interativa, com a conta
   Google do plano.
3. Identidade: `uv run python -m cdp executor registrar --como local-pc --harness antigravity`.
4. Agendador: `uv run python -m cdp rotinas exportar --alvo cron --harness agy` (ou
   `--alvo launchd` / `--alvo windows`, com `--harness agy`). Cada linha chama
   `scripts/cdp_rotina.sh <tarefa> --harness agy`, que faz a prévia do gate (sem trabalho, nenhuma
   chamada de modelo) e roda o `agy` com o prompt da tarefa.
5. Teste sem rodar o modelo: `scripts/cdp_rotina.sh cdp-status --harness agy --seco`; depois, um
   ensaio completo.

**Tarefas agendadas do app Antigravity (experimental, só tarefas leves):** o modelo dessas
tarefas é fixo (um modelo Flash) e não pode ser escolhido. Use-as só para `cdp-status` e
`cdp-risco-1330`/`cdp-risco-1603`; a montagem, o fechamento, as notas e a calibração ficam no
`agy` pelo agendador do sistema (acima). Uma tarefa nunca roda pelos dois caminhos ao mesmo
tempo: cada id fica em um só agendador. Gere os blocos com
`uv run python -m cdp rotinas exportar --alvo gemini --formato md` (nome, cron no horário de
Brasília e o prompt) e crie uma tarefa agendada só para os blocos dessas tarefas leves, no
projeto do clone, com permissão para rodar comandos e acessar a rede sem perguntar.
**Gemini CLI com chave paga:**
`uv run python -m cdp rotinas exportar --alvo cron --harness gemini`. **Jules:** agenda só com
cadência diária ou semanal, sem horário exato, e entrega por pull request — não serve aos
escritores do livro.

## 7. Uma mente por vez

Só o executor designado em `configs/cdp/executor.yaml` grava o livro; nos outros ambientes, o gate
sai sem gravar nada. Ligue as rotinas de **um** app por vez e troque de app pela troca de
executor (`docs/cdp/AUTOMACAO.md`, seção 13; `uv run python -m cdp executor janela` diz se é um
bom momento). Para conferir a agenda e os prompts:

```sh
uv run python -m cdp rotinas listar
uv run python -m cdp rotinas proximas --n 12
uv run python -m cdp rotinas prompt --tarefa cdp-diario --harness codex
uv run python -m cdp rotinas verificar
uv run python -m cdp skills sincronizar --claude --verificar
```

O último confere as skills neutras (`.agents/skills/`) **e** a cópia do Claude Code
(`.claude/skills/`, a que as rotinas na nuvem usam). Depois de mudar `configs/cdp/rotinas.yaml`,
regenere as duas com `uv run python -m cdp skills sincronizar --claude`.

## 8. GitHub Actions: só integração contínua e portal

O GitHub Actions roda a integração contínua (`cdp-ci.yml`) e publica o portal (`cdp-site.yml`),
sem IA. Rodar a mente no Actions é só uma alternativa opcional
(`docs/cdp/AUTOMACAO.md`, apêndice A).

## 9. Sem app com acesso ao repositório

Qualquer passo da mente (pesquisa, decisão do PM, tese, nota por emissor, comentários diário e
semanal) pode ser feito em qualquer assistente de IA — ChatGPT, Gemini, Claude ou outro — pelo
pacote autocontido de `cdp mente pacote`, com o JSON devolvido validado pela mesma CLI
(`docs/cdp/REPRODUZIR.md`).
