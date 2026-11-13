# Risco — CDP — Cabra da Peste — 2026-11-13 16:07 (Brasília)

> Dados reais de mercado (Yahoo Finance, B3, FINRA, BCB); carteira simulada com execução hipotética no leilão de fechamento e custos do modelo.

- Modo: intradiário (cotações ao vivo)
- Status: ok
- Kill switch: desligado
- Base: registro de 2026-11-12 (semana vigente 2026-11-06; hash `f2eb72564c24`)
- Decisão da semana 2026-11-13 gravada, a executar no fechamento: vol ex-ante 3,64%, beta +0,002, gross 90,39%, net +0,68%, 49 longs / 44 shorts

## Ações recomendadas (determinísticas)

- revisar: BRAP4.SA: variação do fechamento -5.7% difere da do fechamento ajustado -1.4% — possível grupamento, desdobramento ou provento.

## Gatilhos

| Nível | Código | Motivo | Ação |
|---|---|---|---|
| SOFT | `possivel_evento_societario:BRAP4.SA` | BRAP4.SA: variação do fechamento -5.7% difere da do fechamento ajustado -1.4% — possível grupamento, desdobramento ou provento. | conferir o evento societário antes do próximo rebalanceamento |

## NAV e drawdown (último fechamento)

- NAV: USD 1,01 mm (pico USD 1,01 mm)
- Retorno do dia: -0,03%; acumulado: +0,67%
- Drawdown: -0,29% — estágio normal (soft -2,50%, hard -5,00%, stop-out -7,50%)

## Risco ex-ante (último fechamento)

- Vol ex-ante: 3,67% (alvo 5,00%; banda 3,00%–7,00%)
- Beta: +0,002 (limite ±0,050)
- Net: +0,34% (limite ±1,00%); gross 80,49%; long 40,42%; short -40,08%; 43 longs / 40 shorts
- VaR 99% 1d: 0,54% (limite 1,00%); ES 99% 1d: 0,67% (limite 1,25%)
- Vol realizada 21d: 2,03%; 63d: n/d

## Fatia idiossincrática (três medidas)

- Ex-ante (κ_F 1,45): 92,71%; realizada em 63 pregões: 90,28%; sem modelo (1 − R² ajustado): n/d
- Meta 90,00%; piso 85,00%; registros na janela: 25

## Intradiário (estimado, cotações atrasadas da fonte)

- P&L desde o fechamento: USD -1.006 (-0,10% do NAV)
- NAV estimado: USD 1,01 mm; drawdown estimado: -0,39% — estágio normal
- Net/gross estimados: +0,24% / 80,86%
- Cobertura do gross com cotação de hoje: 100,00%

| Ticker | Lado | Ret. local | Ret. USD | P&L (USD) | Contrib. |
|---|---|---|---|---|---|
| NU | SHORT | +10,31% | +10,31% | USD -1.035 | -0,10% |
| AUGO | SHORT | -3,73% | -3,73% | USD +921 | +0,09% |
| PICS | LONG | +5,46% | +5,46% | USD +841 | +0,08% |
| AGRO | SHORT | +4,96% | +4,96% | USD -535 | -0,05% |
| TIGO | LONG | -3,20% | -3,20% | USD -421 | -0,04% |

## Liquidez

- Máximo de fechamentos para liquidar: 0,2 fech.; gross liquidável em 1 fechamento: 100,00%

## Short squeeze

- Shorts HIGH no último fechamento: 0
- Short LILAK (fechamento): +15,98% desde a entrada; +0,36% do NAV
- Short AUGO (fechamento): +0,15% desde a entrada; 0,00% do NAV
- Short CX (fechamento): -2,33% desde a entrada; -0,06% do NAV
- Short PAX (fechamento): -3,37% desde a entrada; -0,08% do NAV
- Short SMFT3.SA (fechamento): -2,19% desde a entrada; -0,05% do NAV
- Short FLRY3.SA (fechamento): -8,01% desde a entrada; -0,19% do NAV
- Short ASR (fechamento): +16,27% desde a entrada; +0,19% do NAV
- Short EMBJ3.SA (fechamento): +10,48% desde a entrada; +0,13% do NAV
- Short TIMS3.SA (fechamento): +12,57% desde a entrada; +0,14% do NAV
- Short BRAP4.SA (fechamento): -3,42% desde a entrada; -0,04% do NAV
- Short ARCO (fechamento): -11,36% desde a entrada; -0,14% do NAV
- Short LAR (fechamento): -25,41% desde a entrada; -0,37% do NAV
- Short AGRO (fechamento): -17,11% desde a entrada; -0,22% do NAV
- Short MELI (fechamento): -20,80% desde a entrada; -0,27% do NAV
- Short BMA (fechamento): -7,25% desde a entrada; -0,08% do NAV
- Short NU (fechamento): -18,75% desde a entrada; -0,23% do NAV
- Short UGPA3.SA (fechamento): -18,85% desde a entrada; -0,21% do NAV
- Short SAPR11.SA (fechamento): -26,21% desde a entrada; -0,32% do NAV
- Short AURE3.SA (fechamento): -20,38% desde a entrada; -0,23% do NAV
- Short ALPA4.SA (fechamento): -23,32% desde a entrada; -0,27% do NAV
- Short VBBR3.SA (fechamento): -18,65% desde a entrada; -0,20% do NAV
- Short BBDC4.SA (fechamento): +0,85% desde a entrada; +0,01% do NAV
- Short ENGI11.SA (fechamento): -27,42% desde a entrada; -0,31% do NAV
- Short BRAV3.SA (fechamento): -29,63% desde a entrada; -0,32% do NAV
- Short EQTL3.SA (fechamento): -32,83% desde a entrada; -0,36% do NAV
- Short PAC (fechamento): +7,01% desde a entrada; +0,04% do NAV
- Short SGML (fechamento): -44,26% desde a entrada; -0,54% do NAV
- Short RDOR3.SA (fechamento): -22,96% desde a entrada; -0,19% do NAV
- Short AG (fechamento): -5,28% desde a entrada; -0,03% do NAV
- Short VIVT3.SA (fechamento): +3,67% desde a entrada; +0,02% do NAV
- Short BAP (fechamento): -1,30% desde a entrada; -0,01% do NAV
- Short CIB (fechamento): -6,51% desde a entrada; -0,03% do NAV
- Short ASAI3.SA (fechamento): +7,49% desde a entrada; +0,03% do NAV
- Short STNE (fechamento): -32,75% desde a entrada; -0,20% do NAV
- Short BRSR6.SA (fechamento): -30,66% desde a entrada; -0,16% do NAV
- Short CMIG4.SA (fechamento): -12,45% desde a entrada; -0,05% do NAV
- Short SBSP3.SA (fechamento): -19,85% desde a entrada; -0,07% do NAV
- Short RAIL3.SA (fechamento): -16,25% desde a entrada; -0,05% do NAV
- Short LREN3.SA (fechamento): -5,34% desde a entrada; -0,01% do NAV
- Short PAM (fechamento): -20,49% desde a entrada; -0,06% do NAV
- Short LILAK (intradiário): +16,04% desde a entrada; +0,36% do NAV
- Short AUGO (intradiário): -3,58% desde a entrada; -0,09% do NAV
- Short CX (intradiário): -1,77% desde a entrada; -0,04% do NAV
- Short PAX (intradiário): -3,74% desde a entrada; -0,09% do NAV
- Short SMFT3.SA (intradiário): -2,68% desde a entrada; -0,07% do NAV
- Short FLRY3.SA (intradiário): -7,27% desde a entrada; -0,17% do NAV
- Short ASR (intradiário): +15,56% desde a entrada; +0,18% do NAV
- Short EMBJ3.SA (intradiário): +8,57% desde a entrada; +0,11% do NAV
- Short TIMS3.SA (intradiário): +12,00% desde a entrada; +0,13% do NAV
- Short BRAP4.SA (intradiário): -4,26% desde a entrada; -0,05% do NAV
- Short ARCO (intradiário): -9,59% desde a entrada; -0,12% do NAV
- Short LAR (intradiário): -25,31% desde a entrada; -0,37% do NAV
- Short AGRO (intradiário): -13,00% desde a entrada; -0,17% do NAV
- Short MELI (intradiário): -19,94% desde a entrada; -0,26% do NAV
- Short BMA (intradiário): -5,41% desde a entrada; -0,06% do NAV
- Short NU (intradiário): -10,37% desde a entrada; -0,13% do NAV
- Short UGPA3.SA (intradiário): -16,78% desde a entrada; -0,19% do NAV
- Short SAPR11.SA (intradiário): -28,03% desde a entrada; -0,34% do NAV
- Short AURE3.SA (intradiário): -19,10% desde a entrada; -0,21% do NAV
- Short ALPA4.SA (intradiário): -21,31% desde a entrada; -0,24% do NAV
- Short VBBR3.SA (intradiário): -17,32% desde a entrada; -0,18% do NAV
- Short BBDC4.SA (intradiário): +1,41% desde a entrada; +0,01% do NAV
- Short ENGI11.SA (intradiário): -25,99% desde a entrada; -0,29% do NAV
- Short BRAV3.SA (intradiário): -29,34% desde a entrada; -0,32% do NAV
- Short EQTL3.SA (intradiário): -33,22% desde a entrada; -0,37% do NAV
- Short PAC (intradiário): +5,98% desde a entrada; +0,04% do NAV
- Short SGML (intradiário): -43,98% desde a entrada; -0,54% do NAV
- Short RDOR3.SA (intradiário): -20,87% desde a entrada; -0,18% do NAV
- Short AG (intradiário): -6,60% desde a entrada; -0,04% do NAV
- Short VIVT3.SA (intradiário): +4,22% desde a entrada; +0,02% do NAV
- Short BAP (intradiário): -0,79% desde a entrada; 0,00% do NAV
- Short CIB (intradiário): -6,24% desde a entrada; -0,03% do NAV
- Short ASAI3.SA (intradiário): +8,74% desde a entrada; +0,03% do NAV
- Short STNE (intradiário): -32,49% desde a entrada; -0,20% do NAV
- Short BRSR6.SA (intradiário): -31,19% desde a entrada; -0,16% do NAV
- Short CMIG4.SA (intradiário): -9,65% desde a entrada; -0,04% do NAV
- Short SBSP3.SA (intradiário): -18,66% desde a entrada; -0,06% do NAV
- Short RAIL3.SA (intradiário): -11,30% desde a entrada; -0,04% do NAV
- Short LREN3.SA (intradiário): -3,63% desde a entrada; -0,01% do NAV
- Short PAM (intradiário): -18,15% desde a entrada; -0,05% do NAV

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
- Limitação de dados: Revisões de fechamento do Yahoo em datas anteriores NÃO aplicadas (164): SCCO@2026-11-02 (0.9901), SID@2026-11-02 (0.9974), AC.MX@2026-11-03 (1.0004), ALPEKA.MX@2026-11-03 (1.0039), ALSEA.MX@2026-11-03 (1.0019), AMXB.MX@2026-11-03 (0.9970), ASURB.MX@2026-11-03 (1.0011), BBAJIOO.MX@2026-11-03 (1.000…
- Limitação de dados: Revisões de volume em datas anteriores NÃO aplicadas: 742.
- Limitação de dados: Barras tardias (datas anteriores não gravadas) NÃO aplicadas: 1.
- Limitação de dados: Benchmarks sem barra no pregão: ^MERV.
- Limitação de dados: Aluguel B3 indisponível: RuntimeError('Fonte de aluguel B3 (BDI) indisponível: 2026-11-12: BDI BTBLendingOpenPosition 2026-11-12: HTTP 502').

## Limitações

- NAV intradiário estimado sem accrual de financiamento/aluguel do dia; risco ex-ante e beta são os do último fechamento.

_Relatório gerado por código (`cdp risk`); nenhum número foi calculado por IA. Carteira simulada: o kill switch só bloqueia risco novo e nunca afrouxa limites._
