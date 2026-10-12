# Risco — CDP — Cabra da Peste — 2026-10-12 13:30 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: último fechamento
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-10-09 (semana vigente 2026-10-09; hash `093e281066e7`)

## Ações recomendadas (determinísticas)

- revisar: Exposição líquida +1,25% fora do limite ±1,00% (net neutral)
- revisar: Shorts com risco de squeeze HIGH: 1 no último fechamento

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `net_fora_do_limite` | Exposição líquida +1,25% fora do limite ±1,00% (net neutral) | reequilibrar no próximo rebalanceamento |
| SOFT | `squeeze_high` | Shorts com risco de squeeze HIGH: 1 no último fechamento | reavaliar/reduzir no próximo rebalanceamento |
| INFO | `janela_incompleta` | Janela de 5 registros incompleta (1): gatilho de 5 pregões não avaliado. |  |

## NAV e drawdown (último fechamento)

- NAV: USD 998,9 mil (pico USD 1,00 mm)
- Retorno do dia: -0,11%; acumulado: -0,11%
- Drawdown: -0,11% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,68% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,010 (limite ±0,050)
- Net: +1,25% (limite ±1,00%); gross 64,78%; long 33,02%; short -31,77%; 37 longs / 36 shorts
- VaR 99% 1d: 0,54% (limite 1,00%); ES 99% 1d: 0,62% (limite 1,25%)
- Vol realizada 21d: n/d; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 94,11%; realizada em 63 pregões: n/d; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 1

## Liquidez

- Máximo de fechamentos para liquidar: 0,4 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 1
- Short PAX (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short INTR (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short UGPA3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BBDC4.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short FMX (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short CX (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short EQTL3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short YPF (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short ALOS3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BRAV3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short VBBR3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short AGRO (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short SAPR11.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short ASR (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short LAR (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short SGML (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short ALPA4.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short CIB (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short ORVR3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short MELI (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BCH (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short USIM5.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short LILAK (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short EMBJ (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short RDOR3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short ARCO (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short CSMG3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short CBAV3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short KLBN11.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short DLO (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short CMIG4.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short SBSP3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BRSR6.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short OMAB (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short BSAC (fechamento): 0,00% desde a entrada; 0,00% do NAV
- Short EGIE3.SA (fechamento): 0,00% desde a entrada; 0,00% do NAV

## Alertas do registro de fechamento

- Exposição líquida +1,25% fora do limite ±1,00% (net neutral).
- Short INTR (BR_INTER) com risco de squeeze HIGH (era LOW na decisão): reavaliar/reduzir.
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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (159): AC.MX@2026-10-05 (0.9995), ALPEKA.MX@2026-10-05 (1.0048), ALSEA.MX@2026-10-05 (0.9998), AMXB.MX@2026-10-05 (0.9985), ANDINA-B.SN@2026-10-05 (0.9592), ASURB.MX@2026-10-05 (0.9966), BBAJIOO.MX@2026-10-05 (0.9990), BCI.SN@2026-10…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 807.
- Limitação de dados: QA paridade ADR: SID vs CSNA3.SA desvio -3.3% no pregão (mediana -3.6%; tolerância 3%).
- Janela de evento ativa: Eleição Brasil 2026 (2º turno 25/out) (vol × 1,50 em BR).

## Limitações

- nenhuma

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
