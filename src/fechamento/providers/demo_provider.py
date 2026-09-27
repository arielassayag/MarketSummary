"""Provedor determinístico de demonstração (DemoProvider).

Gera o comentário de fechamento estruturado 100% offline via regras lógicas,
utilizando os fatos do FactBook e as notícias elegíveis, com placeholders
{{fact:id}} e {{news:id}}.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import uuid4

from ..contracts import (
    ClaimType,
    CommentaryDraft,
    CommentaryParagraph,
)
from .base import NarrativeProvider, NarrativeRequest, NarrativeResult


class DemoProvider(NarrativeProvider):
    """Provedor determinístico e offline. Não realiza chamadas a LLM."""

    def generate(self, request: NarrativeRequest) -> NarrativeResult:
        start_time = time.perf_counter()
        fb = request.factbook

        # Identificar fatos chave
        ibov_fact = fb.get_fact("ibov.return_pct")
        usd_change_fact = fb.get_fact("usd_brl.change_pct")
        usd_level_fact = fb.get_fact("usd_brl.level")
        port_ret_fact = fb.get_fact("portfolio.return_pct")

        if not ibov_fact or not port_ret_fact:
            return NarrativeResult(
                provider_name="DemoProvider",
                is_deterministic=True,
                error_message="Fatos essenciais (IBOV ou Carteira) ausentes no FactBook.",
            )

        # Buscar principais contribuidores positivos e negativos
        pos_facts = [
            f for f_id, f in fb.facts.items()
            if f_id.startswith("asset.") and f_id.endswith(".contribution_bps") and f.value > 0
        ]
        pos_facts.sort(key=lambda x: x.value, reverse=True)

        neg_facts = [
            f for f_id, f in fb.facts.items()
            if f_id.startswith("asset.") and f_id.endswith(".contribution_bps") and f.value < 0
        ]
        neg_facts.sort(key=lambda x: x.value)

        # Mapear notícias elegíveis por ticker
        news_by_ticker: dict[str, list[str]] = {}
        for n in request.eligible_news:
            for t in n.related_tickers:
                news_by_ticker.setdefault(t, []).append(n.news_id)

        paragraphs: list[CommentaryParagraph] = []

        # Parágrafo 1: Visão Geral do Mercado e Carteira (Factual)
        p1_facts = ["ibov.return_pct", "portfolio.return_pct", "portfolio.spread_vs_ibov_bps"]
        p1_text = (
            "No retrato de mercado do pacote, o Ibovespa apresentou variação de {{fact:ibov.return_pct}}, "
            "enquanto a carteira de referência registrou retorno de {{fact:portfolio.return_pct}}, "
            "resultando em um desempenho relativo de {{fact:portfolio.spread_vs_ibov_bps}} frente ao benchmark. "
        )

        if usd_change_fact and usd_level_fact:
            p1_facts.extend(["usd_brl.change_pct", "usd_brl.level"])
            p1_text += (
                "No mercado de câmbio, o dólar comercial apresentou oscilação de {{fact:usd_brl.change_pct}}, "
                "cotado a R$ {{fact:usd_brl.level}} por dólar no horário informado pela fonte. "
            )

        p1_text += (
            "Os resultados descrevem as variações dos preços no pacote e não identificam suas causas. "
            "A comparação requer conferir datas, fontes e critérios de ajuste antes de interpretar o desempenho."
        )

        if fb.is_synthetic:
            p1_text = "PACOTE DIDÁTICO — CONTÉM DADOS OU CARTEIRA SIMULADOS. " + p1_text

        paragraphs.append(CommentaryParagraph(
            paragraph_id=1,
            text=p1_text,
            claim_type=ClaimType.FACTUAL,
            fact_refs=p1_facts,
            news_refs=[],
        ))

        # Parágrafo 2: Contribuidores Positivos e Setores (Interpretação amparada)
        p2_facts: list[str] = []
        p2_news: list[str] = []
        p2_text = "Entre os destaques positivos da carteira, "

        if pos_facts:
            top_pos = pos_facts[0]
            ticker_pos = top_pos.fact_id.split(".")[1]
            ret_pos_id = f"asset.{ticker_pos}.return_pct"
            contrib_pos_id = top_pos.fact_id
            p2_facts.extend([ret_pos_id, contrib_pos_id])

            p2_text += (
                f"o principal impacto favorável adveio de {ticker_pos}, que avançou "
                f"{{{{fact:{ret_pos_id}}}}} e acrescentou {{{{fact:{contrib_pos_id}}}}} à rentabilidade total do portfólio. "
            )

            # Verificar se há notícia elegível vinculada
            if ticker_pos in news_by_ticker and news_by_ticker[ticker_pos]:
                n_id = news_by_ticker[ticker_pos][0]
                p2_news.append(n_id)
                p2_text += (
                    f"Há uma manchete associada ao ativo ({{{{news:{n_id}}}}}). "
                    "Essa associação não comprova que a notícia tenha causado o movimento do preço. "
                )

            if len(pos_facts) > 1:
                sec_pos = pos_facts[1]
                t_sec = sec_pos.fact_id.split(".")[1]
                r_sec = f"asset.{t_sec}.return_pct"
                c_sec = sec_pos.fact_id
                p2_facts.extend([r_sec, c_sec])
                p2_text += (
                    f"Adicionalmente, {t_sec} registrou alta de {{{{fact:{r_sec}}}}}, "
                    f"contribuindo com {{{{fact:{c_sec}}}}} para o resultado. "
                )

            p2_text += (
                "O ranking considera os pesos iniciais da carteira e os retornos calculados em código. "
                "Ele descreve o impacto de cada posição no resultado, sem atribuir motivos ao movimento."
            )
        else:
            p2_text += "nenhum ativo individual apresentou contribuição positiva relevante na sessão de hoje."

        paragraphs.append(CommentaryParagraph(
            paragraph_id=2,
            text=p2_text,
            claim_type=ClaimType.INTERPRETATION if p2_news else ClaimType.FACTUAL,
            fact_refs=p2_facts,
            news_refs=p2_news,
        ))

        # Parágrafo 3: Detratores e Disciplina de Evidência
        p3_facts: list[str] = []
        p3_news: list[str] = []
        p3_text = "Em contrapartida, no campo dos detratores de desempenho, "

        if neg_facts:
            top_neg = neg_facts[0]
            ticker_neg = top_neg.fact_id.split(".")[1]
            ret_neg_id = f"asset.{ticker_neg}.return_pct"
            contrib_neg_id = top_neg.fact_id
            p3_facts.extend([ret_neg_id, contrib_neg_id])

            p3_text += (
                f"a maior pressão baixista partiu de {ticker_neg}, cujas ações recuaram "
                f"{{{{fact:{ret_neg_id}}}}}, subtraindo {{{{fact:{contrib_neg_id}}}}} da carteira. "
            )

            if ticker_neg in news_by_ticker and news_by_ticker[ticker_neg]:
                n_id_neg = news_by_ticker[ticker_neg][0]
                p3_news.append(n_id_neg)
                p3_text += (
                    f"O pacote contém uma manchete associada ao ativo ({{{{news:{n_id_neg}}}}}). "
                    "Sua relevância para a variação observada depende de revisão humana. "
                )

            if len(neg_facts) > 1:
                sec_neg = neg_facts[1]
                t_sec_n = sec_neg.fact_id.split(".")[1]
                r_sec_n = f"asset.{t_sec_n}.return_pct"
                c_sec_n = sec_neg.fact_id
                p3_facts.extend([r_sec_n, c_sec_n])
                p3_text += (
                    f"O papel {t_sec_n} também encerrou no campo negativo com variação de {{{{fact:{r_sec_n}}}}} "
                    f"({{{{fact:{c_sec_n}}}}}). "
                )

            p3_text += (
                "Quando faltam evidências para explicar um movimento, sua causa permanece indeterminada. "
                "A leitura de manchetes, por si só, não confirma mudanças nos fundamentos nem permite atribuir causalidade."
            )
        else:
            p3_text += "nenhum ativo apresentou detração expressiva no período analisado."

        paragraphs.append(CommentaryParagraph(
            paragraph_id=3,
            text=p3_text,
            claim_type=ClaimType.INTERPRETATION if p3_news else ClaimType.FACTUAL,
            fact_refs=p3_facts,
            news_refs=p3_news,
        ))

        draft = CommentaryDraft(
            draft_id=f"draft_{uuid4().hex[:8]}",
            paragraphs=paragraphs,
            provider_id="DemoProvider",
            model_id="deterministic-rules-v1",
            created_at=datetime.now(UTC),
            is_synthetic=True,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return NarrativeResult(
            draft=draft,
            raw_response=draft.model_dump_json(indent=2),
            latency_ms=elapsed_ms,
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            cost_usd=None,
            provider_name="DemoProvider",
            model_name="deterministic-rules-v1",
            is_deterministic=True,
        )
