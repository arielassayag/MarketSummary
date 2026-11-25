# Risco — CDP — Cabra da Peste — 2026-11-25 16:04 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-24 (semana vigente 2026-11-13; hash `0d89fab7dab3`)

## Ações recomendadas (determinísticas)

- revisar: UGPA3.SA: variação do fechamento -4.3% difere da do fechamento ajustado -1.1% — possível grupamento, desdobramento ou provento.
- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `possivel_evento_societario:UGPA3.SA` | UGPA3.SA: variação do fechamento -4.3% difere da do fechamento ajustado -1.1% — possível grupamento, desdobramento ou provento. | conferir o evento societário antes do próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 994,4 mil (pico USD 1,01 mm)
- Retorno do dia: -0,30%; acumulado: -0,56%
- Drawdown: -1,51% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,46% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,017 (limite ±0,050)
- Net: -0,66% (limite ±1,00%); gross 84,80%; long 42,07%; short -42,73%; 49 longs / 44 shorts
- VaR 99% 1d: 0,51% (limite 1,00%); ES 99% 1d: 0,66% (limite 1,25%)
- Vol realizada 21d: 3,03%; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 90,88%; realizada em 63 pregões: 95,20%; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 33

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -1.319 (-0,13% do NAV)
- NAV estimado: USD 993,0 mil; drawdown estimado: -1,64% — estágio normal
- Net/gross estimados: -0,79% / 87,28%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| SMFT3.SA | SHORT | +4,96% | +6,58% | USD -1.516 | -0,15% |
| BRAV3.SA | SHORT | +6,88% | +8,54% | USD -978 | -0,10% |
| AUGO | SHORT | +5,70% | +5,70% | USD -906 | -0,09% |
| TEO | LONG | +5,85% | +5,85% | USD +836 | +0,08% |
| BBAS3.SA | SHORT | +3,81% | +5,42% | USD -723 | -0,07% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short LILAK (fechamento): +12,06% desde a entrada; +0,27% do NAV
- Short AURE3.SA (fechamento): -9,13% desde a entrada; -0,24% do NAV
- Short PAX (fechamento): -4,21% desde a entrada; -0,11% do NAV
- Short SMFT3.SA (fechamento): -1,59% desde a entrada; -0,04% do NAV
- Short FLRY3.SA (fechamento): -1,63% desde a entrada; -0,04% do NAV
- Short CX (fechamento): -11,10% desde a entrada; -0,26% do NAV
- Short AUGO (fechamento): -22,04% desde a entrada; -0,45% do NAV
- Short ASR (fechamento): +19,23% desde a entrada; +0,23% do NAV
- Short BBAS3.SA (fechamento): -6,09% desde a entrada; -0,09% do NAV
- Short EMBJ (fechamento): -8,14% desde a entrada; -0,11% do NAV
- Short TIMS3.SA (fechamento): +14,61% desde a entrada; +0,16% do NAV
- Short BRAV3.SA (fechamento): -32,71% desde a entrada; -0,56% do NAV
- Short ARCO (fechamento): -13,89% desde a entrada; -0,18% do NAV
- Short MELI (fechamento): -22,13% desde a entrada; -0,29% do NAV
- Short NU (fechamento): -18,54% desde a entrada; -0,23% do NAV
- Short AGRO (fechamento): -24,16% desde a entrada; -0,32% do NAV
- Short LAR (fechamento): -34,61% desde a entrada; -0,52% do NAV
- Short BRAP4.SA (fechamento): -17,10% desde a entrada; -0,19% do NAV
- Short BMA (fechamento): -15,89% desde a entrada; -0,18% do NAV
- Short SAPR11.SA (fechamento): -22,22% desde a entrada; -0,26% do NAV
- Short UGPA3.SA (fechamento): -22,69% desde a entrada; -0,25% do NAV
- Short ALPA4.SA (fechamento): -22,67% desde a entrada; -0,25% do NAV
- Short ENGI11.SA (fechamento): -24,22% desde a entrada; -0,26% do NAV
- Short VALE (fechamento): -16,49% desde a entrada; -0,15% do NAV
- Short BBDC4.SA (fechamento): -4,08% desde a entrada; -0,03% do NAV
- Short EQTL3.SA (fechamento): -33,89% desde a entrada; -0,36% do NAV
- Short BAP (fechamento): -7,61% desde a entrada; -0,06% do NAV
- Short PAC (fechamento): +2,72% desde a entrada; +0,02% do NAV
- Short RDOR3.SA (fechamento): -17,67% desde a entrada; -0,14% do NAV
- Short BCH (fechamento): -7,50% desde a entrada; -0,05% do NAV
- Short INTR (fechamento): -8,19% desde a entrada; -0,06% do NAV
- Short CSMG3.SA (fechamento): +4,01% desde a entrada; +0,02% do NAV
- Short VIVT3.SA (fechamento): +8,85% desde a entrada; +0,04% do NAV
- Short VBBR3.SA (fechamento): -15,12% desde a entrada; -0,08% do NAV
- Short DLO (fechamento): -10,15% desde a entrada; -0,05% do NAV
- Short ASAI3.SA (fechamento): +9,53% desde a entrada; +0,03% do NAV
- Short BRSR6.SA (fechamento): -33,93% desde a entrada; -0,17% do NAV
- Short BEEF3.SA (fechamento): +10,26% desde a entrada; +0,03% do NAV
- Short CMIG4.SA (fechamento): -10,80% desde a entrada; -0,04% do NAV
- Short AG (fechamento): -27,15% desde a entrada; -0,11% do NAV
- Short RAIL3.SA (fechamento): -9,26% desde a entrada; -0,03% do NAV
- Short LREN3.SA (fechamento): -7,35% desde a entrada; -0,02% do NAV
- Short PAM (fechamento): -23,07% desde a entrada; -0,07% do NAV
- Short TGS (fechamento): -9,66% desde a entrada; -0,02% do NAV
- Short LILAK (intradiário): +12,24% desde a entrada; +0,28% do NAV
- Short AURE3.SA (intradiário): -8,52% desde a entrada; -0,23% do NAV
- Short PAX (intradiário): -1,63% desde a entrada; -0,04% do NAV
- Short SMFT3.SA (intradiário): +3,29% desde a entrada; +0,08% do NAV
- Short FLRY3.SA (intradiário): -1,32% desde a entrada; -0,03% do NAV
- Short CX (intradiário): -8,49% desde a entrada; -0,20% do NAV
- Short AUGO (intradiário): -17,59% desde a entrada; -0,36% do NAV
- Short ASR (intradiário): +19,77% desde a entrada; +0,24% do NAV
- Short BBAS3.SA (intradiário): -2,52% desde a entrada; -0,04% do NAV
- Short EMBJ (intradiário): -9,26% desde a entrada; -0,13% do NAV
- Short TIMS3.SA (intradiário): +14,35% desde a entrada; +0,16% do NAV
- Short BRAV3.SA (intradiário): -28,08% desde a entrada; -0,49% do NAV
- Short ARCO (intradiário): -12,31% desde a entrada; -0,16% do NAV
- Short MELI (intradiário): -20,38% desde a entrada; -0,27% do NAV
- Short NU (intradiário): -15,01% desde a entrada; -0,19% do NAV
- Short AGRO (intradiário): -21,71% desde a entrada; -0,28% do NAV
- Short LAR (intradiário): -32,81% desde a entrada; -0,49% do NAV
- Short BRAP4.SA (intradiário): -14,41% desde a entrada; -0,16% do NAV
- Short BMA (intradiário): -15,67% desde a entrada; -0,17% do NAV
- Short SAPR11.SA (intradiário): -21,33% desde a entrada; -0,25% do NAV
- Short UGPA3.SA (intradiário): -21,64% desde a entrada; -0,24% do NAV
- Short ALPA4.SA (intradiário): -23,32% desde a entrada; -0,26% do NAV
- Short ENGI11.SA (intradiário): -22,51% desde a entrada; -0,25% do NAV
- Short VALE (intradiário): -12,49% desde a entrada; -0,11% do NAV
- Short BBDC4.SA (intradiário): -0,28% desde a entrada; 0,00% do NAV
- Short EQTL3.SA (intradiário): -31,63% desde a entrada; -0,34% do NAV
- Short BAP (intradiário): -5,63% desde a entrada; -0,04% do NAV
- Short PAC (intradiário): +3,85% desde a entrada; +0,02% do NAV
- Short RDOR3.SA (intradiário): -17,70% desde a entrada; -0,15% do NAV
- Short BCH (intradiário): -6,86% desde a entrada; -0,05% do NAV
- Short INTR (intradiário): -3,25% desde a entrada; -0,02% do NAV
- Short CSMG3.SA (intradiário): +7,02% desde a entrada; +0,04% do NAV
- Short VIVT3.SA (intradiário): +7,22% desde a entrada; +0,04% do NAV
- Short VBBR3.SA (intradiário): -13,43% desde a entrada; -0,07% do NAV
- Short DLO (intradiário): -8,55% desde a entrada; -0,04% do NAV
- Short ASAI3.SA (intradiário): +11,80% desde a entrada; +0,04% do NAV
- Short BRSR6.SA (intradiário): -32,32% desde a entrada; -0,17% do NAV
- Short BEEF3.SA (intradiário): +13,49% desde a entrada; +0,04% do NAV
- Short CMIG4.SA (intradiário): -11,38% desde a entrada; -0,04% do NAV
- Short AG (intradiário): -23,92% desde a entrada; -0,10% do NAV
- Short RAIL3.SA (intradiário): -7,70% desde a entrada; -0,02% do NAV
- Short LREN3.SA (intradiário): -5,24% desde a entrada; -0,01% do NAV
- Short PAM (intradiário): -22,00% desde a entrada; -0,07% do NAV
- Short TGS (intradiário): -8,22% desde a entrada; -0,02% do NAV

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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (185): BAK@2026-11-16 (0.9999), SID@2026-11-16 (0.9973), AC.MX@2026-11-17 (1.0022), ALPEKA.MX@2026-11-17 (1.0038), ALSEA.MX@2026-11-17 (1.0024), AMXB.MX@2026-11-17 (0.9996), ASURB.MX@2026-11-17 (1.0019), BAK@2026-11-17 (0.9999), BBAJ…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 565.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: Aluguel B3 indisponível: RuntimeError('Fonte de aluguel B3 (BDI) indisponível: 2026-11-23: Falha de rede em POST https://arquivos.b3.com.br/bdi/table/BTBLendingOpenPosition/2026-11-23/2026-11-23/1/1000: ReadTimeout(ReadTimeoutError("HTTPSConnectionPool(host=\'arquivos.b3.com.br\', port=443): Read t…
- Limitação de dados: Aluguel B3 (BDI) ausente para pregões já fechados: 2026-11-23 (nova tentativa nos próximos incrementos enquanto estiverem na janela D-21).
- Limitação de dados: QA paridade ADR: BAK vs BRKM5.SA desvio -7.6% no pregão (mediana -1.7%; tolerância 3%).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -7.7% no pregão (mediana -0.8%; tolerância 3%).
- Limitação de dados: EMBJ em 17/11/2026: predecessor selado reconciliado com Nasdaq e eventos Yahoo consultados retrospectivamente.

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
