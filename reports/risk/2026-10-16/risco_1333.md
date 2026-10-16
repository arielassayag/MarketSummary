# Risco — CDP — Cabra da Peste — 2026-10-16 13:33 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-15 (semana vigente 2026-10-09; hash `dc555d18a849`)
- Decisão da semana 2026-10-16 gravada, a executar no fechamento: vol ex-ante 3,52%, beta 0,000, gross 67,51%, net +0,04%, 38 longs / 35 shorts

## Ações recomendadas (determinísticas)

- revisar: Exposição líquida +1,69% fora do limite ±1,00% (net neutral)
- revisar: Shorts com risco de squeeze HIGH: 2 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `net_fora_do_limite` | Exposição líquida +1,69% fora do limite ±1,00% (net neutral) | reequilibrar no próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 2 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 1,00 mm (pico USD 1,00 mm)
- Retorno do dia: -0,01%; acumulado: +0,41%
- Drawdown: -0,01% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,55% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,014 (limite ±0,050)
- Net: +1,69% (limite ±1,00%); gross 62,95%; long 32,32%; short -30,63%; 37 longs / 36 shorts
- VaR 99% 1d: 0,52% (limite 1,00%); ES 99% 1d: 0,60% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 92,51%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 5

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD +971 (+0,10% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: 0,00% — estágio normal
- Net/gross estimados: +1,79% / 62,95%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| FMX | SHORT | +4,91% | +4,91% | USD -630 | -0,06% |
| PBR | LONG | +1,76% | +1,76% | USD +592 | +0,06% |
| LABB.MX | LONG | +1,89% | +1,60% | USD +473 | +0,05% |
| SUZB3.SA | LONG | +1,65% | +2,08% | USD +387 | +0,04% |
| PAGS | LONG | -1,39% | -1,39% | USD -325 | -0,03% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,4 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 2
- Short PAX (fechamento): +1,20% desde a entrada; +0,03% do NAV
- Short INTR (fechamento): -11,98% desde a entrada; -0,25% do NAV
- Short UGPA3.SA (fechamento): -1,15% desde a entrada; -0,02% do NAV
- Short CX (fechamento): +5,23% desde a entrada; +0,07% do NAV
- Short FMX (fechamento): +1,47% desde a entrada; +0,02% do NAV
- Short BBDC4.SA (fechamento): -4,07% desde a entrada; -0,05% do NAV
- Short YPF (fechamento): +2,14% desde a entrada; +0,03% do NAV
- Short EQTL3.SA (fechamento): -5,12% desde a entrada; -0,06% do NAV
- Short ALOS3.SA (fechamento): -3,32% desde a entrada; -0,04% do NAV
- Short BRAV3.SA (fechamento): +0,58% desde a entrada; +0,01% do NAV
- Short ASR (fechamento): +1,44% desde a entrada; +0,01% do NAV
- Short AGRO (fechamento): -1,86% desde a entrada; -0,02% do NAV
- Short VBBR3.SA (fechamento): -1,71% desde a entrada; -0,02% do NAV
- Short LAR (fechamento): -9,49% desde a entrada; -0,10% do NAV
- Short ALPA4.SA (fechamento): +8,88% desde a entrada; +0,07% do NAV
- Short SGML (fechamento): -5,99% desde a entrada; -0,06% do NAV
- Short SAPR11.SA (fechamento): -12,54% desde a entrada; -0,13% do NAV
- Short CIB (fechamento): +3,00% desde a entrada; +0,02% do NAV
- Short MELI (fechamento): -1,74% desde a entrada; -0,01% do NAV
- Short ORVR3.SA (fechamento): -6,95% desde a entrada; -0,05% do NAV
- Short BCH (fechamento): +0,54% desde a entrada; 0,00% do NAV
- Short LILAK (fechamento): +0,86% desde a entrada; +0,01% do NAV
- Short EMBJ (fechamento): +1,32% desde a entrada; +0,01% do NAV
- Short USIM5.SA (fechamento): -7,95% desde a entrada; -0,05% do NAV
- Short RDOR3.SA (fechamento): -6,34% desde a entrada; -0,04% do NAV
- Short ARCO (fechamento): +3,73% desde a entrada; +0,02% do NAV
- Short CBAV3.SA (fechamento): +0,53% desde a entrada; 0,00% do NAV
- Short CSMG3.SA (fechamento): -3,97% desde a entrada; -0,02% do NAV
- Short DLO (fechamento): -0,85% desde a entrada; 0,00% do NAV
- Short KLBN11.SA (fechamento): -0,11% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (fechamento): -3,05% desde a entrada; -0,01% do NAV
- Short SBSP3.SA (fechamento): -5,15% desde a entrada; -0,02% do NAV
- Short BRSR6.SA (fechamento): -9,22% desde a entrada; -0,04% do NAV
- Short OMAB (fechamento): +1,16% desde a entrada; 0,00% do NAV
- Short BSAC (fechamento): +1,86% desde a entrada; 0,00% do NAV
- Short EGIE3.SA (fechamento): -1,17% desde a entrada; 0,00% do NAV
- Short PAX (intradiário): +0,47% desde a entrada; +0,01% do NAV
- Short INTR (intradiário): -13,09% desde a entrada; -0,28% do NAV
- Short UGPA3.SA (intradiário): +0,08% desde a entrada; 0,00% do NAV
- Short CX (intradiário): +7,55% desde a entrada; +0,09% do NAV
- Short FMX (intradiário): +6,45% desde a entrada; +0,08% do NAV
- Short BBDC4.SA (intradiário): -5,69% desde a entrada; -0,07% do NAV
- Short YPF (intradiário): +2,82% desde a entrada; +0,03% do NAV
- Short EQTL3.SA (intradiário): -5,28% desde a entrada; -0,06% do NAV
- Short ALOS3.SA (intradiário): -4,80% desde a entrada; -0,06% do NAV
- Short BRAV3.SA (intradiário): +2,28% desde a entrada; +0,02% do NAV
- Short ASR (intradiário): +1,26% desde a entrada; +0,01% do NAV
- Short AGRO (intradiário): -1,27% desde a entrada; -0,01% do NAV
- Short VBBR3.SA (intradiário): -1,44% desde a entrada; -0,02% do NAV
- Short LAR (intradiário): -10,80% desde a entrada; -0,11% do NAV
- Short ALPA4.SA (intradiário): +5,52% desde a entrada; +0,05% do NAV
- Short SGML (intradiário): -6,95% desde a entrada; -0,07% do NAV
- Short SAPR11.SA (intradiário): -14,33% desde a entrada; -0,15% do NAV
- Short CIB (intradiário): +3,21% desde a entrada; +0,03% do NAV
- Short MELI (intradiário): -2,67% desde a entrada; -0,02% do NAV
- Short ORVR3.SA (intradiário): -9,63% desde a entrada; -0,08% do NAV
- Short BCH (intradiário): -0,13% desde a entrada; 0,00% do NAV
- Short LILAK (intradiário): -0,55% desde a entrada; 0,00% do NAV
- Short EMBJ (intradiário): +1,17% desde a entrada; +0,01% do NAV
- Short USIM5.SA (intradiário): -7,40% desde a entrada; -0,05% do NAV
- Short RDOR3.SA (intradiário): -7,48% desde a entrada; -0,04% do NAV
- Short ARCO (intradiário): +3,11% desde a entrada; +0,02% do NAV
- Short CBAV3.SA (intradiário): +0,36% desde a entrada; 0,00% do NAV
- Short CSMG3.SA (intradiário): -5,02% desde a entrada; -0,02% do NAV
- Short DLO (intradiário): -3,94% desde a entrada; -0,02% do NAV
- Short KLBN11.SA (intradiário): +0,39% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (intradiário): -3,22% desde a entrada; -0,01% do NAV
- Short SBSP3.SA (intradiário): -5,65% desde a entrada; -0,02% do NAV
- Short BRSR6.SA (intradiário): -9,91% desde a entrada; -0,04% do NAV
- Short OMAB (intradiário): +0,70% desde a entrada; 0,00% do NAV
- Short BSAC (intradiário): +1,06% desde a entrada; 0,00% do NAV
- Short EGIE3.SA (intradiário): -1,32% desde a entrada; 0,00% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Exposição líquida +1,69% fora do limite ±1,00% (net neutral).
- Short ALPA4.SA (BR_ALPARGATAS) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
- Short DLO (LA_DLOCAL) com risco de squeeze HIGH (era MEDIUM na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (352): AC.MX@2026-10-05 (0.9995), ALPEKA.MX@2026-10-05 (1.0048), ALSEA.MX@2026-10-05 (0.9998), AMXB.MX@2026-10-05 (0.9985), ANDINA-B.SN@2026-10-05 (0.9592), ASURB.MX@2026-10-05 (0.9966), BBAJIOO.MX@2026-10-05 (0.9990), BCI.SN@2026-10…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1711.
- Limitação de dados: QA paridade ADR: BAK vs BRKM5.SA desvio +6.8% no pregão (mediana -0.2%; tolerância 3%).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -1.9% no pregão (mediana -3.5%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
