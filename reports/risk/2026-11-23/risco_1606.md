# Risco — CDP — Cabra da Peste — 2026-11-23 16:06 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-20 (semana vigente 2026-11-13; hash `8c6d12b68106`)

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 997,0 mil (pico USD 1,01 mm)
- Retorno do dia: +0,05%; acumulado: -0,30%
- Drawdown: -1,25% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,38% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,012 (limite ±0,050)
- Net: -0,34% (limite ±1,00%); gross 83,63%; long 41,64%; short -41,98%; 49 longs / 44 shorts
- VaR 99% 1d: 0,50% (limite 1,00%); ES 99% 1d: 0,66% (limite 1,25%)
- Vol realizada 21d: 2,94%; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 92,78%; realizada em 63 pregões: 95,80%; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 31

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -1.052 (-0,11% do NAV)
- NAV estimado: USD 996,0 mil; drawdown estimado: -1,35% — estágio normal
- Net/gross estimados: -0,45% / 84,74%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| AUGO | SHORT | +11,69% | +11,69% | USD -1.746 | -0,18% |
| PAGS | LONG | +4,99% | +4,99% | USD +1.419 | +0,14% |
| FSM | LONG | +7,25% | +7,25% | USD +1.236 | +0,12% |
| AERO | LONG | +6,60% | +6,60% | USD +996 | +0,10% |
| CX | SHORT | +4,63% | +4,63% | USD -951 | -0,10% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short LILAK (fechamento): +8,74% desde a entrada; +0,20% do NAV
- Short AURE3.SA (fechamento): -8,67% desde a entrada; -0,23% do NAV
- Short SMFT3.SA (fechamento): -3,07% desde a entrada; -0,07% do NAV
- Short PAX (fechamento): -8,42% desde a entrada; -0,21% do NAV
- Short FLRY3.SA (fechamento): -6,00% desde a entrada; -0,14% do NAV
- Short CX (fechamento): -13,43% desde a entrada; -0,32% do NAV
- Short AUGO (fechamento): -26,69% desde a entrada; -0,54% do NAV
- Short ASR (fechamento): +16,64% desde a entrada; +0,20% do NAV
- Short BBAS3.SA (fechamento): -5,30% desde a entrada; -0,08% do NAV
- Short TIMS3.SA (fechamento): +15,24% desde a entrada; +0,16% do NAV
- Short BRAV3.SA (fechamento): -27,57% desde a entrada; -0,47% do NAV
- Short EMBJ (fechamento): -10,63% desde a entrada; -0,15% do NAV
- Short ARCO (fechamento): -18,07% desde a entrada; -0,23% do NAV
- Short AGRO (fechamento): -23,18% desde a entrada; -0,30% do NAV
- Short BRAP4.SA (fechamento): -12,78% desde a entrada; -0,14% do NAV
- Short NU (fechamento): -22,60% desde a entrada; -0,28% do NAV
- Short MELI (fechamento): -27,25% desde a entrada; -0,36% do NAV
- Short BMA (fechamento): -16,27% desde a entrada; -0,18% do NAV
- Short SAPR11.SA (fechamento): -22,42% desde a entrada; -0,26% do NAV
- Short LAR (fechamento): -39,21% desde a entrada; -0,58% do NAV
- Short UGPA3.SA (fechamento): -19,77% desde a entrada; -0,22% do NAV
- Short ALPA4.SA (fechamento): -21,49% desde a entrada; -0,24% do NAV
- Short ENGI11.SA (fechamento): -25,81% desde a entrada; -0,28% do NAV
- Short BBDC4.SA (fechamento): -2,61% desde a entrada; -0,02% do NAV
- Short VALE (fechamento): -15,42% desde a entrada; -0,14% do NAV
- Short EQTL3.SA (fechamento): -35,17% desde a entrada; -0,38% do NAV
- Short BAP (fechamento): -8,95% desde a entrada; -0,07% do NAV
- Short BCH (fechamento): -6,97% desde a entrada; -0,05% do NAV
- Short RDOR3.SA (fechamento): -19,20% desde a entrada; -0,16% do NAV
- Short PAC (fechamento): -0,86% desde a entrada; -0,01% do NAV
- Short INTR (fechamento): -13,25% desde a entrada; -0,09% do NAV
- Short CSMG3.SA (fechamento): +1,70% desde a entrada; +0,01% do NAV
- Short VIVT3.SA (fechamento): +8,60% desde a entrada; +0,04% do NAV
- Short VBBR3.SA (fechamento): -18,08% desde a entrada; -0,10% do NAV
- Short DLO (fechamento): -12,05% desde a entrada; -0,06% do NAV
- Short ASAI3.SA (fechamento): +6,47% desde a entrada; +0,02% do NAV
- Short BRSR6.SA (fechamento): -33,07% desde a entrada; -0,17% do NAV
- Short BEEF3.SA (fechamento): +9,38% desde a entrada; +0,03% do NAV
- Short CMIG4.SA (fechamento): -9,81% desde a entrada; -0,04% do NAV
- Short AG (fechamento): -26,13% desde a entrada; -0,11% do NAV
- Short RAIL3.SA (fechamento): -9,58% desde a entrada; -0,03% do NAV
- Short LREN3.SA (fechamento): -8,36% desde a entrada; -0,02% do NAV
- Short PAM (fechamento): -23,74% desde a entrada; -0,07% do NAV
- Short TGS (fechamento): -10,68% desde a entrada; -0,02% do NAV
- Short LILAK (intradiário): +5,83% desde a entrada; +0,13% do NAV
- Short AURE3.SA (intradiário): -10,82% desde a entrada; -0,29% do NAV
- Short SMFT3.SA (intradiário): -1,86% desde a entrada; -0,04% do NAV
- Short PAX (intradiário): -4,95% desde a entrada; -0,12% do NAV
- Short FLRY3.SA (intradiário): -5,30% desde a entrada; -0,12% do NAV
- Short CX (intradiário): -9,42% desde a entrada; -0,22% do NAV
- Short AUGO (intradiário): -18,12% desde a entrada; -0,37% do NAV
- Short ASR (intradiário): +18,12% desde a entrada; +0,22% do NAV
- Short BBAS3.SA (intradiário): -4,70% desde a entrada; -0,07% do NAV
- Short TIMS3.SA (intradiário): +15,87% desde a entrada; +0,17% do NAV
- Short BRAV3.SA (intradiário): -28,30% desde a entrada; -0,48% do NAV
- Short EMBJ (intradiário): -7,79% desde a entrada; -0,11% do NAV
- Short ARCO (intradiário): -14,40% desde a entrada; -0,18% do NAV
- Short AGRO (intradiário): -21,79% desde a entrada; -0,28% do NAV
- Short BRAP4.SA (intradiário): -12,73% desde a entrada; -0,14% do NAV
- Short NU (intradiário): -19,02% desde a entrada; -0,24% do NAV
- Short MELI (intradiário): -23,68% desde a entrada; -0,31% do NAV
- Short BMA (intradiário): -13,52% desde a entrada; -0,15% do NAV
- Short SAPR11.SA (intradiário): -22,60% desde a entrada; -0,26% do NAV
- Short LAR (intradiário): -35,11% desde a entrada; -0,52% do NAV
- Short UGPA3.SA (intradiário): -19,88% desde a entrada; -0,22% do NAV
- Short ALPA4.SA (intradiário): -23,14% desde a entrada; -0,25% do NAV
- Short ENGI11.SA (intradiário): -24,80% desde a entrada; -0,27% do NAV
- Short BBDC4.SA (intradiário): -3,59% desde a entrada; -0,03% do NAV
- Short VALE (intradiário): -11,81% desde a entrada; -0,11% do NAV
- Short EQTL3.SA (intradiário): -35,92% desde a entrada; -0,38% do NAV
- Short BAP (intradiário): -4,23% desde a entrada; -0,03% do NAV
- Short BCH (intradiário): -5,31% desde a entrada; -0,04% do NAV
- Short RDOR3.SA (intradiário): -18,03% desde a entrada; -0,15% do NAV
- Short PAC (intradiário): +0,12% desde a entrada; 0,00% do NAV
- Short INTR (intradiário): -10,41% desde a entrada; -0,07% do NAV
- Short CSMG3.SA (intradiário): +2,47% desde a entrada; +0,01% do NAV
- Short VIVT3.SA (intradiário): +8,11% desde a entrada; +0,04% do NAV
- Short VBBR3.SA (intradiário): -17,21% desde a entrada; -0,09% do NAV
- Short DLO (intradiário): -7,52% desde a entrada; -0,04% do NAV
- Short ASAI3.SA (intradiário): +7,04% desde a entrada; +0,03% do NAV
- Short BRSR6.SA (intradiário): -33,07% desde a entrada; -0,17% do NAV
- Short BEEF3.SA (intradiário): +7,04% desde a entrada; +0,02% do NAV
- Short CMIG4.SA (intradiário): -11,62% desde a entrada; -0,04% do NAV
- Short AG (intradiário): -22,55% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (intradiário): -9,42% desde a entrada; -0,03% do NAV
- Short LREN3.SA (intradiário): -8,36% desde a entrada; -0,02% do NAV
- Short PAM (intradiário): -21,50% desde a entrada; -0,07% do NAV
- Short TGS (intradiário): -7,85% desde a entrada; -0,02% do NAV

## Alertas do registro de fechamento

- Preço ausente no pregão (linha não negociou; posição não reprecificada, valor mantido): ALPA4.SA, ALUP11.SA, ABEV3.SA, ASAI3.SA, AURE3.SA, AXIA3.SA, BRSR6.SA, BBAS3.SA (+40).
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (156): ANDINA-B.SN@2026-11-10 (1.0033), BCI.SN@2026-11-10 (0.9902), BSANTANDER.SN@2026-11-10 (1.0019), CENCOMALLS.SN@2026-11-10 (0.9989), CENCOSUD.SN@2026-11-10 (1.0265), CHILE.SN@2026-11-10 (1.0114), CMPC.SN@2026-11-10 (1.0068), COP…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 645.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: BOVA11.SA, ^BVSP, ^MERV.
- Limitação de dados: Aluguel B3 sem publicação nova entre 2026-11-20 e 2026-11-20 (BDI publica em D+1).
- Limitação de dados: EMBJ em 17/11/2026: predecessor selado reconciliado com Nasdaq e eventos Yahoo consultados retrospectivamente.

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
