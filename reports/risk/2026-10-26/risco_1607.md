# Risco — CDP — Cabra da Peste — 2026-10-26 16:07 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-23 (semana vigente 2026-10-23; hash `560aec5dd00c`)

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 5 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 5 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: -0,01%; acumulado: +0,69%
- Drawdown: -0,01% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,75% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: 0,000 (limite ±0,050)
- Net: +0,94% (limite ±1,00%); gross 69,85%; long 35,39%; short -34,45%; 39 longs / 36 shorts
- VaR 99% 1d: 0,55% (limite 1,00%); ES 99% 1d: 0,63% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 89,32%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 11

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD +34 (0,00% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,01% — estágio normal
- Net/gross estimados: +0,95% / 58,88%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| RIAA3.SA | LONG | -46,06% | -50,52% | USD -10.047 | -1,00% |
| ENGI11.SA | SHORT | -30,53% | -36,27% | USD +4.753 | +0,47% |
| AURE3.SA | SHORT | -28,67% | -34,57% | USD +4.538 | +0,45% |
| EQTL3.SA | SHORT | -29,75% | -35,55% | USD +4.312 | +0,43% |
| TEND3.SA | LONG | -26,38% | -32,46% | USD -4.264 | -0,42% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 5
- Short ORVR3.SA (fechamento): -1,52% desde a entrada; -0,02% do NAV
- Short SAPR11.SA (fechamento): -4,74% desde a entrada; -0,07% do NAV
- Short FLRY3.SA (fechamento): +2,80% desde a entrada; +0,04% do NAV
- Short AURE3.SA (fechamento): +2,83% desde a entrada; +0,04% do NAV
- Short ENGI11.SA (fechamento): +1,81% desde a entrada; +0,02% do NAV
- Short ALPA4.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BRAV3.SA (fechamento): +5,19% desde a entrada; +0,06% do NAV
- Short ARCO (fechamento): +2,44% desde a entrada; +0,03% do NAV
- Short AGRO (fechamento): -0,96% desde a entrada; -0,01% do NAV
- Short NU (fechamento): +4,12% desde a entrada; +0,05% do NAV
- Short BRAP4.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short UGPA3.SA (fechamento): -1,38% desde a entrada; -0,02% do NAV
- Short TIMS3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short MELI (fechamento): -2,81% desde a entrada; -0,04% do NAV
- Short ASR (fechamento): +6,27% desde a entrada; +0,07% do NAV
- Short LAR (fechamento): -15,22% desde a entrada; -0,22% do NAV
- Short LILAK (fechamento): -0,81% desde a entrada; -0,01% do NAV
- Short EMBJ (fechamento): -1,26% desde a entrada; -0,02% do NAV
- Short EQTL3.SA (fechamento): -3,68% desde a entrada; -0,05% do NAV
- Short VBBR3.SA (fechamento): -2,61% desde a entrada; -0,03% do NAV
- Short SGML (fechamento): -12,89% desde a entrada; -0,16% do NAV
- Short RDOR3.SA (fechamento): -1,61% desde a entrada; -0,02% do NAV
- Short CIB (fechamento): +3,36% desde a entrada; +0,03% do NAV
- Short GGAL (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short PAC (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short STNE (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short VIVT3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BRSR6.SA (fechamento): -2,46% desde a entrada; -0,01% do NAV
- Short AG (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BAP (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (fechamento): -3,79% desde a entrada; -0,02% do NAV
- Short TOTS3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short SBSP3.SA (fechamento): -4,82% desde a entrada; -0,02% do NAV
- Short RAIL3.SA (fechamento): +0,22% desde a entrada; 0,00% do NAV
- Short PAM (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BMA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short ORVR3.SA (intradiário): -26,85% desde a entrada; -0,33% do NAV
- Short SAPR11.SA (intradiário): -24,24% desde a entrada; -0,31% do NAV
- Short FLRY3.SA (intradiário): -18,11% desde a entrada; -0,21% do NAV
- Short AURE3.SA (intradiário): -26,65% desde a entrada; -0,31% do NAV
- Short ENGI11.SA (intradiário): -29,27% desde a entrada; -0,34% do NAV
- Short ALPA4.SA (intradiário): -24,73% desde a entrada; -0,29% do NAV
- Short BRAV3.SA (intradiário): -7,71% desde a entrada; -0,09% do NAV
- Short ARCO (intradiário): -9,40% desde a entrada; -0,12% do NAV
- Short AGRO (intradiário): -1,89% desde a entrada; -0,02% do NAV
- Short NU (intradiário): -13,61% desde a entrada; -0,17% do NAV
- Short BRAP4.SA (intradiário): +1,10% desde a entrada; +0,01% do NAV
- Short UGPA3.SA (intradiário): -10,49% desde a entrada; -0,12% do NAV
- Short TIMS3.SA (intradiário): -6,23% desde a entrada; -0,07% do NAV
- Short MELI (intradiário): -10,79% desde a entrada; -0,14% do NAV
- Short ASR (intradiário): +7,89% desde a entrada; +0,09% do NAV
- Short LAR (intradiário): -16,92% desde a entrada; -0,25% do NAV
- Short LILAK (intradiário): -3,98% desde a entrada; -0,05% do NAV
- Short EMBJ (intradiário): -1,04% desde a entrada; -0,01% do NAV
- Short EQTL3.SA (intradiário): -32,33% desde a entrada; -0,37% do NAV
- Short VBBR3.SA (intradiário): -13,38% desde a entrada; -0,15% do NAV
- Short SGML (intradiário): -12,94% desde a entrada; -0,16% do NAV
- Short RDOR3.SA (intradiário): -22,40% desde a entrada; -0,20% do NAV
- Short CIB (intradiário): +1,10% desde a entrada; +0,01% do NAV
- Short GGAL (intradiário): -6,33% desde a entrada; -0,04% do NAV
- Short PAC (intradiário): +1,10% desde a entrada; +0,01% do NAV
- Short STNE (intradiário): -27,66% desde a entrada; -0,17% do NAV
- Short VIVT3.SA (intradiário): -6,29% desde a entrada; -0,03% do NAV
- Short BRSR6.SA (intradiário): -23,51% desde a entrada; -0,13% do NAV
- Short AG (intradiário): +0,34% desde a entrada; 0,00% do NAV
- Short BAP (intradiário): +0,83% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (intradiário): -15,58% desde a entrada; -0,06% do NAV
- Short TOTS3.SA (intradiário): -17,86% desde a entrada; -0,07% do NAV
- Short SBSP3.SA (intradiário): -26,28% desde a entrada; -0,10% do NAV
- Short RAIL3.SA (intradiário): -20,67% desde a entrada; -0,07% do NAV
- Short PAM (intradiário): -3,59% desde a entrada; -0,01% do NAV
- Short BMA (intradiário): -6,60% desde a entrada; -0,02% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Ordens abaixo da banda de não-negociação (0,10% do NAV ou do custo fixo mínimo por ordem do mercado): BBAR, CEPU, IRS, ALUP11.SA, ABEV3.SA, AURE3.SA, AXIA3.SA, BBSE3.SA (+31).
- Short ORVR3.SA (BR_ORIZON) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
- Short FLRY3.SA (BR_FLEURY) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
- Short ENGI11.SA (BR_ENERGISA) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
- Short ALPA4.SA (BR_ALPARGATAS) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
- Short TOTS3.SA (BR_TOTVS) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (357): AC.MX@2026-10-13 (0.9991), ALPEKA.MX@2026-10-13 (0.9962), ALSEA.MX@2026-10-13 (0.9996), AMXB.MX@2026-10-13 (1.0010), ASURB.MX@2026-10-13 (0.9972), BBAJIOO.MX@2026-10-13 (0.9977), BIMBOA.MX@2026-10-13 (0.9998), CEMEXCPO.MX@2026…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 2085.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -3.5% no pregão (mediana -3.3%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
