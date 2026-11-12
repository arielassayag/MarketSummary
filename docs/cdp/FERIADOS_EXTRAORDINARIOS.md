# Feriados extraordinários: BYMA, novembro de 2026

Conferência em 12/11/2026. A biblioteca `exchange_calendars 4.13.2` classificava
09 e 10/11/2026 como pregões XBUE. O calendário oficial da BYMA, versão publicada
em 05/10/2026, determina ausência de negociação e liquidação nas duas datas.
A exceção explícita em `cdp.calendar` é compartilhada com a prontidão da base em
`cdp.data.store`. Não altera mandato, percentuais mínimos, câmbio nem fontes de preços.

## Evidência primária

- [Página do calendário bursátil BYMA](https://www.byma.com.ar/mercado/calendario-bursatil).
- [PDF oficial BYMA, versão de outubro/2026](https://cdn.prod.website-files.com/6697a441a50c6b926e1972e0/6ac4f9ae3586c3d1c5453462_BYMA-Calendario_bursatil_2026-vOCT_6.pdf).
  SHA-256 dos bytes conferidos:
  `b8c860f46dee6093c4e6f8228bf7888ed2238a1448a6836b8db938f90009b0ec`.
  A legenda foi conferida visualmente: 09/11 é feriado nacional; 10/11 é dia sem
  negociação nem liquidação. Em 11/11 há negociação e somente restrição de liquidação
  em cable pelo feriado dos EUA. Não tratar 11/11 como fechamento.
- [BCRA, Comunicação C102390, 01/10/2026](https://www.bcra.gob.ar/archivos/Pdfs/comytexord/C102390.pdf):
  feriado nacional de 09/11, Decreto 1103/2026.
- [BCRA, Comunicação A8487, 01/10/2026](https://www.bcra.gob.ar/archivos/Pdfs/comytexord/A8487.pdf):
  feriado bancário de 10/11.

## Limites e regressão

A consulta Yahoo realizada em 12/11 trouxe as quatro linhas locais do universo até
06/11, nenhuma barra de 09/11 e barras com preço repetido e volume zero em 10/11.
A correção permite que o mecanismo existente descarte essas barras sintéticas
somente em mercado oficialmente fechado. Barras com volume real continuam preservadas
para expor divergências de calendário. O dia 11/11 permanece aberto e seu controle de
preços suficientes continua obrigatório; sua ausência no Yahoo é pendência separada.

Os testes cobrem as duas interfaces de calendário, ausência de horário de fechamento
nos feriados, negociação em 06/11 e 11–13/11, B3/NYSE inalteradas e descarte de barras
sintéticas sem perder barras reais. Não há regravação de histórico nem substituição de
preços por zero, repetição do preço anterior ou dados presumidos.

## Diagnóstico separado de 11/11

Consultas diretas ao endpoint público Yahoo `v8/finance/chart` nas variantes `query1`
e `query2`, janelas `range=1mo` e período 01–12/11, confirmaram para GGAL.BA a barra
com data 11/11 mas `close=null` e `adjclose=null`. As linhas BMA.BA, PAMP.BA e YPFD.BA
mostraram a mesma lacuna em `query1/range=1mo`. Há campos intradiários e volume, mas
não fechamento utilizável: a normalização não está descartando um fechamento válido.

O [resumo diário BYMA/IAMC](https://www.iamc.com.ar/informesmes/) consultado em
12/11 confirma negociação em 11/11 (`acc.fecha=2026-11-11`, anterior `2026-11-06`).
SHA-256 do HTML: `7221e9ff91a9340dcfb56990d167f17f82aec1bcd5714b7591f5c023a731daa3`.
Seu fechamento bruto (`px`) e volume financeiro (`ve`) não equivalem a preço ajustado
e volume nominal de ações. Não foi implementado preenchimento nem fallback usando
esses campos. A ausência do fechamento ajustado deve continuar bloqueando o pregão
aberto; nenhuma barra intradiária ou preço anterior pode ser presumida como fechamento.
