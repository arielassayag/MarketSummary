# CDP — Cabra da Peste · Arquitetura

> Carteira simulada long/short de ações da América Latina, base USD, PL inicial de US$ 1,0 mi,
> **neutra em mercado**, volatilidade-alvo ex-ante de **5% a.a. (banda 3%–7%)**. A carteira é
> montada no **último pregão da semana na NYSE** (sexta-feira, ou o pregão anterior em feriado
> nos EUA), decidida antes do fechamento e executada no **leilão de fechamento**. A decisão é
> autônoma, sob gates determinísticos; todo número sai de código testado, só com dados públicos.

Este documento mostra como as peças se encaixam. Os números do mandato e dos limites vivem em
`configs/cdp/fund.yaml` e estão explicados em `docs/cdp/METODOLOGIA.md` (risco, alpha,
construção) e `docs/cdp/EXECUCAO.md` (prazo, leilão, capacidade e custos); a operação em
qualquer app de IA está em `AGENTS.md` e `docs/cdp/AUTOMACAO.md`.

## 1. Princípios

1. **Números só em código testado.** Retornos, riscos, rankings, pesos, custos, preços-alvo e
   contribuições saem de Python determinístico. A IA (a "mente") produz apenas juízos
   qualitativos estruturados e textos em JSON validado por schema, que citam fatos por
   `{{fact:id}}`.
2. **Só dados públicos e modelos abertos.** CVM, SEC EDGAR, B3, bancos centrais e institutos de
   estatística, RI das empresas, emissores de ETF, Damodaran, Yahoo Finance (consenso público
   rotulado) e notícias públicas. Cada insumo guarda fonte, URL, datas e SHA-256; qualquer
   pessoa refaz as contas (`docs/cdp/REPRODUZIR.md`).
3. **IA só aperta, nunca afrouxa.** As visões da mente inclinam o alpha dentro de um teto pequeno
   e podem *restringir* risco (proibir short ou long, reduzir peso). Nunca ampliam o mandato.
4. **Alpha puro.** O alpha é ortogonalizado aos fatores de risco e a construção busca risco
   idiossincrático: meta de 90% da variância (alerta) e piso de 85% (bloqueio), medidos em dois
   modelos de risco (`docs/cdp/METODOLOGIA.md`, seção 4.5).
5. **Liquidez, execução e short squeeze são restrições de primeira classe**: capacidade do leilão
   de fechamento, dias para liquidar, aluguel e vetos de short entram no otimizador e na
   compliance, não só nos relatórios.
6. **Decisão autônoma vinculada por hash** à proposta, ao snapshot, ao mandato, à pesquisa, à
   decisão estruturada do PM e aos gates de risco. Falha HARD de compliance nunca é executada: a
   escada cai para alternativas mais conservadoras (só-quant, manter a carteira).
7. **Escritor único.** Só o executor designado (`configs/cdp/executor.yaml`) grava o livro; a
   publicação passa por `cdp publicar` com trava distribuída e escopo de caminhos.
8. **Offline-first e sem look-ahead.** Testes e demonstração rodam sem internet, com dados
   sinalizados "DADOS SIMULADOS". Backtests e modelos só usam informação publicada até a data;
   sinais de retrato atual são marcados como não point-in-time.

## 2. Fluxo da semana e do dia

```
 quinta (véspera)               sexta = dia de montagem (último pregão da semana na NYSE)                  sexta à noite
┌──────────────────┐ ┌──────────────┐ ┌────────────────────────────────┐ ┌──────────────┐ ┌──────────────────────────┐
│ 19:22 fechamento │→│ 22:37 notas  │→│ 11:07 weekly prepare (dados até│→│ leilões de   │→│ 19:22 daily close:       │
│ diário + retrato │ │ de cobertura │ │ o momento) → mente → validate →│ │ fechamento   │ │ efetivação ao fechamento,│
│ da cobertura     │ │ (fontes      │ │ preview → decide até o prazo   │ │ (MOC), dentro│ │ registro diário,         │
│ (preços-alvo)    │ │ públicas)    │ │ efetivo → tese                 │ │ da capacidade│ │ relatório semanal, portal│
└──────────────────┘ └──────────────┘ └────────────────────────────────┘ └──────────────┘ └──────────────────────────┘
```

Horários de Brasília (agenda em `configs/cdp/rotinas.yaml`; cada disparo passa primeiro pelo
gate de código, que só deixa agir quando há trabalho pendente):

| Quando | Rotina | O que acontece |
|---|---|---|
| dias úteis, 13:30 e 16:03 | `cdp-risco-*` | monitor de risco intradiário; kill switch só por gatilho HARD do código |
| dias úteis, 19:22 (reforço 21:07; repescagem sábado 10:07) | `cdp-diario` | marcação a mercado, risco, atribuição, registro diário encadeado, comentário; retrato da cobertura do pregão (`cobertura run`) quando pendente |
| segunda a quinta, 22:37 | `cdp-cobertura` | notas de pesquisa por emissor, fila determinística do código (até 12 por noite) |
| sexta, 11:07 (reservas 12:07, 13:07, 14:07) | `cdp-semanal` | `weekly prepare` com todos os dados até o momento (barra intradiária provisória) → pesquisa e decisão do PM pela mente → `validate` → `weekly preview` → `weekly decide` até o **prazo efetivo** (15:00; 14:15 em fechamento antecipado nos EUA) → tese da carteira decidida |
| sexta, leilões de fechamento | — | execução ao preço oficial de fechamento de cada linha, limitada à capacidade do leilão e da janela pré-fechamento (`docs/cdp/EXECUCAO.md`) |
| sexta, 19:22 | `cdp-diario` | efetivação ao fechamento oficial, primeiro registro da nova carteira, **relatório semanal de resultado** (`weekly close-report`), retrato da cobertura; o push em `main` dispara o portal |
| dia 1 do mês, 09:15 | `cdp-calibracao` | backtest com todo o histórico e comparação com a execução anterior (nunca muda o mandato) |
| segundas, 08:30 | `cdp-status` | saúde da operação (só leitura) |

Se a decisão não sair até o prazo efetivo, o código não decide depois: a carteira vigente é
mantida até o dia de montagem seguinte (`decisao_perdida` na agenda). A data de início do
mandato (`fund.inception_date`, 09/10/2026) é sempre dia de montagem: a carteira inaugural.

Estados da proposta: `DRAFT → IN_REVIEW → APPROVED | REJECTED → BOOKED`; nova versão ⇒
`SUPERSEDED`; falha
HARD de compliance ⇒ `BLOCKED` (nunca executada). A decisão autônoma é assinada pelo PM do CDP
em modo `AUTONOMOUS`, com as falhas SOFT registradas como cientes.

## 3. Módulos (`src/cdp`)

| Módulo | Responsabilidade | Principais APIs e comandos |
|---|---|---|
| `config.py` | mandato e limites (`configs/cdp/fund.yaml`), hash da configuração | `load_config()`, `FundConfig.config_hash()`; CLI `cdp status` (fundo e calendário) |
| `contracts.py` | artefatos persistidos (Pydantic): proposta, decisão, pesquisa, visões, registros | `Proposal`, `Decision`, `ResearchNote`, `View`, `HARNESS_MINDS` |
| `hashing.py`, `audit.py` | hash canônico e trilha encadeada (`book/audit_log.jsonl`) | `sha256_obj`, `AuditLog.append/verify_chain` |
| `workflow/avaliacao.py`, `research/evaluation.py` | sinais/base residual pré-registrados, autoria observada, vínculo à decisão, maturidade e outcomes autenticados; IC separado por mente/canal, fase somente recomendada | CLI `cdp avaliacao status`, `cdp avaliacao ic --mind codex --canal mente_final`; anexos escritos só pelo runtime; Brier ausente sem forecast probabilístico |
| `calendar.py` | calendários de pregão e regra de montagem (último pregão da semana na NYSE; data de início) | dias de montagem, pregões de dados |
| `universe.py`, `market.py` | emissores e linhas (local/ADR); contêiner `MarketData` | `load_universe()`, `MarketData.truncate()` |
| `data/` | coleta, snapshot imutável, base diária, barra intradiária provisória, dados lentos ao vivo | `build_snapshot`, `load_snapshot`, `intraday`, `live_refresh`, `store`; CLI `cdp fetch-base` |
| `data/publico*.py` | camada de dados públicos: CVM (DFP, ITR, FRE, IPE), SEC EDGAR (XBRL), Yahoo Finance, emissores de ETF, taxas; arquivo bruto com SHA-256 em `data/publico/` | `publico_cvm`, `publico_sec`, `publico_arquivo` |
| `analytics/` | painel em USD, liquidez, squeeze, alugabilidade | `build_asset_panel`, `squeeze_table`, `short_availability` |
| `risk/` | modelo fatorial, decomposição, VaR, estresse, escada de drawdown, janelas de evento, gatilhos de perda, limites de short, risco idiossincrático | `estimate_risk_model`, `risk_decomposition`, `idio`, `gatilhos`, `limites`, `drawdown` |
| `alpha/` | sinais, combinação, ortogonalização, visões | `compute_signals`, `build_alpha`, `apply_views` |
| `portfolio/` | custos, otimizador, compliance, ordens, câmbio | `optimize`, `run_compliance`, `build_trades` |
| `portfolio/execucao.py` | execução no leilão de fechamento: janela do pregão, prazo efetivo, capacidade por linha, efetivação ao preço oficial | `janela_execucao`, capacidade de fechamento |
| `backtest/` | walk-forward semanal, métricas e replay operacional isolado | `run_backtest`, `performance_metrics`; CLI `cdp backtest`; `cdp backtest-operacional` compõe o Runtime com ações, MOC, diário e origem retrospectiva autenticada (`docs/cdp/REPLAY_OPERACIONAL.md`) |
| `research/` | camada da mente: briefing, schemas, guardrails (números, fontes públicas, injeção), PM, comentários diário e semanal, notas, avaliação por fases | `pm_agent`, `guardrails`, `comentario_semanal`, `notas`, `evaluation` |
| `cobertura/` | cobertura de todo o universo: insumos point-in-time, custo de capital, métodos por arquétipo, cenários, rating, portões de qualidade, ponte do preço-alvo, ETFs, sinal de valuation (sombra), placar de acertos, livro imutável `book/cobertura/` | CLI `cdp cobertura run`, `cdp cobertura verify` (`docs/cdp/COBERTURA.md`) |
| `workflow/weekly.py`, `autonomy.py`, `runtime.py` | pipeline semanal autônomo, escada de alternativas, reprodutibilidade `prepare` → `decide` por hash | CLI `cdp weekly prepare|preview|decide`, `cdp validate` |
| `workflow/daily.py`, `track_record.py`, `ledger.py` | fechamento diário: efetivação no leilão, marcação, risco, atribuição, registro diário encadeado | CLI `cdp daily close|publish`, `cdp validate-daily` |
| `workflow/relatorio_semanal.py` | relatório semanal de resultado na noite do dia de montagem (fatos do código, comentário da mente) | CLI `cdp weekly close-report [--publish]`, `cdp validate-weekly-report` |
| `workflow/tese*.py` | tese de investimento da carteira decidida: FactBook, análises, validação e publicação imutável | CLI `cdp tese prepare|publish`, `cdp validate-tese` (`docs/cdp/TESE.md`) |
| `workflow/notas.py` | notas de pesquisa por emissor: fila, preparação, validação, publicação imutável | CLI `cdp nota agenda|prepare|publish`, `cdp validate-nota` (`docs/cdp/NOTAS.md`) |
| `workflow/pacote.py` | pacote autocontido de uma etapa da mente para qualquer assistente (ChatGPT, Gemini, Claude) | CLI `cdp mente pacote` (`docs/cdp/REPRODUZIR.md`) |
| `workflow/agenda.py`, `risk_monitor.py` | o que fazer agora pelo relógio de Brasília; monitor de risco com ações determinísticas | CLI `cdp agenda`, `cdp risk`, `cdp kill-switch` |
| `workflow/reinicio.py` | abertura do livro na data de início do mandato (uma única vez, pelo executor; simulação por padrão) | CLI `cdp reinicio [--executar]` |
| `workflow/demo.py` | demonstração offline completa com mercado sintético (DADOS SIMULADOS): montagens, tese, fechamentos, relatório semanal e verificação da trilha | CLI `cdp demo` |
| `workflow/painel*.py`, `painel_template.html` | painel de gestão (dados e página) na identidade visual da marca | CLI `cdp painel` |
| `estado.py` | retrato só de leitura para qualquer agente: fase, executor, trava, integridade, últimas execuções, pendências, incidentes e próximo passo | CLI `cdp estado [--rede] [--sla]` |
| `rotinas.py` | agenda como dados: gate determinístico, prompts neutros, exportação para agendadores, skills geradas | CLI `cdp rotinas listar|proximas|verificar|gate|prompt|exportar|conferir`, `cdp skills sincronizar|verificar` |
| `executor.py` | escritor único: executor designado, trava distribuída (ramo `cdp-trava`), sincronização e publicação por código, entrega entre jobs | CLI `cdp executor`, `cdp trava`, `cdp sincronizar`, `cdp publicar`, `cdp entrega` |
| `site.py` | portal público estático (GitHub Pages): painel sem cortes, dados abertos com SHA-256, manifesto ligado à versão | CLI `cdp site construir|conferir|estaticos` (`docs/cdp/SITE.md`) |
| `ui/` + `cdp_app.py` | app Streamlit local (leitura do livro) | `uv run streamlit run cdp_app.py` |

## 4. Contratos de dados em memória

- `MarketData` (`market.py`): `close`, `adj_close`, `volume` (data × ticker, moeda local),
  `fx` (data × moeda, **USD por 1 unidade**; `USD`=1), `fundamentals`/`short_interest`/`lending`
  (índice ticker; retratos atuais), `benchmarks`, `rates` (decimal anual), `news`.
- `AssetPanel` (`analytics/panel.py`): nível emissor, retornos diários totais em USD da linha
  primária, `price_usd`, `traded_value_usd` (todas as linhas), `assets` (país, setor, mcap USD,
  ADTV USD, elegibilidade e motivo), `lines` (ADTV por linha, preço local/USD).
- `RiskModel` (`risk/types.py`): `exposures` (B), `factor_cov` (F, anual), `specific_var` (D,
  anual), `factor_returns`, `specific_returns`, `factor_groups`. Fatores: `market`,
  `country:<XX>`, `sector:<GICS>` e estilos; a definição completa está em
  `docs/cdp/METODOLOGIA.md`, seção 4.1.

### Layout do snapshot (`data/snapshots/<as_of>/`)

```
manifest.json            SnapshotManifest (hash de cada arquivo, fontes, limitações)
universe.csv             cópia do universo usado
prices.parquet           longo: date, ticker, close, adj_close, volume
fx.parquet               longo: date, currency, usd_per_unit
benchmarks.parquet       longo: date, symbol, close
rates.parquet            longo: date, series, value
fundamentals.parquet     índice ticker (FUNDAMENTAL_FIELDS)
short_interest.parquet   índice ticker (SHORT_INTEREST_FIELDS)
lending.parquet          índice ticker (LENDING_FIELDS, B3/BTC)
news.jsonl               NewsItem por linha (conteúdo NÃO confiável)
```

A pasta de destino precisa ser nova (nunca sobrescreve). `load_snapshot` recalcula todos os
hashes e falha em divergência. Os arquivos públicos brutos da cobertura ficam em
`data/publico/<FONTE>/...`, com índice append-only e SHA-256 de cada coleta. Os brutos
volumosos que a fonte regrava todo dia (pacotes anuais DFP, ITR, FRE, FCA e calendário do IPE da
CVM; `companyfacts` da SEC) ficam só no clone das rotinas, fora do git: o índice (URL, tamanho,
SHA-256) é versionado e os extratos usados por emissor vão no retrato da cobertura
(`book/cobertura/<data>/insumos/`), que é o que `cdp cobertura verify` recalcula.

## 5. Motor quantitativo (resumo)

- **Risco:** modelo fatorial cross-section diário (mercado, países, setores, estilos e, quando
  configurado, bloco macro), covariância EWMA com correções de assincronia, risco específico com
  encolhimento e piso; ajuste de janelas de evento; VaR/ES e estresses históricos e
  hipotéticos.
- **Alpha:** sinais point-in-time (momentum residual, reversão, baixo risco) e de retrato
  (valor, qualidade, revisões), z-scores winsorizados, combinação, α de Grinold,
  ortogonalização contra as exposições; visões da mente como inclinações limitadas por fase
  (S0–S3, promovidas só com IC realizado). O sinal de valuation da cobertura roda em sombra
  (peso 0) até a promoção por IC.
- **Construção:** otimizador convexo com neutralidade de dólar, beta, país, setor e estilos,
  vol-alvo, limites por nome assimétricos, liquidez, capacidade do leilão de fechamento,
  aluguel e vetos de short, turnover, custos (spread, comissão, câmbio, impacto) e a meta de
  risco idiossincrático; inviável ⇒ escada de relaxamento documentada, nunca nos limites de
  risco do mandato.
- **Gestão de risco:** escada de drawdown sobre a vol ex-ante, gatilhos de velocidade de perda e
  de evento societário, stops de squeeze por nome e kill switch (só redução de risco; desligado
  só por humano).

Fórmulas, parâmetros e justificativas: `docs/cdp/METODOLOGIA.md`; execução e custos:
`docs/cdp/EXECUCAO.md`; valuation: `docs/cdp/COBERTURA.md`.

## 6. Camada da mente

A mente é intercambiável (Claude Code, Codex, Gemini, ChatGPT ou outro): recebe briefings e
schemas gerados pelo código e devolve só JSON validado.

| Etapa | Arquivo da mente | Validação | Publicação |
|---|---|---|---|
| pesquisa e decisão do PM | `book/<semana>/inputs/research_pack.json`, `pm_decision.json` | `cdp validate` | `cdp weekly decide` |
| tese da semana | `book/<semana>/tese/tese.json` | `cdp validate-tese` | `cdp tese publish` |
| comentário diário | `reports/daily/<data>/comentario.json` | `cdp validate-daily` | `cdp daily publish` |
| relatório semanal | `reports/semanal/<data>/comentario.json` | `cdp validate-weekly-report` | `cdp weekly close-report --publish` |
| nota por emissor | `book/cobertura/notas/<IID>/<data>/nota.json` | `cdp validate-nota` | `cdp nota publish` |

Guardrails: números no texto só como `{{fact:id}}` de fatos existentes; fontes públicas por URL
(domínios oficiais para fontes regulatórias e de bolsa); notícias delimitadas e tratadas como
dado não confiável; guia de estilo pt-BR institucional (`docs/cdp/ESTILO.md`). Texto inválido
depois de três tentativas ⇒ o código publica o texto automático. Provedores do modo programático:
`demo` (regras determinísticas, offline), `imported` (JSON de qualquer assistente),
`anthropic` e `openrouter` (opcionais, por variável de ambiente).

## 7. Livro e auditoria (`book/`)

```
book/
  audit_log.jsonl                  eventos encadeados por hash (decisões, registros, cobertura)
  <semana>/briefing/               briefing, contexto e schemas para a mente
  <semana>/inputs/                 research_pack.json e pm_decision.json (mente)
  <semana>/proposal_v<k>.json      propostas versionadas (imutáveis)
  <semana>/decision_v<k>.json      decisão autônoma + approval_hash
  <semana>/booked.json             carteira efetivada no leilão de fechamento
  <semana>/memo_v<k>.md, trades_v<k>.csv, positions_v<k>.csv, shadow_quant.json
  <semana>/tese/                   factbook.json, fatos.md, analise.json, tese.schema.json,
                                   tese.json (mente), tese_publicada.json e tese.md (imutáveis)
  track_record/                    registros diários encadeados (records/<data>.json) e resumo
  cobertura/                       livro.jsonl encadeado, <data>/ (manifesto, selo, modelos),
                                   notas/<IID>/<data>/ (nota da mente e publicada)
```

`approval_hash = sha256(proposal_hash | snapshot_hash | config_hash | research_hash | decisor |
decisão | decided_at)`, com os hashes da decisão do PM e dos gates de risco. A efetivação exige
uma decisão válida e recalcula todos os hashes. Uma tese escrita fora do clone das rotinas é
entregue como rascunho em `docs/cdp/teses/<semana>.json` e adotada pelo `tese prepare`.

`uv run python -m cdp verify` confere a trilha, as decisões, os registros diários, as notas e a
base de mercado; `uv run python -m cdp cobertura verify` confere o livro da cobertura e
recalcula os preços-alvo.

## 8. Operação em qualquer app de IA e publicação

```
 agendador dentro do app de IA (rotinas na nuvem do Claude Code | tarefas agendadas do Codex |
 Antigravity / Gemini CLI)  →  prompt neutro (`cdp rotinas exportar` / `cdp rotinas prompt`)
   1. cdp rotinas gate --adquirir   código: executor? atrasada? há trabalho? trava distribuída
   2. cdp sincronizar --executar    código: o remoto mudou o livro? então parar
   3. roteiro docs/cdp/playbooks/   mente: pesquisa, juízos e textos (JSON validado)
   4. cdp publicar                  código: verify, trava, só o que a execução gravou, push em main
   5. cdp trava liberar
 push em main  →  GitHub Actions cdp-site.yml (sem IA)  →  GitHub Pages (portal público)
```

- **Executor designado** em `configs/cdp/executor.yaml`; identidade de cada ambiente explícita
  (`CDP_EXECUTOR` ou `.cdp/local.yaml`). Troca de executor só por decisão humana
  (`docs/cdp/AUTOMACAO.md`, "Troca de executor").
- **GitHub Actions** faz só a integração contínua (`.github/workflows/cdp-ci.yml`: lint,
  testes, integridade, rotinas, skills, portal da demonstração) e o portal
  (`.github/workflows/cdp-site.yml`); nunca grava no repositório.
- **Conhecimento** agnóstico ao app: `AGENTS.md` (manual canônico), roteiros em
  `docs/cdp/playbooks/`, agenda em `configs/cdp/rotinas.yaml`, skills abertas geradas em
  `.agents/skills/` (espelho em `.claude/skills/`); `docs/cdp/EM_ANDAMENTO.md` e
  `docs/cdp/DECISOES.md` para a continuidade entre sessões.
