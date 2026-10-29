# Risco — CDP — Cabra da Peste — 2026-10-29 16:08 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-28 (semana vigente 2026-10-23; hash `c52f10047c3d`)

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `vol_abaixo_da_banda` | Vol ex-ante 2,51% abaixo da banda (3,00%–7,00%) | subutilização do orçamento de risco; nenhuma ação intradiária |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: -0,11%; acumulado: +0,65%
- Drawdown: -0,14% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 2,51% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,003 (limite ±0,050)
- Net: +0,85% (limite ±1,00%); gross 58,98%; long 29,92%; short -29,07%; 39 longs / 36 shorts
- VaR 99% 1d: 0,41% (limite 1,00%); ES 99% 1d: 0,45% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 90,30%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 14

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD +584 (+0,06% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,08% — estágio normal
- Net/gross estimados: +0,91% / 58,22%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| SGML | SHORT | -7,12% | -7,12% | USD +812 | +0,08% |
| EMBJ | SHORT | +5,12% | +5,12% | USD -635 | -0,06% |
| RIAA3.SA | LONG | -4,72% | -5,48% | USD -557 | -0,06% |
| FSM | LONG | -3,89% | -3,89% | USD -523 | -0,05% |
| GGB | LONG | +5,88% | +5,88% | USD +481 | +0,05% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,1 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short LAR (fechamento): -9,22% desde a entrada; -0,14% do NAV
- Short ASR (fechamento): +6,07% desde a entrada; +0,07% do NAV
- Short LILAK (fechamento): -0,19% desde a entrada; 0,00% do NAV
- Short AGRO (fechamento): -3,90% desde a entrada; -0,05% do NAV
- Short EMBJ (fechamento): +0,51% desde a entrada; +0,01% do NAV
- Short TIMS3.SA (fechamento): +1,83% desde a entrada; +0,02% do NAV
- Short MELI (fechamento): -10,17% desde a entrada; -0,13% do NAV
- Short SGML (fechamento): -7,66% desde a entrada; -0,09% do NAV
- Short BRAP4.SA (fechamento): -4,79% desde a entrada; -0,06% do NAV
- Short ARCO (fechamento): -12,37% desde a entrada; -0,16% do NAV
- Short BRAV3.SA (fechamento): -11,05% desde a entrada; -0,13% do NAV
- Short NU (fechamento): -17,79% desde a entrada; -0,22% do NAV
- Short UGPA3.SA (fechamento): -15,68% desde a entrada; -0,19% do NAV
- Short ALPA4.SA (fechamento): -20,90% desde a entrada; -0,25% do NAV
- Short FLRY3.SA (fechamento): -19,44% desde a entrada; -0,23% do NAV
- Short SAPR11.SA (fechamento): -26,33% desde a entrada; -0,34% do NAV
- Short ORVR3.SA (fechamento): -25,00% desde a entrada; -0,31% do NAV
- Short VBBR3.SA (fechamento): -16,64% desde a entrada; -0,18% do NAV
- Short AURE3.SA (fechamento): -25,57% desde a entrada; -0,30% do NAV
- Short ENGI11.SA (fechamento): -29,99% desde a entrada; -0,36% do NAV
- Short CIB (fechamento): -0,15% desde a entrada; 0,00% do NAV
- Short EQTL3.SA (fechamento): -32,89% desde a entrada; -0,38% do NAV
- Short RDOR3.SA (fechamento): -24,20% desde a entrada; -0,22% do NAV
- Short PAC (fechamento): -0,09% desde a entrada; 0,00% do NAV
- Short AG (fechamento): +6,97% desde a entrada; +0,04% do NAV
- Short GGAL (fechamento): -10,74% desde a entrada; -0,07% do NAV
- Short VIVT3.SA (fechamento): -5,21% desde a entrada; -0,03% do NAV
- Short BAP (fechamento): -1,66% desde a entrada; -0,01% do NAV
- Short STNE (fechamento): -29,53% desde a entrada; -0,18% do NAV
- Short BRSR6.SA (fechamento): -30,06% desde a entrada; -0,17% do NAV
- Short CMIG4.SA (fechamento): -16,41% desde a entrada; -0,06% do NAV
- Short PAM (fechamento): -5,07% desde a entrada; -0,02% do NAV
- Short TOTS3.SA (fechamento): -23,09% desde a entrada; -0,09% do NAV
- Short SBSP3.SA (fechamento): -25,27% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (fechamento): -22,07% desde a entrada; -0,07% do NAV
- Short BMA (fechamento): -8,83% desde a entrada; -0,02% do NAV
- Short LAR (intradiário): -11,12% desde a entrada; -0,16% do NAV
- Short ASR (intradiário): +7,26% desde a entrada; +0,09% do NAV
- Short LILAK (intradiário): +2,41% desde a entrada; +0,03% do NAV
- Short AGRO (intradiário): -5,15% desde a entrada; -0,07% do NAV
- Short EMBJ (intradiário): +5,65% desde a entrada; +0,07% do NAV
- Short TIMS3.SA (intradiário): +2,62% desde a entrada; +0,03% do NAV
- Short MELI (intradiário): -11,32% desde a entrada; -0,15% do NAV
- Short SGML (intradiário): -14,23% desde a entrada; -0,17% do NAV
- Short BRAP4.SA (intradiário): -5,84% desde a entrada; -0,07% do NAV
- Short ARCO (intradiário): -12,69% desde a entrada; -0,16% do NAV
- Short BRAV3.SA (intradiário): -12,75% desde a entrada; -0,14% do NAV
- Short NU (intradiário): -17,58% desde a entrada; -0,22% do NAV
- Short UGPA3.SA (intradiário): -17,34% desde a entrada; -0,20% do NAV
- Short ALPA4.SA (intradiário): -23,32% desde a entrada; -0,28% do NAV
- Short FLRY3.SA (intradiário): -22,57% desde a entrada; -0,26% do NAV
- Short SAPR11.SA (intradiário): -27,42% desde a entrada; -0,35% do NAV
- Short ORVR3.SA (intradiário): -25,29% desde a entrada; -0,31% do NAV
- Short VBBR3.SA (intradiário): -16,50% desde a entrada; -0,18% do NAV
- Short AURE3.SA (intradiário): -26,05% desde a entrada; -0,30% do NAV
- Short ENGI11.SA (intradiário): -31,34% desde a entrada; -0,37% do NAV
- Short CIB (intradiário): -1,37% desde a entrada; -0,01% do NAV
- Short EQTL3.SA (intradiário): -35,00% desde a entrada; -0,40% do NAV
- Short RDOR3.SA (intradiário): -26,92% desde a entrada; -0,24% do NAV
- Short PAC (intradiário): +1,45% desde a entrada; +0,01% do NAV
- Short AG (intradiário): +3,42% desde a entrada; +0,02% do NAV
- Short GGAL (intradiário): -11,45% desde a entrada; -0,08% do NAV
- Short VIVT3.SA (intradiário): -4,72% desde a entrada; -0,03% do NAV
- Short BAP (intradiário): -2,94% desde a entrada; -0,02% do NAV
- Short STNE (intradiário): -30,49% desde a entrada; -0,18% do NAV
- Short BRSR6.SA (intradiário): -31,84% desde a entrada; -0,18% do NAV
- Short CMIG4.SA (intradiário): -16,49% desde a entrada; -0,06% do NAV
- Short PAM (intradiário): -5,57% desde a entrada; -0,02% do NAV
- Short TOTS3.SA (intradiário): -24,42% desde a entrada; -0,09% do NAV
- Short SBSP3.SA (intradiário): -25,65% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (intradiário): -23,20% desde a entrada; -0,08% do NAV
- Short BMA (intradiário): -7,48% desde a entrada; -0,02% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Vol ex-ante 2,51% abaixo da banda (3,00%–7,00%): subutilização do orçamento de risco.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (328): AC.MX@2026-10-19 (1.0004), ALPEKA.MX@2026-10-19 (1.0025), ALSEA.MX@2026-10-19 (1.0013), AMXB.MX@2026-10-19 (1.0014), ASURB.MX@2026-10-19 (1.0014), BBAJIOO.MX@2026-10-19 (0.9981), BIMBOA.MX@2026-10-19 (0.9998), BOLSAA.MX@2026-1…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1845.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 3.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: Aluguel B3 (BDI) ausente para pregões já fechados: 2026-10-26 (nova tentativa nos próximos incrementos enquanto estiverem na janela D-21).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -0.7% no pregão (mediana -3.3%; tolerância 3%).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
