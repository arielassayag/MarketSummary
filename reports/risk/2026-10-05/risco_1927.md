# Risco — CDP — Cabra da Peste — 2026-10-05 19:27 (Brasília)

> Dados reais de mercado; paper trading com execução hipotética no fechamento (MOC) e custos do modelo.

- Modo: último fechamento
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-05 (semana vigente 2026-10-05; hash `7b481b7cdacd`)

## Ações recomendadas (determinísticas)

- revisar: Exposição líquida +1,00% fora do limite ±1,00% (net neutral)
- revisar: Exposição líquida de país BR +2,00% acima do limite ±2,00%
- revisar: Exposição líquida de país CL +2,00% acima do limite ±2,00%
- revisar: Exposição líquida de setor Energy +2,50% acima do limite ±2,50%
- revisar: Exposição líquida de estilo liquidity +0,100 acima do limite ±0,100

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `net_fora_do_limite` | Exposição líquida +1,00% fora do limite ±1,00% (net neutral) | reequilibrar no próximo rebalanceamento |
| SOFT | `exposicao_country_BR` | Exposição líquida de país BR +2,00% acima do limite ±2,00% | neutralizar no próximo rebalanceamento |
| SOFT | `exposicao_country_CL` | Exposição líquida de país CL +2,00% acima do limite ±2,00% | neutralizar no próximo rebalanceamento |
| SOFT | `exposicao_sector_Energy` | Exposição líquida de setor Energy +2,50% acima do limite ±2,50% | neutralizar no próximo rebalanceamento |
| SOFT | `exposicao_style_liquidity` | Exposição líquida de estilo liquidity +0,100 acima do limite ±0,100 | neutralizar no próximo rebalanceamento |
| INFO | `gross_abaixo_do_minimo` | Gross 45,92% abaixo do mínimo 50,00% | nenhuma ação intradiária (pode refletir a escada de drawdown) |

## NAV e drawdown (último fechamento)

- NAV: USD 99,82 mm (pico USD 100,00 mm)
- Retorno do dia: -0,18%; acumulado: -0,18%
- Drawdown: -0,18% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,13% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,020 (limite ±0,050)
- Net: +1,00% (limite ±1,00%); gross 45,92%; long 23,46%; short -22,46%; 25 longs / 21 shorts
- VaR 99% 1d: 0,46% (limite 1,00%); ES 99% 1d: 0,52% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Exposições acima do limite

| Grupo | Nome | Net | Limite |
|---|---|---|---|
| country | BR | +2,00% | ±2,00% |
| country | CL | +2,00% | ±2,00% |
| sector | Energy | +2,50% | ±2,50% |
| style | liquidity | +0,100 | ±0,100 |

## Liquidez

- Máximo de dias para liquidar: 0,7 d; gross liquidável em 1 dia: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 0
- Short EMBJ (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short LILAK (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short USIM5.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short CIB (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short SCCO (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short PAX (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short UGPA3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short FMX (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short FLRY3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short ALOS3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short RDOR3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short DLO (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short VALE (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short EC (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short KLBN11.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short EGIE3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short ITSA4.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short LAR (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short MBRF3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short GOAU4.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short SANB11.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV

## Alertas do registro de fechamento

- Exposição líquida +1,00% fora do limite ±1,00% (net neutral).
- Exposição líquida de país BR +2,00% acima do limite ±2,00%.
- Exposição líquida de país CL +2,00% acima do limite ±2,00%.
- Exposição líquida de setor Energy +2,50% acima do limite ±2,50%.
- Exposição líquida de estilo liquidity +0,100 acima do limite ±0,100.
- Limitação de dados: Viés de sobrevivência: o universo foi definido na data de criação (não é point-in-time); emissores deslistados antes dessa data não aparecem no histórico.
- Limitação de dados: Fundamentos (Yahoo Ticker.info) são retrato atual, NÃO point-in-time; múltiplos podem misturar moedas/classes — ver coluna fundamentals_quality.
- Limitação de dados: Adj Close do Yahoo é ajustado retroativamente por proventos/desdobramentos e muda a cada novo evento; o hash é por snapshot.
- Limitação de dados: Câmbio do Yahoo (=X) usa barras diárias carimbadas em Europe/London, normalizadas para a data do pregão; não é fixing oficial (PTAX/FIX/TRM).
- Limitação de dados: Short interest de ADRs refere-se ao float do ADS (não ao float total da companhia) e é publicado pela FINRA com defasagem (liquidação + 7 dias úteis).
- Limitação de dados: Saldo de aluguel B3 (BTC) inclui arbitragem/ETF/hedge (limite superior do short); taxas sem contratos no dia são a última taxa calculada (rate_stale).
- Limitação de dados: Notícias (Google News RSS) são conteúdo NÃO confiável: usadas apenas como dado citado.
- Limitação de dados: Notícias indisponíveis para 10 emissores.
- Limitação de dados: Volume zero com preço válido tratado como AUSENTE (NaN + volume_suspeito): 4547 observações em 108 linhas; maiores: EISA.SN (635), AMXB.MX (625), SGML (362), PCAR3.SA (252), GRUPOSURA.CL (186), GRUPOARGOS.CL (165), CIBEST.CL (159), ERO (156).
- Limitação de dados: Retornos diários > 35% em módulo (revisar eventos corporativos): BBAR (2), BMA (2), BMA.BA (1), CAAP (2), CEPU (2), CIBEST.CL (2), COLBUN.SN (1), CRESY (1), DLO (1), GGAL (2), GGAL.BA (1), GRUPOARGOS.CL (1), GRUPOSURA.CL (1), GTE (3), HAPV3.SA (1), IRS (1), JBSS32.SA (1), LOMA (1), LTM.SN (15), NAT…
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio mediano -3.7% (último -1.8%; referência +0.0%; tolerância 3%).
- Limitação de dados: Argentina: CCL implícito nas paridades ADR ≈ +5.9% vs câmbio oficial (ARS=X); preços locais em ARS embutem o CCL.
- Limitação de dados: Aluguel B3 sem publicação nova entre 2026-10-03 e 2026-10-05 (BDI publica em D+1).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -3.7% no pregão (mediana -3.7%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- nenhuma

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Paper trading: o kill switch só bloqueia risco novo e nunca afrouxa limites._
