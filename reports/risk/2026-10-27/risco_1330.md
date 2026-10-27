# Risco — CDP — Cabra da Peste — 2026-10-27 13:30 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-26 (semana vigente 2026-10-23; hash `8329ab7a35f0`)

## Ações recomendadas (determinísticas)

- revisar: Exposição líquida +1,01% fora do limite ±1,00% (net neutral)
- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `net_fora_do_limite` | Exposição líquida +1,01% fora do limite ±1,00% (net neutral) | reequilibrar no próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `movimento_extremo:RIAA3.SA` | RIAA3.SA: fechamento variou -44.2% no dia. |  |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: +0,10%; acumulado: +0,79%
- Drawdown: 0,00% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,20% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,004 (limite ±0,050)
- Net: +1,01% (limite ±1,00%); gross 59,47%; long 30,24%; short -29,23%; 39 longs / 36 shorts
- VaR 99% 1d: 0,47% (limite 1,00%); ES 99% 1d: 0,54% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 90,61%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 12

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -901 (-0,09% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,09% — estágio normal
- Net/gross estimados: +0,92% / 60,21%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| LAR | SHORT | +8,99% | +8,99% | USD -1.113 | -0,11% |
| TEND3.SA | LONG | +9,10% | +9,73% | USD +869 | +0,09% |
| RIAA3.SA | LONG | +6,68% | +7,30% | USD +747 | +0,07% |
| SGML | SHORT | +5,85% | +5,85% | USD -632 | -0,06% |
| AERO | LONG | +4,35% | +4,35% | USD +516 | +0,05% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short ASR (fechamento): +7,88% desde a entrada; +0,09% do NAV
- Short AGRO (fechamento): -2,04% desde a entrada; -0,03% do NAV
- Short LAR (fechamento): -16,62% desde a entrada; -0,24% do NAV
- Short EMBJ (fechamento): -0,94% desde a entrada; -0,01% do NAV
- Short LILAK (fechamento): -3,92% desde a entrada; -0,05% do NAV
- Short BRAP4.SA (fechamento): +1,32% desde a entrada; +0,02% do NAV
- Short MELI (fechamento): -10,40% desde a entrada; -0,13% do NAV
- Short ARCO (fechamento): -10,85% desde a entrada; -0,14% do NAV
- Short TIMS3.SA (fechamento): -5,19% desde a entrada; -0,06% do NAV
- Short SGML (fechamento): -12,55% desde a entrada; -0,15% do NAV
- Short UGPA3.SA (fechamento): -9,85% desde a entrada; -0,12% do NAV
- Short NU (fechamento): -13,53% desde a entrada; -0,17% do NAV
- Short BRAV3.SA (fechamento): -7,42% desde a entrada; -0,08% do NAV
- Short SAPR11.SA (fechamento): -22,35% desde a entrada; -0,28% do NAV
- Short VBBR3.SA (fechamento): -12,43% desde a entrada; -0,14% do NAV
- Short FLRY3.SA (fechamento): -18,48% desde a entrada; -0,22% do NAV
- Short ALPA4.SA (fechamento): -21,49% desde a entrada; -0,26% do NAV
- Short ORVR3.SA (fechamento): -25,33% desde a entrada; -0,31% do NAV
- Short ENGI11.SA (fechamento): -27,57% desde a entrada; -0,33% do NAV
- Short AURE3.SA (fechamento): -27,40% desde a entrada; -0,32% do NAV
- Short CIB (fechamento): +1,68% desde a entrada; +0,01% do NAV
- Short EQTL3.SA (fechamento): -31,35% desde a entrada; -0,36% do NAV
- Short RDOR3.SA (fechamento): -21,21% desde a entrada; -0,19% do NAV
- Short PAC (fechamento): +1,01% desde a entrada; +0,01% do NAV
- Short GGAL (fechamento): -6,75% desde a entrada; -0,04% do NAV
- Short AG (fechamento): +0,54% desde a entrada; 0,00% do NAV
- Short BAP (fechamento): +1,03% desde a entrada; +0,01% do NAV
- Short VIVT3.SA (fechamento): -5,37% desde a entrada; -0,03% do NAV
- Short STNE (fechamento): -27,44% desde a entrada; -0,17% do NAV
- Short BRSR6.SA (fechamento): -21,95% desde a entrada; -0,12% do NAV
- Short CMIG4.SA (fechamento): -14,76% desde a entrada; -0,06% do NAV
- Short TOTS3.SA (fechamento): -14,50% desde a entrada; -0,05% do NAV
- Short PAM (fechamento): -3,62% desde a entrada; -0,01% do NAV
- Short RAIL3.SA (fechamento): -16,58% desde a entrada; -0,05% do NAV
- Short SBSP3.SA (fechamento): -24,79% desde a entrada; -0,09% do NAV
- Short BMA (fechamento): -6,30% desde a entrada; -0,02% do NAV
- Short ASR (intradiário): +7,14% desde a entrada; +0,08% do NAV
- Short AGRO (intradiário): -2,53% desde a entrada; -0,03% do NAV
- Short LAR (intradiário): -9,12% desde a entrada; -0,13% do NAV
- Short EMBJ (intradiário): +0,57% desde a entrada; +0,01% do NAV
- Short LILAK (intradiário): -1,50% desde a entrada; -0,02% do NAV
- Short BRAP4.SA (intradiário): -2,05% desde a entrada; -0,02% do NAV
- Short MELI (intradiário): -8,40% desde a entrada; -0,11% do NAV
- Short ARCO (intradiário): -10,80% desde a entrada; -0,14% do NAV
- Short TIMS3.SA (intradiário): -3,51% desde a entrada; -0,04% do NAV
- Short SGML (intradiário): -7,43% desde a entrada; -0,09% do NAV
- Short UGPA3.SA (intradiário): -11,15% desde a entrada; -0,13% do NAV
- Short NU (intradiário): -14,05% desde a entrada; -0,17% do NAV
- Short BRAV3.SA (intradiário): -6,79% desde a entrada; -0,08% do NAV
- Short SAPR11.SA (intradiário): -21,58% desde a entrada; -0,28% do NAV
- Short VBBR3.SA (intradiário): -12,15% desde a entrada; -0,13% do NAV
- Short FLRY3.SA (intradiário): -16,45% desde a entrada; -0,19% do NAV
- Short ALPA4.SA (intradiário): -18,65% desde a entrada; -0,23% do NAV
- Short ORVR3.SA (intradiário): -25,57% desde a entrada; -0,32% do NAV
- Short ENGI11.SA (intradiário): -26,60% desde a entrada; -0,32% do NAV
- Short AURE3.SA (intradiário): -25,10% desde a entrada; -0,30% do NAV
- Short CIB (intradiário): +1,38% desde a entrada; +0,01% do NAV
- Short EQTL3.SA (intradiário): -29,73% desde a entrada; -0,35% do NAV
- Short RDOR3.SA (intradiário): -21,88% desde a entrada; -0,20% do NAV
- Short PAC (intradiário): +0,79% desde a entrada; 0,00% do NAV
- Short GGAL (intradiário): -7,15% desde a entrada; -0,05% do NAV
- Short AG (intradiário): +3,86% desde a entrada; +0,02% do NAV
- Short BAP (intradiário): -0,21% desde a entrada; 0,00% do NAV
- Short VIVT3.SA (intradiário): -4,72% desde a entrada; -0,03% do NAV
- Short STNE (intradiário): -28,40% desde a entrada; -0,17% do NAV
- Short BRSR6.SA (intradiário): -24,64% desde a entrada; -0,14% do NAV
- Short CMIG4.SA (intradiário): -13,77% desde a entrada; -0,05% do NAV
- Short TOTS3.SA (intradiário): -17,63% desde a entrada; -0,07% do NAV
- Short PAM (intradiário): -3,90% desde a entrada; -0,01% do NAV
- Short RAIL3.SA (intradiário): -16,42% desde a entrada; -0,05% do NAV
- Short SBSP3.SA (intradiário): -24,32% desde a entrada; -0,09% do NAV
- Short BMA (intradiário): -6,00% desde a entrada; -0,02% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Exposição líquida +1,01% fora do limite ±1,00% (net neutral).
- Short GGAL (AR_GALICIA) com risco de squeeze HIGH (era MEDIUM na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (305): AC.MX@2026-10-16 (0.9972), ALSEA.MX@2026-10-16 (1.0002), AMXB.MX@2026-10-16 (1.0009), ASURB.MX@2026-10-16 (0.9998), BBAJIOO.MX@2026-10-16 (0.9979), BIMBOA.MX@2026-10-16 (1.0003), BOLSAA.MX@2026-10-16 (1.0019), CEMEXCPO.MX@2026…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1580.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 2.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: QA paridade ADR: BAK vs BRKM5.SA desvio -7.0% no pregão (mediana +1.6%; tolerância 3%).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -2.1% no pregão (mediana -3.3%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
