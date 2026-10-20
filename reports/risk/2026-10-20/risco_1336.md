# Risco — CDP — Cabra da Peste — 2026-10-20 13:36 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-19 (semana vigente 2026-10-16; hash `884a821165f5`)

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: +0,14%; acumulado: +0,64%
- Drawdown: 0,00% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,51% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,003 (limite ±0,050)
- Net: +0,28% (limite ±1,00%); gross 67,19%; long 33,73%; short -33,46%; 38 longs / 35 shorts
- VaR 99% 1d: 0,51% (limite 1,00%); ES 99% 1d: 0,59% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 89,87%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 7

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -3.624 (-0,36% do NAV)
- NAV estimado: USD 1,00 mm; drawdown estimado: -0,36% — estágio normal
- Net/gross estimados: -0,08% / 68,75%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| AERO | LONG | -7,74% | -7,74% | USD -1.919 | -0,19% |
| RIAA3.SA | LONG | +6,05% | +7,02% | USD +976 | +0,10% |
| CURY3.SA | LONG | +5,29% | +6,26% | USD +746 | +0,07% |
| NU | SHORT | +6,03% | +6,03% | USD -742 | -0,07% |
| HYPE3.SA | LONG | +4,39% | +5,34% | USD +695 | +0,07% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short FMX (fechamento): +6,45% desde a entrada; +0,08% do NAV
- Short ENGI11.SA (fechamento): +1,16% desde a entrada; +0,01% do NAV
- Short FLRY3.SA (fechamento): +1,59% desde a entrada; +0,02% do NAV
- Short UGPA3.SA (fechamento): +0,03% desde a entrada; 0,00% do NAV
- Short ORVR3.SA (fechamento): -4,49% desde a entrada; -0,06% do NAV
- Short AURE3.SA (fechamento): +0,47% desde a entrada; +0,01% do NAV
- Short EMBJ (fechamento): +2,10% desde a entrada; +0,03% do NAV
- Short CX (fechamento): +7,64% desde a entrada; +0,09% do NAV
- Short USIM5.SA (fechamento): -5,06% desde a entrada; -0,07% do NAV
- Short PAX (fechamento): +0,60% desde a entrada; +0,01% do NAV
- Short BRAV3.SA (fechamento): +1,65% desde a entrada; +0,02% do NAV
- Short YPF (fechamento): +1,30% desde a entrada; +0,02% do NAV
- Short NU (fechamento): -0,34% desde a entrada; 0,00% do NAV
- Short LAR (fechamento): -10,74% desde a entrada; -0,14% do NAV
- Short EQTL3.SA (fechamento): -4,32% desde a entrada; -0,05% do NAV
- Short ALOS3.SA (fechamento): -2,65% desde a entrada; -0,03% do NAV
- Short MELI (fechamento): -1,68% desde a entrada; -0,02% do NAV
- Short ARCO (fechamento): +1,06% desde a entrada; +0,01% do NAV
- Short ASR (fechamento): +3,36% desde a entrada; +0,03% do NAV
- Short SAPR11.SA (fechamento): -9,65% desde a entrada; -0,11% do NAV
- Short VBBR3.SA (fechamento): -1,60% desde a entrada; -0,02% do NAV
- Short AGRO (fechamento): -5,86% desde a entrada; -0,06% do NAV
- Short RDOR3.SA (fechamento): -2,47% desde a entrada; -0,02% do NAV
- Short SGML (fechamento): -9,41% desde a entrada; -0,09% do NAV
- Short CIB (fechamento): +0,83% desde a entrada; +0,01% do NAV
- Short BSAC (fechamento): +0,28% desde a entrada; 0,00% do NAV
- Short BCH (fechamento): +0,21% desde a entrada; 0,00% do NAV
- Short LILAK (fechamento): -3,08% desde a entrada; -0,02% do NAV
- Short CSMG3.SA (fechamento): -3,53% desde a entrada; -0,02% do NAV
- Short KLBN11.SA (fechamento): +0,17% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (fechamento): -4,29% desde a entrada; -0,02% do NAV
- Short SBSP3.SA (fechamento): -4,20% desde a entrada; -0,02% do NAV
- Short BRSR6.SA (fechamento): -6,94% desde a entrada; -0,03% do NAV
- Short RAIL3.SA (fechamento): -0,16% desde a entrada; 0,00% do NAV
- Short OMAB (fechamento): +2,16% desde a entrada; +0,01% do NAV
- Short FMX (intradiário): +8,63% desde a entrada; +0,11% do NAV
- Short ENGI11.SA (intradiário): +4,86% desde a entrada; +0,06% do NAV
- Short FLRY3.SA (intradiário): +5,09% desde a entrada; +0,06% do NAV
- Short UGPA3.SA (intradiário): +2,07% desde a entrada; +0,03% do NAV
- Short ORVR3.SA (intradiário): -0,71% desde a entrada; -0,01% do NAV
- Short AURE3.SA (intradiário): +3,78% desde a entrada; +0,05% do NAV
- Short EMBJ (intradiário): +2,18% desde a entrada; +0,03% do NAV
- Short CX (intradiário): +7,58% desde a entrada; +0,09% do NAV
- Short USIM5.SA (intradiário): -2,20% desde a entrada; -0,03% do NAV
- Short PAX (intradiário): +2,61% desde a entrada; +0,03% do NAV
- Short BRAV3.SA (intradiário): +1,75% desde a entrada; +0,02% do NAV
- Short YPF (intradiário): +2,20% desde a entrada; +0,03% do NAV
- Short NU (intradiário): +5,67% desde a entrada; +0,07% do NAV
- Short LAR (intradiário): -11,42% desde a entrada; -0,15% do NAV
- Short EQTL3.SA (intradiário): -1,38% desde a entrada; -0,02% do NAV
- Short ALOS3.SA (intradiário): +0,17% desde a entrada; 0,00% do NAV
- Short MELI (intradiário): -0,87% desde a entrada; -0,01% do NAV
- Short ARCO (intradiário): +3,67% desde a entrada; +0,04% do NAV
- Short ASR (intradiário): +6,60% desde a entrada; +0,07% do NAV
- Short SAPR11.SA (intradiário): -7,30% desde a entrada; -0,09% do NAV
- Short VBBR3.SA (intradiário): -0,89% desde a entrada; -0,01% do NAV
- Short AGRO (intradiário): -6,15% desde a entrada; -0,07% do NAV
- Short RDOR3.SA (intradiário): +0,50% desde a entrada; 0,00% do NAV
- Short SGML (intradiário): -8,77% desde a entrada; -0,09% do NAV
- Short CIB (intradiário): +0,92% desde a entrada; +0,01% do NAV
- Short BSAC (intradiário): +1,89% desde a entrada; +0,01% do NAV
- Short BCH (intradiário): +2,37% desde a entrada; +0,02% do NAV
- Short LILAK (intradiário): -1,11% desde a entrada; -0,01% do NAV
- Short CSMG3.SA (intradiário): -1,21% desde a entrada; -0,01% do NAV
- Short KLBN11.SA (intradiário): +0,99% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (intradiário): -2,14% desde a entrada; -0,01% do NAV
- Short SBSP3.SA (intradiário): -2,50% desde a entrada; -0,01% do NAV
- Short BRSR6.SA (intradiário): -4,40% desde a entrada; -0,02% do NAV
- Short RAIL3.SA (intradiário): +4,09% desde a entrada; +0,01% do NAV
- Short OMAB (intradiário): +4,41% desde a entrada; +0,01% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Short FLRY3.SA (BR_FLEURY) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
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
- Limitação de dados: Retorno total por preço (sem barra anterior na janela) para: CEMARGOS.CL, CIBEST.CL, ECOPETROL.CL, GRUPOARGOS.CL, GRUPOSURA.CL, ISA.CL, PFCIBEST.CL, PFGRUPOARG.CL, PFGRUPSURA.CL.
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (296): AC.MX@2026-10-09 (0.9996), ALPEKA.MX@2026-10-09 (1.0078), ALSEA.MX@2026-10-09 (0.9998), AMXB.MX@2026-10-09 (0.9985), ANDINA-B.SN@2026-10-09 (0.9895), ASURB.MX@2026-10-09 (1.0000), BBAJIOO.MX@2026-10-09 (1.0009), BCI.SN@2026-10…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 1426.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -4.4% no pregão (mediana -3.5%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
