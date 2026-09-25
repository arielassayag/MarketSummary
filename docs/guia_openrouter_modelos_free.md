# Guia: Como Usar os Modelos Gratuitos Mais Potentes no OpenRouter (`:free`)

O **OpenRouter** (`https://openrouter.ai`) é um dos maiores agregadores de modelos de IA do mundo. Além dos modelos pagos, ele disponibiliza **modelos de ponta 100% gratuitos** identificados pelo sufixo `:free`.

---

## 1. Top Modelos Gratuitos Mais Potentes no OpenRouter

| Modelo | ID no OpenRouter | Fornecedor | Destaque Principal | Custo |
| :--- | :--- | :--- | :--- | :---: |
| **Llama 3.3 70B Instruct** | `meta-llama/llama-3.3-70b-instruct:free` | Meta | Desempenho equivalente aos modelos fechados de ponta em redação institucional e análise de mercado. | **$0.00** |
| **Gemini 2.0 Flash Exp** | `google/gemini-2.0-flash-exp:free` | Google | Altíssima velocidade, excelente aderência a JSON schemas e disciplina factual. | **$0.00** |
| **Qwen 2.5 72B Instruct** | `qwen/qwen-2.5-72b-instruct:free` | Alibaba Cloud | Líder em benchmarks matemáticos, lógica e formatação estruturada. | **$0.00** |
| **DeepSeek R1** | `deepseek/deepseek-r1:free` | DeepSeek | Modelo de raciocínio profundo (*reasoning model*) com cadeia de pensamento analítica. | **$0.00** |
| **Auto Router** | `openrouter/auto` | OpenRouter | Roteia dinamicamente para o melhor modelo disponível no momento. | **$0.00** |

---

## 2. Como Obter Sua Chave Gratuita no OpenRouter

1. Acesse [openrouter.ai](https://openrouter.ai) e faça login com sua conta do GitHub ou Google.
2. Não é necessário cadastrar cartão de crédito para usar os modelos `:free`.
3. Acesse **Keys** no menu superior e clique em **Create Key**.
4. Copie a chave gerada (ela começa com `sk-or-v1-...`).
5. Cole no arquivo `.env` do seu projeto:
   ```bash
   OPENROUTER_API_KEY="sk-or-v1-sua-chave-aqui"
   ```

---

## 3. Como Listar Automaticamente Todos os Modelos Gratuitos em Python

O OpenRouter oferece um catálogo público via API para consultar os modelos ativos:

```python
import urllib.request
import json

url = "https://openrouter.ai/api/v1/models"
with urllib.request.urlopen(url) as response:
    models = json.loads(response.read().decode("utf-8"))["data"]
    
    # Filtrar modelos gratuitos (pricing zerado ou id terminando em :free)
    free_models = [
        m for m in models 
        if m["id"].endswith(":free") or (
            float(m.get("pricing", {}).get("prompt", 1.0)) == 0.0 and
            float(m.get("pricing", {}).get("completion", 1.0)) == 0.0
        )
    ]
    
    print(f"Total de modelos 100% gratuitos encontrados: {len(free_models)}")
    for m in free_models[:10]:
        print(f" - {m['id']} ({m.get('name', '')})")
```

---

## 4. Uso no Projeto Fechamento

Na aplicação **Fechamento — AI Notes #8**, os modelos `:free` são suportados nativamente:

- **Pela Interface Web (Streamlit):**
  Na aba **2. Executar**, selecione `OpenRouterProvider` e escolha `meta-llama/llama-3.3-70b-instruct:free`. O sistema garantirá que a chamada não consuma créditos e exibirá o custo de `$0.00`.
  
- **Pelo Terminal (CLI):**
  ```bash
  uv run python -m fechamento run \
    --scenario-dir data/real/2026-02-11 \
    --provider openrouter \
    --model meta-llama/llama-3.3-70b-instruct:free
  ```
