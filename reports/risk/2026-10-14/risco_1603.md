# Risco — CDP — Cabra da Peste — 2026-10-14 16:03 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-13 (semana vigente 2026-10-09; hash `8d21ca4494a8`)

## Ações recomendadas (determinísticas)

- revisar: Exposição líquida +1,48% fora do limite ±1,00% (net neutral)
- revisar: Shorts com risco de squeeze HIGH: 3 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `net_fora_do_limite` | Exposição líquida +1,48% fora do limite ±1,00% (net neutral) | reequilibrar no próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 3 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `janela_incompleta` | Janela de 5 registros incompleta (3): gatilho de 5 pregões não avaliado. |  |

## NAV e drawdown (último fechamento)

- NAV: USD 1,00 mm (pico USD 1,00 mm)
- Retorno do dia: +0,16%; acumulado: +0,17%
- Drawdown: 0,00% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,63% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,013 (limite ±0,050)
- Net: +1,48% (limite ±1,00%); gross 64,34%; long 32,91%; short -31,43%; 37 longs / 36 shorts
- VaR 99% 1d: 0,53% (limite 1,00%); ES 99% 1d: 0,61% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 92,96%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 3

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD +2.791 (+0,28% do NAV)
- NAV estimado: USD 1,00 mm; drawdown estimado: 0,00% — estágio normal
- Net/gross estimados: +1,75% / 63,33%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| INTR | SHORT | -6,04% | -6,04% | USD +1.250 | +0,12% |
| LABB.MX | LONG | +3,83% | +3,01% | USD +863 | +0,09% |
| TEND3.SA | LONG | -4,23% | -5,13% | USD -815 | -0,08% |
| LAR | SHORT | -5,90% | -5,90% | USD +574 | +0,06% |
| PBR | LONG | +1,55% | +1,55% | USD +525 | +0,05% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,4 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 3
- Short PAX (fechamento): -0,30% desde a entrada; -0,01% do NAV
- Short INTR (fechamento): -2,99% desde a entrada; -0,06% do NAV
- Short UGPA3.SA (fechamento): -0,74% desde a entrada; -0,01% do NAV
- Short BBDC4.SA (fechamento): -0,97% desde a entrada; -0,01% do NAV
- Short CX (fechamento): +1,99% desde a entrada; +0,03% do NAV
- Short FMX (fechamento): +1,63% desde a entrada; +0,02% do NAV
- Short YPF (fechamento): +3,50% desde a entrada; +0,04% do NAV
- Short EQTL3.SA (fechamento): -3,05% desde a entrada; -0,04% do NAV
- Short ALOS3.SA (fechamento): -2,87% desde a entrada; -0,03% do NAV
- Short BRAV3.SA (fechamento): +1,65% desde a entrada; +0,02% do NAV
- Short AGRO (fechamento): +2,93% desde a entrada; +0,03% do NAV
- Short VBBR3.SA (fechamento): -0,79% desde a entrada; -0,01% do NAV
- Short ASR (fechamento): +1,14% desde a entrada; +0,01% do NAV
- Short LAR (fechamento): -5,12% desde a entrada; -0,05% do NAV
- Short SAPR11.SA (fechamento): -8,36% desde a entrada; -0,09% do NAV
- Short SGML (fechamento): -6,95% desde a entrada; -0,07% do NAV
- Short ALPA4.SA (fechamento): +4,14% desde a entrada; +0,04% do NAV
- Short CIB (fechamento): +0,72% desde a entrada; +0,01% do NAV
- Short ORVR3.SA (fechamento): -2,86% desde a entrada; -0,02% do NAV
- Short MELI (fechamento): -0,73% desde a entrada; -0,01% do NAV
- Short BCH (fechamento): +0,54% desde a entrada; 0,00% do NAV
- Short USIM5.SA (fechamento): -2,05% desde a entrada; -0,01% do NAV
- Short LILAK (fechamento): +1,48% desde a entrada; +0,01% do NAV
- Short EMBJ (fechamento): +0,98% desde a entrada; +0,01% do NAV
- Short RDOR3.SA (fechamento): -2,67% desde a entrada; -0,02% do NAV
- Short ARCO (fechamento): +2,83% desde a entrada; +0,01% do NAV
- Short CBAV3.SA (fechamento): +0,53% desde a entrada; 0,00% do NAV
- Short CSMG3.SA (fechamento): -3,39% desde a entrada; -0,02% do NAV
- Short KLBN11.SA (fechamento): +0,22% desde a entrada; 0,00% do NAV
- Short DLO (fechamento): -1,38% desde a entrada; -0,01% do NAV
- Short CMIG4.SA (fechamento): -1,90% desde a entrada; -0,01% do NAV
- Short BRSR6.SA (fechamento): -1,70% desde a entrada; -0,01% do NAV
- Short SBSP3.SA (fechamento): -3,15% desde a entrada; -0,01% do NAV
- Short OMAB (fechamento): -0,50% desde a entrada; 0,00% do NAV
- Short BSAC (fechamento): -0,12% desde a entrada; 0,00% do NAV
- Short EGIE3.SA (fechamento): -1,29% desde a entrada; 0,00% do NAV
- Short PAX (intradiário): -2,19% desde a entrada; -0,05% do NAV
- Short INTR (intradiário): -8,85% desde a entrada; -0,19% do NAV
- Short UGPA3.SA (intradiário): +0,28% desde a entrada; 0,00% do NAV
- Short BBDC4.SA (intradiário): -3,29% desde a entrada; -0,04% do NAV
- Short CX (intradiário): -0,84% desde a entrada; -0,01% do NAV
- Short FMX (intradiário): +0,79% desde a entrada; +0,01% do NAV
- Short YPF (intradiário): +4,88% desde a entrada; +0,06% do NAV
- Short EQTL3.SA (intradiário): -2,80% desde a entrada; -0,03% do NAV
- Short ALOS3.SA (intradiário): -3,21% desde a entrada; -0,04% do NAV
- Short BRAV3.SA (intradiário): +0,49% desde a entrada; +0,01% do NAV
- Short AGRO (intradiário): +1,66% desde a entrada; +0,02% do NAV
- Short VBBR3.SA (intradiário): +0,70% desde a entrada; +0,01% do NAV
- Short ASR (intradiário): -1,38% desde a entrada; -0,01% do NAV
- Short LAR (intradiário): -10,72% desde a entrada; -0,11% do NAV
- Short SAPR11.SA (intradiário): -9,41% desde a entrada; -0,10% do NAV
- Short SGML (intradiário): -9,25% desde a entrada; -0,09% do NAV
- Short ALPA4.SA (intradiário): +5,16% desde a entrada; +0,04% do NAV
- Short CIB (intradiário): +1,66% desde a entrada; +0,01% do NAV
- Short ORVR3.SA (intradiário): -5,27% desde a entrada; -0,04% do NAV
- Short MELI (intradiário): -3,33% desde a entrada; -0,03% do NAV
- Short BCH (intradiário): +0,39% desde a entrada; 0,00% do NAV
- Short USIM5.SA (intradiário): -6,85% desde a entrada; -0,05% do NAV
- Short LILAK (intradiário): -0,68% desde a entrada; 0,00% do NAV
- Short EMBJ (intradiário): +0,87% desde a entrada; +0,01% do NAV
- Short RDOR3.SA (intradiário): -3,85% desde a entrada; -0,02% do NAV
- Short ARCO (intradiário): +1,67% desde a entrada; +0,01% do NAV
- Short CBAV3.SA (intradiário): +1,16% desde a entrada; +0,01% do NAV
- Short CSMG3.SA (intradiário): -1,87% desde a entrada; -0,01% do NAV
- Short KLBN11.SA (intradiário): +0,66% desde a entrada; 0,00% do NAV
- Short DLO (intradiário): -4,37% desde a entrada; -0,02% do NAV
- Short CMIG4.SA (intradiário): -1,90% desde a entrada; -0,01% do NAV
- Short BRSR6.SA (intradiário): -2,23% desde a entrada; -0,01% do NAV
- Short SBSP3.SA (intradiário): -2,83% desde a entrada; -0,01% do NAV
- Short OMAB (intradiário): -2,04% desde a entrada; -0,01% do NAV
- Short BSAC (intradiário): -0,06% desde a entrada; 0,00% do NAV
- Short EGIE3.SA (intradiário): -0,13% desde a entrada; 0,00% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Exposição líquida +1,48% fora do limite ±1,00% (net neutral).
- Short INTR (BR_INTER) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (248): AC.MX@2026-10-05 (0.9995), ALPEKA.MX@2026-10-05 (1.0048), ALSEA.MX@2026-10-05 (0.9998), AMXB.MX@2026-10-05 (0.9985), ANDINA-B.SN@2026-10-05 (0.9592), ASURB.MX@2026-10-05 (0.9966), BBAJIOO.MX@2026-10-05 (0.9990), BCI.SN@2026-10…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1180.
- Limitação de dados: Aluguel B3 sem publicação nova entre 2026-10-10 e 2026-10-13 (BDI publica em D+1).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -4.2% no pregão (mediana -3.6%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
