# LatAm L/S — Arquitetura do Gestor de Carteira com IA

> Fundo long/short de ações latino-americanas, base USD, capital inicial USD 100 milhões,
> **net neutral**, volatilidade-alvo ex-ante de **5% a.a. (banda 3%–7%)**, rebalanceamento
> **semanal (segunda-feira)** com decisão final do gestor humano.

## 1. Princípios

1. **Números só em código testado.** Retornos, riscos, rankings, pesos, custos e contribuições
   saem de Python determinístico. O LLM produz apenas juízos qualitativos estruturados
   (stance −2…+2, confiança, catalisadores, riscos, veto de short) que referenciam fatos por ID.
2. **IA só aperta, nunca afrouxa.** Visões de IA podem inclinar o alpha dentro de um teto
   pequeno (IC a priori) e podem *restringir* risco (proibir short/long, reduzir peso máximo).
   Nunca ampliam limites do mandato.
3. **Alpha puro.** O alpha composto é ortogonalizado aos fatores de risco e o otimizador
   impõe neutralidade de dólar, beta, país, setor e estilos. O P&L esperado vem do risco específico.
4. **Liquidez e short squeeze como restrições de primeira classe**, não apenas relatórios.
5. **Aprovação humana vinculada a hashes** (snapshot, configuração, pesquisa, proposta).
   Sem autoaprovação. Qualquer mudança invalida a aprovação.
6. **Offline-first.** Testes e demo rodam sem internet com dados simulados sinalizados
   ("DADOS SIMULADOS"). Dados reais vêm de snapshots imutáveis com SHA-256.
7. **Sem look-ahead.** Backtest walk-forward só usa dados até a sexta anterior; sinais
   fundamentalistas de retrato atual são marcados como não point-in-time.

## 2. Fluxo semanal (segunda-feira)

```
sexta (fechamento)                     segunda-feira (manhã)                               semana
┌──────────────┐  ┌──────────────┐  ┌───────────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────┐  ┌────────┐
│ fetch:       │→ │ painel USD + │→ │ sinais quant  │→ │ pesquisa IA│→ │ otimizador  │→ │ gestor   │→ │ book + │
│ snapshot     │  │ modelo risco │  │ + alpha puro  │  │ (visões)   │  │ + compliance│  │ aprova/  │  │ MTM +  │
│ imutável     │  │ + squeeze    │  │               │  │            │  │ + memo      │  │ ajusta   │  │ atrib. │
└──────────────┘  └──────────────┘  └───────────────┘  └────────────┘  └─────────────┘  └──────────┘  └────────┘
```

Estados da proposta: `DRAFT → IN_REVIEW → APPROVED | REJECTED → BOOKED`; nova versão ⇒ `SUPERSEDED`.
Falha HARD de compliance ⇒ `BLOCKED` (não aprovável).

## 3. Pacote `src/cdp`

| Módulo | Responsabilidade | Principais APIs |
|---|---|---|
| `config.py` | Mandato e limites (`configs/cdp/fund.yaml`) | `load_config()`, `FundConfig.config_hash()` |
| `contracts.py` | Artefatos persistidos (Pydantic) | `Proposal`, `Decision`, `ResearchNote`, `View`, … |
| `hashing.py` / `audit.py` | Hash canônico e trilha encadeada | `sha256_obj`, `AuditLog.append/verify_chain` |
| `universe.py` | Emissores e linhas (local/ADR) | `load_universe()`, `Universe` |
| `market.py` | Contêiner `MarketData` | `MarketData.truncate()` |
| `data/` | Coleta real + snapshot + sintético | `build_snapshot`, `load_snapshot`, `make_synthetic_market` |
| `analytics/` | Painel USD, liquidez, squeeze, shortability | `build_asset_panel`, `squeeze_table`, `short_availability` |
| `risk/` | Modelo fatorial, decomposição, VaR, estresse | `estimate_risk_model`, `risk_decomposition`, `stress_tests` |
| `alpha/` | Sinais, combinação, ortogonalização, visões | `compute_signals`, `build_alpha`, `apply_views` |
| `portfolio/` | Custos, otimizador, compliance, trades, FX | `optimize`, `run_compliance`, `build_positions`, `build_trades` |
| `backtest/` | Walk-forward semanal e métricas | `run_backtest`, `performance_metrics` |
| `research/` | Camada GenAI multiagente + guardrails | `run_research`, provedores `demo/anthropic/openrouter/imported` |
| `workflow/` | Pipeline semanal, aprovação, livro, ledger, memo | `WeeklyPipeline`, `Book` |
| `workflow/agenda.py`, `workflow/risk_monitor.py` | Rotinas locais: agenda pelo relógio de Brasília (pendências, prazos) e monitor de risco intradiário/fechamento com ações determinísticas (`kill-switch:` só para gatilhos HARD) | `agenda`, `run_risk_monitor` |
| `ui/` + `pm_app.py` | App Streamlit do gestor | `uv run streamlit run pm_app.py` |

## 4. Contratos de dados em memória

- `MarketData` (`market.py`): `close`, `adj_close`, `volume` (data × ticker, moeda local),
  `fx` (data × moeda, **USD por 1 unidade**; `USD`=1), `fundamentals`/`short_interest`/`lending`
  (índice ticker; retratos atuais), `benchmarks`, `rates` (decimal anual), `news`.
- `AssetPanel` (`analytics/panel.py`): nível emissor, retornos diários totais em USD da linha
  primária, `price_usd`, `traded_value_usd` (todas as linhas), `assets` (país, setor, mcap USD,
  ADTV USD, elegibilidade e motivo), `lines` (ADTV por linha, preço local/USD).
- `RiskModel` (`risk/types.py`): `exposures` (B), `factor_cov` (F, anual), `specific_var` (D,
  anual), `factor_returns`, `specific_returns`, `factor_groups`. Fatores: `market`,
  `country:<XX>`, `sector:<GICS>`, estilos `beta,size,momentum,resvol,value,liquidity,fx_sens`.

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
hashes e falha em divergência.

## 5. Modelo de risco (estilo Barra, adaptado à LatAm)

- Regressão cross-section diária WLS (peso √mcap) dos retornos em USD sobre
  `market + países + setores + estilos`, com restrições de soma zero ponderada por
  capitalização para países e setores (identificação).
- Exposições de estilo padronizadas (média ponderada por cap = 0, desvio = 1, winsor ±3).
  Ausente ⇒ 0 (média) com flag de qualidade.
- Covariância fatorial EWMA (meia-vida 84d para vol, 252d para correlação) + Newey-West (2 lags,
  assincronia de fechamento entre mercados). Risco específico EWMA (84d) com shrinkage bayesiano
  para a média do grupo país×tamanho e piso.
- Saídas: vol ex-ante, decomposição fator × específico, MCTR, beta previsto, VaR/ES 1d e 1s
  (paramétrico e histórico), testes de estresse históricos (COVID 2020, PASO Argentina 2019,
  eleição México 2024, choque fiscal BRL dez/2024 …) e hipotéticos (BRL −10%, commodities −15%,
  momentum crash, squeeze dos 5 maiores shorts +30%).

## 6. Alpha

| Sinal | Definição | PIT no backtest |
|---|---|---|
| `residual_momentum` | Σ resíduos 12m−1m / vol residual | Sim |
| `short_term_reversal` | −resíduo do último mês | Sim |
| `low_risk` | −vol residual 6m | Sim |
| `value` | E/P, B/P, EV/EBITDA⁻¹ relativos ao setor | Não (retrato atual) |
| `quality` | ROE, margens, −alavancagem relativos ao setor | Não |
| `analyst_revision` | upside ao preço-alvo e recomendação média | Não |

z-score winsorizado → combinação ponderada (pesos da config, IC realizado no backtest) →
α anual = IC × σ_específico × z (Grinold) → ortogonalização WLS contra B (alpha puro) →
visões (IA/gestor) como inclinações limitadas.

## 7. Otimizador (cvxpy + CLARABEL)

Maximiza `αᵀw − (52/H)·custo(w − w₀) − aluguelᵀ·short(w) − λ·wᵀΣw` sujeito a:

- `|Σw| ≤ net_exposure_max_abs` (net neutral), `|βᵀw| ≤ beta_max_abs`;
- `wᵀΣw ≤ σ_alvo²` (vol-alvo 5%; teto duro da banda 7%);
- `|exposição país/setor| ≤ 5% NAV`, `|estilo| ≤ 0,15`;
- `Σ|w| ≤ gross_max`; por nome `w ≤ 4%`, `w ≥ −2,5%` (assimétrico);
- liquidez: `|w|·NAV ≤ participação × ADTV × dias` (3 dias long, 2 dias short);
- negociação: `|Δw|·NAV ≤ participação × ADTV × dias de execução` (5 na inception, 2 depois);
- short somente se a linha for alugável e o squeeze não for HIGH; MEDIUM ⇒ teto × 0,5;
- visões de IA/gestor: `no_short`, `no_long`, `max_abs_weight` (apenas restritivas);
- turnover semanal ≤ limite (exceto inception); custo = spread + comissão + FX + impacto √.

Duas passadas: zera posições < `min_position_weight` e reotimiza. Se inviável, relaxa em
ordem documentada (turnover → estilos → país/setor), sempre reportando o relaxamento.

## 8. Linha de execução (local × ADR)

- Long: linha de maior ADTV; empate ⇒ ADR (sem FX/custódia local).
- Short: apenas linhas alugáveis (ADR/US com GC; B3 via BTC). México/Chile/Colômbia/Peru/Argentina
  locais ⇒ short só via ADR. Sem linha alugável ⇒ `can_short = False`.
- Exposição cambial residual por moeda > 1% NAV ⇒ sugestão de hedge via NDF.

## 9. Camada GenAI (pesquisa)

Papéis (inspirados em TradingAgents / AlphaAgents / práticas de Man, Balyasny, BlackRock):

1. **Estrategista macro** (por país) — regime, eventos, riscos.
2. **Analista fundamentalista** (por candidato) — tese bull/bear, catalisadores, stance.
3. **Analista de notícias** — sentimento e materialidade de manchetes (não confiáveis).
4. **Analista de risco de short** — `ok/caution/veto` para cada short proposto.
5. **Juiz bull × bear** para as maiores convicções.
6. **Redator do memo** — texto com placeholders `{{fact:id}}` renderizados pelo código.

Provedores: `demo` (regras determinísticas, offline), `anthropic` (SDK oficial; modelo via
variável de ambiente), `openrouter`, `imported` (notas JSON produzidas por analistas/agentes
externos, validadas por schema). Guardrails: evidências precisam existir no FactBook, números no
texto precisam corresponder a fatos citados, notícias delimitadas e sanitizadas contra injeção,
cache por hash de entrada, versão de prompt registrada.

## 10. Livro, aprovação e auditoria (`book/`)

```
book/
  audit_log.jsonl                  eventos encadeados por hash
  ledger.csv                       NAV diário/semanal, P&L, atribuição
  <semana>/research_pack.json      pesquisa e visões usadas
  <semana>/proposal_v<k>.json      propostas versionadas (imutáveis)
  <semana>/decision.json           decisão humana + approval_hash
  <semana>/booked.json             carteira efetivada
  <semana>/memo.md, trades.csv, positions.csv
```

`approval_hash = sha256(proposal_hash | snapshot_hash | config_hash | research_hash | approver |
decision | decided_at)`. Booking exige decisão `APPROVE` válida e recalcula todos os hashes.
