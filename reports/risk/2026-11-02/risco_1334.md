# Risco — CDP — Cabra da Peste — 2026-11-02 13:34 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: último fechamento
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-29 (semana vigente 2026-10-23; hash `9ab0d3f83346`)

## Ações recomendadas (determinísticas)

- revisar: Último registro diário é de 2026-10-29; o pregão de 2026-10-30 não foi fechado
- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `registro_defasado` | Último registro diário é de 2026-10-29; o pregão de 2026-10-30 não foi fechado | rodar o fechamento diário pendente (skill diario) |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `vol_abaixo_da_banda` | Vol ex-ante 2,47% abaixo da banda (3,00%–7,00%) | subutilização do orçamento de risco; nenhuma ação intradiária |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: +0,10%; acumulado: +0,75%
- Drawdown: -0,04% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 2,47% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: -0,002 (limite ±0,050)
- Net: +0,93% (limite ±1,00%); gross 58,19%; long 29,56%; short -28,63%; 39 longs / 36 shorts
- VaR 99% 1d: 0,39% (limite 1,00%); ES 99% 1d: 0,44% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 89,84%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 15

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short LAR (fechamento): -11,02% desde a entrada; -0,16% do NAV
- Short EMBJ (fechamento): +5,81% desde a entrada; +0,07% do NAV
- Short LILAK (fechamento): +2,66% desde a entrada; +0,03% do NAV
- Short ASR (fechamento): +8,23% desde a entrada; +0,10% do NAV
- Short AGRO (fechamento): -4,98% desde a entrada; -0,06% do NAV
- Short TIMS3.SA (fechamento): +1,78% desde a entrada; +0,02% do NAV
- Short MELI (fechamento): -10,87% desde a entrada; -0,14% do NAV
- Short BRAP4.SA (fechamento): -6,47% desde a entrada; -0,08% do NAV
- Short ARCO (fechamento): -12,62% desde a entrada; -0,16% do NAV
- Short SGML (fechamento): -14,78% desde a entrada; -0,18% do NAV
- Short NU (fechamento): -17,24% desde a entrada; -0,21% do NAV
- Short BRAV3.SA (fechamento): -13,38% desde a entrada; -0,15% do NAV
- Short UGPA3.SA (fechamento): -18,11% desde a entrada; -0,21% do NAV
- Short ORVR3.SA (fechamento): -24,95% desde a entrada; -0,31% do NAV
- Short SAPR11.SA (fechamento): -27,62% desde a entrada; -0,35% do NAV
- Short ALPA4.SA (fechamento): -23,55% desde a entrada; -0,28% do NAV
- Short VBBR3.SA (fechamento): -17,18% desde a entrada; -0,19% do NAV
- Short FLRY3.SA (fechamento): -23,50% desde a entrada; -0,28% do NAV
- Short AURE3.SA (fechamento): -25,98% desde a entrada; -0,30% do NAV
- Short ENGI11.SA (fechamento): -31,84% desde a entrada; -0,38% do NAV
- Short CIB (fechamento): -1,32% desde a entrada; -0,01% do NAV
- Short EQTL3.SA (fechamento): -35,17% desde a entrada; -0,41% do NAV
- Short RDOR3.SA (fechamento): -27,21% desde a entrada; -0,24% do NAV
- Short PAC (fechamento): +2,27% desde a entrada; +0,01% do NAV
- Short AG (fechamento): +3,79% desde a entrada; +0,02% do NAV
- Short GGAL (fechamento): -11,03% desde a entrada; -0,07% do NAV
- Short VIVT3.SA (fechamento): -5,18% desde a entrada; -0,03% do NAV
- Short BAP (fechamento): -2,44% desde a entrada; -0,01% do NAV
- Short STNE (fechamento): -30,31% desde a entrada; -0,18% do NAV
- Short BRSR6.SA (fechamento): -32,59% desde a entrada; -0,18% do NAV
- Short CMIG4.SA (fechamento): -16,98% desde a entrada; -0,07% do NAV
- Short PAM (fechamento): -5,51% desde a entrada; -0,02% do NAV
- Short TOTS3.SA (fechamento): -25,07% desde a entrada; -0,09% do NAV
- Short SBSP3.SA (fechamento): -25,18% desde a entrada; -0,09% do NAV
- Short RAIL3.SA (fechamento): -23,36% desde a entrada; -0,08% do NAV
- Short BMA (fechamento): -7,22% desde a entrada; -0,02% do NAV

## Alertas do registro de fechamento

- Retornos fatoriais do dia estimados por regressão cross-section com as exposições da sessão anterior. Macro observado descontado antes da regressão estrutural.
- Vol ex-ante 2,47% abaixo da banda (3,00%–7,00%): subutilização do orçamento de risco.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (330): AC.MX@2026-10-19 (1.0004), ALPEKA.MX@2026-10-19 (1.0025), ALSEA.MX@2026-10-19 (1.0013), AMXB.MX@2026-10-19 (1.0014), ASURB.MX@2026-10-19 (1.0014), BBAJIOO.MX@2026-10-19 (0.9981), BIMBOA.MX@2026-10-19 (0.9998), BOLSAA.MX@2026-1…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 2099.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 3.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -1.0% no pregão (mediana -3.1%; tolerância 3%).

## Limitações

- nenhuma

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
