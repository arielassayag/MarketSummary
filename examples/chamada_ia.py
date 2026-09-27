"""Exemplo didático: números fictícios, modelo gratuito e chave lida do .env."""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
chave = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not chave:
    raise SystemExit("Configure OPENROUTER_API_KEY no arquivo .env antes de executar.")

# NÚMEROS FICTÍCIOS: servem apenas para entender a chamada à API.
fatos_do_dia = "Ibovespa: +1,25% | Dólar: R$ 5,1836 (-0,36%) | PETR4: +1,83%"
envelope = {
    "model": "openrouter/free",
    "provider": {"max_price": {"prompt": 0, "completion": 0}},
    "messages": [
        {"role": "system", "content": "Redija em português. Identifique os dados como fictícios. Use apenas os números fornecidos e não invente explicações para os movimentos. Retorne somente os dois parágrafos finais, sem comentários sobre como escrever a resposta."},
        {"role": "user", "content": f"Escreva dois parágrafos curtos com estes dados fictícios: {fatos_do_dia}"},
    ],
    "temperature": 0.2,
    "max_tokens": 4096,
    "reasoning": {"effort": "low", "exclude": True},
}
requisicao = urllib.request.Request(
    "https://openrouter.ai/api/v1/chat/completions",
    data=json.dumps(envelope).encode("utf-8"),
    headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        resultado = json.loads(resposta.read().decode("utf-8"))
    escolha = resultado["choices"][0]
    if escolha.get("finish_reason") == "length":
        raise ValueError("Resposta incompleta por limite de tokens; tente novamente")
    texto = escolha["message"]["content"]
    if not texto:
        raise ValueError("Resposta vazia")
    print("DADOS FICTÍCIOS — EXEMPLO DIDÁTICO\n")
    print(texto)
except urllib.error.HTTPError as erro:
    raise SystemExit(f"OpenRouter retornou HTTP {erro.code}. Confira a chave, os limites gratuitos e a disponibilidade. Não houve troca para modelo pago.") from None
except (OSError, ValueError, KeyError, IndexError) as erro:
    raise SystemExit(f"Não foi possível obter o texto: {erro}. Tente novamente mais tarde.") from None
