# Risco — CDP — Cabra da Peste — 2026-10-21 16:08 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-20 (semana vigente 2026-10-16; hash `55bc20da7258`)

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 2 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 2 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 1,00 mm (pico USD 1,01 mm)
- Retorno do dia: -0,18%; acumulado: +0,46%
- Drawdown: -0,18% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,60% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,003 (limite ±0,050)
- Net: +0,09% (limite ±1,00%); gross 68,37%; long 34,23%; short -34,14%; 38 longs / 35 shorts
- VaR 99% 1d: 0,53% (limite 1,00%); ES 99% 1d: 0,60% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 87,30%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 8

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD +646 (+0,06% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,11% — estágio normal
- Net/gross estimados: +0,15% / 67,83%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| SGML | SHORT | -5,08% | -5,08% | USD +450 | +0,04% |
| ENGI11.SA | SHORT | -2,59% | -3,08% | USD +406 | +0,04% |
| HYPE3.SA | LONG | -2,17% | -2,65% | USD -362 | -0,04% |
| PINE4.SA | LONG | +3,76% | +3,25% | USD +356 | +0,04% |
| EQTL3.SA | SHORT | -2,30% | -2,78% | USD +340 | +0,03% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 2
- Short FMX (fechamento): +8,28% desde a entrada; +0,10% do NAV
- Short FLRY3.SA (fechamento): +4,02% desde a entrada; +0,05% do NAV
- Short ENGI11.SA (fechamento): +3,37% desde a entrada; +0,04% do NAV
- Short UGPA3.SA (fechamento): +1,74% desde a entrada; +0,02% do NAV
- Short AURE3.SA (fechamento): +2,56% desde a entrada; +0,03% do NAV
- Short ORVR3.SA (fechamento): -2,89% desde a entrada; -0,04% do NAV
- Short USIM5.SA (fechamento): -3,20% desde a entrada; -0,04% do NAV
- Short NU (fechamento): +3,64% desde a entrada; +0,04% do NAV
- Short PAX (fechamento): +3,08% desde a entrada; +0,04% do NAV
- Short CX (fechamento): +7,43% desde a entrada; +0,09% do NAV
- Short BRAV3.SA (fechamento): +1,70% desde a entrada; +0,02% do NAV
- Short EMBJ (fechamento): +0,87% desde a entrada; +0,01% do NAV
- Short YPF (fechamento): +1,48% desde a entrada; +0,02% do NAV
- Short EQTL3.SA (fechamento): -2,31% desde a entrada; -0,03% do NAV
- Short ALOS3.SA (fechamento): -0,36% desde a entrada; 0,00% do NAV
- Short LAR (fechamento): -12,70% desde a entrada; -0,17% do NAV
- Short MELI (fechamento): +0,44% desde a entrada; 0,00% do NAV
- Short ARCO (fechamento): +3,48% desde a entrada; +0,04% do NAV
- Short ASR (fechamento): +6,99% desde a entrada; +0,07% do NAV
- Short SAPR11.SA (fechamento): -7,77% desde a entrada; -0,09% do NAV
- Short VBBR3.SA (fechamento): -0,54% desde a entrada; -0,01% do NAV
- Short AGRO (fechamento): -6,64% desde a entrada; -0,07% do NAV
- Short RDOR3.SA (fechamento): -0,80% desde a entrada; -0,01% do NAV
- Short SGML (fechamento): -9,52% desde a entrada; -0,09% do NAV
- Short CIB (fechamento): +1,12% desde a entrada; +0,01% do NAV
- Short BSAC (fechamento): +1,75% desde a entrada; +0,01% do NAV
- Short BCH (fechamento): +2,08% desde a entrada; +0,01% do NAV
- Short LILAK (fechamento): -1,48% desde a entrada; -0,01% do NAV
- Short CSMG3.SA (fechamento): -1,56% desde a entrada; -0,01% do NAV
- Short KLBN11.SA (fechamento): +1,60% desde a entrada; +0,01% do NAV
- Short CMIG4.SA (fechamento): -2,47% desde a entrada; -0,01% do NAV
- Short SBSP3.SA (fechamento): -3,15% desde a entrada; -0,01% do NAV
- Short BRSR6.SA (fechamento): -3,66% desde a entrada; -0,01% do NAV
- Short RAIL3.SA (fechamento): +3,88% desde a entrada; +0,01% do NAV
- Short OMAB (fechamento): +5,12% desde a entrada; +0,02% do NAV
- Short FMX (intradiário): +7,48% desde a entrada; +0,09% do NAV
- Short FLRY3.SA (intradiário): +2,99% desde a entrada; +0,04% do NAV
- Short ENGI11.SA (intradiário): +0,69% desde a entrada; +0,01% do NAV
- Short UGPA3.SA (intradiário): +2,56% desde a entrada; +0,03% do NAV
- Short AURE3.SA (intradiário): +2,43% desde a entrada; +0,03% do NAV
- Short ORVR3.SA (intradiário): -3,59% desde a entrada; -0,05% do NAV
- Short USIM5.SA (intradiário): -4,49% desde a entrada; -0,06% do NAV
- Short NU (intradiário): +3,30% desde a entrada; +0,04% do NAV
- Short PAX (intradiário): +2,06% desde a entrada; +0,03% do NAV
- Short CX (intradiário): +8,68% desde a entrada; +0,10% do NAV
- Short BRAV3.SA (intradiário): +2,48% desde a entrada; +0,03% do NAV
- Short EMBJ (intradiário): +1,54% desde a entrada; +0,02% do NAV
- Short YPF (intradiário): +1,12% desde a entrada; +0,01% do NAV
- Short EQTL3.SA (intradiário): -4,55% desde a entrada; -0,06% do NAV
- Short ALOS3.SA (intradiário): -1,98% desde a entrada; -0,02% do NAV
- Short LAR (intradiário): -13,19% desde a entrada; -0,17% do NAV
- Short MELI (intradiário): -1,41% desde a entrada; -0,02% do NAV
- Short ARCO (intradiário): +2,33% desde a entrada; +0,03% do NAV
- Short ASR (intradiário): +9,08% desde a entrada; +0,09% do NAV
- Short SAPR11.SA (intradiário): -7,73% desde a entrada; -0,09% do NAV
- Short VBBR3.SA (intradiário): -0,46% desde a entrada; 0,00% do NAV
- Short AGRO (intradiário): -6,84% desde a entrada; -0,07% do NAV
- Short RDOR3.SA (intradiário): -2,24% desde a entrada; -0,02% do NAV
- Short SGML (intradiário): -14,12% desde a entrada; -0,14% do NAV
- Short CIB (intradiário): +3,39% desde a entrada; +0,03% do NAV
- Short BSAC (intradiário): +1,16% desde a entrada; +0,01% do NAV
- Short BCH (intradiário): +1,32% desde a entrada; +0,01% do NAV
- Short LILAK (intradiário): -1,60% desde a entrada; -0,01% do NAV
- Short CSMG3.SA (intradiário): -2,65% desde a entrada; -0,01% do NAV
- Short KLBN11.SA (intradiário): +0,17% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (intradiário): -4,12% desde a entrada; -0,02% do NAV
- Short SBSP3.SA (intradiário): -4,17% desde a entrada; -0,02% do NAV
- Short BRSR6.SA (intradiário): -3,44% desde a entrada; -0,01% do NAV
- Short RAIL3.SA (intradiário): +0,75% desde a entrada; 0,00% do NAV
- Short OMAB (intradiário): +8,87% desde a entrada; +0,03% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Short FLRY3.SA (BR_FLEURY) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
- Short ENGI11.SA (BR_ENERGISA) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (227): AC.MX@2026-10-12 (1.0016), ALPEKA.MX@2026-10-12 (1.0075), ALSEA.MX@2026-10-12 (1.0025), AMXB.MX@2026-10-12 (0.9990), ASURB.MX@2026-10-12 (1.0008), BBAJIOO.MX@2026-10-12 (1.0009), BIMBOA.MX@2026-10-12 (1.0031), BOLSAA.MX@2026-1…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1401.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -3.3% no pregão (mediana -3.4%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
