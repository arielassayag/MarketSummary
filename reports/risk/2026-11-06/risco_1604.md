# Risco — CDP — Cabra da Peste — 2026-11-06 16:04 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-05 (semana vigente 2026-10-23; hash `361ceb59efb1`)
- Decisão da semana 2026-11-06 gravada, a executar no fechamento: vol ex-ante 3,61%, beta +0,003, gross 80,10%, net +0,23%, 43 longs / 40 shorts

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 2 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 2 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `vol_abaixo_da_banda` | Vol ex-ante 2,38% abaixo da banda (3,00%–7,00%) | subutilização do orçamento de risco; nenhuma ação intradiária |

## NAV e drawdown (último fechamento)

- NAV: USD 1,00 mm (pico USD 1,01 mm)
- Retorno do dia: -0,14%; acumulado: +0,48%
- Drawdown: -0,48% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 2,38% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,005 (limite ±0,050)
- Net: +0,60% (limite ±1,00%); gross 55,99%; long 28,29%; short -27,70%; 39 longs / 36 shorts
- VaR 99% 1d: 0,38% (limite 1,00%); ES 99% 1d: 0,41% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 87,25%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 20

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD +1.688 (+0,17% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,31% — estágio normal
- Net/gross estimados: +0,76% / 56,77%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| LABB.MX | LONG | +5,76% | +6,30% | USD +839 | +0,08% |
| SGML | SHORT | +10,75% | +10,75% | USD -790 | -0,08% |
| TIGO | LONG | +5,33% | +5,33% | USD +688 | +0,07% |
| RIAA3.SA | LONG | +6,84% | +6,91% | USD +659 | +0,07% |
| AERO | LONG | +4,22% | +4,22% | USD +558 | +0,06% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 2
- Short LILAK (fechamento): +10,61% desde a entrada; +0,13% do NAV
- Short ASR (fechamento): +13,14% desde a entrada; +0,16% do NAV
- Short EMBJ (fechamento): +3,41% desde a entrada; +0,04% do NAV
- Short LAR (fechamento): -18,62% desde a entrada; -0,28% do NAV
- Short TIMS3.SA (fechamento): +4,56% desde a entrada; +0,05% do NAV
- Short AGRO (fechamento): -11,04% desde a entrada; -0,14% do NAV
- Short BRAP4.SA (fechamento): -0,68% desde a entrada; -0,01% do NAV
- Short ARCO (fechamento): -11,49% desde a entrada; -0,14% do NAV
- Short MELI (fechamento): -17,84% desde a entrada; -0,23% do NAV
- Short NU (fechamento): -19,37% desde a entrada; -0,24% do NAV
- Short ORVR3.SA (fechamento): -19,76% desde a entrada; -0,24% do NAV
- Short UGPA3.SA (fechamento): -21,72% desde a entrada; -0,25% do NAV
- Short ALPA4.SA (fechamento): -25,27% desde a entrada; -0,30% do NAV
- Short SAPR11.SA (fechamento): -30,28% desde a entrada; -0,38% do NAV
- Short AURE3.SA (fechamento): -24,56% desde a entrada; -0,28% do NAV
- Short FLRY3.SA (fechamento): -25,23% desde a entrada; -0,29% do NAV
- Short BRAV3.SA (fechamento): -23,57% desde a entrada; -0,26% do NAV
- Short VBBR3.SA (fechamento): -22,24% desde a entrada; -0,24% do NAV
- Short ENGI11.SA (fechamento): -31,40% desde a entrada; -0,36% do NAV
- Short CIB (fechamento): -2,73% desde a entrada; -0,02% do NAV
- Short EQTL3.SA (fechamento): -34,62% desde a entrada; -0,39% do NAV
- Short SGML (fechamento): -40,48% desde a entrada; -0,50% do NAV
- Short PAC (fechamento): +10,56% desde a entrada; +0,07% do NAV
- Short RDOR3.SA (fechamento): -26,49% desde a entrada; -0,23% do NAV
- Short AG (fechamento): +0,81% desde a entrada; 0,00% do NAV
- Short GGAL (fechamento): -21,13% desde a entrada; -0,14% do NAV
- Short VIVT3.SA (fechamento): -4,04% desde a entrada; -0,02% do NAV
- Short BAP (fechamento): -6,00% desde a entrada; -0,03% do NAV
- Short STNE (fechamento): -34,76% desde a entrada; -0,21% do NAV
- Short BRSR6.SA (fechamento): -32,27% desde a entrada; -0,17% do NAV
- Short CMIG4.SA (fechamento): -16,24% desde a entrada; -0,06% do NAV
- Short SBSP3.SA (fechamento): -25,51% desde a entrada; -0,09% do NAV
- Short TOTS3.SA (fechamento): -26,38% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (fechamento): -23,63% desde a entrada; -0,08% do NAV
- Short PAM (fechamento): -19,41% desde a entrada; -0,06% do NAV
- Short BMA (fechamento): -12,19% desde a entrada; -0,03% do NAV
- Short LILAK (intradiário): +9,74% desde a entrada; +0,12% do NAV
- Short ASR (intradiário): +12,97% desde a entrada; +0,15% do NAV
- Short EMBJ (intradiário): +3,86% desde a entrada; +0,05% do NAV
- Short LAR (intradiário): -16,62% desde a entrada; -0,25% do NAV
- Short TIMS3.SA (intradiário): +5,45% desde a entrada; +0,06% do NAV
- Short AGRO (intradiário): -12,32% desde a entrada; -0,16% do NAV
- Short BRAP4.SA (intradiário): +1,10% desde a entrada; +0,01% do NAV
- Short ARCO (intradiário): -11,04% desde a entrada; -0,14% do NAV
- Short MELI (intradiário): -19,21% desde a entrada; -0,25% do NAV
- Short NU (intradiário): -17,00% desde a entrada; -0,21% do NAV
- Short ORVR3.SA (intradiário): -16,54% desde a entrada; -0,20% do NAV
- Short UGPA3.SA (intradiário): -23,18% desde a entrada; -0,27% do NAV
- Short ALPA4.SA (intradiário): -23,79% desde a entrada; -0,28% do NAV
- Short SAPR11.SA (intradiário): -27,24% desde a entrada; -0,34% do NAV
- Short AURE3.SA (intradiário): -21,52% desde a entrada; -0,25% do NAV
- Short FLRY3.SA (intradiário): -26,41% desde a entrada; -0,30% do NAV
- Short BRAV3.SA (intradiário): -23,86% desde a entrada; -0,26% do NAV
- Short VBBR3.SA (intradiário): -22,73% desde a entrada; -0,24% do NAV
- Short ENGI11.SA (intradiário): -29,45% desde a entrada; -0,34% do NAV
- Short CIB (intradiário): -3,29% desde a entrada; -0,03% do NAV
- Short EQTL3.SA (intradiário): -32,69% desde a entrada; -0,37% do NAV
- Short SGML (intradiário): -34,08% desde a entrada; -0,42% do NAV
- Short PAC (intradiário): +11,73% desde a entrada; +0,07% do NAV
- Short RDOR3.SA (intradiário): -24,15% desde a entrada; -0,21% do NAV
- Short AG (intradiário): +2,47% desde a entrada; +0,01% do NAV
- Short GGAL (intradiário): -22,21% desde a entrada; -0,15% do NAV
- Short VIVT3.SA (intradiário): -2,71% desde a entrada; -0,01% do NAV
- Short BAP (intradiário): -5,13% desde a entrada; -0,03% do NAV
- Short STNE (intradiário): -34,45% desde a entrada; -0,21% do NAV
- Short BRSR6.SA (intradiário): -29,74% desde a entrada; -0,16% do NAV
- Short CMIG4.SA (intradiário): -14,18% desde a entrada; -0,05% do NAV
- Short SBSP3.SA (intradiário): -20,54% desde a entrada; -0,07% do NAV
- Short TOTS3.SA (intradiário): -25,68% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (intradiário): -22,17% desde a entrada; -0,07% do NAV
- Short PAM (intradiário): -19,69% desde a entrada; -0,06% do NAV
- Short BMA (intradiário): -13,01% desde a entrada; -0,03% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Vol ex-ante 2,38% abaixo da banda (3,00%–7,00%): subutilização do orçamento de risco.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (313): AC.MX@2026-10-26 (0.9994), ALSEA.MX@2026-10-26 (1.0025), AMXB.MX@2026-10-26 (0.9973), ASURB.MX@2026-10-26 (0.9995), BBAJIOO.MX@2026-10-26 (1.0029), BIMBOA.MX@2026-10-26 (1.0033), BOLSAA.MX@2026-10-26 (1.0019), CBAV3.SA@2026-10…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1475.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 3.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: Aluguel B3 indisponível: RuntimeError('Fonte de aluguel B3 (BDI) indisponível: 2026-11-04: Falha de rede em POST https://arquivos.b3.com.br/bdi/table/BTBLoanBalance/2026-11-04/2026-11-04/5/1000: ReadTimeout(ReadTimeoutError("HTTPSConnectionPool(host=\'arquivos.b3.com.br\', port=443): Read timed out…
- Limitação de dados: Aluguel B3 (BDI) ausente para pregões já fechados: 2026-11-04 (nova tentativa nos próximos incrementos enquanto estiverem na janela D-21).
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio +6.0% no pregão (mediana -2.3%; tolerância 3%).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
