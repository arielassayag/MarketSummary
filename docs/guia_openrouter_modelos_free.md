# OpenRouter gratuito no MarketSummary

Siga a instalação e a configuração da chave no [README](../README.md).

Use `openrouter/free`. O nome dos modelos individuais pode mudar. O catálogo público em `https://openrouter.ai/api/v1/models` permite verificar IDs, preços e parâmetros disponíveis. O projeto filtra variantes gratuitas com preço zero e usa o roteador gratuito como opção quando não consegue consultar o catálogo.

**`openrouter/auto` não é garantia de gratuidade.** Não é utilizado neste tutorial.

```sh
uv run python -m fechamento run --scenario-dir data/real/minha_coleta --provider openrouter --model openrouter/free
```

A rota gratuita usa `provider.max_price` com `prompt: 0` e `completion: 0`. Um modelo `:free` indisponível pode ser substituído por `openrouter/free`, nunca por uma rota paga. Não se deve inventar o sufixo `:free` para um modelo que não tem essa variante no catálogo.

- 401: confira a chave e o arquivo `.env`.
- 402: confira as condições da conta; não compre créditos para seguir o tutorial gratuito.
- 404: modelo/provedor indisponível ou incompatível com os parâmetros.
- 429: cota ou capacidade esgotada; aguarde.
- 5xx ou timeout: falha temporária; tente mais tarde.
- JSON inválido ou falha na conferência: a execução não produz um rascunho aprovado. Revise o erro.

As respostas variam. Não há promessa de prazo nem sucesso para todas as contas. Não exponha chaves, carteiras privadas ou dados confidenciais.

Fontes oficiais: [roteador gratuito](https://openrouter.ai/docs/cookbook/get-started/free-models-router-playground), [limites](https://openrouter.ai/docs/api-reference/limits), [privacidade](https://openrouter.ai/docs/guides/privacy/data-collection), [limites de preço](https://openrouter.ai/docs/guides/routing/provider-selection#max-price).
