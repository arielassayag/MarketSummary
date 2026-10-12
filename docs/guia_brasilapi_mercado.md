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
| Manchetes | GDELT DOC 2.0; Google News RSS como contingência | Preserva horário retornado e link; não verifica publicação original ou veracidade |
| Pesos de carteira | Código de exemplo | Simulados, iguais, explicitamente identificados |

O retorno de cada ação usa a última cotação e o fechamento da sessão anterior na série. `chartPreviousClose` pode ser o fechamento anterior ao início do intervalo de cinco dias, por isso não serve automaticamente de referência diária. Não há ajuste de proventos/splits.

`quotes.csv` guarda o timestamp da fonte. `manifest.json` guarda a sessão, o corte da coleta e hashes; `sources.json` guarda as URLs e limitações. Em fins de semana a data da cotação continua sendo a da sessão disponível. As notícias usam uma janela recente e podem ser posteriores a essa sessão.

Falhas em cotações obrigatórias interrompem a coleta. Taxas e notícias ausentes são registradas; nunca são substituídas por valores ou textos inventados. Sessões incompatíveis, timestamp futuro e atraso superior a sete dias bloqueiam a coleta. Mesmo dentro desse limite, confira a atualidade dos dados antes de usar o rascunho.

Só `1d` é aceito. Não há implementação semanal/mensal. Como há carteira simulada, o manifesto é marcado como contendo dados sintéticos, embora cada preço coletado seja registrado como não sintético.

O corpo JSON das taxas e a hora da consulta ficam em `sources.json`, conferido pelo SHA do manifesto. Esse retrato não é uma notícia nem confirma publicação ou vigência. O FactBook usa apenas os campos estruturados desse contexto; uma manchete citando Selic/CDI não cria uma taxa. Se um campo ou o contexto estiver ausente, o fato também permanece ausente.

Fontes: [BrasilAPI](https://brasilapi.com.br/docs), [AwesomeAPI](https://docs.awesomeapi.com.br/api-de-moedas).

## Notícias da GDELT DOC 2.0 — Notícias de Mercado sem Chave

A API DOC 2.0 da **GDELT** pesquisa notícias e devolve uma lista estruturada em JSON. O projeto filtra publicações brasileiras em português e consulta termos ligados ao Ibovespa e às empresas da carteira.

```http
GET https://api.gdeltproject.org/api/v2/doc/doc?query=(Ibovespa%20OR%20Petrobras)%20sourcelang:portuguese%20sourcecountry:brazil&mode=ArtList&format=json&sort=DateDesc&timespan=24h&maxrecords=6
```

```python
import json
import urllib.parse
import urllib.request

params = {
    "query": "(Ibovespa OR Petrobras) sourcelang:portuguese sourcecountry:brazil",
    "mode": "ArtList",
    "format": "json",
    "sort": "DateDesc",
    "timespan": "24h",
    "maxrecords": 6,
}
url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)

with urllib.request.urlopen(url, timeout=10) as response:
    artigos = json.loads(response.read().decode("utf-8"))["articles"]
```

O módulo preserva o registro original, o título, a URL, o domínio e o horário retornado pela API. No GDELT, o campo `seendate` é arquivado literalmente: seu horário não é tratado como data confirmada de publicação do veículo. Sem fonte que confirme a publicação original, essa data fica ausente. O corte usa o horário disponível recebido, com fuso, e informa sua origem; sem qualquer horário válido, o registro é recusado. No RSS, `pubDate` mantém sua origem própria. Se a GDELT estiver temporariamente indisponível, a coleta tenta o Google News RSS. Se as duas fontes falharem, nenhuma manchete é inventada.

---
