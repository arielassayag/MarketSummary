"""Provedor de narrativa via API oficial do Google Gemini (opcional).

Exige chave de API autorizada e habilitação explícita. O modelo recebe apenas
o FactBook, notícias elegíveis e instruções de estilo, respondendo em JSON
estruturado validado por schema com placeholders {{fact:id}} e {{news:id}}.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from ..contracts import (
    ClaimType,
    CommentaryDraft,
    CommentaryParagraph,
)
from .base import NarrativeProvider, NarrativeRequest, NarrativeResult

GEMINI_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "paragraphs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "paragraph_id": {"type": "integer"},
                    "text": {
                        "type": "string",
                        "description": "Texto em português brasileiro contendo placeholders {{fact:id}} para todos os números financeiros e {{news:id}} para notícias."
                    },
                    "claim_type": {
                        "type": "string",
                        "enum": ["factual", "interpretation"]
                    },
                    "fact_refs": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "news_refs": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["paragraph_id", "text", "claim_type", "fact_refs", "news_refs"]
            }
        }
    },
    "required": ["paragraphs"]
}


class GeminiProvider(NarrativeProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
        enabled: bool = False,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds

    def generate(self, request: NarrativeRequest) -> NarrativeResult:
        if not self.enabled:
            return NarrativeResult(
                provider_name="GeminiProvider",
                model_name=self.model_name,
                is_deterministic=False,
                error_message="Provedor Gemini desabilitado na configuração. Ative explicitamente para chamadas externas.",
            )

        if not self.api_key or not self.api_key.strip():
            return NarrativeResult(
                provider_name="GeminiProvider",
                model_name=self.model_name,
                is_deterministic=False,
                error_message="Chave GEMINI_API_KEY não fornecida. Configure a credencial para utilizar este modo.",
            )

        start_time = time.perf_counter()

        # Preparação do prompt com fronteira rígida
        system_prompt = (
            "Você é um redator financeiro institucional para fechamento de mercado da B3.\n"
            "REGRAS INVIOLÁVEIS:\n"
            "1. NÃO invente, calcule ou estime NENHUM número financeiro.\n"
            "2. Todos os valores numéricos de mercado DEVEM obrigatoriamente usar placeholders {{fact:fact_id}}.\n"
            "3. Todas as citações a notícias DEVEM usar placeholders {{news:news_id}}.\n"
            "4. A palavra 'contribuição' só pode ser usada com fatos de contribution_bps.\n"
            "5. A cotação USD/BRL é em reais por dólar. Variação positiva é alta do dólar / desvalorização do real.\n"
            "6. Uma notícia no mesmo dia NÃO comprova causalidade por si só. Classifique parágrafos com inferências como 'interpretation'.\n"
            "7. Tamanho esperado: aproximadamente 180 a 300 palavras em português do Brasil.\n"
            "8. Responda ESTRITAMENTE em formato JSON conforme o schema exigido."
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
            f"DATA DO PREGÃO: {request.factbook.reference_date.isoformat()}\n\n"
            f"CATÁLOGO DE FATOS DISPONÍVEIS (FactBook):\n" + "\n".join(facts_summary) + "\n\n"
            "NOTÍCIAS ELEGÍVEIS (pré-corte):\n" + ("\n".join(news_summary) if news_summary else "Nenhuma notícia no período.") + "\n\n"
            f"INSTRUÇÕES DE ESTILO:\n{request.style_instructions}\n\n"
            "Gere o rascunho com 3 parágrafos: (1) Visão Geral do Mercado e Carteira; (2) Principais Contribuidores Positivos; (3) Principais Detratores e Disciplina Factual."
        )

        # Tentativa de chamada via SDK oficial ou fallback HTTP REST oficial
        try:
            raw_text, token_usage = self._call_api(system_prompt, user_content)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return NarrativeResult(
                provider_name="GeminiProvider",
                model_name=self.model_name,
                is_deterministic=False,
                latency_ms=elapsed_ms,
                error_message=f"Falha na comunicação com a API do Gemini: {e}",
            )

        # Parse e validação do JSON retornado (com no máximo 1 tentativa de correção de formato)
        draft, parse_error = self._parse_response(raw_text)
        if parse_error and not draft:
            # 1 retentativa estrita de correção de formato
            try:
                retry_prompt = f"O JSON anterior continha erros de sintaxe ou schema: {parse_error}. Corrija e retorne apenas o JSON estrito:\n{raw_text}"
                raw_text, token_usage_retry = self._call_api(system_prompt, retry_prompt)
                draft, parse_error = self._parse_response(raw_text)
                if token_usage and token_usage_retry:
                    for k in token_usage:
                        token_usage[k] += token_usage_retry.get(k, 0)
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return NarrativeResult(
                    provider_name="GeminiProvider",
                    model_name=self.model_name,
                    is_deterministic=False,
                    latency_ms=elapsed_ms,
                    error_message=f"Erro na retentativa de formatação do Gemini: {e}",
                )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if not draft:
            return NarrativeResult(
                provider_name="GeminiProvider",
                model_name=self.model_name,
                is_deterministic=False,
                raw_response=raw_text,
                latency_ms=elapsed_ms,
                token_usage=token_usage,
                error_message=f"Não foi possível obter JSON válido no schema exigido: {parse_error}",
            )

        return NarrativeResult(
            draft=draft,
            raw_response=raw_text,
            latency_ms=elapsed_ms,
            token_usage=token_usage,
            cost_usd=None,
            provider_name="GeminiProvider",
            model_name=self.model_name,
            is_deterministic=False,
        )

    def _call_api(self, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, int]]:
        """Executa a requisição oficial para o Gemini."""
        import urllib.error
        import urllib.request

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            res_json = json.loads(body)

        candidates = res_json.get("candidates", [])
        if not candidates:
            raise ValueError(f"Nenhum candidato retornado pelo modelo: {body}")

        candidate = candidates[0]
        content_parts = candidate.get("content", {}).get("parts", [])
        raw_text = content_parts[0].get("text", "") if content_parts else ""

        usage = res_json.get("usageMetadata", {})
        token_usage = {
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0),
        }

        return raw_text, token_usage

    def _parse_response(self, raw_text: str) -> tuple[CommentaryDraft | None, str | None]:
        """Faz o parse seguro do JSON retornado e converte para CommentaryDraft."""
        try:
            # Remove eventuais delimitadores markdown caso o modelo os tenha incluído
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
                paragraph = CommentaryParagraph(
                    paragraph_id=int(p["paragraph_id"]),
                    text=str(p["text"]),
                    claim_type=ClaimType(p.get("claim_type", "factual")),
                    fact_refs=[str(x) for x in p.get("fact_refs", [])],
                    news_refs=[str(x) for x in p.get("news_refs", [])],
                )
                paragraphs.append(paragraph)

            draft = CommentaryDraft(
                draft_id=f"gemini_draft_{uuid4().hex[:8]}",
                paragraphs=paragraphs,
                provider_id="GeminiProvider",
                model_id=self.model_name,
                created_at=datetime.now(UTC),
                is_synthetic=True,
            )
            return draft, None

        except Exception as e:
            return None, str(e)
