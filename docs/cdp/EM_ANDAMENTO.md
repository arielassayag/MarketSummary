# Em andamento — passagem de bastão entre sessões (qualquer app de IA)

Documento vivo. Quem encerra uma sessão de desenvolvimento atualiza este arquivo: o que mudou, o
que falta, riscos. Quem chega — no Claude Code, no Codex, no Gemini ou em outro app — lê aqui
antes de mexer em qualquer coisa (`AGENTS.md`, seção 1). Decisões já tomadas, com data e
motivo: `docs/cdp/DECISOES.md`.

Última atualização: 2026-10-06, terça-feira (correções do ensaio geral com o Codex como executor).

## Como continuar (qualquer app)

1. `uv sync --extra dev --extra ai` e `uv run python -m cdp estado --formato md` (fase do fundo,
   executor, pendências, incidentes, próximo passo).
2. Leia as tabelas abaixo; escolha uma frente sem dono ativo ou continue a sua.
3. Trabalhe em ramo próprio; nunca grave `book/`, `data/`, `reports/`, `artifacts/` (só o
   executor grava, pelas rotinas).
4. Antes de propor um commit: `uv run pytest tests/cdp -q` e `uv run ruff check .`.
5. Ao encerrar, atualize este arquivo (o que mudou, o que falta, riscos) e, se decidiu algo,
   acrescente a entrada em `docs/cdp/DECISOES.md`.

## O que já está entregue

| Área | O que existe | Onde ler |
|---|---|---|
| Calendário e execução | regra do dia de montagem (último pregão da semana na NYSE), prazo efetivo, execução no leilão de fechamento com capacidade de liquidez | `docs/cdp/EXECUCAO.md`, `src/cdp/calendar.py`, `src/cdp/portfolio/execucao.py` |
| Construção e risco | otimizador com meta de risco idiossincrático (90%) e piso (85%), escada de relaxamento, escada de drawdown, gatilhos de perda, limites de short | `docs/cdp/METODOLOGIA.md` |
| Cobertura | modelos abertos e preços-alvo de 12 meses de todo o universo (ações e ETFs) só com dados públicos, livro encadeado, placar | `docs/cdp/COBERTURA.md`, `uv run python -m cdp cobertura verify` |
| Camada da mente | notas por emissor, relatório semanal de resultado, pacote da mente para qualquer assistente, guia de estilo | `docs/cdp/NOTAS.md`, `docs/cdp/REPRODUZIR.md`, `docs/cdp/ESTILO.md` |
| Pré-início | abertura do livro na data de início, uma única vez, pela primeira rotina do executor | `cdp reinicio` (simulação por padrão) |
| Operação em qualquer app | `cdp estado`, `cdp rotinas` (gate, prompts, exportação), `cdp executor`, `cdp trava`, `cdp sincronizar`, `cdp publicar`, `cdp entrega`, skills neutras em `.agents/skills/` | `AGENTS.md`, `docs/cdp/AUTOMACAO.md` |
| Portal público | `cdp site construir/conferir`, `.github/workflows/cdp-site.yml` (GitHub Pages) | `docs/cdp/SITE.md` |
| Integração contínua | `.github/workflows/cdp-ci.yml` (lint, testes, integridade, rotinas, skills, portal da demonstração) | — |
| Documentação | `AGENTS.md` como fonte única, arquitetura, automação dentro do app de IA, teste de consistência; licenças (Apache-2.0 + CC BY 4.0, confirmadas pelo titular em 06/10/2026) e aviso legal | `docs/cdp/ARQUITETURA.md`, `tests/cdp/test_docs_consistencia.py` |
| Cronograma e construção (no ramo de integração, aguardando o commit) | stop de squeeze por nome, série de risco idiossincrático no monitor, kill switch desligado só por humano num terminal interativo, pedido de kill switch mesclável (`reports/risk/<data>/kill_switch_<HHMM>.yaml`, aplicado pela execução exclusiva seguinte ou por `cdp kill-switch aplicar-pedidos`; a agenda lista os pendentes) | `docs/cdp/EXECUCAO.md`, `docs/cdp/METODOLOGIA.md` |

## Correções do ensaio geral (06/10/2026, Codex como executor)

Feitas no código, nos roteiros e nas skills (suíte `tests/cdp` e ruff verdes):

- `weekly prepare` monta o briefing numa área temporária e promove de uma vez; falha no meio não
  trava a semana (briefing parcial antigo é afastado); cotação intradiária vazia é falha de coleta
  (análise no fechamento anterior); a agenda só conta briefing completo.
- Kill switch: `kill-switch off` exige a senha do operador (hash fora do repositório;
  `cdp kill-switch senha`), e `CDP_HARNESS`/`CODEX_*`/`ANTIGRAVITY_*` contam como contexto de
  agente; kill switch antes da carteira inaugural sai como status estruturado; prazo vencido no
  `weekly decide` sai como JSON (`prazo_vencido`), com texto próprio da inaugural.
- Modo ensaio: `CDP_AGORA` (relógio do cenário), `CDP_ENSAIO_SUBSTITUTO=1` (substituto de dados
  rotulado) e commit local com o trailer `CDP-Ensaio` (um clone com ensaio nunca publica).
- Mente: os validadores e as publicações recusam `mind` diferente da execução (`--mind` ou
  `CDP_HARNESS`), salvo rascunho entregue; exemplos com a mente da execução; o Codex é o app das
  rotinas (`configs/cdp/executor.yaml`, documentação neutra); `CDP_EXECUTOR` inválido é recusado.
- Dados: brutos volumosos da CVM e da SEC fora do git (índice versionado); portal publica só o
  último retrato completo da cobertura; BDI com tempo-limite curto e parada após 3 datas com
  falha; manchetes com padrão de instrução vão para a quarentena; filtro de relevância de notícias.
- Texto ao investidor: relatórios semanal e diário em pt-BR (nomes de empresas, rótulos, horário
  de Brasília, sem o nome do app); avisos técnicos de dados numa frase só; VOL_TARGET contra a meta
  aplicada; "(USD)" só nos benchmarks cotados em dólar e validador que recusa "em dólares" para
  fato em moeda local; nomes com acento (`configs/cdp/nomes.yaml`); portão G20 de plausibilidade
  do alvo (consenso, cenários, margem do G11); ADR com o alvo da própria classe (PBR ← PETR3).

Pendências que dependem do titular ou do commit (não são código):

- `git rm -r --cached artifacts/painel` mantendo `.gitkeep` (a pasta passou a ser ignorada; o HTML
  antigo com a fonte proprietária removida ainda está versionado) e decidir o histórico público
  antes de 09/10 (commits da rodada anterior e da calibração: ramo novo ou aceitar).
- Logotipo e imagem de compartilhamento com "ASSET MANAGEMENT" (arte da marca) e
  `fund.minds` (valor do mandato, entra no hash da configuração da gênese).
- Fora do escopo desta passagem: páginas estáticas por ativo (SEO), identidade visual dos
  relatórios HTML e da página de dados, gráfico de potencial no celular, tabela anual do lucro
  residual na memória de cálculo e arquivo das planilhas Damodaran no retrato.

## Frentes em andamento (2026-10-06)

| Frente | Estado | Próximo passo |
|---|---|---|
| Portal: aba "Modelo aberto" da cobertura e "Auditoria e reprodução"; perfil "site" do painel sem cortes | em desenvolvimento | revisar no portal real montado de uma cópia do livro; no portal da demonstração, só depois de a demonstração gerar cobertura e notas (integração pendente abaixo) |
| Calibração da cobertura (parâmetros de valuation e arquétipos) | em desenvolvimento | suíte da cobertura verde; retrato de 08/10 conferido por `cdp cobertura verify` |
| Skills, plugin e roteiros no envelope gate → `cdp sincronizar` → roteiro → `cdp publicar` → `cdp trava liberar`; exportação para as tarefas agendadas do Codex e do Antigravity (`--alvo codex`, `--alvo gemini`) | em desenvolvimento | `uv run python -m cdp skills verificar`, versão do plugin, tabela de `docs/cdp/ROTINAS.md` gerada |
| Construção: otimizador robusto na demonstração, recalibração de liquidez e custos para o PL de US$ 1,0 mi | em desenvolvimento | ensaio geral numa cópia do livro |
| Ativação do mandato em `configs/cdp/fund.yaml` (regra do último pregão da semana na NYSE, seção `execution`, bloco de construção, liquidez e custos para o PL de US$ 1,0 mi) | **aplicada em 06/10/2026** (mescla chave a chave conferida semanticamente; `agenda --agora 2026-10-09T11:07` dá `acao: montar` e prazo efetivo 15:00) | — |

## Cronograma até a primeira montagem regular (horário de Brasília)

| Data | O que acontece | Quem |
|---|---|---|
| ter 06/10 | integração das frentes acima; push em `main` só com a suíte e o ruff verdes (licenças só depois da confirmação do titular) | desenvolvimento |
| logo depois do push de integração (no máximo qua 07/10) | **preparar o PC executor para o novo envelope** (as skills e o plugin passam a começar por `cdp rotinas gate`; sem a identidade do clone, toda rotina responde "Sem execução: identidade deste ambiente desconhecida" — e uma rotina não consegue se registrar sozinha): no clone das rotinas do PC (`docs/cdp/LOCAL.md`, seção 3), `git pull --ff-only` e `bash scripts/cdp_setup_local.sh` (registra `cdp executor registrar --como local-pc --harness claude-code`, testa o push em `main` e no ramo `cdp-trava`, reinstala o plugin); recriar as tarefas do app desktop pela tabela de `uv run python -m cdp rotinas exportar --alvo claude-desktop` — as 12, inclusive `cdp-cobertura` (segunda a quinta, 22:37), `cdp-risco-1603`, `cdp-diario-sabado` e as reservas `cdp-semanal-b`/`-c`/`-d` (12:07, 13:07, 14:07); "Run now" em `cdp-status` e conferir em `uv run python -m cdp estado --formato md` que `executor.sou_o_executor` é verdadeiro | operador |
| qua 07/10 | **regra do ramo `main`** no GitHub (Settings → Rules → Rulesets): bloquear force push e exclusão, **sem** exigir pull request, ramo `cdp-trava` livre; conferir com `gh api repos/arielassayag/MarketSummary/rulesets` (hoje a lista vem vazia: `main` sem proteção) — obrigatória antes de qualquer executor fora do Claude Code e antes da troca de 11/10 | titular |
| qua 07/10 | rotinas da nuvem do Claude Code criadas **desligadas** no ambiente "CDP" e ligadas no "CDP-ensaio" (`CDP_ENSAIO=1`; nomes "CDP · <tarefa> (…) · ensaio"), em paralelo ao PC local | operador |
| qui 08/10, até 18:00 | código completo, revisado, suíte verde; ativação do mandato publicada | desenvolvimento e titular |
| qui 08/10, noite | 19:22 rotina diária com o retrato da cobertura de 08/10; 22:37 notas de cobertura | executor (PC local) |
| sex 09/10 | **carteira inaugural**: 11:07 pesquisa e preparação, decisão até o prazo efetivo (15:00), execução no leilão de fechamento; 19:22 efetivação, primeiro registro diário, relatório semanal, portal. Às 11:00, conferir o uso do plano em claude.ai/settings/usage: o ensaio `cdp-semanal*` da nuvem roda ao mesmo tempo, na mesma conta; se a janela de uso estiver apertada, desligar as rotinas `cdp-semanal*` do CDP-ensaio antes das 11:07 (a carteira real tem prioridade) | executor (PC local); operador |
| sáb 10/10, 10:07 | repescagem do fechamento, se necessário | executor |
| dom 11/10, 10:00 | **troca do executor para a nuvem** (`cdp executor transferir --para claude-cloud`), depois de conferir o ensaio; **desligar as rotinas "· ensaio" do ambiente CDP-ensaio** (senão continuam rodando, cerca de 46 disparos por semana, e montam uma carteira paralela toda sexta na mesma conta); o PC fica como reserva quente por duas semanas, com as tarefas do app desktop desligadas (`docs/cdp/AUTOMACAO.md`, seção 13) | titular |
| seg 12/10 | feriado na B3 com a NYSE aberta (pregão de dados); primeiras rotinas reais na nuvem | rotinas |
| qui 15/10 | fechamento, retrato da cobertura e notas na nuvem | rotinas |
| sex 16/10 | **primeira montagem regular** (com limites de giro), execução no leilão de fechamento e relatório semanal | rotinas |

## Riscos conhecidos

- Rotinas da nuvem do Claude Code são um recurso em prévia: o formato da API pode mudar e a
  documentação só traz limites por hora — conferir o uso em claude.ai/settings/usage. Sem a
  conexão do GitHub, execuções são puladas (72 h depois, a rotina é desligada).
- **PC executor sem a identidade do clone**: depois do push de integração, se o PC não rodar
  `scripts/cdp_setup_local.sh` e não recriar as tarefas, as rotinas de quinta à noite (fechamento
  e notas) e as de sexta (11:07 a 14:07) respondem "Sem execução" e a decisão da carteira
  inaugural se perde (`decisao_perdida`). Ver a linha do cronograma logo depois do push.
- **`main` sem proteção no GitHub** (nenhuma regra hoje): os apps com acesso total (Codex,
  Antigravity) e o push da nuvem ficam limitados só pelo código (`cdp publicar` nunca força) até
  a regra do ramo existir.
- Até a ativação do mandato, `configs/cdp/fund.yaml` mantém a regra antiga de dia de montagem
  (prazo 16:30, sem relatório semanal na sexta à noite, próxima montagem na terça 13/10); a
  ativação precisa entrar antes de 09/10 (o portal filtra backtests pela regra vigente).
- Kill switch pedido pela rotina de risco enquanto outra rotina segura a trava, em máquinas
  separadas (nuvem): o relatório e o pedido (`reports/risk/<data>/kill_switch_<HHMM>.yaml`) saem
  na hora, mas o kill switch só entra no livro na execução exclusiva seguinte (montagem ou
  fechamento), que aplica os pedidos pendentes antes de gravar qualquer coisa.
- Ensaio na nuvem em paralelo ao executor: consome a mesma capacidade do plano (cerca de 46
  disparos por semana; na sexta, uma montagem completa sem publicar) — por isso a conferência do
  uso na sexta e o desligamento no domingo.
- Tarefas agendadas do Codex e do Antigravity rodam no computador (app aberto); o Antigravity
  usa um modelo fixo nas tarefas agendadas e a sua documentação pública ainda é escassa —
  ensaiar antes de confiar.
- `artifacts/painel/` passou a ser ignorada pelo git (cópia local do painel); o
  `cdp_painel_local.html` antigo (cerca de 2,3 MB, texto de pesquisa anterior à data de início)
  ainda é versionado até o `git rm -r --cached artifacts/painel` do commit, e até lá é a única
  exceção nominal do teste de termos proibidos. `cdp site conferir` falha se um termo vedado
  aparecer em qualquer arquivo do portal.
- **Licenças confirmadas pelo titular em 06/10/2026**: `LICENSE` (Apache-2.0, todo o código do
  repositório, inclusive o app Fechamento), `LICENSE-docs` (CC BY 4.0, textos e conteúdos do
  CDP) e `NOTICE` (marca reservada) — ver `docs/cdp/DECISOES.md`.
- **Enquadramento regulatório do portal** (Resoluções CVM nº 20/2021 e nº 175/2022): o portal
  público e indexado mostra ratings (Compra, Neutro, Venda), preços-alvo e os termos "fundo",
  "gestão" e "Asset Management"; um aviso legal não muda a natureza do conteúdo. Revisão
  jurídica pendente antes da publicação de 09/10 (`docs/cdp/DECISOES.md`); o aviso legal das
  docs foi reescrito como descrição (sem conclusões jurídicas).

## Integração pendente com outros donos

- `configs/cdp/site.yaml` (sem dono nesta onda): depois da confirmação do titular,
  `licenca: {codigo: Apache-2.0, conteudo: CC-BY-4.0}` (hoje `null`: o schema.org e
  `dados/datapackage.json` saem sem licença) e `aviso_legal` igual ao aviso legal fixo do
  `README.md` (hoje mais curto); depois, estender `test_licenses_and_disclaimer` a esse arquivo.
- Um só aviso legal no código: hoje há redações próprias em `PAPER_TRADING_TEXT`
  (`src/cdp/workflow/reports.py`), no texto de reserva de `src/cdp/workflow/painel_template.html`,
  em `AVISO_CVM` (`src/cdp/workflow/painel_cobertura.py`) e em `DISCLAIMER`
  (`src/cdp/research/notas.py`) — todas devem derivar do texto de `configs/cdp/site.yaml`.
- Revisão jurídica (titular) e, conforme o resultado, os donos do portal e da cobertura: rótulos
  de rating que não soem como recomendação (por exemplo, posição em relação ao valor do modelo),
  sem "Asset Management", "gestão" e "fundo" nos textos do portal, ou `noindex` nas páginas da
  cobertura.
- Portal e painel com repositório, endereço e título lidos de `configs/cdp/site.yaml` e
  `configs/cdp/fund.yaml`, sem constantes fixas: `REPO` e `PORTAL_URL`
  (`src/cdp/workflow/painel.py`), `REPOSITORIO` (`src/cdp/workflow/painel_cobertura.py`),
  cabeçalho do portal em `src/cdp/site.py` e do painel em
  `src/cdp/workflow/painel_template.html`; `tests/cdp/test_painel.py` derivando o endereço de
  `configs/cdp/site.yaml`. Também um comentário no bloco `>>> marca` do template dizendo que a
  marca embutida fica fora da Apache-2.0 (`NOTICE`).
- `cdp reinicio --executar` abrindo um livro vazio com a gênese (ou um comando novo de
  preparação da cópia, como o previsto no desenho da replicação), para uma cópia do projeto
  começar com `book/genese.json` e o evento `FUND_GENESIS` (`docs/cdp/REPLICAR.md`, seção 3).
- Guarda nos validadores da pesquisa e das notas que recuse, nas evidências e no texto livre, a
  fonte proprietária removida e as ferramentas pagas de dados (hoje a guarda só confere o
  endereço das URLs); `tests/cdp/test_docs_consistencia.py` já varre `artifacts/`, `reports/` e o
  livro a partir da data de início.
- `run_demo` (`src/cdp/workflow/demo.py`) gerar a cobertura sintética (`cdp.cobertura.demo`) e
  notas (`write_demo_note`, em `src/cdp/workflow/notas.py`) nas sextas da demonstração — dono:
  cobertura e mente. Sem isso, o portal da demonstração (DADOS SIMULADOS) sai sem cobertura e sem
  notas.
- `src/cdp/rotinas.py` (prompts gerados): "use nada (ensaio)" e "use nada (o executor publica)"
  → "não faça nada (ensaio: nada é publicado)" e "não faça nada: o executor publica"; depois,
  `uv run python -m cdp skills sincronizar` e exportações de novo.
- `docs/cdp/REPRODUZIR.md`: retirar a seção em inglês (tudo em português) e ajustar o teste que
  a exige.
- `GEMINI.md` (sem dono nesta onda; **antes do push**): hoje diz que o caminho sem supervisão é
  o GitHub Actions ou o agendador "sem credencial de escrita" e aponta para a seção 5 de
  `docs/cdp/AUTOMACAO.md` (que agora é o Codex). Quem seguir isso não configura a credencial de
  push e a trava (falha fechada) barra todo escritor exclusivo. Texto certo: sem supervisão =
  tarefas agendadas do Antigravity ou `agy`/`gemini -p` pelo agendador do sistema, num clone
  dedicado com credencial de push em `main` e no ramo `cdp-trava` (seção 6); IA no Actions só no
  apêndice A. O teste `test_gemini_md_points_to_the_app_scheduler` já confere (hoje marcado como
  falha esperada). `CLAUDE.md`: citar as saídas da mente (`AGENTS.md`, seção 3).
- Redação antiga do dia de montagem em docstrings de `src/cdp/data/intraday.py` e
  `src/cdp/data/live_refresh.py`; o backtest (`src/cdp/backtest/engine.py`) ainda usa a regra
  antiga de dia de montagem.
- "A mente (Claude Code ou Codex)" em `docs/cdp/METODOLOGIA.md`, `docs/cdp/TESE.md` e em
  docstrings da camada da mente → "qualquer app de IA".
- Workflows: passo `name: Checkout` → `name: Baixar o repositório`.
