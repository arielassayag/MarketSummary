"""Módulo de validação determinística de rascunhos e resolução de placeholders.

Garante que nenhum número financeiro seja alucinado ou inserido fora do FactBook,
substitui deterministicamente os placeholders {{fact:id}} e {{news:id}}, e aplica
regras de disciplina causal, contagem de palavras e vocabulário proibido.
"""

from __future__ import annotations

import re

from .contracts import (
    ClaimType,
    CommentaryDraft,
    CommentaryParagraph,
    FactBook,
    NewsItem,
    ValidationCheckResult,
)

# Regex para placeholders
FACT_PLACEHOLDER_REGEX = re.compile(r"\{\{fact:([^}]+)\}\}")
NEWS_PLACEHOLDER_REGEX = re.compile(r"\{\{news:([^}]+)\}\}")
GENERIC_PLACEHOLDER_REGEX = re.compile(r"\{\{[^}]+\}\}")

# Regex para números financeiros não autorizados fora de placeholders
# Ignora tickers (ex: PETR4, VALE3), datas (18/09/2026, 2026), horas (18h00) e ordinais (1º, 2ª)
FINANCIAL_NUMBER_REGEX = re.compile(
    r"(?<![A-Za-z])"  # Não precedido por letra (evita tickers como PETR4)
    r"(?:\bR\$\s*|\bUS\$\s*|\b\$\s*)?"  # Prefixo de moeda opcional
    r"\b\d+(?:[.,]\d+)?\b"  # Número
    r"(?:\s*(?:%|p\.p\.|bps|pontos-base|pontos|reais|dólares|centavos))?"  # Sufixo financeiro opcional
    r"(?![A-Za-z0-9_])"  # Não sucedido por identificador
)


def extract_plain_text_without_placeholders(text: str) -> str:
    """Remove os placeholders {{fact:...}}, {{news:...}} ou {{...}} do texto para inspecionar o restante."""
    cleaned = re.sub(r"\{\{[^}]+\}\}\s*(?:%|bps)?", " ", text)
    return cleaned


def find_unauthorized_numbers(text_with_placeholders: str) -> list[str]:
    """Detecta números financeiros inseridos no texto fora do mecanismo de placeholders.

    Trata explicitamente exceções legítimas:
    - Tickers de ações (PETR4, VALE3, MGLU3, etc.)
    - Anos e datas (2026, 18/09, 18h30)
    - Ordinais (1º, 2º, 3ª)
    - Números ordinais em enumerações de parágrafos
    """
    plain = extract_plain_text_without_placeholders(text_with_placeholders)

    # Lista de padrões permitidos a ignorar
    # 1. Tickers conhecidos ou padrão [A-Z]{4}\d
    plain = re.sub(r"\b[A-Z]{4}\d{1,2}\b", " ", plain)
    # 2. Datas: dd/mm/aaaa ou aaaa-mm-dd ou dd de mês ou dia de semana
    plain = re.sub(
        r"\b\d{1,2}\s+(?:de\s+)?(?:janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)(?:\s+de\s+\d{4})?\b",
        " ",
        plain,
        flags=re.IGNORECASE,
    )
    plain = re.sub(
        r"\b(?:segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)(?:-feira)?(?:,)?\s+(?:dia\s+)?\d{1,2}\b",
        " ",
        plain,
        flags=re.IGNORECASE,
    )
    plain = re.sub(r"\b(?:dia|dias)\s+\d{1,2}\b", " ", plain, flags=re.IGNORECASE)
    plain = re.sub(r"\b\d+\s+(?:dias|meses|horas|minutos|anos|semanas|segundos)\b", " ", plain, flags=re.IGNORECASE)
    plain = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", plain)
    plain = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", plain)
    plain = re.sub(r"\b\d{4}\b", " ", plain)  # Anos como 2026
    # 3. Horários: 18h, 17h15, 18:00
    plain = re.sub(r"\b\d{1,2}h(?:\d{2})?\b", " ", plain)
    plain = re.sub(r"\b\d{1,2}:\d{2}\b", " ", plain)
    # 4. Ordinais: 1º, 2ª, etc.
    plain = re.sub(r"\b\d+[ºª°]\b", " ", plain)
    # 5. Parágrafo / Seção: ex: "Parágrafo 1", "(1)"
    plain = re.sub(r"\b(?:parágrafo|item|etapa|passo)\s+\d+\b", " ", plain, flags=re.IGNORECASE)
    plain = re.sub(r"\(\d+\)", " ", plain)

    violations = []
    for match in FINANCIAL_NUMBER_REGEX.finditer(plain):
        token = match.group(0).strip()
        if not token:
            continue
        # Se for apenas um número puro de 1 dígito isolado sem símbolo financeiro, pode ser numeração textual
        if token.isdigit() and len(token) == 1:
            continue
        violations.append(token)

    return violations


def resolve_text_placeholders(
    text: str,
    factbook: FactBook,
    news_map: dict[str, NewsItem],
) -> tuple[str, list[str]]:
    """Substitui os placeholders {{fact:id}}, {{news:id}} ou {{id}} pelos valores reais formatados.

    Retorna o texto renderizado e a lista de erros de resolução (placeholders inexistentes).
    """
    errors: list[str] = []

    def replace_placeholder(m: re.Match) -> str:
        key = m.group(1).strip()
        if key.startswith("fact:"):
            fact_id = key[5:].strip()
            fact = factbook.get_fact(fact_id)
            if fact:
                return fact.formatted_value
            errors.append(f"Fato não encontrado no FactBook: '{fact_id}'")
            return f"[FATO NÃO ENCONTRADO: {fact_id}]"
        elif key.startswith("news:"):
            news_id = key[5:].strip()
            news = news_map.get(news_id)
            if news:
                return f"[{news.source}: \"{news.title}\"]"
            errors.append(f"Notícia não encontrada nas notícias elegíveis: '{news_id}'")
            return f"[NOTÍCIA NÃO ENCONTRADA: {news_id}]"
        else:
            # Pode ser um fato direto sem o prefixo 'fact:' (ex: {{portfolio.return_pct}})
            fact = factbook.get_fact(key)
            if fact:
                return fact.formatted_value
            # Ou pode ser uma notícia direta
            news = news_map.get(key)
            if news:
                return f"[{news.source}: \"{news.title}\"]"
            errors.append(f"Placeholder não resolvido ou com sintaxe inválida: {{{key}}}")
            return f"[PLACEHOLDER NÃO ENCONTRADO: {key}]"

    rendered = re.sub(r"\{\{([^}]+)\}\}", replace_placeholder, text)
    rendered = re.sub(r"%\s*%", "%", rendered)

    return rendered, errors


def validate_draft(
    draft: CommentaryDraft,
    factbook: FactBook,
    eligible_news: list[NewsItem],
) -> tuple[CommentaryDraft, list[ValidationCheckResult]]:
    """Executa a bateria de conferências determinísticas no rascunho.

    Retorna o rascunho com os parágrafos renderizados e a lista de resultados das verificações.
    """
    checks: list[ValidationCheckResult] = []
    news_map = {n.news_id: n for n in eligible_news}

    rendered_paragraphs: list[CommentaryParagraph] = []
    total_words = 0
    all_unauthorized_numbers: list[str] = []
    all_placeholder_errors: list[str] = []
    has_invalid_contribution_usage = False

    for p in draft.paragraphs:
        # 1. Resolução de placeholders
        rendered_p_text, p_errors = resolve_text_placeholders(p.text, factbook, news_map)
        all_placeholder_errors.extend(p_errors)

        # 2. Detecção de números financeiros não autorizados no texto original
        unauth = find_unauthorized_numbers(p.text)
        if unauth:
            all_unauthorized_numbers.extend(unauth)

        # 3. Disciplina de uso do termo 'contribuição'
        if "contribui" in p.text.lower():
            # Deve haver pelo menos uma referência a fato de contribution_bps
            has_contrib_fact = any("contribution_bps" in f_id for f_id in p.fact_refs) or "contribution_bps" in p.text
            if not has_contrib_fact:
                has_invalid_contribution_usage = True

        rendered_p = CommentaryParagraph(
            paragraph_id=p.paragraph_id,
            text=p.text,
            rendered_text=rendered_p_text,
            claim_type=p.claim_type,
            fact_refs=p.fact_refs,
            news_refs=p.news_refs,
        )
        rendered_paragraphs.append(rendered_p)
        total_words += len(rendered_p_text.split())

    full_rendered_text = "\n\n".join(
        p.rendered_text for p in rendered_paragraphs if p.rendered_text
    )

    # Checagem 1: Placeholders resolvidos
    checks.append(ValidationCheckResult(
        check_id="check_placeholders",
        name="Resolução integral de placeholders {{fact:...}} e {{news:...}}",
        passed=len(all_placeholder_errors) == 0,
        severity="critical",
        details="Todos os placeholders foram localizados e resolvidos com sucesso."
        if not all_placeholder_errors
        else f"Falha na resolução: {'; '.join(all_placeholder_errors)}",
    ))

    # Checagem 2: Ausência de números financeiros não autorizados
    checks.append(ValidationCheckResult(
        check_id="check_unauthorized_numbers",
        name="Ausência de números financeiros introduzidos fora do FactBook",
        passed=len(all_unauthorized_numbers) == 0,
        severity="critical",
        details="Nenhum número financeiro alucinado ou inserido fora de placeholders."
        if not all_unauthorized_numbers
        else f"Números não autorizados detectados no texto: {', '.join(all_unauthorized_numbers)}",
    ))

    # Checagem 3: Disciplina conceitual do termo 'contribuição'
    checks.append(ValidationCheckResult(
        check_id="check_contribution_discipline",
        name="Uso restrito da palavra 'contribuição' vinculado a contribution_bps",
        passed=not has_invalid_contribution_usage,
        severity="critical",
        details="Termo 'contribuição' utilizado exclusivamente com métrica ponderada da carteira."
        if not has_invalid_contribution_usage
        else "A palavra 'contribuição' foi usada em parágrafo sem referência a fato de contribution_bps.",
    ))

    # Checagem 4: Contagem de palavras (~180 a 300 palavras, tolerância 140 a 350)
    word_count_passed = 140 <= total_words <= 350
    checks.append(ValidationCheckResult(
        check_id="check_word_count",
        name="Tamanho do comentário (~180 a 300 palavras)",
        passed=word_count_passed,
        severity="warning",
        details=f"Comentário contém {total_words} palavras (faixa recomendada: 180-300).",
    ))

    # Checagem 5: Disciplina Causal e Justificação
    causal_issues = []
    for p in draft.paragraphs:
        if p.claim_type == ClaimType.INTERPRETATION and not p.news_refs and not p.fact_refs:
            causal_issues.append(f"Parágrafo {p.paragraph_id} classificado como interpretação mas sem referências.")
    checks.append(ValidationCheckResult(
        check_id="check_causal_discipline",
        name="Sustentação de afirmações interpretativas por referências",
        passed=len(causal_issues) == 0,
        severity="warning",
        details="Todas as interpretações possuem referências documentadas."
        if not causal_issues
        else "; ".join(causal_issues),
    ))

    # Checagem 6: Ausência de termos promocionais ou recomendações de compra/venda
    prohibited_terms = [
        "compre", "venda", "recomendamos compra", "recomendamos venda",
        "preço-alvo", "target price", "oportunidade imperdível", "compre já"
    ]
    found_prohibited = [t for t in prohibited_terms if t in full_rendered_text.lower()]
    checks.append(ValidationCheckResult(
        check_id="check_prohibited_terms",
        name="Ausência de recomendações de investimento ou adjetivos promocionais",
        passed=len(found_prohibited) == 0,
        severity="critical",
        details="Nenhum termo proibido encontrado."
        if not found_prohibited
        else f"Termos proibidos encontrados: {', '.join(found_prohibited)}",
    ))

    updated_draft = CommentaryDraft(
        draft_id=draft.draft_id,
        paragraphs=rendered_paragraphs,
        rendered_text=full_rendered_text,
        provider_id=draft.provider_id,
        model_id=draft.model_id,
        created_at=draft.created_at,
        is_synthetic=draft.is_synthetic,
    )

    return updated_draft, checks
