# Risco — CDP — Cabra da Peste — 2026-11-17 16:10 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-16 (semana vigente 2026-11-13; hash `0aa6cea537b5`)

## Ações recomendadas (determinísticas)

- revisar: CURY3.SA: variação do fechamento -4.7% difere da do fechamento ajustado -2.5% — possível grupamento, desdobramento ou provento.
- revisar: EMBJ: variação do fechamento -76.2% difere da do fechamento ajustado -4.6% — possível grupamento, desdobramento ou provento.
- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `possivel_evento_societario:CURY3.SA` | CURY3.SA: variação do fechamento -4.7% difere da do fechamento ajustado -2.5% — possível grupamento, desdobramento ou provento. | conferir o evento societário antes do próximo rebalanceamento |
| SOFT | `possivel_evento_societario:EMBJ` | EMBJ: variação do fechamento -76.2% difere da do fechamento ajustado -4.6% — possível grupamento, desdobramento ou provento. | conferir o evento societário antes do próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `movimento_extremo:EMBJ` | EMBJ: fechamento variou -76.2% no dia. |  |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: +0,23%; acumulado: +0,72%
- Drawdown: -0,24% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,59% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,003 (limite ±0,050)
- Net: +0,72% (limite ±1,00%); gross 88,29%; long 44,50%; short -43,79%; 49 longs / 44 shorts
- VaR 99% 1d: 0,53% (limite 1,00%); ES 99% 1d: 0,72% (limite 1,25%)
- Vol realizada 21d: 2,25%; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 94,72%; realizada em 63 pregões: 89,52%; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 27

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -5.120 (-0,51% do NAV)
- NAV estimado: USD 1,00 mm; drawdown estimado: -0,75% — estágio normal
- Net/gross estimados: +0,21% / 88,44%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| PICS | LONG | -26,90% | -26,90% | USD -4.070 | -0,40% |
| AURE3.SA | SHORT | +3,16% | +3,31% | USD -806 | -0,08% |
| TEND3.SA | LONG | -2,82% | -2,68% | USD -536 | -0,05% |
| AUGO | SHORT | -2,56% | -2,56% | USD +458 | +0,05% |
| TEO | LONG | +2,73% | +2,73% | USD +410 | +0,04% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short LILAK (fechamento): +18,11% desde a entrada; +0,40% do NAV
- Short AURE3.SA (fechamento): -10,13% desde a entrada; -0,27% do NAV
- Short PAX (fechamento): -5,89% desde a entrada; -0,15% do NAV
- Short SMFT3.SA (fechamento): -2,79% desde a entrada; -0,07% do NAV
- Short CX (fechamento): -3,36% desde a entrada; -0,08% do NAV
- Short FLRY3.SA (fechamento): -9,28% desde a entrada; -0,21% do NAV
- Short AUGO (fechamento): -10,99% desde a entrada; -0,22% do NAV
- Short BBAS3.SA (fechamento): -0,99% desde a entrada; -0,01% do NAV
- Short ASR (fechamento): +15,08% desde a entrada; +0,18% do NAV
- Short BRAV3.SA (fechamento): -21,30% desde a entrada; -0,37% do NAV
- Short EMBJ (fechamento): -4,64% desde a entrada; -0,06% do NAV
- Short TIMS3.SA (fechamento): +14,56% desde a entrada; +0,16% do NAV
- Short ARCO (fechamento): -12,12% desde a entrada; -0,15% do NAV
- Short AGRO (fechamento): -14,96% desde a entrada; -0,19% do NAV
- Short NU (fechamento): -12,91% desde a entrada; -0,16% do NAV
- Short BRAP4.SA (fechamento): -9,94% desde a entrada; -0,11% do NAV
- Short LAR (fechamento): -30,41% desde a entrada; -0,45% do NAV
- Short MELI (fechamento): -21,50% desde a entrada; -0,28% do NAV
- Short BMA (fechamento): -9,57% desde a entrada; -0,10% do NAV
- Short UGPA3.SA (fechamento): -17,42% desde a entrada; -0,19% do NAV
- Short SAPR11.SA (fechamento): -25,24% desde a entrada; -0,30% do NAV
- Short ALPA4.SA (fechamento): -22,14% desde a entrada; -0,25% do NAV
- Short VALE (fechamento): -6,77% desde a entrada; -0,06% do NAV
- Short ENGI11.SA (fechamento): -26,04% desde a entrada; -0,29% do NAV
- Short BBDC4.SA (fechamento): +0,21% desde a entrada; 0,00% do NAV
- Short BAP (fechamento): -2,17% desde a entrada; -0,02% do NAV
- Short EQTL3.SA (fechamento): -33,44% desde a entrada; -0,36% do NAV
- Short BCH (fechamento): -2,45% desde a entrada; -0,02% do NAV
- Short PAC (fechamento): +5,36% desde a entrada; +0,03% do NAV
- Short INTR (fechamento): -4,58% desde a entrada; -0,03% do NAV
- Short RDOR3.SA (fechamento): -20,71% desde a entrada; -0,17% do NAV
- Short CSMG3.SA (fechamento): -0,87% desde a entrada; 0,00% do NAV
- Short VIVT3.SA (fechamento): +6,48% desde a entrada; +0,03% do NAV
- Short DLO (fechamento): -2,56% desde a entrada; -0,01% do NAV
- Short VBBR3.SA (fechamento): -16,53% desde a entrada; -0,09% do NAV
- Short ASAI3.SA (fechamento): +6,58% desde a entrada; +0,02% do NAV
- Short AG (fechamento): -14,22% desde a entrada; -0,06% do NAV
- Short BRSR6.SA (fechamento): -32,27% desde a entrada; -0,17% do NAV
- Short CMIG4.SA (fechamento): -9,73% desde a entrada; -0,03% do NAV
- Short BEEF3.SA (fechamento): +0,29% desde a entrada; 0,00% do NAV
- Short RAIL3.SA (fechamento): -12,33% desde a entrada; -0,04% do NAV
- Short LREN3.SA (fechamento): -3,52% desde a entrada; -0,01% do NAV
- Short PAM (fechamento): -23,35% desde a entrada; -0,07% do NAV
- Short TGS (fechamento): -6,36% desde a entrada; -0,01% do NAV
- Short LILAK (intradiário): +17,46% desde a entrada; +0,39% do NAV
- Short AURE3.SA (intradiário): -7,29% desde a entrada; -0,20% do NAV
- Short PAX (intradiário): -6,64% desde a entrada; -0,16% do NAV
- Short SMFT3.SA (intradiário): -4,05% desde a entrada; -0,10% do NAV
- Short CX (intradiário): -4,71% desde a entrada; -0,11% do NAV
- Short FLRY3.SA (intradiário): -8,97% desde a entrada; -0,21% do NAV
- Short AUGO (intradiário): -13,26% desde a entrada; -0,27% do NAV
- Short BBAS3.SA (intradiário): -0,93% desde a entrada; -0,01% do NAV
- Short ASR (intradiário): +15,59% desde a entrada; +0,19% do NAV
- Short BRAV3.SA (intradiário): -21,53% desde a entrada; -0,37% do NAV
- Short EMBJ (intradiário): -3,67% desde a entrada; -0,05% do NAV
- Short TIMS3.SA (intradiário): +17,81% desde a entrada; +0,19% do NAV
- Short ARCO (intradiário): -13,64% desde a entrada; -0,17% do NAV
- Short AGRO (intradiário): -14,51% desde a entrada; -0,19% do NAV
- Short NU (intradiário): -15,14% desde a entrada; -0,19% do NAV
- Short BRAP4.SA (intradiário): -9,00% desde a entrada; -0,10% do NAV
- Short LAR (intradiário): -28,63% desde a entrada; -0,42% do NAV
- Short MELI (intradiário): -22,68% desde a entrada; -0,30% do NAV
- Short BMA (intradiário): -9,00% desde a entrada; -0,10% do NAV
- Short UGPA3.SA (intradiário): -18,50% desde a entrada; -0,20% do NAV
- Short SAPR11.SA (intradiário): -23,15% desde a entrada; -0,28% do NAV
- Short ALPA4.SA (intradiário): -21,25% desde a entrada; -0,24% do NAV
- Short VALE (intradiário): -6,51% desde a entrada; -0,06% do NAV
- Short ENGI11.SA (intradiário): -24,78% desde a entrada; -0,27% do NAV
- Short BBDC4.SA (intradiário): +0,49% desde a entrada; 0,00% do NAV
- Short BAP (intradiário): -2,28% desde a entrada; -0,02% do NAV
- Short EQTL3.SA (intradiário): -33,16% desde a entrada; -0,36% do NAV
- Short BCH (intradiário): -2,08% desde a entrada; -0,01% do NAV
- Short PAC (intradiário): +5,75% desde a entrada; +0,04% do NAV
- Short INTR (intradiário): -5,66% desde a entrada; -0,04% do NAV
- Short RDOR3.SA (intradiário): -18,37% desde a entrada; -0,15% do NAV
- Short CSMG3.SA (intradiário): +1,96% desde a entrada; +0,01% do NAV
- Short VIVT3.SA (intradiário): +10,82% desde a entrada; +0,06% do NAV
- Short DLO (intradiário): -8,69% desde a entrada; -0,04% do NAV
- Short VBBR3.SA (intradiário): -17,13% desde a entrada; -0,10% do NAV
- Short ASAI3.SA (intradiário): +8,40% desde a entrada; +0,03% do NAV
- Short AG (intradiário): -13,71% desde a entrada; -0,06% do NAV
- Short BRSR6.SA (intradiário): -32,43% desde a entrada; -0,17% do NAV
- Short CMIG4.SA (intradiário): -10,39% desde a entrada; -0,04% do NAV
- Short BEEF3.SA (intradiário): +1,47% desde a entrada; 0,00% do NAV
- Short RAIL3.SA (intradiário): -8,77% desde a entrada; -0,03% do NAV
- Short LREN3.SA (intradiário): -4,03% desde a entrada; -0,01% do NAV
- Short PAM (intradiário): -21,38% desde a entrada; -0,06% do NAV
- Short TGS (intradiário): -4,46% desde a entrada; -0,01% do NAV

## Alertas do registro de fechamento

- RETIFICAÇÃO FINANCEIRA: evento corporativo aplicado; original preservado.
- Evento corporativo verificado em EMBJ: quantidade multiplicada por 4; retorno em base comparável.
- Preço ausente no pregão (linha não negociou; posição não reprecificada, valor mantido): ALPEKA.MX, LABB.MX.
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
- Limitação de dados: Retorno total por preço (sem barra anterior na janela) para: EMBJ.
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (199): AC.MX@2026-11-06 (0.9994), ALPEKA.MX@2026-11-06 (0.9993), ALSEA.MX@2026-11-06 (0.9990), AMXB.MX@2026-11-06 (0.9983), ASURB.MX@2026-11-06 (1.0007), BBAJIOO.MX@2026-11-06 (0.9975), BIMBOA.MX@2026-11-06 (1.0011), BOLSAA.MX@2026-1…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 630.
- Limitação de dados: Câmbio ausente no pregão para: COP.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV, ^MXX.
- Limitação de dados: Notícias indisponíveis para 1 emissores.
- Limitação de dados: QA paridade ADR: EMBJ vs EMBJ3.SA desvio -75.0% no pregão (mediana -0.4%; tolerância 3%).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
