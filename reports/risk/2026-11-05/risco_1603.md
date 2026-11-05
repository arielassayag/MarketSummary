# Risco — CDP — Cabra da Peste — 2026-11-05 16:03 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-04 (semana vigente 2026-10-23; hash `8551bf6e87cd`)

## Ações recomendadas (determinísticas)

- revisar: CXSE3.SA: variação do fechamento -0.0% difere da do fechamento ajustado +1.7% — possível grupamento, desdobramento ou provento.
- revisar: Shorts com risco de squeeze HIGH: 2 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `possivel_evento_societario:CXSE3.SA` | CXSE3.SA: variação do fechamento -0.0% difere da do fechamento ajustado +1.7% — possível grupamento, desdobramento ou provento. | conferir o evento societário antes do próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 2 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `vol_abaixo_da_banda` | Vol ex-ante 2,43% abaixo da banda (3,00%–7,00%) | subutilização do orçamento de risco; nenhuma ação intradiária |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: -0,26%; acumulado: +0,62%
- Drawdown: -0,34% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 2,43% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,003 (limite ±0,050)
- Net: +0,74% (limite ±1,00%); gross 57,17%; long 28,95%; short -28,21%; 39 longs / 36 shorts
- VaR 99% 1d: 0,39% (limite 1,00%); ES 99% 1d: 0,42% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 87,19%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 19

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -674 (-0,07% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,41% — estágio normal
- Net/gross estimados: +0,68% / 55,80%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| MELI | SHORT | -12,73% | -12,73% | USD +1.551 | +0,15% |
| TEND3.SA | LONG | -16,51% | -17,01% | USD -1.416 | -0,14% |
| EMBJ | SHORT | -6,19% | -6,19% | USD +836 | +0,08% |
| ERO | LONG | -9,38% | -9,38% | USD -835 | -0,08% |
| LAR | SHORT | -4,88% | -4,88% | USD +609 | +0,06% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 2
- Short ASR (fechamento): +13,64% desde a entrada; +0,16% do NAV
- Short EMBJ (fechamento): +9,45% desde a entrada; +0,12% do NAV
- Short LILAK (fechamento): +6,88% desde a entrada; +0,09% do NAV
- Short LAR (fechamento): -16,02% desde a entrada; -0,24% do NAV
- Short MELI (fechamento): -6,58% desde a entrada; -0,09% do NAV
- Short TIMS3.SA (fechamento): +3,72% desde a entrada; +0,04% do NAV
- Short AGRO (fechamento): -9,67% desde a entrada; -0,13% do NAV
- Short BRAP4.SA (fechamento): -1,95% desde a entrada; -0,02% do NAV
- Short ARCO (fechamento): -10,22% desde a entrada; -0,13% do NAV
- Short NU (fechamento): -17,65% desde a entrada; -0,22% do NAV
- Short ORVR3.SA (fechamento): -22,40% desde a entrada; -0,27% do NAV
- Short UGPA3.SA (fechamento): -21,51% desde a entrada; -0,25% do NAV
- Short ALPA4.SA (fechamento): -23,14% desde a entrada; -0,27% do NAV
- Short SAPR11.SA (fechamento): -29,12% desde a entrada; -0,37% do NAV
- Short FLRY3.SA (fechamento): -23,61% desde a entrada; -0,27% do NAV
- Short BRAV3.SA (fechamento): -22,35% desde a entrada; -0,25% do NAV
- Short VBBR3.SA (fechamento): -20,47% desde a entrada; -0,22% do NAV
- Short AURE3.SA (fechamento): -25,84% desde a entrada; -0,30% do NAV
- Short CIB (fechamento): -0,45% desde a entrada; 0,00% do NAV
- Short ENGI11.SA (fechamento): -31,47% desde a entrada; -0,37% do NAV
- Short SGML (fechamento): -37,47% desde a entrada; -0,46% do NAV
- Short EQTL3.SA (fechamento): -34,44% desde a entrada; -0,39% do NAV
- Short PAC (fechamento): +10,85% desde a entrada; +0,07% do NAV
- Short RDOR3.SA (fechamento): -26,79% desde a entrada; -0,23% do NAV
- Short AG (fechamento): +4,20% desde a entrada; +0,02% do NAV
- Short GGAL (fechamento): -18,36% desde a entrada; -0,12% do NAV
- Short VIVT3.SA (fechamento): -4,41% desde a entrada; -0,02% do NAV
- Short BAP (fechamento): -2,97% desde a entrada; -0,02% do NAV
- Short STNE (fechamento): -33,01% desde a entrada; -0,20% do NAV
- Short BRSR6.SA (fechamento): -31,57% desde a entrada; -0,17% do NAV
- Short CMIG4.SA (fechamento): -15,91% desde a entrada; -0,06% do NAV
- Short TOTS3.SA (fechamento): -24,69% desde a entrada; -0,09% do NAV
- Short SBSP3.SA (fechamento): -24,91% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (fechamento): -23,04% desde a entrada; -0,07% do NAV
- Short PAM (fechamento): -18,44% desde a entrada; -0,06% do NAV
- Short BMA (fechamento): -9,33% desde a entrada; -0,02% do NAV
- Short ASR (intradiário): +12,26% desde a entrada; +0,15% do NAV
- Short EMBJ (intradiário): +2,67% desde a entrada; +0,03% do NAV
- Short LILAK (intradiário): +5,14% desde a entrada; +0,06% do NAV
- Short LAR (intradiário): -20,11% desde a entrada; -0,30% do NAV
- Short MELI (intradiário): -18,48% desde a entrada; -0,24% do NAV
- Short TIMS3.SA (intradiário): +3,98% desde a entrada; +0,05% do NAV
- Short AGRO (intradiário): -10,16% desde a entrada; -0,13% do NAV
- Short BRAP4.SA (intradiário): -0,84% desde a entrada; -0,01% do NAV
- Short ARCO (intradiário): -12,18% desde a entrada; -0,15% do NAV
- Short NU (intradiário): -20,33% desde a entrada; -0,25% do NAV
- Short ORVR3.SA (intradiário): -20,80% desde a entrada; -0,25% do NAV
- Short UGPA3.SA (intradiário): -21,74% desde a entrada; -0,25% do NAV
- Short ALPA4.SA (intradiário): -24,56% desde a entrada; -0,29% do NAV
- Short SAPR11.SA (intradiário): -29,99% desde a entrada; -0,37% do NAV
- Short FLRY3.SA (intradiário): -24,97% desde a entrada; -0,29% do NAV
- Short BRAV3.SA (intradiário): -22,40% desde a entrada; -0,25% do NAV
- Short VBBR3.SA (intradiário): -21,72% desde a entrada; -0,23% do NAV
- Short AURE3.SA (intradiário): -24,29% desde a entrada; -0,28% do NAV
- Short CIB (intradiário): -3,35% desde a entrada; -0,03% do NAV
- Short ENGI11.SA (intradiário): -31,26% desde a entrada; -0,36% do NAV
- Short SGML (intradiário): -41,42% desde a entrada; -0,51% do NAV
- Short EQTL3.SA (intradiário): -34,27% desde a entrada; -0,39% do NAV
- Short PAC (intradiário): +8,91% desde a entrada; +0,06% do NAV
- Short RDOR3.SA (intradiário): -26,29% desde a entrada; -0,23% do NAV
- Short AG (intradiário): +0,54% desde a entrada; 0,00% do NAV
- Short GGAL (intradiário): -22,08% desde a entrada; -0,15% do NAV
- Short VIVT3.SA (intradiário): -3,95% desde a entrada; -0,02% do NAV
- Short BAP (intradiário): -6,08% desde a entrada; -0,03% do NAV
- Short STNE (intradiário): -35,24% desde a entrada; -0,21% do NAV
- Short BRSR6.SA (intradiário): -32,16% desde a entrada; -0,17% do NAV
- Short CMIG4.SA (intradiário): -16,08% desde a entrada; -0,06% do NAV
- Short TOTS3.SA (intradiário): -26,29% desde a entrada; -0,09% do NAV
- Short SBSP3.SA (intradiário): -25,65% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (intradiário): -23,57% desde a entrada; -0,08% do NAV
- Short PAM (intradiário): -20,13% desde a entrada; -0,06% do NAV
- Short BMA (intradiário): -13,84% desde a entrada; -0,04% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Vol ex-ante 2,43% abaixo da banda (3,00%–7,00%): subutilização do orçamento de risco.
- Short ORVR3.SA (BR_ORIZON) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (270): AC.MX@2026-10-26 (0.9994), ALSEA.MX@2026-10-26 (1.0025), AMXB.MX@2026-10-26 (0.9973), ASURB.MX@2026-10-26 (0.9995), BBAJIOO.MX@2026-10-26 (1.0029), BIMBOA.MX@2026-10-26 (1.0033), BOLSAA.MX@2026-10-26 (1.0019), CBAV3.SA@2026-10…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1330.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 2.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
