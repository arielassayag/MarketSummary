# Risco — CDP — Cabra da Peste — 2026-11-24 16:05 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-23 (semana vigente 2026-11-13; hash `2405d1c6cd14`)

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 997,4 mil (pico USD 1,01 mm)
- Retorno do dia: +0,03%; acumulado: -0,26%
- Drawdown: -1,22% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,42% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,013 (limite ±0,050)
- Net: -0,34% (limite ±1,00%); gross 84,44%; long 42,05%; short -42,39%; 49 longs / 44 shorts
- VaR 99% 1d: 0,50% (limite 1,00%); ES 99% 1d: 0,66% (limite 1,25%)
- Vol realizada 21d: 2,95%; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 92,37%; realizada em 63 pregões: 95,45%; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 32

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -2.826 (-0,28% do NAV)
- NAV estimado: USD 994,5 mil; drawdown estimado: -1,50% — estágio normal
- Net/gross estimados: -0,63% / 85,08%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| LILAK | SHORT | +6,53% | +6,53% | USD -1.547 | -0,16% |
| FLRY3.SA | SHORT | +2,62% | +3,09% | USD -663 | -0,07% |
| PAGS | LONG | -1,82% | -1,82% | USD -544 | -0,05% |
| AUGO | SHORT | -2,89% | -2,89% | USD +477 | +0,05% |
| AURE3.SA | SHORT | +1,28% | +1,74% | USD -413 | -0,04% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short AURE3.SA (fechamento): -10,36% desde a entrada; -0,27% do NAV
- Short LILAK (fechamento): +5,41% desde a entrada; +0,12% do NAV
- Short PAX (fechamento): -5,58% desde a entrada; -0,14% do NAV
- Short SMFT3.SA (fechamento): -1,64% desde a entrada; -0,04% do NAV
- Short FLRY3.SA (fechamento): -5,04% desde a entrada; -0,11% do NAV
- Short CX (fechamento): -10,54% desde a entrada; -0,25% do NAV
- Short AUGO (fechamento): -18,85% desde a entrada; -0,38% do NAV
- Short ASR (fechamento): +19,07% desde a entrada; +0,23% do NAV
- Short BBAS3.SA (fechamento): -5,96% desde a entrada; -0,08% do NAV
- Short EMBJ (fechamento): -8,29% desde a entrada; -0,11% do NAV
- Short TIMS3.SA (fechamento): +14,82% desde a entrada; +0,16% do NAV
- Short BRAV3.SA (fechamento): -29,94% desde a entrada; -0,51% do NAV
- Short ARCO (fechamento): -14,40% desde a entrada; -0,18% do NAV
- Short AGRO (fechamento): -22,40% desde a entrada; -0,29% do NAV
- Short NU (fechamento): -18,96% desde a entrada; -0,23% do NAV
- Short MELI (fechamento): -23,49% desde a entrada; -0,31% do NAV
- Short BRAP4.SA (fechamento): -13,20% desde a entrada; -0,14% do NAV
- Short BMA (fechamento): -13,18% desde a entrada; -0,15% do NAV
- Short LAR (fechamento): -36,21% desde a entrada; -0,54% do NAV
- Short SAPR11.SA (fechamento): -23,10% desde a entrada; -0,27% do NAV
- Short UGPA3.SA (fechamento): -19,24% desde a entrada; -0,21% do NAV
- Short ALPA4.SA (fechamento): -22,90% desde a entrada; -0,25% do NAV
- Short ENGI11.SA (fechamento): -25,06% desde a entrada; -0,27% do NAV
- Short VALE (fechamento): -12,66% desde a entrada; -0,11% do NAV
- Short BBDC4.SA (fechamento): -3,45% desde a entrada; -0,03% do NAV
- Short BAP (fechamento): -4,68% desde a entrada; -0,03% do NAV
- Short EQTL3.SA (fechamento): -35,49% desde a entrada; -0,38% do NAV
- Short BCH (fechamento): -5,92% desde a entrada; -0,04% do NAV
- Short RDOR3.SA (fechamento): -18,51% desde a entrada; -0,15% do NAV
- Short PAC (fechamento): -0,36% desde a entrada; 0,00% do NAV
- Short INTR (fechamento): -11,08% desde a entrada; -0,08% do NAV
- Short CSMG3.SA (fechamento): +2,77% desde a entrada; +0,02% do NAV
- Short VIVT3.SA (fechamento): +7,83% desde a entrada; +0,04% do NAV
- Short DLO (fechamento): -7,60% desde a entrada; -0,04% do NAV
- Short VBBR3.SA (fechamento): -16,59% desde a entrada; -0,09% do NAV
- Short ASAI3.SA (fechamento): +6,24% desde a entrada; +0,02% do NAV
- Short BRSR6.SA (fechamento): -33,56% desde a entrada; -0,17% do NAV
- Short BEEF3.SA (fechamento): +9,97% desde a entrada; +0,03% do NAV
- Short AG (fechamento): -23,76% desde a entrada; -0,10% do NAV
- Short CMIG4.SA (fechamento): -11,13% desde a entrada; -0,04% do NAV
- Short RAIL3.SA (fechamento): -9,20% desde a entrada; -0,03% do NAV
- Short LREN3.SA (fechamento): -7,25% desde a entrada; -0,02% do NAV
- Short PAM (fechamento): -21,81% desde a entrada; -0,07% do NAV
- Short TGS (fechamento): -7,85% desde a entrada; -0,02% do NAV
- Short AURE3.SA (intradiário): -9,21% desde a entrada; -0,25% do NAV
- Short LILAK (intradiário): +12,30% desde a entrada; +0,28% do NAV
- Short PAX (intradiário): -6,16% desde a entrada; -0,15% do NAV
- Short SMFT3.SA (intradiário): -1,10% desde a entrada; -0,03% do NAV
- Short FLRY3.SA (intradiário): -2,55% desde a entrada; -0,06% do NAV
- Short CX (intradiário): -11,15% desde a entrada; -0,27% do NAV
- Short AUGO (intradiário): -21,19% desde a entrada; -0,43% do NAV
- Short ASR (intradiário): +18,97% desde a entrada; +0,23% do NAV
- Short BBAS3.SA (intradiário): -3,84% desde a entrada; -0,05% do NAV
- Short EMBJ (intradiário): -7,92% desde a entrada; -0,11% do NAV
- Short TIMS3.SA (intradiário): +15,14% desde a entrada; +0,16% do NAV
- Short BRAV3.SA (intradiário): -31,18% desde a entrada; -0,53% do NAV
- Short ARCO (intradiário): -13,83% desde a entrada; -0,18% do NAV
- Short AGRO (intradiário): -22,74% desde a entrada; -0,30% do NAV
- Short NU (intradiário): -18,03% desde a entrada; -0,22% do NAV
- Short MELI (intradiário): -22,62% desde a entrada; -0,30% do NAV
- Short BRAP4.SA (intradiário): -16,15% desde a entrada; -0,17% do NAV
- Short BMA (intradiário): -13,39% desde a entrada; -0,15% do NAV
- Short LAR (intradiário): -34,21% desde a entrada; -0,51% do NAV
- Short SAPR11.SA (intradiário): -21,85% desde a entrada; -0,26% do NAV
- Short UGPA3.SA (intradiário): -22,82% desde a entrada; -0,25% do NAV
- Short ALPA4.SA (intradiário): -22,55% desde a entrada; -0,25% do NAV
- Short ENGI11.SA (intradiário): -23,85% desde a entrada; -0,26% do NAV
- Short VALE (intradiário): -15,91% desde a entrada; -0,14% do NAV
- Short BBDC4.SA (intradiário): -3,59% desde a entrada; -0,03% do NAV
- Short BAP (intradiário): -7,50% desde a entrada; -0,06% do NAV
- Short EQTL3.SA (intradiário): -34,05% desde a entrada; -0,36% do NAV
- Short BCH (intradiário): -7,48% desde a entrada; -0,05% do NAV
- Short RDOR3.SA (intradiário): -17,22% desde a entrada; -0,14% do NAV
- Short PAC (intradiário): +2,54% desde a entrada; +0,02% do NAV
- Short INTR (intradiário): -6,63% desde a entrada; -0,05% do NAV
- Short CSMG3.SA (intradiário): +6,09% desde a entrada; +0,03% do NAV
- Short VIVT3.SA (intradiário): +8,88% desde a entrada; +0,04% do NAV
- Short DLO (intradiário): -9,61% desde a entrada; -0,05% do NAV
- Short VBBR3.SA (intradiário): -15,06% desde a entrada; -0,08% do NAV
- Short ASAI3.SA (intradiário): +10,10% desde a entrada; +0,04% do NAV
- Short BRSR6.SA (intradiário): -33,39% desde a entrada; -0,17% do NAV
- Short BEEF3.SA (intradiário): +11,44% desde a entrada; +0,03% do NAV
- Short AG (intradiário): -26,73% desde a entrada; -0,11% do NAV
- Short CMIG4.SA (intradiário): -11,54% desde a entrada; -0,04% do NAV
- Short RAIL3.SA (intradiário): -8,99% desde a entrada; -0,03% do NAV
- Short LREN3.SA (intradiário): -7,55% desde a entrada; -0,02% do NAV
- Short PAM (intradiário): -22,03% desde a entrada; -0,07% do NAV
- Short TGS (intradiário): -8,04% desde a entrada; -0,02% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Short BEEF3.SA (BR_MINERVA) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (177): AC.MX@2026-11-13 (0.9969), ALSEA.MX@2026-11-13 (0.9986), AMXB.MX@2026-11-13 (0.9996), ASURB.MX@2026-11-13 (0.9959), BBAJIOO.MX@2026-11-13 (0.9986), BIMBOA.MX@2026-11-13 (0.9964), BOLSAA.MX@2026-11-13 (0.9995), CEMARGOS.CL@2026…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 644.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: Aluguel B3 sem publicação nova entre 2026-11-20 e 2026-11-23 (BDI publica em D+1).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -8.7% no pregão (mediana -0.8%; tolerância 3%).
- Limitação de dados: EMBJ em 17/11/2026: predecessor selado reconciliado com Nasdaq e eventos Yahoo consultados retrospectivamente.

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
