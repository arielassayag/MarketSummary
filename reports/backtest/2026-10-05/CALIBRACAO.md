# Calibração do núcleo quantitativo — 2026-10-05

Backtest walk-forward semanal com dados reais (base imutável `data/market/base/2026-10-02`):
300 rebalanceamentos de 2021-01-04 a 2026-09-28. O rebalanceamento acontece no primeiro pregão
da semana da B3, com dados até o pregão anterior, e a execução é no fechamento (MOC).

O teste usa só os sinais point-in-time (momentum residual, reversão de curto prazo e baixo
risco). Inclui custos, aluguel e juros do caixa. A camada de IA não entra (não é testável
honestamente) e a escada de drawdown não é aplicada.

Vieses conhecidos:
- Sobrevivência: o universo é o de hoje.
- Aluguel e short interest não são point-in-time.
- A capitalização histórica usa as ações atuais.

Números copiados de `metrics.json` de cada pasta.

| Variante | Retorno a.a. | Vol a.a. | Sharpe (exc. caixa) | Sharpe bruto | Max DD | Custos a.a. | Giro semanal | P&L específico a.a. | P&L fatorial a.a. | PSR | DSR (4 testes) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 — modo match escalando só o alpha | 2,29% | 5,20% | −0,17 | 0,35 | −6,39% | 2,38% | 15,4% | 1,83% | −0,02% | 0,34 | — |
| v2 — modo match reduzindo λ (base) | 2,63% | 5,13% | −0,11 | 0,36 | −7,02% | 2,12% | 14,1% | 1,74% | 0,13% | 0,40 | — |
| A — v2 + custo ×2 | 1,77% | 4,11% | −0,35 | −0,16 | −8,81% | 0,58% | 5,2% | 0,10% | −0,75% | 0,20 | 0,03 |
| **B — v2 sem reversão de curto prazo** | **4,21%** | **4,42%** | **0,22** | **0,40** | **−7,03%** | **0,57%** | **4,8%** | **2,17%** | **−0,42%** | **0,70** | **0,30** |
| C — A + B | 3,74% | 3,61% | 0,13 | 0,24 | −4,33% | 0,25% | 2,4% | 1,02% | −0,15% | 0,62 | 0,23 |

## Decisões

1. **Modo `match` do otimizador**: a meta de vol passa a ser perseguida reduzindo a aversão a
   risco (λ/κ), sem escalar só o alpha.
   - Escalar só o alpha tornava custos e aluguel quase irrelevantes e fazia a carteira girar
     demais (v1 → v2).
   - Se o alpha líquido não justificar a meta, o alpha é escalado só até o piso da banda.
2. **Reversão de curto prazo com peso zero** (`configs/cdp/fund.yaml`, `alpha.signal_weights`).
   - O sinal gerava giro (cerca de 14% por semana) sem alpha suficiente para pagar os custos.
   - Sem ele, os custos caem de 2,1% para 0,6% a.a. e o P&L específico se mantém (B).
   - Os demais pesos são renormalizados pelo código.
   - A variante B foi escolhida também por coerência econômica: menos giro e alpha
     idiossincrático preservado.
3. **Custo ×2 não foi adotado.** Reduz o giro, mas destrói o alpha específico (A).

## Limites estatísticos

O Sharpe deflacionado da variante escolhida, com quatro testes, é de cerca de 0,30. A evidência
ainda não é estatisticamente significativa. A calibração deve ser refeita mensalmente (skill
`calibracao`) com o track record real e a carteira-sombra só-quant. Nenhuma mudança de mandato é
automática: toda alteração fica registrada aqui e no `config_hash`.
