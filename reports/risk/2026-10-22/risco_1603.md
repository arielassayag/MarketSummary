# Risco — CDP — Cabra da Peste — 2026-10-22 16:03 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-21 (semana vigente 2026-10-16; hash `51aa3cb58d89`)

## Ações recomendadas (determinísticas)

- revisar: PINE4.SA: variação do fechamento +5.7% difere da do fechamento ajustado +6.9% — possível grupamento, desdobramento ou provento.

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `possivel_evento_societario:PINE4.SA` | PINE4.SA: variação do fechamento +5.7% difere da do fechamento ajustado +6.9% — possível grupamento, desdobramento ou provento. | conferir o evento societário antes do próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: +0,07%; acumulado: +0,53%
- Drawdown: -0,11% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,58% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,003 (limite ±0,050)
- Net: +0,15% (limite ±1,00%); gross 68,01%; long 34,08%; short -33,93%; 38 longs / 35 shorts
- VaR 99% 1d: 0,52% (limite 1,00%); ES 99% 1d: 0,60% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 86,77%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 9

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD +1.715 (+0,17% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: 0,00% — estágio normal
- Net/gross estimados: +0,32% / 66,85%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| FSM | LONG | -8,27% | -8,27% | USD -994 | -0,10% |
| SGML | SHORT | -9,03% | -9,03% | USD +770 | +0,08% |
| PINE4.SA | LONG | -5,82% | -6,03% | USD -704 | -0,07% |
| EMBJ | SHORT | -5,34% | -5,34% | USD +669 | +0,07% |
| LAR | SHORT | -5,70% | -5,70% | USD +663 | +0,07% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 0
- Short FMX (fechamento): +7,33% desde a entrada; +0,09% do NAV
- Short FLRY3.SA (fechamento): +3,73% desde a entrada; +0,05% do NAV
- Short UGPA3.SA (fechamento): +2,40% desde a entrada; +0,03% do NAV
- Short AURE3.SA (fechamento): +2,77% desde a entrada; +0,03% do NAV
- Short ORVR3.SA (fechamento): -3,12% desde a entrada; -0,04% do NAV
- Short ENGI11.SA (fechamento): +1,09% desde a entrada; +0,01% do NAV
- Short NU (fechamento): +3,37% desde a entrada; +0,04% do NAV
- Short CX (fechamento): +8,68% desde a entrada; +0,10% do NAV
- Short PAX (fechamento): +2,06% desde a entrada; +0,03% do NAV
- Short USIM5.SA (fechamento): -5,06% desde a entrada; -0,07% do NAV
- Short EMBJ (fechamento): +1,61% desde a entrada; +0,02% do NAV
- Short BRAV3.SA (fechamento): +2,04% desde a entrada; +0,02% do NAV
- Short YPF (fechamento): +0,66% desde a entrada; +0,01% do NAV
- Short EQTL3.SA (fechamento): -4,18% desde a entrada; -0,05% do NAV
- Short LAR (fechamento): -12,50% desde a entrada; -0,17% do NAV
- Short ALOS3.SA (fechamento): -1,59% desde a entrada; -0,02% do NAV
- Short ASR (fechamento): +9,08% desde a entrada; +0,09% do NAV
- Short ARCO (fechamento): +2,84% desde a entrada; +0,03% do NAV
- Short MELI (fechamento): -0,87% desde a entrada; -0,01% do NAV
- Short SAPR11.SA (fechamento): -7,26% desde a entrada; -0,09% do NAV
- Short VBBR3.SA (fechamento): -0,14% desde a entrada; 0,00% do NAV
- Short AGRO (fechamento): -7,42% desde a entrada; -0,08% do NAV
- Short RDOR3.SA (fechamento): -1,66% desde a entrada; -0,02% do NAV
- Short SGML (fechamento): -12,94% desde a entrada; -0,13% do NAV
- Short CIB (fechamento): +2,94% desde a entrada; +0,02% do NAV
- Short BCH (fechamento): +1,93% desde a entrada; +0,01% do NAV
- Short BSAC (fechamento): +1,39% desde a entrada; +0,01% do NAV
- Short LILAK (fechamento): -1,85% desde a entrada; -0,01% do NAV
- Short CSMG3.SA (fechamento): -2,42% desde a entrada; -0,01% do NAV
- Short KLBN11.SA (fechamento): +0,39% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (fechamento): -3,54% desde a entrada; -0,01% do NAV
- Short SBSP3.SA (fechamento): -4,67% desde a entrada; -0,02% do NAV
- Short BRSR6.SA (fechamento): -3,92% desde a entrada; -0,02% do NAV
- Short RAIL3.SA (fechamento): +2,05% desde a entrada; +0,01% do NAV
- Short OMAB (fechamento): +9,26% desde a entrada; +0,03% do NAV
- Short FMX (intradiário): +8,01% desde a entrada; +0,10% do NAV
- Short FLRY3.SA (intradiário): +2,84% desde a entrada; +0,04% do NAV
- Short UGPA3.SA (intradiário): +0,28% desde a entrada; 0,00% do NAV
- Short AURE3.SA (intradiário): -0,47% desde a entrada; -0,01% do NAV
- Short ORVR3.SA (intradiário): -5,20% desde a entrada; -0,07% do NAV
- Short ENGI11.SA (intradiário): +0,14% desde a entrada; 0,00% do NAV
- Short NU (intradiário): +0,65% desde a entrada; +0,01% do NAV
- Short CX (intradiário): +5,54% desde a entrada; +0,06% do NAV
- Short PAX (intradiário): +1,84% desde a entrada; +0,02% do NAV
- Short USIM5.SA (intradiário): -9,20% desde a entrada; -0,12% do NAV
- Short EMBJ (intradiário): -3,81% desde a entrada; -0,05% do NAV
- Short BRAV3.SA (intradiário): +2,86% desde a entrada; +0,03% do NAV
- Short YPF (intradiário): -1,52% desde a entrada; -0,02% do NAV
- Short EQTL3.SA (intradiário): -4,81% desde a entrada; -0,06% do NAV
- Short LAR (intradiário): -17,49% desde a entrada; -0,23% do NAV
- Short ALOS3.SA (intradiário): -2,76% desde a entrada; -0,03% do NAV
- Short ASR (intradiário): +8,30% desde a entrada; +0,09% do NAV
- Short ARCO (intradiário): +1,83% desde a entrada; +0,02% do NAV
- Short MELI (intradiário): -3,35% desde a entrada; -0,04% do NAV
- Short SAPR11.SA (intradiário): -7,37% desde a entrada; -0,09% do NAV
- Short VBBR3.SA (intradiário): -0,22% desde a entrada; 0,00% do NAV
- Short AGRO (intradiário): -5,66% desde a entrada; -0,06% do NAV
- Short RDOR3.SA (intradiário): -1,05% desde a entrada; -0,01% do NAV
- Short SGML (intradiário): -20,80% desde a entrada; -0,20% do NAV
- Short CIB (intradiário): +1,57% desde a entrada; +0,01% do NAV
- Short BCH (intradiário): -1,02% desde a entrada; -0,01% do NAV
- Short BSAC (intradiário): -1,84% desde a entrada; -0,01% do NAV
- Short LILAK (intradiário): +0,18% desde a entrada; 0,00% do NAV
- Short CSMG3.SA (intradiário): -2,18% desde a entrada; -0,01% do NAV
- Short KLBN11.SA (intradiário): +0,28% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (intradiário): -3,96% desde a entrada; -0,02% do NAV
- Short SBSP3.SA (intradiário): -5,83% desde a entrada; -0,02% do NAV
- Short BRSR6.SA (intradiário): -5,78% desde a entrada; -0,02% do NAV
- Short RAIL3.SA (intradiário): -0,22% desde a entrada; 0,00% do NAV
- Short OMAB (intradiário): +9,45% desde a entrada; +0,03% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (282): AC.MX@2026-10-12 (1.0016), ALPEKA.MX@2026-10-12 (1.0075), ALSEA.MX@2026-10-12 (1.0025), AMXB.MX@2026-10-12 (0.9990), ASURB.MX@2026-10-12 (1.0008), BBAJIOO.MX@2026-10-12 (1.0009), BIMBOA.MX@2026-10-12 (1.0031), BOLSAA.MX@2026-1…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1672.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -3.2% no pregão (mediana -3.3%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
