# Risco — CDP — Cabra da Peste — 2026-10-28 13:30 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-27 (semana vigente 2026-10-23; hash `ac063ff4f4d0`)

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `vol_abaixo_da_banda` | Vol ex-ante 2,53% abaixo da banda (3,00%–7,00%) | subutilização do orçamento de risco; nenhuma ação intradiária |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: -0,03%; acumulado: +0,76%
- Drawdown: -0,03% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 2,53% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,003 (limite ±0,050)
- Net: +0,97% (limite ±1,00%); gross 60,01%; long 30,49%; short -29,52%; 39 longs / 36 shorts
- VaR 99% 1d: 0,41% (limite 1,00%); ES 99% 1d: 0,46% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 91,68%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 13

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -778 (-0,08% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,11% — estágio normal
- Net/gross estimados: +0,89% / 58,71%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| RIAA3.SA | LONG | -9,86% | -10,29% | USD -1.135 | -0,11% |
| TEND3.SA | LONG | -7,34% | -7,80% | USD -771 | -0,08% |
| CURY3.SA | LONG | -7,24% | -7,69% | USD -769 | -0,08% |
| LABB.MX | LONG | -5,06% | -4,91% | USD -671 | -0,07% |
| AXIA3.SA | LONG | -4,21% | -4,67% | USD -475 | -0,05% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short LAR (fechamento): -8,42% desde a entrada; -0,12% do NAV
- Short ASR (fechamento): +6,61% desde a entrada; +0,08% do NAV
- Short EMBJ (fechamento): +1,38% desde a entrada; +0,02% do NAV
- Short AGRO (fechamento): -4,00% desde a entrada; -0,05% do NAV
- Short LILAK (fechamento): -1,93% desde a entrada; -0,02% do NAV
- Short MELI (fechamento): -9,77% desde a entrada; -0,13% do NAV
- Short TIMS3.SA (fechamento): -0,42% desde a entrada; 0,00% do NAV
- Short SGML (fechamento): -5,99% desde a entrada; -0,07% do NAV
- Short BRAP4.SA (fechamento): -2,68% desde a entrada; -0,03% do NAV
- Short ARCO (fechamento): -11,36% desde a entrada; -0,14% do NAV
- Short NU (fechamento): -14,84% desde a entrada; -0,18% do NAV
- Short UGPA3.SA (fechamento): -12,43% desde a entrada; -0,15% do NAV
- Short BRAV3.SA (fechamento): -8,73% desde a entrada; -0,10% do NAV
- Short FLRY3.SA (fechamento): -15,46% desde a entrada; -0,18% do NAV
- Short SAPR11.SA (fechamento): -23,49% desde a entrada; -0,30% do NAV
- Short ALPA4.SA (fechamento): -19,01% desde a entrada; -0,23% do NAV
- Short VBBR3.SA (fechamento): -12,51% desde a entrada; -0,14% do NAV
- Short ORVR3.SA (fechamento): -24,53% desde a entrada; -0,30% do NAV
- Short AURE3.SA (fechamento): -25,17% desde a entrada; -0,30% do NAV
- Short ENGI11.SA (fechamento): -27,03% desde a entrada; -0,32% do NAV
- Short CIB (fechamento): +1,04% desde a entrada; +0,01% do NAV
- Short EQTL3.SA (fechamento): -30,44% desde a entrada; -0,35% do NAV
- Short RDOR3.SA (fechamento): -21,88% desde a entrada; -0,19% do NAV
- Short PAC (fechamento): +0,71% desde a entrada; 0,00% do NAV
- Short GGAL (fechamento): -7,31% desde a entrada; -0,05% do NAV
- Short AG (fechamento): +5,89% desde a entrada; +0,03% do NAV
- Short VIVT3.SA (fechamento): -4,16% desde a entrada; -0,02% do NAV
- Short BAP (fechamento): -1,33% desde a entrada; -0,01% do NAV
- Short STNE (fechamento): -28,96% desde a entrada; -0,17% do NAV
- Short BRSR6.SA (fechamento): -26,90% desde a entrada; -0,15% do NAV
- Short CMIG4.SA (fechamento): -13,85% desde a entrada; -0,05% do NAV
- Short TOTS3.SA (fechamento): -20,29% desde a entrada; -0,07% do NAV
- Short PAM (fechamento): -5,17% desde a entrada; -0,02% do NAV
- Short SBSP3.SA (fechamento): -24,02% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (fechamento): -17,33% desde a entrada; -0,06% do NAV
- Short BMA (fechamento): -6,51% desde a entrada; -0,02% do NAV
- Short LAR (intradiário): -10,72% desde a entrada; -0,16% do NAV
- Short ASR (intradiário): +5,34% desde a entrada; +0,06% do NAV
- Short EMBJ (intradiário): +0,41% desde a entrada; +0,01% do NAV
- Short AGRO (intradiário): -2,58% desde a entrada; -0,03% do NAV
- Short LILAK (intradiário): -1,50% desde a entrada; -0,02% do NAV
- Short MELI (intradiário): -10,39% desde a entrada; -0,13% do NAV
- Short TIMS3.SA (intradiário): -0,05% desde a entrada; 0,00% do NAV
- Short SGML (intradiário): -8,66% desde a entrada; -0,11% do NAV
- Short BRAP4.SA (intradiário): -5,31% desde a entrada; -0,06% do NAV
- Short ARCO (intradiário): -12,88% desde a entrada; -0,16% do NAV
- Short NU (intradiário): -16,76% desde a entrada; -0,21% do NAV
- Short UGPA3.SA (intradiário): -15,81% desde a entrada; -0,19% do NAV
- Short BRAV3.SA (intradiário): -9,79% desde a entrada; -0,11% do NAV
- Short FLRY3.SA (intradiário): -18,48% desde a entrada; -0,22% do NAV
- Short SAPR11.SA (intradiário): -26,65% desde a entrada; -0,34% do NAV
- Short ALPA4.SA (intradiário): -21,07% desde a entrada; -0,25% do NAV
- Short VBBR3.SA (intradiário): -14,95% desde a entrada; -0,16% do NAV
- Short ORVR3.SA (intradiário): -26,28% desde a entrada; -0,32% do NAV
- Short AURE3.SA (intradiário): -25,64% desde a entrada; -0,30% do NAV
- Short ENGI11.SA (intradiário): -30,14% desde a entrada; -0,36% do NAV
- Short CIB (intradiário): -0,57% desde a entrada; 0,00% do NAV
- Short EQTL3.SA (intradiário): -33,42% desde a entrada; -0,39% do NAV
- Short RDOR3.SA (intradiário): -23,48% desde a entrada; -0,21% do NAV
- Short PAC (intradiário): -1,29% desde a entrada; -0,01% do NAV
- Short GGAL (intradiário): -9,76% desde a entrada; -0,06% do NAV
- Short AG (intradiário): +5,08% desde a entrada; +0,03% do NAV
- Short VIVT3.SA (intradiário): -4,75% desde a entrada; -0,03% do NAV
- Short BAP (intradiário): -2,31% desde a entrada; -0,01% do NAV
- Short STNE (intradiário): -28,88% desde a entrada; -0,17% do NAV
- Short BRSR6.SA (intradiário): -30,01% desde a entrada; -0,17% do NAV
- Short CMIG4.SA (intradiário): -16,24% desde a entrada; -0,06% do NAV
- Short TOTS3.SA (intradiário): -24,42% desde a entrada; -0,09% do NAV
- Short PAM (intradiário): -5,01% desde a entrada; -0,02% do NAV
- Short SBSP3.SA (intradiário): -26,16% desde a entrada; -0,10% do NAV
- Short RAIL3.SA (intradiário): -21,74% desde a entrada; -0,07% do NAV
- Short BMA (intradiário): -8,27% desde a entrada; -0,02% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Vol ex-ante 2,53% abaixo da banda (3,00%–7,00%): subutilização do orçamento de risco.
- Short GGAL (AR_GALICIA) com risco de squeeze HIGH (era MEDIUM na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (271): AC.MX@2026-10-19 (1.0004), ALPEKA.MX@2026-10-19 (1.0025), ALSEA.MX@2026-10-19 (1.0013), AMXB.MX@2026-10-19 (1.0014), ASURB.MX@2026-10-19 (1.0014), BBAJIOO.MX@2026-10-19 (0.9981), BIMBOA.MX@2026-10-19 (0.9998), BOLSAA.MX@2026-1…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1582.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 3.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: Aluguel B3 indisponível: RuntimeError('Fonte de aluguel B3 (BDI) indisponível: 2026-10-26: Falha de rede em POST https://arquivos.b3.com.br/bdi/table/BTBLoanBalance/2026-10-26/2026-10-26/1/1000: ReadTimeout(ReadTimeoutError("HTTPSConnectionPool(host=\'arquivos.b3.com.br\', port=443): Read timed out…
- Limitação de dados: Aluguel B3 (BDI) ausente para pregões já fechados: 2026-10-26 (nova tentativa nos próximos incrementos enquanto estiverem na janela D-21).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -2.2% no pregão (mediana -3.3%; tolerância 3%).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
