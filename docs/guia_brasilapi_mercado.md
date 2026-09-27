# Coleta pública: fontes, horários e limites

Consulte [o roteiro completo](../README.md). O comando não exige chave de IA:

```sh
uv run python -m fechamento fetch --output-dir data/real/minha_coleta
```

A saída deve ser uma pasta nova. O código está em [live_fetcher.py](../src/fechamento/live_fetcher.py).

| Informação | Fonte | Limitação |
|---|---|---|
| Selic/CDI | BrasilAPI `/api/taxas/v1` | Retrato da consulta; endpoint não informa vigência |
| USD/BRL | AwesomeAPI `/last/USD-BRL,EUR-BRL` | Bid e referência de variação da própria fonte |
| IBOV e ações | Yahoo Finance Chart, intervalo diário | Endpoint público sujeito a bloqueio/atraso; não é feed oficial da B3 |
| Manchetes | Google News RSS | Preserva publicação e link; não verifica veracidade |
| Pesos de carteira | Código de exemplo | Simulados, iguais, explicitamente identificados |

O retorno de cada ação usa a última cotação e o fechamento da sessão anterior na série. `chartPreviousClose` pode ser o fechamento anterior ao início do intervalo de cinco dias, por isso não serve automaticamente de referência diária. Não há ajuste de proventos/splits.

`quotes.csv` guarda o timestamp da fonte. `manifest.json` guarda a sessão, o corte da coleta e hashes; `sources.json` guarda as URLs e limitações. Em fins de semana a data da cotação continua sendo a da sessão disponível. As notícias usam uma janela recente e podem ser posteriores a essa sessão.

Falhas em cotações obrigatórias interrompem a coleta. Taxas e notícias ausentes são registradas; nunca são substituídas por valores ou textos inventados. Sessões incompatíveis, timestamp futuro e atraso superior a sete dias bloqueiam a coleta. Mesmo dentro desse limite, confira a atualidade dos dados antes de usar o rascunho.

Só `1d` é aceito. Não há implementação semanal/mensal. Como há carteira simulada, o manifesto é marcado como contendo dados sintéticos, embora cada preço coletado seja registrado como não sintético.

Fontes: [BrasilAPI](https://brasilapi.com.br/docs), [AwesomeAPI](https://docs.awesomeapi.com.br/api-de-moedas).
