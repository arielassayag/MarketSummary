# Risco — CDP — Cabra da Peste — 2026-11-27 16:03 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-26 (semana vigente 2026-11-13; hash `22ca829ed6ee`)
- Decisão da semana 2026-11-27 gravada, a executar no fechamento: vol ex-ante 3,64%, beta +0,001, gross 93,80%, net +0,77%, 45 longs / 47 shorts

## Ações recomendadas (determinísticas)

- revisar: Exposição líquida -1,25% fora do limite ±1,00% (net neutral)
- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento
- revisar: STOP DE SQUEEZE intradiário: short ASAI3.SA (BR_ASSAI) perde 27,58% desde a entrada (limite 25,00%) — o corte à metade e o veto de compra valem se o stop se confirmar num fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `net_fora_do_limite` | Exposição líquida -1,25% fora do limite ±1,00% (net neutral) | reequilibrar no próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| SOFT | `stop_squeeze_posicao_ASAI3.SA` | STOP DE SQUEEZE intradiário: short ASAI3.SA (BR_ASSAI) perde 27,58% desde a entrada (limite 25,00%) — o corte à metade e o veto de compra valem se o stop se confirmar num fechamento | aviso antecipado: o corte à metade e o veto de compra valem se o short estiver em stop num fechamento (registro diário); dois shorts distintos em stop dentro de 5 pregões ligam o kill switch |
| INFO | `idio_realizada_63d_abaixo_do_piso` | Fatia idiossincrática realizada (63 pregões) 84,8% abaixo do piso 85% | acompanhar: medida realizada com amostra curta; a decisão usa o modelo ex-ante |

## NAV e drawdown (último fechamento)

- NAV: USD 988,7 mil (pico USD 1,01 mm)
- Retorno do dia: -0,51%; acumulado: -1,13%
- Drawdown: -2,07% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,81% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,030 (limite ±0,050)
- Net: -1,25% (limite ±1,00%); gross 91,52%; long 45,14%; short -46,39%; 49 longs / 44 shorts
- VaR 99% 1d: 0,56% (limite 1,00%); ES 99% 1d: 0,72% (limite 1,25%)
- Vol realizada 21d: 3,40%; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 85,95%; realizada em 63 pregões: 84,79%; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 35

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD +4.002 (+0,40% do NAV)
- NAV estimado: USD 992,7 mil; drawdown estimado: -1,67% — estágio normal
- Net/gross estimados: -0,84% / 95,01%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| TEND3.SA | LONG | +12,05% | +14,54% | USD +3.010 | +0,30% |
| PAGS | LONG | +7,40% | +7,40% | USD +2.216 | +0,22% |
| AURE3.SA | SHORT | +3,42% | +5,72% | USD -1.564 | -0,16% |
| SMFT3.SA | SHORT | +3,30% | +5,58% | USD -1.521 | -0,15% |
| PAX | SHORT | +6,20% | +6,20% | USD -1.516 | -0,15% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,3 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short AURE3.SA (fechamento): -1,46% desde a entrada; -0,04% do NAV
- Short SMFT3.SA (fechamento): +11,40% desde a entrada; +0,28% do NAV
- Short FLRY3.SA (fechamento): +6,19% desde a entrada; +0,15% do NAV
- Short LILAK (fechamento): +11,52% desde a entrada; +0,26% do NAV
- Short PAX (fechamento): -1,58% desde a entrada; -0,04% do NAV
- Short CX (fechamento): -7,74% desde a entrada; -0,19% do NAV
- Short AUGO (fechamento): -19,12% desde a entrada; -0,39% do NAV
- Short BBAS3.SA (fechamento): +9,54% desde a entrada; +0,14% do NAV
- Short ASR (fechamento): +20,38% desde a entrada; +0,25% do NAV
- Short TIMS3.SA (fechamento): +20,43% desde a entrada; +0,23% do NAV
- Short BRAV3.SA (fechamento): -25,25% desde a entrada; -0,45% do NAV
- Short EMBJ (fechamento): -9,51% desde a entrada; -0,13% do NAV
- Short ARCO (fechamento): -12,37% desde a entrada; -0,16% do NAV
- Short NU (fechamento): -15,11% desde a entrada; -0,19% do NAV
- Short BRAP4.SA (fechamento): -11,20% desde a entrada; -0,13% do NAV
- Short AGRO (fechamento): -20,93% desde a entrada; -0,28% do NAV
- Short MELI (fechamento): -21,22% desde a entrada; -0,28% do NAV
- Short SAPR11.SA (fechamento): -18,26% desde a entrada; -0,22% do NAV
- Short LAR (fechamento): -33,41% desde a entrada; -0,50% do NAV
- Short UGPA3.SA (fechamento): -15,78% desde a entrada; -0,18% do NAV
- Short BMA (fechamento): -15,45% desde a entrada; -0,17% do NAV
- Short ENGI11.SA (fechamento): -17,92% desde a entrada; -0,20% do NAV
- Short ALPA4.SA (fechamento): -20,37% desde a entrada; -0,24% do NAV
- Short BBDC4.SA (fechamento): +11,48% desde a entrada; +0,10% do NAV
- Short EQTL3.SA (fechamento): -25,66% desde a entrada; -0,29% do NAV
- Short VALE (fechamento): -12,57% desde a entrada; -0,11% do NAV
- Short RDOR3.SA (fechamento): -11,89% desde a entrada; -0,10% do NAV
- Short BAP (fechamento): -5,05% desde a entrada; -0,04% do NAV
- Short CSMG3.SA (fechamento): +14,98% desde a entrada; +0,09% do NAV
- Short PAC (fechamento): +4,02% desde a entrada; +0,03% do NAV
- Short INTR (fechamento): -3,37% desde a entrada; -0,02% do NAV
- Short BCH (fechamento): -6,43% desde a entrada; -0,05% do NAV
- Short VIVT3.SA (fechamento): +11,16% desde a entrada; +0,06% do NAV
- Short VBBR3.SA (fechamento): -4,30% desde a entrada; -0,02% do NAV
- Short ASAI3.SA (fechamento): +21,79% desde a entrada; +0,08% do NAV
- Short DLO (fechamento): -8,18% desde a entrada; -0,04% do NAV
- Short BRSR6.SA (fechamento): -29,26% desde a entrada; -0,16% do NAV
- Short BEEF3.SA (fechamento): +14,08% desde a entrada; +0,04% do NAV
- Short CMIG4.SA (fechamento): -6,92% desde a entrada; -0,03% do NAV
- Short AG (fechamento): -23,97% desde a entrada; -0,10% do NAV
- Short RAIL3.SA (fechamento): -3,66% desde a entrada; -0,01% do NAV
- Short LREN3.SA (fechamento): +0,91% desde a entrada; 0,00% do NAV
- Short PAM (fechamento): -21,61% desde a entrada; -0,07% do NAV
- Short TGS (fechamento): -7,62% desde a entrada; -0,02% do NAV
- Short AURE3.SA (intradiário): +1,91% desde a entrada; +0,05% do NAV
- Short SMFT3.SA (intradiário): +15,07% desde a entrada; +0,38% do NAV
- Short FLRY3.SA (intradiário): +6,41% desde a entrada; +0,16% do NAV
- Short LILAK (intradiário): +15,62% desde a entrada; +0,35% do NAV
- Short PAX (intradiário): +4,53% desde a entrada; +0,11% do NAV
- Short CX (intradiário): -5,41% desde a entrada; -0,13% do NAV
- Short AUGO (intradiário): -12,50% desde a entrada; -0,25% do NAV
- Short BBAS3.SA (intradiário): +11,06% desde a entrada; +0,17% do NAV
- Short ASR (intradiário): +17,46% desde a entrada; +0,21% do NAV
- Short TIMS3.SA (intradiário): +18,23% desde a entrada; +0,21% do NAV
- Short BRAV3.SA (intradiário): -24,46% desde a entrada; -0,45% do NAV
- Short EMBJ (intradiário): -4,08% desde a entrada; -0,06% do NAV
- Short ARCO (intradiário): -10,09% desde a entrada; -0,13% do NAV
- Short NU (intradiário): -11,33% desde a entrada; -0,14% do NAV
- Short BRAP4.SA (intradiário): -12,31% desde a entrada; -0,14% do NAV
- Short AGRO (intradiário): -19,75% desde a entrada; -0,26% do NAV
- Short MELI (intradiário): -17,70% desde a entrada; -0,23% do NAV
- Short SAPR11.SA (intradiário): -18,97% desde a entrada; -0,24% do NAV
- Short LAR (intradiário): -30,41% desde a entrada; -0,45% do NAV
- Short UGPA3.SA (intradiário): -17,83% desde a entrada; -0,21% do NAV
- Short BMA (intradiário): -12,04% desde a entrada; -0,13% do NAV
- Short ENGI11.SA (intradiário): -16,11% desde a entrada; -0,19% do NAV
- Short ALPA4.SA (intradiário): -18,54% desde a entrada; -0,22% do NAV
- Short BBDC4.SA (intradiário): +12,68% desde a entrada; +0,11% do NAV
- Short EQTL3.SA (intradiário): -24,18% desde a entrada; -0,28% do NAV
- Short VALE (intradiário): -8,47% desde a entrada; -0,08% do NAV
- Short RDOR3.SA (intradiário): -10,59% desde a entrada; -0,09% do NAV
- Short BAP (intradiário): -2,33% desde a entrada; -0,02% do NAV
- Short CSMG3.SA (intradiário): +14,58% desde a entrada; +0,09% do NAV
- Short PAC (intradiário): +4,38% desde a entrada; +0,03% do NAV
- Short INTR (intradiário): +12,29% desde a entrada; +0,09% do NAV
- Short BCH (intradiário): -3,29% desde a entrada; -0,02% do NAV
- Short VIVT3.SA (intradiário): +9,47% desde a entrada; +0,05% do NAV
- Short VBBR3.SA (intradiário): -7,91% desde a entrada; -0,05% do NAV
- Short ASAI3.SA (intradiário): +27,58% desde a entrada; +0,11% do NAV **STOP**
- Short DLO (intradiário): -6,14% desde a entrada; -0,03% do NAV
- Short BRSR6.SA (intradiário): -27,11% desde a entrada; -0,15% do NAV
- Short BEEF3.SA (intradiário): +14,37% desde a entrada; +0,05% do NAV
- Short CMIG4.SA (intradiário): -6,76% desde a entrada; -0,03% do NAV
- Short AG (intradiário): -16,52% desde a entrada; -0,07% do NAV
- Short RAIL3.SA (intradiário): -3,18% desde a entrada; -0,01% do NAV
- Short LREN3.SA (intradiário): +5,74% desde a entrada; +0,02% do NAV
- Short PAM (intradiário): -20,49% desde a entrada; -0,06% do NAV
- Short TGS (intradiário): -5,16% desde a entrada; -0,01% do NAV

## Alertas do registro de fechamento

- Preço ausente no pregão (linha não negociou; posição não reprecificada, valor mantido): AGRO, BBAR, CEPU, IRS, LAR, BMA, PAM, TEO (+35).
- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Exposição líquida -1,25% fora do limite ±1,00% (net neutral).
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (259): BAK@2026-11-16 (0.9999), SID@2026-11-16 (0.9973), AC.MX@2026-11-17 (1.0022), ALPEKA.MX@2026-11-17 (1.0038), ALSEA.MX@2026-11-17 (1.0024), AMXB.MX@2026-11-17 (0.9996), ASURB.MX@2026-11-17 (1.0019), BAK@2026-11-17 (0.9999), BBAJ…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 843.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: ARGT, COLO, ECH, EEM, EPU, EWW, EWZ, ILF, SPY, ^MERV.
- Limitação de dados: EMBJ em 17/11/2026: predecessor selado reconciliado com Nasdaq e eventos Yahoo consultados retrospectivamente.

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
