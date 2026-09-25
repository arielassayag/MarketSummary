# Guia de Coleta de Dados de Mercado 100% Reais e Gratuitos — BrasilAPI e APIs Abertas

Este guia ensina como obter dados de mercado brasileiros em tempo real, de forma 100% gratuita, sem necessidade de chaves de API pagas ou cadastros burocráticos.

---

## 1. BrasilAPI — Taxas Oficiais (Selic, CDI e IPCA)

A **BrasilAPI** (`https://brasilapi.com.br`) é uma iniciativa aberta comunitária que centraliza dados públicos brasileiros de fontes oficiais como Banco Central, B3 e IBGE.

### Endpoint de Taxas Financeiras:
```http
GET https://brasilapi.com.br/api/taxas/v1
```

### Exemplo em Python:
```python
import urllib.request
import json

url = "https://brasilapi.com.br/api/taxas/v1"
req = urllib.request.Request(url, headers={"User-Agent": "MarketReader/1.0"})

with urllib.request.urlopen(req) as response:
    taxas = json.loads(response.read().decode("utf-8"))
    for item in taxas:
        print(f"Taxa: {item['nome']} | Valor: {item['valor']}%")
```

### Resposta Típica:
```json
[
  {"nome": "Selic", "valor": 13.75},
  {"nome": "CDI", "valor": 13.65},
  {"nome": "IPCA", "valor": 4.22}
]
```

---

## 2. AwesomeAPI — Câmbio USD/BRL em Tempo Real

A **AwesomeAPI** (`https://economia.awesomeapi.com.br`) oferece cotações em tempo real de moedas contra o Real brasileiro, sem necessidade de autenticação.

### Endpoint de Cotações:
```http
GET https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL
```

### Exemplo em Python:
```python
import urllib.request
import json

url = "https://economia.awesomeapi.com.br/last/USD-BRL"
req = urllib.request.Request(url, headers={"User-Agent": "MarketReader/1.0"})

with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode("utf-8"))["USDBRL"]
    print(f"Dólar Compra (bid): R$ {data['bid']}")
    print(f"Dólar Venda (ask): R$ {data['ask']}")
    print(f"Variação Diária: {data['pctChange']}%")
    print(f"Máxima: R$ {data['high']} | Mínima: R$ {data['low']}")
```

---

## 3. Cotações B3 e Ibovespa via Endpoints Públicos

Para ações da B3 e o índice Ibovespa (`^BVSP`), podemos consultar os endpoints públicos de séries históricas e intradiárias:

```python
import urllib.request
import json

def fetch_b3_quote(ticker: str):
    # Ex: ^BVSP para Ibovespa, PETR4.SA para Petrobras
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))
        meta = data["chart"]["result"][0]["meta"]
        return {
            "current_price": meta["regularMarketPrice"],
            "previous_price": meta["previousClose"]
        }

ibov = fetch_b3_quote("^BVSP")
petr = fetch_b3_quote("PETR4.SA")
print(f"Ibovespa Atual: {ibov['current_price']} pts | Anterior: {ibov['previous_price']} pts")
print(f"PETR4 Atual: R$ {petr['current_price']} | Anterior: R$ {petr['previous_price']}")
```

---

## 4. Integração no Projeto Fechamento

O módulo [`src/fechamento/live_fetcher.py`](file:///Users/arielassayag/codigos/MarketSummary/src/fechamento/live_fetcher.py) consolida essas três fontes em um único comando:
```python
from fechamento.live_fetcher import build_live_market_package

# Cria pacote completo com quotes.csv, positions.csv, news.jsonl e manifest.json
pacote_dir = build_live_market_package(output_dir="data/real/live_hoje", timeframe="1d")
```
Isso alimenta diretamente o pipeline determinístico sem intervenção manual.
