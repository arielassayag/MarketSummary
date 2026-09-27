"""Provedor de narrativa via API oficial do OpenRouter.

Conecta-se ao gateway https://openrouter.ai/api/v1/chat/completions, permitindo
utilizar múltiplos modelos de fronteira com schema JSON estrito, placeholders
{{fact:id}} e {{news:id}}, e rastreamento de custos e tokens em tempo real.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from ..contracts import (
    ClaimType,
    CommentaryDraft,
    CommentaryParagraph,
)
from .base import NarrativeProvider, NarrativeRequest, NarrativeResult

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def get_recommended_free_models() -> list[dict[str, str]]:
    """Retorna os modelos gratuitos mais potentes e ativos disponíveis no OpenRouter (cost = $0.00)."""
    defaults = [{
        "id": "openrouter/free",
        "name": "OpenRouter Free Router",
        "description": "Roteamento entre modelos gratuitos, sujeito a cotas e disponibilidade.",
    }]

    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            live_models = data.get("data", [])
            live_free = [
                {"id": m["id"], "name": f"{m.get('name', m['id'])} (Free)", "description": m.get("description", "Modelo gratuito")}
                for m in live_models
                if (m["id"].endswith(":free") or m["id"] == "openrouter/free")
                and float(m.get("pricing", {}).get("prompt", 1)) == 0
                and float(m.get("pricing", {}).get("completion", 1)) == 0
            ]
            if live_free:
                # Garante openrouter/free no topo
                ordered = [m for m in live_free if m["id"] == "openrouter/free"]
                ordered += [m for m in live_free if m["id"] != "openrouter/free"]
                return ordered[:10]
    except Exception:
        pass

    return defaults


class OpenRouterProvider(NarrativeProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "openrouter/free",
        site_url: str = "https://github.com/arielassayag/MarketSummary",
        app_name: str = "AI Notes Fechamento",
        timeout_seconds: float = 60.0,
    ) -> None:
        # Carrega .env se existir na raiz ou em market-close-eval
        load_dotenv()
        if api_key is None:
            env_path = Path(".env")
            if not env_path.exists():
                env_eval = Path("market-close-eval/.env")
                if env_eval.exists():
                    load_dotenv(env_eval)
            self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        else:
            self.api_key = api_key

        self.model_name = model_name
        self.site_url = site_url
        self.app_name = app_name
        self.timeout_seconds = timeout_seconds

    def generate(self, request: NarrativeRequest) -> NarrativeResult:
        if not self.api_key or not self.api_key.strip():
            return NarrativeResult(
                provider_name="OpenRouterProvider",
                model_name=self.model_name,
                is_deterministic=False,
                error_message="Chave OPENROUTER_API_KEY não configurada. Defina no .env ou forneça na interface.",
            )

        start_time = time.perf_counter()

        system_prompt = (
            "Você é um redator financeiro institucional para fechamento de mercado da B3.\n"
            "REGRAS INVIOLÁVEIS:\n"
            "1. NÃO invente, calcule ou estime NENHUM número financeiro.\n"
            "2. Todos os valores numéricos de mercado DEVEM obrigatoriamente usar placeholders {{fact:fact_id}}.\n"
            "3. NUNCA escreva porcentagens ou valores financeiros diretamente no texto (ex: NUNCA escreva '13,75%'). Se quiser citar taxas, use {{fact:macro.selic.rate}} ou {{fact:macro.cdi.rate}}.\n"
            "4. Todas as citações a notícias DEVEM usar placeholders {{news:news_id}}. NUNCA copie porcentagens das notícias para o texto.\n"
            "5. A palavra 'contribuição' só pode ser usada com fatos de contribution_bps.\n"
            "6. A cotação USD/BRL é em reais por dólar. Variação positiva é alta do dólar / desvalorização do real.\n"
            "7. Uma notícia no mesmo dia NÃO comprova causalidade por si só. Classifique parágrafos com inferências como 'interpretation'.\n"
            "8. Tamanho esperado: aproximadamente 180 a 300 palavras em português do Brasil.\n"
            "9. Responda ESTRITAMENTE em formato JSON com o seguinte schema:\n"
            "{\n"
            '  "paragraphs": [\n'
            "    {\n"
            '      "paragraph_id": 1,\n'
            '      "text": "Texto com {{fact:...}} e {{news:...}}",\n'
            '      "claim_type": "factual" ou "interpretation",\n'
            '      "fact_refs": ["fact_id_1", ...],\n'
            '      "news_refs": ["news_id_1", ...]\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        facts_summary = [
            f"- {f.fact_id}: {f.name} = {f.formatted_value} (fórmula: {f.formula})"
            for f in request.factbook.facts.values()
        ]

        news_summary = [
            f"- [{n.news_id}] (Publicado: {n.published_at.isoformat()}): {n.title} -- {n.body}"
            for n in request.eligible_news
        ]

        user_content = (
            f"DATA DE REFERÊNCIA: {request.factbook.reference_date.isoformat()}\n"
            f"LIMITAÇÕES DOS DADOS: {request.factbook.data_notice}\n"
            "Não afirme encerramento de pregão nem causalidade sem comprovação.\n\n"
            f"CATÁLOGO DE FATOS DISPONÍVEIS (FactBook):\n" + "\n".join(facts_summary) + "\n\n"
            "NOTÍCIAS ELEGÍVEIS (pré-corte):\n" + ("\n".join(news_summary) if news_summary else "Nenhuma notícia no período.") + "\n\n"
            f"INSTRUÇÕES DE ESTILO:\n{request.style_instructions}\n\n"
            "Gere o rascunho com 3 parágrafos: (1) Visão Geral do Mercado e Carteira; (2) Principais Contribuidores Positivos; (3) Principais Detratores e Disciplina Factual."
        )

        try:
            raw_text, token_usage, cost_usd = self._call_openrouter(system_prompt, user_content)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return NarrativeResult(
                provider_name="OpenRouterProvider",
                model_name=self.model_name,
                is_deterministic=False,
                latency_ms=elapsed_ms,
                error_message=f"Falha na comunicação com o OpenRouter: {e}",
            )

        draft, parse_error = self._parse_response(raw_text)
        if parse_error and not draft:
            # 1 retentativa de correção
            try:
                retry_prompt = f"O JSON anterior continha erros de sintaxe ou schema: {parse_error}. Retorne apenas o JSON estrito:\n{raw_text}"
                raw_text, token_usage_retry, cost_retry = self._call_openrouter(system_prompt, retry_prompt)
                draft, parse_error = self._parse_response(raw_text)
                if token_usage and token_usage_retry:
                    for k in token_usage:
                        token_usage[k] += token_usage_retry.get(k, 0)
                if cost_usd is not None and cost_retry is not None:
                    cost_usd += cost_retry
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return NarrativeResult(
                    provider_name="OpenRouterProvider",
                    model_name=self.model_name,
                    is_deterministic=False,
                    latency_ms=elapsed_ms,
                    error_message=f"Erro na retentativa de formatação do OpenRouter: {e}",
                )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if not draft:
            return NarrativeResult(
                provider_name="OpenRouterProvider",
                model_name=self.model_name,
                is_deterministic=False,
                raw_response=raw_text,
                latency_ms=elapsed_ms,
                token_usage=token_usage,
                cost_usd=cost_usd,
                error_message=f"Não foi possível obter JSON válido no schema: {parse_error}",
            )

        return NarrativeResult(
            draft=draft,
            raw_response=raw_text,
            latency_ms=elapsed_ms,
            token_usage=token_usage,
            cost_usd=cost_usd,
            provider_name="OpenRouterProvider",
            model_name=self.model_name,
            is_deterministic=False,
        )

    def _call_openrouter(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[str, dict[str, int], float | None]:
        models_to_try = [self.model_name]
        free_route = self.model_name.endswith(":free") or self.model_name == "openrouter/free"
        if free_route:
            for fallback in ["openrouter/free"]:
                if fallback not in models_to_try:
                    models_to_try.append(fallback)

        last_error: Exception | None = None

        for model_cand in models_to_try:
            payload = {
                "model": model_cand,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            }

            if free_route:
                payload["provider"] = {"max_price": {"prompt": 0, "completion": 0}}

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.site_url,
                "X-Title": self.app_name,
            }

            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                OPENROUTER_API_URL,
                data=data_bytes,
                headers=headers,
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    body = resp.read().decode("utf-8")
                    res_json = json.loads(body)

                choices = res_json.get("choices", [])
                if not choices:
                    err_info = res_json.get("error", {})
                    raise ValueError(f"OpenRouter ({model_cand}): {err_info.get('message', body)}")

                raw_text = choices[0].get("message", {}).get("content", "")
                if not isinstance(raw_text, str) or not raw_text.strip():
                    raise ValueError("OpenRouter retornou resposta vazia; tente novamente mais tarde.")
                self.model_name = model_cand

                usage = res_json.get("usage", {})
                token_usage = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
                cost_usd = usage.get("cost")
                if cost_usd is not None:
                    cost_usd = float(cost_usd)

                return raw_text, token_usage, cost_usd

            except Exception as e:
                last_error = e
                err_msg = str(e).lower()
                if any(code in err_msg for code in ("404", "502", "503", "429", "overloaded")):
                    time.sleep(1)
                    continue
                raise e

        if last_error:
            raise last_error
        raise RuntimeError("Nenhum modelo do OpenRouter retornou resposta válida.")

    def _parse_response(self, raw_text: str) -> tuple[CommentaryDraft | None, str | None]:
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)
            paragraphs_data = data.get("paragraphs", [])
            if not paragraphs_data:
                return None, "Campo 'paragraphs' ausente ou vazio no JSON."

            paragraphs: list[CommentaryParagraph] = []
            for p in paragraphs_data:
                text_val = str(p.get("text", ""))
                # Extrai automaticamente placeholders do texto caso o LLM não tenha preenchido o array
                text_facts = [m.group(1) for m in re.finditer(r"\{\{fact:([^}]+)\}\}", text_val)]
                text_news = [m.group(1) for m in re.finditer(r"\{\{news:([^}]+)\}\}", text_val)]
                declared_facts = [str(x) for x in p.get("fact_refs", [])]
                declared_news = [str(x) for x in p.get("news_refs", [])]
                combined_facts = list(dict.fromkeys(declared_facts + text_facts))
                combined_news = list(dict.fromkeys(declared_news + text_news))

                paragraph = CommentaryParagraph(
                    paragraph_id=int(p.get("paragraph_id", len(paragraphs) + 1)),
                    text=text_val,
                    claim_type=ClaimType(p.get("claim_type", "factual")),
                    fact_refs=combined_facts,
                    news_refs=combined_news,
                )
                paragraphs.append(paragraph)

            draft = CommentaryDraft(
                draft_id=f"openrouter_draft_{uuid4().hex[:8]}",
                paragraphs=paragraphs,
                provider_id="OpenRouterProvider",
                model_id=self.model_name,
                created_at=datetime.now(UTC),
                is_synthetic=False,
            )
            return draft, None

        except Exception as e:
            return None, str(e)
