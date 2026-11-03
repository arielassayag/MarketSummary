# Risco — CDP — Cabra da Peste — 2026-11-03 16:03 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-02 (semana vigente 2026-10-23; hash `2be600745a8d`)

## Ações recomendadas (determinísticas)

- revisar: Exposição líquida +1,10% fora do limite ±1,00% (net neutral)
- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `net_fora_do_limite` | Exposição líquida +1,10% fora do limite ±1,00% (net neutral) | reequilibrar no próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `vol_abaixo_da_banda` | Vol ex-ante 2,38% abaixo da banda (3,00%–7,00%) | subutilização do orçamento de risco; nenhuma ação intradiária |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: +0,02%; acumulado: +0,96%
- Drawdown: 0,00% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 2,38% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: 0,000 (limite ±0,050)
- Net: +1,10% (limite ±1,00%); gross 56,82%; long 28,96%; short -27,86%; 39 longs / 36 shorts
- VaR 99% 1d: 0,36% (limite 1,00%); ES 99% 1d: 0,40% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 88,38%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 17

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -465 (-0,05% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,05% — estágio normal
- Net/gross estimados: +1,06% / 56,02%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| PRIO3.SA | LONG | -4,15% | -6,02% | USD -670 | -0,07% |
| BRAV3.SA | SHORT | -4,40% | -6,26% | USD +638 | +0,06% |
| SGML | SHORT | +7,29% | +7,29% | USD -522 | -0,05% |
| SAPR11.SA | SHORT | -3,47% | -5,35% | USD +479 | +0,05% |
| ORVR3.SA | SHORT | -2,63% | -4,53% | USD +422 | +0,04% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short LILAK (fechamento): +6,51% desde a entrada; +0,08% do NAV
- Short ASR (fechamento): +9,29% desde a entrada; +0,11% do NAV
- Short EMBJ (fechamento): +4,99% desde a entrada; +0,06% do NAV
- Short AGRO (fechamento): -6,44% desde a entrada; -0,08% do NAV
- Short LAR (fechamento): -18,42% desde a entrada; -0,27% do NAV
- Short TIMS3.SA (fechamento): +0,42% desde a entrada; 0,00% do NAV
- Short MELI (fechamento): -9,97% desde a entrada; -0,13% do NAV
- Short BRAP4.SA (fechamento): -3,89% desde a entrada; -0,05% do NAV
- Short ARCO (fechamento): -14,27% desde a entrada; -0,18% do NAV
- Short BRAV3.SA (fechamento): -10,67% desde a entrada; -0,12% do NAV
- Short NU (fechamento): -20,19% desde a entrada; -0,25% do NAV
- Short UGPA3.SA (fechamento): -18,75% desde a entrada; -0,22% do NAV
- Short ORVR3.SA (fechamento): -24,58% desde a entrada; -0,30% do NAV
- Short SAPR11.SA (fechamento): -29,90% desde a entrada; -0,38% do NAV
- Short FLRY3.SA (fechamento): -24,49% desde a entrada; -0,29% do NAV
- Short VBBR3.SA (fechamento): -19,52% desde a entrada; -0,21% do NAV
- Short ALPA4.SA (fechamento): -26,92% desde a entrada; -0,32% do NAV
- Short AURE3.SA (fechamento): -26,65% desde a entrada; -0,31% do NAV
- Short ENGI11.SA (fechamento): -32,16% desde a entrada; -0,38% do NAV
- Short CIB (fechamento): -2,89% desde a entrada; -0,02% do NAV
- Short EQTL3.SA (fechamento): -35,76% desde a entrada; -0,41% do NAV
- Short SGML (fechamento): -42,04% desde a entrada; -0,51% do NAV
- Short PAC (fechamento): +5,82% desde a entrada; +0,04% do NAV
- Short RDOR3.SA (fechamento): -28,72% desde a entrada; -0,25% do NAV
- Short AG (fechamento): -3,05% desde a entrada; -0,02% do NAV
- Short GGAL (fechamento): -16,96% desde a entrada; -0,11% do NAV
- Short VIVT3.SA (fechamento): -5,33% desde a entrada; -0,03% do NAV
- Short BAP (fechamento): -5,19% desde a entrada; -0,03% do NAV
- Short STNE (fechamento): -33,45% desde a entrada; -0,20% do NAV
- Short BRSR6.SA (fechamento): -33,61% desde a entrada; -0,18% do NAV
- Short CMIG4.SA (fechamento): -16,98% desde a entrada; -0,07% do NAV
- Short SBSP3.SA (fechamento): -26,49% desde a entrada; -0,10% do NAV
- Short TOTS3.SA (fechamento): -27,85% desde a entrada; -0,10% do NAV
- Short PAM (fechamento): -12,23% desde a entrada; -0,04% do NAV
- Short RAIL3.SA (fechamento): -25,83% desde a entrada; -0,08% do NAV
- Short BMA (fechamento): -10,66% desde a entrada; -0,03% do NAV
- Short LILAK (intradiário): +7,75% desde a entrada; +0,10% do NAV
- Short ASR (intradiário): +10,61% desde a entrada; +0,13% do NAV
- Short EMBJ (intradiário): +4,97% desde a entrada; +0,06% do NAV
- Short AGRO (intradiário): -5,86% desde a entrada; -0,08% do NAV
- Short LAR (intradiário): -20,11% desde a entrada; -0,30% do NAV
- Short TIMS3.SA (intradiário): +3,30% desde a entrada; +0,04% do NAV
- Short MELI (intradiário): -10,05% desde a entrada; -0,13% do NAV
- Short BRAP4.SA (intradiário): -5,21% desde a entrada; -0,06% do NAV
- Short ARCO (intradiário): -14,21% desde a entrada; -0,18% do NAV
- Short BRAV3.SA (intradiário): -14,60% desde a entrada; -0,16% do NAV
- Short NU (intradiário): -19,78% desde a entrada; -0,24% do NAV
- Short UGPA3.SA (intradiário): -20,49% desde a entrada; -0,24% do NAV
- Short ORVR3.SA (intradiário): -26,56% desde a entrada; -0,32% do NAV
- Short SAPR11.SA (intradiário): -32,33% desde a entrada; -0,40% do NAV
- Short FLRY3.SA (intradiário): -24,75% desde a entrada; -0,28% do NAV
- Short VBBR3.SA (intradiário): -20,53% desde a entrada; -0,22% do NAV
- Short ALPA4.SA (intradiário): -27,98% desde a entrada; -0,33% do NAV
- Short AURE3.SA (intradiário): -28,14% desde a entrada; -0,32% do NAV
- Short ENGI11.SA (intradiário): -33,74% desde a entrada; -0,39% do NAV
- Short CIB (intradiário): -1,95% desde a entrada; -0,02% do NAV
- Short EQTL3.SA (intradiário): -37,00% desde a entrada; -0,42% do NAV
- Short SGML (intradiário): -37,81% desde a entrada; -0,46% do NAV
- Short PAC (intradiário): +7,00% desde a entrada; +0,04% do NAV
- Short RDOR3.SA (intradiário): -29,73% desde a entrada; -0,26% do NAV
- Short AG (intradiário): -4,37% desde a entrada; -0,03% do NAV
- Short GGAL (intradiário): -16,33% desde a entrada; -0,11% do NAV
- Short VIVT3.SA (intradiário): -5,55% desde a entrada; -0,03% do NAV
- Short BAP (intradiário): -5,20% desde a entrada; -0,03% do NAV
- Short STNE (intradiário): -34,69% desde a entrada; -0,21% do NAV
- Short BRSR6.SA (intradiário): -33,82% desde a entrada; -0,18% do NAV
- Short CMIG4.SA (intradiário): -18,47% desde a entrada; -0,07% do NAV
- Short SBSP3.SA (intradiário): -27,62% desde a entrada; -0,10% do NAV
- Short TOTS3.SA (intradiário): -27,96% desde a entrada; -0,10% do NAV
- Short PAM (intradiário): -13,57% desde a entrada; -0,04% do NAV
- Short RAIL3.SA (intradiário): -26,16% desde a entrada; -0,08% do NAV
- Short BMA (intradiário): -7,75% desde a entrada; -0,02% do NAV

## Alertas do registro de fechamento

- Preço ausente no pregão (linha não negociou; posição não reprecificada, valor mantido): ALPA4.SA, ALUP11.SA, ABEV3.SA, AURE3.SA, AXIA3.SA, BRSR6.SA, BBSE3.SA, BRAP4.SA (+30).
- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Vol ex-ante 2,38% abaixo da banda (3,00%–7,00%): subutilização do orçamento de risco.
- Exposição líquida +1,10% fora do limite ±1,00% (net neutral).
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (228): AC.MX@2026-10-23 (0.9981), ALPEKA.MX@2026-10-23 (0.9994), ALSEA.MX@2026-10-23 (0.9994), AMXB.MX@2026-10-23 (1.0013), ASURB.MX@2026-10-23 (1.0023), BBAJIOO.MX@2026-10-23 (1.0010), BIMBOA.MX@2026-10-23 (1.0011), BOLSAA.MX@2026-1…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1324.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 3.
- Limitação de dados: Benchmarks sem barra no pregão: BOVA11.SA, ^BVSP, ^MERV, ^MXX.
- Limitação de dados: Aluguel B3 sem publicação nova entre 2026-10-31 e 2026-11-02 (BDI publica em D+1).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
