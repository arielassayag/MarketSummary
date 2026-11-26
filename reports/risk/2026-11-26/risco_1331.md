# Risco — CDP — Cabra da Peste — 2026-11-26 13:31 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-25 (semana vigente 2026-11-13; hash `c4c5d7fddcfd`)

## Ações recomendadas (determinísticas)

- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `cobertura_intradiaria_parcial` | Cobertura intradiária de 51,50% do gross (mínimo 95,00% para gatilho HARD de drawdown) | gatilhos intradiários de drawdown rebaixados a SOFT |

## NAV e drawdown (último fechamento)

- NAV: USD 993,8 mil (pico USD 1,01 mm)
- Retorno do dia: -0,06%; acumulado: -0,62%
- Drawdown: -1,57% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,56% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,018 (limite ±0,050)
- Net: -0,72% (limite ±1,00%); gross 87,19%; long 43,23%; short -43,96%; 49 longs / 44 shorts
- VaR 99% 1d: 0,52% (limite 1,00%); ES 99% 1d: 0,69% (limite 1,25%)
- Vol realizada 21d: 3,03%; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 90,80%; realizada em 63 pregões: 95,03%; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 34

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -2.672 (-0,27% do NAV)
- NAV estimado: USD 991,1 mil; drawdown estimado: -1,83% — estágio normal
- Net/gross estimados: -1,00% / 89,78%
- Cobertura do gross com cotação de hoje: 51,50% (parcial)

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| SMFT3.SA | SHORT | +7,70% | +9,15% | USD -2.242 | -0,23% |
| AURE3.SA | SHORT | +5,54% | +6,96% | USD -1.716 | -0,17% |
| FLRY3.SA | SHORT | +4,94% | +6,36% | USD -1.437 | -0,14% |
| BBAS3.SA | SHORT | +6,81% | +8,25% | USD -1.158 | -0,12% |
| TEND3.SA | LONG | +4,55% | +5,97% | USD +1.133 | +0,11% |

Sem cotação do dia (fora do P&L): PAGS (sem negócio hoje), LILAK (sem negócio hoje), PAX (sem negócio hoje), CX (sem negócio hoje), FSM (sem negócio hoje), AERO (sem negócio hoje), AUGO (sem negócio hoje), TEO (sem negócio hoje), TIGO (sem negócio hoje), ASR (sem negócio hoje), PBR (sem negócio hoje), EMBJ (sem negócio hoje), PICS (sem negócio hoje), ARCO (sem negócio hoje), AMX (sem negócio hoje), NU (sem negócio hoje), AGRO (sem negócio hoje), MELI (sem negócio hoje), LAR (sem negócio hoje), BMA (sem negócio hoje), GGB (sem negócio hoje), CEPU (sem negócio hoje), VALE (sem negócio hoje), BAP (sem negócio hoje), PAC (sem negócio hoje), INTR (sem negócio hoje), BCH (sem negócio hoje), CPA (sem negócio hoje), VTEX (sem negócio hoje), VIST (sem negócio hoje), HBM (sem negócio hoje), LTM (sem negócio hoje), EXK (sem negócio hoje), DLO (sem negócio hoje), JBS (sem negócio hoje), BBAR (sem negócio hoje), STNE (sem negócio hoje), AG (sem negócio hoje), IRS (sem negócio hoje), BVN (sem negócio hoje), PAM (sem negócio hoje), TGS (sem negócio hoje), ITUB (sem negócio hoje)

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short LILAK (fechamento): +11,52% desde a entrada; +0,26% do NAV
- Short AURE3.SA (fechamento): -8,59% desde a entrada; -0,23% do NAV
- Short SMFT3.SA (fechamento): +3,18% desde a entrada; +0,08% do NAV
- Short PAX (fechamento): -1,58% desde a entrada; -0,04% do NAV
- Short FLRY3.SA (fechamento): -1,89% desde a entrada; -0,04% do NAV
- Short CX (fechamento): -7,74% desde a entrada; -0,18% do NAV
- Short AUGO (fechamento): -19,12% desde a entrada; -0,39% do NAV
- Short ASR (fechamento): +20,38% desde a entrada; +0,24% do NAV
- Short BBAS3.SA (fechamento): -2,72% desde a entrada; -0,04% do NAV
- Short TIMS3.SA (fechamento): +14,35% desde a entrada; +0,16% do NAV
- Short EMBJ (fechamento): -9,51% desde a entrada; -0,13% do NAV
- Short BRAV3.SA (fechamento): -28,42% desde a entrada; -0,49% do NAV
- Short ARCO (fechamento): -12,37% desde a entrada; -0,16% do NAV
- Short NU (fechamento): -15,11% desde a entrada; -0,19% do NAV
- Short AGRO (fechamento): -20,93% desde a entrada; -0,27% do NAV
- Short MELI (fechamento): -21,22% desde a entrada; -0,28% do NAV
- Short LAR (fechamento): -33,41% desde a entrada; -0,50% do NAV
- Short BRAP4.SA (fechamento): -14,10% desde a entrada; -0,16% do NAV
- Short BMA (fechamento): -15,45% desde a entrada; -0,17% do NAV
- Short SAPR11.SA (fechamento): -21,53% desde a entrada; -0,26% do NAV
- Short UGPA3.SA (fechamento): -21,11% desde a entrada; -0,23% do NAV
- Short ALPA4.SA (fechamento): -23,61% desde a entrada; -0,27% do NAV
- Short ENGI11.SA (fechamento): -22,41% desde a entrada; -0,25% do NAV
- Short BBDC4.SA (fechamento): -0,07% desde a entrada; 0,00% do NAV
- Short VALE (fechamento): -12,57% desde a entrada; -0,11% do NAV
- Short EQTL3.SA (fechamento): -31,29% desde a entrada; -0,34% do NAV
- Short BAP (fechamento): -5,05% desde a entrada; -0,04% do NAV
- Short RDOR3.SA (fechamento): -17,20% desde a entrada; -0,14% do NAV
- Short PAC (fechamento): +4,02% desde a entrada; +0,03% do NAV
- Short INTR (fechamento): -3,37% desde a entrada; -0,02% do NAV
- Short BCH (fechamento): -6,43% desde a entrada; -0,05% do NAV
- Short CSMG3.SA (fechamento): +8,83% desde a entrada; +0,05% do NAV
- Short VIVT3.SA (fechamento): +7,31% desde a entrada; +0,04% do NAV
- Short VBBR3.SA (fechamento): -11,72% desde a entrada; -0,07% do NAV
- Short DLO (fechamento): -8,18% desde a entrada; -0,04% do NAV
- Short ASAI3.SA (fechamento): +11,69% desde a entrada; +0,04% do NAV
- Short BRSR6.SA (fechamento): -32,64% desde a entrada; -0,17% do NAV
- Short BEEF3.SA (fechamento): +11,44% desde a entrada; +0,03% do NAV
- Short CMIG4.SA (fechamento): -11,54% desde a entrada; -0,04% do NAV
- Short AG (fechamento): -23,97% desde a entrada; -0,10% do NAV
- Short RAIL3.SA (fechamento): -8,34% desde a entrada; -0,03% do NAV
- Short LREN3.SA (fechamento): -6,75% desde a entrada; -0,02% do NAV
- Short PAM (fechamento): -21,61% desde a entrada; -0,07% do NAV
- Short TGS (fechamento): -7,62% desde a entrada; -0,02% do NAV
- Short AURE3.SA (intradiário): -3,53% desde a entrada; -0,10% do NAV
- Short SMFT3.SA (intradiário): +11,12% desde a entrada; +0,27% do NAV
- Short FLRY3.SA (intradiário): +2,96% desde a entrada; +0,07% do NAV
- Short BBAS3.SA (intradiário): +3,91% desde a entrada; +0,06% do NAV
- Short TIMS3.SA (intradiário): +18,39% desde a entrada; +0,20% do NAV
- Short BRAV3.SA (intradiário): -25,48% desde a entrada; -0,45% do NAV
- Short BRAP4.SA (intradiário): -11,84% desde a entrada; -0,13% do NAV
- Short SAPR11.SA (intradiário): -19,33% desde a entrada; -0,23% do NAV
- Short UGPA3.SA (intradiário): -18,34% desde a entrada; -0,21% do NAV
- Short ALPA4.SA (intradiário): -23,91% desde a entrada; -0,27% do NAV
- Short ENGI11.SA (intradiário): -19,21% desde a entrada; -0,22% do NAV
- Short BBDC4.SA (intradiário): +6,55% desde a entrada; +0,05% do NAV
- Short EQTL3.SA (intradiário): -27,61% desde a entrada; -0,30% do NAV
- Short RDOR3.SA (intradiário): -13,49% desde a entrada; -0,11% do NAV
- Short CSMG3.SA (intradiário): +11,57% desde a entrada; +0,07% do NAV
- Short VIVT3.SA (intradiário): +10,18% desde a entrada; +0,05% do NAV
- Short VBBR3.SA (intradiário): -7,91% desde a entrada; -0,04% do NAV
- Short ASAI3.SA (intradiário): +18,16% desde a entrada; +0,07% do NAV
- Short BRSR6.SA (intradiário): -30,12% desde a entrada; -0,16% do NAV
- Short BEEF3.SA (intradiário): +13,49% desde a entrada; +0,04% do NAV
- Short CMIG4.SA (intradiário): -7,75% desde a entrada; -0,03% do NAV
- Short RAIL3.SA (intradiário): -5,01% desde a entrada; -0,02% do NAV
- Short LREN3.SA (intradiário): -1,31% desde a entrada; 0,00% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (221): BAK@2026-11-16 (0.9999), SID@2026-11-16 (0.9973), AC.MX@2026-11-17 (1.0022), ALPEKA.MX@2026-11-17 (1.0038), ALSEA.MX@2026-11-17 (1.0024), AMXB.MX@2026-11-17 (0.9996), ASURB.MX@2026-11-17 (1.0019), BAK@2026-11-17 (0.9999), BBAJ…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 703.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -8.5% no pregão (mediana -0.8%; tolerância 3%).
- Limitação de dados: EMBJ em 17/11/2026: predecessor selado reconciliado com Nasdaq e eventos Yahoo consultados retrospectivamente.

## Limitações

- Posições sem cotação do dia ficam fora do P&L intradiário (nunca viram retorno zero) e entram no net/gross estimados pelo valor do último fechamento.
- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
